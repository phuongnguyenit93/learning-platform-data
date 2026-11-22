# 16.9. Phân biệt xử lý event trực tiếp với đọc file; độ trễ và chi phí của consumer

Java Flight Recorder (JFR) cho phép ghi lại các sự kiện JVM và ứng dụng mà không cần chèn log thủ công vào mọi chỗ. Khi cần viết chương trình phân tích JFR, một quyết định quan trọng là **nhận sự kiện liên tục khi JVM đang chạy** hay **đọc một tệp recording đã được lưu**. Hai cách đều dùng dữ liệu JFR, nhưng khác nhau về thời điểm có dữ liệu, chi phí vận hành, tính đầy đủ của bằng chứng và vòng đời consumer.

Trong bài này, “xử lý event trực tiếp” nghĩa là **JFR event streaming** với `RecordingStream` hoặc `EventStream` đọc repository đang được ghi. Nó **không** có nghĩa rằng `Event.commit()` sẽ gọi đồng bộ callback trong cùng thread như một listener Java thông thường. Event streaming vẫn đi qua bộ đệm và các lần flush; **gần thời gian thực không đồng nghĩa tức thì**.

Bài tập trung vào Java 17+ và các API trong `jdk.jfr` / `jdk.jfr.consumer`: cách chọn active/passive stream, phân biệt đọc file, đo độ trễ, quản lý callback và so sánh chi phí thực tế.

## 1. Tách ba phần: nguồn event, nơi ghi, và consumer

Một JFR event được tạo khi JVM hoặc mã ứng dụng đánh dấu một hoạt động: GC pause, CPU load, file read, allocation sample, hay một custom event. JFR chỉ thu những event đang được **enable** và thỏa cấu hình như threshold, period hoặc stack-trace setting.

Mô hình khái niệm:

```text
JVM / ứng dụng tạo event
         │
         ▼
JFR ghi nhận sự kiện được bật
         │ (thread-local buffers, các tầng bộ đệm/chunk)
         ▼
JFR recording/repository ───────────┬────────────────────┐
         │                           │                    │
         ▼                           ▼                    ▼
 EventStream đọc                Dump/stop recording   RecordingStream
 repository đang ghi                 │                tạo recording
         │                           ▼                    │
         ▼                      Tệp .jfr                stream event
 onEvent / onFlush                  │                    │
         │                           ├── RecordingFile    ▼
    tổng hợp/alert                   └── EventStream.openFile
                                         │
                                         ▼
                                    phân tích offline
```

Sơ đồ mô tả **vai trò API** chứ không khẳng định có ba luồng dữ liệu hoàn toàn độc lập: `RecordingStream` vừa tạo recording riêng cho JVM hiện tại, vừa đăng ký consumer; `EventStream.openRepository()` là consumer thụ động đọc repository, không tự cấu hình recording mới. Các event có thể được giao cho consumer theo **batch** sau khi flush.

Đọc file và streaming không phân biệt bằng việc “có callback hay không”. `EventStream.openFile(path)` **cũng** gọi `onEvent(...)`, nhưng nguồn là **tệp đã có**; nó không theo dõi những event mới trong JVM như một live repository stream.

## 2. Bốn API chủ đạo và điều kiện sử dụng

| API Java 17+ | Nguồn | Ai kiểm soát việc ghi JFR? | Dùng khi |
| --- | --- | --- | --- |
| `new RecordingStream()` | JVM **hiện tại**, đang chạy. | Chính stream có thể `enable/disable` event, đặt period/threshold và giữ recording. | Viết một ứng dụng/agent trong process cần phát hiện tín hiệu khi chạy. |
| `EventStream.openRepository()` | Repository JFR của JVM **hiện tại**; có overload nhận thư mục repository. | Consumer này **không tự bật recording**; dữ liệu do recording đang được JVM/ứng dụng khác cấu hình. | Nghe thụ động những event đã được bật bởi recording khác. |
| `EventStream.openFile(Path)` | Một tệp `.jfr`. | Tệp đã được tạo; không thay đổi nguồn ghi. | Muốn callback/filter/aggregate từ dữ liệu lưu trữ. |
| `new RecordingFile(Path)` | Một tệp `.jfr`. | Tệp đã được tạo; consumer tự duyệt tuần tự. | Muốn một vòng lặp phân tích, chủ động kiểm soát bộ nhớ và trạng thái đọc. |

`RecordingFile.readAllEvents(path)` tiện cho tệp nhỏ vì trả về `List<RecordedEvent>`, nhưng **không nên dùng với recording lớn**: danh sách và object events có thể tiêu tốn nhiều heap. Thay bằng `RecordingFile` + `hasMoreEvents()/readEvent()` hoặc `EventStream.openFile()`.

