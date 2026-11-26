# Kiểm tra ngữ cảnh được khôi phục sau tác vụ thành công hoặc thất bại

Một bài kiểm thử bất đồng bộ có thể xác nhận rằng tác vụ nhìn thấy tên người dùng `alice`, nhưng vẫn bỏ sót một lỗi bảo mật nghiêm trọng: **sau khi tác vụ kết thúc, luồng trong thread pool vẫn giữ `SecurityContext` của Alice**. Tác vụ kế tiếp được chạy trên cùng worker thread có nguy cơ nhìn thấy danh tính cũ và thực hiện hành động dưới quyền không thuộc về nó.

Bài học thuộc chương **Bất đồng bộ và ngữ cảnh** trong module **SPRING_SECURITY_TESTING**. Mục tiêu là kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test`, với trọng tâm là **kiểm tra việc thiết lập và khôi phục `SecurityContext` ngay cả khi tác vụ ném exception**. Chúng ta sử dụng ví dụ xác định được thứ tự chạy trên Servlet/Java thread pool, sau đó liên hệ đến `@Async`, MockMvc, WebFlux, WebTestClient, JWT và OAuth2/OIDC.

## 1. Vì sao phải kiểm tra bước khôi phục?

Trong ứng dụng Servlet, `SecurityContextHolder` thường sử dụng chiến lược `MODE_THREADLOCAL`: `Authentication` nằm trong context gắn với thread hiện tại. Một request có thể được xác thực là Alice, nhưng nếu ứng dụng đẩy công việc sang executor, đó là **một thread khác**.

Hãy hình dung luồng thực thi:

```text
HTTP request thread                    Worker thread của thread pool
-------------------                    ----------------------------
SecurityContext = alice                SecurityContext = (trống hoặc trước đó)
   |
   +---- submit(tác vụ)  ------------> SecurityContext = alice  [được truyền có chủ đích]
                                             |
                                             +-- chạy business logic
                                             |
                                             +-- thành công HOẶC ném lỗi
                                             |
                                        KHÔI PHỤC SecurityContext trước đó
                                        (hoặc clear nếu trước đó trống)
```

**Khôi phục** không đồng nghĩa luôn gọi `clearContext()`. Khi wrapper bước vào worker thread, nó phải ghi nhớ context **đang có trên chính worker đó**. Kết thúc tác vụ, nó cần đặt lại context ban đầu; nếu ban đầu thread không có authentication thì phải trở về trạng thái không được xác thực. Điều này đúng cho cả đường thành công và đường ngoại lệ.

Một số câu hỏi cần kiểm thử riêng:

| Câu hỏi | Điều kiện kiểm tra |
| --- | --- |
| Tác vụ có nhìn thấy Authentication được truyền vào không? | Trong task, `getAuthentication().getName()` là `alice` |
| Tác vụ hoàn tất bình thường có làm bẩn worker không? | Sau task, worker lại mang context đã có **trước task** |
| Tác vụ ném exception có làm bẩn worker không? | Exception truyền tới caller, **đồng thời** context của worker được khôi phục |
| Worker ban đầu không có authentication thì sao? | Sau task, `getAuthentication()` vẫn `null` |
| Thread gửi công việc có bị thay đổi context không? | Caller vẫn giữ authentication trước khi submit |
| Tác vụ kế tiếp trên cùng worker có nhìn thấy Alice ngoài ý muốn không? | Không; nó chỉ nhìn thấy context riêng theo chính sách |

Nếu chỉ kiểm tra `Future.get()` trả một kết quả đúng, chưa có bằng chứng về việc **dọn ngữ cảnh**.

## 2. Ngữ cảnh được truyền như thế nào trong Spring Security?

`SecurityContextHolder.getContext()` trả về `SecurityContext` của thread hiện tại; thông thường context chứa một `Authentication`. Spring Security cung cấp các lớp để hỗ trợ chạy code với context có chủ đích:

- `DelegatingSecurityContextRunnable`: bọc `Runnable`, đặt context mục tiêu trước khi chạy delegate, rồi khôi phục context trước đó trong khối `finally`.
- `DelegatingSecurityContextCallable<V>`: cơ chế tương tự cho `Callable<V>`, cho phép trả kết quả hoặc ném exception.
- `DelegatingSecurityContextExecutor` và các executor wrapper khác: tự bọc task khi submit để tránh rải logic set/restore vào từng nơi.
- `DelegatingSecurityContextAsyncTaskExecutor`: wrapper dành cho `AsyncTaskExecutor`, phù hợp khi ứng dụng dùng `@Async` hoặc các cơ chế Spring Task.

Ví dụ minh họa khái niệm bên trong wrapper:

```java
// PSEUDOCODE giải thích, không phải bản sao source của Spring Security.
SecurityContext previousOnWorker = SecurityContextHolder.getContext();

