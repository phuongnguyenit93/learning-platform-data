# Vì sao không chia sẻ `SimpleDateFormat` tùy ý giữa nhiều luồng?

## 1. Vấn đề trong ứng dụng Java xử lý đồng thời

`java.text.SimpleDateFormat` là API cũ dùng để định dạng và phân tích ngày giờ dựa trên pattern như `dd/MM/yyyy`, `yyyy-MM-dd HH:mm:ss` và các quy tắc locale. Nó xuất hiện nhiều trong ứng dụng Java lâu năm, xử lý dữ liệu `Date`, báo cáo, log và tích hợp hệ thống.

Ví dụ một ứng dụng web có nhiều request chạy cùng lúc:

```java
// Ví dụ PHẢN DIỆN: không dùng chung theo cách này trong nhiều thread.
private static final SimpleDateFormat FORMAT =
        new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US);
```

Rồi nhiều luồng cùng gọi:

```java
String text = FORMAT.format(date);  // Thread A
Date value = FORMAT.parse(input);   // Thread B
```

Mẫu này **không an toàn chỉ vì biến `FORMAT` là `static final`**. `SimpleDateFormat` và lớp cha `DateFormat` chứa **trạng thái có thể thay đổi**; ngay cả các thao tác định dạng/phân tích cũng sử dụng trạng thái nội bộ. Java không bảo đảm nhiều thread được gọi `format` và `parse` đồng thời trên cùng một instance nếu thiếu đồng bộ hóa thích hợp.

Điều có thể xảy ra là kết quả sai, parser không ổn định, lỗi chỉ xuất hiện dưới tải cao hoặc một thread quan sát cấu hình do thread khác thay đổi. Một lần thử chạy thành công **không chứng minh** an toàn đa luồng.

> **Quy tắc thiết kế:** `SimpleDateFormat` nên thuộc sở hữu của một luồng/tác vụ tại một thời điểm, hoặc mọi thao tác trên instance chia sẻ phải được đồng bộ hóa nhất quán. Với mã Java mới, ưu tiên `java.time.format.DateTimeFormatter` là bất biến và thread-safe.

## 2. `SimpleDateFormat` mutable ở đâu?

`SimpleDateFormat` kế thừa `DateFormat` và sử dụng các thành phần liên quan đến ngày/giờ và số. Một số trạng thái/thiết lập đáng chú ý:

| Thành phần hoặc thao tác | Vì sao liên quan đến tính mutable? |
| --- | --- |
| `Calendar` của `DateFormat` | Tham gia tính toán các trường năm, tháng, ngày, giờ, múi giờ khi parse/format |
| `NumberFormat` liên quan | Tham gia đọc/ghi các phần có chữ số của ngày giờ |
| `applyPattern(...)` | Thay đổi pattern của formatter hiện có |
| `setTimeZone(...)` | Thay đổi múi giờ dùng để diễn giải/hiển thị |
| `setLenient(...)` | Thay đổi quy tắc chấp nhận ngày không hợp lệ |
| `setDateFormatSymbols(...)` | Thay đổi ký hiệu và tên tháng/ngày liên quan đến locale |
| `setCalendar(...)`, `setNumberFormat(...)` | Thay đổi các thành phần phục vụ parse/format |

Một instance `SimpleDateFormat` là **một đối tượng có cấu hình và trạng thái thao tác**. Bản thân `format` hay `parse` không phải phép biến đổi thuần (pure function) được API hứa hẹn thread-safe.

Hãy hình dung hai lời gọi trên **cùng một instance**:

```text
Thread A: format(dateA)             Thread B: parse(textB)
    │                                   │
    ├── cập nhật trạng thái lịch         │
    │                                   ├── dùng/cập nhật trạng thái lịch
    ├── đọc các trường lịch              │
    │                                   ├── đọc/ghi các trường của parser
    └── tạo chuỗi kết quả                └── tạo Date/kết quả
```

Sơ đồ chỉ minh họa **nguy cơ xen kẽ các thao tác trên trạng thái chung**, không phải lời khẳng định rằng mọi JDK thực hiện các bước theo chính xác thứ tự này. Điểm quan trọng là **không có hợp đồng đồng bộ nội bộ đủ cho việc chia sẻ tùy ý**.

