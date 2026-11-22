# Bẫy khi giữ request object trong Application Event: thread, vòng đời và cách tạo payload an toàn

## 1. Vấn đề: `HttpServletRequest` không phải dữ liệu event bền vững

Trong ứng dụng Spring MVC, `jakarta.servlet.http.HttpServletRequest` đại diện cho **một HTTP request cụ thể đang được Servlet container xử lý**. Nó cho phép controller/filter đọc method, path, header, parameter, attribute, principal và stream của body trong phạm vi request đó.

Một lỗi thiết kế thường gặp là đưa **nguyên đối tượng `HttpServletRequest`** vào Spring Application Event:

```java
public record OrderReceivedEvent(HttpServletRequest request) {}

@PostMapping("/orders")
public ResponseEntity<Void> submit(HttpServletRequest request) {
    publisher.publishEvent(new OrderReceivedEvent(request));
    return ResponseEntity.accepted().build();
}
```

Đây là **mã minh họa**, cần Spring MVC controller, `ApplicationEventPublisher`, import Servlet API và các cấu hình ứng dụng tương ứng.

Khi listener xử lý ngay, đồng bộ trên request thread, code có thể có vẻ hoạt động. Nhưng nếu sau này listener dùng `@Async`, multicaster có executor, listener chạy sau commit hoặc event được giữ lại trong queue, worker có thể truy cập request **sau khi thread/controller đã hoàn thành xử lý**. Khi đó dữ liệu có thể không còn hợp lệ, thay đổi, không còn truy cập an toàn hoặc phụ thuộc implementation của container.

**Nguyên tắc:** Event phải chứa **thông tin nghiệp vụ cần thiết đã được sao chép thành dữ liệu bất biến** trong khi request còn hiệu lực, thay vì giữ request, response, session, input stream hoặc object phụ thuộc thread/request scope.

Ví dụ nên ưu tiên:

```java
public record OrderReceivedEvent(
        String orderId,
        String requestId,
        String tenantId,
        String actorId) {}
```

Đây là record minh họa; các ID là giá trị đã được **xác thực/chuẩn hóa** bởi ứng dụng. Đừng dùng nguyên header `X-Tenant-Id` do client tự khai như danh tính được phép truy cập nếu chưa có bước ủy quyền.

## 2. Ba vòng đời khác nhau dễ bị nhầm

Trong Spring, vòng đời của event, thread và request **không đồng nhất**.

| Đối tượng/ngữ cảnh | Ai quản lý? | Lưu ý |
| --- | --- | --- |
| `HttpServletRequest` | Servlet container và request processing | Có ý nghĩa trong vòng đời request; không dùng như object lưu trữ dài hạn |
| `RequestContextHolder` | Spring Web, thông thường bind vào thread xử lý request | Không tự chuyển sang worker thread dùng cho `@Async` |
| `ApplicationEvent` | Spring event publisher/multicaster và consumer | Có thể được xử lý ngay, async, theo transaction phase hoặc được ứng dụng giữ lại |
| `SecurityContextHolder` | Spring Security theo chiến lược context | Mặc định thường dùng thread-local; cần chính sách propagation rõ ràng |
| MDC/tracing/observation context | Logging/observability integration | Không phải một phần của event payload mặc định |
| JDBC/JPA transaction | `PlatformTransactionManager` | Transaction imperative thường gắn thread; `@Async` không tự kế thừa |

Luồng nguy hiểm:

```text
HTTP request thread
  |
  +-- Controller nhận HttpServletRequest R1
  +-- publishEvent(new MyEvent(R1))
  |     |
  |     +-- @Async listener -> submit task
  |
  +-- Controller trả HTTP response
  +-- Servlet filter/DispatcherServlet kết thúc request
  +-- RequestContextHolder được cleanup
  +-- Container có thể thu hồi/recycle tài nguyên request
                         |
                         v
                 Executor worker thread
                         |
                         +-- đọc event.request()
                         +-- request data có thể không còn hợp lệ
                         +-- RequestContextHolder có thể là null
```

Spring Framework mặc định phát `@EventListener` **đồng bộ trên thread publisher** khi dùng multicaster mặc định. Nhưng `@Async` hoặc executor cấu hình ở `applicationEventMulticaster` làm listener chạy ở thread khác. **Kể cả Spring không bật async hôm nay, payload vẫn nên được thiết kế để không phụ thuộc request object**; chỉ một thay đổi kiến trúc sau này đã có thể biến code đang chạy thành race condition.

## 3. Sáu nhóm rủi ro khi giữ request trong event

### 3.1. Vòng đời request kết thúc trước khi listener đọc

Một số đối tượng Servlet có vòng đời gắn với request. Khi request kết thúc, container có thể giải phóng hoặc tái sử dụng nội bộ. Servlet API không thiết lập hợp đồng rằng bạn có thể giữ tham chiếu `HttpServletRequest` bao lâu tùy thích rồi dùng lại ở background worker sau request.

Hậu quả có thể khác theo container, filter, wrapper và thời điểm:

- `IllegalStateException` hoặc hành vi không còn được bảo đảm khi truy cập thuộc tính phụ thuộc vòng đời;
- `getInputStream()`/`getReader()` không còn dùng được như mong muốn;
- dữ liệu attribute thay đổi bởi phần khác của pipeline;
- wrapper tham chiếu tới tài nguyên đã đóng;
- worker đọc trạng thái không còn đại diện cho request ban đầu.

