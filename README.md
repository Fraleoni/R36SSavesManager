# R36S Saves Manager

Interfaccia web locale, in inglese con traduzione italiana, per importare salvataggi SRAM di RetroArch
sulla R36S. Python >= 3.9, senza pacchetti esterni, CDN o accesso a Internet.
Python 3.13.5 e i percorsi sotto sono stati verificati via SSH sulla console.

## Lingue

La lingua predefinita e **English**. Il selettore nell'intestazione permette di
passare a **Italiano** senza ricaricare la pagina, perdere il file selezionato,
l'anteprima o le conferme. La scelta viene ricordata in questo browser tramite
`localStorage`; se lo storage non e disponibile, resta valida per la pagina corrente.
Nomi di ROM, file, sistemi configurati e percorsi non vengono tradotti.

I cataloghi [locales/en.json](locales/en.json) e [locales/it.json](locales/it.json)
contengono le stringhe dell'interfaccia, gli errori API e i messaggi Python e del menu
Advanced. Mantenere le stesse chiavi e i parametri tra parentesi graffe, ad esempio
`{size}`. Le chiavi mancanti in italiano usano il testo inglese. Non inserire HTML
nelle traduzioni. Le modifiche ai cataloghi richiedono il riavvio del server.
Entrambi i file devono essere distribuiti nella sottocartella `locales`.

L'API accetta `X-Language: en` oppure `X-Language: it`; valori assenti o non
supportati usano l'inglese. Gli errori includono `error` (testo), `error_key`
(chiave stabile) e `parameters`, cosi la pagina puo ritradurli anche dopo la risposta.

Per i messaggi Python usare `--language it`, anche insieme a `--set-password`.
Per il launcher impostare `R36S_LANGUAGE=it` nell'ambiente che lo avvia, ad esempio:

```bash
R36S_LANGUAGE=it bash '/opt/system/Advanced/Saves Manager.sh' --status
```

La lingua del browser e indipendente da quella del terminale e del menu console.
Gli strumenti di installazione e rilascio mostrano messaggi in inglese; i messaggi
nativi di browser, sistema operativo, argparse, SSH e systemd dipendono dai rispettivi strumenti.

## Configurazione iniziale

Il file [config.json](config.json) abilita **Super Nintendo** e **PlayStation**.
Per Super Nintendo:

- ROM: `/roms2/snes/`
- Salvataggi: `/home/ark/.config/retroarch/saves/snes/`
- Formato in ingresso e in uscita: `.srm`
- Porta predefinita: `8765`, modificabile con `--port`.

Per PlayStation: ROM in `/roms2/psx/`, salvataggi per gioco in
`/home/ark/.config/retroarch/saves/psx/`, destinazione `<nome ROM>.srm`.
Sono accettati `.srm` e immagini raw `.mcd` / `.mcr`. Per questi ultimi due
formati vengono verificati dimensione esatta di 131072 byte (128 KiB), firma
`MC` e checksum XOR dell'intestazione (primo frame da 128 byte).
I byte vengono conservati, senza conversione o rimozione di header.
Questi controlli non garantiscono l'integrita dei singoli salvataggi interni
o la compatibilita con regione e revisione del gioco.

L'importazione PSX sostituisce **l'intera memory card del gioco**, non un singolo
slot. La precedente viene conservata nel backup quando si conferma la sostituzione.
La seconda scheda condivisa `pcsx-card2.mcd` non e una destinazione del gestore.
Selezionare PlayStation prima di scegliere o trascinare `.mcd` / `.mcr`.

Le impostazioni osservate sia in RetroArch sia in RetroArch32 sono:
`sort_savefiles_by_content_enable = "true"`, `sort_savefiles_enable = "false"`,
`savefiles_in_content_dir = "false"`.
Il programma applica questa regola, non rilegge automaticamente gli override.
Per una ROM in una sottocartella viene usato il nome della **cartella immediatamente
contenente la ROM**, non tutto il percorso relativo. Ad esempio:

