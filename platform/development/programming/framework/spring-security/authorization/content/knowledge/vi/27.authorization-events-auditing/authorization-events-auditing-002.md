# AuthorizationDeniedEvent và dữ liệu phục vụ điều tra

Trong Spring Security, một yêu cầu bị từ chối thường được nhìn thấy dưới dạng **HTTP 403**, **HTTP 401** hoặc một `AccessDeniedException`. Đối với vận hành hệ thống, chỉ biết mã HTTP là chưa đủ: phải trả lời được **ai** yêu cầu, **tài nguyên hoặc thao tác nào** bị chặn, **lớp kiểm soát nào** đưa ra quyết định và **request/trace nào** nối sự kiện đó với log ứng dụng. `AuthorizationDeniedEvent` là một điểm móc quan trọng để thu thập bằng chứng của quyết định **authorization bị từ chối** ở Spring Security.

Bài thuộc nhóm **Sự kiện và audit** trong module **Spring Security - authorization**. Ví dụ sử dụng **Spring Boot 3.5.x, Spring Security 6.x (Servlet), Java 17+**. Cơ chế sự kiện có thể xuất hiện trong cả servlet HTTP authorization và method security; chi tiết API cụ thể cần kiểm tra theo phiên bản đang sử dụng.

## 1. Kết quả học tập

Sau khi học, bạn có thể:

- Mô tả thời điểm và vai trò của `AuthorizationDeniedEvent`, `AuthorizationEventPublisher` và `SpringAuthorizationEventPublisher`.
- Phân biệt một **quyết định bị từ chối**, một **exception**, một **HTTP response**, một **authentication failure** và một **bản ghi audit bền vững**.
- Đọc các dữ liệu chính từ `AuthorizationDeniedEvent`; xác định phần nào phải lấy thêm từ request, SecurityContext, MDC/tracing hoặc chính sách nghiệp vụ.
- Tạo listener có thể thực thi để ghi nhận HTTP và method denial; kết nối `requestId` với kết quả quan sát.
- Thiết kế audit log có ích khi điều tra nhưng tránh ghi mật khẩu, token, cookie, body, tham số nhạy cảm và đối tượng Java thô.
- Kiểm thử các ca 401/403, phân biệt denial từ rule truy cập với CSRF, thất bại xác thực và từ chối không đi qua cơ chế publish sự kiện.

## 2. AuthorizationDeniedEvent thực sự biểu thị điều gì?

`AuthorizationDeniedEvent<T>` thuộc package `org.springframework.security.authorization.event`, là một Spring `ApplicationEvent` báo rằng một phép kiểm tra quyền đã trả kết quả **không cho phép**. Sự kiện lưu thông tin về yêu cầu kiểm tra, **không** phải một bản mô tả hoàn chỉnh về cuộc gọi HTTP hay toàn bộ lý do điều tra.

Luồng khái niệm:

```text
HTTP request / lời gọi method
          |
          v
AuthorizationManager kiểm tra quyền
          |
          +--> Granted: tiếp tục thực thi
          |      (sự kiện granted KHÔNG được publish mặc định)
          |
          +--> Denied: AuthorizationEventPublisher
                     |
                     v
              AuthorizationDeniedEvent
                     |
                     +--> @EventListener -> audit/log/metric
                     |
                     v
              Chặn lời gọi hoặc ném exception
                     |
                     v
              Xử lý phản hồi phù hợp (401/403...)
```

Sự kiện được phát **tại quyết định authorization**. Trả lời HTTP được hình thành ở một lớp khác, tùy người gọi đã xác thực hay chưa và cấu hình `AuthenticationEntryPoint` / `AccessDeniedHandler`. Do đó:

- `AuthorizationDeniedEvent` **không đồng nghĩa** với “đã trả HTTP 403”. Với người dùng anonymous, một denial có thể khởi động quy trình xác thực và cuối cùng trả **401** (API Basic/Bearer) hoặc **302** tới trang đăng nhập.
- `AuthorizationDeniedEvent` **không phải** `AuthenticationFailureEvent`. Sai mật khẩu/invalid token thường được xử lý trong quá trình authentication; không nên đếm những lỗi đó thành quyết định thiếu quyền, trừ khi thực tế còn có một phép authorization bị từ chối.
- `AuthorizationDeniedEvent` **không phải** `AuditEvent` của Spring Boot Actuator. Nó là một event trong tiến trình; nếu chỉ có listener ghi console, không có bảo đảm lưu lâu dài, tra cứu, phân quyền truy cập hay tính bất biến.
- Không phải **mọi HTTP 403** đều bắt nguồn từ `AuthorizationDeniedEvent`: ví dụ kiểm tra CSRF thất bại, filter tùy biến, lỗi gateway hay mã lỗi do controller tự trả.

