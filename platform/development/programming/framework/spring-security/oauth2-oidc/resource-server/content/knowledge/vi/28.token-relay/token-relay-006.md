# Ngữ cảnh xác thực khi chuyển sang tác vụ khác hoặc chuỗi bất đồng bộ

Trong một ứng dụng Spring Security Resource Server, request HTTP thường được xác thực trong security filter chain. Sau khi access token hợp lệ, Spring Security tạo một **Authentication** và đặt nó vào **SecurityContext** để controller, service và authorization rules sử dụng. Nhưng khi xử lý chuyển sang thread khác, executor, callback bất đồng bộ, Reactor pipeline hoặc background job, ngữ cảnh này có thể không còn sẵn có.

Đây là điểm quan trọng trong chương **Chuyển tiếp token**: **chuyển tiếp SecurityContext**, **chuyển tiếp access token** và **ủy quyền để gọi một dịch vụ khác** là ba việc liên quan nhưng không giống nhau. Copy ngữ cảnh xác thực sang thread khác không tự làm access token phù hợp với downstream API. Ngược lại, đưa raw token vào task hoặc message queue không phải cách an toàn để duy trì danh tính.

Bài học trình bày cách Spring Security lưu và truyền context trong Servlet và WebFlux, cách cấu hình executor cho `@Async`/`CompletableFuture`, cách dùng WebClient để relay Bearer token, giới hạn của Reactor Context, và cách xử lý background work kéo dài sau request. Trọng tâm là giữ đúng identity và quyền trong từng execution boundary, đồng thời tránh rò rỉ credential hoặc dùng nhầm token.

> **Ngữ cảnh minh họa:** Orders API chạy Spring Boot 3.x / Spring Security 6.x. API nhận access token từ caller, kiểm tra scope và có thể gọi Inventory API hoặc Billing API. Một số thao tác được thực hiện qua `@Async`, `CompletableFuture`, WebFlux `Mono`/`Flux` hoặc message queue. Ví dụ code là các mẫu kiến trúc; cần chọn đúng Servlet/WebFlux stack và đối chiếu API với phiên bản dự án.

## 1. Bốn khái niệm cần phân biệt

### 1.1. Authentication

`Authentication` biểu diễn kết quả xác thực hoặc một yêu cầu xác thực đang chờ xử lý. Trong Resource Server, ví dụ thường gặp:

- `JwtAuthenticationToken` khi access token là JWT.
- `BearerTokenAuthentication` khi access token opaque được xác minh qua introspection.

Một Authentication đã xác thực có thể chứa principal, authorities và thông tin token liên quan. Nó không phải một object vô hại: tùy loại Authentication, credentials hoặc token object có thể chứa bearer credential nhạy cảm.

### 1.2. SecurityContext

`SecurityContext` giữ `Authentication` hiện tại. Code ứng dụng thường đọc context qua:

- Servlet: `SecurityContextHolder`.
- WebFlux: `ReactiveSecurityContextHolder`.

SecurityContext trả lời câu hỏi: **execution hiện tại đang được thực hiện dưới danh tính nào?**

### 1.3. Access token

Access token là credential được gửi tới Resource Server hoặc downstream resource phù hợp. Nó có audience, scope, thời hạn và issuer. Việc có `Authentication` trong memory không tự chứng minh token còn hiệu lực hoặc phù hợp với một API khác.

### 1.4. Delegation và token relay

Khi Orders API gọi Inventory API, có thể:

- **Relay:** chuyển tiếp access token inbound hiện tại nếu token đó được cấp cho downstream resource và chính sách cho phép.
- **OAuth2 Client:** dùng authorized client riêng của Orders service để lấy token outbound.
- **Token exchange / on-behalf-of:** xin token mới dành cho downstream, đại diện user hoặc actor theo chính sách AS.
- **Workload identity:** gọi bằng danh tính service, không giả danh user.

Không lựa chọn một cách chỉ vì SecurityContext đang có sẵn.

| Khái niệm | Câu hỏi được giải quyết | Ví dụ |
|---|---|---|
| Authentication | Ai đã được xác thực? | `JwtAuthenticationToken` |
| SecurityContext | Authentication nào thuộc execution hiện tại? | Context trong request/thread/Reactor |
| Access token | Credential nào được gửi tới resource? | `Authorization: Bearer ...` |
| Token relay | Có thể chuyển tiếp token hiện tại tới downstream không? | WebClient bearer relay filter |
| Token exchange | AS có cấp token khác cho downstream không? | Token dành cho `inventory-api` |
| Workload identity | Service tự xác thực với AS như thế nào? | `client_credentials`, mTLS |

## 2. Vì sao ngữ cảnh xác thực có thể mất khi chạy bất đồng bộ?

Một request Servlet thường đi qua filter chain trên một thread:

```text
HTTP request
    |
    v
Security filter chain
    |
    v
Authenticate Bearer token
    |
    v
SecurityContextHolder
    |
    v
Controller
    |
    v
Service
    |
    v
Response
```

Trong Servlet stack mặc định, Spring Security lưu SecurityContext bằng `ThreadLocal` thông qua `SecurityContextHolderStrategy` mặc định. Thread xử lý request có context, nhưng thread pool xử lý task nền là thread khác.

Ví dụ:

```text
Request thread: http-nio-8080-exec-4
    SecurityContext = user-42
          |
          | submit task
          v
Worker thread: task-7
    SecurityContext = empty
```

Nếu code gọi `@Async`, `CompletableFuture.supplyAsync(...)`, `Executor.execute(...)` hoặc một thư viện tự tạo thread mà không có cơ chế truyền context, worker thread không tự kế thừa SecurityContext của request.

### 2.1. Thread pool làm vấn đề khó hơn

Thread pool tái sử dụng thread cho nhiều request:

```text
Worker thread task-7
    |
    +-- xử lý task của user A
    |
    +-- được trả lại pool
    |
    +-- xử lý task của user B
```

Nếu code tự `setContext(...)` mà không `clearContext()` trong `finally`, context của user A có thể tồn tại khi worker chạy task của user B. Đây là nguy cơ **cross-user context leakage**.

### 2.2. InheritableThreadLocal không phải giải pháp chung cho thread pool

Spring Security có thể cấu hình `MODE_INHERITABLETHREADLOCAL`, nhưng cơ chế này phù hợp hơn với thread con được tạo mới và kế thừa context lúc tạo. Với thread pool, thread thường đã được tạo trước khi task của request chạy; context của request không tự thay đổi theo mỗi task.

Vì vậy, không dùng `MODE_INHERITABLETHREADLOCAL` như cách bật propagation toàn cục cho mọi executor. Dùng wrapper executor có vòng đời set/restore/clear context rõ ràng.

## 3. Servlet SecurityContextHolder hoạt động thế nào?

