# Đặt formatter riêng cho đối số trong MessageFormat và giới hạn với các kiểu java.time

`java.text.MessageFormat` kết hợp một mẫu câu với các đối số động như tên người dùng, số lượng, đơn giá hoặc ngày hẹn. Trong thực tế, **một mẫu câu có thể cần nhiều quy tắc định dạng riêng**, và **ngày giờ hiện đại trong `java.time` không hoàn toàn tương thích trực tiếp với các định dạng ngày kiểu cũ của `MessageFormat` trên Java 17/21**.

Bài này hướng dẫn gán `java.text.Format` cho **từng chỉ số đối số**, phân biệt chỉ số đối số với thứ tự xuất hiện của placeholder, lựa chọn locale, và ba cách xử lý `LocalDate`/`LocalDateTime`/`Instant`: **định dạng trước thành chuỗi**, **dùng `DateTimeFormatter.toFormat()`**, hoặc **chuyển sang `java.util.Date` khi thực sự cần tương tác với API cũ**. Các chương trình chạy được trên Java 17 trở lên; những cú pháp `MessageFormat` được nói đến là cú pháp có trên **Java 17 và Java 21**, tránh dựa vào phần mở rộng của JDK mới hơn.

## 1. Nhắc lại vị trí của MessageFormat

Một `MessageFormat` nhận **pattern** chứa các mục như `{0}`, `{1,number}`, `{2,date,short}` và một mảng đối số. Số trong dấu ngoặc nhọn là **argument index**, bắt đầu từ 0; nó trỏ vào mảng truyền cho `format(...)`.

```java
import java.text.MessageFormat;
import java.util.Locale;

MessageFormat message = new MessageFormat(
        "Hello {0}, you have {1,number,integer} items.",
        Locale.US);
String text = message.format(new Object[] {"Lan", 5});
```

Đây là **fragment trong một phương thức**, không phải file chạy độc lập. Giá trị `text` là:

```text
Hello Lan, you have 5 items.
```

Thông thường, `MessageFormat` tự tạo các subformatter cho `number`, `date`, `time` và `choice` theo pattern và locale. Nhưng có lúc lập trình viên cần một `DecimalFormat` riêng, một bộ định dạng mã hóa đơn hàng, hoặc `DateTimeFormatter` cho `LocalDate`. Khi ấy, thay subformatter của **chỉ số đối số** bằng `setFormatByArgumentIndex(...)` là lựa chọn quan trọng.

### Hai loại chỉ số rất dễ nhầm

Pattern sau có ba **format element** nhưng chỉ hai **argument index**:

```text
Mẫu:        "A={1}; B={0}; C={1}"
Vị trí 0:   {1}   -> argument index 1
Vị trí 1:   {0}   -> argument index 0
Vị trí 2:   {1}   -> argument index 1 (lặp)
```

- **Argument index**: số bên trong `{...}`, ví dụ `1` trong `{1}`. Giữ nghĩa của đối số dù bản dịch thay đổi thứ tự các placeholder.
- **Format-element index**: vị trí xuất hiện 0, 1, 2... của một biểu thức `{...}` khi quét pattern từ trái qua phải. Có thể đổi khi biên dịch viên sắp xếp lại câu.

Đó là lý do không thể tùy tiện thay `setFormatByArgumentIndex(1, ...)` bằng `setFormat(1, ...)`.

## 2. Bốn API gán formatter và ý nghĩa của chúng

| API | Chỉ số tương ứng | Hiệu lực khi chỉ số lặp |
| --- | --- | --- |
| `setFormatByArgumentIndex(int argIndex, Format format)` | **Argument index**, ví dụ số trong `{1}` | Thay formatter của **mọi** format element dùng cùng argument index |
| `setFormatsByArgumentIndex(Format[] formats)` | Chỉ số của mảng = argument index | Tương tự cho nhiều argument index |
| `setFormat(int elementIndex, Format format)` | Thứ tự **format element** trong pattern | Chỉ thay một lần xuất hiện cụ thể |
| `setFormats(Format[] formats)` | Thứ tự các format element trong pattern | Mỗi phần tử tác động đến một vị trí xuất hiện |

Hãy ưu tiên `setFormatByArgumentIndex` hoặc `setFormatsByArgumentIndex` khi **một đối số có một quy tắc định dạng thống nhất**, đặc biệt nếu các câu được dịch có thứ tự placeholder khác nhau.

Vẫn có trường hợp hợp lý để dùng `setFormat(elementIndex, ...)`: cùng một đối số phải xuất hiện ở hai chỗ theo **hai cách diễn đạt khác nhau**, ví dụ ngày ở tiêu đề dạng ngắn và trong phần nội dung dạng dài. Khi ấy bạn cần cố tình định dạng **từng lần xuất hiện**, nhưng phải hiểu rằng việc biên dịch viên đổi cấu trúc câu có thể thay đổi thứ tự element.

### `Format` là kiểu gì?

Các phương thức này nhận `java.text.Format` hoặc subclass; ví dụ:

- `NumberFormat`: số, tỷ lệ, tiền tệ; có thể chọn locale và currency tường minh.
- `DecimalFormat`: mẫu số như `"0000"`, `"#,##0.00"`.
- `DateFormat`/`SimpleDateFormat`: định dạng kiểu `java.util.Date` và API tương thích.
- `ChoiceFormat`: nhánh theo giá trị số trong mẫu câu đơn giản.
- Một adapter dạng `Format` tạo từ `DateTimeFormatter.toFormat()`: giúp nhận đối tượng `java.time.temporal.TemporalAccessor` trong Java 17/21.

**Chú ý:** `DateTimeFormatter` không phải subclass của `java.text.Format`. Không thể truyền trực tiếp `DateTimeFormatter.ISO_LOCAL_DATE` vào `setFormatByArgumentIndex`; phải dùng `toFormat()` hoặc một chiến lược chuyển đổi khác.

## 3. Ví dụ chạy được: đặt formatter theo argument index

Tạo file **`ArgumentFormatDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.MessageFormat;
import java.util.Locale;

public class ArgumentFormatDemo {
    public static void main(String[] args) {
        Locale locale = Locale.US;

        MessageFormat byArgument = new MessageFormat(
                "Order={1}, qty={0}, repeat={0}", locale);

        DecimalFormat quantity = new DecimalFormat(
                "0000", DecimalFormatSymbols.getInstance(locale));
        byArgument.setFormatByArgumentIndex(0, quantity);

        System.out.println(byArgument.format(
                new Object[] {7, "AB"}));

        MessageFormat byElement = new MessageFormat(
                "One={1}; plain={0}; again={1}", locale);
        DecimalFormat padded = new DecimalFormat(
                "000", DecimalFormatSymbols.getInstance(locale));
        byElement.setFormat(0, padded);

        System.out.println(byElement.format(
                new Object[] {7, 7}));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ArgumentFormatDemo.java
java ArgumentFormatDemo
```

Stdout:

```text
Order=AB, qty=0007, repeat=0007
One=007; plain=7; again=7
```

**Giải thích dòng 1:** hai placeholder `{0}` dùng cùng đối số `7`, nên `setFormatByArgumentIndex(0, quantity)` biến **cả hai** thành `0007`. Vị trí của `{0}` trong câu không quan trọng.

**Giải thích dòng 2:** `setFormat(0, padded)` chỉ thay **format element đầu tiên** của mẫu, chính là `{1}` đứng trong `One=...`. Lần xuất hiện thứ hai của `{1}` trong `again=...` vẫn theo định dạng mặc định, cho giá trị `7`. Việc đưa `1` vào `setFormat(0, ...)` không có nghĩa là “gán cho argument index 0”.

### Nếu bản dịch đảo trật tự placeholder thì sao?

Giả sử tiếng Anh dùng `"Qty={0}; code={1}"` còn tiếng Việt dùng `"Mã {1}; số lượng {0}"`. Với `setFormatByArgumentIndex(0, quantity)`, số lượng được định dạng như nhau dù vị trí xuất hiện trong câu khác nhau. Với `setFormat(0, quantity)`, format element đầu tiên của bản dịch tiếng Việt lại là `{1}` (mã hàng), có thể dẫn tới lỗi kiểu hoặc hiển thị sai.

Đó là lý do các API dựa trên **argument index** là lựa chọn mặc định phù hợp khi dữ liệu thông điệp đến từ nhiều `ResourceBundle`.

## 4. Gán nhiều formatter bằng mảng

`setFormatsByArgumentIndex(new Format[] {...})` cho phép gán quy tắc cho nhiều chỉ số:

```java
Format[] formats = {
    null,        // argument 0: không gán subformat tường minh
    null,        // argument 1
    priceFormat  // argument 2
};
message.setFormatsByArgumentIndex(formats);
```

Đây chỉ là **fragment**: `message` và `priceFormat` cần được khai báo ở ngữ cảnh chứa nó. Các vị trí trong mảng lần lượt là argument 0, 1, 2. Với một argument không xuất hiện trong pattern, phần tử tương ứng bị bỏ qua; với số phần tử ít hơn số argument được dùng, các chỉ số còn lại giữ nguyên format hiện có. Giá trị `null` là không dùng subformat chỉ định cho vị trí đó (lúc định dạng, `MessageFormat` dùng hành vi mặc định theo kiểu đối số).

**Chương trình chạy được — `MultipleFormatsDemo.java`:**

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.Format;
import java.text.MessageFormat;
import java.util.Locale;

