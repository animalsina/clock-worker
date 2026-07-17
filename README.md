# WorkBreak Guard

WorkBreak Guard è un’applicazione per Ubuntu e ambienti desktop Linux, progettata per gestire pause, tempo di lavoro, attività, obiettivi giornalieri, saldi orari e straordinari.

L’applicazione funziona tramite area di notifica AppIndicator, con una finestra di controllo alternativa quando il pannello non supporta correttamente la tray.

## Funzionalità principali

- gestione separata delle fasce lavorative mattutina e pomeridiana;
- cicli configurabili di lavoro e pausa;
- tracciamento del tempo per progetto e attività;
- obiettivo giornaliero e saldo tra giornate lavorative;
- gestione di pause regolari, pause manuali e rientri in ritardo;
- classificazione automatica di straordinari ed EXTRA;
- festività italiane, ferie e giornate lavorative straordinarie;
- riepiloghi giornalieri, settimanali e mensili;
- persistenza dello stato dopo la chiusura del programma;
- backup locale e seconda copia opzionale su Google Drive;
- scorciatoia globale per cambiare rapidamente attività.

---

## Modello di funzionamento

### Fasce lavorative

È possibile configurare:

- inizio e fine della fascia mattutina;
- inizio e fine della fascia pomeridiana;
- giorni attivi;
- obiettivo massimo giornaliero;
- durata dei cicli di lavoro e delle pause.

Il timer parte automaticamente soltanto nei giorni e nelle fasce configurate. È comunque possibile avviare manualmente una sessione:

- prima dell’inizio della mattina;
- durante l’intervallo tra mattina e pomeriggio;
- dopo una chiusura anticipata;
- durante ferie, festività o giorni normalmente non lavorativi.

Il tempo lavorato nei giorni esclusi viene classificato come **EXTRA festivo/ferie**.

### Inizio del lavoro

All’avvio di una sessione viene richiesta la coppia:

```text
Progetto + Attività
```

È possibile:

- continuare l’attività corrente;
- riprendere un’attività usata oggi o ieri;
- creare una nuova attività;
- cercare un progetto già utilizzato.

Ogni secondo di lavoro viene attribuito all’attività selezionata.

### Fine della fascia

Alla fine della fascia mattutina o pomeridiana il conteggio non viene interrotto automaticamente.

L’applicazione chiede se il lavoro sta continuando. In caso di conferma:

- il tempo successivo viene registrato come lavoro effettivo;
- l’avviso viene ripetuto secondo l’intervallo configurato;
- il lavoro oltre la fascia contribuisce a compensare eventuali ore mancanti.

Se l’avviso non riceve risposta entro 20 minuti, il tempo viene chiuso all’ultimo momento confermato, evitando di registrare lavoro non effettivamente svolto.

---

## Cicli di lavoro e pause

### Scadenza del ciclo

Quando termina un ciclo di lavoro è possibile scegliere:

- l’ultimatum predefinito;
- 5 minuti;
- 10 minuti;
- avvio immediato della pausa;
- prosecuzione del lavoro senza registrare alcuna pausa.

Il lavoro continua a essere conteggiato fino alla conferma effettiva dell’inizio della pausa.

### Durata della pausa

Per ogni pausa ciclica è possibile scegliere:

- 5 minuti;
- 10 minuti;
- 15 minuti;
- una durata personalizzata fino a 12 ore.

Durante la pausa il countdown viene mostrato nell’area di notifica.

Al termine viene richiesta la nuova attività. Il tempo trascorso tra la fine prevista della pausa e la conferma del rientro rimane registrato come pausa effettiva.

### Pause manuali

Dal comando **Metti in pausa** è possibile avviare:

- una pausa da 5, 10, 15, 30 o 60 minuti;
- una pausa personalizzata da 1 a 720 minuti;
- una pausa senza scadenza.

Le pause manuali interrompono il lavoro e vengono registrate nello storico, ma non vengono considerate tempo utile per il raggiungimento dell’obiettivo giornaliero.

