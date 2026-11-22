# Tính bất biến và an toàn đa luồng của `DateTimeFormatter` trong Java

## 1. Vấn đề: định dạng ngày giờ trong ứng dụng nhiều luồng

Một hệ thống web có thể đồng thời xử lý hàng trăm request. Mỗi request cần biến một `LocalDate`, `Instant` hoặc `ZonedDateTime` thành chuỗi ngày giờ theo locale và múi giờ của người dùng; một số request khác cần đọc chuỗi ngày giờ trở lại thành kiểu dữ liệu Java.

Cách tổ chức tốt là **tái sử dụng một `DateTimeFormatter` đã cấu hình xong** khi nhiều tác vụ có cùng quy tắc định dạng. Java bảo đảm `java.time.format.DateTimeFormatter` là **immutable (bất biến) và thread-safe (an toàn để nhiều luồng cùng sử dụng)**.

Hai tính chất có liên quan nhưng không đồng nghĩa:

- **Bất biến:** sau khi được tạo, trạng thái cấu hình của một `DateTimeFormatter` không bị thay đổi bởi các thao tác như `format`, `parse`, `withLocale` hay `withZone`.
- **An toàn đa luồng:** nhiều luồng có thể đồng thời gọi những thao tác đọc/format/parse trên **cùng một formatter** mà không cần đặt `synchronized` bên ngoài chỉ để bảo vệ trạng thái formatter.

Điều này khác với `java.text.SimpleDateFormat`, vốn có trạng thái thay đổi và **không an toàn để dùng chung tùy ý giữa các luồng**.

**Điểm cốt lõi:** an toàn đa luồng của formatter không tự làm mọi đối tượng/nguồn dữ liệu được truyền vào trở nên bất biến; cũng không tự giải quyết bài toán chọn locale, múi giờ, lịch, phân giải ngày hoặc kiểm soát đầu vào không hợp lệ.

## 2. Hiểu đúng “bất biến”: cấu hình không bị sửa tại chỗ

Hãy xem formatter như một **đối tượng mô tả quy tắc** gồm pattern, locale, chronology, decimal style, resolver style và có thể có zone override. Sau khi hoàn thành việc xây dựng, cấu hình ấy được giữ ổn định.

Ví dụ:

```java
DateTimeFormatter base =
        DateTimeFormatter.ofPattern("d MMMM uuuu", Locale.US);

DateTimeFormatter german = base.withLocale(Locale.GERMANY);
```

`withLocale(Locale.GERMANY)` **không sửa** `base`; nó trả về formatter có cấu hình locale được yêu cầu. Vì vậy `base` vẫn dùng tiếng Anh khi format tên tháng, còn `german` có thể dùng tiếng Đức.

Các phương thức `with...` chính:

| Phương thức | Cấu hình được thay ở formatter trả về | Điều không xảy ra |
| --- | --- | --- |
| `withLocale(locale)` | Locale dùng cho văn bản và quy tắc định dạng liên quan | Không đổi locale của formatter ban đầu |
| `withZone(zone)` | Múi giờ override khi format/parse theo ngữ nghĩa API | Không đặt lại múi giờ toàn cục của JVM |
| `withChronology(chronology)` | Hệ lịch override | Không sửa đối tượng thời gian gốc |
| `withDecimalStyle(style)` | Ký hiệu chữ số, dấu thập phân, dấu âm... dùng trong parsing/formatting thích hợp | Không làm thay đổi mọi chuỗi trong ứng dụng |
| `withResolverStyle(style)` | Chính sách phân giải các trường ngày/giờ | Không ép formatter gốc đổi kiểu resolver |
| `withResolverFields(...)` | Tập trường dùng trong bước resolve | Không thay đổi formatter gốc |

**Lưu ý về identity:** API có thể tối ưu bằng cách trả lại **chính đối tượng hiện tại** nếu cấu hình yêu cầu đã giống trạng thái sẵn có. Vì vậy không nên kiểm thử bất biến bằng điều kiện `a != a.withLocale(a.getLocale())`. Hợp đồng cần dựa vào **không có mutation quan sát được**, không phải “mỗi lời gọi chắc chắn cấp phát một object mới”.

Và cũng cần nhớ: muốn thay cấu hình khi sử dụng, **phải giữ giá trị trả về**:

```java
DateTimeFormatter base =
        DateTimeFormatter.ofPattern("d MMMM uuuu", Locale.US);

base.withLocale(Locale.GERMANY); // Không đổi base.
DateTimeFormatter german = base.withLocale(Locale.GERMANY); // Đúng.
```

Nếu bỏ qua giá trị trả về, ứng dụng vẫn dùng formatter gốc. Đây là lỗi phổ biến khi chuyển từ các API mutable có setter sang API bất biến.

## 3. Ví dụ hoàn chỉnh: `withLocale` không thay đổi formatter gốc

Tạo tệp **`ImmutableFormatterDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ImmutableFormatterDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter english =
                DateTimeFormatter.ofPattern("d MMMM uuuu", Locale.US);
        DateTimeFormatter german =
                english.withLocale(Locale.GERMANY);

        System.out.println("english=" + english.format(date));
        System.out.println("german=" + german.format(date));
        System.out.println("english-again=" + english.format(date));
        System.out.println("same-object=" + (english == german));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 ImmutableFormatterDemo.java
java -cp . ImmutableFormatterDemo
```

Đầu ra với dữ liệu locale tiếng Anh/Đức thông dụng của JDK:

```text
english=28 October 2026
german=28 Oktober 2026
english-again=28 October 2026
same-object=false
```

**Giải thích:** `german` mang locale khác, nhưng formatter `english` vẫn giữ nguyên cấu hình. Biến `date` là một `LocalDate` cố định, không thay đổi khi format.

Đầu ra tên tháng dựa trên dữ liệu locale của Java runtime; giữa các bản JDK/CLDR và các hệ ngôn ngữ khác, cách viết có thể thay đổi. Với kiểm thử snapshot cần tính đến dữ liệu locale/version; các ví dụ số hoàn toàn thường ổn định hơn cho bài kiểm tra an toàn đa luồng.

### Một số hiểu nhầm khi gọi `withLocale`

- `withLocale` không dịch những **chữ literal** mà developer cố ý đặt trong pattern, ví dụ `'tháng'`; nó tác động lên các thành phần định dạng có dữ liệu locale như tên tháng/ngày.
- `withLocale` không tự thay đổi **múi giờ**. Một người dùng chọn tiếng Việt không có nghĩa họ ở múi giờ Việt Nam.
- `withLocale` không quyết định **kiểu hiển thị** cho mọi pattern tùy biến. Nếu pattern được cố định thành `dd/MM/uuuu`, dấu gạch chéo và thứ tự phần tử do pattern quy định sẽ giữ như thế.
- Để dùng một kiểu ngày/giờ thích nghi theo locale (ngày ngắn, trung bình, dài), có thể dùng `DateTimeFormatter.ofLocalizedDate(...)` hoặc `ofLocalizedDateTime(...)` với locale đúng; dữ liệu mẫu theo locale có thể thay đổi theo JDK.

## 4. Thread-safe nghĩa là có thể chia sẻ cùng một formatter

Một formatter được khởi tạo đầy đủ có thể được giữ trong một hằng số:

```java
private static final DateTimeFormatter DATE_FORMATTER =
        DateTimeFormatter.ofPattern(
                "dd/MM/uuuu", Locale.US);
```

Sau đó nhiều luồng có thể gọi `DATE_FORMATTER.format(date)` và `LocalDate.parse(input, DATE_FORMATTER)` đồng thời, miễn là logic của ứng dụng không chia sẻ **trạng thái mutable không an toàn khác**.

So sánh tư duy triển khai:

```text
Nhiều request
    │
    ├── request A ──> format(dateA) ──┐
    ├── request B ──> parse(textB) ──┤
    ├── request C ──> format(dateC) ──┤── formatter chung (immutable)
    └── request D ──> parse(textD) ──┘
```

Không cần tạo một `DateTimeFormatter` mới cho **mỗi lần** format nếu tất cả request dùng cùng cấu hình. Không cần `ThreadLocal<DateTimeFormatter>` chỉ vì lo formatter Java Time có trạng thái bị thay đổi.

Tuy vậy, **cùng formatter** chỉ đúng khi các request thực sự cần **cùng pattern, locale, chronology, resolver và zone override**. Nếu mỗi người dùng có locale khác nhau, hãy lấy biến thể formatter theo locale thay vì dùng một formatter chứa locale sai cho tất cả người dùng.

