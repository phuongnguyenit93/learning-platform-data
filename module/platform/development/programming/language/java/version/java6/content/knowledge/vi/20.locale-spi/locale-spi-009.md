# Locale SPI: Phân biệt cơ chế mở rộng với dữ liệu locale thay đổi theo phiên bản

## Mục tiêu của bài

Một chương trình Java có thể gọi **NumberFormat.getNumberInstance(locale)**, **Locale.getDisplayLanguage(locale)** hoặc **DateTimeFormatter.ofLocalizedDate(...)** bằng cùng source code trong nhiều năm nhưng nhận được một số chuỗi hiển thị khác nhau sau khi nâng cấp JDK. Đó **không nhất thiết là API bị phá vỡ**: phần lớn API vẫn có cùng hợp đồng, còn **dữ liệu địa phương hóa (locale data)** được cập nhật theo phiên bản CLDR/JDK. Ngược lại, **Locale Service Provider Interface (Locale SPI)** là **cơ chế mở rộng bằng Java code** để thêm hoặc ưu tiên các dịch vụ định dạng/tên địa phương hóa cho những Locale được công bố.

Hai vấn đề này liên quan nhưng không đồng nhất:

- **Cơ chế mở rộng:** ứng dụng tự triển khai một provider, đóng gói/đăng ký nó, quyết định dịch vụ và Locale được hỗ trợ; runtime lựa chọn provider theo thứ tự adapter.
- **Dữ liệu thay đổi:** runtime cập nhật dữ liệu CLDR hoặc dữ liệu quốc tế hóa khác; cùng method/Locale/input có thể cho ra ký hiệu, tên, pattern hoặc chuỗi khác giữa các bản JDK.

Bài học dưới ngữ cảnh **Locale SPI** giúp bạn phân biệt nguồn kết quả, xây test đúng, lựa chọn lúc nào phải dùng SPI và chuẩn bị nâng cấp JDK an toàn. Sau bài này, bạn có thể:

1. Giải thích vì sao **API compatibility** không đồng nghĩa **locale output byte-for-byte compatibility**.
2. Phân biệt **Locale metadata**, **CLDR data**, **SPI implementation**, **HOST adapter**, **application resources** và dữ liệu timezone/currency có nguồn riêng.
3. Hiểu cách dùng **java.locale.providers=SPI,CLDR** để ưu tiên SPI, và vì sao **ServiceLoader** tìm được implementation chưa chứng minh các factory JDK dùng nó.
4. Triển khai ví dụ **LocaleNameProvider** có service descriptor, chạy so sánh **SPI,CLDR** với **CLDR-only** trên hai JVM riêng.
5. Quan sát localized number/date/name output như một **runtime snapshot**, không giả định nó giữ nguyên qua các phiên bản JDK/CLDR.
6. Lập **compatibility test matrix** và golden tests có phân biệt những gì được sản phẩm kiểm soát với những gì là dữ liệu của runtime.
7. Biết các lựa chọn khi sản phẩm cần output ổn định: explicit pattern/symbols, bundle riêng, custom SPI hoặc cố định phiên bản runtime, cùng giới hạn của từng cách.

**Phiên bản áp dụng:** Nội dung sử dụng API chuẩn Java 17+ còn được hỗ trợ trên JDK hiện đại. Ví dụ được kiểm thử bằng **OpenJDK 24.0.2** với **javac --release 17**. Dữ liệu CLDR của từng JDK được đối chiếu tài liệu **LocaleServiceProvider Java SE 26**; không dùng các tùy chọn legacy locale data đã bị loại bỏ làm khuyến nghị hiện hành.

## 1. Ba lớp cần tách riêng trong quốc tế hóa

Trong một ứng dụng Java, kết quả địa phương hóa thường đi qua ba lớp:

~~~text
Ứng dụng gọi API (hợp đồng Java)
       │
       ▼
Locale-sensitive service lookup
       │
       ├── CLDR  ← dữ liệu locale đi cùng JDK
       ├── SPI   ← implementation do ứng dụng/thư viện cung cấp
       └── HOST  ← thiết lập host OS nếu JDK/nền tảng hỗ trợ
       │
       ▼
Đối tượng/giá trị trả về
       │
       ├── NumberFormat, DateFormat, Collator...
       ├── Tên hiển thị language/country/currency...
       └── Patterns, symbols, localized output
~~~

**Lớp 1 — API:** Các class và phương thức như **Locale**, **NumberFormat**, **DateTimeFormatter**, **Currency**, **LocaleServiceProvider**. Source program có thể giữ nguyên khi phiên bản runtime đổi.

**Lớp 2 — nguồn dữ liệu và implementation:** Một lời gọi có thể dùng dữ liệu **CLDR** do JDK đi kèm, một provider **SPI** đã triển khai riêng, hoặc dữ liệu **HOST** nếu được hỗ trợ. Đây là nơi thứ tự lựa chọn ảnh hưởng kết quả.

**Lớp 3 — dữ liệu thực tế:** Thứ tự ngày/tháng/năm, tên tháng, tên vùng, dấu phân nhóm, ký hiệu tiền tệ, khoảng trắng Unicode và những pattern có thể thay đổi. Những khác biệt ở đây không tự chứng minh Java API đã thay đổi signature hoặc contract.

### 1.1. Bảng so sánh nhanh

| Câu hỏi | Cơ chế mở rộng SPI | Dữ liệu locale trong JDK/CLDR |
| --- | --- | --- |
| Ai cung cấp? | Tác giả ứng dụng/thư viện triển khai Java provider | JDK cung cấp dữ liệu nhập từ CLDR và xử lý của runtime |
| Điều gì thay đổi? | Java class, service registration, algorithm, local data do provider quản lý | Localized patterns, names, symbols, quy tắc/coverage cập nhật |
| Cơ chế truy cập | Locale-sensitive API gọi provider nếu adapter selection chọn SPI | Locale-sensitive API dựa trên CLDR adapter |
| Phụ thuộc version JDK? | API SPI vẫn có contract; runtime selection/compatibility cần test | Nội dung dữ liệu có thể khác giữa các JDK releases |
| Có cần viết code provider? | Có, nếu muốn tự thêm/ghi đè dịch vụ | Không, nếu chỉ dùng dữ liệu JDK |
| Kiểm thử ra sao? | Test discovery, provider selection, output do mình định nghĩa | So sánh behavior giữa JDK versions, policy-based assertions |
| Khả năng kiểm soát | Cao với logic/data tự quản, nhưng chịu quy tắc runtime | Phụ thuộc runtime, JDK vendor/version và cập nhật dữ liệu |
| Dùng khi nào? | Thật sự cần bổ sung/override locale service | Muốn hỗ trợ locale chuẩn và theo cập nhật quốc tế hóa |

**Ví dụ:** Nếu ứng dụng định nghĩa provider để hiển thị tên ngôn ngữ **fr** bằng câu riêng ở một test Locale, đó là **extension**. Nếu JDK mới đổi tên một vùng, dấu thập phân hoặc pattern ngày do cập nhật CLDR, đó là **data evolution**. Hai sự kiện có thể đồng thời xảy ra nhưng phải chẩn đoán riêng.

