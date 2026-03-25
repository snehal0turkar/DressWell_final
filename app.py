from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import sqlite3
import hashlib
import os
import json
import requests
import colorsys
import uuid
from datetime import datetime
from functools import wraps
from PIL import Image
from zoneinfo import ZoneInfo
IST = ZoneInfo('Asia/Kolkata')


# ─────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dresswell-skintone-2024')

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(BASE_DIR, 'instance', 'dresswell.db')
WEATHER_KEY = os.environ.get('WEATHER_API_KEY', '')
UPLOAD_DIR  = os.path.join(BASE_DIR, 'static', 'uploads')

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)

# ─── JINJA FILTERS ───────────────────────────────────────────────────────────

@app.template_filter('fromjson')
def fromjson_filter(v):
    try:
        return json.loads(v) if v else []
    except Exception:
        return []

@app.template_filter('csscolor')
def csscolor_filter(v):
    return css_color(v) if v else '#888'

# ─── DATABASE ────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def qdb(sql, args=(), one=False):
    conn = get_db()
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return (rows[0] if rows else None) if one else rows

def xdb(sql, args=()):
    conn = get_db()
    cur  = conn.execute(sql, args)
    conn.commit()
    lid  = cur.lastrowid
    conn.close()
    return lid

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth'))
        return f(*args, **kwargs)
    return wrapped

# ─── CSS COLOR HELPER ────────────────────────────────────────────────────────

_CSS_MAP = {
    'light grey':'#b0b0b0','light gray':'#b0b0b0','dark grey':'#404040',
    'dark gray':'#404040','off-white':'#f5f5f0','nude':'#e8c9a0',
    'ecru':'#f0ead6','stone':'#928e85','camel':'#c19a6b','coral':'#ff6b6b',
    'rust':'#b7410e','burgundy':'#800020','maroon':'maroon','charcoal':'#36454f',
    'ivory':'#fffff0','khaki':'khaki','lavender':'lavender','olive':'olive',
    'navy':'navy','cream':'#fffdd0','teal':'teal',
}

def css_color(name):
    if not name:
        return '#888'
    return _CSS_MAP.get(name.lower().strip(), name.lower().strip())

# ─── IMAGE / K-MEANS ─────────────────────────────────────────────────────────

ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

