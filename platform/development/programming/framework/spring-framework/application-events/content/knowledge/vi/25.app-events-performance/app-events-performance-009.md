# Batch hóa tác vụ hậu kỳ

## 1. Batch hóa tác vụ hậu kỳ là gì?

Trong Spring Framework Application Events, một use case có thể công bố `OrderPlaced` sau khi đơn hàng được đặt. Nhiều thành phần quan tâm đến sự kiện này để làm **việc phụ trợ** (*post-processing*): ghi audit, tính chỉ số, đồng bộ search index, tạo bản tổng hợp, gửi thông báo, cập nhật hệ thống tích hợp.

Cách đơn giản là mỗi event dẫn tới một thao tác I/O:

~~~text
OrderPlaced #101 -> listener -> INSERT audit 101
OrderPlaced #102 -> listener -> INSERT audit 102
OrderPlaced #103 -> listener -> INSERT audit 103
OrderPlaced #104 -> listener -> INSERT audit 104
~~~

Nếu mỗi lần round trip tới database hoặc dịch vụ ngoài đều có fixed overhead, cách làm này có thể tốn tài nguyên và tăng độ trễ. **Batch hóa** là gom nhiều đơn vị công việc cùng kiểu thành một lần xử lý có giới hạn:

~~~text
OrderPlaced #101 --+
OrderPlaced #102 --+-- buffer --> batch [101,102,103] --> xử lý một lượt
OrderPlaced #103 --+
OrderPlaced #104 -----------+--> batch [104,...]     --> xử lý đợt sau
~~~

Ý tưởng cốt lõi:

1. **Tiếp nhận nhanh:** listener chỉ tạo một task/snapshot tối thiểu rồi đưa vào buffer hoặc durable queue.
2. **Tích lũy có giới hạn:** gom tối đa `maxBatchSize` phần tử, đồng thời có ngưỡng chờ `maxWait` để những event xuất hiện thưa không phải chờ mãi.
3. **Xử lý theo lô:** worker gọi một API hỗ trợ batch thật sự, chẳng hạn JDBC batch, một bulk indexing request hoặc một API tích hợp có bulk endpoint.
4. **Ghi nhận kết quả và lỗi:** batch thành công được ACK; batch lỗi phải có cơ chế retry, chia nhỏ, cách ly poison item hoặc chuyển vào dead-letter theo mức độ tin cậy cần thiết.

Batch hóa **không phải** chỉ thêm `@Async` vào từng listener. `@Async` giúp chuyển việc sang thread khác nhưng vẫn có thể tạo **một task và một lần I/O cho mỗi event**. Batch hóa làm giảm số lời gọi I/O khi có đủ điều kiện.

## 2. Vì sao batch giúp hiệu năng?

Giả sử thao tác ghi một bản audit cần thời gian xấp xỉ:

- `L`: chi phí cố định mỗi lần gọi database hoặc HTTP;
- `c`: chi phí xử lý một phần tử;
- `N`: tổng số phần tử.

Không batch:

~~~text
T_single ≈ N × (L + c)
~~~

Nếu chia thành batch có kích thước `B`:

~~~text
T_batch ≈ ceil(N / B) × L + N × c + chi phí gom/serialize batch
~~~

Đây là mô hình đơn giản để hiểu **lý do giảm round trip**, không phải lời hứa rằng throughput thực tế luôn tăng tuyến tính. Database driver, transaction, giới hạn payload, network, contention, memory và cơ chế xử lý lỗi đều có thể ảnh hưởng kết quả.

Ví dụ thuần minh họa, nếu `N = 1000`, `B = 100`, overhead cố định `L = 5 ms`, phần biến đổi `c = 0,1 ms`:

| Cách xử lý | Số lần gọi | Thời gian ước lượng theo mô hình |
| --- | ---: | ---: |
| Ghi riêng từng phần tử | 1.000 | ~5.100 ms |
| Ghi theo batch 100 | 10 | ~150 ms trước overhead bổ sung |

Không dùng các con số giả định này để kết luận SLA. **Benchmark với workload thật** và so sánh throughput, p50/p95/p99 latency, CPU, connection pool, lỗi/retry và backlog.

### Đổi throughput lấy độ trễ

Batch lớn hơn thường giảm overhead trên mỗi phần tử nhưng làm một event phải **chờ những event khác**. Nếu chỉ có một event mỗi phút và policy là “đủ 100 event mới flush”, phần tử đó có thể chờ rất lâu.

Vì vậy phải định nghĩa **hai trigger**:

~~~text
Flush khi:
    pendingCount >= maxBatchSize
            HOẶC
    thời gian chờ của item cũ nhất >= maxWait
~~~

Đây là *size-or-time batching*. Triển khai bằng scheduler định kỳ có thể chỉ bảo đảm thời gian chờ **xấp xỉ** vì worker bận, lịch chạy trễ hoặc có backlog. Nếu SLA đòi hạn cứng, cần thiết kế clock/deadline, scheduling và giám sát phù hợp.

## 3. Kiến trúc batch hóa trong Spring Application Events

Một cách tổ chức hợp lý:

~~~text
Application service
      |
      v
ApplicationEventPublisher.publishEvent(...)
      |
      v
@EventListener hoặc @TransactionalEventListener
      |
      |  thao tác nhẹ: map event -> immutable BatchItem
      v
Bounded queue / Outbox / Broker
      |
      | maxBatchSize / maxWait / retry policy
      v
