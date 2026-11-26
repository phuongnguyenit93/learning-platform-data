# DelegatingSecurityContextRunnable và Callable: truyền SecurityContext qua tác vụ bất đồng bộ

Một API Servlet có thể xác thực Alice thành công trong request HTTP, nhưng khi controller chuyển công việc sang `ExecutorService`, đoạn mã chạy ở worker thread lại không tìm thấy `Authentication`. Nếu tác vụ cần ghi audit, kiểm tra quyền hoặc gọi một service được bảo vệ bằng `@PreAuthorize`, mất danh tính có thể làm thao tác thất bại; nguy hiểm hơn, truyền ngữ cảnh không đúng có thể khiến **quyền của request trước rò sang request sau**.

Trong chương **Bất đồng bộ và ngữ cảnh** của **SPRING_SECURITY_TESTING**, chúng ta kiểm chứng vấn đề này bằng `spring-security-test`, JUnit, `MockMvc` và đối chiếu `WebTestClient`. Trọng tâm là **`DelegatingSecurityContextRunnable` và `DelegatingSecurityContextCallable` theo cơ chế mà ứng dụng đang dùng**: ThreadLocal trên Servlet, executor hoặc `@Async` ở phía imperative; Reactor Context trên WebFlux thì cần cách xử lý khác.

Sau bài học, người học cần phân biệt được việc **xác thực request**, **truyền ngữ cảnh sang tác vụ khác**, **giới hạn phạm vi đặc quyền** và **dọn SecurityContext sau khi chạy**. Một test `@WithMockUser` thành công trên request thread chưa chứng minh danh tính đã được truyền sang thread pool.

## 1. Vì sao SecurityContext biến mất khi đổi thread?

Trong ứng dụng Servlet, `SecurityContextHolder` mặc định sử dụng chiến lược `MODE_THREADLOCAL`. Một `SecurityContext` chứa `Authentication` hiện tại, bao gồm principal, các authority và trạng thái xác thực. Thông tin đó gắn với thread đang xử lý, không tự động xuất hiện ở thread khác.

~~~text
HTTP request thread                     Worker thread của ExecutorService
-------------------                     --------------------------------
SecurityContextHolder                    SecurityContextHolder
  Authentication = Alice                   Authentication = null (thường gặp)
        |                                        ^
        +---- pool.submit(runnable) ------------+
                    [không tự mang ThreadLocal sang]
~~~

Một số thành phần cần phân biệt:

| Thành phần | Vai trò | Điều không tự bảo đảm |
| --- | --- | --- |
| `SecurityContextHolder` | Truy cập ngữ cảnh bảo mật ở thread hiện tại | Tự chuyển `Authentication` sang mọi thread trong executor |
| `SecurityContext` | Chứa `Authentication` của phiên xử lý | Là một snapshot bất biến |
| `Runnable` | Tác vụ không có kết quả trả về | Chạy trong ngữ cảnh của request tạo tác vụ |
| `Callable<V>` | Tác vụ có kết quả hoặc ném exception | Có authentication của caller |
| `DelegatingSecurityContextRunnable` | Chạy delegate trong một `SecurityContext` được chỉ định/nắm bắt | Tự cấp thêm quyền hoặc kiểm tra authorization |
| `DelegatingSecurityContextCallable<V>` | Tương tự với tác vụ trả kết quả | Tự quyết định khi nào principal hết quyền |

`Runnable` và `Callable` là các kiểu của Java concurrency. Các wrapper của Spring Security không thay thế `@PreAuthorize` hay authentication provider; chúng **đặt đúng ngữ cảnh để code chạy dưới danh tính đã chọn**.

~~~mermaid
sequenceDiagram
    participant HTTP as Request thread
    participant Pool as Executor / worker thread
    participant Task as Business task
    HTTP->>HTTP: Lấy SecurityContext của Alice
    HTTP->>Pool: Submit task được bọc context
    Pool->>Pool: Lưu context vốn có của worker
    Pool->>Pool: Thiết lập context của Alice
    Pool->>Task: run() / call()
    Task-->>Pool: Kết quả hoặc exception
    Pool->>Pool: Dọn/khôi phục context trong finally
    Pool-->>HTTP: Future hoàn thành
~~~

Điểm quan trọng nhất là **khôi phục trạng thái sau khi tác vụ kết thúc kể cả khi ném exception**. Worker thread có thể được dùng lại cho Bob ngay sau Alice. Nếu mã tự `setContext(aliceContext)` mà quên dọn, các tác vụ sau có nguy cơ nhìn thấy principal Alice.

## 2. Hai cách tạo wrapper: Runnable và Callable

Trong cơ chế `SecurityContextHolder` thông thường, Spring Security cung cấp hai kiểu:

~~~java
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.concurrent.DelegatingSecurityContextCallable;

