# Locale mặc định và định dạng cần Locale tường minh trong Java

## Mục tiêu bài học

Khi thao tác với API chuỗi của Java, cùng một giá trị có thể được hiển thị khác nhau tùy ngôn ngữ và quy ước vùng miền (*locale*). Bài học này giúp bạn:

- Hiểu **default locale** là gì và vì sao kết quả từ `String.format(...)` hoặc `String.formatted(...)` có thể khác nhau giữa máy phát triển, máy kiểm thử và máy chủ.
- Chọn **Locale tường minh** khi format số, ngày tháng, chữ hoa/chữ thường hoặc văn bản cần hiển thị cho một đối tượng xác định.
- Phân biệt nhu cầu **hiển thị cho người dùng** và **dữ liệu kỹ thuật cần kết quả ổn định**.
- Tránh phụ thuộc vào locale mặc định của hệ thống khi viết API, log có cấu trúc, dữ liệu xuất, kiểm thử hoặc xử lý khóa định danh.

**Phạm vi hiện hành:** Các API `java.util.Locale`, `String.format`, `String.formatted`, `NumberFormat` và `java.time.format.DateTimeFormatter` đều vẫn được sử dụng trong Java hiện đại. `String.formatted` có từ Java 15; ví dụ hoàn chỉnh trong bài dùng cú pháp tương thích **Java 17+**. Không cần preview flag.

## 1. Locale là gì? Vì sao một số có nhiều cách viết?

`Locale` mô tả quy ước về ngôn ngữ, quốc gia/vùng và các đặc điểm bản địa hóa liên quan. Ví dụ:

- `Locale.US`: quy ước tiếng Anh tại Hoa Kỳ, thường dùng dấu chấm làm dấu thập phân và dấu phẩy để nhóm hàng nghìn.
- `Locale.GERMANY`: quy ước tiếng Đức tại Đức, thường dùng dấu phẩy thập phân và dấu chấm nhóm hàng nghìn.
- `Locale.forLanguageTag("vi-VN")`: một locale cho tiếng Việt tại Việt Nam.
- `Locale.ROOT`: locale trung lập, thường hữu ích cho một số thao tác **kỹ thuật không nhắm đến ngôn ngữ người dùng**.

Cùng số `12345.67`:

```java
double value = 12345.67;

String us = String.format(Locale.US, "%,.2f", value);
String germany = String.format(Locale.GERMANY, "%,.2f", value);

// us      = "12,345.67"
// germany = "12.345,67"
```

Đây chỉ là **hai cách biểu diễn dạng văn bản** của cùng một `double`. Giá trị số trong bộ nhớ không đổi, và không nên nhầm chuỗi đã format với cách trao đổi dữ liệu số trong giao thức máy.

> Các mảnh code ở những mục giải thích có thể cần `import java.util.Locale;` hoặc đặt trong một phương thức. Phần “Chương trình hoàn chỉnh” ở cuối có đủ import, tên tệp, lệnh chạy và stdout.

## 2. Default locale: tiện dụng nhưng phụ thuộc môi trường

Java cho phép một ứng dụng có **locale mặc định**. Nếu một API không được truyền `Locale`, nó có thể lấy locale mặc định tương ứng. Giá trị này có thể khác theo cấu hình máy, container, quy trình chạy hoặc thay đổi do chính ứng dụng thực hiện. Do đó, mặc định của hệ điều hành **không nhất thiết là lựa chọn của người đang xem nội dung**.

Với các API định dạng, hãy biết hai lệnh sau:

```java
Locale generalDefault = Locale.getDefault();
Locale formatDefault = Locale.getDefault(Locale.Category.FORMAT);
```

`Locale.Category.FORMAT` dành cho các tác vụ format/parse số, ngày, tiền tệ. `Locale.Category.DISPLAY` dùng cho mục đích hiển thị tên ngôn ngữ/vùng. Hai category có thể được cấu hình khác nhau; vì thế **không nên mặc định rằng `getDefault()` luôn bằng `getDefault(FORMAT)`**.

### 2.1. `String.format` không có đối số Locale

