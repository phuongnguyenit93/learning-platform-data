# Giới hạn truyền `SecurityContext`, MDC và ngữ cảnh giao dịch khi đổi luồng

## 1. Tình huống thực tế và điều cần phân biệt

Một HTTP request vào ứng dụng Spring Boot có thể đi qua servlet filter, Spring Security, controller, service được đánh dấu `@Transactional`, rồi đẩy một công việc sang `@Async`, `CompletableFuture`, `ExecutorService` hoặc Reactor scheduler. Trên thread xử lý request, ứng dụng đọc được:

- **`SecurityContext`**: thông tin `Authentication` đang gắn với luồng thực thi, dùng để nhận biết người dùng và thực hiện kiểm tra quyền trong Spring Security Servlet.
- **MDC (Mapped Diagnostic Context)**: các cặp khóa–giá trị như `requestId`, `traceId`, `tenantId` đưa vào log để tương quan các dòng log.
- **Ngữ cảnh giao dịch**: tài nguyên, trạng thái và đồng bộ giao dịch do `PlatformTransactionManager` quản lý; với JDBC/JPA thường ràng buộc vào thread.

Sau khi đổi sang thread khác, ba thứ trên **không mặc nhiên đi theo**. Kết quả thường gặp là `SecurityContextHolder.getContext().getAuthentication()` không còn thông tin của request, `MDC.get("requestId")` trả `null`, hoặc thao tác database chạy ngoài giao dịch của caller.

Câu hỏi cốt lõi không chỉ là “làm sao copy context?”. Cần hỏi: **context nào được phép truyền, truyền theo cơ chế nào, sống đến lúc nào và có an toàn khi dùng trên một thread khác hay không?** Security context và MDC có thể được đưa sang một công việc có giới hạn theo chính sách rõ ràng. Giao dịch JDBC/JPA đang hoạt động **không thể được chuyển giao an toàn chỉ bằng copy các biến thread-local**.

Phạm vi bài: Spring Boot 3.3.x, Spring Framework 6.1.x, Spring Security 6.x, Java 17+; phân biệt Servlet stack và Reactive/WebFlux. Các ví dụ có nhãn **chạy độc lập** hoặc **mẫu tích hợp** để không nhầm đoạn mã minh họa với ứng dụng đầy đủ.

## 2. Mô hình nền tảng: luồng vật lý và ngữ cảnh logic

`ThreadLocal<T>` lưu một giá trị theo **thread hiện tại**. Hai thread đọc cùng một biến `ThreadLocal` vẫn nhận các giá trị khác nhau:

```text
Request R-42
    |
    v
Thread servlet-1
    SecurityContextHolder = user: alice
    MDC["requestId"]     = R-42
    JDBC transaction     = tx-A / connection-A
    |
    +---- executor.submit(task) ----> Thread pool-3
                                      SecurityContext = không được tự truyền
                                      MDC             = không được tự truyền
                                      tx-A            = không được tự truyền
```

Một request là **đơn vị logic**; một thread là **đơn vị thực thi**. Trong Servlet đồng bộ, chúng thường trùng nhau trong phần xử lý chính. Khi thực thi bất đồng bộ, job có thể dùng thread khác, thread cũ được tái sử dụng cho request khác, và thậm chí một reactive pipeline có thể chuyển qua nhiều thread trong vòng đời một subscription.

| Ngữ cảnh | Cơ chế phổ biến trong Servlet/imperative | Qua thread khác mặc định | Cách xử lý phù hợp |
| --- | --- | --- | --- |
| Security | `SecurityContextHolder` mặc định dùng `MODE_THREADLOCAL` | Không đáng tin cậy | Spring Security delegating wrappers hoặc truyền dữ liệu danh tính đã được kiểm soát |
| MDC | Logging framework thường duy trì map theo thread | Không đáng tin cậy | Snapshot MDC khi submit, cài vào worker, hoàn nguyên trong `finally` |
| Transaction JDBC/JPA | `TransactionSynchronizationManager` gắn resource/transaction state với thread | **Không truyền** | Tạo giao dịch mới có chủ đích bên worker, hoặc giữ thao tác đồng bộ trong transaction gốc |
| Security trong WebFlux | Reactor `Context` thông qua `ReactiveSecurityContextHolder` | Còn khi tiếp tục cùng reactive chain/subscription | Giữ pipeline và `Context`; tránh dựa vào Servlet `ThreadLocal` |
| Transaction reactive | Reactor `Context` với `ReactiveTransactionManager` | Còn khi tham gia cùng reactive subscription | Duy trì chuỗi reactive và transaction operator đúng phạm vi |
| Tracing/observation | Micrometer/observability context + bridge phù hợp | Phụ thuộc cấu hình/instrumentation | Dùng context propagation đã đăng ký, không hiểu là chuyển giao DB transaction |

Một lỗi thiết kế là gộp ba dạng context thành một “request context” rồi sao chép tất cả. Mỗi context có nguồn gốc, độ nhạy cảm và quy tắc vòng đời khác nhau.

## 3. Java 17: thí nghiệm `ThreadLocal` có kết quả xác định

Ví dụ sau chạy **độc lập chỉ với JDK 17+**; nó cho thấy giá trị request không tự xuất hiện ở worker, và cách scope/restore một snapshot trong một task.

