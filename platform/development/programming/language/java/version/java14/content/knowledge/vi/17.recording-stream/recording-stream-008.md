# Giới hạn dữ liệu lưu bằng `setMaxAge` và `setMaxSize` trong `RecordingStream`

## 1. Mục tiêu bài học và phiên bản Java

**Java Flight Recorder (JFR)** thu thập sự kiện từ JVM, ví dụ hoạt động garbage collection, thread, I/O hoặc các sự kiện do ứng dụng tự định nghĩa. `jdk.jfr.consumer.RecordingStream` cho phép chương trình Java **nhận các sự kiện JFR liên tục từ JVM hiện tại**, đăng ký callback rồi xử lý khi dữ liệu được phát tới stream.

Từ **Java 14, JEP 349 — JFR Event Streaming**, API `RecordingStream` được đưa vào Java như một phần khả năng theo dõi sự kiện thời gian gần thực. Khác với một file `.jfr` chụp theo đợt, recording stream có thể hoạt động lâu dài trong dịch vụ. Vì dữ liệu sự kiện được ghi và giữ trong **JFR disk repository**, không nên để thời gian/dung lượng giữ lại tăng lên không kiểm soát.

Hai phương thức chính để **giới hạn dữ liệu JFR được lưu lại cho stream** là:

```java
stream.setMaxAge(Duration.ofMinutes(5));
stream.setMaxSize(16L * 1024 * 1024);
```

- **`setMaxAge(Duration)`:** giới hạn **độ tuổi dữ liệu ghi đã lưu**. Khi dữ liệu trên đĩa cũ hơn khoảng thời gian cho phép, JVM loại bỏ dữ liệu cũ theo cơ chế lưu trữ JFR.
- **`setMaxSize(long)`:** giới hạn **dung lượng dữ liệu ghi được giữ lại**, đơn vị **byte**. Khi vượt giới hạn, JVM loại bỏ **chunk cũ nhất** để nhường chỗ cho chunk mới hơn.

**Quan trọng:** đây là giới hạn **retention của dữ liệu recording trên đĩa**, **không phải** giới hạn thời lượng chạy của `RecordingStream`, số event mỗi giây, dung lượng heap Java, CPU hay số callback được gọi. Vì JFR lưu dữ liệu theo **chunks**, các mốc không nên được hiểu là giới hạn tuyệt đối chính xác đến từng byte/từng mili giây của toàn bộ tiến trình.

Bài này sử dụng API **chuẩn, vẫn còn hiệu lực trên Java 17+**: `java.time.Duration`, `jdk.jfr.Event`, `jdk.jfr.Name` và `jdk.jfr.consumer.RecordingStream`. Không cần bật preview, không dựa vào cấu hình thử nghiệm hoặc cách làm đã lỗi thời.

Sau bài học, bạn sẽ biết lựa chọn khoảng giữ dữ liệu và dung lượng phù hợp, xử lý giá trị vô hạn, quản lý vòng đời stream, tránh mất dữ liệu khi consumer chậm, kiểm chứng qua mã Java 17+ và hiểu sự khác nhau giữa retention với export, filtering và event processing.

## 2. `RecordingStream` hoạt động như thế nào?

`RecordingStream` thuộc module **`jdk.jfr`**, package `jdk.jfr.consumer`. Mỗi đối tượng tạo một stream nhận các sự kiện của **JVM hiện tại**. Một quy trình điển hình:

1. Tạo `RecordingStream`.
2. Thiết lập retention `setMaxAge` và/hoặc `setMaxSize`.
3. Chọn sự kiện bằng `enable(Class)` hoặc `enable(String)`; nếu cần, đặt ngưỡng hoặc chu kỳ thu thập.
4. Đăng ký callback bằng `onEvent(...)` và handler lỗi bằng `onError(...)`.
5. Gọi `startAsync()` để xử lý trên luồng khác, hoặc `start()` để xử lý trong luồng gọi.
6. Trong quá trình chạy, JVM phát sinh và ghi các sự kiện. Consumer đọc các chunk/sự kiện được công bố rồi gọi callback.
7. Khi hoàn tất, `close()` để dừng stream và giải phóng tài nguyên; nên dùng `try-with-resources`.

Mô hình logic:

```text
JVM / ứng dụng sinh sự kiện
             |
             v
      Bộ đệm JFR
             |
             v
     JFR disk repository
       /           \
      /             \  Retention theo thời gian/dung lượng
     v               v
JFR chunks  ------>  chunk cũ được loại bỏ
     |
     v
RecordingStream đọc dữ liệu
     |
     v
onEvent(RecordedEvent) callback
     |
     v
Phân tích / thống kê / xử lý
```

*Lưu ý:* đây là sơ đồ khái niệm, không mô tả toàn bộ chi tiết nội bộ JVM; buffering, flush, chunk rotation và lịch dọn dữ liệu phụ thuộc triển khai.

Nếu không cấu hình giới hạn, Javadoc cảnh báo dữ liệu recording **có thể phát triển không giới hạn**, nhất là khi sự kiện được bật mà không được tiêu thụ kịp. Với stream chạy trong production nhiều giờ/ngày, hãy đặt **ít nhất một giới hạn hợp lý**, thường nên cân nhắc **cả hai**.

### 2.1. Không nhầm với lớp `Recording`

Hai API có tên gần nhau:

| API | Trọng tâm | `setMaxAge` / `setMaxSize` |
| --- | --- | --- |
| `jdk.jfr.Recording` | Điều khiển một recording: start/stop/dump, settings, retention | Giới hạn dữ liệu recording lưu ở disk repository |
| `jdk.jfr.consumer.RecordingStream` | Vừa thu thập vừa đọc sự kiện liên tục qua callback trong JVM hiện tại | Giới hạn dữ liệu giữ cho recording stream |
| `jdk.jfr.consumer.EventStream` | Interface chung để tiêu thụ sự kiện | **Không** định nghĩa trực tiếp hai setter này |

