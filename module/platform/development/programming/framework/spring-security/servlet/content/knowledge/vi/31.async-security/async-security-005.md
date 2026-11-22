# DelegatingSecurityContextExecutor và bộ thực thi cho @Async trong Spring Security Servlet

## 1. Tại sao SecurityContext biến mất khi chạy bất đồng bộ?

Trong một ứng dụng **Spring Boot + Spring Security Servlet**, request HTTP thường được xử lý trên một thread của servlet container. Sau khi xác thực, Spring Security đặt thông tin người dùng vào **SecurityContextHolder**. Với chiến lược mặc định **MODE_THREADLOCAL**, mỗi thread có một SecurityContext riêng.

Ví dụ, controller nhận request đã xác thực của người dùng **alice** rồi gọi một tác vụ trên thread pool:

~~~text
HTTP request: Authorization: Basic ...
          |
          v
Thread servlet: http-nio-8080-exec-4
  SecurityContextHolder -> Authentication(name="alice")
          |
          | executor.execute(...) hoặc @Async
          v
Thread worker: secured-async-1
  SecurityContextHolder -> ?  (mặc định không được chuyển từ thread servlet)
          |
          v
Ghi audit / gửi thông báo / gọi service kiểm tra quyền
~~~

Nếu dùng một **Executor**, **ExecutorService**, **CompletableFuture.supplyAsync(...)** hoặc một phương thức **@Async** với thread pool thông thường, việc chuyển sang thread khác **không tự động mang theo** SecurityContext của request. Kết quả có thể là:

- **SecurityContextHolder.getContext().getAuthentication() == null** trong worker.
- Một phép kiểm tra quyền theo principal không còn thấy user.
- Audit ghi thiếu người yêu cầu.
- Nếu tự chép ThreadLocal nhưng quên dọn dẹp, worker có thể **rò rỉ danh tính** từ công việc trước sang công việc sau.

Spring Security cung cấp các wrapper **DelegatingSecurityContext...** để chuyển một SecurityContext đã được lựa chọn vào lúc chạy task, đồng thời phục hồi/dọn trạng thái thread trong khối **finally**. Hai thành phần quan trọng của bài này:

1. **DelegatingSecurityContextExecutor**: dành cho API **java.util.concurrent.Executor.execute(Runnable)**.
2. **DelegatingSecurityContextAsyncTaskExecutor**: dành cho Spring **AsyncTaskExecutor**, phù hợp với **@Async** và cả các lời gọi **submit(...)** được hỗ trợ.

Mục tiêu không phải biến mọi background task thành “được quyền làm mọi thứ”, mà là **bảo toàn danh tính và ngữ cảnh xác thực tại đúng thread** để các bước kiểm tra tiếp theo có dữ liệu phù hợp.

## 2. Ba lớp cơ chế cần phân biệt

### 2.1. SecurityContext, SecurityContextHolder và Authentication

- **Authentication** là đối tượng chứa principal, authorities và trạng thái xác thực; tùy cách đăng nhập có thể là UsernamePasswordAuthenticationToken, JwtAuthenticationToken, OAuth2AuthenticationToken hoặc implementation khác.
- **SecurityContext** giữ Authentication. Nó là một đối tượng; việc truyền tham chiếu của nó **không tự tạo bản sao sâu bất biến**.
- **SecurityContextHolder** cung cấp cách truy cập SecurityContext trong execution context hiện tại. Mặc định Spring Security Servlet dùng ThreadLocal.
- **SecurityContextHolderFilter / SecurityContextPersistenceFilter** ở các thế hệ cấu hình khác nhau thiết lập và giải phóng security context trong request lifecycle; không nên dựa vào context còn nằm trên servlet thread sau khi request kết thúc.

Đọc tên người dùng mà không giả định loại Authentication cụ thể:

~~~java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
String username = auth == null ? "anonymous" : auth.getName();
~~~

Đoạn trên là **snippet đặt trong một phương thức Java đã import** Authentication và SecurityContextHolder, không phải chương trình chạy độc lập. Đừng ép kiểu sang UsernamePasswordAuthenticationToken nếu ứng dụng có thể dùng JWT/OIDC.

