# Truyền observation qua thread

> **Chương:** Context propagation  
> **Bối cảnh:** Spring Modulith Documentation & Observability — giữ liên hệ giữa observation, module entry span và log context khi request chuyển việc sang executor hoặc tác vụ bất đồng bộ trong ứng dụng Spring Boot.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao observation hiện hành thường được truy cập qua `ThreadLocal` và vì sao nó không tự đi theo tác vụ sang thread khác.
2. Phân biệt truyền context với truyền tham số nghiệp vụ, sao chép object và distributed tracing qua mạng.
3. Mô tả vai trò của `ThreadLocalAccessor`, `ContextRegistry`, `ContextSnapshot` và `ContextSnapshotFactory` trong Micrometer Context Propagation.
4. Cấu hình `ContextPropagatingTaskDecorator` trên `ThreadPoolTaskExecutor` và dùng đúng executor cho `@Async`/`CompletableFuture`.
5. Chủ động capture và restore context khi phải dùng `Executor` thuần Java.
6. Kiểm tra observation hiện hành trong worker thread và chẩn đoán trường hợp trace bị đứt hoặc context bị rò giữa các tác vụ.
7. Phân biệt ranh giới thread imperative với Reactor Context và message/network boundary.

## 2. Vì sao observation bị mất khi đổi thread?

Trong ứng dụng Spring Boot, request thường bắt đầu trên thread xử lý HTTP. Spring MVC, Micrometer Tracing và logging integration có thể gắn observation/span hiện hành với thread thông qua scope dựa trên `ThreadLocal`.

Khi mã chạy đồng bộ, lời gọi sang module khác vẫn ở trong cùng thread:

~~~text
HTTP request thread
  └── orders.placeOrder()
        └── payments.authorize()
~~~

Observation hiện hành có thể được các interceptor và instrumentation đọc trực tiếp. Nhưng khi gửi công việc sang executor:

~~~text
HTTP request thread                    Worker thread
  orders.placeOrder()                     |
       |                                  |
       +---- executor.execute(task) ----> |
                                          +-- payments.authorize()
~~~

Worker thread có vùng `ThreadLocal` riêng. Java không tự sao chép các giá trị đang gắn với thread gửi sang thread nhận. Vì vậy, nếu chỉ gọi:

~~~java
executor.execute(() -> paymentApi.authorize(orderId));
~~~

thì code nghiệp vụ có thể chạy bình thường, nhưng observation hiện hành, trace context hoặc MDC có thể không còn trong worker. Hậu quả thường thấy:

- Module entry span của worker không có quan hệ parent/child mong đợi.
- Trace bị chia thành hai cây hoặc worker không tạo được span liên kết.
- Log của worker thiếu `traceId`/`spanId` dù log của request có đầy đủ.
- Metadata như tenant hoặc correlation context biến mất.

Đây là vấn đề **context propagation**. Nó không nhất thiết làm hỏng logic nghiệp vụ; nó làm giảm khả năng quan sát và tương quan các bước xử lý.

## 3. Observation scope và ThreadLocal

Micrometer Observation có vòng đời gồm tạo observation, bắt đầu, mở scope, chạy code, đóng scope và dừng observation. Khi mở scope, observation hiện hành được đặt vào context cục bộ của thread để instrumentation bên trong có thể truy cập:

~~~java
Observation observation =
    Observation.start("orders.place", observationRegistry);

try (Observation.Scope scope = observation.openScope()) {
    // Trong đoạn này, observation là current observation
    orderService.placeOrder(orderId);
}
finally {
    observation.stop();
}
~~~

Trong ứng dụng thông thường, có thể dùng `observation.observe(...)` để quản lý vòng đời gọn hơn. Ví dụ trên giúp thấy rõ **scope chỉ tồn tại trên thread đang mở nó**.

Mỗi thread có giá trị ThreadLocal riêng; thread pool còn tái sử dụng worker cho nhiều tác vụ khác nhau. Nếu một tác vụ đặt giá trị vào `ThreadLocal` rồi không dọn, tác vụ sau có thể nhìn thấy dữ liệu cũ.

