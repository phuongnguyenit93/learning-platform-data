# 18.2. JFR FileRead, FileWrite, SocketRead và SocketWrite theo thời lượng hoặc kích thước

## 1. Mục đích và giới hạn của bài

Khi một ứng dụng Java đáp ứng chậm, thời gian có thể được tiêu tốn ở thao tác đọc/ghi file hoặc socket. **Java Flight Recorder (JFR)** cho phép ghi lại những thao tác I/O nhất định thành các *duration events* để biết **thread nào**, **đối tượng file hoặc kết nối nào**, **mỗi thao tác mất bao lâu** và **đã chuyển bao nhiêu byte**.

Bốn event cần nhận diện:

- `jdk.FileRead` — một thao tác đọc từ file.
- `jdk.FileWrite` — một thao tác ghi vào file.
- `jdk.SocketRead` — một thao tác đọc từ socket.
- `jdk.SocketWrite` — một thao tác ghi vào socket.

**Trọng tâm của bài là hai chiều lọc khác nhau:** *thời lượng* (event diễn ra lâu) và *kích thước* (event chuyển nhiều byte). Một operation có thể chậm nhưng rất ít byte, hoặc nhanh nhưng rất nhiều byte. Vì thế không được coi “đọc nhiều dữ liệu” là “đọc chậm” hay ngược lại.

Sau bài này, bạn có thể:

1. Đọc đúng tên, trường dữ liệu và đơn vị của bốn event.
2. Hiểu rõ **JFR `threshold` dùng thời lượng**, còn lọc theo số byte thường được thực hiện **sau khi thu event**.
3. Bật và xác minh các event trong recording; lấy dữ liệu bằng `jfr`, JDK Mission Control hoặc API `RecordingFile`.
4. Phân nhóm theo path/endpoint/thread, tìm thao tác chậm hoặc nhiều byte và phân biệt những gì event thực sự chứng minh với giả thuyết về root cause.
5. Chạy ví dụ Java 17+ ghi cả bốn loại I/O rồi kiểm tra sự hiện diện của chúng trong file `.jfr`.
6. Tránh kết luận sai do threshold, thiếu event, các hoạt động concurrent hoặc giới hạn phạm vi instrument của JDK.

Phạm vi: các **sự kiện I/O JFR được JVM phát ra**, không phải một bộ đếm tất cả syscall của hệ điều hành hay giải pháp theo dõi toàn bộ mạng/ổ đĩa. Kết quả phụ thuộc JDK, VM, cấu hình event và đường API I/O mà ứng dụng thực sự sử dụng.

## 2. Đường đi từ I/O đến sự kiện JFR

~~~text
Code Java                        HotSpot/JDK instrumentation
----------                       ---------------------------
FileInputStream.read()  --------> jdk.FileRead
FileOutputStream.write() -------> jdk.FileWrite
Socket InputStream.read() ------> jdk.SocketRead
Socket OutputStream.write() ----> jdk.SocketWrite
                                           |
                                           | nếu event được bật
                                           | và duration đạt threshold
                                           v
                                     Event JFR
                        (startTime, duration, bytes, thread,
                         path hoặc host/address/port...)
                                           |
                                           v
                                    Recording .jfr
                                           |
                         +-----------------+----------------+
                         |                                  |
                    jfr print/view                    JMC / Java API
                         |                                  |
                         +--------------> phân tích <-------+
~~~

Đây là sơ đồ **minh họa những API phổ biến có instrumentation**. Không cam kết mọi lệnh `read()`/`write()` hoặc mọi API NIO/asynchronous/native đều sinh một event tương ứng trên mọi bản JDK. Một lời gọi thư viện có thể tạo nhiều thao tác ở tầng thấp, một thao tác có thể được gộp, hoặc một đường I/O không đi qua hook quan sát đang dùng. Kiểm chứng trên đúng JVM và workload thay vì đoán từ tên phương thức.

Bản ghi JFR có các **event đã qua bộ lọc**, không phải nhật ký hoàn chỉnh của mọi I/O. Nếu `threshold=20 ms`, một thao tác 2 ms có thể bị loại dù nó chuyển hàng MB. Ngược lại thao tác đọc 1 byte kéo dài 200 ms vẫn có thể xuất hiện.

### 2.1. Event duration là gì?

`RecordedEvent.getDuration()` trả về `java.time.Duration` của **một event**, tức khoảng thời gian được ghi nhận cho thao tác. Nó không bằng tổng latency của HTTP request, không luôn là thời gian thiết bị vật lý bận, và không phản ánh trực tiếp số byte/giây của toàn bộ ứng dụng. Thời lượng còn chịu ảnh hưởng của cách API vận hành, blocking, scheduling và instrumentation.

Ví dụ: `jdk.SocketRead` mất 180 ms để nhận 100 byte. Các nguyên nhân khả dĩ gồm đối tác phản hồi chậm, chờ dữ liệu, mạng, TLS/application framing hoặc lịch trình thread. **Event chỉ định vị thời gian của lời gọi**, chưa đủ kết luận mạng bị hỏng.

### 2.2. Event size là gì?

`bytesRead`/`bytesWritten` diễn tả **số byte được chuyển trong thao tác được ghi**. Nó không phải kích thước toàn bộ file, số byte của cả HTTP request, độ dài payload ở tầng nghiệp vụ, mức sử dụng băng thông trên dây hay dung lượng đĩa đã phân bổ.

