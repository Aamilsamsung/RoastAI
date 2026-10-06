from typing import Literal
from pydantic import BaseModel, Field, field_validator
Modes=Literal["normal","sarcastic","savage","brutal","vulgar","funny","deadpan","intelligent","respectful"]
Profanity=Literal["off","light","heavy"]
Script=Literal["native","roman"]
ReplyLanguage=Literal["same","english","hindi","kannada","malayalam","tamil","telugu","bengali","marathi","punjabi","urdu"]
class BotSettings(BaseModel):
    enabled: bool=False; whatsapp_enabled: bool=True; instagram_enabled: bool=True; facebook_enabled: bool=False
    roast_mode: Modes="savage"; intensity:int=Field(7,ge=1,le=10); profanity_level:Profanity="light"
    custom_instructions:str=Field("",max_length=2000); reply_delay_seconds:float=Field(1,ge=0,le=60); cooldown_seconds:int=Field(10,ge=0,le=3600)
    max_reply_length:int=Field(300,ge=50,le=1000); dry_run:bool=True; input_language:str=Field("auto",max_length=40)
    reply_language:ReplyLanguage="same"; script_mode:Script="roman"
class RoastRequest(BaseModel):
    message:str=Field(min_length=1,max_length=5000); sender_name:str=Field("Someone",max_length=100); input_language:str=Field("auto",max_length=40)
    reply_language:ReplyLanguage="same"; script_mode:Script="roman"

    @field_validator('message')
    @classmethod
    def meaningful_message(cls, value):
        if not value.strip(): raise ValueError('Message cannot be blank')
        return value
