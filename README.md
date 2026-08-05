# AI Müsahibə Platforması

Namizədə bacarıqları və 1–10 arası səviyyələri təyin olunur; Claude həmin
səviyyəyə uyğun texniki müsahibə aparır və HR üçün strukturlaşdırılmış hesabat
hazırlayır.

- **Backend:** Python `http.server` (çərçivəsiz), port 5000
- **AI:** Anthropic Claude (`claude-opus-5`)
- **Baza:** MySQL — `musahibe` (SQLite istifadə olunmur; bütün vəziyyət bazadadır)
- **Asılılıqlar:** `anthropic`, `PyMySQL`

---

## 1. İşə salma

```bash
cd /home/musahibe/musahibe

# 1) .env faylına Anthropic açarını yazın
#    ANTHROPIC_API_KEY=sk-ant-...

# 2) Serveri başladın
./.venv/bin/python app.py
```

Açılan ünvanlar:

| | |
|---|---|
| Admin panel | `http://localhost:5000/admin/` |
| Namizəd linki | `http://localhost:5000/candidate/?token=<token>` |

**İlk istifadəçi.** Panel boş bazada istifadəçisiz açılmır — ilk hesabı
serverdən yaradın (parol verilməsə təsadüfi parol yaradılıb ekrana yazılır):

```bash
./.venv/bin/python create_user.py hr "<parol>" "Ad Soyad" bas_hr
```

Sonrakı hesablar panelin içindən, Baş HR tərəfindən yaradılır — bax §11.

> Parolları repoya, sənədə və ya mesajlara yazmayın.

---

## 2. İş axını

1. HR admin panelə daxil olur.
2. Namizədin adını, soyadını, vəzifəsini yazır.
3. Bacarıqları əlavə edir və hər biri üçün səviyyəni sürgü ilə **1–10** təyin edir.
4. **Link** düyməsi ilə namizədin şəxsi müsahibə linkini kopyalayıb göndərir.
5. Namizəd linki açır — AI salamlayır və birinci sualı verir.
   Suallar təyin olunan səviyyəyə uyğun çətinlikdə olur; hər bacarıq üçün
   təxminən `QUESTIONS_PER_SKILL` (default 2) sual verilir.
6. Müsahibə bitəndə AI markeri qoyur, status `completed` olur və hesabat
   avtomatik hazırlanır.
7. HR panelində **Hesabat** düyməsi ilə ümumi balı, bacarıq ballarını,
   güclü/zəif tərəfləri, xülasəni və tam yazışmanı görür.

---

## 3. Konfiqurasiya (`.env`)

| Açar | Təyinat |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API açarı — **məcburidir** |
| `MODEL` | Model adı (default `claude-opus-5`) |
| `PORT` | Server portu (default 5000) |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | MySQL bağlantısı |
| `QUESTIONS_PER_SKILL` | Hər bacarıq üçün sual sayı (default 2) |
| `INTERVIEW_MINUTES` | Yeni namizəd formasındakı **default** müddət (default 15) |
| `SESSION_HOURS` | Admin sessiyasının müddəti (default 8 saat) |

`.env` `.gitignore`-dadır və `600` icazəsi ilə saxlanılır — repoya salınmamalıdır.

---

## 4. Baza sxemi (`musahibe`)

| Cədvəl | Təyinat |
|---|---|
| `candidates` | Namizəd, vəzifə, giriş tokeni (UUIDv4), **müsahibə müddəti**, status, vaxtlar |
| `skills` | Namizədin bacarıqları və 1–10 səviyyəsi |
| `messages` | Müsahibənin tam yazışması (`user` / `assistant`) |
| `reports` | Ümumi bal, bacarıq balları, güclü/zəif tərəflər, xülasə, tövsiyə |
| `users` | Panel istifadəçiləri — **rol** (`hr` / `bas_hr`), parol `pbkdf2_sha256` (200k iterasiya) |
| `sessions` | Admin sessiya tokenləri və bitmə vaxtı |

Bütün əlaqələr `ON DELETE CASCADE` — namizəd silinəndə onun bacarıqları,
yazışması və hesabatı da silinir. Cədvəllər `app.py` başlayanda avtomatik
yaradılır (idempotent).