**Tệp `ThreadBoundaryDemo.java`:**

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadBoundaryDemo {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            REQUEST_ID.set("req-42");
            System.out.println("caller: " + REQUEST_ID.get());

            String before = pool.submit(REQUEST_ID::get).get();
            System.out.println("worker before: " + before);

            String captured = REQUEST_ID.get(); // snapshot trước khi submit
            pool.submit(() -> {
                String previous = REQUEST_ID.get();
                try {
                    REQUEST_ID.set(captured);
                    System.out.println("worker during: " + REQUEST_ID.get());
                } finally {
                    if (previous == null) {
                        REQUEST_ID.remove();
                    } else {
                        REQUEST_ID.set(previous);
                    }
                }
            }).get();

            String after = pool.submit(REQUEST_ID::get).get();
            System.out.println("worker after: " + after);
        } finally {
            REQUEST_ID.remove();
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ThreadBoundaryDemo.java
java ThreadBoundaryDemo
```

**Stdout chính xác:**

```text
caller: req-42
worker before: null
worker during: req-42
worker after: null
```

`newSingleThreadExecutor()` giữ cùng worker thread cho ba task theo thứ tự. Task thứ nhất chứng minh không có kế thừa tự động; task thứ hai cài snapshot trong phạm vi thực thi; task thứ ba chứng minh đã dọn dẹp. Nếu bỏ `finally`, thread pool có thể giữ dữ liệu của request trước và khiến request sau đọc nhầm dữ liệu — đặc biệt nguy hiểm khi dữ liệu gắn với người dùng.

Đây chỉ là bản mô phỏng để hiểu ranh giới; trong ứng dụng Spring Security, **không dùng một `ThreadLocal` tự chế để thay thế cơ chế bảo mật**.

## 4. `SecurityContext` trong Spring Security Servlet

Trong mô hình Servlet, `SecurityContextHolder` cung cấp cách truy cập context hiện thời:

```java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
```

`Authentication` có thể là người dùng đã xác thực, anonymous authentication hoặc `null`, tùy vị trí trong filter chain và cấu hình. Vì vậy “context trống” không đồng nghĩa tuyệt đối với “request chắc chắn chưa đăng nhập”. Chỉ nên đưa ra quyết định cấp quyền bằng các cơ chế security/filter/method-security đã cấu hình; không suy quyền bằng MDC hay tên thread.

### 4.1. Điều gì xảy ra ở `@Async`/executor?

Với strategy mặc định `MODE_THREADLOCAL`, Spring Security gắn context vào thread hiện tại. `new Thread(...)`, `CompletableFuture.supplyAsync(...)` hoặc một `Executor` thông thường chạy task trên thread khác; **bạn không nên kỳ vọng context Servlet được truyền nguyên vẹn**.

Tránh giải pháp tưởng như nhanh:

```java
// Không nên chọn làm giải pháp chung cho thread pool:
SecurityContextHolder.setStrategyName(
        SecurityContextHolder.MODE_INHERITABLETHREADLOCAL);
```

`MODE_INHERITABLETHREADLOCAL` chỉ có cơ chế kế thừa khi tạo **thread con**; thread trong pool thường được tạo trước khi request đến và được tái sử dụng. Nó không cung cấp snapshot đúng cho từng lần submit; nguy cơ chia sẻ context sai người dùng hoặc làm dữ liệu tồn tại lâu hơn request. `MODE_GLOBAL` còn nguy hiểm hơn cho web app nhiều người dùng vì chia sẻ toàn JVM.

### 4.2. Truyền theo **mỗi task** bằng cơ chế Spring Security

Mẫu tích hợp cho Servlet stack, chạy tại chỗ đã có `SecurityContext` của caller:

```java
import java.util.concurrent.Executor;

import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;

// delegate là Executor thật, chẳng hạn thread pool do ứng dụng quản lý.
Executor securityAware = new DelegatingSecurityContextExecutor(delegate);

securityAware.execute(() -> securedService.process());
```

Constructor **không truyền cố định `SecurityContext`** lấy context hiện hành khi submit từng task, bọc task, thiết lập context trên worker và dọn dẹp sau khi task kết thúc. Nếu truyền một `SecurityContext` cố định vào constructor khác, mọi task có thể dùng cùng danh tính — chỉ phù hợp với trường hợp hệ thống được thiết kế riêng, không phù hợp làm executor chung cho người dùng web.

Spring Security có những adapter liên quan: `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextExecutorService`, `DelegatingSecurityContextAsyncTaskExecutor`, ... Chọn adapter khớp API và đường thực thi thực tế.

**Giới hạn:** Wrapper hỗ trợ chuyển `SecurityContext`; nó **không tự chuyển MDC, transaction JDBC/JPA, request attributes hoặc mọi `ThreadLocal` khác**. Context được nắm bắt ở thời điểm submit có thể khác context tại lúc task thực sự chạy. Không mặc nhiên mang credentials của request vào job chạy lâu, queue tồn tại bền vững hay service bên ngoài.

### 4.3. `@Async` phải dùng đúng executor và đúng proxy

`@Async` hoạt động qua Spring proxy (mặc định). Phương thức `@Async` được gọi từ **bean khác thông qua proxy** mới kích hoạt cơ chế chuyển việc sang executor; gọi `this.someAsyncMethod()` từ cùng bean thường không được intercept.

Nếu khai báo:

```java
@Async("contextAwareExecutor")
public CompletableFuture<String> fetchAsync() {
    Authentication a =
            SecurityContextHolder.getContext().getAuthentication();
    String username = a == null ? "none" : a.getName();
    return CompletableFuture.completedFuture(username);
}
```

Thì `contextAwareExecutor` phải là một `Executor`/`AsyncTaskExecutor` được cấu hình hỗ trợ chuyển security context. Đoạn method trên là **mẫu tích hợp trong Spring bean**, không phải chương trình độc lập: cần `@EnableAsync`, Spring Security và bean executor tương ứng.

Lưu ý riêng: Spring MVC có tích hợp security-context cho một số cơ chế Servlet async, chẳng hạn `Callable` do MVC quản lý. **Không khái quát điều đó cho mọi `CompletableFuture`, `DeferredResult`, thread tùy tạo hay `@Async`**; mỗi đường thực thi có contract riêng.

## 5. MDC: copy **dữ liệu log** và luôn khôi phục trạng thái worker

Trong ứng dụng Spring Boot Servlet dùng SLF4J với Logback mặc định, `MDC.put("requestId", ...)` thường gắn dữ liệu với thread hiện hành:

```java
MDC.put("requestId", "req-42");
try {
    // log ở thread hiện tại có thể đọc requestId
} finally {
    MDC.remove("requestId");
}
```

Khi thread đổi, bản đồ MDC không tự được chuyển theo một cách có thể dựa vào. MDC chứa **metadata của log**, không phải nguồn xác thực hay transaction. Nếu cần truyền, phải chụp `MDC.getCopyOfContextMap()` ở **thời điểm submit**, cài vào worker trong khoảng chạy task và khôi phục bản đồ trước đó bằng `finally`.

Ví dụ `TaskDecorator` dùng trong Spring 6.1+:

```java
import java.util.Map;

import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                restore(captured);
                task.run();
            } finally {
                restore(previous);
            }
        };
    }

    private static void restore(Map<String, String> context) {
        if (context == null || context.isEmpty()) {
            MDC.clear();
        } else {
            MDC.setContextMap(context);
        }
    }
}
```

Đây là **một class độc lập về cú pháp**, nhưng cần thư viện `slf4j-api` và `spring-core` trên classpath. `TaskDecorator` chỉ phát huy tác dụng khi được gắn vào executor được dùng thật. `getCopyOfContextMap()` tạo bản sao của map; không nên giữ map mutable được chia sẻ giữa nhiều request. `finally` chạy cả khi task phát sinh exception.

Nếu ứng dụng đã tích hợp Micrometer Context Propagation và có `ThreadLocalAccessor` tương ứng, có thể cân nhắc `org.springframework.core.task.support.ContextPropagatingTaskDecorator`. Nó hữu ích cho observability/logging context **đã đăng ký**, nhưng không thể kỳ vọng sao chép mọi loại ThreadLocal, và càng không biến transaction database thành context truyền được.

Cần tránh đưa access token, mật khẩu, session secret, số định danh nhạy cảm hay đối tượng `Authentication` vào MDC. Đặc biệt, **MDC không được dùng làm dữ liệu ủy quyền**. Nếu `requestId` đến từ HTTP header bên ngoài, cần chuẩn hóa/khoanh giới độ dài để tránh log injection và nhãn có cardinality quá cao.

## 6. Mẫu kết hợp MDC và Security cho `@Async` trong Spring Boot

Mục đích mẫu này: mỗi task submit qua `contextAwareExecutor` nhận được **SecurityContext phù hợp** và **snapshot MDC của caller**; không truyền transaction.

**`AsyncContextConfiguration.java`** — mẫu tích hợp trong ứng dụng Spring Boot có `spring-boot-starter-security`:

```java
package com.example.web;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncContextConfiguration {

    @Bean("mdcDelegateExecutor")
    ThreadPoolTaskExecutor mdcDelegateExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("background-");
        executor.setTaskDecorator(new MdcTaskDecorator());
        return executor;
    }

    @Bean("contextAwareExecutor")
    AsyncTaskExecutor contextAwareExecutor(
            @Qualifier("mdcDelegateExecutor") ThreadPoolTaskExecutor delegate) {
        return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
    }
}
```

`ThreadPoolTaskExecutor` là Spring bean nên container gọi lifecycle khởi tạo/đóng của bean delegate; tránh tự quản lý nhiều executor trùng vai trò. Lớp `MdcTaskDecorator` của mục trước đặt cùng package `com.example.web`. Khi submit, adapter Spring Security bọc task, còn delegate áp dụng MDC decorator. Cả hai phải giữ nguyên quy tắc dọn context sau khi task hoàn tất.

**`AsyncAuditService.java`** — bean khác được gọi qua Spring proxy:

```java
package com.example.web;