## 2. Locale là định danh, không phải bản sao bất biến của dữ liệu định dạng

**java.util.Locale** mô tả các thành phần như:

- **Language**: vi, en, fr, zh.
- **Script**: Latn, Hant, Cyrl.
- **Region**: VN, US, FR.
- **Variant**: biến thể theo convention.
- **Unicode locale extensions**: chẳng hạn **nu** cho numbering system, **ca** cho calendar.

Một Locale cụ thể:

~~~java
// Mảnh code Java minh họa, không phải file độc lập.
Locale vietnamese = Locale.forLanguageTag("vi-VN");
String tag = vietnamese.toLanguageTag(); // "vi-VN"
~~~

**Tag vi-VN là định danh locale**, không chứa bản sao của mọi pattern số, tên tháng, ký hiệu tiền hoặc date styles. Do đó, chỉ vì **vi-VN** không đổi giữa JDK 17 và JDK 26, bạn không thể suy ra mọi lời gọi formatter sẽ trả đúng cùng chuỗi.

### 2.1. Bốn loại thông tin dễ bị đánh đồng

| Thông tin | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Locale tag | **vi-VN** | Locale mà caller yêu cầu |
| Dữ liệu CLDR | decimal/grouping symbols, tên tháng, date patterns | Một bộ dữ liệu của runtime, có phiên bản |
| Provider implementation | **DemoLocaleNameProvider** | Code mở rộng của ứng dụng |
| Chuỗi đã định dạng | **1.234.567,89**, **1 tháng 9, 2024** | Output chịu ảnh hưởng data/provider/options |

**Locale không có thuộc tính “CLDR version” riêng.** Muốn biết dữ liệu của runtime thuộc phiên bản nào, phải xem JDK release/documentation hoặc build metadata của runtime chứ không suy ra từ **Locale.toLanguageTag()**.

### 2.2. Unicode extensions cũng ảnh hưởng kết quả

Một locale có **-u-nu-latn** có thể yêu cầu hệ chữ số Latin. Một locale có **-u-ca-...** có thể chỉ định calendar preference. Quy tắc hỗ trợ phụ thuộc API, provider và dữ liệu đi kèm.

**isSupportedLocale(Locale)** mặc định trong LocaleServiceProvider kiểm tra Locale sau khi bỏ extensions khi so với những Locale trong **getAvailableLocales()**. Nếu provider thực sự hỗ trợ một số extensions và phải từ chối phần khác, nó có thể override isSupportedLocale cho đúng contract, thay vì so sánh locale equality một cách cứng nhắc.

Không nên tuyên bố một provider tự hiểu mọi Unicode extension chỉ vì nó công bố locale gốc.

## 3. Locale SPI là gì và những điểm mở rộng còn áp dụng

**java.util.spi.LocaleServiceProvider** là superclass cho các provider phục vụ locale-sensitive operations trong **java.util** và **java.text**. Những provider cụ thể phổ biến:

| SPI | Chức năng |
| --- | --- |
| **NumberFormatProvider** | Tạo number/integer/currency/percent formatters |
| **DecimalFormatSymbolsProvider** | Cung cấp symbols cho decimal formatting |
| **DateFormatProvider** | Cung cấp date/time formatters thuộc java.text |
| **DateFormatSymbolsProvider** | Cung cấp tên tháng, ngày/tuần và symbols liên quan |
| **LocaleNameProvider** | Cung cấp tên hiển thị language/region/variant/script |
| **CurrencyNameProvider** | Cung cấp tên và ký hiệu tiền tệ theo display locale |
| **TimeZoneNameProvider** | Cung cấp tên localized time zones |
| **CollatorProvider** | Cung cấp locale-aware collation |
| **BreakIteratorProvider** | Cung cấp cách tìm ranh giới ký tự/từ/câu |
| **CalendarDataProvider / CalendarNameProvider** | Cung cấp dữ liệu/tên calendar cho các API tương ứng |

Đây là **các lớp SPI chuẩn**, vẫn hiện diện trong tài liệu Java SE 26. Dù một SPI được hỗ trợ, không có nghĩa mọi API mới trong hệ sinh thái Java đều nhất thiết gọi vào đúng SPI đó. Ví dụ **java.time** có cách tổ chức riêng; không khẳng định DateFormatProvider của **java.text** sẽ tự ghi đè mọi **DateTimeFormatter** hoặc every java.time API.

### 3.1. Hợp đồng chung

Provider thường có:

~~~java
// Mảnh minh họa ý tưởng, không phải một class hoàn chỉnh.
@Override
public Locale[] getAvailableLocales() {
    return new Locale[] { Locale.forLanguageTag("qaa-QA") };
}
~~~

**getAvailableLocales()** công bố những locale provider hỗ trợ; API **isSupportedLocale(...)** kiểm tra yêu cầu theo contract. Các method chuyên biệt trả object hoặc localized name phù hợp. Không công bố Locale chỉ để “được gọi”, rồi trả dữ liệu sai/không hỗ trợ cho mọi method.

Có hai vấn đề độc lập:

1. **Discovery:** JVM có tìm được implementation qua service registration hay không?
2. **Selection:** Khi một locale-sensitive factory được gọi, adapter order và Locale support có đưa yêu cầu đến provider hay không?

Đây chính là chỗ khác biệt giữa một **extension mechanism** và **dữ liệu JDK đã có**.

### 3.2. Classpath và module path

Với **classpath/unnamed module**, provider thường khai báo resource:

~~~text
META-INF/services/java.util.spi.LocaleNameProvider
~~~

Nội dung:

~~~text
demo.spi.DemoLocaleNameProvider
~~~

Tên file là **fully qualified service interface/abstract class name**; nội dung là tên Java class implementation. Descriptor phải được đóng gói cùng output, theo format UTF-8 của ServiceLoader. Provider cần constructor/cơ chế khởi tạo phù hợp và được runtime system classloader nhìn thấy.

Với **named module**, provider dùng **provides ... with ...**:

~~~java
// Mảnh minh họa module-info.java; cần module path/launch phù hợp.
module demo.localedata {
    provides java.util.spi.LocaleNameProvider
            with demo.spi.DemoLocaleNameProvider;
}
~~~

Đừng coi việc một class Java được compile thành công là bằng chứng service descriptor/provider declaration đã có trong bản JAR/module cuối.

## 4. CLDR và lý do dữ liệu có thể thay đổi qua JDK releases

**Unicode Common Locale Data Repository (CLDR)** là nguồn dữ liệu quốc tế hóa được JDK Reference Implementation dùng cho nhiều localized services. Dữ liệu bao gồm tên ngôn ngữ/vùng, patterns, symbols và quy tắc biểu diễn khác.

**CLDR là dữ liệu được duy trì và cập nhật**, không phải một tập hằng số bất biến của Java API. Khi JDK chuyển sang một version CLDR mới, cùng code và cùng Locale có thể cho ra khác biệt ở output; những thay đổi đó có thể là sửa lỗi dữ liệu hoặc cập nhật tập quán/chuẩn bản địa hóa.

### 4.1. Ví dụ version mapping theo tài liệu Java SE 26