~~~mermaid
flowchart TB
    A["Request thread<br/>ThreadLocal = Observation A"] --> B["Submit task"]
    B --> C["Worker thread<br/>ThreadLocal riêng"]
    C --> D{"Có propagation?"}
    D -->|"Không"| E["Current observation không có<br/>hoặc không đúng"]
    D -->|"Có"| F["Restore snapshot vào worker"]
    F --> G["Tạo span con / log có trace context"]
    G --> H["Đóng scope và khôi phục trạng thái cũ"]
~~~

**Điểm cần nhớ:** mở scope trong request thread không làm cho mọi thread khác tự thấy observation đó. Cần một cơ chế capture và restore ở ranh giới giao việc.

## 4. Micrometer Context Propagation gồm những gì?

Thư viện `io.micrometer:context-propagation` cung cấp lớp trung gian giữa các kiểu context khác nhau:

| Thành phần | Vai trò | Câu hỏi nó trả lời |
| --- | --- | --- |
| `ThreadLocalAccessor<T>` | Đọc, đặt và xóa một giá trị ThreadLocal cụ thể | Làm thế nào lấy/khôi phục giá trị này? |
| `ContextAccessor` | Đọc/ghi context dạng map hoặc cấu trúc tương đương | Làm thế nào tương tác với context không phải ThreadLocal? |
| `ContextRegistry` | Đăng ký các accessor để thư viện biết những loại context nào có thể truyền | Có những giá trị nào được phép capture? |
| `ContextSnapshot` | Giữ ảnh chụp các giá trị đã capture và cung cấp thao tác restore/wrap | Cần mang những giá trị nào sang nơi thực thi? |
| `ContextSnapshotFactory` | Tạo snapshot theo registry và quy tắc capture | Capture các context theo cấu hình nào? |

Một snapshot chỉ capture những giá trị mà **accessor tương ứng đã đăng ký** có thể đọc. Nó không quét và sao chép toàn bộ ThreadLocal của JVM.

Ví dụ một ứng dụng có:

- Observation/tracing context được thư viện Micrometer tích hợp.
- MDC/logging context được logging bridge hỗ trợ.
- Tenant context do ứng dụng tự tạo.

Muốn truyền tenant context tự tạo, ứng dụng phải cung cấp `ThreadLocalAccessor` tương ứng. Nếu không có accessor, `ContextSnapshot` không biết cách đọc và khôi phục giá trị đó.

## 5. Vòng đời capture → submit → restore → cleanup

Quy trình truyền context qua executor gồm bốn bước:

1. **Capture:** lấy các giá trị context hiện hành ở thread gửi, khi observation vẫn đang trong scope.
2. **Submit:** gửi task đã được bọc hoặc gửi task qua executor có decorator.
3. **Restore:** trước khi chạy task, đặt các giá trị đã capture vào context cục bộ của worker.
4. **Cleanup:** khi task hoàn tất, đóng scope để khôi phục hoặc xóa các giá trị vừa đặt, tránh ảnh hưởng task tiếp theo.

~~~mermaid
sequenceDiagram
    participant Request as Request thread
    participant Snapshot as ContextSnapshot
    participant Executor as TaskExecutor
    participant Worker as Worker thread
    Request->>Snapshot: captureAll() trong observation scope
    Request->>Executor: submit task đã wrap
    Executor->>Worker: chạy decorated Runnable
    Worker->>Snapshot: setThreadLocals()
    Note over Worker: Current observation/trace context được khôi phục
    Worker->>Worker: Chạy business code
    Worker->>Snapshot: close Scope
    Note over Worker: Restore trạng thái ThreadLocal trước task
~~~

Thời điểm capture quan trọng. Nếu capture sau khi request scope đã đóng, snapshot có thể không còn observation cần truyền. Vì vậy capture phải diễn ra **ở phía gửi và trước khi submit**.

## 6. Cách đơn giản với Spring: ContextPropagatingTaskDecorator

Spring Framework cung cấp `ContextPropagatingTaskDecorator` từ **Spring Framework 6.1**. Decorator này bọc task và sử dụng Micrometer Context Propagation để khôi phục các giá trị context đã đăng ký khi task chạy trên thread khác.

Với executor do ứng dụng tự cấu hình, gắn decorator trực tiếp:

~~~java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class AsyncConfiguration {

    @Bean("contextAwareExecutor")
    ThreadPoolTaskExecutor contextAwareExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("context-aware-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Ở đây:

- `ThreadPoolTaskExecutor` là executor do Spring quản lý vòng đời.
- `setTaskDecorator(...)` áp dụng wrapper cho task được gửi qua **executor này**.
- `ContextPropagatingTaskDecorator` dùng factory mặc định để capture/restore context đã đăng ký.
- `threadNamePrefix` chỉ giúp đọc log và chẩn đoán; tên thread không tự truyền observation.

Decorator có overhead vì phải capture và restore context. Với các tác vụ cực nhỏ, số lượng rất lớn, hãy đo hiệu năng thực tế trước khi áp dụng đại trà.

### 6.1. Dùng executor đã cấu hình với `@Async`

Kích hoạt async support và chỉ định đúng executor:

~~~java
package com.example.shop.payments;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class PaymentWorker {

    @Async("contextAwareExecutor")
    public CompletableFuture<String> authorize(String orderId) {
        // Được thực thi trên executor có ContextPropagatingTaskDecorator.
        // Module instrumentation và tracing có thể đọc context đã restore.
        String result = "AUTHORIZED:" + orderId;
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Lớp cấu hình cần bật `@EnableAsync`:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncMethodConfiguration {
}
~~~

Lời gọi `@Async` phải đi qua Spring proxy, ví dụ từ một bean khác. Tự gọi `this.authorize(...)` bên trong cùng bean thường bỏ qua async interceptor, vì vậy task không đi qua executor như mong đợi.

### 6.2. Với AsyncTaskExecutor do Spring Boot tự cấu hình

Ở những phiên bản Spring Boot có thuộc tính `spring.task.execution.propagate-context` (được tài liệu Spring Boot 4.x công bố), có thể bật propagation cho **auto-configured AsyncTaskExecutor**:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Thuộc tính này có giá trị mặc định `false`. Nó áp dụng cho executor do Boot tự cấu hình; không nên giả định một executor tùy chỉnh hoặc một `ExecutorService` do thư viện khác tạo cũng tự được bọc.

Với các dòng Spring Boot 3.x, kiểm tra đúng reference guide của phiên bản. Cách tường minh cho executor tự tạo là gắn `ContextPropagatingTaskDecorator` trực tiếp như ví dụ ở phần 6. Không copy thuộc tính Boot 4.x vào ứng dụng 3.x nếu metadata cấu hình của phiên bản đó không hỗ trợ.

## 7. Truyền context với Executor thuần Java

Không phải mọi executor đều là `ThreadPoolTaskExecutor`. Khi phải dùng `java.util.concurrent.Executor` hoặc thư viện tạo pool riêng, có thể chủ động sử dụng `ContextSnapshotFactory` và `ContextSnapshot`.

Đầu tiên, tạo factory:

~~~java
import io.micrometer.context.ContextSnapshotFactory;

ContextSnapshotFactory snapshotFactory =
    ContextSnapshotFactory.builder().build();
~~~

Ở phía gửi, capture snapshot khi observation đang hiện hành:

~~~java
import io.micrometer.context.ContextSnapshot;
import java.util.concurrent.Executor;

void submitPayment(Executor executor, String orderId) {
    ContextSnapshot snapshot = snapshotFactory.captureAll();

    executor.execute(snapshot.wrap(() -> {
        paymentApi.authorize(orderId);
    }));
}
~~~

`snapshot.wrap(Runnable)` trả về một `Runnable` đã được bọc: khi chạy, snapshot đặt các ThreadLocal values lên worker, gọi task và tự đóng scope sau khi task kết thúc. Có thể dùng trực tiếp:

~~~java
executor.execute(snapshot.wrap(() -> performBackgroundWork()));
~~~

Hoặc với `Callable`:

~~~java
Future<String> result = executorService.submit(
    snapshot.wrap(() -> calculateResult())
);
~~~

**Không tạo snapshot một lần khi ứng dụng khởi động rồi dùng lại cho mọi request.** Snapshot cần được capture riêng tại thời điểm submit của mỗi tác vụ, nếu không có thể truyền nhầm context của request trước.

### 7.1. Dùng `wrapExecutor(...)`

Micrometer còn cho phép tạo executor wrapper:

~~~java
ContextSnapshot snapshot = snapshotFactory.captureAll();
Executor contextAware = snapshot.wrapExecutor(delegateExecutor);

contextAware.execute(() -> paymentApi.authorize(orderId));
~~~

Trong ví dụ, wrapper mang **snapshot vừa capture** cho các task được gửi qua nó. Nếu context thay đổi giữa các request, hãy tạo wrapper/snapshot tại đúng ranh giới của từng request hoặc dùng task decorator capture theo từng lần submit. Không giữ wrapper chứa snapshot của request A rồi tái sử dụng cho request B.

## 8. Khi ứng dụng tự tạo ThreadLocal

Các context do thư viện hỗ trợ có thể đã được đăng ký accessor. Với ThreadLocal tự tạo, cần định nghĩa cách đọc/ghi/xóa.

Ví dụ một tenant context đơn giản:

~~~java
package com.example.shop.context;

public final class TenantContext {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private TenantContext() {
    }

    public static String get() {
        return CURRENT.get();
    }

    public static void set(String tenantId) {
        CURRENT.set(tenantId);
    }

    public static void clear() {
        CURRENT.remove();
    }
}
~~~

Accessor tương ứng:

~~~java
package com.example.shop.context;

import io.micrometer.context.ThreadLocalAccessor;

public final class TenantThreadLocalAccessor
        implements ThreadLocalAccessor<String> {

    public static final String KEY = "shop.tenant";

    @Override
    public Object key() {
        return KEY;
    }

    @Override
    public String getValue() {
        return TenantContext.get();
    }

    @Override
    public void setValue(String value) {
        TenantContext.set(value);
    }

    @Override
    public void setValue() {
        TenantContext.clear();
    }
}
~~~

Đăng ký accessor một lần trong quá trình khởi động:

~~~java
import io.micrometer.context.ContextRegistry;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class TenantContextPropagationConfiguration {

    TenantContextPropagationConfiguration() {
        ContextRegistry.getInstance()
            .registerThreadLocalAccessor(new TenantThreadLocalAccessor());
    }
}
~~~

Khi accessor đã được đăng ký, `ContextSnapshotFactory.captureAll()` có thể capture giá trị `shop.tenant` cùng các context khác có accessor. Phương thức `setValue()` không tham số phải xóa giá trị, để khi scope đóng worker thread được trả về trạng thái sạch.

**Lưu ý:** registry toàn cục tồn tại lâu hơn một số test/application context trong cùng JVM. Trong môi trường test, tránh đăng ký lặp nhiều accessor cùng key; cần có chiến lược dọn hoặc dùng registry riêng nếu test cô lập yêu cầu điều đó.

## 9. Ví dụ xuyên suốt: orders giao việc cho payments

Giả sử module `orders` xử lý request và gửi bước thanh toán sang executor:

~~~java
package com.example.shop.orders;

import com.example.shop.payments.PaymentWorker;
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final PaymentWorker paymentWorker;

    public OrderService(PaymentWorker paymentWorker) {
        this.paymentWorker = paymentWorker;
    }

    public CompletableFuture<String> placeOrder(String orderId) {
        // Thực hiện validation và lưu đơn theo transaction phù hợp.
        return paymentWorker.authorize(orderId);
    }
}
~~~

Luồng xử lý mong đợi:

~~~mermaid
sequenceDiagram
    participant HTTP as HTTP request thread
    participant Orders as orders module
    participant Executor as contextAwareExecutor
    participant Payments as payments worker
    HTTP->>Orders: placeOrder(orderId)
    Note over HTTP,Orders: Current observation / trace context
    Orders->>Executor: @Async authorize(orderId)
    Note over Executor: Capture context khi submit
    Executor->>Payments: Restore context, run task
    Note over Payments: payments module entry span có parent context
    Payments-->>HTTP: CompletableFuture completion
~~~

Nếu `PaymentWorker` là Spring bean, method `@Async` được gọi qua proxy và executor đã gắn decorator, observation/tracing context có thể được khôi phục trên worker. Khi module `payments` có instrumentation phù hợp, module entry span có thể nối vào trace đang hoạt động.

**Đừng hiểu propagation là kéo dài vòng đời request.** Worker có thể bắt đầu sau khi HTTP response đã được gửi hoặc parent span đã kết thúc. Với công việc nền kéo dài, retry hoặc được lưu bền vững, hãy cân nhắc tạo trace mới có correlation/link thay vì ép một tác vụ độc lập sống trong scope request cũ.

## 10. CompletableFuture và nhiều executor

`CompletableFuture.supplyAsync(...)` không truyền executor sẽ dùng common pool mặc định. Common pool không tự sử dụng decorator bạn cấu hình trên `contextAwareExecutor`.

Hãy chỉ định executor có propagation:

~~~java
CompletableFuture
    .supplyAsync(() -> loadOrder(orderId), contextAwareExecutor)
    .thenApplyAsync(this::calculateTotal, contextAwareExecutor)
    .thenAcceptAsync(this::saveResult, contextAwareExecutor);
~~~

Những stage có hậu tố `Async` cần được kiểm tra executor thực tế. Nếu một stage quay về common pool hoặc pool khác không được bọc, context có thể mất ở đúng ranh giới đó.

Một stage không có hậu tố `Async` có thể chạy trên thread hoàn thành stage trước hoặc thread gắn callback; đừng dựa vào một thread cụ thể để giữ ThreadLocal. Nếu logic cần một context nhất quán ở mỗi chặng, hãy dùng executor có decorator cho các stage bất đồng bộ và kiểm tra trace thực tế.

### 10.1. Đừng dùng chung executor cho mọi mục đích một cách vô thức

Trong ứng dụng lớn, có thể có:

- Executor xử lý HTTP async.
- Executor cho `@Async` nghiệp vụ.
- Executor của event multicaster.
- Executor cho lịch chạy định kỳ.
- Executor riêng do client hoặc thư viện tạo.

Decorator chỉ áp dụng lên **executor được gắn nó**. Hãy ghi rõ executor nào chịu trách nhiệm cho task nào, tránh nghĩ rằng một bean decorator tự động bọc mọi thread trong JVM.

## 11. Event listener bất đồng bộ và Spring Modulith

Spring Modulith có thể công bố event giữa các application module. Listener có thể được chạy bất đồng bộ hoặc sau khi transaction commit. Nếu event listener sử dụng executor riêng, cần xem xét propagation trên **executor thực tế của listener**.

Với một `@EventListener` dùng `@Async`:

~~~java
@Component
class NotificationListener {

    @Async("contextAwareExecutor")
    @EventListener
    void on(OrderPlaced event) {
        notificationService.send(event.orderId());
    }
}
~~~

Điều kiện để context propagation hoạt động:

1. Async support được bật và lời gọi listener được xử lý bởi executor có decorator.
2. Observation/trace context còn có thể capture tại thời điểm task được submit.
3. Các context cần truyền có accessor phù hợp.
4. Cách xử lý event, transaction và thời điểm listener được gọi phù hợp với mục tiêu tương quan trace.

**Event Publication Registry không phải context snapshot.** Registry theo dõi publication và trạng thái listener; snapshot giữ context trong bộ nhớ để chuyển qua ranh giới thực thi. Nếu publication được retry sau restart hoặc xử lý bởi instance khác, snapshot trong JVM ban đầu không thể tự tồn tại qua lần khởi động hay qua mạng.

Đối với event bền vững hoặc message broker, cần truyền trace context qua metadata/headers theo giao thức (chẳng hạn W3C Trace Context), sau đó trích xuất ở consumer. Với tác vụ được phát lại sau thời gian dài, một trace mới có correlation hoặc span link thường mô tả quan hệ nhân quả rõ hơn.

## 12. Phân biệt executor thread với Reactor pipeline

Reactor có mô hình context khác. `Reactor Context` gắn với subscription/subscriber, không gắn cố định vào một thread. Các operator như `publishOn` hoặc `subscribeOn` có thể đổi thread mà Reactor Context vẫn đi theo subscription.

Spring Boot cho phép chọn chế độ truyền ThreadLocal vào Reactor operator qua:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Các chế độ thường gặp:

| Chế độ | Hành vi |
| --- | --- |
| `limited` (mặc định của Reactor trong nhiều cấu hình hiện hành) | Khôi phục ThreadLocal tại một số operator hỗ trợ như `handle` và `tap`, khi context đã được capture |
| `auto` | Khôi phục ThreadLocal từ Reactor Context xuyên các operator và ranh giới thread của reactive chain |

Với chế độ mặc định, `contextCapture()` có thể capture ThreadLocal đã đăng ký accessor vào Reactor Context tại subscription. Khi cần đọc metadata nghiệp vụ trong pipeline, ưu tiên đọc từ Reactor Context qua `deferContextual(...)` thay vì giả định ThreadLocal luôn có giá trị.

Reactor automatic mode chỉ áp dụng cho **subscription được tạo sau khi bật chế độ**. Nó cũng có chi phí restore/cleanup; cần đo hiệu năng với workload thật. Cấu hình Reactor không thay thế `ContextPropagatingTaskDecorator` cho một executor imperative độc lập.

## 13. Điều context propagation không làm

| Nhầm lẫn | Thực tế |
| --- | --- |
| “Copy toàn bộ ThreadLocal của thread gửi” | Chỉ các giá trị có accessor được đăng ký mới được capture |
| “Deep copy mọi object trong context” | Snapshot không phải cơ chế serialize/clone object nghiệp vụ |
| “Truyền được orderId thì không cần method parameter” | Dữ liệu nghiệp vụ vẫn phải truyền qua tham số/event payload/hợp đồng phù hợp |
| “Decorator của một executor áp dụng cho tất cả executor” | Chỉ task đi qua executor được gắn decorator mới được bọc |
| “Context snapshot đi qua Kafka/HTTP hoặc restart” | Snapshot là dữ liệu trong bộ nhớ; cross-process cần headers/metadata và propagation theo giao thức |
| “Mọi async job phải là child span của HTTP request” | Background work có thể cần trace mới, correlation hoặc span link |
| “Có cùng traceId là chắc chắn có quan hệ cha–con trực tiếp” | Cần xem span parent/link và thời gian thực thi |
| “ThreadLocal có giá trị trên worker là an toàn” | Phải khôi phục/dọn context đúng cách để tránh rò dữ liệu giữa task |

### 13.1. Snapshot không thay thế dữ liệu nghiệp vụ

Không dùng Observation, MDC hoặc custom ThreadLocal làm nguồn duy nhất cho `orderId`, `tenantId` hoặc quyền truy cập nghiệp vụ. Những giá trị cần thiết để xử lý đúng phải được truyền tường minh qua tham số, command, event payload hoặc cơ chế lưu trữ có hợp đồng rõ ràng.

Context propagation là phương tiện giữ **ngữ cảnh thực thi/quan sát**; không phải kho dữ liệu hoặc cơ chế phân quyền.

### 13.2. Tránh rò context giữa các request

Thread pool tái sử dụng worker. Nếu một task đặt giá trị ThreadLocal và không xóa, task sau có thể nhìn thấy giá trị của task trước. `ContextSnapshot.setThreadLocals()` và `ContextPropagatingTaskDecorator` tạo scope có cleanup để khôi phục trạng thái trước đó.

Tránh mẫu thủ công:

~~~java
// Không nên: không bảo đảm dọn ThreadLocal khi task lỗi.
executor.execute(() -> {
    TENANT.set(tenantId);
    performWork();
});
~~~

Nếu bắt buộc quản lý ThreadLocal thủ công, phải dùng `try/finally` để restore/remove. Tuy nhiên, với context đã có accessor, nên dùng snapshot/decorator để tránh tự triển khai vòng đời này.

## 14. Kiểm tra propagation bằng test

Một integration test có thể xác minh observation hiện hành trong worker:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.Future;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootTest
class ContextPropagationIntegrationTest {

    @Autowired ObservationRegistry registry;
    @Autowired ThreadPoolTaskExecutor contextAwareExecutor;

    @Test
    void currentObservationIsRestoredOnWorkerThread() throws Exception {
        Observation parent = Observation.start("test.request", registry);

        try (Observation.Scope scope = parent.openScope()) {
            Future<Observation> current = contextAwareExecutor.submit(
                registry::getCurrentObservation
            );

            assertThat(current.get()).isSameAs(parent);
        }
        finally {
            parent.stop();
        }
    }
}
~~~

Test giả định `contextAwareExecutor` là đúng bean có `ContextPropagatingTaskDecorator`. Nó kiểm tra **observation context** trên worker; nó chưa chứng minh exporter đã gửi span đến backend.

Một bộ kiểm tra tốt hơn có thể bổ sung:

1. So sánh cùng một task khi executor không có decorator và khi có decorator.
2. Kiểm tra tenant ThreadLocal có accessor được restore và sau task quay về trạng thái cũ.
3. Tạo observation con trong worker và xác minh trace context/parent relationship bằng test tracer.
4. Chạy nhiều task liên tiếp trên cùng pool để phát hiện context bị rò từ request trước.
5. Với event listener bất đồng bộ, kiểm tra đúng executor và thời điểm submit; không chỉ kiểm tra listener được gọi.

**Lưu ý:** cấu hình auto-configuration trong test có thể khác production. Nếu test không có `MeterRegistry` hoặc tracer, cần bật test observability phù hợp với phiên bản Spring Boot; không lấy việc thiếu exporter trong test làm bằng chứng decorator không hoạt động.

## 15. Chẩn đoán khi observation bị mất

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Worker không thấy current observation | Executor chưa được decorate hoặc task đi qua pool khác | Xem bean/executor thực tế được dùng |
| Log request có traceId nhưng worker không có | MDC/tracing context không được capture/restore | Kiểm tra accessor, decorator và scope |
| `@Async` không chạy trên executor đã cấu hình | Sai qualifier, thiếu `@EnableAsync`, self-invocation bỏ qua proxy | Kiểm tra call path và bean name |
| `CompletableFuture` mất trace ở stage sau | Một stage dùng common pool hoặc executor khác | Truyền executor có propagation cho các stage async |
| ThreadLocal tự tạo không được truyền | Chưa đăng ký `ThreadLocalAccessor` hoặc key không khớp | Kiểm tra `ContextRegistry` và accessor |
| Task sau nhận tenant/trace của task trước | Custom ThreadLocal không cleanup, wrapper không đóng scope | Dùng snapshot scope, kiểm tra `setValue()` không tham số xóa đúng |
| Observation chỉ được capture rỗng | Capture sau khi parent scope đóng hoặc task được submit ngoài scope | Capture ngay trước submit khi context còn hiện hành |
| Có span nhưng không có parent mong đợi | Trace context không được propagate, hoặc tác vụ cần trace/link mới | Kiểm tra traceparent, executor, async lifecycle |
| Background job có span vượt quá thời gian request | Tác vụ chạy sau khi request kết thúc | Xem lại mô hình trace: parent context, new trace hoặc span link |
| Reactor operator không thấy ThreadLocal | Chế độ limited, thiếu contextCapture hoặc không phải operator hỗ trợ | Dùng Reactor Context; kiểm tra `spring.reactor.context-propagation` |
| Context có giá trị nhưng không có span trong backend | Sampling, exporter, collector hoặc tracing handler | Kiểm tra tracing pipeline độc lập |
| Tác vụ nhỏ bị chậm sau khi thêm decorator | Chi phí capture/restore so với thời gian thực thi quá lớn | Đo benchmark, cân nhắc batch hoặc truyền tham số tường minh |

Khi điều tra, đi theo chuỗi: **điểm capture → executor được submit → decorator/wrapper → accessor → scope restore → instrumentation/tracing backend**. Điều đó giúp tách lỗi propagation khỏi lỗi tạo observation hoặc xuất trace.

## 16. Bài thực hành: nối trace qua executor

**Bối cảnh:** ứng dụng Spring Boot có module `orders` và `payments`. HTTP request gọi `OrderService.placeOrder()`; service gửi tác vụ sang `PaymentWorker.authorize()` bằng `@Async`. Mục tiêu là xác minh module entry span của payments vẫn có trace context liên quan đến request.

Thực hiện:

1. Cấu hình Spring Modulith observability và tracing pipeline trong môi trường thử nghiệm.
2. Tạo `ThreadPoolTaskExecutor` có `ContextPropagatingTaskDecorator`, đặt tên bean `contextAwareExecutor`.
3. Dùng `@EnableAsync` và `@Async("contextAwareExecutor")` ở bean payments.
4. Gửi một request tạo đơn hàng, kiểm tra trace backend trước tiên với executor chưa decorate để có baseline.
5. Bật decorator, gửi lại request tương đương; tìm module entry span `payments` và kiểm tra `traceId`, parent relationship, thời gian và tên thread nếu có log.
6. Thêm một custom `ThreadLocalAccessor` cho tenant ID với hai giá trị `TENANT_A` và `TENANT_B`; gửi các tác vụ xen kẽ để kiểm tra không lẫn context.
7. Thử `CompletableFuture.supplyAsync(...)` không chỉ định executor và quan sát khác biệt; sau đó truyền executor đã decorate.
8. Tạo một event listener `@Async` dùng cùng executor và kiểm tra thời điểm listener được submit so với transaction/request.
9. Thử một job chạy sau request lâu hơn; giải thích khi nào nên dùng trace mới hoặc span link thay vì coi parent HTTP scope còn sống.

Mẫu bảng kết quả:

| Phép thử | Kết quả cần quan sát | Kết luận |
| --- | --- | --- |
| Executor không decorator | Worker có thể không thấy current observation | ThreadLocal không tự truyền |
| Executor có decorator | Worker thấy context đã capture | TaskDecorator phục hồi context |
| Hai tenant gửi xen kẽ | Mỗi task thấy tenant tương ứng, không lẫn | Accessor và cleanup đúng |
| CompletableFuture dùng common pool | Context có thể mất ở stage đó | Phải chỉ định executor phù hợp |
| Trace backend | Module span của payments có context liên quan khi propagation đúng | Có thể nối các module operation trong một trace |
| Durable/retried event | Không mặc định còn parent request scope | Cần trace metadata/link phù hợp |

**Tiêu chí hoàn thành:** giải thích được vì sao observation mất qua thread, cấu hình được decorator, kiểm tra được current observation trên worker, chứng minh cleanup bằng tác vụ liên tiếp và phân biệt thread propagation với distributed trace propagation.

## 17. Ghi nhớ

Để truyền observation qua thread, hãy nghĩ theo chu trình:

~~~text
Capture tại thread gửi
        ↓
Submit qua executor có decorator/wrapper
        ↓
Restore context trong worker
        ↓
Chạy operation và instrumentation
        ↓
Close scope, khôi phục trạng thái thread
~~~

Spring Framework cung cấp `ContextPropagatingTaskDecorator`; Micrometer Context Propagation cung cấp accessor, registry và snapshot; Spring Boot tích hợp chúng với observation, logging và tracing. Với Spring Modulith, cơ chế này giúp giữ liên hệ của module entry spans khi một lời gọi được chuyển sang executor. Với tác vụ đi qua message broker hoặc tiến trình khác, cần propagation theo giao thức và metadata riêng.

### Tài liệu tham khảo

- [Spring Boot — Observability: Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html) — thuộc tính propagation cho executor tự cấu hình và Reactor.
- [Spring Framework — ContextPropagatingTaskDecorator API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html) — decorator cho observation/logging context, có từ Spring Framework 6.1.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — TaskExecutor, TaskDecorator và `@Async`.
- [Micrometer Context Propagation — Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html) — ThreadLocalAccessor, ContextAccessor, ContextRegistry và ContextSnapshot.
- [Micrometer Context Propagation — Usage Examples](https://docs.micrometer.io/context-propagation/reference/usage.html) — capture/restore và scope cleanup.
- [Project Reactor — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html) — limited/automatic mode, `contextCapture` và khôi phục ThreadLocal.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — module entry spans và observability trong application modules.

> **Lưu ý phiên bản:** `ContextPropagatingTaskDecorator` yêu cầu Spring Framework 6.1 trở lên. Thuộc tính `spring.task.execution.propagate-context` được tài liệu Spring Boot 4.x công bố cho auto-configured AsyncTaskExecutor; các dòng Boot 3.x cần đối chiếu hướng dẫn phiên bản và cấu hình decorator phù hợp. Bài được soạn ở STEP 4; Content QA chuyên môn thuộc bước riêng.
