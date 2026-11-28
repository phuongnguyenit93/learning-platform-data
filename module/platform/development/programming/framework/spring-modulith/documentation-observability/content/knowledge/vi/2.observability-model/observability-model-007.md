# Context truyền qua thread, executor và reactive pipeline

> **Chương:** Mô hình quan sát  
> **Phạm vi:** Spring Modulith trong ứng dụng Spring Boot; giữ ngữ cảnh quan sát khi lời gọi đi qua thread, executor hoặc chuỗi Reactor.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **ngữ cảnh quan sát** (observation/tracing context), **ngữ cảnh ghi log** (MDC) và **ngữ cảnh nghiệp vụ** (ví dụ `orderId`).
2. Giải thích vì sao một lời gọi giữa các application module có thể xuất hiện trong cùng trace khi chạy đồng bộ, nhưng đứt mạch khi chuyển sang `@Async`, `Executor` hoặc `CompletableFuture`.
3. Dùng `ContextPropagatingTaskDecorator` hoặc Micrometer `ContextSnapshot` để chuyển ngữ cảnh an toàn sang thread khác.
4. Hiểu vai trò của Reactor `Context`, `contextWrite`, `contextCapture`, `publishOn`, `subscribeOn` và chế độ truyền context tự động.
5. Đọc dấu hiệu trên trace, log và Actuator để xác định việc truyền context có hoạt động, đồng thời nhận ra giới hạn khi sự kiện được xử lý sau hoặc ở tiến trình khác.

## 2. Tại sao Spring Modulith cần context propagation?

Spring Modulith mô tả ứng dụng Spring Boot theo các **application module** có ranh giới rõ ràng. Ví dụ, một yêu cầu đặt hàng có thể đi qua module `orders`, gọi API công khai của module `payments`, rồi phát sự kiện để module `notifications` tiếp tục xử lý. Khả năng quan sát của Spring Modulith giúp ghi nhận tương tác tại ranh giới module thành các observation/span Micrometer, kết hợp cơ chế Actuator, metrics và tracing của Spring Boot.

Khi xử lý đồng bộ trên một thread, observation hiện hành thường được gắn với thread thông qua một **scope**. Lời gọi sang module kế tiếp có thể tạo span con trong cùng trace. Nhưng hệ thống thực tế thường chuyển việc sang thread pool hoặc reactive scheduler:

~~~text
HTTP request
  └── orders.placeOrder()           [request thread]
        ├── payments.chargeAsync()  [executor thread]
        └── notifications.send()    [Reactor scheduler]
~~~

Nếu ngữ cảnh không theo kịp chỗ chuyển luồng, các thao tác vẫn có thể thành công về nghiệp vụ nhưng trace bị tách, thiếu quan hệ cha–con hoặc log của tác vụ không còn `traceId`. Đó là lỗi **khả năng quan sát**, không nhất thiết là lỗi xử lý đơn hàng.

Ví dụ dấu vết mong muốn:

~~~text
Trace T-123
  HTTP POST /orders                  span A
    orders.placeOrder                span B
      payments.charge                span C  (thread khác)
      notifications.send             span D  (reactive)
~~~

Các span không buộc phải có cùng `spanId`: chúng thường **cùng `traceId` nhưng có `spanId` riêng**, và quan hệ cha–con được gắn đúng. Việc mọi đoạn code đều tạo span cũng không tự động được đảm bảo: cần instrumentation tương ứng và hệ thống ghi nhận trace.

## 3. Hiểu đúng các loại context

| Thành phần | Lưu gì? | Phạm vi và ý nghĩa |
| --- | --- | --- |
| `Observation` / tracing context | Observation hiện hành; tùy cấu hình có thông tin span, trace | Xác định operation nào đang được quan sát và quan hệ trong trace |
| `ThreadLocal` | Giá trị gắn với **một thread** | Tiện trong mã đồng bộ nhưng không tự nhảy sang thread pool |
| SLF4J MDC | Các cặp khóa–giá trị để đưa vào log, ví dụ `traceId`, `spanId` | Thường dựa trên `ThreadLocal`; việc có MDC đúng tùy tracing bridge và scope |
| Micrometer `ContextSnapshot` | Ảnh chụp các giá trị context mà accessor đã đăng ký đọc được | Cầu nối để khôi phục giá trị ở thread hoặc loại context khác |
| Reactor `Context` | Dữ liệu bất biến theo **subscription/subscriber** | Nên là nguồn ngữ cảnh chính trong chuỗi reactive; không phụ thuộc cố định vào thread |
| Dữ liệu nghiệp vụ | `orderId`, `customerId`, trạng thái thanh toán... | Phải truyền bằng tham số, command, event payload hoặc cơ chế lưu trữ phù hợp |

