# Request context không tự truyền sang thread mới

## 1. Vấn đề: listener xử lý event trên thread khác request

Trong ứng dụng Spring MVC, một HTTP request thường được xử lý trên một thread của servlet container. Spring gắn `RequestAttributes` với thread đó để các API như `RequestContextHolder`, bean `request scope` và một số thành phần web truy cập thông tin của request hiện tại.

Khi ứng dụng công bố event trong request:

~~~text
HTTP request /orders
    |
    v
Servlet thread: http-nio-8080-exec-1
  RequestContextHolder = RequestAttributes của request hiện tại
    |
    +-- publishEvent(new OrderPlaced(...))
            |
            +-- @EventListener đồng bộ, mặc định:
            |      chạy trên chính servlet thread
            |      -> có thể thấy RequestAttributes của request
            |
            +-- @Async @EventListener:
                   chạy trên executor thread event-1
                   -> KHÔNG tự có RequestAttributes
~~~

Bẫy hay gặp là listener dùng:

~~~java
RequestAttributes attributes =
    RequestContextHolder.currentRequestAttributes();
~~~

Đoạn trên có thể hoạt động trong request thread, nhưng ở thread xử lý event bất đồng bộ có thể ném `IllegalStateException` với thông điệp tương tự **“No thread-bound request found”**. Nếu dùng `RequestContextHolder.getRequestAttributes()`, kết quả thường là `null` thay vì exception.

Điều quan trọng: **event payload vẫn được truyền sang listener**, nhưng **request context gắn với thread không tự được truyền**. Đây là hai cơ chế khác nhau.

## 2. Request context trong Spring là gì?

Trong Spring Web MVC/Servlet, request context thường được đại diện bởi `org.springframework.web.context.request.RequestAttributes`. Nó cung cấp khả năng đọc các attribute theo scope, ví dụ `RequestAttributes.SCOPE_REQUEST`.

`RequestContextHolder` giữ tham chiếu này trong thread-bound storage; tùy cấu hình có thể sử dụng `ThreadLocal` hoặc `InheritableThreadLocal`. Một số thành phần liên quan:

| Thành phần | Vai trò |
| --- | --- |
| `DispatcherServlet` | Thông thường cung cấp request context trong quá trình dispatch HTTP của Spring MVC |
| `RequestContextFilter` / `RequestContextListener` | Có thể gắn request context cho các luồng xử lý servlet thích hợp |
| `RequestContextHolder.getRequestAttributes()` | Lấy request attributes đang gắn với thread, hoặc `null` nếu không có |
| `RequestContextHolder.currentRequestAttributes()` | Yêu cầu có request attributes; nếu thiếu có thể ném exception |
| Bean `‎@RequestScope` | Bean có vòng đời gắn với request; việc truy cập ngoài request context hợp lệ thường thất bại |
| `ThreadPoolTaskExecutor` / `@Async` | Chạy tác vụ trên thread executor; không tự vận chuyển mọi thread-bound context |

Một request có thể có các dữ liệu như `requestId`, `tenantId`, ngôn ngữ, header hoặc principal. Tuy nhiên, **không phải toàn bộ dữ liệu này nằm trong cùng một context**. Cần phân biệt:

- `RequestContextHolder`: Spring Web request attributes.
- `LocaleContextHolder`: locale/time zone gắn với thread.
- `SecurityContextHolder`: Spring Security authentication/security context.
- MDC của logging framework: thông tin log như request ID, correlation ID.
- Transaction context của transaction imperative: tài nguyên transaction do Spring gắn với thread.

Việc chuyển một trong các context trên **không đồng nghĩa tự chuyển tất cả context còn lại**. Cũng không nên tự sao chép toàn bộ các context chỉ vì listener cần một chuỗi `correlationId`.

## 3. Tại sao ThreadLocal không tự đi cùng event?

`ThreadLocal<T>` giữ một giá trị **riêng cho mỗi thread**, không phải một trường trên object event và không phải biến global dùng chung.

Ví dụ khái niệm:

~~~text
Thread A (request)              Thread B (executor)
--------------------            -------------------
ThreadLocal<Request> = R1       ThreadLocal<Request> = null

publishEvent(event)
    |
    +-- executor.execute(task)
                           -->  listener(event)
                                event tồn tại
                                request context không tự xuất hiện
~~~

