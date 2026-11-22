# Không thực hiện I/O chậm trên luồng gọi điểm đo

Khi dùng **Java Instrumentation** để theo dõi method, đo thời gian, ghi trace hoặc thu thập metrics, một đoạn mã nhỏ (*probe/hook*) thường được chèn trực tiếp vào đường thực thi của ứng dụng. **Probe chạy ngay trên luồng đang gọi method được đo**, không tự động được chuyển sang một luồng riêng. Nếu probe gọi hệ thống file, mạng, console logging, database hoặc chờ exporter, độ trễ của việc giám sát sẽ **cộng trực tiếp vào độ trễ nghiệp vụ**.

Vì vậy, với các đường chạy nhạy cảm hiệu năng, quy tắc cơ bản là: **không thực hiện I/O chậm, retry hoặc chờ hàng đợi có chỗ trong hook**. Hook chỉ thu thập một ít thông tin cần thiết rồi chuyển dữ liệu sang **bộ đệm bounded** hoặc cập nhật bộ đếm nhẹ. Một worker chuyên trách sẽ thực hiện encode, flush, ghi file, xuất mạng và retry ở ngoài luồng ứng dụng.

Tuy nhiên, **asynchronous không có nghĩa zero cost hay zero loss**. Nếu queue vô hạn, có thể dẫn tới OutOfMemoryError. Nếu queue đầy mà producer dùng `put()`, thread ứng dụng bị chặn. Nếu worker chết mà không ai phát hiện, telemetry mất âm thầm. Bài này làm rõ kiến trúc, lựa chọn khi quá tải, ví dụ Java 17+ chạy được và cách kiểm chứng chi phí thực tế.

## 1. Xác định đúng luồng gọi điểm đo

Hình dung agent chèn hook vào `OrderService.submit()`:

```text
REQUEST THREAD
  |
  v
OrderService.submit()
  +-- Probe.enter()     <- cùng request thread
  +-- business logic
  +-- Probe.exit()      <- cùng request thread
  |
  v
HTTP response
```

Nếu `Probe.exit()` chờ 200 ms để file/network ghi xong, request cũng có thể chậm thêm 200 ms. Khi lệnh được instrument thực thi nhiều lần trong một request, overhead lặp lại nhiều lần. Trong vùng code đang giữ lock, thread bị chặn còn làm các threads khác chờ lock, gây hiệu ứng dây chuyền.

Một đường đi phù hợp hơn:

```text
REQUEST THREAD
   |
   +-- timestamp / event ID / primitive fields
   |
   +-- boundedQueue.offer(event)
           |             |
         accepted        full
           |             |
           v             v
      bounded queue    drop/sample/counter
           |
           v
EXPORTER THREAD
   |
   +-- format / batch / compress
   +-- file or network I/O
   +-- flush / retry / error report
```

Phân biệt **hai thời gian**: chi phí hook trả quyền điều khiển cho business thread (*capture/enqueue latency*) và thời gian từ lúc sự kiện sinh ra đến lúc được lưu/xuất (*delivery latency*). Tách I/O giúp giới hạn thành phần thứ nhất, nhưng có thể làm tăng thành phần thứ hai.

### 1.1. I/O chậm không chỉ là ghi file

Các thao tác cần tránh trong hook nhạy độ trễ:

- `Files.writeString(...)`, `FileOutputStream.write(...)`, `BufferedWriter.flush()`, `FileChannel.force(...)` và file rotation;
- `System.out.println(...)` / `System.err.println(...)` — console/pipe có thể có lock, buffer và phía nhận chậm;
- logging đồng bộ từ SLF4J/Logback/Log4j hoặc cấu hình async appender mà khi đầy **chuyển sang chặn caller**;
- HTTP/gRPC, socket write, DNS lookup, TLS handshake, exporter, JDBC/database;
- gọi `Future.get()`, `CompletableFuture.join()`, `Thread.sleep()`, `CountDownLatch.await()`, `Thread.join()` hoặc `BlockingQueue.put()` trong hot path;
- serialize toàn bộ request, dump stack trace lớn, tạo JSON nặng, phản xạ sâu hoặc load class/helper chưa được khởi tạo;
- lấy khóa chung lâu, hoặc chờ lock logger/formatter có thể đang bị worker khác giữ.

Không phải mọi thao tác trên đều là file/network I/O, nhưng chúng đều có thể **kéo dài thời gian luồng nghiệp vụ bị giữ lại**. Hãy phân tích từ góc nhìn tail latency và khả năng chặn thay vì chỉ từ tên API.

## 2. Anti-pattern: I/O đồng bộ trong hook

Ví dụ **chỉ minh họa hành vi cần tránh**, không phải chương trình độc lập:

```java
static void onExit(String method) throws java.io.IOException {
    java.nio.file.Files.writeString(
        java.nio.file.Path.of("trace.log"),
        method + System.lineSeparator(),
        java.nio.file.StandardOpenOption.CREATE,
        java.nio.file.StandardOpenOption.APPEND
    );
}
```

Có ít nhất năm vấn đề:

1. Lệnh ghi chạy **trong thread gọi `onExit`**; filesystem có thể ngẫu nhiên chậm vì disk saturation, remote file server, quota hay flush.
2. Việc mở/cập nhật file ở mỗi event tạo overhead và tranh chấp khi nhiều luồng ghi đồng thời.
3. Nếu phát sinh `IOException` rồi thoát hook, **nghiệp vụ có thể thất bại vì lỗi telemetry**; trong `finally`, lỗi này còn có thể che mất exception nghiệp vụ ban đầu.
4. Logger/formatter có thể cấp phát nhiều đối tượng, làm tăng GC và tạo tail latency dù I/O thường nhanh.
5. Ghi dày đặc làm giảm throughput, khiến request backlog tăng, lại tiếp tục sinh thêm log — vòng lặp khuếch đại sự cố.

**Dùng `BufferedWriter` trực tiếp trong hook chưa đủ.** Buffer có thể phải flush khi đầy, giữ lock hoặc chờ I/O. Điều quan trọng là **lệnh ghi diễn ra ở luồng khác**, không phải chỉ có một buffer ở dưới API.

### 2.1. Đừng tưởng mọi logger đều async

`logger.info("duration={}", duration)` có thể là lệnh rất rẻ trong một cấu hình; cũng có thể đồng bộ hoặc chặn khi appender/queue full. Nếu bạn tạo message trước khi logger kiểm tra level, việc format nặng vẫn xảy ra ngay trên caller.

Trong instrumentation, phải kiểm tra **cấu hình exporter/appender thực tế**: bounded hay unbounded, chính sách khi đầy, đồng bộ hóa nội bộ, khả năng gọi lại hook từ chính logger và hành vi lúc shutdown.

## 3. Công việc nào nên nằm trong hook?

Một hook nên có **chi phí nhỏ và một ngưỡng rõ ràng**:

| Công việc | Khuyến nghị |
| --- | --- |
| Đo duration | Dùng `System.nanoTime()` để tính thời gian trôi qua; đừng format timestamp thành chuỗi phức tạp trong mỗi hook. |
| Lấy một số primitive/ID | Snapshot ít trường, tránh truy cập lazy getter có thể tạo I/O. |
| Kiểm tra sampling | Kiểm tra sớm trước khi cấp phát event. |
| Tạo record nhỏ | Chỉ giữ dữ liệu cần thiết; không giữ reference tới toàn bộ request/context lớn. |
| Enqueue | Dùng bounded queue và thao tác **không đợi dung lượng** như `offer(event)`. |
| Queue full | Theo chính sách có chủ đích: drop, sample/aggregate, hoặc cơ chế dành riêng cho dữ liệu bắt buộc. |
| Counters | `AtomicLong`/`LongAdder` hoặc cơ chế phù hợp; kiểm tra contention dưới tải. |
| Format/encode, I/O, retry | Chuyển sang consumer thread. |
| Flush/drain/join | Chỉ làm ở lifecycle thread, không bên trong điểm đo. |

Mã hook cần có **đường thoát nhanh** khi tracing bị tắt, khi exporter lỗi hoặc khi cần sampling. Tránh để code đo dùng chính logging infrastructure đang bị đo rồi tạo **đệ quy instrumentation**.

### 3.1. Ngoại lệ trong probe có thể nguy hiểm

Nếu agent chèn probe vào `finally` để đảm bảo ghi sự kiện cả khi business method ném lỗi, bản thân probe **không nên ném lỗi telemetry làm thay exception nghiệp vụ**. Ví dụ:

```java
// Đoạn minh họa trong method; businessOperation, probe, eventId
// được định nghĩa ở nơi tích hợp thực tế.
long started = System.nanoTime();
try {
    businessOperation();
} finally {
    long elapsedNs = System.nanoTime() - started;
    probe.tryRecord(eventId, elapsedNs);
}
```

Đây **không phải file Java độc lập**. `tryRecord` cần hoạt động theo failure policy riêng, không gửi HTTP hoặc ghi file đồng bộ và không tùy tiện ném `IOException` ra caller. Cũng không được vô điều kiện `catch(Throwable)` rồi nuốt các lỗi nghiêm trọng như `VirtualMachineError` chỉ để bảo vệ telemetry.

## 4. Các thao tác queue: không nhầm `offer` với `put`

