from rest_framework import viewsets


from ACI_backend.ACIApp.models import Repository
from ACI_backend.api.serializers import RepositorySerializer


class RepositoryViewSet(viewsets.ModelViewSet):
    queryset = Repository.objects.all()
    serializer_class = RepositorySerializer