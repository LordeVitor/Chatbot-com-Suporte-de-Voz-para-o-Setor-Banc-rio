# sender.py 

import requests
import json

CHATBOT_URL = "http://localhost:5001"

# --- Funções de Envio de Mensagens ---

def send_to_specific_users():
    """Busca a lista de utilizadores, permite a seleção e envia uma mensagem."""
    try:
        response = requests.get(f"{CHATBOT_URL}/get-users")
        response.raise_for_status()
        users = response.json()
        if not users:
            print("Nenhum utilizador encontrado na base de dados.")
            return
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar a lista de utilizadores: {e}")
        return

    print("\n--- Lista de Contactos ---")
    user_list = list(users.items())
    for index, (number, name) in enumerate(user_list):
        display_name = name if name else "Sem nome"
        print(f"{index + 1}: {display_name} ({number})")

    selection = input("\nDigite os números dos contactos para quem quer enviar, separados por vírgula (ex: 1,3,5): ")
    try:
        indices = [int(i.strip()) - 1 for i in selection.split(',')]
        selected_numbers = [user_list[i][0] for i in indices]
    except (ValueError, IndexError):
        print("Seleção inválida. Por favor, use o formato correto.")
        return

    if not selected_numbers:
        print("Nenhum contacto selecionado.")
        return

    message = input(f"Escreva a mensagem a ser enviada para os {len(selected_numbers)} contactos selecionados: ")
    if not message:
        print("A mensagem não pode estar vazia.")
        return

    payload = {
        "numbers": selected_numbers,
        "message": message
    }
    
    try:
        response = requests.post(f"{CHATBOT_URL}/send-to-specific", json=payload)
        response.raise_for_status()
        print("\nSucesso! Resposta do servidor:")
        print(response.json())
    except requests.exceptions.RequestException as e:
        print(f"\nErro ao enviar para os contactos selecionados: {e}")


def send_simple_broadcast():
    message = input("Escreva a mensagem que deseja enviar para todos: ")
    if not message:
        print("Mensagem não pode estar vazia.")
        return
    payload = {"message": message}
    try:
        response = requests.post(f"{CHATBOT_URL}/broadcast", json=payload)
        response.raise_for_status()
        print("\nSucesso! Resposta do servidor:")
        print(response.json())
    except requests.exceptions.RequestException as e:
        print(f"\nErro ao enviar a transmissão: {e}")

def send_personalized_broadcast():
    print("\nEscreva a sua mensagem. Use '{name}' onde quiser que o nome do utilizador apareça.")
    template = input("Template da mensagem: ")
    if not template or '{name}' not in template:
        print("O template é inválido. Deve conter o marcador '{name}'.")
        return
    payload = {"template": template}
    try:
        response = requests.post(f"{CHATBOT_URL}/personalized-broadcast", json=payload)
        response.raise_for_status()
        print("\nSucesso! Resposta do servidor:")
        print(response.json())
    except requests.exceptions.RequestException as e:
        print(f"\nErro ao enviar a transmissão personalizada: {e}")

# --- Funções de Controle da IA ---

def change_chatbot_mode():
    """Permite alterar o modo de operação do chatbot."""
    print("\n--- Alterar Modo da IA ---")
    print("1. Modo Vendas (Foco em produtos financeiros)")
    print("2. Modo Padrão (Assistente geral)")
    choice = input("Escolha o novo modo: ")

    if choice == '1':
        new_mode = 'sales'
    elif choice == '2':
        new_mode = 'standard'
    else:
        print("Opção inválida.")
        return

    try:
        payload = {"mode": new_mode}
        response = requests.post(f"{CHATBOT_URL}/mode", json=payload)
        response.raise_for_status()
        print(f"\nSucesso! Modo do chatbot alterado para '{new_mode}'.")
    except requests.exceptions.RequestException as e:
        print(f"\nErro ao alterar o modo: {e}")

def check_current_mode():
    """Verifica e exibe o modo atual do chatbot."""
    try:
        response = requests.get(f"{CHATBOT_URL}/mode")
        response.raise_for_status()
        mode_data = response.json()
        print(f"\n--- Modo Atual da IA: {mode_data.get('current_mode', 'desconhecido').upper()} ---")
    except requests.exceptions.RequestException as e:
        print(f"\nErro ao verificar o modo: {e}")


# --- Menu Principal ---

if __name__ == '__main__':
    while True:
        check_current_mode() # Mostra o modo atual sempre no início
        print("\n--- Painel de Controlo ---")
        print("1. Enviar a mesma mensagem para TODOS")
        print("2. Enviar mensagem personalizada para TODOS")
        print("3. Enviar mensagem para contactos ESPECÍFICOS")
        print("4. Alterar Modo da IA (Vendas/Padrão)")
        print("5. Sair")
        choice = input("Escolha uma opção: ")

        if choice == '1':
            send_simple_broadcast()
        elif choice == '2':
            send_personalized_broadcast()
        elif choice == '3':
            send_to_specific_users()
        elif choice == '4':
            change_chatbot_mode()
        elif choice == '5':
            break
        else:
            print("Opção inválida. Tente novamente.")


        input("\nPressione Enter para continuar...")