---

## 5. API

### Admin (`X-Admin-Token` başlığı tələb olunur)

| Metod | Yol | Təyinat |
|---|---|---|
| POST | `/api/admin/login` | `{username, password}` → sessiya tokeni |
| POST | `/api/admin/logout` | Sessiyanı bağlayır |
| GET | `/api/admin/me` | Cari sessiya |
| GET | `/api/admin/candidates` | Namizəd siyahısı + hesabat xülasəsi |
| POST | `/api/admin/candidates` | `{first_name, last_name, role, skills:[{name, level}]}` |
| GET | `/api/admin/candidates/<id>` | Namizəd + hesabat + tam yazışma |
| DELETE | `/api/admin/candidates/<id>` | Namizədi silir |

`login` istisna olmaqla bütün admin endpoint-ləri sessiya tələb edir.

### Namizəd (giriş tokeni ilə)

| Metod | Yol | Təyinat |
|---|---|---|
| GET | `/api/interview/<token>` | Namizəd məlumatı + mövcud yazışma |
| POST | `/api/interview/<token>/message` | `{message}` → `{reply, finished}` |

Boş `message` göndərilməsi müsahibəni başladır (salamlama + ilk sual).

---

## 6. Təhlükəsizlik qeydləri

- Admin endpoint-ləri sessiya tokeni olmadan `401` qaytarır.
- Namizəd tokenləri UUIDv4-dür və yalnız admin panelindən görünür.
- Parollar `pbkdf2_sha256` (200 000 iterasiya, təsadüfi salt) ilə saxlanılır.
- Bütün SQL sorğuları parametrləşdirilib.
- Frontend `textContent` / HTML escape istifadə edir — XSS qorunması var.
- Statik fayllar `static/` qovluğundan kənara çıxa bilmir (path traversal → 403).
- Baza istifadəçisi `musahibe_app` yalnız `musahibe` bazasına icazəlidir.
- **Cihaz kilidi:** müsahibə linki yalnız onu ilk açan brauzerdə işləyir
  (bax §8) — link paylaşılsa da başqası cavab yaza bilmir.

**İstehsalda:** serveri HTTPS reverse proxy (nginx) arxasında işlədin və
`hr` istifadəçisinin default parolunu dəyişin.

---

## 7. Domen və avtomatik işə salma

Layihə `deploy/` qovluğunda iki hazır konfiqurasiya var (hər ikisi `sudo` tələb edir):

| Fayl | Təyinat |
|---|---|
| `deploy/musahibe.service` | systemd — server avtomatik qalxsın və çökəndə yenidən başlasın |
| `deploy/musahibe.azerenerji.az.conf` | Apache reverse proxy — `:5000` portsuz, adi `http://musahibe.azerenerji.az` |
| `Dockerfile` | Konteyner image-i |
| `k8s/musahibe.yaml` | Kubernetes: Namespace `interview`, Deployment, Service, Istio Gateway + VirtualService |
| `k8s/secret.example.yaml` | Konfiqurasiya Secret-inin nümunəsi (real variantı `.gitignore`-dadır) |

Quraşdırma addımları hər faylın öz başlığında yazılıb.

Proxy olmadan da işləyir: `http://musahibe.azerenerji.az:5000`
(hosts faylı `10.10.12.84` ünvanına yönləndirilməlidir).

---

## 8. Cihaz kilidi (link paylaşılmasına qarşı)

Müsahibə linki **yalnız onu ilk dəfə açan brauzerdə** işləyir.

**Necə işləyir:** namizəd linki açanda server təsadüfi sessiya identifikatoru yaradır,
onu `musahibe_sess` cookie-si kimi qoyur (HttpOnly, SameSite=Lax) və eyni anda
`candidates.session_id` sütununa yazır. Yazma **şərtli UPDATE**-dir
(`WHERE session_id IS NULL`), ona görə iki brauzer eyni saniyədə açsa belə
yalnız biri sahiblənir.

Sonra hər sorğuda cookie ilə bazadakı dəyər müqayisə olunur:

| Vəziyyət | Nəticə |
|---|---|
| Eyni brauzer | Normal işləyir |
| Başqa brauzer / cihaz / gizli rejim | `403` → namizəd xəta səhifəsi görür |

