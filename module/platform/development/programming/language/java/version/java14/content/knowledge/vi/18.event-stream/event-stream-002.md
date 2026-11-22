# Đọc repository JFR được chỉ định theo đường dẫn bằng EventStream

## 1. Giới thiệu và mục tiêu

`jdk.jfr.consumer.EventStream` cho phép Java đọc sự kiện được ghi bởi **JDK Flight Recorder (JFR)**. Khi đã biết một **disk repository** nằm ở đâu, ta sử dụng overload:

```java
EventStream.openRepository(Path directory)
```

Đây là lời gọi **mở luồng sự kiện từ một thư mục repository trên đĩa**, không phải lời gọi bật JFR trong JVM, tạo recording mới hay mở một file `.jfr` đã được xuất. Bài học nằm trong chủ đề **EventStream**, tập trung vào cách dùng đường dẫn chính xác và các vấn đề thực tế khi dữ liệu JFR được producer ghi bất đồng bộ.

Kết thúc bài, bạn sẽ:

- Phân biệt disk repository, chunk file và file recording `.jfr`.
- Biết khi nào chọn `EventStream.openRepository(Path)`, `openRepository()`, `openFile(Path)` hoặc `RecordingStream`.
- Dùng `java.nio.file.Path`, đăng ký `onEvent`, gọi `startAsync`, giới hạn thời gian đọc và tự động `close`.
- Hiểu tại sao một stream có thể không nhận event nào mà không hề gặp lỗi lập trình.
- Điều chỉnh thời điểm bắt đầu bằng `setStartTime` để đọc các sự kiện còn được lưu.
- Viết và kiểm tra một chương trình Java độc lập nhận repository path từ command line.
- Áp dụng các biện pháp an toàn về quyền đọc, tài nguyên, event payload và thread.

**Tính hiện hành:** JFR Event Streaming API được đưa vào Java 14 (JEP 349), đã là API chính thức và vẫn có trong Java hiện đại. Mọi chương trình thực hành trong bài sử dụng **JDK 17 trở lên**, không cần bật preview và không dùng phương thức legacy.

## 2. Disk repository không phải file .jfr

JFR có thể ghi sự kiện ra đĩa thành các **chunk**, được quản lý trong một **disk repository**. JVM nguồn ghi và flush những chunk đó; một chương trình khác hoặc một thành phần khác có quyền filesystem có thể đọc thông tin từ repository qua `EventStream`.

```text
JVM nguồn
  |
  | JFR recording: event được bật và phát sinh
  v
Disk repository (JFR chunks)
  |
  | EventStream.openRepository(Path)
  v
Luồng các RecordedEvent
  |
  | onEvent(...) / onFlush(...) / onError(...)
  v
Ứng dụng phân tích, thống kê hoặc chẩn đoán
```

Cần nhớ:

- **Repository** là một thư mục dữ liệu JFR được quản lý, có thể thay đổi trong khi JVM nguồn hoạt động.
- **Chunk** là phần dữ liệu của recording. Chunks có thể được hoàn tất, loại bỏ hoặc hết thời gian giữ tùy chính sách JFR.
- **Tệp `.jfr`** là recording được lưu/dump thành file. Đó là loại nguồn khác: không truyền một file `.jfr` vào API vốn nhận repository directory.
- **Thời điểm callback** không nhất thiết trùng với thời điểm event được ghi; JFR có buffering và flush.

Ví dụ `Path.of("/srv/jfr/recording.jfr")` mô tả một **file**; còn `Path.of("/srv/jfr/active-repository")` dự kiến là một **directory**. Tên đường dẫn không chứng minh loại nguồn thực tế: phải kiểm tra filesystem và cấu hình JFR.

## 3. So sánh các API đọc sự kiện JFR

| API | Nguồn dữ liệu | Cách sử dụng |
| --- | --- | --- |
| `EventStream.openRepository()` | Repository của **JVM hiện tại** | Không truyền Path |
| `EventStream.openRepository(Path)` | **Disk repository được chỉ định** | Truyền Path của thư mục repository |
| `EventStream.openFile(Path)` | **Một file recording `.jfr`** | Truyền Path của file |
| `RecordingFile` | Recording file `.jfr` | Phân tích offline theo file |
| `RecordingStream` | Recording/stream của **JVM hiện tại** | Có API `enable` để cấu hình event được ghi |
| `Recording` | Một phiên ghi JFR | Điều khiển việc ghi, dừng và dump |

