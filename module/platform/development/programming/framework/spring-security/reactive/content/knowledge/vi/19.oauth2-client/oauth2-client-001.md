# OAuth2AuthorizedClient và vòng đời access token, refresh token

> **Phạm vi:** OAuth2 Client trên **Spring Security reactive / Spring WebFlux**, không nhầm với OAuth2 Resource Server. Bài học dùng Java 17+, Spring Boot 3.x và API Spring Security 6.5.x để giải thích `OAuth2AuthorizedClient`, cấp mới/làm mới token, lưu trữ, thời điểm hết hạn, refresh-token rotation, xử lý `invalid_grant`, tích hợp `WebClient` và kiểm thử mà không cần IdP thật.

## 1. Mục tiêu

Sau khi học, bạn có thể:

1. Phân biệt `ClientRegistration`, `OAuth2AuthorizedClient`, `Authentication`, `OAuth2AccessToken` và `OAuth2RefreshToken`.
2. Mô tả vòng đời access token từ lúc cấp, sử dụng, gần hết hạn, refresh/re-authorize cho đến khi token bị thu hồi.
3. Giải thích **refresh token có thể không tồn tại** và không phải mọi grant đều dùng refresh token.
4. Cấu hình `ReactiveOAuth2AuthorizedClientManager` với `authorizationCode()`, `refreshToken()` hoặc `clientCredentials()` tùy flow.
5. Chọn giữa `DefaultReactiveOAuth2AuthorizedClientManager` trong HTTP request và `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` cho scheduled jobs.
6. Phân biệt `ServerOAuth2AuthorizedClientRepository` với `ReactiveOAuth2AuthorizedClientService` và lưu token đúng principal/registration.
7. Sử dụng `ServerOAuth2AuthorizedClientExchangeFilterFunction` với `WebClient` để gắn Bearer **access token**, không vô tình gửi token tới host khác.
8. Biết xử lý `invalid_grant` từ Token Endpoint và lỗi 401/403 từ Resource Server, kể cả failure handler của WebClient.
9. Hiểu refresh token rotation, concurrent refresh, multi-pod persistence, logout, revocation và rò rỉ thông tin.
10. Viết test `StepVerifier` chứng minh token còn hạn được dùng lại, token hết hạn được làm mới và lưu, thiếu refresh không thể refresh, `invalid_grant` loại state cũ.

## 2. Ứng dụng đóng vai trò OAuth2 Client là gì?

Một ứng dụng WebFlux đóng vai trò **OAuth2 Client** khi muốn gọi một **Resource Server** bằng access token được **Authorization Server/Identity Provider (IdP)** cấp.

Ví dụ điển hình: user `alice` đăng nhập vào web app, chấp thuận scope `reports.read`, và app gọi một reports API bằng Bearer access token gắn với tài khoản alice.

```text
Browser alice
   |
   | GET /reports/current
   v
Spring WebFlux + Spring Security OAuth2 Client
   |
   | Nếu chưa có quyền: authorization-code redirect
   v
Authorization Server / IdP
   |
   | Token Endpoint sau login/consent:
   |   access token
   |   refresh token (tùy provider/policy)
   v
WebFlux lưu OAuth2AuthorizedClient
   |
   | Khi gọi reports API:
   |   load, kiểm expiry, có thể refresh
   v
WebClient: Authorization: Bearer <ACCESS_TOKEN>
   |
   v
Resource Server: kiểm issuer/audience/scope/quyền tài nguyên
   |
   v
Response báo cáo
```

**Refresh token tuyệt đối không phải Bearer token gửi tới reports API.** Nó chỉ dùng với **Token Endpoint của IdP** để xin access token mới. Và token không nên xuất hiện trong browser URL, frontend JSON, log hoặc metrics.

### 2.1 OAuth2 Client khác Resource Server

| Vai trò | Làm gì? | Cấu hình Spring Security |
| --- | --- | --- |
| OAuth2 Client | Lấy/lưu token và đính kèm Bearer vào outbound request | `oauth2Client()`, reactive authorized-client manager |
| OAuth2 Login | Tương tác browser, redirect code, thiết lập user login | `oauth2Login()` |
| Resource Server | Kiểm chứng **inbound** Bearer token và authorities | `oauth2ResourceServer(...)` |
| Authorization Server | Cấp code/access/refresh tokens, cung cấp authorize/token endpoints | Một IdP/Authorization Server riêng |

Cùng một WebFlux app có thể vừa là Resource Server cho inbound request vừa là OAuth2 Client khi gọi downstream. Tuy nhiên **có OAuth2 client registration không có nghĩa inbound token được kiểm chữ ký**; hai trách nhiệm phải cấu hình riêng.

### 2.2 ID token không phải access token

Với OpenID Connect, IdP có thể trả **ID token** đại diện cho sự kiện đăng nhập/claims danh tính. ID token có audience là client/Relying Party, còn **access token** dùng để gọi Resource Server. Không gửi ID token thay Bearer access token chỉ vì cả hai trông giống JWT. Refresh token lại là credential cấp quyền nhận access token mới, không phải bằng chứng danh tính gửi tới Resource Server.

## 3. OAuth2AuthorizedClient chứa gì?

Theo Spring Security, `OAuth2AuthorizedClient` gắn:

- Một **`ClientRegistration`**: registration ID, client ID, grant type, auth/token URIs, scope, client authentication method.
- **Principal name**: chủ thể được cấp quyền hoặc service principal.
- Một **`OAuth2AccessToken`**: token type, giá trị bí mật, issuedAt/expiresAt, scopes.
- Có thể có **`OAuth2RefreshToken`**: giá trị bí mật, issuedAt và metadata thời gian nếu được cung cấp.

Một representation **chỉ để giải thích**, không phải JSON mà Spring Security tự trả:

```text
ClientRegistration:
  registrationId: reports
  clientId: server-side-report-client
  grantType: authorization_code
  tokenUri: https://idp.example.test/oauth2/token

OAuth2AuthorizedClient:
  registration: reports
  principalName: alice
  accessToken:
    type: Bearer
    value: <SECRET>
    issuedAt:  2026-01-01T10:00:00Z
    expiresAt: 2026-01-01T11:00:00Z
    scopes: [reports.read]
  refreshToken:
    value: <SECRET_IF_ISSUED>
    issuedAt: 2026-01-01T10:00:00Z
```

