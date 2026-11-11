let dirty = false;
window.addEventListener('labelate-dirty', event => { dirty = event.detail === true; });
window.addEventListener('beforeunload', event => {
  if (dirty) { event.preventDefault(); event.returnValue = ''; }
});
if (typeof WebAssembly.Suspending !== 'function') {
  document.getElementById('pui-status').textContent =
    'This browser does not support WebAssembly JSPI, required for file dialogs. Use a current Chrome or Edge release.';
} else {
  import('./client.js').catch(error => {
    document.getElementById('pui-status').textContent = `Unable to start Labelate: ${error.message}`;
  });
}

window.labelateSavePNGs = files => new Promise((resolve, reject) => {
  if (!window.showDirectoryPicker) {
    reject(new Error('Folder export requires a browser with directory write access, such as Chrome or Edge.'));
    return;
  }
  const dialog = document.createElement('dialog');
  const message = document.createElement('p');
  message.textContent = `Export ${files.length} PNG labels to a folder.`;
  const choose = document.createElement('button');
  choose.textContent = 'Choose folder';
  const cancel = document.createElement('button');
  cancel.textContent = 'Cancel';
  const finish = (value, error) => {
    dialog.close();
    dialog.remove();
    error ? reject(error) : resolve(value);
  };
  cancel.onclick = () => finish('');
  dialog.oncancel = event => { event.preventDefault(); finish(''); };
  choose.onclick = async () => {
    try {
      const directory = await window.showDirectoryPicker({mode:'readwrite'});
      choose.disabled = true;
      cancel.disabled = true;
      dialog.oncancel = event => event.preventDefault();
      let existing = false;
      for (const [name] of files) {
        try { await directory.getFileHandle(name); existing = true; }
        catch (error) { if (error.name !== 'NotFoundError') throw error; }
      }
      if (existing && !window.confirm('Replace existing label PNG files in this folder?')) {
        finish('');
        return;
      }
      for (const [name, data] of files) {
        const file = await directory.getFileHandle(name, {create:true});
        const stream = await file.createWritable();
        try { await stream.write(data); await stream.close(); }
        catch (error) { await stream.abort().catch(()=>{}); throw error; }
      }
      finish(directory.name);
    } catch (error) {
      if (error.name === 'AbortError') finish('');
      else finish('', error);
    }
  };
  dialog.append(message, choose, cancel);
  document.body.append(dialog);
  dialog.showModal();
});