`ApplicationEventPublisher.publishEvent(...)` truyền **event object** cho cơ chế multicaster. Khi listener chạy đồng bộ, nó thường chạy cùng thread của publisher nên có thể quan sát thread context hiện tại. Khi `‎@Async` hoặc một custom `ApplicationEventMulticaster` gán `TaskExecutor`, listener có thể thực thi trên thread khác và mất các thread-local bindings của request.

Đừng nhầm:

- **Bean singleton dùng chung** không có nghĩa request context dùng chung.
- **Event chứa request ID** không có nghĩa `RequestContextHolder` cũng được truyền.
- **TaskExecutor dùng cùng Java process** không có nghĩa thread-local của thread nguồn xuất hiện ở thread đích.
- **`publishEvent` được gọi trong transaction** không có nghĩa một listener bất đồng bộ được tham gia transaction đó.

Ở hệ thống dùng thread pool, thread làm việc có thể được tái sử dụng cho nhiều request; việc gắn nhầm request context từ request A vào thread rồi để lại có thể làm request B nhìn thấy dữ liệu cũ. Đây là rủi ro **đúng đắn và bảo mật**.

## 4. Ví dụ Java 17+ chạy được: request có context, listener @Async không có

Demo dùng **Spring Framework 6.2.18**, `spring-web`, `spring-test` và một request mô phỏng bằng `MockHttpServletRequest`. Không cần chạy web server; mục tiêu là tái hiện chính xác sự khác biệt giữa thread request và executor. Thông tin hữu ích `correlationId` được truyền an toàn bằng **payload `OrderPlaced`**, thay vì mong `RequestContextHolder` tự truyền sang thread mới.

### Cấu trúc dự án

~~~text
request-context-async-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/RequestContextDemo.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'request-context-async-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
    implementation 'org.springframework:spring-web:6.2.18'
    implementation 'org.springframework:spring-test:6.2.18'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.RequestContextDemo'
}
~~~

Tệp `src/main/java/demo/RequestContextDemo.java`:

~~~java
package demo;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

@Configuration
@EnableAsync
public class RequestContextDemo {

    // Payload là một snapshot giá trị. Không mang HttpServletRequest
    // hoặc RequestAttributes sang thread khác.
    public record OrderPlaced(long orderId, String correlationId) {}

    public record Observation(
        String contextCorrelationId,
        String eventCorrelationId,
        boolean onExecutorThread
    ) {}

    @Bean(name = "taskExecutor")
    ThreadPoolTaskExecutor taskExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("event-");
        return executor;
    }

    @Bean
    BlockingQueue<Observation> observations() {
        return new LinkedBlockingQueue<>();
    }

    @Bean
    AsyncOrderListener asyncOrderListener(
            BlockingQueue<Observation> results) {
        return new AsyncOrderListener(results);
    }

    // Không đánh dấu class/method final: @Async cần proxy
    // trong cấu hình proxy tiêu chuẩn.
    public static class AsyncOrderListener {
        private final BlockingQueue<Observation> results;

        public AsyncOrderListener(BlockingQueue<Observation> results) {
            this.results = results;
        }

        @Async
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            RequestAttributes attributes =
                RequestContextHolder.getRequestAttributes();

            String contextId = attributes == null
                ? "<none>"
                : String.valueOf(attributes.getAttribute(
                    "correlationId",
                    RequestAttributes.SCOPE_REQUEST
                ));

            results.add(new Observation(
                contextId,
                event.correlationId(),
                Thread.currentThread().getName().startsWith("event-")
            ));
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                RequestContextDemo.class)) {

            // Giả lập thread xử lý HTTP request.
            var request = new MockHttpServletRequest();
            request.setAttribute("correlationId", "REQ-101");

            RequestContextHolder.setRequestAttributes(
                new ServletRequestAttributes(request),
                false  // KHÔNG bật InheritableThreadLocal
            );

            try {
                String requestId = String.valueOf(
                    RequestContextHolder.currentRequestAttributes()
                        .getAttribute(
                            "correlationId",
                            RequestAttributes.SCOPE_REQUEST
                        )
                );
                System.out.println("request thread context: " + requestId);

                // Đưa dữ liệu cần thiết vào một immutable event payload.
                context.publishEvent(new OrderPlaced(101L, requestId));

                // Đợi listener trên executor hoàn tất để kiểm tra,
                // không block trong thread xử lý web thật.
                // Queue chưa chắc có kết quả ngay sau publishEvent.
                // Đợi tín hiệu hoàn tất từ thread worker tối đa 10 giây.
                @SuppressWarnings("unchecked")
                BlockingQueue<Observation> queue =
                    (BlockingQueue<Observation>) context
                        .getBean("observations");
                Observation result = queue.poll(10, TimeUnit.SECONDS);

                if (result == null) {
                    throw new IllegalStateException(
                        "Async listener did not finish"
                    );
                }

                System.out.println(
                    "listener on executor: " + result.onExecutorThread()
                );
                System.out.println(
                    "worker request context: " + result.contextCorrelationId()
                );
                System.out.println(
                    "event correlationId: " + result.eventCorrelationId()
                );
            } finally {
                // Gỡ request context khỏi thread nguồn.
                RequestContextHolder.resetRequestAttributes();
            }
        }
    }
}
~~~

