# Giám sát tỷ lệ từ chối và lỗi quyết định quyền bất thường

> Phạm vi: **Spring Security - authorization**, phần **Hiệu năng và vận hành**. Bài này hướng dẫn giám sát việc phân quyền ở ứng dụng Spring Boot Servlet/MVC: đo tỷ lệ từ chối, phân biệt hành vi bị từ chối đúng chính sách với **lỗi khi đánh giá quyền**, gắn cảnh báo và điều tra mà không làm suy yếu kiểm soát truy cập. Ví dụ dùng Java 17, Spring Boot 3.3/3.4, Spring Security 6.x, Micrometer, Prometheus và JUnit 5.

## 1. Không đồng nhất HTTP 403 với lỗi quyết định quyền

Một yêu cầu HTTP có thể đi qua xác thực, kiểm tra CSRF, `AuthorizationFilter` (quyền truy cập URL), `@PreAuthorize` trên service, rồi mới đến nghiệp vụ. Không phải trường hợp thất bại nào cũng là “policy sai”.

| Tín hiệu | Ý nghĩa | Điều cần phân biệt |
| --- | --- | --- |
| HTTP 401 | Chưa xác thực được theo contract của ứng dụng | Token thiếu/hết hạn, HTTP Basic anonymous; thường là **authentication**, không phải kết quả policy deny |
| HTTP 403 | Request cuối cùng bị cấm | Có thể do thiếu quyền **hoặc** CSRF, custom filter/handler, gateway |
| `allow` | Policy được quan sát đã đánh giá và cho phép | Request vẫn có thể nhận 4xx/5xx ở lớp sau; không đồng nghĩa HTTP 200 |
| `deny` | Policy được quan sát đã đưa ra quyết định từ chối | Anonymous có thể nhận 401; authenticated thường nhận 403 |
| `abstain` | Policy không đưa ra kết quả (`null` ở một số API) | Chưa thể coi là allow hoặc deny; xử lý phụ thuộc chuỗi policy/framework |
| `error` | Mã đánh giá quyền gặp exception bất ngờ | Ví dụ lỗi SpEL, DB/remote PDP timeout, cấu hình sai; đây là **sự cố kỹ thuật**, không được đổi ngầm thành allow |
| Denied event | `AuthorizationDeniedEvent` do Spring Security phát | Cần `AuthorizationEventPublisher`; không bao phủ mọi 401/403, và sự kiện có thể xuất hiện nhiều lần trong một request |

Trong Servlet stack, `ExceptionTranslationFilter` xử lý `AccessDeniedException`: với anonymous thường chuyển sang `AuthenticationEntryPoint`; với người đã xác thực thường chuyển sang `AccessDeniedHandler`. Kết quả cụ thể tùy HTTP Basic, session, bearer token, exception handler và policy. Vì vậy **số HTTP 403 không phải mẫu số/tử số trực tiếp của tỷ lệ policy deny**.

```text
HTTP request
   |
   +--> authentication / CSRF ----> có thể trả 401 hoặc 403 sớm
   |
   v
AuthorizationFilter ----------------> allow / deny / error (quyết định URL)
   |
   v
Controller --> Method Security -----> allow / deny / error (quyết định method)
   |
   v
Service / Repository ----------------> success hoặc lỗi nghiệp vụ
   |
   v
HTTP status cuối cùng
```

Một request có thể tạo **nhiều lần đánh giá quyền** (URL + method security, `ERROR`/`FORWARD` dispatch, lời gọi nhiều service). Muốn đo “tỷ lệ request bị từ chối” phải thiết kế phép đếm ở **request boundary** có loại trừ trùng lặp; muốn đo “tỷ lệ decision bị từ chối” phải đếm mỗi quyết định và dùng cùng một phạm vi policy.

## 2. Thiết kế các chỉ số có mẫu số rõ ràng

Bộ metric tối thiểu được đề xuất:

| Tên | Loại/nguồn | Tags ít cardinality | Sử dụng |
| --- | --- | --- | --- |
| `http.server.requests` | Timer, Spring Boot Actuator | method, status, outcome, URI template khi có | Theo dõi HTTP 401/403/5xx, volume và latency |
| `security.authorization.decisions` | Counter riêng | `policy`, `result=allow/deny/abstain/error/auth_error` | Đếm evaluation trong những policy **đã instrument** |
| `security.authorization.denied.events` | Counter riêng | Không tag người dùng | Theo dõi sự kiện deny từ Spring |
| `security.authorization.latency` | Timer tùy chọn | policy, result hữu hạn | Độ trễ policy, nhất là policy phụ thuộc DB/remote PDP |

**Nhóm `policy` phải cố định**: ví dụ `reports.read`, `invoice.approve`, `documents.archive`. Không dùng username, tenant ID tự do, token, email, request UUID, IP, ID tài liệu, raw URL, query string hoặc exception message làm Prometheus label: các giá trị đó gây bùng nổ time series và dễ lộ dữ liệu nhạy cảm.

Nếu trong một cửa sổ 5 phút `documents.archive` có 970 allow, 30 deny và 2 error thì:

```text
deny_ratio  = 30 / (970 + 30) = 3%
error_ratio = 2 / (970 + 30 + 2) ≈ 0,20%
```

Không gọi 32/1002 là tỷ lệ từ chối. Nếu cùng khoảng có 4.000 HTTP request và 80 HTTP 403, thì HTTP 403 ratio là `80 / 4000 = 2%`. **Ba tỷ lệ khác nhau** vì đơn vị là policy decision hoặc HTTP request. Deny rate nên tính riêng theo từng policy; khi lượng evaluation thấp, tỷ lệ cao chưa đủ để kết luận có sự cố.

## 3. Thu thập HTTP status qua Micrometer/Actuator

Trong ứng dụng Spring Boot 3.x dùng Gradle và Spring Boot BOM, nếu chưa có các dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Cấu hình mẫu `src/main/resources/application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: never
```

Endpoint `/actuator/metrics` giúp chẩn đoán metric, `/actuator/prometheus` cung cấp dữ liệu scrape khi có Prometheus registry. **Không tự cho rằng endpoint đã được bảo vệ**: cấu hình exposure chỉ xác định được công bố, còn phải giới hạn mạng quản trị, xác thực service account/TLS và SecurityFilterChain tương ứng. Nếu ứng dụng dùng `.anyRequest().denyAll()`, phải xây dựng quy tắc quản trị riêng trước khi collector có thể scrape.

Metric HTTP thường có labels method, status, outcome và URI template khi framework nhận ra route. Với request bị filter chặn sớm, tag URI có thể không có template hoặc là `UNKNOWN`; hãy kiểm tra kết quả export thực tế trước khi viết biểu đồ cố định. Không dùng raw URL chứa ID chỉ để tăng độ chi tiết.

## 4. Java 17+ — bọc `AuthorizationManager` để đếm allow/deny/error

Ví dụ độc lập với quy tắc: GET `/api/reports` đòi authority `report:read`. Ta **giữ lại chính policy của Spring Security**, thêm decorator ghi nhận kết quả và không thay đổi quyền, return value, exception. Đo ở điểm này giúp biết chính xác mẫu số các lần policy `reports.read` được gọi.

File hoàn chỉnh `src/main/java/com/example/securitymonitor/AuthorizationMonitoringApp.java`:

