# Kiểm thử không rò rỉ danh tính khi luồng được tái sử dụng

**Phạm vi:** Spring Security **Servlet/Spring MVC**, Java 17+, Spring Boot 3.x và Spring Security 6.x. Bài học tập trung vào một lỗi tinh vi ở xử lý bất đồng bộ: **thread pool tái sử dụng worker của tác vụ trước nhưng `SecurityContext` chứa danh tính người dùng trước chưa được dọn**, dẫn đến truy cập tài nguyên/audit theo sai người. Ta sẽ thiết kế test có khả năng tái hiện chắc chắn, minh họa lỗi và bản sửa, sau đó kiểm tra `ExecutorService`, `@Async`, `Callable` và tác vụ bị exception.

## 1. Vì sao tái sử dụng thread gây rò rỉ danh tính?

Trong Spring Security Servlet, `SecurityContextHolder` cho phép lấy `SecurityContext` và `Authentication` của thread hiện tại:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
String name = authentication == null
    ? null : authentication.getName();
```

Chiến lược mặc định của Spring Security Servlet là **`MODE_THREADLOCAL`**. Context nằm trong ThreadLocal, **không tự biến thành dữ liệu gắn riêng cho mỗi job**, không tự được truyền đến mọi async thread và không tự biến mất chỉ vì business method đã trả kết quả.

Trong vòng đời Servlet request bình thường, **Spring Security filter chain** quản lý thời điểm thiết lập/lưu và dọn security context. Nhưng khi ứng dụng tự dùng `ExecutorService`, `CompletableFuture`, `@Async` hoặc custom callback, code phải hiểu rõ ai **truyền** và ai **dọn** `SecurityContext` trên worker thread.

```text
Request của Alice                  ExecutorService (pool 1 thread)
       │                                     │
       ├── submit task A ──────────────────> │ worker-1
       │                                     │ setContext(alice)
       │                                     │ thực thi A
       │                                     │ QUÊN clearContext()
       │                                     │
Request của Bob                     ────────> │ worker-1 tái sử dụng
       ├── submit task B ──────────────────> │ getContext() vẫn = alice
       │                                     │ có thể ghi/audit/truy cập
       │                                     │ dữ liệu dưới quyền Alice
