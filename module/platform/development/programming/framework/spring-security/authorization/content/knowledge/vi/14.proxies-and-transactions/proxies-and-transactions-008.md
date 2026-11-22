# @Async, executor và truyền SecurityContext đúng phạm vi

> **Chủ đề:** Spring Security – authorization · **Nhóm:** Proxy và giao dịch. Bài này giải thích cách Spring `@Async` thay đổi luồng thực thi, vì sao `SecurityContext` mặc định không đi theo executor thread, và cách đưa danh tính/quyền sang task **đúng người, đúng thời điểm, đúng phạm vi** mà không làm rò rỉ giữa các task. Phạm vi chính: Spring Boot Servlet, Spring Security method security, Java 17+.

## 1. Bạn cần nắm được gì?

Sau bài này, bạn có thể:

1. Giải thích quan hệ giữa `SecurityContextHolder`, `ThreadLocal`, `@Async`, Spring proxy và thread pool.
2. Chọn `DelegatingSecurityContextAsyncTaskExecutor`, `DelegatingSecurityContextExecutor`, `Runnable`/`Callable` wrapper hoặc một danh tính hệ thống riêng theo đúng loại tác vụ.
3. Dùng `@Async("...")` để chỉ rõ executor đã bọc `SecurityContext` thay vì phụ thuộc vào executor mặc định.
4. Phân biệt **truyền security context** với **kiểm tra quyền**, **truyền transaction**, **truyền HTTP request** và **truyền trace/MDC**.
5. Viết test chứng minh principal được nhìn thấy trong worker, method security vẫn chặn người thiếu quyền, và thread được dọn sau cả thành công lẫn ngoại lệ.
6. Nhận diện nguy cơ nhầm người dùng khi thread tái sử dụng, task chạy muộn, token bị thu hồi và lời gọi nội bộ bỏ qua proxy.

## 2. Vì sao có lỗi khi đưa logic sang @Async?

Trong ứng dụng Spring Security Servlet điển hình, `SecurityContextHolder` lưu `SecurityContext` cho **luồng hiện tại**, mặc định qua chiến lược `MODE_THREADLOCAL`. `SecurityContext` chứa `Authentication` (principal, authorities, thông tin xác thực). Khi request HTTP được bảo vệ, filter chain thiết lập ngữ cảnh thích hợp trên request thread và dọn khi hoàn tất.

Giả sử controller gọi method service đã bảo vệ bởi `@PreAuthorize("hasAuthority('report:read')")`. Trên thread xử lý HTTP, `SecurityContextHolder.getContext().getAuthentication()` có thể là Alice, mang authority `report:read`. Nếu chuyển việc sang `@Async`, phương thức có thể chạy trên một executor thread **khác**; `ThreadLocal` của thread cha không tự xuất hiện trong worker. Hậu quả hay gặp:

- `SecurityContextHolder.getContext().getAuthentication() == null` ở worker; code gọi `getName()` có thể ném `NullPointerException`.
- `@PreAuthorize`/`@PostAuthorize` chạy trong worker thiếu `Authentication`, nên phương thức bảo vệ có thể bị từ chối, dù caller HTTP đã xác thực.
- Nếu ứng dụng tự thiết lập context rồi **quên dọn**, pool tái sử dụng thread có thể mang principal của Alice vào task của Bob: lỗi cách ly nghiêm trọng.
- Tự sửa bằng cách chuyển `username` dưới dạng tham số không bảo đảm đúng quyền: một chuỗi ID không phải `Authentication` đã xác minh; bảo mật cần kiểm chứng policy ở điểm dùng.

### Sơ đồ một yêu cầu

~~~text
HTTP request của Alice
  |
  v
request thread "http-..."
SecurityContextHolder -> Authentication(alice, report:read)
  |
  | gọi proxy @Async, submit task
  v
worker thread "report-..."
SecurityContextHolder -> [trống theo mặc định]
  |
  +--> gọi @PreAuthorize -> thiếu authentication -> DENY

Nếu dùng executor bọc SecurityContext:
request thread: Authentication(alice)
  | submit => capture context ở điểm giao việc
  v
worker thread: set context Alice
  | gọi service được Spring bảo vệ -> đánh giá quyền Alice
  | finally: clear context
  v
thread về pool, không giữ Alice cho task khác
~~~

**Điểm mấu chốt:** `@Async` chỉ lo **đưa method sang executor**. Nó không phải tính năng tự truyền toàn bộ thread-local state. `@EnableMethodSecurity` kích hoạt kiểm tra quyền phương thức nhưng cũng không tự truyền ngữ cảnh sang worker.

## 3. SecurityContext có những ranh giới nào?

### 3.1. Thread-local, không phải global cho mọi request

| Chiến lược/cơ chế | Hành vi | Dùng trong tình huống này? |
| --- | --- | --- |
| `MODE_THREADLOCAL` (thông dụng/mặc định) | Context thuộc thread hiện tại | Phù hợp request thread; executor cần wrapper để chuyển context |
| `MODE_INHERITABLETHREADLOCAL` | Thread **con mới tạo** có thể kế thừa tham chiếu context lúc tạo | **Không** là giải pháp an toàn chung cho pool tái sử dụng thread |
| `MODE_GLOBAL` | Một context chia sẻ cho toàn bộ JVM | **Không** phù hợp ứng dụng server nhiều người dùng |
| `DelegatingSecurityContext...` | Bọc từng task, cài context khi thực thi, dọn sau thực thi | Cách phù hợp cho executor work cần danh tính caller |
| Explicit principal/tenant/scope trong job payload | Mang dữ liệu nghiệp vụ qua ranh giới, có xác minh lại | Phù hợp long-running/durable jobs, queue hoặc service khác |

