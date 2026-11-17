# LinkedIn ilk paylaşım taslağı (onay bekliyor, yayınlanmadı)

Ansys'te bir analiz çalıştırdın, renkli bir gerilme haritası çıktı. Peki sonuca ne kadar güvenebilirsin?

Bunu otomatik ölçen bir araç yazdım: **feacheck**. Ansys Mechanical içinde tek tuşla çalışıyor:

- Mesh'i kendisi inceltip yakınsamayı ölçüyor (GCI, Celik 2008 çözümlü örneğiyle birebir doğrulandı)
- Keskin köşedeki sahte tekil gerilmeyi gerçek yığılmadan ayırıyor
- Sonucu bağımsız bir el hesabıyla karşılaştırıyor
- Modeli hata için denetliyor (aşırı kısıtlama, eksik yük, lineer eleman) ve Türkçe HTML rapor üretiyor

Gerçek bir L-braket üzerinde: keskin köşe hariç 133,7 MPa, el hesabı 133,3 MPa (%0,3 fark). R5 radyusunda ihtiyatlı tasarım değeri 198,3 MPa, el hesabı aralığı 168–201 MPa. Aynı model iki ayrı günde birebir aynı çıktı.

Önemli bir ders: yakınsama düşük mertebedeyse (p < 1) araç emniyet katsayısını kendisi büyütüyor ve "geniş belirsizlik" diyor. Güvenilir olmayan sonucu güvenilir göstermemek en önemli kısmıydı.

İKA ve rover parçalarımda kullanmak için yaptım; MIT lisansıyla açık: https://github.com/enespirlant/feacheck

#FEA #Ansys #MechanicalEngineering #Python