Token values là **credentials** chứ không phải thông tin để debug bằng cách log. `authorizedClient.getRefreshToken()` có thể là `null`: không được gọi `getTokenValue()` mà không kiểm tra null.

### 3.1 ClientRegistration không có nghĩa đã được cấp quyền

Một `ClientRegistration` tồn tại ngay từ lúc ứng dụng khởi chạy, ngay cả khi chưa user nào đăng nhập hoặc chưa có token nào.

`OAuth2AuthorizedClient` chỉ hình thành khi có authorized client state — ví dụ sau authorization-code exchange thành công, hoặc sau client-credentials token request. Do đó:

```text
client registration != authorized client != authenticated user session
```

Một user có thể đăng nhập app nhưng chưa cấp quyền cho báo cáo; có thể có nhiều authorized clients cho nhiều registrations; có thể logout app nhưng token ở IdP vẫn còn hiệu lực. Ngược lại scheduled job có authorized client mà không có browser session.

### 3.2 Access token và refresh token khác nhau

| Tiêu chí | Access token | Refresh token |
| --- | --- | --- |
| Đích sử dụng | Protected Resource Server | Authorization Server Token Endpoint |
| Mục đích | Cho phép truy cập API theo scope/audience/quyền | Xin access token mới theo grant/policy |
| Thời hạn | Thường ngắn | Có thể dài hơn, hoặc không được cấp |
| Truyền trong API request | `Authorization: Bearer <access_token>` | **Không** |
| Nơi lưu | Server-side authorized-client repository/service | Server-side, phải bảo vệ nghiêm ngặt |
| Khi hết hạn/revoked | API có thể trả 401 | Refresh request có thể trả `invalid_grant` |
| Khi bị đánh cắp | Có thể gọi API trong giới hạn token | Có thể xin thêm access tokens nếu không bị chặn, rủi ro cao |

Không tự suy ra token là JWT: nhiều IdP phát **opaque access token**, phải để Resource Server dùng JWT validation/introspection phù hợp. Client-side metadata `expiresAt` hỗ trợ scheduling, không thay Resource Server validation.

## 4. Vòng đời token trong authorization_code flow

```text
Chưa có OAuth2AuthorizedClient cho ("reports", "alice")
        |
        | 1. Browser bắt đầu OAuth2 authorization request
        | 2. IdP xác thực user và yêu cầu consent (nếu cần)
        | 3. Authorization code redirect về WebFlux
        | 4. Backend đổi code ở Token Endpoint
        v
Authorized Client { access A1, refresh R1 nếu được cấp }
        |
        | 5. WebClient dùng access A1 gọi Resource Server
        |
        +-- Access A1 còn hạn: reuse
        |
        +-- Access A1 gần/hết hạn:
              |
              +-- Có R1 và provider refreshToken()?
              |     |
              |     +-- Được IdP chấp nhận:
              |     |      access A2
              |     |      refresh R2 nếu rotate
              |     |      save Authorized Client mới
              |     |
              |     +-- invalid_grant:
              |            stale Authorized Client bị loại
              |            cần authorization-code/consent lại
              |
              +-- Không có refresh token:
                    cần re-authorization phù hợp
```

**Không bảo đảm sẽ tự refresh chỉ vì bạn khai báo OAuth2 Client.** Manager phải được dùng trong request, refresh-token provider phải được cấu hình, authorized client phải có refresh token hợp lệ, access token cần refresh và IdP phải chấp nhận.

### 4.1 Hết hạn và khoảng clock skew

`OAuth2AccessToken` thường có `Instant getIssuedAt()` và `getExpiresAt()`. Đợi chính xác sát `expiresAt` rồi mới gửi token có thể gây 401 vì network latency và đồng hồ giữa app/IdP/API không hoàn toàn giống nhau.

`RefreshTokenReactiveOAuth2AuthorizedClientProvider` có thể cấu hình clock skew qua `setClockSkew(...)` hoặc builder. Ví dụ nếu chọn **60 giây**:

```text
10:00:00 token được cấp, expiresAt = 11:00:00
10:58:30 token còn xa threshold -> có thể reuse
10:59:10 token trong khoảng 60s tới expiry -> refresh provider có thể hoạt động
11:00:00 token hết hạn theo expiresAt
```

Đây là ví dụ **với skew đã chọn**, không phải bằng chứng mọi hệ thống dùng ngưỡng mặc định giống nhau. Test expiry nên dùng `Instant` và khoảng thời gian đủ rộng, tránh test nhạy với mili-giây hoặc múi giờ máy.

### 4.2 Vì sao refresh token có thể không được cấp?

Cơ chế tùy provider và policy: scopes, offline access, consent, client type, grant type, rotation/expiry, bảo mật của OAuth2 app.

- Authorization code **có thể** nhận refresh token, không chắc chắn.
- Client credentials **thường không** nhận refresh token; cần grant mới khi access hết hạn.
- Public clients cần PKCE và chính sách refresh-token rotation/replay protection phù hợp.
- Nếu không có refresh token, không được tự “kéo dài” `expiresAt` hoặc gửi access token hết hạn như thể hợp lệ.

### 4.3 Refresh-token rotation

IdP có thể cấp `R2` sau khi `R1` được sử dụng thành công. Token `R1` có thể lập tức không còn hợp lệ. Client phải persist **trạng thái mới**, không giữ `R1` trong DB/cache rồi dùng lại ở lần sau.

```json
{
  "access_token": "<REDACTED_NEW_ACCESS>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "reports.read",
  "refresh_token": "<REDACTED_ROTATED_REFRESH>"
}
```

Đây chỉ là ví dụ response shape, không có token thật. Nếu IdP không cấp refresh token mới, xử lý theo token response semantics của provider; không tự xóa cái cũ nếu chính sách cho phép giữ.

## 5. Reactive OAuth2 Client manager và provider

### 5.1 ReactiveOAuth2AuthorizedClientManager

`ReactiveOAuth2AuthorizedClientManager` điều phối bốn công việc:

1. Tìm authorized client theo registration + principal.
2. Quyết định có cần (re-)authorize dựa trên provider/grant/expiry.
3. Lưu authorized client cập nhật qua repository/service và success handler.
4. Xử lý authorization failure, ví dụ loại stale state khi IdP trả `invalid_grant`.

Chính manager dùng `ReactiveOAuth2AuthorizedClientProvider` để thực hiện grant logic. Đừng tự viết controller gọi Token Endpoint và lưu token values bằng cách ghép chuỗi HTTP khi Spring Security đã có integration chuẩn.

