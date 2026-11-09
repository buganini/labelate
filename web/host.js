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