**Khác biệt quan trọng:** `EventStream` là **interface nhận sự kiện**, **không có phương thức `enable(...)`**. Nếu nguồn JVM chưa bật `jdk.CPULoad` thì viết một callback đọc `jdk.CPULoad` không thể khiến event tự được tạo. Việc bật/sinh event là trách nhiệm **producer JVM** qua cấu hình recording hoặc các API phù hợp.

`EventStream.openRepository(Path)` cũng **không** kết nối tự động tới một JVM theo PID, không thiết lập JMX connection, không tải file từ máy khác. Nó đọc những chunk JFR thông qua đường dẫn mà **tiến trình consumer** có thể truy cập.

## 4. Khởi tạo EventStream theo đúng đường dẫn

Import:

```java
import java.io.IOException;
import java.nio.file.Path;
import jdk.jfr.consumer.EventStream;
```

Ví dụ trong một method (chưa phải chương trình độc lập):

```java
Path repository = Path.of("/absolute/path/to/jfr-repository");

try (EventStream stream =
        EventStream.openRepository(repository)) {

    stream.onEvent(event -> {
        System.out.println(event.getEventType().getName());
    });

    stream.start();
} catch (IOException error) {
    System.err.println("Cannot read JFR repository: "
            + error.getMessage());
}
```

`start()` dùng **thread đang gọi** để xử lý callback. Nếu repository còn đang được ghi, việc gọi này có thể chặn cho tới khi stream kết thúc hoặc được đóng. Để ứng dụng có thể tiếp tục xử lý công việc khác, thường dùng `startAsync()` và quản lý thời hạn quan sát.

Javadoc chính thức quy định `EventStream.openRepository(Path directory)`:

- Nhận một `Path` trỏ tới **disk repository**, không phải `null`.
- Tạo `EventStream` khác `null` khi thành công.
- Có thể ném `IOException` khi không thể mở stream hoặc không đọc được repository.
- **Chỉ nên mở repository đáng tin cậy**, vì dữ liệu JFR không phải nội dung vô hại được xác minh cho mọi nguồn.
- **Mặc định bắt đầu với sự kiện tiếp theo được JFR flush**, chứ không mặc định phát lại mọi event cũ.

`Path.of(...)` chỉ biểu diễn một đường dẫn; nó không tự tạo directory hay recording, không xác nhận quyền và không khẳng định dữ liệu chunk là hợp lệ.

## 5. Cách xác định thư mục repository thực

Trên JVM nguồn, JDK có lệnh chẩn đoán để cấu hình recording, ví dụ:

```bash
jcmd <PID> JFR.configure repositorypath=/srv/jfr/repository-base
jcmd <PID> JFR.start settings=default disk=true
```

Thay `<PID>` bằng PID thật và chọn đường dẫn có quyền ghi. Đây chỉ là **lệnh minh họa khi vận hành JVM nguồn**: việc thay đổi cài đặt có thể bị giới hạn nếu JFR đã được khởi tạo. Nếu triển khai hệ thống thật, nên chuẩn bị cấu hình sớm và kiểm tra trạng thái recording.

Có thể chọn cách khởi động JVM với JVM options:

```bash
java -XX:FlightRecorderOptions=repository=/srv/jfr/repository-base -XX:StartFlightRecording=settings=default,disk=true -cp app MyApplication
```

Hai cách này là phương án thay thế, không yêu cầu chạy đồng thời.

**Đặc biệt quan trọng:** Tham số cấu hình `repositorypath` có thể chỉ định **địa điểm gốc**, còn JFR có thể tạo **thư mục repository thực tế riêng cho tiến trình** bên trong. Đường dẫn đưa vào `EventStream.openRepository(Path)` phải là **directory chứa các JFR chunks thật sự cần đọc**, không phải bất kỳ thư mục cha có tên gợi nhớ đến JFR.

Nếu producer đang ở JVM khác hoặc máy khác, việc consumer nhìn thấy các chunk qua filesystem cần được cấu hình riêng và giới hạn quyền. `openRepository(Path)` không phải API truy cập JVM qua mạng.

## 6. Tại sao stream mặc định không đọc toàn bộ lịch sử?

Theo Javadoc của cả Java 17 lẫn Java hiện đại, repository stream **mặc định bắt đầu với event tiếp theo được Flight Recorder flush**. Vì vậy mở một directory đã chứa nhiều chunk không đồng nghĩa tự phát lại mọi event trong những chunk đó.

