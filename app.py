import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from supabase import create_client, Client
from werkzeug.security import generate_password_hash, check_password_hash

# Importando a lógica do novo arquivo de PDF
from pdf_generator import criar_pdf_buffer

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "uma-chave-padrao-segura")

# Configurações do Supabase
URL_SUPABASE = os.environ.get("SUPABASE_URL", "")
CHAVE_SUPABASE = os.environ.get("SUPABASE_KEY", "")
supabase: Client = create_client(URL_SUPABASE, CHAVE_SUPABASE)

# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/cadastro')
def cadastro_page():
    return render_template('cadastro.html')

@app.route('/auth/cadastro', methods=['POST'])
def realizar_cadastro():
    nome = request.form.get('nome')
    email = request.form.get('email')
    senha = request.form.get('senha')
    cargo = str(request.form.get('cargo')).strip()
    senha_hash = generate_password_hash(senha)

    try:
        data = {"nome": nome, "email": email, "senha": senha_hash, "cargo": cargo}
        supabase.table("usuarios").insert(data).execute()
        flash("Cadastro realizado com sucesso!", "success")
        return redirect(url_for('login_page'))
    except Exception as e:
        flash(f"Erro: {str(e)}", "danger")
        return redirect(url_for('cadastro_page'))

@app.route('/auth/login', methods=['POST'])
def realizar_login():
    email = request.form.get('email')
    senha = request.form.get('senha')
    res = supabase.table("usuarios").select("*").eq("email", email).execute()
    
    if res.data and check_password_hash(res.data[0]['senha'], senha):
        session['user_id'] = res.data[0]['id']
        session['user_nome'] = res.data[0]['nome']
        session['user_role'] = str(res.data[0]['cargo']).strip()
        return redirect(url_for('dashboard'))
    
    flash("E-mail ou senha incorretos.", "danger")
    return redirect(url_for('login_page'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# --- ROTAS DE DASHBOARD E NAVEGAÇÃO ---

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: 
        return redirect(url_for('login_page'))
    
    try:
        # Ordenar funcionários pelos mais recentes
        func_res = supabase.table("funcionarios").select("*").order("created_at", desc=True).execute()
        itens_res = supabase.table("checklist_modelos").select("*").eq("excluido", False).execute()
        
        # Agrupar nomes de modelos únicos para os selects do formulário
        modelos_admissao = sorted(list(set(item['nome_checklist'] for item in itens_res.data if item['tipo'] == 'admissao')))
        modelos_desligamento = sorted(list(set(item['nome_checklist'] for item in itens_res.data if item['tipo'] == 'desligamento')))

        if session['user_role'] == 'RH':
            return render_template('dashboard_rh.html', 
                                   nome=session['user_nome'], 
                                   funcionarios=func_res.data,
                                   itens_master=itens_res.data,
                                   modelos_admissao=modelos_admissao,
                                   modelos_desligamento=modelos_desligamento)
        else:
            return render_template('dashboard_administrativo.html', 
                                   nome=session['user_nome'], 
                                   funcionarios=func_res.data)
    except Exception as e:
        flash(f"Erro ao carregar dados: {str(e)}", "danger")
        return render_template('login.html')

# --- OPERAÇÕES DE NEGÓCIO (RH) ---

@app.route('/cadastrar_funcionario', methods=['POST'])
def cadastrar_funcionario():
    if session.get('user_role') != 'RH': return redirect(url_for('index'))
    
    nome = request.form.get('nome')
    cpf = request.form.get('cpf')
    data_adm = request.form.get('data_admissao')
    modelo_nome = request.form.get('modelo_checklist')
    
    try:
        # 1. Cadastra o Funcionário
        resp = supabase.table("funcionarios").insert({
            "nome": nome, "cpf": cpf, "data_admissao": data_adm
        }).execute()
        
        if resp.data:
            novo_id = resp.data[0]['id']
            # 2. Busca itens do modelo selecionado
            itens_modelo = supabase.table("checklist_modelos").select("id").eq("nome_checklist", modelo_nome).eq("excluido", False).execute()
            
            # 3. Cria as respostas iniciais apenas para os itens desse modelo
            if itens_modelo.data:
                respostas_batch = [
                    {"funcionario_id": novo_id, "item_id": item['id'], "validado_rh": False, "validado_executivo": False}
                    for item in itens_modelo.data
                ]
                supabase.table("checklist_respostas").insert(respostas_batch).execute()

        flash("Funcionário e Checklist de Admissão criados!", "success")
    except Exception as e:
        flash(f"Erro ao cadastrar funcionário: {str(e)}", "danger")
    
    return redirect(url_for('dashboard'))

@app.route('/cadastrar_item_checklist_massa', methods=['POST'])
def cadastrar_item_checklist_massa():
    if session.get('user_role') != 'RH': return redirect(url_for('index'))
    
    descricoes = request.form.getlist('descricao[]')
    tipo_global = request.form.get('tipo_global')
    nome_checklist = request.form.get('nome_checklist') # Novo campo solicitado
    
    try:
        itens_para_inserir = []
        for d in descricoes:
            if d.strip(): 
                itens_para_inserir.append({"descricao": d, "tipo": tipo_global, "nome_checklist": nome_checklist})
        
        if itens_para_inserir:
            supabase.table("checklist_modelos").insert(itens_para_inserir).execute()
            flash(f"{len(itens_para_inserir)} itens adicionados ao modelo global!", "success")
    except Exception as e:
        flash(f"Erro ao salvar modelos: {str(e)}", "danger")
    
    return redirect(url_for('dashboard'))

# --- SISTEMA DE CHECKLIST E VALIDAÇÃO ---

@app.route('/validar/<id_funcionario>')
def tela_validacao(id_funcionario):
    if 'user_id' not in session: return redirect(url_for('login_page'))
    
    print(f"DEBUG: Cargo do usuário na sessão: '{session.get('user_role')}'")

    try:
        func_query = supabase.table("funcionarios").select("*").eq("id", id_funcionario).single().execute()
        func = func_query.data

        # Busca apenas os itens que já foram vinculados a este funcionário
        checklists = supabase.table("checklist_respostas").select("*, checklist_modelos(descricao, tipo)").eq("funcionario_id", id_funcionario).execute().data
        
        return render_template('validar_checklist.html', funcionario=func, checklists=checklists)
    except Exception as e:
        flash(f"Erro ao carregar checklist: {str(e)}", "danger")
        return redirect(url_for('dashboard'))

@app.route('/salvar_checklist/<id_funcionario>', methods=['POST'])
def salvar_checklist(id_funcionario):
    user_role = str(session.get('user_role', '')).upper()
    
    # Verifica se o checklist já está encerrado
    func = supabase.table("funcionarios").select("status").eq("id", id_funcionario).single().execute().data
    if func and func.get('status') == 'Finalizado':
        flash("Este checklist está finalizado e não pode mais ser editado.", "warning")
        return redirect(url_for('dashboard'))
    
    try:
        # Busca todas as respostas atuais para este funcionário para saber o que processar
        respostas = supabase.table("checklist_respostas").select("id").eq("funcionario_id", id_funcionario).execute().data
        
        for r in respostas:
            id_res = r['id']
            
            if user_role == 'RH':
                # O RH como Master pode validar tanto o seu campo quanto o Administrativo
                val_rh = True if request.form.get(f"item_{id_res}_rh") == 'on' else False
                val_adm = True if request.form.get(f"item_{id_res}_adm") == 'on' else False
                
                supabase.table("checklist_respostas").update({
                    "validado_rh": val_rh, 
                    "validado_executivo": val_adm
                }).eq("id", id_res).execute()
                
            elif user_role in ['EXECUTIVO', 'ADMINISTRATIVO']:
                # Para o Administrativo, verifica se o campo 'item_ID_adm' está no form
                campo_nome = f"item_{id_res}_adm"
                # O Administrativo pode validar o campo administrativo a qualquer momento
                valor = True if request.form.get(campo_nome) == 'on' else False
                supabase.table("checklist_respostas").update({"validado_executivo": valor}).eq("id", id_res).execute()
                
        flash("Validações salvas com sucesso!", "success")
    except Exception as e:
        flash(f"Erro ao salvar: {str(e)}", "danger")
        
    return redirect(url_for('dashboard'))

# --- NOVAS ROTAS DE CONTROLE DE FLUXO ---

@app.route('/iniciar_desligamento/<id_funcionario>', methods=['POST'])
def iniciar_desligamento(id_funcionario):
    if session.get('user_role') != 'RH': return redirect(url_for('index'))
    modelo_nome = request.form.get('modelo_desligamento')

    try:
        # Marcar que o desligamento foi iniciado
        supabase.table("funcionarios").update({"foi_desligado": True}).eq("id", id_funcionario).execute()
        
        # Adicionar itens do modelo de desligamento ao checklist do funcionário
        itens_modelo = supabase.table("checklist_modelos").select("id").eq("nome_checklist", modelo_nome).eq("excluido", False).execute()
        
        if itens_modelo.data:
            respostas_batch = [
                {"funcionario_id": id_funcionario, "item_id": item['id'], "validado_rh": False, "validado_executivo": False}
                for item in itens_modelo.data
            ]
            supabase.table("checklist_respostas").insert(respostas_batch).execute()
            flash("Checklist de Desligamento iniciado!", "success")
    except Exception as e:
        flash(f"Erro ao iniciar desligamento: {str(e)}", "danger")
    return redirect(url_for('dashboard'))

@app.route('/encerrar_processo/<id_funcionario>')
def encerrar_processo(id_funcionario):
    if session.get('user_role') != 'RH': return redirect(url_for('index'))
    try:
        supabase.table("funcionarios").update({"status": "Finalizado"}).eq("id", id_funcionario).execute()
        flash("Processo encerrado com sucesso! Nenhuma alteração futura será permitida.", "success")
    except Exception as e:
        flash(f"Erro ao encerrar: {str(e)}", "danger")
    return redirect(url_for('dashboard'))

# --- ROTA PARA GERAR PDF ---

@app.route('/gerar_pdf/<id_funcionario>/<tipo>')
def gerar_pdf(id_funcionario, tipo):
    if 'user_id' not in session: 
        return redirect(url_for('login_page'))
    
    try:
        # Busca dados do funcionário
        func = supabase.table("funcionarios").select("*").eq("id", id_funcionario).single().execute().data
        
        # Busca as respostas filtrando pelo tipo (admissao ou desligamento)
        res = supabase.table("checklist_respostas").select("*, checklist_modelos(descricao, tipo)").eq("funcionario_id", id_funcionario).execute().data
        
        # Filtra apenas os itens do tipo solicitado
        checklists_filtrados = [item for item in res if item.get('checklist_modelos', {}).get('tipo') == tipo]

        # Gera o PDF usando a função do arquivo externo
        pdf_buffer = criar_pdf_buffer(func, checklists_filtrados, tipo.capitalize())

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f"Checklist_{tipo}_{func['nome'].replace(' ', '_')}.pdf",
            mimetype='application/pdf'
        )
    except Exception as e:
        flash(f"Erro ao gerar PDF: {str(e)}", "danger")
        return redirect(url_for('dashboard'))

# --- ADMINISTRAÇÃO DE MODELOS ---

@app.route('/excluir_item_modelo/<id_item>')
def excluir_item_modelo(id_item):
    if session.get('user_role') != 'RH': 
        return redirect(url_for('index'))
    
    try:
        supabase.table("checklist_modelos").update({"excluido": True}).eq("id", id_item).execute()
        flash("Item removido do modelo com sucesso!", "success")
    except Exception as e:
        flash(f"Erro ao excluir item: {str(e)}", "danger")
    
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