```

Đây là **identity leakage giữa các yêu cầu/tác vụ**. Nó có thể dẫn đến đọc thông tin người khác, quyết định authorization sai, ghi audit nhầm hoặc dùng sai tenant. Chỉ kiểm tra “task bất đồng bộ có nhìn thấy username không?” **không đủ**.

Cần phân biệt hai tình huống:

- **Không được truyền context:** task chạy trên thread mới thấy authentication `null`, nên chức năng yêu cầu principal bị lỗi. Đây là vấn đề **context propagation**.
- **Bị tồn dư context:** task không được cấp danh tính nhưng đọc được authentication của user chạy trước, ví dụ Alice. Đây là **rò rỉ danh tính**.

Nguy cơ lớn nhất nằm ở việc task mới chạy trên **đúng thread** từng xử lý một principal khác, nên một test dùng pool nhiều thread chạy ngẫu nhiên có thể bỏ sót.

## 2. Những bất biến bảo mật phải test

| Bất biến | Trường hợp thử | Kết quả đúng |
| --- | --- | --- |
| Đúng danh tính | Task Alice, sau đó task Bob | Alice chỉ thấy Alice, Bob chỉ thấy Bob. |
| Không kế thừa vô cớ | Task kế tiếp không có context | Không thấy Authentication của Alice/Bob. |
| Dọn khi hoàn thành | Task có context trả về bình thường | Raw worker sau đó không còn principal. |
| Dọn khi thất bại | Task có context ném exception | Raw worker sau đó vẫn không còn principal. |
| Tái sử dụng có chủ đích | Hai task trên cùng một worker | Test không phụ thuộc scheduler chọn thread ngẫu nhiên. |
| Không chia sẻ mutable context | Có nhiều job đồng thời, caller đổi Authentication | Job A không bất ngờ thành Bob. |
| Không rò các holder khác | MDC/tenant/locale/request context | Mỗi holder có quy tắc cleanup riêng. |

**Đo ở đâu?** Nếu kiểm tra trực tiếp một **raw executor worker** sau `clearContext()`, `SecurityContextHolder.getContext().getAuthentication()` thông thường là `null`. Nếu kiểm tra ở **Servlet request** đã đi qua `AnonymousAuthenticationFilter`, có thể xuất hiện `AnonymousAuthenticationToken` chứ không phải `null`; đây **không phải** user đã đăng nhập. Phải xác định trạng thái kỳ vọng theo ngữ cảnh, không dùng `isAuthenticated()` đơn lẻ để phân biệt anonymous với user thật.

## 3. Java 17 độc lập: tái hiện lỗi ThreadLocal

Trước hết quan sát cơ chế ở Java SE, chưa cần Spring:

**`ThreadLocalReuseDemo.java`**

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ThreadLocalReuseDemo {

    private static final ThreadLocal<String> CURRENT_USER =
        new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            String first = pool.submit(() -> {
                CURRENT_USER.set("alice");
                // Sai có chủ ý: không CURRENT_USER.remove().
                return CURRENT_USER.get();
            }).get();

            String leaked = pool.submit(() -> {
                return CURRENT_USER.get();
            }).get();

            // Phải remove trên WORKER, không phải caller thread.
            pool.submit(CURRENT_USER::remove).get();

            String after = pool.submit(() -> {
                return String.valueOf(CURRENT_USER.get());
            }).get();

            System.out.println("first=" + first);
            System.out.println("withoutCleanup=" + leaked);
            System.out.println("afterCleanup=" + after);
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch/chạy với JDK 17:

```bash
javac ThreadLocalReuseDemo.java
java ThreadLocalReuseDemo
```

**Stdout chính xác:**

```text
first=alice
withoutCleanup=alice
afterCleanup=null
```

Giải thích: `newSingleThreadExecutor()` thực thi các task tuần tự trên một worker; mỗi `Future.get()` đợi task trước kết thúc. Task B không nhận username nhưng vẫn đọc được Alice do ThreadLocal tồn dư. `CURRENT_USER.remove()` dọn đúng worker. **Đây chỉ là demo Java SE về ThreadLocal**, không phải một chương trình Spring Security hay cách triển khai an toàn.

## 4. Bộ test JUnit 5 cho SecurityContextHolder

Khi dùng Spring Security Core, test có thể đặt trong project Spring Boot đã có **Spring Security** và **Spring Boot Starter Test** (JUnit Jupiter). Ba test quan trọng: (1) tái hiện lỗi có kiểm soát, (2) xác minh cleanup `finally` khi thành công/thất bại, (3) kiểm tra wrapper truyền danh tính theo từng lần submit và không để lại residue.

**`src/test/java/com/example/threadsecurity/SecurityContextReuseTest.java`**

```java
package com.example.threadsecurity;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutorService;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.*;

class SecurityContextReuseTest {

    @AfterEach
    void cleanupCallerThread() {
        SecurityContextHolder.clearContext();
    }

    private static SecurityContext contextFor(String username) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();

