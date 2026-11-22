# Chi phí phát event trong request với Spring Framework Application Events

Khi một HTTP request hoặc một lời gọi nghiệp vụ sử dụng `ApplicationEventPublisher.publishEvent(...)`, việc “phát event” **không mặc nhiên là thao tác nền, không mất thời gian hoặc không ảnh hưởng đến response**. Trong Spring Framework, `SimpleApplicationEventMulticaster` mặc định gọi listener **đồng bộ trên chính thread của publisher**. Vì thế, nếu một `@EventListener` gọi HTTP chậm, truy vấn database nặng hoặc đợi I/O, thời gian đó thường **nằm trong thời gian request phải chờ**. Nếu một listener đồng bộ ném lỗi, lỗi mặc định có thể truyền về publisher và ảnh hưởng luồng giao dịch.

Bài này phân tích **chi phí phát event trong request** thuộc nhóm *Hiệu năng*: chi phí dispatch thực sự, độ trễ do listener, tác động tới throughput/thread pool/transaction, ranh giới giữa đồng bộ và bất đồng bộ, cách đo đúng và các chiến lược tối ưu mà không hy sinh tính nhất quán hoặc độ tin cậy.

## 1. “Publish event” thực sự làm những gì?

Ví dụ service:

```java
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    Order order = orderRepository.save(toOrder(command));
    applicationEventPublisher.publishEvent(
            new OrderPlaced(order.getId(), command.requestId()));
}
```

Đây là **đoạn minh họa tích hợp**, không độc lập: các kiểu `Order`, `PlaceOrderCommand` và repository là của ứng dụng. Vì annotation `@Transactional` bao quanh toàn bộ service, listener đồng bộ chạy trong **call stack** và thường cả **transaction/thread context** của service khi event được publish.

Một đường đi phổ biến:

```text
HTTP thread T
  |
  +-- Controller
        |
        +-- @Transactional OrderService.placeOrder(...)
              |
              +-- save(order)
              |
              +-- publishEvent(OrderPlaced)
              |     |
              |     +-- Spring chọn các listener khớp event
              |     |
              |     +-- AuditListener       4 ms
              |     +-- ProjectionListener 18 ms
              |     +-- EmailListener     300 ms
              |     |
              |     +-- publishEvent(...) trả về
              |
              +-- commit transaction
        |
        +-- trả HTTP response
```

Những con số `4 ms`, `18 ms`, `300 ms` là **ví dụ giả định**, không phải kết quả benchmark của Spring. Trong cấu hình đồng bộ, request có thể phải chờ tổng thời gian các listener được gọi, cộng các bước xử lý ngoài event. Một listener gọi dịch vụ ngoài chậm hoàn toàn có thể chi phối latency, dù overhead **framework dispatch** thực tế nhỏ.

### Khái niệm cần tách biệt

| Thành phần | Điều gì tiêu tốn thời gian/tài nguyên? | Có nằm trong request mặc định? |
| --- | --- | --- |
| Tạo event object | Allocation, copy dữ liệu vào payload, GC nếu tần suất cao | Có |
| `publishEvent(...)` và multicaster | Phân phối, chọn listener, adapter, kiểm tra kiểu/điều kiện | Có |
| `@EventListener` đồng bộ | CPU, database, HTTP, log, khóa, đợi I/O, xử lý nested event | **Có** |
| `@TransactionalEventListener(AFTER_COMMIT)` | Đăng ký callback; xử lý được chạy khi transaction hoàn tất theo phase | **Có thể vẫn làm chậm request** nếu callback chạy đồng bộ trên luồng commit |
| `@Async @EventListener` | Chi phí submit vào executor, quản lý queue; listener chạy sau trên worker | Thường chỉ chi phí submit, **nhưng có thể bị chặn hoặc lỗi khi executor quá tải** |
| Outbox + background dispatcher | Ghi outbox trong transaction, worker đọc/gửi sau commit | Ghi outbox nằm trong transaction; gửi ra ngoài tách khỏi request |

Không có cơ chế “zero cost”: chuyển work khỏi request thường đổi **latency** lấy yêu cầu quản lý **concurrency, queue, retry, consistency và delivery**.

## 2. Vì sao mặc định là đồng bộ?

`ApplicationEventPublisher` cung cấp API publish; việc phân phối thực tế do `ApplicationEventMulticaster` trong `ApplicationContext` đảm nhiệm. `SimpleApplicationEventMulticaster` mặc định chạy listener trên **thread gọi publish**, tương đương sử dụng `SyncTaskExecutor`.

Ưu điểm:

- Luồng thực thi đơn giản: có thể thấy thứ tự listener trong stack trace.
- Có thể tham gia thread-bound transaction cùng publisher khi tương thích và cùng thread.
- Exception đồng bộ mặc định có thể truyền về publisher, giúp fail-fast.
- Thường có overhead tổ chức công việc nhỏ, không phải tạo task/queue/scheduling cho mỗi listener.
- ThreadLocal logging/tracing context của publisher thường còn hiện diện trên chính thread.

Đổi lại:

- Một listener chậm kéo dài thời gian lời gọi `publishEvent(...)`.
- Một listener gọi network không timeout có thể giữ HTTP worker và transaction quá lâu.
- Khi listener A chờ, listener B phía sau có thể bị trì hoãn.
- Nếu listener đồng bộ ném exception mà không có handler đặc biệt, các listener còn lại có thể không được gọi.
- Nếu listener giữ database transaction mở khi gọi HTTP, nó có thể tăng thời gian giữ connection/lock và giảm throughput toàn hệ thống.

**Một event có nhiều listener không có nghĩa Spring chạy chúng song song.** Với cấu hình mặc định, listener được thực thi trên thread publisher, trừ các listener có cơ chế async riêng được cấu hình.

### Mô hình latency

Đặt:

- `T_before`: thời gian request xử lý trước publish.
- `T_dispatch`: overhead tạo/phân phối event, tìm listener, adapter/filter.
- `T_listener_i`: thời gian của listener đồng bộ thứ `i`, **bao gồm tất cả công việc nó thực hiện**.
- `T_after`: công việc request và các bước transaction/commit còn lại sau publish.

Mô hình gần đúng cho một publish đồng bộ không có xử lý song song:

```text
T_publish ≈ T_dispatch + Σ T_listener_i
T_request ≈ T_before + T_publish + T_after
```

Đây là **mô hình tư duy**, không phải công thức hằng số áp dụng cho mọi request. Một listener có thể publish thêm event lồng nhau, event có thể được lọc do `condition`, transaction synchronization có callback sau commit, và I/O có jitter. Khi có async, tổng thời gian listener chạy ở worker **không còn bằng** thời gian publisher phải chờ; phải đo thời gian submit, queue và thực thi riêng.

Một request có thể có nhiều lần publish. Nếu `N` event được phát, mỗi event có nhiều listener và mỗi listener làm việc tốn kém, tổng chi phí có thể tăng nhanh theo số event/lần request và chi phí xử lý mỗi listener. Với một vòng lặp publish event cho từng dòng đơn hàng, overhead nhỏ cũng có thể bị nhân lên rất lớn.

## 3. Ví dụ Java 17+ chạy được: một listener chậm kéo dài publish

Ví dụ dùng Spring Framework **6.2.9**, không cần Spring Boot, database hoặc web server. Nó tạo hai context độc lập:

1. **Sync context:** hai `@EventListener` được sắp thứ tự; listener đầu tiên ngủ 150 ms để mô phỏng I/O. Code publisher chỉ trở về sau khi cả hai listener xong.
2. **Async context:** một listener có `@Async("eventExecutor")` và ngủ 200 ms. Publisher có thể trở về trước khi listener hoàn tất. Test/demo dùng `CountDownLatch` để xác nhận công việc đã xong, **không dùng thời gian ngủ tùy tiện ở phía caller để đoán completion**.

### 3.1. Cấu trúc

```text
event-request-cost-demo/
├── pom.xml
└── src/main/java/example/EventRequestCostDemo.java
```

### 3.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>event-request-cost-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.EventRequestCostDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 3.3. src/main/java/example/EventRequestCostDemo.java

```java
package example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class EventRequestCostDemo {

    public record OrderPlaced(String orderId) {}

    public static class OrderService {
        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void place(String orderId) {
            publisher.publishEvent(new OrderPlaced(orderId));
        }
    }

    private static void simulateBlockingIo(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Simulated I/O interrupted", ex);
        }
    }

    public static class SlowSyncListener {
        @EventListener
        @Order(10)
        public void onOrderPlaced(OrderPlaced event) {
            simulateBlockingIo(150);
            System.out.println("sync: slow listener completed " + event.orderId());
        }
    }

    public static class FastSyncListener {
        @EventListener
        @Order(20)
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println("sync: fast listener completed " + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SyncConfig {
        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        SlowSyncListener slowSyncListener() {
            return new SlowSyncListener();
        }

        @Bean
        FastSyncListener fastSyncListener() {
            return new FastSyncListener();
        }
    }

    public static class AsyncListener {
        private final CountDownLatch completed;

        public AsyncListener(CountDownLatch completed) {
            this.completed = completed;
        }

        @Async("eventExecutor")
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            try {
                simulateBlockingIo(200);
                System.out.println(
                        "async: listener completed " + event.orderId());
            } finally {
                completed.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AsyncConfig {
        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        CountDownLatch completed() {
            return new CountDownLatch(1);
        }

        @Bean
        AsyncListener asyncListener(CountDownLatch completed) {
            return new AsyncListener(completed);
        }

        @Bean(name = "eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-");
            executor.initialize();
            return executor;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                     new AnnotationConfigApplicationContext(SyncConfig.class)) {
            System.out.println("sync: before publish");
            long start = System.nanoTime();

            context.getBean(OrderService.class).place("PO-1");

            long elapsed = System.nanoTime() - start;
            System.out.println("sync: after publish");
            System.out.println(
                    "sync: includes blocking work="
                            + (elapsed >= TimeUnit.MILLISECONDS.toNanos(100)));
        }

        try (var context =
                     new AnnotationConfigApplicationContext(AsyncConfig.class)) {
            System.out.println("async: before publish");

            context.getBean(OrderService.class).place("PO-2");

            System.out.println("async: publish returned");
            boolean finished = context.getBean(CountDownLatch.class)
                    .await(5, TimeUnit.SECONDS);
            if (!finished) {
                throw new IllegalStateException("Async listener timed out");
            }
            System.out.println("async: completion confirmed");
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`, cần JDK 17+, Maven và khả năng tải dependency ở lần chạy đầu:

```bash
mvn -q compile exec:java
```

Các dòng do chương trình in trong một lần chạy bình thường, với executor và máy không bị ngừng/suy giảm nghiêm trọng:

```text
sync: before publish
sync: slow listener completed PO-1
sync: fast listener completed PO-1
sync: after publish
sync: includes blocking work=true
async: before publish
async: publish returned
async: listener completed PO-2
async: completion confirmed
```

**Giải thích kết quả:**

1. `SlowSyncListener` và `FastSyncListener` là Spring beans. `@Order(10)` và `@Order(20)` quyết định thứ tự gọi của listener trong ví dụ đồng bộ. Listener đầu giả lập đợi 150 ms, nên `publishEvent(...)` bị chặn trước khi in dòng `sync: after publish`.
2. Biểu thức `elapsed >= 100 ms` chỉ dùng như **kiểm tra minh họa về việc có công việc chặn bên trong publish**. Đây không phải benchmark hay cam kết latency cố định của Spring. Thời gian thật phụ thuộc JVM, OS, tải máy và khả năng điều phối thread.
3. Context async bật `@EnableAsync`, cung cấp `ThreadPoolTaskExecutor` có hàng đợi giới hạn và bean `AsyncListener`. Phương thức `@Async("eventExecutor")` chạy trên executor, trong khi `publishEvent(...)` thường chỉ cần sắp lịch xử lý. Vì listener mô phỏng I/O 200 ms nên caller thường in `async: publish returned` trước khi listener hoàn tất.
4. `CountDownLatch.await(...)` làm demo đợi **kết quả hoàn thành thật**. Trong ứng dụng HTTP thông thường không nên `await()` ngay trong controller nếu mục tiêu là giảm latency; demo chỉ đợi để output rõ và đóng context an toàn.
5. Context thứ nhất và context thứ hai **độc lập** nên không có listener chạy trùng từ hai cấu hình. Ví dụ không có database và không có transaction; đừng suy luận từ đây rằng async giữ transaction của publisher.
6. Nếu máy bị pause bất thường, thứ tự giữa log caller và worker có thể thay đổi vì scheduling, và timeout 5 giây là điều kiện kiểm tra demo, không phải SLA production. Không viết test chặt vào thời gian tuyệt đối để chứng minh một contract async.

**Lưu ý:** trong `@Async` với phương thức `void`, exception xử lý trên worker không tự truyền về publisher. Cần error handler, logging/metrics và cơ chế retry phù hợp. Việc event method thực sự chạy sau khi publisher trả về **không bảo đảm** event được lưu bền vững.

## 4. Đo đúng chi phí: tách publish, listener và request

### 4.1. Đừng lấy thời gian xử lý API làm “overhead của Spring events”

Nếu request mất `500 ms` sau khi thêm event, chưa đủ kết luận event dispatcher chậm. Cần phân biệt:

- `T_dispatch`: chọn listener, tạo wrapper/adapter, kiểm tra kiểu và condition.
- `T_handler`: công việc thực trong `@EventListener` — ví dụ SQL, HTTP, serialization, log, CPU.
- `T_queue`: thời gian task nằm trong hàng đợi executor (nếu async).
- `T_commit`: transaction flush, commit, synchronization callback.
- `T_request`: toàn bộ end-to-end từ đầu vào tới response.

Một ví dụ gắn stop-watch ở publisher:

```java
long started = System.nanoTime();
publisher.publishEvent(new OrderPlaced(orderId));
long publishNanos = System.nanoTime() - started;
metrics.recordPublishDuration(publishNanos);
```

Đây là **mã minh họa tích hợp**, phụ thuộc vào bean `publisher`, `metrics` và `orderId` của ứng dụng.

Với multicaster đồng bộ, `publishNanos` bao gồm **độ trễ thực thi các listener** và dispatch, không đo riêng overhead thuần của Spring. Với async, nó có thể chỉ đo thời gian đưa task vào queue, không đo completion. Nếu mục tiêu xác định bottleneck, cần instrument **đoạn xử lý bên trong từng listener** và tổng HTTP request.

### 4.2. Spring không tự tạo Observation cho từng @EventListener

Theo tài liệu Spring Framework, `@EventListener` không có **Micrometer Observation tự động** theo mặc định. Nếu cần metric/trace của một listener, có thể tạo observation thủ công:

```java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    Observation.createNotStarted("application.event.listener", registry)
            .lowCardinalityKeyValue("event.type", "OrderPlaced")
            .lowCardinalityKeyValue("listener", "InvoiceProjection")
            .highCardinalityKeyValue("event.id", event.eventId())
            .observe(() -> projectionService.update(event));
}
```

