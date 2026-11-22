# Giới hạn ThreadLocal khi công việc chuyển sang luồng khác trong Spring Security Servlet

## 1. Bài toán: request đã đăng nhập nhưng tác vụ bất đồng bộ không thấy người dùng

Trong ứng dụng Spring Security **Servlet**, thông tin xác thực của request đang xử lý thường được truy cập qua `SecurityContextHolder`. Chiến lược mặc định của nó là `MODE_THREADLOCAL`: `SecurityContext` gắn với **luồng Java hiện tại**, không gắn tự động với mọi tác vụ sinh ra từ request. Vì vậy, controller có thể thấy `Authentication` của người dùng Alice nhưng công việc chạy trong `ExecutorService`, `@Async` hoặc một callback khác lại thấy `null` hoặc security context rỗng.

Ví dụ khái niệm:

```text
HTTP request (Thread servlet-1)
  SecurityContextHolder -> Authentication("alice")
  |
  +-- submit task vào thread pool
        |
        v
     Thread worker-7
       SecurityContextHolder -> context riêng, thường rỗng
       Không tự nhận Authentication("alice")
```

Bài toán còn nguy hiểm hơn việc “mất principal”: nếu code tự `setContext(...)` trên một thread pool mà quên khôi phục/dọn trong `finally`, yêu cầu của Bob có thể chạy trên một worker còn context của Alice. Đây là nguy cơ **rò rỉ danh tính và phân quyền xuyên tác vụ**.

Mục tiêu bài học:
- Hiểu phạm vi `ThreadLocal`, `SecurityContextHolder`, `SecurityContext` và `Authentication`.
- Nắm khác biệt giữa xử lý request bình thường, Spring MVC `Callable`, `DeferredResult`, `CompletableFuture`, `ExecutorService`, `@Async`, scheduler và virtual threads.
- Sử dụng đúng `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextExecutorService` và `DelegatingSecurityContextAsyncTaskExecutor`.
- Biết khi nào **không nên** truyền toàn bộ security context: công việc kéo dài, event, message queue, scheduled job hoặc nghiệp vụ cần service identity riêng.
- Kiểm thử propagation, cleanup, tài khoản bị cô lập và xử lý lỗi mà không dựa vào thời điểm thread pool tùy ý.

**Quy tắc nền tảng:** Một `ThreadLocal` mang dữ liệu của **thread**, không phải của “task nghiệp vụ” hay “người dùng”. Chuyển sang thread khác là chuyển sang một phạm vi dữ liệu khác, trừ khi có thành phần được thiết kế để truyền context.

## 2. SecurityContextHolder thực sự lưu gì?

Trong Spring Security, hai đối tượng quan trọng:

- **`Authentication`**: kết quả xác thực, thường bao gồm principal, authorities và trạng thái authenticated. Ví dụ `UsernamePasswordAuthenticationToken` hoặc `JwtAuthenticationToken`.
- **`SecurityContext`**: container chứa `Authentication`, được truy cập qua `SecurityContextHolder` khi authorization, service hoặc controller cần danh tính hiện hành.

