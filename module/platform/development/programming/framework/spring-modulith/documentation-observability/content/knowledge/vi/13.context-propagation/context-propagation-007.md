# ContextPropagatingTaskDecorator

Trong ứng dụng Spring Boot, một request thường bắt đầu trên một thread xử lý HTTP, sau đó có thể giao công việc sang thread pool để chạy bất đồng bộ. Các thông tin quan sát như **Observation hiện tại, trace/span context và log correlation** thường được giữ trong `ThreadLocal` hoặc cơ chế context gắn với thread. Khi task chuyển sang thread khác, các thông tin đó không tự động đi theo. Kết quả là log mất trace ID, span con bị tách khỏi trace cha, hoặc hệ thống khó liên hệ một thao tác bất đồng bộ với request đã tạo ra nó.

Spring Framework cung cấp **`ContextPropagatingTaskDecorator`** để giải quyết tình huống này cho các task được thực thi qua một `TaskExecutor`: decorator chụp (capture) context tại thời điểm task được submit, khôi phục (restore) context khi task chạy và trả thread về trạng thái trước đó sau khi task kết thúc.

Bài thuộc chương **Context propagation** của mô-đun **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Ta sẽ dùng decorator để hiểu cách nối observation/tracing qua executor, đặc biệt với các luồng bất đồng bộ liên quan đến application module và event listener.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `ThreadLocal` và context gắn với thread không tự truyền qua thread pool.
2. Mô tả vòng đời capture, restore và cleanup của `ContextPropagatingTaskDecorator`.
3. Cấu hình decorator cho `ThreadPoolTaskExecutor` hoặc dùng cấu hình auto-configured của Spring Boot khi phù hợp.
4. Phân biệt `Observation.Context`, active `Observation.Scope`, trace context và các loại context khác.
5. Giải thích vai trò của Micrometer Context Propagation và các `ThreadLocalAccessor`.
6. Áp dụng decorator cho `@Async` và xác định executor thực sự được dùng bởi listener bất đồng bộ.
7. Nhận diện các giới hạn: decorator không tự truyền mọi `ThreadLocal`, không chuyển transaction sang thread khác và không thay thế instrumentation/exporter.
8. Kiểm chứng context propagation bằng trace ID, parent span, log correlation và test có đồng bộ hóa.

## 2. Vấn đề: thread pool không tự mang context của caller

Giả sử một request tạo đơn hàng trong module `orders`, sau đó giao việc gửi thông báo cho executor:

~~~text
HTTP request thread
  traceId = abc...
  current span = orders.placeOrder
  MDC.traceId = abc...
        |
        | executor.execute(task)
        v
Thread pool worker
  traceId = ?
  current span = ?
  MDC.traceId = ?
~~~

Một `ThreadLocal` thuộc về **thread hiện tại**, không thuộc về đối tượng `Runnable` hay request. Thread pool có thể chạy task trên một worker đã được dùng bởi nhiều request khác nhau. Nếu task không có cơ chế truyền context, nó không nhìn thấy giá trị của caller; tệ hơn, một `ThreadLocal` không được dọn sạch có thể làm lộ context cũ của task trước.

### 2.1. Vì sao lỗi này ảnh hưởng tracing?

Một distributed trace thường có quan hệ:

~~~text
Trace abc...
└── HTTP POST /orders
    └── orders.placeOrder
        └── task gửi notification
            └── notification.send
~~~

Để span `notification.send` là span con hoặc span có liên hệ đúng với công việc tạo ra nó, tracing cần **current trace context** tại thời điểm task bắt đầu. Nếu context bị mất, thư viện tracing có thể tạo một trace mới, tạo span không có parent mong muốn hoặc không ghi được correlation như dự kiến.

Trong Spring Modulith, module entry span có thể mang metadata như:

- `module.identifier`: technical ID của module, ví dụ `notification`.
- `module.name`: tên hiển thị.
- `module.invocation-type`: hình thức đi vào, ví dụ `bean` hoặc `event listener`.
- `module.method`: entry method được gọi.

Các metadata này mô tả **module đang được quan sát**. Việc giữ trace context qua executor lại quyết định **span đó nối với trace cha nào**. Hai việc liên quan nhưng khác nhau.

## 3. `ContextPropagatingTaskDecorator` làm gì?

