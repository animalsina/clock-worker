# WorkBreak Guard

Promemoria pause per Ubuntu/Wayland, pensato per chi lavora molte ore al PC.

## Cosa fa

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

## Installazione

```bash
unzip workbreak-guard.zip
cd workbreak-guard
sudo apt-get install -y python3-gi gir1.2-gtk-3.0 pulseaudio-utils pipewire-bin dbus gir1.2-ayatanaappindicator3-0.1 gnome-shell-extension-appindicator
./install.sh
```

L’installazione abilita l’avvio automatico, chiude in modo controllato l’eventuale versione precedente e avvia sempre la versione appena installata. Il riavvio usa il PID salvato dall’app e verifica che il nuovo processo sia realmente partito; in caso contrario indica il file di log `~/.config/workbreak-guard/startup.log`.

Il launcher usa esplicitamente `/usr/bin/python3` in modalità isolata e rimuove le variabili ereditate da Snap, IDE e AppImage. In questo modo non vengono caricate per errore librerie come `/snap/core20/.../libpthread.so.0`, incompatibili con la glibc del sistema. Durante l’installazione vengono inoltre riparate le eventuali vecchie scorciatoie di WorkBreak Guard presenti in **Desktop/Scrivania**: non cercano più i file del progetto accanto al collegamento, ma aprono sempre l’installazione stabile in `~/.local/bin/workbreak-guard`.

Per installare senza autostart, ma aprendo comunque subito il programma:

```bash
./install.sh --no-autostart
```

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

### Backup locale e Google Drive

Nelle impostazioni, la sezione **Backup dati locale e Google Drive** gestisce due destinazioni indipendenti:

1. **copia locale**, disponibile senza login e attiva per impostazione predefinita;
2. **seconda copia Google Drive**, facoltativa.

La cartella locale predefinita è:

```text
~/.config/workbreak-guard/backups/
```

Puoi cambiarla con **Scegli cartella locale** oppure disattivare la copia locale. Il pulsante **Esegui backup adesso** crea un solo file JSON e prova a copiarlo in tutte le destinazioni abilitate. Se Google Drive fallisce, la copia locale rimane valida e il programma mostra separatamente l’errore remoto.

Per configurare Google Drive:

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

```text
~/.config/workbreak-guard/restore-safety/
```

Dopo il ripristino il timer viene congelato per impedire che lo stato appena recuperato venga sovrascritto. Puoi scegliere **Riavvia ora** oppure riaprire manualmente WorkBreak Guard in seguito.

Con i valori predefiniti, una giornata da 8 ore funziona così:

```text
Quota regolare:             10 min × 4 blocchi da 2 ore = 40 min
Abbuono extra giornaliero:                              + 20 min
Pausa complessiva utile:                                  60 min
```

Per esempio, una pausa impostata a 5 minuti può durare 10 minuti senza creare deficit, finché resta disponibile il plafond giornaliero. Il tempo dall’undicesimo minuto in poi viene invece sottratto dal completamento delle ore giornaliere.

Il file delle impostazioni è qui:

```text
~/.config/workbreak-guard/settings.json
```

Le statistiche giornaliere, i progetti e i tempi dettagliati delle attività sono qui:

```text
~/.config/workbreak-guard/activity-log.json
```

Lo stato temporaneo necessario a riprendere il timer dopo la chiusura è salvato qui:

```text
~/.config/workbreak-guard/runtime-state.json
```


### Chiamate Slack su Wayland

L’accettazione e la chiusura della chiamata vengono rilevate dal flusso microfono di Slack tramite PipeWire/PulseAudio. Il nome del chiamante viene invece recuperato, quando disponibile, dalla notifica standard del desktop e mantenuto per un intervallo configurabile, predefinito a 180 secondi.

Il nome non è garantito: Slack può nascondere il contenuto delle notifiche, le notifiche possono essere disattivate oppure la formulazione può cambiare. In questi casi la chiamata viene comunque registrata con il nome attività generico. Nelle impostazioni puoi disattivare separatamente il recupero del chiamante e modificare la validità temporale della notifica.

