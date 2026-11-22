# Truyền ngữ cảnh khi chuyển luồng, chạy @Async hoặc thực thi tác vụ nền

> **Chủ đề cha:** Ngữ cảnh bảo mật. Tài liệu dành cho Java 17+, Spring Boot 3.x, Spring Security 6.x trên **Servlet/Spring MVC**. Trọng tâm: tại sao `SecurityContextHolder` có danh tính trong HTTP request nhưng thiếu danh tính khi chuyển sang worker thread; cách truyền có chủ đích bằng `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor` và `DelegatingSecurityContextAsyncTaskExecutor`; cách dùng `@Async`, `CompletableFuture`, Spring MVC `Callable` và công việc chạy theo lịch; cách tránh rò danh tính, dùng quyền lỗi thời hoặc “giả mạo” principal.

## 1. Bài toán: trong controller có Alice, trong @Async lại null

Ví dụ một endpoint đã xác thực xử lý request từ Alice:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String username = authentication.getName(); // alice trong ví dụ
~~~

Sau đó code gọi một method `@Async`:

~~~java
@Async
public void generateReport() {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

    // Có thể null vì method chạy trên worker thread khác.
}
~~~

**Nguyên nhân phổ biến:** `SecurityContextHolder` trong Servlet stack mặc định dùng `ThreadLocal`. Nó giữ `SecurityContext` theo **thread hiện tại**, không lưu một biến global cho toàn JVM và không tự theo mọi task được gửi sang executor.

~~~text
Servlet thread A                              Worker thread B
  |
  +--> SecurityContextHolder                    SecurityContextHolder
  |       Authentication(Alice)                     Authentication=null
  |
  +--> @Async / executor.submit(task) ----------> Task chạy trên B
                                                  |
                                                  +--> Không tự có identity A
~~~

Điều đó **không có nghĩa Alice mất đăng nhập**. Trên request thread, Spring Security đã xác thực Alice. Worker thread là một execution khác nên không tự nhận context. Khi tác vụ thật sự được phép thực hiện **thay mặt Alice**, phải chọn cơ chế context propagation thích hợp. Khi tác vụ là **system job** hoặc chạy nhiều giờ, cách đúng thường là **service identity + reauthorization**, không phải sao chép nguyên session của Alice.

### 1.1. Các đối tượng không được nhầm lẫn

| Đối tượng | Vai trò | Không tự làm |
| --- | --- | --- |
| `Authentication` | Chứa principal, authorities, trạng thái xác thực, có thể có credentials/details | Không chứng minh quyền sở hữu mọi tài nguyên |
| `SecurityContext` | Bao chứa một Authentication hiện tại | Không phải database, token revocation store |
| `SecurityContextHolder` | Truy cập SecurityContext cho execution hiện tại | Không tự chia sẻ context qua mọi thread |
| `Executor`/`ExecutorService` | Quản lý việc chạy task trên threads | Không tự xác thực danh tính |
| `AsyncTaskExecutor` | Giao diện Spring Task cho công việc bất đồng bộ | Không mặc định đảm bảo propagation trong mọi cấu hình |
| `DelegatingSecurityContextRunnable` | Đưa context vào worker quanh một `Runnable` rồi cleanup | Không cập nhật role từ database |
| `DelegatingSecurityContextCallable` | Tương tự cho `Callable<T>` | Không thay Future timeout/error handling |
| `DelegatingSecurityContextExecutor` | Bọc task khi `execute`; có thể lấy context tại submit time | Không tự bảo vệ quyền domain |
| `DelegatingSecurityContextAsyncTaskExecutor` | Wrapper tích hợp Spring `@Async`/`AsyncTaskExecutor` | Không biến job dài hạn thành delegation vĩnh viễn |

**Truyền SecurityContext là mang theo một thông tin đã tồn tại**, không phải tạo bằng chứng xác thực mới. Nếu caller chưa được xác thực hoặc context đã cũ, wrapper không tự sửa vấn đề đó.

## 2. Java 17: chứng minh ThreadLocal không tự chuyển thread

