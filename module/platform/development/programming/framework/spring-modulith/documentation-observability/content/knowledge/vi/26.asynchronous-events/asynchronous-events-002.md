# Thời điểm tạo span cho listener

## 1. Vấn đề cần giải quyết

Bài học thuộc chương **Sự kiện bất đồng bộ** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Với Spring Modulith, chúng ta vừa có thể mô tả **ranh giới application module** (module graph, Actuator), vừa quan sát **tương tác thực tế giữa các module** (Micrometer Observation, tracing, event metrics). Khi một module phát sự kiện và một module khác tiếp nhận bất đồng bộ, câu hỏi quan trọng là:

> **Span đo hoạt động của listener cần bắt đầu lúc phát sự kiện, lúc transaction commit, lúc đưa công việc vào executor, hay lúc listener thực sự chạy?**

Câu trả lời cho **span đo thời gian xử lý listener** là: **bắt đầu khi lời gọi listener thực sự được thực thi trên thread xử lý (hoặc ngay ở interceptor bao quanh lời gọi đó), và kết thúc khi phần xử lý được đo hoàn thành hoặc thất bại**. Khoảng thời gian sự kiện chờ commit/chờ executor là một chỉ số khác; không nên cộng nó một cách vô ý vào thời gian thực thi nghiệp vụ của listener.

Đây là nguyên tắc thiết kế phép đo. Với **span tự động do Spring Modulith tạo**, điểm bắt đầu/kết thúc chính xác còn phụ thuộc vào interceptor, proxy và phạm vi instrumentation của phiên bản đang dùng. Với **span tự tạo bằng Micrometer**, bạn chủ động lựa chọn chính xác đoạn mã cần đo.

### Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt span của **publisher**, span của **listener** và thời gian chờ để listener được xử lý.
- Xác định đúng ranh giới span đối với `@EventListener`, `@TransactionalEventListener` và `@ApplicationModuleListener`.
- Dùng Spring Modulith Observability để nhận diện một **module entry span** cho lời gọi sự kiện; giải thích khi nào cần tạo observation riêng.
- Cấu hình **context propagation** qua `@Async`/`TaskExecutor` để các span liên quan có thể nằm trong cùng trace.
- Kiểm tra trace, module graph, metrics và các trường hợp retry/failure mà không nhầm số lần phát sự kiện với số lần xử lý thành công.

## 2. Phân biệt ba đồng hồ thời gian

Xét ứng dụng Spring Boot gồm module `orders` phát sự kiện `OrderPlaced`; module `inventory` lắng nghe để giữ hàng. Khi dùng listener bất đồng bộ, một request có thể hoàn tất trước khi giữ hàng xong.

~~~mermaid
sequenceDiagram
    autonumber
    participant H as HTTP request
    participant O as orders
    participant DB as Transaction / Registry
    participant Q as Async executor
    participant I as inventory listener
    H->>O: placeOrder()
    activate O
    O->>DB: Lưu đơn và publishEvent(OrderPlaced)
    Note over O,DB: t0: tạo sự kiện trong transaction
    DB-->>O: Đăng ký xử lý sau commit
    O->>DB: commit
    Note over DB,Q: t1: commit thành công
    DB->>Q: Schedule listener
    Note over Q: t2: task đã được submit
    deactivate O
    Q->>I: Bắt đầu thực thi trên worker
    activate I
    Note over I: t3: listener span bắt đầu
    I->>I: Giữ hàng, ghi dữ liệu, gọi API
    Note over I: t4: xử lý xong hoặc ném lỗi
    deactivate I
~~~

Có ba khoảng thời gian khác nhau:

| Phép đo | Điểm bắt đầu | Điểm kết thúc | Ý nghĩa |
| --- | --- | --- | --- |
| **Publisher span** | Bắt đầu thao tác nghiệp vụ phát sự kiện | Thao tác phía publisher kết thúc | Thời gian xử lý của module phát sự kiện; có thể bao gồm transaction/commit tùy lớp đo |
| **Event-to-listener lag** | Lúc sự kiện được tạo/ghi nhận, hoặc lúc commit, theo định nghĩa metric | Lúc listener bắt đầu | Độ trễ đưa sự kiện đến lúc xử lý, gồm các thành phần khác nhau tùy mốc ban đầu |
| **Listener execution span** | Ngay trước đoạn xử lý listener cần quan sát (`t3`) | Khi đoạn xử lý đó trả về hoặc lỗi (`t4`) | Thời gian thực thi của listener |