Cả `Recording` và `RecordingStream` đều có setter tương ứng, nhưng **không phải cùng một đối tượng**. Nếu code đang dùng `RecordingStream`, hãy gọi setter trên chính instance `RecordingStream` đó. `RecordingStream` **không có** cặp getter `getMaxAge()`/`getMaxSize()` như `Recording` trong Java 17; khi cần theo dõi cấu hình, lưu giá trị do ứng dụng thiết lập trong cấu hình/metric riêng.

## 3. `setMaxAge(Duration)`: giữ dữ liệu trong một cửa sổ thời gian

Chữ ký chính thức:

```java
public void setMaxAge(java.time.Duration maxAge)
```

`maxAge` là **khoảng thời gian lưu giữ tối đa** cho dữ liệu ghi trong repository. Ví dụ:

```java
stream.setMaxAge(Duration.ofMinutes(5));
```

Ứng dụng đang yêu cầu JVM **không giữ dữ liệu recording quá cũ** so với khoảng 5 phút cho stream. Khi dữ liệu vượt độ tuổi, JVM loại bỏ phần lưu trữ cũ theo cơ chế JFR. Đây là một **chính sách retention liên tục**, không phải “chạy stream trong 5 phút rồi dừng”.

Các ví dụ khác:

```java
stream.setMaxAge(Duration.ofSeconds(30));
stream.setMaxAge(Duration.ofMinutes(10));
stream.setMaxAge(Duration.ofHours(1));
```

Chọn giá trị dựa trên mục đích quan sát. Nếu chỉ cần sự kiện gần thời gian thực, retention ngắn có thể đủ. Nếu cần lưu lịch sử ngắn để điều tra hoặc dump sau sự cố, retention dài hơn hữu ích nhưng tăng nhu cầu dung lượng.

### 3.1. `null` có nghĩa **không giới hạn độ tuổi**

Javadoc của `RecordingStream.setMaxAge` quy định:

```java
stream.setMaxAge(null);
```

`null` có nghĩa **infinite age** (không đặt giới hạn tuổi theo API). Nó **không phải** lệnh đóng stream, không phải “xóa sạch dữ liệu”, và cũng không nghĩa là tắt JFR. Nếu `setMaxSize` đang có giới hạn, giới hạn dung lượng vẫn áp dụng.

**Không nhầm `Duration.ZERO` với `null`.** `null` là giá trị chính thức được API mô tả cho “vô hạn”; `Duration.ZERO` là khoảng thời gian bằng 0, không dùng nó như cách viết “không giới hạn”.

### 3.2. `Duration` âm gây lỗi

`setMaxAge(Duration.ofSeconds(-1))` ném `IllegalArgumentException` theo Javadoc. Validation này giúp phát hiện cấu hình sai trước khi chạy.

Đừng nhập cấu hình thời gian từ người dùng dưới dạng chuỗi rồi truyền thẳng vào API mà không xác minh. Nếu một cấu hình có nghĩa là “unlimited”, chuyển nó **có chủ đích** thành `null`; nếu chính sách của dịch vụ không cho phép unlimited, từ chối cấu hình ngay khi khởi động.

### 3.3. Giới hạn tuổi không hứa hẹn xóa đúng từng thời điểm tuyệt đối

JFR lưu dữ liệu theo **chunk** và có cơ chế flush/rotation. `setMaxAge` được dùng để thực thi chính sách giữ lại dữ liệu recording, không bảo đảm mỗi event vừa tròn 5 phút tuổi sẽ biến mất chính xác ở mili giây tiếp theo. Không dùng API này làm bộ xóa dữ liệu mang tính pháp lý tuyệt đối hoặc scheduler thời gian thực.

Nếu chính sách retention gắn với pháp lý/bảo mật, cần thiết kế cả chu trình lưu file dump, copy, backup, nơi event được chuyển tới và thời gian xóa ở các kho bên ngoài.

## 4. `setMaxSize(long)`: giới hạn dung lượng dữ liệu được giữ

Chữ ký chính thức:

```java
public void setMaxSize(long maxSize)
```

Giá trị `maxSize` đo bằng **byte**, không phải KiB/MiB, không phải số event. Ví dụ:

```java
long maxBytes = 16L * 1024 * 1024; // 16 MiB = 16_777_216 byte.
stream.setMaxSize(maxBytes);
```

Khi lượng dữ liệu lưu đã vượt mức, JVM loại bỏ **chunk cũ nhất** để nhường chỗ cho dữ liệu mới theo chính sách JFR. Điều đó có nghĩa stream ưu tiên **lịch sử gần hơn**, không có bảo đảm giữ toàn bộ lịch sử từ khi bắt đầu.

Một số đơn vị thường gặp:

| Mục tiêu | Biểu thức Java | Giá trị byte |
| --- | --- | ---: |
| 1 MiB | `1L * 1024 * 1024` | 1.048.576 |
| 16 MiB | `16L * 1024 * 1024` | 16.777.216 |
| 64 MiB | `64L * 1024 * 1024` | 67.108.864 |
| 128 MiB | `128L * 1024 * 1024` | 134.217.728 |

Dùng literal `long` hoặc nhân với `long` như `16L` để tránh tràn số nguyên với giá trị lớn. Không nhầm `16_000_000` (byte thập phân) với `16 * 1024 * 1024` (16 MiB).

### 4.1. `0` có nghĩa **không giới hạn dung lượng**

Theo Javadoc:

```java
stream.setMaxSize(0L);
```

Giá trị `0` là **infinite size**. Nó **không** nghĩa “lưu 0 byte”, “ngừng ghi” hay “xóa file repository”.