Đây là **đoạn tích hợp minh họa**, cần các kiểu `OrderPlaced`, `projectionService`, `registry` và import Micrometer. Đoạn này không được copy vào class `OrderPlaced` một field ở mục 3 vì record demo chỉ có `orderId()`; ở đây là event production có `eventId()`.

Khi ứng dụng có `ObservationRegistry`, handler và exporters phù hợp (chẳng hạn Spring Boot Actuator + Micrometer), observation có thể đóng góp metrics/tracing. Chỉ gọi `createNotStarted` không có nghĩa đã xuất Prometheus meter hay OpenTelemetry span.

Không gắn `eventId`/`orderId`/email vào **low-cardinality metric tags**. Các giá trị này thường tạo một time series mới cho mỗi event, gây nổ cardinality; chỉ dùng ở logs/traces/high-cardinality metadata khi phù hợp.

### 4.3. Những chỉ số nên theo dõi

| Signal | Đo điều gì | Tại sao hữu ích |
| --- | --- | --- |
| HTTP request duration, p50/p95/p99 | Latency end-to-end | Kiểm tra event có kéo dài response thực tế không |
| Event publish duration | Thời gian từ lúc gọi publish đến lúc trả về | Thấy tác động trên caller; phải hiểu sync hay async |
| Listener processing duration | Thời gian bắt đầu–kết thúc công việc listener | Tìm listener chậm, phân biệt CPU/I/O |
| Listener failure rate | Số lỗi theo loại event/listener hữu hạn | Phát hiện lỗi bị nuốt trong async |
| Executor active threads / queue depth | Tải và backlog | Biết async có thực sự xử lý kịp không |
| Rejected tasks | Số task submit bị từ chối | Phát hiện mất công việc khi executor đầy |
| Outbox lag / oldest pending age | Trễ từ dữ liệu commit đến lúc xử lý event | Đo độ trễ business eventual consistency |
| Database connection/lock wait | Tắc nghẽn tài nguyên transaction | Thấy hệ quả gián tiếp của listener đồng bộ |

Phân biệt **thời gian publish** với **thời gian xử lý listener**. Nếu dashboard chỉ có metrics cho publisher, một listener async mất 3 giây có thể không hề xuất hiện trong latency publisher.

### 4.4. Benchmark micro khác với load test end-to-end

Muốn đo **overhead thuần của framework** khi handler chỉ làm một thao tác nhỏ, một benchmark có warmup/JIT, đo phân bổ object và kiểm soát GC (ví dụ JMH) có thể hữu ích. Tuy nhiên nó không thay thế test HTTP request thật.

Muốn đo **tác động trong request**, cần load test representative traffic: số listener thực, kết nối database, thread pool, payload sizes, logging/tracing, lỗi/timeout bên ngoài. So sánh p95/p99 request và throughput trước–sau thay đổi; đo cả việc listener có hoàn tất đúng SLA, không chỉ API trả về nhanh hơn.

**Không nên kết luận hiệu năng từ một lần gọi `System.nanoTime()`.** Demo ở mục 3 minh họa blocking semantics, không đưa ra số liệu benchmark cho mọi workload.

## 5. Transaction: chi phí giữ lock và connection có thể lớn hơn latency trực tiếp

Với code:

```java
@Transactional
public void placeOrder(Command command) {
    orderRepository.save(...);
    eventPublisher.publishEvent(new OrderPlaced(...));
}
```

Đây là **mã minh họa**, dấu `...` đại diện phần domain code không được cung cấp.

Nếu `@EventListener` đồng bộ gọi một API chậm trong khi transaction vẫn mở:

- Connection có thể vẫn đang được giữ.
- Lock có thể giữ lâu hơn, tăng `lock wait` cho các transaction khác.
- Transaction timeout có thể xuất hiện trong tải cao.
- Request thread bị chiếm lâu hơn, làm giảm số request có thể phục vụ đồng thời.
- Khi event listener phát thêm event hoặc gọi repository, phạm vi giao dịch có thể trở nên khó dự đoán.

Hệ quả **không chỉ** là request chậm thêm đúng bằng thời gian API bên ngoài: giữ tài nguyên có thể làm **nhiều request khác cùng chậm**, tạo hiệu ứng dây chuyền.

Nếu một hành động là **bất biến nghiệp vụ cần xác nhận trước commit**, không được tự ý đưa nó sang async để giảm thời gian HTTP. Ví dụ kiểm tra tồn kho bắt buộc hoặc bảo đảm hạn mức không nên trở thành một fire-and-forget listener thiếu transaction consistency. Hãy làm việc đó trong use case/transaction rõ ràng hoặc thiết kế saga/compensation hợp lý.

Nếu side effect **chỉ được phép sau commit**, cân nhắc `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` hoặc ghi outbox. Nhưng:

**`AFTER_COMMIT` không tự đồng nghĩa async.** Callback transaction có thể chạy đồng bộ khi quá trình commit kết thúc, trên thread xử lý request; một listener sau commit gọi HTTP chậm vẫn có thể kéo dài thời gian trước khi response được gửi. Phải đo thực tế theo transaction manager và cấu hình listener.