### 2.2. Vì sao InheritableThreadLocal không phải giải pháp cho thread pool?

**SecurityContextHolder.MODE_INHERITABLETHREADLOCAL** cho phép thread con mới nhận một giá trị context theo cơ chế Java InheritableThreadLocal. Nhưng thread pool **tái sử dụng thread**: worker có thể được tạo lâu trước khi có request mới và tiếp tục chạy nhiều task của nhiều người dùng.

Điều này tạo các vấn đề:

- Context được thừa kế lúc **thread được tạo**, không đảm bảo phản ánh user **đang submit task**.
- Thread có thể chạy các công việc khác nhau với nhiều principal.
- Sai sót cleanup có thể khiến một task quan sát danh tính của task khác.

Vì vậy, **không bật MODE_INHERITABLETHREADLOCAL toàn ứng dụng chỉ để “sửa” @Async**. Với thread pool, hãy dùng wrapper chuyển context theo từng task và phục hồi context khi task kết thúc.

### 2.3. Wrapper hoạt động như thế nào?

Ý tưởng của **DelegatingSecurityContextRunnable** (mô tả logic, không phải source code nội bộ chính xác từng phiên bản):

~~~text
Khi submit:
  capture SecurityContext của caller (nếu không truyền context cố định)
  bọc Runnable gốc thành DelegatingSecurityContextRunnable

Khi worker chạy:
  ghi nhớ SecurityContext hiện có trên worker (nếu cần)
  đặt context đã chọn vào SecurityContextHolder của worker
  try:
      chạy Runnable gốc
  finally:
      phục hồi / xóa SecurityContext trên worker
~~~

**Khối finally là thiết yếu**: nếu task ném exception, context vẫn phải được dọn. Không tự viết ThreadLocal setter mà thiếu cleanup.

**Thời điểm chụp context:** Constructor wrapper không truyền SecurityContext rõ ràng được dùng để lấy context của caller **khi submit task** (ví dụ gọi execute), không phải để “đóng băng” user lúc bean Executor được tạo. Điều này cho phép một Executor bean phục vụ alice và bob trong các request khác nhau mà mỗi task thấy context tương ứng.

**Lưu ý về tham chiếu:** Các wrapper thường giữ SecurityContext được chọn, không cam kết deep clone mọi trường trong Authentication. Vì vậy tránh sửa Authentication/SecurityContext sau khi đã submit, tránh dùng cùng một mutable context cho tác vụ chạy đồng thời, và không coi wrapper là bằng chứng rằng credential/token vẫn còn hợp lệ khi task thực thi sau nhiều phút.

## 3. DelegatingSecurityContextExecutor: dùng với execute(Runnable)

Giả sử đã có một **Executor delegate** quản lý thread. Có thể bọc nó như sau:

~~~java
Executor contextAware =
        new DelegatingSecurityContextExecutor(delegate);

contextAware.execute(() -> {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
    String user = auth == null ? "anonymous" : auth.getName();
    // Ghi audit hoặc thực hiện logic đã được cấp quyền phù hợp.
});
~~~

Đây là **snippet minh họa**: biến delegate cần được định nghĩa, executor cần được quản lý vòng đời, và phải import đúng Executor, Authentication, SecurityContextHolder, DelegatingSecurityContextExecutor. Khi gọi **execute(...)**, context hiện tại của caller được gắn với Runnable.

### Hai kiểu constructor và tác động bảo mật

**A. Capture theo caller ở mỗi lần submit:**

~~~java
Executor wrapped =
        new DelegatingSecurityContextExecutor(delegate);
~~~

Dùng khi task phải chạy **nhân danh user vừa gửi request**. Cùng một Executor có thể nhận task từ nhiều request khác nhau mà không trộn context, miễn là wrapper được sử dụng ở mọi đường vào.

**B. Dùng một SecurityContext được truyền tường minh:**

~~~java
SecurityContext serviceContext =
        SecurityContextHolder.createEmptyContext();
serviceContext.setAuthentication(serviceAuthentication);