## 3. Thành phần và điều kiện phát sự kiện

### 3.1. Bộ phát sự kiện

`AuthorizationEventPublisher` là giao diện mà thành phần kiểm soát quyền dùng để phát sự kiện. `SpringAuthorizationEventPublisher` tích hợp với Spring `ApplicationEventPublisher`; cài đặt tiêu chuẩn của Spring Security phát **denial event** theo mặc định, không phát tất cả grant vì số lượng có thể rất lớn.

Đăng ký bean publisher rõ ràng:

```java
@Bean
AuthorizationEventPublisher authorizationEventPublisher(
        ApplicationEventPublisher applicationEvents) {
    return new SpringAuthorizationEventPublisher(applicationEvents);
}
```

Khi các thành phần authorization sử dụng publisher đã cấu hình, bạn có thể lắng nghe:

```java
@EventListener
public void onDenied(AuthorizationDeniedEvent<?> event) {
    // Chọn các trường audit cho phép; đừng serialize nguyên event.
}
```

**Điểm phải xác minh khi tích hợp:** có bean publisher và có listener mới chỉ là điều kiện cần. Bộ phận thực thi authorization phải thực sự đưa quyết định đến publisher. `AuthorizationFilter` hỗ trợ `setAuthorizationEventPublisher(...)` và hệ thống method authorization có cơ chế publish event. Nếu thay bằng filter, manager hoặc cơ chế legacy tùy biến, hãy kiểm thử đường đi cụ thể thay vì suy luận rằng mọi denial chắc chắn phát event.

Với Spring Security 6.x, có thể tạo `AuthorizationDeniedEvent` từ `AuthorizationResult`; các API xoay quanh `AuthorizationDecision` cũ có phiên bản đã bị deprecated. Mã mới nên dùng `getAuthorizationResult()` và `isGranted()`, không phụ thuộc API deprecated để xây audit.

### 3.2. Servlet authorization và method authorization

**Ở HTTP URL:** `AuthorizationFilter` gọi `AuthorizationManager<HttpServletRequest>` để kiểm tra các rule từ `authorizeHttpRequests`. Object trong denial event thường là `HttpServletRequest`. Listener có thể nhận biết HTTP method, request URI và context tại thời điểm request; tuy nhiên cần loại bỏ dữ liệu nhạy cảm trước khi log.

**Ở method security:** khi bật `@EnableMethodSecurity`, interceptor có thể thực thi `@PreAuthorize` / `@PostAuthorize`. Một denial có thể mang `MethodInvocation` hoặc kiểu object dành cho method invocation/result tùy thời điểm kiểm tra. Để có định danh an toàn, lấy **tên class và method**, tránh ghi nguyên `getArguments()` hay object trả về vì thường chứa dữ liệu nghiệp vụ.

**Một request có thể có nhiều điểm kiểm tra:** authorization ở URL, sau đó ở service, rồi ở object-level. Số event không nhất thiết bằng số request, số người dùng hay số phản hồi 403. Nếu request bị chặn ngay ở filter trước controller, method security chưa hề được gọi.

## 4. API của event: dữ liệu nào thật sự có?

| Dữ liệu / API | Ý nghĩa | Giới hạn điều tra |
| --- | --- | --- |
| `event.getAuthentication()` | `Supplier<Authentication>` liên quan đến quyết định; cần gọi `.get()` để truy cập `Authentication` khi phù hợp | Có thể là anonymous; credential/principal trong đối tượng có thể nhạy cảm |
| `event.getObject()` | Đối tượng đang được kiểm soát truy cập, kiểu `T` | Có thể là `HttpServletRequest`, `MethodInvocation` hay một object khác; không an toàn để serialize nguyên bản |
| `event.getAuthorizationResult()` | Kết quả authorization; `isGranted()` là `false` với denied event | Không nhất thiết chứa “tên policy”, quyền bị thiếu, lý do nghiệp vụ hay status HTTP |
| `event.getTimestamp()` | Thời điểm tạo Spring `ApplicationEvent` (milliseconds từ epoch) | Không phải timestamp hoàn tất HTTP response, cũng không phải thời điểm ghi bản ghi bền vững |
| `event.getSource()` | Phần source kế thừa từ Spring event | Không nên coi là tài liệu log an toàn; dùng API typed phía trên |

