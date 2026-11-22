# Kiểm thử song song và xác nhận không rò rỉ danh tính giữa người dùng

## 1. Mục tiêu và bối cảnh

Đăng nhập thành công trong một request không chứng minh rằng hệ thống an toàn khi **nhiều người cùng đăng nhập hoặc gửi request đồng thời**. Một dịch vụ Java thường xử lý hàng trăm request trên một nhóm thread, giữ session cho nhiều browser, gọi tác vụ `@Async`, gửi message hoặc sử dụng Reactor trong WebFlux. Nếu danh tính người dùng bị lưu ở **biến dùng chung**, `ThreadLocal` không được dọn, `SecurityContext` dùng chung hoặc cache phân quyền sai khóa, request của người A có thể nhìn thấy `principal`, dữ liệu hoặc quyền của người B.

Bài Knowledge này tập trung vào **kiểm thử đăng nhập song song và cách ly danh tính** trong Spring Security. Sau bài học, bạn có thể:

1. Diễn đạt và kiểm thử invariant **“request nào thuộc tài khoản nào thì dùng đúng identity/authorities của tài khoản đó”**.
2. Phân biệt leak ở **thread**, **session/cookie**, **HTTP cache**, **authorization dữ liệu**, **async task** và **reactive context**.
3. Hiểu cách Spring Security Servlet dùng `SecurityContextHolder`, `SecurityContext`, `Authentication`, `SecurityContextRepository` và cơ chế dọn context.
4. Viết chương trình Java 17 và JUnit 5 kiểm thử song song bằng `ExecutorService`, `CountDownLatch`, `CyclicBarrier` và `Future` **không phụ thuộc sleep tùy tiện**.
5. Xây dựng một Spring Boot 3.x + Spring Security 6.x demo có hai/ba user, chạy **HTTP requests thực sự song song** và assert đúng principal, authorities, 401/403.
6. Thiết kế kiểm thử session-form-login với **cookie jars tách biệt**, CSRF và session fixation protection; không nhầm giới hạn session cùng account với cách ly hai account.
7. Kiểm thử `@Async`, `DelegatingSecurityContextCallable`/executor và Reactive `ReactiveSecurityContextHolder`, không sao chép `SecurityContext` của người A cho người B.
8. Tạo ma trận regression tests cho tenant/data ownership, logout, Bearer token, role thay đổi và hệ thống nhiều node.

**Phạm vi:** trọng tâm Spring Security 6.5 / Spring Boot 3.x, Java 17+ cho Servlet Spring MVC; có phân biệt Spring Security 7.x và WebFlux. Ví dụ thành phần được đánh dấu rõ là chạy độc lập hay chỉ là snippet cần đặt vào project.

## 2. “Rò rỉ danh tính giữa người dùng” gồm những gì?

**Cross-user identity leakage** là khi request hoặc job của một chủ thể nhận nhầm danh tính, quyền hoặc dữ liệu gắn với chủ thể khác. Điều này có thể chỉ xuất hiện dưới tải đồng thời, khi server tái sử dụng thread, session hoặc đối tượng.

Ví dụ:

```text
Thời điểm            Request A / Alice                 Request B / Bob
   t0                Authentication = Alice            Authentication = Bob
   t1                đọc /api/me                         đọc /api/me
   t2                kỳ vọng Alice                       kỳ vọng Bob
   t3                thực tế Alice                       thực tế Alice  <-- LEAK
```

Hoặc tinh vi hơn:

```text
A (ROLE_USER) -> GET /api/orders/1001 -> order của A
B (ROLE_USER) -> GET /api/orders/2002 -> order của B

B gửi GET /api/orders/1001:
- B vẫn có thể thấy `principal=bob` đúng;
- Nhưng API trả order của Alice do không kiểm tra owner.
```

Trường hợp thứ hai là **rò rỉ dữ liệu/phân quyền đối tượng (IDOR/BOLA)** chứ không nhất thiết là lỗi `SecurityContextHolder`. Bài test tốt phải phát hiện **cả principal leak và data leak**.

Các dạng khác:

| Dạng lỗi | Dấu hiệu | Nguyên nhân thường gặp |
| --- | --- | --- |
| Principal leak | `/api/me` của Bob trả `alice` | Static field/currentUser singleton, context dùng chung |
| Authority leak | Bob có `ROLE_ADMIN` của Alice | Mutable authorities list/cache không gắn user |
| Session leak | Browser B thấy phiên của A | Cookie jar dùng chung, session ID sai, custom repository lỗi |
| Async leak | Background job của Bob chạy dưới account A | Context truyền từ người khác hoặc thread pool không clear |
| Cross-tenant leak | Bob ở tenant B thấy profile tenant A | Cache/repository key thiếu tenant, query không scope tenant |
| Object leak | Alice đọc order của Bob dù principal đúng | Thiếu authorization trên object |
| Response cache leak | Response private của A được phục vụ cho B | Cache HTTP/CDN không vary/private/no-store đúng |
| Audit leak | Event của A ghi actor B | Singleton mutable actor, context sai trong job |
| Resource Server leak | Claims/authorities từ JWT A gán sang B | Cache converter không khóa theo token/subject/issuer |
| Test contamination | Test B pass/fail phụ thuộc test A | SecurityContextHolder/global strategy/static test fixture |

**Điểm mấu chốt:** không thể chỉ assert hai login đều nhận 200. Cần assert **nội dung identity, authorities, ownership và dấu vết độc lập** trên từng request.

## 3. Các invariant phải duy trì

Đặt `principal(request)` là user đã được xác thực với request cụ thể và `grants(request)` là authorities đã được server xác minh. Ta cần những điều kiện:

1. **Identity correctness:** `principal(A) == Alice`, `principal(B) == Bob`, không bị tráo ngay cả khi chạy cùng lúc.
2. **No unauthenticated inheritance:** request không gửi credentials/session hợp lệ **không** được hưởng Authentication của request vừa xử lý trên cùng worker thread.
3. **Authority isolation:** authority của A không bị cộng hoặc giữ lại trong Authentication của B.
4. **Resource ownership:** truy cập object phải kiểm tra `owner`/tenant hoặc policy tương đương, không chỉ `isAuthenticated()`.
5. **Session boundary:** cookie/session của A không thể trở thành session của B do cache, lưu context hay response sai.
6. **Context lifetime:** context chỉ có hiệu lực trong đúng request/task, được dọn/khôi phục sau đó.
7. **Async ownership:** nếu job cần chạy dưới identity gọi nó, context phải được **truyền có kiểm soát** từ request đó và dọn sau job. Nếu job là system task, dùng service identity riêng thay vì kế thừa ngẫu nhiên.
8. **Credential secrecy:** response/audit không chứa raw password, access token, cookie, OTP hoặc secret của user khác.
9. **Failure isolation:** sai password của B không làm request A trở thành anonymous, không xóa session A, và không để B dùng context A.
10. **Revocation semantics:** sau logout, disable user hoặc đổi role, những request mới tuân thủ policy về revoke/TTL; không giả định session cũ tự cập nhật tức thì nếu chưa triển khai.

Invariant này phải được thử với **các actor khác nhau**. Hai request của cùng một user không đủ kiểm chứng lỗi tráo danh tính giữa A và B.

## 4. Vì sao Java server dễ gặp lỗi đồng thời?

Các nguồn chia sẻ trạng thái trong Spring Boot:

- `@Service`, `@Component`, `@Controller` mặc định là **singleton bean**. Nếu class có field mutable `currentUsername`, field này có thể bị nhiều request cùng ghi đè.
- Servlet container dùng **thread pool**. Một thread hôm nay phục vụ Alice, request sau phục vụ Bob hoặc anonymous.
- `SecurityContextHolder` mặc định dựa trên **ThreadLocal**, nhưng code ứng dụng có thể thay chiến lược hoặc tự dùng ThreadLocal mà quên xóa.
- `HttpSession` liên kết browser/client thông qua cookie session, không theo địa chỉ IP hoặc việc mở tab.
- `SecurityContext` chứa một `Authentication` object có thể được chia sẻ nếu app tự tái sử dụng instance trên nhiều request.
- Executor/`@Async` chạy trên thread khác, **không tự có context** của request khởi tạo nếu thiếu cầu nối đúng.
- WebFlux tiếp tục một request qua nhiều thread, do đó `ThreadLocal` không phải nơi chính để đọc Authentication; Spring Security dùng **Reactor Context**.
- Cache application có thể chứa response/permission dữ liệu theo key quá rộng như `profile` thay vì `tenantId:userId:profile`.

### Anti-pattern: current user trong singleton service

```java
// SAI: field mutable nằm trong singleton bean, có thể bị request khác ghi đè.
@Service
public class UnsafeIdentityService {
    private String currentUser;

    public void setUser(String username) {
        this.currentUser = username;
    }

    public String currentUser() {
        return currentUser;
    }
}
```

