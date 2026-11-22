# CLDR làm nguồn dữ liệu locale mặc định trong Java

## Mục tiêu

Trong nhóm **Locale và bản dịch**, Java 9 chọn dữ liệu locale từ **Unicode Common Locale Data Repository (CLDR)** làm mặc định. CLDR cung cấp quy ước theo ngôn ngữ và khu vực để các API locale-sensitive hiển thị ngày giờ, số, tiền tệ, tên quốc gia, ngôn ngữ và thông tin văn hóa phù hợp.

**Locale** và **CLDR** có vai trò khác nhau. Locale xác định ngôn ngữ, vùng và các thuộc tính văn hóa mà chương trình yêu cầu; CLDR cung cấp dữ liệu để các API Java thực hiện yêu cầu đó. Cùng một giá trị số hoặc ngày có thể được hiển thị khác nhau khi dùng Locale khác nhau.

Bài này trình bày vì sao Java 9 đổi sang CLDR, cách chọn locale provider trên JDK hiện hành, những API sử dụng dữ liệu locale, cách kiểm thử và xử lý thay đổi dữ liệu khi nâng cấp JDK.

## 1. CLDR là gì?

**CLDR** là kho dữ liệu locale do Unicode Consortium duy trì. Dữ liệu được tổ chức theo ngôn ngữ và khu vực, bao gồm những quy ước như:

- Dấu phân cách phần nguyên và phần thập phân.
- Cách nhóm chữ số trong số lớn.
- Ký hiệu và tên tiền tệ.
- Thứ tự ngày, tháng, năm và mẫu định dạng ngày giờ.
- Tên tháng, thứ trong tuần, quốc gia, ngôn ngữ và múi giờ.
- Quy tắc hiển thị, sắp xếp và phân đoạn văn bản theo locale.

Ví dụ, cùng giá trị `1234567.89` có thể được hiển thị như sau:

| Locale | Cách hiển thị số |
|---|---|
| `en-US` | `1,234,567.89` |
| `de-DE` | `1.234.567,89` |
| `fr-FR` | `1 234 567,89` |

Các dấu phân cách và khoảng trắng trong ví dụ là dữ liệu trình bày theo locale, không làm thay đổi giá trị số bên trong chương trình.

CLDR cũng cung cấp dữ liệu tên tiền tệ và ký hiệu tiền tệ. Dữ liệu này không phải tỷ giá hối đoái; muốn quy đổi tiền, ứng dụng phải dùng nguồn tỷ giá riêng.

## 2. Vì sao CLDR trở thành mặc định từ Java 9?

CLDR đã được đưa vào JDK 8, nhưng ban đầu không phải nguồn locale mặc định. **JEP 252** thay đổi lựa chọn mặc định từ JDK 9 để Java sử dụng dữ liệu chuẩn hóa do Unicode CLDR duy trì.

Điều này giúp Java có bộ dữ liệu locale phong phú và đồng nhất hơn cho các khu vực trên thế giới. Những API chịu ảnh hưởng có thể bao gồm:

- `NumberFormat` và `DecimalFormatSymbols`.
- `DateFormat` và các formatter dựa trên locale.
- `DateTimeFormatter` khi dùng các kiểu định dạng localized.
- `Collator` và `BreakIterator`.
- Các API trong `java.util` và `java.text` lấy tên ngôn ngữ, quốc gia, tiền tệ hoặc thông tin locale.

Một thay đổi dễ nhận thấy là chuỗi ngày, số hoặc tiền tệ có thể khác giữa JDK 8 và JDK 9+, dù mã nguồn không đổi. Ngay cả `printf()` cũng có thể dùng quy tắc locale nếu không chỉ định locale rõ ràng.

CLDR là nguồn dữ liệu cho các dịch vụ locale của JDK. Nó không tự dịch các thông báo riêng của ứng dụng; nội dung giao diện như nút, thông báo lỗi và mô tả sản phẩm vẫn cần được quản lý bằng tài nguyên dịch của ứng dụng.

## 3. Locale là yêu cầu, CLDR là dữ liệu

Một đối tượng **Locale** biểu diễn định danh ngôn ngữ và khu vực. Nó không chứa toàn bộ quy tắc định dạng. API nhận Locale sẽ sử dụng dữ liệu phù hợp từ provider mà runtime chọn.