SecurityContext selectedContext = SecurityContextHolder.getContext();

Runnable work = () -> auditCurrentUser();
Runnable securedWork =
    new DelegatingSecurityContextRunnable(work, selectedContext);

Callable<String> query = () ->
    SecurityContextHolder.getContext().getAuthentication().getName();

Callable<String> securedQuery =
    new DelegatingSecurityContextCallable<>(query, selectedContext);
~~~

Với `Runnable`, executor gọi `run()` và không có giá trị trả về; có thể quan sát trạng thái qua `AtomicReference`, latch hoặc mock. Với `Callable<V>`, executor gọi `call()` và `Future<V>` có thể chứa kết quả hoặc lỗi.

Lúc cần context rõ ràng, nên truyền tham số `SecurityContext` trực tiếp. Các overload chỉ nhận tác vụ có thể lấy context hiện tại theo thời điểm wrapper được tạo; đọc đúng Javadoc/phiên bản dùng trong dự án để không nhầm **thời điểm bắt context**. Khi bọc executor ở mục 4, cũng cần phân biệt context cố định với context lấy theo từng lần submit.

### Tạo một context riêng cho test

Để tránh phụ thuộc trạng thái đang nằm trong test thread, có thể tạo `SecurityContext` và authentication giả ngay trong fixture:

~~~java
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

static SecurityContext contextFor(String username, String authority) {
    SecurityContext context = SecurityContextHolder.createEmptyContext();
    context.setAuthentication(
        UsernamePasswordAuthenticationToken.authenticated(
            username,
            "N/A",
            List.of(new SimpleGrantedAuthority(authority))));
    return context;
}
~~~

`createEmptyContext()` giúp tạo object tách biệt với context đang gắn ở thread hiện tại. Giá trị `N/A` chỉ là placeholder trong test; không phải mật khẩu được hệ thống xác thực. Cần hiểu rằng `SecurityContext` và thậm chí `Authentication` có thể chứa state có thể thay đổi: wrapper giữ tham chiếu tới context đã truyền, **không phải cơ chế chụp bản sao bất biến**. Khi cần cách ly, tạo object mới cho mỗi luồng công việc và không sửa đồng thời một context đang được sử dụng.

## 3. JUnit: xác nhận Runnable truyền identity và dọn thread pool

Ví dụ test dưới đây không cần khởi động ứng dụng Spring. Nó dùng executor một worker để chứng minh cả **có identity trong delegate** lẫn **không còn identity sau khi delegate kết thúc**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;

class RunnableContextPropagationTest {