Đây là bẫy cấu hình phổ biến: nếu định dùng 0 để vô hiệu hóa storage, thực tế có thể bỏ giới hạn và gây tăng dung lượng. Không nên tự diễn giải 0 theo ý nghĩa trong API khác.

### 4.2. Giá trị âm gây `IllegalArgumentException`

```java
stream.setMaxSize(-1L); // Lỗi: giới hạn dung lượng âm.
```

Đây là một **đoạn minh họa cố ý phát sinh lỗi lúc chạy**, không nên đưa vào mã cấu hình production. Nếu nhu cầu là không giới hạn dung lượng, dùng đúng `0L` và có biện pháp giới hạn khác theo chính sách; nếu không, chọn số byte dương.

### 4.3. Đây không phải hard quota cho toàn bộ đĩa hay heap

`setMaxSize` chỉ giới hạn dữ liệu **được giữ cho recording stream**, không đặt trần cho:

- **Toàn bộ disk usage của hệ điều hành/JVM**: còn nhiều recording, stream và file khác cùng dùng đĩa.
- **Heap của callback hoặc queue ứng dụng**: bạn có thể vô tình giữ hàng triệu `RecordedEvent` hoặc object khác trong bộ nhớ dù repository có giới hạn.
- **Dung lượng file xuất hoặc log do ứng dụng tự ghi**: sau khi export/forward, các bản sao do hệ thống khác quản lý.
- **Mức tăng tạm thời khi JVM đang tạo chunk**: việc loại bỏ theo chunk không hứa hẹn mức sử dụng vật lý luôn nhỏ hơn chính xác `maxSize` từng byte.
- **Số sự kiện**: event có kích thước khác nhau, một số event còn chứa stack trace hoặc thông tin metadata.

Đặt `maxSize` là bước kiểm soát **retention**, không thay thế monitoring disk, kiểm soát backpressure, quota hệ thống hay retention của file xuất.

## 5. Dùng **cả hai** giới hạn và hiểu cơ chế loại bỏ

Có thể cấu hình đồng thời:

```java
stream.setMaxAge(Duration.ofMinutes(5));
stream.setMaxSize(16L * 1024 * 1024);
```

Chính sách mong muốn:

- Dữ liệu quá cũ theo **cửa sổ thời gian** sẽ không cần được giữ.
- Nếu tải sự kiện cao làm dữ liệu vượt **cửa sổ dung lượng**, JVM phải loại bỏ chunk cũ ngay cả khi thời gian chưa dài.
- Do đó lịch sử còn lại có thể **ngắn hơn 5 phút** khi hệ thống tạo nhiều sự kiện.
- Ngược lại, nếu lưu ít sự kiện, giới hạn tuổi có thể loại dữ liệu cũ dù tổng byte còn thấp.

Đừng suy ra rằng việc đặt cả hai giúp **bảo đảm luôn có đủ 5 phút dữ liệu**. Retention xác định giới hạn **phần lịch sử có thể giữ**, không phải cam kết về độ đầy đủ. Không có bảo đảm “nhận đủ mọi event trước khi xóa” chỉ vì callback đã đăng ký.

### 5.1. Ví dụ tình huống

Giả sử một ứng dụng yêu cầu giữ tối đa 5 phút và khoảng 16 MiB:

| Tình huống | Giới hạn đáng chú ý | Cần hiểu |
| --- | --- | --- |
| Event ít, một giờ mới có vài chunk | `maxAge` | Dữ liệu quá cũ được loại; byte thấp không có nghĩa giữ mãi |
| Event rất nhiều, 16 MiB đầy nhanh | `maxSize` | Chunk cũ bị loại, cửa sổ dữ liệu thực có thể ngắn hơn 5 phút |
| Consumer xử lý chậm | Cả hai | Dữ liệu cũ có nguy cơ bị loại trước khi xử lý |
| Stream vừa khởi động | Cả hai | Chưa có sẵn 5 phút lịch sử do stream mới tạo |
| Ứng dụng dump ra file `.jfr` | Retention + file export | File mới có vòng đời riêng, không tự bị setter xóa |
| Stream đã đóng | Không sửa được chính sách | Setter có thể ném `IllegalStateException` |

Các con số trong bảng chỉ là ví dụ. Để chọn cấu hình production, hãy đo thực tế **byte/s, chu kỳ flush/chunk, latency của consumer và mục đích giữ dữ liệu**; không sao chép 16 MiB như một giá trị “chuẩn” cho mọi dịch vụ.

### 5.2. Khi consumer không theo kịp

Nếu JVM ghi dữ liệu nhanh hơn tốc độ callback đọc/xử lý và kích thước/tuổi giữ lại có hạn, **các chunk cũ có thể bị xóa trước khi stream kịp xử lý**, dẫn tới thiếu lịch sử. Đó là một *trade-off* của retention có giới hạn.

Giải pháp không phải lúc nào cũng tăng size vô hạn. Hãy cân nhắc:

1. Giảm số lượng sự kiện bằng `enable` chỉ các event cần thiết; cấu hình threshold/period phù hợp.
2. Giữ callback ngắn, tránh I/O chậm và xử lý CPU nặng ngay trong `onEvent`.
3. Nếu cần chuyển sang worker riêng, dùng **queue có giới hạn** và chính sách overflow minh bạch; queue vô hạn chỉ chuyển rủi ro từ disk sang heap.
4. Theo dõi tốc độ event, độ trễ xử lý, lượng dữ liệu bị loại, disk pressure và dấu hiệu stream không theo kịp.
5. Điều chỉnh `maxAge` và `maxSize` theo dữ liệu đo đạc; dự liệu đỉnh tải và phản ứng khi hết dung lượng đĩa.

**Không dùng `setMaxAge` làm delay callback**. Độ trễ công bố event liên quan flush/buffering và nhịp consumer, chứ không trực tiếp bằng retention age.

