# Phân biệt thời gian đồng hồ với thời gian trôi qua trong Java

Một ứng dụng có thể cần lưu **đơn hàng được tạo lúc 09:00**, đồng thời cần biết **HTTP request mất 180 ms**. Dù cả hai đều liên quan đến thời gian, chúng là hai câu hỏi khác nhau:

- **Thời gian đồng hồ** (*wall-clock time*, thời gian lịch): **Bây giờ là lúc nào?** Đặt sự kiện lên một trục thời gian có ý nghĩa bên ngoài chương trình; có thể trình bày theo ngày, giờ và múi giờ của người dùng.
- **Thời gian trôi qua** (*elapsed time*, khoảng thời gian đã trôi): **Có bao lâu từ lúc bắt đầu đến lúc kết thúc?** Dùng để đo độ trễ, hiệu năng, thời gian chờ và timeout. Trong cùng tiến trình, nên đo bằng nguồn thời gian chuyên cho khoảng trôi qua, chẳng hạn `System.nanoTime()`.

Nhầm hai khái niệm có thể khiến phép đo âm sau khi hệ thống chỉnh đồng hồ, timeout xảy ra sai lúc, lịch hẹn lệch một giờ khi đổi DST, hoặc báo cáo “một ngày” thành 24 giờ trong khi thực tế chỉ 23 giờ.

## 1. Hai cách nhìn một sự kiện

| Câu hỏi | Thời gian đồng hồ | Thời gian trôi qua |
| --- | --- | --- |
| Mục đích | Xác định **khi nào** sự kiện xảy ra. | Xác định **bao lâu** quá trình diễn ra. |
| Ví dụ | “Đã thanh toán lúc 2025-01-15T02:30:00Z”. | “Thanh toán xử lý trong 125 ms”. |
| Kiểu/nguồn thường dùng | `Instant.now()`, `Clock`, `System.currentTimeMillis()`; khi hiển thị có `ZoneId`, `ZonedDateTime`. | `System.nanoTime()` để lấy hai số đo, phép trừ để tính chênh lệch; `Duration` để biểu diễn độ dài. |
| Có thể hiển thị thành ngày/giờ? | Có, khi chọn múi giờ. | Bản thân độ dài không có ngày, giờ bắt đầu hoặc múi giờ. |
| Đổi múi giờ có thay đổi ý nghĩa? | `Instant` của sự kiện không đổi; giờ hiển thị đổi. | Không; 125 ms luôn là 125 ms. |
| Đồng hồ hệ thống được chỉnh/NTP đồng bộ lại? | Giá trị đọc có thể nhảy tiến/lùi. | Phép đo bằng nguồn đơn điệu thường không bị ảnh hưởng bởi chỉnh giờ tường thông thường. |
| Qua DST (đổi giờ mùa hè)? | Giờ địa phương có thể nhảy hoặc lặp; một ngày lịch có thể không dài 24 giờ. | Độ dài tính từ hai mốc thực vẫn là số giây đã trôi. |
| Có thể lưu và so sánh trên nhiều máy? | Có nếu biểu diễn mốc bằng `Instant`/timestamp theo hợp đồng chung; vẫn cần quan tâm độ lệch đồng hồ giữa các máy. | Số `nanoTime` tuyệt đối của các JVM **không so sánh được**; chỉ dùng chênh lệch trong cùng một nguồn thời gian phù hợp. |

Điểm tinh tế: **thời gian đồng hồ không đồng nghĩa chỉ với `LocalTime`**. `LocalTime.of(9, 0)` đúng là 09:00 trên mặt đồng hồ nhưng **không xác định một sự kiện thực** nếu thiếu ngày và vùng. Khi muốn biết “sự kiện xảy ra lúc nào”, dùng một `Instant` hoặc dữ liệu có đủ ngày, giờ và múi giờ để chuyển thành `Instant`. Khi muốn biết “mất bao lâu”, sử dụng một khoảng như `Duration`.

## 2. Đồng hồ hệ thống, UTC và giờ địa phương

Một đồng hồ hệ thống thông thường được đồng bộ với thời gian thực bằng hệ điều hành và có thể chịu tác động bởi quản trị viên, dịch vụ đồng bộ thời gian (NTP), đồng bộ máy ảo, hoặc cấu hình sai. Nguồn này cung cấp **thời gian lịch** để ghi nhận sự kiện, nhưng không bảo đảm mọi lần đọc liên tiếp đều tăng.

