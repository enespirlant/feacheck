# feacheck kullanım kılavuzu

feacheck, Ansys Mechanical'daki doğrusal statik bir analizin gerilme sonucuna güvenilip güvenilemeyeceğini söyler:
sahte (tekil) tepeyi gerçek gerilme yığılmasından ayırır, sonucun mesh'e bağlı belirsizliğini (GCI) ölçer, tasarımda
kullanılacak ihtiyatlı değeri ve kurulum hatalarını raporlar.

## 1. Kurulum (bir kez)

```
conda create -n cadfea python=3.12 -y
conda activate cadfea
pip install -e .
feacheck setup
```

`feacheck setup` iki Mechanical düğmesi ve bir masaüstü kısayolu kurar, ekrana kopyalanacak satırları yazar:

| Dosya | Ne işe yarar |
|---|---|
| `feacheck_button.py` | Seçili analizi kontrol eder, rapor açar (her gün kullanacağın düğme) |
| `feacheck_oztest.py` | Öz test: hata kataloğunu bu model üzerinde koşar (bölüm 5) |
| `feacheck.bat` (masaüstü) | `.mechdb` dosyasını üzerine sürükle-bırak: Mechanical'ı açmadan kontrol |

Düğmeyi kalıcı yapmak için satırı Mechanical › Automation › Manage (User Buttons) ile kaydet. Düğmeler her
çalıştırmada en güncel feacheck kodunu üretir; kodu güncelleyince `setup`'ı tekrarlaman gerekmez.

## 2. Günlük kullanım

1. Modelini her zamanki gibi kur: geometri, malzeme, mesnetler, yükler. Mesh'i varsayılanda bırak.
2. Ağaçta analizine tıkla, feacheck düğmesine bas.
3. Malzeme penceresinde akma dayanımını onayla ya da değiştir.
4. Birkaç dakika sonra rapor tarayıcıda açılır.
5. feacheck mesh'i son seviyede bırakır: kendi sonuçların için bir kez daha **Solve** et.

Raporlar ve geçmiş veri klasöründedir (`C:\Users\<sen>\feacheck`): `feacheck log` listeler, `feacheck show <no>` açar.

## 3. Raporu okumak

Yukarıdan aşağı, karar için gereken sırayla:

- **Başlık ve renk** — tek cümlelik hüküm. Yeşil: güvenilir. Turuncu: tekillik ayrıldı, belirsizlik geniş ya da çözülmedi.
  Kırmızı: analiz tamamlanamadı.
- **Büyük sayı** — tasarımda kullanacağın ihtiyatlı gerilme. Gri ve "gösterge" yazıyorsa tasarımda kullanma.
- **Gerilme cetveli** — reddedilen sahte tepe (üstü çizili), tasarım değeri, el hesabı bandı ve akma aynı eksende.
- **Kontroller** — her satır bir soru: mesh yakınsadı mı, tekillik var mı, denge tutuyor mu, mesh kalitesi, model
  kurulumu, emniyet katsayısı, el hesabı.
- **Bulgular ve yapılacaklar** — önce kurulum uyarıları (bunları düzeltmeden sonuç anlamsız), sonra açıklamalar.
- **Sahte tepe mi, gerçek gerilme mi?** — kırmızı çizgi her incelmede yükseliyorsa tekillik, yataylaşıyorsa gerçek.
- **Nerede?** — mesnet/yük yüzleri, dışlama bölgeleri, sahte tepe ve tasarım noktası. Yanlış yüze sınır şartı vermeyi
  buradan yakalarsın.
- **Sayısal belirsizlik** — GCI hesabı gerçek sayılarla adım adım.

Güven düzeyleri: **yüksek** (yakınsama teorik mertebeyle tutarlı), **orta** (yalnız bir bölge inceldi ya da mertebe
aralığın kenarında), **düşük** (yakınsama zayıf doğrulandı; değer GCI bandının üstünden alınır).

## 4. El hesabıyla karşılaştırma

Veri klasöründeki `elhesap.yaml`'a model adında geçen bir anahtarla değer ya da aralık yaz:

```yaml
Konsol aks:
  deger: 113.3          # tek değer, varsayılan tolerans ±%10
  tolerans: 5
L_braket_R5:
  alt: 168              # iki bağımsız el hesabıyla sınırlanan durum
  ust: 201
  aciklama: "Alt: omuz radyusu Kt (Peterson). Üst: Winkler eğri kiriş."
```