Tạo file độc lập **`ThreadLocalDemo.java`**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadLocalDemo {

    private static final ThreadLocal<String> CURRENT =
        new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool =
            Executors.newSingleThreadExecutor();

        try {
            CURRENT.set("alice");

            System.out.println(
                "request=" + CURRENT.get()
            );

            String fromWorker = pool.submit(
                () -> CURRENT.get()
            ).get();

            System.out.println(
                "worker=" + fromWorker
            );
        } finally {
            CURRENT.remove();
            pool.shutdown();
        }

        System.out.println(
            "after=" + CURRENT.get()
        );
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac ThreadLocalDemo.java
java ThreadLocalDemo
~~~

**Stdout chính xác:**

~~~text
request=alice
worker=null
after=null
~~~

Main thread đặt `"alice"` trong ThreadLocal. Executor tạo worker thread khác, `CURRENT.get()` trên worker không thấy Alice. `CURRENT.remove()` trong `finally` dọn context của main thread. Đây là ví dụ Java thuần để hiểu **cách ly theo thread**; Spring Security có cơ chế context và cleanup riêng, không dùng thẳng `ThreadLocal<String>` như code demo.

### 2.1. Tại sao không dùng static field để chia sẻ user?

~~~java
// SAI trong server nhiều người dùng:
static Authentication CURRENT_AUTHENTICATION;
~~~

Static field dùng chung cho tất cả requests. Alice và Bob có thể ghi đè identity của nhau, làm rò dữ liệu hoặc tăng quyền. Giải pháp đúng là context theo execution, context propagation có kiểm soát hoặc truyền **account ID tin cậy** như một tham số nghiệp vụ.

### 2.2. Ba chế độ SecurityContextHolder

| Strategy | Ý nghĩa | Nguy cơ |
| --- | --- | --- |
| `MODE_THREADLOCAL` | Context gắn với thread hiện tại; mặc định của Servlet | Cần cơ chế handoff nếu chuyển sang worker |
| `MODE_INHERITABLETHREADLOCAL` | Thread mới có thể kế thừa context ở thời điểm thread được tạo | Không phù hợp tự động cho thread pool tái sử dụng; có thể stale/mix user |
| `MODE_GLOBAL` | Context chia sẻ trên JVM | Không dùng trong web server đa người dùng |

Một thread pool thường được tạo lúc startup và tái sử dụng qua hàng nghìn requests. `InheritableThreadLocal` **không sao chép lại context mỗi lần submit task**. Do đó không chữa lỗi `@Async` bằng cách đổi chiến lược toàn JVM sang `MODE_GLOBAL` hoặc tin rằng `MODE_INHERITABLETHREADLOCAL` luôn đúng.

## 3. Vòng đời đúng khi chuyển context sang worker

~~~text
HTTP request của Alice
    |
    v
Spring Security Authentication Filter
    |
    +--> Authentication(Alice) được xác minh
    |
    v
SecurityContextHolder trên servlet thread
    |
    +--> context chứa Alice
    |
    v
Submit task tại T1 qua wrapper
    |
    +--> Capture context của thread submit
    |
    v
Worker thread nhận wrapped Runnable/Callable
    |
    +--> Đặt captured context trong holder của worker
    +--> Thực hiện task/authorization nếu phù hợp
    |
    v
finally
    |
    +--> Clear/restore context theo wrapper implementation
    |
    v
Worker thread trở lại pool để chạy task khác
~~~

**Hai yếu tố quan trọng nhất là thời điểm capture và cleanup.** Nếu capture quá muộn, request context đã bị dọn. Nếu không cleanup, task của Bob trên cùng worker thread có thể vô tình đọc identity Alice.

### 3.1. Cleanup kể cả khi task ném exception

Spring Security `DelegatingSecurityContextRunnable` thiết lập context cho worker, gọi `Runnable.run()` và dọn holder trong `finally`. Vì vậy exception không khiến identity vướng lại trên pool thread theo cơ chế wrapper đó.

Mô hình rút gọn:

~~~java
// Chỉ minh họa nguyên tắc, không phải copy mã nguồn của thư viện.
try {
    SecurityContextHolder.setContext(capturedContext);
    delegate.run();
} finally {
    SecurityContextHolder.clearContext();
}
~~~

Thư viện thực tế có thể dùng `SecurityContextHolderStrategy` và cơ chế restore phù hợp; **ưu tiên wrapper có sẵn thay vì tự xây lại**. Cleanup không tự quan sát hay xử lý lỗi business; caller vẫn phải xử lý Future exception, timeout/cancellation và retry.

### 3.2. “Capture” không nhất thiết là deep copy

`SecurityContext` và `Authentication` có thể là objects mutable. Khi wrapper được tạo với một context, nó **không hứa tạo immutable snapshot sâu** của mọi object và authorities. Nếu hai threads giữ cùng object rồi một thread thay Authentication, có thể xảy ra race.

Không dùng SecurityContext như “tấm vé cấp quyền không thể thay đổi” cho một task chạy dài; quyền có thể bị thu hồi trong database khi task còn đang chờ ở queue. Với tác vụ nhạy cảm, hãy lưu account ID/job ID tin cậy và kiểm tra quyền hiện tại khi thực thi.

## 4. Cách 1: DelegatingSecurityContextRunnable

`org.springframework.security.concurrent.DelegatingSecurityContextRunnable` bọc một Runnable bằng context đã chọn.

~~~java
SecurityContext context =
    SecurityContextHolder.getContext();

Runnable action = () -> {
    Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

    if (current == null) {
        throw new IllegalStateException("Missing security identity");
    }

    System.out.println("worker=" + current.getName());
};

Runnable wrapped =
    new DelegatingSecurityContextRunnable(action, context);

rawExecutor.execute(wrapped);
~~~

Đây là **snippet trong service**: `rawExecutor` phải là một `Executor` được quản lý; cần imports. Nó giả định đang ở caller thread có Authentication đã được framework xác minh. Không gửi `context` giả từ userId hoặc role client tự khai.

### 4.1. Constructor không nhận context

~~~java
Runnable wrapped =
    new DelegatingSecurityContextRunnable(action);
~~~

Constructor shortcut dùng context hiện tại **khi wrapper được tạo**. Nếu wrapper được tạo từ scheduler thread không có user hoặc sau khi request kết thúc, nó sẽ không magically truy vấn user đang đăng nhập ở thread khác.

### 4.2. Callable trả kết quả

~~~java
Callable<String> action = () -> {
    Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

    return current == null ? "none" : current.getName();
};

Callable<String> wrapped =
    new DelegatingSecurityContextCallable<>(
        action, SecurityContextHolder.getContext()
    );

Future<String> future = executorService.submit(wrapped);
~~~

`Callable` có thể trả kết quả hoặc ném exception. `Future.get()` là operation blocking; khi gọi từ HTTP thread phải đặt timeout phù hợp, tránh block vô hạn. Nếu chỉ cần ngắn gọn với Java concurrent APIs, có thể dùng `DelegatingSecurityContextExecutorService`.

## 5. Cách 2: DelegatingSecurityContextExecutor

Thay vì bọc mỗi task, bọc `Executor`:

~~~java
Executor securedExecutor =
    new DelegatingSecurityContextExecutor(rawExecutor);

securedExecutor.execute(() -> {
    Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

    // Dùng principal đã xác thực nếu action được phép.
});
~~~

Với constructor **chỉ nhận delegate**, wrapper lấy SecurityContext của caller tại **thời điểm gọi `execute`**, sau đó bọc task. Điều này phù hợp cho những công việc ngắn hạn gửi từ request đã xác thực.

### 5.1. Một tham số hay hai tham số tạo ra security policy khác nhau

| Constructor | Context được áp dụng |
| --- | --- |
| `new DelegatingSecurityContextExecutor(delegate)` | Context tại thời điểm **submit từng task** |
| `new DelegatingSecurityContextExecutor(delegate, fixedContext)` | **Cùng fixedContext cho mọi task** |

**Bẫy nguy hiểm:** Nếu singleton bean `Executor` được xây với context của **admin Alice** tại request đầu tiên, mọi task do Bob submit sau đó có thể chạy như admin Alice. Đây là lỗi impersonation/privilege escalation.

Fixed context chỉ phù hợp khi application **thật sự** muốn dùng một định danh hệ thống cố định được provision và kiểm soát. Không dùng context của user tình cờ để biến thành “system account”.

### 5.2. CompletableFuture.supplyAsync

`CompletableFuture.supplyAsync(supplier)` không nhận executor thường chạy trên common pool, không mặc định có SecurityContext của request.

~~~java
Executor secured =
    new DelegatingSecurityContextExecutor(rawExecutor);

CompletableFuture<String> result =
    CompletableFuture.supplyAsync(() -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        return auth == null ? "none" : auth.getName();
    }, secured);
