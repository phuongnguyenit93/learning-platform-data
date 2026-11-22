# 16.10. Thiết kế consumer không làm nghẽn hệ thống và quản lý thay đổi schema event

Java Flight Recorder (JFR) vừa là nguồn dữ liệu chẩn đoán JVM, vừa có API để mã Java đọc sự kiện trực tiếp hoặc từ file `.jfr`. Một consumer tưởng như đơn giản — đăng ký `onEvent` rồi gửi mỗi event sang database/HTTP — có thể trở thành điểm nghẽn: exporter chậm, callback bị giữ, dữ liệu tồn đọng và JVM phải tốn thêm CPU, bộ nhớ, I/O. Một rủi ro khác là event producer đổi tên field, kiểu dữ liệu hoặc đơn vị đo khiến consumer cũ ném ngoại lệ, đọc nhầm giá trị hay ngừng hoạt động.

Bài học tập trung vào **hai trách nhiệm thiết kế**:

1. **Không làm nghẽn hệ thống:** callback JFR chỉ thực hiện công việc ngắn, có giới hạn; luồng xử lý nặng được tách ra bằng hàng đợi hữu hạn với chính sách quá tải rõ ràng.
2. **Chịu được schema thay đổi:** nhận diện event type theo tên ổn định, đọc field có kiểm tra, xử lý phiên bản cũ/mới và giám sát schema không tương thích.

Các API chính thuộc module `jdk.jfr`, package `jdk.jfr.consumer`, khả dụng trên JDK 17+ (các API riêng cần xem `Since`). Đây là kiến thức thiết kế consumer; cấu hình JFR, kích thước queue và nhu cầu mất dữ liệu phải được xác định theo SLA thực tế, không dùng một con số mặc định cho mọi dịch vụ.

## 1. Consumer JFR thực sự chạy ở đâu?

Có ba kiểu đọc thường gặp:

| API | Phạm vi | Cách chạy |
| --- | --- | --- |
| `RecordingStream` | Tạo recording và tiêu thụ event của **JVM hiện tại** | Đăng ký callback rồi `start()` hoặc `startAsync()` |
| `EventStream.openRepository(...)` | Đọc event từ repository của JVM hoặc đường dẫn repository được chỉ định | Theo dõi stream/chunk dữ liệu từ nguồn đã tồn tại |
| `EventStream.openFile(Path)` / `RecordingFile` | Đọc recording file `.jfr` có sẵn | Dùng cho kiểm thử, phân tích offline, xử lý lại file có thời hạn |

**`startAsync()` không tạo một worker cho mỗi callback.** Theo API JDK 21, callback của `RecordingStream` được thực thi trong **một luồng xử lý riêng của stream**. Nếu callback chờ mạng, làm truy vấn DB, ghi log đồng bộ hoặc chạy phép tổng hợp nặng, nó vẫn kéo dài thời gian stream xử lý batch tiếp theo. Với `start()`, chính luồng gọi sẽ xử lý đến khi stream kết thúc. Mô hình bất đồng bộ chỉ chuyển nơi chạy callback; nó không tự cung cấp hàng đợi downstream, retry hay backpressure.

`onEvent("fully.qualified.EventName", action)` nhận đúng một loại event, thường hiệu quả hơn `onEvent(action)` rồi lọc thủ công mọi event. `onFlush(Runnable)` được gọi sau khi một batch đã được xử lý, phù hợp cho snapshot counter/batch aggregate nhỏ; cũng **không nên** thực hiện network I/O kéo dài ngay trong callback flush. `onError` và `onClose` giúp quan sát lỗi và vòng đời stream, nhưng không thay thế cơ chế quản trị tài nguyên của ứng dụng.

## 2. Kiến trúc consumer có hàng đợi hữu hạn

Luồng khuyến nghị:

~~~text
JFR repository / RecordingStream
          |
          v
onEvent callback (đọc field -> validate -> copy dữ liệu nhỏ)
          |
          +-- invalid schema? -> tăng counter, cảnh báo gộp
          |
          v
non-blocking queue.offer(snapshot)   [bounded N]
          |                |
          | success        +-- full -> policy: drop/coalesce/sample/durable fallback
          v
worker/exporter riêng
          |
          +-- aggregate / batch / timeout / retry có giới hạn
          v
metrics / storage / external sink

Các metrics riêng: received, accepted, dropped, invalid,
queue depth, processing lag, export errors, end-to-end latency.
~~~

Cần phân biệt **ba vùng đệm**:

- **Bộ nhớ/buffer và disk repository do JFR quản lý**: `RecordingStream.setMaxAge(Duration)` và `setMaxSize(long)` giới hạn lịch sử recording được lưu; chúng **không giới hạn** số phần tử của queue do ứng dụng tự tạo.
- **Hàng đợi trong JVM của consumer**: ví dụ `ArrayBlockingQueue<Snapshot>` kích thước 128 hoặc 1.024. Chính ứng dụng quản lý dung lượng, chính sách đầy queue và luồng worker.
- **Buffer/batch ở exporter hoặc hệ thống đích**: HTTP client, message broker, database, telemetry agent… có timeout, retry và độ trễ riêng. Có queue hữu hạn ở tầng thứ hai **không bảo đảm** tầng thứ ba đã hữu hạn.

Không bao giờ dùng một `ArrayList<RecordedEvent>` tăng vô hạn để “xử lý sau”. Đối với ứng dụng chẩn đoán chạy dài, đó chính là cách tạo memory leak thứ cấp ngay trong hệ thống quan sát.