Batch worker
      |
      +--> JDBC batchUpdate(...) / bulk API / search bulk request
      |
      +--> success: ghi ACK/hoàn thành
      |
      +--> failure: retry/backoff/DLQ theo hợp đồng
~~~

**Điểm cần phân tách:** Spring application event mặc định là **cơ chế dispatch trong bộ nhớ của một application context**, không phải message broker bền vững. Nếu process chết, một task nằm trong hàng đợi RAM có thể mất. Việc dùng `@EventListener`, `@Async` hay `@Scheduled` không tự tạo delivery guarantee.

Bảng lựa chọn:

| Nhu cầu | Thiết kế thường hợp lý |
| --- | --- |
| Chỉ tối ưu xử lý nội bộ, mất dữ liệu khi restart được chấp nhận | Bounded in-memory queue + worker định kỳ |
| Phải xử lý **chỉ khi transaction nghiệp vụ commit** | `@TransactionalEventListener(AFTER_COMMIT)` hoặc cơ chế outbox phù hợp |
| Không được mất tác vụ dù crash ngay sau commit | **Transactional outbox** (ghi cùng transaction với domain state) |
| Nhiều service/instance cùng tiêu thụ, cần retry bền vững | Broker/queue bền vững + consumer batch + ACK/retry |
| Phải thực hiện atomically với business transaction | Xử lý trong transaction đó; không tự ý hoãn sang worker |
| Tác vụ phải chạy tức thì, latency quan trọng hơn throughput | Tránh batch lớn; xử lý trực tiếp hoặc batch nhỏ |

**Không batch nhầm những việc bắt buộc để xác nhận thành công**: kiểm tra business invariant, giữ hàng hoặc cập nhật trạng thái cốt lõi có thể phải nằm trong transaction/use case chính. Chỉ vì một việc “xảy ra sau event” không có nghĩa nó được phép trì hoãn hoặc thực hiện eventual consistency.

## 4. Các tham số cần xác định trước khi triển khai

### Batch size

`maxBatchSize` giới hạn số event xử lý trong một lượt. Ví dụ chọn 100, 250 hoặc 500 theo benchmark, **không có giá trị tối ưu chung**. Batch quá lớn có thể làm:

- tăng heap/payload/serialization;
- chiếm database connection lâu;
- vượt giới hạn HTTP request/SQL parameter;
- tăng chi phí retry nếu chỉ một phần tử lỗi;
- làm p99 latency xấu khi flush kéo dài.

Nên dùng đồng thời giới hạn **số item** và **ước lượng số byte** khi payload có kích thước khác nhau. Ví dụ 100 event nhỏ và 100 event chứa dữ liệu lớn không tiêu thụ RAM như nhau.

### Max wait / flush interval

`maxWait` giới hạn sự trì hoãn mong muốn của item cũ nhất. Với `@Scheduled(fixedDelay = 200)`, phương thức được chạy cách nhau 200 ms **tính từ lần chạy trước hoàn tất**; thời gian chờ thực tế có thể lớn hơn 200 ms khi flush chậm hoặc scheduler bị tải. Nếu muốn strict oldest-item deadline, cần thiết kế flush dựa trên timestamp của item và wake-up phù hợp.

### Queue capacity / backpressure

`queueCapacity` phải **hữu hạn** để không tăng RAM không kiểm soát. Khi hàng đợi đầy:

- **Reject có chủ ý:** trả lỗi ở bước enqueue; caller quyết định retry. Phù hợp khi task không được phép mất nhưng caller có thể xử lý lỗi.
- **Block có timeout:** tạo backpressure về publisher; phải chấp nhận khả năng tăng latency của request.
- **Chuyển sang kênh bền vững:** dùng queue/broker/outbox khi delivery bắt buộc.
- **Drop có chủ ý:** chỉ dành cho dữ liệu có thể mất (ví dụ telemetry không quan trọng), có metric cảnh báo rõ.

Không âm thầm dùng `offer()` rồi bỏ qua `false`: hệ thống có thể tuyên bố đã tiếp nhận tác vụ nhưng thực tế vứt mất event.

### Concurrency và ordering

Một worker có thể xử lý tuần tự theo thứ tự vào queue của **một instance**. Khi thêm nhiều worker/partition/instance:

- thứ tự hoàn thành giữa các batch không được bảo đảm mặc định;
- duplicate delivery có thể xảy ra khi retry;
- các event của cùng aggregate có thể cần route theo `aggregateId`/partition và sequence để giữ thứ tự tương đối;
- không chia batch theo ngẫu nhiên nếu tác vụ có phụ thuộc nhân quả;
- lưu `eventId` trong hệ thống xử lý để idempotent khi cần.

`ConcurrentLinkedQueue`, `ArrayBlockingQueue` và broker partition có các bảo đảm khác nhau; không dùng một lời khẳng định “FIFO” để suy diễn thứ tự xử lý toàn hệ thống.

## 5. Ví dụ Java 17+ chạy được: listener gom queue, worker flush tối đa ba item

Để nhìn rõ thuật toán mà không phụ thuộc scheduler timing, ví dụ đầu tiên thực thi **flush thủ công trong `main`**. Nó minh họa đúng hai trách nhiệm: listener **enqueue nhanh**, worker **drain một batch có giới hạn**. Môi trường production sẽ kích hoạt worker bằng scheduler hoặc queue consumer thay vì gọi tay.

Dự án dùng **Spring Framework 6.2.19** và Java 17+, không cần database hay Spring Boot.