public class MultipleFormatsDemo {
    public static void main(String[] args) {
        MessageFormat message = new MessageFormat(
                "Price={2}; item={0}; again={2}", Locale.US);

        DecimalFormat price = new DecimalFormat(
                "0.00", DecimalFormatSymbols.getInstance(Locale.US));

        message.setFormatsByArgumentIndex(
                new Format[] {null, null, price});

        System.out.println(message.format(
                new Object[] {"Notebook", "unused", 12.5}));
    }
}
```

```bash
javac -encoding UTF-8 MultipleFormatsDemo.java
java MultipleFormatsDemo
```

Stdout:

```text
Price=12.50; item=Notebook; again=12.50
```

`setFormats(...)` dùng **thứ tự xuất hiện** của `{2}`, `{0}`, `{2}`. Vì hai `{2}` lặp lại, việc dùng mảng theo argument index giúp tránh đặt nhầm formatter hoặc bỏ sót một lần xuất hiện.

### Đọc lại cấu hình formatter

- `getFormatsByArgumentIndex()` trả mảng đánh chỉ số theo **argument index**. Nếu cùng một argument xuất hiện nhiều lần với formatter khác nhau, phần tử trả về tương ứng **lần xuất hiện cuối** của argument đó, vì một ô mảng không thể mô tả mọi sự khác biệt.
- `getFormats()` trả mảng theo **format-element index**, đủ để phân biệt các lần xuất hiện riêng.
- Hai API này phục vụ kiểm tra cấu hình, nhưng khi lập trình hãy lưu cả **pattern gốc** và ý định formatter, vì việc gọi `applyPattern(...)` có thể thay thế các subformatter đã gán.

## 5. Locale của MessageFormat và locale của formatter con

`new MessageFormat(pattern, locale)` chọn locale cho các subformat được tạo từ pattern như `{0,number}` và `{1,date,short}`. Nếu bạn gán một `DecimalFormat` hoặc `DateFormat` **do chính mình tạo**, nó giữ locale/cấu hình của **đối tượng formatter ấy**, không tự chuyển sang locale của `MessageFormat`.

```java
Locale uiLocale = Locale.forLanguageTag("vi-VN");
Locale numericLocale = Locale.US;

MessageFormat message =
        new MessageFormat("Value={0}", uiLocale);
DecimalFormat numeric =
        new DecimalFormat("0.00",
                DecimalFormatSymbols.getInstance(numericLocale));
message.setFormatByArgumentIndex(0, numeric);
```

Đoạn trên là **fragment Java**, với `import` phù hợp. Nó có ý nghĩa: mẫu thông điệp được chuẩn bị cho ngôn ngữ giao diện `vi-VN`, nhưng đối số số dùng quy ước số do `numericLocale` kiểm soát. Nếu muốn số cũng theo `vi-VN`, tạo `DecimalFormatSymbols.getInstance(uiLocale)`.

**`setLocale(Locale)` không cập nhật lại các subformatter đã được tạo trước đó**. Nó tác động đến subformatter được tạo trong các lần `applyPattern(...)` về sau và một số trường hợp định dạng chưa có subformat. Cần tạo lại `MessageFormat` hoặc gán lại formatter con khi thay đổi locale của request.

**`applyPattern(...)` phân tích mẫu và xây dựng lại tập format element**, vì thế một formatter tùy chỉnh đã được gán bằng `setFormatByArgumentIndex(...)` có thể mất sau khi áp dụng mẫu khác. Trình tự nên dùng là:

1. Lấy **pattern đúng locale** từ tài nguyên dịch.
2. Tạo `MessageFormat(pattern, locale)`.
3. Tạo subformatter với locale/tiền tệ/múi giờ phù hợp.
4. Gán formatter theo **argument index**.
5. Gọi `format(new Object[] {...})` với các giá trị đúng kiểu.

Không thiết kế một formatter toàn cục rồi liên tục thay `setLocale` hoặc `applyPattern` khi các request chạy song song.

## 6. Vấn đề lớn với java.time trên Java 17 và Java 21

Cú pháp cổ điển của `MessageFormat` cho ngày và giờ là:

```text
{0,date}
{0,date,short}
{1,time,long}
{2,date,yyyy-MM-dd}
```

Trên **Java 17 và Java 21**, các mục kiểu `date`/`time` trên tạo `java.text.DateFormat` hoặc `SimpleDateFormat`. Chúng hiểu những kiểu đầu vào của API ngày giờ cũ, đặc biệt `java.util.Date`, nhưng **không chấp nhận `LocalDate`/`LocalDateTime`/`Instant` như một `java.util.Date`**.

| Giá trị đầu vào | `{0}` không gán subformat | `{0,date,short}` trên Java 17/21 |
| --- | --- | --- |
| `java.util.Date` | `MessageFormat` dùng định dạng ngày/giờ mặc định cho đối số Date | Định dạng qua `DateFormat` |
| `LocalDate` | Thường thành chuỗi qua `toString()`; ví dụ `2026-10-28` | Thường ném `IllegalArgumentException` vì không phải kiểu `Date` |
| `LocalDateTime` | Chuỗi `toString()`, không có địa chỉ múi giờ | Không được `DateFormat` hỗ trợ trực tiếp |
| `Instant` | Chuỗi `toString()` như `2026-10-28T...Z` | Không được `DateFormat` hỗ trợ trực tiếp |
| `ZonedDateTime` | Chuỗi `toString()` có thông tin vùng/offset | Không được `DateFormat` hỗ trợ trực tiếp |

**Không nhầm `toString()` với localize:** khi pattern chỉ có `{0}`, việc thấy `LocalDate` được in thành `2026-10-28` không có nghĩa là `MessageFormat` đã áp dụng quy tắc ngày của người dùng. Đó chỉ là cách biểu diễn mặc định của đối tượng. Nếu cần tên tháng hoặc thứ tự ngày/tháng theo locale, phải dùng `DateTimeFormatter` phù hợp.

### Ví dụ chứng minh khác biệt — `JavaTimeLimitationDemo.java`

```java
import java.text.MessageFormat;
import java.time.LocalDate;
import java.util.Locale;

