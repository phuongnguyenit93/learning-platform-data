# Cấu hình Authorization Code và Client Credentials theo loại ứng dụng — Spring Security Reactive

## 1. Mục tiêu bài học

Khi dùng **Spring WebFlux** như một **OAuth2 Client**, bạn phải trả lời câu hỏi trước tiên: **“Ứng dụng đang xin quyền thay mặt người dùng hay xin quyền cho chính nó?”** Hai mục tiêu dẫn đến hai loại grant rất khác nhau:

- **Authorization Code**: có người dùng tương tác. Ứng dụng chuyển trình duyệt đến Authorization Server, nhận authorization code qua callback, kiểm tra `state` và các điều kiện cần thiết, rồi đổi code lấy token. Luồng đăng nhập thường được kết hợp **OpenID Connect (OIDC)** khi muốn biết danh tính người dùng. **PKCE** bảo vệ authorization code, đặc biệt bắt buộc về thiết kế với public clients.
- **Client Credentials**: một service/backend tin cậy tự chứng minh danh tính tại token endpoint và lấy access token **cho workload/application**, không có người dùng, không mở trình duyệt, không có callback OAuth2 login. Grant này dành cho gọi API máy–máy, batch job hoặc queue worker.

Bài sẽ so sánh grant theo **server-rendered web app, BFF, SPA, mobile, background job và microservice**, hướng dẫn cấu hình hai client registrations trong Spring Boot 3.x, sử dụng `ServerHttpSecurity.oauth2Login()` với người dùng và `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` với service token; đồng thời trình bày Java 17+, `WebClient`, kiểm thử và các lỗi bảo mật thường gặp.

> **Phạm vi:** Spring Security 6.x **Reactive**, không phải servlet `HttpSecurity`/`ServletOAuth2AuthorizedClientExchangeFilterFunction`. OAuth2 Client là **bên xin token**, không phải Authorization Server phát token hay Resource Server xác minh Bearer token. Một ứng dụng có thể đóng nhiều vai trò nhưng phải tách ranh giới và cấu hình.

## 2. Chọn grant theo loại ứng dụng

| Ứng dụng hoặc công việc | Có người dùng? | Grant khuyến nghị | Điều phải tránh |
| --- | --- | --- | --- |
| Web app chạy server-side, có session/cookie | Có | **Authorization Code**; OIDC nếu cần login | Đẩy client secret/access token xuống HTML/JS |
| **BFF** phục vụ SPA | Có | BFF thực hiện Authorization Code, giữ tokens ở server | Cho browser tự giữ secret của BFF |
| SPA chỉ chạy trên browser | Có | **Authorization Code + PKCE**, public client; cân nhắc BFF | **Client Credentials trong JavaScript** |
| Mobile/desktop native | Có | Authorization Code + PKCE qua system browser | Hardcode secret rồi coi là bí mật an toàn |
| Backend gọi API theo quyền user đăng nhập | Có | Token delegated từ Authorization Code; đúng scope/audience | Dùng machine token toàn quyền thay user |
| Microservice A gọi B cho nghiệp vụ riêng của A | Không | **Client Credentials** | Dùng username/password người dùng “robot” |
| Batch, cron, queue consumer | Không | **Client Credentials**, manager không phụ thuộc HTTP request | Đòi `ServerWebExchange` hoặc browser callback |
| Public client không thể giữ secret | Có/không | Authorization Code + PKCE nếu cần user | Phát application token bằng client secret công khai |

**Quy tắc quyết định:**

1. Cần người dùng cấp quyền hoặc đăng nhập → **Authorization Code**.
2. Cần ứng dụng tự gọi API không mang user → **Client Credentials**.
3. Cần danh tính người dùng → **OIDC** với `openid`, kiểm chứng ID token/nonce/issuer/audience theo cấu hình provider.
4. Cần người dùng và machine cùng gọi một API → Resource Server phải **phân biệt token loại nào được chấp nhận cho endpoint nào**; hai grants không hoán đổi.

`Client Credentials` không có “đăng nhập người dùng đơn giản hóa”. Trong token đó, `sub` (nếu có) có thể biểu diễn client/service identity; không được coi nó là chủ tài khoản người dùng.

## 3. So sánh bản chất OAuth2 Grant

| Khía cạnh | Authorization Code | Client Credentials |
| --- | --- | --- |
| Actor chính | Resource owner/user + client | Confidential client/service |
| Bước `/authorize` | **Có**, redirect trình duyệt | **Không** |
| Token endpoint | `grant_type=authorization_code`, có `code`; PKCE verifier nếu dùng | `grant_type=client_credentials` và client authentication |
| Callback/redirect URI | **Có**, phải được allowlist | **Không** |
| `state` | Dùng để liên kết callback với yêu cầu ban đầu | Không có browser callback tương đương |
| PKCE | Nên dùng; thiết yếu với public clients | Không phải cơ chế của grant này |
| Client secret | Confidential client dùng; public client không giữ secret | Confidential client phải xác thực bằng phương thức được AS hỗ trợ |
| Access token đại diện | User-delegated authorization | Application/workload authorization |
| Refresh token | Có thể được cấp, phụ thuộc provider | Thông thường không có; xin access token mới khi hết hạn |
| Token storage | Theo user/authorized client và session strategy | Theo registration + workload principal/service |
| Khi nào bị lạm dụng | Mất `state`, mất PKCE, sai redirect URI, lộ token | Lộ client secret, token quyền cao, confused deputy |

