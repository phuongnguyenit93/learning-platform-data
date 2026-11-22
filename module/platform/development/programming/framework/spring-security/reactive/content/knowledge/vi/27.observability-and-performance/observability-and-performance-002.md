# Theo dõi quyết định xác thực, phân quyền và mã tương quan của yêu cầu trong Spring Security WebFlux

Bài học thuộc nhóm **Quan sát và hiệu năng** của **Spring Security – reactive**. Mục tiêu là trả lời được ba câu hỏi khi một yêu cầu HTTP bị chặn hoặc được chấp nhận: **đã có nỗ lực xác thực nào và kết quả ra sao**, **chính sách phân quyền nào đã được đánh giá**, và **những bản ghi nào thuộc cùng một yêu cầu**. Trọng tâm là `SecurityWebFilterChain`, `ReactiveAuthenticationManager`, `ReactiveAuthorizationManager`, `ServerWebExchange` và Reactor `Context`; không áp dụng cách cài đặt `SecurityFilterChain`/`OncePerRequestFilter` của Servlet vào WebFlux.

## 1. Phân biệt ba loại tín hiệu

| Tín hiệu | Câu hỏi cần trả lời | Điểm ghi nhận phù hợp |
| --- | --- | --- |
| **Xác thực (authentication)** | Có nỗ lực kiểm tra danh tính không? Thành công, thất bại hay không có quyết định? | `ReactiveAuthenticationManager` hoặc success/failure handler của cơ chế đăng nhập tương ứng |
| **Phân quyền (authorization)** | Quy tắc nào được xét? `GRANT`, `DENY` hay không phát sinh quyết định? | `ReactiveAuthorizationManager` được gắn vào `authorizeExchange(...).access(...)`; với bảo vệ phương thức cần quan sát riêng |
| **Kết quả HTTP** | Cuối cùng máy khách nhận mã trạng thái nào? | `WebFilter` ở rìa yêu cầu, callback khi response chuẩn bị commit |
| **Mã tương quan** | Log của filter, bảo mật và nghiệp vụ nào cùng một lượt xử lý? | Một ID sinh/chuẩn hóa tại điểm vào; truyền qua `ServerWebExchange` và Reactor `Context` |

**Authentication khác authorization.** Một tài khoản có thể xác thực thành công nhưng bị từ chối vào `/admin` vì thiếu `ROLE_ADMIN`. Một yêu cầu không có `Authorization` header có thể không hề kích hoạt một **nỗ lực** xác thực HTTP Basic, nhưng vẫn bị chính sách “phải đăng nhập” từ chối. Đừng ghi “mật khẩu sai” khi thực tế chỉ thiếu thông tin xác thực.

**Decision khác response.** Quyết định từ chối thường dẫn đến HTTP 403 khi người dùng đã xác thực và HTTP 401 khi cần bắt đầu xác thực (tùy entry point, cơ chế bảo mật và cấu hình). HTTP 401/403 tự nó không nói được cụ thể manager nào đã ra quyết định; lỗi nghiệp vụ cũng có thể phát sinh 403. Phải kết hợp các tín hiệu theo cùng `correlation_id`.

Trong WebFlux, pipeline có thể đổi luồng thực thi. `ThreadLocal` và MDC gắn trực tiếp với thread có thể bị thiếu hoặc mang dữ liệu của yêu cầu khác nếu dùng sai. `ServerWebExchange` giữ dữ liệu cho request HTTP hiện tại; Reactor `Context` giữ dữ liệu cho chuỗi reactive theo subscription. `ReactiveSecurityContextHolder` dùng Reactor context cho SecurityContext của Spring Security, không phải request-scoped ThreadLocal kiểu Servlet.

## 2. Mô hình luồng quan sát

