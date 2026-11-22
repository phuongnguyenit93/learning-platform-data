# Phân biệt ngữ cảnh bảo mật cục bộ với token truyền sang dịch vụ khác

> **Module:** Spring Security - reactive  
> **Nhóm:** Ngữ cảnh bảo mật  
> **Mục tiêu:** Hiểu ranh giới giữa `SecurityContext` tồn tại trong một reactive execution với access token được gửi trong HTTP request sang service khác; thực hành đọc ngữ cảnh bằng `ReactiveSecurityContextHolder`, relay Bearer token bằng `WebClient`, kiểm thử và đánh giá audience/scope, quyền nghiệp vụ.

## 1. Kết quả học tập

Sau bài này, người học cần phân biệt được bốn điều: (1) service A **đã xác thực** người gọi và lưu kết quả trong local `SecurityContext`; (2) một HTTP client của A có thể **chọn credential** khi gọi B; (3) B phải **xác thực lại credential** của request tới B; (4) B phải **tự cấp quyền** cho từng thao tác và đối tượng dữ liệu, kể cả khi A đã cho phép request trước đó.

Kết quả thực hành phải chứng minh được rằng **có local SecurityContext chưa đủ để WebClient tự gửi Bearer token**. Khi cấu hình relay filter trên WebClient được phép, token có thể được đính kèm ở header `Authorization`. Điều này không đồng nghĩa toàn bộ context, role hoặc quyền dữ liệu của A tự chuyển sang B.

## 2. Hai phạm vi: local context và HTTP credential

Giả sử client gọi `GET /api/reports/current` vào service A. A cần hỏi service B qua `GET /internal/reports/current`.

~~~text
Client
  │ Bearer access token
  ▼
Service A — Spring WebFlux
  │ 1. SecurityWebFilterChain xác thực request vào
  │ 2. Authentication nằm trong SecurityContext của Reactor pipeline A
  │ 3. Controller/Service đọc danh tính và kiểm tra quyền của A
  │ 4. WebClient tạo một HTTP request outbound mới
  │    Authorization: Bearer <credential được phép gửi>
  ▼
Service B — Spring WebFlux, process độc lập
  │ 5. SecurityWebFilterChain của B kiểm chứng token lại
  │ 6. B có SecurityContext MỚI cho request của B
  │ 7. B kiểm tra scope, tenant/owner/trạng thái dữ liệu
  ▼
Kết quả B trả về A rồi A trả về client
~~~

**Reactor Context không đi xuyên qua HTTP.** Service A và service B dù đều dùng Spring Security Reactive vẫn thuộc hai không gian bộ nhớ và hai subscription khác nhau. B không thể đọc object `SecurityContext` của A bằng cách gọi `ReactiveSecurityContextHolder` trong process của B.

| Thuộc tính | SecurityContext / Authentication cục bộ | OAuth2 access token gửi ra ngoài |
| --- | --- | --- |
| Bản chất | Trạng thái kết quả xác thực trong execution hiện hành | Credential do nhà cung cấp danh tính/authorization server cấp |
| Vị trí | Reactor Context của service đang xử lý | Thường ở header `Authorization: Bearer ...` của HTTP request |
| Ai đọc? | Code trong service hiện tại | Resource server nhận HTTP request mới |
| Nội dung | Principal, authorities, trạng thái authenticated, đôi khi có credentials | JWT đã ký hoặc opaque token; scope, audience, issuer, hạn dùng theo giao thức |
| Tự đi qua network? | **Không** | Chỉ khi outbound client/flow chủ động gửi |
| Phạm vi tin cậy | Local execution + chính sách của service A | Phạm vi được cấp cho resource server đích |
| Quyết định quyền dữ liệu B | Không thể thay quyền ở B | Token hợp lệ vẫn cần authorization nghiệp vụ của B |

**Không serialize nguyên `SecurityContext`, `Authentication` hoặc tên user thành JSON để B tin là đã đăng nhập.** Việc gửi username hay `X-User: alice` không tự tạo một bằng chứng danh tính đáng tin; nếu có mô hình trusted gateway, nó phải có cơ chế bảo vệ/chứng thực assertion và ranh giới tin cậy riêng.

## 3. SecurityContext trong Spring Security Reactive

### 3.1. Context và principal

`Authentication` biểu diễn principal và các `GrantedAuthority` được Spring Security xác thực; `SecurityContext` chứa Authentication. Ở Spring WebFlux, Spring Security gắn SecurityContext vào **Reactor Context**. Dữ liệu context đi theo **subscription**, không bị buộc vào một thread cố định.