### Các pha transaction

| Phase | Khi xử lý | Tác động/giới hạn |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước commit | Công việc chậm có thể kéo dài transaction và thời gian request |
| `AFTER_COMMIT` | Sau commit thành công | Không thể rollback transaction đã commit; callback đồng bộ vẫn có thể chặn |
| `AFTER_ROLLBACK` | Sau rollback | Phản ứng/cảnh báo lỗi; tránh làm mất nguyên nhân rollback |
| `AFTER_COMPLETION` | Sau khi kết thúc commit hoặc rollback | Cleanup/quan sát trạng thái, không coi mọi completion là success |

`@TransactionalEventListener` mặc định dùng `AFTER_COMMIT` và mặc định `fallbackExecution = false`: nếu publish ngoài transaction phù hợp, listener không chạy. Với transaction reactive, ngữ cảnh nằm trong Reactor Context và event cần gắn transaction context theo cơ chế được hỗ trợ; ThreadLocal assumption của ví dụ imperative không áp dụng nguyên vẹn.

## 6. Chuyển async: latency được dời, không phải biến mất

Hai cách thường gặp:

1. **`@Async` trên một `@EventListener` cụ thể.**
2. **Custom `SimpleApplicationEventMulticaster` với `TaskExecutor`**, ảnh hưởng tới các listener hỗ trợ async execution.

Không nên chuyển mọi listener sang async chỉ vì một listener chậm. Các listener dựa vào transaction trong caller và listener không hỗ trợ async execution có semantics riêng; Spring 6.2 quy định một số listener như transaction-synchronized listener **vẫn chạy trên thread publisher** dù multicaster được cấu hình executor.

### 6.1. @Async trên listener

```java
@Async("notificationExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    notificationGateway.send(event);
}
```

Đây là **mã minh họa tích hợp**. Cần `@EnableAsync`, executor bean `notificationExecutor` và các dependency tương ứng.

Ưu điểm: request thường không phải chờ thao tác gửi notification. Nhưng:

- Exception từ listener không tự trở về caller để rollback.
- Executor có số thread/queue hữu hạn; khi quá tải có thể reject task hoặc gây pressure khác.
- ThreadLocal transaction/MDC/tracing context không được truyền qua một thread khác theo mặc định.
- Nếu process chết sau khi publish nhưng trước khi task thực hiện, event **có thể mất**.
- Nếu listener gọi JPA entity đang lazy-loaded, việc xử lý ngoài transaction/thread gốc có thể gặp lỗi hoặc đọc state không nhất quán.
- Listener async không thể phát event mới bằng **return value của `@EventListener`**; cần gọi publisher tường minh.

Đặc biệt, annotation `@Async` phải được xử lý bởi Spring AOP; gọi method async trực tiếp trên `this` (self-invocation) có thể bỏ qua proxy, khiến phương thức vẫn chạy đồng bộ. Trong ví dụ mục 3, event multicaster gọi một Spring-managed listener qua cơ chế đăng ký listener, không phải một lệnh self-invocation thủ công.

### 6.2. Executor bounded queue và backpressure

Giả sử một endpoint có lượng event đến trung bình `λ` event/giây, một pool có `c` worker, mỗi listener mất trung bình `s` giây. Khả năng xử lý danh nghĩa khi không có overhead và tải phân phối đều gần `c/s` task/giây. Nếu event đến lâu dài nhanh hơn khả năng xử lý, backlog sẽ tăng và không thể giải quyết bằng hàng đợi vô hạn.

```text
Request threads
     |
     +-- publishEvent(...)
              |
              +-- executor.submit(task)
                        |
                        +-- bounded queue (pending work)
                               |
                               +-- worker threads
                                      |
                                      +-- listener I/O / CPU
```

Khi queue đầy, chính sách executor/rejection quyết định điều gì xảy ra. Có thể trả lỗi `TaskRejectedException`/`RejectedExecutionException` hoặc dùng một chính sách khác được cấu hình. Nếu dùng `CallerRunsPolicy`, task có thể chạy trên **request thread**, khiến latency tăng mạnh trở lại dưới tải. Vì vậy “async luôn nhanh” là kết luận sai.

Các quyết định cần có:

- **Core/max pool size** phù hợp workload CPU-bound/I/O-bound và ngân sách tài nguyên.
- **Queue capacity hữu hạn**, có metric backlog/rejections.
- **Timeout** cho external I/O và giới hạn concurrency.
- **Retry/backoff** có giới hạn, tránh retry storm.
- **Shutdown semantics**: còn task trong queue khi ứng dụng dừng thì sao?
- **Phương án mất task**: nếu event quan trọng phải được lưu bền vững, một in-memory executor queue không đủ.

### 6.3. TaskDecorator và context propagation

Chuyển listener sang thread khác có thể làm mất current observation, MDC và trace context. Spring hỗ trợ `ContextPropagatingTaskDecorator` cùng Micrometer Context Propagation để hỗ trợ chuyển ngữ cảnh ở các executor phù hợp.

