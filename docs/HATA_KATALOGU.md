# feacheck hata kataloğu

Bilerek yanlış kurulmuş modeller ve feacheck'in her birinde ne demesi gerektiği. Amaç iki şey:
aracın gerçekten yakaladığını kanıtlamak ve yakalayamadıklarını dürüstçe yazmak.

Modeller mevcut üç parçadan türetilir: **aks** (konsol Ø20×200, uçta 500 N), **plaka** (200×50×5, Ø10 delik,
10 kN çekme), **L-braket** (keskin köşe ve R5). Her vaka için modeli kopyala, yalnızca "Nasıl bozulur"
sütunundaki tek değişikliği yap, butona bas, ham JSON'u `inbox`'ta bırak.

Durum sütunu: **gerçek** = Ansys koşusunun ham sonucu testte var; **sentetik** = karar mantığı elle yazılmış
veriyle test edildi, Ansys'te henüz koşulmadı; **yok** = test yok.

## Öz test: kataloğu tek tıkla koşmak

`feacheck setup` iki düğme kurar. İkincisi öz test: herhangi bir modeli açıp analizini seç, `feacheck_oztest.py`'yi
çalıştır. Araç modeli sırayla bozar, her vakada feacheck'in tamamını koşar ve **her vakadan sonra modeli geri alır**:

| Öz test vakası | Ne değiştirir | Katalog no | Beklenen |
|---|---|---|---|
| temel | hiçbir şey | – | kurulum uyarısı yok |
| lineer | Element Order = Linear | 9 | "Eleman derecesi LINEAR" |
| yuk_x5 | tüm Force büyüklükleri ×5 | 11 | tepe gerilme ×5 (doğrusallık), akma aşılırsa uyarı |
| ikinci_fixed | mesnet ve yükten en uzak düz yüze ek Fixed | 7 | ölçüm: iç kuvvet oranı (eşik ayarı) |
| egri_yuze_fixed | en büyük silindirik/eğri yüze ek Fixed | 8 | "Fixed Support silindirik/eğri yüze" |
| mesnetsiz | tüm mesnetler bastırılır | 1 | "mesnet yok", çözüm yapılmaz |

Sonuçlar `inbox/katalog_<tarih>/` klasörüne yazılır, `ozet.html` geçti/kaldı tablosuyla açılır. Bozuk vakalarda
radyus serisi ve ek seviye kapalıdır (yalnız tespit sınanır), bu yüzden toplam süre yaklaşık 4–6 normal koşu kadardır.

## Yakalanması gerekenler

