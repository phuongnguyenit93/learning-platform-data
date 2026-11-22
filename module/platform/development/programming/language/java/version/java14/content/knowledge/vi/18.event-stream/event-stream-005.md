# Đặt khoảng thời gian bằng setStartTime và setEndTime trong Java JFR EventStream

## 1. Mục tiêu: đọc đúng phần sự kiện JFR cần phân tích

**Java Flight Recorder (JFR)** thu thập sự kiện hoạt động của JVM và ứng dụng: GC, CPU, thread, cấp phát bộ nhớ, I/O và các **custom events**. API `jdk.jfr.consumer.EventStream` cho phép đăng ký callback xử lý sự kiện, đọc từ tệp recording `.jfr` hoặc từ JFR repository.

Khi ứng dụng chỉ cần phân tích một khoảng thời gian, chẳng hạn vài phút xảy ra lỗi, hai phương thức của `EventStream` rất hữu ích:

~~~java
void setStartTime(java.time.Instant startTime);
void setEndTime(java.time.Instant endTime);
~~~

- **`setStartTime(Instant)`** xác định **mốc bắt đầu** của luồng sự kiện được xử lý.
- **`setEndTime(Instant)`** xác định **mốc kết thúc** của luồng; tài liệu Java quy định **đến end time, stream được đóng**.
- Cả hai phải được gọi **trước khi `start()` hoặc `startAsync()`**. Gọi khi stream đã bắt đầu sẽ gây `IllegalStateException`.
- `Instant` là mốc tuyệt đối trên timeline; không phải chuỗi thời gian cục bộ, thời lượng tương đối hay số phút tính từ lúc gọi API.

Mẫu sử dụng:

~~~java
try (EventStream stream = EventStream.openFile(path)) {
    stream.setStartTime(from);
    stream.setEndTime(to);
    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(event.getEndTime());
    });
    stream.start();
}
~~~

Đây là **mảnh mã minh họa**: cần các import, `Path path` chỉ tới tệp JFR có thật và `Instant from/to` đã được tính. Chương trình **chạy độc lập hoàn chỉnh** nằm ở mục 6.

API `EventStream` có từ **Java 14** và tiếp tục được hỗ trợ trong các JDK hiện đại. Bài sử dụng **Java 17+**, không cần preview flag hoặc những cách viết đã lỗi thời.

## 2. Phân biệt ba khái niệm thời gian

| Khái niệm | Đại diện Java | Dùng để làm gì? |
| --- | --- | --- |
| Thời điểm muốn **bắt đầu đọc stream** | `Instant from` → `setStartTime(from)` | Chọn mốc bắt đầu tiêu thụ sự kiện |
| Thời điểm muốn **kết thúc stream** | `Instant to` → `setEndTime(to)` | Giới hạn điểm cuối, stream tự đóng khi tới mốc |
| Thời gian **của mỗi sự kiện** | `RecordedEvent.getStartTime()`, `getEndTime()`, `getDuration()` | Phân tích sự kiện xảy ra lúc nào và dài bao lâu |

**Không đồng nhất mốc của stream với timestamp của tất cả các sự kiện.**

Một sự kiện kiểu duration có thể bắt đầu lúc `10:00:00` và kết thúc `10:00:05`. Nếu muốn tìm “mọi thao tác **chồng lấn** khoảng 10:00:02–10:00:04”, đó là **chính sách phân tích của ứng dụng** cần diễn đạt rõ bằng `getStartTime()` và `getEndTime()`. Không nên tự suy rằng chỉ gọi hai setter có nghĩa là mọi sự kiện được báo đều **bắt đầu và kết thúc hoàn toàn trong khoảng đó**.

Với **instant event** (sự kiện tức thời), tài liệu `RecordedEvent` cho biết `getStartTime()` bằng `getEndTime()`. Với duration event, hai mốc có thể khác nhau.

Trong ứng dụng có yêu cầu **chính xác ngữ nghĩa biên** (ví dụ [from, to) hay [from, to]), hãy bổ sung phép so sánh timestamp **tường minh trong callback**, đồng thời dùng `setStartTime/setEndTime` để giới hạn việc stream tiêu thụ dữ liệu. Các setter không phải hợp đồng truy vấn SQL bảo đảm mọi quy tắc nghiệp vụ về biên thời gian.

## 3. Cú pháp và vòng đời: phải đặt trước khi chạy

Cách dùng đúng, theo thứ tự:

~~~java
EventStream stream = EventStream.openFile(file);
try (stream) {
    stream.setStartTime(from);
    stream.setEndTime(to);
    stream.onEvent("demo.Order", event -> process(event));
    stream.start();
}
~~~

