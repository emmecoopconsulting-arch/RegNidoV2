from dataclasses import dataclass


@dataclass
class Bambino:
    id: str
    nome: str
    cognome: str

    @property
    def display_name(self) -> str:
        return f"{self.cognome} {self.nome}"