public class JavaTimeLimitationDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        MessageFormat raw = new MessageFormat(
                "Raw={0}", Locale.US);
        System.out.println(raw.format(new Object[] {date}));

        MessageFormat legacy = new MessageFormat(
                "Date={0,date,short}", Locale.US);
        try {
            System.out.println(
                    legacy.format(new Object[] {date}));
        } catch (IllegalArgumentException exception) {
            System.out.println(
                    "Date type rejected: "
                    + exception.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 JavaTimeLimitationDemo.java
java JavaTimeLimitationDemo
```

Stdout trên Java 17/21:

```text
Raw=2026-10-28
Date type rejected: IllegalArgumentException
```

Dòng đầu là `LocalDate.toString()`, dòng thứ hai là lỗi khi `DateFormat` được chọn cho placeholder. Không nên “sửa” bằng cách ép kiểu `(java.util.Date) localDate`: đây là các hệ kiểu khác nhau, ép kiểu trực tiếp không hợp lệ.

**Lưu ý phiên bản:** các JDK mới hơn có thể bổ sung cú pháp MessageFormat tương tác trực tiếp với `DateTimeFormatter`. Không suy diễn cú pháp mới đó đã có trong **Java 17/21**. Bài này tập trung các giải pháp thực sự dùng được ở baseline Java 17+ phổ biến.

## 7. Cách 1 — Định dạng java.time trước rồi truyền String

Cách đơn giản, dễ kiểm soát nhất khi mẫu câu chỉ cần **một cách hiển thị** của ngày: dùng `DateTimeFormatter` để chuyển đối tượng thời gian thành chuỗi, sau đó để `MessageFormat` chèn chuỗi vào `{0}`.

**File `PreformatJavaTimeDemo.java`:**

```java
import java.text.MessageFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class PreformatJavaTimeDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter dateFormatter =
                DateTimeFormatter.ISO_LOCAL_DATE;

        String prepared = date.format(dateFormatter);

        MessageFormat message = new MessageFormat(
                "Meeting date: {0}", Locale.US);

        System.out.println(message.format(
                new Object[] {prepared}));
    }
}
```

```bash
javac -encoding UTF-8 PreformatJavaTimeDemo.java
java PreformatJavaTimeDemo
```

Stdout:

```text
Meeting date: 2026-10-28
```

Nếu muốn bản địa hóa, thay `ISO_LOCAL_DATE` bằng:

```java
// Fragment trong một phương thức đã import các lớp liên quan.
DateTimeFormatter local = DateTimeFormatter
        .ofLocalizedDate(java.time.format.FormatStyle.LONG)
        .withLocale(Locale.forLanguageTag("vi-VN"));