### Cấu trúc

~~~text
event-postprocessing-batch/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/BatchPostProcessingDemo.java
    └── test/java/demo/BatchPostProcessingDemoTest.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'event-postprocessing-batch'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.BatchPostProcessingDemo'
}

test {
    useJUnitPlatform()
}
~~~

### src/main/java/demo/BatchPostProcessingDemo.java

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

@Configuration
public class BatchPostProcessingDemo {

    public record OrderPlaced(long orderId) {}

    @Bean
    EventBuffer eventBuffer() {
        // Capacity lớn hơn ví dụ 7 events nhưng vẫn hữu hạn.
        return new EventBuffer(8);
    }

    @Bean
    OrderEventListener orderEventListener(EventBuffer buffer) {
        return new OrderEventListener(buffer);
    }

    @Bean
    BatchSink batchSink() {
        return new BatchSink();
    }

    @Bean
    BatchWorker batchWorker(EventBuffer buffer, BatchSink sink) {
        return new BatchWorker(buffer, sink, 3);
    }

    public static final class EventBuffer {
        private final BlockingQueue<OrderPlaced> queue;

        public EventBuffer(int capacity) {
            this.queue = new ArrayBlockingQueue<>(capacity);
        }

        public void enqueue(OrderPlaced event) {
            // Không chặn request; reject rõ ràng nếu quá tải.
            if (!queue.offer(event)) {
                throw new IllegalStateException(
                    "Batch queue is full"
                );
            }
        }

        public int drainTo(List<OrderPlaced> batch, int maxItems) {
            return queue.drainTo(batch, maxItems);
        }

        public int pending() {
            return queue.size();
        }
    }

    public static final class OrderEventListener {
        private final EventBuffer buffer;

        public OrderEventListener(EventBuffer buffer) {
            this.buffer = buffer;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            // Đồng bộ nhưng rất nhẹ: chỉ enqueue.
            // Nếu queue đầy thì reject, không làm mất âm thầm.
            buffer.enqueue(event);
        }
    }

    public static final class BatchSink {
        private final List<List<Long>> completed =
            new ArrayList<>();

        // Giả lập một bulk write: một lời gọi / batch.
        public void writeBatch(List<OrderPlaced> batch) {
            List<Long> ids = batch.stream()
                .map(OrderPlaced::orderId)
                .toList();

            completed.add(List.copyOf(ids));
            System.out.println(
                "batch " + completed.size()
                + ": ids=" + ids
            );
        }

        public List<List<Long>> completedBatches() {
            return List.copyOf(completed);
        }
    }

    public static final class BatchWorker {
        private final EventBuffer buffer;
        private final BatchSink sink;
        private final int maxBatchSize;

        public BatchWorker(
                EventBuffer buffer,
                BatchSink sink,
                int maxBatchSize) {
            this.buffer = buffer;
            this.sink = sink;
            this.maxBatchSize = maxBatchSize;
        }

        // Một worker tại một thời điểm trong demo.
        // synchronized ngăn các lời gọi flushOnce trên cùng object
        // chạy đồng thời, nhưng không khóa giữa các application instances.
        public synchronized int flushOnce() {
            List<OrderPlaced> batch =
                new ArrayList<>(maxBatchSize);

            buffer.drainTo(batch, maxBatchSize);

            if (batch.isEmpty()) {
                return 0;
            }

            // DEMO ONLY: drain đã xóa item khỏi RAM.
            // Nếu writeBatch thất bại, không có durable retry.
            sink.writeBatch(batch);
            return batch.size();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                BatchPostProcessingDemo.class)) {

            for (long id = 101; id <= 107; id++) {
                context.publishEvent(new OrderPlaced(id));
            }

            BatchWorker worker = context.getBean(
                BatchWorker.class
            );

            while (worker.flushOnce() > 0) {
                // Flush tới khi hàng đợi trống trong demo.
            }

            System.out.println(
                "pending=" + context.getBean(
                    EventBuffer.class).pending()
            );
        }
    }
}
~~~

### Lệnh chạy và output

~~~bash
gradle run --quiet
# Nếu có Gradle Wrapper: ./gradlew run --quiet
# Trên Windows: gradlew.bat run --quiet
~~~

Các dòng do chính demo in ra:

~~~text
batch 1: ids=[101, 102, 103]
batch 2: ids=[104, 105, 106]
batch 3: ids=[107]
pending=0
~~~

**Giải thích chính xác:**

1. `publishEvent` được gọi bảy lần, mỗi lần listener `OrderEventListener` thêm **một item** vào `ArrayBlockingQueue` capacity 8.
2. Không có lần xử lý bulk nào trong listener. Nó chỉ gọi `offer`, vì vậy mô phỏng đường tiếp nhận ngắn.
3. `flushOnce()` dùng `drainTo(..., 3)`, nên lấy tối đa ba phần tử cho một batch; ba lần flush trả về lần lượt **3, 3, 1**.
4. Lần flush cuối thấy queue trống và trả `0`, khiến vòng lặp kết thúc.
5. `BatchSink` giả lập một bulk endpoint bằng cách ghi lịch sử batch trong RAM. **Nó không phải JDBC batch thật**, không lưu dữ liệu bền vững và cũng không đo hiệu năng thực tế.

Ví dụ chủ động để `main` tự flush nhằm bảo đảm output tái lập. Để xử lý **ngoài request thread**, worker production cần được scheduler hoặc queue consumer thực thi trên thread khác, xem mục tiếp theo.

