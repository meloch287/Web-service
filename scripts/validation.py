def validate_user(user: dict) -> bool:
    """Проверка целостности данных пользователя."""
    required_fields = ["ClientId", "PAM", "FullName", "Account", "Address", "PayerBIC"]
    return all(field in user for field in required_fields)

def validate_transaction(data_payload: dict) -> bool:
    """Проверка целостности данных транзакции."""
    required_fields = ["TrnId", "TrnType", "PayerData", "BeneficiaryData", "Amount", "Currency"]
    return all(field in data_payload for field in required_fields)