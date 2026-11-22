# Che dữ liệu cá nhân, token và thuộc tính nhạy cảm trong log

> **Ngữ cảnh:** Spring Security – authorization, nhóm **Sự kiện và audit**. Bài này giải thích cách thiết kế log phục vụ điều tra và quan sát quyết định phân quyền nhưng không làm lộ dữ liệu cá nhân, thông tin xác thực hay thuộc tính nhạy cảm. Ví dụ thực hành dùng **Java 17, Spring Boot 3.5.6, Spring Security 6.5.x (Servlet/Spring MVC)** và SLF4J/Logback.

## 1. Tại sao log bảo mật cũng có thể trở thành lỗ hổng?

Ứng dụng cần trả lời những câu hỏi vận hành như “Tại sao tài khoản này bị từ chối truy cập báo cáo?” hoặc “Có tăng đột biến quyết định phân quyền `DENIED` không?”. Nếu ghi thẳng request, đối tượng `Authentication` hoặc exception vào log, hệ thống quan sát có thể vô tình giữ lại:

- `Authorization: Bearer eyJ...` — access token có thể còn hiệu lực; cả JWT header/payload và chữ ký không nên xuất hiện trong log.
- `Authorization: Basic ...` — chuỗi Base64 chứa username/password; Base64 **không phải mã hóa bí mật**.
- `Cookie`, `Set-Cookie`, `JSESSIONID`, refresh token, session ID, API key, mã OAuth authorization code, mật khẩu, OTP, mã khôi phục.
- Họ tên, email, điện thoại, địa chỉ, định danh cá nhân, tài chính/sức khỏe, nội dung hồ sơ hoặc thuộc tính quyền nhạy cảm.
- Query string như `?token=...`, path có customer ID/email, HTTP body, multipart upload, response body, stack trace kèm dữ liệu đầu vào.
- `Authentication.getCredentials()`, `SecurityContext`, `Principal`, `Jwt`, `OAuth2AuthenticationToken`, full `HttpServletRequest` hoặc đối tượng nghiệp vụ được chuyển thành chuỗi bằng `toString()`.

Log thường được sao chép sang stdout của container, file, hệ thống tập trung, APM/trace, dashboard, cảnh báo, ticket hoặc công cụ hỗ trợ. Một bí mật đã đi vào log có thể tồn tại trên nhiều bản sao, được nhiều người đọc và còn sau khi request kết thúc.

**Nguyên tắc ưu tiên:** Thu thập đúng *sự kiện cần điều tra* với tập trường được cho phép ngay tại nơi tạo log. **Không đưa dữ liệu nhạy cảm vào pipeline rồi hy vọng bộ lọc cuối cùng sẽ che hết.** “Masking” là biện pháp bổ sung; thiết kế **data minimization + allowlist** mới là lớp bảo vệ chính.

## 2. Phân biệt các kỹ thuật bảo vệ

| Kỹ thuật | Ví dụ | Khi nào phù hợp | Giới hạn |
|---|---|---|---|
| **Không ghi (omit)** | Không tạo trường `Authorization`, `Cookie`, email, body | Mặc định cho secret và dữ liệu không cần điều tra | Không thể truy vấn dữ liệu đã chủ động bỏ |
| **Redaction** (loại bỏ giá trị) | `access_token=[REDACTED]` | Cần biết *trường đã hiện diện* mà không cần giá trị | Phải kiểm tra cả các bản sao/alias của trường |
| **Masking** (che một phần) | `m***@example.com` | Chỉ khi có căn cứ nghiệp vụ và quyền xử lý phù hợp | Phần còn lại vẫn có thể là **dữ liệu cá nhân**; không dùng cho token hoặc mật khẩu |
| **Pseudonymization có khóa** | `actor_ref=HMAC(k, stableId)` | Cần nối các event cùng chủ thể mà không ghi ID gốc | Vẫn có thể là dữ liệu liên quan cá nhân; khóa/rotation/khả năng liên kết phải quản lý |
| **Hash thường** | `SHA-256(email)` | Không nên dùng mặc định cho email/điện thoại | Dữ liệu có entropy thấp dễ bị dò bằng từ điển |
| **Truncation** | Giới hạn 200 ký tự của một trường | Chặn log injection và log quá lớn | Không bảo mật: 200 ký tự đầu vẫn có thể là nguyên token |
| **Mã hóa tại nơi lưu** | Encrypted log archive | Bảo vệ dữ liệu lưu trữ/truyền dẫn | Không xóa việc lộ secret cho người có quyền đọc log |

Với **password, access token, refresh token, OTP, session ID, private key**, quy tắc thực hành là **không log giá trị**, kể cả vài ký tự đầu/cuối. Nếu cần một nhãn chẩn đoán, chỉ ghi một trạng thái hữu hạn như `credential_present=true` khi đã có lý do chính đáng; thường không cần cả trạng thái này.