Không đổi `SecurityContextHolder.setStrategyName(MODE_INHERITABLETHREADLOCAL)` chỉ để “chữa” `@Async`. Pool có thể tạo thread trước khi request bắt đầu; thread được tái sử dụng, không kế thừa lại context ở mỗi lần submit. Hơn nữa, context có thể bị truyền tới thread con **không cần quyền đó**.

### 3.2. Capture context khác với tạo quyền mới

Chuyển context chỉ có nghĩa **worker thấy một Authentication được chuyển sang**, không có nghĩa quyền đó còn hiệu lực mãi mãi hoặc mọi resource đều cho phép. Worker vẫn phải gọi method security hoặc domain policy. Khi task chờ lâu, role có thể đã đổi hoặc tài khoản bị khóa; một snapshot cũ không tự được làm mới.

Mọi task cũng không nên nhân danh request user. Ví dụ:
- **Công việc yêu cầu chính Alice và quyền hiện tại của Alice:** truyền context của Alice khi submit, và cân nhắc re-check khi thực thi.
- **Bảo trì định kỳ của hệ thống:** chạy dưới service identity riêng với quyền tối thiểu; không sao chép context của request ngẫu nhiên.
- **Job kéo dài qua restart/messaging:** lưu actor ID/tenant/permission intent có kiểm soát; ở worker process khác phải thiết lập và xác minh một identity đáng tin, không “copy `ThreadLocal` qua Kafka”.

## 4. @Async thật sự hoạt động ở đâu?

Cần bật async processing:

~~~java
@Configuration
@EnableAsync
class AsyncConfiguration {
}
~~~

Khi phương thức có `@Async` được **gọi qua Spring proxy**, Spring gửi lời gọi vào `TaskExecutor` phù hợp; caller có thể nhận về `CompletableFuture`/`Future` ngay, còn thân method chạy ở thread do executor quyết định. Có thể chọn executor theo tên:

~~~java
// Đoạn trích trong Spring-managed bean.
@Async("securedWorkerExecutor")
public CompletableFuture<String> calculate() {
    return CompletableFuture.completedFuture("done");
}
~~~

**Không được nhầm `@Async` với “tự chạy song song” trong mọi trường hợp:**

- `this.calculate()` từ cùng bean thường **không đi qua proxy**, nên `@Async` không được kích hoạt ở proxy mode mặc định.
- `@EnableAsync` và `@EnableMethodSecurity` là hai cơ chế kích hoạt riêng; nếu gọi một method gắn `@PreAuthorize` qua self-invocation, authorization cũng có thể bị bỏ qua.
- `@Async` với `void` không có future để chuyển exception cho caller; nên cấu hình `AsyncUncaughtExceptionHandler` hoặc cơ chế log/monitor phù hợp.
- `CompletableFuture.get()/join()` đưa ngoại lệ từ worker về caller khi đợi; không nhầm “đã submit” với “đã thành công”.
- Với `@Async`, hàm có kết quả thường trả `Future`/`CompletableFuture`; không dùng một giá trị `String` thường rồi mong Spring tự biến thành future.
- Nếu bạn viết `CompletableFuture.supplyAsync(...)` bên trong `@Async` mà không truyền executor, bạn tạo **ranh giới thread thứ hai** (thường common pool) và có thể lại mất security context. Trong phương thức đã async, tạo `completedFuture(...)` sau khi xử lý đồng bộ trên worker thường dễ lý giải hơn.

### 4.1. Thứ tự giữa @Async, @PreAuthorize và @Transactional

Các advice/proxy có thứ tự do framework/cấu hình quyết định. Đừng suy luận rằng hai annotation gắn cùng một method sẽ luôn chạy trên cùng một thread hoặc theo thứ tự bạn muốn. Cách dễ kiểm thử là:

- Bean A chứa method `@Async("securedWorkerExecutor")`.
- Bean B chứa method `@PreAuthorize` thực thi policy trên worker.
- Bean C (nếu cần) quản lý giao dịch DB trong worker.

Khi A gọi B **qua Spring bean proxy**, worker đã được wrapper cài `SecurityContext` rồi mới tới method security của B. Cấu trúc này làm ranh giới rõ ràng và tránh dựa vào advisor ordering giữa `@Async` với `@PreAuthorize` trên cùng method.

## 5. Dùng DelegatingSecurityContextAsyncTaskExecutor

Spring Security cung cấp `org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor`, một `AsyncTaskExecutor` bọc task trước khi chuyển tới executor thật. Wrapper của `Runnable`/`Callable` cài `SecurityContext` vào worker trước khi chạy delegate và dọn context trong `finally` sau đó.

### 5.1. Hai kiểu constructor có ý nghĩa khác nhau

**Dùng context tại lúc submit (thường đúng cho user-triggered @Async):**

~~~java
AsyncTaskExecutor secured = new DelegatingSecurityContextAsyncTaskExecutor(
        rawAsyncTaskExecutor);
~~~

Không truyền `SecurityContext` cố định: wrapper lấy context của thread **đang submit task** để chuyển sang worker. Nếu Alice submit rồi Bob submit, mỗi task đi với context ở thời điểm tương ứng. Đừng hiểu đây là “constructor chụp vĩnh viễn Alice” khi tạo bean.

