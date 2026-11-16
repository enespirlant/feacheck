# feacheck — Ajan görev listesi

**Amaç:** Ansys Mechanical'da kurulmuş bir statik analizin sonucuna ne kadar güvenilebileceğini
(mesh yakınsaması/GCI, tekillik ayrımı, sınır şartı denetimi) otomatik ölçen araç; ilk hedef
kullanıcının kendi rover/İKA parçalarında güvenle kullanılabilmesi.

## Sonraki oturum planı (kullanıcıyla 15.11 kararlaştırıldı)
1. Genel güncelleme/geliştirme: R5 koşusunun ham JSON'u ile bugünkü yenilikleri doğrula (4. seviyeler,
   mesnet başına tepki, yüzey tipi, yeni rapor); çıkan hataları düzelt.
2. Güvenilirliği yükselt: katalog 7 ve 8 (ve mümkünse 1–3, 9) Ansys koşuları → gerçek fixture'lar, iç kuvvet
   eşiğinin ayarı; rover parçası pilotu (yük + el hesabı + feacheck).
3. Projeyi bitir: GitHub deposu, README son hali, demo, sınırlamalar; LinkedIn ilk paylaşım metni.
4. Kullanıcıya baştan sona anlatım: her modül ve her kararın nedeni (GCI, p kırpma, tekillik sınıflandırması,
   dışlama bölgesi, radyus serisi, karar izi), mülakat sorularına hazırlık.

Kullanıcının getireceği: R5 koşusu ham JSON'u (inbox), katalog 7/8 koşuları, rover parçası (STEP + araç kütlesi,
teker çapı, motor torku, bağlantı şekli).

## R5 4 seviyeli gerçek koşu (15.11 22:25) sonrası
- [x] Ansys'te doğrulandı: yüzey tipi okuma, mesnet başına tepki, eleman derecesi, radyus 4. seviye, yeni rapor.
- [x] HATA DÜZELTİLDİ: 'küçük değişim' kuralı aynı yönde büyüyen adımları (1,0 → 2,4 → 4,4 MPa) gürültü sayıp
      R5'i 'güvenilir 181,9' diyordu. Artık hızlanan artış reddediliyor; R5 = yakınsamadı, gösterge 186,2.
      README ve demo rapor düzeltildi.
- [x] Radyus serisinde hacim büyüme oranı 1,2. 22:34 koşusunda ETKİSİZ çıktı (adaptive sizing açıkken yok sayılıyor;
      düğüm sayıları birebir aynı). Düzeltme: seri boyunca UseAdaptiveSizing = False, değerler geri okunuyor. ANSYS'TE DENENMEDİ.
- [x] R5 23:04: adaptive sizing kapalı + büyüme 1,2 ile mesh değişti, seri yakınsadı (179,8 → 182,0 → 183,6), p = 0,70.
      p < 1 → Fs = 3 kuralı eklendi; GCI ≤ 2×eşik ise düşük güvenle bandın üstü (198,3 MPa) tasarım değeri.

## 15.11 akşam (kullanıcı yokken)
- [x] GCI, Celik vd. 2008 Tablo 1 çözülmüş örneğiyle birebir doğrulandı; e_ext eklendi.
- [x] El hesabı modülü handcalc.py + elhesap.yaml + rapor karşılaştırması (cetvelde aralık bandı, kontrol satırı, bölüm).
- [ ] Rover pilotunda handcalc ile yük/el hesabı birlikte. (Yük fonksiyonu + rover_girdi.yaml hazır; kullanıcı formu dolduracak)