Có một trường hợp mở rộng: `RemoteRecordingStream` (qua JMX/remote connector được hỗ trợ) cho phép consumer chạy ngoài JVM đích. Khi đó serialization, mạng, quyền truy cập và xử lý phía remote sẽ bổ sung chi phí. **Không đánh đồng** việc đọc một file `.jfr` được copy ra máy phân tích với kết nối streaming từ xa; file đã lưu có thể xử lý offline mà JVM nguồn không còn chạy.

### Sự khác biệt giữa “active” và “passive” stream

`RecordingStream` là **active**: khởi tạo một recording cho JVM hiện tại và có thể điều khiển event settings:

```java
try (var stream = new jdk.jfr.consumer.RecordingStream()) {
    stream.enable("jdk.CPULoad")
          .withPeriod(java.time.Duration.ofSeconds(1));
    stream.onEvent("jdk.CPULoad", event -> {
        double percent = 100.0 * event.getFloat("jvmUser");
        System.out.printf("JVM user CPU: %.2f%%%n", percent);
    });
    stream.start();
}
```

Đây là đoạn minh họa có đủ import qua tên fully qualified và có thể đặt trong phương thức `main`; riêng đoạn `try` **không phải cả tệp Java độc lập**, và `start()` sẽ chạy chặn đến khi stream được đóng. Ví dụ chương trình hoàn chỉnh, có giới hạn thời gian, xuất hiện ở phần thực hành bên dưới.

`EventStream.openRepository()` là **passive**: nó đọc các event đã được các recording khác tạo. Theo mặc định, stream bắt đầu từ **sự kiện tiếp theo được flush**, không tự tua về toàn bộ lịch sử; muốn điều chỉnh thời điểm đọc cần `setStartTime(...)` trước `start()`, trong giới hạn dữ liệu còn được repository giữ. Nếu không có recording nào đang bật event tương ứng, callback sẽ không có gì để xử lý.

## 3. Streaming không phải callback đồng bộ tại `commit()`

Giả sử ứng dụng gọi `event.commit()` vào 10:00:00.000. JFR có thể chưa chuyển ngay event ra cho người đọc: event đi qua bộ đệm, chunk/flush, rồi thread consumer mới phân tích và gọi action. Điều này tạo ra một khoảng trễ.

Javadoc `EventStream` của JDK 17 nêu rõ:

- Event được **giao theo batch**; `onFlush(Runnable)` chạy sau khi batch được flush, phù hợp để đẩy thống kê đã tích lũy.
- Các event **trong một batch** được sắp theo thời điểm kết thúc nếu giữ mặc định ordered; **giữa các batch** không có cam kết thứ tự thời gian toàn cục tuyệt đối.
- `start()` xử lý trong thread gọi; `startAsync()` xử lý callback ở thread riêng, không biến callbacks thành nhiều worker song song.
- `close()` dừng stream và giải phóng tài nguyên; thao tác này **không bảo đảm** mọi callback đã chạy hết khi trả về.
- Khi xử lý cần sự kiện sau callback, hãy hiểu rõ `setReuse(boolean)`: ở chế độ reuse, cùng object `RecordedEvent` có thể được dùng lại cho event khác.

**Độ trễ streaming không có một SLA cố định chỉ từ việc chọn API.** Nó phụ thuộc thời điểm flush, event rate, khối lượng dữ liệu, năng lực CPU/I/O, lịch scheduler, số lượng consumer, thao tác trong callback, và cách repository ghi/giữ dữ liệu.

## 4. Độ trễ của consumer phải đo từ mốc đúng

Đặt:

- `t_event_end`: timestamp kết thúc event được ghi trong `RecordedEvent.getEndTime()`.
- `t_visible`: lúc event/batch đã đủ dữ liệu để stream có thể đọc.
- `t_callback`: lúc callback thực sự chạy và hoàn tất phần trích xuất tối thiểu.
- `t_action`: lúc dashboard/alert/đầu ra cuối đã nhận kết quả, nếu có.

Các độ trễ mang ý nghĩa khác nhau:

```text
delivery lag   = t_callback - t_event_end
processing lag = t_action - t_callback
end-to-end lag = t_action - t_event_end
```

Đây là **thước đo thời gian quan sát được**, không phải thời gian GC/CPU của event. Với một duration event dài, `getEndTime()` phù hợp hơn `getStartTime()` khi bạn đang đo “sau khi hoạt động kết thúc bao lâu mới thấy event”.

Ví dụ giả định:

| Mốc | Thời điểm |
| --- | --- |
| Event kết thúc | 12:00:00.000 |
| JFR có batch để đọc | 12:00:00.350 |
| Callback xử lý event | 12:00:00.420 |
| Metric/alert được gửi xong | 12:00:00.700 |