Cần nói rõ mốc gốc của độ trễ. Nếu `occurredAt` được đặt ngay lúc tạo sự kiện trước commit, hiệu `listenerStart - occurredAt` bao gồm **thời gian transaction chưa commit** và **thời gian chờ thực thi**. Nó không phải chỉ riêng thời gian đứng trong queue. Muốn đo đúng thời gian chờ executor, phải ghi thời điểm task được submit (`t2`) hoặc sử dụng instrumentation tại lớp executor.

**Ví dụ số:** sự kiện sinh lúc 10:00:00.000, commit lúc 10:00:00.120, submit lúc 10:00:00.125, listener chạy lúc 10:00:00.500 và kết thúc lúc 10:00:00.570.

- Event-to-listener lag từ lúc tạo sự kiện: **500 ms**.
- Executor waiting từ lúc submit: **375 ms**.
- Listener execution: **70 ms**.

Nếu khởi tạo listener span tại `publishEvent()` rồi dừng khi listener xong, span dài **570 ms** và dễ khiến người xem trace tưởng nghiệp vụ giữ hàng chạy rất chậm, trong khi phần lớn thời gian là chờ. Có thể tạo **một span/observation riêng** cho vòng đời giao nhận hoặc một metric độ trễ giao hàng nếu đó thực sự là điều cần quan sát.

## 3. Thời điểm gọi listener phụ thuộc loại sự kiện

Một annotation khác nhau có thể đổi cả thread thực thi lẫn mốc xử lý trong transaction.

| Cách đăng ký listener | Thời điểm thường thực thi | Thread | Điều nên đo |
| --- | --- | --- | --- |
| `@EventListener` mặc định | Trong lời gọi `publishEvent()` | Cùng thread, đồng bộ | Span có thể nằm trực tiếp dưới publisher nếu tracing còn hiệu lực |
| `@TransactionalEventListener` mặc định | Pha `AFTER_COMMIT`, khi transaction phát sự kiện commit thành công | Thông thường cùng thread nếu không thêm `@Async` | Span bắt đầu khi callback thực sự được gọi, không phải ngay lúc publish |
| `@Async @TransactionalEventListener` | Sau commit rồi được đưa qua executor | Worker thread | Span bắt đầu ở worker; cần truyền trace context |
| `@ApplicationModuleListener` | Shortcut cho `@Async` + `@TransactionalEventListener` + `@Transactional(propagation = REQUIRES_NEW)` | Worker thread, transaction mới | Span bắt đầu tại điểm entry của listener, hoặc trong thân listener nếu đo thủ công |

`@ApplicationModuleListener` là cách được Spring Modulith cung cấp để tích hợp module qua sự kiện, tách đơn vị xử lý của module nhận khỏi transaction ban đầu. Khi commit bị rollback thì callback `AFTER_COMMIT` không chạy. Khi listener chạy trong transaction mới, **transaction context của publisher không được chuyển sang worker**; transaction mới là có chủ đích. **Trace context** lại là ngữ cảnh quan sát có thể truyền qua thread nếu có cấu hình phù hợp.

Cần phân biệt thêm: nếu bạn cấu hình `ApplicationEventMulticaster` dùng executor riêng, hành vi của các listener có thể khác mặc định. `@TransactionalEventListener` còn phụ thuộc transaction synchronization, vì vậy không nên suy rằng mọi loại listener đều được chạy bằng cùng một thread pool hay đều chạy sau commit.

## 4. Spring Modulith tạo span gì?

Spring Modulith có hỗ trợ quan sát tương tác giữa các application module. Khi cấu hình runtime phù hợp, các lời gọi được instrumentation vào **module entry** có thể tạo Micrometer spans, kể cả lời gọi đi qua event listener. Theo tài liệu Spring Modulith, nhóm span module entry có các thuộc tính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `module.identifier` | Mã định danh module |
| `module.name` | Tên module hiển thị |
| `module.invocation-type` | Kiểu gọi: `event listener` hoặc `bean` |
| `module.method` | Phương thức đã được gọi |