**Lưu ý về việc đợi event:** trong demo, `poll(timeout)` được sử dụng để biến kết quả bất đồng bộ thành stdout có thể kiểm tra. Trong Spring MVC thực tế, không nên dùng `block()` hay chờ trên request thread chỉ để đợi một tác vụ mà nghiệp vụ cho phép chạy nền. Dùng trạng thái công việc, queue bền vững hoặc API phản hồi phù hợp.

Chạy bằng JDK 17+ và Gradle / Gradle Wrapper nếu có:

~~~bash
gradle run --quiet
# Linux/macOS với wrapper: ./gradlew run --quiet
# Windows với wrapper: gradlew.bat run --quiet
~~~

Các dòng do chương trình tự in:

~~~text
request thread context: REQ-101
listener on executor: true
worker request context: <none>
event correlationId: REQ-101
~~~

Giải thích:

1. `RequestContextHolder.setRequestAttributes(..., false)` gắn request mô phỏng vào **main thread**; vì vậy dòng đầu đọc được `REQ-101`.
2. `context.publishEvent(...)` công bố `OrderPlaced` chứa bản sao chuỗi correlation ID.
3. `@Async` kết hợp `@EnableAsync` đưa listener vào `ThreadPoolTaskExecutor`; đây là một thread khác. Không có cơ chế truyền `RequestAttributes`, nên listener thấy `null` và hiển thị `<none>`.
4. Tuy request context không truyền theo, **payload `OrderPlaced.correlationId` vẫn còn nguyên**, vì object event được Spring chuyển cho listener.
5. Cuối cùng `resetRequestAttributes()` bảo đảm binding của request trên thread ban đầu được dọn; executor được đóng khi Spring context đóng.

**Vì sao demo dùng `MockHttpServletRequest`?** Nó tái hiện `ServletRequestAttributes` mà không cần servlet container. Đây là bài học về **thread-local context**, không phải mô phỏng đầy đủ HTTP lifecycle, Spring Security hay transaction.

## 5. Cách làm khuyến nghị: chụp dữ liệu cần thiết thành event payload

Nếu listener chỉ cần `requestId`, `correlationId`, `tenantId` hoặc ID của người khởi tạo, hãy trích xuất **giá trị được phép sử dụng** ngay tại boundary đang có context hợp lệ, rồi công bố event chứa các giá trị ấy.

Ví dụ với Spring MVC:

~~~java
// Đoạn minh họa trong controller/service; không phải file độc lập.
@PostMapping("/orders")
public ResponseEntity<Void> placeOrder(
        @RequestHeader("X-Correlation-ID") String correlationId,
        @RequestBody PlaceOrder command) {

    // Validate header, quyền truy cập, định dạng và kích thước ID.
    applicationService.place(command, correlationId);
    return ResponseEntity.accepted().build();
}
~~~

Ở tầng ứng dụng:

~~~java
// Đoạn minh họa; cần các type và bean của ứng dụng.
public void place(PlaceOrder command, String correlationId) {
    Order order = orderDomainService.place(command);
    publisher.publishEvent(new OrderPlaced(
        order.getId(),
        correlationId
    ));
}
~~~

Listener bất đồng bộ:

~~~java
@Async
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    notificationService.enqueue(
        event.orderId(),
        event.correlationId()
    );
}
~~~

Đây là hướng tiếp cận rõ ràng vì:

- Không lệ thuộc request còn sống sau khi controller đã trả response.
- Không cần sao chép toàn bộ HTTP request, session hoặc request-scoped bean sang worker.
- Dễ viết test cho consumer: chỉ cần tạo event payload.
- Dễ nâng cấp từ local event lên broker/outbox vì metadata là một phần contract.
- Tránh rò rỉ trạng thái request giữa các task chạy trong thread pool.

**Không đặt toàn bộ header, access token, cookie hoặc mutable `HttpServletRequest` vào event**. Chỉ trích xuất trường có mục đích rõ ràng, tuân thủ chính sách quyền riêng tư và bảo mật. Nếu cần phân quyền, worker phải xác minh quyền theo trust boundary của chính nó; một chuỗi `userId` trong event không tự chứng minh quyền truy cập.

## 6. Những cách xử lý dễ sai

### Sai 1 — Cố gọi currentRequestAttributes() trong @Async listener

~~~java
@Async
@EventListener
public void handle(OrderPlaced event) {
    String id = (String) RequestContextHolder
        .currentRequestAttributes()
        .getAttribute("correlationId", RequestAttributes.SCOPE_REQUEST);
}
~~~

Có thể ném `IllegalStateException` khi worker không có request context. Trong listener `void` chạy async, exception cũng thường **không quay về thread publish**, nên cần logging, `AsyncUncaughtExceptionHandler` hoặc cơ chế theo dõi tác vụ.

Cách sửa: dùng `event.correlationId()` theo một contract rõ ràng, hoặc triển khai propagation có kiểm soát khi thực sự cần toàn bộ execution context.

### Sai 2 — Bật inheritable=true để “sửa mọi thread”

~~~java
RequestContextHolder.setRequestAttributes(attributes, true);
~~~

Tham số `true` dùng `InheritableThreadLocal` để **thread con mới được tạo** có thể nhận giá trị kế thừa. Nó **không phải cách giải quyết tổng quát cho thread pool**:

- Thread trong pool có thể đã tồn tại từ trước, nên không kế thừa gì.
- Một thread pool có thể tạo thread mới khi đang phục vụ request A rồi **tái sử dụng thread đó** cho request B; request context cũ có nguy cơ bị giữ lại hoặc rò rỉ.
- Request A có thể đã kết thúc khi task chạy, khiến request attributes không còn hợp lệ.

Javadoc của Spring cảnh báo không bật thừa kế request context trên các pooled threads có thể tạo thread động theo tải. `RequestContextFilter.setThreadContextInheritable` mặc định là `false` vì lý do đó.

### Sai 3 — Sao chép HttpServletRequest hoặc request-scoped bean sang task nền

~~~java
// Anti-pattern; không phải file biên dịch độc lập:
executor.execute(() -> {
    String token = request.getHeader("Authorization");
    doBackgroundWork(token);
});
~~~

Task có thể chạy sau khi request kết thúc; hơn nữa chuyển trực tiếp token cho tác vụ khác dễ tạo vấn đề bảo mật và quản lý vòng đời. Đừng dựa vào một request object còn sống khi listener chạy. Hãy trích xuất dữ liệu không nhạy cảm cần thiết, thiết kế cấp quyền độc lập và thời hạn xử lý phù hợp.

### Sai 4 — Quên dọn ThreadLocal ở worker

Nếu ứng dụng thực sự phải truyền một số **execution context** bằng `TaskDecorator`, runnable wrapper phải **restore trạng thái cũ hoặc clear trong `finally`**. Quên dọn sẽ làm worker của request B đọc metadata của request A. Không dùng `ThreadLocal` như một kho dữ liệu vĩnh viễn.

### Sai 5 — Nhầm logger MDC, security và request scope

Việc bật context propagation cho MDC/observability **không đồng nghĩa** request-scoped beans tự hoạt động ở mọi executor. Security context dùng cơ chế riêng, ví dụ các executor wrapper của Spring Security khi đúng mục đích. Context không được cung cấp thì không nên “sửa” bằng cách tạo principal giả.

## 7. Khi nào dùng TaskDecorator hay ContextPropagatingTaskDecorator?

`ThreadPoolTaskExecutor` hỗ trợ `TaskDecorator` để bọc `Runnable` trước khi giao cho worker. Đây là extension point để truyền **execution metadata** có kiểm soát, ví dụ logging correlation, observation/trace context.

Với Spring 6.1+, `org.springframework.core.task.support.ContextPropagatingTaskDecorator` hỗ trợ khôi phục context dựa trên thư viện **Micrometer Context Propagation** và các accessor tương ứng.

