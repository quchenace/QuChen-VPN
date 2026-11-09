/* 国家/地区旗帜（内联 SVG，无需外部资源） */

const _h3 = (a, b, c) => `<rect width="16" height="3.7" y="0" fill="${a}"/><rect width="16" height="3.7" y="3.7" fill="${b}"/><rect width="16" height="3.7" y="7.3" fill="${c}"/>`;
const _v3 = (a, b, c) => `<rect width="5.34" height="11" fill="${a}"/><rect x="5.34" width="5.33" height="11" fill="${b}"/><rect x="10.67" width="5.33" height="11" fill="${c}"/>`;
const _star = (x, y, r, fill = '#fff') => {
  let p = '';
  for (let i = 0; i < 10; i++) {
    const ang = -Math.PI / 2 + i * Math.PI / 5;
    const rr = i % 2 ? r * 0.42 : r;
    p += `${(x + rr * Math.cos(ang)).toFixed(2)},${(y + rr * Math.sin(ang)).toFixed(2)} `;
  }
  return `<polygon points="${p}" fill="${fill}"/>`;
};
const _cross = (c, w, thick) => `<rect x="${8 - thick / 2}" width="${thick}" height="11" fill="${c}"/><rect y="${5.5 - thick / 2}" width="16" height="${thick}" fill="${c}"/>`;