~~~

Để những stage khác cũng chạy với policy đúng:

~~~java
CompletableFuture<String> normalized =
    result.thenApplyAsync(String::toUpperCase, secured);
~~~

Tuy nhiên, **không được suy ra mọi stage luôn capture user ban đầu**: một stage có thể được submit từ completion thread, không phải request thread. Nếu stage cần security context, đánh giá đúng **ai đang submit tại thời điểm capture**. Với pipeline nhiều bước, thường nên truyền account ID/tenant ID được xác minh như dữ liệu và reauthorize ở bước thực thi, thay vì dựa vào ThreadLocal qua mọi callback.

`thenApply` không có `Async` cũng không cam kết chạy trên servlet thread; nó có thể chạy trên thread hoàn thành preceding stage. Đừng dùng ThreadLocal của một stage làm căn cứ authorization vô điều kiện.

### 5.3. ExecutorService, scheduling và fixed context

Spring Security còn cung cấp:
- `DelegatingSecurityContextExecutorService`
- `DelegatingSecurityContextScheduledExecutorService`
- `DelegatingSecurityContextTaskExecutor`
- `DelegatingSecurityContextSchedulingTaskExecutor`
- `DelegatingSecurityContextTaskScheduler`

Chọn wrapper đúng interface. Nếu cần `submit(Callable)` hoặc shutdown, một `Executor` thuần không có đủ các method đó. **Scheduled task lặp lại không nên giữ quyền người tạo lịch vô thời hạn**; xem phần job dài hạn.

## 6. Cách 3: @Async + DelegatingSecurityContextAsyncTaskExecutor

Spring Framework `@Async` dùng cơ chế proxy để chạy một method trên executor khác. Nó **không đồng nghĩa** một `ThreadLocal` tự đi theo worker. Với Spring Security Servlet, ta có thể dùng `DelegatingSecurityContextAsyncTaskExecutor`.

~~~text
Controller (request thread, Alice)
    |
    +--> Spring proxy intercept @Async
    |
    +--> AsyncTaskExecutor.submit(...)
           |
           +--> Nếu là raw executor:
           |      worker không có Alice
           |
           +--> Nếu là DelegatingSecurityContextAsyncTaskExecutor:
                  capture context khi submit
                  -> set Alice trong worker
                  -> run method
                  -> cleanup
~~~

Cần cấu hình rõ **bean executor nào** được `@Async("beanName")` chọn.

### 6.1. Tạo hai executors để học

~~~java
@Configuration
@EnableAsync
class AsyncConfig {

    @Bean("rawAsyncExecutor")
    ThreadPoolTaskExecutor rawAsyncExecutor() {
        ThreadPoolTaskExecutor pool =
            new ThreadPoolTaskExecutor();

        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("worker-");
        return pool;
    }

    @Bean("securityAsyncExecutor")
    AsyncTaskExecutor securityAsyncExecutor(
            @Qualifier("rawAsyncExecutor")
            ThreadPoolTaskExecutor raw) {

        return new DelegatingSecurityContextAsyncTaskExecutor(raw);
    }
}
~~~

Đây là **snippet**, phần imports đầy đủ xuất hiện ở demo dưới. `rawAsyncExecutor` là pool thông thường; `securityAsyncExecutor` bọc pool đó và giúp truyền context. Spring quản lý lifecycle của `ThreadPoolTaskExecutor` bean; không tạo pool mới trên mỗi request.

**Không tạo wrapper với SecurityContext fixed của Alice trong cấu hình bean**, vì bean này phải phục vụ nhiều users. Constructor của `DelegatingSecurityContextAsyncTaskExecutor` chỉ nhận delegate cho mục đích capture context của caller khi submit task.

### 6.2. @Async public method trên Spring bean

~~~java
@Service
class UserJobService {