Ví dụ cấu hình **minh họa**, không đưa vào demo mục 4:

~~~java
@Bean
ThreadPoolTaskExecutor taskExecutor() {
    var executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setThreadNamePrefix("event-");

    // Cần dependency micrometer-context-propagation và
    // những ThreadLocalAccessor được đăng ký phù hợp.
    executor.setTaskDecorator(
        new ContextPropagatingTaskDecorator()
    );
    return executor;
}
~~~

Cần import `org.springframework.core.task.support.ContextPropagatingTaskDecorator` và có dependency Micrometer tương ứng. Điểm quan trọng:

1. Decorator nên được dùng cho **metadata có vòng đời an toàn**, chẳng hạn tracing/log context, không mặc định sao chép toàn bộ `ServletRequestAttributes`.
2. Nó **không phải phép màu**: chỉ những context có cơ chế capture/restore và accessor phù hợp mới được truyền.
3. Có overhead cho capture/restore; cần kiểm thử với workload.
4. Việc restore/clear trong `finally` rất quan trọng để không làm bẩn pooled thread.
5. Nếu mục tiêu chỉ là dùng một `correlationId` ở listener, **event payload rõ ràng thường đơn giản hơn**.

### Có trường hợp Spring tự gắn request context ở async servlet không?

Có. Một **servlet async dispatch** đi qua `DispatcherServlet` hoặc `RequestContextFilter` có thể được Spring gắn request context cho chính **dispatch thread** đó. Nhưng đây là hành vi của **lifecycle async servlet được container quản lý**, không phải bảo đảm cho bất kỳ `@Async` method, executor task hoặc event listener nào do ứng dụng khởi tạo. Cần phân biệt rõ hai cơ chế.

## 8. @TransactionalEventListener, @Async và transaction context

Bài học tập trung vào HTTP request context, nhưng khi dùng Spring application events còn có một bẫy khác: **request context, transaction context và thời điểm phát listener không phải một thứ**.

| Listener | Thread và thời điểm thường gặp | Lưu ý |
| --- | --- | --- |
| `@EventListener` mặc định | Đồng bộ, thường trên thread gọi `publishEvent` | Có thể nhìn thấy request attributes nếu publish trong servlet request thread |
| `@Async @EventListener` | Chạy trên thread executor; có thể bắt đầu ngay sau khi event được dispatch | Không tự có request/transaction thread context; có thể chạy **trước DB commit** |
| Custom `SimpleApplicationEventMulticaster` có executor | Có thể dùng worker threads cho listener hỗ trợ async | Các listener **không hỗ trợ thực thi async** có thể vẫn chạy đồng bộ theo contract riêng |
| `‎@TransactionalEventListener(AFTER_COMMIT)` | Đăng ký callback trong transaction; xử lý khi transaction commit thành công | **Không tự tạo transaction mới**, cũng không tự chuyển HTTP request context |
| `‎@TransactionalEventListener(AFTER_COMMIT)` kèm `@Async` | Callback được kích hoạt sau commit, còn method được giao cho executor theo async proxy | Request/transaction thread context không tự truyền vào worker; phải quản lý lifecycle và lỗi async |

Với `TransactionalEventListener`, Spring có thể có transaction synchronization còn gắn tài nguyên trước cleanup; nếu listener muốn ghi DB **sau commit**, phải thiết lập transaction mới theo nhu cầu (ví dụ `REQUIRES_NEW` cho imperative). Đừng dùng request context để “đoán” trạng thái transaction.

Nếu sử dụng WebFlux/R2DBC, transaction và nhiều loại context được lưu trong **Reactor Context** gắn với subscriber, không phải servlet `RequestContextHolder`. Reactor Context có quy tắc propagation riêng trong một reactive chain; gọi `subscribe()` độc lập hoặc chuyển qua boundary khác vẫn cần thiết kế rõ. Không suy diễn từ việc Servlet thread-local mất sang kết luận Reactor Context luôn mất.

## 9. Test thực tế và cách chẩn đoán

### Test phải phân biệt thread nguồn và thread worker

Một bộ test tốt không chỉ assert listener “đã được gọi”; cần chứng minh **thread context có hay không** và **payload vẫn còn đúng**.