```text
/roms2/snes/Collection/Game.zip
-> /home/ark/.config/retroarch/saves/Collection/Game.srm
```

I percorsi assoluti o relativi sono configurabili; quelli relativi partono dalla
cartella del file JSON. `~` si riferisce all'utente che avvia il programma:
sulla console avviarlo come **ark**, non con sudo.

## Prova sul PC

```powershell
.\.venv\Scripts\python.exe R36SavesManager.py --demo
```

Aprire <http://127.0.0.1:8765>. La demo ascolta esclusivamente su loopback e
non richiede password. Crea tre ROM segnaposto e un salvataggio sintetico da
8 KiB e due savestate sintetici (automatico e manuale) in una cartella temporanea,
senza leggere `/roms2` o i salvataggi veri.
I dati temporanei vengono eliminati all'arresto normale con Ctrl+C.
Non contiene ROM giocabili o salvataggi del gioco originale.

## Installazione con menu Advanced

### Rilascio da Windows

Eseguire [packaging/deploy.ps1](packaging/deploy.ps1) da PowerShell:

```powershell
.\packaging\deploy.ps1
```

Lo script chiede IP IPv4, utente SSH (default `ark`), se pubblicare la
configurazione e se avviare il servizio al termine. Prima di collegarsi chiede
conferma: il rilascio arresta il servizio web e invalida le sessioni aperte.
Terminare eventuali importazioni prima di procedere.

La password di accesso viene richiesta direttamente da OpenSSH, con input
nascosto, e non viene salvata ne passata sulla riga di comando. Verifica,
trasferimento e installazione usano **una sola connessione SSH**, quindi basta
inserirla una volta. Se la password e errata, lo script termina e va rilanciato;
se sono gia configurate chiavi SSH, vengono usate normalmente. Al primo
collegamento verificare la fingerprint della console prima di accettarla.
La password web dell'applicazione e separata e non viene modificata.

Richiede Windows PowerShell 5.1 o PowerShell 7, client OpenSSH e `tar.exe`
nativi di Windows. Sulla console serve `sudo -n` senza prompt, come nella
configurazione dArkOSen verificata. L'utente richiesto serve per autenticarsi:
il layout di installazione e l'utente del servizio restano `/home/ark` e `ark`.

Opzioni esplicite, mantenendo comunque la conferma prima del rilascio:

```powershell
.\packaging\deploy.ps1 -ConsoleIp 192.168.1.43 -SshUser ark -PublishConfig -StartService
```

`-PublishConfig` pubblica l'intero [config.json](config.json) locale, inclusi
i nuovi profili. Prima di sostituire la configurazione remota ne crea un backup
privato `config.json.before-<id-rilascio>.bak`. Senza questa opzione, o rispondendo
No al prompt, la configurazione esistente e conservata. Non viene eseguita una
fusione dei profili: verificare prima eventuali personalizzazioni remote.
Senza avvio finale il servizio resta fermo; non viene mai abilitato al boot.

Per verificare il pacchetto e visualizzare i comandi senza collegarsi:

```powershell
.\packaging\deploy.ps1 -ConsoleIp 192.168.1.43 -SshUser ark -DryRun
```

Il trasferimento include soltanto i file runtime/installer necessari e i cataloghi,
inviati in Base64 sullo standard input di SSH, con verifica SHA256 sulla console
prima dell'estrazione. La codifica evita alterazioni dei byte anche in Windows
PowerShell 5.1; non sostituisce la cifratura fornita da SSH.
Non include password, ROM, salvataggi o
virtualenv. I file temporanei locali vengono rimossi anche in caso di errore;
se il trasferimento viene interrotto prima dell'installazione, il percorso
temporaneo remoto eventualmente rimasto viene segnalato. Un errore interrompe
il rilascio, senza dichiarare successo; non e previsto rollback automatico.

### Installazione manuale