Java SE 17 `ArrayBlockingQueue` là **bounded buffer** có capacity cố định. Các thao tác thường gặp:

| API | Khi queue đầy | Tác động tới caller |
| --- | --- | --- |
| `offer(event)` | Trả `false` nếu không thể thêm ngay do đầy | Không chờ queue có chỗ; phù hợp best-effort telemetry. |
| `put(event)` | **Đợi** tới khi có chỗ | Có thể kéo dài thời gian nghiệp vụ vô hạn nếu worker ngừng lấy. |
| `offer(event, timeout, unit)` | Có thể đợi tới thời hạn | Timeout bị cộng vào business latency. |
| `add(event)` | Ném `IllegalStateException` khi đầy | Không phù hợp nếu lỗi chưa được quản lý. |
| Queue không giới hạn | Backlog có thể tăng không giới hạn | Có thể giữ sống event graph, gây GC/OOM. |

Lưu ý kỹ: **`ArrayBlockingQueue.offer` không phải thuật toán wait-free/lock-free**. Nó không chờ **dung lượng**, nhưng implementation sử dụng khóa nội bộ; nhiều producers có thể tranh chấp ngắn. Nếu muốn ngân sách latency cực thấp, phải benchmark và có thể chọn SPSC/MPSC/ring buffer hoặc per-thread buffers.

**Queue chỉ đệm được burst**, không giải quyết sự chênh lệch throughput kéo dài. Nếu producer sinh nhanh hơn consumer, queue bounded sẽ đầy và hệ thống phải thực thi overflow policy.

## 5. Chọn chính sách khi quá tải

| Chính sách | Đổi lấy điều gì? | Trường hợp |
| --- | --- | --- |
| **Drop newest** | Mất event mới khi queue full; đơn giản, caller không đợi capacity | Metrics/trace best-effort. |
| **Drop oldest** | Có dữ liệu mới hơn nhưng mất lịch sử cũ; khó giữ thứ tự | Trạng thái ưu tiên sự kiện gần nhất. |
| **Sampling** | Chỉ thu một tập đại diện; giảm event volume | Hot methods có tần suất rất cao. |
| **Aggregation** | Không giữ từng event; chỉ count/summary/histogram | Metrics thống kê. |
| **Coalescing** | Gộp nhiều cập nhật cùng key | Progress/state, không yêu cầu đầy đủ từng thay đổi. |
| **Backpressure/block** | Giữ dữ liệu nhưng producer phải chờ | Chỉ dùng khi chấp nhận ảnh hưởng latency trong hợp đồng nghiệp vụ. |
| **Durable journal** | Cần thiết kế ghi bền, chi phí I/O/quy tắc lỗi | Audit/sự kiện bắt buộc không được mất. |

**Không thể vừa đòi “không chặn trong mọi tình huống”, vừa “không mất một sự kiện”, vừa dùng bộ nhớ hữu hạn nếu downstream có thể dừng vô thời hạn.** Đây là trade-off kiến trúc. Nếu dữ liệu mang tính pháp lý, thanh toán, compliance hoặc audit bắt buộc, không lặng lẽ drop để bảo vệ latency; cần durable boundary phù hợp ngay ở thiết kế nghiệp vụ.

Cần phân biệt ba counter: **accepted** là đã vào queue, **dropped** là bị bỏ, **persisted/exported** là đã xử lý thành công theo định nghĩa đích. Accepted **không đồng nghĩa đã lưu ra file/dịch vụ**. Với exporter có retry, còn phải tính tới duplicate/at-least-once delivery.

## 6. Ví dụ Java 17+ chạy được: tách điểm đo và I/O

Ví dụ đầy đủ dưới đây không cần bytecode weaving, vì gọi `onMeasurement(id)` để **mô phỏng hook được agent chèn vào method**. Chương trình chỉ tập trung vào việc **hook không ghi file**, bounded queue và worker tách biệt.

Để kiểm chứng overflow **deterministic**, consumer dùng một `CountDownLatch` **chỉ trong bài test** để tạm ngừng lấy event khi main gửi năm events vào queue capacity hai. Hai events đầu vào hàng đợi thành công, ba events sau bị drop ngay. Sau khi kết thúc các điểm đo, lệnh `close()` từ main mới giải phóng worker để ghi file.

Cấu trúc:

```text
buffered-probe-demo/
└── BufferedProbeDemo.java

Sau khi chạy xuất hiện:
└── probe-events.log
```