Trong Java có ba biểu diễn thường gặp:

- `System.currentTimeMillis()`: số mili giây tính từ Unix epoch `1970-01-01T00:00:00Z` theo đồng hồ hệ thống. Có thể tăng, giữ nguyên hoặc giảm giữa các lần gọi vì độ phân giải và điều chỉnh đồng hồ. Nó không chứa múi giờ địa phương.
- `Instant.now()`: mốc hiện tại trên dòng thời gian UTC theo nguồn đồng hồ hiện hành. Có thể biểu diễn giây và phần nano giây, nhưng **độ chính xác và độ phân giải thực tế phụ thuộc nền tảng**. Đây là lựa chọn thường phù hợp để lưu timestamp sự kiện.
- `Clock`: cách trừu tượng hóa nguồn đồng hồ cho API `java.time`, chẳng hạn `Clock.systemUTC()`, `Clock.system(zone)`, `Clock.fixed(instant, zone)`. Nó giúp cung cấp thời gian hiện tại và viết kiểm thử lặp lại được. **`Clock` không mặc nhiên là nguồn thời gian đơn điệu.**

Ví dụ cùng một sự kiện `2025-01-15T02:30:00Z` sẽ hiển thị `2025-01-15T09:30+07:00[Asia/Ho_Chi_Minh]` ở Việt Nam. Thay đổi múi giờ hiển thị không làm sự kiện dịch đi 7 giờ. Cần phân biệt **`Instant` (thời điểm)**, **`ZoneId` (quy tắc múi giờ)**, **`ZonedDateTime` (ngày/giờ trong vùng)**, và **`LocalDateTime` (ngày/giờ chưa gắn vùng)**.

### Khi nên dùng wall clock

1. Ghi `createdAt`, `updatedAt`, thời điểm đặt hàng, đăng nhập, nhận thông báo, sự kiện log.
2. Lưu giờ bắt đầu hoặc hết hạn có ý nghĩa với các hệ thống khác: “token hết hạn lúc 12:00 UTC”.
3. Hiển thị lịch, sổ cái, bảng giờ hoạt động, lịch họp theo múi giờ của người dùng.
4. Tra cứu sự kiện lịch sử theo khoảng timestamp; khi so sánh dữ liệu máy khác nhau cần chấp nhận hoặc kiểm soát sai lệch đồng hồ giữa các máy.
5. Tính “ngày tiếp theo lúc 09:00 ở New York” bằng quy tắc lịch và `ZoneId`; không thay bằng cộng cố định 24 giờ nếu yêu cầu là giờ địa phương.

Ví dụ API lưu timestamp:

```java
import java.time.Clock;
import java.time.Instant;

class PaymentService {
    private final Clock clock;

    PaymentService(Clock clock) {
        this.clock = clock;
    }

    Instant capturePaidAt() {
        return Instant.now(clock);
    }
}
```

Đây là **đoạn lớp dùng trong ứng dụng**, không có `main` nên không phải chương trình chạy độc lập. Việc truyền `Clock` giúp hệ thống thật dùng `Clock.systemUTC()`, còn test truyền `Clock.fixed(...)`. Để một lịch hẹn lặp theo địa phương, lưu thêm `ZoneId` và chính sách xử lý ngày/giờ không tồn tại hoặc bị lặp do DST.

## 3. Thời gian trôi qua: lấy chênh lệch từ nguồn đo khoảng trôi

Khi đo một thao tác bắt đầu ở mốc A và kết thúc ở mốc B, ta cần **độ dài giữa hai lần quan sát**, không cần biết “trên lịch đang là ngày mấy”.

`System.nanoTime()` trả về giá trị kiểu `long` từ một nguồn độ phân giải cao phục vụ **đo khoảng thời gian đã trôi trong JVM**. Mốc gốc của giá trị là tùy ý, có thể khác nhau giữa các lần chạy và không có ý nghĩa lịch. Chỉ chênh lệch của hai lần đo cùng nguồn là có ý nghĩa:

```java
long started = System.nanoTime();

performOperation();

long elapsedNanos = System.nanoTime() - started;
```

`performOperation()` là hàm minh họa, phải được định nghĩa trong chương trình thực tế. Kết quả `elapsedNanos` là nano giây đã trôi theo nguồn đo này; có thể biểu diễn bằng `Duration.ofNanos(elapsedNanos)` hoặc đổi ra mili giây bằng `TimeUnit.NANOSECONDS.toMillis(elapsedNanos)`.

