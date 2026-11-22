# Ghi nhận sự kiện bảo mật và thiết kế nhật ký kiểm toán trong Spring Security Reactive

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể phân biệt log vận hành với nhật ký kiểm toán (audit trail), xác định sự kiện bảo mật cần ghi, xây dựng bản ghi có cấu trúc và nối quá trình ghi audit vào luồng Reactor mà không chặn event loop. Trọng tâm là ứng dụng Spring Boot WebFlux dùng `SecurityWebFilterChain`, `ReactiveAuthenticationManager` và `ReactiveSecurityContextHolder`.

**Tình huống:** một tài khoản thử mật khẩu sai, một người dùng đã xác thực nhưng gọi API quản trị, hoặc quản trị viên thay đổi vai trò tài khoản. Cả ba đều cần bằng chứng truy vết: ai thực hiện, thao tác nào, thời điểm, đối tượng, kết quả, lý do và mã tương quan. Một dòng `DEBUG` chứa HTTP status thường không đủ trả lời các câu hỏi này.

Audit không thay thế cơ chế xác thực, phân quyền, cảnh báo hay tracing. Nó phải ghi nhận quyết định/sự kiện đã xảy ra; việc có bản ghi không đồng nghĩa hệ thống đã ngăn chặn được tấn công.

## 2. Log ứng dụng, quan sát và audit khác nhau thế nào?

| Dạng dữ liệu | Mục đích | Ví dụ | Tính chất |
| --- | --- | --- | --- |
| Application log | Chẩn đoán lỗi, theo dõi xử lý | Timeout khi gọi dịch vụ | Có thể lấy mẫu, thay đổi mức log |
| Metrics / tracing | Đo độ trễ, tỷ lệ lỗi, lần theo yêu cầu | Số lần HTTP 403, trace ID | Thường tổng hợp, có thể sampling |
| Security event | Phát hiện hoạt động đáng ngờ | Đăng nhập sai nhiều lần, truy cập bị từ chối | Có tên sự kiện và kết quả rõ ràng |
| Audit trail | Giải trình hoạt động nhạy cảm | Ai cấp quyền ADMIN cho ai, trước/sau là gì | Cần đầy đủ, có bảo vệ toàn vẹn, quyền xem và vòng đời lưu trữ |

Một sự kiện có thể phục vụ cả giám sát và kiểm toán, nhưng **không dùng sampling ngẫu nhiên cho các sự kiện bắt buộc kiểm toán**. Không biến mọi HTTP 200 thành “đăng nhập thành công”: với HTTP Basic, xác thực lại trên nhiều request; với phiên đăng nhập, refresh token hay OAuth2/OIDC, ranh giới sự kiện khác nhau.

Phân loại tối thiểu:

1. **Authentication:** thử xác thực thành công/thất bại; khóa, mở khóa, vô hiệu hóa tài khoản; đăng xuất, thu hồi phiên/token khi có luồng tương ứng. Phân biệt `AUTHENTICATION_FAILED` với “chưa gửi thông tin xác thực”.
2. **Authorization:** truy cập bị từ chối do thiếu quyền, sai phạm vi tenant, chính sách; thay đổi quyền/nhóm/chính sách; nêu chính xác mức **HTTP** hay **method security**.
3. **Security-sensitive business actions:** đổi email khôi phục, bật/tắt MFA, reset credential, thay đổi vai trò, đọc/xuất dữ liệu nhạy cảm, sửa chính sách. Ghi tại tầng nghiệp vụ sau khi biết kết quả thật, không chỉ suy ra từ HTTP status.
4. **Control-plane events:** chỉnh cấu hình bảo mật, thay đổi khóa/certificate, đổi chính sách giữ log, xóa dữ liệu audit theo quy trình được phép.

**HTTP 401 và 403:** thông thường 401 là cần xác thực hoặc xác thực không hợp lệ; 403 là bị từ chối quyền sau khi xác thực. Nhưng không thể dựa duy nhất vào status để biết nguyên nhân: CSRF, lỗi tài nguyên, custom entry point và các xử lý khác có thể tạo cùng status. Ghi tại đúng hook bảo mật, kèm mã lý do đã phân loại.

## 3. Hợp đồng dữ liệu của một audit event

Thiết kế schema có phiên bản và các trường ổn định. Ví dụ:

| Trường | Ý nghĩa |
| --- | --- |
| `eventId`, `schemaVersion` | ID duy nhất phục vụ chống trùng / định dạng có thể tiến hóa |
| `occurredAt`, `recordedAt` | Thời gian sự kiện xảy ra và lúc hệ thống lưu, chuẩn UTC |
| `service`, `environment`, `tenantId` | Nguồn phát sinh; tenant nếu ứng dụng đa thuê |
| `eventType`, `outcome`, `reasonCode` | Loại hành động; SUCCESS/DENIED/FAILURE; mã nguyên nhân có kiểm soát |
| `actorId`, `actorType` | Định danh ổn định của người/service, hoặc UNKNOWN nếu chưa xác thực |
| `targetType`, `targetId` | Đối tượng bị tác động, tách khỏi actor |
| `httpMethod`, `routeTemplate` | Phương thức và route chuẩn hóa, tránh nhúng query/path thô có bí mật |
| `requestId`, `traceId` | Khóa nối với trace và log vận hành; không dùng làm định danh người dùng |
| `authMethod`, `clientContext` | Cơ chế xác thực; IP/UA đã chuẩn hóa nếu thực sự cần và theo chính sách riêng tư |
| `changeSummary` | Các trường bị thay đổi, tên quyền cũ/mới **đã lọc**; không chép dữ liệu nhạy cảm |

Bản ghi minh họa (giá trị giả định, không phải stdout cố định của ví dụ chạy bên dưới):

```json
{
  "eventId": "f58ce0fa-6f81-4e0b-a562-cd296c597632",
  "schemaVersion": 1,
  "occurredAt": "2026-11-07T09:00:00Z",
  "service": "security-reactive-api",
  "eventType": "AUTHORIZATION_DENIED",
  "outcome": "DENIED",
  "reasonCode": "MISSING_REQUIRED_ROLE",
  "actorId": "user-42",
  "targetType": "HTTP_ROUTE",
  "targetId": "GET /admin",
  "requestId": "req-7a1e",
  "traceId": "trace-9c2b"
}
```

**Không đưa vào audit:** mật khẩu, header `Authorization`, cookie/session ID, access/refresh token, OTP, private key, toàn bộ request/response body, URL có query bí mật, stack trace chứa dữ liệu nhạy cảm. Tên người dùng, email và IP cũng có thể là dữ liệu cá nhân: chỉ giữ nếu cần và kiểm soát quyền đọc, thời hạn lưu, masking/pseudonymization. Dùng mã lỗi như `BAD_CREDENTIALS` thay vì ghi nội dung ngoại lệ có thể chứa chi tiết nội bộ.

## 4. Vị trí ghi trong luồng WebFlux

```text
Client
  -> WebFilter tạo requestId/đặt Reactor Context
  -> SecurityWebFilterChain
       -> HTTP Basic / form / OAuth2 / resource-server authentication
          -> Authentication thành công hoặc thất bại -> audit
       -> Authorization (route/method)
          -> Denied -> ServerAccessDeniedHandler / hook tương ứng -> audit
       -> Controller -> Service nghiệp vụ
          -> Thay đổi nhạy cảm thành công/thất bại -> audit nghiệp vụ
  -> Structured log / queue / transactional outbox / audit store
  -> SIEM, cảnh báo và tra cứu có phân quyền
```

Các điểm mở rộng chính:

- **`ReactiveAuthenticationManager`:** có thể bọc bằng `flatMap` và `onErrorResume` để quan sát quyết định của **cơ chế xác thực đang dùng**. `Mono.empty()` có thể là “không quyết định”, không tự đồng nhất với thất bại. Nếu có nhiều provider, đặt hook ở tầng xác thực phù hợp để tránh sự kiện trùng hoặc bỏ sót.
- **`ServerAuthenticationSuccessHandler` / `ServerAuthenticationFailureHandler`:** hữu ích khi tùy biến `AuthenticationWebFilter` hoặc form login. Khi bọc handler, phải tiếp tục gọi handler gốc để giữ redirect, lưu `SecurityContext`, HTTP challenge và hành vi đăng nhập. Không gán một handler HTTP Basic cho tất cả OAuth2/JWT một cách máy móc.
- **`ServerAuthenticationEntryPoint`:** kích hoạt phản hồi yêu cầu xác thực, thường 401; đây **không tự động có nghĩa mật khẩu sai**.
- **`ServerAccessDeniedHandler`:** xử lý trường hợp thiếu quyền, thường 403. Với CSRF, cần xem handler của `csrf` riêng; với method security, kiểm tra rằng exception thực sự đi qua lớp xử lý HTTP tương ứng. Không cam kết mọi `AccessDeniedException` đều tới một hook.
- **Tầng nghiệp vụ:** ở bước cấp quyền, thu hồi token, sửa policy, cần log sự kiện với đối tượng và kết quả giao dịch thật, thay vì chỉ gắn `WebFilter` đọc status.