    @AfterEach
    void cleanTestThread() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void wrappedRunnableUsesAliceAndRestoresWorkerContext()
            throws Exception {
        SecurityContext alice = contextFor("alice", "ROLE_USER");
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            AtomicReference<String> observed = new AtomicReference<>();

            Runnable task = () -> {
                Authentication auth =
                    SecurityContextHolder.getContext().getAuthentication();
                observed.set(auth.getName());
            };

            Future<?> completed = pool.submit(
                new DelegatingSecurityContextRunnable(task, alice));
            completed.get(3, TimeUnit.SECONDS);

            assertThat(observed.get()).isEqualTo("alice");

            // Cùng worker thread, nhưng đã ra khỏi wrapper.
            Future<Authentication> after = pool.submit(() ->
                SecurityContextHolder.getContext().getAuthentication());
            assertThat(after.get(3, TimeUnit.SECONDS)).isNull();
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Đặt helper `contextFor(...)` từ mục 2 vào cùng test class hoặc một lớp fixture trong test source. Assertion thứ hai là đối chứng quan trọng: nếu wrapper không dọn đúng, worker vừa phục vụ Alice có thể để lại `Authentication`. Việc dùng `get(timeout, ...)` bảo đảm test không chờ vô hạn khi một tác vụ bị treo.

**Lưu ý:** test này đưa `SecurityContext` vào wrapper *bằng tham số*, không dựa vào `@WithMockUser`. Nó kiểm tra hợp đồng của wrapper ở môi trường Spring Security thông thường; không chứng minh authentication provider hoặc HTTP filter đã chạy.

### Cùng nguyên tắc với Callable có kết quả

~~~java
@Test
void callableReturnsTheIdentityFromItsOwnContext() throws Exception {
    SecurityContext bob = contextFor("bob", "ROLE_AUDITOR");
    ExecutorService pool = Executors.newSingleThreadExecutor();
    try {
        Callable<String> delegate = () ->
            SecurityContextHolder.getContext()
                .getAuthentication().getName();

        Callable<String> wrapped =
            new DelegatingSecurityContextCallable<>(delegate, bob);

        String result = pool.submit(wrapped).get(3, TimeUnit.SECONDS);
        assertThat(result).isEqualTo("bob");

        assertThat(pool.submit(() ->
                SecurityContextHolder.getContext().getAuthentication())
            .get(3, TimeUnit.SECONDS)).isNull();
    } finally {
        pool.shutdownNow();
    }
}
~~~

Trong test `Callable`, thêm import `java.util.concurrent.Callable` và các import từ ví dụ trước. Đổi principal Alice → Bob minh họa rằng wrapper thực hiện tác vụ với context được truyền cho nó, không phải một danh tính cố định gắn với thread pool. Thực tế nên có thêm test delegate ném exception để chứng minh dọn context vẫn xảy ra trong đường thất bại.

## 4. Bọc Executor thay vì bọc thủ công từng tác vụ

Khi ứng dụng gọi executor ở nhiều nơi, bọc từng `Runnable`/`Callable` dễ bị quên. Spring Security còn cung cấp các adapter như `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextExecutorService` và `DelegatingSecurityContextAsyncTaskExecutor`.

### Cơ chế lấy context tại thời điểm submit

~~~java
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;

ExecutorService rawPool = Executors.newSingleThreadExecutor();

// Không truyền SecurityContext cố định vào constructor:
Executor securedExecutor = new DelegatingSecurityContextExecutor(rawPool);

// Caller đang có SecurityContext của Alice:
SecurityContextHolder.setContext(contextFor("alice", "ROLE_USER"));
securedExecutor.execute(() -> auditCurrentUser());

// Một lần execute khác khi caller là Bob:
SecurityContextHolder.setContext(contextFor("bob", "ROLE_USER"));
securedExecutor.execute(() -> auditCurrentUser());

// Trong ứng dụng, cần quản lý lifecycle và shutdown rawPool;
// trong test thì dọn sau khi đã chờ tác vụ hoàn thành.
~~~

Với constructor không có tham số context, wrapper executor lấy context ở **thời điểm nộp công việc** (trên thread gọi `execute(...)`), rồi truyền nó cho worker. Nếu truyền một `SecurityContext` cụ thể vào constructor của executor, các tác vụ sẽ dùng **context cố định đó**; cách này chỉ phù hợp khi thực sự muốn tất cả chạy với một danh tính được lựa chọn sẵn.

Ví dụ như một job hệ thống được cho phép dùng danh tính service account có thể sử dụng context cố định, nhưng đó phải là quyết định bảo mật rõ ràng, không phải cách tránh lỗi “không có Authentication”. Với tác vụ của người dùng Alice/Bob, **lấy context tại mỗi lần submit** thường phù hợp hơn.

### ExecutorService và Future

Nếu ứng dụng cần `submit(...)` để nhận `Future`, dùng `DelegatingSecurityContextExecutorService` hoặc bọc `Callable` thủ công. Ví dụ:

~~~java
ExecutorService raw = Executors.newFixedThreadPool(2);
ExecutorService secured =
    new DelegatingSecurityContextExecutorService(raw);

SecurityContextHolder.setContext(contextFor("alice", "ROLE_USER"));
Future<String> alice = secured.submit(() ->
    SecurityContextHolder.getContext().getAuthentication().getName());

SecurityContextHolder.setContext(contextFor("bob", "ROLE_USER"));
Future<String> bob = secured.submit(() ->
    SecurityContextHolder.getContext().getAuthentication().getName());

assertThat(alice.get(3, TimeUnit.SECONDS)).isEqualTo("alice");
assertThat(bob.get(3, TimeUnit.SECONDS)).isEqualTo("bob");

secured.shutdown();
SecurityContextHolder.clearContext();
~~~

Đây là code minh họa; trong test thực, đặt các thao tác đợi và shutdown trong `try/finally` để chắc chắn dọn thread pool dù assertion lỗi. Khi nộp hai tác vụ với hai principal, điều cần xác nhận là **không bị trộn ngữ cảnh**. Không nên dùng một `SecurityContext` có thể thay đổi rồi gọi `setAuthentication(...)` cho Alice và Bob khi hai tác vụ đang chạy: đó vẫn là cùng một object được chia sẻ.

## 5. @Async: dùng DelegatingSecurityContextAsyncTaskExecutor

Trong một ứng dụng Spring, `@Async` thường nộp công việc qua `TaskExecutor` được chỉ định. Nếu service dùng `@Async` và cần biết principal của request đã tạo tác vụ, cấu hình một executor biết truyền SecurityContext:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;
import org.springframework.stereotype.Service;

@Configuration
@EnableAsync
class SecuredAsyncConfiguration {

    @Bean("rawAuditExecutor")
    ThreadPoolTaskExecutor rawAuditExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("audit-");
        pool.initialize();
        return pool;
    }

    @Bean("securityAwareAuditExecutor")
    AsyncTaskExecutor securityAwareAuditExecutor(
            @Qualifier("rawAuditExecutor") ThreadPoolTaskExecutor pool) {
        // Constructor này lấy context từ từng thread submit task,
        // không dùng một principal cố định cho tất cả request.
        return new DelegatingSecurityContextAsyncTaskExecutor(pool);
    }
}

@Service
class AsyncAuditService {

