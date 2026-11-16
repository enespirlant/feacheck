# feacheck — Ajan günlüğü

## 2026-11-15 (ajan çalıştırması 1)
**Yapılanlar**
- Faz 1a koşuları (keskin köşe 133,7 MPa; R5 "çözünürlük yetersiz") doğru adla golden teste bağlandı.
  Cihazdaki `lbraket_r5_v2.json` ve `lbraket_keskin_v2.json` adları birbirinin tersiydi.
- Radyus yüzüne otomatik yerel sıklaştırma: global seri bitince tepe eğri bir yüzdeyse ve radyusta
  < 8 eleman varsa, global boyut sabit tutulup o yüze R/4 → R/6 → R/9 yerel boyutla ek seri çözülüyor.
  Seri yakınsar ve tepe radyusta kalırsa tasarım gerilmesi oradan (güven "orta"); yakınsamazsa gösterge
  değer bu seriden. Rapora rozet, GCI satırı ve "Radyus yerel sıklaştırma serisi" tablosu eklendi.
  Ayar: `radyus_siklastirma: true` (ayarlar.yaml).
- Dışlama bölgesi: Lc/2 yerine en büyük mesnet/yük nesnesinin √(yüz alanı); alt sınır 2·h0, üst sınır Lc/2.
  Mevcut 9 gerçek vakada karar değişmedi; ince parçalarda (ör. 500×40×3) bölge 19,6 → 11 mm.
  Şablondaki IronPython kodu CPython fonksiyonuyla test içinde karşılaştırılıyor.
- Testler: 29 → 38 (hepsi geçiyor). Radyus serisi testleri SENTETİK veriyle (fixture'da işaretli).

**Takılanlar / dikkat**
- Radyus serisi Mechanical'da hiç çalıştırılmadı; API çağrıları (AddSizing, PlotData) mevcut kodla aynı
  kalıpta ama gerçek koşu şart.
- Cihazda git kullanılamıyor (silme izni yok → kilit dosyaları); geçmiş ajan ortamında tutuldu.

**Sıradaki**
1. Ansys'te R5 koşusu → gerçek radyus serisi verisi → golden test (görev 12)
2. Görev 4: R5 için Peterson el hesabı
3. Görev 6–7: eleman derecesi ve kalınlıkta eleman sayısı uyarıları

## 2026-11-15 (ajan çalıştırması 2) — ilk gerçek radyus serisi
**Sonuç:** Radyus serisi Mechanical'da sorunsuz çalıştı (188,5 s). Yerel seri 178,4 → 179,5 → 181,9 MPa,
tepe her seviyede radyusta. Araç önce "yerel seri de yakınsamadı" dedi: artışlar %0,6 ve %1,3 olduğu
için ε oranı testi bunu "ıraksıyor" sayıyordu.
**Düzeltme:** Iraksayan görünen ama her adımı ≤ eşik/2 (%2,5) olan seriler artık "güvenilir (küçük
değişim)", güven düşük, belirsizlik = son üç değerin aralığı × 1,25. Tekillik bu kurala takılmaz
(r = 1,5'te tekillik adım başı > %4). Gerçek koşu golden teste eklendi.
**R5 sonucu:** tasarım gerilmesi 186,2 MPa (ince 181,9 ± %2,4), GK 1,34. Köşe hariç 133,7 MPa ile
Kt ≈ 1,36–1,40. Önceki "185–195" beklentisinin alt ucu; Peterson abağıyla teyit gerekiyor (görev 4).
**Gözlem:** Global en ince mesh (radyusta ~4 eleman) 183,1 verdi, yani yerel serinin hepsinden yüksek.
Kaba mesh'te radyusun çokgen gibi temsil edilmesi tepeyi biraz şişiriyor olabilir; kesin değil.

## 2026-11-15 (ajan çalıştırması 3)
- **R5 el hesabı (görev 4):** L köşesi için Peterson'da birebir abak yok, iki sınırla kıstırıldı.
  Alt: kademeli düz çubuk omuz radyusu, eğilme, Peterson eğri uydurması (h/r = 12, 2h/D ≈ 0,92) → Kt ≈ 1,27,
  σ ≈ 168 MPa. Üst: Winkler eğri kiriş iç lifi (ri = 5, ro = 15) → 198 + 3,3 ≈ 201 MPa.
  feacheck 181,9 (ihtiyatlı 186,2) MPa: aralığın içinde. Golden testte sabitlendi. Bu bir sınırlama,
  % düzeyinde doğrulama değil; daha sıkı referans için yayınlanmış bir L-köşe FEA/deney çalışması gerekir.
  Kaynak (formül): amesweb.info, Peterson/Pilkey omuz radyusu eğri uydurmaları.
- **Görev 6–7:** Mesh eleman derecesi okunuyor; Linear ise bulgu. Etkin kalınlık / en ince eleman < 2 ise
  "kalınlık boyunca az eleman" bulgusu. L-brakette ≈ 3,7 eleman (uyarı yok).
- Testler: 42.
**Sıradaki:** görev 8 (mesnet başına tepki, iç kuvvet oranı), görev 9 (deliğe Fixed uyarısı), sonra rover pilotu.

## 2026-11-15 (ajan çalıştırması 4, dar bütçe: 1 görev)
- **Görev 8:** Her mesnedin tepkisi ayrı okunuyor; iç kuvvet oranı Σ|R_i|/|ΣR_i| hesaplanıyor. En az iki
  mesnet varken oran > 3 ise "mesnetler birbirine karşı çalışıyor / aşırı kısıtlama olabilir" bulgusu
  (karar değil, soru olarak). Raporda denge bölümüne mesnet tablosu. Eşik 3 geçici; hata kataloğuyla ayarlanacak.
- Mechanical tarafı (reactions_by_support) Ansys'te henüz denenmedi. Testler: 43.
**Sıradaki:** görev 9 (silindirik yüze Fixed uyarısı), görev 10 (hata kataloğu), rover pilotu.

## 2026-11-15 — ajan çalıştırması 5 (tek görev, %10 bütçe)
- Görev 9: Şablon artık her mesnet/yük yüzünün yüzey tipini (`surface`) ve kenar yarıçaplarını kaydediyor.
  Analiz, bastırılmamış bir Fixed Support silindirik/konik/torus yüze uygulanmışsa bulgu üretiyor
  (yarıçapla birlikte; Cylindrical Support / ön yük + temas / rondela izi önerisi). Eski JSON'larda alan
  yoksa uyarı çıkmıyor. Test eklendi, 44 test geçiyor.
- Doğrulanmadı: `SurfaceType` değerinin Mechanical'da "Cylinder" içeren bir ad döndürdüğü (radyus
  hedeflemesinde aynı özellik kullanılıyor ve çalışıyordu, o yüzden düşük risk).
