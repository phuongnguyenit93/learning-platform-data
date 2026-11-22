# 34.7. Ứng dụng WebFlux đăng nhập OIDC và gọi downstream

## Mục tiêu bài thực hành

Bài này xây dựng một ví dụ đầy đủ về **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client trên WebFlux**: người dùng đăng nhập vào Reactive Portal qua OpenID Provider, Portal quản lý OAuth2 authorized client, sau đó dùng `WebClient` gửi access token tới một downstream Orders API được bảo vệ bằng Resource Server.

Kết quả mong muốn:

- Portal ở `http://localhost:8080` sử dụng **WebFlux + OIDC Login**.
- Orders API ở `http://localhost:8081` sử dụng **WebFlux + JWT Resource Server**.
- OpenID Provider/Authorization Server (OP/AS) là hệ thống độc lập được cấu hình ở môi trường local hoặc test.
- Browser giữ session cookie của Portal; **không nhận refresh token trong JSON**.
- Portal dùng `ReactiveOAuth2AuthorizedClientManager` và `ServerOAuth2AuthorizedClientExchangeFilterFunction` để lấy/đính kèm access token khi gọi API.
- Orders API xác minh token signature, issuer, expiry, audience và `orders.read` scope.
- Những lỗi thiếu authentication, sai audience, thiếu scope và gọi nhầm host được xử lý an toàn.
- Tất cả HTTP công việc downstream được compose với `Mono`/`Flux`, không gọi `block()` trong request path.

Sau khi hoàn thành, bạn có thể tự mở rộng sang Redis-backed session, multi-tenant access control, token refresh và reactive integration tests.

> **Quan trọng:** ID token dùng xác nhận người dùng cho Portal, access token dùng truy cập Orders API. Hai token không hoán đổi cho nhau. Cấu hình OIDC Login không tự biến Portal thành Resource Server, và API không thể tin session cookie của Portal.

---

## 1. Kiến trúc cần xây

~~~mermaid
flowchart LR
    B["Alice / Browser"] -->|"Portal cookie"| P["Reactive Portal :8080"]
    P -->|"OIDC Code exchange, refresh"| OP["OpenID Provider / AS"]
    OP -->|"ID + access token"| P
    P -->|"Bearer access token"| API["Orders API :8081"]
    API -->|"JWT validation / JWKS"| OP
    API -->|"Owner + tenant policy"| DB["Orders database"]
    API -->|"Orders JSON"| P
    P -->|"JSON / HTML"| B
~~~

### 1.1. Ba ranh giới bảo mật

| Ranh giới | Credential chính | Bên xác minh |
|---|---|---|
| Browser → Portal | Session cookie | Portal |
| Portal → OP token endpoint | Authorization code/refresh token, client authentication | AS |
| Portal → Orders API | OAuth access token | Orders API Resource Server |

Web session cookie không tự có giá trị ở Orders API. ID token có audience dành cho OIDC Relying Party không phải Bearer token của API.

### 1.2. Vì sao chọn BFF?

Portal hoạt động như **Backend for Frontend**: browser tương tác với Portal bằng cookie, backend giữ access/refresh tokens, và WebClient gọi API. Nhờ đó browser không phải tự lưu raw refresh token ở localStorage.

Thiết kế BFF vẫn phải bảo vệ CSRF, XSS, cookies, session fixation, server-side token store, redirects và destination host.

### 1.3. Những trách nhiệm không được gộp

- **OIDC Authentication**: OP xác thực Alice, Portal có `OidcUser`.
- **OAuth2 Client Authorization**: AS cấp access token cho đúng resource/scope, Portal có `OAuth2AuthorizedClient`.
- **API Authorization**: Orders API xác minh token và quyền trên từng order.

Có OIDC Login thành công chưa chắc Alice được xem mọi order.

## 2. Chuẩn bị môi trường

Cần JDK tương thích Spring Boot 3.x / Spring Framework 6.x, Maven hoặc Gradle và một OP tương thích OpenID Connect (ví dụ OP chạy local/staging).

Tại OP, cấu hình một **confidential client**:

~~~text
Issuer URI:       https://id.example.test/realms/demo
Client ID:        reactive-portal
Client Secret:    <test-secret>
Authorization:    authorization_code
Redirect URI:     http://localhost:8080/login/oauth2/code/corporate
Requested scopes: openid profile orders.read
API audience:     orders-api
Test user:        alice-123
~~~

Các URLs là placeholders. Khi chạy thật, thay bằng issuer/endpoint thực và bảo đảm **cả Portal lẫn Orders API có thể kết nối issuer và JWKS**.

### 2.1. Scope chưa đảm bảo audience

Nhiều OP không tự cấp access token có `aud=orders-api` chỉ vì client xin `orders.read`. Có thể cần đăng ký API resource, audience mapper hoặc authorization policy tại OP.

### 2.2. Token mẫu đúng loại

Một JWT access token cho Orders API có thể chứa:

~~~json
{
  "iss": "https://id.example.test/realms/demo",
  "sub": "alice-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1795000000
}
~~~

Claims minh họa, không phải JWT thực. Access token có thể là opaque; nếu vậy phải đổi Resource Server validation sang introspection.

### 2.3. Không commit client secrets

Lưu `OIDC_CLIENT_SECRET` trong secret store hoặc biến môi trường server. Không đưa client secret vào code, frontend bundle hoặc Git.

## 3. Cấu trúc hai ứng dụng

~~~text
reactive-oidc-lab/
├── portal/
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/example/portal/
│       │   ├── PortalApplication.java
│       │   ├── PortalSecurityConfig.java
│       │   ├── PortalOAuthClientConfig.java
│       │   ├── OrdersGateway.java
│       │   └── PortalController.java
│       └── resources/application.yml
└── orders-api/
    ├── pom.xml
    └── src/main/
        ├── java/com/example/orders/
        │   ├── OrdersApiApplication.java
        │   ├── ApiSecurityConfig.java
        │   ├── JwtAudienceConfig.java
        │   └── OrdersController.java
        └── resources/application.yml