Phần lớn dữ liệu điều tra cần **enrichment** từ nguồn khác: server-generated request ID, trace/span ID, route template, tên policy hoặc mã rule do ứng dụng định nghĩa, tenant/resource ID đã kiểm tra quyền, phiên bản policy, actor ID nội bộ, HTTP response status sau khi xử lý, service name và môi trường chạy.

**Không tự suy diễn nguyên nhân cụ thể** từ `isGranted() == false`. Có thể do thiếu quyền, ownership/tenant rule, trạng thái resource, policy tùy chỉnh hoặc điều kiện dữ liệu khác. Nếu ứng dụng muốn ghi `reasonCode`, hãy thiết kế nó trong policy layer theo một contract có kiểm soát; `AuthorizationDeniedEvent` mặc định không có thuộc tính `getReason()` phổ quát.

## 5. Ví dụ runnable: phát sự kiện và ghi log denial có correlation ID

Ví dụ dùng HTTP Basic để chủ động thử bằng `curl`. Có hai chính sách:

- `GET /api/admin/reports` chỉ cho `ROLE_ADMIN`: denial xảy ra ở **HTTP filter**.
- `GET /api/reports/export` yêu cầu đã xác thực ở URL, nhưng phương thức service yêu cầu authority `REPORT_EXPORT`: denial xảy ra ở **method security**.

Một servlet filter cấp `X-Request-Id` và đặt cùng ID vào SLF4J MDC. Listener chỉ ghi route/policy được chuẩn hóa, actor demo và tên loại object; nó không dump headers, principal hay request body.

### 5.1. Tệp pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>authorization-audit</artifactId>
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

### 5.2. Tệp src/main/java/com/example/audit/AuthorizationAuditApplication.java

```java
package com.example.audit;

import java.io.IOException;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.aopalliance.intercept.MethodInvocation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.context.event.EventListener;
import org.springframework.security.access.prepost.PreAuthorize;

@SpringBootApplication
@EnableMethodSecurity
public class AuthorizationAuditApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthorizationAuditApplication.class, args);
    }

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher events) {
        return new SpringAuthorizationEventPublisher(events);
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password("{noop}reader123")
                        .authorities("ROLE_USER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}admin123")
                        .authorities("ROLE_ADMIN", "REPORT_EXPORT")
                        .build());
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .requestMatchers("/api/admin/reports").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class ReportController {

        private final ReportService reportService;

        ReportController(ReportService reportService) {
            this.reportService = reportService;
        }

        @GetMapping("/api/public")
        Map<String, String> publicEndpoint() {
            return Map.of("result", "public");
        }

        @GetMapping("/api/admin/reports")
        Map<String, String> adminReports() {
            return Map.of("result", "admin-only");
        }

        @GetMapping("/api/reports/export")
        Map<String, String> export() {
            return reportService.export();
        }
    }

    @Service
    static class ReportService {

        @PreAuthorize("hasAuthority('REPORT_EXPORT')")
        public Map<String, String> export() {
            return Map.of("result", "export-ready");
        }
    }

    // Filter ở ngoài Spring Security filter chain để correlation
    // áp dụng cả khi authentication từ chối trước authorization.
    @Component
    @Order(Ordered.HIGHEST_PRECEDENCE)
    static class CorrelationIdFilter extends OncePerRequestFilter {

        @Override
        protected void doFilterInternal(
                HttpServletRequest request, HttpServletResponse response,
                FilterChain chain) throws ServletException, IOException {
            String requestId = UUID.randomUUID().toString();
            response.setHeader("X-Request-Id", requestId);
            MDC.put("requestId", requestId);
            try {
                chain.doFilter(request, response);
            } finally {
                MDC.remove("requestId");
            }
        }
    }

    @Component
    static class DeniedAuditListener {

        private static final Logger log =
                LoggerFactory.getLogger(DeniedAuditListener.class);

        @EventListener
        public void onDenied(AuthorizationDeniedEvent<?> event) {
            Authentication auth = event.getAuthentication().get();
            String actor = (auth == null
                    || auth instanceof AnonymousAuthenticationToken)
                    ? "anonymous" : auth.getName();

            Object securedObject = event.getObject();
            String layer;
            String resource;

            if (securedObject instanceof HttpServletRequest request) {
                layer = "HTTP";
                // Ghi nhãn route an toàn, tránh log URI chứa ID/PII.
                resource = request.getRequestURI()
                        .startsWith("/api/admin/")
                        ? "api.admin" : "api.other";
            } else if (securedObject instanceof MethodInvocation invocation) {
                layer = "METHOD";
                resource = invocation.getMethod().getDeclaringClass()
                        .getSimpleName()
                        + "#" + invocation.getMethod().getName();
            } else {
                layer = "OTHER";
                resource = "secured-object";
            }

            // Mẫu học tập: actor là username demo đã kiểm soát.
            // Trong production nên dùng internal actor ID hoặc bí danh.
            log.warn(
                    "event=authorization_denied at={} requestId={} "
                    + "actor={} layer={} resource={} granted={}",
                    Instant.ofEpochMilli(event.getTimestamp()),
                    MDC.get("requestId"),
                    actor,
                    layer,
                    resource,
                    event.getAuthorizationResult().isGranted());
        }
    }
}
```