| Dòng JDK | Phiên bản CLDR mà tài liệu LocaleServiceProvider JDK 26 liệt kê |
| --- | --- |
| JDK 17 | **CLDR 39** |
| JDK 21 | **CLDR 43** |
| JDK 23 | **CLDR 45** |
| JDK 24 | **CLDR 46** |
| JDK 25 | **CLDR 47** |
| JDK 26 | **CLDR 48** |

**Đây là thông tin từ bảng mapping của tài liệu JDK 26**, không phải kết quả đo tự động từ mỗi JDK trong ví dụ. Bài thực hành ở phần 8 chỉ chạy trên **JDK 24.0.2**.

Các phiên bản CLDR khác nhau **không bảo đảm một output cụ thể sẽ khác**: một pattern có thể giữ nguyên giữa nhiều releases. Nhưng ứng dụng **không nên dựa trên giả định chúng luôn giống nhau**. Giai đoạn nâng cấp JDK nên dùng regression tests của sản phẩm để phát hiện những thay đổi có ý nghĩa.

### 4.2. Những gì có thể thay đổi

- **Date/time formatting:** thứ tự thành phần ngày, tên tháng, tên thứ, punctuation, spacing, dạng giờ.
- **Number formatting:** grouping/decimal separators, grouping conventions, digit displays tùy locale.
- **Currency display:** tên, symbol hoặc cách trình bày theo locale.
- **Language/region naming:** tên hiển thị các nước/vùng/ngôn ngữ, thay đổi chính tả hoặc cách gọi chính thức.
- **Localized sorting:** collation hoặc danh sách variants/locale data có thể được nâng cấp.
- **Time-zone display names:** tên vùng, GMT patterns, localized names.
- **Coverage:** thêm/sửa các vùng và dữ liệu cho những locale ít phổ biến.

Không nên coi từng yếu tố ở đây là cố định trong **Java SE specification**. Khi một sản phẩm có snapshot tests so sánh từng ký tự của formatted output, nâng cấp dữ liệu hợp lệ có thể làm test fail.

### 4.3. Dữ liệu không chỉ đến từ CLDR

**Timezone transition rules** thường đến từ dữ liệu múi giờ (tzdb), khác với **localized time-zone names** thường liên quan CLDR. **Currency codes/region mapping** còn có chuẩn và lịch cập nhật riêng. **HOST** có thể phản ánh tùy chỉnh hệ điều hành nếu provider đó tồn tại. Dữ liệu app như **ResourceBundle** hay danh mục dịch của sản phẩm lại thuộc quyền kiểm soát khác.

Khi có output khác nhau, hãy xác định **nguồn nào đã đổi** trước khi đổ mọi thay đổi vào “CLDR”. Một ứng dụng có thể đồng thời nâng JDK, CLDR, tzdb, application bundle và phiên bản thư viện.

## 5. java.locale.providers: chọn nguồn thay vì sửa dữ liệu

Java cung cấp **system property java.locale.providers** để cấu hình thứ tự ưu tiên các locale-sensitive providers.

Những adapter identifiers còn được JDK Reference Implementation hiện đại mô tả:

| Giá trị | Ý nghĩa |
| --- | --- |
| **CLDR** | Locale data của runtime dựa trên Unicode CLDR |
| **SPI** | Các LocaleServiceProvider implementations do ứng dụng/thư viện đăng ký |
| **HOST** | Thiết lập OS, nếu runtime và nền tảng hỗ trợ |

Ví dụ:

~~~bash
java -Djava.locale.providers=SPI,CLDR -cp build demo.app.LocaleDataDemo
~~~

Ý nghĩa: **thử SPI trước**, rồi CLDR nếu dịch vụ/locale không do SPI đáp ứng.

Ngược lại:

~~~bash
java -Djava.locale.providers=CLDR -cp build demo.app.LocaleDataDemo
~~~

chỉ chọn nguồn CLDR cho các locale-sensitive service lookups của JDK trong phạm vi áp dụng. **Đây không phải cách gỡ provider class khỏi classpath**; ServiceLoader vẫn có thể thấy nó nếu descriptor còn đó.

**Đặt property ở lệnh khởi động JVM.** Theo contract LocaleServiceProvider, thứ tự lookup được đọc và cache ở giai đoạn khởi tạo; thay bằng **System.setProperty** sau khi các locale services đã dùng không phải cách kiểm thử đáng tin.

### 5.1. Mặc định trên JDK hiện đại

Theo tài liệu Java SE 26, default adapter order của JDK Reference Implementation về cơ bản là **CLDR** nếu ứng dụng không cung cấp cấu hình khác. Vì vậy chỉ thêm **META-INF/services** chưa chắc đủ để các factory JDK chọn code extension của bạn.

**Cần phân biệt hai kết luận:**

- **ServiceLoader tìm được provider:** service configuration hợp lệ và class có thể nạp.
- **Factory/locale lookup thực sự dùng provider:** phải xác minh adapter order, locale support và behavior tại điểm gọi.

### 5.2. Không khôi phục locale data cũ bằng một adapter đã bị loại

Các tài liệu trước đây có thể nhắc đến **JRE** hoặc **COMPAT** data adapters. Những cơ chế này **không còn là lựa chọn khả dụng trên JDK 23 trở lên**: JDK 23 đã loại dữ liệu locale legacy, nên cấu hình JRE/COMPAT không còn tác dụng. Với code mới hoặc bản nâng cấp hiện đại, không dùng cách “đặt COMPAT để khôi phục nguyên output cũ” làm phương án duy trì dài hạn.

Nếu sản phẩm thực sự cần format cũ, hãy mô tả pattern/symbols trong application policy, quản lý data riêng hoặc một provider có hợp đồng rõ; sau đó kiểm thử, thay vì trông đợi JDK mới tiếp tục chứa một bộ dữ liệu đã bị loại.

## 6. Ví dụ đối chiếu: cùng service, khác nguồn được chọn

Bài thực hành dùng **LocaleNameProvider** thay vì NumberFormatProvider để tập trung vào sự khác biệt giữa **mở rộng logic** và **dữ liệu tên locale**.

Tạo provider cho **display Locale** giả lập **qaa-QA**, với một kết quả cố ý dễ nhận biết:

~~~text
French from custom SPI
~~~

Khi adapter order **SPI,CLDR**, provider trả về đúng câu trên cho tên hiển thị của ngôn ngữ **fr**. Khi adapter order **CLDR**, provider vẫn được ServiceLoader tìm thấy nhưng **Locale.FRENCH.getDisplayLanguage(...)** dùng dữ liệu runtime, không sử dụng câu do provider viết.

**qaa-QA là Locale dành riêng cho bài test, không phải quy tắc bản địa hóa thực tế của một quốc gia hoặc ngôn ngữ.** Không sử dụng câu demo trong UI production.

### 6.1. Cấu trúc bài thực hành

~~~text
locale-spi-vs-data/
├── src/
│   └── demo/
│       ├── spi/DemoLocaleNameProvider.java
│       └── app/LocaleDataDemo.java
└── resources/
    └── META-INF/services/
        └── java.util.spi.LocaleNameProvider
~~~