### Giới hạn quan trọng của ví dụ

`BlockingQueue.drainTo(...)` **xóa phần tử khỏi queue trước khi `BatchSink.writeBatch(...)` thành công**. Nếu sink ném lỗi sau khi drain, phần tử có thể đã mất. Vì vậy **mẫu này chỉ dùng học thuật / công việc best-effort**, không dùng nguyên trạng cho audit/notification bắt buộc. Không thêm `try/catch` rồi nuốt lỗi để coi như đã ACK.

Hơn nữa, nếu một listener đồng bộ ném exception do queue đầy, lỗi có thể lan về `publishEvent(...)` trong multicaster mặc định. Nếu publisher đang ở trong transaction nghiệp vụ, exception đó **có thể làm transaction rollback**, tùy điểm gọi và quy tắc rollback; đây là một chính sách backpressure có tác động thực, không phải hiệu năng “miễn phí”.

## 6. Kiểm thử batch size, thứ tự và backpressure bằng JUnit 5

Tạo `src/test/java/demo/BatchPostProcessingDemoTest.java`:

~~~java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class BatchPostProcessingDemoTest {

    @Test
    void groupsSevenEventsIntoThreeBatches() {
        try (var ctx = new AnnotationConfigApplicationContext(
                BatchPostProcessingDemo.class)) {

            for (long id = 101; id <= 107; id++) {
                ctx.publishEvent(
                    new BatchPostProcessingDemo.OrderPlaced(id)
                );
            }

            var worker = ctx.getBean(
                BatchPostProcessingDemo.BatchWorker.class
            );

            assertEquals(3, worker.flushOnce());
            assertEquals(3, worker.flushOnce());
            assertEquals(1, worker.flushOnce());
            assertEquals(0, worker.flushOnce());

            var sink = ctx.getBean(
                BatchPostProcessingDemo.BatchSink.class
            );

            assertEquals(
                List.of(
                    List.of(101L, 102L, 103L),
                    List.of(104L, 105L, 106L),
                    List.of(107L)
                ),
                sink.completedBatches()
            );

            assertEquals(
                0,
                ctx.getBean(
                    BatchPostProcessingDemo.EventBuffer.class
                ).pending()
            );
        }
    }

    @Test
    void rejectsNewWorkWhenBufferIsFull() {
        try (var ctx = new AnnotationConfigApplicationContext(
                BatchPostProcessingDemo.class)) {

            // Capacity của queue là 8.
            for (long id = 1; id <= 8; id++) {
                ctx.publishEvent(
                    new BatchPostProcessingDemo.OrderPlaced(id)
                );
            }

            assertThrows(
                IllegalStateException.class,
                () -> ctx.publishEvent(
                    new BatchPostProcessingDemo.OrderPlaced(9)
                )
            );

            assertEquals(
                8,
                ctx.getBean(
                    BatchPostProcessingDemo.EventBuffer.class
                ).pending()
            );
        }
    }
}
~~~

Chạy:

~~~bash
gradle test
# Nếu có wrapper: ./gradlew test
# Windows: gradlew.bat test
~~~

Kỳ vọng **hai bài test pass** với cấu hình Spring mặc định:

- Test 1 kiểm tra đúng giới hạn 3 item/batch, không trùng/thiếu item và queue trống.
- Test 2 kiểm tra khi queue đủ 8 item, event thứ 9 **không bị bỏ qua âm thầm** mà `IllegalStateException` lan về caller trong dispatch đồng bộ mặc định.

Những test này **không** kiểm chứng xử lý nhiều worker đồng thời, lỗi lưu database, transaction rollback, shutdown hoặc khả năng phục hồi crash. Đó là phần riêng bắt buộc nếu triển khai production.

## 7. Kích hoạt flush theo thời gian với @Scheduled

Spring Framework hỗ trợ `@EnableScheduling` và `@Scheduled` để định kỳ gọi worker. Ví dụ **minh họa phần bổ sung**, không phải một phần của project main mục 5:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Configuration
@EnableScheduling
class SchedulingConfig {}

@Component
class PeriodicBatchFlush {
    private final BatchPostProcessingDemo.BatchWorker worker;

    PeriodicBatchFlush(
            BatchPostProcessingDemo.BatchWorker worker) {
        this.worker = worker;
    }

    @Scheduled(fixedDelay = 200, initialDelay = 200)
    public void flushOnTimer() {
        // Chỉ một batch tối đa 3 item mỗi tick trong ví dụ.
        worker.flushOnce();
    }
}
~~~

Để sử dụng snippet này, cần đăng ký đúng `SchedulingConfig`, `PeriodicBatchFlush` và các bean của ví dụ trong một application context, không tạo bản sao bean; cấu hình ở trên **chỉ minh họa việc scheduling**, không tự được kích hoạt trong dự án ở mục 5.

`fixedDelay = 200` ở đây là **200 ms sau khi lần chạy trước hoàn tất**. Vì vậy không được khẳng định item luôn flush đúng 200 ms sau khi đến. Khi backlog dài, worker có thể chỉ xử lý 3 item mỗi tick và queue tiếp tục tăng.

Để hỗ trợ **size-or-time batching** thật sự, có thể:

- dùng một worker `BlockingQueue.poll(timeout)`: đợi item đầu tiên, rồi gom đến `maxBatchSize` hoặc một deadline `maxWait` theo item cũ nhất;
- hoặc dùng scheduler định kỳ và cơ chế đánh thức worker sớm khi lượng item đủ ngưỡng;
- luôn bảo đảm một batch không bị hai worker cùng claim; nếu muốn chạy song song, phải định nghĩa partition và ACK semantics.

