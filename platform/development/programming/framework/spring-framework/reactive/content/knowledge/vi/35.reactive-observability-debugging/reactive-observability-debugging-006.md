# Quan sát Scheduler, hàng đợi, pool kết nối và bộ đệm trong Spring WebFlux

## 1. Mục tiêu và tư duy quan sát

Một ứng dụng Spring WebFlux có thể tiếp nhận nhiều request đồng thời mà không cần một thread riêng cho mỗi request. Nhưng non-blocking không có nghĩa là tài nguyên vô hạn hoặc không thể bị nghẽn. Một pipeline có thể chậm vì CPU bão hòa, Scheduler hết worker, hàng đợi tích lũy, connection pool cạn, database phản hồi chậm, client đọc quá chậm hoặc buffer được giữ quá lâu.

**Observability** là khả năng hiểu trạng thái bên trong hệ thống qua metrics, logs và traces. Với reactive system, cần nhìn theo từng tầng:

1. HTTP request: lưu lượng, latency, status và lỗi.
2. Reactor pipeline: subscription, thời gian sống, demand, cancellation và lỗi.
3. Scheduler: tác vụ đang chạy, tác vụ chờ và tốc độ hoàn thành.
4. Queue: độ sâu, sức chứa, thời gian chờ và số tác vụ bị từ chối.
5. Connection pool: kết nối đang dùng, nhàn rỗi, đang chờ và thời gian acquire.
6. Memory/buffer: heap, direct memory, Netty allocator và dấu hiệu leak.
7. Database/downstream: query latency, timeout, lock, retry và giới hạn của dịch vụ phụ thuộc.

Sau bài học này, bạn có thể chọn metric đúng cho từng tài nguyên, bật Reactor/Micrometer metrics, đọc R2DBC và Reactor Netty pool metrics, quan sát buffer, xây dashboard/alert, chẩn đoán một số triệu chứng thường gặp và triển khai demo Spring Boot WebFlux Java 17+.

**Nguyên tắc:** một con số đơn lẻ hiếm khi giải thích được sự cố. Hãy đối chiếu lưu lượng, latency p95/p99, pending work, throughput, lỗi và mức sử dụng tài nguyên trong cùng một khoảng thời gian.

## 2. Bốn khái niệm cần phân biệt

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| Metrics | Bao nhiêu, nhanh/chậm thế nào, xu hướng ra sao? | request/s, p99, pending connections |
| Logs | Sự kiện cụ thể nào vừa xảy ra? | request timeout, pool acquire failed |
| Traces | Một request đi qua những service/span nào? | HTTP → service → database → remote API |
| Profiling/diagnostics | CPU, allocation, lock hoặc thread đang tiêu tốn ở đâu? | JFR, thread dump, heap dump, async-profiler |

Metrics phù hợp để dashboard và alert theo thời gian. Logs giữ chi tiết sự kiện và context. Distributed traces giúp tìm span chậm trong request xuyên nhiều service. Profiling giúp xác định nguyên nhân sâu như vòng lặp CPU, lock contention, allocation cao hoặc blocking call.

Không ghi mọi payload vào logs để “quan sát đầy đủ”. Payload có thể chứa token, thông tin cá nhân hoặc dữ liệu nhạy cảm. Hãy log correlation ID, route template, operation, status, loại lỗi và thời lượng; chỉ thêm dữ liệu đã được phép và đã redaction.

## 3. Luồng tài nguyên trong một request WebFlux

~~~text
HTTP client
    |
    v
Reactor Netty event loop
    |
    v
WebFlux controller / service
    |
    +------> Reactor Scheduler (nếu pipeline chuyển scheduler)
    |
    +------> R2DBC Connection Pool
    |             |
    |             v
    |          Database
    |
    +------> WebClient Connection Pool
    |             |
    |             v
    |          Remote service
    |
    +------> Application queue / buffer
                  |
                  v
              Consumer
~~~

Event loop xử lý I/O và callback ngắn. Không chạy JDBC/JPA, file I/O blocking hoặc tính toán CPU nặng trên event loop. Nếu cần cô lập một API blocking chưa thể thay thế, dùng Scheduler thích hợp và giới hạn concurrency/queue. Nếu công việc là CPU-bound, dùng parallel Scheduler hoặc executor CPU được sizing theo số core; không đưa mọi công việc vào boundedElastic.

Mỗi pool và queue đều có giới hạn. Khi consumer xử lý chậm hơn producer, công việc có thể chờ, bị từ chối, bị drop hoặc làm tăng memory. Phải chọn overflow/backpressure policy có chủ đích.

## 4. Metrics nền tảng của Spring Boot Actuator

Thêm Actuator và một registry phù hợp để xuất metrics:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Spring Boot dùng Micrometer làm facade metrics. Tùy dependency và cấu hình, các meter có thể được xuất tới Prometheus, OTLP, Datadog, New Relic hoặc backend khác.

Các metric thường cần có:

| Nhóm | Meter thường gặp | Ý nghĩa |
| --- | --- | --- |
| HTTP server | `http.server.requests` | số lượng và thời gian xử lý request theo route/status |
| JVM heap | `jvm.memory.used`, `jvm.memory.max` | heap đã dùng và giới hạn |
| JVM buffer | `jvm.buffer.count`, `jvm.buffer.memory.used` | số lượng và bộ nhớ của JVM buffer pool |
| GC | `jvm.gc.pause` | thời gian pause GC |
| Threads | `jvm.threads.live`, `jvm.threads.peak` | thread đang sống và peak |
| Process/system | `process.cpu.usage`, `system.cpu.usage` | CPU của process và host |
| Application | metric tự định nghĩa | queue depth, rejected work, business latency |

`/actuator/metrics` dùng để xem danh sách meter và chẩn đoán một meter cụ thể. Endpoint này không phải backend để Prometheus scrape liên tục. Với Prometheus, dùng `/actuator/prometheus` và registry tương ứng.

Cấu hình minh họa:

~~~properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.tags.application=reactive-observability-lab
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.slo.http.server.requests=50ms,100ms,250ms,500ms,1s
~~~

Chỉ expose các endpoint cần thiết. Trong production, giới hạn mạng và áp dụng authentication/authorization cho Actuator. Không mở tất cả endpoint ra Internet. Tên meter trong `/actuator/metrics` dùng dạng Micrometer như `jvm.memory.used`; Prometheus có thể chuyển tên sang dạng snake_case.

## 5. Quan sát Reactor Scheduler

Scheduler quyết định tác vụ được thực thi ở đâu. Những lựa chọn phổ biến:

| Scheduler | Mục đích | Lưu ý |
| --- | --- | --- |
| `Schedulers.parallel()` | CPU-bound work ngắn | Không dùng cho blocking I/O |
| `Schedulers.boundedElastic()` | Cô lập blocking work | Có giới hạn thread và queue |
| `Schedulers.single()` | Một worker thread dùng chung | Một tác vụ chậm có thể làm các tác vụ khác chờ |
| `Schedulers.immediate()` | Chạy trên thread hiện tại | Không tạo thread mới |
| `Schedulers.newParallel(...)` | Scheduler CPU riêng | Cần dispose khi không dùng |
| `Schedulers.newBoundedElastic(...)` | Scheduler blocking riêng với giới hạn | Chọn thread cap và queue cap theo workload |

Một request có thể đổi thread qua `publishOn` hoặc `subscribeOn`. Vì vậy không suy luận lifecycle của request chỉ từ tên thread hiện tại. Hãy đo Scheduler cụ thể mà ứng dụng chủ động sử dụng.

### 5.1. Dùng Micrometer.timedScheduler

Với Reactor hiện đại, module `reactor-core-micrometer` cung cấp wrapper đo Scheduler:

~~~groovy
implementation 'io.projectreactor:reactor-core-micrometer'
~~~

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import reactor.core.observability.micrometer.Micrometer;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
class SchedulerConfiguration {

    @Bean(destroyMethod = "dispose")
    Scheduler observedIoScheduler(MeterRegistry registry) {
        Scheduler delegate =
            Schedulers.newBoundedElastic(4, 100, "observed-io");

        return Micrometer.timedScheduler(
            delegate,
            registry,
            "app.io"
        );
    }
}
~~~

Tên metric dùng prefix đã truyền vào, ví dụ `app.io.scheduler.tasks.completed`. Các meter quan trọng:

| Meter | Loại | Ý nghĩa |
| --- | --- | --- |
| `app.io.scheduler.tasks.active` | LongTaskTimer | tác vụ đang hoạt động, gồm cả tác vụ delayed/periodic |
| `app.io.scheduler.tasks.completed` | Timer | thời gian thực thi các tác vụ đã hoàn thành |
| `app.io.scheduler.tasks.pending` | LongTaskTimer | tác vụ immediate không thể bắt đầu ngay vì Scheduler đã đạt capacity |
| `app.io.scheduler.tasks.submitted` | Counter | số lần submit, có tag phân loại kiểu submission |

**Điểm rất quan trọng:** wrapper chỉ instrument các Runnable được submit qua chính Scheduler trả về từ `Micrometer.timedScheduler`. Nếu code tiếp tục dùng `Schedulers.parallel()` hoặc một Scheduler khác, những tác vụ đó không tự động xuất hiện dưới prefix `app.io`.

`tasks.pending` không phải gauge cho toàn bộ queue depth. Nó mô tả những tác vụ immediate đã submit nhưng không thể bắt đầu ngay theo semantics của wrapper. Để biết độ sâu queue ứng dụng, hãy tự instrument queue ở tầng ứng dụng.

`Schedulers.enableMetrics()` là API cũ đã deprecated; ưu tiên wrapper tường minh `Micrometer.timedScheduler`. Không gọi API cũ chỉ vì thấy ví dụ từ Reactor đời trước.

### 5.2. Gắn Scheduler vào pipeline

~~~java
@Service
class WorkService {
    private final Scheduler ioScheduler;
    private final MeterRegistry registry;

    WorkService(
            Scheduler observedIoScheduler,
            MeterRegistry registry) {
        this.ioScheduler = observedIoScheduler;
        this.registry = registry;
    }

    Flux<Integer> calculate(int count) {
        return Flux.range(1, count)
            .flatMapSequential(value ->
                Mono.fromCallable(() -> {
                    // Mô phỏng một API blocking cũ.
                    Thread.sleep(20);
                    return value * value;
                }).subscribeOn(ioScheduler),
                4
            )
            .name("demo.work")
            .tag("operation", "square")
            .tap(Micrometer.metrics(registry));
    }
}
~~~

Đoạn `Thread.sleep` chỉ mô phỏng một dependency blocking trong bài thực hành và được cô lập trên bounded elastic. Ứng dụng thực tế nên thay bằng client non-blocking khi có thể. `flatMapSequential(..., 4)` giới hạn số tác vụ đồng thời ở bốn và giữ thứ tự kết quả theo nguồn.

### 5.3. Metrics cho reactive sequence

Ngoài Scheduler, `Micrometer.metrics(registry)` gắn qua `tap` có thể đo sequence đã đặt tên:

- `demo.work.flow.duration`: thời gian từ subscribe đến complete/error/cancel.
- `demo.work.onNext.delay`: khoảng cách thời gian giữa các onNext.
- `demo.work.requested`: lượng demand được request.
- `demo.work.subscribed`: số subscription.
- `demo.work.malformed.source`: sự kiện từ nguồn sai protocol, khi phát hiện.

Các meter của sequence có thể dùng tag status như completed, completedEmpty, error hoặc cancelled. Điều này hữu ích để phân biệt request thành công với publisher bị hủy do client rời đi.

Dùng `name` và tag có cardinality thấp như operation, source hoặc result. Không đưa user ID, request ID, email, raw URL hay exception message vào metric tag; cardinality cao có thể làm Prometheus/Micrometer tăng memory và chi phí lưu trữ rất nhanh.

## 6. Quan sát hàng đợi và backpressure

Một queue là nơi công việc chờ consumer. Những chỉ số nên có:

| Metric ứng dụng | Ý nghĩa |
| --- | --- |
| `app.work.queue.depth` | số phần tử hiện có |
| `app.work.queue.capacity` | sức chứa tối đa |
| `app.work.queue.rejected` | số lần enqueue thất bại |
| `app.work.queue.wait` | thời gian từ enqueue tới dequeue |
| `app.work.queue.processed` | số công việc hoàn tất |
| `app.work.queue.processing` | số công việc đang xử lý |

Nếu depth tăng liên tục, producer đang nhanh hơn consumer. Tăng capacity chỉ kéo dài thời gian trước khi đầy; nó không giải quyết thiếu throughput và còn có thể giữ nhiều object trong memory hơn.

Chính sách khi queue đầy cần được xác định:

- Reject: từ chối công việc mới và trả 429/503 hoặc tín hiệu tương ứng.
- Drop newest: bỏ phần tử mới nhất nếu nghiệp vụ cho phép.
- Drop oldest: bỏ phần tử cũ nhất nếu dữ liệu mới có giá trị hơn.
- Buffer có giới hạn: chờ trong một khoảng nhất định rồi reject.
- Backpressure: yêu cầu upstream giảm tốc nếu upstream hỗ trợ demand.
- Persist: ghi công việc vào broker/database khi cần durability.

Không dùng queue không giới hạn làm giải pháp cho một consumer chậm. Hãy xác định queue capacity, maximum wait, overflow policy và metric cho mỗi queue.

### 6.1. Queue của Reactor Netty và queue ứng dụng không giống nhau