Đây là ví dụ **mảnh mã**, với `file` là `Path`, `process` là hàm do ứng dụng định nghĩa.

Trình tự:

1. **Mở stream** phù hợp nguồn dữ liệu: `openFile`, `openRepository` hoặc loại stream chuyên dụng.
2. **Thiết lập cửa sổ thời gian** trước khi stream bắt đầu.
3. **Đăng ký callback** theo event name với `onEvent(String, Consumer)`.
4. **Bắt đầu xử lý** bằng `start()` (đồng bộ) hoặc `startAsync()` (bất đồng bộ).
5. **Đóng stream** bằng try-with-resources, hoặc cơ chế kết thúc thích hợp.

### Sai: thay mốc thời gian sau khi start

~~~java
// Cố ý sai về vòng đời:
EventStream stream = EventStream.openFile(file);
stream.startAsync();
stream.setStartTime(from); // IllegalStateException.
~~~

Hai phương thức `setStartTime` và `setEndTime` đều yêu cầu thiết lập trước khi stream chạy. Không thể dùng chúng để **“nhảy” sang một khoảng khác trong cùng một stream đang phát sự kiện**.

Nếu cần tra một cửa sổ khác trong **cùng tệp JFR**, đóng stream cũ rồi tạo **EventStream mới**, cấu hình mốc mới và khởi chạy. Với nguồn repository đang thay đổi, dữ liệu cũ có thể đã bị luân chuyển/xóa, nên việc mở stream mới **không bảo đảm** đọc lại toàn bộ lịch sử.

### `start()` và `startAsync()`

| API | Cơ chế | Cách dùng phù hợp |
| --- | --- | --- |
| `start()` | Dispatch các callback trong thread gọi; chạy cho tới khi nguồn kết thúc hoặc stream được đóng | Đọc hết một tệp `.jfr` hữu hạn, dễ kiểm thử và tổng hợp kết quả |
| `startAsync()` | Dispatch callback trong một thread riêng | Quan sát nguồn đang chạy, GUI, service cần tiếp tục làm việc |
| `awaitTermination(Duration)` | Chờ stream hoàn thành/đóng hoặc tới timeout/ngắt thread | Chờ nguồn bất đồng bộ một cách có giới hạn |
| `close()` | Yêu cầu đóng/giải phóng tài nguyên, có thể dừng ở flush kế tiếp | Dọn dẹp khi không cần thêm dữ liệu |

Không gọi `start()` lần thứ hai trên cùng stream đã bắt đầu/đã đóng. Với callback bất đồng bộ, cần bảo vệ dữ liệu dùng chung theo quy tắc concurrency; `ArrayList` thông thường không nên được đọc/ghi đồng thời tùy ý. Ví dụ mục 6 cố ý dùng **`start()` đồng bộ** để dễ kiểm tra chính xác stdout.

## 4. Mốc thời gian là `Instant`, không phải múi giờ hiển thị

Kiểu đối số:

~~~java
import java.time.Instant;

Instant from = Instant.parse("2026-11-07T02:00:00Z");
Instant to = Instant.parse("2026-11-07T02:05:00Z");
~~~

Chữ `Z` chỉ **UTC offset +00:00**. Hai `Instant` là hai mốc tuyệt đối, không phụ thuộc vào múi giờ mặc định của máy chủ đang chạy.

Nếu người dùng cung cấp thời gian địa phương (ví dụ `09:00` ở một khu vực), hãy **gắn ZoneId đúng** rồi chuyển sang `Instant`:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.Instant;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = LocalDateTime.of(2026, 11, 7, 9, 0)
        .atZone(zone).toInstant();
Instant to = LocalDateTime.of(2026, 11, 7, 9, 5)
        .atZone(zone).toInstant();
~~~

Đây là **mảnh code độc lập về ý tưởng** (không cần nằm cùng ví dụ đầu). Với UTC+07:00 ngày đã nêu, hai mốc tương ứng là `2026-11-07T02:00:00Z` và `2026-11-07T02:05:00Z`.

**Lỗi dễ gặp:** viết `Instant.parse("2026-11-07T09:00:00")` mà không có timezone/offset. `Instant.parse` cần định dạng mốc thời gian có offset/UTC thích hợp và không thể tự đoán `09:00` đó là múi giờ nào.

### Chọn cả ngày địa phương

Nếu muốn dữ liệu của **ngày 7/11/2026 theo một múi giờ cụ thể**, tạo hai mốc nửa mở từ **đầu ngày này** đến **đầu ngày sau**:

~~~java
import java.time.LocalDate;
import java.time.ZoneId;

LocalDate day = LocalDate.of(2026, 11, 7);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = day.atStartOfDay(zone).toInstant();
Instant to = day.plusDays(1).atStartOfDay(zone).toInstant();
~~~

Dùng `day.plusDays(1).atStartOfDay(zone)` thay vì mặc định cộng đúng 24 giờ cho mọi khu vực nếu ứng dụng có thể làm việc với vùng chuyển giờ mùa hè (DST). Một ngày lịch địa phương không luôn bằng 24 giờ tuyệt đối ở các time zones có DST.

### Kiểm tra thứ tự hai mốc

Trước khi gọi setter, nên tự kiểm tra hợp đồng:

~~~java
if (!from.isBefore(to)) {
    throw new IllegalArgumentException("from must be before to");
}
~~~

Đây là kiểm tra **do ứng dụng chủ động áp dụng**, không phải lời khẳng định rằng `EventStream` luôn tự phát sinh đúng exception này cho mọi trường hợp `from >= to`. Một cửa sổ rỗng hoặc đảo ngược thường là lỗi đầu vào nên được phát hiện sớm.

## 5. Chọn nguồn: tệp recording hay repository?

`EventStream` có các nhà máy tạo stream:

| Cách tạo | Dữ liệu đọc | Mặc định khi không đặt start time |
| --- | --- | --- |
| `EventStream.openFile(Path file)` | File recording `.jfr` đã có | Bắt đầu từ sự kiện đầu tiên trong file |
| `EventStream.openRepository()` | JFR repository của JVM hiện tại | Bắt đầu với sự kiện **tiếp theo được flush**, không tự đọc lại toàn bộ lịch sử |
| `EventStream.openRepository(Path directory)` | JFR disk repository do người gọi chỉ định | Mặc định cũng bắt đầu với sự kiện mới được flush |
| `RecordingStream` | Tự cấu hình và tạo recording của JVM hiện tại | Điều khiển recording và xử lý sự kiện trong cùng đối tượng |

**Khác biệt then chốt:** File `.jfr` là **nguồn hữu hạn** đã có dữ liệu; repository là **nguồn có thể được bổ sung theo thời gian**. Đặt `setStartTime` trong quá khứ **không thể tạo lại các sự kiện chưa từng được ghi hoặc đã bị loại khỏi repository**.

Với file, đặt một khoảng nằm ngoài toàn bộ thời gian file thường dẫn tới **không có sự kiện phù hợp** và stream kết thúc khi duyệt xong nguồn; đừng xem đó là lỗi bắt buộc. Với repository, nguồn có thể tiếp tục có sự kiện mới, nên `start()` có thể chờ thêm dữ liệu, và việc đặt end time hoặc đóng stream giúp giới hạn vòng đời.

Khi mục tiêu là “đọc từ 10:00 đến 10:05 **hôm qua**”, lựa chọn an toàn, tái lập được thường là **một file `.jfr` đã được lưu** đúng khoảng thời gian. Không nên mở repository hiện tại rồi mặc định dữ liệu hôm qua vẫn còn.

### Có thể kết hợp tên sự kiện và khoảng thời gian

~~~java
try (EventStream stream = EventStream.openFile(file)) {
    stream.setStartTime(from);
    stream.setEndTime(to);
    stream.onEvent("jdk.GarbageCollection", event -> {
        System.out.println(event.getDuration());
    });
    stream.start();
}
~~~

Đây là **mảnh mã tích hợp**. `onEvent("jdk.GarbageCollection", ...)` chỉ dispatch cho **event type đó**, giúp giảm công việc trong callback. Còn `setStartTime/setEndTime` quyết định khoảng thời gian của stream. Hai loại lọc phục vụ các chiều **khác nhau**, và không thay thế cho nhau.

## 6. Ví dụ Java 17+ chạy được: chọn đúng sự kiện trong một khoảng

Ví dụ sau minh họa trực tiếp cách dùng hai setter **mà không phụ thuộc thời gian đồng hồ thực tế**.

Thay vì gán `Instant.now().minusSeconds(5)` khi không biết chính xác event xảy ra lúc nào, chương trình:

1. Tạo một tệp JFR tạm chứa **ba custom instant events** có ID 1, 2, 3, cách nhau về thời gian.
2. Đọc các timestamp thật từ tệp vừa tạo.
3. Tính một `from` **ở giữa event 1 và event 2**, và một `to` **ở giữa event 2 và event 3**.
4. Mở `EventStream` trên chính file đó, đặt start/end trước `start()`, chỉ nhận event type custom.
5. Xác nhận chỉ nhận được **ID 2**, rồi xóa tệp tạm.

