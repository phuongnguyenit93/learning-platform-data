# Không ghi mật khẩu, token, API key hoặc mã khôi phục vào log

Khi phòng chống tấn công vào hệ thống xác thực Spring Security, nhật ký (*log*) là công cụ quan trọng để phát hiện đăng nhập thất bại, phát hiện truy cập bị từ chối, điều tra sự cố và giám sát hoạt động quản trị. Nhưng chính log cũng có thể trở thành **kho credential bị rò rỉ** nếu mã ứng dụng hoặc hạ tầng vô tình ghi mật khẩu, access token, refresh token, API key, recovery code hay session cookie.

**Nguyên tắc chính:** *Ghi sự kiện bảo mật và kết quả xử lý, không ghi bí mật được dùng để thực hiện sự kiện đó.* Ví dụ có thể ghi `security_event=LOGIN_REJECTED`, `outcome=DENIED` và một ID truy vết do server tạo; không ghi trường `password`, toàn bộ header `Authorization`, `Cookie` hoặc chuỗi token mà người dùng vừa gửi.

Bài học áp dụng cho **Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet)**, cũng hữu ích cho WebFlux, API Gateway, reverse proxy và hệ thống observability. Ví dụ minh họa chỉ dùng dữ liệu thử nghiệm, không đòi credential thật. Mục tiêu là thiết lập cơ chế **ngăn dữ liệu nhạy cảm đi vào log ngay từ nguồn**, thay vì trông chờ một regex che chuỗi sau khi bí mật đã lọt vào pipeline.

## 1. Vì sao một dòng log có thể làm vô hiệu cơ chế xác thực?

Giả sử API nhận:

~~~http
POST /api/auth/login HTTP/1.1
Content-Type: application/json
Authorization: Bearer <ACCESS_TOKEN_TEST_ONLY>

{
  "username": "alice",
  "password": "<PASSWORD_TEST_ONLY>"
}
~~~

Một developer có thể nghĩ ghi toàn bộ request để debug sẽ giúp điều tra lỗi:

~~~java
// SAI: có thể ghi cả mật khẩu hoặc token người dùng vừa nhập.
log.debug("loginRequest={}", requestBody);
log.debug("authorization={}", httpRequest.getHeader("Authorization"));
~~~

Nếu kẻ tấn công có quyền đọc log, hệ quả có thể là:

- **Password**: thử đăng nhập lại hoặc dùng trong credential-stuffing trên dịch vụ khác.
- **Bearer access token**: truy cập API dưới danh nghĩa chủ token cho đến khi token bị từ chối/hết hạn.
- **Refresh token**: xin access token mới, tiềm ẩn quyền truy cập lâu hơn.
- **Session cookie/ID**: chiếm phiên tùy chính sách session và phòng vệ bổ sung.
- **API key**: gọi dịch vụ tích hợp, tiêu thụ quota, đọc/sửa dữ liệu.
- **Mã khôi phục (recovery code)**: vượt qua một bước xác thực đa yếu tố hoặc chiếm quyền khôi phục.
- **Reset password/magic-link/one-time token**: chiếm quyền thao tác reset hoặc tạo phiên khi token còn hiệu lực.
- **Private key, client secret, connection string có credential**: chiếm quyền của ứng dụng/dịch vụ thay vì chỉ một user.

Log thường được sao chép sang collector, dashboard, APM, tracing, hệ thống cảnh báo, bản backup hoặc đơn vị hỗ trợ bên ngoài; xóa một dòng trong file local **không đảm bảo** đã xóa mọi bản sao. Đây là lý do dữ liệu nhạy cảm phải bị **loại bỏ trước khi ghi**.

## 2. Phân loại: dữ liệu nào tuyệt đối không ghi nguyên văn?

| Loại dữ liệu | Ví dụ vị trí xuất hiện | Quy tắc |
| --- | --- | --- |
| **Mật khẩu**: current/new/confirm/temporary | JSON/form body, query lỗi, DTO, exception | **Không log**, kể cả login thất bại; không dùng `toString()` của DTO chứa password |
| **Password hash** | DB entity, `UserDetails`, response debug | Không đưa vào log; tuy không phải plaintext nhưng có thể bị tấn công offline |
| **Bearer access token, JWT, ID token** | Header `Authorization`, cookie, body, query | Không log raw token hoặc payload/claims nhạy cảm; có thể ghi mã lỗi validator |
| **Refresh token, opaque token, session ID** | Cookie, token endpoint, response `Set-Cookie` | Không log; session ID là credential trong nhiều cơ chế |
| **API key, client secret** | `X-API-Key`, `Authorization: Basic`, config, env, HTTP response | Không log giá trị; quản lý riêng bằng secret store |
| **Mã MFA/recovery/backup code** | Form đổi thiết bị, reset, TOTP recovery | Không log cả mã đã dùng lẫn chưa dùng |
| **Password reset token, magic-link OTT** | Query string `?token=...`, path, email redirect | Không log URL chứa token; ghi event về yêu cầu hoặc consume thành công/thất bại |
| **Khóa riêng, seed, signing secret** | PEM, keystore, JWT issuer, Vault response | Không log; cần bảo vệ cả metadata và đường phát sinh lỗi |
| **PII không cần thiết** | Email, điện thoại, IP, thiết bị | Hạn chế theo mục đích điều tra và quy định riêng tư; nếu cần có access control/retention |
| **Dữ liệu an toàn để log khi thiết kế đúng** | Event type đã cố định, HTTP status, outcome enum, server request ID, route template | Cho phép khi đã kiểm tra provenance, kích thước và không chứa giá trị người dùng có thể chèn bí mật |

**Lưu ý về “mask”:** ghi `Authorization: Bearer ****` đỡ nguy hiểm hơn ghi token nguyên văn, nhưng tốt nhất là **không thu thập toàn bộ header** nếu không cần. Cơ chế cắt còn 4 ký tự cuối của API key/token cũng có thể làm lộ thông tin có giá trị trong một số mô hình; không mặc định làm vậy. Một token dạng JWT có thể chứa thông tin nhạy cảm ở payload dù chữ ký bị che.

### “Mật khẩu đã mã hóa Base64” có an toàn không?

Không. Base64 chỉ là **encoding**, người khác có thể giải mã. Tương tự, JWT ba đoạn thường có payload Base64url đọc được; `jwt.toString()`/`getClaims()` có thể tiết lộ danh tính, email hoặc các thuộc tính nhạy cảm. Không log token rồi cho rằng “không đọc được ngay” nên an toàn.