Il pacchetto [packaging/install.sh](packaging/install.sh) installa una unit di
sistema che esegue Python come `ark`, indipendente dalla sessione SSH e dal menu.
Non avvia il server e non abilita l'avvio al boot. Richiede il layout dArkOSen
verificato in [CONSOLE_NOTES.md](CONSOLE_NOTES.md), `systemd`, `dialog` e
`/opt/inttools/gptokeyb`.

Trasferire sulla console i file runtime e i cataloghi elencati nella sezione seguente
e la directory `packaging`, mantenendo la struttura. Dalla directory trasferita:

```bash
sudo -n bash packaging/install.sh
```

Destinazioni:

```text
/home/ark/.local/share/r36s-saves-manager/   codice e asset
/home/ark/.config/r36s-saves-manager/       config.json e password
/etc/systemd/system/r36s-saves-manager.service
/opt/system/Advanced/Saves Manager.sh
```

Impostare la password web da un terminale SSH interattivo **come ark**, non con
sudo. Inserirla soltanto nei prompt nascosti, mai nella riga di comando o in chat:

```bash
python3 /home/ark/.local/share/r36s-saves-manager/R36SavesManager.py \
  --set-password --password-file /home/ark/.config/r36s-saves-manager/password
```

La password deve avere almeno 8 caratteri ed essere diversa da quella SSH.
Il file viene scritto atomicamente con permessi `0600` nella directory privata
`0700`; contiene la password in chiaro ed e leggibile da `ark` e root.
Ripetere il comando per cambiarla, poi arrestare e riavviare il servizio.

Riaprire **Advanced > Saves Manager**: **Start**, **Status**, **Stop**.
Start attende la notifica READY di systemd e verifica HTTP prima di mostrare
l'indirizzo. Uscire dal menu lascia il server attivo. La comparsa della voce,
la resa sul display e i pulsanti vanno verificati sulla console; non riavviare
automaticamente il frontend per forzare un aggiornamento del menu.

Gli stessi controlli sono disponibili via SSH senza avviare il mapper gamepad:

```bash
bash '/opt/system/Advanced/Saves Manager.sh' --start
bash '/opt/system/Advanced/Saves Manager.sh' --status
bash '/opt/system/Advanced/Saves Manager.sh' --stop
journalctl -u r36s-saves-manager.service -n 30 --no-pager
```

Aprire l'indirizzo mostrato, normalmente <http://192.168.1.43:8765>.
La porta e `8765`; se e occupata, l'avvio fallisce. Non viene terminato il processo
che la occupa. La unit non contiene una sezione Install e non va abilitata al boot.
L'arresto attende le richieste in corso, con un limite systemd di 90 secondi:
oltre tale limite il processo viene terminato forzatamente.

Per aggiornare, trasferire il pacchetto nuovo e rieseguire l'installer: il servizio
viene arrestato, codice e launcher sostituiti, configurazione e password conservate.
Riavviarlo esplicitamente. Il servizio ha accesso in scrittura solo alla directory
salvataggi predefinita e al proprio spazio temporaneo: per cambiare `save_root`
occorre adeguare anche `ReadWritePaths` nella unit, oltre alla configurazione JSON.
Lo stesso vale per `state_root`: la unit consente anche la scrittura in
`/home/ark/.config/retroarch/states`, se presente all'avvio del servizio.

Per disinstallare, senza eliminare salvataggi, backup, configurazione o password:

```bash
sudo -n systemctl stop r36s-saves-manager.service
sudo -n rm /etc/systemd/system/r36s-saves-manager.service '/opt/system/Advanced/Saves Manager.sh'
sudo -n systemctl daemon-reload
rm -r /home/ark/.local/share/r36s-saves-manager
```

La directory privata con configurazione e credenziale resta disponibile per
una reinstallazione. Gli aggiornamenti del firmware potrebbero rimuovere il launcher.

## Avvio manuale alternativo

Copiare sulla console questi file, mantenendo la sottocartella `locales`:

- [R36SavesManager.py](R36SavesManager.py)
- [config.json](config.json)
- [index.html](index.html)
- [app.js](app.js)
- [console.png](console.png)
- [locales/en.json](locales/en.json)
- [locales/it.json](locales/it.json)

