# Khác biệt điểm bắt đầu mặc định của tệp và repository trong `EventStream` (Java 14+)

> **Mục tiêu:** hiểu vì sao cùng giao diện `jdk.jfr.consumer.EventStream` nhưng `openFile(Path)` mặc định đọc từ **event đầu tiên có trong tệp**, còn `openRepository()` và `openRepository(Path)` mặc định bắt đầu từ **event tiếp theo được Flight Recorder flush**. Bài học giải thích tác động khi phân tích file JFR so với giám sát stream đang hoạt động, cách chủ động đặt `setStartTime(Instant)`, giới hạn của lịch sử repository, ví dụ Java chạy được và các lỗi thường gặp. `EventStream` có từ Java 14, là API JFR vẫn còn được hỗ trợ trong JDK hiện đại; ví dụ biên dịch bằng JDK 17+.

## 1. Một giao diện `EventStream`, hai loại nguồn dữ liệu

Java Flight Recorder (JFR) ghi các sự kiện hoạt động của JVM như CPU load, garbage collection, hoạt động thread hoặc sự kiện tùy chỉnh. Giao diện `EventStream` trong module `jdk.jfr` cung cấp cơ chế đọc các sự kiện ấy và chuyển chúng đến callback đã đăng ký qua `onEvent(...)`.

Hai nguồn thường dùng:

- **Tệp recording `.jfr` đã có trên đĩa:** `EventStream.openFile(Path file)`. Thích hợp cho phân tích hậu kiểm, báo cáo hoặc điều tra sự cố từ tệp đã thu thập.
- **Repository JFR:** `EventStream.openRepository()` (repository của JVM hiện tại) hoặc `EventStream.openRepository(Path directory)` (một thư mục repository cụ thể). Thích hợp cho việc theo dõi các chunk/sự kiện mà JFR đang ghi và flush.

Dù cùng trả về `EventStream`, **điểm bắt đầu mặc định không giống nhau**. Đây là hợp đồng API, không phải lỗi Java hay do hai nguồn có những event type khác nhau.

```java
import jdk.jfr.consumer.EventStream;

EventStream fromFile = EventStream.openFile(file);
EventStream fromRepository = EventStream.openRepository();
```

Hai câu trên là **snippet minh họa**, giả định `file` là `java.nio.file.Path` trỏ tới một recording JFR hợp lệ; trong mã thực tế phải đóng các stream bằng `try-with-resources`, đăng ký callback trước khi bắt đầu và xử lý `IOException`.

## 2. Bảng so sánh điểm bắt đầu mặc định chính xác

| API tạo stream | Nguồn | Điểm bắt đầu mặc định theo JavaDoc | Ý nghĩa thực tế |
|---|---|---|---|
| `EventStream.openFile(Path file)` | Một tệp `.jfr` | **Sự kiện đầu tiên trong tệp** | Đọc lịch sử đã được lưu trong tệp, từ đầu phạm vi dữ liệu của tệp |
| `EventStream.openRepository()` | Repository của **JVM đang chạy** | **Sự kiện tiếp theo được JFR flush** | Mặc định theo dõi từ phần dữ liệu được flush tiếp theo, không tự replay toàn bộ lịch sử repository |
| `EventStream.openRepository(Path directory)` | Thư mục repository trên đĩa | **Sự kiện tiếp theo được JFR flush** | Cùng cơ chế mặc định như repository của JVM hiện tại; nguồn do đường dẫn quyết định |

JavaDoc `EventStream` của Oracle mô tả rõ hai câu tiếng Anh:

- Với tệp: “By default, the stream starts with the first event in the file.”
- Với repository: “By default, the stream starts with the next event flushed by Flight Recorder.”

**Không đánh đồng “event đầu tiên trong tệp” với “event đầu tiên JVM từng ghi”.** Một file `.jfr` chỉ chứa dữ liệu có trong phạm vi recording/dump đó, có thể là một khoảng thời gian ngắn, bị giới hạn dung lượng hoặc thiếu các event type không được bật.

