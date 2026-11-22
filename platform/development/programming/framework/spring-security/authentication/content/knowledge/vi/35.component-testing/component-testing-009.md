# Kiểm thử ghi, đọc và dọn SecurityContext trong đúng mô hình thực thi

**SecurityContext** chứa `Authentication` và danh tính/quyền mà Spring Security đang dùng trong một luồng xử lý. Một câu nói như “context đã được set” có thể chỉ ba tình huống khác nhau: đặt context trên **ThreadLocal của Servlet thread**, lưu context vào **SecurityContextRepository** cho request tiếp theo, hoặc gắn nó vào **Reactor Context** của một subscription WebFlux. Nếu không phân biệt rõ các trường hợp này, bài kiểm thử có thể xanh nhưng production vẫn bị rò quyền giữa người dùng, mất đăng nhập sau redirect hoặc chạy task async bằng danh tính không đúng.

Mục tiêu là kiểm thử vòng đời **ghi → đọc → dọn** theo đúng mô hình thực thi: Java unit test, Spring MVC/Servlet filter chain, session persistence, thread pool/async và WebFlux. Ví dụ dùng Java 17+, Spring Security hiện đại, JUnit 5 và phân biệt rõ chương trình độc lập với mảnh mã yêu cầu Spring Boot.

**Bất biến an toàn:** Một request của Alice không được khiến request hoặc task không liên quan của Bob đọc nhầm `Authentication` của Alice. Khi kết thúc phạm vi do một component sở hữu, nó phải dọn/khôi phục context đúng cách; nếu cần duy trì login sang request khác, phải dựa vào repository/token hợp lệ, không dựa vào ThreadLocal còn sót.

## 1. Các khái niệm cần phân biệt

| Thành phần | Vai trò | Bài test cần khẳng định |
| --- | --- | --- |
| `Authentication` | Principal, authorities, credentials, trạng thái xác thực | Đúng người/dịch vụ, đúng quyền |
| `SecurityContext` | Container chứa `Authentication` | Authentication đúng thời điểm |
| `SecurityContextHolder` | API truy cập context hiện hành | Đọc đúng trong thread/strategy |
| `SecurityContextHolderStrategy` | Cơ chế lưu context của holder | Mặc định Servlet thường là ThreadLocal |
| `SecurityContextRepository` | Lưu/tải context qua requests/dispatch | Request kế tiếp có/không mang session auth đúng mong đợi |
| `SecurityContextHolderFilter` | Nạp context cho Servlet request và dọn thread boundary | Không rò sang request khác dùng lại thread |
| `TestSecurityContextHolder` | Công cụ Spring Security Test | Fixture và cleanup của test đúng |
| `ReactiveSecurityContextHolder` | Đọc/gắn context qua Reactor Context | Không phụ thuộc JUnit/event-loop thread |

Một SecurityContext trống có thể tồn tại:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
// authentication có thể là null dù context != null.
~~~

Do đó đừng viết test `assertNull(SecurityContextHolder.getContext())` sau cleanup. Holder có thể tạo context mới rỗng khi gọi `getContext()`. Kiểm `getAuthentication() == null` hoặc kiểm rằng request vô danh không được truy cập protected endpoint.

Ngoài ra, `AnonymousAuthenticationFilter` có thể tạo `AnonymousAuthenticationToken` cho request chưa login. Việc có `Authentication` với `isAuthenticated() == true` **không nhất thiết** chứng minh user đã login tương tác. Hãy dùng authorization framework hoặc `AuthenticationTrustResolver` khi cần phân biệt anonymous/remember-me/fully-authenticated.

## 2. Chọn chiến lược test theo mô hình thực thi

| Môi trường | Nơi lưu context | Công cụ kiểm thử | Lúc dọn |
| --- | --- | --- | --- |
| Service Java đồng bộ | `SecurityContextHolder` / ThreadLocal | JUnit + createEmptyContext/setContext | finally, @AfterEach |
| Spring MVC Servlet request | Thread context do filter chain quản lý | MockMvc + Spring Security filters | Cuối chain, kể cả lỗi |
| Spring Security Test fixture | TestSecurityContextHolder/test thread | @WithMockUser / @WithSecurityContext | TestExecutionListener |
| Executor/worker | ThreadLocal ở worker, khác caller | DelegatingSecurityContextExecutor / Runnable | Wrapper finally trên worker |
| WebFlux/reactive | Reactor Context của subscription | StepVerifier + ReactiveSecurityContextHolder | Kết thúc/hủy subscription |
| HTTP WebFlux | SecurityWebFilterChain | WebTestClient + mockUser | Mỗi exchange |
| Full HTTP qua TCP | Context ở server thread, không ở JUnit thread | Login thật/cookie/token | Lifecycle server và session/token |