Avviare dalla console o via SSH come utente `ark`:

```bash
python3 R36SavesManager.py --host 0.0.0.0 --port 8765
```

Impostare al prompt una password di almeno 8 caratteri, distinta da quella SSH.
La password non viene salvata su disco. In alternativa il processo puo riceverla
tramite la variabile d'ambiente `R36S_PASSWORD`; non inserirla nel codice o in Git.

Dal PC o telefono sulla stessa rete aprire <http://192.168.1.43:8765> e accedere.
L'indirizzo IP puo cambiare se assegnato tramite DHCP. Il server resta in primo
piano: chiudere la sessione SSH puo arrestarlo. Questa modalita non installa servizi.
Se la porta e occupata, scegliere un'altra porta con `--port`.

**Solo reti fidate:** HTTP non cifra password o salvataggi. Non esporre il servizio
su Internet e non configurare port forwarding. Il server standard Python e adatto
a questo uso locale, non a un servizio pubblico. Per una connessione cifrata,
avviarlo con `--host 127.0.0.1` e usare un tunnel SSH dal PC:

```bash
ssh -L 8765:127.0.0.1:8765 ark@192.168.1.43
```

Con il tunnel aperto usare <http://127.0.0.1:8765>. Il servizio accetta indirizzi IP
locali o `localhost`, non nomi mDNS o domini personalizzati. Il login scade dopo
30 minuti; cinque password errate bloccano nuovi tentativi da quell'IP fino alla
fine della finestra di un minuto.

## Cancellazione savestate automatico

Selezionare il gioco nella libreria, poi **Automatic savestate > Check selected game**
(in italiano **Savestate automatico > Controlla gioco selezionato**).
Non occorre caricare un file SRAM. Verificare il percorso mostrato, confermare
che il gioco e chiuso e accettare la cancellazione definitiva, quindi premere
**Delete automatic savestate** / **Cancella savestate automatico**.

Viene eliminato soltanto `<nome ROM>.state.auto`, senza backup. Ad esempio:

```text
/roms2/psx/Alundra (USA).chd
-> ~/.config/retroarch/states/psx/Alundra (USA).state.auto
```

I file `.srm`, `.sav`, `.state`, `.state1`, le immagini `.state.auto.png` e i
savestate degli altri giochi restano invariati. Se il file manca, non viene
cancellato nulla. Il server richiede autenticazione, CSRF, due conferme e un
ticket monouso valido per dieci minuti; rifiuta destinazioni ambigue, collegamenti
simbolici e contenuto cambiato dopo la verifica. Cambiare ROM annulla le conferme.

`state_root` in [config.json](config.json) indica la directory degli stati.
Per le configurazioni precedenti senza questa chiave viene usata la directory
`states` accanto a `save_root`. La mappatura usa il nome della cartella immediatamente
contenente la ROM, come per i salvataggi SRAM. Verificare che corrisponda alle
impostazioni RetroArch: directory personalizzate, ordinamento per core e override
non sono rilevati automaticamente. Il gioco deve essere chiuso: l'app non puo
impedire a RetroArch di ricreare o modificare il file durante l'operazione.

Per abilitare il permesso nella unit installata, ridistribuire anche il pacchetto
con l'installer e riavviare il servizio. Non serve pubblicare nuovamente la
configurazione se i percorsi sono quelli predefiniti. Se la directory `states`
viene creata mentre il servizio e gia attivo, riavviarlo per renderla scrivibile.

## Importazione

1. Chiudere il gioco sulla console. Il programma non puo impedire a un emulatore
   ancora aperto di sovrascrivere successivamente il salvataggio.
2. Selezionare il sistema e la ROM. La ricerca include regione, revisione e sottocartella.
3. Selezionare oppure trascinare nella pagina un solo file `.srm` o `.sav`
  (per PSX anche `.mcd` / `.mcr` raw da 128 KiB),
  non vuoto, massimo 16 MiB. Il trascinamento e disponibile dopo l'accesso,
  quando non ci sono operazioni in corso. Non avvia automaticamente l'importazione.
  Se il nome coincide
   esattamente con una sola ROM, quella ROM viene selezionata automaticamente.