Khi muốn bắt đầu từ một mốc thời gian cũ hơn, hãy gọi **trước khi start**:

```java
stream.setStartTime(
        java.time.Instant.now().minusSeconds(60));

stream.onEvent(event -> {
    // Xử lý các event còn được lưu từ mốc đã chọn.
});

stream.startAsync();
```

Đoạn này giả định `stream` đã được khởi tạo ở scope xung quanh.

Cần hiểu giới hạn:

1. `setStartTime` chỉ thay đổi **mốc thời gian đọc**, không tạo thêm event mới.
2. Chunk đã bị producer/JFR xóa sẽ không thể khôi phục bằng cách đặt mốc `Instant.EPOCH`.
3. Nếu producer không bật loại event hoặc chưa flush dữ liệu, callback có thể không nhận gì.
4. Đặt mốc rất xa như `Instant.EPOCH` trên repository lớn có thể tạo nhiều I/O/CPU; nên giới hạn cửa sổ theo nhu cầu.
5. `setEndTime(Instant)` cũng phải được gọi trước `start`; nó giới hạn thời điểm kết thúc event stream, nhưng không thay thế mọi cơ chế timeout, cleanup hoặc xử lý lỗi I/O.

## 7. Các phương thức vận hành cần nhớ

| Phương thức | Hành vi | Ghi chú |
| --- | --- | --- |
| `onEvent(Consumer)` | Callback cho mọi event được giao | Có thể nhận rất nhiều event |
| `onEvent(String, Consumer)` | Callback theo đúng tên event | Cần biết JFR event name |
| `onFlush(Runnable)` | Callback khi batch hoàn thành | Phù hợp tổng hợp dữ liệu |
| `onError(Consumer<Throwable>)` | Nhận lỗi xử lý | Không mặc nhiên ném lên main thread |
| `onClose(Runnable)` | Thông báo stream đóng | Dùng cho cleanup/trạng thái |
| `start()` | Xử lý trên thread hiện tại | Có thể chặn |
| `startAsync()` | Xử lý trên thread riêng | Main thread đi tiếp |
| `awaitTermination(Duration)` | Chờ stream kết thúc/đóng hoặc timeout | Timeout không tự `close` |
| `setStartTime(Instant)` | Chọn mốc bắt đầu đọc | Trước `start` |
| `setEndTime(Instant)` | Chọn mốc kết thúc | Trước `start` |
| `setOrdered(boolean)` | Điều khiển sắp xếp event theo thời gian | Không tạo thứ tự toàn cục tuyệt đối |
| `setReuse(boolean)` | Điều khiển tái sử dụng `RecordedEvent` | Tránh lưu reference ngoài callback nếu reuse |
| `close()` | Đóng stream/giải phóng tài nguyên | Không bảo đảm mọi callback đã hoàn tất |

**Trình tự an toàn:** mở nguồn → chọn mốc thời gian → đăng ký callback và handler lỗi → start → quan sát/chờ → close. Với `startAsync`, không đóng ngay ở câu lệnh kế tiếp nếu mục tiêu là thu nhận event.

## 8. Chương trình Java 17+ chạy được: RepositoryEventStreamDemo.java

Ví dụ này yêu cầu **một đường dẫn** từ command line. Nó đọc mọi event được stream giao, đếm số lượng và ghi lại tên event đầu tiên, không phụ thuộc event type nào chắc chắn tồn tại trong repository.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import jdk.jfr.consumer.EventStream;

public final class RepositoryEventStreamDemo {
    private RepositoryEventStreamDemo() {
    }

