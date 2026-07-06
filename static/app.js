document.addEventListener('DOMContentLoaded', () => {
    // --- State and Constants ---
    let resumesList = []; // Local cache of resumes for client-side search
    let deleteIdTarget = null; // Stores target ID when confirming deletion
    const ALLOWED_EXTENSIONS = ['.pdf', '.doc', '.docx'];
    const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

    // --- DOM Selections ---
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const selectedFileName = document.getElementById('selected-file-name');
    const uploadForm = document.getElementById('upload-form');
    const submitBtn = document.getElementById('submit-btn');
    const btnSpinner = document.getElementById('btn-spinner');
    
    const searchInput = document.getElementById('search-input');
    const resumesListContainer = document.getElementById('resumes-list');
    const tableLoading = document.getElementById('table-loading');
    const emptyState = document.getElementById('empty-state');
    const emptyMessage = document.getElementById('empty-message');
    const alertContainer = document.getElementById('alert-container');
    
    // Modal Selectors
    const confirmModal = document.getElementById('confirm-modal');
    const confirmCancelBtn = document.getElementById('confirm-cancel');
    const confirmDeleteBtn = document.getElementById('confirm-delete');
    const confirmSpinner = document.getElementById('confirm-spinner');

    // --- Floating Alerts Helper ---
    function showAlert(message, type = 'success') {
        const alert = document.createElement('div');
        alert.className = `alert ${type}`;
        
        // Custom check/cross SVG based on type
        const iconSvg = type === 'success' 
            ? `<svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`
            : `<svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;

        alert.innerHTML = `
            ${iconSvg}
            <div class="alert-message">${escapeHTML(message)}</div>
            <button type="button" class="alert-close" aria-label="Close alert">
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
            </button>
        `;

        alertContainer.appendChild(alert);

        // Auto close after 5 seconds
        const autoCloseTimeout = setTimeout(() => {
            closeAlert(alert);
        }, 5000);

        // Close on button click
        alert.querySelector('.alert-close').addEventListener('click', () => {
            clearTimeout(autoCloseTimeout);
            closeAlert(alert);
        });
    }

    function closeAlert(alertElement) {
        alertElement.style.opacity = '0';
        alertElement.style.transform = 'translateY(-1rem) scale(0.95)';
        setTimeout(() => {
            alertElement.remove();
        }, 200);
    }

    // --- HTML Escaping Helper ---
    function escapeHTML(str) {
        return str.replace(/[&<>'"]/g, 
            tag => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                "'": '&#39;',
                '"': '&quot;'
            }[tag] || tag)
        );
    }

    // --- Fetch Resumes List ---
    async function loadResumes() {
        showTableSpinner(true);
        try {
            const response = await fetch('/resumes');
            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.message || `HTTP error ${response.status}`);
            }
            resumesList = await response.json();
            renderResumes(resumesList);
        } catch (error) {
            console.error('Fetch error:', error);
            showAlert(`Failed to fetch documents: ${error.message}`, 'error');
            renderResumes([]); // render empty
        } finally {
            showTableSpinner(false);
        }
    }

    // --- Render Resumes Table ---
    function renderResumes(list) {
        resumesListContainer.innerHTML = '';
        
        if (list.length === 0) {
            emptyState.classList.remove('hidden');
            if (resumesList.length === 0) {
                emptyMessage.textContent = 'No resumes available in the repository.';
            } else {
                emptyMessage.textContent = 'No matching documents found.';
            }
            return;
        }

        emptyState.classList.add('hidden');

        list.forEach(resume => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>
                    <div style="font-weight: 500; color: var(--text-primary); word-break: break-all;">
                        ${escapeHTML(resume.filename)}
                    </div>
                </td>
                <td style="color: var(--text-secondary); white-space: nowrap;">
                    ${escapeHTML(resume.upload_time)}
                </td>
                <td style="color: var(--text-secondary); white-space: nowrap;">
                    ${escapeHTML(resume.size)}
                </td>
                <td class="text-right">
                    <div class="action-buttons">
                        <a href="/download/${resume.id}" class="action-btn" title="Download Document" download>
                            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
                            </svg>
                        </a>
                        <button type="button" class="action-btn delete-btn" data-id="${resume.id}" title="Delete Document">
                            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                            </svg>
                        </button>
                    </div>
                </td>
            `;

            // Setup Delete Button Event
            row.querySelector('.delete-btn').addEventListener('click', (e) => {
                const btn = e.currentTarget;
                const id = btn.getAttribute('data-id');
                openDeleteModal(id);
            });

            resumesListContainer.appendChild(row);
        });
    }

    // --- Spinners Visibility Helpers ---
    function showTableSpinner(show) {
        if (show) {
            tableLoading.style.display = 'flex';
            resumesListContainer.style.opacity = '0.4';
            emptyState.classList.add('hidden');
        } else {
            tableLoading.style.display = 'none';
            resumesListContainer.style.opacity = '1';
        }
    }

    function toggleSubmitLoading(loading) {
        if (loading) {
            submitBtn.disabled = true;
            btnSpinner.style.display = 'inline-block';
            submitBtn.querySelector('.btn-text').textContent = 'Uploading...';
        } else {
            submitBtn.disabled = false;
            btnSpinner.style.display = 'none';
            submitBtn.querySelector('.btn-text').textContent = 'Upload File';
        }
    }

    function toggleDeleteLoading(loading) {
        if (loading) {
            confirmDeleteBtn.disabled = true;
            confirmCancelBtn.disabled = true;
            confirmSpinner.style.display = 'inline-block';
            confirmDeleteBtn.querySelector('.btn-text').textContent = 'Deleting...';
        } else {
            confirmDeleteBtn.disabled = false;
            confirmCancelBtn.disabled = false;
            confirmSpinner.style.display = 'none';
            confirmDeleteBtn.querySelector('.btn-text').textContent = 'Confirm Delete';
        }
    }

    // --- Search Filter Logic ---
    searchInput.addEventListener('input', () => {
        const query = searchInput.value.toLowerCase().trim();
        if (!query) {
            renderResumes(resumesList);
            return;
        }
        const filtered = resumesList.filter(resume => 
            resume.filename.toLowerCase().includes(query)
        );
        renderResumes(filtered);
    });

    // --- Drop Zone Interaction & Input Validation ---
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('dragover');
        }, false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            fileInput.files = files;
            handleFileSelection(files[0]);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFileSelection(fileInput.files[0]);
        }
    });

    function handleFileSelection(file) {
        if (!file) {
            resetUploadForm();
            return;
        }

        const ext = '.' + file.name.split('.').pop().toLowerCase();
        
        // Client-side format filtering validation
        if (!ALLOWED_EXTENSIONS.includes(ext)) {
            showAlert('Unsupported file format. Only PDF, DOC, and DOCX are allowed.', 'error');
            resetUploadForm();
            return;
        }

        // Client-side capacity ceiling validation
        if (file.size > MAX_FILE_SIZE) {
            showAlert('File size exceeds the strict 10 MB limit.', 'error');
            resetUploadForm();
            return;
        }

        selectedFileName.textContent = `${file.name} (${formatBytes(file.size)})`;
        selectedFileName.style.color = 'var(--text-primary)';
        submitBtn.disabled = false;
    }

    function resetUploadForm() {
        fileInput.value = '';
        selectedFileName.textContent = 'No file selected';
        selectedFileName.style.color = 'var(--text-muted)';
        submitBtn.disabled = true;
    }

    function formatBytes(bytes) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }

    // --- Upload Form Submission handler ---
    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const file = fileInput.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        toggleSubmitLoading(true);

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                throw new Error(data.message || `Server responded with ${response.status}`);
            }

            showAlert(data.message || 'File uploaded successfully!', 'success');
            resetUploadForm();
            
            // Automated list synchronization
            await loadResumes();
        } catch (error) {
            console.error('Upload error:', error);
            showAlert(`Upload failed: ${error.message}`, 'error');
        } finally {
            toggleSubmitLoading(false);
        }
    });

    // --- Delete Confirmation Modal Logic ---
    function openDeleteModal(id) {
        deleteIdTarget = id;
        confirmModal.classList.remove('hidden');
    }

    function closeDeleteModal() {
        deleteIdTarget = null;
        confirmModal.classList.add('hidden');
        toggleDeleteLoading(false);
    }

    confirmCancelBtn.addEventListener('click', closeDeleteModal);

    // Close modal if clicking outside card
    confirmModal.addEventListener('click', (e) => {
        if (e.target === confirmModal) {
            closeDeleteModal();
        }
    });

    confirmDeleteBtn.addEventListener('click', async () => {
        if (!deleteIdTarget) return;

        toggleDeleteLoading(true);

        try {
            const response = await fetch(`/resume/${deleteIdTarget}`, {
                method: 'DELETE'
            });

            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                throw new Error(data.message || `Server responded with status ${response.status}`);
            }

            showAlert(data.message || 'Document deleted successfully.', 'success');
            closeDeleteModal();

            // Automated list synchronization
            await loadResumes();
        } catch (error) {
            console.error('Delete error:', error);
            showAlert(`Deletion failed: ${error.message}`, 'error');
            toggleDeleteLoading(false);
        }
    });

    // --- Initial Load ---
    loadResumes();
});