```java
String amount = String.format("%,.2f", 12345.67);
```

Lời gọi này dùng **default FORMAT locale**. Trên một môi trường, `amount` có thể là `"12,345.67"`; trên môi trường khác có thể là `"12.345,67"`. Không thể kết luận chính xác đầu ra chỉ từ đoạn mã trên nếu chưa biết môi trường thực thi.

Nếu muốn chủ động dùng locale mặc định của ứng dụng một cách minh bạch:

```java
Locale locale = Locale.getDefault(Locale.Category.FORMAT);
String amount = String.format(locale, "%,.2f", 12345.67);
```

Cách này làm **nguồn lựa chọn locale** dễ nhìn hơn, nhưng kết quả vẫn phụ thuộc cấu hình hiện tại. Nó chỉ phù hợp nếu đó thật sự là chính sách định dạng mong muốn của ứng dụng.

### 2.2. `String.formatted` cũng dựa trên default locale

`String.formatted(Object... args)` (Java 15+) gọi cơ chế format của `String` với chính chuỗi hiện tại làm mẫu:

```java
String text = "Amount: %,.2f".formatted(12345.67);
```

Nó **không có overload nhận `Locale` ở vị trí đầu**. Do đó, khi cần locale tường minh, hãy dùng:

```java
String text = String.format(Locale.US, "Amount: %,.2f", 12345.67);
```

Không viết `"Amount: %,.2f".formatted(Locale.US, 12345.67)` với kỳ vọng chọn locale: `Locale.US` ở đây sẽ bị coi là một đối số format thông thường, không phải cấu hình locale.

Điều tương tự cần lưu ý với `System.out.printf(...)` và `System.out.format(...)`: các API này có overload nhận `Locale`. Muốn kiểm soát kết quả, hãy chọn overload đó, ví dụ `System.out.printf(Locale.US, "%.2f%n", 1.5);`.

## 3. Khi nào phải truyền Locale tường minh?

Nên truyền locale rõ ràng nếu định dạng có ý nghĩa nghiệp vụ hoặc cần dự đoán được:

1. **Giao diện cho người dùng:** định dạng theo ngôn ngữ/vùng mà người dùng đã chọn hoặc ứng dụng xác định, thay vì ngẫu nhiên theo máy chủ.
2. **Email, báo cáo, hóa đơn, thông báo:** người nhận có quy ước số và ngày riêng; ứng dụng cần biết ai là người nhận.
3. **Kiểm thử snapshot/expected string:** phải cố định locale để cùng đầu vào tạo cùng chuỗi trên máy CI khác nhau.
4. **Dữ liệu xuất theo hợp đồng định dạng:** trường CSV, báo cáo cho hệ thống bên ngoài hoặc API có đặc tả riêng phải theo quy tắc đã công bố.
5. **Xử lý văn bản kỹ thuật:** chuyển chữ hoa/chữ thường cho token, khóa cấu hình, từ khóa giao thức thường cần `Locale.ROOT` hoặc quy tắc chuẩn hóa chuyên biệt.

Ví dụ cho một báo cáo yêu cầu quy ước số của Đức:

```java
Locale reportLocale = Locale.GERMANY;
String total = String.format(reportLocale, "Total: %,.2f", 12345.67);
// "Total: 12.345,67"
```

Chữ `Total` vẫn là tiếng Anh: **Locale chỉ ảnh hưởng quy tắc định dạng được API hỗ trợ**, không tự dịch nội dung văn bản. Nếu cần dịch thông báo, ứng dụng phải cung cấp tài nguyên bản địa hóa phù hợp, ví dụ `ResourceBundle`, và xử lý câu theo yêu cầu ngôn ngữ. Việc chọn locale định dạng và chọn bản dịch là hai việc có liên quan nhưng không đồng nhất.

## 4. Chọn Locale nào: US, ROOT, hay locale của người dùng?

### 4.1. `Locale.US` hoặc locale cụ thể cho đầu ra được quy định

Nếu hợp đồng dữ liệu yêu cầu dấu chấm thập phân kiểu US và bạn đang dùng `Formatter`:

```java
String stable = String.format(Locale.US, "%.2f", 1.5);
// "1.50"
```

Không cần đoán locale của máy chủ. Với nội dung theo người dùng, dùng locale người dùng được chọn, chẳng hạn:

```java
Locale userLocale = Locale.forLanguageTag("vi-VN");
String amount = String.format(userLocale, "%,.2f", 12345.67);
```

Vì dữ liệu bản địa hóa có thể thay đổi theo phiên bản JDK/CLDR, không nên khẳng định mọi dạng biểu diễn dành cho người dùng sẽ giống từng dấu câu qua mọi phiên bản runtime. Khi cần định dạng chính xác từng ký tự, hãy đặc tả và kiểm thử kết quả theo yêu cầu hệ thống.

### 4.2. `Locale.ROOT` cho một số thao tác trung lập

`Locale.ROOT` không đại diện cho một người dùng cụ thể. Nó thích hợp khi một thao tác **không cần lựa chọn ngôn ngữ theo người dùng**, đặc biệt khi chuẩn hóa chữ hoa/chữ thường của từ khóa kỹ thuật:

```java
String normalizedKey = "Content-Type".toLowerCase(Locale.ROOT);
// "content-type"
```

Với định dạng số đơn giản, `String.format(Locale.ROOT, "%.1f", 1.5)` tạo `"1.5"`. Tuy nhiên, `Locale.ROOT` không phải “locale đúng cho mọi dữ liệu”. Muốn xuất JSON, dùng thư viện JSON; muốn ngày theo ISO, dùng `DateTimeFormatter.ISO_LOCAL_DATE`; muốn biểu diễn số chính xác dùng trong tính toán, cân nhắc `BigDecimal` và API chuyển số thích hợp. Đừng dùng định dạng dành cho người dùng làm chuẩn truyền dữ liệu nếu giao thức đã có định dạng riêng.

### 4.3. Chọn locale theo người nhận, không theo người tạo dữ liệu

Một máy chủ đặt tại Mỹ có thể phục vụ người dùng ở Việt Nam và Đức. Nếu dùng `String.format("%,.2f", value)` trên máy chủ, cả hai người dùng dễ nhận cùng định dạng bất kể lựa chọn thực tế của họ. Ứng dụng nên lấy locale từ cài đặt người dùng, bối cảnh phiên hoặc nguồn được chính sách ứng dụng chấp nhận, rồi **truyền locale trực tiếp xuống lớp trình bày**:

```java
static String formatAmount(double amount, Locale userLocale) {
    return String.format(userLocale, "%,.2f", amount);
}
```

Cách truyền phụ thuộc rõ ràng giúp code dễ kiểm thử và tránh trạng thái toàn cục khó dự đoán.

## 5. Locale còn ảnh hưởng chuyển chữ hoa/chữ thường

Ngoài `format`, `String.toLowerCase()` và `String.toUpperCase()` **không đối số** còn dùng default locale cho việc đổi chữ. Điều này có thể gây lỗi ở những ngôn ngữ có quy tắc riêng.

Ví dụ nổi tiếng là tiếng Thổ Nhĩ Kỳ: chữ `I` viết thường có thể thành **ı** (Latin small dotless i, U+0131), khác chữ `i` trong tiếng Anh:

```java
Locale turkish = Locale.forLanguageTag("tr-TR");

String neutral = "TITLE".toLowerCase(Locale.ROOT);  // "title"
String localized = "TITLE".toLowerCase(turkish);     // "tıtle"
```

Khi chuẩn hóa từ khóa kỹ thuật, dùng overload nhận `Locale` để chủ động quy tắc:

```java
String command = userInput.toLowerCase(Locale.ROOT);
```

Nếu đang hiển thị tên/văn bản bằng ngôn ngữ người dùng, hãy cân nhắc locale thực tế của người đó thay vì `ROOT`.

**Điểm phân biệt quan trọng:** `toLowerCase()` không đối số lấy default locale tổng quát (`Locale.getDefault()`), còn `String.format(...)` không có locale dùng default `FORMAT` locale. Đừng coi hai lời gọi mặc định này luôn sử dụng cùng một cấu hình category.