## 6. Ví dụ hoàn chỉnh Java 17+: vừa giới hạn vừa nhận sự kiện

Ví dụ dùng một JFR event tự định nghĩa `demo.Pulse`. Callback chỉ giảm `CountDownLatch` khi nhận ít nhất một event, tránh phụ thuộc số event được gom ở từng chunk.

**Tệp `RecordingStreamRetentionDemo.java`:**

```java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public class RecordingStreamRetentionDemo {
    @Name("demo.Pulse")
    static class Pulse extends Event {
        int sequence;
    }

    public static void main(String[] args) throws Exception {
        long maxBytes = 16L * 1024 * 1024;
        CountDownLatch received = new CountDownLatch(1);

        try (RecordingStream stream = new RecordingStream()) {
            stream.setMaxAge(Duration.ofMinutes(5));
            stream.setMaxSize(maxBytes);

            stream.enable(Pulse.class).withoutThreshold();
            stream.onEvent("demo.Pulse", event -> received.countDown());
            stream.startAsync();

            for (int index = 0; index < 100; index++) {
                Pulse pulse = new Pulse();
                pulse.sequence = index;
                pulse.commit();
            }

            System.out.println("retentionMinutes=5");
            System.out.println("retentionBytes=" + maxBytes);
            System.out.println("eventSeen=" +
                    received.await(10, TimeUnit.SECONDS));
        }

        System.out.println("streamClosed=true");
    }
}
```

**Lệnh biên dịch/chạy:**

```bash
javac --release 17 -encoding UTF-8 RecordingStreamRetentionDemo.java
java RecordingStreamRetentionDemo
```

**Kết quả đã kiểm chứng trên HotSpot JDK 24:**

```text
retentionMinutes=5
retentionBytes=16777216
eventSeen=true
streamClosed=true
```

**Lưu ý tính bất đồng bộ:** `eventSeen=true` là kết quả đã quan sát khi callback được gọi trong thời gian chờ 10 giây. Trên JVM thiếu JFR, môi trường hạn chế quyền, quá tải hoặc khi callback chưa được xử lý kịp, đầu ra có thể khác hoặc stream không khởi tạo được. Ví dụ **không cam kết số event chính xác** và không đo đạc dung lượng thực của repository; nó chứng minh API cấu hình, vòng đời và cơ chế callback.

### 6.1. Vì sao trình tự này đúng?

- `stream.setMaxAge(...)` và `stream.setMaxSize(...)` chạy **trước `startAsync()`**, tránh một giai đoạn vô tình chạy với retention chưa cấu hình.
- `stream.enable(Pulse.class).withoutThreshold()` bật event tùy chỉnh, bỏ ngưỡng thời lượng đối với loại event này để ví dụ dễ quan sát.
- `stream.onEvent("demo.Pulse", ...)` chỉ xử lý event có tên tương ứng; callback trong ví dụ không giữ `RecordedEvent` vào bộ nhớ.
- `stream.startAsync()` đưa xử lý sự kiện sang luồng riêng. Phương thức `main` tiếp tục tạo các `Pulse` rồi `commit()`.
- `CountDownLatch` giúp `main` đợi **tín hiệu đã nhận ít nhất một event**, thay vì ngủ một khoảng cố định rồi đoán stream đã flush.
- `try-with-resources` tự gọi `close()` khi rời block, kể cả lúc có ngoại lệ. Đây là cách quản lý vòng đời hợp lệ trong Java 17.
- `System.out.println("streamClosed=true")` chạy sau khi `try` hoàn tất; nó mô tả rằng `close()` đã được gọi trên đường đi bình thường, **không** phải một phép đo trạng thái nội bộ qua getter.

### 6.2. Vì sao không dựa vào số lượng event cụ thể?

JFR có buffering/chunk flushing và phân phối event bất đồng bộ. Một số event phụ thuộc điều kiện runtime, sampling, cấu hình threshold, quyền JVM và thời điểm đóng stream. Vì vậy, test kiểu `assertEquals(100, numberOfEventsInCallback)` ngay sau `startAsync()` có thể không đáng tin.

Trong ví dụ này, ta chỉ chờ một event để minh họa API. Với ứng dụng sản xuất cần đo lường đầy đủ/không mất sự kiện, hãy thiết kế thêm giám sát, backpressure và chính sách xử lý việc mất sự kiện.

### 6.3. `start()` khác `startAsync()`

- `start()` xử lý sự kiện trong **luồng gọi**, về cơ bản sẽ chặn ở đó cho tới khi stream được đóng.
- `startAsync()` xử lý trong **luồng riêng** và trả về cho luồng gọi, phù hợp khi ứng dụng vẫn cần làm việc khác.
- Với Java 17, **`close()`** là thao tác dừng/giải phóng tài nguyên tiêu chuẩn. Một số API `stop()` được bổ sung sau các phiên bản JDK cũ hơn; không lấy code JDK mới rồi mặc định rằng mọi phương thức đều có ở `--release 17`.

`setMaxAge` và `setMaxSize` **không điều khiển hai cơ chế start này**. Stream có thể chạy nhiều giờ với retention 5 phút.

## 7. Kiểm tra đầu vào và trạng thái đóng của stream

Javadoc công bố các quy tắc cần biết:

| Phương thức | Giá trị hợp lệ đặc biệt | Giá trị âm | Stream đã `CLOSED` |
| --- | --- | --- | --- |
| `setMaxAge(Duration)` | `null` = không giới hạn tuổi | `IllegalArgumentException` | `IllegalStateException` |
| `setMaxSize(long)` | `0L` = không giới hạn dung lượng | `IllegalArgumentException` | `IllegalStateException` |

**Tệp `RetentionValidationDemo.java` — Java 17+:**

