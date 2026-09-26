# R36S Saves Manager

[English](README.md)

App web locale per importare salvataggi RetroArch sulla R36S, scaricare salvataggi
e backup e cancellare savestate automatici. Disponibile in inglese e italiano.
Richiede **Python >= 3.9**, senza pacchetti esterni o accesso a Internet.

## Formati supportati

| Sistema | Formati in ingresso | Destinazione |
| --- | --- | --- |
| Super Nintendo | `.srm` | Salvataggio `.srm` del gioco |
| PlayStation | `.srm`, `.mcd` / `.mcr` raw da 128 KiB | Memory card `.srm` del gioco |

I file vengono copiati senza conversioni. Per le schede PSX raw vengono verificati
dimensione, firma e checksum dell'header, ma la compatibilita con il gioco non e garantita.
**L'importazione PSX sostituisce l'intera memory card del gioco**, non un singolo slot.
La scheda condivisa `pcsx-card2.mcd` non viene gestita.

Non sono supportati l'importazione di savestate, esportazioni con header, schede
`.bin` e salvataggi di emulatori standalone. Un file `.sav` viene accettato solo
se il sistema e configurato per `.sav`: non viene convertito automaticamente in `.srm`.
Verificare sempre regione, revisione del gioco e compatibilita con l'emulatore.

## Installazione

### Da Windows

Servono PowerShell 5.1 o 7, il client OpenSSH nativo di Windows e `tar.exe`.
L'installer per la console richiede il layout dArkOSen con utente `ark`, `systemd`,
`dialog`, `/opt/inttools/gptokeyb` e `sudo -n` senza richiesta di password.

```powershell
.\packaging\deploy.ps1
```

Inserire indirizzo IPv4 della console e utente SSH, quindi scegliere se pubblicare
la configurazione e avviare il servizio. L'autenticazione viene gestita da OpenSSH;
verificare la fingerprint della console al primo collegamento.

- Il rilascio arresta il servizio e invalida le sessioni: terminare prima le importazioni.
- Configurazione e password web esistenti vengono conservate per impostazione predefinita.
- `-PublishConfig` sostituisce tutta la configurazione remota dopo un backup; i profili non vengono uniti.
- `-StartService` avvia il servizio al termine; l'avvio automatico al boot non viene mai abilitato.
- `-DryRun` verifica il pacchetto senza collegarsi. Il rilascio non prevede rollback automatico.

### Installazione manuale

Trasferire sulla console [R36SavesManager.py](R36SavesManager.py), [config.json](config.json),
[index.html](index.html), [app.js](app.js), [console.png](console.png),
la directory [locales](locales) e [packaging](packaging).
Mantenere la struttura delle cartelle, quindi eseguire:

```bash
sudo -n bash packaging/install.sh
```

### Password e avvio

Dopo l'installazione con uno dei due metodi, impostare la password web da un
terminale SSH interattivo **come `ark`, senza sudo**:

```bash
python3 /home/ark/.local/share/r36s-saves-manager/R36SavesManager.py \
  --set-password --password-file /home/ark/.config/r36s-saves-manager/password
```

Usare almeno 8 caratteri e una password diversa da quella SSH. Inserirla solo
nei prompt nascosti. Il file contiene la password in chiaro, con permessi `0600`
in una directory privata `0700`; e leggibile da `ark` e root.
Per cambiarla, ripetere il comando e riavviare il servizio.

Aprire **Advanced > Saves Manager > Start**, quindi visitare l'indirizzo mostrato
da un PC o telefono sulla stessa rete. La porta predefinita e `8765`.
**Status** mostra lo stato del servizio; **Stop** lo arresta. Uscire dal menu
lascia il server attivo. Se la porta e occupata, l'avvio fallisce.

### Avvio senza installazione

Copiare gli stessi file runtime e la directory `locales`, quindi avviare come `ark`:

```bash
python3 R36SavesManager.py --host 0.0.0.0 --port 8765
```

Inserire la password web al prompt; in questa modalita non viene salvata su disco.
Il server rimane in primo piano, quindi chiudere SSH potrebbe arrestarlo.
Usare `--port` per scegliere un'altra porta.

## Importazione dei salvataggi

1. **Chiudere il gioco sulla console** per evitare che l'emulatore sovrascriva il salvataggio.
2. Selezionare sistema e ROM, poi scegliere o trascinare un salvataggio non vuoto, massimo **16 MiB**.
3. Aprire l'anteprima e verificare la destinazione, determinata dalla ROM selezionata.
4. Confermare che il gioco e chiuso, autorizzare l'eventuale sostituzione e importare.

Le anteprime sono monouso e scadono dopo dieci minuti. L'importazione viene
rifiutata se la destinazione e ambigua o il salvataggio esistente e cambiato
dopo l'anteprima. Selezionare PlayStation prima di caricare file `.mcd` / `.mcr`.

