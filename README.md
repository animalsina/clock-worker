# WorkBreak Guard

Promemoria pause per Ubuntu/Wayland, pensato per chi lavora molte ore al PC.

## Cosa fa

- Gestisce separatamente la fascia del mattino e quella del pomeriggio.
- All’ingresso in **Mattina inizio** e **Pomeriggio inizio** azzera sempre il timer al valore completo configurato.
- Non avvia automaticamente il conteggio: mostra prima la richiesta **“Possiamo iniziare la mattina/pomeriggio?”**.
- Nella stessa richiesta permette di indicare **progetto** e **attività**, continuare quella corrente oppure riprendere una voce usata oggi o ieri.
- Conta solo nei giorni e nelle fasce configurate.
- Alla fine della fascia mattutina o pomeridiana non interrompe il lavoro automaticamente: chiede se stai ancora lavorando.
- Premendo **Sto continuando** conteggia anche il tempo trascorso dalla fine prevista e ripropone l’avviso ogni intervallo configurato, 10 minuti per impostazione predefinita.
- Se non rispondi entro 20 minuti, evita falsi positivi e considera come ultimo momento lavorato l’orario previsto oppure l’ultimo avviso a cui avevi confermato di continuare.
- Quando termini il mattino, avvia un countdown centrale per recuperare l’intera pausa prevista tra **Mattina fine** e **Pomeriggio inizio**. Il lavoro oltre orario sposta quindi in avanti il rientro dello stesso numero di minuti.
- Il countdown di recupero può essere interrotto con **Interrompi e ricomincia a lavorare**; da quel momento l’app considera già avviato il pomeriggio senza mostrare un secondo avviso di inizio.
- Calcola automaticamente le festività nazionali italiane, compreso il lunedì dell’Angelo e, dal 2026, il 4 ottobre; può inoltre includere i patroni di Este e Firenze.
- Non recupera le ore perse: se il PC è spento o l’app non gira, il timer non accumula arretrati.
- Alla scadenza del tempo di lavoro chiede quale ultimatum usare:
  - tempo predefinito configurato;
  - 5 minuti;
  - 10 minuti.
- Dopo la scelta, il countdown non resta in una finestra: viene mostrato accanto all’icona nella barra di sistema.
- Anche mentre scegli l’ultimatum o mentre è aperto **“Fermati subito!”**, il lavoro continua a essere conteggiato fino a quando premi **Ho iniziato la pausa**.
- Anche il countdown della pausa resta nella barra e non apre una finestra centrale dedicata.
- Al termine della pausa chiede **“Cosa stai facendo adesso?”**, con possibilità di continuare, cambiare attività o riprenderne una di oggi/ieri.
- Registra i secondi di lavoro effettivo e di pausa effettiva, includendo l’eventuale tempo oltre la fine della pausa fino alla conferma del rientro.
- Per l’obiettivo giornaliero considera **lavoro effettivo + sola pausa regolare fino allo zero del countdown**. Il ritardo prima del rientro resta una pausa effettiva, ma non riduce le ore mancanti.
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
- La finestra **Attività e tempi** è sempre consultabile dal menu dell’icona o dalla finestra di controllo e permette di scorrere i giorni. Mostra anche i totali settimanali e mensili e il riporto del mese precedente.
- Da **Attività e tempi** puoi aggiungere manualmente nuove righe, modificare progetto, attività e durata, oppure eliminare una voce; i totali giornalieri vengono aggiornati automaticamente.
- Anche **Tempo precedente non classificato** è modificabile: lasciando vuota l’attività puoi correggerne soltanto la durata, compilando progetto e attività puoi classificarlo, oppure puoi eliminarlo e sottrarlo dal totale giornaliero.
- Il pulsante **Mostra Markdown** genera il riepilogo del giorno selezionato con titolo nel formato `02 dic 2026`, pronto da modificare e copiare negli appunti.
- Conserva attività, progetti e straordinari per 24 mesi. I progetti già usati vengono proposti con ricerca rapida.
- Il comando **Resetta e comincia adesso** annulla pausa, ultimatum o attese e riporta subito il timer al valore completo configurato.
- Se chiudi e riapri il programma nella stessa fascia e nello stesso giorno, riprende esattamente dal punto interrotto: tempo di lavoro, ultimatum, pausa, attesa di rientro, progetto e attività corrente.
- Il tempo trascorso mentre il programma è chiuso non viene scalato. Se nel frattempo cambia fascia o giornata, viene applicato il normale reset di inizio mattina/pomeriggio.
- La scorciatoia globale **Ctrl + Alt + Q** apre direttamente **“Cosa stai facendo adesso?”**, anche mentre stai usando un altro programma.
- Le finestre di avviso vengono centrate, quando il sistema lo consente, sul monitor in cui si trova il puntatore del mouse.
- Durante la pausa può emettere beep lievi, configurabili e disattivabili.
- Aggiunge una voce nella tray/barra se AppIndicator è disponibile; altrimenti usa una piccola finestra di controllo.