Executor wrapped =
        new DelegatingSecurityContextExecutor(delegate, serviceContext);
~~~

Đoạn này chỉ là **snippet**; serviceAuthentication là một Authentication đã được tạo và cấp quyền theo quy trình tin cậy của ứng dụng. Cấu hình này khiến các task dùng **cùng một context đã chỉ định**, không phải user đang gọi execute.

Trường hợp context tường minh thích hợp với **tác vụ nền thật sự chạy dưới service principal cố định** và có ranh giới quyền rõ ràng. Nó **không** thích hợp để bọc Executor xử lý mọi request của người dùng bằng một principal admin, vì như vậy mọi task có thể được chạy với quyền sai.

### Executor vs ExecutorService

**DelegatingSecurityContextExecutor** có giao diện **execute(Runnable)**. Nếu bạn cần **submit(Callable)** hoặc trả về **Future**, cân nhắc wrapper đúng loại, như **DelegatingSecurityContextExecutorService** cho ExecutorService. Đối với **@Async**, đừng dùng nhầm Executor thuần khi bạn đã có **AsyncTaskExecutor** của Spring: dùng wrapper dành riêng cho AsyncTaskExecutor ở mục tiếp theo.

## 4. Dùng DelegatingSecurityContextAsyncTaskExecutor cho @Async

### 4.1. Vì sao @Async cần một bean AsyncTaskExecutor?

Khi một phương thức được đánh dấu:

~~~java
@Async("securityContextExecutor")
public CompletableFuture<String> currentUser() {
    // Chạy trên một worker do executor được chọn cung cấp.
}
~~~

Spring tạo proxy để gửi công việc tới executor có tên **securityContextExecutor**. Nếu đó chỉ là một pool bình thường, SecurityContext không nhất thiết có mặt trong task. Để bảo đảm propagation trên task được submit qua @Async, hãy đặt **DelegatingSecurityContextAsyncTaskExecutor** bên ngoài một **ThreadPoolTaskExecutor**.

**Đặt tên rõ ràng** cho executor trong @Async giúp tránh việc Spring chọn executor mặc định khác không có security context wrapper.

### 4.2. Ví dụ ứng dụng hoàn chỉnh: Spring Boot 3.x, Security 6.x, Java 17+

Tạo dự án Spring Boot 3.x dùng Java 17+, với Gradle wrapper. File **build.gradle** cần các starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Tệp **src/main/java/com/example/asyncsecurity/AsyncSecurityApplication.java**:

~~~java
package com.example.asyncsecurity;