Hậu quả có thể thay đổi theo JDK, môi trường và kiểu dữ liệu. Không nên dựa vào một lỗi cụ thể như `NumberFormatException` hoặc kết quả sai ngày để “xác nhận” rằng chỉ khi lỗi đó xuất hiện mới có race condition.

## 3. `static final` không đồng nghĩa với immutable

Có ba khái niệm thường bị nhầm:

- **`static`**: tham chiếu thuộc lớp, thường được mọi instance và thread sử dụng chung.
- **`final`**: sau khi khởi tạo, tham chiếu không được gán sang một đối tượng khác.
- **Immutable/thread-safe**: là **hợp đồng hành vi của đối tượng**; `static final` không tự biến một formatter mutable thành immutable hoặc tự đồng bộ các phương thức của nó.

Ví dụ:

```java
private static final SimpleDateFormat SHARED =
        new SimpleDateFormat("dd/MM/yyyy", Locale.US);

// Hợp lệ về mặt cú pháp Java, nhưng vẫn sửa nội dung SHARED:
SHARED.setLenient(false);
SHARED.setTimeZone(TimeZone.getTimeZone("UTC"));
SHARED.applyPattern("yyyy-MM-dd");
```

Đây là **đoạn mã minh họa**, cần các import `SimpleDateFormat`, `Locale`, `TimeZone` và nằm trong phạm vi class/method thích hợp. `final` chỉ ngăn lệnh `SHARED = new SimpleDateFormat(...)`; nó không chặn các setter.

Thậm chí khi ứng dụng **không gọi setter** sau khi khởi tạo, vẫn không nên cho rằng nhiều luồng có thể gọi `format`/`parse` song song trên cùng instance. Cấu hình đã được thiết lập một lần **không đủ** để biến lớp legacy này thành thread-safe.

### Hai kiểu lỗi khác nhau

**Tranh chấp trạng thái khi format/parse:** hai thread dùng cùng formatter cùng lúc. Kết quả có thể không ổn định do trạng thái nội bộ bị can thiệp.

**Tranh chấp cấu hình:** một thread gọi `setTimeZone`, `applyPattern` hoặc `setLenient` trong khi thread khác định dạng. Thread sau có thể dùng một cấu hình không phải của request đó. Ngay cả nếu bao riêng `format` trong khóa nhưng setter không dùng cùng khóa, thiết kế vẫn không an toàn.

## 4. Khi nào chia sẻ thực sự có rủi ro?

Một `SimpleDateFormat` **dùng cục bộ và tuần tự** hoàn toàn có thể hoạt động đúng. Rủi ro xuất hiện khi **cùng một instance** có thể được truy cập đồng thời mà không có hợp đồng bảo vệ.

| Tình huống | Đánh giá |
| --- | --- |
| Tạo formatter trong một phương thức, chỉ thread đó dùng rồi bỏ | Phù hợp, không có trạng thái formatter chung |
| Một thread duy nhất sử dụng formatter qua nhiều thao tác tuần tự | Không có race giữa các thread trên formatter đó |
| Một formatter lưu trong singleton rồi nhiều request cùng `format` | **Không an toàn** nếu không bảo vệ toàn bộ truy cập |
| Một formatter `static final`, nhiều thread chỉ gọi `parse` | Vẫn **không được bảo đảm an toàn** |
| `synchronized` quanh **mọi** truy cập formatter dùng chung | Có thể bảo vệ tính đúng đắn, nhưng tuần tự hóa thao tác |
| Mỗi thread có formatter riêng qua `ThreadLocal` và quản lý vòng đời | Có thể dùng được, nhưng thêm chi phí/quản lý trạng thái |
| Một `DateTimeFormatter` immutable dùng chung | Được thiết kế thread-safe theo hợp đồng `java.time` |

“Chỉ đọc” dễ gây hiểu lầm ở đây: `FORMAT.format(date)` có vẻ chỉ đọc `date`, nhưng **phương thức của đối tượng formatter mutable** không được hứa hẹn là read-only đối với mọi trạng thái nội bộ.