try {
    SecurityContextHolder.setContext(contextForTask);
    delegate.run();
} finally {
    // Nếu previousOnWorker là context rỗng, implementation có thể clear.
    SecurityContextHolder.setContext(previousOnWorker);
}
```

`finally` là phần quyết định. Nếu delegate ném `IllegalStateException`, Java vẫn chạy `finally` để trả lại context. Đừng tự triển khai wrapper chỉ có `setContext()` rồi `run()` mà quên phần khôi phục.

### Không nhầm với chiến lược InheritableThreadLocal

`SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` có thể truyền context khi **tạo một thread con mới**, nhưng không giải quyết an toàn bài toán **thread pool tái sử dụng worker**. Thread được tạo trước khi request đến có thể không nhận được context; ngược lại thread nhận được context ở thời điểm tạo có thể giữ thông tin không phù hợp khi xử lý task của người dùng khác.

Không chuyển toàn ứng dụng sang `MODE_GLOBAL` hay `MODE_INHERITABLETHREADLOCAL` chỉ để test bất đồng bộ “xanh”. Hãy dùng một cơ chế truyền context rõ ràng và kiểm thử cleanup.

## 3. Tình huống đúng và sai khi worker được tái sử dụng

Giả sử một executor chỉ có **một worker**. Trước khi nhận công việc, worker đang có context `worker-original` (được thiết lập cố ý trong bài test để dễ nhận diện). Caller muốn chạy task với context `alice`.

Hành vi đúng:

```text
Worker trước task:       worker-original
Task đang chạy:          alice
Task kết thúc thành công: worker-original

Worker trước task:       worker-original
Task đang chạy:          alice
Task ném IllegalStateException:
                         worker-original