Ví dụ method lấy tên người đang được xác thực:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> currentUserName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication())
        .map(Authentication::getName);
}
~~~

Đoạn trên là method minh họa dùng trong một Spring bean, **không** phải file Java độc lập. Nếu chưa có context, Mono có thể hoàn tất trống; controller hoặc service phải xác định chính sách cho trường hợp anonymous. Với HTTP request đã xác thực, Spring Security thiết lập context cho pipeline phù hợp.

### 3.2. Reactor Context khác ThreadLocal

Với Spring MVC Servlet, người học thường thấy `SecurityContextHolder.getContext()` liên quan tới thread. Trong WebFlux, một request có thể chuyển scheduler, còn thread event-loop phục vụ nhiều request. Dùng ThreadLocal của Servlet rồi giả định cùng một thread luôn mang user là không an toàn.

**Đúng:** đọc context trong `Mono` hoặc `Flux` bằng `ReactiveSecurityContextHolder.getContext()` và kết hợp bằng các operator như `flatMap`. `publishOn` trong **cùng subscription** vẫn hỗ trợ propagation theo Reactor Context. **Không nên** tự gọi `block()` trên event-loop hoặc tạo `subscribe()` riêng rồi trông chờ context của request ban đầu vẫn tồn tại đầy đủ.

### 3.3. Có context nhưng không có HTTP request

Ví dụ chỉ dành cho một method test:

~~~java
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

TestingAuthenticationToken auth =
    new TestingAuthenticationToken("alice", "ignored", "ROLE_USER");

Mono<String> userName = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
~~~

Khi subscribe, pipeline phát tên `alice`. Không có JWT được ký, không có HTTP request tới B và không có external authentication. `contextWrite` chỉ bổ sung thông tin vào **một reactive subscription của test**, không biến object Authentication thành credential có thể truyền qua mạng.

## 4. Access token là credential có giới hạn

HTTP Bearer credential thường có dạng:

~~~http
GET /internal/reports/current HTTP/1.1
Host: reports.example.invalid
Authorization: Bearer <access-token>
~~~

Một JWT access token có thể chứa `iss` (issuer), `sub` (subject), `aud` (audience), `exp`/`nbf` và `scope`. Service B phải kiểm tra chữ ký (hoặc introspection cho opaque token), thời hạn, issuer, audience và quyền cần thiết theo chính sách. **Chỉ giải mã payload Base64 không xác thực token.**

Phân biệt:

- **Access token:** dùng để yêu cầu quyền truy cập resource server theo phạm vi đã được cấp.
- **ID token trong OpenID Connect:** chủ yếu phục vụ xác thực người dùng tại OAuth2/OIDC client; không dùng thay access token của API B.
- **Session cookie:** có thể chứng minh người dùng đăng nhập ở website A, nhưng không mặc định được B chấp nhận như Bearer token.
- **Username/role truyền trong body hoặc header tự đặt:** không phải credential nếu không có giao thức chứng thực tin cậy.

**Bearer token là bí mật:** ai nắm được token chưa hết hạn có thể thử sử dụng token trong phạm vi còn hiệu lực. Chỉ gửi qua TLS, không log token, không trả token về JSON response, không chuyển tới host không được phép.

## 5. Bốn bước khi A gọi B

1. **Client → A:** A kiểm tra Bearer token/session của request **inbound** và tạo `Authentication` của A. Đăng nhập hợp lệ ở A không tự chứng minh quyền dùng B.
2. **Trong A:** Spring Security đặt `SecurityContext` vào Reactor Context. Controller/service A đọc principal để xử lý local và kiểm tra quyền tương ứng.
3. **A → B:** A chọn có gửi credential hay không. `WebClient` tạo **request outbound riêng**; chỉ token/header được gắn vào request mới được truyền qua mạng, không có object Reactor Context đi theo.
4. **Tại B:** B xác thực lại token, tạo SecurityContext **của B**, kiểm tra quyền route/service và quyền trên bản ghi. Nếu token không dành cho B, B phải từ chối.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Client
    participant A as Service A
    participant C as Reactor Context A
    participant B as Service B
    U->>A: GET /api/reports/current + Bearer token
    A->>A: Validate JWT / Authenticate
    A->>C: Lưu SecurityContext của A
    A->>C: Đọc principal và authorities
    A->>B: WebClient + token được phép gửi
    Note over A,B: Không gửi object SecurityContext qua mạng
    B->>B: Validate token + tạo context B + authorize
    B-->>A: 200 / 401 / 403
    A-->>U: Kết quả hoặc lỗi đã xử lý
~~~