Nếu A gọi `setUser("alice")`, B gọi `setUser("bob")`, rồi A đọc `currentUser`, A có thể thấy `bob`. `volatile` chỉ giúp visibility, **không** biến một field chung thành vùng lưu trữ identity theo request. `synchronized` cũng không giải quyết mô hình lưu một principal dùng chung.

**Đúng:** lấy `Authentication`/`Principal` của **request hiện tại**, rồi chuyển định danh rõ ràng vào service cần dùng, ví dụ:

```java
@GetMapping("/api/me")
public String me(Authentication authentication) {
    return authentication.getName();
}
```

Đây là **snippet trong Spring MVC controller** đã xác thực request. Không nhận `username` do client truyền rồi tự coi đó là user hiện tại.

## 5. `SecurityContextHolder` trong Servlet: ThreadLocal nhưng không phải session

Theo Spring Security Servlet:

```text
HTTP request A (JSESSIONID=...)
  |
  v
FilterChainProxy / SecurityContextHolderFilter
  |
  +-- Load SecurityContext từ SecurityContextRepository
  |     hoặc từ auth filter tương ứng
  |
  +-- Authentication hiện tại = Alice
  |
  +-- Controller/service (thread của request)
  |
  v
Dọn SecurityContextHolder khi request kết thúc

Thread worker có thể được tái sử dụng cho HTTP request B:
  |
  +-- Load Authentication của B hoặc anonymous
  +-- Không được kế thừa Alice từ ThreadLocal cũ
```

`SecurityContextHolder` lưu `SecurityContext` cho **thread hiện tại** theo chiến lược mặc định `MODE_THREADLOCAL`. `SecurityContext` chứa `Authentication`: principal, credentials (thường được erase sau khi login) và authorities.

`FilterChainProxy` của Spring Security chịu trách nhiệm dọn context khi request kết thúc. Điều này **không** bảo đảm những ThreadLocal tự tạo hoặc executor tự quản của ứng dụng cũng được dọn.