```

Hành vi sai:

```java
// PHẢN VÍ DỤ: không dùng cho production.
executor.submit(() -> {
    SecurityContextHolder.setContext(aliceContext);
    doWork(); // Có thể ném exception.
    // Không khôi phục context cũ.
});
```

Lỗi trên có thể không xuất hiện trong test đầu tiên vì tác vụ của Alice vẫn chạy đúng quyền. Nó lộ ra khi một task khác được thực thi trên **cùng worker** và đọc được Alice từ `SecurityContextHolder`.

Ta cần chứng minh cả hai: **context trong task** và **context trên worker sau task**, chứ không suy luận rằng wrapper chắc chắn sạch chỉ vì không có exception.

## 4. Ví dụ JUnit 5 kiểm tra đường thành công và đường thất bại

Ví dụ dưới đây sử dụng `DelegatingSecurityContextRunnable` và `Executors.newSingleThreadExecutor()`. Việc chỉ có một worker làm cho thứ tự kiểm tra đáng tin cậy: nếu `submit(...).get()` đã hoàn tất, lệnh `submit` tiếp theo được thực thi trên **đúng worker cũ**.

Dependency cho một dự án Spring Boot 3.x / Spring Security 6.x:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

Các ví dụ `SecurityContextHolder`, `@Async` và MockMvc dùng ứng dụng Servlet. Để chạy riêng ví dụ Reactive có `StepVerifier` ở mục 9, dùng module WebFlux tương ứng với `spring-boot-starter-webflux` và bổ sung `testImplementation("io.projectreactor:reactor-test")`; không cần chuyển toàn bộ ứng dụng MVC sang WebFlux chỉ để chạy bài test Reactor Context.

Dưới đây là lớp test JUnit 5 độc lập, có thể đặt tại `src/test/java`:

```java
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class SecurityContextRestorationTests {

    private ExecutorService worker;

    @BeforeEach
    void startWorker() {
        worker = Executors.newSingleThreadExecutor();
    }

    @AfterEach
    void cleanUp() throws Exception {
        try {
            // Xóa mọi context đã tạo cho worker trong bài test.
            worker.submit(SecurityContextHolder::clearContext)
                .get(2, TimeUnit.SECONDS);
        } finally {
            worker.shutdownNow();
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    void successfulTaskRestoresPreviousWorkerContext() throws Exception {
        SecurityContext original = contextFor("worker-original");
        SecurityContext alice = contextFor("alice");

        // Tạo một baseline CHỈ để kiểm tra restore, không phải cách
        // chuẩn để gán danh tính vào thread pool production.
        worker.submit(() -> SecurityContextHolder.setContext(original))
            .get(2, TimeUnit.SECONDS);

        AtomicReference<String> seenInside = new AtomicReference<>();

        Future<?> task = worker.submit(
            new DelegatingSecurityContextRunnable(
                () -> seenInside.set(currentPrincipalName()),
                alice));

        task.get(2, TimeUnit.SECONDS);

        assertThat(seenInside.get()).isEqualTo("alice");
        assertThat(currentNameOnWorker()).isEqualTo("worker-original");
    }

    @Test
    void failingTaskAlsoRestoresPreviousWorkerContext() throws Exception {
        SecurityContext original = contextFor("worker-original");
        SecurityContext alice = contextFor("alice");

        worker.submit(() -> SecurityContextHolder.setContext(original))
            .get(2, TimeUnit.SECONDS);

        AtomicReference<String> seenInside = new AtomicReference<>();

        Future<?> task = worker.submit(
            new DelegatingSecurityContextRunnable(() -> {
                seenInside.set(currentPrincipalName());
                throw new IllegalStateException("business failure");
            }, alice));

        assertThatThrownBy(() -> task.get(2, TimeUnit.SECONDS))
            .isInstanceOf(ExecutionException.class)
            .hasCauseInstanceOf(IllegalStateException.class);

        assertThat(seenInside.get()).isEqualTo("alice");
        // Ném exception KHÔNG được để lại Alice trên worker.
        assertThat(currentNameOnWorker()).isEqualTo("worker-original");
    }

    @Test
    void emptyWorkerContextRemainsUnauthenticatedAfterTask()
            throws Exception {

        worker.submit(SecurityContextHolder::clearContext)
            .get(2, TimeUnit.SECONDS);

        Future<?> task = worker.submit(
            new DelegatingSecurityContextRunnable(() -> {
                assertThat(currentPrincipalName()).isEqualTo("alice");
            }, contextFor("alice")));

        task.get(2, TimeUnit.SECONDS);

        // Context có thể được tạo rỗng khi gọi getContext();
        // cần kiểm tra Authentication, không so context với null.
        assertThat(currentNameOnWorker()).isEqualTo("<anonymous>");
    }

    @Test
    void submittingThreadIsNotReplacedByWorkerContext()
            throws Exception {

        SecurityContextHolder.setContext(contextFor("caller"));
        SecurityContext alice = contextFor("alice");

        Future<?> task = worker.submit(
            new DelegatingSecurityContextRunnable(() -> {
                assertThat(currentPrincipalName()).isEqualTo("alice");
            }, alice));

        task.get(2, TimeUnit.SECONDS);

        assertThat(currentPrincipalName()).isEqualTo("caller");
        assertThat(currentNameOnWorker()).isEqualTo("<anonymous>");
    }

    private String currentNameOnWorker() throws Exception {
        return worker.submit(
            SecurityContextRestorationTests::currentPrincipalName)
            .get(2, TimeUnit.SECONDS);
    }

    private static String currentPrincipalName() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        return authentication == null
            ? "<anonymous>"
            : authentication.getName();
    }

    private static SecurityContext contextFor(String name) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();

        context.setAuthentication(new UsernamePasswordAuthenticationToken(
            name,
            "N/A",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));

        return context;
    }
}
```

### Những gì bốn bài test chứng minh

| Test | Trong task | Sau task trên worker | Điều đã kiểm chứng |
| --- | --- | --- | --- |
| `successfulTaskRestoresPreviousWorkerContext` | Alice | `worker-original` | Khôi phục sau **thành công** |
| `failingTaskAlsoRestoresPreviousWorkerContext` | Alice, sau đó ném lỗi | `worker-original` | Khôi phục trong nhánh **exception** |
| `emptyWorkerContextRemainsUnauthenticatedAfterTask` | Alice | Không có Authentication | Cleanup khi worker ban đầu trống |
| `submittingThreadIsNotReplacedByWorkerContext` | Alice | Trống; caller vẫn là `caller` | Không làm biến đổi nhầm context của caller |

Trong bài test thất bại, `Future.get()` ném `ExecutionException` bọc `IllegalStateException` do delegate sinh ra. Assertion chỉ kiểm tra exception **chưa đủ**: dòng đọc lại worker sau đó là bằng chứng ngữ cảnh được khôi phục.

**Chủ đích sử dụng `worker-original`:** đây là context nhân tạo để phát hiện việc wrapper chỉ gọi `clearContext()` thay vì trả lại trạng thái có trước. Ứng dụng thật không nên duy trì authentication tùy tiện trên worker của thread pool.

## 5. Không để bài test tự gây rò rỉ SecurityContext

Kiểm thử context là một phần của hệ thống đang chia sẻ thread trong tiến trình test. Nếu fixture tạo context mà không cleanup, test chạy sau có thể sai dù implementation production đúng.

Trong ví dụ JUnit, `@AfterEach` thực hiện hai việc tách biệt:

1. Gửi tác vụ `SecurityContextHolder.clearContext()` vào **worker thread** trước khi shutdown, để không giữ context ở đó.
2. Gọi `SecurityContextHolder.clearContext()` trên **JUnit test thread** vì `SecurityContextHolder` dùng ThreadLocal.

Một lời gọi `SecurityContextHolder.clearContext()` trong test thread **không xóa được** context của worker thread khác. Đây là nguyên nhân phổ biến khiến một test tưởng đã cleanup nhưng vẫn làm bẩn thread pool.

Nếu test dùng `@WithMockUser`, `WithSecurityContextTestExecutionListener` sẽ thiết lập và dọn context theo vòng đời phương thức test. Nhưng cơ chế đó **không mặc định làm sạch các worker thread do ứng dụng tự tạo**. Khi test tự `setContext()` ở thread khác, cần có cleanup tương ứng.

Không dùng `Thread.sleep(500)` để đoán tác vụ đã kết thúc. `Future.get(timeout)`, `CountDownLatch` hoặc cơ chế synchronization rõ ràng ổn định hơn và tránh kết quả ngẫu nhiên trên CI.

### Truyền tham chiếu chứ không tự động deep-copy

`DelegatingSecurityContextRunnable` nhận một đối tượng `SecurityContext`. Đây không phải một phép “snapshot bất biến” tự động: nếu nhiều thread cùng sửa `Authentication` hoặc chính context được chia sẻ, có nguy cơ race và thay đổi ngoài dự kiến.

Khi xây dựng một context test độc lập, ví dụ sử dụng `SecurityContextHolder.createEmptyContext()` rồi đặt Authentication vào context đó. Trong ứng dụng thật, tránh sửa context đã chia sẻ sau khi submit task. Nếu cần snapshot quyền tại thời điểm submit, thiết kế dữ liệu bất biến, tách biệt quyền cần dùng và xác thực lại khi cần; không mặc định việc copy tham chiếu mang lại cách ly.

## 6. Chọn executor wrapper cho @Async

Trong một service Spring, việc bọc từng `Runnable` bằng tay không phải lúc nào cũng thuận tiện. Có thể cấu hình executor được trang trí bằng `DelegatingSecurityContextAsyncTaskExecutor`:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;
import org.springframework.stereotype.Service;

@Configuration
@EnableAsync
class ApplicationAsyncConfig {

    @Bean("rawExecutor")
    ThreadPoolTaskExecutor rawExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("secured-work-");
        executor.initialize();
        return executor;
    }

    @Bean("securedExecutor")
    AsyncTaskExecutor securedExecutor(
            @Qualifier("rawExecutor") ThreadPoolTaskExecutor delegate) {
        // Không truyền context cố định: lấy SecurityContext của
        // thread submit task theo cơ chế wrapper.
        return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
    }
}

@Service
class ReportService {

    @Async("securedExecutor")
    public CompletableFuture<String> currentUser() {
        String username = SecurityContextHolder.getContext()
            .getAuthentication().getName();

        return CompletableFuture.completedFuture(username);
    }
}
```