Chương trình còn in hai chuỗi định dạng từ Locale **vi-VN** của JDK:

- Một **number formatting sample** với số 1234567.89.
- Một **localized date sample** với ngày cố định **2024-09-01**.

Hai dòng này được xem là **runtime locale-data observations**, không phải lời hứa rằng mọi JDK về sau phải in đúng y hệt.

### 6.2. Provider class hoàn chỉnh

**src/demo/spi/DemoLocaleNameProvider.java**

~~~java
package demo.spi;

import java.util.Locale;
import java.util.spi.LocaleNameProvider;

public final class DemoLocaleNameProvider extends LocaleNameProvider {
    private static final Locale DISPLAY = Locale.forLanguageTag("qaa-QA");

    public DemoLocaleNameProvider() {}

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { DISPLAY };
    }

    @Override
    public String getDisplayLanguage(String languageCode, Locale displayLocale) {
        if (!DISPLAY.equals(displayLocale.stripExtensions())) {
            throw new IllegalArgumentException("Unsupported display locale");
        }
        return "fr".equals(languageCode) ? "French from custom SPI" : null;
    }

    @Override
    public String getDisplayCountry(String countryCode, Locale displayLocale) {
        return null;
    }

    @Override
    public String getDisplayVariant(String variant, Locale displayLocale) {
        return null;
    }
}
~~~

**Cơ chế của provider:**

1. **getAvailableLocales()** công bố display Locale qaa-QA.
2. **getDisplayLanguage("fr", qaa-QA)** trả tên riêng mà bài test kiểm soát.
3. Các tên khác trả **null** theo contract name provider khi không có bản dịch riêng, để runtime có thể tiếp tục lựa chọn/fallback theo lookup algorithm.
4. **getDisplayCountry/getDisplayVariant** trả null vì demo không cung cấp tên vùng/variant; cả hai override cần có để triển khai abstract class.
5. **stripExtensions()** giúp ví dụ nhận cùng locale gốc khi display Locale chứa Unicode extension, nhưng một provider production cần thiết kế đầy đủ chính sách extensions.
6. Provider không tự truy vấn ngược **Locale.getDisplayLanguage(...)** ở method của nó cho cùng input, tránh recursion trong service lookup.
7. Code không phụ thuộc phiên bản CLDR để tạo câu custom; nó chỉ phụ thuộc logic do ứng dụng định nghĩa và việc JDK thực sự chọn SPI.

**Cảnh báo:** Với API phục vụ **localized names**, provider được phép trả **null** khi nó không có tên cho một code cụ thể. Điều đó khác với một provider chuyên tạo NumberFormat, nơi method tạo formatter cho Locale được hỗ trợ phải trả formatter hợp lệ theo contract.

### 6.3. Service descriptor

File **resources/META-INF/services/java.util.spi.LocaleNameProvider** chứa đúng một dòng:

~~~text
demo.spi.DemoLocaleNameProvider
~~~

Tên file chính là tên abstract service class **java.util.spi.LocaleNameProvider**. File này phải được copy vào output runtime classes/JAR. Với ServiceLoader trên classpath, resource cần encoding **UTF-8**, đúng class name và constructor có thể dùng để tạo provider.

### 6.4. Client program hoàn chỉnh

**src/demo/app/LocaleDataDemo.java**

~~~java
package demo.app;

import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.ServiceLoader;
import java.util.spi.LocaleNameProvider;

public final class LocaleDataDemo {
    public static void main(String[] args) {
        Locale display = Locale.forLanguageTag("qaa-QA");
        Locale vietnamese = Locale.forLanguageTag("vi-VN");
        String name = Locale.FRENCH.getDisplayLanguage(display);

        boolean found = ServiceLoader.load(LocaleNameProvider.class)
                .stream().anyMatch(item -> item.type().getName()
                        .equals("demo.spi.DemoLocaleNameProvider"));

        System.out.println("descriptorVisible=" + found);
        System.out.println("adapterOrder="
                + System.getProperty("java.locale.providers", "<default>"));
        System.out.println("customDisplayName=" + name);
        System.out.println("displayTag=" + display.toLanguageTag());
        System.out.println("javaFeature=" + Runtime.version().feature());

        String sampleNumber = NumberFormat.getNumberInstance(vietnamese)
                .format(1234567.89);
        String sampleDate = DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(vietnamese)
                .format(LocalDate.of(2024, 9, 1));
        System.out.println("viNumber=" + sampleNumber);
        System.out.println("viDate=" + sampleDate);
    }
}
~~~

**Tại sao dùng hai nguồn output?**

- **customDisplayName** thể hiện **SPI-controlled behavior** khi adapter order chọn SPI và display Locale đúng.
- **viNumber / viDate** thể hiện localized output từ runtime (theo adapter/service của lời gọi); mẫu này dùng **locale vi-VN**, mà demo LocaleNameProvider không hề đăng ký để thay đổi.
- **displayTag** và **javaFeature** là metadata phục vụ diagnostics, không trực tiếp là localized content.
- **descriptorVisible** kiểm tra service registration, còn **customDisplayName** mới kiểm tra xem SPI selection có hiệu lực với tên ngôn ngữ.
- **LocaleDataDemo** được viết để output dễ diff; việc chuẩn bị baseline phải luôn ghi lại JDK vendor/version, adapter order và locale.

### 6.5. Build/run trên Bash/Linux/macOS

Đứng trong thư mục **locale-spi-vs-data**:

~~~bash
mkdir -p build/META-INF/services

javac -encoding UTF-8 --release 17 -d build \
    src/demo/spi/DemoLocaleNameProvider.java \
    src/demo/app/LocaleDataDemo.java

cp resources/META-INF/services/java.util.spi.LocaleNameProvider \
   build/META-INF/services/

java -Djava.locale.providers=SPI,CLDR \
    -cp build demo.app.LocaleDataDemo

java -Djava.locale.providers=CLDR \
    -cp build demo.app.LocaleDataDemo
~~~

Chạy **hai tiến trình java độc lập**, không cố đổi system property sau khi locale service đã khởi tạo.

### 6.6. Build/run trên PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/META-INF/services | Out-Null

javac -encoding UTF-8 --release 17 -d build src/demo/spi/DemoLocaleNameProvider.java src/demo/app/LocaleDataDemo.java

Copy-Item resources/META-INF/services/java.util.spi.LocaleNameProvider build/META-INF/services/

java "-Djava.locale.providers=SPI,CLDR" -cp build demo.app.LocaleDataDemo

java "-Djava.locale.providers=CLDR" -cp build demo.app.LocaleDataDemo
~~~

**Lưu ý:** Trên PowerShell, đặt đối số **-Djava.locale.providers=SPI,CLDR** trong dấu nháy để chuyển đúng cho launcher. File service descriptor phải được đóng gói **UTF-8 không BOM** theo cách an toàn trong build pipeline.

### 6.7. Stdout thực tế trên OpenJDK 24.0.2

Với **SPI,CLDR**:

~~~text
descriptorVisible=true
adapterOrder=SPI,CLDR
customDisplayName=French from custom SPI
displayTag=qaa-QA
javaFeature=24
viNumber=1.234.567,89
viDate=1 tháng 9, 2024
~~~