## 5. Ví dụ Java 17+: sử dụng một formatter từ nhiều luồng

Ví dụ dưới đây chia sẻ hằng số `SHARED` giữa bốn tác vụ. Các tác vụ chạy qua thread pool, sử dụng formatter để format rồi parse ngày. Để đầu ra xác định được, chương trình **đọc `Future` theo thứ tự tác vụ đã gửi**, không in trực tiếp từ từng thread.

Tạo **`SharedFormatterDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SharedFormatterDemo {
    private static final DateTimeFormatter SHARED =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.US)
                    .withResolverStyle(ResolverStyle.STRICT);

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            List<Callable<String>> tasks = new ArrayList<>();

            for (int i = 0; i < 4; i++) {
                final int taskId = i;

                tasks.add(() -> {
                    LocalDate date = LocalDate.of(2026, 10, 28)
                            .plusDays(taskId);
                    String text = SHARED.format(date);
                    LocalDate parsed = LocalDate.parse(text, SHARED);

                    return "task-" + taskId + ": " + text
                            + " -> " + parsed;
                });
            }

            List<Future<String>> results = pool.invokeAll(tasks);

            for (Future<String> future : results) {
                System.out.println(future.get());
            }
        } finally {
            pool.shutdown();
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SharedFormatterDemo.java
java -cp . SharedFormatterDemo
```

Kết quả:

```text
task-0: 28/10/2026 -> 2026-10-28
task-1: 29/10/2026 -> 2026-10-29
task-2: 30/10/2026 -> 2026-10-30
task-3: 31/10/2026 -> 2026-10-31
```

Từng `Callable` dùng **cùng đối tượng formatter `SHARED`**. `LocalDate` và chuỗi ngày của mỗi tác vụ được tạo riêng; `Future.get()` chờ kết quả rồi in theo thứ tự cố định. Thứ tự thread thực sự chạy có thể khác nhưng không ảnh hưởng tính đúng đắn hoặc thứ tự các dòng in.

**Điểm học thuật:** một lần chạy thành công của chương trình đa luồng **không phải bằng chứng toán học** rằng API thread-safe; bảo đảm này đến từ **hợp đồng của `DateTimeFormatter`**. Ví dụ giúp minh họa một cách sử dụng hợp lệ, không nên cố tạo cuộc đua dữ liệu rồi đợi xuất hiện lỗi để “chứng minh” thread-safety.

## 6. `withZone` trả về một cấu hình mới, không làm đổi formatter chung

Ngày và giờ cần thêm yếu tố **múi giờ**. Một `Instant` mô tả một thời điểm tuyệt đối, nhưng muốn in giờ địa phương phải chọn `ZoneId`. `DateTimeFormatter.withZone` tạo formatter với **zone override**, thích hợp khi format một `Instant` bằng pattern có giờ và offset.

Ví dụ:

```java
DateTimeFormatter utcFormatter =
        DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", Locale.US)
                .withZone(ZoneOffset.UTC);

DateTimeFormatter vietnamFormatter =
        utcFormatter.withZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));
```

Nếu cùng format một `Instant`, hai formatter cho giờ địa phương khác nhau. Điều quan trọng: `utcFormatter` không bị đổi sang múi giờ Việt Nam sau lời gọi `withZone`.

### Chương trình hoàn chỉnh

Tạo **`FormatterZoneDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class FormatterZoneDemo {
    public static void main(String[] args) {
        Instant instant =
                Instant.parse("2026-10-28T10:15:30Z");

        DateTimeFormatter utc =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm XXX", Locale.US)
                        .withZone(ZoneOffset.UTC);

        DateTimeFormatter hcm =
                utc.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("UTC=" + utc.format(instant));
        System.out.println("HCM=" + hcm.format(instant));
        System.out.println("UTC-again=" + utc.format(instant));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FormatterZoneDemo.java
java -cp . FormatterZoneDemo
```

Kết quả:

```text
UTC=2026-10-28 10:15 Z
HCM=2026-10-28 17:15 +07:00
UTC-again=2026-10-28 10:15 Z
```

**Lưu ý về mô hình thời gian:**