**Một chi tiết được tài liệu Spring Security nhấn mạnh:** khi cần thiết lập Authentication bằng tay, nên tạo `SecurityContext` **mới**:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
```

Thay vì sửa thẳng:

```java
// Không khuyến nghị khi context có thể đang được chia sẻ:
SecurityContextHolder.getContext().setAuthentication(authentication);
```

Vì một `SecurityContext` hiện có có thể được chia sẻ, gây race và tráo identity. Không dùng `SecurityContextHolder.MODE_GLOBAL` cho ứng dụng web đa người dùng; `MODE_INHERITABLETHREADLOCAL` không phải cách giải quyết tổng quát cho thread pool, vì một thread tái sử dụng không tương đương một child thread mới được tạo cho mỗi request.

### SecurityContextRepository không tự là ThreadLocal

`SecurityContextRepository` lưu và khôi phục context qua các request; ví dụ `HttpSessionSecurityContextRepository` dùng session cho browser login, `RequestAttributeSecurityContextRepository` có phạm vi request. Với Spring Security 6.x, khi **tự viết login filter/controller** tạo Authentication, phải lưu context qua `SecurityContextRepository.saveContext(...)` nếu muốn duy trì session. Chỉ gọi `SecurityContextHolder.setContext(...)` trong custom controller không tự bảo đảm request sau nhận lại user.

Vấn đề dễ rò rỉ không nằm ở một dòng `setContext` đơn lẻ; nó xuất hiện khi app dùng **một SecurityContext chung** cho nhiều session, hoặc lưu context của A vào session/cookie của B.

## 6. Tách concurrency theo từng lớp

“Chạy song song” có thể có ít nhất năm nghĩa:

| Kiểu chạy | Ví dụ | Điều cần assert |
| --- | --- | --- |
| Concurrent request | A và B GET `/api/me` cùng lúc | A vẫn A, B vẫn B |
| Sequential reuse of thread | Worker vừa phục vụ A, request B đến sau | B không đọc ThreadLocal của A |
| Concurrent login | A và B POST `/login` đồng thời từ browser riêng | Session/cookie của A và B không tráo |
| Concurrent operations in one session | Hai tab của **cùng browser** gửi request | Semantics session và login/logout phù hợp; không coi hai tab là hai session |
| Async/background work | A và B submit jobs lên executor | Mỗi job dùng đúng identity đã cấp cho job |
| Distributed concurrency | A/B qua hai app nodes, Redis/shared sessions | Key/cache/session tách biệt giữa users |
| Reactive interleaving | Hai `Mono` xen kẽ trên event loop | Reactor Context của từng subscription độc lập |

Test chỉ có hai user **chạy lần lượt** có thể bỏ sót race do shared mutable field. Ngược lại, test concurrent mà mỗi request dùng cùng cookie jar cũng có thể tạo kết quả tráo user do **test tự chia sẻ client/session**, chứ không phải server có lỗ hổng. Cần kiểm soát cả phía server lẫn test harness.

## 7. Thiết kế dữ liệu thử nghiệm không mơ hồ

Dùng fixture có principal, role và dữ liệu riêng, **không dùng account thật**:

| Account | Authorities | Resource hợp lệ | Resource phải bị chặn |
| --- | --- | --- | --- |
| `alice` | `ROLE_USER` | `profile-alice`, `order-A1` | `profile-bob`, `order-B1`, admin |
| `bob` | `ROLE_AUDITOR` | `profile-bob`, `order-B1` | `profile-alice`, `order-A1`, admin |
| `carol` | `ROLE_ADMIN` | `profile-carol`, `/api/admin` | Dữ liệu riêng của A/B nếu admin không được ủy quyền |
| Anonymous | Không có role user | Public endpoints | `/api/me`, `/api/admin`, private objects |

**Đừng mặc định `ROLE_ADMIN` nghĩa được xem mọi dữ liệu tenant.** Vai trò admin và ownership là hai chiều kiểm soát có thể độc lập.

Một bài test nên quan sát:
- `Authentication.getName()` của **mỗi request**.
- `Authentication.getAuthorities()` so với **tập quyền chính xác**; chỉ assert có `ROLE_USER` sẽ bỏ lọt `ROLE_ADMIN`.
- Body resource chứa `ownerId` đúng người/tenant, không bao giờ xuất dữ liệu riêng của B cho A.
- HTTP status/redirect/cookies tương ứng, kể cả 401/403/404 theo policy.
- Session/cookie jar riêng cho từng browser actor.
- Audit actor và correlation ID; không log secret để kiểm tra.

Trong kiểm thử login song song, cùng một `requestId` hoặc cùng `TraceId` sai cách gắn kết cũng có thể làm audit ghi nhận danh tính sai dù response khách hàng tình cờ đúng.

## 8. Java 17 thuần JDK: demo cách ly `ThreadLocal`

Đây là chương trình **chạy độc lập**, không cần Spring. Nó dùng hai thread hoạt động đồng thời, đồng bộ bằng `CyclicBarrier`, rồi cố tình tái sử dụng pool để kiểm tra context đã được xóa.

File `ParallelIdentityIsolationDemo.java`:

```java
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ParallelIdentityIsolationDemo {

    private static final ThreadLocal<String> CURRENT_USER =
        new ThreadLocal<>();

    private static Callable<String> request(
            String user, CyclicBarrier overlap) {
        return () -> {
            try {
                CURRENT_USER.set(user);
                overlap.await(5, TimeUnit.SECONDS);
                return CURRENT_USER.get();
            } finally {
                CURRENT_USER.remove();
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            CyclicBarrier overlap = new CyclicBarrier(2);
            Future<String> a = pool.submit(request("alice", overlap));
            Future<String> b = pool.submit(request("bob", overlap));

            boolean aliceOk = "alice".equals(a.get(10, TimeUnit.SECONDS));
            boolean bobOk = "bob".equals(b.get(10, TimeUnit.SECONDS));

            // Hai tác vụ sau không tự có danh tính từ tác vụ trước.
            Future<Boolean> cleanA = pool.submit(
                () -> CURRENT_USER.get() == null
            );
            Future<Boolean> cleanB = pool.submit(
                () -> CURRENT_USER.get() == null
            );

            System.out.println("alice-isolated=" + aliceOk);
            System.out.println("bob-isolated=" + bobOk);
            System.out.println(
                "no-stale-context="
                    + (cleanA.get(10, TimeUnit.SECONDS)
                       && cleanB.get(10, TimeUnit.SECONDS))
            );
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac ParallelIdentityIsolationDemo.java
java ParallelIdentityIsolationDemo
```

**stdout khi hai task được thực thi bình thường:**

```text
alice-isolated=true
bob-isolated=true
no-stale-context=true
```

Đây là kết quả logic kỳ vọng; trường hợp môi trường nghẽn quá thời hạn chờ 5 giây sẽ ném exception thay vì in `false`, nên khi dùng cho CI cần timeout hợp lý.

**Giải thích:**
- `ThreadLocal` tách giá trị theo thread, **không** theo user/session.
- `CyclicBarrier(2)` bảo đảm A và B cùng đi tới điểm hẹn trước khi đọc identity; tránh bài test “song song” nhưng thực tế chạy lần lượt.
- `try/finally` gọi `CURRENT_USER.remove()` để thread pool không giữ identity của nhiệm vụ trước.
- `Future.get(...)` chuyển lỗi bên worker về thread test, không nuốt exception.
- Các task sau kiểm tra việc pool **không tái sử dụng user cũ**.

**Giới hạn:** chương trình này không phải `SecurityContextHolder` và không kiểm chứng servlet filter chain, session, cookie hay quyền truy cập object. Nó chỉ minh họa bản chất thread-local context và cách kiểm thử có điều phối.

## 9. JUnit 5: kiểm thử thật `SecurityContextHolder` theo hai thread

Trong dự án Gradle dùng Spring Boot 3.x + Spring Security 6.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo file `src/test/java/example/isolation/SecurityContextIsolationTest.java`:

```java
package example.isolation;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SecurityContextIsolationTest {

    private SecurityContext contextFor(String username) {
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            new TestingAuthenticationToken(
                username, "fixture-only", "ROLE_USER"
            )
        );
        return context;
    }

    private Callable<String> task(
            String username,
            CountDownLatch entered,
            CountDownLatch release) {
        return () -> {
            SecurityContextHolder.setContext(contextFor(username));
            try {
                entered.countDown();
                if (!release.await(10, TimeUnit.SECONDS)) {
                    throw new AssertionError("Test did not release tasks");
                }
                return SecurityContextHolder.getContext()
                    .getAuthentication().getName();
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    @Test
    void parallelWorkersKeepDifferentPrincipals() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch entered = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> a =
                pool.submit(task("alice", entered, release));
            Future<String> b =
                pool.submit(task("bob", entered, release));

            assertTrue(entered.await(10, TimeUnit.SECONDS));
            release.countDown();

            assertEquals("alice", a.get(15, TimeUnit.SECONDS));
            assertEquals("bob", b.get(15, TimeUnit.SECONDS));

            // Thread pool tái sử dụng: không còn principal cũ.
            Future<Boolean> cleared = pool.submit(
                () -> SecurityContextHolder
                    .getContext().getAuthentication() == null
            );
            assertTrue(cleared.get(15, TimeUnit.SECONDS));
        } finally {
            release.countDown();
            pool.shutdownNow();
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    void newContextIsNotTheSameInstanceAsAnotherUsers() {
        SecurityContext alice = contextFor("alice");
        SecurityContext bob = contextFor("bob");

        assertTrue(alice != bob);
        assertEquals("alice", alice.getAuthentication().getName());
        assertEquals("bob", bob.getAuthentication().getName());
    }
}
```

Chạy:

```bash
./gradlew test --tests example.isolation.SecurityContextIsolationTest
```

**Ý nghĩa kiểm thử:**
- Hai task cố ý chờ nhau, do đó race/overlap thực sự được kích hoạt ở lớp test.
- Mỗi task tạo một `SecurityContext` **riêng**, không sửa `Authentication` trong context của thread khác.
- `clearContext()` chạy trong `finally` ngay cả khi assertion ném lỗi.
- Task tái sử dụng pool kiểm tra không còn principal cũ.
- Không đổi `SecurityContextHolder` sang `MODE_GLOBAL`/`MODE_INHERITABLETHREADLOCAL` ở mức JVM trong test; những cấu hình này có thể ảnh hưởng các test khác nếu chạy chung.

**Phạm vi:** đây là **component-level concurrency test**, không chứng minh `HttpSessionSecurityContextRepository` gắn context đúng session của mỗi browser. Đó là lý do còn cần HTTP integration test ở mục 12.

### Một điểm cần tránh trong assertion

Không tạo `Authentication` từ test bằng:

```java
// SAI trong production: không hề xác minh credential.
UsernamePasswordAuthenticationToken.authenticated(
    "alice", null, someAuthorities
);
```

Token này có thể là fixture trong unit test thuần authorization, nhưng không phải bằng chứng login thực đã xác thực password/OTP. Mục 9 chỉ kiểm tra khả năng cách ly **holder**, không kiểm tra password verification.

## 10. Tác vụ bất đồng bộ: không để context của A xuất hiện ở B

Với `SecurityContextHolder.MODE_THREADLOCAL`, một task chạy trên thread khác thường **không tự có** Authentication của request tạo task. Nếu code app bắt buộc tác vụ cần chạy dưới identity của caller, Spring Security cung cấp:

- `DelegatingSecurityContextRunnable`
- `DelegatingSecurityContextCallable`
- `DelegatingSecurityContextExecutor`
- `DelegatingSecurityContextExecutorService`
- Các wrapper/scheduler tương ứng trong concurrency support

`DelegatingSecurityContextCallable` nhận **context cụ thể** hoặc chụp context hiện tại tại lúc wrapper được tạo, rồi thiết lập context cho callable và **khôi phục/dọn sau khi chạy**. Nhờ đó cùng một pool có thể phục vụ job của A rồi B mà không trộn identity, nếu mỗi job thực sự dùng context đúng của nó.

### JUnit test tái sử dụng cùng một worker thread

Tạo `src/test/java/example/isolation/DelegatingContextTest.java`:

```java
package example.isolation;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextCallable;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class DelegatingContextTest {

    private SecurityContext contextFor(String user) {
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            new TestingAuthenticationToken(user, "fixture-only", "ROLE_USER")
        );
        return context;
    }

    @Test
    void onePooledThreadHandlesAliceThenBobWithoutLeak()
            throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            var aliceTask = new DelegatingSecurityContextCallable<>(
                () -> SecurityContextHolder.getContext()
                    .getAuthentication().getName(),
                contextFor("alice")
            );

            var bobTask = new DelegatingSecurityContextCallable<>(
                () -> SecurityContextHolder.getContext()
                    .getAuthentication().getName(),
                contextFor("bob")
            );

            assertEquals("alice",
                pool.submit(aliceTask).get(10, TimeUnit.SECONDS));
            assertEquals("bob",
                pool.submit(bobTask).get(10, TimeUnit.SECONDS));

            Future<Boolean> after = pool.submit(
                () -> SecurityContextHolder
                    .getContext().getAuthentication() == null
            );
            assertEquals(true, after.get(10, TimeUnit.SECONDS));
        } finally {
            pool.shutdownNow();
            SecurityContextHolder.clearContext();
        }
    }
}
```

**Vì sao dùng một worker thread?** Nếu có lỗi giữ lại context, tác vụ Bob và kiểm tra cuối có cơ hội gặp **chính thread được tái sử dụng**. Dùng nhiều thread mà scheduler tình cờ chọn thread khác có thể khiến test false negative.

### `DelegatingSecurityContextExecutorService` khi nào phù hợp?

Ví dụ khi code thật có một shared `ExecutorService`:

```java
ExecutorService raw = Executors.newFixedThreadPool(4);
ExecutorService secured =
    new DelegatingSecurityContextExecutorService(raw);
```

Đây là **snippet** trong lớp chịu trách nhiệm vòng đời executor. Wrapper chụp context phù hợp khi submit nhiệm vụ từ request đang có security context. Khi dùng xong, cần shutdown executor theo lifecycle do ứng dụng quản lý; không tạo pool mới mỗi request.

Cảnh báo về phiên bản constructor với `SecurityContext` cố định:

```java
// KHÔNG dùng một context Alice cố định cho mọi user khác nhau.
new DelegatingSecurityContextExecutorService(raw, aliceContext);
```

Nếu wrapper được cấu hình context **cố định**, mọi task qua wrapper đó có thể chạy dưới identity Alice. Đây là tính năng có chủ đích cho **service account** trong một vài workflow, không phải cấu hình nên dùng cho requests của nhiều người.

Nếu job là **system task**, tốt hơn cấp một service principal/permission hạn chế và audit nguồn kích hoạt riêng, thay vì kéo nguyên `ROLE_ADMIN` của người dùng vào background task kéo dài nhiều giờ.

## 11. Demo Spring Boot Web MVC: endpoint nhận diện người dùng thật

Một component test `SecurityContextHolder` chỉ chứng minh ThreadLocal API. Để xác minh **login thực sự** qua Spring Security, xây ứng dụng REST nhỏ với HTTP Basic stateless, ba account và endpoint phản hồi principal/authorities. HTTP Basic đơn giản hóa bài kiểm thử vì **không cần cookie hoặc CSRF cho GET**; bài sẽ xét form login/session riêng ở mục 14.

### 11.1. Dependencies

Trong `build.gradle` của project Spring Boot 3.x đã có plugin/BOM/JDK 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Không trộn Spring Security 6.x và 7.x ngoài dependency management của Boot. Dùng JDK 17+.

### 11.2. Main class

File `src/main/java/example/isolation/ParallelAuthApplication.java`:

```java
package example.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ParallelAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(ParallelAuthApplication.class, args);
    }
}
```

### 11.3. Security configuration

File `src/main/java/example/isolation/IsolationSecurityConfig.java`:

```java
package example.isolation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class IsolationSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/me").authenticated()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        // Cost thấp CHỈ dành cho bộ test cục bộ.
        return new BCryptPasswordEncoder(4);
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-test-only"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-test-only"))
                .roles("AUDITOR")
                .build(),
            User.withUsername("carol")
                .password(encoder.encode("carol-test-only"))
                .roles("ADMIN")
                .build()
        );
    }
}
```

**Giải thích:**

- `.httpBasic(...)` sử dụng HTTP Basic để test login bằng credential thực. Mỗi request xác minh user và tạo `Authentication` cho request đó.
- `.sessionCreationPolicy(STATELESS)` cho bài demo không khôi phục Authentication từ HTTP session; mỗi request phải có `Authorization: Basic ...`.
- `/api/me` cần authenticated, `/api/admin` cần `ROLE_ADMIN`; một user authenticated không tự có quyền admin.
- `InMemoryUserDetailsManager` chỉ dành demo; production dùng DB/LDAP/IdP phù hợp và cache policy rõ.
- `BCryptPasswordEncoder(4)` có cost thấp để test chạy nhanh, **không** phải cấu hình production.
- Chỉ có GET routes trong demo; Spring Security vẫn giữ CSRF mặc định. Khi thêm form login hoặc POST/PUT/DELETE trên cookie-authenticated app, phải xử lý CSRF theo policy, **không** sao chép một dòng tắt CSRF bừa bãi.
- Bản demo không bật `maximumSessions(1)` vì đó là chính sách **giới hạn phiên của cùng user**, không giải quyết mục tiêu cách ly A/B.

### 11.4. Controller không giữ `currentUser` trong field

File `src/main/java/example/isolation/IdentityController.java`:

```java
package example.isolation;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication auth) {
        List<String> authorities = auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "username", auth.getName(),
            "authorities", authorities
        );
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin-ok";
    }
}
```

Controller được Spring quản lý singleton nhưng không giữ thông tin request trong field. `Authentication` được resolve cho request hiện tại. Với dữ liệu nghiệp vụ thật, không trả những thuộc tính nhạy cảm không cần thiết; `/api/me` ở đây chỉ để **kiểm thử isolation**, còn `/api/admin` để test role boundary.

Chạy:

```bash
./gradlew bootRun
```

Request minh họa trên máy local:

```bash
curl -i -u alice:alice-test-only http://localhost:8080/api/me
curl -i -u bob:bob-test-only http://localhost:8080/api/me
curl -i -u carol:carol-test-only http://localhost:8080/api/admin
```

**Kết quả mong đợi:** Alice nhận `username=alice`, authorities chỉ `ROLE_USER`; Bob chỉ `ROLE_AUDITOR`; Carol được `/api/admin` trả `admin-ok`. Password demo không phải secret production. `curl -u` có thể lộ thông tin giả trong process list/shell history, nên không dùng cách này cho credentials thật.

## 12. Spring Boot integration test: nhiều HTTP requests thật song song

Test sau chạy **HTTP server thực** ở port ngẫu nhiên (`RANDOM_PORT`), dùng `java.net.http.HttpClient` của JDK 17, gửi 30 tác vụ chia cho Alice/Bob/Carol, so principal và **tập quyền chính xác** ở từng response.

Tạo `src/test/java/example/isolation/ParallelLoginHttpTest.java`:

```java
package example.isolation;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ParallelLoginHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private HttpRequest request(
            String path, String username, String password) {
        String raw = username + ":" + password;
        String basic = Base64.getEncoder().encodeToString(
            raw.getBytes(StandardCharsets.UTF_8)
        );

        return HttpRequest.newBuilder()
            .uri(URI.create("http://localhost:" + port + path))
            .header("Authorization", "Basic " + basic)
            .GET()
            .build();
    }

    @Test
    void parallelAccountsNeverExchangeNamesOrAuthorities()
            throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        int workers = 10;
        int requests = 30;
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Void>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < requests; i++) {
                int index = i;

                futures.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(10, TimeUnit.SECONDS)) {
                        throw new AssertionError("Start latch timed out");
                    }

                    String user;
                    String password;
                    Set<String> expectedAuthorities;

                    switch (index % 3) {
                        case 0 -> {
                            user = "alice";
                            password = "alice-test-only";
                            expectedAuthorities = Set.of("ROLE_USER");
                        }
                        case 1 -> {
                            user = "bob";
                            password = "bob-test-only";
                            expectedAuthorities = Set.of("ROLE_AUDITOR");
                        }
                        default -> {
                            user = "carol";
                            password = "carol-test-only";
                            expectedAuthorities = Set.of("ROLE_ADMIN");
                        }
                    }

                    HttpResponse<String> me = client.send(
                        request("/api/me", user, password),
                        HttpResponse.BodyHandlers.ofString()
                    );
                    assertEquals(200, me.statusCode());

                    JsonNode json = mapper.readTree(me.body());
                    assertEquals(user, json.path("username").asText());

                    Set<String> actualAuthorities = new HashSet<>();
                    for (JsonNode authority : json.path("authorities")) {
                        actualAuthorities.add(authority.asText());
                    }
                    assertEquals(
                        expectedAuthorities, actualAuthorities
                    );

                    HttpResponse<String> admin = client.send(
                        request("/api/admin", user, password),
                        HttpResponse.BodyHandlers.ofString()
                    );
                    assertEquals(
                        "carol".equals(user) ? 200 : 403,
                        admin.statusCode()
                    );
                    if ("carol".equals(user)) {
                        assertEquals("admin-ok", admin.body());
                    }
                    return null;
                }));
            }

            assertTrue(ready.await(10, TimeUnit.SECONDS));
            start.countDown();

            for (Future<Void> future : futures) {
                future.get(60, TimeUnit.SECONDS);
            }
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
./gradlew test --tests example.isolation.ParallelLoginHttpTest
```

**Kỳ vọng theo cấu hình mục 11:** 30 tác vụ đều đọc đúng `username` và đúng tập authorities; `/api/admin` chỉ trả 200 cho Carol, trả 403 cho Alice và Bob. Đây là **kết quả kỳ vọng từ code**, không phải kết quả đã được thực thi trên server thật trong bài.

### Tại sao test này đáng giá?

1. Spring Boot thực sự khởi động **embedded HTTP server**, không chỉ gọi trực tiếp controller.
2. `HttpClient` không được cấu hình cookie store dùng chung; mô hình **stateless Basic** tạo ra authentication riêng theo header của mỗi request.
3. `CountDownLatch` giúp nhiều worker bắt đầu cùng lúc; mỗi request đi qua security filter chain thật.
4. Mỗi response được so với account **đã gửi request** thay vì chỉ kiểm tra status 200.
5. Authorities được so như **Set đầy đủ**, nên phát hiện quyền thừa bị rò.
6. `/api/admin` bắt được một số lỗi cấp nhầm vai trò.
7. `Future.get(...)` truyền assertion failure từ worker về JUnit, không giấu lỗi trong executor.
8. Với ba user, race có thể phát hiện tình huống singleton controller, cache hoặc custom authentication code chia sẻ state.

### Những điều test này CHƯA chứng minh

- Nó không sử dụng **form login** hoặc HTTP session/JSESSIONID; nên không kiểm tra session fixation/cookie jar.
- Nó không kiểm tra quyền trên từng object thuộc account/tenant.
- Nó không kiểm thử `@Async`/message broker/WebFlux Reactor Context.
- Nó không mô phỏng phân tán nhiều node; local app là một instance.
- Một lần pass không chứng minh **không bao giờ** có race; cần lặp lại có kiểm soát và test các nhánh lỗi.
- Basic credential vẫn có thể bị replay nếu lộ; production cần HTTPS và cơ chế xác thực phù hợp, chứ không coi bài demo là kiến trúc xác thực đề xuất.

## 13. Chọn tiêu chí pass/fail đúng

Một bộ kiểm thử tốt không dừng ở:

```java
assertEquals(200, response.statusCode());
```

Mà cần khẳng định tương quan:

```text
For each actor:
  - request dùng credential/session/token của actor đó
  - response principal == actor
  - response authority set == policy của actor
  - response private resource owner == actor hoặc quyền được ủy quyền rõ
  - response không có thuộc tính/secret thuộc actor khác
  - audit event actor == actor (nếu audit là phần scope)
  - anonymous/invalid-token không được nhận identity cũ