Với **CLDR-only**:

~~~text
descriptorVisible=true
adapterOrder=CLDR
customDisplayName=French
displayTag=qaa-QA
javaFeature=24
viNumber=1.234.567,89
viDate=1 tháng 9, 2024
~~~

**Hai output này là kết quả kiểm thử thực tế trên OpenJDK 24.0.2, không phải golden results áp dụng tự động cho tất cả JDK 17–26 hoặc mọi vendor.** Hai file Java được compile bằng **--release 17** và chạy thành công; phép kiểm thử riêng xác nhận:

- **descriptorVisible=true** ở cả hai tiến trình.
- **customDisplayName=French from custom SPI** khi SPI được ưu tiên.
- Khi CLDR-only, output **không phải** câu custom; trên JDK 24 bản thử nghiệm là **French**.
- Cặp number/date vi-VN trong JDK 24 là kết quả quan sát, không cứng hóa thành policy vĩnh viễn.

### 6.8. Diễn giải đúng kết quả

**Điều 1:** ServiceLoader thấy provider ở cả hai lần chạy. Một **service descriptor** nói code có mặt; nó không buộc JDK dùng code đó trong mọi lookup.

**Điều 2:** Dòng adapterOrder khác nhau vì hai JVM được launch với system property khác nhau. Với SPI-first, lookup tên language dùng implementation của ứng dụng. Với CLDR-only, JDK sử dụng dữ liệu mặc định thay vì câu mà code custom định nghĩa.

**Điều 3:** viNumber và viDate giống nhau giữa hai mode trên cùng JDK 24 trong phép thử này bởi provider chỉ triển khai **LocaleNameProvider** cho display Locale qaa-QA, không định nghĩa number/date formatting cho vi-VN. Không suy rộng rằng mọi adapter mode luôn cho cùng number/date output.

**Điều 4:** Nếu nâng JDK nhưng vẫn dùng provider code không đổi, **câu custom** có thể giữ ổn định khi provider được chọn; nhưng fallback CLDR cho tên khác, localized number/date hoặc chính compatibility/runtime selection vẫn cần kiểm thử.

## 7. Khi nào dữ liệu CLDR khác mà API không đổi?

Giả sử có hai runtime:

~~~text
JDK A + CLDR version A
        │
        ├── Locale.forLanguageTag("vi-VN")
        └── DateTimeFormatter.ofLocalizedDate(LONG).withLocale(vi-VN)
                │
                ▼
          Localized date string A

JDK B + CLDR version B
        │
        ├── Locale.forLanguageTag("vi-VN")
        └── DateTimeFormatter.ofLocalizedDate(LONG).withLocale(vi-VN)
                │
                ▼
          Localized date string B
~~~

Các phương thức vẫn được gọi với cùng tham số. Nếu **string A khác B**, cần xem release notes, CLDR version, dữ liệu JDK vendor, adapter order và formatter options. Không vội kết luận JDK đã thay đổi method signature hoặc Locale parser bị lỗi.

### 7.1. Ví dụ thay đổi có thể quan sát

Một locale release mới có thể:

- Đổi dấu nhóm số theo dữ liệu cập nhật.
- Thêm hoặc sửa cách gọi tên một vùng địa lý.
- Điều chỉnh dạng tên tháng trong ngữ cảnh viết ngày.
- Đổi localized currency spacing hoặc ký hiệu.
- Thêm dạng rút gọn cho compact number formatting.
- Thay cách biểu diễn timezone names.
- Điều chỉnh các pattern khác theo khảo sát/quy chuẩn locale data.

Các ví dụ trên thể hiện **loại thay đổi có thể xảy ra**, không phải tuyên bố tất cả những thay đổi đó đã xảy ra với vi-VN ở mỗi JDK.

### 7.2. CLDR không phải mọi loại dữ liệu quốc tế hóa

Một bản update của **tzdb** có thể thay lịch sử/chuyển đổi daylight-saving time mà không cần API hoặc CLDR name change. Một bản **Currency** update có thể phản ánh chính sách tiền tệ. **CLDR** có dữ liệu tên localized nhưng không phải là nguồn duy nhất của tất cả metadata thời gian/tiền tệ.

Trong báo cáo QA khi nâng JDK, hãy liệt kê **version và nguồn dữ liệu** thay vì viết chung “locale changed”.

## 8. Lập kế hoạch kiểm thử nhiều JDK

Để đánh giá một bản nâng cấp, không chỉ chạy unit tests compile API. Hãy thử **cùng JAR**, **cùng locale**, **cùng input**, **cùng adapter configuration**, nhưng chạy trên các phiên bản JDK được hỗ trợ.

### 8.1. Trước hết xác định phần nào do ứng dụng kiểm soát

| Hành vi | Nguồn trách nhiệm | Loại assertion phù hợp |
| --- | --- | --- |
| SPI provider class được khám phá | Service descriptor/module metadata | **Phải đúng** nếu artifact hợp lệ |
| SPI-first chọn câu custom cho qaa-QA | App provider + JVM adapter order | **Exact equality** với câu custom |
| Locale tag vi-VN | Dữ liệu Locale identifier | **Exact equality** cho tag đã chọn |
| Date/number output của CLDR | Dữ liệu locale runtime/version | **Versioned snapshot** hoặc semantic property checks |
| Chữ ký số/hash từ bytes | Protocol/data contract | **Byte-for-byte**, không tùy ý normalize |
| Monetary amount trước format | Business data | **Numeric exactness**, không dùng display string làm source of truth |
| Message text trong application ResourceBundle | File bản dịch do app quản lý | Exact theo version app, nhưng vẫn kiểm tra formatting/locale |
| Time-zone transition | tzdb/runtime | Test theo timezone version và business expectations |

Không biến tất cả assertions thành exact snapshot, cũng không xóa hết assertions khi có mismatch. Phân loại sở hữu dữ liệu trước rồi mới chọn cách test.

### 8.2. Những thông tin cần lưu trong test report

Tối thiểu:

- JDK vendor và full version, ví dụ từ **java -version**.
- Runtime feature version từ **Runtime.version().feature()**.
- OS và relevant locale/environment settings nếu sản phẩm có HOST/default-locale behavior.
- **java.locale.providers** đã đặt khi startup, kể cả trường hợp không đặt.
- Requested Locale đầy đủ, bao gồm Unicode extensions.
- Formatter API, style, currency, zone, rounding/parse settings, input giá trị và phạm vi test.
- CLDR version theo JDK documentation tương ứng; đừng đoán phiên bản từ kết quả format.
- Versions của application SPI/provider, resource bundles và dependencies.
- Phân biệt output do SPI quản lý với output từ CLDR, java.time, tzdb hoặc data khác.

Dùng đầy đủ metadata giúp phân tích đúng root cause khi test fail sau JDK upgrade.

### 8.3. Một ma trận nâng cấp gợi ý