        context.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                username, "not-used",
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
            )
        );
        return context;
    }

    private static String nameOnCurrentThread() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        return auth == null ? null : auth.getName();
    }

    @Test
    void reproducesLeakIfSomeoneForgetsCleanup() throws Exception {
        ExecutorService raw = Executors.newSingleThreadExecutor();
        try {
            long before = raw.submit(
                () -> Thread.currentThread().getId()
            ).get();

            raw.submit((Runnable) () ->
                SecurityContextHolder.setContext(contextFor("alice"))
            ).get();

            String leaked = raw.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get();

            long after = raw.submit(
                () -> Thread.currentThread().getId()
            ).get();

            assertEquals(before, after);
            // Test giáo dục: PASS khi chứng minh được lỗi cố tình tạo.
            assertEquals("alice", leaked);
        } finally {
            // Dọn ngay trên worker, dù một assertion đã thất bại.
            try {
                raw.submit(SecurityContextHolder::clearContext).get();
            } finally {
                raw.shutdownNow();
            }
        }
    }

    @Test
    void cleanupWorksEvenWhenTheDelegateThrows() throws Exception {
        ExecutorService raw = Executors.newSingleThreadExecutor();

        try {
            Future<String> first = raw.submit(() -> {
                SecurityContextHolder.setContext(contextFor("alice"));
                try {
                    return nameOnCurrentThread();
                } finally {
                    SecurityContextHolder.clearContext();
                }
            });

            assertEquals("alice", first.get());
            assertNull(raw.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());

            Future<?> failed = raw.submit((Runnable) () -> {
                SecurityContextHolder.setContext(contextFor("bob"));
                try {
                    throw new IllegalStateException("boom");
                } finally {
                    SecurityContextHolder.clearContext();
                }
            });

            ExecutionException exception = assertThrows(
                ExecutionException.class, failed::get
            );
            assertInstanceOf(
                IllegalStateException.class, exception.getCause()
            );

            assertNull(raw.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());
        } finally {
            raw.shutdownNow();
        }
    }

    @Test
    void delegatingExecutorScopesAliceBobAndAnonymous()
            throws Exception {

        ExecutorService raw = Executors.newSingleThreadExecutor();
        ExecutorService guarded =
            new DelegatingSecurityContextExecutorService(raw);

        try {
            SecurityContextHolder.setContext(contextFor("alice"));
            assertEquals("alice", guarded.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());

            // Probe trực tiếp raw worker, không qua wrapper.
            assertNull(raw.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());

            SecurityContextHolder.setContext(contextFor("bob"));
            assertEquals("bob", guarded.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());

            assertNull(raw.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());

            SecurityContextHolder.clearContext();
            assertNull(guarded.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());

            assertNull(raw.submit(
                (Callable<String>) SecurityContextReuseTest::nameOnCurrentThread
            ).get());
        } finally {
            SecurityContextHolder.clearContext();
            raw.shutdownNow();
        }
    }
}
```

**Đọc đúng kết quả kiểm thử:**

- `reproducesLeakIfSomeoneForgetsCleanup` **cố tình** mô phỏng lỗi và **PASS** khi phát hiện Alice tồn dư. Nó là ví dụ nguyên nhân, **không** chứng minh app production an toàn.
- `cleanupWorksEvenWhenTheDelegateThrows` bảo vệ bất biến không còn principal sau task hoàn thành và task bị exception.
- `delegatingExecutorScopesAliceBobAndAnonymous` xác minh propagation Alice/Bob/no-user đồng thời **probe raw executor sau mỗi task** để tìm residual identity.
- `SecurityContextHolder.clearContext()` ở `@AfterEach` chỉ dọn **JUnit caller thread**. Nó không xóa ThreadLocal trên worker thread; test phải có `finally`/wrapper ở worker.
- Mỗi `contextFor(...)` tạo context riêng. Tránh một `SecurityContext` mutable được share rồi đổi Authentication sau submit.

**Điểm cần cảnh giác với test đỏ–xanh:** regression test thực tế của ứng dụng phải assert **không còn authentication** sau task. Nếu đặt `assertNull(raw.submit(...).get())` ngay sau tác vụ cố tình để sót Alice ở test đầu, test sẽ **FAIL**. Sau khi sửa task bằng `try/finally` hoặc wrapper, assert đó phải **PASS**. Không dùng “test tái hiện leak chạy xanh” làm bằng chứng đã vá lỗi.

## 5. Cách ngăn rò rỉ ở lớp thực thi task

### 5.1 Dùng try/finally khi chủ động đặt SecurityContext

Nếu một worker hoàn toàn do ứng dụng sở hữu, có thể scope context theo kiểu:

```java
SecurityContext scoped = SecurityContextHolder.createEmptyContext();
scoped.setAuthentication(authenticationForThisTask);