`ContextPropagatingTaskDecorator` là một implementation của Spring `TaskDecorator`. Nó dùng Micrometer Context Propagation để chụp context đã được đăng ký thông qua các accessor, sau đó bọc task bằng một `ContextSnapshot` để context được khôi phục trong lúc thực thi.

~~~mermaid
sequenceDiagram
    participant C as Caller thread
    participant D as TaskDecorator
    participant Q as Executor queue
    participant W as Worker thread
    C->>D: submit Runnable
    Note over C: Observation / trace / MDC context active
    D->>D: capture ContextSnapshot
    D->>Q: enqueue wrapped Runnable
    Q->>W: execute wrapped Runnable
    W->>W: restore snapshot into worker context
    W->>W: run original task
    W->>W: close scope / restore previous worker context
~~~

Có ba thời điểm cần nhớ:

1. **Capture khi task được decorate/submit:** decorator lấy snapshot của context hiện hành ở phía caller.
2. **Restore khi task chạy:** snapshot được mở trong worker thread để các accessor khôi phục giá trị tương ứng.
3. **Cleanup khi task kết thúc:** scope được đóng để khôi phục trạng thái context vốn có của worker, tránh context của request trước rò sang task tiếp theo.

Decorator không tạo thread, không quyết định task chạy đồng bộ hay bất đồng bộ và cũng không tự tạo observation. Nó chỉ bổ sung cơ chế truyền context cho task được executor thực thi.

### 3.1. API và package

Lớp có tên đầy đủ:

~~~java
org.springframework.core.task.support.ContextPropagatingTaskDecorator
~~~

Nó thuộc Spring Framework (từ dòng **6.1**). Ví dụ import:

~~~java
import org.springframework.core.task.TaskDecorator;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
~~~

`TaskDecorator` là abstraction cho phép bọc một `Runnable`; `ContextPropagatingTaskDecorator` là implementation dùng context snapshot của Micrometer. Dự án cần các dependency Spring/Micrometer tương thích; trong ứng dụng Spring Boot, các starter phù hợp thường quản lý các dependency nền này.

## 4. Cấu hình thủ công với `ThreadPoolTaskExecutor`

Khi ứng dụng tự khai báo thread pool, gắn decorator vào đúng executor sẽ xử lý task:

~~~java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class AsyncExecutorConfiguration {

    @Bean("applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("shop-async-");

        // Capture/restore context cho mỗi Runnable được executor chạy.
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());

        // Không cần gọi initialize() thủ công khi bean được Spring quản lý.
        return executor;
    }
}
~~~

Spring quản lý vòng đời `ThreadPoolTaskExecutor` và gọi các callback khởi tạo thích hợp cho bean. Nếu tự tạo executor ngoài Spring container, bạn phải tự quản lý khởi tạo và shutdown theo API của executor.

### 4.1. Chọn đúng executor cho `@Async`

Ví dụ:

~~~java
package com.example.shop.notification;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
class NotificationService {

    @Async("applicationTaskExecutor")
    public void sendOrderConfirmation(String orderNumber) {
        // Gửi thông báo bất đồng bộ.
    }
}
~~~

Và bật async processing:

~~~java
package com.example.shop.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
class AsyncMethodConfiguration {
}
~~~

Tên qualifier trong `@Async` phải khớp bean executor. Nếu method dùng executor khác, decorator gắn trên `applicationTaskExecutor` sẽ **không** tự động áp dụng cho executor kia.

**Lưu ý:** `@Async` chỉ hoạt động qua Spring proxy; gọi method async bằng self-invocation như `this.sendOrderConfirmation(...)` thường không đi qua proxy và không tạo task như mong muốn. Khi kiểm tra propagation, hãy gọi qua bean/proxy thực sự.

### 4.2. Cấu hình executor tự động của Spring Boot

Nếu dùng `TaskExecutor` do Spring Boot auto-configure, các phiên bản Spring Boot có hỗ trợ thuộc tính sau cho task execution:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Thuộc tính này yêu cầu cấu hình task execution mặc định bật context propagation bằng decorator tương ứng. Hãy đối chiếu tài liệu của đúng phiên bản Spring Boot.

Nếu ứng dụng **tự khai báo một `ThreadPoolTaskExecutor` riêng**, đừng mặc định property trên tự gắn decorator vào executor đó. Cấu hình `setTaskDecorator(...)` trực tiếp và bảo đảm infrastructure thực sự chọn executor đó.

## 5. Context nào được truyền?