**Dùng một context được cấp rõ ràng cho mọi task:**

~~~java
SecurityContext systemContext = SecurityContextHolder.createEmptyContext();
// Đặt Authentication của service identity đã được xác minh bằng cách đáng tin.
AsyncTaskExecutor secured = new DelegatingSecurityContextAsyncTaskExecutor(
        rawAsyncTaskExecutor, systemContext);
~~~

Trường hợp thứ hai chỉ phù hợp khi **mọi task** cố ý chạy dưới cùng identity (ví dụ subsystem được thiết kế làm công việc hệ thống). Đừng cấp principal quản trị cố định chỉ để các task qua `@PreAuthorize`; điều đó có thể biến lỗ hổng truyền context thành lỗ hổng leo thang quyền. Không dùng đối tượng `Authentication` giả tự tạo theo dữ liệu client để “vượt qua” kiểm tra.

### 5.2. Một wrapper không phải một transaction, request hay trace wrapper

Wrapper security chỉ quản lý `SecurityContextHolder`; nó **không tự chuyển**:
- Giao dịch `@Transactional`, JDBC connection, `EntityManager` hoặc persistence context của request.
- `RequestContextHolder`/`HttpServletRequest`, session đã kết thúc.
- SLF4J MDC/correlation IDs, `LocaleContextHolder`, tracing state hoặc các custom `ThreadLocal` khác.
- Identity/token tới một process khác.

Nếu cần MDC/trace, dùng cơ chế context propagation được hỗ trợ riêng và xác định thứ tự cleanup; đừng gom các trạng thái không liên quan vào `SecurityContext` hoặc sử dụng static/global user. Luôn xóa/khôi phục state trong `finally`.

### 5.3. Lưu ý tham chiếu mutable và thời điểm submit

`SecurityContext` là một đối tượng có thể thay đổi. Khi chuyển **cùng một instance** sang task, đừng dùng các lời gọi `SecurityContextHolder.getContext().setAuthentication(...)` để liên tục tráo user trên context đang được các task giữ tham chiếu. Khi thay identity, tạo context mới:

~~~java
SecurityContext separate = SecurityContextHolder.createEmptyContext();
separate.setAuthentication(trustedAuthentication);
SecurityContextHolder.setContext(separate);
~~~

Đây là hướng dẫn **thao tác trên context hợp lệ đã xác minh**, không phải cách tự nâng quyền. Nếu task cần snapshot đáng tin và tồn tại lâu, hãy thiết kế dữ liệu authorization/identity riêng theo contract và kiểm tra lại tại execution time. Việc “capture lúc submit” không đồng nghĩa đóng băng mọi thuộc tính mutable, không bảo đảm tránh thay đổi quyền hoặc hết hạn token.

## 6. Ví dụ Spring Boot: executor thô và executor đã truyền SecurityContext

Ví dụ này dùng Spring Boot application context, không cần REST controller, để cô lập việc `@Async` và method security. Các phần nằm trong **một file Java** và chạy được trong một dự án Spring Boot cấu hình đúng dependencies. Một bean `ThreadPoolTaskExecutor` dùng chung pool một thread, có hai đường gọi:

- `@Async("rawWorkerPool")`: worker nhận **không có** context từ caller.
- `@Async("securedWorkerExecutor")`: wrapper chuyển context của caller vào worker, sau đó dọn.
- Một **bean khác** dùng `@PreAuthorize` để chứng minh quyền thực sự được đánh giá trong worker.

Tạo `src/main/java/demo/asyncsecurity/AsyncSecurityApplication.java`:

~~~java
package demo.asyncsecurity;

import java.util.concurrent.CompletableFuture;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;
import org.springframework.stereotype.Service;

@SpringBootApplication
@EnableAsync
@EnableMethodSecurity
public class AsyncSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(AsyncSecurityApplication.class, args);
    }

    @Bean(name = "rawWorkerPool")
    ThreadPoolTaskExecutor rawWorkerPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(20);
        pool.setThreadNamePrefix("report-worker-");
        pool.initialize();
        return pool;
    }

    @Bean(name = "securedWorkerExecutor")
    AsyncTaskExecutor securedWorkerExecutor(
            @Qualifier("rawWorkerPool") ThreadPoolTaskExecutor delegate) {
        // Không truyền SecurityContext cố định:
        // lấy ngữ cảnh của thread submit riêng cho từng task.
        return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
    }
}

@Service
class ProtectedReportReader {
    // Method này được gọi từ bean khác qua Spring proxy.
    @PreAuthorize("hasAuthority('report:read')")
    public String readUnderCurrentPrincipal() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        return auth.getName();
    }
}

@Service
class AsyncReportReader {
    private final ProtectedReportReader securedReader;

    AsyncReportReader(ProtectedReportReader securedReader) {
        this.securedReader = securedReader;
    }

    @Async("rawWorkerPool")
    public CompletableFuture<String> nameWithoutPropagation() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        return CompletableFuture.completedFuture(
                auth == null ? "anonymous" : auth.getName());
    }

    @Async("securedWorkerExecutor")
    public CompletableFuture<String> nameWithPropagationAndAuthorization() {
        String name = securedReader.readUnderCurrentPrincipal();
        return CompletableFuture.completedFuture(name);
    }
}
~~~