Khi đó: delivery lag = **420 ms**, processing lag = **280 ms**, end-to-end lag = **700 ms**. Bốn thời điểm chỉ minh họa phép tính, **không phải mức trễ tiêu chuẩn của JFR**. Nếu callback bị chặn bởi I/O hay lock, `t_callback` tiếp tục lùi và việc xử lý những event sau cũng trễ.

Trên một process, có thể ước lượng `Duration.between(event.getEndTime(), Instant.now())` trong callback. Đây là **wall-clock estimate**, có thể nhiễu bởi việc điều chỉnh đồng hồ hệ thống và chi phí callback. Với consumer từ xa, timestamp máy nguồn và thời gian máy consumer cần đồng bộ; clock skew có thể tạo số đo âm hoặc rất sai. Đo độ trễ xử lý nội bộ bằng đồng hồ monotonic (`System.nanoTime()`) quanh callback/queue; **không trừ hai giá trị nanoTime ở hai JVM khác nhau**.

### File reader có độ trễ kiểu khác

Với chế độ dump/stop → đọc `.jfr`:

```text
sự kiện xảy ra
    → ghi/flush recording
    → dump hoặc stop tạo tệp hoàn chỉnh
    → copy/tải file (nếu khác máy)
    → consumer mở file, parse và phân tích
```

**Thời gian đến khi có kết quả** phụ thuộc cả lịch xuất file và chuyển file, nhưng **throughput đọc file** có thể rất cao khi bạn xử lý liên tục offline. Vì thế không so sánh “consumer đọc file được 100.000 event/s” với “live stream báo chậm 2 giây” như hai con số cùng loại. Một con số là tốc độ phân tích dữ liệu có sẵn, con số kia là thời gian từ lúc event phát sinh đến lúc quan sát.

## 5. Chi phí nằm ở đâu?

Chọn streaming hay đọc file không quyết định toàn bộ overhead. Cần tách **chi phí nguồn ghi JFR** và **chi phí consumer**.

| Nguồn chi phí | Streaming | Đọc file |
| --- | --- | --- |
| Tạo event, lấy stack trace, sampling, threshold | Có; phụ thuộc loại event/settings được bật. | Đã trả khi recording được ghi; phần đọc offline không tự thay đổi settings ở JVM nguồn. |
| JFR buffer và repository/chunk | Có theo cách JFR vận hành. | Đọc các chunk đã hoàn thành trong tệp. |
| Parse/khởi tạo `RecordedEvent` | Có, lặp liên tục trong thời gian chạy. | Có, tập trung khi phân tích file. |
| Sắp xếp event | Có thể tốn chi phí khi ordered. | Tùy API/cách phân tích và thứ tự event. |
| Aggregate/filter | Có trong callback, thường liên tục. | Có trong vòng lặp hoặc file event callback. |
| In log, gọi HTTP, ghi DB mỗi event | Có thể làm consumer tụt lại sau nguồn. | Cũng tốn chi phí, nhưng có thể chạy ngoài production và kiểm soát batch/retry. |
| Memory/GC của consumer | Ảnh hưởng trực tiếp JVM nếu consumer nằm cùng process. | Có thể chuyển sang JVM/máy phân tích riêng. |
| File storage/transfer | Repository và retention; remote stream có chi phí mạng/serialization. | Dung lượng `.jfr`, I/O đọc/copy/lưu và an toàn dữ liệu. |

**Chi phí phát sinh từ cấu hình event rất quan trọng.** Bật hàng loạt sự kiện stack trace ở threshold bằng 0, hoặc custom event với payload lớn trên mỗi request, có thể khiến producer nặng dù callback chỉ tăng bộ đếm. Không nên dùng một con số overhead phần trăm cố định cho mọi cấu hình.

**Chi phí callback rất dễ vượt quá chi phí ghi nhận event.** Một `System.out.println(event)` trên mọi event, serialize JSON lớn, gọi REST API hoặc truy DB đồng bộ có thể tốn nhiều CPU/I/O, giữ lock và làm cả luồng consumer chậm. Hãy trích field cần dùng, cộng dồn counters trong bộ nhớ, và xuất định kỳ theo batch.

### Retention không phải cơ chế backpressure đầy đủ

`RecordingStream.setMaxAge(Duration)` và `setMaxSize(long)` giới hạn lượng recording data được giữ (theo thời gian hoặc byte) trong quá trình stream. Chúng giúp khống chế tăng trưởng dung lượng, **không bảo đảm xử lý chính xác một lần mọi event** hay buộc producer phải chờ consumer chậm. Khi quá tải và dữ liệu cũ bị loại theo retention, consumer có thể bỏ lỡ các event không kịp đọc; bên cạnh đó, threshold/sampling và bộ đệm JFR có thể ảnh hưởng lượng event thực sự ghi nhận.

