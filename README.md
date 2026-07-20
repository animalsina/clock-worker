# WorkBreak Guard

WorkBreak Guard è un’applicazione per Ubuntu e ambienti desktop Linux, progettata per gestire pause, tempo di lavoro, attività, obiettivi giornalieri, saldi orari e straordinari.

L’applicazione funziona tramite area di notifica AppIndicator, con una finestra di controllo alternativa quando il pannello non supporta correttamente la tray.

<<<<<<< HEAD
- Rileva su Wayland le chiamate Slack accettate tramite il flusso microfono PipeWire/PulseAudio, propone un timer dedicato, applica una retention configurabile alla chiusura e chiede una descrizione finale. Quando Slack include il chiamante nella notifica desktop, correla il nome alla chiamata e crea attività come **Chiamata Slack con Mario Rossi — argomento**. Dal menu dell’icona è disponibile anche una modalità chiamata manuale per telefono, Meet o altre occasioni.

- Gestisce separatamente la fascia del mattino e quella del pomeriggio.
- All’ingresso in **Mattina inizio** e **Pomeriggio inizio** azzera il ciclo, ma applica sempre un limite forzato all’orario di fine della fascia: il timer parte dal valore minore tra i minuti configurati e il tempo realmente rimasto. Per esempio, alle 12:38 con **Mattina fine** alle 13:00 mostra 22 minuti, non 60.
- Non avvia automaticamente il conteggio: mostra prima la richiesta **“Possiamo iniziare la mattina/pomeriggio?”**.
- Nella stessa richiesta permette di indicare **progetto** e **attività**, continuare quella corrente oppure riprendere una voce usata oggi o ieri.
- Conta automaticamente nei giorni e nelle fasce configurate, ma permette anche di iniziare manualmente prima dell’orario o in una giornata esclusa.
- **Inizia a lavorare adesso** apre la stessa scelta progetto/attività e avvia immediatamente il conteggio; il lavoro anticipato riduce il deficit giornaliero e l’eventuale eccedenza confluisce nel saldo.
- **Pausa manuale…** permette pause rapide da 5, 10, 15, 30 o 60 minuti, una durata personalizzata fino a 12 ore oppure una pausa senza scadenza.
- Le pause manuali vengono registrate come pause effettive ma non sono accreditate nell’obiettivo giornaliero, quindi generano correttamente un eventuale deficit.
- **Termina la giornata adesso** ferma immediatamente ogni conteggio, fotografa il saldo del momento e lascia disponibile **Riprendi la giornata adesso** per ricominciare più tardi nello stesso giorno.
- Alla fine della fascia mattutina o pomeridiana non interrompe il lavoro automaticamente: chiede se stai ancora lavorando.
- Premendo **Sto continuando** conteggia anche il tempo trascorso dalla fine prevista e ripropone l’avviso ogni intervallo configurato, 10 minuti per impostazione predefinita.
- Se non rispondi entro 20 minuti, evita falsi positivi e considera come ultimo momento lavorato l’orario previsto oppure l’ultimo avviso a cui avevi confermato di continuare.
- Quando termini il mattino, il countdown centrale usa come riferimento **Pomeriggio inizio** se la pausa è cominciata puntualmente o in anticipo. Se la pausa è iniziata dopo **Mattina fine**, il rientro viene spostato dello stesso ritardo per garantire l’intera pausa prevista.
- Quando il recupero arriva a `00:00` e non hai ancora confermato il rientro, continua in negativo (`-00:01`, `-00:02`, …). Tutto il tempo negativo resta pausa effettiva e aumenta il deficit; il ritardo iniziale non viene conteggiato due volte quando la pausa è partita tardi.
- Il countdown di recupero può essere interrotto con **Interrompi e ricomincia a lavorare**; da quel momento l’app considera già avviato il pomeriggio senza mostrare un secondo avviso di inizio.
- Calcola automaticamente le festività nazionali italiane, compreso il lunedì dell’Angelo e, dal 2026, il 4 ottobre; può inoltre includere i patroni di Este e Firenze.
- Non recupera le ore perse: se il PC è spento o l’app non gira, il timer non accumula arretrati.
- Alla scadenza del tempo di lavoro chiede quale ultimatum usare:
  - tempo predefinito configurato;
  - 5 minuti;
  - 10 minuti;
  - **Inizia subito la pausa**, senza passare da “Fermati subito!”.