## Installazione

```bash
unzip workbreak-guard.zip
cd workbreak-guard
sudo apt-get install -y python3-gi gir1.2-gtk-3.0 pulseaudio-utils gir1.2-ayatanaappindicator3-0.1 gnome-shell-extension-appindicator
./install.sh
workbreak-guard
```

L’installazione abilita l’avvio automatico. Per installare senza avvio automatico:

```bash
./install.sh --no-autostart
```

Su Ubuntu/GNOME la tray può dipendere dall’estensione AppIndicator. Se non compare, l’app resta utilizzabile tramite la finestra di controllo.

## Configurazione

Apri **Impostazioni** dal menu tray o dalla finestra di controllo.

Puoi modificare:

- attivo/disattivo;
- avvio automatico all’accesso;
- minuti di lavoro;
- minuti di pausa;
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
- volume beep;
- numero beep e distanza in secondi.

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

## Voci nella barra

Quando il pannello supporta le etichette AppIndicator, accanto all’icona vengono mostrati stati compatti come:

- `52m`: tempo al prossimo ciclo;
- `! 05:00`: ultimatum prima della pausa;
- `☕ 04:30`: pausa in corso;
- `START`: attesa della conferma di inizio mattina/pomeriggio;
- `Rientro`: pausa terminata, in attesa della conferma;
- `STOP`: pausa da iniziare immediatamente;
- `Fine?`: attesa della conferma alla fine della fascia;
- `Saldo?`: scelta tra compensazione post chiusura e rinvio;
- `↥ 01:00`: compensazione del saldo mancante in corso;
- `+ 12:30`: lavoro confermato oltre l’orario previsto;
- `↻ 42:15`: recupero della pausa mattutina;
- `Zz`: fuori fascia;
- `OFF`: promemoria disattivato.

Accanto allo stato viene mostrato anche il tempo ancora necessario per completare l’obiettivo giornaliero, per esempio `52m · 6h30 da fare`. Nelle giornate lavorative straordinarie viene invece mostrato il totale `EXTRA` già accumulato.

Dal menu dell’icona sono disponibili anche **Cosa stai facendo adesso?**, **Resetta e comincia adesso**, **Avvia pausa adesso**, **Attività e tempi** e **Ferie, festività e giornate EXTRA**. Durante la compensazione post chiusura compare inoltre **Concludi definitivamente adesso**.

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

Cambiare attività non modifica il countdown della pausa: cambia soltanto la voce a cui vengono attribuiti i secondi successivi. Il pulsante **Resetta e comincia adesso**, invece, riporta il countdown ai minuti di lavoro configurati e lo avvia immediatamente.

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
- generare il riepilogo Markdown del giorno aperto e copiarlo negli appunti;
- aprire **Straordinari ed EXTRA del mese**, con dettaglio giornaliero, distinzione tra oltre fascia, limite settimanale e festività/ferie, totale mensile e riporto del mese precedente.

Esempio di esportazione:

```markdown
# 02 dic 2026

- **MyQuadra**
  - Correzione profilo utente — 1 h 20 min

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

## Ferie, festività e giornate lavorative EXTRA

Apri **Ferie, festività e giornate EXTRA** dal menu dell’icona oppure da **Impostazioni**.

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

Su Wayland alcuni compositor possono limitare il posizionamento assoluto delle finestre. L’app prova a mostrare gli avvisi sul monitor in cui si trova il puntatore, ma il compositor può scegliere una posizione differente.

La preview testuale accanto all’icona usa la funzione label di AppIndicator/Ayatana. Alcuni pannelli GNOME possono mostrare solo l’icona e nascondere il testo: in quel caso lo stato completo resta visibile nel menu della tray e nella finestra di controllo.