Decorator không sao chép mọi biến toàn cục trong JVM. Micrometer Context Propagation làm việc với những context có **accessor được đăng ký** trong `ContextRegistry` hoặc được cung cấp bởi tích hợp framework.

Các loại context thường quan tâm:

| Context | Ví dụ | Điều kiện để được khôi phục |
| --- | --- | --- |
| Micrometer Observation | Current `Observation` / scope | Accessor Observation được đăng ký và registry tương thích |
| Micrometer Tracing | Current span/trace context | Tích hợp tracer/bridge và accessor tương ứng |
| Logging correlation | MDC fields như trace ID | Có accessor MDC phù hợp được đăng ký |
| Context tùy chỉnh | Tenant classification hoặc correlation metadata | Đăng ký `ThreadLocalAccessor` cho `ThreadLocal` đó |
| Spring Security context | Authentication/authorization | Dùng cơ chế tích hợp Security phù hợp; không mặc định mọi cấu hình được decorator tự xử lý |
| Transaction context | JDBC transaction gắn với thread | Không coi là context có thể chuyển sang worker; transaction cần được thiết kế riêng |

### 5.1. Micrometer Context Propagation và accessor

Micrometer Context Propagation cung cấp các abstraction như:

- `ContextRegistry`: nơi đăng ký các accessor để đọc/ghi context.
- `ThreadLocalAccessor`: mô tả cách lấy, đặt và reset một giá trị gắn với thread.
- `ContextSnapshot`: snapshot của các giá trị context đã đăng ký.
- `ContextSnapshotFactory`: tạo snapshot theo registry/cấu hình.
- `ContextPropagatingTaskDecorator`: sử dụng snapshot để bọc `Runnable`.

Có thể hình dung:

~~~text
ThreadLocal của caller
      |
      | ThreadLocalAccessor.getValue()
      v
ContextSnapshot
      |
      | TaskDecorator bọc Runnable
      v
Worker thread
      |
      | ThreadLocalAccessor.setValue(snapshot value)
      v
Task nhìn thấy context đã khôi phục
      |
      | reset/restore khi task kết thúc
      v
Worker thread trở về context ban đầu
~~~

### 5.2. Đăng ký một `ThreadLocalAccessor` tùy chỉnh

Nếu ứng dụng có context riêng và cần truyền qua executor, phải đăng ký accessor. Ví dụ dưới đây chỉ minh họa một **nhãn phân vùng** nội bộ; không dùng dữ liệu nhạy cảm hoặc giá trị không được kiểm soát:

~~~java
package com.example.shop.context;

import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ThreadLocalAccessor;

public final class RegionContext {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();
    private static final Object KEY = RegionContext.class.getName();

    private RegionContext() {
    }

    public static String get() {
        return CURRENT.get();
    }

    public static void set(String value) {
        CURRENT.set(value);
    }

    public static void clear() {
        CURRENT.remove();
    }

    public static void registerAccessor() {
        ContextRegistry.getInstance().registerThreadLocalAccessor(
                new ThreadLocalAccessor<String>() {
                    @Override
                    public Object key() {
                        return KEY;
                    }

                    @Override
                    public String getValue() {
                        return RegionContext.get();
                    }

                    @Override
                    public void setValue(String value) {
                        RegionContext.set(value);
                    }

                    @Override
                    public void reset() {
                        RegionContext.clear();
                    }
                });
    }
}
~~~

Đăng ký accessor một lần trong quá trình khởi tạo ứng dụng, không đăng ký lại ở mỗi request. Cần tránh trùng key hoặc đăng ký nhiều accessor xung đột cho cùng một context.

**Ý nghĩa:** decorator chỉ biết cách truyền giá trị nếu context có accessor tương ứng. Một `ThreadLocal` tự tạo mà không có accessor không tự xuất hiện trong snapshot.

## 6. Phân biệt Observation.Context, Scope và ThreadLocal

Ba khái niệm dễ bị gộp chung:

| Thành phần | Vai trò |
| --- | --- |
| `Observation.Context` | Dữ liệu và trạng thái thuộc một observation cụ thể |
| `Observation.Scope` | Đặt observation làm current observation trong phạm vi code hiện tại và đóng scope khi kết thúc |
| Thread-local context / trace context | Cách một số thư viện lưu trạng thái hiện hành theo thread |

Khi code mở scope:

~~~java
Observation observation =
        Observation.start("shop.orders.place", observationRegistry);