Dal menu dell’icona puoi scegliere **Avvia modalità chiamata manuale**. Durante il conteggio la voce viene sostituita da **Termina modalità chiamata**; alla chiusura viene usato lo stesso flusso della chiamata automatica, compresa la domanda finale sull’argomento e il ripristino dell’attività precedente.

Gli identificativi tecnici temporanei `__wbg_slack_call_*__` vengono ora riparati automaticamente all’avvio. Possono rimanere nello storico soltanto quando una versione precedente viene interrotta prima del consolidamento della chiamata.

## Voci nella barra

Quando il pannello supporta le etichette AppIndicator, accanto all’icona vengono mostrati stati compatti come:

- `52m`: tempo al prossimo ciclo;
- `! 05:00`: ultimatum prima della pausa;
- `☕ 04:30`: pausa in corso;
- `START`: attesa della conferma di inizio mattina/pomeriggio;
- `FINE`: giornata terminata anticipatamente ma ancora riapribile;
- `☕ ∞`: pausa manuale senza scadenza;
- `Rientro -00:30`: pausa terminata da 30 secondi, in attesa della conferma;
- `STOP`: pausa da iniziare immediatamente;
- `Fine?`: attesa della conferma alla fine della fascia;
- `Saldo?`: scelta tra compensazione post chiusura e rinvio;
- `↥ 01:00`: compensazione del saldo mancante in corso;
- `+ 12:30`: lavoro confermato oltre l’orario previsto;
- `↻ 42:15`: recupero della pausa mattutina ancora disponibile;
- `↻ -05:30`: rientro dalla pausa mattutina in ritardo di 5 minuti e 30 secondi;
- `Zz`: fuori fascia;
- `OFF`: promemoria disattivato e timer completamente congelato.

Accanto allo stato viene mostrato anche il tempo ancora necessario per completare l’obiettivo giornaliero, per esempio `52m · 6h30 da fare`. Nelle giornate lavorative straordinarie viene invece mostrato il totale `EXTRA` già accumulato.

Il menu dell’icona è organizzato in gruppi separati e mantiene a portata di mano soltanto le azioni operative: **Disattiva Promemoria**, **Cosa stai facendo adesso? (CTRL + ALT + Q)**, l’eventuale avvio o ripresa della giornata, **Metti in pausa** oppure **Riprendi il lavoro adesso**, **Termina la giornata adesso**, **Mostra riepilogo** e **Impostazioni**. Durante la compensazione post chiusura compare inoltre **Concludi definitivamente adesso**. **Esci** è separato dal resto del menu.

**Disattiva Promemoria** congela senza azzerare il timer, la fase corrente, l’attività e il progetto. La voce diventa **Riattiva promemoria**; alla riattivazione puoi scegliere **Continua da dove interrotto** per recuperare esattamente il residuo congelato oppure **Ricomincia il conteggio** per avviare un nuovo ciclo completo. Se nel frattempo è iniziata una nuova giornata, il vecchio ciclo non viene attribuito alla data nuova e viene applicato il normale avvio odierno.

Dentro **Impostazioni**, nella sezione a due colonne **Azioni programma**, sono disponibili **Resetta e comincia adesso**, **Attività e tempi**, **Ferie, festività e giornate EXTRA** e **Mostra controllo**. L’avvio automatico si abilita o disabilita dalla relativa casella nelle impostazioni.

## Controlli manuali della giornata

Le azioni operative principali sono disponibili dal menu dell’icona. La finestra **Mostra controllo** resta raggiungibile dalla sezione **Azioni programma** delle impostazioni.

### Inizia a lavorare adesso

Puoi avviare il lavoro prima di **Mattina inizio**, durante l’intervallo tra mattina e pomeriggio, dopo una chiusura anticipata oppure in una giornata normalmente esclusa. L’app chiede progetto e attività prima di iniziare.

- prima della mattina il tempo viene conteggiato come lavoro reale anticipato;
- tra mattina e pomeriggio viene avviata anticipatamente la sessione pomeridiana;
- dopo la chiusura il lavoro prosegue in modalità manuale finché non lo termini;
- durante ferie, festività o giorni non attivi il tempo resta classificato come **EXTRA festivo/ferie**.

