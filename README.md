# 🗺️ AI PrettyMap

Szabad szöveges ("chat") utasításokból készít **stílusos térképképeket**. Beírod,
milyen térképet szeretnél ("mutasd Budapestet kék vízzel, négyzet alakban"), egy
**Hugging Face** nyelvi modell ezt térkép-beállításokká alakítja, a
[**prettymapp**](https://github.com/chrieke/prettymapp) pedig kirajzolja.

Ez egy **tanulóprojekt**: azt mutatja be, hogyan lehet egy programban AI-t
használni "értelmező rétegként" — a modell nem képet generál, hanem a szabad
szöveget alakítja géppel végrehajtható paraméterekké.

## Mit tud

- 💬 **Szabad szöveges utasítások** — helyszín, sugár (méret), alak (kör/négyzet),
  színtéma, egyedi rétegszínek (víz, utak, épületek, zöld, erdő, háttér), felirat.
  A modellre nem kell "válaszolni", csak a képet alakítja. Relatív kéréseket is ért
  ("nagyobb legyen", "zoomolj ki", "vedd le a feliratot").
- 🎨 **Színek egy feltöltött képből** — feltöltesz egy fotót, a program kinyeri a
  domináns színeit, és ezeket képezi rá a térkép rétegeire (a legkékebb szín lesz a
  víz, a legsötétebb az utak, stb.).
- ⚠️ **Visszajelzés, ha valamit nem tud** — ha egy kérést nem lehet térképbeállítássá
  alakítani (vagy a helyszín nem található), a program jelzi a beszélgetésben.

## Hogyan működik az AI rész

A `aiprettymap/nlp.py` a [Hugging Face Inference Providers](https://huggingface.co/docs/inference-providers)
szolgáltatáson keresztül hív egy **hosztolt** modellt (alapból
`Qwen/Qwen2.5-7B-Instruct`). Mivel a modell a Hugging Face szerverén fut, **nem kell
erős gép** — elég egy ingyenes API-token. A modell egy kis JSON "patch"-et ad vissza
(csak azok a beállítások, amiket változtatni kell), amit a `schema.py` **validál**,
mielőtt alkalmazzuk — így az AI soha nem állíthat be érvénytelen értéket.

## Gyors indítás (helyben)

```bash
git clone https://github.com/barnabashub/aiprettymap.git
cd aiprettymap
pip install -r requirements.txt

# Hugging Face token (ingyenes): https://huggingface.co/settings/tokens
export HF_TOKEN="hf_..."

streamlit run app.py
```

Nyisd meg a böngészőben: http://localhost:8501

> A tokent nem kötelező környezeti változóként megadni — az appban is beírhatod az
> oldalsávon.

## Futtatás Dockerrel

```bash
docker build -t aiprettymap .
docker run -p 8501:8501 -e HF_TOKEN=hf_... aiprettymap
```

## Ingyenes hosztolás – Streamlit Community Cloud

1. Told fel ezt a repót a GitHubra (publikus is lehet).
2. Menj a [share.streamlit.io](https://share.streamlit.io) oldalra, jelentkezz be
   GitHubbal, és válaszd ki a repót + a `app.py` fájlt.
3. Az **Advanced settings → Secrets** mezőbe írd be:
   ```toml
   HF_TOKEN = "hf_..."
   ```
4. Deploy. Kész, van egy publikus linked, amit meg tudsz osztani.

A prettymapp geo-függőségei (osmnx, geopandas, shapely) manylinux wheelekkel
települnek, ezért Streamlit Cloudon **nincs szükség extra rendszercsomagra**.

## Hugging Face token beszerzése (1 perc)

1. Regisztrálj: https://huggingface.co/join
2. Settings → Access Tokens → **Create new token** → típus: **Fine-grained**.
3. Az **Inference** szekcióban pipáld be: **„Make calls to Inference Providers"**.
   (Ez a lépés a lényeg — enélkül 403-at kapsz!)
4. Create → másold ki (`hf_...`) és add meg az appnak.

> A modell a Hugging Face **Inference Providers** szolgáltatásán fut, amihez a
> tokennek a fenti jogosultság kell. A régi, sima "Read" token ehhez ma már nem elég.

## Hibaelhárítás

| Hiba | Megoldás |
|------|----------|
| **403 / "sufficient permissions"** | A tokennek nincs Inference Providers joga — készíts újat a fenti 3. lépés szerint. |
| **403 továbbra is** | Nézd meg az ingyenes kereted: https://huggingface.co/settings/billing (szöveges értelmezéshez pár kredit elég). |
| **"model_not_supported" / 404** | Az app automatikusan végigpróbál több modellt. Ha mind elbukik: engedélyezz egy (ingyenes) providert a https://huggingface.co/settings/inference-providers oldalon, vagy adj meg konkrét modellt az oldalsávon / `HF_MODEL`-ben. |
| **429 / 503** | A modell épp foglalt — várj pár másodpercet és próbáld újra. |
| **A helyszín nem található** | Adj meg pontosabb címet/várost, vagy nagyobb sugarat. |

## Példa utasítások

- `Mutasd Budapestet, Magyarország`
- `Zoomolj ki egy kicsit és használd az Auburn témát`
- `A víz legyen sötétkék, az utak feketék`
- `Négyzet alak, felirat nélkül`
- `Állítsd vissza a színeket a témára`

## Projektszerkezet

```
aiprettymap/
├── app.py                  # Streamlit felület (chat + térkép + képfeltöltés)
├── aiprettymap/
│   ├── schema.py           # paraméterek, alapértékek, validáció, "apply_changes"
│   ├── nlp.py              # Hugging Face utasításértelmező (szöveg -> JSON patch)
│   ├── colors.py           # domináns színek kinyerése + rétegekre képezése
│   └── mapmaker.py         # állapot -> prettymapp -> matplotlib figura
├── tests/test_logic.py     # hálózat nélküli tesztek a logikára
├── requirements.txt
├── Dockerfile
└── .streamlit/config.toml
```

## Beállítható környezeti változók

| Változó    | Kötelező | Leírás                                              |
|------------|----------|-----------------------------------------------------|
| `HF_TOKEN`    | igen  | Hugging Face access token (Inference Providers joggal). |
| `HF_MODEL`    | nem   | Másik modell (alap: `Qwen/Qwen2.5-7B-Instruct`).        |
| `HF_PROVIDER` | nem   | Konkrét provider (alap: `auto`), pl. `hf-inference`.    |

## Korlátok / megjegyzések

- A térkép adatai az OpenStreetMapből jönnek (osmnx), ezért **internetkapcsolat kell**,
  és nagyon nagy területnél lassabb lehet — a sugár ezért 200–3000 m közé van fogva.
- A modell kimenete néha eltérhet; a validáció miatt a hibás értékeket az app egyszerűen
  kihagyja és jelzi.
- Ez tanulóprojekt, nem éles termék — a token kezelése is a legegyszerűbb módon történik.

## Köszönet

- [prettymapp](https://github.com/chrieke/prettymapp) – a térképek motorja (Christoph Rieke)
- [OpenStreetMap](https://www.openstreetmap.org) közreműködők – a térképadatok
- [Hugging Face](https://huggingface.co) – a hosztolt nyelvi modell

## Licenc

MIT — lásd [LICENSE](LICENSE).
