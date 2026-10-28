"""Proposed manual generation entitlements. Payment collection is not enabled.

Reservations and request claims share a transaction. Failed requests release their
reservation; ambiguous/crashed requests retain it until reviewed. UTC calendar
months define the allowance, independently of a provider's billing anniversary.
"""
from datetime import datetime, timezone
import time
from fastapi import HTTPException
from . import store
from .config import settings

PLANS = {
    'free': {'monthly_generations': 30, 'price_inr': 0},
    'pro': {'monthly_generations': 500, 'price_inr': 299},
    'business': {'monthly_generations': 2500, 'price_inr': 999},
}


def month_key():
    return datetime.now(timezone.utc).strftime('%Y-%m')


def effective_plan(connection, owner_id):
    row = connection.execute(store.text(
        'SELECT plan,status,paid_until FROM subscriptions WHERE owner_id=:o'
    ), {'o': owner_id}).mappings().first()
    # Cancellation keeps access through the already paid period. Past-due,
    # expired and unknown states fail closed to Free; no client-supplied plan.
    if row and row['plan'] in PLANS and row['status'] in ('active', 'cancelled') and row['paid_until'] > time.time():
        return row['plan']
    return 'free'


def reserve(connection, request_id):
    if not settings.manual_generation_limits_enabled or store.owner.get() == 0:
        return
    owner_id, month = store.owner.get(), month_key()
    connection.execute(store.text(
        'INSERT INTO monthly_usage(owner_id,month) VALUES(:o,:m) ON CONFLICT(owner_id,month) DO NOTHING'
    ), {'o': owner_id, 'm': month})
    limit = PLANS[effective_plan(connection, owner_id)]['monthly_generations']
    updated = connection.execute(store.text(
        'UPDATE monthly_usage SET generations=generations+1 WHERE owner_id=:o AND month=:m AND generations<:n'
    ), {'o': owner_id, 'm': month, 'n': limit})
    if updated.rowcount != 1:
        raise HTTPException(429, 'Monthly AI generation allowance reached')
    connection.execute(store.text(
        "INSERT INTO usage_reservations(owner_id,request_id,month,status) VALUES(:o,:r,:m,'reserved')"
    ), {'o': owner_id, 'r': request_id, 'm': month})


def settle(connection, request_id, success, usage):
    owner_id = store.owner.get()
    row = connection.execute(store.text(
        'SELECT month FROM usage_reservations WHERE owner_id=:o AND request_id=:r'
    ), {'o': owner_id, 'r': request_id}).mappings().first()
    if not row:
        return
    updated = connection.execute(store.text(
        "UPDATE usage_reservations SET status=:s WHERE owner_id=:o AND request_id=:r AND status='reserved'"
    ), {'o': owner_id, 'r': request_id, 's': 'done' if success else 'released'})
    if updated.rowcount != 1:
        return
    values = {'o': owner_id, 'm': row['month'], 'refund': 0 if success else 1}
    # Only aggregate observed SDK counters; absent counters remain unknown in
    # each request's durable response and are not estimates of provider billing.
    for field in ('input_tokens', 'output_tokens', 'total_tokens'):
        value = usage.get(field)
        values[field] = value if success and type(value) is int and value >= 0 else 0
    connection.execute(store.text(
        'UPDATE monthly_usage SET generations=generations-:refund,input_tokens=input_tokens+:input_tokens,'
        'output_tokens=output_tokens+:output_tokens,total_tokens=total_tokens+:total_tokens WHERE owner_id=:o AND month=:m'
    ), values)


def summary():
    owner_id, month = store.owner.get(), month_key()
    with store.engine.begin() as connection:
        plan = effective_plan(connection, owner_id)
        row = connection.execute(store.text(
            'SELECT generations,input_tokens,output_tokens,total_tokens FROM monthly_usage WHERE owner_id=:o AND month=:m'
        ), {'o': owner_id, 'm': month}).mappings().first()
    return {'plan': plan, 'plans': PLANS, 'month_utc': month,
            'usage': dict(row) if row else {'generations': 0, 'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
            'manual_limits_enabled': settings.manual_generation_limits_enabled,
            'payments_enabled': False, 'scope': 'manual_generations_only',
            'token_accounting': 'observed_successful_sdk_counters_only'}