Nếu hệ thống yêu cầu **audit delivery exactly-once hoặc không mất bản ghi**, JFR stream thường không phải hàng đợi bền vững có ACK/replay chuẩn nghiệp vụ. Sử dụng một pipeline sự kiện nghiệp vụ có cơ chế lưu, retry, dedup và checkpoint phù hợp; dùng JFR để chẩn đoán/quan sát.

## 6. Thiết kế callback nhẹ và quản lý batch

Một consumer có độ trễ thấp thường làm ít việc trong `onEvent`:

1. Chỉ subscribe những event cần thiết bằng `onEvent("event.name", ...)`.
2. Trong callback, trích ngay các scalar fields cần dùng và tăng counter/sum hoặc ghi vào một **bounded queue**. Không giữ toàn bộ `RecordedEvent` khi không cần.
3. Dùng `onFlush` để gom và xuất thống kê batch (với mức I/O có kiểm soát).
4. Đặt giới hạn cho queue, nêu rõ khi đầy sẽ drop, coalesce, sample hay giảm tốc độ thu. Không để queue tăng vô hạn.
5. Ghi nhận consumer lag, queue size, error count và thời điểm batch xử lý xong.
6. Khi dừng, xác định liệu còn cần drain queue/flush kết quả cuối; `close()` của JFR stream tự nó không phải cam kết drain mọi callback.

### `setReuse` và `setOrdered` cần hiểu đúng

```java
stream.setReuse(true);   // giảm cấp phát RecordedEvent; không giữ object sau callback
stream.setOrdered(false); // giảm công sắp xếp nếu không cần thứ tự thời gian
```

Đây là **các dòng minh họa** đặt trước `start()` của một `EventStream` hoặc `RecordingStream`, không phải chương trình hoàn chỉnh. Tài liệu JDK 17 nói `RecordedEvent` có thể được **tái sử dụng mặc định**; nếu callback muốn lưu object và dùng sau callback, phải gọi `setReuse(false)` trước khi bắt đầu hoặc **tốt hơn, copy ngay giá trị thiết yếu** sang DTO immutable. Đừng đẩy reference đến object có thể bị tái sử dụng vào queue rồi đọc sau, vì field có thể không còn thuộc event ban đầu.

`setOrdered(false)` giúp bỏ bước sắp xếp trong một số trường hợp nhưng consumer **không còn dựa vào thứ tự event** để dựng timeline. Nếu phải ghép các event theo thời gian, giữ ordered và vẫn kiểm tra timestamp — thứ tự đảm bảo **trong batch**, không phải mọi batch đều liên tục toàn cục.

### Xử lý lỗi và vòng đời

Đăng ký `onError(Consumer<Throwable>)` để ghi nhận sự cố callback/parser; nếu không có handler, mặc định lỗi có thể được in lên stderr. Nhưng **bắt lỗi không có nghĩa stream sẽ tự restart hoặc không mất dữ liệu**. Với consumer dài hạn, có chính sách retry có giới hạn, health check và cảnh báo.

`start()` chạy chặn trong thread hiện tại. `startAsync()` chạy callback ở thread riêng; code khởi động có thể tiếp tục, nhưng khi ra khỏi `try-with-resources`, stream đóng. Một lỗi phổ biến là `startAsync()` rồi kết thúc `main` ngay: chưa có thời gian flush event nên tưởng recording hỏng.

## 7. Ví dụ chạy được 1 — streaming từ chính JVM (Java 17+)

Chương trình `LiveCpuStream.java` sau tạo `RecordingStream`, bật sự kiện CPU định kỳ, tính số event/độ trễ quan sát được cho từng batch và **dừng sau 10 giây**. Nó không gọi HTTP hay log từng event; chỉ in một dòng khi `onFlush` có mẫu.

```java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import jdk.jfr.consumer.RecordingStream;

public final class LiveCpuStream {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger samplesInBatch = new AtomicInteger();
        AtomicLong lastDeliveryLagMs = new AtomicLong(-1);

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable("jdk.CPULoad")
                  .withPeriod(Duration.ofSeconds(1));

            stream.setMaxAge(Duration.ofMinutes(1));
            stream.setMaxSize(16L * 1024 * 1024);

            stream.onEvent("jdk.CPULoad", event -> {
                long lag = Duration.between(
                        event.getEndTime(), Instant.now()).toMillis();

                samplesInBatch.incrementAndGet();
                lastDeliveryLagMs.set(lag);
            });

            stream.onFlush(() -> {
                int n = samplesInBatch.getAndSet(0);
                if (n > 0) {
                    System.out.printf(
                            "batchSamples=%d lastDeliveryLagMs=%d%n",
                            n, lastDeliveryLagMs.get());
                }
            });

            stream.onError(error -> error.printStackTrace(System.err));
            stream.startAsync();

            Thread.sleep(10_000);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac LiveCpuStream.java
java LiveCpuStream
```

