# Kiểm tra mất ngữ cảnh khi chuyển luồng hoặc dùng reactive sai cách

## 1. Hiện tượng: đã đăng nhập nhưng tác vụ khác không thấy người dùng

Trong ứng dụng Spring Security, một lỗi khó chẩn đoán là **request HTTP ban đầu đã xác thực thành công** nhưng một đoạn xử lý bất đồng bộ lại thấy `Authentication == null`, tên người dùng `anonymousUser`, thiếu role hoặc trả 401/403 dù trước đó cùng request đã có danh tính.

Tình huống thường gặp:

- Controller Servlet đọc `SecurityContextHolder.getContext().getAuthentication()` và thấy Alice; bên trong `CompletableFuture.supplyAsync(...)` hoặc `@Async` lại thấy null.
- Worker chạy bằng `ExecutorService` đôi khi thấy ngữ cảnh của **request trước**, không phải request hiện tại. Đây có thể là **rò rỉ danh tính giữa người dùng**, nghiêm trọng hơn việc mất ngữ cảnh.
- Ứng dụng Spring WebFlux đọc `SecurityContextHolder` của Servlet ở trong `Mono.map(...)`, `Flux.flatMap(...)` hoặc sau `publishOn(...)` và thấy null/giá trị không ổn định.
- Một nhánh reactive được gọi bằng `subscribe()` riêng hoặc chuyển sang `Future`/callback ngoài pipeline, làm phần công việc đó không còn dùng đúng subscriber context.
- Kiểm thử dùng `mockUser()` thành công ở tầng HTTP nhưng công việc nền không nhận cùng danh tính, hoặc test chỉ chạy trên một thread nên che khuất lỗi thực tế.
- Log hiển thị thread khác nhưng không cho biết đó có phải một lỗi hay không.

**Quan trọng: đổi thread không tự động đồng nghĩa mất ngữ cảnh trong Reactor.** Đây là sự khác biệt giữa hai mô hình:

| Mô hình | Nơi Spring Security lưu ngữ cảnh trong trường hợp thông thường | Điều phải bảo đảm |
| --- | --- | --- |
| Servlet/MVC, xử lý đồng bộ | `SecurityContextHolder`, thường dựa trên `ThreadLocal` | Truyền ngữ cảnh có kiểm soát khi tự đưa tác vụ sang thread/executor mới |
| Servlet/MVC, xử lý bất đồng bộ | Có tích hợp sẵn cho **một số** đường Servlet/MVC async; tác vụ tự tạo vẫn cần kiểm tra | Không giả định mọi `CompletableFuture`, `new Thread`, `@Async`, thư viện callback đều được tự động truyền |
| Spring WebFlux/Reactor | `ReactiveSecurityContextHolder` sử dụng **Reactor Context** gắn với subscriber | Giữ công việc trong pipeline, không phụ thuộc `ThreadLocal` của Servlet |
| Tác vụ nền tách khỏi request | Có thể **không có danh tính HTTP hiện tại** | Truyền metadata actor/ủy quyền rõ ràng, xác thực lại theo quy trình nghiệp vụ khi cần |

Mục tiêu của bài là **đọc đúng triệu chứng, tái hiện lỗi có kiểm soát, phân biệt stack Servlet và reactive, rồi sửa tại điểm làm đứt ngữ cảnh** — không vá bằng cách cấp quyền mặc định hoặc làm giả danh tính.

## 2. Ba thứ hay bị gọi chung là "context"

Cần tách rõ ba loại để đọc log và sửa đúng chỗ:

1. **SecurityContext**: chứa `Authentication` (principal, authorities và trạng thái xác thực). Trong Servlet, `SecurityContextHolder` mặc định dùng chiến lược dựa vào `ThreadLocal`.
2. **Reactor Context**: cấu trúc dữ liệu gắn với **subscriber** và được truyền qua giao thức subscription của `Mono`/`Flux`. Spring Security reactive sử dụng nó để đưa `SecurityContext` tới phần còn lại của pipeline.
3. **Logging/trace context**: ví dụ MDC của SLF4J, request ID, trace ID. Đây là **ngữ cảnh quan sát**, không phải chứng cứ xác thực hay cấp quyền. Một request có trace ID đúng nhưng `Authentication` sai vẫn là lỗi bảo mật.

`ThreadLocal` gắn với **thread**; Reactor Context gắn với **subscription**. Reactor có thể chạy trên nhiều thread và cùng một thread có thể xử lý nhiều subscriber khác nhau. Vì vậy phép đo "thread hiện tại khác thread ban đầu" **không chứng minh** rằng Reactor Context đã mất.

Sơ đồ so sánh:

```text
Servlet request:
  thread-http-1
    SecurityContextHolder --> alice
       |
       +--> rawExecutor.submit(task)
                worker-2
                SecurityContextHolder --> thường trống
                (hoặc tệ hơn: bị rò context nếu code tự set mà quên clear)
       |
       +--> DelegatingSecurityContextExecutor.submit(task)
                worker-3
                context được thiết lập khi thực hiện task
                rồi cleanup sau khi chạy

WebFlux request:
  subscriber của request A
    Reactor Context --> Authentication(alice)
       |
       +--> Mono.publishOn(otherScheduler)
                thread khác, cùng subscription
                ReactiveSecurityContextHolder --> alice
       |
       +--> tự tạo subscription/job/callback độc lập
                KHÔNG mặc định có cùng Context
```

Cả hai mô hình đều không nên đọc `userId` từ header/query/body do client tự khai rồi coi đó là danh tính thay thế.

## 3. Nhận diện lỗi qua log và status

Một triệu chứng có thể xuất hiện dưới nhiều hình thức:

| Triệu chứng | Chẩn đoán ban đầu hợp lý | Chưa được vội kết luận |
| --- | --- | --- |
| Trước `supplyAsync` thấy Alice, trong task thấy null | ThreadLocal không tự đi sang worker | Không kết luận người dùng chưa login hoặc password sai |
| Trong task thấy một người dùng khác | Có thể có context leak do giữ ThreadLocal/Authentication sai | Không coi là dữ liệu "ngẫu nhiên" vô hại |
| WebFlux sau `publishOn` đọc `SecurityContextHolder` thấy null | Đang đọc **sai API cho reactive** | Không kết luận `publishOn` tự làm mất Reactor Context |
| `ReactiveSecurityContextHolder.getContext()` rỗng | Chưa có subscriber context, nhánh bị tách, hoặc request không được xác thực | Không suy ra ngay thread switch làm mất context |
| `@PreAuthorize` trong service từ chối sau `@Async` | Kiểm tra task executor, lời gọi qua proxy, thời điểm capture | Không vô hiệu hóa method security để "sửa" |
| Login hợp lệ, HTTP 403 trong POST | Có thể là CSRF hoặc authorization, không nhất thiết context | Cần phân biệt filter từ chối và lỗi propagation |
| Unit test pass, production fail dưới tải | Test thiếu concurrency hoặc code giữ context quá lâu | Không dùng `Thread.sleep(...)` làm biện pháp sửa chính |

Một quy trình debug tốt **không log token, password hay serialized Authentication**. Chỉ cần các dấu hiệu không nhạy cảm: request ID, endpoint chuẩn hóa, phase (before-submit / inside-task / after-completion), tên thread, "authenticated present?" và một mã actor đã giả danh nếu có cơ sở sử dụng.

Ví dụ dạng log an toàn:

```text
trace=req-42 phase=before-submit thread=http-nio-8080-exec-2 authPresent=true
trace=req-42 phase=inside-raw-task thread=pool-1-thread-1 authPresent=false
trace=req-42 phase=inside-delegated-task thread=pool-1-thread-2 authPresent=true
```

Đây là **dạng minh họa**, không phải dòng log cố định do Spring Security tự in. Log cần thể hiện rõ những giá trị được kiểm tra và vị trí task, nhưng không công bố credentials hoặc dữ liệu cá nhân.

## 4. Ngữ cảnh trong Servlet: vì sao ThreadLocal không đi theo Executor?

Trong Spring Security Servlet, `SecurityContextHolder` thường sử dụng `MODE_THREADLOCAL`. Khi request vào pipeline bảo mật, Spring Security lấy/khởi tạo ngữ cảnh cho **thread đang xử lý request**. Khi pipeline kết thúc, framework thực hiện cleanup theo cơ chế tương ứng.

Một thread mới hoặc worker từ thread pool **không tự nhận** giá trị `ThreadLocal` của thread gửi task.

Ví dụ conceptual:

```java
Authentication before =
    SecurityContextHolder.getContext().getAuthentication();
// Trong request đã xác thực: before có thể là Authentication của Alice.

executor.execute(() -> {
    Authentication inside =
        SecurityContextHolder.getContext().getAuthentication();
    // Với raw executor, inside thường là null.
});
```

Đây là snippet minh họa, yêu cầu `executor` và imports trong dự án Spring Security. Không nên sửa bằng cách chèn:

```java
// KHÔNG NÊN: quyền dùng chung tất cả người dùng trên toàn JVM.
SecurityContextHolder.setStrategyName(
    SecurityContextHolder.MODE_GLOBAL
);
```

`MODE_GLOBAL` khiến security context trở thành trạng thái dùng chung toàn tiến trình, không phù hợp ứng dụng nhiều request/người dùng. `MODE_INHERITABLETHREADLOCAL` cũng **không phải thuốc chữa tổng quát cho thread pool**: giá trị được kế thừa khi tạo thread không bảo đảm phản ánh đúng người gửi công việc sau đó; thread được tái sử dụng có thể giữ trạng thái sai. Thay đổi strategy toàn cục còn ảnh hưởng mọi thành phần trong JVM.

### 4.1. Cách chuẩn: DelegatingSecurityContextRunnable/Executor

Spring Security cung cấp các wrapper:

- `DelegatingSecurityContextRunnable` và `DelegatingSecurityContextCallable`;
- `DelegatingSecurityContextExecutor` / `DelegatingSecurityContextExecutorService`;
- `DelegatingSecurityContextAsyncTaskExecutor` hoặc các adapter Spring Task phù hợp.

Wrapper thiết lập context trong thời gian task chạy và thực hiện cleanup sau đó. Với `DelegatingSecurityContextExecutor(delegate)` **không truyền một SecurityContext cố định vào constructor**, ngữ cảnh được lấy khi **gửi task** từ caller. Đây là lựa chọn phù hợp cho các request độc lập nếu cần chạy task **nhân danh caller của request tại thời điểm submit**.

Ngược lại, constructor truyền **một SecurityContext cố định** sẽ dùng ngữ cảnh đó cho các task. Nếu vô tình truyền context của Alice vào executor singleton khi khởi động, mọi task có thể chạy dưới danh tính Alice — một lỗi cấp quyền nghiêm trọng. Chỉ dùng fixed context khi thực sự thiết kế một service identity chuyên dụng, có kiểm soát rõ ràng.

### 4.2. Ví dụ Java 17+ Spring Boot MVC tái hiện và sửa lỗi

Tạo ứng dụng Spring Boot 3.x / Spring Security 6.x kiểu **Servlet/MVC**, dependencies:

- `spring-boot-starter-web`
- `spring-boot-starter-security`

Lưu mã đầy đủ ở:

```text
src/main/java/demo/context/ServletContextLabApplication.java
```