Tạo Locale theo BCP 47 language tag:

`````````java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale englishUS = Locale.forLanguageTag("en-US");
Locale frenchCanada = Locale.forLanguageTag("fr-CA");
`````````

Có thể dùng các hằng số có sẵn khi phù hợp:

`````````java
Locale us = Locale.US;
Locale uk = Locale.UK;
Locale germany = Locale.GERMANY;
`````````

Một Locale có thể chứa language, script, region, variant và extension. Ví dụ `zh-Hant-TW` xác định tiếng Trung với chữ phồn thể tại Đài Loan. Việc chỉ dùng ngôn ngữ mà bỏ qua script hoặc region có thể khiến chương trình chọn quy ước không đúng mong muốn.

Không nên mặc định rằng mọi API đều hỗ trợ chính xác cùng một tập Locale. Việc hỗ trợ phụ thuộc dịch vụ locale cụ thể và provider đang có. Khi cần kiểm soát, hãy kiểm thử đúng API và Locale mà ứng dụng sử dụng.

## 4. Các locale provider hiện hành

JDK reference implementation cung cấp ba nguồn dữ liệu locale chính:

| Provider | Vai trò |
|---|---|
| `CLDR` | Dữ liệu từ Unicode Common Locale Data Repository |
| `HOST` | Thiết lập tùy chỉnh của hệ điều hành hiện tại |
| `SPI` | Các dịch vụ locale do ứng dụng hoặc thư viện cài đặt qua Service Provider Interface |

Mặc định hiện hành tương đương:

`````````bash
java -Djava.locale.providers=CLDR MyApplication
`````````

Nếu không đặt `java.locale.providers`, runtime mặc định dùng `CLDR`. Vì đây là lựa chọn mặc định, thông thường không cần thêm thuộc tính này.

Có thể thay đổi thứ tự ưu tiên provider. Ví dụ, nếu ứng dụng cài đặt một locale service provider riêng và muốn thử provider đó trước CLDR:

`````````bash
java -Djava.locale.providers=SPI,CLDR MyApplication
`````````

Runtime tìm dữ liệu theo thứ tự đã khai báo. Nếu provider trước không cung cấp dịch vụ hoặc Locale cần thiết, việc tìm kiếm tiếp tục với provider sau.

`HOST` có thể được dùng khi muốn lấy tùy chỉnh locale từ hệ điều hành:

`````````bash
java -Djava.locale.providers=HOST,CLDR MyApplication
`````````

Khả năng hỗ trợ `HOST` phụ thuộc JDK implementation. Provider này làm việc với default locale của người dùng và chủ yếu áp dụng cho định dạng ngày giờ, số và tiền tệ. Nó không có nghĩa mọi Locale mà ứng dụng truyền vào đều được thay bằng cấu hình hệ điều hành.

## 5. Cấu hình provider đúng thời điểm

Thuộc tính `java.locale.providers` được đọc và cache khi `LocaleServiceProvider` được khởi tạo. Vì vậy, hãy đặt nó ngay trên lệnh khởi chạy JVM:

`````````bash
java -Djava.locale.providers=SPI,CLDR -jar application.jar
`````````

Không nên đợi ứng dụng chạy rồi gọi:

`````````java
System.setProperty("java.locale.providers", "SPI,CLDR");
`````````

Việc đổi system property sau khi các lớp locale service đã khởi tạo có thể không làm thay đổi thứ tự provider đang dùng.

Nếu ứng dụng chạy trong container hoặc service manager, hãy đặt thuộc tính ở cấu hình khởi chạy tương ứng, sau đó kiểm tra cấu hình thực tế trong môi trường triển khai. Không dựa vào cấu hình terminal phát triển để suy ra cấu hình của tiến trình production.

## 6. Tạo locale service provider riêng bằng SPI

Khi CLDR và HOST không cung cấp quy tắc cần thiết, ứng dụng có thể triển khai một **Locale Service Provider**. Java có các SPI tương ứng với dịch vụ locale, chẳng hạn:

- `DateFormatProvider`.
- `NumberFormatProvider`.
- `DateFormatSymbolsProvider`.
- `CurrencyNameProvider`.
- `LocaleNameProvider`.
- `CollatorProvider`.