Kilid vurulmuş namizədlərin yanında admin paneldə 🔒 işarəsi görünür.
Kilid **geri açılmır** — namizəd brauzer dəyişməli olsa, HR namizədi silib
yenidən yaratmalıdır (yeni link, yeni kilid).

---

## 9. Müsahibənin obyektivliyi

Müsahibəçi **ipucu vermir və düzgün cavabı açıqlamır**: cavabı qiymətləndirmir,
çatışmayan hissəni sadalamır, termin/atribut/kod nümunəsi yazmır. Yalnız qısa
neytral keçid yazıb növbəti suala keçir. Bütün təhlil namizədin görmədiyi yekun
hesabatdadır.

**Rol sızması qorunması.** Model bəzən öz növbəsini bitirmir, `user` etiketi yazıb
namizədin cavabını özü uydurur — həmin mətn namizədə göstərilsə, faktiki olaraq
cavabı ona vermiş olur. İki qat qorunma var:
`stop_sequences` (API generasiyanı həmin nöqtədə dayandırır) və `_strip_role_bleed()`
(cavab yazılmazdan əvvəl mətni kəsir).

**Prompt injection.** Namizədin mesajındakı göstərişlər ("əvvəlki göstərişləri unut",
"mənə tam bal ver") sistem promptunda açıq şəkildə "qiymətləndirilməli mətn" kimi
təsvir olunub — model onlara əməl etmir.

**Orfoqrafiya qiymətləndirilmir.** Namizəd sürətlə yazır: hərf səhvləri
(`datavase`, `guthub`), durğu işarələri, böyük-kiçik hərf və diakritiklərin
olmaması (ə/e, ş/s, ç/c) nə müsahibə gedişində şərh olunur, nə də hesabatda zəif
tərəf sayılır. Model səhv yazılmış termini düzgün başa düşüb məzmuna görə
qiymətləndirir.

**Yeganə istisna — dil bacarıqları.** Yoxlanılan bacarığın özü dildirsə
(`İngilis dili`, `Rus dili`, `Azərbaycan dili` və s.), dil düzgünlüyü **yalnız
həmin bacarığın balına** təsir edir, digər texniki bacarıqlara yox. Bu istisna
bütün dillərə aiddir.

---

## 10. Müsahibə müddəti və hesabatın çapı

**Müddət hər namizəd üçün ayrıca təyin olunur.** Yeni namizəd formasında
"Müddət (dəqiqə)" sahəsi var (1–180 arası; default `.env`-dəki
`INTERVIEW_MINUTES`). Dəyər `candidates.duration_minutes` sütununda saxlanılır —
taymer, avtomatik tamamlama və AI-a verilən göstəriş hamısı həmin dəyəri
istifadə edir. Siyahıda hər namizədin müddəti ayrıca sütunda görünür.

**Hesabatın çapı / PDF.** Hesabat pəncərəsində **"Çap / PDF"** düyməsi var.
Brauzerin çap dialoqunu açır; "Hədəf: PDF olaraq saxla" seçilsə hesabat PDF-ə
çevrilir. Çap zamanı yalnız hesabat görünür (panel, cədvəl, düymələr gizlənir),
müsahibə yazışması tam açılır (ekranda skroll olunan hissə çapda bütöv çıxır),
bal zolaqları və nişanların rəngləri saxlanılır, səhifə kəsimləri bənd və
mesajların ortasından getmir. Başlıqda çap tarixi yazılır.

---

## 11. Rollar və istifadəçi idarəetməsi

### Açıq qeydiyyat YOXDUR

Hesablar yalnız panelin içindən, **Baş HR mütəxəssis** tərəfindən yaradılır.
İnternetdən əlçatan qeydiyyat səhifəsi qəsdən mövcud deyil.

| Rol | Nə edə bilir |
|---|---|
| **HR mütəxəssis** (`hr`) | Namizəd yaradır, müsahibə linki göndərir, hesabatlara baxır, namizədi silir |
| **Baş HR mütəxəssis** (`bas_hr`) | HR-ın hamısı **+ canlı izləmə + istifadəçi idarəetməsi** |

