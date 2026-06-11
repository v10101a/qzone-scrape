'use strict';
if (matchMedia('(hover: hover) and (pointer: fine)').matches) {
  document.body.classList.add('museum-cursor');
  const cur = document.createElement('img');
  cur.id = 'museumCursor'; cur.alt = '';
  cur.src = 'library/cursor_anim/1520.png';
  document.body.appendChild(cur);
  document.addEventListener('pointermove', e => {
    cur.style.transform = `translate(${e.clientX}px, ${e.clientY}px)`;
    cur.style.display = 'block';
  }, { passive: true, capture: true });
  document.documentElement.addEventListener('mouseleave', () => { cur.style.display = 'none'; });
}