- `Locale` không phải `ZoneId`. Tiếng Việt có thể được sử dụng ở bất kỳ múi giờ nào.
- `Instant` có thể chuyển thành giờ địa phương khi đã có zone; `LocalDateTime` bản thân **không đại diện cho một thời điểm tuyệt đối**, nên không được tự gán offset như thể nó mang timezone.
- Khi format theo vùng, sử dụng zone ID vùng như `Asia/Ho_Chi_Minh`, `Europe/Paris` nếu hệ thống cần quy tắc vùng/lịch sử; offset cố định như `+07:00` không đồng nghĩa với mọi quy tắc của một vùng ở mọi thời điểm.
- Đừng dùng `TimeZone.setDefault(...)` hoặc `Locale.setDefault(...)` trong mỗi request để thay cấu hình toàn cục. Việc thay default là trạng thái chia sẻ và có thể gây ảnh hưởng chéo giữa người dùng.

## 7. `ResolverStyle` bất biến nhưng ảnh hưởng kết quả parse

Một formatter có thể cần phân giải các trường ngày/giờ theo mức độ nghiêm ngặt khác nhau. `DateTimeFormatter.ofPattern(...)` mặc định dùng `ResolverStyle.SMART`; `withResolverStyle(ResolverStyle.STRICT)` trả một formatter khác áp quy tắc nghiêm ngặt.

Đặt `uuuu` trong pattern khi mục tiêu là kiểm tra ngày theo năm proleptic Gregorian để tránh nhầm giữa `yyyy` (year-of-era) và `uuuu` khi dùng `STRICT`.

Ví dụ hoàn chỉnh **`ResolverStyleDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ResolverStyleDemo {
    public static void main(String[] args) {
        DateTimeFormatter smart =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd", Locale.US);

        DateTimeFormatter strict =
                smart.withResolverStyle(ResolverStyle.STRICT);

        System.out.println("smart-style=" +
                smart.getResolverStyle());
        System.out.println("strict-style=" +
                strict.getResolverStyle());

        System.out.println("smart=" +
                LocalDate.parse("2026-02-30", smart));

        try {
            LocalDate.parse("2026-02-30", strict);
            System.out.println("strict=accepted");
        } catch (DateTimeParseException ex) {
            System.out.println("strict=DateTimeParseException");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ResolverStyleDemo.java
java -cp . ResolverStyleDemo
```

Kết quả:

```text
smart-style=SMART
strict-style=STRICT
smart=2026-02-28
strict=DateTimeParseException
```

Ở đây `SMART` có thể điều chỉnh ngày 30 tháng 2 về ngày cuối cùng của tháng, còn `STRICT` từ chối. Cả hai formatter đều bất biến. Tính bất biến **không quyết định** chính sách kiểm tra ngày; chính developer phải chọn `ResolverStyle` phù hợp nghiệp vụ.

Đối với nhập liệu ngày giao dịch/ngày sinh cần chính xác, nên xem xét `STRICT` với pattern và chronology phù hợp. Với định dạng để đọc, các thiết lập mặc định có thể chấp nhận được, nhưng phải kiểm thử.

## 8. `DateTimeFormatterBuilder` **không giống** `DateTimeFormatter`

Đây là khác biệt quan trọng khi xây dựng cấu hình:

- `DateTimeFormatterBuilder` là **builder mutable**: các phương thức `appendPattern`, `appendLiteral`, `appendValue`, `optionalStart`... sửa **trạng thái đang xây**.
- `DateTimeFormatter` do `builder.toFormatter(...)` tạo ra là **formatter bất biến** và an toàn để chia sẻ giữa các luồng.

Không nên chia sẻ **cùng một builder** cho nhiều luồng đang gọi các phương thức `append...` vì builder có trạng thái mutable. Hãy hoàn tất bước xây dựng ở nơi được kiểm soát, sau đó công bố formatter hoàn chỉnh cho các luồng xử lý request.

Tạo **`BuilderFreezeDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.util.Locale;

public class BuilderFreezeDemo {
    public static void main(String[] args) {
        DateTimeFormatterBuilder builder =
                new DateTimeFormatterBuilder();

        builder.appendPattern("dd/MM/uuuu");

        DateTimeFormatter frozen =
                builder.toFormatter(Locale.US);

        // Tiếp tục thay đổi builder, không làm thay đổi 'frozen'.
        builder.appendLiteral('!');
        DateTimeFormatter later =
                builder.toFormatter(Locale.US);

        LocalDate day = LocalDate.of(2026, 10, 28);
        System.out.println("frozen=" + frozen.format(day));
        System.out.println("later=" + later.format(day));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BuilderFreezeDemo.java
java -cp . BuilderFreezeDemo
```