Hesaplar için `feacheck/handcalc.py`: kiriş eğilme/burulma, konsol sehimi, von Mises, Winkler eğri kiriş, delikli levha
Kt, mil omzu Kt (eğilme/çekme/burulma). Örnek:

```python
from feacheck import handcalc as h
kt = h.kt_shaft_shoulder(D=25, d=20, r=1.5, load="bending")["value"]
sigma = kt * h.bending_round(M_Nmm=40_000, d=20)["value"]
```

Eğri uydurmaları geçerlilik aralığı dışında hata verir; kaynakları sonucun `source` alanında yazar.

## 4b. Araç yükü kıyası (rover/İKA)

Veri klasöründeki `arac.yaml`'a aracı **bir kez** yaz: kütle, teker sayısı, teker çapı, motor torku (dişli oranı,
verim ve varsayımlar önerilen değerlerle gelir). Parça bilgisi (malzeme, mesnet, kuvvet) Ansys modelinden okunur;
parça başına form yok.

`arac.yaml` doluysa buton bitişte tek soru sorar: modeldeki kuvvet teker başına **düşey / çekiş / yanal** yükten hangisi
(0 = araç yükü değil). Seçim model adına göre `yuk_tipleri.txt`'de hatırlanır; sonraki koşularda OK'a basman yeterli.
Raporda "Araç yükü" satırı çıkar: modeldeki kuvvet beklenenin %95'inden azsa kırmızı bulgu, 2 katından fazlaysa
"çok ihtiyatlı" uyarısı. Hesap en yüklü teker için: Fz = k_dyn·k_teker·mg/n, Fx = min(T·i·η/r, μ·k_teker·mg/n), Fy = μy·k_teker·mg/n.
`k_teker` = en yüklü teker / ortalama (rampa, fren, engel). Aracın kendi hesabında teker başı çekiş varsa
`cekis_tasarim` (N) yaz, doğrudan kullanılır. `verim` yalnız dişli kaybıdır: tork motor milinde ölçülmüşse ve dişli
yoksa 1. T_teker = Fx·r tekere gelen torktur, eğilme momenti değil.

## 5. Öz test

Bir modeli aç, analizine tıkla, `feacheck_oztest.py`'yi çalıştır. Araç modeli sırayla bilerek bozar (lineer eleman,
5 kat yük, ikinci Fixed, eğri yüze Fixed, mesnetsiz), her vakada feacheck'i koşar ve **modeli her vakadan sonra geri
alır**. Sonunda `ozet.html` hangi hatayı yakaladığını geçti/kaldı tablosuyla gösterir. Ayrıntı: `docs/HATA_KATALOGU.md`.

## 6. Ayarlar (`ayarlar.yaml`)

| Anahtar | Varsayılan | Anlamı |
|---|---|---|
| `dugum_limiti` | 128000 | En ince mesh'in düğüm sınırı (öğrenci lisansı) |
| `gci_esigi_yuzde` | 5 | Bu GCI'ın altı "güvenilir"; 2 katına kadar "geniş belirsizlik" |
| `mesh_seviye_sayisi` | 3 | Global seri seviye sayısı (3 önerilir; düğüm limiti en ince mesh'i sabitler) |
| `incelme_orani` | 1,5 | Seviyeler arası eleman boyu oranı |
| `yerel_siklastirma` | false | Global yerine sıcak bölge yüzlerini incelt |
| `radyus_siklastirma` | true | Tepe çözülmemiş bir radyustaysa radyus serisi koş |
| `radyus_ek_seviye` | true | Radyus serisinde gerektiğinde 4. seviye |
| `global_ek_seviye` | true | Global seride gerektiğinde 4. seviye |
| `radyus_buyume_orani` | 1,2 | Radyus serisinde hacim büyüme oranı (0 = kapalı) |

## 7. Sınırlar

- Yalnız doğrusal statik, katı modeller. Kabuk/kiriş eleman ve doğrusal olmayan malzeme desteklenmez.
- Temaslı modellerde bağlantı türü tespit edilir ve uyarılır, ama temasın doğruluğu (ön yük, sürtünme) ölçülmez.
- feacheck **doğrulama** (verification) yapar: denklemin bu mesh'te doğru çözülüp çözülmediğini. Modelin gerçek parçayı
  doğru temsil edip etmediği (validation: yük, mesnet, malzeme) kullanıcının sorumluluğudur; el hesabı ve konum haritası
  bunu kontrol etmene yardım eder.
- Yanlış yüze yük, yanlış malzeme ya da yanlış yük büyüklüğü otomatik yakalanmaz (bkz. hata kataloğu).