Mã truy cập thường gặp:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null && authentication.isAuthenticated()) {
    String username = authentication.getName();
    // Sử dụng username cho nghiệp vụ có kiểm soát quyền.
}
```

Đây là **snippet bên trong ứng dụng Spring Security**, không phải file Java chạy độc lập. Phải lưu ý `getContext()` có thể cung cấp một context **rỗng**, nên `getAuthentication()` có thể là `null`. Đừng coi một context object tồn tại đồng nghĩa request đã xác thực.

### 2.1. Chiến lược mặc định MODE_THREADLOCAL

Theo cấu hình Servlet thông dụng, `SecurityContextHolder` dùng `MODE_THREADLOCAL`. Về mặt ý tưởng, mỗi thread có ô riêng:

```text
Thread A --> ThreadLocal<SecurityContext> = Alice
Thread B --> ThreadLocal<SecurityContext> = null / empty
Thread C --> ThreadLocal<SecurityContext> = Bob
```

Tất cả cùng gọi `SecurityContextHolder.getContext()` nhưng đọc **slot của thread đang chạy**, không đọc một biến toàn cục dùng chung. Security filters đặt context phù hợp trong phần xử lý request và dọn nó khi kết thúc phạm vi xử lý.

Spring Security 6 có các thành phần như `SecurityContextHolderFilter` và `SecurityContextRepository`. Repository nạp/lưu context theo chính sách request/session; **khác** với việc `SecurityContextHolder` lưu tạm giá trị trong thread hiện hành. Không nên nhầm “lưu SecurityContext trong session cho request sau” với “truyền SecurityContext qua một worker thread trong cùng tác vụ”.

### 2.2. Thread pool làm vấn đề rõ hơn

Servlet container và worker executor đều **tái sử dụng thread** để xử lý nhiều request/task. Các thread này không có quan hệ cha–con bền vững với request logic. Một task nộp từ request A không có bảo đảm được chạy trong thread A, và task B có thể dùng lại thread đã chạy task A.

Lỗi nguy hiểm:

```java
// PHẢN VÍ DỤ: không được sao chép vào production
SecurityContextHolder.setContext(capturedContext);
doWork();
// Không khôi phục hoặc clear context -> có thể rò rỉ sang task sau.
```

Nếu task lỗi giữa chừng, tình hình càng nghiêm trọng. Bảo vệ chuẩn là dùng wrapper của Spring Security hoặc khôi phục trạng thái trong `finally`, không chỉ gọi `clearContext()` sau một dòng có thể ném exception.

## 3. Java 17 chạy độc lập: ThreadLocal không tự truyền qua executor

Ví dụ thuần JDK dưới đây minh họa giới hạn này bằng một `ThreadLocal<String>`. Nó **không dùng Spring Security**, chỉ làm rõ nguyên tắc nền tảng có thể kiểm chứng. File `ThreadLocalBoundaryDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ThreadLocalBoundaryDemo {
    private static final ThreadLocal<String> ACTOR = new ThreadLocal<>();

    private static String show(String value) {
        return value == null ? "<none>" : value;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            ACTOR.set("alice"); // Giả lập request thread.
            System.out.println("request=" + show(ACTOR.get()));

            String before = worker.submit(() -> ACTOR.get()).get();
            System.out.println("worker-before=" + show(before));

            // Capture dữ liệu cụ thể ở request thread, truyền khi submit.
            String capturedActor = ACTOR.get();
            String during = worker.submit(() -> {
                String previous = ACTOR.get();
                try {
                    ACTOR.set(capturedActor);
                    return ACTOR.get();
                } finally {
                    if (previous == null) {
                        ACTOR.remove();
                    } else {
                        ACTOR.set(previous);
                    }
                }
            }).get();
            System.out.println("worker-with-scope=" + during);

            String after = worker.submit(() -> ACTOR.get()).get();
            System.out.println("worker-after=" + show(after));
        } finally {
            ACTOR.remove();
            worker.shutdown();
        }
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac ThreadLocalBoundaryDemo.java
java ThreadLocalBoundaryDemo
```

Stdout chính xác:

```text
request=alice
worker-before=<none>
worker-with-scope=alice
worker-after=<none>
```

Giải thích:
1. Thread chạy `main` có `ACTOR="alice"`.
2. `newSingleThreadExecutor` có worker thread riêng, vì vậy slot `ThreadLocal` ban đầu của worker rỗng.
3. Ta capture **giá trị rõ ràng** khi nộp task rồi gắn nó cho khoảng chạy task, không phụ thuộc một tên thread.
4. `finally` khôi phục giá trị trước đó hoặc `remove()`; task sau không nhìn thấy Alice.

Đây là bài thực hành về **lifecycle của ThreadLocal**. Với Spring Security, không cần tự viết bản sao wrapper như trên: hãy dùng các `DelegatingSecurityContext*` wrapper để tránh quên propagation và cleanup.

## 4. Điều gì xảy ra với mỗi loại async?

| Kỹ thuật | Context ở thread đang gọi | Context ở thread thực thi | Điều cần làm |
| --- | --- | --- | --- |
| Controller/service đồng bộ trong cùng servlet request thread | Có thể có Authentication | Cùng thread, thường vẫn thấy context | Không cần propagation riêng |
| `new Thread(runnable)` | Có Authentication | Với `MODE_THREADLOCAL` mặc định **không tự nhận** | Tránh tự tạo thread trong web app; nếu thật sự cần, wrapper/capture có kiểm soát |
| `ExecutorService.submit(...)` | Có Authentication khi nộp | Task chạy worker thread pool riêng | Dùng `DelegatingSecurityContextExecutorService` hoặc wrapper task |
| `CompletableFuture.supplyAsync(...)` không truyền executor | Có Authentication khi gọi | Thường chạy ForkJoin common pool | Cung cấp executor được cấu hình propagation; không tin default |
| `@Async` | Caller có Authentication | Phương thức chạy trên executor Spring | Cấu hình `DelegatingSecurityContextAsyncTaskExecutor` / cơ chế context propagation |
| Spring MVC trả `Callable<T>` | Security filter xử lý request | MVC gọi Callable trên executor | Spring Security có tích hợp `WebAsyncManagerIntegrationFilter` cho `Callable` chuẩn |
| Spring MVC `DeferredResult<T>` | Thread xử lý request đầu tiên có context | App tự hoàn thành kết quả từ thread khác | **Không có bảo đảm** tự truyền context sang thread do app quản lý |
| Scheduler / message listener | Không nhất thiết có HTTP request | Thread scheduler/consumer | Dùng service identity rõ ràng, không đoán user từ ThreadLocal |
| Servlet async tự quản lý `AsyncContext` | Request có context | Callback/dispatch có thể chạy ở thread khác | Kiểm tra lifecycle và integration của từng API/filter; không giả định tự truyền |
| Virtual threads Java mới | Mỗi virtual thread có ThreadLocal riêng | Thread mới khác request thread | Phải truyền context có chủ đích; virtual thread không biến ThreadLocal thành task context |

**Đừng nhầm `Callable` của Spring MVC với mọi `Callable` của Java.** Tích hợp tự động của Spring Security áp dụng cho một luồng MVC cụ thể; nếu bạn tự tạo `ExecutorService.submit(Callable)` thì không được mặc định hưởng tích hợp đó.

### 4.1. Spring MVC Callable

Ví dụ:

```java
@GetMapping("/whoami")
public Callable<String> whoAmI() {
    return () -> {
        Authentication a =
            SecurityContextHolder.getContext().getAuthentication();
        return a == null ? "<none>" : a.getName();
    };
}
```

Đoạn này là **method controller minh họa**, không phải Java class độc lập. Khi Spring Security Servlet tích hợp đúng với Spring MVC async, `WebAsyncManagerIntegrationFilter` có thể đưa context phù hợp vào thread chạy `Callable`. Việc test trong một ứng dụng không có Spring Security filter hoặc dùng custom MVC executor/filters sai thứ tự có thể cho kết quả khác.

Điều này **không có nghĩa** có thể tiếp tục tạo thread khác bên trong `Callable` rồi luôn thấy cùng context. Khi `Callable` lại gọi `CompletableFuture.supplyAsync`, đó là một thread boundary **mới**.

### 4.2. DeferredResult và CompletableFuture

`DeferredResult` cho phép một thread khác cung cấp kết quả sau khi servlet request ban đầu đã rời thread. Spring Security không tự biết bạn nộp mọi task nào để hoàn tất `DeferredResult`. Nếu callback cần danh tính, hãy truyền dữ liệu nghiệp vụ cần thiết hoặc dùng wrapper executor được cấu hình.

`CompletableFuture` cũng có thể đổi thread giữa các stage: `thenApply` đôi khi chạy trên thread hoàn tất stage trước, còn `thenApplyAsync` có thể dùng executor khác. Đừng để code phân quyền ngầm gọi `SecurityContextHolder` tại một stage mà bạn không kiểm soát executor và context. Thay vào đó, phân quyền **trước khi schedule**, rồi truyền các IDs/claims tối thiểu cần thiết; với tác vụ có quyền thực thi muộn cần **xác minh lại** khi chạy.

## 5. Vì sao MODE_INHERITABLETHREADLOCAL không phải cách chữa tổng quát?

Ngoài `MODE_THREADLOCAL`, `SecurityContextHolder` có các strategy khác:

- `MODE_INHERITABLETHREADLOCAL`: dùng `InheritableThreadLocal` để thread con mới có thể thừa hưởng context của thread tạo ra nó theo cơ chế inheritance.
- `MODE_GLOBAL`: một context chung cấp JVM, **không phù hợp web server nhiều người dùng**.

Cả hai đều không phải lối tắt an toàn cho request trên thread pool.

**Rủi ro với `MODE_INHERITABLETHREADLOCAL`:**

1. Thread trong pool thường được tạo **trước** request, hoặc được tạo bởi thread quản lý pool, không phải thread của Alice.
2. Thread pool sống lâu và được tái sử dụng. Nếu một worker thừa hưởng context tại thời điểm tạo, việc Alice logout/đổi người dùng không nhất thiết cập nhật state này theo yêu cầu.
3. Inheritance có thể mang **tham chiếu tới SecurityContext mutable**, không phải bản snapshot bất biến độc lập.
4. Dễ vô tình lộ danh tính xuyên request nếu dựa vào context thừa hưởng mà không dọn.
5. Không kiểm soát rõ **thời điểm** và **đối tượng** được phép mang context.

`MODE_GLOBAL` còn nguy hiểm hơn với web application vì một context chung có thể đại diện nhầm người dùng cho các request khác nhau. Đừng đổi strategy trên toàn JVM để sửa một lỗi `@Async`. Việc thay `SecurityContextHolder.setStrategyName(...)` trong ứng dụng đang chạy cũng ảnh hưởng toàn hệ thống, không nên xem như cấu hình cục bộ cho task.

**Giải pháp đúng:** lựa chọn propagation ở **ranh giới giao việc** (task submission) hoặc dùng framework integration, đi kèm cleanup.

## 6. DelegatingSecurityContextRunnable và Callable

Spring Security cung cấp wrapper nhằm thiết lập `SecurityContextHolder` phù hợp trong thời gian task chạy, sau đó khôi phục context có trước trên worker thread.

Ví dụ **snippet thuộc ứng dụng Spring Security**, không phải file biên dịch riêng:

```java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;

SecurityContext capturedContext = SecurityContextHolder.getContext();

Runnable originalTask = () -> {
    String name = SecurityContextHolder.getContext()
        .getAuthentication().getName();
    performWorkFor(name); // Phương thức nghiệp vụ giả định của ứng dụng.
};

Runnable securedTask =
    new DelegatingSecurityContextRunnable(originalTask, capturedContext);

executor.execute(securedTask);
```

Với `Callable<T>` có wrapper `DelegatingSecurityContextCallable<T>` tương tự. Các constructor/factory method có thể nhận context cụ thể, hoặc capture context tại **thời điểm tạo wrapper** tùy cách gọi. Thời điểm capture phải nằm trong phạm vi caller có Authentication hợp lệ; nếu để wrapper tự lấy context sau khi request kết thúc, dễ nhận context rỗng hoặc sai.

**Quan trọng về tham chiếu mutable:** `capturedContext` ở trên là một **tham chiếu** tới `SecurityContext` hiện có. Việc truyền một tham chiếu chung qua thread có thể gặp race và thay đổi Authentication ngoài ý muốn nếu code cập nhật context đồng thời. Khi cần “snapshot” tương đối độc lập, có thể tạo `SecurityContextHolder.createEmptyContext()` rồi đặt `Authentication` đã được lựa chọn. Tuy nhiên bản thân `Authentication`/principal/credentials có thể là object mutable; đây không tự động là deep copy. Cân nhắc truyền **chỉ user ID và quyền cần thiết** rồi tái kiểm tra authorization tại thời điểm chạy.

### 6.1. Tự xử lý propagation thủ công nếu không có wrapper

Trong trường hợp tích hợp framework yêu cầu callback đặc biệt, nguyên tắc là:

```java
SecurityContext previous = SecurityContextHolder.getContext();
try {
    SecurityContextHolder.setContext(contextForThisTask);
    doWork(); // Snippet: doWork là phương thức nghiệp vụ.
} finally {
    // Khôi phục trạng thái của worker thread nếu đã có.
    SecurityContextHolder.setContext(previous);
}
```

Nhưng lưu ý: `getContext()` có thể **khởi tạo một empty context** nếu chưa có. Cách restore ở trên chỉ là phác thảo; ứng dụng thực cần xác định khi nào nên `clearContext()` thay vì gắn lại một empty context, và xem lại strategy được dùng. **Ưu tiên DelegatingSecurityContext wrappers** đã xử lý ranh giới lifecycle.

Đừng bao giờ đặt context mà không bảo đảm dọn trong `finally`, kể cả khi callable bị timeout, ném runtime exception, bị hủy hoặc thread pool tiếp tục xử lý việc khác.

## 7. DelegatingSecurityContextExecutorService: giữ context khi submit task

Khi có nhiều task, thay vì tự wrap từng `Runnable`/`Callable`, có thể bọc một `ExecutorService` bằng `DelegatingSecurityContextExecutorService`.

File minh họa Spring config `SecureExecutorConfig.java` (cần Spring Security dependency):

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutorService;

@Configuration
public class SecureExecutorConfig {
    @Bean(destroyMethod = "shutdown")
    ExecutorService securityContextExecutor() {
        ExecutorService delegate = Executors.newFixedThreadPool(4);
        return new DelegatingSecurityContextExecutorService(delegate);
    }
}
```

Dùng từ service hoặc controller có `SecurityContext` hiện tại:

```java
Future<String> task = securityContextExecutor.submit(() -> {
    Authentication a =
        SecurityContextHolder.getContext().getAuthentication();
    return a == null ? "<none>" : a.getName();
});
String resolved = task.get();
```

Đây là snippet: `securityContextExecutor` phải được inject từ bean phía trên; cần import `Future`, `Authentication`, `SecurityContextHolder`. Khi dùng wrapper constructor **không truyền một SecurityContext cố định**, Spring Security có thể capture context của thread đang **submit** task rồi thiết lập trên worker khi nó chạy. Không nên tự tạo wrapper ở một thread khác sau khi mất authentication và mong nó tự lấy đúng user.

**Cảnh báo:** constructor có overload nhận một `SecurityContext` **cố định**. Chế độ đó phù hợp một số tác vụ có service identity rõ ràng nhưng **không** phải lựa chọn mặc định nếu pool phục vụ nhiều người dùng. Nếu một shared executor luôn dùng context Alice, mọi task Bob submit sẽ có nguy cơ chạy dưới danh tính Alice.

### 7.1. Kích thước pool và cancellation

Context propagation không giải quyết vấn đề hiệu năng và an toàn của task queue:
- Pool quá nhỏ có thể bị nghẽn hoặc starvation; không gọi `Future.get()` ở cùng worker mà có thể tự deadlock.
- Pool quá lớn có thể gây cạn tài nguyên; cần giới hạn queue và rejection policy.
- Task bị chờ lâu vẫn có thể giữ reference tới Authentication/claims; giảm retention, giới hạn timeout.
- Khi task chạy muộn, quyền của người dùng có thể đã đổi; không xem “đã authenticated lúc submit” là authorization vĩnh viễn.
- Khi ứng dụng shutdown, hủy/đợi task theo quy tắc sản phẩm và dọn tài nguyên.

## 8. @Async với DelegatingSecurityContextAsyncTaskExecutor

Spring `@Async` chuyển lời gọi phương thức qua proxy và executor. Không có propagation phù hợp, `SecurityContextHolder.getContext().getAuthentication()` ở thread async có thể là `null` mặc dù request thread đã đăng nhập.

### 8.1. Cấu hình async executor an toàn

File `AsyncSecurityConfig.java`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
public class AsyncSecurityConfig {
    @Bean("secureTaskExecutor")
    AsyncTaskExecutor secureTaskExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("secure-task-");
        pool.initialize();

        return new DelegatingSecurityContextAsyncTaskExecutor(pool);
    }
}
```

`ThreadPoolTaskExecutor` là Spring executor; `DelegatingSecurityContextAsyncTaskExecutor` bọc nó và thực hiện propagation trong phạm vi task. Với constructor này, **không cố định sẵn context Alice trong bean singleton**; wrapper lấy context phù hợp lúc task được submit.

Quyết định kích thước pool/queue/rejection/metrics nên dựa trên hệ thống thực. Bean ví dụ chưa chứa cơ chế shutdown/drain tùy biến; khi production cần quản lý lifecycle của executor và context startup/shutdown phù hợp. Trong ứng dụng Spring Boot, các bean executor phải được thiết kế tránh xung đột tên với executor mặc định được tự cấu hình.

### 8.2. Service và controller gọi @Async

File `AsyncIdentityService.java`:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class AsyncIdentityService {
    @Async("secureTaskExecutor")
    public CompletableFuture<String> currentUsername() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        String username = authentication == null
            ? "<none>"
            : authentication.getName();

        return CompletableFuture.completedFuture(username);
    }
}
```