- Sıradaki: 10 (hata kataloğu), 11 (PyMechanical yolu), README + demo (LinkedIn hazırlığı).

## 2026-11-15 — ajan çalıştırması 6 (tek görev)
- Görev 14: İngilizce README (amaç, yöntem, 5 doğrulama vakası, kurulum, sınırlamalar, kaynaklar; "verification, not validation" açıkça yazıldı). Türkçe README'deki "test ediliyor" satırı gerçek sonuçlarla değiştirildi.
- Sıradaki: 15 (demo raporları), 10 (hata kataloğu), 11 (PyMechanical yolu).

## 2026-11-15 — ajan çalıştırması 7 (3 görev; kullanıcı bütçe sınırını kaldırdı)
- Görev 15: `examples/reports/` altına 4 demo rapor (keskin köşe, R5, delikli plaka, aks) + 2 ekran görüntüsü;
  `examples/make_reports.py` ile yeniden üretilir. README'lere eklendi.
  Bu sırada hata bulundu ve düzeltildi: radyus yerel seriyle çözüldüğünde rapor hâlâ "ÇÖZÜNÜRLÜK YETERSİZ … tasarım
  değeri olarak kullanılmaz" bulgusunu gösteriyordu (rozetle çelişki). Test eklendi.
- Görev 11: `feacheck converge` artık butonla aynı `template_cfg` yapılandırmasını kullanıyor: boyutları kendisi
  hesaplamıyor (şablon kalınlık sınırını uyguluyor), ayarlar.yaml (seviye, oran, düğüm limiti, GCI eşiği,
  radyus seçenekleri) uygulanıyor; raporda gerçekten kullanılan boyutlar görünüyor. Sahte oturumla test edildi.
- Görev 13: Radyus serisinde değişim gürültü düzeyinde (≤ eşik/2) ama yönü belirsizse (salınım ya da son adım
  büyüyor) 4. seviye çözülüyor (`radyus_ek_seviye: true`). Gerçek R5 serisi (178,4 → 179,5 → 181,9) bunu tetikler.
  GCI son üç seviyeden; raporda not. 48 test geçiyor.
- Ansys'te denenmedi: 4. seviye ve silindirik yüz uyarısı. Bir sonraki R5 koşusu ikisini de sınar.
- Sıradaki: 10 (hata kataloğu: bozuk modeller + beklenen sonuç tablosu), 5 (R1/R2 STEP), rover pilotu.