```java
package demo.context;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServletContextLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServletContextLabApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth ->
                auth.anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob123"))
                .roles("USER")
                .build()
        );
    }

    // Executor thật để chạy task. Chỉ dùng cho demo.
    @Bean(destroyMethod = "shutdown")
    ExecutorService rawWorkers() {
        return Executors.newFixedThreadPool(2);
    }

    // Wrapper không chứa fixed identity: capture ngữ cảnh
    // tại thời điểm submit task từ thread caller.
    @Bean
    Executor securedExecutor(
            @Qualifier("rawWorkers") ExecutorService workers) {

        return new DelegatingSecurityContextExecutor(workers);
    }

    static String callerFromSecurityContext() {
        Authentication auth = SecurityContextHolder
            .getContext()
            .getAuthentication();

        if (auth == null
                || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            return "missing-context";
        }
        return "actor=" + auth.getName();
    }

    @RestController
    static class DemoController {
        private final ExecutorService rawWorkers;
        private final Executor securedExecutor;

        DemoController(
                @Qualifier("rawWorkers") ExecutorService rawWorkers,
                @Qualifier("securedExecutor") Executor securedExecutor) {

            this.rawWorkers = rawWorkers;
            this.securedExecutor = securedExecutor;
        }

        @GetMapping("/api/current")
        String current() {
            return callerFromSecurityContext();
        }

        // Chủ đích MINH HỌA LỖI trong môi trường cục bộ.
        @GetMapping("/api/raw")
        CompletableFuture<String> raw() {
            return CompletableFuture.supplyAsync(
                ServletContextLabApplication
                    ::callerFromSecurityContext,
                rawWorkers
            );
        }

        @GetMapping("/api/delegated")
        CompletableFuture<String> delegated() {
            return CompletableFuture.supplyAsync(
                ServletContextLabApplication
                    ::callerFromSecurityContext,
                securedExecutor
            );
        }
    }
}
```

**Đây là chương trình hoàn chỉnh trong một dự án Spring Boot có các dependency kể trên**, không thể chạy bằng `javac` trần thiếu classpath Spring. Hai endpoint `/api/raw` và `/api/delegated` trả `CompletableFuture`, cho phép Spring MVC xử lý phản hồi async sau khi task hoàn tất.

Điểm cần kiểm tra kỹ:

1. `/api/current` chạy trên request thread đã xác thực nên đọc được Alice từ `SecurityContextHolder`.
2. `/api/raw` tự đưa lambda tới `ExecutorService` bằng `CompletableFuture.supplyAsync(...)`; raw pool không tự chuyển `ThreadLocal`, vì vậy worker thường thấy `missing-context` trong demo.
3. `/api/delegated` dùng `DelegatingSecurityContextExecutor`. Wrapper capture context khi gửi task từ request thread, thiết lập context cho worker trong lúc task chạy, rồi cleanup.
4. `rawWorkers` được quản lý vòng đời bằng `destroyMethod="shutdown"` để tránh giữ thread sau khi ứng dụng dừng.
5. Không tái sử dụng `Authentication` của một request cho request khác; wrapper không dùng một `SecurityContext` toàn cục.
6. Ví dụ **không phải giải pháp truyền danh tính cho job kéo dài hàng giờ** hoặc cho một công việc do queue chạy trên máy khác. Đối với những trường hợp đó, cần một thiết kế identity/delegation riêng.

### 4.3. Chạy và quan sát

Từ thư mục gốc dự án Gradle do Spring Initializr sinh:

```bash
./gradlew bootRun

# Trên Windows PowerShell:
# .\gradlew.bat bootRun
```

Trong terminal khác:

```bash
curl -s -u alice:alice123 http://localhost:8080/api/current
curl -s -u alice:alice123 http://localhost:8080/api/raw
curl -s -u alice:alice123 http://localhost:8080/api/delegated

curl -s -u bob:bob123 http://localhost:8080/api/delegated
```

Body văn bản **kỳ vọng trong điều kiện demo không có code khác can thiệp vào raw pool**:

```text
actor=alice
missing-context
actor=alice
actor=bob
```

Bốn dòng tương ứng với bốn lệnh phía trên; không có dấu prompt, header hoặc timestamp. Nếu dùng `curl -i` để xem status thì output chứa thêm header HTTP. Không dùng mật khẩu mẫu này trong môi trường thật; HTTP Basic phải đi qua HTTPS trên mạng thực.

**Nhắc lại:** chương trình được thiết kế để minh họa lỗi thread-local và cách dùng wrapper; việc raw worker trả `missing-context` không chứng minh mọi trường hợp thiếu context đều cùng nguyên nhân. Nếu thread bị một đoạn code khác gắn security context nhưng quên dọn, worker còn có thể thấy **danh tính sai của request khác** — tuyệt đối không coi đó là hành vi đúng.

### 4.4. Cách kiểm tra trong test MVC async

Khi kiểm thử một controller trả `CompletableFuture` bằng `MockMvc`, không thể chỉ so body ngay sau `mvc.perform(...)` nếu request đã chuyển sang chế độ async. Cần lấy `MvcResult`, kiểm tra `asyncStarted()`, rồi `asyncDispatch(...)`:

```java
// Snippet bên trong lớp @SpringBootTest + @AutoConfigureMockMvc
// với field @Autowired MockMvc mvc; yêu cầu spring-security-test.
MvcResult pending = mvc.perform(
        get("/api/delegated")
            .with(httpBasic("alice", "alice123"))
    )
    .andExpect(request().asyncStarted())
    .andReturn();

mvc.perform(asyncDispatch(pending))
    .andExpect(status().isOk())
    .andExpect(content().string("actor=alice"));
```