### 6.1. `BufferedProbeDemo.java`

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public final class BufferedProbeDemo {
    private BufferedProbeDemo() {}

    private record Event(int id) {}

    public static void main(String[] args) throws Exception {
        Path path = Path.of("probe-events.log");
        try (BoundedProbe probe = new BoundedProbe(path, 2)) {
            for (int id = 1; id <= 5; id++) {
                probe.onMeasurement(id);
            }
            System.out.println("[caller] accepted=" + probe.accepted()
                    + " dropped=" + probe.dropped());
        }
        List<String> saved = Files.readAllLines(path, StandardCharsets.UTF_8);
        System.out.println("[after-close] persisted=" + saved.size());
        System.out.println("[after-close] events=" + String.join(",", saved));
    }

    private static final class BoundedProbe implements AutoCloseable {
        private final ArrayBlockingQueue<Event> queue;
        private final AtomicLong accepted = new AtomicLong();
        private final AtomicLong dropped = new AtomicLong();
        private final AtomicBoolean closing = new AtomicBoolean();
        private final CountDownLatch writerReady = new CountDownLatch(1);
        private final CountDownLatch allowDrain = new CountDownLatch(1);
        private final Thread writer;
        private final Path path;
        private volatile IOException failure;

        BoundedProbe(Path path, int capacity)
                throws IOException, InterruptedException {
            this.path = path;
            this.queue = new ArrayBlockingQueue<>(capacity);
            this.writer = new Thread(this::writeLoop, "probe-writer");
            writer.start();
            writerReady.await(); // Khởi tạo một lần, KHÔNG trong điểm đo.
            if (failure != null) {
                throw failure;
            }
        }

        void onMeasurement(int id) {
            if (closing.get()) {
                dropped.incrementAndGet();
                return;
            }
            if (queue.offer(new Event(id))) {
                accepted.incrementAndGet();
            } else {
                dropped.incrementAndGet(); // Đầy: bỏ sự kiện, không đợi I/O.
            }
        }

        long accepted() { return accepted.get(); }
        long dropped() { return dropped.get(); }

        private void writeLoop() {
            try (BufferedWriter out = Files.newBufferedWriter(
                    path, StandardCharsets.UTF_8)) {
                writerReady.countDown();
                allowDrain.await(); // Chỉ để test tình huống queue đầy có kiểm soát.
                while (true) {
                    Event event = queue.poll(50, TimeUnit.MILLISECONDS);
                    if (event != null) {
                        out.write("hit-" + event.id());
                        out.newLine();
                    }
                    if (closing.get() && queue.isEmpty()) {
                        break;
                    }
                }
                out.flush();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                failure = new IOException("Writer interrupted", interrupted);
            } catch (IOException io) {
                failure = io;
            } finally {
                writerReady.countDown(); // Kể cả khi open file thất bại.
            }
        }

        @Override
        public void close() throws IOException, InterruptedException {
            closing.set(true);
            allowDrain.countDown();
            writer.join(); // Có thể đợi I/O: chỉ gọi NGOÀI điểm đo.
            if (failure != null) {
                throw failure;
            }
        }
    }
}
```

**Lưu ý:** Mã Java 17 trên là chương trình độc lập. Nó tạo một file log trong thư mục làm việc; `Files.newBufferedWriter` mặc định sẽ **ghi đè file cũ** nếu bạn chạy lại. Hãy dùng thư mục thử nghiệm riêng, không sử dụng file đang chứa dữ liệu cần giữ.

### 6.2. Vì sao hook ở đây không chờ I/O?

Hàm `onMeasurement(int id)` chỉ:

1. Kiểm tra trạng thái `closing`.
2. Tạo record nhỏ chứa số nguyên `id`.
3. Thử `queue.offer(...)`, **không đợi capacity**.
4. Tăng `accepted` hoặc `dropped`.

Nó **không** gọi `Files.writeString`, `newBufferedWriter`, `flush`, `logger.info`, `sleep`, `await` hay `join`. Những thao tác chờ/mở file/ghi file nằm ở **writer thread** hoặc **lifecycle/main thread**. Vì vậy worker chậm sẽ gây **queue full + drop** chứ không bắt request thread chờ tới lúc writer ghi xong.

Cần nói chính xác: `offer` của `ArrayBlockingQueue` **vẫn dùng lock nội bộ**; hook không hoàn toàn wait-free, cũng còn chi phí cấp phát record, counter và memory barriers. Mục tiêu của thiết kế là **tránh chờ I/O/downstream**, không hứa không có bất kỳ overhead nào.

`CountDownLatch allowDrain` trong worker chỉ để cố ý tạo queue full có thể tái lập. **Không đặt một latch như thế trong consumer production**; consumer thật nên lấy và ghi events liên tục với chính sách batch/retry.

### 6.3. Lệnh biên dịch và chạy

Dùng JDK 17 hoặc mới hơn:

```bash
javac --release 17 BufferedProbeDemo.java
java BufferedProbeDemo
```

PowerShell cũng dùng hai lệnh trên khi `javac` và `java` có trong `PATH`. `--release 17` cho phép record `Event` và các API concurrent trong mã, đồng thời đảm bảo classfile/source target Java 17.

**Stdout đã kiểm chứng trên Zulu/OpenJDK 24.0.2 với mã biên dịch bằng `javac --release 17`:**

```text
[caller] accepted=2 dropped=3
[after-close] persisted=2
[after-close] events=hit-1,hit-2
```

Nội dung `probe-events.log` sau khi đóng:

```text
hit-1
hit-2
```

Phân tích kết quả:

- Constructor khởi động thread `probe-writer` và đợi worker mở file **trong giai đoạn setup**, không ở hook.
- Worker được giữ sau `writerReady` bởi `allowDrain` **chỉ để thử tình huống nghẽn**.
- Hai lần `onMeasurement(1)` và `onMeasurement(2)` vào queue hai slot.
- Ba lần với id 3, 4, 5 gặp full → `offer` trả `false` → tăng `dropped` mà không ghi file trên caller.
- Sau khi các lần gọi hook đã kết thúc, `try-with-resources` gọi `close()` để giải phóng latch và `writer.join()` trên main thread. Worker ghi hai events và kết thúc; khi đó main mới đọc file.
- Tổng accepted, dropped, persisted theo thực nghiệm: **2, 3, 2**. Đây không phải benchmark throughput mà là kiểm tra chính sách overflow.

**Không được suy từ kết quả này rằng luôn có đúng hai event được persist trong ứng dụng thật.** Khi worker chạy bình thường, nó có thể tiêu thụ đồng thời với producer, nên tỷ lệ accepted/drop phụ thuộc tải và scheduling.

## 7. Lifecycle, shutdown và lỗi worker trong production

Demo dùng **một producer trên main thread** và chỉ gọi `close()` **sau khi mọi lời gọi `onMeasurement` hoàn tất**. Đây là tiền đề quan trọng để drain chính xác mà không phải mô hình hóa hàng trăm producers.

### 7.1. Race khi nhiều producers đang hoạt động

Nếu ứng dụng đang đo trên nhiều threads:

```text
producer A: thấy closing=false
                                     manager: closing=true
                                     writer: queue đã rỗng, thoát
