# Độ trễ async logging trong Java Core Logging

## Mục tiêu học tập

Bài học này thuộc nhóm **Logging bất đồng bộ**. Sau khi học, bạn có thể:

- Phân biệt **độ trễ của lời gọi ghi log** với **độ trễ từ lúc phát sinh sự kiện đến lúc log được ghi, chuyển đi hoặc có thể tìm thấy**.
- Mô tả vai trò của hàng đợi, luồng xử lý nền, thiết bị ghi, log collector và hệ thống index trong độ trễ logging.
- Giải thích vì sao async logging thường giảm thời gian chặn luồng nghiệp vụ nhưng không đảm bảo log xuất hiện sớm hơn hoặc không bao giờ mất.
- Đo p50/p95/p99 latency, queue depth, blocked enqueue time, throughput và số log bị loại; lựa chọn backpressure phù hợp.
- Cấu hình, kiểm thử và xử lý lỗi độ trễ async logging trong Java 17+ với các thư viện như Logback và Log4j 2.

Không có một con số “độ trễ async logging” chung cho mọi hệ thống. Cần xác định **đang đo từ đâu đến đâu**, tải bao nhiêu, yêu cầu giữ log thế nào và đầu ra là file, console hay mạng.

## 1. Async logging thay đổi điểm chờ của ứng dụng

Với synchronous logging, lời gọi ghi log thường xử lý phần lớn công việc của appender ngay trên luồng nghiệp vụ: tạo event, định dạng và ghi vào output theo cơ chế của appender. Lời gọi có thể bị chậm khi I/O hoặc lock chậm.

Với asynchronous logging, luồng nghiệp vụ thường tạo/capture log event rồi đưa vào **queue hoặc ring buffer**. Một hoặc nhiều worker sau đó lấy event để encode và chuyển tới appender/sink. Luồng nghiệp vụ có thể quay lại sớm, nhưng log **chưa chắc đã được ghi** khi phương thức logging trả về.

```text
SYNC:
Business thread -> log event -> format/write sink -> return to business

ASYNC:
Business thread -> capture event -> enqueue -> return to business
                                      |
                                      v
                              background worker
                                      |
                                format / write
                                      |
                              file / stdout / network
                                      |
                                collector / index
```

Điểm phân biệt cốt lõi:

- **Giảm caller latency:** lời gọi `logger.info(...)` thường không phải chờ sink hoàn thành mỗi event trong điều kiện queue còn chỗ và xử lý producer nhẹ.
- **Không bảo đảm end-to-end latency thấp hơn:** log có thể phải nằm trong hàng đợi lâu, chờ I/O, chờ ship hoặc chờ index; lúc quá tải producer vẫn có thể bị chặn.
- **Không đồng nghĩa durable:** việc enqueue thành công thường mới là nhận event trong bộ nhớ. Process crash, shutdown không hoàn chỉnh hoặc sink/collector lỗi có thể làm mất log chưa kịp xử lý.

Một số framework phân biệt **AsyncAppender** (đẩy việc gọi appender khác sang worker) và **AsyncLogger** (thiết kế pipeline async riêng, chẳng hạn Disruptor của Log4j 2). Hai cách đều có hàng đợi và cơ chế quá tải; cấu hình và đặc điểm chi phí khác nhau theo implementation.

## 2. Các loại latency cần đo đúng ranh giới

Một sự kiện log đi qua nhiều mốc:

```text
t0                    t1               t2                  t3             t4           t5
| logger call begins | producer returns | worker picks event | sink completed | collector ack | searchable
       ^-- caller --^
       ^----------- dispatch/pickup -----------^
       ^---------------- appender path --------------------^
       ^---------------------- end-to-end visibility --------------------------^
```

Ký hiệu:

| Chỉ số | Ranh giới đo | Ý nghĩa |
| --- | --- | --- |
| **Caller latency / enqueue latency** | `t1 - t0` | Thời gian lời gọi logging giữ luồng nghiệp vụ; gồm capture, preprocess, enqueue và thời gian bị block khi queue đầy. |
| **Time to pickup** | `t2 - t0` | Từ lúc bắt đầu log đến worker nhận event; gồm cả thời gian producer có thể chờ chỗ trống và chờ trong queue. |
| **Queue residence time** | Từ lúc event **thực sự vào queue** đến lúc worker lấy ra | Phản ánh backlog trong queue, khác với toàn bộ thời gian producer chờ enqueue. Cần instrumentation phù hợp để đánh dấu mốc chính xác. |
| **Sink processing latency** | `t3 - t2` | Thời gian worker xử lý/format/ghi tới sink; phụ thuộc I/O, lock và batch. |
| **Collector/index latency** | `t5 - t3`, nếu có | Thời gian ship, tiếp nhận và index để truy vấn được. |
| **End-to-end visibility latency** | `t5 - t0` | Người vận hành phải chờ bao lâu từ sự kiện đến lúc tìm được log. |

Chỉ số “ghi xong” cũng cần định nghĩa rõ. `FileOutputStream.write` hoặc một appender hoàn tất có thể mới chuyển byte sang OS cache, **không nhất thiết đã fsync xuống đĩa**. Network send thành công cũng không chứng minh collector đã lưu/index vững bền. Nếu mục tiêu là **độ bền dữ liệu**, phải xác định riêng mốc xác nhận bền vững; không lấy thời gian logger trả về làm thời gian durable.

Ở cùng một JVM, dùng `System.nanoTime()` để đo **khoảng thời gian** (elapsed time). Dùng timestamp thời gian thực như `Instant.now()` để đối chiếu sự kiện và log pipeline; khi so mốc ở nhiều máy phải tính đến clock skew, đồng bộ thời gian, timestamp do agent/collector tạo và sai số do batch.

Một bất đẳng thức thường đúng với cùng một event là: thời điểm sink hoàn thành không thể trước thời điểm worker nhận event. Tuy nhiên, thời gian caller kết thúc và worker bắt đầu có thể xen kẽ: worker có thể lấy event ngay trước khi thread producer kịp thực thi lệnh kế tiếp sau `offer/put`.

## 3. Điều gì làm async logging chậm?

### 3.1. Chi phí trên luồng producer

Dù async, producer vẫn có thể phải kiểm tra log level, evaluate đối số Java, tạo event, chụp timestamp/Thread name/MDC, xác định stack trace/caller data và publish vào queue. Ví dụ:

```java
logger.debug("result=" + expensiveComputation());
```

Biểu thức `expensiveComputation()` được Java thực thi trước khi gọi logger, kể cả khi mức DEBUG đang tắt. Parameterized logging như `logger.debug("result={}", value)` tránh nối chuỗi sớm, nhưng giá trị truyền vào vẫn phải được tính. Nếu tính toán rất tốn kém, nên kiểm tra `logger.isDebugEnabled()` hoặc dùng cơ chế lazy supplier nếu framework hỗ trợ đúng mục đích. Async không làm biến mất chi phí sinh dữ liệu log.

Việc ghi stack trace lớn, serialize object nặng, copy MDC hoặc caller location làm producer chậm hơn dự kiến; một phần chi phí thuộc producer hay worker phụ thuộc logging framework và cấu hình.

### 3.2. Queue và tốc độ phục vụ

Giả sử producer tạo trung bình **λ** log event/giây, trong khi worker/sink xử lý trung bình **μ** event/giây.

- Nếu `λ < μ` trong điều kiện tải ổn định và không có burst lớn, backlog có thể được giải phóng.
- Nếu `λ ≈ μ`, một đợt tăng tải ngắn hoặc I/O chậm có thể làm p99 queue wait tăng rất mạnh.
- Nếu `λ > μ` trong thời gian đủ lâu, hàng đợi tăng đến giới hạn (nếu bounded). Sau đó cơ chế **block, drop, fallback synchronous hoặc reject** quyết định hành vi thực tế, tùy implementation.

Ví dụ giả định sink xử lý 4.000 event/s nhưng producer tạo 5.000 event/s trong một đợt tăng tải. Backlog tăng xấp xỉ 1.000 event/s. Queue đang trống với sức chứa 2.000 event sẽ đầy sau khoảng 2 giây nếu tốc độ giữ nguyên; đây là mô hình đơn giản, chưa tính burst, độ biến thiên và overhead. Tăng queue size chỉ **trì hoãn thời điểm đầy**; không sửa nguyên nhân nếu tốc độ tiêu thụ thấp hơn tốc độ sinh log kéo dài.