Trong ứng dụng dùng thread pool, các tác vụ có thể tái sử dụng thread hoặc chạy song song khác thời điểm. Không nên suy luận một formatter an toàn chỉ từ việc các lần thử tình cờ không trùng nhau.

## 5. Ví dụ phản diện: formatter chung không bảo vệ

Ví dụ dưới chỉ nhằm chỉ ra thiết kế cần tránh; **không có đầu ra được cam kết** và không nên dùng làm mã production:

```java
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class UnsafeSharedFormatter {
    private static final SimpleDateFormat SHARED =
            new SimpleDateFormat(
                    "yyyy-MM-dd HH:mm:ss", Locale.US);

    public static String render(Date date) {
        // Nhiều thread gọi đồng thời: không được bảo đảm an toàn.
        return SHARED.format(date);
    }
}
```

Class này biên dịch được nhưng không có `main`; nó minh họa cách một dịch vụ có thể vô tình chia sẻ trạng thái formatter qua biến `static`.

Có thể cả nghìn lần thử đều ra đúng; không vì thế mà mã hợp lệ về concurrency. Nếu lỗi xuất hiện, nó còn có thể bị ảnh hưởng bởi dữ liệu đầu vào, scheduling, JIT và implementation JDK. **Không xây dựng unit test yêu cầu race phải xảy ra**; concurrency bug là vi phạm hợp đồng, không nhất thiết có biểu hiện ổn định.

## 6. Cách 1: tạo `SimpleDateFormat` mới cho mỗi tác vụ

Đây là cách đơn giản nhất nếu phải dùng API cũ nhưng lượng thao tác không quá lớn: **không chia sẻ formatter**.

Tạo tệp **`TaskLocalSimpleDateFormatDemo.java`**:

```java
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class TaskLocalSimpleDateFormatDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(3);

        try {
            List<Callable<String>> tasks = new ArrayList<>();

            for (int i = 0; i < 3; i++) {
                final int id = i;
                tasks.add(() -> {
                    // Mỗi task sở hữu formatter riêng của nó.
                    SimpleDateFormat formatter =
                            new SimpleDateFormat(
                                    "yyyy-MM-dd HH:mm:ss", Locale.US);
                    formatter.setTimeZone(TimeZone.getTimeZone("UTC"));
                    formatter.setLenient(false);

                    Date instant = new Date(id * 1000L);
                    String text = formatter.format(instant);
                    Date parsed = formatter.parse(text);

                    return "task-" + id + ": " + text
                            + " -> " + parsed.getTime();
                });
            }

            List<Future<String>> futures = executor.invokeAll(tasks);
            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 TaskLocalSimpleDateFormatDemo.java
java -cp . TaskLocalSimpleDateFormatDemo
```

Kết quả:

```text
task-0: 1970-01-01 00:00:00 -> 0
task-1: 1970-01-01 00:00:01 -> 1000
task-2: 1970-01-01 00:00:02 -> 2000
```

**Vì sao an toàn cho formatter?** Mỗi `Callable` tạo một instance `SimpleDateFormat` riêng, cấu hình UTC và không đưa instance đó cho thread khác. Không có formatter mutable dùng chung.

Thứ tự thực thi các task không được bảo đảm, nhưng chương trình thu các `Future` theo thứ tự gửi đi rồi mới in, nên stdout ở ví dụ được giữ ổn định. Múi giờ được đặt rõ thành UTC để không phụ thuộc múi giờ của máy.

**Đổi lại:** mỗi lần gọi cần khởi tạo formatter. Với nhu cầu lượng lớn, có thể đánh giá hiệu năng thực tế; không tối ưu quá sớm bằng việc đưa cùng một formatter mutable vào biến toàn cục.

## 7. Cách 2: đồng bộ hóa nhất quán khi dùng chung formatter

Khi không thể thay kiến trúc ngay, một khóa chung có thể bảo vệ một instance `SimpleDateFormat`. Điều kiện là **mọi** đường truy cập — cả `format`, `parse` và các setter có thể thay trạng thái — phải theo cùng một chính sách đồng bộ.

Tạo tệp **`SynchronizedLegacyDemo.java`**:

```java
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SynchronizedLegacyDemo {
    private static final Object FORMAT_LOCK = new Object();

    private static final SimpleDateFormat SHARED =
            new SimpleDateFormat(
                    "yyyy-MM-dd HH:mm:ss", Locale.US);

    static {
        SHARED.setTimeZone(TimeZone.getTimeZone("UTC"));
        SHARED.setLenient(false);
    }

    private static String renderAndParse(int id) throws Exception {
        Date date = new Date(id * 1000L);

        synchronized (FORMAT_LOCK) {
            // Cả format và parse cùng được bảo vệ bởi một khóa.
            String text = SHARED.format(date);
            Date parsed = SHARED.parse(text);
            return "task-" + id + ": " + text
                    + " -> " + parsed.getTime();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(3);

        try {
            List<Callable<String>> tasks = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                final int id = i;
                tasks.add(() -> renderAndParse(id));
            }

            List<Future<String>> futures = executor.invokeAll(tasks);
            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SynchronizedLegacyDemo.java
java -cp . SynchronizedLegacyDemo
```

Kết quả:

```text
task-0: 1970-01-01 00:00:00 -> 0
task-1: 1970-01-01 00:00:01 -> 1000
task-2: 1970-01-01 00:00:02 -> 2000
```

**Điều kiện an toàn rất quan trọng:** các phương thức/đường mã khác không được gọi `SHARED.format`, `SHARED.parse`, `SHARED.setTimeZone` hoặc `SHARED.applyPattern` ngoài khóa mà bạn quy định. Nếu chỉ một nhánh mã bỏ qua khóa, race vẫn có thể xảy ra.

**Chi phí:** nhiều request phải lần lượt đi qua cùng một vùng khóa, có thể tạo điểm nghẽn nếu tải lớn. Không nên coi `synchronized` là phương án tối ưu mặc định cho mọi ứng dụng. Và việc khóa **chính formatter** (`synchronized (SHARED)`) cũng chỉ đúng khi mọi nơi thống nhất dùng đúng monitor đó; một đối tượng khóa riêng thường giúp kiểm soát phạm vi truy cập rõ hơn.

## 8. Cách 3: `ThreadLocal<SimpleDateFormat>` — hữu ích nhưng cần quản lý vòng đời

`ThreadLocal` tạo mối liên hệ giữa **mỗi thread** và **một giá trị riêng**. Nếu mỗi thread lấy formatter của chính nó, các thao tác trên formatter đó không tranh chấp trực tiếp với formatter của thread khác.

Ví dụ một lớp tiện ích có thể viết:

```java
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public final class LegacyThreadLocalFormats {
    private static final ThreadLocal<SimpleDateFormat> FORMATTER =
            ThreadLocal.withInitial(() -> {
                SimpleDateFormat f = new SimpleDateFormat(
                        "yyyy-MM-dd HH:mm:ss", Locale.US);
                f.setTimeZone(TimeZone.getTimeZone("UTC"));
                f.setLenient(false);
                return f;
            });

    public static String format(Date date) {
        return FORMATTER.get().format(date);
    }

    public static void clearCurrentThread() {
        FORMATTER.remove();
    }

    private LegacyThreadLocalFormats() {
    }
}
```

Đây là một **class tiện ích biên dịch được nhưng không có `main`**; nó minh họa một hướng thiết kế, không phải bài chạy độc lập.

Cần cân nhắc:

- Trong **thread pool**, thread có thể sống lâu và phục vụ nhiều request. Formatter của thread sẽ tồn tại và được tái sử dụng; điều này có thể tốt cho hiệu năng nhưng cũng khiến **cấu hình hoặc trạng thái gắn với request cũ bị rò sang request sau** nếu code sửa formatter.
- Khi cần giải phóng trạng thái theo vòng đời request/task, dùng `remove()` trong `finally` tại ranh giới thích hợp. Sau khi remove, lần `get()` kế tiếp sẽ tạo formatter mới.
- Nếu locale/zone/pattern thay đổi theo request, một formatter `ThreadLocal` cấu hình cố định **không tự đáp ứng** từng người dùng. Không nên đổi timezone của giá trị trong thread rồi quên reset.
- `ThreadLocal` không phải phép thay thế cho kiến trúc bất biến và làm tăng công việc kiểm soát memory/vòng đời, đặc biệt trong application server hoặc thread pool sống lâu.