Với thiết lập này, các tác vụ được submit qua `securedExecutor` mang context phù hợp với thread submit và được wrapper khôi phục sau khi chạy. Khi ứng dụng dùng `@Async`, phải gọi phương thức qua **Spring proxy**; việc một method trong cùng bean tự gọi method `@Async` của nó thường không kích hoạt interceptor bất đồng bộ.

Một bài kiểm thử tích hợp có thể dùng `@WithMockUser(username = "alice")`:

```java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ReportServiceIntegrationTests {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(username = "alice")
    void asyncServiceSeesSubmittedPrincipal() throws Exception {
        assertThat(reportService.currentUser()
                .get(2, TimeUnit.SECONDS))
            .isEqualTo("alice");
    }
}
```

**Giới hạn:** test trên chỉ chứng minh `ReportService` thấy Alice. Muốn khẳng định **worker khôi phục context sau task thành công và thất bại**, cần kiểm tra ngữ cảnh trên worker sau khi tác vụ được xử lý như mục 4, hoặc instrument/decorate executor được sử dụng trong test. Đừng gộp hai khẳng định thành một chỉ vì `@WithMockUser` hoạt động.

### Context cố định và context của người gọi

Một số constructor của executor wrapper nhận một `SecurityContext` **cố định**. Điều đó phù hợp với một số tác vụ nền chạy dưới danh tính kỹ thuật đã thiết kế, nhưng rất nguy hiểm nếu dùng nhầm cho tác vụ thay mặt nhiều người dùng: mọi task có thể nhận cùng một danh tính.