**Phân biệt then chốt:** propagation giữ thông tin *đang quan sát công việc nào*; nó không thay thế việc truyền dữ liệu nghiệp vụ. Không dùng MDC hoặc tracing baggage làm nơi chứa thông tin quan trọng để hệ thống ra quyết định.

Một số thư viện sử dụng `ThreadLocal` để cho phép truy cập observation hiện hành trong mã imperative. Micrometer Context Propagation cung cấp các khái niệm:

- `ThreadLocalAccessor`: biết cách đọc, ghi, xóa một loại `ThreadLocal`.
- `ContextAccessor`: đọc/ghi context dạng cấu trúc như Reactor `Context`.
- `ContextRegistry`: đăng ký và tìm các accessor.
- `ContextSnapshot`: chụp tại **thời điểm giao việc**, khôi phục tạm thời khi task chạy và dọn lại khi scope đóng.

Chỉ những giá trị có **accessor phù hợp** mới được chuyển qua cơ chế snapshot. Bật propagation không có nghĩa mọi `ThreadLocal` tự tạo, mọi khóa MDC hoặc mọi biến trong ứng dụng đều được sao chép.

## 4. Context chạy thế nào trên cùng thread?

Trong mã imperative, observation có thể được tạo và mở scope quanh công việc:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class OrderUseCase {
    private final ObservationRegistry registry;
    private final PaymentApi paymentApi;

    public OrderUseCase(ObservationRegistry registry, PaymentApi paymentApi) {
        this.registry = registry;
        this.paymentApi = paymentApi;
    }

    public void placeOrder(String orderId) {
        Observation.createNotStarted("order.place", registry)
            .observe(() -> paymentApi.charge(orderId));
    }
}
~~~

Trong phạm vi `observe(...)`, observation được đưa vào scope để các thành phần có instrumentation đọc được ngữ cảnh hiện hành. Nếu `PaymentApi` là API công khai của module `payments` được Spring Modulith instrument, lời gọi có thể tạo module span nằm dưới ngữ cảnh của operation đang chạy. Observation được kết thúc ngay cả khi mã trong callback ném exception, theo cơ chế `observe` của Micrometer.

Phần trên minh họa **một luồng đồng bộ**. Ngay khi tác vụ được đẩy sang thread khác, không nên giả định `ObservationRegistry.getCurrentObservation()` trong worker sẽ còn giống thread gửi.

## 5. Chuyển thread và executor: chỗ context thường bị mất

Xét ví dụ sau:

~~~java
// Đang chạy trong request thread, có observation hiện hành.
executor.execute(() -> paymentApi.charge(orderId));
~~~

Lệnh `execute` chỉ chuyển một `Runnable` vào hàng đợi. Thread nhận việc có bộ `ThreadLocal` riêng, có thể đã được tái sử dụng từ tác vụ trước. Mặc định, Java `Executor` không biết phải mang observation, MDC hay các context khác từ thread gửi theo. Dùng `new Thread(...)` hay `CompletableFuture.supplyAsync(...)` với common pool cũng tạo ranh giới tương tự.

### 5.1. Ưu tiên `ContextPropagatingTaskDecorator` với Spring

