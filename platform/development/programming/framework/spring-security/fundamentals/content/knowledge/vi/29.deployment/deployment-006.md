# Giới hạn thử đăng nhập và phối hợp chống dò tài khoản với hạ tầng

> **Phạm vi:** Bảo vệ đăng nhập Spring Security trên Java 17+, Spring Boot 3.x/Spring Security 6.x trước brute force, password spraying, credential stuffing và tự động hóa độc hại. Nội dung kết nối **ứng dụng, Identity Provider (IdP), WAF/CDN, reverse proxy, API gateway, Redis và observability**. Ví dụ minh họa có thể chạy trên một JVM; phần triển khai phân tán nêu rõ yêu cầu phải có trước production.

## 1. Nhận diện bài toán

Password được lưu bằng BCrypt/Argon2 không tự ngăn kẻ tấn công **gửi hàng nghìn lần thử password lên endpoint đăng nhập**. Cần kiểm soát cả số lần thử, tốc độ và rủi ro; đồng thời không làm người dùng thật bị khóa vì một bot chủ động gửi password sai vào account của họ.

| Hình thức | Hành vi | Dấu hiệu | Phòng vệ |
| --- | --- | --- | --- |
| Brute force | Nhiều password cho **một account**, có thể đổi IP. | Failure count cao theo account. | Account counter, progressive delay/step-up, MFA. |
| Password spraying | Một vài password phổ biến trên **nhiều account**. | Nhiều username cùng IP/ASN, ít lần sai mỗi account. | IP/network/risk detection, IdP/WAF controls. |
| Credential stuffing | Thử các cặp user/password bị lộ từ nguồn khác. | Nhiều account, nhiều IP, có thể có login thành công. | MFA/passkeys, bot mitigation, phân tích login success/failure và breached credentials. |
| Username enumeration | Đoán tài khoản tồn tại qua response/timing. | Lỗi khác nhau theo account state. | Generic error/status, timing mitigation, throttling cho cả unknown user. |
| Authentication resource exhaustion | Flood login để ép CPU hash password/DB. | CPU cao, queue/latency tăng. | Early WAF/gateway request limits, pre-auth checks, backpressure. |

**Authentication** xác minh password/token; **throttling** quyết định có cho request đi tới bước xác thực hay không. Khi quota bị chặn, **password đúng cũng có thể tạm bị từ chối**: điều này cần được phản ánh trong UX và threat model. Không đặt quy tắc “cứ sai 5 lần khóa 24 giờ” như một tiêu chuẩn chung.

## 2. Nhiều lớp bảo vệ, không một rule duy nhất

```text
Browser / Mobile / API client
       |
       v
CDN / WAF / Bot & DDoS protection
  - request rate, IP reputation, ASN, burst, challenge
       |
       v
Trusted reverse proxy / API gateway
  - TLS, canonical client IP, route-specific quotas
       |
       v
Spring Security / authentication endpoint
  - CSRF (khi cookie login), pre-auth rate check
  - UserDetailsService / AuthenticationProvider / password hash
  - failure/success handling; account-aware policy
       |
       +--> Distributed counters (Redis atomic + TTL)
       |
       +--> IdP / MFA / passkeys / breached-password checks
       |
       v
Structured logs + metrics + SIEM / alert + incident response
```

**WAF/gateway** thấy lưu lượng thô trước khi ứng dụng tốn CPU. **Ứng dụng** biết username chuẩn hóa, user/tenant, thất bại/đăng nhập thành công và policy nghiệp vụ. **IdP** có trách nhiệm bảo vệ password/MFA nếu login thực diễn ra ngoài ứng dụng OIDC. **Redis/kho đếm dùng chung** giữ state thống nhất giữa nhiều pod. **Giám sát** phát hiện tấn công phân tán và false positives. Phòng vệ theo lớp giảm nguy cơ bỏ lọt và tránh biến một thành phần lỗi thành lỗ hổng toàn hệ thống.

### 2.1. Trách nhiệm theo thành phần

| Tầng | Điều phù hợp để làm | Điều không thể thay thế |
| --- | --- | --- |
| CDN/WAF | Chặn bot/flood, rate/bot challenges, IP reputation và traffic anomalies. | Quyền account thật, password đúng/sai, membership tenant. |
| Proxy/gateway | Route limits, TLS, request bounds, canonical IP, deny bypass origin. | Xác định username tồn tại hay không từ database. |
| Spring Security | Password provider, CSRF/session, authentication handlers, account-aware limiter. | Anti-DDoS ở edge hoặc distributed counters nếu chỉ có RAM. |
| Redis | Atomic counters, TTL, chia sẻ quota nhiều instance. | Chính sách danh tính, MFA và bot reputation. |
| IdP | Password guessing defense, MFA/SSO, account risk, token issuance. | App-specific owner/tenant authorization. |
| Monitoring/on-call | Điều tra distributed attack, điều chỉnh policy, incident response. | Bảo vệ synchronous login nếu chỉ gửi alert sau sự kiện. |

