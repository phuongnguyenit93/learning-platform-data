# Xử lý sự cố bảo mật mà không ghi lộ dữ liệu hoặc mở quyền tạm thời

> **Ngữ cảnh:** Spring Security — fundamentals / Triển khai. Bài học hướng dẫn **điều tra và xử lý sự cố xác thực, phân quyền, CSRF, phiên đăng nhập và cấu hình bảo mật** mà **không ghi lộ mật khẩu, token, cookie, dữ liệu cá nhân hoặc khóa**, đồng thời **không tạm thời cho phép truy cập rộng hơn** chỉ để gỡ lỗi. Ví dụ sử dụng Java 17+, Spring Boot 3.5.0, Spring Security 6.x (Servlet), Maven, JUnit 5 và MockMvc.

## 1. Hai ranh giới không được phá khi đang có sự cố

Sự cố thường bắt đầu bằng một triệu chứng gấp gáp: người dùng hợp lệ nhận 401/403, login redirect vòng lặp, API bị chặn sau deploy, hoặc xuất hiện dấu hiệu request trái phép. Một cách “sửa nhanh” nguy hiểm là:

~~~java
// SAI: mở toàn bộ API chỉ để tìm nguyên nhân trả 403.
http.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll());
~~~

Hoặc bật cấu hình log quá rộng:

~~~properties
# KHÔNG dùng tùy tiện ở production.
logging.level.root=TRACE
~~~

Hai việc này có thể đồng thời tạo **sự cố thứ hai**: quyền truy cập dữ liệu bị mở và credentials/PII xuất hiện trong log tập trung, APM, hệ thống support hoặc artifacts CI.

**Hai nguyên tắc bắt buộc:**

1. **Không nới quyền vì cần debug.** Không đổi `authenticated()` thành `permitAll()`, không tắt role/ownership/tenant checks, không vô hiệu CSRF hoặc các filter bảo mật để có một response 200. Hãy điều tra ở môi trường/đường quan sát có kiểm soát, giữ nguyên nguyên tắc **deny by default** và **least privilege**.
2. **Không ghi dữ liệu nhạy cảm để lấy thêm ngữ cảnh.** Không dump raw `Authorization`, `Cookie`, `Set-Cookie`, password, OAuth2 code, API key, JWT, CSRF token, private key, nội dung hồ sơ khách hàng hoặc nguyên body HTTP. Ghi **sự kiện, mã lý do an toàn, route template/nhóm endpoint, trạng thái và correlation ID**.

Điều tra đúng là tăng **tín hiệu hữu ích** mà không tăng **quyền bị lộ**. Khi rủi ro cao, có thể phải *thu hẹp* truy cập, rollback bản phát hành hoặc cô lập service; không có lý do nghiệp vụ nào tự cấp phép “mở toàn bộ API trong vài phút”.

## 2. Trước tiên phân loại: lỗi chức năng hay sự cố an ninh?

| Hiện tượng | Có thể do | Tín hiệu cần đối chiếu | Tuyệt đối không làm |
|---|---|---|---|
| API trả **401** | Thiếu/sai credentials, token hết hạn, issuer/audience mismatch, mất session | Loại authentication, `WWW-Authenticate` nếu phù hợp, event auth failure, cookie-present **boolean** | Log raw Bearer/JSESSIONID/password |
| API trả **403** | Thiếu authority, sai role, CSRF token thiếu/sai, tenant/owner không được phép | Decision code, rule/method, CSRF reason phân loại, chủ thể đã xác thực? | Thay `hasRole` bằng `permitAll` |
| Đăng nhập xong lại anonymous | Cookie không gửi, session hết hạn, context không lưu | Cookie-present, session lookup hit/miss, context-loaded, node ID | Log toàn bộ session, tắt CSRF |
| Chỉ có lỗi qua proxy | Rewrite path, HTTPS/forwarded headers, CORS, context path | Route chuẩn hóa, request ID, node và proxy trace đã redacted | Tin `X-Forwarded-*` từ client Internet |
| Một user xem được đối tượng user khác | BOLA/IDOR, thiếu kiểm owner/tenant | Resource-policy decision và actor pseudonym, ID nội bộ đã kiểm soát | Để lỗi tồn tại rồi chỉ ẩn nút |
| Nhiều 401 liên tục hoặc token bị sử dụng lạ | Password spraying, credential stuffing, token compromise | Count/rate theo vùng/time window, audit identity đã giảm định danh | In credentials “để xác minh ai thử” |
| 403 sau khi update nhưng DB vẫn đổi | Kiểm quyền sau side effect | Audit mutation, transaction, state invariant | Coi status đúng là hệ thống an toàn |
| Có dữ liệu nhạy cảm xuất hiện trong log | Logging filter/debug, exception, Actuator, APM | Chỉ số lượng/source/retention, không phát tán lại secret | Copy raw log vào ticket/chat |

Nếu nhận thấy **đang có xâm nhập hoặc rò rỉ**, chuyển sang quy trình ứng cứu sự cố và thông báo nhóm chịu trách nhiệm; ưu tiên ngăn tác hại và bảo toàn chứng cứ theo chính sách. Nếu là **false deny** do cấu hình, xác minh policy và hồi phục dịch vụ một cách an toàn bằng fix/rollback đã kiểm thử.

Không tự suy rằng `401` là bug và `403` là “Spring Security chặn nhầm”. Một `403` trên tài liệu của người khác có thể là hệ thống **đang làm đúng**.

## 3. Quy trình ứng phó 7 bước không phá ranh giới bảo mật

### Bước 1 — Kích hoạt kênh xử lý có quyền hạn

Xác định incident owner, người điều phối, chuyên gia Spring Security, SRE, chủ sở hữu dữ liệu và đại diện bảo mật. Dùng ticket/chat nội bộ **đã được cấp quyền truy cập phù hợp**, không chuyển nguyên log nhạy cảm sang kênh rộng. Ghi thời gian phát hiện (kèm múi giờ), phiên bản ứng dụng, phạm vi người dùng/endpoint, đánh giá tác động và mức độ ưu tiên.

Đặt thời hạn cho từng hành động, tránh “giữ debug logging đến khi có ai nhớ tắt”. Người xem bằng chứng phải tuân thủ need-to-know; nếu có dữ liệu khách hàng, áp dụng chính sách bảo vệ dữ liệu hiện hành.

### Bước 2 — Giữ nguyên policy, xác nhận phạm vi

Chụp **hash/version cấu hình, deployment revision, tên rule/route và feature flag**, không chụp secret values. Xác định:

- Có ảnh hưởng chỉ một `SecurityFilterChain`, một tenant hoặc tất cả requests?
- Lỗi bắt đầu sau deploy/config change, rotate key, thay nhà cung cấp danh tính hay thay reverse proxy?
- Có endpoint thật sự đang trả dữ liệu trái phép hay chỉ trả 401/403?
- Có dấu hiệu bị tấn công đang diễn ra không?

Nếu đã phát hiện quyền sai, cần **khống chế sớm** (ví dụ block route nhạy cảm cụ thể, revoke token, disable compromised client). Nếu là sự cố thiếu quyền sai, **không** lấy việc mở quyền đại trà làm workaround.

### Bước 3 — Tăng quan sát theo kiểu tối thiểu và có kiểm soát

Dùng request correlation ID do server tạo, status, method **đã allowlist**, nhóm route hoặc route template **không chứa ID/secret**, code loại lỗi (authn/authz/CSRF/session), service instance và timestamp. Ghi count/latency tóm tắt. Không dump session, principal object, raw path/query, headers, payload, exception messages có thể phản chiếu input.