**Không** gọi `Instant.ofEpochSecond(System.nanoTime())` hoặc `new Date(System.nanoTime())`: bạn đang biến một bộ đếm có gốc tùy ý thành ngày lịch và kết quả vô nghĩa. Cũng không trừ `System.currentTimeMillis()` khỏi `System.nanoTime()`: khác cả gốc thời gian lẫn đơn vị.

### Độ phân giải khác độ chính xác

- Tên `nanoTime` và đơn vị trả về là **nanosecond**, nhưng phần cứng/OS/JVM không bảo đảm mỗi nano giây lại có một tick đo riêng. Nhiều lần đọc có thể trả giá trị bằng nhau.
- Một phép đo ngắn dễ bị ảnh hưởng bởi scheduler, JIT, GC, warm-up, I/O, CPU và tải hệ thống. `nanoTime()` phù hợp ghi nhận thời gian chạy thông thường, nhưng kiểm tra vi hiệu năng cần benchmark có phương pháp (ví dụ JMH), không rút kết luận từ một lần chạy.
- `Thread.sleep(100)` chỉ yêu cầu ngủ khoảng thời gian đó; việc thread được lập lịch chạy lại, ngắt và tải hệ thống làm thời gian thực tế có thể dài hơn.
- Dùng `Duration` làm **kiểu giá trị khoảng thời gian** không đồng nghĩa `Duration.between(Instant.now(), Instant.now())` là cách đo ổn định: nếu hai `Instant` đến từ wall clock được điều chỉnh, chênh lệch có thể sai.

### Khi nên dùng elapsed time

- Đo độ trễ API, truy vấn CSDL, tác vụ CPU, thời gian giữ khóa, hiệu năng.
- Kiểm tra timeout cho thao tác đang chạy trong một tiến trình.
- Điều khiển chu kỳ retry/backoff, polling, wait một độ dài tương đối.
- Quan sát bao lâu một tác vụ ở trạng thái chờ.
- Ghi chỉ số như `processingDurationMs`, `requestLatencyNanos` với đơn vị rõ ràng.

## 4. Java 17+: ví dụ đầy đủ về thời gian đồng hồ và ngày lịch

Bài tập sau đặt đồng hồ cố định tại 12:00 ngày 09/03/2024 ở New York. Hôm sau vùng này bắt đầu DST: giờ nhảy từ 02:00 lên 03:00. Ta so **ngày hôm sau cùng giờ địa phương** với **sau đúng 24 giờ trôi**.

Tạo tệp `WallClockDemo.java`:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;

public class WallClockDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        Clock clock = Clock.fixed(Instant.parse("2024-03-09T17:00:00Z"), zone);
        Instant now = Instant.now(clock);

        ZonedDateTime local = now.atZone(zone);
        ZonedDateTime nextDay = local.plusDays(1);
        ZonedDateTime plus24Hours = local.plus(Duration.ofHours(24));

        System.out.println("UTC event       : " + now);
        System.out.println("Local event     : " + local);
        System.out.println("Next local day  : " + nextDay);
        System.out.println("Elapsed hours   : "
                + Duration.between(now, nextDay.toInstant()).toHours());
        System.out.println("Calendar days   : "
                + ChronoUnit.DAYS.between(local.toLocalDate(), nextDay.toLocalDate()));
        System.out.println("After 24 hours  : " + plus24Hours);
    }
}
```

Chạy trên JDK 17+:

```bash
javac WallClockDemo.java
java WallClockDemo
```

Kết quả đã kiểm tra:

```text
UTC event       : 2024-03-09T17:00:00Z
Local event     : 2024-03-09T12:00-05:00[America/New_York]
Next local day  : 2024-03-10T12:00-04:00[America/New_York]
Elapsed hours   : 23
Calendar days   : 1
After 24 hours  : 2024-03-10T13:00-04:00[America/New_York]
```

**Giải thích:**

- `Instant` `2024-03-09T17:00:00Z` là một thời điểm cố định và không phụ thuộc múi giờ JVM.
- `local.plusDays(1)` cộng **một ngày theo lịch địa phương**, đi tới trưa ngày kế tiếp. Lúc đó New York đã chuyển từ `-05:00` sang `-04:00`, nên chỉ **23 giờ thực** trôi qua.
- `local.plus(Duration.ofHours(24))` cộng **86.400 giây thực**, dẫn tới 13:00 giờ địa phương, không còn giữ số 12 trên đồng hồ.
- `ChronoUnit.DAYS.between(...)` trên hai `LocalDate` trả **1 ngày lịch**, còn `Duration.between(...).toHours()` trên hai mốc trả **23 giờ**. Hai kết quả cùng đúng vì đang trả lời hai câu hỏi khác nhau.

DST không làm nguồn `Instant` chạy nhanh hơn hay chậm hơn; nó thay đổi **cách ánh xạ thời điểm sang giờ địa phương**. Lúc đổi giờ mùa thu, một ngày địa phương có thể dài 25 giờ. Quy tắc khác nhau theo vùng và từng năm; chọn `ZoneId` cụ thể thay vì giả định mọi nơi đều có DST hoặc mọi ngày đều dài 24 giờ.

## 5. Java 17+: đo thời lượng thao tác và kiểm tra timeout

Ví dụ này thực sự đo thời gian giữa hai lần gọi `System.nanoTime()`. Vì có `Thread.sleep` và hệ điều hành lập lịch, số mili giây đầu tiên **không cố định**; không được lấy một lần chạy làm kết quả chuẩn cứng. Phần thứ hai mô phỏng hai tick để phép kiểm timeout có kết quả hoàn toàn xác định.

Tạo tệp `ElapsedTimeDemo.java`:

```java
import java.time.Duration;
import java.util.function.LongSupplier;