Provider phải khai báo các Locale được hỗ trợ và triển khai đúng service tương ứng. Với module, khai báo dịch vụ bằng directive `provides`. Với class path, dùng tệp cấu hình trong `META-INF/services`.

Ví dụ về cấu hình provider trong `module-info.java`:

`````````java
module com.example.locale {
    provides java.text.spi.DateFormatProvider
        with com.example.locale.CustomDateFormatProvider;
}
`````````

Sau khi triển khai và đóng gói provider, khởi chạy ứng dụng với SPI đứng trước CLDR:

`````````bash
java -Djava.locale.providers=SPI,CLDR -jar application.jar
`````````

JDK cần nhìn thấy provider thông qua system class loader theo quy tắc triển khai SPI. Hãy kiểm tra đúng module path hoặc class path và xác nhận provider hỗ trợ Locale mà ứng dụng yêu cầu.

Không cần viết provider riêng chỉ để thay một mẫu ngày đơn giản. Nếu ứng dụng chỉ cần một định dạng cố định cho một trường dữ liệu, formatter với pattern tường minh thường dễ triển khai và kiểm thử hơn.

## 7. Dữ liệu CLDR thay đổi theo phiên bản JDK

CLDR được cập nhật theo thời gian. JDK tích hợp một phiên bản CLDR cụ thể, vì vậy kết quả localized formatting có thể thay đổi khi nâng cấp JDK.

Một số mốc phiên bản:

| JDK | Phiên bản CLDR |
|---|---|
| JDK 9 | 29 |
| JDK 17 | 39 |
| JDK 23 | 45 |
| JDK 24 | 46 |
| JDK 25 | 47 |
| JDK 26 | 48 |

Đây là lý do không nên dùng chuỗi đã format theo locale làm định dạng lưu trữ hoặc giao thức trao đổi giữa các hệ thống. Ví dụ, nếu một dịch vụ gửi ngày theo chuỗi hiển thị của `DateTimeFormatter.ofLocalizedDate()`, hệ thống nhận có thể dùng phiên bản CLDR hoặc Locale khác và không parse được chuỗi đó.

Nên phân biệt:

- **Hiển thị cho người dùng**: dùng localized formatter và Locale rõ ràng.
- **Lưu trữ hoặc truyền dữ liệu**: dùng định dạng ổn định như ISO-8601, mã tiền tệ ISO hoặc kiểu dữ liệu số/ngày có cấu trúc.
- **Kiểm thử**: không giả định mọi JDK sẽ luôn tạo cùng một chuỗi localized nếu dữ liệu CLDR có thể được cập nhật.

JDK 23 đã loại bỏ dữ liệu locale legacy `COMPAT`/`JRE`. Vì vậy, không dựa vào các giá trị provider cũ này để cấu hình ứng dụng hiện đại. Nếu cần giữ một mẫu hiển thị đặc thù vì yêu cầu nghiệp vụ, hãy dùng pattern tường minh hoặc triển khai locale service provider phù hợp.

## 8. Sử dụng Locale tường minh trong các API định dạng

### Định dạng số

Dùng `NumberFormat` với Locale cụ thể:

`````````java
NumberFormat germanNumbers =
        NumberFormat.getNumberInstance(Locale.GERMANY);

String text = germanNumbers.format(1234567.89);
System.out.println(text);
`````````

Không dựa vào Locale mặc định của máy nếu kết quả cần nhất quán giữa các môi trường. Một máy chủ có default locale `en-US` và một máy khác có `de-DE` có thể tạo chuỗi khác nhau nếu chương trình gọi factory method không truyền Locale.

### Định dạng tiền tệ

Dùng `NumberFormat.getCurrencyInstance(locale)` để định dạng theo quy ước của Locale:

`````````java
NumberFormat usCurrency =
        NumberFormat.getCurrencyInstance(Locale.US);

System.out.println(usCurrency.format(1234.56));
`````````

Nếu cần lưu trữ tiền, hãy lưu giá trị số cùng mã tiền tệ, chẳng hạn `BigDecimal` và `USD`. Không lưu chuỗi `$1,234.56` làm dữ liệu tài chính chuẩn vì ký hiệu, vị trí và dấu phân cách phụ thuộc locale.