**Đặc biệt với OIDC/SAML:** khi browser được redirect tới IdP để nhập password, BFF/Spring Security OAuth2 login **không thấy password người dùng**. Giới hạn `POST /login` của ứng dụng không thay thế được rate limits/MFA/lockout tại IdP; app vẫn phải bảo vệ callback, session, logout và các endpoint riêng của mình.

## 3. Chọn khóa rate limit

| Khóa | Bắt được | Trade-off |
| --- | --- | --- |
| **Account/normalized login ID** | Tấn công cùng một tài khoản qua nhiều IP. | Có thể bị dùng để khóa nạn nhân; phải áp dụng cả account chưa tồn tại. |
| **IP** | Bot tập trung và một phần password spraying. | NAT công ty/di động, VPN, đổi IP; false positives. |
| **IP prefix/ASN/risk** | Cụm botnet hoặc mạng có hành vi bất thường. | Mạng chung và VPN hợp lệ cũng có thể trùng. |
| **Account + IP** | Tấn công dai dẳng từ một nguồn tới một account. | IP rotation tạo vô số tổ hợp khác nhau. |
| **Session/device signal** | Hành vi lặp qua nhiều IP. | Có thể bị xóa/giả; cần policy riêng tư và TTL. |
| **Route/global burst** | Flood gây cạn CPU và connection. | Giới hạn quá thấp gây outage traffic hợp pháp. |
| **Verified client/tenant** | Abuse bởi một partner/tenant xác định. | Không tin client ID/tenant header tự khai. |

Không chỉ dùng IP hoặc account. Một thiết kế thường phối hợp **rate request ở edge**, **failure count theo account**, **network-level abuse detection**, **MFA/step-up** và **monitoring**. Tài khoản quan trọng có thể cần biện pháp mạnh hơn trong khi user dùng chung NAT cần ngưỡng IP đủ rộng.

### 3.1. Cửa sổ, ngưỡng và hành động

Mỗi policy phải ghi rõ:

1. Threshold (số request hoặc thất bại), window (ví dụ phút), burst và cooldown.
2. Fixed/sliding window, token bucket hay leaky bucket; giới hạn theo IP/account hay kết hợp.
3. Action: monitor, progressive delay, CAPTCHA/bot challenge, step-up MFA, HTTP 429 hoặc temporary lock.
4. State store: một node hay Redis; TTL, cleanup, maximum keys và data privacy.
5. Khi nào tăng counter: trước password verify cho request admission hay sau authentication failure?
6. Khi nào reset: success chỉ reset phần nào, window expiry, admin override có audit?
7. Failover khi Redis/edge lỗi, khả năng mở rộng, cảnh báo và chủ sở hữu rule.
8. UX: generic response, retry guidance, recovery path và false positives.

**Không có ngưỡng mặc định cho mọi sản phẩm.** Các giá trị `5 failures/account` và `12 failures/IP` ở ví dụ sau **chỉ để minh họa kiểm thử**, không phải benchmark bảo mật hay khuyến nghị đưa thẳng vào production.

### 3.2. Request quota và failure counter khác nhau

- **Pre-auth admission quota:** được kiểm/đặt chỗ **trước khi** chạy hash password, giúp giảm CPU DoS. Ở production cần atomic reservation để nhiều request song song không đồng thời vượt ngưỡng.
- **Failure counter:** tăng **sau khi** provider xác định login thất bại, hữu ích cho phát hiện brute force theo account. Nếu chỉ kiểm preflight rồi ghi failure sau, các request song song có thể cùng đi qua quota trước khi counter tăng.
- **Successful login:** dùng để phân tích nguy cơ account compromise và cân nhắc reset counter account; **không reset toàn bộ IP/global counters** chỉ vì một account đăng nhập đúng.

Account lockout có thể bị lợi dụng làm DoS đối với người dùng. Khi rủi ro cao, cân nhắc **challenges/MFA/progressive delays**, cooldown ngắn và recovery thay vì hard lock dài hạn.

## 4. Thông báo lỗi, enumeration và 401/403/429

| Kết quả | HTTP/UX tùy mô hình | Cần phân biệt |
| --- | --- | --- |
| Username/password sai, còn quota | Demo trả **401** với thông báo chung. | Không nói “user không tồn tại” hay “sai password” khác nhau. |
| Đạt giới hạn thử đăng nhập | Demo trả **429 Too Many Requests** và `Retry-After`. | Không lộ account state qua message/khác biệt status phụ thuộc user tồn tại. |
| POST browser login thiếu CSRF | **403 Forbidden**. | Lỗi CSRF khác throttle; không tắt CSRF để sửa. |
| Form login chưa đăng nhập vào endpoint yêu cầu auth | Thường **302** redirect tới login. | Với HTTP Basic/Bearer API, thường **401**. |
| Login đúng, đủ quota | Demo **200**; session được lập. | Throttle và password validation là hai điều kiện khác nhau. |

OWASP khuyến nghị phản hồi tổng quát cho user không tồn tại, password sai, tài khoản bị khóa hoặc disabled, đồng thời tránh khác biệt timing đáng kể. Một `429` chỉ theo account có thể làm lộ thông tin nếu account không tồn tại không bị đếm hoặc có hành vi khác. Phải áp dụng cùng một chính sách đối với account key chưa tồn tại và hạn chế chênh lệch status/message do account existence.