Với workload theo request, thường dùng wrapper lấy context ở **thời điểm submit**. Luôn kiểm thử rằng task của Bob không nhìn thấy Authentication của Alice sau khi các task được chạy nối tiếp trên thread pool.

## 7. Spring MVC bất đồng bộ: Callable và MockMvc

Spring Security trên Servlet có tích hợp với cơ chế async `Callable` của Spring MVC thông qua `WebAsyncManagerIntegrationFilter`. Khi xử lý một request MVC có `Callable`, context của request được liên kết để đoạn callable có thể nhìn thấy Authentication thích hợp. Đây không có nghĩa mọi nguồn bất đồng bộ tự tạo đều được truyền context giống nhau; `DeferredResult` hoặc `CompletableFuture.supplyAsync(...)` trên executor tùy ý cần được đánh giá riêng.

Controller minh họa:

```java
import java.util.concurrent.Callable;

import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AsyncIdentityController {

    @GetMapping("/async/identity")
    Callable<String> identity() {
        return () -> SecurityContextHolder.getContext()
            .getAuthentication().getName();
    }
}
```

Nếu SecurityFilterChain cho phép request của người dùng đã đăng nhập vào `/async/identity`, ta kiểm tra bằng MockMvc và `asyncDispatch`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncIdentityMvcTests {

    @Autowired
    MockMvc mvc;

    @Test
    void securityContextIsAvailableInAsyncCallable()
            throws Exception {

        MvcResult pending = mvc.perform(get("/async/identity")
                .with(user("alice")))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }
}
```

`user("alice")` là helper của **spring-security-test**: nó giả lập người dùng cho request của MockMvc chứ không kiểm chứng login HTTP thật. `asyncDispatch(pending)` là bước quan trọng để xử lý kết quả MVC async và assert phản hồi cuối.

Test MVC này xác minh việc **propagation cho Callable** trong một request. Nó chưa chứng minh cleanup worker thread sau mọi ngoại lệ; các test thread pool ở mục 4 là lớp kiểm chứng bổ sung. Nếu ứng dụng có endpoint async thất bại, hãy test cả exception handler và sự vắng mặt của authentication cũ trên request hoặc task tiếp theo.

## 8. Vì sao CompletableFuture.supplyAsync không mặc nhiên an toàn?

Đoạn code:

```java
CompletableFuture<String> future = CompletableFuture.supplyAsync(
    () -> SecurityContextHolder.getContext()
        .getAuthentication().getName());