- Nella scelta dell’ultimatum, nella schermata **“Fermati subito!”** e nella selezione della durata è disponibile **Salta pausa e continua il lavoro**: non registra alcuna pausa e avvia subito un nuovo blocco di lavoro sull’attività corrente.
- Quando la pausa viene realmente avviata permette di scegliere ogni volta **5, 10 o 15 minuti**, oppure una durata personalizzata fino a 12 ore.
- La pausa ciclica concorre all’obiettivo giornaliero entro due quote: **10 minuti per ciascun blocco iniziato di 2 ore lavorate** e un **abbuono extra giornaliero di 20 minuti**, entrambi configurabili. Con una giornata da 8 ore il valore predefinito è quindi **40 minuti regolari + 20 minuti extra**. Soltanto la parte che supera il tetto giornaliero diventa tempo da recuperare.
- Il limite della singola pausa resta quello configurato, 10 minuti per impostazione predefinita: scegliendo 5 minuti, anche gli eventuali 5 minuti successivi trascorsi nella schermata di rientro possono essere abbuonati. Dall’undicesimo minuto la pausa produce recupero, oppure prima quando il plafond giornaliero è già esaurito.
- Dopo la scelta, il countdown non resta in una finestra: viene mostrato accanto all’icona nella barra di sistema.
- Anche mentre scegli l’ultimatum o mentre è aperto **“Fermati subito!”**, il lavoro continua a essere conteggiato fino a quando premi **Ho iniziato la pausa**.
- Anche il countdown della pausa resta nella barra e non apre una finestra centrale dedicata.
- Al termine della pausa chiede **“Cosa stai facendo adesso?”**, con possibilità di continuare, cambiare attività o riprenderne una di oggi/ieri.
- Nella stessa schermata di rientro mostra due conteggi aggiornati ogni secondo: **quanto tempo è trascorso dalla fine prevista della pausa**, nel formato negativo `-00:30`, e **quanto stai superando la quota realmente abbuonata**. Per esempio, dopo una pausa effettiva di 15 minuti con 10 minuti abbuonati e 30 secondi di ritardo mostra `Pausa terminata da: -00:30` e `Sforamento oltre i 10:00 abbuonati: -05:30`.
- Registra i secondi di lavoro effettivo e di pausa effettiva, includendo l’eventuale tempo oltre la fine della pausa fino alla conferma del rientro.
- Per l’obiettivo giornaliero considera **lavoro effettivo + quota abbuonabile delle pause regolari**. I minuti entro il plafond giornaliero non aumentano le ore mancanti; soltanto l’eccedenza oltre il limite della singola pausa o oltre il plafond complessivo resta da recuperare. I minuti lavorati oltre la fine della fascia sono sempre lavoro effettivo e compensano immediatamente il deficit.
- Se una pausa pomeridiana oltrepasserebbe l’orario di chiusura, la sua durata viene automaticamente troncata ai soli minuti ancora disponibili prima della fine giornata. Il tempo successivo non viene accreditato come lavoro.
- Permette di impostare il **tempo massimo per giornata**, 8 ore per impostazione predefinita, e mostra continuamente quanto manca al completamento.
- Mantiene un **saldo ore** tra le giornate lavorative: il tempo lavorato in più compensa prima eventuali ore mancanti; soltanto il surplus residuo resta disponibile come credito.
- Alla chiusura del pomeriggio, quando il saldo resta negativo, mostra due scelte:
  - **Compensa post chiusura**, continuando il conteggio con un countdown centrale fino all’azzeramento del debito;
  - **Posticipa al prossimo giorno**, conservando il residuo e sommandolo al conteggio del prossimo giorno lavorativo.