| Test case | JDK cũ | JDK mới | Kỳ vọng |
| --- | --- | --- | --- |
| Classpath SPI descriptor | Load được | Load được | Provider discoverable |
| SPI-first custom LocaleNameProvider | Câu custom | Câu custom | Exact string nếu code/contract không đổi |
| CLDR-only Locale display language | Quan sát | Quan sát | Có thể thay đổi, kiểm tra theo policy |
| vi-VN decimal/grouping | Quan sát | Quan sát | Kiểm tra separators/semantic behavior |
| vi-VN localized date | Quan sát | Quan sát | Xem style, lịch, pattern, độ đọc |
| Currency display | Quan sát | Quan sát | Đúng mã Currency, style của locale |
| Parse một chuỗi do phiên bản cũ tạo ra | Thành công | Cần kiểm chứng | Có thể fail nếu grammar/pattern thay đổi |
| ResourceBundle app-managed text | Theo artifact | Theo artifact | Exact nếu resource không đổi |
| Named module SPI discovery | Load được | Load được | provides/service resolution hợp lệ |

Trong CI, có thể giữ **một nhóm assertions ổn định theo contract** và **một nhóm snapshot được gắn nhãn phiên bản JDK**. Khi data changes hợp lệ, review diff và cập nhật baseline có kiểm soát; không tự chấp nhận mọi thay đổi chỉ vì JDK mới.

## 9. Kiểm thử compile một lần, chạy nhiều runtime

Ví dụ được compile bằng:

~~~bash
javac --release 17 -d build \
    src/demo/spi/DemoLocaleNameProvider.java \
    src/demo/app/LocaleDataDemo.java
~~~

Điều này giới hạn Java language/API ở **Java 17 compatibility** khi compiler hỗ trợ --release. Nếu binary được tạo ở mức Java 17, nó có thể chạy trên các JDK mới tương thích nhưng **không đóng băng dữ liệu CLDR của JDK dùng để chạy**.

Để đánh giá nâng cấp, dùng runtime đã cài thực tế và giữ nguyên output classes/JAR của bài test:

~~~bash
# Mảnh script minh họa, chỉ chạy khi các JDK đã được cài đúng đường dẫn.
"$JDK_OLD/bin/java" -Djava.locale.providers=SPI,CLDR \
    -cp build demo.app.LocaleDataDemo > old-spi.txt

"$JDK_NEW/bin/java" -Djava.locale.providers=SPI,CLDR \
    -cp build demo.app.LocaleDataDemo > new-spi.txt

diff -u old-spi.txt new-spi.txt
~~~

**JDK_OLD/JDK_NEW** là biến môi trường được người chạy cấu hình. Hai lệnh không phải kiểm thử đã thực hiện ở bài này: máy kiểm chứng thực tế chỉ được dùng để compile/run trên OpenJDK 24.0.2.

Khi so sánh, **javaFeature** hiển nhiên khác nếu hai JDK thuộc major releases khác nhau; hãy tách dòng metadata khỏi phép so sánh behavior nếu muốn assertion chính xác. Sau đó chạy thêm hai lệnh **CLDR-only** để quan sát phần không có SPI override.

### 9.1. Đừng yêu cầu cùng exact stdout cho mọi JDK

Nếu golden test so sánh toàn bộ output và chứa **javaFeature** hoặc localized date, nó có thể fail vì **kỳ vọng sai** chứ không phải product regression. Đổi cách kiểm tra:

- Câu **French from custom SPI** là output do app định nghĩa: giữ exact assertion khi provider được chọn.
- **displayTag=qaa-QA** được kiểm tra như định danh.
- **javaFeature** phải khớp runtime test đang chạy, không một hằng số cho mọi môi trường.
- **viNumber/viDate** kiểm tra theo locale data/version hoặc semantic requirements, không mặc định giữ từng dấu chấm/khoảng trắng.
- Nếu phải đọc dữ liệu đã được định dạng bởi bản JDK cũ, cần **backward-compatibility parse tests**; đổi locale data có thể làm parser không chấp nhận lại chuỗi cũ.

### 9.2. Nâng cấp JDK có thể đổi nhiều hơn dữ liệu CLDR

Một chương trình cũng có thể thay đổi vì:

- Default locale/time zone của môi trường.
- JVM vendor hoặc build options khác.
- Ứng dụng thay đổi **Locale.Category.FORMAT** hoặc **Locale.Category.DISPLAY**.
- CLDR provider selection khác do cấu hình **java.locale.providers**.
- Dữ liệu TZDB/currency được update.
- Provider SPI mới/khác phiên bản hoặc classloader resolution khác.
- Application ResourceBundle thay đổi, fallback của parent resource đổi.
- Một thư viện định dạng độc lập được nâng cấp.

Bởi vậy, nếu chỉ nhìn “JDK changed”, nên điều tra thêm trước khi kết luận **CLDR thay đổi**.

## 10. Cách chẩn đoán khi output đổi ngoài mong đợi

Một trình tự thực hành:

1. **Xác minh input/Locale:** dùng **Locale.toLanguageTag()**, kiểm tra extensions và **Locale.getDefault(Category.FORMAT/DISPLAY)** nếu API dựa vào default.
2. **Xác minh runtime:** lấy **java -version**, full vendor/build, OS và launcher options.
3. **Kiểm tra adapter order:** JVM có **-Djava.locale.providers=SPI,CLDR**, **CLDR** hay dùng mặc định?
4. **Kiểm tra service registration:** ServiceLoader thấy SPI implementation không? Artifact đã copy đúng **META-INF/services** hoặc named module provides chưa?
5. **Xác nhận provider selection thật:** dùng một output đặc trưng do app kiểm soát, không chỉ dựa vào ServiceLoader.
6. **So sánh định dạng:** method nào được gọi, style/format options, Currency, rounding, time zone và format Locale?
7. **Tra phiên bản CLDR theo JDK docs:** so sánh delta/patch notes nếu có thay đổi localized text.
8. **Kiểm tra dữ liệu ngoài CLDR:** ResourceBundle app, tzdb, currency metadata, environment/host overrides.
9. **Chạy test trên runtime cũ và mới với cùng artifact:** tách khác biệt do code và runtime data.
10. **Đánh giá tác động nghiệp vụ:** UI thay đổi nhưng hợp lệ hay parser/exports/unique key bị phá?
11. **Quyết định chính sách:** chấp nhận và cập nhật baseline, hoặc ghim format/data theo app.
12. **Lưu regression tests:** ít nhất các locale và output quan trọng với người dùng của sản phẩm.

### 10.1. Triệu chứng và nguyên nhân