### 5.2 Provider composite

Ví dụ builder:

```java
ReactiveOAuth2AuthorizedClientProvider provider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
```

Đây là **snippet cần imports** của Spring Security OAuth2 Client. Các provider có vai trò khác nhau:

- `authorizationCode()`: flow browser redirect/authorization code.
- `refreshToken()`: lấy access token mới bằng refresh token khi điều kiện phù hợp.
- `clientCredentials()`: xin access token cho app/service; không đòi refresh token.
- Một số docs 6.x cũ còn `password()`; Resource Owner Password Credentials grant là legacy/deprecated, không lựa chọn cho ứng dụng mới.

`Mono.empty()` từ provider có thể nghĩa provider **không hỗ trợ grant hoặc không cần re-authorization** cho context ấy. Không hiểu là nó phát access token rỗng. Manager có thể trả authorized client hiện có; caller vẫn cần lưu ý expiry khi không có cách refresh.

### 5.3 Manager cho WebFlux HTTP request

Dùng `DefaultReactiveOAuth2AuthorizedClientManager` với `ReactiveClientRegistrationRepository` và `ServerOAuth2AuthorizedClientRepository` trong **ServerWebExchange**:

```java
var manager = new DefaultReactiveOAuth2AuthorizedClientManager(
    registrations, authorizedClientRepository
);
manager.setAuthorizedClientProvider(
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build()
);
```

Đây là snippet. Manager này gắn với request web, dùng repository theo principal/exchange. Default authorization success handler lưu client; failure handler mặc định có thể loại state với error code như `invalid_grant`. Khi tùy chỉnh các handlers, phải bảo đảm storage chính xác và không bỏ xử lý stale token.

### 5.4 Manager cho background job/service tier

Khi không có `ServerWebExchange` (scheduled task, message consumer, background processor), dùng:

```java
var manager =
    new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
        registrations, authorizedClientService
    );
manager.setAuthorizedClientProvider(
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build()
);
```

Đây là snippet cho service identity, cần service và registration được cấu hình. Không giả tạo một web exchange chỉ để tái sử dụng manager của controller.

### 5.5 Chọn manager nào?

| Ngữ cảnh | Lựa chọn | Kho state |
| --- | --- | --- |
| WebFlux controller gọi API thay mặt user đăng nhập | `DefaultReactiveOAuth2AuthorizedClientManager` | `ServerOAuth2AuthorizedClientRepository` |
| WebClient trong HTTP exchange có principal | Web manager thích hợp | Repository gắn web exchange |
| Cron job xin token `client_credentials` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientService` |
| Message consumer với service principal | Service manager | Shared authorized-client service nếu cần |
| Nhiều replicas, cần state sau restart | Manager + persistence bền vững | DB/shared store bảo vệ credentials |

Nếu đăng ký **nhiều manager cùng interface**, dùng bean name/`@Qualifier` để injection không mơ hồ.

## 6. Lưu OAuth2AuthorizedClient đúng chỗ

### 6.1 ServerOAuth2AuthorizedClientRepository

Repository quản lý authorized clients theo web context, có các operations:

```java
Mono<OAuth2AuthorizedClient> loadAuthorizedClient(
    String registrationId,
    Authentication principal,
    ServerWebExchange exchange
);

Mono<Void> saveAuthorizedClient(
    OAuth2AuthorizedClient client,
    Authentication principal,
    ServerWebExchange exchange
);

Mono<Void> removeAuthorizedClient(
    String registrationId,
    Authentication principal,
    ServerWebExchange exchange
);
```

Đây là **chữ ký minh họa**, không phải file interface Java đầy đủ. Implementation có thể dùng WebSession hoặc ủy thác service theo tình huống; không giả định mọi application đều đang lưu DB khi có interface này.

### 6.2 ReactiveOAuth2AuthorizedClientService

Service làm việc ở application level và có operations:

```java
Mono<OAuth2AuthorizedClient> loadAuthorizedClient(
    String registrationId, String principalName
);

Mono<Void> saveAuthorizedClient(
    OAuth2AuthorizedClient client, Authentication principal
);

Mono<Void> removeAuthorizedClient(
    String registrationId, String principalName
);
```

`InMemoryReactiveOAuth2AuthorizedClientService` hữu ích cho unit test và demo; `R2dbcReactiveOAuth2AuthorizedClientService` hỗ trợ storage bằng R2DBC khi bạn cung cấp schema/database tương ứng.

**Quan trọng:** In-memory store không chia sẻ giữa các pods, mất token sau restart, khó xử lý rotation race. Production cần quyết định persistence, mã hóa dữ liệu, session retention, backup/restore và concurrency strategy.

### 6.3 Storage key phải tách principal

Ví dụ:

```text
("reports", "alice") -> access A / refresh RA
("reports", "bob")   -> access B / refresh RB
("mail",    "alice") -> access C / refresh RC
```

Không lưu một token toàn cục chỉ theo `registrationId` cho user-delegated flow. User A và B có thể có quyền, tenant và consent khác nhau. Với nhiều issuers/tenants, cần định danh ổn định có issuer/tenant boundary đáng tin cậy; đừng lấy principal name trực tiếp từ query param. Với service `client_credentials`, một principal riêng do app kiểm soát như `nightly-job` có thể được dùng để reuse token.

## 7. Cấu hình Spring Boot 3.x + WebFlux đầy đủ

Ví dụ user-delegated OAuth2 authorization code: browser login với provider giả lập theo domain `example.test`; khi có IdP thật và registration tương ứng, `WebClient` gọi resource báo cáo cố định bằng access token gắn với user.

**Để chạy ứng dụng end-to-end**, bắt buộc có IdP/Authorization Server, redirect URI chính xác, scopes và Resource Server thật. Các domain `example.test` không phải dịch vụ live. Tuy nhiên source Java là các class riêng, phù hợp project Boot/WebFlux/Security đã có dependency; test manager offline ở mục 9 **không cần IdP**.

### 7.1 Gradle

`build.gradle` trong Spring Boot project do Spring Initializr tạo, đã có plugins và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chọn đúng WebFlux stack; `HttpSecurity` và Servlet `OAuth2AuthorizedClientManager` **không** thay `ServerHttpSecurity` và `ReactiveOAuth2AuthorizedClientManager`. Khi có cả MVC starter và WebFlux starter, Spring Boot thường ưu tiên MVC mặc định.

### 7.2 File layout

```text
src/main/java/com/example/oauthtokens/
  TokenLifecycleApplication.java
  OAuthClientConfiguration.java
  ReportsController.java