Không tuyên bố "Tomcat luôn recycle và trả request B khi đọc reference của A" — điều đó không phải một quy tắc phổ quát của Servlet API. **Vấn đề là không có hợp đồng an toàn về thời gian sống và thread-safety sau khi request kết thúc.**

### 3.2. Request object và attributes có thể mutable

`HttpServletRequest` cung cấp `setAttribute(...)`, `removeAttribute(...)` qua ServletRequest. Các filter, interceptor hoặc controller có thể thay đổi attributes trong quá trình xử lý. Đưa reference vào event **không chụp giá trị**:

```java
request.setAttribute("tenantId", "alpha");
publisher.publishEvent(new UnsafeEvent(request));
request.setAttribute("tenantId", "beta");
```

Một listener async đọc `event.request().getAttribute("tenantId")` về sau có thể thấy `"beta"`, không phải `"alpha"` tại lúc event phát. Với nhiều thread cùng đọc/ghi, còn có rủi ro dữ liệu không nhất quán. Việc bọc request trong Java `record` chỉ giữ reference ở field `final`; **không làm request bất biến**.

### 3.3. `RequestContextHolder` là thread-bound

Ví dụ mã lỗi:

```java
@Async
@EventListener
public void onOrderReceived(OrderReceivedEvent event) {
    ServletRequestAttributes attrs =
            (ServletRequestAttributes)
                    RequestContextHolder.currentRequestAttributes();
    HttpServletRequest request = attrs.getRequest();
    // Có thể ném IllegalStateException: không có request context
    // được bind vào worker thread.
}
```

Đây là **mã minh họa**, không phải chương trình độc lập. `RequestContextHolder.currentRequestAttributes()` ném `IllegalStateException` nếu không có context phù hợp. Ngược lại, `getRequestAttributes()` có thể trả `null`.

Request context trong `DispatcherServlet` được bind cho xử lý request; executor worker **không tự có cùng ThreadLocal**. Tự truyền reference request vào event không đồng nghĩa ThreadLocal request context đã được bind sang thread đó.

### 3.4. Body stream, multipart và session

Đặc biệt tránh cho event giữ:

- `ServletInputStream`/`BufferedReader` từ request body: stream có thể đã được đọc, tiêu thụ một lần hoặc đóng.
- `MultipartFile`/`Part` gắn với upload tạm: file tạm có thể bị cleanup sau request.
- `HttpSession`: quyền truy cập đồng thời không tự thread-safe; session có thể expire/invalidate.
- `HttpServletResponse`: response thường đã commit; không thể sửa headers/status/body từ background listener như ở controller.
- `ServletRequestAttributes` hoặc Spring `WebRequest`: chỉ là wrapper của request scope/context, không phải immutable snapshot.

Nếu worker phải xử lý file upload sau HTTP response, hãy **chủ động chuyển file sang storage bền vững trong thời gian request còn hiệu lực**, sau đó đưa `objectKey`, checksum, size và metadata đã kiểm tra vào event. Không chỉ giữ `MultipartFile` rồi đọc trong thread async.

### 3.5. Rủi ro giữ bộ nhớ và rò rỉ thông tin

Một `HttpServletRequest` reference có thể gián tiếp giữ attributes, security/session data, wrapper, body buffers và object graph lớn. Nếu event được giữ trong executor queue lâu, cache hoặc danh sách retry, garbage collector không thể giải phóng những đối tượng còn reachable.

Nếu vô tình serialize/log toàn bộ request, hệ thống cũng có thể phơi bày token `Authorization`, cookies, IP, query string, thông tin cá nhân hoặc dữ liệu bí mật trong attributes. Event nên áp dụng **data minimization**: chỉ các trường có mục đích nghiệp vụ rõ ràng.

### 3.6. `@TransactionalEventListener(AFTER_COMMIT)` cũng không cứu request reference

`AFTER_COMMIT` chỉ gắn listener với **kết quả transaction DB**, không mở rộng vòng đời `HttpServletRequest`. Nếu callback được chạy trên request thread và ngay sau commit, đôi khi request vẫn truy cập được; nhưng dựa vào chi tiết timing này là coupling mong manh. Khi callback chuyển qua `@Async` hoặc sau response, request có thể hết hiệu lực.

Nếu cần ghi database sau commit, phải xử lý transaction mới phù hợp (`Propagation.REQUIRES_NEW`) riêng với bài toán request context; đây là **hai vấn đề độc lập**.

## 4. Cách thiết kế đúng: snapshot payload bất biến

Thay vì event chứa `HttpServletRequest`, hãy lấy **chính xác các giá trị cần thiết** trước khi publish.

Ví dụ payload:

```java
public record RequestSnapshot(
        String requestId,
        String tenantId,
        String actorId,
        String httpMethod,
        String route) {}

public record OrderProcessingRequested(
        String orderId,
        RequestSnapshot context) {}
```

Đây là định nghĩa minh họa. Các `String` là immutable; Java record bảo đảm không thể gán lại các component sau khi tạo. Nếu thêm `List`/`Map` hay nested DTO, phải defensive copy (`List.copyOf`, `Map.copyOf`) và bảo đảm **phần tử bên trong cũng immutable**.

Một boundary để capture từ request:

```java
private static RequestSnapshot capture(
        HttpServletRequest request,
        String verifiedActorId,
        String verifiedTenantId) {

    String requestId =
            (String) request.getAttribute("correlationId");

    return new RequestSnapshot(
            requestId,
            verifiedTenantId,
            verifiedActorId,
            request.getMethod(),
            request.getRequestURI());
}
```