producer A: enqueue thành công
                                     -> event không còn người tiêu thụ
```

Chỉ dùng `AtomicBoolean closing` **không biến cặp thao tác check+offer thành atomic**. Hệ thống thật phải có lifecycle protocol: dừng nhận các lần hook mới, đợi các producers đang hoạt động/đang enqueue, xác định ranh giới drain, rồi mới cho consumer đóng. Có thể dùng phaser, counter in-flight với barrier, hoặc cơ chế đặc thù khác; không sao chép demo một producer thành multi-producer service mà không bổ sung điều phối.

### 7.2. Đóng pipeline có thể phải chặn

`writer.join()`, `flush()` và đóng file có thể mất thời gian dài. Vì thế chỉ làm ở **shutdown/control thread** chứ không trong các method nghiệp vụ được instrument. Bản demo dùng `join()` không timeout để giải thích rõ thứ tự; production cần **shutdown timeout và chính sách khi vượt hạn**, ví dụ báo số event chưa persist hoặc cho phép service dừng với lượng mất đã biết.

Đặt writer là daemon thread giúp process dễ thoát, nhưng có thể mất dữ liệu chưa drain; để non-daemon thread mà không có timeout cũng có thể giữ JVM lại khi downstream kẹt. Cả hai lựa chọn đều cần chính sách vận hành.

### 7.3. Error state không được biến mất

Trong ví dụ, worker giữ `IOException` ở `failure` và `close()` báo lại. Nếu writer lỗi sớm, producer có thể tiếp tục enqueue cho đến khi queue đầy. **Production phải phát hiện lỗi sớm hơn**, xuất một health state, stop/reconfigure producer hoặc fallback theo chính sách. Đừng dựa vào “đến lúc shutdown mới biết file lỗi”.

Các metric hữu ích: writer status, last successful export, dropped-on-full, permanently-failed, retry-count, backlog, consumer throughput, lượng dữ liệu chưa flush khi đóng.

## 8. Batching, retry và nguồn lực hữu hạn

Chuyển I/O sang thread khác **chưa khiến downstream nhanh hơn**. Nếu producer sinh `λ` sự kiện/giây và worker chỉ ghi được `μ` sự kiện/giây với `λ > μ` kéo dài, backlog tăng gần `λ - μ` cho đến khi queue đầy.

Ví dụ minh họa:

```text
Producer: 50.000 events/second
Consumer: 30.000 events/second
Backlog grows: 20.000 events/second
Queue capacity: 10.000 items