Possono essere interrotte in qualsiasi momento con **Riprendi il lavoro adesso**.

---

## Abbuono delle pause regolari

Le pause cicliche possono contribuire al completamento dell’obiettivo giornaliero entro un plafond configurabile.

Il valore predefinito è composto da:

```text
10 minuti per ogni blocco iniziato di 2 ore lavorate
+ 20 minuti di abbuono extra giornaliero
```

Con una giornata da 8 ore:

```text
Quota regolare:             10 min × 4 blocchi = 40 min
Abbuono extra giornaliero:                   + 20 min
Plafond totale:                                60 min
```

Il tempo di pausa entro il plafond viene considerato utile per l’obiettivo giornaliero. Diventa invece tempo da recuperare:

- la parte che supera il limite della singola pausa;
- la parte che supera il plafond giornaliero complessivo.

Il limite della singola pausa è configurabile e vale 10 minuti per impostazione predefinita.

Esempio: una pausa impostata a 5 minuti può arrivare a 10 minuti senza generare deficit, purché il plafond giornaliero non sia già esaurito. Dall’undicesimo minuto il tempo eccedente viene sottratto dal completamento della giornata.

Le pause manuali sono sempre escluse da questo meccanismo.

---

## Pausa tra mattina e pomeriggio

Se la fascia mattutina termina puntualmente o in anticipo, il rientro viene calcolato rispetto a **Pomeriggio inizio**.

Se il lavoro mattutino termina in ritardo, l’inizio del pomeriggio viene posticipato dello stesso intervallo, in modo da preservare la pausa prevista.

Quando il countdown raggiunge zero senza conferma del rientro, continua con valori negativi:

```text
-00:01
-00:02
-00:03
```

Il tempo negativo resta pausa effettiva e aumenta il deficit.

Il recupero può essere interrotto con **Interrompi e ricomincia a lavorare**. In questo caso la sessione pomeridiana viene avviata immediatamente.

---

## Obiettivo giornaliero e saldo ore

L’obiettivo giornaliero è configurabile e vale 8 ore per impostazione predefinita.

Per il suo completamento vengono considerati:

```text
lavoro effettivo
+ quota abbuonata delle pause cicliche
```

Non vengono considerate:

- pause manuali;
- pause oltre il plafond;
- tempo trascorso con il programma chiuso;
- tempo non confermato dopo la fine della fascia.

Il saldo viene mantenuto tra le giornate lavorative:

- il lavoro in più compensa prima eventuali ore mancanti;
- soltanto il surplus residuo diventa credito;
- un saldo negativo viene riportato finché non viene recuperato.

### Chiusura con saldo negativo

Alla fine della giornata è possibile:

- continuare a lavorare fino all’azzeramento del debito;
- rinviare il residuo al giorno lavorativo successivo.

Durante la compensazione è disponibile **Concludi definitivamente adesso**, che chiude la giornata e riporta soltanto il debito ancora presente.

### Chiusura mensile

Il saldo positivo può essere chiuso automaticamente una volta al mese.

È possibile configurare:

- il giorno base del mese;
- il primo giorno della settimana uguale o successivo al giorno base.

Alla chiusura:

- il saldo positivo diventa **EXTRA da saldo chiuso**;
- il saldo ordinario riparte da zero;
- un saldo negativo continua a essere riportato.

---

## Straordinari ed EXTRA

WorkBreak Guard distingue diverse categorie di tempo aggiuntivo.

### Straordinario oltre fascia

È il lavoro effettivo svolto dopo la fine prevista della fascia.

Contribuisce prima al completamento dell’obiettivo e alla compensazione del saldo negativo.

### EXTRA settimanale

Il limite ordinario settimanale viene calcolato come:

```text
obiettivo giornaliero × numero di giorni attivi
```

Il tempo che supera questo limite viene classificato come **EXTRA settimanale**.

### EXTRA festivo/ferie

Il lavoro svolto durante:

- festività;
- ferie;
- weekend esclusi;
- altri giorni normalmente non lavorativi;

viene classificato integralmente come **EXTRA festivo/ferie** e non consuma il monte ordinario settimanale.

### Giornate lavorative straordinarie

Una data normalmente esclusa può essere marcata come giornata lavorativa straordinaria.

In questo caso vengono utilizzate le normali fasce mattutine e pomeridiane, ma tutto il lavoro rimane classificato come EXTRA.

---

## Gestione della giornata

### Inizia a lavorare adesso

Avvia immediatamente una sessione, anche fuori dalle fasce configurate.

Prima dell’avvio viene richiesta l’attività da utilizzare.

### Termina la giornata adesso

Interrompe:

- lavoro;
- ultimatum;
- pausa;
- attesa di rientro.

Il saldo viene calcolato nel momento della chiusura.

La giornata può essere riaperta nello stesso giorno tramite **Riprendi la giornata adesso**.

### Disattiva promemoria

Il comando congela completamente lo stato corrente senza azzerarlo:

- timer;
- fase;
- attività;
- progetto;
- pausa;
- ultimatum;
- recupero.

Alla riattivazione è possibile:

- continuare dal valore congelato;
- iniziare un nuovo ciclo completo.

Se nel frattempo è cambiata la giornata, viene applicato il normale flusso di avvio della nuova data.

### Reset immediato

Il comando **Resetta e comincia adesso** annulla la fase corrente e avvia un nuovo ciclo completo sull’attività selezionata.

---

## Attività e progetti

La finestra **Attività e tempi** consente di consultare e modificare lo storico.

Per ogni giornata mostra:

- lavoro effettivo;
- pause effettive;
- pause conteggiate nell’obiettivo;
- obiettivo richiesto e tempo mancante;
- saldo giornaliero;
- straordinario oltre fascia;
- EXTRA settimanale;
- EXTRA festivo/ferie;
- dettaglio per progetto e attività.

È possibile:

- aggiungere manualmente una voce;
- modificare progetto, attività e durata;
- eliminare una registrazione;
- classificare il tempo non attribuito;
- trasferire tutto o parte del tempo tra attività della stessa giornata.

Il trasferimento tra attività non modifica il totale lavorato, il saldo o gli straordinari.

Lo storico viene conservato per 24 mesi.

---

## Riepiloghi

Il comando **Mostra riepilogo** apre tre viste.

### Grafico

Mostra:

- avanzamento dell’obiettivo;
- lavoro e pause;
- saldo;
- distribuzione del tempo per progetto e attività.

### Solo testo

Presenta gli stessi dati in forma leggibile e pronta per la consultazione.

### Markdown

Genera un testo modificabile e copiabile, con titolo nel formato:

```text
02 dic 2026
```

La visualizzazione della durata accanto a ogni attività può essere abilitata nelle impostazioni.

Esempio:

```markdown
# 02 dic 2026

- **MyWork**
  - Correzione profilo utente

- **Totale lavoro:** 1 h 20 min
- **Totale pause:** 10 min
- **Pausa conteggiata nell’obiettivo:** 5 min
- **Obiettivo giornaliero:** 1 h 25 min / 8 h
- **Tempo mancante:** 6 h 35 min
- **Straordinario oltre fascia:** 20 min
- **EXTRA totale del giorno:** 0 min
```

---

## Ferie e festività

WorkBreak Guard calcola automaticamente le festività nazionali italiane, comprese quelle mobili come il lunedì dell’Angelo.

Dal 2026 viene considerato anche il 4 ottobre.

È inoltre possibile abilitare separatamente:

- patrono di Este, 23 settembre;
- patrono di Firenze, 24 giugno.

La finestra **Ferie, festività e giornate EXTRA** permette di aggiungere:

- una singola data;
- un intervallo;
- una ricorrenza annuale;
- una giornata lavorativa straordinaria;
- una descrizione personalizzata.

Le date inserite possono essere modificate o eliminate.

