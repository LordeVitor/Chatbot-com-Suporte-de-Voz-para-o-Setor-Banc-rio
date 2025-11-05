# validator.py

import re

def is_valid_name(name):
    """
    Verifica se um nome fornecido é provável que seja um nome real.
    """
    if not name:
        return False

    # 1. Verifica o comprimento mínimo
    if len(name.strip()) < 3:
        return False

    # 2. Verifica se contém pelo menos uma letra
    if not re.search(r'[a-zA-Z]', name):
        return False
        
    # 3. Verifica a presença de caracteres que geralmente não estão em nomes
    # (emojis, símbolos excessivos, etc.).
    emoji_pattern = re.compile(
        "["
        u"\U0001F600-\U0001F64F"  # emojis
        u"\U0001F300-\U0001F5FF"  # simbolos
        u"\U0001F680-\U0001F6FF"  
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    if emoji_pattern.search(name):
        return False

    return True