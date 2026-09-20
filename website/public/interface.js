document.querySelectorAll('[data-tab]').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('[data-tab]').forEach(other => {
      const selected = other === tab;
      other.setAttribute('aria-selected', String(selected));
      other.tabIndex = selected ? 0 : -1;
      document.getElementById(other.dataset.tab).hidden = !selected;
    });
  });
  tab.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const tabs = [...document.querySelectorAll('[data-tab]')];
    const index = tabs.indexOf(tab);
    const next = event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs.at(-1) : tabs[(index + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    next.click(); next.focus();
  });
  tab.tabIndex = tab.getAttribute('aria-selected') === 'true' ? 0 : -1;
});
document.querySelector('[data-expand-years]')?.addEventListener('click', () => {
  document.querySelectorAll('.year-archive').forEach(year => year.open = true);
});
document.querySelector('[data-collapse-years]')?.addEventListener('click', () => {
  document.querySelectorAll('.year-archive').forEach(year => year.open = false);
});
document.querySelector('[data-text-size]')?.addEventListener('click', () => {
  document.body.classList.toggle('large-text');
});
