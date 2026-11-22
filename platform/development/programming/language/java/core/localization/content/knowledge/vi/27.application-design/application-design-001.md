# Tách dữ liệu nghiệp vụ khỏi văn bản hiển thị trong ứng dụng Java

## 1. Vì sao cần tách dữ liệu nghiệp vụ và văn bản hiển thị?

Trong một ứng dụng bản địa hóa (*localization*), **dữ liệu nghiệp vụ** mô tả sự thật và các quy tắc của hệ thống: số tiền, đơn vị tiền tệ, số lượng, thời điểm, trạng thái đơn hàng, mã sản phẩm. **Văn bản hiển thị** là cách diễn đạt dữ liệu đó cho người dùng bằng một ngôn ngữ, quy ước số, ngày giờ và bố cục cụ thể.

Giả sử một đơn hàng có tổng tiền **1.234,50 EUR**. Cùng một dữ liệu có thể được hiển thị:

```text
en-US: €1,234.50
de-DE: 1.234,50 €
```

Chữ `EUR`, trị số decimal `1234.50` và ID đơn hàng **không thay đổi** khi người dùng chuyển từ tiếng Anh sang tiếng Đức. Chỉ lớp trình bày (*presentation*) sử dụng `Locale` để quyết định dấu thập phân, dấu nhóm, vị trí ký hiệu và khoảng trắng.

Nếu lưu `"€1,234.50"` làm giá trị tiền, một parser theo `de-DE` có thể hiểu sai hoặc từ chối nó; nếu so chuỗi hiển thị làm khóa, thay đổi ngôn ngữ có thể làm tra cứu thất bại; nếu lưu `"Đã thanh toán"` thay cho trạng thái `PAID`, hệ thống sẽ phụ thuộc bản dịch tiếng Việt để vận hành.

**Nguyên tắc:** *Dữ liệu domain là nguồn sự thật; văn bản hiển thị là kết quả có thể tái tạo theo locale và ngữ cảnh.* Không đảo vai trò của hai lớp này.

### Mục tiêu học tập

Sau bài học, bạn sẽ:

1. Phân biệt domain model, application/service, persistence/API, localization/presentation và UI layout.
2. Biểu diễn **số tiền** bằng `BigDecimal` cùng `Currency`, **thời điểm** bằng `Instant` hoặc kiểu thời gian thích hợp, **trạng thái** bằng enum/mã ổn định.
3. Sử dụng `NumberFormat`, `DateTimeFormatter`, `ResourceBundle` và `MessageFormat` ở đúng ranh giới hiển thị.
4. Thiết kế đầu vào theo locale nhưng lưu dữ liệu theo **hợp đồng độc lập locale**.
5. Tránh các lỗi trộn bản dịch với business rules, lưu tiền ở dạng chuỗi định dạng, dùng default locale toàn JVM hoặc so sánh nhãn UI.
6. Phân biệt **mã máy dùng để trao đổi** với **tên/nhãn người dùng đọc được**, và tách locale, currency, timezone thành những thuộc tính độc lập.
7. Kiểm thử việc đổi ngôn ngữ mà không làm đổi giá trị nghiệp vụ.

## 2. Một ví dụ: cùng một đơn hàng, nhiều cách nhìn

Xét dữ liệu domain:

```text
orderId    = "ORD-2026-042"
quantity   = 3
unitPrice  = 411.50
currency   = "EUR"
total      = 1234.50
paidAt     = 2026-10-28T01:30:00Z
status     = PAID
```

Phần **đã lưu** phải mang được các ý nghĩa này mà không dựa vào ngôn ngữ hiện tại. Với một locale và múi giờ hiển thị cụ thể, UI mới tạo các chuỗi:

| Trường domain | Người dùng en-US, UTC | Người dùng de-DE, Europe/Berlin |
| --- | --- | --- |
| `status = PAID` | Paid | Bezahlt |
| `total = 1234.50 EUR` | €1,234.50 | 1.234,50 € |
| `paidAt = 2026-10-28T01:30:00Z` | Ngày/giờ theo UTC | Ngày/giờ theo Europe/Berlin |
| `orderId` | ORD-2026-042 | ORD-2026-042 |

Bảng mô tả **ý nghĩa**; bản dịch, ngày/giờ và chuỗi tiền cụ thể phụ thuộc resource, Java locale provider và cấu hình sản phẩm. Dù presentation đổi, `total`, `currency`, `paidAt` và `status` vẫn bất biến.

Nếu người dùng đổi ngôn ngữ, hệ thống nên tính lại **view model** hoặc chuỗi đang hiển thị, không sửa record gốc trong database.

## 3. Các tầng trách nhiệm

| Tầng | Sở hữu | Không nên sở hữu |
| --- | --- | --- |
| **Domain model** | Giá trị và quy tắc nghiệp vụ: tiền, thuế, trạng thái, số lượng, thời điểm | Văn bản `"Đã thanh toán"`, dấu nhóm, tên tháng, nút UI |
| **Application/service** | Use case, tính toán, validation domain, giao dịch, quyền truy cập | Trộn các nhãn đã dịch vào business logic |
| **Persistence/API** | Schema, ID, currency code, decimal, instant, enum/code, hợp đồng trao đổi | Chuỗi trình bày tùy locale nếu không được định nghĩa là dữ liệu |
| **Localization/presenter** | `Locale`, `ResourceBundle`, formatter số/ngày, lời nhắn và placeholders | Quyết định số tiền thật, trạng thái thật, rounding nghiệp vụ |
| **UI/layout** | Wrap, canh lề, font, RTL, ellipsis, accessibility | Tự suy lại giá trị nghiệp vụ từ label |

Sơ đồ luồng một chiều:

```text
Persistence / API (canonical data)
                 |
                 v
    Domain model / use case
                 |
                 | dữ liệu có kiểu và ngữ nghĩa
                 v
          Presenter / i18n
         /          |          \
   ResourceBundle  NumberFormat  DateTimeFormatter
         \          |          /
                 v
       View model / UI strings
                 |
                 v
       Layout, font, RTL, wrap

User input → parser theo locale → validation → domain value
```

Việc UI gửi input lên không phá nguyên tắc này: chuỗi nhập **chỉ là đầu vào tạm thời**; một bước parsing/validation có trách nhiệm chuyển nó thành giá trị có kiểu trước khi truyền vào nghiệp vụ.

## 4. Số tiền: `BigDecimal` và mã tiền tệ, không phải một `String`

Một thiết kế sai thường gặp:

```java
// Sai về mô hình dữ liệu:
String total = "1.234,50 €";
```

Chuỗi này chứa đồng thời **giá trị**, **dấu phân nhóm**, **dấu thập phân**, **ký hiệu tiền** và **quy ước locale**. Không dễ cộng, so, lưu bền hoặc parse lại khi locale/JDK thay đổi. Ký hiệu `€` không thay thế được mô hình currency; tương tự ký hiệu `$` có thể chỉ nhiều đồng tiền.

