# Khi event không phù hợp với tải cao trong Spring Framework Application Events

## 1. Bối cảnh: event tách code, không tự tạo thêm năng lực xử lý

Trong Spring, `ApplicationEventPublisher.publishEvent(...)` và `@EventListener` giúp các thành phần trao đổi sự kiện nghiệp vụ mà producer không cần biết trực tiếp mọi consumer. Đây là cách thiết kế tiện lợi cho audit, cache invalidation, cập nhật projection hoặc những phản ứng có thể tách khỏi use case chính.

Tuy nhiên, **Spring Application Events là cơ chế phân phát event nội bộ `ApplicationContext`**, không tự cung cấp durable queue, broker, consumer group, offset, replay hay distributed backpressure. Một kiến trúc có nhiều `@EventListener` không mặc nhiên xử lý được tải cao hơn một use case gọi service trực tiếp.

Ví dụ:

~~~text
POST /orders
     |
     v
OrderService.placeOrder()
     |
     +--> save Order
     |
     +--> publish(OrderPlaced)
              |
              +--> AuditListener          10 ms
              +--> SearchIndexListener    20 ms
              +--> EmailListener         150 ms
              +--> AnalyticsListener      40 ms
              +--> PromotionListener      30 ms
~~~

Nếu năm listener trên chạy đồng bộ, nối tiếp trên request thread, tổng thời gian handler theo giả định là **250 ms**, chưa tính DB của use case, network của controller hay overhead của framework. Chỉ một listener phụ thuộc API ngoài bị treo có thể làm request chậm. Thêm `@Async` có thể làm caller trả về nhanh hơn, nhưng phần việc vẫn phải chạy ở worker thread và phải dùng CPU/DB/network.

*Các thời gian trên chỉ minh họa, không phải benchmark của Spring.*

**Vấn đề cần đánh giá không phải “event có nhanh hơn method call không?” mà là: hệ thống có đủ capacity, độ trễ, backpressure, transaction semantics và recovery cho loại công việc này hay không?**

### Mục tiêu bài học

Sau bài này, người học có thể:

- Hiểu chi phí `publishEvent` và listener trên đường đồng bộ.
- Phân tích fan-out, event chain, số handler invocations và amplification.
- Phân biệt **request latency**, **event processing latency**, **throughput thành công** và **backlog**.
- Biết tại sao `@Async` không tự giải quyết tải cao; chọn `ThreadPoolTaskExecutor` bounded và quan sát rejection.
- Biết khi nào nên dùng service call trực tiếp, batching, coalescing, durable job, transactional outbox hoặc broker.
- Xây dựng benchmark/load test đo bottleneck thật thay vì suy từ microbenchmark.
- Rà soát hậu quả về transaction, ordering, idempotency và graceful shutdown.
- Chạy ví dụ Java 17+ để quan sát listener đồng bộ giữ publisher và fan-out nhân số lần xử lý.

## 2. Cơ chế dispatch: Spring Application Events hoạt động thế nào?

`ApplicationEventPublisher` là API công bố sự kiện. Với ứng dụng Spring Framework thông thường, `ApplicationContext` phân phát event tới `ApplicationEventMulticaster`, rồi multicaster chọn các listener phù hợp.

`SimpleApplicationEventMulticaster` mặc định xử lý listener thông thường **trên thread của caller** khi không có executor riêng. API `publishEvent` nói về việc chuyển event vào cơ chế dispatch, chứ không phải lời hứa rằng mọi consumer sẽ thành công hay đã commit side effect.

~~~text
publisherThread
    |
    +--> publishEvent(new OrderPlaced(...))
           |
           +--> audit listener
           +--> projection listener
           +--> notification listener
           |
           v
        return from publishEvent
    |
    +--> continue request
~~~

Trong dispatch đồng bộ, listener chạy xong mới trả về; exception chưa được bắt có thể truyền về publisher. Nếu đang ở `@Transactional` và transaction manager áp dụng rollback rule tương ứng, lỗi listener có thể khiến transaction nguồn rollback.

Điểm thuận lợi là **đơn giản, dễ debug và dễ giữ transaction context**. Nhưng dưới tải cao, tất cả công việc listener có thể góp phần kéo dài request. Spring event **không miễn phí** chỉ vì producer không gọi listener trực tiếp.

### 2.1. Chi phí của một event nằm ở những tầng nào?

- Tạo và giữ payload (POJO/record, metadata, trace context).
- Lookup listener theo event type/generic/condition.
- Reflection/adapter/proxy khi dùng `@EventListener` hoặc AOP.
- Công việc nghiệp vụ thật trong mọi handler: CPU, DB, HTTP, serialization, lock.
- Nếu async: task allocation, enqueue/dequeue, thread scheduling, context propagation.
- Nếu nhiều event con: số lượt dispatch và side effect mới.
- Nếu retry: cùng task hoặc event được xử lý nhiều lần, yêu cầu deduplication.

Trong nhiều ứng dụng, **I/O của listener mới là bottleneck**, không phải bản thân việc Spring dispatch một object. Vì vậy tối ưu chi phí lookup hoặc tạo record nhỏ thường có tác dụng thấp hơn giảm DB round trip, HTTP call, fan-out hoặc xử lý lặp.

### 2.2. Một số đo dễ bị đánh đồng