Tạo file **`EventStreamWindowDemo.java`**:

~~~java
import java.nio.file.*;
import java.time.*;
import java.util.*;
import jdk.jfr.*;
import jdk.jfr.consumer.*;

public class EventStreamWindowDemo {

    @Name("demo.WindowPoint")
    @StackTrace(false)
    static class Point extends Event {
        int id;
    }

    // Mốc nằm chính giữa hai event, tránh tranh luận
    // sự kiện đúng bằng biên có được tính hay không.
    static Instant middle(Instant first, Instant second) {
        if (!first.isBefore(second)) {
            throw new IllegalArgumentException("events too close");
        }
        return first.plusNanos(
            Duration.between(first, second).toNanos() / 2
        );
    }

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("event-window-", ".jfr");
        try {
            // 1. Tạo dữ liệu mẫu trong một recording thật.
            try (Recording rec = new Recording()) {
                rec.setToDisk(true);
                rec.enable(Point.class)
                   .withoutThreshold()
                   .withoutStackTrace();
                rec.start();

                for (int id = 1; id <= 3; id++) {
                    Thread.sleep(180);
                    Point e = new Point();
                    e.id = id;
                    e.commit();
                }
                rec.stop();
                rec.dump(path);
            }

            // 2. Xác định mốc thực tế từ file mẫu.
            List<RecordedEvent> events =
                RecordingFile.readAllEvents(path).stream()
                    .filter(e -> "demo.WindowPoint"
                        .equals(e.getEventType().getName()))
                    .sorted(Comparator.comparing(
                        RecordedEvent::getEndTime))
                    .toList();

            if (events.size() != 3) {
                throw new AssertionError(
                    "Events = " + events.size()
                );
            }

            Instant from = middle(
                events.get(0).getEndTime(),
                events.get(1).getEndTime()
            );
            Instant to = middle(
                events.get(1).getEndTime(),
                events.get(2).getEndTime()
            );

            // 3. Chọn một khoảng ở giữa 3 sự kiện.
            List<Integer> selected = new ArrayList<>();

            try (EventStream es = EventStream.openFile(path)) {
                es.setStartTime(from);
                es.setEndTime(to);
                es.onEvent("demo.WindowPoint",
                    e -> selected.add(e.getInt("id")));
                es.start();
            }

            System.out.println(
                "source-count=" + events.size()
            );
            System.out.println("window-ids=" + selected);
            System.out.println(
                "window-count=" + selected.size()
            );
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên (không cần thư viện ngoài):

~~~bash
javac -encoding UTF-8 EventStreamWindowDemo.java
java EventStreamWindowDemo
~~~

**Đầu ra đã kiểm chứng bằng cách chạy trên OpenJDK 24:**

~~~text
source-count=3
window-ids=[2]
window-count=1
~~~

### Giải thích kỹ cơ chế

- `@Name("demo.WindowPoint")` đặt tên event type, dùng khi gọi `onEvent("demo.WindowPoint", ...)`.
- `@StackTrace(false)` tránh ghi stack trace cho custom event không cần đường gọi; `withoutStackTrace()` bảo đảm cấu hình recording không ghi stack trace của loại event này.
- `rec.enable(Point.class).withoutThreshold()` bật recording cho event type và không áp ngưỡng duration, phù hợp với các instant events trong ví dụ.
- `Thread.sleep(180)` tạo khoảng cách đủ lớn cho ví dụ demo; **không** có nghĩa thời gian event được định nghĩa bằng đồng hồ sleep hoặc có độ chính xác 180 ms tuyệt đối.
- `RecordingFile.readAllEvents` đọc tất cả event của file, sau đó code chỉ lấy những sự kiện của ví dụ và sắp xếp theo `getEndTime()`.
- `middle(t1,t2)` tạo một mốc nằm giữa hai timestamp phân biệt, giúp tránh phụ thuộc quy tắc chính xác của sự kiện nằm **ngay trên ranh giới**. Nếu timestamp không tăng, chương trình báo lỗi rõ ràng thay vì cho kết quả mơ hồ.
- `setStartTime(from)` và `setEndTime(to)` được gọi **trước `es.start()`**. Callback chỉ được đăng ký cho event `demo.WindowPoint` và lấy trường `id`.
- Vì đây là các **instant events** với timestamp 1 < 2 < 3, cửa sổ từ midpoint(1,2) đến midpoint(2,3) chỉ bao gồm event 2. Do vậy output ID là `[2]`.
- `es.start()` xử lý đồng bộ toàn bộ phần phù hợp của tệp rồi kết thúc; không cần `awaitTermination()`.
- `Files.deleteIfExists(path)` trong `finally` giúp dọn dữ liệu demo. Với tệp sản xuất, **không tự xóa recording của người dùng**.

Đây là ví dụ tạo data thật rồi đọc thật, không chỉ in giá trị tính tay. Tuy nhiên, cách tạo khoảng bằng hai mốc giữa event chỉ phục vụ kiểm thử; trong ứng dụng thật, `from/to` thường đến từ thời điểm sự cố, timestamp trong log hoặc input của người dùng.

## 7. Kiểm soát chính xác chính sách ranh giới thời gian

Tên setter `setStartTime/setEndTime` nghe giống bộ lọc `WHERE eventTime BETWEEN ...`. Nhưng tài liệu mô tả chúng là **mốc của stream**, không tuyên bố mọi chính sách nghiệp vụ về sự kiện kéo dài qua nhiều giây.

Khi cần **cửa sổ nửa mở [from, to)** trên **thời điểm kết thúc event**, viết điều kiện rõ:

~~~java
static boolean endsWithin(
        RecordedEvent event, Instant from, Instant to) {
    Instant time = event.getEndTime();
    return !time.isBefore(from) && time.isBefore(to);
}
~~~

Đây là một **mảnh phương thức**; cần import `jdk.jfr.consumer.RecordedEvent` và `java.time.Instant`, có thể dùng bên trong callback nếu người viết cần chính sách [from, to) chính xác.

- `!time.isBefore(from)` tương đương `time >= from`.
- `time.isBefore(to)` tương đương `time < to`.
- Do đó sự kiện kết thúc **đúng `from` được nhận**, đúng `to` bị loại theo chính sách tự chọn này.

Với event có thời lượng, có thể chọn một trong ba câu hỏi:

| Chính sách | Ý nghĩa | Điều kiện minh họa |
| --- | --- | --- |
| End within | Event kết thúc trong [from, to) | `end >= from && end < to` |
| Fully contained | Toàn bộ event nằm trong [from, to) | `start >= from && end < to` |
| Overlaps | Event kéo dài có phần thời gian giao với [from, to) | `start < to && end > from` |

Điều kiện trong bảng là **biểu thức toán học**, cần chuyển thành các phép `Instant.isBefore/isAfter` trong Java.

Cẩn thận: quy tắc **overlaps** `start < to && end > from` phù hợp với **event có thời lượng dương**. Một **instant event** có `start == end == from` sẽ không thỏa điều kiện đó, dù chính sách point-in-window [from,to) có thể muốn lấy nó. Với instant events, dùng phép kiểm tra timestamp điểm như `endsWithin`.

**Không nên dùng setter làm thay thế tuyệt đối cho predicate của hệ thống kiểm tra ranh giới chính xác.** Tùy nguồn và cách JFR giao event theo flush/chunk, bộ lọc ở stream có thể mang ngữ nghĩa tiêu thụ/đóng stream chứ không phải chính sách dữ liệu nghiệp vụ.

## 8. EventStream theo thời gian không tạo hoặc khôi phục dữ liệu

`setStartTime(from)` **không**:

- Bật thu thập event mà recording/JVM chưa từng ghi.
- Khôi phục những chunk đã bị JVM repository loại bỏ do retention.
- Sửa timestamp của sự kiện.
- Làm `Recording` bắt đầu ghi vào quá khứ.
- Tự mở tệp `.jfr` khác hoặc hợp nhất nhiều file.
- Thay thế việc xác định timezone và diễn giải ngày tháng ở đầu vào.

`setEndTime(to)` **không**:

- Tự đặt `Recording.setMaxAge/setMaxSize` hoặc `Recording.setDuration`.
- Xóa file `.jfr` đã tạo.
- Bảo đảm toàn bộ dữ liệu có timestamp trước to đã được flush nếu nguồn live đóng quá sớm hoặc mất dữ liệu.
- Hủy mọi JFR recording khác đang chạy cùng JVM.

Điều đặc biệt quan trọng khi phân tích production: nếu một instance ngừng trước khi recording được lưu, việc yêu cầu EventStream đọc “30 phút trước” không thể tái tạo các sự kiện không tồn tại trong nguồn.

### File đã kết thúc khác với live repository

Khi xử lý file JFR, `EventStream.openFile(file)` sẽ dừng sau khi xử lý dữ liệu có sẵn; nếu cửa sổ kết thúc sau thời gian cuối file, không có dữ liệu bổ sung. Với repository đang được JVM cập nhật, stream có thể chờ events mới; `setEndTime` có thể dùng làm mốc tự đóng.

Do các events được flush theo batch/chunk, **thời điểm callback nhận được event không nhất thiết trùng thời điểm sự kiện xảy ra**. Không dùng `Instant.now()` bên trong callback làm thay thế cho `event.getStartTime()/getEndTime()` nếu cần phân tích lịch sử.

## 9. Sắp xếp và giao sự kiện: đừng suy ra thứ tự toàn cục

Tài liệu `EventStream` cho biết:

- Events được giao **theo batch**.
- Trong một batch, events được sắp theo **thời điểm kết thúc**.
- Sự kiện ở batch sau có thể mang timestamp nhỏ hơn sự kiện ở batch trước, vì chỉ những event có sẵn tại thời điểm flush mới được sắp tương đối trong batch đó.
- Có thể gọi `setOrdered(false)` khi không cần sắp để giảm công việc sắp xếp.

Vì vậy, với nguồn **live repository**, **không** khẳng định toàn bộ callback nhận event theo một thứ tự tăng tuyệt đối trên timeline. Nếu cần báo cáo thứ tự toàn cục sau thu thập, hãy lưu các trường cần thiết rồi sort lại theo timestamp trong phạm vi hữu hạn; đồng thời lưu ý đến độ trễ flush, dữ liệu đến muộn và chi phí bộ nhớ.

### Tránh giữ `RecordedEvent` dài hơn callback nếu bật reuse

`EventStream.setReuse(boolean)` cho phép reuse cùng object `RecordedEvent` cho các lần dispatch. Nếu reuse là true, đừng giữ tham chiếu event sau khi callback kết thúc. Hãy **trích dữ liệu cần thiết ngay trong callback**, hoặc đặt `setReuse(false)` trước khi bắt đầu stream nếu muốn giữ objects riêng (đổi lại có thể tăng cấp phát bộ nhớ).

Trong ví dụ mục 6, callback chỉ lấy `int id` và thêm vào `List<Integer>`, không giữ `RecordedEvent`. Vì vậy không cần thay đổi reuse.

## 10. Sử dụng với nguồn repository đang chạy

Một dạng minh họa cho JVM hiện tại:

~~~java
import java.time.Duration;
import java.time.Instant;
import jdk.jfr.consumer.EventStream;

try (EventStream stream = EventStream.openRepository()) {
    Instant from = Instant.now().minus(Duration.ofSeconds(30));
    Instant to = Instant.now().plus(Duration.ofSeconds(10));

    stream.setStartTime(from);
    stream.setEndTime(to);

    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(
            "CPU event end time: " + event.getEndTime()
        );
    });