**Không đặt username/password, raw token, cookie hay OTP trong logs, metrics hoặc body lỗi.** Với forgot-password, trả thông điệp kiểu “Nếu tài khoản tồn tại, hướng dẫn đã được gửi”; registration, resend OTP/email, magic link, recovery và refresh token cũng có nguy cơ abuse, cần giới hạn riêng.

## 5. Ví dụ Java 17+ chạy được trên một Spring Boot instance

Ví dụ dùng form login/session và CSRF mặc định để trình bày rõ nơi kết nối limiter với Spring Security. **Đây không phải giải pháp multi-pod production**: bộ đếm in-memory không chia sẻ qua các instance và còn race giữa precheck với callback failure. Phần sau giải thích cách thay bằng Redis/edge.

**Chính sách demo:** trong cửa sổ 5 phút, 5 failures cùng account (kể cả nhiều IP) hoặc 12 failures cùng IP (kể cả nhiều username) khiến **lần thử tiếp theo** nhận 429. Login đúng reset counter account nhưng **không reset counter IP**. Username unknown cũng được đếm. Bộ đếm dùng `System.currentTimeMillis` ở runtime và đồng hồ tùy biến ở test; khi expiry được truy cập lại nó sẽ reset.

### 5.1. Project Gradle

`settings.gradle`:

```groovy
rootProject.name = 'login-throttle-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.3.5 được ghim để bài học có dependencies tái lập; **không phải bản Spring Boot mới nhất hoặc phiên bản production nên chọn vào năm 2026**. Khi xây hệ thống thật, chọn nhánh còn được vá bảo mật. Yêu cầu JDK 17+ và Gradle 8.x tương thích.

### 5.2. Mã ứng dụng hoàn chỉnh

Tạo tệp `src/main/java/demo/loginthrottle/LoginThrottleApplication.java`; một public class và các class/record package-private trong cùng tệp Java là hợp lệ.

```java
package demo.loginthrottle;

import java.io.IOException;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.function.LongSupplier;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class LoginThrottleApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginThrottleApplication.class, args);
    }
}

class LoginAttemptLimiter {
    private static final long WINDOW_MS = 5 * 60_000L;
    private static final int MAX_PER_ACCOUNT = 5;
    private static final int MAX_PER_IP = 12;

    private record Bucket(long start, int failures) {}

    private final LongSupplier nowMillis;
    private final Map<String, Bucket> accounts = new HashMap<>();
    private final Map<String, Bucket> ips = new HashMap<>();

    LoginAttemptLimiter(LongSupplier nowMillis) {
        this.nowMillis = nowMillis;
    }

    private String accountKey(String username) {
        // Demo giả định username không phân biệt chữ hoa/thường.
        // Production dùng canonical identity theo IdP.
        return username == null
            ? "<missing>"
            : username.strip().toLowerCase(Locale.ROOT);
    }

    private void increment(Map<String, Bucket> table,
                           String key, long now) {
        Bucket old = table.get(key);
        if (old == null || now < old.start()
                || now - old.start() >= WINDOW_MS) {
            table.put(key, new Bucket(now, 1));
        } else {
            table.put(key, new Bucket(old.start(), old.failures() + 1));
        }
    }

    private long waitFor(Map<String, Bucket> table,
                         String key, int threshold, long now) {
        Bucket old = table.get(key);
        if (old == null) {
            return 0;
        }

        long remaining = WINDOW_MS - (now - old.start());
        if (remaining <= 0 || remaining > WINDOW_MS) {
            table.remove(key);
            return 0;
        }
        if (old.failures() < threshold) {
            return 0;
        }
        return Math.max(1, (remaining + 999) / 1_000);
    }

    synchronized long retryAfterSeconds(String username, String ip) {
        long now = nowMillis.getAsLong();
        return Math.max(
            waitFor(accounts, accountKey(username),
                    MAX_PER_ACCOUNT, now),
            waitFor(ips, ip, MAX_PER_IP, now)
        );
    }

    synchronized void failed(String username, String ip) {
        long now = nowMillis.getAsLong();
        increment(accounts, accountKey(username), now);
        increment(ips, ip, now);
    }

    synchronized void succeeded(String username) {
        // Không xóa dấu vết nhiều lần fail từ một IP.
        accounts.remove(accountKey(username));
    }

    synchronized void clearForTests() {
        accounts.clear();
        ips.clear();
    }
}

class LoginThrottleFilter extends OncePerRequestFilter {
    private final LoginAttemptLimiter limiter;

    LoginThrottleFilter(LoginAttemptLimiter limiter) {
        this.limiter = limiter;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest req) {
        return !("POST".equals(req.getMethod())
                && "/login".equals(req.getServletPath()));
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest req,
            HttpServletResponse res,
            FilterChain chain) throws ServletException, IOException {
        long seconds = limiter.retryAfterSeconds(
            req.getParameter("username"), req.getRemoteAddr()
        );
        if (seconds > 0) {
            res.setStatus(429);
            res.setHeader("Retry-After", Long.toString(seconds));
            res.setHeader("Cache-Control", "no-store");
            res.setContentType("text/plain;charset=UTF-8");
            res.getWriter().write("Please try again later");
            return;
        }
        chain.doFilter(req, res);
    }
}