### Định dạng ngày bằng java.time

Với ngày hiển thị theo quy ước của người dùng:

`````````java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(Locale.UK);

String dateText =
        formatter.format(LocalDate.of(2024, 3, 19));
`````````

Với dữ liệu trao đổi giữa các hệ thống, dùng formatter ISO:

`````````java
String wireDate =
        DateTimeFormatter.ISO_LOCAL_DATE
                .format(LocalDate.of(2024, 3, 19));
`````````

ISO format không phụ thuộc cách CLDR chọn mẫu ngày hiển thị cho một Locale.

### Phân biệt default locale

Java có default locale cho các API không nhận Locale tường minh:

`````````java
Locale current = Locale.getDefault();
Locale formatLocale = Locale.getDefault(Locale.Category.FORMAT);
Locale displayLocale = Locale.getDefault(Locale.Category.DISPLAY);
`````````

`FORMAT` thường dùng cho ngày, số và tiền tệ; `DISPLAY` dùng cho tên hiển thị của ngôn ngữ, quốc gia và các thành phần locale. Có thể truyền Locale tường minh để tránh kết quả phụ thuộc môi trường chạy.

`Locale.setDefault()` thay đổi trạng thái mặc định của JVM và có thể ảnh hưởng các thành phần khác. Chỉ thay đổi khi ứng dụng thật sự muốn điều chỉnh default locale ở phạm vi đó; thông thường nên truyền Locale trực tiếp vào API.

## 9. CLDR không thay thế ResourceBundle của ứng dụng

CLDR cung cấp quy tắc locale dùng chung, ví dụ cách hiển thị ngày, số, tiền tệ và tên ngôn ngữ. Nó không chứa toàn bộ bản dịch riêng của từng ứng dụng.

Dùng `ResourceBundle` để quản lý thông báo do ứng dụng sở hữu:

`````````java
ResourceBundle messages =
        ResourceBundle.getBundle("messages", Locale.forLanguageTag("vi-VN"));

String greeting = messages.getString("greeting");
`````````

Ví dụ, ứng dụng có thể đóng gói `messages_vi_VN.properties` chứa bản dịch tiếng Việt của thông báo `greeting`. Dữ liệu CLDR không tự sinh ra nội dung đó.

Khi xây dựng ứng dụng đa ngôn ngữ, hãy kết hợp:

- `Locale` để xác định ngôn ngữ/khu vực.
- CLDR hoặc provider phù hợp để định dạng dữ liệu theo quy ước locale.
- `ResourceBundle` hoặc hệ thống dịch riêng để quản lý nội dung giao diện.
- `DateTimeFormatter`/`NumberFormat` để hiển thị ngày, số và tiền tệ.

## 10. Ví dụ Java hoàn chỉnh

Chương trình sau minh họa cùng một giá trị được định dạng theo ba Locale khác nhau. Ví dụ dùng Locale tường minh, không phụ thuộc default locale của máy.

Tạo tệp **CldrLocaleDemo.java**:

`````````java
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;

public class CldrLocaleDemo {
    public static void main(String[] args) {
        Locale germany = Locale.GERMANY;
        Locale unitedStates = Locale.US;
        Locale unitedKingdom = Locale.UK;

        NumberFormat germanNumber =
                NumberFormat.getNumberInstance(germany);
        NumberFormat usCurrency =
                NumberFormat.getCurrencyInstance(unitedStates);
        DateTimeFormatter ukDate =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                        .withLocale(unitedKingdom);

        System.out.println("java.version="
                + Runtime.version().feature());
        System.out.println("java.locale.providers="
                + System.getProperty(
                        "java.locale.providers", "<default: CLDR>"));
        System.out.println("Germany number="
                + germanNumber.format(1234567.89));
        System.out.println("US currency="
                + usCurrency.format(1234.56));
        System.out.println("UK medium date="
                + ukDate.format(LocalDate.of(2024, 3, 19)));
        System.out.println("US currency code="
                + Currency.getInstance(unitedStates).getCurrencyCode());
    }
}
`````````

Biên dịch và chạy trên Java 17+:

`````````bash
javac --release 17 -Xlint:all CldrLocaleDemo.java
java CldrLocaleDemo
`````````