| Triệu chứng | Cơ chế có thể liên quan | Việc nên kiểm tra |
| --- | --- | --- |
| ServiceLoader tìm được provider nhưng output không theo custom | Adapter order không có SPI | java.locale.providers và requested Locale |
| Output custom biến mất sau deploy | Descriptor/JAR/module classpath khác | Service resource, package, module path |
| Cùng Locale, tên vùng khác sau JDK upgrade | CLDR names update | JDK/CLDR versions, locale, release notes |
| Dấu phân cách số hoặc currency spacing thay đổi | CLDR / NumberFormat implementation | Formatter data và numeric semantics |
| Date parse chuỗi cũ bị lỗi | Dữ liệu/pattern locale cập nhật | Test round-trip across versions, explicit input grammar |
| Câu trong ResourceBundle đổi | App localization files, fallback hoặc packaging | Resource content/version; không mặc định CLDR |
| Tên múi giờ khác nhưng giờ offset vẫn đúng | Localized names vs actual tzdb rules | ZoneId/tzdb và display locale |
| Offset/time instant thật khác | Timezone rules/tzdb hoặc business logic | tzdb data/version, ZoneId, timestamps |
| Chạy trên Linux và Windows khác nhau | HOST adapter, defaults, fonts/encoding | JVM settings, host provider availability |
| Locale extension không được tôn trọng | Provider implementation thiếu extension support | isSupportedLocale và các method của provider |
| Test snapshot fail chỉ ở JDK mới | Golden exact bị buộc vào runtime data | Versioned snapshots + contract assertions |
| Format giống nhau qua JDK upgrade | Data của locale đó chưa thay đổi hoặc cùng semantics | Không thể kết luận CLDR version giống nhau |

## 11. Nếu sản phẩm yêu cầu kết quả ổn định thì làm gì?

Đầu tiên cần xác định **“ổn định”** ở mức nào:

- Ổn định về **giá trị tính toán** (numeric amount, timestamp, currency code).
- Ổn định về **cách hiển thị cho người dùng** theo quy tắc quốc tế hóa hiện hành.
- Ổn định **byte-for-byte** để dùng trong export, hash, chữ ký, báo cáo được ký hoặc giao thức kết nối.

Ba mục tiêu này không giống nhau và không có một tùy chọn Java chung giải quyết hết.

### 11.1. Tách canonical data khỏi formatted display

Ví dụ số tiền cần lưu dạng **BigDecimal + Currency code**, không chỉ chuỗi như **1.234.567,89 ₫**. Thời điểm cần lưu bằng **Instant** hoặc kiểu thời gian đúng theo domain, kèm ZoneId nếu cần hiển thị theo địa phương; tránh lưu duy nhất chuỗi ngày dài được format.

Nếu lưu canonical data, bạn có thể thay đổi cách format cho người dùng khi nâng cấp CLDR mà không làm mất giá trị gốc. Nếu chỉ lưu localized string, parser có thể phụ thuộc vào locale data cũ để đọc trở lại.

### 11.2. Chọn explicit pattern/symbols khi format là protocol

Nếu hệ thống giao tiếp yêu cầu đúng định dạng **yyyy-MM-dd** hoặc decimal separator là dấu chấm ASCII, nên dùng **định dạng có contract rõ** thay vì localized style mặc định của người dùng.

Ví dụ:

~~~java
// Mảnh minh họa, cần imports tương ứng.
String machineDate = LocalDate.of(2024, 9, 1)
        .format(DateTimeFormatter.ISO_LOCAL_DATE); // 2024-09-01
~~~

**ISO_LOCAL_DATE** dành cho dữ liệu máy cần ngày chuẩn, khác với localized date dành cho UI. Với số, dùng formatter/serializer có định nghĩa rõ theo protocol (chẳng hạn BigDecimal.toPlainString khi thích hợp) thay vì một NumberFormat phụ thuộc locale.

Một explicit pattern có thể giảm phụ thuộc vào **pattern** từ CLDR, nhưng **không bảo đảm mọi localized symbol/text đã bất biến** nếu pattern vẫn dùng tên tháng, chữ số hoặc ký hiệu từ locale data; muốn byte-level guarantee cần kiểm soát cả symbols/encoding.

### 11.3. Quản lý dữ liệu dịch và format tại application layer

Với các câu chữ do sản phẩm sở hữu, dùng ResourceBundle hoặc hệ thống localization riêng để version hóa strings. Với format độc quyền, có thể giữ explicit symbols/patterns trong resource theo version ứng dụng.

Điều này cho phép CI so sánh chính xác các artifacts được app quản lý. Tuy nhiên việc giữ data riêng phát sinh trách nhiệm cập nhật ngôn ngữ, kiểm thử Unicode/locale và đồng bộ chính sách.

### 11.4. Khi nào nên dùng Locale SPI?

Dùng SPI nếu muốn **Locale-sensitive factories tiêu chuẩn của JDK** có thể chọn implementation riêng cho một tập Locale. Nếu chỉ cần một formatter ở một call site, tạo formatter explicit thường đơn giản hơn và ít tác động toàn application.

SPI không phải giải pháp “khóa toàn bộ dữ liệu JDK”: nó chỉ override dịch vụ/Locale mà provider thực sự hỗ trợ và được adapter lookup chọn. Những dịch vụ khác hoặc Locale không hỗ trợ có thể tiếp tục dùng CLDR.

### 11.5. Cố định runtime: hữu ích nhưng không giải quyết mãi mãi

Đóng gói một phiên bản JDK cụ thể cùng ứng dụng giúp giảm biến thiên khi vận hành và có thể giữ cùng CLDR data trong deployment hiện tại. Nhưng khi nâng cấp bảo mật/JDK, dữ liệu có thể đổi. **Không nên trì hoãn cập nhật bảo mật chỉ để giữ một snapshot localization**; nếu cần byte-level ổn định, sản phẩm phải kiểm soát output format ngay tại boundary.

## 12. Những cạm bẫy khi trộn SPI với dữ liệu theo phiên bản

### 12.1. Provider riêng không có nghĩa “toàn bộ Locale” đã được override

Nếu bạn triển khai **LocaleNameProvider** cho qaa-QA, không có lý do mặc định để **NumberFormat.getNumberInstance(vi-VN)** hoặc **DateTimeFormatter** cũng phải đổi. Mỗi service có lookup và phạm vi riêng.

Tương tự, một **NumberFormatProvider** có thể override number/currency/percent factory cho một Locale nhưng không mặc nhiên thay mọi DateFormat/Collator.

### 12.2. Data trong provider cũng có thể thay đổi

SPI là code do bạn kiểm soát, nhưng nếu provider của bạn đọc JSON, database, config, ICU/CLDR library hoặc resources được update, output của chính provider vẫn có thể thay đổi theo phiên bản **provider data**. Muốn reproducible, phải version hóa cả code và data.

### 12.3. Provider discovery không giống provider selection

**ServiceLoader.load(...)** cho thấy có provider implementation. **java.locale.providers** quyết định adapter ưu tiên ở thời điểm runtime chọn locale service; provider còn phải công bố Locale phù hợp và có implementation đúng contract.

Test chỉ assert **providerFound == true** là chưa đủ. Test mẫu còn assert **customDisplayName** đúng khi SPI-first và không phải câu đó trong CLDR-only.

### 12.4. Không coi HOST là nguồn luôn có

HOST data provider chỉ tồn tại ở những implementation/nền tảng hỗ trợ, phản ánh một phần thiết lập OS. Đưa **HOST** vào adapter order không bảo đảm trên mọi OS sẽ có cùng kết quả. Nếu muốn ứng dụng server deterministic, cần xem có phù hợp dùng HOST hay không.

### 12.5. Không “mặc định hóa” Locale do môi trường

Nhiều API overload không nhận Locale dùng default locale của JVM; điều này có thể thay đổi theo user, region và setting. Dùng **Locale** tường minh trong nghiệp vụ quan trọng để giảm một nguồn biến thiên.