Chuyển chữ hoa/chữ thường còn xuất hiện trong `Formatter`: conversion `%S` có thể dùng locale của formatter để viết hoa biểu diễn đối số.

```java
Locale turkish = Locale.forLanguageTag("tr-TR");
boolean upperIsTurkish = String.format(turkish, "%S", "iki")
        .equals("\u0130K\u0130"); // true, \u0130 là U+0130
```

Chuyển lowercase không phải một thuật toán xác định danh tính/so khớp Unicode hoàn chỉnh: đừng tùy tiện lấy `toLowerCase(Locale.ROOT)` làm bằng chứng hai tên người dùng hay hai chuỗi Unicode tương đương. Nếu hệ thống cần quy tắc so khớp Unicode nghiêm ngặt, phải định nghĩa và kiểm thử quy tắc đó riêng.

## 6. Format số cần Locale tường minh

### 6.1. Dùng `String.format(Locale, ...)`

Đối với cú pháp định dạng kiểu `Formatter`, những conversion như `%f` và cờ phân nhóm `,` được địa phương hóa:

```java
double amount = 12345.67;
String us = String.format(Locale.US, "%,.2f", amount);
String de = String.format(Locale.GERMANY, "%,.2f", amount);

// us = "12,345.67"
// de = "12.345,67"
```

Mẫu `%,.2f` có nghĩa là định dạng số thực với phân nhóm hàng nghìn và hai chữ số sau dấu thập phân. Việc dùng `Locale` ảnh hưởng dấu phân nhóm và dấu thập phân; không làm biến đổi `amount`.

Cảnh báo thực tế: `double` là số dấu phẩy động nhị phân; với tiền và bài toán cần độ chính xác thập phân chặt chẽ, nên sử dụng `BigDecimal` hoặc kiểu tiền phù hợp. `Locale` chỉ thay đổi **cách hiển thị**, không giải quyết sai số biểu diễn số.

### 6.2. Dùng `NumberFormat` cho trình bày hoặc đọc số bản địa hóa

`java.text.NumberFormat` vẫn là API phù hợp cho nhiều trường hợp số, phần trăm và tiền tệ. Truyền locale rõ ràng khi tạo formatter:

```java
import java.text.NumberFormat;
import java.util.Locale;

Locale locale = Locale.GERMANY;
NumberFormat numberFormat = NumberFormat.getNumberInstance(locale);
numberFormat.setMinimumFractionDigits(2);
numberFormat.setMaximumFractionDigits(2);
String display = numberFormat.format(12345.67);
```

Khi cần đọc lại số ở dạng văn bản của người dùng, có thể dùng `NumberFormat.getNumberInstance(locale).parse(input)`, đồng thời kiểm tra lỗi và quy tắc chấp nhận đầu vào. Không dùng máy móc `Double.parseDouble` cho chuỗi đã địa phương hóa: nó kỳ vọng cú pháp số của Java, không hiểu mọi dạng dấu phân nhóm/thập phân của người dùng.

Đối với tiền tệ, locale trình bày chưa nhất thiết xác định đúng **loại tiền nghiệp vụ**. Hãy chọn `Currency` theo giao dịch hoặc thiết lập đã được xác định, không suy luận tiền tệ chỉ từ nơi đặt máy chủ.

## 7. Format ngày giờ: dùng `java.time` và Locale tường minh

Ngày tháng đặc biệt nhạy với ngôn ngữ của **tên tháng, thứ trong tuần** và thứ tự trình bày. Với API hiện đại `java.time`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalDate date = LocalDate.of(2024, 1, 2);

String usDate = DateTimeFormatter
        .ofPattern("dd MMMM uuuu", Locale.US)
        .format(date);

String germanDate = DateTimeFormatter
        .ofPattern("dd MMMM uuuu", Locale.GERMANY)
        .format(date);

