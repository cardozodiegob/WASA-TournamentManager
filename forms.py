"""WTForms form classes for Tournament Manager V10."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, PasswordField, TextAreaField, SelectField,
    IntegerField, BooleanField, SubmitField, HiddenField,
    DateTimeField, ValidationError
)
from wtforms.validators import (
    DataRequired, Email, EqualTo, Length, Optional, NumberRange, Regexp
)

class LoginForm(FlaskForm):
    username=StringField('Username',validators=[DataRequired(),Length(3,64)])
    password=PasswordField('Password',validators=[DataRequired()])
    remember=BooleanField('Remember')
    submit=SubmitField('Sign In')

class RegForm(FlaskForm):
    username=StringField('Username',validators=[DataRequired(),Length(3,64),
        Regexp(r'^[\w.]+$',message='Letters/numbers/dots/underscores.')])
    email=StringField('Email',validators=[DataRequired(),Email(),Length(max=120)])
    password=PasswordField('Password',validators=[DataRequired(),Length(8,128)])
    password2=PasswordField('Confirm',validators=[DataRequired(),EqualTo('password')])
    submit=SubmitField('Register')
    def validate_username(s,f):
        from models import User
        if User.query.filter_by(username=f.data).first(): raise ValidationError('Taken.')
    def validate_email(s,f):
        from models import User
        if User.query.filter_by(email=f.data).first(): raise ValidationError('Registered.')

class ProfileForm(FlaskForm):
    display_name=StringField('Name',validators=[Optional(),Length(max=64)])
    bio=TextAreaField('Bio',validators=[Optional(),Length(max=500)])
    submit=SubmitField('Save')

class ClanForm(FlaskForm):
    name=StringField('Name',validators=[DataRequired(),Length(3,64)])
    tag=StringField('Tag',validators=[DataRequired(),Length(4,4),
        Regexp(r'^[A-Za-z0-9]{4}$',message='4 alnum.')])
    description=TextAreaField('Desc',validators=[Optional(),Length(max=1000)])
    recruiting=BooleanField('Recruiting',default=True)
    max_members=IntegerField('Max',validators=[Optional(),NumberRange(2,200)],default=50)
    submit=SubmitField('Save')

class TourneyForm(FlaskForm):
    name=StringField('Name',validators=[DataRequired(),Length(3,128)])
    desc=TextAreaField('Desc',validators=[Optional(),Length(max=2000)])
    game=StringField('Game',validators=[Optional(),Length(max=64)])
    fmt=SelectField('Format',choices=[('single_elimination','Single Elim'),('double_elimination','Double Elim'),('round_robin','Round Robin'),('swiss','Swiss')])
    max_p=IntegerField('Max',validators=[DataRequired(),NumberRange(2,256)],default=32)
    prize=StringField('Prize',validators=[Optional(),Length(max=128)])
    rules=TextAreaField('Rules',validators=[Optional(),Length(max=5000)])
    start=DateTimeField('Start',format='%Y-%m-%dT%H:%M',validators=[Optional()])
    reg_dl=DateTimeField('Deadline',format='%Y-%m-%dT%H:%M',validators=[Optional()])
    ranked=BooleanField('Ranked',default=True)
    default_series=SelectField('Default Series',choices=[('bo1','Best of 1'),('bo3','Best of 3'),('bo5','Best of 5')],default='bo1')
    verify_timeout_days=IntegerField('Verification Timeout (days)',validators=[Optional(),NumberRange(min=0)],default=0)
    submit=SubmitField('Save')

class MatchForm(FlaskForm):
    p1_id=SelectField('P1',coerce=int,validators=[DataRequired()])
    p2_id=SelectField('P2',coerce=int,validators=[DataRequired()])
    p1_score=IntegerField('P1',validators=[Optional(),NumberRange(min=0)],default=0)
    p2_score=IntegerField('P2',validators=[Optional(),NumberRange(min=0)],default=0)
    draw=BooleanField('Draw')
    ranked=BooleanField('Ranked',default=True)
    notes=TextAreaField('Notes',validators=[Optional(),Length(max=500)])
    submit=SubmitField('Submit')

class NewsForm(FlaskForm):
    title=StringField('Title',validators=[DataRequired(),Length(3,200)])
    summary=TextAreaField('Summary',validators=[Optional(),Length(max=2000)])
    content=TextAreaField('Content',validators=[DataRequired()])
    category=SelectField('Cat',choices=[('general','General'),('tournament','Tournament'),('update','Update'),('community','Community'),('patch','Patch'),('match','Match')])
    image=FileField('Image',validators=[Optional(),FileAllowed(['jpg','jpeg','png','gif','webp'])])
    pinned=BooleanField('Pin')
    submit=SubmitField('Publish')

class AdminUserForm(FlaskForm):
    display_name=StringField('Name',validators=[Optional(),Length(max=64)])
    email=StringField('Email',validators=[DataRequired(),Email()])
    admin=BooleanField('Admin')
    banned=BooleanField('Banned')
    ban_reason=StringField('Reason',validators=[Optional(),Length(max=256)])
    elo=IntegerField('ELO',validators=[Optional(),NumberRange(0,5000)])
    submit=SubmitField('Save')

class AchForm(FlaskForm):
    title=StringField('Title',validators=[DataRequired(),Length(2,128)])
    description=TextAreaField('Desc',validators=[Optional(),Length(max=500)])
    image=FileField('PNG',validators=[Optional(),FileAllowed(['png'])])
    submit=SubmitField('Create')

class ChallengeForm(FlaskForm):
    to_id=SelectField('Player',coerce=int,validators=[DataRequired()])
    when=DateTimeField('When',format='%Y-%m-%dT%H:%M',validators=[Optional()])
    msg=StringField('Msg',validators=[Optional(),Length(max=500)])
    ranked=BooleanField('Ranked',default=False)
    stake=IntegerField('Stake',validators=[Optional(),NumberRange(min=0,max=500)],default=0)
    series_format=SelectField('Series',choices=[('bo1','Best of 1'),('bo3','Best of 3'),('bo5','Best of 5')],default='bo1')
    submit=SubmitField('Send')

class ResultForm(FlaskForm):
    my_score=IntegerField('You',validators=[Optional(),NumberRange(min=0)],default=0)
    opp_score=IntegerField('Opp',validators=[Optional(),NumberRange(min=0)],default=0)
    draw=BooleanField('Draw')
    notes=TextAreaField('Notes',validators=[Optional(),Length(max=500)])
    submit=SubmitField('Submit')

class AdminAlertForm(FlaskForm):
    target=SelectField('To',coerce=int,validators=[DataRequired()])
    title=StringField('Title',validators=[DataRequired(),Length(3,128)])
    message=TextAreaField('Message',validators=[DataRequired(),Length(max=500)])
    cat=SelectField('Type',choices=[('info','Info'),('success','Success'),('warning','Warning'),('danger','Danger')])
    submit=SubmitField('Send')