Trong Servlet application, sau khi Bearer token được xác minh, Spring Security tạo Authentication và đặt vào SecurityContext. Code có thể đọc:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
```

Đây là cách đọc trong execution thread Servlet. Không nên lưu Authentication vào một field của singleton service:

```java
// KHÔNG DÙNG: singleton field dùng chung cho mọi request.
@Service
public class OrderService {
    private Authentication currentAuthentication;
}
```

Nhiều request có thể chạy đồng thời. Field dùng chung có thể bị ghi đè, khiến user A xử lý bằng identity của user B.

### 3.1. Context thuộc execution hiện tại, không phải thuộc singleton bean

Service Spring thường là singleton. Context phải được đọc khi method đang chạy, hoặc được truyền rõ ràng vào task. Không lưu context request vào field, static variable hoặc cache dùng chung.

### 3.2. Spring Security dọn context ở cuối request

Security filter chain quản lý việc thiết lập và dọn SecurityContext theo vòng đời request. Khi tự thay đổi `SecurityContextHolder`, code phải khôi phục context trước đó hoặc xóa context trong `finally`.

Không giữ Authentication sau request bằng cách copy vào một biến toàn cục.

## 4. Truyền SecurityContext sang Executor trong Servlet

Spring Security cung cấp wrapper để thực thi task với SecurityContext được chụp tại thời điểm submit. Hai lựa chọn thường gặp:

- `DelegatingSecurityContextExecutor` cho `Executor`.
- `DelegatingSecurityContextAsyncTaskExecutor` cho `AsyncTaskExecutor` và Spring `@Async`.

Wrapper thực hiện việc đặt context phù hợp trước khi chạy task và dọn/khôi phục context sau khi task kết thúc.

### 4.1. Cấu hình ThreadPoolTaskExecutor và DelegatingSecurityContextAsyncTaskExecutor

```java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
public class AsyncSecurityConfiguration {

    @Bean
    ThreadPoolTaskExecutor applicationDelegateExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("orders-async-");

        return executor;
    }

    @Bean(name = "taskExecutor")
    AsyncTaskExecutor taskExecutor(
            ThreadPoolTaskExecutor applicationDelegateExecutor) {

        return new DelegatingSecurityContextAsyncTaskExecutor(
            applicationDelegateExecutor
        );
    }
}
```

Trong cấu hình này:

1. `applicationDelegateExecutor` quản lý thread pool.
2. Bean tên `taskExecutor` là executor được bọc bằng Spring Security.
3. `@Async("taskExecutor")` yêu cầu đúng executor đã được bọc.
4. Wrapper truyền context của thread submit vào task.
5. Khi task hoàn thành, wrapper dọn context theo cơ chế của Spring Security.

Spring quản lý lifecycle của `ThreadPoolTaskExecutor` bean; không tạo một pool mới trong mỗi request.

### 4.2. Sử dụng với @Async

```java
package com.example.orders.application;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class OrderReportService {

    @Async("taskExecutor")
    public CompletableFuture<ReportResult> buildReport(
            String orderId) {

        // Có thể đọc SecurityContext trong task này
        // vì taskExecutor đã propagate context.
        ReportResult result = buildReportForCurrentActor(orderId);

        return CompletableFuture.completedFuture(result);
    }

    private ReportResult buildReportForCurrentActor(String orderId) {
        // Phần xử lý nghiệp vụ minh họa.
        return new ReportResult(orderId, "READY");
    }
}
```

`ReportResult` là DTO của ứng dụng. Method `@Async` cần được gọi qua Spring proxy từ một bean khác để async interception hoạt động.

### 4.3. Tự gọi method trong cùng bean không kích hoạt @Async như mong đợi

Ví dụ:

```java
@Service
public class ReportService {

    public void start() {
        this.buildAsync(); // Self-invocation: thường bypass proxy.
    }

    @Async("taskExecutor")
    public void buildAsync() {
        // ...
    }
}
```

Trong proxy-based Spring AOP, lời gọi `this.buildAsync()` không đi qua proxy nên `@Async` không được áp dụng. Tách async method sang bean khác hoặc gọi qua proxy được inject theo kiến trúc phù hợp.

## 5. DelegatingSecurityContextExecutor cho CompletableFuture

`CompletableFuture.supplyAsync(...)` mặc định thường dùng common ForkJoinPool nếu không truyền executor. Common pool không tự mang Servlet SecurityContext của request.

Không nên:

```java
CompletableFuture.supplyAsync(() -> {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

    return createReport(authentication);
});
```

Task có thể chạy trên thread không có context.

### 5.1. Truyền executor đã được bọc

```java
package com.example.orders.config;

import java.util.concurrent.Executor;
import java.util.concurrent.Executors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;

@Configuration
public class ReportExecutorConfiguration {

    @Bean(destroyMethod = "shutdown")
    Executor reportDelegateExecutor() {
        return Executors.newFixedThreadPool(8);
    }

    @Bean(name = "securityContextExecutor")
    Executor securityContextExecutor(Executor reportDelegateExecutor) {
        return new DelegatingSecurityContextExecutor(
            reportDelegateExecutor
        );
    }
}
```

Trong dự án thực tế, tránh inject `Executor` chung chung khi có nhiều bean cùng type; dùng `@Qualifier` hoặc tên bean rõ ràng để tránh chọn nhầm executor. Ví dụ trên minh họa wrapper; production nên cấu hình thread naming, bounded queue, shutdown và rejection policy.

### 5.2. Dùng executor rõ ràng trong CompletableFuture

```java
@Service
public class AsyncOrderFacade {

    private final Executor securityContextExecutor;

    public AsyncOrderFacade(
            @Qualifier("securityContextExecutor")
            Executor securityContextExecutor) {
        this.securityContextExecutor = securityContextExecutor;
    }

    public CompletableFuture<ReportResult> createReport(String orderId) {
        return CompletableFuture.supplyAsync(
            () -> createReportForCurrentActor(orderId),
            securityContextExecutor
        );
    }

    private ReportResult createReportForCurrentActor(String orderId) {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        return new ReportResult(
            orderId,
            authentication.getName()
        );
    }
}
```

Đoạn code cần imports `Authentication`, `SecurityContextHolder`, `Qualifier` và DTO. Nó chỉ minh họa propagation trong một task được submit từ request thread có context.

### 5.3. Với thenApplyAsync và các stage tiếp theo

Mỗi async stage cần executor được chọn rõ:

```java
CompletableFuture.supplyAsync(
        () -> loadOrder(orderId),
        securityContextExecutor
    )
    .thenApplyAsync(
        this::buildReport,
        securityContextExecutor
    );