Đây là đoạn minh họa; `verifiedActorId` và `verifiedTenantId` phải được tầng xác thực/ủy quyền cung cấp. `getRequestURI()` có thể chứa dữ liệu người dùng trong path, nên cân nhắc dùng **route pattern đã định danh** như `/orders/{orderId}` cho telemetry và payload chung. Nếu không cần route, **bỏ field đó**.

**Chốt thời điểm snapshot:** capture **trong request thread, khi dữ liệu còn hợp lệ và đã xác thực**, rồi mới gọi `publisher.publishEvent(...)`. Không cho worker async nhận `Supplier<HttpServletRequest>` hoặc entity/request reference để tự capture muộn.

Một payload hữu ích thường chỉ cần `orderId`, `eventId`, `requestId`, `actorId` và `tenantId` đã xác thực. Nếu listener cần nội dung nghiệp vụ, hãy truyền một snapshot DTO nghiệp vụ đủ dữ liệu hoặc ID/version để truy vấn DB trong transaction riêng.

## 5. Ví dụ Java 17+ chạy được: mock request thay đổi trong khi listener chờ

Ví dụ dùng **Spring Framework 6.2.12**, `spring-web`, `spring-test`, Jakarta Servlet API, Gradle và Java 17+. Không cần Spring Boot hay web server.

Mục tiêu demo:

1. Tạo `MockHttpServletRequest` với tenant ban đầu `"tenant-original"`.
2. Publish một **event lỗi** giữ `HttpServletRequest` và một **event đúng** giữ snapshot record.
3. Hai `@Async @EventListener` dùng `CountDownLatch` để **dừng lại trước khi đọc payload**, loại bỏ tính ngẫu nhiên do timing.
4. Publisher đổi request attribute thành `"tenant-modified"`, đánh dấu request attributes hoàn tất, unbind `RequestContextHolder`, rồi cho worker tiếp tục.
5. Worker giữ reference đọc **tenant mới**, còn worker giữ snapshot đọc **tenant cũ**. Worker không có request context theo cấu hình ThreadLocal mặc định.

**Lưu ý:** `MockHttpServletRequest` từ `spring-test` cho phép mô phỏng sự thay đổi sau publish một cách xác định; nó **không mô phỏng đầy đủ cơ chế recycle/cleanup của Tomcat, Jetty hay Undertow**. Demo chứng minh shared mutable reference và thread-bound context; với request thật, hậu quả còn phụ thuộc Servlet container.

### 5.1. Cấu trúc dự án

```text
request-payload-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/RequestPayloadDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'request-payload-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-web:6.2.12'
    implementation 'org.springframework:spring-test:6.2.12'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'demo.RequestPayloadDemo'
}
```

`spring-test` được đưa vào `implementation` **chỉ vì demo là ứng dụng console sử dụng `MockHttpServletRequest` ở runtime**. Trong ứng dụng web production, không cần Spring Test trong main classpath; thư viện này thông thường thuộc `testImplementation`.

### 5.2. `src/main/java/demo/RequestPayloadDemo.java`

```java
package demo;

import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

public class RequestPayloadDemo {

    // Phản ví dụ: giữ reference đến request mutable.
    public record UnsafeEvent(HttpServletRequest request) {}

    // Đúng: chụp giá trị cần thiết vào object bất biến.
    public record RequestSnapshot(
            String requestId,
            String tenantId,
            String method,
            String path) {

        public static RequestSnapshot from(HttpServletRequest request) {
            return new RequestSnapshot(
                    Objects.toString(
                            request.getAttribute("requestId"), ""),
                    Objects.toString(
                            request.getAttribute("tenantId"), ""),
                    request.getMethod(),
                    request.getRequestURI());
        }
    }

    public record SafeEvent(RequestSnapshot snapshot) {}

    // Bean độc lập để chia sẻ trạng thái kiểm thử với proxy async.
    public static class Probe {
        final CountDownLatch entered = new CountDownLatch(2);
        final CountDownLatch release = new CountDownLatch(1);
        final CountDownLatch finished = new CountDownLatch(2);

        final AtomicReference<String> unsafeTenant =
                new AtomicReference<>();
        final AtomicReference<String> safeTenant =
                new AtomicReference<>();
        final AtomicReference<Boolean> workerHasRequestContext =
                new AtomicReference<>();
        final AtomicReference<Exception> error =
                new AtomicReference<>();

        void waitUntilReleased() throws InterruptedException {
            entered.countDown();
            if (!release.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker wait timed out");
            }
        }
    }

    public static class RequestEventListeners {
        private final Probe probe;

        public RequestEventListeners(Probe probe) {
            this.probe = probe;
        }

        @Async("eventExecutor")
        @EventListener
        public void onUnsafe(UnsafeEvent event) {
            try {
                probe.waitUntilReleased();

                // Cùng request reference đã bị publisher thay đổi.
                probe.unsafeTenant.set(Objects.toString(
                        event.request().getAttribute("tenantId"), ""));

                probe.workerHasRequestContext.set(
                        RequestContextHolder.getRequestAttributes() != null);
            } catch (Exception ex) {
                probe.error.compareAndSet(null, ex);
                if (ex instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }
            } finally {
                probe.finished.countDown();
            }
        }

        @Async("eventExecutor")
        @EventListener
        public void onSafe(SafeEvent event) {
            try {
                probe.waitUntilReleased();

                // Snapshot chỉ giữ String bất biến.
                probe.safeTenant.set(event.snapshot().tenantId());
            } catch (Exception ex) {
                probe.error.compareAndSet(null, ex);
                if (ex instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }
            } finally {
                probe.finished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {

        @Bean("eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        RequestEventListeners requestEventListeners(Probe probe) {
            return new RequestEventListeners(probe);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            Probe probe = context.getBean(Probe.class);

            // Mock request: không phải Servlet container thật.
            MockHttpServletRequest request =
                    new MockHttpServletRequest("POST", "/orders");
            request.setAttribute("requestId", "REQ-42");
            request.setAttribute("tenantId", "tenant-original");

            ServletRequestAttributes attributes =
                    new ServletRequestAttributes(request);

            RequestContextHolder.setRequestAttributes(attributes);
            try {
                // Chụp snapshot TRƯỚC khi publish.
                RequestSnapshot snapshot =
                        RequestSnapshot.from(request);

                context.publishEvent(new UnsafeEvent(request));
                context.publishEvent(new SafeEvent(snapshot));

                if (!probe.entered.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "both async listeners did not enter");
                }

                // Sau khi cả hai worker đã chờ, đổi request mutable.
                request.setAttribute("tenantId", "tenant-modified");

                // Mô phỏng kết thúc request attributes.
                attributes.requestCompleted();
            } finally {
                RequestContextHolder.resetRequestAttributes();
                probe.release.countDown();
            }

            if (!probe.finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "async listeners did not finish");
            }
            if (probe.error.get() != null) {
                throw new IllegalStateException(
                        "async listener failure", probe.error.get());
            }

            System.out.println(
                    "unsafe event tenant=" + probe.unsafeTenant.get());
            System.out.println(
                    "snapshot event tenant=" + probe.safeTenant.get());
            System.out.println(
                    "worker has request context="
                            + probe.workerHasRequestContext.get());
            System.out.println(
                    "publisher context after cleanup="
                            + (RequestContextHolder
                                    .getRequestAttributes() != null));
        }
    }
}
```