### Có nên log SHA-256 của token để đối chiếu?

Không mặc định. Hash không khóa của mã khôi phục ngắn, OTP hoặc API key entropy thấp có thể bị dò offline. Kể cả token entropy cao, fingerprint ổn định có thể liên kết người dùng/phiên qua hệ thống log. Nếu bắt buộc tương quan, ưu tiên **random event ID**, hoặc thiết kế token reference nội bộ/HMAC tách khóa với chính sách quyền truy cập và vòng đời; phải đánh giá rủi ro riêng, không biến hash thành một secret mới xuất hiện ở mọi log.

## 3. Các điểm rò rỉ ngoài câu lệnh log của developer

~~~text
Client
  │
  ├─ Browser URL/history/devtools
  │
  ▼
CDN / WAF / Load Balancer / API Gateway / Nginx
  │ ├─ access log chứa path + query
  │ ├─ debug request/response headers
  │ └─ WAF sample/trace
  ▼
Servlet container (Tomcat)
  │ ├─ access log
  │ └─ exception/error details
  ▼
Spring Security filter chain
  │ ├─ authentication failure/success handlers
  │ └─ debug/TRACE của security library
  ▼
Spring MVC Controller / Service
  │ ├─ log DTO / exception / validation error
  │ ├─ request/response logging filter
  │ └─ DB/HTTP client tracing
  ▼
Logback / SLF4J + MDC / Micrometer / OpenTelemetry
  │ ├─ exporter/collector/APM
  │ ├─ log aggregator/index
  │ └─ alerts, dumps, backups và support bundles
~~~

Không có “một công tắc” đủ bảo vệ toàn bộ đường truyền này. Phải kiểm tra **mọi nơi có thể tạo và chuyển log**, bao gồm:

1. **Backend source**: các call `log.debug/info/warn/error`, `System.out.println`, `printStackTrace()`, class `toString()`, AOP logging, audit event và HTTP client interceptors.
2. **Web filters**: `CommonsRequestLoggingFilter` hoặc filter tự viết có thể đọc/ghi header, query, payload; tránh bật bừa.
3. **Spring MVC**: cấu hình cho phép in chi tiết request ở DEBUG/TRACE.
4. **Error handler**: `@ControllerAdvice` có thể serialize toàn bộ exception/DTO, khiến `rejectedValue` chứa password lộ ra.
5. **Database/ORM/driver**: log SQL bind parameters, connection URL kèm credential hoặc bind values.
6. **Reverse proxy/load balancer**: nhiều access log format mặc định ghi nguyên request line, bao gồm query string.
7. **Traces/APM/metrics**: tự đặt tag `authorization`, `request.body`, `session_id` hoặc `token` biến bí mật thành telemetry có độ lan tỏa lớn.
8. **CI/build/tools**: `curl -v`, pipeline debug, test report, crash dump, environment dumps, troubleshooting attachments.
9. **Frontend/mobile**: console/debug network, third-party analytics và client error tracking có thể nhận input hoặc URL token.
10. **Alert/chat**: hệ thống gửi toàn bộ log line/stack trace sang email, chat hay ticket mở rộng người có quyền đọc.

**Đừng chỉ kiểm tra log của lớp Controller.** Một `request.getHeader("Authorization")` bị in bởi proxy hoặc APM vẫn là sự cố dù controller không có một dòng log nào.

## 4. Thiết kế sự kiện bảo mật an toàn: log *metadata*, không log secret

Một bộ từ vựng log giúp tránh việc mỗi developer ghép chuỗi tự do:

| Sự kiện | Metadata tối thiểu gợi ý | Tuyệt đối tránh |
| --- | --- | --- |
| `LOGIN_REJECTED` | time, outcome, audit ID, reason **category** nội bộ, app/module | Password vừa thử, toàn `Authentication`, username nếu không cần |
| `LOGIN_ACCEPTED` | time, event, account ID nội bộ có kiểm soát, audit ID | Session ID, credential/password |
| `JWT_REJECTED` | mã loại lỗi `SIGNATURE_INVALID`/`EXPIRED`/`AUDIENCE_INVALID` | Raw JWT, JWT claims, header Authorization |
| `API_KEY_ROTATED` | key record ID **do hệ thống phát hành** (không phải raw key), action outcome | API key cũ/mới, secret prefix đáng ngờ |
| `RECOVERY_REQUESTED` | event, generic outcome, rate-limit classification | Recovery code, reset token, “email X không tồn tại” nếu không cần |
| `MFA_CODE_REJECTED` | type chung, audit ID, outcome | OTP/TOTP/recovery code |
| `ACCESS_DENIED` | policy/route template, HTTP 403, audit ID | URL có token, full request, serialized principal/authorities nhạy cảm |
| `ACCOUNT_LOCKED` | event, reason category, privacy-safe account reference nếu policy cho phép | Password sai, mã reset và thông tin email ngoài phạm vi |

### 4.1. Sử dụng allowlist field

**Cách không an toàn:**

~~~java
// SAI: request, credentials hoặc exception có thể chứa secret.
log.warn("Login failed: {}", request);
log.warn("Authentication details: {}", authentication);
log.warn("Reason: {}", exception.getMessage());
log.warn("Headers: {}", request.getHeaderNames());
log.warn("JWT: {}", jwt);
~~~

Ở một số trường hợp `request.getHeaderNames()` chỉ hiển thị tên header, nhưng đoạn log trên là mẫu xấu vì thu thập context không cần thiết; người khác dễ “nâng cấp” nó thành dump cả values. `exception.getMessage()` đặc biệt nguy hiểm khi exception được tạo từ dữ liệu đầu vào hoặc do thư viện/HTTP client đưa giá trị credential vào message. Không gọi `log.warn("...", exception)` ở luồng xác thực nhạy cảm một cách mặc định mà chưa xác định exception chain có chứa secret hay không.

**Cách an toàn hơn:**

~~~java
log.warn("security_event={} outcome={} audit_id={}",
        "LOGIN_REJECTED", "DENIED", generatedAuditId);
~~~

Tuy nhiên `generatedAuditId` phải do server sinh hoặc được kiểm tra chặt, không dùng nguyên header `X-Request-ID` từ client nếu không tin nguồn; header có thể chứa newline, văn bản giả log hoặc thông tin bí mật do attacker chèn. Và một log call an toàn **không đảm bảo** filter/proxy bên ngoài cũng an toàn.

### 4.2. Vì sao enum giúp giảm rủi ro?