Định luật Little trong trạng thái ổn định cho `L = λ × W`: `L` là số event trung bình đang chờ/xử lý trong phạm vi đo, `λ` là throughput hiệu dụng, `W` là thời gian trung bình trong phạm vi đó. Không áp dụng máy móc khi hệ thống đang overflow hoặc khi số liệu bao gồm các event đã bị drop. Ví dụ nếu trung bình có 500 event chờ queue và throughput là 1.000 event/s, thời gian chờ trung bình tương ứng khoảng 0,5 giây trong điều kiện hệ thống ổn định.

### 3.3. Tác nhân gây long-tail latency

- **Slow sink:** ghi console trong container, file trên ổ mạng, fsync/flush, rolling/rotation file, disk saturation, stdout collector bị nghẽn, network timeout hoặc logging backend chậm.
- **Burst:** số request/log theo đợt lớn hơn tốc độ worker, nhất là log debug ở vòng lặp hoặc khi lỗi hàng loạt.
- **CPU/GC:** encode JSON, format exception, cấp phát object/byte array, GC pause hoặc cạnh tranh CPU khiến producer và worker không được lịch chạy đều.
- **Lock/coordination:** nhiều producer cạnh tranh để publish, một worker bị serialize tại appender hoặc contention trên appender chung.
- **Batching:** sink gom nhiều log để gửi một lần giúp throughput nhưng có thể tăng thời gian chờ của event cuối batch hoặc event ít tải.
- **Pipeline phía sau:** collector retry, agent backlog, broker, ingest pipeline và index refresh làm log có trong file nhưng chưa truy vấn được.

**Async không biến I/O chậm thành I/O nhanh.** Nó chuyển thời điểm chịu chi phí sang worker và hấp thụ burst trong một giới hạn. Với log volume quá lớn, việc giảm chi phí log không cần thiết và tăng năng lực sink mới giải quyết được tải bền vững.

## 4. Backpressure: phải chọn chính sách khi queue đầy

Hàng đợi bounded có sức chứa hữu hạn, giúp giới hạn bộ nhớ. Khi đầy, thường có các chiến lược:

| Cách xử lý | Tác động đến caller latency | Tác động đến log |
| --- | --- | --- |
| **Block/put chờ chỗ trống** | Caller có thể phải chờ lâu, thậm chí làm chậm endpoint | Giảm nguy cơ mất event tại queue nhưng không loại bỏ lỗi sink/shutdown. |
| **Drop event mới** | Caller trả về nhanh | Mất một phần log; cần counter cảnh báo và chính sách log level. |
| **Drop event ít quan trọng** | Giữ log ưu tiên cao hơn, có thể giảm độ trễ trung bình | Chấp nhận mất DEBUG/INFO; không được hiểu là mọi event đều đã lưu. |
| **Fallback ghi đồng bộ** | Caller đột ngột chịu I/O, p99 có thể tăng cao | Có cơ hội ghi ngay nhưng vẫn có thể thất bại nếu sink lỗi. |
| **Reject/báo lỗi** | Caller thấy lỗi hoặc phải xử lý retry | Tùy framework và chính sách, có thể ảnh hưởng nghiệp vụ. |

Không có chiến lược đúng cho mọi ứng dụng. Với log debug hoặc thống kê có thể tái tạo, chấp nhận drop có kiểm soát kèm metric có thể hợp lý. Với audit bắt buộc hoặc event quan trọng cho nghiệp vụ, logging thông thường có hàng đợi trong RAM không cung cấp đảm bảo lưu trữ; cần thiết kế đường lưu durable riêng theo yêu cầu (transactional outbox, message broker bền vững, audit store...) nếu thực sự cần.