    stream.startAsync();
    stream.awaitTermination(Duration.ofSeconds(15));
}
~~~

Đây là **mảnh mã đặt trong phương thức có xử lý `IOException/InterruptedException`**; không phải class chạy độc lập.

Điều cần hiểu:

1. `openRepository()` dùng repository của chính JVM; **không tự tạo recording mới** chỉ vì stream được mở. Phải có sự kiện thực sự được thu thập/flush vào nguồn.
2. `from` cách `Instant.now()` 30 giây chỉ yêu cầu bắt đầu tìm từ mốc đó **nếu dữ liệu còn hiện diện** trong repository.
3. `to` là mốc 10 giây trong tương lai. Khi đến mốc kết thúc, stream được đóng; callback có thể nhận ít, nhiều hoặc **0** sự kiện `jdk.CPULoad` tùy recording, event settings và flush.
4. `startAsync()` cho phép thread gọi tiếp tục. `awaitTermination(Duration.ofSeconds(15))` chỉ chờ **tối đa** khoảng đó; nó không tự chứng minh mọi event mong muốn đã được thu thập.
5. Try-with-resources đóng stream kể cả khi bị lỗi; không nên để stream chạy vô hạn sau khi chức năng giám sát đã kết thúc.

### Khi cần tạo recording cùng lúc