import java.util.concurrent.CompletableFuture;

import org.slf4j.MDC;
import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class AsyncAuditService {

    @Async("contextAwareExecutor")
    public CompletableFuture<String> describeCaller() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        String username = auth == null ? "none" : auth.getName();
        String requestId = MDC.get("requestId");

        return CompletableFuture.completedFuture(
                "user=" + username + ", requestId=" + requestId);
    }
}
```

Khi **một bean khác** gọi `asyncAuditService.describeCaller()` bên trong request đã xác thực và đã thiết lập MDC, giá trị principal và request ID sẽ sẵn có trong task nếu toàn bộ đường thực thi đi qua executor trên. Kết quả cụ thể phụ thuộc authentication và MDC thực tế; không cố định stdout cho một request chưa được cung cấp.

Ví dụ tích hợp này cần Spring Boot web/async/security và logging như môi trường dự án; nó **không chứng minh giao dịch caller còn hiệu lực**. Không đặt `@Transactional` trên config chỉ vì muốn copy context.

**Khi nào không cần copy?** Nếu công việc chỉ cần `orderId`, `userId` ổn định và `correlationId`, thường tốt hơn truyền ba giá trị dạng immutable qua tham số rõ ràng. Điều này tránh phát tán toàn bộ quyền truy cập của một request sang công việc nền có vòng đời dài hơn.

## 7. Ngữ cảnh giao dịch imperative: ranh giới KHÔNG được vượt bằng copy

Spring Framework sử dụng `TransactionSynchronizationManager` để quản lý resource và transaction synchronization **theo thread** trong mô hình imperative, ví dụ JDBC/Hibernate:

```text
Thread request-1:
@Transactional boundary (PlatformTransactionManager)
    -> Connection / EntityManager gắn với thread-1
    -> save(order)
    -> executor.execute(...)
         |
         v
       Thread worker-7:
         Không tự có Connection / EntityManager / tx gốc
    -> commit hoặc rollback của transaction gốc xảy ra trên thread-1