```java
package com.example.securitymonitor;

import java.util.function.Supplier;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.event.EventListener;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@Import({AuthorizationMonitoringApp.SecurityConfig.class,
         AuthorizationMonitoringApp.ReportController.class})
public class AuthorizationMonitoringApp {

    public static void main(String[] args) {
        SpringApplication.run(AuthorizationMonitoringApp.class, args);
    }

    @RestController
    public static class ReportController {
        @GetMapping("/api/reports")
        public String read() {
            return "reports-ok";
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SecurityConfig {
        @Bean
        SecurityFilterChain web(HttpSecurity http, MeterRegistry registry)
                throws Exception {
            AuthorizationManager<RequestAuthorizationContext> policy =
                AuthorityAuthorizationManager.hasAuthority("report:read");

            return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/api/reports")
                    .access(new CountingAuthorizationManager(
                        "reports.read", policy, registry))
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        }

        @Bean
        AuthorizationEventPublisher authorizationEventPublisher(
                ApplicationEventPublisher springEvents) {
            return new SpringAuthorizationEventPublisher(springEvents);
        }

        @Bean
        DeniedEventMeter deniedEventMeter(MeterRegistry registry) {
            return new DeniedEventMeter(registry);
        }
    }

    // Mẫu cho Spring Security 6.x. Với API lớn hơn, kiểm tra
    // migration từ check() sang authorize() theo phiên bản đang dùng.
    static final class CountingAuthorizationManager
            implements AuthorizationManager<RequestAuthorizationContext> {

        private final AuthorizationManager<RequestAuthorizationContext> target;
        private final Counter allowed, denied, abstained, error, authError;

        CountingAuthorizationManager(String policy,
                AuthorizationManager<RequestAuthorizationContext> target,
                MeterRegistry registry) {
            this.target = target;
            allowed = counter(registry, policy, "allow");
            denied = counter(registry, policy, "deny");
            abstained = counter(registry, policy, "abstain");
            error = counter(registry, policy, "error");
            authError = counter(registry, policy, "auth_error");
        }

        private static Counter counter(
                MeterRegistry registry, String policy, String result) {
            return Counter.builder("security.authorization.decisions")
                .tag("policy", policy)
                .tag("result", result)
                .register(registry);
        }

        @Override
        public AuthorizationDecision check(
                Supplier<Authentication> authentication,
                RequestAuthorizationContext context) {
            try {
                AuthorizationDecision decision =
                    target.check(authentication, context);
                if (decision == null) {
                    abstained.increment();
                } else if (decision.isGranted()) {
                    allowed.increment();
                } else {
                    denied.increment();
                }
                return decision;
            } catch (AccessDeniedException rejection) {
                denied.increment();
                throw rejection;
            } catch (AuthenticationException failure) {
                authError.increment();
                throw failure;
            } catch (RuntimeException unexpected) {
                error.increment();
                throw unexpected; // Không đổi lỗi thành cho phép.
            }
        }
    }

    static final class DeniedEventMeter {
        private final Counter events;

        DeniedEventMeter(MeterRegistry registry) {
            events = Counter.builder("security.authorization.denied.events")
                .register(registry);
        }

        @EventListener
        public void onDenied(AuthorizationDeniedEvent<?> event) {
            // Không đưa object/authentication hoặc raw exception vào tags.
            events.increment();
        }
    }
}
```

### Cơ chế vận hành của ví dụ

1. Request có authority `report:read` → `CountingAuthorizationManager` gọi policy gốc, thấy `isGranted()==true`, counter `result=allow` tăng 1, API trả `reports-ok`.
2. Authenticated request chỉ có `report:list` → counter `result=deny` tăng, Spring Security từ chối truy cập (ở ví dụ HTTP Basic là 403).
3. Anonymous request → HTTP Basic thường trả 401. Việc policy có được thực thi và phát deny event hay không phụ thuộc chuỗi filter và authentication; **không đếm 401 như 403**.
4. Policy phụ thuộc DB/SpEL nếu ném `IllegalStateException` → counter `result=error` tăng và exception được ném tiếp. `AccessDeniedException` chủ đích được tính là deny; `AuthenticationException` được tách thành `auth_error`. Không tự giả định mọi lỗi đánh giá luôn trở thành HTTP 500, vì mapping của ứng dụng có thể khác.
5. `DeniedEventMeter` nhận `AuthorizationDeniedEvent` do publisher Spring phát. **Không cộng metric events với metric decisions**: URL guard, method security và các dispatcher có thể tạo event khác nhau trong một request.

Decorator trên chỉ đo những lượt qua rule GET `/api/reports`; `.anyRequest().denyAll()` và guard method khác không tự được gắn `reports.read`. Nếu ứng dụng dùng `@PreAuthorize`, bật `@EnableMethodSecurity`, quan sát riêng đúng điểm enforcement và ghi rõ metric nào bao gồm method-level decision. Tránh bọc mọi policy bằng cùng một `policy="all"` nếu muốn tìm endpoint đang bất thường.

### 4.1. Kiểm thử counters, status và exception propagation

Tạo `src/test/java/com/example/securitymonitor/AuthorizationMonitoringTest.java`:

```java
package com.example.securitymonitor;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = AuthorizationMonitoringApp.class)
@AutoConfigureMockMvc
class AuthorizationMonitoringTest {

    @Autowired MockMvc mvc;
    @Autowired MeterRegistry registry;

    private double count(String result) {
        return registry.get("security.authorization.decisions")
            .tags("policy", "reports.read", "result", result)
            .counter().count();
    }

    @Test
    void allowedRequestIncreasesAllowOnly() throws Exception {
        double allowed = count("allow");
        double denied = count("deny");

        mvc.perform(get("/api/reports")
                .with(user("alice").authorities("report:read")))
            .andExpect(status().isOk())
            .andExpect(content().string("reports-ok"));

        assertEquals(allowed + 1, count("allow"));
        assertEquals(denied, count("deny"));
    }

    @Test
    void forbiddenRequestIncreasesDenyOnly() throws Exception {
        double allowed = count("allow");
        double denied = count("deny");

        mvc.perform(get("/api/reports")
                .with(user("bob").authorities("report:list")))
            .andExpect(status().isForbidden());

        assertEquals(allowed, count("allow"));
        assertEquals(denied + 1, count("deny"));
    }

    @Test
    void anonymousRequestUsesAuthenticationEntryPoint()
            throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unexpectedPolicyFailureIsErrorNotDeny() {
        try (SimpleMeterRegistry isolated = new SimpleMeterRegistry()) {
            AuthorizationManager<RequestAuthorizationContext> broken =
                (auth, request) -> {
                    throw new IllegalStateException("policy backend down");
                };

            var monitored = new AuthorizationMonitoringApp
                .CountingAuthorizationManager(
                    "reports.read", broken, isolated);

            var context = new RequestAuthorizationContext(
                new MockHttpServletRequest("GET", "/api/reports"));

            assertThrows(IllegalStateException.class,
                () -> monitored.check(
                    () -> new TestingAuthenticationToken(
                        "alice", "unused", "report:read"),
                    context));

            assertEquals(1.0, isolated
                .get("security.authorization.decisions")
                .tags("policy", "reports.read", "result", "error")
                .counter().count());

            assertEquals(0.0, isolated
                .get("security.authorization.decisions")
                .tags("policy", "reports.read", "result", "deny")
                .counter().count());
        }
    }
}
```

Chạy từ root dự án có Gradle Wrapper:

```bash
./gradlew test --tests "com.example.securitymonitor.AuthorizationMonitoringTest"
```

Trên Windows:

```powershell
.\gradlew.bat test --tests "com.example.securitymonitor.AuthorizationMonitoringTest"
```

**Kỳ vọng:** 4 test xanh khi chạy trong dự án có dependency và Spring Boot 3.3/3.4 tương thích. Đây là kỳ vọng theo assertion, **không phải kết quả Gradle đã chạy**. Test thứ tư chứng minh error tăng, deny không tăng và exception không bị nuốt. Có thể thêm test kiểm tra `AccessDeniedException`, `AuthenticationException` và `null` decision; nếu policy đổi, các trường hợp này phải giữ nguyên phân loại.

## 5. Truy vấn Prometheus và cảnh báo

Micrometer thường đổi Counter `security.authorization.decisions` thành `security_authorization_decisions_total`; HTTP Timer thường xuất count dưới `http_server_requests_seconds_count`. **Kiểm tra tên thực tế trên `/actuator/prometheus`** vì naming convention, version và backend có thể khác.

### 5.1. Tỷ lệ policy deny trong 5 phút

```promql
sum by (policy) (
  rate(security_authorization_decisions_total{result="deny"}[5m])
)
/
clamp_min(
  sum by (policy) (
    rate(security_authorization_decisions_total{result=~"allow|deny"}[5m])
  ),
  1e-9
)
```

Chỉ đo policy đã instrument. Khi không có dữ liệu đủ mẫu số, dashboard phải thể hiện *no data* thay vì kết luận 0% từ chối.

### 5.2. Lỗi policy evaluation

```promql
sum by (policy) (
  increase(security_authorization_decisions_total{result="error"}[5m])
)
```

Lỗi đánh giá quyền thường đáng ưu tiên hơn deny hợp lệ vì có thể làm gián đoạn truy cập, chuyển HTTP 5xx hoặc làm hệ thống fail-closed hàng loạt.