```text
HTTP request
  |
  v
WebFilter đầu vào: sinh correlation_id, đưa vào exchange + Reactor Context
  |
  v
Spring Security WebFilter chain
  |-- AuthenticationWebFilter / cơ chế HTTP Basic, Bearer, OAuth2...
  |     |-- ReactiveAuthenticationManager -> authn_success / authn_failure (nếu có thử xác thực)
  |
  |-- AuthorizationWebFilter -> ReactiveAuthorizationManager
  |     |-- GRANT -> tiếp tục xử lý
  |     |-- DENY  -> từ chối theo chính sách
  |     '-- no decision / error -> xử lý theo hợp đồng manager, không gán nhầm GRANT
  |
  v
Controller / service / phương thức bảo vệ bởi @PreAuthorize (nếu có)
  |
  v
HTTP response -> ghi status với cùng correlation_id
```

Quy tắc trong `authorizeExchange` được xét theo thứ tự khai báo; matcher đầu tiên áp dụng sẽ chọn chính sách tương ứng. Vì vậy một lớp quan sát bọc `/admin` chỉ thấy những yêu cầu thực sự đi qua quy tắc đó. Yêu cầu bị xác thực thất bại sớm có thể **không có** bản ghi phân quyền; request vào đường dẫn `permitAll()` cũng không đi qua manager quan sát viết riêng cho các đường dẫn còn lại. “Không thấy sự kiện” không được suy ra thành “đã cho phép”.

## 3. Quy ước sự kiện và dữ liệu nên ghi

Ghi sự kiện có cấu trúc, các field nhất quán để tìm kiếm và thống kê:

- `timestamp` (UTC/ISO-8601 từ hệ thống log), `service`, `environment`; nếu có nhiều instance thì thêm `instance`.
- `correlation_id` cho một yêu cầu; `trace_id`/`span_id` từ hệ thống distributed tracing nếu đã tích hợp. Đây là các định danh **khác nhau**, không tự coi `X-Correlation-ID` là W3C `traceparent`.
- `event` = `authn_success`, `authn_failure`, `authz_decision` hoặc `http_response`; `mechanism` = `http_basic`/`bearer`/...; `policy` là tên ổn định của quy tắc.
- `outcome` = `GRANT`, `DENY`, `ABSTAIN` (khi manager không phát ra decision); `status` là HTTP status cuối.
- `principal` chỉ khi cần thiết và được phép: ưu tiên định danh nội bộ đã giảm nhạy cảm/giả danh hóa; `reason` dùng mã loại lỗi cố định, không dùng toàn bộ exception message.

**Không ghi** mật khẩu, Basic Authorization header, access/refresh token, cookie phiên, toàn bộ JWT/claims nhạy cảm, nội dung request body, query chứa dữ liệu cá nhân, hoặc stack trace cho mọi trường hợp sai thông tin đăng nhập. Không đưa tên người dùng, request ID, token, URL có ID động vào **nhãn metric** vì tạo cardinality cao và rò rỉ dữ liệu.

Một bản ghi minh họa (ID ngẫu nhiên chỉ để mô tả quan hệ, không phải output cố định):

```text
event=authn_success correlation_id=8fe2... mechanism=http_basic principal=reader
event=authz_decision correlation_id=8fe2... policy=admin_only outcome=DENY
event=http_response correlation_id=8fe2... status=403
```

## 4. Ví dụ chạy được: HTTP Basic và phân quyền theo vai trò

Ví dụ dùng **Java 17+**, Spring Boot **3.3.13** / Spring Security 6.3.x, Spring WebFlux và HTTP Basic để dễ kiểm tra luồng. Dữ liệu người dùng và mật khẩu dưới đây **chỉ phục vụ môi trường học tập**. Trong hệ thống thực, dùng danh tính và chính sách thực tế của ứng dụng; không tạo tài khoản mẫu như vậy.

Tạo dự án Maven với `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>security-trace</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
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

Tạo `src/main/java/com/example/securitytrace/SecurityTraceApplication.java`:

```java
package com.example.securitytrace;