### Pausa manuale

Premendo **Metti in pausa** puoi scegliere 5, 10, 15, 30 o 60 minuti, indicare liberamente una durata da 1 a 720 minuti oppure selezionare **Pausa senza scadenza**.

La pausa parte nel momento della scelta, interrompe il conteggio del lavoro e viene registrata tra le pause effettive. Non viene però sommata alle ore utili dell’obiettivo giornaliero. Puoi interromperla in qualunque momento con **Riprendi il lavoro adesso**; prima di ripartire viene mostrata la normale finestra **Cosa stai facendo adesso?**.

### Termina e riprendi la giornata

**Termina la giornata adesso** ferma lavoro, ultimatum o pausa in corso e registra immediatamente il saldo maturato. Il riepilogo mostra quindi l’eventuale deficit o surplus corrente.

La giornata non viene bloccata definitivamente: nello stesso giorno compare **Riprendi la giornata adesso**, che riapre il saldo e ricomincia ad attribuire il tempo al progetto e all’attività scelti. Il nuovo lavoro riduce prima il deficit e soltanto l’eventuale eccedenza diventa credito.

## Scorciatoie globali

Durante l’installazione viene registrata su GNOME/Ubuntu la scorciatoia:

- **Ctrl + Alt + Q**: apre la finestra **Cosa stai facendo adesso?** e permette di continuare, riprendere o creare rapidamente un’attività.

La scorciatoia richiama l’istanza già aperta di WorkBreak Guard senza avviare un secondo timer. Se l’app non è in esecuzione, la avvia e inoltra la richiesta; fuori dalle fasce configurate viene mostrato il normale avviso di fuori fascia.

Lo stesso comando può essere richiamato da terminale:

```bash
workbreak-guard --change-activity
```

Su ambienti desktop diversi da GNOME la registrazione automatica potrebbe non essere disponibile; il comando precedente può comunque essere associato manualmente a una scorciatoia di sistema. La disinstallazione rimuove anche la scorciatoia GNOME registrata dall’app.

## Attività e progetti

All’avvio della mattina la domanda resta **“Cosa stai facendo oggi?”**. Negli altri momenti, quando rientri da una pausa, usi il menu o premi **Ctrl + Alt + Q**, la finestra mostra **“Cosa stai facendo adesso?”** e puoi:

- continuare l’attività corrente;
- riprendere una delle attività usate oggi o ieri;
- creare una nuova attività;
- associare o cercare rapidamente un progetto già utilizzato.

Cambiare attività non modifica il countdown della pausa: cambia soltanto la voce a cui vengono attribuiti i secondi successivi. Il pulsante **Resetta e comincia adesso**, disponibile nelle impostazioni, riporta il countdown ai minuti di lavoro configurati e lo avvia immediatamente. **Inizia a lavorare adesso** può essere usato anche prima o fuori dalle fasce, mentre **Termina la giornata adesso** e **Riprendi la giornata adesso** permettono di sospendere e riaprire il conteggio senza perdere il saldo.

La finestra **Attività e tempi** mostra per ogni giorno:

- totale del lavoro effettivo;
- totale delle pause effettive;
- pausa regolare conteggiata nell’obiettivo giornaliero;
- ore richieste, ore utili registrate e tempo ancora mancante;
- straordinario oltre la fascia oraria;
- monte ordinario settimanale e relativo limite;
- EXTRA oltre il limite settimanale;
- EXTRA festivo/ferie, mostrato separatamente;
- totale EXTRA del mese e riporto del mese precedente;
- progetto;
- attività;
- tempo effettivamente impiegato.

Da questa finestra puoi inoltre:

- aggiungere autonomamente una nuova voce con progetto, attività e durata;
- modificare una riga con doppio clic o con **Modifica selezionata**;
- correggere, classificare o eliminare **Tempo precedente non classificato**;
- eliminare una voce e sottrarre automaticamente il relativo tempo dal totale;
- aprire il riepilogo del giorno nei tab ordinati **Grafico**, **Solo testo** e **Markdown**; dal menu dell’icona la voce **Mostra riepilogo** apre direttamente quello della giornata corrente;
- aprire **Straordinari ed EXTRA del mese**, con dettaglio giornaliero, distinzione tra oltre fascia, limite settimanale e festività/ferie, totale mensile e riporto del mese precedente.

Esempio di esportazione con i tempi per task disattivati, come da impostazione predefinita:

```markdown
# 02 dic 2026

- **MyWork**
  - Correzione profilo utente

- **Totale lavoro:** 1 h 20 min
- **Totale pause:** 10 min
- **Pausa conteggiata nell’obiettivo giornaliero:** 5 min
- **Obiettivo giornaliero:** 1 h 25 min / 8 h
- **Tempo mancante:** 6 h 35 min
- **Straordinario oltre fascia del giorno:** 20 min
- **EXTRA totale del giorno:** 0 min
- **EXTRA dicembre 2026:** 3 h 10 min
- **EXTRA riportato dal mese precedente (novembre 2026):** 1 h 15 min
```

Attivando **Mostra il tempo impiegato per ogni task nel Markdown** nelle impostazioni, le attività vengono invece mostrate nel formato `Correzione profilo utente — 1 h 20 min`. Questa opzione riguarda soltanto il tab Markdown: il tab Grafico mostra sempre le durate, perché sono necessarie per leggere correttamente le barre.

## Ferie, festività e giornate lavorative EXTRA

Apri **Ferie, festività e giornate EXTRA** dalla sezione **Azioni programma** di **Impostazioni**.

La finestra permette di:

- aggiungere una singola giornata di ferie o una festività mancante;
- aggiungere un intervallo, per esempio dal 10 al 21 agosto;
- aggiungere una **Giornata lavorativa straordinaria** che riattiva le fasce configurate anche se quella data è festiva, di ferie o normalmente esclusa;
- assegnare una descrizione;
- scegliere se la voce vale una sola volta oppure si ripete ogni anno;
- modificare ed eliminare le date inserite.

Le festività nazionali sono calcolate in base all’anno, quindi il lunedì dell’Angelo cambia automaticamente. Le ricorrenze fisse e i patroni selezionati vengono riconosciuti anche negli anni successivi.

Quando una giornata normalmente esclusa viene resa lavorativa, il timer usa le normali fasce mattina/pomeriggio ma tutte le ore effettivamente lavorate vengono indicate come **EXTRA festivo/ferie**. Queste ore non consumano il limite ordinario settimanale e vengono mostrate separatamente nei riepiloghi.

## Comandi utili

```bash
workbreak-guard --enable-autostart
workbreak-guard --disable-autostart
workbreak-guard --status-autostart
```

Il file autostart viene gestito qui:

```text
~/.config/autostart/workbreak-guard.desktop
```

## Disinstallazione

```bash
./uninstall.sh
```

## Note Wayland/GNOME

Su Wayland alcuni compositor possono limitare il posizionamento assoluto delle finestre. L’app prova a mostrare gli avvisi rapidi in alto a destra sul monitor in cui si trova il puntatore e senza focus automatico, ma il compositor può scegliere una posizione differente.

La preview testuale accanto all’icona usa la funzione label di AppIndicator/Ayatana. Alcuni pannelli GNOME possono mostrare solo l’icona e nascondere il testo: in quel caso lo stato completo resta visibile nel menu della tray e nella finestra di controllo.

## Licenza, autore e contatti

Copyright © 2026 **Giuseppe Mazzullo** — **info@animalsina.work**.

WorkBreak Guard è distribuito con **PolyForm Noncommercial License 1.0.0**. L’uso, la modifica e la redistribuzione gratuita sono consentiti per finalità non commerciali nel rispetto del file [`LICENSE`](LICENSE) e mantenendo gli avvisi di copyright. Qualsiasi utilizzo commerciale richiede un’autorizzazione scritta separata dell’autore.

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