### 12.6. Không dùng localized strings làm khóa giao thức

Chuỗi như **“1 tháng 9, 2024”**, **“1.234.567,89”** hoặc tên vùng được dịch thích hợp cho UI nhưng thường không phải **canonical protocol representation**. Dùng ISO formats, numeric types, currency codes và identifier contracts khi cần parse/serialize lâu dài.

### 12.7. Đừng dùng APIs bị loại bỏ để giữ kết quả cũ

JDK mới không chứa legacy locale data provider JRE/COMPAT. Hãy chuyển sang CLDR, dùng explicit representation hoặc SPI hiện hành có trách nhiệm rõ. Những giải pháp dựa trên JDK internals hoặc flags legacy sẽ làm tăng chi phí bảo trì và tạo false sense of compatibility.

## 13. Thực hành kiểm thử hành vi nâng cấp

### Bài tập 1 — kiểm chứng nguồn SPI

Chạy chương trình ở phần 6 với:

~~~bash
java -Djava.locale.providers=SPI,CLDR -cp build demo.app.LocaleDataDemo
java -Djava.locale.providers=CLDR -cp build demo.app.LocaleDataDemo
~~~

Giải thích vì sao **descriptorVisible=true** ở cả hai, còn **customDisplayName** chỉ có câu custom khi SPI được ưu tiên.

### Bài tập 2 — thay đổi dữ liệu provider của ứng dụng

Sửa câu **French from custom SPI** thành một câu demo khác trong provider, compile lại rồi chạy SPI-first. Kết quả thay đổi mà JDK/CLDR không đổi: đây là **application provider change**, không phải CLDR data evolution.

### Bài tập 3 — thử Locale khác

Đổi display Locale từ **qaa-QA** sang Locale khác mà provider không công bố, kiểm tra runtime fallback. Viết lại **getAvailableLocales/isSupportedLocale** cho yêu cầu mở rộng thay vì ép mọi Locale được hỗ trợ.

### Bài tập 4 — quan sát dữ liệu CLDR khác phiên bản

Nếu có hai JDK đã cài hợp lệ, chạy cùng binary Java 17 với hai runtime. So sánh **viNumber**, **viDate** và localized names. Nếu khác, kiểm tra version CLDR và những setting liên quan. Nếu giống, không kết luận hai JDK có cùng CLDR.

### Bài tập 5 — parser backward compatibility

Lấy một chuỗi ngày do formatter localized của JDK cũ tạo, thử parse ở JDK mới theo locale/style tương ứng. Viết test xử lý khi separator, pattern hoặc name đổi. Nếu đây là dữ liệu máy cần lưu lâu dài, thiết kế lại thành ISO format thay vì localized text.

### Bài tập 6 — định danh có Unicode extensions

Tạo Locale với Unicode extension như **vi-VN-u-nu-latn**. Kiểm tra provider supports/extensions policy; so sánh với vi-VN thuần. Phân biệt việc lookup được support với việc method thực sự tôn trọng extension.

### Bài tập 7 — đóng gói JAR hoặc named module

Đóng gói service descriptor vào JAR rồi kiểm tra đường dẫn. Với named module, dùng **provides java.util.spi.LocaleNameProvider with ...** trong module-info.java. Kiểm chứng bằng service discovery và output.

### Bài tập 8 — snapshot test có trách nhiệm

Thiết kế hai nhóm tests:

- **Exact:** câu custom của SPI, protocol date ISO, numeric canonical values.
- **Version-aware:** localized date/number/currency/name từ CLDR.

Ghi JDK version và adapter order cho từng test result. Khi phát hiện diff, phân loại thay đổi hợp lệ hay regression thực tế.

## 14. Checklist trước khi nâng JDK hoặc thêm Locale SPI

- [ ] Xác định từng localized output đến từ **CLDR**, **SPI**, **HOST**, application bundle hay nguồn khác.
- [ ] Không nhầm **Locale tag ổn định** với **CLDR data bất biến**.
- [ ] Đọc release notes và CLDR version của JDK đích.
- [ ] Thực hiện test trên những JDK versions mà sản phẩm hỗ trợ, dùng cùng artifact/input khi so sánh.
- [ ] Kiểm tra cả **formatting** lẫn **parsing dữ liệu cũ** khi có lưu localized strings.
- [ ] Nếu dùng SPI, kiểm tra descriptor/provides, classloader/module path, Locale coverage.
- [ ] Xác minh **java.locale.providers** ở startup, không tự thay property sau service initialization.
- [ ] Không coi ServiceLoader discovery là đủ bằng chứng selection.
- [ ] Kiểm thử custom behavior của SPI bằng những giá trị do app kiểm soát.
- [ ] Không hard-code CLDR display strings làm contract xuyên JDK nếu không có lý do nghiệp vụ.
- [ ] Tách UI localized text khỏi canonical persisted/protocol values.
- [ ] Nếu cần byte-for-byte output, kiểm soát patterns, symbols, encoding và versioned data.
- [ ] Không phụ thuộc vào JRE/COMPAT legacy data adapters đã bị loại bỏ trên JDK mới.
- [ ] Không nhầm timezone rules/tzdb với CLDR localized time-zone names.
- [ ] Đánh giá mức ảnh hưởng tới người dùng, export, business calculations và security boundaries.
- [ ] Bảo đảm test đầy đủ Locale có tiếng Việt **vi-VN**, dấu/spacing Unicode, currency và thời gian theo nhu cầu sản phẩm.

## Kết luận

**Locale SPI là cơ chế mở rộng có Java implementation, service discovery và adapter selection. CLDR là nguồn dữ liệu locale của runtime có thể được cập nhật giữa các JDK releases.** Chúng liên hệ qua những factory và API địa phương hóa nhưng **không phải một thứ**.

Khi thêm SPI, phải xác minh **provider đã được khám phá và đã được chọn**. Khi nâng JDK, phải kiểm tra **dữ liệu CLDR/version cùng định dạng thực tế**, không đánh đồng một thay đổi về ký hiệu/tên/pattern với việc Java API thay đổi. Nếu sản phẩm cần output ổn định, hãy quản lý canonical data và explicit format/data policy; còn khi sản phẩm muốn theo chuẩn quốc tế hóa mới, hãy chấp nhận các thay đổi được review và kiểm thử có trách nhiệm.

**Tài liệu chính thức còn được hỗ trợ (kiểm tra tại thời điểm viết):**

- [LocaleServiceProvider — Java SE 26, SPI/CLDR/HOST, thứ tự chọn và bảng CLDR versions](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleServiceProvider.html)
- [Locale — Java SE 26, mô hình Locale và dữ liệu thay đổi theo JDK release](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html)
- [LocaleNameProvider — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleNameProvider.html)
- [NumberFormat — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/NumberFormat.html)
- [ServiceLoader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html)
- [DateTimeFormatter — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Oracle JDK 26 Migration Guide — thay đổi locale data và removal JRE/COMPAT](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html)
- [JDK 26 Release Notes — nâng cấp CLDR 48 và khác biệt localized formats](https://www.oracle.com/java/technologies/javase/26all-relnotes.html)