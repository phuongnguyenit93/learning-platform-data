# Event listener và Observability trong Spring Framework

**Observability** là khả năng hiểu trạng thái vận hành của một ứng dụng từ những tín hiệu được tạo ra khi nó chạy: **logs, metrics và traces**. Với Spring Framework Application Events, observability giúp trả lời những câu hỏi như:

- Event nào đã được **publish**, event nào thực sự được listener **xử lý**?
- Listener nào chậm, lỗi nhiều, bị timeout hoặc ngừng nhận event?
- Khi một request dẫn đến nhiều listener, có thể truy từ request đến những công việc phát sinh hay không?
- Listener xử lý **đồng bộ** hay **bất đồng bộ**, trên thread nào, với trace context nào?
- Event được xử lý **trước hay sau commit**, và kết quả transaction có thực sự thành công không?

Một điều quan trọng trong **Spring Framework 6.2**: **Spring không tự tạo Micrometer Observation cho từng lần gọi `@EventListener`**. Theo tài liệu chính thức, Spring không gắn sẵn observation cho các lời gọi này do semantics của Spring application events: mặc định chúng chạy đồng bộ trên cùng thread với publisher, và đã nằm trong ngữ cảnh gọi hiện tại. Nếu muốn đo **từng listener**, hãy chủ động instrument công việc ở listener (hoặc một lớp wrapper có hợp đồng rõ ràng); nếu dùng async thì quản lý truyền context và quan sát kết quả bất đồng bộ.

Bài này tập trung vào **ApplicationEventPublisher**, **`@EventListener`**, **`@TransactionalEventListener`**, **Micrometer Observation** và **context propagation**, không đánh đồng chúng với cơ chế đo lường của Kafka/JMS hoặc hàng đợi bền vững.

## 1. Cần quan sát những giai đoạn nào?

Xét một dịch vụ phát `OrderPlaced` và hai listener:

```text
HTTP request / command
         |
         v
OrderService.placeOrder()
         |
         +-- ghi dữ liệu trong transaction T1
         |
         +-- ApplicationEventPublisher.publishEvent(OrderPlaced)
                 |
                 +-- AuditListener         (thường chạy đồng bộ)
                 |
                 +-- EmailListener         (có thể chạy @Async / sau commit)
         |
         +-- COMMIT hoặc ROLLBACK transaction T1
```

Ở hệ thống event-driven, cần phân biệt **bốn thời điểm** thường bị gộp nhầm:

| Khái niệm | Ý nghĩa | Không được suy ra |
| --- | --- | --- |
| **Published** | Code đã gọi publish; multicaster được yêu cầu phân phối event | Tất cả listener đã hoàn tất |
| **Listener started** | Một listener đã bắt đầu xử lý event | Listener sẽ thành công |
| **Listener completed** | Một listener đã hoàn tất, có thể thành công hoặc lỗi | Transaction nghiệp vụ đã commit |
| **Transaction committed** | Transaction manager đã commit thay đổi nguồn | Webhook, email hoặc listener async đã xử lý xong |

Nếu có broker/outbox, còn một trạng thái thứ năm: **message delivered/acknowledged**. Spring application event chỉ là cơ chế giao tiếp trong tiến trình; không tự bảo đảm lưu bền vững, retry hoặc delivery exactly-once.

### Những signal nên thiết kế

- **Logs:** event type, event ID/correlation ID, listener, pha transaction, attempt, outcome và exception root cause. Mọi dữ liệu nhạy cảm cần được loại bỏ hoặc làm mờ.
- **Metrics:** số lần bắt đầu/xử lý thành công/xử lý lỗi, thời gian xử lý, độ dài hàng đợi executor (nếu có), số task bị từ chối, retry và độ trễ xử lý outbox.
- **Traces:** span của use case, các thao tác dữ liệu, và span con cho công việc listener đáng quan sát. Trace context giúp thấy quan hệ nhân quả, nhưng chỉ khi context được truyền qua ranh giới phù hợp.

Không cần phát sinh ba signal cho **mọi** event nhỏ. Observability có chi phí CPU, phân bổ bộ nhớ, lưu trữ và cardinality. Hãy instrument các listener quan trọng hoặc có SLA cụ thể.

## 2. Vì sao Spring không tự sinh Observation cho `@EventListener`?

Trong một Spring `ApplicationContext`, `ApplicationEventPublisher.publishEvent(...)` chuyển event tới `ApplicationEventMulticaster`. Với cấu hình mặc định, `SimpleApplicationEventMulticaster` gọi các listener **đồng bộ trên thread publisher**. Vì thế một listener được gọi từ request thường đang ở trong cùng call stack và context của request.

```text
Request span (đã tồn tại do HTTP instrumentation)
  |
  +-- OrderService
        |
        +-- publishEvent(...)
              +-- @EventListener A   [cùng thread]
              +-- @EventListener B   [cùng thread]
```