### OAuth2 và OIDC

OAuth 2.0 tập trung vào **ủy quyền truy cập tài nguyên**; OIDC bổ sung **ID token** và quy tắc xác thực danh tính. Một ứng dụng “Đăng nhập bằng IdP” thường chọn Authorization Code với scope `openid` và cấu hình OIDC provider thực. **ID token không thay thế access token** khi gọi Resource Server, trừ khi API có hợp đồng đặc biệt đã xác minh; JWT nói chung cũng không có nghĩa là ID token.

## 4. Luồng Authorization Code trong Spring WebFlux

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant C as Spring WebFlux OAuth2 Client
    participant A as Authorization Server
    participant R as Resource Server
    B->>C: GET /oauth2/authorization/browser
    C->>C: Tạo authorization request, state, PKCE
    C-->>B: 302 đến authorization endpoint
    B->>A: GET /authorize?response_type=code&client_id&state...
    A-->>B: Login và consent
    B->>C: GET /login/oauth2/code/browser?code=...&state=...
    C->>C: Khôi phục request gốc; kiểm tra state
    C->>A: POST /token grant_type=authorization_code
    A-->>C: Access token (và token khác nếu được cấp)
    C->>C: OIDC/user validation, lưu Authentication/authorized client
    C-->>B: Redirect về ứng dụng
    C->>R: API request + Bearer user access token
    R-->>C: Response theo quyền user
~~~

Theo mặc định, endpoint bắt đầu luồng là:

~~~text
GET /oauth2/authorization/{registrationId}
~~~

và callback mặc định là:

~~~text
GET /login/oauth2/code/{registrationId}?code=...&state=...
~~~

Trong Spring Security Reactive:

- `DefaultServerOAuth2AuthorizationRequestResolver` xây `OAuth2AuthorizationRequest` từ `ClientRegistration`.
- `OAuth2AuthorizationRequestRedirectWebFilter` lưu request rồi redirect sang Authorization Server.
- `ServerAuthorizationRequestRepository` thường lưu request tạm trong `WebSession`, để callback đối chiếu `state` cùng các attributes phục vụ PKCE/OIDC.
- OAuth2 login authentication flow xử lý callback, token exchange và xác thực user.
- `ServerOAuth2AuthorizedClientRepository` / `ReactiveOAuth2AuthorizedClientService` lưu `OAuth2AuthorizedClient` sau khi token được cấp.
- `ServerSecurityContextRepository` lưu `SecurityContext`/`Authentication` theo chính sách đăng nhập.

**Không nhầm ba kho dữ liệu:** authorization-request repository giữ `state` **trước** callback; authorized-client store giữ tokens **sau** cấp quyền; security-context repository giữ **danh tính đã xác thực** cho request tiếp theo.

### Vai trò của PKCE

Client tạo `code_verifier` ngẫu nhiên và gửi `code_challenge` (thường là `S256`) ở authorize request. Khi đổi code lấy token, client gửi `code_verifier` gốc để Authorization Server xác minh. Public SPA/mobile không thể giữ client secret có ý nghĩa, vì vậy cần PKCE, cùng bảo vệ `state`/redirect URI và tránh mất verifier trong session/authorization-request store. Với confidential server-side client, secret và PKCE có thể bổ trợ nhau khi provider hỗ trợ.

### Cảnh báo redirect URI

Tham số:

~~~yaml
redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

phải khớp redirect URI mà IdP cho phép. Khi ứng dụng ở sau proxy, `{baseUrl}` phải là HTTPS public host/path, không phải host nội bộ. Chỉ tin forwarded headers từ proxy đã cấu hình đáng tin; không dựa vào một tham số `redirect_uri` tùy ý do client gửi.

## 5. Luồng Client Credentials cho backend và job

~~~mermaid
sequenceDiagram
    participant S as Service A
    participant A as Authorization Server
    participant R as Resource Server B
    S->>A: POST /token grant_type=client_credentials + client authentication
    A->>A: Verify client_id, method, scopes, audience
    A-->>S: access_token, token_type, expires_in
    S->>R: GET /internal/data + Authorization: Bearer access_token
    R->>R: Verify signature/introspection, iss, aud, scope
    R-->>S: 200 hoặc 401/403 theo permission
~~~

**Không có** `/oauth2/authorization/...`, `/login/oauth2/code/...` hay session của user. Một backend chỉ cần giao tiếp máy–máy không phải cấu hình `oauth2Login()`.

Token endpoint có thể nhận yêu cầu dạng:

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials-encoded>

grant_type=client_credentials&scope=inventory.read
~~~

`client_secret_basic` là một client-authentication method phổ biến; provider khác có thể yêu cầu `client_secret_post`, private-key JWT hoặc phương thức phù hợp khác. **HTTP Basic chỉ an toàn khi dùng TLS**; Base64 không mã hóa secrets. Không phát client secret xuống browser, mobile app hay public repository.

Token `client_credentials` thường chỉ có **access token**. Khi sắp hết hạn hoặc đã hết hạn, client manager thường xin token mới bằng cùng grant; không đòi refresh token. Resource Server vẫn phải kiểm tra chữ ký/introspection, `iss`, `aud`, thời hạn, scope và quyền workload.

## 6. Vai trò của các lớp Reactive OAuth2 Client