Khi tìm trace, hãy lọc theo `module.invocation-type=event listener` và đối chiếu `module.identifier` của module tiếp nhận. Đây là cách xác nhận **đường tương tác runtime** cùng với module graph đã khai báo.

**Không giả định mọi method có `@EventListener` đều tự động có span.** Instrumentation phụ thuộc module được Spring Modulith nhận diện, điểm entry được bao quanh, cấu hình tracing, proxy và sampling. Spring Framework bản thân nó không mặc định tạo Observation cho mọi `@EventListener`. Nếu thiếu span, trước hết kiểm tra phạm vi instrumentation và đường gọi thực tế; chỉ tạo observation thủ công khi cần đo thêm một đoạn mã cụ thể.

Spring Modulith còn công bố các counter như `module.events.published` và metric riêng theo module/event. **Counter phát sự kiện không đo thời gian listener, cũng không chứng minh đã xử lý thành công.** Khi phân tích sự cố, kết hợp event metrics, Event Publication Registry và trace.

## 5. Cấu hình nền tảng quan sát

Các mảnh ghép cần có:

1. Spring Boot Actuator, Micrometer Observation và một tracing bridge/exporter phù hợp để đẩy trace tới hệ thống quan sát.
2. Spring Modulith Insight starter (hoặc các thành phần Actuator/Observability tương đương) để quan sát ranh giới module.
3. Executor chạy `@Async` có **context propagation**.
4. Một listener có khối nghiệp vụ cụ thể cần đo và hệ thống thu thập trace đã cấu hình nhận dữ liệu.

Ví dụ dependency Maven trọng tâm (để BOM Spring Boot và Spring Modulith quản lý các phiên bản tương thích):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Một ví dụ cầu nối Micrometer Tracing sang OpenTelemetry -->
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <!-- Bổ sung exporter OTLP phù hợp với phiên bản Spring Boot đã chọn -->
</dependencies>
~~~

Ví dụ trên mô tả **một hướng tích hợp**. Tên starter, cách thiết lập exporter và thuộc tính cấu hình có thể khác giữa Spring Boot 3.x/4.x và Spring Modulith 1.x/2.x; hãy dùng cùng một dải phiên bản được hỗ trợ bởi BOM dự án. Chỉ thêm `spring-modulith-starter-insight` không có nghĩa trace đã được xuất thành công nếu chưa cấu hình tracing/exporter.

Trong môi trường phát triển, có thể dùng cấu hình quan sát tương tự:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,modulith
  tracing:
    sampling:
      probability: 1.0 # Chỉ nên đặt 100% để kiểm tra trong môi trường thử nghiệm
~~~

Endpoint `/actuator/modulith` thể hiện cấu trúc module và dependencies (ví dụ loại `EVENT_LISTENER`); **Actuator module graph không cung cấp timeline xử lý của từng sự kiện**. Timeline phải đọc từ trace hoặc metric có gắn thời điểm. Giới hạn quyền truy cập endpoint vận hành theo chính sách của môi trường.

### Truyền context qua worker thread

Với `@Async`, trace/observation hiện tại thường nằm trong `ThreadLocal` và không tự xuất hiện trên worker thread. `ContextPropagatingTaskDecorator` có thể sao chép **ngữ cảnh quan sát đã được đăng ký để truyền** từ thời điểm submit task sang lúc thực thi.

Cấu hình rõ ràng một executor dành cho listener:

~~~java
package com.example.modulith.config;