Nếu logger chỉ nhận `SecurityEvent` và `Outcome` (enum hữu hạn), developer khó vô tình truyền password hoặc nguyên exception. Khi muốn mở rộng log, reviewer phải thay đổi interface của hàm thay vì truyền bất kỳ `Object` hay `Map<String,Object>` nào.

Mã sự kiện/nhãn nên nhỏ, ổn định và hữu ích cho SIEM, ví dụ `LOGIN_REJECTED`, `TOKEN_INVALID` và `RECOVERY_REDEEM_FAILED`. Tránh reason code quá chi tiết ở response công khai khiến attacker suy ra tài khoản có tồn tại hay không.

## 5. Ví dụ Java 17 độc lập, không cần Spring: log an toàn và stdout chính xác

Ví dụ tối giản dùng `java.util.logging` và một `enum` để minh họa có thể điều tra sự kiện mà không cần đặt secret vào logger. Tệp độc lập `SafeAuditJava17.java`:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class SafeAuditJava17 {

    enum Event {
        LOGIN_REJECTED, TOKEN_REJECTED, API_KEY_ROTATED
    }

    enum Outcome {
        DENIED, COMPLETED
    }

    private static final Logger AUDIT =
            Logger.getLogger("example.security.audit");

    public static void main(String[] args) {
        AUDIT.setUseParentHandlers(false);
        AUDIT.setLevel(Level.INFO);

        StreamHandler handler = new StreamHandler(System.out,
                new Formatter() {
                    @Override
                    public String format(LogRecord record) {
                        return formatMessage(record)
                                + System.lineSeparator();
                    }
                });
        handler.setLevel(Level.INFO);
        AUDIT.addHandler(handler);

        // Mật khẩu/token/API key không được đưa vào tham số log.
        // ID demo được kiểm soát, không lấy từ HTTP header.
        audit(Event.LOGIN_REJECTED, Outcome.DENIED, "audit-001");
        audit(Event.TOKEN_REJECTED, Outcome.DENIED, "audit-002");
        audit(Event.API_KEY_ROTATED, Outcome.COMPLETED, "audit-003");

        handler.flush();
        AUDIT.removeHandler(handler);
        handler.close();
    }

    static void audit(Event event, Outcome outcome, String auditId) {
        AUDIT.log(Level.INFO,
                "security_event={0} outcome={1} audit_id={2}",
                new Object[] {
                    event.name(), outcome.name(), auditId
                });
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 SafeAuditJava17.java
java SafeAuditJava17
~~~

**Stdout xác định**:

~~~text
security_event=LOGIN_REJECTED outcome=DENIED audit_id=audit-001
security_event=TOKEN_REJECTED outcome=DENIED audit_id=audit-002
security_event=API_KEY_ROTATED outcome=COMPLETED audit_id=audit-003
~~~

Đoạn này không chứa, đọc hay xác thực credential; nó **chỉ chứng minh một cách thiết kế event logger**. Không đưa nguyên `AuditId` do client tự gửi vào hàm trên trong hệ thống thực; phải dùng ID server-generated/được kiểm tra.

### Điểm mạnh và giới hạn

Mẫu dùng enum và tham số định sẵn giúp không có đường trực tiếp để người lập trình truyền raw password vào log. Dù vậy, triển khai thật vẫn cần:

- Quy ước rõ field nào được bổ sung;
- Kiểm tra input lạ trong metadata như route, username, user agent, IP;
- Bảo mật kênh log và quyền truy cập;
- Kiểm tra các logger **khác** trong ứng dụng và hạ tầng;
- Tự động kiểm tra secret leakage bằng canary trong CI.

Một dòng event log “sạch” không cho phép kết luận toàn hệ thống không rò secret nếu framework debug hoặc proxy vẫn ghi request.

## 6. Spring Boot 3.5 + Spring Security 6.5: safe authentication failure logging

Ứng dụng mẫu này dùng **form login** của Spring Security. Khi một lần đăng nhập bị từ chối, `AuthenticationFailureHandler` ghi **chỉ event code, outcome và audit ID do server sinh**. Nó không ghi `request`, `authentication`, `password`, `exception.getMessage()` hoặc body.

### 6.1. Gradle dependencies

Trong project Spring Boot 3.5.x đã có Boot Gradle plugin/BOM, JDK 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Spring Boot starter logging thường mang SLF4J/Logback; ví dụ và bài test dưới đây dựa trên logging mặc định của Boot 3.x. Nếu project thay logger backend, cách chặn log và capture test có thể cần khác.

### 6.2. application.properties

Tệp `src/main/resources/application.properties`:

~~~properties
# Để tường minh: không cho Spring MVC in request details ở DEBUG/TRACE.
spring.mvc.log-request-details=false

# Giữ log tại mức cần thiết. Không bật debug HTTP body/headers toàn ứng dụng.
logging.level.org.springframework.web=INFO
logging.level.org.springframework.security=INFO

# Password người dùng lab được truyền qua biến môi trường/secret store.
# Không commit giá trị demo.password thực vào repository.
demo.password=${DEMO_PASSWORD}
~~~

`spring.mvc.log-request-details=false` là thuộc tính Spring Boot 3.5, mặc định đã là `false`; đặt rõ tránh vô tình cho phép log request parameters/headers. Nó **không bao phủ** một custom filter, SDK telemetry, Nginx hay log code do bạn tự viết.

**Không dùng `logging.level.root=OFF` để “giải quyết” lộ secret:** điều đó che mất dấu hiệu tấn công. Cần xử lý nguồn rò, không tắt toàn bộ audit/security monitoring.

### 6.3. File Java đầy đủ

Tệp `src/main/java/example/safelog/SafeLoggingApplication.java`:

~~~java
package example.safelog;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SafeLoggingApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeLoggingApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService labUsers(
            PasswordEncoder encoder,
            @Value("${demo.password}") String rawDemoPassword) {

        // Tài khoản chỉ dùng trong lab: không commit password vào mã nguồn.
        UserDetails labUser = User.withUsername("lab-user")
                .password(encoder.encode(rawDemoPassword))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(labUser);
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http, SafeSecurityAudit audit)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .failureHandler((request, response, exception) -> {
                    // KHÔNG LOG exception, request, password hoặc username.
                    audit.record(SecurityEvent.LOGIN_REJECTED,
                            AuditOutcome.DENIED);
                    response.sendRedirect(
                            request.getContextPath() + "/login?error");
                }));

        return http.build();
    }
}

enum SecurityEvent {
    LOGIN_REJECTED,
    TOKEN_REJECTED,
    RECOVERY_REDEEM_FAILED,
    API_KEY_ROTATED
}