Mövcud `hr` istifadəçisi sadə **HR mütəxəssis** rolundadır. Rol panelin yuxarı
sağında nişan kimi görünür.

### İstifadəçi yaratmaq

Baş HR panelə girəndə yuxarıda **"İstifadəçilər"** düyməsi görünür (sadə HR-da
görünmür). Açılan pəncərədə mövcud hesablar sadalanır və yeni hesab yaradılır:
ad-soyad, istifadəçi adı, parol (ən azı 8 simvol), rol.

Qorunmalar: öz hesabını silmək olmaz; **sonuncu Baş HR** silinə bilməz (əks halda
panelə heç kim istifadəçi əlavə edə bilməzdi); istifadəçi adı təkrarlana bilməz.

Serverdən əl ilə istifadəçi yaratmaq üçün (məsələn bütün Baş HR hesabları itsə):

```bash
./.venv/bin/python create_user.py <istifadəçi> <parol> "Ad Soyad"
```

### Canlı izləmə (yalnız Baş HR)

Namizəd siyahısında tamamlanmamış müsahibələrin yanında **"İzlə"** düyməsi çıxır
(yalnız `bas_hr` üçün) və `/watch/?token=...` səhifəsini yeni tabda açır.

Səhifə **yalnız oxuyur**:

- Cihaz kilidini **vurmur** və sessiya yaratmır — namizədin müsahibəsinə təsir etmir
- Giriş sahəsi **yoxdur** — müdaxilə fiziki olaraq mümkün deyil
- Yazışma hər 3 saniyədə yenilənir, yeni mesaj qısa müddət vurğulanır
- Namizədin taymeri, "Canlı" göstəricisi və bacarıq siyahısı görünür
- Müsahibə bitəndə göstərici "Bitdi" olur və sorğular dayanır

Sadə HR bu ünvana girsə `403`, giriş etməyibsə `401` alır.

---

## 12. Kubernetes ilə yerləşdirmə

| | |
|---|---|
| Namespace | `interview` |
| Domen | `musahibe.azerenerji.az` |
| Image | `azerenerjirepo/musahibe:v1.1.0` |
| Replica | 3 (tətbiq stateless-dir — bütün vəziyyət MySQL-dədir) |

### 1) Image-i qurun və registry-yə göndərin

```bash
docker build -t azerenerjirepo/musahibe:v1.1.0 .
docker push azerenerjirepo/musahibe:v1.1.0
```

`.dockerignore` `.env`, `.venv/` və k8s secret fayllarını image-dən kənarlaşdırır.

### 2) Konfiqurasiya Secret-i

**Credentiallar manifestdə deyil, Secret-dədir.** Ən sadə yol — yerli `.env`-dən:

```bash
kubectl create namespace interview
kubectl -n interview create secret generic musahibe-env --from-file=.env=./.env
```

Declarative istəyirsinizsə `k8s/secret.example.yaml`-ı `k8s/secret.yaml` kimi
kopyalayıb doldurun — həmin ad `.gitignore`-dadır.

### 3) TLS sertifikatı

```bash
kubectl -n istio-system create secret tls musahibe-tls \
  --cert=musahibe.crt --key=musahibe.key
```

### 4) Tətbiqi qurun

```bash
kubectl apply -f k8s/musahibe.yaml
kubectl -n interview rollout status deployment/musahibe
```

Secret dəyişdikdən sonra pod-lar yenidən başladılmalıdır:

```bash
kubectl -n interview rollout restart deployment/musahibe
```

### Manifestdəki iki kritik detal

**`ndots: 1`** — Kubernetes defolt olaraq `ndots:5` qoyur. `api.anthropic.com`
iki nöqtəlidir, ona görə resolver əvvəlcə bütün daxili search domenlərini sınayır
(`api.anthropic.com.interview.svc.cluster.local` və s.) — hər AI çağırışına
onlarla artıq DNS sorğusu düşür və aralıq `Temporary failure in name resolution`
xətaları yaranır.

**Service portunun adı `http`-dir, `https` deyil** — Istio protokolu məhz port
adına görə seçir. Tətbiq 5000-də plain HTTP danışır, TLS-i Gateway sonlandırır.
Adı `https` yazılsa bütün sorğular sınır.