Lưu ý: B có thể nhận cùng subject nếu A relay access token của user, nhưng đó là **một lần xác thực mới** ở B. Không tồn tại quy tắc “A đã cho phép thì B phải cho phép”.

## 6. WebClient thường không tự relay token

Code sau dùng WebClient mặc định:

~~~java
WebClient plain = WebClient.create();

Mono<String> report = plain.get()
    .uri("https://reports.example.invalid/internal/reports/current")
    .retrieve()
    .bodyToMono(String.class);
~~~

Ngay cả khi `ReactiveSecurityContextHolder.getContext()` đang có `JwtAuthenticationToken`, một WebClient thông thường **không** tự đọc Authentication rồi thêm header `Authorization`. Nếu B yêu cầu Bearer token, request không có credential có thể nhận 401.

Đừng sửa bằng cách cho B bỏ kiểm chứng JWT hoặc tin tên user do A đưa vào JSON. Thay vào đó, chọn **cơ chế outbound credential** phù hợp với hợp đồng bảo mật A → B.

## 7. Resource Server relay: ServerBearerExchangeFilterFunction

Spring Security Reactive cung cấp `ServerBearerExchangeFilterFunction`, là một WebClient `ExchangeFilterFunction`. Filter tìm `Authentication` của reactive context, lấy credential dạng `AbstractOAuth2Token` (ví dụ JWT trong `JwtAuthenticationToken`) và đặt Bearer token vào header outbound request.

~~~java
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

WebClient relay = WebClient.builder()
    .filter(new ServerBearerExchangeFilterFunction())
    .build();
~~~

Điều này **không tự lấy token mới** từ issuer và **không refresh** token hết hạn. Filter chỉ có thể truyền credential hiện có, nếu context/authentication phù hợp. Token được relay có thể bị B từ chối nếu `aud`, `scope`, `iss` hoặc hạn dùng không phù hợp.

**Nguyên tắc sử dụng:** chỉ gắn filter vào WebClient dành cho downstream tin cậy, có đích được quản lý. Mọi outgoing request sử dụng client đó đều có thể được đính kèm Bearer token; không đưa URL tùy ý từ user vào client này, cũng không giả định `baseUrl` tự chặn được URI tuyệt đối ngoài host.

## 8. Dự án mẫu Java 17+: một Resource Server A gọi B

Ví dụ thiết kế **service A** với hai endpoint:

- `GET /api/whoami` chỉ đọc principal **local**.
- `GET /api/reports/current` cần authority `SCOPE_reports.read` rồi dùng WebClient dành riêng để gọi service B tại `/internal/reports/current`.

Bài dùng Spring Boot **3.3.13** để minh họa Spring Security 6.x và tương thích với nhánh lab; Spring Boot 3.3 đã hết hỗ trợ mã nguồn mở, nên sản phẩm mới phải dùng phiên bản còn được hỗ trợ. Các file dưới đây là dự án độc lập đủ cho **biên dịch và chạy unit test**. Chạy end-to-end cần một issuer thật, token hợp lệ và service B thật; tên miền `example.invalid` chỉ là ví dụ.

### 8.1. Cấu trúc

~~~text
reactive-context-vs-token/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/context/
    │   │   ├── ContextVsTokenApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── ReportWebClientConfig.java
    │   │   ├── ReportClient.java
    │   │   └── ApiController.java
    │   └── resources/application.yml
    └── test/java/example/context/
        └── TokenPropagationTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-context-vs-token</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
~~~

Không thêm `spring-boot-starter-web` vì lab theo mô hình WebFlux.

### 8.3. Application entrypoint

File `src/main/java/example/context/ContextVsTokenApplication.java`:

~~~java
package example.context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextVsTokenApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContextVsTokenApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig của service A: xác thực **inbound**

File `src/main/java/example/context/SecurityConfig.java`:

~~~java
package example.context;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/whoami")
                    .authenticated()
                .pathMatchers(HttpMethod.GET, "/api/reports/current")
                    .hasAuthority("SCOPE_reports.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Rule này **chỉ quyết định ai vào được A**. `SCOPE_reports.read` giả định scope JWT được ánh xạ theo mặc định có prefix `SCOPE_`. Với claim quyền không chuẩn, phải cấu hình converter riêng. Ngoài các validator mặc định, cần audience validation dành cho A.

### 8.5. WebClient outbound được cấu hình relay

File `src/main/java/example/context/ReportWebClientConfig.java`:

~~~java
package example.context;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportWebClientConfig {

    @Bean("reportWebClient")
    WebClient reportWebClient(
            WebClient.Builder builder,
            @Value("${app.reports.base-url}") String baseUrl) {

        return builder.clone()
            .baseUrl(baseUrl)
            .filter(new ServerBearerExchangeFilterFunction())
            .build();
    }
}
~~~

Chỉ bean `reportWebClient` dùng relay filter. Bean riêng hạn chế phạm vi sử dụng credential; vẫn cần tránh dùng URI tuyệt đối hoặc redirect tới host không tin cậy. `@Value` lấy một property cấu hình ở phần YAML dưới đây.

### 8.6. Gọi B trong cùng reactive pipeline

File `src/main/java/example/context/ReportClient.java`:

~~~java
package example.context;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReportClient {

    private final WebClient reportWebClient;

    public ReportClient(
            @Qualifier("reportWebClient") WebClient reportWebClient) {
        this.reportWebClient = reportWebClient;
    }

    public Mono<String> loadCurrentReport() {
        return reportWebClient.get()
            .uri("/internal/reports/current")
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

Đây là HTTP call tới B. Khi chain được subscribe trong request đã xác thực, filter có thể lấy token từ local `Authentication` và thêm `Authorization: Bearer ...` vào request ra. Method **không** gọi `block()` hoặc tạo subscription riêng bằng `subscribe()`; điều đó giúp không phá pipeline/context và tránh blocking event-loop.

### 8.7. Controller phân biệt hai thao tác

File `src/main/java/example/context/ApiController.java`:

~~~java
package example.context;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    private final ReportClient reports;

    public ApiController(ReportClient reports) {
        this.reports = reports;
    }

    @GetMapping("/api/whoami")
    public Mono<Map<String, String>> whoAmI() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> Map.of(
                "principal", ctx.getAuthentication().getName()
            ));
    }

    @GetMapping("/api/reports/current")
    public Mono<String> currentReport() {
        return reports.loadCurrentReport();
    }
}
~~~

`whoAmI()` chỉ đọc local principal; `currentReport()` cần một HTTP request mới. Sự khác nhau này tồn tại dù hai method nằm cùng controller và do cùng user gọi.

### 8.8. application.yml

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.invalid/realms/lab

app:
  reports:
    base-url: https://reports.example.invalid
~~~

Các URL `.invalid` chỉ minh họa. Để chạy hệ thống thật, thay issuer bằng IdP có metadata/JWKS hợp lệ và thay base URL bằng service B tin cậy qua HTTPS. Đặt cấu hình thực tế bằng secret/config management phù hợp; không cho phép một request parameter bất kỳ tự quyết định host nhận token.

`issuer-uri` không tự bảo đảm token được cấp cho đúng audience của A và B. Cần kiểm tra audience riêng cho mỗi Resource Server. Khi B không chấp nhận token gốc của A, phải chọn token được cấp đúng cho B, không tắt validation chỉ để nhận token.

## 9. Kiểm thử ba trường hợp bằng ExchangeFunction giả lập

Không cần tạo JWT ký thật để chứng minh **có/không có Bearer header được gửi outbound**. Test dưới đây dùng `JwtAuthenticationToken` giả đặt trong Reactor Context và một `ExchangeFunction` trả phản hồi `report-ok`. Không kết nối mạng, không cần IdP, không sử dụng credential production.

File `src/test/java/example/context/TokenPropagationTest.java`:

~~~java
package example.context;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TokenPropagationTest {

    private static final String DESTINATION =
        "https://reports.example.invalid/internal/reports/current";

    private JwtAuthenticationToken fakeAuthentication() {
        Jwt jwt = Jwt.withTokenValue("fake-test-token")
            .header("alg", "RS256")
            .claim("sub", "alice")
            .claim("scope", "reports.read")
            .build();

        return new JwtAuthenticationToken(
            jwt,
            List.of(new SimpleGrantedAuthority("SCOPE_reports.read"))
        );
    }

    private WebClient fakeClient(
            AtomicReference<String> capturedAuth,
            boolean enableRelay) {

        WebClient.Builder builder = WebClient.builder()
            .exchangeFunction(request -> {
                capturedAuth.set(
                    request.headers().getFirst(HttpHeaders.AUTHORIZATION)
                );
                return Mono.just(
                    ClientResponse.create(HttpStatus.OK)
                        .body("report-ok")
                        .build()
                );
            });

        if (enableRelay) {
            builder.filter(new ServerBearerExchangeFilterFunction());
        }

        return builder.build();
    }

    @Test
    void localContextDoesNotAutomaticallySendBearer() {
        AtomicReference<String> observed = new AtomicReference<>();
        WebClient plain = fakeClient(observed, false);

        Mono<String> call = plain.get()
            .uri(DESTINATION)
            .retrieve()
            .bodyToMono(String.class)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    fakeAuthentication()
                )
            );

        StepVerifier.create(call)
            .expectNext("report-ok")
            .verifyComplete();

        assertNull(observed.get());
    }

    @Test
    void relayFilterSendsBearerFromReactiveContext() {
        AtomicReference<String> observed = new AtomicReference<>();
        WebClient relay = fakeClient(observed, true);

        Mono<String> call = relay.get()
            .uri(DESTINATION)
            .retrieve()
            .bodyToMono(String.class)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    fakeAuthentication()
                )
            );

        StepVerifier.create(call)
            .expectNext("report-ok")
            .verifyComplete();

        assertEquals("Bearer fake-test-token", observed.get());
    }

    @Test
    void noContextMeansNoBearerToRelay() {
        AtomicReference<String> observed = new AtomicReference<>();
        WebClient relay = fakeClient(observed, true);

        Mono<String> call = relay.get()
            .uri(DESTINATION)
            .retrieve()
            .bodyToMono(String.class);

        StepVerifier.create(call)
            .expectNext("report-ok")
            .verifyComplete();

        assertNull(observed.get());
    }
}
~~~