public class ElapsedTimeDemo {
    static boolean timedOut(long started, long limitNanos, LongSupplier ticks) {
        return ticks.getAsLong() - started >= limitNanos;
    }

    public static void main(String[] args) throws InterruptedException {
        long started = System.nanoTime();
        Thread.sleep(30);
        long nanos = System.nanoTime() - started;
        System.out.println("Elapsed milliseconds (varies): "
                + Duration.ofNanos(nanos).toMillis());

        long fakeStart = 1_000_000_000L;
        long fakeNow = fakeStart + Duration.ofMillis(500).toNanos();
        boolean expired = timedOut(
                fakeStart,
                Duration.ofMillis(300).toNanos(),
                () -> fakeNow
        );
        System.out.println("Synthetic timeout: " + expired);
    }
}
```

```bash
javac ElapsedTimeDemo.java
java ElapsedTimeDemo
```

Ví dụ kết quả từ một lần chạy, dòng đầu sẽ thay đổi theo máy:

```text
Elapsed milliseconds (varies): 31
Synthetic timeout: true
```

Phần tổng thời gian ngủ đo cả khoảng chờ và thời điểm scheduler chạy lại, nên con số thực tế có thể lớn hơn 30 ms. Phần kiểm thử cố định dùng **500 ms đã trôi > giới hạn 300 ms**; nhờ nguồn giả lập `LongSupplier`, ta kiểm tra logic timeout mà không phải thật sự đợi 300 ms.

Trong code thực tế có thể truyền `System::nanoTime`:

```java
long started = System.nanoTime();
long timeoutNanos = Duration.ofSeconds(2).toNanos();
boolean expired = timedOut(started, timeoutNanos, System::nanoTime);
```

Đây là **đoạn mã bổ sung nằm trong phạm vi lớp** `ElapsedTimeDemo`, nơi đã khai báo `timedOut`; nó không phải tệp chạy độc lập. Nó cho phép kiểm tra thời gian từ lúc bắt đầu, thay vì hỏi “hiện nay là mấy giờ”.

**Chú ý phép trừ:** nên so `System.nanoTime() - started >= timeoutNanos` đối với timeout dương, ngắn và hợp lý, thay vì suy diễn giá trị nanoTime thành timestamp lịch. Tài liệu Java lưu ý giá trị `nanoTime` có thể có gốc tùy ý, thậm chí âm; dùng phép trừ để đo khoảng, và không dùng để đo khoảng quá lớn (xấp xỉ từ 292 năm trở lên do giới hạn `long`). `Duration.toNanos()` cũng có thể báo tràn số nếu khoảng quá lớn. Với timeout âm/zero cần quyết định chính sách, không coi đó là cấu hình hợp lệ một cách ngầm định.

## 6. Vì sao không dùng wall clock làm đồng hồ bấm giờ?

Xét một hệ thống mà đồng hồ tường đang hiển thị 10:00:00.000 khi tác vụ bắt đầu. Sau 600 ms thực, dịch vụ đồng bộ sửa đồng hồ lùi 5 giây. Tại lúc tác vụ kết thúc, đồng hồ tường có thể đọc khoảng 09:59:55.600.

Nếu lấy `System.currentTimeMillis()` lúc cuối trừ lúc đầu, kết quả gần **-4.400 ms** dù thao tác thực sự đã chạy 600 ms. Nếu đồng hồ được chỉnh tiến một phút, chênh lệch lại lớn bất thường. Đây là ví dụ giả lập cơ chế, không phụ thuộc hệ điều hành nào phải luôn sửa đồng hồ theo cách đó.

Tương tự, một timeout tính bằng `Instant.now().isAfter(deadline)` trong tiến trình đang chạy có thể bị kéo dài hoặc rút ngắn nếu đồng hồ bị chỉnh. Với **thời lượng chờ nội bộ**, hãy lưu mốc `System.nanoTime()` và so chênh lệch.

Tuy nhiên, **timestamp của hai sự kiện lịch sử** lại nên lưu bằng `Instant`. Nếu bạn chỉ có hai timestamp được ghi trước đó, `Duration.between(createdAt, completedAt)` có thể tính **chênh lệch theo các timestamp** và có ích cho báo cáo, nhưng độ đúng của thời gian xử lý phụ thuộc đồng hồ lúc ghi. Muốn đo hiệu năng đáng tin trong tiến trình, đo riêng bằng nguồn elapsed và lưu metric khoảng trôi. Hai trường dữ liệu có thể cùng tồn tại: `createdAt: Instant` và `processingDuration: Duration`.

## 7. Ba nhu cầu thời gian thường bị lẫn

### A. Mốc hạn tuyệt đối (*absolute deadline*)

“Phiếu đăng nhập hết hạn lúc 2025-01-15T10:00:00Z” là **mốc thời gian đồng hồ**. Hệ thống khác hoặc tiến trình sau khi restart phải hiểu cùng deadline, nên lưu `Instant` hoặc epoch milliseconds có hợp đồng múi giờ rõ ràng.

Ví dụ:

```java
Instant expiresAt = Instant.parse("2025-01-15T10:00:00Z");
boolean expiredNow = !Instant.now().isBefore(expiresAt);
```

Đây là đoạn minh họa trong ngữ cảnh có `import java.time.Instant;`. Việc xác định **hiện tại** theo đồng hồ các máy vẫn phụ thuộc đồng bộ thời gian, độ lệch cho phép và chính sách hết hạn. Nếu yêu cầu token tồn tại được sau restart và phải có cùng nghĩa trên nhiều máy, không thể lưu một giá trị tuyệt đối lấy từ `nanoTime`.

### B. Ngân sách chờ tương đối (*relative timeout*)

“Chờ tối đa 2 giây kể từ khi request bắt đầu” là **khoảng trôi**. Trong tiến trình hiện tại, đánh dấu thời gian bắt đầu bằng `System.nanoTime()` và kiểm tra đã dùng hết ngân sách chưa. Nếu một request gọi nhiều dịch vụ con, nên truyền **ngân sách còn lại** để tránh mỗi lần lại tự bắt đầu một timeout mới quá dài.

Các API như `ScheduledExecutorService.schedule(task, 2, TimeUnit.SECONDS)` và `Future.get(2, TimeUnit.SECONDS)` diễn đạt thời gian chờ tương đối; chính xác khi nào task được thực thi vẫn phụ thuộc scheduler, tài nguyên và quy tắc API. Timeout không phải lời hứa hệ điều hành sẽ ngắt mọi công việc đúng từng nano giây.

### C. Quy tắc lịch (*calendar schedule*)

“Mỗi ngày làm việc lúc 09:00 tại New York” dùng ngày, giờ địa phương, `ZoneId`, quy tắc ngày làm việc và cách xử lý DST. Khoảng cách giữa hai lần chạy có thể không đúng 24 giờ. `LocalDate.plusDays(1)` hoặc các thao tác theo lịch là một bước hợp lý, nhưng tự thêm đúng 86.400 giây vào `Instant` trước đó sẽ làm giờ địa phương bị lệch tại thời điểm DST.

Đừng nhầm `Period` (năm/tháng/ngày theo lịch) với `Duration` (độ dài theo giây/nano giây), dù cả hai có thể được dịch thành “khoảng thời gian”. `Period.ofDays(1)` và `Duration.ofDays(1)` có thể dẫn tới hai thời điểm khác nhau khi cộng vào `ZonedDateTime` đi qua DST.

## 8. Nguồn thời gian nào dùng ở từng tầng?

| Tình huống | Cách dùng đề xuất | Lý do |
| --- | --- | --- |
| Lưu sự kiện theo UTC để nhiều hệ thống đọc | `Instant.now(clock)` | Có mốc trên dòng thời gian, dễ chuyển múi giờ. |
| Lưu ngày sinh, ngày nghỉ | `LocalDate` | Chỉ cần ngày lịch, không cần giờ chính xác. |
| Hiển thị giờ của sự kiện ở địa phương | `instant.atZone(zone)` | Giữ nguyên mốc, thay đổi giờ hiển thị. |
| Lịch chạy theo giờ một thành phố | `LocalDateTime` + `ZoneId` + chính sách DST | Giữ ý nghĩa lịch địa phương qua thay đổi offset. |
| Đo thời gian xử lý một đoạn code | Chênh lệch hai `System.nanoTime()` | Dùng nguồn đo khoảng trôi trong JVM. |
| Giới hạn request trong vài giây | Elapsed source, deadline tương đối | Ít chịu ảnh hưởng chỉnh wall clock. |
| Lưu deadline để áp dụng sau restart | `Instant` | Giá trị `nanoTime` không còn ý nghĩa xuyên JVM/restart. |
| Kiểm thử thời điểm “bây giờ” | Inject `Clock.fixed(...)` | Test không phụ thuộc ngày giờ thực. |
| Kiểm thử logic timeout | Inject `LongSupplier` hoặc abstraction cho ticker | Test không cần `sleep`, điều khiển tick chính xác. |
| Benchmark Java mức micro/nano | JMH với warm-up và đo thống kê | Giảm sai lệch do JIT/GC và phương pháp đo. |

Một “đồng hồ” trong nghiệp vụ có thể bao gồm **hai nguồn riêng**: `Clock` để biết “khi nào”, và một *ticker* (ví dụ `LongSupplier` gọi `System.nanoTime`) để biết “bao lâu”. Chỉ cần phân biệt bằng tên và mục đích rõ ràng; không cần tạo lớp phức tạp nếu ứng dụng đơn giản.

## 9. Kiểm thử mà không phải chờ thật

**Kiểm thử thời gian đồng hồ:** truyền một `Clock.fixed` thay cho thời gian thật:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2025-01-15T02:30:00Z"),
        ZoneOffset.UTC
);
Instant now = Instant.now(fixedClock);
// now luôn bằng 2025-01-15T02:30:00Z
```

