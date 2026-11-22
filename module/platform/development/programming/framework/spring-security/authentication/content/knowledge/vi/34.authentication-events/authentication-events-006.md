# Tách tác vụ kiểm toán khỏi đường xử lý dễ gây tăng độ trễ hoặc lộ dữ liệu

## 1. Tại sao audit authentication phải được tách khỏi xử lý đăng nhập?

Trong một ứng dụng Spring Security, khi người dùng nhập đúng/sai mật khẩu, dùng OTP, truy cập bằng Bearer token hoặc thực hiện xác thực lại, hệ thống thường muốn ghi **sự kiện kiểm toán (audit event)**: ai đã thử, khi nào, phương thức nào, kết quả, lý do lỗi ở mức an toàn và thông tin tương quan phục vụ điều tra.

Điều dễ mắc sai lầm là làm mọi thứ ngay trong luồng nhận request:

```text
POST /login
  → UsernamePasswordAuthenticationFilter
  → AuthenticationManager xác minh password
  → AuthenticationSuccessEvent / AuthenticationFailureEvent
  → @EventListener
  → gọi database, gọi Kafka/HTTP, tra GeoIP, gửi email, log toàn Authentication
  → phản hồi cho người dùng
```

Trong cấu hình mặc định của Spring Application Events, listener thường chạy **đồng bộ trên chính luồng phát sự kiện**. Một câu lệnh ghi DB mất 1 giây, một HTTP request audit timeout 3 giây hoặc lỗi ghi file log có thể làm tăng latency của login; exception từ listener đồng bộ thậm chí có thể ảnh hưởng luồng xác thực. Nếu listener ghi `Authentication.toString()` hoặc `getCredentials()`, hệ thống có nguy cơ **lộ mật khẩu, token, session data hoặc thông tin cá nhân**.

Bài này trình bày cách:

- Hiểu **ai phát** và **ai nhận** sự kiện xác thực trong Spring Security.
- Phân biệt bước **bảo mật bắt buộc trên đường đồng bộ** với bước **kiểm toán/telemetry có thể chuyển sang hậu xử lý**.
- Chỉ lấy **snapshot tối thiểu, đã loại bỏ dữ liệu nhạy cảm**, không mang nguyên `Authentication` sang queue.
- Tách công việc I/O qua **hàng đợi có giới hạn**, backpressure, chính sách khi queue đầy và monitoring.
- Chọn giải pháp **durable message/outbox** nếu audit có yêu cầu chống mất, thay vì nhầm `@Async` với lưu bền vững.
- Triển khai minh họa bằng Java 17+, Spring Boot 3.x/Spring Security 6.x, và kiểm thử tính đúng, latency, bảo mật dữ liệu.

**Phân biệt ngay từ đầu:** audit để quan sát/điều tra thường có thể thực hiện sau xác thực; nhưng **rate limiting, account lock, MFA, kiểm chữ ký token, cảnh báo rủi ro dùng để từ chối request, authorization** có thể là điều kiện đồng bộ bắt buộc. Không “đẩy sang async” một kiểm soát bảo mật mà request phải vượt qua trước khi được cho phép.

## 2. Cơ chế phát sự kiện xác thực trong Spring Security

Spring Security có `AuthenticationEventPublisher`. Với `DefaultAuthenticationEventPublisher`, các authentication managers như `ProviderManager` có thể phát:

| Event | Ý nghĩa | Nguồn tiêu biểu |
| --- | --- | --- |
| `AuthenticationSuccessEvent` | Một lần xác thực qua manager thành công | ProviderManager/password hay provider hỗ trợ |
| `AbstractAuthenticationFailureEvent` | Lớp cha cho các failure events | Bad credentials, locked, disabled, expired… |
| `AuthenticationFailureBadCredentialsEvent` | Sai credential | Password sai, một số bearer failures được map |
| `AuthenticationFailureLockedEvent` | Account đã bị khóa | Provider phát `LockedException` |
| `AuthenticationFailureDisabledEvent` | Account bị vô hiệu hóa | Provider phát `DisabledException` |
| `InteractiveAuthenticationSuccessEvent` | Thông báo đăng nhập tương tác thành công của filter | Luồng web/form/interactive login |
| `LogoutSuccessEvent` | Kết quả logout ở nơi hỗ trợ | Logout processing |

Không giả định rằng **mỗi lần request** có đúng một event, hoặc mọi authentication mechanism đều phát cùng loại. Một hệ thống có thể phát cả success event của manager và interactive success event của filter cho cùng lần login. HTTP Bearer token có thể được xác minh trên mỗi request; lượng sự kiện có thể lớn hơn nhiều so với login form. Tự publish events trong provider tùy chỉnh, cấu hình nhiều parent managers hoặc theo dõi cả filter và manager có thể dẫn đến **đếm trùng**.

### 2.1. Sơ đồ các lớp xử lý

```text
Request /login
      │
      ▼
Authentication filter
      │
      ▼
AuthenticationManager / ProviderManager
      │
      ├─ Verify password, account policy, MFA...
      │
      ├─ success / failure
      │
      └─ AuthenticationEventPublisher
               │
               ▼
        Spring ApplicationEvent
               │
               ▼
        @EventListener (mặc định synchronous)
               │    Chỉ lấy snapshot tối thiểu
               ▼
        SafeAuditEvent không chứa credential
               │
        ┌──────┴────────┐
        ▼               ▼
   Bounded queue     Durable outbox / broker
   best effort       cho audit bắt buộc
        │               │
        ▼               ▼
   Audit consumer   Outbox relay/consumer
        │               │
        └──────┬────────┘
               ▼
      Storage/analytics/SIEM
```

**Một listener đồng bộ vẫn có thể rất nhẹ** nếu chỉ chuẩn hóa và enqueue một bản ghi nhỏ. Tách khỏi đường request là tách **việc I/O nặng hoặc chậm**, không có nghĩa cần chạy mọi logic xác thực trên thread khác.

### 2.2. Cách đăng ký publisher

Trong Spring Security 6.5, tài liệu có ví dụ bean:

```java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher publisher) {
    return new DefaultAuthenticationEventPublisher(publisher);
}
```

Các imports là `org.springframework.security.authentication.AuthenticationEventPublisher`, `DefaultAuthenticationEventPublisher` và `org.springframework.context.ApplicationEventPublisher`. Đây là **snippet bên trong class @Configuration**, không phải Java file độc lập.

Spring Boot có thể tự cấu hình publisher theo phiên bản/cấu hình. Khi ứng dụng tự dựng `ProviderManager` hoặc authentication manager khác, phải đảm bảo publisher được liên kết đúng; không chỉ tạo listener rồi mặc định manager nào cũng phát. `DefaultAuthenticationEventPublisher` ánh xạ nhiều lỗi xác thực sang các event type; ánh xạ lớp exception tùy chỉnh có thể cần đăng ký thêm, và kiểm tra điều kiện exact exception class trong tài liệu.

## 3. Vì sao listener “ghi audit ngay” là anti-pattern?

Giả sử đoạn sau nằm trong class xử lý event:

```java
// PHẢN VÍ DỤ — KHÔNG triển khai
@EventListener
void unsafe(AuthenticationFailureBadCredentialsEvent event) {
    log.warn("Failed authentication: {}", event.getAuthentication());
    remoteAuditClient.post(event);
    userRepository.findByName(event.getAuthentication().getName());
    emailService.sendAlert(event.getAuthentication());
}
```

Đây là snippet minh họa lỗi, không phải class chạy độc lập.

Có ít nhất bốn vấn đề:

1. **Latency:** mạng, DB, email/SIEM bên ngoài làm tăng thời gian người dùng chờ login, có thể dẫn đến timeout/cạn servlet threads.
2. **Tính sẵn sàng:** dịch vụ audit không sẵn sàng có thể gây ảnh hưởng trực tiếp authentication nếu exception từ listener đồng bộ bị ném ngược.
3. **Dữ liệu nhạy cảm:** toàn bộ `Authentication` có thể chứa credentials, principal, `details`, thông tin phiên, remote address hoặc thuộc tính custom. `toString()` không phải hợp đồng redaction.
4. **Khuếch đại tấn công:** attacker chủ động tạo nhiều failed logins rồi buộc hệ thống mở nhiều HTTP connection, DB writes, emails, GeoIP lookups; tự biến chức năng audit thành DoS.

**Không sửa bằng cách đơn giản gọi `new Thread(...)` cho mỗi event.** Cách đó tạo số thread không giới hạn, không quản lifecycle/rejection, không có bảo đảm bền vững và tiếp tục đưa object nhạy cảm sang thread khác.

## 4. Phân loại: cái gì cần đồng bộ, cái gì có thể bất đồng bộ?

Không phải tất cả sự kiện “security” đều có chính sách mất dữ liệu giống nhau:

| Công việc | Vị trí hợp lý | Nếu thất bại |
| --- | --- | --- |
| Kiểm password, token, MFA | Trước khi cho qua request | Từ chối xác thực, không bỏ qua |
| Account khóa/disabled/revocation check | Trên đường ra quyết định bảo mật | Fail closed theo chính sách |
| Rate limit / chống brute force đang quyết định request | Trước việc xác minh tốn tài nguyên | Fail closed/degraded guard được thiết kế |
| Phân quyền trên role/tenant/ownership | Trước khi trả dữ liệu | Không cho qua |
| Ghi chỉ số tổng hợp login attempts | Hậu xử lý async/best effort | Có thể mất mẫu có đo lường |
| Đưa sự kiện an toàn vào SIEM phục vụ điều tra | Async, queue/broker có kiểm soát | Cần phát hiện mất, retry, chính sách lưu bền |
| Audit yêu cầu pháp lý hoặc phê duyệt giao dịch | Durable synchronous handoff/outbox khi ràng buộc | Có thể phải fail closed nếu không ghi nhận được |
| Gửi email cảnh báo người dùng | Async qua queue phù hợp | Retry, chống spam, không làm chậm login |
| Phân tích địa lý/IP reputation cho dashboard | Async nếu chỉ quan sát | Không tác động quyết định đăng nhập vừa xử lý |

**Quy tắc quyết định:** nếu hành động phải hoàn tất **trước khi** quyền được trao, không được âm thầm hoãn sang async. Nếu mục đích chỉ là ghi nhận, cảnh báo và phân tích, nên tách khỏi đường xử lý, với mức độ tin cậy/độ trễ được xác định rõ.

Ví dụ sự kiện “admin chấp nhận điều khoản trước khi được cấp quyền” có thể đòi ghi nhận durable như phần của giao dịch. Còn “đếm login success cho dashboard” thường chấp nhận tính gần đúng.

## 5. Thiết kế một SafeAuditEvent tối thiểu

**Không enqueue trực tiếp `Authentication`, `HttpServletRequest`, `SecurityContext` hoặc exception object.** Hãy tạo DTO/record immutable, chỉ gồm dữ liệu theo allowlist phục vụ audit.

Ví dụ schema:

| Thuộc tính | Kiểu/ý nghĩa | Lưu ý |
| --- | --- | --- |
| `eventId` | UUID tạo một lần tại nguồn | Dedupe khi consumer retry |
| `occurredAt` | Timestamp UTC tại nguồn | Giữ giờ gốc; giờ consumer là dữ liệu khác |
| `eventType` | Enum/chuỗi cố định `AUTH_SUCCESS`, `AUTH_FAILURE` | Không cho client tự chỉ định |
| `actorRef` | HMAC của canonical account identifier | Pseudonymous, không phải anonymous tuyệt đối |
| `actorKind` | `ASSERTED` / `VERIFIED` | Failures chứa username do attacker khai, không phải identity đã xác nhận |
| `mechanism` | `PASSWORD`, `BEARER`, `OIDC`… nếu tin được | Suy ra từ provider/chain, không từ header client |
| `reasonCategory` | Enum whitelist, ví dụ `BAD_CREDENTIALS` | Không sao chép exception message |
| `correlationId` | ID ngắn do server tạo hoặc validate | Tránh đưa credential vào trace |
| `sourceRef` | HMAC/aggregate của IP client tin cậy nếu cần | IP là dữ liệu nhạy cảm; chính sách retention |
| `schemaVersion` | Định dạng sự kiện | Hỗ trợ nâng cấp consumer |

**Không có**: raw password, OTP, access/refresh token, session cookie, `Authorization` header, toàn request body, full exception stack trace, nguyên `Authentication.toString()` hoặc nguyên principal object.

Nếu cần lưu email/username raw cho điều tra pháp lý, phải có một kho riêng được phân quyền, mã hóa, audit truy cập và thời hạn giữ cụ thể; không để dữ liệu raw chảy qua mọi pipeline analytics. Với HMAC, secret/pepper phải được bảo vệ riêng, thay đổi có ảnh hưởng đến việc liên kết các sự kiện qua các kỳ; nên quản key version theo policy.

### 5.1. Principal trên failure chưa chắc là người dùng thật

Khi một người gửi `username=ceo@example.test` và password sai, failure event có thể chứa chính chuỗi username được gửi. Nó **không chứng minh** CEO đã thao tác. Ghi `actorKind=ASSERTED`, không biến login failure thành hoạt động đã được xác minh của nạn nhân.

Ngược lại, sau authentication thành công do provider tin cậy, subject được xác minh mới có thể dùng `VERIFIED` theo contract. Với machine tokens, service principal, anonymous requests và OIDC, cần phân loại riêng, không mặc định `getName()` luôn là email.

## 6. Ranh giới dữ liệu: snapshot nhỏ ngay trên caller thread

Quy trình khuyến nghị cho audit best-effort:

```text
AuthenticationEvent (có thể nhạy cảm)
        │
        │ synchronous listener: O(1), không network/DB
        ▼
Sanitize + allowlist + HMAC actor + UUID
        │ SafeAuditEvent immutable, kích thước nhỏ
        ▼
Non-blocking queue.offer(record)
        │
        ├── accepted: authentication flow tiếp tục
        └── rejected: counter/alert overflow, không log secrets
                 (chỉ phù hợp với telemetry cho phép mất)
        ▼
Consumer thread theo lịch / worker pool
        │
        ├── batch + transport + retry policy
        └── audit sink / metrics / SIEM
```