import java.util.concurrent.Executor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
@EnableAsync
public class AsyncSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(AsyncSecurityApplication.class, args);
    }

    @Bean("rawAsyncPool")
    ThreadPoolTaskExecutor rawAsyncPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("secured-async-");
        // Là Spring bean nên framework quản lý initialize/shutdown.
        return pool;
    }

    @Bean("securityContextExecutor")
    AsyncTaskExecutor securityContextExecutor(
            @Qualifier("rawAsyncPool") ThreadPoolTaskExecutor pool) {
        // Capture context theo caller khi mỗi task được submit.
        return new DelegatingSecurityContextAsyncTaskExecutor(pool);
    }

    @Bean("jobExecutor")
    Executor jobExecutor(
            @Qualifier("rawAsyncPool") ThreadPoolTaskExecutor pool) {
        // Cho các lời gọi thủ công executor.execute(Runnable).
        return new DelegatingSecurityContextExecutor(pool);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // Chỉ là user demo. Không hard-code credential ở production.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("demo-password"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/async-identity")
                        .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**Điểm quan trọng của cấu hình:**

- **@EnableAsync** kích hoạt cơ chế xử lý phương thức @Async.
- **rawAsyncPool** là bean **ThreadPoolTaskExecutor** thật, nên Spring quản lý lifecycle. Ví dụ dùng **một worker** để test không rò context qua thread tái sử dụng; production phải điều chỉnh pool size, queue capacity, timeout, saturation/rejection policy theo tải thực.
- **securityContextExecutor** là AsyncTaskExecutor được bọc bởi **DelegatingSecurityContextAsyncTaskExecutor**, và được @Async gọi bằng tên rõ ràng.
- **jobExecutor** là wrapper **DelegatingSecurityContextExecutor** cho execute(Runnable) thủ công; hai wrapper dùng chung pool nhưng capture context độc lập theo từng task được submit qua chúng.
- **HTTP Basic** chỉ giúp có user demo mà không cần trang đăng nhập. Trong hệ thống thật có thể dùng form login/OIDC/JWT; ví dụ service chỉ dựa vào interface Authentication chung.
- **anyRequest().denyAll()** giúp demo chỉ công khai endpoint có chính sách xác thực rõ ràng; không sao chép chính sách vào ứng dụng thật mà không thiết kế các route.
- ThreadPoolTaskExecutor được khai báo riêng để container khởi tạo và shutdown; không tạo một ExecutorService không bao giờ đóng ở mỗi request.

Tệp **src/main/java/com/example/asyncsecurity/CurrentUserAsyncService.java**:

~~~java
package com.example.asyncsecurity;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class CurrentUserAsyncService {

    @Async("securityContextExecutor")
    public CompletableFuture<String> identity() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        String username = authentication == null
                ? "anonymous"
                : authentication.getName();

        String result = username + "@" + Thread.currentThread().getName();
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Mã trong phương thức **identity()** chạy trên **secured-async-...** nếu đi qua proxy Spring và bean executor được cấu hình như trên. Từ phương thức này, không dùng **CompletableFuture.supplyAsync(...)** không truyền executor khác để tạo một hop mới, vì hop đó có thể chạy trong **ForkJoinPool.commonPool()** và làm mất security context. Trả **completedFuture** là cách tương thích hợp đồng @Async khi thân method đã chạy ở worker.

Tệp **src/main/java/com/example/asyncsecurity/IdentityController.java**:

~~~java
package com.example.asyncsecurity;

import java.util.concurrent.CompletableFuture;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    private final CurrentUserAsyncService service;

    public IdentityController(CurrentUserAsyncService service) {
        this.service = service;
    }

    @GetMapping("/api/async-identity")
    public CompletableFuture<String> identity() {
        // Gọi qua bean @Service được Spring proxy, không gọi nội bộ this.
        return service.identity();
    }
}
~~~

Chạy ứng dụng trong dự án đã có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Thử request:

~~~bash
curl -i -u alice:demo-password \
  'http://localhost:8080/api/async-identity'
~~~

Khi cấu hình hoạt động, phản hồi **HTTP 200** có body bắt đầu bằng **alice@secured-async-**, ví dụ:

~~~text
alice@secured-async-1
~~~

Số thread cuối cùng không phải hợp đồng cố định. Request không có credential phù hợp sẽ không vào controller và thường nhận **HTTP 401** với HTTP Basic entry point. Không nên dùng credential demo này bên ngoài môi trường local.

**Lưu ý về security trong ví dụ:** Context được truyền sang worker chỉ giúp đọc danh tính của người đang gọi. Nếu identity service truy cập dữ liệu nhạy cảm, API vẫn cần authorization chi tiết theo role/scope và từng tài nguyên. Không tự xem “có Authentication” là đã có quyền với mọi object.

## 5. Test propagation và chống rò danh tính trong cùng thread pool

Nên test ít nhất hai chiều:

1. Khi caller có Authentication **alice**, worker đọc được **alice**.
2. Sau khi caller clear context, task tiếp theo trên **cùng thread pool** không được nhìn lại **alice**.

Trong ví dụ, pool có đúng một worker để tập trung kiểm tra việc **reuse** thread. Test không phụ thuộc tên thread đầy đủ ngoài prefix đã cấu hình. Vì ứng dụng có **@EnableAsync**, service injected vào test là Spring proxy, không phải object được tạo bằng **new CurrentUserAsyncService()**.

Tệp **src/test/java/com/example/asyncsecurity/AsyncSecurityContextTest.java**:

~~~java
package com.example.asyncsecurity;

import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class AsyncSecurityContextTest {

    @Autowired
    CurrentUserAsyncService service;

    @Autowired
    @Qualifier("jobExecutor")
    Executor jobExecutor;

    private static SecurityContext aliceContext() {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                        "alice",
                        "N/A",
                        List.of(new SimpleGrantedAuthority("ROLE_USER"))));
        return context;
    }

    @Test
    void asyncMethodCarriesIdentityAndNextTaskHasNoLeak()
            throws Exception {

        try {
            SecurityContextHolder.setContext(aliceContext());

            String first = service.identity().get(5, TimeUnit.SECONDS);
            assertThat(first).startsWith("alice@secured-async-");
        } finally {
            SecurityContextHolder.clearContext();
        }

        // Chính pool một worker sẽ được tái sử dụng.
        String second = service.identity().get(5, TimeUnit.SECONDS);
        assertThat(second).startsWith("anonymous@secured-async-");
    }

    @Test
    void manualExecutorPropagatesCallerContext() throws Exception {
        CompletableFuture<String> result = new CompletableFuture<>();

        try {
            SecurityContextHolder.setContext(aliceContext());
            jobExecutor.execute(() -> {
                Authentication a =
                        SecurityContextHolder.getContext().getAuthentication();
                result.complete(a == null ? "anonymous" : a.getName());
            });

            assertThat(result.get(5, TimeUnit.SECONDS)).isEqualTo("alice");
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests com.example.asyncsecurity.AsyncSecurityContextTest
~~~

Windows (ở PowerShell/cmd tại thư mục có Gradle wrapper):

~~~powershell
.\gradlew.bat test --tests com.example.asyncsecurity.AsyncSecurityContextTest
~~~

**Kỳ vọng** hai test hoàn tất không có assertion error với project Boot 3.x, Java 17+, Spring Security 6.x tương thích. Đây là kết quả dự kiến từ logic, không phải log đã chạy được xác nhận. Test thứ nhất xác minh đúng user **alice** được mang sang worker và không bị giữ cho task sau; test thứ hai xác minh **DelegatingSecurityContextExecutor** với execute(Runnable).

### Bổ sung các test quan trọng trước production

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Caller **alice**, caller **bob** submit đan xen | Worker nào chạy task của ai đều thấy đúng danh tính khi task bắt đầu |
| Task ném exception | SecurityContext trên thread pool vẫn được dọn, task tiếp theo không thừa hưởng user trước |
| Caller không có Authentication | Task không được tự xuất hiện principal cũ hoặc admin |
| Executor queue đầy | Rejection được xử lý đúng (không im lặng mất dữ liệu, không bỏ qua kiểm tra quyền) |
| Caller logout / bị khóa sau submit | Task còn queue không được phép bỏ qua chính sách quyền tại thời điểm xử lý |
| @Async từ method cùng bean | Không coi self-invocation là tác vụ async đã được proxy |
| Nested CompletableFuture hoặc một executor thứ hai | Mọi thread hop cần context policy riêng, không chỉ hop đầu |
| Ứng dụng nhiều node | Context gắn với task in-process, không tự vượt qua message broker hoặc JVM khác |
| HTTP Basic, form login, JWT, OIDC | Principal cụ thể có thể khác; test không phụ thuộc lớp Authentication |
| Security method annotations | Kiểm tra advisor/proxy order, vị trí đánh giá authorization và Principal mong đợi |

## 6. Những tình huống @Async dễ gặp lỗi

### 6.1. Quên @EnableAsync hoặc self-invocation

Khi một phương thức trong cùng object gọi **this.identity()**, lời gọi không đi qua Spring proxy nên **@Async không có hiệu lực** theo cơ chế proxy mặc định. Nó có thể chạy ngay trên servlet thread và vô tình trả đúng principal khiến developer tin rằng propagation đã thành công.

Sai:

~~~java
@Service
class ExampleService {
    public void handle() {
        identity(); // self-invocation: @Async có thể bị bỏ qua
    }

    @Async("securityContextExecutor")
    public CompletableFuture<String> identity() {
        // ...
        return CompletableFuture.completedFuture("...");
    }
}
~~~

Đây là **snippet rút gọn** để nêu anti-pattern, không phải file độc lập. Cách đúng là gọi **method public của bean khác qua Spring proxy** như IdentityController → CurrentUserAsyncService; hoặc tổ chức rõ bean được proxy thay vì gọi this.

**@Async không nên chỉ đặt trên private method** và kỳ vọng Spring proxy intercept được. Khi debug, kiểm tra thực sự có thread name **secured-async-...** chứ không chỉ xem kết quả principal.

### 6.2. Dùng nhầm executor mặc định

Nếu viết **@Async** không chỉ định bean, Spring có thể tìm executor mặc định được cấu hình qua AsyncConfigurer, một bean TaskExecutor hoặc tạo fallback tùy hoàn cảnh. Nếu executor được chọn không được bọc, worker mất security context.

Với bài này, chọn cách rõ ràng:

~~~java
@Async("securityContextExecutor")
public CompletableFuture<String> identity() {
    // ...
}
~~~

Hoặc, ở hệ thống lớn, định nghĩa **AsyncConfigurer** chỉ về wrapper mặc định để các method @Async không cần lặp tên, nhưng phải kiểm tra thực sự sử dụng đúng bean và không tạo vòng phụ thuộc. Không tạo nhiều wrapper trên các pool khác nhau một cách ngẫu nhiên.

### 6.3. Nested async và CompletableFuture

Một task nhận được context không có nghĩa mọi công việc **bên trong nó** đều giữ context nếu lại chuyển thread:

~~~text
Servlet thread (alice)
  → @Async("securityContextExecutor")  [alice có mặt]
      → CompletableFuture.supplyAsync(... commonPool) [không bảo đảm alice]
          → call another service [context có thể mất]
~~~

Nếu cần chuyển thêm hop, truyền một **Executor đã bọc context** cho hop đó. Tại thời điểm submit nested task, worker đang có context thích hợp nên wrapper có thể capture nó. Nếu dùng chung service context cố định, phải thiết kế phân quyền riêng cho service đó.

### 6.4. @Async không tự mang mọi ThreadLocal

SecurityContext propagation không có nghĩa các trạng thái sau tự đi theo:

- **RequestContextHolder**, HttpServletRequest, HttpSession;
- **MDC** phục vụ logging/correlation ID;
- **LocaleContextHolder**, timezone của request;
- **TransactionSynchronizationManager** và transaction Spring;
- tracing context hoặc những thread-local khác.

Đừng cố đọc **HttpServletRequest** hoặc entity gắn với transaction đã đóng từ worker sau request. Nếu cần correlation ID/MDC, cấu hình **TaskDecorator** hoặc context-propagation mechanism thích hợp và bảo đảm dọn dẹp trong finally. **Không dùng TaskDecorator để thay thế kiểm tra quyền**; SecurityContext wrapper giải quyết riêng việc truyền security context.

### 6.5. Xử lý exception, Future và cancellation

Với @Async trả **CompletableFuture**, lỗi trong task thường được biểu diễn bằng completion ngoại lệ; caller cần **handle/whenComplete/exceptionally** thích hợp thay vì mặc định “fire and forget” thành công. Với phương thức @Async trả **void**, lỗi có thể đi tới **AsyncUncaughtExceptionHandler**, cần cấu hình giám sát/logging phù hợp.

- Propagation wrapper vẫn phải cleanup context ngay cả khi task lỗi.
- Không ghi raw token, password hoặc thông tin nhạy cảm của Authentication vào exception log.
- Nếu task bị hủy/cancel hoặc queue full, bảo đảm side effect và audit của nghiệp vụ nhất quán; không coi việc submit thành công là công việc đã hoàn tất.
- Không gộp kiểm tra “task đã được đặt vào queue” với “nghiệp vụ đã được thực thi thành công”.

## 7. Ranh giới bảo mật: propagation không phải authorization

Cần phân biệt:

1. **Capture context** trả lời: task này được submit trong ngữ cảnh xác thực nào?
2. **Authorization** trả lời: principal đó **có quyền** thực hiện nghiệp vụ này không?
3. **Freshness/identity** trả lời: quyền, trạng thái tài khoản hoặc session còn hợp lệ **khi task thực thi** không?
4. **Audit** trả lời: ai yêu cầu tác vụ, tác vụ được thực hiện theo quyền nào, khi nào và trên tài nguyên nào?

Ví dụ người dùng alice có quyền xem đơn hàng tại lúc submit nhưng bị thu hồi quyền trước khi task chạy sau 30 phút. Một SecurityContext snapshot vẫn có thể chứa authorities cũ, nên không thể coi nó là nguồn quyền mới nhất. Với công việc kéo dài hoặc có side effect đáng kể, nên:

- Chuyển **requesterId/tenantId/jobId/operationId** như dữ liệu nghiệp vụ được kiểm soát, không persist cả SecurityContext.
- Ở thời điểm thực thi, tải lại **trạng thái người dùng/quyền/đối tượng** từ nguồn đáng tin và kiểm tra authorization theo chính sách.
- Khi tác vụ ở queue/message broker hoặc chạy trên JVM khác, thiết kế danh tính service và ủy quyền có phạm vi (on-behalf-of) rõ ràng; in-memory SecurityContext không tự serialize qua broker.
- Cần chứng minh danh tính/ủy quyền ở tầng gọi lẫn tầng worker khi nghiệp vụ rủi ro cao; không chỉ tin một chuỗi username do client gửi.
- Không lưu credentials/access token của user lâu dài trong Runnable hoặc message để “dùng lại” khi task chạy.

### @PreAuthorize và thread bất đồng bộ

Một method bảo vệ bằng **@PreAuthorize** có thể được gọi trong hoặc ngoài worker tùy cấu trúc bean/proxy và thứ tự advisor. Không mặc định rằng một annotation đặt cạnh @Async sẽ luôn được đánh giá tại thread mà bạn mong đợi. Nếu cần method security:

- Bật **@EnableMethodSecurity** một cách tường minh khi phù hợp.
- Đặt boundary kiểm tra quyền tại method/service rõ ràng, kiểm tra hành vi bằng integration test qua proxy thật.
- Xem xét các quy tắc ownership/tenant; một authority cũ trong SecurityContext không đủ để cấp quyền cho mọi tài nguyên.
- Nếu cần xác thực lại quyền ở thời điểm task chạy, gọi service policy có dữ liệu mới thay vì chỉ đọc authority snapshot.

## 8. So sánh các cách triển khai

| Cách làm | Context cho worker | Khi nào dùng |
| --- | --- | --- |
| **Executor** thuần | Không tự truyền SecurityContext | Tác vụ không phụ thuộc user, hoặc bạn quản lý context khác bằng cơ chế đáng tin |
| **DelegatingSecurityContextExecutor(delegate)** | Capture theo caller khi execute | Runnable submit thủ công nhân danh user |
| **DelegatingSecurityContextExecutor(delegate, fixedContext)** | Dùng một context tường minh | Service principal có phạm vi quyền cố định, không dùng để “nâng quyền” mọi user |
| **DelegatingSecurityContextAsyncTaskExecutor(delegate)** | Capture theo caller khi @Async/submit | Spring @Async, AsyncTaskExecutor |
| **MODE_INHERITABLETHREADLOCAL** | Có thể thừa kế khi tạo thread mới | Không phù hợp như cơ chế chính trên thread pool tái sử dụng |
| **TaskDecorator** tự xây | Phụ thuộc implementation | Propagation của MDC/tracing/context khác; cần cleanup an toàn |
| **Chỉ truyền requesterId/jobId** | Không tự tạo Authentication | Job dài hạn, queue ngoài JVM, cần kiểm quyền lại tại execution |

## 9. Troubleshooting nhanh

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách khắc phục |
| --- | --- | --- |
| Trong @Async, **getAuthentication() == null** | @Async chạy trong pool không bọc; thread boundary làm mất ThreadLocal | Dùng **DelegatingSecurityContextAsyncTaskExecutor** và chỉ định bean qua @Async |
| Vẫn thấy alice dù caller đã chuyển sang bob | ThreadLocal bị set thủ công mà quên clear; dùng context cố định sai mục đích | Dùng wrapper chuẩn, kiểm tra constructor, test reuse thread |
| Có principal nhưng thread name vẫn là http-nio... | Self-invocation hoặc chưa bật @EnableAsync; task không async thật | Gọi qua proxy bean khác và xác minh thread |
| @Async đôi khi chạy được, đôi khi không | Multiple executor beans, fallback khác nhau, annotation qualifier sai | Đặt tên và tiêm đúng AsyncTaskExecutor; kiểm tra cấu hình thực |
| Kiểm tra quyền trong worker sai role | Context capture quá sớm, quyền đã thay đổi, proxy/method security order | Thiết kế reauthorization ở lúc chạy, test với quyền thay đổi |
| Nested CompletableFuture mất context | Hop mới dùng commonPool / Executor không bọc | Dùng wrapper cho **từng thread hop** |
| Task async trả exception nhưng HTTP vẫn thành công | Controller chỉ submit, không chờ/quan sát Future | Định nghĩa contract phản hồi, quản lý Future và trạng thái job |
| Lỗi sau logout dù task đã submit | Context snapshot vẫn còn nhưng session/token không chắc còn hiệu lực | Tách identity snapshot với trạng thái authorization hiện tại |
| Không thấy MDC/correlation ID | Security wrapper chỉ xử lý SecurityContext | Bổ sung context propagation cho MDC/tracing riêng |
| Thread pool đầy / pending tasks vô hạn | Cấu hình queue/pool sai và không có backpressure | Giới hạn queue, timeout, rejection policy, giám sát executor |
| @Async chạy ở request dùng JWT/OIDC | Code giả định UsernamePasswordAuthenticationToken | Dùng interface Authentication chung, xét principal type theo thực tế |

## 10. Checklist đưa vào ứng dụng thật

- Xác định task nào chạy nhân danh người dùng hiện tại, task nào cần service principal, và task nào không nên nhận SecurityContext.
- Với @Async, có **@EnableAsync**, method được gọi **qua proxy** và executor bean **AsyncTaskExecutor đã bọc** với tên rõ ràng.
- Với execute(Runnable) thủ công, dùng **DelegatingSecurityContextExecutor**; với submit(Callable)/Future dùng wrapper tương ứng với loại Executor.
- Không bật **MODE_INHERITABLETHREADLOCAL** để chữa lỗi thread pool và không tự set SecurityContextHolder ở worker mà thiếu finally.
- Chỉ chọn fixed SecurityContext khi có lý do rõ ràng; không vô tình chạy task user dưới quyền admin.
- Test cả context propagation và **no leak** khi pool tái sử dụng thread, cả trường hợp caller anonymous, task lỗi, nhiều user đan xen.
- Không giả định SecurityContext propagation mang theo HTTP request, transaction, MDC hoặc mọi ThreadLocal.
- Không dựa vào context đã capture để thực hiện nghiệp vụ nhạy cảm sau hàng giờ; xác thực lại trạng thái, quyền, tenant và object tại execution.
- Không ghi hoặc lưu trữ lâu dài token/credentials. Quản lý vòng đời executor, queue capacity, shutdown và exception.
- Nếu task vượt JVM, dùng job identity và cơ chế ủy quyền được thiết kế riêng; SecurityContext trong ThreadLocal không tự chuyển qua message broker.
- Audit ghi tách **requestedBy** và **executedAs** khi tác vụ có service principal, kèm operation ID/tenant/resource ID.
- Kiểm tra đường HTTP thực, method-security proxy và kết quả Future trước khi kết luận propagation đã hoạt động.

**Kết luận:** Spring Security bảo vệ SecurityContext theo thread; bất đồng bộ phải chủ động xác định context của từng task. **DelegatingSecurityContextExecutor** là công cụ cho Runnable/Executor, còn **DelegatingSecurityContextAsyncTaskExecutor** thích hợp cho @Async. Wrapper cung cấp propagation và cleanup an toàn hơn việc tự truyền ThreadLocal, nhưng **không** thay authorization, kiểm tra quyền mới nhất hay quản trị tác vụ chạy lâu.
