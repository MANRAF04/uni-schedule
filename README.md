# Εβδομαδιαίο Πρόγραμμα (Flask)

Μικρή εφαρμογή Flask που διαβάζει το `programme.htm` και εμφανίζει το εβδομαδιαίο πρόγραμμα μαθημάτων (Δευτέρα–Παρασκευή) με δυνατότητα αφαίρεσης μαθημάτων και εξαγωγής σε JSON / ICS.

## Γρήγορη Εκτέλεση
```bash
python -m venv .venv
# Windows PowerShell activate:
. .venv/Scripts/Activate.ps1
# Windows Command Prompt activate:
.venv\Scripts\activate.bat
# Linux activate:
./venv/bin/activate
pip install -r requirements.txt
python run.py
```
Άνοιξε: http://127.0.0.1:5000/

## Βασικές Λειτουργίες
- Αφαίρεση μαθήματος: Κλικ στο ✕ (αφαιρεί όλα τα τμήματα με τον ίδιο τίτλο).
- Επαναφορά: Κουμπί «Επαναφορά» (διαγράφει `remaining_courses.json`).
- Μετρητής: Δείχνει πόσα διαφορετικά μαθήματα απομένουν.
- Εξαγωγή JSON: `/api/export`.
- Εξαγωγή ICS: `/export/ics?start=YYYY-MM-DD&weeks=N` (οι εβδομάδες είναι διδακτικές, παραλείπεται το διάστημα 2025-12-23 έως 2026-01-06).

## Παράδειγμα ICS
```
/export/ics?start=2025-09-22&weeks=15
```

## Εισαγωγή στο Google Calendar
Ρυθμίσεις & Import → Import → επιλέγεις το αρχείο .ics → διαλέγεις ημερολόγιο.

## Σημειώσεις
- Οι εβδομάδες στο ICS παραλείπουν τις αργίες Χριστουγέννων (EXDATE).
- Δεν γίνεται μόνιμη αποθήκευση πέρα από το `remaining_courses.json` (δημιουργείται/ενημερώνεται αυτόματα).
