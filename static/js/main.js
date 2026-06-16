/* ================================================
   WAIS StockSystem — Main JavaScript
   ================================================ */

/* --- Inventory: Bulk Add Modal --- */

function addRow() {
    const tbody = document.querySelector('#bulkTable tbody');
    if (!tbody) return;
    const newRow = tbody.rows[0].cloneNode(true);
    newRow.querySelectorAll('input').forEach(input => input.value = '');
    tbody.appendChild(newRow);
}

function removeRow(btn) {
    const tbody = document.querySelector('#bulkTable tbody');
    if (!tbody) return;
    if (tbody.rows.length > 1) {
        btn.closest('tr').remove();
    } else {
        alert('You must keep at least one row.');
    }
}