Điều này **không tự tạo một span mới** cho mỗi listener; nó chỉ có nghĩa listener có thể chạy trong phạm vi observation/trace đang hoạt động ở thread đó. Nếu cần xác định “listener A mất 200 ms, listener B mất 10 ms”, hãy tạo observation cụ thể.

Theo tài liệu **Spring Framework Observability**, Spring không cung cấp Observations cho những lời gọi `@EventListener` như một instrumentation mặc định. Không nên bật Spring Boot Actuator rồi giả định sẽ có tự động metric `application.event.listener` cho toàn bộ listener.

Khi dùng custom multicaster với `TaskExecutor`, hoặc đánh dấu listener bằng `@Async`, công việc có thể chạy trên thread khác; khi đó **ThreadLocal, MDC và observation scope** của publisher thường không tự xuất hiện bên listener. Cần cấu hình context propagation phù hợp.

## 3. Micrometer Observation: khái niệm và vòng đời

Micrometer cung cấp `Observation` và `ObservationRegistry`:

- **`Observation`** biểu diễn một tác vụ được quan sát, ví dụ xử lý một event trong một listener.
- **`ObservationRegistry`** chứa cấu hình và các `ObservationHandler` nhận callback khi observation bắt đầu, gặp lỗi, kết thúc hoặc mở/đóng scope.
- **`ObservationHandler`** có thể biến lifecycle observation thành metrics, spans, logs hoặc công việc đo lường khác, tùy hệ thống đã cấu hình.
- **`Observation.Scope`** thiết lập phạm vi observation ở thread hiện tại, để các bước lồng nhau có thể liên hệ với ngữ cảnh đang hoạt động.

Vòng đời thủ công điển hình:

```java
Observation observation = Observation
        .createNotStarted("application.event.listener", registry)
        .lowCardinalityKeyValue("event.type", "OrderPlaced")
        .lowCardinalityKeyValue("listener", "BillingProjection")
        .start();

try (Observation.Scope scope = observation.openScope()) {
    handleBusinessEvent(event);
} catch (RuntimeException | Error ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
```

Đây là **đoạn minh họa tích hợp**, giả định `registry`, `event` và `handleBusinessEvent` được cung cấp bởi ứng dụng. Quan trọng:

1. Tạo observation với tên ổn định, bổ sung các key trước `start()` khi có thể.
2. **Mở scope** quanh phần công việc thực sự cần đo; đóng scope khi kết thúc.
3. Khi lỗi, gọi `observation.error(ex)` để handler biết kết quả; **rethrow exception gốc** nếu lỗi phải lan ra.
4. Luôn gọi `stop()` trong `finally`, nếu không sẽ thiếu số đo thời gian hoàn tất.
5. Chỉ việc tạo observation/registry **chưa đồng nghĩa metrics/traces được xuất**. Cần `ObservationHandler` phù hợp và backend/exporter được cấu hình.

Có thể dùng tiện ích `observation.observe(Runnable)`/`observe(Supplier)` để tự bao gồm start, scope, error và stop. Cách thủ công hữu ích khi muốn nhìn rõ từng bước lifecycle.

### Low cardinality và high cardinality

Micrometer phân biệt:

| Key | Ví dụ | Gợi ý |
| --- | --- | --- |
| **Low cardinality** | `event.type=OrderPlaced`, `listener=BillingProjection`, `outcome=success/error` | Phù hợp để làm nhãn của metrics nếu tập giá trị có giới hạn |
| **High cardinality** | `event.id=evt-23f...`, `order.id=ORD-19283`, `correlation.id=...` | Chỉ dùng cho trace hoặc log cần correlation; **không** tạo một time series metric cho mỗi ID |
| Không được gắn nhãn | Email, token, địa chỉ khách hàng, payload đầy đủ, thông tin thanh toán | Rủi ro bảo mật/PII và cardinality không kiểm soát |

Đừng dùng tên exception chứa dữ liệu động hoặc câu thông báo lỗi làm metric tag. Với lỗi, có thể gắn **nhóm lỗi hữu hạn** (ví dụ `validation`, `database`, `external`); exception cụ thể và stack trace nên ở logs/traces. Một `event.type` lấy trực tiếp từ chuỗi tùy ý người dùng cũng có thể tạo cardinality vô hạn, vì vậy nên giữ tên loại event trong danh sách kiểm soát.

## 4. Ví dụ Java 17+ chạy được: ghi nhận observation cho từng listener

Ví dụ đơn giản dưới đây minh họa Spring `@EventListener` cùng **Micrometer Observation** mà không cần Spring Boot hoặc hệ thống tracing. Để có output dễ kiểm chứng, chương trình đăng ký một `ObservationHandler` tự đếm số lần observation **kết thúc** và **gặp lỗi**. Handler này **không phải exporter metrics/traces production**; nó chứng minh lifecycle của observation đã được thực thi.