**Cảnh báo vận hành:** Cấu hình "never block" giảm độ trễ producer trong một số tình huống, đổi lại event có thể mất khi đầy. Cấu hình "never drop" thường đồng nghĩa producer có thể block, và process crash vẫn có thể mất event trong RAM. Luôn kiểm thử chính sách chính xác của framework và phiên bản đang dùng.

## 5. Ví dụ Java 17: đo caller latency và thời gian xử lý nền

Chương trình thuần JDK bên dưới mô phỏng một async log pipeline có queue bounded và một worker chậm. Nó đo ba khoảng thời gian theo từng event:

- `callerNs`: từ trước `queue.put` đến khi `put` trả về; khi queue đầy, nó bao gồm thời gian chờ chỗ trống.
- `pickupNs`: từ lúc ứng dụng bắt đầu phát event đến khi worker `take`; bao gồm enqueue blocking **và** queue residence, nên không gọi đây là riêng queue residence.
- `sinkDoneNs`: từ lúc phát event đến sau khi worker giả lập xử lý xong; **không** đại diện cho thời gian log tới hệ thống index.

Chương trình cố ý dùng `Thread.sleep(4)` để mô phỏng sink chậm, không dùng `System.out.println` cho từng event vì việc in ra console có thể làm lệch thí nghiệm. Thời gian sẽ biến động theo OS/JVM, nên chỉ các dòng đếm và kiểm tra được coi là output bất biến.

Tạo file **`AsyncLoggingLatencyDemo.java`**:

```java
import java.util.Arrays;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.atomic.AtomicInteger;

public class AsyncLoggingLatencyDemo {
    private record Event(int id, long startedNs) {}

    private static long percentile(long[] sortedNs, int percent) {
        int rank = (int) Math.ceil(sortedNs.length * percent / 100.0);
        return sortedNs[Math.max(0, rank - 1)];
    }

    private static double milliseconds(long nanoseconds) {
        return nanoseconds / 1_000_000.0;
    }

    public static void main(String[] args) throws InterruptedException {
        final int total = 40;
        BlockingQueue<Event> queue = new ArrayBlockingQueue<>(8);
        long[] callerNs = new long[total];
        long[] pickupNs = new long[total];
        long[] sinkDoneNs = new long[total];
        AtomicInteger processed = new AtomicInteger();

        Thread worker = new Thread(() -> {
            try {
                for (int i = 0; i < total; i++) {
                    Event event = queue.take();
                    pickupNs[event.id()] =
                            System.nanoTime() - event.startedNs();

                    Thread.sleep(4); // mô phỏng sink xử lý 1 event

                    sinkDoneNs[event.id()] =
                            System.nanoTime() - event.startedNs();
                    processed.incrementAndGet();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "async-log-writer");

        worker.start();

        for (int i = 0; i < total; i++) {
            long startedNs = System.nanoTime();
            queue.put(new Event(i, startedNs));
            callerNs[i] = System.nanoTime() - startedNs;
        }

        worker.join();

        if (processed.get() != total) {
            throw new IllegalStateException("Worker did not drain queue");
        }

        Arrays.sort(callerNs);
        Arrays.sort(pickupNs);
        Arrays.sort(sinkDoneNs);

        System.out.println("processed=" + processed.get());
        System.out.println("queueEmpty=" + queue.isEmpty());
        System.out.println("samples=" + callerNs.length);

        System.out.printf("caller_p95_ms=%.3f%n",
                milliseconds(percentile(callerNs, 95)));
        System.out.printf("pickup_p95_ms=%.3f%n",
                milliseconds(percentile(pickupNs, 95)));
        System.out.printf("sink_done_p95_ms=%.3f%n",
                milliseconds(percentile(sinkDoneNs, 95)));
    }
}
```

Biên dịch và chạy bằng **JDK 17+**:

```bash
javac AsyncLoggingLatencyDemo.java
java AsyncLoggingLatencyDemo
```

Ba dòng đầu tiên của **stdout** luôn là:

```text
processed=40
queueEmpty=true
samples=40
```