```

Không giả định `thenApplyAsync(...)` sẽ dùng đúng executor hoặc context nếu bỏ đối số executor. Các stage không có hậu tố `Async` có thể chạy trên thread hoàn thành stage trước; không nên dựa vào ambient thread context của callback để thực hiện security-sensitive work.

Với pipeline nhiều stage, truyền actor context như một tham số bất biến thường dễ hiểu và dễ kiểm soát hơn việc phụ thuộc context ngầm ở mọi callback.

### 5.4. Delegating executor không biến context thành token outbound

Wrapper executor chỉ giúp task nhìn thấy SecurityContext. Nó không:

- Làm access token sống lâu hơn.
- Refresh access token.
- Đổi audience hoặc scope.
- Cấp quyền gọi downstream API.
- Biến JWT thành token exchange.
- Làm một task chạy lâu trở thành an toàn để giữ credential vô hạn.

Task vẫn phải dùng token đúng mục đích và kiểm tra authorization theo policy.

## 6. Không dùng ThreadLocal thủ công mà quên cleanup

Nếu cần viết một wrapper rất đặc thù, nguyên tắc tối thiểu là lưu context cũ, đặt context task, rồi khôi phục/xóa trong `finally`. Tuy nhiên, ưu tiên các wrapper của Spring Security thay vì tự viết.

Một ví dụ minh họa vì sao `finally` cần thiết:

```java
SecurityContext previous =
    SecurityContextHolder.getContext();

try {
    SecurityContextHolder.setContext(taskContext);
    task.run();
} finally {
    SecurityContextHolder.setContext(previous);
}
```

Đây chỉ là minh họa về cleanup; code thực tế cần xử lý trường hợp context trước đó rỗng và không nên tự chia sẻ một mutable SecurityContext giữa nhiều task. Các wrapper chính thức xử lý các chi tiết lifecycle và strategy tốt hơn.

Không làm:

```java
SecurityContextHolder.setContext(context);
executor.execute(task);
// Không có cleanup khi task hoàn tất.
```

Nếu context tồn tại trên pooled thread, task sau có thể kế thừa danh tính không đúng.

## 7. SecurityContext mutable và nguyên tắc truyền dữ liệu tối thiểu

`SecurityContext` và `Authentication` có thể là object mutable. Không sửa authorities/principal trong một context được chia sẻ giữa các task. Không gắn thêm thông tin tenant vào Authentication dùng chung sau khi đã publish sang executor.

Nếu task chỉ cần biết actor đã khởi tạo công việc, hãy tạo một object bất biến chứa thông tin tối thiểu:

```java
public record ActorContext(
    String issuer,
    String subject,
    String tenantId,
    String correlationId
) {}
```

Có thể trích object này trong request đã xác thực rồi truyền tường minh:

```java
ActorContext actor = actorContextFactory.fromCurrentAuthentication();

CompletableFuture<ReportResult> future =
    CompletableFuture.supplyAsync(
        () -> reportService.buildFor(actor, orderId),
        reportExecutor
    );
```

`ActorContext` là dữ liệu phục vụ audit/logic. Nó **không phải credential** và không tự thay thế authorization ở thời điểm task chạy. Nếu task cần truy cập dữ liệu nhạy cảm, cần kiểm tra quyền hiện hành hoặc dùng service identity/delegated token theo policy.

### 7.1. Không lưu raw access token vào actor DTO

Không thêm các field như:

```java
public record UnsafeActorContext(
    String userId,
    String accessToken,
    String refreshToken
) {}
```

Đưa token vào object truyền qua nhiều layer làm tăng số nơi có thể log, serialize, dump hoặc giữ token quá lâu. Chỉ giữ token trong thành phần có trách nhiệm gửi token và có lifecycle rõ.

### 7.2. Không lưu Authentication vào singleton field

Tránh:

```java
@Component
public class CurrentUserHolder {
    private Authentication authentication;
}
```

Singleton được nhiều request dùng chung. Authentication phải gắn với execution context hoặc truyền qua tham số của task, không gắn vào trạng thái dùng chung của bean.

## 8. WebFlux lưu SecurityContext trong Reactor Context

WebFlux không dùng `ThreadLocal` làm cơ chế mặc định để truyền security context qua reactive pipeline. Spring Security tích hợp SecurityContext với **Reactor Context**.

Đọc Authentication:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;

public Mono<Authentication> currentAuthentication() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
}
```

Trong reactive chain, context đi theo subscription. Các operator như `map`, `flatMap`, `publishOn` và `subscribeOn` không làm mất Reactor Context chỉ vì execution chuyển sang thread khác.

### 8.1. Thread thay đổi nhưng Reactor Context vẫn theo subscription

```text
HTTP request
    |
    v
WebFlux security filters
    |
    v
SecurityContext được ghi vào Reactor Context
    |
    v
Mono / Flux pipeline
    |
    +-- publishOn(Schedulers.parallel())
    |
    +-- flatMap(...)
    |
    +-- WebClient outbound call
    |
    v
Cùng subscription context được sử dụng
```

Reactor Context không phải ThreadLocal. Vì vậy, code không nên gọi `SecurityContextHolder.getContext()` trong một operator WebFlux rồi mong thấy authentication của request.

### 8.2. Không dùng SecurityContextHolder trong WebFlux reactive code

Sai:

```java
return orderRepository.findById(orderId)
    .map(order -> {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        return authorize(order, authentication);
    });
```

Thread đang chạy operator có thể không phải thread request ban đầu và `SecurityContextHolder` có thể rỗng hoặc không đại diện request hiện tại.

Đúng:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .zipWith(orderRepository.findById(orderId))
    .map(tuple -> authorize(
        tuple.getT2(),
        tuple.getT1()
    ));
```

Hoặc truyền Authentication/ActorContext rõ ràng từ một bước đã đọc context.

### 8.3. contextWrite không phải cách cấp danh tính tùy tiện

Reactor cho phép ghi context theo subscription. Spring Security có helper `ReactiveSecurityContextHolder.withAuthentication(...)`. API này hữu ích cho test hoặc integration có chủ đích, nhưng không dùng để tự tạo Authentication từ request header chưa xác minh.

Không làm:

```java
return service.call()
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(
            new UsernamePasswordAuthenticationToken(
                request.getUser(),
                "N/A",
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
            )
        )
    );