enum AuditOutcome {
    DENIED, COMPLETED
}

@Component
class SafeSecurityAudit {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeSecurityAudit.class);

    void record(SecurityEvent event, AuditOutcome outcome) {
        // ID luôn sinh trong server; không đọc header do client gửi.
        String auditId = UUID.randomUUID().toString();
        LOG.warn("security_event={} outcome={} audit_id={}",
                event.name(), outcome.name(), auditId);
    }
}

@RestController
class PrivatePage {
    @GetMapping("/private")
    String privatePage() {
        return "ok";
    }
}
~~~

**Cách hoạt động:**

1. `InMemoryUserDetailsManager` có một user lab để Spring không tự tạo một mật khẩu khởi tạo ngẫu nhiên và in giá trị ấy ra console trong môi trường dev; password lab do người chạy cung cấp, encode trước khi lưu.
2. `formLogin` có default login page tại `GET /login`, xử lý `POST /login` và CSRF theo cấu hình Spring Security mặc định.
3. `AuthenticationFailureHandler` được gọi khi login thất bại; nó chỉ ghi `LOGIN_REJECTED`/`DENIED` và UUID. Không truyền đối tượng `exception` vào logger.
4. Sau log, handler đưa browser về `/login?error`. URL này chứa **mã trạng thái hiển thị**, không chứa credential hay user identifier.
5. `/private` cần authentication, nên request chưa đăng nhập được redirect tới form login.
6. Khi login thành công, Spring Security dùng session thông thường; ví dụ không log session ID/cookie.
7. Code là **demo local**; production phải dùng user repository thật, HTTPS, rate limiting, account-locking/MFA/session policy, không lưu tài khoản mẫu trong RAM.

**Lưu ý:** mặc định form login có thể sử dụng request parameter `username`/`password`; Spring Security xử lý nội bộ. Việc một framework **đọc** password để xác thực không có nghĩa bạn được phép **ghi** password ra logger. Không bật `CommonsRequestLoggingFilter` đọc toàn request để “xem form có gì”.

### 6.4. Chạy lab

Cần đặt `DEMO_PASSWORD` bằng một phương thức bí mật do hệ điều hành/IDE/secret manager cung cấp **trước khi** chạy, không gõ giá trị thật vào shell command hiển thị trong build log, CI YAML hoặc message chat. Mật khẩu này là **dữ liệu lab**, không dùng lại với tài khoản thật.

~~~bash
./gradlew bootRun
~~~

Trên Windows, dùng `gradlew.bat bootRun`.

Khi chạy đúng, mở `http://localhost:8080/login`, thử user `lab-user` với password **sai**. Browser được redirect tới `/login?error`, console có dòng tương tự:

~~~text
... WARN ... security_event=LOGIN_REJECTED outcome=DENIED audit_id=<uuid-do-server-tao>
~~~

Đây là **dạng log dự kiến**, không phải stdout cố định: timestamp, logger format và UUID thay đổi ở mỗi lần chạy. Console không được có password vừa nhập hay header session/cookie. Nếu thử đúng password lab do `DEMO_PASSWORD` cung cấp, login thành công và `GET /private` trả:

~~~text
ok
~~~

**Đừng bật DEBUG/TRACE toàn framework để chụp “bằng chứng” rồi đưa logs có secret lên ticket.** Kiểm tra có kiểm soát bằng dữ liệu giả tại môi trường test, không sử dụng credential thật.

## 7. Kiểm thử tự động: dùng canary để phát hiện credential lọt vào app log

**Canary** là một chuỗi giả độc nhất chỉ dùng trong test, ví dụ `TEST_CANARY_DO_NOT_USE_2026`. Test gửi canary qua đúng trường password/token/API key/recovery code rồi kiểm tra **đầu ra log thực** không chứa canary. Canary **không phải mật khẩu thật** và tuyệt đối không được dùng làm secret production.

Dưới đây là test Spring Boot 3.5 + JUnit 5 + MockMvc/Logback. Nó bắt `ILoggingEvent` từ logger riêng của `SafeSecurityAudit`; test xác minh đoạn logger này không ghi canary. **Giới hạn:** việc chỉ capture logger của lớp audit không chứng minh mọi proxy/filter/APM đều an toàn. Hãy bổ sung integration/canary test cấp pipeline ở mục sau.

Tệp `src/test/java/example/safelog/SafeSecurityAuditTest.java`:

~~~java
package example.safelog;

import java.util.stream.Collectors;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = "demo.password=TEST_ONLY_LAB_PASSWORD")
@AutoConfigureMockMvc
class SafeSecurityAuditTest {

    @Autowired MockMvc mvc;

    @Test
    void rejectedLoginDoesNotPutPasswordInAuditLog()
            throws Exception {

        // Giả lập một password SAI, chỉ là dữ liệu canary của test.
        String canary = "TEST_CANARY_DO_NOT_USE_2026";

        Logger auditLogger = (Logger) LoggerFactory.getLogger(
                SafeSecurityAudit.class);

        ListAppender<ILoggingEvent> buffer = new ListAppender<>();
        buffer.start();
        auditLogger.addAppender(buffer);

        try {
            mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "lab-user")
                    .param("password", canary))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"));

            String messages = buffer.list.stream()
                    .map(ILoggingEvent::getFormattedMessage)
                    .collect(Collectors.joining("\n"));

            assertTrue(messages.contains(
                    "security_event=LOGIN_REJECTED"));
            assertTrue(messages.contains("outcome=DENIED"));
            assertFalse(messages.contains(canary));
            assertFalse(messages.contains("TEST_ONLY_LAB_PASSWORD"));
        }
        finally {
            auditLogger.detachAppender(buffer);
            buffer.stop();
        }
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests example.safelog.SafeSecurityAuditTest
~~~

Kết quả mong đợi: test pass nếu app và library phù hợp, redirect được handler thực hiện và logger không chứa password canary. **Không kết luận “không rò credential toàn hệ thống” chỉ từ test này**. Nó không quan sát Nginx, container access logs, request filters ngoài test context, HTTP client logs, APM exporter hoặc dashboard.

### 7.1. Test canary toàn pipeline

Một bài kiểm thử tích hợp tốt hơn cần đưa các chuỗi canary *khác nhau* vào:

- `password` và `currentPassword`/`newPassword`;
- `Authorization: Bearer <canary>`;
- `X-API-Key: <canary>`;
- `Cookie: JSESSIONID=<canary>` và response `Set-Cookie` khi có flow phù hợp;
- `recoveryCode`, `otp`, `resetToken` trong JSON/form;
- `?token=<canary>` và path chứa canary trong môi trường test để phát hiện proxy access-log leakage (sau đó sửa kiến trúc không truyền secret qua URL nếu có thể);
- Exception message, validation rejectedValue và request DTO auto-generated `toString()`;
- Outbound client request chứa API key tới service khác.

Sau khi gửi request, thu thập **tất cả kênh ghi** trong test environment: ứng dụng, container, ingress/proxy/WAF, log collector, APM/traces, metrics tags, error tracking, alert/ticket exports. Quét exact canary và các encoding thông thường chỉ khi được phép; đừng vì search không thấy chuỗi raw mà bỏ qua Base64, URL-encoding hoặc JSON-escaping của secret.

Một test có giá trị nếu nó xác nhận **không xuất hiện trong nguồn dữ liệu đã thu thập**. Không có quyền đọc APM/proxy thì ghi kết luận đúng phạm vi: “app logger pass”, không được ghi “system-wide pass”.

### 7.2. Kiểm tra hỏng có chủ đích

Trong môi trường test, tạo một filter sai (không merge vào production) ghi `Authorization` rồi kiểm tra pipeline test **phát hiện** canary. Điều này chứng minh phép kiểm tra có khả năng bắt lỗi, không chỉ pass vì test chưa thu được log nào. Khi kết thúc test, gỡ filter sai và chắc chắn không deploy vào bất kỳ môi trường thật nào.

## 8. Spring Framework và các cấu hình logging dễ làm rò secret

### 8.1. Spring MVC request-details logging

Theo Spring Framework, thông tin chi tiết parameters/headers của request được che khi DEBUG/TRACE theo mặc định; việc bật `enableLoggingRequestDetails` có thể hiển thị dữ liệu nhạy cảm. Spring Boot 3.5 có:

~~~properties
spring.mvc.log-request-details=false
~~~

Không đặt thành `true` trên hệ thống chứa form password hoặc header Authorization mà không có cơ chế kiểm soát đã được đánh giá. Không giả định chỉ cần property này là bảo vệ được custom filter/proxy: đó là **một lớp** trong Spring MVC.

### 8.2. CommonsRequestLoggingFilter

`CommonsRequestLoggingFilter`/`AbstractRequestLoggingFilter` có các công tắc:

- `setIncludeHeaders(boolean)`;
- `setIncludePayload(boolean)`;
- `setIncludeQueryString(boolean)`;
- `setIncludeClientInfo(boolean)`;
- `setHeaderPredicate(Predicate<String>)`;
- `setMaxPayloadLength(int)`.

Một cấu hình thận trọng **nếu ứng dụng bắt buộc có request logging filter**:

~~~java
CommonsRequestLoggingFilter filter = new CommonsRequestLoggingFilter();
filter.setIncludeHeaders(false);
filter.setIncludePayload(false);
filter.setIncludeQueryString(false);
filter.setIncludeClientInfo(false);
~~~

Snippet này cần import `org.springframework.web.filter.CommonsRequestLoggingFilter` và được đặt trong cấu hình thích hợp, **chưa phải chương trình độc lập**. Dù các flag trên đều false, filter vẫn có thể ghi **URI path** (không chứa query). Nếu ứng dụng nhúng reset token/API key trong đường dẫn path, URI vẫn có thể lộ. Vì vậy tốt nhất **không dùng request logging generic** trên endpoint nhạy cảm, chỉ ghi route template/event code đã định nghĩa.

**Đừng dùng `setMaxPayloadLength(20)` làm cơ chế che password.** Nó chỉ cắt số ký tự được log, không phân loại dữ liệu; 20 ký tự đầu có thể đã đủ để lộ bí mật.

### 8.3. Spring Security DEBUG và Authentication objects

Một số thành phần Security có thể thêm thông tin debug hữu ích khi troubleshooting, nhưng không nên xem bất kỳ mức log nào là “chắc chắn không chứa PII/secret” trong mọi version và custom extension.

Đặc biệt tránh:

~~~java
// SAI: credentials/details có thể bị lộ qua serialization/toString.
log.debug("SecurityContext={}", SecurityContextHolder.getContext());
log.debug("Authentication={}", authentication);
log.debug("Request={}", request);
log.debug("Exception={}", exception);
~~~

Ngay cả khi một implementation cố xóa/mask credentials khi authenticated, các custom `Authentication`, `AuthenticationDetailsSource` hoặc exception có thể mang dữ liệu raw. Chỉ log mã event và những metadata đã kiểm soát.

### 8.4. @ControllerAdvice, Bean Validation và error reporting

Một DTO như:

~~~java
record LoginRequest(String username, String password) {
}
~~~

Java `record` có `toString()` tự sinh chứa cả field `password`; gọi `log.info("{}", loginRequest)` có thể in secret. Đây là lý do không đưa DTO nhạy cảm vào logging. Nếu muốn giảm rủi ro lỡ gọi `toString`, có thể định nghĩa một kiểu DTO với `toString()` trả ra nhãn đã che; nhưng **không** dùng override đó làm biện pháp duy nhất vì JSON serializer/filter vẫn đọc raw fields.

Khi xử lý `MethodArgumentNotValidException`, `FieldError.getRejectedValue()` có thể chứa password/OTP. Chỉ trả field name và error code đã whitelist:

~~~java
// Minh họa bên trong @ExceptionHandler(MethodArgumentNotValidException.class).
List<String> invalidFields = exception.getBindingResult()
        .getFieldErrors().stream()
        .map(error -> error.getField())
        .distinct()
        .toList();

log.warn("security_event={} invalid_field_count={}",
        "VALIDATION_REJECTED", invalidFields.size());
~~~

Không log hoặc trả `exception.getMessage()`, `getRejectedValue()`, cả `BindingResult` hay request body. Với endpoint reset/login, phản hồi lỗi **không cho attacker biết user có tồn tại hay không**; có thể dùng chung thông báo trong khi ghi category nội bộ không nhạy cảm vào audit.

## 9. Reverse proxy, URL và access log

### 9.1. Query string là một ổ rò phổ biến

Nhiều proxy dùng access log chứa HTTP request line kiểu:

~~~text
"GET /reset-password?token=<RESET_TOKEN_TEST_ONLY> HTTP/1.1" 200
~~~

Một người dùng mở magic link có token ở query có thể khiến token đi qua browser history, proxy access logs, error tracking, referrer hoặc analytics. Dù token chỉ dùng một lần, **trước khi tiêu thụ** nó vẫn là credential.