Ví dụ, một lần `FileRead.bytesRead=8192` nghĩa là thao tác đó trả về 8192 byte theo instrumentation; file nguồn vẫn có thể dài vài GB. Một request đọc qua socket có thể chia thành nhiều sự kiện, mỗi sự kiện chỉ chứa một phần bytes.

## 3. Schema của bốn loại event

Các tên field sau khớp metadata quan sát được trên OpenJDK 24 và là mẫu thường gặp của HotSpot. **Khi tự động hóa phải đọc metadata của JDK/file thực tế**, bởi sự kiện nội bộ và field có thể khác giữa bản phát hành.

| Event | Trường riêng thường có | Ý nghĩa chính |
| --- | --- | --- |
| `jdk.FileRead` | `path: String`; `bytesRead: long`; `endOfFile: boolean` | File nào được đọc, số byte đọc, đã tới EOF hay chưa |
| `jdk.FileWrite` | `path: String`; `bytesWritten: long` | File nào được ghi, số byte ghi |
| `jdk.SocketRead` | `host: String`; `address: String`; `port: int`; `timeout: long`; `bytesRead: long`; `endOfStream: boolean` | Địa chỉ/port phía xa, timeout cấu hình (ms), lượng dữ liệu nhận, EOF trên stream |
| `jdk.SocketWrite` | `host: String`; `address: String`; `port: int`; `bytesWritten: long` | Đích socket phía xa và byte được ghi |

Cả bốn loại còn có các trường event chung như `startTime`, `duration`, `eventThread` và `stackTrace` (nếu recording thu stack). Khi dùng Java consumer API, nên lấy thời lượng bằng `event.getDuration()` và luồng bằng `event.getThread()`; không tự đoán cách diễn giải các tick raw trong file.

- `path` có thể là `N/A` hoặc không mang đường dẫn hữu ích khi dùng file descriptor, `System.in`/`System.out` hoặc một số nguồn đặc biệt. Không mặc định mọi file event đều có path tuyệt đối hợp lệ.
- `host` và `address` có thể khác nhau: tên host khác địa chỉ IP. `port` là **remote port**, không mặc định là cổng lắng nghe nội bộ của tiến trình đang phân tích.
- `timeout` của `SocketRead` là timeout cấu hình cho việc đọc (field annotated theo milliseconds), **không phải duration thực đã chờ**. Dùng `event.getDuration()` để đo thời lượng thao tác; tuyệt đối không gán nhầm `timeout=5000` thành “mất 5 giây”.
- `endOfFile` và `endOfStream` báo tình huống đọc kết thúc nguồn. Một event EOF với `bytesRead=0` không chứng minh đã chuyển 0 byte trong suốt phiên; nó chỉ mô tả riêng thao tác đó.
- `stackTrace` có thể `null` nếu event không bật stack, stack bị cắt theo cấu hình hoặc JVM không cung cấp. Không xây pipeline yêu cầu stack luôn có.

### 3.1. Kiểm tra field bằng công cụ của JDK

~~~bash
# Dùng JDK đang phân tích; xác nhận schema ngay trên JDK đó.
jfr metadata --events jdk.FileRead,jdk.FileWrite,jdk.SocketRead,jdk.SocketWrite

# Nếu đã có bản ghi, xem metadata chứa trong chính bản ghi:
jfr metadata --events jdk.FileRead,jdk.FileWrite,jdk.SocketRead,jdk.SocketWrite io-diagnostics.jfr
~~~

`jfr metadata` không phải là lệnh đếm số I/O đã diễn ra; nó mô tả schema. `jfr summary` và `jfr print` được dùng khi muốn xem **instance event có thật**. Một event có metadata không có nghĩa trong file có event instance.

## 4. Thời lượng và kích thước là hai tiêu chí độc lập

| Tiêu chí | Đo bằng | Áp dụng ở đâu | Rủi ro khi hiểu sai |
| --- | --- | --- | --- |
| **Duration** | `getDuration()` hoặc field `duration`, thường hiển thị ms | JFR có **`threshold`** lúc thu; cũng lọc lại sau ghi | Bỏ qua hàng nghìn I/O nhanh, dù tổng byte rất lớn |
| **Bytes** | `bytesRead` / `bytesWritten`, đơn vị **byte** | Thường **lọc trên sự kiện đã thu** bằng JMC/API/script | Dữ liệu dưới duration threshold chưa có trong file để lọc theo bytes |
| **Số lần** | Count các instance event | Tổng hợp theo time window và event type | Count trong file là **count sự kiện đủ điều kiện**, không nhất thiết count mọi lời gọi I/O |
| **Endpoint/path** | `path` hoặc `address/host + port` | Group/filter sau thu | Hostname không ổn định; path có thể chứa dữ liệu nhạy cảm hoặc bị ẩn |
| **Thread/stack** | `getThread()`, `getStackTrace()` | Điều tra caller và mã đang chờ | Stack có thể thiếu; không thay thế trace toàn request |

### 4.1. Ngưỡng thời lượng của JFR

