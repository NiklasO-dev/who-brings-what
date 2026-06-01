// Minimal JS - copy to clipboard for share links, privacy dialog
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('input[readonly]').forEach(function(input) {
        input.addEventListener('click', function() {
            this.select();
            if (navigator.clipboard) {
                navigator.clipboard.writeText(this.value);
            }
        });
    });

    var dialog = document.getElementById('privacy-dialog');
    var link = document.getElementById('privacy-link');
    if (!dialog || !link) {
        return;
    }

    var supportsDialog = typeof dialog.showModal === 'function';

    if (supportsDialog) {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            dialog.showModal();
        });

        dialog.querySelectorAll('[data-privacy-close]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                dialog.close();
            });
        });

        dialog.addEventListener('click', function(e) {
            if (e.target === dialog) {
                dialog.close();
            }
        });

        dialog.addEventListener('cancel', function(e) {
            e.preventDefault();
            dialog.close();
        });
    }
});