**Không xử lý batch trực tiếp trong listener khi nó vừa đạt ngưỡng** nếu mục tiêu là giảm thời gian trên request thread. Khi đủ 100 event mà listener đồng bộ tự ghi DB 100 dòng, request thứ 100 có thể chịu độ trễ lớn bất thường.

### Skeleton size-or-time worker

Giả sử có `BlockingQueue<BatchItem>` với `BatchItem.receivedAt` (dữ liệu kiểm soát từ lúc enqueue), thuật toán tổng quát:

~~~text
loop while running:
    first = queue.poll(waitForNextItem)
    if first == null:
        continue

    batch = [first]
    deadline = monotonicNow + maxWait

    while batch.size < maxBatchSize:
        remaining = deadline - monotonicNow
        if remaining <= 0:
            break
        next = queue.poll(remaining)
        if next == null:
            break
        batch.add(next)

    writeAndAcknowledge(batch)
~~~

Đây là **pseudocode**, không phải API Java độc lập. Khi dùng deadline cho độ trễ thời gian trôi, ưu tiên clock đơn điệu như `System.nanoTime()` thay vì đồng hồ wall-clock dễ bị điều chỉnh. Việc đếm từ `first` lấy khỏi queue **không đủ** để bảo đảm maxWait tính từ lúc item thật sự **được enqueue**, đặc biệt khi backlog chờ dài; phải mang timestamp enqueue hoặc đo queue age và thiết kế xử lý backlog.

Trong production, có thể dùng broker/outbox để giữ event chờ, worker poll/claim, batch xử lý và ACK chỉ sau khi ghi kết quả thành công.

## 8. Batch hóa hậu commit với @TransactionalEventListener

Trong hệ thống dùng transaction, event có thể được công bố **trước khi DB commit**:

~~~text
@Transactional placeOrder()
    BEGIN T1
    save(order)
    publishEvent(OrderPlaced)
    ...
    COMMIT hoặc ROLLBACK
~~~

Nếu listener nhận event đồng bộ và enqueue ngay trong T1, một event có thể đã vào RAM trong khi T1 sau đó **rollback**. Một task hậu kỳ có thể xử lý sự việc không có trong dữ liệu đã commit.

Với công việc chỉ nên bắt đầu sau commit:

~~~java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

// Minh họa listener nằm trong bean của ứng dụng.
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT)
public void acceptCommittedOrder(OrderPlaced event) {
    // Enqueue sau khi transaction T1 commit thành công.
    buffer.enqueue(event);
}
~~~

Đoạn trên là **minh họa**, phụ thuộc vào kiểu `OrderPlaced`, biến `buffer` và bean được quản lý. Cần cân nhắc:

1. `@TransactionalEventListener` mặc định là `AFTER_COMMIT`; khai báo tường minh giúp code dễ đọc.
2. Mặc định listener không chạy khi event được publish **ngoài transaction** và `fallbackExecution=false`. Nếu cần xử lý ngoài transaction, phải chọn semantics rõ ràng, không tự bật fallback để che lỗi.
3. Callback chạy sau commit, nên **queue đầy làm enqueue thất bại cũng không rollback được T1**. Khi lỗi sau commit, ứng dụng vẫn cần cách phát hiện và khôi phục công việc.
4. Giữa **DB commit** và **enqueue vào RAM**, process có thể chết. Việc dùng AFTER_COMMIT giải quyết **thời điểm**, không bảo đảm **độ bền**.
5. Listener hậu commit muốn ghi DB mới cần transaction phù hợp, thường qua một Spring-managed service độc lập mở transaction mới theo use case. Không dùng tài nguyên T1 trong cleanup như thể nó luôn có commit mới.
6. Với reactive transaction, context ở Reactor Context; dùng cơ chế transaction-bound event phù hợp như `TransactionalEventPublisher` thay vì dựa vào servlet ThreadLocal.

**Tránh cách nói “`AFTER_COMMIT` + `Async` = event không thể mất”**: cả callback trong process và local executor đều có cửa sổ crash.

## 9. Hệ thống cần độ tin cậy: transactional outbox và bulk consumer

Đối với event phải được xử lý ngay cả khi server chết, kiến trúc phù hợp thường là:

~~~text
BEGIN T1
  INSERT orders(...)
  INSERT outbox(event_id, event_type, aggregate_id,
                payload, created_at, status='PENDING')
COMMIT T1

Outbox worker:
  claim tối đa B rows PENDING
  gửi/ghi batch đến hệ thống đích
  nhận ACK/commit của đích
  đánh dấu rows là DONE
  nếu lỗi: retry/backoff hoặc DLQ
~~~

Đây là **pseudocode kiến trúc**. Cơ chế claim/lock/lease phụ thuộc DB và topology. Đừng triển khai bằng “SELECT pending rồi UPDATE” không có bảo vệ khi hai worker cùng chạy vì có thể double-process.

Các nguyên tắc:

- **Atomicity nguồn:** bản ghi domain và outbox phải commit **trong cùng T1**.
- **ACK sau khi thành công:** chỉ đánh dấu DONE khi phía xử lý đã xác nhận thành công theo hợp đồng. Với bulk API có partial-success, ACK **theo từng item** đúng kết quả, không đánh dấu cả batch khi một phần tử thất bại.
- **Retry giữ identity:** một sự việc vẫn có `eventId` gốc; số lần gửi có thể lớn hơn 1.
- **Idempotency:** consumer dùng event ID và phạm vi xử lý phù hợp (ví dụ unique constraint) để xử lý trùng an toàn. “Gửi một lần” và “xử lý exactly-once trên mọi hệ thống” không tự có chỉ vì dùng outbox.
- **Dead letter/poison item:** tách item lỗi vĩnh viễn để tránh một bản ghi xấu giữ chân cả batch.
- **Progress:** đo số item pending, tuổi outbox cũ nhất, retry, batch duration, throughput và failure rate.
- **Retention:** định nghĩa khi nào xóa/archive DONE; outbox không tự dọn mãi mãi.
- **Ordering:** nếu mỗi aggregate có sequence, giữ thứ tự khi claim/batch/partition nếu consumer yêu cầu; nhiều worker có thể đảo thứ tự hoàn thành nếu không điều phối.

### Ví dụ JDBC batch thật

Trong Spring JDBC, `JdbcTemplate.batchUpdate(...)` có thể gom nhiều thao tác chuẩn bị statement để giảm overhead, tùy driver. Đoạn **minh họa trong một Spring-managed service**, cần `JdbcTemplate jdbcTemplate` và kiểu `OrderPlaced` của ứng dụng:

~~~java
public void writeAuditBatch(List<OrderPlaced> batch) {
    jdbcTemplate.batchUpdate(
        "INSERT INTO order_audit(order_id) VALUES (?)",
        batch,
        batch.size(),
        (ps, event) -> ps.setLong(1, event.orderId())
    );
}
~~~

Giả sử schema và constraint đã có. Đối với batch rỗng, nên bỏ qua hoặc xử lý riêng. **Không suy diễn** kết quả của một lần gọi `batchUpdate` là “mọi item đã commit” khi phương thức chạy trong transaction có thể rollback hoặc driver trả các update counts khác nhau.

Nếu audit phải ghi nhất quán, chạy đúng transaction/commit boundary. Nếu consumer lấy outbox và ghi DB đích, áp dụng transaction và cơ chế claim/ACK phù hợp. Batch API của JDBC không thay thế durable queue.

## 10. Lỗi từng phần: batch một item thất bại thì sao?

Batch có thể thất bại theo nhiều mức:

~~~text
Batch [101,102,103,104]
  |
  +-- 101: OK
  +-- 102: OK
  +-- 103: invalid payload
  +-- 104: chưa được xử lý
~~~

Tùy driver/API, kết quả có thể:

- **All-or-nothing:** một transaction rollback toàn batch.
- **Partial success:** một số item đã được commit/accepted, số khác lỗi.
- **Ambiguous outcome:** timeout sau khi phía đích có thể đã thực hiện, client không biết đã thành công hay chưa.

Thiết kế retry phải căn cứ vào hợp đồng của **sink**:

1. Nếu all-or-nothing, retry toàn batch có backoff và giới hạn số lần (khi đúng lỗi tạm thời).
2. Nếu partial success, ACK những item thành công và retry những item thất bại; không gửi lại phần đã thành công khi có thể tránh.
3. Nếu outcome không rõ, dùng **idempotency key** để retry an toàn. Đừng tự coi timeout là “chắc chắn chưa xử lý”.
4. Nếu một item lỗi vĩnh viễn (poison), giảm kích thước/chia batch hoặc đưa nó vào DLQ, để những item tốt tiếp tục.
5. Nếu lỗi do quota hoặc quá tải, áp dụng backoff/circuit breaker, giảm concurrency hoặc batch size; không tạo retry storm.
6. Bảo toàn `eventId`, `correlationId` và payload cần thiết qua mọi lần retry.

Ví dụ **không an toàn** cần tránh:

~~~java
List<OrderPlaced> batch = drainFromMemoryQueue();
try {
    bulkApi.send(batch);
} catch (Exception ignored) {
    // Sai: queue đã xóa item, không còn retry hay cảnh báo.
}
~~~

Điều cần giải quyết không phải “catch đủ exception” mà là **giao thức nhận việc và xác nhận việc**. Nếu yêu cầu at-least-once, broker/outbox cung cấp trạng thái nhận/claim/ACK bền vững; worker vẫn phải idempotent.

## 11. Graceful shutdown và tăng số worker

Một ứng dụng chạy tốt trong lab có thể thất lạc event khi deploy:

~~~text
t0: đã enqueue 800 items trong RAM
t1: Pod nhận SIGTERM
t2: executor/scheduler bị dừng
t3: RAM biến mất cùng 800 items chưa flush
~~~

Khi chấp nhận in-memory batching, có thể thiết kế dừng có kiểm soát:

- Ngừng nhận tác vụ mới hoặc chuyển sang instance khác.
- Chặn việc chạy đồng thời các lần flush.
- Chờ một khoảng tối đa để các batch đang xử lý hoàn tất.
- Flush phần còn lại nếu có đủ thời gian và sink khả dụng.
- Ghi metric/log nếu còn việc chưa hoàn tất.

Nhưng **graceful shutdown không cứu được power loss, crash, kill -9 hoặc hạ tầng bị mất đột ngột**. Với công việc bắt buộc, cần persistence trước khi ACK nguồn. Ngoài ra, `@PreDestroy` hoặc shutdown hook không phải cơ chế xử lý lỗi và retry bền vững.