```java
import java.time.Duration;
import jdk.jfr.consumer.RecordingStream;

public class RetentionValidationDemo {
    public static void main(String[] args) {
        RecordingStream stream = new RecordingStream();
        try {
            try {
                stream.setMaxAge(Duration.ofSeconds(-1));
                System.out.println("negativeAgeRejected=false");
            } catch (IllegalArgumentException ex) {
                System.out.println("negativeAgeRejected=true");
            }

            try {
                stream.setMaxSize(-1L);
                System.out.println("negativeSizeRejected=false");
            } catch (IllegalArgumentException ex) {
                System.out.println("negativeSizeRejected=true");
            }

            stream.setMaxAge(Duration.ofSeconds(30));
            stream.setMaxSize(1024L * 1024);
            stream.setMaxAge(null);  // Unlimited age theo API.
            stream.setMaxSize(0L);   // Unlimited size theo API.
            System.out.println("unlimitedValuesAccepted=true");
        } finally {
            stream.close();
        }

        try {
            stream.setMaxAge(Duration.ofSeconds(10));
            System.out.println("closedAgeRejected=false");
        } catch (IllegalStateException ex) {
            System.out.println("closedAgeRejected=true");
        }

        try {
            stream.setMaxSize(4096);
            System.out.println("closedSizeRejected=false");
        } catch (IllegalStateException ex) {
            System.out.println("closedSizeRejected=true");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RetentionValidationDemo.java
java RetentionValidationDemo
```

**Stdout chính xác trên JDK có JFR hoạt động:**

```text
negativeAgeRejected=true
negativeSizeRejected=true
unlimitedValuesAccepted=true
closedAgeRejected=true
closedSizeRejected=true
```

Giải thích:

1. `Duration.ofSeconds(-1)` và `-1L` không có ý nghĩa retention hợp lệ, nên bị từ chối.
2. `setMaxAge(null)` và `setMaxSize(0L)` là hai **giá trị API đặc biệt có nghĩa không giới hạn**; được chấp nhận nhưng **không khuyến nghị cho stream production chạy lâu mà không có giới hạn khác**.
3. `close()` chuyển stream vào trạng thái không thể điều chỉnh retention; thử setter sau khi đã đóng dẫn đến `IllegalStateException`.
4. Các `try/catch` chỉ dành để giải thích hành vi API. Production nên **validate cấu hình trước** thay vì dựa vào exception khi chạy để quyết định policy.

**Không nhầm `0L` với một byte, và không dùng số âm làm “cờ tắt”**. Với `RecordingStream.setMaxSize`, không giới hạn theo size là `0L`; với `setMaxAge`, không giới hạn theo age là `null`.

## 8. Retention khác với event filtering, callback và thời gian chạy

Các API dễ nhầm nhưng không tương đương:

| Mục đích | API/liên quan | Ảnh hưởng chính |
| --- | --- | --- |
| Giữ tối đa một khoảng tuổi dữ liệu | `setMaxAge(Duration)` | Retention của dữ liệu ghi lưu trên đĩa |
| Giữ tối đa một lượng byte dữ liệu | `setMaxSize(long)` | Loại chunk cũ khi vượt giới hạn |
| Chọn loại sự kiện cần ghi | `enable(Class/String)`, `disable(...)` | Lượng/loại dữ liệu thu thập |
| Lọc theo threshold/period | `EventSettings.withThreshold`, `withPeriod` | Cách event được phát sinh/ghi tùy loại |
| Nhận sự kiện | `onEvent(...)` | Callback xử lý khi event được tiêu thụ |
| Kiểm soát bắt đầu/kết thúc tiêu thụ | `setStartTime`, `setEndTime` | Cửa sổ xử lý stream (khác retention) |
| Kết thúc xử lý và giải phóng tài nguyên | `close()` | Dừng/đóng stream |
| Lưu bản ghi thành file | `dump(Path)` (Java 17+) | Tạo file xuất từ dữ liệu ghi còn sẵn |

### 8.1. Không dùng `setMaxAge` để đặt thời gian chạy stream

`stream.setMaxAge(Duration.ofMinutes(5))` **không tương đương** “stream tự dừng sau 5 phút”. Nếu cần chạy trong đúng khoảng thời gian, thiết kế vòng đời ứng dụng hoặc dùng API thời gian bắt đầu/kết thúc sự kiện phù hợp. Đừng gán ngữ nghĩa scheduler cho setter retention.

### 8.2. Không dùng `setMaxSize` để hạn chế số callback

Dù giới hạn dữ liệu repository là 16 MiB, callback có thể nhận rất nhiều event liên tục qua thời gian nếu consumer theo kịp. `setMaxSize` **không** có nghĩa chỉ được gọi `onEvent` tối đa 16 triệu lần hoặc chỉ gửi một lượng bytes sự kiện cố định trong suốt vòng đời stream.

### 8.3. Giới hạn `RecordingStream` khác với giữ các `RecordedEvent` trong ứng dụng

Callback có thể đẩy event hoặc snapshot vào `List`, queue, cache hoặc gửi ra mạng. Dữ liệu này nằm **ngoài** phạm vi retention của JFR. Đừng làm:

```java
// Anti-pattern: cache không giới hạn mọi event trong heap.
List<RecordedEvent> allEvents = new ArrayList<>();
stream.onEvent(event -> allEvents.add(event));
```

Đây là **snippet minh họa rủi ro**, chưa có `imports`/`main` đầy đủ. Nếu sự kiện đến liên tục, `allEvents` sẽ tăng không giới hạn dù stream đã gọi `setMaxSize(...)`. Thay bằng bộ tổng hợp số liệu, ring buffer có giới hạn, queue bounded hoặc gửi sang hệ thống quan sát có retention riêng.