- Durante la compensazione post chiusura puoi premere **Concludi definitivamente adesso** in qualsiasi momento: la giornata viene chiusa subito e soltanto il residuo ancora mancante viene rinviato.
- Il saldo positivo viene chiuso una volta al mese. Nelle impostazioni puoi scegliere il giorno base del mese e il primo giorno della settimana uguale o successivo, per esempio il primo lunedì o venerdì dopo la data indicata.
- Alla chiusura mensile il saldo positivo diventa **EXTRA da saldo chiuso** e riparte da zero; un eventuale saldo negativo continua invece a essere riportato finché non viene recuperato.
- Calcola il limite ordinario settimanale come **tempo massimo per giornata × numero di giorni attivi**. Tutto ciò che supera questo valore viene classificato come **EXTRA settimanale**.
- Le ore lavorate in festività, ferie o giorni normalmente non lavorativi vengono classificate integralmente come **EXTRA festivo/ferie** e restano separate dal monte ordinario settimanale.
- Attribuisce ogni secondo di lavoro alla coppia **Progetto + Attività**, così è possibile passare da un lavoro all’altro senza perdere i tempi.
- Alla fine della fascia pomeridiana mostra il riepilogo giornaliero completo, con lavoro, pause, obiettivo giornaliero, straordinario oltre fascia, EXTRA settimanale, EXTRA festivo/ferie e tempo impiegato per ogni attività.
- La finestra **Attività e tempi** è consultabile da **Impostazioni** o dalla finestra di controllo e permette di scorrere i giorni. Mostra anche i totali settimanali e mensili e il riporto del mese precedente.
- Da **Attività e tempi** puoi aggiungere manualmente nuove righe, modificare progetto, attività e durata, trasferire tutto o parte del tempo di un task verso un altro task della stessa giornata, oppure eliminare una voce. Il trasferimento non modifica il totale lavorato, il saldo o gli straordinari giornalieri.
- Anche **Tempo precedente non classificato** è modificabile: lasciando vuota l’attività puoi correggerne soltanto la durata, compilando progetto e attività puoi classificarlo, oppure puoi eliminarlo e sottrarlo dal totale giornaliero.
- **Mostra riepilogo** è disponibile direttamente dal menu dell’icona e dentro **Attività e tempi**. La finestra apre per primo **Grafico**, con avanzamento dell’obiettivo, indicatori di lavoro/pausa/saldo e barre ordinate per progetto e attività; segue **Solo testo**, con sezioni leggibili e durata sempre visibile per ogni task; infine **Markdown**, con titolo nel formato `02 dic 2026`, testo modificabile e copia negli appunti. Testo e Markdown hanno pulsanti di copia separati.
- Conserva attività, progetti e straordinari per 24 mesi. I progetti già usati vengono proposti con ricerca rapida.
- Il comando **Resetta e comincia adesso**, spostato nella sezione **Azioni programma** delle impostazioni, annulla pausa, ultimatum o attese e riporta subito il timer al valore completo configurato.
- Se chiudi e riapri il programma nello stesso giorno, riprende esattamente dal punto interrotto: tempo di lavoro, ultimatum, pausa normale o manuale, pausa senza scadenza, giornata sospesa, progetto e attività corrente.
- Il tempo trascorso mentre il programma è chiuso non viene scalato. Se nel frattempo cambia fascia o giornata, viene applicato il normale reset di inizio mattina/pomeriggio.
- **Disattiva Promemoria** non cancella più lo stato: congela lavoro, ultimatum, pausa, rientro o recupero esattamente al secondo corrente. Alla riattivazione viene chiesto se continuare dal residuo oppure ricominciare il conteggio.
- La scorciatoia globale **Ctrl + Alt + Q** apre direttamente **“Cosa stai facendo adesso?”**, anche mentre stai usando un altro programma.
- Le finestre di avviso rapide vengono mostrate in alto a destra sul monitor in cui si trova il puntatore, senza rubare il focus alla tastiera. I pulsanti restano disabilitati per i primi 800 ms per evitare selezioni involontarie causate dal clic già in corso.
- Alla scadenza dei timer permette di scegliere tra nessun suono, beep morbido, doppio beep o campanello; nelle impostazioni è disponibile anche il pulsante **Prova**. Durante la pausa può continuare a emettere beep lievi periodici, configurabili e disattivabili.
- Aggiunge una voce nella tray/barra se AppIndicator è disponibile; altrimenti usa una piccola finestra di controllo.
=======
## Funzionalità principali
>>>>>>> fd9e63a066e7a5249316d6588de4d8b4a502f918

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