| Chỉ số | Mô tả | Sai lầm phổ biến |
| --- | --- | --- |
| Request p95/p99 | Thời gian API từ đầu đến phản hồi | Đánh giá hệ thống ổn chỉ vì async làm HTTP nhanh |
| Publish latency | Thời gian lời gọi publish | Đánh đồng đã publish với tất cả consumer đã xử lý |
| Consumer execution time | Thời gian chạy thân handler | Quên thời gian nằm trong queue |
| End-to-end event lag | Từ lúc event xảy ra đến khi side effect đạt mục tiêu | Chỉ xem thời gian execute, không xem queue wait |
| Successful throughput | Số công việc hoàn tất đúng mỗi giây | Dùng published/s làm processed/s |
| Backlog/queue depth | Công việc còn đang chờ | Queue tăng liên tục nhưng không có exception |
| Error/retry rate | Thất bại và số lần thử lại | Retry storm làm tăng tổng tải |

Một thiết kế tải cao tốt cần **successful throughput ổn định** và độ trễ đạt SLA, không chỉ gọi publisher thật nhanh.

## 3. Listener đồng bộ có thể làm request bị kẹt

Trong mô hình thường gặp:

~~~text
HTTP Request Thread
    |
    +--> OrderService.place()
            |
            +--> repository.save(order)
            |
            +--> publish(OrderPlaced)
                    |
                    +--> AuditListener: CPU 5 ms
                    +--> SearchListener: DB 30 ms
                    +--> EmailListener: HTTP 200 ms
                    |
                return
    |
    +--> HTTP response
~~~

Nếu một API phụ bên ngoài bị timeout, request thread bị giữ lâu hơn mong muốn. Dưới tải cao, số request threads có hạn; nhiều request cùng đợi listener chậm làm giảm khả năng nhận request mới và kéo p99 lên cao.

### 3.1. Các dạng coupling gián tiếp

**Latency coupling:** thêm listener mới làm producer chậm, dù controller không đổi code.

**Failure coupling:** handler sâu ném exception và trả ngược; nghiệp vụ chính có thể bị fail/rollback dù đó chỉ là chức năng gửi thông báo.

**Transaction coupling:** listener cùng thread có thể tham gia transaction của publisher nếu resource và transaction manager phù hợp; handler lâu sẽ giữ transaction/connection/lock lâu hơn.

**Lifecycle coupling:** event được xử lý trong lúc context khởi động/đóng có thể phụ thuộc bean chưa sẵn sàng hoặc đang destroy.

### 3.2. Đừng dùng event để che một bước bắt buộc

Nếu thanh toán hoặc xác thực hạn mức phải thành công trước khi đặt đơn thành công, một listener side effect bí mật có thể khiến hợp đồng khó hiểu. Cân nhắc gọi trực tiếp domain/application service hoặc orchestrator có trạng thái. **Phụ thuộc rõ ràng đôi khi tốt hơn coupling ẩn qua event.**

Ngược lại, audit phụ trợ, analytics, cache invalidation hoặc notification không bắt buộc có thể là consumer của event sau khi sự thật nghiệp vụ đã hình thành. Điều quan trọng là xác định rõ **thành công của command có phụ thuộc công việc đó hay không**.

## 4. Fan-out: tải listener có thể lớn hơn tải publisher nhiều lần

Giả sử mỗi `OrderPlaced` có bốn listener:

~~~text
                   +--> audit
                   |
OrderPlaced -------+--> search indexing
                   |
                   +--> email
                   |
                   +--> analytics
~~~

Nếu có 1.000 event mỗi giây, hệ thống có khoảng **4.000 listener invocations mỗi giây**, chưa kể những listener phát thêm event hoặc retry. Một event có nhiều consumer không phải “chạy một lần” theo nghĩa tài nguyên.

Một chuỗi có thể phình rộng:

~~~text
OrderPlaced
  |
  +--> InvoiceIssued --> AccountingUpdated
  |
  +--> PaymentAuthorized
  |       |
  |       +--> InventoryReserved
  |       +--> FulfillmentReady
  |
  +--> SearchIndexed
  +--> EmailScheduled
~~~

Độ sâu, fan-out, fan-in và cycle đều có thể làm tải tăng:

- **Depth:** nhiều bước nối tiếp, latency tích lũy, khó lần dấu.
- **Fan-out:** một event kích hoạt nhiều listener/task/side effect.
- **Fan-in:** nhiều nhánh cùng điều kiện để tiếp tục; có thể race.
- **Cycle:** một listener phát event quay trở lại chính loại sự kiện cũ; có thể tạo event storm.
- **Retries:** khi downstream lỗi, số lần xử lý tăng đúng lúc hệ thống yếu nhất.

Nếu một event tạo trung bình `b` event con ở mỗi tầng và có `d` tầng, số node lý thuyết có thể tăng theo `1 + b + b² + ... + b^d`. Đây là mô hình **minh họa**, không phải công thức Spring tự sinh event, nhưng cho thấy vì sao graph quan trọng.

### 4.1. Event in-process không chia tải đa pod tự động

Listener được đăng ký trong một context cụ thể. Một event publish ở pod A **không tự được truyền đến** listener ở pod B hoặc C. Scale số pod chỉ giúp khi traffic/event nguồn được phân phối tới các pod theo thiết kế.

Nếu muốn nhiều worker chia một dòng job, cần queue/broker/job table với consumer group, partition hoặc cơ chế claim job phù hợp. `ApplicationEventPublisher` không có khái niệm consumer group như một broker.

## 5. @Async: dời bottleneck sang executor, không loại bỏ bottleneck

Một listener có thể dùng `@Async`:

~~~java
@Component
public class SearchListener {
    @Async("searchExecutor")
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        searchIndex.update(event.orderId());
    }
}
~~~

