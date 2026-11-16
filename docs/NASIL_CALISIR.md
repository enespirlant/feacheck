# feacheck nasıl çalışır: baştan sona

Bu belge feacheck'in her parçasını ve her kararın nedenini anlatır. Amaç, projeyi birine (hoca, mülakatçı, takım
arkadaşı) kendi cümlelerinle anlatabilmen ve "neden böyle?" sorularına cevap verebilmen. Sondaki soru listesiyle
kendini sına.

---

## 1. Problem

Doğrusal statik bir FEA'da en yüksek gerilmeye bakıp "parça dayanır mı?" diye karar verilir. Sorun şu: o en yüksek
değer çoğu zaman fiziksel değildir.

- **Sınır şartı tekilliği.** Fixed Support bir yüzü sonsuz rijit tutar. Yüzün kenarında elastisite çözümü sonsuz
  gerilme verir. Mesh inceldikçe değer 120 → 150 → 200 → … diye artar, hiç durmaz.
- **Geometrik tekillik.** Radyussuz keskin iç köşede de çözüm sonsuzdur (Williams 1952: 90° köşede σ ∝ r^(−0,455)).
- **Çözülmemiş radyus.** Gerçek bir radyus vardır, gerilme sonludur, ama mesh radyusu birkaç elemanla geçtiği için değer
  henüz oturmamıştır. Bu gerçek bir gerilme yığılmasıdır; doğru değeri bulmak için o bölge inceltilmelidir.

Üçü de ekranda aynı görünür: kırmızı bir nokta. feacheck bunları birbirinden ve gerçek gerilmeden ayırır, sonucun
mesh'e bağlı belirsizliğini sayıyla verir.

## 2. Büyük resim

```
Mechanical (IronPython 2.7)                         Bilgisayarın (CPython 3)
┌──────────────────────────────┐   raw_*.json    ┌────────────────────────────────────┐
│ mech_converge.py şablonu     │ ──────────────► │ analysis.py  karar mantığı         │
│ • ön kontroller              │                 │ gci.py       Richardson / GCI      │
│ • 3 seviye global mesh+çözüm │                 │ handcalc.py  el hesabı             │
│ • (gerekirse) radyus serisi  │                 │ report.py    HTML rapor            │
│ • sonuçları oku, modeli geri │                 │ selftest.py  öz test özeti         │
│   al                         │                 └────────────────────────────────────┘
└──────────────────────────────┘
```

**Neden iki katman?** Mechanical'ın içindeki betik dili IronPython 2.7: eski, kütüphane kurulamaz, hata ayıklaması zor,
ve yalnız Ansys açıkken çalışır. Bu yüzden Mechanical tarafı yalnızca *ölçer* (mesh at, çöz, sayıları oku, JSON yaz).
Bütün *kararlar* normal Python'da verilir. Sonuç: karar mantığının tamamı Ansys olmadan, gerçek koşuların kaydedilmiş
ham sonuçlarıyla test edilebilir. 66 testin hiçbiri Ansys istemez.

## 3. Mesh serisi

- **Kaç seviye?** GCI için en az üç çözüm gerekir: iki çözüm yalnız farkı verir, üçüncüsü farkın nasıl küçüldüğünü (mertebe
  p) verir.