### 5.3. Chạy và đầu ra

Có JDK 17+ và Gradle đã cài:

```bash
gradle -q run
```

Các dòng `System.out.println` của chương trình:

```text
unsafe event tenant=tenant-modified
snapshot event tenant=tenant-original
worker has request context=false
publisher context after cleanup=false
```

Gradle có thể in log build riêng; bốn dòng trên là kết quả kiểm tra do chương trình tạo ra. `CountDownLatch` khiến kết quả không phụ thuộc việc worker nào được scheduler chạy trước. Mỗi listener `@Async` chờ chung một latch, còn publisher chỉ thay đổi request sau khi cả hai đã bắt đầu chờ.

**Vì sao kết quả khác nhau?**

1. `UnsafeEvent(request)` chứa reference đến cùng `MockHttpServletRequest` mutable mà publisher đang dùng.
2. `SafeEvent(snapshot)` chứa các giá trị `String` được đọc **trước khi publish**; `RequestSnapshot` không giữ request object.
3. Sau khi cả hai listener vào trạng thái chờ, publisher thay attribute từ `"tenant-original"` sang `"tenant-modified"`.
4. Khi mở latch, `onUnsafe` đọc reference và nhận giá trị mới; `onSafe` đọc snapshot và vẫn nhận giá trị cũ.
5. `RequestContextHolder.setRequestAttributes(...)` chỉ bind cho **publisher thread** theo mặc định; worker thread từ `ThreadPoolTaskExecutor` không tự mang theo binding. Vì thế `worker has request context=false`.
6. Trong khối `finally`, publisher gọi `RequestContextHolder.resetRequestAttributes()`, tránh để request context rò sang công việc khác trên chính thread đó.
7. Chương trình chờ `finished` và kiểm tra `error` trước khi in; dùng `AtomicReference` và latch để truyền kết quả an toàn giữa các thread.

**Giới hạn có chủ đích:** `MockHttpServletRequest` vẫn cho đọc attribute sau `attributes.requestCompleted()` trong tình huống mô phỏng này. **Không được suy ra** request thật an toàn để dùng sau completion. Chương trình chứng minh một reference không phải snapshot; chính ví dụ xấu chỉ có mặt để học, không phải mẫu production.

## 6. Áp dụng thực tế trong Spring MVC controller

Thay vì:

```java
@PostMapping("/orders")
public ResponseEntity<Void> submit(
        HttpServletRequest request,
        @RequestBody CreateOrderRequest body) {

    publisher.publishEvent(new OrderCreatedEvent(request, body));
    return ResponseEntity.accepted().build();
}
```

Đây là mã **không nên áp dụng**: event giữ request và có thể giữ cả `body` mutable. `CreateOrderRequest` là DTO do ứng dụng định nghĩa.

Một cách tốt hơn là tách dữ liệu đã kiểm tra khỏi object Servlet:

```java
public record OrderCreatedEvent(
        String orderId,
        String requestId,
        String tenantId,
        String actorId) {}

@PostMapping("/orders")
public ResponseEntity<Void> submit(
        HttpServletRequest request,
        @Valid @RequestBody CreateOrderRequest body,
        Authentication authentication) {

    // Ví dụ minh họa: ứng dụng phải validate/authz body,
    // tenantId và principal theo cơ chế security thực tế.
    String tenantId = tenantAccess.verifiedTenantId(authentication);
    String actorId = authentication.getName();
    String requestId = correlationIdResolver.resolve(request);

    String orderId = orderService.create(
            body, tenantId, actorId);

    publisher.publishEvent(new OrderCreatedEvent(
            orderId, requestId, tenantId, actorId));

    return ResponseEntity.accepted().build();
}
```