`jdk.jfr.consumer.RecordingStream` triển khai `EventStream` và có thể bật các event cụ thể rồi bắt đầu recording của JVM hiện tại. Ví dụ:

~~~java
import java.time.Duration;
import java.time.Instant;
import jdk.jfr.consumer.RecordingStream;

try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad")
          .withPeriod(Duration.ofSeconds(1));
    stream.setEndTime(Instant.now().plusSeconds(5));
    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(event.getEndTime());
    });
    stream.start();
}
~~~

Đây là **mảnh mã tích hợp**. Nó không cam kết số lượng event cố định vì periodic event phụ thuộc thời gian chạy và flush. `RecordingStream` phù hợp khi ứng dụng muốn **tạo và tiêu thụ** recording từ hiện tại. `EventStream.openFile` phù hợp khi cần **đọc lại lịch sử trong một tệp**.

Đặt `setStartTime` về thời gian quá khứ trên RecordingStream **không thể làm nó tạo sự kiện trước khi recording bắt đầu**.

## 11. Những lỗi thường gặp và cách sửa

| Lỗi hoặc hiểu nhầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Đặt `setStartTime` sau `startAsync()` | Stream đã bắt đầu; API ném `IllegalStateException` | Cấu hình từ trước khi start |
| Truyền `LocalDateTime` trực tiếp | Setter yêu cầu `Instant` | Quy đổi qua `ZoneId` rồi `toInstant()` |
| Dùng ngày/giờ địa phương nhưng giả định là UTC | Lệch nhiều giờ, chọn sai khoảng | Xác định zone/offset ở đầu vào |
| Gọi `Instant.parse("2026-11-07T09:00")` | Thiếu offset/UTC phù hợp | Dùng `LocalDateTime + ZoneId` hoặc ISO-8601 có `Z` |
| Để `from >= to` | Khoảng không hợp lý với nghiệp vụ | Tự kiểm tra `from.isBefore(to)` trước khi cấu hình |
| Nghĩ setter lọc mọi event theo chính xác [from,to) nghiệp vụ | Setter đặt thời gian **của stream**, không mô tả đầy đủ mọi quy tắc cho duration event | Dùng predicate tường minh theo `getStartTime/getEndTime` |
| Coi event kết thúc lúc nào là lúc callback chạy | Sự kiện có thể được giao khi batch/chunk flush | Đọc timestamp từ `RecordedEvent` |
| Cho rằng setStartTime lấy lại lịch sử đã bị xóa | Dữ liệu không còn trong repository/tệp | Bảo đảm retention và recording từ trước |
| Mở `openRepository()` rồi đợi có toàn bộ sự kiện | Mặc định là sự kiện flush tiếp theo; nguồn có thể không đang ghi | Kiểm tra recording/event settings |
| Dùng `onEvent(event -> ...)` rồi xử lý mọi loại | Nhiều callback ngoài nhu cầu và chi phí phân loại | Dùng `onEvent("event.name", ...)` khi biết loại |
| Giữ `RecordedEvent` khi reuse bật | Object có thể được dùng lại cho event khác | Trích dữ liệu trong callback hoặc `setReuse(false)` |
| Mong `startAsync()` là đã xử lý hết | Callback chạy trong thread khác | Dùng `awaitTermination`/signal và lifecycle đúng |
| Nghĩ `setEndTime` dừng mọi JFR trong JVM | Nó là mốc kết thúc của **stream**, không phải nút xóa các recording khác | Điều khiển recording qua API quản lý riêng |
| Test số event trong nguồn live bằng một con số cố định | Phụ thuộc flush, event settings, tần suất | Tạo file fixture hữu hạn như mục 6 để kiểm tra |
| Phân tích JFR file từ nơi không tin cậy | Tệp có thể chứa dữ liệu nhạy cảm hoặc không hợp lệ | Chỉ mở recording từ nguồn đáng tin và giới hạn quyền |