| Lớp/interface | Dùng để làm gì |
| --- | --- |
| `ClientRegistration` | Client ID, authentication method, grant, redirect URI, scopes, endpoints |
| `ReactiveClientRegistrationRepository` | Tìm registration theo `registrationId` |
| `ReactiveOAuth2AuthorizedClientManager` | Xin/mở rộng/quản lý authorized client qua provider |
| `ReactiveOAuth2AuthorizedClientProvider` | Strategy từng grant như Authorization Code, refresh token, Client Credentials |
| `DefaultReactiveOAuth2AuthorizedClientManager` | Quản lý authorized client trong ngữ cảnh `ServerWebExchange` |
| `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | Quản lý ngoài web request, phù hợp background/service app |
| `ServerOAuth2AuthorizedClientRepository` | Authorized-client persistence theo web request |
| `ReactiveOAuth2AuthorizedClientService` | Authorized-client persistence ở mức ứng dụng |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Thêm Bearer token vào outbound `WebClient` theo authorized client |
| `OAuth2AuthorizedClient` | Registration + access token và có thể refresh token, gắn với principal |
| `ServerHttpSecurity.oauth2Login` | Thiết lập redirect/callback đăng nhập người dùng trên WebFlux |
| `ServerHttpSecurity.oauth2Client` | Các tính năng OAuth2 Client outbound trong ngữ cảnh web |
| `SecurityWebFilterChain` | Bảo vệ inbound HTTP; khác Resource Server token validation |

Điểm quan trọng: **`DefaultReactiveOAuth2AuthorizedClientManager` được thiết kế để dùng trong `ServerWebExchange`**. Tài liệu Spring Security 6.5 hướng dẫn dùng **`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`** cho những service chạy ngoài HTTP request, như scheduler/queue consumer.

Ngay cả với Client Credentials, `OAuth2AuthorizeRequest` gửi cho manager cần một **principal ổn định để làm khóa lưu authorized client**. Ví dụ `"workload-inventory"` là cache identity nội bộ, **không phải username Alice hay Bob**.

## 7. Ví dụ Java 17+: hai registrations trong cùng ứng dụng WebFlux

Ví dụ dùng Spring Boot 3.x / Spring Security 6.x. Nó khởi động và chạy các test registration/redirect/service token propagation mà **không cần IdP thật**. Để hoàn tất OAuth2 login hoặc gọi resource API qua token endpoint, phải thay domain demo bằng provider/Resource Server có thật và client credentials được cấp phát chính thức.

### 7.1. Dependencies

Thêm vào dự án Gradle đã cấu hình Spring Boot plugin, repositories và Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Không thêm `spring-boot-starter-web` nếu ví dụ này cần chạy WebFlux thay vì Servlet. Hãy dùng Spring Boot BOM quản lý dependencies; không trộn các Spring Security jars khác phiên bản.

### 7.2. `src/main/resources/application.yml`

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          browser:
            provider: demo
            client-id: demo-browser-client
            client-secret: demo-browser-secret
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: profile

          machine:
            provider: demo
            client-id: demo-machine-client
            client-secret: demo-machine-secret
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: inventory.read

        provider:
          demo:
            authorization-uri: https://idp.example.test/oauth2/authorize
            token-uri: https://idp.example.test/oauth2/token
            user-info-uri: https://idp.example.test/oauth2/userinfo
            user-name-attribute: sub

demo:
  machine-resource-uri: https://api.example.test/internal/inventory
~~~

- Hai registrations `browser` và `machine` dùng **client ID/secret khác nhau**. Tách client registrations giúp cấp quyền tối thiểu, audit và rotation độc lập.
- `browser` cần authorize endpoint và redirect URI; `machine` chỉ cần token endpoint nhưng có thể cùng tham chiếu `provider.demo`. Trong hệ thống thật, nên đăng ký provider đúng khả năng của từng client.
- `scope: profile` dùng minh họa OAuth2 login qua UserInfo endpoint. Nếu cần **OIDC**, cấu hình provider hỗ trợ OIDC với `openid`, issuer/JWK metadata và ID token validation; không chỉ thêm scope vào IdP giả.
- `inventory.read` là tên application scope minh họa; IdP thực phải cho client đó quyền tương ứng, Resource Server phải kiểm tra đúng audience/scope.
- `idp.example.test` và `api.example.test` là địa chỉ **không có IdP/resource thật**. Chương trình có thể khởi động và tạo redirect; token exchange/call đến đó không hoàn tất. Không hiểu đây là code production đã kết nối.
- Production đưa credentials vào environment variables/secret manager, **không commit** giá trị production vào YAML, log hoặc frontend.

### 7.3. `src/main/java/demo/grants/GrantTypesApplication.java`

~~~java
package demo.grants;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GrantTypesApplication {
    public static void main(String[] args) {
        SpringApplication.run(GrantTypesApplication.class, args);
    }
}
~~~

### 7.4. `src/main/java/demo/grants/SecurityConfig.java`

~~~java
package demo.grants;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
                .pathMatchers("/", "/public/**").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

- `oauth2Login` bật Authorization Code login cho registration `browser`. Registration `machine` không trở thành browser login vì grant là `client_credentials`.
- `GET /oauth2/authorization/browser` do Spring Security xử lý; không cần controller tự nhận authorization code.
- Các route khác ngoài `/`, `/public/**` yêu cầu user authentication.
- Chưa thêm `oauth2Client` vào chain vì phần machine bên dưới chủ động dùng manager ngoài HTTP; nếu cần **user-delegated outbound API** với `@RegisteredOAuth2AuthorizedClient`, cần cấu hình OAuth2 Client/authorized-client repository cho đúng chain theo ứng dụng.
- Không tắt CSRF toàn cục; browser session vẫn cần CSRF cho các HTTP methods không an toàn.

### 7.5. `src/main/java/demo/grants/MachineOAuth2Config.java`

~~~java
package demo.grants;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
public class MachineOAuth2Config {

    @Bean
    ReactiveOAuth2AuthorizedClientService authorizedClientService(
            ReactiveClientRegistrationRepository registrations) {
        return new InMemoryReactiveOAuth2AuthorizedClientService(
            registrations);
    }

    @Bean("machineManager")
    ReactiveOAuth2AuthorizedClientManager machineManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClientService) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClientService);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

**Lý do dùng loại manager này:**

1. `ReactiveClientRegistrationRepository` có cả `browser` và `machine`.
2. `ReactiveOAuth2AuthorizedClientService` giữ `OAuth2AuthorizedClient` đã cấp. `InMemoryReactiveOAuth2AuthorizedClientService` thích hợp demo/instance đơn; production nhiều replicas nên đánh giá persistence/consistency/token caching.
3. `machineManager` cài provider **chỉ `clientCredentials()`**, tránh nhầm path browser Authorization Code với path service.
4. `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` không cần `ServerWebExchange`; hợp với scheduler/queue consumer và các service không có user hiện diện.
5. Khi access token gần hết hạn, manager/provider sẽ thực hiện policy xin mới phù hợp. Không tự giả định Client Credentials có refresh token.

### 7.6. `src/main/java/demo/grants/MachineResourceClient.java`

~~~java
package demo.grants;

import java.net.URI;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class MachineResourceClient {
    private final ReactiveOAuth2AuthorizedClientManager manager;
    private final WebClient webClient;
    private final URI resourceUri;

    @Autowired
    public MachineResourceClient(
            @Qualifier("machineManager")
            ReactiveOAuth2AuthorizedClientManager manager,
            WebClient.Builder builder,
            @Value("${demo.machine-resource-uri}") String uri) {
        this(manager, builder.build(), URI.create(uri));
    }

    // Constructor package-private để kiểm thử không cần IdP.
    MachineResourceClient(
            ReactiveOAuth2AuthorizedClientManager manager,
            WebClient webClient,
            URI resourceUri) {
        this.manager = manager;
        this.webClient = webClient;
        this.resourceUri = resourceUri;
    }

    public Mono<String> fetchInventory() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("machine")
                .principal("workload-inventory")
                .build();

        return manager.authorize(request)
            .switchIfEmpty(Mono.error(new IllegalStateException(
                "Machine client was not authorized")))
            .flatMap(client -> webClient.get()
                .uri(resourceUri)
                .headers(headers -> headers.setBearerAuth(
                    client.getAccessToken().getTokenValue()))
                .retrieve()
                .bodyToMono(String.class));
    }
}
~~~

**Bản chất của đoạn mã:**

- Manager chỉ định `registrationId=machine` và principal cố định `workload-inventory`; đây là **khóa cache/persistence**, không phải user đăng nhập.
- `manager.authorize(request)` trả reactive publisher, không block event loop. Nếu client chưa có token hợp lệ, nó có thể liên hệ token endpoint.
- Chỉ khi có `OAuth2AuthorizedClient` mới thêm `Authorization: Bearer ...` vào outbound request.
- Không trả access token về browser, không log token, và không sử dụng machine credential để vượt object-level authorization của user.
- `switchIfEmpty` biến tình huống manager không hỗ trợ grant/registration thành lỗi rõ thay vì gửi request thiếu token.
- `@Autowired` xác định constructor cho Spring; constructor nhận `WebClient` trực tiếp để unit test với fake HTTP exchange.
- URI downstream được cấu hình server-side. **Không để người dùng chọn URI tùy ý**, kẻo machine token bị gửi sang host độc hại (SSRF/token exfiltration).

### 7.7. `src/main/java/demo/grants/DemoController.java`

~~~java
package demo.grants;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {
    private final MachineResourceClient machine;

    public DemoController(MachineResourceClient machine) {
        this.machine = machine;
    }

    @GetMapping("/")
    public Mono<String> index() {
        return Mono.just(
            "Start login at /oauth2/authorization/browser");
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/private/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName());
    }

    @GetMapping("/demo/machine-inventory")
    public Mono<String> machineInventory() {
        return machine.fetchInventory();
    }
}
~~~

Đường `/demo/machine-inventory` yêu cầu browser user authenticated vì cấu hình `anyExchange().authenticated()`. **Đây chỉ là endpoint thử nghiệm** để thấy service dùng Client Credentials khi thực hiện downstream call. Trong production, không để mọi người dùng đã login gọi một API machine quyền cao theo ý họ; hãy kiểm tra role/policy riêng hoặc chỉ khởi chạy machine call từ workflow/background job được phép. Quyền người dùng và quyền service là **hai phép kiểm tra riêng**.

### 7.8. Chạy thử

~~~bash
# Linux/macOS
./gradlew bootRun

# Windows
gradlew.bat bootRun

# Endpoint public chạy mà không cần IdP:
curl -i http://localhost:8080/public/ping

# Chỉ xem redirect, không dùng -L để truy cập IdP demo:
curl -i http://localhost:8080/oauth2/authorization/browser
~~~

Kết quả dự kiến `/public/ping` trả `200 OK`, body `pong`. Request bắt đầu Authorization Code thường trả `302` với `Location` có `https://idp.example.test/oauth2/authorize`, `client_id`, `state`, `redirect_uri` và `response_type=code`. Giá trị `state` ngẫu nhiên; thứ tự parameters/encoding có thể khác.

**Không thể hoàn tất login hoặc machine token request với domain demo**. Để thử end-to-end, cấu hình IdP thật hoặc test identity server có authorization/token/userinfo endpoints; bật HTTPS và đăng ký redirect URI chính xác tại IdP.

## 8. `WebClient` và OAuth2 authorized-client filter

Ví dụ chính đặt Bearer header tường minh để thấy cơ chế. Spring Security Reactive còn hỗ trợ `ServerOAuth2AuthorizedClientExchangeFilterFunction` để gắn `OAuth2AuthorizedClient` vào outbound `WebClient`.

~~~java
// Đoạn tích hợp trong @Configuration, không thay đồng thời
// với WebClient chính nếu chưa làm rõ nơi chọn token.
@Bean
WebClient oauthWebClient(
        @Qualifier("machineManager")
        ReactiveOAuth2AuthorizedClientManager manager) {

    var oauthFilter =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return WebClient.builder().filter(oauthFilter).build();
}
~~~

Import `WebClient`, `ReactiveOAuth2AuthorizedClientManager`, `Qualifier`, `Bean` và `org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction`.

Ở mỗi outbound request, có thể dùng:

~~~java
// Trích đoạn trong service sở hữu WebClient đã cấu hình:
return oauthWebClient.get()
    .uri("https://api.example.test/internal/inventory")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .clientRegistrationId("machine"))
    .retrieve()
    .bodyToMono(String.class);
~~~

**Lưu ý:** nếu gọi từ background process, phải bảo đảm manager có principal/workload identity ổn định; trong một số cấu hình, filter cần authentication attribute cụ thể. Vì vậy ví dụ `MachineResourceClient` dùng `OAuth2AuthorizeRequest.principal("workload-inventory")` tường minh, không dựa vào current HTTP user.

**Không** bật `setDefaultOAuth2AuthorizedClient(true)` hoặc `setDefaultClientRegistrationId("machine")` trên một WebClient dùng chung gọi nhiều URL tùy ý. Nếu cấu hình default sai, client có thể **vô tình gửi access token tới host không thuộc audience**. Hãy dùng client chuyên biệt hoặc attributes chọn registration rõ ràng, kết hợp allowlist downstream hosts.

## 9. Gọi resource API thay mặt người dùng

Khi người dùng đã đăng nhập qua Authorization Code/OIDC, backend có thể cần gọi resource API bằng **access token của người dùng**. Đây là tình huống khác với machine token.

Spring Security WebFlux có `@RegisteredOAuth2AuthorizedClient` và `ServerOAuth2AuthorizedClientExchangeFilterFunction` để lấy/áp authorized client phù hợp. Ví dụ **trích đoạn trong controller/service có WebClient đã cấu hình**:

~~~java
@GetMapping("/user/profile-from-api")
public Mono<String> profile(
        @RegisteredOAuth2AuthorizedClient("browser")
        OAuth2AuthorizedClient client) {
    return userWebClient.get()
        .uri("https://api.example.test/user/profile")
        .headers(h -> h.setBearerAuth(
            client.getAccessToken().getTokenValue()))
        .retrieve()
        .bodyToMono(String.class);
}
~~~

Đoạn trên **không chạy độc lập**: `userWebClient` phải được inject, OAuth2 client argument resolver/repository phải được cấu hình trong security chain theo yêu cầu của app (có thể dùng `oauth2Client()`), và token phải có **đúng audience/scope** mà API chấp nhận. Import `OAuth2AuthorizedClient`, `RegisteredOAuth2AuthorizedClient`, `GetMapping`, `Mono`.

Không lấy **ID token** để gọi API nếu resource server cần **access token**, và không tự dùng `machine` token để đọc dữ liệu riêng của Alice/Bob nếu downstream dự kiến user-delegated authorization. Nếu yêu cầu gọi API thay mặt user nhưng token ban đầu không thể dùng cho target audience, cần cơ chế token exchange/on-behalf-of được Authorization Server hỗ trợ, không tự biến Client Credentials thành delegation.

## 10. Quy tắc cho SPA, mobile, BFF và service

### Server-side web app

Backend giữ client secret và tokens; browser giữ cookie session. Dùng Authorization Code và OIDC khi cần login. Cấu hình `state`, PKCE nếu IdP hỗ trợ, redirect URI allowlist, CSRF và session/cookie flags. Không trả secrets/tokens xuống frontend nếu không cần.

### BFF cho frontend SPA

BFF là confidential OAuth2 client, xử lý Authorization Code phía backend và giữ authorized clients/tokens tại server. Browser gọi BFF bằng session cookie và CSRF token cho request thay đổi trạng thái. Đây là kiến trúc hạn chế nơi access tokens xuất hiện so với SPA hoàn toàn tự quản lý tokens.

### SPA public client

SPA không thể giấu `client-secret` trong JavaScript. Dùng Authorization Code + **PKCE** (client authentication `none` nếu IdP coi là public client). Vẫn phải đánh giá XSS, token storage, redirect URI, state, Refresh Token Rotation, CORS và provider policy. **Không** dùng Client Credentials từ browser.

### Native mobile/desktop

Dùng Authorization Code + PKCE qua system browser, redirect URI hợp lệ theo nền tảng, lưu tokens bằng khả năng bảo vệ của hệ điều hành. App binary có thể bị reverse engineer; client secret hardcode không phải bí mật đáng tin.

### Backend service và scheduler

Dùng Client Credentials, workload identity, scopes tối thiểu, manager ngoài `ServerWebExchange`. Không tạo một user giả có password để mô phỏng máy–máy. Khi token endpoint báo lỗi, fail closed thay vì dùng access token không hợp lệ hay cấp quyền tạm.

## 11. Kiểm thử cấu hình client registrations

Test sau xác nhận hai grants được cấu hình đúng mà không gọi IdP.

Tệp `src/test/java/demo/grants/RegistrationContractTest.java`:

~~~java
package demo.grants;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.client.registration
    .ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class RegistrationContractTest {

    @Autowired
    ReactiveClientRegistrationRepository registrations;

    @Test
    void browserUsesAuthorizationCode() {
        StepVerifier.create(
                registrations.findByRegistrationId("browser"))
            .assertNext(reg -> {
                assertEquals(AuthorizationGrantType.AUTHORIZATION_CODE,
                    reg.getAuthorizationGrantType());
                assertTrue(reg.getRedirectUri().contains(
                    "/login/oauth2/code/"));
            })
            .verifyComplete();
    }

    @Test
    void machineUsesClientCredentials() {
        StepVerifier.create(
                registrations.findByRegistrationId("machine"))
            .assertNext(reg -> {
                assertEquals(AuthorizationGrantType.CLIENT_CREDENTIALS,
                    reg.getAuthorizationGrantType());
                assertTrue(reg.getScopes().contains("inventory.read"));
            })
            .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests 'demo.grants.RegistrationContractTest'
~~~

Test chứng minh **registration properties** đã map đúng sang `ClientRegistration`, không chứng minh secret hợp lệ ở IdP.

## 12. Kiểm thử Authorization Code redirect bằng `WebTestClient`

Tệp `src/test/java/demo/grants/AuthorizationCodeRedirectTest.java`:

~~~java
package demo.grants;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class AuthorizationCodeRedirectTest {

    @Autowired
    WebTestClient client;

    @Test
    void startsBrowserGrantWithState() {
        client.get().uri("/oauth2/authorization/browser")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value("Location", location -> {
                assertTrue(location.startsWith(
                    "https://idp.example.test/oauth2/authorize"));
                assertTrue(location.contains("response_type=code"));
                assertTrue(location.contains("client_id="));
                assertTrue(location.contains("state="));
                assertTrue(location.contains("redirect_uri="));
            });
    }

    @Test
    void publicEndpointDoesNotNeedLogin() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }
}
~~~

Test này chỉ kiểm tra **initiation** và client registration. Nó **không xác minh callback, state/PKCE validation, code exchange hoặc OIDC ID token**; các phần đó cần test với IdP giả lập đầy đủ hoặc IdP test tenant. Đừng gọi `/oauth2/authorization/machine` rồi mong có redirect: machine grant không phải luồng browser.

## 13. Unit test Machine Client không cần IdP

Ta có thể tạo fake manager trả `OAuth2AuthorizedClient` có token thử nghiệm và fake WebClient exchange để chứng minh token được gửi **đúng downstream**, mà không gọi token endpoint thật.

Tệp `src/test/java/demo/grants/MachineResourceClientTest.java`:

~~~java
package demo.grants;

import java.net.URI;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MachineResourceClientTest {

    private ClientRegistration registration() {
        return ClientRegistration.withRegistrationId("machine")
            .clientId("unit-client")
            .clientSecret("unit-secret")
            .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
            .tokenUri("https://idp.example.test/oauth2/token")
            .build();
    }

    @Test
    void sendsBearerTokenToConfiguredResourceOnly() {
        var accessToken = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "unit-token",
            Instant.now(),
            Instant.now().plusSeconds(300));

        var authorized = new OAuth2AuthorizedClient(
            registration(), "workload-inventory", accessToken);

        ReactiveOAuth2AuthorizedClientManager manager = request -> {
            assertEquals("machine", request.getClientRegistrationId());
            assertEquals("workload-inventory",
                request.getPrincipal().getName());
            return Mono.just(authorized);
        };

        ExchangeFunction fakeResource = request -> {
            assertEquals(
                "https://api.example.test/internal/inventory",
                request.url().toString());
            assertEquals("Bearer unit-token",
                request.headers().getFirst(HttpHeaders.AUTHORIZATION));
            return Mono.just(
                ClientResponse.create(HttpStatus.OK)
                    .body("inventory-response")
                    .build());
        };

        WebClient webClient =
            WebClient.builder().exchangeFunction(fakeResource).build();

        var service = new MachineResourceClient(
            manager,
            webClient,
            URI.create("https://api.example.test/internal/inventory"));

        StepVerifier.create(service.fetchInventory())
            .expectNext("inventory-response")
            .verifyComplete();
    }

    @Test
    void refusesToCallResourceWithoutAuthorizedClient() {
        ReactiveOAuth2AuthorizedClientManager manager =
            request -> Mono.empty();

        ExchangeFunction forbiddenCall = request ->
            Mono.error(new AssertionError(
                "Resource should not be called without a token"));

        var service = new MachineResourceClient(
            manager,
            WebClient.builder().exchangeFunction(forbiddenCall).build(),
            URI.create("https://api.example.test/internal/inventory"));

        StepVerifier.create(service.fetchInventory())
            .expectError(IllegalStateException.class)
            .verify();
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests 'demo.grants.MachineResourceClientTest'
~~~

Test này kiểm tra **phần consume token** và không gọi resource khi manager không cấp token. Nó **không** chứng minh `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` đã thực sự POST token endpoint. Để kiểm tra grant end-to-end, tạo mock AS nhận `grant_type=client_credentials`, kiểm tra client authentication/scopes, trả synthetic token; sau đó mock Resource Server xác nhận bearer token và trả 401/403 khi token không hợp lệ.

## 14. Token lifecycle: refresh, hết hạn và caching

**Authorization Code:** AS có thể cấp access token và refresh token. Manager có provider `refreshToken()` có thể dùng refresh token nếu nó tồn tại và access token cần renew. Nếu refresh token đã bị thu hồi hoặc IdP không cấp refresh token, có thể phải bắt đầu authorization flow mới.

Ví dụ **trích đoạn provider composite** trong manager web:

~~~java
ReactiveOAuth2AuthorizedClientProvider provider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();
~~~

**Client Credentials:** thông thường chỉ nhận access token; khi hết hạn, manager xin token mới bằng client authentication, không “refresh” bằng user refresh token. Có thể tồn tại nhiều cache keys theo registration và principal. Với demo `InMemoryReactiveOAuth2AuthorizedClientService`, mỗi JVM giữ token riêng; nhiều replicas có thể xin token độc lập.

**Lưu ý concurrency và availability:**

- Nhiều requests cùng thấy token expired có thể gây token storm. Kiểm thử rate limit/concurrency, backoff và cơ chế cache phù hợp.
- Không gọi token endpoint trong mỗi HTTP request nếu token còn hiệu lực; tận dụng authorized-client manager.
- Tách `invalid_client` (secret/method) khỏi `invalid_scope` (policy) và lỗi mạng/503.
- Không retry POST có side effect ở downstream chỉ vì token bị renew, trừ khi nghiệp vụ đã có idempotency.
- Không log raw Bearer token, response token JSON, client secret, PKCE verifier hoặc authorization code.
- Đặt timeout hợp lý và metric lỗi OAuth2/Resource Server nhưng giữ bí mật request.

## 15. Phân quyền khác nhau cho user và service token

Ví dụ API có hai endpoint:

~~~text
GET /customers/me
GET /internal/inventory
~~~

`/customers/me` thường yêu cầu user-delegated access token và kiểm tra user subject/ownership. `/internal/inventory` có thể dành cho service client có `SCOPE_inventory.read` hoặc permission tương ứng. **Client Credentials token không thể coi như token của user** để đọc dữ liệu riêng của Alice/Bob, trừ khi Resource Server có một chính sách rõ ràng cho phép ứng dụng thao tác đó thay người dùng với kiểm tra authorization bổ sung.

Các nguy cơ thường gặp:

- **Confused deputy:** user request bất kỳ được backend chuyển thành machine token quyền cao mà không kiểm tra user có quyền đối với đối tượng hay không.
- **Token exfiltration:** một WebClient default token gửi Bearer token tới URL do attacker kiểm soát.
- **Wrong audience:** token hợp lệ cho service A được dùng gọi service B và Resource Server kiểm tra `aud` lỏng lẻo.
- **Client secret reuse:** browser app, batch job và nhiều services dùng chung credential quyền cao, khó rotation và truy vết.
- **ID token làm access token:** Resource Server vô tình chấp nhận ID token cấp cho client thay vì access token dành cho API.

Thiết kế tốt: tách registrations; audience/scopes tối thiểu; authorization riêng ở Resource Server; log theo client ID/workload ID không kèm token; bảo vệ user ownership và tenant boundary; dùng token exchange/on-behalf-of chuẩn khi thực sự cần delegation, không tự giả lập bằng machine token.

## 16. Sự cố thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân gợi ý | Kiểm tra |
| --- | --- | --- |
| `/oauth2/authorization/browser` không redirect | Thiếu `oauth2Login`/registration sai/chain không match | Security config và `browser` registration |
| Redirect URI mismatch | Host/scheme/path không khớp IdP allowlist | `{baseUrl}`, proxy, HTTPS |
| Callback báo invalid state | Mất WebSession/cookie, state không khớp | SameSite, session store, repository |
| Authorization Code `invalid_grant` | Code expired/đã dùng, PKCE verifier sai | Code exchange, verifier, redirect URI |
| OIDC ID token lỗi | Issuer/audience/nonce/JWK mismatch | Provider metadata và validation |
| Client Credentials `invalid_client` | Client ID/secret/method sai hoặc secret đã rotate | Credential store, `client_secret_basic` |
| Client Credentials `unsupported_grant_type` | AS/client không được phép dùng grant | IdP client settings |
| Machine `invalid_scope` | `inventory.read` không được cấp cho client | AS app permissions |
| Background job thiếu `ServerWebExchange` | Dùng web-bound manager ngoài HTTP | Dùng service-based manager |
| Request đến machine API bị redirect browser | Chọn nhầm registration `browser` hoặc manager | Log an toàn registrationId/grant |
| Outbound thiếu Bearer token | Manager empty, WebClient filter chưa gắn, sai registration | `OAuth2AuthorizeRequest` và manager result |
| Resource Server trả 401 | Token missing/expired/invalid/wrong audience | Verify token, `iss`, `aud`, expiry |
| Resource Server trả 403 | Token hợp lệ nhưng thiếu scopes/permissions | Resource authorization policy |
| Job xin token liên tục | Token store chỉ in-memory hoặc caching sai | Cache key, expiry, concurrency |
| Browser không thấy access token trong JS | BFF/server-side app giữ token trên backend | Có thể là thiết kế đúng |
| App khởi động được, login thất bại tại domain .test | Domain demo không có IdP thật | Dùng IdP test tenant/endpoint hợp lệ |

**Quy trình debug:** xác nhận loại ứng dụng → grant/registration → endpoint (authorize hay token) → client authentication → manager phù hợp với HTTP/background → token/claims → Resource Server policy → lifecycle/cookie/proxy/rotation. Không “chữa” bằng cách tắt state, bỏ PKCE, mở mọi scopes hoặc chuyển sai grant sang Client Credentials.

## 17. Checklist trước production

| Hạng mục | Cần đạt |
| --- | --- |
| Chọn đúng actor | User vs workload được phân biệt |
| Grant | User: Authorization Code; machine: Client Credentials |
| SPA/mobile | Public client + PKCE, không đưa secret xuống client |
| BFF | Tokens ở server, session/CSRF phù hợp |
| OIDC | Có `openid` và kiểm chứng ID token nếu cần danh tính |
| Client registration | Grant, scopes, client ID, authentication method đúng IdP |
| Redirect URI | HTTPS public, allowlisted, reverse proxy headers được tin cậy |
| `state` và PKCE | Correlation/PKCE verifier/nonce không bị mất |
| Manager | Service-based manager cho background, tránh phụ thuộc exchange |
| Token storage | Isolated theo registration + principal/tenant, TTL/expiry |
| Resource Server | Kiểm tra chữ ký/introspection, `iss`, `aud`, scopes, ownership |
| Secrets | Secret manager, rotation, audit, không gửi tới JS/log |
| WebClient | Token chỉ tới đúng host và đúng registration |
| Tránh privilege escalation | Machine token không thay user token |
| Testing | Contract, redirect, bearer propagation, token endpoint integration |
| Negative cases | Bad secret, invalid scope, state mismatch, token expired, 401/403 |
| Deployment | Token caching/concurrency, IdP outage, tracing an toàn |

## 18. Câu hỏi tự kiểm tra

**1. Vì sao SPA không nên dùng Client Credentials?** Vì browser không giữ được confidential client secret. Dùng Authorization Code + PKCE hoặc chuyển việc quản lý token cho BFF.

**2. Authorization Code có callback không?** Có, sau user authorization. Client phải khôi phục request gốc, xác minh `state` và đổi code ở token endpoint.

**3. Client Credentials có cần `/authorize` hoặc `state` không?** Không, grant này lấy token trực tiếp từ token endpoint cho application identity.

**4. Vì sao job nên dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`?** Vì nó làm việc ngoài `ServerWebExchange`/user request và lưu authorized clients ở mức service.

**5. `principal("workload-inventory")` có phải người dùng của API không?** Không. Đây là khóa nội bộ liên kết authorized-client cache; token mang identity/permission do Authorization Server cấp cho client.

**6. Token Client Credentials có dùng để đọc tài liệu cá nhân theo quyền Alice được không?** Không tự động; đó là app token, không phải delegated user token. Nếu cần, phải có authorization/ủy quyền thích hợp tại downstream.

**7. Một response OAuth2 có `access_token` và `id_token`, dùng cái nào gọi Resource Server?** Thông thường dùng access token đúng audience; ID token phục vụ OIDC login/client identity validation.

**8. Lỗi `invalid_client` thường liên quan điều gì?** Client ID, secret/key, authentication method, rotation, chính sách AS.

**9. Vì sao `WebClient` không nên mặc định gắn token cho mọi URL?** Dễ rò token đến host ngoài audience hoặc URL bị attacker điều khiển.

**10. Có thể test grant mà không có IdP thật không?** Có thể test registrations, redirect và việc gắn Bearer token bằng fake manager/HTTP; token exchange thực sự cần mock AS/IdP test tenant.

## Ghi nhớ

- **Authorization Code** có user, browser redirect, callback, state, token exchange và PKCE; OIDC bổ sung ID token/nonce.
- **Client Credentials** có application identity, token endpoint, không có user/callback.
- WebFlux server-side user login dùng **`oauth2Login()`**; background service dùng **`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`** với `clientCredentials()`.
- **`OAuth2AuthorizedClient`/authorized-client service lưu token**, khác authorization-request repository lưu state tạm và security-context repository lưu Authentication.
- **Machine token không thay user token**. Resource Server kiểm tra chủ thể, scopes, audience và ownership.
- **Không hardcode client secrets ở SPA/native**. Giữ token/secret trong vùng tin cậy, dùng TLS và rotation.
- Test cả luồng redirect và outbound machine token; đừng coi HTTP 302 của login là bằng chứng token exchange thành công.

### Tài liệu chính thức

- [Spring Security 6.5 — Reactive OAuth2 Client: Authorization Grant Support](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html)
- [Spring Security 6.5 — Reactive OAuth2 Client: Core Interfaces](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html)
- [Spring Security 6.5 — Reactive OAuth2 Client: Authorized Client Features](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html)
- [Spring Security 6.5 — Reactive OAuth2 Login: Core Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/core.html)
- [Spring Security 6.5 — Reactive OAuth2 Client Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/client-authentication.html)
- [RFC 6749 — OAuth 2.0 Authorization Code / Client Credentials](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