Nếu chỉ cần format một ngày trong request, tạo formatter mới hoặc dùng `DateTimeFormatter` thường ít rủi ro hơn duy trì `ThreadLocal`.

## 9. Cách 4 được khuyến nghị cho mã mới: `DateTimeFormatter`

API `java.time.format.DateTimeFormatter` được thiết kế **immutable** và **thread-safe**. Một formatter đã tạo có thể được gọi đồng thời từ nhiều thread; không cần `synchronized` hoặc `ThreadLocal` chỉ để bảo vệ formatter.

Đối với ngày giờ UTC, sử dụng cùng `Instant` từ epoch và một formatter chia sẻ:

Tạo **`ModernFormatterConcurrencyDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ModernFormatterConcurrencyDemo {
    private static final DateTimeFormatter SHARED =
            DateTimeFormatter.ofPattern(
                    "uuuu-MM-dd HH:mm:ss XXX", Locale.US)
                    .withZone(ZoneOffset.UTC);

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(3);

        try {
            List<Callable<String>> tasks = new ArrayList<>();

            for (int i = 0; i < 3; i++) {
                final int id = i;
                tasks.add(() -> {
                    Instant instant = Instant.ofEpochSecond(id);
                    String text = SHARED.format(instant);
                    Instant parsed = Instant.from(SHARED.parse(text));

                    return "task-" + id + ": " + text
                            + " -> " + parsed.getEpochSecond();
                });
            }

            List<Future<String>> futures = executor.invokeAll(tasks);
            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ModernFormatterConcurrencyDemo.java
java -cp . ModernFormatterConcurrencyDemo
```

Kết quả:

```text
task-0: 1970-01-01 00:00:00 Z -> 0
task-1: 1970-01-01 00:00:01 Z -> 1
task-2: 1970-01-01 00:00:02 Z -> 2
```

Khác biệt:

1. `SHARED` là cùng một formatter mà tất cả task sử dụng đồng thời theo **hợp đồng an toàn đa luồng**.
2. `Instant` bất biến và biểu diễn một thời điểm tuyệt đối; `withZone(ZoneOffset.UTC)` cung cấp múi giờ cần thiết để in thời gian.
3. Phép parse có offset `XXX`, nên có thể lấy `Instant` từ kết quả parsed. Nếu pattern chỉ có giờ/ngày mà không có zone/offset, không nên mặc định có đủ thông tin để chuyển thành thời điểm tuyệt đối.
4. Kết quả được lấy qua các `Future` theo thứ tự, tránh phụ thuộc lịch chạy của executor.

### Cách chuyển từ `Date` sang `java.time`

Khi API cũ trả về `java.util.Date`, có thể chuyển sang `Instant`:

```java
Date legacyDate = new Date(0L);
Instant instant = legacyDate.toInstant();
```

Đây là **trích đoạn** cần import `java.util.Date` và `java.time.Instant`. Có thể format `instant` bằng `DateTimeFormatter` đã cấu hình zone.

Ngược lại, khi một API legacy bắt buộc nhận `Date`, có thể dùng `Date.from(instant)`. Nhưng chuyển đổi kiểu dữ liệu **không tự xác định locale, zone hay pattern**. Khi migrate, cần đảm bảo ngữ nghĩa thời gian và dữ liệu đầu vào vẫn đúng.

## 10. Không nhầm pattern và kiểu thời gian khi migrate

`SimpleDateFormat` dùng pattern như `yyyy-MM-dd`; `DateTimeFormatter` cũng có các ký tự tương tự nhưng **không bảo đảm mọi ký tự mang ngữ nghĩa giống hệt** ở hai API.

Ví dụ:

- `DateTimeFormatter` có `u` cho **proleptic year**, còn `y` là **year-of-era**. Với parser `ResolverStyle.STRICT`, `uuuu` thường thích hợp hơn `yyyy` khi đọc ngày lịch Gregorian không có era.
- `SimpleDateFormat` dùng `Date`/`Calendar`, trong khi API mới khuyến nghị `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime` hoặc `Instant` tùy ý nghĩa.
- `LocalDateTime` **không phải `Instant`**. Nó không có zone/offset; muốn chuyển sang thời điểm tuyệt đối cần một zone hoặc offset được chọn theo nghiệp vụ.
- Locale và zone là **hai cấu hình khác nhau**. Ngôn ngữ Việt Nam không bắt buộc người dùng đang ở múi giờ `Asia/Ho_Chi_Minh`.
- Để parse ngày không hợp lệ, `SimpleDateFormat.setLenient(false)` và `DateTimeFormatter.withResolverStyle(ResolverStyle.STRICT)` là hai cách thuộc hai API khác nhau; cần kiểm thử các trường hợp biên trước khi coi việc migrate tương đương.

Vì vậy, đổi tên class và copy nguyên pattern không phải một chiến lược migration đầy đủ. Nên kiểm thử cả format, parse, timezone, ngày nhuận, lịch và hành vi error.

## 11. Locale và timezone trong một dịch vụ đa người dùng

Vấn đề chia sẻ formatter còn nguy hiểm hơn nếu ứng dụng dùng cùng `SimpleDateFormat` rồi **thay đổi cấu hình cho từng request**:

```java
// PHẢN DIỆN: hai request thay đổi cùng một object.
SHARED.setTimeZone(userTimeZone);
String text = SHARED.format(date);
```

Một request A có thể đặt `Asia/Ho_Chi_Minh`, nhưng trước khi A gọi `format`, request B thay nó thành `Europe/Berlin`. Kết quả của A có thể dùng timezone của B. Đây là vấn đề **state chia sẻ trong cấu hình**, khác với race do các thao tác format/parse nội bộ.

Thiết kế phù hợp:

- Với legacy API, tạo formatter **riêng theo request** với `Locale` và `TimeZone` của request; không đặt timezone của formatter toàn cục qua mỗi request.
- Với API mới, tạo formatter gốc bất biến rồi lấy biến thể từ `withLocale(userLocale)` và `withZone(userZone)`. Hai phương thức trả một formatter có cấu hình mới mà **không sửa đối tượng gốc**.
- Không gọi `Locale.setDefault` hoặc `TimeZone.setDefault` theo từng request; các giá trị default này là trạng thái JVM có thể ảnh hưởng các luồng khác.

Trích đoạn có `DateTimeFormatter`:

```java
DateTimeFormatter perRequest = BASE
        .withLocale(userLocale)
        .withZone(userZone);
String text = perRequest.format(instant);
```

Đây là **đoạn mã minh họa**, giả định `BASE`, `userLocale`, `userZone`, `instant` đã được khai báo. Tính bất biến cho phép mỗi request có cấu hình riêng mà không gây đột biến trên formatter gốc.

Một lựa chọn lưu cache formatter theo pattern/locale/zone cũng khả thi, miễn cấu trúc cache an toàn đa luồng và khóa cache chứa **đầy đủ những chiều cấu hình ảnh hưởng kết quả**. Không tạo cache không giới hạn từ chuỗi pattern tùy ý của người dùng.

## 12. Các tình huống lỗi thực tế và cách phân biệt

### 12.1. Đầu ra sai không lặp lại được

Triệu chứng: cùng ngày/giờ nhưng đôi khi formatter chung cho chuỗi khác, hoặc parser nhận kết quả không ổn định dưới tải. Nguyên nhân có thể liên quan tới truy cập đồng thời vào trạng thái mutable, nhưng cần kiểm tra dữ liệu, locale, timezone và các setter trước khi kết luận. Không chỉ sửa bằng cách thay đổi thứ tự task hoặc thêm `sleep`.

### 12.2. Lỗi parser ngẫu nhiên

Khi các luồng đồng thời gọi `parse`, trạng thái nội bộ của formatter cũ có thể bị can thiệp. Một số triển khai/hành vi có thể dẫn tới exception hoặc giá trị không như mong đợi. Không ghi một **loại exception cố định** làm hệ quả bắt buộc ở mọi JDK; không có bảo đảm lỗi sẽ xuất hiện ở lần chạy nào.

### 12.3. Cùng formatter nhưng timezone đổi giữa các request