## 17.11 gece
- [x] 16.11 R5 tekrarı: 15.11 koşusuyla birebir aynı → tekrarlanabilirlik testi.
- [x] Düz `pytest` yeşil (cadquery yoksa atlanır), GitHub Actions (ubuntu+windows, py3.10/3.12).
- [x] Montaj bağlantıları: şablon temas/mafsal/kiriş + gövde sayısı okuyor (ANSYS'TE DENENMEDİ); analiz: bağsız gövde,
      bonded, doğrusal olmayan temas, tepe temas yüzü yakınında; rapor tablosu; katalog 13–14.

## 17.11 gece (2. çalıştırma)
- [x] Öz test düğmesi (feacheck_oztest.py + feacheck katalog): 6 vaka, model her vakadan sonra geri alınır. ANSYS'TE DENENMEDİ.
- [x] Sürüm 0.2.0, CHANGELOG, docs/KULLANIM.md, --version.
- [x] docs/NASIL_CALISIR.md (öğrenme rehberi + kendini sına + 60 sn anlatım).
- [x] Büyüme üssü göstergesi karar mantığıyla uyumlu hale getirildi.

## Kullanıcıya sorulacak
- GitHub: depo herkese açık mı, kim gönderecek? Lisans (önerilen MIT).
- Rover pilotu için parça + yükler.

## Görevler (öncelik sırasıyla)

- [x] 1. Yanlış adlandırılmış `_v2` fixture'larını doğru adla kopyala ve golden teste bağla
      (`lbraket_r5_v2.json` aslında keskin köşe, `lbraket_keskin_v2.json` aslında R5)
- [x] 2. Radyus yüzüne otomatik yerel sıklaştırma: maksimum radyustaysa ve radyusta < 8 eleman varsa
      o yüze R/4 → R/6 → R/9 boyutlarıyla ek seri; analizde bu seriden tasarım gerilmesi; raporda gösterim
- [x] 3. Dışlama bölgesi: Lc/2 yerine mesnet/yük yüz alanına bağlı (√A, alt sınır 2·h0, üst sınır Lc/2)
- [x] 4. R5 el hesabı: birebir abak yok; alt sınır omuz radyusu Kt≈1,27 → ~168 MPa, üst sınır Winkler eğri kiriş → ~201 MPa; FEA 182–186 arada
- [x] 5. Radyus serisi için R1 / R2 L-braket STEP dosyaları (examples/make_lbraket.py; parts/ altına yazıldı). Ansys koşusu kullanıcıda
- [x] 6. Eleman derecesi kontrolü (Element Order = Linear ise uyarı)
- [x] 7. Kalınlık boyunca eleman sayısı uyarısı (t_eff / h_ince < 2)
- [x] 8. Mesnet başına tepki + iç kuvvet oranı Σ|R_i| / |ΣR_i| (aşırı kısıtlama uyarısı)
- [x] 9. Silindirik yüze Fixed Support uyarısı (ön kontrol)
- [x] 10. Hata kataloğu: `docs/HATA_KATALOGU.md` (12 vaka + yakalanamayanlar); Ansys koşuları kullanıcıda
- [x] 11. `feacheck converge` (PyMechanical yolu) boyutları kendisi hesaplıyor: kalınlık sınırı (2V/A) ve
      ayarlar.yaml orada uygulanmıyor; şablonun kendi hesabına bırakılmalı
- [x] 12. Radyus serisi gerçek veriyle gelince sentetik fixture'ların yanına gerçek golden test ekle

## Kullanıcıya sorulacak / kullanıcının yapacağı
- ~~Ansys'te yapılacak~~ (15.11 yapıldı, sonuç PROGRESS.md'de): `L_braket_R5.step` ile butona bas (sınır şartları
  TALIMAT'taki gibi). Beklenen: global seri "çözünürlük yetersiz", ardından otomatik radyus serisi
  (yerel h ≈ 1,25 → 0,83 → 0,56 mm, radyusta 6 → 9 → 14 eleman). Rozet "GÜVENİLİR · RADYUS YEREL
  SIKLAŞTIRMAYLA ÇÖZÜLDÜ" olmalı. Ham JSON'u (`C:\Users\pirla\feacheck\inbox\raw_*.json`) bana ver.
- Eski `_v2` fixture adları ters (silme izni olmadığı için silinmedi); istersen elle silebilirsin.
- [x] 14. İngilizce README (README.en.md) + Türkçe README'de L-braket satırları
- [x] 15. Demo: örnek HTML raporları (keskin köşe + R5) examples/ altına, README'ye ekran görüntüsü
- [x] 13. Radyus serisinde 4. seviye seçeneği (küçük değişimde yön belirsizse bir adım daha çöz)