```java
@Bean("notificationExecutor")
ThreadPoolTaskExecutor notificationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("notify-");
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
    executor.initialize();
    return executor;
}
```

Đây là **cấu hình tích hợp minh họa**, không phải file của demo mục 3; cần import Spring và dependency `io.micrometer:context-propagation` cùng các context accessors phù hợp. Context propagation **không truyền transaction imperative của request qua worker** và không thay thế commit guarantee, retry hoặc durable storage.

## 7. Custom multicaster: chỉ dùng khi hiểu tác động toàn cục

Nếu muốn các listener hỗ trợ async được chạy trên executor ở mức event bus:

```java
@Configuration
public class EventBusConfiguration {

    @Bean(name = "applicationEventMulticaster")
    SimpleApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventExecutor") TaskExecutor eventExecutor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(eventExecutor);
        return multicaster;
    }
}
```

Đây là **cấu hình minh họa**, không phải class chạy độc lập; cần `TaskExecutor`, `@Qualifier`, `@Bean`, `@Configuration` và một executor bean. Không tạo cấu hình này nếu không có lý do rõ ràng.

Tác động cần rà soát:

- Có thể làm thay đổi timing của **nhiều** listener, không chỉ listener notification chậm.
- Exception từ listener chạy trên executor **không nhất thiết propagate** về thread publisher.
- Thread-bound transaction context không tự được mang sang executor.
- Listener khai báo `supportsAsyncExecution() == false` vẫn được chạy trên thread publisher, chẳng hạn transaction-synchronized listener của Spring Framework 6.2.
- Thứ tự hoàn tất không còn đồng nghĩa thứ tự đăng ký hoặc `@Order`.
- Nếu multicaster có custom `ErrorHandler`, hành vi swallow/log/propagate có thể thay đổi; phải test cả đường lỗi.

**Ưu tiên tách listener cụ thể sang async** khi chỉ một công việc độc lập cần offload. Thay đổi multicaster toàn cục là một quyết định kiến trúc có ảnh hưởng lớn đến semantics của toàn ứng dụng.

## 8. Tối ưu hóa có thứ tự, tránh “sửa nhanh” sai nghiệp vụ

Một trình tự thực dụng:

### Bước 1 — Xác định handler thật sự tốn thời gian

Instrument request và từng listener. Tìm p95/p99, tỷ lệ lỗi, SQL/query, cache hit, thời gian network, lock wait, GC. Có thể listener chậm vì N+1 query, connection pool cạn hoặc gọi API ngoài thiếu timeout, chứ không phải vì cơ chế event dispatch.

### Bước 2 — Tách loại công việc theo tính nhất quán

| Loại công việc | Hướng xử lý thường phù hợp |
| --- | --- |
| Kiểm tra invariant trước commit, xác thực business rules | Thực hiện rõ ràng, đồng bộ trong use case/transaction; không fire-and-forget |
| Ghi các thay đổi phụ phải atomic cùng aggregate | Cùng transaction, được thiết kế và đo riêng |
| Cập nhật read model có thể trễ | Async consumer hoặc outbox, retry/idempotency |
| Gửi email/webhook không được mất | Transactional Outbox hoặc durable messaging; gửi sau commit |
| Metrics/log best-effort | Giữ nhẹ, có sampling/batching và fail-safe |
| Fan-out nhiều dịch vụ | Message broker/workflow/saga theo contract, không dùng in-process event bus để giả làm broker |

### Bước 3 — Giảm công việc trong listener đồng bộ

- Bỏ lệnh gọi network chậm không thuộc invariant.
- Thay nhiều truy vấn nhỏ bằng truy vấn hiệu quả hoặc batching nếu nghiệp vụ cho phép.
- Không serialize payload lớn nếu handler chỉ cần một ID.
- Dùng immutable value/event record để tránh graph JPA lớn và lazy-loading bất ngờ.
- Tránh publish trong vòng lặp mỗi item nếu có một event tổng hợp có ý nghĩa nghiệp vụ phù hợp.
- Giảm log payload và metric tags high-cardinality không cần thiết.
- Giảm lock contention bằng cách rút ngắn transaction và tránh I/O không cần thiết bên trong nó.
- Giữ các listener độc lập về contract; không buộc đường request chờ công việc không cần phản hồi.

### Bước 4 — Chọn chiến lược xử lý sau commit có độ tin cậy phù hợp

Nếu chỉ cần trì hoãn side effect cho đến khi commit, `@TransactionalEventListener(AFTER_COMMIT)` có thể đúng về **thời điểm**. Nhưng nó không tự tạo hàng đợi bền vững và không mặc định chạy nền.

Nếu cần **không mất event** khi process crash, thiết kế **Transactional Outbox**:

```text
Transaction T1:
  INSERT order
  INSERT outbox(eventId, aggregateId, type, payload, status=PENDING)
  COMMIT T1
         |
         v
Background dispatcher
  đọc outbox pending
  -> gửi tới broker / consumer
  -> retry có backoff
  -> đánh dấu SENT theo quy trình
         |
         v
Consumer idempotent theo eventId
```