Đây là đoạn minh họa ở phạm vi phương thức, phù hợp đưa vào một test hoặc `main`; nó không phải chương trình đầy đủ độc lập. Một test có thể kiểm tra quy tắc deadline dựa trên `Instant.now(fixedClock)` mà không phụ thuộc CI đang chạy hôm nay hay ngày mai.

**Kiểm thử khoảng trôi:** truyền một nguồn tick điều khiển được như `() -> fakeNow` ở ví dụ `ElapsedTimeDemo`. Đặt lần đầu 1.000.000.000 ns, lần sau 1.500.000.000 ns và kiểm tra timeout 300 ms đã hết. Thử thêm trường hợp 299 ms chưa hết và 300 ms vừa hết để kiểm tra ranh giới. Cách này chạy lập tức và tránh test lúc xanh lúc đỏ do `Thread.sleep`.

Không lấy `Clock.fixed` để benchmark tốc độ: nó là đồng hồ lịch cố định, đọc lặp lại sẽ luôn cùng một thời điểm. Ngược lại, không dùng `System.nanoTime` để tạo ngày/giờ kiểm thử.

## 10. Các giới hạn cần hiểu đúng

1. **Wall clock có thể bị chỉnh:** thuật toán dựa vào timestamp hiện tại cần tính đến đồng bộ NTP, clock skew và thay đổi thủ công; `Instant` không tự giải quyết sai lệch đồng hồ giữa các máy.
2. **Monotonic không phải lịch:** `System.nanoTime()` chỉ có ý nghĩa khi so chênh lệch cùng nguồn thích hợp; đừng gửi giá trị thô sang máy khác, lưu vào DB để dùng sau restart, hay chuyển nó thành giờ UTC.
3. **Không hứa độ phân giải nano giây thực:** API trả đơn vị ns, nhưng độ phân giải nguồn đo và sai số hệ điều hành có thể lớn hơn.
4. **Wall-clock time và local clock time khác nhau:** `Instant` là mốc thực trên dòng thời gian; `LocalTime` chỉ là con số đồng hồ trong ngày. Ngay cả `LocalDateTime` cũng thiếu `ZoneId`/offset để gắn với một mốc toàn cầu.
5. **DST làm lịch và elapsed chênh nhau:** qua ngày đổi giờ, “ngày tiếp theo cùng giờ” không nhất thiết “sau 24 giờ”.
6. **Không nhầm micro/milli/nano:** `currentTimeMillis` trả ms, `nanoTime` trả ns. Nhân/chia sai 1.000 hoặc 1.000.000 gây timeout sai rất lớn; ưu tiên `Duration`/`TimeUnit` và đặt tên biến kèm đơn vị.
7. **Phép toán trên `long` có giới hạn:** giá trị tick có thể âm, tràn khi tính deadline khổng lồ; so **chênh lệch** trong khoảng ngắn có giới hạn rõ. Chuyển `Duration.toNanos` cho khoảng cực lớn có thể tràn số.
8. **Thời gian chờ thực tế không chính xác tuyệt đối:** `sleep`, scheduler, thread contention, GC và I/O ảnh hưởng thời điểm thread tiếp tục, dù phép đo elapsed vẫn cho biết khoảng đã trôi.
9. **“Một ngày” cần xác định là ngày lịch hay 24 giờ:** hợp đồng nghiệp vụ nên ghi rõ, nhất là khi tính phí, chấm công, thời hạn và nhắc lịch.
10. **Thời gian sự kiện và hiệu năng cần hai dữ liệu:** log thời điểm bắt đầu bằng `Instant` và latency bằng khoảng đo `nanoTime` nếu cả hai đều cần; không bắt một timestamp duy nhất gánh cả hai ý nghĩa.