```

`@Transactional` trên service request **không làm transaction tự đi theo** task gửi sang thread khác. Nếu `worker-7` gọi repository, thao tác có thể chạy trong **transaction khác** (nếu method repository/worker mở transaction riêng) hoặc ngoài transaction của request, tùy API. Hậu quả:

- Worker có thể đọc dữ liệu chưa commit và nhận kết quả không như mong đợi; ở isolation phổ biến, worker thường **không thấy** thay đổi chưa commit.
- Task có thể chạy **trước khi caller commit** hoặc vẫn tiếp tục **sau khi caller rollback**.
- Lỗi ở task không mặc nhiên rollback transaction của caller; rollback của caller cũng không đảo ngược transaction worker đã commit.
- `EntityManager`/JPA persistence context và JDBC `Connection` thường không an toàn để truy cập đồng thời từ nhiều thread.

**Không thực hiện:**

```java
// Sai hướng: copy các resource/đối tượng TransactionSynchronizationManager
// hoặc đưa Connection/EntityManager của request vào worker.
executor.execute(() -> useSameEntityManagerAcrossThreads());
```

`TransactionSynchronizationManager.bindResource(...)` là API phục vụ transaction/resource infrastructure; tự copy thread-bound resources sang worker không tạo một transaction phân tán hợp lệ, có thể gây concurrent access, commit/rollback sai và rò rỉ connection. Không dùng security/MDC context propagation để “sửa” chuyện này.

### 7.1. Muốn worker có giao dịch: mở giao dịch **mới trên worker**

Mẫu tích hợp dùng bean service riêng; `@Async` và `@Transactional` được áp dụng qua Spring proxy, với một `PlatformTransactionManager` phù hợp:

```java
package com.example.web;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AsyncDatabaseService {

    private final AuditRepository auditRepository;

    public AsyncDatabaseService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Async("contextAwareExecutor")
    @Transactional
    public CompletableFuture<Void> saveAudit(AuditEntry entry) {
        auditRepository.save(entry);
        return CompletableFuture.completedFuture(null);
    }
}
```

**Mẫu tích hợp, chưa phải ứng dụng tự chạy**: `AuditRepository`/`AuditEntry` là các kiểu miền của ứng dụng cần được định nghĩa. `@EnableAsync` và transaction management phải được cấu hình; gọi qua proxy. Transaction tại `saveAudit(...)` được tạo **trong thread chạy method**, độc lập với transaction của người gọi, chứ không “nối tiếp transaction gốc” theo nghĩa chia sẻ resource/commit. Giá trị `Propagation.REQUIRED` của transaction worker chỉ có thể tham gia transaction đang gắn với **chính worker**, không thể phát hiện transaction đang chạy ở thread caller.

Nếu cần kiểm soát giao dịch tường minh, thực hiện `transactionTemplate.execute(status -> ...)` **bên trong worker** với `TransactionTemplate` và transaction manager được cấu hình đúng. Không khởi tạo transaction trên request thread rồi đưa connection sang worker.

### 7.2. Nếu công việc phải chạy sau commit

Không gọi tác vụ ngoài hệ thống trước khi kết quả database trở nên bền vững. Những cách thường dùng:

1. **Đồng bộ:** để những thay đổi bắt buộc cùng atomicity trong một service `@Transactional` trên cùng thread.
2. **Sau commit, cùng process:** `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` kích hoạt xử lý sau khi giao dịch commit. Nếu cần bất đồng bộ, chuyển sang executor sau mốc này; xử lý worker có thể cần **transaction mới** để ghi DB. Event in-memory không phải queue bền vững: process có thể chết sau commit nhưng trước khi task hoàn tất.
3. **Cần tin cậy qua restart:** transactional outbox — trong transaction gốc ghi cả dữ liệu nghiệp vụ và bản ghi outbox; worker đọc outbox đã commit và retry độc lập. Thiết kế consumer idempotent vì delivery có thể lặp.

Không hiểu `@TransactionalEventListener(AFTER_COMMIT)` là “mọi thao tác DB trong callback đều tự có transaction mới”. Sau commit, tài nguyên transaction có thể vẫn còn gắn tạm thời với thread trong giai đoạn cleanup; nếu callback cần ghi bền vững, chỉ rõ một transaction mới, chẳng hạn qua service `@Transactional(propagation = REQUIRES_NEW)` được gọi bằng proxy hoặc để worker mở transaction của chính nó.

## 8. WebFlux: Reactor `Context` không đồng nghĩa `ThreadLocal`

Trong WebFlux, một request không nhất thiết được xử lý trên đúng một thread từ đầu đến cuối. `publishOn(...)` đổi thread dùng cho tín hiệu downstream; `subscribeOn(...)` tác động việc subscription/source được chạy; reactive pipeline có thể chuyển scheduler mà vẫn là một **subscription logic**.

Reactor cung cấp `Context`/`ContextView` gắn với **Subscriber**, không phải thread. Đây là cơ sở cho Spring Security Reactive và transaction reactive.

### 8.1. Demo Reactor Context xuyên qua `publishOn`

Đoạn này là **ví dụ Java dùng reactor-core**; có thể đưa vào `main` của project có dependency Reactor (ví dụ `spring-boot-starter-webflux`):

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public class ReactorContextDemo {

    public static void main(String[] args) {
        Mono<String> pipeline = Mono.deferContextual(view ->
                        Mono.just(view.getOrDefault("requestId", "missing")))
                .publishOn(Schedulers.parallel())
                .contextWrite(Context.of("requestId", "req-42"));

        System.out.println(pipeline.block());
    }
}
```