`reactor.netty.eventloop.pending.tasks` đo số tác vụ đang chờ trên event loop của Reactor Netty khi metrics tương ứng được bật. Nó không đo queue nghiệp vụ, queue trong `flatMap` hoặc mọi buffer trong Reactor operator.

`ThreadPoolTaskExecutor` và `ThreadPoolTaskScheduler` do Spring quản lý có thể được Actuator instrument tự động. Các meter executor thường cho biết active threads, pool size, queued tasks và completed tasks. Một Reactor Scheduler riêng cần instrumentation Reactor như phần trên.

### 6.2. Đo queue của chính ứng dụng

~~~java
@Component
class WorkQueueTelemetry {
    private record Entry(String value, long enqueuedAtNanos) {}

    private final ArrayBlockingQueue<Entry> queue =
        new ArrayBlockingQueue<>(64);

    private final Counter rejected;
    private final Timer waitTime;

    WorkQueueTelemetry(MeterRegistry registry) {
        Gauge.builder(
            "app.work.queue.depth", queue, Queue::size
        ).register(registry);

        Gauge.builder(
            "app.work.queue.capacity",
            queue,
            q -> q.size() + q.remainingCapacity()
        ).register(registry);

        this.rejected = registry.counter("app.work.queue.rejected");
        this.waitTime = registry.timer("app.work.queue.wait");
    }

    boolean offer(String value) {
        boolean accepted =
            queue.offer(new Entry(value, System.nanoTime()));

        if (!accepted) {
            rejected.increment();
        }
        return accepted;
    }

    Optional<String> poll() {
        Entry entry = queue.poll();
        if (entry == null) {
            return Optional.empty();
        }

        waitTime.record(
            System.nanoTime() - entry.enqueuedAtNanos(),
            TimeUnit.NANOSECONDS
        );
        return Optional.of(entry.value());
    }

    int depth() {
        return queue.size();
    }

    int capacity() {
        return queue.size() + queue.remainingCapacity();
    }
}
~~~

Gauge chỉ phản ánh snapshot tại thời điểm scrape. Counter rejection là số tích lũy; Timer wait ghi phân phối thời gian chờ. Khi queue được thay bằng broker, hãy dùng metric broker tương ứng thay vì chỉ đo queue local.

## 7. Quan sát connection pool

Một request reactive có thể không block thread trong lúc đợi database, nhưng vẫn phải chờ connection nếu pool đã dùng hết. Đây là dạng nghẽn phổ biến: CPU có thể thấp trong khi HTTP latency và pending acquire tăng.

### 7.1. R2DBC pool metrics

Spring Boot 3.5 có hỗ trợ Actuator metrics cho R2DBC connection pool khi pool được cấu hình và driver/pool tương ứng có mặt.

| Meter | Ý nghĩa |
| --- | --- |
| `r2dbc.pool.acquired` | connection đang được acquire và sử dụng |
| `r2dbc.pool.allocated` | tổng connection đã allocate trong pool, gồm active và idle |
| `r2dbc.pool.idle` | connection đang nhàn rỗi |
| `r2dbc.pool.pending` | request đang chờ acquire connection |
| `r2dbc.pool.max.allocated` | giới hạn connection pool |
| `r2dbc.pool.max.pending` | giới hạn hàng đợi chờ acquire |

Các phép đọc hữu ích:

- `acquired` gần `max.allocated` và `pending` tăng: pool có thể đang bão hòa.
- `idle` lớn nhưng latency vẫn cao: xem query, network, lock, transaction hoặc downstream khác.
- `pending` bằng 0 không chứng minh database khỏe; query vẫn có thể chậm khi đã lấy connection.
- Transaction giữ connection lâu có thể làm pool thiếu capacity dù query riêng lẻ nhanh.

Cấu hình minh họa:

~~~properties
spring.r2dbc.pool.enabled=true
spring.r2dbc.pool.initial-size=5
spring.r2dbc.pool.max-size=20
spring.r2dbc.pool.max-acquire-time=3s
spring.r2dbc.pool.max-idle-time=30m
~~~

Chọn max-size theo giới hạn database, số instance/pod và workload. Tổng connection tối đa xấp xỉ số replica nhân pool max-size; phải để lại headroom cho migration, monitoring và service khác.

Không tăng pool một cách mù quáng. Nếu database đã quá tải CPU/IO/locks, thêm connection có thể làm tình hình tệ hơn. Kiểm tra thời gian query, thời gian giữ transaction, số request đồng thời và giới hạn database trước khi thay đổi pool.

### 7.2. Reactor Netty HTTP client connection pool

Với WebClient/Reactor Netty, connection pool có nhóm metric riêng khi metrics được bật:

| Meter | Ý nghĩa |
| --- | --- |
| `reactor.netty.connection.provider.active.connections` | connection đang được sử dụng |
| `reactor.netty.connection.provider.idle.connections` | connection đang nhàn rỗi |
| `reactor.netty.connection.provider.total.connections` | tổng active + idle |
| `reactor.netty.connection.provider.max.connections` | giới hạn connection |
| `reactor.netty.connection.provider.pending.connections` | request chờ connection |
| `reactor.netty.connection.provider.pending.connections.time` | thời gian chờ acquire |
| `reactor.netty.connection.provider.max.pending.connections` | giới hạn pending queue |

Nếu tự tạo `ConnectionProvider` hoặc `HttpClient`, cần bật metrics ở cấu hình Reactor Netty tương ứng, ví dụ `ConnectionProvider.builder(...).metrics(true)` và `HttpClient.metrics(true, ...)`. Không giả định một client tự tạo thủ công được instrument giống hệt client do Spring Boot quản lý.

Pool metric client chỉ nói về kết nối outbound tới remote server. Nó không phải số lượng inbound WebFlux client đang kết nối tới ứng dụng.

## 8. Quan sát bộ đệm và bộ nhớ

Reactive pipeline có thể giữ dữ liệu trong:

- JVM heap: object, DTO, collection và queue.
- JVM direct buffer pool: NIO direct ByteBuffer.
- Netty ByteBuf allocator: pooled heap/direct memory.
- Reactor operator buffers: prefetch, publishOn, flatMap, buffer/window.
- Application queue: queue tự xây.
- Driver/broker/network: buffer bên ngoài JVM hoặc ở native memory.

Không có một metric duy nhất phản ánh tổng mọi buffer của toàn hệ thống.

### 8.1. JVM buffer pool

Spring Boot có thể expose các meter:

- `jvm.buffer.count`: số buffer trong pool.
- `jvm.buffer.memory.used`: bộ nhớ đang được JVM buffer pool sử dụng.
- `jvm.buffer.total.capacity`: tổng capacity của các buffer.

Có thể drill down theo tag `id` để phân biệt `direct` và `mapped` khi meter đó cung cấp tag tương ứng. JVM buffer pool metrics không phải lúc nào cũng bằng số byte Netty allocator đang giữ.