| Case | Mong đợi |
| --- | --- |
| `@EventListener` chạy mặc định trong servlet request thread | Có thể đọc `RequestContextHolder` khi request còn active |
| `@Async @EventListener` chạy trong thread pool mặc định | `getRequestAttributes()` thường trả `null` |
| `@Async` listener nhận payload `correlationId` | Đọc đúng giá trị mà publisher đã snapshot vào event |
| `currentRequestAttributes()` trong worker không được bind | Có thể ném `IllegalStateException` |
| Gửi task A, rồi task B trên cùng worker thread | Không rò metadata của request A sang B |
| Sau khi HTTP request kết thúc mới thực thi task | Không dereference raw request object; payload snapshot vẫn hợp lệ |
| Transaction T1 rollback trong khi `@Async @EventListener` đã chạy | Không được coi async listener là after-commit; chọn callback/outbox phù hợp |
| Context-propagating executor | Chỉ những context được cấu hình phù hợp mới được truyền, và phải dọn đúng |

### Các câu hỏi debug nên đi theo thứ tự

1. **Listener chạy trên thread nào?** Log tên thread tại `publishEvent` và trong listener.
2. **Dùng loại listener nào?** `@EventListener`, `@Async`, multicaster executor hay `@TransactionalEventListener`?
3. **RequestAttributes có ở thread nguồn không?** Dùng `RequestContextHolder.getRequestAttributes()` để kiểm tra an toàn.
4. **Worker thiếu request context hay request đã kết thúc?** Hai lỗi khác nhau nhưng đều khiến việc phụ thuộc raw request nguy hiểm.
5. **Listener thật sự cần dữ liệu gì?** `orderId`, `tenantId`, `correlationId`? Nếu là vài giá trị, đặt vào immutable payload.
6. **Có bật `InheritableThreadLocal` hoặc custom decorator không?** Đánh giá khả năng rò giữa tasks và việc clear/restore.
7. **Có tạo subscription/task ngoài vòng đời quản lý không?** `subscribe()`, raw `new Thread(...)`, executor dùng sai cấu hình có thể bỏ qua context propagation.
8. **Có lỗi async không báo về caller?** Quan sát error handler, Future/CompletableFuture, queue, metrics, tracing.
9. **Có cần bảo đảm event chỉ phát sau DB commit không?** Nếu có, tách bài toán transaction timing khỏi HTTP context.
10. **Đã test nhiều request đồng thời và thread pool reuse chưa?** Đây là trường hợp dễ lộ dữ liệu chéo giữa người dùng.

## 10. Checklist thiết kế để tránh phụ thuộc request context trong worker

- [ ] Chỉ lấy dữ liệu HTTP/request khi request còn hiệu lực.
- [ ] Chụp chính xác metadata cần thiết (ví dụ `correlationId`) vào payload hoặc envelope trước khi rời boundary.
- [ ] Không đưa raw `HttpServletRequest`, access token hay request-scoped bean vào task nền.
- [ ] Không gọi `currentRequestAttributes()` trong async handler nếu chưa thiết kế context binding cụ thể.
- [ ] Không bật `inheritable=true` trên pooled threads như cách khắc phục mặc định.
- [ ] Nếu propagate logging/observation context, dùng cơ chế capture/restore/cleanup rõ ràng.
- [ ] Phân biệt HTTP request context, security context, locale, MDC, transaction context và Reactor Context.
- [ ] Kiểm thử request kết thúc, nhiều request liên tiếp, worker reuse, lỗi async và transaction rollback.
- [ ] Với side effect quan trọng, có chính sách retry/idempotency hoặc outbox tùy yêu cầu độ tin cậy.

### Ghi nhớ

~~~text
Spring ApplicationEventPublisher:
  Chuyển object event tới listener.

@EventListener mặc định:
  Cùng thread publisher -> có thể thấy thread-bound context hiện có.

@Async @EventListener:
  Sang worker thread -> không tự có RequestContextHolder của request.

Cách ưu tiên:
  Trích xuất metadata hợp lệ khi còn trong request.
  Đưa giá trị tối thiểu vào immutable event payload.
  Listener chỉ dựa vào payload / dữ liệu hệ thống độc lập.

Không dùng:
  InheritableThreadLocal trên thread pool như một "bản sửa" mặc định.
  Raw HttpServletRequest cho công việc chạy sau request.
~~~

## Tài liệu chính thức

- [Spring Framework — ApplicationContext Events và Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — RequestContextHolder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html)
- [Spring Framework — RequestContextFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/RequestContextFilter.html)
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