const FLAGS = {
  '香港': `<rect width="16" height="11" fill="#DE2910"/><circle cx="8" cy="5.5" r="2.9" fill="#fff"/><circle cx="8" cy="3.6" r="1" fill="#DE2910"/><circle cx="9.9" cy="4.9" r="1" fill="#DE2910"/><circle cx="9.2" cy="7.2" r="1" fill="#DE2910"/><circle cx="6.8" cy="7.2" r="1" fill="#DE2910"/><circle cx="6.1" cy="4.9" r="1" fill="#DE2910"/>`,
  '台湾': `<rect width="16" height="11" fill="#FE0000"/><rect width="8" height="5.5" fill="#000095"/><circle cx="4" cy="2.75" r="2" fill="#fff"/><circle cx="4" cy="2.75" r="1.55" fill="#000095"/>`,
  '日本': `<rect width="16" height="11" fill="#fff"/><circle cx="8" cy="5.5" r="3.1" fill="#BC002D"/>`,
  '新加坡': `<rect width="16" height="5.5" fill="#ED2939"/><rect y="5.5" width="16" height="5.5" fill="#fff"/><circle cx="3.6" cy="2.75" r="2.2" fill="#fff"/><circle cx="4.9" cy="2.75" r="1.9" fill="#ED2939"/>${_star(6.4, 1.5, 0.7)}${_star(7.9, 2.6, 0.7)}${_star(7.3, 4.3, 0.7)}`,
  '韩国': `<rect width="16" height="11" fill="#fff"/><circle cx="8" cy="5.5" r="2.6" fill="#CD2E3A"/><path d="M5.4 5.5a2.6 2.6 0 0 0 5.2 0 1.3 1.3 0 0 0-2.6 0 1.3 1.3 0 0 1-2.6 0Z" fill="#0047A0"/>`,
  '美国': `<rect width="16" height="11" fill="#fff"/>${[0, 2, 4, 6, 8, 10].map(y => `<rect y="${y}" width="16" height="1" fill="#B22234"/>`).join('')}<rect width="7" height="6" fill="#3C3B6E"/>`,
  '英国': `<rect width="16" height="11" fill="#012169"/><path d="M0 0 16 11M16 0 0 11" stroke="#fff" stroke-width="2.2"/><path d="M0 0 16 11M16 0 0 11" stroke="#C8102E" stroke-width="1.1"/>${_cross('#fff', 0, 3.1)}${_cross('#C8102E', 0, 1.7)}`,
  '德国': _h3('#000', '#DD0000', '#FFCE00'),
  '法国': _v3('#002395', '#fff', '#ED2939'),
  '荷兰': _h3('#AE1C28', '#fff', '#21468B'),
  '加拿大': `<rect width="16" height="11" fill="#fff"/><rect width="4.4" height="11" fill="#D80621"/><rect x="11.6" width="4.4" height="11" fill="#D80621"/><polygon points="8,2.6 8.9,4.4 10.4,4.1 9.6,5.7 10.8,6.7 8.9,6.9 8,8.8 7.1,6.9 5.2,6.7 6.4,5.7 5.6,4.1 7.1,4.4" fill="#D80621"/>`,
  '澳大利亚': `<rect width="16" height="11" fill="#00247D"/><rect width="7" height="5.2" fill="#00247D"/><path d="M0 0 7 5.2M7 0 0 5.2" stroke="#fff" stroke-width="1.2"/>${_cross('#fff', 0, 1.6)}${_cross('#C8102E', 0, 0.8)}${_star(12, 3, 1.3)}${_star(13.6, 7.4, 1)}${_star(10.4, 8.4, 0.9)}`,
  '俄罗斯': _h3('#fff', '#0039A6', '#D52B1E'),
  '印度': `${_h3('#FF9933', '#fff', '#138808')}<circle cx="8" cy="5.5" r="1.5" fill="none" stroke="#000080" stroke-width="0.7"/><circle cx="8" cy="5.5" r="0.35" fill="#000080"/>`,
  '土耳其': `<rect width="16" height="11" fill="#E30A17"/><circle cx="6.6" cy="5.5" r="2.5" fill="#fff"/><circle cx="7.6" cy="5.5" r="2" fill="#E30A17"/>${_star(10.4, 5.5, 1.3)}`,
  '越南': `<rect width="16" height="11" fill="#DA251D"/>${_star(8, 5.5, 2.7, '#FFFF00')}`,
  '马来西亚': `<rect width="16" height="11" fill="#fff"/>${[0, 2, 4, 6, 8, 10].map(y => `<rect y="${y}" width="16" height="1" fill="#CC0001"/>`).join('')}<rect width="8" height="6" fill="#010066"/><circle cx="3.4" cy="3" r="2" fill="#FFCC00"/><circle cx="4.5" cy="3" r="1.7" fill="#010066"/>`,
  '泰国': `<rect width="16" height="11" fill="#F4F5F8"/><rect width="16" height="2.2" fill="#A51931"/><rect y="8.8" width="16" height="2.2" fill="#A51931"/><rect y="3.7" width="16" height="3.6" fill="#2D2A4A"/>`,
  '菲律宾': `<rect width="16" height="5.5" fill="#0038A8"/><rect y="5.5" width="16" height="5.5" fill="#CE1126"/><polygon points="0,0 7,5.5 0,11" fill="#fff"/>`,
  '印尼': `<rect width="16" height="5.5" fill="#CE1126"/><rect y="5.5" width="16" height="5.5" fill="#fff"/>`,
  '阿联酋': `<rect width="16" height="3.7" fill="#00732F"/><rect y="3.7" width="16" height="3.65" fill="#fff"/><rect y="7.35" width="16" height="3.65" fill="#000"/><rect width="4" height="11" fill="#FF0000"/>`,
  '巴西': `<rect width="16" height="11" fill="#009C3B"/><polygon points="8,1.6 14.6,5.5 8,9.4 1.4,5.5" fill="#FFDF00"/><circle cx="8" cy="5.5" r="2.2" fill="#002776"/>`,
  '阿根廷': `<rect width="16" height="11" fill="#fff"/><rect width="16" height="3.66" fill="#74ACDF"/><rect y="7.34" width="16" height="3.66" fill="#74ACDF"/><circle cx="8" cy="5.5" r="1.3" fill="#F6B40E"/>`,
  '南非': `<rect width="16" height="11" fill="#007A4D"/><rect width="16" height="4" fill="#DE3831"/><rect y="7" width="16" height="4" fill="#002395"/><polygon points="0,0 7,5.5 0,11" fill="#000"/><polygon points="0,1.6 5.4,5.5 0,9.4" fill="#FFB612"/>`,
  '波兰': `<rect width="16" height="5.5" fill="#fff"/><rect y="5.5" width="16" height="5.5" fill="#DC143C"/>`,
  '瑞典': `<rect width="16" height="11" fill="#006AA7"/><rect x="4.6" width="2.2" height="11" fill="#FECC00"/><rect y="4.4" width="16" height="2.2" fill="#FECC00"/>`,
  '芬兰': `<rect width="16" height="11" fill="#fff"/><rect x="4.4" width="2.6" height="11" fill="#003580"/><rect y="4.2" width="16" height="2.6" fill="#003580"/>`,
  '瑞士': `<rect width="16" height="11" fill="#D52B1E"/><rect x="6.9" y="2.6" width="2.2" height="5.8" fill="#fff"/><rect x="5.1" y="4.4" width="5.8" height="2.2" fill="#fff"/>`,
  '西班牙': `<rect width="16" height="11" fill="#AA151B"/><rect y="2.75" width="16" height="5.5" fill="#F1BF00"/>`,
  '意大利': _v3('#009246', '#fff', '#CE2B37'),
  '爱尔兰': _v3('#169B62', '#fff', '#FF883E'),
  '乌克兰': `<rect width="16" height="5.5" fill="#0057B7"/><rect y="5.5" width="16" height="5.5" fill="#FFD700"/>`,
  '以色列': `<rect width="16" height="11" fill="#fff"/><rect y="1.4" width="16" height="1.3" fill="#0038B8"/><rect y="8.3" width="16" height="1.3" fill="#0038B8"/><path d="M8 3.8 9.6 6.6H6.4Z" fill="none" stroke="#0038B8" stroke-width="0.55"/><path d="M8 8.2 6.4 5.4h3.2Z" fill="none" stroke="#0038B8" stroke-width="0.55"/>`,
  '智利': `<rect width="16" height="5.5" fill="#fff"/><rect y="5.5" width="16" height="5.5" fill="#D52B1E"/><rect width="5.33" height="5.5" fill="#0039A6"/>${_star(2.66, 2.75, 1.6)}`,
  '墨西哥': _v3('#006847', '#fff', '#CE1126'),
  '奥地利': _h3('#ED2939', '#fff', '#ED2939'),
  '挪威': `<rect width="16" height="11" fill="#BA0C2F"/><rect x="4" width="3" height="11" fill="#fff"/><rect y="4" width="16" height="3" fill="#fff"/><rect x="5" width="1.4" height="11" fill="#00205B"/><rect y="4.8" width="16" height="1.4" fill="#00205B"/>`,
  '丹麦': `<rect width="16" height="11" fill="#C8102E"/><rect x="4.3" width="2.4" height="11" fill="#fff"/><rect y="4.3" width="16" height="2.4" fill="#fff"/>`,
  '比利时': _v3('#000', '#FDDA24', '#EF3340'),
  '捷克': `<rect width="16" height="5.5" fill="#fff"/><rect y="5.5" width="16" height="5.5" fill="#D7141A"/><polygon points="0,0 8,5.5 0,11" fill="#11457E"/>`,
  '罗马尼亚': _v3('#002B7F', '#FCD116', '#CE1126'),
  '匈牙利': _h3('#CE2939', '#fff', '#477050'),
  '葡萄牙': `<rect width="16" height="11" fill="#FF0000"/><rect width="6.4" height="11" fill="#006600"/><circle cx="6.4" cy="5.5" r="2.2" fill="#FFFF00" stroke="#FF0000" stroke-width="0.5"/>`,
  '希腊': `<rect width="16" height="11" fill="#fff"/>${[0, 2.2, 4.4, 6.6, 8.8].map(y => `<rect y="${y}" width="16" height="1.1" fill="#0D5EAF"/>`).join('')}<rect width="6" height="6" fill="#0D5EAF"/><rect x="2.2" width="1.6" height="6" fill="#fff"/><rect y="2.2" width="6" height="1.6" fill="#fff"/>`,
  '埃及': _h3('#CE1126', '#fff', '#000'),
  '沙特': `<rect width="16" height="11" fill="#165D31"/><rect x="3" y="4.4" width="10" height="0.9" rx="0.45" fill="#fff"/><rect x="4.6" y="6.2" width="6.8" height="0.8" rx="0.4" fill="#fff"/>`,
  '巴基斯坦': `<rect width="16" height="11" fill="#01411C"/><rect width="4" height="11" fill="#fff"/><circle cx="10.6" cy="5.5" r="2.2" fill="#fff"/><circle cx="11.8" cy="5" r="1.9" fill="#01411C"/>${_star(12.4, 3.2, 0.8)}`,
  '孟加拉': `<rect width="16" height="11" fill="#006A4E"/><circle cx="6.6" cy="5.5" r="2.9" fill="#F42A41"/>`,
  '柬埔寨': `<rect width="16" height="11" fill="#032EA1"/><rect y="2.8" width="16" height="5.4" fill="#E00025"/><rect x="6.8" y="4.2" width="2.4" height="3.2" fill="#fff"/>`,
  '新西兰': `<rect width="16" height="11" fill="#00247D"/><rect width="7" height="5.2" fill="#00247D"/><path d="M0 0 7 5.2M7 0 0 5.2" stroke="#fff" stroke-width="1.1"/>${_cross('#fff', 0, 1.4)}${_cross('#CC142B', 0, 0.7)}${_star(12, 3.2, 1)}${_star(13.6, 6.4, 0.9)}${_star(10.6, 8.2, 0.8)}`,
  '哈萨克斯坦': `<rect width="16" height="11" fill="#00AFCA"/><circle cx="8" cy="5.5" r="1.8" fill="#FEC50C"/><rect y="7.6" width="16" height="0.7" fill="#FEC50C"/>`,
  '立陶宛': _h3('#FDB913', '#006A44', '#C1272D'),
  '爱沙尼亚': _h3('#0072CE', '#000', '#fff'),
  '拉脱维亚': `<rect width="16" height="4.4" fill="#9E3039"/><rect y="4.4" width="16" height="2.2" fill="#fff"/><rect y="6.6" width="16" height="4.4" fill="#9E3039"/>`,
  '保加利亚': _h3('#fff', '#00966E', '#D62612'),
  '其他': `<rect width="16" height="11" fill="#EEF3FA"/><circle cx="8" cy="5.5" r="3" fill="none" stroke="#8AA0C0" stroke-width="0.9"/><path d="M5 5.5h6M8 2.5c1.4 1.8 1.4 4.2 0 6" stroke="#8AA0C0" stroke-width="0.8" fill="none"/>`,
};

function flagSvg(country, cls = 'flag') {
  const body = FLAGS[country] || FLAGS['其他'];
  return `<svg class="${cls}" viewBox="0 0 16 11" preserveAspectRatio="none">${body}</svg>`;
}

/* 去掉名字里的国旗 emoji（Windows 无彩色旗帜字体，统一改用 SVG） */
function stripFlag(name) {
  return String(name || '')
    .replace(/[\u{1F1E6}-\u{1F1FF}]{2}/gu, '')
    .replace(/\s+/g, ' ')
    .trim();
}
