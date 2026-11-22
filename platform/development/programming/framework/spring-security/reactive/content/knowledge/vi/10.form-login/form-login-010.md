# Giới hạn thử đăng nhập và phòng chống dò mật khẩu ở tầng ứng dụng

> **Chủ đề:** Spring Security – reactive  
> **Nhóm kiến thức:** Đăng nhập biểu mẫu  
> **Trọng tâm:** Thiết kế login throttling cho `POST /login` của Spring Security WebFlux: đếm lần xác thực sai, giới hạn theo tài khoản và nguồn gửi, khóa tạm thời có thời hạn, phản hồi không tiết lộ tài khoản, và kiểm thử được bằng `WebTestClient`.

## 1. Vì sao biểu mẫu đăng nhập cần chống dò mật khẩu?

Một biểu mẫu đăng nhập hợp lệ có thể bị lạm dụng để thử hàng nghìn cặp tên đăng nhập/mật khẩu. Mật khẩu được băm bằng BCrypt/Argon2 không đủ để ngăn hành vi này: thuật toán băm giúp bảo vệ mật khẩu **đang lưu trong cơ sở dữ liệu**, còn ở thời điểm đăng nhập server vẫn phải kiểm tra từng mật khẩu được gửi tới. Nếu không có biện pháp giới hạn, đối tượng tấn công có thể khai thác tốc độ gửi request, password yếu, password tái sử dụng và tài khoản có đặc quyền.

Cần phân biệt một số dạng tấn công:

| Kiểu tấn công | Mô tả | Vì sao một luật đơn lẻ chưa đủ |
| --- | --- | --- |
| **Brute force** | Thử nhiều mật khẩu trên một tài khoản | Giới hạn theo **tài khoản** giúp chặn ngay cả khi nguồn IP thay đổi |
| **Password spraying** | Dùng một số mật khẩu phổ biến trên nhiều username | Chỉ khóa từng tài khoản sau ba lần sai có thể không bắt được |
| **Credential stuffing** | Thử các cặp username/password đã lộ từ dịch vụ khác | Mật khẩu có thể đúng ở lần thử đầu; cần MFA, phân tích rủi ro và phát hiện bất thường |
| **Distributed attack** | Chia request cho nhiều IP/thiết bị/instance | Chỉ giới hạn theo một IP hoặc chỉ lưu counters trong bộ nhớ một server có thể bị vượt qua |
| **Account enumeration** | So sánh thông báo/thời gian để biết username có tồn tại | Phản hồi “tài khoản bị khóa” khác “tài khoản không tồn tại” có thể tạo side channel |
| **Lockout denial of service** | Cố tình nhập sai để khóa người dùng thật | Khóa cứng dài hoặc vĩnh viễn có thể biến biện pháp phòng vệ thành công cụ gây gián đoạn |

Mục tiêu là **giảm tốc độ thử mật khẩu và tăng khả năng phát hiện**, không phải hứa rằng một bộ đếm sẽ loại bỏ mọi kiểu tấn công. Chính sách tốt kết hợp nhiều lớp: account-aware throttling, IP/device/risk throttling, MFA, bảo vệ mật khẩu, observability, giới hạn hạ tầng, phương án khôi phục và kiểm tra hành vi.

### Mục tiêu học tập

1. Chọn đúng khóa giới hạn (`account`, IP đã xác minh, `account+IP`, tenant) và hiểu điểm yếu của mỗi loại.
2. Thiết kế bộ đếm với **ngưỡng**, **cửa sổ quan sát**, **thời gian chặn** và **điều kiện xóa bộ đếm**.
3. Đặt chốt kiểm tra **trước khi xác thực mật khẩu** và ghi nhận kết quả sau khi xác thực, thay vì chỉ chặn trong controller.
4. Tích hợp với `ReactiveAuthenticationManager` và `ServerHttpSecurity.formLogin(...)`, giữ nguyên CSRF/session/redirect của WebFlux.
5. Viết ví dụ Java 17+ runnable với clock điều khiển được trong test; biết rõ giới hạn của demo bộ nhớ.
6. Đánh giá concurrency, Redis TTL/atomic operations, log bí mật, NAT/proxy, UX và cách phản hồi khi throttled.

## 2. Tầng nào chịu trách nhiệm?

Trong Spring WebFlux, form login chạy qua **Spring Security WebFilter chain**, không phải Servlet `UsernamePasswordAuthenticationFilter` hay `HttpSecurity`. Luồng giản lược:

```text
Browser gửi GET /login
  └── Form đăng nhập + CSRF token

Browser gửi POST /login
 Content-Type: application/x-www-form-urlencoded
 username=...&password=...&_csrf=...
  |
  v
CsrfWebFilter / SecurityWebFilterChain
  |
  v
AuthenticationWebFilter (form login)
  |
  v
ServerFormLoginAuthenticationConverter
  |
  v
ReactiveAuthenticationManager có giới hạn thử
  |       |
  |       +-- throttle blocked --> AuthenticationException
  |       |
  |       +-- chưa blocked --> authentication manager thật
  |                              |
  |                              +-- bad credentials --> tăng đếm
  |                              |
  |                              +-- success --> xóa/giảm bộ đếm
  v
ServerAuthenticationSuccessHandler / ServerAuthenticationFailureHandler
  |                                             |
  +-- redirect sau đăng nhập thành công         +-- redirect về /login?error
  |
  v
WebSession / Reactor SecurityContext cho request tiếp theo
```

Một vài điểm quan trọng:

- **CSRF chạy trước việc xử lý POST login** ở trường hợp cấu hình mặc định. POST thiếu CSRF token thường bị 403 **trước khi** tới authentication manager. Không ghi một sự kiện “mật khẩu sai” cho lỗi CSRF.
- `ReactiveAuthenticationManager` là nơi phù hợp để áp chính sách **dựa trên danh tính đăng nhập** trước khi kiểm tra password; nó có `Authentication.getName()` và thấy kết quả xác thực. Nếu giới hạn theo IP/ASN/thiết bị cần thêm thông tin request, hãy dùng một thành phần WebFilter/gateway được thiết kế để thu thập nguồn gửi một cách tin cậy.
- `ServerAuthenticationFailureHandler` giúp xử lý response khi authentication thất bại; **chỉ tùy biến failure handler mà không chặn ở trước password check** thì không ngăn được chi phí xác thực hoặc những lần thử song song.
- **Authorization** (`hasRole`, `@PreAuthorize`) xảy ra sau/khác authentication. Người dùng đã đăng nhập mà thiếu quyền thường nhận 403; đây không phải sự kiện “thử mật khẩu sai”.
- Với Spring Security reactive, form login dùng `ServerHttpSecurity.formLogin`, `SecurityWebFilterChain`, `AuthenticationWebFilter`, `ReactiveAuthenticationManager` và `ServerAuthenticationFailureHandler`.

## 3. Thiết kế chính sách: ngưỡng, cửa sổ, cooldown

Một bộ chính sách cần trả lời rõ:

| Tham số | Câu hỏi | Giá trị **chỉ dùng trong demo** |
| --- | --- | --- |
| `MAX_FAILURES` | Bao nhiêu password sai mới chặn? | **3** |
| `WINDOW` | Các lỗi được quan sát trong bao lâu? | **10 phút** |
| `COOLDOWN` | Chặn tạm thời trong bao lâu? | **2 phút** |
| Key | Lỗi của ai được gom chung? | Username nhập vào, so khớp chính xác |
| Reset | Khi nào xóa lỗi? | Xác thực thành công hoặc bắt đầu cửa sổ mới |
| Phản hồi | Có tiết lộ blocked/unknown/wrong không? | Không; chung `/login?error` |
| State storage | Counter đặt ở đâu? | `ConcurrentHashMap` **chỉ demo một JVM** |

Đây là các giá trị phục vụ kiểm thử nhanh, **không phải khuyến nghị ngưỡng production mặc định**. Chính sách thực phải dựa trên risk, SLO, dữ liệu vận hành, mức độ nhạy cảm của tài khoản, traffic của tổ chức, MFA và hậu quả khóa nhầm.

### 3.1. Quy tắc chuyển trạng thái

Gọi `n` là số lần nhập sai hiện có của tài khoản trong cửa sổ đang hiệu lực.

1. Chưa có state: xác thực được thử, nếu sai thì `n=1`.
2. Sai lần thứ 2 khi chưa hết cửa sổ: `n=2`.
3. Sai lần thứ 3: `n=3`, đánh dấu `blockedUntil = now + COOLDOWN`.
4. Trong lúc khóa tạm: mọi lần thử từ tài khoản đó (kể cả password đúng) bị từ chối **trước khi kiểm tra mật khẩu**.
5. Sau khi hết cooldown: cho thử lại; lần thất bại kế tiếp khởi tạo cửa sổ mới. Thành công xóa bộ đếm.
6. Nếu quá `WINDOW` mà chưa chạm ngưỡng: lần thất bại mới bắt đầu cửa sổ mới.

**Đừng nhầm “3 lần sai là khóa” với “lần gửi thứ 4 mới tăng đếm”:** Demo tạo trạng thái blocked ngay khi ghi nhận lỗi thứ ba, nhưng phản hồi của cả ba lỗi vẫn là redirect chung. Request thứ tư gặp gate chặn trước việc xác minh password.

```text
                         +------------------+
                         | Không có failure |
                         +--------+---------+
                                  |
                           sai lần 1/2
                                  |
                         +--------v---------+
                         | Đếm failure      |
                         | trong WINDOW     |
                         +---+----------+---+
                             |          |
                 password đúng          đủ 3 failure
                             |          |
                         xóa state      v
                             |   +------+-------+
                             |   | BLOCKED      |
                             |   | tới deadline |
                             |   +------+-------+
                             |          |
                             |       hết COOLDOWN
                             |          |
                             +----------v
                               Cho thử lại
```

### 3.2. Giới hạn theo key nào?

**Theo tài khoản:** chống brute force từ nhiều IP nhưng có thể bị lợi dụng để DoS bằng khóa tài khoản người khác. Key phải dựa trên cùng chính sách canonicalization của user store. Nếu DB phân biệt hoa/thường mà limiter tự lowercase thì có thể gom hai tài khoản khác nhau; nếu DB không phân biệt nhưng limiter phân biệt thì attacker có thể đổi chữ hoa/thường để né hạn mức.

**Theo IP:** giới hạn burst và password spraying nhưng không đủ để chặn botnet/rotating proxy. Một IP có thể là NAT của cả văn phòng, trường học hoặc mạng di động; khóa toàn bộ IP dễ gây false positive.

**Theo cặp `account + IP`:** giúp giới hạn trong một nguồn cụ thể nhưng chỉ dùng cặp này sẽ cho một attacker phân phối thử trên vô số IP. Có thể kết hợp **account-wide limit + IP-wide limit + account/IP limit**, mỗi loại với policy riêng.

**Theo thiết bị/cookie/ASN/tenant:** dùng như tín hiệu bổ sung, không được coi cookie tự khai hoặc `X-Forwarded-For` do client tự gửi là danh tính đáng tin. IP phía sau proxy chỉ lấy theo cấu hình trusted proxy và `ForwardedHeaderTransformer`/hạ tầng đã được kiểm soát; không mặc định tin phần tử đầu của `X-Forwarded-For`.

## 4. Vì sao “chỉ kiểm tra sau khi login fail” chưa đủ?

Nếu chỉ gọi `recordFailure(username)` ở `ServerAuthenticationFailureHandler` mà **không kiểm tra trước**, server vẫn trả lời mọi request bằng cách thử password (có thể gọi DB và BCrypt) rồi mới cập nhật bộ đếm. Attacker vẫn có thể dùng hàng trăm request song song để tiêu thụ tài nguyên.

Một mô hình chuẩn hơn là:

```text
1. Nhận authentication attempt có username.
2. Kiểm tra policy trước khi kiểm tra password.
3. Nếu blocked: không gọi password verifier; trả AuthenticationException chung.
4. Nếu được phép: gọi delegate.authenticate(...).
5. Thành công: ghi nhận success và reset failure state thích hợp.
6. Sai credentials: tăng failure counter.
7. Lỗi hạ tầng: ghi alert riêng, KHÔNG tự tăng “sai mật khẩu”.
```

Đưa gate vào **`ReactiveAuthenticationManager` decorator** giúp test được thuật toán độc lập và không thay đổi cách Spring Security parse form login. Trong ứng dụng phân tán, bước 2 và 6 phải tính tới race/in-flight attempts; mục 11 thảo luận cách xử lý atomicity.

### 4.1. Phân loại lỗi

| Loại lỗi | Có đếm là password sai? | Ví dụ |
| --- | --- | --- |
| `BadCredentialsException` | **Có** | Password không đúng |
| `UsernameNotFoundException` nếu được phát ra | **Có**, nhưng không tiết lộ ra client | Không tìm thấy account |
| `LockedException` do chính gate tạo | **Không tăng lặp** | Cooldown đang hiệu lực |
| `AuthenticationServiceException` / lỗi DB | **Không** | Provider unavailable, timeout |
| CSRF 403 | **Không** | Token CSRF không hợp lệ |
| Authorization 403 | **Không** | User đã đăng nhập nhưng thiếu quyền |
| Password reset/OTP failure | **Chính sách riêng** | Không dùng chung counter một cách tùy tiện |

Spring Security có thể che giấu nguyên nhân username không tồn tại bằng `BadCredentialsException`. Hãy test kiểu `ReactiveAuthenticationManager` bạn thực sự sử dụng. Đừng log credential, password, token hoặc raw exception chứa thông tin nhạy cảm.

## 5. Project Java 17+ runnable với Spring Security WebFlux

Đây là một **ví dụ học tập một JVM** dùng Spring Boot **3.5.16** (nhánh Spring Security 6.x được quản lý bởi Boot), Maven, JUnit và `WebTestClient`. Spring Boot 3.5.16 đã kết thúc hỗ trợ OSS cho nhánh 3.5; production mới nên chọn nhánh còn được hỗ trợ, theo migration guide thích hợp. Mã tập trung vào **form login**. Thuật toán in-memory của ví dụ **không an toàn để dùng nguyên trạng cho nhiều server hoặc traffic song song lớn**.

**Quyết định thiết kế:**