Vấn đề này thường dễ suy luận từ `setTimeZone`: setter thay một **đối tượng chia sẻ**. Ngay cả khi không có lỗi parser, kết quả có thể sai vùng giờ. Giải pháp là cấu hình theo request hoặc áp dụng đồng bộ và chính sách chia sẻ nghiêm ngặt.

### 12.4. Formatter được đồng bộ nhưng một helper khác bỏ qua khóa

Giả sử controller đồng bộ `format` nhưng một background task gọi `SHARED.parse(...)` trực tiếp. Thiết kế vẫn có race. Một cách ngăn ngừa là bọc formatter trong **dịch vụ có API duy nhất** và không để lộ trực tiếp instance mutable ra bên ngoài; mọi truy cập đều được điều phối thống nhất.

### 12.5. Đổi sang `DateTimeFormatter` nhưng vẫn có lỗi đồng thời

Hãy kiểm tra phần khác của hệ thống: `HashMap` bị sửa đồng thời, dữ liệu thời gian mutable do API legacy trả về, các cấu hình `Locale`/`TimeZone` default bị đổi toàn cục, hoặc chia sẻ một `DateTimeFormatterBuilder` vẫn đang được chỉnh sửa.

`DateTimeFormatter` an toàn **không làm tất cả mã xung quanh tự động an toàn**.

## 13. Đo và kiểm thử concurrency sao cho có ý nghĩa

Một phép thử tạo nhiều thread, lặp 10.000 lần rồi không thấy lỗi là tín hiệu hữu ích về một lần chạy, nhưng **không có giá trị chứng minh** lớp `SimpleDateFormat` thread-safe. Race condition có thể phụ thuộc scheduling, CPU/JVM, tải hệ thống và đường mã cụ thể.

Thay vì tìm lỗi ngẫu nhiên bằng mọi giá, hãy tổ chức QA:

1. **Rà soát ownership:** formatter được tạo ở đâu, lưu tại `static`, singleton, bean Spring, thread pool hay scope cục bộ?
2. **Tìm mọi đường gọi:** `format`, `parse`, `applyPattern`, `setTimeZone`, `setLenient`, `setCalendar`... trên cùng instance.
3. **Phân loại cách bảo vệ:** per-task, thread confinement, synchronized toàn bộ, hoặc migrate sang immutable.
4. **Dùng dữ liệu cố định:** `Date(0)`, mốc UTC, locale rõ ràng; không phụ thuộc clock và default timezone của CI.
5. **Thu kết quả có thứ tự:** với executor, thu `Future` rồi so sánh expected, tránh thất bại chỉ vì thứ tự log khác nhau.
6. **Kiểm thử định dạng và parse:** không chỉ gọi `format` mà bỏ qua nhánh `parse`; các nhánh xử lý có thể dùng trạng thái khác nhau.
7. **Kiểm thử cấu hình theo request:** ít nhất hai zone/locale và trường hợp nhiều request đồng thời, đặc biệt nếu code cũ từng dùng setter trên formatter dùng chung.
8. **Kiểm thử sau migrate:** định dạng ngày, giờ, năm nhuận, DST, ngày không hợp lệ, dấu vùng giờ và ngôn ngữ. So sánh hợp đồng nghiệp vụ, không chỉ chuỗi trong một môi trường.
9. **Đo hiệu năng sau khi đúng:** benchmark phương án per-call, synchronized, `ThreadLocal`, `DateTimeFormatter` trên workload thực tế; không lựa chọn giải pháp nguy hiểm chỉ vì giả định tạo formatter tốn tài nguyên.

Các ví dụ chạy được ở phần 6–9 có output ổn định nhờ thiết lập UTC và lấy kết quả theo thứ tự. Một stress test cố tình dùng cùng formatter **không đồng bộ** nếu được viết thêm chỉ nên dùng để **tái hiện rủi ro**, không đưa vào chương trình nghiệp vụ, không tự tuyên bố “chạy đúng một lần là an toàn”.

## 14. Câu hỏi thường gặp

**Có thể dùng `SimpleDateFormat` trong một method bình thường không?**