**Stdout:**

```text
req-42
```

`contextWrite(...)` gắn dữ liệu vào subscription cho các operator ở phía upstream; `deferContextual(...)` đọc khi subscriber đăng ký. `publishOn(...)` có thể đổi thread, nhưng Reactor context vẫn đi cùng cùng pipeline/subscription. Không suy ra `ThreadLocal` trong `Mono` sẽ được khôi phục: đó là một cơ chế khác.

**Lưu ý về ranh giới:** tự gọi `subscribe()` bên trong method để tạo subscription độc lập, chuyển sang một `ExecutorService` thường hoặc ra khỏi reactive pipeline không tự giữ Reactor Context của caller. Context cũng không mặc nhiên biến thành header HTTP hoặc metadata của message broker.

### 8.2. Reactive SecurityContext

Trong Spring Security WebFlux, truy cập danh tính thông qua `ReactiveSecurityContextHolder`:

```java
import reactor.core.publisher.Mono;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

Mono<String> currentUsername =
        ReactiveSecurityContextHolder.getContext()
                .flatMap(context ->
                        Mono.justOrEmpty(context.getAuthentication()))
                .map(Authentication::getName)
                .defaultIfEmpty("anonymous");
```

Đoạn này là **mẫu tích hợp** cần chạy trong WebFlux request đã được Spring Security cấu hình, hoặc một subscription mà bạn đã đưa context bảo mật vào. `ReactiveSecurityContextHolder` đọc từ Reactor Context; không thay bằng `SecurityContextHolder.getContext()` dựa trên thread khi code thực sự là reactive. Trong test có thể đặt Authentication cho một chain bằng:

```java
Mono<String> secured = currentUsername.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication));
```

`authentication` là đối tượng `Authentication` do test/ứng dụng cung cấp, không phải biến có sẵn trong snippet. Context của reactive subscription không mang nghĩa phiên xác thực dài hạn cho mọi task nền.

### 8.3. Reactive transaction khác transaction JDBC/JPA

Với `ReactiveTransactionManager` (ví dụ một transaction manager dành cho R2DBC), Spring mang trạng thái giao dịch qua **Reactor Context**. Các thao tác data access muốn cùng transaction phải tham gia cùng reactive pipeline/subscription tương ứng; phương thức `@Transactional` reactive phải trả kiểu reactive như `Mono`/`Flux`, hoặc sử dụng `TransactionalOperator`.

Với `PlatformTransactionManager` (JDBC/JPA), trạng thái lại gắn với thread. **Không thể dùng Reactor Context để tự biến JDBC transaction thành transaction reactive**, cũng không dùng cơ chế Micrometer truyền `ThreadLocal` để “vác” `Connection`/`EntityManager` của thread này sang thread khác.

Ví dụ phân biệt:

| Mẫu | Kết luận |
| --- | --- |
| `Mono.defer(...).publishOn(...).contextWrite(...)` | Context Reactor có thể được nhìn thấy qua đổi scheduler trong cùng subscription |
| Reactive repository trong `TransactionalOperator` | Có thể tham gia reactive transaction do operator quản lý |
| JDBC/JPA `@Transactional` rồi gọi `CompletableFuture.supplyAsync(...)` | Task không được kế thừa JDBC/JPA transaction của caller |
| Gọi `.block()` để chờ reactive operation rồi coi nó là một phần transaction imperative hiện tại | Không có bảo đảm tự động; có thêm ranh giới subscription và thread, dễ gây blocking/event-loop issues |
| Khởi chạy một `subscribe()` mới bên trong pipeline giao dịch | Tạo subscription độc lập; không nên kỳ vọng nó ở trong transaction/context của chain ban đầu |

Đối với WebFlux, tránh block event-loop bằng JDBC hoặc `.block()` trong request processing. Nếu buộc gọi API blocking, cân nhắc `Schedulers.boundedElastic()` và **transaction riêng có phạm vi rõ ràng**; không nhầm việc chuyển scheduler với chuyển giao transaction.