- User demo `alice` có mật khẩu `welcome123`, được lưu dưới dạng BCrypt hash do ứng dụng tạo lúc khởi động.
- Form login mặc định `GET /login`, `POST /login`, form fields `username`, `password` và CSRF token.
- Sai mật khẩu: redirect chung `/login?error`; không công khai “sai password”, “user không tồn tại” hay “đang khóa”.
- Đúng mật khẩu: redirect `/home`; Spring Security xử lý SecurityContext cho phiên.
- Ba lần sai trong cửa sổ 10 phút chặn thử mật khẩu trong 2 phút.
- `/public` cho người chưa đăng nhập; `/home` yêu cầu xác thực.
- HTTP Basic tắt để test không vô tình đi qua cơ chế khác.
- Thử nghiệm sử dụng credentials thật trong form và `csrf()` của Spring Security Test, không dùng `mockUser` làm bằng chứng cho password validation.

### 5.1. Cấu trúc thư mục

```text
form-login-throttle/
├── pom.xml
└── src/
    ├── main/java/demo/login/
    │   ├── Application.java
    │   ├── LoginAttemptLimiter.java
    │   ├── ThrottledAuthenticationManager.java
    │   ├── SecurityConfiguration.java
    │   └── PageController.java
    └── test/java/demo/login/
        ├── LoginAttemptLimiterTests.java
        └── FormLoginThrottleTests.java
```

### 5.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>form-login-throttle</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot parent/BOM quản lý phiên bản Spring Security, Reactor và các dependency phù hợp. Không chèn version riêng cho `spring-security-test` để tránh lệch API. `spring-boot-starter-test` mang JUnit/Spring Test, `spring-security-test` mang helper `csrf()` và `springSecurity()`.

### 5.3. `src/main/java/demo/login/Application.java`

```java
package demo.login;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 5.4. `src/main/java/demo/login/LoginAttemptLimiter.java`

Đây là bộ đếm **fixed observation window + cooldown** dùng `Clock` truyền vào. `ConcurrentHashMap.compute` giúp cập nhật một key theo cách atomic trong **cùng JVM**. Bản demo cố ý không chứa DB/Redis hay cleanup nền và **không bảo đảm gate check + delegate authentication atomic trong trường hợp có nhiều request song song**.

```java
package demo.login;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public final class LoginAttemptLimiter {
    private static final int MAX_FAILURES = 3;
    private static final Duration WINDOW = Duration.ofMinutes(10);
    private static final Duration COOLDOWN = Duration.ofMinutes(2);

    private final ConcurrentMap<String, State> states =
        new ConcurrentHashMap<>();
    private final Clock clock;

    private record State(
        Instant firstFailure,
        int failures,
        Instant blockedUntil
    ) {}

    public LoginAttemptLimiter(Clock clock) {
        this.clock = clock;
    }

    public boolean isBlocked(String username) {
        State state = states.get(username);
        return state != null
            && state.blockedUntil() != null
            && clock.instant().isBefore(state.blockedUntil());
    }

    public void recordFailure(String username) {
        Instant now = clock.instant();
        states.compute(username, (key, old) -> {
            // New account, expired observation window, or expired cooldown.
            if (old == null
                    || !now.isBefore(old.firstFailure().plus(WINDOW))
                    || (old.blockedUntil() != null
                        && !now.isBefore(old.blockedUntil()))) {
                return new State(now, 1, null);
            }

            // Do not keep incrementing during cooldown.
            if (old.blockedUntil() != null) {
                return old;
            }

            int failures = Math.min(MAX_FAILURES, old.failures() + 1);
            Instant blockedUntil = failures >= MAX_FAILURES
                ? now.plus(COOLDOWN) : null;

            return new State(old.firstFailure(), failures, blockedUntil);
        });
    }

    public void recordSuccess(String username) {
        states.remove(username);
    }

    public int failureCount(String username) {
        State state = states.get(username);
        return state == null ? 0 : state.failures();
    }

    // Chỉ dành cho ví dụ/test trong package demo.login.
    void clearForTests() {
        states.clear();
    }
}
```

**Các bất biến quan trọng:**

- `State` là Java `record`, các field của chính State bất biến. `compute` thay giá trị cho một key bằng State mới; không có `get` → `put` thiếu atomicity khi ghi failure.
- `Clock` được inject nên test có thể điều khiển thời gian, không cần `Thread.sleep(120000)`.
- Sau khi hết cooldown, `isBlocked` trả false. `recordSuccess` xóa state; `recordFailure` sau cooldown tạo cửa sổ mới.
- `failureCount()` chỉ dùng minh họa và kiểm thử; không trả số này cho client vì có thể giúp dò trạng thái account.
- **Username là khóa nhập vào đúng chuỗi.** Demo user store phân biệt chuỗi; nếu account production dùng quy tắc case-insensitive, phải canonicalize **đồng nhất** giữa limiter và user store. Không trim/lowercase username tùy tiện ở một chỗ.
- **Rủi ro memory:** Attacker tạo vô số username khác nhau khiến `ConcurrentHashMap` tăng không giới hạn. Production phải dùng storage có TTL, hạn mức key và giới hạn ingress.
- **Rủi ro race:** `isBlocked` và `recordFailure` là hai thao tác rời; nhiều request cùng qua gate trước khi có failure thứ ba. Production cần reservation/rate limiting atomic hoặc concurrency cap như mục 11.
- Đây là **giới hạn theo account**, chưa phải hệ thống chống credential stuffing hoàn chỉnh.

### 5.5. `src/main/java/demo/login/ThrottledAuthenticationManager.java`

Decorator này nhận `Authentication` chưa xác thực, kiểm tra khóa **trước** khi gọi manager thật, và ghi trạng thái sau khi có kết quả.

```java
package demo.login;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import reactor.core.publisher.Mono;