```

mặc định thường chạy trên `ForkJoinPool.commonPool()` và không tự sao chép `SecurityContext` của request thread. Với `MODE_THREADLOCAL`, `getAuthentication()` trên worker có thể là `null`. Việc dùng `MODE_INHERITABLETHREADLOCAL` cho toàn JVM để sửa tình trạng này không bảo đảm thread pool được truyền/khôi phục đúng.

Nếu bắt buộc dùng một `Executor` cho `CompletableFuture`, hãy truyền một executor đã được tích hợp propagation đúng và kiểm tra cleanup:

```java
CompletableFuture<String> future = CompletableFuture.supplyAsync(
    () -> SecurityContextHolder.getContext()
        .getAuthentication().getName(),
    securedExecutor);
```

Ở đây `securedExecutor` là executor đã được bọc bằng cơ chế `DelegatingSecurityContext...` và được tiêm từ cấu hình ứng dụng. Nếu `CompletableFuture` có nhiều stage async, hãy xem stage nào chạy trên executor nào; context không tự nhiên đi theo **mọi nhánh** nếu các stage lại chuyển sang executor không được trang trí.

Đừng suy luận rằng `SecurityContext` được khôi phục khi một task đã trả kết quả thành công mà quên nhánh `exceptionally`, `handle` hoặc stage bị hủy; kiểm thử cần bao phủ đúng chỗ thực thi work và chính sách cleanup của executor.

## 9. Reactive là một mô hình khác: Reactor Context

Trên Spring WebFlux, không nên dựa vào `SecurityContextHolder` ThreadLocal để tìm Authentication ở các toán tử Reactive. Một luồng `Mono`/`Flux` có thể chuyển thread với `publishOn()`, `subscribeOn()` mà vẫn thuộc cùng một subscription.

Spring Security Reactive dùng `ReactiveSecurityContextHolder` và **Reactor Context**. “Khôi phục” trong mô hình này chủ yếu có nghĩa **ngữ cảnh của một subscriber không rò sang subscriber khác**, kể cả khi một nhánh hoàn thành với lỗi, thay vì đặt lại ThreadLocal ở cuối mỗi `Runnable`.

Ví dụ test bằng `reactor-test` và `StepVerifier`:

```java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveSecurityContextIsolationTests {

    private static Authentication auth(String name) {
        return new UsernamePasswordAuthenticationToken(
            name, "N/A",
            List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private static Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .defaultIfEmpty("<anonymous>");
    }

    @Test
    void successAndErrorDoNotLeakBetweenSubscribers() {
        StepVerifier.create(currentUser().contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    auth("alice"))))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(
                currentUser()
                    .flatMap(name -> Mono.<String>error(
                        new IllegalStateException("failed for " + name)))
                    .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                            auth("bob"))))
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && error.getMessage().equals("failed for bob"))
            .verify();

        StepVerifier.create(currentUser())
            .expectNext("<anonymous>")
            .verifyComplete();
    }
}
```

Ở đây mỗi lần `StepVerifier.create(...)` tạo một **subscription riêng**. Alice, Bob và subscriber không có authentication không chia sẻ SecurityContext chỉ vì một nhánh trước đã thành công hoặc thất bại. `contextWrite` cung cấp ngữ cảnh theo phạm vi của chuỗi reactive đã định.

Với `WebTestClient`, có thể dùng `mockUser("alice")`, `mockJwt()`, `mockOAuth2Login()`, `mockOidcLogin()` để thử phân quyền trong mock server WebFlux đã áp dụng `springSecurity()`. Các helper đó không làm biến một JWT giả thành bearer token thật gửi đến server ngoài tiến trình. Muốn kiểm thử xác thực JWT/OAuth2/OIDC thực sự, cần dùng credentials hợp lệ qua HTTP và decoder/provider thích hợp.

## 10. Phân biệt rò rỉ context với lỗi nghiệp vụ

Một tác vụ có thể ném exception vì database, network hoặc validation, không phải vì Spring Security. Test **không nên nuốt exception** chỉ để chờ context được dọn:

```text
Task của Alice bắt đầu
   |
   +-- gọi service -> lỗi
   |
   +-- Future/CompletionStage báo thất bại
   |
   +-- worker context được khôi phục
   |
   +-- task của Bob bắt đầu và chỉ thấy Bob
