# fitness-progression-tracker

# Guida Utente — Fitness Progression Tracker

## Panoramica

Fitness Progression Tracker è un'app per registrare e analizzare i tuoi allenamenti in palestra. Il punto di forza è il **motore di progressione**: un sistema che analizza le tue sessioni e ti dice esattamente cosa fare la volta successiva, senza doverti ricordare numeri o fare calcoli.

---

## Registrazione e Login

All'avvio dell'app trovi due tab: **Accedi** e **Registrati**.

- **Registrati**: scegli un username, inserisci il tuo nome e una password. Alla prima registrazione ti vengono caricati automaticamente circa 35 esercizi predefiniti divisi per gruppo muscolare (petto, schiena, spalle, gambe, braccia, core).
- **Accedi**: usa le credenziali scelte in fase di registrazione.
- **Logout**: bottone in sidebar, in alto. La sessione rimane aperta finché non esci manualmente.

---

## Registra Allenamento

È la schermata principale, quella che usi ogni volta che vai in palestra.

**Come funziona:**
1. Scegli la data (default: oggi).
2. Seleziona l'esercizio dal menu a tendina. Gli esercizi sono raggruppati per categoria.
3. Per ogni serie inserisci reps e peso (kg).
4. Premi **Aggiungi serie** — la serie viene salvata subito.
5. Ripeti per tutte le serie dell'esercizio.
6. Cambia esercizio e ripeti.

L'app mostra in tempo reale le serie già registrate per quel giorno. Puoi eliminare una singola serie con il bottone accanto.

> Nota pratica: non devi "chiudere" l'allenamento. Ogni serie è salvata nel momento in cui la aggiungi. Se blocchi lo schermo del telefono, quando torni sei ancora loggato e puoi continuare.

---

## Storico Allenamenti

Visualizza tutti gli allenamenti registrati, filtrabili per data o per esercizio.

- Puoi vedere il dettaglio di ogni sessione passata.
- Utile per verificare cosa hai fatto la settimana scorsa prima di iniziare.
- Le serie possono essere eliminate anche da qui.

---

## Progressi

Grafici interattivi per monitorare l'andamento nel tempo.

- **Peso massimo per sessione**: vedi se il tuo massimo sta salendo o è fermo.
- **Volume totale** (peso × reps × serie): misura il lavoro complessivo per sessione.
- **Medie reps**: utile per capire se stai performando in modo costante.

Puoi filtrare per esercizio e per periodo. I grafici sono interattivi: puoi zoomare e passare con il mouse sui punti per vedere i valori esatti.

---

## Motore di Progressione

È la sezione più utile. Per ogni esercizio analizza le ultime sessioni e ti dice cosa fare la prossima volta.

### Come usarlo

1. Seleziona un esercizio.
2. Il motore mostra la **suggerimento corrente** con il ragionamento.
3. Dopo l'allenamento, torna qui e registra il feedback: hai seguito il suggerimento? Quante reps hai fatto effettivamente?
4. Il feedback alimenta lo storico delle decisioni, utile per vedere i pattern nel tempo.

### Le 7 logiche del motore

Il motore valuta le regole in questo ordine esatto:

| Priorità | Situazione rilevata | Suggerimento |
|----------|---------------------|--------------|
| 1 | Nessun dato disponibile | — |
| 2 | Pausa > 14 giorni dall'ultima sessione | Ripresa graduale: -20% del peso |
| 3 | Peso o reps in calo per 2+ sessioni consecutive | Deload: -10% |
| 4 | Volume alto costante per 4+ settimane senza scarico | Deload proattivo -10% |
| 5 | Stesso peso e stesse reps per 3+ sessioni | Plateau: micro-aumento o cambio schema |
| 6 | Tutte le serie al massimo delle reps target | Aumenta peso del passo configurato |
| 7 | Tutte le serie nel range target ma non al massimo | Aumenta reps di 1 |
| 8 | Qualche serie sotto il minimo target | Mantieni e consolida |

### I parametri configurabili per esercizio

Nella sezione **Impostazioni Target** puoi personalizzare per ogni esercizio:

- **Serie target**: quante serie fare (default: 3)
- **Range reps**: minimo e massimo (default: 8-12)
- **Passo di progressione** (kg): di quanto aumentare il peso ogni volta che sali (default: 2.5 kg)

> Per esempio: per la panca piana potresti impostare 5-8 reps e 5 kg di passo. Per le alzate laterali, 12-15 reps e 1 kg di passo.

---

## Gestione Esercizi

Nella sezione dedicata puoi:

- Aggiungere esercizi personalizzati (nome + categoria).
- Eliminare esercizi che non usi. Attenzione: eliminare un esercizio cancella anche tutto lo storico associato.

---

## Limiti da conoscere

- Il motore analizza le **ultime 8 sessioni** per esercizio.
- Il **plateau** viene rilevato guardando 3 sessioni consecutive: può essere un po' presto su esercizi che progrediscono lentamente. In quel caso valuta tu se cambiare qualcosa o ignorare il suggerimento.
- Il **passo progressione** è lo stesso per tutte le serie dello stesso esercizio. Per esercizi d'isolamento con poco carico, metti un passo piccolo (0.5-1 kg).
- Non c'è distinzione automatica tra esercizi compound e isolation nelle logiche — la personalizzazione dei parametri target è il modo per compensare.