Có. Nếu formatter được tạo và dùng bởi một tác vụ tại một thời điểm, không bị công bố ra cho các thread khác, việc sử dụng tuần tự là bình thường. Vấn đề là **cùng instance bị truy cập đồng thời**.

**Chỉ gọi `format`, không dùng `parse`, thì có an toàn không?**

Không được bảo đảm. Hợp đồng của `SimpleDateFormat` không cho phép suy ra rằng các lời gọi `format` song song trên cùng đối tượng mutable là thread-safe.

**`static final` có bảo đảm không?**

Không. `final` chỉ cố định tham chiếu, không ngăn object thay đổi trạng thái nội bộ hoặc bị setter thay cấu hình.

**Chỉ thêm `synchronized` vào một method gọi formatter được không?**

Chỉ khi **mọi** đường truy cập cùng instance đều đi qua cùng khóa và không có chỗ nào sửa trạng thái ngoài khóa. Nếu application lộ instance cho bên khác gọi trực tiếp, bảo đảm dễ bị phá vỡ. Đồng bộ hóa toàn bộ cũng có thể gây nghẽn.

**`ThreadLocal` có phải lúc nào cũng tốt hơn tạo mới?**

Không. Nó giảm tạo object trong một số tình huống nhưng cần quản lý lifecycle, xóa state phù hợp và ngăn rò cấu hình giữa các request trong thread pool. Tạo mới thường dễ kiểm chứng hơn.

**`DateTimeFormatter` có an toàn khi nhiều thread cùng dùng không?**

Có, theo hợp đồng API; nó bất biến và thread-safe. Nhưng mỗi thread vẫn cần dữ liệu thời gian và cấu hình locale/zone đúng, đồng thời mã xung quanh phải quản lý các trạng thái mutable khác một cách riêng biệt.

**Có thể dùng `SimpleDateFormat` mãi nếu đã khóa đúng không?**

Có thể giữ tạm trong hệ thống legacy khi mọi truy cập được kiểm soát và hiệu năng chấp nhận được. Tuy nhiên, với mã mới hoặc lần nâng cấp đáng kể, `java.time` thường cho mô hình dữ liệu rõ hơn và tránh được nguy cơ chia sẻ formatter mutable.

## 15. Bảng chọn giải pháp

| Giải pháp | Độ an toàn khi thực hiện đúng | Chi phí / giới hạn | Khi nào cân nhắc |
| --- | --- | --- | --- |
| Tạo `SimpleDateFormat` trong từng task | Không chia sẻ formatter mutable | Có chi phí khởi tạo | Sửa nhanh, đơn giản, lượng tải phù hợp |
| `synchronized` mọi truy cập chung | An toàn nếu mọi đường dùng cùng khóa | Tuần tự hóa, dễ bỏ sót một code path | Legacy khó sửa, cần kiểm soát một chỗ |
| `ThreadLocal<SimpleDateFormat>` | Mỗi thread có formatter riêng | Quản lý vòng đời, cấu hình và cleanup | Có lý do đo đạc rõ trong hệ thống legacy |
| `DateTimeFormatter` dùng chung | Immutable, thread-safe theo API | Phải migrate kiểu ngày/pattern/zone có ý nghĩa | Phương án ưu tiên cho mã Java hiện đại |

## 16. Ghi nhớ

- **`SimpleDateFormat` là formatter mutable, không thread-safe.** Các thao tác `format` và `parse` trên cùng instance không được chia sẻ tùy ý giữa nhiều thread.
- **`static final` cố định tham chiếu chứ không bất biến hóa đối tượng.** Vẫn có race khi dùng formatter legacy chung.
- **Cách tránh rủi ro:** tạo formatter riêng cho từng tác vụ, đồng bộ hóa **mọi** truy cập, hoặc quản lý một instance theo từng thread với vòng đời rõ ràng.
- **Khuyến nghị cho mã mới:** dùng `java.time.format.DateTimeFormatter` bất biến và thread-safe; vẫn cần chọn đúng loại thời gian, locale, zone và pattern.
- **Đừng lấy kết quả của stress test làm hợp đồng an toàn.** Không thấy lỗi không có nghĩa thread-safe; chất lượng thiết kế dựa trên API contract và việc quản lý trạng thái chia sẻ đúng cách.