## 12. Checklist triển khai cho ứng dụng

1. **Nguồn dữ liệu:** đọc file `.jfr`, repository JVM đang chạy hay tạo recording mới?
2. **Mốc thời gian:** `from/to` là `Instant` UTC đúng chưa? Nếu đến từ ngày/giờ địa phương, zone đã đúng chưa?
3. **Hợp lệ:** `from.isBefore(to)` có đúng không? Nếu cửa sổ rỗng là có chủ đích, ứng dụng sẽ báo gì?
4. **Lifecycle:** đã gọi setters và đăng ký callback **trước** `start/startAsync` chưa?
5. **Event types:** nên chọn rõ `onEvent("jdk.EventName", ...)` thay vì xử lý tất cả?
6. **Điều kiện của event:** với duration event, ứng dụng muốn lấy event kết thúc, nằm trọn hay chồng lấn khoảng?
7. **Ranh giới:** cần [from,to) hay [from,to]? Predicate bên trong callback có thể hiện chính xác không?
8. **Availability:** nguồn có chứa dữ liệu trong khoảng đó không, hay repository đã hết retention?
9. **Delivery:** xử lý sync hay async? Có thể trễ flush? Callback có thread safety và xử lý exception chưa?
10. **Ordering:** có giả định sai về thứ tự toàn cục giữa các batch không?
11. **Performance:** có giữ quá nhiều event trong RAM hoặc lọc quá rộng không?
12. **Bảo mật:** `.jfr` có thể chứa class/thread/file/network metadata hoặc custom payload; đã quản lý quyền đọc/retention chưa?