Đầu ra:

```text
frozen=28/10/2026
later=28/10/2026!
```

Bước `appendLiteral('!')` thay đổi builder; formatter `frozen` đã được tạo trước đó vẫn cho ra văn bản không có dấu `!`. Điều này minh họa chính xác ranh giới giữa **mutable construction** và **immutable formatter**.

### Tại sao builder hữu ích?

`DateTimeFormatterBuilder` hỗ trợ các mẫu phức tạp: thành phần tùy chọn, chữ số có độ rộng biến thiên, parse case-sensitive/insensitive, parse lenient/strict ở mức cú pháp, text map cho trường thời gian, vùng, offset...

Nhưng lưu ý `parseStrict()`/`parseLenient()` của builder tác động đến **giai đoạn phân tích cú pháp trường**, khác với `withResolverStyle(STRICT/SMART/LENIENT)` tác động đến **giai đoạn phân giải trường thành đối tượng ngày giờ**. Bất biến không làm biến mất sự khác biệt hai giai đoạn này.

## 9. Vì sao `SimpleDateFormat` không nên được chia sẻ tùy ý?

API cũ `java.text.SimpleDateFormat` là **mutable** và không mặc định thread-safe. Nó giữ/điều khiển trạng thái liên quan đến `Calendar`, `DateFormat`, `NumberFormat` và các cấu hình khác trong quá trình parse/format.

Đoạn mã sau là một **anti-pattern** trong ứng dụng đa luồng:

```java
// Trích đoạn không nên áp dụng:
private static final SimpleDateFormat SHARED =
        new SimpleDateFormat("dd/MM/yyyy");

// Nhiều thread đồng thời:
SHARED.format(date);
SHARED.parse(input);
```

Ngay cả khi tham chiếu `SHARED` là `static final`, **đối tượng được tham chiếu vẫn mutable**. Từ khóa `final` chỉ ngăn việc gán lại biến/tham chiếu, **không biến đối tượng thành immutable**. Các luồng có thể ảnh hưởng lẫn nhau, tạo kết quả sai hoặc ngoại lệ không ổn định. Không dùng việc “chạy thử nhiều lần chưa thấy lỗi” làm bằng chứng an toàn.

Các hướng xử lý:

1. **Ưu tiên `java.time` + `DateTimeFormatter`** khi có quyền thiết kế/migrate hệ thống.
2. Nếu buộc giữ `SimpleDateFormat`, tạo **instance riêng cho mỗi tác vụ** hoặc bảo vệ truy cập bằng đồng bộ hóa phù hợp; `ThreadLocal` có thể hữu ích nhưng đi kèm quản lý vòng đời, cấu hình, cleanup.
3. Đừng chỉ thay `static` thành `static final` rồi coi rủi ro đã được giải quyết.

Đối với mã mới:

```java
private static final DateTimeFormatter SHARED =
        DateTimeFormatter.ofPattern("dd/MM/uuuu");
```

có thể chia sẻ an toàn giữa các luồng. Tuy nhiên nên truyền `Locale` tường minh khi quy tắc có yếu tố văn bản theo ngôn ngữ để tránh phụ thuộc môi trường.

## 10. Tính thread-safe của formatter không lan sang mọi thành phần

### 10.1. Dữ liệu đầu vào và kết quả

`LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `ZonedDateTime` là các kiểu bất biến của `java.time`, rất phù hợp cho chia sẻ giá trị. Nhưng `TemporalAccessor` là một **interface**, và ứng dụng có thể cung cấp implementation riêng; đừng mặc nhiên bảo đảm mọi implementation custom đều thread-safe.

Nếu một request dùng đối tượng mutable bên ngoài hoặc gọi API khác không an toàn đồng thời, formatter an toàn **không tự sửa** vấn đề ấy. Ví dụ một bộ nhớ đệm (cache) `HashMap` bị sửa đồng thời từ nhiều luồng vẫn cần cách quản lý đúng dù các giá trị trong map là `DateTimeFormatter`.

### 10.2. Cấu hình theo request

Một formatter chung chỉ được tái sử dụng cho cùng quy tắc. Những người dùng khác nhau có thể yêu cầu:

- Locale `vi-VN` và `de-DE`.
- Zone `Asia/Ho_Chi_Minh` và `Europe/Berlin`.
- Mẫu hiển thị ngắn hoặc dài.
- Chronology hoặc decimal style khác.

Thay vì sửa một formatter chung (vốn không thể sửa trực tiếp), hãy lấy một biến thể bằng `with...`:

```java
DateTimeFormatter requestFormatter = BASE_FORMATTER
        .withLocale(userLocale)
        .withZone(userZone);

String text = requestFormatter.format(instant);
```

Đoạn trên chỉ là **trích đoạn**, dùng các biến `BASE_FORMATTER`, `userLocale`, `userZone` và `instant` giả định đã được xác định. Mỗi request nhận một cấu hình logic phù hợp, không tác động đến formatter dùng ở request khác.

### 10.3. Múi giờ, locale và thay đổi dữ liệu hệ thống

Formatter bất biến nhưng kết quả có thể còn phụ thuộc **dữ liệu vùng** (CLDR và nhà cung cấp locale), **quy tắc múi giờ** từ timezone database, version JDK, chronology và nguồn `TemporalAccessor`. Vì vậy các kết quả tên tháng/định dạng locale hoặc offset lịch sử có thể thay đổi khi cập nhật runtime. Bất biến là tính chất **đối tượng trong một tiến trình**, không bảo đảm chuỗi đầu ra giống hệt ở mọi phiên bản Java.

### 10.4. Đồng bộ hóa quanh formatter không thay thế kiểm soát nghiệp vụ

Nếu lập trình viên đặt `synchronized` quanh mọi lời gọi formatter chỉ vì formatter được dùng chung, ứng dụng có thể tự tạo điểm nghẽn vô ích. Nhưng nếu format là một phần của giao dịch cần cập nhật state chia sẻ, đồng bộ hóa **state nghiệp vụ** vẫn cần được thiết kế riêng. Đừng bỏ khóa của dữ liệu mutable khác chỉ vì formatter thread-safe.

## 11. Thiết kế cache formatter: đúng, cần thiết và đủ

Tạo formatter có thể gồm parse pattern, xây dựng cấu trúc nội bộ và cấu hình. Với các mẫu sử dụng thường xuyên, tái sử dụng là hợp lý:

```java
public final class DateFormats {
    public static final DateTimeFormatter API_DATE =
            DateTimeFormatter.ISO_LOCAL_DATE;

    public static final DateTimeFormatter UI_DATE =
            DateTimeFormatter.ofPattern(
                    "dd/MM/uuuu", Locale.US);

    private DateFormats() {
    }
}
```

Đây là **thành phần tiện ích** (không có `main`), có thể được dùng bởi các class khác. Những hằng số `DateTimeFormatter.ISO_LOCAL_DATE`, `ISO_INSTANT`, `ISO_OFFSET_DATE_TIME` đã được Java cung cấp và có thể tái sử dụng, đặc biệt cho dữ liệu máy-máy theo chuẩn.

Nếu số lượng pattern/locale/zone có giới hạn, có thể tạo một số formatter cố định theo cấu hình. Nếu cần cache động, khóa cache cần chứa **mọi chiều cấu hình ảnh hưởng ngữ nghĩa** (pattern, locale, zone, resolver style, chronology, decimal style...) và cấu trúc cache phải an toàn đa luồng, ví dụ `ConcurrentHashMap` với chính sách kiểm soát kích thước.

Không nên tạo cache vô hạn từ pattern tùy ý do người dùng nhập, vì có thể làm tăng bộ nhớ. Cũng không nên dùng một cache key chỉ có locale nếu pattern và zone khác nhau.

**Khi nào tạo formatter theo request vẫn chấp nhận được?** Khi số lượng ít, cấu hình biến thiên hoặc cần đơn giản hóa thiết kế, tạo formatter mới cho mỗi request vẫn đúng về mặt chức năng. Thread-safety cho phép chia sẻ an toàn, **không bắt buộc** mọi ứng dụng phải có một cache toàn cục.

## 12. Khi nào dùng `ofLocalizedDate` và khi nào dùng pattern cố định?

`DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)` hoặc `ofLocalizedDateTime(FormatStyle.MEDIUM)` thể hiện chủ đích **định dạng để người dùng đọc theo quy ước của locale**. Kết hợp `withLocale` để chọn ngôn ngữ/vùng của từng người dùng.

```java
DateTimeFormatter localDate =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(Locale.forLanguageTag("vi-VN"));
```

Đây là trích đoạn cần import `DateTimeFormatter`, `FormatStyle`, `Locale`. Không nên viết test đòi đúng một chuỗi cố định cho tất cả runtime nếu dữ liệu định dạng ngày theo locale có thể thay đổi.

Trong khi đó, dữ liệu giao thức như `2026-10-28` nên dùng quy tắc chuẩn và độc lập với UI:

```java
String wire = DateTimeFormatter.ISO_LOCAL_DATE
        .format(LocalDate.of(2026, 10, 28));