```

Đoạn này biến dữ liệu caller gửi thành danh tính/authority. Authentication phải được tạo bởi cơ chế xác thực đáng tin cậy, rồi mới được đưa vào SecurityContext.

## 9. Reactive chain tự giữ context; detached subscription thì không

Trong WebFlux, hãy giữ công việc trong cùng một publisher:

```java
public Mono<OrderSummary> summarize(String orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            inventoryClient.getAvailability(order)
                .map(availability ->
                    toSummary(order, availability)
                )
        );
}
```

Nếu `inventoryClient` dùng WebClient và DPoP/Bearer relay filter đúng, nó có thể đọc security context từ Reactor Context của cùng subscription.

### 9.1. Không gọi subscribe() rời trong service

Sai:

```java
public Mono<Void> processOrder(String orderId) {
    inventoryClient.update(orderId)
        .subscribe();

    return Mono.empty();
}
```

Lệnh `subscribe()` tạo subscription độc lập. Nó tách công việc khỏi pipeline của caller, làm khó quản lý lỗi/cancellation/lifecycle và có thể không mang context như mong đợi. Controller hoặc framework thường là nơi subscribe vào publisher được trả về.

Đúng:

```java
public Mono<Void> processOrder(String orderId) {
    return inventoryClient.update(orderId);
}
```

Nếu cần chạy side effect, biểu diễn nó trong pipeline và để caller/framework quản lý subscription.

### 9.2. Không block để lấy Authentication

Sai:

```java
Authentication authentication =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .block();
```

`block()` có thể chặn event loop và làm mất cấu trúc reactive. Dùng `flatMap`, `zipWhen`, `deferContextual` hoặc truyền dữ liệu tường minh.

### 9.3. Mono/Flux được tạo trước request context

Một publisher lạnh có thể được tạo ở một nơi và subscribe ở nơi khác. SecurityContext thuộc **subscription hiện tại**, không phải một field gắn cố định vào object `Mono`. Vì vậy, đừng cache một publisher chứa dữ liệu user-specific rồi chia sẻ cho nhiều request.

Dùng `Mono.defer(...)`/`Flux.defer(...)` khi cần đọc context ở thời điểm subscribe, và tránh lưu Authentication vào field.

## 10. Ranh giới Reactor sang Executor hoặc CompletableFuture

Reactor Context được giữ qua operator trong cùng reactive subscription. Khi chuyển sang API imperative hoặc executor độc lập, cần quyết định dữ liệu nào được mang qua.

Ví dụ không tốt:

```java
return orderRepository.findById(orderId)
    .doOnNext(order -> {
        CompletableFuture.runAsync(
            () -> auditService.record(order)
        );
    })
    .then();
```

`CompletableFuture.runAsync` không tự tham gia Reactor Context. Nó thường dùng common pool và có thể chạy mà không có security context.

### 10.1. Ưu tiên giữ công việc reactive

Nếu downstream có reactive client, hãy nối publisher vào cùng pipeline:

```java
return orderRepository.findById(orderId)
    .flatMap(order ->
        auditClient.record(order)
    );