| # | Hata | Nasıl bozulur | feacheck ne demeli | Durum |
|---|---|---|---|---|
| 1 | Mesnet yok | Aks: Fixed Support'u sil (suppress değil) | Hata: "analizde mesnet yok; model serbest", çözüm yapılmaz | yok |
| 2 | Kapsamı boş sınır şartı | Aks: Fixed Support'un geometrisini temizle | Hata: "Tanımsız/hatalı sınır şartı", çözüm yapılmaz | yok |
| 3 | Yanlış analiz tipi | Modal analizi seçip butona bas | Hata: "yalnızca Static Structural" | yok |
| 4 | Mesnet kenarındaki sahte tepe | Aks, olduğu gibi | Tekillik ayrıldı (sınır şartı); tasarım ≈ 113 MPa, ham tepe ≈ 138 dışlanır | gerçek (`aks.json`) |
| 5 | Keskin iç köşe | L-braket R0 | Keskin köşe: köşe hariç 133,7 MPa; köşe değeri verilmez | gerçek (`lbraket_keskin_yuzbilgili.json`) |
| 6 | Çözülmemiş radyus | L-braket R5, `ayarlar.yaml`'da `radyus_siklastirma: false` | Çözünürlük yetersiz; tasarım değeri verilmez | gerçek (`lbraket_r5.json`) |
| 7 | Aşırı kısıtlama | L-braket: alt yüzde Fixed dururken üst yüze ikinci bir Fixed | Mesnetler birbirine karşı çalışıyorsa iç kuvvet oranı > 3; aynı yönde çalışıyorsa "mesnet neredeyse yüksüz" (payı < %5) | gerçek (`katalog_gercek_20261117`: yan yüze ikinci Fixed yükün %99,9'unu aldı, oran 1, tepe 183 → 65 MPa) |
| 8 | Deliğe Fixed Support | Plaka: sol uç yerine delik yüzüne Fixed | "Fixed Support silindirik yüze uygulanmış (R 5 mm)", Cylindrical Support önerisi | sentetik |
| 9 | Lineer eleman | Aks: Mesh › Element Order = Linear | "Eleman derecesi LINEAR" uyarısı; gerilme kuadratikten belirgin düşük | sentetik |
| 10 | Kalınlık boyunca tek eleman | Plaka: `feacheck converge --sizes 10,7,5` | "Kalınlık boyunca ~1 eleman" uyarısı | sentetik |
| 11 | Akma aşımı | Aks: kuvveti 500 → 2500 N | "Tasarım gerilmesi akmayı aşıyor: doğrusal analiz geçersiz", GK < 1 | sentetik |
| 12 | Büyük deformasyon | Aks: çapı 20 → 6 mm | "Deformasyon parça boyutunun %5'inden büyük: Large Deflection" | sentetik |
| 13 | Gövdeler bağlı değil | İki ayrı parçayı (ör. braket + plaka) içeri al, Connections altındaki otomatik temasları sil | "N gövde var ama aralarında temas yok" | sentetik |
| 14 | Bonded temas, tepe temas kenarında | Braketi bir plakaya bonded bağla, yükü braketten ver | "bonded temas" bilgisi + "en yüksek gerilme ... temas yüzünün yakınında" | sentetik |

## Yakalayamadıkları (bilinen sınırlar)

| Hata | Neden yakalanmıyor | feacheck'in yardımı |
|---|---|---|
| Yük yanlış yüzde | Model kendi içinde tutarlı; denge de tutar | Sınır şartı tablosu yüz merkezlerini global koordinatta gösterir; kullanıcı doğrular |
| Yanlış malzeme / birim | Hangi malzemenin doğru olduğunu bilemez | Raporda malzeme adı ve akma değerinin kaynağı yazılı |
| Yanlış yük büyüklüğü | Aynı şekilde | Denge tablosunda uygulanan kuvvet görünür; el hesabıyla karşılaştır |
| Gerçekte temas olan bağlantıyı bonded saymak | Temas doğrusal statiğin dışında | Henüz yok |
| Ön yük, ısıl gerilme | Denge kontrolü bu yüklerde atlanır | Raporda "otomatik denge kontrolü yapılmadı" notu |

## Eşik ayarı

Vaka 7'nin eşiği (iç kuvvet oranı 3) geçicidir. Ayarlamak için şu iki doğru kurulmuş modelde oranın 1'e yakın
kaldığını görmek gerekir: iki ucundan basit mesnetli kiriş (ortada yük; beklenen oran 1) ve iki ucu Fixed ama
yalnız eksenel çekmeli çubuk (Poisson etkisiyle 1'in biraz üstü). Bu iki koşu ve vaka 7 gelince eşik, iki
gruptaki değerlerin arasına konur.

## Test bağlantısı

`tests/test_golden.py` ve `tests/test_feacheck.py` içinde her vaka adıyla aranabilir: `aks`, `keskin`,
`r5_cozulmemis`, `ic_kuvvet_orani`, `silindirik_yuze_fixed`, `lineer`/`kalinlik`, `katalog_11_12`. Bir vaka Ansys'te koşulunca
ham JSON `tests/fixtures/katalog_<no>_<ad>.json` olarak eklenir ve durum "gerçek"e çekilir.