### 8.4. `dump(Path)` trên Java 17+

`RecordingStream.dump(Path)` tồn tại từ Java 17 và ghi dữ liệu recording còn sẵn thành file `.jfr`. Javadoc **khuyến nghị rất mạnh** đặt `maxAge` hoặc `maxSize` **trước khi bắt đầu stream**, nếu không bản dump có thể **không chứa event nào** tùy cách stream xử lý dữ liệu.

```java
// Snippet minh họa khi stream đã start và chưa close.
stream.dump(java.nio.file.Path.of("diagnostics.jfr"));
```

Dữ liệu đã bị loại khỏi retention **không được phục hồi** chỉ vì bạn gọi `dump`. File `diagnostics.jfr` mới có **vòng đời, quyền truy cập, dung lượng và chính sách xóa riêng**; setter của stream không giới hạn file dump sau khi xuất.

Đừng dump từng giây vào cùng hệ thống file mà không đặt retention cho các file xuất: rất dễ chuyển rủi ro tăng dung lượng từ JFR repository sang thư mục output.

## 9. Chọn giá trị `maxAge` và `maxSize` cho production

Không có một con số phù hợp với mọi dịch vụ. Hãy suy ra dựa trên **tốc độ sự kiện thực**, thời gian cần điều tra sự cố và giới hạn tài nguyên.

### 9.1. Câu hỏi cần trả lời

1. Bạn cần **nhìn ngược thời gian bao lâu** khi phát hiện spike? Vài chục giây, vài phút hay hàng giờ?
2. Ở tải bình thường và tải đỉnh, **JFR sinh bao nhiêu byte mỗi giây**?
3. Có cần dump file để điều tra không? File cuối cùng gồm những event nào và có bao nhiêu lịch sử hữu ích?
4. Consumer xử lý callback có nhanh hơn tốc độ phát sinh event không?
5. Có bao nhiêu recording/stream đồng thời trong JVM? Giới hạn mỗi stream **không** là tổng quota của máy.
6. Dữ liệu JFR có chứa stack trace, tên class hoặc thông tin người dùng cần hạn chế quyền truy cập không?
7. Nếu quá tải, bạn chấp nhận **mất sự kiện cũ** hay phải giảm tần suất recording/đổi kiến trúc thu thập?

### 9.2. Ước tính dung lượng ban đầu

Nếu quan sát tốc độ trung bình `R` byte/giây trong một khoảng và muốn giữ `T` giây, ước tính thô là:

\[
\text{bytes cần lưu} \approx R \times T
\]

Đây là **ước lượng để chọn cấu hình thử nghiệm**, không phải công thức chính xác của disk repository vì còn overhead/chunk rotation/sự biến động của tải. Ví dụ **minh họa giả định**:

- `R = 40 KiB/giây`, `T = 300 giây` → khoảng `12\,000 KiB \approx 11,72 MiB` trước overhead.
- Nếu chọn `maxSize = 16 MiB`, mức này có thể tạm phù hợp khi tải ổn định nhưng cần đo khi đỉnh tải và trong môi trường thật.
- Nếu đỉnh tải tăng gấp nhiều lần, dữ liệu có thể bị loại sớm hơn mốc `maxAge = 5 phút`.

Không coi các con số này là benchmark của Java hoặc JFR. Cần đo ở ứng dụng thực tế.

### 9.3. Cấu hình qua biến môi trường hoặc service config

Với ứng dụng có cấu hình `maxAgeMinutes` và `maxSizeMiB`, **validate trước khi tạo stream**:

```java
// Snippet bên trong code cấu hình, không phải chương trình độc lập.
if (maxAgeMinutes <= 0 || maxSizeMiB <= 0) {
    throw new IllegalArgumentException("Retention must be positive");
}

Duration age = Duration.ofMinutes(maxAgeMinutes);
long bytes = Math.multiplyExact(maxSizeMiB, 1024L * 1024L);

stream.setMaxAge(age);
stream.setMaxSize(bytes);
```

Phương thức `Math.multiplyExact` giúp phát hiện phép nhân vượt miền `long`. Vì `maxAgeMinutes` / `maxSizeMiB` là biến giả định của cấu hình, hãy thay bằng giá trị thực trong ứng dụng và có handling lỗi startup phù hợp. Trong sản phẩm yêu cầu giới hạn bắt buộc, **đừng tự chuyển 0 thành unlimited** khi người dùng nhập sai.

### 9.4. Đo thay vì chỉ dựa vào cấu hình

`RecordingStream` không cung cấp `getMaxAge()` hay `getMaxSize()` trong Java 17 như `Recording`. Lưu và xuất **metric cấu hình** của chính ứng dụng, đồng thời quan sát disk pressure tổng thể, lượng dữ liệu JFR sinh ra, độ trễ callback, số event nhận được và hiệu năng của toàn bộ hệ thống.

Nếu muốn chứng minh retention sau khi JVM dọn chunk, dùng test/stress môi trường có kiểm soát, tạo tải đủ dài để xuất hiện rotation và kiểm tra recording dump/chunks hoặc metrics JFR phù hợp; không lấy kết quả của một event nhỏ làm bằng chứng “luôn đúng 16 MiB”.

## 10. Bảo mật và vận hành lâu dài

JFR là công cụ observability, nhưng event/stack trace/tên class/tên thread có thể phản ánh cấu trúc nội bộ hoặc đôi khi chứa dữ liệu có tính nhạy cảm, tùy event và tùy ứng dụng. Cần áp dụng:

- **Quyền truy cập:** hạn chế ai có thể bật recording, đọc event/dump, tải file `.jfr`.
- **Dữ liệu tối thiểu:** chỉ enable event cần thiết; tránh đưa raw token, mật khẩu hay PII vào custom JFR event.
- **Retention cho mọi nơi lưu:** `setMaxAge`/`setMaxSize` chỉ áp dụng cho stream; file dump, object storage, log, APM và backup có chính sách riêng.
- **Cảnh báo dung lượng:** theo dõi cả thư mục repository, tổng số recordings/streams và những file được xuất.
- **Hiệu năng:** callback ngắn, không giữ vô hạn trong heap; chuẩn bị cơ chế khi consumer tụt hậu.
- **Đóng tài nguyên:** dùng `try-with-resources` hoặc cleanup theo shutdown của ứng dụng, tránh leak thread/resource.
- **Thử nghiệm có kiểm soát:** profiling/JFR overhead phụ thuộc loại event được bật, thresholds, sampling và khối lượng sự kiện; không giả định đặt retention là không tốn CPU/I/O.

Trong môi trường cần lưu dữ liệu dài hạn, nên dùng pipeline lưu trữ có lifecycle/retention phù hợp thay vì tắt mọi giới hạn của `RecordingStream` rồi để JVM giữ vô hạn.

## 11. Những lỗi thường gặp và cách sửa

### Lỗi 1 — Nghĩ `setMaxAge(Duration.ofMinutes(5))` khiến stream tự dừng

Sai: đó là **độ tuổi giữ dữ liệu**, không phải tổng thời gian hoạt động. Dùng cơ chế điều khiển vòng đời để đóng stream khi cần dừng.

### Lỗi 2 — Nghĩ `setMaxSize(0)` nghĩa là không lưu gì

Sai: **0 nghĩa là không giới hạn** theo Javadoc. Chọn số byte dương để giới hạn; nếu muốn tắt thu thập, thay đổi cấu hình sự kiện/stream, không dùng 0 làm cờ dừng.

### Lỗi 3 — Nghĩ `setMaxAge(null)` nghĩa là xóa mọi dữ liệu

Sai: `null` nghĩa **không giới hạn thời gian**. Nếu không muốn giữ dữ liệu theo thời gian dài, đặt `Duration` dương có ý nghĩa.

### Lỗi 4 — Nhập số âm

`setMaxSize(-1)` và `setMaxAge(Duration.ofSeconds(-1))` ném `IllegalArgumentException`. Validate cấu hình, không dùng số âm làm sentinel.

### Lỗi 5 — Gọi setter sau khi đóng stream

`stream.close(); stream.setMaxSize(1024);` sẽ phát sinh `IllegalStateException`. Thiết lập và điều chỉnh khi stream còn hợp lệ; sau close tạo stream mới nếu cần.

### Lỗi 6 — Giả định giới hạn byte là hard quota cho disk

JFR loại theo **chunk**, và repository còn dữ liệu khác. Đừng dựa vào 16 MiB như giới hạn tuyệt đối của cả hệ thống; cần giám sát tổng disk usage.

### Lỗi 7 — Cho rằng retention bảo đảm không mất callback

Khi consumer chậm hoặc tải tăng, dữ liệu cũ có thể bị dọn trước khi xử lý. Cần monitor/giảm tốc độ tạo event/tăng năng lực xử lý, không chỉ đặt cấu hình một lần rồi bỏ qua.

### Lỗi 8 — Cho rằng max size là số lượng event

`setMaxSize(10_000L)` biểu diễn **10.000 byte**, không phải 10.000 event. Kích thước event khác nhau, không thể quy đổi cứng một event một byte.

### Lỗi 9 — Nhầm `Duration.ZERO` với không giới hạn

Đối với tuổi, **`null` mới là giá trị “infinite” theo API**. Đừng áp dụng quy ước `0` của size cho tuổi một cách máy móc.

### Lỗi 10 — Dùng `Recording.getMaxSize()` như thể có trên `RecordingStream`

Hai lớp có API khác nhau. Với `RecordingStream` trên Java 17, lưu các tham số cấu hình trong ứng dụng; không gọi getter không tồn tại.

### Lỗi 11 — Chỉ giới hạn repository, còn event queue và file dump không giới hạn

`setMaxSize` không tự giới hạn `List<RecordedEvent>`, queue, `diagnostics.jfr` hoặc hệ thống APM. Từng nơi có giới hạn/lifecycle riêng.

### Lỗi 12 — Không đóng stream

Stream có thể giữ tài nguyên và tiếp tục hoạt động lâu hơn yêu cầu. Dùng `try-with-resources`; với ứng dụng chạy dài, quản lý lifecycle theo startup/shutdown và exception paths.

### Lỗi 13 — Đặt retention quá nhỏ và kết luận JFR bị hỏng

Nếu chunk bị loại trước lúc consumer đọc hoặc dump, có thể thiếu sự kiện. Hãy thử với retention hợp lý, đảm bảo stream hoạt động, đo throughput/latency và kiểm tra cấu hình event.

### Lỗi 14 — Nhầm lựa chọn `enable(...)` với retention

`enable("jdk.CPULoad")` quyết định loại event được thu thập; `setMaxAge` và `setMaxSize` quyết định lịch sử dữ liệu giữ lại. Hai nhóm tác động khác nhau nhưng **cùng cần thiết** trong thiết kế observability.

### Lỗi 15 — Dùng phương thức chỉ có ở JDK mới trong project `--release 17`

Kiểm tra Javadoc đúng phiên bản biên dịch, không chỉ phiên bản JVM đang cài. Code trong bài dùng `startAsync()`, `close()`, `setMaxAge`, `setMaxSize` và custom JFR `Event` đều hỗ trợ từ Java 17.

## 12. Checklist triển khai và kiểm thử