```

Đây là cách đơn giản nhất để giữ context và error propagation trong WebFlux.

### 10.2. Nếu phải gọi imperative task, truyền ActorContext tường minh

Đọc actor từ Reactor Context rồi truyền vào task:

```java
public Mono<ReportResult> createReport(String orderId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(actorContextFactory::from)
        .flatMap(actor ->
            Mono.fromFuture(
                reportExecutor.submit(actor, orderId)
            )
        );
}
```

`reportExecutor.submit(...)` và `ActorContextFactory` là API ứng dụng minh họa. `ActorContext` cần immutable và không chứa raw bearer/refresh token.

Nếu task cần gọi API thay mặt user, phải có cơ chế delegation phù hợp; chỉ truyền subject hoặc tenant ID không biến task thành một OAuth client được ủy quyền.

### 10.3. Context propagation library không thay security design

Các hệ sinh thái có thể dùng Micrometer Context Propagation hoặc tích hợp context snapshot để bridge ThreadLocal/Reactor Context. Những công cụ này giúp truyền dữ liệu context qua boundary, nhưng không tự xác định context nào được phép truyền, có nên mang raw token không, task còn thuộc request ban đầu không, user authorization còn hợp lệ lúc task chạy không hoặc downstream audience/scope có phù hợp không.

Chỉ bật automatic context propagation khi đã xác định rõ context keys, lifecycle và dữ liệu nhạy cảm.

## 11. Chuyển tiếp Bearer token bằng WebClient trong Servlet

Khi downstream API chấp nhận chính access token inbound và token có audience/scope phù hợp, Spring Security cung cấp `ServletBearerExchangeFilterFunction`.

Ví dụ:

```java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServletBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class DownstreamClientConfiguration {

    @Bean
    WebClient inventoryWebClient() {
        return WebClient.builder()
            .baseUrl("https://inventory.internal.example")
            .filter(new ServletBearerExchangeFilterFunction())
            .build();
    }
}
```

Filter function đọc Authentication hiện tại trong Servlet SecurityContext. Khi Authentication đại diện cho OAuth2 access token phù hợp, nó thêm Bearer token vào outbound request.

### 11.1. Điều kiện để relay hoạt động trong async task

Trong request thread, `SecurityContextHolder` có Authentication nên filter function có thể lấy token.

Nếu WebClient được gọi trong `@Async` hoặc `CompletableFuture` trên thread khác, context phải được truyền bằng executor đã bọc. Nếu không, filter không thấy Authentication của caller và không thể relay token như mong đợi.

### 11.2. Filter relay không refresh token

`ServletBearerExchangeFilterFunction` chỉ chuyển tiếp access token hiện có. Nó không gọi token endpoint, dùng refresh token, thay đổi audience, tăng scope, đổi token sang DPoP/mTLS hoặc đảm bảo downstream chấp nhận token.

Nếu token hết hạn, downstream có thể trả 401. Việc lấy token mới thuộc OAuth2 Client/Authorization Server flow.

### 11.3. Chỉ relay khi downstream thực sự được phép nhận token

Không chuyển tiếp access token inbound tới mọi WebClient. Token có thể dành cho `orders-api`, không dành cho `inventory-api`. Nếu downstream audience khác, token có thể bị từ chối hoặc tạo rủi ro token substitution.

Chỉ relay nếu AS đã cấp token cho đúng resource hoặc trust contract cho phép nhiều resource. Nếu không, dùng token exchange hoặc service identity.

## 12. Chuyển tiếp Bearer token trong WebFlux

Với WebFlux, thành phần tương ứng là `ServerBearerExchangeFilterFunction`.

```java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReactiveDownstreamClientConfiguration {

    @Bean
    WebClient inventoryWebClient() {
        return WebClient.builder()
            .baseUrl("https://inventory.internal.example")
            .filter(new ServerBearerExchangeFilterFunction())
            .build();
    }
}
```

Filter này sử dụng Authentication trong reactive security context của subscription để relay Bearer access token khi phù hợp.

### 12.1. WebClient call phải ở cùng reactive chain

```java
public Mono<Availability> check(String sku) {
    return inventoryWebClient.get()
        .uri("/api/availability/{sku}", sku)
        .retrieve()
        .bodyToMono(Availability.class);
}
```

Khi method này được gọi trong cùng reactive chain của request đã xác thực, Reactor Context được truyền theo subscription và filter có thể lấy token.

### 12.2. Không tạo subscription mới bên trong WebClient wrapper

Tránh tự `subscribe()` trong filter hoặc service. Để WebClient trả publisher cho caller. Như vậy lỗi 401/403, cancellation, timeout và context được quản lý trong một luồng.

### 12.3. Servlet và WebFlux dùng filter khác nhau

| Ứng dụng | Filter |
|---|---|
| Servlet MVC | `ServletBearerExchangeFilterFunction` |
| Spring WebFlux | `ServerBearerExchangeFilterFunction` |

Không dùng Servlet filter function trong reactive application và không dùng WebFlux filter function trong Servlet request context. Hai implementation lấy SecurityContext từ hai mô hình khác nhau.

## 13. Token relay không phải token exchange

Giả sử client gửi token dành cho Orders API:

```json
{
  "iss": "https://login.example.com",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Orders API gọi Inventory API. Nếu Inventory API yêu cầu `aud=inventory-api`, token inbound không tự phù hợp.

Có ba hướng:

1. **Relay token:** dùng cùng access token khi downstream được phép nhận token đó.
2. **Client credentials:** Orders service gọi Inventory với identity của service.
3. **Token exchange/on-behalf-of:** AS cấp token mới cho Inventory, có subject/actor delegation phù hợp.

### 13.1. Relay token

```text
Caller --access token A--> Orders API
Orders API --same token A--> Inventory API
```

Chỉ dùng khi audience, scope, issuer, trust boundary và delegation policy cho phép. Token relay không thay đổi token.

### 13.2. Client credentials

```text
Orders service --client authentication--> Authorization Server
Authorization Server --service access token--> Orders service
Orders service --service token--> Inventory API
```

Downstream thấy workload identity của Orders service. Nếu cần phân quyền theo user, phải có policy riêng hoặc delegation mechanism.

### 13.3. Token exchange

RFC 8693 định nghĩa OAuth 2.0 Token Exchange. Orders service có thể dùng subject token/actor token theo contract để xin token mới cho downstream resource. AS kiểm tra quyền delegation và phát token phù hợp.

Token exchange không phải việc Resource Server tự sửa `aud` hoặc `scope` trong JWT. Chỉ AS có quyền cấp token mới theo chính sách.

## 14. Khi nào không nên relay access token inbound?

Không relay token một cách tự động khi:

- Downstream có audience khác.
- Token không có scope cần thiết.
- Downstream không thuộc trust boundary được phép nhận token.
- Downstream là bên thứ ba hoặc host do user điều khiển.
- Token có sender constraint như DPoP/mTLS nhưng downstream không thể đáp ứng.
- Task chạy lâu và token có thể hết hạn.
- Caller đã bị logout/revoked nhưng job còn chờ.
- Service cần workload identity riêng.
- Việc relay làm lộ token qua logs/proxies hoặc hệ thống observability.

### 14.1. Không gửi token tới URL tùy ý

Không viết code nhận URL downstream từ request rồi gắn Authorization header vào:

```java
// CỐ Ý SAI: có thể gửi bearer token tới host do caller chọn.
webClient.get()
    .uri(request.getParameter("callbackUrl"))
    .headers(headers -> headers.setBearerAuth(accessToken))
    .retrieve();
```

Đây là nguy cơ credential exfiltration/SSRF. Downstream endpoint phải được cấu hình hoặc allowlist, không lấy từ input chưa tin.

### 14.2. Token relay có thể làm lộ quyền rộng hơn cần thiết

Nếu access token inbound chứa `orders.read`, không có nghĩa mọi downstream đều được phép nhận token đó. Phải xem xét principle of least privilege, resource indicators/audience, scope và service boundary.

## 15. Tác vụ bất đồng bộ ngắn trong request và background job dài hạn

Hai loại công việc cần được phân biệt.

### 15.1. Async ngắn, thuộc cùng request

Ví dụ tạo report trong vài giây rồi trả kết quả cho request đang mở. Có thể truyền SecurityContext qua executor nếu task thực sự cần thực thi dưới caller identity.

Cần bảo đảm:

- Executor được bọc.
- Task có timeout và queue bounded.
- Task không giữ context lâu hơn cần thiết.
- Token còn hiệu lực trong lúc outbound call.
- Cancellation/error được trả về đúng request.
- Không ghi token vào task result hoặc logs.

### 15.2. Background job sống độc lập với request

Ví dụ caller gửi yêu cầu export, API trả `202 Accepted`, job chạy sau vài phút hoặc vài giờ. Không nên giữ nguyên SecurityContext và bearer token của request trong queue để chạy vô thời hạn.

Lý do:

- Access token có thể hết hạn trước khi job chạy.
- User có thể bị disable hoặc quyền/tenant membership thay đổi.
- Refresh token thuộc OAuth client, không phải worker.
- Queue payload thường được persist/replicate/inspect.
- Job có thể chạy trên host hoặc worker khác.
- Context cũ có thể không còn phù hợp với trạng thái hiện tại.

### 15.3. Pattern phù hợp cho background job

```text
HTTP request
   |
   v
Authenticate caller
   |
   v
Authorize creation of job
   |
   v
Create immutable job command:
  jobId, actorId, tenantId, requestedOperation,
  resourceIds, correlationId, createdAt
   |
   v
Persist + enqueue command (no raw tokens)
   |
   v
Worker receives job
   |
   v
Authenticate as workload/service
   |
   v
Re-check current policy and resource state
   |
   v
Execute job
   |
   v
Audit initiatedBy=actorId
```

Actor metadata trong job giúp audit “ai đã khởi tạo”, nhưng worker vẫn xác thực bằng workload identity và áp dụng policy tại thời điểm thực thi.

### 15.4. Nếu cần giữ quyền delegated của user

Nếu job cần thực sự hoạt động thay mặt user, phải có một delegation design rõ:

- OAuth Token Exchange để cấp token downstream có audience/scope giới hạn.
- Grant/job authorization record có expiry, scope và tenant ràng buộc.
- Delegated credential được lưu trong vault/secure store với lifecycle rõ ràng nếu provider hỗ trợ.
- Kiểm tra lại user/grant/job state trước khi thực hiện.

Không serialize `SecurityContext` hoặc raw refresh token vào message queue để thay cho delegation protocol.

## 16. Queue và message listener không tự có request SecurityContext

Khi message được publish, execution hiện tại có thể có SecurityContext. Nhưng message consumer thường chạy trong một process/thread khác và không có HTTP request gốc.

Không giả định:

```java
@KafkaListener(topics = "order-export")
public void consume(ExportCommand command) {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
}
```

sẽ nhận Authentication của HTTP caller. Consumer cần workload identity hoặc một cơ chế message security riêng.

### 16.1. Payload event nên chứa actor metadata tối thiểu

Ví dụ:

```json
{
  "eventId": "evt-1024",
  "jobId": "job-77",
  "initiatedBy": {
    "issuerId": "company-idp",
    "subject": "customer-42",
    "tenantId": "tenant-a"
  },
  "operation": "ORDER_EXPORT",
  "resourceIds": ["order-42", "order-43"],
  "correlationId": "corr-abc"
}
```

Đây là event metadata, không phải credential. Consumer cần xác thực message broker/source và không coi `initiatedBy` do bất kỳ publisher nào gửi là danh tính đã xác minh.

### 16.2. Broker trust và event integrity

- Xác thực producer/consumer với broker.
- Phân quyền topic và consumer group.
- Dùng message schema/version rõ ràng.
- Bảo vệ event integrity theo trust boundary.
- Không đưa access/refresh token vào payload.
- Chống duplicate delivery bằng idempotency/event ID.
- Audit actor metadata như dữ liệu provenance, không thay identity của worker.

### 16.3. Re-authorization ở thời điểm xử lý

Nếu user bị thu hồi quyền sau khi job được enqueue nhưng trước khi chạy, policy cần quyết định:

- Job đã được authorize và chấp nhận tại thời điểm tạo thì có tiếp tục không?
- Hay cần kiểm tra lại quyền hiện tại?
- Job có expiry/cancel state không?
- Tenant/resource có còn tồn tại và thuộc đúng actor không?

Không dùng snapshot Authentication cũ để bỏ qua chính sách mới nếu nghiệp vụ yêu cầu quyền phải còn hiệu lực tại thời điểm thực thi.

## 17. WebClient trong @Async: phối hợp context và token relay

Một ứng dụng Servlet có thể gọi WebClient từ `@Async`. Để relay inbound Bearer token, cần cả hai điều kiện:

1. Executor truyền Servlet SecurityContext sang worker thread.
2. WebClient có `ServletBearerExchangeFilterFunction`.

Ví dụ:

```java
@Service
public class AsyncInventoryService {

    private final WebClient inventoryWebClient;

    public AsyncInventoryService(
            @Qualifier("inventoryWebClient")
            WebClient inventoryWebClient) {
        this.inventoryWebClient = inventoryWebClient;
    }

    @Async("taskExecutor")
    public CompletableFuture<Availability> check(String sku) {
        Availability result = inventoryWebClient.get()
            .uri("/api/availability/{sku}", sku)
            .retrieve()
            .bodyToMono(Availability.class)
            .block();

        return CompletableFuture.completedFuture(result);
    }
}
```

Đây là ví dụ Servlet async, không phải WebFlux service. `block()` ở đây có thể phù hợp nếu method đang chạy trên worker thread riêng và WebClient call được quản lý có timeout; không copy mẫu này vào Netty event loop hoặc reactive handler. Với code thuần reactive, trả `Mono` và không block.

Trong production, cần đặt connect/response timeout, bounded executor, cancellation policy và xử lý lỗi downstream. Nếu không cần imperative boundary, giữ publisher reactive sẽ đơn giản hơn.

### 17.1. Điều gì xảy ra nếu thiếu DelegatingSecurityContextAsyncTaskExecutor?

Task vẫn chạy nhưng `ServletBearerExchangeFilterFunction` có thể không thấy Authentication trong `SecurityContextHolder`. Outbound request không có Bearer token hoặc thất bại theo cấu hình. Không khắc phục bằng cách đưa raw token vào singleton field.

### 17.2. Điều gì xảy ra nếu token hết hạn giữa request và task?

Context propagation không kéo dài token. Downstream có thể từ chối token. Client/BFF cần một OAuth2 Client manager hoặc token exchange phù hợp; Resource Server không tự refresh token inbound.

## 18. Token relay trong WebFlux chain

Trong WebFlux, dùng `ServerBearerExchangeFilterFunction` và giữ outbound call trong cùng subscription:

```java
@Service
public class ReactiveInventoryService {

    private final WebClient inventoryWebClient;

    public ReactiveInventoryService(
            @Qualifier("inventoryWebClient")
            WebClient inventoryWebClient) {
        this.inventoryWebClient = inventoryWebClient;
    }

    public Mono<Availability> check(String sku) {
        return inventoryWebClient.get()
            .uri("/api/availability/{sku}", sku)
            .retrieve()
            .bodyToMono(Availability.class);
    }
}
```

Nếu gọi `check(...)` từ reactive request pipeline, Reactor Context được duy trì và filter có thể relay Bearer token phù hợp.

Không tạo `CompletableFuture` hoặc `new Thread(...)` trong method này nếu muốn giữ reactive context tự nhiên.

### 18.1. publishOn và subscribeOn

`publishOn`/`subscribeOn` thay đổi scheduler/thread thực thi, nhưng Reactor Context thuộc subscription nên vẫn được truyền qua các operator Reactor. Điều này khác Servlet ThreadLocal.

Tuy vậy, nếu bên trong operator gọi một API imperative đọc `SecurityContextHolder`, context không tự trở thành ThreadLocal. Dùng reactive APIs hoặc một bridge context propagation đã được cấu hình.

## 19. OAuth2 Client manager cho outbound token riêng

Khi inbound access token không phù hợp downstream, backend có thể là OAuth2 Client và dùng `OAuth2AuthorizedClientManager` (Servlet) hoặc `ReactiveOAuth2AuthorizedClientManager` (WebFlux).

Manager có thể chọn client registration, thực hiện client credentials hoặc authorization code flow, refresh authorized client outbound nếu có refresh token hợp lệ, và lưu authorized client theo principal/service context.

Đây là token của **authorized client outbound**, không phải token caller inbound tự động chuyển thành token downstream.

### 19.1. Khi dùng service identity

Orders service có thể dùng `client_credentials` để gọi Inventory API. Khi đó downstream nhận service principal. Nếu cần kiểm tra user khởi tạo, truyền actor metadata riêng cho audit hoặc dùng delegation/token exchange theo policy.

### 19.2. Khi dùng on-behalf-of/token exchange

Nếu downstream cần quyền delegated của user, AS có thể cấp token mới có audience/scope phù hợp. Token exchange phải được thực hiện bởi client được phép và có policy rõ về subject token, actor, audience, scope và tenant.

Không tự decode JWT rồi đổi claim `aud` thành downstream audience. Chỉ AS mới phát hành token mới.

## 20. DPoP và sender-constrained token khi chuyển tiếp

Nếu inbound access token được ràng buộc với DPoP key, chỉ chuyển tiếp raw token như Bearer là sai. Downstream request cần proof phù hợp với key được token ràng buộc, downstream HTTP method, target URI, exact access token, `iat`, `jti`, nonce và replay rules.

Proof của request inbound không thể tái sử dụng cho downstream vì `htu`/`htm` khác và `ath` có thể gắn với token khác. Một DPoP-aware client phải tạo proof mới cho downstream theo protocol.

Với mTLS-bound token, downstream connection cần certificate/private key phù hợp với `cnf` binding. Không relay token qua một connection không có sender identity tương ứng.

Nếu không thể đáp ứng sender constraint, dùng token exchange/workload identity phù hợp thay vì hạ token xuống Bearer.

## 21. Context propagation và cancellation/timeout

Task bất đồng bộ cần lifecycle rõ:

- Request bị client disconnect thì task có tiếp tục không?
- Task có thể bị cancel không?
- Task chạy tối đa bao lâu?
- Nếu downstream timeout, có retry không?
- Task có giữ context/token lâu hơn cần thiết không?
- Khi user bị logout/revoke, task đang chạy có dừng không?
- Async exception được trả về HTTP response hay ghi vào job status?

Với `CompletableFuture`, gắn timeout/cancellation theo use case và không để thread pool bị lấp đầy bởi task chờ vô hạn.

Với Reactor, giữ publisher trong pipeline để cancellation được truyền. Dùng timeout operator phù hợp và xử lý lỗi upstream/downstream.

Với background job trả `202 Accepted`, request HTTP đã kết thúc; không cố ghi response sau đó. Lưu trạng thái job và cho client poll/subscribe qua endpoint được bảo vệ.

## 22. Error handling và audit khi chạy dưới danh tính caller

Một async task có thể thất bại sau khi request ban đầu đã trả response. Hệ thống cần ghi rõ:

- `jobId`/correlation ID.
- Actor đã khởi tạo.
- Tenant và resource scope liên quan.
- Execution identity của worker.
- Policy decision tại thời điểm submit và execute.
- Error category, không phải raw token/claim nhạy cảm.
- Thời điểm và retry count.

Phân biệt:

- **Initiator:** user/service đã yêu cầu công việc.
- **Executor:** workload identity thực sự chạy công việc.
- **Delegated subject:** danh tính mà token exchange/delegation cho phép đại diện.

Không ghi mọi log như thể worker là user nếu worker đang dùng service identity. Audit cần thể hiện cả initiator lẫn executor.

## 23. Kiểm thử Servlet context propagation

### 23.1. Test task thấy Authentication

Một test có thể cài SecurityContext giả rồi submit task qua `DelegatingSecurityContextExecutor`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SecurityContextExecutorTest {

    @Test
    void propagatesContextToWorkerTask() throws Exception {
        ExecutorService delegate =
            Executors.newSingleThreadExecutor();

        try {
            var executor =
                new DelegatingSecurityContextExecutor(delegate);

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();

            context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                    "user-42",
                    "N/A",
                    java.util.List.of()
                )
            );

            SecurityContextHolder.setContext(context);

            Future<String> future = submit(executor);

            assertEquals("user-42", future.get());
        } finally {
            SecurityContextHolder.clearContext();
            delegate.shutdown();
        }
    }

    private Future<String> submit(java.util.concurrent.Executor executor)
            throws Exception {
        var result = new java.util.concurrent.CompletableFuture<String>();

        executor.execute(() ->
            result.complete(
                SecurityContextHolder.getContext()
                    .getAuthentication()
                    .getName()
            )
        );

        return result;
    }
}
```

Đây là test fragment minh họa. Trong test thực tế cần chờ executor shutdown đúng cách, tránh để context tồn tại qua test, và dùng test authentication phù hợp.

### 23.2. Test context không rò sang task tiếp theo

Với single-thread executor:

1. Submit task dưới user A.
2. Task kết thúc.
3. Submit task thứ hai không có context.
4. Xác nhận task thứ hai không nhìn thấy Authentication của A.

Test này kiểm tra wrapper cleanup, không chỉ kiểm tra propagation thành công.

### 23.3. Test @Async qua Spring proxy

Test integration cần gọi async method từ bean khác và chờ Future. Nếu gọi `this.asyncMethod()` trong cùng bean, test có thể không đi qua proxy và không xác minh được cấu hình `@Async`.

## 24. Kiểm thử WebFlux Reactor Context

Có thể dùng `StepVerifier` và `ReactiveSecurityContextHolder.withAuthentication(...)` để cài context test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveSecurityContextTest {

    @Test
    void readsAuthenticationFromReactorContext() {
        var authentication =
            UsernamePasswordAuthenticationToken.authenticated(
                "user-42",
                "N/A",
                java.util.List.of()
            );

        Mono<String> currentUser =
            ReactiveSecurityContextHolder.getContext()
                .map(context ->
                    context.getAuthentication().getName()
                )
                .publishOn(reactor.core.scheduler.Schedulers.parallel());

        StepVerifier.create(
                currentUser.contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(authentication)
                )
            )
            .expectNext("user-42")
            .verifyComplete();
    }
}
```