def allowed(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def _cdist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5

def _rgb_to_name(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    hd = h * 360
    if v < .15:  return 'black'
    if v > .88 and s < .12: return 'white'
    if s < .10:  return 'grey'
    if s < .20 and v > .65: return 'beige' if r > b else 'light grey'
    if hd < 15 or hd >= 345: return 'red' if s > .5 else 'pink'
    if hd < 45:  return 'orange' if s > .6 else 'coral'
    if hd < 75:  return 'yellow' if s > .5 else 'cream'
    if hd < 150: return 'green'  if s > .4 else 'olive'
    if hd < 195: return 'teal'
    if hd < 255: return 'navy'   if v < .35 else 'blue'
    if hd < 285: return 'purple' if s > .35 else 'lavender'
    if hd < 330: return 'pink'   if v > .6  else 'maroon'
    return 'neutral'

def extract_dominant_colors(path, k=5):
    try:
        img = Image.open(path).convert('RGB')
        img.thumbnail((120, 120), Image.LANCZOS)
        pixels = list(img.getdata())
        filtered = [(r, g, b) for r, g, b in pixels
                    if not ((r+g+b)/3 > 240 and max(r,g,b)-min(r,g,b) < 20)
                    and not (r+g+b)/3 < 15]
        pixels = filtered if len(filtered) > 50 else pixels
        if not pixels:
            return []
        k = min(k, len(pixels))
        step = max(1, len(pixels) // k)
        centroids = [pixels[i * step] for i in range(k)]
        for _ in range(15):
            clusters = [[] for _ in range(k)]
            for p in pixels:
                clusters[min(range(k), key=lambda i: _cdist(p, centroids[i]))].append(p)
            nc = [(sum(p[0] for p in cl) // len(cl),
                   sum(p[1] for p in cl) // len(cl),
                   sum(p[2] for p in cl) // len(cl)) if cl else centroids[i]
                  for i, cl in enumerate(clusters)]
            if nc == centroids:
                break
            centroids = nc
        clusters2 = [[] for _ in range(k)]
        for p in pixels:
            clusters2[min(range(k), key=lambda i: _cdist(p, centroids[i]))].append(p)
        total = len(pixels)
        res = [{'hex': '#{:02x}{:02x}{:02x}'.format(*c), 'rgb': list(c),
                'name': _rgb_to_name(*c), 'percentage': round(len(cl) / total * 100, 1)}
               for c, cl in zip(centroids, clusters2) if cl]
        res.sort(key=lambda x: x['percentage'], reverse=True)
        return res[:k]
    except Exception as e:
        print('Color error:', e)
        return []

def save_image(file, uid):
    if not file or not file.filename or not allowed(file.filename):
        return None
    ext = file.filename.rsplit('.', 1)[1].lower()
    fn  = 'u{}_{}.{}'.format(uid, uuid.uuid4().hex[:10], ext)
    fp  = os.path.join(UPLOAD_DIR, fn)
    img = Image.open(file.stream).convert('RGB')
    img.thumbnail((800, 800), Image.LANCZOS)
    img.save(fp, quality=88, optimize=True)
    return 'uploads/' + fn

# ─── FASHION COLOR ENGINE ─────────────────────────────────────────────────────

class FCE:
    NEUTRALS      = {'black','white','grey','gray','beige','cream','ivory',
                     'charcoal','off-white','khaki','nude','tan','light grey',
                     'dark grey','ecru','stone'}
    NEAR_NEUTRALS = {'navy','olive','brown','maroon','burgundy','rust','camel','slate'}

    CLASH = {
        frozenset({'green','red'}):15, frozenset({'lime','red'}):12,
        frozenset({'orange','purple'}):20, frozenset({'yellow','purple'}):30,
        frozenset({'pink','orange'}):28, frozenset({'red','pink'}):32,
        frozenset({'green','blue'}):32, frozenset({'blue','green'}):32,
        frozenset({'yellow','green'}):38, frozenset({'purple','green'}):25,
        frozenset({'teal','orange'}):35, frozenset({'red','orange'}):38,
        frozenset({'coral','red'}):38,
    }
    GOOD = {
        frozenset({'navy','white'}):97, frozenset({'black','white'}):97,
        frozenset({'black','red'}):88,  frozenset({'white','red'}):88,
        frozenset({'navy','grey'}):93,  frozenset({'blue','white'}):93,
        frozenset({'beige','navy'}):92, frozenset({'olive','brown'}):88,
        frozenset({'olive','beige'}):87,frozenset({'olive','cream'}):87,
        frozenset({'burgundy','navy'}):85,frozenset({'burgundy','grey'}):83,
        frozenset({'maroon','beige'}):84,frozenset({'grey','blue'}):82,
        frozenset({'beige','brown'}):86,frozenset({'cream','brown'}):85,
        frozenset({'black','grey'}):88, frozenset({'navy','red'}):80,
        frozenset({'white','green'}):82,frozenset({'teal','white'}):86,
        frozenset({'teal','navy'}):82,  frozenset({'pink','grey'}):82,
        frozenset({'pink','white'}):85, frozenset({'yellow','navy'}):78,
        frozenset({'coral','white'}):84,frozenset({'lavender','grey'}):83,
        frozenset({'lavender','white'}):85,frozenset({'rust','olive'}):84,
        frozenset({'rust','navy'}):80,  frozenset({'rust','cream'}):84,
        frozenset({'brown','cream'}):86,frozenset({'charcoal','white'}):92,
        frozenset({'charcoal','red'}):82,frozenset({'black','navy'}):75,
    }
    HUE = {'red':0,'coral':16,'orange':30,'yellow':60,'lime':80,'olive':80,
           'green':120,'teal':170,'blue':215,'navy':225,'purple':270,
           'lavender':275,'pink':330,'maroon':5,'burgundy':345,'rust':15,
           'brown':20,'camel':35,'tan':38}
    SAT = {'red':.9,'coral':.7,'orange':.85,'yellow':.9,'lime':.95,'green':.85,
           'teal':.65,'blue':.8,'navy':.7,'purple':.8,'lavender':.4,'pink':.5,
           'maroon':.7,'burgundy':.65,'rust':.65,'brown':.5,'olive':.5,
           'camel':.35,'tan':.3,'beige':.2,'cream':.15,'grey':0.,'charcoal':.05,
           'black':0.,'white':0.}

    @classmethod
    def label(cls, sc):
        if sc >= 92: return 'Iconic Pairing'
        if sc >= 85: return 'Great Match'
        if sc >= 78: return 'Good Pairing'
        if sc >= 68: return 'Neutral / Safe'
        if sc >= 50: return 'Bold — Style Carefully'
        if sc >= 30: return 'Risky Combination'
        return 'Fashion Clash'

    @classmethod
    def score_rgb(cls, rgb1, rgb2):
        r1,g1,b1 = [x/255 for x in rgb1]
        r2,g2,b2 = [x/255 for x in rgb2]
        h1,s1,v1 = colorsys.rgb_to_hsv(r1,g1,b1)
        h2,s2,v2 = colorsys.rgb_to_hsv(r2,g2,b2)
        n1 = _rgb_to_name(int(rgb1[0]),int(rgb1[1]),int(rgb1[2]))
        n2 = _rgb_to_name(int(rgb2[0]),int(rgb2[1]),int(rgb2[2]))
        pair = frozenset({n1,n2})
        if pair in cls.GOOD:  sc=cls.GOOD[pair];  return sc,cls.label(sc),'Iconic pairing'
        if pair in cls.CLASH: sc=cls.CLASH[pair]; return sc,cls.label(sc),'Known fashion clash'
        nn1 = n1 in cls.NEUTRALS or n1 in cls.NEAR_NEUTRALS
        nn2 = n2 in cls.NEUTRALS or n2 in cls.NEAR_NEUTRALS
        if nn1 and nn2: return 88,'Tonal Pairing','Both neutrals'
        if nn1 or nn2:  return 90,'Neutral Anchor','Neutral grounds the look'
        diff = abs(h1*360 - h2*360)
        if diff > 180: diff = 360 - diff
        avg_sat = (s1+s2)/2
        if diff < 20:  return round(85+(1-avg_sat)*10),'Monochromatic','Same colour family'
        if diff < 50:  return round(80+(1-avg_sat)*8),'Analogous','Close hues blend'
        if 150 <= diff <= 210:
            if avg_sat > .65: return max(15,40-int((avg_sat-.65)*100)),'Vivid Clash','Highly saturated opposites clash'
            if avg_sat > .40: return 55+int((.65-avg_sat)*50),'Bold Contrast','Works if styled intentionally'
            return round(min(72+int((.40-avg_sat)*40),84)),'Muted Complement','Toned opposites can work'
        if 90 <= diff < 150 or 210 < diff <= 270:
            sc = 35 if avg_sat>.70 else (58 if avg_sat>.45 else 72)
            return sc,'Triadic / Split','Needs one muted anchor'
        sc = 35 if avg_sat>.70 else 62
        return sc,'Moderate Match','Hue conflict'

    @classmethod
    def score_names(cls, c1, c2):
        c1,c2 = c1.lower().strip(), c2.lower().strip()
        pair = frozenset({c1,c2})
        if pair in cls.GOOD:  return cls.GOOD[pair]
        if pair in cls.CLASH: return cls.CLASH[pair]
        n1 = c1 in cls.NEUTRALS or c1 in cls.NEAR_NEUTRALS
        n2 = c2 in cls.NEUTRALS or c2 in cls.NEAR_NEUTRALS
        if n1 and n2: return 87
        if n1 or n2:  return 90
        h1 = cls.HUE.get(c1); h2 = cls.HUE.get(c2)
        if h1 is None or h2 is None: return 65
        s1 = cls.SAT.get(c1,.6); s2 = cls.SAT.get(c2,.6); avg = (s1+s2)/2
        diff = abs(h1-h2)
        if diff > 180: diff = 360-diff
        if diff < 20:  return round(85+(1-avg)*10)
        if diff < 50:  return round(78+(1-avg)*8)
        if 150<=diff<=210:
            if avg>.65: return max(15,40-int((avg-.65)*100))
            if avg>.40: return 55+int((.65-avg)*50)
            return round(min(74+int((.40-avg)*40),82))
        if 90<=diff<150: return 35 if avg>.70 else (58 if avg>.45 else 70)
        return 60

    @classmethod
    def score(cls, item1, item2):
        rgb1 = _item_rgb(item1)
        rgb2 = _item_rgb(item2)
        if rgb1 and rgb2:
            return cls.score_rgb(rgb1, rgb2)
        c1 = _color_name(item1)
        c2 = _color_name(item2)
        sc = cls.score_names(c1, c2)
        return sc, cls.label(sc), 'Name-based estimate'

def _item_rgb(item):
    if item['color_palette']:
        try:
            p = json.loads(item['color_palette'])
            if p and 'rgb' in p[0]:
                return tuple(p[0]['rgb'])
        except Exception:
            pass
    return None

def _color_name(item):
    if item['color_palette']:
        try:
            p = json.loads(item['color_palette'])
            if p:
                return p[0].get('name', 'neutral')
        except Exception:
            pass
    return (item['color_rgb'] or 'neutral').lower()

# ─── SKIN TONE ENGINE ─────────────────────────────────────────────────────────

class SkinToneEngine:
    TONES = {
        'fair': {
            'label':       'Fair / Light',
            'description': 'Cool or neutral undertones with light pink or peach skin.',
            'tip':         'Jewel tones and rich deep colours pop against fair skin. Avoid colours too close to your skin tone.',
            'palette_hex': '#f5d5b8',
            'best': ['navy','blue','burgundy','maroon','green','purple','lavender',
                     'teal','black','charcoal','white','coral','red'],
        },
        'light': {
            'label':       'Light / Warm',
            'description': 'Warm golden or peachy undertones with light to medium skin.',
            'tip':         'Earth tones and warm colours are your best friend. Warm whites look better than stark white.',
            'palette_hex': '#e8b895',
            'best': ['olive','brown','rust','camel','coral','orange','cream',
                     'burgundy','navy','maroon','teal','green','yellow'],
        },
        'medium': {
            'label':       'Medium / Olive',
            'description': 'Warm olive or golden-brown undertones.',
            'tip':         'You can carry bold and earthy tones equally well. Bright jewel tones are especially striking.',
            'palette_hex': '#c68642',
            'best': ['olive','rust','camel','burgundy','navy','teal','coral',
                     'orange','white','black','green','blue'],
        },
        'tan': {
            'label':       'Tan / Brown',
            'description': 'Warm medium-to-deep brown skin with rich undertones.',
            'tip':         'Bold and vibrant colours look amazing on you. White and bright colours create stunning contrast.',
            'palette_hex': '#8d5524',
            'best': ['white','ivory','yellow','orange','red','coral','blue',
                     'navy','green','purple','gold','teal','black'],
        },
        'deep': {
            'label':       'Deep / Rich',
            'description': 'Deep brown to ebony skin with warm or cool undertones.',
            'tip':         'Bold vivid colours and bright whites are stunning. Avoid very dark shades that reduce contrast.',
            'palette_hex': '#3b1505',
            'best': ['white','yellow','orange','red','blue','green','purple',
                     'coral','pink','teal','navy'],
        },
    }

    TONE_BEST = {
        'fair':   ['navy','blue','burgundy','maroon','green','purple','lavender','teal','black','charcoal','white','coral','red'],
        'light':  ['olive','brown','rust','camel','coral','orange','cream','burgundy','navy','maroon','teal','green','yellow'],
        'medium': ['olive','rust','camel','burgundy','navy','teal','coral','orange','white','black','green','blue'],
        'tan':    ['white','ivory','yellow','orange','red','coral','blue','navy','green','purple','gold','teal','black'],
        'deep':   ['white','yellow','orange','red','blue','green','purple','coral','pink','teal','navy'],
    }

    @classmethod
    def classify(cls, r, g, b):
        lum = (0.299*r + 0.587*g + 0.114*b) / 255
        if lum > 0.80: return 'fair'
        if lum > 0.65: return 'light'
        if lum > 0.48: return 'medium'
        if lum > 0.28: return 'tan'
        return 'deep'

    @classmethod
    def score_item_for_tone(cls, item, tone):
        item_col = _color_name(item).lower().strip()
        best     = cls.TONE_BEST.get(tone, [])
        if item_col in best:
            return 95
        for bc in best:
            if bc in item_col or item_col in bc:
                return 88
        if item_col in FCE.NEUTRALS:   return 78
        if item_col in FCE.NEAR_NEUTRALS: return 72
        if best:
            return round(max(FCE.score_names(item_col, bc) for bc in best[:6]) * 0.85)
        return 60

    @classmethod
    def suggest_outfits(cls, user_id, tone):
        tops    = qdb("SELECT * FROM clothing_items WHERE user_id=? AND wear_type='top'",    (user_id,))
        bottoms = qdb("SELECT * FROM clothing_items WHERE user_id=? AND wear_type='bottom'", (user_id,))
        if not tops or not bottoms:
            return []
        pairs = []
        seen  = set()
        for top in tops:
            for bot in bottoms:
                key = (top['item_id'], bot['item_id'])
                if key in seen: continue
                seen.add(key)
                cs, hlbl, _ = FCE.score(top, bot)
                if cs < 40: continue
                top_st   = cls.score_item_for_tone(top, tone)
                bot_st   = cls.score_item_for_tone(bot, tone)
                skin_avg = (top_st + bot_st) / 2
                final    = skin_avg * 0.60 + cs * 0.40
                pairs.append({
                    'top':            dict(top),
                    'bottom':         dict(bot),
                    'color_harmony':  round(cs),
                    'harmony_type':   hlbl,
                    'skin_score':     round(skin_avg),
                    'top_skin_score': round(top_st),
                    'bot_skin_score': round(bot_st),
                    'score':          final,
                })
        pairs.sort(key=lambda x: x['score'], reverse=True)
        return pairs[:6]

# ─── USER PREFERENCE MODEL ────────────────────────────────────────────────────

class UserPreferenceModel:
    @classmethod
    def build(cls, user_id):
        rows = qdb(
            "SELECT top_id,bottom_id,feedback_type,harmony_type "
            "FROM outfit_feedback WHERE user_id=? ORDER BY created_at DESC LIMIT 200",
            (user_id,))
        empty = {'liked_ids':set(),'disliked_ids':set(),
                 'liked_categories':{},'disliked_categories':{},
                 'liked_harmony':{},'liked_colors':{}}
        if not rows:
            return empty
        liked_ids=set(); disliked_ids=set()
        liked_cat={}; disliked_cat={}; liked_harm={}; liked_col={}
        for row in rows:
            is_like = row['feedback_type'] == 'like'
            for iid in [row['top_id'], row['bottom_id']]:
                if not iid: continue
                if is_like: liked_ids.add(iid)
                else:       disliked_ids.add(iid)
                item = qdb("SELECT category,color_palette,color_rgb FROM clothing_items WHERE item_id=?", (iid,), one=True)
                if item:
                    cat = (item['category'] or '').strip()
                    if cat:
                        d = liked_cat if is_like else disliked_cat
                        d[cat] = d.get(cat,0) + 1
                    if is_like:
                        col = _color_name(item)
                        if col and col != 'neutral':
                            liked_col[col] = liked_col.get(col,0) + 1
            if is_like and row['harmony_type']:
                ht = row['harmony_type']
                liked_harm[ht] = liked_harm.get(ht,0) + 1
        return {'liked_ids':liked_ids,'disliked_ids':disliked_ids,
                'liked_categories':liked_cat,'disliked_categories':disliked_cat,
                'liked_harmony':liked_harm,'liked_colors':liked_col}

    @classmethod
    def score_pair(cls, prefs, top, bot, harmony_type):
        boost = 0.0
        tid = top['item_id']; bid = bot['item_id']
        if tid in prefs['liked_ids']:    boost += 8
        if bid in prefs['liked_ids']:    boost += 8
        if tid in prefs['disliked_ids']: boost -= 14
        if bid in prefs['disliked_ids']: boost -= 14
        total_cat = sum(prefs['liked_categories'].values()) or 1
        tc = (top['category'] or '').strip()
        bc = (bot['category'] or '').strip()
        if tc and tc in prefs['liked_categories']:
            boost += 6*(prefs['liked_categories'][tc]/total_cat)
        if bc and bc in prefs['liked_categories']:
            boost += 6*(prefs['liked_categories'][bc]/total_cat)
        dis_total = sum(prefs['disliked_categories'].values()) or 1
        if tc and tc in prefs['disliked_categories']:
            boost -= 8*(prefs['disliked_categories'][tc]/dis_total)
        if bc and bc in prefs['disliked_categories']:
            boost -= 8*(prefs['disliked_categories'][bc]/dis_total)
        total_harm = sum(prefs['liked_harmony'].values()) or 1
        if harmony_type in prefs['liked_harmony']:
            boost += 5*(prefs['liked_harmony'][harmony_type]/total_harm)
        total_col = sum(prefs['liked_colors'].values()) or 1
        tcol = _color_name(top); bcol = _color_name(bot)
        if tcol in prefs['liked_colors']:
            boost += 4*(prefs['liked_colors'][tcol]/total_col)
        if bcol in prefs['liked_colors']:
            boost += 4*(prefs['liked_colors'][bcol]/total_col)
        return boost

# ─── RECOMMENDATION ENGINE ───────────────────────────────────────────────────

class RE:
    OCC = {
        'casual':     ['casual','t-shirt','jeans','shorts','sneakers'],
        'office':     ['formal','business','shirt','trousers','blazer'],
        'party':      ['party','evening','dress','cocktail'],
        'date':       ['smart casual','date','romantic','dinner'],
        'gym':        ['gym','workout','sports','athleisure','yoga'],
        'wedding':    ['formal','elegant','wedding','suit','ethnic'],
        'travel':     ['comfortable','travel','casual'],
        'traditional':['ethnic','traditional','festival','cultural'],
        'beach':      ['beach','summer','light','casual'],
    }
    WX = {
        'freezing':['coat','jacket','sweater','thermal','wool'],
        'cold':    ['jacket','sweater','hoodie','long sleeve'],
        'mild':    ['light jacket','long sleeve','jeans','chinos'],
        'warm':    ['t-shirt','shirt','chinos','light','linen'],
        'hot':     ['shorts','sleeveless','linen','light','tank'],
    }

    @staticmethod
    def wcat(t):
        if t <= 5:  return 'freezing'
        if t <= 15: return 'cold'
        if t <= 22: return 'mild'
        if t <= 30: return 'warm'
        return 'hot'

    @classmethod
    def wscore(cls, item, temp):
        txt = '{} {} {}'.format(item['name'], item['category'] or '', item['occasions'] or '').lower()
        if item['temp_min'] is not None and item['temp_max'] is not None:
            lo, hi = item['temp_min'], item['temp_max']
            sc = 100 if lo<=temp<=hi else (70 if abs(lo-temp)<=5 or abs(hi-temp)<=5 else 20)
        else:
            COLD_KW = ['coat','jacket','blazer','sweater','hoodie','wool','puffer','thermal','knit']
            HOT_KW  = ['shorts','sleeveless','tank','crop','linen','tee','t-shirt']
            is_cold = any(k in txt for k in COLD_KW)
            is_hot  = any(k in txt for k in HOT_KW)
            wcat = cls.wcat(temp)
            if is_cold and not is_hot:
                sc = 90 if wcat in ('freezing','cold') else (70 if wcat=='mild' else (40 if wcat=='warm' else 20))
            elif is_hot and not is_cold:
                sc = 90 if wcat=='hot' else (80 if wcat=='warm' else (60 if wcat=='mild' else 30))
            else:
                sc = 75 if wcat in ('mild','warm') else (65 if wcat in ('cold','hot') else 50)
        for kw in cls.WX.get(cls.wcat(temp), []):
            if kw in txt: sc = min(100, sc+8)
        return sc

    @classmethod
    def oscore(cls, item, occ):
        txt = '{} {} {}'.format(item['name'], item['category'] or '', item['occasions'] or '').lower()
        if not occ:
            if item['occasions']:
                tagged = [o.strip() for o in item['occasions'].split(',') if o.strip()]
                return min(85, 60 + len(tagged)*6)
            FORMAL = ['blazer','suit','shirt','trousers','chinos']
            CASUAL = ['tee','t-shirt','jeans','shorts','hoodie']
            SPORT  = ['gym','track','yoga','sports','leggings']
            if any(k in txt for k in FORMAL): return 72
            if any(k in txt for k in CASUAL): return 68
            if any(k in txt for k in SPORT):  return 65
            return 65
        sc = 40
        for kw in cls.OCC.get(occ.lower(), []):
            if kw in txt: sc += 15
        if item['occasions']:
            if occ.lower() in [o.strip().lower() for o in item['occasions'].split(',')]:
                sc += 30
        return min(100, sc)

    @classmethod
    def recommend(cls, user_id, temp=22, occasion=None, color_pref=None, limit=6):
        tops    = qdb("SELECT * FROM clothing_items WHERE user_id=? AND wear_type='top'",    (user_id,))
        bottoms = qdb("SELECT * FROM clothing_items WHERE user_id=? AND wear_type='bottom'", (user_id,))
        if not tops or not bottoms:
            return []

        user_row  = qdb("SELECT skin_tone FROM users WHERE user_id=?", (user_id,), one=True)
        skin_tone = user_row['skin_tone'] if user_row and user_row['skin_tone'] else None
        prefs     = UserPreferenceModel.build(user_id)
        favs      = {(r['top_id'], r['bottom_id'])
                     for r in qdb("SELECT top_id,bottom_id FROM favourite_outfits WHERE user_id=?", (user_id,))}

        scored = []
        for top in tops:
            for bot in bottoms:
                ws  = (cls.wscore(top,temp) + cls.wscore(bot,temp)) / 2
                os_ = (cls.oscore(top,occasion) + cls.oscore(bot,occasion)) / 2
                cs, hlbl, hreason = FCE.score(top, bot)
                tc = _color_name(top); bc = _color_name(bot)

                if skin_tone:
                    top_st   = SkinToneEngine.score_item_for_tone(top, skin_tone)
                    bot_st   = SkinToneEngine.score_item_for_tone(bot, skin_tone)
                    st_score = (top_st + bot_st) / 2
                else:
                    st_score = 70

                pb = UserPreferenceModel.score_pair(prefs, top, bot, hlbl)
                cp = 10 if color_pref and cs >= 50 and (color_pref.lower() in tc or color_pref.lower() in bc) else 0
                clash_penalty = max(0, (35-cs)*0.8) if cs < 35 else 0

                if skin_tone:
                    final = ws*.30 + os_*.25 + cs*.22 + st_score*.18 + cp*.05 + pb - clash_penalty
                else:
                    final = ws*.35 + os_*.27 + cs*.28 + cp*.10 + pb - clash_penalty

                scored.append({
                    'top':             dict(top), 'bottom':          dict(bot),
                    'score':           final,
                    'weather_score':   round(ws),
                    'occasion_match':  round(os_),
                    'color_harmony':   round(cs),
                    'skin_score':      round(st_score) if skin_tone else None,
                    'harmony_type':    hlbl,
                    'harmony_reason':  hreason,
                    'top_color':       tc, 'bottom_color':    bc,
                    'is_clash':        cs < 40,
                    'is_favourite':    (top['item_id'], bot['item_id']) in favs,
                    'skin_tone_active': skin_tone is not None,
                })

        good = sorted([o for o in scored if not o['is_clash']], key=lambda x: x['score'], reverse=True)
        if not good:
            good = sorted(scored, key=lambda x: x['score'], reverse=True)
        return good[:limit]

RecommendationEngine = RE  # alias

# ─── WEATHER ──────────────────────────────────────────────────────────────────

def get_weather(city=None, lat=None, lon=None):
    if not WEATHER_KEY or WEATHER_KEY == '':
        return None
    try:
        if lat and lon:
            url = 'https://api.openweathermap.org/data/2.5/weather?lat={}&lon={}&appid={}&units=metric'.format(lat, lon, WEATHER_KEY)
        elif city:
            url = 'https://api.openweathermap.org/data/2.5/weather?q={}&appid={}&units=metric'.format(city, WEATHER_KEY)
        else:
            return None
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            d = r.json()
            return {
                'temp':        round(d['main']['temp']),
                'feels_like':  round(d['main']['feels_like']),
                'humidity':    d['main']['humidity'],
                'description': d['weather'][0]['description'].title(),
                'city':        d['name'],
                'country':     d['sys']['country'],
                'wind_speed':  round(d['wind']['speed'] * 3.6, 1),
                'condition':   d['weather'][0]['main'].lower(),
            }
    except Exception as e:
        print('Weather error:', e)
    return None

def outfit_tip(w):
    if not w:
        return 'Check the weather before stepping out!'
    t = w['temp']; c = w.get('condition', '')
    if t <= 5:    tip = 'Bundle up — thermal base, heavy sweater and a warm coat.'
    elif t <= 15: tip = 'Cool outside — a jacket or sweater works perfectly.'
    elif t <= 22: tip = 'Mild and pleasant. Long sleeves or a light layer will do.'
    elif t <= 28: tip = 'Warm day — light breathable fabrics are your best friend.'
    else:         tip = 'Hot day! Go for airy fabrics like linen or cotton.'
    if 'rain' in c:                    tip += " Don't forget a waterproof layer!"
    if 'snow' in c:                    tip += ' Waterproof boots essential today.'
    if w.get('wind_speed', 0) > 30:    tip += " It's windy — avoid loose flowy garments."
    return tip

# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('dashboard')) if 'user_id' in session else render_template('landing.html')

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'register':
            un = request.form.get('username', '').strip()
            em = request.form.get('email', '').strip().lower()
            pw = request.form.get('password', '')
            gn = request.form.get('gender', 'prefer_not_to_say')
            ct = request.form.get('city', '').strip()
            if not all([un, em, pw]):
                flash('Please fill in all required fields.', 'error')
                return render_template('auth.html', tab='register')
            if len(pw) < 6:
                flash('Password must be at least 6 characters.', 'error')
                return render_template('auth.html', tab='register')
            if qdb("SELECT user_id FROM users WHERE email=?", (em,), one=True):
                flash('Email already registered.', 'error')
                return render_template('auth.html', tab='register')
            h   = hashlib.sha256(pw.encode()).hexdigest()
            uid = xdb("INSERT INTO users(username,email,password_hash,gender,city) VALUES(?,?,?,?,?)", (un,em,h,gn,ct))
            session.update({'user_id':uid,'username':un,'gender':gn,'city':ct,'skin_tone':''})
            flash('Welcome to DressWell, {}!'.format(un), 'success')
            return redirect(url_for('dashboard'))
        elif action == 'login':
            em = request.form.get('email', '').strip().lower()
            pw = request.form.get('password', '')
            h  = hashlib.sha256(pw.encode()).hexdigest()
            u  = qdb("SELECT * FROM users WHERE email=? AND password_hash=?", (em, h), one=True)
            if u:
                session.update({'user_id':u['user_id'],'username':u['username'],
                                'gender':u['gender'] or 'other','city':u['city'] or '',
                                'skin_tone':u['skin_tone'] or ''})
                flash('Welcome back, {}!'.format(u['username']), 'success')
                return redirect(url_for('dashboard'))
            flash('Invalid email or password.', 'error')
    return render_template('auth.html', tab=request.args.get('tab', 'login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    uid = session['user_id']
    w   = get_weather(city=session.get('city', '')) if session.get('city') else None
    t   = w['temp'] if w else 22
    _tc = qdb("SELECT COUNT(*) c FROM clothing_items WHERE user_id=? AND wear_type='top'",    (uid,), one=True)
    _bc = qdb("SELECT COUNT(*) c FROM clothing_items WHERE user_id=? AND wear_type='bottom'", (uid,), one=True)
    _fc = qdb("SELECT COUNT(*) c FROM favourite_outfits WHERE user_id=?",                     (uid,), one=True)
    tc  = _tc['c'] if _tc else 0
    bc  = _bc['c'] if _bc else 0
    fc  = _fc['c'] if _fc else 0
    recs   = RE.recommend(uid, temp=t, limit=3)
    recent = qdb("SELECT * FROM clothing_items WHERE user_id=? ORDER BY item_id DESC LIMIT 4", (uid,))
    skin_tone = session.get('skin_tone') or ''
    if not skin_tone:
        row = qdb("SELECT skin_tone FROM users WHERE user_id=?", (uid,), one=True)
        skin_tone = row['skin_tone'] if row and row['skin_tone'] else ''
    tone_meta = SkinToneEngine.TONES.get(skin_tone, {}) if skin_tone else {}
    return render_template('dashboard.html',
        weather=w, outfit_tip=outfit_tip(w),
        recommendations=recs, tops_count=tc, bottoms_count=bc, favourites_count=fc,
        recent_items=recent, now_hour=datetime.now(tz=IST).hour,
        skin_tone=skin_tone, tone_meta=tone_meta)

@app.route('/wardrobe')
@login_required
def wardrobe():
    uid     = session['user_id']
    tops    = qdb("SELECT * FROM clothing_items WHERE user_id=? AND wear_type='top'    ORDER BY item_id DESC", (uid,))
    bottoms = qdb("SELECT * FROM clothing_items WHERE user_id=? AND wear_type='bottom' ORDER BY item_id DESC", (uid,))
    return render_template('wardrobe.html', tops=tops, bottoms=bottoms)

@app.route('/wardrobe/add', methods=['POST'])
@login_required
def add_item():
    uid      = session['user_id']
    name     = request.form.get('name', '').strip()
    wtype    = request.form.get('wear_type', 'top')
    category = request.form.get('category', '').strip()
    color    = request.form.get('color', '').strip()
    occasions= request.form.get('occasions', '').strip()
    tmin     = request.form.get('temp_min', type=int)
    tmax     = request.form.get('temp_max', type=int)
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    img_path = pal_json = None
    f = request.files.get('photo')
    if f and f.filename:
        img_path = save_image(f, uid)
        if img_path:
            cols     = extract_dominant_colors(os.path.join(BASE_DIR, 'static', img_path), k=5)
            pal_json = json.dumps(cols)
            if not color and cols:
                color = cols[0]['name']
    iid = xdb(
        "INSERT INTO clothing_items(user_id,name,wear_type,category,color_rgb,occasions,temp_min,temp_max,image_path,color_palette) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (uid, name, wtype, category, color, occasions, tmin, tmax, img_path, pal_json))
    return jsonify({'success': True, 'message': '{} added!'.format(name), 'item_id': iid,
                    'image_path': img_path, 'palette': json.loads(pal_json) if pal_json else []})

@app.route('/wardrobe/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    uid  = session['user_id']
    item = qdb("SELECT image_path FROM clothing_items WHERE item_id=? AND user_id=?", (item_id, uid), one=True)
    if item and item['image_path']:
        try:
            os.remove(os.path.join(BASE_DIR, 'static', item['image_path']))
        except Exception:
            pass
    xdb("DELETE FROM clothing_items   WHERE item_id=? AND user_id=?", (item_id, uid))
    xdb("DELETE FROM favourite_outfits WHERE (top_id=? OR bottom_id=?) AND user_id=?", (item_id, item_id, uid))
    return jsonify({'success': True})

@app.route('/outfit-wheel')
@login_required
def outfit_wheel():
    return render_template('outfit_wheel.html')

@app.route('/recommendations')
@login_required
def recommendations():
    uid     = session['user_id']
    w       = get_weather(city=session.get('city', '')) if session.get('city') else None
    t       = w['temp'] if w else 22
    occ     = request.args.get('occasion')
    col     = request.args.get('color')
    outfits = RE.recommend(uid, temp=t, occasion=occ, color_pref=col, limit=9)
    return render_template('recommendations.html', outfits=outfits, weather=w, occasion=occ, color=col)

@app.route('/favourites')
@login_required
def favourites():
    uid  = session['user_id']
    rows = qdb("""
        SELECT f.favourite_id, f.created_at,
               t.item_id top_id, t.name top_name, t.category top_cat,
               t.image_path top_img, t.color_palette top_pal, t.color_rgb top_color,
               b.item_id bot_id, b.name bot_name, b.category bot_cat,
               b.image_path bot_img, b.color_palette bot_pal, b.color_rgb bot_color
        FROM favourite_outfits f
        JOIN clothing_items t ON f.top_id    = t.item_id
        JOIN clothing_items b ON f.bottom_id = b.item_id
        WHERE f.user_id=? ORDER BY f.created_at DESC
    """, (uid,))
    outfits = []
    for r in rows:
        ti = {'color_palette': r['top_pal'], 'color_rgb': r['top_color']}
        bi = {'color_palette': r['bot_pal'], 'color_rgb': r['bot_color']}
        cs, hlbl, _ = FCE.score(ti, bi)
        outfits.append({
            'favourite_id': r['favourite_id'],
            'created_at':   r['created_at'],
            'top':    {'item_id':r['top_id'],'name':r['top_name'],'category':r['top_cat'],
                       'image_path':r['top_img'],'color_palette':r['top_pal'],'color_rgb':r['top_color']},
            'bottom': {'item_id':r['bot_id'],'name':r['bot_name'],'category':r['bot_cat'],
                       'image_path':r['bot_img'],'color_palette':r['bot_pal'],'color_rgb':r['bot_color']},
            'color_harmony': round(cs), 'harmony_type': hlbl,
        })
    return render_template('favourites.html', outfits=outfits)

@app.route('/camera-scan')
@login_required
def camera_scan():
    return render_template('camera_scan.html')

# ─── API ──────────────────────────────────────────────────────────────────────

@app.route('/api/weather')
@login_required
def api_weather():
    lat  = request.args.get('lat')
    lon  = request.args.get('lon')
    city = request.args.get('city') or session.get('city')
    w    = get_weather(city=city, lat=lat, lon=lon)
    if w:
        session['city'] = w['city']
        xdb("UPDATE users SET city=? WHERE user_id=?", (w['city'], session['user_id']))
        return jsonify({'success': True, 'weather': w, 'tip': outfit_tip(w)})
    return jsonify({'success': False, 'error': 'Could not fetch weather'}), 400

@app.route('/api/feedback', methods=['POST'])
@login_required
def api_feedback():
    uid  = session['user_id']
    data = request.get_json()
    top_id  = data.get('top_id')
    bot_id  = data.get('bottom_id')
    ftype   = data.get('feedback_type', 'like')
    harmony = data.get('harmony_type', '')
    if not top_id or not bot_id:
        return jsonify({'success': False, 'error': 'top_id and bottom_id required'}), 400
    try:
        top_id, bot_id = int(top_id), int(bot_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid IDs'}), 400
    existing = qdb(
        "SELECT feedback_id FROM outfit_feedback WHERE user_id=? AND top_id=? AND bottom_id=?",
        (uid, top_id, bot_id), one=True)
    if existing:
        xdb("UPDATE outfit_feedback SET feedback_type=?,created_at=CURRENT_TIMESTAMP WHERE feedback_id=?",
            (ftype, existing['feedback_id']))
    else:
        xdb("INSERT INTO outfit_feedback(user_id,top_id,bottom_id,item_ids,feedback_type,harmony_type) VALUES(?,?,?,?,?,?)",
            (uid, top_id, bot_id, json.dumps([top_id, bot_id]), ftype, harmony))
    msg = "Loved! We'll suggest this style more." if ftype == 'like' else "Got it — we'll adjust your feed."
    return jsonify({'success': True, 'message': msg})

@app.route('/api/toggle-favourite', methods=['POST'])
@login_required
def toggle_favourite():
    uid  = session['user_id']
    data = request.get_json()
    top_id = data.get('top_id')
    bot_id = data.get('bottom_id')
    if not top_id or not bot_id:
        return jsonify({'success': False, 'error': 'IDs required'}), 400
    try:
        top_id, bot_id = int(top_id), int(bot_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid IDs'}), 400
    existing = qdb(
        "SELECT favourite_id FROM favourite_outfits WHERE user_id=? AND top_id=? AND bottom_id=?",
        (uid, top_id, bot_id), one=True)
    if existing:
        xdb("DELETE FROM favourite_outfits WHERE favourite_id=?", (existing['favourite_id'],))
        return jsonify({'success': True, 'favourited': False, 'message': 'Removed from favourites'})
    xdb("INSERT OR IGNORE INTO favourite_outfits(user_id,top_id,bottom_id) VALUES(?,?,?)", (uid, top_id, bot_id))
    return jsonify({'success': True, 'favourited': True, 'message': 'Added to favourites!'})

@app.route('/api/remove-favourite/<int:fav_id>', methods=['POST'])
@login_required
def remove_favourite(fav_id):
    xdb("DELETE FROM favourite_outfits WHERE favourite_id=? AND user_id=?", (fav_id, session['user_id']))
    return jsonify({'success': True})

@app.route('/api/spin-wheel', methods=['POST'])
@login_required
def spin_wheel():
    uid  = session['user_id']
    data = request.get_json()
    occ  = data.get('occasion')
    col  = data.get('color')
    w    = get_weather(city=session.get('city', '')) if session.get('city') else None
    t    = w['temp'] if w else 22
    outs = RE.recommend(uid, temp=t, occasion=occ, color_pref=col, limit=1)
    if outs:
        o = outs[0]
        parts = []
        if w:   parts.append('Perfect for {}°C weather.'.format(w['temp']))
        if occ: parts.append('Great for a {} look.'.format(occ))
        parts.append('{} — {}% harmony.'.format(o['harmony_type'], o['color_harmony']))
        return jsonify({'success': True, 'outfit': o, 'tip': ' '.join(parts)})
    g = _generic(occ)
    return jsonify({'success': True, 'outfit': None, 'generic': g, 'tip': g['tip']})

def _generic(occ):
    m = {
        'casual':      {'top':'Graphic Tee',         'bottom':'Slim Fit Jeans',        'tip':'Effortlessly cool.'},
        'office':      {'top':'Fitted Dress Shirt',   'bottom':'Tailored Trousers',     'tip':'Sharp and professional.'},
        'party':       {'top':'Printed Shirt',        'bottom':'Slim Trousers',         'tip':'Let the night begin!'},
        'date':        {'top':'Smart Polo',           'bottom':'Chinos',                'tip':'Look great, effortlessly.'},
        'gym':         {'top':'Dry-fit Tee',          'bottom':'Track Pants',           'tip':'Comfort meets performance.'},
        'wedding':     {'top':'Blazer / Sherwani',    'bottom':'Dress Trousers',        'tip':'Occasion dressing at its finest.'},
        'beach':       {'top':'Floral Shirt',         'bottom':'Board Shorts',          'tip':'Sun, sand, and style!'},
        'traditional': {'top':'Kurta',                'bottom':'Churidar / Lehenga',    'tip':'Cultural elegance.'},
    }
    return m.get((occ or '').lower(), {'top':'Classic Tee', 'bottom':'Jeans', 'tip':'A timeless look.'})

@app.route('/api/save-outfit', methods=['POST'])
@login_required
def save_outfit():
    uid  = session['user_id']
    data = request.get_json()
    xdb("INSERT INTO saved_outfits(user_id,items) VALUES(?,?)", (uid, json.dumps(data.get('items', []))))
    return jsonify({'success': True, 'message': 'Outfit saved!'})

@app.route('/api/scan-skin', methods=['POST'])
@login_required
def scan_skin():
    uid  = session['user_id']
    data = request.get_json() or {}
    try:
        r = max(0, min(255, int(data.get('r', 200))))
        g = max(0, min(255, int(data.get('g', 160))))
        b = max(0, min(255, int(data.get('b', 120))))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid RGB values'}), 400

    tone    = SkinToneEngine.classify(r, g, b)
    outfits = SkinToneEngine.suggest_outfits(uid, tone)

    # Save to profile
    xdb("UPDATE users SET skin_tone=? WHERE user_id=?", (tone, uid))
    session['skin_tone'] = tone

    tone_data = SkinToneEngine.TONES.get(tone, {})
    return jsonify({
        'success':          True,
        'tone':             tone,
        'skin_hex':         '#{:02x}{:02x}{:02x}'.format(r, g, b),
        'tone_label':       tone_data.get('label', ''),
        'tone_description': tone_data.get('description', ''),
        'tone_tip':         tone_data.get('tip', ''),
        'palette_hex':      tone_data.get('palette_hex', '#c68642'),
        'outfits':          outfits,
        'saved':            True,
    })

@app.route('/api/scan-colour', methods=['POST'])
@login_required
def scan_colour():
    return scan_skin()

@app.route('/api/update-profile', methods=['POST'])
@login_required
def update_profile():
    uid  = session['user_id']
    city = (request.get_json() or {}).get('city', '').strip()
    if city:
        session['city'] = city
        xdb("UPDATE users SET city=? WHERE user_id=?", (city, uid))
    return jsonify({'success': True})


if __name__ == '__main__':
    app.run(debug=True)