**Dependencies Gradle** trong một dự án đã bật Spring Boot plugin, dependency management và Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Có thể chạy application bằng wrapper của dự án (ví dụ `./gradlew bootRun` trên Unix hoặc `gradlew.bat bootRun` trên Windows). Demo không khai báo HTTP endpoint và không tạo tài khoản thực. Để có bằng chứng xác thực, chạy `./gradlew test` với test ở phần tiếp theo. Để dùng trong API thật, thêm Spring Web/SecurityFilterChain phù hợp và đảm bảo request caller có `Authentication` trước khi submit.

### 6.1. Đọc đường gọi của ví dụ

~~~text
@WithMockUser(alice, report:read) / request xác thực
  |
  +-- asyncReportReader.nameWithoutPropagation()
  |    |
  |    +-- @Async("rawWorkerPool")
  |         worker thread: auth == null -> "anonymous"
  |
  +-- asyncReportReader.nameWithPropagationAndAuthorization()
       |
       +-- @Async("securedWorkerExecutor")
            wrapper lấy context Alice tại submit
            rawWorkerPool chạy task với context Alice
                |
                +-- protectedReportReader.readUnderCurrentPrincipal()
                    Spring proxy @PreAuthorize("hasAuthority('report:read')")
                    => PASS, kết quả "alice"
            finally: dọn context Alice khỏi worker
~~~

Một pool có một thread làm tính chất tái sử dụng dễ kiểm chứng, nhưng **không phải** yêu cầu để wrapper đúng. Production có thể chọn pool size/queue policy theo tải, giới hạn backpressure và SLA. Nếu không kiểm soát queue và rejection, async task có thể bị từ chối khi quá tải; lỗi submit không đồng nghĩa lỗi authorization.

### 6.2. Vì sao tạo bean riêng cho raw pool?

Ta giữ `rawWorkerPool` dưới Spring lifecycle để Spring quản lý shutdown và dùng nó làm delegate cho wrapper. Bean `securedWorkerExecutor` chỉ chịu trách nhiệm chuyển `SecurityContext`. Nhờ `@Async("securedWorkerExecutor")`, method cụ thể dùng đúng executor đã bọc.

**Trong code production, đừng mặc định cho mọi `@Async` quyền sử dụng raw pool.** Có thể chỉ expose secured executor cho các tác vụ cần principal; đặt tên rõ cho nhiệm vụ chạy dưới service identity; tránh một nhóm method vô tình dùng executor không truyền context. Nếu viết `@Async` không chỉ định, Spring sẽ chọn executor theo cấu hình và cơ chế chọn mặc định; không coi đó luôn là `securedWorkerExecutor`.

## 7. Kiểm thử end-to-end method security trong worker

Đặt `src/test/java/demo/asyncsecurity/AsyncSecurityApplicationTest.java` cùng package:

~~~java
package demo.asyncsecurity;

import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class AsyncSecurityApplicationTest {
    @Autowired
    AsyncReportReader reader;

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void transfersAliceAndClearsWorkerAfterward() throws Exception {
        assertEquals("anonymous",
                reader.nameWithoutPropagation()
                        .get(3, TimeUnit.SECONDS));

        assertEquals("alice",
                reader.nameWithPropagationAndAuthorization()
                        .get(3, TimeUnit.SECONDS));

        // Raw pool chỉ có một worker, nên lần gọi sau dùng lại cùng thread.
        assertEquals("anonymous",
                reader.nameWithoutPropagation()
                        .get(3, TimeUnit.SECONDS));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "profile:read")
    void methodSecurityDeniesEvenWithContextTransferred()
            throws Exception {
        ExecutionException failure = assertThrows(
                ExecutionException.class,
                () -> reader.nameWithPropagationAndAuthorization()
                        .get(3, TimeUnit.SECONDS));

        assertInstanceOf(AccessDeniedException.class,
                failure.getCause());

        // Đường lỗi cũng phải dọn context khỏi worker.
        assertEquals("anonymous",
                reader.nameWithoutPropagation()
                        .get(3, TimeUnit.SECONDS));
    }

    @Test
    @WithMockUser(username = "carol", authorities = "report:read")
    void nextCallerGetsOwnPrincipal() throws Exception {
        assertEquals("carol",
                reader.nameWithPropagationAndAuthorization()
                        .get(3, TimeUnit.SECONDS));

        assertEquals("anonymous",
                reader.nameWithoutPropagation()
                        .get(3, TimeUnit.SECONDS));
    }
}
~~~

### Kỳ vọng của từng test

| Trường hợp | Dấu hiệu quan trọng |
| --- | --- |
| `nameWithoutPropagation` dù request/test là Alice | `anonymous` trong worker; @Async không tự truyền auth |
| `nameWithPropagationAndAuthorization` với Alice có quyền đọc | Worker thấy Alice và `@PreAuthorize` cho phép |
| Bob thiếu `report:read` | `Future.get()` ném `ExecutionException` chứa `AccessDeniedException` |
| Sau task thành công/thất bại, gọi qua raw pool | `anonymous`: không giữ principal ở thread tái sử dụng |
| Carol submit sau những task trước | Kết quả Carol, không phải Alice/Bob |

Bằng chứng cuối dựa vào **một worker** được cấu hình ở ví dụ, không nên dùng điều đó làm thuật toán kiểm tra production đa luồng. Trong production, dùng test có task barrier và tracking riêng để phát hiện contamination dưới nhiều users/threads.