Test chứng minh Reactor Context được đọc qua scheduler switch. Nó không chứng minh JWT signature hoặc DPoP proof được xác minh; các tầng đó cần test riêng.

### 24.1. Test detached subscription không được coi là context propagation

Tạo một `subscribe()` rời rồi kiểm tra behavior có thể khó ổn định vì thread/scheduler. Thay vào đó, test kiến trúc bằng cách đảm bảo service trả publisher, không tự subscribe; kiểm tra WebClient outbound filter chạy trong cùng chain và nhận đúng authentication.

## 25. Kiểm thử token relay và token boundary

| Test | Điều cần chứng minh |
|---|---|
| Servlet request có Bearer token | WebClient relay filter chuyển tiếp token theo cấu hình |
| Servlet `@Async` có wrapped executor | Filter thấy SecurityContext trong worker |
| Servlet `@Async` dùng raw executor | Không giả định context có mặt |
| WebFlux cùng Reactor chain | Server bearer relay filter đọc context |
| WebFlux detached subscription | Không phụ thuộc context request cũ |
| Token audience sai downstream | Downstream từ chối hoặc không relay theo policy |
| Token hết hạn trong task | Không tự refresh bởi relay filter |
| DPoP-bound token | Không hạ xuống Bearer hoặc reuse inbound proof |
| Background queue job | Không có raw token trong payload |
| Token exchange | Token mới có audience/scope phù hợp |
| Worker identity | Audit phân biệt initiator và executor |