**Vì sao mã này có ý nghĩa?**

1. `@Bean AuthorizationEventPublisher` nối authorization event với Spring application events. Listener dùng `@EventListener` để xử lý `AuthorizationDeniedEvent<?>`.
2. `@EnableMethodSecurity` kích hoạt kiểm tra `@PreAuthorize` trên service bean. Controller **gọi qua bean được Spring quản lý**, giúp AOP interceptor thực thi; tự gọi một method cùng object có thể bỏ qua proxy.
3. Chính sách HTTP kiểm tra `/api/admin/reports` trước khi controller được gọi. `reader` bị từ chối ở `AuthorizationFilter`.
4. Chính sách của `/api/reports/export` ở tầng URL chỉ yêu cầu xác thực; người dùng `reader` vượt qua URL check rồi bị chặn ở `ReportService#export` do thiếu `REPORT_EXPORT`.
5. Filter tạo ID ở server, ghi vào MDC và header để người điều tra đối chiếu cùng một request. `finally` dọn MDC, tránh rò dữ liệu sang request khác khi servlet thread được tái sử dụng.
6. Listener kiểm tra kiểu object trước khi lấy thông tin; không gọi `securedObject.toString()`, không ghi method arguments hoặc toàn bộ `Authentication`. Với hệ thống thật, mở rộng theo danh sách field an toàn và quy tắc bảo vệ dữ liệu tại mục 7.
7. Tài khoản `{noop}` và HTTP Basic chỉ dành cho demo cục bộ. Bản thực phải dùng lưu trữ mật khẩu mã hóa/identity provider thích hợp, TLS, cơ chế auth tương ứng và chính sách CSRF đúng mô hình credential.

### 5.3. Chạy và kiểm tra

Đặt `pom.xml` và tệp Java tại đúng đường dẫn trên. Với JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Maven chạy và biên dịch ứng dụng với dependencies Spring; không thể chỉ `javac AuthorizationAuditApplication.java` nếu không cung cấp classpath đầy đủ.

Thử các ca:

```bash
# Không credential: HTTP Basic yêu cầu xác thực (thường HTTP 401).
curl -i http://localhost:8080/api/admin/reports

# Đã xác thực, thiếu ROLE_ADMIN: HTTP 403, denial ở HTTP.
curl -i -u reader:reader123 http://localhost:8080/api/admin/reports

# Đã xác thực, thiếu REPORT_EXPORT: HTTP 403, denial ở method.
curl -i -u reader:reader123 http://localhost:8080/api/reports/export

# Đã đủ quyền: HTTP 200.
curl -i -u admin:admin123 http://localhost:8080/api/admin/reports
curl -i -u admin:admin123 http://localhost:8080/api/reports/export

# Sai mật khẩu: HTTP 401 do authentication thất bại.
curl -i -u reader:wrong http://localhost:8080/api/reports/export

# Endpoint công khai: HTTP 200.
curl -i http://localhost:8080/api/public
```