**Cũng không dịch “next event flushed” thành “mọi event có timestamp từ `Instant.now()` trở đi”.** Một sự kiện có thể đã được ghi/commit trước khi mở stream nhưng chỉ được flush vào một chunk ở lần flush tiếp theo. Điểm phân biệt của mặc định repository là **biên nhận dữ liệu JFR tiếp theo**, không phải phép lọc timestamp được hứa chính xác bằng đồng hồ lúc gọi `openRepository()`.

## 3. Tình huống trực quan: tệp replay, repository theo dõi

Giả sử một recording chứa ba event thời gian:

```text
Thời gian:    t1            t2            t3            t4
               |             |             |             |
Đã commit:    A             B             C
Tệp .jfr:     [ A --------- B ----------- C ]
Mở file:                                          ^ openFile(file) rồi start()
Kết quả mặc định: xử lý từ A nếu A là event đầu tiên trong file.
```

`openFile` đọc từ đầu tệp đã tồn tại **cho dù lời gọi mở file diễn ra sau t3**. Đây là cách thích hợp để điều tra điều gì đã xảy ra trước khi công cụ phân tích chạy.

Với repository, diễn tiến có thể khác:

```text
Repository:    [chunk cũ ...]   [chunk kế tiếp flush]   [chunk sau nữa ...]
Mở stream:                        ^ khởi tạo và start
Mặc định:                          theo dõi từ sự kiện flush tiếp theo
```

`openRepository()` **không có nghĩa** tự tìm về chunk cũ nhất để replay toàn bộ lịch sử. Nếu muốn đọc các event quá khứ còn **được lưu giữ** trong repository, cần đặt mốc bắt đầu riêng bằng `setStartTime(...)` **trước `start()` hoặc `startAsync()`**.

Hai hành vi phù hợp với mục đích:

- **Phân tích từ đầu recording đã đóng:** mở file và đọc từ đầu.
- **Giám sát JVM còn chạy:** mở repository và nhận phần dữ liệu JFR sắp được flush; nếu cần quan sát cả khoảng trước khi đăng ký, hãy cân nhắc đặt thời gian bắt đầu có chủ đích.

## 4. Vì sao “flush tiếp theo” không nhất thiết là “event vừa được tạo”?

JFR ghi dữ liệu vào bộ đệm và các chunk, sau đó flush/chuyển dữ liệu cho consumer. Vì thế có ba thời điểm cần phân biệt:

1. **Event được phát sinh/commit** bởi JVM hoặc ứng dụng.
2. **Dữ liệu event được flush** vào nguồn mà `EventStream` có thể đọc.
3. **Callback `onEvent` nhận** `RecordedEvent` sau khi stream xử lý dữ liệu đã được flush.

Chúng không nhất thiết trùng nhau. Một callback có thể nhận sự kiện **đã commit trước đó** nhưng nằm trong phần dữ liệu mới được flush. Vì vậy khi kiểm thử repository stream:

- Không kỳ vọng mọi event có `getStartTime()` lớn hơn thời điểm gọi `openRepository()`.
- Không coi việc một callback đến muộn là bằng chứng `setStartTime` hoặc repository default bị sai.
- Không dùng `Thread.sleep(100)` như một barrier khẳng định mọi event cũ đã hoàn tất.
- Khi cần phân tích thời gian, đọc `RecordedEvent.getStartTime()` hoặc `getEndTime()` theo ngữ nghĩa event và làm rõ cửa sổ thời gian của hệ thống giám sát.

**Phạm vi bảo đảm ở đây là hợp đồng API** về nơi bắt đầu, không phải cam kết callback đến ngay tại thời điểm commit hay có đúng một số event cố định.

## 5. Đọc tệp JFR từ đầu bằng `openFile`

Khi đã có `Path file` tới recording:

```java
try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("jdk.GarbageCollection", event -> {
        System.out.println(event.getStartTime());
    });
    stream.start();
}
```