    @Async("securityAsyncExecutor")
    public CompletableFuture<String> getCallerName() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        return CompletableFuture.completedFuture(
            auth == null ? "none" : auth.getName()
        );
    }
}
~~~

Nếu controller inject `UserJobService` từ Spring và gọi `getCallerName()` qua proxy, method body được thực hiện trên worker thread trong context phù hợp. `CompletableFuture.completedFuture` ở **bên trong** method không có nghĩa cả method là synchronous; lời gọi được proxy xử lý trước.

### 6.3. Self-invocation: @Async có thể không chạy bất đồng bộ

~~~java
@Service
class ReportService {

    public void launch() {
        generateAsync(); // Gọi nội bộ cùng object, có thể bypass proxy.
    }

    @Async("securityAsyncExecutor")
    public void generateAsync() {
        // Nếu self-invocation, có thể chạy ngay trên request thread.
    }
}
~~~

Nếu test chỉ thấy Authentication có Alice trong method, có thể method **chưa hề chuyển thread**. Để kiểm tra propagation thật, gọi qua một Spring-managed bean khác, kiểm tra executor, thread name hoặc dùng MockMvc `asyncStarted` với return type thích hợp.

Method private/final và việc tự `new` object thay vì inject bean cũng có thể làm annotation không được proxy intercept theo cấu hình.

### 6.4. Chọn executor và xử lý lỗi

`@Async` không ghi tên executor có thể dùng executor mặc định của framework/Boot. Nếu project có nhiều executor, luôn kiểm tra bean nào nhận task. Method trả `void` có thể báo lỗi qua `AsyncUncaughtExceptionHandler`; method trả `Future`/`CompletableFuture` cần xử lý lỗi completion, timeout, cancellation và rejection.

**Truyền SecurityContext không truyền luôn transaction hoặc MDC**. Transaction-bound context có vòng đời riêng; một `@Transactional` trên request thread không tự kéo transaction ấy vào worker. Nếu worker cần DB transaction, tạo transaction boundary phù hợp trong chính worker/service.

## 7. Demo Spring Boot 3/Java 17: raw executor đối chiếu secured executor

Demo thực hành ba request:

- `GET /probe/direct`: request thread đọc Authentication của Alice.
- `GET /probe/secure`: `@Async("securityAsyncExecutor")` dùng wrapper, worker đọc Alice.
- `GET /probe/raw`: `@Async("rawAsyncExecutor")` không propagate, worker đọc `"none"`.

Ngoài ra `GET /public` công khai. Cả `/probe/secure` và `/probe/raw` **vẫn yêu cầu người dùng đã đăng nhập** trước khi controller cho submit task. Endpoint raw chỉ để quan sát kỹ thuật, **không thực hiện hành động business nhạy cảm**.

Ứng dụng dùng **HTTP Basic + STATELESS** để mỗi HTTP request độc lập; không có server-side session giúp “giữ hộ” danh tính giữa requests. Basic credentials demo chỉ dùng ở localhost.

### 7.1. Dependencies và files

Tạo project Spring Boot 3.x, Spring Security 6.x, Java 17+ có Gradle plugin/repositories/Wrapper. Trong `build.gradle` đã có, thêm block:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là **dependencies**, không phải `build.gradle` độc lập.

~~~text
src/main/java/com/example/asyncidentity/
  AsyncIdentityApplication.java
  SecurityConfig.java
  AsyncConfig.java
  IdentityProbeService.java
  IdentityController.java

src/test/java/com/example/asyncidentity/
  SecurityContextAsyncTest.java
~~~

### 7.2. AsyncIdentityApplication.java