Không chuyển nguyên logic `SecurityContextHolder.setContext()` từ Servlet sang WebFlux. Trong reactive, các operators có thể đổi thread và context thuộc subscription. Ngược lại, trong Servlet thông thường, Reactor Context không tự truyền Authentication cho một executor bạn tạo.

## 3. Vòng đời SecurityContext trong Servlet

Luồng tổng quát:

~~~text
HTTP request
     |
     v
SecurityFilterChain
     |
     +-- SecurityContextHolderFilter nạp context từ repository
     +-- Authentication filter kiểm credential, tạo Authentication
     +-- Authorization đọc Authentication/authorities
     +-- Controller/Service đọc principal trong request
     |
     v
Filter chain hoàn tất hoặc ném lỗi
     |
     v
Framework dọn context khỏi thread Servlet
     |
     v
Thread quay lại pool, không giữ identity của request cũ
~~~

**Dọn ThreadLocal** và **lưu session** là hai việc khác nhau. Dọn context cuối request ngăn rò Alice → Bob. Nếu Alice đã đăng nhập bằng session, request kế tiếp của Alice phải **được tải lại** từ repository khi cookie/session hợp lệ, không phải nhờ context sống qua hai requests.

Trong Spring Security 6.x, `SecurityContextHolderFilter` được dùng mặc định để nạp context, nhưng không tự lưu context thay đổi. Khi custom authentication flow muốn lưu session, phải gọi explicit save sau xác minh:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);

SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(
        context, httpServletRequest, httpServletResponse);
~~~

Đây là **mảnh mã Servlet**, trong đó `verifiedAuthentication` chỉ được tạo sau khi provider đã xác thực credential; repository phải là repository thực mà chain sử dụng. Lưu trước khi response redirect/commit. Với `SecurityContextPersistenceFilter` (cách cũ), semantics save tự động có khác; hãy kiểm đúng phiên bản và filter chain.

**Không gọi saveContext cho mọi request stateless.** Nếu API dùng Bearer token và `NullSecurityContextRepository`, hệ thống thường xác thực lại token trên mỗi request. Test kỳ vọng request tiếp theo không token phải bị từ chối.

## 4. Tạo context mới thay vì sửa context có thể chia sẻ

Đọc Authentication:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication == null) {
    throw new IllegalStateException("No Authentication");
}

String principal = authentication.getName();
~~~

Đoạn này chưa xử lý anonymous semantics; code application nên dựa vào SecurityFilterChain và policy authorization.

Khi cần ghi Authentication đã xác minh, ưu tiên:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
~~~

Không mặc định sửa trực tiếp object có thể đang được shared:

~~~java
// Dễ tạo shared mutable state khi context đến từ repository:
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

Một SecurityContext được tải từ session có thể có nhiều references, đặc biệt ở concurrent requests. Tạo context mới giảm nguy cơ request này chỉnh Authentication mà request khác đang dùng.

## 5. JUnit 5: set, read, clear trong cùng thread

Tệp **SecurityContextHolderLifecycleTest.java** (Spring Security Core + JUnit 5):

~~~java
package demo.security;

import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.*;

class SecurityContextHolderLifecycleTest {

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void setReadAndClearOnCurrentThread() {
        assertNull(SecurityContextHolder.getContext().getAuthentication());

        Authentication verified = new UsernamePasswordAuthenticationToken(
                "alice", null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));

        SecurityContext next = SecurityContextHolder.createEmptyContext();
        next.setAuthentication(verified);
        SecurityContextHolder.setContext(next);

        assertSame(verified,
                SecurityContextHolder.getContext().getAuthentication());
        assertEquals("alice",
                SecurityContextHolder.getContext().getAuthentication().getName());