try {
    SecurityContextHolder.setContext(scoped);
    performWork();
} finally {
    SecurityContextHolder.clearContext();
}
```

Đây là **snippet bên trong task**, chưa phải class độc lập. Không đặt `clearContext()` sau `performWork()` mà bỏ `finally` vì exception sẽ đi qua đoạn cleanup. Nếu một adapter framework đang có context hợp lệ cần giữ, hãy dùng cơ chế scoped wrapper thích hợp **khôi phục trạng thái trước đó**, không tùy tiện xóa context người khác.

### 5.2 Dùng wrapper của Spring Security khi cần truyền context

Các wrapper quan trọng:

- `DelegatingSecurityContextRunnable` / `DelegatingSecurityContextCallable`: chạy một task trong phạm vi context chọn trước, xử lý cleanup/restore phù hợp.
- `DelegatingSecurityContextExecutor` / `DelegatingSecurityContextExecutorService`: bọc task khi submit lên executor; constructor một tham số có thể sử dụng context caller tại thời điểm submit.
- `DelegatingSecurityContextAsyncTaskExecutor`: bọc `AsyncTaskExecutor` cho `@Async` trong Spring.

**Cẩn thận với fixed context:** một số constructor nhận một `SecurityContext` cố định. Nếu khởi tạo lúc startup với context của Alice, mọi task có thể chạy như Alice, dù submitted bởi Bob. Với web app nhiều người dùng, thông thường cần chụp context **theo từng submission**, không dùng một identity fixed ngẫu nhiên.

**Không phải task nào cũng nên kế thừa user.** Job định kỳ, queue consumer và service background có thể không có principal của browser; khi đó phải chọn service identity/authorization rõ ràng thay vì mượn “user cuối cùng”.

### 5.3 MODE_INHERITABLETHREADLOCAL và MODE_GLOBAL không phải bản sửa

`MODE_INHERITABLETHREADLOCAL` sao chép giá trị **khi tạo thread con**, không phải khi task mới được submit. Worker của pool tạo dưới request Alice vẫn có thể mang Alice khi xử lý task của Bob. Dùng inheritable mode để “làm @Async thấy user” có thể làm rủi ro tệ hơn.

`MODE_GLOBAL` dùng context phạm vi ứng dụng thay vì theo thread và không thích hợp cho nhiều user request song song. Giữ chiến lược `MODE_THREADLOCAL` mặc định trong Servlet và dùng các wrapper có vòng đời xác định khi thật sự cần.

### 5.4 SecurityContext có thể mutable

`SecurityContext` là object mutable. Nếu caller gọi `SecurityContextHolder.getContext().setAuthentication(bobAuth)` trên object mà task A đang tham chiếu, task A có thể bất ngờ thấy Bob. Hãy hiểu thời điểm capture, tạo context tách biệt khi cần, tránh lưu `Authentication`/`SecurityContext` trong static field dùng chung, tránh sửa object context đã truyền cho nhiều task đồng thời.

## 6. Ví dụ @Async sử dụng pooled executor an toàn

Ví dụ Spring Boot Servlet dùng một `ThreadPoolTaskExecutor` **một worker** để dễ quan sát reuse và một `DelegatingSecurityContextAsyncTaskExecutor` để truyền SecurityContext đúng phạm vi.

**`src/main/java/com/example/asyncsecurity/AsyncConfig.java`**

```java
package com.example.asyncsecurity;

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

    @Bean("rawWorkerExecutor")
    ThreadPoolTaskExecutor rawWorkerExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(16);
        pool.setThreadNamePrefix("identity-worker-");
        pool.initialize();
        return pool;
    }

    @Bean("securityExecutor")
    AsyncTaskExecutor securityExecutor(
            @Qualifier("rawWorkerExecutor") ThreadPoolTaskExecutor raw) {
        return new DelegatingSecurityContextAsyncTaskExecutor(raw);
    }
}
```

**`src/main/java/com/example/asyncsecurity/IdentityJobService.java`**

```java
package com.example.asyncsecurity;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class IdentityJobService {

    @Async("securityExecutor")
    public CompletableFuture<String> currentUserName() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        String name = auth == null ? null : auth.getName();
        return CompletableFuture.completedFuture(name);
    }
}
```

**`src/main/java/com/example/asyncsecurity/AsyncSecurityApplication.java`**

```java
package com.example.asyncsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncSecurityApplication.class, args);
    }
}
```

Để chạy dạng Spring Boot project, cần Spring Boot 3.x, Spring Web, Spring Security và Java 17+, chạy bằng `./gradlew bootRun` trên project Gradle wrapper (Windows `.\gradlew.bat bootRun`). Những class sử dụng Spring trên classpath, **không biên dịch bằng javac thuần**.

`@Async` thường hoạt động qua Spring proxy. Gọi method `this.currentUserName()` từ cùng class có thể **bypass proxy** và không chạy bất đồng bộ. Gọi qua bean do Spring quản lý để đảm bảo executor `securityExecutor` được sử dụng.

### 6.1 Integration test Alice → Bob → không có principal

**`src/test/java/com/example/asyncsecurity/AsyncIdentityIsolationTest.java`**

```java
package com.example.asyncsecurity;