**Lưu ý:** `@WithMockUser` đặt authentication trong security context của test thread, không biến mất chỉ vì async task hoàn tất. Mục tiêu kiểm thử ở đây là wrapper chuyển context từ test thread vào executor thread, kiểm tra method security tại worker và dọn worker. Một bài test chỉ khởi tạo service bằng `new` sẽ **không** kiểm tra được Spring proxy.

## 8. Java 17 độc lập: mô phỏng capture/restore theo từng task

Ví dụ chỉ dùng JDK, không sử dụng Spring Security. Nó mô phỏng `ThreadLocal` và executor để người học nhìn thấy rõ sự khác biệt giữa một task raw và task được bọc. Cơ chế minh họa có thêm bước **khôi phục giá trị worker trước đó** trong `finally`; Spring Security dùng wrapper quản lý `SecurityContextHolder` riêng và tài liệu của framework mô tả hành vi dọn context sau task.

Lưu thành `ThreadContextDemo.java`:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadContextDemo {
    private static final ThreadLocal<String> USER = new ThreadLocal<>();

    static <T> Callable<T> propagate(Callable<T> operation) {
        // Capture khi caller submit, không lấy lại bên trong worker.
        String captured = USER.get();

        return () -> {
            String previous = USER.get();
            try {
                if (captured == null) {
                    USER.remove();
                } else {
                    USER.set(captured);
                }
                return operation.call();
            } finally {
                if (previous == null) {
                    USER.remove();
                } else {
                    USER.set(previous);
                }
            }
        };
    }

    static String currentName() {
        String user = USER.get();
        return user == null ? "anonymous" : user;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            USER.set("alice");
            System.out.println("raw=" +
                    pool.submit(ThreadContextDemo::currentName).get());

            System.out.println("alice=" +
                    pool.submit(propagate(ThreadContextDemo::currentName))
                            .get());

            USER.set("bob");
            System.out.println("bob=" +
                    pool.submit(propagate(ThreadContextDemo::currentName))
                            .get());

            System.out.println("after=" +
                    pool.submit(ThreadContextDemo::currentName).get());
        } finally {
            USER.remove();
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ThreadContextDemo.java
java ThreadContextDemo
~~~

**stdout chính xác** (chương trình `get()` để tuần tự hóa thứ tự in):

~~~text
raw=anonymous
alice=alice
bob=bob
after=anonymous
~~~

**Giải thích kết quả:** `raw` chạy trực tiếp trên pool thread, không thấy `ThreadLocal` của caller. Hai lệnh `propagate(...)` chụp lần lượt Alice và Bob ở thread submit; worker cài đúng giá trị rồi dọn. Lần raw cuối xác nhận worker không giữ Bob. Với app Spring, hãy dùng `DelegatingSecurityContext...` thay vì viết wrapper security thủ công khi framework đã hỗ trợ.

## 9. @Async và @Transactional: hai ranh giới cần quản lý riêng

`SecurityContext` có thể được chuyển sang worker nhờ wrapper, nhưng **transaction context không tự đi theo**. Ví dụ:

~~~java
// Sơ đồ nghiệp vụ, không phải chương trình độc lập.
@Transactional
public void approveAndNotify(long invoiceId) {
    invoiceRepository.markApproved(invoiceId);
    notificationService.sendAsync(invoiceId); // @Async ở bean khác
}
~~~

Nếu `sendAsync` chạy nhanh, có thể thực thi **trước lúc transaction của approveAndNotify commit**. Nó có thể không thấy dữ liệu mới hoặc gửi thông báo cho giao dịch cuối cùng rollback. Truyền `SecurityContext` không giải quyết được race đó.

Nguyên tắc:

1. `@Transactional` mở và kết thúc giao dịch gắn với thread thực thi theo transaction manager tương ứng. Khi đổi thread, không tự mang theo JDBC transaction/persistence context của caller.
2. Nếu method thực thi **trong worker** cần transaction riêng, gọi bean `@Transactional` qua Spring proxy ngay trong worker; kiểm tra read/write và rollback tại transaction của worker.
3. Nếu task chỉ được chạy sau khi dữ liệu commit, cân nhắc `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` để gửi lệnh async **sau commit** (nhưng event listener không tự biến tác vụ thành durable). Với yêu cầu delivery đáng tin sau restart hoặc khi executor lỗi, dùng transactional outbox/queue và retry có idempotency.
4. Không mang JPA entity đang lazy-loading qua async thread rồi giả định session còn mở. Chuyển ID/DTO tối thiểu, đọc lại trong transaction riêng nếu cần.
5. Nếu business cần kiểm tra quyền theo tenant ở thời điểm worker thực sự chạy, dùng identity/tenant đã xác thực và kiểm tra lại policy với dữ liệu hiện tại. Caller có quyền lúc enqueue không đồng nghĩa task còn được phép sau vài giờ.

### 9.1. Gắn @Async và @Transactional cùng method?

Có thể có cấu hình để worker mở transaction riêng, nhưng tương tác proxy/advice dễ bị hiểu nhầm. Cách minh bạch là tách bean async và bean transactional:

~~~java
// Đoạn minh họa, tên bean/method thuộc ứng dụng của bạn.
@Service
class AsyncCoordinator {
    private final TransactionalWorker worker;

    AsyncCoordinator(TransactionalWorker worker) {
        this.worker = worker;
    }

    @Async("securedWorkerExecutor")
    public CompletableFuture<Void> execute(long id) {
        worker.processOne(id);
        return CompletableFuture.completedFuture(null);
    }
}

@Service
class TransactionalWorker {
    @Transactional
    public void processOne(long id) {
        // Mở transaction mới từ worker thread khi gọi qua proxy.
        // Tra lại trạng thái/tài nguyên và áp dụng quyền trước khi ghi.
    }
}
~~~

Khối trên **chưa độc lập**: thiếu import và logic lưu trữ. Nó minh họa chủ đích ranh giới; không thay thế đầy đủ lỗi, idempotency, timeout hay transaction propagation configuration. Nếu chính service transactional là ranh giới authorization, thêm `@PreAuthorize` hoặc policy phù hợp để bảo vệ khi job/HTTP gọi qua các đường khác nhau.

## 10. Đúng phạm vi: “truyền Authentication” khác với “cấp quyền”

### 10.1. Quyền tại thời điểm giao việc và tại thời điểm chạy

Có ít nhất ba thời điểm:
- **t0:** request Alice được xác thực và muốn tạo job.
- **t1:** hệ thống đưa task vào executor queue; wrapper chụp context của thread submit.
- **t2:** worker thực thi task sau khi t0 và t1 đã qua.

Nếu tài khoản Alice bị khóa ở giữa t1/t2, context đã capture không phải phép kiểm chứng trạng thái tài khoản mới. Method security có thể đánh giá authority nằm trong `Authentication` cũ, trừ khi policy chủ động tra trạng thái cập nhật. Chọn một trong các contract có giải thích rõ:

| Contract | Cách xử lý gợi ý |
| --- | --- |
| Task ngắn, gắn chặt với request | Capture context tại submit, kiểm tra quyền tại worker, dọn context sau task |
| Tác vụ kéo dài, rủi ro cao, quyền có thể bị thu hồi | Lưu actor/tenant/scope tối thiểu; xác minh lại trước thao tác nhạy cảm |
| Background job hệ thống | Service identity riêng, quyền tối thiểu, audit “on behalf of” khi có |
| Tác vụ message queue/process khác | Không truyền Java `ThreadLocal`; xác minh identity trong worker, bảo vệ message payload, idempotency |

Cần phân biệt **thực hiện theo quyền của người tạo yêu cầu** và **thực hiện theo quyền hiện tại của hệ thống**. Cả hai có thể hợp lệ tùy nghiệp vụ, nhưng không được vô tình chạy bằng một identity khác do pool reuse.

### 10.2. Một SecurityContext instance không phải snapshot bất biến

Nếu code cùng dùng `SecurityContext` mutable ở nhiều thread, thao tác đổi `Authentication` trong context đó có thể gây hiệu ứng ngoài ý muốn. Không dùng một instance static hay singleton để đại diện “current user”. Khi cần thay authentication trên thread, tạo `SecurityContextHolder.createEmptyContext()` mới, kiểm soát phạm vi và dọn đúng lifecycle. Với job cần tính ổn định lâu dài, truyền một **identity claim đã xác minh**, sau đó dựng/kiểm chứng context theo cơ chế authentication hợp lệ của worker.

### 10.3. Đừng truyền credentials quá rộng

`Authentication` có thể chứa details hoặc credential nhạy cảm tùy provider. Chuyển context sang task chỉ khi task thật sự cần và trong cùng trust boundary. Với queue, audit log hoặc lưu DB, **không serialize nguyên `SecurityContext`** một cách tùy tiện. Dùng actor ID, tenant ID, correlation ID và ý định hành động tối thiểu; giải quyết quyền bằng policy khi cần.

### 10.4. Method security vẫn là enforcement

Nếu worker chỉ thực hiện:

~~~java
String username = authentication.getName();
emailGateway.send(...);
~~~

việc có `username` không chứng minh email đó được phép gửi. Phải đánh giá cả authority và quyền trên tài nguyên, ví dụ `@PreAuthorize("hasAuthority('report:read')")`, bean policy ACL hoặc service validation. Nếu user chỉ có quyền đọc báo cáo A, context của user không tự cấp quyền đọc báo cáo B. Kiểm tra phạm vi tenant, resource ownership và không đặt trust vào ID client cung cấp.

## 11. Các cơ chế liên quan nhưng không tương đương

### 11.1. DelegatingSecurityContextRunnable và Callable

Với một task riêng lẻ không đi qua Spring `@Async`:

~~~java
// Trong thread đã có SecurityContext hợp lệ:
Runnable securedTask =
        new DelegatingSecurityContextRunnable(() -> protectedService.run());
executor.execute(securedTask);
~~~

Wrapper ngắn gọn phù hợp khi bạn kiểm soát submission thủ công. Nếu mọi task trên executor cần context của caller, bọc **executor** một lần thường ít lỗi hơn bọc từng Runnable thủ công. Với `Callable` có kết quả, dùng `DelegatingSecurityContextCallable`. Với `ExecutorService` chuẩn, Spring Security có `DelegatingSecurityContextExecutorService`.

Cần nhớ **wrap xảy ra tại đâu**: đối tượng `Runnable`/`Callable` nên được bọc khi caller có context hợp lệ, hoặc executor wrapper sẽ bọc khi submit. Đừng tạo task rồi để nó được bọc lần đầu trong worker sau khi context của caller đã biến mất.

### 11.2. TaskDecorator

Spring `ThreadPoolTaskExecutor` hỗ trợ `TaskDecorator` để bổ sung logic quanh task, hay dùng cho MDC/observability. Nếu tự làm security propagation qua decorator, phải xử lý capture, cleanup, wrapper layering và trạng thái bị ghi đè; đối với `SecurityContext`, ưu tiên abstraction `DelegatingSecurityContext...` chuyên dụng. Kết hợp nhiều decorator/wrapper có thể dẫn đến capture sai thời điểm hoặc dọn context trong thứ tự ngoài dự kiến; viết integration test theo các đường gọi thật.

### 11.3. Servlet async, MVC Callable, WebFlux không giống @Async

- Servlet `AsyncContext.start(...)` và Spring MVC async return type có các điểm tích hợp với Spring Security riêng, **không tự suy ra** từ cách viết `@Async` của service.
- Reactor/WebFlux có `ReactiveSecurityContextHolder` gắn với Reactor Context chứ không phải chỉ với một thread-local truyền qua executor giống Servlet.
- Java virtual threads có ngữ nghĩa tạo thread khác pool truyền thống nhưng không biến `SecurityContext` thành global state; vẫn cần phương pháp propagation theo execution model.
- `CompletableFuture.supplyAsync(...)` có executor riêng; nếu không truyền executor phù hợp, không thể dựa vào `@Async("securedWorkerExecutor")` ở method bên ngoài để bảo vệ công việc trên thread tiếp theo.

## 12. Lỗi phổ biến và cách nhận biết

### Lỗi 1 — “Bật @EnableAsync và @EnableMethodSecurity là đủ”

Triệu chứng: request thành công trước khi async, chuyển sang async lại bị `AccessDeniedException` hoặc `Authentication` null. Nguyên nhân: security context là thread-local và không được chuyển qua worker. Chọn executor bọc context, kiểm thử thực tế qua proxy.

### Lỗi 2 — Dùng MODE_INHERITABLETHREADLOCAL cho thread pool

Có thể cho kết quả đúng ngẫu nhiên nếu pool vừa tạo thread trong request của Alice, sau đó sai khi Bob dùng lại thread. Đây là giải pháp nguy hiểm cho ứng dụng nhiều người dùng. Không dùng làm cơ chế chuẩn cho pool; wrapper per-task mới gắn với user **ở thời điểm submit**.

### Lỗi 3 — Set context trong worker rồi không clear

~~~java
// Phản ví dụ không an toàn:
SecurityContextHolder.setContext(aliceContext);
doWork(); // ném exception thì thread có thể giữ Alice mãi
~~~

Hãy dùng wrapper Spring Security; nếu buộc tự quản lý, phải đặt cleanup/restore vào `finally` và test cả đường ném exception, cancellation và rejection. Đừng dùng một static `SecurityContext` cho mọi task.

### Lỗi 4 — Một executor bọc fixed admin context

Mọi task vô tình được nâng lên quyền admin, che giấu việc caller không đủ quyền. Chỉ dùng fixed context khi **cố ý thiết kế service identity**, được cấp phát đáng tin và chỉ có đúng quyền cần thiết, phân biệt job hệ thống với user task.

### Lỗi 5 — @Async bị vô hiệu vì self-invocation

~~~java
@Service
class WrongAsyncService {
    public void start() {
        doAsync(); // this.doAsync(): bypass proxy mặc định
    }

    @Async("securedWorkerExecutor")
    public void doAsync() {
        // Có thể chạy ngay trên caller thread.
    }
}
~~~

Giải pháp: tách `doAsync` sang bean khác và gọi qua bean được Spring quản lý, hoặc lựa chọn cơ chế interception khác có chủ đích. Đừng dựa vào việc có annotation để khẳng định đã đổi thread.

### Lỗi 6 — Hậu kiểm/transaction bị nhầm phạm vi

Task đọc entity chưa commit, hoặc gửi email rồi caller transaction rollback. Việc truyền context Alice không kéo theo transaction hay rollback. Thiết kế after-commit, transaction riêng hoặc outbox, đồng thời re-check policy tại điểm ghi.

### Lỗi 7 — Future bị bỏ qua và lỗi bị nuốt

`@Async void` có thể log exception ở nơi không ai theo dõi; `CompletableFuture` trả về nhưng caller không quan sát lỗi thì job thất bại âm thầm. Dùng future/monitoring, retry policy, idempotency và log đủ correlation ID **không tiết lộ credentials**. Bắt riêng lỗi authorization: không retry mù quáng một `AccessDeniedException` như lỗi mạng tạm thời.

### Lỗi 8 — Nghĩ rằng truyền context có nghĩa đã xác minh quyền

Caller có một `Authentication` không đồng nghĩa mọi thao tác đều được phép. Method security và policy phải kiểm tra authority, tenant, ownership và trạng thái tài nguyên; nếu task được chạy muộn, cân nhắc quyền bị thu hồi.

### Lỗi 9 — Async task tạo thêm async task qua common pool

`CompletableFuture.supplyAsync` mặc định có thể dùng `ForkJoinPool.commonPool`; thread thứ hai thiếu wrapper context. Chỉ định executor thích hợp cho **mỗi** ranh giới submit, hoặc giữ công việc trong một executor đã cấu hình và kiểm thử tất cả nhánh.

### Lỗi 10 — Dùng credential của HTTP request cho job bền vững

Request logout, token hết hạn hoặc thread kết thúc nhưng job còn nằm trong queue lâu. Job có thể thiếu quyền mới nhất hoặc lưu credential không phù hợp. Phân tách request-scoped task với durable job; truyền actor/tenant/scope tối thiểu và xác minh lại bằng nguồn tin cậy khi thực thi.

## 13. Ma trận kiểm thử tối thiểu cho ứng dụng thật

| Case | Điều cần chứng minh |
| --- | --- |
| Caller Alice có quyền đọc | Worker được chuyển đúng Authentication Alice |
| Caller Bob có quyền khác | Worker từ chối ở method security, không “mượn” Alice |
| Caller anonymous/không có context | Fail closed; không tự gán quyền mặc định |
| Task ném exception | Context worker được dọn/khôi phục; future biểu diễn lỗi |
| Pool có một thread và gọi Alice → Bob → Alice | Không có cross-user contamination |
| Pool có nhiều thread và task song song | Mỗi task gắn identity tại điểm submit |
| Bean gọi nội bộ `this.@AsyncMethod` | Test phát hiện lời gọi không đi qua proxy |
| Gọi service từ scheduled job/message listener | Identity rõ, method authorization vẫn được enforce |
| Transaction caller rollback | Async action không bị hiểu nhầm là giao dịch caller |
| User bị thu hồi quyền trước khi task chạy | Policy re-check theo contract; task không mặc nhiên giữ quyền mãi |
| Queue đầy, executor shutdown, task cancel | Không có kết quả “thành công giả”; cleanup/monitoring đúng |
| Nested `CompletableFuture`/executor | Mỗi thread boundary có context propagation thích hợp |

Không kiểm chứng bằng việc in `Thread.currentThread().getName()` rồi suy ra bảo mật. Cần assert **principal/authorities đúng từng task, không rò rỉ sau task, và quyết định quyền đúng trong service**. Nếu có HTTP endpoint, bổ sung `MockMvc` để xác minh request filter chain; `@WithMockUser` ở test service đơn thuần chưa bảo đảm đường đi HTTP thực tế.

## 14. Quy tắc lựa chọn trong thực tế

1. **Task ngắn do user đã xác thực kích hoạt và cần method security?** Dùng `@Async("securedWorkerExecutor")` với `DelegatingSecurityContextAsyncTaskExecutor` không truyền context cố định; test auth và cleanup.
2. **Task không cần danh tính user?** Không truyền context cho bằng được; dùng hợp đồng service/job có identity rõ, quyền tối thiểu.
3. **Đầu việc chậm/được xếp hàng lâu?** Thiết kế re-authorization hoặc service identity khi thực thi; không tin snapshot authority cũ một cách vô thời hạn.
4. **Tác vụ làm thay đổi DB?** Tạo transaction thích hợp trên worker, bảo vệ trạng thái tại điểm ghi, và tách thời điểm commit của caller.
5. **Dữ liệu đến từ tenant khác hoặc qua queue/process?** Không chuyển raw context/credential bừa bãi; validate identity và resource scope tại điểm xử lý.
6. **Nhiều executor/nested futures?** Kiểm tra executor nào thực sự chạy mỗi đoạn; đừng giả định wrapper ở tầng ngoài tự bảo vệ mọi thread.

### Câu hỏi tự luyện

**Câu 1:** Alice có `report:read` gọi `@Async` qua raw executor và bên worker gọi một bean `@PreAuthorize("hasAuthority('report:read')")`. Vì sao có thể bị từ chối?

**Đáp án:** `@Async` đổi thread; `SecurityContextHolder` mặc định là thread-local, worker không có authentication của Alice. Cần executor bọc context tại submission và tiếp tục kiểm tra quyền trong worker.

**Câu 2:** Bật `MODE_INHERITABLETHREADLOCAL` có giải quyết triệt để cho thread pool không?

**Đáp án:** Không. Pool tái sử dụng thread đã tồn tại; thừa kế xảy ra ở thời điểm tạo child thread và có nguy cơ giữ danh tính sai giữa tasks.

**Câu 3:** Wrapper đã chuyển Authentication rồi, có cần `@PreAuthorize`/kiểm tra ACL ở worker không?

**Đáp án:** Vẫn cần. Propagation chỉ cung cấp dữ liệu danh tính; enforcement quyết định task được làm gì với tài nguyên nào.

**Câu 4:** Cập nhật invoice trong transaction request, submit async email ngay, sau đó transaction rollback. Truyền context có giải quyết được không?

**Đáp án:** Không. Security context khác transaction. Cần đồng bộ với commit (after-commit/outbox), xử lý giao dịch riêng trong worker và idempotency.

**Câu 5:** `CompletableFuture.supplyAsync` bên trong một `@Async` đã dùng secured executor có tự an toàn không?

**Đáp án:** Không thể giả định. Nó có thể chạy trên executor khác; phải truyền executor phù hợp ở lần submit tiếp theo.

## Tài liệu đối chiếu

- [Spring Security – Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html): `SecurityContextHolder` theo thread; `DelegatingSecurityContextRunnable` và `DelegatingSecurityContextExecutor`, ngữ nghĩa capture/cleanup.
- [DelegatingSecurityContextAsyncTaskExecutor Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/task/DelegatingSecurityContextAsyncTaskExecutor.html): hai constructor, wrapper `Runnable`/`Callable`, giao diện `AsyncTaskExecutor`.
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableAsync`, `@Async`, chọn executor, proxy/self-invocation và xử lý exception.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, method interception.
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy boundary và transaction semantics.