Phòng vệ:

1. Nếu giao thức cho phép, đưa token vào body hoặc quy trình chuyển đổi an toàn thay vì tiếp tục lan truyền trên URL.
2. Nếu magic-link yêu cầu token trong URL, kiểm soát access log/query, referrer và third-party resources; dùng `Referrer-Policy: no-referrer` cho trang nhạy cảm.
3. Không ghi toàn bộ `requestURI + "?" + queryString`, không ghi full `getRequestURL()`/`getQueryString()`.
4. Không xây redirect URL chứa token mới rồi log `Location` response header.
5. Hạn chế TTL và atomic one-time consume, tránh token còn sử dụng được sau lần mở link đầu tiên; nhưng **single-use không thay cho phòng chống leak**.

### 9.2. Nginx: mô hình log không có query/token

Một ví dụ access log **đơn giản hóa** chỉ ghi method, mã kết quả và route category cố định, không ghi `$request` hay `$request_uri`:

~~~nginx
map $uri $safe_route {
    default "other";
    =/login "login";
    =/api/auth/login "auth_login";
    =/reset-password "password_reset";
}

log_format safe_auth '$remote_addr $request_method $safe_route '
                     '$status $request_time';

access_log /var/log/nginx/access.log safe_auth;
~~~

Đặt `map` ở context `http` và áp `access_log` trong context phù hợp. `$uri` ở đây chỉ dùng **để chọn một nhãn tĩnh** trong whitelist, không được in trực tiếp. Nếu đường dẫn biến thiên với token/username, nó chỉ được log thành `other`, không ghi nguyên chuỗi path. Đây là **minh họa kỹ thuật**, cấu hình Nginx thật cần tương thích routing, reverse proxy, privacy policy, trust boundaries và yêu cầu audit của tổ chức. IP trong log vẫn là dữ liệu cần quản trị quyền riêng tư/retention.

Không dùng câu “đã tắt Spring request logging” để kết luận Nginx access log đã an toàn: đó là hai pipeline khác nhau.

## 10. Micrometer, OpenTelemetry, MDC và logs có cấu trúc

Spring Boot có ba trụ cột observability: **log, metrics, traces**, và tích hợp Micrometer Observation. Một chuỗi log có thể không chứa token nhưng vẫn bị rò qua:

- tag `http.request.header.authorization`;
- `request.body`/`response.body`;
- span attribute `url.full` (có query);
- tag `session.id`, `api.key`, `jwt` hoặc `recovery.code`;
- message bất kỳ gắn vào baggage/MDC rồi được exporter ghi lại;
- error reporting SaaS thu thập request/exception stack trong nền.

### 10.1. Không đưa secret vào MDC

MDC/trace baggage được thiết kế để **truyền context**, không phải kho lưu secret. Không gọi:

~~~java
// SAI: dễ xuất hiện trong mọi dòng log của cùng thread.
MDC.put("token", bearerToken);
MDC.put("apiKey", apiKey);
MDC.put("sessionId", sessionId);
~~~

Chỉ dùng field được cho phép như random correlation ID, route template hoặc mã subsystem do server đặt và đã được chuẩn hóa/kiểm tra. Với web thread pool, phải dọn MDC đúng vòng đời request (`MDC.remove`/`MDC.clear` thích hợp), tránh context rò sang request khác. Trong reactive pipelines, `ThreadLocal` có giới hạn; dùng cơ chế context propagation phù hợp, nhưng vẫn **không** đưa credential vào context.

### 10.2. Metrics và cardinality

Tránh `token_value`, `user_input` hoặc `email` như metric tag. Metrics có thể lưu/lan truyền riêng và dễ bị tăng cardinality gây tốn tài nguyên. Nên dùng category hữu hạn:

~~~text
auth_attempts_total{event="login", outcome="denied", reason="invalid_credentials"}
auth_attempts_total{event="token", outcome="denied", reason="expired"}
~~~

Dòng là **ví dụ biểu diễn metrics**, không phải cấu hình Prometheus/Micrometer hoàn chỉnh. `reason` ở đây là nhãn cố định từ allowlist, không phải `exception.getMessage()` hoặc JWT claim.

### 10.3. Logback masking có thay được việc không log secret?

**Không.** Converter/filter/redaction ở Logback hoặc collector chỉ nên là *defense in depth*:

- Regex có thể bỏ sót JSON escaping, Base64/URL encoding, token với định dạng mới, nested fields hoặc dữ liệu chia thành nhiều dòng.
- Bí mật có thể đã bị truyền vào memory buffer, collector, stdout hoặc network trước khi mask cuối cùng.
- Một secret nằm trong exception/call stack khác có thể không khớp tên field `password`.
- Việc in *một phần* token vẫn có thể là rủi ro, tùy thuật toán và threat model.

Ưu tiên **không ghi secret ngay trong API logger** và **không thu body/headers nhạy cảm** ở filter/proxy/tracing; sau đó mới dùng masking như lưới an toàn phụ.

## 11. Secret có thể lộ qua Java exception và thư viện khác

### 11.1. Đừng đưa nguyên exception message ra log/API theo mặc định

Trong một số trường hợp exception từ HTTP client, database, JSON parser hay validation có thể chứa:

- URL với `?api_key=...` hoặc `?token=...`;
- database connection string và username/password;
- body/field value bị reject;
- access token trong message của external API;
- đối tượng chứa recovery code qua `toString()` tự sinh.

**Không có nghĩa phải bỏ hết stack trace:** với exception của thành phần đã đánh giá không chứa secret, có thể log trong kênh nội bộ có quyền/retention phù hợp. Nhưng đối với luồng **authentication/password reset/token exchange**, nên chọn mã lỗi đã whitelist và kiểm soát mọi exception/message cause trước khi xuất. Client không nên thấy stack trace hoặc raw upstream error.

### 11.2. HTTP client/outbound integrations

Khi RestClient/WebClient/Feign hoặc một SDK thêm `Authorization`/`X-API-Key` vào request đi ra:

- Đừng bật full wire logging hoặc log body/headers của outbound request.
- Nếu interceptor cần log, chỉ log host/route **đã tin cậy**, method, outcome, timeout category và correlation ID.
- Không log request builder toàn phần hoặc full response body từ token endpoint.
- Nếu nhà cung cấp API trả token/secret trong error body, xử lý thành category; đừng đổ `responseBody` vào exception log.

### 11.3. CI và hỗ trợ vận hành

Các nguồn rò ở ngoài backend:

- Lệnh `curl -v`/`--trace` có thể hiển thị header Authorization, cookie, body.
- `gradle --debug`, environment dump, `env`/`printenv` và command-line args có thể lộ secret.
- Screenshot developer tools, mạng, error-tracking attachment.
- Ticket hoặc chat chứa chuỗi “hãy cho tôi xem request đầy đủ” và file HAR chưa scrub.
- Container crash dumps, heap dumps, remote diagnostic snapshots có thể chứa credential trong RAM.

Chỉ dùng **test credentials/canaries** cho debug, giới hạn quyền truy cập, và tạo quy trình scrub trước khi chia sẻ artifact. Một file có tên `debug.log` vẫn là log và phải được bảo vệ/retention như log khác.

## 12. Nếu phát hiện secret đã bị ghi vào log: xử lý sự cố

Khi một password, API key, token hoặc recovery code thực xuất hiện trong log, không chỉ sửa câu lệnh log rồi kết luận đã xong:

1. **Dừng nguồn rò** hoặc cô lập route/filter gây lộ mà không phá hủy dữ liệu điều tra cần bảo toàn.
2. **Phân loại secret**: access token, refresh token, session ID, API key, password, recovery code, reset token, private key; xác định hệ thống và phạm vi quyền.
3. **Thu hồi/đổi secret bị ảnh hưởng**: revoke session/refresh token, rotate API key/client secret, invalidate recovery/reset codes, buộc reset password khi phù hợp.
4. **Xác định khoảng thời gian và phạm vi**: log của node, proxy, collector, APM, alerts, backup, shared ticket; kiểm soát ai đã truy cập và có dấu hiệu lạm dụng không.
5. **Hạn chế truy cập log và bản sao** trong khi thực hiện điều tra; phối hợp bộ phận bảo mật/pháp chế theo quy trình.
6. **Xử lý bản sao theo chính sách retention, pháp lý và bảo toàn chứng cứ**; không xóa thiếu kiểm soát khi đang điều tra.
7. **Sửa tận nguồn**, thêm test canary để ngăn tái diễn; rà soát logging config và release pipeline.
8. **Thông báo và hậu kiểm**: xác định trách nhiệm liên quan, phân tích root cause, cập nhật runbook, quyết định thông báo ảnh hưởng theo quy định áp dụng.

**Nguyên tắc:** nếu một API key đã xuất hiện ở log mà nhiều người có quyền đọc, phải đánh giá nó như credential có khả năng bị lộ; chỉ “ẩn dòng trên dashboard” không làm API key cũ trở lại an toàn.

### Checklist phản ứng theo loại secret

| Loại secret | Hành động ưu tiên |
| --- | --- |
| Password đăng nhập | Reset/rotate password theo rủi ro, xem reuse và các phiên bất thường |
| Access token | Revoke nếu được hỗ trợ hoặc chặn phiên liên quan; theo dõi tới hết hạn |
| Refresh token | Revoke token family/session phù hợp chính sách OAuth |
| Session cookie | Invalidate session server-side; xem chính sách rotation cookie |
| API key/client secret | Rotate và thay trên các workload dùng key; theo dõi mọi lần gọi lạ |
| Recovery/backup code | Invalidate mã bị lộ, phát hành bộ mã mới qua flow xác thực an toàn |
| Password reset/OTT token | Invalidate/chặn consume, phát hành lại qua kênh tin cậy |
| Private key/signing key | Xem xét key rotation, phân phối trust và ảnh hưởng tới chứng thư/token đã ký |

Các thao tác cụ thể phụ thuộc khả năng revoke của token type và kiến trúc phát hành. Không khẳng định một JWT stateless đang còn hạn có thể bị vô hiệu hóa tức thì nếu hệ thống không có denylist, token-version, issuer key rotation hoặc cơ chế tương đương.

## 13. Ma trận QA bắt buộc

| ID | Bài kiểm thử | Kết quả đạt |
| --- | --- | --- |
| S01 | Đăng nhập với password canary, cả thành công và thất bại | Không xuất hiện password trong app log, proxy, APM |
| S02 | Bearer access token canary qua `Authorization` | Không có raw token/JWT trong bất kỳ log |
| S03 | API key qua `X-API-Key`/body | Không lộ key, kể cả outbound client debug |
| S04 | Refresh token/opaque token | Không lộ ở token endpoint, audit hay response logging |
| S05 | Recovery code hoặc OTP bị từ chối | Chỉ ghi `RECOVERY_REDEEM_FAILED`/mã category |
| S06 | Reset token trong URL query test | Không xuất hiện trong access log/traces/referrer |
| S07 | Reset token nằm trong đường dẫn path | Không log raw path; chỉ ghi route template/category |
| S08 | Session ID trong Cookie và Set-Cookie | Không ghi session identifier hoặc response header chứa cookie |
| S09 | `LoginRequest.toString()`/DTO record | Không được gọi trong logger ở code thật |
| S10 | Bean Validation thất bại | Không chứa `getRejectedValue()` trong error/log |
| S11 | Spring MVC DEBUG/TRACE | Không bật `log-request-details` và không log request nhạy cảm |
| S12 | CommonsRequestLoggingFilter | Không thu headers/body/query; kiểm tra URI path còn lại |
| S13 | Nginx/Gateway access log | Không ghi `$request`/`$request_uri` chứa secret |
| S14 | Security exception với input lạ | Không log nguyên message/stack có credential |
| S15 | HTTP client request/response đến IdP | Không có Authorization/refresh token trong wire log |
| S16 | MDC/baggage/trace attributes | Không có token, key, session, raw email/password |
| S17 | Metrics labels | Chỉ enum/category hữu hạn, không có user input/high cardinality secret |
| S18 | Test CI log failure/report | Không in canary/raw payload khi test thất bại |
| S19 | Log đã xóa trên một node nhưng collector còn bản sao | Retention, export và incident workflow xử lý toàn bộ |
| S20 | Canary injection có chủ đích vào filter test | Bộ kiểm tra thực sự phát hiện rò rỉ |
| S21 | Audit event sau khi loại secrets | Vẫn đủ context: event, outcome, time, correlation ID, action |
| S22 | User-controlled request id chứa xuống dòng | Không tạo log injection, không chèn trực tiếp |
| S23 | Giảm log level production | Không vô hiệu giám sát hành vi nghi ngờ |
| S24 | WebFlux/microservice khác | Áp policy tương đương, không giả định chỉ MVC có rủi ro |