Các static import minh họa cần có:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
```

Đây là **snippet test trong một lớp test đã cấu hình**, không phải tệp có thể biên dịch độc lập. Các dependency test thường là `spring-boot-starter-test` và `spring-security-test`. `MockMvc` cũng cần được cấu hình đi qua Spring Security filter chain.

Lưu ý: Spring Security có **tích hợp nhất định với Servlet `AsyncContext.start(Runnable)` và Spring MVC async**. Đừng kết luận “mọi async Servlet đều mất context”. Mục đích của ví dụ là **tác vụ do chính chương trình gửi đến raw ExecutorService**, cần được kiểm chứng độc lập với cơ chế async response của MVC.

## 5. Sai lầm thường gặp với @Async và CompletableFuture

### 5.1. @Async dùng thread pool nhưng không có security-aware executor

Đây là dạng lỗi phổ biến:

```java
// Minh họa method trong một @Service dùng @EnableAsync.
// Nếu executor không truyền SecurityContext, principal có thể thiếu.
@Async
public CompletableFuture<String> process() {
    Authentication authentication = SecurityContextHolder
        .getContext()
        .getAuthentication();

    String name = authentication == null
        ? "missing-context"
        : authentication.getName();

    return CompletableFuture.completedFuture(name);
}
```

Để dùng Spring `@Async` an toàn khi có nhu cầu chạy **nhân danh caller**, cần cấu hình task executor tương ứng với `DelegatingSecurityContextAsyncTaskExecutor` hoặc lớp wrapper tương đương; bảo đảm Spring `@Async` chọn đúng executor, không phải bean raw executor khác. Ví dụ cấu hình **minh họa một phần**:

```java
@Bean
AsyncTaskExecutor securityAwareTaskExecutor(
        ThreadPoolTaskExecutor delegate) {

    return new DelegatingSecurityContextAsyncTaskExecutor(
        delegate
    );
}
```

Các kiểu trong snippet thuộc Spring Task và Spring Security task integration; phải có `ThreadPoolTaskExecutor` được tạo, khởi tạo và quản lý đóng ứng dụng phù hợp, đồng thời gắn `@Async("securityAwareTaskExecutor")` hoặc cấu hình executor mặc định. Đừng đặt bean wrapper mà không bảo đảm chính method thực sự dùng nó.

Một lỗi khác: gọi một method `@Async` từ chính một method khác **trên cùng đối tượng (`this.asyncMethod()`)** có thể bỏ qua proxy Spring, khiến method không chạy theo mô hình async mà bạn tưởng. Khi debug, phân biệt rõ “task có được chuyển thread không?” và “context có được truyền đúng không?” — hai vấn đề khác nhau.

### 5.2. Chuỗi Future có điểm chuyển thread thứ hai

Giả sử một bước ban đầu đã chạy trong executor aware:

```java
CompletableFuture<String> result = CompletableFuture
    .supplyAsync(this::loadData, securedExecutor)
    .thenApplyAsync(this::enrichData);
```

`thenApplyAsync(...)` không truyền `Executor` ở đây nên mặc định có thể chạy trên common pool, **không đương nhiên nhận SecurityContext** từ bước trước. Nếu `enrichData` cần principal, phải truyền executor phù hợp cho giai đoạn đó hoặc — tốt hơn — lấy và xác minh danh tính/authorization trước khi tạo chuỗi tác vụ, rồi truyền các giá trị nghiệp vụ tối thiểu cần thiết một cách tường minh.

Không coi `thenApply(...)` là “an toàn tuyệt đối” chỉ vì không có hậu tố Async: nó có thể chạy trên thread hoàn thành một stage trước đó, không nhất thiết thread gốc gửi công việc.

### 5.3. Không giữ request-scoped Authentication vô hạn

Một tác vụ được đưa vào queue và thực thi nhiều giờ sau có thể chạy khi session đã hết hạn hoặc quyền người dùng đã bị thu hồi. Truyền nguyên object `SecurityContext` lâu dài không phải chính sách ủy quyền tốt cho background job.

Khi thiết kế job dài hạn, nên:

- Ghi nhận **actor ID đã xác minh**, action được yêu cầu, resource ID và lý do/giới hạn ủy quyền.
- Quyết định job chạy dưới **service identity** hay một cơ chế delegated authorization hợp lệ.
- Kiểm tra lại trạng thái quyền tại thời điểm thực hiện những hành động nhạy cảm theo yêu cầu nghiệp vụ.
- Không serialize access token/session cookie vào hàng đợi chỉ để phục hồi `SecurityContext`.
- Audit rõ “ai khởi tạo” và “principal nào thực sự thực thi”, tránh tự gán quyền quá mức.

## 6. WebFlux: ReactiveSecurityContextHolder chứ không phải Servlet ThreadLocal

Spring Security reactive đưa security information vào **Reactor Context** gắn với subscriber, qua các thành phần như `ReactorContextWebFilter` và cơ chế xác thực reactive.

Dùng đúng API:

```java
Mono<String> principalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(authentication -> authentication.getName());
}
```

Đây là **method Java minh họa** trong ứng dụng reactive có Reactor/Spring Security. Publisher trả giá trị khi có `SecurityContext` hợp lệ trong subscriber hiện tại; nếu không có, có thể hoàn thành rỗng. Không biến việc thiếu context thành người dùng tự nhận qua `X-User-Id`.

Không nên dùng:

```java
// Sai cho việc xác định danh tính request WebFlux
// nếu code phụ thuộc ThreadLocal kiểu Servlet.
String user = SecurityContextHolder
    .getContext()
    .getAuthentication()
    .getName();