## 2026-11-15 — ajan çalıştırması 8 (3 görev)
- Rapor sayfası yeniden tasarlandı: üstte tek cümlelik hüküm ve kullanılacak sayı, reddedilen ham tepe /
  tasarım değeri / akmayı aynı eksende gösteren gerilme cetveli, 6 maddelik kontrol listesi, bulgular;
  karar izi, GCI, mesh seviyeleri, sınır şartları, denge ve ayarlar katlanır "Teknik ayrıntılar"da.
- Kullanıcı "5 mesh seviyesi?" diye sordu: düğüm limiti en ince mesh'i sabitlediği için 5 seviye en kaba mesh'i
  asimptotik bölgenin dışına iter. Yerine global seride uyarlamalı 4. seviye eklendi (aday değer gürültü
  düzeyinde ama yönü belirsizse ve sonraki seviye limite sığıyorsa). 12 gerçek koşudan yalnız birini tetikler.
  Sıfır değişimin "belirsiz" sayılması hatası test sırasında bulunup düzeltildi.
- Hata kataloğu `docs/HATA_KATALOGU.md`: 12 vaka (nasıl bozulur / beklenen sonuç / test durumu) ve
  yakalanamayan hatalar. Akma aşımı ve büyük deformasyon için test eklendi. 51 test geçiyor.
- Sıradaki: katalog vakalarının Ansys koşuları (kullanıcı), ondalık virgül, rover pilotu.

## 2026-11-15 — ajan çalıştırması 9 (kullanıcı: rapor daha ayrıntılı ve görsel olsun)
- Yeni `feacheck/report_viz.py` (bağımlılıksız SVG): eleman boyuna karşı yakınsama grafiği (ham tepe vs tasarım
  büyüklüğü, h→0 ekstrapolasyonu, GCI bandı), büyüme üssü q göstergesi (yakınsıyor / çözünürlük / tekillik,
  0,455 keskin köşe işareti), iki izdüşümlü konum haritası (mesnet/yük yüzleri, dışlama bölgeleri, ham tepe,
  tasarım noktası), denge ve mesh çubuk grafikleri, radyus serisi grafiği.
- Rapor: bölüm gezinmesi, özet sayılar, her kontrolün ne anlama geldiği, GCI hesabı gerçek sayılarla adım adım,
  tüm büyüklükler tablosunda seviye değerleri ve tasarım satırı vurgulu, Türkçe ondalık virgül, baskı stili.
- Ekran görüntüsüyle gözden geçirilip düzeltilenler: etiket çakışması, sıfır eksenlerde gürültü değerleri,
  bilimsel gösterim, küçük değişimlerin eksen ölçeğiyle abartılması. 51 test geçiyor.

## 2026-11-15 22:30 — R5 gerçek koşusu (4 seviye) ve düzeltme
- Ansys'te ilk kez çalışan ve doğrulanan: yüzey tipi (GeoSurfacePlane), mesnet başına tepki (1000 N),
  eleman derecesi (ProgramControlled), radyus 4. seviye (21 eleman/yay, 83 bin düğüm), yeni rapor.