Đây là snippet, cần Spring bean, import, `@EnableAsync`, executor và `OrderPlaced`/`searchIndex` tương ứng. Khi async proxy hoạt động, publisher có thể trả về trước khi thân handler hoàn tất. Thời gian xử lý thực sự chỉ chuyển từ request thread sang worker thread.

Nếu số task vào lớn hơn năng lực worker trong một khoảng dài, queue sẽ tăng. Nếu queue có giới hạn, task có thể bị từ chối khi vượt capacity. Nếu queue không giới hạn, quá tải dễ bị che bởi backlog, allocation và GC/heap pressure.

### 5.1. Công thức capacity dùng để suy nghĩ, không dùng làm cấu hình tuyệt đối

Giả sử:

- `λ` là số event/giây.
- `f` là số handler tasks trung bình mỗi event.
- `w` là thời gian một task chiếm worker, tính bằng giây.

Tải vào theo task là `λ × f` task/giây. Khi ổn định và các giả định phù hợp, Little's law gợi ý concurrency đang xử lý xấp xỉ `λ × f × w`.

~~~text
Arrival          = 500 events/s
Average fan-out  = 3 tasks/event
Service time     = 0.020 s/task

Task arrival rate= 1,500 tasks/s
In-service work  ≈ 1,500 * 0.020 = 30 concurrent tasks
~~~

**Không suy ra ngay cần 30 threads.** Đây chỉ là ước lượng: CPU-bound/I/O-bound, độ biến thiên, p95/p99, burst traffic, retry và giới hạn downstream quyết định capacity thực tế. Nếu CPU có 4 cores và task CPU-bound nặng, 30 runnable threads có thể làm throughput kém đi do context switching.

### 5.2. Backlog tăng khi không theo kịp

~~~text
Task arrival rate  = 2,000 tasks/s
Task service rate  = 1,500 tasks/s
Growth             ≈ 500 tasks/s
After 60 seconds   ≈ 30,000 queued tasks (nếu không có điều tiết)
~~~

Ví dụ này giả định tốc độ không đổi và không có drop/backpressure; không phải kết quả đo. Mỗi task giữ object event, closure, trace data... nên queue tăng có thể ngốn heap. Hệ thống trả HTTP nhanh trong khi tác vụ nền bị trễ nhiều phút vẫn có thể **thất bại ở SLA nghiệp vụ**.

## 6. ThreadPoolTaskExecutor: chọn bounded queue, worker và rejection policy

Một cấu hình minh họa cho workload nội bộ có thể bỏ qua hoặc tự rebuild:

~~~java
@Configuration
@EnableAsync
public class AsyncEventConfig {