Snapshot trong listener nhanh giúp tránh mang tham chiếu `Authentication` hoặc `HttpServletRequest` sang thread khác, tránh đọc thread-local `SecurityContextHolder` sau khi request đã kết thúc và tránh để logger vô tình serialize credentials.

Chỉ nên dùng `queue.offer(...)` **không blocking** cho best-effort path; `put(...)` hoặc `offer(timeout dài)` có thể khiến authentication vẫn bị chặn khi queue đầy. Bounded queue cần chính sách cụ thể khi overflow: drop một phần sự kiện low-priority, sampling, degrade, hoặc từ chối request theo yêu cầu audit. **Đừng im lặng mất dữ liệu.**

## 7. Ví dụ Java 17 độc lập: queue có giới hạn và không chặn request

Chương trình sau chỉ dùng Java standard library, minh họa việc enqueue ngay rồi consumer mới lấy ra; không phụ thuộc Spring hoặc database.

**`BoundedAuditDemo.java`**

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicLong;

public class BoundedAuditDemo {
    record AuditRecord(String kind, String actorRef) {}

    static final class AuditBuffer {
        private final ArrayBlockingQueue<AuditRecord> queue =
                new ArrayBlockingQueue<>(2);
        private final AtomicLong overflow = new AtomicLong();

        boolean offer(AuditRecord record) {
            if (queue.offer(record)) {
                return true;
            }
            overflow.incrementAndGet();
            return false;
        }

        AuditRecord poll() {
            return queue.poll();
        }

        long overflowCount() {
            return overflow.get();
        }
    }

    public static void main(String[] args) {
        AuditBuffer queue = new AuditBuffer();

        System.out.println("first = " + queue.offer(
                new AuditRecord("AUTH_SUCCESS", "actor-1")));
        System.out.println("second = " + queue.offer(
                new AuditRecord("AUTH_FAILURE", "actor-2")));
        System.out.println("third = " + queue.offer(
                new AuditRecord("AUTH_SUCCESS", "actor-3")));

        AuditRecord item;
        while ((item = queue.poll()) != null) {
            System.out.println("write = " + item.kind()
                    + ":" + item.actorRef());
        }
        System.out.println("overflow = " + queue.overflowCount());
    }
}
```

Biên dịch/chạy trên Java 17+:

```bash
javac BoundedAuditDemo.java
java BoundedAuditDemo
```

**Stdout chính xác:**

```text
first = true
second = true
third = false
write = AUTH_SUCCESS:actor-1
write = AUTH_FAILURE:actor-2
overflow = 1
```

Hai phần tử đầu chiếm hết queue có sức chứa 2; phần tử thứ ba bị từ chối ngay, không blocking. Sau đó consumer giả lập mới drain. Trong sản xuất, consumer chạy trên một thread/process riêng và có chính sách retry; ở ví dụ này consumer chạy sau các lệnh enqueue nhằm cho stdout xác định.

**Đây không phải durable audit:** process crash khi queue còn dữ liệu sẽ mất sự kiện; queue đầy làm mất thêm dữ liệu; consumer poll rồi crash trước khi lưu cũng mất. Bài tập làm rõ **độ trễ** và **chính sách overflow**, không chứng minh độ bền hay tính đầy đủ của hồ sơ kiểm toán.

## 8. Dự án Spring Boot 3.x: listener an toàn và worker riêng

Mẫu tích hợp bên dưới dùng:

- Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet.
- Spring Security events cho form login qua `DefaultAuthenticationEventPublisher`.
- `@EventListener` **đồng bộ nhưng ngắn**, chỉ tạo SafeAuditRecord đã pseudonymize và enqueue.
- `@Scheduled` worker xử lý queue ở thread khác, không làm I/O trong authentication callback.
- Bounded queue nhỏ cho **telemetry minh họa**. Đối với audit bắt buộc không được mất, áp dụng durable outbox ở mục 13.

Các class là các tệp riêng cùng package `com.example.auditdemo` dưới `src/main/java/com/example/auditdemo/`.

### 8.1. Gradle dependencies và cấu hình

Trong một project Spring Boot có Gradle plugin và dependency management đúng phiên bản, thêm khối:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo `src/main/resources/application.yml`:

```yaml
audit:
  hmac-secret: ${AUDIT_HMAC_SECRET}
  drain-millis: 500
demo:
  password: ${DEMO_USER_PASSWORD}
```

Đây là properties của **ví dụ**, không phải secret management hoàn chỉnh. `AUDIT_HMAC_SECRET` cần là secret ngẫu nhiên đủ mạnh được cấp từ secret manager; không hardcode trong repository. `DEMO_USER_PASSWORD` là mật khẩu dành cho local lab, không dùng một mật khẩu demo chung trong production.

Chạy thử ở shell Bash của môi trường phát triển:

```bash
export AUDIT_HMAC_SECRET="$(openssl rand -base64 48)"
export DEMO_USER_PASSWORD='local-lab-only-not-for-production'
./gradlew bootRun
```

Chỉ dùng cách cấp biến môi trường này trong lab. Production nên dùng secret manager, phân quyền chặt, rotation và không đưa secret vào command history hoặc CI logs. Mẫu Boot ở đây sử dụng username `local-demo` để đăng nhập web form.

### 8.2. Application, SecurityConfig, controller

**`AuthAuditApplication.java`**

```java
package com.example.auditdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class AuthAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthAuditApplication.class, args);
    }
}
```

**`SecurityConfig.java`**

```java
package com.example.auditdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher applicationPublisher) {
        return new DefaultAuthenticationEventPublisher(applicationPublisher);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${demo.password}") String demoPassword) {
        return new InMemoryUserDetailsManager(
                User.withUsername("local-demo")
                        .password(encoder.encode(demoPassword))
                        .roles("USER")
                        .build());
    }
}
```

**`DemoController.java`**

```java
package com.example.auditdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "Home: public";
    }

    @GetMapping("/private")
    public String privateResource() {
        return "Private: authenticated";
    }
}
```

Những file Java này giả định project Spring Boot 3.x chuẩn có các dependencies ở trên. `formLogin()` tạo login page mặc định và dùng session/cookie: vì vậy vẫn phải giữ CSRF protection cho POST login (trong ví dụ **không** disable CSRF). User store trong bộ nhớ chỉ phục vụ demo.

### 8.3. SafeAuditRecord: chỉ cho phép các field an toàn

**`SafeAuditRecord.java`**

```java
package com.example.auditdemo;

import java.time.Instant;