## 9. MDC và observability trong Reactive/async: cơ chế bridge có giới hạn

MDC của SLF4J thường truy xuất theo thread, còn Reactor Context theo subscription. Vì vậy:

```text
Reactor Context["requestId"] = req-42
               |
               +--> publishOn(thread B)
                         |
                         +--> MDC.get("requestId") có thể null
```

`contextWrite(...)` không tự bảo đảm `MDC.get(...)` đọc được giá trị. Có ba hướng:

- Trong operator có thông tin context, **đọc `ContextView`** và đặt MDC cục bộ bao quanh đúng câu lệnh log; dùng `try/finally` hoặc `MDC.putCloseable` để cleanup ngay, không để lại MDC trong event-loop thread.
- Với Micrometer Context Propagation: đăng ký accessor tương ứng, nắm/khôi phục context tại ranh giới được hỗ trợ; chọn automatic context propagation cho Reactor khi hệ thống cần. Thư viện chỉ khôi phục các ThreadLocal mà accessor biết và chế độ đã cấu hình.
- Dùng Micrometer Tracing/Observation và instrumentation phù hợp để trace/span correlation đi qua pipeline theo cơ chế được hỗ trợ. Kiểm tra log pattern và version, không tự giả định có MDC keys nếu chưa cấu hình.

Spring Boot 3.3 có thuộc tính:

```properties
# Chỉ dùng khi dự án có nhu cầu và phụ thuộc hỗ trợ Context Propagation
spring.reactor.context-propagation=auto
```

Thuộc tính này bật chế độ context propagation tự động cho Reactor **khi có hạ tầng hỗ trợ thích hợp**; nó không biến bất kỳ `ThreadLocal` nào thành dữ liệu truyền được, cũng không chuyển transaction JDBC/JPA. Với `@Async` ở Spring Boot 3.3, muốn truyền observation/logging context qua executor tự cấu hình thì cần `TaskDecorator`/cơ chế capture tương ứng; không suy rằng bật `spring.reactor.context-propagation=auto` sẽ xử lý cả thread pool thông thường.

Một quyết định thực tế: chỉ truyền **correlation metadata cần thiết**. Nếu tác vụ nền không cùng vòng đời request, hãy tự tạo correlation cho job và liên kết với request gốc bằng ID, không giữ nguyên toàn bộ MDC và SecurityContext vô hạn.

## 10. Bảng ranh giới theo API thực thi

| API/tình huống | Có chuyển thread? | Security Servlet | MDC | Transaction imperative |
| --- | --- | --- | --- | --- |
| Controller → service đồng bộ trong cùng call stack | Thường không | Giữ trong phạm vi thread/request hiện hành | Giữ trong thread | Có thể tham gia transaction do Spring quản lý |
| `new Thread(...).start()` | Có | Không mặc định | Không mặc định | Không |
| `ExecutorService.submit(...)` | Thường có | Không mặc định; cần wrapper theo task | Không mặc định; cần decorator/snapshot | Không |
| `CompletableFuture.supplyAsync(...)` không truyền executor | Có thể chạy ở common pool | Không mặc định | Không mặc định | Không |
| `@Async` trên bean được gọi qua proxy | Có | Cần cấu hình executor hỗ trợ security context nếu muốn truyền | Cần decorator/propagation phù hợp | Transaction caller không đi theo; method async có thể tự mở transaction |
| `parallelStream()` | Thường có worker khác | Không mặc định | Không mặc định | Không; tránh thao tác DB phụ thuộc transaction thread-bound trong parallel stream |
| Spring MVC async `Callable` do MVC quản lý | Có thể | Có tích hợp đặc thù của Spring Security khi được cấu hình | Không suy là được truyền | Không suy là được truyền |
| Spring WebFlux `publishOn` trong cùng subscription | Có thể | Dùng ReactiveSecurityContextHolder/Reactor Context | MDC cần bridge | Reactive transaction có thể tiếp tục trong chain; JDBC transaction không đi theo |
| Message queue/HTTP call sang process khác | Khác process | Không thể truyền đối tượng ThreadLocal/SecurityContext Java | Gửi correlation/tracing metadata theo protocol | Không thể tự chuyển local DB transaction; dùng message/outbox/transaction phù hợp |

Đây là **bản đồ mặc định và giới hạn hợp đồng**. Thư viện, filter, TaskDecorator, agent tracing hoặc cấu hình ứng dụng có thể bổ sung một số kiểu propagation; phải kiểm chứng cơ chế cụ thể trước khi dựa vào nó.

## 11. Chu trình request–async–database: ba lỗi kinh điển

Giả sử request `POST /orders` đang thuộc user `alice`, có `MDC["requestId"]="R-42"` và service lưu order trong transaction `tx-A`.

**Lỗi 1: mất danh tính trên worker**

```text
Controller on servlet thread: alice
    -> @Async worker: Authentication null/khác request
    -> @PreAuthorize(...) tại worker có thể fail
```

Giải pháp: dùng executor bọc `SecurityContext` nếu công việc **thực sự phải dùng quyền của caller**. Với tác vụ kéo dài, dùng danh tính/ủy quyền thích hợp cho worker và truyền input immutable; không giữ quyền của một phiên đã hết hạn theo cách thiếu kiểm soát.

**Lỗi 2: log không nối được theo request hoặc bị lẫn request**

```text
servlet-1: requestId=R-42
pool-3:    requestId=null
pool-3:    requestId=R-10 (nếu task trước quên clear)
```

