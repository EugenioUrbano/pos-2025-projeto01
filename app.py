import os
from datetime import date
from flask import Flask, redirect, url_for, session, render_template, request
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import requests

# --- Carregar variáveis de ambiente ---
load_dotenv()

# --- Criar app Flask ---
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", "chave-dev")

# --- Configuração OAuth SUAP ---
oauth = OAuth(app)
suap = oauth.register(
    name="suap",
    client_id=os.getenv("SUAP_CLIENT_ID"),
    client_secret=os.getenv("SUAP_CLIENT_SECRET"),
    access_token_url="https://suap.ifrn.edu.br/o/token/",
    authorize_url="https://suap.ifrn.edu.br/o/authorize/",
    api_base_url="https://suap.ifrn.edu.br/api/v2/",
    client_kwargs={"scope": "identificacao email"},
)

# --- Helpers ---
def is_logged_in():
    return "token" in session

def make_suap_request(endpoint):
    """Faz requisições autenticadas para a API do SUAP"""
    if not is_logged_in():
        return None

    headers = {
        "Authorization": f"Bearer {session['token']['access_token']}",
        "Accept": "application/json"
    }

    try:
        url = f"https://suap.ifrn.edu.br/api/v2/{endpoint}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Erro {response.status_code} na requisição para {endpoint}")
            return None
    except Exception as e:
        print(f"Erro na requisição para {endpoint}: {e}")
        return None

def fetch_user():
    """Busca dados básicos do usuário logado"""
    user_data = make_suap_request("minhas-informacoes/meus-dados/")
    if user_data:
        user_data['matricula'] = user_data.get('matricula', '')
        foto = user_data.get('url_foto_150x200', '')
        if foto and not foto.startswith("http"):
            foto = f"https://suap.ifrn.edu.br{foto}"
        user_data['url_foto'] = foto
        user_data['nome_completo'] = user_data.get('nome_usual', user_data.get('nome', ''))
    return user_data

def fetch_student_data():
    """Busca informações acadêmicas do estudante (curso)"""
    cursos = make_suap_request("minhas-informacoes/meus-cursos/")
    if cursos and isinstance(cursos, list) and len(cursos) > 0:
        return cursos[0]  # primeiro curso ativo
    return None

def fetch_periods():
    """Busca períodos letivos disponíveis no boletim"""
    periods_data = make_suap_request("minhas-informacoes/boletim/")
    print(">>> DEBUG periods:", periods_data)

    if periods_data and isinstance(periods_data, dict) and 'results' in periods_data:
        return periods_data['results']
    elif periods_data and isinstance(periods_data, list):
        return periods_data
    return []

def fetch_boletim(ano, periodo):
    """Busca boletim para um ano e período específico"""
    # Tenta formato com query params
    boletim_data = make_suap_request(
        f"minhas-informacoes/boletim/?ano_letivo={ano}&periodo_letivo={periodo}"
    )
    print(">>> DEBUG boletim (query params):", boletim_data)

    if boletim_data and isinstance(boletim_data, dict) and 'results' in boletim_data:
        return boletim_data['results']
    if boletim_data and isinstance(boletim_data, list) and len(boletim_data) > 0:
        return boletim_data

    # Se não vier nada, tenta formato alternativo
    boletim_data_alt = make_suap_request(
        f"minhas-informacoes/boletim/{ano}/{periodo}/"
    )
    print(">>> DEBUG boletim (rota direta):", boletim_data_alt)

    if boletim_data_alt and isinstance(boletim_data_alt, list):
        return boletim_data_alt

    return []


# Disponibiliza user em todos os templates
@app.context_processor
def inject_user():
    user = fetch_user() if is_logged_in() else None
    return dict(user=user)

# --- Rotas ---
@app.route("/")
def index():
    if is_logged_in():
        return redirect(url_for("perfil"))
    return render_template("index.html")

@app.route("/login")
def login():
    redirect_uri = url_for("authorize", _external=True)
    return suap.authorize_redirect(redirect_uri)

@app.route("/login/authorized")
def authorize():
    try:
        token = suap.authorize_access_token()
        session["token"] = token
        return redirect(url_for("perfil"))
    except Exception as e:
        print(f"Erro na autenticação: {e}")
        return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/perfil")
def perfil():
    if not is_logged_in():
        return redirect(url_for("login"))

    user_data = fetch_user()
    student_data = fetch_student_data()
    return render_template("perfil.html", user_data=user_data, student_data=student_data)

@app.route("/boletim")
def boletim():
    if not is_logged_in():
        return redirect(url_for("login"))

    periods = fetch_periods()

    ano = request.args.get("ano", type=int)
    periodo = request.args.get("periodo", type=int)

    if not ano or not periodo:
        if periods:
            sorted_periods = sorted(
                periods,
                key=lambda x: (x['ano_letivo'], x['periodo_letivo']),
                reverse=True
            )
            ano = sorted_periods[0]['ano_letivo']
            periodo = sorted_periods[0]['periodo_letivo']
        else:
            current_date = date.today()
            ano = current_date.year
            periodo = 1 if current_date.month <= 6 else 2

    boletim_data = fetch_boletim(ano, periodo)

    return render_template(
        "boletim.html",
        boletim=boletim_data,
        ano=ano,
        periodo=periodo,
        periods=periods
    )

if __name__ == "__main__":
    app.run(debug=True, port=5000)