    @Async("securityAwareAuditExecutor")
    public CompletableFuture<String> principalThatSubmittedWork() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        if (auth == null) {
            return CompletableFuture.completedFuture("<anonymous>");
        }
        return CompletableFuture.completedFuture(auth.getName());
    }
}
~~~

Điều kiện để ví dụ làm việc như mong đợi:

1. `@EnableAsync` được kích hoạt.
2. `AsyncAuditService` là Spring bean và được gọi **qua Spring proxy**, không phải `new AsyncAuditService()` hay self-invocation trong cùng bean.
3. Phương thức `@Async` sử dụng đúng executor `securityAwareAuditExecutor`.
4. Tại thời điểm lời gọi được **nộp vào executor**, request/caller đang có `SecurityContext` tương ứng.
5. Mã nghiệp vụ không tự tách công việc sang một executor thứ hai không biết truyền context.

Ví dụ trả về `CompletableFuture.completedFuture(...)` từ thân phương thức là cách tương thích với proxy của `@Async`: chính proxy đảm nhận chạy phương thức trên executor, rồi trả một future cho caller. Nếu tự gọi `CompletableFuture.supplyAsync(...)` **trong** phương thức, tác vụ mới sẽ được chuyển sang một pool khác trừ khi truyền executor thích hợp; context của `@Async` không mặc nhiên theo qua pool mới.

### Kiểm thử @Async với @WithMockUser

~~~java
import static java.util.concurrent.TimeUnit.SECONDS;
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class AsyncAuditSecurityTest {
    @Autowired
    AsyncAuditService audit;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void asyncTaskSeesAliceFromSubmittingTestThread()
            throws Exception {
        String observed =
            audit.principalThatSubmittedWork().get(3, SECONDS);
        assertThat(observed).isEqualTo("alice");
    }

    @Test
    @WithMockUser(username = "bob", roles = "AUDITOR")
    void subsequentTaskSeesBobInsteadOfPreviousUser()
            throws Exception {
        String observed =
            audit.principalThatSubmittedWork().get(3, SECONDS);
        assertThat(observed).isEqualTo("bob");
    }
}
~~~

Test cần tải cả `SecuredAsyncConfiguration` và `AsyncAuditService` trong Spring context. Spring Security Test gắn `Authentication` giả lập vào test thread cho `@WithMockUser`; executor wrapper chuyển thông tin sang worker. Hai ca kiểm tra việc task nhận danh tính của người nộp công việc, nhưng không tự chứng minh HTTP authentication đã được gọi.

Không được dựa vào thứ tự hai test: JUnit có thể chạy khác thứ tự hoặc song song. Mỗi ca phải tự thiết lập identity. Để kiểm tra chống rò rỉ mạnh hơn, dùng **cùng worker thread** rồi chạy Alice → Bob → tác vụ không có authentication và assert cả ba kết quả. Khi đó dùng một fixture executor dành riêng cho test và điều phối rõ ràng qua `Future`/`CountDownLatch`, tránh phụ thuộc scheduler.

### CompletableFuture và executor tùy chọn

Một tác vụ chuyển ngữ cảnh không tự động qua `CompletableFuture.supplyAsync(...)` khi dùng common pool:

~~~java
// Common pool không tự lấy SecurityContextHolder của caller.
CompletableFuture<String> unsafeAssumption =
    CompletableFuture.supplyAsync(() ->
        SecurityContextHolder.getContext()
            .getAuthentication().getName());
~~~

Đoạn trên chỉ để chỉ ra **giả định sai**, không nên chạy nguyên trạng vì `getAuthentication()` có thể là `null` và ném `NullPointerException`.

Nếu muốn cung cấp executor truyền context cho `CompletableFuture`:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(2);
Executor secured = new DelegatingSecurityContextExecutor(pool);

// Caller có SecurityContext của người đã xác thực.
CompletableFuture<String> future =
    CompletableFuture.supplyAsync(() -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        return auth == null ? "<anonymous>" : auth.getName();
    }, secured);

// Chờ future ở test/application flow rồi shutdown pool theo lifecycle.
~~~

Phương thức `supplyAsync(Supplier, Executor)` chỉ yêu cầu `Executor`, nên `DelegatingSecurityContextExecutor` phù hợp. Với mã sử dụng `submit(...)` và `Future` trực tiếp, `DelegatingSecurityContextExecutorService` hoặc `DelegatingSecurityContextCallable` phù hợp hơn.