---

## Persistenza dello stato

Se il programma viene chiuso e riaperto nella stessa giornata, vengono ripristinati:

- fase corrente;
- tempo residuo;
- progetto e attività;
- ultimatum;
- pausa normale o manuale;
- pausa senza scadenza;
- giornata sospesa;
- recupero post chiusura.

Il tempo trascorso mentre il programma non è in esecuzione non viene conteggiato.

Se alla riapertura è cambiata la fascia o la giornata, viene applicato il normale reset previsto dalla configurazione.

---

## Backup

WorkBreak Guard supporta due destinazioni indipendenti:

1. backup JSON locale;
2. seconda copia opzionale su Google Drive o in una cartella sincronizzata.

Il backup locale è attivo per impostazione predefinita.

### Cartella predefinita

```text
~/.config/workbreak-guard/backups/
```

### Contenuto

Ogni backup contiene:

- impostazioni;
- storico delle attività;
- stato temporaneo del timer, quando disponibile;
- versione e data del formato di backup.

Il nome del file segue questo formato:

```text
workbreak-guard-backup-2026-07-17_183000.json
```

### Frequenza

È possibile scegliere:

- backup automatico disattivato;
- backup giornaliero alla prima apertura utile;
- backup mensile alla prima apertura utile.

Il comando **Esegui backup adesso** genera un unico file e tenta di copiarlo in tutte le destinazioni abilitate.

Il fallimento della copia remota non invalida il backup locale.

### Google Drive

Il programma non richiede un’integrazione Google proprietaria. Utilizza una cartella Drive già disponibile nel file manager oppure una normale cartella locale sincronizzata con un servizio esterno.

Procedura:

1. selezionare **Configura backup su Google Drive**;
2. scegliere il Drive già collegato da **Altre posizioni**;
3. selezionare la cartella di destinazione;
4. attendere la verifica di scrittura.

Il comando **Gestisci account Google** apre le impostazioni Account online di GNOME ed è necessario soltanto per aggiungere o correggere un account.

### Ripristino

**Ripristina da backup** permette di selezionare un file JSON locale o raggiungibile tramite Drive.

Prima del ripristino viene creata una copia di sicurezza in:

```text
~/.config/workbreak-guard/restore-safety/
```

Dopo l’operazione il timer rimane congelato per evitare che i dati ripristinati vengano sovrascritti prima del riavvio.

---

## Installazione

### Dipendenze

```bash
sudo apt-get install -y \
  python3-gi \
  gir1.2-gtk-3.0 \
  pulseaudio-utils \
  gir1.2-ayatanaappindicator3-0.1 \
  gnome-shell-extension-appindicator
```

### Installazione del programma

```bash
unzip workbreak-guard.zip
cd workbreak-guard
./install.sh
```

Avvio:

```bash
workbreak-guard
```

L’installazione abilita automaticamente l’avvio all’accesso.

Se una versione è già in esecuzione, lo script:

1. chiude l’istanza corrente;
2. sostituisce i file;
3. riavvia il programma soltanto se era già aperto.

Per non configurare l’avvio automatico:

```bash
./install.sh --no-autostart
```

---

## Configurazione

Aprire **Impostazioni** dal menu dell’area di notifica o dalla finestra di controllo.

Le principali opzioni configurabili sono:

- fasce mattutina e pomeridiana;
- giorni lavorativi;
- durata dei cicli;
- durata predefinita delle pause;
- plafond giornaliero delle pause;
- limite della singola pausa;
- obiettivo massimo giornaliero;
- gestione del saldo mensile;
- festività e patroni;
- ferie e giornate EXTRA;
- intervallo degli avvisi oltre fascia;
- suoni e volume;
- avvio automatico;
- formato dei riepiloghi;
- backup locale e remoto.

Il salvataggio delle impostazioni non interrompe né azzera il timer.

Le opzioni strutturali contrassegnate con **↻** vengono applicate al successivo avvio, tra cui:

- cicli;
- obiettivo giornaliero;
- fasce;
- giorni;
- festività;
- quote delle pause;
- chiusura mensile.

Le impostazioni audio, l’avvio automatico e il formato Markdown possono essere applicati immediatamente.

---

## File dati

Impostazioni:

```text
~/.config/workbreak-guard/settings.json
```

Storico giornaliero, progetti e attività:

```text
~/.config/workbreak-guard/activity-log.json
```

Stato temporaneo del timer:

```text
~/.config/workbreak-guard/runtime-state.json
```

Backup:

```text
~/.config/workbreak-guard/backups/
```

Copie di sicurezza create prima di un ripristino:

```text
~/.config/workbreak-guard/restore-safety/
```

Configurazione autostart:

```text
~/.config/autostart/workbreak-guard.desktop
```

---

## Area di notifica

Quando AppIndicator supporta le etichette, accanto all’icona viene mostrato uno stato sintetico.

| Stato | Significato |
|---|---|
| `52m` | tempo rimanente nel ciclo di lavoro |
| `! 05:00` | ultimatum prima della pausa |
| `☕ 04:30` | pausa in corso |
| `☕ ∞` | pausa manuale senza scadenza |
| `Rientro -00:30` | pausa terminata, rientro non ancora confermato |
| `START` | attesa dell’avvio della fascia |
| `FINE` | giornata chiusa ma ancora riapribile |
| `Fine?` | conferma richiesta alla fine della fascia |
| `↥ 01:00` | compensazione del saldo negativo |
| `+ 12:30` | lavoro oltre l’orario previsto |
| `Zz` | fuori fascia |
| `OFF` | promemoria disattivati e stato congelato |

Quando disponibile, viene mostrato anche il tempo necessario per completare l’obiettivo:

```text
52m · 6h30 da fare
```

Nei giorni classificati interamente come EXTRA viene mostrato il totale accumulato.

---

## Scorciatoia globale

L’installazione registra su GNOME:

```text
Ctrl + Alt + Q
```

La scorciatoia apre direttamente la selezione dell’attività e comunica con l’istanza già in esecuzione.

Il comando equivalente è:

```bash
workbreak-guard --change-activity
```

Su desktop diversi da GNOME può essere associato manualmente a una scorciatoia di sistema.

---

## Comandi disponibili

Gestione dell’avvio automatico:

```bash
workbreak-guard --enable-autostart
workbreak-guard --disable-autostart
workbreak-guard --status-autostart
```

Cambio rapido dell’attività:

```bash
workbreak-guard --change-activity
```

---

## Compatibilità Wayland e GNOME

Su Wayland il compositor può limitare il posizionamento assoluto delle finestre.

WorkBreak Guard tenta di mostrare gli avvisi:

- sul monitor in cui si trova il puntatore;
- in alto a destra;
- senza sottrarre il focus alla finestra corrente.

Il compositor può comunque scegliere una posizione differente.

La visualizzazione del testo accanto all’icona dipende dal supporto AppIndicator del pannello. Quando il pannello mostra soltanto l’icona, lo stato completo rimane disponibile nel menu e nella finestra di controllo.

---

## Disinstallazione

Dalla cartella del programma:

```bash
./uninstall.sh
```

La procedura rimuove anche l’avvio automatico e la scorciatoia GNOME registrata dall’applicazione.

---

## Licenza

Copyright © 2026 **Giuseppe Mazzullo**  
Contatto: **info@animalsina.work**

WorkBreak Guard è distribuito secondo i termini della **PolyForm Noncommercial License 1.0.0**.

Sono consentiti uso, modifica e redistribuzione per finalità non commerciali, nel rispetto del file [`LICENSE`](LICENSE) e degli avvisi di copyright.

Qualsiasi utilizzo commerciale richiede un’autorizzazione scritta separata dell’autore.

Ulteriori riferimenti sono disponibili in:

- [`AUTHORS.md`](AUTHORS.md)
- [`NOTICE`](NOTICE)