```

Kết quả là `2026-10-28` (đoạn này cần import `LocalDate` và `DateTimeFormatter`). Đừng dùng `Locale.getDefault()` để biến đổi ngày máy-máy theo ngôn ngữ máy chạy.

Tính immutable/thread-safe không đồng nghĩa mọi formatter có thể hoán đổi tùy tiện: một formatter chuyên để format `LocalDate` không nhất thiết có đủ trường để format `Instant` nếu chưa đặt zone; một formatter ISO date không tự bao gồm giờ và offset.

## 13. Parse an toàn đa luồng không có nghĩa luôn parse thành công

`DateTimeFormatter` là thread-safe cả khi **format** và **parse**, nhưng một chuỗi sai pattern vẫn có thể ném `DateTimeParseException`.

Ví dụ:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.US)
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate good =
        LocalDate.parse("2026-02-28", formatter);
```

Với `2026-02-30`, parse nghiêm ngặt phải thất bại. Trong ứng dụng web, cần xử lý lỗi đúng ngữ cảnh đầu vào, ghi nhận locale và pattern đang được dùng, không trả exception thô cho người dùng.

Một số nguồn dữ liệu có khoảng trắng, Unicode đặc biệt hoặc định dạng ngày giờ sai. Đừng đồng nhất “nhiều luồng cùng parse không làm hỏng formatter” với “parser chấp nhận mọi input”. Muốn kiểm tra ngữ nghĩa, cần hợp đồng riêng về năm, tháng, ngày, múi giờ, độ chính xác và kiểu `Temporal`.

Ngoài ra, các nguồn thời gian như `Clock.systemDefaultZone()` có thể phụ thuộc môi trường. Với kiểm thử, truyền `Clock.fixed(...)` hoặc dùng giá trị ngày giờ cố định để không khiến test fail chỉ vì thời gian thực thay đổi.

## 14. Các lỗi phổ biến

| Lỗi | Điều thực sự xảy ra | Cách xử lý |
| --- | --- | --- |
| Gọi `base.withLocale(locale)` nhưng bỏ giá trị trả về | `base` không đổi cấu hình | Gán biến thể mới hoặc dùng trực tiếp giá trị trả về |
| Nghĩ `withZone` sẽ đổi timezone hệ thống | Chỉ cấu hình zone override của formatter trả về | Truyền `ZoneId` rõ ràng cho từng request |
| Chia sẻ `SimpleDateFormat` trong `static final` | Tham chiếu final nhưng formatter vẫn mutable/không thread-safe | Dùng `DateTimeFormatter` hoặc bảo vệ legacy API |
| Chia sẻ cùng một `DateTimeFormatterBuilder` rồi `append...` đồng thời | Builder mutable, không có bảo đảm an toàn như formatter | Xây builder ở một luồng, `toFormatter`, sau đó chia sẻ formatter |
| Cho mọi request dùng một formatter có locale cố định | Kết quả sai ngôn ngữ người dùng dù không có race | Dùng biến thể `withLocale` theo từng request |
| Chỉ đổi locale khi cần giờ Việt Nam | Locale không quyết định múi giờ | Chọn `ZoneId` độc lập |
| Dùng `LocalDateTime` như một `Instant` | Thiếu thông tin zone/offset để xác định thời điểm | Chuyển đổi có ngữ nghĩa bằng zone phù hợp |
| Nghĩ immutable đồng nghĩa mọi `with...` luôn trả object khác | API có thể tái sử dụng instance khi cấu hình trùng | Kiểm tra hành vi, không phụ thuộc identity |
| Nghĩ `STRICT` tự là mặc định của mọi `ofPattern` | Default resolver thường là `SMART` | Chọn `withResolverStyle(STRICT)` khi cần |
| Dùng `yyyy` cùng strict parse mà không hiểu era | `yyyy` là year-of-era, không hoàn toàn giống `uuuu` | Chọn field năm thích hợp, thử các trường hợp biên |
| Dùng khóa cache chỉ có tên locale | Có thể tái sử dụng nhầm pattern/zone/resolver | Cache key phải đại diện đầy đủ cấu hình |
| Cho rằng JDK mới luôn trả tên tháng giống JDK cũ | Dữ liệu locale/tzdb có thể đổi theo version | Kiểm thử trên runtime mục tiêu |
| In trực tiếp kết quả từ các thread rồi so thứ tự dòng cố định | Thứ tự lập lịch không xác định | Ghi kết quả vào `Future` hoặc sắp theo ID trước khi khẳng định output |