Không nên đưa `SecurityContext` của request người dùng vào một tác vụ phải chạy nhiều giờ hoặc sau khi phiên người dùng đã bị thu hồi mà không có policy riêng. Việc sao truyền context không tái xác minh quyền hay trạng thái session sau thời điểm giao việc. Với các job nền dài hạn, nên cân nhắc **service identity** rõ ràng hoặc giữ immutable user ID và xác minh lại quyền khi cần.

## 6. Servlet MVC async không đồng nghĩa với mọi executor tùy biến

Trong Spring MVC, controller có thể trả `Callable<T>` để request được xử lý bất đồng bộ. Khi Spring Security được tích hợp đúng, `WebAsyncManagerIntegrationFilter` hỗ trợ mang ngữ cảnh bảo mật vào xử lý `Callable` do Spring MVC quản lý.

Ví dụ controller:

~~~java
import java.util.concurrent.Callable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AsyncWhoAmIController {

    @GetMapping("/api/async/me")
    Callable<String> whoAmI() {
        return () -> {
            Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
            return auth == null ? "<anonymous>" : auth.getName();
        };
    }
}
~~~

Khi `MockMvc` đã có Spring Security filter chain:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@Test
void mvcCallableCanSeeItsRequestAuthentication() throws Exception {
    MvcResult pending = mockMvc.perform(get("/api/async/me")
            .with(user("alice")))
        .andExpect(request().asyncStarted())
        .andReturn();

    mockMvc.perform(asyncDispatch(pending))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));
}
~~~

Trong test trên, `MockMvc` cần cấu hình `springSecurity()` hoặc `@AutoConfigureMockMvc` trên một Spring Boot application đã kích hoạt Security. Các import còn thiếu gồm `org.springframework.test.web.servlet.MvcResult` và JUnit `@Test`. Test này kiểm tra **Spring MVC async Callable** được quản lý bởi cơ chế MVC và Security filter tương ứng.

Không suy luận rằng **mọi** công việc bất đồng bộ từ controller sẽ tự mang `SecurityContext`. Ví dụ controller tạo `DeferredResult` rồi tự gọi `executor.submit(...)` trên một pool tùy biến sẽ phụ thuộc vào cách pool được cấu hình. Trong trường hợp ấy, bọc `Runnable`/`Callable` hoặc executor là lựa chọn rõ ràng. Một `CompletableFuture` sử dụng common pool cũng không tự được bảo vệ chỉ vì nó được tạo trong request MVC.

### Phân biệt MockMvc asyncDispatch với test Runnable

| Cách kiểm thử | Phạm vi được kiểm chứng |
| --- | --- |
| `MockMvc.perform(...).andExpect(asyncStarted())` rồi `asyncDispatch` | Servlet async request, MVC integration và HTTP result |
| `new DelegatingSecurityContextRunnable(...)` + executor | Việc truyền context khi chạy `Runnable` bên ngoài pipeline HTTP |
| `new DelegatingSecurityContextCallable<>(...)` + `Future.get()` | Context và kết quả của `Callable` |
| `@Async` + `@WithMockUser` | Spring async proxy và executor được cấu hình trong test |

Một bài học tốt không gộp cả bốn vào cùng một test; mỗi test nên có mục tiêu và bằng chứng rõ ràng.

## 7. Reactive WebFlux: dùng Reactor Context thay vì ThreadLocal wrappers

`DelegatingSecurityContextRunnable` và `DelegatingSecurityContextCallable` được thiết kế cho những đoạn mã chạy theo `SecurityContextHolder`/thread. Trong ứng dụng WebFlux, security context thường được đưa qua **Reactor Context**, với API `ReactiveSecurityContextHolder`:

~~~java
Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}

Mono<String> forAlice =
    currentUser().contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(
            UsernamePasswordAuthenticationToken.authenticated(
                "alice", "N/A",
                List.of(new SimpleGrantedAuthority("ROLE_USER")))));

StepVerifier.create(forAlice)
    .expectNext("alice")
    .verifyComplete();
~~~

Ở đây, `contextWrite(...)` truyền Authentication dọc reactive subscription. Đó không phải là thao tác `SecurityContextHolder.setContext(...)` trên một thread. Các operator chuẩn của Reactor thường duy trì context theo subscription kể cả khi có `publishOn` hoặc `subscribeOn`, miễn là pipeline được nối đúng. Bọc một `Runnable` bằng API ThreadLocal rồi giả định context Reactor tự xuất hiện là sai hướng giải quyết.

Một endpoint WebFlux có thể trả tên principal từ Reactor Context:

~~~java
@RestController
class ReactiveWhoAmIController {