// usDate     = "02 January 2024"
// germanDate = "02 Januar 2024"
```

Ở đây `MMMM` nghĩa là tên tháng đầy đủ theo locale; `uuuu` là năm theo proleptic ISO year trong mẫu này. Nếu chọn `DateTimeFormatter.ofPattern(pattern)` mà không truyền locale, kết quả có thể chịu ảnh hưởng của default FORMAT locale.

Đối với dữ liệu kỹ thuật tuân theo ISO 8601, dùng formatter ISO có sẵn thay vì dựa vào tên tháng hay locale môi trường:

```java
String iso = DateTimeFormatter.ISO_LOCAL_DATE
        .format(LocalDate.of(2024, 1, 2));
// "2024-01-02"
```

**Locale không đồng nghĩa với múi giờ (time zone).** Locale quyết định quy ước trình bày; múi giờ dùng các API liên quan như `ZoneId` và loại thời gian thích hợp (ví dụ `ZonedDateTime`). Chọn `Locale.US` không tự chuyển thời điểm sang múi giờ Hoa Kỳ.

## 8. Locale mặc định thay đổi được, nhưng không nên dùng để điều khiển từng yêu cầu

Java có API thay đổi default locale, bao gồm `Locale.setDefault(...)` và `Locale.setDefault(Locale.Category.FORMAT, ...)`. Việc thay đổi này ảnh hưởng tới **trạng thái mặc định cấp JVM**, có thể tác động các phần khác của ứng dụng, thư viện hoặc luồng đang xử lý đồng thời.

Đoạn dưới chỉ **minh họa cơ chế**, không phải giải pháp khuyến nghị trong server xử lý nhiều người dùng:

```java
// Ví dụ minh họa: thay đổi default FORMAT locale của JVM
Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);
String value = String.format("%,.2f", 12345.67);
```

Đừng gọi `Locale.setDefault` mỗi khi nhận HTTP request để format theo locale người dùng; hai request chạy song song có thể phụ thuộc lẫn nhau. Hãy truyền locale vào lời gọi định dạng:

```java
String value = String.format(userLocale, "%,.2f", 12345.67);
```

Đối với kiểm thử, tốt nhất viết test có đối số `Locale` cụ thể. Nếu bắt buộc kiểm thử hành vi mặc định, hãy cô lập thay đổi trạng thái JVM, khôi phục cấu hình sau test và tránh chạy đồng thời những test phụ thuộc nó.

## 9. Thiết kế API dễ kiểm thử và dễ mở rộng

Một hàm format làm việc rõ ràng hơn khi nhận cả giá trị và locale:

```java
static String labelFor(double total, Locale locale) {
    return String.format(locale, "Total: %,.2f", total);
}
```

Ưu điểm:

- Đầu vào có tất cả thông tin cần để quyết định format; không phải đoán môi trường chạy.
- Cùng hàm có thể phục vụ nhiều vùng/ngôn ngữ.
- Unit test có thể kiểm tra các trường hợp `Locale.US`, `Locale.GERMANY` bằng expected string chính xác.
- Việc đổi mặc định của máy chủ không vô tình làm thay đổi tài liệu hoặc dữ liệu đã cam kết định dạng.

Nếu nhận mã ngôn ngữ từ bên ngoài, `Locale.forLanguageTag("vi-VN")` là cách tạo `Locale` từ chuỗi tag theo chuẩn BCP 47. Với input không đáng tin hoặc yêu cầu khắt khe, cần xác thực tag và kiểm tra locale có thuộc danh sách được ứng dụng hỗ trợ trước khi sử dụng; đừng coi mọi chuỗi đầu vào đều biểu diễn locale hợp lệ và có dữ liệu bản địa hóa đầy đủ.

### Giao thức dữ liệu và văn bản hiển thị là hai tầng khác nhau

Ví dụ một API trả về số tiền để máy khác xử lý: nên truyền giá trị số hoặc biểu diễn số theo giao thức có cấu trúc rõ ràng. Chuỗi `"12.345,67"` hữu ích cho người dùng Đức nhưng không thích hợp để đoán ngược số bằng một parser định dạng US. Tương tự, ngày truyền giữa các hệ thống nên dùng mẫu ngày ISO hoặc kiểu dữ liệu có đặc tả, sau đó mới địa phương hóa ở nơi trình bày.

## 10. Chương trình Java hoàn chỉnh (có thể biên dịch)

Tạo tệp `LocaleStringDemo.java` với nội dung sau (UTF-8). Chương trình tránh phụ thuộc vào locale của máy khi in các giá trị cần so sánh; trường hợp default được kiểm tra bằng biểu thức tương đương thay vì gán một kết quả cụ thể cho mọi môi trường.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class LocaleStringDemo {
    public static void main(String[] args) {
        Locale us = Locale.US;
        Locale germany = Locale.GERMANY;
        Locale turkish = Locale.forLanguageTag("tr-TR");
        double amount = 12345.67;

        System.out.println("us=" +
                String.format(us, "%,.2f", amount));
        System.out.println("de=" +
                String.format(germany, "%,.2f", amount));

        String defaultFormatted = "%.2f".formatted(1.5);
        String sameDefault = String.format(
                Locale.getDefault(Locale.Category.FORMAT),
                "%.2f", 1.5);
        System.out.println("formattedDefault=" +
                defaultFormatted.equals(sameDefault));

        System.out.println("rootLower=" +
                "TITLE".toLowerCase(Locale.ROOT).equals("title"));
        System.out.println("turkishLower=" +
                "TITLE".toLowerCase(turkish).equals("t\u0131tle"));

        LocalDate date = LocalDate.of(2024, 1, 2);
        System.out.println("dateUS=" +
                DateTimeFormatter.ofPattern("dd MMMM uuuu", us)
                        .format(date));
        System.out.println("dateDE=" +
                DateTimeFormatter.ofPattern("dd MMMM uuuu", germany)
                        .format(date));

        System.out.println("rootNumber=" +
                String.format(Locale.ROOT, "%.1f", 1.5));
        System.out.println("trPercentS=" +
                String.format(turkish, "%S", "iki")
                        .equals("\u0130K\u0130"));
    }
}
```