Một lần test thành công của `SafeSecurityAuditTest` chỉ bảo đảm **logger được test**. Hoàn tất QA yêu cầu kiểm soát và thu thập log từ các **thành phần thực sự triển khai**, không chỉ tuyên bố “mã này không dùng log.debug”.

## 14. Lỗi phổ biến và cách khắc phục

| Sai lầm | Vì sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| `log.info("request={}", dto)` | Record/Lombok `toString()` có thể chứa password/OTP | Chỉ log event code; tránh toString cho DTO nhạy cảm |
| `log.warn("JWT={}", jwt)` | JWT chứa claims/token có thể bị phát tán | Log `TOKEN_INVALID` và reason category |
| `log.debug("headers={}", headers)` | Có `Authorization`, `Cookie`, `X-API-Key` | Không ghi header; nếu cần metadata, chỉ chọn allowlist đã đánh giá |
| `log.error("{}", exception.getMessage())` | Message có thể chứa URL/token hoặc raw input | Dùng mã lỗi đã whitelist, kiểm soát exception logging |
| `request.getQueryString()` trong access log | Magic link/reset token dễ lọt vào log | Dùng route category, bỏ query và tránh URL-token |
| Bật `spring.mvc.log-request-details=true` | DEBUG/TRACE có thể in request chi tiết | Giữ `false`; test mọi filter/custom code |
| Bật body logger nhưng chỉ cắt 20 byte | Đoạn đầu vẫn có thể là secret | Không thu body nhạy cảm |
| Redaction regex ở log collector là biện pháp duy nhất | Lọt nhiều dạng encoding và log trước bước redaction | Ngăn tại source và gateway; masking chỉ bổ sung |
| Dùng suffix/fingerprint token để correlate mặc định | Có thể lộ một phần hoặc tạo tracking ID | Dùng ID ngẫu nhiên server-side hoặc thiết kế HMAC được duyệt |
| Gửi error response nguyên exception | Có thể lộ password/SQL/token ra client, sau đó thành log | Trả status + mã lỗi chung + server audit ID |
| Cho người support xem raw HAR | Chứa Cookie/Authorization/request body | Scrub/cấm upload credential; dùng test canary |
| Xóa log local là xong | Còn collector, backup, alert, ticket | Thực hiện incident response và rotate/revoke secret |
| Không log security event để tránh leak | Mất dấu hiệu tấn công và không đáp ứng audit | Vẫn log event an toàn và kết quả, không log secret |

## 15. Tự kiểm tra

1. Vì sao mật khẩu và recovery code không nên xuất hiện trong log **ngay cả khi đã dùng xong**?
2. Một JWT đã được ký số hợp lệ có thể đưa vào log để debug không? Vì sao?
3. Điểm nào trong chuỗi Client → Nginx → Tomcat → Spring → APM có thể rò token dù controller không log?
4. Vì sao log nguyên `exception.getMessage()` đôi khi nguy hiểm hơn log một mã `LOGIN_REJECTED`?
5. Vì sao `LoginRequest` khai báo dưới dạng Java `record` cần tránh log cả đối tượng?
6. `spring.mvc.log-request-details=false` có tự bảo vệ Nginx/Custom filter/RestClient không?
7. Nếu proxy đã bỏ query nhưng vẫn log raw URI path có token, còn rủi ro gì?
8. Khác nhau giữa “mask token bằng regex” và “không thu token vào log ngay từ đầu” là gì?
9. Test `SafeSecurityAuditTest` pass có chứng minh APM/collector không nhận credential không?
10. Nếu phát hiện refresh token thật đã lọt vào log, chỉ xóa bản ghi log có đủ chưa?
11. Có nên đưa session ID hoặc API key vào MDC/metric tags để dễ trace không?
12. Có thể log những trường nào để điều tra brute-force mà không in password hay token?

**Đáp án định hướng:** (1) vẫn là dữ liệu nhạy cảm có thể dùng lại/giúp tấn công và có nhiều bản sao; (2) không, token vẫn là credential và có claims; (3) mọi tầng có access/request/trace logging; (4) message có thể chứa input; (5) auto-toString có thể in password; (6) không; (7) secret trong path vẫn lộ; (8) ngăn tại source vững hơn và giảm phạm vi phát tán; (9) không, test chỉ quan sát logger nhất định; (10) không, cần rotate/revoke và điều tra bản sao; (11) không; (12) event, outcome, timestamp, mã lỗi, server correlation ID, metadata đã được duyệt.

## 16. Checklist nghiệm thu

- [ ] Không có password/currentPassword/newPassword, TOTP, recoveryCode, reset token trong app/access/APM logs.
- [ ] Không có `Authorization`/`Cookie`/`Set-Cookie`/`X-API-Key` raw values trong logs.
- [ ] Không ghi JWT/opaque token/session ID/key/secret/hash dạng đầy đủ hoặc chỉ “mã hóa Base64”.
- [ ] Controller/Service/Filter/exception handlers không log DTO, Authentication, SecurityContext hoặc raw request.
- [ ] Spring MVC `log-request-details=false`; generic request logging filter không thu body/header/query của luồng nhạy cảm.
- [ ] Gateway/proxy không log query, path chứa token hoặc request/response headers nhạy cảm.
- [ ] MDC, traces, metrics, tags, APM và error tracking không có credential.
- [ ] Có thiết kế audit event allowlist với outcome/code và server-generated correlation ID.
- [ ] Log retention, access control, encryption/tamper protection phù hợp quy định.
- [ ] Có canary tests kiểm tra cả ứng dụng và hạ tầng được triển khai; có kiểm tra tiêu cực bắt leak.
- [ ] Có playbook thu hồi/rotate credential, xử lý bản sao logs và thông báo sự cố.
- [ ] Vẫn giữ đủ sự kiện đăng nhập thất bại/thành công, truy cập bị từ chối, đổi key, khôi phục tài khoản để phục vụ phát hiện tấn công.

## 17. Tài liệu tham khảo

- [OWASP Logging Cheat Sheet — Data to exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Sensitive Data Exposure / Security Logging Testing](https://owasp.github.io/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/02-Configuration_and_Deployment_Management/02-Application_Platform_Configuration)
- [Spring Framework 6.2 — MVC Logging, Sensitive Data](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/logging.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Framework 6.2 — AbstractRequestLoggingFilter API](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/web/filter/AbstractRequestLoggingFilter.html)
- [Spring Security 6.5 — Form Login and AuthenticationFailureHandler](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot — HTTP Exchanges](https://docs.spring.io/spring-boot/reference/actuator/http-exchanges.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)