## 13. Bài tập và đáp án gợi ý

### Bài 1 — Đặt khoảng 5 phút

Có file recording và muốn đọc CPU load từ `09:00` đến `09:05` ngày 7/11/2026 tại Việt Nam. Hãy tạo hai `Instant` và đặt setter trước khi start.

**Đáp án:**

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant from = LocalDateTime.of(2026, 11, 7, 9, 0)
        .atZone(zone).toInstant();
Instant to = LocalDateTime.of(2026, 11, 7, 9, 5)
        .atZone(zone).toInstant();

try (EventStream stream = EventStream.openFile(file)) {
    stream.setStartTime(from);
    stream.setEndTime(to);
    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(event.getEndTime());
    });
    stream.start();
}
~~~

Đây là **mảnh mã tích hợp** (cần import các type, `file` trỏ tới file có thật). Hai mốc UTC là `02:00:00Z` và `02:05:00Z`.

### Bài 2 — Dùng startAsync rồi đổi khoảng

~~~java
stream.startAsync();
stream.setEndTime(Instant.now().plusSeconds(30));
~~~

**Đáp án:** sai. `setEndTime` phải gọi **trước** khi stream bắt đầu; API có thể ném `IllegalStateException`. Sửa thứ tự: đặt end time, đăng ký callback, rồi gọi `startAsync()`.

### Bài 3 — Duration event chồng lấn cửa sổ

Một event bắt đầu lúc 10:00:00 và kết thúc 10:00:05. Khoảng phân tích [10:00:02, 10:00:04) có chứa event đó không?

**Đáp án:** theo chính sách **fully contained**, không; theo **overlaps**, có; theo chính sách **end within**, không. Vì vậy ứng dụng cần xác định rõ ngữ nghĩa trước khi lọc. Hai setter không thay thế quyết định này.

### Bài 4 — Không có sự kiện dù khoảng hợp lệ

`from` là 30 phút trước nhưng bạn mở `EventStream.openRepository()` và không nhận event nào của loại `jdk.CPULoad`. Hãy nêu ít nhất ba nguyên nhân có thể.

**Đáp án gợi ý:** repository không còn dữ liệu cũ; không có recording/event type đang enabled; event chưa được flush; khoảng đã kết thúc; sự kiện trong khoảng không tồn tại. Đừng vội cho rằng setter bị lỗi.

### Bài 5 — Chứng minh lọc khoảng từ fixture

Chạy `EventStreamWindowDemo.java`, quan sát `window-ids=[2]`. Sau đó chỉnh `from` nằm giữa event 2 và event 3; `to` là mốc sau event 3 một khoảng. Dự đoán event được chọn theo timestamp, rồi chạy và so sánh. Chú ý tránh đặt ranh giới đúng timestamp của event để không phụ thuộc chính sách ở biên.

### Bài 6 — Chọn đúng timestamp

Trong một event duration, `getStartTime()` nằm trước `from` và `getEndTime()` nằm trong [from,to). Hãy cho biết event được nhận theo ba chính sách ở mục 7.

**Đáp án:** `end within`: có; `fully contained`: không; `overlaps`: có (khi event duration dương và thời gian thực sự chồng lấn).

## 14. Tài liệu chính thức còn áp dụng

- [Oracle JDK 25 — EventStream API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): `setStartTime`, `setEndTime`, `openFile`, `openRepository`, `start/startAsync`, flush, ordering, reuse và callback lifecycle.
- [Oracle JDK 17 — EventStream API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): xác nhận các phương thức đã ổn định và có từ Java 14.
- [Oracle JDK 17 — RecordedEvent API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): timestamp bắt đầu/kết thúc của event và `getDuration()`.
- [Oracle JDK 17 — RecordingFile API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc recording đã lưu, `readAllEvents`.
- [Oracle JDK 17 — Recording API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html): cách tạo và dump recording dùng trong ví dụ.
- [Oracle JDK 17 — Event API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Event.html): custom events và `commit()`.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): cơ sở thiết kế cơ chế event streaming được đưa vào Java 14.