Tài liệu Spring Security về `AuthenticationSuccessEvent` / `DefaultAuthenticationEventPublisher` ở nhánh **Servlet** không có nghĩa ứng dụng WebFlux tự phát đầy đủ các sự kiện đó. Phải kiểm chứng cơ chế/provider reactive thực tế rồi gắn hook phù hợp.

### Reactor Context, thread và backpressure

WebFlux có thể chuyển luồng xử lý giữa nhiều thread. `SecurityContextHolder` dựa trên `ThreadLocal` của luồng servlet không phải cách đọc danh tính chuẩn trong Reactor; dùng `ReactiveSecurityContextHolder.getContext()` hoặc `exchange.getPrincipal()` khi ở Web layer. Đặt request ID vào `Reactor Context` bằng `contextWrite`, lấy qua `Mono.deferContextual`. MDC truyền thống cũng dựa trên ThreadLocal nên muốn dùng phải có cầu nối context phù hợp, không mặc định trông cậy MDC luôn theo kịp các lần chuyển thread.

Audit writer trả về `Mono<Void>` để **compose** vào pipeline bằng `then` / `flatMap`. Tránh `block()` trên event loop; tránh gọi `subscribe()` “fire-and-forget” trong handler vì mất kiểm soát lỗi, thứ tự và vòng đời. Ghi file/DB sync hoặc chuyển JSON nặng trong cùng event loop cũng có thể gây nghẽn dù API trả về `Mono`; production cần appender/driver bất đồng bộ hoặc outbox/queue có kiểm soát.

## 5. Ví dụ chạy được: HTTP Basic + audit sự kiện và 401/403

Ví dụ nhỏ dùng Java 17, Spring Boot **3.3.13**, WebFlux và Spring Security 6.3.x; có hai user demo. Mục tiêu là minh họa hook, cấu trúc log và Reactor Context; đây chưa phải kho audit bất biến cho production.

### 5.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>dev.example</groupId>
    <artifactId>reactive-audit-demo</artifactId>
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

Tạo file `src/main/java/dev/example/audit/AuditDemoApplication.java` (tất cả class phụ nằm cùng file và không khai báo `public`):