Giải pháp: capture map theo từng task, cài/khôi phục bằng `finally`; kiểm tra MDC sau khi task chạy xong, cả nhánh lỗi. Với queue/outbox, ID tương quan nên được lưu như metadata nghiệp vụ rõ ràng.

**Lỗi 3: task đọc/ghi DB trước commit**

```text
tx-A: save(order=123)
      submit(asyncSendOrder123)
pool-3: query(order=123)    <-- có thể chưa thấy bản ghi
tx-A: rollback             <-- task vẫn có thể đã gửi thông báo
```

Giải pháp: không khởi chạy side effect chỉ vì `save()` vừa được gọi trong transaction chưa commit. Chọn `AFTER_COMMIT`, transaction mới tại worker khi cần DB, hoặc outbox nếu cần xử lý tin cậy. **Security/MDC propagation không giải quyết tính nguyên tử của giao dịch.**

## 12. Thời điểm capture, vòng đời, an toàn và hiệu năng

Một giải pháp propagation tốt phải trả lời các câu hỏi sau:

1. **Capture lúc nào?** Thường là lúc submit task, khi request context đang hợp lệ. Nếu task xếp hàng lâu, context/claims có thể hết hạn trước khi thực thi.
2. **Truyền những gì?** Truyền giá trị tối thiểu (`correlationId`, `actorId`, immutable business data); chỉ chuyển full SecurityContext khi cơ chế security được thiết kế cho việc đó.
3. **Restore lúc nào?** Khi task bắt đầu; khôi phục trạng thái worker cũ trong `finally`, kể cả hủy hoặc exception. Dọn context tại ranh giới request/filter cũng quan trọng.
4. **Có task con không?** Task A đã được bọc không có nghĩa task B do A tự `supplyAsync(...)` sẽ được bọc. Mỗi ranh giới executor/subscription/process phải được thiết kế riêng.
5. **Có retry và pooling không?** Worker có thể tái sử dụng; tránh rò rỉ MDC và danh tính giữa người dùng. Retry sau nhiều phút nên dùng input có chủ đích, không dùng bản copy ngữ cảnh của request đã kết thúc.
6. **Tác động hiệu năng?** Capture/copy context có chi phí; không áp dụng decorator nặng cho hàng triệu task cực nhỏ nếu không cần. Giữ cardinality của MDC và trace attributes ở mức hợp lý.
7. **Virtual threads thì sao?** Java 21 virtual thread vẫn có `ThreadLocal` riêng; virtual thread không giúp truyền arbitrary context từ caller sang thread khác một cách tự động. Đừng gắn correctness với tên thread hoặc giả định mọi request luôn cố định trên một thread.

`ThreadLocal`/MDC không phải kênh giao tiếp giữa các service, cũng không phải nơi lưu trạng thái business dài hạn. Dùng header/tracing conventions, message metadata, database/outbox và đối tượng dữ liệu rõ ràng tùy yêu cầu.

## 13. Cách kiểm chứng trong dự án Spring Boot

Có thể ghi log kiểm chứng tại **request thread** và **worker thread** bằng một helper quan sát nhỏ:

```java
import org.slf4j.MDC;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class ContextProbe {
    private ContextProbe() { }

    public static void inspect(String label) {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        String username = authentication == null
                ? "<none>" : authentication.getName();

        System.out.printf(
                "%s | thread=%s | user=%s | requestId=%s | tx=%s%n",
                label,
                Thread.currentThread().getName(),
                username,
                MDC.get("requestId"),
                TransactionSynchronizationManager.isActualTransactionActive());
    }
}
```

**Mẫu tích hợp** cần classpath Spring Security, SLF4J và Spring transaction. Dùng:

```java
ContextProbe.inspect("before-submit");
asyncService.run(...); // qua proxy và executor được chỉ định
```

và gọi `ContextProbe.inspect("inside-worker")` từ method async. Không có stdout cố định vì giá trị tùy request/executor/transaction thực tế. `isActualTransactionActive()` cho biết trạng thái transaction mà Spring đang gắn **với thread đang kiểm tra**, không chứng minh hai thread đang chia sẻ cùng một transaction.

Một checklist kiểm thử có giá trị:

- **Mặc định:** Executor không bọc context không được giả định có principal/requestId của caller; worker không được nhìn thấy imperative transaction của thread request.
- **Có wrapper:** Gửi hai request với hai user và hai requestId khác nhau qua một pool tái sử dụng, chặn chờ có kiểm soát nếu cần; đảm bảo mỗi task thấy đúng user/requestId của nó.
- **Không rò rỉ:** Sau mỗi task, worker không để lại requestId/user từ task trước; test cả đường throw exception và cancellation.
- **Giao dịch:** Trong request `@Transactional`, đo trạng thái transaction; trong worker đo riêng. Kiểm tra rõ việc worker tự mở transaction và tình huống caller rollback.
- **Sau commit:** Thử đường commit thành công, rollback và restart process; nếu cần bảo đảm không mất job, xác nhận outbox và retry/idempotency.
- **Reactive:** Với cùng pipeline có `contextWrite`, thử `publishOn`/`subscribeOn` và đọc `deferContextual`; tách `subscribe()` để thấy giới hạn; nếu có reactive transaction, xác nhận repository operations ở đúng subscription.