~~~

Mỗi app có `@SpringBootApplication` và process riêng. Đừng chia sẻ `SecurityContext` hay WebSession giữa Portal và Resource Server.

## 4. Tạo Portal: dependencies

Trong Spring Boot Maven project của Portal:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
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
~~~

Dùng Boot BOM để quản lý versions. Với WebFlux, không thêm Servlet MVC starter nếu mục tiêu là một reactive web application thuần túy.

### 4.1. `webflux` cung cấp gì?

`Mono` và `Flux` từ Reactor, `WebClient` và reactive HTTP handling. Spring Security sử dụng `SecurityWebFilterChain` thay vì Servlet `SecurityFilterChain`.

### 4.2. `oauth2-client` khác `oauth2-resource-server`

Portal cần OAuth2 Client starter để login và gọi API. Orders API cần Resource Server starter để xác minh incoming Bearer token.

## 5. Cấu hình Portal OIDC Client

`portal/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-op
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company-op:
            issuer-uri: ${OIDC_ISSUER_URI}

app:
  orders-api:
    base-url: ${ORDERS_API_BASE_URL:http://localhost:8081}
~~~

### 5.1. Registration ID là `corporate`

Nó xuất hiện trong authorization initiation và callback routes:

~~~text
/oauth2/authorization/corporate
/login/oauth2/code/corporate
~~~

### 5.2. `openid` yêu cầu OIDC

Khi OIDC flow thành công, Spring Security xác minh ID token và tạo `OidcUser`. Scope `profile` cung cấp profile claims nếu OP cho phép.

### 5.3. `orders.read` là OAuth scope

Scope này chỉ xin quyền cấp token; Orders API vẫn phải xác minh token có scope, audience, issuer và domain permission.

### 5.4. Callback chính xác tại OP

OP phải allowlist redirect URI `http://localhost:8080/login/oauth2/code/corporate` trong local development. Production dùng HTTPS public origin đúng.

### 5.5. Reverse proxy

Nếu TLS kết thúc ở ingress, cấu hình forwarded-header trust và base URL đúng. Không cho Internet tự đặt arbitrary forwarded headers để thay redirect URI.

## 6. PortalApplication

~~~java
package com.example.portal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PortalApplication {
    public static void main(String[] args) {
        SpringApplication.run(PortalApplication.class, args);
    }
}
~~~

Chạy ứng dụng bằng Maven/Gradle theo project. Đảm bảo `OIDC_ISSUER_URI` là issuer có discovery metadata và JWKS hợp lệ.