Đây là **đoạn minh họa, không phải chương trình độc lập**. Các dependency `tenantAccess`, `correlationIdResolver`, `orderService`, `CreateOrderRequest` do ứng dụng định nghĩa; cần Spring MVC, Jakarta Validation/Spring Security phù hợp. `@Valid` chỉ là bước validation DTO, **không thay thế kiểm tra quyền tenant**. `authentication.getName()` là một ví dụ định danh; production nên dùng stable subject ID theo domain nếu có.

Một trường hợp cần chú ý: nếu `orderService.create(...)` là transaction riêng, khi hàm trả về transaction có thể đã commit; event publish tại controller lúc đó có thể **không nằm trong transaction** nữa. Nếu muốn listener `@TransactionalEventListener(AFTER_COMMIT)` nhận event, hãy **publish bên trong transaction ở service**:

```java
@Service
public class OrderService {
    @Transactional
    public String create(CreateOrderCommand command) {
        String id = repository.insert(command);
        publisher.publishEvent(new OrderCreatedEvent(
                id, command.requestId(),
                command.tenantId(), command.actorId()));
        return id;
    }
}
```

Đây là **mã minh họa**, `CreateOrderCommand`, `repository`, `publisher` do ứng dụng định nghĩa. `command` ở đây là DTO bất biến/đã validate chuyển từ controller sang service; **không chứa `HttpServletRequest`**. Khi event được phát trong transaction, listener `AFTER_COMMIT` có thể đăng ký callback đúng pha.

## 7. `RequestContextHolder`, `@RequestScope` và thread pool

`RequestContextHolder` giữ `RequestAttributes` gắn với thread; `DispatcherServlet` thông thường expose request context trong khi xử lý request. `getRequestAttributes()` có thể trả `null` nếu thread không được bind:

```java
RequestAttributes attrs =
        RequestContextHolder.getRequestAttributes();

if (attrs == null) {
    // Thread hiện tại không có request context phù hợp.
}
```

Đoạn trên là code minh họa; import `RequestAttributes` và `RequestContextHolder` từ package `org.springframework.web.context.request`.

### Bẫy với request-scoped bean

```java
@RequestScope
@Component
public class RequestIdentity {
    private String correlationId;
    // ...
}
```

Nếu một async listener cố truy cập request-scoped proxy từ worker **không có request context**, có thể gặp `ScopeNotActiveException`, `IllegalStateException` hoặc lỗi liên quan, tùy cách truy cập. Nếu listener cần correlation ID, capture `String` trước khi publish; đừng chuyển request-scoped proxy vào event.

### Đừng sửa bằng cách bật inheritable request context cho mọi thread

`RequestContextHolder.setRequestAttributes(attributes, true)` có thể đưa request context vào **child thread mới** qua `InheritableThreadLocal` trong một số trường hợp. Nhưng một executor với thread pool **tái sử dụng thread**: không thể coi inheritable ThreadLocal là cơ chế context propagation đúng theo từng task. Thread có thể được tạo trước đó hoặc giữ dữ liệu không còn phù hợp.

Tài liệu Spring cảnh báo về việc sử dụng inheritable request context với các thread pool có khả năng thêm thread theo yêu cầu. Không bật `RequestContextFilter.setThreadContextInheritable(true)` như một mẹo để làm async listener truy cập được servlet request. Rủi ro bao gồm **request context sai người dùng**, dữ liệu cũ hoặc tình trạng giữ tài nguyên dài hơn dự kiến.

Nếu chương trình tự bind một ThreadLocal để thực hiện task có kiểm soát, **luôn restore hoặc remove trong `finally`**. Nhưng việc có thể bind một request context kỹ thuật **không làm đối tượng Servlet trở nên an toàn sau khi request kết thúc**.

## 8. `@Async` và cơ chế propagation context: dùng đúng mục đích

Spring Framework hỗ trợ `TaskDecorator`, và với thư viện Micrometer Context Propagation còn có `ContextPropagatingTaskDecorator` để chuyển một số ngữ cảnh quan sát/tracing/logging qua executor:

```java
@Bean("observedExecutor")
public ThreadPoolTaskExecutor observedExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator());
    executor.setThreadNamePrefix("observed-");
    return executor;
}
```

Đây là **mã minh họa**, không phải phần của ví dụ console; cần Spring 6.2, Micrometer Context Propagation trên classpath và import `ThreadPoolTaskExecutor`, `ContextPropagatingTaskDecorator`, `Bean`. Decorator hỗ trợ restoration của **các context có accessor/cấu hình phù hợp**. Không phải mọi `ThreadLocal` tùy ý sẽ tự được chuyển qua, và propagation context không làm sống lâu thêm Servlet request.

Tách rõ hai nhu cầu:

1. **Observability:** trace ID, span context, MDC phục vụ logging/correlation. Có thể dùng framework propagation và thiết lập/cleanup đúng để log từ worker vẫn nối với request.
2. **Business payload:** các giá trị nghiệp vụ mà listener cần để xử lý đúng (orderId, actorId, tenantId đã xác thực, eventId). Phải đưa chúng vào **event DTO bất biến** hoặc persisted work item, không phụ thuộc một logging context có thể bị xóa.