- **Başlangıç boyu.** Karakteristik boy L꜀ = V^(1/3), h₀ = L꜀/8. İnce cidarlı parçada bu kalınlıktan büyük çıkar; o
  yüzden etkin kalınlıkla t = 2V/A sınırlanır (ilk mesh'te kalınlık boyunca en az ~1 kuadratik eleman).
- **İncelme oranı r = 1,5.** Celik (2008) r > 1,3 önerir; küçük r'de farklar gürültüye karışır, büyük r'de düğüm sayısı
  hızla patlar (3B'de her seviye ≈ r³ = 3,4 kat).
- **Neden 5 seviye değil?** Öğrenci lisansı düğüm sayısını sınırlar, yani en ince mesh sabit. Seviye eklemek en kabayı daha
  kaba yapar ve o mesh asimptotik bölgenin dışına düşer. Bunun yerine **uyarlamalı 4. seviye** var: değişim gürültü
  düzeyinde ama yönü belirsizse ve düğüm bütçesi yetiyorsa bir seviye daha çözülür.

## 4. GCI: sayısal belirsizlik

Üç çözüm f₁ (ince), f₂, f₃ (kaba); eleman boyları h₁ < h₂ < h₃; oranlar r₂₁ = h₂/h₁, r₃₂ = h₃/h₂.

1. Farklar: ε₂₁ = f₂ − f₁, ε₃₂ = f₃ − f₂. İşaretleri aynıysa **monoton**, farklıysa **salınımlı**.
2. Görünen mertebe p, sabit nokta iterasyonuyla:
   p = |ln|ε₃₂/ε₂₁| + q(p)| / ln r₂₁,  q(p) = ln((r₂₁ᵖ − s)/(r₃₂ᵖ − s)),  s = işaret(ε₃₂/ε₂₁).
   Oranlar eşitse q = 0 ve p = ln(ε₃₂/ε₂₁)/ln r.
3. Richardson ekstrapolasyonu: f(h→0) ≈ f₁ + (f₁ − f₂)/(r₂₁ᵖ − 1). "Mesh sonsuz ince olsaydı."
4. GCI = Fs·|ε₂₁/f₁| / (r₂₁ᵖ − 1). Yaklaşık %95 güvenle gerçek değerin f₁ ± GCI içinde olduğunu söyler.

**Güvenlik çarpanı Fs.** Roache: mertebe doğrulanmışsa 1,25, doğrulanmamışsa 3.
- p, [0,5; 4] dışında → seri asimptotik değil, p kırpılır, Fs = 3.
- 0,5 ≤ p < 1 → kuadratik elemanda gerilme için beklenen p ≈ 2'nin çok altında, Fs = 3 ve güven "düşük".

**Doğrulama:** `gci.py`, Celik vd. (2008) makalesinin Tablo 1 örneğini birebir üretir (p = 1,53, φ_ext = 6,1685,
GCI = %2,2). Bu bir testtir; kodun formülü doğru uyguladığının kanıtı.

**Küçük değişim kuralı.** Değişimler çok küçükken (adım başı < eşik/2) oranları gürültü belirler ve p anlamsızlaşır. Bu
durumda **salınım ya da küçülen adım** varsa sonuç "güvenilir (küçük değişim)" sayılır. **Aynı yönde büyüyen** adımlar ise
gürültü değildir: seri yakınsamıyordur. (Bu ayrım R5'te gerçek bir hatayı düzeltti, bkz. §7.)

## 5. Tekillik ayrımı

Ham tepe değer yakınsamıyorsa, büyüme üssü q ölçülür: σ ∝ h^(−q), q = ln(σ_ince/σ_kaba) / ln(h_kaba/h_ince).

| Durum | Nasıl tanınır | Ne yapılır |
|---|---|---|
| Sınır şartı tekilliği | Tepe bir mesnet/yük yüzüne dışlama mesafesinden yakın, q > 0,05 | Tepe reddedilir; değer dışlama bölgesi dışından |
| Geometrik tekillik | q > 0,1, tepe düz yüzlerin keskin kenarında | Köşe reddedilir; değer köşeden uzaktan; köşeyi gerçek radyusla modelle |
| Çözülmemiş radyus | q > 0,1, tepe silindirik bir yüzde | Radyus yerel sıklaştırma serisi (§6) |

q'nun kendisi tekillik ile radyusu ayırmaz; **tepenin bulunduğu yüzün tipi** ayırır. Yüz bilgisi yoksa yedek kural: adım
adım q tekillikte sabit kalır, çözülmemiş radyusta azalır.

**Dışlama bölgesi (Saint-Venant).** Bir yükün nasıl uygulandığının etkisi, yük bölgesinin boyutu kadar mesafede söner. Bu
yüzden mesafe = max √(yüz alanı); alt sınır 2·h₀ (en az iki eleman), üst sınır L꜀/2 (parçanın yarısını dışlamamak için).

## 6. Radyus yerel sıklaştırma

Global mesh'i radyusu çözecek kadar inceltmek düğüm limitini aşar. Onun yerine global boy sabit tutulur, yalnız radyus
yüzüne R/4 → R/6 → R/9 eleman boyu verilir ve o noktanın tepesi izlenir. İki ders:

1. **Yalnız yüzey yetmez.** Yüzey elemanları küçülür ama altındaki hacim kaba kalırsa gerilmenin içeri doğru azalması
   çözülemez; değer tırmanmaya devam eder. Çözüm: seri boyunca mesh büyüme oranı 1,2 (ince yüzeyden hacme yavaş geçiş).
2. **Ayar gerçekten uygulandı mı, geri oku.** Mechanical'da "Use Adaptive Sizing" açıkken büyüme oranı hatasız atanır
   ama yok sayılır. feacheck önce adaptive sizing'i kapatır, sonra değeri Ansys'ten geri okuyup rapora onu yazar.

## 7. Gerçek koşuların öğrettikleri (R5 L-braket)

| Koşu | Radyus serisi [MPa] | Araç ne dedi | Gerçek |
|---|---|---|---|
| 1 | 178,4 → 179,5 → 181,9 | güvenilir 181,9 | Yanlış: adımlar büyüyor |
| 2 | … → 186,2 (4. seviye) | güvenilir 194,7 | Yanlış: aynı hata |
| 3 | aynı (düğümler birebir aynı) | büyüme oranı 1,2 uygulandı | Yanlış: ayar yok sayılmış |
| 4 | 181,9 → 179,8 → 182,0 → 183,6 | güvenilir 188,5, Fs 1,25 | İyimser: p = 0,70 |
| 5 | aynı | ihtiyatlı 198,3, GCI %8, güven düşük | El hesabı 168–201 içinde |
| 6 | 5 ile birebir aynı (ertesi gün) | aynı | Tekrarlanabilir |

Her satırdaki hata düzeltildi ve o koşunun ham sonucu testlere eklendi. Bu, projenin en güçlü hikâyesi: araç kendi
kurallarını gerçek veriyle sınadı ve yanıldığı yerlerde düzeltildi.

## 8. Tasarım değerinin seçimi

Aday büyüklükler, her mesh seviyesinde ölçülür:

- **Global maksimum**: tekillik yoksa doğrudan bu.
- **Sabit nokta (probe)**: ilk mesh seviyesinde dışlama bölgesi dışındaki en yüksek gerilmenin yeri; sonraki seviyelerde
  hep o koordinata en yakın düğümde okunur (aynı fiziksel nokta, farklı mesh).
- **Bölge dışı maksimum**: dışlama bölgesinin dışındaki en yüksek değer.
- **Tepe dışı maksimum**: tekil noktanın çevresi hariç en yüksek değer.
- **Radyus tepesi**: radyus serisinden.

Tekillik türüne göre sırayla denenir; ilk "güvenilir" olan seçilir. Her kabul/ret gerekçesiyle **karar izine** yazılır.
Seçilen değer kritik noktadan düşükse ve kritik nokta gerçek bir yığılmaysa reddedilir (ihtiyatsız olur).

**İhtiyatlı değer.** Yakınsayan seride max(f₁, f_ext): azalan seride ekstrapolasyon ince değerin altına düşer, emniyet
katsayısını şişirmemek için büyük olan alınır. Düşük mertebe ya da geniş belirsizlikte f₁·(1 + GCI): bandın üst ucu.

## 9. Kurulum kontrolleri

| Kontrol | Neden |
|---|---|
| Kuvvet dengesi | Tepki toplamı yükü karşılamıyorsa model yanlış. (Tutması doğru olduğunu göstermez.) |
| İç kuvvet oranı Σ‖Rᵢ‖ / ‖ΣRᵢ‖ | Mesnetler birbirine karşı itiyorsa oran büyür: aşırı kısıtlama. Eşik 3, öz testle ayarlanacak. |
| Silindirik yüze Fixed | Cıvata deliğini tamamen ankastre yapmak gerçeğinden rijit; kenarda yapay yığılma. |
| Lineer eleman | Gerilme elemanda sabit; tepe değerler ciddi düşük çıkar. |
| Kalınlık boyunca eleman | 2'nin altında eğilme gerilmesi çözülemez. |
| Montaj bağlantıları | Bağsız gövde, bonded (gerçekten rijit), sürtünmeli temas (iteratif), tepe temas kenarında. |
| Akma aşımı / büyük deformasyon | Doğrusal analiz geçersizleşir. |
| Mesh kalitesi | Ansys kabul sınırları (quality, skewness, aspect). |

## 10. El hesabı

FEA'yı bağımsız bir yöntemle sınamak için. Tek değer (aks: 32M/πd³ = 113,3 MPa; FEA 113,8) ya da **aralık**: bazı
geometrilerde birebir formül yoktur, gerçek durum iki idealleştirmenin arasında kalır. L-braket R5: alt sınır kademeli düz
çubuk omuz radyusu Kt ≈ 1,27 (gerçeğinden yumuşak), üst sınır Winkler eğri kiriş (gerçeğinden zayıf kesit, iç lif
198 MPa). FEA 183,6 aralıkta. Eğri uydurmaları geçerlilik aralığı dışında hata verir.

## 11. Testler

- **Golden testler**: gerçek Ansys koşularının ham sonuçları (`tests/fixtures/`) ve beklenen kararlar. Bir kural
  değişince eski bir koşunun sonucu değişirse test kırılır.
- **Sentetik testler**: Ansys'te henüz koşulmamış durumlar için elle türetilmiş veri; her biri dosyasında "SENTETİK" diye
  işaretli.
- **Yöntem doğrulaması**: Celik 2008 örneği, el hesabı formülleri bilinen değerlere karşı.
- **CI**: her gönderimde Windows ve Linux'ta, Ansys olmadan.

## 12. Doğrulama (verification) ≠ validasyon (validation)

- **Doğrulama:** denklemi doğru çözüyor muyum? (mesh yakınsaması, tekillik, sayısal belirsizlik) → feacheck bunu yapar.
- **Validasyon:** doğru denklemi mi çözüyorum? (yük doğru mu, mesnet gerçeği yansıtıyor mu, malzeme doğru mu) → fiziksel
  test ister (gerinim ölçer). ASME V&V 10 bu ayrımı tanımlar.

feacheck'in "güvenilir" demesi "parça dayanır" demek değildir; "bu model bu sonucu sayısal olarak doğru veriyor"
demektir.

## 13. Sınırlar

Doğrusal statik, katı modeller. Kabuk/kiriş eleman, doğrusal olmayan malzeme desteklenmez. Temasın doğruluğu ölçülmez.
Yanlış yüze yük, yanlış malzeme, yanlış yük büyüklüğü yakalanmaz.

---

## Kendini sına

1. **Neden en az üç mesh?** İki çözüm farkı verir; mertebeyi (farkın nasıl küçüldüğünü) bulmak için üçüncüsü gerekir.
2. **GCI %3 ne demek?** Sayısal hata payı: gerçek (sonsuz ince mesh) değer yaklaşık %95 güvenle ince mesh değerinin ±%3'ü
   içinde. Modelleme hatalarını kapsamaz.
3. **Fs neden bazen 1,25, bazen 3?** Görünen mertebe beklenenle tutarlıysa yakınsama doğrulanmıştır (1,25); değilse
   tahmine daha az güvenilir (3).
4. **p'yi neden [0,5; 4] aralığına kırpıyorsun?** Bu aralık dışındaki p seri asimptotik bölgede değil demektir; o p ile
   ekstrapolasyon anlamsız büyük ya da küçük çıkar.
5. **Sahte tepeyi nasıl tanırsın?** Mesh inceldikçe yakınsamıyor; büyüme üssü q > 0,1; konumu mesnet/yük yüzüne yakın
   (sınır şartı) ya da keskin düz kenarda (geometrik).
6. **Keskin köşe ile çözülmemiş radyus aynı görünüyor, nasıl ayırıyorsun?** Tepenin bulunduğu yüzün tipi: düz yüzlerin
   kenarı mı, silindirik yüz mü. Yedek: adım adım q sabit mi, azalıyor mu.
7. **Dışlama mesafesini nasıl seçiyorsun?** Saint-Venant: yük bölgesinin boyutu kadar; √(yüz alanı), alt 2·h₀, üst L꜀/2.
8. **Toplam denge tutuyorsa model doğru mudur?** Hayır. Doğrusal statikte denge neredeyse her zaman tutar; yanlış yüze
   verilen yük de dengededir.
9. **Aracın yanıldığı bir örnek?** R5: tırmanan seriyi "küçük değişim" diye kabul etti; gerçek koşu gösterdi, kural
   düzeltildi (aynı yönde büyüyen adımlar gürültü değildir), koşu teste eklendi.
10. **Verification ile validation farkı?** Denklemi doğru çözmek ile doğru denklemi çözmek. feacheck birincisini yapar.

## 60 saniyede anlat

"FEA'da en yüksek gerilme çoğu zaman sahtedir: mesnet kenarında ya da keskin köşede mesh inceldikçe sonsuza gider.
feacheck, Ansys Mechanical'da tek tuşla modeli üç mesh seviyesinde çözer, Richardson ekstrapolasyonu ve GCI ile
sonucun mesh'e bağlı belirsizliğini ölçer, sahte tepeyi büyüme hızından ve konumundan tanıyıp ayırır, radyus gibi gerçek
yığılmaları yerel sıklaştırmayla çözer ve tasarımda kullanılacak ihtiyatlı değeri karar iziyle birlikte raporlar. GCI
uygulamasını Celik 2008'in çözülmüş örneğiyle, sonuçları el hesaplarıyla doğruladım. Gerçek koşular aracın üç kuralında
hata buldu; her birini düzelttim ve o koşuları regresyon testine çevirdim."
