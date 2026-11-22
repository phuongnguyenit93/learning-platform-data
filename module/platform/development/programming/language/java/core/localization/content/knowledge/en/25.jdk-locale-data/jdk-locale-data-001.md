# CLDR và vai trò cung cấp quy ước bản địa hóa cho JDK

Trong ứng dụng Java đa ngôn ngữ, thay đổi `Locale` có thể làm định dạng ngày, số, đơn vị tiền, tên tháng, tên quốc gia hoặc cách trình bày thời gian thay đổi. Phần lớn những khác biệt ấy **không được suy ra từ mã ngôn ngữ bằng một vài câu lệnh `if`**. Chúng cần nguồn dữ liệu được nghiên cứu, duy trì và cập nhật cho nhiều ngôn ngữ/vùng. **Unicode CLDR — Common Locale Data Repository** — là một trong những nguồn dữ liệu nền tảng quan trọng nhất cho nhiệm vụ đó.

Trong Java, CLDR không phải một hàm `translate()` hay một đối tượng bạn trực tiếp gọi để lấy “bản dịch của cả ứng dụng”. Nó là **kho dữ liệu và quy tắc bản địa hóa**, được JDK sử dụng qua những **locale data providers** và API phù hợp. JDK 9 trở lên ưu tiên dữ liệu CLDR theo mặc định; riêng ứng dụng chạy Java 17 cần hiểu cơ chế nhà cung cấp, giới hạn phạm vi được JDK triển khai và khả năng kết quả đổi khi nâng JDK/CLDR.

Mục tiêu bài học: hiểu CLDR cung cấp gì, cách Java Core tiêu thụ dữ liệu locale, tại sao cùng `Locale` có thể cho kết quả khác giữa JDK, khi nào cần tài nguyên tự dịch hoặc thư viện chuyên dụng, và cách kiểm thử ứng dụng thay vì viết cứng mọi quy ước văn hóa.

## 1. CLDR là gì?

**CLDR (Common Locale Data Repository)** là dự án dữ liệu locale của Unicode Consortium. Nó cung cấp dữ liệu có cấu trúc và các quy tắc phục vụ **quốc tế hóa (internationalization/i18n)** và **bản địa hóa (localization/l10n)** trên nhiều ngôn ngữ, hệ chữ và vùng địa lý.

Những ví dụ điển hình về dữ liệu/quy ước CLDR:

- Mẫu định dạng **ngày, tháng, giờ**, tên thứ, tên tháng, các khoảng thời gian và tên vùng giờ theo ngôn ngữ.
- Ký hiệu **dấu thập phân**, phân nhóm chữ số, cách hiển thị số và đơn vị tiền.
- Tên hiển thị của **ngôn ngữ, hệ chữ, quốc gia/vùng, tiền tệ**.
- Thông tin về **tuần đầu năm, ngày đầu tuần**, quy ước hệ lịch và lựa chọn regional preferences.
- Quy tắc **plural/cardinal/ordinal** cho nhiều ngôn ngữ, dùng để lựa chọn hình thức thông điệp.
- Các dữ liệu và quy tắc khác trong hệ sinh thái CLDR về **collation, segmentation, unit formatting, numbering systems** và tương tác ngôn ngữ.

Đây là **danh sách phạm vi của dự án CLDR**, không phải lời cam kết JDK 17 đã đưa toàn bộ dữ liệu và mọi thuật toán CLDR ra thành API Java chuẩn. Những lớp hoặc chức năng cụ thể phải được kiểm tra theo phiên bản Java và nhà cung cấp locale đang hoạt động.

CLDR còn có các tài liệu đặc tả, đặc biệt **UTS #35 / LDML** (Locale Data Markup Language), mô tả cấu trúc dữ liệu và các quy tắc sử dụng. Dữ liệu CLDR do cộng đồng/chuyên gia ngôn ngữ và nhiều tổ chức đóng góp, được kiểm tra và phát hành theo phiên bản. Chính vì thế **quy ước hiển thị không nhất thiết bất biến theo thời gian**.

### Một ví dụ đơn giản

Cùng số `1234.5`, một ứng dụng thường hiển thị khác nhau tùy locale:

~~~text
en-US → 1,234.5
de-DE → 1.234,5
~~~

Dấu phân tách nghìn và dấu thập phân **đổi vai trò**. Đó là minh họa về **quy ước trình bày**, không phải đổi giá trị số. `1234.5` vẫn là cùng một lượng số học.

Tương tự, cùng ngày lịch `2024-06-16` có thể hiển thị theo thứ tự tháng/ngày/năm hoặc ngày/tháng/năm. Ứng dụng không nên đồng nhất chuỗi đã bản địa hóa với dữ liệu ngày nguồn dùng cho máy.

## 2. CLDR không đồng nghĩa với Locale, ResourceBundle hoặc ứng dụng dịch

Bốn khái niệm có vai trò khác nhau:

| Khái niệm | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| `Locale` | Định danh ngôn ngữ, vùng, script và tùy chọn locale | `Locale.forLanguageTag("vi-VN")` |
| CLDR | Dữ liệu/quy tắc bản địa hóa chung để phần mềm áp dụng | Dấu thập phân, mẫu ngày, tên tháng |
| API định dạng Java | Tiêu thụ dữ liệu locale qua provider để format/parse | `NumberFormat`, `DateTimeFormatter` |
| `ResourceBundle` của ứng dụng | Lưu thông điệp, nhãn và nội dung do nhóm sản phẩm dịch | `login.button=Đăng nhập` |

**Có `Locale` chưa đủ để có nội dung đã được dịch.** Mã `"vi-VN"` chỉ yêu cầu ngữ cảnh tiếng Việt/vùng Việt Nam; JDK không biết chức năng “Thanh toán ngay” của một dự án phải dịch thế nào. `ResourceBundle` chứa nội dung ứng dụng; CLDR chủ yếu là nguồn quy ước và dữ liệu dùng chung.

**CLDR không phải Google Translate hoặc dịch máy.** Nó có thể chứa tên hiển thị của quốc gia, đơn vị tiền, tháng hay một số danh mục dữ liệu chung nhưng không có nghĩa toàn bộ mô tả sản phẩm, email, thông báo lỗi và đoạn hội thoại của dự án đã được tự dịch.

**CLDR cũng không phải timezone database duy nhất.** Tính offset và quy tắc chuyển giờ của vùng theo thời gian là trách nhiệm riêng của dữ liệu timezone/`ZoneRules` (thường dựa trên tzdb). CLDR có thể cung cấp **tên vùng giờ được bản địa hóa** hoặc một số quy ước trình bày vùng giờ; nó không tự xác định `ZoneId` hiện tại của người dùng.

### Ba bước khi format dữ liệu

~~~text
Giá trị nghiệp vụ
        +
Locale người dùng
        +
Dữ liệu locale do provider JDK cung cấp
        ↓
API NumberFormat / DateTimeFormatter / ...
        ↓
Chuỗi hiển thị cho người đọc
~~~

Ví dụ `NumberFormat.getNumberInstance(Locale.GERMANY)` lấy một formatter có hành vi phù hợp locale theo dữ liệu/provider hiện hành, không thay đổi giá trị nguồn. Khi hiển thị số USD cho người dùng ở Đức, phải xác định **currency giao dịch** riêng với locale trình bày.

## 3. JDK dùng CLDR từ khi nào?

Một số mốc lịch sử cần biết:

1. **JDK 8** có đưa dữ liệu CLDR vào runtime, nhưng không đặt CLDR làm nguồn ưu tiên mặc định.
2. **Từ JDK 9**, theo **JEP 252 — Use CLDR Locale Data by Default**, CLDR được ưu tiên mặc định cho nhiều locale-sensitive services.
3. **JDK 17** sử dụng CLDR mặc định và vẫn có nhà cung cấp dữ liệu cũ **`COMPAT`** để hỗ trợ chuyển đổi từ hành vi trước JDK 9.
4. **Từ JDK 23**, dữ liệu locale cũ `COMPAT`/`JRE` đã bị loại bỏ; cấu hình này không còn khôi phục được kết quả cũ như trên JDK 17.

Riêng theo tài liệu **Oracle JDK 17 Supported Locales**, nhà cung cấp CLDR trong Oracle JDK 17 dựa trên **CLDR release 39**. Không vì dự án Unicode CLDR có bản phát hành mới mà suy ra một JDK 17 đang chạy đã có dữ liệu CLDR mới tương đương. Phải kiểm tra runtime thực và bản cập nhật được sử dụng.

Khi một hệ thống được nâng từ Java 8 sang Java 17, định dạng số/ngày/tiền có thể đổi **dù logic nghiệp vụ không sửa**. Khi nâng từ Java 17 sang Java 23+, không thể dựa vào `COMPAT` như giải pháp lâu dài. Cần kế hoạch kiểm thử và di trú thay vì kỳ vọng tất cả chuỗi giao diện bất biến.

### “Mặc định dùng CLDR” không có nghĩa mọi API dùng CLDR

Điểm dễ nhầm: **dự án CLDR** có rất nhiều bộ dữ liệu, nhưng **phạm vi JDK tích hợp** không bao gồm mọi loại. Theo tài liệu Oracle JDK 17, dữ liệu CLDR của nhà cung cấp JDK 17 **không được áp dụng cho `BreakIterator` và `Collator`** theo cách các dữ liệu định dạng ngày/số được áp dụng.

Do đó tránh phát biểu rằng “Java 17 dùng CLDR nên mọi quy tắc phân từ, sắp xếp theo ngôn ngữ hoặc plural CLDR đều đã có sẵn trong Java Core”. Một ứng dụng cần thuật toán/độ bao phủ cụ thể phải kiểm tra API Java, bộ dữ liệu và thư viện chuyên môn của mình.

## 4. Locale data provider là gì?

Nhiều dịch vụ Java nhạy cảm với locale được cung cấp thông qua cơ chế **locale service providers**. Chúng có thể đến từ dữ liệu tích hợp JDK, hệ điều hành hoặc triển khai riêng, tùy runtime.

Trong **JDK 17**, các nhãn provider quan trọng gồm:

| Provider | Vai trò trong JDK 17 |
| --- | --- |
| `CLDR` | Dịch vụ dùng dữ liệu Unicode CLDR mà JDK tích hợp |
| `COMPAT` | Bộ dữ liệu tương thích với nhiều hành vi trước JDK 9 |
| `JRE` | Bí danh cũ của `COMPAT` trong phiên bản hỗ trợ, đã được đánh dấu sẽ loại bỏ |
| `SPI` | Các locale service provider do ứng dụng/thư viện bên ngoài hiện thực |
| `HOST` | Tham chiếu tùy chỉnh locale của hệ điều hành khi được hỗ trợ; không phải mọi nền tảng đều cung cấp |

Phạm vi mà một nhà cung cấp hỗ trợ có thể khác theo **dịch vụ**, **locale**, runtime và hệ điều hành. Không phải cứ có locale `fr-FR` là mọi API i18n đều tìm được dữ liệu cùng provider và cùng mức độ đầy đủ.

### java.locale.providers

JDK hỗ trợ cấu hình thứ tự tìm nguồn locale bằng system property **`java.locale.providers`**.

Ví dụ chạy **trên JDK 17**:

~~~bash
java -Djava.locale.providers=CLDR,COMPAT CldrJdkLocaleDemo
java -Djava.locale.providers=COMPAT,CLDR CldrJdkLocaleDemo
~~~

Với các dịch vụ locale phù hợp, provider được tra theo thứ tự cấu hình; khi một provider không đáp ứng dữ liệu dịch vụ/locale được yêu cầu, runtime có thể xem provider tiếp theo. Trong Oracle JDK 17, thứ tự mặc định về hành vi được tài liệu mô tả tương đương ưu tiên `CLDR,COMPAT`.

**Quan trọng:**

- Đặt property **khi khởi động JVM**; theo hợp đồng `LocaleServiceProvider` Java 17, thứ tự này được đọc ở startup. Gọi `System.setProperty("java.locale.providers", "...")` sau khi ứng dụng chạy **không đổi lại thứ tự provider đang dùng**.
- `COMPAT` chỉ là lựa chọn chuyển tiếp phù hợp một số JDK cũ. **Từ JDK 23**, dữ liệu `COMPAT/JRE` đã bị loại bỏ; không giới thiệu nó như giải pháp tương thích dùng vĩnh viễn.
- `SPI` muốn được dùng phải có provider cài đặt/đăng ký phù hợp và được chọn theo cơ chế provider của runtime. Đặt `SPI` trong property **không tự tạo** dữ liệu dịch thuật cho ứng dụng.
- `HOST` có thể không có trên một hệ điều hành/runtime hoặc chỉ phản ánh một số thiết lập của người dùng hệ điều hành, chứ không phải locale của mọi khách hàng trong ứng dụng web.
- Việc đổi provider có thể đổi pattern, dấu phân tách, tên tháng hoặc một số cách parse. Không dựa vào một output ngẫu nhiên để quyết định “đúng tuyệt đối” cho mọi JDK.

### Nhà cung cấp nào thật sự phục vụ một cuộc gọi?

`Locale` không chứa thuộc tính kiểu “bản ghi này được phục vụ bởi CLDR version X”. Không phải API định dạng tiêu chuẩn nào cũng cho bạn một phương thức lấy trực tiếp tên provider đã được chọn cho lần gọi đó.

Để debug, xác nhận **phiên bản JDK/runtime**, startup property, locale yêu cầu, mô-đun locale data được đóng gói, và output trong môi trường đó. Kiểm thử với hai cấu hình provider trên **cùng bản JDK hỗ trợ** có thể giúp xác định sự khác biệt, nhưng cần tránh phỏng đoán dữ liệu nào đã được dùng chỉ từ một dấu thập phân.

## 5. CLDR giúp định dạng số như thế nào?

`java.text.NumberFormat` là một API Java để format/parse số theo locale. Một giá trị số nhất quán có thể được trình bày với dấu phân nhóm và thập phân khác nhau:

~~~java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);

String a = us.format(new BigDecimal("1234.5"));
String b = de.format(new BigDecimal("1234.5"));
~~~

Đây là **đoạn mã minh họa** với import `java.text.NumberFormat`, `java.math.BigDecimal` và `java.util.Locale`. Trên nhiều JDK/provider phổ biến:

~~~text
en-US: 1,234.5
de-DE: 1.234,5
~~~

Nhưng ứng dụng không nên lấy hai chuỗi đó làm hợp đồng byte-for-byte bất biến trên mọi bản JDK. CLDR dữ liệu và provider có thể cập nhật. Nếu dữ liệu là đầu ra giữa hai máy, nên dùng hợp đồng số machine-readable có quy tắc riêng, không lấy chuỗi đã bản địa hóa làm dữ liệu tính toán.

### Parse theo locale cần kỷ luật

Một chuỗi như `1,234` có thể được hiểu khác theo locale: dấu `,` có thể là phân tách hàng nghìn hoặc dấu thập phân. Do đó:

- Nếu số đến từ **UI** của người dùng, parse theo locale nhập liệu đã chọn và kiểm tra đã tiêu thụ toàn bộ chuỗi.
- Nếu số đến từ **API/CSV máy**, xác định format giao thức ổn định, tránh tự động parse bằng locale máy chủ.
- Với tiền tệ, phải giữ **currency** và **quy tắc làm tròn** riêng: CLDR cung cấp quy ước hiển thị, không quyết định luật thuế, bước làm tròn tiền mặt hoặc độ chính xác thanh toán của hệ thống.

`NumberFormat` còn có trạng thái cấu hình có thể thay đổi; không chia sẻ một instance mutable tùy tiện giữa các luồng. Nếu cần formatter trong ứng dụng nhiều request, nên tạo riêng hoặc kiểm soát truy cập/cấu hình đúng cách.

## 6. CLDR giúp trình bày ngày giờ như thế nào?

`DateTimeFormatter` của `java.time` có các factory bản địa hóa như:

~~~java
DateTimeFormatter formatter = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.SHORT)
        .withLocale(Locale.GERMANY);

String shown = LocalDate.of(2024, 6, 16).format(formatter);
~~~

Đây là **đoạn minh họa Java 17** cần import `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.time.format.FormatStyle`, `java.util.Locale`.

Với `ofLocalizedDate(FormatStyle.SHORT)`, **style** được yêu cầu và **locale** quyết định mẫu định dạng cụ thể qua dữ liệu runtime. Không lấy một pattern ngày của một quốc gia rồi áp cho tất cả.

`DateTimeFormatter.ofPattern("uuuu-MM-dd", locale)` lại là trường hợp khác: developer **chọn pattern cụ thể**, và phần literal/định dạng được xác định bởi pattern. Nó có thể phù hợp với một giao thức hay bản in yêu cầu thứ tự xác định, nhưng không phải cách để mỗi quốc gia tùy quyết định thứ tự trường.

### Date locale khác timezone

CLDR có thể giúp tên tháng/thứ hoặc cách trình bày ngày, nhưng timezone phải được chọn theo **sự kiện/người dùng**:

~~~java
Instant instant = Instant.parse("2024-06-16T12:00:00Z");
ZonedDateTime event = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Đây là đoạn minh họa, cần import `java.time.*`. Mã `Locale.US` không suy ra `America/New_York`; một quốc gia có thể có nhiều timezone và người dùng có thể chọn ngôn ngữ khác nơi ở.

CLDR cung cấp một số dữ liệu **tên vùng giờ được bản địa hóa**, trong khi quy tắc offset lịch sử/DST là vấn đề của timezone rule provider. Khi cần xác định thời điểm thực, ưu tiên `Instant` và `ZoneId` theo ý nghĩa nghiệp vụ.

## 7. Tiền tệ, tên vùng và dữ liệu ngôn ngữ

Các API liên quan:

- `Currency.getInstance("USD")` cho biết đối tượng currency theo mã; `getCurrencyCode()` trả về định danh `USD`.
- `Currency.getSymbol(locale)` và `getDisplayName(locale)` lấy **chuỗi trình bày** tùy locale/dữ liệu hỗ trợ.
- `Locale.getDisplayCountry(displayLocale)`, `getDisplayLanguage(displayLocale)` và tương tự giúp hiển thị tên quốc gia/ngôn ngữ theo locale mong muốn.
- `NumberFormat.getCurrencyInstance(locale)` tạo formatter tiền theo quy ước locale.

Ví dụ:

~~~java
Currency usd = Currency.getInstance("USD");

String code = usd.getCurrencyCode();       // "USD"
String symbol = usd.getSymbol(Locale.US); // phụ thuộc locale/runtime
~~~

Đây là đoạn minh họa với import `java.util.Currency`, `java.util.Locale`.

**Không nhầm symbol với currency code.** `$` có thể là ký hiệu của nhiều đơn vị tiền, trong khi `USD` và `CAD` là các mã khác nhau. Không dùng symbol để lưu ID tiền.

**Không suy currency của hóa đơn từ locale UI.** Một người dùng hiển thị giao diện tiếng Việt vẫn có thể thanh toán bằng USD. Hệ thống phải lưu đơn vị tiền tệ thực tế; locale quyết định cách hiển thị chứ không tự quy đổi.

**Không nhầm thông tin CLDR với quy định tài chính.** Dữ liệu currency có thể có thông tin chữ số thập phân thường dùng, nhưng quy tắc làm tròn khoản thanh toán, thuế, phí hoặc tỷ giá là quyết định nghiệp vụ/pháp lý riêng.

## 8. Ví dụ Java 17 chạy độc lập

Chương trình minh họa rằng **cùng một giá trị số và ngày** có thể có cách trình bày khác nhau theo hai locale; đổi locale không làm đổi giá trị gốc. Nó chủ động in **các bất biến dạng boolean** thay vì đóng đinh một chuỗi ngày/số phụ thuộc CLDR/provider. Vì vậy ví dụ nhấn mạnh hành vi API, dễ kiểm thử và ít phụ thuộc khác biệt ký tự khoảng trắng hoặc cách trình bày của từng JDK.