Đây là **snippet** trong phương thức có `throws IOException` hoặc xử lý `IOException`, đã import `EventStream` và `Path`. Các đặc điểm:

- `openFile(file)` là factory trả về stream từ **một tệp JFR**, không phải đường dẫn folder repository.
- Không gọi `setStartTime(...)` thì JavaDoc quy định bắt đầu từ **event đầu tiên trong file**.
- `onEvent("jdk.GarbageCollection", ...)` là bộ lọc **loại event được callback nhận**, không thay đổi nơi bắt đầu của file.
- `start()` xử lý đồng bộ trong thread gọi. Với file hữu hạn, việc xử lý hoàn tất khi hết dữ liệu của file hoặc khi đóng stream.
- Nếu không có `jdk.GarbageCollection` trong file, callback không chạy; điều đó **không chứng minh** stream bắt đầu sai.

**Quan trọng:** chỉ có thể đọc những event thực sự có trong file. Nếu một event không được ghi khi recording diễn ra, `openFile` không thể phục hồi nó bằng cách sửa mốc thời gian hoặc đăng ký thêm callback.

### Cần bỏ qua phần đầu của file?

Có thể chủ động đặt mốc sau này bằng `setStartTime`:

```java
import java.time.Instant;
import jdk.jfr.consumer.EventStream;

Instant cutoff = Instant.parse("2026-01-01T00:00:00Z");
try (EventStream stream = EventStream.openFile(file)) {
    stream.setStartTime(cutoff); // PHẢI trước start().
    stream.onEvent(event -> {
        System.out.println(event.getEventType().getName());
    });
    stream.start();
}
```

Đây là **snippet** giả định `file` đã khai báo và phương thức xử lý ngoại lệ I/O. Mốc `cutoff` chỉ có tác dụng nếu dữ liệu trong file nằm trong phạm vi liên quan; không có event ở hoặc sau mốc thì không có callback. Ngày ISO-8601 là ví dụ minh họa, không phải “mốc mặc định của EventStream”.

## 6. Theo dõi repository với mặc định “next flushed event”

Repository stream đọc các chunk JFR được quản lý bởi JVM hoặc tại một đường dẫn repository cụ thể. Một mẫu theo dõi JVM hiện tại:

```java
import jdk.jfr.consumer.EventStream;

try (EventStream stream = EventStream.openRepository()) {
    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println("CPU event at " + event.getEndTime());
    });
    stream.start(); // Theo dõi đồng bộ cho tới khi đóng/dừng.
}
```

Đây là **snippet**: trong ứng dụng giám sát thực tế cần cơ chế dừng hợp lệ (`close()`) hoặc chạy `startAsync()`. Không dùng `start()` ngay trên thread giao diện/HTTP request nếu không muốn nó chặn luồng xử lý.

Mặc định repository stream nhận dữ liệu bắt đầu từ **event tiếp theo được JFR flush** sau khi stream hoạt động, không tự đọc lại tất cả event đã tồn tại trong repository trước đó. Đó là điểm khác với file.

Một `EventStream` dùng `openRepository(Path directory)` có cùng mặc định nhưng đọc từ **thư mục repository** cụ thể:

```java
try (EventStream stream = EventStream.openRepository(repositoryDirectory)) {
    stream.onEvent(event -> {
        System.out.println(event.getEventType().getName());
    });
    stream.start();
}
```

`repositoryDirectory` là `Path` tới **repository JFR**, không phải tệp `.jfr`. Chỉ mở repository đáng tin cậy theo cảnh báo bảo mật JavaDoc. Nếu muốn đọc một tệp `.jfr` thì dùng `openFile` chứ không truyền tệp cho `openRepository(Path)`.

### Repository không tự tạo recording cho ứng dụng

`EventStream.openRepository()` là API **đọc**, không phải API tạo/tự enable mọi event type. Nếu không có event phát sinh hoặc loại event chưa được JFR bật trong recording phù hợp, việc đăng ký callback không làm chúng xuất hiện.