Hai phản hồi thành công có body JSON chính xác theo controller:

```json
{"result":"admin-only"}
```

```json
{"result":"export-ready"}
```

Log minh họa (timestamp, requestId và tiền tố log thay đổi mỗi lần chạy):

```text
event=authorization_denied at=2026-11-05T10:00:00Z requestId=<server-generated-id> actor=reader layer=HTTP resource=api.admin granted=false
event=authorization_denied at=2026-11-05T10:01:00Z requestId=<server-generated-id> actor=reader layer=METHOD resource=ReportService#export granted=false
```

**Đây là log minh họa, không phải stdout cố định.** Với Basic/HTTP, `401` thường kèm header `WWW-Authenticate`; listener không biết HTTP status cuối chỉ từ event. Đối chiếu `X-Request-Id` từ response với `requestId` trong log.

### 5.4. Kiểm thử tự động bằng MockMvc và Spring ApplicationEvents

Tệp `src/test/java/com/example/audit/AuthorizationAuditApplicationTests.java`:

```java
package com.example.audit;

import jakarta.servlet.http.HttpServletRequest;
import org.aopalliance.intercept.MethodInvocation;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@RecordApplicationEvents
class AuthorizationAuditApplicationTests {

    @Autowired MockMvc mvc;
    @Autowired ApplicationEvents events;

    @Test
    @WithMockUser(roles = "USER")
    void urlDenialPublishesEvent() throws Exception {
        mvc.perform(get("/api/admin/reports"))
                .andExpect(status().isForbidden());

        assertTrue(events.stream(AuthorizationDeniedEvent.class)
                .anyMatch(event ->
                        event.getObject() instanceof HttpServletRequest));
    }

    @Test
    @WithMockUser(roles = "USER")
    void methodDenialPublishesEvent() throws Exception {
        mvc.perform(get("/api/reports/export"))
                .andExpect(status().isForbidden());

        assertTrue(events.stream(AuthorizationDeniedEvent.class)
                .anyMatch(event ->
                        event.getObject() instanceof MethodInvocation));
    }
}
```

Chạy:

```bash
mvn test
```

Hai phép kiểm thử xác minh **có sự kiện** ở lớp URL và method; chúng không phụ thuộc vào chuỗi log hoặc UUID ngẫu nhiên. Khi mở rộng, thêm test cho anonymous, admin, authentication sai, CSRF, route pattern và policy đặc thù. Nếu custom manager/filter không sử dụng publisher, test này sẽ phát hiện mất sự kiện.

## 6. Thiết kế dữ liệu audit để điều tra được sự cố

Đừng gửi nguyên event vào Elasticsearch, Kafka hoặc bảng dữ liệu. Nên chuyển thành một **audit record có schema rõ ràng** và kiểm soát field. Ví dụ schema:

| Field | Nguồn đáng tin | Giá trị điều tra |
| --- | --- | --- |
| `eventId` | UUID của hệ thống audit | Phân biệt bản ghi, xử lý ghi trùng |
| `occurredAt` | `event.getTimestamp()` hoặc đồng hồ quan sát | Sắp xếp dòng thời gian UTC |
| `requestId`, `traceId`, `spanId` | Middleware/tracing do server tạo | Nối gateway → security → service → DB |
| `service`, `environment`, `instance` | Cấu hình triển khai | Xác định pod/service/version |
| `actorId` | Identity nội bộ/subject đã chuẩn hóa | Xác định danh tính bằng quyền truy cập kiểm soát; không đưa token |
| `authenticationType` | Thông tin xác thực đã chuẩn hóa | Phân biệt anonymous, session, API key, Bearer... |
| `tenantId` | Tenant context đã được xác thực | Phân biệt từ chối cross-tenant |
| `layer` | HTTP / METHOD / POLICY | Xác định lớp chặn |
| `resourceType`, `resourceId` | Route template, domain resource metadata | Phân biệt endpoint và tài nguyên; ID có thể cần pseudonymization |
| `action` | GET/POST hoặc operation code | Hành động được yêu cầu |
| `policyId`, `policyVersion` | Chính sách do ứng dụng quản lý | Giải thích tác động khi thay đổi rule |
| `decision` | `AuthorizationResult.isGranted()` | `DENY` cho event này |
| `reasonCode` | Logic authorization riêng của ứng dụng | Lý do chuẩn hóa như `MISSING_AUTHORITY` hoặc `CROSS_TENANT` nếu thật sự được biết |
| `httpStatus` | Quan sát phản hồi sau cùng | Đối chiếu 401/403/redirect; **không có sẵn trong event** |
| `clientIp` | Edge/proxy chain đáng tin cậy, nếu được phép lưu | Điều tra hành vi mạng; không tin mù quáng `X-Forwarded-For` từ client |