~~~java
package com.example.asyncidentity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncIdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(AsyncIdentityApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig.java

~~~java
package com.example.asyncidentity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/probe/**")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }
}
~~~

Request Basic qua Spring Security filter/AuthenticationManager; user đúng password nhận Authentication, user sai/không gửi credential bị từ chối ở endpoints protected. `STATELESS` không có nghĩa request không có SecurityContext: **trong mỗi request** vẫn có context của user nếu credential được xác minh.

### 7.4. AsyncConfig.java

~~~java
package com.example.asyncidentity;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfig {

    @Bean("rawAsyncExecutor")
    ThreadPoolTaskExecutor rawAsyncExecutor() {
        ThreadPoolTaskExecutor pool =
            new ThreadPoolTaskExecutor();

        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("identity-worker-");
        return pool;
    }

    @Bean("securityAsyncExecutor")
    AsyncTaskExecutor securityAsyncExecutor(
            @Qualifier("rawAsyncExecutor")
            ThreadPoolTaskExecutor raw) {

        return new DelegatingSecurityContextAsyncTaskExecutor(raw);
    }
}
~~~

Trong một ứng dụng production, cần sizing executor theo tải, queue capacity/rejection policy, monitoring, shutdown và giới hạn khối lượng tác vụ. Không dùng unbounded thread pool hoặc unbounded queue chỉ để tránh lỗi bị reject.

### 7.5. IdentityProbeService.java

~~~java
package com.example.asyncidentity;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class IdentityProbeService {

    @Async("securityAsyncExecutor")
    public CompletableFuture<String> propagated() {
        return CompletableFuture.completedFuture(currentName());
    }

    @Async("rawAsyncExecutor")
    public CompletableFuture<String> withoutPropagation() {
        return CompletableFuture.completedFuture(currentName());
    }

    private String currentName() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        return auth == null ? "none" : auth.getName();
    }
}
~~~

Hai methods chạy cùng logic, khác executor. Với request của Alice:
- `propagated()` kỳ vọng thấy `"alice"`;
- `withoutPropagation()` kỳ vọng `"none"` vì raw pool thread không có request ThreadLocal.

Khi có custom TaskDecorator hoặc một `SecurityContextHolderStrategy` thay đổi toàn JVM, kết quả có thể khác; demo giả định cấu hình chuẩn của Spring Security Servlet.

### 7.6. IdentityController.java

~~~java
package com.example.asyncidentity;

import java.util.concurrent.CompletableFuture;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    private final IdentityProbeService service;

    public IdentityController(IdentityProbeService service) {
        this.service = service;
    }

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/probe/direct")
    public String direct(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/probe/secure")
    public CompletableFuture<String> secure() {
        return service.propagated();
    }

    @GetMapping("/probe/raw")
    public CompletableFuture<String> raw() {
        return service.withoutPropagation();
    }
}
~~~

Controller inject `IdentityProbeService` là **Spring bean riêng**, đảm bảo invocation `@Async` đi qua proxy. Controller trả CompletableFuture để Spring MVC xử lý asynchronous response; không block request bằng `join()`.

### 7.7. Chạy và quan sát HTTP

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Mở terminal khác tại localhost:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/probe/secure
curl -i -u alice:alice123 http://localhost:8080/probe/direct
curl -i -u alice:alice123 http://localhost:8080/probe/secure
curl -i -u alice:alice123 http://localhost:8080/probe/raw
curl -i -u admin:admin123 http://localhost:8080/probe/secure
curl -i -u admin:admin123 http://localhost:8080/probe/raw
~~~

| Request | HTTP dự kiến | Body dự kiến | Ý nghĩa |
| --- | --- | --- | --- |
| `/public` anonymous | 200 | `public` | Public |
| `/probe/secure` anonymous | 401 | Tùy Basic entry point | Không cho submit nếu chưa xác thực |
| Alice `/probe/direct` | 200 | `alice` | Request thread có Alice |
| Alice `/probe/secure` | 200 | `alice` | Worker được propagate context |
| Alice `/probe/raw` | 200 | `none` | Raw worker không có Alice |
| Admin `/probe/secure` | 200 | `admin` | Capture theo mỗi lần submit |
| Admin `/probe/raw` | 200 | `none` | Không tự thừa kế Alice/admin |

Các status/body là **kỳ vọng theo code**, không phải log của một Gradle run đã thực hiện. Lệnh demo chứa password chỉ dùng localhost; production cần TLS và tránh ghi password vào shell history/traces.

## 8. Kiểm thử MockMvc: truyền đúng user và không rò sang user khác

Tạo `src/test/java/com/example/asyncidentity/SecurityContextAsyncTest.java`:

~~~java
package com.example.asyncidentity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityContextAsyncTest {

    @Autowired
    MockMvc mvc;

    private String callAsync(
            String path, String username, String password)
            throws Exception {

        MvcResult initial = mvc.perform(get(path)
                .with(httpBasic(username, password)))
            .andExpect(request().asyncStarted())
            .andReturn();

        MvcResult completed = mvc.perform(asyncDispatch(initial))
            .andExpect(status().isOk())
            .andReturn();

        return completed.getResponse().getContentAsString();
    }

    @Test
    void asyncWrapperPropagatesIdentityPerUser()
            throws Exception {
        assertEquals(
            "alice",
            callAsync("/probe/secure", "alice", "alice123")
        );
        assertEquals(
            "admin",
            callAsync("/probe/secure", "admin", "admin123")
        );
    }

    @Test
    void rawExecutorHasNoRequestIdentity()
            throws Exception {
        assertEquals(
            "none",
            callAsync("/probe/raw", "alice", "alice123")
        );
    }

    @Test
    void oneUsersContextDoesNotLeakToTheNextTask()
            throws Exception {
        assertEquals(
            "alice",
            callAsync("/probe/secure", "alice", "alice123")
        );
        assertEquals(
            "none",
            callAsync("/probe/raw", "admin", "admin123")
        );
        assertEquals(
            "admin",
            callAsync("/probe/secure", "admin", "admin123")
        );

        assertNull(
            SecurityContextHolder.getContext().getAuthentication()
        );
    }

    @Test
    void directControllerUsesRequestThreadAuthentication()
            throws Exception {
        mvc.perform(get("/probe/direct")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void anonymousCannotScheduleAProtectedProbe()
            throws Exception {
        mvc.perform(get("/probe/secure"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }
}
~~~

Chạy test:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

**Vì sao dùng `request().asyncStarted()` + `asyncDispatch`?** Controller trả `CompletableFuture`. Spring MVC có asynchronous request lifecycle; lần dispatch đầu có thể chưa trả response cuối. `asyncDispatch(initial)` mô phỏng bước hoàn tất trước khi assert status/body.

**Vì sao test Alice rồi admin?** Một test chỉ có Alice có thể bỏ sót fixed-context executor; chạy hai accounts giúp phát hiện lỗi wrapper capture user đầu tiên rồi dùng lại cho mọi task.

**Vì sao `.with(httpBasic(...))` mà không chỉ `@WithMockUser`?** Test Basic cho request đi qua Spring Security authentication filter/provider, trong khi mock user dựng một Authentication phục vụ test và không chứng minh password được xác thực. Đối với domain permission/owner/tenant cần thêm kiểm thử riêng.

**Bộ test ở đây chỉ được rà soát tĩnh.** Cần chạy Gradle trên project thật, với version/dependency tương ứng, mới khẳng định build/test đã thực thi.

## 9. Spring MVC Callable không giống @Async hoặc DeferredResult

Spring Security 6.x có integration riêng với Spring MVC asynchronous request processing.

### 9.1. Controller trả Callable

~~~java
@GetMapping("/mvc/callable")
public Callable<String> callable() {
    return () -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        return auth == null ? "none" : auth.getName();
    };
}
~~~

Khi ứng dụng dùng Spring Security filter chain đúng cách, `WebAsyncManagerIntegrationFilter` kết hợp Spring MVC để **truyền context đến thread xử lý Callable**. Spring Security docs mô tả context được gắn vào Callable dựa trên SecurityContext có ở thời điểm `startCallableProcessing`.

Đó là **một integration cụ thể**, không phải lời hứa rằng mọi `new Thread()`, `CompletableFuture`, `@Async`, scheduler hay thread pool library tự nhận Authentication.

### 9.2. DeferredResult do application tự hoàn tất

Một controller trả `DeferredResult` có thể được hoàn tất bởi code chạy sau trên một thread do ứng dụng quản lý. Không có cơ chế tự động tương đương với MVC Callable để mọi nơi set kết quả đều có context. Phải dùng wrapper/managed executor nếu thật sự cần identity trong completion callback, hoặc truyền trusted account ID thay cho context.

### 9.3. CompletableFuture stages

~~~java
@GetMapping("/mvc/future")
public CompletableFuture<String> future() {
    return CompletableFuture.supplyAsync(() -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        return auth == null ? "none" : auth.getName();
    });
}
~~~

Đây là **phản ví dụ**: overload không chỉ định executor thường dùng common pool, không đảm bảo SecurityContext của servlet request. Cần executor được bọc **ngay tại nơi submit**, và tiếp tục xem xét từng stage. Nếu task chỉ cần user ID, truyền user ID tin cậy có thể đơn giản và an toàn hơn.

### 9.4. AsyncContext.start và custom dispatch

Spring Security có integration với một số Servlet Async API, bao gồm `AsyncContext.start(Runnable)`. Behavior phụ thuộc servlet security filters và container configuration. Không tự suy luận tất cả callback không thuộc request-managed async flow được propagate. Test cụ thể cho mechanism đang dùng.

### 9.5. WebFlux là mô hình khác

Spring WebFlux reactive dùng Reactor Context và `ReactiveSecurityContextHolder`, không lấy Servlet ThreadLocal làm nguồn danh tính đúng cho mọi operator trên reactive stream. Không copy nguyên hướng dẫn của bài này vào `SecurityWebFilterChain`/Reactor pipeline.

## 10. @Scheduled, message queue và long-running background jobs

Trong `@Scheduled` hoặc một queue consumer, **không có HTTP request user** vào thời điểm task chạy. Context rỗng có thể là trạng thái hoàn toàn đúng.

### 10.1. Không biến session người tạo job thành quyền vĩnh viễn

Ví dụ:

~~~text
09:00: Alice có ROLE_ADMIN, gửi yêu cầu export.
       App capture SecurityContext(Alice, ROLE_ADMIN).

09:05: Admin khóa Alice, thu hồi ROLE_ADMIN.

10:00: Worker mới xử lý export.
       Context cũ vẫn có thể chứa ROLE_ADMIN.
~~~

Wrapper không tự cập nhật quyền khi database đổi. Một check `hasRole("ADMIN")` dựa vào captured Authentication có thể cho kết quả stale. Với tài nguyên nhạy cảm, cần reauthorization theo chính sách hiện hành, account enabled/locked, owner, tenant và action.

### 10.2. Job command thay vì serialized Authentication

Một job bền vững nên lưu thông tin tối thiểu:

~~~java
public record ExportJob(
    String jobId,
    String requestedByAccountId,
    String tenantId,
    String reportId
) {}
~~~

Dữ liệu này **không tự trở thành Authentication**. Workflow production:

1. Khi nhận request tạo job, framework xác thực user.
2. Service kiểm tra user có quyền tạo job theo owner/tenant/domain policy.
3. Lưu job ID và immutable account/tenant ID từ nguồn đã xác minh, không dùng userId do client tự khai.
4. Worker chạy bằng **service/workload identity** được cấp phép với scope tối thiểu.
5. Khi worker bắt đầu, kiểm tra lại trạng thái account, quyền hiện tại và resource (nếu policy yêu cầu).
6. Audit cả **requestedBy** và **executedBy**, object, thời điểm và kết quả.
7. Giải quyết idempotency, retry, cancellation, timeouts và revocation của delegated authority.

**Không serialize nguyên SecurityContext/Authentication vào Kafka, RabbitMQ hoặc database queue**. Object có thể chứa credentials/details, authorities cũ, session metadata và implementation classes gây lệ thuộc version.

### 10.3. Scheduler nên dùng service identity

Job chạy theo lịch cần authentication với các API khác có thể dùng OAuth2 `client_credentials`, workload identity, mTLS hoặc cơ chế service-to-service đáng tin cậy. Không gắn ROLE_ADMIN từ một HTTP request trước đây vào scheduler để “cho job đủ quyền”.

Nếu thực sự phải hành động thay mặt user trong tương lai, phải có hợp đồng delegated authorization rõ: scopes, thời hạn, consent/audit, quyền thu hồi, và revalidation theo yêu cầu.

## 11. Các lỗi nguy hiểm về bảo mật và concurrency

### 11.1. Context có mặt không đồng nghĩa hành động được phép

~~~java
Authentication a =
    SecurityContextHolder.getContext().getAuthentication();

boolean flag =
    a != null && a.isAuthenticated();
~~~

`flag` không đủ cho authorization: anonymous authentication có thể báo true, một role snapshot có thể stale và một resource có owner/tenant riêng. Dùng Spring Security authorization/method security và domain policy cụ thể; đối với job nhạy cảm, kiểm tra quyền cập nhật gần thời điểm thực thi.

### 11.2. Không tự tạo trusted token từ dữ liệu client

~~~java
// Phản ví dụ không an toàn:
Authentication forged =
    UsernamePasswordAuthenticationToken.authenticated(
        userIdFromRequest,
        "not-verified",
        AuthorityUtils.createAuthorityList("ROLE_ADMIN")
    );
~~~

Client không có quyền tự khai ADMIN rồi biến thành trusted authentication. Chỉ AuthenticationManager, IdP hoặc cơ chế hệ thống đã kiểm soát có thể tạo principal/authorities theo policy. Nếu truyền một forged Authentication sang worker, wrapper không sửa được lỗi privilege escalation.

### 11.3. Không copy shared mutable SecurityContext rồi mutate đồng thời

Một context bị chia sẻ qua nhiều threads có thể tạo race khi thay `setAuthentication`. Nếu cần đúng một identity immutable cho job, sử dụng object nghiệp vụ nhỏ hoặc lấy thông tin từ nguồn tin cậy tại execution. Không giả định constructor wrapper thực hiện deep copy.

### 11.4. Không nhầm transaction propagation

`@Transactional` trên HTTP request thường gắn transaction/session với thread hiện tại. `@Async` chạy trên thread khác và không tự mang transaction cũ sang. Worker cần transaction boundary riêng và không nên giữ transaction mở trong khi chờ queue.

SecurityContext propagation **không tương đương** database transaction propagation, request-scoped bean transfer hoặc MDC/tracing propagation. Mỗi context có cơ chế và vòng đời khác nhau.

### 11.5. MDC/tracing cũng không tự chứng minh Authentication

Các TaskDecorator/Micrometer integrations có thể chuyển trace IDs qua threads. Nhưng trace baggage hoặc header do client gửi **không phải bằng chứng đăng nhập**. Đừng suy ra một task đã có SecurityContext chỉ vì log xuất hiện cùng trace ID; test từng context và cleanup riêng.

### 11.6. Failure path, task cancellation và rate limits

Cần kiểm thử:
- Task ném exception và worker thread được cleanup.
- Executor queue đầy, task bị reject nhưng HTTP status/observability vẫn rõ.
- Future bị cancel hoặc timeout, task có tiếp tục side effects không.
- Account bị khóa sau submit nhưng trước execution.
- Hai users submit đồng thời không trộn identity.
- Shutdown có dọn pool và không giữ data nhạy cảm.
- Authorization vẫn chạy đúng trước tài nguyên thật, không chỉ kiểm tra `getName()`.

## 12. Những lỗi phổ biến

| Lỗi | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Dùng static Authentication | Trộn users giữa requests | SecurityContext theo execution |
| Đổi MODE_GLOBAL để chữa @Async | Chia sẻ identity toàn JVM | Giữ ThreadLocal, dùng wrappers |
| Dùng MODE_INHERITABLETHREADLOCAL với pool | Kế thừa sai thời điểm/stale context | Capture per task |
| `CompletableFuture.supplyAsync` không executor | Common pool không có request context | Truyền managed executor phù hợp |
| Quên `@Async("securityAsyncExecutor")` | Dùng default executor không propagate | Chỉ định đúng bean |
| Gọi `this.asyncMethod()` | Self-invocation bypass proxy | Gọi qua injected Spring bean |
| Fixed context lấy từ user đầu tiên | Bob có thể chạy như Alice | Capture tại mỗi submit |
| Không cleanup trong custom worker | Task sau nhìn thấy user trước | Dùng DelegatingSecurityContext* wrappers |
| Giữ `Authentication` trong queue dài hạn | Quyền stale, lộ credentials | Job command + fresh authorization |
| Dùng `@Scheduled` với user context cũ | Privilege vượt phạm vi | Service identity và delegation có hạn |
| Chỉ check `isAuthenticated` | Anonymous/role stale/tenant bypass | AuthorizationManager/domain policy |
| Coi MVC Callable giống DeferredResult | Thiếu context ở callback | Đọc rõ integration của từng API |
| Quên `asyncDispatch` trong MockMvc | Assert response trước completion | `request().asyncStarted()` + `asyncDispatch` |
| `@WithMockUser` được coi login E2E | Không xác minh password/token | Test qua filter/login thật |
| Chỉ test một user | Bỏ sót fixed context/leak | Test xen kẽ Alice/admin/anonymous |

## 13. Debug khi @Async không thấy người dùng

Hãy kiểm tra theo đúng ranh giới:

1. Trên request thread, Authentication có thực sự tồn tại và đã xác minh? Có bị anonymous không?
2. Request đi qua SecurityFilterChain nào? Có bị match sai URL/dispatcher?
3. Method `@Async` có chạy qua Spring proxy, hay self-invocation khiến nó chạy ngay caller thread?
4. `@Async` đang chọn bean executor nào? Có được bọc bằng `DelegatingSecurityContextAsyncTaskExecutor`?
5. Thời điểm submit có context Alice không? Hay request đã hoàn tất và holder bị clear?
6. Worker thread có cùng user hoặc đang null? Có fixed-context wrapper sai không?
7. Raw executor có TaskDecorator/custom strategy nào đang vô tình giữ identity?
8. Trong `CompletableFuture`, stage nào dùng executor nào, và được submit từ thread nào?
9. `DeferredResult` completion có được application tự lập trình đúng context policy không?
10. Spring MVC `Callable` có WebAsyncManagerIntegrationFilter/async support đúng không?
11. Job chạy sau một giờ có quyền mới nhất không? Có revalidate account, roles, owner/tenant không?
12. Khi task ném exception, context có được dọn trên pool thread không?
13. Queue capacity, timeout, cancellation và exception handlers có được quan sát không?
14. Có dùng MODE_GLOBAL hoặc InheritableThreadLocal làm rò identity không?

Ví dụ log cho development:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.aop.interceptor.AsyncExecutionInterceptor=DEBUG
~~~

Ghi correlation ID, job ID, endpoint, principal type hoặc account ID được phép ghi; **không log raw password, Authorization header, access tokens, session cookies, nguyên SecurityContext, authentication credentials hoặc JWT claims nhạy cảm**.

## 14. Bài tập tự kiểm tra

**Câu 1.** Controller thấy Alice trong SecurityContext, nhưng worker `@Async` trả null. `UserDetailsService` chắc chắn sai?

**Đáp:** Không. Rất có thể là ranh giới ThreadLocal và chưa propagate context sang executor thread.

**Câu 2.** `SecurityContextHolder.MODE_GLOBAL` có phù hợp để mọi async job thấy user không?

**Đáp:** Không. Nó chia sẻ context toàn JVM và nguy hiểm trong ứng dụng nhiều users.

**Câu 3.** Constructor `DelegatingSecurityContextExecutor(delegate)` lấy context khi nào?

**Đáp:** Ở mỗi lần caller submit task qua `execute()`.

**Câu 4.** Còn constructor `(delegate, fixedContext)`?

**Đáp:** Mọi task dùng context được cung cấp; cần tránh fixed user context vô tình bị áp cho request của người khác.

**Câu 5.** Vì sao wrapper phải dọn holder trong finally?

**Đáp:** Để không rò danh tính sang task tiếp theo trên pool thread, kể cả khi task lỗi.

**Câu 6.** `@Async` tự gọi từ `this` có chắc chạy async?

**Đáp:** Không. Có thể bỏ qua proxy. Nên gọi qua injected bean khác và test handoff.

**Câu 7.** `CompletableFuture.supplyAsync(...)` không chỉ định executor có tự mang current Authentication?

**Đáp:** Không bảo đảm; common pool thường không có request ThreadLocal.

**Câu 8.** Spring MVC Callable có hỗ trợ context propagation riêng không?

**Đáp:** Có qua Spring Security/WebAsyncManagerIntegrationFilter khi cấu hình đúng.

**Câu 9.** DeferredResult có được tự động propagate sang mọi callback thread giống Callable không?

**Đáp:** Không. Cần wrapper hoặc truyền thông tin đáng tin theo nghiệp vụ.

**Câu 10.** Worker chạy scheduled job có nên dùng session của Alice từ tuần trước?

**Đáp:** Không. Nên dùng service identity hoặc delegated authorization có giới hạn và revalidation.

**Câu 11.** ROLE_ADMIN đã bị thu hồi sau khi job được queue. Context captured có tự cập nhật không?

**Đáp:** Không. Cần kiểm tra quyền hiện hành khi tác vụ được thực hiện nếu policy yêu cầu.

**Câu 12.** Có nên đưa nguyên Authentication object vào queue?

**Đáp:** Không. Dùng job command với account ID/tenant ID và metadata tối thiểu, không credentials.

**Câu 13.** Propagation có tự mang transaction từ `@Transactional` sang `@Async` không?

**Đáp:** Không. Transaction context có thread boundary riêng.

**Câu 14.** Nếu task Bob nhìn thấy Alice, nên kiểm tra gì?

**Đáp:** Fixed context executor, cleanup lỗi, shared static auth, MODE_GLOBAL/INHERITABLETHREADLOCAL.

**Câu 15.** Có Authentication trong worker nghĩa được bỏ kiểm tra owner/tenant không?

**Đáp:** Không. Authentication không thay authorization; quyền có thể stale.

**Câu 16.** Trong WebFlux có dùng nguyên Servlet ThreadLocal guidance này không?

**Đáp:** Không. WebFlux dùng Reactor Context/ReactiveSecurityContextHolder và cơ chế propagation riêng.

## 15. Tài liệu chính thức

- Spring Security 6.5 — **Concurrency Support**: https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html
- Spring Security — **Servlet Concurrency**: https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html
- Spring Security — **Spring MVC Integration**: https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/mvc.html
- Spring Security — **Authentication Architecture & SecurityContextHolder**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — **Method Security**: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — **DelegatingSecurityContextExecutor API**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/concurrent/DelegatingSecurityContextExecutor.html
- Spring Security — **DelegatingSecurityContextAsyncTaskExecutor API**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/task/DelegatingSecurityContextAsyncTaskExecutor.html
- Spring Framework — **Task Execution, Scheduling và @Async**: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — **Async Requests trong Spring MVC**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html

**Ghi nhớ:** Trong Spring Security Servlet, `SecurityContextHolder` mặc định dùng **ThreadLocal**. Khi chuyển task sang thread khác, chỉ truyền `SecurityContext` nếu có lý do và quyền phù hợp, bằng `DelegatingSecurityContext*` wrapper: **capture đúng lúc submit, thiết lập tạm trong worker và cleanup sau khi chạy**. Với `@Async`, bọc executor và gọi qua Spring proxy. Với scheduler, queue và long-running jobs, ưu tiên **service identity, command dữ liệu tối thiểu và kiểm tra quyền hiện hành**, không giữ mãi Authentication của HTTP request cũ.