```

Hai điều có thể cùng đúng:

1. Tác vụ thất bại và caller nhận được exception theo contract của API.
2. Worker thread không giữ authentication của task vừa thất bại.

Một test chỉ `assertThrows(IllegalStateException.class, ...)` không đủ. Tương tự, một test chỉ kiểm tra context sau khi `run()` trực tiếp trên **test thread** không chứng minh được behavior ở worker thật. Cần chạy wrapper trên executor và kiểm tra task được submit **sau đó trên cùng worker**, như mục 4.

### Ma trận ca kiểm thử đề xuất

| Tình huống | Trong task | Trạng thái sau task | Điều nên assert |
| --- | --- | --- | --- |
| Task thành công, worker ban đầu trống | Alice | Không authentication | Alice trong task, `null` sau |
| Task thành công, worker có context cũ | Alice | Context cũ | Khôi phục thay vì xóa tùy tiện |
| Task ném runtime exception | Alice, lỗi | Context cũ hoặc trống như ban đầu | `Future.get` báo lỗi **và** context được khôi phục |
| Task của Bob chạy sau Alice | Bob | Trạng thái trước task của Bob | Không rò danh tính Alice |
| Không có propagation wrapper | Không bảo đảm có Alice | Theo executor | Test có thể phát hiện thiếu context; không giả định kế thừa tự động |
| MVC `Callable` qua MockMvc | Principal giả của request | Phản hồi async đúng | `asyncStarted()` rồi `asyncDispatch()` |
| Reactive stream lỗi rồi subscriber mới | Context riêng từng subscription | Không chia sẻ context | `StepVerifier` không thấy danh tính cũ |

## 11. Các sai lầm phổ biến

### Chỉ kiểm tra nội dung task, không kiểm tra worker sau task

`assertThat(seenInside).isEqualTo("alice")` chứng minh propagation, không chứng minh restoration. Hãy submit một tác vụ đọc context mới sau khi future đã kết thúc.

### Đọc lại context trên test thread thay vì worker thread

`SecurityContextHolder.getContext()` trên JUnit thread không nói gì về ThreadLocal của worker. Dùng `executor.submit(() -> SecurityContextHolder.getContext()...)` với cùng executor; test có một worker giúp tránh đo nhầm thread.

### Dùng sleep để chờ tác vụ

`Thread.sleep` làm test phụ thuộc tốc độ CPU/CI, dễ race. `Future.get(timeout)` hoặc latch giúp xác định rõ task đã hoàn tất trước khi kiểm tra.

### Coi `@WithMockUser` tự động truyền sang mọi executor

Annotation tạo Authentication trong vòng đời test được Spring Security Test quản lý, nhưng không bảo đảm một `CompletableFuture.supplyAsync()` trên common pool sẽ nhìn thấy cùng context. Chọn executor đã được bọc phù hợp.

### Xem exception là lý do có thể bỏ cleanup

Đường lỗi thường là nơi rò context dễ xảy ra nhất. Luôn kiểm tra cleanup trong nhánh lỗi; wrapper dựa vào `finally` để khôi phục.

### Đặt SecurityContext cố định cho mọi request bất đồng bộ

Một wrapper được khởi tạo với context quyền cao cố định có thể vô tình chạy mọi task dưới danh tính đó. Khi tác vụ phụ thuộc request, truyền context đúng của caller tại thời điểm submit và kiểm thử thay đổi principal giữa Alice/Bob.

### Dùng ThreadLocal trong WebFlux

`ReactiveSecurityContextHolder` làm việc với Reactor Context. Truy cập `SecurityContextHolder` ThreadLocal từ `publishOn` có thể nhận `null` hoặc danh tính không phù hợp. Dùng API reactive và kiểm thử nhiều subscription.

## 12. Bài tập thực hành

1. Chạy `successfulTaskRestoresPreviousWorkerContext` và `failingTaskAlsoRestoresPreviousWorkerContext`. Giải thích vì sao cùng một worker phải nhìn thấy `worker-original` sau cả hai.
2. Viết một `Runnable` sai chỉ gọi `setContext(alice)` rồi `run()`, không có `finally`. Dùng test theo mục 4 chứng minh `worker-original` bị thay thế bởi Alice sau task.
3. Bổ sung ca worker ban đầu trống nhưng delegate ném lỗi. Assert `Future.get()` thất bại và `getAuthentication()` trên worker vẫn là `null`.
4. Cho task của Alice rồi task của Bob chạy trên một pool một worker, mỗi task có wrapper truyền context riêng. Assert mỗi task thấy đúng principal và sau cùng pool không giữ danh tính nào.
5. Dùng `@WithMockUser(username="alice")` gọi `ReportService.currentUser()` qua proxy Spring. Sau đó thay bằng `CompletableFuture.supplyAsync()` không chỉ định executor và giải thích vì sao kết quả không còn được bảo đảm.
6. Viết endpoint Spring MVC trả `Callable<String>` rồi dùng MockMvc `request().asyncStarted()` và `asyncDispatch()` để xác minh principal được truyền vào callable.
7. Viết một Reactive test với Bob được gắn `ReactiveSecurityContextHolder.withAuthentication(...)` rồi ném `IllegalStateException`; xác minh subscriber tiếp theo không tự mang danh tính Bob.
8. Thiết kế test bảo mật cho async service xử lý JWT hoặc OAuth2 principal: phân biệt kiểm tra authority từ Authentication đã được mock với việc xác minh JWT signature/issuer hay OAuth2 login thực.

## 13. Ghi nhớ

- **Propagation và restoration là hai yêu cầu độc lập.** Task thấy Alice chưa có nghĩa worker được dọn sau task.
- **Context cần được khôi phục cả khi thành công lẫn khi ném exception.** Kết hợp assertion trong task, `Future.get` và một task kiểm tra tiếp theo trên **cùng worker**.
- **`DelegatingSecurityContextRunnable` và executor wrappers của Spring Security xử lý set/restore context** để tránh tự viết logic ThreadLocal thiếu `finally`.
- **Đừng nhầm context caller với context worker.** Dọn context trong test thread không thể thay thế việc cleanup trên worker thread.
- **`@WithMockUser` và MockMvc giúp kiểm thử danh tính giả lập**, nhưng không tự biến mọi executor thành executor truyền SecurityContext.
- **Reactive sử dụng Reactor Context thay cho ThreadLocal**. Với WebTestClient và WebFlux, kiểm thử cô lập từng subscriber và đường lỗi theo mô hình Reactor.
- **Không nới lỏng xác thực HTTP để làm test xanh.** Khi cần JWT/OAuth2/OIDC thật, kiểm tra token và filter chain qua request HTTP tương ứng.

Trong **SPRING_SECURITY_TESTING**, câu hỏi quyết định không chỉ là **“Tác vụ đã nhận đúng SecurityContext chưa?”** mà còn là **“Sau mọi con đường kết thúc, SecurityContext của thread hoặc subscription tiếp theo có vẫn đúng phạm vi của chính nó không?”**. Một bài test bao phủ cả hai câu hỏi mới có giá trị bảo vệ hệ thống bất đồng bộ.