import java.util.Objects;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatusCode;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authorization.AuthenticatedReactiveAuthorizationManager;
import org.springframework.security.authorization.AuthorityReactiveAuthorizationManager;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class SecurityTraceApplication {

    private static final Logger log =
            LoggerFactory.getLogger(SecurityTraceApplication.class);
    private static final String CORRELATION_ID = "correlationId";

    public static void main(String[] args) {
        SpringApplication.run(SecurityTraceApplication.class, args);
    }

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    WebFilter correlationFilter() {
        return (exchange, chain) -> {
            // Server sinh ID, không tin trực tiếp header do client tùy ý gửi.
            String id = UUID.randomUUID().toString();
            exchange.getAttributes().put(CORRELATION_ID, id);
            exchange.getResponse().getHeaders().set("X-Correlation-ID", id);

            // Ghi trạng thái khi response chuẩn bị commit, kể cả khi security chặn.
            exchange.getResponse().beforeCommit(() -> {
                HttpStatusCode code = exchange.getResponse().getStatusCode();
                log.info("event=http_response correlation_id={} status={}",
                        id, code == null ? 200 : code.value());
                return Mono.empty();
            });

            // contextWrite cấp ID cho các publisher ở phía trong filter chain.
            return chain.filter(exchange)
                    .contextWrite(ctx -> ctx.put(CORRELATION_ID, id));
        };
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
                User.withUsername("reader")
                        .password(encoder.encode("reader123"))
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin123"))
                        .roles("ADMIN")
                        .build()
        );
    }

    @Bean
    ReactiveAuthenticationManager observedAuthenticationManager(
            MapReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        var delegate = new UserDetailsRepositoryReactiveAuthenticationManager(users);
        delegate.setPasswordEncoder(encoder);

        return submitted -> Mono.deferContextual(context -> {
            String id = context.getOrDefault(CORRELATION_ID, "missing");
            return delegate.authenticate(submitted)
                    .doOnNext(auth -> log.info(
                            "event=authn_success correlation_id={} mechanism=http_basic principal={}",
                            id, auth.getName()))
                    .doOnError(AuthenticationException.class, ex -> log.warn(
                            "event=authn_failure correlation_id={} mechanism=http_basic reason={}",
                            id, ex.getClass().getSimpleName()));
        });
    }

    private static ReactiveAuthorizationManager<AuthorizationContext> observedPolicy(
            String policy,
            ReactiveAuthorizationManager<AuthorizationContext> delegate) {

        return (authentication, context) ->
                delegate.check(authentication, context)
                        .doOnSuccess(decision -> {
                            ServerWebExchange exchange = context.getExchange();
                            String id = Objects.toString(
                                    exchange.getAttribute(CORRELATION_ID), "missing");
                            String outcome = decision == null ? "ABSTAIN"
                                    : decision.isGranted() ? "GRANT" : "DENY";
                            log.info(
                                    "event=authz_decision correlation_id={} policy={} outcome={}",
                                    id, policy, outcome);
                        });
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager observedAuthenticationManager) {

        return http
                // Demo chỉ đọc bằng GET; không dùng disable CSRF như mặc định sản xuất.
                .csrf(csrf -> csrf.disable())
                .formLogin(form -> form.disable())
                .httpBasic(basic ->
                        basic.authenticationManager(observedAuthenticationManager))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").access(observedPolicy(
                                "admin_only",
                                AuthorityReactiveAuthorizationManager.hasRole("ADMIN")))
                        .anyExchange().access(observedPolicy(
                                "login_required",
                                AuthenticatedReactiveAuthorizationManager.authenticated())))
                .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/admin")
    Mono<String> adminEndpoint() {
        return Mono.just("admin");
    }

    @GetMapping("/profile")
    Mono<String> profileEndpoint() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> "hello " + ctx.getAuthentication().getName());
    }
}
```

**Vì sao đoạn mã giữ nguyên quyết định bảo mật?**

1. `observedAuthenticationManager` gọi `delegate.authenticate(...)` rồi gắn các toán tử quan sát `doOnNext`/`doOnError`; nó không tự trả về một đối tượng `Authentication` giả, không nuốt `AuthenticationException` và không biến thất bại thành thành công. Một `Mono.empty()` (nếu delegate không thể xử lý loại thông tin xác thực) không đồng nghĩa với đăng nhập thành công.
2. `observedPolicy` ủy quyền nguyên kết quả từ `delegate.check(...)`. `doOnSuccess` nhận `null` khi `Mono` kết thúc rỗng, nên ví dụ ghi `ABSTAIN` thay vì giả định `GRANT`. Nó không dùng `onErrorResume` để chuyển exception thành một quyết định được phép.
3. `@Order(Ordered.HIGHEST_PRECEDENCE)` đưa filter gắn correlation ID vào trước phần lớn filter khác, trong đó có chuỗi bảo mật; `contextWrite` làm ID khả dụng trong phép kiểm tra mật khẩu chạy bất đồng bộ. `ServerWebExchange` giúp manager phân quyền truy xuất ID của request. Filter chỉ quan sát response, không tự đổi status.
4. `.pathMatchers("/public").permitAll()` thực sự cho truy cập công khai; vì không qua `observedPolicy` nên chỉ nhận log HTTP cuối, trừ khi người dùng chủ động gửi thông tin Basic làm phát sinh nỗ lực xác thực. `/admin` đòi `ROLE_ADMIN`, còn `/profile` đòi tài khoản đã xác thực. `roles("ADMIN")` tạo authority `ROLE_ADMIN`; `hasRole("ADMIN")` tự thêm tiền tố `ROLE_`.

**Giới hạn của mẫu:** lớp quan sát authentication chỉ áp dụng cho manager đã nối với **HTTP Basic** trong ví dụ. Nếu dùng Bearer JWT, OAuth2 Login, session, custom authentication filter hay gateway, phải gắn tín hiệu ở **manager/handler đúng cơ chế**; không được tuyên bố mẫu HTTP Basic tự bắt được tất cả lần xác thực. `@PreAuthorize`/`@PostAuthorize` là phân quyền ở tầng phương thức, không nằm trong log của `authorizeExchange`; cần theo dõi riêng nếu ứng dụng bật reactive method security. Bản ghi thành công `principal=...` ở ví dụ chỉ để học; sản xuất nên cân nhắc giả danh hóa hoặc bỏ field này.

## 5. Chạy và kiểm tra theo tình huống

Trong thư mục chứa `pom.xml`, dùng JDK 17+ và Maven 3.6.3+:

```bash
mvn spring-boot:run
```

Mở terminal khác và thử các yêu cầu:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u reader:reader123 http://localhost:8080/profile
curl -i -u reader:wrong http://localhost:8080/profile
curl -i -u reader:reader123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
```