        SecurityContextHolder.clearContext();
        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }

    @Test
    void anotherTestDoesNotInheritAuthentication() {
        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }
}
~~~

Đây là test Spring Core **không có HTTP hoặc database**. Nó chứng minh ghi/đọc/clear trên **thread hiện tại**, không chứng minh credential Alice là thật hay đã lưu session. Constructor `UsernamePasswordAuthenticationToken` với ba đối số đánh dấu authenticated; trong bài test đó là fixture đáng tin, **không dùng làm đường tắt production để đánh dấu username client gửi là đã xác thực**.

Cleanup `@AfterEach` bảo vệ khi một assertion ném lỗi. Nhưng nó chỉ dọn **test thread**; nếu test tạo worker thread khác, phải kiểm và cleanup tại worker đó.

## 6. Ownership: clear hay restore context?

Một component tạm thay context trong một thread đã có owner có thể cần **khôi phục** context cũ:

~~~java
SecurityContext previous = SecurityContextHolder.getContext();
SecurityContext temporary = SecurityContextHolder.createEmptyContext();
temporary.setAuthentication(delegatedAuthentication);

try {
    SecurityContextHolder.setContext(temporary);
    doTemporaryWork();
} finally {
    SecurityContextHolder.setContext(previous);
}
~~~

Đây là mảnh code; `delegatedAuthentication` và `doTemporaryWork()` thuộc ứng dụng. Chỉ sử dụng khi đã xác định chính sách ủy quyền và ownership cho việc impersonation/delegation.

Khi một test/worker tự sở hữu context từ đầu tới cuối, thường cần **clear**:

~~~java
try {
    SecurityContextHolder.setContext(contextForThisOperation);
    doWork();
} finally {
    SecurityContextHolder.clearContext();
}
~~~

Nếu `doWork()` ném exception, `finally` vẫn chạy. Không chỉ clear trong success branch.

**Đừng gọi clear ở cuối mỗi phương thức service Servlet thông thường**: filter/controller khác trong cùng request vẫn có thể cần context. Boundary do framework quản lý thì framework làm cleanup; code tự set context ngoài framework phải thực hiện cleanup theo contract.

## 7. Java 17 chạy độc lập: mô phỏng ThreadLocal trong thread pool