### Khi ứng dụng scale ngang

Giả sử có ba Spring instances A/B/C, mỗi instance có một queue trong RAM. Những queue này **không tự chia sẻ** backlog. Một instance chết làm mất riêng hàng đợi của nó. Trạng thái tổng trên dashboard phải tổng hợp từ các instance.

Đối với phân phối công việc:

- Broker với partition/consumer group có thể chia tải;
- Outbox workers có thể claim theo lease/lock/partition;
- Event của một aggregate cần thứ tự có thể route cùng partition;
- Batch size tối ưu cần xét tổng tải chứ không chỉ tối ưu một instance;
- Cần tránh tăng worker vô hạn khi hệ thống đích đã saturation.

`synchronized` trong ví dụ Java chỉ bảo vệ **một object trong một JVM**, không phải distributed lock. Nó không thể giữ thứ tự hoặc chống trùng trên nhiều instance.

## 12. Đo hiệu quả thật: không chỉ đếm số batch

Một dashboard tốt cho post-processing batching gồm:

| Metric | Ý nghĩa |
| --- | --- |
| `postprocess.enqueue.total` | Số item được tiếp nhận vào queue/outbox theo contract |
| `postprocess.enqueue.rejected.total` | Số item bị từ chối vì quá tải |
| `postprocess.queue.depth` | Số item đang chờ |
| `postprocess.queue.oldest_age.seconds` | Tuổi của phần tử cũ nhất đang chờ |
| `postprocess.batch.flush.total` | Số lần thử flush |
| `postprocess.batch.size` | Phân bố số item mỗi batch |
| `postprocess.batch.duration` | Thời gian xử lý một batch |
| `postprocess.items.success.total` | Số item xử lý thành công theo kết quả sink |
| `postprocess.items.failed.total` | Số item thất bại |
| `postprocess.retry.total` | Số lần retry |
| `postprocess.dead_letter.total` | Số item bị cách ly để xử lý thủ công |

Tên metric chỉ là **đề xuất theo ứng dụng**, không phải những metric Spring tự có.

Với Micrometer, batch duration có thể dùng `Timer`, batch size dùng `DistributionSummary`, queue depth dùng `Gauge`; success/error dùng `Counter`. Không đặt `eventId`, `orderId`, `correlationId` hoặc message text làm metric tag vì cardinality rất cao; dùng ID trong structured logs/tracing.

Một vài tiêu chí hiệu năng hữu ích:

- **Throughput:** items/s đã xử lý thành công, không chỉ items/s đã enqueue.
- **Batch fill ratio:** batch size thực tế / maxBatchSize. Nếu luôn thấp, batch interval quá ngắn hoặc lưu lượng thấp.
- **Queueing latency:** từ enqueue đến bắt đầu xử lý, đặc biệt p95/p99.
- **End-to-end latency:** từ sự việc nghiệp vụ đến khi side effect hoàn tất.
- **Backlog age:** nếu tăng liên tục, sink/worker đang không theo kịp.
- **Retry amplification:** tổng số lần thử xử lý / số item độc lập; retry storm có thể xóa lợi ích của batch.

**Dấu hiệu quá tải nguy hiểm:** queue tăng, oldest age tăng, CPU/connection pool cao, số item thành công mỗi giây không tăng dù batch size hoặc worker tăng. Tăng concurrency có thể làm tình hình tệ hơn.

## 13. Cách benchmark và điều chỉnh

Thay vì chọn `maxBatchSize=1000` vì “càng nhiều càng tốt”, hãy thử nghiệm có kiểm soát.

**Bước 1 — Chốt workload.** Event/second ở steady state và peak, kích thước payload, phân bố loại event, chi phí sink, tỉ lệ lỗi, concurrency, yêu cầu consistency và SLA latency.

**Bước 2 — Chọn baseline.** Đo cách xử lý từng event: throughput, p95/p99, số round trip, CPU, DB connections và số tác vụ mất/lỗi.

**Bước 3 — Thử nhiều batch sizes.** Chẳng hạn 10, 50, 100, 250 với `maxWait` như 50 ms, 200 ms, 1 s tùy yêu cầu. Giữ các yếu tố khác tương đối cố định.

**Bước 4 — Đo cả low traffic và burst.** Batch chỉ đạt max size khi tải đủ lớn. Ở low traffic, max wait quyết định phần lớn latency.

**Bước 5 — Thử failure modes.** Sink trả 429/503, partial success, timeout mơ hồ, một poison event, worker crash, shutdown, queue full, rollback transaction, retry.

**Bước 6 — Chốt giới hạn hoạt động.** Max queue depth, max retry attempts, max payload bytes, max in-flight batches, cảnh báo oldest-age, DLQ và rollback/backoff policy.

Không benchmark bằng `Thread.sleep` hoặc chỉ nhìn vài dòng console. Với database, cần xác nhận **driver thực sự hỗ trợ batch hiệu quả** và dùng đo lường ở cả Java lẫn hệ thống đích.

## 14. Các lỗi thiết kế phổ biến

### Sai 1 — @Async cho mọi event rồi gọi đó là batching

~~~java
@Async
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    jdbcTemplate.update(
        "INSERT INTO audit(order_id) VALUES (?)",
        event.orderId()
    );
}
~~~

Mỗi event vẫn tạo một `UPDATE/INSERT` riêng và có thể tốn một task của executor. Đây là **asynchronous processing**, không phải bulk batching. Khi cần batch, hãy gom event vào một queue/stream rồi gọi API bulk thích hợp.