Khi muốn khởi tạo recording và streaming trong cùng mã ứng dụng, `jdk.jfr.consumer.RecordingStream` có thể thuận tiện hơn vì nó quản lý recording riêng cùng luồng sự kiện. Tuy nhiên đây là **API khác**, không làm thay đổi các mặc định riêng của `EventStream.openFile` và `EventStream.openRepository`.

## 7. Chủ động thay mốc bằng `setStartTime(Instant)`

Hợp đồng `EventStream` cung cấp:

```java
void setStartTime(java.time.Instant startTime)
```

Cách sử dụng chuẩn:

1. Mở đúng loại stream: file hay repository.
2. **Trước khi gọi `start()`/`startAsync()`**, gọi `setStartTime(instant)`.
3. Đăng ký `onEvent`/`onError`/`onClose` phù hợp.
4. Khởi chạy stream, nhận event và đóng/đợi kết thúc đúng vòng đời.

`setStartTime` **phải gọi trước khi stream được start**; gọi sau khi `start()` hoặc `startAsync()` đã bắt đầu sẽ gây `IllegalStateException` theo JavaDoc. Argument không được `null`.

### Muốn đọc cả dữ liệu còn giữ trong repository từ quá khứ

Ví dụ chủ động lấy cửa sổ 5 phút gần nhất:

```java
import java.time.Duration;
import java.time.Instant;
import jdk.jfr.consumer.EventStream;

Instant since = Instant.now().minus(Duration.ofMinutes(5));
try (EventStream stream = EventStream.openRepository()) {
    stream.setStartTime(since);
    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(event.getEndTime());
    });
    stream.startAsync();
    // Duy trì stream và đóng nó khi ứng dụng không cần theo dõi nữa.
}
```

Đoạn trên là **snippet**, không phải ví dụ có bảo đảm callback ngay lập tức. `try-with-resources` đóng stream khi rời block; trong ứng dụng muốn theo dõi dài hơn cần quản lý lifecycle thay vì rời block ngay.

**Giới hạn rất quan trọng:** chọn `since` trong quá khứ **không đảm bảo** repository vẫn giữ toàn bộ lịch sử. Chunk cũ có thể đã bị xóa do chính sách lưu trữ, dung lượng, vòng đời recording và hoạt động JVM. `setStartTime(Instant.EPOCH)` cũng **không phải** câu lệnh “tải lại mọi event từ đầu đời JVM”; nó chỉ yêu cầu phạm vi thời gian, còn dữ liệu thực tế phải **còn tồn tại và truy cập được**.

### Kết hợp điểm kết thúc

`EventStream.setEndTime(Instant endTime)` cho phép chỉ định mốc kết thúc **trước khi bắt đầu stream**. Phương thức này hữu ích khi đọc cửa sổ thời gian của file hoặc định giới hạn streaming theo thời gian. JavaDoc cho biết stream được đóng ở mốc end time. Không nhầm thời điểm lập lịch đóng stream với “số event chắc chắn đã được giao trong khoảng thời gian ấy”, vì JFR có cơ chế flush/buffer.

## 8. Chương trình Java 17+ hoàn chỉnh: tạo file, đọc lại và mở repository

Tệp **`EventStreamStartDemo.java`** dưới đây tạo một recording thực với hai sự kiện tùy chỉnh, lưu thành file `.jfr`, đọc file bằng `openFile` *không setStartTime*, đồng thời mở repository stream để chứng minh đường khởi tạo hai nguồn API đều hợp lệ.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.EventStream;

public class EventStreamStartDemo {
    @Name("demo.Checkpoint")
    static class Checkpoint extends Event {
        String label;
        Checkpoint(String label) { this.label = label; }
    }

