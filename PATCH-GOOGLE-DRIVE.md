# Correzione rilevamento Google Drive su GNOME

## Problema

Il programma considerava disponibile Google Drive soltanto quando l'account era già montato da Nautilus/GVFS. Un account correttamente presente in **Impostazioni → Account online** poteva quindi risultare "non trovato" finché non veniva aperto manualmente in **File → Altre posizioni**.

## Correzione

- Lettura degli account Google con servizio File tramite `org.gnome.OnlineAccounts` su D-Bus.
- Uso diretto dell'URI GVFS esposto dall'interfaccia `org.gnome.OnlineAccounts.Files`.
- Tentativo automatico di montaggio tramite `gio mount` quando l'account non è ancora montato.
- Messaggi distinti per account assente, servizio File disabilitato e account che richiede nuova autenticazione.
- Aggiunto `libglib2.0-bin` alle dipendenze consigliate per garantire la presenza del comando `gio`.

## Installazione

Eseguire dalla cartella del delta:

```bash
chmod +x install.sh
./install.sh
```

Il pacchetto contiene soltanto i file modificati.


## Correzione scrittura del file remoto unico

Alcune versioni del backend `google-drive` di GVfs restituiscono `G_IO_ERROR_NOT_SUPPORTED (15)` quando `Gio.File.copy(..., OVERWRITE)` tenta di copiare un file locale direttamente sul mount virtuale o di sostituire atomicamente un file esistente.

La scrittura ora:

- elimina esclusivamente il precedente `workbreak-guard-backup.json`, se presente;
- crea nuovamente lo stesso file remoto;
- trasferisce il JSON tramite `Gio.OutputStream`, a blocchi;
- non usa rename, replace atomico o copia diretta tra filesystem;
- usa una lettura a flusso equivalente anche per il ripristino da Drive.

Google Drive continua quindi a contenere un unico file di backup, mentre i backup con timestamp restano soltanto locali.