**Output có điều kiện:** có thể thấy các dòng dạng:

```text
batchSamples=2 lastDeliveryLagMs=428
batchSamples=1 lastDeliveryLagMs=365
```

Đây là **số liệu minh họa**, không phải stdout cố định: số batch, số event, mốc flush và lag biến động theo JVM, scheduling và tải. Có thể nhận ít mẫu hơn mong đợi nếu không flush kịp trước khi chương trình đóng stream. Thời gian 10 giây tính từ sau `startAsync()`, không bảo đảm đúng 10 event: `jdk.CPULoad` là periodic event và phải đi qua pipeline JFR. Nếu thử nhiều lần, hãy so **độ trễ phân bố** qua khoảng thời gian dài hơn thay vì một dòng.

`onFlush` ở đây chỉ lấy số mẫu của batch vừa quan sát, không phải tổng event JFR đang được JVM tạo. Nếu cần một khoảng thời gian chính xác hơn, dùng timestamp/định nghĩa window rõ ràng và ghi nhận khi batch đến muộn. Trong production, ngay cả xuất một dòng mỗi batch cũng phải cân nhắc tần suất và stdout overhead.

## 8. Ví dụ chạy được 2 — tạo file và đọc offline (Java 17+)

Để so sánh một cách có kiểm soát, phần này **tạo một file `batch.jfr` chứa 5 custom events**, sau đó đọc bằng `RecordingFile`. Khác ví dụ live, sau khi tạo file xong bạn có thể phân tích lại bao nhiêu lần tùy ý mà không cần JVM nguồn vẫn chạy.

### 8.1. Tạo recording

Tạo file `WriteBatchJfr.java`:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class WriteBatchJfr {
    @Name("demo.Batch")
    public static final class BatchEvent extends Event {
        public int units;
    }

    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording()) {
            recording.enable(BatchEvent.class)
                     .withThreshold(Duration.ZERO);
            recording.start();

            for (int i = 1; i <= 5; i++) {
                BatchEvent event = new BatchEvent();
                event.units = 10 * i;
                event.commit();
            }

            recording.stop();
            recording.dump(Path.of("batch.jfr"));
        }

        System.out.println("Created batch.jfr");
    }
}
```

Biên dịch và chạy:

```bash
javac WriteBatchJfr.java
java WriteBatchJfr
jfr summary batch.jfr
```

Nếu tạo file thành công, **stdout của chương trình Java** là:

```text
Created batch.jfr
```

`jfr summary` sẽ in metadata, thời lượng và các loại event của recording, phụ thuộc bản JDK và môi trường; đừng coi đó là phần cố định của stdout chương trình. Custom event có tên `demo.Batch` và mỗi event mang `units=10,20,30,40,50`. Việc bật rõ loại event với threshold bằng 0 giúp ví dụ không phụ thuộc sampling/threshold mặc định.

### 8.2. Đọc tuần tự, không giữ toàn bộ sự kiện trên heap

Tạo file `ReadBatchJfr.java`:

```java
import java.nio.file.Path;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class ReadBatchJfr {
    public static void main(String[] args) throws Exception {
        int count = 0;
        long totalUnits = 0;

        try (RecordingFile file =
                     new RecordingFile(Path.of("batch.jfr"))) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();

                if ("demo.Batch".equals(event.getEventType().getName())) {
                    count++;
                    totalUnits += event.getInt("units");
                }
            }
        }

        System.out.printf(
                "count=%d totalUnits=%d%n", count, totalUnits);
    }
}
```

Biên dịch và chạy **sau khi đã có file `batch.jfr`**:

```bash
javac ReadBatchJfr.java
java ReadBatchJfr
```

**Stdout nếu cả hai bước chạy thành công:**

```text
count=5 totalUnits=150
```

Đây là kết quả xác định vì đã tự tạo đúng 5 `demo.Batch` events. Trong thực tế, nhiều loại event hệ thống khác có thể có trong file, nhưng bộ lọc `getEventType().getName()` chỉ cộng sự kiện do bài tập tạo.

Vòng lặp này duyệt file tuần tự: mỗi lượt chỉ giữ một `RecordedEvent` cùng hai biến tổng hợp, không tải sẵn cả danh sách. **Không đồng nghĩa bộ nhớ tiêu thụ chỉ đúng một event**, vì parser JFR còn có state/cache/chunk; tuy vậy nhìn chung phù hợp hơn `RecordingFile.readAllEvents(...)` khi file lớn.

### 8.3. Callback từ **file** vẫn là offline

Cùng một tệp có thể đọc qua `EventStream.openFile`. Tạo file độc lập `ReadBatchWithCallbacks.java`:

```java
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import jdk.jfr.consumer.EventStream;