```

Trong pipeline reactive, code có thể chạy trên nhiều scheduler. Việc đọc `SecurityContextHolder` dạng ThreadLocal có thể trả null, null pointer hoặc một dữ liệu không liên quan (nếu môi trường khác làm rò ThreadLocal). Reactive `SecurityContext` phải được đọc từ subscriber context bằng `ReactiveSecurityContextHolder` hoặc tham số principal reactive được framework cung cấp.

### 6.1. Điều gì xảy ra khi publishOn()/subscribeOn()?

Một điểm rất dễ hiểu sai:

- `publishOn(scheduler)` thay đổi nơi **một phần downstream signal** được xử lý.
- `subscribeOn(scheduler)` ảnh hưởng nơi phần subscribe/upstream thực thi.
- **Bản thân chúng không xóa Reactor Context** khỏi một subscription đúng cách được tạo và truyền theo Reactor API.

Reactor Context **không đi theo thread**; nó được truyền theo tín hiệu subscription. Nếu một request WebFlux có security context và pipeline sử dụng `Mono`/`Flux` đúng cách, phần code sau khi đổi scheduler vẫn có thể truy cập `ReactiveSecurityContextHolder`.

Vì vậy câu "request mất user sau `publishOn` nên publishOn làm mất security context" thường là chẩn đoán thiếu một bước: chính code đó có đang đọc `ThreadLocal` hay không, đã tạo subscription mới, đã rời Reactor chain, hoặc dùng library không truyền context hay chưa?

### 6.2. Ví dụ Java 17+ WebFlux chạy riêng

Tạo **một dự án Spring Boot khác** để không trộn Spring MVC và Spring WebFlux ngoài ý muốn. Dependencies:

- `spring-boot-starter-webflux`
- `spring-boot-starter-security`

Tệp:

```text
src/main/java/demo/reactivecontext/ReactiveContextLabApplication.java
```

```java
package demo.reactivecontext;

import java.time.Duration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveContextLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveContextLabApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/actor").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    PasswordEncoder encoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build()
        );
    }

    @RestController
    static class ReactiveController {

        @GetMapping("/api/actor")
        Mono<String> actor() {
            // Chủ đích chuyển scheduler, vẫn ở cùng Reactor chain.
            return Mono.delay(Duration.ofMillis(10))
                .publishOn(Schedulers.boundedElastic())
                .then(
                    ReactiveSecurityContextHolder.getContext()
                        .map(context ->
                            context.getAuthentication().getName()
                        )
                        .map(name -> "actor=" + name)
                        .defaultIfEmpty("missing-context")
                );
        }
    }
}
```

Đây là **chương trình Spring Boot WebFlux hoàn chỉnh khi đặt trong dự án với hai dependency trên**. Kết quả `Mono.delay(...)` chỉ để chủ động tạo xử lý bất đồng bộ. `publishOn(Schedulers.boundedElastic())` chuyển scheduler, còn lời gọi `ReactiveSecurityContextHolder.getContext()` được thực thi trong pipeline nối tiếp, thuộc cùng subscription.

Chạy:

```bash
./gradlew bootRun