<<<<<<< HEAD
```bash
unzip workbreak-guard.zip
cd workbreak-guard
sudo apt-get install -y python3-gi gir1.2-gtk-3.0 pulseaudio-utils pipewire-bin dbus gir1.2-ayatanaappindicator3-0.1 gnome-shell-extension-appindicator
./install.sh
```

L’installazione abilita l’avvio automatico, chiude in modo controllato l’eventuale versione precedente e avvia sempre la versione appena installata. Il riavvio usa il PID salvato dall’app e verifica che il nuovo processo sia realmente partito; in caso contrario indica il file di log `~/.config/workbreak-guard/startup.log`.

Il launcher usa esplicitamente `/usr/bin/python3` in modalità isolata e rimuove le variabili ereditate da Snap, IDE e AppImage. In questo modo non vengono caricate per errore librerie come `/snap/core20/.../libpthread.so.0`, incompatibili con la glibc del sistema. Durante l’installazione vengono inoltre riparate le eventuali vecchie scorciatoie di WorkBreak Guard presenti in **Desktop/Scrivania**: non cercano più i file del progetto accanto al collegamento, ma aprono sempre l’installazione stabile in `~/.local/bin/workbreak-guard`.

Per installare senza autostart, ma aprendo comunque subito il programma:
=======
---

## Modello di funzionamento

### Fasce lavorative
>>>>>>> fd9e63a066e7a5249316d6588de4d8b4a502f918

È possibile configurare:

<<<<<<< HEAD
Per installare senza aprire il programma al termine:

```bash
./install.sh --no-start
```

Su Ubuntu/GNOME la tray può dipendere dall’estensione AppIndicator. Se non compare, l’app resta utilizzabile tramite la finestra di controllo.

## Configurazione

Apri **Impostazioni** dal menu tray o dalla finestra di controllo. La finestra si adatta allo schermo, ha una scrollbar verticale e mantiene sempre raggiungibili i pulsanti inferiori. In alto, la sezione **Azioni programma** dispone i comandi spostati dal menu dell’icona in due colonne.

Salvare le impostazioni non riavvia, non azzera e non sospende il timer, e non apre più richieste del tipo “continui da dove interrotto?”. Le opzioni strutturali contrassegnate con **↻** — durata dei cicli, obiettivo giornaliero, fasce, giorni, festività, quote pausa e chiusura mensile — vengono salvate e applicate al prossimo avvio del programma. Audio, suono, volume, beep, formato Markdown e avvio automatico possono invece essere applicati immediatamente. Lo stato dei promemoria si cambia soltanto tramite **Disattiva/Riattiva promemoria**, senza passare dal pulsante Salva.

Puoi modificare:

- stato dei promemoria tramite il comando dedicato, senza coinvolgere il salvataggio;
- avvio automatico all’accesso;
- minuti di lavoro;
- minuti di pausa ciclica;
- quota regolare di pausa per ogni blocco di 2 ore lavorate e limite della singola pausa, predefinita a 10 minuti;
- abbuono extra giornaliero delle pause, predefinito a 20 minuti: con 8 ore di lavoro porta il plafond standard da 40 a 60 minuti;
- pause manuali avviabili in qualsiasi momento, con durata definita o senza scadenza;
- tempo massimo per giornata, predefinito a 8 ore;
- giorno base del mese per la chiusura del saldo EXTRA;
- giorno della settimana usato per la chiusura mensile, ad esempio lunedì o venerdì;
- tempo predefinito prima di “Fermati subito!”;
- intervallo dei promemoria quando continui a lavorare oltre la fine fascia, predefinito a 10 minuti;
- fasce orarie mattina/pomeriggio;
- giorni attivi;
- esclusione delle festività nazionali italiane;
- festività patronali di Este (23 settembre) e Firenze (24 giugno), attivabili separatamente;
- ferie, assenze e festività personalizzate aggiungibili come giorno singolo o intervallo;
- giornate lavorative straordinarie, utili per autorizzare il timer durante festività, ferie, weekend o altri giorni esclusi;
- ricorrenza annuale automatica per le date personalizzate che devono valere anche negli anni successivi;
- audio on/off;
- suono alla scadenza dei timer: nessuno, beep morbido, doppio beep o campanello, con anteprima tramite **Prova**;
- volume beep;
- numero beep e distanza in secondi;
- inclusione facoltativa del tempo impiegato accanto a ogni task nel riepilogo Markdown, disattivata per impostazione predefinita;
- backup JSON locale indipendente da Google, attivo per impostazione predefinita;
- copia opzionale su Google Drive gestita come singolo file remoto fisso, senza selezionare o sincronizzare cartelle arbitrarie;
- backup manuale unico verso tutte le destinazioni configurate;
- backup automatico giornaliero all’orario di apertura mattutina oppure mensile alla prima apertura utile;
- ripristino da un backup locale o remoto con conferma e creazione preventiva di una copia locale di sicurezza;
- rilevamento chiamate Slack disattivabile, con intervallo di controllo, retention di chiusura, progetto e nome attività configurabili;
- recupero facoltativo del nome chiamante dalle notifiche desktop, con validità configurabile da 15 a 600 secondi.
=======
- inizio e fine della fascia mattutina;
- inizio e fine della fascia pomeridiana;
- giorni attivi;
- obiettivo massimo giornaliero;
- durata dei cicli di lavoro e delle pause.
>>>>>>> fd9e63a066e7a5249316d6588de4d8b4a502f918

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

<<<<<<< HEAD
1. collega l’account in **Account online** di GNOME, se non è già presente;
2. nell’account Google verifica che il servizio **File** sia abilitato;
3. premi **Configura backup su Google Drive**;
4. scegli soltanto l’account, non una cartella;
5. il programma rileva l’URI esposto da GNOME, monta Drive se necessario e crea una copia di verifica.

Non è più necessario aprire manualmente Google Drive in **File → Altre posizioni** prima della configurazione.

Su Google Drive viene mantenuto esclusivamente questo file, sempre sovrascritto con la versione più recente:

```text
workbreak-guard-backup.json
```

Non viene sincronizzata alcuna cartella e non vengono creati backup remoti con timestamp. Il trasferimento remoto avviene tramite uno stream GIO compatibile con GVfs: il vecchio file viene rimosso e viene creato direttamente il nuovo JSON, senza usare copie o sostituzioni atomiche non supportate dal mount Google Drive. Lo storico locale continua invece a usare file autonomi con nome simile a:

```text
workbreak-guard-backup-2026-07-20_103000.json
```

**Gestisci account Google** apre Account online di GNOME solo per aggiungere, rimuovere o correggere un account. Se una versione precedente aveva salvato una cartella arbitraria, il programma richiede una sola riconfigurazione per passare alla modalità a file remoto unico.

Ogni file contiene in forma leggibile:

- `settings.json`;
- `activity-log.json`;
- `runtime-state.json`, quando presente;
- data, tipo e versione del formato di backup.