Một bản ghi **đã được chuẩn hóa** có thể trông như sau; giá trị đều mang tính minh họa:

```json
{
  "eventId": "35fc6115-6f39-4702-bcdc-3af94f8d75aa",
  "eventType": "AUTHORIZATION_DENIED",
  "occurredAt": "2026-11-05T10:01:00Z",
  "service": "report-api",
  "environment": "staging",
  "requestId": "c5e6e50f-6f69-4d56-9ab3-8d2d0ea6a14b",
  "traceId": "7b9a2240924d7b4e918acde701682071",
  "actorId": "user-42",
  "tenantId": "tenant-7",
  "layer": "METHOD",
  "resourceType": "REPORT_EXPORT",
  "action": "EXPORT",
  "policyId": "report.export.permission",
  "policyVersion": "2026-11-01",
  "decision": "DENY",
  "reasonCode": "MISSING_AUTHORITY",
  "httpStatus": 403
}
```

**Phân biệt nguồn dữ liệu:** đoạn Java runnable bên trên chỉ ghi một tập field tối thiểu. JSON vừa nêu là **mẫu schema mục tiêu**; nó không phải payload sẵn có của `AuthorizationDeniedEvent`. Các field như `tenantId`, `reasonCode`, `policyVersion`, `httpStatus` đòi hỏi instrumentation, policy domain và đường ghi audit riêng.

### Chú ý khi ghi thông tin nhạy cảm

- **Không log** `Authorization` header, Bearer token, Basic credential, cookie phiên, password, OTP, secret, toàn bộ JWT claims, request/response body hoặc method arguments theo mặc định.
- **Không serialize trực tiếp** `HttpServletRequest`, `Authentication`, `Principal`, `MethodInvocation`, entity/domain object hoặc exception stack trace vào audit record. Chúng có thể chứa thông tin cá nhân, credential và object graph rất lớn.
- Với URL có ID nhạy cảm, dùng `route template` (ví dụ `/orders/{id}`) thay vì raw `/orders/123456`; ID cần thiết cho điều tra phải được phân loại và bảo vệ.
- Tên đăng nhập/IP có thể là dữ liệu cá nhân. Chỉ giữ dữ liệu cần thiết, pseudonymize nếu phù hợp và tách quyền đọc log bảo mật khỏi người vận hành thông thường.
- Tránh **log injection**: dữ liệu do user kiểm soát có thể chứa xuống dòng/ký tự điều khiển. Sử dụng structured logging, encode/sanitize chuỗi và giới hạn độ dài.
- Đừng lấy `X-Request-Id` hoặc `X-Forwarded-For` từ client làm nguồn tin mặc định. Edge đáng tin có thể phát lại/chuẩn hóa chúng; nếu không, tự sinh ID ở server.
- Định nghĩa thời hạn giữ, phân quyền đọc, mã hóa lưu trữ/vận chuyển, xóa theo chính sách, cảnh báo và audit việc truy cập chính kho audit.

## 7. Điều tra một sự cố bị từ chối: quy trình thực tế

**Tình huống:** người dùng báo “tôi vừa được cấp quyền xuất báo cáo nhưng API vẫn trả 403”.