public final class ThrottledAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final ReactiveAuthenticationManager delegate;
    private final LoginAttemptLimiter limiter;

    public ThrottledAuthenticationManager(
            ReactiveAuthenticationManager delegate,
            LoginAttemptLimiter limiter) {
        this.delegate = delegate;
        this.limiter = limiter;
    }

    @Override
    public Mono<Authentication> authenticate(Authentication attempt) {
        // defer: kiểm tra hạn mức tại subscription, không phải assembly.
        return Mono.defer(() -> {
            String username = attempt.getName();

            if (limiter.isBlocked(username)) {
                return Mono.error(
                    new LockedException("Authentication temporarily unavailable"));
            }

            return delegate.authenticate(attempt)
                .doOnNext(result -> limiter.recordSuccess(username))
                .doOnError(error -> {
                    if (error instanceof BadCredentialsException
                            || error instanceof UsernameNotFoundException) {
                        limiter.recordFailure(username);
                    }
                });
        });
    }
}
```

Vì `ReactiveAuthenticationManager.authenticate` trả `Mono<Authentication>`, wrapper không gọi `block()` hoặc `subscribe()`. Nếu chưa blocked, delegate mới tiến hành kiểm tra password/DB theo cơ chế chuẩn. Nếu blocked, `LockedException` dừng trước delegate.

Chỉ các lỗi credentials đã chọn mới được tính. Với lỗi hạ tầng (`AuthenticationServiceException` hoặc những lỗi không thuộc `AuthenticationException` cần kiểm soát), hãy phát cảnh báo/telemetry thích hợp thay vì cộng vào `wrong-password count`.

**Giới hạn:** Spring Security có thể dùng nhiều cơ chế xác thực. Đảm bảo **form login thực sự dùng wrapper** qua `.authenticationManager(manager)`; nếu có đăng nhập qua OAuth2, passkey, magic link, MFA hoặc reset password, chính sách và event counting phải được thiết kế riêng. Đừng coi mọi `Authentication` hợp lệ là password login.

### 5.6. `src/main/java/demo/login/SecurityConfiguration.java`

```java
package demo.login;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    LoginAttemptLimiter loginAttemptLimiter(Clock clock) {
        return new LoginAttemptLimiter(clock);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        // Chỉ là tài khoản demo; production không hardcode mật khẩu.
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("welcome123"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("hello456"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice, bob);
    }

    @Bean
    ReactiveAuthenticationManager formAuthenticationManager(
            MapReactiveUserDetailsService users,
            PasswordEncoder encoder,
            LoginAttemptLimiter limiter) {

        UserDetailsRepositoryReactiveAuthenticationManager delegate =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        delegate.setPasswordEncoder(encoder);

        return new ThrottledAuthenticationManager(delegate, limiter);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager formAuthenticationManager) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/login", "/public").permitAll()
                .pathMatchers("/home").authenticated()
                .anyExchange().denyAll()
            )
            .formLogin(form -> form
                .authenticationManager(formAuthenticationManager)
                .authenticationSuccessHandler(
                    new RedirectServerAuthenticationSuccessHandler("/home"))
                .authenticationFailureHandler(
                    new RedirectServerAuthenticationFailureHandler("/login?error"))
            )
            .httpBasic(basic -> basic.disable())
            .build();
    }
}
```

Các lựa chọn:

1. `formLogin(...)` bật form login mặc định của Spring Security WebFlux. Vì **không gọi `.loginPage(...)`**, Spring Security cung cấp trang login mặc định ở `GET /login` và xử lý `POST /login`.
2. `authenticationManager(formAuthenticationManager)` chỉ rõ bộ lọc đăng nhập dùng decorator throttling thay vì bỏ qua bộ đếm.
3. Success/failure redirect dùng đúng các handler reactive (`RedirectServerAuthenticationSuccessHandler`, `RedirectServerAuthenticationFailureHandler`) với **cùng thông báo lỗi chung**, không lộ trạng thái khóa.
4. `httpBasic(...disable())` làm bài tập tập trung vào form login, tránh test vô tình thành công nhờ Basic.
5. `CSRF` vẫn được bật theo mặc định. Trình duyệt phải nộp form với CSRF token; `WebTestClient` dùng `mutateWith(csrf())`.
6. `MapReactiveUserDetailsService` chỉ là nguồn user giả cho demo. Mật khẩu được lưu **dưới dạng BCrypt hash**, dù input mẫu vẫn xuất hiện rõ ràng trong source vì mục đích học tập.
7. Chỉ có **một** bean `ReactiveAuthenticationManager` (wrapper) được đăng ký; delegate được tạo cục bộ trong factory bean, tránh việc injection manager bị mơ hồ.
8. Form login có session/cookie theo cơ chế Spring Security. Đừng tùy tiện làm `NoOpServerSecurityContextRepository` nếu kỳ vọng người dùng vẫn đăng nhập sau redirect.

### 5.7. `src/main/java/demo/login/PageController.java`

```java
package demo.login;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PageController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public OK");
    }

    @GetMapping("/home")
    public Mono<String> home() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(username -> "Hello " + username);
    }
}
```

Trang `/home` là REST text endpoint thay cho trang HTML thật để demo gọn hơn. Kết quả chỉ xuất hiện sau khi Spring Security đã xác thực người dùng từ session. Không đọc username bằng query/header tùy ý để quyết định một người đã đăng nhập.

## 6. Kiểm thử chính sách bằng đồng hồ giả: không chờ hai phút thật

### 6.1. `src/test/java/demo/login/LoginAttemptLimiterTests.java`

Test trực tiếp thuật toán fixed-window và cooldown. Dùng `AdjustableClock` tự viết nên kết quả hoàn toàn xác định trong cùng JVM.

```java
package demo.login;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LoginAttemptLimiterTests {

    private static final class AdjustableClock extends Clock {
        private Instant now = Instant.parse("2026-01-01T00:00:00Z");

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return Clock.fixed(now, zone);
        }

        @Override
        public Instant instant() {
            return now;
        }

        void advance(Duration elapsed) {
            now = now.plus(elapsed);
        }
    }

    @Test
    void threeFailuresCauseTwoMinuteCooldown() {
        AdjustableClock clock = new AdjustableClock();
        LoginAttemptLimiter limiter = new LoginAttemptLimiter(clock);

        limiter.recordFailure("alice");
        limiter.recordFailure("alice");
        assertEquals(2, limiter.failureCount("alice"));
        assertFalse(limiter.isBlocked("alice"));

        limiter.recordFailure("alice");
        assertEquals(3, limiter.failureCount("alice"));
        assertTrue(limiter.isBlocked("alice"));

        clock.advance(Duration.ofMinutes(2));
        assertFalse(limiter.isBlocked("alice"));

        limiter.recordFailure("alice");
        assertEquals(1, limiter.failureCount("alice"));
    }

    @Test
    void successResetsOnlyItsOwnAccount() {
        LoginAttemptLimiter limiter =
            new LoginAttemptLimiter(Clock.systemUTC());

        limiter.recordFailure("alice");
        limiter.recordFailure("bob");
        limiter.recordSuccess("alice");

        assertEquals(0, limiter.failureCount("alice"));
        assertEquals(1, limiter.failureCount("bob"));
    }

    @Test
    void failureAfterObservationWindowStartsNewWindow() {
        AdjustableClock clock = new AdjustableClock();
        LoginAttemptLimiter limiter = new LoginAttemptLimiter(clock);

        limiter.recordFailure("alice");
        limiter.recordFailure("alice");

        clock.advance(Duration.ofMinutes(10));
        limiter.recordFailure("alice");

        assertEquals(1, limiter.failureCount("alice"));
        assertFalse(limiter.isBlocked("alice"));
    }
}
```

Test có **3 phương thức JUnit**. Test cho thấy:

- Ngay sau lần sai thứ ba, `isBlocked("alice")` là true.
- Sau đúng 2 phút, cooldown kết thúc; lần sai tiếp theo bắt đầu cửa sổ mới.
- Thành công chỉ xóa state của tài khoản đó.
- Hết 10 phút thì một lần sai tiếp theo bắt đầu lại đếm, không giữ vô hạn các lỗi cũ.

Không dùng `Thread.sleep` trong test này, không phụ thuộc tốc độ máy/CI.

## 7. Integration test thật cho `POST /login` và CSRF

Một test chỉ gọi `mockUser()` không hề chứng minh `ReactiveAuthenticationManager` đã kiểm tra password, nên **không đủ** để kiểm thử chống dò mật khẩu. Với form login, hãy gửi `application/x-www-form-urlencoded` và CSRF token hợp lệ.

### 7.1. `src/test/java/demo/login/FormLoginThrottleTests.java`

```java
package demo.login;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class FormLoginThrottleTests {

    @Autowired
    ApplicationContext applicationContext;

    @Autowired
    LoginAttemptLimiter limiter;

    private WebTestClient client;

    @BeforeEach
    void prepare() {
        limiter.clearForTests(); // Reset chỉ trong test.
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec login(
            String username, String password) {

        return client.mutateWith(csrf())
            .post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", username)
                .with("password", password))
            .exchange();
    }

    @Test
    void loginPageIsAvailable() {
        client.get().uri("/login")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void guestIsRedirectedToLogin() {
        client.get().uri("/home")
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void incorrectPasswordUsesGenericFailureRedirect() {
        login("alice", "wrong")
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/login?error");

        assertEquals(1, limiter.failureCount("alice"));
    }

    @Test
    void unknownUserSeesSameErrorUrl() {
        login("nobody", "wrong")
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/login?error");

        assertEquals(1, limiter.failureCount("nobody"));
    }

    @Test
    void threeBadPasswordsBlockLaterCorrectPassword() {
        for (int attempt = 0; attempt < 3; attempt++) {
            login("alice", "wrong")
                .expectStatus().is3xxRedirection()
                .expectHeader().valueEquals(
                    HttpHeaders.LOCATION, "/login?error");
        }

        assertEquals(3, limiter.failureCount("alice"));
        assertTrue(limiter.isBlocked("alice"));

        // Dù mật khẩu giờ đúng, gate chưa hết cooldown.
        login("alice", "welcome123")
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/login?error");
    }

    @Test
    void successfulLoginResetsEarlierFailures() {
        login("alice", "wrong").expectStatus().is3xxRedirection();
        login("alice", "wrong").expectStatus().is3xxRedirection();
        assertEquals(2, limiter.failureCount("alice"));

        login("alice", "welcome123")
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/home");

        assertEquals(0, limiter.failureCount("alice"));
        assertFalse(limiter.isBlocked("alice"));
    }

    @Test
    void oneLockedAccountDoesNotBlockAnother() {
        for (int attempt = 0; attempt < 3; attempt++) {
            login("alice", "wrong").expectStatus().is3xxRedirection();
        }
        assertTrue(limiter.isBlocked("alice"));

        login("bob", "hello456")
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/home");

        assertFalse(limiter.isBlocked("bob"));
    }

    @Test
    void formPostWithoutCsrfIsRejectedBeforePasswordCheck() {
        client.post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", "alice")
                .with("password", "wrong"))
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(0, limiter.failureCount("alice"));
    }
}
```

Có **8 phương thức `@Test`** trong test integration. Cộng với 3 test limiter ở mục 6 là **11 test**. `WebTestClient` được liên kết với ApplicationContext và `springSecurity()` để áp dụng chain thật; `csrf()` là mock support cấp token CSRF hợp lệ cho request thử nghiệm, không phải cách cấu hình production bỏ kiểm tra CSRF.

**Quan trọng về session:** Các test cố ý kiểm tra redirect khi login thành công, không giả định một `WebTestClient` tự lưu cookie từ response này sang request tiếp theo. Để test `GET /home` sau login, cần **lấy session cookie từ login response và gửi lại cookie tương ứng**, hoặc dùng test client được cấu hình giữ cookie. Đừng đánh đồng “POST login trả redirect” với “đã kiểm chứng request tiếp theo mang session”. Chủ đề hiện tại ưu tiên limiter; một bài về session cần test riêng cookie/session persistence.

### 7.2. Ma trận test và diễn giải

| Kiểm thử | Điều kiểm chứng | Kết quả |
| --- | --- | --- |
| GET `/login` | Form mặc định được cung cấp | **200** |
| GET `/home` chưa đăng nhập | Authentication entry point cho browser | **3xx** tới login |
| `alice` sai password 1 lần | Counter sau authentication failure | `302 /login?error`, count = 1 |
| `nobody` sai password | Không tiết lộ account tồn tại | Redirect chung như user có thật |
| `alice` sai 3 lần | Ngưỡng khóa | Count = 3, blocked |
| `alice` đúng password khi blocked | Gate nằm trước password verifier | Vẫn redirect lỗi chung |
| `alice` sai 2 lần rồi đúng | Reset sau success | Redirect `/home`, count = 0 |
| `alice` blocked, `bob` đăng nhập | Tách state theo account | Bob thành công |
| POST `/login` thiếu CSRF | CSRF không bị biến thành password failure | **403**, count = 0 |

Phản hồi browser form login **thường là redirect 302**, không nhất thiết 401/429. Nếu một API JSON muốn trả 429 cho throttling, cần endpoint/authentication mechanism và failure/entry point phù hợp; không đổi mọi `BadCredentialsException` thành 429 để tránh lộ trạng thái tài khoản.

## 8. Chạy thử và quan sát từ browser

### 8.1. Yêu cầu môi trường

- Java 17+ (Spring Boot 3.5.x), Maven tương thích.
- Các file đúng package `demo.login`, đúng cấu trúc Maven.
- Một cổng `8080` trống hoặc cấu hình lại `server.port`.

Lệnh:

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

Kỳ vọng bộ test gồm **11 tests, 0 failures, 0 errors** theo mã demo, và build thành công nếu JDK/dependencies tương thích. Đây là **kết quả dự kiến**, không phải tuyên bố test đã chạy trong mọi môi trường.

Mở browser tại `http://localhost:8080/login`, thử:

1. Đăng nhập `alice` với password `wrong`: hiển thị trạng thái lỗi chung.
2. Thử sai tổng cộng ba lần: tài khoản `alice` bị blocked tạm thời.
3. Nhập password đúng `welcome123` ngay sau đó: vẫn nhận lỗi chung trong thời gian cooldown.
4. Dùng `bob`/`hello456`: tài khoản khác đăng nhập được.
5. Sau khi cooldown hết, `alice` có thể đăng nhập bằng `welcome123`; thành công reset state.

**Lưu ý khi tự thử bằng browser:** Sau login thành công, session hiện tại vẫn lưu trạng thái đã đăng nhập. Muốn thử tình huống chưa đăng nhập từ đầu, hãy logout qua flow Spring Security (đúng CSRF) hoặc mở cửa sổ trình duyệt riêng/ẩn danh với cookie sạch. Không dùng tài khoản demo trong môi trường công khai.

### 8.2. Vì sao không khuyên `curl -X POST /login -d ...` đơn giản?

Spring Security WebFlux form login thường bật CSRF. Một POST thiếu CSRF token sẽ bị **403** trước khi gọi authentication manager, nên không phải phép thử phù hợp cho thuật toán giới hạn mật khẩu. Với browser, trang login mặc định có cơ chế tạo CSRF token cho form. Với integration tests, `WebTestClient.mutateWith(csrf())` xử lý phần này.

Nếu cần kiểm thử thủ công bằng `curl`, phải quản lý **cookie + CSRF token + form fields** theo cách thực tế, không tắt CSRF chỉ để tránh 403. Với API dùng credentials không tự gửi bởi browser, CSRF policy có thể khác nhưng phải đánh giá nguy cơ trước khi thay đổi.

## 9. Khi nào nên trả 429, khi nào giữ redirect chung?

Ở endpoint form login cho trình duyệt, trả `/login?error` cho mọi lỗi xác thực giúp tránh việc tiết lộ “username đúng nhưng đang bị khóa”. Throttling không nhất thiết phải hiện rõ cho client là counter bao nhiêu.

Ở một lớp **IP/edge rate limiting**, `429 Too Many Requests` với `Retry-After` có thể phù hợp: client gửi quá nhiều request độc lập với account. Nhưng đừng chỉ dựa vào 429 của gateway để chống brute force phân tán, và đừng mặc định gửi 429 khi đạt account threshold nếu hành vi này cho attacker biết tài khoản có tồn tại.

| Loại phản hồi | Tình huống nên cân nhắc | Nguy cơ |
| --- | --- | --- |
| Redirect chung `/login?error` | Form authentication sai hoặc đang cooldown | Ít leak trạng thái hơn, nhưng người dùng cần hướng dẫn khôi phục chung |
| `401 Unauthorized` với body chung | API login/password không dùng browser redirect | Không mô tả quá chi tiết tài khoản |
| `429 Too Many Requests` | Giới hạn burst chung theo IP/client với `Retry-After` | Nếu chỉ phát cho account tồn tại, có thể tạo enumeration |
| CAPTCHA / progressive delay | Nhiều request rủi ro, hỗ trợ người dùng hợp lệ | CAPTCHA không thay thế throttle; ảnh hưởng accessibility |
| Step-up MFA / passkey | Rủi ro cao, password đã bị lộ hoặc đăng nhập bất thường | Cần chống bypass các đường đăng nhập khác nhau |
| Recovery/self-service | Người dùng hợp lệ gặp cooldown | Phải chống abuse của chính cơ chế recovery |

Nội dung hiển thị có thể là “Không thể đăng nhập. Hãy kiểm tra thông tin hoặc thử lại sau; nếu cần, sử dụng khôi phục tài khoản.” Tránh câu phân biệt “Tên đăng nhập này không tồn tại” và “Tài khoản thật vừa bị khóa vì 3 lần sai”.

## 10. Thiết kế lớp bảo vệ IP và account kết hợp

**Chỉ giới hạn theo username trong demo là chưa đủ** đối với credential stuffing và password spraying. Bổ sung một **coarse request-rate gate** trước authentication:

```text
Internet
  |
  v
CDN / WAF / ingress        --> IP/source burst rate, abuse reputation
  |
  v
Spring WebFlux WebFilter   --> trusted remote address / device risk
  |
  v
Form AuthenticationFilter  --> account-wide failure window
  |
  v
Password verification      --> BCrypt/Argon2id, account state
  |
  v
Login result               --> MFA/step-up, metrics và audit đã redact
```

Ví dụ logic **minh họa kiến trúc, không phải Java có thể chạy độc lập**:

```text
if IP budget exhausted:
    respond 429/Retry-After (generic; do not parse username)
else if account-wide failed-login budget exhausted:
    fail authentication with generic login response
else:
    verify credentials
    if credentials wrong:
        atomically record account failure
        record coarse source risk signal
    if credentials right:
        clear/reduce account failures
        continue normal session/MFA flow
```

**Không đọc trực tiếp header `X-Forwarded-For` từ Internet** để làm key rate limit. Client có thể tự đặt header giả nếu ứng dụng không được che bởi trusted proxy. Trong hạ tầng tin cậy, configure forwarded headers ở đúng lớp proxy, khai báo danh sách proxy tin cậy, và dùng remote address đã được chuẩn hóa.

Các điểm cần xét cho IP key:

- IPv4/IPv6: normalize định dạng, cân nhắc IPv6 prefix và policy tránh khóa cả khối mạng quá lớn.
- NAT: nhiều người chung địa chỉ IP, nhất là mạng công ty và di động.
- Proxy chain: đừng tin giá trị client có thể tự điền.
- VPN/botnet: IP thay đổi, không được dùng IP làm biện pháp duy nhất.
- Privacy: giữ IP chỉ theo mức cần thiết, TTL rõ ràng, không log password; tuân chính sách bảo vệ dữ liệu.
- Rate limits cho `POST /login` nên khác limit chung toàn website; tránh khiến người dùng đọc nội dung bị ảnh hưởng bởi hành vi thử đăng nhập của một attacker.

## 11. Production: atomicity, TTL, đa instance và chống DoS

### 11.1. Vì sao `ConcurrentHashMap` chưa đủ?

Demo chỉ giữ state trong **một JVM**. Với ba replica của ứng dụng:

```text
Login requests
   |
   +--> Instance A: alice failures = 2
   +--> Instance B: alice failures = 2
   +--> Instance C: alice failures = 2

Nếu mỗi instance tự giới hạn tại 3, attacker đã thử 6 lần
mà chưa chắc instance nào chạm ngưỡng 3.
```

Rolling restart còn làm bộ đếm mất, và mỗi JVM tốn bộ nhớ theo số username. Đừng triển khai nguyên `ConcurrentHashMap` cho hệ thống có nhiều instance. Với sản phẩm thật, dùng **Redis** (hoặc storage chuyên dụng với TTL/atomic updates) để chia sẻ trạng thái giữa replicas và tránh tăng bộ nhớ vô hạn.

### 11.2. TTL và thiết kế key trong Redis

Một cấu trúc khái niệm:

```text
login:acct:<keyed-hash-of-canonical-username>
  failures: 2
  window_started_ms: ...
  blocked_until_ms: ...
  EXPIRE: đủ dài để bao phủ window/cooldown
```

Tránh lưu raw password, `Authorization`, JWT và dữ liệu không cần thiết. Nếu username là dữ liệu nhận dạng, có thể dùng HMAC với secret giữ tại server để tạo key ổn định, giảm việc lộ trực tiếp username trong Redis key; vẫn cần xử lý vòng đời secret, giới hạn cardinality và quyền truy cập Redis. Một hash thông thường không phải giải pháp bảo mật tự động cho username có entropy thấp.

**Mỗi cập nhật counter và TTL phải atomic**, ví dụ Redis Lua script hoặc giao dịch/primitive phù hợp. Mẫu đọc `GET` rồi ghi `SET` tách rời giữa replicas có thể gây lost update khi nhiều request cùng tới.

### 11.3. Concurrency: gate và password check là hai bước

Giả sử `MAX_FAILURES=3`, hiện tại `failures=2`. Có 100 request song song cùng thấy chưa blocked và cùng bắt đầu BCrypt trước khi request đầu ghi lỗi thứ ba. Bộ đếm có thể ghi chính xác sau đó nhưng **chi phí tính toán và số attempt đã lọt** vẫn vượt ngưỡng. Trong production, cần cơ chế atomic **reserve/check budget** trước password verifier:

```text
Lua/transaction (ý tưởng):
  read current window, blocked-until, in-flight
  atomically reject if blocked or risk budget exhausted
  reserve one attempt slot and set short TTL
return allow/deny

if allow:
  verify credentials
  atomically mark failed/successful and release reservation
  release reservation also on cancellation/timeout
```

Mẫu trên là **pseudocode**, không phải chương trình Redis Lua hoàn chỉnh. Phải thiết kế kỹ idempotency, TTL cho in-flight reservations, race giữa success và failure, clock source, outage fallback, và cancellation. Nếu thiếu reservation hoặc concurrency cap, chỉ tăng counter sau khi fail không ngăn được flood đã vào password verifier.

Không tạo một khóa account **vĩnh viễn** chỉ vì nhiều password sai; đây có thể là cách gây denial of service tới chủ tài khoản. Có thể kết hợp progressive backoff, MFA/step-up, xác minh rủi ro và recovery an toàn.

### 11.4. Chính sách lỗi Redis: fail-open hay fail-closed?

Khi Redis chậm/hỏng, hệ thống phải quyết định trade-off:

- **Fail-open** cho phép login tiếp tục: tăng availability nhưng giảm lớp chống brute force.
- **Fail-closed** từ chối login: bảo vệ tốt hơn nhưng một sự cố Redis có thể làm toàn bộ người dùng không đăng nhập được.
- **Degraded mode**: dùng mức hạn chế chặt hơn ở gateway, cache cục bộ có TTL ngắn, alarm, circuit breaker, hoặc chiến lược dựa trên rủi ro.

Không có một lựa chọn đúng cho mọi sản phẩm. Quyết định phải được mô tả trong runbook, kiểm thử tải/sự cố và tuân SLO cùng mức độ nhạy cảm tài khoản.

### 11.5. Giới hạn memory/cardinality

Ngay cả Redis có TTL cũng có thể bị bơm hàng triệu username ngẫu nhiên; IP-only và account-only là hai chiều bổ sung. Hãy kiểm soát **số lượng key được tạo**, TTL của key, tốc độ tạo key từ một nguồn, capacity Redis và retention. Một attacker có thể cố ý làm đầy cache nếu hệ thống tạo key cho mọi username không giới hạn.

## 12. User enumeration, độ trễ và UX

Phản hồi cùng câu chữ **chưa chắc đủ** để chống dò tài khoản. Nếu username có thật phải thực hiện BCrypt trong khi username không tồn tại được từ chối ngay, thời gian phản hồi có thể khác. Spring Security user-details authentication có các cơ chế che giấu username-not-found và giảm timing differences tùy provider, nhưng mọi custom authentication manager/DB integration phải được kiểm tra lại.

Các quy tắc:

1. Không trả `"Unknown username"` hoặc `"Account locked for 120 seconds"` chỉ cho tài khoản tồn tại.
2. Đảm bảo chính sách timing tương đối nhất quán khi unknown account và wrong password, trong khả năng thực tế; tránh sleep blocking trên Netty event loop để tạo delay giả.
3. Không log raw username/password vào high-cardinality metrics. Có thể dùng bucket/labels tổng hợp, request correlation ID và audit store được bảo vệ.
4. Khi người dùng bị chặn tạm, cung cấp **đường khôi phục an toàn** nhưng không mở thêm endpoint dễ bị abuse.
5. Login error page phải accessible không cần authentication; với `GET /login?error`, Spring Security match path `/login` (query string không phải một path matcher riêng).
6. Rate-limit hoạt động ngay cả với username không tồn tại để tránh attacker dùng `nobody` làm thử nghiệm vô hạn, nhưng cần bound number of distinct keys.

### Tình huống user bị khóa do người khác cố tình gây ra

Một attacker có thể nhập sai password cho email công khai của nhân viên để khiến nhân viên không đăng nhập được. Phòng thủ có thể bao gồm per-IP limit, nâng dần độ trễ thay vì khóa cứng, MFA, cơ chế khôi phục có kiểm soát, phát hiện false positive, và thông báo cho người dùng theo kênh tin cậy mà không tiết lộ thêm trạng thái qua giao diện đăng nhập.

Không coi CAPTCHA là giải pháp duy nhất: bot có thể giải CAPTCHA qua dịch vụ thuê ngoài, ảnh hưởng accessibility và trải nghiệm người dùng. CAPTCHA là **defense in depth**, dùng sau tín hiệu rủi ro thích hợp.

## 13. Testing và QA cho môi trường thật

Test demo có tính giáo dục, nhưng production cần nhiều mức kiểm thử:

| Nhóm kiểm thử | Điều cần kiểm tra | Gợi ý |
| --- | --- | --- |
| Unit | Boundary `MAX_FAILURES`, `WINDOW`, `COOLDOWN`, reset | Fake `Clock`, không sleep |
| Integration | POST form+CSRF đúng, authentication manager được gọi, redirect chung | `WebTestClient` gửi credentials thật |
| Negative | Unknown user, password sai, blocked account, expired cooldown | Không lộ username qua response |
| CSRF | POST thiếu/sai token không thực hiện password verification | 403, không tăng wrong-password count |
| Concurrency | N request song song cùng key | Không vượt số reservation/budget |
| Distributed | N replica dùng chung counters | Redis/script atomic, không lost update |
| Proxy/IP | Header giả, nhiều proxy hop, NAT/IPv6 | Không tin `X-Forwarded-For` của client |
| Availability | Redis timeout, DB unavailable | Chính sách fail-open/closed có test |
| Security | Password hash, TLS, CSRF, session fixation, cookie | Không log secret; session behavior đúng |
| Load | Flood login làm cạn CPU vì BCrypt | Gate trước verifier, backpressure và giới hạn in-flight |
| Usability | Account lockout nhầm, recovery, accessibility | Support flow và thông báo trung tính |

Trong Spring Security, `@WithMockUser` hữu ích để kiểm tra **authorization**, nhưng nó **không mô phỏng một lần password sai qua form login**, nên không nên dùng làm test chính cho limiter đặt trong `ReactiveAuthenticationManager`.

Các test khác hữu ích:

- Đảm bảo **success sau 1–2 lần sai** reset counter, nhưng không xóa key của người dùng khác.
- Test đúng thời điểm boundary của WINDOW/COOLDOWN, ví dụ `now == blockedUntil`.
- Test sau restart/deploy nếu policy yêu cầu counters sống qua nhiều instance.
- Test cùng một account từ hai IP khác nhau và password spray nhiều account từ một IP.
- Test rate limit behavior khi client hủy request sau khi đã reserve slot.
- Test session/cookie thực: form login thành công redirect xong, request tiếp theo với session cookie truy cập được `/home`; chưa login thì redirect.
- Test password reset/account recovery không làm bypass chính sách hoặc enumeration.
- Test logs, traces và metrics không chứa raw password, form payload hoặc raw authentication object.

## 14. Các lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đếm theo IP duy nhất | Botnet dùng IP mới để thử cùng account | Bổ sung account-wide budget |
| Đếm theo username duy nhất | Password spraying trên nhiều account không bị phát hiện | Bổ sung source-wide burst limits |
| Đếm trong từng replica bằng map | Load balancer phân phối request làm bypass | Dùng state chia sẻ có TTL và atomic operations |
| Tăng counter ở failure handler nhưng không gate trước manager | CPU BCrypt vẫn bị flood | Thêm pre-auth decision trước password verification |
| Dùng `get` rồi `put` counter | Lost update khi race | `compute`, Redis script/atomic primitive |
| Chỉ đếm “user thật” | User enumeration và unlimited unknown guesses | Đếm bad credentials/unknown theo chính sách chung |
| Đếm mọi `AuthenticationException` là bad password | Redis/DB outage làm khóa người dùng | Phân biệt bad credentials với lỗi hệ thống |
| Trả “locked” chỉ khi username tồn tại | Tiết lộ tài khoản | Dùng thông báo/thời gian tương đối nhất quán |
| Hard lock vĩnh viễn ở lần sai thứ ba | Attacker dễ gây DoS vào tài khoản thật | Cooldown có giới hạn, progressive controls, recovery |
| Không reset khi success | Người dùng hợp lệ dễ bị khóa liên tục | Quy định reset/reduction theo chính sách |
| Reset mọi key khi một user thành công | Có thể xóa dấu hiệu tấn công IP/system-wide | Chỉ reset đúng phạm vi account |
| Tự `subscribe()` hoặc `block()` trong WebFilter | Rò context, blocking event loop, khó kiểm soát cancellation | Compose `Mono`/reactive operators |
| Tắt CSRF chỉ để POST login test chạy | Browser form có thể bị CSRF | Test dùng `csrf()`, giữ chính sách thích hợp |
| Dựa vào `@WithMockUser` để kiểm chứng password | Bỏ qua đường xác thực thật | POST form và kiểm tra manager/counters |
| Đọc IP từ header tùy ý của client | Attacker giả IP để né giới hạn | Chỉ tin proxy đã cấu hình |
| Không giới hạn key cardinality | Memory/Redis exhaustion | TTL, per-source limits, HMAC/normalization |
| 429 cho account có thật, 401 cho account không tồn tại | User enumeration | Response chung cho account status, 429 cho global/IP budget khi thích hợp |
| Password hardcoded trong source production | Lộ secret | Secret management/DB hash, rotation |
| Log form payload, `Authentication.getCredentials()` | Lộ password | Redact logs, audit ở mức cần thiết |
| Không có kế hoạch lỗi Redis | Fail-open không kiểm soát hoặc login outage | Runbook, alerts, fallback đã kiểm thử |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Nếu chính sách khóa sau ba lần nhập sai trên một username, một botnet 20 IP có thể bị chặn bằng IP-only limiter không?  
**Đáp án:** Không đáng tin. Botnet có thể phân phối attempts. Cần account-wide state và các tín hiệu nguồn/rủi ro bổ sung.

**Câu 2.** Vì sao không đặt duy nhất `recordFailure` trong `ServerAuthenticationFailureHandler`?  
**Đáp án:** Vì các request có thể vẫn đi qua kiểm tra password/BCrypt trước khi handler được gọi; không có gate sớm thì không giảm chi phí xác thực và số request in-flight.

**Câu 3.** Nếu form login POST thiếu CSRF token và trả 403, có nên cộng một bad-password attempt không?  
**Đáp án:** Không. Xác thực mật khẩu chưa chắc được thực hiện; lỗi CSRF thuộc lớp khác. Cần ghi signal rủi ro riêng nếu muốn.

**Câu 4.** Người dùng đăng nhập đúng sau hai lần sai. Bước nào reset state?  
**Đáp án:** `doOnNext(result -> limiter.recordSuccess(username))` trong decorator sau khi manager trả authentication thành công. Không reset trước khi kiểm tra mật khẩu.

**Câu 5.** Vì sao demo `ConcurrentHashMap.compute` vẫn chưa đủ cho nhiều request concurrent?  
**Đáp án:** Bản thân cập nhật per-key là atomic, nhưng **`isBlocked` và `delegate.authenticate` xảy ra trước khi failure được ghi**. Nhiều request có thể đi qua gate cùng lúc; production cần reservation/in-flight cap atomic.

**Câu 6.** Vì sao một Redis `INCR` có TTL chưa chắc đủ?  
**Đáp án:** Cần xử lý cùng lúc window, cooldown, giới hạn in-flight, điều kiện reset và race, có thể bằng script/transaction. Phải bảo đảm TTL/cardinality và failover.

**Câu 7.** Trả rõ “username alice đang bị khóa 2 phút” có rủi ro gì?  
**Đáp án:** Có thể tiết lộ tài khoản tồn tại và trạng thái đăng nhập, giúp account enumeration và denial of service. Dùng thông báo chung và kênh hỗ trợ/khôi phục an toàn.

**Câu 8.** Tại sao phải kết hợp `@SpringBootTest`, `WebTestClient` và `csrf()` trong bài thực hành?  
**Đáp án:** Vì cần chạy form authentication/filter chain thật với POST hợp lệ. `csrf()` tránh lỗi 403 ở lớp CSRF khiến test không kiểm tra được password limiter.

**Câu 9.** Nếu provider xác thực gặp timeout, đó có phải password sai để tăng counter?  
**Đáp án:** Không. Phải phân loại sự cố hạ tầng riêng, có alert và lỗi phù hợp; không tự tạo account lockout từ outage.

**Câu 10.** Khóa tài khoản càng lâu càng tốt phải không?  
**Đáp án:** Không. Khóa dài có thể bị attacker lợi dụng gây DoS. Cần cân bằng bảo vệ và khả dụng: window, cooldown, progressive controls, MFA, recovery và chính sách rủi ro.

**Câu 11.** Vì sao Basic authentication và form login không thể mặc nhiên dùng cùng một failure handler/flow?  
**Đáp án:** Form login thường dùng session, CSRF và redirect browser; HTTP Basic thường dùng challenge 401. Hạn mức có thể chia sẻ ở identity service nhưng phản hồi HTTP và cách xác thực khác.

**Câu 12.** Cần test điều gì khi có ba instance ứng dụng?  
**Đáp án:** Counters dùng chung, cập nhật atomic, hoạt động khi node restart, không vượt budget do concurrent requests, và hành vi khi storage trung tâm timeout.

## 16. Checklist triển khai

- [ ] Chính sách account-wide/IP-wide/account-IP được thống nhất với risk team và SLO.
- [ ] Có ngưỡng, observation window, cooldown, reset và giới hạn concurrent attempts rõ ràng.
- [ ] Gate chạy **trước** password verification; kết quả failed/success được ghi sau.
- [ ] Phân biệt bad credentials, locked, service failure, CSRF, authorization.
- [ ] Response và timing không tiết lộ account tồn tại/không tồn tại theo cách dễ khai thác.
- [ ] Có CSRF cho browser form và cookie/session policy phù hợp.
- [ ] Mật khẩu được lưu dạng hash mạnh, không có credentials thật trong code/log/trace.
- [ ] Trusted proxy/IP handling và IPv6/NAT đã được kiểm thử.
- [ ] Multi-instance dùng store chia sẻ với TTL, atomic updates, bounded cardinality.
- [ ] Có phương án xử lý failure của Redis/gateway và alert.
- [ ] Có đo lường abuse nhưng không log raw secrets.
- [ ] Có MFA/step-up, quản lý tài khoản bị khóa nhầm và recovery an toàn.
- [ ] Test unit boundaries, integration POST login, concurrency, distributed, security và usability.
- [ ] Không mang nguyên demo in-memory single-JVM lên production.

## 17. Tổng kết và tài liệu tham khảo

**Ghi nhớ:** Giới hạn đăng nhập hiệu quả phải ngăn số lần **kiểm tra password thực sự** chứ không chỉ đếm lỗi. Với Spring Security WebFlux form login, có thể dùng `ReactiveAuthenticationManager` decorator để kiểm tra account limiter trước delegate, cập nhật sau authentication success/bad credentials, và giữ response chung bằng `ServerAuthenticationFailureHandler`. Nhưng production cần kết hợp giới hạn nguồn gửi, state phân tán, atomic reservation, bảo mật CSRF/session, MFA, anti-enumeration và vận hành/khôi phục.

**Nguồn chính thức:**

- OWASP Authentication Cheat Sheet – Login Throttling, Account Lockout, Authentication Responses: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Credential Stuffing Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html
- OWASP Forgot Password Cheat Sheet – chống user enumeration và rate limiting: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- Spring Security 6.5 – WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 – `ServerHttpSecurity.FormLoginSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html
- Spring Security 6.5 – `AuthenticationWebFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security – WebFlux CSRF protection: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security – Testing CSRF with WebTestClient: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html
- Spring Security – Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Boot 3.5.16 release announcement (end of OSS support): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