    public static void main(String[] args)
            throws IOException, InterruptedException {

        if (args.length != 1) {
            System.err.println(
                    "Usage: java RepositoryEventStreamDemo "
                    + "<jfr-repository-directory>");
            return;
        }

        Path directory = Path.of(args[0])
                .toAbsolutePath().normalize();

        if (!Files.isDirectory(directory)) {
            throw new IllegalArgumentException(
                    "Not a repository directory: " + directory);
        }
        if (!Files.isReadable(directory)) {
            throw new IllegalArgumentException(
                    "Repository is not readable: " + directory);
        }

        AtomicLong count = new AtomicLong();
        AtomicReference<String> firstType =
                new AtomicReference<>();
        AtomicReference<Throwable> failure =
                new AtomicReference<>();

        try (EventStream stream =
                EventStream.openRepository(directory)) {

            stream.setStartTime(Instant.now().minusSeconds(60));

            stream.onEvent(event -> {
                count.incrementAndGet();
                firstType.compareAndSet(null,
                        event.getEventType().getName());
            });

            stream.onError(error -> {
                failure.compareAndSet(null, error);
            });

            stream.startAsync();

            // Observe for a bounded period, not a delivery guarantee.
            Thread.sleep(5_000);
        }

        Throwable error = failure.get();
        if (error != null) {
            throw new IllegalStateException(
                    "JFR streaming failed", error);
        }

        System.out.println("repositoryOpened=true");
        System.out.println("eventsObserved=" + count.get());
        System.out.println("firstEventType="
                + (firstType.get() == null
                        ? "none"
                        : firstType.get()));
    }
}
```

### Biên dịch và chạy

Dùng **JDK 17+**:

```bash
javac --release 17 RepositoryEventStreamDemo.java
java RepositoryEventStreamDemo "/absolute/path/to/jfr-repository"
```

Đường dẫn trong câu lệnh là **giá trị minh họa**, phải thay bằng repository thật và tin cậy trong hệ thống. Trên Windows, có thể dùng một đường dẫn thực như `"C:\jfr\active-repository"`. Không truyền một file `capture.jfr` vào tham số này.

### Stdout nào là đáng tin?

Khi directory mở được, không có exception được handler ghi nhận và **không có event được giao**, một output hợp lệ là:

```text
repositoryOpened=true
eventsObserved=0
firstEventType=none
```

Đây là **một trường hợp ví dụ, không phải stdout cố định của mọi lần chạy**. Khi có event, hai dòng cuối phụ thuộc repository. Ví dụ có thể nhận `eventsObserved=12` và `firstEventType=jdk.CPULoad`; cả số `12` lẫn tên event đều chỉ mang tính minh họa.

Nếu directory sai hoặc không đọc được, ví dụ ném exception tương ứng; không in một báo cáo thành công giả. Nếu hết năm giây mà chưa có event thì `eventsObserved=0` là kết quả quan sát trung thực, không đủ để kết luận bản thân API sai.

### Phân tích chương trình

1. `args.length` buộc caller truyền đúng **một Path**. Với dịch vụ thật, cần giới hạn nguồn được phép mở; không chấp nhận path người lạ tùy ý.
2. `toAbsolutePath().normalize()` chuẩn hóa biểu diễn path theo cú pháp. **Không** xem nó là biện pháp chống truy cập trái phép, kiểm tra symbolic link hay xác nhận repository đáng tin.
3. `Files.isDirectory` và `Files.isReadable` xác nhận điều kiện sơ bộ, **không** khẳng định thư mục có chunk hợp lệ và không loại trừ thay đổi quyền sau thời điểm kiểm tra.
4. `EventStream.openRepository(directory)` đọc disk repository được chỉ định. Nó không sử dụng repository của chính consumer trừ khi Path thật sự trỏ tới nơi đó.
5. `setStartTime(Instant.now().minusSeconds(60))` giúp tìm các event gần đây **còn lưu**; xóa dòng này thì trở về mốc mặc định từ next flushed event.
6. `onEvent` tăng `AtomicLong` và lưu tên event đầu tiên trong `AtomicReference`, vì callback chạy ở thread khác khi dùng `startAsync`.
7. `onError` lưu một lỗi xử lý được thông báo. Main thread kiểm tra giá trị ấy khi cửa sổ quan sát kết thúc.
8. `startAsync` không chặn; `Thread.sleep(5_000)` giữ stream sống năm giây. Đây là **giới hạn thời gian demo**, không bảo đảm JFR flush và phân phối mọi sự kiện trong khoảng đó.
9. `try-with-resources` gọi `close()` cả khi có exception. Javadoc nói rõ việc đóng không bảo đảm mọi callback đã chạy xong trước khi method đóng trả về, nên số đếm chỉ là **ảnh chụp giá trị đã nhận**, không phải tổng event từng tồn tại.
10. Vì event source, timing và retention thay đổi theo môi trường, chương trình không có stdout hoàn toàn cố định về số lượng. Điều được kiểm chứng là **đường dữ liệu và cách xử lý được triển khai đúng API**.

## 9. Lọc event theo tên

Khi chỉ muốn quan sát một loại như `jdk.CPULoad`, thay callback nhận mọi event bằng:

```java
stream.onEvent("jdk.CPULoad", event -> {
    if (event.hasField("machineTotal")) {
        System.out.println(event.getFloat("machineTotal"));
    }
});
```

Đây là **đoạn code minh họa trong scope có biến `stream`**, không phải chương trình độc lập. `jdk.CPULoad` phải được **producer JVM bật và ghi**; consumer không có `enable`. Nếu không có callback trong một cửa sổ ngắn, hãy kiểm tra loại event, cấu hình recording, mốc thời gian và trạng thái flush trước khi kết luận thư mục hỏng.

Với custom event, tên trong `onEvent("my.company.EventName", ...)` phải tương ứng `@Name(...)` hoặc metadata do producer phát ra. `event.getEventType().getName()` và `event.hasField(...)` giúp tìm hiểu field có thật trước khi gọi getter kiểu dữ liệu cụ thể.

## 10. Batch, thứ tự và chính sách reuse

Javadoc `EventStream` nêu rằng events được phân phối theo các **batch**. Các event trong cùng một batch được sắp xếp theo thời gian kết thúc khi ordering được bật; không được suy ra rằng **toàn bộ các batch liên tiếp** có thứ tự tuyệt đối như một file log tuyến tính.

Nếu thứ tự không quan trọng, `setOrdered(false)` có thể bỏ sắp xếp. `onFlush(Runnable)` giúp chốt thống kê khi một batch được xử lý xong, nhưng không làm thay đổi loại event producer ghi.

**RecordedEvent có thể được tái sử dụng.** Nếu callback cần lưu kết quả lâu dài, nên **sao chép các giá trị cần thiết** (tên loại, timestamp, dữ liệu đã kiểm tra) vào object của ứng dụng, thay vì giữ nguyên reference `RecordedEvent` sau khi callback kết thúc. Có thể dùng `setReuse(false)` khi thực sự cần các object riêng, nhưng điều đó phát sinh chi phí cấp phát.

Callback nhanh giúp stream xử lý tốt hơn. Không tải dữ liệu vô hạn vào RAM hoặc gọi dịch vụ mạng chậm trong từng callback nếu ứng dụng có lưu lượng event lớn.

## 11. Các vấn đề bảo mật và tài nguyên

- **Repository đáng tin:** chỉ mở từ nguồn đã xác minh; không nhận một đường dẫn từ người dùng bất kỳ rồi cho dịch vụ có quyền cao đọc nội dung.
- **Dữ liệu nhạy cảm:** JFR event có thể chứa đường dẫn, địa chỉ mạng, tên phương thức hoặc custom payload. Không log toàn bộ `RecordedEvent` nếu chưa có chính sách quyền riêng tư.
- **Quyền filesystem:** producer cần quyền ghi, consumer cần quyền đọc; quyền và vị trí chunks có thể thay đổi trong lúc stream chạy.
- **Giới hạn tài nguyên:** với stream lâu dài, tránh giữ mọi event trong list; chọn bộ đếm, thống kê theo loại hoặc bounded queue với chính sách bỏ/tạm dừng phù hợp.
- **Lifecycle:** `close()` phải được gọi khi dừng; với stream async, cần một điều kiện kết thúc, không phụ thuộc vào chương trình được phép chạy mãi.
- **Không dùng như event bus nghiệp vụ đảm bảo giao đủ:** JFR phục vụ quan sát/chẩn đoán và có các điều kiện về ghi/flush/retention; không mặc định nó thay thế một messaging system có contract giao hàng chính xác.

## 12. Những lỗi thường gặp

| Lỗi | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| Truyền `capture.jfr` vào `openRepository` | Path trỏ file, không phải repository directory | Dùng `openFile(Path)` |
| Truyền thư mục cha `repository-base` | JFR có thể tạo repository thực trong thư mục con | Xác minh đường dẫn chứa chunks |
| Quên start sau khi đăng ký onEvent | Callback chưa được xử lý | `start` hoặc `startAsync` |
| Dùng `stream.enable(...)` | `EventStream` không có API enable | Bật event ở JVM producer |
| Đóng ngay sau `startAsync` | Chưa đủ thời gian nhận event | Chờ hữu hạn hoặc tín hiệu phù hợp |
| Mong toàn bộ lịch sử theo mặc định | Stream bắt đầu từ next flushed event | `setStartTime` trước start |
| Không nhận event và suy ra bug | Có thể không có nguồn, chưa flush hoặc đã bị lọc | Kiểm tra producer/settings/retention |
| Dùng `start()` trong main mà cần đi tiếp | `start` có thể chặn thread | Dùng async và quản lý vòng đời |
| Chỉ test một stdout event count | Số event phụ thuộc thời gian và môi trường | Test hành vi, xử lý ca 0 |
| Không xử lý IOException | Repository có thể không mở/đọc được | Báo lỗi I/O riêng, không giả vờ thành công |
| Giữ mọi RecordedEvent vô hạn | Tăng memory không kiểm soát | Tổng hợp/queue có giới hạn |
| Giữ reference khi reuse mặc định | Nội dung event object có thể đổi sau callback | Sao chép field hoặc `setReuse(false)` |

## 13. Checklist vận hành

1. Xác minh **JVM producer** có recording ghi xuống disk và loại event quan tâm được bật.
2. Xác định **thư mục repository thực** có chứa JFR chunks, không đoán từ tên folder.
3. Chỉ mở nguồn **đáng tin** và có quyền đọc.
4. Chọn `EventStream.openRepository(Path)` thay vì `openRepository()` khi muốn **một đường dẫn cụ thể**.
5. Đặt `setStartTime` nếu cần đọc những event còn lưu từ trước.
6. Đăng ký `onEvent`/`onError` trước khi start.
7. Chọn `startAsync` nếu main thread còn việc phải làm; giữ stream sống đủ lâu.
8. Ghi nhận **số event nhận được thật**, kể cả 0, và phân biệt số 0 với `IOException`.
9. Không phụ thuộc vào thứ tự toàn cục hoặc callback tức thời.
10. Luôn đóng stream và giới hạn tài nguyên thu thập.

## 14. Bài thực hành

**Bài 1:** Dùng đoạn chương trình hoàn chỉnh, truyền một disk repository thực, chạy và ghi nhận số event. Lần lượt thử một file `capture.jfr` và một directory không tồn tại; phân biệt lỗi input với trường hợp không có event.

**Bài 2:** Đổi thành `onEvent("jdk.CPULoad", ...)`. Xác minh producer bật loại event này; giải thích vì sao 10 giây có thể nhận 0 event và vì sao không được gán số lượng kỳ vọng cố định.

**Bài 3:** So sánh chạy có và không có `setStartTime(Instant.now().minusSeconds(60))` trên cùng repository. Giải thích sự khác biệt khi có các event cũ vẫn còn giữ.

**Bài 4:** Viết phiên bản đóng ngay sau `startAsync()`; so sánh với phiên bản giữ stream trong năm giây. Nêu rủi ro flush delay và thread scheduling.

**Bài 5:** Thay bộ đếm tổng bằng `ConcurrentHashMap<String, LongAdder>` để thống kê từng event type. Tránh lưu toàn bộ event object vào collection không giới hạn.

**Bài 6:** Đặt `setEndTime(...)` trước `start`, có timeout chờ và cleanup. Giải thích vì sao `awaitTermination(Duration)` hết thời gian **không phải lệnh đóng stream**.

**Tiêu chí đạt:** Bạn xác định được repository path chính xác, dùng `openRepository(Path)` thay vì API đọc file, nhận hoặc giải thích đúng khi không có event, xử lý lỗi và đóng stream an toàn.

## Nguồn tham khảo chính thức

- [Oracle Java SE 17 — EventStream API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): `openRepository(Path)`, mốc thời gian, callback, lifecycle.
- [Oracle Java SE 26 — EventStream API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): xác nhận API còn được hỗ trợ, khuyến cáo chỉ đọc trusted disk repositories.
- [Oracle Java SE 17 — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): cấu hình `JFR.configure repositorypath` và start recording.
- [Oracle Java SE 17 — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `FlightRecorderOptions` và `StartFlightRecording`.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): API đã có từ Java 14.
- [dev.java — Configuring JDK Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/): cấu hình repository, event và retention.

**Ghi nhớ:** `EventStream.openRepository(Path)` **đọc disk repository có thật tại đường dẫn được chỉ định**, không mở file `.jfr`, không tự bật event ở nguồn và không đảm bảo nhận event tức thời. Muốn có kết quả đáng tin, hãy chọn đúng directory, xác định thời gian đọc, quản lý callback và đóng stream đúng vòng đời.