File `IdentityController.java`:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {
    private final AsyncIdentityService service;

    public IdentityController(AsyncIdentityService service) {
        this.service = service;
    }

    @GetMapping("/api/async-name")
    public CompletableFuture<String> asyncName() {
        return service.currentUsername();
    }
}
```

Giải thích:
- Controller được gọi trong HTTP request thread; Spring Security đã thiết lập `SecurityContext`.
- Controller gọi **bean service khác** qua Spring proxy.
- `@Async("secureTaskExecutor")` khiến service thực thi ở worker executor, được wrapper truyền context đang có tại thời điểm schedule.
- Service chỉ đọc Authentication và trả tên user; khi kết thúc wrapper khôi phục/dọn context trên worker.
- Controller trả `CompletableFuture<String>`, Spring MVC có thể xử lý kết quả theo async lifecycle. Response body minh họa cho Alice là `alice`, nhưng chỉ khi route được bảo vệ và request thực sự đã được xác thực thành Alice.

**Lỗi self-invocation:** nếu method `@Async` được gọi từ phương thức khác **trong cùng đối tượng** (ví dụ `this.currentUsername()`), proxy `@Async` có thể bị bypass và method chạy đồng bộ. Khi đó test “principal vẫn thấy đúng” là **false positive**, vì không có thread boundary thật. Hãy gọi qua Spring-managed proxy từ bean khác và xác minh tên thread khi chẩn đoán.

### 8.3. Spring Security chain minh họa

File `SecurityConfig.java`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là cấu hình **demo để có authentication rõ ràng**; một Resource Server thực tế có thể dùng `oauth2ResourceServer(...jwt(...))`, web login có thể dùng session/cookie, tùy kiến trúc. Truyền `SecurityContext` qua thread boundary **không thay đổi** nguyên tắc CSRF hoặc authorize endpoint. Nếu dùng cookie/session, tiếp tục bảo vệ CSRF thích hợp; nếu API thuần Bearer, quyết định CSRF dựa trên cách credential được gửi, không dựa trên executor.

Các class trên là mã **bên trong dự án Spring Boot 3/Spring Security 6 với Java 17+**, cần `spring-boot-starter-web`, `spring-boot-starter-security` và `spring-boot-starter-aop` khi dùng `@Async` proxy tùy project/dependency. Chúng không biên dịch độc lập bằng `javac` nếu thiếu Spring libraries, class khởi động `@SpringBootApplication` và cấu hình build.

## 9. Kiểm thử propagation, isolation và cleanup

### 9.1. Test @Async thật với Mock SecurityContext

Test file `AsyncSecurityContextTest.java` trong Spring Boot project:

```java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class AsyncSecurityContextTest {
    @Autowired
    AsyncIdentityService service;

    @Test
    @WithMockUser(username = "alice")
    void contextIsAvailableInAsyncService() throws Exception {
        String name = service.currentUsername()
            .get(5, TimeUnit.SECONDS);
        assertEquals("alice", name);
    }

    @Test
    @WithMockUser(username = "bob")
    void nextTaskUsesItsOwnSubmittersContext() throws Exception {
        String name = service.currentUsername()
            .get(5, TimeUnit.SECONDS);
        assertEquals("bob", name);
    }
}
```

Test này dùng Spring Test và `spring-security-test`. `@WithMockUser` thiết lập Authentication trên **test thread**, wrapper chuyển context tới `@Async` worker. Thực tế hai test có thể được chạy thứ tự bất kỳ; mỗi test độc lập mong đợi đúng user của mình. Nó chứng minh propagation qua Spring async executor, **không** chứng minh JWT signature verification hay HTTP filter chain end-to-end.

Chạy trong Maven project:

```bash
mvn -Dtest=AsyncSecurityContextTest test
```

Với Gradle tùy cấu trúc project:

```bash
./gradlew test --tests AsyncSecurityContextTest
```

Để chắc chắn `@Async` không bị bypass, có thể bổ sung kiểm tra tên thread trong môi trường test hoặc test dùng `CountDownLatch` kiểm tra invocation bất đồng bộ. Không nên dùng `Thread.sleep` với thời gian cố định rồi giả định kết quả deterministic.

### 9.2. Test thiếu propagation để tránh false confidence

Một test riêng có thể gọi **raw** `Executors.newSingleThreadExecutor()` từ test thread đã có `@WithMockUser`, sau đó gọi `SecurityContextHolder.getContext().getAuthentication()` trên worker. Với `MODE_THREADLOCAL` mặc định, worker sẽ không tự nhận `Authentication` của test thread. Khi dùng shared wrapper, cùng task sẽ thấy context được truyền đúng.

Đừng lạm dụng test này nếu ứng dụng cố tình thay strategy toàn JVM; test phải xác định baseline `MODE_THREADLOCAL` và cleanup đúng.

### 9.3. Test chống rò rỉ user giữa hai task

Nên có integration test theo trình tự **Alice → Bob → Anonymous** trên một **worker thread được tái sử dụng**:
1. Submit task từ context Alice, xác nhận worker thấy Alice.
2. Submit task từ context Bob, xác nhận worker thấy Bob.
3. Submit task từ context trống, xác nhận worker không còn Alice/Bob.
4. Ném exception trong task Alice, sau đó submit task Bob và xác nhận không bị ảnh hưởng.
5. Kiểm tra cancellation, timeout, error dispatch nếu sản phẩm có các luồng đó.

Sử dụng `newSingleThreadExecutor` hoặc pool có một worker giúp tái sử dụng cùng thread rõ ràng hơn. Test propagation chỉ cho Alice thấy Alice mà không kiểm tra cleanup là chưa đủ để chứng minh không lộ danh tính.

### 9.4. SecurityContext propagation không phải authorization

Test quan trọng khác: người dùng Alice nộp task lúc có quyền, quyền bị thu hồi trước khi task chạy. Nếu task ghi dữ liệu nhạy cảm dựa hoàn toàn trên `Authentication` đã capture ở thời điểm submit, nó có thể thực hiện hành động mà người dùng **không còn được phép**. Với nghiệp vụ quan trọng, **kiểm tra lại authorization khi chạy**, dùng domain user ID/tenant ID và service credentials có phạm vi rõ ràng thay vì tin vào một snapshot cũ.

## 10. ThreadLocal không phải nơi lưu mọi ngữ cảnh bất đồng bộ

### 10.1. MDC và tracing là phạm vi khác

`MDC` (logging correlation IDs) cũng thường dùng `ThreadLocal` nhưng **không phải SecurityContext**. Bọc task bằng `DelegatingSecurityContextAsyncTaskExecutor` không đồng nghĩa trace ID, locale, transaction hoặc MDC tự được truyền. Ngược lại, `TaskDecorator` sao chép MDC không có nghĩa đã truyền `Authentication` an toàn.

Nếu cần cả hai, xác định rõ các context riêng biệt, dùng framework hỗ trợ propagation theo version, và kiểm tra cleanup cho từng loại. **Không** đưa bearer token hoặc full credential vào MDC.

### 10.2. Transaction và EntityManager

Một `@Transactional` trên request thread không tự “đi qua” `@Async`. Transaction state, persistence context/JPA `EntityManager` thường gắn với thread hoặc scope riêng. Worker async nên mở transaction của chính nó nếu cần; đừng chuyển tiếp một entity đang lazy-load hoặc resource thuộc transaction đã đóng mà không đánh giá consistency.

### 10.3. Reactor và reactive stack là chuyện khác

Trong WebFlux/Reactor, security context được truyền qua **Reactor Context** thay vì giả định `ThreadLocal` thông thường. Bài này áp dụng cho **Spring Security Servlet**. Khi Servlet gọi reactive pipeline hoặc reactive code gọi thread pool, phải hiểu điểm giao nhau của các mô hình context và dùng tích hợp tương ứng; đừng dùng `SecurityContextHolder.getContext()` trên mọi reactive callback rồi mong nó luôn đúng.

### 10.4. Virtual threads và structured concurrency

Java virtual threads là thread thực có semantics `ThreadLocal` riêng, nhưng task chạy trên một virtual thread mới **không tự có SecurityContext của servlet request thread**. ThreadLocal trong carrier/worker không phải giải pháp chuyển user context qua virtual thread. Hãy dùng propagation được hỗ trợ và giới hạn retention; tránh sử dụng `InheritableThreadLocal` để “lây” quyền tới mọi child thread.

Nếu sử dụng Java mới có structured concurrency hoặc scoped values, cần xem quy tắc API và tích hợp framework của phiên bản thực tế. Chúng không tự thay thế cơ chế `SecurityContextHolder` của Spring Security 6 Servlet.

## 11. Khi nào nên truyền principal ID thay cho toàn SecurityContext?

Có sự khác biệt đáng kể giữa task **ngắn, ngay trong request** và job **kéo dài sau request**.

### Task ngắn, synchronous-to-async

Ví dụ đọc một số dữ liệu trong vài mili giây, tách phần tính toán từ controller rồi chờ kết quả. Nếu task thật sự cần authorization/current principal trong cùng security scope, có thể dùng `DelegatingSecurityContext*` wrapper, đo hiệu năng và test cleanup.

### Background job kéo dài hoặc queue

Ví dụ tạo hóa đơn cuối ngày, xử lý ảnh, gửi email, đối soát tiền hoặc xử lý message sau hàng phút. **Không nên** serialize, đưa vào queue hay giữ mãi `SecurityContext`/bearer token của người dùng:
- Token có thể hết hạn hoặc bị thu hồi trước khi job chạy.
- Principal/Auth object có thể chứa dữ liệu nhạy cảm, không phù hợp lưu vào queue/log.
- Task được retry trên máy khác không có `ThreadLocal` của HTTP request.
- Quyền có thể thay đổi sau khi người dùng gửi lệnh.

Thiết kế tốt hơn:
1. Trong HTTP request, **authenticate + authorize thao tác nộp job**.
2. Lưu `jobId`, `requesterUserId`, `tenantId`, loại thao tác, input đã validate và metadata audit; không lưu raw token.
3. Worker chạy dưới **service identity** được cấp đúng quyền nghiệp vụ.
4. Nếu job thực thi hành động cần quyền hiện tại của người dùng, kiểm tra lại quyền/ownership tại lúc chạy.
5. Audit tách bạch **người khởi tạo** và **dịch vụ thực thi**, không giả mạo SecurityContext của một người đã logout.

### Gọi downstream API thay mặt người dùng

Nếu tác vụ cần gọi service khác **on behalf of** user, propagation `SecurityContext` chưa tự lấy được access token hợp lệ cho downstream. Sử dụng giải pháp OAuth2 Client/Authorized Client/token exchange phù hợp kiến trúc, scope/audience đúng và token handling an toàn. Không copy `Authentication.getCredentials()` tùy tiện, không ghi log Authorization header và không dùng token đã hết hạn.

## 12. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Controller thấy principal, `@Async` thấy `null` | Async thread không tự nhận ThreadLocal | Sử dụng `DelegatingSecurityContextAsyncTaskExecutor`, test proxy `@Async` |
| `CompletableFuture.supplyAsync` không thấy Authentication | Chạy ở common pool/worker khác | Cấp executor có propagation hoặc truyền user ID an toàn |
| Test `@Async` vẫn chạy cùng thread | Self-invocation bỏ qua proxy | Gọi qua Spring-managed bean khác; test thực sự đổi thread |
| Bob thấy principal Alice trong background worker | Không dọn context hoặc dùng fixed context trong shared executor | Khôi phục trong `finally`; sửa wrapper; test Alice/Bob/anonymous |
| Thử `MODE_INHERITABLETHREADLOCAL` vẫn không được | Pool được tạo trước hoặc tái sử dụng thread | Dùng wrapper lúc submit, không dựa vào inheritance |
| `SecurityContextHolder.setStrategyName(MODE_GLOBAL)` “có tác dụng” | Chia sẻ context trên toàn JVM | **Không dùng trong web app đa người dùng** |
| MVC `Callable` chạy đúng nhưng `DeferredResult` không | Tích hợp framework khác nhau | Tự kiểm soát callback executor/capture có phạm vi |
| Sau logout, job vẫn chạy dưới quyền cũ | Context đã được capture và không có revalidation | Dùng domain IDs + tái kiểm tra quyền/service identity |
| MDC có trace ID nhưng principal vẫn rỗng | MDC và SecurityContext truyền độc lập | Cấu hình propagation cho từng loại context |
| Spring Security context biến mất khi request kết thúc | Đó là cleanup theo lifecycle | Không dựa vào request thread sau khi hoàn tất response |
| `SecurityContext` được lưu trong HttpSession nhưng task async vẫn rỗng | Repository và ThreadLocal giải quyết hai bài toán khác | Truyền context qua thread boundary một cách rõ ràng |

Quy trình debug:
1. Ghi nhận **tên thread** ở nơi submit và nơi task chạy (không log token/PII).
2. Kiểm tra `SecurityContextHolderStrategy` đang dùng và cách các filter set/clear context.
3. Xác định task được submit **trước hay sau** khi request thread mất context.
4. Kiểm tra wrapper/`@Async` executor bean thực sự được sử dụng; phân biệt tự gọi method và gọi qua proxy.
5. Chạy test tái sử dụng pool cùng một worker để phát hiện context leak.
6. Kiểm tra cả quyền nghiệp vụ, session/token expiry, transaction và downstream trust boundary.
7. Chỉ thêm propagation ở đúng ranh giới cần thiết; không đổi strategy toàn JVM để chữa cháy.

## 13. Checklist thực hành

- [ ] Hiểu rằng `SecurityContextHolder` mặc định dùng `MODE_THREADLOCAL` trong Spring Security Servlet.
- [ ] Không trông chờ `ThreadLocal` tự theo `ExecutorService`, `@Async`, `CompletableFuture` hay thread mới.
- [ ] Không đổi sang `MODE_GLOBAL` hoặc `MODE_INHERITABLETHREADLOCAL` để giải quyết chung vấn đề với thread pool.
- [ ] Với async task ngắn cần current Authentication, dùng `DelegatingSecurityContextRunnable/Callable/ExecutorService/AsyncTaskExecutor` đúng phạm vi.
- [ ] Tạo wrapper khi caller có context hợp lệ, không giữ một context của user cố định trong shared executor.
- [ ] Khôi phục/clear worker context trong `finally`, kể cả khi task ném exception.
- [ ] Xác nhận Spring MVC `Callable` integration và xử lý riêng `DeferredResult`/custom callbacks.
- [ ] Có integration test cho Alice → Bob → Anonymous và case exception trên cùng worker.
- [ ] Không hiểu propagation là được cấp quyền vô hạn; tác vụ chạy muộn phải tái kiểm tra authorization.
- [ ] Background jobs truyền user/tenant/job IDs và dùng service identity; tránh serialize token hoặc full SecurityContext.
- [ ] Tách propagation của SecurityContext khỏi MDC, transaction và Reactor Context.
- [ ] Không ghi raw token, credential hoặc principal nhạy cảm vào logs khi debug bất đồng bộ.

**Kết luận:** Trong Spring Security Servlet, `SecurityContextHolder` không phải một “biến toàn cục theo request nghiệp vụ”; với `MODE_THREADLOCAL` nó sống trong **thread đang thực thi**. Chuyển sang `@Async`/executor/DeferredResult là ranh giới mới, cần propagation được kiểm soát hoặc truyền dữ liệu nghiệp vụ tối thiểu. Hãy dùng các wrapper `DelegatingSecurityContext*` cho việc ngắn hạn, luôn dọn context sau task, và không dùng context đã capture để thay cho authorization ở thời điểm xử lý thực tế.