    @GetMapping("/api/reactive/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
~~~

Kiểm thử WebFlux với `WebTestClient` và `mockUser()`:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

@Test
void webFluxEndpointGetsAuthenticationFromReactorContext() {
    webTestClient.mutateWith(mockUser("alice"))
        .get()
        .uri("/api/reactive/me")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("alice");
}
~~~

Đoạn này giả định WebFlux security context được bật và `WebTestClient` tích hợp `spring-security-test`. `mockUser()` tạo principal giả lập để kiểm tra bảo vệ HTTP và truyền Reactor Context; nó không xác minh username/password hoặc JWT signature. Khi muốn kiểm tra Bearer JWT/OIDC thật, phải gửi token qua đúng filter/decoder hoặc luồng login tương ứng.

Nếu đoạn mã Reactive chuyển sang API imperative nằm ngoài Reactor, như một callback thư viện không phản ánh subscription context, cần một cầu nối được thiết kế có chủ đích. Không nên dùng `MODE_INHERITABLETHREADLOCAL` làm cách chữa chung cho mọi pipeline WebFlux.

## 8. Kiểm thử nhiều người dùng trên cùng worker thread

Một lỗi nghiêm trọng là Alice giao việc, worker giữ context Alice, rồi xử lý job của Bob và vô tình chạy dưới quyền Alice. Tác vụ đơn lẻ trả đúng principal chưa đủ chứng minh chống rò rỉ. Nên kiểm tra **nhiều lần submit tới cùng pool**:

~~~java
@Test
void executorUsesEachSubmittersContextAndLeavesNoStaleUser()
        throws Exception {
    ExecutorService raw = Executors.newSingleThreadExecutor();
    Executor secured = new DelegatingSecurityContextExecutor(raw);

    try {
        SecurityContextHolder.setContext(
            contextFor("alice", "ROLE_USER"));
        CompletableFuture<String> first = new CompletableFuture<>();
        secured.execute(() -> first.complete(
            SecurityContextHolder.getContext()
                .getAuthentication().getName()));

        SecurityContextHolder.setContext(
            contextFor("bob", "ROLE_USER"));
        CompletableFuture<String> second = new CompletableFuture<>();
        secured.execute(() -> second.complete(
            SecurityContextHolder.getContext()
                .getAuthentication().getName()));

        // Hai tác vụ trên cùng worker phải thấy hai principal riêng.
        assertThat(first.get(3, TimeUnit.SECONDS)).isEqualTo("alice");
        assertThat(second.get(3, TimeUnit.SECONDS)).isEqualTo("bob");

        // Bỏ wrapper: thread pool không được còn mang identity cũ.
        Future<Authentication> after = raw.submit(() ->
            SecurityContextHolder.getContext().getAuthentication());
        assertThat(after.get(3, TimeUnit.SECONDS)).isNull();
    } finally {
        SecurityContextHolder.clearContext();
        raw.shutdownNow();
    }
}
~~~

Test này cố tình dùng `Executors.newSingleThreadExecutor()` để bảo đảm cùng một worker phục vụ cả hai request giả lập. Nếu dùng pool nhiều thread rồi kiểm tra ngẫu nhiên, test có thể bỏ sót rò rỉ vì lần kiểm tra cuối tình cờ chạy trên thread chưa từng có authentication.

Một test quan trọng khác là **delegate ném exception**:

~~~java
@Test
void failingRunnableStillRestoresSecurityContext() throws Exception {
    ExecutorService raw = Executors.newSingleThreadExecutor();
    try {
        Runnable throwsError = () -> {
            assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getName()).isEqualTo("alice");
            throw new IllegalStateException("task failed");
        };

        Future<?> failed = raw.submit(
            new DelegatingSecurityContextRunnable(
                throwsError, contextFor("alice", "ROLE_USER")));

        assertThatThrownBy(() -> failed.get(3, TimeUnit.SECONDS))
            .isInstanceOf(ExecutionException.class)
            .hasCauseInstanceOf(IllegalStateException.class);

        Future<Authentication> after = raw.submit(() ->
            SecurityContextHolder.getContext().getAuthentication());
        assertThat(after.get(3, TimeUnit.SECONDS)).isNull();
    } finally {
        raw.shutdownNow();
    }
}
~~~

Đoạn này cần AssertJ `assertThatThrownBy` và import `java.util.concurrent.ExecutionException`, bên cạnh fixture `contextFor(...)`. Wrapper phải dọn/khôi phục context trong khối xử lý kể cả khi delegate thất bại; test cố tình kiểm tra chính đường lỗi thay vì chỉ đường thành công.

### Vì sao không bật MODE_INHERITABLETHREADLOCAL cho mọi thread?

`SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` có thể giúp một **thread con mới được tạo** kế thừa ngữ cảnh thread cha. Tuy nhiên:

- Thread pool tái sử dụng worker, nên worker có thể đã được tạo **trước** request Alice hoặc được tái sử dụng cho Bob.
- Thời điểm tạo worker không đồng nhất thời điểm submit từng task.
- Nếu không quản lý vòng đời chặt chẽ, một quyền đã kế thừa có thể tồn tại lâu hơn request.
- Cách này không mô hình hóa Reactor Context của WebFlux.

Vì vậy không nên dùng `MODE_INHERITABLETHREADLOCAL` như phương pháp truyền SecurityContext an toàn mặc định qua các executor tái sử dụng. Hãy dùng wrapper hoặc cơ chế propagation được thiết kế cho executor/framework tương ứng và kiểm thử chống rò rỉ.

## 9. Khi nào không nên truyền identity người dùng?

Truyền context giúp một tác vụ ngắn sử dụng quyền caller ở một thread khác. Nhưng không phải mọi xử lý nền đều nên chạy dưới danh tính người dùng:

| Loại công việc | Lựa chọn thường phù hợp |
| --- | --- |
| Truy vấn ngắn được giao trong lúc request đang sống | Capture context tại mỗi lần submit bằng wrapper/executor |
| `@Async` xử lý thao tác đại diện cho requester | `DelegatingSecurityContextAsyncTaskExecutor` và test mỗi caller |
| Job định kỳ chạy khi không có HTTP request | Danh tính service account/phạm vi quyền riêng, không giả định có context người dùng |
| Job dài hạn tồn tại sau logout, thu hồi tài khoản hoặc đổi quyền | Ghi lại thông tin cần thiết, xác minh lại policy tại lúc thực thi, tránh tin context cũ vô hạn |
| Reactive pipeline WebFlux | `ReactiveSecurityContextHolder` trong Reactor Context |
| Gọi API ngoài bằng access token của người dùng | Tách logic OAuth2 authorized client/token lifecycle; không suy ra token còn hợp lệ chỉ vì Authentication đã truyền |

`DelegatingSecurityContextRunnable` chỉ truyền **context**, không đánh giá token JWT/OIDC lại, không thực thi refresh token và không kiểm tra người dùng đã bị khóa/hết quyền sau khi job được đưa vào queue. Nếu nghiệp vụ cần quyền tại thời điểm thực thi, phải thiết kế bước đánh giá mới; nếu một job đã được phép “chốt quyền” lúc nhận yêu cầu, cần nêu rõ và giới hạn thời hạn đó.

Cũng không nên đưa nguyên `SecurityContext` hoặc JWT/refresh token nhạy cảm vào message queue, log, tracing baggage, hay tác vụ lưu bền mà không có chính sách bảo vệ. Trong môi trường phân tán, truyền một user ID/tác vụ được ký hoặc bằng chứng ủy quyền có hạn và **xác thực lại ở dịch vụ nhận** thường rõ ràng hơn việc cố sao chép object `SecurityContext` qua máy khác.

## 10. Ma trận kiểm thử và chẩn đoán lỗi

| Ca thử | Thiết lập | Kỳ vọng | Lớp được chứng minh |
| --- | --- | --- | --- |
| Task trần trên pool khác | Caller có Alice, nhưng dùng `rawPool.submit(...)` | Worker có thể không có authentication trong mô hình ThreadLocal mặc định | Phát hiện giả định sai khi đổi thread |
| Runnable được bọc | `DelegatingSecurityContextRunnable(task, aliceCtx)` | Delegate nhìn thấy Alice | Propagation với Runnable |
| Callable được bọc | `DelegatingSecurityContextCallable<>(task, bobCtx)` | Future trả Bob | Propagation với Callable |
| Dùng chung pool với hai caller | `DelegatingSecurityContextExecutor` không có context cố định | Alice → Bob đúng thứ tự identity | Capture theo lần submit |
| Sau task đã kết thúc | Gửi tác vụ không bọc tới cùng worker | Authentication không còn sót | Cleanup/restoration |
| Task ném exception | Delegate có lỗi khi đang ở context Alice | Future báo lỗi, worker đã dọn | Cleanup ở đường lỗi |
| `@Async` qua Spring proxy | `@WithMockUser("alice")` gọi bean có secured executor | Future trả Alice | AOP async + propagation |
| Self-invocation `@Async` | Phương thức cùng bean gọi nhau trực tiếp | Có thể không chạy qua proxy | Phát hiện sai phạm vi test |
| Spring MVC Callable | MockMvc `asyncStarted` + `asyncDispatch` | HTTP response phản ánh đúng Alice | Servlet async integration |
| WebFlux reactive chain | `WebTestClient.mutateWith(mockUser("alice"))` | Endpoint đọc Alice từ Reactor Context | Reactive context propagation |
| JWT/OIDC giả lập | `jwt()` hoặc `mockJwt()` | Có identity/authorities giả lập | Authorization, **không** xác minh token thật |

Một số dấu hiệu cần chẩn đoán:

**Worker thấy `null` dù test đã gắn `@WithMockUser`.** Có thể test chỉ gắn SecurityContext ở test thread, còn tác vụ chạy qua raw pool. Kiểm tra executor thực sự được sử dụng, không chỉ bean đã được khai báo trong context.

**Alice và Bob cùng thấy Alice.** Kiểm tra xem `DelegatingSecurityContextExecutor` có được xây bằng **một context cố định của Alice** hay không, hoặc một `SecurityContext` đã bị dùng chung/mutate. Test theo cùng worker thread sẽ giúp bắt lỗi.

**Thỉnh thoảng pass, thỉnh thoảng fail.** Có thể test chưa đợi `Future`, dùng `Thread.sleep(...)` để đoán tác vụ hoàn thành, hoặc kiểm tra một worker khác. Dùng `Future.get(timeout)`, `CountDownLatch` hay `StepVerifier` theo loại công việc.

**Task đã hết hạn vẫn có quyền cũ.** Context propagation không thực hiện kiểm tra revocation; thêm policy đánh giá lại ở thời điểm cần thiết.

**MockMvc Callable hoạt động nhưng `CompletableFuture.supplyAsync` không hoạt động.** Hai đường xử lý khác nhau: Spring MVC async Callable có integration bảo mật riêng, còn common pool không tự biết context của request.

**WebFlux có Authentication trong WebTestClient nhưng `SecurityContextHolder` trống.** Reactive context không phải ThreadLocal thông thường. Dùng `ReactiveSecurityContextHolder` trong pipeline và kiểm tra cách subscription được thực hiện.

## 11. Bài tập thực hành

1. Tạo `SecurityContext` cho Alice với `ROLE_USER` và cho Bob với `ROLE_AUDITOR`. Bọc một `Runnable` và một `Callable<String>`, chạy qua `ExecutorService`, dùng `Future.get(...)` chứng minh mỗi task nhìn thấy đúng principal.
2. Viết test chạy **hai task trên cùng worker**: Alice trước, Bob sau, rồi một task không bọc. Xác minh không có Authentication còn sót.
3. Cho `Callable` ném exception, kiểm tra `ExecutionException` và SecurityContext được dọn khi task kết thúc.
4. Thay `DelegatingSecurityContextExecutor(pool)` bằng constructor dùng `SecurityContext` cố định Alice. Gửi task từ Bob và giải thích vì sao Bob lại có thể chạy dưới Alice. Nêu trường hợp nào thực sự cần context cố định.
5. Tạo service `@Async` và `DelegatingSecurityContextAsyncTaskExecutor`. Dùng `@WithMockUser` trong hai test độc lập để kiểm tra Alice/Bob xuất hiện đúng trong future.
6. Cố ý dùng `CompletableFuture.supplyAsync(...)` với common pool. Quan sát authentication không được truyền trong thiết lập ThreadLocal, rồi cung cấp `DelegatingSecurityContextExecutor` làm tham số executor.
7. Dùng `MockMvc` kiểm thử Spring MVC controller trả `Callable<String>`, xác nhận `asyncStarted` và `asyncDispatch` trả danh tính theo request. Sau đó dùng `DeferredResult` với một executor tự quản lý và so sánh.
8. Dùng `WebTestClient` và `ReactiveSecurityContextHolder` kiểm tra principal trong một Reactive pipeline. Thêm `publishOn(...)` của Reactor và xác minh context vẫn được duy trì trong các operator chuẩn; phân biệt với ThreadLocal.
9. Mô phỏng user bị thu hồi quyền trong khi job còn nằm trong queue. Xây dựng policy yêu cầu kiểm tra lại quyền tại thời điểm chạy và viết test đảm bảo job không sử dụng quyền cũ.
10. Chọn một service thực tế trong dự án và trả lời: context được chụp **khi nào**, ai nắm executor, có cleanup sau exception không, task tồn tại bao lâu, và có thể chuyển identity giữa các principal không?

### Kết quả cần đạt

Người học cần phân biệt được **ngữ cảnh bảo mật ở request thread**, **ngữ cảnh được truyền tới worker thông qua `DelegatingSecurityContextRunnable`/`Callable` hoặc executor wrapper**, và **Reactor Context trong WebFlux**. Cốt lõi không chỉ là nhìn thấy tên người dùng đúng trong task, mà còn phải chứng minh **quyền không bị rò từ task này sang task khác**, xử lý cả trường hợp exception và biết khi nào nên xác thực/ủy quyền lại.

### Tài liệu tham khảo

- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Security — Servlet Async Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/async.html)
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [Spring Security — Reactive Security Context](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