## 11. Bài tập tự kiểm tra

1. Bạn cần ghi nhận “user đăng nhập lúc nào” và “xử lý đăng nhập mất bao lâu”. Hãy chọn hai giá trị **`Instant`** và **`Duration`**; nguồn lấy duration cho thao tác đang chạy là chênh lệch `System.nanoTime()`.
2. Một dịch vụ đang đợi tối đa 500 ms. Trong lúc đợi, quản trị viên chỉnh giờ hệ thống lùi 2 phút. Timeout nội bộ nên dựa trên **elapsed source**, không lấy hai lần `System.currentTimeMillis()` để so thời lượng.
3. Một báo thức kêu mỗi ngày lúc 08:00 tại thành phố có DST. Đây là **quy tắc lịch địa phương** cần `ZoneId`, không phải luôn cộng 24 giờ vào thời điểm hôm trước.
4. Một bản ghi `expiresAt` phải được xử lý bởi dịch vụ khác sau khi máy cũ khởi động lại. Lưu **`Instant`**; giá trị `nanoTime` từ máy cũ không thể dùng làm deadline toàn cục.
5. Code đo xử lý trả `elapsedNanos = 8_500_000`. Hỏi bao nhiêu mili giây? **8,5 ms**; nếu gọi `Duration.ofNanos(elapsedNanos).toMillis()` sẽ lấy phần nguyên **8 ms**, không phải 8,5.
6. Trưa 09/03/2024 sang trưa 10/03/2024 tại New York mất bao lâu? **23 giờ trôi qua**, dù đúng **một ngày lịch**. Đây chính là khác biệt phải phân biệt trước khi chọn phép cộng và kiểu dữ liệu.

Khi viết code, hãy đặt tên theo câu hỏi cần trả lời: `createdAt`, `scheduledLocalTime`, `expiresAt` cho giá trị lịch; `elapsedNanos`, `timeoutDuration`, `latencyMs` cho khoảng trôi. **Thời gian đồng hồ trả lời “khi nào?”, thời gian trôi qua trả lời “bao lâu?”**. Chọn nguồn đo đúng theo hai câu hỏi đó là nền tảng xử lý thời gian chính xác trong Java.