La frequenza condivisa può essere **Disattivata**, **Ogni giorno all’apertura mattutina** oppure **Ogni mese alla prima apertura**. Per il giornaliero viene usato l’orario **Mattina inizio**; se il programma viene aperto più tardi, il backup parte alla prima apertura utile della giornata. Ogni destinazione conserva il proprio stato: se la copia locale riesce e Drive fallisce, al successivo avvio Drive può essere ritentato senza rigenerare inutilmente la copia locale già completata.

**Ripristina da file** apre un JSON locale. **Ripristina dal file su Google Drive** recupera direttamente `workbreak-guard-backup.json` dall’account configurato, senza aprire un selettore di cartelle. Prima di sostituire i dati, l’app crea automaticamente una copia locale in:
=======
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
>>>>>>> fd9e63a066e7a5249316d6588de4d8b4a502f918

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

<<<<<<< HEAD

### Chiamate Slack su Wayland

L’accettazione e la chiusura della chiamata vengono rilevate dal flusso microfono di Slack tramite PipeWire/PulseAudio. Il nome del chiamante viene invece recuperato, quando disponibile, dalla notifica standard del desktop e mantenuto per un intervallo configurabile, predefinito a 180 secondi.

Il nome non è garantito: Slack può nascondere il contenuto delle notifiche, le notifiche possono essere disattivate oppure la formulazione può cambiare. In questi casi la chiamata viene comunque registrata con il nome attività generico. Nelle impostazioni puoi disattivare separatamente il recupero del chiamante e modificare la validità temporale della notifica.

Dal menu dell’icona puoi scegliere **Avvia modalità chiamata manuale**. Durante il conteggio la voce viene sostituita da **Termina modalità chiamata**; alla chiusura viene usato lo stesso flusso della chiamata automatica, compresa la domanda finale sull’argomento e il ripristino dell’attività precedente.

Gli identificativi tecnici temporanei `__wbg_slack_call_*__` vengono ora riparati automaticamente all’avvio. Possono rimanere nello storico soltanto quando una versione precedente viene interrotta prima del consolidamento della chiamata.

## Voci nella barra
=======
Il lavoro svolto durante:
>>>>>>> fd9e63a066e7a5249316d6588de4d8b4a502f918

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

<<<<<<< HEAD
I riferimenti dell’autore e la firma sono disponibili anche in [`AUTHORS.md`](AUTHORS.md) e [`NOTICE`](NOTICE).


## Rilevamento chiamate Slack su Wayland

La funzione è disattivata per impostazione predefinita. Quando viene abilitata, WorkBreak Guard controlla i flussi di acquisizione audio esposti da PipeWire tramite `pactl` e, come fallback, `pw-dump`. Il prompt appare dopo l'accettazione della chiamata, quando Slack apre il microfono. Alla scomparsa del flusso viene applicata una retention configurabile fino a 60 secondi; la retention conferma la chiusura senza essere aggiunta al tempo della chiamata. Poi il tempo viene consolidato come attività separata e può essere descritto al volo.

Impostazioni disponibili:

- attivazione o disattivazione completa;
- intervallo di controllo da 1 a 30 secondi;
- retention di chiusura da 0 a 60 secondi;
- progetto predefinito, inizialmente `Expomeeting`;
- nome attività Slack predefinito, inizialmente `Chiamata Slack`;
- nome attività per la modalità manuale, inizialmente `Chiamata`;
- richiesta opzionale della descrizione finale;
- pulsante di verifica immediata del rilevamento.

Dipendenze consigliate: `pulseaudio-utils` per `pactl`; `pipewire-bin` fornisce `pw-dump` come fallback.
=======
Qualsiasi utilizzo commerciale richiede un’autorizzazione scritta separata dell’autore.

Ulteriori riferimenti sono disponibili in:

- [`AUTHORS.md`](AUTHORS.md)
- [`NOTICE`](NOTICE)
>>>>>>> fd9e63a066e7a5249316d6588de4d8b4a502f918