Trong thư mục chứa `pom.xml`:

~~~bash
mvn clean test
~~~

| Kiểm thử | Có local Authentication? | Có relay filter? | Authorization gửi tới fake B |
| --- | --- | --- | --- |
| `localContextDoesNotAutomaticallySendBearer` | Có, JWT Authentication giả | Không | **Không có header** |
| `relayFilterSendsBearerFromReactiveContext` | Có, JWT Authentication giả | Có | **Bearer fake-test-token** |
| `noContextMeansNoBearerToRelay` | Không | Có | **Không có header** |

**Giới hạn test:** `Jwt.withTokenValue("fake-test-token")` chỉ tạo một object cho unit test, **không** ký JWT, không xác minh chữ ký, không gọi network và không kiểm tra B. Token giả không thể dùng như access token thật. Muốn chứng minh security end-to-end phải thêm integration test với issuer/test keys và B có xác thực thật.

## 10. Service B phải tạo context riêng và cấp quyền riêng

Một đoạn cấu hình minh họa **bên trong project riêng của B**:

~~~java
@Bean
SecurityWebFilterChain downstreamSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers(HttpMethod.GET, "/internal/reports/current")
                .hasAuthority("SCOPE_reports.read")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .build();
}
~~~

Trích đoạn này dùng cùng import như `SecurityConfig.java` ở trên; **không** được coi là service B độc lập nếu chưa có Spring Boot app, decoder, endpoint và issuer configuration của B.

Khi B nhận request, B cần kiểm tra:

1. Chữ ký JWT / opaque introspection, issuer và hạn sử dụng.
2. **Audience dành riêng cho B**, không chỉ issuer. Token hợp lệ cho A chưa chắc hợp lệ cho B.
3. Scope/role cần cho endpoint; authority mapping đúng quy ước.
4. Owner/tenant/quyền trên đối tượng và trạng thái nghiệp vụ.
5. Phạm vi dữ liệu response, log và cache.

Không thể “mượn” quyết định `hasAuthority("SCOPE_reports.read")` tại A để bỏ qua authorization ở B. A chỉ quyết định người gọi có được thực hiện thao tác **qua A**; B quyết định credential đến B được làm gì **trên tài nguyên của B**.

## 11. Audience và scope: khi nào relay nguyên token là sai?

Giả sử token inbound của A có claims minh họa:

~~~json
{
  "iss": "https://issuer.example.invalid/realms/lab",
  "sub": "alice",
  "aud": ["api-a"],
  "scope": "profile.read",
  "exp": 2000000000
}
~~~

Đây chỉ là **payload minh họa**, không phải token đã ký. Service B yêu cầu `aud=reports-api` và `reports.read`. Nếu A chuyển nguyên token có `aud=["api-a"]` sang B thì **B phải từ chối**. A không thể tự sửa audience/scope trong token rồi giữ nguyên chữ ký.

Có các lựa chọn:

| Trường hợp | Cách xử lý | Phải kiểm tra |
| --- | --- | --- |
| Access token ban đầu **được phép** dùng ở cả A và B | Relay token hiện có | Audience, scope, expiry, owner/tenant tại B |
| Token chỉ dành cho A | OAuth2 token exchange / on-behalf-of | IdP hỗ trợ flow, token mới có audience/scope B |
| A gọi B dưới quyền của chính service A | OAuth2 client credentials | B xác thực machine identity; không nhầm là user delegation |
| A đăng nhập user bằng session/OIDC | OAuth2 authorized client hoặc flow delegation hợp lệ | Dùng **access token** cho B, không dùng cookie/ID token |
| B không cần credential | Không gửi token | Không làm rò token không cần thiết |