## 15. Bộ kiểm thử nên có

Một thư viện định dạng ngày giờ dùng chung cho ứng dụng cần được kiểm thử ít nhất:

1. **Bất biến:** gọi `withLocale`, `withZone`, `withResolverStyle` rồi format lại bằng formatter gốc, xác nhận cấu hình cũ vẫn đúng.
2. **Đa luồng:** nhiều task dùng chung formatter để format/parse ngày cố định, bảo đảm kết quả đúng và không chia sẻ biến mutable ngoài ý muốn.
3. **Locale:** thử ít nhất các locale sản phẩm hỗ trợ; tên tháng/ngày, kiểu số và pattern localized phải đúng kỳ vọng người dùng.
4. **Zone:** cùng `Instant` cho nhiều `ZoneId` phải tạo giờ/offset phù hợp; kiểm thử cả chuyển đổi gần ngày mới.
5. **DST:** nếu hỗ trợ vùng đổi giờ mùa, thử thời điểm giao mùa và những giờ địa phương không tồn tại/trùng lặp; không giả định mỗi ngày dài đúng 24 giờ ở mọi vùng.
6. **Resolver:** input ngày không có thật, năm nhuận, tháng 0/13, ngày cuối tháng, phần dư cuối chuỗi.
7. **Pattern:** xác định `u` và `y`, kiểu `LocalDate` vs `Instant`, các trường có/không có zone.
8. **Builder:** thay builder sau `toFormatter` không ảnh hưởng formatter đã xuất bản.
9. **Hệ thống legacy:** không để `SimpleDateFormat` mutable dùng chung trái hợp đồng.
10. **Runtime:** kiểm thử bản JDK, tzdb/CLDR mà sản phẩm thực sự triển khai; tách các test “cú pháp số cố định” khỏi snapshot nhạy cảm với dữ liệu locale.

## 16. Ghi nhớ

- **`DateTimeFormatter` bất biến và an toàn đa luồng**: có thể tái sử dụng một instance hoàn chỉnh cho nhiều luồng format/parse.
- Các phương thức **`withLocale`, `withZone`, `withResolverStyle`, `withDecimalStyle`, `withChronology`** **không sửa formatter gốc**; phải dùng formatter trả về.
- **`DateTimeFormatterBuilder` mutable; `DateTimeFormatter` do nó tạo ra immutable.** Không chia sẻ builder đang được sửa giữa nhiều thread.
- **`SimpleDateFormat` không thread-safe**; `static final` không biến một đối tượng mutable thành immutable.
- **Locale, zone, chronology và resolver là các cấu hình khác nhau.** Chia sẻ formatter chỉ đúng khi các tác vụ cần cùng cấu hình; nếu khác, hãy tạo biến thể riêng theo request.
- Thread-safe là thuộc tính của **formatter**, không phải một cam kết rằng dữ liệu đầu vào, cache, state nghiệp vụ, môi trường locale/tzdb hoặc kết quả parse tự nhiên luôn đúng.