4. Aprire l'anteprima e verificare la destinazione. Il nome originale del file
   caricato non viene usato come percorso: conta la ROM selezionata.
5. Confermare che il gioco e chiuso e, se necessario, la sostituzione. Importare.

L'anteprima scade dopo dieci minuti ed e monouso. Se il salvataggio cambia dopo
l'anteprima, l'importazione viene rifiutata. Destinazioni ambigue tra ROM delle
cartelle configurate sono rifiutate anziche scegliere silenziosamente.
L'importazione mantiene i byte del file: non interpreta o converte il formato.

Prima di ogni sostituzione il file precedente viene copiato in:

```text
<cartella del salvataggio>/.r36s-backups/<nome ROM>.srm/<data UTC>-<id>.bak
```

La scrittura usa un file temporaneo nella stessa directory e una sostituzione
atomica. Se la creazione del backup fallisce, il salvataggio non viene sostituito.
Questo non sostituisce un backup esterno della SD e non garantisce contro guasti
fisici o perdita di alimentazione. I backup non vengono cancellati automaticamente.

Il salvataggio attuale e scaricabile dall'anteprima; subito dopo l'importazione
si puo scaricare il backup precedente, gia rinominato `.srm` per reimportarlo.
I backup precedenti restano sulla SD anche dopo la chiusura della pagina:
per recuperarli manualmente, copiarne uno sul PC e ripristinare l'estensione
`.srm` (o `.sav` secondo il sistema) prima di caricarlo. Non e inclusa una pagina
di gestione dello storico.

## Compatibilita e altri sistemi

Il file PocketSNES di Zelda da 8 KiB e plausibilmente un salvataggio SRAM compatibile,
ma non e stato importato o provato nel gioco. Usare la stessa ROM, regione e revisione.
I test automatici usano dati sintetici, non il file allegato.

- Non sono supportati save state `.state`, conversioni tra formati, esportazioni
  con header, destinazioni memory card condivise o file `.bin` e salvataggi
  di emulatori standalone. `.mcd` / `.mcr` raw sono ammessi solo come ingresso PSX
  verso il file `.srm` del gioco, con i controlli descritti sopra.
- Un `.sav` non viene automaticamente rinominato `.srm`: tranne gli ingressi
  PSX `.mcd` / `.mcr`, estensione sorgente e formato configurato devono coincidere.
  Un'estensione corretta non prova che il
  contenuto sia valido; non viene verificato il checksum interno del gioco.
- Per archivi con nomi interni differenti, giochi multidisco, playlist e override
  specifici verificare prima il percorso di un salvataggio prodotto dall'emulatore.
  Il programma usa il nome dell'archivio senza la sua ultima estensione.
- Non modificare le impostazioni di ordinamento di RetroArch senza adeguare il
  gestore. L'auto-rilevamento dei core e dei loro override non e implementato.

Per aggiungere un sistema, inserire una voce in `systems` e riavviare. Ad esempio,
**dopo aver verificato che il core GBA usi `.srm` e la stessa regola di percorso**:

```json
"gba": {
  "label": "Game Boy Advance",
  "rom_extensions": [".gba", ".zip", ".7z"],
  "save_extension": ".srm"
}
```

## Verifiche locali

```powershell
.\.venv\Scripts\python.exe -m unittest test_saves -v
```

I test coprono integrita byte per byte, rinomina, sottocartelle, nomi ambigui,
backup, modifiche dopo l'anteprima, errori di scrittura, percorsi non sicuri,
login, CSRF, API di importazione/download, password privata, notifica systemd
simulata e attesa delle richieste durante l'arresto. I test PSX coprono ingressi
`.mcd` / `.mcr`, controlli raw via API, backup e scheda condivisa invariata.
Nessun test accede alla console.