```

**Không dùng** một mutable static `expectedUser` bị các task ghi đè làm oracle kiểm thử. Lưu expected user dưới **local variable của từng task**, như mục 12, hoặc record immutable theo request.

Nếu test tạo hai clients song song nhưng response được thu vào một `List` theo thứ tự hoàn tất, đừng coi `results[0]` nhất thiết thuộc Alice. Phải gắn **correlation ID** do test tạo vào future/kết quả và so với actor tương ứng; thứ tự network completion không xác định.

## 14. Form login và HTTP session: kiểm thử cách ly phải dùng hai browser riêng

Với browser form login, thông tin xác thực thường được lưu trong HTTP session và browser gửi `JSESSIONID` qua cookie. Hai **tab trong một browser profile** thường dùng **cùng cookie jar**, do đó không tạo hai phiên độc lập chỉ vì mở hai cửa sổ. Một lần login thành Bob trong tab B có thể làm tab A cùng browser chuyển sang Bob — đây là **hành vi cùng session**, không phải bằng chứng session leak qua hai người dùng độc lập.

Muốn test Alice và Bob trong **hai phiên riêng**, hãy dùng:
- Hai browser contexts/profiles riêng; hoặc
- Hai HTTP clients có cookie jars riêng; hoặc
- Hai `MockHttpSession` khác nhau khi dùng `MockMvc`.

### 14.1. Luồng thực tế cần kiểm thử

```text
Client A / CookieJar A              Client B / CookieJar B
   | GET /login / CSRF                 | GET /login / CSRF
   | POST /login alice                 | POST /login bob
   | <- Set-Cookie JSESSIONID_A        | <- Set-Cookie JSESSIONID_B
   | GET /api/me (cookie A)            | GET /api/me (cookie B)
   | <- alice                          | <- bob
   | GET /api/orders/A1                | GET /api/orders/B1
   | <- data alice                     | <- data bob
   | Logout A                          | vẫn duy trì B
   | GET /api/me -> login/401          | GET /api/me -> bob