Kết quả HTTP **dự kiến** với đúng cấu hình trên:

| Yêu cầu | Status | Authentication | Authorization |
| --- | --- | --- | --- |
| `GET /public` không header | 200 | Không có nỗ lực Basic | Quy tắc `permitAll`; không qua wrapper quan sát |
| `GET /profile` không header | 401 | Không có nỗ lực Basic | Quy tắc `login_required` từ chối/đòi danh tính |
| `GET /profile` với `reader:reader123` | 200 | `authn_success` | `login_required = GRANT` |
| `GET /profile` với `reader:wrong` | 401 | `authn_failure` | Có thể không đi tới manager phân quyền |
| `GET /admin` với `reader:reader123` | 403 | `authn_success` | `admin_only = DENY` |
| `GET /admin` với `admin:admin123` | 200 | `authn_success` | `admin_only = GRANT` |

Mỗi response chứa header `X-Correlation-ID` dạng UUID. Với **từng lần gọi**, đối chiếu giá trị header đó với `correlation_id` trong log authentication (nếu có nỗ lực), authorization (nếu có đánh giá được ghi) và `http_response`. ID sẽ **khác nhau giữa các lần gọi**; không có stdout hoặc UUID cố định để sao chép. Có thể gửi nhiều request đồng thời để xác nhận log không trộn request ID.