import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class AsyncListenerConfiguration {

    @Bean(name = "taskExecutor")
    Executor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("modulith-event-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Tên `taskExecutor` cho phép hạ tầng `@Async` tìm executor mặc định trong trường hợp không có cấu hình executor khác ưu tiên hơn. Nếu ứng dụng có nhiều executor, hãy kiểm tra executor **thực tế được `@ApplicationModuleListener` sử dụng**; trang trí nhầm executor sẽ không giúp trace của listener. Với các phiên bản Spring Boot có hỗ trợ thuộc tính `spring.task.execution.propagate-context` cho executor tự cấu hình, có thể dùng thuộc tính đó thay cho cấu hình executor thủ công. Đừng bật hai cách một cách mù quáng.

**Context propagation chỉ tái lập những context có accessor tương ứng** (đặc biệt Micrometer Observation/Tracing khi tracing được thiết lập). Nó không mặc nhiên chuyển giao transaction, entity manager, mọi dữ liệu `ThreadLocal` hay security context của request. Đặc biệt, không dùng việc có cùng trace ID như bằng chứng listener có cùng transaction.

## 6. Ví dụ: đo span đúng thời điểm trong listener

Giả sử module `orders` phát sự kiện sau khi ghi đơn vào transaction, và module `inventory` giữ hàng sau commit.

Đặt event trong API công khai của module gửi để module nhận có thể tham chiếu hợp lệ:

~~~java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;

// occurredAt ghi nhận lúc sự kiện được tạo, trước transaction commit.
public record OrderPlaced(UUID orderId, Instant occurredAt) {}
~~~

Publisher bên `orders`:

~~~java
package com.example.shop.orders;

import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final ApplicationEventPublisher publisher;
    private final Clock clock;
    private final OrderRepository orders;

    public OrderService(
            ApplicationEventPublisher publisher, Clock clock,
            OrderRepository orders) {
        this.publisher = publisher;
        this.clock = clock;
        this.orders = orders;
    }

    @Transactional
    public void place(UUID orderId) {
        orders.insertPending(orderId); // Repository ứng dụng cung cấp.
        publisher.publishEvent(new OrderPlaced(orderId, Instant.now(clock)));
    }
}
~~~

Đo một khối xử lý trong listener bằng `ObservationRegistry`. Ví dụ này đo **từ lúc chuẩn bị giữ hàng đến lúc kết thúc giữ hàng**; không đo từ lúc phát event.

~~~java
package com.example.shop.inventory;

import com.example.shop.orders.OrderPlaced;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
public class InventoryOnOrderPlaced {
    private static final Logger log =
            LoggerFactory.getLogger(InventoryOnOrderPlaced.class);

    private final InventoryService inventory;
    private final ObservationRegistry observations;
    private final Clock clock;

    public InventoryOnOrderPlaced(
            InventoryService inventory,
            ObservationRegistry observations,
            Clock clock) {
        this.inventory = inventory;
        this.observations = observations;
        this.clock = clock;
    }

    @ApplicationModuleListener
    public void on(OrderPlaced event) {
        // Đã đi qua commit và được executor đưa tới thread xử lý.
        Instant listenerStartedAt = Instant.now(clock);
        long eventToListenerLagMs =
                Math.max(0L, Duration.between(
                        event.occurredAt(), listenerStartedAt).toMillis());

        // Ghi một metric/histogram riêng cho lag nếu cần;
        // không dùng ID từng đơn làm low-cardinality tag.
        log.debug("OrderPlaced delivery lag (ms): {}", eventToListenerLagMs);

        Observation work = Observation
                .createNotStarted("inventory.order-placed.handle", observations)
                .lowCardinalityKeyValue("listener", "inventory-order-placed")
                .lowCardinalityKeyValue("module", "inventory");

        // Đây là thời điểm span/observation thủ công được bắt đầu.
        work.start();
        try (Observation.Scope scope = work.openScope()) {
            // Hàm nghiệp vụ phải idempotent khi event được gửi lại.
            inventory.reserveOnce(event.orderId());
        } catch (RuntimeException ex) {
            work.error(ex);
            throw ex; // Để registry nhận biết xử lý thất bại.
        } finally {
            // Dừng cả trong đường đi thành công lẫn lỗi.
            work.stop();
        }
    }
}
~~~

`Clock`, `OrderRepository` và `InventoryService` là các bean dịch vụ của ứng dụng, được bỏ qua phần cài đặt để tập trung vào thời gian của span; cấu hình một `Clock.systemUTC()` bean nếu ứng dụng chưa có.

Các điểm cần đọc kỹ:

- **`@ApplicationModuleListener`** đảm bảo listener được gắn với cơ chế bất đồng bộ/transactional của Spring Modulith; hàm `on(...)` đang chạy trong nhánh xử lý sau commit.
- **`Observation.createNotStarted(...)`** chỉ chuẩn bị observation; **`work.start()`** mới ghi nhận thời điểm bắt đầu. **`work.openScope()`** đưa observation này vào context hiện tại của thread để lời gọi con có thể thấy nó.
- **`work.error(ex)`** đánh dấu lỗi rồi **ném tiếp** exception. Nếu nuốt lỗi, registry có thể tưởng listener thành công và không thực hiện cơ chế retry tương ứng.
- **`work.stop()`** trong `finally` đánh dấu kết thúc cả khi có exception. Nếu quên stop, duration/trace có thể thiếu hoặc sai.
- Nếu Spring Modulith **đã tạo module entry span** cho listener, observation thủ công ở trên có thể trở thành **span con** để đo riêng `reserveOnce(...)`. Hãy tránh gắn `@Observed` hoặc tạo thêm span giống hệt vòng bao ngoài, nếu không trace sẽ thừa các span cùng ý nghĩa.
- Vì annotation `@Transactional(REQUIRES_NEW)` thường được áp dụng qua interceptor bao ngoài method body, span bắt đầu **bên trong** `on(...)` không nhất thiết đo được cả thời gian mở/commit transaction. Muốn đo trọn vòng gọi listener, dùng span module entry hoặc instrumentation bao ngoài lời gọi.

Nếu chỉ muốn quan sát thời gian chạy toàn bộ listener và Spring Modulith đã tạo span module entry, bạn **không cần** khởi tạo observation thủ công; nên ưu tiên xem span sẵn có. Chỉ thêm span tùy biến khi có một đoạn nghiệp vụ quan trọng hoặc metric riêng cần tách.

## 7. Quan hệ parent-child và trace context bất đồng bộ

Span có hai khía cạnh độc lập: **thời gian** (start/end) và **quan hệ nhân quả** (trace/span ID).

### Khi context được truyền đúng

~~~mermaid
flowchart TB
    A["HTTP request span<br/>orders / placeOrder"] --> B["Commit transaction<br/>và schedule event"]
    B -. "Truyền trace context lúc submit" .-> C["Worker thread"]
    C --> D["Module entry span<br/>inventory listener"]
    D --> E["Custom work span<br/>reserveOnce"]
~~~

Nếu executor truyền context từ điểm submit sang worker và tracing vẫn còn parent hợp lệ để tham chiếu, span của listener có thể chia sẻ `traceId` với publisher và có quan hệ parent-child thể hiện đúng nhân quả. Parent span **có thể đã kết thúc** vào lúc listener chạy; điều đó không khiến span con trở thành không hợp lệ.

Nếu executor **không** truyền context, listener vẫn có thể sinh span, nhưng là **root span của trace khác** hoặc không thấy trace context mong đợi. Khi đó chúng ta mất khả năng nối toàn bộ luồng xử lý qua các module bằng trace đơn lẻ. Việc listener vẫn chạy đúng nghiệp vụ không có nghĩa context đã được bảo toàn.

### Khi sự kiện được xử lý lại sau restart

Một retry hoặc re-publication nhiều phút sau không còn context gốc trong `ThreadLocal`. Event Publication Registry quản lý **độ bền và trạng thái xử lý** của publication, không tự bảo đảm truyền lại toàn bộ distributed trace context sau restart. Để nối sự kiện với request gốc, cân nhắc:

- Lưu một **correlation ID**/event ID ổn định vào metadata nghiệp vụ (được phép ghi log có kiểm soát).
- Dùng một trace mới cho mỗi lần thử và gắn quan hệ liên quan bằng ID hoặc span link nếu tracing stack hỗ trợ và dữ liệu context được lưu một cách có chủ đích.
- Không tái sử dụng một span đang mở từ request cũ hoặc kéo dài span qua thời gian tồn đọng nhiều giờ.

**Trace context và business correlation là hai loại dữ liệu khác nhau.** Correlation cho phép tìm mọi lần thử của cùng sự kiện dù chúng thuộc nhiều trace. Khi xử lý lại, idempotency tại service đích mới bảo đảm không giữ hàng hai lần.

## 8. Span listener chưa đo được những gì?

Có nhiều mục tiêu vận hành; mỗi mục tiêu cần phép đo phù hợp.

| Cần biết | Nguồn/đo lường đề xuất | Tránh hiểu nhầm |
| --- | --- | --- |
| Một listener xử lý mất bao lâu | Module entry span hoặc custom Observation bao quanh xử lý | Không cộng thời gian chờ executor vào thời gian CPU/nghiệp vụ |
| Sự kiện bị chậm đến mức nào | Duration từ event `occurredAt` đến lúc bắt đầu; metric riêng cho queue khi có mốc submit | Event-to-listener lag gồm cả thời gian trước commit |
| Bao nhiêu sự kiện đã được phát | `module.events.published` và metric sự kiện tương ứng | Counter không xác nhận listener thành công |
| Một publication đã hoàn tất chưa | Event Publication Registry / trạng thái publication | Đã publish chưa có nghĩa đã hoàn tất |
| Module nào phụ thuộc nhau | Tài liệu module graph, `/actuator/modulith` | Quan hệ kiến trúc không cho biết latency thực tế |
| Một lần xử lý lỗi vì sao | Span lỗi + log có correlation ID + trạng thái publication | HTTP request thành công không bảo đảm async listener thành công |

**Lưu ý cardinality:** đưa `module.identifier`, tên listener, loại event vào tags hữu hạn là hợp lý; không đưa `orderId`, `customerId`, UUID hoặc trace ID vào **low-cardinality metric tag**. Các ID đó nên xuất hiện trong log/audit hoặc trace metadata được kiểm soát theo chính sách.

## 9. Kiểm thử thời điểm bắt đầu và kết thúc span

Chuẩn bị một môi trường thử nghiệm với tracer/exporter quan sát được (hoặc registry/collector in-memory) và một listener có thể giả lập trì hoãn. Nên kiểm tra hành vi observable ở cấp tích hợp, thay vì kiểm tra nội bộ cài đặt interceptor của framework.

| Tình huống | Điều cần quan sát |
| --- | --- |
| Gửi sự kiện và transaction commit thành công | Listener bắt đầu sau commit; span listener bắt đầu khi method/đoạn work chạy và kết thúc sau khi work xong |
| Transaction bị rollback | Listener `AFTER_COMMIT` không chạy; không có span của một lần xử lý listener vốn không diễn ra |
| Executor chờ lâu nhưng work rất nhanh | Event-to-listener lag lớn, listener execution span ngắn |
| Cố ý ngủ trong `reserveOnce(...)` | Duration của custom work span tăng tương ứng |
| Listener ném exception | Span được đánh dấu lỗi và kết thúc; publication không bị đánh dấu thành công |
| Bật context propagation | Span listener có trace context liên quan tới publisher khi task được submit trong context thích hợp |
| Tắt context propagation trong môi trường thử nghiệm | Có thể mất quan hệ trace ở worker; kết quả này phụ thuộc instrumentation khác đang bật |
| Resubmit sau lỗi hoặc restart | Có span mới cho lần thử mới và correlation ID giúp nối các lần thử |
| Module entry span đã được instrument | Tránh tạo thêm span toàn listener có cùng mục đích; kiểm tra `module.invocation-type` và `module.identifier` |

Một phép thử quan trọng cho **ranh giới thời gian**:

1. Cho thread pool chỉ có một worker và tạm giữ worker bằng công việc giả lập, khiến event thứ hai phải xếp hàng.
2. Phát event thứ hai, commit và đo `event-to-listener lag`.
3. Nhả worker, đo khoảng bắt đầu đến kết thúc của listener thứ hai.
4. Xác nhận **lag tăng mạnh** do chờ, còn **listener execution duration** chỉ phản ánh công việc thật.

Đừng dùng chỉ `Thread.sleep` trong listener để giả lập queue delay: ngủ trong listener sẽ kéo dài **execution span**, làm sai mục tiêu phép thử. Chỉ sử dụng cấu hình pool bị giới hạn tại môi trường test.

### Gợi ý kiểm tra trace thực tế

Trong Zipkin/Grafana/Tempo hoặc backend tương ứng:

- Tra trace theo `traceId` từ request hoặc correlation ID lưu ở log.
- Xem mốc timestamp bắt đầu của span `inventory` so với thời điểm commit/submit task từ log.
- Lọc tag `module.invocation-type=event listener` nếu đang dùng module entry span.
- Quan sát thứ tự span và các khoảng trống trên timeline; lưu ý trace exporter/sampler có thể không thu tất cả span.
- Khi không thấy listener span, kiểm tra sampling, cấu hình exporter, registration của listener, executor và phạm vi instrumentation trước khi kết luận listener không chạy.

## 10. Các lỗi thiết kế thường gặp

**Tạo span lúc `publishEvent()` và giữ mở đến khi async listener hoàn tất.** Span sẽ gộp transaction, queue và nghiệp vụ; khó phân tích độ trễ. Nếu muốn đo toàn bộ pipeline, định nghĩa thêm metric hoặc span riêng với tên thể hiện chính xác phạm vi đó.

**Bắt đầu span trên thread publisher rồi stop ở thread listener.** Scope và context gắn với thread; việc truyền đối tượng span/scope tùy tiện qua thread dễ tạo sai quan hệ hoặc lỗi resource lifecycle. Hãy truyền trace context bằng cơ chế context propagation, sau đó bắt đầu span tương ứng trong luồng xử lý của listener.

**Chỉ truyền MDC bằng tay.** Sao chép một chuỗi `traceId` cho log không tự tạo quan hệ span và không thay thế `Observation`/Micrometer context propagation. Dùng cơ chế dành cho tracing.

**Tạo trùng span do cả Modulith, `@Observed` và manual Observation cùng đo một method.** Trace có thể có nhiều cấp trùng tên/duration. Xác định rõ: module entry để xem ranh giới module; span thủ công chỉ cho tác vụ con cần quan sát.

**Coi trace là cơ chế bảo đảm giao sự kiện.** Trace giúp thấy những lần xử lý đã được instrument; Event Publication Registry và cơ chế retry mới phục vụ độ bền, còn idempotency phục vụ tính đúng khi xử lý lại.

**Bỏ qua version và các bean thực tế.** Cơ chế `@Async` phụ thuộc executor do Spring chọn; các dependency tracing và annotation instrumentation còn tùy phiên bản. Khi cấu hình không có hiệu lực, kiểm tra bean được inject/được chọn và phiên bản thư viện của dự án.

## Câu hỏi tự đánh giá

1. Nếu một event được tạo tại `t0`, commit tại `t1` và listener bắt đầu tại `t3`, nên dùng mốc nào để đo chính xác thời gian xử lý của listener? Vì sao?
2. Vì sao `@ApplicationModuleListener` khác `@EventListener` đồng bộ về transaction và thread?
3. Nếu có listener span nhưng trace ID khác trace publisher, bạn sẽ kiểm tra lớp nào trước?
4. Khi nào việc tự tạo `Observation` ngay trong listener sẽ tạo thông tin có ích, và khi nào nó chỉ tạo span trùng?
5. Vì sao metric `module.events.published` không thể dùng làm số lượng event đã xử lý thành công?
6. Sau restart, làm cách nào liên hệ trace mới của một lần retry với nghiệp vụ ban đầu?
7. Làm sao thử nghiệm để tách thời gian chờ executor ra khỏi thời gian thực thi listener?

## Tài liệu tham khảo

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): semantics của `@ApplicationModuleListener`, transaction và Event Publication Registry.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Modulith actuator, module entry spans và event metrics.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Micrometer Observation, tracing, context propagation qua `@Async`.
- [Spring Framework — Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html): giới hạn instrumentation mặc định của Spring events.
- [Micrometer Tracing — Configuring](https://docs.micrometer.io/tracing/reference/configuring.html): mối quan hệ giữa Observation, Tracing và context propagation.