try (Observation.Scope scope = observation.openScope()) {
    // Current observation được gắn với thread hiện tại.
    processOrder();
} finally {
    observation.stop();
}
~~~

Nếu bên trong `processOrder()` submit một task, `ContextPropagatingTaskDecorator` có thể capture context hiện hành (nếu accessor được đăng ký) và restore nó trong worker thread. Khi task chạy, code có thể tiếp tục dùng context observation/tracing theo tích hợp đã cấu hình.

**Observation.Context không phải bản thân ThreadLocal.** Context là object chứa dữ liệu; scope và accessor là những cơ chế giúp thông tin hiện hành được nhìn thấy ở thread/handler thích hợp.

## 7. Ứng dụng vào Spring Modulith và event listener

Spring Modulith hỗ trợ tương tác module qua bean calls và application events. `@ApplicationModuleListener` thường được dùng cho listener theo transaction và thực thi bất đồng bộ. Khi listener chạy qua executor, context propagation có thể giúp giữ thông tin tracing/logging từ luồng tạo event, tùy cấu hình listener và executor.

~~~mermaid
sequenceDiagram
    participant H as HTTP thread
    participant O as orders module
    participant E as Event publication
    participant X as Async executor
    participant I as inventory listener
    H->>O: placeOrder()
    Note over H,O: Trace context = abc...
    O->>E: publish OrderPlaced
    O-->>H: response
    E->>X: submit listener task
    Note over X: ContextPropagatingTaskDecorator<br/>capture / restore
    X->>I: on(OrderPlaced)
    Note over I: inventory module metadata<br/>và trace context nếu được truyền
~~~

Có hai vấn đề độc lập:

1. **Module metadata:** khi listener đi vào module `inventory`, Spring Modulith nhận diện module và có thể gắn các thuộc tính như `module.identifier=inventory`, `module.invocation-type=event listener`, `module.method=on`.
2. **Trace context:** nếu muốn span listener liên kết với trace của publisher, executor/transport phải truyền hoặc khôi phục context đúng cách.

Decorator hỗ trợ vấn đề thứ hai **trong phạm vi executor được gắn nó**. Nó không tự tạo module entry span nếu không có Modulith instrumentation; cũng không biến event publication thành xử lý đồng bộ.

### 7.1. Xác nhận decorator gắn vào đúng executor

Không phải mọi task bất đồng bộ trong ứng dụng đều chắc chắn dùng cùng một executor. Cần xác định:

- `@Async("...")` chỉ định bean nào?
- Cấu hình Spring Modulith event listener đang dùng executor nào?
- Có executor riêng cho scheduler, messaging hoặc integration client không?
- Task có được gửi qua `ThreadPoolTaskExecutor` đã cấu hình decorator không?

Nếu listener sử dụng executor khác, hãy gắn decorator vào executor đó hoặc cấu hình cơ chế propagation phù hợp cho chính pipeline. Đừng chỉ nhìn thấy bean `applicationTaskExecutor` rồi kết luận toàn ứng dụng đã được bảo vệ.

## 8. ContextPropagatingTaskDecorator không truyền mọi thứ

Decorator có phạm vi cụ thể: capture/restore **các context đã được tích hợp và đăng ký**. Những điều sau không tự động được bảo đảm:

- **Không truyền transaction JDBC/JPA sang worker thread.** Transaction imperative thường gắn với thread. Một task async nên mở transaction riêng tại worker nếu nghiệp vụ cần, ví dụ đặt `@Transactional` ở method listener phù hợp.
- **Không truyền mọi biến `ThreadLocal` tự tạo** nếu thiếu accessor.
- **Không sao chép toàn bộ request object hoặc HTTP body** sang worker.
- **Không tự bảo đảm SecurityContext** nếu ứng dụng dùng Spring Security mà chưa cấu hình tích hợp phù hợp.
- **Không tự gửi trace tới backend.** Vẫn cần Micrometer Tracing, exporter, collector, sampling và network.
- **Không tự nối các message qua broker hoặc service khác** nếu propagation headers/instrumentation của transport chưa được cấu hình.
- **Không thay đổi semantics lỗi của task.** Exception vẫn được xử lý theo API executor, `Future`, `CompletableFuture` hoặc `AsyncUncaughtExceptionHandler`.

### 8.1. Transaction là một ranh giới riêng

Ví dụ:

~~~java
@Service
class InventoryListener {