- [ ] Có ít nhất một giới hạn retention hữu hạn cho stream chạy lâu.
- [ ] Giá trị `Duration` và byte được chọn từ mục tiêu vận hành, không mặc định vô hạn.
- [ ] Đã hiểu `null` (age) và `0L` (size) là **unlimited**, không phải disable.
- [ ] Mọi giá trị cấu hình được validate và đổi đơn vị đúng.
- [ ] Không dùng `int` multiplication dễ overflow khi tính số MiB/GiB.
- [ ] Đặt các giới hạn **trước `startAsync()` hoặc `start()`**.
- [ ] Có callback, error handling và cleanup `close()` an toàn.
- [ ] Có theo dõi tốc độ events, thời gian xử lý và dấu hiệu consumer trễ.
- [ ] Có giới hạn queue/cache nội bộ nếu callback chuyển event đi nơi khác.
- [ ] Đã kiểm thử với peak load, JVM thực, môi trường disk thấp và rotation.
- [ ] Không suy ra retention chính xác đến từng byte hoặc một mili giây.
- [ ] File `.jfr` dump ra có chính sách quyền truy cập/xóa riêng.
- [ ] Không đưa thông tin nhạy cảm vào custom JFR event một cách tùy tiện.
- [ ] Có test xác nhận giá trị âm và setter sau `close()` bị từ chối.
- [ ] Có kế hoạch xử lý khi stream không thể truy cập repository hoặc JFR không được hỗ trợ.

## 13. Bài tập thực hành

1. **Cơ bản:** tạo `RecordingStream` và cấu hình giữ tối đa 2 phút, 32 MiB. Viết các lệnh `setMaxAge`/`setMaxSize` tương ứng.
2. **Giải thích:** nếu đặt `setMaxAge(Duration.ofMinutes(5))`, stream có tự đóng sau 5 phút không? Vì sao?
3. **Giá trị đặc biệt:** tìm ý nghĩa của `setMaxAge(null)` và `setMaxSize(0L)`. Vì sao nguy hiểm nếu dùng nhầm trong dịch vụ liên tục?
4. **Tính đơn vị:** 64 MiB là bao nhiêu byte? Vì sao nên dùng `64L * 1024 * 1024`?
5. **Cả hai giới hạn:** nếu tỷ lệ sinh dữ liệu quá cao, sự kiện mới 2 phút trước có chắc còn trong retention 5 phút không?
6. **Chunk eviction:** giải thích vì sao retention thực tế không phải hard quota chính xác từng byte.
7. **Lỗi cấu hình:** thử `Duration.ofSeconds(-1)` và `setMaxSize(-1)`, nêu exception.
8. **Lỗi vòng đời:** đóng stream rồi gọi `setMaxAge(Duration.ofMinutes(1))`, nêu exception.
9. **Callback:** sửa `RecordingStreamRetentionDemo` để chỉ tăng `AtomicInteger` trong callback, nhưng không giả định nhận đúng 100 event trong một deadline ngắn.
10. **Giới hạn queue:** nếu callback đẩy mọi `RecordedEvent` vào một `ArrayList` không giới hạn, `setMaxSize(16 MiB)` có chặn việc heap tăng không?
11. **Production:** ước tính byte/s từ tải thực, chọn retention và cách theo dõi dấu hiệu mất lịch sử.
12. **Dump:** nếu đã tạo `diagnostics.jfr`, hai setter có tự xóa file này khi hết tuổi không?
13. **So sánh API:** kể tên hai khác biệt thực tế giữa `Recording` và `RecordingStream`.
14. **Nâng cao:** thiết kế thử nghiệm gây tải event nhanh trong khi consumer xử lý chậm; xác định những metric và kết quả cần theo dõi.

**Đáp án định hướng:** (1) `Duration.ofMinutes(2)` và `32L * 1024 * 1024`; (2) không, retention khác runtime; (3) cả hai là vô hạn theo từng loại giới hạn; (4) 67.108.864 byte; (5) không chắc nếu size chạm trước; (6) xóa theo chunks; (7) `IllegalArgumentException`; (8) `IllegalStateException`; (9) callback bất đồng bộ; (10) không, heap ứng dụng là phạm vi khác; (11) đo tải thay vì dùng số cố định; (12) không, file dump có lifecycle riêng; (13) Recording điều khiển snapshot/recording, RecordingStream đọc liên tục qua callback; (14) theo dõi callback throughput, lag, disk, retained history và queue pressure.

## 14. Nguồn tài liệu chính thức

- **Oracle Java SE 17 Javadoc — `jdk.jfr.consumer.RecordingStream`:** `setMaxAge(Duration)`, `setMaxSize(long)`, `startAsync()`, `dump(Path)`, validation exceptions và giá trị vô hạn: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html
- **Oracle Java SE 25 Javadoc — `RecordingStream`:** xác nhận API retention vẫn còn hiệu lực trên JDK hiện đại: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html
- **Oracle Java SE 17 Javadoc — `jdk.jfr.Recording`:** so sánh với recording truyền thống và getters `getMaxAge`/`getMaxSize`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html
- **Oracle Java SE 17 Javadoc — `jdk.jfr.Event`:** khai báo và commit custom JFR events: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Event.html
- **OpenJDK JEP 349 — JFR Event Streaming:** nguồn gốc event streaming ở Java 14: https://openjdk.org/jeps/349
- **Oracle JDK 14 Release Notes — JEP 349 JFR Event Streaming:** xác nhận khả năng stream events được đưa vào Java 14: https://www.oracle.com/java/technologies/javase/14-relnote-issues.html

**Ghi nhớ:** `setMaxAge(Duration)` giữ dữ liệu ghi theo **cửa sổ thời gian**; `setMaxSize(long)` giữ dữ liệu theo **byte** và loại chunk cũ khi cần. `null` (age) và `0` (size) là **không giới hạn**. Đặt retention phù hợp **trước khi khởi chạy**, nhưng đừng nhầm nó với giới hạn heap, số event, thời gian hoạt động hay chính sách xóa các bản dump.