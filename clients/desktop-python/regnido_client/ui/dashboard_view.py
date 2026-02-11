from datetime import datetime, timezone

from PySide6.QtCore import QDate, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class DashboardView(QWidget):
    check_in_requested = Signal(str)
    check_out_requested = Signal(str)
    sync_requested = Signal()
    settings_requested = Signal()
    refresh_device_requested = Signal()
    logout_requested = Signal()
    refresh_users_requested = Signal()
    create_user_requested = Signal(str, str, bool, str, str, str, int)
    refresh_iscritti_requested = Signal(str, bool)
    create_iscritto_requested = Signal(str, str, str, bool)
    delete_iscritto_requested = Signal(str)
    refresh_sedi_requested = Signal()
    create_sede_requested = Signal(str)
    disable_sede_requested = Signal(str)
    refresh_history_requested = Signal(str, str, str, str)
    export_history_requested = Signal(str, str, str, str)
    history_sede_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._presence_rows: dict[str, dict] = {}
        self._presenze_tab_index = -1
        self._storico_tab_index = -1
        self._user_tab_index = -1
        self._iscritti_tab_index = -1
        self._sedi_tab_index = -1

        self.connection_label = QLabel("Stato rete: -")
        self.device_label = QLabel("Dispositivo: -")
        self.pending_label = QLabel("Pending sync: 0")

        self.presenze_table = QTableWidget()
        self.presenze_table.setColumnCount(6)
        self.presenze_table.setHorizontalHeaderLabels(["Bambino", "Ingresso", "Uscita", "Tempo totale", "Entra", "Esce"])
        self.presenze_table.verticalHeader().setVisible(False)
        self.presenze_table.setSelectionMode(QTableWidget.NoSelection)
        self.presenze_table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.sync_button = QPushButton("Sincronizza ora")
        self.settings_button = QPushButton("Impostazioni")
        self.refresh_device_button = QPushButton("Aggiorna dispositivo")
        self.logout_button = QPushButton("Logout")

        self.sync_button.clicked.connect(self.sync_requested)
        self.settings_button.clicked.connect(self.settings_requested)
        self.refresh_device_button.clicked.connect(self.refresh_device_requested)
        self.logout_button.clicked.connect(self.logout_requested)

        top = QHBoxLayout()
        top.addWidget(self.connection_label)
        top.addWidget(self.device_label)
        top.addStretch(1)
        top.addWidget(self.pending_label)

        actions = QVBoxLayout()
        actions.addWidget(self.sync_button)
        actions.addWidget(self.refresh_device_button)
        actions.addWidget(self.settings_button)
        actions.addWidget(self.logout_button)
        actions.addStretch(1)

        body = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(self.presenze_table)
        body.addLayout(left, 2)
        body.addLayout(actions, 1)

        presenze_root = QVBoxLayout()
        presenze_root.addLayout(top)
        presenze_root.addLayout(body)
        presenze_tab = QWidget()
        presenze_tab.setLayout(presenze_root)

        self.users_list_widget = QListWidget()
        self.user_username_input = QLineEdit()
        self.user_sede_combo = QComboBox()
        self.user_role_combo = QComboBox()
        self.user_role_combo.addItem("Educatore", "EDUCATORE")
        self.user_role_combo.addItem("Amministratore", "AMM_CENTRALE")
        self.user_key_name_input = QLineEdit("default")
        self.user_key_passphrase_input = QLineEdit()
        self.user_key_passphrase_input.setEchoMode(QLineEdit.Password)
        self.user_key_days_input = QSpinBox()
        self.user_key_days_input.setMinimum(1)
        self.user_key_days_input.setMaximum(3650)
        self.user_key_days_input.setValue(180)
        self.user_active_checkbox = QCheckBox("Attivo")
        self.user_active_checkbox.setChecked(True)
        self.create_user_button = QPushButton("Crea utente")
        self.refresh_users_button = QPushButton("Aggiorna elenco")
        self.users_status = QTextEdit()
        self.users_status.setReadOnly(True)
        self.users_status.setMaximumHeight(160)

        self.refresh_users_button.clicked.connect(self.refresh_users_requested)
        self.create_user_button.clicked.connect(self._emit_create_user)

        user_form = QFormLayout()
        user_form.addRow("Username", self.user_username_input)
        user_form.addRow("Sede", self.user_sede_combo)
        user_form.addRow("Ruolo", self.user_role_combo)
        user_form.addRow("Nome chiave", self.user_key_name_input)
        user_form.addRow("Passphrase chiave", self.user_key_passphrase_input)
        user_form.addRow("Scadenza chiave (giorni)", self.user_key_days_input)
        user_form.addRow("Stato", self.user_active_checkbox)

        user_actions = QHBoxLayout()
        user_actions.addWidget(self.refresh_users_button)
        user_actions.addStretch(1)
        user_actions.addWidget(self.create_user_button)

        user_form_group = QGroupBox("Nuovo utente")
        user_form_group_layout = QVBoxLayout()
        user_form_group_layout.addLayout(user_form)
        user_form_group_layout.addLayout(user_actions)
        user_form_group.setLayout(user_form_group_layout)

        users_root = QVBoxLayout()
        users_top = QHBoxLayout()
        users_top.addWidget(QLabel("Utenti registrati"))
        users_top.addStretch(1)
        users_home_button = QPushButton("Home Presenze")
        users_home_button.clicked.connect(lambda: self.go_to_section("presenze"))
        users_top.addWidget(users_home_button)
        users_root.addLayout(users_top)
        users_root.addWidget(self.users_list_widget)
        users_root.addWidget(user_form_group)
        users_root.addWidget(self.users_status)
        users_tab = QWidget()
        users_tab.setLayout(users_root)

        self.iscritti_list_widget = QListWidget()
        self.iscritti_sede_filter_combo = QComboBox()
        self.iscritti_include_inactive_checkbox = QCheckBox("Mostra disattivi")
        self.refresh_iscritti_button = QPushButton("Aggiorna iscritti")
        self.iscritto_sede_combo = QComboBox()
        self.iscritto_nome_input = QLineEdit()
        self.iscritto_cognome_input = QLineEdit()
        self.iscritto_attivo_checkbox = QCheckBox("Attivo")
        self.iscritto_attivo_checkbox.setChecked(True)
        self.create_iscritto_button = QPushButton("Aggiungi iscritto")
        self.delete_iscritto_button = QPushButton("Elimina selezionato")
        self.iscritti_status = QTextEdit()
        self.iscritti_status.setReadOnly(True)
        self.iscritti_status.setMaximumHeight(160)

        self.refresh_iscritti_button.clicked.connect(self._emit_refresh_iscritti)
        self.create_iscritto_button.clicked.connect(self._emit_create_iscritto)
        self.delete_iscritto_button.clicked.connect(self._emit_delete_iscritto)

        iscritti_filter_row = QHBoxLayout()
        iscritti_filter_row.addWidget(QLabel("Sede"))
        iscritti_filter_row.addWidget(self.iscritti_sede_filter_combo)
        iscritti_filter_row.addWidget(self.iscritti_include_inactive_checkbox)
        iscritti_filter_row.addStretch(1)
        iscritti_filter_row.addWidget(self.refresh_iscritti_button)

        iscritto_form = QFormLayout()
        iscritto_form.addRow("Sede", self.iscritto_sede_combo)
        iscritto_form.addRow("Nome", self.iscritto_nome_input)
        iscritto_form.addRow("Cognome", self.iscritto_cognome_input)
        iscritto_form.addRow("Stato", self.iscritto_attivo_checkbox)

        iscritti_actions = QHBoxLayout()
        iscritti_actions.addWidget(self.create_iscritto_button)
        iscritti_actions.addWidget(self.delete_iscritto_button)
        iscritti_actions.addStretch(1)

        iscritti_form_group = QGroupBox("Nuovo iscritto")
        iscritti_form_group_layout = QVBoxLayout()
        iscritti_form_group_layout.addLayout(iscritto_form)
        iscritti_form_group_layout.addLayout(iscritti_actions)
        iscritti_form_group.setLayout(iscritti_form_group_layout)

        iscritti_root = QVBoxLayout()
        iscritti_top = QHBoxLayout()
        iscritti_top.addWidget(QLabel("Gestione iscritti"))
        iscritti_top.addStretch(1)
        iscritti_home_button = QPushButton("Home Presenze")
        iscritti_home_button.clicked.connect(lambda: self.go_to_section("presenze"))
        iscritti_top.addWidget(iscritti_home_button)
        iscritti_root.addLayout(iscritti_top)
        iscritti_root.addLayout(iscritti_filter_row)
        iscritti_root.addWidget(self.iscritti_list_widget)
        iscritti_root.addWidget(iscritti_form_group)
        iscritti_root.addWidget(self.iscritti_status)
        iscritti_tab = QWidget()
        iscritti_tab.setLayout(iscritti_root)

        self.sedi_list_widget = QListWidget()
        self.sedi_nome_input = QLineEdit()
        self.refresh_sedi_button = QPushButton("Aggiorna sedi")
        self.create_sede_button = QPushButton("Crea sede")
        self.disable_sede_button = QPushButton("Disattiva selezionata")
        self.sedi_status = QTextEdit()
        self.sedi_status.setReadOnly(True)
        self.sedi_status.setMaximumHeight(160)

        self.refresh_sedi_button.clicked.connect(self.refresh_sedi_requested)
        self.create_sede_button.clicked.connect(lambda: self.create_sede_requested.emit(self.sedi_nome_input.text().strip()))
        self.disable_sede_button.clicked.connect(self._emit_disable_sede)

        sedi_actions = QHBoxLayout()
        sedi_actions.addWidget(self.refresh_sedi_button)
        sedi_actions.addStretch(1)
        sedi_actions.addWidget(self.create_sede_button)
        sedi_actions.addWidget(self.disable_sede_button)

        sedi_form = QFormLayout()
        sedi_form.addRow("Nome sede", self.sedi_nome_input)

        sedi_root = QVBoxLayout()
        sedi_top = QHBoxLayout()
        sedi_top.addWidget(QLabel("Gestione sedi"))
        sedi_top.addStretch(1)
        sedi_home_button = QPushButton("Home Presenze")
        sedi_home_button.clicked.connect(lambda: self.go_to_section("presenze"))
        sedi_top.addWidget(sedi_home_button)
        sedi_root.addLayout(sedi_top)
        sedi_root.addLayout(sedi_form)
        sedi_root.addLayout(sedi_actions)
        sedi_root.addWidget(self.sedi_list_widget)
        sedi_root.addWidget(self.sedi_status)
        sedi_tab = QWidget()
        sedi_tab.setLayout(sedi_root)

        self.history_unit_combo = QComboBox()
        self.history_unit_combo.addItem("Giorno", "giorno")
        self.history_unit_combo.addItem("Mese", "mese")
        self.history_day_input = QDateEdit()
        self.history_day_input.setCalendarPopup(True)
        self.history_day_input.setDate(QDate.currentDate())
        self.history_month_input = QDateEdit()
        self.history_month_input.setCalendarPopup(True)
        self.history_month_input.setDisplayFormat("yyyy-MM")
        self.history_month_input.setDate(QDate.currentDate())
        self.history_sede_combo = QComboBox()
        self.history_iscritto_combo = QComboBox()
        self.refresh_history_button = QPushButton("Aggiorna storico")
        self.export_history_button = QPushButton("Esporta PDF")
        self.history_status = QTextEdit()
        self.history_status.setReadOnly(True)
        self.history_status.setMaximumHeight(140)
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(["Iscritto", "Sede", "Ingresso", "Uscita", "Tempo totale"])
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setSelectionMode(QTableWidget.NoSelection)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.history_unit_combo.currentIndexChanged.connect(self._toggle_history_period_inputs)
        self.history_sede_combo.currentIndexChanged.connect(self._emit_history_sede_changed)
        self.refresh_history_button.clicked.connect(self._emit_refresh_history)
        self.export_history_button.clicked.connect(self._emit_export_history)

        history_filters = QHBoxLayout()
        history_filters.addWidget(QLabel("Unità"))
        history_filters.addWidget(self.history_unit_combo)
        history_filters.addWidget(QLabel("Giorno"))
        history_filters.addWidget(self.history_day_input)
        history_filters.addWidget(QLabel("Mese"))
        history_filters.addWidget(self.history_month_input)
        history_filters.addWidget(QLabel("Sede"))
        history_filters.addWidget(self.history_sede_combo)
        history_filters.addWidget(QLabel("Iscritto"))
        history_filters.addWidget(self.history_iscritto_combo)
        history_filters.addStretch(1)
        history_filters.addWidget(self.refresh_history_button)
        history_filters.addWidget(self.export_history_button)

        history_root = QVBoxLayout()
        history_top = QHBoxLayout()
        history_top.addWidget(QLabel("Storico presenze"))
        history_top.addStretch(1)
        history_home_button = QPushButton("Home Presenze")
        history_home_button.clicked.connect(lambda: self.go_to_section("presenze"))
        history_top.addWidget(history_home_button)
        history_root.addLayout(history_top)
        history_root.addLayout(history_filters)
        history_root.addWidget(self.history_table)
        history_root.addWidget(self.history_status)
        history_tab = QWidget()
        history_tab.setLayout(history_root)

        self.tabs = QTabWidget()
        self._presenze_tab_index = self.tabs.addTab(presenze_tab, "Presenze")
        self._storico_tab_index = self.tabs.addTab(history_tab, "Storico")
        self._user_tab_index = self.tabs.addTab(users_tab, "Gestione utenti")
        self._iscritti_tab_index = self.tabs.addTab(iscritti_tab, "Iscritti")
        self._sedi_tab_index = self.tabs.addTab(sedi_tab, "Sedi")
        self.tabs.setTabVisible(self._user_tab_index, False)
        self.tabs.setTabVisible(self._iscritti_tab_index, False)
        self.tabs.setTabVisible(self._sedi_tab_index, False)
        self.tabs.tabBar().hide()

        root = QVBoxLayout()
        root.addWidget(self.tabs)
        self.setLayout(root)

        self._presence_timer = QTimer(self)
        self._presence_timer.setInterval(1000)
        self._presence_timer.timeout.connect(self._update_presence_timers)
        self._presence_timer.start()
        self._toggle_history_period_inputs()

    def set_presence_rows(self, rows: list[dict]) -> None:
        self._presence_rows = {}
        self.presenze_table.setRowCount(len(rows))
        for idx, row in enumerate(rows):
            bambino_id = str(row.get("id", ""))
            nome = str(row.get("nome", ""))
            cognome = str(row.get("cognome", ""))
            dentro = bool(row.get("dentro"))
            start_raw = row.get("entrata_aperta_da")
            start_dt = None
            if isinstance(start_raw, str) and start_raw:
                try:
                    start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
                except ValueError:
                    start_dt = None
            ingresso_dt = self._parse_iso_dt(row.get("ultimo_ingresso"))
            uscita_dt = self._parse_iso_dt(row.get("ultima_uscita"))
            closed_seconds = max(0, int(row.get("tempo_totale_secondi", 0) or 0))

            display_name = f"{cognome} {nome}".strip()
            self.presenze_table.setItem(idx, 0, QTableWidgetItem(display_name))
            self.presenze_table.setItem(idx, 1, QTableWidgetItem(self._format_datetime(ingresso_dt)))
            self.presenze_table.setItem(idx, 2, QTableWidgetItem(self._format_datetime(uscita_dt)))

            total_label = QLabel(self._format_duration(closed_seconds))
            self.presenze_table.setCellWidget(idx, 3, total_label)

            enter_button = QPushButton("Entra")
            exit_button = QPushButton("Esce")
            enter_button.clicked.connect(lambda _=False, b_id=bambino_id: self.check_in_requested.emit(b_id))
            exit_button.clicked.connect(lambda _=False, b_id=bambino_id: self.check_out_requested.emit(b_id))
            self.presenze_table.setCellWidget(idx, 4, enter_button)
            self.presenze_table.setCellWidget(idx, 5, exit_button)

            self._presence_rows[bambino_id] = {
                "row": idx,
                "display_name": display_name.lower(),
                "dentro": dentro,
                "start_dt": start_dt,
                "closed_seconds": closed_seconds,
                "total_label": total_label,
                "enter_button": enter_button,
                "exit_button": exit_button,
            }

        self._update_presence_timers()
        self._show_all_presence_rows()

    def _update_presence_timers(self) -> None:
        now = datetime.now(timezone.utc)
        for data in self._presence_rows.values():
            dentro = bool(data["dentro"])
            start_dt = data["start_dt"]
            closed_seconds = int(data["closed_seconds"])
            total_label: QLabel = data["total_label"]
            enter_button: QPushButton = data["enter_button"]
            exit_button: QPushButton = data["exit_button"]

            if dentro and isinstance(start_dt, datetime):
                elapsed_live = max(0, int((now - start_dt).total_seconds()))
                total_label.setText(self._format_duration(closed_seconds + elapsed_live))
            else:
                total_label.setText(self._format_duration(closed_seconds))

            enter_button.setEnabled(not dentro)
            exit_button.setEnabled(dentro)

    def _show_all_presence_rows(self) -> None:
        for data in self._presence_rows.values():
            row_idx = int(data["row"])
            self.presenze_table.setRowHidden(row_idx, False)

    def _parse_iso_dt(self, value: object) -> datetime | None:
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    def _format_datetime(self, value: datetime | None) -> str:
        if not isinstance(value, datetime):
            return "-"
        return value.astimezone().strftime("%d/%m/%Y %H:%M")

    def _format_duration(self, seconds: int) -> str:
        total = max(0, int(seconds))
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _toggle_history_period_inputs(self) -> None:
        is_day = str(self.history_unit_combo.currentData()) == "giorno"
        self.history_day_input.setEnabled(is_day)
        self.history_month_input.setEnabled(not is_day)

    def set_history_sedi(self, sedi: list[tuple[str, str]]) -> None:
        self.history_sede_combo.clear()
        self.history_sede_combo.addItem("Tutte le sedi", "")
        for sede_id, sede_nome in sedi:
            self.history_sede_combo.addItem(f"{sede_nome} ({sede_id[:8]})", sede_id)

    def set_history_iscritti(self, iscritti: list[dict[str, str]]) -> None:
        self.history_iscritto_combo.clear()
        self.history_iscritto_combo.addItem("Tutti gli iscritti", "")
        for row in iscritti:
            bambino_id = str(row.get("id", ""))
            label = f"{row.get('cognome', '-')} {row.get('nome', '-')}"
            self.history_iscritto_combo.addItem(label, bambino_id)

    def set_history_rows(self, rows: list[dict[str, object]]) -> None:
        self.history_table.setRowCount(len(rows))
        for idx, row in enumerate(rows):
            label_iscritto = f"{row.get('cognome', '-')} {row.get('nome', '-')}".strip()
            ingresso = self._format_datetime(self._parse_iso_dt(row.get("ingresso")))
            uscita = self._format_datetime(self._parse_iso_dt(row.get("uscita")))
            totale = self._format_duration(int(row.get("tempo_totale_secondi", 0) or 0))

            self.history_table.setItem(idx, 0, QTableWidgetItem(label_iscritto))
            self.history_table.setItem(idx, 1, QTableWidgetItem(str(row.get("sede_nome", "-"))))
            self.history_table.setItem(idx, 2, QTableWidgetItem(ingresso))
            self.history_table.setItem(idx, 3, QTableWidgetItem(uscita))
            self.history_table.setItem(idx, 4, QTableWidgetItem(totale))

    def append_history_status(self, message: str) -> None:
        self.history_status.append(message)

    def history_filters(self) -> tuple[str, str, str, str]:
        unita = str(self.history_unit_combo.currentData())
        if unita == "giorno":
            periodo = self.history_day_input.date().toString("yyyy-MM-dd")
        else:
            periodo = self.history_month_input.date().toString("yyyy-MM")
        sede_id = str(self.history_sede_combo.currentData() or "")
        bambino_id = str(self.history_iscritto_combo.currentData() or "")
        return unita, periodo, sede_id, bambino_id

    def _emit_refresh_history(self) -> None:
        self.refresh_history_requested.emit(*self.history_filters())

    def _emit_export_history(self) -> None:
        self.export_history_requested.emit(*self.history_filters())

    def _emit_history_sede_changed(self) -> None:
        self.history_sede_changed.emit(str(self.history_sede_combo.currentData() or ""))

    def set_connection_status(self, message: str, ok: bool) -> None:
        color = "#1e6a2f" if ok else "#b00020"
        self.connection_label.setStyleSheet(f"color: {color};")
        self.connection_label.setText(f"Stato rete: {message}")

    def set_device_label(self, label: str) -> None:
        self.device_label.setText(f"Dispositivo: {label}")

    def set_pending_count(self, count: int) -> None:
        self.pending_label.setText(f"Pending sync: {count}")

    def set_admin_tabs_visible(self, visible: bool) -> None:
        if self._user_tab_index < 0:
            return
        self.tabs.setTabVisible(self._user_tab_index, visible)
        if self._iscritti_tab_index >= 0:
            self.tabs.setTabVisible(self._iscritti_tab_index, visible)
        if self._sedi_tab_index >= 0:
            self.tabs.setTabVisible(self._sedi_tab_index, visible)
        if not visible and self.tabs.currentIndex() == self._user_tab_index:
            self.tabs.setCurrentIndex(self._presenze_tab_index)
        if not visible and self.tabs.currentIndex() == self._iscritti_tab_index:
            self.tabs.setCurrentIndex(self._presenze_tab_index)
        if not visible and self.tabs.currentIndex() == self._sedi_tab_index:
            self.tabs.setCurrentIndex(self._presenze_tab_index)

    def go_to_section(self, section: str) -> None:
        section_norm = section.strip().lower()
        if section_norm == "presenze":
            self.tabs.setCurrentIndex(self._presenze_tab_index)
            return
        if section_norm == "storico":
            self.tabs.setCurrentIndex(self._storico_tab_index)
            return
        if section_norm == "utenti" and self.tabs.isTabVisible(self._user_tab_index):
            self.tabs.setCurrentIndex(self._user_tab_index)
            return
        if section_norm == "iscritti" and self.tabs.isTabVisible(self._iscritti_tab_index):
            self.tabs.setCurrentIndex(self._iscritti_tab_index)
            return
        if section_norm == "sedi" and self.tabs.isTabVisible(self._sedi_tab_index):
            self.tabs.setCurrentIndex(self._sedi_tab_index)
            return
        self.tabs.setCurrentIndex(self._presenze_tab_index)

    def set_users(self, users: list[dict[str, str]]) -> None:
        self.users_list_widget.clear()
        for user in users:
            groups = ", ".join(user.get("groups", []))
            stato = "attivo" if user.get("attivo") else "disattivo"
            role = user.get("role", "-")
            sede_id = str(user.get("sede_id") or "")
            sede_label = sede_id[:8] if sede_id else "nessuna sede"
            label = f"{user.get('username', '-')}: {role} | {groups} | {sede_label} | {stato}"
            item = QListWidgetItem(label)
            item.setData(1, user.get("id", ""))
            self.users_list_widget.addItem(item)

    def append_users_status(self, message: str) -> None:
        self.users_status.append(message)

    def clear_user_form(self) -> None:
        self.user_username_input.clear()
        self.user_key_passphrase_input.clear()
        self.user_role_combo.setCurrentIndex(0)
        self.user_key_name_input.setText("default")
        self.user_key_days_input.setValue(180)
        self.user_active_checkbox.setChecked(True)

    def _emit_create_user(self) -> None:
        sede_id = str(self.user_sede_combo.currentData() or "")
        self.create_user_requested.emit(
            self.user_username_input.text().strip(),
            str(self.user_role_combo.currentData()),
            self.user_active_checkbox.isChecked(),
            sede_id or "",
            self.user_key_name_input.text().strip(),
            self.user_key_passphrase_input.text(),
            int(self.user_key_days_input.value()),
        )

    def set_sedi_for_users(self, sedi: list[tuple[str, str]]) -> None:
        self.user_sede_combo.clear()
        self.user_sede_combo.addItem("Nessuna sede (admin centrale)", "")
        for sede_id, sede_nome in sedi:
            self.user_sede_combo.addItem(f"{sede_nome} ({sede_id[:8]})", sede_id)

    def set_sedi_for_iscritti(self, sedi: list[tuple[str, str]]) -> None:
        self.iscritti_sede_filter_combo.clear()
        self.iscritti_sede_filter_combo.addItem("Tutte le sedi", "")
        self.iscritto_sede_combo.clear()
        for sede_id, sede_nome in sedi:
            label = f"{sede_nome} ({sede_id[:8]})"
            self.iscritti_sede_filter_combo.addItem(label, sede_id)
            self.iscritto_sede_combo.addItem(label, sede_id)

    def set_iscritti(self, iscritti: list[dict[str, str]], sedi_map: dict[str, str]) -> None:
        self.iscritti_list_widget.clear()
        for iscritto in iscritti:
            sede_id = str(iscritto.get("sede_id", ""))
            sede_nome = sedi_map.get(sede_id, sede_id[:8])
            stato = "attivo" if iscritto.get("attivo") else "disattivo"
            label = f"{iscritto.get('cognome', '-')} {iscritto.get('nome', '-')} | {sede_nome} | {stato}"
            item = QListWidgetItem(label)
            item.setData(1, iscritto.get("id", ""))
            self.iscritti_list_widget.addItem(item)

    def append_iscritti_status(self, message: str) -> None:
        self.iscritti_status.append(message)

    def clear_iscritto_form(self) -> None:
        self.iscritto_nome_input.clear()
        self.iscritto_cognome_input.clear()
        self.iscritto_attivo_checkbox.setChecked(True)

    def _emit_refresh_iscritti(self) -> None:
        sede_id = str(self.iscritti_sede_filter_combo.currentData() or "")
        self.refresh_iscritti_requested.emit(sede_id, self.iscritti_include_inactive_checkbox.isChecked())

    def _emit_create_iscritto(self) -> None:
        sede_id = str(self.iscritto_sede_combo.currentData() or "")
        self.create_iscritto_requested.emit(
            sede_id,
            self.iscritto_nome_input.text().strip(),
            self.iscritto_cognome_input.text().strip(),
            self.iscritto_attivo_checkbox.isChecked(),
        )

    def _emit_delete_iscritto(self) -> None:
        item = self.iscritti_list_widget.currentItem()
        if not item:
            self.delete_iscritto_requested.emit("")
            return
        self.delete_iscritto_requested.emit(str(item.data(1)))

    def set_sedi_admin(self, sedi_rows: list[dict[str, object]]) -> None:
        self.sedi_list_widget.clear()
        for row in sedi_rows:
            sede_id = str(row.get("id", ""))
            nome = str(row.get("nome", "-"))
            stato = "attiva" if bool(row.get("attiva")) else "disattivata"
            item = QListWidgetItem(f"{nome} | {stato}")
            item.setData(1, sede_id)
            self.sedi_list_widget.addItem(item)

    def append_sedi_status(self, message: str) -> None:
        self.sedi_status.append(message)

    def clear_sede_form(self) -> None:
        self.sedi_nome_input.clear()

    def _emit_disable_sede(self) -> None:
        item = self.sedi_list_widget.currentItem()
        if not item:
            self.disable_sede_requested.emit("")
            return
        self.disable_sede_requested.emit(str(item.data(1)))