### 8.2. Reactor Netty ByteBufAllocator metrics

Khi Reactor Netty metrics được bật, các meter có thể gồm:

| Meter | Ý nghĩa |
| --- | --- |
| `reactor.netty.bytebuf.allocator.active.direct.memory` | direct memory thực tế đang được buffer đang dùng |
| `reactor.netty.bytebuf.allocator.active.heap.memory` | heap memory thực tế đang được buffer đang dùng |
| `reactor.netty.bytebuf.allocator.used.direct.memory` | direct memory allocator đã reserve |
| `reactor.netty.bytebuf.allocator.used.heap.memory` | heap memory allocator đã reserve |
| `reactor.netty.eventloop.pending.tasks` | số task đang chờ trên event loop |

**Phân biệt active và used:** allocator có thể giữ vùng memory đã reserve để tái sử dụng sau khi buffer được release. Vì vậy `used.direct.memory` còn cao sau một đợt tải chưa đủ chứng minh leak. Nếu `active.direct.memory` tăng đều và không giảm sau khi traffic dừng, cần điều tra ownership/release và Netty leak log.

Reactor Netty có logger `_reactor.netty.channel.LeakDetection` hỗ trợ chẩn đoán buffer leak; bật DEBUG có thể cung cấp dấu vết ownership. Dùng leak detection level cao trong môi trường kiểm thử có kiểm soát vì nó có overhead. Đừng mặc định bật chế độ nặng nhất trên toàn bộ production traffic.

### 8.3. Không có metric chung cho mọi operator buffer

`publishOn`, `flatMap`, `onBackpressureBuffer` và `buffer` có thể tạo queue nội bộ với semantics khác nhau. Reactor không cung cấp một gauge toàn cục duy nhất cho tổng số phần tử đang nằm trong tất cả operator buffer.

Nếu queue thuộc nghiệp vụ, hãy instrument tại ranh giới ứng dụng. Nếu nghi ngờ operator prefetch làm tăng memory, kiểm tra concurrency/prefetch, kích thước payload, downstream throughput và heap/direct memory; dùng heap dump/JFR để tìm object giữ reference.

## 9. Reactor sequence metrics và tracing

Có thể instrument một đoạn pipeline với `reactor-core-micrometer`:

~~~java
Flux<Order> observed = orderSource
    .name("orders.pipeline")
    .tag("stage", "validation")
    .tap(Micrometer.metrics(meterRegistry))
    .checkpoint("orders.after-validation");
~~~

`name` tạo prefix có ý nghĩa; `tag` nên là giá trị cardinality thấp; `tap(Micrometer.metrics(...))` thu thập metrics về flow. `checkpoint` thêm ranh giới hỗ trợ stack trace khi lỗi được propagate qua pipeline.

Metrics và traces phục vụ mục đích khác nhau:

- Metrics cho biết nhiều request đang chậm hay lỗi.
- Trace cho thấy một request cụ thể đã dành thời gian ở span nào.
- Log liên kết traceId/spanId với sự kiện cụ thể.
- Profiling chỉ ra code path, lock hoặc allocation tốn tài nguyên.

Với tracing, dùng Micrometer Observation/Tracing và context propagation phù hợp. Reactive execution có thể đổi thread, vì vậy không dựa vào ThreadLocal thuần để giữ correlation ID xuyên pipeline. Hạn chế bật automatic context propagation nếu chưa đo overhead và kiểm tra thư viện tích hợp.

## 10. Logs có cấu trúc và correlation

Một log hữu ích cho request reactive nên có:

- timestamp và level;
- service/instance;
- traceId/spanId hoặc request correlation ID;
- route template, method và status;
- operation name;
- duration;
- exception class và nguyên nhân đã được redaction.

Ví dụ log minh họa:

~~~text
INFO traceId=7fa... spanId=21b... method=GET
route=/api/items status=200 durationMs=42 operation=load-items
~~~

Không log raw URI nếu có thể chứa ID hoặc token. Không dùng user ID, order ID hay request ID làm metric tag; những giá trị đó phù hợp hơn trong log/trace đã kiểm soát.

Khi một lỗi xảy ra trong pipeline dài, đặt `checkpoint("order.load.after-db")` tại boundary có ý nghĩa. Tránh bật global operator debug ở production nếu chưa đánh giá chi phí; nó có thể làm tăng overhead và memory.

## 11. Đọc dashboard theo tương quan

Một dashboard tối thiểu nên có các panel:

| Panel | Meter/đại lượng |
| --- | --- |
| Request rate | HTTP requests/s |
| Error rate | 4xx/5xx theo route |
| p50/p95/p99 | HTTP latency và downstream latency |
| Scheduler active/pending | `app.io.scheduler.tasks.active/pending` |
| Scheduler throughput | completed tasks/s và submitted tasks/s |
| Application queue | depth, capacity, rejected, wait time |
| R2DBC pool | acquired, idle, pending, max allocated |
| WebClient pool | active, idle, pending, pending acquire time |
| Heap/GC | heap used, GC pause, allocation |
| Buffer | JVM direct/mapped pool và Netty active/used direct memory |
| Event loop | pending tasks và thread dump khi cần |

Đặt các panel trên cùng time range và chia theo instance/region/route khi tag có cardinality thấp. Đừng so một gauge hiện tại với p99 của một giờ trước rồi kết luận nhân quả.

Các alert nên dựa trên thời gian kéo dài và mức ảnh hưởng:

- p99 vượt SLO liên tục.
- Error/timeout rate tăng.
- R2DBC pending acquire tồn tại liên tục hoặc pool acquire timeout.
- Queue depth tăng và rejected count bắt đầu tăng.
- Scheduler pending tăng cùng với latency.
- Active direct memory tăng liên tục sau khi workload giảm.
- Event loop pending tasks tăng cùng với HTTP latency.

Một giá trị pending tăng trong vài mili giây không nhất thiết là sự cố. Alert cần duration, threshold, baseline và runbook.

## 12. Quy trình chẩn đoán khi latency tăng

Thực hiện theo thứ tự để khoanh vùng:

1. Xác nhận phạm vi: một route, một instance, một vùng hay toàn hệ thống?
2. So request rate, error rate và p95/p99 trong cùng cửa sổ thời gian.
3. Kiểm tra CPU, GC, heap, thread count và event loop.
4. Kiểm tra Scheduler active/pending/completed và application queue.
5. Kiểm tra R2DBC/WebClient pool pending và acquire latency.
6. Kiểm tra database query latency, locks, slow query và remote dependency.
7. Kiểm tra heap/direct buffer metrics nếu memory tăng.
8. Dùng thread dump, JFR hoặc profiler để xác minh giả thuyết.
9. Thay một yếu tố có kiểm soát, sau đó so sánh metrics trước/sau.

### 12.1. Ma trận triệu chứng