Lưu ý: `curl -u` gửi HTTP Basic, thích hợp cho thử nghiệm trên `localhost`; khi truyền thật phải dùng HTTPS. Mật khẩu viết trên command line có thể lộ trong lịch sử shell hoặc danh sách tiến trình. Tài khoản mẫu phải bỏ khỏi ứng dụng thực tế. `csrf.disable()` trong ví dụ chỉ giúp cô lập luồng kiểm tra đối với các endpoint đọc; với ứng dụng có browser/session hoặc thao tác thay đổi trạng thái, phải đánh giá và cấu hình CSRF phù hợp.

## 6. Reactor Context, MDC và distributed tracing

Ví dụ đã minh họa hai cách truy cập cùng một định danh:

- Filter: `exchange.getAttributes().put("correlationId", id)`, phù hợp cho thành phần đã có `ServerWebExchange`.
- Reactive chain: `.contextWrite(ctx -> ctx.put("correlationId", id))` tại điểm bao ngoài; bên trong dùng `Mono.deferContextual(ctx -> ...)`. Context được truyền theo subscription và không dựa vào một thread cố định.

Không giả định `MDC.put("correlationId", id)` một lần ở đầu WebFlux request sẽ có giá trị trong tất cả callback sau `publishOn`/`subscribeOn`, hay luôn tự được xóa. Nếu công ty dùng Logback MDC, cần cơ chế context propagation tương thích phiên bản Reactor/Micrometer và kiểm chứng cả **propagate** lẫn **cleanup** khi đổi thread. Đoạn ví dụ ghi trực tiếp `correlation_id` vào structured log nên tránh phụ thuộc MDC.

Khi gọi dịch vụ khác bằng `WebClient`, muốn nối log liên dịch vụ cần có chiến lược truyền ID/trace context qua outbound request. Nên ưu tiên **Micrometer Observation + OpenTelemetry/W3C Trace Context** đã được cấu hình ở toàn chuỗi; `trace_id` và `span_id` do hệ thống tracing quản lý, còn `X-Correlation-ID` là trường bổ trợ khi có yêu cầu nghiệp vụ. Không tự ghi đè `traceparent` hoặc tin vô điều kiện một request ID do người dùng bên ngoài cung cấp. Nếu phải chấp nhận inbound correlation ID, giới hạn kích thước/ký tự, quyết định lại ở trust boundary, chống ký tự xuống dòng làm giả log; ví dụ an toàn nhất là **sinh UUID mới** tại biên ứng dụng.

## 7. Kiểm tra chất lượng quan sát và hiệu năng

Nên có bộ kiểm thử tích hợp với `WebTestClient` cho các trạng thái **200, 401, 403** và sự tồn tại của `X-Correlation-ID`, sau đó kiểm tra log trong bộ thu ghi thử nghiệm để chứng minh mọi sự kiện liên quan dùng cùng ID. Test riêng hai request chạy song song để phát hiện rò rỉ context. Test URL public, thông tin Basic sai, người dùng thường vào admin, người dùng admin vào admin, và trường hợp manager phát `Mono.empty()` hoặc phát lỗi để bảo đảm không ghi nhầm là `GRANT`.

Có thể theo dõi các metric tổng hợp, ví dụ `authn_attempts_total{mechanism,outcome}` và `authz_decisions_total{policy,outcome}`, cùng độ trễ xác thực/phân quyền theo histogram đã giới hạn nhãn. Đây là **tên metric tự định nghĩa**, không phải tên mặc định được Spring Security tự xuất cho mọi phiên bản. Không gắn `correlation_id`, `principal`, token, IP chi tiết hoặc path có ID động thành nhãn. Nếu đã bật Spring Boot Actuator/Micrometer, tận dụng HTTP server observations và chỉ thêm instrument cần thiết; giới hạn log thành công hoặc dùng sampling khi lưu lượng cao, nhưng giữ tín hiệu thất bại/đáng ngờ theo chính sách bảo mật.