Mask email như `m***@example.com` có thể vẫn nhận diện chủ thể qua domain, ngữ cảnh và các log khác. Không coi dữ liệu đã mask là tự động “ẩn danh”.

## 3. Xác định trường nào được phép ghi trong authorization audit

Đề xuất một sự kiện **từ chối phân quyền** có schema nhỏ, ổn định:

```json
{
  "event_type": "AUTHORIZATION_DENIED",
  "outcome": "DENIED",
  "resource": "REPORT_READ",
  "event_id": "6d1d6d4e-bc78-4759-82c1-4ba3e417f5bf"
}
```

Đây là **schema minh họa do ứng dụng xây dựng**; Spring Security không tự sinh JSON này. Timestamp và service name thường do logging system/collector thêm vào. `event_id` là mã ngẫu nhiên **cho một event**, không phải session ID và cũng không thay thế trace ID.

| Trường | Cho vào log? | Cách lấy an toàn |
|---|---|---|
| `event_type`, `outcome` | Có | Hằng số do code định nghĩa, ví dụ `AUTHORIZATION_DENIED` / `DENIED` |
| `resource` hoặc `action` | Có | Tên logic từ enum/allowlist như `REPORT_READ`; **không dùng raw URL** |
| `event_id` | Có | `UUID.randomUUID()` mới cho từng sự kiện |
| `request_id`/`trace_id` | Có nếu tin cậy | ID do server/tracing tạo hoặc đã validate; không dùng tùy ý header do client gửi |
| `actor_ref` | Chỉ khi cần cho audit | ID thay thế có kiểm soát hoặc keyed HMAC; xem phần 8 |
| `http_method` | Có khi cần | Chỉ chấp nhận tập giá trị hữu hạn như GET/POST; không nối chuỗi lạ chưa kiểm tra |
| `request_uri`, `query_string` | Không ghi thẳng | Chuyển thành tên route logic, loại bỏ query và định danh trong path |
| `Authorization`, `Cookie`, `Set-Cookie`, `X-API-Key` | Không | Bỏ toàn bộ trường/value |
| `Authentication`, `Principal`, `Jwt`, `SecurityContext` | Không ghi dạng object | Trích xuất các trường đã được phê duyệt, không `toString()` |
| `exception.getMessage()`, stack trace, `request.getParameterMap()` | Không mặc định | Chỉ dùng mã lỗi cố định, phân loại lỗi; bật chi tiết khi đã đánh giá rủi ro và có kiểm soát |

Ví dụ một request thực tế:

```http
GET /api/reports/customer-783?email=mai@example.com HTTP/1.1
Authorization: Bearer eyJhbGciOi...
Cookie: SESSION=opaque-secret
```

Dòng log **không nên** chép URI, query hoặc các header trên. Dòng log có ích và an toàn hơn:

```text
security_event=AUTHORIZATION_DENIED outcome=DENIED resource=REPORT_READ event_id=6d1d6d4e-bc78-4759-82c1-4ba3e417f5bf
```

ID báo cáo `customer-783` và email **không xuất hiện**. Vẫn biết có một lần kiểm tra quyền đọc báo cáo bị từ chối.

## 4. Những cách ghi log sai cần tránh

### 4.1. Dùng `toString()` trên đối tượng chứa dữ liệu

**Sai:**

```java
log.warn("Denied: request={} authentication={}", request, authentication);
log.debug("JWT claims={}", jwt.getClaims());
log.error("Permission denied for payload={}", command);
```

Vì `toString()`/serializer của thư viện, model hoặc proxy có thể chứa nhiều trường hơn dự kiến, kể cả dữ liệu mới được thêm trong tương lai. Không thể kết luận là an toàn chỉ vì log từng chạy với dữ liệu thử nghiệm vô hại.

**An toàn hơn:**

```java
log.warn("security_event={} outcome={} resource={}",
        "AUTHORIZATION_DENIED", "DENIED", "REPORT_READ");
```

Ba giá trị trên được định nghĩa ở source và không chịu ảnh hưởng của request. Thực tế nên cung cấp helper/audit service duy nhất nhận enum hoặc record chuyên biệt, tránh mỗi controller tự tạo mẫu log riêng.

### 4.2. Ghi toàn bộ header, body và URL

**Sai:**

```java
log.info("uri={} query={} headers={}",
        request.getRequestURI(),
        request.getQueryString(),
        java.util.Collections.list(request.getHeaderNames()));
```

Đoạn sai này mới ghi *tên* header; việc đổi sang đọc cả *giá trị* sẽ làm lộ secret rõ hơn. Ngay cả URI hoặc tên header cũng có thể tiết lộ chi tiết triển khai và thông tin nhạy cảm. Không tạo filter ghi toàn bộ request/response trong production chỉ để debug 403.