@RestController
class DemoEndpoints {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }
}

@Configuration
class SecurityConfig {
    @Bean
    LoginAttemptLimiter loginAttemptLimiter() {
        return new LoginAttemptLimiter(System::currentTimeMillis);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER").build(),
            User.withUsername("bob")
                .password(encoder.encode("bob123"))
                .roles("USER").build()
        );
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http,
                              LoginAttemptLimiter limiter)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .permitAll()
                .successHandler((req, res, authentication) -> {
                    limiter.succeeded(authentication.getName());
                    res.setStatus(200);
                    res.setHeader("Cache-Control", "no-store");
                    res.setContentType("text/plain;charset=UTF-8");
                    res.getWriter().write("Signed in");
                })
                .failureHandler((req, res, ex) -> {
                    limiter.failed(
                        req.getParameter("username"),
                        req.getRemoteAddr()
                    );
                    res.setStatus(401);
                    res.setHeader("Cache-Control", "no-store");
                    res.setContentType("text/plain;charset=UTF-8");
                    res.getWriter().write("Invalid credentials");
                })
            )
            .addFilterBefore(
                new LoginThrottleFilter(limiter),
                UsernamePasswordAuthenticationFilter.class
            );

        // Giữ CSRF mặc định cho form login/session.
        return http.build();
    }
}
```

### 5.3. Tại sao các điểm móc này đúng?

1. `LoginThrottleFilter` **không khai báo `@Component` hoặc `@Bean` riêng**, tránh Spring Boot tự đăng ký thêm nó ở ngoài security chain. Chỉ khởi tạo bằng `new` rồi `addFilterBefore` vào chain.
2. `shouldNotFilter` chỉ cho filter xử lý `POST /login`. Request `GET /public` hoặc `GET /me` không bị xem như thử password.
3. Trước khi password hash, limiter kiểm account/IP còn quota không. Sau khi provider xác minh credentials sai, `failureHandler` mới tăng counters; sau login đúng, `successHandler` chỉ reset account.
4. `synchronized` giúp dữ liệu map nhất quán **trong một JVM**, nhưng không đồng bộ giữa pod và không giải quyết precheck/recordFailure race khi nhiều request song song.
5. Bản demo giữ một key trong map cho tới khi key đó được truy cập lại: thiếu chủ động TTL eviction/cardinality guard, nên **không triển khai thẳng ở production**.
6. `getRemoteAddr()` không tin trực tiếp `X-Forwarded-For` từ client. Nếu chạy sau proxy, nó có thể là IP proxy; phải cấu hình trusted proxy để dùng canonical client IP đúng.
7. Form login demo chủ động trả **401** credential sai và **200** khi thành công, còn trình duyệt chưa login đi vào endpoint bảo vệ có thể redirect **302**. Nếu CSRF thiếu, login POST trả **403** trước password check.

### 5.4. Test với MockMvc và spring-security-test

Tạo `src/test/java/demo/loginthrottle/LoginThrottleIntegrationTest.java`:

```java
package demo.loginthrottle;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginThrottleIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired LoginAttemptLimiter limiter;

    @BeforeEach
    void reset() {
        limiter.clearForTests();
    }

    private MockHttpServletRequestBuilder attempt(
            String name, String password, String ip) {
        return post("/login")
            .param("username", name)
            .param("password", password)
            .with(csrf())
            .with(req -> {
                req.setRemoteAddr(ip);
                return req;
            });
    }

    @Test
    void publicRequestIsAllowed() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void validCredentialsAreAccepted() throws Exception {
        mvc.perform(attempt("alice", "alice123", "192.0.2.8"))
            .andExpect(status().isOk())
            .andExpect(content().string("Signed in"));
    }

    @Test
    void badPasswordReturnsGeneric401() throws Exception {
        mvc.perform(attempt("alice", "wrong", "192.0.2.8"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string("Invalid credentials"));
    }

    @Test
    void unknownUsernameGetsSameGenericMessage()
            throws Exception {
        mvc.perform(attempt("not-existing", "wrong", "192.0.2.8"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string("Invalid credentials"));
    }

    @Test
    void accountIsLimitedEvenAfterClientChangesIp()
            throws Exception {
        for (int i = 0; i < 5; i++) {
            mvc.perform(attempt("alice", "wrong", "192.0.2.8"))
                .andExpect(status().isUnauthorized());
        }
        mvc.perform(attempt("alice", "alice123", "198.51.100.9"))
            .andExpect(status().isTooManyRequests())
            .andExpect(header().exists("Retry-After"));
    }

    @Test
    void distributedIpsStillHitSameAccountCounter()
            throws Exception {
        for (int i = 0; i < 5; i++) {
            mvc.perform(attempt(
                    "alice", "wrong", "198.51.100." + (i + 1)))
                .andExpect(status().isUnauthorized());
        }
        mvc.perform(attempt("alice", "alice123", "203.0.113.9"))
            .andExpect(status().isTooManyRequests());
    }

    @Test
    void sameIpAcrossManyAccountsIsLimited()
            throws Exception {
        for (int i = 0; i < 12; i++) {
            mvc.perform(attempt(
                    "unknown-" + i, "wrong", "203.0.113.8"))
                .andExpect(status().isUnauthorized());
        }
        mvc.perform(attempt("bob", "bob123", "203.0.113.8"))
            .andExpect(status().isTooManyRequests());
    }

    @Test
    void otherUserFromOtherIpCanStillLogin()
            throws Exception {
        for (int i = 0; i < 5; i++) {
            mvc.perform(attempt("alice", "wrong", "192.0.2.8"))
                .andExpect(status().isUnauthorized());
        }
        mvc.perform(attempt("bob", "bob123", "198.51.100.9"))
            .andExpect(status().isOk());
    }

    @Test
    void successfulLoginResetsAccountFailures()
            throws Exception {
        mvc.perform(attempt("alice", "wrong", "192.0.2.8"))
            .andExpect(status().isUnauthorized());
        mvc.perform(attempt("alice", "alice123", "198.51.100.8"))
            .andExpect(status().isOk());
        mvc.perform(attempt("alice", "wrong", "198.51.100.9"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "alice123"))
            .andExpect(status().isForbidden());
    }
}
```

**Giải thích:** không dùng `@WithMockUser` để kiểm password vì annotation đó tạo authentication giả. Các request test đi qua form filter/provider thật và CSRF. Test account lock kiểm từ **IP khác**, test IP lock kiểm **username khác**, test unknown user nhận cùng message, và test CSRF dùng riêng. Địa chỉ IP dùng dải tài liệu (RFC 5737).

### 5.5. Test TTL không dùng sleep

Tạo `src/test/java/demo/loginthrottle/LoginAttemptLimiterTest.java`:

```java
package demo.loginthrottle;

import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class LoginAttemptLimiterTest {
    @Test
    void fiveMinuteWindowExpires() {
        AtomicLong millis = new AtomicLong(1_000L);
        LoginAttemptLimiter limiter =
            new LoginAttemptLimiter(millis::get);

        for (int i = 0; i < 5; i++) {
            limiter.failed("alice", "192.0.2.8");
        }
        assertThat(limiter.retryAfterSeconds(
            "alice", "198.51.100.9")).isPositive();

        millis.addAndGet(5 * 60_000L);
        assertThat(limiter.retryAfterSeconds(
            "alice", "198.51.100.9")).isZero();
    }
}
```

Test sử dụng đồng hồ điều khiển được, không đợi 5 phút thật; kết quả không phụ thuộc lịch CI. Trong production cần xử lý time drift và Redis TTL đúng semantics.

### 5.6. Chạy và quan sát

Nếu có Gradle Wrapper:

```bash
./gradlew test
./gradlew bootRun
```

Windows: `gradlew.bat test` và `gradlew.bat bootRun`. Nếu chưa có wrapper, dùng `gradle test` và `gradle bootRun` với bản Gradle 8.x tương thích.

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
```

`GET /public` trả 200 và body `public`; `GET /me` khi chưa login thường redirect tới form login. Không thử `curl -d username=...` thiếu CSRF rồi kết luận password sai: Spring Security sẽ trả **403 CSRF** trước khi chạy provider. Các test MockMvc tạo CSRF token hợp lệ để kiểm chính xác lỗi 401/429 và login 200.

## 6. Nâng cấp lên Redis và nhiều instance

### 6.1. Vì sao RAM per-pod không đủ?

Nếu có 4 pod và mỗi pod giữ counters riêng, bot phân phối request qua load balancer sẽ nhân quota cho account. Kể cả một pod, `retryAfterSeconds()` và `failed()` là hai thao tác khác nhau: nhiều request đồng thời có thể qua precheck trước khi failure được ghi. `synchronized` không thể bảo vệ cả cluster và cũng không biến hai bước thành một admission reservation.

### 6.2. Atomic admission và failure counters

Một thiết kế production nên phân biệt:

- **Request admission counter/token bucket:** atomic check + reserve quota **trước khi password hashing**; giới hạn concurrency/burst.
- **Failure counter:** tăng atomically sau authentication failure; account và IP rules có window/TTL.
- **MFA/risk signals:** separate counters cho OTP/reset, đăng nhập thành công bất thường và challenge.
- **TTL/cardinality:** mỗi account/IP key có expiry, maximum key count và bộ dọn state; không lưu hàng triệu username ngẫu nhiên mãi.

Mẫu key mang tính minh họa:

```text
auth:fail:account:<HMAC(normalized-identifier)>
auth:fail:ip:<canonical-ip-or-prefix>
auth:admission:route:<route-id>:<time-bucket>
```

Dùng HMAC với key phía server để tránh lộ username/email thô trong Redis keys và logs, nhưng vẫn cần bảo vệ Redis và rotation. Với Redis Cluster, Lua script thao tác nhiều key nguyên tử phải bảo đảm keys cùng hash slot hoặc thiết kế split phù hợp.

Pseudo-logic **không phải Lua chạy độc lập**:

```text
function atomicFailureIncrement(key, ttlSeconds):
    n = INCR(key)
    if n == 1: EXPIRE(key, ttlSeconds)
    return n

function atomicAdmit(keys, requestedCost):
    if any quota would be exceeded: return DENY + retryAfter
    reserve all required quotas atomically
    return ALLOW
```

Sử dụng Redis Lua/transaction để `INCR` và `EXPIRE` không bị tách rời; với strict admission quota phải có atomic reservation. Sliding window có thể dùng sorted sets với pruning/count/add atomically; token bucket giúp kiểm burst mượt hơn fixed window (fixed window dễ bị dồn request sát ranh giới). Chọn thuật toán theo traffic và SLO, không đưa một Lua script sơ sài vào production khi chưa test concurrency/cluster.

### 6.3. Redis lỗi: fail-open hay fail-closed?

Không có đáp án toàn cầu. Fail-open ưu tiên availability nhưng suy yếu bảo vệ; fail-closed chặn cả người dùng thật khi store lỗi; degraded mode có thể dùng hạn mức tại gateway/per-instance, circuit breaker, alert và risk controls. Cần ghi chính sách cho mỗi loại endpoint và threat model, test Redis timeout/failover và tránh retry storm. Nếu login thuộc dịch vụ rủi ro cao, phối hợp MFA/IdP và quy trình recovery khi không thể xác minh rate limit.

## 7. Trusted client IP sau reverse proxy/WAF

Ứng dụng phía sau Nginx/Envoy/CDN có thể chỉ thấy `request.getRemoteAddr()` là IP proxy. Nếu giới hạn theo IP đó, **mọi user** có thể bị gom vào một quota. Nhưng nếu đọc thẳng header `X-Forwarded-For` do Internet client gửi, attacker có thể giả mạo IP và vượt giới hạn.

Cách triển khai:

1. Chỉ **trusted proxy** được phép ghi/chuẩn hóa forwarded headers sau khi xác định nguồn kết nối. Proxy phải loại bỏ hoặc ghi đè headers từ client không tin.
2. Firewall/private network/mTLS hoặc allowlist chặn truy cập trực tiếp origin/app bypass WAF.
3. Định nghĩa chuỗi trusted hops và canonical client IP; cả edge và app cùng dùng một định nghĩa để correlation.
4. `ForwardedHeaderFilter` hoặc `server.forward-headers-strategy` chỉ dùng sau khi trust boundary đã được bảo vệ; chúng không tự xác minh tính đáng tin của header.
5. Test gửi header giả từ Internet **không làm đổi IP** được dùng trong limiter; test user thật qua gateway không bị gộp vào IP của proxy.
6. Với IPv6 privacy addresses, mobile carriers, VPN doanh nghiệp, NAT, hạn mức theo một IP phải điều chỉnh để giảm false positives.

## 8. WAF/gateway policy theo đường dẫn và phương thức

Không chỉ bảo vệ `POST /login`. Bề mặt xác thực có thể gồm:

- Username/password login trên web, API và mobile.
- MFA/OTP challenge, resend OTP/email.
- Forgot password và password reset.
- Magic link/passwordless login.
- Account registration và activation.
- Token/refresh, device authorization polling.
- SSO/OIDC callback/session management (trong khi password guessing chính ở IdP).

Mỗi endpoint có semantics khác. Login password được kiểm theo account/IP; OTP cần quota theo challenge/session/account; resend cần quota để ngăn spam; refresh token cần phát hiện replay và token rotation; reset endpoint cần generic messages.

**Đừng rate-limit mọi URL bằng một ngưỡng cố định.** Edge global limit quá thấp có thể làm toàn bộ khách hàng không login được vào giờ cao điểm. Có thể thử monitor-only/shadow mode, thu baseline, bắt đầu với soft challenges và tăng blocking theo dữ liệu.

**Bảo vệ trước khi tốn CPU:** bcrypt/argon2 vốn tốn tài nguyên; WAF/gateway có thể loại traffic thô và admission limiter ngay trước password provider tiết kiệm CPU, nhưng app vẫn phải có account-aware rules để ngăn bot đổi IP.

## 9. Account lockout, MFA và UX

Một policy “5 lần sai thì khóa vĩnh viễn tài khoản” tạo điểm tấn công DoS: kẻ biết email của nạn nhân chỉ cần cố ý gửi 5 password sai. Ngay cả khóa 24 giờ cũng có thể phá hoạt động sản phẩm. Do đó:

- Ưu tiên cooldown ngắn, progressive backoff với trần, challenge/step-up MFA và monitoring.
- Dùng MFA/passkeys cho tài khoản quan trọng; chúng giảm tác hại khi password bị lộ.
- Thông báo chung khi login thất bại; không tiết lộ account đang locked/disabled qua public response.
- Bảo vệ quy trình recovery của chính account; reset/MFA không được là “đường vòng” dễ abuse.
- Tránh reset IP/global counter khi một user thành công; có thể giữ risk state để phát hiện password spraying.
- Cho phép support/recovery sau xác minh và có audit; không dùng bypass vô hạn không kiểm soát.

CAPTCHA chỉ là defense-in-depth: bot có thể giải hoặc thuê giải CAPTCHA. Không dùng CAPTCHA thay giới hạn tốc độ, MFA hoặc phát hiện rủi ro.

## 10. Logs, metrics và cảnh báo

Các metric có thể dùng:

| Tên metric/event | Ý nghĩa | Tránh |
| --- | --- | --- |
| `login_attempt_total` theo route/client | Tổng số request thử. | Ghi raw password/username vào labels. |
| `login_failures_total` theo nguyên nhân chuẩn hóa | Sai credential, disabled, MFA fail nội bộ. | Trả lỗi cụ thể ra public response. |
| `login_throttled_total` theo rule | Đo app/edge quota và false positives. | Đếm lặp cùng event mà không correlation. |
| `login_success_total` | Tỷ lệ thành công và biến động bất thường. | Xóa hết risk state sau success. |
| `limiter_storage_errors_total` | Redis outage, timeout, failover. | Retry vô hạn và flood Redis. |
| IP/account distinct count trong window | Credential stuffing và password spraying. | Lưu PII thô lâu hoặc làm high-cardinality labels. |

Logs dùng request ID để liên hệ edge/gateway/app/IdP nhưng không ghi raw session cookies, token, password, OTP, recovery codes. Identity có thể được pseudonymize/HMAC với key an toàn theo privacy policy. Giới hạn retention và quyền truy cập.

**Tín hiệu:** một account bị thử từ nhiều IP; một IP thử rất nhiều account; nhiều account từ nhiều IP với failure rate cao; login thành công bất thường sau chuỗi thất bại; hoặc 429 tăng đồng thời với support tickets (false positive). Cần có runbook: bật WAF policy, kiểm tài khoản compromise, yêu cầu MFA, revoke sessions, thông báo đúng kênh và rollback rule nếu ảnh hưởng khách hàng thật.

## 11. Kiểm thử toàn hệ thống, không chỉ unit test

Checklist từ app tới hạ tầng:

1. **Account across IPs:** cùng một user bị thử từ nhiều IP vẫn có rate limit.
2. **IP across users:** nhiều username từ một IP bị chặn khi phù hợp.
3. **Unknown user:** response không tiết lộ existence, account unknown cũng được đếm.
4. **Concurrency:** nhiều POST login song song không vượt strict admission quota đã thiết kế.
5. **Multi-pod:** request qua pod A/B/C cùng dùng một bộ đếm phân tán.
6. **TTL:** counter hết hạn đúng, reset/eviction không làm memory tăng vô hạn.
7. **IP spoof:** client gửi `X-Forwarded-For` giả không bypass quota.
8. **NAT/shared IP:** user thật qua mobile/corporate proxy không bị lock vô lý.
9. **CSRF:** POST cookie login không token bị từ chối; có token vẫn phải kiểm password/quota.
10. **IdP:** login OIDC/SAML cần verify anti-brute-force tại IdP, MFA và security event integration.
11. **Failure mode:** Redis/WAF outage, retry storm, backpressure và fallback theo runbook.
12. **Telemetry:** alarm có request correlation; metrics không lộ secrets.
13. **Đường vòng:** OTP, reset, register, magic link, refresh token, legacy login URL đều được inventory.
14. **Bảo vệ data sau login:** role/scope không thay object ownership hay tenant authorization.

**Kiểm thử hai chiều:** chỉ test 429 có thể che cấu hình `denyAll()`; chỉ test login 200 có thể che `permitAll()`. Cần positive login, wrong password, limit reached, valid user khác không bị chặn ngoài ý muốn và tài nguyên sau login có đúng quyền.

### 11.1. Rollout policy có kiểm soát

Triển khai monitor-only nếu hạ tầng hỗ trợ, đo baseline theo giờ cao điểm, tenant/ASN, mobile và doanh nghiệp dùng NAT. Bắt đầu với soft challenges và giới hạn rõ ràng, sau đó tăng hard-block dựa trên false-positive rate, CPU load, credential stuffing signal và hỗ trợ khách hàng. Có owner/on-call và rollback procedure, không thay ngưỡng trong giờ incident mà không audit.

## 12. Các lỗi triển khai phổ biến

| Sai lầm | Tác hại | Sửa đúng |
| --- | --- | --- |
| Chỉ rate limit theo IP. | Bot đổi IP; NAT gây chặn oan. | Account + IP + network/risk. |
| Chỉ hard-lock account. | Kẻ tấn công khóa nạn nhân. | Adaptive delay/step-up và recovery. |
| Counter RAM per-pod. | Quota nhân theo số pod. | Redis shared state/edge limits. |
| `GET` rồi `INCR` độc lập. | Race khi parallel requests. | Atomic reservation + TTL. |
| Tin `X-Forwarded-For` client tự gửi. | IP spoofing và bypass. | Trusted proxy + deny origin bypass. |
| Limit sau password hashing. | CPU DoS vẫn xảy ra. | Admission check trước hash + edge. |
| Không TTL hoặc cleanup keys. | Memory/cardinality exhaustion. | Bounded keys, TTL, eviction. |
| User không tồn tại nhận 404. | Username enumeration. | Generic response & timing mitigation. |
| Login đúng reset mọi IP counter. | Attacker xóa dấu vết spray. | Chọn lọc reset. |
| Tắt CSRF chỉ để POST login pass. | CSRF risk với browser cookie. | Token handling theo flow. |
| Chỉ WAF, không app/IdP policy. | Không thấy credential guessing theo account. | Layered defense và telemetry. |
| Không kiểm Redis outage. | Login outage hoặc fail-open bất ngờ. | Degraded mode/runbook. |
| Quên reset/OTP endpoint. | Attacker chuyển vector. | Bảo vệ toàn bộ auth surface. |
| Log password, token hoặc PII thô. | Lộ secrets và privacy risk. | Redaction, access control, retention. |

## 13. Bài tập tự kiểm tra

**A.** WAF giới hạn 20 POST/min/IP nhưng attacker thử một user từ 500 IP, mỗi IP 2 lần.  
**Đáp án:** IP limiter không đủ; cần account rate detection, risk/MFA và dữ liệu tổng hợp.

**B.** Login limit đặt tại mỗi Spring Boot pod, autoscale từ 2 lên 8 pod.  
**Đáp án:** Quota account bị nhân theo pod; dùng distributed limiter/edge và kiểm atomicity.

**C.** User bị khóa 24 giờ sau 5 lần sai; attacker có email nạn nhân.  
**Đáp án:** Tạo DoS đối với nạn nhân. Cân nhắc cooldown ngắn, step-up, challenge và recovery an toàn.

**D.** API có `X-Forwarded-For` từ request bất kỳ và dùng giá trị đó làm IP.  
**Đáp án:** Header có thể bị giả; chỉ tin headers sau trusted reverse proxy đã chuẩn hóa, khóa origin.

**E.** POST login không CSRF trả 403; developer kết luận account bị throttle.  
**Đáp án:** Không đủ bằng chứng; CSRF filter có thể từ chối trước login provider. Test với CSRF token hợp lệ và kiểm chính xác status 401/429.

**F.** Tên user không tồn tại trả lỗi “no such user” nhưng user thật sai password trả “wrong password”.  
**Đáp án:** User enumeration. Dùng thông báo thống nhất và theo dõi timing/status.

**G.** Một IP thử nhiều user, sau đó login đúng bằng một account mà attacker kiểm soát. Tất cả quota IP bị reset.  
**Đáp án:** Đó là bypass. Giữ IP/network risk counters hoặc reset có chọn lọc theo policy.

**H.** Spring OAuth2 Login dùng IdP bên ngoài; app giới hạn `POST /login` nhưng không quản trị IdP.  
**Đáp án:** Không thể mặc định chống brute force ở IdP. Kiểm bảo vệ password/MFA tại IdP và bảo vệ callback/session tại app.

**I.** Redis ngừng hoạt động, app không có chính sách fallback.  
**Đáp án:** Thiếu thiết kế vận hành: cần quyết định fail-open/closed/degraded theo rủi ro, gateway controls và alert.

**J.** JWT Resource Server API nhận Bearer token nhưng developer giới hạn login `POST /login` để chống token guessing.  
**Đáp án:** Phải bảo vệ authorization/token endpoint tương ứng và API Bearer theo semantics của nó; login form local không tự bảo vệ token/IdP.

## 14. Checklist production

- [ ] Đã inventory login, OTP/MFA, reset, magic link, register, refresh và IdP endpoints.
- [ ] Threat model bao gồm brute force, spraying, stuffing, enumeration, CPU DoS và account-lock DoS.
- [ ] Có nhiều keys account/IP/network/risk, tránh chỉ một địa chỉ.
- [ ] Có early request admission trước password hash; distributed atomic quota khi nhiều pod.
- [ ] Counter có TTL, eviction và bounded cardinality; unknown users vẫn có policy.
- [ ] Canonical client IP được cấp bởi trusted proxy; chặn origin bypass.
- [ ] Generic errors, hạn chế timing differences và `Retry-After` nhất quán.
- [ ] Lockout không quá cứng; có MFA/passkeys, step-up và recovery.
- [ ] Browser form/session giữ CSRF/cookie security.
- [ ] WAF, gateway, app và IdP có policy owner rõ và đường dẫn cụ thể.
- [ ] Metrics/alerts theo rule/layer, không chứa secrets hoặc raw PII labels.
- [ ] Test multi-IP, multi-user, multi-pod, concurrency, TTL, IP spoof và Redis failure.
- [ ] Có false-positive measurement, shadow rollout, incident-response và rollback plan.

## 15. Ghi nhớ và tài liệu chính thức

**Công thức triển khai:** WAF/gateway làm giảm flood; Spring Security/IdP phân biệt các lần thử password và quyền account; distributed store giới hạn nhất quán giữa nhiều instances; monitoring tìm tấn công phân tán và user thật bị ảnh hưởng. Không có một captcha, account lock hay rate limit IP nào thay thế được phòng vệ nhiều lớp. MFA/passkeys, password hygiene và thiết kế recovery an toàn là thành phần thiết yếu bên cạnh throttling.

Tài liệu để đối chiếu:

- [OWASP Authentication Cheat Sheet — Login Throttling, Lockout, Enumeration](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html)
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
- [Spring Security — Password/Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Servlet Filter Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Redis — INCR Command and Rate Limiting Pattern](https://redis.io/docs/latest/commands/incr/)