Nếu cần tín hiệu theo user, dùng định danh đã pseudonymize phù hợp và chỉ được phép trong mục đích incident; không lấy hash không salt của email làm “ẩn danh”. Cân nhắc tính riêng tư của IP, user agent và device ID.

### Bước 4 — Tái hiện bằng dữ liệu giả và tài khoản test

Dùng staging/isolated environment, fixture không chứa dữ liệu thật, identity test với role/tenant cụ thể, kiểm cùng request qua hai vai trò. Tránh sao chép production database ra máy local chỉ để debug. Nếu lỗi chỉ xảy ra ở production, sử dụng **safe telemetry đã giảm dữ liệu** và cài đặt quan sát có phạm vi/thời hạn với phê duyệt, không bật trace toàn hệ thống.

### Bước 5 — Sửa nguyên nhân, không vô hiệu bảo vệ

Tùy nhánh: sửa request matcher/rule order, token verification, session store, proxy forwarded headers, CSRF integration, mapping roles, repository ownership predicate. Dùng change nhỏ, review và kiểm thử âm/dương.

Ví dụ nếu `@PreAuthorize` bị bỏ qua do thiếu `@EnableMethodSecurity`, **bật enforcement đúng** và test. Không thay bằng role guard frontend. Nếu authorization đúng mà UI báo 403 khó hiểu, cải thiện UX/thông báo; **không** cho phép thao tác vốn bị cấm.

### Bước 6 — Phát hành có kiểm soát và xác minh không hạ bảo mật

Canary/rollout theo nhóm hạn chế, theo dõi số lỗi 401/403, auth success, CSRF denial, bất thường 5xx và latency bằng dữ liệu đã giảm định danh. Kiểm lại **người hợp lệ được phép**, **người không hợp lệ bị từ chối**, và **không có side effect** từ request bị từ chối.

Rollback về bản cấu hình **biết chắc an toàn** khi cần; không rollback về bản có lỗ hổng để “giúp hệ thống chạy”.

### Bước 7 — Đóng sự cố và dọn dấu vết chẩn đoán

Gỡ instrumentation tạm có phê duyệt, thu hồi quyền break-glass (nếu có), tắt debug flags có hạn, review quyền truy cập log, xóa/cô lập bằng chứng nhạy cảm theo chính sách lưu giữ, viết postmortem **không chứa raw secrets**. Bổ sung test regression, alert và guardrails CI.

**Không xóa chứng cứ cần thiết cho điều tra pháp lý/an ninh khi chưa được người phụ trách cho phép.** Cần phân biệt **bảo toàn chứng cứ trong kho kiểm soát truy cập** với **phát tán bản copy ra ticket hoặc log mới**.

## 4. Thiết kế log an toàn: giữ tín hiệu, bỏ dữ liệu

Một event hữu ích có thể gồm:

~~~json
{
  "event": "security_request_summary",
  "request_id": "server-generated-random-id",
  "timestamp": "2026-01-01T00:00:00Z",
  "route_bucket": "ops_status",
  "http_method": "GET",
  "http_status": 403,
  "outcome": "denied",
  "service": "account-api",
  "instance": "node-a"
}
~~~

**Dữ liệu minh họa**, không phải log từ người dùng thật. `request_id` phải được tạo hoặc xác minh theo chính sách phía server. `route_bucket` là nhãn định nghĩa trong code, **không phải** nguyên `request.getRequestURI()` hay `request.getQueryString()`.

| Được ghi khi có nhu cầu | Không ghi vào application log thông thường |
|---|---|
| Timestamp, service/version, event code | `Authorization: Bearer ...`, `Authorization: Basic ...` |
| Correlation ID server-generated | `Cookie`, `Set-Cookie`, `JSESSIONID`, session ID |
| HTTP method đã chuẩn hóa, status | Raw request body của login, OTP, password |
| Route template/nhóm tĩnh (không có ID nhạy cảm) | Raw URL có query `token`, `code`, `key`, `email` |
| Authentication type (`basic`, `bearer`, `session`) nếu cần | Access token/refresh token, OAuth2 authorization code |
| Quyết định `ALLOW/DENY` và mã lý do nội bộ giới hạn | `Authentication.toString()`, `SecurityContext` toàn bộ |
| Session-present/context-loaded **boolean** nếu đã cân nhắc | Nội dung session attributes, `UserDetails` hoặc claims đầy đủ |
| Metric/tổng hợp theo tenant ở mức được phép | Raw tenant/user/email/IP nếu không có nhu cầu và quyền |
| Thời gian và instance ID | Private key, client secret, DB password, CSRF token |

**Không phải mọi field “trông vô hại” đều thực sự vô hại.** Path `/users/alice@example.com`, query `?access_token=...`, tenant slug và exception message có thể chứa dữ liệu riêng tư. Tên principal có thể là email; raw IP/user-agent cũng có thể là dữ liệu cá nhân. Cần giới hạn access, retention và mục đích.

### Chỉ ghi mã lý do an toàn

Thay vì:

~~~java
// SAI: đối tượng và message có thể chứa username, token, body.
log.error("Request failed: {} payload={} auth={}",
    exception.getMessage(), requestBody, authentication);
~~~

Chọn sự kiện có cấu trúc và mã nguyên nhân đã chuẩn hóa:

~~~java
// Mảnh minh họa: code chỉ nhận các hằng kiểm soát.
log.warn("security_event={} reason={} request_id={}",
    "authorization_denied",
    "MISSING_AUTHORITY",
    requestId);
~~~

Không nối `request.getParameter("reason")`, `Authorization` hay message exception trực tiếp vào log. Nếu dùng structured arguments/JSON logger, vẫn phải giới hạn **tập field và nguồn**: cấu trúc JSON không làm giá trị nhạy cảm tự an toàn.

### Bảo vệ khỏi log forging

Input có CR/LF hoặc control characters có thể tạo dòng log giả hoặc thay đổi ý nghĩa log. Đừng ghi raw user-agent, user name, path, error message. Nếu phải ghi một input do client đưa vào theo policy, chuẩn hóa/giới hạn độ dài/escape control characters ở lớp chuyên dụng và kiểm tra quyền đọc log. Đặc biệt không tin client-supplied `X-Request-ID` làm correlation ID đã được xác thực.

## 5. Spring Security: chọn đúng điểm quan sát

Spring Security Servlet dùng filter chain cho authentication, CSRF và authorization. Mỗi điểm trả 401/403 có ý nghĩa khác nhau:

| Điểm quan sát | Loại sự kiện phù hợp | Cần tránh |
|---|---|---|
| `AuthenticationManager` / provider | Thành công/thất bại theo **loại**, không log credential | `UsernamePasswordAuthenticationToken` đầy đủ |
| `AuthenticationEntryPoint` | Yêu cầu chưa xác thực; 401 hoặc redirect login theo scheme | Trả lỗi phản chiếu token/password |
| `AccessDeniedHandler` | Principal thiếu quyền; 403 (hoặc app chọn 404 để ẩn tài nguyên) | In raw principal/ACL/resource content |
| `CsrfFilter` | POST/PATCH/DELETE thiếu/sai token | Dump CSRF token thật |
| `AuthorizationFilter` / method security | Rule/decision và mã reason đã chuẩn hóa | Mở `permitAll` để tránh 403 |
| `SecurityContextRepository` | Context có/không, session lookup được/không | In `SecurityContext`/session dump |
| Controller/service | Resource action, thuộc tính policy đã giảm định danh | In entity, body, object private fields |
| Reverse proxy/gateway | Request ID, route pattern/status, rate metrics | Raw URL/query, cookies/headers |