## 3. Quy tắc vàng cho `onEvent`: copy nhanh, trả về nhanh

Một callback tốt làm tối thiểu:

1. Xác định event type mong đợi.
2. Kiểm tra field có tồn tại và giá trị có đúng kiểu.
3. Sao chép các field **cần thiết** thành snapshot nhỏ, bất biến hoặc immutable; giới hạn độ dài `String`/stack/JSON, tránh giữ payload nhạy cảm.
4. Gọi `queue.offer(snapshot)` (không chờ). Thành công thì tăng counter; đầy queue thì thực hiện chính sách quá tải đã quyết định.
5. Thoát callback.

Không đặt trong callback: `Thread.sleep`, HTTP synchronous call, truy vấn database, ghi file lớn, lock tranh chấp dài, JSON serialize hàng MB, tính thống kê O(n²), retry có vòng chờ hoặc `queue.put` khi queue có thể đầy.

### 3.1. Rủi ro `RecordedEvent` được tái sử dụng

`EventStream` ghi rõ **cùng một instance `RecordedEvent` có thể được tái sử dụng** cho nhiều event; không an toàn khi giữ tham chiếu đó sau khi callback trả về nếu reuse đang bật. Ví dụ **sai**:

~~~java
// Minh họa anti-pattern, không phải chương trình độc lập:
stream.onEvent("lab.OrderEvent", event -> queue.offer(event));
~~~

Worker có thể đọc object đã được stream dùng lại, làm giá trị thay đổi hoặc gắn nhầm dữ liệu giữa các event. Hai giải pháp:

- **Ưu tiên:** trong callback tạo snapshot chỉ gồm scalar/`String` đã giới hạn/`Instant` (immutable) rồi enqueue snapshot. Khi đó có thể dùng `stream.setReuse(true)` để tiết kiệm allocation phía stream.
- **Khi thật sự cần giữ nguyên toàn event:** `stream.setReuse(false)` yêu cầu cấp phát object event mới. Cách này tăng allocation và **vẫn không giải quyết queue vô hạn**. Cũng cần xét retained graph của các nested objects nếu muốn lưu lâu.

Đừng giả định ghi sự kiện JFR đến callback ngay lập tức theo thời gian thực tuyệt đối. Event được giao theo **batch**, có độ trễ từ flush/chunk và giới hạn ordering. Khi `setOrdered(false)` để giảm công đoạn sắp xếp, mọi thuật toán phía sau phải xử lý out-of-order bằng timestamp hoặc ID phù hợp.

## 4. Chính sách khi producer nhanh hơn consumer

Một hệ thống hữu hạn phải chấp nhận **một trong ba lựa chọn**: giảm tải, mất bớt event, hoặc ghi tạm sang nơi bền vững có giới hạn. Không thể hứa “không mất event, không chặn, không cần lưu trữ bổ sung” khi tốc độ event lớn hơn khả năng xuất dữ liệu trong thời gian dài.

| Chính sách | Cách làm | Phù hợp | Đổi lại |
| --- | --- | --- | --- |
| **Drop newest** | `offer` trả `false` thì bỏ snapshot mới | Telemetry sampling, CPU/memory metrics có thể mất mẫu | Mất tín hiệu của những đỉnh tải; phải đếm dropped |
| **Drop oldest** | Bỏ phần tử cũ rồi thử nhận mẫu mới | Dashboard ưu tiên trạng thái gần đây | Phá lịch sử, có race nếu nhiều worker; cần đồng bộ chính sách |
| **Coalesce/aggregate** | Gộp theo (event type, class, time window) | Counter/histogram/throughput | Không giữ từng event và stack trace cá thể |
| **Sample có điều chỉnh** | Giảm tần suất hoặc chọn subset | Event volume rất cao | Có sai số, không thể phục hồi event bị bỏ |
| **Durable spool/replay** | Ghi file/chunk/queue bền vững có quota, worker đọc lại | Sự kiện cần bảo toàn cao | Tốn I/O, có áp lực disk, cần replay/dedupe và xử lý hỏng dữ liệu |
| **Block producer** | `put` hoặc retry vô hạn tại callback | Thường **không phù hợp** với consumer JFR live | Stream bị chậm, tăng lag/áp lực repository, có thể ảnh hưởng workload |

**Chọn theo độ quan trọng của event.** Với metrics sampled, cho phép drop có quan sát là lựa chọn thường gặp. Với audit/transaction bắt buộc không mất, **JFR streaming không nên là kênh lưu trữ duy nhất**; event nghiệp vụ quan trọng cần đi qua hệ thống có durability/acknowledgement phù hợp. JFR là kênh chẩn đoán, không mang hợp đồng exactly-once delivery.

### 4.1. Ước lượng queue và ngân sách bộ nhớ

Giả sử đỉnh đến là 10.000 event/s, worker xử lý được 8.000 event/s trong 5 giây. Backlog tăng xấp xỉ (10.000 − 8.000) × 5 = **10.000 snapshot**. Queue có 1.000 slot sẽ nhanh chóng đầy. Nếu mỗi snapshot thực tế chiếm trung bình 200 byte (gồm object overhead, reference và nội dung), 10.000 snapshot khoảng 2 MiB; nhưng 200 byte chỉ là **giả định** và có thể tăng nhiều nếu sao chép stack trace hoặc chuỗi dài.

Do đó, hãy:

- Đo **kích thước thực tế snapshot** và hạn chế string/payload/stack.
- Dùng queue capacity, số worker, batch size, timeout và retry budget cố định.
- Giám sát `queue.size()/capacity`, `dropped / received` và thời gian chờ từ capture tới xử lý.
- Thử tải cao hơn mức downstream chịu được, giả lập exporter timeout, disk đầy và shutdown giữa chừng.
- Ưu tiên **giảm dữ liệu ngay tại nguồn** (chỉ enable event có ích, tăng threshold, tắt stack trace khi không cần, dùng event filters) trước khi tăng vô hạn queue.

## 5. Ví dụ Java 17+: RecordingStream + queue hữu hạn + worker riêng

Đây là **chương trình đầy đủ** chạy trong một JVM, tạo custom JFR event `lab.OrderEvent`, đăng ký callback, chuyển **bản sao scalar** vào `ArrayBlockingQueue` hữu hạn, rồi cho worker xử lý chậm có chủ đích. Callback **không chờ** worker; nếu queue đầy, chương trình đếm `dropped`. Một file `.jfr` được tạo để dùng cho ví dụ schema ở phần sau.

Lưu vào **`BoundedJfrConsumerDemo.java`**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.LongAdder;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public final class BoundedJfrConsumerDemo {
    @Name("lab.OrderEvent")
    public static final class OrderEvent extends Event {
        public long orderId;
        public long elapsedMillis;
        public String source;
    }

    private record Snapshot(long id, long durationMillis,
                            String source, Instant timestamp) { }

    public static void main(String[] args) throws Exception {
        var queue = new ArrayBlockingQueue<Snapshot>(128);
        var workerRunning = new AtomicBoolean(true);
        var accepted = new LongAdder();
        var dropped = new LongAdder();
        var invalid = new LongAdder();
        var processed = new LongAdder();
        var streamErrors = new LongAdder();
        var flushes = new LongAdder();

        Thread worker = new Thread(() -> {
            try {
                while (workerRunning.get() || !queue.isEmpty()) {
                    Snapshot value = queue.poll(100, TimeUnit.MILLISECONDS);
                    if (value != null) {
                        // Chỗ giả lập downstream chậm: nằm NGOÀI onEvent.
                        Thread.sleep(2);
                        processed.increment();
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "jfr-exporter");
        worker.start();

        Path recording = Files.createTempFile("bounded-jfr-", ".jfr");
        try (RecordingStream stream = new RecordingStream()) {
            stream.enable(OrderEvent.class)
                  .withoutThreshold()
                  .withoutStackTrace();
            stream.setMaxAge(Duration.ofMinutes(2));
            stream.setMaxSize(32L * 1024 * 1024);
            stream.setOrdered(false); // Consumer không cần thứ tự tuyệt đối.
            stream.setReuse(true);    // KHÔNG giữ RecordedEvent sau callback.
            stream.onFlush(flushes::increment);
            stream.onError(error -> streamErrors.increment());

            stream.onEvent("lab.OrderEvent", event -> {
                if (!event.hasField("orderId")
                        || !event.hasField("elapsedMillis")) {
                    invalid.increment();
                    return;
                }

                Object rawId = event.getValue("orderId");
                Object rawDuration = event.getValue("elapsedMillis");
                if (!(rawId instanceof Number id)
                        || !(rawDuration instanceof Number duration)) {
                    invalid.increment();
                    return;
                }

                String source = "unknown";
                if (event.hasField("source")) {
                    Object raw = event.getValue("source");
                    if (raw instanceof String s) {
                        source = s.substring(0, Math.min(32, s.length()));
                    }
                }

                Snapshot copy = new Snapshot(id.longValue(),
                        duration.longValue(), source, event.getStartTime());
                if (queue.offer(copy)) {
                    accepted.increment();
                } else {
                    dropped.increment();
                }
            });

            stream.startAsync();
            for (long i = 1; i <= 4000; i++) {
                OrderEvent event = new OrderEvent();
                event.orderId = i;
                event.elapsedMillis = i % 20;
                event.source = "training";
                event.commit();
            }

            // Cho stream cơ hội flush; đây KHÔNG là cam kết đủ 4000 callback.
            Thread.sleep(2500L);
            stream.dump(recording);
            stream.close();
            stream.awaitTermination(Duration.ofSeconds(3));
        } finally {
            workerRunning.set(false);
            worker.join();
        }

        System.out.println("Produced=4000");
        System.out.println("Accepted=" + accepted.sum());
        System.out.println("Dropped=" + dropped.sum());
        System.out.println("Invalid=" + invalid.sum());
        System.out.println("Processed=" + processed.sum());
        System.out.println("Stream errors=" + streamErrors.sum());
        System.out.println("Flushes=" + flushes.sum());
        System.out.println("JFR file=" + recording.toAbsolutePath());
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ có hỗ trợ JFR:

~~~bash
javac BoundedJfrConsumerDemo.java
java BoundedJfrConsumerDemo
~~~

Đầu ra **chắc chắn về cấu trúc** gồm các nhãn `Produced=4000`, `Accepted=...`, `Dropped=...`, `Invalid=...`, `Processed=...`, `Stream errors=...`, `Flushes=...`, `JFR file=...`. File đầu ra có đường dẫn tạm khác nhau mỗi lần chạy; số event được consumer nhận **không cố định** vì delivery/flush/CPU/OS scheduling. `Accepted + Dropped` đếm các **event mà callback thực sự nhận**, **không nhất thiết bằng 4.000 event được producer gọi `commit()`** trong ví dụ ngắn này. `Processed` không thể lớn hơn `Accepted` trong chạy bình thường.

Để kiểm tra file sinh ra, dùng đường dẫn thực tế sau `JFR file=`:

~~~bash
jfr summary /path/to/bounded-jfr-example.jfr
jfr print --events lab.OrderEvent /path/to/bounded-jfr-example.jfr
~~~

`/path/to/bounded-jfr-example.jfr` chỉ là **ký hiệu thay thế**, không phải đường dẫn file được chương trình tự tạo. Không chạy nguyên lệnh đó khi chưa thay bằng đường dẫn đã in ra.

Đặc điểm của ví dụ:

- `queue.offer` trả ngay và bị giới hạn ở 128 phần tử; tuyệt đối không gọi `put` trong callback.
- `setReuse(true)` an toàn vì mọi giá trị cần dùng đã chuyển sang record `Snapshot`; không đưa `RecordedEvent` vào queue.
- `setMaxAge` và `setMaxSize` quản lý dữ liệu **JFR recording**, không giới hạn queue. Queue 128 nằm riêng ở `ArrayBlockingQueue`.
- Worker đang mô phỏng exporter, nên **không có I/O từ callback**. Với exporter thật cần batch/timeout/retry có giới hạn.
- Ví dụ đóng stream sau một khoảng chờ và cho worker drain queue. Việc `close()` không đồng nghĩa với cam kết mọi event ở JVM đã đi qua callback; ở môi trường yêu cầu bảo toàn phải có luồng durable/replay riêng.

**Không dùng demo này làm cơ sở suy ra tốc độ xử lý tối đa thực tế:** kích thước event, JIT warm-up, cơ chế chunk flush và tốc độ máy ảnh hưởng lớn. Nó dùng để thấy rõ ranh giới callback → queue → worker.

## 6. Backpressure là bài toán cả chuỗi, không chỉ một ArrayBlockingQueue

### 6.1. Định nghĩa rõ SLO và khi quá tải

Ví dụ consumer chỉ cung cấp telemetry có thể đặt các mục tiêu vận hành **minh họa**:

- `drop_ratio` trong tải bình thường gần 0, nhưng khi downstream outage chấp nhận cảnh báo và mất mẫu.
- Queue occupancy thường thấp hơn mức báo động, exporter lag đo bằng timestamp khi snapshot được nhận/được xử lý.
- Exporter call có timeout hữu hạn và circuit breaker; retry có backoff nhưng **không kéo dài vô hạn**.
- Sau khi quay về tải bình thường, backlog giảm mà memory không tăng không kiểm soát.

Đây không phải SLO bắt buộc của JFR. Người sở hữu dịch vụ phải định nghĩa ngưỡng từ yêu cầu điều tra và tài nguyên máy. Nếu một metric không được đo, đừng tuyên bố consumer “non-blocking” chỉ vì code có `startAsync`.

### 6.2. Metrics cần quan sát

| Metric | Ý nghĩa | Hành động khi bất thường |
| --- | --- | --- |
| `events_received_total` | Event đi vào callback theo từng loại | So với lưu lượng/recording config |
| `events_accepted_total` | Event được enqueue thành công | Phát hiện converter/validation bỏ sót |
| `events_dropped_total` | Event mất do queue đầy theo policy | Giảm event volume, sửa exporter, tăng capacity có kiểm chứng |
| `events_invalid_total` | Event sai/mất field/khác kiểu | Kiểm tra schema drift và phiên bản nguồn |
| `queue_depth` / `queue_capacity` | Backlog và giới hạn | Cảnh báo sớm, tránh full queue kéo dài |
| `export_errors_total` | Timeout/failed batch trong worker | Điều tra sink, retry/circuit breaker |
| `processing_lag_seconds` | Thời gian từ event timestamp/callback đến xử lý | Phân biệt producer chậm hay exporter nghẽn |
| `stream_error_total` / `stream_restarts` | Lỗi trong callback/JFR stream | Bảo vệ consumer và chạy lại có kiểm soát |
| `recording_disk_bytes` | Dữ liệu JFR retained trong repository | Kiểm tra `setMaxAge`, `setMaxSize` và disk |

Lưu ý **thời gian event** và **thời gian nhận callback** khác nhau. Để đo lag xử lý callback→worker, có thể thêm `System.nanoTime()` ngay khi tạo snapshot và trừ khi worker xử lý (chỉ so thời gian trong cùng tiến trình); để đo end-to-end event→sink, dùng timestamp event nhưng chú ý clock sync nếu qua nhiều máy.

### 6.3. Ordering và trùng dữ liệu

Theo API `EventStream`, event đến theo batch; thứ tự trong một batch có thể được sắp xếp theo end time, nhưng **không có bảo đảm thứ tự toàn cục tuyệt đối giữa các batch**. `setOrdered(false)` có thể giảm overhead nhưng downstream phải tự xử lý timestamp và out-of-order nếu có yêu cầu logic theo thời gian.

Không xây dựng quyết định nghiệp vụ không thể đảo ngược dựa trên giả định JFR event được giao **exactly once**, theo ID tuần tự hoặc luôn không có lặp khi đọc lại file. Nếu cần idempotency cho exporter, thiết kế khóa dedupe với phạm vi/TTL rõ ràng và kiểm tra khả năng trùng khi replay. Đừng dùng `EventType.getId()` như định danh event type vĩnh viễn qua các JVM và file.

## 7. Schema event JFR thay đổi theo những cách nào?

Trong JFR, **event type** có tên định danh (ví dụ `lab.OrderEvent`), metadata các field (tên, kiểu, annotation/đơn vị) và ID nội bộ của JVM. `@Name` trên custom `Event` đặt tên máy đọc; `@Label` phục vụ hiển thị. **Consumer nên ghép theo event type name đã được thỏa thuận**, đồng thời kiểm tra shape/semantics của field, thay vì phụ thuộc label hiển thị hoặc một numeric ID giữa nhiều runtime.

| Thay đổi producer | Consumer cũ có thể gặp gì? | Hướng tương thích |
| --- | --- | --- |
| Thêm field tùy chọn `region` | Consumer cũ vẫn đọc các field cũ | Bỏ qua field lạ; consumer mới dùng fallback |
| Bỏ field `elapsedMillis` | `getLong("elapsedMillis")` có thể ném lỗi vì field thiếu | `hasField` trước; đánh dấu thiếu và báo metric |
| Đổi kiểu `long` sang `String` | Getter typed ném `IllegalArgumentException` | Kiểm tra metadata/`getValue` + `instanceof`; không parse bừa |
| Đổi đơn vị từ milli sang nano | Trường vẫn là số nhưng mang nghĩa khác; nguy cơ sai số 10⁶ lần | Đặt tên mới (ví dụ `durationNanos`), convert có kiểm tra |
| Đổi ý nghĩa field mà giữ tên | Lỗi logic **không được phát hiện tự động** | Tạo event version mới hoặc hợp đồng schema version rõ ràng |
| Đổi hẳn event type name | Callback đăng ký tên cũ không còn nhận event | Có giai đoạn dual-publish hoặc đăng ký cả old/new names |
| Class unload/load lại, thay metadata giữa các chunks | Cùng tên/ID trong ngữ cảnh khác có shape khác | Xử lý metadata theo phiên/chunk; không cache schema vô hạn theo name |

Hai chiến lược versioning:

**Tương thích tiến hóa nhẹ:** giữ `@Name("lab.OrderEvent")`, giữ nghĩa/kiểu các field hiện có; thêm field mới có thể vắng mặt ở file cũ. Consumer mới `hasField("region") ? ... : "unknown"`. Với chuỗi event một phiên, metadata vẫn là nguồn sự thật của từng event, không phải tài liệu mô tả cố định.

**Thay đổi phá vỡ hợp đồng:** tạo `@Name("lab.OrderEventV2")` và field có tên, kiểu, đơn vị rõ (`durationNanos`) thay vì âm thầm thay nghĩa `elapsedMillis`. Trong giai đoạn chuyển tiếp, consumer có thể nghe hai tên rồi chuẩn hóa về cùng record nội bộ; ngừng hỗ trợ v1 khi đã xác minh không còn file/producer cũ cần đọc.

### 7.1. Kiểm tra field đúng cách

`RecordedEvent` có `hasField(String)` và `getValue(String)`; `EventType` có `getField(String)`, `getFields()` để kiểm tra metadata. `getValue` trả về object có thể là primitive wrapper hoặc một đối tượng JFR chuyên biệt; getter như `getLong`, `getString`, `getDuration` chỉ thích hợp **khi field tồn tại và có kiểu/annotation đúng**. `hasField` bảo vệ được trường hợp field thiếu, nhưng không thay phép kiểm tra kiểu.

~~~java
// Minh họa riêng, không phải chương trình độc lập:
Object raw = event.hasField("durationNanos")
        ? event.getValue("durationNanos")
        : null;
if (raw instanceof Number number) {
    long nanos = number.longValue();
    // Chỉ chuyển sang milliseconds khi nanos >= 0 và đúng semantics.
}
~~~

Đọc dữ liệu schema như một **hợp đồng dữ liệu có phiên bản**:

- Tên event, field, kiểu, đơn vị và ý nghĩa nghiệp vụ phải được định nghĩa rõ.
- Field mới **có thể vắng mặt** trong file cũ; giá trị null cũng khác “field không tồn tại”.
- Khi cần bắt buộc dữ liệu, không âm thầm dùng 0 nếu mất field: điều đó có thể tạo báo cáo sai. Hãy đếm `invalid_schema`, ghi tên type/version và xử lý theo policy.
- Đọc các file `.jfr` của nhiều JDK/vendor có thể có các event hệ thống và field khác nhau; không hard-code danh sách JFR built-in fields như hợp đồng vĩnh viễn.
- Không coi việc có thêm annotation/label là thay đổi bắt buộc về semantics; giữ bộ kiểm thử contract tương ứng.

## 8. `onMetadata`: phát hiện thay đổi event types khi đang tiêu thụ

`EventStream.onMetadata(Consumer<MetadataEvent>)` có từ JDK 16. Đăng ký **trước khi `start()`/`startAsync()`**. Event metadata cho biết:

- `getEventTypes()`: danh sách event types đang được sử dụng.
- `getAddedEventTypes()`: types xuất hiện từ metadata event trước; ở metadata đầu tiên thường là toàn bộ types hiện biết.
- `getRemovedEventTypes()`: types bị loại từ lần metadata trước.
- `getConfigurations()`: các cấu hình metadata liên quan.

Mỗi `EventType` cung cấp `getName()`, `getId()`, `getFields()`; mỗi `ValueDescriptor` có `getName()` và `getTypeName()`. Có thể tạo **schema signature** bằng cách chuẩn hóa danh sách (tên field, kiểu, đơn vị/annotation có liên quan), lưu theo event name và source version. Nếu metadata thay đổi, log một sự kiện tổng hợp và cảnh báo thay vì in metadata cho mọi event.

**Không thay `onMetadata` cho kiểm tra mỗi event:** metadata có thể thay đổi theo file/chunk, và một field có mặt nhưng giá trị null/khác kiểu. Consumer vẫn phải kiểm tra ở nơi đọc. Với event type không quan tâm, đăng ký callback theo tên cụ thể thay vì parse mọi event trong stream.

Đừng thực hiện I/O nặng trong `onMetadata`. Ví dụ bên dưới in ra schema nhỏ để người học quan sát; trong production có thể đưa schema signature qua queue/batch logging riêng.

## 9. Ví dụ Java 17+ đọc file cũ/mới và chuẩn hóa schema

Ví dụ thứ hai là chương trình **độc lập**. Nó mở file `.jfr` được tạo ở phần 5 hoặc file có custom event cùng contract. Consumer hỗ trợ:

- **v1:** `lab.OrderEvent` có `orderId` và `elapsedMillis`.
- **v2:** `lab.OrderEventV2` có `orderId` và `durationNanos`; có thể có `source`/`outcome` tùy chọn.

Nếu field duration vắng mặt/sai kiểu hoặc giá trị âm, chương trình đếm `invalid`, **không gán bừa duration=0**. Dữ liệu hợp lệ được chuyển về mili giây. Đây là ví dụ chuyển đổi cho contract đã biết, không phải bộ giải mã mọi loại event JFR.

Tạo file **`JfrSchemaCompatibleReader.java`**:

~~~java
import java.nio.file.Path;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collectors;
import jdk.jfr.consumer.EventStream;
import jdk.jfr.consumer.RecordedEvent;

public final class JfrSchemaCompatibleReader {
    private static final Set<String> SUPPORTED =
            Set.of("lab.OrderEvent", "lab.OrderEventV2");
    private static final LongAdder valid = new LongAdder();
    private static final LongAdder invalid = new LongAdder();
    private static final LongAdder totalMillis = new LongAdder();
    private static final LongAdder streamErrors = new LongAdder();

    private static Long number(RecordedEvent event, String field) {
        if (!event.hasField(field)) {
            return null;
        }
        Object raw = event.getValue(field);
        return raw instanceof Number n ? n.longValue() : null;
    }

    private static void consume(RecordedEvent event) {
        Long id = number(event, "orderId");
        Long millis;
        String typeName = event.getEventType().getName();

        if ("lab.OrderEventV2".equals(typeName)) {
            Long nanos = number(event, "durationNanos");
            millis = nanos == null || nanos < 0
                    ? null : TimeUnit.NANOSECONDS.toMillis(nanos);
        } else {
            millis = number(event, "elapsedMillis");
        }

        if (id == null || id < 0 || millis == null || millis < 0) {
            invalid.increment();
            return;
        }

        valid.increment();
        totalMillis.add(millis);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java JfrSchemaCompatibleReader <file.jfr>");
            return;
        }

        try (EventStream stream = EventStream.openFile(Path.of(args[0]))) {
            stream.setOrdered(false);

            stream.onMetadata(metadata -> metadata.getAddedEventTypes()
                .stream()
                .filter(type -> SUPPORTED.contains(type.getName()))
                .forEach(type -> {
                    String fields = type.getFields().stream()
                            .map(f -> f.getName() + ":" + f.getTypeName())
                            .collect(Collectors.joining(", "));
                    System.out.println("Schema " + type.getName()
                            + " {" + fields + "}");
                }));

            stream.onEvent("lab.OrderEvent",
                    JfrSchemaCompatibleReader::consume);
            stream.onEvent("lab.OrderEventV2",
                    JfrSchemaCompatibleReader::consume);
            stream.onError(error -> streamErrors.increment());

            // File hữu hạn: start() đọc đồng bộ đến cuối file.
            stream.start();
        }

        System.out.println("Valid=" + valid.sum());
        System.out.println("Invalid=" + invalid.sum());
        System.out.println("Total duration (ms)=" + totalMillis.sum());
        System.out.println("Stream errors=" + streamErrors.sum());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac JfrSchemaCompatibleReader.java
java JfrSchemaCompatibleReader /path/to/actual-recording.jfr
~~~

Thay `/path/to/actual-recording.jfr` bằng **đường dẫn mà `BoundedJfrConsumerDemo` in ra** hoặc đường dẫn file tương thích. Đầu ra gồm thông báo schema phát hiện và bốn counter; **số lượng và tổng duration phụ thuộc nội dung file**. Với file v1 tạo ở phần 5, chỉ type `lab.OrderEvent` có thể xuất hiện; `lab.OrderEventV2` không bắt buộc tồn tại. Nếu file không có hai loại event trên, `Valid=0` là một kết quả hợp lệ về phạm vi filter, **không phải bằng chứng chương trình chưa đọc file**.

### 9.1. Ví dụ producer v2 (mảnh code, không chạy độc lập)

~~~java
@jdk.jfr.Name("lab.OrderEventV2")
public static final class OrderEventV2 extends jdk.jfr.Event {
    public long orderId;
    public long durationNanos;   // đơn vị mới được ghi rõ trong tên
    public String source;         // có thể thiếu ở bản ghi cũ
    public String outcome;        // field tùy chọn mới
}
~~~

Đây là **mảnh khai báo** dùng khi nâng cấp producer, không phải một file Java riêng hoàn chỉnh. Trong production nên bổ sung annotation `@Label`, `@Description` và `@Timespan` khi phù hợp với semantics, cùng tài liệu hợp đồng schema rõ ràng. Nếu thay đổi tên type giữa v1/v2, giai đoạn chuyển tiếp cần chấp nhận cả hai để không mất dữ liệu khi đọc file cũ.

### 9.2. Chính sách compatibility nên được ghi thành kiểm thử

| Kiểm thử | Mục đích |
| --- | --- |
| Đọc file fixture v1 với consumer mới | Field mới vắng mặt không làm crash |
| Đọc file fixture v2 với consumer mới | Convert duration từ ns → ms, optional field |
| Field duration bị thiếu/null/sai kiểu | Invalid counter tăng; không tạo số liệu 0 giả |
| Event unknown type | Bỏ qua có chủ ý, không phá toàn stream |
| Schema nhiều phiên JDK/vendor/chunk | Không khóa vào numeric ID hoặc một metadata snapshot |
| File hỏng hoặc thiếu quyền đọc | Lỗi được báo; không tạo báo cáo “0 event” giả |
| Đọc file lớn | Memory của consumer ổn định; không nạp mọi event vào list |

Nếu cần chặn breaking changes từ đầu pipeline, tạo CI contract tests bằng file `.jfr` fixture thật, so metadata signatures và kiểm tra các field bắt buộc. **Golden file** phải được tạo/kiểm tra bằng các JDK mà bạn hỗ trợ.

## 10. Vận hành: lỗi, shutdown và phục hồi

### Lỗi callback không được biến thành tắc nghẽn

`onError` nhận ngoại lệ khi xử lý stream/action. Nếu không đăng ký handler, implementation có thể in stack trace mặc định. Trong handler, **chỉ ghi counter hoặc tín hiệu nhẹ**, tránh tiếp tục ném ngoại lệ và tránh gọi remote logging đồng bộ. Lỗi parse field có thể bắt cục bộ, phân loại thành `invalid_schema` thay vì làm hỏng luồng; nhưng không được nuốt tất cả lỗi nghiêm trọng rồi báo thành công.

`onClose` được gọi khi stream đóng. Đừng coi `close()` đồng nghĩa “mọi callback và exporter đã hoàn tất”: tài liệu `EventStream.close()` nói rõ nó không bảo đảm mọi registered action đã kết thúc trước khi trả về. Với `RecordingStream` trên JDK 20+, có `stop()` chờ các event còn được tiêu thụ; nhưng **không gọi `stop()` từ chính callback**, vì có thể đợi vô hạn. Với ví dụ Java 17+ ở đây, dùng `close()` rồi `awaitTermination(timeout)` theo contract; sau đó worker riêng cần drain queue có thời hạn.

### Kết thúc an toàn

Quy trình trên một dịch vụ thực:

1. Ngăn không nhận thêm request hoặc chuyển instance sang trạng thái draining nếu cần.
2. Ngừng stream JFR từ **luồng quản trị** ngoài callback; giới hạn thời gian kết thúc phù hợp.
3. Xử lý hết queue còn lại trong ngân sách shutdown. Nếu hết hạn, ghi số phần tử bị bỏ và chính sách xử lý.
4. Flush batch chưa gửi nếu exporter hỗ trợ, đóng connection và thread pool, giải phóng tài nguyên của stream.
5. Nếu cần forensic data, dump/giữ file `.jfr` độc lập với pipeline telemetry; đừng nhầm retention của file với queue đã xuất.
6. Khi restart, không mặc định stream tiếp tục từ offset cũ hoặc tái phát đủ event chưa nhận. Cơ chế replay/dedupe phải được thiết kế riêng nếu là yêu cầu.

Với `EventStream.openFile`, xử lý file có điểm kết thúc và có thể mở lại để replay (cần kiểm tra trùng dữ liệu). Với live `RecordingStream`, dữ liệu là các batch của recording hiện tại và lịch sử retention; đó **không phải** một durable queue với consumer offset/acknowledgement tiêu chuẩn.

### Cách xử lý outage downstream

- Khi sink chậm, worker dùng timeout/circuit breaker; callback vẫn `offer` nhanh hoặc drop theo policy.
- Khi queue đầy kéo dài, tăng cảnh báo, có thể giảm khối lượng event bằng thay đổi settings/threshold hoặc giảm sampling; không “chữa” bằng retry vô hạn trong callback.
- Khi disk repository JFR chạm giới hạn, `setMaxAge`/`setMaxSize` có thể khiến chunk cũ bị loại. Đây là chính sách lưu trữ; sự kiện đã bị loại khỏi repository **không tự phục hồi**.
- Nếu nhiều consumer cùng đọc một JVM, tổng overhead và duplicate processing cần được đo. Không tạo một recording chi tiết mới cho mỗi request chỉ vì API cho phép.

## 11. Lỗi phổ biến và dấu hiệu nhận biết

| Hiện tượng | Nguyên nhân khả dĩ | Cách khắc phục |
| --- | --- | --- |
| `startAsync()` nhưng JVM vẫn tăng CPU/lag | Callback làm quá nhiều việc hoặc bật quá nhiều event | Chuyển xử lý nặng sang worker, giới hạn event types/settings, đo callback duration |
| Queue tăng liên tục | Exporter throughput thấp hơn event arrival | Batch/scale có giới hạn, giảm upstream event volume, chính sách drop/coalesce |
| OOM ở telemetry agent | Queue/list/pending retry vô hạn hoặc giữ stack/payload lớn | Bounded queue, max payload, max attempts và đo retained heap |
| Số event xử lý khác số `commit()` | JFR delivery/flush, threshold, event disabled, drop queue hoặc shutdown sớm | Đo từng tầng producer→stream→queue→worker; không kết luận từ một counter |
| Worker thấy field của event khác lần trước | Đưa `RecordedEvent` qua thread khi reuse bật | Copy scalar trong callback; hoặc tắt reuse có đánh giá overhead |
| `getLong("elapsedMillis")` ném lỗi | Schema thiếu field hoặc kiểu thay đổi | Dùng `hasField` + typed check; chia version và đếm invalid |
| Duration tăng một triệu lần sau deploy | Field đổi đơn vị milli ↔ nano không đổi contract | Version/rename field, convert đơn vị tường minh |
| `onMetadata` không chạy như mong đợi | Đăng ký sau khi start, file không có metadata mới hoặc khác JDK | Đăng ký trước start, kiểm tra `getEventTypes` và file metadata |
| Event name không còn nhận callback | Producer đổi `@Name` hoặc event disabled | Dual support v1/v2, xác minh tên trong `jfr metadata` |
| Số event có thứ tự “lùi” | Stream theo batch hoặc đã `setOrdered(false)` | Dựa vào timestamp/ID và xử lý late events |
| Consumer restart mất khoảng dữ liệu | Live stream không có offset/ack bền vững | Dùng file/archive và replay design khi thật sự cần |
| Log chứa payload nhạy cảm | Snapshot giữ toàn chuỗi/stack/error context | Allowlist field, giới hạn kích thước, redaction và phân quyền |
| Đọc file `.jfr` không tin cậy | File không hợp lệ hoặc parser xử lý dữ liệu không được kiểm soát | Chỉ nhận file nguồn đáng tin, sandbox tài nguyên, cập nhật JDK |

## 12. Checklist thiết kế và ba bài tập tình huống

**Checklist trước khi đưa consumer lên production:**

- Event type được **allowlist**; sampling, threshold, stack trace và retention được cấu hình theo ngân sách.
- Mọi callback có **thời gian xử lý hữu hạn**, không chờ network/DB/lock lâu.
- Snapshot nhỏ, bất biến, không giữ `RecordedEvent` hoặc đồ thị đối tượng nặng.
- Queue hữu hạn và có **policy khi đầy**, counter dropped/invalid được xuất ra metrics.
- Worker/exporter có timeout, giới hạn retry/backoff, bounded batch và xử lý shutdown.
- Trạng thái event schema được theo dõi qua metadata và contract tests; đọc field cũ/mới có kiểm tra kiểu/đơn vị.
- Có thử nghiệm file v1/v2, event field thiếu, sink outage, queue overflow, file lớn và JVM shutdown.
- Không tuyên bố exactly-once/lossless nếu chưa có cơ chế durable ack/replay.

**Tình huống A:** Callback gửi HTTP và thỉnh thoảng chờ 8 giây, dù `RecordingStream.startAsync()` đã được gọi. Vì sao lag tăng? → Callback vẫn chạy trên luồng xử lý sự kiện của stream; chuyển sang `offer(snapshot)` và worker với timeout/circuit breaker. Đồng thời chấp nhận chính sách mất mẫu hoặc spool có giới hạn khi downstream không phục vụ.

**Tình huống B:** File cũ có `elapsedMillis=15`; bản mới đổi nội dung thành nanosecond nhưng giữ tên `elapsedMillis`. Consumer mới đọc `15` thành 15ms và không ném lỗi. → Đây là **lỗi thay đổi semantics**, `hasField` không thể phát hiện. Phải đổi tên thành `durationNanos` hoặc nâng version event và kiểm tra schema/đơn vị.

**Tình huống C:** Queue 128 slot luôn 100%; code tăng lên 2 triệu slot và hệ thống hết heap sau 20 phút. → Việc tăng queue chỉ trì hoãn backlog. Phải kiểm tra arrival rate, tốc độ exporter, giảm event ở nguồn, batch/scale theo ngân sách hoặc áp dụng drop/coalesce/durable spool có quota.

**Kết luận học tập:** consumer JFR an toàn là một pipeline có **giới hạn tài nguyên và hợp đồng dữ liệu rõ**. `startAsync` tạo luồng nhận sự kiện; `queue.offer` và worker hữu hạn xử lý tốc độ; `setReuse` buộc bạn quyết định vòng đời object; `onMetadata`, `hasField` và versioned event types giúp dữ liệu JFR có thể sống qua nhiều bản ứng dụng/JDK mà không làm sai báo cáo.

## Tài liệu tham khảo chính thức

- Java SE 21 — `EventStream`: batch delivery, `onEvent`, `onMetadata`, `onFlush`, `setReuse`, `setOrdered`, `close`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html
- Java SE 21 — `RecordingStream`: `startAsync`, `enable`, `setMaxAge`, `setMaxSize`, `dump`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html
- Java SE 21 — `MetadataEvent`: `getAddedEventTypes`, `getRemovedEventTypes`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/MetadataEvent.html
- Java SE 21 — `RecordedEvent` và `RecordedObject`: `hasField`, `getValue`, typed getters: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html
- Java SE 21 — `EventType`, `ValueDescriptor`: schema metadata: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventType.html
- Java SE 17 — `RecordingStream`: các API thích hợp với ví dụ Java 17+: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html
- Java SE 21 — `EventSettings`: filter event, threshold và stackTrace: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html