    @Bean("searchExecutor")
    public ThreadPoolTaskExecutor searchExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("search-event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
~~~

Đây là đoạn cấu hình cần import `Configuration`, `EnableAsync`, `Bean` và `ThreadPoolTaskExecutor`, không phải class runnable độc lập. Các số 4/8/200 chỉ mang tính ví dụ. Khi bean do Spring quản lý, container thực hiện lifecycle init/destroy.

### 6.1. Queue ảnh hưởng cách pool mở rộng

Với `ThreadPoolExecutor` bên dưới, pool thường sử dụng các core threads trước; khi core threads bận mà queue còn chỗ, task được enqueue trước khi mở rộng lên `maxPoolSize`. Vì vậy **chỉ tăng maxPoolSize nhưng để queue rất lớn chưa chắc tăng throughput**.

Spring `ThreadPoolTaskExecutor` mặc định không phải một bounded queue nhỏ phù hợp mọi ứng dụng; theo Javadoc phiên bản 6.2, cấu hình mặc định gần như single worker với queue rất lớn. Cần đặt giới hạn theo workload được đo.

`queueCapacity=0` tạo hành vi gần direct handoff và có thể tăng worker nhanh, nhưng cũng tạo áp lực thread nếu `maxPoolSize` quá cao. Không chọn bằng cảm tính.

### 6.2. Lỗi submit khác lỗi trong worker

- **Scheduling rejection:** executor đang shutdown hoặc queue/pool đầy; `TaskRejectedException`/`RejectedExecutionException` có thể xảy ra ngay khi submit, tùy executor/policy.
- **Worker execution error:** task đã được nhận rồi ném exception trong thân listener. Với `@Async void`, lỗi không tự truyền về publisher; `AsyncUncaughtExceptionHandler` là điểm quan sát liên quan.
- **Timeout downstream:** chưa biết side effect đã xảy ra hay chưa; retry cần idempotency.

Một số rejection handler (như caller-runs trong điều kiện áp dụng) có thể thực thi task trên caller để tạo backpressure, nhưng làm tăng latency request và có thể thay đổi failure/transaction semantics. Chính sách “discard” sẽ làm mất việc nếu không có persistence. Không có một rejection policy đúng cho mọi event.

### 6.3. Bulkhead tách workload

Đừng nhất thiết dùng chung một pool toàn ứng dụng:

~~~text
OrderPlaced
   |
   +--> Audit               sync (nếu yêu cầu)
   +--> Search indexing     bounded searchExecutor
   +--> Notification        bounded notificationExecutor
   +--> Analytics           batch/stream worker
~~~

Một notification provider chậm có thể ngốn worker của pool chung, làm chậm những tác vụ khác. **Bulkhead** chia tài nguyên theo loại công việc và downstream, nhưng chia quá nhỏ cũng làm giảm khả năng tận dụng capacity nhàn rỗi; cần benchmark.

### 6.4. @Async không lưu job bền vững

Executor queue nằm trong RAM. Nếu process chết sau database commit nhưng trước khi worker xử lý, task không được tự phục hồi. `@Async` là cơ chế chạy song song, **không phải durable messaging**.

## 7. Ví dụ Java 17+ hoàn chỉnh: đồng bộ giữ publisher và nhân số listener

Ví dụ Spring Framework 6.2.8, Java 17+ và Maven **không dùng Spring Boot**. Nó chứng minh hai điều có thể kiểm chứng mà không suy đoán QPS:

1. Listener đồng bộ có thể giữ lời gọi `publishEvent(...)` chưa trả về.
2. Một event được ba listener xử lý sẽ sinh ba handler invocations; với 1.001 event có 3.003 invocation.

Ta dùng `CountDownLatch` để tạo điểm chờ có kiểm soát, không dùng `Thread.sleep` như một benchmark.

### 7.1. Cấu trúc thư mục

~~~text
sync-fanout-demo/
├── pom.xml
└── src/main/java/SyncFanoutDemo.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>sync-fanout-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>SyncFanoutDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. src/main/java/SyncFanoutDemo.java

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public final class SyncFanoutDemo {

    public record WorkArrived(long id) { }

    public static class Gate {
        final CountDownLatch started = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
    }

    public static class Stats {
        final AtomicInteger slow = new AtomicInteger();
        final AtomicInteger audit = new AtomicInteger();
        final AtomicInteger projection = new AtomicInteger();

        public int total() {
            return slow.get() + audit.get() + projection.get();
        }
    }

    public static class SlowListener {
        private final Gate gate;
        private final Stats stats;

        public SlowListener(Gate gate, Stats stats) {
            this.gate = gate;
            this.stats = stats;
        }

        @Order(10)
        @EventListener
        public void on(WorkArrived event) {
            stats.slow.incrementAndGet();

            if (event.id() == 1L) {
                System.out.println("SLOW_LISTENER_STARTED");
                gate.started.countDown();
                try {
                    if (!gate.release.await(30, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                            "Listener gate timed out"
                        );
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                        "Interrupted", ex
                    );
                }
                System.out.println("SLOW_LISTENER_FINISHED");
            }
        }
    }

    public static class AuditListener {
        private final Stats stats;

        public AuditListener(Stats stats) {
            this.stats = stats;
        }

        @Order(20)
        @EventListener
        public void on(WorkArrived event) {
            stats.audit.incrementAndGet();
        }
    }

    public static class ProjectionListener {
        private final Stats stats;

        public ProjectionListener(Stats stats) {
            this.stats = stats;
        }

        @Order(30)
        @EventListener
        public void on(WorkArrived event) {
            stats.projection.incrementAndGet();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        Gate gate() {
            return new Gate();
        }

        @Bean
        Stats stats() {
            return new Stats();
        }

        @Bean
        SlowListener slowListener(Gate gate, Stats stats) {
            return new SlowListener(gate, stats);
        }

        @Bean
        AuditListener auditListener(Stats stats) {
            return new AuditListener(stats);
        }

        @Bean
        ProjectionListener projectionListener(Stats stats) {
            return new ProjectionListener(stats);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            Gate gate = context.getBean(Gate.class);
            Stats stats = context.getBean(Stats.class);
            AtomicBoolean firstReturned = new AtomicBoolean(false);

            Thread publisherThread = new Thread(() -> {
                context.publishEvent(new WorkArrived(1L));
                firstReturned.set(true);
                System.out.println("FIRST_PUBLISH_RETURNED");
            }, "publisher-thread");

            publisherThread.start();

            if (!gate.started.await(10, TimeUnit.SECONDS)) {
                gate.release.countDown();
                throw new IllegalStateException(
                    "First listener did not start"
                );
            }

            System.out.println(
                "PUBLISH_BLOCKED=" + !firstReturned.get()
            );

            gate.release.countDown();
            publisherThread.join(10_000);
            if (publisherThread.isAlive()) {
                throw new IllegalStateException(
                    "Publisher thread did not finish"
                );
            }

            for (long id = 2L; id <= 1001L; id++) {
                context.publishEvent(new WorkArrived(id));
            }

            System.out.println("PUBLISHED=1001");
            System.out.println(
                "HANDLER_INVOCATIONS=" + stats.total()
            );
        }
    }
}
~~~

Chạy từ thư mục `sync-fanout-demo` bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

Đầu ra **do chương trình in**, khi chạy bình thường không timeout:

~~~text
SLOW_LISTENER_STARTED
PUBLISH_BLOCKED=true
SLOW_LISTENER_FINISHED
FIRST_PUBLISH_RETURNED
PUBLISHED=1001
HANDLER_INVOCATIONS=3003
~~~

### 7.4. Phân tích kết quả

- Spring context được refresh khi tạo `AnnotationConfigApplicationContext(Config.class)`, nên cả ba phương thức `@EventListener` đã được đăng ký trước khi publish event.
- `publisherThread` phát `WorkArrived(1)`. `SlowListener` được xếp trước hai listener còn lại với `@Order(10)` và chạy trên publisher thread mặc định.
- Listener in `SLOW_LISTENER_STARTED`, báo latch `started`, rồi chờ `release`. Main nhận latch và in `PUBLISH_BLOCKED=true` bởi `publishEvent` chưa thể trả về trong lúc listener đang chờ.
- Sau khi main mở latch, listener tiếp tục, in `SLOW_LISTENER_FINISHED`; audit và projection listeners của event đầu cũng chạy. Sau đó mới có `FIRST_PUBLISH_RETURNED`.
- Main publish thêm 1.000 event; mỗi event gọi ba listener. Tổng **1.001 × 3 = 3.003** invocation là giá trị xác định.

Đây **không phải benchmark throughput**: không có dữ liệu DB/network thật, không đo QPS, không mô phỏng tài nguyên bị tranh chấp. Ví dụ chỉ làm rõ sự gắn kết giữa publisher và listener đồng bộ, cộng thêm fan-out. Để đánh giá tải cao phải có load test đại diện sản xuất.

## 8. @Async đôi khi còn làm vấn đề khó nhìn thấy hơn

### 8.1. CPU-bound không cần thêm vô hạn threads

Nếu handler thực hiện tính toán CPU nặng, tăng worker vượt số CPU hữu hiệu có thể tăng context switching, memory allocation và thời gian GC. Nên đo CPU, lock contention, allocation, heap và tối ưu thuật toán hoặc batch work.

### 8.2. I/O-bound chịu giới hạn downstream

Nếu handler chờ DB, HTTP API hoặc search engine, tăng concurrency có thể giúp **đến một mức**. Nhưng khi DB pool hoặc rate limit đã bão hòa, tăng số task chỉ làm timeout và retry nhiều hơn.

Cần có timeout, circuit breaker, concurrency limit và bulkhead theo downstream. Nếu email provider chỉ nhận 200 requests/s, một executor đẩy 2.000 requests/s không khiến provider nhanh hơn.

### 8.3. Async làm thay đổi thứ tự

Hai event cho cùng aggregate có thể hoàn tất đảo thứ tự trên hai worker. `@Order` chỉ điều chỉnh thứ tự dispatch listener trong điều kiện phù hợp, không bảo đảm completion order xuyên executor/process. Nếu projection cần tính nhất quán, sử dụng aggregate version/sequence hoặc consumer xử lý tuần tự theo key.

### 8.4. Async đổi ranh giới transaction

`@Async` thường chạy trên worker thread, **không kế thừa imperative thread-bound transaction** của publisher. Một listener trước đây chạy đồng bộ trong transaction có thể không còn tham gia transaction ấy; lỗi của nó không tự rollback aggregate đã commit.

Không chuyển bước nghiệp vụ bắt buộc sang async nếu API contract vẫn hứa rằng request thành công đồng nghĩa toàn bộ bước đã hoàn tất.

## 9. Global multicaster async không phải giải pháp chung

Spring cho phép cấu hình executor ở `SimpleApplicationEventMulticaster`:

~~~java
// Mã minh họa trong class @Configuration có import/bean phù hợp.
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster(
        ThreadPoolTaskExecutor eventExecutor) {
    SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    return multicaster;
}
~~~

Tuy nhiên, thay multicaster sang executor có thể ảnh hưởng nhiều listener và event lifecycle hơn một `@Async` đặt trên handler cụ thể.

- `ApplicationListener.supportsAsyncExecution()` có thể buộc listener chạy trên publisher thread; transaction-synchronized listeners là trường hợp điển hình.
- Thread context và transaction không tự được chuyển qua worker.
- Handler lỗi và executor rejection có đường xử lý khác nhau; một số implementation có thể fallback thực thi tại caller khi task bị từ chối.
- Cùng một pool làm các workload liên quan chặt về capacity; một listener chậm có thể chiếm tài nguyên của những listener khác.
- Event lifecycle khi shutdown có thể cần xử lý trên luồng phù hợp, không giao vào pool đang dừng.

Một lựa chọn thường dễ kiểm soát hơn là **@Async chọn lọc, executor bounded theo nhóm workload và outcome monitoring**; với công việc bắt buộc cần khả năng khôi phục, dùng durable pipeline.

## 10. Spring event in-process khác queue/broker như thế nào?

| Khả năng | Spring Application Events | Durable queue/broker/job pipeline được cấu hình đúng |
| --- | --- | --- |
| Dispatch trong cùng JVM/context | Có | Qua consumer/adapter |
| Persist event mặc định | Không | Có thể có theo cơ chế, retention và cấu hình |
| Phát lại sau crash | Không tự động | Có thể qua log/offset/job storage |
| Consumer group phân tải nhiều node | Không có sẵn | Nhiều hệ thống hỗ trợ |
| Bounded backlog/backpressure hợp đồng | Không phải API của event bus | Có thể thiết kế qua queue/consumer |
| Retry/ack/checkpoint | Không tự động | Có thể triển khai, cần policy |
| Theo dõi consumer lag | Cần tự instrument | Thường có metric/cơ chế hỗ trợ |
| Exactly-once side effect toàn hệ thống | Không | Cũng không tự động; cần idempotency và transaction |
| Thay đổi schema/version qua service | Phụ thuộc code trong JVM | Cần contract, schema evolution và governance |

Không nên coi broker là lựa chọn luôn tốt hơn. Kafka, RabbitMQ, cloud queue và database job table khác nhau về ordering, retention, consumer model và chi phí vận hành. Với listener nhỏ, nhẹ, trong một service, event in-process có thể đơn giản và an toàn hơn.

### 10.1. Transactional outbox

Khi một sự thật nghiệp vụ phải được chuyển giao dù ứng dụng crash sau commit:

~~~text
Transaction T1:
    save Order
    insert outbox(eventId, OrderPlaced, payload)
    COMMIT
       |
       v
Outbox dispatcher
    |
    +--> message broker / worker
    +--> retry, monitoring, deduplication
       |
       v
Consumer:
    process with stable eventId
    commit local state
    ack / checkpoint
~~~

Cơ chế **transactional outbox** ghi aggregate state và ý định phát event trong **cùng transaction database**. Nếu transaction rollback, cả hai không được commit. Nếu commit rồi ứng dụng chết, dispatcher sau đó có thể đọc bản ghi pending.

Với tải cao, outbox vẫn cần xử lý batch polling, index, cleanup, connection pool, parallel claim, lag và retry. Nó giải quyết **durability/recovery**, không tự xóa bài toán throughput. Delivery thường là **at-least-once**, nên consumer vẫn cần idempotency.

## 11. Khi nào nên chọn direct call, batching hoặc broker?

| Nhu cầu | Cơ chế thường phù hợp | Lý do |
| --- | --- | --- |
| Bước bắt buộc quyết định command thành công | Direct service/domain call | Kết quả, deadline, transaction rõ |
| Audit/cache listener nhỏ, nội bộ, có thể bỏ | Spring event sync | Ít hạ tầng |
| Phản ứng nội bộ chậm, có thể tái tạo | `@Async` + bounded executor | Tách latency request và quản lý tài nguyên |
| Nhiều update cùng key không cần xử lý từng state trung gian | Coalescing/latest-state reconciliation | Loại công việc lỗi thời |
| Nhiều cập nhật có thể xử lý bulk | Batching | Giảm round trip và overhead |
| Công việc phải sống qua restart | Durable job table/transactional outbox | Có thể retry |
| Cần scale consumer độc lập giữa service | Broker/queue có consumer group hoặc partition | Phân phối work |
| Cần lịch sử và replay theo offset | Event log/stream platform | Retention/checkpoint |
| Workflow nhiều bước có timeout/compensation | Orchestrator/saga | Có owner trạng thái và failure policy |

### 11.1. Batching để giảm round trips

Thay vì 10.000 `PriceChanged` gọi 10.000 lần update search index, có thể gom theo batch để dùng bulk API, giảm chi phí gọi mạng.

Nhưng batching làm tăng latency đến khi flush, cần hạn mức bộ nhớ, flush lúc shutdown, xử lý partial failure, retry và giữ ordering nếu nghiệp vụ yêu cầu. Nếu batch fail một phần, không nên coi tất cả event đều đã xử lý.

### 11.2. Coalescing theo key

Với cache invalidation, nhiều sự kiện “cấu hình key X vừa thay đổi” đôi khi có thể hợp nhất thành một lần tải **state mới nhất**. Việc này khác hẳn xử lý các fact tài chính riêng lẻ: không được gộp `PaymentCaptured` chỉ vì cùng order ID nếu chúng là các giao dịch riêng biệt.

### 11.3. Fast path và slow path

~~~text
Command/API
   |
   +--> Fast path:
   |      validate -> change aggregate -> commit
   |      respond according to SLA
   |
   +--> Slow path:
          outbox / queue / bulk processing
          search indexing, analytics, notifications
~~~

Phân biệt công việc bắt buộc trước response với công việc có thể eventual consistency. Nếu API chỉ **nhận yêu cầu** và xử lý sau, response nên thể hiện trạng thái accepted/pending và có job ID/status phù hợp, không giả vờ rằng nghiệp vụ đã hoàn tất.

## 12. Thiết kế benchmark/load test đại diện

Bản demo ở mục 7 không đo throughput. Một load test sản xuất cần đặt rõ giả thuyết và ranh giới:

- Endpoint nào bị ảnh hưởng bởi fan-out?
- Event xuất hiện bao nhiêu lần trên mỗi request?
- Listener nào tiêu thụ CPU, DB connection hoặc HTTP connection nhiều nhất?
- p95/p99 của API và **end-to-end event lag** có nằm trong SLA?
- Queue depth có ổn định trong một soak test dài không?
- Tăng pool size có tăng successful processed/s hay chỉ tăng timeout?
- Có xảy ra rejected tasks, duplicate side effect hoặc loss sau crash?
- Với 2× traffic, năng lực xử lý có đủ headroom không?

### 12.1. Chỉ số cần thu thập

**HTTP/use case:** RPS, p50/p95/p99, error rate, request thread pool, DB latency.

**Event:** published total, listeners invoked, processed-success total, processed-failure total, event chain depth, fan-out.

**Executor:** active threads, queue depth, queue wait time, task duration, rejected count, shutdown/drain time.

**Durable pipeline:** consumer lag, oldest pending age, retries, dead-letter, dedup count, broker/DB saturation.

**Hạ tầng:** CPU, heap, GC pause, memory allocation, database pool, connection timeouts, downstream rate limits.

Metric tên sau là **gợi ý tự định nghĩa**, không phải mặc định của Spring:

~~~text
app_event_published_total{type="OrderPlaced"}
app_event_listener_duration_seconds{listener="search"}
app_event_listener_failures_total{listener="notification"}
app_event_executor_active_threads{pool="search"}
app_event_executor_queue_depth{pool="search"}
app_event_executor_rejections_total{pool="search"}
app_event_processing_lag_seconds{consumer="billing"}
app_event_deduplicated_total{consumer="billing"}
~~~

Tránh `eventId`, `orderId` và `customerId` làm Prometheus labels vì cardinality cao; ID cần ở structured logs/tracing.

### 12.2. Một kế hoạch tải tối thiểu

1. **Baseline** với event đồng bộ và các listener hiện tại.
2. **Steady state** tăng dần input rate; xác định throughput thành công tối đa bền vững.
3. **Burst** để xem queue fill/rejection và latency spike.
4. **Soak** để phát hiện backlog tăng, heap/GC/connection leak.
5. **Downstream slowdown** giả lập DB/API phản hồi chậm và xem retry storm.
6. **Fan-out growth** thêm listener ở môi trường test để định lượng amplification.
7. **Crash/restart** sau commit trước side effect; kiểm chứng outbox/job recovery nếu cần.
8. **Duplicate delivery** với cùng event ID; xác minh idempotency.
9. **Shutdown** khi còn pending job; kiểm tra graceful drain và deadline của container.
10. **Ordering** khi async xử lý event cùng aggregate trên nhiều worker.

Gatling/k6/JMeter phù hợp với tải HTTP; JMH phù hợp microbenchmark hẹp; JFR/profiler cho CPU, allocation, lock contention. Đừng dùng `System.nanoTime()` quanh 1.000 events của demo để suy ra SLA production.

### 12.3. Phân tích đúng kết quả

Nếu request p95 giảm khi bật `@Async` nhưng queue depth và event lag tăng không ngừng, đây là hiện tượng **đổi latency thành backlog**. Nếu publisher chạy 10.000 calls/s nhưng consumer hoàn thành 1.000 calls/s, số published không nói lên năng lực thực.

Mục tiêu là **successful throughput theo kịp arrival rate trong khoảng dài**, với p99/lag/rejection/errors dưới ngưỡng chấp nhận được.

## 13. Transaction và consistency khi tối ưu tải

### 13.1. Sync listener có thể nằm trong transaction nguồn

Nếu `publishEvent` xảy ra bên trong `@Transactional`, listener đồng bộ cùng thread có thể tham gia transaction nguồn (khi transaction manager/resource/phương thức phù hợp). Nó có thể kéo dài connection/lock lifetime; exception có thể propagate gây rollback.

Khi chuyển sang async, worker **không tự thừa hưởng imperative thread-bound transaction**. Nếu side effect bắt buộc phải atomic với use case, không được đơn giản đẩy nó ra worker rồi giữ nguyên hợp đồng.

### 13.2. After-commit chỉ giải quyết thời điểm

~~~java
// Snippet trong bean có @EnableAsync, executor, import và service thực tế.
@Async("searchExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    searchIndexer.index(event.orderId());
}
~~~

Với transaction nguồn tương ứng, `AFTER_COMMIT` chỉ chạy sau khi commit thành công. Nếu transaction rollback, phase này không xử lý. Nếu publish ngoài transaction, mặc định listener không thực thi trừ khi dùng `fallbackExecution=true` có chủ đích.

**AFTER_COMMIT không phải durable delivery.** Worker có thể bị reject, process crash hoặc downstream lỗi sau commit. Nếu job phải được giao không mất, cần lưu trạng thái công việc bền vững như transactional outbox.

### 13.3. Retry, dedup và ordering

Khi tăng concurrency/retry, event có thể đến trùng hoặc hoàn tất đảo thứ tự:

- Giữ `eventId` ổn định cho cùng một fact.
- Consumer idempotent theo event ID, với lưu trữ phù hợp nhiều instance.
- Sử dụng `aggregateId` và `aggregateVersion`/sequence nếu projection cần ordering.
- Giới hạn retry, exponential backoff/jitter, alert và dead-letter/quarantine.
- Không dùng `Set<UUID>` trong bộ nhớ làm bảo đảm cluster/restart.
- Phân biệt `occurredAt`, `publishedAt` và `processedAt` để đo lag thật.
- Timeout downstream không mặc nhiên có nghĩa side effect thất bại; có thể đã hoàn thành rồi mất response.

## 14. Một quyết định thực dụng: có nên bỏ Spring event ở high-load path?

**Nên cân nhắc thay kiến trúc** khi có một hoặc nhiều dấu hiệu có bằng chứng:

- Một listener tốn phần đáng kể p95/p99 của request.
- Fan-out amplification cao, tăng khi có module mới.
- Queue async tăng đều dưới steady-state load.
- Throughput phụ thuộc tài nguyên downstream đã bão hòa.
- Request trả success nhưng side effect cần thiết có thể mất sau crash.
- Cần partition, consumer group hoặc scale handler độc lập qua nhiều node.
- Cần backpressure, checkpoint, replay và độ trễ có SLA.
- Event chain giấu workflow nhiều bước và retry/compensation không có owner.

**Chưa chắc cần thay** khi listener chỉ làm việc nhỏ, độc lập, trong một context; request/processing latency, error rate và queue depth đều ổn. Thêm broker khi không có nhu cầu có thể làm phức tạp deployment, tracing, schema evolution và eventual consistency.

### 14.1. Những câu hỏi kiến trúc cần trả lời

1. Event là **domain fact** hay đang che một command bắt buộc?
2. Nếu listener thất bại, hệ thống có phải rollback use case không?
3. Nếu crash, event có được phép mất không?
4. Sau publish, caller cần biết **accepted**, **scheduled**, hay **completed**?
5. Có bao nhiêu consumer và mỗi consumer có SLA khác nhau không?
6. Hệ thống có cần consumer group/workload partition không?
7. Event có thể coalesce mà không mất fact nghiệp vụ không?
8. Chúng ta đã đo successful throughput, lag và rejected tasks chưa?
9. Tải tăng đột biến sẽ bị giới hạn/từ chối ở đâu?
10. Nếu thêm instance, event sẽ được route tới instance nào?
11. Ai chịu trách nhiệm retry, dead-letter và xử lý duplicate?
12. Có kế hoạch shutdown và phục hồi job đang chờ không?

Nếu thiếu phần lớn câu trả lời này, thêm `@Async` vào listener thường chỉ là biện pháp tạm thời.

## 15. Các lỗi phổ biến

1. **Tưởng @EventListener mặc định async:** mặc định listener thường chạy trên publisher thread.
2. **Chuyển tất cả listener sang @Async:** request giảm latency nhưng backlog/tải downstream vẫn còn.
3. **Queue không giới hạn:** bùng nổ heap và lag trước khi xuất hiện lỗi.
4. **Chỉ tăng maxPoolSize với queue quá lớn:** pool không mở thêm worker như kỳ vọng.
5. **Không đo processed-success/s:** chỉ báo published/s đẹp dù consumer thất bại.
6. **Không xử lý TaskRejectedException:** công việc quan trọng không được giao.
7. **Không phân biệt scheduling error và worker error:** dùng sai exception handler.
8. **Dùng một executor toàn cục cho mọi workload:** listener nặng ảnh hưởng listener quan trọng.
9. **Coi global setTaskExecutor giống @Async chọn lọc:** khác phạm vi, thread và transaction semantics.
10. **Tin @Order bảo đảm completion order async:** thực tế không.
11. **Dùng in-process events để cân tải giữa pod:** không có consumer group tự động.
12. **Không đo fan-out và event chain:** một event có thể kích hoạt nhiều I/O.
13. **Retry không giới hạn:** tạo retry storm khi downstream suy yếu.
14. **Không có idempotency:** timeout/retry có thể gây duplicate email/payment.
15. **Nhầm AFTER_COMMIT với durable queue:** crash sau commit vẫn làm mất task chưa ghi bền vững.
16. **Dời bước bắt buộc sang async nhưng API trả completed:** contract sai.
17. **Gộp các fact tài chính để tiết kiệm công việc:** làm mất thông tin nghiệp vụ.
18. **Không có graceful shutdown:** in-memory queue có thể mất khi rolling deploy.
19. **Cho rằng broker tự bảo đảm exactly-once business side effect:** cần transaction/idempotency riêng.
20. **Dùng benchmark synthetic làm số QPS production:** bỏ qua DB, network, lock và GC.
21. **Giải quyết tải cao bằng thêm threads mà không sửa bottleneck:** CPU/DB vẫn bão hòa.
22. **Bỏ qua ordering/version của cùng aggregate:** projection ghi lùi state dưới concurrency.

## 16. Bài tập tự kiểm tra

1. Một event có 5 listener sync, mỗi listener tốn 40 ms. Tổng thời gian listener theo giả định tuần tự là bao nhiêu?
2. Vì sao `@Async` có thể làm HTTP p95 giảm nhưng event lag tăng?
3. Input 2.000 tasks/s, capacity 1.500 tasks/s. Backlog tăng bao nhiêu sau một phút nếu không điều tiết?
4. Tại sao tăng `maxPoolSize` có thể không tăng throughput nếu queue còn rất nhiều chỗ?
5. Vì sao `TaskRejectedException` có thể xảy ra ngay trước khi task body chạy?
6. Khi fan-out từ 2 lên 6 listener, bạn cần đo những metric nào?
7. Một event publish trong pod A có tự được nhận ở pod B không?
8. Bước thanh toán bắt buộc nên là direct call hay listener best-effort? Vì sao?
9. Khi nào có thể batch/coalesce invalidation và khi nào làm vậy làm mất fact?
10. `@TransactionalEventListener(AFTER_COMMIT)` có bảo đảm event không mất khi crash không?
11. Vì sao `@Order` không giúp projection async hoàn tất theo đúng thứ tự?
12. Nếu API trả ngay sau enqueue job, response nên biểu thị trạng thái gì?
13. Broker có tự bảo đảm exactly-once side effect với email và DB không?
14. Demo `SyncFanoutDemo` chứng minh gì và không chứng minh gì?
15. Queue depth tăng đều trong soak test là dấu hiệu gì?

**Gợi ý:** (1) 200 ms; (2) chuyển xử lý sang backlog; (3) ~30.000 tasks; (4) executor thường ưu tiên queue trước mở worker vượt core; (5) rejection ở submit; (6) p99, listener invocations/s, queue, lag, errors, CPU/DB; (7) không tự động; (8) direct/orchestration rõ kết quả; (9) gom latest state, không gộp giao dịch riêng; (10) chưa, cần durable outbox/job; (11) dispatch order khác completion order; (12) accepted/pending; (13) không; (14) sync blocking và fan-out chứ không đo QPS; (15) long-term overload.

## 17. Tổng kết

**“Khi event không phù hợp với tải cao”** không có nghĩa Spring Application Events luôn chậm. Nó có nghĩa cơ chế event nội bộ không nên bị dùng vượt quá hợp đồng thực thi của nó:

- Listener đồng bộ có thể kéo dài request và giữ transaction/threads.
- Listener async chỉ chuyển công việc sang worker pool; không triệt tiêu giới hạn CPU/DB/network.
- Fan-out và chuỗi event có thể khuếch đại số lời gọi, memory, I/O và retry.
- Event in-process không tự cung cấp durable queue, replay, backpressure hay consumer group đa node.
- Phải đo successful throughput, end-to-end lag, p95/p99, queue depth và lỗi.
- Direct call phù hợp với bước bắt buộc; batching/coalescing giúp giảm công việc hợp lệ; transactional outbox, durable job hoặc broker phù hợp khi phải xử lý sau crash và scale consumer độc lập.
- Dù dùng cơ chế nào, cần rõ transaction, ordering, idempotency, timeout và failure policy.

Một thiết kế bền vững ở tải cao đặt **đúng công việc vào đúng cơ chế**, có giới hạn tài nguyên và kết quả quan sát được, thay vì chỉ tăng số event hay thread.

## Tài liệu tham khảo

- Spring Framework Reference — *Application Events and Asynchronous Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework 6.2.8 Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2.8 Javadoc — *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2.8 Javadoc — *ThreadPoolTaskExecutor*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference — *Task Execution and Scheduling*: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