```

**Lưu ý session fixation protection:** sau khi form login thành công, Spring Security có thể đổi session ID. Không test rằng cookie **trước login** phải bằng cookie **sau login**. Ngược lại, phải dùng cookie hiện hành của mỗi browser context.

### 14.2. MockMvc snippet cho một ứng dụng FORM LOGIN khác

Trong ứng dụng **khác với demo stateless Basic ở mục 11**, giả sử đã bật `.formLogin(withDefaults())`, có hai test users `alice`, `bob` và controller `/api/me`, `MockMvc` được gắn Spring Security filter chain:

```java
// Snippet trong @Test của app dùng form login và HTTP session.
MvcResult aliceLogin = mvc.perform(
        formLogin().user("alice").password("alice-password"))
    .andExpect(authenticated().withUsername("alice"))
    .andReturn();

MvcResult bobLogin = mvc.perform(
        formLogin().user("bob").password("bob-password"))
    .andExpect(authenticated().withUsername("bob"))
    .andReturn();

MockHttpSession sessionAlice =
    (MockHttpSession) aliceLogin.getRequest().getSession(false);
MockHttpSession sessionBob =
    (MockHttpSession) bobLogin.getRequest().getSession(false);

assertNotEquals(sessionAlice.getId(), sessionBob.getId());

mvc.perform(get("/api/me").session(sessionAlice))
   .andExpect(status().isOk())
   .andExpect(jsonPath("$.username").value("alice"));

mvc.perform(get("/api/me").session(sessionBob))
   .andExpect(status().isOk())
   .andExpect(jsonPath("$.username").value("bob"));
```

Imports cần dùng trong method/class test:

```java
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

**Đây là snippet, không phải test độc lập:** project session-based phải cung cấp `MockMvc`, `SecurityFilterChain` form-login, user fixture/password, `/api/me`, CSRF và repository tương ứng. Spring Security Test `formLogin()` tự điền CSRF token hợp lệ theo contract mặc định. Không chạy nguyên snippet này với config stateless Basic mục 11 vì ứng dụng đó **không bật** form login/session.

### 14.3. Session test cần có negative cases

- A login thành công, B login thất bại: B **không** nhận session authenticated của A.
- A logout: B vẫn authenticated; không tự xóa session B.
- B thay password: A không tự bị đổi principal; việc invalidate session khác phải theo policy.
- A cố dùng session ID của B: nếu có cookie/session bị đánh cắp thì đó là **session hijacking**, cần controls/reauth/token binding hợp lý; không thể kỳ vọng server luôn phân biệt người gửi cookie đã bị đánh cắp bằng identity vật lý.
- Một browser profile đăng nhập lần lượt Alice rồi Bob: nên có session rotation/clear context đúng; không để quyền cũ của Alice trộn với Bob.
- Khi response trả `Set-Cookie`, test cập nhật cookie jar **đúng client**; không dùng một `CookieManager` tĩnh cho hai actor.
- `maximumSessions(1)` không thay thế những test này; đó là giới hạn **bao nhiêu session của cùng user**.

## 15. Authentication session vs user context: khi nào có race?

Một lỗi code hay gặp:

```java
// SAI: tất cả request cùng dùng một SecurityContext mutable.
private static final SecurityContext SHARED =
    SecurityContextHolder.createEmptyContext();

public void onAuthenticated(Authentication authentication) {
    SHARED.setAuthentication(authentication);
    SecurityContextHolder.setContext(SHARED);
}
```

Khi A và B gọi `onAuthenticated` đồng thời, `SHARED` chỉ giữ một `Authentication` được ghi sau cùng. Kể cả mỗi thread có `ThreadLocal` trỏ đúng biến `SHARED`, **cùng object context** vẫn bị ghi đè.

Hướng sửa:
- Tạo `SecurityContext` mới theo **mỗi lần authentication**.
- Không giữ static/shared reference tới mutable `SecurityContext`.
- Lưu đúng vào **session/request** thông qua `SecurityContextRepository` tương ứng.
- Không tái sử dụng `UsernamePasswordAuthenticationToken` mutable của user này như result user khác.
- Khi background task cần identity, chụp snapshot hoặc wrapper đúng theo task, không dùng `SecurityContextHolder` toàn cục.

**Lưu ý:** một `SecurityContext` độc lập theo thread nhưng chứa principal/authorities object **mutable dùng chung** vẫn có thể rò quyền hoặc thay dữ liệu giữa các users. Cần đánh giá **toàn bộ object graph**, không chỉ so identity của context instance.

## 16. Tác vụ `@Async`, `CompletableFuture` và thread pool

Trong một servlet request:

```java
public void submitJob() {
    // Chỉ minh họa phạm vi, không phải job implementation hoàn chỉnh.
    executor.execute(() -> {
        // Thread pool có thể khác với request thread.
        // SecurityContextHolder ở đây không mặc nhiên là caller.
    });
}
```

Nếu cần user context bên trong job:
- Tách danh tính nghiệp vụ (actor ID/tenant ID) thành đối số **đã được xác minh ở server**.
- Dùng `DelegatingSecurityContextCallable` hoặc `DelegatingSecurityContextExecutorService` nếu job thực sự cần Spring Security context.
- Khi job lấy identity từ `SecurityContext`, wrapper phải được tạo/submitted **khi caller context còn hiệu lực**, không tới lúc request đã kết thúc.
- Đảm bảo cleanup/restore trên worker thread trong `finally`, đặc biệt lúc job ném exception.
- Không dùng `MODE_INHERITABLETHREADLOCAL` làm cách chuyển context chính cho thread pool.
- Khi dùng `CompletableFuture.supplyAsync` hoặc custom scheduler, xác định executor nào chạy task; common pool không tự mang đúng Spring Security identity.
- Nếu job nhiều giờ, tránh giữ toàn bộ mutable Authentication/session; truyền actor/tenant IDs được phép và kiểm tra quyền tại thời điểm thực thi khi nghiệp vụ đòi hỏi.
- Test nhiều job A/B xen kẽ trên **cùng executor** và test một job ném exception trước khi job B chạy.

### `SecurityContext` đã được truyền đúng nhưng quyền thay đổi?

Ví dụ Alice có `ROLE_MANAGER` khi enqueue, sau đó bị thu hồi trước khi job chạy. Một context snapshot cũ không tự phản ánh revoke. Policy cần quyết định:
- Xử lý theo quyền tại **thời điểm submit** hay **thời điểm execute**?
- Có nên hủy job hoặc recheck account state/permission trước hành động nhạy cảm?
- Job được phép thực hiện với phạm vi dữ liệu nào, và audit cần ghi rõ actor/delegation?
- Có nguy cơ task của A lấy nhầm tenant/resource của B qua cache/repository?

Đó là **authorization freshness**, khác với lỗi identity leak, nhưng phải kiểm thử cùng workflow vì hậu quả tương tự.

## 17. WebFlux: dùng Reactor Context, không giả định ThreadLocal

Trong Spring Security WebFlux, Authentication được đặt trong **Reactor Context** thông qua `ReactiveSecurityContextHolder`. Reactive pipeline có thể chuyển thread ở `publishOn`, `subscribeOn`, `flatMap`; một request không gắn cứng với một thread.

Ví dụ controller reactive:

```java
@GetMapping("/api/reactive/me")
public Mono<String> me() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("No authenticated user")
        ));
}
```

Imports:

```java
import reactor.core.publisher.Mono;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
```

Đây là **snippet trong `@RestController` WebFlux** có `SecurityWebFilterChain` bảo vệ route; không phải endpoint độc lập. Nếu principal là anonymous hoặc chưa authenticated, security filters phải chặn theo policy trước khi controller xử lý; không dùng `IllegalStateException` làm HTTP authentication entry point.

