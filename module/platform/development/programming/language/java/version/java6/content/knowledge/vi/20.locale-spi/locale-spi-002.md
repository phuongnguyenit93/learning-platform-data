# Locale SPI: NumberFormatProvider và định dạng số, tiền tệ, phần trăm

## Mục tiêu học tập

**java.text.spi.NumberFormatProvider** là một **Locale Service Provider Interface (Locale SPI)** chuẩn của Java. Nó cho phép một thư viện cung cấp cách tạo **NumberFormat** cho những Locale mà ứng dụng cần hỗ trợ, thay vì buộc mọi chương trình sử dụng duy nhất dữ liệu định dạng do JDK cung cấp. Provider này hỗ trợ các nhu cầu **định dạng số thông thường, số nguyên, tiền tệ và phần trăm**; người dùng API vẫn gọi các factory quen thuộc như **NumberFormat.getNumberInstance(locale)**.

Điểm thường gây nhầm lẫn là **viết một provider và đăng ký service chưa đủ để đảm bảo NumberFormat sẽ sử dụng nó**. JDK còn có cơ chế lựa chọn các nguồn dữ liệu bản địa hóa (**CLDR**, **SPI** và một số môi trường có **HOST**) theo thứ tự cấu hình. Với JDK hiện đại, cần hiểu rõ **java.locale.providers**, locale được provider công bố và cơ chế service discovery.

Sau bài học, bạn có thể:

1. Phân biệt **NumberFormat**, **DecimalFormat**, **DecimalFormatSymbols**, **NumberFormatProvider**, **LocaleServiceProvider**, **Currency** và service registration.
2. Triển khai đầy đủ **getAvailableLocales()**, **getNumberInstance(Locale)**, **getIntegerInstance(Locale)**, **getCurrencyInstance(Locale)** và **getPercentInstance(Locale)**.
3. Đăng ký provider trên **classpath** qua **META-INF/services/java.text.spi.NumberFormatProvider**, hoặc khai báo **provides ... with ...** trong một named module.
4. Bật SPI trong đường lựa chọn locale bằng **-Djava.locale.providers=SPI,CLDR** ngay khi khởi động JVM; kiểm thử sự khác biệt với **CLDR**.
5. Hiểu **phần trăm nhân 100 khi hiển thị**, format số nguyên có rounding/parse-integer policy, định dạng tiền tệ dùng **Currency** và các dấu phân tách **monetary**.
6. Nhận ra vì sao **ServiceLoader** tìm thấy provider **không tự chứng minh** NumberFormat.get*Instance đã chọn provider đó.
7. Kiểm thử hành vi với dữ liệu xác định, tránh phụ thuộc quá mức vào locale của host, phiên bản CLDR hoặc thứ tự service provider.
8. Thiết kế formatter **mới cho mỗi lời gọi**, giữ provider không có mutable state chung và phân biệt việc **định dạng để hiển thị** với **tính toán tiền tệ** thực sự.

**Phạm vi hiện hành:** Sử dụng Java 17+ và API còn được hỗ trợ; ví dụ được biên dịch bằng **OpenJDK 24.0.2** với **--release 17**. Không hướng dẫn các cơ chế locale provider bị loại bỏ hoặc các kỹ thuật đặc thù của JDK lỗi thời.

## 1. NumberFormatProvider giải quyết bài toán gì?

Java đã hỗ trợ sẵn nhiều Locale. Thông thường, ứng dụng chỉ cần:

~~~java
// Mảnh code minh họa, không phải file độc lập.
Locale viVN = Locale.forLanguageTag("vi-VN");
NumberFormat number = NumberFormat.getNumberInstance(viVN);
NumberFormat money = NumberFormat.getCurrencyInstance(viVN);
NumberFormat percent = NumberFormat.getPercentInstance(viVN);
~~~

Các factory trả về formatter theo quy tắc locale của runtime. Tuy nhiên, có những trường hợp bạn muốn **một quy tắc riêng** cho Locale nghiệp vụ hoặc bổ sung quy tắc mà JDK không cung cấp:

- Ứng dụng có một **synthetic/test Locale** để kiểm chứng đường định dạng.
- Một hệ thống chuyên ngành có quy tắc hiển thị đặc biệt và muốn API client vẫn gọi **NumberFormat.get*Instance(Locale)**.
- Một sản phẩm cần cung cấp **locale-sensitive service implementation** như thư viện được khám phá qua Java SPI.
- Một tổ chức muốn chuẩn hóa cách chọn formatter cho cùng một Locale trong nhiều phần mã chạy chung runtime, có khả năng quản lý provider và thứ tự lựa chọn.

**NumberFormatProvider không phải giải pháp mặc định cho mọi ứng dụng.** Nếu chỉ muốn một formatter ở một vị trí nhất định, cách đơn giản là tạo **NumberFormat.getNumberInstance(locale)** hoặc **DecimalFormat** và cấu hình nó cục bộ. Dùng SPI khi thực sự cần **cắm một nhà cung cấp dịch vụ vào factory cơ sở của JDK**.

### 1.1. Bốn lớp/khái niệm cần phân biệt

~~~text
Ứng dụng
   │
   │ NumberFormat.getNumberInstance(locale)
   ▼
JDK locale-sensitive service lookup
   │
   ├── CLDR (locale data của runtime)
   ├── SPI  (NumberFormatProvider bên ngoài)
   └── HOST (nếu runtime/OS hỗ trợ)
   │
   ▼
Provider cụ thể cho Locale được chọn
   │
   └── trả về NumberFormat mới
               │
               ├── NumberFormat (kiểu API)
               └── có thể là DecimalFormat (implementation)
                         │
                         └── DecimalFormatSymbols
                             dấu nhóm, dấu thập phân,
                             monetary symbols, chữ số...
~~~

- **NumberFormat**: abstract class cung cấp API format/parse số theo Locale và các factory static.
- **DecimalFormat**: một implementation có pattern và cấu hình rounding, grouping, parsing.
- **DecimalFormatSymbols**: chứa những ký hiệu được DecimalFormat dùng khi hiển thị/parse; dấu phân nhóm thông thường có thể khác dấu phân nhóm tiền tệ.
- **NumberFormatProvider**: abstract service provider có thể tạo NumberFormat theo Locale; không tự là NumberFormat.
- **LocaleServiceProvider**: lớp cha xác định cách công bố và kiểm tra Locale được hỗ trợ.
- **Currency**: mô tả đơn vị tiền tệ với mã ISO 4217, default fraction digits và metadata liên quan; không đồng nhất với tên quốc gia/locale hoặc một ký hiệu trang trí.

## 2. Các phương thức bắt buộc của NumberFormatProvider

**NumberFormatProvider** ở package **java.text.spi** kế thừa **java.util.spi.LocaleServiceProvider**.

| Phương thức | Nguồn | Nhiệm vụ |
| --- | --- | --- |
| **getAvailableLocales()** | LocaleServiceProvider, abstract | Công bố tập Locale mà provider hỗ trợ |
| **getNumberInstance(Locale)** | NumberFormatProvider, abstract | Tạo formatter số thông thường |
| **getIntegerInstance(Locale)** | NumberFormatProvider, abstract | Tạo formatter số nguyên |
| **getCurrencyInstance(Locale)** | NumberFormatProvider, abstract | Tạo formatter tiền tệ |
| **getPercentInstance(Locale)** | NumberFormatProvider, abstract | Tạo formatter phần trăm |
| **isSupportedLocale(Locale)** | LocaleServiceProvider, implementation mặc định | Kiểm tra Locale có được provider hỗ trợ |
| **getCompactNumberInstance(Locale, Style)** | NumberFormatProvider, implementation mặc định | Formatter số rút gọn nếu provider hỗ trợ tùy chọn này |