Khi ứng dụng dùng `ThreadPoolTaskExecutor` do mình cấu hình, gắn task decorator tại chính executor đó. Ví dụ dưới đây có thể áp dụng với Spring Framework 6.1+ và phiên bản Spring Boot tương thích:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncConfiguration {

    @Bean("moduleTaskExecutor")
    ThreadPoolTaskExecutor moduleTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("module-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Một bean khác có thể giao việc qua executor đã cấu hình:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
class PaymentWorker {

    @Async("moduleTaskExecutor")
    public CompletableFuture<Void> chargeAsync(String orderId) {
        // Tại đây observation context đã được khôi phục nếu
        // nó được bắt ở thread gửi và có accessor thích hợp.
        performCharge(orderId);
        return CompletableFuture.completedFuture(null);
    }

    private void performCharge(String orderId) {
        // Xử lý nghiệp vụ minh họa.
    }
}
~~~

Lời gọi `@Async` phải đi **qua Spring proxy** (chẳng hạn từ bean khác). Tự gọi `this.chargeAsync(...)` trong cùng bean thường bỏ qua cơ chế `@Async`. Việc sử dụng decorator chỉ tác động đến các task được gửi **đúng executor đã cấu hình**. Nếu sự kiện hoặc tác vụ dùng executor khác, cần xem cấu hình executor thực tế của nó.

Một số phiên bản Spring Boot mới có tùy chọn cấu hình sẵn việc lan truyền context cho `AsyncTaskExecutor` tự động tạo. Tên thuộc tính và cơ chế kích hoạt phụ thuộc phiên bản; cấu hình decorator minh thị như trên giúp xác định rõ đường chạy trong ví dụ. Tránh tạo nhiều executor nhưng chỉ cấu hình propagation trên một executor không được dùng.

### 5.2. Với `CompletableFuture`, chỉ định executor ở mọi chặng bất đồng bộ

~~~java
CompletableFuture
    .supplyAsync(() -> loadInvoice(orderId), moduleTaskExecutor)
    .thenApplyAsync(this::calculateFee, moduleTaskExecutor)
    .thenAcceptAsync(this::storeResult, moduleTaskExecutor);
~~~

Nếu một stage sử dụng `*Async(...)` **không truyền executor**, stage đó có thể chạy trên common pool và không nhận decorator của `moduleTaskExecutor`. Các stage không có hậu tố `Async` có cơ chế chọn thread khác, không được dựa vào một thread cụ thể để lưu thông tin quan sát.

### 5.3. Khi phải dùng `Executor` không do Spring quản lý

Micrometer `ContextSnapshot` cho phép chụp context ở phía gửi và khôi phục trong `Runnable`. Mẫu sau tập trung vào cơ chế truyền; cần có thư viện `io.micrometer:context-propagation` cùng các accessor được đăng ký:

~~~java
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;
import java.util.concurrent.Executor;

void submitPayment(Executor executor, String orderId) {
    // Chụp khi còn ở thread chứa observation hiện hành.
    ContextSnapshot snapshot =
        ContextSnapshotFactory.builder().build().captureAll();

    executor.execute(() -> {
        try (ContextSnapshot.Scope ignored = snapshot.setThreadLocals()) {
            paymentApi.charge(orderId);
        }
        // Scope tự khôi phục/xóa giá trị đã thay đổi.
    });
}
~~~

Không chia sẻ một scope đã mở giữa các thread. Hãy **capture trước khi submit**, **restore tại nơi thực thi**, rồi **close trong `try-with-resources`**. Không gọi `ThreadLocal.set(...)` thủ công mà quên `remove()`: thread pool tái sử dụng thread và có thể làm lộ ngữ cảnh của request trước.

## 6. Reactive pipeline: context gắn với subscription, không gắn với thread

Một chuỗi Reactor có thể đổi thread qua `publishOn` hoặc `subscribeOn`:

- `publishOn(scheduler)` ảnh hưởng nơi các operator ở phía sau xử lý tín hiệu.
- `subscribeOn(scheduler)` ảnh hưởng việc subscription và phía nguồn bắt đầu chạy trên scheduler.
- Cả hai không bảo đảm giữ nguyên `ThreadLocal` của thread gọi ban đầu.

Reactor `Context` đi cùng subscriber và được đọc qua `deferContextual` (hoặc API đọc context tương ứng). Việc đổi scheduler không tự làm mất `Context`:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> buildNotification(String correlationId) {
    return Mono.delay(Duration.ofMillis(10))
        .publishOn(Schedulers.parallel())
        .flatMap(tick -> Mono.deferContextual(ctx ->
            Mono.just("correlationId=" + ctx.get("correlationId"))
        ))
        .contextWrite(ctx -> ctx.put("correlationId", correlationId));
}
~~~

Đoạn ví dụ lưu một ID ứng dụng theo cách minh họa; **không** giả định Spring Boot hay Spring Modulith tự tạo khóa `"correlationId"` này. Với Reactor, `contextWrite` cung cấp giá trị cho **phần upstream của subscription**, và `deferContextual` đọc khi có subscription. Một `Mono` mới được tạo nhưng chưa subscribe thì chưa có công việc reactive nào thực thi.

### 6.1. Cầu nối từ `ThreadLocal` sang Reactor `Context`

Micrometer Context Propagation liên kết các accessor với Reactor:

1. `ThreadLocalAccessor` lấy giá trị từ scope hiện hành ở phía imperative.
2. `contextCapture()` chụp những giá trị **đã đăng ký accessor** tại thời điểm subscription và chuyển chúng vào Reactor `Context`.
3. Trong luồng Reactor, các operator phù hợp hoặc chế độ tự động có thể khôi phục `ThreadLocal` từ Reactor `Context` khi gọi mã imperative.

Ví dụ sử dụng tại một ranh giới imperative → reactive:

~~~java
Mono<String> result = reactivePaymentApi
    .checkStatus(orderId)
    .map(this::formatStatus)
    .contextCapture();

// Việc capture diễn ra lúc subscription; thread tại thời điểm
// subscription phải đang chứa context cần đưa vào Reactor.
~~~

**Không hiểu nhầm:** có `contextCapture()` không đồng nghĩa `MDC.get("traceId")` ở mọi `map` đều có giá trị. Trong chế độ mặc định của Reactor, việc khôi phục `ThreadLocal` chỉ được thực hiện ở những operator được hỗ trợ (đáng chú ý là `handle` và `tap`). Để đọc một giá trị ứng dụng bên trong pipeline, nên ưu tiên Reactor `Context` thay vì phụ thuộc vào thread hiện tại.

### 6.2. Chế độ context propagation tự động

Trong các phiên bản Spring Boot hỗ trợ cấu hình sau, có thể bật chế độ tự động của Reactor:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Reactor cũng cung cấp `Hooks.enableAutomaticContextPropagation()` để kích hoạt ở thời điểm khởi động, **trước khi tạo các subscription cần quan sát**. Nên để Spring Boot quản lý hook nếu dùng thuộc tính Boot; không cần bật lặp lại bằng hai cách.

So sánh hai chế độ:

| Chế độ | Phạm vi khôi phục `ThreadLocal` từ Reactor `Context` | Khi nào phù hợp? |
| --- | --- | --- |
| `limited` (mặc định trong nhiều phiên bản Boot) | Các operator được hỗ trợ, nhất là `handle` và `tap` | Cần kiểm soát rõ chỗ bridge; ưu tiên chi phí thấp có đo đạc |
| `auto` | Khôi phục context trong phạm vi các operator thông qua cơ chế tự động | Ứng dụng tích hợp nhiều API imperative dựa vào tracing/MDC |

Chế độ `auto` **không tự sản sinh context nguồn** và cũng không làm các `ThreadLocal` tùy ý trở nên có thể truyền. Vẫn cần có accessor thích hợp, ngữ cảnh được đưa vào Reactor `Context`, và tracing infrastructure được cấu hình. Khôi phục liên tục có chi phí; hãy đo latency, throughput và hành vi dưới tải thực tế trước khi chọn mặc định cho toàn ứng dụng.

### 6.3. Một ranh giới khó: tự `subscribe()`

Khi service tự gọi `mono.subscribe()`, nó có thể tạo một vòng đời subscription tách khỏi request đang điều khiển lời gọi. Điều này làm quản lý lỗi, hủy, transaction và việc xác định thời điểm capture khó hơn. Trong ứng dụng WebFlux, ưu tiên **trả `Mono`/`Flux` cho tầng gọi** để framework quản lý subscription. Nếu chủ động tách công việc chạy nền, hãy quyết định rõ cần truyền context hiện hành hay mở một operation độc lập có liên kết nhân quả.

## 7. Dòng chảy điển hình qua module

Sơ đồ dưới biểu diễn **luồng logic** và chỗ cần mang context. Trạng thái trace thực tế tùy instrumentation và cách tích hợp tracing:

~~~mermaid
sequenceDiagram
    participant HTTP as HTTP request
    participant Orders as orders module
    participant Queue as Decorated executor
    participant Payments as payments module
    participant Reactor as Reactor pipeline
    participant Notifications as notifications module
    HTTP->>Orders: placeOrder()
    Note over HTTP,Orders: Observation / trace T đang ở scope request
    Orders->>Queue: submit(Runnable + captured snapshot)
    Note over Queue: Restore observation khi task bắt đầu
    Queue->>Payments: charge(orderId)
    Payments-->>Queue: result
    Note over Queue: Close scope / restore thread state
    Orders->>Reactor: compose Mono/Flux
    Note over Reactor: Truyền bằng Reactor Context khi subscribe
    Reactor->>Notifications: notify(orderId)
    Notifications-->>HTTP: Kết quả qua chuỗi xử lý
~~~

Những điều cần phân biệt:

- **Ranh giới module**: Spring Modulith biết thành phần nào thuộc module nào và có thể instrument lời gọi vào API module để tạo module-entry spans.
- **Ranh giới thread**: task decorator hoặc snapshot đảm nhiệm việc mang observation hiện hành sang thread thực thi.
- **Ranh giới reactive**: Reactor `Context` và cơ chế Context Propagation đảm nhiệm việc đưa dữ liệu qua các operator/scheduler.
- **Ranh giới tiến trình hoặc sự kiện bền vững**: `ContextSnapshot` trong bộ nhớ **không thể tự đi qua** Kafka, HTTP, database event publication hay việc restart; cần cơ chế truyền trace headers hoặc metadata và quy tắc mở trace mới.

Ở các event listener của Spring Modulith, đặc biệt listener bất đồng bộ hoặc event được phát lại sau khi ứng dụng khởi động, đừng mặc định một observation trong request ban đầu vẫn còn sống. Hãy kiểm tra executor mà listener sử dụng và chính sách tracing của kênh sự kiện. Khi event đi qua durable boundary, việc tiếp nối cùng trace hay tạo trace mới có **link/correlation** là lựa chọn kiến trúc riêng.

## 8. Quan sát kết quả bằng Spring Modulith, Actuator và tracing

### 8.1. Các thành phần cần có

Để quan sát tương tác module ở runtime, dự án cần cấu hình observability của Spring Modulith, ví dụ `spring-modulith-starter-insight` hoặc phần observability tương ứng. Starter Insight kết hợp thông tin Actuator và observability; muốn **xuất** traces còn phải cấu hình Micrometer Tracing cùng bridge/exporter phù hợp với hệ thống đang dùng (Zipkin, OpenTelemetry/OTLP, Tempo...). Version thư viện nên để BOM tương thích của dự án quản lý.

Endpoint `/actuator/modulith` biểu diễn thông tin cấu trúc module và dependency **tĩnh**; trace biểu diễn tương tác **đã thực sự chạy**. Endpoint Actuator không thay thế việc kiểm tra context propagation giữa các thread.

Spring Modulith có thể cung cấp các tag module span như `module.identifier`, `module.name`, `module.method`, `module.invocation-type`, và metrics về việc publish domain event (ví dụ `module.events.published`). Những thông tin này hữu ích để định vị module, nhưng **event counter tăng không chứng minh trace context đã được truyền đúng**.

### 8.2. Quy trình kiểm chứng tối thiểu

1. Bật tracing/exporter trong môi trường thử nghiệm và bảo đảm có request được lấy mẫu; nếu cần xem đủ trace khi học, có thể đặt `management.tracing.sampling.probability=1.0` **chỉ cho môi trường thử nghiệm**.
2. Gửi một request đi qua `orders`, giao việc cho `payments` qua executor và chạy thêm một nhánh Reactor.
3. Mở trace trong hệ thống tracing: tìm các span thực sự được instrument, kiểm tra `traceId` liên tục qua ranh giới và quan hệ span hợp lý.
4. So sánh với lần tắt decorator hoặc không bridge Reactor context trong môi trường test; tác vụ nghiệp vụ có thể vẫn chạy, nhưng context quan sát trong task có thể không có hoặc thành trace riêng.
5. Đối chiếu log có `traceId`/`spanId` nếu tracing bridge và pattern log đã cấu hình. Cần tách trường hợp **MDC không hiện trong log** với trường hợp **trace thực sự không được nối**.

Bạn cũng có thể kiểm tra trực tiếp observation hiện hành của executor được decorate bằng test nhỏ sau (giả sử `registry` và `moduleTaskExecutor` là các bean đã được cấu hình, có context propagation):

~~~java
import io.micrometer.observation.Observation;
import java.util.concurrent.atomic.AtomicReference;

Observation parent = Observation.start("example.request", registry);
AtomicReference<Observation> seenInWorker = new AtomicReference<>();

try (Observation.Scope ignored = parent.openScope()) {
    moduleTaskExecutor.submit(
        () -> seenInWorker.set(registry.getCurrentObservation())
    ).get();
} finally {
    parent.stop();
}

// Assertion trong test: observation của worker là observation đã capture.
assertSame(parent, seenInWorker.get());
~~~

Test này kiểm tra việc **chuyển observation context** trên executor. Nó không chứng minh rằng exporter, sampling, MDC và giao diện trace đã được cấu hình đầy đủ. Để kiểm tra tính liên tục của trace, cần thêm kiểm thử end-to-end có tracing bridge và span thực tế.

## 9. Chẩn đoán khi context bị đứt

| Triệu chứng | Nguyên nhân thường gặp | Cách xác nhận và xử lý |
| --- | --- | --- |
| Method `@Async` không xuất hiện trong thread pool mong muốn | Tự gọi method trong cùng bean, chưa bật `@EnableAsync` hoặc không đi qua Spring proxy | Kiểm tra bean gọi, tên thread, executor thực tế |
| Worker chạy nhưng không thấy observation hiện hành | Executor chưa gắn decorator, dùng một pool khác hoặc task được submit sau khi scope nguồn đã đóng | Xác định đường submit; capture trong scope nguồn; decorate đúng pool |
| `CompletableFuture` mất context ở stage thứ hai | `thenApplyAsync`/`supplyAsync` dùng common pool | Truyền executor có propagation cho từng stage cần chạy async |
| Custom `ThreadLocal` không được chuyển | Không có `ThreadLocalAccessor` đăng ký | Đăng ký accessor phù hợp hoặc truyền dữ liệu nghiệp vụ tường minh |
| Reactor `Context` có giá trị nhưng `MDC` trong `map` trống | Chế độ `limited`; không có restore ở operator đó hoặc thiếu bridge | Đọc qua `deferContextual`; cân nhắc `auto` và kiểm tra accessor |
| `contextCapture()` không lấy được giá trị | Tại **subscription time** không còn scope nguồn, hoặc chưa đăng ký accessor | Kiểm tra thread/timing của subscription và cách tạo context |
| Event xử lý sau restart thành trace mới | In-memory scope không tồn tại qua durable boundary | Dùng trace/message headers, correlation metadata hoặc trace link phù hợp |
| Không thấy trace nào trong backend | Chưa có tracer/exporter, sampling loại bỏ, endpoint chưa instrument hoặc collector lỗi | Kiểm tra config tracing và collector trước khi kết luận do propagation |
| Log của hai request dính nhầm ID | Tự gán `ThreadLocal`/MDC nhưng không dọn ở cuối task | Restore trong scope có `close`; tránh truyền state thủ công |

**Lỗi dễ mắc:** tưởng rằng Spring Modulith chỉ cần vẽ được module graph là đủ. Module graph trả lời “module nào phụ thuộc module nào”; runtime traces trả lời “lời gọi nào thực sự diễn ra, mất bao lâu, liên quan đến request nào”. Context propagation là điều kiện để các phần thực thi bất đồng bộ còn nối được thành câu chuyện quan sát đó.

## 10. Giới hạn và quyết định thiết kế

- **Đúng chức năng trước, quan sát đúng sau:** `orderId`, phiên bản dữ liệu, thông tin thanh toán phải đi trong input/output hoặc payload có hợp đồng rõ ràng. Context propagation chỉ là hạ tầng bổ trợ.
- **Không đưa dữ liệu nhạy cảm vào baggage, MDC hay tags:** ưu tiên ID kỹ thuật không tiết lộ thông tin cá nhân; tránh tag có cardinality quá cao trong metrics.
- **Đo hiệu năng:** việc capture/restore ở mỗi task rất nhỏ có overhead; chế độ `auto` trên pipeline dài cũng cần đo tải và so sánh với cách truyền ID tường minh.
- **Quan tâm vòng đời:** thread có thể sống lâu hơn request; observation kết thúc không đồng nghĩa tác vụ bất đồng bộ kết thúc. Thiết kế timeout, xử lý lỗi và quan hệ tracing hợp lý cho background jobs.
- **Không đồng nhất propagation với distributed tracing:** khi qua HTTP hoặc message broker, việc mang context cần carrier/headers và instrumentation của giao thức; decorator trong JVM chỉ giải quyết thread boundary tại chỗ.
- **Không chắc có cùng một trace sau sự kiện bền vững:** đối với xử lý sau commit, retry hoặc phát lại, một trace mới có correlation/link có thể phản ánh thực tế tốt hơn việc cố gắng nối vào span đã kết thúc.

## 11. Bài thực hành đề xuất

Xây một ứng dụng Spring Boot có ba module `orders`, `payments`, `notifications`. `orders` nhận `POST /orders`, gọi `payments` qua `@Async("moduleTaskExecutor")`, đồng thời gọi một pipeline `Mono` trong `notifications` có `publishOn`. Cấu hình Spring Modulith observability cùng tracing backend thử nghiệm.

Thực hiện lần lượt:

1. **Baseline:** chạy bằng executor không decorate; tại các ranh giới, log tên thread và `registry.getCurrentObservation()` trong môi trường test. Ghi nhận chỗ mất context.
2. **Executor:** thêm `ContextPropagatingTaskDecorator`; xác minh worker thấy observation được capture tại điểm submit.
3. **Reactor:** đưa correlation ID minh họa vào Reactor `Context` qua `contextWrite`; đọc sau `publishOn` bằng `deferContextual`. Nếu cần hỗ trợ API dựa vào MDC/ThreadLocal, bật cấu hình propagation tự động và kiểm chứng các accessor.
4. **Trace:** xem một trace có các module spans thực sự được instrument; xác định `traceId`, từng `spanId`, quan hệ cha–con và thời gian xử lý.
5. **Phản chứng:** gửi một stage của `CompletableFuture` qua common pool hoặc cố đọc MDC ở operator không được restore; giải thích vì sao kết quả khác với Reactor `Context`.

**Tiêu chí hoàn thành:** giải thích được thời điểm capture, nơi restore và nơi cleanup; tái hiện lỗi mất observation khi đổi thread; sửa được ranh giới executor; chứng minh Reactor `Context` tồn tại qua scheduler switch; không đồng nhất trace context với ID nghiệp vụ.

## 12. Ghi nhớ

Trong ứng dụng Spring Modulith, module boundary instrumentation cho biết *đang đi qua module nào*, còn context propagation giúp giữ mối liên hệ giữa các bước xử lý khi execution model thay đổi. Với mã imperative, nghĩ theo chu trình **capture → submit → restore → close**. Với Reactor, nghĩ theo **subscription → Reactor Context → operator**. Với message hoặc durable event, nghĩ theo **carrier/metadata và quan hệ nhân quả giữa các lần xử lý**.

### Tài liệu tham khảo

- [Spring Modulith – Production-ready Features: Actuator, observability và module spans](https://docs.spring.io/spring-modulith/reference/production-ready.html)
- [Spring Boot – Actuator Observability: Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Context Propagation – Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html)
- [Micrometer Context Propagation – Examples](https://docs.micrometer.io/context-propagation/reference/usage.html)
- [Project Reactor – Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)

> **Lưu ý phiên bản:** cú pháp và khả năng tự cấu hình có thể thay đổi giữa các dòng Spring Boot, Spring Framework, Reactor và Spring Modulith. Hãy dùng bộ phiên bản tương thích được BOM của dự án quản lý và đối chiếu reference guide tương ứng khi triển khai.