    @ApplicationModuleListener
    @Transactional
    void on(OrderPlaced event) {
        // Worker thread mở transaction phù hợp cho việc giữ hàng.
        reserveStock(event.orderId());
    }
}
~~~

Đoạn code chỉ minh họa việc listener xử lý trong transaction của chính nó theo cấu hình Spring Modulith/Spring. Không hiểu `ContextPropagatingTaskDecorator` là cách mang transaction của publisher qua thread. Với transactional event listener, thời điểm publish, commit và dispatch phải tuân theo semantics của event publication registry.

### 8.2. Security context cần quyết định riêng

Nếu cần chuyển thông tin xác thực sang task async, dùng tích hợp Spring Security được thiết kế cho `SecurityContext`, ví dụ các executor/wrapper `DelegatingSecurityContext...` tương ứng với phiên bản. Không nên giả định `ContextPropagatingTaskDecorator` tự động thay thế các wrapper bảo mật trong mọi ứng dụng.

Nguyên tắc là **chỉ truyền context cần thiết**. Đôi khi task nền nên chạy bằng service identity riêng, không nên kế thừa quyền của request caller.

## 9. Cấu hình và kiểm chứng trong Spring Boot

### 9.1. Dependency

`ContextPropagatingTaskDecorator` thuộc Spring Framework. Trong ứng dụng Spring Boot, các starter web/task và observability tương thích thường đưa các module nền cần thiết vào dependency graph. Nếu tự quản lý dependency, xác nhận có:

- Spring Framework 6.1 trở lên cho `ContextPropagatingTaskDecorator`.
- Micrometer Context Propagation tương thích.
- Micrometer Observation/Tracing nếu muốn truyền observation hoặc trace context.
- Tracer bridge/exporter phù hợp nếu cần gửi trace đến backend.

Không thêm một phiên bản Micrometer Context Propagation tùy ý nếu Spring Boot BOM đã quản lý; lệch version có thể gây lỗi tương thích API.

### 9.2. Kiểm tra context qua executor

Một bài test thực tế nên xác minh **giá trị được nhìn thấy bên trong worker** và thread context được reset sau task. Hình thức tổng quát:

~~~java
@Test
void propagatesObservationContextToWorker() throws Exception {
    // 1. Tạo ObservationRegistry có context propagation accessor.
    // 2. Tạo ThreadPoolTaskExecutor với ContextPropagatingTaskDecorator.
    // 3. Mở Observation.Scope ở caller thread.
    // 4. Submit task; trong worker đọc current observation/trace context.
    // 5. Đồng bộ kết quả bằng CompletableFuture hoặc CountDownLatch.
    // 6. Xác nhận worker thấy context của caller.
    // 7. Submit một task mới không có context và xác nhận không rò context cũ.
}
~~~

Đây là **checklist thiết kế test**, không phải test code có thể copy chạy nguyên trạng. Test phải dùng cùng `ObservationRegistry`, accessor và executor với cấu hình ứng dụng. Không kiểm tra context bằng `Thread.sleep()` vì dễ gây flaky; dùng `CompletableFuture`, `CountDownLatch` hoặc assertion đồng bộ.

### 9.3. Kiểm tra trên trace backend

1. Bật tracing và cấu hình exporter/collector.
2. Tạm tăng sampling trong môi trường lab để dễ tìm trace.
3. Gửi request đi qua module `orders`, tạo một task async hoặc event listener.
4. Tìm span phía worker bằng trace ID.
5. Kiểm tra parent/trace relationship và các module attributes.
6. So sánh khi decorator được gắn vào executor và khi không gắn.
7. Nếu trace vẫn tách, xác minh executor thật, accessor, async dispatch và propagation qua transport.

Ví dụ hình dung:

~~~text
Có propagation:
traceId = abc...
orders.placeOrder
└── inventory.on(OrderPlaced)

Không có propagation:
traceId = abc...
orders.placeOrder

traceId = xyz... hoặc không có parent mong muốn
inventory.on(OrderPlaced)
~~~

Đây là kết quả minh họa. Thực tế có thể xuất hiện span link hoặc trace mới tùy cách tích hợp; hãy đọc trace ID, span ID và parent/link thay vì dựa vào cách UI vẽ cây.

## 10. Chi phí và giới hạn hiệu năng