Hai event được publish:

- `PaymentCaptured(41)`: listener thành công.
- `PaymentCaptured(42)`: listener cố tình ném lỗi; observation ghi nhận lỗi và exception vẫn truyền về publisher vì multicaster đồng bộ mặc định.

### 4.1. Cấu trúc

```text
event-observation-demo/
├── pom.xml
└── src/main/java/EventObservationDemo.java
```

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-observation-demo</artifactId>
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
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-observation</artifactId>
            <version>1.14.9</version>
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
                    <mainClass>EventObservationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.3. `src/main/java/EventObservationDemo.java`

```java
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;

public class EventObservationDemo {

    public record PaymentCaptured(long id) {}

    // Handler nhỏ để quan sát lifecycle; không xuất metrics/traces thật.
    public static final class CountingHandler
            implements ObservationHandler<Observation.Context> {

        private final AtomicInteger finished = new AtomicInteger();
        private final AtomicInteger errors = new AtomicInteger();

        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onError(Observation.Context context) {
            errors.incrementAndGet();
        }

        @Override
        public void onStop(Observation.Context context) {
            finished.incrementAndGet();
        }

        public int finishedCount() {
            return finished.get();
        }

        public int errorCount() {
            return errors.get();
        }
    }

    public static final class PaymentListener {
        private final ObservationRegistry registry;

        public PaymentListener(ObservationRegistry registry) {
            this.registry = registry;
        }

        @EventListener
        public void onPaymentCaptured(PaymentCaptured event) {
            Observation observation = Observation
                    .createNotStarted("application.event.listener", registry)
                    .lowCardinalityKeyValue("event.type", "PaymentCaptured")
                    .lowCardinalityKeyValue("listener", "PaymentListener")
                    .highCardinalityKeyValue(
                            "event.id", Long.toString(event.id()))
                    .start();

            try (Observation.Scope scope = observation.openScope()) {
                System.out.println("listener: id=" + event.id());

                if (event.id() == 42L) {
                    throw new IllegalStateException("gateway unavailable");
                }
            } catch (RuntimeException | Error ex) {
                observation.error(ex);
                throw ex;  // Không nuốt lỗi, giữ nguyên nhân gốc.
            } finally {
                observation.stop();
            }
        }
    }

    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();
        CountingHandler counter = new CountingHandler();
        registry.observationConfig().observationHandler(counter);

        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(
                    PaymentListener.class,
                    () -> new PaymentListener(registry));
            context.refresh();

            System.out.println("publisher: id=41");
            context.publishEvent(new PaymentCaptured(41L));

            System.out.println("publisher: id=42");
            try {
                context.publishEvent(new PaymentCaptured(42L));
            } catch (IllegalStateException ex) {
                System.out.println("caller: " + ex.getMessage());
            }

            System.out.println("observation: finished="
                    + counter.finishedCount()
                    + " errors=" + counter.errorCount());
        }
    }
}
```

Chạy bằng Java 17+ và Maven từ thư mục có `pom.xml` (lần đầu cần tải dependencies):

```bash
mvn -q compile exec:java
```

Các dòng do chương trình in ra, theo thứ tự (không tính log của framework/Maven):

```text
publisher: id=41
listener: id=41
publisher: id=42
listener: id=42
caller: gateway unavailable
observation: finished=2 errors=1
```

**Tại sao output đúng như vậy?**

1. `context.registerBean(...)` đăng ký listener bean trước `refresh()`; Spring phát hiện phương thức `@EventListener`.
2. Với `id=41`, observation được start, scope được mở, listener in dòng xử lý, scope đóng và observation stop; handler tăng `finished`.
3. Với `id=42`, listener in dòng rồi ném `IllegalStateException`. Khối catch gọi `observation.error(ex)`, handler tăng `errors`, sau đó ném lại **cùng exception**. Khối finally gọi `stop()`, handler tăng `finished`.
4. Multicaster mặc định đồng bộ nên publisher bắt được exception của listener `id=42`. Kết quả `finished=2` và `errors=1` là số observation đã kết thúc và gặp lỗi, không phải số bản ghi trong cơ sở dữ liệu.
5. Chương trình không tích hợp meter registry, tracing bridge hoặc exporter, vì vậy **không tuyên bố đã tạo Prometheus metrics hay OpenTelemetry spans**. Trong ứng dụng production, registry thường được Spring Boot quản lý và kết nối với handler tương ứng.

Ví dụ không sử dụng `@Async` và không mở transaction. Việc minh họa lỗi đồng bộ ở đây **không phải** test rollback. Nếu cần chứng minh rollback, phải bổ sung một transaction manager và truy vấn database sau khi transaction hoàn tất.

## 5. Spring Boot Actuator: từ Observation đến metrics và traces thật