public record SafeAuditRecord(
        String id,
        Instant occurredAt,
        String kind,
        String actorRef) {
}
```

Đây là record Java 17 immutable về mặt các field chứa String/Instant. Không có `Authentication`, password, credentials, `HttpServletRequest`, IP raw hoặc exception message, nên nếu record bị serialize/log nhầm, phạm vi rò rỉ giảm đáng kể. **Pseudonymous actorRef vẫn là dữ liệu cần bảo vệ**; không coi nó hoàn toàn vô danh.

### 8.4. AuditPrivacy: chuyển username sang HMAC an toàn hơn raw identifier

**`AuditPrivacy.java`**

```java
package com.example.auditdemo;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class AuditPrivacy {

    private final SecretKeySpec secret;

    public AuditPrivacy(@Value("${audit.hmac-secret}") String rawSecret) {
        byte[] bytes = rawSecret.getBytes(StandardCharsets.UTF_8);
        if (bytes.length < 32) {
            throw new IllegalArgumentException(
                    "Audit HMAC secret needs at least 32 bytes");
        }
        this.secret = new SecretKeySpec(bytes, "HmacSHA256");
    }

    public String actorRef(String name) {
        if (name == null || name.isBlank() || name.length() > 256) {
            return "invalid-identifier";
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(secret);
            byte[] digest = mac.doFinal(
                    name.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException(
                    "Cannot calculate audit actor reference", exception);
        }
    }
}
```

**Lưu ý:** đây là HMAC của tên mà `Authentication.getName()` cung cấp. Với **failed login** tên này là *asserted username*, không chứng minh có user tương ứng. Một hệ thống thật cần canonicalization khớp chính xác với identity store (quy tắc Unicode/case/email alias) trước khi tính HMAC; không tùy tiện `toLowerCase()` nếu tên account phân biệt hoa/thường.

HMAC làm giảm khả năng suy username từ bản ghi khi đối thủ chỉ có dữ liệu audit mà **không có secret**. Nếu secret bị lộ thì người có danh sách username vẫn có thể đối chiếu. Secret cần được bảo vệ, rotation và key-versioning; không lưu toàn bộ danh sách identifiers hoặc secret trong logs.

### 8.5. AuditBuffer: enqueue nonblocking, giới hạn bộ nhớ

**`AuditBuffer.java`**

```java
package com.example.auditdemo;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

@Component
public final class AuditBuffer {

    private final ArrayBlockingQueue<SafeAuditRecord> queue =
            new ArrayBlockingQueue<>(512);

    private final AtomicLong overflow = new AtomicLong();
    private final AtomicLong captureError = new AtomicLong();
    private final AtomicLong writeError = new AtomicLong();

    public void offer(SafeAuditRecord record) {
        if (!queue.offer(record)) {
            overflow.incrementAndGet();
        }
    }

    public SafeAuditRecord poll() {
        return queue.poll();
    }

    public void markCaptureError() {
        captureError.incrementAndGet();
    }

    public void markWriteError() {
        writeError.incrementAndGet();
    }

    public long overflowCount() {
        return overflow.get();
    }

    public long captureErrorCount() {
        return captureError.get();
    }

    public long writeErrorCount() {
        return writeError.get();
    }

    public int queuedCount() {
        return queue.size();
    }
}
```

Dùng `ArrayBlockingQueue` để tránh queue tăng vô hạn khi sink bị chậm. `offer` không chờ kết nối đến audit service; overflow được đếm để có thể đo/cảnh báo. Đây là chính sách **best-effort cố ý cho demo**, không phải lựa chọn mặc định cho kiểm toán pháp lý; nếu một sự kiện bắt buộc không được mất, phải dùng đường durable trước khi trả thành công.

### 8.6. Listener chỉ snapshot; không ghi DB/HTTP trong event callback

**`AuthAuditCapture.java`**

```java
package com.example.auditdemo;

import java.time.Instant;
import java.util.UUID;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public final class AuthAuditCapture {

    private final AuditBuffer buffer;
    private final AuditPrivacy privacy;

    public AuthAuditCapture(AuditBuffer buffer, AuditPrivacy privacy) {
        this.buffer = buffer;
        this.privacy = privacy;
    }

    @EventListener
    public void onSuccess(AuthenticationSuccessEvent event) {
        capture("AUTH_SUCCESS", event.getAuthentication());
    }

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        capture("AUTH_FAILURE", event.getAuthentication());
    }

    private void capture(String kind, Authentication authentication) {
        try {
            String name = authentication == null
                    ? null : authentication.getName();

            SafeAuditRecord snapshot = new SafeAuditRecord(
                    UUID.randomUUID().toString(),
                    Instant.now(),
                    kind,
                    privacy.actorRef(name));

            buffer.offer(snapshot);
        } catch (RuntimeException unexpected) {
            // Telemetry demo: không làm hỏng login vì lỗi instrumentation.
            // Không log unexpected.getMessage() hoặc authentication.
            buffer.markCaptureError();
        }
    }
}
```

**Những điểm an toàn:**

- Listener nhận event chứa `Authentication` nhưng **không đưa object đó vào queue**.
- Không đọc `getCredentials()`, `getDetails()`, exception message, toàn principal hoặc HTTP request.
- Actor identifier được xử lý trong callback ngắn để không dựa vào request thread-local sau khi request kết thúc.
- Không kết nối database/HTTP/SIEM, không format và ghi logging hàng nghìn bytes trong auth thread.
- Nếu HMAC/instrumentation lỗi, mẫu telemetry đếm lỗi và không thay đổi outcome đăng nhập. **Với audit bắt buộc**, chính sách phải khác: không được silently ignore.
- Bản ghi minh họa chỉ có `kind`/`actorRef`, chưa có `actorKind`; consumer phải hiểu `AUTH_FAILURE` là user *asserted*, không nhất thiết đã xác minh.
- Event `AuthenticationSuccessEvent` của manager không nhất thiết là “người dùng đã hoàn tất một web session”. Nếu chỉ muốn audit session login tương tác, cần phân biệt `InteractiveAuthenticationSuccessEvent`, tránh ghi trùng và nêu rõ event semantics.

### 8.7. Consumer chạy nền, giữ lỗi rời khỏi auth thread

**`AuditDrain.java`**

```java
package com.example.auditdemo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class AuditDrain {

    private static final Logger log =
            LoggerFactory.getLogger(AuditDrain.class);

    private final AuditBuffer buffer;

    public AuditDrain(AuditBuffer buffer) {
        this.buffer = buffer;
    }

    @Scheduled(fixedDelayString = "${audit.drain-millis:500}")
    public void drain() {
        for (int i = 0; i < 100; i++) {
            SafeAuditRecord record = buffer.poll();
            if (record == null) {
                return;
            }
            try {
                log.info(
                        "audit id={} occurredAt={} kind={} actorRef={}",
                        record.id(), record.occurredAt(),
                        record.kind(), record.actorRef());
            } catch (RuntimeException failure) {
                buffer.markWriteError();
            }
        }
    }
}
```

Trong demo, consumer ghi **structured/sanitized log** làm sink. Việc ghi này chạy từ scheduler, **không chạy trên login request thread**. `@EnableScheduling` ở main class kích hoạt `@Scheduled`.

**Giới hạn phải nói rõ:** khi consumer đã `poll()` và log/DB thất bại, record có thể bị mất. Scheduler crash, process restart, queue đầy, JVM kill hoặc ghi log không durable cũng có thể mất event. Mẫu này chỉ đủ để hiểu tách latency khỏi web login, **không** chứng minh audit chính xác 100%, không có retry/idempotency và không phù hợp làm chứng cứ kiểm toán bắt buộc.

## 9. Có nên dùng @Async ngay trên @EventListener?

Spring Framework hỗ trợ `@Async` kết hợp `@EventListener` khi bật `@EnableAsync`, ví dụ:

```java
// Minh họa API, không khuyến nghị chuyển nguyên Authentication sang async.
@Async("auditExecutor")
@EventListener
public void slowAudit(AuthenticationSuccessEvent event) {
    // I/O sẽ chạy trong executor, KHÔNG ở request thread.
}
```

Việc chạy trên executor mang lại tách thread nhưng có những rủi ro khác:

1. **Event vẫn chứa object nhạy cảm.** `Authentication`/credentials/principal có thể bị giữ lại trong task queue cho tới lúc executor xử lý, và có thể bị serialize/log.
2. **Executor có thể không bounded.** Queue/task dồn lại làm tăng memory hoặc OOM nếu bị tấn công bằng login failures.
3. **Rejection và overload:** nếu executor dùng chính sách CallerRuns, khi đầy task có thể chạy trên request thread; nếu throw `TaskRejectedException`, thời điểm ném có thể tác động caller.
4. **Async exception:** lỗi trong `void @Async` không được ném lại cho request; cần `AsyncUncaughtExceptionHandler`/monitoring.
5. **Thread-local context:** `SecurityContextHolder`, MDC, tracing context không tự động được bảo đảm đi theo thread; không dựa vào context còn tồn tại sau request.
6. **Không durable:** `@Async` không tự lưu bền sự kiện, không có acknowledgements, replay hay dead-letter queue.

**Phương án tốt hơn cho giảm rò dữ liệu:** listener nhận authentication event đồng bộ, snapshot một DTO allowlist, sau đó **chỉ đưa DTO** vào executor/queue. Có thể tạo một event an toàn rồi mới dùng `@Async` cho handler của nó, nhưng vẫn cần queue bound, rejection policy và durability nếu yêu cầu.

### 9.1. Executor có giới hạn và xử lý rejection

Nếu dùng `ThreadPoolTaskExecutor`, thiết lập rõ `corePoolSize`, `maxPoolSize`, `queueCapacity`, thread name, shutdown timeout và `RejectedExecutionHandler`. Bất kỳ policy nào phải được kiểm thử dưới overload. `CallerRunsPolicy` giảm tốc người phát nhưng có thể **đưa I/O audit quay trở lại request thread**; `DiscardPolicy` giảm latency nhưng **làm mất sự kiện**. Không có lựa chọn mặc định “tốt nhất”: nó phụ thuộc bản chất audit được phép mất hay không.

Với một hệ thống yêu cầu kết quả đăng nhập p99 thấp nhưng audit bắt buộc, cân nhắc **durable handoff nhỏ nhất có thể** trước khi trả kết quả, sau đó tách mọi phần I/O dài (SIEM/email/analytics). Không thể đồng thời đòi “không bao giờ chờ bất kỳ storage nào” và “không bao giờ mất event sau crash” mà không có một đảm bảo bền vững khác.

## 10. Không biến tất cả event của Spring thành async một cách mù quáng

Spring có thể cấu hình global `ApplicationEventMulticaster` dùng executor, nhưng khi đổi globally, không chỉ audit listener chịu tác động. Các listener khác có thể đang dựa vào:

- Việc chạy cùng transaction/request thread.
- Thứ tự xử lý và thời điểm cập nhật trạng thái.
- Error propagation khi listener đồng bộ thất bại.
- SecurityContext/MDC/request context và cleanup.
- Một số listener Spring có logic nghiệp vụ cần chạy trước response.

**Không sửa vấn đề audit bằng cách đổi global event multicaster trước khi kiểm tra mọi subscriber**. Chỉ tách **listener/pipeline audit** cụ thể, ưu tiên DTO an toàn; cân nhắc transaction-bound event semantics và context propagation khi dùng async.

Với `@TransactionalEventListener`, event phát khi không có transaction có thể không được xử lý theo mong muốn (trừ khi cấu hình fallback); phát sau commit cũng không tự đem lại bền vững khi process crash ngay sau commit nhưng trước publish. Không coi annotation đó là outbox. Để đồng bộ chính xác event và giao dịch DB, phải ghi **outbox row trong cùng transaction** với thay đổi nghiệp vụ.

## 11. Durable audit khác in-memory queue như thế nào?

| Giải pháp | Latency request | Mất khi process crash? | Retry/replay | Trường hợp |
| --- | --- | --- | --- | --- |
| Listener đồng bộ ghi HTTP/SIEM | Có thể rất cao | Phụ thuộc remote ack | Tùy xây dựng, dễ block | Thường nên tránh |
| `@Async` + executor | Thấp khi chưa đầy | Có thể mất | Không tự có | Chỉ best effort khi đã giới hạn queue |
| `ArrayBlockingQueue` nội bộ | Thấp và bounded | **Có** | Không tự có | Metrics/telemetry chấp nhận mất |
| Kafka/RabbitMQ có durable broker + ack | Có bước handoff/ack khi cần bền | Giảm nếu broker được cấu hình đúng | Có thể có retry/DLQ | Log pipeline quy mô lớn |
| Database transactional outbox | Có ghi DB ngắn trong transaction | Gắn với transaction DB | Relay có thể retry | Audit cần nhất quán với thay đổi DB |
| Append-only audit store đồng bộ được bảo vệ | Có chi phí lưu bền | Tùy HA/replication | Theo hệ thống | Audit pháp lý yêu cầu mạnh |

**“Async” và “durable” là hai trục khác nhau.** Có thể async mà không durable, durable nhưng có chi phí request, hoặc vừa durable handoff vừa async downstream. Không dùng queue nội bộ rồi tuyên bố có exactly-once processing.

Phần lớn broker/consumer thực tế cho **at-least-once delivery**, vì một record có thể gửi/ghi xong nhưng ack bị mất. Phải thiết kế **idempotent consumer** bằng event ID duy nhất. Nếu audit store chỉ append không dedupe, retry có thể tạo hai dòng cho cùng một sự kiện.

## 12. Thiết kế audit schema, privacy và data minimization

### 12.1. Audit event bền vững với schema version

Ví dụ một bản ghi JSON **sau sanitize**, không chứa credential:

```json
{
  "schemaVersion": 1,
  "eventId": "fdc799ec-a5cd-40d1-8105-34648bcd1252",
  "occurredAt": "2026-10-21T09:00:00Z",
  "kind": "AUTH_FAILURE",
  "actorKind": "ASSERTED",
  "actorRef": "hmac:rotation-v1:...",
  "mechanism": "PASSWORD",
  "reasonCategory": "BAD_CREDENTIALS",
  "sourceRef": "hmac:source-v1:...",
  "correlationId": "rq-19a8b2"
}
```

Đây là **dữ liệu minh họa**, các dấu `...` không phải HMAC thực. Ví dụ actorRef ngoài code demo ở trên còn cần kèm keyVersion và subject classification khi tích hợp production.

### 12.2. Quy tắc lấy dữ liệu từ Authentication

Không làm:

```java
// PHẢN VÍ DỤ — không an toàn
String raw = authentication.toString();
String secret = String.valueOf(authentication.getCredentials());
String details = String.valueOf(authentication.getDetails());
auditClient.send(raw + secret + details);
```

Với `UsernamePasswordAuthenticationToken` chưa xác thực, credentials có thể còn chứa password hoặc một chuỗi có tính bí mật. Với `BearerTokenAuthenticationToken`, credential là **access token**. Với `OAuth2AuthenticationToken` và OIDC, principal có thể có claims/email. Các custom authentication objects có thể mang metadata bổ sung mà hệ thống log không được biết. Không dựa vào một implementation hiện tại “có vẻ che password trong toString” để quyết định pipeline toàn hệ thống an toàn.

Tốt hơn: lấy các field đã được review, giới hạn độ dài, phân loại dữ liệu, pseudonymize khi thích hợp, rồi **tạo record immutable**. Không xây `Map<String,Object>` cho phép thêm bất kỳ object vào event mà không có schema validation.

### 12.3. IP, headers và thiết bị

IP của client có thể nằm trong `WebAuthenticationDetails` nhưng trong hệ thống proxy, `getRemoteAddress()` thường phản ánh peer/proxy tùy cấu hình. Không tin `X-Forwarded-For` do client tự gửi nếu chưa được gateway/proxy đã tin cậy chuẩn hóa. Hơn nữa, IP/device fingerprint có thể là dữ liệu cá nhân, cần có mục đích lưu, TTL, truy cập và quy trình xóa phù hợp.

Correlation ID nên là ID do server tạo hoặc do gateway tin cậy phát, kiểm giới hạn ký tự/độ dài, không dùng nguyên `X-Request-Id` tùy ý để chèn log (log forging). Không đưa `Authorization`/Cookie vào MDC/baggage; MDC có thể tự được gửi đến nhiều hệ thống tracing ngoài dự kiến.

## 13. Transactional outbox cho sự kiện không được phép mất

Khi audit phục vụ kiểm toán giao dịch quan trọng hoặc quy định nội bộ yêu cầu không thất lạc, hãy xác định **durability point** trước khi thông báo thao tác thành công. Một thiết kế thường dùng:

1. Trong một DB transaction có liên quan, ghi dữ liệu nghiệp vụ và một dòng **outbox chứa SafeAuditEvent**.
2. Commit cả hai cùng nhau; nếu transaction rollback, không giả vờ rằng nghiệp vụ đã thành công.
3. Một relay riêng đọc outbox chưa xử lý, gửi broker/audit storage, nhận ack, đánh dấu đã chuyển.
4. Nếu relay crash, dòng vẫn còn và được retry; consumer phải dedupe theo event ID.
5. Hạn chế retention/outbox size, retry backoff, dead-letter handling, alert backlog và quyền truy cập DB.

**SQL minh họa PostgreSQL**, không phải migration hoàn chỉnh:

```sql
CREATE TABLE audit_outbox (
    event_id UUID PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    actor_ref VARCHAR(160) NOT NULL,
    payload_json JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX audit_outbox_pending
    ON audit_outbox (occurred_at)
    WHERE published_at IS NULL;
```

Mẫu lấy batch trong transaction relay PostgreSQL:

```sql
SELECT event_id, payload_json
FROM audit_outbox
WHERE published_at IS NULL
ORDER BY occurred_at
FOR UPDATE SKIP LOCKED
LIMIT 100;
```

Đây chỉ là **đoạn query lấy việc**, không phải toàn bộ relay/locking/ack logic. Không đánh dấu published trước khi sink/broker nhận ack. Nếu gửi thành công nhưng relay crash trước khi update `published_at`, event sẽ được gửi lại → consumer cần **idempotency**. Với high throughput, thiết kế partitioning/ordering và lock duration phù hợp; đừng giữ transaction DB chờ network quá lâu nếu có thể tránh, cân nhắc trạng thái claim/lease.

### 13.1. Lưu ý riêng với sự kiện đăng nhập

Luồng login web không nhất thiết nằm trong cùng transaction DB với một thay đổi nghiệp vụ. Nếu login dùng IdP/LDAP bên ngoài, ứng dụng **không thể tự cho rằng** việc ghi outbox local và việc IdP chấp nhận đăng nhập là một transaction phân tán atomic.

Nếu quy định bắt buộc phải ghi audit thành công trước khi trao quyền, ứng dụng có thể yêu cầu append vào durable store **trước khi trả thành công** và chọn fail closed khi lưu thất bại. Điều đó sẽ có chi phí latency và availability cần được đo/đánh giá. Hoặc dùng một audit gateway có ack đã lưu bền; bảo đảm thật sự phụ thuộc hợp đồng durability của gateway/broker.

**Điều quan trọng:** không đánh đổi âm thầm audit bắt buộc lấy tốc độ bằng cách dùng local queue rồi gọi đó là “không mất dữ liệu”. Tài liệu kiến trúc phải ghi rõ mức bảo đảm: best-effort, at-most-once, at-least-once và điểm commit/ack.

## 14. Thử nghiệm Spring Security event listener và redaction

### 14.1. Unit test listener tạo DTO mà không giữ credentials

Tạo `src/test/java/com/example/auditdemo/AuthAuditCaptureTest.java`:

```java
package com.example.auditdemo;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.event.AuthenticationFailureBadCredentialsEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;

class AuthAuditCaptureTest {

    @Test
    void failureProducesOnlyPseudonymizedRecord() {
        AuditBuffer buffer = new AuditBuffer();
        AuditPrivacy privacy = new AuditPrivacy(
                "test-audit-hmac-secret-32-bytes-minimum-2026");
        AuthAuditCapture listener = new AuthAuditCapture(buffer, privacy);

        Authentication submitted =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice@example.test", "DO_NOT_LOG_PASSWORD");

        listener.onFailure(new AuthenticationFailureBadCredentialsEvent(
                submitted, new BadCredentialsException("Invalid credential")));

        SafeAuditRecord audit = buffer.poll();
        assertNotNull(audit);
        assertEquals("AUTH_FAILURE", audit.kind());
        assertFalse(audit.toString().contains("alice@example.test"));
        assertFalse(audit.toString().contains("DO_NOT_LOG_PASSWORD"));
        assertEquals(0, buffer.queuedCount());
    }

    @Test
    void successAlsoUsesSafeActorReference() {
        AuditBuffer buffer = new AuditBuffer();
        AuditPrivacy privacy = new AuditPrivacy(
                "test-audit-hmac-secret-32-bytes-minimum-2026");
        AuthAuditCapture listener = new AuthAuditCapture(buffer, privacy);

        Authentication verified =
                UsernamePasswordAuthenticationToken.authenticated(
                        "alice@example.test", "SENSITIVE",
                        List.of(new SimpleGrantedAuthority("ROLE_USER")));

        listener.onSuccess(new AuthenticationSuccessEvent(verified));

        SafeAuditRecord audit = buffer.poll();
        assertNotNull(audit);
        assertEquals("AUTH_SUCCESS", audit.kind());
        assertFalse(audit.toString().contains("alice@example.test"));
        assertFalse(audit.toString().contains("SENSITIVE"));
    }
}
```

Đây là các unit tests của **adapter/sanitization**, không cần bật Spring context. Chạy `./gradlew test` với dependencies ở mục 8. Hai test chứng minh record tạo ra không có username/password raw trong `toString`; không chứng minh toàn pipeline/log/capture có chính sách dữ liệu đúng nếu sau này bổ sung fields không được kiểm soát.

### 14.2. Test integration để chắc event thật được phát

Một suite tích hợp nên có:

- `@SpringBootTest` + `@AutoConfigureMockMvc`, đăng nhập sai bằng `POST /login` kèm `csrf()` và xác nhận event failure được chuyển thành SafeAuditRecord.
- Đăng nhập đúng `local-demo` bằng password test từ environment rồi xác nhận event success; không log request password.
- Kiểm ứng dụng không chậm rõ rệt khi audit sink bị trì hoãn 5 giây: response path chỉ enqueue, không chờ sink.
- Kiểm malformed username rất dài/blank, lỗi HMAC, listener exception; không làm lộ raw input.
- Kiểm event phát từ provider đã cấu hình; với OIDC/LDAP/JWT tùy luồng, xác minh events thực chứ không mặc định giống form login.
- Kiểm trùng sự kiện khi cùng login phát manager success và interactive success hoặc khi custom publisher xuất hiện ở parent/child manager.

**Cẩn thận với @Scheduled trong test:** consumer có thể drain queue trước khi assertion đọc. Test có thể disable scheduling qua cấu hình riêng, dùng spy/fake sink hoặc kiểm record được persist trong fake writer bằng cơ chế đồng bộ test (latch) thay vì `Thread.sleep` tùy tiện. Unit test listener như trên tránh race.

## 15. Tính đúng và khả năng phục hồi của consumer

Với best-effort queue, ghi record chậm vẫn không làm chậm login, nhưng phải định nghĩa hệ quả:

- **Queue full:** tăng overflow metric, alert theo ngưỡng, có thể giảm sampling cho low-priority events hoặc chuyển sang durable sink; không log riêng từng event bị drop vì sẽ tạo vòng khuếch đại I/O.
- **Consumer lỗi:** retry có backoff, circuit breaker theo dependency, giới hạn concurrency, tránh busy-loop.
- **Poison event:** schema validation, dead-letter queue và alert; không retry vô hạn một record làm nghẽn mọi record phía sau.
- **Process restart:** in-memory queue mất dữ liệu; có thể graceful-drain trong shutdown nhưng không cứu được hard crash.
- **Ordering:** nhiều consumers/partitions có thể reorder; lưu `occurredAt`, event ID và sequence/partition key nếu việc sắp thứ tự là yêu cầu.
- **Duplicate:** durable delivery thường at-least-once; dedupe theo `eventId`, không dùng timestamp/username làm khóa duy nhất.
- **Consumer isolation:** dùng connection pool riêng, CPU/memory budget, outbound circuit breaker, IAM/credentials tối thiểu; lỗi sink audit không được chiếm tài nguyên auth verifier.
- **Rate limit cho event source:** attacker có thể cố ý tạo hàng nghìn authentication failures; cần bảo vệ cả ingress login và event pipeline.

Một audit pipeline khỏe phải có kiểm soát backlog (queue length, oldest-event age), sink success/timeout, retry count, dead-letter count, HMAC/capture failures và drop count. Nếu không có metrics thì việc âm thầm mất sự kiện khiến người vận hành hiểu sai rằng “không có vụ tấn công”.

## 16. SecurityContext, MDC và context propagation

Trong Servlet, `SecurityContextHolder` mặc định gắn context theo thread trong phần lớn cách cấu hình. Với async executor, listener worker chạy ở thread khác, không mặc định mang cùng context. Không nên truyền cả `SecurityContext`/`Authentication` qua thread chỉ để lấy username; hãy snapshot actorRef/tenant/correlation metadata đã lọc ngay khi nhận event.

Với tracing, dùng các cơ chế context propagation được framework hỗ trợ **chỉ cho dữ liệu không nhạy cảm**. MDC được dùng để liên kết log theo correlation ID nhưng có thể lan truyền sang nhiều hệ thống; phải clear context đúng vòng đời để không nhiễm thông tin giữa các request.

Ví dụ **pseudocode**, không phải Java độc lập:

```text
ON authentication event in request thread:
    actorRef = HMAC(trustedConfiguredSecret, canonicalIdentifier)
    requestId = validatedCorrelationIdOrServerGenerated()
    dto = SafeAuditEvent(eventId, at, kind, actorRef, requestId)
    boundedSink.tryPublish(dto)

IN worker:
    set logging context { eventId, requestId }
    try:
        persist(dto)
    finally:
        clear logging context
```

Không chụp `ServletRequestAttributes`, cookie, `Authorization` header hoặc `WebAuthenticationDetails` nguyên vẹn chỉ để sử dụng khi worker xử lý. Việc giữ tham chiếu request sau khi request hoàn tất có thể gây memory leak và xử lý sai do context lifecycle.

## 17. Ẩn dữ liệu và phòng chống log injection

Audit là kho dữ liệu có độ nhạy cảm cao, thường tồn tại lâu và nhiều người vận hành có quyền đọc. Vì vậy:

- **Allowlist fields, deny by default:** chỉ lưu trường đã được review; không dump toàn bộ object qua Jackson/generic JSON converter.
- **Redact tại nguồn:** nếu phải mang raw identifiers tới một vault riêng, mã hóa từ đầu và giới hạn kênh; không tin rằng sink sẽ làm sạch sau.
- **HMAC với key version:** để có thể xoay secret và tính toán correlation theo quy định; HMAC pseudonymization không xóa nghĩa vụ bảo vệ dữ liệu cá nhân.
- **Phân biệt actor verified/asserted:** login failure có thể dùng username giả; không tuyên bố nạn nhân đã thao tác.
- **Chống log forging:** kiểm newline/control characters, truncate correlation IDs, cố định eventType/reason enums, dùng structured logging.
- **Không serialize exception:** `AuthenticationException.getMessage()` và stack trace có thể chứa provider URL, account hint hoặc dữ liệu từ custom provider.
- **Phân quyền audit sink:** ghi chỉ cho service identity, đọc bởi nhóm được cấp quyền, bất biến/tamper-evident nếu yêu cầu, retention/xóa theo chính sách.
- **Không dùng PII làm metric labels:** username, email, IP, token và actorRef high-cardinality cũng không phù hợp làm tags Prometheus.
- **Bảo vệ backup/exports:** bảo mật bảng audit, broker topics, archive, BI exports và tracing; điểm yếu có thể nằm ở hệ thống hậu xử lý chứ không ở source app.

## 18. Đo hiệu năng: có thật đã tách khỏi login path?

Đừng chỉ đo trung bình (average). Cần so sánh:

| Chỉ số | Khi ghi trực tiếp trên request | Khi tách qua queue |
| --- | --- | --- |
| Login p50/p95/p99 | Tăng khi sink audit chậm | Thường không phụ thuộc trực tiếp network sink |
| Audit backlog | Không có hàng đợi rõ, request tự chờ | Quan sát queue depth và event age |
| Thời gian từ login đến audit visible | Thường ngay sau I/O | Trễ có kiểm soát, cần SLO |
| Sự cố sink | Login có thể timeout/throw | Queue tăng, overflow hoặc durable backpressure |
| Khả năng mất dữ liệu | Tùy giao dịch/ack | In-memory queue có thể mất khi crash |
| Dữ liệu nhạy cảm lan truyền | Dễ dump Authentication trực tiếp | Snapshot allowlist giảm bề mặt rò rỉ |
| Hành vi khi 1000 failures/giây | Có thể cạn thread/connection | Có nguy cơ đầy queue, cần limits và alert |

Thiết kế load test:

1. Đo baseline login ở tải bình thường và peak khi audit sink ổn định.
2. Cố ý làm sink delay 200 ms, 2 s, 10 s; đo response p99 và hàng đợi.
3. Tăng failed logins qua nhiều account để đánh giá khuếch đại từ attacker.
4. Giả lập queue full, crash consumer, restart app và broker/DB outage.
5. Đối chiếu số events tạo/queued/persisted/dropped, lưu ý duplicates/retries.
6. Kiểm thread count, heap, GC, connection pools, scheduler drift, tail latency và sự cố logging.
7. Với durable outbox, đo thời gian commit nhỏ và relay lag; chứng minh consistency/dedup thay vì chỉ latency.

**Không tuyên bố “không tăng latency” tuyệt đối.** Snapshot, HMAC và `queue.offer` vẫn tốn CPU/memory nhỏ; HMAC secret manager/network lookup nếu làm trong từng listener sẽ phá mục tiêu. Secret nên được cấp/cached an toàn ở startup, không fetch network trên mỗi authentication event.

## 19. Các lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Ghi DB/HTTP ngay trong `@EventListener` | Login chậm, lỗi sink làm gián đoạn auth | Snapshot + queue/broker, hoặc durable short handoff theo policy |
| Log `Authentication.toString()` | Có thể lộ principal, credential/details | DTO allowlist, HMAC/redact tại nguồn |
| `@Async` nhận nguyên authentication event | Sensitive object sống lâu trong executor queue | Tạo SafeAuditEvent trước, async DTO |
| Executor queue vô hạn | Memory growth/OOM khi login bị spam | Bounded queue, monitoring và rejection policy |
| Dùng `CallerRunsPolicy` nhưng nghĩ I/O luôn async | Khi đầy chạy trên caller, tăng p99 | Chọn rejection hợp đồng và test overload |
| Dùng `DiscardPolicy` cho audit bắt buộc | Mất sự kiện mà không báo | Durable store + ack/alert |
| `queue.poll()` rồi ghi DB fail | Record mất sau khi đã rời queue | Retry/ack/durable consumer tùy yêu cầu |
| Coi `@Async` là durable | Process crash mất queue | Outbox hoặc durable broker |
| Không có eventId | Retry tạo duplicate audit | UUID nguồn, idempotent consumer |
| Đếm cùng login hai success events | Audit phóng đại và alerts sai | Chọn source event và idempotency |
| Bỏ publisher khi tự tạo `ProviderManager` | Listener không nhận event | Cấu hình `AuthenticationEventPublisher` đúng |
| Listener ném exception không bắt | Có thể ảnh hưởng authentication/request | Bounded, safe capture; error policy rõ |
| Truyền `SecurityContext` sang thread nền | Lifecycle/threadlocal mismatch, rò principal | Snapshot field tối thiểu |
| Tin failed username là verified actor | Gán hoạt động attacker cho nạn nhân | ASSERTED vs VERIFIED |
| Thêm raw IP/header vào mọi audit event | Rò PII/credential, IP spoof | Trusted proxy, HMAC/retention, allowlist |
| Chỉ dùng `@TransactionalEventListener` | Không tự bền qua crash/không transaction | Ghi outbox row đồng transaction phù hợp |
| Mất SIEM event mà không có metric | Điều tra sai, báo cáo audit thiếu | Lag/overflow/dropped/failed-writes alerts |
| Đẩy rate limiter/authorization sang async | Request được cho qua dù cần kiểm tức thời | Giữ security decision trên synchronous path |
| Email alert cho từng failed login | Attacker gây mail flood và độ trễ | Aggregation, queue, quotas, cooldown |
| Không kiểm việc audit logging rò secrets qua test | Lộ dữ liệu khi đổi code/provider | Regression tests kiểm field schema/log contents |

## 20. Bài tập tự thực hành

1. Sửa phản ví dụ mục 3: listener chỉ tạo DTO `SafeAuditEvent` với event type, HMAC account và timestamp, sau đó enqueue. Giải thích tại sao không truyền `Authentication` hoặc `Exception`.
2. Chạy `BoundedAuditDemo.java`, đổi capacity thành 1. Dự đoán và đối chiếu số event accepted, rejected, thứ tự consumer nhận được.
3. Với ví dụ Boot 3, tạo một fake sink trì hoãn 3 giây. Dùng test tải đo login p99 trong hai trường hợp ghi sink trực tiếp trên `@EventListener` và ghi bằng `AuditDrain`; kiểm queue depth/overflow.
4. Viết unit test failure với credential chứa một chuỗi bí mật rõ ràng. Assert mọi serialized SafeAuditRecord không chứa chuỗi đó, raw username hoặc exception message.
5. Dùng `AuthenticationSuccessEvent` và `InteractiveAuthenticationSuccessEvent` trong cùng ứng dụng. Chỉ rõ khi nào đó là hai events cho một login, lập chiến lược không double-count.
6. Thiết kế durable audit cho thao tác phê duyệt thanh toán: event ID, outbox row trong transaction, relay, ack, retry, dedupe, retention và điều kiện fail closed.
7. Với một custom `ProviderManager`, xác minh publisher đã được cài. Tạo custom authentication exception và phân tích exact exception mapping.
8. Mô phỏng HMAC secret rotation, so sánh actorRef cùng username trước/sau rotation; đề xuất key version và xử lý historical joins theo chính sách.
9. Mô phỏng toàn bộ audit sink không sẵn sàng trong 10 phút: best-effort telemetry có thể mất bao nhiêu, durable outbox cần bao nhiêu dung lượng, app có thể vẫn login không?
10. Thiết kế security log/metrics sao cho phát hiện credential stuffing mà không lưu full username/IP hoặc làm lộ source tokens qua MDC.

## 21. Tổng kết

- Authentication events của Spring Security là nguồn tiện lợi cho audit, nhưng **listener mặc định đồng bộ** và có thể mang objects nhạy cảm.
- Giữ các bước **xác thực, phân quyền, rate limit và policy bắt buộc** trong đường ra quyết định; đưa I/O kiểm toán/telemetry ra worker sau khi đã tạo bản ghi an toàn.
- **Snapshot sớm, tối thiểu, immutable**: tránh `Authentication`/request/exception raw, ưu tiên HMAC/correlation ID/whitelisted enums, phân biệt asserted với verified principal.
- **Bounded queue + nonblocking offer** giúp bảo vệ latency, nhưng có khả năng mất dữ liệu khi đầy/crash. Phải đo overflow và nêu rõ best-effort.
- **@Async không phải durable**; nó cần executor/rejection/error handler/context policy. Không bật async toàn bộ event multicaster bừa bãi.
- Audit bắt buộc cần **durable handoff/outbox/broker ack**, retry/idempotency; muốn fail closed có thể phải chấp nhận chi phí lưu bền trên đường request.
- Đo đồng thời **p99 latency, event loss, lag, false duplicates, schema privacy** và kiểm thử failure modes. Một pipeline nhanh mà bí mật lọt vào log hoặc audit bị mất âm thầm vẫn là pipeline không an toàn.

**Tài liệu chính thức:**

- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — ProviderManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Framework 6.2 — Application Events và Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Task Execution, @Async và @Scheduled](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework — Observability và event listeners](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)