Thiết kế rõ hơn:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }
}
```

Đây là **một file Java độc lập** nếu lưu thành `Money.java` (trong default package), dùng được trên Java 17+. Nó biểu diễn *amount + currency* mà không chứa locale hiển thị. Trong code thật còn cần quy tắc quy mô/phân số tiền, làm tròn, miền giá trị và phương thức cộng chỉ các đồng tiền tương thích. `BigDecimal` giữ các chữ số decimal, nhưng không tự áp đặt toàn bộ quy tắc tài chính.

### 4.1. `amount` không thể chỉ là `double` nếu cần tính tiền chính xác

`double` biểu diễn số nhị phân xấp xỉ; nhiều số như `0.1` không được lưu chính xác theo decimal. Dùng:

```java
BigDecimal amount = new BigDecimal("1234.50");
```

thay vì:

```java
BigDecimal amount = new BigDecimal(1234.50);
```

khi muốn chuyển từ literal decimal text một cách chính xác. Với các phép toán như chia, cần chọn scale và `RoundingMode` theo nghiệp vụ. **Formatter hiển thị không được âm thầm làm thay đổi amount domain** chỉ vì UI chỉ hiển thị hai chữ số.

### 4.2. Currency và locale là hai tham số khác nhau

`Locale.GERMANY` chỉ mô tả quy ước hiển thị cho người dùng, không có nghĩa mọi giao dịch của người đó đều dùng EUR. Một giao dịch USD của người dùng tại Đức vẫn phải lưu `USD` và amount chính xác, rồi format bằng **locale Đức** và **currency USD**.

Dùng `NumberFormat.getCurrencyInstance(displayLocale)` để lấy formatter, sau đó `setCurrency(domainCurrency)`. Không suy currency thật từ `Currency.getInstance(displayLocale)` nếu hợp đồng giao dịch cung cấp currency riêng.

## 5. Java 17+: một `Money`, hai chuỗi hiển thị

Tạo file `MoneyPresentationDemo.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class MoneyPresentationDemo {
    record Money(BigDecimal amount, Currency currency) {
        Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");
        }
    }

    static String display(Money money, Locale locale) {
        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(locale);
        formatter.setCurrency(money.currency());
        return formatter.format(money.amount());
    }

    public static void main(String[] args) {
        Money money = new Money(
                new BigDecimal("1234.50"),
                Currency.getInstance("EUR"));

        System.out.println("domain amount: "
                + money.amount().toPlainString());
        System.out.println("domain currency: "
                + money.currency().getCurrencyCode());

        for (String tag : List.of("en-US", "de-DE")) {
            Locale locale = Locale.forLanguageTag(tag);
            System.out.println(tag + ": " + display(money, locale));
        }

        System.out.println("unchanged: "
                + money.amount().equals(new BigDecimal("1234.50")));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MoneyPresentationDemo.java
java MoneyPresentationDemo
```

Ví dụ kết quả từ một JDK có locale data CLDR thông dụng:

```text
domain amount: 1234.50
domain currency: EUR
en-US: €1,234.50
de-DE: 1.234,50 €
unchanged: true
```

Dòng `de-DE` có thể chứa **U+00A0 NO-BREAK SPACE** trước `€`, không phải ASCII space. Vị trí/ký hiệu/space có thể khác giữa các bản JDK hoặc locale provider. Các dòng `domain amount`, `domain currency` và `unchanged` minh họa điều cần bất biến.

**Tách biệt quan trọng:** vì `NumberFormat` mutable và không bảo đảm thread-safe, ví dụ tạo formatter **mới cho mỗi lần gọi**. Không dùng chung một `NumberFormat` static giữa nhiều request rồi gọi `setCurrency` liên tục: có thể rò cấu hình và in sai đồng tiền.

### Nếu cần hai chữ số phần lẻ?

Đừng chỉ dựa vào `setMinimumFractionDigits(2)` để quyết định một khoản tiền hợp lệ: đó là **định dạng hiển thị**. Chính sách tiền tệ của domain có thể yêu cầu số chữ số khác nhau theo currency và loại giao dịch. Trước khi lưu hoặc tính toán, áp dụng validation và rounding business (ví dụ `RoundingMode.HALF_EVEN` hoặc quy tắc bắt buộc của nghiệp vụ); sau đó formatter trình bày kết quả theo locale.

## 6. Status: mã ổn định khác nhãn dịch

Một lỗi thiết kế nghiêm trọng:

```java
if (order.statusText().equals("Đã thanh toán")) {
    releaseGoods();
}
```

Mỗi lần thay đổi bản dịch, logic có thể sai. Tương tự, việc đổi ngôn ngữ tiếng Anh → tiếng Việt không phải lý do khiến đơn hàng đổi trạng thái.

Nên dùng một enum hoặc trạng thái domain ổn định:

```java
public enum OrderStatus {
    NEW, PAID, CANCELLED, REFUNDED
}
```

Resource tương ứng có thể là:

```properties
status.NEW=New
status.PAID=Paid
status.CANCELLED=Cancelled
status.REFUNDED=Refunded
```

và bản tiếng Việt:

```properties
status.NEW=Mới
status.PAID=Đã thanh toán
status.CANCELLED=Đã hủy
status.REFUNDED=Đã hoàn tiền
```

Các ví dụ `.properties` trên là **hai bộ dữ liệu khác nhau**, không ghép cùng một file. Khi triển khai, lưu chúng trong `Labels_en.properties` và `Labels_vi.properties` ở classpath.

`ResourceBundle.getBundle("Labels", locale)` chọn bản dịch theo cơ chế locale fallback. `ResourceBundle` là thành phần **presentation**, trong khi `OrderStatus.PAID` là thông tin nghiệp vụ. Không truyền label đã dịch vào API như một enum code; API nên dùng `"PAID"` theo schema đã thống nhất.

Nếu sản phẩm cần thay tên `"Paid"` thành `"Payment received"`, chỉ thay resource; logic domain không cần sửa.

## 7. Ví dụ Java 17+: `ResourceBundle` và `MessageFormat`

Đặt ba file trong **cùng một thư mục** khi chạy:

```text
Labels_en.properties
Labels_vi.properties
LocalizedStatusDemo.java
```

File `Labels_en.properties`:

```properties
status.PAID=Paid
receipt.summary=Order {0}: {1} — {2}
```

File `Labels_vi.properties`:

```properties
status.PAID=Đã thanh toán
receipt.summary=Đơn {0}: {1} — {2}
```

File `LocalizedStatusDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizedStatusDemo {
    static String receipt(String orderId, String amountText,
            Locale locale) {
        ResourceBundle messages =
                ResourceBundle.getBundle("Labels", locale);
        String status = messages.getString("status.PAID");
        String pattern = messages.getString("receipt.summary");

        MessageFormat messageFormat =
                new MessageFormat(pattern, locale);
        return messageFormat.format(
                new Object[] {orderId, amountText, status});
    }

    public static void main(String[] args) {
        String id = "ORD-42";
        String currencyText = "1234.50 EUR";
        System.out.println(receipt(
                id, currencyText, Locale.ENGLISH));
        System.out.println(receipt(
                id, currencyText, Locale.forLanguageTag("vi-VN")));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 LocalizedStatusDemo.java
java LocalizedStatusDemo
```

Kết quả:

```text
Order ORD-42: 1234.50 EUR — Paid
Đơn ORD-42: 1234.50 EUR — Đã thanh toán
```

Ở đây `currencyText` cố tình dùng một chuỗi minh họa đã được tạo bên ngoài, để tập trung vào **nội dung bản dịch**. Trong sản phẩm, giá trị nên đi từ `Money` qua `NumberFormat` theo locale, rồi mới được chèn vào message.

**Lưu ý quan trọng về `MessageFormat`:**

- Message pattern là **cả câu**, để người dịch đổi thứ tự các placeholder `{0}`, `{1}`, `{2}` theo ngữ pháp.
- Trong pattern của `MessageFormat`, dấu nháy đơn `'` có quy tắc escaping riêng; muốn hiển thị dấu nháy đơn literal nhiều khi cần viết `''`. Không gán mọi chuỗi tài nguyên qua `MessageFormat` nếu chưa hiểu quy tắc quote.
- Với số nhiều phức tạp theo locale, Java SE `MessageFormat` cơ bản không phải engine hỗ trợ đầy đủ mọi CLDR plural categories; cân nhắc ICU MessageFormat hoặc giải pháp i18n phù hợp sản phẩm.
- Bản dịch là **dữ liệu ngôn ngữ**, không phải kênh chứa logic chuyển trạng thái, SQL, biểu thức tính tiền hay thứ tự hành động nghiệp vụ.
- Với ứng dụng web, dữ liệu đưa vào HTML còn cần escaping theo ngữ cảnh render (text node, attribute, URL...). `MessageFormat` không tự bảo vệ khỏi HTML/script injection.

## 8. Ngày giờ: `Instant` không phải chuỗi ngày theo ngôn ngữ

Một giao dịch hoàn thành tại:

```text
2026-10-28T01:30:00Z
```

Đây là một **thời điểm tuyệt đối**. Người dùng ở Tokyo xem thấy giờ khác người dùng ở UTC, nhưng `Instant` phải là **cùng một instant**.

Không nên lưu:

```text
"28/10/2026 08:30"
```

mà không có offset/timezone và schema, rồi giả định có thể suy ra instant bất biến. `28/10/2026` có thể là format ngày Việt Nam; nơi khác có thể dùng `10/28/2026`. Nếu có DST, cùng giờ địa phương có thể không tồn tại hoặc lặp.

### 8.1. Các kiểu ngày giờ theo ý nghĩa nghiệp vụ

| Nhu cầu | Java type thường phù hợp | Lưu ý |
| --- | --- | --- |
| Timestamp giao dịch đã xảy ra | `Instant` | Một điểm thời gian tuyệt đối |
| Ngày sinh, ngày nghỉ (không cần giờ) | `LocalDate` | Không chuyển thành instant khi chưa có zone/ngữ nghĩa |
| Giờ mở cửa hàng lặp hằng ngày | `LocalTime` + zone/schedule policy | Không tương đương timestamp |
| Lịch hẹn lúc 9:00 ở một khu vực | `LocalDateTime` + `ZoneId` và chính sách DST | Zone có quy tắc thay đổi |
| Thời điểm đã gắn múi giờ | `ZonedDateTime` | Mang zone ID; cân nhắc lưu instant và zone riêng |
| Thời điểm gửi API có offset | `OffsetDateTime` nếu schema yêu cầu | Offset không luôn giữ region zone ID |

`DateTimeFormatter` biến đối tượng thời gian thành chuỗi. Nếu hiển thị theo locale, có thể dùng `ofLocalizedDateTime` với `withLocale` và `withZone` khi định dạng một `Instant`. Nếu cần timestamp máy, dùng `Instant.toString()`/`DateTimeFormatter.ISO_INSTANT` thay vì localized output.

### Ví dụ Java 17+: cùng một `Instant`, nhiều giờ hiển thị

Tạo `InstantPresentationDemo.java`:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class InstantPresentationDemo {
    public static void main(String[] args) {
        Instant paidAt =
                Instant.parse("2026-10-28T01:30:00Z");

        DateTimeFormatter format =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm XXX", Locale.ROOT);

        System.out.println("stored: " + paidAt);
        System.out.println("UTC: " + format
                .withZone(ZoneId.of("UTC"))
                .format(paidAt));
        System.out.println("Tokyo: " + format
                .withZone(ZoneId.of("Asia/Tokyo"))
                .format(paidAt));
        System.out.println("unchanged: "
                + paidAt.equals(Instant.parse(
                        "2026-10-28T01:30:00Z")));
    }
}
```

```bash
javac InstantPresentationDemo.java
java InstantPresentationDemo
```

```text
stored: 2026-10-28T01:30:00Z
UTC: 2026-10-28 01:30 Z
Tokyo: 2026-10-28 10:30 +09:00
unchanged: true
```

Đây là pattern cố định để có stdout rõ ràng. Trong UI đa ngôn ngữ, dùng `DateTimeFormatter.ofLocalizedDateTime(style).withLocale(locale).withZone(zone)` để lấy quy ước người dùng, rồi **không dùng chuỗi kết quả để lưu lại instant**.

`DateTimeFormatter` là immutable; `withZone` trả một formatter mới, không sửa bản cũ. Ngược lại, nhiều formatter cũ như `SimpleDateFormat` và `NumberFormat` mutable, không nên chia sẻ giữa các thread đang thay cấu hình.

## 9. Parse input: lớp riêng chuyển text thành giá trị nghiệp vụ

Khi người dùng nhập `1.234,50` trong giao diện `de-DE`, đây là **chuỗi của một form nhập liệu**. Domain không nên tự phân tích dấu phẩy/dấu chấm. Một lớp adapter/presenter/parser cần biết locale rồi tạo `BigDecimal`:

```text
Input UI "1.234,50" + locale de-DE
           |
           v
Locale number parser + full-input validation
           |
           v
BigDecimal("1234.50")
           |
           v
Domain validation: >=0, currency/scale/range...
           |
           v
Money(amount=1234.50, currency=EUR)
```

### Vì sao không parse ngay trong domain?

Domain model như `Money` có thể được tạo từ REST API, CSV import, database, batch job, desktop UI hoặc form web. Nếu nó chấp nhận một chuỗi theo locale mặc định của JVM, các nguồn khác nhau vô tình phải tuân một format do máy chủ chọn. Tách parser ở **ranh giới đầu vào** giúp domain nhất quán, còn mỗi input channel có adapter riêng.

### Ví dụ Java 17+: parse đúng locale và kiểm tra toàn bộ input

Tạo `LocalizedNumberInputDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocalizedNumberInputDemo {
    static BigDecimal parseAmount(String text, Locale locale) {
        if (text == null || text.isEmpty()) {
            throw new IllegalArgumentException("Empty amount");
        }

        NumberFormat base =
                NumberFormat.getNumberInstance(locale);
        if (!(base instanceof DecimalFormat decimal)) {
            throw new IllegalStateException(
                    "DecimalFormat is required");
        }
        decimal.setParseBigDecimal(true);

        ParsePosition pos = new ParsePosition(0);
        Number number = decimal.parse(text, pos);

        if (!(number instanceof BigDecimal exact)
                || pos.getIndex() != text.length()) {
            throw new IllegalArgumentException(
                    "Invalid localized amount");
        }
        return exact;
    }

    public static void main(String[] args) {
        Locale german = Locale.GERMANY;
        BigDecimal result =
                parseAmount("1.234,50", german);

        System.out.println("value: "
                + result.toPlainString());
        System.out.println("scale: " + result.scale());

        try {
            parseAmount("1.234,50oops", german);
        } catch (IllegalArgumentException ex) {
            System.out.println("suffix rejected");
        }

        try {
            parseAmount("1.234,50", Locale.US);
        } catch (IllegalArgumentException ex) {
            System.out.println("wrong locale rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 LocalizedNumberInputDemo.java
java LocalizedNumberInputDemo
```

```text
value: 1234.50
scale: 2
suffix rejected
wrong locale rejected
```

**Điểm quan trọng:**

- `DecimalFormat` với `setParseBigDecimal(true)` giữ giá trị decimal hữu hạn và scale theo chuỗi được parse.
- `NumberFormat.parse(String)` thông thường có thể chấp nhận **một tiền tố**; dùng `ParsePosition.getIndex()==text.length()` để phát hiện phần thừa.
- `NaN`/vô cực có thể trả `Double`, không phải `BigDecimal`; `instanceof BigDecimal` giúp từ chối các giá trị không phù hợp domain tiền.
- Việc parse hết chuỗi **chưa chứng minh grouping đúng quy tắc nghiêm ngặt**. `DecimalFormat` có thể chấp nhận nhóm sai vị trí; nếu cần field tiền strict, bổ sung lexical validation theo schema, scale, miền giá trị, giới hạn độ dài.
- Không thay `Locale.setDefault(...)` theo từng request; truyền locale đã xác nhận từ profile/session/input format.
- Nếu currency được chọn riêng trên form, parser số không được tự đoán currency từ mã ngôn ngữ.

## 10. Lưu trữ: dữ liệu canonical, không phải snapshot của text UI

**Canonical data** là giá trị có schema đủ để đọc lại mà không phải đoán locale.

| Domain value | Gợi ý persistence/API | Không nên lưu làm source of truth |
| --- | --- | --- |
| `BigDecimal("1234.50")` | Cột DECIMAL/NUMERIC có precision/scale rõ, hoặc chuỗi decimal không grouping | `"1.234,50"` theo locale Đức |
| `Currency EUR` | `"EUR"` trong cột/code ISO được thống nhất | `"€"` hoặc `"Euro"` |
| `Instant` | Timestamp có hợp đồng UTC/offset, ISO 8601 | `"28/10/2026 08:30"` không zone |
| `OrderStatus.PAID` | Code `"PAID"` hoặc enum mapping theo version schema | `"Đã thanh toán"` |
| `Locale vi-VN` | BCP 47 language tag `"vi-VN"` | `"Tiếng Việt"` làm ID |
| `ZoneId` | ID vùng như `"Asia/Ho_Chi_Minh"` | Tên hiển thị vùng giờ |
| Mã sản phẩm | Chuỗi mã có quy tắc riêng | `NumberFormat` đã thêm grouping |

**Ghi chú về JSON:** JSON number không tự bảo đảm mọi consumer sẽ giữ precision/scale như `BigDecimal`; với số tiền chính xác, cần hợp đồng rõ kiểu và cách biểu diễn (ví dụ decimal string hoặc format JSON decimal thống nhất cho hệ thống) thay vì tin mọi client parse số bằng decimal.

**Ghi chú về JDBC/DB:** scale khi lưu `BigDecimal` phụ thuộc schema cột và driver. Cột DECIMAL(12,2) có các quy tắc giới hạn, rounding/overflow cần test; đừng chỉ để frontend hiển thị hai chữ số rồi tin dữ liệu đã hợp lệ.

### Ví dụ Java 17+: dữ liệu canonical và giá trị khôi phục

Tạo `CanonicalDataDemo.java`:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;
import java.util.Locale;

public class CanonicalDataDemo {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");
        Currency currency = Currency.getInstance("EUR");
        Instant paidAt =
                Instant.parse("2026-10-28T01:30:00Z");

        String storedAmount = amount.toPlainString();
        String storedCurrency = currency.getCurrencyCode();
        String storedInstant = paidAt.toString();

        BigDecimal amountBack = new BigDecimal(storedAmount);
        Currency currencyBack =
                Currency.getInstance(storedCurrency);
        Instant paidAtBack = Instant.parse(storedInstant);

        System.out.println("amount: " + storedAmount);
        System.out.println("currency: " + storedCurrency);
        System.out.println("instant: " + storedInstant);
        System.out.println("amount equals: "
                + amount.equals(amountBack));
        System.out.println("currency equals: "
                + currency.equals(currencyBack));
        System.out.println("instant equals: "
                + paidAt.equals(paidAtBack));
    }
}
```

```bash
javac CanonicalDataDemo.java
java CanonicalDataDemo
```

```text
amount: 1234.50
currency: EUR
instant: 2026-10-28T01:30:00Z
amount equals: true
currency equals: true
instant equals: true
```

Với `BigDecimal` có scale âm, `toPlainString()` không bảo toàn mọi giá trị scale khi dựng lại; nếu phải giữ nguyên scale cho **mọi** số, dùng `toString()` hoặc lưu `unscaledValue + scale` theo schema. Ví dụ này có scale 2 và khôi phục đúng `equals`.

Đừng nhầm việc lưu **bản ghi văn bản đã được ban hành** với lưu **giá trị domain**: một hóa đơn PDF đã phát hành có thể cần lưu snapshot để audit; bản domain vẫn nên lưu amount, currency, date, line items và version của các quy tắc nội dung.

## 11. Domain invariant phải được kiểm tra trước presentation

Chẳng hạn, use case bán hàng có thể quy định:

- quantity phải nguyên dương;
- unit price không âm;
- tổng tiền = unit price × quantity;
- currency của tất cả dòng phải tương thích;
- rounding thuế hoặc chiết khấu dùng quy tắc cụ thể;
- timestamp là thời điểm hợp lệ từ đồng hồ/service.

Những quy tắc này **không thay đổi khi người dùng đổi locale**. Đừng xem chuỗi `"1,23"` hay `"1.23"` là giá trị số khi đang tính toán; đó là biểu diễn đầu vào/đầu ra.

### Java 17+: domain record tính tổng không phụ thuộc locale

Tạo `OrderDomainDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public class OrderDomainDemo {
    record OrderLine(BigDecimal unitPrice,
                     int quantity, Currency currency) {
        OrderLine {
            Objects.requireNonNull(unitPrice);
            Objects.requireNonNull(currency);
            if (unitPrice.signum() < 0 || quantity <= 0) {
                throw new IllegalArgumentException(
                        "Invalid order line");
            }
        }

        BigDecimal total() {
            return unitPrice.multiply(
                    BigDecimal.valueOf(quantity));
        }
    }

    public static void main(String[] args) {
        OrderLine line = new OrderLine(
                new BigDecimal("411.50"),
                3, Currency.getInstance("EUR"));

        System.out.println("quantity: " + line.quantity());
        System.out.println("total: " + line.total().toPlainString());
        System.out.println("currency: "
                + line.currency().getCurrencyCode());
    }
}
```

```bash
javac OrderDomainDemo.java
java OrderDomainDemo
```

```text
quantity: 3
total: 1234.50
currency: EUR
```

Vì code tính trên `BigDecimal`, kết quả không phụ thuộc dấu thập phân của `vi-VN` hay `de-DE`. `OrderLine` là mô hình **đơn giản**: hệ thống thực còn phải xác định tax, discount, quantity units, rounding, currency conversion và chính sách khoản tiền không âm một cách rõ ràng.

### Không dùng label để quyết định trạng thái

**Sai:**

```java
if (statusLabel.equals("Paid")) { /* xử lý đơn */ }
```

**Đúng về tầng trách nhiệm:**

```java
if (order.status() == OrderStatus.PAID) {
    // xử lý nghiệp vụ không phụ thuộc ngôn ngữ
}
```

Đây là **mã minh họa** có biến `order` và enum `OrderStatus` theo domain. Label `"Paid"`/`"Đã thanh toán"` chỉ được tạo sau khi use case biết trạng thái.

## 12. Locale, timezone, currency và ngôn ngữ giao diện không đồng nhất

Một người dùng có thể chọn:

```text
display language: en-US
number format:    de-DE
time zone:        Asia/Ho_Chi_Minh
transaction money: USD
```

Không có mâu thuẫn. Người đó có thể thích tiếng Anh, nhập số theo quy ước Đức, xem giờ Việt Nam và thanh toán USD. Ứng dụng phải xác định **từng thuộc tính** theo hợp đồng sản phẩm; đừng dùng một `Locale` để đoán mọi preference.

| Thuộc tính | Nguồn khả dĩ | Ý nghĩa |
| --- | --- | --- |
| Message locale | Profile, thiết lập ứng dụng, nội dung `Accept-Language` được hỗ trợ | Chọn bản dịch/resource |
| Number input/output locale | User preference hoặc form locale được xác định | Parser/formatter số |
| Zone ID | Profile, đặt lịch, vùng của sự kiện | Quy tắc ngày giờ địa phương |
| Currency code | Đơn hàng/price list/hợp đồng giao dịch | Đồng tiền nghiệp vụ |
| Measurement unit | Domain/schema/user preference được chuyển đổi có kiểm soát | kg/lb, km/mi, °C/°F |
| Calendar system | Quy ước nghiệp vụ hoặc lựa chọn presentation | ISO/Buddhist/Japanese calendar... |

**Không dùng `Locale.getDefault()` hay `TimeZone.getDefault()` của server như sở thích của request.** Hai default này là cấu hình của JVM/process và có thể khác người dùng, không an toàn khi đổi liên tục để phục vụ nhiều request song song.

Nếu một ứng dụng nội bộ thực sự chỉ có một locale/zone cố định, vẫn nên đưa lựa chọn thành **configuration tường minh**, để có thể kiểm thử và di trú.

## 13. Thiết kế DTO và API: text chỉ là một projection

Một response phục vụ máy và response phục vụ UI có thể cần hợp đồng khác nhau.

### 13.1. API có giá trị chuẩn

Ví dụ JSON minh họa:

```json
{
  "orderId": "ORD-2026-042",
  "status": "PAID",
  "amount": "1234.50",
  "currency": "EUR",
  "paidAt": "2026-10-28T01:30:00Z"
}
```

`amount` ở đây là **decimal string theo schema**, không phải số có dấu nhóm; `paidAt` là ISO instant. Consumer có thể tạo bản dịch theo locale của mình, và API không bị ràng buộc phải giữ dấu ngăn cách tiếng Anh hay tiếng Việt.

### 13.2. UI projection có thể thêm label

Ví dụ một view model có thể chứa:

```json
{
  "orderId": "ORD-2026-042",
  "statusCode": "PAID",
  "statusLabel": "Đã thanh toán",
  "formattedTotal": "1.234,50 €",
  "formattedPaidAt": "28/10/2026 08:30"
}
```

Các trường `statusLabel`, `formattedTotal`, `formattedPaidAt` là **presentation data**, phụ thuộc locale, zone và quy tắc hiện hành. Không gửi chúng trở lại API như dữ liệu có thẩm quyền. Nếu backend cung cấp view-model localized để phục vụ UI, vẫn giữ **domain model và serialization ổn định** ở tầng nghiệp vụ.

### Tránh format hai lần

Nếu backend đã format số bằng de-DE và frontend lại gọi formatter en-US với chuỗi ấy, output dễ sai hoặc bị "double-format". Tốt nhất quyết định rõ **formatter thuộc server hay client**; khi client chịu trách nhiệm, gửi raw amount có kiểu/schema và locale preference. Khi server chịu trách nhiệm, gửi display text đi kèm code/value thật nếu client cần tương tác/submit.

## 14. Resource key không phải dữ liệu nghiệp vụ

Resource key như `status.PAID` hoặc `error.order.notFound` là **địa chỉ thông điệp**. Nó nên ổn định trong code và có thể kiểm soát qua resource bundles. Nhưng không nên dùng một đoạn bản dịch làm key:

```java
// Không an toàn khi thay ngôn ngữ:
messageMap.get("Đơn hàng không tồn tại");
```

Hợp lý hơn:

```java
messages.getString("error.order.notFound");
```

Tên key mô tả ý nghĩa và nơi dùng, còn content thực nằm trong resource theo locale. Nếu wording đổi từ `"Không tìm thấy đơn hàng"` sang `"Đơn hàng không tồn tại"`, chương trình vẫn tra đúng key.

### Thông báo lỗi phải tách code và message

Ví dụ domain/service trả:

```text
errorCode = ORDER_NOT_FOUND
orderId   = ORD-2026-042
```

Lớp presentation có thể tạo:

```text
vi-VN: Không tìm thấy đơn hàng ORD-2026-042.
en-US: Order ORD-2026-042 was not found.
```

API client cần xử lý lỗi theo **error code**, không so chuỗi message đang hiển thị. Message có thể thay vì cải tiến cách viết hoặc thay đổi locale mà không phá logic.

## 15. UI chịu trách nhiệm bố cục, không phải domain

Một bản dịch dài hơn có thể khiến nút hoặc nhãn cần nhiều không gian. **Đó là trách nhiệm của giao diện**, không phải lý do thay domain data.

Lớp UI nên:

- cho label/container co giãn và xuống dòng theo hệ chữ/Unicode;
- chọn font, line-height, alignment, khả năng truy cập và overflow policy;
- hỗ trợ RTL/BiDi khi locale yêu cầu;
- giữ nguyên giá trị và trạng thái underlying model khi người dùng đổi ngôn ngữ;
- không cắt tên sản phẩm/đơn vị tiền tệ ở tầng domain chỉ để vừa layout.

Chuỗi `"Đã thanh toán"` có thể bị tạm rút gọn thành nhãn ngắn đã được biên tập riêng trong giao diện hẹp, nhưng `OrderStatus.PAID` vẫn như cũ. Nếu cần lưu đúng văn bản một bản chứng từ đã phát hành, đó là **yêu cầu audit/snapshot** tách với dữ liệu domain.

## 16. Những phản ví dụ khiến ứng dụng bị phụ thuộc ngôn ngữ

### 16.1. Lưu số đã format vào database

```java
String stored = NumberFormat
        .getNumberInstance(Locale.GERMANY)
        .format(new BigDecimal("1234.50"));
```

Chuỗi có thể là `"1.234,5"` (không nhất thiết giữ số 0 cuối) và **không phải decimal canonical**. Sau nâng cấp locale provider, phiên bản JDK, hoặc khi một process đọc bằng locale khác, `stored` có thể khó parse đúng.

**Sửa:** lưu DECIMAL/numeric hoặc decimal string với schema; format khi render.

### 16.2. Quyết định theo text nút bấm

```java
if (button.getText().equals("Delete")) {
    deleteRecord();
}
```

Nếu label thành `"Xóa"`, logic không còn hoạt động. **Sửa:** gán action/command ID hoặc event handler có ý nghĩa nghiệp vụ, không suy action từ chữ trên nút.

### 16.3. Dùng chuỗi ngày theo locale làm ID

```text
"10/11/2026"
```

Chuỗi có thể mang nghĩa ngày 10 tháng 11 hoặc ngày 11 tháng 10 tùy vùng. **Sửa:** truyền `LocalDate` theo schema ISO khi đó là ngày, hoặc `Instant` khi đó là một timestamp tuyệt đối.

### 16.4. Tự đổi default locale cho từng request

```java
Locale.setDefault(userLocale);
TimeZone.setDefault(userZone);
```

Đây là thay đổi ở phạm vi JVM, không phải context của riêng thread/request. Trong server đa người dùng, dễ gây race condition. **Sửa:** truyền `Locale`/`ZoneId` vào từng formatter và use case; dùng dependency injection hoặc request context có ownership rõ.

### 16.5. Dùng display name làm khóa

```text
"Germany"  ← tên quốc gia tiếng Anh
"Deutschland" ← tên tiếng Đức
```

Cả hai cùng nói tới mã quốc gia DE. Lưu tên hiển thị làm foreign key khiến thay ngôn ngữ phá liên kết. **Sửa:** lưu mã domain rõ, trình bày tên theo display locale.

### 16.6. Dùng `String.equals` cho khái niệm số hoặc ngày

```java
"1,234.50".equals("1.234,50") // false
```

Kết quả đúng về so chuỗi nhưng không nói được hai biểu diễn có cùng **giá trị số học** hay không. Phải parse đúng locale thành `BigDecimal` rồi so theo giá trị. Với `BigDecimal`, `equals` còn xét **scale**; `compareTo(...)==0` so trị số. Chọn phương thức so phù hợp nghiệp vụ.

## 17. Thiết kế boundary rõ cho hệ thống nhiều kênh

Một hệ thống có thể có web, mobile, batch import, CLI và REST. Mỗi kênh không nhất thiết cùng locale nhưng phải tạo ra **cùng kiểu dữ liệu domain**.

```text
             Web form de-DE
               "1.234,50"
                     |
               Input adapter
                     |
Batch CSV canonical   |       REST JSON decimal string
     "1234.50"        |              "1234.50"
          \           |            /
           \          v           /
             BigDecimal(1234.50)
                     |
                Domain service
                     |
              Persistence decimal
                     |
               Presenter
              /     |     \
          de-DE   en-US   vi-VN
```

**Thiết kế dễ kiểm thử:** parser adapter có thể được test bằng các cặp `input + locale`; domain service test bằng đối tượng có kiểu, **không cần cài locale JDK**; presenter test bằng `domain + locale + zone`. Lỗi có thể được khoanh vùng theo ranh giới rõ.

### Có cần mọi input đều giữ raw string?

Không nhất thiết. Với một field tiền giao dịch, sau parse đúng và validation domain, có thể chỉ lưu giá trị số và currency. Nếu nghiệp vụ cần audit việc người dùng đã nhập chính xác dạng nào, lưu raw input **riêng** cùng nguồn, thời điểm, version policy và quy tắc bảo mật. Đừng để raw form string trở thành nguồn tính toán.

## 18. Kiểm thử: đổi locale, bất biến domain

Đừng chỉ snapshot từng chuỗi UI. Hãy kiểm tra cả **bất biến nghiệp vụ** và **sự thay đổi trình bày được mong đợi**.

### 18.1. Test miền dữ liệu

- Tổng tiền không đổi khi locale hiển thị đổi.
- Mã currency không đổi, dù symbol dịch khác.
- Status code không đổi, dù label dịch khác.
- Timestamp epoch không đổi, dù giờ địa phương khác.
- Không có phép toán nghiệp vụ nào cần `Locale.getDefault()`.

### 18.2. Test lớp parser

- Input hợp lệ theo locale tương ứng parse thành đúng `BigDecimal`.
- Input có suffix, ký hiệu lạ hoặc locale sai bị từ chối.
- Validation kiểm soát precision, scale, giới hạn và grouping nghiêm ngặt nếu cần.
- Không tự xem `parse(String)` trả number là parse toàn bộ input.
- Không dùng đồng thời mutable `NumberFormat` giữa threads.

### 18.3. Test lớp presentation

- Thông điệp đúng `ResourceBundle` và placeholder được đặt đúng.
- Nhãn dài có thể xuống dòng, phóng to, được screen reader đọc đầy đủ.
- Có test cho locale CJK, RTL, các dấu nhóm Unicode khác ASCII và font fallback.
- Thay JDK/CLDR có thể đổi chuỗi hiển thị; chỉ golden test **literal** ở nơi hợp đồng yêu cầu.
- UI không dùng label để làm khóa hoặc quyết định nghiệp vụ.

### Java 17+: một kiểm thử bất biến dạng executable

Tạo file `DomainSeparationCheck.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Currency;
import java.util.Locale;

public class DomainSeparationCheck {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");
        Currency currency = Currency.getInstance("EUR");
        Instant created = Instant.parse("2026-10-28T01:30:00Z");

        String en = displayMoney(amount, currency, Locale.US);
        String de = displayMoney(amount, currency, Locale.GERMANY);

        if (en.equals(de)) {
            throw new AssertionError("Expected two display styles");
        }
        if (amount.compareTo(new BigDecimal("1234.50")) != 0
                || !currency.getCurrencyCode().equals("EUR")) {
            throw new AssertionError("Domain changed");
        }

        DateTimeFormatter fmt =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm", Locale.ROOT);
        String utc = fmt.withZone(ZoneId.of("UTC")).format(created);
        String tokyo = fmt.withZone(
                ZoneId.of("Asia/Tokyo")).format(created);
        if (utc.equals(tokyo)) {
            throw new AssertionError("Expected local times to differ");
        }
        if (!created.equals(
                Instant.parse("2026-10-28T01:30:00Z"))) {
            throw new AssertionError("Instant changed");
        }
        System.out.println("domain invariant: PASS");
        System.out.println("display variation: PASS");
    }

    static String displayMoney(
            BigDecimal amount, Currency currency, Locale locale) {
        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(locale);
        formatter.setCurrency(currency);
        return formatter.format(amount);
    }
}
```

```bash
javac DomainSeparationCheck.java
java DomainSeparationCheck
```

```text
domain invariant: PASS
display variation: PASS
```

Bài test này xác nhận **cùng một domain value** vẫn đúng sau khi render theo nhiều locale; không kiểm tra nguyên văn ký hiệu/vị trí tiền theo từng phiên bản CLDR. Nếu sản phẩm có contract bắt buộc về chuỗi hiển thị, viết thêm presentation snapshot test có version/provider rõ.

## 19. Đổi locale lúc runtime: cập nhật presenter, không tạo lại domain

Một yêu cầu phổ biến là đổi ngôn ngữ giao diện khi ứng dụng đang mở.

Luồng tốt:

1. Đổi **UI/display locale** trong preference hoặc context của phiên làm việc.
2. Presenter đọc lại resource và format lại các trường domain theo locale/zone mới.
3. UI update text, hướng bố cục và wrapping.
4. Không sửa các field như `order.total`, `order.currency`, `paidAt`, `status`.
5. Nếu form đang có **text chưa submit**, phải xử lý riêng: chuỗi nhập đang theo locale cũ có thể không còn parse đúng với locale mới. Có thể lưu **giá trị parsed** độc lập trước khi re-render, hoặc giữ locale-source cho input cho đến khi người dùng hoàn tất; không âm thầm parse bằng locale mới.

Không gọi `Locale.setDefault(locale)` của JVM để đổi ngôn ngữ một phiên web. Locale nên là phần của UI/session/request context, có nguồn rõ và không gây trạng thái toàn cục.

### Lưu ý khi dữ liệu thay đổi trong khi đang chỉnh sửa

Không ép một chuỗi form `"1.234,50"` đang nhập dở thành `"1,234.50"` chỉ bằng thay ký tự: có thể có separator sai, dấu thập phân chưa nhập xong, selection/caret position và lỗi validation. Thiết kế form nên xác định rõ trạng thái **raw draft**, **parsed value** và **committed domain value**.

## 20. Tách dữ liệu nghiệp vụ còn giúp tăng khả năng truy cập và bảo trì

Các lợi ích không chỉ giới hạn bản địa hóa:

- **Dễ test:** domain service chạy với dữ liệu có kiểu, không cần hệ thống resource bundle.
- **Dễ dịch:** người dịch chỉ chỉnh thông điệp; không làm đổi enum/ID hoặc phép tính.
- **Dễ đổi nền tảng:** web, Android, desktop nhận cùng dữ liệu canonical, tự chọn renderer.
- **Dễ migration:** nâng JDK/CLDR và chỉnh bản dịch không phá schema số/ngày.
- **Dễ truy xuất:** search key/domain ID ổn định; label UI không trở thành khóa.
- **Dễ audit:** lưu timestamp, amount, currency, trạng thái và phiên bản quy tắc tính; snapshot UI có thể được lưu độc lập khi cần.
- **Dễ đáp ứng accessibility:** UI lựa chọn văn bản đầy đủ, trình đọc màn hình và bố cục thay thế mà domain không bị cắt ngắn.
- **Dễ bảo mật:** output encoding và escaping diễn ra ở presentation boundary đúng ngữ cảnh, thay vì để bản dịch tác động đến cú pháp HTML/SQL.

Tuy nhiên, **không phải mọi thứ thuộc presentation đều tự do thay đổi không giới hạn**. Một email giao dịch hoặc hóa đơn pháp lý được phát hành có thể phải lưu nguyên bản đã gửi. Khi đó **snapshot hiển thị là một artifact nghiệp vụ riêng có version**, còn dữ liệu nền vẫn có cấu trúc để tính toán, đối soát và phân tích.

## 21. Anti-pattern và cách thay thế

| Anti-pattern | Vì sao nguy hiểm? | Thiết kế thay thế |
| --- | --- | --- |
| `String total = "1.234,50 €"` làm amount | Không còn type decimal/currency rõ | `Money(BigDecimal, Currency)` |
| `double` cho mọi khoản tiền | Có thể sai số nhị phân | `BigDecimal` + rounding domain |
| Lưu ngày `"28/10/2026"` rồi tự đoán | Mơ hồ locale/timezone | `LocalDate`/`Instant` theo schema |
| Dùng `statusLabel` làm trạng thái | Đổi bản dịch phá logic | Enum/code ổn định |
| Dùng `Currency.getSymbol` làm currency ID | Ký hiệu không duy nhất | ISO currency code |
| Dùng `Locale.getDisplayName` làm khóa | Tên hiển thị đổi theo locale/CLDR | BCP 47 tag/code |
| Nối câu từ các mảnh được dịch | Trật tự ngữ pháp bị cố định | Cả message với placeholders |
| Dùng `Locale.setDefault` theo request | Race trên JVM default | Truyền locale tường minh |
| Parse input trong domain theo server locale | Adapter bị lẫn nghiệp vụ | Localized input parser trước domain |
| `parse(String)` không kiểm tra suffix | Nhận số sai hoặc dữ liệu thừa | `ParsePosition` và validation |
| UI trả chuỗi formatted về API | Double-format hoặc sai parse | Gửi canonical value theo schema |
| Hardcode text width theo tiếng Anh | Bản dịch bị cắt | UI responsive/wrapping |
| Dùng chung `NumberFormat` mutable static | Rò currency/locale qua threads | Tạo formatter riêng/lifecycle rõ |
| Mong `format → parse` giữ số gốc | Rounding/scale/pattern có thể mất | Lưu domain, không lưu display |
| Test chỉ so literal localized output | CLDR nâng cấp gây lỗi giả | Test domain invariants và display contract riêng |
| Chuyển locale khi form chưa commit rồi parse lại | Input thay nghĩa | Quản lý raw draft/parsed/domain riêng |

## 22. Bài tập tự kiểm tra

1. **Nếu cùng số tiền hiển thị `€1,234.50` và `1.234,50 €`, đâu là phần phải giống nhau?** `BigDecimal amount=1234.50` và `Currency EUR`.
2. **Tại sao không dùng `"Đã thanh toán"` làm trạng thái database?** Vì đây là bản dịch; dùng code `PAID` độc lập locale.
3. **`NumberFormat.getCurrencyInstance(Locale.GERMANY)` có tự biết giao dịch là USD không?** Không. Phải truyền `Currency.getInstance("USD")` từ domain.
4. **`BigDecimal` có giải quyết mọi rounding tiền tệ không?** Không; domain phải xác định quy tắc rounding/scale/precision.
5. **Đổi timezone hiển thị có được sửa `Instant` gốc không?** Không; chỉ thay biểu diễn giờ địa phương.
6. **`Locale` và `ZoneId` có phải cùng một thiết lập không?** Không; ngôn ngữ/quy ước và múi giờ là hai chiều độc lập.
7. **Một user ở Việt Nam thích tiếng Anh nhưng thanh toán EUR có hợp lệ không?** Có; locale giao diện, zone, currency độc lập.
8. **Để chuyển `"1.234,50"` thành tiền domain nên làm gì?** Parse theo `de-DE`, kiểm tra hết input và validation rồi tạo `BigDecimal`/`Money`.
9. **Vì sao không dùng `Double.parseDouble` để đọc mọi localized form?** Nó không hiểu các dấu theo locale và dùng kiểu nhị phân xấp xỉ.
10. **Nếu resource dịch thay `Paid` thành `Payment received`, có cần migration `OrderStatus` không?** Không, khi code trạng thái độc lập.
11. **API gửi `"1.234,50"` không kèm locale có vấn đề gì?** Chuỗi mơ hồ, phụ thuộc người nhận; nên dùng schema decimal canonical.
12. **Nếu hóa đơn PDF phát hành phải lưu đúng câu chữ, có mâu thuẫn với tách domain và UI không?** Không; lưu snapshot artifact riêng cùng domain data.
13. **`MessageFormat` có nhiệm vụ quyết định số tiền?** Không; nó tạo thông điệp từ giá trị đã có và formatter theo locale.
14. **Vì sao thay locale lúc form đang gõ cần cẩn trọng?** Text nháp có thể đang theo locale cũ; phải xử lý raw draft/parsed value riêng.
15. **Có nên dùng `Locale.getDefault()` trong server đa người dùng?** Không làm nguồn duy nhất của user context; truyền locale tường minh.
16. **Tại sao việc tách tầng giúp CI test ổn định?** Domain tests so giá trị, không bị ảnh hưởng bản dịch hoặc CLDR; presentation tests kiểm tra đúng trách nhiệm riêng.
17. **Trường hợp nào domain nên lưu cả zone và local time?** Lịch hẹn tương lai được định nghĩa theo giờ địa phương tại một vùng, có thể gặp DST gap/overlap.
18. **Khi nào cần lưu raw input?** Khi có yêu cầu audit/điều tra hoặc khôi phục chính xác cách nhập; lưu riêng theo retention và bảo mật.
19. **Vì sao UI không nên tự suy status từ text của nút?** Text có thể đổi theo locale hoặc A/B test; action ID/command thuộc logic.
20. **Điều cần bất biến khi người dùng đổi từ vi-VN sang en-US?** Giá trị, mã trạng thái, currency, timestamp, ID và các business rules.

## 23. Checklist trước khi triển khai

- [ ] Domain type có ý nghĩa rõ: amount, currency, quantity, date/instant, status code.
- [ ] Không có business rule phụ thuộc vào bản dịch cụ thể hoặc `getText()` của UI component.
- [ ] API/persistence dùng schema canonical, không dùng formatted number/date mặc định của JVM.
- [ ] Locale, zone, currency được chọn riêng theo nguồn dữ liệu và preference.
- [ ] UI messages đặt trong `ResourceBundle` hoặc hệ thống i18n tương đương, có key ổn định.
- [ ] Thông điệp chứa placeholder để người dịch thay trật tự theo ngữ pháp.
- [ ] Input parser hiểu locale của nguồn, kiểm tra toàn bộ chuỗi và validation domain.
- [ ] Parser và presenter có ownership rõ; mutable formatter không chia sẻ tùy tiện giữa threads.
- [ ] Chuyển locale không mutate domain; form input chưa commit được xử lý an toàn.
- [ ] UI hỗ trợ bản dịch dài, RTL, wrap và accessibility.
- [ ] Domain tests không phụ thuộc literal localized display strings.
- [ ] Presentation tests bao phủ locale, font, JDK/CLDR provider và timezone khi có yêu cầu.
- [ ] Artifact cần bảo toàn nguyên văn được lưu snapshot/version riêng, không thay thế domain data.

## Tài liệu tham khảo

- [Oracle Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): format/parse số và tiền theo locale, các phương thức factory, cấu hình currency.
- [Oracle Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): số decimal, `setParseBigDecimal` và cú pháp dấu phân nhóm.
- [Oracle Java SE 17 — Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html): currency code, symbol và trường dữ liệu tiền tệ.
- [Oracle Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): decimal exactness, scale/precision và rounding.
- [Oracle Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): lookup resource theo locale/fallback và classpath bundles.
- [Oracle Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html): placeholders, locale-specific subformats và quy tắc dấu nháy.
- [Oracle Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): định dạng ngày giờ theo locale/zone, immutable.
- [Oracle Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): điểm thời gian tuyệt đối.
- [Oracle Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): locale tags, default và localizations.
- [Unicode CLDR Project](https://cldr.unicode.org/): dữ liệu locale và thay đổi ở cách trình bày số/ngày theo phiên bản.