Trong ứng dụng Spring Boot có `spring-boot-starter-actuator`, hạ tầng Micrometer thường được auto-configure theo dependencies và cấu hình. Có thể inject `ObservationRegistry` vào service/listener để instrument công việc; các observation chỉ trở thành **metrics/traces hữu ích** khi có các `ObservationHandler`, backend và exporters thích hợp.

Một ví dụ triển khai:

```java
@Component
public class InvoiceProjectionListener {

    private final ObservationRegistry registry;
    private final InvoiceProjectionService projectionService;

    public InvoiceProjectionListener(
            ObservationRegistry registry,
            InvoiceProjectionService projectionService) {
        this.registry = registry;
        this.projectionService = projectionService;
    }

    @EventListener
    public void onInvoiceIssued(InvoiceIssued event) {
        Observation.createNotStarted(
                        "application.event.listener", registry)
                .lowCardinalityKeyValue("event.type", "InvoiceIssued")
                .lowCardinalityKeyValue("listener", "InvoiceProjection")
                .highCardinalityKeyValue("event.id", event.eventId())
                .observe(() -> projectionService.update(event));
    }
}
```

Đây là **đoạn tích hợp minh họa**, cần các kiểu `InvoiceIssued`, `InvoiceProjectionService` và import `@Component`, `@EventListener`, `Observation`, `ObservationRegistry`. Phương thức `observe(...)` quản lý start/scope/error/stop tự động trong khối được đo và tiếp tục ném lỗi của listener nếu khối xử lý thất bại.

Tùy ứng dụng và exporter, dữ liệu có thể đi tới:

- **Micrometer MeterRegistry + Prometheus:** quan sát độ trễ, tần suất và lỗi của listener theo các key low-cardinality.
- **Micrometer Tracing / OpenTelemetry:** ghi spans và liên kết đường đi từ request đến công việc listener.
- **Structured logging / MDC:** correlation ID, trace ID, span ID, event ID; tránh in payload chứa dữ liệu nhạy cảm.

Không phải cứ thêm Actuator là tự có những meter `application.event.listener`. **Phải có observation do ứng dụng tạo** hoặc instrumentation cụ thể cung cấp nó. Trước khi dựng dashboard, kiểm tra tên metric thực tế sau khi exporter chuyển đổi dấu chấm/tên theo quy ước backend.

**`@Observed`** có thể giúp instrument phương thức trong những ứng dụng được cấu hình Micrometer annotation instrumentation và AOP phù hợp, nhưng không mặc định bao phủ mọi listener. Trong Spring Boot, tùy phiên bản, bật `management.observations.annotations.enabled=true` và có AspectJ/AOP dependencies có thể cần thiết. Khi phương thức đã có instrumentation khác, chú ý tránh tạo **span/metric trùng**.

## 6. Đồng bộ và bất đồng bộ: vì sao trace context có thể mất?

### 6.1. Listener đồng bộ

Với `SimpleApplicationEventMulticaster` mặc định:

```text
Thread HTTP-1
  +-- Request Observation / Trace scope
        +-- OrderService
              +-- publishEvent(OrderPlaced)
                    +-- Listener A
                    +-- Listener B
```

Listener chạy cùng thread nên thường nhìn thấy ThreadLocal logging/observation context của publisher. Nếu instrument một observation trong listener và mở scope, observation đó có thể được tổ chức như một tác vụ con trong trace, **với điều kiện tracing handler đã được cấu hình**.

Tuy nhiên, *cùng thread* không có nghĩa sẽ tự tạo span mới. Nếu listener xử lý lâu và không instrument riêng, trace có thể chỉ thể hiện thời gian ở span ngoài. Muốn phân biệt độ trễ của từng listener, cần tự đo.

### 6.2. Listener dùng `@Async`

Ví dụ:

```java
@Async("eventExecutor")
@EventListener
public void handle(OrderPlaced event) {
    // Có thể chạy trên thread của executor.
}
```

Đây là **mã minh họa**, giả định `eventExecutor` đã được cấu hình, `@EnableAsync` được bật và `OrderPlaced` tồn tại.

`@Async` thường chuyển việc thực thi sang thread khác. ThreadLocal như current observation, trace scope hoặc MDC **không tự truyền qua mọi executor**. Kết quả thường gặp: logs trong listener có trace ID rỗng hoặc khác request; span tự tạo không còn liên hệ cha–con như mong muốn.

Spring Framework đề xuất dùng **Micrometer Context Propagation** và `ContextPropagatingTaskDecorator` để sao chép/ngữ cảnh hóa context khi task được submit:

```java
@Configuration
@EnableAsync
class AsyncEventConfig {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("event-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

Đây là **đoạn cấu hình tích hợp**, không phải phần chạy trong demo ở mục 4. Cần import `@Configuration`, `@EnableAsync`, `@Bean`, `ThreadPoolTaskExecutor`, `ContextPropagatingTaskDecorator` và dependency `io.micrometer:context-propagation`. Ở Spring Boot, kiểm tra sự có mặt của Micrometer Observation/Tracing và các `ThreadLocalAccessor` tương ứng; task decorator không thể tự tạo trace nếu ứng dụng chưa có hệ thống tracing.

Một số lưu ý:

- Bọc task tại **thời điểm submit** mới giúp chuyển context từ thread publisher sang worker. Nếu event được đưa qua một broker/process khác, phải truyền context qua message headers/carrier; task decorator trong JVM không giải quyết xuyên process.
- Scope mới ở thread worker phải được đóng/khôi phục đúng để không làm **rò rỉ trace context** sang request khác trong thread pool.
- Với một số executor và cơ chế task scheduling, decorator có overhead; chỉ bật cho các tác vụ cần correlation và kiểm tra chi phí thực tế.
- Dùng `@Async` **không bảo đảm listener thành công trước khi publisher trả về**. Exception trên worker không tự rollback transaction trên thread publisher.

### 6.3. Custom multicaster có TaskExecutor

Có thể cấu hình `SimpleApplicationEventMulticaster` với executor riêng:

```java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster eventMulticaster(
        @Qualifier("eventExecutor") TaskExecutor executor) {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(executor);
    return multicaster;
}
```

Đây là **đoạn tích hợp minh họa**, cần import phù hợp và bean `eventExecutor` ở trên; tên `applicationEventMulticaster` được Spring dùng để tìm multicaster cấu hình tùy chỉnh. Không kết luận mọi listener sẽ chạy trên executor: những listener không hỗ trợ async execution theo hợp đồng (đáng chú ý loại transaction-bound) có thể vẫn chạy trên thread publisher.

Cấu hình multicaster toàn cục có thể làm thay đổi propagation exception và thứ tự hoàn tất. Hãy đánh giá riêng các listener đồng bộ bắt buộc, listener best-effort và listener cần transaction, thay vì chuyển tất cả sang async chỉ để giảm response latency.

### 6.4. Reactive context không giống ThreadLocal

Trong hệ thống WebFlux/Reactor, context của reactive pipeline gắn với **subscription**, không tự đồng nhất với ThreadLocal trên một thread cụ thể. Với Spring Boot, việc tự động khôi phục ThreadLocal trong reactive operators tùy phiên bản và cấu hình, chẳng hạn `spring.reactor.context-propagation=auto` ở các phiên bản hỗ trợ.

Đừng giả định `publishOn(...)` hoặc `subscribeOn(...)` luôn làm mất Reactor Context: Reactor Context có thể đi cùng subscription qua các operator thích hợp. Nhưng nếu rời chain, tạo subscription riêng không có kế thừa context hoặc gọi API chỉ biết ThreadLocal, correlation có thể mất.

Đối với **reactive transaction events**, việc liên kết event với transaction còn cần đúng `TransactionalEventPublisher`/`TransactionContext` theo hợp đồng Spring; context propagation cho logging/tracing **không thay thế** transaction propagation.

## 7. Observability và transaction lifecycle

Một event có thể được publish trong transaction chưa commit:

```text
T1 bắt đầu
  |
  +-- INSERT order
  |
  +-- publishEvent(OrderPlaced)
  |     +-- @EventListener chạy ngay (mặc định đồng bộ)
  |
  +-- commit T1 thành công / rollback T1
  |
  +-- @TransactionalEventListener(AFTER_COMMIT) chỉ chạy nếu commit
```

Vì vậy cần đặt tên signal chính xác:

- `event.published`: code đã publish; **không đồng nghĩa transaction committed**.
- `listener.executed`: listener đã chạy; **không đồng nghĩa mọi side effect thành công**.
- `transaction.committed`: transaction đã commit; cần dựa vào transaction manager/database, không chỉ callback synchronous.
- `notification.sent`: dịch vụ ngoài đã xác nhận gửi; trạng thái hoàn toàn khác kết quả commit.

Listener theo transaction:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlaced event) {
    Observation.createNotStarted(
                    "application.event.after_commit", registry)
            .lowCardinalityKeyValue("event.type", "OrderPlaced")
            .lowCardinalityKeyValue("listener", "Notification")
            .observe(() -> notificationService.send(event));
}
```

Đây là **mã minh họa tích hợp**, không độc lập. `registry`, `notificationService` và `OrderPlaced` là dependency của ứng dụng. `@TransactionalEventListener` mặc định `fallbackExecution = false`: nếu event phát **ngoài transaction** phù hợp, listener bị bỏ qua, nên cũng sẽ **không tạo observation** ở phương thức này.

Nếu listener `AFTER_COMMIT` gặp lỗi, transaction nguồn **đã commit** và không thể rollback bằng exception của listener. Một trace có span lỗi không đủ để khẳng định đơn hàng đã rollback; phải đối chiếu outcome của transaction gốc. Nếu xử lý sau commit cần ghi database, hãy tạo transaction **mới** rõ ràng (ví dụ service `REQUIRES_NEW` trong imperative flow), thay vì dựa vào resource transaction có thể vẫn còn hiện diện lúc callback.