Outbox thêm chi phí ghi DB trong request, nhưng có thể tránh việc request phải chờ network đến hệ thống ngoài. Nó cũng tạo khả năng phục hồi có kiểm soát khi dispatcher hoặc downstream lỗi. Không nên quảng cáo outbox là “free latency” hay “exactly-once end-to-end”; nó đòi hỏi worker, cleanup, backpressure, deduplication và quan sát backlog.

### Bước 5 — Kiểm tra tải sau thay đổi

Không dừng ở việc response p95 tốt hơn. Với async/outbox, xem cả:

- Tỷ lệ event được xử lý thành công cuối cùng.
- Độ trễ từ commit tới listener completion.
- Queue depth, oldest pending age và retry backlog.
- Memory footprint, thread count và CPU/GC.
- Số event bị trùng/mất và tính đúng đắn khi service restart.
- Khả năng dừng an toàn khi deployment rolling hoặc executor bị shutdown.

Nếu response nhanh nhưng queue tăng không giới hạn, hiệu năng tổng thể và SLA nghiệp vụ vẫn đang xấu đi.

## 9. Khi nào không nên sử dụng event để “tối ưu” request?

Có những use case mà một lời gọi service rõ ràng tốt hơn một event:

- Controller cần biết ngay kết quả kiểm tra tồn kho để trả HTTP 409.
- Transaction bắt buộc tính toán hạn mức rồi lưu kết quả một cách atomic.
- Listener A bắt buộc thành công trước listener B và trước commit; event bus không phải orchestration engine lý tưởng cho workflow ràng buộc chặt.
- Tác vụ chỉ có một consumer trực tiếp, không có lợi ích decoupling thực sự, nhưng việc thêm event khiến exception flow khó hiểu.

Không phải event pattern xấu; vấn đề là dùng nó **để giấu một dependency đồng bộ**. Nếu hành vi đã bắt buộc đồng bộ, một method call có kiểu trả về/lỗi tường minh thường dễ đo và kiểm thử hơn.

Nếu có nhiều hành vi độc lập và eventual consistency được chấp nhận, event lại hữu ích, nhưng cần chọn rõ ranh giới thread, transaction, executor hoặc broker.

## 10. Lỗi phổ biến về hiệu năng event

**Lỗi 1 — “`publishEvent(...)` trả ngay vì event là async”.**  
Sai theo cấu hình mặc định. `SimpleApplicationEventMulticaster` gọi listener trong caller thread, nên slow listener chặn request.

**Lỗi 2 — Benchmark `publishEvent` khi không có listener rồi áp dụng cho production.**  
Sai vì production latency thường chi phối bởi handler I/O, DB, payload và contention. Benchmark cần workload representative.

**Lỗi 3 — Chuyển listener bắt buộc sang `@Async` để tăng tốc.**  
Có thể phá transaction semantics: lỗi trên worker không rollback caller transaction. Với invariant, giữ đồng bộ hoặc thiết kế workflow riêng.

**Lỗi 4 — Cho rằng `AFTER_COMMIT` tự là background thread.**  
Nó biểu diễn phase transaction, không phải hợp đồng async. Callback đồng bộ sau commit vẫn có thể tăng request latency.

**Lỗi 5 — Dùng unbounded executor queue.**  
Trong peak, backlog/memory tăng nhanh, độ trễ xử lý event tăng không giới hạn, hệ thống có nguy cơ OOM. Cần queue capacity và overload policy.

**Lỗi 6 — Dùng CallerRunsPolicy mà không đo request latency under overload.**  
Task bị đẩy về caller thread khi queue đầy; latency request có thể đột ngột xấu đi.

**Lỗi 7 — Không gắn timeout vào external calls từ listener.**  
Thread hoặc transaction có thể bị giữ vô thời hạn cho tới khi timeout thấp hơn ở tầng khác. Cần deadline/timeout và retry có giới hạn.

**Lỗi 8 — So sánh tổng durations của listener song song với latency một request.**  
Tổng CPU/wall time các task không bằng critical path. Với async, cần timestamp publish/submit/start/end và trace/queue metrics.

**Lỗi 9 — Dùng @EventListener có condition SpEL phức tạp với tần suất rất cao.**  
Đánh giá điều kiện cũng có chi phí; nếu event volume lớn, cần đo và tránh truy cập dữ liệu lớn hoặc dependency không cần thiết trong điều kiện.

**Lỗi 10 — Truyền cả JPA entity sang listener async.**  
Lazy association và persistence context không an toàn để dùng như một transaction portable. Dùng ID/snapshot bất biến rồi query qua transaction riêng nếu cần.

**Lỗi 11 — Tối ưu mỗi request nhưng không xem tổng throughput.**  
Một async executor bị nghẽn có thể khiến event side effects trễ hàng phút. Response latency chỉ là một phần SLA.

**Lỗi 12 — Coi một lượt demo `Thread.sleep` là số liệu chính thức.**  
Demo chỉ cho thấy việc chặn luồng; thời gian thực tế phải đo từ ứng dụng với tải và dependency thật.

## 11. Kiểm thử tính đúng đắn và hiệu năng

Một bộ test hợp lý có ba lớp:

### Unit test cho quyết định publish và payload

Không cần Spring context nếu chỉ kiểm tra service có tạo event đúng nội dung. Có thể dùng fake publisher để ghi event object, assert loại event và dữ liệu. Không dùng unit test loại này để suy ra tốc độ của multicaster thật.

### Integration test Spring context cho đồng bộ và lỗi

Với `AnnotationConfigApplicationContext` hoặc `@SpringBootTest`:

1. Đăng ký các listener theo cấu hình thật.
2. Publish event và assert side effect/sequence trong trường hợp sync.
3. Nếu listener sync ném `RuntimeException`, assert exception propagation và transaction outcome khi dùng `@Transactional` thực.
4. Nếu dùng `@TransactionalEventListener`, dùng transaction manager thật và phân biệt commit/rollback.
5. Nếu event có nhiều listener, không giả định listener bị chặn sau exception sẽ luôn chạy.

Có thể dùng `@RecordApplicationEvents` của `spring-test` để kiểm tra publication, nhưng nó không chứng minh async listener completed hoặc transaction committed.

### Integration/load test cho async và outage

- Dùng `CountDownLatch`, `CompletableFuture` hoặc test executor thay vì `Thread.sleep` để đợi completion.
- Gây executor saturation để xem task rejection policy, dropped work và request p99.
- Tạo lỗi downstream có kiểm soát để xem retry/backoff/circuit breaker.
- Mô phỏng shutdown giữa publish và xử lý để kiểm tra khả năng mất event.
- Với outbox, kiểm tra crash/restart, duplicate delivery và consumer idempotency.
- Với load test, ghi p50/p95/p99 của request và **event completion latency**; đừng chỉ tối ưu một trong hai.

### Một bảng so sánh cần được hiểu đúng

| Tiêu chí | Listener sync | `@Async` in-memory | Transactional Outbox |
| --- | --- | --- | --- |
| Request chờ handler? | Có (mặc định) | Thường không; vẫn chờ submit/rejection/backpressure | Chờ ghi outbox, không cần chờ downstream |
| Dùng caller transaction? | Có thể, khi cùng thread và phù hợp | Không tự kế thừa | Bản ghi outbox trong cùng transaction |
| Lỗi handler ảnh hưởng publisher? | Mặc định có thể propagate | Thường không propagate từ worker | Handler lỗi trong dispatcher cần retry riêng |
| Bảo toàn event khi process chết? | Không tự bảo đảm | Không, queue trong bộ nhớ | Có thể phục hồi từ outbox đã commit |
| Cần vận hành queue/backlog? | Không có executor queue riêng mặc định | Có | Có worker/outbox backlog |
| Độ phức tạp | Thấp | Trung bình | Cao hơn, phù hợp yêu cầu reliability |

Lựa chọn đúng phụ thuộc **semantics nghiệp vụ**, độ trễ cho phép, tải thực, transaction boundary, nhu cầu retry và yêu cầu vận hành.

## 12. Câu hỏi tự đánh giá

**1. Vì sao `publishEvent(...)` có thể làm HTTP request chậm?**  
Vì multicaster mặc định gọi `@EventListener` đồng bộ trên request thread; request đợi listener hoàn tất.

**2. Nếu request mất 500 ms khi publish event, có thể kết luận Spring dispatch overhead là 500 ms không?**  
Không. Con số có thể gồm HTTP/DB của listener, condition, nested events, log và thời gian chờ. Cần instrument riêng dispatcher/handler.

**3. Chuyển một listener sang `@Async` có làm mất chi phí xử lý không?**  
Không. Chỉ di chuyển sang worker và queue; vẫn có CPU, memory, I/O, retry, điều phối và giới hạn năng lực xử lý.

**4. `@TransactionalEventListener(AFTER_COMMIT)` có tự bảo đảm request không phải đợi không?**  
Không. Phase transaction không phải hợp đồng async; callback vẫn có thể chạy đồng bộ trên luồng commit.

**5. Khi executor đầy, chuyện gì xảy ra?**  
Tùy queue/rejection policy, task có thể bị từ chối hoặc chạy trên caller thread, ảnh hưởng request latency và khả năng mất việc. Cần đo rejections/backpressure.

**6. Vì sao cần đo queue wait bên cạnh listener execution time?**  
Async listener có thể xử lý nhanh nhưng phải đợi rất lâu trong backlog. SLA “event được xử lý trong 5 giây” phải tính cả thời gian xếp hàng.

**7. Khi cần notification không được mất sau commit, chỉ `@Async` đã đủ chưa?**  
Chưa. In-memory queue không bền vững. Cân nhắc outbox/durable messaging và idempotency.

**8. Vì sao không đặt event ID vào metric low-cardinality tag?**  
Vì mỗi event tạo giá trị tag khác nhau, làm số lượng time series tăng không kiểm soát. Event ID phù hợp hơn với logs/traces.

## 13. Tài liệu chính thức

- [Spring Framework 6.2.9 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — Application Events, @EventListener, @Async](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework — Observability Support for @EventListener](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework 6.2.9 Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2.9 Javadoc — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)