**An toàn hơn:** ánh xạ URL sang mã tài nguyên cố định như `REPORT_READ`, dựa vào route/endpoint đã biết. Nếu cần đường dẫn cho đo lường, dùng **route template** kiểu `/api/reports/{reportId}` sau khi chắc chắn template lấy từ router đáng tin cậy; không dùng URI đã gắn ID.

### 4.3. Mask bằng regex cuối pipeline như biện pháp duy nhất

Thí dụ một regex bắt chuỗi `Bearer ...` có thể bỏ lọt token trong JSON body, URL encoding, log SQL, phần header bị đổi tên, object lồng nhau, exception hoặc định dạng logging mới. Regex che email cũng không bảo vệ số điện thoại, địa chỉ, thuộc tính sức khỏe hay PII trong token claims.

Regex có thể là **lớp phòng thủ thứ hai** trên sink, nhưng không thay thế allowlist tại nguồn, kiểm soát log level, kiểm thử các nguồn phát log và quản lý quyền đọc log.

### 4.4. Nghĩ rằng parameterized logging tự động che bí mật

SLF4J `log.info("token={}", token)` chỉ trì hoãn format/giảm chi phí tạo chuỗi trong một số tình huống. Nó **không mã hóa, không mask, không redaction**. Tương tự, structured JSON log chỉ giúp schema/escape hợp lệ, không tự quyết định trường nào nhạy cảm.

## 5. Dòng xử lý phù hợp trong Spring Security

Một authorization audit tốt nên nằm ở điểm tạo **sự kiện phân quyền**, rồi chuyển event sang schema đã phê duyệt:

```text
HTTP request (có thể chứa token, PII, payload)
       |
       v
Spring Security authentication / authorization
       |
       +--> AuthorizationManager quyết định DENIED
       |
       +--> AuthorizationEventPublisher
       |        |
       |        +--> SpringAuthorizationEventPublisher
       |                 |
       |                 +--> AuthorizationDeniedEvent
       |                            |
       |                            +--> SafeAuditListener
       |                                     |
       |                                     +--> Xác định resource từ allowlist
       |                                     +--> Tạo event_id ngẫu nhiên
       |                                     +--> Log các trường cố định
       |
       +--> Xử lý HTTP 401 / 403 độc lập
```

Trên Spring Security Servlet, đăng ký bean `AuthorizationEventPublisher` thích hợp để nhận `AuthorizationDeniedEvent` từ các điểm kiểm tra dùng publisher. Mặc định `SpringAuthorizationEventPublisher` tập trung vào **denied** events; không nên hiểu rằng mọi lần truy cập thành công đều có event audit. Một `AccessDeniedHandler` dùng để tạo phản hồi 403; nó không phải nơi tốt nhất để duy trì một schema authorization audit chung.

**Cảnh báo phạm vi:** Không phải mọi HTTP 403 đều đi qua `AuthorizationEventPublisher` (ví dụ lỗi CSRF hoặc custom filter tự chặn). Một request có thể có nhiều authorization checks và tạo nhiều events. Nếu chính sách audit cần bao phủ mọi lệnh nghiệp vụ, phải bổ sung điểm audit nghiệp vụ tương ứng.

## 6. Ví dụ Spring Boot 3.5.6: chỉ log metadata an toàn

Ứng dụng minh họa dùng HTTP Basic để tạo người đã xác thực với role khác nhau. Các mật khẩu `{noop}` chỉ dành cho demo; không dùng trong môi trường thật. Listener **cố ý không log username, token, header, URI hay request body**.

### 6.1. Cấu trúc dự án