import java.util.List;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class AsyncIdentityIsolationTest {

    @Autowired IdentityJobService service;

    @Autowired
    @Qualifier("rawWorkerExecutor")
    ThreadPoolTaskExecutor raw;

    private void loginAs(String name) {
        SecurityContext ctx = SecurityContextHolder.createEmptyContext();
        ctx.setAuthentication(new UsernamePasswordAuthenticationToken(
            name, "not-used",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        ));
        SecurityContextHolder.setContext(ctx);
    }

    private String readRawWorker() throws Exception {
        return raw.submit(() -> {
            Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
            return auth == null ? null : auth.getName();
        }).get(5, TimeUnit.SECONDS);
    }

    @AfterEach
    void cleanupCaller() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void propagatesEachPrincipalAndLeavesWorkerClean() throws Exception {
        loginAs("alice");
        assertEquals("alice",
            service.currentUserName().get(5, TimeUnit.SECONDS));
        assertNull(readRawWorker());

        loginAs("bob");
        assertEquals("bob",
            service.currentUserName().get(5, TimeUnit.SECONDS));
        assertNull(readRawWorker());

        SecurityContextHolder.clearContext();
        assertNull(service.currentUserName().get(5, TimeUnit.SECONDS));
        assertNull(readRawWorker());
    }
}
```

Với một `ThreadPoolTaskExecutor` có `corePoolSize=maxPoolSize=1`, test tái sử dụng cùng worker một cách có chủ đích. `readRawWorker()` bỏ qua wrapper và kiểm tra raw state sau khi task hoàn thành. Nếu test fail, kiểm tra tên bean executor, Spring proxy `@Async`, cách chụp context tại submission, context mutable và code tự `setContext` khác không có cleanup.

## 7. Bất đồng bộ trong Spring MVC: Callable và DeferredResult

Không phải mọi kiểu async có semantics như nhau.

**Controller trả `Callable<T>`:** Spring Security có tích hợp với Servlet async processing (trong đó có `WebAsyncManagerIntegrationFilter`) để truyền security context vào quá trình thực thi `Callable` và xử lý vòng đời theo filter chain. Vẫn cần integration test để xác minh business endpoint và principal.

**`DeferredResult<T>` hoặc custom callback:** mã hoàn tất kết quả có thể chạy trên một thread do ứng dụng tự quản lý. **Không mặc định** có security context của request trên mọi callback/producer. Nếu cần danh tính, chọn wrapper/context scope đúng hoặc truyền **account ID/authorization intent** dưới dạng dữ liệu đã kiểm chứng, không dựa vào ThreadLocal ngẫu nhiên.

**`CompletableFuture.supplyAsync(...)`:** nếu dùng common pool hoặc executor khác, context caller **không tự được đảm bảo**. Cần xác định rõ executor được dùng và bổ sung test cho executor đó, thay vì lấy thành công của `Callable` để suy ra CompletableFuture an toàn.

### 7.1 Controller Callable

**`src/main/java/com/example/asyncsecurity/AsyncController.java`**

```java
package com.example.asyncsecurity;

import java.util.concurrent.Callable;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AsyncController {

    @GetMapping("/api/whoami-async")
    public Callable<String> whoami() {
        return () -> {
            Authentication a =
                SecurityContextHolder.getContext().getAuthentication();
            return a == null ? "no-user" : a.getName();
        };
    }
}
```

**`src/main/java/com/example/asyncsecurity/WebSecurityConfig.java`**

```java
package com.example.asyncsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

### 7.2 Kiểm thử MockMvc với hai người dùng

Dependency test (Gradle):

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