1. **Xác nhận dấu vết:** lấy thời điểm UTC, endpoint, method, request ID/trace ID từ response hoặc telemetry, service và môi trường. Tránh yêu cầu người dùng gửi credential/token.
2. **Tìm event:** lọc `AUTHORIZATION_DENIED` theo `requestId` và thời gian. Kiểm tra có event hay không, `layer` và tên resource/policy. Không suy luận từ mỗi status 403.
3. **Xác nhận danh tính:** kiểm tra actor/tenant trong hệ thống identity, quyền đã phát cho **request đó** chứ không chỉ trạng thái hiện tại. Token có thể mang claim cũ, user cache có thể chưa refresh.
4. **Đối chiếu rule:** kiểm tra `hasRole` vs `hasAuthority`, tiền tố `ROLE_`, chính sách object-level, tenant ownership, policy version, thời điểm rollout và các feature flag liên quan. Kết quả `DENY` một mình không chỉ rõ rule nào.
5. **Phân biệt tầng chặn:** `HTTP` cho thấy request bị chặn trước controller; `METHOD` cho thấy request đã vào ứng dụng và interceptor method từ chối; `OTHER` cần phân loại thêm.
6. **Đối chiếu output:** qua cùng `requestId`, kiểm tra log auth, audit ở policy layer, gateway, CORS/CSRF và status cuối. Nếu là `401`, xem authentication; nếu 403 nhưng không thấy event, kiểm tra bộ phận khác tạo 403.
7. **Lập kết luận có bằng chứng:** ghi nguyên nhân có thể xác minh, nguồn log, rule/version đã đối chiếu, thời điểm quyền được đổi và hành động khắc phục. Không “sửa” bằng cách mở rộng quyền khi chưa hiểu chính sách.
8. **Xác minh sau sửa:** tái hiện cùng loại request trong môi trường phù hợp, kiểm tra status, event/log/correlation ID và kiểm thử hồi quy không cấp quyền ngoài ý muốn.

Ví dụ suy luận hợp lệ:

```text
Request A -> 403
Audit: layer=METHOD, resource=ReportService#export, actor=user-42
Policy: REPORT_EXPORT required, effective authorities did not include it
Identity: role change applied after token was issued
=> Có bằng chứng về claim/authority cũ trong request A;
   cần kiểm tra quy trình refresh/re-issue token và cache của authorization.
```

Đây là ví dụ điều tra, **không** phải kết luận áp dụng cho mọi sự cố 403. Nếu dữ liệu authority tại thời điểm request không được ghi an toàn, cần nguồn identity/token validation telemetry đáng tin; không suy luận chắc chắn từ role hiện tại.

## 8. Những trường hợp dễ gây hiểu nhầm

| Quan sát | Có nhất thiết có AuthorizationDeniedEvent? | Hướng kiểm tra |
| --- | --- | --- |
| Caller anonymous gọi API cần đăng nhập, trả 401 | Có thể có khi URL authorization đưa ra quyết định denial | Authentication entry point, anonymous filter, rule và publisher |
| Caller có tài khoản nhưng thiếu `ROLE_ADMIN`, trả 403 | Thường có với `AuthorizationFilter` + publisher | Route matcher, authority, event HTTP |
| `@PreAuthorize` từ chối service method | Có khi method interceptor active và publisher hoạt động | `@EnableMethodSecurity`, Spring proxy, event method |
| Sai Basic password hoặc Bearer token hết hạn | Không phải một `AuthorizationDeniedEvent` bảo đảm | Authentication events, failure handler/token validator |
| POST thiếu CSRF token, trả 403 | Không nhất thiết | `CsrfFilter` và CSRF token strategy |
| Controller tự trả `ResponseEntity.status(403)` | Không tự tạo authorization event | Controller/business path; cần audit nghiệp vụ riêng |
| Gateway/WAF/nginx từ chối trước khi tới Spring | Spring app không nhìn thấy request | Edge/gateway audit và trace |
| Dùng custom `AccessDeniedHandler` | Handler thay đổi phản hồi, không tự đảm bảo sự kiện | Kiểm tra nơi ra quyết định và publisher |

**Vắng event không chứng minh request được phép**; có thể request đã bị chặn trước authorization, listener chưa đăng ký, publisher chưa được wire, method security bị bypass, event bị rơi khi lưu/đẩy hoặc chưa có correlation ID.

**Có event cũng không đủ để kết luận có sự cố bảo mật:** một loạt denial có thể là kiểm thử quyền bình thường, request của client lỗi cấu hình hoặc tấn công dò quyền. Cần mẫu tần suất, actor, tenant, route, nguồn mạng đáng tin, thay đổi policy và các tín hiệu khác.

## 9. Audit reliability, performance và threat model