**Token exchange** là việc nhờ IdP phát access token mới theo chính sách delegation, không phải việc sửa payload hoặc copy một header sang host khác. Grant/flow được hỗ trợ tùy phiên bản Spring Security và nhà cung cấp danh tính.

**Client credentials** định danh máy/dịch vụ, không tự mang quyền của Alice. Nếu B cần biết Alice đang xin xem báo cáo thuộc tenant nào, thiết kế phải dùng on-behalf-of/delegation hoặc cơ chế tin cậy khác có audit minh bạch.

## 12. Resource Server relay khác OAuth2 Client authorized client

### 12.1. ServerBearerExchangeFilterFunction

Đây là cơ chế ở mục 7: **tái sử dụng OAuth2 token credential** trong local Authentication, không tự xin mới/refresh. Phù hợp khi A là Resource Server và token đầu vào đã hợp lệ cho downstream B.

### 12.2. ServerOAuth2AuthorizedClientExchangeFilterFunction

Khi A đóng vai **OAuth2 Client**, Spring Security có `OAuth2AuthorizedClient` và `ReactiveOAuth2AuthorizedClientManager` để lấy/lưu/refresh access token theo grant được hỗ trợ. WebClient có thể tích hợp bằng filter riêng:

~~~java
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
WebClient oauth2WebClient(
        ReactiveOAuth2AuthorizedClientManager manager) {

    ServerOAuth2AuthorizedClientExchangeFilterFunction filter =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return WebClient.builder()
        .filter(filter)
        .build();
}
~~~

Đây là đoạn cấu hình **cần môi trường OAuth2 Client/ClientRegistration thật**; ví dụ project A ở mục 8 **chỉ dùng Resource Server**, nên chưa có sẵn manager/registration cho đoạn này.

Có thể chọn authorized client hoặc clientRegistrationId rõ ràng cho từng request. **Tránh bật mặc định gắn token user vào tất cả HTTP requests** (như `setDefaultOAuth2AuthorizedClient(true)`) nếu WebClient có thể đi tới host không chủ đích; tài liệu Spring Security cảnh báo nguy cơ đính kèm access token rộng hơn mong muốn.

### 12.3. OIDC login không đồng nghĩa có token trong Authentication.credentials

`oauth2Login()` thường biểu diễn login của user bằng `OAuth2AuthenticationToken` và access token được quản lý qua `OAuth2AuthorizedClient`. Điều đó khác JWT của Resource Server được chứa trong `JwtAuthenticationToken`. Không giả định `ServerBearerExchangeFilterFunction` luôn tìm thấy access token chỉ vì người dùng đã đăng nhập bằng OIDC. Phải sử dụng OAuth2 Client flow phù hợp và xác định loại token cần gửi sang B.

## 13. Những ranh giới dễ làm mất hoặc lộ context

| Xử lý | Local SecurityContext | Token tới B |
| --- | --- | --- |
| Controller → Service nối chuỗi `Mono.flatMap` | Có thể giữ qua cùng subscription | Không tự gửi |
| `publishOn` trong cùng pipeline Reactor | Context đi theo subscription | Không tự gửi |
| `WebClient.create()` không filter | Local context vẫn có ở A | Không tự có Bearer |
| WebClient có `ServerBearerExchangeFilterFunction` | Đọc authentication từ context | Có thể relay Bearer đúng điều kiện |
| Tạo thread riêng/đọc Servlet ThreadLocal | Không bảo đảm | Không tự gửi |
| Tự gọi `subscribe()` ở luồng tách rời | Không bảo đảm kế thừa đúng context | Không tự gửi |
| B nhận HTTP từ A | B chỉ có context mới sau xác thực | B nhận credential ở request |
| Scheduled job hoặc message consumer | Không tự có identity của HTTP request cũ | Cần service/delegated identity phù hợp |

Đừng dùng `block()` để “lấy principal rồi đi gọi B”, hoặc đưa access token vào một biến static để callback về sau dùng. Với request chạy lâu, queue hay scheduled worker, token có thể hết hạn hoặc user đã bị thu hồi quyền. Thiết kế execution identity riêng cho các công việc đó.

Correlation ID / W3C trace context dùng để theo dõi call qua service, **không phải credential**. Không lấy `traceparent` hay tên user trong log làm căn cứ authorization.

## 14. Xử lý lỗi 401, 403 và lỗi từ downstream