**Điểm cập nhật hiện hành:** NumberFormatProvider còn có **getCompactNumberInstance(Locale, NumberFormat.Style)** (từ Java 12). Đây **không phải** một trong bốn phương thức abstract bắt buộc của ví dụ; implementation mặc định **ném UnsupportedOperationException**. Nếu provider của sản phẩm phải hỗ trợ số rút gọn như 1K/1M, hãy nghiên cứu và triển khai contract đó riêng; không tự cho rằng các pattern bốn định dạng trên sẽ giải quyết luôn compact number.

### 2.1. getAvailableLocales phải nói đúng khả năng hỗ trợ

~~~java
// Mảnh minh họa trong NumberFormatProvider.
private static final Locale SUPPORTED =
        Locale.forLanguageTag("qaa-QA");

@Override
public Locale[] getAvailableLocales() {
    return new Locale[] { SUPPORTED };
}
~~~

Ví dụ sử dụng Locale demo **qaa-QA**, một lựa chọn chỉ dành cho **thử nghiệm SPI**, không tuyên bố đây là quy tắc ngôn ngữ hoặc tiền tệ thực của người dùng tại Qatar. Một provider production phải công bố những Locale mà **cả bốn formatter** thực sự đáp ứng được theo contract.

**getAvailableLocales()** không phải danh sách tất cả Locale trên thế giới. Nó chỉ là danh sách provider này cung cấp. **NumberFormat.getAvailableLocales()** ở cấp JDK trả tổng hợp những Locale mà runtime và các providers đang được dùng hỗ trợ, nên không được lẫn hai giá trị đó.

### 2.2. isSupportedLocale và Unicode locale extensions

Implementation mặc định của **LocaleServiceProvider.isSupportedLocale(locale)** thường so với các available locales **sau khi bỏ Unicode extensions**. Vì vậy Locale có extension như numbering system có thể được coi là supported dù provider chỉ công bố tag gốc.

Một provider thực tế nên quyết định rõ cách xử lý extensions như **nu** (numbering system), **rg** (region override), **cf** (currency formatting style) hoặc **cu** (currency type), nếu chúng nằm trong contract mà runtime/provider của bạn hỗ trợ.

Ví dụ đơn giản bên dưới chỉ xử lý **đúng qaa-QA không có extension/variant** và chủ động từ chối Locale khác. Nó là code runnable cho bài học, **không phải template có thể triển khai cho mọi requested Locale**. Trong một provider production hỗ trợ locale fallback/extensions, phần validation phải tương thích với cơ chế **isSupportedLocale** và quy tắc runtime có thể gọi factory bằng **requested Locale gốc** dù lookup đã khớp ở một candidate ít cụ thể hơn.

### 2.3. Hành vi của method khi Locale không được hỗ trợ

Theo API, các method factory phải:

- Không chấp nhận **null Locale**; báo **NullPointerException**.
- Không âm thầm tạo formatter cho Locale không thuộc vùng hỗ trợ; báo **IllegalArgumentException** khi gọi provider trực tiếp với Locale không hợp lệ theo contract.
- Trả về **NumberFormat mới** cho lời gọi hợp lệ, không trả về null.
- Với **getIntegerInstance**: formatter phải phù hợp yêu cầu số nguyên, bao gồm rounding **HALF_EVEN** cho format số không nguyên và **parse-integer-only** khi parse theo contract.
- Không dùng một instance mutable chung để phục vụ mọi thread; NumberFormat và DecimalFormat có cấu hình có thể thay đổi và không nên coi là thread-safe.

Nếu ứng dụng dùng **NumberFormat.get*Instance(locale)**, JDK sẽ quản lý chọn provider và fallback. Nếu bạn gọi thẳng **new DemoNumberFormatProvider().getNumberInstance(locale)**, bạn đang sử dụng implementation trực tiếp và phải tuân thủ điều kiện Locale của provider đó, **không tự nhận fallback do JDK**.

## 3. Ba nhóm định dạng và một dạng số nguyên

### 3.1. Số thông thường

**NumberFormat.getNumberInstance(locale)** phục vụ những con số có nhóm hàng nghìn và chữ số thập phân theo locale.

Ví dụ một formatter được cấu hình cho bài test:

~~~text
Input Number          : 1234567.89
Grouping separator    : _
Decimal separator     : ~
Output                : 1_234_567~89
~~~

Các dấu **_** và **~** chỉ là **ký hiệu demo dễ nhìn**, không phải định dạng chung cho bất kỳ ngôn ngữ thực tế nào. Trong sản phẩm quốc tế hóa, dùng dấu/thứ tự/làm tròn phù hợp với Locale đã chọn.

### 3.2. Số nguyên

**getIntegerInstance(locale)** tạo formatter để **format** ra dạng số nguyên, thường gồm rounding về số nguyên, và được đặt **parseIntegerOnly=true**.

~~~text
Input number         : 1234567.6
Rounding mode        : HALF_EVEN
Output               : 1_234_568
parseIntegerOnly     : true
~~~

Điểm cần hiểu:

- **Formatting** một số thập phân thành chuỗi nguyên có thể làm tròn; không tương đương ép kiểu **(int)** hay cắt phần thập phân.
- **Parsing** theo integer-only policy là một contract khác với làm tròn lúc format. Một parser có thể dừng ở phần thập phân khi đọc chuỗi.
- **HALF_EVEN** chỉ khác các rounding mode khác ở trường hợp đúng giữa hai giá trị (tie), ví dụ các số có phần thập phân đúng 0.5; trong bài test số 1234567.6 không phải tie.
- Khi business logic cần giá trị nguyên chính xác, không lấy chuỗi format làm nguồn sự thật; validate input và kiểu số trước.

### 3.3. Tiền tệ

**getCurrencyInstance(locale)** tạo formatter của một **monetary amount**. Bản thân **Currency** và format hiển thị cần được phân biệt:

- **Currency.getCurrencyCode()** trả mã tiền như **USD**.
- **Currency symbol** có thể thay đổi theo vùng hoặc chính sách hiển thị.
- Số chữ số thập phân thường phụ thuộc **đơn vị tiền** (ví dụ một số đồng tiền sử dụng 0, 2 hoặc các mức khác).
- **Monetary decimal separator** và **monetary grouping separator** có thể khác những dấu dùng cho số thường.
- Pattern **¤** (currency sign placeholder) cho DecimalFormat dùng currency information/symbols, không có nghĩa ứng dụng được quyền tạo ra đơn vị tiền tệ mới chỉ bằng một ký tự.

Trong demo, để output dễ nhận biết đã đi qua provider, formatter dùng **Currency USD** nhưng **gắn ký hiệu hiển thị Q$** giả lập. Output:

~~~text
Q$1_234~50
~~~

**Q$ chỉ là nhãn hiển thị của bài test, không phải mã ISO 4217 hoặc đơn vị tiền tệ thực.** Đừng áp dụng trực tiếp quy tắc này cho báo cáo tài chính/giao dịch. Một hệ thống tiền tệ thực phải gắn **Currency** với domain data, lựa chọn đúng currency code và quy tắc hiển thị theo người dùng/hợp đồng; không suy tiền tệ giao dịch chỉ từ Locale.

### 3.4. Phần trăm

**getPercentInstance(locale)** hiển thị một tỷ lệ dạng số thành phần trăm. Pattern percent của DecimalFormat **nhân giá trị lên 100 khi format** và có dấu phần trăm trong output.

~~~text
Input ratio : 0.125
Output      : 12~5%
Ý nghĩa     : 12.5 phần trăm
~~~