Không dùng một log “thread name giống nhau” làm bằng chứng context đã đúng; trong môi trường concurrent, thread name không mang danh tính người dùng.

## 14. Những hiểu nhầm dễ dẫn tới lỗi nghiêm trọng

**“`@Async` tự sao chép toàn bộ context.”** Không. Cơ chế async chọn executor và chạy method trên thread khác. Muốn propagation phải chọn adapter/decorator tương thích với từng kiểu dữ liệu.

**“Đã có `DelegatingSecurityContextAsyncTaskExecutor` thì MDC và transaction cũng có.”** Không. Spring Security adapter xử lý security context; MDC phải xử lý riêng, transaction imperative phải tạo ranh giới riêng.

**“Dùng `MODE_INHERITABLETHREADLOCAL` là an toàn với thread pool.”** Không. Đó là cơ chế kế thừa khi tạo thread, không có semantics snapshot/cleanup cho mỗi task được submit vào thread đã tồn tại.

**“Sao chép `TransactionSynchronizationManager` hoặc JDBC Connection là chuyển được transaction.”** Sai và nguy hiểm: resource có vòng đời, ownership và giới hạn thread-safety; transaction manager phải tạo/quản lý transaction đúng thread/phạm vi.

**“`@Transactional` bao ngoài `CompletableFuture` khiến toàn bộ future dùng chung transaction.”** Không. Imperative transaction ràng buộc với thread và phạm vi interceptor; future chạy ở thread khác có lifecycle riêng.

**“Reactor Context là bản sao MDC.”** Không. Reactor Context gắn với subscriber; MDC thường gắn với thread. Muốn log có MDC phải có bridge cục bộ hoặc thư viện context propagation đã cấu hình.

**“`publishOn` luôn làm mất Reactive SecurityContext/transaction.”** Không nếu tiếp tục trong cùng reactive subscription và dùng đúng Reactor Context. Nhưng tự tạo subscription mới/chuyển sang API blocking/Executor nằm ngoài chain là ranh giới khác.

**“Truyền user/token vào MDC là cách phân quyền.”** Không. MDC phục vụ log; phải dựa trên cơ chế xác thực/ủy quyền có kiểm soát và tránh rò rỉ bí mật.

## 15. Câu hỏi tự kiểm tra và phương án áp dụng

1. Một service `@Transactional` gửi `CompletableFuture.supplyAsync(...)` để ghi cùng database. Tại sao future không thấy chắc chắn dữ liệu chưa commit, và vì sao lỗi future không tự rollback transaction gốc?
2. Giữa `DelegatingSecurityContextExecutor` và `MdcTaskDecorator`, công cụ nào xử lý loại context nào? Cần thêm gì nếu task cũng cần transaction?
3. Nếu hai request lần lượt dùng chung một worker thread, vì sao thiếu `finally` có thể làm log request thứ hai gắn request ID của request thứ nhất?
4. Trong WebFlux, vì sao `ReactiveSecurityContextHolder.getContext()` phù hợp hơn truy cập `SecurityContextHolder` trực tiếp? Điều gì đổi khi gọi `subscribe()` mới?
5. Với công việc cần gửi thông báo sau khi đặt hàng thành công, khi nào nên dùng `@TransactionalEventListener(AFTER_COMMIT)` và khi nào cần transactional outbox?
6. Nếu bật `spring.reactor.context-propagation=auto`, lý do nào khiến ta vẫn **không được** copy JDBC transaction sang scheduler khác?

Cách chọn giải pháp theo mục tiêu:

| Nhu cầu | Giải pháp ưu tiên |
| --- | --- |
| Ghi thêm request ID vào log ở executor | MDC snapshot/decorator với cleanup, hoặc observability propagation đã cấu hình |
| Chạy `@Async` với danh tính của request hiện tại (task ngắn, có kiểm soát) | `DelegatingSecurityContextAsyncTaskExecutor` + proxy đúng |
| Job dài hạn chỉ cần biết ai đã yêu cầu | Truyền `actorId`/claims tối thiểu dưới dạng immutable input, tự xác thực/ủy quyền theo chính sách job |
| Cập nhật DB trong async worker | `@Transactional`/`TransactionTemplate` mở transaction riêng **trong worker** |
| Side effect phải diễn ra khi DB commit thành công | Sau commit event, hoặc transactional outbox nếu cần bền vững và retry |
| WebFlux security/reactive DB | Reactor Context + `ReactiveSecurityContextHolder` + `ReactiveTransactionManager`/`TransactionalOperator` |
| Gọi sang service/process khác | HTTP headers/tracing context hoặc message metadata có chủ đích; không truyền object ThreadLocal |

**Điểm cần ghi nhớ:** “đổi luồng” có thể làm mất những giá trị vốn được giữ theo thread, nhưng **không phải context nào cũng nên chuyển**. Với security và MDC, dùng cơ chế capture/scope/cleanup đúng ranh giới. Với giao dịch imperative, thiết kế lại transaction boundary; với WebFlux, dựa vào Reactor Context và phạm vi subscription.

### Tài liệu tham khảo chính thức

- Spring Security, Concurrency Support (Servlet): https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html
- Spring Security, reactive method security và Reactor Context: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Framework 6.1, `TransactionSynchronizationManager`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework, declarative transaction implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework 6.1, `ContextPropagatingTaskDecorator`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
- Spring Boot 3.3, application properties (`spring.reactor.context-propagation`): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Project Reactor, Context Propagation: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html