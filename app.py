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
    client_kwargs={"scope": "identificacao email documentos_pessoais"},
)

# --- Helpers ---
def is_logged_in():
    return "token" in session

def make_suap_request(endpoint):
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
            print(f"Erro {response.status_code} na requisição para {endpoint}: {response.text}")
            return None
    except Exception as e:
        print(f"Erro na requisição para {endpoint}: {e}")
        return None

def fetch_user():
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
    cursos = make_suap_request("minhas-informacoes/meus-cursos/")
    if cursos and isinstance(cursos, list) and len(cursos) > 0:
        return cursos[0]
    return None

def fetch_periods():
    periods_data = make_suap_request("minhas-informacoes/meus-periodos-letivos/")
    if periods_data and isinstance(periods_data, list):
        return periods_data
    return []

def fetch_boletim(ano, periodo):
    endpoint = f"minhas-informacoes/boletim/{ano}/{periodo}/"
    boletim_data = make_suap_request(endpoint)

    if boletim_data and isinstance(boletim_data, list):
        # Normalizar carga horária para cada disciplina
        for d in boletim_data:
            carga_horaria = (
                d.get("carga_horaria")
                or d.get("ch_total")
                or d.get("componente_curricular_ch")
            )
            if isinstance(d.get("disciplina"), dict):
                carga_horaria = carga_horaria or d["disciplina"].get("carga_horaria")
            if d.get("diario") and isinstance(d["diario"].get("disciplina"), dict):
                carga_horaria = carga_horaria or d["diario"]["disciplina"].get("carga_horaria")

            d["carga_horaria_normalizada"] = carga_horaria or "N/A"

        return boletim_data
    return []

# --- Context Processor ---
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
    ano_selecionado = request.args.get("ano", type=int)

    # Define o ano mais recente como padrão se nenhum for selecionado
    if not ano_selecionado:
        if periods:
            anos_disponiveis = sorted(list(set(p['ano_letivo'] for p in periods)), reverse=True)
            ano_selecionado = anos_disponiveis[0]
        else:
            ano_selecionado = date.today().year

    # Buscar boletim nos dois períodos e juntar
    boletim_data = []
    boletim_p1 = fetch_boletim(ano_selecionado, 1)
    boletim_p2 = fetch_boletim(ano_selecionado, 2)
    if boletim_p1:
        boletim_data.extend(boletim_p1)
    if boletim_p2:
        boletim_data.extend(boletim_p2)

    return render_template(
        "boletim.html",
        boletim=boletim_data,
        ano_selecionado=ano_selecionado,
        periods=periods
    )

if __name__ == "__main__":
    app.run(debug=True, port=5000)