# Ở terminal khác
curl -i http://localhost:8080/api/actor
curl -i -u alice:alice123 http://localhost:8080/api/actor
```

Kỳ vọng:

| Request | HTTP status | Body |
| --- | --- | --- |
| Không có credentials | **401** | Basic challenge do Spring Security; không tới controller |
| Basic credentials của Alice hợp lệ | **200** | `actor=alice` |

Kết quả "actor=alice" sau một asynchronous boundary minh họa rằng Reactor context vẫn có mặt khi pipeline được ghép đúng. Đừng dựa vào việc log thấy tên thread cũ hay mới để suy ra điều kiện bảo mật.

Lưu ý rằng demo này không minh họa cách gọi database blocking: `boundedElastic` thường dùng cho thao tác blocking có kiểm soát, nhưng **đổi sang boundedElastic không biến truy vấn JDBC thành non-blocking**. Nếu ứng dụng có blocking work, cần thiết kế scheduling, timeout và tài nguyên pool phù hợp.

## 7. Một phép thử nhỏ chứng minh Reactor Context theo subscription

Nếu đã có dự án với `spring-security-test`, `reactor-test`, bạn có thể viết unit test cho một publisher ngoài HTTP. Tệp test trong dự án Spring Boot WebFlux được tạo ở trên:

```text
src/test/java/demo/reactivecontext/ReactorSecurityContextTest.java
```

```java
package demo.reactivecontext;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication
    .UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context
    .ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ReactorSecurityContextTest {

    @Test
    void identitySurvivesPublishOn() {
        Authentication alice =
            new UsernamePasswordAuthenticationToken(
                "alice",
                "n/a",
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
            );

        Mono<String> pipeline = Mono.just("work")
            .publishOn(Schedulers.boundedElastic())
            .flatMap(ignored ->
                ReactiveSecurityContextHolder.getContext()
                    .map(context ->
                        context.getAuthentication().getName()
                    )
            )
            .map(name -> "actor=" + name)
            .contextWrite(
                ReactiveSecurityContextHolder
                    .withAuthentication(alice)
            );

        StepVerifier.create(pipeline)
            .expectNext("actor=alice")
            .verifyComplete();
    }
}
```

**Lưu ý kỹ thuật về imports:** Java cho phép ngắt dòng trong một câu lệnh import trước dấu chấm, nhưng để thuận tiện copy mã, bạn có thể viết các import bị ngắt dòng thành một dòng như sau:

```java
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
```

Dùng **hai dòng đầy đủ thay cho các import bị ngắt dòng**, không giữ cả hai dạng. Với Gradle, thêm:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là phần dependency **bổ sung vào build.gradle đã có plugin Spring Boot**, không phải file Gradle hoàn chỉnh. Chạy:

```bash
./gradlew test --tests "demo.reactivecontext.ReactorSecurityContextTest"
```

Test tạo `Authentication` **chỉ để kiểm tra truyền context nội bộ trong unit test**; nó không chứng minh username/password thật hay JWT đã được xác minh. Giá trị fake không được đưa vào request production để mạo danh Alice.

Điểm quan trọng trong test: `flatMap(...)` gọi `ReactiveSecurityContextHolder.getContext()` **sau** `publishOn`, vì vậy phép thử không chỉ đọc context trước khi đổi scheduler rồi giữ lại tên trong một biến String. `contextWrite(...)` đặt authentication vào **Reactor Context của subscription kiểm thử**, không vào ThreadLocal của một thread cố định.

## 8. Các kiểu lỗi reactive làm ngữ cảnh không còn đúng phạm vi

### 8.1. Tự subscribe trong controller/service

Sai về thiết kế điều phối:

```java
// Minh họa lỗi, không dán trực tiếp vào ứng dụng mẫu.
public Mono<String> process() {
    somePublisher()
        .flatMap(this::saveEvent)
        .subscribe(); // Công việc tách thành một subscription khác.

    return Mono.just("accepted");
}
```

Lời gọi `subscribe()` tạo một subscription độc lập. Bởi vậy code gọi không còn kiểm soát được hoàn thành, error handling, backpressure hoặc context propagation như một nhánh duy nhất của request. Nếu `somePublisher()` cần security context, subscription mới **không mặc định có cùng context của request**.

Cách ghép đúng trong cùng pipeline:

```java
public Mono<String> process() {
    return somePublisher()
        .flatMap(this::saveEvent)
        .thenReturn("accepted");
}
```

Hai snippet này **chỉ minh họa cấu trúc method** và giả định `somePublisher()`, `saveEvent(...)` đã được định nghĩa trong service phù hợp. Chúng không phải chương trình độc lập để biên dịch. Nếu công việc cần thực sự tách khỏi HTTP request (fire-and-forget, queue, scheduled job), hãy thiết kế event/job riêng và quyết định danh tính của job thay vì hy vọng subscription context ngầm đi theo.

### 8.2. Chuyển từ reactive sang CompletableFuture hoặc callback

Ví dụ:

```java
// Minh họa ranh giới cần đánh giá:
CompletableFuture<Data> future = thirdPartyClient.loadAsync();
return Mono.fromFuture(future);
```

`Mono.fromFuture(...)` có thể đưa **kết quả** của Future vào một pipeline reactive, nhưng code đã được chạy bên trong Future **không tự có Reactor Context của subscriber**. Nếu `thirdPartyClient.loadAsync()` cần biết actor, phải truyền metadata actor đã được xác minh vào lời gọi theo hợp đồng rõ ràng hoặc dùng bridge/context propagation phù hợp.

Không suy rằng bản thân `Mono.fromFuture` luôn "làm mất SecurityContext". Lỗi xảy ra khi code cần identity được thực thi ở **ngoài subscription có ngữ cảnh**, hoặc khi ai đó dùng ThreadLocal không được bridge.

### 8.3. Dùng block() ở chỗ không phù hợp

`block()`/`blockOptional()` tạo **subscription** để lấy giá trị đồng bộ. Trong các thread non-blocking của WebFlux, lời gọi `block()` có thể gây lỗi hoặc làm cạn thread, đồng thời tạo một đường thực thi độc lập khiến bối cảnh/điều phối khó suy luận. Không dùng `block()` bên trong handler/reactive chain để lấy username.

Sai:

```java
// Tránh trong handler reactive:
String name = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .block();
```

Đúng hơn là giữ kiểu reactive:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName());
```

Các snippet trên minh họa một phần service/controller; việc trả `Mono<String>` giả định method có kiểu trả phù hợp. Trong test hoặc điểm tích hợp blocking bên ngoài reactive stack, có thể có trường hợp `block()` được dùng có kiểm soát, nhưng **không lấy nó làm chiến lược quản lý security context trong request reactive**.

### 8.4. Đặt contextWrite sai vị trí/nhầm hướng truyền

`contextWrite(...)` ghi context cho phần **upstream** theo luồng subscription. Không thể suy vị trí tác động bằng thứ tự Java dòng trên/dưới như biến mutable. Ví dụ unit test ở mục 7 đặt context tại cuối pipeline trước `StepVerifier` để phần upstream đọc được.

`Mono.deferContextual(...)` được dùng để quan sát trực tiếp Reactor Context; `ReactiveSecurityContextHolder.getContext()` là API Spring Security để lấy `SecurityContext` tương ứng. Nếu tự viết một `contextWrite(context -> Context.empty())` hoặc xoá key mà thư viện bảo mật cần, bạn có thể vô tình loại bỏ dữ liệu cần thiết của pipeline.

Không tự gán `SecurityContext` từ request header chưa xác minh bằng `contextWrite(...)` để "sửa 403": đó là hành vi mạo danh. Trong test, `ReactiveSecurityContextHolder.withAuthentication(testAuthentication)` có thể dùng để **giả lập** ngữ cảnh; production phải có authentication flow thực sự được kiểm chứng.

### 8.5. Nhầm Reactor Context với MDC/ThreadLocal observability

Một dòng log thiếu `traceId` hoặc MDC **không có nghĩa** Spring Security Authentication bị mất. Ngược lại, MDC đúng cũng không chứng minh security context có mặt. Các cầu nối `io.micrometer:context-propagation` và chế độ automatic context propagation của Reactor giúp một số giá trị ThreadLocal tham gia context propagation trong điều kiện được hỗ trợ, nhưng **không biến tất cả ThreadLocal tùy ý thành context bảo mật đúng**.