### Reactive leak anti-pattern

```java
// SAI: dùng chung một identity mutable giữa các subscriptions.
static volatile String lastUser;

Mono<String> whoAmI() {
    return Mono.just(lastUser);
}
```

Một subscription của Bob có thể đọc giá trị Alice hoặc ngược lại. `volatile` không tách dữ liệu theo subscription.

Cũng tránh:
- Truy cập `SecurityContextHolder.getContext()` như thể nó tự đại diện cho reactive request.
- Đặt `Authentication` vào field singleton controller/service.
- Dùng `.block()` để lấy principal trong Netty event loop.
- Giữ một `Mono<String>` đã được `.cache()` **toàn cục** mà nội dung phụ thuộc user nhưng không scope theo user/subscription.
- Đổi từ reactive sang thread pool bên ngoài rồi tự truyền `ThreadLocal` không đúng.

### Hướng test reactive

Dùng `WebTestClient` và Spring Security Test để kiểm tra identity/authority theo từng request. Khi kiểm thử isolation thực, có thể chạy hai `WebTestClient` contexts với credentials khác nhau, hoặc dùng `StepVerifier` cho hai streams có `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))`.

Ví dụ **snippet** đơn vị:

```java
Mono<String> currentName =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());

Mono<String> aliceFlow = currentName.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(aliceAuth)
);
Mono<String> bobFlow = currentName.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(bobAuth)
);
```

`aliceAuth`, `bobAuth` ở đây là hai `Authentication` test được tạo độc lập. Dùng `StepVerifier` hoặc `Mono.zip(aliceFlow, bobFlow)` để assert hai tên không lẫn; `currentName` chỉ được subscribe khi context đúng đã được gắn. Không sử dụng cùng một mutable SecurityContext cho hai flows.

**Kiểm thử HTTP reactive** vẫn cần xác minh filter chain thực, session/cookie hoặc Bearer token và controller, không chỉ unit test `contextWrite`.

## 18. Không rò danh tính vẫn chưa đủ: kiểm soát quyền trên từng resource

Giả sử `/api/me` luôn trả đúng principal, nhưng controller cho lấy dữ liệu bằng ID bất kỳ:

```java
// SAI: không check owner/tenant.
@GetMapping("/api/orders/{orderId}")
public Order getOrder(@PathVariable long orderId) {
    return repository.findById(orderId)
        .orElseThrow();
}
```

Alice có thể thử order ID của Bob. Đây là lỗi **Broken Object Level Authorization (BOLA/IDOR)**.

Một pattern an toàn hơn:

```java
@GetMapping("/api/orders/{orderId}")
public Order getOrder(
        @PathVariable long orderId,
        Authentication authentication) {
    return repository.findByIdAndOwnerId(
            orderId,
            authentication.getName()
        )
        .orElseThrow(() -> new ResponseStatusException(
            HttpStatus.NOT_FOUND
        ));
}
```

Đây là **snippet** cần `Order`, `repository`, import Spring MVC và kiểu `ResponseStatusException` phù hợp. Đối với hệ thống nhiều tenant, `ownerId` thường chưa đủ; query phải kèm `tenantId` và chính sách tenant do server xác minh:

```text
SELECT ... FROM orders
WHERE id = :orderId
  AND owner_id = :authenticatedUserId
  AND tenant_id = :authenticatedTenantId
```

Không lấy `tenantId` từ một query/header client-controlled mà không kiểm tra membership/permission. Với admin, dùng authorization riêng cho cross-user access; không được vô tình bypass owner check vì có bất kỳ `ROLE_ADMIN` ở tenant khác.

### Ma trận negative tests cho object isolation

| Actor | Request | Kỳ vọng |
| --- | --- | --- |
| Alice | `GET /api/orders/A1` | 200, owner=Alice |
| Bob | `GET /api/orders/B1` | 200, owner=Bob |
| Alice | `GET /api/orders/B1` | 403 hoặc 404 theo policy, **không** có dữ liệu Bob |
| Bob | `GET /api/orders/A1` | 403/404, không có dữ liệu Alice |
| Anonymous | `GET /api/orders/A1` | 401/redirect, không có dữ liệu |
| Alice/Bob | Cùng request song song khác tenant | Không trộn dữ liệu/authority |
| Alice | `POST /api/orders` với body `owner=bob` | Server không tin owner từ body nếu policy chỉ cho tạo order của mình |
| Admin tenant A | `GET /api/orders/B1` tenant B | Không tự được phép nếu cross-tenant access bị cấm |

Đối với response bị từ chối, kiểm tra **không có PII** của user khác trong error body/log/headers. Tránh trả message `"Order 123 belongs to bob"` cho Alice.

## 19. Concurrent session control: khác biệt với cách ly người dùng

Spring Security Servlet có `sessionManagement(session -> session.maximumSessions(...))` để giới hạn số **session đồng thời của cùng principal**. Ví dụ:

```java
http.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true)
);
```

Đây là **snippet trong `HttpSecurity` của ứng dụng session-based**, không dùng trực tiếp trong demo Basic stateless mục 11.

`maximumSessions(1)` trả lời: “Một account được đăng nhập từ bao nhiêu session?”. Nó **không** trả lời: “Session của Bob có bị lẫn principal Alice không?”. Hai account Alice và Bob hoàn toàn có thể có session riêng dù mỗi account chỉ cho một session.

Muốn thử concurrency control:
- Tạo **hai clients/session riêng cùng username**.
- Với `maxSessionsPreventsLogin(true)`, lần login thứ hai vượt giới hạn phải bị từ chối (tùy flow).
- Với cấu hình cho phép đăng nhập mới thay session cũ, session trước sẽ bị invalidated theo policy.
- Đảm bảo `SessionRegistry` và session lifecycle events được cấu hình/nhận đủ khi dùng cơ chế truyền thống.
- Trong ứng dụng Spring Session/cluster, kiểm tra registry/store phù hợp mô hình phân tán.
- Nếu custom principal dùng làm key trong `SessionRegistry`, `equals()`/`hashCode()` phải phản ánh identity ổn định; sai implementation có thể khiến đếm session không đúng.

**Một browser có hai tab** thường dùng một session cookie. Đừng dùng hai tab trong cùng profile để kết luận giới hạn concurrent session không hoạt động.

### Session fixation protection cũng cần test

Sau đăng nhập, session ID có thể được đổi để chống session fixation. Test nên:
1. Nhận session/cookie trước login nếu workflow tạo session.
2. Login bằng credential thật.
3. Xác minh cookie/session sau login là identity đang có hiệu lực; thường session ID đổi.
4. Không vô tình gắn `SecurityContext` của user trước vào session mới khi browser chuyển account.
5. Logout/rotate session phải thu hồi theo policy và không làm ảnh hưởng session của account khác.

## 20. JWT/OAuth2 Bearer: kiểm thử đồng thời theo token, issuer và tenant

Resource Server với JWT hoặc opaque token thường không dùng `HttpSession` để xác minh user, nhưng cũng có nguy cơ chia sẻ mutable state trong converter/cache.

Tối thiểu test:
- JWT A có `sub=alice`, issuer/audience hợp lệ, scope `read:a`; JWT B có `sub=bob`, scope `read:b`.
- Hai token được gửi song song tới cùng endpoint: `JwtAuthenticationToken.getName()`/authorities phải phù hợp token hiện hành.
- JWT A không được kế thừa `SCOPE_read:b` từ B (và ngược lại).
- Không lấy `sub`/tenant từ JSON body để thay principal đã được decoder xác minh.
- Invalid signature, expired token hoặc wrong audience phải bị từ chối; không được nhận Authentication do một request trước đó trên thread pool để lại.
- Token A logout/revoke theo policy: nếu self-contained JWT chưa hết hạn và không có revocation, phải hiểu rõ đặc tính đó; không giả định session logout tự hủy JWT.
- Nếu dùng cache `JWT claims → authorities`, cache key phải phản ánh credential/issuer/tenant/policy version, không chỉ đường dẫn `/api/me`.
- Với opaque token introspection, lỗi backend và dữ liệu user A/B phải được map độc lập; không dùng một `OAuth2AuthenticatedPrincipal` mutable singleton.
- Test `JwtGrantedAuthoritiesConverter` hoặc converter custom ở unit level, sau đó test HTTP qua `SecurityWebFilterChain`/`SecurityFilterChain` tương ứng.

**Đừng nhầm `@WithMockUser` với real JWT verification:** request post-processor `.jwt()` trong Spring Security Test thường tạo Authentication giả để test authorization, không tự chứng minh signature/issuer/audience verification. Muốn kiểm thử toàn bộ security pipeline cần decoder/issuer test hoặc integration test token thật phù hợp.

## 21. Header, cache và gateway: principal đúng nhưng response sai

Lỗi cross-user data leak có thể xảy ra **ngoài Spring Security**:

```text
Alice -> GET /api/account/summary -> CDN cache bởi URL
Bob   -> GET /api/account/summary -> CDN trả cache của Alice
```