public final class ReadBatchWithCallbacks {
    public static void main(String[] args) throws Exception {
        AtomicInteger count = new AtomicInteger();
        AtomicLong units = new AtomicLong();

        try (EventStream stream =
                     EventStream.openFile(Path.of("batch.jfr"))) {
            stream.onEvent("demo.Batch", event -> {
                count.incrementAndGet();
                units.addAndGet(event.getInt("units"));
            });

            stream.start();
        }

        System.out.printf("count=%d totalUnits=%d%n",
                count.get(), units.get());
    }
}
```

Biên dịch và chạy:

```bash
javac ReadBatchWithCallbacks.java
java ReadBatchWithCallbacks
```

**Stdout:**

```text
count=5 totalUnits=150
```

Ở đây `start()` xử lý file đến hết trước khi chương trình in tổng. API callback trông giống live consumer, nhưng đây vẫn là **offline file consumer**. Nếu file không tồn tại hoặc định dạng không hỗ trợ, chương trình có thể báo `IOException`. Chỉ mở recording từ nguồn đáng tin và kiểm tra quyền đọc.

## 9. Nếu muốn nghe event của một recording có sẵn mà không bật recording mới

Một ví dụ **passive** đọc repository của JVM hiện tại; đoạn sau là chương trình đầy đủ nhưng cần **có recording JFR khác đang bật `jdk.CPULoad`** thì mới nhận event.

Tạo `PassiveCpuListener.java`:

```java
import java.time.Duration;
import jdk.jfr.consumer.EventStream;