Tệp **ThreadLocalSecurityBoundaryDemo.java** chạy không cần Spring; nó mô phỏng nguy cơ dùng lại cùng worker thread. Đây **không phải SecurityContextHolder**, mà là bài lab về cleanup `ThreadLocal`.

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalSecurityBoundaryDemo {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private static void runAs(String principal) {
        try {
            CURRENT.set(principal);
            System.out.println("Scoped " + principal + " = " + CURRENT.get());
        } finally {
            CURRENT.remove();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<?> alice = pool.submit(() -> runAs("alice"));
            alice.get();

            String afterAlice = pool.submit(CURRENT::get).get();
            System.out.println("After alice = " + afterAlice);

            Future<?> bob = pool.submit(() -> runAs("bob"));
            bob.get();

            String afterBob = pool.submit(CURRENT::get).get();
            System.out.println("After bob = " + afterBob);

            System.out.println("Main thread = " + CURRENT.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~bash
javac ThreadLocalSecurityBoundaryDemo.java
java ThreadLocalSecurityBoundaryDemo
~~~

Stdout chính xác:

~~~text
Scoped alice = alice
After alice = null
Scoped bob = bob
After bob = null
Main thread = null
~~~

`newSingleThreadExecutor()` tái sử dụng worker, còn `Future.get()` giữ thứ tự output. Nếu bỏ `CURRENT.remove()`, task không có principal chạy sau có thể đọc Alice hoặc Bob. Trong Spring Security, dùng APIs holder/wrapper chính thức, không tự xây một ThreadLocal riêng cho danh tính production.

## 8. Test Servlet qua MockMvc, không chỉ gọi controller

Muốn kiểm filter chain thật, dùng MockMvc có Spring Security filters. Ví dụ controller Spring MVC:

~~~java
package demo.security;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class IdentityController {
    @GetMapping("/whoami")
    String whoAmI(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Đây là class của Spring Boot Servlet, cần SecurityFilterChain bảo vệ `/whoami`. Cấu hình minh họa:

~~~java
@Bean
SecurityFilterChain chain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/whoami").authenticated()
                    .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Đây là mảnh cấu hình cần Spring Boot, imports và test user phù hợp.

Tệp **IdentityControllerSecurityTest.java**:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class IdentityControllerSecurityTest {

    @Autowired MockMvc mvc;

    @Test
    void authenticatedRequestDoesNotAuthenticateNextAnonymousRequest()
            throws Exception {

        mvc.perform(get("/whoami").with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));

        mvc.perform(get("/whoami"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

`with(user(...))` đặt user test vào request, **không cần Alice tồn tại trong database**. Filter chain phải thực sự chạy: `@AutoConfigureMockMvc` trong Spring Boot thông thường gắn security filters; với `MockMvcBuilders.standaloneSetup(...)` phải thêm `apply(springSecurity())` hoặc FilterChainProxy theo đúng cấu hình.

Bài test trên dùng HTTP Basic entry point nên request vô danh thường 401. Với formLogin, browser có thể được 302 tới trang login. Điều cốt lõi là request thứ hai không được coi là Alice, không phải luôn trả một status cứng cho mọi app.

## 9. @WithMockUser, @WithSecurityContext và TestSecurityContextHolder

Spring Security Test có thể seed test context bằng annotation:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void methodCanReadMockAuthentication() {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

    assertEquals("alice", auth.getName());
    assertTrue(auth.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_USER")));
}
~~~

Đây là **mảnh test** cần JUnit 5, Spring Security Test và test context. `@WithMockUser` không xác minh password thật; `roles="USER"` tạo authority `ROLE_USER`. Nếu cần `UserDetails` từ service, dùng `@WithUserDetails`; nếu cần custom principal, dùng `@WithSecurityContext` và factory.

Khi Spring Security TestExecutionListener tạo context trước test, framework cũng dọn sau test. **Không dùng việc holder của JUnit test thread còn Alice giữa hai lệnh MockMvc trong cùng một test có annotation để kết luận có leak**: có thể đó là fixture do test framework quản lý.

Với setup thủ công:

~~~java
SecurityContext ctx = SecurityContextHolder.createEmptyContext();
ctx.setAuthentication(testAuthentication);
TestSecurityContextHolder.setContext(ctx);

// Khi cần đưa vào MockMvc request: .with(testSecurityContext())

TestSecurityContextHolder.clearContext();
~~~

Đây là mảnh mã; `testAuthentication` từ test fixture, `testSecurityContext()` là helper Spring Security Test. Đừng clear fixture trước lúc request cần nó.

**Full HTTP qua mạng thật:** annotation trên JUnit thread không tự đi qua TCP sang server ở thread/process khác. Nếu dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` với real HTTP client, phải gửi Basic/Bearer token, session cookie hoặc login hợp lệ để xác thực request.

## 10. Test persistence là test khác với test holder

Chỉ làm:

~~~java
SecurityContextHolder.setContext(context);
assertNotNull(SecurityContextHolder.getContext().getAuthentication());
~~~

không chứng minh request kế tiếp được xác thực. Với stateful session, phải có:

~~~text
Request A: Login
    verify credential
    set context trong holder
    saveContext qua repository
    response Set-Cookie/redirect

Request B: GET /dashboard với cùng session hợp lệ
    filter load context từ repository
    controller nhận đúng principal
    filter clear thread sau request

Request C: GET /dashboard không session/token
    không nhận principal của A
~~~

Các repository:

| Repository | Semantics | Kiểm thử |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Context liên kết HttpSession | Request B cùng session thấy Authentication |
| `RequestAttributeSecurityContextRepository` | Context theo request qua một số dispatch | Không tạo session login lâu dài |
| `DelegatingSecurityContextRepository` | Kết hợp nhiều nơi lưu/tải | Đúng thứ tự repository và ngữ cảnh |
| `NullSecurityContextRepository` | Không persist auth qua request | Không token/session thì request mới anonymous |

Unit test custom auth filter có thể mock repo để verify `saveContext(...)`:

~~~java
verify(repository).saveContext(
        argThat(ctx -> ctx.getAuthentication() != null
                && "alice".equals(ctx.getAuthentication().getName())),
        same(request),
        same(response));
~~~

Đây là **mảnh Mockito**, không phải class JUnit độc lập. Nó kiểm API save đã được gọi, không chứng minh HttpSession cookie hoạt động. Integration test phải lấy cookie/session từ login response rồi request lại, và xác nhận logout/invalid session không còn quyền.

Nếu chỉ gọi `SecurityContextHolder.clearContext()` khi logout nhưng HttpSession vẫn giữ Authentication, request kế tiếp có thể lại tải context đó. Dùng Spring Security logout handlers/DSL để clear và invalidate session/repository theo policy. Với Bearer token stateless, xóa HttpSession không mặc nhiên revoke token.

## 11. Thread pool khác Servlet thread

Servlet request có ThreadLocal Alice:

~~~text
Request thread có Alice
       |
       +---- executor.submit(task)
                         |
                         v
                  Worker thread riêng
                  ThreadLocal không tự có Alice
~~~

Khi task chuyển sang một thread khác, Spring Security không mặc định truyền `SecurityContextHolder` qua mọi executor do ứng dụng tạo. Nếu worker từng bị một tác vụ cũ làm bẩn và không cleanup, task mới có thể nhìn thấy một principal **không liên quan**.

**Không dùng MODE_INHERITABLETHREADLOCAL để sửa mọi thread pool.** Inherited context chỉ có ý nghĩa vào lúc thread được tạo; pooled threads sống lâu và có thể giữ danh tính stale. `MODE_GLOBAL` càng không thích hợp cho web server đa người dùng.

Spring Security cung cấp:

- `DelegatingSecurityContextRunnable` / `DelegatingSecurityContextCallable`;
- `DelegatingSecurityContextExecutor` / `DelegatingSecurityContextExecutorService`;
- `DelegatingSecurityContextAsyncTaskExecutor` cho một số Spring `@Async` setups.

Wrapper đặt context đúng cho task, rồi restore/clear sau khi task kết thúc. Quan trọng: việc propagation xảy ra theo **thời điểm submit** hoặc context cụ thể được truyền khi cấu hình, tùy constructor; phải biết chính xác ai được ủy quyền thực thi background task.

## 12. JUnit kiểm propagation và dọn context trên worker

Test này dùng một backing thread để chắc rằng task kế tiếp có thể chứng minh cleanup của task trước.

Tệp **DelegatingExecutorSecurityTest.java**:

~~~java
package demo.security;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.*;

class DelegatingExecutorSecurityTest {

    @AfterEach
    void cleanupCaller() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void propagatesToTaskAndCleansBackingThread() throws Exception {
        ExecutorService backing = Executors.newSingleThreadExecutor();
        try {
            Authentication alice = new UsernamePasswordAuthenticationToken(
                    "alice", null, List.of());
            SecurityContext ctx = SecurityContextHolder.createEmptyContext();
            ctx.setAuthentication(alice);
            SecurityContextHolder.setContext(ctx);

            var wrapped = new DelegatingSecurityContextExecutor(backing);
            var observed = new java.util.concurrent.CompletableFuture<String>();

            wrapped.execute(() -> {
                Authentication inside =
                        SecurityContextHolder.getContext().getAuthentication();
                observed.complete(inside.getName());
            });

            assertEquals("alice", observed.get(3, TimeUnit.SECONDS));

            // Không qua wrapper: task sau không được nhận Alice.
            Future<Authentication> next = backing.submit(() ->
                    SecurityContextHolder.getContext().getAuthentication());
            assertNull(next.get(3, TimeUnit.SECONDS));
        } finally {
            backing.shutdownNow();
        }
    }
}
~~~

Đây là test Spring Security Core/JUnit 5. Với một worker duy nhất, tác vụ thứ hai chỉ chạy sau khi wrapper task đầu kết thúc và cleanup. Dùng pool nhiều workers mà không xác minh hai tác vụ chạy trên **cùng thread** thì test cleanup có thể pass sai.

Thêm test khi delegate ném exception: xác nhận wrapper vẫn dọn context. Nếu bắt lỗi trong task, không được vô tình che thất bại hoặc bỏ qua `Future.get()` của một task lỗi.

Không tạo một executor mới cho mỗi HTTP request trong production; quản lý executor chung và wrapper qua lifecycle của Spring.

## 13. @Async, Callable, CompletableFuture: kiểm cơ chế tích hợp thật

| Cách chạy | Mức hỗ trợ cần xác minh |
| --- | --- |
| Spring MVC `Callable` được framework hỗ trợ | Spring Security có tích hợp async; kiểm propagation và dispatch |
| Servlet `AsyncContext.start(Runnable)` qua framework | Kiểm context khi callback chạy và cleanup |
| `@Async` dùng TaskExecutor riêng | Cấu hình/decorate executor để mang context theo policy |
| `CompletableFuture.supplyAsync` common pool | Không tự có Servlet ThreadLocal |
| Raw Thread | Không mặc định có Authentication đúng |
| Background queue / scheduled task | Dùng service/workload identity hoặc delegation có kiểm soát, không thừa user gần nhất |

Không mù quáng copy principal của HTTP request sang job dài hạn: user có thể logout hoặc mất quyền khi job bắt đầu chạy. Nếu job hành động thay mặt user, cần policy ủy quyền rõ, giới hạn thời hạn, scope, tenant và kiểm lại resource khi cần.

Một test của `@Async` cần assert **bên trong task** rằng principal đúng, sau task phải kiểm pool worker không còn principal. Chỉ assert trên caller thread là không đủ.

## 14. Reactor/WebFlux: đọc SecurityContext trong subscription

WebFlux không nên dùng `SecurityContextHolder.getContext()` trong một reactive service để suy user. Reactor Context gắn với chuỗi Publisher/subscription, không nhất thiết với một thread.

Mảnh code:

~~~java
Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .defaultIfEmpty("anonymous");
}
~~~

Đưa context vào chuỗi trong test:

~~~java
Authentication alice = new UsernamePasswordAuthenticationToken(
        "alice", null, List.of());

Mono<String> result = currentPrincipalName()
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice));

StepVerifier.create(result)
        .expectNext("alice")
        .verifyComplete();
~~~

Đây là mảnh code dùng Reactor + Spring Security Reactive + reactor-test; cần imports trong class test. Không set ThreadLocal của JUnit thread để giả lập Reactor identity.

### JUnit test WebFlux context isolation

Tệp **ReactiveSecurityContextBoundaryTest.java**:

~~~java
package demo.security;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveSecurityContextBoundaryTest {

    private Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .defaultIfEmpty("anonymous");
    }

    @Test
    void contextsAreScopedToReactiveSubscriptions() {
        Authentication alice = new UsernamePasswordAuthenticationToken(
                "alice", null, List.of());
        Authentication bob = new UsernamePasswordAuthenticationToken(
                "bob", null, List.of());

        StepVerifier.create(currentName().contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)))
                .expectNext("alice")
                .verifyComplete();

        StepVerifier.create(currentName().contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(bob)))
                .expectNext("bob")
                .verifyComplete();

        StepVerifier.create(currentName())
                .expectNext("anonymous")
                .verifyComplete();
    }
}
~~~

Đây là JUnit test trong dự án có spring-security-core, reactor-core, reactor-test. Nó kiểm ba subscriptions độc lập, **không** kiểm filter chain hoặc validation của token WebFlux.

Trong Reactor, không gọi `SecurityContextHolder.clearContext()` ở cuối mỗi operator để “dọn” reactive identity: đó là thao tác lên ThreadLocal khác. Context thường gắn với lifecycle subscription. Với error/cancel, test các side effects và context propagation đúng của framework; đừng giữ mutable per-user context trong singleton.

Không dùng `block()` trong WebFlux request event loop để đọc Authentication, vì có thể block thread hoặc phá vỡ mô hình composition. Hãy tiếp tục với `Mono/Flux`.

## 15. WebTestClient kiểm request reactive

Với WebFlux controller bảo vệ `GET /whoami`, setup:

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .apply(SecurityMockServerConfigurers.springSecurity())
        .configureClient()
        .build();
~~~

Mảnh này cần Spring reactive ApplicationContext và WebTestClient. Dùng test mutator:

~~~java
client.mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/whoami")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("alice");

client.get().uri("/whoami")
        .exchange()
        .expectStatus().isUnauthorized();
~~~

`mockUser` ở đây là API `SecurityMockServerConfigurers.mockUser` của WebFlux, không phải `SecurityMockMvcRequestPostProcessors.user` của Servlet. Status 401 kỳ vọng khi SecurityWebFilterChain dùng HTTP Basic hoặc entry point 401; với form login có thể redirect.

Đây là kiểm **hai exchanges**, không chứng minh WebSession persistence. Nếu muốn kiểm user session, phải gửi cookie do server cấp giữa exchanges và kiểm `ServerSecurityContextRepository`/WebSession theo thiết kế.

**Full HTTP thực:** việc thêm `@WithMockUser` trên JUnit thread không chứng minh request qua mạng tới server đã được xác thực; phải gửi credential/cookie thật hoặc test qua WebTestClient với mock security support được tích hợp đúng.

## 16. Async error, cancel và test isolation

Một hệ thống thường có nhiều ranh giới lỗi:

- Servlet controller ném RuntimeException;
- AuthenticationProvider ném AuthenticationException;
- Filter trả response 401/403 và không gọi controller;
- Worker future ném exception trước khi hoàn thành;
- Reactive Mono/Flux phát error hoặc client hủy subscription;
- Request dispatch ERROR/ASYNC chạy ở thời điểm khác.

Cần kiểm không rò context sau **mọi đường kết thúc**. Với Servlet chain, framework filter/holder strategy phải dọn; với worker tự set, wrapper/finally dọn; với Reactor, Context thuộc subscription và resource cleanup tuân theo framework.

Đừng kiểm `getContext() == null` trên thread JUnit rồi suy context của servlet worker/Netty event loop đã dọn. Phải đo ở **chính boundary thực thi**. Với reusable worker, dùng single-thread executor hoặc test instrumentation để so sánh cùng thread.

Cũng không nên tắt toàn bộ parallel test execution để che rò static holder configuration. Nếu test thay đổi `SecurityContextHolder.setStrategyName()`, nên cô lập environment và khôi phục đúng strategy vì đây là cấu hình global cho JVM.

## 17. Method Security, authorities và kiểm resource

Một test `@WithMockUser(roles="ADMIN")` có thể giúp kiểm authorization của method được proxy bởi Spring. Nhưng phải bật method security, gọi qua Spring bean/proxy, không dùng `new Service()` hoặc self-invocation bypass proxy.

Bộ test cần:

1. User có role hợp lệ được phép gọi.
2. User thiếu quyền bị từ chối (thường `AccessDeniedException` hoặc web 403).
3. Anonymous không tự được coi là user đã login.
4. Authorities không bị sửa bởi concurrent requests.
5. Context trong async method đến từ đúng caller/policy.
6. Reactive method security dùng Reactor Context và Publisher API phù hợp.

Một thành công của test `@WithMockUser` chỉ chứng minh đường **authorization dưới mock Authentication**, không chứng minh password/OIDC/SAML đã được xác thực thực tế.

## 18. Test matrix cho ba mô hình

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Unit set Alice lên holder | Đọc Alice trên cùng thread |
| Sau clearContext | Authentication null trong context mới |
| Exception trước cleanup | finally/@AfterEach vẫn dọn |
| MockMvc request Alice | Controller thấy Alice |
| MockMvc request anonymous tiếp theo | Không thấy Alice |
| Stateful login + session cookie hợp lệ | Request khác tải lại Alice từ repository |
| Stateless API request không token | Không được giữ Authentication request trước |
| Custom login filter chỉ set holder không save | Không tự có persistence trên request kế |
| Logout session | Cookie/session cũ không cấp quyền |
| Thread pool task Alice rồi task không wrapper | Task sau không thấy Alice |
| DelegatingSecurityContextExecutor | Task được nhận context ở thời điểm submit |
| Task được bọc ném exception | Worker được dọn |
| Thread pool nhiều workers | Không suy “same thread” nếu chưa xác minh |
| @WithMockUser fixture | Test listener cleanup đúng lifecycle |
| Real HTTP với @WithMockUser | Không tự mang mock user qua TCP |
| WebFlux Alice/Bob/anonymous subscriptions | Không lẫn identity |
| Reactor error/cancel | Không đưa principal sang subscription khác |
| Method security với @PreAuthorize | Kiểm đúng authorities trên Spring proxy |
| Concurrent requests cùng session | Tránh sửa shared mutable context |
| Cookie/request sau session rotation | Identity đúng account, không lấy user cũ |

Đừng chỉ test “SecurityContext != null”. Test tốt phải trả lời **ai**, **ở đâu**, **khi nào**, **có lưu cho request khác không**, và **đã dọn sau khi hoàn thành chưa**.

## 19. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Sửa |
| --- | --- | --- |
| Test riêng pass, suite fail | Context test trước chưa clear | @AfterEach, TestSecurityContextHolder cleanup |
| Bob thấy Authentication của Alice | Thread pool không cleanup | finally/wrapper ở worker boundary |
| Worker async không thấy principal | Không có propagation | DelegatingSecurityContextExecutor/AsyncTaskExecutor |
| MODE_INHERITABLETHREADLOCAL sai user | Pool tái sử dụng thread cũ | Không dùng inheritance làm propagation cho pool |
| Login success, request kế anonymous | Quên saveContext | Explicit save trước response commit |
| API stateless giữ auth request sau | Session/repository không đúng policy | Dùng per-request credential, repo phù hợp |
| Logout nhưng vẫn đăng nhập | Chỉ clear ThreadLocal | Clear repository/invalidate session hoặc revoke token |
| MockMvc giả lập auth nhưng filter chain không chạy | Thiếu springSecurity() | Gắn FilterChainProxy |
| @WithMockUser không có tác dụng với real HTTP | Server thread khác JUnit thread | Gửi HTTP credentials/cookie |
| Test role USER không có quyền | roles() tạo ROLE_USER | Chọn hasRole/hasAuthority đúng |
| assertNull(getContext()) fail | Holder tạo empty context | Assert Authentication null |
| Reactive không thấy principal | Đọc ThreadLocal | Dùng ReactiveSecurityContextHolder |
| block() làm nghẽn WebFlux | Chặn event-loop | Compose Mono/Flux |
| Anonymous token bị coi là login thật | Hiểu sai isAuthenticated | TrustResolver/authorization framework |
| Shared SecurityContext bị sửa chéo | Mutable object từ session bị chia sẻ | createEmptyContext và quản lý concurrency |
| Context leak chỉ xuất hiện khi lỗi | Cleanup không ở finally | Test exception/error/cancel |

## 20. Checklist triển khai

1. Đã xác định code chạy trong Servlet thread, executor worker, WebFlux subscription hay test HTTP thực?
2. Authentication đến từ provider thật, mock fixture, session hay Bearer token?
3. Có tạo context mới rồi ghi vào đúng holder/Reactor Context không?
4. Test kiểm principal và authorities, không chỉ object context tồn tại?
5. Cleanup diễn ra ở đúng boundary kể cả exception/cancel?
6. Nếu truyền sang executor, wrapper chạy ở đúng thời điểm và worker được dọn sau task?
7. Nếu cần session, có explicit save qua SecurityContextRepository và test request kế tiếp?
8. Nếu stateless, request thiếu token có bị từ chối?
9. MockMvc/WebTestClient có gắn security filters/WebFilterChain thật?
10. Có test Alice → Bob → anonymous, logout, session rotation và concurrent access?
11. Không leak credentials trong logs, test fixture hoặc object shared?
12. Phiên bản SecurityContextHolderFilter và cách test đang dùng có khớp dependency thực tế?

**Kết luận:** Kiểm thử SecurityContext đúng không phải chỉ có `setContext` và `getContext`. Với Servlet, context được gắn vào request thread rồi dọn, persistence qua repository là việc khác. Với executor, cần propagation và cleanup ở worker. Với WebFlux, context thuộc Reactor subscription. Phân biệt và kiểm thử riêng các ranh giới này giúp tránh hai lỗi đối nghịch: **mất Authentication hợp lệ** và **rò danh tính giữa các tác vụ/người dùng**.

### Tài liệu tham khảo

- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Persisting Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security — Session Management / Require Explicit Save: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Concurrency Support: https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html
- Spring Security — MockMvc Testing Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — TestSecurityContextHolder API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/TestSecurityContextHolder.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — WebTestClient Authentication: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Security — WebTestClient Setup: https://docs.spring.io/spring-security/reference/7.0/reactive/test/web/setup.html