**Đừng nhân 100 ở tầng nghiệp vụ rồi truyền vào Percent NumberFormat** nếu giá trị đầu vào đã là ratio: điều đó tạo kết quả gấp 100 lần mong muốn. Ví dụ một tỷ lệ 15% nên được lưu ở dạng **0.15** trong phép tính ratio thông thường, sau đó formatter percent hiển thị theo chính sách locale.

Khi parse phần trăm thành số, formatter percent có semantics chuyển đổi ngược về tỷ lệ; cần kiểm tra hợp đồng parse và độ chính xác với dữ liệu của hệ thống, không giả định mọi input từ người dùng đều parse được chỉ vì nó trông giống 12.5%.

## 4. Vì sao SPI chưa chắc được chọn dù đã đăng ký?

**LocaleServiceProvider** cho phép runtime dùng những nguồn dữ liệu locale khác nhau.

| Tên adapter | Ý nghĩa |
| --- | --- |
| **CLDR** | Dữ liệu chuẩn quốc tế hóa từ Unicode Common Locale Data Repository, là nguồn mặc định của JDK Reference Implementation hiện đại |
| **SPI** | Các triển khai **LocaleServiceProvider** do ứng dụng/thư viện đưa vào |
| **HOST** | Dữ liệu định dạng theo thiết lập host OS nếu JDK/runtime hỗ trợ; không có trên mọi nền tảng |

Để yêu cầu lookup **ưu tiên SPI** trước CLDR, truyền JVM option lúc khởi động:

~~~bash
java -Djava.locale.providers=SPI,CLDR \
    -cp build/classes demo.app.NumberProviderDemo
~~~

**java.locale.providers** là system property điều khiển **thứ tự adapter lookup**. Với **SPI,CLDR**, nếu SPI có dịch vụ phù hợp, nó được thử trước; nếu không, runtime có thể tiếp tục tìm theo CLDR.

**Không nên gọi System.setProperty("java.locale.providers", ...) sau khi ứng dụng đã bắt đầu dùng locale-sensitive APIs rồi mong thứ tự tự đổi.** LocaleServiceProvider đọc/cache cấu hình ở giai đoạn khởi tạo; JDK docs khuyến nghị đặt property trên **java launcher command line**.

### 4.1. Mặc định CLDR và một negative test có ích

Trong JDK hiện đại, **CLDR** là lựa chọn mặc định nếu không chỉ định các adapter khác. Trong demo, lệnh:

~~~bash
java -Djava.locale.providers=CLDR \
    -cp build/classes demo.app.NumberProviderDemo
~~~

vẫn có thể cho kết quả:

~~~text
serviceDiscovered=true
localeOffered=false
providers=CLDR
~~~

Vì **ServiceLoader** trực tiếp vẫn thấy descriptor và class của provider trong classpath, nhưng **NumberFormat factories** không tích hợp SPI khi adapter order chỉ có CLDR.

Đó là một phân biệt cực kỳ quan trọng khi debug: **“ServiceLoader đã thấy provider” không đồng nghĩa “JDK locale factory đã chọn provider”**.

Trong test trên OpenJDK 24, formatting với CLDR-only đã trở về dấu số thông thường và mã currency theo locale/region runtime. Không dựa vào từng ký tự spacing/currency symbol CLDR làm expected output cố định cho mọi JDK release, vì dữ liệu CLDR và Unicode locale preferences thay đổi giữa các phiên bản.

### 4.2. Ưu tiên provider trùng Locale

Nếu cả SPI và CLDR đều cung cấp formatter cho cùng requested locale, thứ tự adapter đã chọn có thể ảnh hưởng implementation nào được dùng. Khi sản phẩm muốn provider riêng có quyền ưu tiên, cấu hình rõ **SPI,CLDR** và kiểm thử behavior cụ thể, không giả định ServiceLoader registration một mình là đủ.

Nếu SPI không hỗ trợ Locale được yêu cầu hoặc một Locale trong candidate chain phù hợp, runtime có thể dùng CLDR. Không bắt mọi locale chung đi qua provider tự tạo; provider chỉ nên công bố những Locale mà nó xử lý thật.

### 4.3. Khác biệt giữa CLDR và phiên bản JDK

CLDR cung cấp dữ liệu locale được cập nhật theo thời gian. Dấu nhóm, ký hiệu currency, cách hiển thị phần trăm, format accounting và các thay đổi về locale là những chi tiết có thể khác nhau giữa các phiên bản JDK/CLDR.

Khi viết test:

- Kiểm tra **provider được lựa chọn** qua ký hiệu demo đặc trưng và adapter config.
- Với số tiền thật, kiểm tra quy tắc theo phiên bản toolchain mà sản phẩm hỗ trợ.
- Không cứng hóa Unicode space, NBSP, currency symbol hoặc grouping cho tất cả JDK vendor/version khi không có contract bắt buộc.
- Cố định test runtime version khi chính sách sản phẩm đòi output đồng nhất tuyệt đối.

## 5. Đăng ký NumberFormatProvider bằng Java Service Provider mechanism

Đối với **classpath/unnamed module**, provider là một Java class public, có constructor public không tham số, kế thừa NumberFormatProvider và nằm trong artifact có resource đăng ký:

~~~text
META-INF/services/java.text.spi.NumberFormatProvider
~~~

Nội dung **một dòng** (tên class provider đầy đủ):

~~~text
demo.spi.DemoNumberFormatProvider
~~~

Java service configuration file được mã hóa bằng **UTF-8**. Trong project thật, file này thường được đặt tại:

~~~text
src/main/resources/META-INF/services/java.text.spi.NumberFormatProvider
~~~

Build system sẽ copy resource vào JAR/classes. File service cần có **đúng tên abstract service type**, không được dùng tên **NumberFormat**, tên class client hoặc tên annotation khác. Nếu artifact shading/packaging thay đổi class name, descriptor phải được cập nhật tương ứng.