src/main/resources/application.yml
src/test/java/com/example/oauthtokens/
  AuthorizedClientLifecycleTest.java
```

Mỗi `public class` nằm trong một file riêng, đúng package. Project cần JDK 17+ và Gradle/Spring dependencies, không chạy bằng `javac` trần.

### 7.3 application.yml

`src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports:
            provider: training-idp
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - reports.read
        provider:
          training-idp:
            authorization-uri: https://idp.example.test/oauth2/authorize
            token-uri: https://idp.example.test/oauth2/token
            user-info-uri: https://idp.example.test/userinfo
            user-name-attribute: sub
```

`reports` là registration ID mà WebClient dùng. `REPORTS_CLIENT_ID`/`REPORTS_CLIENT_SECRET` phải đến từ environment hoặc secrets manager; **không commit giá trị thật**. `authorization-uri` dùng cho browser redirect; `token-uri` dùng ở backend cho code exchange và refresh. Với OIDC thật có `openid` scope/issuer metadata, provider config sẽ khác. IdP phải đăng ký chính xác redirect URI và callback hợp lệ; đừng chấp nhận redirect tùy ý.

### 7.4 TokenLifecycleApplication.java

`src/main/java/com/example/oauthtokens/TokenLifecycleApplication.java`:

```java
package com.example.oauthtokens;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TokenLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(TokenLifecycleApplication.class, args);
    }
}
```

### 7.5 OAuthClientConfiguration.java

`src/main/java/com/example/oauthtokens/OAuthClientConfiguration.java`:

```java
package com.example.oauthtokens;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class OAuthClientConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/", "/error").permitAll()
                .pathMatchers("/reports/**").authenticated()
                .anyExchange().denyAll()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository clients) {

        var provider = ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .authorizationCode()
            .refreshToken()
            .build();

        var manager = new DefaultReactiveOAuth2AuthorizedClientManager(
            registrations, clients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean
    WebClient reportsWebClient(
            ReactiveOAuth2AuthorizedClientManager manager) {
        var filter =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
        // Không gửi default bearer token tới mọi outbound host.
        return WebClient.builder().filter(filter).build();
    }
}
```

Mã trên bật `oauth2Login()`, `oauth2Client()`, dùng request-context manager với authorization code/refresh-token providers, và gắn WebClient filter. Theo **Spring Security 6.5 Javadoc**, khi WebClient filter được tạo bằng **constructor nhận manager**, handler xóa authorized client trên downstream Resource Server 401/403 **không tự cài đặt**. Production cần quyết định cấu hình `setAuthorizationFailureHandler(...)` với remover dùng **cùng backing repository/service** và chính sách error code phù hợp; xem mục 11.

### 7.6 ReportsController.java

`src/main/java/com/example/oauthtokens/ReportsController.java`:

```java
package com.example.oauthtokens;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

@RestController
public class ReportsController {

    private final WebClient reportsWebClient;

    public ReportsController(WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    @GetMapping("/reports/current")
    public Mono<Map> currentReport() {
        return reportsWebClient.get()
            // Chỉ gọi resource server host cố định, không lấy từ user input.
            .uri("https://api.example.test/reports/current")
            .attributes(clientRegistrationId("reports"))
            .retrieve()
            .bodyToMono(Map.class);
    }
}
```

**Giải thích lifecycle của một request:**

1. Browser cần đăng nhập để gọi `GET /reports/current`.
2. WebClient filter nhận `clientRegistrationId("reports")`, manager tra authorized client theo principal.
3. Nếu chưa được cấp quyền reports, có thể phải thực hiện authorization_code flow có browser/consent; không thể tự login thay user từ background job.
4. Nếu access token còn hạn, filter gắn `Authorization: Bearer <access_token>` tới API đúng host.
5. Nếu token cần refresh và có refresh token/provider, manager có thể gọi Token Endpoint và lưu authorized client mới trước khi gửi HTTP request.
6. Nếu downstream trả 401, đây là lỗi Resource Server đối với access token hoặc auth policy, **không phải** `invalid_grant` của Token Endpoint.
7. Không trả token value từ controller, không bật default authorized client chung cho WebClient được dùng với URL user-controlled.

### 7.7 Đọc metadata bằng @RegisteredOAuth2AuthorizedClient

Spring Security reactive cho phép nhận `OAuth2AuthorizedClient` trong controller parameter:

```java
@GetMapping("/reports/token-info")
public Mono<Map<String, String>> tokenInfo(
    @RegisteredOAuth2AuthorizedClient("reports")
    OAuth2AuthorizedClient client) {

    return Mono.just(Map.of(
        "registration", client.getClientRegistration().getRegistrationId(),
        "expiresAt", client.getAccessToken().getExpiresAt().toString()
    ));
}
```

Đây là **method snippet**, cần import `RegisteredOAuth2AuthorizedClient` từ `org.springframework.security.oauth2.client.annotation`, `OAuth2AuthorizedClient`, `Mono` và `Map`. Không trả `getTokenValue()` và không đưa endpoint debug/metadata này vào production nếu không có nhu cầu bảo mật rõ ràng.

## 8. Service-to-service client_credentials không dùng browser refresh token

Một scheduled job muốn gọi API bằng **danh tính ứng dụng**, không có user session. Hãy khai báo registration khác với `authorization-grant-type: client_credentials`, và một service manager dùng `ReactiveOAuth2AuthorizedClientService`.

Ví dụ bean **thay thế hoặc dùng ở module background riêng**:

```java
package com.example.oauthtokens;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration(proxyBeanMethods = false)
public class ServiceAuthorizedClientExample {

    @Bean("serviceAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager serviceManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService service) {

        var provider = ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Khi có **hai managers**, hãy dùng `@Qualifier("serviceAuthorizedClientManager")` trong background component, tránh constructor không rõ bean nào. Job có thể tạo authorize request:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("service-api")
        .principal("nightly-report-job")
        .build();

return serviceManager.authorize(request)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No authorized client")))
    .map(client -> client.getAccessToken().getTokenValue());
```

Đây là **snippet**, cần `OAuth2AuthorizeRequest` và `Mono`, và chỉ dùng token value **nội bộ** khi gắn Bearer vào WebClient; đừng trả từ public endpoint hoặc log. Principal `nightly-report-job` phải là service identity đáng tin cậy, không đến từ query header do client nhập. Khi access token của client_credentials hết hạn, provider gọi token endpoint xin **token mới** theo grant đó, không phải refresh bằng refresh token.

## 9. Kiểm thử manager offline bằng JUnit 5 + StepVerifier

Ta kiểm thử logic quản lý token **không cần IdP thật**: tạo `ClientRegistration` test, một authorized-client service trong memory, và fake `ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>` để provider refreshToken nhận token mới hoặc lỗi `invalid_grant`.

Test này chạy với Spring Security 6.5, JUnit 5, Reactor Test và dependencies ở `build.gradle`; không cần chạy HTTP server. Đặc biệt, nó xác minh rằng **token refresh thành công phải được persist**, không chỉ được trả ra khỏi provider.

Tạo `src/test/java/com/example/oauthtokens/AuthorizedClientLifecycleTest.java`:

```java
package com.example.oauthtokens;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.endpoint.OAuth2RefreshTokenGrantRequest;
import org.springframework.security.oauth2.client.endpoint.ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class AuthorizedClientLifecycleTest {

    private ClientRegistration registration;
    private InMemoryReactiveClientRegistrationRepository registrations;
    private InMemoryReactiveOAuth2AuthorizedClientService service;
    private Authentication alice;

    @BeforeEach
    void setUp() {
        registration = ClientRegistration.withRegistrationId("reports")
            .clientId("offline-test-client")
            .clientSecret("offline-test-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationUri("https://idp.example.test/authorize")
            .tokenUri("https://idp.example.test/token")
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("reports.read")
            .build();

        registrations =
            new InMemoryReactiveClientRegistrationRepository(registration);
        service = new InMemoryReactiveOAuth2AuthorizedClientService(
            registrations
        );
        alice = UsernamePasswordAuthenticationToken.authenticated(
            "alice",
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }

    private OAuth2AuthorizedClient createClient(
            String accessValue, Instant expiresAt, String refreshValue) {
        Instant issuedAt = expiresAt.minusSeconds(3600);

        OAuth2AccessToken access = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            accessValue, issuedAt, expiresAt,
            Set.of("reports.read")
        );

        OAuth2RefreshToken refresh = refreshValue == null
            ? null
            : new OAuth2RefreshToken(refreshValue, issuedAt);

        return new OAuth2AuthorizedClient(
            registration, "alice", access, refresh
        );
    }

    private void save(OAuth2AuthorizedClient authorizedClient) {
        StepVerifier.create(
            service.saveAuthorizedClient(authorizedClient, alice)
        ).verifyComplete();
    }

    private OAuth2AuthorizeRequest authorizeRequest() {
        return OAuth2AuthorizeRequest
            .withClientRegistrationId("reports")
            .principal(alice)
            .build();
    }

    private AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
            managerWithRefresh(AtomicInteger calls, boolean invalidGrant) {

        ReactiveOAuth2AccessTokenResponseClient<
            OAuth2RefreshTokenGrantRequest> tokenClient = grant -> {
                calls.incrementAndGet();

                if (invalidGrant) {
                    return Mono.error(new OAuth2AuthorizationException(
                        new OAuth2Error("invalid_grant")
                    ));
                }

                OAuth2AccessTokenResponse response =
                    OAuth2AccessTokenResponse.withToken("access-new")
                        .tokenType(OAuth2AccessToken.TokenType.BEARER)
                        .expiresIn(3600)
                        .refreshToken("refresh-new")
                        .scopes(Set.of("reports.read"))
                        .build();

                return Mono.just(response);
            };

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken(config ->
                    config.accessTokenResponseClient(tokenClient))
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Test
    void expiredTokenRefreshesAndSavesNewTokens() {
        save(createClient(
            "access-old", Instant.now().minusSeconds(120), "refresh-old"
        ));

        AtomicInteger calls = new AtomicInteger();
        var manager = managerWithRefresh(calls, false);

        StepVerifier.create(manager.authorize(authorizeRequest()))
            .assertNext(client -> {
                assertThat(client.getAccessToken().getTokenValue())
                    .isEqualTo("access-new");
                assertThat(client.getRefreshToken().getTokenValue())
                    .isEqualTo("refresh-new");
            })
            .verifyComplete();

        assertThat(calls.get()).isEqualTo(1);

        StepVerifier.create(
            service.<OAuth2AuthorizedClient>loadAuthorizedClient(
                "reports", "alice")
        )
            .assertNext(saved -> {
                assertThat(saved.getAccessToken().getTokenValue())
                    .isEqualTo("access-new");
                assertThat(saved.getRefreshToken().getTokenValue())
                    .isEqualTo("refresh-new");
            })
            .verifyComplete();
    }

    @Test
    void validAccessTokenDoesNotTriggerRefresh() {
        save(createClient(
            "access-valid", Instant.now().plusSeconds(3600), "refresh-old"
        ));

        AtomicInteger calls = new AtomicInteger();
        var manager = managerWithRefresh(calls, false);

        StepVerifier.create(manager.authorize(authorizeRequest()))
            .assertNext(client ->
                assertThat(client.getAccessToken().getTokenValue())
                    .isEqualTo("access-valid")
            )
            .verifyComplete();

        assertThat(calls.get()).isZero();
    }

    @Test
    void expiredTokenWithoutRefreshCannotBeRefreshed() {
        save(createClient(
            "access-expired", Instant.now().minusSeconds(120), null
        ));

        AtomicInteger calls = new AtomicInteger();
        var manager = managerWithRefresh(calls, false);

        StepVerifier.create(manager.authorize(authorizeRequest()))
            .assertNext(client -> {
                assertThat(client.getRefreshToken()).isNull();
                assertThat(client.getAccessToken().getTokenValue())
                    .isEqualTo("access-expired");
            })
            .verifyComplete();

        assertThat(calls.get()).isZero();
        // Không gửi token hết hạn tới API; cần authorization-code mới.
    }

    @Test
    void invalidGrantRemovesStaleAuthorizedClient() {
        save(createClient(
            "access-expired",
            Instant.now().minusSeconds(120),
            "refresh-invalid"
        ));

        AtomicInteger calls = new AtomicInteger();
        var manager = managerWithRefresh(calls, true);

        StepVerifier.create(manager.authorize(authorizeRequest()))
            .expectError(OAuth2AuthorizationException.class)
            .verify();

        assertThat(calls.get()).isEqualTo(1);

        StepVerifier.create(
            service.<OAuth2AuthorizedClient>loadAuthorizedClient(
                "reports", "alice")
        ).verifyComplete();
    }

    @Test
    void authorizedClientIsolatedByPrincipal() {
        save(createClient(
            "alice-access", Instant.now().plusSeconds(3600), "alice-refresh"
        ));

        StepVerifier.create(
            service.<OAuth2AuthorizedClient>loadAuthorizedClient(
                "reports", "alice")
        )
            .assertNext(client ->
                assertThat(client.getPrincipalName()).isEqualTo("alice")
            )
            .verifyComplete();

        StepVerifier.create(
            service.<OAuth2AuthorizedClient>loadAuthorizedClient(
                "reports", "bob")
        ).verifyComplete();
    }
}
```

**Test này chứng minh những gì?**

| Kiểm thử | Kết quả mong đợi |
| --- | --- |
| `expiredTokenRefreshesAndSavesNewTokens` | Fake token response client được gọi 1 lần, access/refresh mới được save |
| `validAccessTokenDoesNotTriggerRefresh` | Token còn hạn, không gọi fake refresh client |
| `expiredTokenWithoutRefreshCannotBeRefreshed` | Không có refresh token thì provider không thể “tự tạo” refresh; client cũ có thể được trả lại |
| `invalidGrantRemovesStaleAuthorizedClient` | Token Endpoint báo `invalid_grant`, default failure handler loại stale client |
| `authorizedClientIsolatedByPrincipal` | Tra principal bob không lấy token của alice |

**Ngữ nghĩa quan trọng:** Khi expired access token **không có refresh token**, một manager/provider không hỗ trợ reauthorization có thể **trả lại client cũ** thay vì phát token mới. Do đó caller không được suy luận `authorize()` hoàn tất thành công nghĩa là token luôn còn hạn. Với user-delegated flow phải khởi động authorization code lại nếu cần.

Chạy test:

```bash
./gradlew test --tests '*AuthorizedClientLifecycleTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*AuthorizedClientLifecycleTest'
```

Đây là **kết quả kỳ vọng từ mã Java**, chưa phải một lần build/test được thực thi ở môi trường soạn bài. Test không truy cập IdP thật vì `ReactiveOAuth2AccessTokenResponseClient` trả `Mono` ngay trong process.

## 10. WebClient gắn Bearer token: không gửi nhầm host

`ServerOAuth2AuthorizedClientExchangeFilterFunction` nhận authorized client hoặc registration ID từ attributes của `WebClient` request. Khi được chọn và được manager xử lý, filter gắn access token vào header:

```http
GET /reports/current HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_ONLY>
```

Các cách chọn phổ biến:

```java
webClient.get()
    .uri("https://api.example.test/reports/current")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .clientRegistrationId("reports")
    )
    .retrieve()
    .bodyToMono(String.class);
```

Hoặc khi đã có một `OAuth2AuthorizedClient` được resolve:

```java
webClient.get()
    .uri("https://api.example.test/reports/current")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .oauth2AuthorizedClient(authorizedClient)
    )
    .retrieve()
    .bodyToMono(String.class);
```

Các đoạn này là **snippets** trong method có biến `webClient` và `authorizedClient`. Chúng minh họa explicit selection, không phải class độc lập.

### 10.1 Vì sao không bật default authorized client?

Các tùy chọn `setDefaultOAuth2AuthorizedClient(true)` hoặc `setDefaultClientRegistrationId(...)` có thể khiến **nhiều WebClient requests** tự mang Bearer, kể cả khi target URL không phải Resource Server đáng tin. Nếu URL do user nhập/attacker điều khiển hoặc WebClient đi theo redirect tới host ngoài danh sách, token có thể bị rò rỉ.

**Ưu tiên:**
- WebClient chuyên dụng cho một downstream host đáng tin, fixed URL/host allowlist.
- Explicit `clientRegistrationId` hoặc `oauth2AuthorizedClient` trên từng request.
- Không nhận URL tùy ý từ query/body rồi dùng WebClient có OAuth2 filter.
- Tách user-delegated token và service-to-service token.
- Kiểm audience, scopes và trust của Resource Server; không dựa vào việc URL “trông giống” domain được phép.

### 10.2 WebClient failure handler và access token invalid

Theo Javadoc Spring Security 6.5, constructor filter nhận **manager** không tự cài `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` khi Resource Server trả lỗi. Nếu không cấu hình, client có thể tiếp tục dùng token stale ở những lần gọi sau.

Tại production, dùng `filter.setAuthorizationFailureHandler(...)` với remover sử dụng **đúng storage** của manager. Failure handler chỉ nên remove trên OAuth2 error codes phù hợp, không mặc định xóa mọi 403. Lưu ý: **Manager failure handler** xử lý lỗi Authorization Server/token grant; **WebClient filter failure handler** xử lý response Resource Server.

## 11. Lỗi hết hạn, invalid_grant, HTTP 401/403

### 11.1 invalid_grant là lỗi Token Endpoint

OAuth2 `invalid_grant` có thể cho biết refresh token bị revoke, hết hạn, đã rotate, không khớp client hoặc không còn hợp lệ theo IdP. Phản ứng an toàn:

1. Không gửi lại refresh token cũ liên tục.
2. Loại authorized client stale hoặc xử lý theo optimistic-state nếu đã có token mới do request khác.
3. Nếu có user session, yêu cầu authorization code/consent lại; không tự mạo danh user.
4. Với client_credentials, dùng grant mới tương ứng chứ không “refresh” bằng token không tồn tại.
5. Ghi metrics/log **mã lỗi** và registration ID, không ghi refresh token.

### 11.2 Resource Server 401 không đồng nghĩa invalid_grant

`401 Unauthorized` từ downstream API có thể do expired/revoked access token, sai audience/issuer hoặc cấu hình trust khác. Đừng tự giả định chỉ cần refresh token. Xem `WWW-Authenticate` error code nếu có, đăng ký failure handler phù hợp, và xác minh token dùng **đúng resource**.

### 11.3 Resource Server 403 không chắc do token hết hạn

`403 Forbidden` thường là thiếu scope, role, resource ownership hoặc policy. Làm mới access token thường **không tự cấp scope cao hơn**. Không viết vòng lặp “403 → refresh → retry” không giới hạn; nó có thể tạo token storms và không giải quyết được thiếu quyền.

### 11.4 Không retry POST/PUT bất cẩn

Sau khi làm mới token, retry outbound request cần cân nhắc:
- GET/idempotent request thường dễ retry hơn write API.
- POST/PUT/PATCH có thể gây side effects đã thực hiện một phần.
- Dùng idempotency key, deduplication và transaction boundaries cho write APIs.
- Giới hạn retry/backoff/timeout, không retry mã lỗi không thể hồi phục.
- Nếu request body là stream không replay được, không thử retry khi không có cơ chế recreate publisher an toàn.

## 12. Concurrent refresh, refresh-token rotation và multi-pod

Đây là điểm production thường khó nhất:

```text
Store tại thời điểm T0:
  principal=alice, registration=reports
  access=A1 (gần hết hạn), refresh=R1

Request A -> refresh(R1) -> IdP trả A2 + R2
Request B -> refresh(R1) -> IdP trả invalid_grant
Request A -> save A2/R2
Request B -> remove stale -> nếu xóa mù có thể xóa A2/R2
```

Khi IdP bật one-time refresh token và reuse detection, đồng thời refresh trên nhiều pods có thể khiến client bị mất quyền dù một request đã refresh thành công.

**Giải pháp cần đánh giá:**

1. **Single-flight / per-key lock** theo registration + principal + tenant; không dùng một global lock cho mọi users.
2. Dùng **versioned storage/optimistic locking** để không cho request B xóa hoặc ghi đè client mới từ A.
3. Khi gặp `invalid_grant`, kiểm tra store đã được cập nhật/rotate hay chưa trước khi quyết định xóa.
4. Timeout lock và xử lý process crash; tránh deadlock hoặc infinite wait.
5. Phân biệt provider có rotation/reuse detection với provider dùng refresh token có thể reuse.
6. Có refresh throttling, clock skew phù hợp và metrics số attempts/errors.
7. Không cho mỗi replica giữ một in-memory token store nếu việc làm mới phải đồng bộ.

**Framework không tự bảo đảm khóa phân tán/atomic rotation cho mọi ứng dụng.** Storage và concurrency control là một phần của thiết kế production, không thể giải quyết chỉ bằng `refreshToken()`.

## 13. Token storage, bảo mật, logout và thu hồi

### 13.1 Lưu tokens ở đâu?

- Access và refresh tokens lưu **server-side**, có encryption at rest/key management, ít người có quyền đọc.
- Dùng `ReactiveOAuth2AuthorizedClientService` phù hợp với nhu cầu persistence, tránh lộ token trong logs/traces/backups.
- Protect `client-secret` trong environment/secrets manager; không commit secret vào Git, không embed vào JS bundle.
- Dùng HTTPS/TLS tới IdP, Resource Server và browser; xác minh certificates và redirect URIs.
- Áp dụng least-privilege scopes, đúng audience/issuer, session security và PKCE/state protection ở authorization code flow.
- Token lưu theo principal/tenant/issuer đáng tin cậy; không cho client tùy ý yêu cầu token của người dùng khác.
- Cần cơ chế cleanup stale authorized clients sau user deletion, logout hoặc consent revocation.

### 13.2 Logout local không phải revoke tại IdP

Kết thúc WebSession của app **không nhất thiết** khiến access/refresh token đã cấp bị vô hiệu ở Authorization Server. Có ba hành động khác nhau:

1. **Local logout:** hủy user session.
2. **Local authorized-client removal:** xóa `OAuth2AuthorizedClient` khỏi repository/service.
3. **Remote token revocation:** nếu IdP hỗ trợ, gọi token revocation endpoint (RFC 7009) cho token cần thu hồi; với OIDC có các cơ chế logout liên quan.

Không ghi “token đã bị revoke” nếu ứng dụng chỉ xóa DB record cục bộ. Một token đã bị lấy ra khỏi store vẫn có thể hợp lệ tới hết hạn hoặc được IdP revoke.

### 13.3 Không trả token trong API/log

Tránh:

```java
// KHÔNG dùng trong controller:
return Mono.just(authorizedClient.getRefreshToken().getTokenValue());
```

Thay vào đó, nếu thật sự cần vận hành, chỉ log metadata được allowlist, như:
- registration ID;
- loại grant;
- token expiry **không kèm token value**;
- error code đã sanitize;
- request correlation ID không chứa secret.

Không log toàn bộ `OAuth2AuthorizedClient`, OAuth2 token response, `Authorization` header hoặc email/PII không cần thiết. Refresh token có thể mang quyền dài hạn nên cần xem nó như secret rất nhạy cảm.

## 14. Checklist kiểm thử

Một bộ kiểm thử token lifecycle nên bao gồm:

| Tình huống | Kỳ vọng |
| --- | --- |
| Không có authorized client | Grant/authorization code được yêu cầu đúng flow, không mạo danh user |
| Token còn hạn xa | Reuse, không gọi Token Endpoint |
| Token sắp hết hạn trong skew | Refresh provider được gọi nếu có refresh token |
| Token hết hạn có refresh token | Token response mới, lưu access và refresh mới nếu rotate |
| Token hết hạn không có refresh | Không giả mạo refresh; reauthorize khi cần |
| Token Endpoint trả invalid_grant | Loại stale state/reauthorize, không retry vô hạn |
| IdP timeout/5xx | Fail closed, bounded retry, không cấp quyền khi không có token hợp lệ |
| Resource Server 401 invalid_token | Failure handler xử lý đúng storage/error code |
| Resource Server 403 insufficient_scope | Không tự xin quyền cao hơn bằng refresh |
| User alice và bob cùng registration | Token không bị dùng chéo |
| Hai requests refresh đồng thời | Atomic/optimistic update không xóa token mới |
| Logout/revocation | Local cleanup khác remote revocation |
| Multi-replica restart | Shared store hoặc reauth strategy hoạt động |
| WebClient gọi unknown host | Không tự mang Bearer token |
| Scheduled job | Dùng service manager, không cần ServerWebExchange |

## 15. Lỗi phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Nhầm `ClientRegistration` với `OAuth2AuthorizedClient` | Không lưu đúng token theo principal | Hiểu cấu hình client khác trạng thái đã cấp quyền |
| Tưởng đăng nhập app đồng nghĩa đã có authorized client cho mọi API | Thiếu consent/scope | Kiểm registration + authorized client tương ứng |
| Dùng access token thay refresh token ở Token Endpoint | Sai grant request | Sử dụng refresh token chỉ ở Token Endpoint |
| Dùng refresh token làm Bearer gọi Resource Server | Rò rỉ credential cực nhạy | Chỉ gửi access token outbound |
| Cho rằng authorization_code luôn có refresh token | Null refresh token/error | Kiểm policy IdP và offline access |
| Cho rằng client_credentials có refresh token | Logic renewal sai | Xin access token mới bằng client_credentials |
| Dùng manager web trong scheduled job | Không có ServerWebExchange | Dùng service manager |
| Lưu token theo registration ID mà không tách principal | Token user A bị gửi cho user B | Key theo registration+principal+tenant |
| Mặc định WebClient mang token cho mọi host | Token exfiltration/SSRF | Explicit authorized client + trusted URL |
| Nhầm outbound client với inbound resource validation | Token inbound chưa được verify | `oauth2ResourceServer` riêng |
| Retry vô hạn invalid_grant | Token Endpoint storm, không sửa state | Xóa stale authorized client/re-authorization |
| Refresh trên nhiều pods không lock khi rotation | Reuse error, xóa nhầm token mới | Per-key sync/CAS |
| Chỉ dùng in-memory store khi scale | Mất/khác state | Persistent/shared store |
| Bỏ qua filter failure handler của constructor manager | Reuse stale bearer sau downstream 401 | Cấu hình handler đúng với backing store |
| Gặp 403 thì refresh bất kể scope | Không được thêm quyền, retry vô hạn | Kiểm insufficient_scope/authorization |
| Logout app nhưng tuyên bố token revoked | Token có thể vẫn hợp lệ ở IdP | RFC 7009/OIDC logout khi cần |
| Lộ secret qua logs, metrics, traces | Token/client secret compromise | Redaction, allowlist metadata |
| Test chỉ happy path | Bỏ sót expiry, lỗi, race và principal leakage | Unit + integration negative cases |

## 16. Câu hỏi tự kiểm tra

**1. `OAuth2AuthorizedClient` có chứa client ID và token của mọi user trong một object không?** Không. Mỗi authorized client gắn một registration với **một principal** và token tương ứng; nhiều users tạo nhiều authorized clients.

**2. Access token dùng ở đâu?** Gửi tới đúng Resource Server bằng `Authorization: Bearer`. Không dùng nó làm refresh token.

**3. Refresh token dùng ở đâu?** Gửi tới Authorization Server Token Endpoint trong refresh-token grant. Không gửi ra browser/API nghiệp vụ.

**4. Tại sao `getRefreshToken()` có thể null?** IdP không bắt buộc cấp refresh token theo grant/scope/policy; phải xử lý trường hợp này.

**5. `refreshToken()` tự refresh ngay sau login à?** Không. Nó được sử dụng khi access token cần reauthorize, có refresh token và manager gọi provider.

**6. Client credentials hết hạn phải làm gì?** Xin token mới bằng `client_credentials` grant, thường không dùng refresh token.

**7. Khi nào dùng `DefaultReactiveOAuth2AuthorizedClientManager`?** Khi có `ServerWebExchange` trong reactive HTTP request.

**8. Khi nào dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`?** Trong job/service/background process không có web exchange.

**9. `invalid_grant` là HTTP 401 từ downstream API đúng không?** Không. Đây là OAuth2 error từ Token Endpoint khi grant/refresh không hợp lệ; Resource Server 401 là một tầng khác.

**10. Refresh token rotation cần làm gì ở client?** Lưu token mới và tránh các refresh đồng thời ghi đè/xóa nhau, nhất là multi-pod.

**11. Vì sao không bật default bearer token cho mọi WebClient call?** Có thể gửi credentials tới sai host hoặc URL do attacker kiểm soát.

**12. Token mới có tự tăng scope khi gặp 403 không?** Không. Phải có IdP consent/policy và Resource Server authorization phù hợp.

**13. Logout app có tự thu hồi token tại IdP không?** Không bảo đảm; local cleanup khác remote revocation.

**14. Manager trả authorized client dù access token đã hết hạn có khả năng xảy ra không?** Có nếu provider không thể reauthorize (ví dụ thiếu refresh token); caller không được gửi token hết hạn như thể hợp lệ.

**15. Một test đơn vị fake Token Endpoint có thay thế test IdP thực không?** Không. Nó kiểm manager/persistence, còn OIDC metadata, redirect, PKCE, scopes, rotation và downstream authorization cần integration test riêng.

## 17. Tổng kết

**`OAuth2AuthorizedClient` là kết quả cấp quyền của OAuth2 Client**: nó gắn `ClientRegistration` với principal, access token và refresh token tùy chọn. `ReactiveOAuth2AuthorizedClientManager` điều phối cấp mới, kiểm expiry, làm mới và lưu state. `ServerOAuth2AuthorizedClientRepository` / `ReactiveOAuth2AuthorizedClientService` quản lý persistence; `ServerOAuth2AuthorizedClientExchangeFilterFunction` đính kèm Bearer **access token** cho `WebClient`.

Điểm cần ghi nhớ: **access token và refresh token phục vụ hai đích khác nhau; refresh token không phải lúc nào cũng được cấp; client_credentials thường xin token mới thay vì refresh; invalid_grant cần dọn stale state; và refresh-token rotation phải được xử lý an toàn khi có nhiều requests/pods**. Spring Security hỗ trợ lifecycle thông thường nhưng không tự giải quyết mọi vấn đề về token leakage, revocation, distributed locking hay data authorization.

### Nguồn tham khảo chính thức

- [Spring Security 6.5 — Reactive OAuth2 Client Core Interfaces](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html)
- [Spring Security 6.5 — Authorized Client Features và WebClient integration](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html)
- [Spring Security 6.5 — Reactive OAuth2 Authorization Grants](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html)
- [Spring Security 6.5 — Reactive OAuth2 Client overview](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/)
- [Spring Security 6.5 — ServerOAuth2AuthorizedClientExchangeFilterFunction API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html)
- [Spring Security 6.5 — ReactiveOAuth2AuthorizedClientManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientManager.html)
- [Spring Boot 3.5 — OAuth2 client registration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [RFC 6749 — Refresh an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6)
- [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