| Triệu chứng | Dấu hiệu đi kèm | Hướng điều tra |
| --- | --- | --- |
| Latency tăng, CPU cao | Scheduler pending/active tăng | CPU saturation, loop nặng, concurrency quá lớn |
| Latency tăng, CPU thấp | R2DBC pending tăng | Pool cạn, query/transaction giữ connection lâu |
| HTTP latency cao, event loop pending tăng | Thread dump có blocking call | I/O blocking trên event loop, lock hoặc synchronized |
| Queue depth tăng mãi | rejected tăng, consumer throughput thấp | Producer vượt consumer, consumer lỗi hoặc downstream chậm |
| Direct memory active tăng liên tục | traffic giảm nhưng active không giảm | buffer ownership/release, leak hoặc client đọc chậm |
| Heap tăng, GC thường xuyên | object/collection lớn | queue không giới hạn, collectList, cache giữ reference |
| Remote call chậm | WebClient pending acquire tăng | remote connection pool, remote service hoặc timeout |
| Task completed chậm | tasks.active cao, CPU thấp | tác vụ chờ I/O/lock hoặc blocking trên Scheduler không phù hợp |

## 13. Runbook: kiểm tra nhanh bằng Actuator

Liệt kê meter:

~~~bash
curl http://localhost:8080/actuator/metrics
~~~

Xem HTTP request:

~~~bash
curl http://localhost:8080/actuator/metrics/http.server.requests
~~~

Xem R2DBC pool pending:

~~~bash
curl http://localhost:8080/actuator/metrics/r2dbc.pool.pending
~~~

Xem JVM buffer:

~~~bash
curl http://localhost:8080/actuator/metrics/jvm.buffer.memory.used
~~~

Xem scheduler metric:

~~~bash
curl http://localhost:8080/actuator/metrics/app.io.scheduler.tasks.pending
~~~

Xem Prometheus exposition:

~~~bash
curl http://localhost:8080/actuator/prometheus
~~~

Tên meter ở endpoint metrics dùng dấu chấm. Prometheus có thể chuẩn hóa thành snake_case. Nếu meter không xuất hiện, kiểm tra dependency/registry, meter đã được tạo chưa, metrics có bật ở client/pool tương ứng không và actuator endpoint có được expose không.

`/actuator/metrics` là endpoint chẩn đoán tại thời điểm truy vấn; Prometheus nên scrape `/actuator/prometheus`. Bảo vệ management endpoints và không expose endpoint chứa thông tin nội bộ ra mạng công cộng.

## 14. Công cụ gỡ lỗi bổ sung

| Công cụ | Dùng khi |
| --- | --- |
| Thread dump | thread bị block, deadlock, event loop không phản hồi |
| Heap dump | heap tăng, object/collection bị giữ |
| Java Flight Recorder | CPU, allocation, lock, GC, socket và thread events |
| async-profiler | CPU flame graph hoặc allocation profiling |
| BlockHound | phát hiện blocking call trên non-blocking thread trong test/dev |
| Netty leak detection | nghi ngờ ByteBuf bị giữ hoặc release sai |
| Database slow query log | query chậm, lock hoặc index thiếu |
| Prometheus/Grafana | xu hướng, tương quan và alert theo thời gian |

Thread dump không hiển thị đầy đủ mọi task đang nằm trong queue. Heap dump cũng không phải công cụ duy nhất để phân tích direct native memory. Dùng đúng công cụ cho đúng loại tài nguyên.

## 15. Demo hoàn chỉnh: Spring Boot 3.5, WebFlux và Actuator

Demo cung cấp ba nhóm workload:

- `GET /api/work?count=8`: thực thi tác vụ trên Scheduler được instrument.
- `GET /api/items`: đọc dữ liệu từ H2 qua R2DBC để tạo hoạt động connection pool.
- `POST /api/queue` và `POST /api/queue/poll`: thêm/lấy công việc từ queue bounded có metrics depth, capacity, wait và rejected.

Dự án dùng Java 17, Spring Boot 3.5.6, Micrometer, Reactor Core Micrometer, Prometheus và H2 R2DBC.

### 15.1. Cấu trúc dự án

~~~text
reactive-observability-lab/
  settings.gradle
  build.gradle
  src/main/
    java/demo/observability/
      ObservabilityApplication.java
      SchedulerConfiguration.java
      WorkService.java
      WorkController.java
      QueueTelemetry.java
      QueueController.java
      ItemService.java
      ItemController.java
      QueueRequest.java
    resources/
      application.properties
      schema.sql
      data.sql
  src/test/java/demo/observability/
      ObservabilityIntegrationTest.java
      QueueTelemetryTest.java
~~~

### 15.2. settings.gradle

~~~groovy
rootProject.name = 'reactive-observability-lab'
~~~

### 15.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    implementation 'io.projectreactor:reactor-core-micrometer'

    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    runtimeOnly 'io.r2dbc:r2dbc-h2'
    runtimeOnly 'io.r2dbc:r2dbc-pool'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot dependency management chọn các phiên bản Micrometer, Reactor và driver tương thích. Không tự override riêng reactor-core-micrometer sang một version khác với Reactor Core đang được Boot quản lý.

### 15.4. application.properties

~~~properties
spring.application.name=reactive-observability-lab

spring.r2dbc.url=r2dbc:h2:mem:///observability?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.r2dbc.username=sa
spring.r2dbc.password=
spring.r2dbc.pool.enabled=true
spring.r2dbc.pool.initial-size=2
spring.r2dbc.pool.max-size=8
spring.r2dbc.pool.max-acquire-time=3s
spring.sql.init.mode=always

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.tags.application=reactive-observability-lab
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.slo.http.server.requests=50ms,100ms,250ms,500ms,1s
~~~

H2 in-memory chỉ phục vụ demo. Pool size 8 không phải cấu hình production mẫu cho mọi database; nó giúp quan sát pool trong bài lab.

### 15.5. schema.sql

~~~sql
CREATE TABLE observed_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
~~~

### 15.6. data.sql

~~~sql
INSERT INTO observed_items (name) VALUES ('alpha');
INSERT INTO observed_items (name) VALUES ('beta');
INSERT INTO observed_items (name) VALUES ('gamma');
~~~

### 15.7. ObservabilityApplication.java

~~~java
package demo.observability;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObservabilityApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            ObservabilityApplication.class,
            args
        );
    }
}
~~~

### 15.8. SchedulerConfiguration.java

~~~java
package demo.observability;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.observability.micrometer.Micrometer;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
public class SchedulerConfiguration {

    @Bean(destroyMethod = "dispose")
    Scheduler observedIoScheduler(MeterRegistry registry) {
        Scheduler delegate =
            Schedulers.newBoundedElastic(
                4,
                100,
                "observed-io"
            );

        return Micrometer.timedScheduler(
            delegate,
            registry,
            "app.io"
        );
    }
}
~~~