Trong `jdk.jfr`, setting `threshold` biểu thị **duration nhỏ hơn ngưỡng sẽ không được ghi**. Có thể cấu hình bằng `EventSettings.withThreshold(Duration)`, `.jfc` hoặc công cụ điều khiển recording. Với nhiều cấu hình JFR mặc định/phổ biến, các sự kiện I/O có threshold ở khoảng **20 ms**; đó là **giá trị của cấu hình cụ thể**, không phải quy luật cố định của mọi JDK. `default.jfc`, `profile.jfc` hoặc cấu hình custom có thể khác nhau.

Ví dụ:

- `threshold=20 ms`: đọc 1 MiB trong 4 ms **không được ghi** bởi loại event này, dù byte nhiều.
- `threshold=20 ms`: đọc 16 byte trong 150 ms **có thể được ghi** nếu event type được bật và instrumentation thu được.
- `threshold=0`: không loại theo duration, thuận tiện cho đo ngắn trong môi trường lab nhưng có thể tạo **rất nhiều event**, tăng overhead, file size và chi phí phân tích.
- Event disabled thì `threshold=0` cũng không giúp; phải `enabled=true`.

**Không có setting chung “`sizeThreshold=1MB`” cho bốn built-in event này trong API `EventSettings`.** Nếu muốn mọi event ≥1 MiB dù chạy nhanh, giải pháp thường phải thu đủ các event cần thiết (giảm duration threshold phù hợp) rồi lọc `bytesRead/bytesWritten` **sau ghi**. Giảm threshold xuống 0 trong production có thể gây overhead rất lớn trên hệ thống thực hiện I/O tần suất cao.

### 4.2. Ví dụ phân loại cùng một tập dữ liệu

Đây là **bảng giả định để học cách diễn giải**, không phải output JFR của một máy thật:

| Event | Duration | Bytes | Nhận xét |
| --- | ---: | ---: | --- |
| `SocketRead` A | 210 ms | 96 B | Chậm, rất ít byte; nghi chờ peer/response |
| `FileRead` B | 3 ms | 4 MiB | Nhanh, nhiều byte; có thể vắng trong recording threshold 20 ms |
| `SocketWrite` C | 25 ms | 512 KiB | Vừa dài vừa nhiều byte; cần xem bối cảnh |
| `FileWrite` D | 1 ms | 0 B | Ghi không chuyển byte; cần kiểm tra trường hợp call cụ thể |
| `FileRead` E | 85 ms | 4 KiB | Chậm, byte ít; kiểm tra path, filesystem và caller |

Với `duration ≥20 ms`, tập còn A/C/E. Với `bytes ≥1 MiB`, tập chỉ có B **nếu B đã được thu**; nhưng file JFR ghi từ `threshold=20 ms` sẽ **không** có B. Kết luận “không có file read lớn” từ bản ghi đó là sai.

### 4.3. Dùng AND hay OR để trả lời đúng câu hỏi

- **Chậm:** `duration ≥ 20 ms`, không quan tâm bytes.
- **Lớn:** `bytes ≥ 1 MiB`, không quan tâm duration; chỉ làm được trên tập event thực sự đã được thu.
- **Vừa chậm vừa lớn:** `duration ≥ 20 ms AND bytes ≥ 1 MiB`.
- **Chậm hoặc lớn:** `duration ≥ 20 ms OR bytes ≥ 1 MiB`.

Hãy ghi rõ điều kiện trong bảng kết quả. Khi cần tìm “các request chuyển nhiều dữ liệu”, filter theo **một event có bytes lớn** có thể bỏ sót request gồm 100 thao tác nhỏ. Cần bổ sung phép tổng hợp theo request/connection/time window với ID hoặc trace ứng dụng phù hợp.

## 5. Thu bản ghi: chọn khoảng thời gian và kiểm tra sự kiện

Giả sử JVM HotSpot có PID `21891` và operator có quyền attach. Các lệnh sau chỉ là ví dụ; dùng `jcmd 21891 help JFR.start` trên đúng JVM trước khi áp dụng.

~~~bash
jcmd 21891 VM.version
jcmd 21891 help JFR.start

# Ghi tạm 1 phút với cấu hình profile (file do JVM tạo khi recording kết thúc).
jcmd 21891 JFR.start name=io-diag settings=profile duration=1m filename=/secure/jfr/io-diag.jfr

# Kiểm tra trạng thái và cấu hình thực sự:
jcmd 21891 JFR.check name=io-diag
~~~

`settings=profile` là điểm khởi đầu cho điều tra sâu hơn, **không đảm bảo** bốn event đều enabled với threshold mà bạn mong muốn. Hãy kiểm tra `.jfc`/settings và file sau ghi. Bật thêm event, giảm threshold hoặc mở stack traces có thể tăng chi phí CPU, I/O, dung lượng và ảnh hưởng latency. Ghi ngắn trên staging hoặc cửa sổ sự cố có kiểm soát trước khi triển khai kéo dài.

**Cần tùy biến threshold cho từng loại event:** cách dễ kiểm chứng trong Java API là:

~~~java
// Đoạn minh họa bên trong code đã có biến jdk.jfr.Recording recording:
recording.enable("jdk.FileRead")
         .withThreshold(java.time.Duration.ofMillis(5));
recording.enable("jdk.FileWrite")
         .withThreshold(java.time.Duration.ofMillis(5));
recording.enable("jdk.SocketRead")
         .withThreshold(java.time.Duration.ofMillis(20));
recording.enable("jdk.SocketWrite")
         .withThreshold(java.time.Duration.ofMillis(20));