Khi chẩn đoán cần đo **cả hai riêng biệt**: authentication có mặt từ API chính thức của stack không; tracing/diagnostic fields có được truyền theo đúng cơ chế observability không. Chỉ chọn bật automatic context propagation khi đã hiểu phiên bản thư viện, accessor, vòng đời và ảnh hưởng hiệu năng; không xem đó là cách sửa chung cho mọi lỗi quyền.

## 9. Cách kiểm chứng bằng WebTestClient ở lớp HTTP reactive

Trong dự án WebFlux, có thể dùng `WebTestClient` gắn với `ApplicationContext` để request chạy qua chuỗi `SecurityWebFilterChain` mà không mở HTTP port:

```java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();

client.mutateWith(mockUser("alice").roles("USER"))
    .get()
    .uri("/api/actor")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("actor=alice");
```

Snippet này giả định lớp test có `ApplicationContext applicationContext` đã inject, `WebTestClient` của Spring Test, static import `springSecurity` và `mockUser` trong `SecurityMockServerConfigurers`, cùng dependency `spring-security-test`. **Đây là snippet kiểm thử tích hợp**, không phải chương trình độc lập.

Phân biệt hai tầng test:

- `mockUser()` tạo `Authentication` giả lập trong test để kiểm tra **ngữ cảnh được giữ tới controller** và phân quyền theo role. Nó **không** kiểm chứng password, chữ ký JWT, issuer, audience hoặc OAuth2 introspection.
- Gửi HTTP Basic credentials qua `WebTestClient` hoặc `curl` với `MapReactiveUserDetailsService` thật giúp xác minh **xác thực đầu vào** và context tới handler.

Với WebFlux ứng dụng mẫu, thêm bài test qua scheduler khác để chứng minh `ReactiveSecurityContextHolder` vẫn có dữ liệu. Với request anonymous, yêu cầu `/api/actor` phải bị chặn (thường 401 bởi HTTP Basic) **trước khi** controller lấy context. Không biến `missing-context` thành thành công HTTP 200 để che lỗi trong sản phẩm thật; giá trị đó chỉ phục vụ nhận diện lỗi trong demo.

### Test concurrency để bắt rò danh tính

Trong Servlet demo, chạy liên tiếp hoặc đồng thời các request `/api/delegated` dưới Alice và Bob. Kiểm tra mỗi body có đúng actor của request đó. Nếu trả `actor=alice` cho request Bob thì vấn đề không còn là mất context mà là **cross-request context leak**. Khi test, sử dụng identity giả, không dùng dữ liệu cá nhân thật.

Test tối thiểu cần có:

| Stack | Tình huống | Kết quả đúng |
| --- | --- | --- |
| Servlet | Request Alice đọc context đồng bộ | Alice |
| Servlet | Alice gửi task tới raw executor không propagate | Thường context trống trong demo |
| Servlet | Alice gửi task tới delegated executor | Alice |
| Servlet | Bob gửi task tới cùng delegated executor | Bob, không nhận identity của Alice |
| Servlet | Anonymous gọi endpoint bảo vệ | Bị chặn tại security filter |
| WebFlux | Alice qua `publishOn` rồi gọi `ReactiveSecurityContextHolder` | Alice |
| WebFlux | Mock user trong test | Alice tới handler và method security theo rule |
| WebFlux | Request không credentials | 401/challenge khi dùng HTTP Basic |
| WebFlux | Task tách khỏi subscription và không truyền identity | Không được mặc định có context của request |
| Cả hai | Code tự gán user từ `X-User-Id` | Không được coi là caller đã xác thực |

## 10. Gỡ lỗi theo thứ tự để không nhầm nguyên nhân 401/403

### Bước 1 — Xác định stack thực sự đang chạy

Kiểm tra ứng dụng dùng `spring-boot-starter-web` (Servlet) hay `spring-boot-starter-webflux` (reactive). Khi có cả hai, Spring Boot 3.x thường ưu tiên chế độ Servlet nếu không yêu cầu reactive rõ ràng. Đừng chỉ nhìn một method trả `Mono` rồi kết luận toàn ứng dụng là WebFlux.

- Servlet: kiểm tra `HttpSecurity`, `SecurityFilterChain`, `SecurityContextHolder`.
- WebFlux: kiểm tra `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveSecurityContextHolder`.

### Bước 2 — Xác minh HTTP authentication và authorization trước

Gửi một request có credentials **hợp lệ trong môi trường test**. Nếu ngay ở filter đã trả 401/403, chưa tới công đoạn async thì nguyên nhân không phải mất ngữ cảnh trong worker. Với POST còn phải kiểm tra CSRF. Xem status ban đầu, route matcher, role và entry point.

### Bước 3 — Đo context tại hai đầu ranh giới

Trong Servlet, ghi sự tồn tại của `SecurityContextHolder.getContext().getAuthentication()` ngay trước khi submit task và **bên trong task**, cùng request ID và loại executor. Trong WebFlux, đo bằng `ReactiveSecurityContextHolder.getContext()` **tại chỗ tiêu thụ signal**, không lấy giá trị `SecurityContextHolder` của ThreadLocal rồi kết luận.

Không log toàn bộ `Authentication`, credentials, JWT, session cookie hoặc dữ liệu cá nhân. Nếu cần đối chiếu actor giữa các phase, dùng một mã nội bộ/pseudonymous đã được cấp và bảo vệ.

### Bước 4 — Chỉ rõ ranh giới bị đứt

Tìm `new Thread`, `ExecutorService`, `CompletableFuture.supplyAsync/thenApplyAsync`, `@Async`, callback SDK, message queue, scheduler, tự `subscribe()` hoặc `block()`. Đánh dấu task thuộc request hay đã trở thành job độc lập. Kiểm tra executor thực sự sử dụng; cấu hình một bean security-aware **không có tác dụng** nếu method vẫn dùng common pool.