```java
package dev.example.audit;

import java.security.Principal;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class AuditDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuditDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class AuditSecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var alice = User.withUsername("alice")
                .password(encoder.encode("demo123")).roles("USER").build();
        var root = User.withUsername("root")
                .password(encoder.encode("admin123")).roles("ADMIN").build();
        return new MapReactiveUserDetailsService(alice, root);
    }

    @Bean
    ReactiveAuthenticationManager auditAuthenticationManager(
            MapReactiveUserDetailsService users,
            PasswordEncoder encoder,
            AuditLog audit) {
        var delegate = new UserDetailsRepositoryReactiveAuthenticationManager(users);
        delegate.setPasswordEncoder(encoder);

        return request -> Mono.deferContextual(context -> {
            String requestId = context.getOrDefault(AuditRequestIdFilter.KEY, "unknown");
            return delegate.authenticate(request)
                    .flatMap(authenticated -> audit.write(
                            "AUTHENTICATION", "SUCCESS", authenticated.getName(),
                            "HTTP_BASIC", "CREDENTIALS_ACCEPTED", requestId)
                            .thenReturn(authenticated))
                    .onErrorResume(AuthenticationException.class, failure ->
                            audit.write(
                                    "AUTHENTICATION", "FAILURE", request.getName(),
                                    "HTTP_BASIC", failure.getClass().getSimpleName(), requestId)
                                    .then(Mono.error(failure)));
        });
    }

    @Bean
    SecurityWebFilterChain securityChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager auditAuthenticationManager,
            AuditLog audit) {
        var basicChallenge = new HttpBasicServerAuthenticationEntryPoint();
        var forbidden = new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN);

        return http
                .authorizeExchange(authorize -> authorize
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(basic -> basic.authenticationManager(auditAuthenticationManager))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint((exchange, cause) ->
                                audit.write(
                                        "AUTH_REQUIRED", "DENIED", "anonymous",
                                        exchange.getRequest().getPath().value(),
                                        cause.getClass().getSimpleName(),
                                        exchange.getRequest().getId())
                                        .then(basicChallenge.commence(exchange, cause)))
                        .accessDeniedHandler((exchange, cause) ->
                                exchange.getPrincipal()
                                        .map(Principal::getName)
                                        .defaultIfEmpty("anonymous")
                                        .flatMap(actor -> audit.write(
                                                "AUTHORIZATION", "DENIED", actor,
                                                exchange.getRequest().getPath().value(),
                                                cause.getClass().getSimpleName(),
                                                exchange.getRequest().getId()))
                                        .then(forbidden.handle(exchange, cause))))
                .build();
    }
}

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
class AuditRequestIdFilter implements WebFilter {
    static final String KEY = "audit.requestId";

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String requestId = exchange.getRequest().getId();
        return chain.filter(exchange)
                .contextWrite(context -> context.put(KEY, requestId));
    }
}

@Component
class AuditLog {
    private static final Logger LOG = LoggerFactory.getLogger(AuditLog.class);
    private final ObjectMapper mapper;

    AuditLog(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    Mono<Void> write(String type, String outcome, String actor,
                     String resource, String reason, String requestId) {
        return Mono.fromRunnable(() -> {
            Map<String, String> event = new LinkedHashMap<>();
            event.put("eventId", UUID.randomUUID().toString());
            event.put("occurredAt", Instant.now().toString());
            event.put("type", type);
            event.put("outcome", outcome);
            event.put("actor", actor);
            event.put("resource", resource);
            event.put("reason", reason);
            event.put("requestId", requestId);
            try {
                LOG.info("SECURITY_AUDIT {}", mapper.writeValueAsString(event));
            } catch (JsonProcessingException ex) {
                throw new IllegalStateException("Audit serialization failed", ex);
            }
        }).then();
    }
}

@RestController
class DemoController {
    @GetMapping("/public")
    Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());
    }

    @GetMapping("/admin")
    Mono<String> admin() {
        return Mono.just("admin ok");
    }
}
```

**Cơ chế:** `AuditRequestIdFilter` đặt ID của request vào Reactor Context. `auditAuthenticationManager` bọc manager xác thực username/password thực tế; khi tín hiệu `onNext` chứa `Authentication` đã xác thực, phát sự kiện `SUCCESS`; khi manager phát `AuthenticationException`, ghi `FAILURE` rồi truyền lại lỗi. `AUTH_REQUIRED` phản ánh yêu cầu bắt đầu xác thực khi không đủ danh tính; `AUTHORIZATION DENIED` ghi trường hợp có principal nhưng thiếu quyền. Hai delegate phản hồi mặc định vẫn chạy để giữ Basic challenge và HTTP 403.

Ví dụ giữ CSRF theo mặc định và chỉ có GET, không thêm endpoint thay đổi trạng thái. Hai mật khẩu trong source **chỉ để học**; ứng dụng thật dùng kho danh tính, secret management và HTTPS. Do HTTP Basic xác thực theo request, cùng một user có thể tạo nhiều sự kiện `AUTHENTICATION SUCCESS`, không nên diễn giải tất cả là một phiên login mới.