Với `@Async` kết hợp listener sau commit, việc bắt đầu tác vụ async và xử lý thực sự có thể cách nhau về thời gian. Cần đo các mốc **scheduled**, **started**, **completed**, thay vì dùng thời điểm publish làm độ trễ xử lý chắc chắn. Một số event/bean lifecycle sớm còn đòi hỏi đăng ký listener trước lúc context refresh; không thể đo một listener chưa được đăng ký.

## 8. Đặt tên Observation và chọn metric có ý nghĩa

Một quy ước dễ bảo trì:

| Observation/metric ý tưởng | Ý nghĩa | Nhãn low-cardinality gợi ý |
| --- | --- | --- |
| `application.event.listener` | Thời gian thực thi một lần xử lý ở listener | `event.type`, `listener`, `outcome` hoặc `error.group` |
| `application.event.publish` | Thời gian lời gọi publisher | `event.type`, `publisher` |
| `application.event.retry` | Mỗi lần thử xử lý lại | `event.type`, `consumer`, `result` |
| `application.event.backlog` | Độ dài queue/buffer hoặc outbox pending | `queue.name` hay `event.group` có tập tên hữu hạn |

Đây là **tên do ứng dụng đề xuất**, không phải các observation mà Spring Framework tự tạo mặc định.

Đặc biệt:

1. **Thời gian publish không luôn là thời gian xử lý.** Với multicaster đồng bộ, chúng có thể chồng lấn; với async, publish có thể chỉ là thời gian đưa task vào executor.
2. **Không cộng bừa durations của các listener song song để lấy latency request.** Phải dùng trace hoặc critical path; tổng durations là công sức xử lý, không phải wall-clock elapsed.
3. **Không chỉ đo trung bình.** Với SLO, xem histogram/percentiles khi backend hỗ trợ: p95, p99 và số event lỗi theo loại, kết hợp throughput.
4. **Không phân nhóm metrics theo `eventId` hoặc `orderId`**. Điều đó tạo số lượng time series tăng theo từng message.
5. **Không để instrumentation ném exception che lỗi nghiệp vụ.** Reporter custom cần có cơ chế fail-safe, giới hạn timeout và khả năng xử lý lỗi phù hợp; nếu yêu cầu rollback vì lỗi nghiệp vụ, giữ exception gốc.
6. **Đo drop/rejection và queue latency** khi có executor. Một task được submit chưa đồng nghĩa listener đã bắt đầu, và queue backlog tăng có thể là tín hiệu sớm của sự cố.

Thực tế nên chọn một số ít metric hỗ trợ quyết định vận hành: listener latency, error rate, backlog, retry exhaustion và độ trễ từ commit đến phản ứng hoàn tất.

## 9. Logging và correlation ID

Logs nên trả lời được “event này đi qua đâu” mà không phải mở payload nhạy cảm.

Ví dụ log có cấu trúc (các giá trị chỉ minh họa, không phải output của demo):

```text
level=INFO event.type=OrderPlaced event.id=evt-2f1
listener=InvoiceProjection phase=AFTER_COMMIT
outcome=SUCCESS elapsed.ms=18 trace.id=abc123

level=ERROR event.type=OrderPlaced event.id=evt-2f2
listener=Notification phase=AFTER_COMMIT
outcome=FAILED attempt=3 error.type=ExternalTimeout
trace.id=abc124
```

Gợi ý:

- Đưa `eventId`/`correlationId` vào **event envelope** hoặc payload khi event có thể được lưu/replay, để việc truy vết không phụ thuộc hoàn toàn vào ThreadLocal.
- Với Spring Boot + Micrometer Tracing, trace/span IDs có thể được thêm vào log qua tích hợp logging được cấu hình, nhưng **không phải ứng dụng nào cũng bật tracing**.
- Khi cần MDC trong async, dùng context propagation như ở mục 6 hoặc chuyển identifier vào thông điệp; không dựa vào `InheritableThreadLocal` để truyền qua thread pool.
- Ghi exception root cause ở nơi chịu trách nhiệm xử lý lỗi; tránh cùng một stack trace bị ghi lặp nhiều tầng.
- Không log token, password, email khách hàng hoặc toàn bộ event payload mặc định.

**Một trace ID không thay thế event ID.** Trace có thể chỉ bao phủ một request/process; event có thể được retry ở trace khác. Event ID ổn định giúp nối các attempts, xử lý duplicate và điều tra luồng end-to-end.

## 10. Xử lý lỗi và retry có quan sát được