Trong mô hình lý tưởng hóa, queue rỗng đầy sau khoảng 0,5 giây.
```

Kích thước queue chỉ giúp **hấp thụ burst**, không thể xóa một mức thiếu throughput kéo dài. Queue 10.000 entries cũng chỉ giới hạn **số items**, không đảm bảo chi phí bộ nhớ đúng 10.000 byte: mỗi event có thể giữ reference tới object graph lớn.

### 8.1. Batch trong consumer

Một worker có thể lấy nhiều items một lượt bằng `drainTo` hoặc một vòng polling rồi serialize và gửi thành batch:

```text
bounded queue -> drain small batch -> encode -> write/send -> flush
```

Batch size và flush interval phải có hạn. Batch lớn có thể tăng throughput nhưng thêm memory và delivery latency. `BufferedWriter.flush()` không đồng nghĩa `fsync` đảm bảo dữ liệu đã nằm bền vững trên thiết bị; độ bền còn tùy API/filesystem và kiến trúc collector.

### 8.2. Retry có ngân sách

Retry network/disk **chỉ ở worker**, với số lần/thời gian có giới hạn, backoff, lỗi có thể/không thể retry và cách xử lý duplicate. Retry quá dài làm worker ngừng drain, queue tiếp tục đầy. Cần policy về drop, durable spool, sampling hoặc circuit breaker, không mặc định retry vô tận rồi bắt business thread chờ.

### 8.3. Tránh giữ object graph lớn trong queue

Không enqueue nguyên `HttpServletRequest`, `Throwable`, `ClassLoader`, các user session hoặc mảng payload lớn chỉ để worker sau đó lấy vài trường. Việc giữ reference có thể kéo dài lifetime của cả graph, gây heap pressure, rò thông tin nhạy cảm hoặc đọc trạng thái mutable đã đổi. Snapshot **một vài primitive/immutable identifiers** trong hook, tránh tạo JSON/string lớn; worker mới encode chúng.

## 9. Instrumentation thật: class loading và recursion

Một Java agent có thể dùng `ClassFileTransformer` hoặc Class-File API/bytecode library để đưa lời gọi helper vào method. Nhưng **mã helper được gọi mỗi lần thực thi method vẫn nằm trên business thread**. Transformer chỉ quyết định cách chèn hook; nó không tự tạo async boundary.

Cũng cần chú ý `ClassFileTransformer.transform(...)` chạy trong quá trình JVM định nghĩa/redefine/retransform lớp. Làm I/O chậm ngay **trong callback transform** có thể kéo dài class loading, gây contention hay deadlock do khóa classloader. Vì vậy tránh cả hai loại công việc đồng bộ: **I/O trong hook chạy thường xuyên** và **I/O trong callback biến đổi lớp**.

### 9.1. Tự instrument logger/exporter gây đệ quy

Nếu agent instrument luôn class của logger, writer, HTTP client hoặc chính agent helper, worker xử lý một event có thể tạo event mới, rồi lại được worker xử lý — **vòng lặp logging storm**.

Biện pháp:

- Exclude packages/classes của agent, exporter, serializer và hạ tầng được agent dùng khỏi transformer khi hợp lý.
- Khi cần, dùng reentrancy guard `ThreadLocal` được restore trong `finally`; guard cũng có overhead nên kiểm chứng.
- Không ghi lỗi của exporter bằng cùng logging pipeline đang hỏng.
- Tránh class-loading lặp và helper không truy cập được do module/class-loader boundaries.

### 9.2. Thread context không tự di chuyển sang worker

Khi sự kiện chuyển sang worker, dữ liệu `ThreadLocal`, request scoped context, tracing context hay security principal của producer **không tự động xuất hiện** trên consumer thread. Nếu cần correlation, hãy lấy snapshot **những ID cần thiết** tại hook rồi truyền trong event. Không đọc nhầm `ThreadLocal` của worker như thể nó là request thread.

## 10. Đo overhead và kiểm chứng hệ thống

Để chứng minh việc tách I/O thực sự có tác dụng, phải đo với baseline cùng tải và có failure scenarios.

| Metric | Ý nghĩa |
| --- | --- |
| Hook duration p50/p95/p99/p99.9 | Mức chi phí mà instrumentation bổ sung cho caller. |
| Request end-to-end latency | Tác động khách hàng thấy được; đối chiếu agent bật/tắt. |
| Queue offer failure / dropped | Mức sự kiện bị bỏ do quá tải. |
| Queue occupancy & backlog | Worker có theo kịp producer không; coi `size()` là snapshot. |
| Consumer throughput/batch size | Số events đã xử lý và hiệu quả batch. |
| File/socket write latency | Nơi nào I/O thực sự diễn ra, downstream có kẹt không. |
| Accepted vs persisted/exported | Phân biệt vào queue và tới đích. |
| GC allocation rate, memory | Event objects, buffers, queue giữ sống graph. |
| CPU, contention, thread stalls | Queue locks/atomic counters/worker có gây bottleneck khác không. |
| Failures, retries, shutdown loss | Độ tin cậy và hành vi lúc backend lỗi. |

### 10.1. Java Flight Recorder (JFR)

Oracle Java 17 hướng dẫn dùng JFR để phân tích các event như:

- `jdk.FileRead`, `jdk.FileWrite`;
- `jdk.SocketRead`, `jdk.SocketWrite`;
- `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`;
- `jdk.ThreadPark`, `jdk.ThreadSleep`.

Xem **thread name, stack trace và duration** để phân biệt request thread đang làm I/O hay chỉ `probe-writer`/exporter thread. Cấu hình JFR có **threshold**: các I/O rất ngắn có thể không xuất hiện trong recording; “không thấy FileWrite event” **không phải bằng chứng chắc chắn không có I/O**.

### 10.2. Thử tình huống xấu

Đừng chỉ benchmark “disk nhanh, mạng khỏe”. Cần test:

1. Backend dừng đọc, socket write bị timeout.
2. Disk đầy hoặc file permissions không đủ.
3. Queue đầy dưới burst dài.
4. Nhiều producer threads tranh chấp queue/counters.
5. GC dưới allocation rate cao.
6. Worker lỗi trong khi ứng dụng vẫn tiếp tục chạy.
7. Shutdown ngay khi còn backlog và ngay khi I/O kẹt.
8. Agent bật/tắt dưới cùng workload, xem p99/p99.9 chứ không chỉ average.

Việc tách I/O phải **cải thiện cách ly latency**, nhưng chính sách drop/health/durability vẫn cần được đánh giá rõ.

## 11. Những lỗi thiết kế phổ biến

| Nhận định / hành vi | Vấn đề thực tế |
| --- | --- |
| “Log một dòng tại điểm đo thì luôn nhanh.” | File/console/network có thể có tail latency và lock contention. |
| “Logger luôn async.” | Tùy appender; có cấu hình block caller khi queue đầy. |
| “`ArrayBlockingQueue.offer` là wait-free.” | Không, nó dùng khóa nội bộ; chỉ không đợi queue có chỗ. |
| “`BlockingQueue.put` thích hợp cho hot hook.” | Có thể đợi lâu nếu consumer chậm/đứng. |
| “Queue unbounded không block nên không rủi ro.” | Dễ giữ nhiều objects, tăng GC và OOM. |
| “Accepted nghĩa là đã ghi ra file.” | Accepted chỉ là vào queue, chưa persisted. |
| “Tăng capacity đủ lớn thì không bao giờ đầy.” | Nếu producer luôn nhanh hơn consumer, cuối cùng vẫn đầy. |
| “Vừa không chặn vừa không mất một event bằng RAM queue.” | Không bảo đảm dưới downstream outage vô hạn với nguồn lực hữu hạn. |
| “Ghi log trong `finally` có thể ném lỗi tùy ý.” | Có thể che exception nghiệp vụ gốc. |
| “Đã async thì không cần theo dõi dropped.” | Dữ liệu thiếu có thể làm metrics/traces sai; phải report. |
| “Worker daemon luôn an toàn.” | Process có thể kết thúc trước khi flush/drain. |
| “Gọi `join()` từ mỗi hook để chắc dữ liệu đã lưu.” | Làm luồng nghiệp vụ chờ worker; phá mục tiêu async. |
| “Giữ nguyên Request/Throwable trong queue là rẻ.” | Có thể giữ sống graph lớn/PII và dữ liệu mutable. |
| “Consumer lỗi nhưng producer cứ enqueue mãi vẫn ổn.” | Queue sẽ đầy hoặc tích backlog; cần health và fallback. |
| “Gọi `CompletableFuture.runAsync(...)` cho mỗi event là đủ.” | Có thể làm cạn thread pool, queue mặc định phình và khó kiểm soát failure. |
| “Điểm đo có thể instrument chính exporter vô hại.” | Dễ tạo recursion, sự kiện nhân cấp số, stack overflow. |
| “`close()` bất kỳ lúc nào cũng drain đúng với nhiều producers.” | Cần lifecycle barrier để loại race check+enqueue. |
| “Không thấy JFR FileWrite chứng minh hook không I/O.” | Threshold/configuration có thể bỏ qua các I/O ngắn. |
| “Tách I/O làm hook có overhead bằng 0.” | Vẫn có event allocation, queue/atomic contention, memory barriers và GC. |

## 12. Bài tập tự kiểm tra

**Câu 1.** Vì sao không gọi `Files.writeString(...)` trực tiếp trong `Probe.onExit()`?

**Đáp án:** Vì probe chạy trên business thread, file I/O có thể chặn, tăng latency và thậm chí làm thay đổi exception nghiệp vụ nếu lỗi bị truyền ra ngoài.

**Câu 2.** Queue có capacity hai; worker chưa lấy event. Năm lần `offer` liên tiếp theo drop-newest policy tạo kết quả nào?

**Đáp án:** Hai events được accepted, ba events bị dropped; đó là trường hợp demo kiểm chứng. Producer không chờ capacity.

**Câu 3.** `offer` và `put` khác nhau gì khi queue đầy?

**Đáp án:** `offer` trả false khi không thể thêm ngay do full; `put` chờ đến khi có chỗ hoặc bị interrupt. `offer` không tự bảo đảm lock-free.

**Câu 4.** Có thể dùng accepted counter để xác nhận downstream đã nhận tất cả events không?

**Đáp án:** Không. Cần persisted/exported acknowledgements với semantics rõ; accepted chỉ xác nhận queue đã nhận.

**Câu 5.** Nếu worker chậm lâu hơn tốc độ producer, tăng queue capacity có giải quyết vĩnh viễn?

**Đáp án:** Không. Nó chỉ hấp thụ burst; backlog vẫn tăng đến khi đầy nếu throughput deficit kéo dài.

**Câu 6.** Có thể gọi `writer.join()` khi shutdown không?

**Đáp án:** Có, ở lifecycle thread và có policy/time budget; không dùng trong hook. Production cần xử lý I/O treo và dữ liệu chưa flush.

**Câu 7.** Chỉ có `AtomicBoolean closing` là đủ drain tuyệt đối đúng khi nhiều producers đang enqueue?

**Đáp án:** Không. Có race giữa check và offer; phải có lifecycle coordination/barrier hoặc ngăn các in-flight publishers trước khi worker thoát.

**Câu 8.** Vì sao không enqueue toàn bộ `HttpServletRequest` khi chỉ cần method ID và duration?

**Đáp án:** Nó có thể giữ sống object graph lớn, chứa dữ liệu nhạy cảm, và thay đổi trong khi worker đọc. Nên snapshot dữ liệu nhỏ, immutable cần thiết.

**Câu 9.** JFR cho thấy `jdk.SocketWrite` trên request thread của một agent đang export trace. Điều đó gợi ý gì?

**Đáp án:** Exporter có thể đang thực hiện I/O đồng bộ trên đường nghiệp vụ. Kiểm tra call stack/agent config và chuyển sang worker có giới hạn để cách ly.

**Câu 10.** Dữ liệu audit bắt buộc phải đủ, nhưng producer không được chặn và backend có thể mất kết nối vô hạn: queue RAM bounded có bảo đảm đầy đủ không?

**Đáp án:** Không. Cần thay đổi hợp đồng và kiến trúc durable messaging/journal cùng failure semantics; không thể vừa yêu cầu zero loss dưới outage vô hạn vừa bảo đảm không chặn bằng RAM hữu hạn.

## 13. Tóm tắt và nguồn tham khảo

**Quy tắc để instrumentation không phá hiệu năng nghiệp vụ:**

1. **Hook chạy trên caller thread** nên không ghi file, gọi mạng, flush, retry hoặc chờ downstream.
2. **Chỉ thu thập tối thiểu**, snapshot immutable/primitive, sampling sớm và chuyển dữ liệu qua bounded queue.
3. **`offer` không đợi capacity**, nhưng vẫn có contention; không quảng bá wait-free và phải benchmark.
4. Khi quá tải, **overflow policy là bắt buộc**: drop, sample, aggregate hoặc một kiến trúc durable phù hợp dữ liệu.
5. **Accepted khác persisted**; phải đo drops, queue backlog, throughput consumer, write failures và shutdown losses.
6. Consumer chịu trách nhiệm batching/serialize/export/retry, không đẩy lỗi I/O vào business thread.
7. **Shutdown và class-loader/transformer callbacks cũng cần tránh chặn**, đồng thời phải phòng instrumentation recursion.
8. Kiểm chứng bằng JFR/profiler và p95/p99 latency trong cả các tình huống downstream lỗi.

Tài liệu chính thức:

- [Java SE 17 — ArrayBlockingQueue, offer/put/timeout semantics](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)
- [Java SE 17 — BlockingQueue và memory consistency effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Java SE 17 — java.lang.instrument agent/transformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Oracle Java SE 17 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [OpenJDK JEP 328 — Java Flight Recorder](https://openjdk.org/jeps/328)