~~~

Đoạn này **không phải chương trình độc lập**. Với JVM được theo dõi từ ngoài, có thể tạo bản `.jfc` tùy chỉnh bằng `jfr configure`, chỉnh bốn event và truyền `settings=/path/to/your.jfc` khi bắt đầu recording. Cú pháp `jfr configure` và event settings phải được kiểm tra bằng `jfr help configure` và metadata của bản JDK đang dùng. Tránh đổi template mặc định trong JDK hoặc bật `0 ms` vô thời hạn chỉ để tìm event hiếm.

### 5.1. Phân tích file đã thu

~~~bash
# Xác nhận file đọc được và có bao nhiêu instance mỗi loại:
jfr summary /secure/jfr/io-diag.jfr

# In riêng bốn loại; chú ý số lượng dữ liệu có thể rất lớn:
jfr print --events jdk.FileRead,jdk.FileWrite,jdk.SocketRead,jdk.SocketWrite /secure/jfr/io-diag.jfr

# Nếu JDK hỗ trợ, có thể dùng view để có báo cáo tổng hợp:
jfr view types /secure/jfr/io-diag.jfr
~~~

- `summary` trả về count và kích thước nội dung theo loại event; **count=0** có thể là không có thao tác, event disabled, threshold quá cao, recording sai khoảng thời gian hoặc không có instrumentation ở đường code đó.
- `print` hiện các instance, bao gồm duration, byte, thread, path/remote address; cách format có thể thay đổi theo JDK, vì vậy automation nên dùng API/định dạng có schema rồi kiểm tra thay vì tách dòng output tự do bằng vị trí cố định.
- `view` là công cụ tổng hợp hỗ trợ khi JDK có subcommand đó; xác minh bằng `jfr help view`. Không coi nó là bằng chứng mọi I/O đã được thu.
- Trong JDK Mission Control, kiểm tra các trang I/O/Socket, sắp xếp theo thời lượng, bytes hoặc số sự kiện; nhiều UI có aggregate theo host/path/thread. Hãy phân biệt chỉ số của **file đã được lọc threshold** với toàn bộ workload.

File `.jfr` có thể chứa path, host, IP, port, thread name và stack trace. Hãy cấp quyền truy cập theo chính sách bảo mật và không mặc định gửi file vào kênh công khai. Phải bảo đảm thư mục output tồn tại, JVM đích có quyền ghi và đủ dung lượng.

## 6. Ví dụ Java 17+: sinh và kiểm tra cả bốn event

Ví dụ chạy trong **một JVM**: bật bốn loại event với threshold 0, ghi/đọc một file tạm, tạo một `ServerSocket` loopback và trao đổi dữ liệu với `Socket` cục bộ, dừng/dump recording ra file `.jfr` rồi đọc bằng `RecordingFile`.

Nó cố ý in trạng thái **có ít nhất một event có bytes dương** cho từng loại thay vì in số event, duration hay kích thước chính xác (những con số đó phụ thuộc JDK, OS, flush và cách nhóm I/O). Vì `threshold=0` chỉ dùng trong chương trình ngắn này, **không copy nguyên cấu hình vào collector production chạy 24/7**.

Lưu tên `JfrIoEventsDemo.java`:

~~~java
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrIoEventsDemo {
    private static final String[] NAMES = {
        "jdk.FileRead", "jdk.FileWrite", "jdk.SocketRead", "jdk.SocketWrite"
    };

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("jfr-io-data-", ".bin");
        Path recordingFile = Files.createTempFile("jfr-io-recording-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                for (String name : NAMES) {
                    recording.enable(name)
                             .withThreshold(Duration.ZERO)
                             .withoutStackTrace();
                }
                recording.start();

                try (FileOutputStream out = new FileOutputStream(file.toFile())) {
                    out.write(new byte[] {1, 2, 3, 4});
                }
                try (FileInputStream in = new FileInputStream(file.toFile())) {
                    if (in.read() != 1) {
                        throw new IllegalStateException("File read failed");
                    }
                }

                try (ServerSocket server = new ServerSocket(
                        0, 1, InetAddress.getLoopbackAddress())) {
                    Thread replyThread = new Thread(() -> {
                        try (Socket accepted = server.accept()) {
                            byte[] request = accepted.getInputStream().readNBytes(4);
                            if (request.length != 4) {
                                throw new IOException("Incomplete request");
                            }
                            accepted.getOutputStream().write(new byte[] {5, 6, 7});
                        } catch (IOException e) {
                            throw new IllegalStateException(e);
                        }
                    }, "loopback-reply");
                    replyThread.start();

                    try (Socket client = new Socket(InetAddress.getLoopbackAddress(),
                                                    server.getLocalPort())) {
                        client.getOutputStream().write(new byte[] {1, 2, 3, 4});
                        byte[] response = client.getInputStream().readNBytes(3);
                        if (response.length != 3) {
                            throw new IOException("Incomplete response");
                        }
                    }
                    replyThread.join();
                }

                recording.stop();
                recording.dump(recordingFile);
            }

            Map<String, Boolean> found = new LinkedHashMap<>();
            for (String name : NAMES) found.put(name, false);

            try (RecordingFile reader = new RecordingFile(recordingFile)) {
                while (reader.hasMoreEvents()) {
                    RecordedEvent event = reader.readEvent();
                    String name = event.getEventType().getName();
                    if (!found.containsKey(name)) continue;
                    String field = name.endsWith("Read") ? "bytesRead" : "bytesWritten";
                    if (event.hasField(field) && event.getLong(field) > 0) {
                        found.put(name, true);
                    }
                }
            }
            for (Map.Entry<String, Boolean> entry : found.entrySet()) {
                System.out.println(entry.getKey() + "=" + entry.getValue());
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(recordingFile);
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+ có JFR**. Mẫu cần quyền tạo tệp trong thư mục tạm và mở socket loopback:

~~~bash
javac JfrIoEventsDemo.java
java JfrIoEventsDemo
~~~

Stdout **đã được xác minh trực tiếp trên OpenJDK 24**:

~~~text
jdk.FileRead=true
jdk.FileWrite=true
jdk.SocketRead=true
jdk.SocketWrite=true
~~~

**Cách hiểu:**

- Mỗi dòng `true` nghĩa là trong recording có ít nhất một instance có `bytesRead` hoặc `bytesWritten` >0, thuộc loại tương ứng. Nó không nói số event tổng cộng, tổng byte, độ trễ hay rằng JVM luôn phát đúng một event cho một lời gọi.
- Nếu môi trường khác cho `false`, kiểm tra khả năng JFR, thread/IO API, recording settings, quyền loopback, JVM/version và metadata trước khi quy kết lỗi Java. Ví dụ cố ý không “bịa” một duration/bytes cố định.
- `Recording.enable(name).withThreshold(Duration.ZERO)` giúp thu thao tác ngắn trong bài lab. `withoutStackTrace()` giảm dữ liệu call stack của bốn loại event, nên không thể dùng output này để kết luận method gây I/O; hãy bật stack trong phiên điều tra khi cần.
- `recording.stop()` rồi `dump()` chỉ ghi bản sao file từ dữ liệu recording đã dừng, trước khi `close()`.
- `RecordingFile` đọc từng `RecordedEvent` và kiểm tra tên/field thay vì parse text output. Nó vẫn cần xử lý schema khác nếu bạn muốn dùng ở nhiều JDK.
- `finally` xóa file tạm; có thể còn file nếu quá trình bị kill đột ngột, vì vậy môi trường thật phải quản lý cleanup/retention.

## 7. Lọc theo thời lượng hoặc kích thước bằng Java API

Đây là **đoạn code minh họa bên trong vòng đọc `RecordedEvent`**, không phải chương trình độc lập. Nó thể hiện việc phân biệt các thao tác chậm ≥20 ms và các thao tác lớn ≥1 MiB. Điều kiện phụ thuộc event đã thực sự được ghi.

~~~java
// "event" là jdk.jfr.consumer.RecordedEvent đang đọc từ RecordingFile.
String type = event.getEventType().getName();
boolean read = type.equals("jdk.FileRead") || type.equals("jdk.SocketRead");
boolean write = type.equals("jdk.FileWrite") || type.equals("jdk.SocketWrite");
if (read || write) {
    String bytesField = read ? "bytesRead" : "bytesWritten";
    if (event.hasField(bytesField)) {
        long bytes = event.getLong(bytesField);
        java.time.Duration elapsed = event.getDuration();
        boolean slow = elapsed.compareTo(java.time.Duration.ofMillis(20)) >= 0;
        boolean large = bytes >= 1024L * 1024L;

        if (slow || large) {
            // Sau đây là policy phân tích: ghi metric/bản tóm tắt phù hợp.
            System.out.printf("%s slow=%s large=%s%n", type, slow, large);
        }
    }
}
~~~

**Không biến đoạn code thành parser production ngay:** bạn còn phải xác định path/endpoint, thời gian window, xử lý null/field khác schema, storage/privacy, khả năng thiếu event và tải phân tích. Chỉ bắt exception kiểu parsing rồi thay bytes=0 sẽ tạo số liệu sai. Khi API field không tồn tại, báo schema mismatch thay vì gán ý nghĩa nhầm.

Để gom theo cùng một endpoint, bạn có thể định danh:

- File: `event.getString("path")`, chuẩn hóa theo policy (đường dẫn tạm có ID ngẫu nhiên có thể làm cardinality nổ).
- Socket: `host/address/port`, lưu ý cùng IP có nhiều dịch vụ theo port và cùng endpoint có thể có nhiều connections.
- Window: `getStartTime()`/`getEndTime()`, cùng timezone/clock để đối chiếu với log ứng dụng.
- Thread: `event.getThread()`, thuận tiện tìm call site khi stack có mặt nhưng không luôn đồng nghĩa với “request owner”.

### 7.1. Một bài toán tổng hợp minh họa

Trong cửa sổ 60 giây có 3 `SocketRead` cùng peer:

| Sự kiện | Duration | bytesRead |
| --- | ---: | ---: |
| R1 | 100 ms | 100 |
| R2 | 5 ms | 4000 |
| R3 | 180 ms | 100 |

Nếu **đã thu đủ ba event** (threshold cho phép):

- Tổng count = 3, tổng bytesRead = **4.200 B**.
- Tổng duration = **285 ms**, duration trung bình = **95 ms/event**.
- Theo ngưỡng 20 ms: có 2 event chậm, count 2, bytes của event chậm = **200 B**.
- Nếu recording threshold 20 ms, R2 (5 ms, 4000 B) có thể **không tồn tại** trong file: count và tổng bytes được tính từ JFR khi đó chỉ là thống kê **trên các event đạt ngưỡng**, không phải số I/O thật.
- Tổng duration 285 ms không nhất thiết có nghĩa ứng dụng mất 285 ms wall-clock: các sự kiện ở thread khác có thể chồng lấp và cùng một socket có thể được xử lý đồng thời theo kiến trúc ứng dụng.

**Tỷ số bytes/tổng duration không phải băng thông mạng thực.** Với hoạt động chờ nhiều, nó giống tốc độ chuyển dữ liệu theo *thời gian lời gọi ghi nhận*; muốn đo throughput thật, dùng tổng byte trong khoảng **wall-clock** có đầy đủ coverage, và đối chiếu network/OS metrics.

## 8. Cách diễn giải khi điều tra I/O chậm

### 8.1. SocketRead lâu, byte ít

Ví dụ một `SocketRead` mất 450 ms nhưng chỉ nhận 32 B:

- Có thể request đang chờ server/peer gửi dữ liệu, mạng bị trễ, server backend chậm, hoặc ứng dụng có khoảng chờ giữa các frame.
- `duration` mô tả thao tác đọc; nó **không** đo trực tiếp RTT, congestion hay thời gian HTTP server xử lý.
- Xem host/address/port, thread name, stack nếu bật, timestamp và ứng dụng đang ở bước nào; ghép với distributed trace, server log và network metrics để phân biệt.

Đặc biệt, `SocketRead.timeout` là giá trị cấu hình, không phải thời gian chờ thật. Nếu timeout=5000 ms nhưng event duration=40 ms, không được nói thao tác mất 5 giây.

### 8.2. SocketWrite lâu hoặc nhiều byte

Socket write trả về khi dữ liệu được chấp nhận bởi API/socket stack theo semantics, **không phải bằng chứng toàn bộ remote service đã nhận và xử lý dữ liệu**. Duration cao có thể liên quan backpressure, send buffer, tốc độ peer đọc, TLS wrapper hoặc scheduling. Bytes lớn có thể do batch payload, không phải lỗi hiệu năng.

Tìm kết nối có tổng ghi lớn hoặc event ghi kéo dài; đối chiếu ứng dụng có đang streaming/upload đúng thiết kế không. Với HTTPS, event `SocketWrite` phản ánh byte tầng socket (có thể là ciphertext/framing), không nhất thiết đúng kích thước payload nghiệp vụ.

### 8.3. FileRead/FileWrite kéo dài

File I/O chậm có thể liên quan disk, filesystem, network mount, antivirus, page cache, contention hoặc scheduling. Một `FileRead` nhanh không chứng minh ổ đĩa vật lý nhanh vì dữ liệu có thể đến từ OS page cache; một `FileWrite` nhanh không chứng minh dữ liệu đã được `fsync` an toàn tới ổ lưu trữ.

Đối chiếu path (nếu có), mount/volume, file size thực, IOPS, disk latency, queue depth, JVM thread stack, GC/CPU pressure và workload cùng thời điểm. Sự kiện JFR thường không đo riêng thời gian `fsync` hay mức độ durability. Nếu nghi log flush hoặc JDBC storage, cần thêm bằng chứng ở tầng phù hợp.

### 8.4. “Không có event” không có nghĩa “không có I/O”

Một ghi nhận rỗng có thể do:

1. Event type không được enabled trong `.jfc`/recording.
2. Duration của tất cả thao tác nhỏ hơn threshold.
3. Recording bắt đầu quá muộn, kết thúc trước workload hoặc bị lỗi dump.
4. Code dùng API không phát sinh loại event này với JDK cụ thể.
5. Thao tác diễn ra trong tiến trình khác/native code không nằm trong JVM đang ghi.
6. Đã lọc sai event name khi dùng `jfr print`/JMC.
7. Recording file bị thiếu chunk, chưa được dump/stop đúng hoặc không được đọc đủ.

Do đó, luôn dùng `jfr summary`, metadata, timestamp, settings và một thao tác kiểm chứng nhỏ trước khi tin vào “zero I/O”.

## 9. Tư duy phân tích theo workload và giới hạn số liệu

| Điều muốn biết | JFR hỗ trợ thế nào | Cần thêm gì để kết luận |
| --- | --- | --- |
| Thao tác file chậm nhất là gì? | Sắp `jdk.FileRead/FileWrite` theo `duration` | Đối chiếu path, OS disk metrics, stack |
| Peer nào làm read chờ lâu? | Group `SocketRead` theo host/address/port và xem duration | Client/server trace, timeout/retry, network metrics |
| File nào được đọc nhiều byte? | Group `FileRead.bytesRead` | Threshold thấp đủ để không bỏ sót file read nhanh; filesystem/process counters |
| Tổng traffic ứng dụng là bao nhiêu? | Tổng bytes từ event đã thu là một tín hiệu | Socket metrics/telemetry đầy đủ, TLS framing và socket khác |
| I/O có gây p99 HTTP request chậm? | Thread/timestamp/stack có thể nêu đường nghi ngờ | Span request, correlation ID, app latency timeline |
| Có bao nhiêu lời gọi I/O mỗi giây? | Count event theo time window | Xác minh coverage, threshold, instrumentation; không gọi count event là count syscall |
| Mỗi sự kiện được thu từ thread nào? | `eventThread` và stack nếu bật | Mapping sang executor/task/request context |
| Lỗi retry, timeout, EOF có nguyên nhân gì? | `SocketRead.timeout`, `endOfStream`, `FileRead.endOfFile` bổ sung bối cảnh | Exception/log ứng dụng, protocol state, telemetry từ peer |

**Không cộng thời lượng của bốn event rồi coi là “tổng thời gian ứng dụng ngừng hoạt động”.** Có thể có event ở nhiều thread trùng thời gian, hoặc một request cùng sử dụng FileWrite và SocketWrite. Cần đo critical path bằng tracing ứng dụng nếu mục tiêu là latency người dùng.

**Không tổng hợp bytes trên hai phía của cùng một kết nối nội bộ rồi xem đó là traffic toàn hệ thống duy nhất.** Một JVM chạy client và server loopback như bài lab sẽ ghi cả SocketWrite phía gửi lẫn SocketRead phía nhận; đó là hai quan sát của luồng dữ liệu, không phải hai payload độc lập.

## 10. Overhead, an toàn dữ liệu và môi trường triển khai

### 10.1. Trade-off khi giảm threshold

Giảm threshold có thể tăng số event, độ lớn recording, CPU và chi phí stack trace/aggregation. Dùng ngưỡng lớn để xác định **spikes chậm**, rồi thu ngắn với ngưỡng thấp hơn nếu cần thống kê đủ **byte/count**. Không dùng mức 0 ms vô thời hạn trong hệ thống I/O dày mà chưa benchmark.

Thiết kế thử nghiệm: thu baseline throughput/p95/p99/error rate và CPU; bật cấu hình JFR trong một cửa sổ tải tương đương; đo thay đổi; giảm event hoặc tăng threshold nếu có tác động vượt ngân sách. Với recording chạy dài, đặt `maxage`/`maxsize` và theo dõi dung lượng/repository.

### 10.2. Field có thể nhạy cảm

`path`, `host`, `address`, `port`, `thread name`, `stackTrace` có thể tiết lộ cấu trúc hệ thống, tên file của người dùng hoặc điểm kết nối nội bộ. Không đưa raw path/endpoint có cardinality vô hạn vào metric label. Chỉ lưu thông tin đủ cho điều tra, hạn chế đọc file `.jfr` theo quyền, xóa file tạm sau khi phân tích.

### 10.3. Triển khai ngoài JVM được kiểm tra

JDK/vendor khác có thể thay đổi event, field hoặc hành vi instrument. `jfr metadata` của bản ghi và code kiểm tra `event.hasField(...)` giúp tránh fail âm thầm. Với JVM trong container, chú ý PID namespace, quyền `jcmd` và đường filesystem của JVM đích. NIO, asynchronous I/O, virtual threads hoặc native libraries có thể làm event coverage khác; phải thực nghiệm với API đang dùng.

Khi file JFR lớn, `jfr print` toàn bộ có thể tạo lượng stdout khổng lồ: chọn loại event, khoảng thời gian nếu công cụ hỗ trợ, dùng `jfr view`/JMC hoặc API streaming `RecordingFile` với bounded aggregation. Với dashboard liên tục, cân nhắc telemetry ứng dụng/OpenTelemetry và metrics OS bên cạnh JFR; không biến bản ghi sự cố thành nguồn số liệu duy nhất.

## 11. Lỗi phổ biến

| Sai lầm | Tại sao sai | Cách sửa |
| --- | --- | --- |
| `FileRead` hiếm nên file ít được đọc | Threshold loại hết thao tác ngắn | Đọc settings và kiểm chứng workload |
| `SocketRead.timeout = 2000` nghĩa là read mất 2 giây | Timeout là giới hạn cấu hình | Dùng `getDuration()` để lấy duration thật |
| `bytesWritten` là kích thước response HTTP | Socket có framing/TLS và nhiều lần write | Đo payload nghiệp vụ riêng, hoặc phân tích tổng hợp có ngữ cảnh |
| Dùng `duration` để tính throughput toàn app | Các event không chắc phủ toàn bộ I/O và có overlap | Dùng wall-clock và tổng byte hợp lệ, đối chiếu telemetry khác |
| Lọc “bytes ≥1MiB” sau khi thu ở threshold 20ms rồi kết luận đủ | I/O lớn nhưng nhanh đã bị loại | Hạ duration threshold cho cửa sổ đo khi chi phí chấp nhận |
| Cộng socket read và write của loopback vào một traffic “unique” | Hai phía cùng quan sát cùng dữ liệu | Chỉ định hướng/endpoint rõ ràng |
| FileWrite nhanh nghĩa là ghi xuống ổ bền vững | Write có thể vào cache/buffer | Phân biệt write với fsync/flush/durability |
| Bật cả bốn event threshold 0 trong production không giới hạn | Event volume và overhead có thể lớn | Thử ngắn, giới hạn thời gian/dung lượng và đo tác động |
| Một sự kiện JFR là một request | Một request có thể nhiều I/O; nhiều request dùng một socket | Dùng ID/trace ứng dụng để liên kết |
| Stack luôn tồn tại để tìm call site | Có thể tắt stackTrace | Bật stack khi điều tra cần và benchmark overhead |
| Đổi JDK nhưng giữ parser hard-code field | Schema có thể thay đổi | Kiểm tra `jfr metadata`/`hasField` khi nâng cấp |

## 12. Bài tập và tự kiểm tra

**Bài 1 — phân biệt hai tiêu chí.** Có `FileRead` 2 ms/8 MiB và `SocketRead` 150 ms/128 B. Nếu threshold thu là 20 ms, event nào có thể xuất hiện? Chỉ socket read. Nếu muốn tìm 8 MiB file read phải làm gì? Thu với threshold thấp hơn (đã đo overhead), sau đó lọc `bytesRead`.

**Bài 2 — đơn vị.** `SocketRead.timeout=3000`, `getDuration()=120 ms`, `bytesRead=64`. Timeout là bao nhiêu? 3000 ms **giá trị cài đặt**. Thao tác ghi nhận 120 ms và 64 B, chưa xác nhận lỗi mạng hay server.

**Bài 3 — thước đo.** Trong 1 phút có 100 socket reads đều 5 ms và 8 KiB, nhưng JFR threshold 20 ms. `summary` trả count=0. Có được kết luận network throughput=0 không? Không; các thao tác không đủ duration để thành event.

**Bài 4 — cộng thời gian.** Hai thread song song, mỗi thread có `SocketRead.duration=100 ms` cùng khoảng 10:00:00.000–10:00:00.100. Tổng duration=200 ms, elapsed window chỉ 100 ms. Không dùng 200 ms làm latency wall-clock của request nếu chưa phân tích critical path.

**Bài 5 — nhân bản dữ liệu.** JVM vừa tạo loopback client vừa tạo loopback server và ghi 1 MiB. Trong recording có `SocketWrite.bytesWritten≈1 MiB` và `SocketRead.bytesRead≈1 MiB` cho cùng trao đổi. Có được nói “2 MiB dữ liệu độc lập đã được chuyển” không? Không; đó là hai góc quan sát của một luồng dữ liệu.

**Bài 6 — nguyên nhân gốc.** Top event `FileWrite` là 500 ms, `bytesWritten=512`; JVM dùng ổ đĩa mạng. Những nguồn nào cần đối chiếu? Thread stack, thời điểm, app log, OS I/O wait và filesystem/network mount metrics, GC/CPU để phân biệt stalls.

**Bài 7 — kiểm tra code.** Chạy `JfrIoEventsDemo`, sau đó thử `.withThreshold(Duration.ofSeconds(10))` cho bốn event. Vì sao có thể in `false`? Bốn thao tác mẫu ngắn hơn 10 giây nên bị loại. Không đổi logic in boolean để ép ra `true`.

**Bài 8 — chọn phép lọc.** Yêu cầu “các I/O ≥10 MiB *hoặc* ≥100 ms”. Hãy viết điều kiện `bytes >= 10*1024*1024 || duration >= 100 ms` trên event đã thu. Giải thích vì sao `threshold=100ms` lúc ghi sẽ không bao giờ bảo đảm có đủ các event ≥10 MiB chạy nhanh.

## 13. Checklist vận hành

- [ ] Có đúng JVM/PID và đúng khoảng thời gian đang có hiện tượng I/O chậm.
- [ ] Xác nhận bốn event enabled và biết ngưỡng `threshold` thực tế.
- [ ] Biết duration là thời lượng một event, bytes là số byte **trên thao tác đó**, không đồng nhất với request/file/connection total.
- [ ] Đã xem `jfr summary` và metadata của file để tránh kết luận từ event count rỗng.
- [ ] Chọn filter duration, bytes, AND/OR và grouping theo path/peer/thời gian có chú giải rõ.
- [ ] Hiểu dữ liệu thiếu vì threshold hoặc instrumentation, không thay bằng 0.
- [ ] Kết hợp thread/stack/app trace và OS metrics trước khi xác định root cause.
- [ ] Theo dõi overhead, retention, dung lượng, quyền truy cập và cleanup của `.jfr`.

**Kết luận:** JFR cung cấp bằng chứng hữu ích cho **thời lượng** và **số byte** của các thao tác file/socket được ghi lại. Điều kiện thu `threshold` chủ yếu kiểm soát **thời lượng**, còn yêu cầu “I/O bao nhiêu byte” phải phân tích từ field trên **những event đã có**. Hãy đọc đủ schema, giới hạn capture và workload trước khi biến kết quả thành đánh giá hiệu năng.

## Tài liệu đối chiếu

- Oracle Java SE 21, [The jfr Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html) — `metadata`, `summary`, `print` và `view`.
- Oracle Java SE 21, [The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html) — `JFR.start`, `JFR.check` và tùy chọn thu recording.
- Oracle Java SE 21, [jdk.jfr Package](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html) — `enabled`, `threshold`, `period` và `stackTrace`.
- Oracle Java SE 21, [EventSettings](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html) — `withThreshold(Duration)` và cấu hình event.
- Oracle Java SE 21, [RecordedEvent](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html) — `getDuration`, `getStartTime`, `getEndTime`.
- Oracle Java SE 21, [Recording](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html) và [RecordingFile](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html) — bật/ghi/dump và đọc `.jfr` bằng Java.
- Oracle Java SE 21, [Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/) — điều tra điểm nghẽn I/O bằng JFR, threshold và tác động của việc thu thêm event.
