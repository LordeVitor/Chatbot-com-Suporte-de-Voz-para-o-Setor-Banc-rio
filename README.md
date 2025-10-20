# Chatbot-com-Suporte-de-Voz-para-o-Setor-Bancário
Projeto de TCC realizado para o curso de Ciências da Computação

Este projeto implementa um chatbot de WhatsApp totalmente funcional, desenhado para ser robusto e modular. Ele utiliza a Evolution API como ponte para o WhatsApp e a API do Google Gemini para gerar respostas inteligentes e contextuais.

O sistema é totalmente "dockerizado" para fácil implementação e escalabilidade. Inclui uma base de dados SQLite para gestão de utilizadores e uma API de controle que permite alterar o comportamento da IA em tempo real através de um painel de controle em linha de comando.

Funcionalidades:

Integração com WhatsApp: Recebe e envia mensagens através da Evolution API.
Inteligência Artificial: Utiliza o Google Gemini para gerar respostas, compreendendo o contexto da conversa.
Personas Dinâmicas: Permite alterar a "personalidade" da IA em tempo real através de um endpoint. O projeto está pré-configurado com os modos:

standard: Assistente geral e prestável.
sales: Assistente focado em vendas de produtos financeiros.
(Pode ser expansível para outras personas).

Gestão de Utilizadores: Armazena utilizadores numa base de dados SQLite. Identifica novos utilizadores e capta os seus nomes (pushName) ou pergunta o nome se não for válido.

Painel de Controle (sender.py): Um script em Linha de comando (terminal) para administradores, permitindo:

Enviar mensagens em massa (broadcast) para todos os utilizadores.
Enviar mensagens personalizadas (usando {name}) para todos os utilizadores.
Enviar mensagens para utilizadores específicos selecionados de uma lista.
Verificar e alterar o modo/persona atual da IA.

API de Gestão: O chatbot expõe endpoints HTTP para gestão e visualização de dados.
Orquestração com Docker: Os serviços chatbot-ia e evolution-api são geridos com docker-compose, garantindo que funcionam em conjunto e que os dados persistem.

Arquitetura
O projeto é composto por dois serviços principais orquestrados pelo docker-compose.yml:

evolution-api (Serviço Externo)
A imagem atendai/evolution-api.
Atua como a ponte direta com o WhatsApp.
Recebe as mensagens do WhatsApp e encaminha-as para o webhook do chatbot-ia.
Expõe a sua própria API na porta 8080.

chatbot-ia (O Nosso Serviço)
Construído a partir do Dockerfile local.
É um servidor Flask (executado com Gunicorn) que contém toda a lógica do chatbot.
Expõe a sua API na porta 5001.
Endpoint /webhook: Ouve os eventos da evolution-api.
Endpoints de Gestão: Expõe rotas como /mode, /get-users, /broadcast, etc.
Comunica com a API do Google Gemini para gerar as respostas.
Guarda os dados num volume do Docker (chatbot_data) para persistência.

Pré-requisitos

Docker
Docker Compose
Python 3.9+ (apenas para executar o painel de controlo sender.py na sua máquina local)
Chaves de API para:
Google Gemini


Descrição dos Arquivos Principais

​docker-compose.yml: Orquestra os serviços evolution-api e chatbot-ia.

​Dockerfile: Define as instruções para construir a imagem Python/Flask do chatbot.

​.env: (Não deve ser enviado para o Git) Armazena as chaves de API e configurações.

​requirements.txt: Lista as dependências Python para o chatbot.

​chatbot.py: O cérebro do projeto. É o servidor Flask que contém:
​As definições das Personas da IA.
​A lógica do webhook para receber mensagens.
​A função get_gemini_response para comunicar com a IA.
​A função send_whatsapp_message para responder.
​Todos os endpoints da API de gestão (/mode, /get-users, /broadcast, etc.).

​database_manager.py: Um módulo de utilidade que gere toda a lógica da base de dados SQLite (criar tabelas, adicionar/atualizar utilizadores, guardar configurações).

​sender.py: O script CLI (Painel de Controle) que consome a API de gestão do chatbot.py.

​validator.py: Contém lógicas de validação, como is_valid_name, para verificar se o nome do utilizador do WhatsApp é um nome real.

​app.py / sendmedia.py: Scripts de teste para interagir diretamente com a Evolution API.


Como Executar

Configurar as Variáveis de Ambiente
Crie um arquivo chamado .env na raiz do projeto. Ele deve conter:

# Chave para autenticar na API da Evolution
AUTHENTICATION_API_KEY=

# A sua chave de API do Google Gemini
GOOGLE_API_KEY="APIKEY"

# URL interna para a Evolution API (Use com Docker)
EVOLUTION_API_URL="http://evolution-api:8080"

# Nome da instância que será criada na Evolution API
EVOLUTION_INSTANCE_NAME="nome cadastrado na Evolution API"


Construir e Iniciar os Contentores
Execute o seguinte comando na raiz do projeto:

docker-compose up -d --build


Isto irá transferir a imagem da Evolution API, construir a imagem do seu chatbot e iniciar ambos os serviços em segundo plano.

Configurar a Instância do WhatsApp
Acesse à interface da Evolution API no seu navegador: http://localhost:8080
Crie uma nova instância. O nome da instância deve ser o mesmo que definiu em EVOLUTION_INSTANCE_NAME (ex: BANK_AI).
Use a chave definida em AUTHENTICATION_API_KEY para se autenticar.
Siga as instruções para ler o QR Code com o seu celular no app do WhatsApp.
Importante: Na configuração da instância, defina o "Webhook URL" para: http://chatbot-ia:5001/webhook (use o nome do serviço Docker chatbot-ia, não localhost).