public final class PassiveCpuListener {
    public static void main(String[] args) throws Exception {
        try (EventStream stream = EventStream.openRepository()) {
            stream.onEvent("jdk.CPULoad", event -> {
                float cpu = event.getFloat("machineTotal");
                System.out.printf("machineCpu=%.1f%%%n", cpu * 100.0);
            });

            stream.startAsync();
            Thread.sleep(Duration.ofSeconds(10).toMillis());
        }
    }
}
```

Biên dịch và chạy với recording đã được bật từ command line:

```bash
javac PassiveCpuListener.java
java -XX:StartFlightRecording=filename=passive.jfr,settings=default,dumponexit=true PassiveCpuListener
```

**Output:** có thể có những dòng `machineCpu=...%`, nhưng số lượng và giá trị không cố định, vì JFR event settings và flush timing phụ thuộc môi trường. `-XX:StartFlightRecording` ở lệnh chạy tạo **recording bởi launcher/JVM**, còn `EventStream.openRepository()` chỉ nghe thụ động. Nếu bỏ tùy chọn ghi recording mà không có nguồn ghi nào khác, không nên mong `onEvent` được gọi.

`EventStream.openRepository(Path)` nhận đường dẫn **repository JFR**, **không phải đường dẫn của một tệp `.jfr` bất kỳ**. Để đọc file đã lưu, phải dùng `openFile(Path)` hoặc `RecordingFile(Path)`. Không nên tự ý mở repository của JVM khác nếu không xác minh quyền, định dạng và tính tin cậy.

## 10. Chọn phương án theo mục đích

| Nhu cầu | Hướng ưu tiên | Lý do |
| --- | --- | --- |
| Theo dõi GC pause hoặc CPU event để điều chỉnh hành vi khi JVM đang chạy | `RecordingStream` hoặc consumer stream phù hợp. | Có thể phát hiện khi batch mới tới; cần kiểm soát lag và tác động callback. |
| Có sẵn recording do `jcmd JFR.start`/ứng dụng tạo; chỉ muốn nghe mà không bật cấu hình thu khác | `EventStream.openRepository()` khi cùng JVM và repository hợp lệ. | Consumer thụ động, nguồn quyết định event nào được ghi. |
| Phân tích incident sau khi process đã chết | `RecordingFile`, `EventStream.openFile` hoặc JMC. | Dữ liệu lưu trữ vẫn có thể phân tích nhiều lần; dễ giữ bằng chứng và so sánh. |
| Tổng hợp một file rất lớn mà heap máy phân tích có hạn | `RecordingFile` đọc từng event hoặc file event stream. | Giảm nhu cầu giữ toàn bộ event trong một List. |
| Dashboard cần gửi số liệu ra service khác | Stream + aggregate/batch + bounded queue. | Giảm I/O trên mỗi event, nhưng cần backpressure policy và giám sát lag. |
| Cần báo cáo tái lập, audit, kiểm tra sau sự cố | Tệp `.jfr` đã lưu kèm version, settings, thời gian, checksum. | Có snapshot cố định cho nhiều người phân tích; không phụ thuộc stream từng chạy được bao lâu. |
| Cần event bus giao hàng bền vững, ACK, retry từng sự kiện nghiệp vụ | Hệ thống message/log được thiết kế cho nghiệp vụ. | JFR streaming không thay hàng đợi đảm bảo giao hàng chính xác. |

Một thiết kế thực tế thường **kết hợp cả hai**: streaming trích vài tín hiệu nhẹ để cảnh báo sớm; khi phát hiện bất thường, tạo hoặc lưu file `.jfr` có retention đủ dài, sau đó phân tích offline chi tiết bằng JMC/`jfr`/API. Nếu không có recording hoặc sự kiện mục tiêu bị tắt từ đầu, không thể “tạo lại” toàn bộ lịch sử event chỉ bằng cách mở stream.

## 11. Đánh giá chi phí bằng phép thử có đối chứng

Không quyết định “stream nhanh hơn file” chỉ qua cảm giác. Với cùng ứng dụng, cùng workload, cùng JDK và cùng loại event, nên so những cấu hình:

1. **Baseline:** không bật event mục tiêu, đo throughput, p95/p99 latency, CPU, heap/GC, RSS và disk I/O.
2. **Recording-only:** bật JFR tương đương nhưng không chạy ứng dụng consumer tự viết. Phần chênh so baseline chủ yếu phản ánh chi phí capture/chunk/storage.
3. **Streaming lightweight:** thêm consumer chỉ đọc vài field, cộng counters rồi flush theo batch; đo delivery lag p50/p95/p99 và tốc độ xử lý.
4. **Streaming with real sink:** thêm queue và đường xuất metrics thật; đo queue depth, rejected/dropped/coalesced count, downstream latency.
5. **Offline read:** lưu cùng recording và xử lý bằng `RecordingFile` trong một JVM riêng; đo thời gian đọc, events/s, peak heap và I/O của **consumer**.

Giữ workload đủ lâu để hết warm-up/JIT và có event rate đại diện; chạy nhiều lần để kiểm tra biến động. Không so tệp 1 GB với stream có event filter khác hoặc timestamp window khác. Ghi chính xác event settings, threshold, period, stacktrace, sampling và retention.

Các thước đo nên báo cáo:

| Thước đo | Công dụng | Lưu ý |
| --- | --- | --- |
| Event rate quan sát được (events/s) | Tải consumer thực nhận. | Không nhất thiết bằng tổng event xảy ra trong ứng dụng; JFR có sampling/threshold. |
| Delivery lag p50/p95/p99 | Độ trễ từ event end tới callback. | Không suy ra từ duration field; cần đồng hồ phù hợp. |
| Consumer processing time | CPU/wall time cho callback/aggregate/sink. | Có thể đo bằng `nanoTime()` trong cùng thread. |
| Queue depth, queue drop count | Cho biết hệ thống có xử lý kịp hay không. | Phải có bounded queue và metric khi đầy. |
| Heap allocation/GC của consumer | Phát hiện callback tạo quá nhiều object. | `setReuse(false)` và parse/log payload có thể tăng allocation. |
| Disk IO, repository size, file size | Hiểu chi phí capture và retention. | `setMaxAge/Size` không phải SLA không mất event. |
| Total file read time, events/s offline | Đánh giá throughput xử lý file sau sự cố. | Không phải end-to-end alert latency. |

### Khi callback trở thành nút cổ chai

Nếu JVM tạo trung bình **5.000 event/s** và callback mất trung bình **1 ms/event** trên một thread xử lý tuần tự, năng lực lý tưởng của thread chỉ khoảng **1.000 event/s** (chưa tính overhead). Hệ thống có thể tụt lại ~**4.000 event/s** nếu tốc độ duy trì — phép tính chỉ là mô hình đơn giản, không dự đoán chính xác hành vi JFR hay số event mất. Muốn cải thiện, thường cần **ít event hơn và thao tác mỗi event rẻ hơn**; không phải cứ tăng heap là xong.

Không đẩy công việc nặng sang một executor không giới hạn queue. Khi callback rất nhanh nhưng hàng đợi tăng mãi, độ trễ end-to-end vẫn tăng và JVM có thể bị OOM do chính consumer. Dùng bounded queue và tổng hợp trong RAM có giới hạn.

## 12. Những lỗi phổ biến

- **“`RecordingStream` gọi callback ngay khi `Event.commit()` chạy.”** Sai: JFR giao theo batch/flush và thread consumer riêng trong chế độ asynchronous.
- **“Có `onEvent` nghĩa là đang đọc live.”** Sai: `EventStream.openFile` cũng có callback nhưng đọc file đã có.
- **“`EventStream.openRepository()` tự bật những event tôi muốn.”** Sai: cần recording/source được cấu hình bên ngoài.
- **“`startAsync()` xong là main có thể exit ngay.”** Sai: phải giữ stream còn sống để các batch được giao.
- **“`close()` đảm bảo mọi event đã được xử lý.”** Sai: close không phải drain/ack guarantee.
- **“Gọi `setMaxSize` giúp consumer bắt kịp producer.”** Sai: đó là giới hạn retention, không phải cơ chế tăng thông lượng callback.
- **“`RecordedEvent` luôn an toàn để lưu reference vào queue.”** Sai: object có thể bị reuse; copy field hoặc đặt `setReuse(false)` khi cần.
- **“`setOrdered(true)` bảo đảm mọi event từ đầu đến cuối luôn đúng timeline.”** Sai: thứ tự được giữ trong batch, không bảo đảm giữa mọi batch.
- **“`RecordingFile.readAllEvents` tốt nhất cho mọi file.”** Sai: với file lớn nó có thể dùng quá nhiều heap.
- **“File reading có callback nên latency bằng live streaming.”** Sai: file dump/transfer có thể trì hoãn việc phân tích.
- **“Không nhận event nghĩa là hệ thống không tạo event.”** Sai: xem settings, threshold, sampling, flush, window, filter và nguồn recording.
- **“JFR là message bus exactly-once cho nghiệp vụ.”** Sai: thiết kế quan sát/chẩn đoán, không có cùng hợp đồng giao hàng, retry và checkpoint như hệ thống event nghiệp vụ.
- **“In từng event gần như miễn phí.”** Sai: format string/stack trace, console/file I/O và lock contention có thể nặng hơn phần thu JFR.
- **“Consumer chạy trên máy khác luôn không ảnh hưởng JVM nguồn.”** Không hẳn: đọc một file đã xuất ít ảnh hưởng sau khi ghi, nhưng remote live streaming có thể bổ sung serialization/network/CPU, và việc bật thêm recording/event vẫn có chi phí.

## 13. Checklist thiết kế consumer JFR

- [ ] Xác định đúng nguồn: `RecordingStream`, repository live, `EventStream.openFile` hay `RecordingFile`.
- [ ] Event type đã được enable với threshold/period/stack trace phù hợp; không coi view rỗng là không có hoạt động.
- [ ] Cửa sổ thời gian và yêu cầu latency rõ ràng; đo `event end → callback → hành động cuối` thay vì chỉ đếm events.
- [ ] Callback đủ nhẹ; hạn chế console, đồng bộ I/O, JSON serialize và query DB cho từng event.
- [ ] Có giới hạn bộ nhớ/queue/retention; đo lag, throughput, loss/drop và có quy tắc khi quá tải.
- [ ] Không giữ `RecordedEvent` sau callback khi reuse có thể xảy ra; copy dữ liệu cần dùng.
- [ ] Hiểu batch/flush, thứ tự event, xử lý lỗi, lifecycle start/close và trường hợp dừng không drain.
- [ ] Với phân tích offline, không dùng `readAllEvents` trên file lớn; lưu recording và metadata để tái hiện.
- [ ] So sánh overhead bằng cùng workload, settings và JDK; tách producer cost khỏi consumer cost.
- [ ] Kiểm soát quyền truy cập file/repository/remote stream; JFR có thể chứa tên class, đường dẫn file, tham số, lỗi, stacktrace và dữ liệu nhạy cảm trong custom events.

**Điểm cần nhớ:** JFR streaming giúp **quan sát liên tục với độ trễ do flush/buffering/scheduling quyết định**, phù hợp cảnh báo và số liệu nhẹ. Đọc file giúp **phân tích lại một recording cố định**, phù hợp điều tra sâu và kiểm chứng hậu sự cố. Trong cả hai hướng, mức chi phí thực tế chủ yếu do **event settings, số lượng event, cách consumer parse/aggregate và thao tác I/O**. Một consumer tốt đo lag rõ ràng, xử lý callback nhẹ, có giới hạn tài nguyên và không nhầm JFR với hàng đợi giao hàng sự kiện nghiệp vụ.

### Tài liệu tham khảo chính thức

- [Oracle JDK 17 — RecordingStream](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html)
- [Oracle JDK 17 — EventStream](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html)
- [Oracle JDK 17 — RecordingFile](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [Oracle JDK 17 — Recording](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349)
- [Inside Java — JFR Event Stream (API và chi phí consumer)](https://inside.java/2022/05/12/sip49/)