Ba dòng tiếp theo có dạng `caller_p95_ms=...`, `pickup_p95_ms=...`, `sink_done_p95_ms=...` với số đo thực tế khác nhau giữa các lần chạy; không thể đưa ra một số mili giây cố định cho các dòng đó. `percentile` dùng nearest-rank: sắp tăng dần rồi lấy phần tử ở vị trí `ceil(p × N / 100)` (đếm từ 1), một cách ước lượng đơn giản phù hợp để minh họa; công cụ monitoring thực tế có thể dùng histogram hoặc thuật toán quantile khác.

Cách đọc kết quả:

1. Khi queue còn chỗ, `put` thường kết thúc nhanh. Khi sink chậm và queue đầy, nhiều lệnh `put` có thể chờ, làm p95 caller tăng lên.
2. `pickup_p95_ms` cho biết độ trễ từ lúc phát event đến khi worker nhận, bao gồm cả producer block. Để đo **queue residence riêng**, cần đặt timestamp đúng thời điểm event đã thực sự được publish vào queue, với instrumentation an toàn dưới concurrency.
3. `sink_done_p95_ms` còn bao gồm việc worker xử lý. Nó chưa tính collector, log shipping và index.
4. Tăng `Thread.sleep(4)` lên `Thread.sleep(20)` thường làm backlog/caller blocking tăng; kết quả đo không có một tỉ lệ cố định vì scheduler và tải máy khác nhau.
5. Tăng queue capacity sẽ hấp thụ burst dài hơn, nhưng không làm worker xử lý nhanh hơn; khi sink liên tục quá chậm thì vẫn có backlog và tăng bộ nhớ.

Đây là **mô phỏng có thể chạy độc lập**, không phải logger production. Trong thực tế, dùng telemetry của appender và hệ thống thu thập log để đo pipeline tương ứng. Đừng biến bảng số của ví dụ thành latency target.

## 6. Đọc percentiles cho đúng

Vì log events thường có phân phối lệch, trung bình có thể che các đợt bị chậm. Theo dõi **p50, p95, p99** cho caller latency và end-to-end latency trên cùng một time window, kèm số mẫu và tỷ lệ drop. Ví dụ:

| Metric | p50 | p95 | p99 | Ý nghĩa giả định |
| --- | ---: | ---: | ---: | --- |
| `log_call_ms` | 0,04 ms | 0,2 ms | 18 ms | Phần lớn lời gọi nhanh, nhưng 1% tail chịu chặn/GC/contended path. |
| `pickup_delay_ms` | 2 ms | 80 ms | 900 ms | Worker bị backlog ở một số thời điểm. |
| `log_visibility_ms` | 150 ms | 1.400 ms | 8.000 ms | Shipping/indexing cũng đóng góp vào độ trễ quan sát. |

Các số trên **chỉ là ví dụ minh họa**, không phải benchmark của Logback/Log4j 2 hay cam kết hệ thống. Thời điểm đo phải tương đương để so sánh hợp lý; p99 từ cửa sổ rất ít mẫu có thể dao động mạnh. Nếu một tỷ lệ log đã bị drop, quantile tính **chỉ trên những event còn lại** có thể trông tốt giả tạo; hãy luôn báo thêm `dropped_count` và `drop_rate`.

**Không cộng các p99 của từng giai đoạn rồi gọi là p99 end-to-end.** Percentile không cộng tuyến tính: các event gây tail ở từng giai đoạn có thể khác nhau. Tốt hơn là gắn timestamp hoặc ID để đo end-to-end per event hoặc dùng telemetry có tương quan event đúng.

Đặt SLO theo mục tiêu sử dụng: ví dụ minh họa “p99 lời gọi log < 10 ms khi tải mục tiêu, 99% log đã nhận xuất hiện trong 5 giây, tỷ lệ drop < 0,01%”. Đây là ví dụ để thiết kế phép đo; giá trị phù hợp tùy loại log, chi phí hạ tầng và mức độ quan trọng, không phải ngưỡng chung cho Java.

## 7. Cấu hình Logback AsyncAppender trong Java

Với ứng dụng sử dụng **SLF4J + Logback**, `ch.qos.logback.classic.AsyncAppender` dùng hàng đợi hữu hạn và worker để chuyển event tới appender đích. Ví dụ cấu hình **`logback.xml`**:

```xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/app.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} [%thread] %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>2048</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <includeCallerData>false</includeCallerData>
        <maxFlushTime>10000</maxFlushTime>
        <appender-ref ref="FILE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

Cần thêm dependency Logback/SLF4J tương thích vào ứng dụng; file XML trên **không chạy chỉ bằng JDK**. Đường dẫn `logs/app.log` phải ghi được. Ý nghĩa các thuộc tính trong Logback Classic:

- `queueSize=2048`: sức chứa queue theo event, không phải byte. Tăng quá lớn làm tăng bộ nhớ và thời gian chờ của event cuối backlog.
- `discardingThreshold=0`: vô hiệu cơ chế loại các mức log ít quan trọng theo ngưỡng còn chỗ của AsyncAppender. Với cấu hình mặc định, Logback Classic có thể bỏ TRACE/DEBUG/INFO khi queue gần đầy (ngưỡng thường tương đương khoảng 20% sức chứa còn lại). Cần kiểm tra hành vi của phiên bản đang dùng.
- `neverBlock=false`: khi không thể enqueue, producer được phép chờ thay vì chọn nhánh non-blocking drop. Điều này có thể làm p95/p99 của endpoint tăng khi sink chậm; không phải cam kết end-to-end zero loss.
- `includeCallerData=false`: tránh chi phí tính source location trên đường nóng. Nếu cần class/method/line của caller, bật sau khi cân nhắc overhead và đo lại.
- `maxFlushTime=10000`: khi stop, AsyncAppender dành tối đa khoảng 10 giây để chờ worker drain queue; nếu hết thời gian hoặc process bị kill trước đó, có thể còn event chưa được ghi. Trong Logback, giá trị `0` thường có nghĩa chờ vô hạn lúc stop; chính sách shutdown phải xét mục tiêu vận hành.

Trong Logback, event thường phải “prepare for deferred processing” trước khi qua worker: thông tin cần thiết như thread name và MDC được capture ở thời điểm phù hợp, vì context của producer có thể không còn khi worker xử lý. Nếu cần caller data, làm điều đó ở producer có thể tăng caller latency. Các phiên bản/framework có chi tiết khác nhau; hãy đo trên cấu hình sử dụng thật.

Để so sánh các cấu hình:

1. Giữ nguyên log volume, cấu hình sink, máy, định dạng và thời gian thử.
2. Đo sync baseline: throughput và p50/p95/p99 của endpoint lẫn log call, mức sử dụng CPU và disk.
3. Bật AsyncAppender; đo lại cả caller latency, queue depth, throughput, drop và end-to-end visibility.
4. Tạo burst vượt mức xử lý; xác nhận thực tế là **block, discard hay fallback** theo cấu hình, và có cảnh báo khi queue đầy.
5. Cho shutdown có graceful termination; kiểm chứng queue drain theo ngân sách thời gian và đối chiếu số event phát/đã ghi.

Nếu hệ thống ghi stdout trong container, async appender chỉ chuyển thời gian ghi stdout sang worker; stdout runtime, log agent và log backend phía sau vẫn có thể chậm hoặc mất dữ liệu. Mọi benchmark phải gắn với đường đi log thực tế.

## 8. Log4j 2 AsyncLogger và Disruptor

Log4j 2 có cơ chế **AsyncLogger** sử dụng cấu trúc ring buffer dựa trên LMAX Disruptor, bên cạnh **AsyncAppender**. AsyncLogger và AsyncAppender không phải cùng một loại cấu hình hay có hành vi giống nhau ở mọi phiên bản. Ring buffer giúp giảm một số contention/chi phí publish trong điều kiện phù hợp, nhưng vẫn có sức chứa hữu hạn và cần chính sách khi buffer đầy.

Các điểm cần xác minh theo phiên bản Log4j 2, tùy chọn cấu hình và cách triển khai:

- Kích thước ring buffer và mức chiếm dụng thực tế.
- Chiến lược `wait`, `block`, ghi đồng bộ hoặc discard khi buffer đầy.
- Log location/caller data có được capture không và overhead trên producer.
- Hành vi khi appender đích chậm, khi gặp exception và khi shutdown.
- Tải thực tế, phân phối độ trễ tail và log loss.

Không kết luận “AsyncLogger luôn nhanh hơn AsyncAppender” hoặc copy cấu hình giữa hai framework mà không kiểm thử. Nếu dùng cấu hình AsyncLogger toàn cục hay mix sync/async, kiểm tra dependency Disruptor, context selector/cấu hình tương ứng trong tài liệu chính thức của **phiên bản Log4j 2 đang chạy**. Chỉ benchmark khi khởi tạo framework đúng chế độ async dự định.

## 9. Đo đạc và benchmark có ý nghĩa

Một phép đo đáng tin cần trả lời: **log gì, ở tải nào, qua sink nào, mất bao nhiêu, và tác động gì đến nghiệp vụ?**

### Bộ chỉ số nên có

| Nhóm | Metric gợi ý | Mục đích |
| --- | --- | --- |
| Producer | `log_call_duration` p50/p95/p99, blocked enqueue duration | Phát hiện log làm chậm business thread. |
| Queue | queue depth, capacity, high-water mark, occupancy %, thời gian chờ | Đo backlog và khoảng dự phòng trước khi đầy. |
| Consumer/sink | events processed/s, sink write duration, bytes/s, errors/retries | Phân biệt producer tạo nhiều log với sink xử lý chậm. |
| Data integrity | emitted/accepted/written/dropped counts và drop rate | Biết hiệu năng đạt được bằng cách giữ hay bỏ log. |
| Pipeline | event-to-collector, event-to-searchable, ingest lag | Đo lúc vận hành viên thực sự tra cứu được log. |
| Runtime | CPU, GC pauses, allocation, I/O wait, file rotate, throttling | Tìm nguyên nhân gây tail latency. |

Tên metric thực tế phụ thuộc framework. Nếu framework không công bố queue depth/dropped count, cần dùng cơ chế instrumentation được hỗ trợ, MBean/metrics appender hoặc đo ở cấp ứng dụng/sink. Không nên viết instrumentation tốn nhiều lock hoặc tạo thêm log cho mỗi event; chính monitoring cũng có overhead.

### Kịch bản test

- **Steady state:** chạy tải đủ lâu để warm up JIT, tạo log bằng phân phối kích thước/số lượng sát thực tế, đo latency và throughput.
- **Burst:** tăng ngắn hạn số lượng log; đo queue high-water và thời gian hồi phục.
- **Saturation:** sink xử lý chậm hơn producer; đo block duration/drop và hiệu ứng tới p99 endpoint.
- **Failure/recovery:** giả lập disk full, permission denied, collector unreachable, network retry hoặc file rotation; xác nhận visibility/durability policy.
- **Shutdown/crash:** so số event đã phát, queue còn lại và thực sự đến sink; graceful shutdown khác force-kill.
- **Content mix:** log vài byte, JSON dài, exception stack trace, MDC và các log levels; đo allocation/CPU/GC.

Giữ các điều kiện thử công bằng: log level, kích thước event, số producer, cấu hình queue/sink và tài nguyên máy tương đương. Dùng profiler/metrics thay vì chỉ dựa trên tốc độ vòng lặp `logger.info`; benchmark đo producer throughput có thể trông cao nhờ drop nhiều event hoặc để backlog chưa drain khi kết thúc.

### Chọn queue size

Ước lượng sơ bộ dung lượng theo số event cần hấp thụ trong burst, tốc độ sink drain và bộ nhớ sẵn có. Ví dụ queue 10.000 event với event giữ trung bình 2 KiB dữ liệu tương đương khoảng 20 MiB **riêng payload tham khảo**; thực tế heap có thêm object headers, references, layout/message buffers, retained parameters và cấu trúc queue. Nên đo heap dưới payload thật.

Mô hình `burst arrival - consumer capacity` chỉ là điểm bắt đầu. Nếu yêu cầu p99 visibility thấp, queue quá lớn có thể khiến event chờ lâu hơn; để tăng năng lực ổn định cần tối ưu sink, giảm log không cần thiết, batch/ship phù hợp hoặc tăng năng lực tiêu thụ chứ không chỉ tăng queue.

## 10. Tình huống chẩn đoán thực tế

**Tình huống A — HTTP endpoint chậm bất thường dù đã dùng AsyncAppender.** Kiểm tra p99 log call, queue occupancy và blocked enqueue. Nếu queue gần đầy liên tục, producer bị backpressure theo `neverBlock=false`. Kiểm tra nguyên nhân sink chậm, giảm log volume, tối ưu appender/disk hoặc điều chỉnh chính sách; đừng vội tăng queue vô hạn.

**Tình huống B — endpoint nhanh nhưng log xuất hiện trễ vài giây.** Caller latency thấp chỉ chứng minh enqueue nhanh. So event timestamp, queue wait, file append, log agent shipping và index ingest lag. Nếu file đã có event ngay nhưng search backend chậm, nút thắt nằm sau JVM logging.

**Tình huống C — p99 “đẹp” nhưng thiếu log lỗi.** Kiểm tra configured discarding, `neverBlock`, drop counter, log level/filters, exception appender và shutdown. p99 chỉ tính trên các event thành công có thể che log bị mất. Đối chiếu count bằng event ID riêng trong môi trường thử, không dùng Trace ID làm counter.

**Tình huống D — log bị dồn sau GC pause.** GC làm producer/worker tạm ngừng, event sau đó có thể đến queue thành burst. Ghép biểu đồ queue depth và caller/visibility p99 với GC pauses, allocations, CPU throttle và I/O saturation để xác nhận tương quan.

**Tình huống E — crash làm mất vài dòng log cuối.** Async queue nằm trong memory; worker chưa kịp drain thì process dừng. Cấu hình shutdown hook/graceful stop và `maxFlushTime` phù hợp giúp giảm rủi ro khi shutdown bình thường, nhưng không thay được cơ chế durable log store khi yêu cầu không mất dữ liệu.

## 11. Checklist triển khai và hiểu đúng kết quả

1. Ghi rõ SLO: độ trễ của `logger.info`, thời gian log có ở file, thời gian collector nhận hay thời gian có thể search? Mức chấp nhận drop và dữ liệu cần bền vững là gì?
2. Đo baseline sync/async trên workload thật; thu p50/p95/p99, throughput, queue occupancy, drop và endpoint latency. Kết quả phải đo đến khi queue drain nếu so log processing.
3. Xem nguồn nghẽn: format/capture, queue, worker, file/stdout, collector hay index. Sửa đúng đoạn có backlog.
4. Đặt queue bounded dựa trên burst và RAM, đồng thời quyết định rõ chiến lược quá tải. Đừng đánh đổi loss để có biểu đồ latency đẹp mà không ghi nhận.
5. Kiểm tra xử lý shutdown và crash riêng, vì log đã enqueue khác log đã lưu bền vững.
6. Thiết lập cảnh báo queue occupancy cao kéo dài, drop > ngưỡng, worker errors và event-to-searchable lag. Kiểm thử failure path định kỳ.
7. Nếu cần gắn log vào trace, capture trace context/MDC ở thời điểm đúng và xác nhận event bất đồng bộ không mang nhầm context từ thread khác.

**Điểm cần nhớ:** Async logging thường giúp luồng nghiệp vụ thoát lời gọi log sớm hơn trong điều kiện thuận lợi, nhưng hàng đợi và sink vẫn phải xử lý đủ sự kiện. Muốn đánh giá “độ trễ async logging”, cần đo cả **caller latency**, **thời gian chờ/bị chặn**, **thời gian tới sink/collector/index**, **drop rate** và **tính bền vững** theo yêu cầu thực tế.

## Tài liệu tham khảo

- [Logback — AsyncAppender](https://logback.qos.ch/manual/appenders.html#AsyncAppender) — queue, discarding threshold, neverBlock và maxFlushTime.
- [Apache Log4j 2 — Asynchronous Loggers](https://logging.apache.org/log4j/2.x/manual/async.html) — AsyncLogger, AsyncAppender, ring buffer và tradeoff.
- [Java 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html) — `put`, `take`, `offer` và semantics chờ.
- [Java 17 — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()) — đo elapsed time trong một JVM.