Prima della sostituzione, il vecchio salvataggio viene copiato in `.r36s-backups`
accanto al salvataggio. Se il backup fallisce, il file non viene sostituito.
Il salvataggio attuale e scaricabile dall'anteprima; il backup precedente subito
dopo l'importazione. I backup piu vecchi restano sulla SD: ripristinare l'estensione
`.srm` o `.sav` prima di caricarli manualmente. Non sono presenti una pagina dello
storico o una pulizia automatica.
**Conservare un backup separato della SD:** le scritture atomiche non proteggono da guasti o perdita di alimentazione.

## Cancellazione del savestate automatico

Selezionare un gioco, aprire **Savestate automatico > Controlla gioco selezionato**,
verificare il percorso e confermare che il gioco e chiuso e la cancellazione e
definitiva. Premere **Cancella savestate automatico**. Non serve caricare un salvataggio.

**Viene eliminato solo il file `.state.auto` del gioco selezionato, senza backup.**
Salvataggi SRAM, savestate manuali, miniature e altri giochi restano invariati.
Le destinazioni mancanti, cambiate, non sicure o ambigue non vengono cancellate.
Tenere il gioco chiuso durante l'operazione per evitare che RetroArch ricrei il file.

## Configurazione

Modificare [config.json](config.json) e riavviare il server:

| Impostazione | Valore predefinito |
| --- | --- |
| `rom_root` | `/roms2` |
| `save_root` | `~/.config/retroarch/saves` |
| `state_root` | `~/.config/retroarch/states` |
| `systems` | Super Nintendo (`snes`) e PlayStation (`psx`) |

I percorsi relativi partono dalla cartella del file di configurazione; `~` si
riferisce all'utente che avvia l'app. Senza `state_root`, viene usata la directory
`states` accanto a `save_root`.

I percorsi dei salvataggi usano la **cartella immediatamente contenente la ROM**
e il nome della ROM senza l'ultima estensione. Questo presuppone l'ordinamento
RetroArch per cartella del contenuto, non per core, con salvataggi esterni alla
cartella ROM. Gli override non vengono rilevati automaticamente. Per archivi,
giochi multidisco e playlist verificare prima il percorso creato dall'emulatore.

Per aggiungere sistemi, definire `label`, `rom_extensions` e `save_extension` in
`systems`, dopo aver verificato formato e regole dei percorsi del core. Percorsi
personalizzati per `save_root` o `state_root` richiedono anche l'aggiornamento di
`ReadWritePaths` in [packaging/r36s-saves-manager.service](packaging/r36s-saves-manager.service).
Riavviare il servizio se la directory predefinita `states` viene creata dopo l'avvio.

La lingua si cambia dal selettore nell'intestazione e viene ricordata dal browser.
Per i messaggi italiani nel terminale usare `--language it`; per il launcher
della console impostare `R36S_LANGUAGE=it`. Servono entrambi i cataloghi in `locales`.

## Sicurezza

**Usare solo reti fidate.** HTTP non cifra password o salvataggi.
Non esporre il server a Internet e non abilitare il port forwarding.
Per un accesso cifrato, avviare il server con `--host 127.0.0.1` e aprire un
tunnel SSH dal PC, sostituendo `CONSOLE_IP` con l'indirizzo della console:

```bash
ssh -L 8765:127.0.0.1:8765 ark@CONSOLE_IP
```

Aprire quindi <http://127.0.0.1:8765>. Usare indirizzi IP o `localhost`, non nomi
mDNS o domini personalizzati. Non inserire password o salvataggi personali in Git.

## Aggiornamento e rimozione

Rieseguire lo script di rilascio o l'installer per aggiornare. Il servizio viene
arrestato durante l'installazione: riavviarlo al termine. Configurazione e password
vengono conservate, salvo pubblicazione esplicita di una nuova configurazione.

Per disinstallare l'app mantenendo salvataggi, backup, configurazione e password:

```bash
sudo -n systemctl stop r36s-saves-manager.service
sudo -n rm /etc/systemd/system/r36s-saves-manager.service '/opt/system/Advanced/Saves Manager.sh'
sudo -n systemctl daemon-reload
rm -r /home/ark/.local/share/r36s-saves-manager
```

## Demo e test

Con un ambiente Python locale disponibile:

```powershell
.\.venv\Scripts\python.exe R36SavesManager.py --demo
.\.venv\Scripts\python.exe -m unittest test_saves -v
```

La demo si apre su <http://127.0.0.1:8765> senza password e usa dati temporanei
di esempio, senza accedere a ROM o salvataggi reali. Arrestarla con Ctrl+C prima
di eseguire i test. I test vengono eseguiti localmente senza accedere alla console.