### 5.3. Tỷ lệ HTTP 403 toàn ứng dụng

```promql
sum(rate(http_server_requests_seconds_count{status="403"}[5m]))
/
clamp_min(sum(rate(http_server_requests_seconds_count[5m])), 1e-9)
```

Tách biểu đồ 401, 403, 5xx, tổng request volume, P95 latency và tỷ lệ từ chối theo `policy`. Nếu 403 tăng mà `decision deny` không tăng, hãy kiểm tra CSRF, request matcher, gateway hay luồng bị chặn trước khi đến policy. Nếu 5xx và `error` cùng tăng, kiểm tra backend phụ thuộc/biểu thức policy.

### 5.4. Cảnh báo có ngưỡng lưu lượng và thời gian

Mẫu truy vấn khi deny >5% **và** có trên 100 đánh giá allow/deny trong 5 phút:

```promql
(
  sum by(policy) (
    rate(security_authorization_decisions_total{result="deny"}[5m])
  )
  /
  clamp_min(
    sum by(policy) (
      rate(security_authorization_decisions_total{result=~"allow|deny"}[5m])
    ),
    1e-9
  )
) > 0.05
and on(policy)
sum by(policy) (
  increase(security_authorization_decisions_total{result=~"allow|deny"}[5m])
) > 100
```

Trong alert rule dùng thêm `for: 10m` (điều kiện duy trì). Các số **5% / 100 / 10 phút chỉ là ví dụ để hiệu chỉnh**, không phải SLO mặc định. Dựa vào baseline từng policy, khung giờ, release, loại traffic và mức độ nhạy cảm. Một trang `/admin` cố tình chặn đa số user có thể có deny rate cao nhưng hoàn toàn bình thường; hành động ghi dữ liệu đặc quyền có thể cần cảnh báo sau chỉ vài lỗi.

Theo dõi cả **lượng decision sụt xuống bất thường** khi HTTP volume vẫn ổn định: có thể route chuyển sang SecurityFilterChain khác, guard bị bỏ qua, instrumentation không còn chạy hoặc collector mất dữ liệu.

## 6. Log, tracing và bảo vệ dữ liệu khi điều tra

Metrics xác định *bao nhiêu* và *khi nào*; logs/traces làm rõ *tại sao*. Có thể ghi sự kiện cấu trúc như sau (dữ liệu **minh họa**, ứng dụng phải tự tạo các trường):

```json
{
  "event": "authorization_decision",
  "timestamp": "2026-11-06T07:00:00Z",
  "service": "report-api",
  "environment": "production",
  "trace_id": "trace-created-by-tracing-system",
  "policy": "reports.read",
  "action": "read",
  "route_template": "/api/reports",
  "result": "deny",
  "reason_code": "INSUFFICIENT_AUTHORITY",
  "policy_version": "v3"
}
```

Các trường `reason_code` và `policy_version` là dữ liệu nghiệp vụ được quản lý; Spring Security không tự sinh chuẩn này. Chỉ dùng reason code từ danh mục hữu hạn. Không log access token, Authorization header, cookie, mật khẩu, nội dung tài liệu, query chứa bí mật, exception stack trace có secret. Muốn điều tra user/resource cụ thể, lưu định danh được bảo vệ trong hệ thống log có phân quyền và giới hạn thời gian lưu, không đưa vào Prometheus labels.

Những trường hợp cần lưu ý:

- Spring `AuthorizationDeniedEvent` hữu ích để biết có quyết định bị từ chối tại URL hoặc method (khi publisher được nối đúng). Granted events có thể gây nhiều dữ liệu và thường không phát mặc định; **không lấy số denied events làm mẫu số deny ratio**.
- `@PostFilter` có thể loại bản ghi khỏi kết quả mà HTTP vẫn 200; 401/403 không đo được “số bản ghi bị lọc”. Với nghiệp vụ cần theo dõi, thêm metric ở data/service layer, nhưng không lộ ID nhạy cảm.
- Nếu policy gọi remote PDP/DB, đo latency qua `Timer`/Micrometer Observation quanh đúng đoạn gọi, dùng key ít cardinality; đừng dùng P95 HTTP làm đại diện chính xác cho P95 policy.
- Event listener và logging không nên có thao tác I/O nặng đồng bộ trên request; có thể sampling/buffer theo thiết kế quan sát, đo giới hạn queue và drop rate; lỗi telemetry không được khiến policy fail-open.