| Vị trí thất bại | Ví dụ | Bản chất |
| --- | --- | --- |
| A inbound authentication | Thiếu/sai Bearer token vào A | A có thể trả **401** |
| A inbound authorization | Token hợp lệ, thiếu `SCOPE_reports.read` | A có thể trả **403** |
| A outbound credential | WebClient không relay, B nhận request không có token | B trả **401** |
| B token validation | Token đúng với A, sai audience B hoặc đã hết hạn | B từ chối (thường **401**) |
| B authorization | Token hợp lệ cho B nhưng thiếu scope/owner/tenant | B từ chối (**403/404** theo policy) |
| A đọc phản hồi B | `retrieve()` gặp 4xx/5xx | WebClient mặc định phát lỗi reactive; status trả về client A cần mapping riêng |

Không thể suy ra “Reactor Context bị mất” chỉ từ 401 của B. Hãy kiểm tra từng ranh giới theo thứ tự: **A inbound token → A SecurityContext → WebClient filter → có/không header outbound → B token validation → B authorization**. Khi logging, chỉ ghi kết quả và thông tin an toàn, **không ghi giá trị Bearer token**.

## 15. An toàn khi chuyển credential giữa các service

1. **Giới hạn đích:** relay chỉ tới host/đường dẫn nằm trong allowlist. Một URL tuyệt đối truyền vào WebClient có thể ghi đè base URL; nếu URL do user điều khiển, token có thể bị gửi sang domain của attacker (SSRF/credential leakage).
2. **TLS:** dùng HTTPS trên đường mạng; Bearer token là bí mật, Base64/JWT serialization không phải encryption. Kiểm soát redirect để token không vô tình đi sai host.
3. **Không log token:** tránh in header `Authorization`, cookie, raw JWT, refresh token trong request logs, tracing spans, proxy logs và stack traces.
4. **Scope/audience tối thiểu:** chỉ yêu cầu quyền cần thiết cho B. Không tắt audience check của B để làm cho token gốc A “chạy được”.
5. **Quyền object/tenant:** scope chung không tự cho phép truy cập mọi báo cáo hoặc dữ liệu của user khác. B kiểm tra quyền trên từng đối tượng ở service/repository.
6. **Giới hạn vòng đời:** không giữ access token vào global/static cache hoặc queue dài hạn mà không có chính sách hạn dùng/refresh/revocation.
7. **Chống nhầm danh tính:** không khai user đang hành động tại B khi outbound thực tế dùng `client_credentials` của A. Cần audit rõ actor và delegation.
8. **Bảo vệ sai số môi trường:** unit test có fake token và stub HTTP chỉ xác minh wiring; phải thêm integration test cho JWT verifier, audience/scope, TLS và quyền nghiệp vụ của B.

## 16. Lỗi thường gặp và cách sửa

| Lỗi | Giải thích | Cách xử lý |
| --- | --- | --- |
| “Đọc được principal ở A thì WebClient sẽ có token” | Local context khác outgoing Authorization | Thêm cơ chế outbound được phép, test header |
| “Cứ có token là gửi mọi service” | Token có audience/scope và trust boundary | Chỉ relay đúng đích; cần token exchange nếu B yêu cầu token riêng |
| “B tin A đã xác thực” | B là resource server độc lập | B xác thực lại token và phân quyền |
| “Gửi ID token cho B” | ID token không phải access token cho API | Lấy access token đúng resource |
| “Spring OAuth2 login tự được relay bằng Resource Server filter” | Access token có thể nằm trong OAuth2AuthorizedClient | Dùng OAuth2 Client filter/authorized client phù hợp |
| “Gắn relay filter cho WebClient dùng chung” | Mọi URI qua client đều có nguy cơ nhận credential | Dùng bean riêng, kiểm soát host, redirect, egress |
| “B trả 401 vì local context sai” | B có thể từ chối issuer/audience/expiry/token thiếu | Phân biệt inbound/outbound/B validation bằng test |
| “Header X-Username đủ để B tin danh tính” | Header tùy ý không có proof | Dùng token/assertion có xác thực và ranh giới tin cậy |
| “JWT giả trong unit test chứng minh bảo mật production” | Test không có chữ ký, IdP, audience hoặc B | Tạo integration test cho các validator và API thật |
| “block()/subscribe() để lấy user nhanh” | Có thể phá pipeline và mất context | Giữ luồng Mono/Flux, dùng flatMap và context đúng |

## 17. Bài tập thực hành

**Bài A — quan sát local:** thêm một method đọc `ReactiveSecurityContextHolder.getContext()` và trả principal. Giải thích vì sao chạy thành công trong A **không** có nghĩa B được cấp danh tính đó.