Với `@EventListener` đồng bộ, exception từ listener **mặc định có thể lan về publisher** và ảnh hưởng transaction đang mở. Nếu custom `SimpleApplicationEventMulticaster` có `ErrorHandler` hoặc executor, behavior có thể thay đổi. Đừng chỉ nhìn logs rồi kết luận publisher đã nhận lỗi.

Với `@Async`, exception của listener không tự ném về publisher. Với `void` async, cần cấu hình cơ chế xử lý uncaught exception phù hợp; với `Future`/`CompletableFuture`, người quản lý kết quả phải quan sát completion/error theo hợp đồng của API. Instrumentation phải bao **thân thực thi trên worker**, không chỉ việc submit từ publisher.

Khi retry:

```text
eventId = evt-101
  |
  +-- attempt=1 -> FAILED timeout
  |
  +-- attempt=2 -> FAILED timeout
  |
  +-- attempt=3 -> SUCCESS
```

Nên đo **số attempts**, lỗi từng lần và **kết quả cuối cùng** riêng; không ghi ba lần failure như ba logical events độc lập. Sử dụng stable event ID để liên kết. Nếu việc xử lý có side effect không idempotent, consumer phải có chiến lược idempotency/inbox trước khi retry.

Nếu cần bảo đảm event không mất khi process chết, cân nhắc **Transactional Outbox**: ghi outbox cùng transaction nguồn, worker lấy event rồi retry có trạng thái. ApplicationEventPublisher tự nó không bảo đảm persistence hoặc replay; thêm Micrometer Observation cũng **không** biến nó thành message broker.

Khi hệ thống ngừng hoạt động đột ngột, có thể không có observation **stop**, không có span cuối hoặc log cuối cùng. Đây là lý do metrics/traces không phải kho dữ liệu nghiệp vụ bền vững.

## 11. Các lỗi thường gặp

**Lỗi 1 — “Đã bật Actuator nên mọi `@EventListener` tự có span”.**  
Không đúng theo Spring Framework 6.2. Phải có instrumentation tương ứng: observation được tạo thủ công ở listener hoặc một cơ chế được cấu hình riêng. Chỉ khi có handlers/exporters mới có dữ liệu metrics/tracing thật.

**Lỗi 2 — Đo `publishEvent` rồi gọi số đo là latency xử lý mọi listener.**  
Sai khi dùng `@Async` hoặc multicaster có executor. Hãy đo publish, queue wait, listener processing và hoàn tất riêng khi kiến trúc yêu cầu.

**Lỗi 3 — Đưa `eventId` vào metric tag.**  
Cardinality tăng theo số event; tạo áp lực lên hệ thống metrics. Hãy dùng high-cardinality trong traces/logs, còn metrics dùng tập nhãn hữu hạn.

**Lỗi 4 — Dùng thread pool nhưng không truyền trace context.**  
Logs ở worker thiếu correlation. Cấu hình `ContextPropagatingTaskDecorator` và Micrometer Context Propagation phù hợp hoặc truyền correlation ID qua event.

**Lỗi 5 — Nhầm lỗi listener sau commit với rollback.**  
Transaction đã commit không thể rollback vì callback `AFTER_COMMIT` lỗi. Phải ghi nhận trạng thái side effect riêng, retry hoặc compensation phù hợp.

**Lỗi 6 — Không gọi `stop()` khi exception.**  
Observation có thể không có thời gian kết thúc, gây dữ liệu sai hoặc thiếu. Dùng `observe(...)` hoặc `try/finally` bao mọi đường đi.

**Lỗi 7 — Bắt exception chỉ để tăng counter rồi nuốt lỗi.**  
Nếu listener là bước bắt buộc trong transaction, hành vi nghiệp vụ bị thay đổi. Hãy gọi `observation.error(ex)` và propagate lỗi phù hợp.

**Lỗi 8 — Tạo metrics/traces trùng nhau.**  
Một span thủ công, `@Observed` và instrumentation tự động ở tầng khác cùng đo một thao tác mà không rõ ranh giới có thể làm báo cáo sai và tốn chi phí. Quy định ai sở hữu observation nào.

**Lỗi 9 — Tuyên bố event đã xử lý vì publisher không thấy exception.**  
Với async, listener có thể đang queue, đang chạy hoặc thất bại sau đó. Phải quan sát completion/acknowledgement thật.

**Lỗi 10 — Coi log/trace là nguồn sự thật transaction.**  
Metrics/traces có thể bị sampling, drop hoặc ngắt giữa chừng. Đối chiếu database transaction outcome, outbox/inbox trạng thái và dữ liệu nghiệp vụ khi điều tra.

## 12. Cách kiểm thử observability cho listener

Nên kiểm thử theo cả **behavior** và **telemetry**, không chỉ kiểm tra rằng một method logging được gọi:

| Tình huống | Kiểm tra nghiệp vụ | Kiểm tra observability |
| --- | --- | --- |
| Listener đồng bộ thành công | Xử lý đúng một lần theo hợp đồng | Observation start/stop, không có error |
| Listener đồng bộ ném lỗi | Exception lan đúng đường, transaction rollback nếu chính sách yêu cầu | Observation đánh dấu error và vẫn stop |
| Listener chạy `@Async` | Publisher không chờ kết quả nếu hợp đồng async; completion được theo dõi riêng | Correlation ID/trace được truyền đúng, latency đo trên worker |
| Listener `AFTER_COMMIT` | Chỉ xử lý sau commit; không chạy khi rollback | Observation phản ánh đúng phase, không đồng nhất error với transaction rollback |
| Event không được listener nhận | Không có side effect, tìm lý do type/registration/transaction | Không báo listener success vì chỉ thấy publisher event |
| Reporter/telemetry tạm ngưng | Quy tắc nghiệp vụ vẫn được giữ | Tác vụ đo lường không vô tình nuốt hoặc thay lỗi gốc |
| Retry nhiều lần | Consumer idempotent, không thực hiện duplicate side effect | Attempt và final outcome phân biệt rõ |

Với Micrometer, có thể sử dụng `TestObservationRegistry` trong test khi thêm dependency `micrometer-observation-test`, hoặc cấu hình một `ObservationHandler` thu thập như ví dụ mục 4. Nếu muốn test metrics thật, dùng `SimpleMeterRegistry` và `DefaultMeterObservationHandler`; nếu muốn test traces, cấu hình tracer/test exporter tương ứng.

Với bất đồng bộ, không dùng `Thread.sleep(...)` để đoán công việc đã hoàn tất. Dùng latch, `CompletableFuture`, test executor hoặc công cụ test thích hợp. Với transaction, query database ở connection/transaction riêng sau khi luồng kết thúc để tránh hiểu nhầm dữ liệu chưa commit.

Một checklist QA trước khi triển khai production:

1. **Signal ownership:** observer nằm ở producer, listener, executor hay worker outbox? Có bị đo trùng không?
2. **Lifecycle:** start/stop/error đủ các đường đi (success, throw, cancellation, retry)?
3. **Cardinality:** chỉ dùng low-cardinality tags cho metrics, high-cardinality IDs cho trace/log?
4. **Correlation:** async/thread pool/reactive/broker có chuyển đúng context và eventId không?
5. **Outcome:** phân biệt published, started, completed, committed, delivered?
6. **Security:** logs/traces không chứa secrets, PII hoặc payload nguyên trạng?
7. **Reliability:** telemetry outage không làm lỗi nghiệp vụ bị che, và event quan trọng có retry/outbox thích hợp?
8. **Dashboards/alerts:** có ngưỡng thực tế cho error rate, p95 latency, queue lag và backlog?

## 13. Tự kiểm tra

**1. Spring Framework 6.2 có tự tạo Observation riêng cho mọi `@EventListener` không?**  
Không. Cần instrumentation tự tạo hoặc cơ chế cụ thể do ứng dụng bổ sung. Listener đồng bộ thường thừa hưởng ngữ cảnh của publisher, nhưng không tự có span con.

**2. Vì sao một listener `@Async` có thể thiếu trace ID dù publisher có trace?**  
Vì current observation/MDC thường lưu trong ThreadLocal; khi công việc chuyển sang thread executor cần context propagation hoặc correlation qua event.

**3. Tại sao không nên đặt `eventId` vào low-cardinality key?**  
Mỗi event có thể có ID khác nhau, làm nổ số lượng time series metrics. ID phù hợp hơn với high-cardinality trace key hoặc log field.

**4. Vì sao observation được tạo rồi vẫn không có Prometheus metrics?**  
Vì `ObservationRegistry` cần handler tạo meter, registry/exporter thích hợp; demo chỉ dùng CountingHandler chứ chưa tạo metrics thật.

**5. Listener `AFTER_COMMIT` xử lý lỗi thì transaction nguồn có rollback không?**  
Không; commit đã xảy ra. Cần quan sát riêng trạng thái công việc phụ và cơ chế retry/outbox nếu quan trọng.

**6. Có thể dùng `publishEvent` latency làm tổng thời gian của listener async không?**  
Không. Publisher có thể chỉ submit task. Đo queue wait, execution duration và completion riêng.

**7. Với lỗi listener, dùng `observation.error(ex)` đã đủ chưa?**  
Chưa. Phải giữ exception propagation theo hợp đồng nghiệp vụ (nếu cần rollback) và luôn `stop()`. Ghi observation không thay thế xử lý lỗi.

## 14. Tài liệu chính thức

- [Spring Framework 6.2 — Observability Support, mục Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html)
- [Spring Framework 6.2 — Application Events và multicaster](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Boot 3.4 — Observability, custom observations và context propagation](https://docs.spring.io/spring-boot/3.4/reference/actuator/observability.html)
- [Micrometer — Observation Components và ObservationHandler](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Observation Instrumentation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html)