Không chỉ assert outbound request có header Authorization. Cần assert **đúng token**, đúng host, đúng resource, không bị gửi tới endpoint ngoài allowlist và không xuất hiện trong logs.

## 26. Các anti-pattern thường gặp

1. **Giả định @Async tự truyền SecurityContext:** sai với executor không được bọc. Dùng `DelegatingSecurityContextAsyncTaskExecutor` hoặc truyền actor context tường minh.
2. **Dùng commonPool mặc định cho CompletableFuture:** sai nếu task cần Servlet SecurityContext. Truyền executor đã được bọc hoặc không dựa vào context ngầm.
3. **Bật MODE_INHERITABLETHREADLOCAL để sửa mọi thread pool:** sai vì thread pool tái sử dụng thread; inheritance không theo từng task và có thể gây stale context.
4. **Đọc SecurityContextHolder trong WebFlux:** sai vì WebFlux dùng Reactor Context. Dùng `ReactiveSecurityContextHolder`.
5. **subscribe() rời trong reactive service:** sai vì tách subscription, error/cancellation/context và lifecycle khỏi request pipeline.
6. **block() trên Netty event loop:** sai vì chặn event loop. Giữ reactive chain.
7. **Lưu Authentication trong singleton field:** sai vì nhiều request có thể ghi đè và lẫn identity.
8. **Đưa raw access/refresh token vào queue:** sai vì queue, DLQ, backup và consumer logs mở rộng bề mặt lộ credential.
9. **Coi SecurityContext propagation là token exchange:** sai vì propagation chỉ truyền context; không thay audience, scope hoặc cấp token mới.
10. **Relay token tới mọi downstream:** sai vì token có thể sai audience, trust boundary hoặc sender constraint.
11. **Cho rằng token relay tự refresh:** sai. Bearer exchange filter chỉ chuyển tiếp token hiện có.
12. **Dùng DPoP proof inbound cho downstream:** sai vì proof gắn với method/URI/token của request inbound.
13. **Giữ SecurityContext sau khi request đã kết thúc:** sai vì task dài hạn có thể chạy bằng quyền cũ, token hết hạn và user đã bị thu hồi quyền.
14. **Ghi log Authentication/toString():** sai vì object có thể chứa claims/credentials.