Bean được dispose khi context đóng. Mọi pipeline muốn được đo bằng prefix `app.io` phải dùng bean Scheduler này. Nếu một đoạn code gọi trực tiếp `Schedulers.boundedElastic()` thì task đó không đi qua wrapper ở trên.

### 15.9. WorkService.java

~~~java
package demo.observability;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import reactor.core.observability.micrometer.Micrometer;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;

@Service
public class WorkService {
    private final Scheduler scheduler;
    private final MeterRegistry registry;

    public WorkService(
            @Qualifier("observedIoScheduler") Scheduler scheduler,
            MeterRegistry registry) {
        this.scheduler = scheduler;
        this.registry = registry;
    }

    public Flux<Integer> calculate(int count) {
        return Flux.range(1, count)
            .flatMapSequential(value ->
                Mono.fromCallable(() -> {
                    // Mô phỏng dependency blocking trong bài lab.
                    Thread.sleep(20);
                    return value * value;
                }).subscribeOn(scheduler),
                4
            )
            .name("demo.work")
            .tag("operation", "square")
            .tap(Micrometer.metrics(registry))
            .checkpoint("demo.work.calculate");
    }
}
~~~

`flatMapSequential` cho phép tối đa bốn tác vụ đồng thời nhưng giữ thứ tự kết quả. Đoạn sleep chỉ mô phỏng một lời gọi legacy blocking được cô lập; production nên ưu tiên API non-blocking.

### 15.10. WorkController.java

~~~java
package demo.observability;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/work")
public class WorkController {
    private final WorkService service;

    public WorkController(WorkService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<Integer> calculate(
            @RequestParam(defaultValue = "8") int count) {
        if (count < 1 || count > 100) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "count must be between 1 and 100"
            );
        }
        return service.calculate(count);
    }
}
~~~

### 15.11. QueueTelemetry.java

~~~java
package demo.observability;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.Optional;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class QueueTelemetry {
    private record Entry(String value, long enqueuedAtNanos) {}

    private final ArrayBlockingQueue<Entry> queue =
        new ArrayBlockingQueue<>(64);

    private final Counter rejected;
    private final Timer waitTime;

    public QueueTelemetry(MeterRegistry registry) {
        Gauge.builder(
            "app.work.queue.depth",
            queue,
            q -> q.size()
        ).register(registry);

        Gauge.builder(
            "app.work.queue.capacity",
            queue,
            q -> q.size() + q.remainingCapacity()
        ).register(registry);

        this.rejected =
            registry.counter("app.work.queue.rejected");

        this.waitTime =
            registry.timer("app.work.queue.wait");
    }

    public boolean offer(String value) {
        boolean accepted = queue.offer(
            new Entry(value, System.nanoTime())
        );

        if (!accepted) {
            rejected.increment();
        }
        return accepted;
    }

    public Optional<String> poll() {
        Entry entry = queue.poll();
        if (entry == null) {
            return Optional.empty();
        }

        waitTime.record(
            System.nanoTime() - entry.enqueuedAtNanos(),
            TimeUnit.NANOSECONDS
        );
        return Optional.of(entry.value());
    }

    public int depth() {
        return queue.size();
    }

    public int capacity() {
        return queue.size() + queue.remainingCapacity();
    }

    public double rejectedCount() {
        return rejected.count();
    }
}
~~~

Queue có capacity 64. Khi đầy, `offer` trả false và tăng counter; không âm thầm bỏ dữ liệu. Gauge depth/capacity cho snapshot, Timer wait đo thời gian một phần tử ở trong queue.

### 15.12. QueueRequest.java

~~~java
package demo.observability;

public record QueueRequest(String value) {
}
~~~

### 15.13. QueueController.java

~~~java
package demo.observability;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/queue")
public class QueueController {
    private final QueueTelemetry queue;

    public QueueController(QueueTelemetry queue) {
        this.queue = queue;
    }

    @PostMapping
    public ResponseEntity<Map<String, Object>> enqueue(
            @RequestBody QueueRequest request) {
        boolean accepted = queue.offer(request.value());

        Map<String, Object> body = Map.of(
            "accepted", accepted,
            "depth", queue.depth(),
            "capacity", queue.capacity()
        );

        return ResponseEntity
            .status(accepted
                ? HttpStatus.ACCEPTED
                : HttpStatus.TOO_MANY_REQUESTS)
            .body(body);
    }

    @PostMapping("/poll")
    public Map<String, Object> poll() {
        var value = queue.poll();

        return Map.of(
            "present", value.isPresent(),
            "value", value.orElse(""),
            "depth", queue.depth()
        );
    }

    @GetMapping
    public Map<String, Object> stats() {
        return Map.of(
            "depth", queue.depth(),
            "capacity", queue.capacity(),
            "rejected", queue.rejectedCount()
        );
    }
}
~~~

### 15.14. ItemService.java

~~~java
package demo.observability;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class ItemService {
    private final DatabaseClient databaseClient;

    public ItemService(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<String> findAll() {
        return databaseClient
            .sql("SELECT name FROM observed_items ORDER BY id")
            .map((row, metadata) ->
                row.get("name", String.class)
            )
            .all();
    }
}
~~~

### 15.15. ItemController.java

~~~java
package demo.observability;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/items")
public class ItemController {
    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<String> findAll() {
        return service.findAll();
    }
}
~~~

Khi gọi endpoint này, Boot R2DBC pool có thể tạo các meter acquired/allocated/idle/pending để quan sát connection usage. Nếu các meter không xuất hiện trong môi trường khác, kiểm tra dependency r2dbc-pool, pool enablement và Actuator R2DBC metrics auto-configuration.

### 15.16. QueueTelemetryTest.java

~~~java
package demo.observability;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class QueueTelemetryTest {

    @Test
    void queueDepthAndOverflowAreMeasured() {
        SimpleMeterRegistry registry =
            new SimpleMeterRegistry();

        QueueTelemetry queue = new QueueTelemetry(registry);

        for (int i = 0; i < 64; i++) {
            assertTrue(queue.offer("task-" + i));
        }

        assertFalse(queue.offer("overflow"));
        assertEquals(64.0,
            registry.get("app.work.queue.depth")
                .gauge().value());
        assertEquals(1.0,
            registry.get("app.work.queue.rejected")
                .counter().count());

        assertTrue(queue.poll().isPresent());
        assertEquals(63, queue.depth());

        registry.close();
    }
}
~~~

### 15.17. ObservabilityIntegrationTest.java

~~~java
package demo.observability;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ObservabilityIntegrationTest {

    @Autowired
    WebTestClient client;

    @Autowired
    MeterRegistry registry;

    @Test
    void workEndpointProducesSchedulerAndReactorMetrics() {
        client.get()
            .uri("/api/work?count=4")
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Integer.class)
            .contains(1, 4, 9, 16);

        assertNotNull(
            registry.find("app.io.scheduler.tasks.submitted")
                .counter()
        );

        assertTrue(
            registry.find("demo.work.subscribed")
                .counter()
                .count() > 0
        );
    }

    @Test
    void databaseEndpointUsesR2dbcPool() {
        client.get()
            .uri("/api/items")
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(String.class)
            .contains("alpha", "beta", "gamma");

        assertNotNull(
            registry.find("r2dbc.pool.allocated").gauge()
        );
    }

    @Test
    void actuatorMetricsEndpointIsAvailable() {
        client.get()
            .uri("/actuator/metrics")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.names").isArray();
    }
}
~~~

