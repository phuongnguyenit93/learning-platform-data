# Context khi xử lý application event bất đồng bộ

Trong một ứng dụng Spring Boot được tổ chức bằng **Spring Modulith**, một application module thường phát sự kiện để module khác xử lý mà không cần gọi trực tiếp implementation của nhau. Cách làm này giúp giữ ranh giới mô-đun, nhưng cũng tạo ra một vấn đề khi vận hành: listener có thể chạy **sau khi transaction gốc commit và trên một thread khác**. Những thông tin đang gắn với thread của request — chẳng hạn tracing context, observation context hoặc logging MDC — có thể không còn xuất hiện trong listener.

Nếu context bị đứt, backend tracing có thể hiển thị HTTP request ở module `order` nhưng không nối được với công việc giữ hàng của `inventory`. Log listener thiếu `traceId` khiến việc điều tra khó hơn. Ngược lại, nếu truyền nhầm toàn bộ request/security context sang tác vụ nền, hệ thống có thể giữ dữ liệu không cần thiết hoặc tạo ra ranh giới quyền truy cập sai.

Bài học thuộc chương **Context propagation** của module `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Ta sẽ tìm hiểu cách truyền ngữ cảnh khi xử lý application event bất đồng bộ, cách Spring Modulith triển khai `@ApplicationModuleListener`, cách cấu hình Micrometer Context Propagation cho executor, và cách phân biệt **trace context**, **tenant/business context**, **security context** với **transaction context**.

> **Phạm vi phiên bản:** Ví dụ chính dùng Spring Boot 3.x và Spring Modulith tương thích. `ContextPropagatingTaskDecorator` có từ Spring Framework 6.1. Thuộc tính `spring.task.execution.propagate-context` có trong các phiên bản Spring Boot hỗ trợ cấu hình executor này (ví dụ tài liệu Boot 3.4). Hãy kiểm tra tài liệu đúng BOM của dự án; không giả định mọi bản cũ đều có cùng property.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao context gắn với thread hiện tại có thể mất khi listener chạy bất đồng bộ.
2. Mô tả vòng đời của `@ApplicationModuleListener`: listener transactional, bất đồng bộ và chạy trong transaction riêng sau commit.
3. Phân biệt context propagation trong cùng JVM với truyền trace context qua message broker hoặc HTTP.
4. Cấu hình `ContextPropagatingTaskDecorator` cho executor thực sự chạy listener.
5. Sử dụng cấu hình Spring Boot để truyền context khi dùng executor được auto-configure.
6. Phân biệt trace/observation context với transaction, tenant và security context.
7. Thiết kế event payload có correlation/business metadata rõ ràng, không phụ thuộc ThreadLocal của request.
8. Kiểm chứng trace/log của listener và xác định các giới hạn khi event được retry hoặc phát lại sau khi ứng dụng khởi động lại.

## 2. Context là gì và vì sao cần truyền?

**Context** là tập thông tin gắn với một đơn vị công việc đang thực thi. Tùy tầng ứng dụng, context có thể chứa:

| Loại context | Ví dụ | Câu hỏi được hỗ trợ |
| --- | --- | --- |
| **Observation context** | Observation đang hoạt động, thông tin của thao tác hiện tại | Công việc nào đang được đo? |
| **Tracing context** | `traceId`, `spanId`, parent/span relationship | Các bước này thuộc trace nào? |
| **Logging context (MDC)** | Trường `traceId`, `spanId` hoặc correlation key trong log | Log nào thuộc cùng một thao tác? |
| **Security context** | Principal, authorities, authentication | Ai đang được xác thực trong thao tác? |
| **Tenant/business context** | Tenant đã được xác thực, correlation ID, locale | Tác vụ nền thuộc tenant/nghiệp vụ nào? |
| **Transaction context** | Transaction hiện tại, connection và trạng thái commit | Dữ liệu đang ở trong giao dịch nào? |

Trong ứng dụng đồng bộ, các thư viện thường đặt một phần context vào `ThreadLocal`. Khi lời gọi tiếp tục trên cùng thread, code bên dưới có thể đọc context đó. Nhưng thread pool tái sử dụng thread và tác vụ async có thể chạy ở thread khác:

~~~mermaid
flowchart LR
    Request["HTTP request thread"] --> ThreadLocal["ThreadLocal / observation scope"]
    Request --> Submit["Submit task to executor"]
    Submit --> Worker["Worker thread"]
    ThreadLocal -. "Không tự chuyển sang thread khác" .-> Worker
    Worker --> Listener["Application event listener"]
~~~

**Không nên coi ThreadLocal là dữ liệu được mang theo tự động.** Nếu không có cơ chế capture/restore, worker thread có thể không có context của request, hoặc có context cũ nếu một thư viện quản lý ThreadLocal không đúng. Đây là một lý do phải dùng cơ chế propagation có quản lý vòng đời.

### Context propagation thực hiện việc gì?

Một cơ chế propagation thường có ba bước:

1. **Capture:** chụp các context values đã được đăng ký tại thời điểm task được gửi.
2. **Restore:** cài những giá trị ấy vào execution context của thread chạy task.
3. **Cleanup/restore previous state:** sau khi task kết thúc, khôi phục trạng thái thread trước đó để tránh rò context sang task tiếp theo.

Micrometer Context Propagation cung cấp các thành phần như `ThreadLocalAccessor`, `ContextSnapshot` và registry để kết nối các context carriers. Spring Framework cung cấp `ContextPropagatingTaskDecorator` để bọc task của executor bằng thao tác capture/restore phù hợp.

**Chỉ các context có accessor tương ứng mới được truyền theo cơ chế này.** Việc đặt một biến bất kỳ vào ThreadLocal không tự động khiến Micrometer biết cách đọc, ghi và khôi phục nó.

## 3. Vì sao application event bất đồng bộ làm context bị đứt?

Giả sử ứng dụng bán hàng có ba module:

- `order` nhận request và lưu đơn.
- `inventory` giữ hàng khi nhận `OrderPlaced`.
- `notification` gửi thông báo sau khi đơn được tạo.

Luồng nghiệp vụ:

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order module
    participant DB as Database
    participant Inventory as inventory listener
    participant Notify as notification listener

    Client->>Order: POST /orders
    Order->>DB: Lưu đơn + phát OrderPlaced
    Order->>DB: Commit transaction
    Order-->>Client: 201 Created
    Note over Order,Inventory: Các listener xử lý bất đồng bộ sau commit
    Order-->>Inventory: OrderPlaced
    Order-->>Notify: OrderPlaced
    Inventory->>DB: Giữ hàng
    Notify->>Notify: Gửi thông báo
~~~

Với Spring Modulith, `@ApplicationModuleListener` là một cách khai báo listener tích hợp giữa application module. Annotation này kết hợp:

- `@Async`: xử lý bất đồng bộ.
- `@TransactionalEventListener`: mặc định lắng nghe ở giai đoạn sau commit (`AFTER_COMMIT`).
- `@Transactional(propagation = REQUIRES_NEW)`: chạy listener trong transaction riêng.

Như vậy, request gốc có thể hoàn tất và trả HTTP response trước khi listener hoàn thành. Listener chạy ở thread khác, nên context dựa trên ThreadLocal không tự nhiên tồn tại ở đó. **Transaction của listener cũng là transaction mới**, không phải transaction gốc được mang qua thread.

Ví dụ listener:

~~~java
package com.example.shop.inventory;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ReserveInventoryOnOrderPlaced {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Giữ hàng trong transaction riêng của listener.
    }
}
~~~

Annotation hiện hành thuộc package `org.springframework.modulith.events`. Dự án cũ có thể gặp API legacy ở package khác; hãy dùng API theo version Spring Modulith đang quản lý. Nếu cần độ tin cậy khi ứng dụng hoặc listener gặp lỗi, nên kết hợp listener với **Event Publication Registry** và cấu hình persistence phù hợp. Context propagation không thay thế registry, retry hoặc idempotency.

### Điều gì xảy ra nếu không truyền context?

Ví dụ request gốc có:

~~~text
HTTP request:
  traceId = A
  spanId  = H1
  thread  = http-nio-8080-exec-3
~~~

Listener có thể ghi:

~~~text
inventory listener:
  traceId = (không có) hoặc B
  spanId  = I1
  thread  = task-2
~~~

Khi đó, backend tracing có thể không hiển thị span listener trong trace `A`. Log của listener cũng có thể thiếu trace ID nếu MDC không được khôi phục. Điều này **không chứng minh listener không chạy**; cần kiểm tra log nghiệp vụ, metric consumer và publication state riêng.

## 4. Các loại context không được đánh đồng

Một lỗi thiết kế phổ biến là nói “đã truyền context” nhưng không xác định đang nói tới context nào. Hãy phân biệt:

| Loại | Cách truyền phù hợp | Điều không được bảo đảm |
| --- | --- | --- |
| **Observation/tracing** | Micrometer Context Propagation, tracing instrumentation và executor decorator | Listener thành công hoặc có transaction chung |
| **Logging MDC** | MDC accessor/bridge được đăng ký và propagation đúng | Mọi trường log tùy ý đều an toàn hoặc có mặt |
| **Tenant/business** | Đưa metadata cần thiết vào event payload hoặc tra nguồn server-side đáng tin cậy | ThreadLocal tenant tự tồn tại sau commit |
| **Security** | Xác định listener chạy dưới service identity hay có chủ đích dùng security context; cấu hình Spring Security phù hợp | Context propagation cho observation tự động truyền mọi Authentication |
| **Transaction** | Listener mở transaction riêng theo annotation và transaction manager | Transaction gốc được chuyển sang thread listener |
| **HTTP request attributes** | Chỉ giữ khi thực sự cần và có cơ chế hỗ trợ rõ ràng | Request/response object có thể sử dụng an toàn sau khi request kết thúc |

**Trace context là metadata vận hành, không phải quyền truy cập.** Một trace ID được truyền thành công không có nghĩa listener được phép truy cập dữ liệu của tenant. Tương tự, việc có tenant ID trong event không thay thế kiểm tra tenant ownership và authorization tại nơi tiêu thụ.

## 5. Truyền observation/tracing context trong cùng JVM

### Micrometer Context Propagation

Micrometer Context Propagation cung cấp một abstraction để đọc/ghi context từ nhiều carrier. Ví dụ thường gặp:

- `ThreadLocal`: context gắn với thread.
- Reactor `Context`: context gắn với reactive subscription.
- `ContextSnapshot`: snapshot các giá trị đã đăng ký, có thể restore trong một phạm vi thực thi khác.
- `ThreadLocalAccessor`: quy định cách lấy, đặt và xóa giá trị cho một context carrier.

Trong Spring Boot, observation và tracing integration có thể đăng ký các accessor cần thiết. Vì vậy, khi task chuyển thread, ứng dụng cần sử dụng executor có cơ chế propagation tương ứng.

### Spring Framework: ContextPropagatingTaskDecorator

Từ Spring Framework 6.1, có thể dùng:

~~~java
org.springframework.core.task.support.ContextPropagatingTaskDecorator
~~~

Decorator bọc `Runnable` của executor để capture và restore context đã đăng ký quanh thời gian task chạy. Nó đặc biệt hữu ích khi task được gửi sang một thread khác và cần giữ observation/logging context.

**Lưu ý chi phí:** việc capture/restore có overhead. Với tác vụ cực nhỏ và tần suất rất cao, cần benchmark; không phải mọi task đều cần toàn bộ context.

## 6. Cách 1 — Dùng executor được Spring Boot auto-configure

Nếu ứng dụng dùng `AsyncTaskExecutor` do Spring Boot tự cấu hình cho các phương thức `@Async`, những phiên bản Boot hỗ trợ property này có thể bật propagation bằng:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Property này yêu cầu executor được **auto-configure** theo cơ chế Spring Boot. Nếu ứng dụng đã cung cấp executor riêng, không nên giả định property tự động thêm decorator vào executor tùy chỉnh đó.

Với `@ApplicationModuleListener` (có meta-annotation `@Async`), hãy xác minh listener thực sự dùng executor được Boot cấu hình. Nếu dự án có nhiều executor, có `AsyncConfigurer` hoặc có cấu hình async riêng, cần kiểm tra cơ chế lựa chọn executor trước khi kết luận property có hiệu lực.

### Khi nào nên chọn cách này?

- Ứng dụng dùng executor mặc định của Spring Boot cho async.
- Không cần một pool riêng với chính sách queue/thread khác.
- Phiên bản Spring Boot có property `spring.task.execution.propagate-context`.
- Muốn áp dụng context propagation thống nhất cho các tác vụ chạy qua executor auto-configure.

## 7. Cách 2 — Gắn TaskDecorator vào executor tùy chỉnh

Nếu ứng dụng tự tạo `ThreadPoolTaskExecutor`, hãy đăng ký decorator trực tiếp vào **đúng executor đang chạy listener**.

Ví dụ:

~~~java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncExecutionConfiguration {

    @Bean
    ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }

    @Bean(name = "taskExecutor")
    ThreadPoolTaskExecutor taskExecutor(
            ContextPropagatingTaskDecorator contextPropagatingTaskDecorator) {

        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("module-events-");
        executor.setTaskDecorator(contextPropagatingTaskDecorator);
        return executor;
    }
}
~~~

Giải thích:

1. `@EnableAsync` bật xử lý annotation `@Async` nếu ứng dụng chưa bật ở cấu hình khác.
2. Bean `ContextPropagatingTaskDecorator` tạo cơ chế bọc task bằng context snapshot.
3. `ThreadPoolTaskExecutor` là pool thực thi công việc bất đồng bộ.
4. `setTaskDecorator(...)` gắn propagation vào pool.
5. Tên bean `taskExecutor` giúp Spring `@Async` tìm executor mặc định theo quy tắc lựa chọn executor. Nếu dự án có nhiều executor, `AsyncConfigurer` hoặc cấu hình lựa chọn rõ ràng có thể cần thiết.

**Không tạo một executor có decorator rồi mặc định mọi listener đều dùng nó.** Phải kiểm tra bean executor mà `@ApplicationModuleListener`/Spring `@Async` thực sự chọn. Khi ứng dụng có custom `AsyncConfigurer`, executor bean riêng hoặc cấu hình thư viện, cách lựa chọn có thể khác.

### Dependency

Spring Framework 6.1+ có lớp `ContextPropagatingTaskDecorator`. Cơ chế snapshot dựa trên Micrometer Context Propagation; trong một số dependency graph thư viện này đã được kéo theo, nhưng nếu không có trên classpath, cần khai báo dependency tương thích:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>context-propagation</artifactId>
</dependency>
~~~

Version nên do BOM Spring Boot quản lý. Nếu ứng dụng cũng xuất trace, cần tracing bridge/exporter tương ứng; decorator không tự cài backend.

## 8. Cách 3 — Tự quản lý executor và context accessor

Đôi khi ứng dụng có context riêng ngoài observation/tracing, chẳng hạn một `TenantContextHolder` dựa trên ThreadLocal. Context Propagation không tự biết cấu trúc ThreadLocal tùy biến đó. Ta cần đăng ký một accessor để định nghĩa cách capture, restore và clear.

Ví dụ khái niệm:

~~~java
// Pseudocode minh họa hợp đồng; không phải API hoàn chỉnh để copy.
class TenantContextAccessor {

    Object key() {
        return "tenant";
    }

    Object getValue() {
        return TenantContextHolder.getCurrentTenant();
    }

    void setValue(Object value) {
        TenantContextHolder.setCurrentTenant((String) value);
    }

    void setValue() {
        TenantContextHolder.clear();
    }
}
~~~

Trong mã thực tế, triển khai interface `io.micrometer.context.ThreadLocalAccessor<T>` theo đúng version, đăng ký vào `ContextRegistry` đang được dùng bởi snapshot factory, và viết test để chứng minh:

- Giá trị được capture từ thread gửi task.
- Giá trị được restore ở worker thread trong lúc task chạy.
- Giá trị trước đó của worker thread được khôi phục hoặc context được xóa sau task.
- Không có tenant/user context từ task trước rò sang task kế tiếp.

**Đừng đăng ký accessor chỉ để truyền mọi ThreadLocal.** Chỉ đưa context thật sự cần thiết và có vòng đời rõ ràng. Với tenant/business metadata, event payload thường là nguồn dữ liệu minh bạch hơn một ThreadLocal ẩn.

## 9. Event payload nên mang business context cần thiết

Context propagation phục vụ liên kết **ngữ cảnh thực thi**. Một event còn phải mang những dữ liệu nghiệp vụ cần thiết để consumer tự xử lý, kể cả khi:

- Listener chạy sau khi request gốc đã kết thúc.
- Event được retry.
- Publication được phục hồi sau khi ứng dụng restart.
- Consumer chạy ở tiến trình hoặc service khác.

Ví dụ record:

~~~java
package com.example.shop.order;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        String tenantId,
        String correlationId,
        Instant occurredAt) {
}
~~~

Trong ví dụ này:

- `eventId` định danh publication/event theo quy ước nghiệp vụ.
- `orderId` xác định đơn cần xử lý.
- `tenantId` là tenant đã được xác thực và gắn bởi phía server nếu listener cần xử lý theo tenant.
- `correlationId` hỗ trợ liên kết các bước nghiệp vụ qua nhiều event.
- `occurredAt` ghi thời điểm nghiệp vụ phát sinh.

Không đưa dữ liệu nhạy cảm không cần thiết vào event. Consumer vẫn phải kiểm tra quyền và tính hợp lệ của tenant theo mô hình bảo mật; việc event chứa tenant ID không tự chứng minh người gửi có quyền thao tác trên tenant đó.

### Publisher và listener

Publisher phát event trong transaction nghiệp vụ:

~~~java
package com.example.shop.order;

import java.time.Instant;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderService {

    private final ApplicationEventPublisher events;

    OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void placeOrder(
            UUID orderId,
            String trustedTenantId,
            String correlationId) {

        // Lưu đơn hàng trong transaction này.
        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                orderId,
                trustedTenantId,
                correlationId,
                Instant.now()));
    }
}
~~~

Listener ở module khác xử lý sau commit:

~~~java
package com.example.shop.inventory;

import com.example.shop.order.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryManagement {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Dùng orderId/tenantId/correlationId từ event đã được kiểm soát.
        // Gọi nghiệp vụ giữ hàng trong transaction của listener.
    }
}
~~~

Các ví dụ là skeleton để giải thích ranh giới event; trong ứng dụng thật, cần API module công khai phù hợp, persistence, validation, idempotency và xử lý lỗi.

**Không trông chờ request ThreadLocal để tìm tenant trong listener.** Nếu consumer cần tenant để truy cập dữ liệu, hãy lấy từ event hoặc tra lại nguồn server-side tin cậy.

## 10. Truyền trace context trong cùng JVM và qua message broker

Hai trường hợp thường bị gộp làm một:

### A. Task async trong cùng JVM

Khi Spring gửi task vào executor, `ContextPropagatingTaskDecorator` có thể capture/restore context đã đăng ký trong cùng tiến trình. Đây là cơ chế phù hợp cho `@Async` và executor dùng bởi `@ApplicationModuleListener`.

~~~text
HTTP thread
  traceId=A, spanId=H
       |
       | submit task + capture context
       v
Executor worker
  restore traceId=A
  listener spanId=L
~~~

Span listener có thể được liên kết với trace A nếu tracing integration và thời điểm capture phù hợp. Parent span HTTP có thể đã kết thúc trước khi listener hoàn tất; duration của listener **không được cộng vào HTTP response time**. Một số cách biểu diễn tracing có thể dùng span link cho công việc bất đồng bộ có vòng đời độc lập.

### B. Event đi qua broker hoặc ranh giới tiến trình

TaskDecorator chỉ xử lý task trong executor của **một tiến trình**. Nó không gửi context qua Kafka, RabbitMQ, HTTP hoặc một process khác.

Với messaging, tracing instrumentation cần:

1. **Inject** trace context vào message headers khi producer gửi.
2. **Extract** trace context từ headers khi consumer nhận.
3. Tạo span cho việc xử lý message và nối quan hệ theo chuẩn propagation (ví dụ W3C Trace Context) mà stack hỗ trợ.

~~~mermaid
sequenceDiagram
    participant P as Producer / order
    participant B as Message broker
    participant C as Consumer / inventory
    P->>P: Tạo span publish
    P->>B: Message + trace headers
    B-->>C: Message + trace headers
    C->>C: Extract context
    C->>C: Tạo consumer/process span
~~~

Không đưa token, mật khẩu hoặc dữ liệu nhạy cảm vào tracing baggage/message headers. Trace context là thông tin liên kết vận hành; nó không phải dữ liệu xác thực người dùng.

## 11. Security context và tenant context cần chính sách riêng

### Security context

Một listener sau commit thường chạy trong transaction mới và có thể được thiết kế để chạy dưới **service identity** của ứng dụng. Không nên mặc định truyền toàn bộ `SecurityContext` từ request người dùng sang listener.

Nếu một nghiệp vụ thật sự cần danh tính người khởi tạo để audit, hãy đưa thông tin actor tối thiểu và đáng tin cậy vào event theo chính sách bảo mật. Nếu listener cần thực hiện authorization, thực hiện kiểm tra theo quyền của consumer/service và dữ liệu nghiệp vụ. Spring Security có cơ chế executor riêng như `DelegatingSecurityContextAsyncTaskExecutor` cho trường hợp chủ đích truyền security context; đây là quyết định khác với propagation của Micrometer observation.

### Tenant context

Nếu ứng dụng dùng ThreadLocal để lưu tenant hiện tại, listener chạy thread khác có thể không đọc được. Có hai lựa chọn thường rõ ràng hơn:

- Đưa `tenantId` đã được xác thực vào event payload khi consumer cần nó.
- Đăng ký một accessor và propagation cho tenant context nếu thật sự cần giữ context trong cùng JVM; vẫn phải xác minh giá trị được capture từ nguồn tin cậy.

Không lấy `X-Tenant-Id` do client gửi làm giá trị đáng tin cậy chỉ vì decorator truyền nó sang listener thành công.

### Transaction context

Với `@ApplicationModuleListener`, transaction của listener có ranh giới riêng (mặc định `REQUIRES_NEW`). **Không propagate transaction của request** để biến listener async thành một phần của transaction đã commit. Nếu listener thất bại, xử lý retry/compensation và idempotency theo thiết kế nghiệp vụ.

## 12. Event Publication Registry không phải context propagation

Hai tính năng giải quyết hai vấn đề khác nhau:

| Cơ chế | Câu hỏi trả lời |
| --- | --- |
| **Event Publication Registry** | Publication nào đang chờ, hoàn tất hoặc cần xử lý lại sau lỗi? |
| **Context propagation** | Observation/tracing/logging context nào được khôi phục khi task chạy ở thread khác? |
| **Event payload metadata** | Consumer cần dữ liệu nghiệp vụ/correlation nào để xử lý độc lập? |
| **Idempotency** | Nếu cùng event được giao lại, làm sao tránh áp dụng thay đổi nghiệp vụ nhiều lần? |

Spring Modulith khuyến nghị dùng Event Publication Registry để bảo vệ việc giao event cho transactional listeners trước lỗi ứng dụng/listener. Tuy nhiên, registry không tự giữ mọi ThreadLocal trong request. Khi publication được phục hồi sau khi ứng dụng restart, không thể giả định thread-local trace context ban đầu còn tồn tại. Có thể tạo trace mới cho lần xử lý lại và dùng event/correlation ID để liên hệ với nghiệp vụ gốc.

~~~mermaid
flowchart TB
    Publish["Publish OrderPlaced"] --> Registry["Event Publication Registry"]
    Registry --> Delivery["Deliver to listener"]
    Delivery --> Context["Context propagation (nếu cùng executor/JVM)"]
    Delivery --> Business["Business processing / transaction"]
    Business --> Success["Mark publication complete"]
    Business --> Failure["Failure / retry / recovery"]
    Failure --> Delivery
~~~

**Retry không đồng nghĩa exactly-once.** Consumer cần chịu được việc nhận cùng event nhiều lần. Context propagation không thay thế deduplication hoặc tính idempotent của nghiệp vụ.

## 13. Kiểm tra propagation sau khi ứng dụng khởi động

Một lần startup thành công chưa chứng minh context được truyền. Hãy kiểm tra theo đường đi thực tế.

### Bước 1 — Xác nhận listener thực sự async

Đảm bảo method được gắn `@ApplicationModuleListener` và event được publish trong transaction mà listener quan sát được. Theo dõi thread name ở publisher và listener:

~~~java
log.info("Publishing eventId={} thread={}",
        event.eventId(), Thread.currentThread().getName());
~~~

Trong listener:

~~~java
log.info("Handling eventId={} thread={}",
        event.eventId(), Thread.currentThread().getName());
~~~

Thread name khác nhau là bằng chứng hữu ích cho việc đổi thread, nhưng **chưa nói gì về trace context**.

### Bước 2 — Xác nhận executor có decorator

Nếu dùng Boot auto-configured executor, kiểm tra property `spring.task.execution.propagate-context=true` có được version hiện tại hỗ trợ và executor thực sự dùng property đó không. Nếu dùng custom executor, kiểm tra bean `TaskExecutor` đang chọn có `ContextPropagatingTaskDecorator`.

### Bước 3 — Tạo một trace kiểm soát

Gọi endpoint tạo đơn và phát `OrderPlaced`. Tìm trace ở backend:

~~~text
HTTP POST /orders
  traceId = A
  spanId  = H

inventory listener
  traceId = A  (kỳ vọng khi context được capture/restore)
  spanId  = I
~~~

Kết quả có thể khác nếu trace không được sample, điểm listener không instrument, context capture diễn ra khi scope đã đóng hoặc executor khác được sử dụng. Nếu listener được retry sau restart, trace ID mới cũng có thể là hợp lý.

### Bước 4 — Kiểm tra logs và cleanup

Đảm bảo log listener có các trường trace/correlation cần thiết và không có context của task trước. Với pool tái sử dụng thread, sau task:

- Thread không giữ trace ID/tenant ID cũ.
- Task tiếp theo không nhìn thấy MDC hoặc tenant context của task trước.
- Khi task không có context nguồn, listener vẫn chạy theo chính sách mặc định, không đọc dữ liệu stale.

### Bước 5 — Đối chiếu kết quả nghiệp vụ

Kiểm tra trạng thái giữ hàng, publication state (nếu có registry), số lượt retry và idempotency. Một trace ID giống nhau chỉ chứng minh được **mối liên hệ telemetry**; nó không chứng minh event đã xử lý đúng.

## 14. Kịch bản lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| HTTP span có, listener span không cùng trace | Executor không propagation hoặc listener chạy sau khi context gốc không còn được capture | Xem executor thực, decorator/property, thời điểm submit và trace backend |
| Listener log không có `traceId` | MDC/observation accessor chưa được đăng ký hoặc executor không restore context | Kiểm tra Micrometer Context Propagation và logging integration |
| Bean decorator có nhưng không hiệu lực | Listener dùng executor khác | Xác định executor được Spring `@Async` chọn |
| Custom ThreadLocal không sang worker | Chưa có `ThreadLocalAccessor` tương ứng | Đăng ký accessor, test capture/restore/cleanup |
| Tenant của task trước xuất hiện ở task sau | Context không được dọn hoặc custom accessor không hỗ trợ clear/restore đúng | Kiểm tra cleanup và chạy test với thread pool tái sử dụng |
| Listener có trace mới thay vì trace gốc | Không có propagation hoặc consumer là một process/message boundary mới | Kiểm tra headers, instrumentation producer/consumer và lifecycle |
| Event được retry nhưng trace không còn nối request ban đầu | Publication được phục hồi sau restart, context ban đầu không còn | Dùng correlation/event ID và trace mới cho lần xử lý lại |
| HTTP trả thành công nhưng listener lỗi | Listener chạy sau commit và bất đồng bộ | Xem listener logs/metrics, publication registry và dữ liệu nghiệp vụ |
| Bật decorator làm tăng latency tác vụ nhỏ | Chi phí capture/restore context | Benchmark; chỉ truyền context cần thiết |
| Tenant ID có trong event nhưng consumer truy cập dữ liệu tenant sai | Metadata không đáng tin cậy hoặc authorization không được kiểm tra lại | Xác minh nguồn tenant phía server và policy ở consumer |

## 15. Thực hành: nối trace của request với application event

Thực hiện trên ứng dụng Spring Boot có hai module `order` và `inventory`. Bật Actuator, tracing bridge/exporter và một backend trace trong môi trường local/test.

1. **Tạo baseline:** chạy request `POST /orders` với `@ApplicationModuleListener`; tìm HTTP span và listener span. Ghi trace ID, span ID, thread name và thời điểm.
2. **Tắt propagation có kiểm soát:** dùng executor thử nghiệm không có decorator (hoặc property false nếu dùng auto-configured executor); gửi lại request và so trace/log.
3. **Bật propagation:** bật property cho executor auto-configured hoặc gắn `ContextPropagatingTaskDecorator` vào custom executor thực sự dùng.
4. **Kiểm tra lại:** listener có trace ID tương quan với request không? Có span riêng cho listener không? Parent/child relationship có phù hợp với thời điểm xử lý?
5. **Kiểm tra MDC:** log listener có trace ID/span ID hay không; chạy thêm task không có context để kiểm tra cleanup.
6. **Thêm business context:** đưa event ID, tenant ID đã xác thực và correlation ID vào payload; xác nhận listener xử lý được ngay cả khi không có HTTP request context.
7. **Tạo lỗi consumer:** làm listener thất bại trong môi trường test; kiểm tra publication registry/retry, log và trạng thái nghiệp vụ. Phân biệt một event được publish với một lượt consumer đã xử lý.
8. **Thử replay:** phục hồi hoặc phát lại một publication trong môi trường test; xác nhận hệ thống dùng correlation ID để truy vết và idempotency để tránh xử lý trùng, không phụ thuộc ThreadLocal gốc.

Mẫu ghi kết quả:

| Trạng thái | HTTP trace ID | Listener trace ID | Executor có decorator? | Business result |
| --- | --- | --- | --- | --- |
| Không propagation | … | … | Không | … |
| Có propagation | … | … | Có | … |
| Listener retry sau restart | … | … | Theo cấu hình | … |

Không đánh dấu PASS chỉ vì hai log có cùng chuỗi ID: cần xác nhận ID đó là trace ID do tracing integration tạo, span listener được ghi nhận và kết quả nghiệp vụ đúng.

## 16. Checklist triển khai

- [ ] Listener được khai báo đúng bằng `@ApplicationModuleListener` và hiểu rõ thời điểm sau commit/transaction riêng.
- [ ] Xác định executor thực tế dùng cho listener bất đồng bộ.
- [ ] Nếu dùng executor Boot auto-configured, kiểm tra property propagation đúng phiên bản.
- [ ] Nếu dùng executor tùy chỉnh, gắn `ContextPropagatingTaskDecorator` vào chính executor đó.
- [ ] Có Micrometer Context Propagation và các accessor cần thiết trên classpath.
- [ ] Không giả định mọi ThreadLocal tùy biến tự động được truyền.
- [ ] Event payload mang business metadata cần thiết, được tạo từ nguồn tin cậy.
- [ ] Security/tenant authorization có chính sách riêng; không coi trace context là quyền truy cập.
- [ ] Không truyền transaction gốc qua ranh giới async; listener dùng transaction theo thiết kế.
- [ ] Event Publication Registry, retry và idempotency được thiết kế độc lập với tracing.
- [ ] Kiểm tra trace ID, span, MDC và cleanup sau task trong môi trường thử nghiệm.
- [ ] Đánh giá overhead khi propagation cho lượng lớn tác vụ rất nhỏ.

## 17. Câu hỏi tự kiểm tra

1. Vì sao một `ThreadLocal` trong HTTP thread không tự xuất hiện ở worker thread?
2. `@ApplicationModuleListener` khác `@EventListener` đồng bộ ở những điểm nào?
3. `ContextPropagatingTaskDecorator` thực hiện capture/restore/cleanup ra sao?
4. Vì sao có decorator bean nhưng listener vẫn mất context?
5. `spring.task.execution.propagate-context=true` áp dụng cho loại executor nào?
6. Context propagation có chuyển transaction của request sang listener không?
7. Tại sao tenant ID cần nằm trong event payload hoặc nguồn dữ liệu đáng tin cậy thay vì chỉ nằm trong request ThreadLocal?
8. Khi listener chạy sau commit và HTTP span đã kết thúc, trace vẫn có thể liên hệ listener với request bằng cách nào?
9. Điều gì cần làm khác khi event đi qua Kafka/RabbitMQ thay vì executor trong cùng JVM?
10. Tại sao Event Publication Registry, context propagation và idempotency giải quyết ba vấn đề khác nhau?
11. Khi publication được retry sau khi ứng dụng restart, có nên kỳ vọng ThreadLocal trace context gốc còn không?
12. Nếu log listener không có trace ID, những chặng nào cần kiểm tra trước khi kết luận listener không chạy?

## 18. Tổng kết

Khi application event được xử lý bất đồng bộ, listener của Spring Modulith có thể chạy sau commit và trên một thread khác. **Context propagation** giúp chuyển những ngữ cảnh quan sát đã đăng ký — như observation, tracing và logging context — sang executor để các tín hiệu của listener có thể được liên kết với luồng phát sự kiện. Với Spring Boot auto-configured executor, có thể dùng `spring.task.execution.propagate-context` ở phiên bản hỗ trợ; với executor tùy chỉnh, cần gắn `ContextPropagatingTaskDecorator` vào đúng pool đang chạy listener.

Context propagation không thay thế event payload, authorization, transaction, Event Publication Registry hay idempotency. Tenant/business metadata cần có nguồn tin cậy và được truyền minh bạch; transaction của listener có ranh giới riêng; message broker cần cơ chế inject/extract trace headers thay vì dùng TaskDecorator. Kiểm tra thread, trace ID, span, MDC, cleanup và trạng thái nghiệp vụ sẽ cho biết **ngữ cảnh nào đã được truyền**, **đường đi nào đã được quan sát** và **consumer có thực sự xử lý thành công hay không**.

## Tài liệu tham khảo

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html).
- [Spring Modulith — ApplicationModuleListener API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/ApplicationModuleListener.html).
- [Spring Boot — Observability and Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
- [Spring Framework — ContextPropagatingTaskDecorator API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html).
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/).
