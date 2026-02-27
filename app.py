# app.py (versão atualizada com hora de nascimento no registro e perfil)
import re
import os
import json
import threading
import requests  # Adicionado para chamadas HTTP à API Vedic
from collections import defaultdict, Counter
from urllib.parse import urlsplit, urlunsplit
from datetime import date, datetime, time  # Adicionado time para horóscopo

from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.serving import run_simple
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, DateField, SelectField, SubmitField, TextAreaField, IntegerField
from wtforms.validators import DataRequired, Email, Length, EqualTo, NumberRange
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from wtforms.fields import IntegerField as WTIntegerField
from wtforms import ValidationError
app = Flask(__name__)
app.debug = True  # Ativado para depuração
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'selfdecrypt-secret-key-2025'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
# ---------- CONFIG ----------
USE_PROXY_FIX = True
PROXY_FIX_CONFIG = dict(x_for=1, x_proto=1, x_host=1)

# HTTP and HTTPS ports for testing
HTTP_PORT = int(os.environ.get("HTTP_PORT", 6101))
HTTPS_PORT = int(os.environ.get("HTTPS_PORT", 6102))

# Use 302 while testing to avoid caching; set to True to use 301 permanently
REDIRECT_PERMANENT = False
# ----------------------------

# Configuração da API Vedic (assumindo que roda em localhost:8000)
VEDIC_API_URL = "http://localhost:8000"

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    birth_date = db.Column(db.Date, nullable=False)
    birth_hour = db.Column(db.Integer, default=12, nullable=False)  # Hora de nascimento (0-23)
    birth_minute = db.Column(db.Integer, default=0, nullable=False)  # Minuto de nascimento (0-59)
    country = db.Column(db.String(50), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(id):
    return db.session.get(User, int(id))  


class SafeIntegerField(WTIntegerField):
    def process_formdata(self, valuelist):
        if not valuelist:
            return
        try:
            # Strip e coerce para int, aceitando '0', '00', etc.
            raw_value = valuelist[0].strip()
            if raw_value == '':
                self.data = None
            else:
                self.data = int(raw_value)
        except ValueError:
            self.data = None
            raise ValueError('Invalid integer value')

# Agora, nos forms:
def validate_time_field(form, field, min_val, max_val, field_name):
    if not field.data:
        raise ValidationError(f'{field_name} is required.')
    try:
        value = int(field.data.strip())
        if not (min_val <= value <= max_val):
            raise ValidationError(f'{field_name} must be between {min_val} and {max_val}.')
        field.data = value  # Armazena como int no data
    except ValueError:
        raise ValidationError(f'{field_name} must be a valid number.')

# Forms atualizados
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password_confirm = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    full_name = StringField('Full Name', validators=[DataRequired()])
    birth_date = DateField('Birth Date', validators=[DataRequired()], format='%Y-%m-%d')
    birth_hour = StringField('Birth Hour (0-23)', validators=[DataRequired(), lambda f, field: validate_time_field(f, field, 0, 23, 'Birth Hour')])
    birth_minute = StringField('Birth Minute (0-59)', validators=[DataRequired(), lambda f, field: validate_time_field(f, field, 0, 59, 'Birth Minute')])
    country = StringField('Country', validators=[DataRequired()])
    city = StringField('City', validators=[DataRequired()])
    phone = StringField('Phone Number', validators=[DataRequired()])
    submit = SubmitField('Register')

class ProfileForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired()])
    birth_date = DateField('Birth Date', validators=[DataRequired()], format='%Y-%m-%d')
    birth_hour = StringField('Birth Hour (0-23)', validators=[DataRequired(), lambda f, field: validate_time_field(f, field, 0, 23, 'Birth Hour')])
    birth_minute = StringField('Birth Minute (0-59)', validators=[DataRequired(), lambda f, field: validate_time_field(f, field, 0, 59, 'Birth Minute')])
    country = StringField('Country', validators=[DataRequired()])
    city = StringField('City', validators=[DataRequired()])
    phone = StringField('Phone Number', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Update Profile')

# Route /register com debug completo (veja console!)
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    print(f"Debug POST data: {request.form}")  # Veja se 'birth_minute' está lá
    if form.validate_on_submit():
        print(f"Debug Sucesso: Hora={form.birth_hour.data}, Minuto={form.birth_minute.data} (types: {type(form.birth_hour.data)}, {type(form.birth_minute.data)})")
        existing_user = User.query.filter((User.username == form.username.data) | (User.email == form.email.data)).first()
        if existing_user:
            flash('Username or email already exists!', 'error')
            return render_template('register.html', form=form)
        
        user = User(
            username=form.username.data,
            email=form.email.data,
            full_name=form.full_name.data,
            birth_date=form.birth_date.data,
            birth_hour=int(form.birth_hour.data),  # Garante int
            birth_minute=int(form.birth_minute.data),  # Garante int
            country=form.country.data,
            city=form.city.data,
            phone=form.phone.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Registration decrypted! Your exact birth time unlocks precise Vedic insights. Log in to begin.', 'success')
        return redirect(url_for('login'))
    else:
        if request.method == 'POST':
            error_details = '; '.join([f"{k}: {v[0]}" for k, v in form.errors.items()])
            print(f"Debug Erros no Form: {error_details}")
            flash(f'Form decryption failed: {error_details}', 'error')
    return render_template('register.html', form=form)

# Para /profile, adicione o mesmo print(request.form) e debug no if validate_on_submit()
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    print(f"Debug Profile POST: {request.form}")
    if form.validate_on_submit():
        print(f"Debug Profile Sucesso: Hora={form.birth_hour.data}, Minuto={form.birth_minute.data}")
        if form.email.data != current_user.email:
            existing_email = User.query.filter_by(email=form.email.data).first()
            if existing_email:
                flash('Email already exists!', 'error')
                return render_template('profile.html', form=form)
        
        current_user.full_name = form.full_name.data
        current_user.birth_date = form.birth_date.data
        current_user.birth_hour = int(form.birth_hour.data)
        current_user.birth_minute = int(form.birth_minute.data)
        current_user.country = form.country.data
        current_user.city = form.city.data
        current_user.phone = form.phone.data
        current_user.email = form.email.data
        db.session.commit()
        flash('Profile decrypted and updated! Recalculate your archetypes for new insights.', 'success')
        return redirect(url_for('seletor'))
    else:
        if request.method == 'POST':
            error_details = '; '.join([f"{k}: {v[0]}" for k, v in form.errors.items()])
            print(f"Debug Profile Erros: {error_details}")
            flash(f'Profile update failed: {error_details}', 'error')
    return render_template('profile.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('lingua'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for('home'))  # Ou 'seletor' se preferir pular direto pro seletor
        flash('Invalid username or password', 'error')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('lingua'))


def carregar_arquetipos():
    try:
        file_path = os.path.join(os.path.dirname(__file__), 'data', 'arquetipos.json')
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {arch['name']: arch for arch in data['archetypes']}
    except FileNotFoundError:
        print(f"Erro: arquetipos.json não encontrado em {os.path.join(os.path.dirname(__file__), 'data')}")
        return {}
    except json.JSONDecodeError:
        print("Erro: JSON inválido em arquetipos.json")
        return {}


def gerar_triangulo_invertido(nome):
    """Gera o triângulo invertido numerológico baseado nas reduções cabalísticas do nome."""
    letra_valor = {
        'a':1, 'i':1, 'j':1, 'q':1, 'y':1,
        'b':2, 'k':2, 'r':2,
        'c':3, 'g':3, 'l':3, 's':3,
        'd':4, 'm':4, 't':4,
        'e':5, 'h':5, 'n':5, 'x':5,
        'u':6, 'v':6, 'w':6,
        'o':7, 'z':7,
        'f':8, 'p':8
    }

    # Limpa e transforma o nome
    nome_limpo = ''.join(c for c in nome.upper() if c.isalpha())
    nome_limpo = nome_limpo.replace('Á','A').replace('É','E').replace('Í','I').replace('Ó','O').replace('Ú','U').replace('Ç','C')
    valores = [letra_valor.get(c.lower(), 0) for c in nome_limpo]

    if not valores:
        return []

    # Geração invertida — começa com a linha das letras e reduz até sobrar 1 número
    linhas = [valores]
    while len(linhas[-1]) > 1:
        anterior = linhas[-1]
        nova = [(anterior[i] + anterior[i+1]) % 9 or 9 for i in range(len(anterior)-1)]
        linhas.append(nova)
    return linhas  # lista de listas (da base ao topo)

def calcular_numerologia_cabalistica(full_name, birth_date):
    # Tabela Chaldean/Cabalistic ocidental
    letra_valor = {
        'a':1, 'i':1, 'j':1, 'q':1, 'y':1,
        'b':2, 'k':2, 'r':2,
        'c':3, 'g':3, 'l':3, 's':3,
        'd':4, 'm':4, 't':4,
        'e':5, 'h':5, 'n':5, 'x':5,
        'u':6, 'v':6, 'w':6,
        'o':7, 'z':7,
        'f':8, 'p':8
    }
    
    def e_vogal(c):
        return c.lower() in 'aeiouy'  # Y como vogal se presente
    
    def reduzir_numero(n, keep_masters=True):
        original = n
        while n > 9:
            if keep_masters and n in [11, 22, 33]:
                return n
            n = sum(int(d) for d in str(n))
        return n
    
    # Nome limpo: maiúsculas, sem acentos/espaços
    nome_limpo = ''.join(c for c in full_name.upper() if c.isalpha())
    nome_limpo = nome_limpo.replace('Á','A').replace('É','E').replace('Í','I').replace('Ó','O').replace('Ú','U').replace('Ç','C')
    valores = [letra_valor.get(c.lower(), 0) for c in nome_limpo]
    
    soma_total = sum(valores)
    expressao_compound = soma_total
    expressao = reduzir_numero(soma_total)
    
    # Motivação/Soul Urge: vogais
    vogais = [valores[i] for i, c in enumerate(nome_limpo) if e_vogal(c)]
    soma_vogais = sum(vogais)
    motivacao_compound = soma_vogais
    motivacao = reduzir_numero(soma_vogais)
    
    # Impressão/Personality: consoantes
    consoantes = [v for v in valores if v not in vogais]  # Aproximação; usa valores não vogal
    soma_consoantes = soma_total - soma_vogais
    impressao_compound = soma_consoantes
    impressao = reduzir_numero(soma_consoantes)
    
    # Data de nascimento
    dia, mes, ano = birth_date.day, birth_date.month, birth_date.year
    soma_ano = sum(int(d) for d in str(ano))
    year_reduced = reduzir_numero(soma_ano)
    life_path_compound = dia + mes + soma_ano
    life_path = reduzir_numero(life_path_compound)  # Destiny from date
    
    # Psychic Number: Dia reduzido
    psiquico = reduzir_numero(dia)
    
    # Missão: Expressão + Life Path
    missao = reduzir_numero(expressao + life_path)
    
    # Ciclos de Vida (Month, Day, Year reduced)
    ciclo1 = reduzir_numero(mes)  # 1º: Mês
    ciclo2 = reduzir_numero(dia)  # 2º: Dia
    ciclo3 = year_reduced  # 3º: Ano reduzido
    
    # Reduzidos para desafios
    reduced_mes = reduzir_numero(mes)
    reduced_dia = reduzir_numero(dia)
    reduced_ano = year_reduced
    
    # Desafios corrigidos: Baseado no Dia para ambos
    desafio1 = reduzir_numero(abs(reduced_dia - reduced_mes))  # Primeiro: |Dia - Mês|
    desafio2 = reduzir_numero(abs(reduced_dia - reduced_ano))  # Segundo: |Dia - Ano|
    desafio_principal = reduzir_numero(abs(desafio1 - desafio2))  # Principal: |Desafio1 - Desafio2|
    
    # Lições Cármicas: Números 1-8 ausentes no nome
    freq = Counter(valores)
    liçoes_carmicas = [i for i in range(1, 9) if freq[i] == 0]
    
    # Tendências Ocultas: Hidden Passion (número com mais ocorrências)
    if valores:
        tendencias_ocultas = max(freq, key=freq.get)
    else:
        tendencias_ocultas = 0
    
    # Resposta Subconsciente: Subconscious Self (número de números únicos no nome, 1-8)
    unique_nums = len([k for k in freq if 1 <= k <= 8 and freq[k] > 0])
    resposta_subconsciente = unique_nums
    
    # Momentos Decisivos (Pinnacles)
    p1 = reduzir_numero(mes + dia)  # 1º: mes + dia
    p2 = reduzir_numero(dia + year_reduced)  # 2º: dia + ano reduzido
    p3 = reduzir_numero(p1 + p2)  # 3º: p1 + p2
    p4 = reduzir_numero(mes + year_reduced)  # 4º: mes + ano reduzido
    
    # Harmonias Conjugais (compatibilidade baseada em Missão; usando tabela cabalística fornecida)
    destiny = missao  # Usar missao para compat
    compat = {
        1: {'vibra_com': [9], 'atrai': [4, 8], 'oposto': [6, 7], 'passivo': [2, 3, 5]},
        2: {'vibra_com': [8], 'atrai': [7, 9], 'oposto': [5], 'passivo': [1, 3, 4, 6]},
        3: {'vibra_com': [7], 'atrai': [5, 6], 'oposto': [4], 'passivo': [1, 2]},
        4: {'vibra_com': [1, 8], 'atrai': [3, 5], 'oposto': [7], 'passivo': [2, 6, 9]},
        5: {'vibra_com': [5], 'atrai': [3, 9], 'oposto': [2, 4], 'passivo': [1, 6, 7, 8]},
        6: {'vibra_com': [4], 'atrai': [3, 9], 'oposto': [1, 8], 'passivo': [2]},
        7: {'vibra_com': [3], 'atrai': [2, 6], 'oposto': [4, 5], 'passivo': [1, 6, 8, 9]},
        8: {'vibra_com': [2], 'atrai': [1, 4], 'oposto': [3], 'passivo': [5, 6, 7, 9]},
        9: {'vibra_com': [1], 'atrai': [2, 6], 'oposto': [8], 'passivo': [3, 4, 5, 7]}
    }
    harmonia = compat.get(destiny, {})
    harmonia_vibra_com = harmonia.get('vibra_com', [])
    harmonia_atrai = harmonia.get('atrai', [])
    harmonia_oposto = harmonia.get('oposto', [])
    harmonia_passivo = harmonia.get('passivo', [])
    
    # Dias favoráveis baseados na Missão
    dias_favoraveis_map = {
        1: ['Domingo', 'Segunda-feira'],
        2: ['Segunda-feira', 'Terça-feira'],
        3: ['Terça-feira', 'Quarta-feira'],
        4: ['Quarta-feira', 'Quinta-feira'],
        5: ['Quinta-feira', 'Sexta-feira'],
        6: ['Sexta-feira', 'Sábado'],
        7: ['Sábado', 'Domingo'],
        8: ['Sábado', 'Domingo'],
        9: ['Domingo', 'Segunda-feira']
    }
    dias_favoraveis = dias_favoraveis_map.get(missao, [])
    
    # Dívidas Cármicas: 13, 14, 16, 19 na soma compound
    dividas_carmicas = []
    if expressao_compound in [13, 14, 16, 19, 22, 26, 28, 31, 34, 37]:
        dividas_carmicas.append(expressao_compound)
    if motivacao_compound in [13, 14, 16, 19]:
        dividas_carmicas.append(motivacao_compound)
    if life_path_compound in [13, 14, 16, 19]:
        dividas_carmicas.append(life_path_compound)
    
    # Triângulo Invertido
    triangulo = gerar_triangulo_invertido(full_name)
    triangulo_html = formatar_triangulo_com_letras(triangulo, full_name)
    
    return {
        'motivacao': motivacao, 'soma_motivacao': motivacao_compound,
        'impressao': impressao, 'soma_impressao': impressao_compound,
        'expressao': expressao, 'soma_expressao': expressao_compound,
        'psiquico': psiquico,
        'destino': life_path,
        'missao': missao,
        'ciclo1': ciclo1, 'ciclo2': ciclo2, 'ciclo3': ciclo3,
        'desafio1': desafio1, 'desafio2': desafio2, 'desafio_principal': desafio_principal,
        'licoes_carmicas': liçoes_carmicas,
        'tendencias_ocultas': tendencias_ocultas,
        'resposta_subconsciente': resposta_subconsciente,
        'momento1': p1, 'momento2': p2, 'momento3': p3, 'momento4': p4,
        'harmonia_vibra_com': harmonia_vibra_com,
        'harmonia_atrai': harmonia_atrai,
        'harmonia_oposto': harmonia_oposto,
        'harmonia_passivo': harmonia_passivo,
        'dias_favoraveis': dias_favoraveis,
        'dividas_carmicas': dividas_carmicas,
        'triangulo_html': triangulo_html
    }


def formatar_triangulo_com_letras(triangulo, nome):
    """Formata com letras alinhadas exatamente acima dos dígitos da primeira fileira.
       Destaca sequências consecutivas (tokens) do mesmo número com tamanho >=3 (1–9).
    """
    nome_limpo = ''.join(c for c in nome.upper() if c.isalpha())
    nome_slots = [f" {l} " for l in nome_limpo]
    nome_formatado = ''.join(nome_slots)

    def num_slot(num):
        return f" {num} " if int(num) < 10 else f"{num} "

    lines = [nome_formatado]
    if triangulo:
        first_line_str = ''.join(num_slot(num) for num in triangulo[0])
        lines.append(first_line_str)
        for linha in triangulo[1:]:
            line_str = ''.join(num_slot(num) for num in linha)
            lines.append(line_str)

    max_len = max(len(line) for line in lines) if lines else 0
    centered_lines = [line.center(max_len) for line in lines]

    token_re = re.compile(r'(\d{1,2})|(\D+)')

    def highlight_line(line):
        parts = token_re.findall(line)
        seq = []
        for num, non in parts:
            if num:
                seq.append({'type': 'num', 'text': num})
            else:
                seq.append({'type': 'sep', 'text': non})

        out = []
        i = 0
        N = len(seq)
        while i < N:
            if seq[i]['type'] == 'num':
                run_val = seq[i]['text']
                run_idxs = [i]
                j = i + 1
                while j < N:
                    if seq[j]['type'] == 'sep':
                        j += 1
                        continue
                    if seq[j]['type'] == 'num' and seq[j]['text'] == run_val:
                        run_idxs.append(j)
                        j += 1
                        continue
                    break
                num_tokens_in_run = len(run_idxs)
                # ✅ Regra 2 — qualquer número repetido >=3
                if num_tokens_in_run >= 3:
                    k = i
                    block = ''
                    while k < j:
                        block += seq[k]['text']
                        k += 1
                    out.append(f'<span style="color:#dc3545;font-weight:700;">{block}</span>')
                    i = j
                else:
                    out.append(seq[i]['text'])
                    i += 1
                while i < N and seq[i]['type'] == 'sep':
                    out.append(seq[i]['text'])
                    i += 1
            else:
                out.append(seq[i]['text'])
                i += 1
        return ''.join(out)

    highlighted = [highlight_line(l) for l in centered_lines]
    tri_html = '\n'.join(highlighted)
    return tri_html

# Função para chamar a API Vedic
# app.py - Updated chamar_api_vedica with better error handling
def chamar_api_vedica(user):
    """Chama a API Vedic para análise completa usando dados do usuário."""
    nascimento_data = {
        "dia": user.birth_date.day,
        "mes": user.birth_date.month,
        "ano": user.birth_date.year,
        "hora": user.birth_hour,
        "minuto": user.birth_minute,
        "segundo": 0,
        "cidade": user.city,
        "pais": user.country,
        "timezone": None,  # Deixar a API detectar
        "latitude": None,
        "longitude": None
    }
    
    print(f"Debug: Enviando para API Vedic: {nascimento_data}")  # Adicionado para debug
    
    try:
        response = requests.post(f"{VEDIC_API_URL}/analise-completa", json=nascimento_data, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as err:
        print(f"HTTP Error na API Vedic: {err.response.status_code} - {err.response.text}")
        flash('Erro ao calcular horóscopo védico. Verifique sua cidade/país e tente novamente.', 'error')
        return None
    except requests.exceptions.RequestException as e:
        print(f"Erro ao chamar API Vedic: {e}")
        flash('Erro ao calcular horóscopo védico. Tente novamente mais tarde.', 'error')
        return None

if USE_PROXY_FIX:
    app.wsgi_app = ProxyFix(app.wsgi_app, **PROXY_FIX_CONFIG)

@app.route('/')
def home():
    return redirect(url_for('lingua'))

@app.route('/lingua')
def lingua():
    return render_template('lingua.html')

@app.route('/landing')
def landing():
    lang = request.args.get('lang', 'pt')
    return render_template('landing.html', lang=lang)

@app.route('/seletor')
@login_required
def seletor(lang=None):
    lang = lang or request.args.get('lang', 'pt')
    return render_template('seletor.html', lang=lang)

@app.route('/questionario/<formato>')
@login_required
def questionario(formato):
    lang = request.args.get('lang', 'pt')
    arquetipos_full = carregar_arquetipos()
    perguntas = []
    for i, nome in enumerate(arquetipos_full):
        questions = arquetipos_full[nome].get('questions', {})
        if formato == 'likert':
            for j, q in enumerate(questions.get('likert', [])):
                perguntas.append({
                    'id': f"{i+1}_likert_{j+1}",
                    'texto': q.get(lang, q.get('pt', 'Pergunta não disponível')),
                    'arquetipo': nome,
                    'tipo': 'likert'
                })
        elif formato == 'escolha':
            for j, escolha in enumerate(questions.get('choice', [])):
                perguntas.append({
                    'id': f"{i+1}_escolha_{j+1}",
                    'A': escolha['A'].get(lang, escolha['A'].get('pt', 'Opção A não disponível')),
                    'B': escolha['B'].get(lang, escolha['B'].get('pt', 'Opção B não disponível')),
                    'texto': None,
                    'arquetipo': nome,
                    'tipo': 'escolha'
                })

    if app.debug:
        print(f"Debug: {len(perguntas)} perguntas carregadas para {formato}/{lang}")
        for p in perguntas[:2]:
            print(f"Ex: {p['id']} - Tipo: {p['tipo']} - Texto/A: {p.get('texto', p.get('A', 'N/A'))}")

    return render_template('index.html', perguntas=perguntas, formato=formato, lang=lang)


@app.route('/resultado', methods=['POST'])
@login_required
def resultado():
    lang = request.form.get('lang', request.args.get('lang', 'pt'))
    respostas = request.form
    formato = respostas.get('formato', 'likert')
    arquetipos_full = carregar_arquetipos()
    if not arquetipos_full:
        return "Erro: Arquétipos não carregados.", 500

    pontuacao = defaultdict(int)
    max_possivel = defaultdict(int)

    for nome in arquetipos_full:
        questions = arquetipos_full[nome].get('questions', {})
        num_likert = len(questions.get('likert', []))
        num_choice = len(questions.get('choice', []))
        if formato == 'likert':
            max_possivel[nome] = num_likert * 5
        else:
            max_possivel[nome] = num_choice * 2

    for key, value in respostas.items():
        if key in ['formato', 'lang']:
            continue
        if '_' in key:
            parts = key.split('_')
            if len(parts) >= 3:
                try:
                    id_arch = int(parts[0]) - 1
                    tipo_q = parts[1]
                    id_q = int(parts[-1])
                    nomes = list(arquetipos_full.keys())
                    if 0 <= id_arch < len(nomes):
                        nome = nomes[id_arch]
                        if formato == 'likert':
                            pontuacao[nome] += int(value)
                        elif formato == 'escolha':
                            if value == 'A':
                                pontuacao[nome] += 2
                            elif value == 'B':
                                pontuacao[nome] += 1
                except (ValueError, IndexError, KeyError):
                    if app.debug:
                        print(f"Erro ao processar {key}: {value}")
                    continue

    for nome in list(pontuacao.keys()):
        if max_possivel[nome] > 0:
            pontuacao[nome] = round((pontuacao[nome] / max_possivel[nome]) * 100)
        else:
            del pontuacao[nome]

    for nome in arquetipos_full:
        if nome not in pontuacao:
            pontuacao[nome] = 0

    ranking = sorted(pontuacao.items(), key=lambda x: x[1], reverse=True)
    categorias = {
        'regente': ranking[0:1] if ranking else [],
        'secundarios': ranking[1:6] if len(ranking) > 1 else [],
        'emergentes': ranking[6:12] if len(ranking) > 6 else [],
        'fracos': ranking[12:] if len(ranking) > 12 else []
    }

    if app.debug:
        print(f"Debug: Ranking calculado: {ranking[:3]}... (top 3)")

    # Integração unificada: Calcular numerologia para o usuário logado
    numerologia = calcular_numerologia_cabalistica(current_user.full_name, current_user.birth_date)
    
    # Carregar descrições de numerologia
    descricoes_numerologia = {}
    try:
        file_path = os.path.join(os.path.dirname(__file__), 'data', 'numerologia.json')
        with open(file_path, 'r', encoding='utf-8') as f:
            descricoes_numerologia = json.load(f)
    except FileNotFoundError:
        print(f"numerologia.json não encontrado em {os.path.join(os.path.dirname(__file__), 'data')}; usando vazio.")
    except json.JSONDecodeError:
        print("JSON inválido em numerologia.json")

    # Integração da API Vedic
    vedica = chamar_api_vedica(current_user)

    return render_template('resultado.html', ranking=ranking, categorias=categorias, arquetipos_full=arquetipos_full, lang=lang, numerologia=numerologia, descricoes_numerologia=descricoes_numerologia, vedica=vedica)


@app.route('/numerologia')
@login_required
def numerologia():
    lang = request.args.get('lang', 'pt')
    numerologia = calcular_numerologia_cabalistica(current_user.full_name, current_user.birth_date)
    descricoes = {}
    try:
        file_path = os.path.join(os.path.dirname(__file__), 'data', 'numerologia.json')
        with open(file_path, 'r', encoding='utf-8') as f:
            descricoes = json.load(f)
    except FileNotFoundError:
        print(f"numerologia.json não encontrado em {os.path.join(os.path.dirname(__file__), 'data')}; usando vazio.")
    except json.JSONDecodeError:
        print("JSON inválido em numerologia.json")
    return render_template('resultado_numerologia.html', numerologia=numerologia, descricoes=descricoes, lang=lang)


# ---- server runners for testing ----
def run_http_server():
    print(f"Starting HTTP server on 0.0.0.0:{HTTP_PORT}")
    run_simple('0.0.0.0', HTTP_PORT, app, use_reloader=False, threaded=True)


def run_https_server():
    cert = os.environ.get('SSL_CERT', 'cert.pem')
    key = os.environ.get('SSL_KEY', 'key.pem')
    if not (os.path.exists(cert) and os.path.exists(key)):
        print(f"HTTPS cert/key not found (expected {cert} and {key}). HTTPS server won't start.")
        return
    print(f"Starting HTTPS server on 0.0.0.0:{HTTPS_PORT} (redirects to HTTP on port {HTTP_PORT})")
    run_simple('0.0.0.0', HTTPS_PORT, app, ssl_context=(cert, key), use_reloader=False, threaded=True)
    
def calcular_idade(birth_date):
    today = date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


@app.context_processor
def utility_processor():
    return dict(calcular_idade=calcular_idade)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    # Start HTTPS runner in background (if cert exists), and always start the HTTP server.
    t = threading.Thread(target=run_https_server, daemon=True)
    t.start()
    run_http_server()