Trong `authorizeHttpRequests`, matcher được xét theo thứ tự; `anyRequest().denyAll()` giúp không mở nhầm route mới. Chỉ rule thuộc **SecurityFilterChain được chọn** mới áp dụng. Một chain `securityMatcher("/api/**")` không thể bảo vệ `/internal/**` nếu không có fallback chain.

**Phân biệt đúng khi điều tra:**

- `401` thường là thiếu hoặc sai authentication, HTTP Basic có thể trả `WWW-Authenticate`.
- `403` có thể do authenticated user thiếu role hoặc request thiếu CSRF token. Không suy từ status rằng “user mất login”.
- `404` có thể là resource không tồn tại hoặc cố ý che ID người khác. Không thay 404 bằng 200 chỉ để kiểm data.
- Browser form login có thể redirect `302` thay vì trả 401; xác định hợp đồng API.

Khi một endpoint cần kiểm ownership/tenant, `hasRole("USER")` không đủ; cần kiểm ở service/repository. Incident diagnostics tuyệt đối không được bỏ qua bước này.

## 6. Một ứng dụng Java 17 minh họa quan sát an toàn

Để chứng minh thực tế, ta tạo một service nhỏ có:

- `GET /public/health`: public, chỉ trả trạng thái không nhạy cảm.
- `GET /api/ops/status`: chỉ `ROLE_OPS`, trả trạng thái cố định.
- Tất cả method/path khác bị `denyAll()`.
- Một servlet filter **đặt trước Spring Security** phát correlation ID server-generated và ghi **duy nhất** event metadata đã allowlist, kể cả khi request bị chặn trước controller.
- Hai account demo `ops` và `viewer`; passwords được cấp **qua runtime configuration**, không commit giá trị của môi trường thật vào source.
- MockMvc kiểm chức năng, quyền, absence of leaked secret trong **log ứng dụng thử nghiệm** và phản hồi.

Demo không có API dump cấu hình, xem session, thay role hoặc tắt quyền. Nó minh họa triage **không cần** một “debug backdoor”.

**Công cụ:** JDK 17+, Maven 3.9+, Spring Boot 3.5.0 / Spring Security 6.x.

~~~text
safe-incident-debug/
├── pom.xml
├── src/main/java/com/example/safediag/
│   ├── SafeIncidentApplication.java
│   ├── SecurityConfig.java
│   ├── SafeRequestAuditFilter.java
│   └── DiagnosticController.java
└── src/test/java/com/example/safediag/
    └── SafeIncidentSecurityTest.java
~~~

### 6.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>safe-incident-debug</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
~~~

### 6.2. SafeIncidentApplication.java

~~~java
package com.example.safediag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeIncidentApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeIncidentApplication.class, args);
    }
}
~~~

### 6.3. SecurityConfig.java

~~~java
package com.example.safediag;