```text
safe-authorization-logs/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/safelogs/
│   ├── SafeLogsApplication.java
│   ├── SecurityConfig.java
│   ├── ReportController.java
│   └── SafeAuthorizationAuditListener.java
└── src/test/java/com/example/safelogs/
    └── SafeAuthorizationAuditTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>safe-authorization-logs</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

`src/main/resources/application.properties`:

```properties
spring.application.name=safe-authorization-logs
logging.level.root=INFO
logging.level.org.springframework.security=INFO
logging.level.org.springframework.web=INFO
spring.mvc.log-request-details=false
```

Thiết lập trên giảm mức chi tiết dễ rủi ro từ log framework mặc định. **Đây không phải bộ lọc chống rò rỉ toàn cục**: logger ứng dụng, JDBC/ORM, HTTP client, reverse proxy, tracing và agent APM có chính sách độc lập. Không đặt `logging.level.org.springframework.security=TRACE` hoặc bật request-detail/body logging ở production chỉ để chẩn đoán một 403.

### 6.2. Main application

`src/main/java/com/example/safelogs/SafeLogsApplication.java`:

```java
package com.example.safelogs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeLogsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeLogsApplication.class, args);
    }
}
```

### 6.3. Cấu hình phân quyền và event publisher

`src/main/java/com/example/safelogs/SecurityConfig.java`:

```java
package com.example.safelogs;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher events) {
        return new SpringAuthorizationEventPublisher(events);
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/reports/**").hasRole("AUDITOR")
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        var analyst = User.withUsername("analyst")
                .password("{noop}analyst123")
                .roles("ANALYST")
                .build();
        var auditor = User.withUsername("auditor")
                .password("{noop}auditor123")
                .roles("AUDITOR")
                .build();
        return new InMemoryUserDetailsManager(analyst, auditor);
    }
}
```

`hasRole("AUDITOR")` yêu cầu authority `ROLE_AUDITOR`; `roles("AUDITOR")` tạo authority đó. Người `analyst` đã xác thực nhưng thiếu role, nên nhận 403. Bean `AuthorizationEventPublisher` cho phép cơ chế authorization phát event vào Spring event infrastructure; việc không đưa giá trị request vào logger là trách nhiệm **của listener**.

### 6.4. Controller

`src/main/java/com/example/safelogs/ReportController.java`:

```java
package com.example.safelogs;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    @GetMapping("/api/reports/{reportId}")
    public Map<String, String> report(@PathVariable String reportId) {
        return Map.of("status", "ready");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile() {
        return Map.of("status", "visible");
    }
}
```

`reportId` có thể là định danh khách hàng; controller chỉ nhận nó để minh họa rằng **path variable có tồn tại nhưng sẽ không bị đưa vào audit log**. Rule tại security filter chặn trước khi gọi method nếu thiếu quyền.

### 6.5. Listener chỉ ghi hằng số và mã sự kiện

`src/main/java/com/example/safelogs/SafeAuthorizationAuditListener.java`:

```java
package com.example.safelogs;

import jakarta.servlet.http.HttpServletRequest;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.stereotype.Component;

@Component
public class SafeAuthorizationAuditListener {
    private static final Logger log =
            LoggerFactory.getLogger(SafeAuthorizationAuditListener.class);

    @EventListener
    public void onDenied(AuthorizationDeniedEvent<?> event) {
        String resource = resourceCategory(event.getObject());
        String eventId = UUID.randomUUID().toString();

        log.warn("security_event=AUTHORIZATION_DENIED outcome=DENIED " +
                 "resource={} event_id={}", resource, eventId);
    }

    private String resourceCategory(Object securedObject) {
        if (securedObject instanceof HttpServletRequest request) {
            // Chỉ đọc URI để PHÂN LOẠI trong bộ nhớ, tuyệt đối không log URI.
            String relativePath = request.getRequestURI()
                    .substring(request.getContextPath().length());

            if ("GET".equals(request.getMethod())
                    && relativePath.startsWith("/api/reports/")) {
                return "REPORT_READ";
            }
        }
        return "OTHER_PROTECTED_RESOURCE";
    }
}
```

**Điểm cần hiểu khi đọc code:**

1. `@EventListener` nhận `AuthorizationDeniedEvent<?>`. Giá trị của `event.getObject()` **không phải lúc nào cũng là Servlet request**: với method security hoặc custom publisher, đó có thể là đối tượng khác. Mọi trường hợp không khớp nhận nhãn cố định `OTHER_PROTECTED_RESOURCE`.
2. Phương thức `resourceCategory` dùng URI trong **bộ nhớ** để phân loại tài nguyên, nhưng không xuất URI, ID, query hoặc header. Với ứng dụng có nhiều route và context path, nên ánh xạ bằng route metadata chính thức hoặc enum action từ domain, rồi kiểm thử đúng các mapping.
3. Log chỉ nhận hai biến do ứng dụng kiểm soát: `resource` từ tập giá trị hữu hạn và `eventId` ngẫu nhiên. Không có dữ liệu cá nhân hoặc credential từ request.
4. `eventId` được tạo mỗi event; nó **không** phải idempotency key, không phải session ID. Muốn nối nhiều event của cùng một request, cần request/correlation ID do server tạo và quản lý vòng đời rõ ràng.
5. Handler không lưu tham chiếu tới `HttpServletRequest`, `Authentication` hoặc token để xử lý nền. Không gọi `toString()` trên event hoặc exception.

Ví dụ log (UUID thực tế khác mỗi lần):

```text
security_event=AUTHORIZATION_DENIED outcome=DENIED resource=REPORT_READ event_id=6d1d6d4e-bc78-4759-82c1-4ba3e417f5bf
```

Một system logging có thể thêm timestamp, thread và logger name trước dòng trên. Mục tiêu của code là **không có** `reportId`, email, Bearer token hay cookie trong message do listener tạo.

### 6.6. Khởi động và quan sát

Tại thư mục chứa `pom.xml`, dùng JDK 17+ và Maven 3.9+:

```bash
mvn spring-boot:run
```

Ở một terminal khác, thử:

```bash
# Analyst thiếu ROLE_AUDITOR. HTTP 403 + audit log an toàn.
curl -i -u analyst:analyst123 \
  'http://localhost:8080/api/reports/customer-783?email=mai%40example.com'

# Auditor có quyền. HTTP 200, không có denied audit.
curl -i -u auditor:auditor123 \
  'http://localhost:8080/api/reports/customer-783?email=mai%40example.com'

# Chưa xác thực. HTTP Basic yêu cầu xác thực: thường 401.
curl -i 'http://localhost:8080/api/reports/customer-783'
```

Trên Windows PowerShell, dùng `curl.exe` nếu `curl` là alias. Shell Windows cũng có cách xuống dòng khác: có thể gộp từng lệnh thành một dòng, bỏ ký tự `\` xuống dòng của Bash.

Bảng trạng thái dự kiến:

| Lời gọi | HTTP | Log do listener |
|---|---|---|
| Analyst thiếu quyền đọc report | **403** | `AUTHORIZATION_DENIED` với `resource=REPORT_READ` |
| Auditor đủ quyền | **200** | Không phát denied log từ request kiểm tra thành công |
| Không có xác thực | Thường **401** với HTTP Basic | Không giả định chính xác số authorization events; phụ thuộc luồng authentication/authorization |

Lưu ý kết quả 403 và log là **hai luồng xử lý liên quan nhưng độc lập**. Một 403 khác nguồn, ví dụ CSRF, có thể không tạo event này.

## 7. Kiểm thử không rò rỉ secret và dữ liệu cá nhân

Test cần kiểm tra **một request thật đi qua filter chain**, rồi xem output log. Chỉ unit test utility mask chưa chứng minh ứng dụng không ghi dữ liệu nhạy cảm ở lớp khác.

`src/test/java/com/example/safelogs/SafeAuthorizationAuditTest.java`:

```java
package com.example.safelogs;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class SafeAuthorizationAuditTest {
    @Autowired
    MockMvc mvc;

    @Test
    void deniedRequestLogsMetadataWithoutSecrets(CapturedOutput output)
            throws Exception {
        String jwtLike = "eyJhbGciOiJIUzI1NiJ9.sample.signature";
        String privateEmail = "mai@example.com";
        String privateReport = "customer-783";
        String privateCookie = "SESSION=secret-session-value";

        mvc.perform(get("/api/reports/" + privateReport)
                .with(user("analyst").roles("ANALYST"))
                .queryParam("email", privateEmail)
                .header("Authorization", "Bearer " + jwtLike)
                .header("Cookie", privateCookie))
            .andExpect(status().isForbidden());

        String logged = output.getAll();
        assertThat(logged)
            .contains("security_event=AUTHORIZATION_DENIED")
            .contains("resource=REPORT_READ")
            .doesNotContain(jwtLike)
            .doesNotContain(privateEmail)
            .doesNotContain(privateReport)
            .doesNotContain(privateCookie)
            .doesNotContain("secret-session-value");
    }

    @Test
    void authorizedUserCanReadWithoutDeniedLog(CapturedOutput output)
            throws Exception {
        mvc.perform(get("/api/reports/customer-783")
                .with(user("auditor").roles("AUDITOR")))
            .andExpect(status().isOk());

        assertThat(output.getAll())
            .doesNotContain("security_event=AUTHORIZATION_DENIED");
    }

    @Test
    void unauthenticatedRequestIsChallenged() throws Exception {
        mvc.perform(get("/api/reports/customer-783"))
            .andExpect(status().isUnauthorized());
    }
}
```

Chạy:

```bash
mvn test
```

**Giải thích kiểm thử:**

- `with(user("analyst").roles("ANALYST"))` gắn authentication cho MockMvc mà không gửi mật khẩu demo; header `Authorization: Bearer ...` được thêm như dữ liệu nhạy cảm *để kiểm tra rằng listener không ghi nó*. Cấu hình này dùng HTTP Basic, không bật OAuth2 Resource Server nên Bearer header không phải cơ chế xác thực của demo.
- Test denied xác nhận 403, marker audit, tên resource logic và **không có** token, email, path variable hoặc cookie trong log đã capture.
- Test allowed xác nhận 200 và không có marker **denied** trong request thành công của ví dụ.
- `CapturedOutput` là kết quả console/output của tiến trình test. Đây là **kiểm thử cần thiết nhưng chưa đủ** để tuyên bố toàn hệ thống không rò rỉ: proxy, ingress, HTTP client, APM, SQL logger, sidecar và external collector có thể còn dữ liệu ngoài capture.
- Assertion `doesNotContain(...)` chỉ bảo vệ các mẫu kiểm thử cụ thể. Cần mở rộng bộ dữ liệu mẫu với email/ID quốc tế, nested JSON, token ở nhiều vị trí, newline injection, URL encoding và các nguồn log thực tế.

`@SpringBootTest` + `@AutoConfigureMockMvc` dùng security filter chain của ứng dụng. Nếu chỉ tạo `MockMvcBuilders.standaloneSetup(...)` mà không gắn security filters, test không kiểm chứng được quyết định phân quyền.

## 8. Khi audit bắt buộc phải liên kết theo người dùng

Bỏ hẳn username/ID trong demo là lựa chọn an toàn để dạy cơ chế, nhưng audit nghiệp vụ có thể cần truy vết hành động theo tài khoản. Khi đó hãy **xác định mục đích, quyền xử lý và thời hạn lưu** trước khi thêm định danh.

Một phương án là **pseudonymization có khóa** trên **mã người dùng nội bộ ổn định**:

```text
stableInternalUserId
    |
    +--> HMAC-SHA256(secretKey, "audit:v1:" + stableInternalUserId)
                |
                +--> actor_ref = digest đã rút gọn đủ dài (theo chính sách)
```

- Sử dụng khóa bí mật chất lượng cao được quản lý trong secret manager/KMS; không ghi khóa vào source, config commit, exception hoặc log.
- Dùng **HMAC**, không dùng `SHA-256(email)` đơn thuần vì email/số điện thoại dễ bị dò.
- Phân tách mục đích bằng tiền tố domain như `audit:v1:`; định nghĩa rõ phiên bản khóa, vòng đời rotation và hệ quả khi đổi khóa đối với việc nối các event.
- Xem xét tình huống điều tra cần giải quyết ngược mã thay thế về tài khoản gốc: chỉ hệ thống/nhân sự được phép thực hiện; lưu mapping hoặc quy trình kiểm soát riêng nếu thật sự cần.
- Mã giả thay thế có thể vẫn là **dữ liệu cá nhân** theo ngữ cảnh/quy định áp dụng. Không được gọi đó là “anonymization” tuyệt đối.

Trong Java, primitive phù hợp là `javax.crypto.Mac` với thuật toán `HmacSHA256` và `javax.crypto.spec.SecretKeySpec`. Ví dụ minh họa cách gọi (không phải một chương trình độc lập; `keyBytes` phải được cấp an toàn từ KMS/secret store):

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class AuditActorRef {
    private AuditActorRef() {}

    public static String of(String internalUserId, byte[] keyBytes) {
        if (internalUserId == null || internalUserId.isBlank()) {
            throw new IllegalArgumentException("Missing internal user ID");
        }
        if (keyBytes == null || keyBytes.length < 32) {
            throw new IllegalArgumentException("HMAC key must be at least 32 bytes");
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(keyBytes, "HmacSHA256"));
            byte[] digest = mac.doFinal(
                ("audit:v1:" + internalUserId).getBytes(StandardCharsets.UTF_8));
            // 128 bit từ HMAC, đủ dài cho định danh audit ví dụ này.
            return HexFormat.of().formatHex(digest, 0, 16);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("Audit pseudonymization unavailable", e);
        }
    }
}
```

Không log `internalUserId` và `keyBytes`, không đưa đối tượng `Authentication` nguyên vẹn qua thread khác. Giá trị HMAC được rút gọn **để giảm chiều dài**, không vì rút gọn làm nó “vô danh”. Quyết định độ dài cuối cùng phụ thuộc số lượng chủ thể, collision budget và yêu cầu liên kết event. Phải xác định thứ tự rotate/rekey trước khi đổi khóa.

## 9. Phòng vệ nhiều lớp ngoài listener

### 9.1. Logging framework và cấu hình chi tiết

- **Ứng dụng:** audit helper dùng allowlist, enum/mã lỗi cố định. Không gọi `log.*("{}", request)` hoặc log nguyên map response/claims.
- **Spring MVC & Security:** kiểm soát `logging.level.*`, tránh `TRACE`/DEBUG rộng trong production; `spring.mvc.log-request-details=false` chỉ kiểm soát một phần logging MVC, **không bao trùm toàn bộ logger**.
- **HTTP client/server:** request/response logging ở Feign, RestTemplate, WebClient, gateway, reverse proxy thường có cấu hình riêng. Kiểm tra cơ chế ẩn `Authorization`, cookie, body, query ở từng nơi.
- **ORM/SQL:** SQL bind parameter có thể chứa email, token, payload dù text SQL không có. Kiểm tra logger của Hibernate/JDBC/tracing.
- **Log encoder/appender:** dùng structured log có schema ổn định, cấu hình bộ lọc bổ sung cho trường bí mật và escape các ký tự điều khiển.
- **APM/traces/error trackers:** spans, baggage, exception breadcrumbs và crash dumps cũng là telemetry; không gắn PII, credential hoặc raw request vào attributes.

Chỉ đổi `logger` sang JSON **không tự loại bỏ sensitive fields**. Kể cả khi output đã che, collector có thể giữ nguyên bản gốc nếu redaction diễn ra sau bước ingest. Chọn điểm che **sớm nhất có thể**.

### 9.2. MDC và correlation ID

SLF4J MDC là bản đồ giá trị theo ngữ cảnh thread dùng để bổ sung log. Có thể đặt một `requestId` do server tạo; **không đặt email, username, JWT hoặc session ID vào MDC** vì mọi log của thread có thể mang chúng. Với Servlet, cần dọn MDC trong `finally` sau request:

```java
// Minh họa phần thân filter/interceptor, không phải class hoàn chỉnh.
String requestId = java.util.UUID.randomUUID().toString();
org.slf4j.MDC.put("requestId", requestId);
try {
    filterChain.doFilter(request, response);
} finally {
    org.slf4j.MDC.remove("requestId");
}
```

Trong async execution, virtual threads, thread pools hoặc reactive context, MDC không tự động giữ đúng ngữ cảnh; dùng cơ chế propagation được framework hỗ trợ, chỉ truyền các giá trị đã phê duyệt và dọn khi xong. Không nhận nguyên `X-Request-ID` do client cấp rồi log mà thiếu validation/giới hạn độ dài; header do client kiểm soát có thể chứa newline, dữ liệu cá nhân hoặc chuỗi tấn công.

### 9.3. Chống log injection và dữ liệu không tin cậy

Nếu không thể tránh một trường text do người dùng cung cấp, phải có allowlist, giới hạn độ dài, normalize/escape `\r`, `\n`, tab và ký tự điều khiển phù hợp với log format; nếu không, một giá trị có thể tạo dòng log giả mạo. Structured logging có thể hỗ trợ escaping, nhưng vẫn cần schema và limit size. Không in chuỗi đã được che một phần mà vẫn chứa mã OTP, secret trong mảnh còn lại.

**Không dùng `trim` hay `substring` để “mask” secret**; truncation chỉ giới hạn kích thước, không biến dữ liệu nhạy cảm thành an toàn.

## 10. Lưu trữ, truy cập và quy trình xử lý sự cố

Dù log đã được giảm dữ liệu, sự kiện an ninh vẫn nhạy cảm vì chúng mô tả hoạt động và điểm kiểm soát quyền.

1. **Quyền đọc/ghi tách biệt:** hạn chế người xem log, audit mọi lần truy cập, không cho ứng dụng sửa lịch sử tùy tiện; ưu tiên collection chỉ ghi khi phù hợp.
2. **Retention rõ ràng:** thời gian giữ phụ thuộc mục tiêu điều tra và yêu cầu pháp lý/kinh doanh áp dụng. Giảm bản sao không kiểm soát (agent buffer, archive, backup, export).
3. **Truyền/lưu bảo vệ:** TLS cho luồng telemetry; mã hóa khi lưu; quản lý khóa và quyền truy cập riêng.
4. **Độ tin cậy và tải:** listener đồng bộ làm tăng latency; exception trong listener có thể ảnh hưởng request. Phân tách sink/queue với chính sách lỗi và backpressure phù hợp. Nếu audit bắt buộc bền vững, Spring application event trong process **không** đủ làm chứng cứ đã lưu thành công.
5. **Incident có token bị lộ vào log:** xem token như đã bị lộ; thực hiện revoke/rotate theo loại credential, giới hạn phạm vi truy cập log, điều tra downstream exports và xử lý dữ liệu theo quy trình sự cố được phê duyệt. Xóa một dòng khỏi dashboard **không** đồng nghĩa đã xóa khỏi mọi archive.
6. **Kiểm tra định kỳ:** rà soát rule logging, secret scanner cho telemetry ở môi trường thử nghiệm, log query theo dữ liệu tổng hợp được phép; luôn tránh biến việc thử nghiệm thành nơi ghi thêm secret thật.

## 11. Tình huống phân tích trước – sau

**Tình huống A: API trả 403**

- Trước: `log.warn("Denied {}", request.getRequestURL())` ghi đường dẫn chứa ID cá nhân và có thể không phân biệt role.
- Sau: `event_type=AUTHORIZATION_DENIED resource=REPORT_READ outcome=DENIED`. Quyết định quyền được điều tra theo event ID; client vẫn nhận HTTP 403 từ Spring Security.

**Tình huống B: JWT hết hạn hoặc thiếu scope**

- Trước: `log.error("JWT error token={}", token)` tạo rủi ro chiếm quyền nếu token còn được dùng ở nơi khác.
- Sau: ghi `auth_error_code=INVALID_TOKEN` hoặc `INSUFFICIENT_SCOPE` từ tập mã cố định, có thể kèm correlation ID. Không log nguyên claims, bearer token hay exception message tự do. Cần phân biệt sự kiện **authentication** với **authorization** đúng nghĩa.

**Tình huống C: Muốn tìm toàn bộ event của một người**

- Trước: log email hoặc số điện thoại nguyên văn vào mọi dòng.
- Sau: chỉ thêm `actor_ref` khi cần và khi có chính sách rõ ràng; tạo từ ID nội bộ bằng HMAC có khóa. Tránh dùng IP/user-agent làm danh tính tuyệt đối vì chúng có thể thay đổi, chia sẻ hoặc thuộc dữ liệu cá nhân.

**Tình huống D: QA phát hiện secret trong HTTP client debug log**

- Trước: chỉ sửa listener authorization nhưng vẫn bật wire logging toàn body.
- Sau: tắt/sửa nguồn rò thực tế ở HTTP client, rà soát downstream, thêm canary test không dùng secret thật và kiểm soát cấu hình production.

## 12. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách sửa |
|---|---|---|
| Log che password nhưng vẫn thấy Bearer token | Redaction chỉ áp dụng trường `password` | Bỏ hoàn toàn auth header/token tại nguồn; audit bằng mã lỗi cố định |
| Regex mask email nhưng thấy PII trong JSON lồng nhau | Quét chuỗi không đủ hiểu schema/escaping | Allowlist field trước serialization; kiểm tra sink bổ sung |
| Hash email vẫn có thể bị đoán | Dùng hash không khóa với đầu vào ít khả năng | HMAC bằng secret và ID nội bộ khi có nhu cầu liên kết |
| Log có URI không chứa query nhưng vẫn lộ ID | Path variable là định danh cá nhân | Dùng route template/mã tài nguyên logic |
| JWT payload không được coi là secret | JWT payload Base64URL dễ decode, token vẫn có thể dùng để truy cập | Không log bất cứ phần nào của JWT, kể cả “chỉ claims” |
| Bật DEBUG/TRACE trong production rồi xuất hiện credential | Thư viện/framework khác log ngoài helper | Rà soát cấu hình mỗi thành phần, chặn wire/request body log |
| Một denied event xuất hiện hai lần | Nhiều check quyền hoặc dispatcher khác nhau | Gắn event ID/correlation và source; không mặc định 1 event = 1 request |
| Audit log thiếu actor nên không phục vụ điều tra | Data minimization quá mức so với yêu cầu | Bổ sung actor_ref có kiểm soát khi có mục đích và quyền truy cập |
| Correlation ID chứa newline hoặc data không tin cậy | Log trực tiếp header client gửi | Tạo ID server-side hoặc validate format/length |
| Test pass nhưng proxy vẫn ghi secret | Chỉ capture stdout trong ứng dụng | Kiểm tra gateway, ingress, APM, queue, collector và retention |

## 13. Checklist review trước khi phát hành

- [ ] Mọi log authorization/audit dùng **schema có allowlist**, không serialize thẳng request, response, SecurityContext, Principal hoặc exception.
- [ ] Không có password, token, cookie, session ID, key, OTP, OAuth code trong message, MDC, span attributes, appender hoặc export.
- [ ] Không ghi nguyên URL/query/path variable hoặc body có thể chứa dữ liệu cá nhân.
- [ ] Các nhãn `resource/action/outcome` đến từ enum/tập hữu hạn, có test cho unknown route.
- [ ] Nếu có `actor_ref`, mục đích, phương pháp HMAC, khóa, rotation, quyền đọc và retention đã được xác định.
- [ ] Kiểm thử ít nhất một request denied 403 có token/email/ID giả; xác nhận log đúng schema và không có chuỗi bí mật.
- [ ] Kiểm thử request allowed 200; tránh hiểu nhầm không có denied event là không có request.
- [ ] Có giới hạn log level/field size, chống CRLF injection, cleanup MDC và chính sách lỗi cho listener.
- [ ] Đã kiểm tra các nguồn ngoài ứng dụng: proxy, client, SQL, APM, traces và collector.
- [ ] Có phương án xử lý sự cố nếu secret đã từng bị ghi vào log.

## Tài liệu tham khảo

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu thường cần loại khỏi log, masking/sanitization, chống log injection và quản trị log.
- [Spring Security – Authorization Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/events.html): `AuthorizationEventPublisher`, `SpringAuthorizationEventPublisher` và `AuthorizationDeniedEvent`.
- [Spring Security – Servlet Authorization](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter` và quyết định quyền.
- [Spring Boot – Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html): logger levels, Logback, output và cấu hình Spring Boot.
- [Spring Boot – CapturedOutput/OutputCaptureExtension](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/system/OutputCaptureExtension.html): kiểm thử output log của ứng dụng.