Một **META-INF/services** được đặt nhầm dưới package **demo/spi/** hoặc không nằm trên runtime classpath sẽ khiến Java không phát hiện provider từ classpath.

### 5.1. Hai quá trình khác nhau

~~~text
(1) Service discovery
META-INF/services/java.text.spi.NumberFormatProvider
                    │
                    ▼
ServiceLoader.finds demo.spi.DemoNumberFormatProvider

(2) Locale service selection
NumberFormat.getNumberInstance(qaa-QA)
                    │
       java.locale.providers=SPI,CLDR ?
                    │
           provider có hỗ trợ locale?
                    │
                    ▼
               NumberFormat
~~~

**Service discovery** trả lời “JAR có công bố implementation không?”. **Locale service selection** trả lời “JDK có dùng implementation đó cho lời gọi này không?”. Cả hai đều cần phù hợp.

### 5.2. Packaging bằng named module

Nếu provider được đóng gói như một **named Java module**, dùng **provides** trong module descriptor thay vì trông đợi descriptor classpath:

~~~java
// Mảnh minh họa module-info.java, không phải module hoàn chỉnh.
module demo.numberformats {
    provides java.text.spi.NumberFormatProvider
            with demo.spi.DemoNumberFormatProvider;
}
~~~

Provider cần public/accessibility phù hợp và nằm trên **module path** mà runtime dùng để tìm module/service. Cần cấu hình launcher/module path đúng; không đưa riêng module-info.java vào ví dụ classpath ở phần sau.

Cả classpath ServiceLoader configuration và JPMS provides declaration **đều còn là cơ chế chuẩn hiện hành**. Chọn một đường packaging phù hợp với cách chạy ứng dụng.

## 6. Ví dụ chạy được Java 17+: một NumberFormatProvider đầy đủ

Ví dụ sử dụng **Locale.forLanguageTag("qaa-QA")** cho demonstration. Các ký hiệu không theo quy tắc thực của một quốc gia:

- Dấu nhóm: **_**
- Dấu thập phân: **~**
- Ký hiệu tiền tệ demo: **Q$**
- Currency object để kiểm tra API: **USD**
- Percent sign: **%**

Các giá trị này được chọn **chỉ để nhìn ra provider đã chạy**, không phải hướng dẫn định dạng giao dịch thực tế.

### 6.1. Cấu trúc project

~~~text
numberformat-spi-demo/
├── src/
│   └── demo/
│       ├── spi/DemoNumberFormatProvider.java
│       └── app/NumberProviderDemo.java
└── resources/
    └── META-INF/
        └── services/
            └── java.text.spi.NumberFormatProvider
~~~

### 6.2. Provider class

Tạo file **src/demo/spi/DemoNumberFormatProvider.java** với mã sau:

~~~java
package demo.spi;

import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Currency;
import java.util.Locale;

public final class DemoNumberFormatProvider extends NumberFormatProvider {
    private static final Locale SUPPORTED = Locale.forLanguageTag("qaa-QA");

    public DemoNumberFormatProvider() {}

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { SUPPORTED };
    }

    private static void requireSupported(Locale locale) {
        if (locale == null) {
            throw new NullPointerException("locale");
        }
        if (!SUPPORTED.equals(locale)) {
            throw new IllegalArgumentException("Unsupported locale: " + locale);
        }
    }

    private static DecimalFormat create(String pattern) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.ROOT);
        symbols.setGroupingSeparator('_');
        symbols.setDecimalSeparator('~');
        symbols.setCurrency(Currency.getInstance("USD"));
        symbols.setCurrencySymbol("Q$");
        symbols.setMonetaryGroupingSeparator('_');
        symbols.setMonetaryDecimalSeparator('~');
        DecimalFormat result = new DecimalFormat(pattern, symbols);
        result.setRoundingMode(RoundingMode.HALF_EVEN);
        return result;
    }

    @Override
    public NumberFormat getNumberInstance(Locale locale) {
        requireSupported(locale);
        return create("#,##0.00");
    }

    @Override
    public NumberFormat getIntegerInstance(Locale locale) {
        requireSupported(locale);
        DecimalFormat result = create("#,##0");
        result.setParseIntegerOnly(true);
        return result;
    }

    @Override
    public NumberFormat getCurrencyInstance(Locale locale) {
        requireSupported(locale);
        return create("\u00A4#,##0.00");
    }

    @Override
    public NumberFormat getPercentInstance(Locale locale) {
        requireSupported(locale);
        return create("#,##0.0%");
    }
}
~~~

### 6.3. Giải thích các lựa chọn trong provider

**Constructor public không tham số:** ServiceLoader/classpath registration có thể khởi tạo class bằng constructor phù hợp. Abstract class cha có constructor protected, class con triển khai constructor public.

**getAvailableLocales():** trả mảng mới chứa qaa-QA. Không trả mảng mutable static có thể bị bên ngoài sửa mất phần tử.

**requireSupported(...):** kiểm tra null và chỉ nhận qaa-QA chính xác. Đây là policy demo; nếu muốn locale extensions hoặc fallback variants, cần thiết kế tương thích với contract của isSupportedLocale/locale lookup, không sao chép kiểm tra equality này mù quáng.

**create(pattern):** tạo **DecimalFormatSymbols** riêng, thiết lập ký hiệu demo rồi tạo **DecimalFormat mới**. Không gọi **NumberFormat.getNumberInstance(SUPPORTED)** từ trong **getNumberInstance(...)** của provider: việc đó có thể gọi ngược vào chính provider và gây vòng lặp/stack overflow.

**setGroupingSeparator('_')** và **setDecimalSeparator('~')** cấu hình dấu cho số thông thường.

**setCurrency(Currency.getInstance("USD"))** gắn currency object hợp lệ. **setCurrencySymbol("Q$")** chỉ thay đổi symbol được render trong ví dụ. Currency code vẫn là **USD**.

**setMonetaryGroupingSeparator('_')** và **setMonetaryDecimalSeparator('~')** là hai lệnh quan trọng: **pattern tiền tệ với ký hiệu ¤ có thể dùng monetary separators khác ordinary separators**. Nếu chỉ sửa grouping/decimal thông thường, output currency có thể vẫn dùng dấu mặc định, dù output số thường đã thay đổi. Điều này đã được phát hiện và kiểm chứng khi chạy chương trình trên JDK 24.

**setRoundingMode(HALF_EVEN):** minh họa rounding policy. Với số nguyên, formatter có pattern không hiển thị phần thập phân; **setParseIntegerOnly(true)** đáp ứng parsing policy của integer formatter.

**Các get*Instance:** mỗi method tạo **formatter mới**. Chúng không giữ DecimalFormat mutable trong static field rồi trả cùng reference cho mọi client/thread.

**Percent:** pattern **#,##0.0%** làm tỷ lệ 0.125 thành 12~5%; không tự nhân giá trị đầu vào trước.

### 6.4. Client class dùng các factory NumberFormat

Tạo **src/demo/app/NumberProviderDemo.java**:

~~~java
package demo.app;

import java.math.BigDecimal;
import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Arrays;
import java.util.Locale;
import java.util.ServiceLoader;

public final class NumberProviderDemo {
    private static final Locale CUSTOM = Locale.forLanguageTag("qaa-QA");

    public static void main(String[] args) {
        boolean discovered = ServiceLoader.load(NumberFormatProvider.class)
                .stream().anyMatch(p -> p.type().getName()
                        .equals("demo.spi.DemoNumberFormatProvider"));
        System.out.println("serviceDiscovered=" + discovered);
        System.out.println("localeOffered="
                + Arrays.asList(NumberFormat.getAvailableLocales()).contains(CUSTOM));
        System.out.println("providers=" + System.getProperty("java.locale.providers"));

        NumberFormat number = NumberFormat.getNumberInstance(CUSTOM);
        NumberFormat integer = NumberFormat.getIntegerInstance(CUSTOM);
        NumberFormat money = NumberFormat.getCurrencyInstance(CUSTOM);
        NumberFormat percent = NumberFormat.getPercentInstance(CUSTOM);
        System.out.println("number=" + number.format(new BigDecimal("1234567.89")));
        System.out.println("integer=" + integer.format(1234567.6));
        System.out.println("parseIntegerOnly=" + integer.isParseIntegerOnly());
        System.out.println("currency=" + money.format(new BigDecimal("1234.5")));
        System.out.println("currencyCode=" + money.getCurrency().getCurrencyCode());
        System.out.println("percent=" + percent.format(new BigDecimal("0.125")));
        System.out.println("separateInstances="
                + (number != NumberFormat.getNumberInstance(CUSTOM)));
    }
}
~~~

**Tại sao dùng BigDecimal trong ví dụ?** Khi một con số được biểu diễn từ chuỗi thập phân và cần kiểm soát chính xác giá trị ban đầu, **new BigDecimal("...")** tránh sai số nhị phân có thể xuất hiện từ việc khởi tạo một số thập phân theo **double**. Tuy vậy, **formatting không thay thế tính toán tài chính**, và ngay cả BigDecimal cũng cần rounding/scale/domain policy.

**Tại sao test bằng dấu kỳ lạ?** Nếu NumberFormat thực sự chọn provider, output sẽ có **1_234_567~89**, rất khác format CLDR thường gặp. Nhìn mỗi **serviceDiscovered=true** không đủ kiểm chứng đường selection.

### 6.5. Service provider configuration file

Tạo file đúng đường dẫn **resources/META-INF/services/java.text.spi.NumberFormatProvider** với nội dung:

~~~text
demo.spi.DemoNumberFormatProvider
~~~

Không có phần mở rộng **.txt** hoặc **.java**. File chứa **fully qualified class name** của provider, không phải của client. Khi đóng gói JAR, resource phải nằm tại **META-INF/services/java.text.spi.NumberFormatProvider**.

### 6.6. Compile/run trên Linux, macOS hoặc Bash

Đứng tại thư mục **numberformat-spi-demo**:

~~~bash
mkdir -p build/classes/META-INF/services

javac -encoding UTF-8 --release 17 \
    -d build/classes \
    src/demo/spi/DemoNumberFormatProvider.java \
    src/demo/app/NumberProviderDemo.java

cp resources/META-INF/services/java.text.spi.NumberFormatProvider \
   build/classes/META-INF/services/

java -Djava.locale.providers=SPI,CLDR \
    -cp build/classes demo.app.NumberProviderDemo
~~~

**Lưu ý:** Option **-Djava.locale.providers=SPI,CLDR** thuộc lệnh **java launcher**, không phải một argument ứng dụng sau tên main class. Nên đặt nó **trước -cp hoặc trước main class** để JVM đọc cấu hình khi khởi tạo.

Nếu bạn muốn chạy demo trực tiếp trong Maven/Gradle, resource-processing phase phải copy descriptor đến đúng đường dẫn output. Chỉ compile hai file Java mà quên service descriptor là không đủ.

### 6.7. Compile/run trên Windows PowerShell

Mã nguồn Java giữ nguyên; tạo thư mục output, compile và copy descriptor:

~~~powershell
New-Item -ItemType Directory -Force build/classes/META-INF/services | Out-Null

javac -encoding UTF-8 --release 17 -d build/classes src/demo/spi/DemoNumberFormatProvider.java src/demo/app/NumberProviderDemo.java

Copy-Item resources/META-INF/services/java.text.spi.NumberFormatProvider build/classes/META-INF/services/

java "-Djava.locale.providers=SPI,CLDR" -cp build/classes demo.app.NumberProviderDemo
~~~

File service descriptor phải là text UTF-8 hợp lệ. Nếu bạn tự tạo descriptor bằng PowerShell 5.1 thay vì copy file UTF-8 sẵn có, hãy tránh các thao tác ghi có thể thêm BOM không mong muốn; có thể dùng **System.IO.File.WriteAllText** với **UTF8Encoding(false)**.

### 6.8. Stdout chính xác đã kiểm chứng

Chạy đúng lệnh với **SPI,CLDR** trên OpenJDK 24.0.2:

~~~text
serviceDiscovered=true
localeOffered=true
providers=SPI,CLDR
number=1_234_567~89
integer=1_234_568
parseIntegerOnly=true
currency=Q$1_234~50
currencyCode=USD
percent=12~5%
separateInstances=true
~~~

**Đây là 10 dòng stdout**, đã kiểm tra khớp từng dòng sau khi biên dịch bằng **--release 17**.

Ý nghĩa chính:

- **serviceDiscovered=true**: ServiceLoader tìm thấy provider đã đăng ký.
- **localeOffered=true**: trong cấu hình đang chạy, NumberFormat.getAvailableLocales có qaa-QA.
- **providers=SPI,CLDR**: adapter list ưu tiên SPI.
- **number**: custom grouping và ordinary decimal separators hoạt động.
- **integer**: dữ liệu được làm tròn về số nguyên theo pattern và policy.
- **parseIntegerOnly=true**: integer formatter hỗ trợ parsing integer-only.
- **currency**: custom monetary grouping/decimal separators và ký hiệu demo hoạt động.
- **currencyCode=USD**: mã tiền trong Currency object vẫn là USD.
- **percent**: đầu vào ratio 0.125 được nhân lên 100 khi hiển thị.
- **separateInstances=true**: hai factory calls trả các NumberFormat objects khác nhau trong lần chạy kiểm chứng, phù hợp quy tắc tránh chia sẻ mutable formatter.

## 7. Negative test: provider được khám phá nhưng không được chọn

Chạy cùng output classes và cùng service descriptor, chỉ thay **adapter configuration**:

~~~bash
java -Djava.locale.providers=CLDR \
    -cp build/classes demo.app.NumberProviderDemo
~~~

Trên PowerShell:

~~~powershell
java "-Djava.locale.providers=CLDR" -cp build/classes demo.app.NumberProviderDemo
~~~

Trong phép thử OpenJDK 24.0.2, ba dòng đầu:

~~~text
serviceDiscovered=true
localeOffered=false
providers=CLDR
~~~

Các dòng số/tiền tệ/phần trăm sử dụng định dạng CLDR thay vì quy tắc **_** và **~** của provider. Trong phép thử riêng này, số thông thường được in là **1,234,567.89**, còn currency đến từ dữ liệu CLDR cho region QA thay vì ký hiệu **Q$** demo.

**Đừng dùng toàn bộ stdout CLDR-only làm golden output cố định qua nhiều phiên bản JDK**: ký hiệu tiền tệ, spacing và dữ liệu locale có thể thay đổi. Điểm cần chứng minh là **service descriptor tồn tại**, **ServiceLoader vẫn thấy provider**, nhưng **adapter list không có SPI nên NumberFormat factories không sử dụng provider đó**.

### 7.1. Khi nào dùng một JVM riêng?

Property **java.locale.providers** được xử lý lúc khởi tạo locale service. Để so sánh SPI,CLDR và CLDR-only, hãy chạy **hai tiến trình java riêng**, như hai lệnh ở trên. Không cố đổi System.setProperty trong cùng process rồi dùng kết quả như bằng chứng mạnh, bởi adapter order có thể đã được cache.

### 7.2. Cách chẩn đoán khi output không có dấu demo

Kiểm tra lần lượt:

1. Có descriptor **META-INF/services/java.text.spi.NumberFormatProvider** không?
2. Descriptor chứa đúng **demo.spi.DemoNumberFormatProvider** và không có BOM/ký tự lạ làm lỗi parsing không?
3. Provider class + dependencies có trong runtime classpath/module path mà **system classloader** thấy không?
4. **java.locale.providers** có chứa **SPI** và được đặt lúc startup không?
5. **Locale** truyền vào factory có đúng **qaa-QA**, không bị đổi mặc định sang en-US/vi-VN không?
6. Provider công bố Locale trong **getAvailableLocales()** và **isSupportedLocale(...)** có đồng ý không?
7. Code gọi **NumberFormat.getNumberInstance(CUSTOM)** hay vô tình gọi overload không tham số dùng default **Locale.Category.FORMAT**?
8. Một adapter khác đứng trước SPI có cung cấp Locale đó không?
9. Có classloader/module boundaries, service duplicates hoặc provider không có constructor hợp lệ không?
10. Kết quả được tạo từ đúng build artifact hiện tại, không phải output stale của lần compile cũ?

## 8. Formatting, parsing và chính sách rounding

### 8.1. NumberFormat được dùng cho cả format và parse

**NumberFormat.format(number)** tạo chuỗi theo locale. **NumberFormat.parse(text)** thực hiện parse theo syntax của formatter và có thể trả **Number** với kiểu cụ thể phụ thuộc implementation.

Không mặc định:

- Mọi provider đều trả **DecimalFormat**.
- Mọi parser phải tiêu thụ toàn bộ chuỗi input.
- Một giá trị đã format ra 2 chữ số thập phân có thể khôi phục chính xác toàn bộ input gốc.
- Một formatter percent sẽ parse giống một formatter number thông thường.
- Dấu ngăn nhóm, dấu tiền tệ và khoảng trắng có thể bỏ qua khi parse qua locale khác.
- Mã tiền được trích xuất chính xác chỉ bằng việc parse text hiển thị nếu có ambiguity về symbol.

Nếu cần **kiểm tra toàn bộ input được parse**, có thể dùng **ParsePosition**:

~~~java
// Mảnh minh họa, cần import java.text.NumberFormat, ParsePosition.
ParsePosition pos = new ParsePosition(0);
Number parsed = formatter.parse(input, pos);

boolean complete = parsed != null
        && pos.getIndex() == input.length()
        && pos.getErrorIndex() < 0;
~~~

**formatter** và **input** phải do chương trình cung cấp. Đoạn trên chỉ minh họa cách kiểm tra parser không dừng giữa chuỗi mà báo thành công một phần.

### 8.2. DecimalFormat và BigDecimal

Nếu bạn thực sự có **DecimalFormat** và muốn parsing dữ liệu số thập phân như BigDecimal theo contract của implementation đó, có thể cấu hình:

~~~java
// Mảnh minh họa; không áp dụng nếu returned type không là DecimalFormat.
if (formatter instanceof DecimalFormat decimal) {
    decimal.setParseBigDecimal(true);
}
~~~

Đừng cast **NumberFormat** sang DecimalFormat vô điều kiện: một SPI có thể cung cấp một subclass NumberFormat khác. Khi format tiền tệ trong code thực tế, **BigDecimal** nên được kết hợp với **Currency** và quy tắc scale/rounding của domain, thay vì để formatting quyết định số tiền phải giao dịch.

### 8.3. Rounding mode và fraction digits

**NumberFormat.setMaximumFractionDigits(...)**, **setMinimumFractionDigits(...)**, **setRoundingMode(...)** (nếu implementation hỗ trợ) có thể thay đổi output. Các thao tác đó liên quan **làm tròn để hiển thị**, không tự thay đổi giá trị BigDecimal gốc.

Khi dùng kiểu số nguyên, các case tie như **2.5** và **3.5** giúp kiểm tra HALF_EVEN: nearest even integer lần lượt là **2** và **4**. Không dùng trực tiếp double representation cho yêu cầu tiền tệ chính xác nếu có thể tránh, đặc biệt khi tích lũy phép tính qua nhiều bước.

### 8.4. Percent input là tỷ lệ, không phải số phần trăm đã nhân

Nếu dữ liệu nghiệp vụ lưu **0.125** cho 12.5%, dùng formatter percent trực tiếp. Nếu một API đưa bạn giá trị **12.5** với ý nghĩa “12.5 percent”, cần chuẩn hóa semantics trước khi format, không tự gọi **getPercentInstance().format(12.5)** rồi mong ra 12.5%.

Dùng tài liệu hợp đồng field để phân biệt:

| Field | Ý nghĩa | Giá trị đưa vào Percent NumberFormat |
| --- | --- | --- |
| ratio | 0.125 = 12.5% | **0.125** |
| percentPoints | 12.5 = 12.5 điểm phần trăm | Chuyển thành **0.125** nếu muốn hiển thị 12.5% |
| integerPercent | 15 = 15% | Chuyển thành **0.15** theo quy tắc nghiệp vụ |

## 9. Monetary symbols không phải ordinary symbols

Đây là một chi tiết dễ gây lỗi ngay cả với người quen DecimalFormat.

**DecimalFormatSymbols** có:

| API | Vai trò |
| --- | --- |
| **setGroupingSeparator(char)** | Dấu nhóm trong số thông thường |
| **setDecimalSeparator(char)** | Dấu thập phân số thông thường |
| **setMonetaryGroupingSeparator(char)** | Dấu nhóm cho monetary format |
| **setMonetaryDecimalSeparator(char)** | Dấu thập phân cho monetary format |
| **setCurrency(Currency)** | Gắn currency object |
| **setCurrencySymbol(String)** | Đặt ký hiệu currency để hiển thị |
| **setInternationalCurrencySymbol(String)** | Đặt mã tiền tệ quốc tế theo contract; cẩn thận với giá trị được cung cấp |

Với pattern **¤#,##0.00**, DecimalFormat có thể sử dụng các ký hiệu **monetary** chứ không đơn thuần các ký hiệu number. Điều này giải thích vì sao chỉ đặt ordinary separators có thể làm **number=1_234_567~89** nhưng currency vẫn hiện **1,234.50**.

Trong provider của ví dụ, đã thiết lập **cả ordinary và monetary separators**, nên output currency có **Q$1_234~50** theo đúng yêu cầu kiểm thử.

**Không đồng nhất setCurrencySymbol với setCurrency.** Thay ký hiệu không thay metadata ISO của Currency object. Một hệ thống thanh toán không được suy ra số tiền/currency chính xác từ một String display có ký hiệu tùy ý.

### 9.1. Ký hiệu tiền có thể không duy nhất

Dấu **$** có thể được dùng cho nhiều đồng tiền. Một formatter cho giao diện người dùng có thể dùng ký hiệu bản địa, ký hiệu có tiền tố quốc gia hoặc ISO code để tránh nhầm lẫn. Lựa chọn phải theo hợp đồng sản phẩm, ví dụ khi hiển thị nhiều currency cùng một màn hình.

Một số currencies có **0 fraction digits** theo quy tắc ISO; nhiều nghiệp vụ lại có quy định riêng. Không hard-code luôn 2 chữ số thập phân cho mọi Currency. Đoạn demo dùng USD và hai chữ số vì mục tiêu kiểm chứng SPI, không phải một financial formatter tổng quát.

### 9.2. Khi locale có Unicode extension

Locale có thể mang extension **nu** cho numbering system, **rg** cho region override, **cf** cho currency format style, **cu** cho currency type. Runtime hỗ trợ từng extension tùy provider/data, không thể đảm bảo mọi implementation hiểu mọi giá trị.

Nếu NumberFormatProvider muốn hỗ trợ đầy đủ các extensions, nó nên:

- Kiểm tra Locale gốc và extensions theo **isSupportedLocale** có chủ đích.
- Không lặng lẽ bỏ qua currency override nếu contract đã hứa tôn trọng nó.
- Đọc/định nghĩa numbering system, currency selection và rounding chính xác.
- Có test cho unsupported extension để chọn cách phản hồi/fallback phù hợp.

## 10. Quy tắc provider stateless, thread safety và vòng đời

**NumberFormat** và **DecimalFormat** có các setter nên formatter là object có thể thay đổi. Ở ứng dụng multi-thread:

- Đừng dùng một static **DecimalFormat** chung để nhiều thread vừa gọi format vừa thay đổi cấu hình.
- Mỗi lần factory được gọi, provider trả **formatter mới** đúng contract.
- Provider class có thể được runtime dùng lại. Bản thân provider nên **không có mutable state dùng chung cho các requests**, hoặc phải đồng bộ/thiết kế thread-safe khi bắt buộc.
- Nếu cache immutable metadata hoặc templates, giữ dữ liệu bất biến; đừng trả về cùng một DecimalFormat mutable từ cache.
- Đừng để constructor/newBundle service có side effects phụ thuộc thời điểm chạy, host locale hoặc network khi không cần.
- Nếu một NumberFormat subclass tùy chỉnh override format/parse, bảo đảm các overload cơ bản, rounding/parse settings và semantics của nó nhất quán.
- Nếu muốn dùng **clone()** cho formatter, vẫn cần xác minh implementation cụ thể và ownership; việc tạo mới thường dễ kiểm soát nhất trong ví dụ này.

Provider không phải một nơi để lưu dữ liệu nghiệp vụ theo user/session. Nó cung cấp **chiến lược định dạng**, không nên giữ transaction amounts hay thông tin cá nhân trong singleton mutable state.

## 11. Phân biệt NumberFormatProvider với các SPI liên quan

Trong package **java.text.spi**, có nhiều provider cho các phần quốc tế hóa khác nhau:

| SPI | Trách nhiệm |
| --- | --- |
| **NumberFormatProvider** | Tạo formatter cho number/integer/currency/percent |
| **DecimalFormatSymbolsProvider** | Cung cấp bộ ký hiệu cho DecimalFormat theo Locale |
| **DateFormatProvider** | Tạo date/time formatter của java.text |
| **DateFormatSymbolsProvider** | Cung cấp symbols dùng cho date/time formatting |
| **CollatorProvider** | Cung cấp cách so sánh/sắp xếp văn bản theo Locale |
| **BreakIteratorProvider** | Cung cấp cách chia ranh giới đoạn/ký tự/từ/câu |
| **CurrencyNameProvider** | Cung cấp tên/ký hiệu tiền tệ theo Locale |
| **LocaleNameProvider** | Cung cấp tên hiển thị của Locale components |

**Sửa symbols không tương đương triển khai toàn bộ NumberFormatProvider.** Nếu nhu cầu chỉ là thay ký hiệu tiền tệ hoặc dấu thập phân trong một formatter, trước tiên xem khả năng cấu hình **DecimalFormatSymbols** cục bộ. Nếu muốn cung cấp symbols ở tầng factory hệ thống, **DecimalFormatSymbolsProvider** mới đúng vai trò.

**CurrencyNameProvider** ảnh hưởng tên/ký hiệu currency cho Locale; nó không thay thế NumberFormatProvider trong việc tạo formatter có rounding, grouping hoặc percent semantics.

Tương tự, **NumberFormatProvider** không quyết định thứ tự lựa chọn **Locale** của người dùng trong ứng dụng; locale resolution/selection policy là bài toán khác.

## 12. Classpath packaging, JAR và JPMS

### 12.1. Một JAR provider thường chứa những gì?

~~~text
demo-numberformats.jar
├── demo/spi/DemoNumberFormatProvider.class
└── META-INF/services/java.text.spi.NumberFormatProvider
~~~

Trong dự án thật, class trong JAR sẽ có thêm dependency nếu provider dựa vào thư viện khác. JDK cần **system classloader** có thể nhìn thấy service provider phù hợp khi locale service lookup diễn ra.

Một descriptor có thể chứa nhiều provider class names (mỗi dòng một provider), nhưng cần tránh trùng tên/tài nguyên khi shading nhiều JAR. Nếu cùng service bị các JAR khác nhau đăng ký nhiều implementations cho cùng Locale, việc lựa chọn phải được kiểm thử và quản lý bằng packaging/order policy rõ ràng.

### 12.2. Khi nào nên tạo module riêng?

Nếu dùng JPMS, module có thể khai báo service:

~~~java
module demo.numberformats {
    provides java.text.spi.NumberFormatProvider
            with demo.spi.DemoNumberFormatProvider;
}
~~~

Đây là **mảnh module descriptor minh họa**, chưa bao gồm cấu trúc đầy đủ của ứng dụng module. Thêm dependency/module path và cấu hình launch thích hợp trong dự án của bạn. **Không** phải thêm **META-INF/services** vào named module rồi bỏ qua module declaration nếu muốn dùng đường service modular chuẩn.

### 12.3. Vì sao cần test artifact thực, không chỉ class sources?

Nếu ứng dụng chạy từ IDE, class output có thể chứa descriptor nằm đúng thư mục. Khi đóng gói JAR, bước resource copy/shading có thể làm descriptor biến mất. Kết quả: class Java vẫn compile, nhưng ServiceLoader không còn tìm được provider.

Hãy kiểm tra artifact sau đóng gói bằng tool phù hợp, ví dụ:

~~~bash
jar tf demo-numberformats.jar
~~~

Phải thấy **META-INF/services/java.text.spi.NumberFormatProvider** hoặc module declaration được build đúng. Đừng xem “compiler không có error” là bằng chứng service registration đã hoạt động.

## 13. Những lỗi phổ biến và cách giải quyết

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/sửa |
| --- | --- | --- |
| **serviceDiscovered=false** | Thiếu descriptor, sai path/class name hoặc classloader không thấy provider | Xem META-INF/services trong artifact, package và constructor |
| ServiceLoader thấy provider nhưng format không đổi | Adapter list không có SPI hoặc thứ tự ưu tiên khác | Chạy với **-Djava.locale.providers=SPI,CLDR** lúc startup |
| **localeOffered=false** trong NumberFormat.getAvailableLocales | SPI không được chọn trong runtime | Kiểm tra java.locale.providers và service metadata |
| Factory trả dấu thường thay vì dấu demo | Provider không được chọn, Locale khác hoặc data adapter khác ưu tiên | Kiểm tra requested Locale, SPI order và output |
| **ServiceConfigurationError** | Provider class không thể nạp, constructor lỗi hoặc descriptor sai | Xem stack trace, public class/constructor, runtime dependencies |
| **IllegalArgumentException: Unsupported locale** | Factory bị gọi trực tiếp hoặc Runtime đưa Locale khác cách provider validation dự tính | Xem getAvailableLocales/isSupportedLocale/locale extensions |
| **NullPointerException** trong provider | Locale null hoặc phần cấu hình bắt buộc null | Validate locale/options, không trả null formatter |
| **StackOverflowError** khi tạo format | Provider gọi ngược NumberFormat.get*Instance cùng locale | Tạo implementation trực tiếp, tránh recursive factory call |
| Số thường dùng dấu demo nhưng currency không đổi | Chưa cấu hình monetary separators | Dùng setMonetaryGroupingSeparator và setMonetaryDecimalSeparator |
| Phần trăm lớn gấp 100 lần | Caller tự nhân 100 trước khi đưa vào percent formatter | Truyền ratio như 0.125 cho 12.5% |
| Currency code không phải ký hiệu hiển thị | Nhầm symbol với Currency object | Kiểm tra getCurrency().getCurrencyCode(), symbol và domain |
| Output sai khi nhiều thread | Formatter mutable bị chia sẻ | Factory trả object mới, quản lý cache/thread-safety |
| Unit test khác giữa JDK | CLDR/currency symbols/spacing hoặc rounding configuration khác | Cố định toolchain/test data, không snapshot output host không kiểm soát |
| Parse dừng giữa input nhưng vẫn trả Number | Parser lenient hoặc không kiểm tra consumed length | Dùng ParsePosition/full-consumption validation |
| Format integer nhưng parse nhận phần thập phân | Chưa thiết lập parseIntegerOnly | Cấu hình và kiểm thử getIntegerInstance |
| Descriptor có BOM hoặc encoding sai | Service file không đúng UTF-8 format | Lưu descriptor UTF-8 hợp lệ, không BOM |
| Provider chạy được IDE nhưng fail JAR | Descriptor bị bỏ khi packaging hoặc dependency thiếu | Kiểm tra JAR content, module/classloader |
| Không hoạt động khi dùng Locale có extension | Provider chỉ kiểm tra equals exact | Thiết kế isSupportedLocale + factory cho extensions/fallback |
| Dùng NumberFormat cho giao dịch tài chính | Lẫn hiển thị với số tiền thực và rounding | Lưu BigDecimal/Currency chính xác theo domain, format chỉ cho UI |

### 13.1. Debug theo thứ tự

1. Kiểm tra **Locale.forLanguageTag(...).toLanguageTag()** của yêu cầu.
2. Xác minh descriptor bằng **ServiceLoader.load(NumberFormatProvider.class)**.
3. Kiểm tra NumberFormat.getAvailableLocales() có bao gồm Locale demo khi cấu hình SPI hay không.
4. In **System.getProperty("java.locale.providers")** (không ghi dữ liệu nhạy cảm).
5. Xác minh JVM được khởi động với **SPI,CLDR** trước khi locale service khởi tạo.
6. So sánh output đặc trưng trong sample, ví dụ **1_234_567~89**.
7. Nếu currency sai, kiểm tra MonetaryDecimal/GroupingSeparator và Currency object.
8. Nếu percent sai, kiểm tra semantics ratio/percentPoints.
9. Nếu parse lỗi, kiểm tra ký hiệu, rounding, parse-integer-only, full-consumption.
10. Nếu chỉ xảy ra trong deployment, kiểm tra JAR/modules, system classloader, provider dependencies.
11. Chạy lại trên cùng JDK version với clean output để loại bỏ artifacts cũ.

## 14. Khi nào không nên tạo custom NumberFormatProvider?

Không phải mọi nhu cầu format là nhu cầu SPI.

**Chỉ cần hiển thị số/tiền tệ/phần trăm cho các Locale phổ biến:** dùng các factory chuẩn:

~~~java
// Mảnh code minh họa.
Locale locale = Locale.forLanguageTag("vi-VN");
NumberFormat number = NumberFormat.getNumberInstance(locale);
NumberFormat money = NumberFormat.getCurrencyInstance(locale);
NumberFormat percent = NumberFormat.getPercentInstance(locale);
~~~

**Chỉ muốn điều chỉnh một formatter:** có thể lấy NumberFormat và sử dụng setter được hỗ trợ hoặc tạo DecimalFormat + DecimalFormatSymbols cục bộ, không cần ảnh hưởng toàn JVM.

**Muốn thay ký hiệu số theo Locale toàn runtime:** tìm hiểu **DecimalFormatSymbolsProvider**; nhưng vẫn cần cân nhắc adapter order và side effects cho các thư viện dùng chung.

**Muốn đổi luật tính tiền:** NumberFormatProvider không đủ. Số tiền, currency, rounding/tax/FX rates và chính sách tài chính cần implementation nghiệp vụ có test riêng. NumberFormat chỉ chịu trách nhiệm về representation và parsing.

**Muốn định dạng kiểu dữ liệu mới không phải Number:** xây formatter riêng theo domain thay vì ép mọi logic vào NumberFormatProvider.

**Muốn hỗ trợ locale chuẩn sẵn có:** trước hết kiểm tra dữ liệu CLDR của JDK đang dùng; đừng copy một snapshot format địa phương vào provider mới nếu không có yêu cầu override thực tế.

## 15. Bài tập thực hành

1. Thay pattern number từ **#,##0.00** thành **#,##0.000** rồi chạy lại, kiểm tra phần thập phân của 1234567.89.
2. Thử format 2.5 và 3.5 bằng integer formatter; giải thích HALF_EVEN và sự khác biệt so với cắt phần thập phân.
3. Đổi **0.125** sang **0.075** với Percent NumberFormat. Dự đoán output theo pattern và rounding.
4. Cố tình bỏ hai lệnh **setMonetaryGroupingSeparator** và **setMonetaryDecimalSeparator**. So sánh output currency với number và giải thích vì sao khác.
5. Chạy một JVM với **SPI,CLDR** và một JVM với **CLDR**. Tạo regression test chứng minh ServiceLoader có thể phát hiện provider dù factory không chọn nó.
6. Đổi **getAvailableLocales()** để công bố thêm Locale khác, nhưng chưa cập nhật requireSupported; quan sát lỗi để hiểu trách nhiệm nhất quán giữa discovery và factory.
7. Tạo test cho Locale null, Locale không hỗ trợ, và Locale có Unicode extension, rồi viết contract xử lý phù hợp (thay vì chỉ dùng equals exact).
8. Thêm một **DecimalFormatSymbolsProvider** và giải thích khác biệt so với NumberFormatProvider; không giả định JDK tự dùng cả hai nếu chưa cấu hình SPI.
9. Đóng gói provider vào JAR, kiểm tra **META-INF/services/java.text.spi.NumberFormatProvider** có trong archive.
10. Chuyển provider sang named module, khai báo **provides** và chạy module-path riêng; kiểm tra service discovery.
11. Tạo test ParsePosition bảo đảm một chuỗi số có ký tự thừa không được coi là parse thành công toàn bộ.
12. Viết use case hiển thị giá tiền trong nhiều currencies; phân biệt Currency code, symbol và Locale của người xem.

## 16. Checklist production

- [ ] Sự cần thiết của SPI đã rõ; nếu chỉ muốn format một chỗ, dùng formatter cục bộ.
- [ ] NumberFormatProvider công bố Locale đúng và nhất quán với mọi factory methods.
- [ ] Có public no-arg constructor/đăng ký dịch vụ hợp lệ trên classpath hoặc provides đúng trong named module.
- [ ] JVM adapter order được cấu hình ở startup khi cần ưu tiên SPI.
- [ ] Có test chứng minh **factory thực sự chọn provider**, không chỉ ServiceLoader đã thấy class.
- [ ] getNumberInstance, getIntegerInstance, getCurrencyInstance và getPercentInstance đều có hành vi đúng.
- [ ] Integer format/parse tuân thủ rounding và parse-integer policy.
- [ ] Percent đầu vào có semantics ratio rõ; không nhân 100 hai lần.
- [ ] Currency object, symbol, fraction digits và monetary separators được xử lý đúng.
- [ ] Không dùng ký hiệu tiền thử nghiệm như Q$ làm metadata tiền tệ thật.
- [ ] Cấu hình locale extensions/candidate fallback và unsupported Locale có contract rõ.
- [ ] Factory trả formatter mới hoặc một đối tượng có contract thread-safety rõ, không chia sẻ mutable DecimalFormat.
- [ ] Không gọi lại cùng NumberFormat factory từ provider gây recursion.
- [ ] Format output không được dùng làm nguồn tính toán tiền tệ.
- [ ] Tests tách định dạng do provider kiểm soát với output CLDR phụ thuộc JDK release.
- [ ] Classpath/JAR/module metadata được xác minh trong artifact cuối.
- [ ] Không sử dụng adapter options hoặc cơ chế provider đã không còn được hỗ trợ.

## Kết luận

**NumberFormatProvider** là điểm mở rộng chuẩn của **Locale SPI** cho các factory NumberFormat. Một triển khai đúng phải **công bố Locale**, tạo **bốn formatter** với semantics phù hợp, đăng ký provider để runtime khám phá, đồng thời đặt **SPI** vào adapter lookup khi muốn NumberFormat factories thực sự dùng nó.

Số thông thường, số nguyên, tiền tệ và phần trăm có những hợp đồng khác nhau: **grouping/decimal symbols**, **rounding + parseIntegerOnly**, **Currency + monetary symbols**, và **nhân tỷ lệ với 100 khi format percent**. Với Java hiện đại, cần kiểm tra cả **CLDR/SPI priority**, locale extensions, cache/init behavior, classpath/module deployment và tính an toàn khi nhiều thread cùng gọi formatting.

**Tài liệu chính thức đang áp dụng:**

- [NumberFormatProvider — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/spi/NumberFormatProvider.html)
- [LocaleServiceProvider — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleServiceProvider.html)
- [NumberFormat — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/NumberFormat.html)
- [DecimalFormat — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/DecimalFormat.html)
- [DecimalFormatSymbols — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/DecimalFormatSymbols.html)
- [Currency — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Currency.html)
- [ServiceLoader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html)