import jakarta.servlet.DispatcherType;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${OPS_PASSWORD}") String opsPassword,
            @Value("${VIEWER_PASSWORD}") String viewerPassword) {

        return new InMemoryUserDetailsManager(
            User.withUsername("ops")
                .password(encoder.encode(opsPassword))
                .roles("OPS")
                .build(),
            User.withUsername("viewer")
                .password(encoder.encode(viewerPassword))
                .roles("VIEWER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
                .requestMatchers(HttpMethod.GET, "/public/health")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/ops/status")
                    .hasRole("OPS")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // Không tắt CSRF, không permitAll toàn cục, không mở debug path.
        return http.build();
    }
}
~~~

**Chú ý về nguồn cấu hình:** `@Value("${OPS_PASSWORD}")` và `@Value("${VIEWER_PASSWORD}")` đọc properties có tên tương ứng; trong demo, chúng có thể đến từ env vars. Nếu thiếu, ứng dụng không được có “default debug password” để chạy qua. Test sẽ cấp **giá trị test-only** bằng `@SpringBootTest(properties=...)`; chúng không phải mật khẩu production.

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` dùng encoder phù hợp để hash mật khẩu demo ở runtime, không ghi raw password vào logger. Với hệ thống thật, thay in-memory users bằng IdP/DB, session/token policy, rotation và least privilege thích hợp. `STATELESS` phù hợp HTTP Basic demo, nhưng **không** là lựa chọn mặc định cho hệ thống muốn lưu login qua `HttpSession`.

`httpBasic` có thể trả `401` cho client chưa có credentials và `403` cho user đã đăng nhập nhưng không có OPS. Các request `POST` khác cũng bị CSRF mặc định hoặc catch-all chặn; không tắt CSRF để kiểm tra quyền. `DispatcherType.ERROR`/`FORWARD` chỉ phục vụ những lượt dispatch nội bộ cần thiết cho response/error của demo, không phải mở URL public.

### 6.4. SafeRequestAuditFilter.java

~~~java
package com.example.safediag;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class SafeRequestAuditFilter extends OncePerRequestFilter {

    private static final Logger log =
        LoggerFactory.getLogger(SafeRequestAuditFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // Không tin request header X-Request-ID do client tự gửi.
        String requestId = UUID.randomUUID().toString();
        request.setAttribute("app.requestId", requestId);
        response.setHeader("X-Request-ID", requestId);

        try {
            chain.doFilter(request, response);
        } finally {
            log.info(
                "event=http_request request_id={} route_bucket={} "
                + "method={} status={}",
                requestId,
                routeBucket(request.getRequestURI()),
                safeMethod(request.getMethod()),
                response.getStatus()
            );
        }
    }

    private static String routeBucket(String uri) {
        // Đọc URI để phân loại nhưng không đưa raw URI vào log.
        return switch (uri) {
            case "/public/health" -> "public_health";
            case "/api/ops/status" -> "ops_status";
            default -> "other";
        };
    }

    private static String safeMethod(String method) {
        return switch (method) {
            case "GET", "POST", "PUT", "PATCH", "DELETE",
                 "HEAD", "OPTIONS" -> method;
            default -> "OTHER";
        };
    }
}
~~~

**Vì sao ví dụ này không làm lộ dữ liệu?**

- `requestId` được tạo ngẫu nhiên phía server, **không lấy session ID, JWT hoặc header do client tự gửi**. Nó chỉ để liên kết các sự kiện cùng request.
- `routeBucket()` trả một trong các nhãn cố định, không ghi raw path/query. Nếu request là `/reset-password?token=SECRET`, log chỉ ghi `other`, không có token.
- `safeMethod()` chỉ cho phép các method name hợp lệ/đã chuẩn hóa.
- Không gọi `getHeader("Authorization")`, `getCookies()`, `getInputStream()`, `getParameterMap()`, `SecurityContextHolder.getContext().toString()`, `request.toString()` hoặc ghi exception message chứa input.
- `@Order(Ordered.HIGHEST_PRECEDENCE + 10)` đăng ký servlet filter đủ sớm trong demo để nhận cả request bị Spring Security từ chối, nếu container/filter registration áp dụng thứ tự Spring Boot như dự kiến.
- `finally` ghi một event ngay cả khi chain kết thúc bất thường. Tuy nhiên status lúc đó có thể chưa phản ánh **error dispatch cuối cùng** nếu lỗi chưa được xử lý; production cần quyết định logging sau error handling và async dispatch phù hợp. Mẫu này chỉ minh họa request **đồng bộ**.

**Giới hạn:** event chỉ chứng minh filter này **không chủ động log bí mật**. Nó không thể đảm bảo log từ mọi dependency, servlet container, proxy, APM agent hoặc default access log đã được sanitize. Cần kiểm những lớp đó theo cùng chính sách.

Không dùng correlation ID làm authorization token, không dùng nó thay session ID. Nếu frontend gửi một `X-Request-ID`, hệ thống có thể dùng một field riêng như `client_trace_id` đã validate cho debugging, nhưng không được coi nó là identity/tính toàn vẹn hoặc ghi raw không giới hạn.

### 6.5. DiagnosticController.java

~~~java
package com.example.safediag;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DiagnosticController {

    @GetMapping("/public/health")
    public Health health() {
        return new Health("ok");
    }

    @GetMapping("/api/ops/status")
    public OpsStatus opsStatus() {
        // Không trả Environment, beans, keys, stack trace hay session.
        return new OpsStatus("operational");
    }

    public record Health(String status) {}
    public record OpsStatus(String status) {}
}
~~~

Endpoint OPS trong demo chỉ trả trạng thái tĩnh, **không** cung cấp toàn bộ config/server details. Trong production, nhiều tình huống không cần endpoint OPS mới: quan sát qua metrics/tracing đã có có thể an toàn hơn. Nếu buộc dùng endpoint chẩn đoán, giới hạn network, RBAC, danh mục field, thời gian tồn tại và audit.

### 6.6. SafeIncidentSecurityTest.java

~~~java
package com.example.safediag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "OPS_PASSWORD=local-fixture-ops-only",
    "VIEWER_PASSWORD=local-fixture-viewer-only"
})
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class SafeIncidentSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicHealthDoesNotNeedCredentials() throws Exception {
        mvc.perform(get("/public/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(header().exists("X-Request-ID"));
    }

    @Test
    void anonymousCannotAccessOpsEndpoint() throws Exception {
        mvc.perform(get("/api/ops/status"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void viewerCannotUseOpsEndpoint() throws Exception {
        mvc.perform(get("/api/ops/status")
                .with(httpBasic(
                    "viewer", "local-fixture-viewer-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void opsCanReadOnlySafeStatus() throws Exception {
        mvc.perform(get("/api/ops/status")
                .with(httpBasic(
                    "ops", "local-fixture-ops-only")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("operational"));
    }

    @Test
    void spoofingRoleAndRequestIdCannotWidenPermissions(
            CapturedOutput logs) throws Exception {

        String secretCanary = "SENSITIVE_CANARY_NEVER_LOG_THIS";

        mvc.perform(get("/api/ops/status")
                .with(httpBasic(
                    "viewer", "local-fixture-viewer-only"))
                .header("X-Role", "OPS")
                .header("X-Request-ID", secretCanary)
                .header("X-Api-Key", secretCanary)
                .param("access_token", secretCanary))
            .andExpect(status().isForbidden())
            .andExpect(header().exists("X-Request-ID"));

        assertThat(logs.getAll())
            .contains("event=http_request")
            .doesNotContain(secretCanary);
    }

    @Test
    void deniedEndpointDoesNotReflectCredential(
            CapturedOutput logs) throws Exception {
        String canary = "BEARER_CREDENTIAL_NOT_FOR_LOGGING";

        mvc.perform(get("/internal/debug")
                .header("Authorization", "Bearer " + canary)
                .param("token", canary))
            .andExpect(status().isUnauthorized());

        assertThat(logs.getAll())
            .contains("event=http_request")
            .doesNotContain(canary);
    }

    @Test
    void thereIsNoTemporaryPermitAllForOtherPaths()
            throws Exception {
        mvc.perform(get("/internal/debug")
                .with(httpBasic(
                    "ops", "local-fixture-ops-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void csrfIsStillEnforcedForUnsafeRequests() throws Exception {
        mvc.perform(post("/api/ops/status")
                .with(httpBasic(
                    "ops", "local-fixture-ops-only"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isForbidden());

        // Có CSRF token vẫn bị denyAll vì POST không nằm trong policy.
        mvc.perform(post("/api/ops/status")
                .with(httpBasic(
                    "ops", "local-fixture-ops-only"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isForbidden());
    }
}
~~~

**Test đáng chú ý:**

- Không có controller thực nào đọc `Authorization`, `X-Api-Key`, `X-Role` hoặc query `access_token`. Test cố ý gửi một marker vô hại giả secret để chứng minh filter log **không phản chiếu marker**.
- Test viewer đã xác thực nhưng thiếu `ROLE_OPS` nhận `403`; test anonymous nhận `401`; test ops có quyền nhận `200`.
- Test `/internal/debug` chứng minh không có debug backdoor, ngay cả ops cũng nhận `403` nếu đã xác thực.
- `CapturedOutput` trong Spring Boot Test giúp kiểm log được capture trong **thời gian test**, không phải quét log production hoặc tất cả các logger của hạ tầng.
- `X-Request-ID` request do client đặt không được dùng làm ID log. Response có ID riêng do server tạo.
- `POST /api/ops/status` không được phép, cả khi có CSRF token hợp lệ. Đây là **authorization theo method**, không phải tắt CSRF để “cho chạy”.
- `local-fixture-...` là dữ liệu test không có quyền ở bất kỳ môi trường thật nào; production phải có secret/config hoặc hệ thống danh tính riêng.

`@SpringBootTest` và `@AutoConfigureMockMvc` chạy security filter chain với MockMvc, không cần mở cổng HTTP thật. Dù test này pass, **không thể suy rằng log của Nginx, ingress, service mesh, APM, sidecar hoặc công cụ hỗ trợ đã an toàn**; phải có kiểm thử/hardening riêng tại các lớp đó.

## 7. Chạy và kiểm tra mẫu, không cần mở quyền

Trong thư mục dự án:

~~~bash
mvn test
~~~

Kỳ vọng các test pass nếu môi trường Java/Maven/dependencies phù hợp. Đây là **hướng dẫn thực thi**, không phải khẳng định Maven đã được chạy trong tài liệu này.

Chạy app local bằng **hai password riêng được cấp qua environment** (bash). Lệnh nhập ẩn để tránh ghi nguyên secret vào shell history:

~~~bash
read -r -s -p "OPS password: " OPS_PASSWORD
echo
read -r -s -p "VIEWER password: " VIEWER_PASSWORD
echo
export OPS_PASSWORD VIEWER_PASSWORD
mvn spring-boot:run
~~~

Environment variables phù hợp demo, nhưng có thể bị đọc bởi process inspection/debug tools; production nên dùng secret manager và quyền hạn phù hợp, không coi env là bảo vệ tuyệt đối. Mật khẩu demo không được đưa vào Git/JAR/image và không được in vào log.

Ở terminal khác:

~~~bash
# Public endpoint: 200.
curl -i http://localhost:8080/public/health

# Anonymous OPS request: 401.
curl -i http://localhost:8080/api/ops/status

# Authenticated OPS: 200. curl hỏi password tương tác.
curl -i -u ops http://localhost:8080/api/ops/status

# Authenticated OPS nhưng URL không được duyệt: 403.
curl -i -u ops http://localhost:8080/internal/debug
~~~

Trên PowerShell, dùng `curl.exe` nếu `curl` là alias `Invoke-WebRequest`. Đừng đặt password trên dòng lệnh `-u ops:secret`, vì history/process list có thể thấy. Khi kết thúc kiểm thử:

~~~bash
unset OPS_PASSWORD VIEWER_PASSWORD
~~~

`unset` không thu hồi credentials nếu đã bị lộ; phải reset/revoke ở hệ thống phát hành.

**Những gì nên thấy trong application log:** một dòng `event=http_request request_id=<random> route_bucket=ops_status method=GET status=403` hoặc tương tự; không xuất hiện raw password, token, cookie hay query. Đây là **ví dụ format**, UUID sẽ khác mỗi request. Nếu có log proxy/container khác, phải đánh giá riêng.

## 8. Gỡ lỗi 401 và login mà không in credentials

### Trường hợp A — 401 sau khi gửi Bearer

Các nguyên nhân khả dĩ: client không gửi header, token hết hạn, issuer không tin cậy, signature sai, audience sai, định dạng `Authorization` không hợp lệ, key rotation chưa đồng bộ. Ghi được:

~~~text
event=authentication_failure
auth_scheme=bearer
reason=TOKEN_VALIDATION_FAILED
route_bucket=orders_api
request_id=<server-generated>
status=401
~~~

**Không ghi:** token value, JWT raw, toàn bộ claims, signature, refresh token, client secret, security context. Nếu cần phân biệt `expired` với `audience_mismatch` cho debugging, dùng **reason code trong log kiểm soát quyền**, không trả thông tin nhạy cảm ra response công khai; cân nhắc nguy cơ giúp attacker suy đoán token.

Với Spring Security OAuth2 Resource Server, phải xác minh issuer, audience theo hợp đồng và thuật toán phù hợp. Khi JWKS rotate, kiểm cache/keys bằng metadata phiên bản an toàn; đừng đưa private key ra các verifier chỉ để debug.

### Trường hợp B — 401 sau session login

Quan sát theo chuỗi:

~~~text
POST /login:
  authn_succeeded=true?
  set_cookie_session_present=true?
  security_context_saved=true?

GET /api/me:
  session_cookie_present=true?
  session_lookup_hit=true?
  security_context_loaded=true?
  authentication_present=true?
~~~

Đây là danh sách **boolean/diagnostic signals**, không phải thuộc tính mặc định mọi logger của Spring. Đừng gọi `request.getSession()` trong logging filter vì nó có thể **tạo session mới và làm sai chẩn đoán**; dùng `getSession(false)` ở thành phần được phép khi cần.

Lưu ý `HttpOnly` khiến JavaScript không đọc `JSESSIONID`, không nghĩa browser mất cookie. Session ID đổi sau login có thể là **session fixation protection**. `SecurityContextHolder` được dọn sau request là đúng; nếu custom login dùng explicit-save mà quên `SecurityContextRepository.saveContext(...)`, request sau có thể anonymous.

### Trường hợp C — Basic credentials sai

Chỉ ghi credential type `basic`, kết quả `BAD_CREDENTIALS`, request ID, rate đã tổng hợp. Không log Base64 `Authorization`: Base64 có thể được giải mã thẳng thành username/password. Không chạy script decode header thật “để tiện kiểm”. Với nguy cơ password spraying, dùng rate limiting/alert, không tạo log hàng triệu secret.

## 9. Gỡ lỗi 403 mà không tắt phân quyền hoặc CSRF

Đầu tiên xác định `403` đến từ đâu:

1. **CSRF denial:** unsafe method (POST/PUT/PATCH/DELETE) thiếu/sai token; filter chặn trước controller. Test authorization cần cung cấp token hợp lệ theo cơ chế client.
2. **Route authorization:** user đã xác thực nhưng thiếu `ROLE_ADMIN`, `SCOPE_x` hoặc matcher bắt nhầm. Kiểm method, path pattern, thứ tự request matchers và chain selection bằng dữ liệu đã giảm định danh.
3. **Method security:** `@PreAuthorize`/policy bean chặn service; cần `@EnableMethodSecurity` và Spring proxy invocation đúng.
4. **Object authorization:** user đủ role nhưng không sở hữu ID, khác tenant hoặc không có ACL. Đây có thể là hành vi đúng; không cho phép truy cập bằng cách bỏ owner predicate.
5. **Firewall/CORS/proxy:** request không tới đúng application route, preflight bị chặn, header được rewrite; cần quan sát ingress và application riêng.

**Không được làm các “fix tạm” sau:**

~~~java
// SAI: loại bỏ lớp bảo vệ để xóa triệu chứng 403.
http.csrf(csrf -> csrf.disable());
http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
~~~

Ngoài việc tạo lỗ hổng, thay đổi này còn làm mất bằng chứng: bạn không còn biết chính sách nào đã chặn request. Cách sửa đúng là tái hiện với principal test, CSRF token hợp lệ và tài nguyên test, sau đó chỉnh **rule cụ thể** đã xác nhận sai.

### HTTP status không đủ: kiểm side effect

Một endpoint trả 403 nhưng DB đã đổi trước khi policy check thì vẫn có lỗi nghiêm trọng. Trong test:

~~~text
Actor: bob (không sở hữu order 101)
Action: PATCH /api/orders/101
Expected HTTP: 403 hoặc 404 theo policy
Expected DB state: owner/order content giữ nguyên
Expected side effects: không email, không event, không ghi file
~~~

Nếu người được phép sửa thành công nhưng user khác thì bị từ chối, hai case này cùng xác minh ranh giới. Không sửa frontend ẩn nút để thay backend test.

## 10. Debug request/response mà không dùng raw payload dump

Nhiều thư viện request logging có tùy chọn `includeHeaders`, `includePayload`, `includeQueryString`. Bật toàn bộ ở production có thể log mật khẩu, token, PII và nội dung khách hàng.

Ví dụ cấu hình không nên đưa vào production chỉ để debug:

~~~java
// SAI trong môi trường chứa dữ liệu nhạy cảm.
CommonsRequestLoggingFilter filter = new CommonsRequestLoggingFilter();
filter.setIncludeHeaders(true);
filter.setIncludePayload(true);
filter.setIncludeQueryString(true);
~~~

**Thay thế an toàn hơn:** chỉ ghi route template/route bucket, method đã chuẩn hóa, status, request ID, duration và event code. Nếu thật sự cần biết một input bị sai format, ghi **validation rule ID** thay vì raw input; ví dụ `INVALID_DATE_FORMAT`, `MISSING_REQUIRED_FIELD`, `UNSUPPORTED_MEDIA_TYPE`. Một hash đơn giản của raw email/token thường không đủ ẩn danh và có thể bị dò lại từ dictionary.

Nếu cần so sánh các request mà không lưu dữ liệu thô, cân nhắc fingerprint **HMAC với key riêng dùng cho telemetry, phạm vi/thời gian ngắn và quyền hạn chặt**, nhưng chỉ khi có cơ sở nghiệp vụ và chính sách bảo vệ dữ liệu. Không dùng `SHA-256(rawPassword)` hoặc log 4 ký tự cuối của token một cách mặc định: đó vẫn có thể là dữ liệu nhạy cảm hoặc giúp correlation sai mục đích.

Tránh chụp screenshot DevTools Network khi header chứa token; nếu cần cung cấp minh chứng, phải redact **trước khi chia sẻ**, xác nhận ảnh/PDF không còn metadata hoặc lớp text có thể khôi phục bí mật.

## 11. Error response an toàn nhưng đủ để người dùng báo lỗi

Người dùng cần cách gửi ticket mà không phải chụp token hay body lỗi nội bộ. Một response an toàn có thể là:

~~~json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to perform this action.",
  "requestId": "server-generated-id"
}
~~~

Đây là **mẫu hợp đồng API minh họa**, không phải body mặc định Spring Security của ví dụ ở mục 6. Với Spring MVC, có thể sử dụng `ProblemDetail` cho các application exceptions; exception translation trong Spring Security có handlers riêng cho 401/403. Không để frontend hiển thị nguyên stack trace/exception message và không đưa secret vào mã lỗi.

**Phân biệt hai đối tượng:**

- Client: thông báo ngắn, status, request ID; không giải thích chi tiết “resource ID 515 thuộc Alice ở tenant east”.
- Điều tra viên được phép: event code/route template/metadata đã giảm định danh và audit cụ thể, được cấp quyền qua hệ thống quan sát.

Không tự đưa `ex.getMessage()` vào JSON, vì exception message có thể chứa database URL, query, token hay dữ liệu client. Tránh cấu hình `server.error.include-stacktrace=always` và `server.error.include-message=always` tại production chỉ để debug.

## 12. Actuator và logging level: tránh mở kênh phụ để chẩn đoán

Spring Boot Actuator cung cấp observability và management endpoints, nhưng có endpoint nhạy cảm như `env`, `configprops`, `heapdump`, `threaddump`, `loggers`, `mappings`. Không mở `management.endpoints.web.exposure.include=*` ra Internet hoặc `.permitAll("/actuator/**")` trong sự cố.

Nếu cần thêm metrics/health:

- Chỉ mở những endpoint đã đánh giá an toàn, đúng mạng/quyền.
- Giới hạn management interface/network, role riêng, mTLS/VPN theo hạ tầng; không tin chỉ “đường dẫn khó đoán”.
- Kiểm sanitization của config values và logs; chính sách “sanitize theo tên key” có thể bỏ sót tên custom.
- Tách lệnh xem hoặc thay log level khỏi app user thường; không cho bất kỳ user nào gọi endpoint `loggers`.
- Có change record, TTL và monitoring cho bất kỳ thay đổi tạm nào.

Ví dụ cần tránh:

~~~properties
# SAI nếu áp dụng rộng để "xem toàn bộ cấu hình".
management.endpoints.web.exposure.include=*
management.endpoint.env.show-values=always
logging.level.org.springframework.security=TRACE
~~~

`TRACE`/wire-level logs có thể chứa thông tin nhạy cảm tùy component. Khi thật sự phải bật logging chi tiết ở một service hoặc request subset, cần review **kiểu dữ liệu sẽ log**, quyền xem, TTL tự động tắt, sampling, kênh an toàn và điều kiện giữ chứng cứ. **Ưu tiên log sự kiện mục tiêu** thay vì tăng root level.

## 13. Những workaround bị cấm và lựa chọn thay thế

| Workaround nguy hiểm | Vì sao nguy hiểm | Thay thế đúng |
|---|---|---|
| `.anyRequest().permitAll()` | Bỏ toàn bộ route authorization | So lại matcher/chain, sửa rule cụ thể sau test |
| `.requestMatchers("/api/**").permitAll()` | Mở tất cả API, gồm endpoint mới | Liệt kê route/method hợp lệ, `denyAll` fallback |
| `csrf.disable()` cho browser app | Mở nguy cơ CSRF khi credentials được gửi tự động | Cấp/sử dụng CSRF token đúng, test riêng |
| `web.ignoring("/**")` | Bỏ filter chain và security headers | Dùng `permitAll` có chủ đích cho public assets; giữ chain |
| Tắt password/JWT validation | Cho credentials giả hoặc không hợp lệ đi qua | Sửa issuer/key/audience/time config bằng chứng cứ |
| Bỏ predicate owner/tenant | Mở truy cập chéo user/tenant | Test và sửa query/policy chính xác |
| Debug login trả raw `Authentication` | Lộ credentials, roles, claims và identifiers | Trả boolean/principal tối thiểu theo quyền |
| Dump `Cookie`/`Authorization` | Lộ session/token, có thể dẫn đến chiếm quyền | Cookie-present/auth-scheme và event code |
| `management...include=*` công khai | Lộ config, memory, mappings, log controls | Management network/RBAC + endpoint allowlist |
| Thêm user `ROLE_ADMIN` chung | Khó audit, leo thang đặc quyền | JIT break-glass approval theo người/time/scope |
| Tắt WAF/rate limit toàn cục | Tăng bề mặt tấn công đúng lúc có sự cố | Rule hẹp theo route/signature đã kiểm tra |
| Upload production DB sang laptop | Mở rộng phạm vi dữ liệu nhạy cảm | Fixture tổng hợp hoặc môi trường forensic được kiểm soát |
| In exception message/body | Có thể phản chiếu secret hoặc PII | Lý do theo enum và request ID |

Nếu cần áp dụng một thay đổi **phục hồi** trong emergency, phải có người chịu trách nhiệm, đánh giá rủi ro, test và rollback; nó **không được là thay đổi làm mất kiểm tra quyền**. Một route đúng bị chặn do bug nên được sửa đúng matcher/authority mapping, không mở đường phụ `/debug?skipAuth=true`.

## 14. Break-glass: hỗ trợ khẩn cấp nhưng không tạo “admin tạm” tùy tiện

Một số sự cố thực sự cần quyền đặc biệt để khôi phục hệ thống. **Break-glass** khác hoàn toàn với `permitAll` hoặc gắn `ROLE_ADMIN` cho tất cả user.

Một quy trình break-glass đúng có:

1. **Lý do rõ:** incident ID, mục tiêu, resource/action cụ thể; không dùng cho sự tiện lợi hằng ngày.
2. **Người phê duyệt độc lập:** ít nhất theo chính sách tổ chức, có thể yêu cầu hai người hoặc on-call security.
3. **Danh tính riêng và MFA:** không dùng shared password hoặc tài khoản ẩn không audit được.
4. **Quyền tối thiểu:** read-only diagnostics khi có thể; không tự cấp quyền đọc dữ liệu khách hàng nếu chỉ cần kiểm status.
5. **JIT và TTL ngắn:** hết hạn tự động, revoke ngay khi xong; không tồn tại vĩnh viễn.
6. **Phạm vi cô lập:** giới hạn service, environment, action, host và session; có thể yêu cầu VPN/mTLS.
7. **Audit đầy đủ nhưng tối thiểu:** ai được duyệt, khi nào, hành động loại nào, kết quả; không log raw secret hoặc payload.
8. **Giám sát riêng và hậu kiểm:** alert lúc cấp/thu hồi, kiểm tra những lệnh đã thực hiện và cập nhật runbook.

**Không nên** đưa vào code:

~~~java
// SAI: query parameter trở thành "công tắc" vô hiệu auth.
if ("true".equals(request.getParameter("debug"))) {
    return allowEverything();
}
~~~

Nếu sản phẩm phải hỗ trợ một thao tác khôi phục đặc biệt, xây **lệnh quản trị riêng được bảo vệ ở tầng identity, network và policy**, với review/audit, hoặc dùng hạ tầng quản trị có kiểm soát. Không đặt một query/header bypass vào endpoint ứng dụng.

## 15. Containment an toàn khi nghi đang bị khai thác

Khi có dấu hiệu credential compromise, lộ token, BOLA hoặc lạm dụng endpoint, các hành động containment có thể gồm:

- Revoke access/refresh tokens, reset compromised credentials, rotate client secret hoặc signing key theo runbook, cập nhật session invalidation.
- Block **đúng endpoint/action/traffic pattern** đang bị khai thác hoặc đưa chức năng nhạy cảm vào chế độ không nhận lệnh ghi. Xác minh block không ảnh hưởng đường quan sát thiết yếu.
- Rollback hoặc rollout hotfix có policy chặt chẽ, giám sát negative/positive test.
- Thêm rate limits / abuse detection trong phạm vi phù hợp, không bắt buộc tắt toàn bộ security middleware.
- Cô lập một instance/service nghi compromise, bảo toàn forensic artifacts trong kho có RBAC và chain-of-custody.
- Kiểm theo tenant/owner nếu lỗi là object-level authorization, xác định phạm vi ảnh hưởng và liên hệ đúng đội chịu trách nhiệm.

**Không tự động xóa log, xóa container image, dọn session store hay phá chứng cứ trước khi có kế hoạch ứng cứu.** Mục tiêu là giới hạn thiệt hại và giữ đủ bằng chứng kiểm soát để tìm root cause; không nhân bản secret trong quá trình điều tra.

Nếu đã lộ secret trong một log, **đừng dán lại log đó** vào ticket. Hãy thông báo incident owner, hạn chế quyền truy cập kho log, rotate/revoke secret theo mức ảnh hưởng, xác định copies/retention và xử lý dữ liệu theo chính sách tổ chức.

## 16. Điều tra rule/chain sai mà không phải ghi toàn bộ request

### Quy tắc route trong Spring Security

Một `SecurityFilterChain` có thể có cấu hình:

~~~java
// Mảnh cấu hình minh họa, không phải class độc lập.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/status").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/orders/{id}")
        .hasRole("USER")
    .anyRequest().denyAll()
);
~~~

Nếu user hợp lệ bị 403, kiểm:

1. Request method chính xác là `GET` hay `POST`?
2. Route mapping và context path có đúng `/api/orders/{id}`?
3. Principal có `ROLE_USER` đáng tin hay một claim khác format?
4. Request có vào đúng chain không? Một `securityMatcher` rộng/hẹp hoặc `@Order` sai có thể chọn chain khác.
5. Object authorization trong service có chặn do owner/tenant không?
6. Response bị tạo bởi CSRF, AccessDeniedHandler, method security hay exception ở downstream?

Không cần ghi raw `/api/orders/423?token=...` để trả lời; dùng route template, method và request ID. Những thứ có thể chứa IDs khách hàng chỉ nên được dùng trong forensic store có quyền hạn với mục đích rõ.

### Nhiều SecurityFilterChain

`securityMatcher` chọn phạm vi **toàn chain**; `requestMatchers` phân quyền **bên trong chain**. `.anyRequest().denyAll()` trong chain chỉ match `/api/**` không bảo vệ `/legacy/**` nếu không có fallback. Khi điều tra sự cố route mở bất ngờ, kiểm đủ chain inventory và thứ tự. Không “sửa” bằng cách nới matcher `/**` cho `permitAll`.

### Method security và proxy

`@PreAuthorize` cần `@EnableMethodSecurity` ở cấu hình tương ứng. Internal self-invocation qua `this.method()` có thể bypass AOP interceptor, và gọi service qua job/message khác controller có thể bypass HTTP authorization. Kiểm policy thực thi ở service/repository, có test gọi cả entry points nhạy cảm.

## 17. Tạo tín hiệu root cause mà không lộ dữ liệu

Một số **mã chẩn đoán mục tiêu** có thể được phát bởi code/metrics được review:

~~~text
AUTHN_MISSING
AUTHN_BAD_CREDENTIALS
TOKEN_EXPIRED
TOKEN_VALIDATION_FAILED
AUTHZ_MISSING_AUTHORITY
AUTHZ_OBJECT_DENIED
CSRF_MISSING
CSRF_INVALID
SESSION_NOT_FOUND
CONTEXT_NOT_LOADED
ROUTE_NOT_ALLOWED
RATE_LIMITED
~~~

Những mã này mang tính **khái niệm và minh họa**, không phải enum mặc định của Spring Security. Khi implement cần mapping rõ từ exception/event loại nào, không in raw exception message. Public API có thể cố ý trả code tổng quát hơn để tránh lộ cơ chế xác thực.

Nếu cần correlation trong hệ thống phân tán:

- Gateway sinh hoặc chuẩn hóa một trace ID không chứa credentials.
- Các service tin cậy propagate ID qua kênh được kiểm soát; client-supplied ID phải được validate/đổi tên nếu không đáng tin.
- Log mỗi service kèm `event_code`, `route_bucket`, `status`, `service_version`, `trace_id` — không gửi payload/token qua tracing baggage.
- Traces/spans không tự an toàn: HTTP semantic attributes, DB statements, span events và exception attributes vẫn có thể mang secret. Cấu hình redaction ở collector/agent theo field allowlist.
- Metrics có cardinality thấp: không gắn raw user ID/email/token/session ID vào metric labels.

Một metric như `security_denial_total{reason="MISSING_AUTHORITY",route="ops_status"}` hữu ích hơn hàng triệu labels chứa user/URL khác nhau. Khi cần phân tích người dùng bị ảnh hưởng, dùng kho audit riêng có RBAC/retention phù hợp, không nhồi PII vào Prometheus labels.

## 18. Kiểm thử regression: quyền không mở và dữ liệu không rò

Một incident fix phải có cả phép thử thành công **và** bị từ chối:

| Case | Input | Bằng chứng pass |
|---|---|---|
| Public health | Anonymous `GET /public/health` | 200, không lộ config |
| OPS status | OPS credentials hợp lệ | 200, response chỉ trạng thái |
| OPS status | Viewer credentials hợp lệ | 403, không trả diagnostics nhạy cảm |
| OPS status | Anonymous | 401 theo HTTP Basic |
| Đường `/internal/debug` | OPS đã đăng nhập | 403 vì ngoài allowlist |
| Method không mong đợi | `POST /api/ops/status` với CSRF hợp lệ | Vẫn 403 do policy, không handler ghi dữ liệu |
| Thiếu CSRF | POST không token | 403, bảo vệ vẫn bật |
| Header `X-Role: OPS` giả | Viewer gửi header giả | Vẫn 403 |
| Query/header chứa canary giả secret | HTTP request test | Log và response không phản chiếu canary |
| Root/logging level ở production | Kiểm config triển khai | Không TRACE/headers/payload dump bừa bãi |
| Actuator, proxy, APM | Smoke test tại entry point thật | Không lộ config/secret hoặc mở unauth endpoint |
| Đọc/sửa resource ngoài tenant | Account khác tenant | Từ chối đúng và không có side effect |
| Rollback | Bản cũ được coi là an toàn | Policy vẫn deny và test âm pass |

**Không chỉ test status.** Với endpoint thay đổi dữ liệu, kiểm DB/queue/cache/file sau request bị từ chối. Một response 403 xuất hiện **sau khi đã cập nhật dữ liệu** không được coi là an toàn.

### Quy trình test canary không lộ secret thật

Trong test, dùng một marker giả như `SENSITIVE_CANARY_NEVER_LOG_THIS` đặt ở query/header/body theo cách có kiểm soát. Sau khi chạy, quét **log test** và response để xác nhận marker không xuất hiện. Marker không phải password/token thật. Không tự chèn production secrets vào request “để test redaction”.

**Giới hạn cần công bố:** một phép thử canary không chứng minh mọi dữ liệu đều đã được redact ở mọi nơi. Cần bổ sung code review, integration test, ingress/APM config review, source/artifact scanning và kiểm sampling sau deploy.

## 19. Runbook xử lý theo từng nhóm sự cố

### 19.1. “Production 403 hàng loạt ngay sau deploy”

- So thời điểm đổi `SecurityFilterChain`, `@EnableMethodSecurity`, claims mapping, route matcher và proxy path.
- Thu request ID, rule/route bucket, method, authentication-presence và reason code đã allowlist; tránh in JWT để xem `roles`.
- Tái hiện với token test/user fixture có role tương đương và path/method tương ứng.
- Đối chiếu `CSRF_INVALID` với `AUTHZ_MISSING_AUTHORITY`: hai hướng sửa khác nhau.
- Rollback sang bản **đã kiểm chứng không mở quyền**, hoặc hotfix đúng matcher/role; chạy negative tests với principal không đủ quyền.
- Không sửa bằng `permitAll`, `web.ignoring`, tắt CSRF hoặc cấp ADMIN tạm cho tất cả user.

### 19.2. “JWT hết hạn, người dùng bị logout”

- Kiểm expiry/issuer/audience, thời gian hệ thống, JWKS cache và rotation; phân biệt **token invalid** với **identity không có quyền**.
- Chỉ ghi reason code/metadata key version được phép; không log JWT raw, refresh token hay Authorization header.
- Nếu key rotation lệch, điều phối JWKS/issuer theo chính sách overlap; không phát private key cho resource servers.
- Nếu token compromise, revoke/rotate theo incident procedure, không gia hạn toàn cục hoặc bỏ signature verification.

### 19.3. “Cookie phiên không đi tới API”

- Kiểm `Set-Cookie` attributes nhưng không ghi cookie value: `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path`, expiry.
- Kiểm browser `fetch(credentials: "include")`, CORS, HTTPS, proxy host/scheme và session store.
- Dùng `getSession(false)` khi quan sát, không tạo session mới trong logger.
- Không tắt `HttpOnly`, `Secure` hay CSRF để browser “dùng được cookie”.
- Nếu app stateless Bearer, request không có session có thể là đúng thiết kế.

### 19.4. “User đọc được document không sở hữu”

- Ưu tiên containment: chặn hành động/route bị khai thác **có phạm vi**, không mở thêm quyền.
- Kiểm route authn/role, service ownership/tenant predicate, repository query, cache key và các đường list/export/file.
- Audit theo policy và metadata giảm định danh; xác định resource/caller thật trong **forensic store có RBAC**, không dump vào log chung.
- Thêm test Alice/Bob/cross-tenant, kiểm truy cập trực tiếp bằng HTTP, no-side-effect cho PATCH/DELETE.
- Xác định dữ liệu đã rò, thông báo bộ phận pháp lý/bảo mật theo chính sách; không che giấu sự cố chỉ bằng ẩn nút frontend.

### 19.5. “Log đã chứa session cookie hoặc client secret”

- Hạn chế truy cập hệ thống log, giữ bằng chứng theo quy trình ứng cứu, xác định nguồn phát tán và copies.
- Rotate/revoke bị ảnh hưởng, logout/invalidate sessions cần thiết, điều tra truy cập log và credential abuse.
- Sửa logger/redaction ở nguồn; kiểm cả ingress/APM/CI backups.
- Không dán mẫu secret thật vào PR/ticket để giải thích; dùng field name, checksum/fingerprint được phê duyệt hoặc marker test.
- Làm sạch log/history chỉ theo retention và forensic policy; **xóa log không thu hồi secret đã lộ**.

## 20. Checklist review trước khi bật công cụ chẩn đoán

1. Có ticket/incident ID và người chịu trách nhiệm? Mục tiêu điều tra cụ thể là gì?
2. Có thể trả lời bằng metric/event code/request ID hiện có thay vì bật payload dump không?
3. Có thay đổi authn/authz/CSRF/session/proxy/WAF/rate limit nào **làm yếu** policy không? Nếu có, phải từ chối cách tiếp cận đó.
4. Field nào thực sự cần? Có chứa token, cookie, email, URL query, raw body, `Authentication` object hay key không?
5. Input có thể chứa newline/log forging hoặc giá trị do client cố tình kiểm soát không?
6. Route/method/status đã chuẩn hóa và giới hạn cardinality chưa?
7. Logs có RBAC, encryption, retention, audit người xem và TTL instrumentation không?
8. Có phương án chạy với tài khoản/fixture giả và test scenario âm/dương không?
9. Có monitoring để phát hiện sai lệch quyền hoặc secret leakage ngay sau rollout không?
10. Với quyền break-glass (nếu buộc phải có), có MFA, dual approval theo policy, JIT TTL, scope hẹp và revoke không?
11. Có kiểm chính sách Actuator, proxy, tracing, APM, CI artifacts và exception responses không?
12. Có lịch gỡ instrumentation và người xác nhận sau incident không?

## 21. Câu hỏi tự kiểm tra

1. Vì sao `anyRequest().permitAll()` không phải cách debug hợp lệ khi một endpoint trả 403?
2. Nếu `POST` trả 403, làm thế nào phân biệt thiếu CSRF với thiếu role **mà không tắt CSRF**?
3. Vì sao raw `request.getRequestURI()` và `request.getQueryString()` có thể chứa bí mật dù không log headers?
4. Tại sao không dùng `JSESSIONID` hoặc `X-Request-ID` do client cung cấp làm request correlation ID đáng tin?
5. Nếu một `SecurityFilterChain` có `securityMatcher("/api/**")`, nó có bảo vệ `/internal/**` không? Cần kiểm gì?
6. Điều gì nguy hiểm khi log `Authentication.toString()` hoặc `@ConfigurationProperties` object?
7. “Có 403” có chứng minh request bị từ chối **trước khi thay đổi dữ liệu** không? Test cần làm gì?
8. Vì sao không thể dựa vào Spring Boot Actuator sanitization làm biện pháp duy nhất?
9. Khi một client secret đã xuất hiện trong CI logs, vì sao xóa log hoặc ẩn dòng trong ticket vẫn chưa đủ?
10. Trong tình huống cần khôi phục khẩn cấp, break-glass phải khác `ROLE_ADMIN` dùng chung ở những điểm nào?
11. Test `CapturedOutput` cho marker giả có phạm vi và giới hạn gì? Lớp hạ tầng nào cần kiểm riêng?
12. Nếu rollback làm biến mất lỗi 401 nhưng khôi phục một lỗ hổng BOLA, tại sao đó không phải rollback an toàn?
13. Vì sao `logging.level.org.springframework.security=TRACE` trong production cần đánh giá rủi ro và TTL thay vì bật vô hạn?
14. Với sự cố browser gửi cookie sai, bạn cần bằng chứng `Cookie`/session-present nào **không lộ giá trị cookie**?
15. Khi user báo không truy cập được tài liệu thuộc tenant khác, đâu là bằng chứng cho thấy policy đang hoạt động đúng?

**Kết luận:** trong một sự cố Spring Security, cách xử lý đáng tin là **giữ nguyên giới hạn quyền, tăng quan sát bằng tín hiệu tối thiểu đã giảm định danh, tái hiện bằng dữ liệu giả, sửa đúng nguyên nhân và xác minh bằng test âm/dương**. Không đánh đổi bảo mật dữ liệu lấy sự tiện lợi gỡ lỗi: raw secrets không thuộc logs, và “mở quyền tạm” không phải một công cụ quan sát.

## Tài liệu tham khảo chính thức

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Exception Handling / Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — Testing with MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Boot 3.5 — Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP — Incident Response Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Incident_Response_Cheat_Sheet.html)