## 27. Quy trình lựa chọn cách truyền context

**Bước 1 — Xác định execution model.**

- Servlet thread?
- `@Async`/Executor?
- `CompletableFuture`?
- WebFlux Reactor chain?
- Queue/background worker?

**Bước 2 — Xác định task cần dữ liệu gì.**

- Chỉ cần actor ID để audit?
- Cần authorization dưới caller identity?
- Cần access token outbound?
- Cần token dành cho resource khác?
- Cần workload identity?

**Bước 3 — Chọn cách truyền phù hợp.**

| Nhu cầu | Cách xử lý |
|---|---|
| Servlet async ngắn cần context hiện tại | `DelegatingSecurityContextAsyncTaskExecutor` |
| Executor/CompletableFuture Servlet | `DelegatingSecurityContextExecutor` |
| WebFlux reactive chain | Giữ cùng Reactor pipeline/Context |
| WebFlux sang imperative task | Truyền ActorContext rõ ràng hoặc bridge được kiểm soát |
| Outbound cùng token/audience phù hợp | Servlet/Server Bearer Exchange filter |
| Outbound token khác resource | OAuth2 Client hoặc token exchange |
| Background job độc lập | Message command + workload identity + re-authorization |
| DPoP/mTLS-bound token | Dùng sender-constrained client đúng protocol, không relay raw như Bearer |

**Bước 4 — Kiểm tra trust boundary.**

- Destination có allowlist không?
- Token có audience phù hợp không?
- Scope có đủ không?
- Có sender constraint không?
- Có thể lộ token trong logs/proxy/queue không?
- Task có sống lâu hơn request/token không?

**Bước 5 — Kiểm thử lifecycle.**

- Context có được đặt trước task không?
- Có được clear/restore sau task không?
- Có lẫn giữa hai user không?
- Error/cancellation có cleanup không?
- Async boundary có còn đúng security context không?
- Token relay có gửi đúng token tới đúng downstream không?

## 28. Checklist vận hành

| Hạng mục | Điều cần bảo đảm |
|---|---|
| Servlet async executor | Được bọc bằng Delegating Security Context executor khi cần context |
| `@Async` | Gọi qua proxy và chỉ định đúng executor |
| CompletableFuture | Không dùng commonPool mặc định khi cần context |
| Thread pool | Bounded, có lifecycle/rejection policy |
| Context cleanup | Không rò context sang task tiếp theo |
| Mutable context | Không sửa SecurityContext/Authentication chia sẻ |
| WebFlux | Dùng Reactor Context APIs |
| Reactive pipeline | Không detached subscribe/block |
| WebClient Servlet | Dùng Servlet bearer relay đúng khi được phép |
| WebClient WebFlux | Dùng Server bearer relay đúng khi được phép |
| Token audience | Phù hợp downstream |
| Scope/tenant | Được kiểm tra độc lập |
| Refresh | Không do Resource Server bearer relay filter thực hiện |
| Token exchange | Thực hiện qua AS được tin cậy |
| Queue payload | Không chứa raw access/refresh token |
| Background worker | Workload identity và re-authorization |
| DPoP/mTLS | Giữ sender constraint đúng protocol |
| Logging | Không ghi token, proof hoặc full Authentication |
| Audit | Phân biệt initiator, executor và delegated subject |
| Tests | Có context propagation, cleanup, token relay và cross-user isolation |

## 29. Tài liệu tham khảo

- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html): `DelegatingSecurityContextRunnable`, executor wrappers và context propagation trong Servlet.
- [Spring Security — Servlet OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Bearer authentication và `ServletBearerExchangeFilterFunction`.
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html): Bearer authentication trong WebFlux và `ServerBearerExchangeFilterFunction`.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): authorized client và token lifecycle cho outbound calls.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): `ReactiveOAuth2AuthorizedClientManager` và WebClient integration.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): context gắn với subscription, không gắn với thread.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer access token usage và security considerations.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): token exchange và delegation giữa resource servers.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access token và proof-of-possession.
- [OWASP API Security Top 10](https://owasp.org/API-Security/): authorization, credential exposure và API trust boundaries.

**Kết luận:** SecurityContext phải được truyền theo đúng execution model: Servlet dùng executor wrapper như `DelegatingSecurityContextAsyncTaskExecutor`, WebFlux giữ cùng Reactor Context trong một reactive subscription. Token relay chỉ chuyển tiếp access token hiện có; nó không refresh, không đổi audience và không cấp quyền downstream. Với background job sống độc lập, nên truyền actor metadata tối thiểu, chạy bằng workload identity và kiểm tra lại quyền khi thực thi; nếu cần đại diện user, dùng delegation/token exchange được Authorization Server hỗ trợ. Giữ tách biệt **context propagation**, **token relay** và **delegation** giúp async work không lẫn danh tính, không rò credential và không mang quyền cũ vượt quá vòng đời request.
