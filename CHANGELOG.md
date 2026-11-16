# Değişiklik günlüğü

## Yayınlanmamış

### Eklendi
- `examples/make_lbraket.py`: L-braket STEP üretici (R0/R5 mevcut dosyalarla birebir aynı hacim ve yüzler; R1, R2 üretildi).
- `handcalc.rover_wheel_loads`: teker başına düşey/tasarım/çekiş/yanal yük ve aks momenti; çekişi motor ya da zemin sınırlar.
- `examples/rover_girdi.yaml`: rover pilotu için doldurulacak girdi formu.

## 0.2.0 (2026-11-17)

Gerçek Ansys koşularıyla sınanan ilk sürüm. Her "düzeltildi" maddesi gerçek bir koşunun yakaladığı bir hatadır ve
o koşunun ham sonucu `tests/fixtures/` altında regresyon testidir.

### Eklendi
- **Radyus yerel sıklaştırma serisi.** Tepe bir radyusta ve global mesh onu çözemiyorsa yalnız radyus yüzü R/4 → R/6 →
  R/9 inceltilir; seri boyunca adaptive sizing kapatılıp büyüme oranı 1,2 yapılır ki radyusun altındaki hacim de incelsin.
- **Uyarlamalı 4. seviye** (global ve radyus serisi): değişim gürültü düzeyinde ama yönü belirsizse ve düğüm bütçesi
  yetiyorsa bir seviye daha çözülür.
- **Dışlama bölgesi √A kuralı**: max √(yüz alanı), alt sınır 2·h₀, üst sınır L꜀/2.
- **Kurulum kontrolleri**: silindirik/eğri yüze Fixed Support, mesnet başına tepki ve iç kuvvet oranı (aşırı kısıtlama),
  eleman derecesi, kalınlık boyunca eleman sayısı, montaj bağlantıları (bağsız gövde, bonded, doğrusal olmayan temas,
  tepe temas kenarında).
- **El hesabı modülü** (`handcalc.py`) ve `elhesap.yaml` ile otomatik karşılaştırma.
- **Öz test düğmesi**: hata kataloğunu Mechanical içinde tek tıkla koşar, modeli her vakadan sonra geri alır.
- **Rapor**: hüküm cümlesi, gerilme cetveli, kontrol listesi, yakınsama grafiği (h→0, GCI bandı), büyüme üssü göstergesi,
  konum haritası, adım adım GCI, denge/mesh grafikleri, Türkçe sayı biçimi.
- `feacheck --version`, GitHub Actions (Windows + Linux).

### Düzeltildi
- **Hızlanan artış gürültü sayılıyordu.** R5 radyus serisi 178,4 → 179,5 → 181,9 → 186,2 MPa (adımlar büyüyor) "küçük
  değişim" kuralıyla "güvenilir" ilan ediliyordu. Artık yalnız salınım ya da küçülen adım kabul edilir.
- **Büyüme oranı sessizce yok sayılıyordu.** Adaptive sizing açıkken `Mesh.GrowthRate` hatasız atanıyor ama mesh
  değişmiyordu (düğüm sayıları birebir aynı); rapor yine "1,2" yazıyordu. Adaptive sizing kapatılıyor, rapor Ansys'ten geri
  okunan değeri yazıyor.
- **Düşük görünen mertebede iyimser güvenlik çarpanı.** p = 0,70 (kuadratik elemanda beklenen ≈ 2) iken Fs = 1,25
  kullanılıyordu. Artık p < 1 → Fs = 3 (Roache 1998), güven düşük, tasarım değeri GCI bandının üstü.
- Radyus çözüldüğünde raporda kalan çelişkili "çözünürlük yetersiz" bulgusu.
- `feacheck converge` yolunun kalınlık sınırını ve `ayarlar.yaml`'ı uygulamaması.

### Doğrulandı
- GCI, Celik vd. (2008) Tablo 1 çözülmüş örneğini birebir üretiyor.
- Aynı model iki ayrı günde son haneye kadar aynı sonucu veriyor.

## 0.1.0 (2026-11-14)
- İlk sürüm: üç seviyeli global mesh serisi, GCI, tekillik ayrımı (sınır şartı / geometrik / çözülmemiş radyus),
  güvenilir tasarım gerilmesi ve karar izi, HTML rapor, Mechanical butonu.