Tạo tệp **`CldrJdkLocaleDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;

public class CldrJdkLocaleDemo {
    public static void main(String[] args) {
        Locale us = Locale.US;
        Locale de = Locale.GERMANY;
        BigDecimal number = new BigDecimal("1234.5");

        NumberFormat usNumber = NumberFormat.getNumberInstance(us);
        NumberFormat deNumber = NumberFormat.getNumberInstance(de);
        String usText = usNumber.format(number);
        String deText = deNumber.format(number);

        System.out.println("US locale: " + us.toLanguageTag());
        System.out.println("DE locale: " + de.toLanguageTag());
        System.out.println("Number formats differ: "
                + !usText.equals(deText));

        LocalDate date = LocalDate.of(2024, 6, 16);
        String dateUS = date.format(DateTimeFormatter
                .ofLocalizedDate(FormatStyle.SHORT).withLocale(us));
        String dateDE = date.format(DateTimeFormatter
                .ofLocalizedDate(FormatStyle.SHORT).withLocale(de));

        System.out.println("Date formats differ: "
                + !dateUS.equals(dateDE));

        NumberFormat usdUS = NumberFormat.getCurrencyInstance(us);
        usdUS.setCurrency(Currency.getInstance("USD"));
        NumberFormat usdDE = NumberFormat.getCurrencyInstance(de);
        usdDE.setCurrency(Currency.getInstance("USD"));

        System.out.println("Currency display differs: "
                + !usdUS.format(number).equals(usdDE.format(number)));

        System.out.println("Machine date: "
                + date.format(DateTimeFormatter.ISO_LOCAL_DATE));
        System.out.println("Same underlying number: "
                + (number.compareTo(new BigDecimal("1234.50")) == 0));
        System.out.println("USD code: "
                + Currency.getInstance("USD").getCurrencyCode());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 CldrJdkLocaleDemo.java
java CldrJdkLocaleDemo
~~~

Kết quả quan sát với môi trường JDK/locale data đã kiểm thử:

~~~text
US locale: en-US
DE locale: de-DE
Number formats differ: true
Date formats differ: true
Currency display differs: true
Machine date: 2024-06-16
Same underlying number: true
USD code: USD
~~~

**Giải thích từng dòng:**

1. Hai tag `en-US` và `de-DE` xác định ngữ cảnh hiển thị được yêu cầu.
2. `Number formats differ: true` cho thấy cùng số `1234.5` có thể được format khác nhau theo locale.
3. `Date formats differ: true` thể hiện mẫu ngày `SHORT` có thể đổi theo locale. Các chuỗi thực tế còn có thể chịu tác động của phiên bản data/provider.
4. `Currency display differs: true` minh họa cùng mã tiền `USD` có thể được biểu diễn khác nhau khi locale khác.
5. `Machine date` là một chuỗi theo `ISO_LOCAL_DATE`, phù hợp cho biểu diễn ngày theo hợp đồng máy (không phải ngày tháng có dịch tên).
6. `BigDecimal.compareTo` xác nhận `1234.5` và `1234.50` là cùng giá trị số học; việc format không sửa giá trị.
7. `Currency.getCurrencyCode()` trả `USD`; mã tiền không thay theo locale.

**Cảnh báo về tính tái lập:** Các dòng boolean so sánh **kết quả thực của một môi trường JDK có dữ liệu en-US/de-DE thông thường**. Chúng là ví dụ kiểm thử, không phải quy định rằng mọi runtime tùy biến hay mọi thứ tự provider sẽ luôn trả cùng chuỗi hay luôn khác nhau. Nếu chạy trong môi trường `jlink` đã loại bỏ dữ liệu locale hoặc provider đặc thù, cần kiểm tra lại kỳ vọng. Khi muốn khám phá chính xác, có thể in riêng `usText`, `deText`, `dateUS`, `dateDE` và ghi lại version/runtime.

### Vì sao không in thẳng kết quả number/date làm output chuẩn?

CLDR là dữ liệu có phiên bản, runtime cung cấp nhà cung cấp có thứ tự ưu tiên, và nhiều định dạng có các ký tự khoảng trắng đặc biệt hoặc thay đổi về dấu phân cách. Khóa kiểm thử **giá trị đầu vào và các bất biến nghiệp vụ** nên bền hơn việc coi một snapshot theo một JDK là chân lý cho mọi phiên bản.

Tuy nhiên, snapshot UI vẫn có ích để phát hiện thay đổi trong chính ứng dụng của bạn; khi nâng JDK/CLDR, hãy xem xét snapshot bằng chuyên môn bản địa hóa thay vì tự động chấp nhận mọi khác biệt.

## 9. CLDR không tự giải quyết plural và ngữ pháp phức tạp trong Java 17

Dự án CLDR có dữ liệu về **plural categories** theo ngôn ngữ, nhưng `java.text.MessageFormat` của Java 17 **không hỗ trợ trực tiếp** cú pháp `plural`/`select` của ICU MessageFormat.

Đừng viết:

~~~text
{count, plural, one{# item} other{# items}}
~~~

rồi truyền chuỗi ấy vào `new java.text.MessageFormat(...)` Java 17 với kỳ vọng nó tự hiểu và áp plural rules của CLDR. Đây là một **pattern theo hệ cú pháp ICU**, không phải một kiểu định dạng có sẵn trong `java.text.MessageFormat` Java 17.

Java Core có `MessageFormat`, `ChoiceFormat` và `ResourceBundle` để lưu/chèn thông điệp, nhưng `ChoiceFormat` là công cụ chọn theo ngưỡng số do developer đặt, không phải plural engine cho mọi locale.

Nếu cần plural theo CLDR, ordinal, grammatical gender hoặc select lồng nhau ở nhiều ngôn ngữ, xem xét **ICU4J hoặc framework i18n** có hỗ trợ đúng dữ liệu và cú pháp, đồng thời người dịch phải cung cấp câu hoàn chỉnh đúng ngôn ngữ.

**Nguyên tắc:** CLDR có một dữ liệu/quy tắc **không đồng nghĩa** Java Core đã phơi bày tất cả thành một API Java 17 hoàn chỉnh. Kiểm tra chức năng của **lớp thật sự được dùng**, không suy từ tên dự án dữ liệu.

## 10. Dữ liệu locale không phải bản dịch nội dung ứng dụng

Ví dụ tài nguyên riêng của sản phẩm:

~~~properties
# messages_vi.properties
cart.empty=Giỏ hàng chưa có sản phẩm.
button.checkout=Thanh toán
~~~

~~~properties
# messages_en.properties
cart.empty=Your cart is empty.
button.checkout=Checkout
~~~

Các nội dung này phải do ứng dụng/người dịch cung cấp và kiểm thử. CLDR có thể cung cấp tên tháng hoặc quy ước số để các placeholder trong thông điệp được trình bày phù hợp, nhưng nó **không tự tạo bản dịch** cho `cart.empty`.

Ví dụ định dạng:

~~~java
ResourceBundle messages = ResourceBundle.getBundle(
        "messages", userLocale);
String template = messages.getString("cart.total");
String formattedNumber = NumberFormat.getNumberInstance(
        userLocale).format(total);
~~~

Đây là **đoạn minh họa không độc lập** (giả định có các biến `userLocale`, `total` và tệp bundle chứa `cart.total`). Tách hai trách nhiệm: nội dung thông điệp do ứng dụng quản lý, định dạng số do Java/locale provider xử lý. Với thông điệp có placeholders, nên dùng `MessageFormat` đúng cách, cân nhắc escaping/apostrophe và ngữ pháp theo ngôn ngữ.

### Fallback ResourceBundle khác fallback provider

`ResourceBundle.getBundle` có cơ chế tìm bundle theo locale/parent và fallback theo chính sách cụ thể của API. `java.locale.providers` lại quyết định thứ tự **nguồn dữ liệu cho locale-sensitive services**.

Hai thứ này không phải một:
- thiếu `messages_vi_VN.properties` không có nghĩa JDK đã hết dữ liệu số tiếng Việt;
- có dữ liệu CLDR cho `vi-VN` không có nghĩa ứng dụng đã dịch mọi nhãn;
- thay `java.locale.providers` không tự viết/đổi nội dung `ResourceBundle` của sản phẩm.

## 11. Một số ranh giới CLDR dễ nhầm

### Locale không suy ra tất cả sở thích cá nhân

`Locale.forLanguageTag("en-US")` không chứng minh người dùng đang ở Mỹ hay dùng USD. Người dùng có thể thích giao diện tiếng Anh nhưng cần giờ Việt Nam, thanh toán bằng EUR hoặc dùng đơn vị đo hệ mét.

CLDR ghi nhận các **quy ước thường gặp**, không nên được dùng thay cho **lựa chọn và dữ liệu giao dịch thực**. Với các lĩnh vực quan trọng, nên xác định rõ `Locale` hiển thị, `ZoneId`, `Currency`, hệ lịch, numbering system và cài đặt riêng.

### Tên locale, mã locale và dữ liệu hiển thị

`Locale.getLanguage()` trả mã ngôn ngữ, `getCountry()` trả mã vùng; chúng không tự là bản dịch tên hiển thị. Để có tên hiển thị, gọi `getDisplayLanguage(displayLocale)` hoặc `getDisplayCountry(displayLocale)`. Tên có thể thay đổi theo dữ liệu và phiên bản JDK.

### Chuẩn hóa Unicode là nhiệm vụ khác

CLDR liên quan đến quy tắc và dữ liệu bản địa hóa, nhưng Unicode normalization như `Normalizer.Form.NFC` là API xử lý **tương đương ký tự**; không phải “cài CLDR rồi mọi tên đều được Unicode-normalize”. Đừng coi CLDR, chuyển chữ hoa/thường, phiên âm, dịch thuật và Unicode normalization là một thao tác.

### Dữ liệu và thuật toán phải đi với nhau

Một bộ quy tắc plural, collation hoặc segmentation chỉ có ích nếu thư viện/API **thực thi đúng quy tắc tương ứng**, với dữ liệu/phiên bản được biết. Không dùng `String.equals` rồi gọi đó là collation theo CLDR; không dùng regex xóa dấu rồi gọi đó là Unicode normalization.

## 12. jlink và phạm vi dữ liệu locale trong runtime

Khi tạo **runtime tùy biến bằng `jlink`**, ứng dụng có thể không đóng gói toàn bộ dữ liệu locale của JDK. Trong hệ JDK module, một phần dữ liệu locale bổ sung liên quan đến module `jdk.localedata`. Vì vậy:

- Một ứng dụng chạy đúng khi dùng JDK đầy đủ có thể có kết quả/khả năng hỗ trợ locale khác khi chuyển sang custom runtime image.
- Các thành phần trong `java.base` không có nghĩa mọi locale đều còn được đóng gói.
- Cần kiểm tra danh sách module và tùy chọn build image; `--include-locales` của jlink là một cơ chế chọn locale tại thời điểm tạo image khi cấu hình tương thích.
- Không mặc định “`Locale.forLanguageTag("xx-YY")` tạo thành công” đồng nghĩa dịch vụ định dạng có đầy đủ dữ liệu của `xx-YY` trong runtime image đó.

**Đây là một vấn đề triển khai**, khác với việc source code Java đúng cú pháp. Với các ứng dụng chạy Docker/minimal JVM image, hãy thử format/parse những locale thật sự được hỗ trợ ngay trên **artifact runtime cuối cùng**, không chỉ trên máy lập trình viên.

## 13. Nâng JDK, đổi CLDR và chiến lược kiểm thử

CLDR được cập nhật theo dữ liệu và nhu cầu ngôn ngữ. JDK có phiên bản dữ liệu riêng, và việc nâng bản cập nhật lớn/nhỏ có thể làm một số kết quả bản địa hóa khác trước.

Những mục nên đưa vào quy trình kiểm thử:

1. **Ma trận locale:** các locale thật sự hỗ trợ, không chỉ mặc định của máy chủ.
2. **Ma trận dịch vụ:** số, tiền, phần trăm, ngày, giờ, tên tháng, tên vùng và parse.
3. **Các trường hợp biên:** ngày cuối tháng/năm, dấu phân nhóm/decimal, số âm, số lớn, ký tự Unicode đặc biệt.
4. **Provider/version:** ghi nhận JDK vendor, version, các property startup và runtime image modules.
5. **Tài nguyên ứng dụng:** kiểm tra key bản dịch và biến placeholder riêng với dữ liệu định dạng của JDK.
6. **Output người dùng:** so sánh hiển thị trước/sau nâng cấp, đánh giá với người am hiểu locale.
7. **Giao thức máy:** bảo đảm dữ liệu API/database không dựa vào định dạng hiển thị phụ thuộc CLDR.
8. **Độ chính xác tiền tệ:** `BigDecimal`, Currency code, rounding policy không được thay bằng một chuỗi số format theo UI.
9. **Timezone:** kiểm thử `ZoneId`/DST riêng; không lấy thay đổi tên vùng giờ làm bằng chứng offset đổi.
10. **Custom runtime:** kiểm tra lại locale thực tế khi thay build `jlink`/container.
11. **Legacy provider:** nếu còn startup `COMPAT` trên Java 17/21/22, lập kế hoạch chuyển sang CLDR thay vì dựa vào cấu hình đã bị xóa từ JDK 23.

### Snapshot tests: cách dùng có trách nhiệm

Một test kỳ vọng chuỗi hiển thị chính xác có thể giúp phát hiện regression. Nhưng khi JDK/CLDR được nâng, một biến đổi pattern **có thể là cập nhật ngôn ngữ đúng** thay vì lỗi. Tránh sửa snapshot mù quáng; phân tích:
- source dữ liệu/provider/version đã thay đổi chưa;
- nội dung giao diện có còn rõ ràng và đúng ngôn ngữ không;
- việc parse từ chuỗi cũ có bị phá không;
- yêu cầu pháp lý/bản in có cần format cố định ngoài CLDR không.

Đối với giao tiếp giữa các hệ thống, dùng dạng có hợp đồng ổn định như ISO 8601 cho ngày/giờ phù hợp ngữ nghĩa, decimal string hoặc số có đơn vị rõ ràng, chứ không dùng locale display text làm “nguồn chân lý”.

## 14. Bảng lỗi phổ biến

| Sai lầm | Vì sao sai | Cách tránh |
| --- | --- | --- |
| Nghĩ CLDR là máy dịch tự động | CLDR là dữ liệu/quy tắc locale chung, không dịch mọi câu ứng dụng | Dùng ResourceBundle + người dịch/tooling |
| Nghĩ `Locale` chứa mọi quy tắc văn hóa trong chính object | Locale chủ yếu là định danh | Dùng API + provider data |
| Nghĩ JDK 17 có mọi API CLDR | CLDR có nhiều lĩnh vực, JDK chỉ tích hợp một phần | Kiểm tra JDK API cụ thể |
| Suy `BreakIterator`/`Collator` Java17 chắc chắn dùng CLDR | Tài liệu JDK17 nêu ngoại lệ tích hợp | Đọc hỗ trợ của từng service |
| Dùng một pattern ngày cố định cho mọi locale | Thứ tự và quy ước khác nhau | ofLocalizedDate với locale |
| Parse số UI bằng locale của server | Dấu chấm/phẩy khác nghĩa | Truyền locale nhập liệu và validate |
| Dùng ký hiệu tiền như đơn vị lưu trữ | Symbol có thể trùng giữa currency | Lưu mã ISO |
| Suy timezone từ locale | Nhiều vùng, người dùng có lựa chọn khác | ZoneId riêng |
| Dùng `java.locale.providers` sau startup | Thứ tự provider đã được đọc khi JVM khởi động | Đặt khi launch |
| Giới thiệu `COMPAT` như lựa chọn cho JDK 23+ | Legacy provider đã bị xóa | Chuyển sang CLDR hoặc giải pháp rõ |
| Cho rằng CLDR mới nhất đồng nghĩa JDK đã mới | Runtime có dữ liệu tích hợp theo phiên bản | Kiểm tra vendor/version |
| Không test `jlink` runtime cuối | Có thể thiếu locale data modules | Test runtime image thực |
| Dùng localized text làm API máy | Output đổi theo locale/runtime | Dùng machine-readable format |
| Nghĩ CLDR plural rules = Java17 MessageFormat plural | API Java17 không hỗ trợ cú pháp ICU plural | Dùng engine phù hợp khi cần |
| Chỉ test en-US | Không thấy các lỗi locale khác | Test toàn bộ locale hỗ trợ |

## 15. Bài tập tự đánh giá

**Câu 1.** CLDR có phải một API Java chuyên dịch các nhãn giao diện sang mọi ngôn ngữ không?

**Đáp án:** Không. CLDR là repository dữ liệu và quy tắc locale dùng chung. Ứng dụng vẫn phải cung cấp bản dịch nội dung của chính mình qua ResourceBundle hoặc hệ thống bản dịch tương đương.

**Câu 2.** Vì sao cùng `BigDecimal("1234.5")` có thể được format khác giữa `Locale.US` và `Locale.GERMANY`?

**Đáp án:** Hai locale có quy ước dấu phân nhóm và dấu thập phân khác nhau; `NumberFormat` lấy dữ liệu và hành vi phù hợp từ provider của JDK. Giá trị số học không đổi.

**Câu 3.** Trên Java 17, `java.locale.providers=COMPAT,CLDR` có ý nghĩa gì? Trên Java 23 có nên dùng như một phương án cố định không?

**Đáp án:** Trên Java 17, nó ưu tiên bộ dữ liệu tương thích cũ trước CLDR khi hỗ trợ. Dữ liệu COMPAT/JRE đã bị loại bỏ từ JDK 23, nên không dựa vào cách này làm chiến lược lâu dài.

**Câu 4.** Nếu CLDR có plural rules tiếng Nga, tại sao Java 17 `java.text.MessageFormat` không tự hiểu `{count, plural, ...}`?

**Đáp án:** Dự án dữ liệu và khả năng của API formatter là hai thứ khác nhau. Cú pháp plural ICU không phải cú pháp `java.text.MessageFormat` của Java 17; cần một thư viện/engine hỗ trợ.

**Câu 5.** `Locale.forLanguageTag("vi-VN")` có tự xác định timezone và đơn vị tiền thực tế của giao dịch không?

**Đáp án:** Không. Locale giúp chọn cách hiển thị nhưng timezone người dùng và currency giao dịch phải được cung cấp theo nghiệp vụ.

**Bài tập:** Chạy `CldrJdkLocaleDemo` trên JDK 17 với startup provider mặc định và với `-Djava.locale.providers=COMPAT,CLDR`. Ghi lại kết quả format thực tế ở en-US, de-DE, fr-FR và vi-VN, kết hợp kiểm thử ngày/số/tiền. Sau đó chạy trên JDK mới và phân tích vì sao lựa chọn COMPAT không còn giá trị từ JDK 23. Đừng suy rằng mọi khác biệt là bug; đối chiếu với dữ liệu locale và tài liệu provider của runtime.

## 16. Tài liệu tham khảo

- [Unicode CLDR Project](https://cldr.unicode.org/): mục đích, phạm vi, dữ liệu locale và phát hành.
- [Unicode Technical Standard #35 — CLDR](https://www.unicode.org/reports/tr35/tr35.html): mô hình locale, LDML và các quy tắc.
- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252): cơ chế và lịch sử ưu tiên CLDR trong Java.
- [Oracle JDK 17 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk17-suported-locales.html): dữ liệu Oracle JDK 17, CLDR 39, provider và ngoại lệ BreakIterator/Collator.
- [LocaleServiceProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): thứ tự `java.locale.providers` và các loại nhà cung cấp.
- [DateTimeFormatter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): định dạng ngày giờ theo locale.
- [NumberFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): định dạng số và tiền.
- [JDK 23 migration — Removed legacy locale data](https://docs.oracle.com/en/java/javase/23/migrate/removed-tools-and-components.html): việc loại bỏ COMPAT/JRE.
- [Locale — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): language tag và tên hiển thị.

**Ghi nhớ:** **CLDR cung cấp dữ liệu/quy tắc bản địa hóa; JDK cung cấp các API và nhà cung cấp áp dụng phần dữ liệu phù hợp; ứng dụng chịu trách nhiệm ngữ nghĩa nghiệp vụ và nội dung dịch riêng.** Truyền `Locale` tường minh, phân biệt định dạng người đọc với dữ liệu máy, kiểm thử theo phiên bản/provider JDK và không giả định mọi chức năng CLDR đều được Java 17 tích hợp.