## 7. Runbook điều tra tăng tỷ lệ từ chối hoặc lỗi đánh giá

| Bước | Câu hỏi | Hành động cụ thể |
| --- | --- | --- |
| 1. Xác nhận dữ liệu | Exporter đang hoạt động? Có counter reset/scrape gap? | So raw count, instance, thời điểm, request volume |
| 2. Khoanh phạm vi | Một policy hay mọi policy? Ở phiên bản nào? | Group theo policy, service, release; so trước/sau deploy |
| 3. Phân loại | Tăng 401, 403, deny hay error? | Đối chiếu HTTP metrics, policy counters và security events |
| 4. Tìm nguyên nhân xác thực | Token hết hạn, mapping scope/role sai, CSRF? | Kiểm tra auth provider, gateway, thay đổi client |
| 5. Tìm nguyên nhân phân quyền | Thứ tự matcher, policy mới, owner/tenant, role hierarchy? | So bảng quyền đã review và regression tests |
| 6. Điều tra evaluation error | DB/remote PDP timeout, lỗi cấu hình/SpEL? | Traces, dependency latency, release diff, exception có kiểm soát |
| 7. Khắc phục và hậu kiểm | Sửa policy hay rollback cấu hình? | Không tự nới quyền để giảm 403; chạy test và đo lại số liệu |

**Tình huống A:** trước deploy policy `reports.read` có 12.000 allow và 120 deny/giờ (~0,99%), sau deploy có 9.000 allow và 3.000 deny/giờ (25%), HTTP traffic không giảm, error=0. Kiểm tra rule matcher, mapping authorities và thay đổi policy sau deploy. Đừng mặc nhiên kết luận đang bị dò quét.

**Tình huống B:** sau front-end release, HTTP 403 tăng rõ ở POST, trong khi counter `deny` của policy không thay đổi. POST có thể bị CSRF filter chặn **trước authorization**. Việc sửa quyền không giải quyết được lỗi token CSRF.

**Tình huống C:** `error` tăng cùng 5xx và P95 latency cao; bản ghi log theo policy ghi `DEPENDENCY_TIMEOUT`. Kiểm tra DB/remote PDP, timeout/circuit breaker, release và cơ chế fail-closed. Không đổi lỗi dependency thành quyết định cho phép.

## 8. Lỗi phổ biến và checklist nghiệm thu

Các lỗi cần tránh:

1. Chỉ đếm 403 mà gọi nó là “authorization deny”: thiếu mẫu số và có thể gồm CSRF.
2. Lấy `denied_events / http_requests` làm “decision deny rate”: đơn vị đo sai, có thể có nhiều event/request.
3. Không tách `deny` và `error`: sự cố kỹ thuật bị hiểu thành người dùng thiếu quyền.
4. Log hoặc tag user ID, token, raw URL chứa ID: tăng cardinality và rò thông tin.
5. Cảnh báo chỉ dựa trên tỷ lệ khi có 1–2 request: nhiễu, phải thêm tối thiểu số mẫu và thời gian giữ điều kiện.
6. Đếm ở quá nhiều tầng rồi cộng chung: trùng lặp URL/method/dispatcher.
7. Bắt exception rồi trả `true`: nguy cơ fail-open. Giữ nguyên exception/deny semantics và có error telemetry.
8. Không kiểm thử instrumentation: route vẫn hoạt động nhưng metric mất sau refactor security config.
9. Mở Actuator để scrape mà không bảo vệ bằng mạng và auth phù hợp.

Checklist trước production: xác nhận các policy quan trọng được instrument; metric có policy/result hữu hạn và định nghĩa mẫu số; biểu đồ 401/403/5xx/traffic/deny/error/latency; alert được hiệu chỉnh theo baseline; runbook có owner; log/trace bảo vệ dữ liệu; test chứng minh allow/deny/error không đổi quyết định quyền; kiểm tra scraper access và chi phí cardinality sau deploy.

## Tài liệu tham khảo

- [Spring Security — Authorization Events](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html)
- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