**Bài B — chứng minh outbound:** chạy ba test của mục 9. Thử bỏ filter trong test thứ hai; dự đoán assertion nào fail. Khôi phục và giải thích việc filter lấy token từ đâu.

**Bài C — thiết kế audience:** token client cấp có `aud=["api-a"]`; B yêu cầu `aud=reports-api`. Viết lựa chọn giữa relay, token exchange và client credentials; giải thích vì sao không được tắt audience validation của B.

**Bài D — phân quyền dữ liệu:** Alice và Bob đều có `reports.read`, nhưng report 42 thuộc Bob. Khi Alice gọi B qua A, bước nào ngăn Alice xem report 42? Viết test âm tính tại B cho owner/tenant.

**Bài E — chống lộ token:** mô tả kịch bản attacker đưa URL tuyệt đối vào một WebClient đang gắn relay filter. Sửa thiết kế chỉ cho URI tương đối tới service B được cấu hình và thêm kiểm soát outbound host/redirect. Không dùng credential thật trong bài lab.

**Bài F — so sánh OAuth2 Login:** A xác thực người dùng qua OIDC session, có `OAuth2AuthorizedClient`. Giải thích vì sao Resource Server relay filter có thể không lấy được access token và cách dùng OAuth2 Client manager/filter thay thế.

## 18. Checklist hoàn thành

- [ ] Phân biệt local `SecurityContext` với `Authorization: Bearer ...`.
- [ ] Hiểu Reactor Context nằm trong một execution/subscription, không tự đi qua mạng.
- [ ] Đọc principal bằng `ReactiveSecurityContextHolder` thay vì tin vào Servlet ThreadLocal.
- [ ] Biết một WebClient thường không tự truyền token.
- [ ] Biết `ServerBearerExchangeFilterFunction` có thể relay OAuth2 token credential hiện có, không tự làm token exchange/refresh.
- [ ] Test có context nhưng **không filter** thì không có header Authorization.
- [ ] Test có context **và** relay filter thì có Bearer header fake.
- [ ] Test **không context** thì filter không tự tạo token.
- [ ] B vẫn xác thực token và kiểm tra audience, scope, tenant và owner.
- [ ] Phân biệt relay, OAuth2 Client authorized client, token exchange và service client credentials.
- [ ] Nhận diện rủi ro log token, token gửi sai host, JWT sai audience và dùng ID token sai mục đích.

## 19. Câu hỏi tự kiểm tra

1. Hai service Spring WebFlux có chung một `Reactor Context` không? Vì sao?
2. `Authentication.getName()` ở A trả `alice` thì B đã biết Alice chưa?
3. Khi nào `ServerBearerExchangeFilterFunction` có token để thêm vào HTTP outbound request?
4. Vì sao `WebClient.create()` không tự relay Bearer dù trong A có `JwtAuthenticationToken`?
5. Nếu JWT chỉ cấp cho A, sửa audience và gửi sang B có hợp lệ không?
6. `oauth2Login()` khác Resource Server JWT ở nơi quản lý access token như thế nào?
7. B trả 401 và A vẫn đọc được principal: nên kiểm tra những điểm nào?
8. Vì sao `client_credentials` của A không tự chứng minh Alice có quyền trên report của B?
9. Test fake JWT của mục 9 chứng minh được lớp nào và chưa chứng minh được lớp nào?
10. Tại sao correlation ID hoặc `X-User` không thay thế được OAuth2 access token?

## 20. Tài liệu tham khảo chính thức

- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context và `ReactiveSecurityContextHolder`.
- [Spring Security — Bearer Token Propagation](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/bearer-tokens.html): `ServerBearerExchangeFilterFunction` và đặc tính không refresh token.
- [Spring Security — OAuth2 Client Authorized Client Features](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html): WebClient filter cho `OAuth2AuthorizedClient` và cảnh báo về default bearer propagation.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): OAuth2 client, manager, authorization grants.
- [Spring Security — Reactive Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html): JWT/opaque token validation tại B.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Context theo subscription và khác ThreadLocal.
- [Spring Cloud Gateway — TokenRelay](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html): trường hợp dùng gateway; đây là thành phần riêng, không phải mọi WebFlux app tự có.

**Kết luận:** `SecurityContext` là kết quả xác thực **cục bộ của service đang thực thi**. Access token là credential có thể được gửi sang resource server khác, nhưng chỉ khi client được cấu hình, token được phép sử dụng đúng audience/scope và kết nối bảo vệ token. Service B phải xác thực và cấp quyền riêng; không có sự tự động chuyển nguyên SecurityContext của A thành SecurityContext của B.