Đối với sự cố, tra cứu theo thứ tự: **response status + correlation ID → có nỗ lực authn không → cơ chế và kết quả authn → policy và outcome authz → exception/luồng nghiệp vụ → trace liên dịch vụ**. Nếu chỉ thấy HTTP 401 mà thiếu sự kiện `authn_failure`, đầu tiên kiểm tra request có gửi thông tin xác thực hay không; nếu chỉ thấy 403 mà không có `authz_decision`, kiểm tra method security, handler ứng dụng và chỗ đặt instrument. Bật DEBUG/TRACE của `org.springframework.security` chỉ trong môi trường kiểm soát để chẩn đoán, không dùng làm nguồn audit lâu dài và rà soát dữ liệu có thể xuất hiện trong log.

## 8. Lỗi thường gặp và cách sửa

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `OncePerRequestFilter` hoặc `HttpSecurity` trong WebFlux | Gắn nhầm tầng Servlet, không quan sát được reactive security chain | Dùng `WebFilter`, `ServerHttpSecurity`, `SecurityWebFilterChain` |
| Kết luận “đăng nhập thất bại” cho mọi HTTP 401 | Trộn “không gửi credential” với “credential sai” | Ghi riêng authn attempt, authz decision và HTTP status |
| Ghi mỗi status 403 là “thiếu ROLE_ADMIN” | Có thể do method security, CSRF hay code nghiệp vụ | Kèm `policy` + `outcome` tại đúng điểm đánh giá |
| Chỉ dùng MDC `ThreadLocal` xuyên suốt reactive chain | Mất/sai request ID khi đổi thread | Dùng Reactor `Context` hoặc context propagation được cấu hình và kiểm thử |
| Nuốt exception bằng `onErrorResume(e -> Mono.just(GRANT))` | Làm thay đổi hành vi bảo mật và tạo lỗ hổng | Wrapper quan sát phải giữ nguyên delegate result/error |
| Log nguyên header `Authorization` hoặc JWT | Lộ credential; tăng rủi ro dữ liệu | Log mã sự kiện/loại lỗi cố định; lọc dữ liệu nhạy cảm |
| Dùng request ID/user/path làm tag metric | Bùng nổ chuỗi thời gian, chi phí cao | Giới hạn tag ở mechanism/policy/outcome hữu hạn |
| Chỉ instrument `authorizeExchange` rồi khẳng định bao phủ `@PreAuthorize` | Bỏ sót quyết định bảo mật ở service/method | Quan sát thêm reactive method authorization theo phạm vi ứng dụng |

## 9. Tiêu chí hoàn thành bài thực hành

- **Đúng nghĩa:** phân biệt ba sự kiện `authn`, `authz`, `http_response`; không suy đoán authn failure chỉ từ status.
- **Đúng tương quan:** một request có một ID trả về client và gắn với tất cả bản ghi liên quan trong chuỗi reactive; không lẫn giữa hai request song song.
- **Đúng bảo mật:** observer không thay đổi quyết định, không tiết lộ secret và không coi `ABSTAIN`/exception là `GRANT`.
- **Đúng phạm vi:** khi bổ sung OAuth2/JWT và method security, biết chính xác điểm instrument nào chưa được ví dụ HTTP Basic bao phủ.
- **Đúng hiệu năng:** log được lấy mẫu theo nhu cầu, metric có cardinality giới hạn và có công cụ truy tìm theo correlation/trace ID.

### Tài liệu chính thức

- Spring Security – Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security 6.3 – `AuthenticatedReactiveAuthorizationManager`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/authorization/AuthenticatedReactiveAuthorizationManager.html
- Spring Security 6.3 – `ServerHttpSecurity.HttpBasicSpec`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Reactor – Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Reactor – Context Propagation Support: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html