Spring `@EventListener` với multicaster mặc định thường xử lý **đồng bộ** ngay trong luồng publish. Listener thực hiện truy vấn DB chậm, gọi HTTP tới SIEM hoặc ghi network blocking có thể tăng latency request. Một listener ném exception không kiểm soát cũng có nguy cơ ảnh hưởng request tùy cấu hình publisher/multicaster.

- Giữ handler nhẹ: ánh xạ những field cần thiết, chuẩn hóa, đưa vào logging/sink có backpressure phù hợp. Nếu yêu cầu lưu bền vững, cân nhắc hàng đợi đáng tin, retry có giới hạn, dead-letter queue và khả năng phát hiện mất event.
- Chọn mức cam kết dữ liệu rõ ràng: **best-effort log** khác với audit có retention/bằng chứng phục vụ compliance. Không tuyên bố “mọi denial đã lưu” nếu hệ thống chưa có xác nhận ghi, giám sát lỗi và chính sách khi sink lỗi.
- Với xử lý async, không mặc định MDC, SecurityContext hoặc servlet request tự lan sang thread khác. Snapshot dữ liệu an toàn **trước khi enqueue**, và propagate tracing context theo cơ chế được hỗ trợ.
- Bảo vệ hệ thống trước denial storm: rate-limit/aggregation/alert dựa trên chiều phân tích phù hợp; tránh publish granted events tràn ngập. Nếu sampling denial để giảm tải, phải công khai ảnh hưởng đến tính đầy đủ của audit.
- Không phát log chứa toàn bộ policy evaluation state; các điều kiện rule có thể chứa dữ liệu nhạy cảm. Chỉ đưa vào event code đã được phân loại và cho phép.
- Đồng bộ thời gian giữa hệ thống và ghi cả `occurredAt` lẫn thời điểm ingestion nếu cần phân tích trễ truyền/queue.

## 10. Checklist kiểm thử và vận hành

Trước khi coi việc thu thập denial đã hoàn chỉnh, xác nhận:

- [ ] Publisher được đăng ký và đường HTTP/method đang dùng thực sự gọi nó.
- [ ] `@EventListener` nhận sự kiện cho deny từ URL và từ `@PreAuthorize`; test xác nhận **loại secured object**, không chỉ test status.
- [ ] `permitAll` và request có đủ quyền không bị đếm nhầm thành denied; không bật grant event đại trà.
- [ ] Anonymous, 401, 403, sai credential, CSRF, custom error path được phân loại bằng bằng chứng.
- [ ] Một request có nhiều kiểm tra không dẫn đến tính sai số người bị chặn hoặc số request duy nhất.
- [ ] Correlation ID server-generated xuất hiện trong response và audit; tracing vẫn hoạt động qua proxy theo trust boundary.
- [ ] Không ghi credential, header nhạy cảm, payload, raw object, raw dynamic URL hay PII không cần thiết.
- [ ] Role/authority/tenant, policy version, reason code được lấy từ nguồn thực; không gán nguyên nhân mặc định cho mọi denial.
- [ ] Có ngưỡng cảnh báo, retention, phân quyền đọc, cơ chế xử lý sink lỗi và cách xác minh end-to-end.
- [ ] Chạy `mvn test` và thực hiện các request mẫu trong môi trường thử nghiệm; kiểm tra cả audit và HTTP response thực tế.

## 11. Tài liệu tham khảo chính thức

- Spring Security: [Authorization Events](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html) — cách đăng ký publisher, listener và lý do grant không mặc định được phát.
- Spring Security: [AuthorizationDeniedEvent API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/event/AuthorizationDeniedEvent.html) — secured object và kiểu dữ liệu sự kiện.
- Spring Security: [AuthorizationEvent API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/event/AuthorizationEvent.html) — authentication supplier, authorization result, timestamp.
- Spring Security: [Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) — `@EnableMethodSecurity` và denied event ở method interceptor.
- Spring Security: [AuthorizationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/intercept/AuthorizationFilter.html) — `setAuthorizationEventPublisher`.
- Spring Security: [Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html) — phân biệt failed authentication với denial authorization.

**Ghi nhớ:** `AuthorizationDeniedEvent` là bằng chứng về **quyết định từ chối quyền**, còn dữ liệu đủ để **điều tra** phải được ghép với identity/policy, request/trace và HTTP outcome một cách an toàn, có thể kiểm chứng.