**`src/test/java/com/example/asyncsecurity/CallableIsolationTest.java`**

```java
package com.example.asyncsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class CallableIsolationTest {

    @Autowired MockMvc mvc;

    @Test
    void twoRequestsSeeTheirOwnPrincipals() throws Exception {
        MvcResult alice = mvc.perform(
            get("/api/whoami-async").with(user("alice"))
        ).andExpect(request().asyncStarted()).andReturn();

        mvc.perform(asyncDispatch(alice))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

        MvcResult bob = mvc.perform(
            get("/api/whoami-async").with(user("bob"))
        ).andExpect(request().asyncStarted()).andReturn();

        mvc.perform(asyncDispatch(bob))
            .andExpect(status().isOk())
            .andExpect(content().string("bob"));
    }
}
```

Test này xác minh identity qua **Servlet Callable**, nhưng **không chứng minh** hai request chạy trên cùng physical thread. Phép thử `newSingleThreadExecutor()` ở trên mới ép worker reuse và tìm residual identity một cách chắc chắn. Đối với `DeferredResult`, `CompletableFuture`, scheduler và queue consumer, phải test **đúng executor thực tế**.

## 8. Các lỗi kiểm thử phổ biến

| Triệu chứng | Vì sao xảy ra | Hướng sửa/test |
| --- | --- | --- |
| Test no-leak xanh ngẫu nhiên | Scheduler cấp hai worker khác nhau. | Dùng single-thread pool và `Future.get()`. |
| Task B thấy Alice | Thiếu cleanup, wrapper không được sử dụng hoặc inheritable context. | Probe raw worker sau Alice, Bob, anonymous. |
| Task thất bại khiến user tồn dư | `clearContext()` nằm ngoài `finally`. | Inject exception và assert worker trống sau failure. |
| `@Async` chạy đồng bộ | Self-invocation/bypass proxy hoặc chưa `@EnableAsync`. | Gọi qua Spring bean và chỉ định đúng executor. |
| `@Async` thấy authentication null | Không truyền context từ caller. | Dùng `DelegatingSecurityContextAsyncTaskExecutor` nếu thật sự cần user. |
| Worker task luôn thấy cùng một user | Fixed SecurityContext bị bọc cho mọi submission. | Dùng constructor/wrapper capture context theo từng submit. |
| Context đổi khi job đang chạy | Share một SecurityContext mutable rồi đổi Authentication. | Tạo context riêng, không mutate sau khi submit. |
| MDC log vẫn ghi Alice | MDC là ThreadLocal khác. | Dọn MDC riêng trong TaskDecorator/`finally`. |
| Servlet Callable đúng nhưng DeferredResult sai | Cơ chế propagation không giống nhau. | Test executor/callback của DeferredResult. |
| Bật MODE_INHERITABLETHREADLOCAL mà leak nặng hơn | Worker được tạo dưới Alice và tái sử dụng. | Giữ MODE_THREADLOCAL, dùng propagation wrapper. |
| Đã dọn ở request thread nhưng worker vẫn dính | ThreadLocal gắn từng thread. | Dọn trên chính worker trong task. |
| Audit ghi Alice trong job Bob dù SecurityContext sạch | Custom tenant holder/actor ThreadLocal/cache riêng còn cũ. | Kiểm thử mọi context carrier, không chỉ Spring Security. |

`MDC`, `RequestContextHolder`, `LocaleContextHolder` và custom `ThreadLocal` phải được dọn/quản lý độc lập. `DelegatingSecurityContextExecutorService` chỉ giải quyết **Spring Security context**, không tự dọn MDC/tenant context. Nếu có tracing, task decorators hoặc request attributes, kiểm tra thứ tự đặt và khôi phục các context; không chuyển nhầm identity vào logger/cross-tenant cache.

## 9. Bộ regression cases nên có trong CI