String prepared = date.format(local);
```

Văn bản `prepared` khi đó phụ thuộc dữ liệu locale của JDK, nên không nên dùng một chuỗi ngày cụ thể làm stdout bất biến trên mọi môi trường.

**Ưu điểm:** thao tác rõ ràng, tận dụng API `java.time` immutable, dễ xử lý `LocalDate`, `LocalTime`, `LocalDateTime`. **Giới hạn:** khi một bản dịch cần cùng đối số ngày xuất hiện **hai lần với hai định dạng khác nhau**, bạn phải tạo hai chuỗi hoặc dùng adapter; dịch giả nên biết tham số đã được định dạng.

**Quan trọng:** không dùng một pattern như `"{0,date}"` cho đối số đã là `String`: subformat `DateFormat` vẫn mong giá trị ngày kiểu cũ và có thể báo lỗi. Với chuỗi chuẩn bị sẵn, pattern phải dùng `{0}`.

## 8. Cách 2 — DateTimeFormatter.toFormat() để gán formatter con

`DateTimeFormatter` không kế thừa `java.text.Format`, nhưng có phương thức **`toFormat()`** và **`toFormat(TemporalQuery<?>)`** trả về adapter `Format`. Adapter này nhận các đối tượng triển khai `TemporalAccessor` khi định dạng, bao gồm `LocalDate`; đây là cầu nối trực tiếp để dùng `setFormatByArgumentIndex` trong Java 17/21.

**Ví dụ chạy độc lập — `JavaTimeFormatBridgeDemo.java`:**

```java
import java.text.Format;
import java.text.MessageFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class JavaTimeFormatBridgeDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        MessageFormat message = new MessageFormat(
                "Planned={0}; repeated={0}", Locale.US);

        Format adapter =
                DateTimeFormatter.ISO_LOCAL_DATE
                        .toFormat(LocalDate::from);

        message.setFormatByArgumentIndex(0, adapter);

        System.out.println(message.format(
                new Object[] {date}));
    }
}
```

```bash
javac -encoding UTF-8 JavaTimeFormatBridgeDemo.java
java JavaTimeFormatBridgeDemo
```

Stdout:

```text
Planned=2026-10-28; repeated=2026-10-28
```

**Cách hoạt động:**

1. `DateTimeFormatter.ISO_LOCAL_DATE` biết định dạng `LocalDate` thành một ngày ISO.
2. `toFormat(LocalDate::from)` trả một `java.text.Format` tương thích với setter của `MessageFormat`. Khi **parse** ngược, query giúp nhận một `LocalDate` thay vì một `TemporalAccessor` tổng quát.
3. `setFormatByArgumentIndex(0, adapter)` gán adapter cho **cả hai** placeholder `{0}`.
4. Đối số vẫn là **`LocalDate`**, không cần chuyển sang `java.util.Date` hoặc sang chuỗi trước.

Có thể dùng `DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withLocale(uiLocale).toFormat()` để định dạng ngày theo locale người dùng. Khi dùng formatter chứa trường giờ, phải cung cấp kiểu temporal đủ trường. Ví dụ một `LocalDate` **không có giờ** nên sẽ thất bại nếu formatter yêu cầu giờ; `LocalDateTime` **không có offset/zone** nên không thể tự biểu diễn instant toàn cầu nếu thiếu `ZoneId`.

### Khi parse ngược thì sao?

`toFormat()` không tham số thường parse ra `TemporalAccessor` đã resolve; `toFormat(LocalDate::from)` yêu cầu lấy `LocalDate`. Trong ứng dụng thông điệp, `MessageFormat` chủ yếu dùng để **format**; việc parse trở lại từ câu văn được dịch dễ mơ hồ và không phù hợp làm API nhập dữ liệu quan trọng. Nếu cần parse ngày, dùng `LocalDate.parse(input, dateFormatter)` trực tiếp, với formatter và locale đã biết.

## 9. Cách 3 — Chuyển sang java.util.Date khi phải dùng DateFormat cũ

Với một hệ thống legacy vốn có `DateFormat` hoặc `SimpleDateFormat` đã được cấu hình, bạn có thể chuyển đối tượng `java.time` sang `java.util.Date` **sau khi xác định rõ instant và múi giờ**.

**Không có chuyển đổi trực tiếp từ `LocalDate` sang `Date` mà không có lựa chọn vùng**, vì `LocalDate` chỉ là ngày trên lịch, không có giờ và timezone. Một ngày `2026-10-28` ở đầu ngày tại `Asia/Ho_Chi_Minh` ứng với instant khác đầu ngày tại `UTC`.

**File `LegacyDateBridgeDemo.java`:**

```java
import java.text.MessageFormat;
import java.text.SimpleDateFormat;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class LegacyDateBridgeDemo {
    public static void main(String[] args) {
        LocalDate localDate = LocalDate.of(2026, 10, 28);
        ZoneId zone = ZoneId.of("UTC");

        Date oldDate = Date.from(
                localDate.atStartOfDay(zone).toInstant());

        SimpleDateFormat legacyFormat =
                new SimpleDateFormat("yyyy-MM-dd", Locale.US);
        legacyFormat.setTimeZone(TimeZone.getTimeZone(zone));

        MessageFormat message = new MessageFormat(
                "Legacy={0}", Locale.US);
        message.setFormatByArgumentIndex(0, legacyFormat);

        System.out.println(message.format(
                new Object[] {oldDate}));
    }
}
```

```bash
javac -encoding UTF-8 LegacyDateBridgeDemo.java
java LegacyDateBridgeDemo
```

Stdout:

```text
Legacy=2026-10-28
```

Kết quả ổn định vì cả **bước chuyển `LocalDate` sang instant** và **`SimpleDateFormat`** đều dùng UTC. Nếu bỏ `setTimeZone(...)`, formatter có thể diễn giải `Date` theo timezone mặc định của JVM và làm ngày hiển thị lệch trong một số môi trường.

Khi đã có `Instant`, có thể dùng `Date.from(instant)` vì cả hai đại diện cho một thời điểm. Khi đã có `LocalDateTime`, hãy chọn `ZoneId` theo ý nghĩa nghiệp vụ rồi tạo `ZonedDateTime`/`Instant` trước khi chuyển. **Đừng dùng múi giờ server như một quyết định ngầm** nếu ngày giờ gắn với vị trí hoặc người dùng cụ thể.

**Đánh đổi:** cách này thích hợp để tương tác hệ thống cũ; với code mới, `DateTimeFormatter.toFormat()` hoặc định dạng trước thường ít bước và ít rủi ro nhầm timezone hơn. `SimpleDateFormat` có trạng thái mutable và không an toàn khi nhiều thread gọi đồng thời mà không bảo vệ.

## 10. Lỗi kỹ thuật khi đặt formatter

### A. Truyền sai kiểu đối số

Subformat được chỉ định là `NumberFormat` thì đối số phải là số phù hợp; `DateFormat` đòi giá trị ngày hỗ trợ; adapter `DateTimeFormatter` nhận `TemporalAccessor` có đủ trường cần thiết. Ví dụ:

```java
MessageFormat form = new MessageFormat(
        "Date={0,date,short}", Locale.US);