### 5.2. Thử các trường hợp

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Ở terminal khác:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/admin
curl -i -u alice:wrong http://localhost:8080/me
curl -i -u alice:demo123 http://localhost:8080/me
curl -i -u alice:demo123 http://localhost:8080/admin
curl -i -u root:admin123 http://localhost:8080/admin
```

| Request | HTTP mong đợi | Audit mong đợi |
| --- | --- | --- |
| GET `/public`, không credential | 200, body `public` | Không cần event xác thực/khước từ |
| GET `/admin`, không credential | 401, có Basic challenge | `AUTH_REQUIRED / DENIED` |
| GET `/me`, mật khẩu sai | 401 | `AUTHENTICATION / FAILURE`; handler Basic có thể phát challenge mà không đi qua hook `AUTH_REQUIRED` |
| GET `/me`, alice hợp lệ | 200, body `alice` | `AUTHENTICATION / SUCCESS` |
| GET `/admin`, alice hợp lệ | 403 | `AUTHENTICATION / SUCCESS` và `AUTHORIZATION / DENIED` |
| GET `/admin`, root hợp lệ | 200, body `admin ok` | `AUTHENTICATION / SUCCESS` |

Console sẽ có dòng bắt đầu bằng `SECURITY_AUDIT` và một JSON với các trường `eventId`, `occurredAt`, `type`, `outcome`, `actor`, `resource`, `reason`, `requestId`; các giá trị thời gian/ID thay đổi mỗi lần chạy nên không đưa một stdout cố định giả. Nếu dùng client/header tùy chỉnh hoặc nhiều security chain, kiểm tra đường đi filter/handler thực tế bằng test tích hợp.

### 5.3. Những giới hạn có chủ ý của demo

- `AuditLog` chỉ ghi ra logger: **chưa bảo đảm lưu bền, chống sửa hoặc chống mất log**; appender console đồng bộ có thể gây trễ trên event loop. Production dùng pipeline có buffering/backpressure, giới hạn hàng đợi, retry có kiểm soát, và kho audit phù hợp.
- `resource` của handler đang dùng đường dẫn thực. Production nên dùng **route template** hoặc loại bỏ ID/bí mật trong path, tuyệt đối không thêm query string; đặt `tenantId` và `actorId` từ nguồn tin cậy.
- Hook `ReactiveAuthenticationManager` ở đây bao phủ **HTTP Basic** được gán manager này. Thêm form login, OAuth2/OIDC hay JWT phải xác định pipeline tương ứng; chỉ có một bean manager không chứng minh mọi phương thức được ghi.
- Ví dụ không có hành động đổi quyền; việc audit **thay đổi trạng thái nghiệp vụ** phải được thêm tại service/transaction tương ứng. Không suy từ HTTP 200 rằng thay đổi đã được commit.
- `getRequest().getId()` là request ID nội bộ. Khi có OpenTelemetry/Micrometer tracing, nối thêm trace/span ID thật; không tin mù quáng vào header tương quan do client gửi.

## 6. Từ console log sang audit trail có thể tin cậy

### 6.1. Chọn ngữ nghĩa thành công và bảo toàn dữ liệu

**Ghi ở ranh giới quyết định:** xác thực được chấp nhận, authorization bị từ chối, thay đổi dữ liệu đã commit; tránh ghi “SUCCESS” trước khi giao dịch thành công. Nếu rollback, cần event `FAILED`/`ROLLED_BACK` hoặc mô hình business rõ ràng.

**Chính sách lỗi:** với log chẩn đoán thông thường có thể cho nghiệp vụ tiếp tục khi logging mất; với hành động bắt buộc kiểm toán, tổ chức có thể yêu cầu không cho phép thao tác hoàn tất khi chưa bảo đảm ghi audit. Quyết định fail-open/fail-closed phải được phê duyệt theo mức độ rủi ro. Demo nối `Mono` theo thứ tự, nên lỗi ghi log có thể khiến luồng trả lỗi; nhưng **không có cam kết giao dịch nguyên tử** giữa thao tác nghiệp vụ và log file.

**Transactional outbox** khi nghiệp vụ và audit cần đi cùng transaction: trong cùng transaction của DB nghiệp vụ, lưu thay đổi và một outbox event; worker riêng đẩy qua broker tới kho audit, retry có idempotency bằng `eventId`. Với hệ thống reactive, dùng API DB/transaction reactive thích hợp và xác nhận chính sách exactly-once theo thiết kế; broker thường thực tế hơn với at-least-once + deduplication.

### 6.2. Bảo vệ tính toàn vẹn, riêng tư và khả năng tra cứu

- **Append-only:** tài khoản ứng dụng chỉ có quyền thêm, không được UPDATE/DELETE audit; tách tài khoản quản trị, bật cơ chế lưu bất biến / WORM nếu pháp lý hoặc rủi ro yêu cầu. Hash hoặc chữ ký chỉ giúp khi khóa, phân quyền và chuỗi bảo quản cũng được bảo vệ; hash đơn thuần không chống người có quyền sửa toàn bộ dữ liệu.
- **Đồng hồ và định danh:** chuẩn hóa timestamp UTC, duy trì clock sync, lưu cả event time và ingest time khi có queue; dùng ID duy nhất và schemaVersion. Tách actor, target, tenant để không nhầm chủ thể.
- **Quyền và bảo mật:** chỉ nhóm được ủy quyền xem log; mã hóa lúc truyền/lưu, giám sát truy cập kho audit, hạn chế xuất file, che dữ liệu nhạy cảm, chống log injection bằng JSON serializer; không ghi credential hoặc raw token.
- **Giữ và hủy:** thiết lập retention theo yêu cầu nghiệp vụ/pháp luật, cơ chế legal hold nếu có; lưu dài hơn không tự động tốt hơn. Xóa/ẩn danh theo chính sách và vẫn lưu bằng chứng thao tác quản trị phù hợp.
- **Tìm kiếm:** index trên `occurredAt`, `eventType`, `actorId`, `targetId`, `tenantId`, `requestId`; có phân trang, lọc tenant bắt buộc, giới hạn truy vấn và kiểm tra không rò thông tin qua API tra cứu.

### 6.3. Hiệu năng, độ tin cậy và cảnh báo

Theo dõi: audit events/giây theo loại, độ trễ ghi (p95/p99), kích thước hàng đợi, bản ghi bỏ sót, lỗi serializer/sink, retry, khoảng trễ event-to-ingest, dung lượng lưu trữ. Dùng alert cho chuỗi thất bại bất thường, truy cập denied tăng vọt, cấp quyền nhạy cảm, kho audit ngừng nhận dữ liệu; đặt ngưỡng chống false positive.

Các sự kiện bắt buộc phải audit thường được ưu tiên trước debug logs. Nếu áp dụng sampling cho log thường, bảo đảm pipeline audit không bị sampling hoặc rate limit làm mất sự kiện quan trọng. Giảm chi phí bằng schema gọn, mã lý do có kiểm soát, partition theo thời gian/tenant và archive hợp lý.

## 7. Checklist QA và lỗi thường gặp

**Kịch bản kiểm tra tối thiểu:** thử 401 khi thiếu credential; 401 khi sai mật khẩu; 200 khi đúng mật khẩu; 403 khi thiếu role; 200 khi đúng role; CSRF/method security nếu bật; audit cho thao tác quản trị và rollback; sự kiện khi sink lỗi; khôi phục sau retry và loại bỏ trùng `eventId`; thử username chứa newline/ký tự Unicode để xác nhận JSON an toàn.

Kiểm tra mỗi event chỉ ghi một lần theo **ranh giới đã định nghĩa**, có `eventId` duy nhất, thời gian UTC, type/outcome/reason hợp lệ, correlation ID và actor/target đúng. Không có password, token, cookie hay dữ liệu bí mật trong log; tài khoản không đủ quyền không tra cứu được audit của người khác.

Các lỗi dễ gặp:

1. Dùng `SecurityContextHolder.getContext()` từ thread bất kỳ trong WebFlux rồi thấy user `null`; dùng `ReactiveSecurityContextHolder` hoặc principal trong exchange.
2. Gọi `block()` / `subscribe()` bên trong reactive handler; làm nghẽn hoặc mất tín hiệu lỗi. Hãy compose `Mono`.
3. Ghi `AUTHENTICATION_SUCCESS` cho mọi 200; HTTP status không chứng minh xác thực mới hoặc nghiệp vụ đã commit.
4. Chỉ log `exception.getMessage()`; có thể rò rỉ dữ liệu, khó truy vấn và không ổn định theo phiên bản. Dùng `reasonCode` có kiểm soát.
5. Chỉ cấu hình event publisher của **Servlet** rồi mặc định nghĩ WebFlux bao phủ; kiểm thử chính xác hook reactive được sử dụng.
6. Ghi audit trước transaction nhưng nghiệp vụ rollback, hoặc fire-and-forget khiến record bị mất; dùng transaction/outbox phù hợp.
7. Tin vào `X-Forwarded-For`/`X-Request-Id` do client gửi mà không cấu hình trusted proxy; cho phép giả mạo nguồn gốc.
8. Đồng nhất log text trên console với kho audit bất biến; cần kiểm soát truy cập, lưu bền, integrity, retention và giám sát tính đầy đủ.

## 8. Tài liệu tham khảo

- Spring Security — Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — Enable Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — ServerHttpSecurity API: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security — AuthenticationWebFilter API: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