| Ca thử | Task A | Task B trên cùng worker | Assert mong muốn |
| --- | --- | --- | --- |
| Demo lỗi có chủ đích | Set Alice, quên clear. | Task không identity. | Phát hiện Alice còn tồn dư để chứng minh nguyên nhân. |
| Cleanup thường | Scope Alice với `finally`. | Task không identity. | `Authentication == null`. |
| Cleanup lỗi | Scope Alice, ném `RuntimeException`. | Task không identity. | `Authentication == null`. |
| Đổi principal | Wrapper Alice. | Wrapper Bob. | Alice đúng, Bob đúng; raw worker trống sau mỗi task. |
| Anonymous sau nhiều user | Alice → Bob. | Task không principal. | Không thấy Alice/Bob. |
| Đúng context thời điểm submit | Submit A rồi caller đổi sang B. | Job A thực thi sau đó. | Không bất ngờ thành B do shared mutable object. |
| Servlet Callable | HTTP Alice. | HTTP Bob. | Endpoint trả đúng từng principal. |
| DeferredResult/custom callback | Task Alice. | Task Bob/no-user. | Không leak; kiểm tra executor thật. |
| Cancellation/timeout | Task bị ngắt hoặc fail. | Task sau. | Context không tồn dư. |
| Tenant/MDC | Actor Alice + tenant A. | Actor Bob + tenant B. | Không rò actor/tenant/logging context. |

**Cách thực hành đỏ → xanh:** tạo test khẳng định raw pool không còn Authentication sau task. Nếu implementation cố tình bỏ `finally`, test **phải fail**. Sửa bằng cleanup hoặc Spring wrapper, chạy lại để test pass. Test mô phỏng leak vốn `assertEquals("alice", leaked)` pass **không** phải security acceptance test.

**Chống test flaky:** xác định rõ executor một thread, chờ từng `Future`, bảo đảm không dùng chung context mutable, tách pool cho từng test, có timeout trong integration test và cleanup ở cả caller/worker. Test thêm exception/cancel/rejected-task phù hợp với executor thật. Không dùng kết quả stress test ít lần để suy ra rủi ro đã biến mất.

## 10. Checklist điều tra và triển khai

1. Xác định executor nào chạy task: Servlet Callable, `@Async`, `CompletableFuture`, scheduler, queue consumer hoặc pool của thư viện khác.
2. Kiểm tra chiến lược `SecurityContextHolder`: mặc định `MODE_THREADLOCAL` hay đã bị đổi thành `MODE_INHERITABLETHREADLOCAL`/`MODE_GLOBAL`.
3. Tìm mọi `SecurityContextHolder.setContext`, `getContext().setAuthentication`, custom principal/tenant ThreadLocal và vị trí cleanup.
4. Tách nhu cầu: job có cần impersonate user ở thời điểm submit không, hay nên dùng service identity và dữ liệu actor đã xác minh?
5. Nếu cần propagation, dùng đúng `DelegatingSecurityContext*` wrapper và xác nhận context **theo submission**, không fixed identity ngoài ý muốn.
6. Tạo test một worker: Alice, anonymous, Bob, anonymous, exception, anonymous. Assert raw worker không có user cũ.
7. Kiểm thử Servlet async riêng: `Callable` có tích hợp security context, nhưng `DeferredResult`/custom executor cần cấu hình rõ.
8. Không đặt `SecurityContext` mutable trong static/global, đừng bật inheritable/global để “sửa nhanh”.
9. Bao phủ MDC/tenant/locale/request-scoped state và logging/audit. Context sạch ở một holder chưa chứng minh mọi context khác sạch.
10. Nếu có bằng chứng rò rỉ thật, rà soát quyền truy cập dữ liệu, audit logs, hệ thống background jobs và thực hiện đánh giá sự cố bảo mật trước khi đóng issue.

## 11. Ghi nhớ

**Thread-local identity không gắn vĩnh viễn với một request: nó gắn với thread, mà thread pool có thể tái sử dụng.** Một task của Bob không được phép nhìn thấy `Authentication` của Alice chỉ vì dùng lại worker cũ. Để kiểm thử chắc chắn, **ép dùng cùng một worker**, chạy chuỗi nhiều principal và task không danh tính, thử đường exception, rồi đọc **raw worker state** sau từng task. Khi cần truyền context, dùng wrapper Spring Security có lifecycle đúng; khi tự đặt context, bảo đảm `try/finally`. Và luôn kiểm tra các carrier khác như MDC/tenant, vì cleanup `SecurityContextHolder` không tự dọn chúng.