Context propagation có overhead: snapshot phải capture các accessor đã đăng ký, worker phải restore và sau task phải cleanup. Với tác vụ lớn như gọi dịch vụ ngoài hoặc xử lý event, overhead này thường nhỏ so với công việc chính. Với **rất nhiều task cực ngắn**, chi phí capture/restore có thể đáng kể.

Spring Framework khuyến nghị cân nhắc decorator này khi thực sự cần truyền context; không phải ứng dụng nào cũng nên bật mọi context cho mọi task. Có thể:

- Chỉ gắn decorator vào executor cần tracing/log correlation.
- Giữ số lượng accessor vừa đủ.
- Không chụp payload lớn hoặc object graph nặng.
- Không tạo task cực nhỏ chỉ để tránh thao tác đồng bộ.
- Đo overhead và throughput dưới tải đại diện trước khi bật rộng.

Decorator cũng không phải giải pháp thay thế cho **structured concurrency**, queue, durable messaging hoặc thiết kế workflow. Nó chỉ giải quyết việc giữ context trong lúc chuyển thực thi qua task executor.

## 11. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Trace ID mất trong async task | Executor chưa gắn decorator hoặc accessor tracing chưa hoạt động | Kiểm tra bean executor thực tế, tracer bridge và context registry |
| Log không có MDC correlation | MDC accessor chưa được đăng ký hoặc logging pattern không in field | Kiểm tra MDC accessor, cấu hình logging và worker task |
| Task vẫn chạy nhưng trace tách thành root mới | Context không được restore hoặc task qua broker/client chưa propagate headers | Xem trace/span IDs và đường chuyển giao |
| Task A thấy context của task B | ThreadLocal không được reset hoặc custom accessor thiếu `reset()` | Kiểm tra cleanup, accessor và test chạy liên tiếp trên cùng worker |
| `spring.task.execution.propagate-context=true` nhưng không tác dụng | Ứng dụng dùng custom executor không thuộc auto-configuration | Gắn `ContextPropagatingTaskDecorator` trực tiếp vào executor thực sự |
| Một listener có module metadata nhưng trace không có parent publisher | Module instrumentation vẫn hoạt động nhưng trace context không được truyền | Kiểm tra async executor và parent/span context |
| Transaction không nhìn thấy dữ liệu của caller | Transaction không tự truyền qua thread | Thiết kế transaction mới tại worker hoặc dùng event/outbox đúng semantics |
| Security principal bị mất | Security context cần tích hợp riêng | Dùng cơ chế Spring Security tương ứng |
| Exception không xuất hiện trong caller | Task async có cơ chế lỗi riêng | Quan sát `Future`/`CompletableFuture` hoặc `AsyncUncaughtExceptionHandler` |
| Task nhỏ chạy chậm hơn sau khi bật decorator | Overhead capture/restore/accessor | Benchmark và giới hạn executor/accessors |

### 11.1. Phân biệt lỗi propagation với lỗi export

Một task có thể **đã nhận đúng context** nhưng không thấy trace trên UI do exporter/collector lỗi, sampling bỏ trace hoặc backend chưa ingest. Ngược lại, trace có thể được export nhưng span listener vẫn là trace mới vì propagation không hoạt động.

Điều tra theo lớp:

1. Task có chạy trên executor dự kiến không?
2. Worker có đọc được context mong đợi không?
3. Span có được tạo và có đúng trace/parent không?
4. Exporter có gửi dữ liệu không?
5. Backend có nhận và truy vấn được không?

Không thay đổi code nghiệp vụ chỉ vì dashboard không hiển thị span.

## 12. Bài thực hành

### Bài 1 — Quan sát ThreadLocal qua thread pool

Tạo một `ThreadLocal<String>` đơn giản. Đặt giá trị ở caller, submit `Runnable` tới `ThreadPoolTaskExecutor` và đọc ở worker. Thực hiện lại sau khi cấu hình decorator và accessor. Ghi lại sự khác biệt.

### Bài 2 — Gắn decorator vào `@Async`

Tạo `applicationTaskExecutor` có `ContextPropagatingTaskDecorator`, bật `@EnableAsync` và gọi một method `@Async("applicationTaskExecutor")` bên trong Observation scope. Kiểm tra current observation ở worker.

### Bài 3 — So sánh trace ID

Bật Micrometer Tracing và một exporter. Gọi HTTP endpoint tạo task async. Chạy hai lượt: có decorator và không có decorator. So sánh trace ID, parent span và log correlation ở worker.

### Bài 4 — Áp dụng cho listener của Spring Modulith