    static void emit(String label) {
        new Checkpoint(label).commit();
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("start-demo-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(Checkpoint.class).withoutThreshold();
                recording.start();
                emit("first");
                emit("second");
                recording.stop();
                recording.dump(file);
            }

            List<String> fileEvents = new ArrayList<>();
            try (EventStream fileStream = EventStream.openFile(file)) {
                fileStream.onEvent("demo.Checkpoint",
                    event -> fileEvents.add(event.getString("label")));
                fileStream.start();
            }
            System.out.println("fileEvents=" + fileEvents);
            System.out.println("fileCount=" + fileEvents.size());

            try (EventStream repositoryStream = EventStream.openRepository()) {
                repositoryStream.onEvent("demo.Checkpoint", event -> {});
                repositoryStream.startAsync();
                System.out.println("repositoryStarted=true");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy với **JDK 17+ có module `jdk.jfr` và hỗ trợ Flight Recorder**:

```bash
javac -encoding UTF-8 EventStreamStartDemo.java
java EventStreamStartDemo
```

**Stdout đã được kiểm tra trên OpenJDK 24:**

```text
fileEvents=[first, second]
fileCount=2
repositoryStarted=true
```

**Diễn giải đúng phạm vi những gì chương trình chứng minh:**

- `recording.enable(Checkpoint.class)` bật sự kiện `demo.Checkpoint` do class mẫu định nghĩa; sau đó `emit("first")` và `emit("second")` commit hai sự kiện vào recording.
- `recording.stop()` và `recording.dump(file)` tạo file `.jfr` với dữ liệu. Sau đó `openFile(file)` và `start()` đọc các sự kiện đã tồn tại và callback thêm nhãn vào `fileEvents`.
- `fileEvents=[first, second]` chứng minh đường đọc file từ đầu trên JVM đã thử; `fileCount=2` là số event tùy chỉnh của demo, không phải tổng số event JFR khác trong recording.
- `repositoryStarted=true` chỉ được in sau `openRepository()` và `startAsync()` thành công. Nó **không** tuyên bố rằng repository đã trả về một số event cụ thể. Callback repository được để rỗng có chủ đích vì event live và thời điểm flush **không bảo đảm số lượng cố định** trong thời gian rất ngắn.
- Việc test không cố tình khẳng định repository “bỏ qua first/second” dựa trên số callback: quy tắc **next flushed event** đã được JavaDoc quy định; thu thập event live còn phụ thuộc flush, retention và recording hiện hoạt.
- `Files.deleteIfExists(file)` ở `finally` dọn tệp tạm, và `try-with-resources` đóng các đối tượng JFR.

**Giới hạn môi trường:** nơi chạy cần có `jdk.jfr` và JFR hoạt động. Một JVM đặc biệt bị vô hiệu hóa Flight Recorder hoặc môi trường thiếu quyền ghi tệp tạm có thể không chạy được ví dụ dù code đúng. Trong trường hợp đó, hãy kiểm tra JDK, cấu hình JFR và quyền tệp; đừng tự suy luận default của API đã thay đổi.

## 9. Các nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu và sửa |
|---|---|
| `openFile` bắt đầu từ lúc gọi API | Sai: mặc định nó bắt đầu từ **sự kiện đầu tiên trong file đã được lưu** |
| `openRepository` tự replay tất cả event cũ | Sai: mặc định bắt đầu từ **event tiếp theo được flush** |
| “Next flushed” nghĩa là timestamp event luôn lớn hơn `Instant.now()` | Không chính xác: event có thể được commit trước và flush sau |
| `setStartTime(Instant.EPOCH)` lấy lại toàn bộ lịch sử JVM | Sai: chỉ đọc được những event còn tồn tại trong phạm vi repository |
| `onEvent` làm JFR bật loại event đó | Sai: callback chỉ lắng nghe; event cần được recording bật và thực sự phát sinh |
| `openRepository(Path)` nhận file `.jfr` | Sai: phương thức này nhận **thư mục repository**; file dùng `openFile(Path)` |
| Có thể gọi `setStartTime` sau `startAsync` | Sai: `IllegalStateException`; hãy cấu hình trước khi start |
| Không thấy callback là stream hỏng | Có thể vì event chưa phát sinh, chưa flush, loại event không bật hoặc không có dữ liệu trong phạm vi lọc |
| `start()` và `startAsync()` giống nhau hoàn toàn | Không: `start()` xử lý trên thread hiện tại; `startAsync()` dùng thread riêng |
| Đóng stream là chắc chắn mọi handler đã chạy xong | `close()` không bảo đảm mọi registered action đã kết thúc trước khi trả về; khi cần, thiết kế đồng bộ phù hợp |
| Đọc file hay repository lạ không có rủi ro | JDK cảnh báo **chỉ mở file/repository tin cậy**; hạn chế đầu vào và quyền truy cập |

### Một tình huống chọn API sai

Bạn có tệp `incident.jfr` được dump trong khoảng thời gian 10:00–10:05 và muốn phân tích nguyên nhân lúc 10:02. Dùng `EventStream.openFile(Path.of("incident.jfr"))` để đọc dữ liệu hiện có; theo mặc định, luồng bắt đầu từ event đầu tiên trong file. Có thể gọi `setStartTime(Instant.parse("..."))` nếu muốn thu hẹp cửa sổ điều tra.

Nếu thay bằng `openRepository()` trên JVM đang chạy lúc 11:00, bạn đang đọc **repository của JVM đó**, mặc định theo dõi event tiếp theo được flush — không phải “mở lại `incident.jfr`”. Muốn truy lại file quá khứ thì phải chỉ đích danh file.

## 10. Checklist khi triển khai

1. **Xác định nguồn:** một file `.jfr` hay repository JVM đang ghi?
2. **Xác định nhu cầu:** replay lịch sử file từ đầu, nhận flush tương lai hay đọc một cửa sổ thời gian tùy chỉnh?
3. **Chọn đúng factory:** `openFile(Path)` cho file; `openRepository()`/`openRepository(Path)` cho repository.
4. **Ghi nhớ default:** file bắt đầu ở event đầu tiên trong file; repository bắt đầu ở event tiếp theo được flush.
5. **Cấu hình `setStartTime` trước `start/startAsync`** khi muốn khác default; kiểm tra mốc thời gian UTC bằng `Instant`.
6. **Kiểm tra dữ liệu tồn tại:** file có đúng event type? Repository còn giữ dữ liệu trong cửa sổ yêu cầu không?
7. **Đăng ký `onEvent` trước start**, xử lý đúng loại event và không giả định sự kiện phát sinh định kỳ theo bất kỳ thời gian thử nghiệm cố định nào.
8. **Tách thời điểm commit/flush/callback** khi debug độ trễ hoặc kiểm tra thứ tự.
9. **Quản lý vòng đời:** dùng `try-with-resources`, `close()`, `awaitTermination` khi cần, và dọn file tạm đúng cách.
10. **Bảo vệ nguồn dữ liệu:** chỉ mở JFR files/repositories tin cậy, không để lộ thông tin nhạy cảm trong recording.
11. **Giữ ví dụ cập nhật:** dùng API Java 14+ hiện hành và JDK 17+ để chạy thử; không dựa vào flag preview hay tài liệu kỹ thuật cũ.

## Tham khảo tài liệu chính thức

- Oracle Java SE 26 API, `EventStream` — ba factory và mô tả default cho file/repository: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html
- Oracle Java SE 17 API, `EventStream` — `setStartTime`, `start`, `startAsync`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html
- Oracle Java SE 25 API, `EventStream` — giao diện streaming và callback: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html
- Oracle Java SE 17 API, `Recording` — tạo và dump recording ra file: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html
- Oracle Java SE 17 API, `RecordedEvent` — thời gian và giá trị của event: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html
- Oracle Java SE 17 API, `RecordingStream` — API khác để tạo recording và đọc stream cùng lúc: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html