Stdout quan sát được trên OpenJDK 24:

`````````text
java.version=24
java.locale.providers=<default: CLDR>
Germany number=1.234.567,89
US currency=$1,234.56
UK medium date=19 Mar 2024
US currency code=USD
`````````

Nếu muốn chỉ định CLDR rõ ràng trong cấu hình chạy:

`````````bash
java -Djava.locale.providers=CLDR CldrLocaleDemo
`````````

Kết quả của ví dụ cho thấy Locale quyết định quy ước hiển thị mà API sử dụng. Chuỗi localized là dữ liệu trình bày; hãy lưu ngày, số và tiền tệ dưới dạng dữ liệu có cấu trúc để tránh phụ thuộc phiên bản CLDR.

## 11. Lỗi thường gặp và cách tránh

1. **Cho rằng Locale chứa sẵn toàn bộ quy tắc định dạng**: Locale chỉ định danh ngôn ngữ/khu vực; provider cung cấp dữ liệu cho API locale-sensitive.
2. **Dùng default locale ở mọi môi trường**: truyền Locale tường minh khi kết quả phải ổn định theo khu vực nghiệp vụ.
3. **Nhầm CLDR với bản dịch ứng dụng**: dùng ResourceBundle hoặc hệ thống dịch riêng cho nội dung giao diện.
4. **Lưu chuỗi ngày hoặc tiền tệ đã format**: lưu kiểu dữ liệu chuẩn và chỉ format ở lớp hiển thị.
5. **Giả định JDK mới luôn tạo cùng chuỗi localized**: dữ liệu CLDR được cập nhật; kiểm thử khi nâng cấp JDK.
6. **Đổi java.locale.providers sau khi runtime khởi tạo**: đặt thuộc tính trên command line trước khi locale service được khởi tạo.
7. **Cấu hình SPI nhưng không triển khai provider**: provider phải được đóng gói và nhìn thấy qua module path hoặc class path đúng cách.
8. **Giả định HOST có trên mọi JDK**: khả năng hỗ trợ phụ thuộc implementation và chỉ áp dụng cho một số định dạng của default locale.
9. **Dùng dữ liệu locale để suy ra tỷ giá**: CLDR cung cấp ký hiệu/tên tiền tệ, không cung cấp tỷ giá quy đổi.
10. **Dùng COMPAT/JRE trên JDK hiện hành**: dữ liệu locale legacy này đã bị loại bỏ từ JDK 23; chọn CLDR hoặc provider hiện hành.
11. **Nhầm tên múi giờ với quy tắc chuyển giờ**: CLDR có tên hiển thị theo locale; quy tắc múi giờ thực tế được quản lý bởi dữ liệu time-zone riêng của JDK.
12. **Kiểm thử chuỗi localized bằng một môi trường duy nhất**: kiểm thử trên các JDK/Locale cần hỗ trợ và dùng ISO hoặc pattern tường minh cho dữ liệu có hợp đồng ổn định.

## Kết luận

Từ Java 9, CLDR là nguồn dữ liệu locale mặc định của Java. Nó giúp các API định dạng ngày giờ, số, tiền tệ và tên ngôn ngữ tuân theo quy ước của từng khu vực. JDK hiện hành cung cấp các provider CLDR, HOST và SPI; thứ tự lựa chọn được điều khiển bằng `java.locale.providers` khi khởi chạy JVM.

Hãy truyền Locale tường minh cho thao tác định dạng, dùng ResourceBundle cho bản dịch riêng của ứng dụng, kiểm thử khi nâng cấp JDK và dùng định dạng chuẩn cho dữ liệu lưu trữ hoặc trao đổi. Cách này giữ trải nghiệm hiển thị phù hợp locale mà không làm dữ liệu nghiệp vụ phụ thuộc vào thay đổi của CLDR.

## Nguồn tham khảo

- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252)
- [JDK 26 Internationalization Overview — CLDR Locale Data Enabled by Default](https://docs.oracle.com/en/java/javase/26/intl/internationalization-overview.html)
- [JDK 26 LocaleServiceProvider API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleServiceProvider.html)
- [JDK 26 Migration Guide — Changes to Locale Data](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html)