Server ở request B có thể đã xác thực Bob đúng, nhưng cache layer dùng **key không phân biệt user** và phục vụ dữ liệu Alice. Do đó cần test qua deployment/gateway khi production có cache.

Biện pháp:
- Với response cá nhân/nhạy cảm, cân nhắc `Cache-Control: private, no-store` hoặc policy cache tương đương.
- Không cache response có data user dưới một key global chỉ dựa vào URL/path.
- Nếu phải cache, dùng key chứa principal/tenant/permissions/policy version và cơ chế invalidation đúng; không đưa raw token làm key hiển thị trong logs/metrics.
- Kiểm tra reverse proxy và HTTP `Vary` phù hợp; không coi `Vary: Authorization` là bảo đảm duy nhất cho mọi CDN.
- Không trả thông tin riêng trước auth/authorization filter; bảo vệ streaming/SSE trước khi commit response.
- Kiểm tra GraphQL DataLoader/cache per-request: một DataLoader singleton có cache theo ID nhưng không scope tenant có thể trả object của B cho A.
- Với WebSocket, principal được gắn ở handshake/session; phải xác minh permission cho subscription/topic và khi quyền thay đổi. Một connection khác của Bob không được nhận event dành cho Alice.
- Khi dùng gateway có pre-auth headers, chỉ tin headers từ proxy đã xác thực và bị chặn spoof từ client.

Điều này nhắc lại: test `SecurityContextHolder` là cần nhưng **không đủ** để chứng minh không lộ dữ liệu người dùng.

## 22. Trạng thái thay đổi trong khi các request còn chạy

Kiểm thử song song phải tính đến **thời điểm thay đổi security state**:

### Case A: Logout trong khi một request khác đang xử lý

```text
t0: Alice mở request A1 (đã xác thực)
t1: Alice logout trên một request A2
t2: A1 vẫn đang chạy
t3: Một request mới A3 sau logout
```

Không thể luôn yêu cầu A1 tự bị hủy ngay tại t1; điều này phụ thuộc vào chính sách/session và việc request đã được authorize trước đó. Nhưng A3 phải tuân thủ logout/revocation và không thể “tái xuất hiện” Authentication cũ do một thread/session write race.

### Case B: Alice và Bob đăng nhập cùng lúc

- Cookie jars phải tách biệt.
- CSRF token và session state của mỗi client đi đúng pair.
- Mỗi login mới chỉ ghi `SecurityContext` vào repository/session đúng đối tượng.
- Login thất bại của B không được xóa session A.
- Audit events có actor identity và correlation IDs đúng.
- Với `SecurityContextRepository` custom, kiểm tra key/session ID không bị ghi đè.

### Case C: Đổi role trong lúc request đang chạy

- Request đã authorize có thể dùng quyền snapshot tại thời điểm bắt đầu.
- Request mới phải tuân thủ chính sách reload/revoke/quyền vừa cập nhật.
- Không nên mặc nhiên xem thay role trong DB là thay ngay mọi `Authentication` đang lưu session hoặc JWT đã cấp.
- Nếu nghiệp vụ yêu cầu hiệu lực ngay, thiết kế **revocation/version check** riêng.

### Case D: Hai request ghi dữ liệu của cùng user

Đây còn là vấn đề **business concurrency**: có thể cần optimistic locking, unique constraint, idempotency và transaction. Test không rò danh tính **không** chứng minh không mất cập nhật hoặc double-charge. Mỗi yêu cầu phải có assertion riêng, nhất là khi thao tác thay đổi quyền/credential hoặc redeem recovery token.

## 23. Ma trận kiểm thử tổng hợp

| Nhóm | Bối cảnh song song / nối tiếp | Điều kiện pass |
| --- | --- | --- |
| Context | A và B dùng hai thread cùng lúc | Context mỗi thread là đúng principal |
| Thread reuse | A kết thúc, B chạy trên cùng pooled thread | Không còn A trong B |
| Anonymous | A authenticated, anonymous GET song song | Anonymous không thấy A |
| Login success | A/B login đúng trên hai client riêng | Đúng account và quyền riêng |
| Login failure | A đúng, B sai mật khẩu | B không kế thừa A; A không bị mất phiên |
| Role | A user, C admin cùng lúc | A không có `ROLE_ADMIN`; C có |
| Session | Cookie A vs cookie B | A thấy A, B thấy B |
| Same-browser tabs | Một cookie jar, đổi account giữa tab | Đúng semantics của một session, không coi là hai session |
| Logout | Logout A trong khi B gửi request | B vẫn hợp lệ; A bị từ chối theo policy |
| Password reset | Reset A trong khi B đang login | Token/session của B không bị gắn nhầm A |
| `@Async` | Job A rồi B trong một executor | Job A dùng A, Job B dùng B, cleanup sau mỗi job |
| Job failure | Job A ném exception rồi job B chạy | Context A không rò sang B |
| WebFlux | Alice/Bob `Mono` interleave | Reactor Context không trộn |
| JWT | JWT A/B/invalid xen kẽ | Claims/authorities đúng token, invalid bị từ chối |
| Ownership | A truy cập object B | 403/404; không có data của B trong response |
| Tenant | Hai account trùng ID ở tenant khác | Query/cache scope tenant đúng |
| Cache | CDN/app cache nhận request A rồi B | B không thấy payload A |
| Session fixation | Login đổi session ID | Auth context gắn session mới đúng |
| Concurrent sessions | Cùng user login hai browser | Chính sách maximumSessions được thực thi |
| User revoked | Disable/role revoke trong lúc có request | Request mới theo revocation policy |
| Multi-node | A/B qua nhiều nodes | Session/cache/store không trộn actor |
| Audit | Interleave log events A/B | Actor, tenant, request ID chính xác |

### Test data nên mang dấu vết rõ

Dùng record giả:

```json
{
  "ownerId": "alice",
  "tenantId": "tenant-a",
  "marker": "ALICE_PRIVATE_TEST_ONLY"
}
```

Và record Bob với marker khác. Test body của Bob **không chứa** marker Alice. Đừng dùng dữ liệu nhạy cảm thật để phát hiện leak; fixture chỉ cần đủ phân biệt.

## 24. Tránh test flaky và false positives

**Test concurrent sai cách:**

```java
// Không có bảo đảm cùng lúc, còn dùng sleep theo may rủi.
Thread.sleep(100);
```

Thay bằng `CountDownLatch`, `CyclicBarrier`, `Phaser` hoặc điều phối mock dependency có kiểm soát. Dùng timeout để test không treo CI vô hạn.

Những quy tắc nên áp dụng:

1. **Barrier trước công việc cần kiểm chứng:** ít nhất hai worker phải chạm điểm hẹn. Nếu dùng test ở controller/business layer, có thể gắn barrier ở một test-only service, không chèn blocking barrier vào production.
2. **Tách expected dữ liệu:** expected actor nằm trong `Callable`/immutable record của từng request.
3. **Bắt exception:** gọi `Future.get`, đừng chỉ `pool.execute` mà không thu failure.
4. **Cleanup:** `shutdownNow`/`awaitTermination`, `SecurityContextHolder.clearContext`, close test clients/sessions khi cần.
5. **Không đổi SecurityContextHolder strategy global giữa tests song song** nếu thiếu isolation, vì chiến lược là JVM-wide.
6. **Không dùng một `MockHttpSession` chung** khi mục tiêu là hai browser độc lập.
7. **Không dùng cùng cookie store** rồi nhầm session mixing do test tự tạo là lỗi server.
8. **Không dùng `@WithMockUser` thay real login** nếu mục tiêu là xác minh provider/authentication filter.
9. **Đừng đồng nhất thứ tự `Future` completion với thứ tự input**; dùng mapping actor-request.
10. **Không chỉ assert 200:** phải assert name, authorities, tenant, resource content và negative paths.
11. **Giới hạn tải:** kiểm thử đồng thời với số request có kiểm soát, không tạo load test ngẫu nhiên lên production.
12. **Repeat có chủ đích:** chạy nhiều seeds/iterations trong CI hoặc môi trường staging để tìm race xác suất thấp; không dựa trên một lần pass.
13. **Không che lỗi bằng retry:** nếu retry làm một race biến mất, giữ log/correlation và một bài regression test riêng để sửa nguyên nhân.
14. **Phân biệt failure hạ tầng:** timeout/429/503 do test overload không được gán nhãn “rò danh tính”; kiểm tra service capacity và phân loại lỗi.
15. **Không bật parallel test suite rộng quá sớm:** JUnit parallel test execution có thể thay đổi trạng thái singleton, cache và context test fixtures, gây nhiễu. Cô lập fixture và dùng resource locks khi cần.

### Kiểm thử cố định thời gian

Tránh `Thread.sleep` để “đợi login xong” hoặc “đợi session hết hạn”. Sử dụng `Clock` inject được cho TTL, latch/barrier cho race và event hooks trong test. Với HTTP real session expiry, có thể test cấu hình TTL ngắn ở test profile hoặc dùng API quản lý session có kiểm soát thay vì sleep dài không ổn định.