Tạo `@ApplicationModuleListener` trong module `inventory` để xử lý `OrderPlaced`. Xác minh listener dùng executor nào; cấu hình decorator trên executor đó. Kiểm tra:

- Module span của listener có `module.identifier=inventory` không?
- `module.invocation-type` có nhận diện là event listener không?
- Trace ID và quan hệ parent có được nối với publisher không?
- Event Publication Registry có ghi nhận completion/failure độc lập với trace hay không?

### Bài 5 — Kiểm tra không rò context giữa hai task

Dùng pool chỉ có một worker để bảo đảm hai task chạy trên cùng thread:

1. Task A được submit khi caller có context `region=west`.
2. Task B được submit khi caller không có region context.
3. Xác nhận task B không nhìn thấy `region=west` của task A.
4. Thử bỏ `reset()` khỏi accessor tùy chỉnh trong một nhánh test để quan sát nguy cơ rò context, sau đó khôi phục implementation đúng.

### Bài 6 — Phân biệt transaction và tracing context

Tạo một request có transaction nguồn rồi submit task async. Kiểm tra trace context có thể được truyền, nhưng transaction JDBC không được coi là cùng transaction của caller. Thiết kế transaction mới tại listener và giải thích vì sao đây là hai quyết định riêng.

## 13. Câu hỏi ôn tập

1. `ThreadLocal` có được chia sẻ tự động giữa các thread trong thread pool không?
2. `ContextPropagatingTaskDecorator` capture context ở giai đoạn nào?
3. `ContextSnapshot` và `ThreadLocalAccessor` có vai trò gì?
4. Vì sao custom `ThreadLocal` cần accessor mới được truyền?
5. Khi task kết thúc, tại sao phải restore/reset context của worker?
6. `ContextPropagatingTaskDecorator` có tự tạo executor hoặc thread không?
7. Khi nào dùng `spring.task.execution.propagate-context`?
8. Vì sao property auto-config không chắc tác động lên custom executor?
9. Decorator có truyền transaction JDBC/JPA của caller sang worker không?
10. Security context có luôn tự động được truyền không?
11. Metadata `module.identifier` khác trace ID như thế nào?
12. Vì sao module entry span của listener có thể mang đúng metadata nhưng không có parent trace mong muốn?
13. Khi kiểm tra lỗi propagation, cần phân biệt những lớp nào từ executor đến backend?
14. Vì sao không nên bật context propagation cho mọi task rất ngắn mà chưa đo overhead?

## 14. Ghi nhớ

**`ContextPropagatingTaskDecorator` giúp chuyển context đã được đăng ký từ thread submit task sang thread thực thi task.** Nó chụp context, khôi phục context trong worker và dọn/khôi phục trạng thái sau khi task hoàn tất. Trong Spring Boot, bạn có thể gắn decorator trực tiếp vào `ThreadPoolTaskExecutor` hoặc dùng property auto-configuration ở phiên bản hỗ trợ.

Trong Spring Modulith, decorator đặc biệt hữu ích khi một luồng chuyển từ request/module đồng bộ sang executor xử lý event hoặc tác vụ nền: **module metadata** cho biết listener thuộc module nào, còn **trace context propagation** giúp nối span listener với hoạt động đã khởi phát nếu cơ chế dispatch hỗ trợ. Hãy xác minh executor thực tế và accessor đã đăng ký.

Decorator **không truyền mọi `ThreadLocal`, không chuyển transaction qua thread, không thay thế cấu hình Security, instrumentation, sampling hay exporter**. Chọn context thực sự cần thiết, kiểm tra cleanup và đo overhead trước khi áp dụng rộng.

### Tài liệu tham khảo

- [Spring Framework — `ContextPropagatingTaskDecorator` JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html).
- [Spring Framework — `TaskDecorator` JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskDecorator.html).
- [Micrometer Context Propagation — Reference](https://docs.micrometer.io/context-propagation/reference/).
- [Micrometer Context Propagation — `ThreadLocalAccessor` API](https://docs.micrometer.io/context-propagation/api/io/micrometer/context/ThreadLocalAccessor.html).
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html).
- [Spring Boot — Observability and Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
- [Spring Modulith — Application Events and `@ApplicationModuleListener`](https://docs.spring.io/spring-modulith/reference/events.html).
- [Spring Modulith — Observing Application Modules](https://docs.spring.io/spring-modulith/reference/production-ready.html).