- Bulunan hata: radyus serisi 178,4 → 179,5 → 181,9 → 186,2; adımlar aynı yönde ve büyüyor. "Küçük değişim"
  kuralı bunu gürültü sayıp güvenilir diyordu (önceki 3 seviyeli koşuda da 181,9'u yanlışlıkla kabul etmişti).
  Kural düzeltildi: salınım ya da küçülen adım gerekiyor. Gerçek 4 seviyeli koşu fixture olarak eklendi,
  eski yanlış kararı kodlayan testler yeniden yazıldı, README/demo düzeltildi.
- Olası neden ve önlem: yalnız yüzey inceldiği için radyus altındaki hacim kaba. Radyus serisinde mesh
  büyüme oranı 1,2'ye düşürülüyor (Mesh.GrowthRate; sonra eski haline dönüyor). Ansys'te denenmedi.

## 2026-11-15 22:40 — büyüme oranı etkisiz kaldı
- 22:34 koşusu: radyus serisi değerleri ve düğüm sayıları önceki koşuyla birebir aynı; Mesh.GrowthRate hatasız
  atandı ama "Use Adaptive Sizing = Yes" iken yok sayılıyor. Rapor yine de "büyüme oranı 1,2" yazıyordu.
- Düzeltme: seri boyunca UseAdaptiveSizing = False (sonra geri yükleniyor); rapor istenen değeri değil Ansys'ten
  geri okunan değeri ve adaptive sizing durumunu yazıyor; bulgu metni buna göre değişiyor. Gerçek koşu fixture
  olarak eklendi. 52 test geçiyor.

## 2026-11-15 22:45 — ajan çalıştırması (kullanıcı yokken, 3 görev)
- GCI kodu Celik vd. (2008) Tablo 1 örneğini birebir üretiyor (p 1,537 / φ_ext 6,1682 / e_a %1,50 / e_ext %1,71 /
  GCI %2,17); kalıcı test. Çıktıya ve rapora e_ext eklendi.
- handcalc.py: kiriş, burulma, sehim, von Mises, Winkler (198,05 MPa = önceki el hesabı), delikli levha Kt
  (Heywood; 2,506 → 125,3 MPa), mil omzu Kt (Roark Tablo 17.1 / Pilkey uydurması, kaynak amesweb; grafiklerle
  ±%7). Aralık dışı ValueError. elhesap.yaml (model adı eşleşmesi) → rapor karşılaştırması; uyuşmazsa bulgu.
- Rapor: cetvel gösterge değeri ve el hesabı bandını da çiziyor; "El hesabı" kontrol satırı ve bölümü.
  Demo raporlarının el hesapları handcalc ile üretiliyor. 59 test geçiyor.

## 2026-11-15 23:10 — R5 yakınsadı
- Adaptive sizing kapatılınca büyüme oranı uygulandı (radyus düğümleri 30.297 → 52.355; önce 33.486 → 83.204).
  Radyus tepesi 181,9 → 179,8 → 182,0 → 183,6: son üç seviye yakınsıyor, p = 0,695, ext 188,5.
- Yeni kurallar: (1) 0,5 ≤ p < 1 → Fs = 3 ("low_order", Roache 1998), güven düşük, ihtiyatlı değer GCI bandının
  üstü; (2) yakınsayan seride GCI ≤ 2 × eşik → "güvenilir (geniş belirsizlik)", düşük güven; (3) 4+ seviyede
  erken yön değişimi notu. Diğer tüm fixture'larda tasarım değeri değişmedi.
- R5 sonucu: ince 183,6, ihtiyatlı 198,3 MPa (GCI %8), GK 1,26, el hesabı 168–201 içinde, Kt ≈ 1,37. 60 test.

## 2026-11-17 02:30 — ajan çalıştırması (3 görev)
- 16.11 R5 koşusu 15.11 23:04 koşusuyla birebir aynı (düğüm, gerilme son haneye kadar) → tekrarlanabilirlik testi.
- Düz `pytest` artık yeşil: cadquery yoksa boru hattı testleri atlanıyor (importorskip). GitHub Actions iş akışı
  (ubuntu + windows, Python 3.10/3.12; yalnız pyyaml + pytest). Ansys/mcp/cadquery engellenmiş ortamda doğrulandı.
- Montaj bağlantıları: şablon Connections altındaki temas bölgelerini (tip, kaynak/hedef yüzler), mafsalları, kiriş
  bağlantılarını ve gövde sayısını okuyor (ANSYS'TE DENENMEDİ). Analiz: bağlantısız çok gövde, bonded temas,
  doğrusal olmayan temas, tepe temas yüzü yakınında. Rapor tablosu, katalog 13–14. Sentetik testler.
- Bulgu/karar izi/not metinlerinde Python biçimli sayılar Türkçeye çevriliyor; sayı gruplarında ';' ayırıcı.
- 63 test geçiyor (+1 atlanan).

## 2026-11-17 03:00 — ajan çalıştırması (kullanıcı "tamamen özgürsün", 3 görev)
- Öz test: build_selftest şablonun son çağrısını 6 vakalık döngüyle değiştirir (temel, lineer, yuk_x5, ikinci_fixed,
  egri_yuze_fixed, mesnetsiz); her vaka try/finally ile geri alınır; CFG vakalar arası derin kopyayla sıfırlanır (şablon
  sizes_mm listesine yerinde ekleme yapıyordu). `feacheck katalog` geçti/kaldı özeti. setup ikinci düğmeyi kurar.
  Sentetik klasörle test: 5 geçti + 1 ölçüm.
- 0.2.0: CHANGELOG (her düzeltme gerçek koşuya bağlı), KULLANIM.md, --version, rapor altbilgisi.
- NASIL_CALISIR.md: tüm modüller, gerekçeler, R5 hikâyesi, 10 soru, 60 sn anlatım. Rehberi yazarken büyüme üssü
  göstergesinin bölgeleri (0,3 eşiği) ile karar mantığı (q > 0,1 + yüz tipi) arasında tutarsızlık bulundu, düzeltildi.
- 66 test geçiyor (+1 atlanan).