form.format(new Object[] {
        java.time.LocalDate.of(2026, 10, 28)
});
```

Đây là đoạn mã **minh họa lỗi trên Java 17/21**, không phải ví dụ để chạy thành công: `DateFormat` từ mẫu `date` nhận `LocalDate` sai kiểu, thường phát sinh `IllegalArgumentException`. Cách sửa là dùng một trong ba giải pháp ở trên.

### B. Dùng chỉ số element trong nội dung dịch

`setFormat(0, ...)` gán cho placeholder **đầu tiên trong câu**, không hẳn argument `0`. Câu của hai ngôn ngữ có thể đảo thứ tự. Hãy ưu tiên `setFormatByArgumentIndex(0, ...)` khi cùng đối số cần một formatter.

### C. Một argument được định dạng nhiều cách

Nếu pattern chứa `"{0,date,short} ... {0,date,long}"`, gọi `setFormatByArgumentIndex(0, custom)` sẽ thay **cả hai subformatter**, làm mất sự khác biệt ngắn/dài. Khi cần chủ đích hai định dạng, có thể truyền **hai đối số** đã chuẩn bị sẵn (ví dụ `{0}` cho ngày ngắn và `{1}` cho ngày dài), hoặc gán theo từng **element index** với kiểm thử bản dịch.

### D. `applyPattern` làm thay đổi custom formatter

`applyPattern(...)` phân tích lại pattern và tạo tập format element tương ứng. Nếu code gán custom formatter trước rồi mới áp dụng bản dịch, formatter có thể mất tác dụng. Hãy **chọn pattern trước, gán format sau**; đổi locale thì tạo `MessageFormat` mới hoặc gán lại format đúng ngữ cảnh.

### E. Dùng `setLocale` như một lệnh cập nhật tất cả formatter

`message.setLocale(newLocale)` không tự cập nhật subformatter đã được tạo. `DecimalFormat`, `DateFormat` và adapter `DateTimeFormatter` mà bạn gán vào giữ cấu hình riêng của chúng. Nếu cần thay locale, hãy dựng lại cấu hình từ đầu.

### F. Chia sẻ MessageFormat giữa các thread

`MessageFormat` không đồng bộ; nhiều subformatter như `NumberFormat` và `SimpleDateFormat` có trạng thái thay đổi được. Trong web server, nên tạo instance theo mỗi lần render/request hoặc bảo vệ việc dùng instance chia sẻ theo thiết kế. Tránh ghi `setFormatByArgumentIndex` trên một đối tượng đang được các request khác dùng.

### G. Quên dấu nháy đơn và ngoặc nhọn trong pattern

Trong pattern `MessageFormat`, dấu nháy đơn `'` có tác dụng quote cú pháp; muốn hiển thị dấu nháy đơn thật, thường phải viết `''`. Các dấu `{`/`}` trong văn bản không phải placeholder cần được quote đúng cách. Khi lấy pattern từ `ResourceBundle`, biên dịch viên phải biết đây là chuỗi được `MessageFormat` diễn giải; ký tự quote sai có thể khiến placeholder không được thay.

### H. Dùng `MessageFormat.parse` để tái tạo dữ liệu nghiệp vụ

`format` không luôn đảo ngược được. Nếu cùng argument xuất hiện nhiều lần, `parse` có thể lấy kết quả **lần khớp cuối**. Đơn vị tiền, múi giờ, locale và định dạng hiển thị còn có thể làm mất thông tin. Đầu vào cần dữ liệu có cấu trúc nên dùng parser chuyên biệt (`LocalDate.parse`, `NumberFormat.parse` với kiểm tra toàn bộ đầu vào, v.v.), không dựa vào parsing từ câu giao diện.

## 11. Ví dụ ghép thông điệp từ ResourceBundle với formatter cho từng đối số

Trong sản phẩm bản địa hóa, **câu chữ thuộc bundle**, dữ liệu thuộc code và formatter thuộc ngữ cảnh định dạng. Có thể dùng một key chứa placeholder trong `messages.properties`:

```properties
order.summary=Order {0} has {1} units, ship date {2}.
```

Ví dụ `messages_vi.properties`:

```properties
order.summary=Đơn {0} có {1} sản phẩm, giao ngày {2}.
```

Nếu nguồn thông điệp là bundle, luồng làm việc điển hình gồm:

1. Xác định `Locale uiLocale` của người dùng, load bundle qua `ResourceBundle.getBundle(baseName, uiLocale)`.
2. Lấy pattern bằng `bundle.getString("order.summary")`.
3. Tạo `MessageFormat(pattern, uiLocale)`.
4. Gán formatter số cho argument `1` và adapter `DateTimeFormatter` cho argument `2`.
5. Truyền đối số gồm mã đơn hàng, số lượng và `LocalDate`; nhận về một câu hoàn chỉnh.

**Chương trình Java 17+ độc lập** — file `MessageBundleBridgeDemo.java` (mẫu câu được khai báo sẵn để không cần thêm file .properties trong bài thử này):

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.MessageFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class MessageBundleBridgeDemo {
    public static void main(String[] args) {
        Locale uiLocale = Locale.US;
        String pattern =
                "Order {0}: {1} units, date {2}, repeat {2}";

        MessageFormat message =
                new MessageFormat(pattern, uiLocale);

        DecimalFormat quantity = new DecimalFormat(
                "000", DecimalFormatSymbols.getInstance(uiLocale));
        message.setFormatByArgumentIndex(1, quantity);

        message.setFormatByArgumentIndex(
                2, DateTimeFormatter.ISO_LOCAL_DATE.toFormat());

        Object[] values = {
                "AX-9",
                7,
                LocalDate.of(2026, 10, 28)
        };

        System.out.println(message.format(values));
    }
}
```

```bash
javac -encoding UTF-8 MessageBundleBridgeDemo.java
java MessageBundleBridgeDemo
```

Stdout:

```text
Order AX-9: 007 units, date 2026-10-28, repeat 2026-10-28
```

Đây là ví dụ *nhúng mẫu câu trực tiếp* để chạy riêng. Khi chuyển sang dùng `ResourceBundle` thật, thay biến `pattern` bằng `bundle.getString(key)` và giữ phần gán format theo **argument index**, để bản dịch có thể đổi thứ tự đối số mà không làm sai kiểu dữ liệu. Cách định dạng ngày có thể đổi từ `ISO_LOCAL_DATE` sang `ofLocalizedDate(FormatStyle.MEDIUM).withLocale(uiLocale)` khi UI cần quy ước địa phương; chuỗi ngày khi đó phụ thuộc dữ liệu locale runtime.

## 12. Khả năng định dạng và giới hạn theo từng kiểu java.time

| Kiểu thời gian | Có thể định dạng trước bằng DateTimeFormatter? | Có thể dùng `toFormat()` làm subformatter? | Điểm cần lưu ý |
| --- | --- | --- | --- |
| `LocalDate` | Có, với formatter ngày | Có, nếu formatter chỉ đòi trường ngày | Không có giờ/múi giờ |
| `LocalTime` | Có, với formatter giờ | Có, nếu chỉ đòi trường giờ | Không có ngày/timezone |
| `LocalDateTime` | Có, nếu formatter đòi ngày và/hoặc giờ | Có | Không gắn với một instant nếu chưa biết vùng |
| `OffsetDateTime` | Có, dùng pattern có offset khi cần | Có | Chứa offset nhưng không nhất thiết có region zone |
| `ZonedDateTime` | Có, gồm vùng/offset nếu formatter yêu cầu | Có | Quy tắc vùng có thể ảnh hưởng kết quả |
| `Instant` | Có với `DateTimeFormatter.ISO_INSTANT`, hoặc formatter đã được cung cấp zone phù hợp | Có với formatter tương thích | Không tự chứa calendar fields theo vùng nếu formatter chưa có zone |
| `YearMonth` | Có với pattern `uuuu-MM` | Có với formatter chỉ yêu cầu năm/tháng | Không có ngày trong tháng |
| `Duration` / `Period` | Không phải đối tượng ngày lịch thông thường cho mọi localized date/time formatter | Không dùng chung `ofLocalizedDate` một cách trực tiếp | Dùng `toString()` hoặc định dạng nghiệp vụ riêng |

**Quy tắc chọn formatter:** muốn định dạng kiểu nào, phải có các trường mà kiểu đó cung cấp. Ví dụ `LocalDate` không có `HOUR_OF_DAY` nên `DateTimeFormatter.ofLocalizedTime(...)` không thể tự tạo giờ. `Instant` cần chuyển sang một zone để tạo được các thành phần ngày/giờ địa phương; chỉ dùng locale không đủ.

**Không đánh đồng Locale và ZoneId:** locale xác định quy tắc ngôn ngữ/định dạng, còn `ZoneId` xác định cách một instant được biểu diễn theo giờ địa phương. Hai người cùng `en-US` có thể ở hai múi giờ, và một người có thể chọn ngôn ngữ khác vùng mình đang ở.

### Biến thể nâng cao: bộ định dạng bất biến và có kiểm soát

`DateTimeFormatter` là immutable, thread-safe ở bản thân nó. Tuy nhiên, đối tượng `MessageFormat` bao quanh vẫn mutable và không bảo đảm an toàn khi chia sẻ không đồng bộ. Đừng suy ra việc dùng một `DateTimeFormatter` tốt sẽ khiến toàn bộ đối tượng `MessageFormat` thread-safe.

## 13. Kiểm thử cần thiết

Một bộ kiểm thử hữu ích cho chức năng format thông điệp gồm:

- **Argument lặp:** `{0}` xuất hiện nhiều lần và `setFormatByArgumentIndex(0, ...)` phải áp dụng cho tất cả lần xuất hiện.
- **Đảo trật tự dịch:** đổi thứ tự `{0}`/`{1}` giữa hai pattern; formatter vẫn gắn với đúng **argument index**.
- **Phân biệt element và argument:** kiểm tra `setFormat(0, ...)` chỉ đổi vị trí đầu tiên, không đổi mọi placeholder có cùng số đối số.
- **Kiểu sai:** `LocalDate` với `{0,date,short}` trên Java 17/21 ném lỗi; với `DateTimeFormatter.toFormat()` thì hoạt động.
- **Chuỗi chuẩn bị trước:** `date.format(dtf)` truyền vào `{0}` không cần DateFormat cũ.
- **Timezone:** khi chuyển `LocalDate` sang `Date`, chỉ ra và kiểm thử vùng dùng để tạo instant cũng như timezone formatter.
- **Locale thay đổi:** format số/ngày theo locale request; không dùng `setLocale` như cách cập nhật subformatter đã có.
- **applyPattern:** khi áp dụng mẫu mới, cấu hình lại formatter trước khi render.
- **Đa luồng:** các request không cùng sửa một instance `MessageFormat` hoặc `SimpleDateFormat`.
- **Parse:** nếu cần đọc dữ liệu từ input, dùng parser chuyên biệt và kiểm tra cả chuỗi, không tự tin khôi phục từ câu đã render.

### Bài tập 1 — Hai vị trí cho cùng một đối số

Cho pattern `"ID={1}; amount={0}; amountAgain={0}"` và đối số `{12.5, "A-1"}`. Dùng `setFormatByArgumentIndex(0, new DecimalFormat("0.00", DecimalFormatSymbols.getInstance(Locale.US)))` để hai vị trí số cùng in `12.50`. Sau đó thử `setFormat(0, ...)` và giải thích vì sao nó tác động lên placeholder `{1}` ở đầu câu.

### Bài tập 2 — Ngày kiểu mới

Với `LocalDate.of(2026, 10, 28)`, tạo hai mẫu `"Date={0}"` và `"Date={0,date,short}"`. Quan sát kết quả trên Java 17/21. Dùng `ISO_LOCAL_DATE.toFormat()` cho mẫu `{0}`, sau đó thử formatter địa phương hóa với `withLocale(Locale.forLanguageTag("vi-VN"))`.

### Bài tập 3 — Từ bundle ra màn hình

Tạo hai file thông điệp chứa cùng một cặp argument index cho mã đơn và số lượng, nhưng thứ tự khác nhau. Đọc từng pattern và gán formatter số theo argument index. Chứng minh bản dịch vẫn nhận đúng dữ liệu, không phụ thuộc vị trí placeholder trong câu.

## 14. Tài liệu chính thức và phiên bản

- [JDK 21 — java.text.MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html): pattern, `setFormatByArgumentIndex`, `setFormatsByArgumentIndex`, `setFormat`, `applyPattern`, mặc định date/time ở API cổ điển.
- [JDK 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): `toFormat()`, `toFormat(TemporalQuery)`, `withLocale`, `withZone` và cách định dạng `java.time`.
- [JDK 21 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/SimpleDateFormat.html): mô hình ngày/giờ cũ, time zone và lưu ý về mutable format.

JDK mới có thể mở rộng khả năng `MessageFormat`; khi chương trình yêu cầu chạy trên Java 17/21, luôn kiểm tra tài liệu **đúng phiên bản đang dùng** và không chép cú pháp từ tài liệu JDK mới mà chưa xác minh tính tương thích.

## 15. Ghi nhớ

**`setFormatByArgumentIndex(index, format)` gán formatter theo chỉ số đối số và áp dụng cho mọi placeholder dùng đối số đó; `setFormat(elementIndex, format)` chỉ gán theo vị trí xuất hiện của placeholder trong câu.** Với thông điệp được dịch, cách gán theo argument index thường bền vững hơn khi trật tự câu thay đổi.

Trên **Java 17/21**, `{0,date}`/`{0,time}` của `MessageFormat` dựa vào API `java.text` và không dùng trực tiếp được với nhiều kiểu `java.time` như `LocalDate`. Để xử lý đúng, hãy **định dạng trước thành chuỗi**, **gán adapter `DateTimeFormatter.toFormat()`**, hoặc **chuyển sang `java.util.Date` cùng `ZoneId` rõ ràng khi phải tương tác code cũ**. Luôn kiểm soát locale, kiểu đối số, múi giờ và vòng đời của `MessageFormat` để tránh lỗi đầu ra hoặc đụng độ giữa các luồng.