## 25. Quan sát và điều tra khi nghi ngờ leak

Những dấu hiệu production:
- User khi refresh trang thấy tên người khác vài lần rồi tự hết.
- Log actor khác với `sub` trong token đã được xác minh.
- API response có `ownerId` khác principal dù request authenticated.
- Vấn đề chỉ xảy ra khi traffic cao hoặc có background jobs.
- Các request khác user cùng hit một shared cache key.
- Sau job thất bại, job kế tiếp có authorities của user trước.
- CDN/browser cache trả profile người khác.
- Logout của một user tác động lên session không liên quan.

Khi điều tra:
- Theo dõi **requestId**, trace/span, principal internal ID và tenant ID **được server xác minh**, session **pseudonymous ID** nếu cần.
- Không log raw cookie, access/refresh tokens, password, OTP hay user PII không cần thiết.
- Ghi các sự kiện: auth success/failure, session create/rotate/logout/revoke, principal resolution, authorization deny, context propagation, cache hit/miss.
- Có thể thêm alert khi `response.ownerId` khác `authenticated.subject` ở điểm kiểm soát nghiệp vụ, nhưng cân nhắc privacy.
- Chụp **bằng chứng kiểm thử nhân tạo** (fixture), không gửi dữ liệu khách hàng thật cho bên thứ ba.
- Dùng correlation per request, không dùng một `ThreadLocal` logging context mà quên clear ở cuối request.
- Với lỗi đã được xác nhận có lộ dữ liệu, cần xử lý như security incident: chặn nguồn rò, điều tra phạm vi, thực hiện thông báo theo chính sách/pháp lý và thêm regression tests.

**Không sửa bằng cách “thêm synchronized vào mọi endpoint”.** Nếu gốc lỗi là singleton `currentUser`, đồng bộ hóa có thể chỉ giảm race tạm thời nhưng vẫn không tạo identity per-request. Sửa scope/ownership của state mới là biện pháp đúng.

## 26. Câu hỏi tự kiểm tra

**Câu 1.** Alice và Bob cùng GET `/api/me`, đều nhận HTTP 200. Có thể kết luận không rò identity không?

**Trả lời:** Không. Phải assert `username`/authorities trong body (hoặc thông tin trả về khác) tương ứng đúng request, và kiểm tra owner data. Hai response 200 không đủ.

**Câu 2.** Trong Servlet, `SecurityContextHolder` mặc định dùng `ThreadLocal`, vậy vì sao còn có leak?

**Trả lời:** Vì code tùy chỉnh có thể dùng một `SecurityContext` mutable chung, lưu principal trong singleton/static field, truyền context sai cho executor hoặc không clear ThreadLocal tự tạo. Spring filter chain không sửa các anti-pattern của application.

**Câu 3.** `ThreadLocal.remove()` trong `finally` quan trọng như thế nào?

**Trả lời:** Nó ngăn thread pool giữ identity của task trước sau khi task kết thúc, kể cả khi exception xảy ra. Với Spring-managed servlet request, framework dọn SecurityContextHolder; với tự quản thread/task, phải áp dụng cơ chế propagation/cleanup đúng.

**Câu 4.** Hai tab trong cùng Chrome profile đăng nhập Alice và Bob có phải hai session không?

**Trả lời:** Thường không. Hai tab thường dùng cùng cookie jar, vì vậy có thể cùng một session. Dùng hai profiles/contexts hoặc hai cookie jars khi test session isolation.

**Câu 5.** `maximumSessions(1)` có bảo đảm session Bob không nhìn thấy Alice không?

**Trả lời:** Không. Nó giới hạn số session của cùng account theo policy. Vẫn phải test principal, cookie, SecurityContextRepository và resource ownership.

**Câu 6.** Vì sao `@WithMockUser("alice")` không đủ để kiểm thử login song song thực?

**Trả lời:** Nó gắn Authentication giả cho test, không chứng minh HTTP login/credential validation, session cookie, concurrency hay context persistence của ứng dụng.

**Câu 7.** Trong WebFlux, có nên đọc `SecurityContextHolder` ở mọi `flatMap()` không?

**Trả lời:** Không. Spring Security WebFlux dựa trên Reactor Context; dùng `ReactiveSecurityContextHolder` hoặc injection phù hợp. ThreadLocal không gắn duy nhất với một reactive subscription.

**Câu 8.** API của Bob trả `principal=bob` nhưng trả đơn hàng Alice. Có phải bài test identity đã pass?

**Trả lời:** Kiểm thử principal có thể pass, nhưng **kiểm thử data ownership thất bại nghiêm trọng** (IDOR/BOLA). Phải bổ sung authorization per-object/tenant.

**Câu 9.** Có nên tạo một `DelegatingSecurityContextExecutorService(raw, aliceContext)` rồi submit mọi request user khác qua nó?

**Trả lời:** Không. Constructor với `SecurityContext` cố định có thể chạy tất cả jobs dưới Alice. Với hệ thống đa người dùng, truyền context đúng theo từng task hoặc dùng wrapper capture tại submission phù hợp, kèm cleanup.

**Câu 10.** Một lần chạy song song 30 requests đều đúng có chứng minh vĩnh viễn không có race không?

**Trả lời:** Không. Nó là một lớp regression test. Cần test request/session/async/object ownership ở nhiều điều kiện, chạy lặp theo seeds/tải có kiểm soát, và review kiến trúc shared state.

## 27. Checklist release và lời kết

Trước khi kết luận chức năng đăng nhập an toàn trong môi trường nhiều người dùng, cần bảo đảm:

- [ ] Có ít nhất hai/ba test users với role, tenant và private-data markers khác nhau.
- [ ] Concurrent HTTP tests so principal và **tập authorities chính xác**, không chỉ HTTP 200.
- [ ] Test A/B trên hai sessions/cookie jars riêng khi ứng dụng dùng form login.
- [ ] Test anonymous không kế thừa auth từ request trước trên pooled thread.
- [ ] Không có singleton/static mutable field chứa `currentUser`/`Authentication` cho toàn bộ ứng dụng.
- [ ] `SecurityContext` được tạo và lưu riêng đúng request/session; không chia sẻ mutable instance giữa users.
- [ ] Custom login dùng `SecurityContextRepository.saveContext(...)` khi muốn lưu phiên.
- [ ] Task executor/`@Async` truyền context đúng theo caller hoặc chạy dưới service principal rõ ràng, luôn cleanup.
- [ ] Reactive code dùng Reactor Context, không dựa vào ThreadLocal như Servlet.
- [ ] JWT/opaque token mapper/cache không trộn claims/authorities giữa users/tenants.
- [ ] Quyền trên từng object và tenant được kiểm chứng; không chỉ `isAuthenticated()`.
- [ ] Logout, change-account, session fixation, role revoke có test riêng.
- [ ] Same-user concurrent-session limit được test độc lập với cross-user isolation.
- [ ] Có negative tests: token sai, password sai, access denied, object của người khác, cache hit.
- [ ] Không có cache response riêng tư dùng key global cho nhiều users.
- [ ] `Future.get`/timeouts/cleanup giúp concurrent test fail đáng tin, không treo CI.
- [ ] Chạy regression tests qua HTTP/cluster/gateway khi kiến trúc thực sự có các tầng đó.
- [ ] Logs và monitoring không ghi raw secrets/cookies nhưng đủ correlation để phát hiện actor sai.

**Kết luận:** trong hệ thống Spring Security, nguyên tắc cách ly danh tính là **mỗi request/job nhận đúng security context và quyền của nó, không có state chung có thể làm tráo hoặc mở rộng quyền giữa người dùng**. Kiểm thử phải áp dụng đồng thời ở cấp **thread**, **authentication filter**, **session**, **async/reactive context**, **authorization trên object** và **hạ tầng cache/gateway**. Bài test mạnh nhất là một test chạy đồng thời có kỳ vọng cụ thể theo actor và một tập negative cases đủ để chứng minh không có đường đi nào trả dữ liệu của người khác.

## 28. Tài liệu tham khảo chính thức

- Spring Security 6.5 — Servlet Authentication Architecture (`SecurityContextHolder`, createEmptyContext, ThreadLocal): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — Concurrency Support (`DelegatingSecurityContextRunnable`, Executor): https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html
- Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — Session Management / Concurrent Sessions: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security 6.5 — MockMvc Security Setup: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html
- Spring Security — Testing Form Based Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html
- Spring Security 6.5 API — `DelegatingSecurityContextCallable`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/concurrent/DelegatingSecurityContextCallable.html
- Spring Security 6.5 API — `DelegatingSecurityContextExecutorService`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/concurrent/DelegatingSecurityContextExecutorService.html
- Spring Security 6.5 — Reactive Method Security and Reactor Context: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security 6.5 — Testing Authentication and MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html
- OWASP — Authorization Cheat Sheet (kiểm soát quyền mỗi object): https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — API Security Top 10: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