Test integration tạo HTTP request thật tới ứng dụng chạy random port. Unit test queue dùng SimpleMeterRegistry độc lập. Các test chứng minh metric được đăng ký và endpoint hoạt động; chúng không thay thế load test hoặc kiểm tra saturation thực tế.

### 15.18. Chạy ứng dụng và quan sát

Cần Java 17 và Gradle:

~~~bash
gradle test
gradle bootRun
~~~

Gọi Scheduler workload:

~~~bash
curl "http://localhost:8080/api/work?count=8"
~~~

Body dự kiến:

~~~json
[1,4,9,16,25,36,49,64]
~~~

Đọc database qua R2DBC:

~~~bash
curl http://localhost:8080/api/items
~~~

Body dự kiến:

~~~json
["alpha","beta","gamma"]
~~~

Thêm một phần tử vào queue:

~~~bash
curl -i -X POST http://localhost:8080/api/queue \
  -H "Content-Type: application/json" \
  -d '{"value":"task-1"}'
~~~

Xem trạng thái queue:

~~~bash
curl http://localhost:8080/api/queue
~~~

Lấy một phần tử ra khỏi queue:

~~~bash
curl -X POST http://localhost:8080/api/queue/poll
~~~

Xem metric scheduler:

~~~bash
curl http://localhost:8080/actuator/metrics/app.io.scheduler.tasks.submitted
~~~

Xem metric pool:

~~~bash
curl http://localhost:8080/actuator/metrics/r2dbc.pool.pending
~~~

Xem Prometheus:

~~~bash
curl http://localhost:8080/actuator/prometheus
~~~

Tên và giá trị meter thay đổi theo số request và thời điểm scrape. Không có một stdout cố định cho toàn bộ metrics.

## 16. Cấu hình và quan sát Reactor Netty client

Nếu ứng dụng tạo WebClient riêng với Reactor Netty, có thể cấu hình pool có giới hạn và bật metrics:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("observed-remote")
        .maxConnections(40)
        .pendingAcquireMaxCount(100)
        .pendingAcquireTimeout(Duration.ofSeconds(3))
        .metrics(true)
        .build();

HttpClient httpClient = HttpClient.create(provider)
    .metrics(true, uri -> uri);

WebClient client = WebClient.builder()
    .clientConnector(
        new ReactorClientHttpConnector(httpClient)
    )
    .build();
~~~

Đoạn này là cấu hình cho custom client; trong Spring Boot, hãy ưu tiên dùng builder do Boot quản lý và customize nó để giữ các customizer/observation đã đăng ký. Đừng tạo một WebClient/ConnectionProvider mới cho mỗi request.

Khi ứng dụng shutdown, dispose resource client/provider theo lifecycle của bean. Pool metrics có ích để phát hiện pending acquire và connection saturation; chúng không thay thế metric latency của remote endpoint.

## 17. Cách đặt ngưỡng và cảnh báo

Không dùng cùng một threshold cho mọi workload. Hãy bắt đầu từ SLO và baseline sau đó điều chỉnh.

| Tín hiệu | Điều kiện nên điều tra | Câu hỏi tiếp theo |
| --- | --- | --- |
| HTTP p99 | vượt SLO liên tục | route nào, downstream nào? |
| HTTP 5xx/timeout | tăng so với baseline | lỗi tập trung ở instance nào? |
| Scheduler pending | tăng kéo dài cùng latency | worker có bị chiếm bởi tác vụ chậm? |
| Queue depth | tăng liên tục hoặc gần capacity | consumer có đủ throughput? |
| Queue rejected | khác 0 hoặc tăng nhanh | cần admission control hay scale consumer? |
| R2DBC pending | tồn tại kéo dài | connection bị giữ lâu hay DB chậm? |
| Netty pending acquire | tăng cùng remote latency | remote pool/remote service có bão hòa? |
| Active direct memory | tăng liên tục sau khi traffic giảm | có buffer chưa release? |
| GC pause | tăng cùng heap pressure | allocation/retained object ở đâu? |
| Event loop pending | tăng kéo dài | có blocking hoặc callback quá nặng? |

Một số PromQL minh họa sau khi scrape Prometheus:

~~~promql
rate(http_server_requests_seconds_count[5m])
~~~

~~~promql
r2dbc_pool_pending
~~~

~~~promql
reactor_netty_connection_provider_pending_connections
~~~

~~~promql
app_work_queue_depth / app_work_queue_capacity
~~~

Tên metric trong Prometheus có thể được chuẩn hóa từ Micrometer name. Kiểm tra endpoint exposition thực tế trước khi viết query/alert.

## 18. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ nhìn CPU | Bỏ sót I/O wait và pool saturation | Kết hợp latency, pending và pool |
| Coi tasks.pending là queue depth | Hiểu sai phạm vi metric | Instrument queue nghiệp vụ riêng |
| Nghĩ timedScheduler đo mọi Scheduler | Meter thiếu một số workload | Dùng đúng wrapper trong pipeline |
| Dùng Schedulers.enableMetrics() cho code mới | Dùng API deprecated | Micrometer.timedScheduler |
| Tăng pool connection để chữa query chậm | DB có thể quá tải hơn | Đo query, lock và transaction duration |
| Dùng queue không giới hạn | Memory tăng không kiểm soát | Bounded queue và overflow policy |
| Không đếm rejected/dropped | Mất dữ liệu không thấy được | Counter cho drop/reject |
| Coi used direct memory cao là leak | Báo động giả với pooled allocator | So active và used, quan sát xu hướng sau tải |
| Không instrument buffer/queue của app | Chỉ thấy JVM memory tổng | Gauge depth/capacity và timer wait |
| Tag metric bằng userId/requestId | Cardinality bùng nổ | Đưa ID vào logs/traces |
| Log toàn bộ payload | Rò rỉ dữ liệu nhạy cảm | Log metadata đã redaction |
| Expose toàn bộ Actuator public | Lộ thông tin nội bộ | Restrict endpoint và bảo vệ management port |
| Tạo WebClient mới mỗi request | Pool bị phân mảnh, resource leak | Reuse client và ConnectionProvider |
| Dùng heap dump để giải thích mọi direct memory | Thiếu góc nhìn native allocator | JVM buffer/Netty metrics, JFR/NMT/leak logs |
| Alert chỉ theo một sample | Nhiều cảnh báo giả | Dùng window, duration và baseline |
| Không có runbook sau alert | Không biết bước điều tra kế tiếp | Gắn owner, query và action cho từng alert |

