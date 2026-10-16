from backoffice.services.auditoria import definir_usuario, limpar_usuario


class UsuarioAuditoriaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            definir_usuario(request.user.get_username())
        try:
            return self.get_response(request)
        finally:
            limpar_usuario()