Chạy với **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 LocaleStringDemo.java
java LocaleStringDemo
```

**Stdout đã kiểm chứng:**

```text
us=12,345.67
de=12.345,67
formattedDefault=true
rootLower=true
turkishLower=true
dateUS=02 January 2024
dateDE=02 Januar 2024
rootNumber=1.5
trPercentS=true
```

Diễn giải: hai dòng đầu cho thấy sự khác biệt của locale trong định dạng số; `formattedDefault=true` xác nhận `formatted` dùng cùng default FORMAT locale như overload tương ứng của `String.format`; hai kết quả lowercase cho thấy quy tắc Unicode theo locale; hai kết quả ngày cho thấy tên tháng khác nhau; `rootNumber` là ví dụ định dạng trung lập; `%S` chứng minh chuyển chữ hoa trong `Formatter` cũng có thể phụ thuộc locale.

## 11. Lỗi phổ biến và cách khắc phục

| Lỗi thường gặp | Vì sao sai hoặc dễ lỗi | Cách đúng |
| --- | --- | --- |
| Dùng `String.format("%,.2f", amount)` trong dữ liệu phải giống nhau ở mọi môi trường | Kết quả phụ thuộc default FORMAT locale | Truyền `Locale.US`, `Locale.ROOT` hoặc locale do đặc tả yêu cầu |
| Cho rằng `"%.2f".formatted(number)` luôn dùng dấu chấm | `formatted` không nhận locale và dùng default FORMAT locale | Dùng `String.format(locale, "%.2f", number)` |
| Dùng `Locale.getDefault()` làm locale cho mọi người dùng | Locale của server không nhất thiết là lựa chọn của người nhận | Lấy locale từ thiết lập/bối cảnh người dùng và truyền tường minh |
| Dùng `toLowerCase()` cho khóa cấu hình | Kết quả có thể thay đổi theo default locale | Dùng `toLowerCase(Locale.ROOT)` nếu phù hợp hợp đồng chuẩn hóa |
| Nghĩ `Locale.ROOT` là ngôn ngữ hiển thị của mọi người dùng | ROOT không phản ánh một quốc gia/ngôn ngữ cụ thể | Dùng locale người dùng khi hiển thị văn bản |
| Nghĩ `Locale.US` tự dịch thông báo sang tiếng Anh | Locale chỉ áp dụng lên quy tắc mà API hỗ trợ | Dùng tài nguyên bản dịch cho câu chữ, đồng thời format theo locale |
| Thay `Locale.setDefault` cho từng request | Thay đổi trạng thái mặc định ở JVM, dễ ảnh hưởng request khác | Truyền `Locale` qua tham số phương thức |
| Dùng chuỗi số đã format cho người đọc làm đầu vào máy | Dấu phân cách có thể khác giữa các locale | Dùng kiểu số/serializer theo giao thức; parse theo locale khi xử lý input người dùng |
| Nhầm locale với timezone | Locale và múi giờ là hai khái niệm khác nhau | Dùng `ZoneId` và kiểu `java.time` khi cần chuyển múi giờ |
| Snapshot test theo tên tháng locale mặc định | Locale môi trường và dữ liệu CLDR có thể thay đổi | Khóa locale trong test, cân nhắc formatter ISO cho dữ liệu kỹ thuật |

## 12. Bài tập tự kiểm tra

**Bài 1.** Hai lời gọi sau có chắc giống nhau trên mọi máy không?

```java
String a = String.format("%,.2f", 12345.67);
String b = String.format(Locale.US, "%,.2f", 12345.67);
```

**Đáp án:** Không. `a` dựa vào default FORMAT locale; `b` chọn locale US rõ ràng. Chúng chỉ chắc chắn trùng về quy tắc locale khi môi trường của `a` chọn quy ước tương ứng.

**Bài 2.** Vì sao `"%.1f".formatted(1.5)` không phù hợp khi hợp đồng luôn yêu cầu chuỗi `"1.5"`?

**Đáp án:** `formatted` chịu ảnh hưởng default FORMAT locale. Dùng `String.format(Locale.US, "%.1f", 1.5)` hoặc API biểu diễn số máy theo yêu cầu giao thức.

**Bài 3.** Bạn viết hàm tạo chuỗi tiền cho người dùng ở nhiều quốc gia. Có nên gọi `Locale.setDefault` trong mỗi lần gọi hàm?

**Đáp án:** Không. Hãy truyền locale người dùng vào hàm, đồng thời xác định đơn vị tiền tệ theo giao dịch. Không thay đổi locale mặc định của JVM theo từng người dùng.

**Bài 4.** Vì sao `"TITLE".toLowerCase()` không thích hợp làm chuẩn hóa từ khóa mang nghĩa kỹ thuật?

**Đáp án:** Nó phụ thuộc default locale; ví dụ trong locale tiếng Thổ Nhĩ Kỳ, chữ `I` có thể chuyển thành `ı`. Khi quy tắc kỹ thuật phù hợp, dùng `toLowerCase(Locale.ROOT)`; với hệ thống có yêu cầu so khớp Unicode riêng phải tuân thủ quy tắc được thiết kế rõ ràng.

## Ghi nhớ

**Locale mặc định là một phụ thuộc môi trường.** Đối với mã Java tạo văn bản cần tính nhất quán, hãy kiểm soát locale ngay tại lời gọi API. `String.format(Locale, ...)` cho phép tường minh, còn `String.formatted(...)` sử dụng default FORMAT locale. Khi chuyển chữ hoa/chữ thường của khóa kỹ thuật, cân nhắc `Locale.ROOT`; khi hiển thị số/ngày cho người dùng, chọn locale của chính người dùng; khi truyền dữ liệu giữa các hệ thống, ưu tiên định dạng giao thức đã định nghĩa.

### Tài liệu chính thức

- [Java SE 21 – String: format, formatted và đổi chữ hoa/chữ thường](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Java SE 21 – Locale và Locale.Category](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Java SE 21 – Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html)
- [Java SE 21 – NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html)
- [Java SE 21 – DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