### Bước 5 — Sửa theo mô hình đúng

- **Servlet cùng request:** dùng `DelegatingSecurityContextExecutor`/`Runnable`/`Callable` hoặc adapter task phù hợp để transfer context khi có chủ đích. Kiểm tra cleanup và tránh fixed context sai.
- **WebFlux cùng subscription:** compose `Mono`/`Flux`, đọc bằng `ReactiveSecurityContextHolder`, không tạo subscription con tự phát và không dùng Servlet ThreadLocal để tìm principal.
- **Tác vụ background thực sự:** truyền actor/job identity theo hợp đồng nghiệp vụ, phân quyền phù hợp tại thời điểm thực thi và audit nguồn yêu cầu.
- **Bridge reactive ↔ blocking:** xác định điểm cắt, chuyển **dữ liệu tối thiểu đã xác minh** hoặc dùng cơ chế context propagation được hỗ trợ/test kỹ; không chép token tùy tiện.

### Bước 6 — Thử nhiều request đồng thời

Một test đơn lẻ không bắt được mọi lỗi. Chạy hai tài khoản test khác nhau xen kẽ qua cùng thread pool; xác nhận không lẫn danh tính. Thử timeout, lỗi task, cancellation, retry và shutdown. Sau lỗi, task tiếp theo **không được kế thừa** security context của task trước.

## 11. Những cách "sửa" nguy hiểm cần tránh

1. **`MODE_GLOBAL`**: biến principal thành trạng thái toàn tiến trình, có thể làm lẫn các user.
2. **`MODE_INHERITABLETHREADLOCAL` áp dụng bừa bãi**: có thể giữ ngữ cảnh stale ở thread pool; không bảo đảm danh tính hiện tại của request.
3. **Không dọn ThreadLocal sau task**: làm rò thông tin giữa requests; thư viện wrapper chuẩn có cơ chế cleanup/restoration.
4. **Tạo principal từ header `X-User-Id` hoặc query `userId`**: chỉ chuyển lỗi mất context thành lỗ hổng mạo danh.
5. **Cố định một `SecurityContext` của admin vào executor dùng chung**: mọi task có thể chạy với quyền admin.
6. **Tắt `@PreAuthorize` / `authorizeHttpRequests`** chỉ vì 403: làm mất lớp bảo vệ thay vì sửa nguồn identity.
7. **Gọi `block()` trong request WebFlux** để đọc username: có thể chặn event loop và tạo subscription sai phạm vi.
8. **Gọi `subscribe()` trong service không có quản lý vòng đời**: tách context, lỗi và completion khỏi request.
9. **Cho rằng `publishOn` tự làm mất Reactor Context**: dễ dẫn tới sửa sai; phải kiểm tra API context và ranh giới thực.
10. **Ghi toàn bộ security context vào log**: có nguy cơ lộ credentials và dữ liệu cá nhân, đặc biệt khi TRACE bật rộng.
11. **Cho mọi task nền chạy dưới danh tính HTTP đang gọi khi đã hết request**: không có nghĩa ủy quyền vẫn còn hiệu lực.
12. **Coi context propagation là authorization**: truyền đúng Alice chỉ cho biết "ai thực thi"; vẫn cần kiểm tra Alice được quyền trên **resource/action** cụ thể hay không.

## 12. Checklist áp dụng khi điều tra sự cố thực tế

- [ ] Xác định rõ Servlet hay WebFlux và phiên bản Spring Security/Boot.
- [ ] Xác nhận request ban đầu đã xác thực thành công và rule 401/403/CSRF được hiểu đúng.
- [ ] Đo actor **trước và sau điểm chuyển xử lý** bằng API đúng với stack.
- [ ] Kiểm tra executor/scheduler thực sự được gọi; không đoán theo tên bean.
- [ ] Với Servlet, xác nhận có cơ chế capture/restore/cleanup `SecurityContext` khi tự tạo task.
- [ ] Với WebFlux, giữ cùng Reactor subscription và lấy context bằng `ReactiveSecurityContextHolder`.
- [ ] Kiểm tra mọi nhánh `Future`, `@Async`, callback, nested subscribe, queue, scheduled job.
- [ ] Xác minh method security/authorization **không bị vô hiệu hóa** để che lỗi.
- [ ] Kiểm tra xử lý timeout/cancel/error có cleanup và không rò danh tính.
- [ ] Chạy test xen kẽ Alice/Bob trên cùng pool để phát hiện ngữ cảnh của người khác.
- [ ] Không ghi token, password, principal serialize hoặc raw personal data vào log.
- [ ] Phân biệt "có đúng Authentication" với "có đủ quyền cho tài nguyên".

**Kết luận:** trong Servlet, một `ThreadLocal` không tự đi theo task trên executor — dùng cơ chế delegation của Spring Security khi cần. Trong WebFlux, ngữ cảnh được truyền qua **Reactor subscriber Context**; đổi scheduler không tự làm mất nó, nhưng tự tách subscription, thoát khỏi pipeline hoặc đọc sai API có thể khiến code không thấy danh tính đúng. Mọi cách sửa phải bảo vệ **hai chiều**: không mất quyền hợp lệ của người gọi và tuyệt đối không làm lẫn quyền của người dùng khác.

### Tài liệu chính thức

- [Spring Security 6.5 — Concurrency Support (Servlet)](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html)
- [Spring Security — Servlet Concurrency Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Security — Servlet AsyncContext integration](https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html)
- [Spring Security 6.5 — Reactive Method Security and Reactor Context](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Project Reactor — Adding Context to a Reactive Sequence](https://projectreactor.io/docs/core/3.7.0/reference/advancedFeatures/context.html)
- [Project Reactor — Context Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
- [Spring Security — Reactive Web Test Support](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