Nếu dùng Spring Security, có cơ chế như `DelegatingSecurityContextAsyncTaskExecutor` để truyền `SecurityContext` cho các tác vụ cụ thể; nhưng **không** coi nó là lý do để giữ nguyên `Authentication`, session hoặc request object trong event kéo dài. Quyền thực thi tác vụ nền cần có ranh giới tin cậy riêng, nhất là khi job chạy lại sau khi quyền của người dùng đã đổi.

### Phạm vi context của từng thread

| Ngữ cảnh | `@EventListener` đồng bộ mặc định | `@Async @EventListener` mặc định |
| --- | --- | --- |
| Event payload immutable | Có | Có |
| `RequestContextHolder` | Có thể có nếu đang chạy trong request thread | **Không tự propagate** |
| `SecurityContextHolder` | Có thể có nếu filter đã bind | Không tự đảm bảo có |
| MDC/trace | Thường nhìn thấy giá trị thread hiện tại | Không tự bảo đảm nếu không cấu hình propagation |
| Imperative JDBC transaction | Có thể tham gia transaction publisher | Không tự truyền sang worker |
| Servlet request reference | Có thể truy cập trong vòng đời request | **Không nên dùng**, dù reference được truyền |

Một event chứa snapshot bất biến là cách ổn định nhất để vượt ranh giới thread, lifecycle và retry.

## 9. Multipart, file upload và request body phải được xử lý trước khi phát event

Ví dụ lỗi:

```java
public record FileUploadedEvent(MultipartFile file) {}

@PostMapping("/files")
public void upload(@RequestParam MultipartFile file) {
    publisher.publishEvent(new FileUploadedEvent(file));
}
```

Đây là **mã minh họa xấu**, không phải lời khuyên triển khai. `MultipartFile` có thể được hỗ trợ bằng file tạm nằm trong quản lý của multipart resolver; sau request, container có thể dọn tài nguyên. Listener async đọc `file.getInputStream()` muộn có thể gặp lỗi hoặc không còn dữ liệu.

Cách đáng tin hơn:

```text
HTTP request đang hoạt động
   |
   +-- validate định dạng/kích thước
   +-- stream upload vào persistent storage có kiểm soát
   +-- kiểm tra checksum và xác định objectKey
   +-- publish FileReady(objectKey, checksum, size, requestId)
        |
        +-- listener async đọc từ storage theo objectKey
```

Không nên nhét toàn bộ file bytes vào Application Event nếu kích thước lớn; làm tăng chi phí memory, queue và logging. Nếu cần xóa file khi transaction rollback, thiết kế chiến lược cleanup bù trừ; upload storage ngoài DB không tự rollback theo JDBC transaction.

Đối với JSON body, controller có thể dùng `@RequestBody` để đọc và validate thành DTO. Hãy **ánh xạ phần thông tin cần thiết sang một event DTO/value object** trước khi publish, thay vì giữ `HttpServletRequest` hay đọc lại body stream từ worker.

## 10. Ranh giới bảo mật: không dùng raw header làm authority

Một lỗi nguy hiểm không chỉ liên quan async:

```java
String tenantId = request.getHeader("X-Tenant-Id");
publisher.publishEvent(new WorkRequested(tenantId, orderId));
```

Đây là **mã minh họa rủi ro**. Nếu header do client tùy ý gửi và consumer xem nó là tenant được phép truy cập, ứng dụng có thể tạo lỗ hổng cross-tenant. Snapshot chỉ giữ **giá trị**, không tự chứng minh giá trị đó đáng tin.

Thực hành an toàn:

- Xác thực principal, xác minh quyền với tenant/resource tại điểm ingress.
- Chỉ đưa **verified tenant ID** và **stable actor ID** vào event khi thật sự cần.
- Tránh đưa nguyên `Authorization` header, cookies, session ID, bearer token, refresh token, CSRF token hoặc nguyên `Authentication` có credentials.
- Coi `X-Request-Id` hoặc correlation ID từ bên ngoài là **input cần giới hạn độ dài/định dạng**. Có thể tạo request ID ở hệ thống nếu input không đáng tin.
- Không log toàn bộ event nếu payload chứa dữ liệu cá nhân; Java record tự sinh `toString()` với các components.
- Khi worker chạy trễ/retry, kiểm tra lại những quyền cần **current authorization** nếu chính sách nghiệp vụ đòi hỏi; quyền tại thời điểm request ban đầu không nhất thiết còn đúng.

Nếu listener chỉ cần actor ID để ghi audit một hành động đã được ủy quyền trước đó, snapshot verified actor ID là phù hợp. Nếu worker thực hiện **một hành động mới nhạy cảm**, phải thiết kế rõ nó chạy dưới quyền nào, có cần re-authorization hoặc service identity không.

## 11. Synchronous listener có được giữ request không?

Một listener đồng bộ xử lý ngay trong request thread có thể đọc request **khi request còn hoạt động**, chẳng hạn một listener cần log request metadata. Nhưng vẫn có hạn chế:

- Payload bị phụ thuộc mạnh vào web layer, khó tái sử dụng từ batch/scheduler/message broker.
- Unit test cần tạo/mock Servlet request thay vì chỉ truyền các giá trị nghiệp vụ.
- Nếu đổi sang async hoặc transaction-bound processing, code có thể hỏng.
- Listener có thể giữ event/request trong collection, cache, `CompletableFuture`, retry task mà không ai biết.
- Thay đổi request attributes sau publish làm những người dùng reference muộn thấy dữ liệu mới.
- Truy cập session/stream có quy tắc lifecycle/thread riêng, không tự bảo đảm an toàn chỉ vì listener đồng bộ.

**Được phép truy cập request trực tiếp trong phạm vi một HTTP request không đồng nghĩa nên chứa nó trong application-level event.** Tách web adapter và business event giúp code bền hơn khi xử lý bất đồng bộ.

Nếu event chỉ phục vụ một thao tác *thuần web* phải chạy ngay trong request, cân nhắc dùng interceptor/filter thay vì đẩy request object vào một domain event.

## 12. Có nên đưa toàn bộ dữ liệu request vào DTO snapshot?

Không. Snapshot đúng nghĩa là **bản chụp có chủ đích**, không phải serialize toàn bộ Servlet request.

| Kiểu payload | Phù hợp khi | Rủi ro cần kiểm soát |
| --- | --- | --- |
| `orderId`, `eventId` | Consumer chỉ cần tra cứu hoặc biết mốc nghiệp vụ | DB có thể thay đổi sau event; cần version nếu muốn snapshot lịch sử |
| `orderId`, `requestId`, `actorId`, `tenantId` | Audit/correlation cần những ID đã xác thực | Bảo vệ PII/tenant boundary, không log credentials |
| Immutable business snapshot | Consumer cần thông tin đúng ở thời điểm tạo event | Deep immutability, schema/version, kích thước |
| `HttpServletRequest` | **Không nên dùng làm event payload qua ranh giới async/lifecycle** | Lifetime, ThreadLocal, mutable state, memory retention |
| `HttpSession`/`MultipartFile`/`InputStream` | **Không nên giữ trong event dài hạn** | Thread safety, cleanup, one-shot stream, sensitive data |

Event bền vững thường có metadata:

```java
public record WorkRequested(
        String eventId,
        String requestId,
        String aggregateId,
        long aggregateVersion,
        String verifiedActorId,
        String verifiedTenantId) {}
```

Đây là đoạn minh họa; cần validate các ID và xem xét thời điểm capture. Nếu consumer có thể xử lý trùng, `eventId` giúp xây dựng idempotency. Nếu cần trạng thái lịch sử, `aggregateVersion` hoặc snapshot nghiệp vụ cho phép phát hiện event cũ khi đọc lại DB.

### Tránh shallow copy

Với payload chứa `List<MutableLine>`, `List.copyOf(...)` chỉ làm danh sách không thể sửa qua chính list đó, **không làm các phần tử `MutableLine` bất biến**. Hãy ánh xạ từng phần tử thành DTO bất biến, ví dụ Java record chứa `String`, `int`, `BigDecimal` và immutable nested DTO; collection sau đó `List.copyOf(...)`.

Không đưa entity JPA/proxy lazy-loading vào event async rồi kỳ vọng persistence context của request/transaction sẽ còn. Chụp DTO trong transaction có dữ liệu hợp lệ hoặc gửi ID/version để consumer mở transaction riêng và query theo mục đích.

## 13. `@TransactionalEventListener` và `@Async` có thể kết hợp, nhưng không mở rộng request lifetime

Ví dụ:

```java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCommitted(OrderCreatedEvent event) {
    // Xử lý event DTO bất biến trên worker thread.
    notificationService.schedule(event.orderId());
}
```

Đây là mã minh họa với event và service do ứng dụng định nghĩa. Cần:

1. `OrderCreatedEvent` được publish **bên trong transaction** mà bạn muốn theo dõi.
2. `@EnableAsync` và executor `eventExecutor`.
3. Listener là Spring-managed bean, method được async proxy intercept.
4. Event chứa **snapshot/ID phù hợp**, không giữ request.
5. Worker mở transaction DB riêng qua Spring service nếu cần thao tác với DB.

`AFTER_COMMIT` giải quyết **thời điểm so với transaction gốc**, `@Async` giải quyết **thread xử lý**, immutable DTO giải quyết **độ ổn định của payload**. Không cơ chế nào tự thực hiện thay nhiệm vụ của hai cơ chế còn lại.

`@TransactionalEventListener` mặc định bỏ qua event khi publish **không có transaction** (`fallbackExecution=false`). Nếu controller publish event **sau khi** một service `@Transactional` đã hoàn tất, listener có thể không chạy; hãy publish đúng trong service transaction hoặc điều chỉnh design cho phù hợp.

Với yêu cầu không mất task qua crash, cần transactional outbox/persistent work queue. Spring Application Events trong bộ nhớ không tự bảo đảm lưu và replay.

## 14. Kiểm thử để phát hiện lỗi request reference

Một bộ test tốt nên chủ động làm rõ rằng listener **không phụ thuộc Servlet request đã hoàn tất**:

1. **Chụp trước publish:** request có tenant `"original"`, snapshot được tạo, sau publish request mutable chuyển sang `"changed"`; event an toàn vẫn chứa `"original"`.
2. **Async scheduling:** dùng latch để chặn worker trước khi đọc; tránh `Thread.sleep` ngẫu nhiên.
3. **Request context trên worker:** `RequestContextHolder.getRequestAttributes()` thường là `null` nếu không cấu hình propagation; không coi đó là lỗi của Spring.
4. **Cleanup:** unbind request context ở boundary, xác minh thread được tái sử dụng không mang request cũ.
5. **Request scope:** không truy cập request-scoped bean từ worker nếu không có context hợp lệ.
6. **Multipart:** chuyển upload sang persistent storage trước khi request hoàn tất, rồi test listener chỉ dùng `objectKey`.
7. **Bảo mật:** gửi raw tenant header không đáng tin phải bị từ chối hoặc xác minh trước khi event được tạo.
8. **Transactions:** event gửi cho `AFTER_COMMIT` phải được publish trong transaction; test rollback để xác minh listener không chạy.
9. **Retry:** event ID/version xử lý trùng và đến trễ không gây side effect lặp.
10. **Leak:** không giữ request/session/response trong queue lâu; kiểm tra payload và event log với những loại dữ liệu nhạy cảm.

### Trường hợp test có web mock

Test dùng `MockMvc` giúp kiểm tra hành vi controller với Servlet request mock, nhưng **không chứng minh** một request thực bị container recycle ra sao. Để kiểm tra memory/lifecycle dưới tải, nên có integration test với web server thực, slow consumers và giới hạn concurrency; xem tracing/thread dumps/heap profile khi cần.

Đối với các listener dùng `@Async`, test cần latch, future hoặc Awaitility với timeout. Kiểm tra event output sau khi worker báo hoàn tất, không suy luận từ việc HTTP response đã trở về.

## 15. Chẩn đoán lỗi thường gặp

| Dấu hiệu | Nguyên nhân đáng kiểm tra | Cách sửa |
| --- | --- | --- |
| `No thread-bound request found` từ worker | `RequestContextHolder` không có binding trên executor thread | Không đọc request context trong async consumer; đưa dữ liệu vào immutable event |
| Request attribute khác lúc publish | Event chỉ giữ shared `HttpServletRequest` reference | Capture DTO snapshot trước publish |
| Exception khi đọc request/body sau response | Container đã cleanup hoặc stream đã bị tiêu thụ/đóng | Đọc/validate/copy dữ liệu trong request; worker chỉ nhận ID/DTO |
| `MultipartFile` không còn đọc được | File tạm được dọn sau request | Chuyển sang storage bền vững trước publish |
| Lỗi khi dùng `@RequestScope` bean trên worker | Request scope không hoạt động ngoài request-bound thread | Không chuyển request-scoped bean qua async |
| Thread pool thỉnh thoảng dùng context user khác | Inheritable ThreadLocal/binding không cleanup hoặc pool reuse | Không kế thừa raw request context; restore/remove đúng trong `finally` |
| MDC/trace ID biến mất | Logging context không auto-propagate | Dùng TaskDecorator/Context Propagation cho observability, hoặc event correlation ID |
| Tenant bị giả mạo | Snapshot từ raw `X-Tenant-Id` chưa được kiểm tra | Lấy tenant đã được xác thực và authorized |
| `AFTER_COMMIT` listener không chạy | Publish xảy ra ngoài transaction hoặc T1 rollback | Phát event bên trong đúng transaction; test cả commit/rollback |
| Cùng một job gửi email hai lần | Retry/duplicate event không idempotent | Event ID, unique key, outbox/durable retry |
| Heap tăng khi event queue đầy | Event giữ request object graph lớn | Payload tối thiểu, queue bounded, không cache Servlet request |
| Async listener chạy trên caller thread | Thiếu `@EnableAsync` hoặc self-invocation | Dùng Spring bean proxy/executor đúng cách |

## 16. Checklist thiết kế trước khi đưa event vào production

Trước khi publish từ HTTP request, hãy tự hỏi:

- Event đang chứa **Servlet object** hay chỉ các **giá trị bất biến**?
- Listener có thể chạy **sau response** hoặc **trên thread khác** không?
- Field nào cần cho nghiệp vụ, field nào chỉ phục vụ tracing? Có thể giảm payload không?
- Actor/tenant/resource đã qua **authentication + authorization** chưa?
- Có trường nhạy cảm như token, cookie, body, session hoặc PII không được đưa vào event không?
- Nếu listener cần file upload, file đã nằm ở **persistent storage** chưa?
- Nếu listener cần kết quả DB đã commit, event có được publish bên trong transaction đúng và xử lý ở `AFTER_COMMIT` chưa?
- Worker có cần transaction riêng, timeout, retry/idempotency hay outbox không?
- Nếu phải propagate trace/MDC, executor đã có **cơ chế context propagation và cleanup** thích hợp chưa?
- Test đã chứng minh snapshot không đổi khi request object được mutate/hoàn tất chưa?

**Kết luận:** `HttpServletRequest` là context của một lần xử lý HTTP, không phải payload đáng tin cho Application Event sống qua request hoặc đi sang executor. **Chụp DTO bất biến trước khi publish, truyền ID/metadata đã xác thực và để worker tự mở các tài nguyên, transaction cần thiết.** Context propagation có thể giúp observability trong những tình huống được hỗ trợ, nhưng không biến request object thành an toàn để giữ vô thời hạn.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — ApplicationContext Events và Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — `RequestContextHolder` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html)
- [Spring Framework 6.2 — `ServletRequestAttributes` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/context/request/ServletRequestAttributes.html)
- [Spring Framework 6.2 — Spring MVC Controller Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Framework 6.2 — Application Events Observability & Context Propagation](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Jakarta Servlet 6.0 — `ServletRequest` Interface](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/servletrequest)