## 7. Reactive SecurityWebFilterChain

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class PortalSecurityConfig {

    @Bean
    SecurityWebFilterChain portalSecurity(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/", "/login", "/error")
                        .permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

### 7.1. `oauth2Login()`

Xử lý browser redirect, state/callback, code exchange, ID token validation và tạo Authentication của Portal.

### 7.2. `oauth2Client()`

Hỗ trợ OAuth2 authorized-client infrastructure cho outbound API calls. Nó không tự bảo vệ Orders API.

### 7.3. `authorizeExchange(...)`

WebFlux dùng `authorizeExchange` thay vì Servlet `authorizeHttpRequests`.

### 7.4. Giữ CSRF cho Portal

Portal dùng browser cookie. Không tắt CSRF toàn cục chỉ vì có OAuth2; state-changing POST/PUT/DELETE cần chống CSRF theo design.

### 7.5. Authentication khác domain authorization

`authenticated()` không chứng minh Alice có quyền truy cập mọi tenant/order. Quyền cụ thể thuộc API/domain service.

## 8. Bắt đầu OIDC Login

Mở:

~~~text
http://localhost:8080/oauth2/authorization/corporate
~~~

Chuỗi sự kiện:

1. Portal tạo Authorization Request với state và OIDC parameters.
2. Browser được redirect đến OP.
3. OP xác thực Alice và yêu cầu consent nếu policy cần.
4. OP redirect về Portal với `code` và `state`.
5. Spring Security đối chiếu pending authorization request.
6. Portal đổi code tại token endpoint.
7. Spring Security xác minh ID token và tạo Authentication.
8. Session và authorized-client state được lưu theo configuration.

Không tự gửi authorization code lấy từ browser tới API khác. Không bỏ state/nonce/PKCE validation khi callback thất bại.

## 9. Đọc OIDC principal

Tạo controller chỉ xuất identity tối thiểu:

~~~java
package com.example.portal;

import org.springframework.security.core.annotation
        .AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MeController {

    @GetMapping("/me")
    Mono<MeView> me(
            @AuthenticationPrincipal OidcUser user) {

        return Mono.just(new MeView(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject(),
                user.getFullName()));
    }

    record MeView(
            String issuer, String subject, String displayName) {}
}
~~~

### 9.1. OIDC Authentication

`OAuth2AuthenticationToken` thường chứa `OidcUser` principal cùng registration ID. `OidcUser` có ID token và có thể có UserInfo.

### 9.2. Subject không globally unique

OIDC `sub` là định danh trong phạm vi `iss`. Hệ thống nhiều OP phải dùng issuer+subject hoặc internal identity mapping đã xác minh.

### 9.3. Không serialize raw OIDC objects

Không trả `OidcUser`/ID token/access token/refresh token trực tiếp ra browser JSON. Trả DTO với claims thực sự cần cho UI.

### 9.4. Display name có thể thiếu

Không dựa vào email hoặc display name làm authorization identity key.

## 10. `OidcUser` và `OAuth2AuthorizedClient` khác nhau

~~~text
OAuth2AuthenticationToken
  principal = OidcUser
  authenticated = true
  registrationId = corporate

OAuth2AuthorizedClient
  clientRegistration = corporate
  principalName = Alice
  accessToken = A1
  refreshToken = R1 (nếu AS cấp)
~~~

| Token/credential | Vai trò | Nơi gửi |
|---|---|---|
| ID token | Portal biết Alice được OP xác thực | Relying Party/Portal |
| Access token | Cho phép gọi protected resource | Orders API đúng audience |
| Refresh token | Xin access token mới | AS token endpoint |
| Session cookie | Browser nhận diện Portal session | Portal |
| Client secret | Confidential client authentication | AS token endpoint |

**Không dùng `user.getIdToken().getTokenValue()` làm Bearer token tới Orders API.** Access token được lấy từ `OAuth2AuthorizedClient`.

## 11. Reactive OAuth2AuthorizedClientManager

Tạo manager để tìm authorized client hiện tại và refresh khi cần.

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration
        .ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web
        .DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server
        .ServerOAuth2AuthorizedClientRepository;

@Configuration
public class PortalOAuthClientConfig {

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        var provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .build();

        var manager =
                new DefaultReactiveOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

### 11.1. Reactive contract

`ReactiveOAuth2AuthorizedClientManager.authorize(...)` trả `Mono<OAuth2AuthorizedClient>`. Nó không bắt ứng dụng dùng `block()` để đợi access token.

### 11.2. Provider chain

`authorizationCode()` hỗ trợ authorization tương ứng với interactive login, `refreshToken()` xử lý access token hết/gần hết hạn khi có refresh token hợp lệ.

### 11.3. Store phải đúng principal

Authorized client có thể được lưu theo registration/user/session. Không dùng một static singleton access token cho mọi user.

### 11.4. Khi nhiều Pods

WebSession, pending state và authorized-client storage cần persistence hoặc sticky routing phù hợp. Không bỏ OAuth state validation để sửa lỗi callback đi sang Pod khác.

### 11.5. Background job

Service chạy ngoài web exchange có thể dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` phù hợp phiên bản, thay vì manager dựa trên `ServerWebExchange`.

## 12. WebClient có OAuth2 filter

~~~java
package com.example.portal;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client
        .ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OrdersWebClientConfig {

    @Bean
    WebClient ordersApiWebClient(
            ReactiveOAuth2AuthorizedClientManager manager,
            @Value("${app.orders-api.base-url}") String apiBaseUrl) {

        var oauth2 =
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                        manager);

        return WebClient.builder()
                .baseUrl(apiBaseUrl)
                .filter(oauth2)
                .build();
    }
}
~~~

### 12.1. OAuth2 exchange filter làm gì?

Khi outbound request có `OAuth2AuthorizedClient` trong attributes, filter thêm access token vào header:

~~~http
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

### 12.2. Giữ URL cố định

Base URL lấy từ trusted backend config. Không cho caller tự cung cấp host tùy ý rồi gắn Bearer token.

### 12.3. Không bật token forwarding mặc định cho mọi request

Dùng explicit authorized client per request. Nếu filter tự động dùng principal mặc định cho mọi host, dễ làm lộ token ở outbound URL ngoài dự kiến.

### 12.4. API vẫn tự xác minh token

Có Authorization header không đồng nghĩa token hợp lệ với Orders API.

## 13. OrdersGateway: authorize rồi gọi API

~~~java
package com.example.portal;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client
        .ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class OrdersGateway {

    private final WebClient ordersWebClient;
    private final ReactiveOAuth2AuthorizedClientManager manager;

    public OrdersGateway(
            WebClient ordersApiWebClient,
            ReactiveOAuth2AuthorizedClientManager manager) {
        this.ordersWebClient = ordersApiWebClient;
        this.manager = manager;
    }

    public Mono<List<OrderView>> list(
            Authentication authentication,
            ServerWebExchange exchange) {

        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                        .withClientRegistrationId("corporate")
                        .principal(authentication)
                        .attribute(
                                ServerWebExchange.class.getName(),
                                exchange)
                        .build();

        return manager.authorize(request)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.UNAUTHORIZED,
                                "OAuth client authorization required")))
                .flatMap(authorized ->
                        ordersWebClient.get()
                                .uri("/api/orders")
                                .attributes(
                                        ServerOAuth2AuthorizedClientExchangeFilterFunction
                                                .oauth2AuthorizedClient(
                                                        authorized))
                                .retrieve()
                                .bodyToFlux(OrderView.class)
                                .collectList());
    }

    public record OrderView(String id, String status) {}
}
~~~

### 13.1. Vì sao phải có `Authentication`?

Manager cần biết principal hiện tại để tìm authorized client của đúng user.

### 13.2. Vì sao truyền `ServerWebExchange`?

WebFlux manager/repository cần web request/session context để load/save authorized client.

### 13.3. `switchIfEmpty`

Nếu manager không thể lấy authorization và trả empty publisher, ứng dụng xử lý rõ ràng; không dereference null.

### 13.4. `oauth2AuthorizedClient(authorized)`

Đây là request attribute cho OAuth2 filter. Filter lấy **access token** của authorized client, không lấy ID token.

### 13.5. Không gọi `block()`

`OrdersGateway.list()` trả `Mono<List<OrderView>>`. WebFlux quản lý subscription; không block event loop đợi `WebClient`.

### 13.6. Không gọi host từ input người dùng

`.uri("/api/orders")` là relative path từ trusted base URL. Nếu dùng `?url=https://attacker.example` rồi forward token, sẽ tạo rủi ro SSRF/token exfiltration.

## 14. PortalController cho browser

~~~java
package com.example.portal;

import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class PortalController {

    private final OrdersGateway gateway;

    public PortalController(OrdersGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/orders")
    Mono<List<OrdersGateway.OrderView>> orders(
            Authentication authentication,
            ServerWebExchange exchange) {

        return gateway.list(authentication, exchange);
    }
}
~~~

### 14.1. Browser chỉ gửi cookie

~~~http
GET /orders HTTP/1.1
Host: localhost:8080
Cookie: SESSION=...
~~~

Portal chuyển thành server-side API request chứa Bearer access token. Browser không được phép yêu cầu Portal trả raw access token.

### 14.2. Authentication khác principal name

`Authentication.getName()` không nhất thiết là email. Đừng dùng email làm security key nếu OP có immutable subject.

### 14.3. Đừng giữ Authentication trong field của singleton

Reactive requests phục vụ nhiều users đồng thời. Truyền Authentication trong reactive context hoặc method argument, không lưu biến `currentUser` ở singleton bean.

## 15. Phương án `@RegisteredOAuth2AuthorizedClient`

Ở các Spring Security versions hỗ trợ WebFlux controller argument resolver, có thể nhận authorized client trực tiếp:

~~~java
@GetMapping("/orders/alternative")
Mono<List<OrdersGateway.OrderView>> alternative(
        @RegisteredOAuth2AuthorizedClient("corporate")
        OAuth2AuthorizedClient client) {

    return ordersWebClient.get()
            .uri("/api/orders")
            .attributes(
                    ServerOAuth2AuthorizedClientExchangeFilterFunction
                            .oauth2AuthorizedClient(client))
            .retrieve()
            .bodyToFlux(OrdersGateway.OrderView.class)
            .collectList();
}
~~~

Method minh họa cần đặt trong controller có `ordersWebClient` đã inject. Imports: `org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient` và `org.springframework.security.oauth2.client.OAuth2AuthorizedClient`.

### 15.1. Chọn annotation khi nào?

Khi controller chỉ cần authorized client của registration đang đăng nhập. Với token lifecycle/refresh/error policy phức tạp, manager explicit giúp kiểm soát behavior và dễ test.

### 15.2. Không tự coi annotation là bằng chứng refresh đúng

Test authorized-client repository, manager và token endpoint riêng để xác minh refresh, rotation và persistence.

## 16. Orders API dependencies

`orders-api/pom.xml`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
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
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

### 16.1. API là Resource Server

Orders API không thực hiện OIDC browser Login. Nó nhận access token từ Portal và xác minh incoming Bearer authentication.

### 16.2. Không dùng Portal session

Orders API không tin Portal cookie hoặc serialize `SecurityContext` từ Portal qua mạng.

## 17. Orders API configuration

`orders-api/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8081

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OIDC_ISSUER_URI}

app:
  security:
    required-audience: orders-api
~~~

`app.security.required-audience` là **property custom** dùng bởi validator ở phần tiếp theo. Spring Security không tự xác minh audience chỉ vì custom property tồn tại.

## 18. Orders API SecurityWebFilterChain

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context
        .NoOpServerSecurityContextRepository;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {

        return http
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .securityContextRepository(
                        NoOpServerSecurityContextRepository
                                .getInstance())
                .authorizeExchange(auth -> auth
                        .pathMatchers(
                                HttpMethod.GET, "/api/orders")
                        .hasAuthority("SCOPE_orders.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

### 18.1. Vì sao API tắt CSRF?

Ví dụ này là **bearer-only API**, không dùng browser cookie/session làm authentication. Vì thế có thể tắt CSRF token requirement. Không copy cấu hình này sang Portal dùng session cookie.

### 18.2. `SCOPE_orders.read`

Spring Security JWT Resource Server thường map `scope` hoặc `scp` claim thành authorities tiền tố `SCOPE_`. Nếu OP trả claim khác, cấu hình converter theo contract.

### 18.3. Stateless security context

`NoOpServerSecurityContextRepository` tránh lưu API Authentication theo web session. API xác minh Bearer token theo incoming request.

### 18.4. API cần object-level authorization

Scope chỉ là coarse-grained permission. Trong production phải kiểm tra tenant/owner và domain rules cho từng order.

## 19. JWT audience validation

Một JWT do đúng issuer ký nhưng dành cho Billing API không được Orders API chấp nhận.

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class JwtAudienceConfig {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${app.security.required-audience}")
            String audience) {

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                        .withIssuerLocation(issuer)
                        .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Orders API audience required",
                            null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        JwtValidators.createDefaultWithIssuer(issuer),
                        audienceValidator));

        return decoder;
    }
}
~~~

### 19.1. Những gì decoder xác minh

Với trusted issuer/JWKS, decoder xác minh signature và những claims validity theo validator. Custom audience validator buộc token hướng tới Orders API.

### 19.2. ID token không phù hợp

OIDC ID token thường có `aud=reactive-portal`. API muốn access token có `aud=orders-api`; do đó không chấp nhận ID token thay access token.

### 19.3. Scope chưa đủ

Ngoài audience, security chain yêu cầu `SCOPE_orders.read`. Nếu JWT scope chỉ là `profile`, request thường bị 403 khi token authentication hợp lệ.

### 19.4. Không tin arbitrary JWKS URL

Issuer/JWKS phải đến từ cấu hình tin cậy, không phải browser-provided host.

## 20. Orders API Controller

~~~java
package com.example.orders;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    @GetMapping
    Flux<OrderView> list(@AuthenticationPrincipal Jwt jwt) {

        return Flux.just(
                new OrderView(
                        "demo-" + jwt.getSubject() + "-001",
                        "READY"),
                new OrderView(
                        "demo-" + jwt.getSubject() + "-002",
                        "PROCESSING"));
    }

    record OrderView(String id, String status) {}
}
~~~

### 20.1. Chỉ demo data

Ví dụ tạo orders giả từ validated JWT subject, không phải production domain repository. Thực tế, phải query dữ liệu theo verified tenant/user và kiểm tra owner permission.

### 20.2. Token service khác human user

Nếu API hỗ trợ client_credentials, `sub` có thể biểu diễn client/service, không nhất thiết là người dùng. Cần authorization policy phù hợp.

### 20.3. Không phản hồi raw token

JSON response chỉ chứa dữ liệu nghiệp vụ, không echo Authorization header hoặc JWT.

## 21. OrdersApiApplication

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApiApplication.class, args);
    }
}
~~~

API chạy port 8081 theo YAML.

## 22. Chạy end-to-end theo thứ tự

1. **Chuẩn bị OP:** tạo confidential client, user Alice, redirect URI và audience/scope cho Orders API.
2. **Đặt biến môi trường:** `OIDC_ISSUER_URI`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `ORDERS_API_BASE_URL`.
3. **Khởi động Orders API:** port 8081; API phải có JWKS/issuer truy cập được.
4. **Khởi động Portal:** port 8080.
5. **Mở `/oauth2/authorization/corporate`:** hoàn tất login tại OP.
6. **Mở `/me`:** kiểm tra issuer/subject của authenticated OIDC principal.
7. **Mở `/orders`:** Portal dùng access token và WebClient gọi Orders API.
8. **Kiểm tra lỗi:** thử token thiếu audience/scope bằng fake OP/test JWT.

### 22.1. Ví dụ biến môi trường

~~~powershell
$env:OIDC_ISSUER_URI = "https://id.example.test/realms/demo"
$env:OIDC_CLIENT_ID = "reactive-portal"
$env:OIDC_CLIENT_SECRET = "<test-secret>"
$env:ORDERS_API_BASE_URL = "http://localhost:8081"
~~~

Thay giá trị placeholders bằng OP local/staging thực. Không dùng credentials production để học thực hành.

### 22.2. Không nhất thiết login xong sẽ lập tức vào /orders

Sau login, Spring Security có thể chuyển đến saved request/default success URL. Sau khi session tồn tại, gọi `/orders` để kiểm tra downstream.

### 22.3. Session cookie của Portal

Browser gửi session cookie tới `localhost:8080`. Portal không chuyển cookie đó như một Bearer token cho API.

### 22.4. Khi API trả 401

Kiểm tra audience/issuer/signature/expiry và xem Portal đã gắn access token chưa; không disable validation để lấy 200.

## 23. Sequence diagram

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser
    participant Portal as Reactive Portal
    participant OP as OIDC Provider
    participant API as Orders API

    User->>Browser: Open /orders
    Browser->>Portal: GET /orders (anonymous)
    Portal-->>Browser: Redirect OP
    Browser->>OP: Authorization request
    OP->>OP: User authentication/consent
    OP-->>Browser: Redirect code + state
    Browser->>Portal: Callback with session
    Portal->>Portal: Correlate state
    Portal->>OP: Exchange code
    OP-->>Portal: ID token + access token
    Portal->>Portal: Validate ID token, store Authentication
    Portal-->>Browser: Browser session + redirect
    Browser->>Portal: GET /orders + cookie
    Portal->>Portal: Load/refresh authorized client
    Portal->>API: GET /api/orders + Bearer access token
    API->>API: Verify issuer, aud, exp, scope
    API-->>Portal: Orders JSON
    Portal-->>Browser: Orders JSON
~~~

### 23.1. Bước token exchange khác browser redirect

Browser đi tới authorization endpoint, backend gọi token endpoint. Mỗi bước có HTTP client/security boundary khác nhau.

### 23.2. Resource Server authentication độc lập

Orders API không cần `OidcUser` từ Portal. Nó tạo Authentication từ validated access token.

## 24. Reactor Context và tránh blocking

### 24.1. Không dùng `SecurityContextHolder` ThreadLocal như Servlet

Reactive Spring Security dùng `ReactiveSecurityContextHolder` và Reactor Context. Thread execution có thể đổi qua operators/schedulers.

### 24.2. Lấy Authentication reactive

~~~java
ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
~~~

Import `org.springframework.security.core.context.ReactiveSecurityContextHolder`.

### 24.3. Không dùng `block()`

Sai:

~~~java
List<OrderView> orders = ordersWebClient.get()
        .uri("/api/orders")
        .retrieve()
        .bodyToFlux(OrderView.class)
        .collectList()
        .block();
~~~

`block()` ở WebFlux request path có thể nghẽn event loop. Đúng là return `Mono<List<OrderView>>` để pipeline được subscribe/hủy/quản lý tự nhiên.

### 24.4. Không `subscribe()` thủ công rồi trả kết quả trước

Sai:

~~~java
ordersWebClient.get()
        .uri("/api/orders")
        .retrieve()
        .bodyToMono(String.class)
        .subscribe();

return Mono.just("done");
~~~

Đoạn này bỏ qua backpressure, error propagation và request lifecycle. Hãy compose reactive publisher.

### 24.5. Giới hạn concurrency

Nếu batch nhiều downstream calls, dùng bounded `flatMap(..., concurrency)` và configured connection pool; nonblocking không biến HTTP capacity thành vô hạn.

## 25. Refresh token lifecycle

Khi user login, OP có thể trả:

~~~text
Access token A1, expiresAt 11:00
Refresh token R1 (nếu OP cấp)
~~~

### 25.1. Token còn hạn

Manager thường reuse A1, không gửi refresh grant mỗi lần người dùng đọc orders.

### 25.2. Token gần hết hạn

Refresh provider có thể dùng R1 để xin A2; nếu AS rotate, nhận thêm R2 và cần save.

### 25.3. Không có refresh token

OP có thể không cấp R1 tùy policy. Nếu A1 expired và manager không thể refresh, cần reauthorization/login flow tương ứng.

### 25.4. Refresh không chứng minh MFA mới

Refresh token grant không phải interactive user authentication mới. Nếu nghiệp vụ cần step-up, phải yêu cầu OIDC authentication theo OP policy.

### 25.5. Rotation race

Nếu hai Pods cùng refresh R1, một request có thể nhận `invalid_grant` hoặc kích hoạt reuse detection. Cần single-flight, version/CAS và shared storage strategy.

### 25.6. Timeout không đồng nghĩa AS chưa rotate

Nếu refresh response mất sau khi AS đã cấp R2, retry R1 mù quáng có thể thất bại. Không áp generic retry interceptor cho mọi token POST.

## 26. 401, 403 và downstream errors

Mặc định `WebClient.retrieve()` báo lỗi cho 4xx/5xx. Một BFF nên map lỗi an toàn thay vì trả raw downstream body/headers cho browser.

| Status | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| 401 API | Missing/invalid Bearer access token | Kiểm tra signature, issuer, audience, expiry |
| 403 API | Thiếu scope hoặc quyền tenant/owner | Kiểm tra API authorization |
| 429 API | Quota/rate limit | Backoff có giới hạn theo operation |
| 503 API | Service unavailable | Fail fast/circuit breaker, retry khi an toàn |

### 26.1. Ví dụ map 401/403

Thay phần `retrieve()` trong Gateway bằng:

~~~java
.retrieve()
.onStatus(
        code -> code.value() == 401,
        response -> Mono.just(
                new ResponseStatusException(
                        HttpStatus.BAD_GATEWAY,
                        "Orders API rejected access token")))
.onStatus(
        code -> code.value() == 403,
        response -> Mono.just(
                new ResponseStatusException(
                        HttpStatus.FORBIDDEN,
                        "Orders access denied")))
.bodyToFlux(OrderView.class)
.collectList();
~~~

### 26.2. Không retry 401 vô hạn

Một token sai audience hoặc issuer sẽ tiếp tục bị từ chối dù refresh. Cần giới hạn retry/re-authorize policy.

### 26.3. Authorization failure handler của WebClient

Nếu muốn API `invalid_token` làm remove stale authorized client, phải cấu hình failure handler/manager integration tương ứng. Không mặc định mọi cách dựng OAuth2 filter tự động remove record.

### 26.4. POST cần idempotency

Nếu sau này thêm tạo order, retry sau timeout có thể tạo duplicate object. Dùng idempotency key hoặc contract phù hợp, không generic retry mọi POST.

## 27. CSRF, CORS và cookies

### 27.1. Portal dùng browser session nên cần CSRF protection

Cookie được browser gửi tự động. Các state-changing POST/PUT/DELETE phải có CSRF protection theo Portal policy. Không tắt CSRF chỉ vì user đăng nhập OIDC.

### 27.2. Bearer-only API có threat model khác

Orders API trong bài nhận Authorization header, không dùng cookie/session. Vì vậy API chain có thể disable CSRF. Nếu về sau API nhận cookie, đánh giá lại.

### 27.3. CORS không phải authentication

Browser gọi Portal cùng origin; Portal gọi Orders API server-to-server, không phụ thuộc browser CORS.

Nếu SPA gọi API trực tiếp từ origin khác, cần CORS nhưng vẫn phải xác minh Bearer token.

### 27.4. Cookie hardening

Production cần HTTPS, Secure, HttpOnly, SameSite đúng login flow, session lifetime, CSRF tokens, session fixation protection và trusted forwarded headers.

### 27.5. Multi-instance session

Nếu browser được chuyển tới Pod khác sau login callback, phải có shared WebSession/authorization request state hoặc sticky routing phù hợp. Không tắt OAuth state correlation.

## 28. Ngăn lộ access token

### 28.1. Không proxy URL tùy ý

Một endpoint như:

~~~text
GET /proxy?url=https://attacker.example
~~~

không được tự động gắn access token vào arbitrary destination.

### 28.2. Redirect handling

HTTP client cần tránh forward Authorization header sang cross-origin host ngoài allowlist. Cân nhắc disable redirects cho token-bearing requests hoặc validate destination.

### 28.3. Không trả `OAuth2AuthorizedClient` ra browser

Authorized client có thể chứa refresh token. Chỉ trả DTO dữ liệu nghiệp vụ.

### 28.4. Không log secrets

Không log raw access token, refresh token, ID token, client secret, authorization code, code verifier hoặc session cookie.

### 28.5. HTTPS production

Local HTTP `localhost` dùng cho bài học cô lập; production phải dùng HTTPS, trusted certificates và egress controls.

## 29. WebTestClient: test OIDC controller

Reactive tests dùng `WebTestClient` và `mockOidcLogin()` từ Spring Security Test.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOidcLogin;

@WebFluxTest(MeController.class)
class MeControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void readsOidcSubject() {

        client.mutateWith(
                        mockOidcLogin()
                                .idToken(token -> token
                                        .claim("sub", "alice-123")))
                .get()
                .uri("/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject")
                .isEqualTo("alice-123");
    }
}
~~~

### 29.1. Kiểm tra SecurityWebFilterChain trong test

`@WebFluxTest` là slice; nếu custom production security rules là mục tiêu test, cần nạp/import đúng security config. Dependency services của controller cần test beans/mocks phù hợp.

### 29.2. `mockOidcLogin()` không chạy callback thật

Helper dựng authenticated OIDC principal cho request. Nó không gọi OP, không xác minh JWT chữ ký, `state`, `nonce` hoặc PKCE.

### 29.3. Anonymous negative test

Gửi request không mock login; assert redirect/challenge theo entry point của test security chain.

### 29.4. Test CSRF

Với POST session-backed, thêm reactive test `csrf()` tương ứng và kiểm tra missing-token case bị deny.

## 30. WebTestClient: test API authorization

API Resource Server dùng `mockJwt()` thay vì `mockOidcLogin()`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

@WebFluxTest(OrdersController.class)
@Import(ApiSecurityConfig.class)
class OrdersApiTest {

    @Autowired
    WebTestClient client;

    @Test
    void allowsReadScope() {

        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt.subject("alice-123"))
                        .authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_orders.read")))
                .get()
                .uri("/api/orders")
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void rejectsMissingScope() {

        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt.subject("alice-123"))
                        .authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_profile")))
                .get()
                .uri("/api/orders")
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

### 30.1. `mockJwt()` không kiểm chứng signature thật

Nó mô phỏng authenticated JWT principal để test endpoint rules. Phải test `ReactiveJwtDecoder` riêng với test JWKS/JWT ký hợp lệ và invalid issuer/audience cases.

### 30.2. JWT negative matrix

| Input | Kỳ vọng |
|---|---|
| Không Bearer token | 401 |
| Signature sai | 401 |
| Issuer sai | 401 |
| Expired JWT | 401 |
| `aud=billing-api` | 401 |
| Audience đúng, thiếu `orders.read` | 403 |
| Scope đủ, resource của người khác | 403/404 theo domain |
| Audience, scope, owner đúng | 200 |

### 30.3. Test owner/tenant thực

Nếu controller dùng mock data, chưa chứng minh object-level authorization. Khi có repository thật, test principal Alice không đọc được order Bob.

## 31. Test Bearer forwarding tới fake Orders API

Để kiểm tra WebClient thực sự gửi access token, dùng fake HTTP server (WireMock/MockWebServer) thay vì chỉ mock `OrdersGateway`.

Test plan:

1. Tạo fake `OAuth2AuthorizedClient` chứa access token `test-A1`.
2. Cấu hình reactive manager test trả authorized client này.
3. Đặt `ORDERS_API_BASE_URL` trỏ fake server trên random port.
4. Gửi `GET /orders` tới Portal với authentication phù hợp.
5. Fake server ghi nhận `GET /api/orders`.
6. Assert header `Authorization: Bearer test-A1`.
7. Assert không có ID token/refresh token trong request.
8. Fake server trả JSON.
9. Assert Portal trả DTO đúng.
10. Cho fake API trả 401/403 để kiểm tra error behavior.

### 31.1. Chỉ fake token values

Không lấy token từ production logs hoặc browser session production.

### 31.2. Destination assertion quan trọng

Nếu URL sai host, test phải fail. Không chỉ assert Portal trả 200 khi WebClient bị mock hoàn toàn.

### 31.3. Không phỏng đoán refresh từ một mock principal

`mockOidcLogin()` không chứng minh manager đã refresh token hoặc lưu R2. Cần component test manager/provider/store riêng.

## 32. Integration test OIDC flow thật

Dùng fake OP với các endpoints:

~~~text
/.well-known/openid-configuration
/authorize
/token
/jwks
/userinfo (nếu flow dùng)
~~~

### 32.1. Happy path

- Bắt đầu `/oauth2/authorization/corporate`.
- Lấy `state`/`nonce` từ redirect.
- Gửi callback code+state trong cùng session.
- Fake OP trả token response hợp lệ.
- ID token được ký bằng test key/JWKS, issuer/audience/nonce khớp.
- Portal tạo Authentication và authorized client.

### 32.2. Denied consent

Callback `error=access_denied` không được tạo login thành công.

### 32.3. Sai state

Callback state không khớp pending request phải bị từ chối trước token endpoint.

### 32.4. ID token sai

Signature, issuer, audience, expiry hoặc nonce sai phải bị reject.

### 32.5. Duplicate callback

Code và state đã tiêu thụ không được xử lý như một authorization mới. AS phải enforce one-time authorization code.

### 32.6. Network failure

Token/JWKS/UserInfo timeout phải fail closed, không tạo Authentication chưa verify.

## 33. Refresh test và concurrency

### 33.1. A1 còn hạn

Manager reuse A1; fake AS token endpoint call count nên bằng zero cho trường hợp chỉ sử dụng token còn hiệu lực.

### 33.2. A1 sắp hết hạn

Fake AS trả A2/R2 sau refresh R1; assert manager result và authorized-client store đều cập nhật A2/R2.

### 33.3. Không có refresh token

Nếu OP không cấp R1 và A1 expired, manager không tự tạo authorization code mới. Cần UI/reauthorization flow theo policy.

### 33.4. `invalid_grant`

Xử lý stale token/reauthorization theo failure handler policy. Không retry grant lỗi vô hạn.

### 33.5. Concurrent refresh

Hai requests cùng dùng R1 có thể bị rotation race. Test single-flight/version/CAS nếu nhiều Pods dùng shared store.

### 33.6. Đừng refresh để khắc phục 403 scope

Scope/owner/tenant denial không tự biến mất sau refresh.

## 34. Opaque access token

Nếu AS phát **opaque access token**, Orders API không dùng JWT decoder như mục 18–19. Thay bằng opaque introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: ${OIDC_INTROSPECTION_URI}
          client-id: ${API_INTROSPECTION_CLIENT_ID}
          client-secret: ${API_INTROSPECTION_CLIENT_SECRET}
~~~

và Resource Server DSL:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
        .opaqueToken(Customizer.withDefaults()))
~~~

### 34.1. Introspection cũng cần authority mapping

Nếu AS trả scopes dưới dạng khác, cần cấu hình mapper. `active=true` không thay owner/tenant checks.

### 34.2. Access token format độc lập ID token format

OIDC ID token là JWT, nhưng OAuth access token **không bắt buộc** là JWT.

## 35. Multi-tenant domain authorization

Một user có thể là admin tenant Acme nhưng chỉ viewer tenant Globex.

~~~text
Issuer = company-op
Subject = alice-123
Acme: ORDER_ADMIN
Globex: ORDER_VIEWER
~~~

### 35.1. API scope là coarse-grained

`orders.read` chỉ là quyền ở mức API. Query/domain service vẫn cần xác minh tenant/owner.

### 35.2. Không tin tenant ID do caller tự khai

Nếu client gửi `?tenant=globex`, API phải đối chiếu verified membership/policy thay vì dùng trực tiếp làm điều kiện duy nhất.

### 35.3. Cache cần tenant-aware

Cache key chỉ theo `sub` hoặc order ID có thể làm rò dữ liệu giữa tenants; thiết kế key theo identity/tenant và authorization context.

### 35.4. Service identities

Client credentials token không tự có human user. API phải phân biệt service authorization với user-delegated access.

## 36. Deployment và vận hành

### 36.1. Session persistence

Với nhiều Portal Pods, authorization request state và WebSession phải tồn tại qua callback. Dùng shared reactive session store hoặc sticky routing theo thiết kế.

### 36.2. Provider timeouts

Token endpoint, UserInfo, JWKS/discovery có network clients và timeouts riêng. Không assume một WebClient bean điều khiển tất cả.

### 36.3. Connection pool và backpressure

Reactor Netty connection pool phải có max connections/pending acquire bounds; nonblocking không làm provider capacity vô hạn.

### 36.4. Retry grants cẩn thận

Authorization Code single-use và rotating refresh token không an toàn để retry POST mù quáng sau unknown outcome.

### 36.5. Observability

Đo login success/failure, callback latency, refresh errors, Orders API 401/403/5xx, pool saturation và tracing correlation. Không log raw tokens.

### 36.6. Secrets và egress

Client secrets ở secret store; HTTPS production và egress allowlist OP/Orders API. Không follow redirects tới arbitrary destinations kèm token.

## 37. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Portal không redirect login | Chain/matcher chưa đúng | `oauth2Login()` |
| Callback 404 | Redirect URI sai | OP/client config |
| Callback state mismatch | Session mất/khác Pod | WebSession/state repository |
| Login fail issuer | Issuer metadata không khớp | OP issuer |
| Login fail nonce | OIDC nonce mismatch | Request vs ID token |
| `/me` null OidcUser | Auth không phải OIDC Login | Principal type |
| `/orders` 401 ở Portal | No auth/authorized client | Session + manager |
| API 401 | Thiếu Bearer/sai issuer/audience/expiry | JWT decoder |
| API 403 | Thiếu scope/owner/tenant | API authorization |
| Scope đúng, audience sai | AS không cấp token cho API | Audience mapper |
| API nhận ID token | Sai token type | Authorized client usage |
| Refresh không chạy | No R1/provider | Reactive manager |
| Refresh invalid_grant | Rotation/revocation | Store/concurrency |
| `.block()` lỗi ở event loop | Blocking reactive pipeline | Return Mono/Flux |
| WebClient lộ token | Dynamic URL/redirect | Allowlist, filters |
| WebSession mất khi scale | Không shared state | Session persistence |
| CSRF 403 ở POST | Thiếu token | CSRF configuration |
| CORS error | Browser trực tiếp gọi API | BFF vs SPA |
| `mockJwt()` xanh nhưng JWT thật 401 | Không test cryptographic decoder | Test JWKS |
| `mockOidcLogin()` xanh nhưng callback fail | Mock bypasses full login | Fake OP flow |

## 38. Bài tập mở rộng

### A. Xem identity

Tạo `GET /me` trả issuer/subject, không trả raw ID token.

### B. Đăng nhập trước khi đọc orders

Đảm bảo anonymous `GET /orders` vào login flow.

### C. Bearer forwarding

Dùng fake Orders API kiểm tra header `Authorization: Bearer test-A1`.

### D. Sai audience

Token có `aud=billing-api` phải không được API chấp nhận.

### E. Thiếu scope

Token đúng audience nhưng không có `orders.read` phải bị 403.

### F. Refresh rotation

Fake AS R1 → A2/R2, assert manager/store lưu token mới.

### G. Tenant isolation

Alice thuộc Acme không được xem orders Globex.

### H. CSRF

Thêm Portal POST, test có/không CSRF token.

### I. Wrong host

Thử dynamic URL user input; Portal phải không forward token tới host lạ.

### J. Concurrent refresh

Hai requests dùng R1 đồng thời; áp single-flight/CAS và kiểm tra không mất R2.

## 39. Câu hỏi tự kiểm tra

**1. WebFlux dùng security chain nào?** `SecurityWebFilterChain`.

**2. Scope nào kích hoạt OIDC?** `openid`.

**3. Login initiation path phổ biến?** `/oauth2/authorization/{registrationId}`.

**4. OIDC callback path phổ biến?** `/login/oauth2/code/{registrationId}`.

**5. Principal OIDC sau login thường là gì?** `OidcUser` trong `OAuth2AuthenticationToken`.

**6. API access token lấy từ đâu?** `OAuth2AuthorizedClient.getAccessToken()`.

**7. Có gửi ID token làm API Bearer không?** Không theo contract thông thường.

**8. Reactive manager trả kiểu gì?** `Mono<OAuth2AuthorizedClient>`.

**9. WebClient OAuth2 filter làm gì?** Đính kèm access token Bearer theo authorized client.

**10. Vì sao cần ServerWebExchange?** Để manager/repository có request/session context.

**11. Resource Server cần kiểm tra gì?** Signature, issuer, expiry, audience, scope và domain permission.

**12. Sai audience nên làm gì?** API từ chối token.

**13. Có thể dùng opaque access token không?** Có, với introspection.

**14. Có nên `block()` trong WebFlux controller?** Không.

**15. Portal session-backed POST cần CSRF không?** Có theo threat model.

**16. `mockOidcLogin()` test callback thật không?** Không.

**17. `mockJwt()` verify JWT signature không?** Không.

**18. Multi-Pod Portal cần gì?** WebSession/state/authorized-client persistence hoặc routing phù hợp.

**19. Vì sao không forward token tới arbitrary URL?** Nguy cơ lộ token và SSRF.

**20. Refresh rotation cần lưu gì?** A2 và R2 khi AS cấp.

## Ghi nhớ

- **Reactive Portal dùng `oauth2Login()` cho OIDC authentication và `oauth2Client()` cho outbound authorized clients**. Orders API dùng `oauth2ResourceServer()` độc lập.
- **Browser gửi session cookie tới Portal; Portal gửi Bearer access token tới API**. ID token và access token không hoán đổi.
- **`ReactiveOAuth2AuthorizedClientManager` tìm/tái sử dụng/refresh authorized client theo registration và principal**, còn WebClient OAuth2 filter gắn access token.
- **Orders API phải xác minh chữ ký, issuer, expiry, audience, scope và domain authorization**; login thành công không cấp quyền mọi orders.
- **Reactor Context khác ThreadLocal Servlet**. Không `block()` hoặc `subscribe()` tùy tiện trong request path.
- **BFF vẫn phải chống CSRF và bảo vệ session**, trong khi bearer-only API có threat model riêng.
- **`mockOidcLogin()` và `mockJwt()` kiểm thử sau-authentication**, không thay fake OP/JWKS integration tests cho callback và JWT validation thật.
- **Refresh token rotation, 401/403, concurrency và token storage cần kiểm thử riêng**, không retry vô hạn.
- **Không ghi token vào logs, không trả credentials ra browser và không gắn Bearer vào arbitrary host**.