## 19. Checklist trước khi đưa ứng dụng reactive vào production

1. Có Actuator, MeterRegistry và backend scrape/export chưa?
2. HTTP request có rate, error rate, latency histogram và route tag không?
3. Các Scheduler quan trọng có wrapper metrics và được inject đúng nơi không?
4. Có phân biệt Scheduler pending với application queue depth không?
5. Mọi queue có capacity, overflow policy, depth và rejected counter không?
6. R2DBC pool có acquired/idle/pending/max metrics không?
7. WebClient/Netty pool có active/idle/pending/acquire latency không?
8. Heap, GC, JVM buffer và Netty direct memory được quan sát chưa?
9. Có metric cho dropped/cancelled/retried work không?
10. Log có traceId/correlation ID và redaction không?
11. Trace cho thấy latency theo từng dependency không?
12. Có dashboard p95/p99 và alert theo SLO không?
13. Actuator endpoints đã được bảo vệ chưa?
14. Có thread dump/JFR/profiling runbook không?
15. Có load test với slow consumer, pool exhaustion và queue overflow không?
16. Đã kiểm tra metric cardinality và chi phí scrape chưa?
17. Có kiểm thử shutdown/dispose Scheduler và connection provider không?

## 20. Câu hỏi ôn tập có đáp án

**Câu 1. Vì sao WebFlux vẫn có thể bị nghẽn khi không block event loop?**

Vì Scheduler, connection pool, queue, database và remote service đều có capacity hữu hạn. Request có thể chờ tài nguyên dù thread không bị block.

**Câu 2. Micrometer.timedScheduler đo điều gì?**

Nó instrument các tác vụ được submit qua Scheduler wrapper, gồm active/completed/pending/submitted theo semantics của wrapper.

**Câu 3. Vì sao không thể dùng tasks.pending thay cho queue depth?**

tasks.pending phản ánh nhóm task immediate chưa thể bắt đầu do Scheduler đạt capacity; nó không phải độ dài mọi queue/operator/application buffer.

**Câu 4. Metric nào báo request đang chờ R2DBC connection?**

`r2dbc.pool.pending`.

**Câu 5. acquired và allocated khác nhau thế nào?**

acquired là connection đang được sử dụng; allocated là tổng connection đã allocate trong pool, gồm cả active và idle.

**Câu 6. Vì sao tăng max-size không phải lúc nào cũng tốt?**

Nó có thể đẩy nhiều query đồng thời hơn vào database đang bão hòa CPU, IO hoặc lock, làm latency tăng.

**Câu 7. Direct memory khác heap memory thế nào?**

Direct memory nằm ngoài heap Java thông thường và thường được dùng bởi NIO/Netty; nó có lifecycle và công cụ chẩn đoán khác.

**Câu 8. used.direct.memory tăng có chứng minh leak không?**

Không. Allocator có thể giữ memory đã reserve để tái sử dụng. Cần xem active direct memory, xu hướng sau tải và leak diagnostics.

**Câu 9. Vì sao phải instrument queue nghiệp vụ riêng?**

Vì Reactor/Netty không cung cấp một metric toàn cục cho mọi operator buffer hoặc queue do ứng dụng tạo.

**Câu 10. Vì sao không dùng requestId làm metric tag?**

Mỗi request tạo một time series mới, khiến cardinality và chi phí lưu trữ tăng mạnh. ID phù hợp với log/trace hơn.

**Câu 11. Metrics, logs và traces khác nhau thế nào?**

Metrics cho xu hướng/tổng hợp; logs ghi sự kiện; traces thể hiện đường đi và thời gian từng span của một request.

**Câu 12. Khi nào cần thread dump hoặc JFR?**

Khi metrics chỉ ra triệu chứng nhưng chưa rõ nguyên nhân như blocking, lock contention, CPU hotspot, allocation hoặc GC.

**Câu 13. Vì sao cần theo dõi rejected queue work?**

Depth có thể vẫn thấp nếu producer bị reject sớm. Counter rejected giúp phát hiện mất/từ chối công việc.

**Câu 14. Actuator metrics endpoint có thay Prometheus không?**

Không. `/actuator/metrics` phục vụ chẩn đoán tương tác; backend metrics nên scrape/export từ registry endpoint như `/actuator/prometheus`.

## 21. Ghi nhớ

- Quan sát reactive system phải bao gồm HTTP, Reactor pipeline, Scheduler, queue, connection pool và buffer.
- `Micrometer.timedScheduler` đo Scheduler wrapper cụ thể; task phải đi qua wrapper đó.
- `tasks.pending` không phải queue depth tổng quát.
- R2DBC pool có acquired/allocated/idle/pending/max metrics.
- Reactor Netty pool và ByteBufAllocator có metrics riêng khi được instrument.
- So sánh active và used direct memory để tránh kết luận leak sai.
- Queue cần capacity, wait time và rejected/dropped metrics.
- Dùng metrics cho xu hướng, logs cho sự kiện, traces cho request path và profiling để tìm nguyên nhân.
- Đặt tag cardinality thấp, bảo vệ Actuator và gắn alert với runbook.
- Chẩn đoán theo tương quan latency, throughput, pending, error và resource saturation.

## 22. Tài liệu chính thức

1. [Spring Boot 3.5 — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): JVM, executor, HTTP, Actuator metrics endpoint và Micrometer integration.
2. [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): expose, access control và bảo vệ endpoint.
3. [Spring Boot 3.5 — R2DBC SQL](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): ConnectionFactory, cấu hình và R2DBC support.
4. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): pool max-size, acquire timeout và cấu hình R2DBC.
5. [Spring Boot 3.5 — ConnectionPoolMetrics Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/metrics/r2dbc/ConnectionPoolMetrics.html): metric binder cho R2DBC ConnectionPool.
6. [Project Reactor 3.8.7 — Exposing Reactor Metrics](https://projectreactor.io/docs/core/3.8.7/reference/metrics.html): reactor-core-micrometer, timedScheduler, sequence metrics và Observation.
7. [Project Reactor — Metrics Details](https://projectreactor.io/docs/core/release/reference/metrics-details.html): tên meter và tags của Scheduler/publisher.
8. [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): Scheduler types, boundedElastic, parallel và threading model.
9. [Reactor Netty — Reference Guide](https://projectreactor.io/docs/netty/release/reference/index.html): connection pool, event loop, ByteBufAllocator metrics và leak detection.
10. [Micrometer — Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): meter, tags, timers, gauges, counters và cardinality.
11. [Spring Boot — Prometheus Endpoint](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): Prometheus registry và exposition endpoint.
12. [OpenJDK — Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder.html): ghi nhận và phân tích sự kiện runtime.