### Sai 2 — Không giới hạn queue

`new LinkedBlockingQueue<>()` có thể cho phép queue lớn tới giới hạn nguyên rất cao về mặt API. Nếu publisher nhanh hơn consumer, RAM có thể tăng cho tới khi ứng dụng bị áp lực memory. Dùng queue bounded hoặc broker có quota/backpressure.

### Sai 3 — Chỉ flush khi đủ B item, không có timeout

Nếu lưu lượng giảm hoặc hệ thống sắp shutdown, phần dư có thể nằm mãi. Cần time-trigger, flush-on-shutdown có giới hạn và/hoặc durable queue.

### Sai 4 — Flush trực tiếp trên request thread khi batch đầy

Request tình cờ chạm ngưỡng sẽ trả chậm bất thường. Nếu mục đích là tối ưu request latency, tách worker khỏi thread request.

### Sai 5 — Drain queue rồi nuốt exception

Khi sink thất bại, item đã bị lấy khỏi queue. Nếu không có cơ chế xử lý lỗi/ACK/retry, dữ liệu có thể mất. Phải quyết định nghĩa vụ delivery trước khi chọn buffer.

### Sai 6 — Coi @TransactionalEventListener(AFTER_COMMIT) là durable

Callback sau commit tránh xử lý trước khi dữ liệu commit, nhưng process crash giữa commit và callback/enqueue vẫn mất task. Cần outbox khi yêu cầu bền vững.

### Sai 7 — Retry nguyên batch vô hạn không có idempotency

Một item lỗi vĩnh viễn có thể làm hàng đợi bị chặn; retry hàng loạt cũng có thể gửi trùng những item đã thành công một phần. Dùng retry có giới hạn, DLQ, partial ACK và event ID ổn định.

### Sai 8 — Bỏ qua ordering và partition khi scale

Nhiều worker có thể làm event `OrderCancelled` hoàn thành trước `OrderPlaced` ở hệ thống đích. Nếu consumer yêu cầu thứ tự theo aggregate, dùng partition/sequence và quy tắc đồng bộ phù hợp.

### Sai 9 — Batch mọi loại event vào một bulk call

Các event có schema/điểm đến/SLA khác nhau có thể không cùng một API batch. Gom nhóm theo target, event type, tenant/partition hoặc khóa phù hợp **nhưng không lộ thông tin nhạy cảm** và không tạo quá nhiều queue.

### Sai 10 — Đếm publish như đã xử lý thành công

`publishEvent` return không chứng minh transaction commit, worker ACK hay sink success. Cần metric ở đúng điểm enqueue, flush, ACK và retry.

## 15. Checklist trước khi triển khai production

- [ ] Xác định **việc hậu kỳ** có được trì hoãn và cho phép eventual consistency hay không.
- [ ] Chốt yêu cầu **mất dữ liệu được hay không**; nếu không, dùng outbox/broker thay vì chỉ RAM.
- [ ] Đặt `maxBatchSize`, `maxWait`, `queueCapacity` và giới hạn byte.
- [ ] Có đường flush cho traffic thấp và partial batch.
- [ ] Có backpressure/reject/timeout rõ ràng khi queue đầy.
- [ ] Listener enqueue nhanh; không bất ngờ chạy bulk I/O trên request thread.
- [ ] Có cơ chế chỉ xử lý event **đã commit** khi nghiệp vụ yêu cầu.
- [ ] Batch worker có claim/ACK/retry, idempotency và DLQ theo hợp đồng sink.
- [ ] Xử lý đúng partial-success và timeout không rõ kết quả.
- [ ] Không vô tình thay đổi thứ tự của một aggregate có dependency.
- [ ] Kiểm thử burst, low traffic, crash, shutdown, retry, queue full, poison item và transaction rollback.
- [ ] Quan sát queue depth, oldest age, batch size, throughput, lỗi và p95/p99 latency.
- [ ] Benchmark với dữ liệu thật thay vì dựa vào lý thuyết “batch càng lớn càng nhanh”.

### Ghi nhớ

~~~text
Một event -> một side effect
    dễ hiểu, nhưng tốn overhead I/O khi lưu lượng lớn.

Nhiều event -> một batch
    tăng throughput nếu sink hỗ trợ bulk,
    đổi lại thêm thời gian chờ, RAM, backpressure và logic lỗi.

@EventListener
    dispatch trong process, không tự bảo đảm durability.

@Async
    chuyển thread, không tự gom batch.

@Scheduled / worker
    có thể kích hoạt flush; cần giới hạn size/time.

@TransactionalEventListener(AFTER_COMMIT)
    ràng buộc thời điểm sau commit, không cứu crash window.

Transactional outbox + consumer batch + ACK/idempotency
    khi cần tính bền vững và xử lý đáng tin cậy.
~~~

**Kết luận:** batch hóa tác vụ hậu kỳ là bài toán **tối ưu I/O có kiểm soát**, không chỉ là một annotation của Spring. Một thiết kế tốt phải nói rõ cái gì được gom, khi nào flush, queue đầy xử lý thế nào, một batch lỗi được retry/ACK ra sao, và sự kiện đã commit có bị mất khi process dừng hay không.

## Tài liệu chính thức

- [Spring Framework 6.2 — ApplicationContext Events và asynchronous listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [SimpleApplicationEventMulticaster — Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [JdbcTemplate — Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Micrometer — Timers, Counters, Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts.html)
