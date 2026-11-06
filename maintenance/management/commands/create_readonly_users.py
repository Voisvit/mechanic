import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from maintenance.access import READ_ONLY_GROUP


# Логін і посада в родовому відмінку для напису «Доступ для ...» у шапці.
READ_ONLY_ACCOUNTS = (
    ("nachalnyk", "начальника дільниці №2"),
    ("holmekh", "головного механіка"),
    ("dyrektor", "директора"),
)
PASSWORD_WORDS = ("stal", "bolt", "kran", "shkyv", "remin", "pres", "valok", "lanka", "pruzhyna", "shayba")


def generate_password():
    return f"{secrets.choice(PASSWORD_WORDS)}-{secrets.randbelow(9000) + 1000}"


class Command(BaseCommand):
    help = "Створює групу «Тільки перегляд» і облікові записи керівників. Наявних користувачів не змінює."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            action="append",
            default=[],
            metavar="ЛОГІН=ПАРОЛЬ",
            help="Заданий пароль для логіна. Без нього пароль буде згенеровано.",
        )

    def parse_passwords(self, raw_values):
        known_logins = {username for username, _ in READ_ONLY_ACCOUNTS}
        passwords = {}
        for raw_value in raw_values:
            username, separator, password = raw_value.partition("=")
            if not separator or not password:
                raise CommandError(f"Очікується формат ЛОГІН=ПАРОЛЬ: {username}")
            if username not in known_logins:
                raise CommandError(f"Невідомий логін: {username}")
            try:
                validate_password(password)
            except ValidationError as error:
                raise CommandError(f"Пароль для {username}: {' '.join(error.messages)}")
            passwords[username] = password
        return passwords

    @transaction.atomic
    def handle(self, *args, **options):
        passwords = self.parse_passwords(options["password"])
        User = get_user_model()
        group, _ = Group.objects.get_or_create(name=READ_ONLY_GROUP)

        for username, position in READ_ONLY_ACCOUNTS:
            if User.objects.filter(username=username).exists():
                self.stdout.write(f"{username}: уже існує, не змінено")
                continue

            password = passwords.get(username) or generate_password()
            user = User.objects.create_user(username=username, password=password, first_name=position)
            user.groups.add(group)
            self.stdout.write(f"{username}: створено, пароль {password}")
