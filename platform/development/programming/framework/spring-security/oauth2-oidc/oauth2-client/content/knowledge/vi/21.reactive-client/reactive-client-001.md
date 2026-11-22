# 21.1. ReactiveOAuth2AuthorizedClientManager và OAuth2AuthorizeRequest

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, một ứng dụng **Spring WebFlux** thường cần access token để gọi Resource Server. Thay vì tự xử lý mọi bước lấy, lưu, dùng lại và làm mới token, ứng dụng có thể sử dụng **`ReactiveOAuth2AuthorizedClientManager`**.

Một điểm đáng chú ý: dù manager là **reactive**, tham số đầu vào của nó vẫn là **`OAuth2AuthorizeRequest`** — một object đồng bộ mô tả yêu cầu. Kết quả của lời gọi manager mới là publisher reactive:

~~~java
Mono<OAuth2AuthorizedClient> result =
        reactiveAuthorizedClientManager.authorize(authorizeRequest);
~~~

Manager không đơn giản là một HTTP client gọi token endpoint. Nó điều phối **client registration**, **principal**, **authorized client đang được lưu** và **provider theo OAuth grant**. Một lời gọi `authorize(...)` có thể tạo authorized client mới, trả lại token hiện có, refresh token hoặc không có kết quả khi không thể authorize trong ngữ cảnh đó.

Sau bài học, bạn có thể:

1. Hiểu chính xác hợp đồng của `ReactiveOAuth2AuthorizedClientManager.authorize(OAuth2AuthorizeRequest)`.
2. Phân biệt `OAuth2AuthorizeRequest` với `OAuth2AuthorizationRequest` của redirect flow.
3. Xây `OAuth2AuthorizeRequest` với registration ID, principal và những thuộc tính ngữ cảnh cần thiết.
4. Chọn `DefaultReactiveOAuth2AuthorizedClientManager` cho WebFlux HTTP request và `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` cho tác vụ không gắn request.
5. Hiểu vai trò của `ReactiveOAuth2AuthorizedClientProvider`, `ReactiveClientRegistrationRepository`, `ServerOAuth2AuthorizedClientRepository` và `ReactiveOAuth2AuthorizedClientService`.
6. Cấu hình manager để xử lý `authorization_code`, `refresh_token`, `client_credentials` theo đúng môi trường.
7. Compose `Mono<OAuth2AuthorizedClient>` vào controller, service và `WebClient`, không gọi `block()` hoặc `subscribe()` tùy tiện.
8. Xử lý `Mono.empty()`, lỗi token endpoint, refresh token rotation, concurrent requests và isolation giữa các principal.
9. Phân biệt access token, ID token và principal OIDC để tránh dùng sai token khi gọi API.

## 1. Tình huống: WebFlux Portal gọi Orders API

Giả sử có một **Employee Portal** xây dựng bằng Spring Boot WebFlux. Nhân viên đăng nhập qua một OpenID Provider (OP), còn Portal cần access token để gọi **Orders API**.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Browser
    participant Portal as WebFlux Portal
    participant OP as OpenID Provider
    participant Store as Authorized Client Store
    participant Orders as Orders API
    User->>Browser: Truy cập /api/orders
    Browser->>Portal: HTTP request
    Portal-->>Browser: Redirect OIDC nếu chưa đăng nhập
    Browser->>OP: Authorization Request
    OP-->>Browser: Authorization Code
    Browser->>Portal: Callback
    Portal->>OP: Đổi code lấy token
    OP-->>Portal: ID token, access token
    Note over Portal: Tạo Authentication và OidcUser
    Portal->>Store: Lưu authorized client
    Browser->>Portal: Request tiếp theo
    Portal->>Store: Tìm authorized client
    Store-->>Portal: Access token và refresh token nếu có
    Portal->>Orders: Bearer access token dành cho Orders API
    Orders-->>Portal: Danh sách đơn hàng
    Portal-->>Browser: HTTP response
~~~

Portal có hai nhu cầu khác nhau:

- **Authentication**: biết người dùng nào đang truy cập Portal.
- **OAuth 2.0 Client authorization**: có access token phù hợp để gọi Orders API.

`ReactiveOAuth2AuthorizedClientManager` chủ yếu giải quyết phần thứ hai: quản lý trạng thái **OAuth2AuthorizedClient** và điều phối việc authorize/reauthorize.

### 1.1. Không phải mỗi lần gọi manager đều gửi request đến OP

Ví dụ:

~~~text
09:00  Alice đăng nhập, Portal nhận access token A1
09:02  Manager tìm A1 trong repository -> dùng lại A1
09:05  Manager vẫn có thể dùng lại A1
09:10  A1 gần hết hạn -> provider thử refresh bằng R1 nếu được cấp
09:11  Lưu A2/R2 hoặc A2/R1 tùy response và chính sách AS
09:12  Lần gọi sau dùng authorized client đã cập nhật
~~~

Các mốc thời gian chỉ minh họa. Điểm cốt lõi là lời gọi `authorize(...)` **không có nghĩa luôn bắt đầu OIDC Login mới**.

## 2. Năm đối tượng cốt lõi

| Đối tượng | Nhiệm vụ | Có phải reactive không? |
|---|---|---|
| `OAuth2AuthorizeRequest` | Mô tả registration, principal và context attributes của một yêu cầu authorize | Không, là object đầu vào |
| `ReactiveOAuth2AuthorizedClientManager` | Điều phối cấp quyền/dùng lại/reauthorize | Có, trả `Mono<OAuth2AuthorizedClient>` |
| `ReactiveOAuth2AuthorizedClientProvider` | Thực hiện grant hoặc reauthorization phù hợp | Có, tham gia reactive pipeline |
| `OAuth2AuthorizedClient` | Trạng thái client đã được cấp quyền: access token và có thể refresh token | Object dữ liệu, không phải publisher |
| Repository/service lưu authorized client | Lưu và truy xuất authorized client | API Reactive khi dùng stack WebFlux |

### 2.1. `ClientRegistration` không phải token của user

`ClientRegistration` mô tả một client đăng ký với Authorization Server:

~~~text
registrationId = corporate
clientId = employee-portal
authorizationGrantType = authorization_code
scopes = openid profile orders.read
provider = company-oidc
~~~

Đăng ký client có thể tồn tại trước khi Alice đăng nhập. Nó **không** chứa access token của Alice.

### 2.2. `OAuth2AuthorizedClient` là kết quả đã cấp quyền

Một authorized client có cấu trúc khái niệm:

~~~text
OAuth2AuthorizedClient
├── clientRegistration = corporate
├── principalName = alice
├── accessToken = A1
│   ├── issuedAt = ...
│   └── expiresAt = ...
└── refreshToken = R1 (nếu được AS cấp)
~~~

Token có thể được dùng lại hoặc được cập nhật, nhưng phải gắn đúng principal/registration và Resource Server.

### 2.3. `OAuth2AuthorizeRequest` chỉ mô tả yêu cầu

Ví dụ:

~~~java
OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest
                .withClientRegistrationId("corporate")
                .principal(authentication)
                .build();
~~~

Đoạn code này **chưa thực hiện authorization** và chưa tạo token. Nó chỉ xây một yêu cầu để chuyển vào manager.

### 2.4. `ReactiveOAuth2AuthorizedClientManager` trả publisher

~~~java
Mono<OAuth2AuthorizedClient> authorizedClientMono =
        manager.authorize(request);
~~~

Khi publisher được subscribe trong ngữ cảnh phù hợp, manager sẽ tìm authorized client, phối hợp provider và trả kết quả hoặc lỗi. Không cố lấy token bằng cách ép `Mono` thành `OAuth2AuthorizedClient` đồng bộ.

### 2.5. Provider quyết định grant nào có thể xử lý

Các provider điển hình hỗ trợ:

- `authorization_code`.
- `refresh_token`.
- `client_credentials`.

Việc provider tồn tại không có nghĩa grant được phép cho mọi registration. `ClientRegistration.getAuthorizationGrantType()` và authorization context phải phù hợp với provider.

## 3. Hợp đồng của `ReactiveOAuth2AuthorizedClientManager`

Interface chính:

~~~java
package org.springframework.security.oauth2.client;

public interface ReactiveOAuth2AuthorizedClientManager {
    Mono<OAuth2AuthorizedClient> authorize(
            OAuth2AuthorizeRequest authorizeRequest);
}
~~~

Đây là chữ ký rút gọn để giải thích API.

### 3.1. Đầu vào: một `OAuth2AuthorizeRequest`

Request cung cấp ít nhất:

- Client registration hoặc registration ID cần authorize.
- Principal đại diện cho user/service.
- Context attributes cần thiết để manager/provider làm việc.

Ví dụ `ServerWebExchange` có thể được truyền qua attributes trong WebFlux request.

### 3.2. Đầu ra: `Mono<OAuth2AuthorizedClient>`

Có ba loại kết quả cần hiểu:

| Kết quả | Ý nghĩa |
|---|---|
| `Mono` phát ra authorized client | Có trạng thái authorized client mà ứng dụng có thể sử dụng |
| `Mono.empty()` | Không có authorized client được tạo/trả về trong ngữ cảnh này |
| `Mono.error(...)` | Authorization/reauthorization gặp lỗi |

**Không nhầm empty với error.** `Mono.empty()` không chứa object để gọi `getAccessToken()`; còn `Mono.error(...)` cần được xử lý theo policy của ứng dụng.

### 3.3. Manager có thể trả client đang lưu

Một authorized client đã tồn tại có thể được trả về nguyên trạng nếu token còn được dùng và provider không cần hoặc không thể reauthorize.

Vì vậy:

~~~text
manager.authorize(request)
  -> authorized client hiện có
  -> provider không tạo authorization mới
  -> trả authorized client đã lưu
~~~

Lời gọi `authorize()` không tự động chứng minh đã có HTTP token request đến Authorization Server.

### 3.4. Khi không có authorized client

Manager sẽ xem provider chain có thể thực hiện grant phù hợp không. Ví dụ:

- `client_credentials` có thể xin token ở backend.
- `refresh_token` không có tác dụng nếu chưa từng có refresh token.
- `authorization_code` cần flow tương tác phù hợp, không thể chỉ bằng một lời gọi manager trong background job mà tự mở browser và hoàn thành callback.

## 4. Phân biệt hai tên gần giống nhau

| Tên | Vai trò |
|---|---|
| `OAuth2AuthorizeRequest` | Request nội bộ đưa cho authorized client manager |
| `OAuth2AuthorizationRequest` | Authorization Request của giao thức, thường dùng khi redirect browser tới authorization endpoint |
| `OAuth2AuthorizedClient` | Kết quả client đã được cấp token |
| `OAuth2AccessTokenResponse` | Phản hồi token endpoint sau token request |
| `OAuth2AuthorizationContext` | Context cho provider khi đánh giá authorize/reauthorize |

### 4.1. `OAuth2AuthorizationRequest` trong Authorization Code flow

Một authorization request tới OP có thể chứa:

~~~text
response_type = code
client_id = employee-portal
redirect_uri = https://portal.example.com/login/oauth2/code/corporate
scope = openid profile orders.read
state = random-correlated-value
code_challenge = ... (nếu dùng PKCE)
nonce = ... (nếu dùng OIDC)
~~~

Nó liên quan đến browser redirect, state correlation, PKCE/nonce và callback.

### 4.2. `OAuth2AuthorizeRequest` trong application code

Một manager request có thể gồm:

~~~text
clientRegistrationId = corporate
principal = Authentication của Alice
attributes = { ServerWebExchange: request hiện tại }
~~~

Nó giúp Spring Security xác định client/principal và context để tìm hoặc cấp authorized client.

**Đừng đưa hai đối tượng này vào chung một repository.** Authorization Request đang chờ callback và authorized client chứa token là hai loại trạng thái khác nhau.

## 5. Luồng xử lý của reactive manager

~~~mermaid
flowchart TD
    A["App tạo OAuth2AuthorizeRequest"] --> B["ReactiveOAuth2AuthorizedClientManager.authorize"]
    B --> C["Tìm ClientRegistration"]
    C --> D["Tìm OAuth2AuthorizedClient hiện có"]
    D --> E["Tạo OAuth2AuthorizationContext"]
    E --> F["ReactiveOAuth2AuthorizedClientProvider chain"]
    F --> G{"Có thể tạo/đổi authorized client?"}
    G -->|Có| H["Thực hiện grant hoặc refresh"]
    H --> I["Lưu authorized client qua success handler"]
    I --> J["Mono<OAuth2AuthorizedClient> mới/cập nhật"]
    G -->|Không| K{"Đã có client đang lưu?"}
    K -->|Có| L["Mono phát authorized client hiện có"]
    K -->|Không| M["Mono.empty hoặc kết quả không đủ điều kiện"]
    H -->|Lỗi| N["Mono.error và failure handling"]
~~~

Sơ đồ là mô hình khái niệm, không phải khẳng định mọi provider luôn thực hiện một token request.

Một authorized client tồn tại không bảo đảm token sẽ được mọi Resource Server chấp nhận: API vẫn cần kiểm tra issuer, audience, scope và quyền nghiệp vụ.

## 6. Hai implementation manager cần chọn đúng

Spring Security Reactive cung cấp hai lựa chọn quan trọng:

1. **`DefaultReactiveOAuth2AuthorizedClientManager`**: cho xử lý trong ngữ cảnh **WebFlux HTTP request**.
2. **`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`**: cho xử lý **ngoài `ServerWebExchange`**, ví dụ scheduled job hoặc backend service.

### 6.1. So sánh nhanh

| Đặc điểm | `DefaultReactiveOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
|---|---|---|
| Ngữ cảnh chính | WebFlux HTTP request | Background/non-web |
| Cấu hình registration | `ReactiveClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| Kho authorized client | `ServerOAuth2AuthorizedClientRepository` | `ReactiveOAuth2AuthorizedClientService` |
| Có thể cần ServerWebExchange | Có, vì repository theo web request | Không |
| Phù hợp UI OIDC Login | Có, khi cấu hình đúng login/client | Không tự xử lý browser login |
| Phù hợp client credentials job | Có thể dùng nếu thực hiện trong HTTP request | Phù hợp hơn |
| Đầu vào manager | `OAuth2AuthorizeRequest` | `OAuth2AuthorizeRequest` |
| Kết quả | `Mono<OAuth2AuthorizedClient>` | `Mono<OAuth2AuthorizedClient>` |

Hai implementation cùng interface nhưng có contract về **ngữ cảnh và nơi lưu** khác nhau.

### 6.2. Không nhầm với manager của Servlet

Trong Servlet stack có:

~~~java
org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager
~~~

Đây là manager **đồng bộ**, sử dụng `OAuth2AuthorizedClientRepository` với `HttpServletRequest`/`HttpServletResponse`.

WebFlux sử dụng manager **Reactive**, `ServerWebExchange` và repository/service reactive tương ứng. Không lấy một Servlet manager rồi bọc trong `Mono.fromCallable(...)` để coi đó là một giải pháp reactive đúng.

## 7. Cấu hình dự án Spring Boot WebFlux

### 7.1. Maven dependencies

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Đây là ví dụ Reactive stack. Nếu một dự án đưa cả Spring MVC và WebFlux starters vào classpath, cần xác định rõ Spring Boot đang chạy ở web application type nào; không mặc định mọi controller sẽ là WebFlux chỉ vì có dependency WebFlux.

### 7.2. Đăng ký OIDC client

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
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
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

Ở đây:

- `corporate` là registration ID nội bộ.
- `client-id`/`client-secret` phải khớp đăng ký tại OP.
- `authorization_code` là grant của login tương tác.
- `openid` yêu cầu OpenID Connect.
- `orders.read` chỉ là scope API minh họa, AS phải hỗ trợ và cấp đúng.
- `issuer-uri` giúp xác định OP đáng tin cậy.

Secret cần được lấy từ môi trường hoặc secret manager, không commit giá trị thật vào repository.

### 7.3. WebFlux SecurityWebFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/", "/health", "/error").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

`oauth2Login()` hỗ trợ OIDC/OAuth2 browser login, còn `oauth2Client()` hỗ trợ client authorization và việc dùng token cho request ra ngoài.

Trong ứng dụng thật, chỉ cho phép public endpoints phù hợp và giữ CSRF protection với các request dựa trên browser cookie/session khi cần.

## 8. Cấu hình `DefaultReactiveOAuth2AuthorizedClientManager`

Lớp:

~~~java
org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager
~~~

Nó sử dụng:

- `ReactiveClientRegistrationRepository` để tìm registration.
- `ServerOAuth2AuthorizedClientRepository` để lưu/tra cứu authorized client trong ngữ cảnh WebFlux.
- `ReactiveOAuth2AuthorizedClientProvider` để xử lý các grant.

### 8.1. Một manager web với provider chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
public class WebAuthorizedClientManagerConfig {

    @Bean("webAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager webAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .clientCredentials()
                        .build();

        DefaultReactiveOAuth2AuthorizedClientManager manager =
                new DefaultReactiveOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Giải thích:

1. Manager biết các client registrations.
2. Authorized client repository quản lý trạng thái trong request/WebSession hoặc service theo implementation.
3. Provider chain cho phép xử lý các grant phù hợp.
4. Khi authorized client cập nhật, manager có thể dùng success handler để lưu.
5. Không có provider nào “tự chuyển” một registration `authorization_code` thành `client_credentials` nếu AS không cho phép.

### 8.2. Không khai báo bean thừa nếu auto-configuration đã đáp ứng

Spring Boot/Spring Security có thể cung cấp các bean mặc định tùy classpath, version và cấu hình. Bạn không nhất thiết phải viết manager custom cho mọi dự án.

Chỉ tạo manager riêng khi cần thay đổi provider chain, token client, success/failure handler hoặc vị trí lưu authorized client. Nếu tự khai báo hai manager cùng interface, cần dùng `@Qualifier` để chọn đúng bean.

## 9. Xây `OAuth2AuthorizeRequest` trong WebFlux HTTP request

Một WebFlux controller có thể truy cập `ServerWebExchange` để lấy principal đã xác thực và truyền exchange làm context attribute.

### 9.1. Ví dụ trực tiếp từ controller

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class AuthorizedClientStatusController {

    private final ReactiveOAuth2AuthorizedClientManager manager;

    public AuthorizedClientStatusController(
            @Qualifier("webAuthorizedClientManager")
            ReactiveOAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @GetMapping("/api/client-status")
    Mono<ClientStatus> clientStatus(ServerWebExchange exchange) {
        return exchange.getPrincipal()
                .cast(Authentication.class)
                .flatMap(authentication -> {
                    OAuth2AuthorizeRequest request =
                            OAuth2AuthorizeRequest
                                    .withClientRegistrationId("corporate")
                                    .principal(authentication)
                                    .attribute(
                                            ServerWebExchange.class.getName(),
                                            exchange)
                                    .build();

                    return manager.authorize(request);
                })
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.UNAUTHORIZED,
                                "Authorization required")))
                .map(client -> new ClientStatus(
                        client.getClientRegistration()
                                .getRegistrationId(),
                        client.getAccessToken() != null));
    }

    record ClientStatus(
            String registrationId,
            boolean accessTokenPresent) {}
}
~~~

Trong ví dụ, endpoint được bảo vệ bởi `SecurityWebFilterChain` và giả định principal do Spring Security cung cấp là `Authentication`. Nếu app hỗ trợ nhiều kiểu principal khác, cần xử lý kiểu phù hợp.

### 9.2. Vì sao cần thuộc tính `ServerWebExchange`?

`DefaultReactiveOAuth2AuthorizedClientManager` dùng repository theo WebFlux request. `OAuth2AuthorizeRequest` có thể chuyển `ServerWebExchange` thông qua attributes để manager có ngữ cảnh load/save authorized client.

~~~java
.attribute(ServerWebExchange.class.getName(), exchange)
~~~

Đây là **context attribute bên trong authorize request**, không phải claim OAuth, scope hoặc parameter gửi lên token endpoint.

Nếu manager không có WebFlux request context cần thiết, nó có thể không thao tác repository như dự kiến. Hãy dùng đúng manager cho đúng môi trường.

### 9.3. Khi nào nên dùng `principal(Authentication)`?

`OAuth2AuthorizeRequest.Builder` cho phép gắn principal dạng `Authentication`. Với web request, nên lấy nó từ Spring Security/`ServerWebExchange` đã được xác thực.

Không lấy principal name từ query parameter rồi tạo request thay mặt một user khác:

~~~text
GET /api/orders?principalName=admin
~~~

Một input như thế không được xem là bằng chứng user có quyền dùng authorized client của admin.

### 9.4. Nếu manager trả `Mono.empty()`?

`switchIfEmpty(...)` cho phép chuyển kết quả rỗng thành phản hồi ứng dụng có kiểm soát.

Tùy nghiệp vụ, có thể:

- Trả 401 nếu thiếu authorization cần thiết.
- Bắt đầu một login/consent flow có chủ đích.
- Trả lỗi tích hợp nếu registration/provider không được cấu hình đúng.

Không biến kết quả rỗng thành access token giả.

## 10. Vì sao không gọi `block()` hoặc `subscribe()` thủ công?

Một cách sai trong WebFlux request handler:

~~~java
OAuth2AuthorizedClient client =
        manager.authorize(request).block();
~~~

`block()` đợi kết quả đồng bộ, có thể chặn event loop và làm mất ngữ cảnh reactive như thiết kế. Không dùng trong request path non-blocking để “lấy object cho dễ”.

Mẫu khác dễ gây lỗi:

~~~java
manager.authorize(request)
        .subscribe(client -> callApi(client));
~~~

Tự tạo subscription khiến:

- HTTP response không còn được điều phối theo publisher gốc.
- Exception có thể thoát khỏi luồng xử lý request.
- Context propagation có thể không như mong đợi.
- Gọi API là side effect khó kiểm soát.
- Test trở nên khó xác định thời điểm hoàn tất.

**Hãy trả lại `Mono`/`Flux` hoặc dùng `flatMap` để compose**.

### 10.1. Compose manager với WebClient

~~~java
Mono<String> orders = manager.authorize(request)
        .switchIfEmpty(Mono.error(
                new IllegalStateException("No authorized client")))
        .flatMap(client ->
                ordersWebClient.get()
                        .uri("/api/orders")
                        .headers(headers -> headers.setBearerAuth(
                                client.getAccessToken().getTokenValue()))
                        .retrieve()
                        .bodyToMono(String.class));
~~~

Trong đó `ordersWebClient` là một `WebClient` đã được cấu hình chỉ gọi Orders API đáng tin cậy. Ví dụ thể hiện cách combine publisher, không phải quy trình refresh và kiểm soát URL production hoàn chỉnh.

### 10.2. Không lạm dụng `Mono.just(...)`

`Mono.just(client)` chỉ phù hợp khi đã có object client đồng bộ, không thay thế `manager.authorize(...)`.

Không viết:

~~~java
return Mono.just(manager.authorize(request));
~~~

vì kết quả trở thành `Mono<Mono<OAuth2AuthorizedClient>>`, không phải một authorized client đã được resolve.

## 11. `OAuth2AuthorizeRequest` có thể chứa những gì?

Một builder request thông dụng:

~~~java
OAuth2AuthorizeRequest authorizeRequest =
        OAuth2AuthorizeRequest
                .withClientRegistrationId("corporate")
                .principal(authentication)
                .attribute(
                        ServerWebExchange.class.getName(),
                        exchange)
                .build();
~~~

### 11.1. Registration ID

`withClientRegistrationId("corporate")` chọn một client registration đã cấu hình.

Nếu một ứng dụng có nhiều registrations:

~~~text
corporate        -> OIDC Login nhân viên
reporting-service -> client_credentials cho job báo cáo
billing          -> client riêng cho Billing API
~~~

không được mặc định mọi registration có cùng scope/audience.

### 11.2. Principal

`principal(authentication)` cung cấp Authentication liên quan tới request. Với tác vụ nền, một request có thể dùng principal name kỹ thuật:

~~~java
OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest
                .withClientRegistrationId("reporting-service")
                .principal("reporting-job")
                .build();
~~~

`reporting-job` là định danh kỹ thuật dùng để lưu authorized client; **không có nghĩa một End-User tên reporting-job đã đăng nhập OIDC**.

### 11.3. Attributes

`attribute(...)` cho phép chuyển những giá trị ngữ cảnh mà manager/provider cần.

Không coi attributes là nơi nhận dữ liệu OAuth chưa kiểm chứng từ người dùng. Chúng là input có thể ảnh hưởng authorization, vì vậy cần được tạo từ các thành phần tin cậy của ứng dụng.

### 11.4. Có thể dùng authorized client hiện có

Builder của `OAuth2AuthorizeRequest` còn hỗ trợ khởi tạo từ một `OAuth2AuthorizedClient` đã có khi use case phù hợp. Khi đó phải bảo đảm client thuộc đúng principal/registration, không dùng object do browser tự truyền.

Ví dụ khái niệm:

~~~java
OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest
                .withAuthorizedClient(existingClient)
                .principal(authentication)
                .build();
~~~

Không chuyển authorized client của Alice cho Authentication của Bob chỉ vì cùng registration ID.

## 12. Provider chain: Authorization Code, Refresh Token, Client Credentials

### 12.1. Xây reactive provider chain

~~~java
ReactiveOAuth2AuthorizedClientProvider provider =
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();
~~~

Các provider phản ứng theo điều kiện cụ thể. Có provider trong chain **không đồng nghĩa grant sẽ luôn được thực hiện**.

### 12.2. Authorization Code

Đối với WebFlux OIDC Login:

1. Browser được redirect tới OP.
2. OP xác thực/consent theo policy.
3. Browser quay về callback với authorization code.
4. Spring Security hoàn tất token exchange, kiểm tra ID token và lưu authorized client.

`authorizationCode()` trong provider chain không tự biến mọi lời gọi manager thành một browser redirect/callback hoàn chỉnh. Luồng tương tác cần WebFlux OAuth2 Login filters và authorization request repository.

### 12.3. Refresh Token

Nếu authorized client có refresh token và access token cần refresh, `refreshToken()` có thể gửi refresh-token grant và trả authorized client cập nhật.

Nếu response refresh thành công **không cấp refresh token mới**, provider thông thường giữ refresh token cũ; nếu AS cấp token mới thì cập nhật theo rotation.

Một access token mới **không tự chứng minh người dùng vừa xác thực lại tại OP**.

### 12.4. Client Credentials

Đối với background service, `clientCredentials()` có thể xin access token lần đầu hoặc xin token mới khi token trước không còn dùng được.

Nó đại diện cho **client/service**, không phải End-User OIDC Login.

### 12.5. Không provider nào phù hợp

Nếu registration dùng `authorization_code` nhưng chain chỉ có `clientCredentials()`, manager không thể tự lấy token cho registration đó.

Nếu có `refreshToken()` nhưng authorized client chưa từng có refresh token, provider refresh cũng không tạo token mới.

**Grant, registration và provider chain phải tương thích.**

## 13. Manager dành cho background job không có WebFlux request

Lớp:

~~~java
org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
~~~

Manager này dùng:

- `ReactiveClientRegistrationRepository`.
- `ReactiveOAuth2AuthorizedClientService`.

Nó phù hợp với scheduled task, message consumer hoặc service không có `ServerWebExchange`.

### 13.1. Registration dùng client credentials

Ví dụ thêm vào `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-service:
            provider: company-auth
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company-auth:
            token-uri: https://id.example.com/oauth2/token
~~~

`reporting-service` không phải OIDC Login, không cần `openid` hoặc redirect URI dành cho browser.

### 13.2. Cấu hình manager cho service

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
public class BackgroundAuthorizedClientConfig {

    @Bean("backgroundAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager backgroundManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Không cần Servlet HttpSession hay ServerWebExchange. Authorized client được quản lý theo registration/principal trong service.

### 13.3. Dùng manager trong reactive service

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReportingTokenService {

    private final ReactiveOAuth2AuthorizedClientManager manager;

    public ReportingTokenService(
            @Qualifier("backgroundAuthorizedClientManager")
            ReactiveOAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public Mono<String> accessToken() {
        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                        .withClientRegistrationId("reporting-service")
                        .principal("reporting-job")
                        .build();

        return manager.authorize(request)
                .switchIfEmpty(Mono.error(
                        new IllegalStateException(
                                "No token for reporting-service")))
                .map(client -> client.getAccessToken().getTokenValue());
    }
}
~~~

Mẫu này trả `Mono<String>` để service khác compose, không gọi `block()` hay `subscribe()`.

**Trong production, tránh đưa access token ra frontend hoặc log.** Thường tốt hơn khi dùng manager trong HTTP client chuyên dụng gọi đúng Reporting API.

### 13.4. Principal kỹ thuật và chia sẻ token

Nhiều job có thể dùng cùng principal name `reporting-job` và registration `reporting-service`, từ đó chia sẻ authorized client trong backing store nếu được thiết kế như vậy.

Cần quyết định:

- Mỗi job có cần scope/audience riêng không?
- Có cần bảo vệ concurrent token requests không?
- Lưu token qua nhiều instances ra sao?
- Khi thay client secret hoặc thu hồi token thì cleanup thế nào?

Không dùng principal name của một user bất kỳ làm service principal.

## 14. WebFlux repository và authorized client service khác nhau

### 14.1. `ServerOAuth2AuthorizedClientRepository`

Repository này làm việc trong ngữ cảnh WebFlux server, có thể liên hệ với request, principal và `ServerWebExchange`. Implementation cụ thể quyết định lưu theo WebSession hay service/identity.

### 14.2. `ReactiveOAuth2AuthorizedClientService`

Service có thể lưu và đọc authorized client theo registration ID và principal name, với API reactive. Nó không yêu cầu `ServerWebExchange` để hoạt động.

### 14.3. Các lựa chọn lưu trữ

| Yêu cầu | Hướng lựa chọn |
|---|---|
| UI OIDC Login dùng WebSession | WebFlux authorized client repository phù hợp |
| Authenticated user, lưu theo principal | Repository kết hợp với reactive service nếu phù hợp |
| Scheduled job không có HTTP request | Reactive authorized client service + service manager |
| Nhiều instance cần dùng chung token | Backing store chia sẻ với bảo vệ concurrency |
| Token chỉ cần theo một phiên browser | Session-backed repository nếu policy cho phép |
| Login/logout/đổi tài khoản | Cleanup và ràng buộc principal nhất quán |

**Không nhầm `WebSession` của WebFlux với `HttpSession` của Servlet.** Reactive stack dùng các abstraction riêng, không cần Servlet request.

### 14.4. Session có Authentication không có nghĩa luôn có authorized client

Một người có thể đã đăng nhập tại Portal nhưng:

- Chưa được cấp token cho API cần gọi.
- Access token đã hết hạn.
- Refresh token không được cấp.
- Authorized client nằm trong service store khác.
- Resource Server không chấp nhận audience/scope.

Authentication và authorized client là hai trạng thái khác nhau.

## 15. Dùng `WebClient` với reactive manager

`WebClient` là HTTP client non-blocking của Spring WebFlux. Nó có thể sử dụng access token qua hai phương án:

1. Compose `manager.authorize(request)` rồi tự set Bearer header.
2. Sử dụng `ServerOAuth2AuthorizedClientExchangeFilterFunction` để tích hợp OAuth2 client.

### 15.1. Kết hợp trực tiếp `Mono`

~~~java
public Mono<String> orders(
        OAuth2AuthorizeRequest authorizeRequest) {

    return manager.authorize(authorizeRequest)
            .switchIfEmpty(Mono.error(
                    new IllegalStateException(
                            "Orders authorization required")))
            .flatMap(client -> ordersWebClient.get()
                    .uri("/api/orders")
                    .headers(headers -> headers.setBearerAuth(
                            client.getAccessToken().getTokenValue()))
                    .retrieve()
                    .bodyToMono(String.class));
}
~~~

Ví dụ này giả định `ordersWebClient` có base URL tin cậy và không gửi token tới URL tùy ý.

Việc compose bằng `flatMap` giữ luồng bất đồng bộ và cho phép upstream xử lý kết quả/lỗi.

### 15.2. Tích hợp OAuth2 với `ServerOAuth2AuthorizedClientExchangeFilterFunction`

Lớp:

~~~java
org.springframework.security.oauth2.client.web.reactive.function.client
        .ServerOAuth2AuthorizedClientExchangeFilterFunction
~~~

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OrdersWebClientConfig {

    @Bean
    WebClient ordersWebClient(
            ReactiveOAuth2AuthorizedClientManager manager) {

        var oauth2 =
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                        manager);

        return WebClient.builder()
                .baseUrl("https://orders-api.example.com")
                .filter(oauth2)
                .build();
    }
}
~~~

Nếu có nhiều manager bean, thêm `@Qualifier` để WebClient dùng đúng manager web hoặc service.

Một request có thể chỉ định registration:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> result = ordersWebClient.get()
        .uri("/api/orders")
        .attributes(clientRegistrationId("corporate"))
        .retrieve()
        .bodyToMono(String.class);
~~~

Khi dùng manager phụ thuộc WebFlux request, cần bảo đảm `ServerWebExchange`/principal context được cung cấp qua integration tương ứng. Nếu gọi ngoài request, sử dụng manager dành cho service.

### 15.3. Không tự động gửi token tới mọi URL

Nếu ứng dụng dùng OAuth2 filter gắn token theo registration, tránh dùng WebClient đó như một generic HTTP client cho URL được truyền tùy ý.

Chỉ gửi token đến host được phép, đúng resource/audience/scope. Một request đi qua redirect hoặc full absolute URI có thể tạo nguy cơ rò rỉ credential nếu không kiểm soát URL và HTTP client.

### 15.4. Có thể dùng authorized client trực tiếp

Khi caller đã có `OAuth2AuthorizedClient` hợp lệ, `ServerOAuth2AuthorizedClientExchangeFilterFunction` cũng có khả năng sử dụng authorized client qua request attribute tương ứng. Dù vậy, phải bảo đảm authorized client thuộc đúng user/client registration.

Không dùng authorized client của người dùng A cho user B chỉ vì cả hai gọi cùng API.

## 16. Reactor Context và Authentication của WebFlux

### 16.1. Reactive SecurityContext

Với Spring WebFlux, Authentication có thể được truy cập qua:

~~~java
ReactiveSecurityContextHolder.getContext()
~~~

Kết quả là:

~~~java
Mono<SecurityContext>
~~~

Không được mặc định `SecurityContextHolder.getContext()` (thường gắn ThreadLocal ở Servlet) sẽ hoạt động chính xác trong mọi reactive operator.

### 16.2. Tạo authorize request từ reactive context

~~~java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import reactor.core.publisher.Mono;

Mono<OAuth2AuthorizedClient> currentUserClient() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(authentication ->
                    manager.authorize(
                            OAuth2AuthorizeRequest
                                    .withClientRegistrationId("corporate")
                                    .principal(authentication)
                                    .build()));
}
~~~

Ví dụ này minh họa cách lấy principal mà không phụ thuộc ThreadLocal.

**Quan trọng:** nếu đang dùng `DefaultReactiveOAuth2AuthorizedClientManager` với repository cần `ServerWebExchange`, bạn vẫn phải bảo đảm exchange được cung cấp trong ngữ cảnh request phù hợp. Chỉ lấy Authentication chưa đảm bảo đủ context cho mọi repository.

### 16.3. Vì sao context quan trọng với manager?

Reactive pipeline có thể chuyển scheduler. Reactor Context đi theo subscriber/publisher theo cơ chế Reactor, không phải một biến global dùng chung cho mọi request.

Khi manager và WebClient được compose trong cùng pipeline, ngữ cảnh có thể được giữ theo quy tắc reactive. Nếu tự tạo subscription mới hoặc chuyển qua callback ngoài Reactor mà không truyền ngữ cảnh, các thành phần có thể không thấy principal/exchange như kỳ vọng.

### 16.4. Truyền identity tường minh

Với domain service, có thể tốt hơn khi lấy danh tính đã xác minh ở biên request rồi truyền DTO bất biến (ví dụ issuer + subject hoặc user ID nội bộ) vào service.

Tuy nhiên, việc truyền một DTO không thay thế `Authentication` nếu manager/repository cần đúng principal để lấy token. Cần xác định rõ ràng trách nhiệm: **identity cho nghiệp vụ** và **principal cho authorized client manager**.

## 17. `oauth2Login()` khác `oauth2Client()`

Trong WebFlux:

- `oauth2Login()` xử lý authentication của browser bằng OAuth 2.0 Login/OIDC.
- `oauth2Client()` cung cấp hỗ trợ OAuth2 client cho việc ứng dụng sử dụng authorized client/access token.

### 17.1. Login không tự cấp token cho mọi Resource Server

Một user có thể đã login vào Portal nhưng cần một access token riêng cho Orders API, với scope/audience do AS và API quy định.

Không dùng ID token làm access token của API chỉ vì OIDC Login đã thành công.

### 17.2. Login thành công không đảm bảo refresh token tồn tại

AS có thể hoặc không cấp refresh token theo policy, scope/consent và loại client. Khi access token hết hạn mà không có refresh token, manager không thể tự tạo refresh token.

Có thể phải thực hiện authorization mới theo luồng tương tác nếu ứng dụng cho phép.

### 17.3. Background client credentials không phải OIDC Login

Một scheduled job dùng `client_credentials` thường không có `OidcUser`, ID token hay WebSession. Token đại diện cho client/service.

Không tự gắn principal của người dùng ngẫu nhiên vào service authorization request.

## 18. Manager và provider quyết định khi nào refresh

### 18.1. Khi access token còn hạn

Provider chain có thể không thực hiện reauthorization, manager trả authorized client đã lưu. Không nhất thiết có token endpoint request.

### 18.2. Khi token hết hạn hoặc sắp hết hạn

Provider refresh có thể tính `expiresAt` và clock skew, sau đó dùng refresh token nếu có.

~~~text
A1 gần hết hạn
R1 còn hợp lệ
  -> refresh_token grant
  -> A2 và có thể R2
  -> lưu updated authorized client
~~~

### 18.3. Khi response không cấp refresh token mới

Nếu AS trả A2 nhưng không có R2, Spring Security refresh provider thông thường giữ R1 đã có khi tạo authorized client cập nhật.

Nếu AS cấp R2, phải thay R1 bằng R2 theo token rotation policy.

### 18.4. Khi không thể refresh

Nếu R1 hết hạn/bị revoke hoặc AS trả `invalid_grant`, application cần xử lý failure. Không retry vô hạn cùng R1 và không lấy ID token thay refresh token.

### 18.5. Token mới không đồng nghĩa reauthentication OIDC

Một access token được refresh không chứng minh End-User vừa thực hiện MFA hoặc nhập lại mật khẩu.

Nếu nghiệp vụ cần authentication freshness/step-up, phải dùng OIDC Authentication Request phù hợp (ví dụ `max_age`, `prompt=login`, `acr_values`) và kiểm tra kết quả theo policy.

## 19. Kết quả empty, error và HTTP API failure

### 19.1. `Mono.empty()`

Manager không có authorized client và provider chain không thể authorize trong ngữ cảnh hiện tại.

Ứng dụng có thể dùng:

~~~java
return manager.authorize(request)
        .switchIfEmpty(Mono.error(
                new IllegalStateException(
                        "Client authorization unavailable")));
~~~

Trong WebFlux controller, có thể chuyển thành `ResponseStatusException` với status hợp lý theo contract API.

### 19.2. `Mono.error(...)`

Token endpoint có thể từ chối authorization, ví dụ:

- `invalid_client`: client authentication sai.
- `invalid_grant`: refresh token hết hạn, bị revoke hoặc không hợp lệ.
- Network timeout.
- Provider/registration cấu hình sai.
- Failure handler hoặc repository gặp lỗi.

Không đồng nhất lỗi cấu hình AS với “user chưa đăng nhập”.

### 19.3. API trả 401

Sau khi manager đã trả access token, Resource Server có thể trả 401 nếu token sai audience/issuer, hết hạn, bị revoke hoặc không được chấp nhận.

Manager không tự biết mọi lỗi API nếu WebClient không được tích hợp failure handling phù hợp. Cần xem HTTP response và chính sách authorized client management.

### 19.4. API trả 403

403 thường liên quan authorization/scope/ownership. Refresh token không mặc định làm token có thêm quyền.

Không xử lý mọi 401/403 bằng cách xóa authorized client hoặc refresh vô điều kiện.

### 19.5. Tránh retry request có side effect

Nếu một POST thanh toán thất bại, việc làm mới token và retry phải cân nhắc idempotency. Không được lặp POST vô hạn sau timeout hoặc lỗi có kết quả không chắc chắn.

## 20. Authorization success/failure handlers

Manager có thể sử dụng authorization success handler để lưu authorized client mới/cập nhật vào repository/service.

### 20.1. Sau refresh thành công

Nếu AS trả A2/R2, handler phải đảm bảo trạng thái cập nhật được lưu đúng registration/principal. Nếu request tiếp theo đọc ở kho khác, nó có thể vẫn thấy A1/R1.

### 20.2. Khi `invalid_grant`

Một số manager/handler mặc định của Spring Security có khả năng loại bỏ authorized client khi lỗi token refresh cụ thể khiến token cũ không còn dùng được. Behavior chi tiết phụ thuộc implementation và cấu hình.

Không tự mặc định mọi failure sẽ xóa token; cũng không giữ token `invalid_grant` rồi retry vô hạn.

### 20.3. Khi tùy biến handler

Nếu viết custom success/failure handler:

- Chọn đúng kho lưu.
- Duy trì principal isolation.
- Không ghi token thô trong log.
- Không xóa token của user khác.
- Không coi network timeout là chắc chắn refresh token đã bị revoke.
- Xử lý cập nhật đồng thời nếu nhiều request cùng refresh.

## 21. Đổi tài khoản và rủi ro token của principal khác

Giả sử Alice login vào Portal, sau đó Bob đăng nhập trong cùng browser/session.

Nếu authorized client repository lưu token theo session nhưng không dọn đúng khi đổi principal, request của Bob có thể vô tình dùng access token Alice.

Cần:

1. Định danh user theo issuer + subject từ OIDC đã xác minh.
2. Ràng buộc authorized client với đúng principal/session.
3. Dọn token cũ khi chuyển account hoặc tenant.
4. Không dùng cache token toàn cục theo registration ID.
5. Không chọn principal name do browser tự gửi.
6. Kiểm tra quyền ở API đích.

### 21.1. Nhiều issuer có thể trùng `sub`

OIDC `sub` chỉ đảm bảo định danh trong phạm vi issuer. Nếu hai OP cùng phát hành `sub=12345`, không mặc định cùng một user.

Khi thiết kế khóa định danh dùng cho token store, nên sử dụng identity nội bộ đáng tin cậy liên kết với `iss` + `sub` hoặc mô hình tenant tương đương.

### 21.2. Registration ID không phải audience

Cùng registration ID có thể xuất hiện trong code, nhưng access token vẫn phải phù hợp Resource Server cụ thể. Không đưa token dành cho Orders API sang Billing API.

## 22. Refresh token rotation và request đồng thời

Giả sử authorized client A1/R1, và AS dùng rotation:

~~~text
Request A: load A1/R1
Request B: load A1/R1
Request A: refresh R1 -> A2/R2
Request B: refresh R1 -> invalid_grant hoặc reuse detection
~~~

Không mặc định manager/repository đảm bảo atomic refresh trên nhiều request hoặc nhiều node.

Khi tải cao, cần cân nhắc:

- Khóa đồng bộ theo registration + principal/service.
- Single-flight hoặc locking phù hợp.
- Ghi token mới có điều kiện để tránh ghi đè bằng bản cũ.
- Kho token chia sẻ giữa instances.
- Xử lý refresh response bị mất.
- Chính sách của AS về rotation và reuse.

Nếu response refresh thành công không cấp R2, provider thường giữ R1. Nhưng R1 vẫn có thể hết hạn hoặc bị AS revoke về sau; không coi nó hợp lệ mãi mãi.

## 23. Security considerations

### 23.1. Token là credential nhạy cảm

Không ghi vào logs/tracing:

~~~text
access_token
refresh_token
id_token
authorization_code
code_verifier
client_secret
WebSession cookie
serialized OAuth2AuthorizedClient
~~~

Nên log thông tin ít nhạy cảm:

~~~text
registrationId=corporate
principalReference=internal-user-id
authorizedClientFound=true
refreshAttempted=true
refreshSucceeded=true
tokenExpiresAt=timestamp
correlationId=...
~~~

### 23.2. Dùng access token đúng API

`OAuth2AuthorizedClient.getAccessToken()` cung cấp access token dành cho API. Không gửi `OidcUser.getIdToken()` hoặc refresh token đến Resource Server.

Phải xác định audience/scope đúng và giới hạn outbound WebClient chỉ gọi host tin cậy.

### 23.3. Không để WebClient gắn token cho URL tùy ý

Một OAuth2-aware WebClient có thể tự gắn bearer token. Nếu ứng dụng nhận full URL từ user rồi dùng cùng WebClient, token có thể bị gửi đến host không mong đợi.

Tách client theo Resource Server, hạn chế host/redirect, HTTPS và token scopes theo policy.

### 23.4. Session và logout

WebFlux thường dùng `WebSession` và `ServerSecurityContextRepository`. Session logout và xóa authorized client cục bộ không tự thu hồi token tại AS.

Nếu authorized client lưu qua `ReactiveOAuth2AuthorizedClientService` ngoài session, record có thể tồn tại sau logout nếu không có cleanup riêng.

### 23.5. Không coi `Authentication.isAuthenticated()` là đủ quyền API

User đăng nhập hợp lệ vẫn có thể không được xem đơn hàng của người khác. API phải kiểm tra ownership, tenant và quyền nghiệp vụ theo từng request.

## 24. Testing reactive manager

### 24.1. Dùng `StepVerifier` kiểm tra publisher

Với một manager đã được cấu hình cùng mock token endpoint/service phù hợp, có thể dùng Reactor Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class AuthorizedClientManagerTest {

    @Test
    void returnsClientWhenAvailable() {
        // manager và authorizeRequest được tạo bằng test fixtures
        StepVerifier.create(manager.authorize(authorizeRequest))
                .assertNext(client -> {
                    assertThat(client.getClientRegistration()
                            .getRegistrationId())
                            .isEqualTo("corporate");
                    assertThat(client.getAccessToken()).isNotNull();
                })
                .verifyComplete();
    }
}
~~~

Đây là ví dụ minh họa cấu trúc test; `manager` và `authorizeRequest` là fixtures do test cung cấp, không phải biến được Spring tự tạo trong class ví dụ.

Để dùng `StepVerifier` cần dependency `reactor-test` trong phạm vi test.

### 24.2. Những tình huống nên kiểm tra

| Tình huống | Kỳ vọng |
|---|---|
| Registration không có authorized client, grant hỗ trợ | Provider tạo token khi điều kiện cho phép |
| Token còn hạn | Manager có thể trả client cũ |
| Token sắp hết hạn, có refresh token | Provider refresh và lưu token mới |
| Refresh response không có token thay thế | Giữ refresh token cũ |
| Refresh response có R2 | Lưu R2, không dùng lại R1 |
| AS trả `invalid_grant` | Failure handling đúng, không retry vô hạn |
| Không có provider phù hợp | Empty/error theo contract, không tạo token giả |
| Web manager thiếu exchange cần thiết | Xử lý/lỗi context rõ ràng |
| Background manager chạy ngoài HTTP | Không cần ServerWebExchange |
| Request Bob đọc token Alice | Bị ngăn bằng principal isolation |
| Hai requests refresh đồng thời | Không ghi đè token rotation mới |
| WebClient gọi sai host | Không làm lộ bearer token |

### 24.3. Test không nên gọi AS production

Dùng stub/mock HTTP token endpoint hoặc test Authorization Server trong môi trường được kiểm soát. Không ghi token thật vào test logs hoặc dùng refresh token thật để tạo lỗi rotation/reuse.

## 25. Troubleshooting

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `authorize()` trả `Mono.empty()` | Không có authorized client/provider phù hợp | Kiểm tra registration, grant, context |
| Manager bị thiếu `ServerWebExchange` | Dùng web manager ngoài request hoặc thiếu attribute | Truyền exchange đúng hoặc chọn service manager |
| Background job lỗi vì thiếu session | Dùng web repository thay service | Dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| Không thấy token sau login | Repository/service khác nơi lưu hoặc chưa hoàn tất flow | Xem wiring và callback |
| Token cũ được trả về nhiều lần | Access token còn đủ điều kiện dùng | Có thể là hành vi đúng |
| Token hết hạn không refresh | Không có R1, thiếu refresh provider hoặc AS policy | Kiểm tra provider, grant, token store |
| `invalid_grant` khi refresh | Expiry/revocation/rotation/race | Xử lý failure, không retry mù |
| `invalid_client` | Client authentication/config sai | Kiểm tra registration, secret, provider |
| `block()` gây lỗi trên event loop | Blocking trong reactive request | Compose Mono bằng flatMap |
| Không thấy Authentication trong operator | Dùng ThreadLocal hoặc tách subscription | Dùng ReactiveSecurityContextHolder, giữ pipeline |
| 401 từ Resource Server | Sai audience/issuer/expiry/token profile | Kiểm tra API validation |
| 403 từ Resource Server | Thiếu quyền/scope/ownership | Không chỉ refresh token |
| Hai instance thấy token khác nhau | Store không chia sẻ/không nhất quán | Reactive service store/session shared |
| User Bob dùng token Alice | Principal/session isolation lỗi | Sửa storage key/cleanup |
| Token xuất hiện trong log | Debug interceptor/tracing thu thập header | Redact credential |

## 26. Tình huống thực hành

### Tình huống A: user OIDC Login trong WebFlux

Alice đăng nhập thành công, có `Authentication` và authorized client `corporate`. Controller cần access token để gọi Orders API.

**Cách làm:** dùng web manager hoặc OAuth2-aware WebClient với principal và exchange context đáng tin cậy. Trả `Mono`; không gọi `block()`.

### Tình huống B: không có authorized client

Controller gọi manager trước khi hoàn tất browser Authorization Code flow.

**Cách làm:** bắt đầu authorization flow tương tác khi phù hợp; không mặc định manager sẽ tự mở browser và hoàn thành callback.

### Tình huống C: scheduled reporting job

Một job chạy mỗi giờ, cần token `client_credentials`.

**Cách làm:** dùng service manager với principal kỹ thuật `reporting-job`, provider `clientCredentials()` và reactive authorized client service. Không cần WebSession.

### Tình huống D: access token hết hạn

Authorized client A1/R1; provider có `refreshToken()`.

**Cách làm:** manager có thể refresh và lưu A2/R2 hoặc A2/R1 theo token response. Không coi refresh là login mới.

### Tình huống E: token API trả 403

Access token có `orders.read`, endpoint yêu cầu `orders.approve`.

**Cách làm:** xem scope và quyền nghiệp vụ; refresh không tự tăng quyền.

### Tình huống F: Reactor Context bị mất

Service tự `subscribe()` trong callback tách khỏi HTTP request và không thấy principal.

**Cách làm:** trả `Mono` để upstream compose; khi chạy độc lập, dùng service identity hoặc truyền dữ liệu tin cậy theo thiết kế.

### Tình huống G: chuyển tài khoản

Alice logout, Bob login cùng browser nhưng authorized client cũ còn trong store.

**Cách làm:** cleanup và ràng buộc principal/issuer+subject, không dùng token của Alice cho Bob.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** `ReactiveOAuth2AuthorizedClientManager.authorize(...)` nhận tham số kiểu gì?

**Trả lời:** `OAuth2AuthorizeRequest` — object mô tả registration, principal và context attributes.

**Câu 2.** Phương thức trả về kiểu gì?

**Trả lời:** `Mono<OAuth2AuthorizedClient>`, không phải `OAuth2AuthorizedClient` đồng bộ.

**Câu 3.** `OAuth2AuthorizeRequest` có giống `OAuth2AuthorizationRequest` gửi đến OP không?

**Trả lời:** Không. Một object là request nội bộ cho manager; object kia mô tả protocol Authorization Request của flow redirect.

**Câu 4.** Manager nào phù hợp HTTP WebFlux request?

**Trả lời:** `DefaultReactiveOAuth2AuthorizedClientManager` với `ServerOAuth2AuthorizedClientRepository`.

**Câu 5.** Manager nào phù hợp scheduled job không có `ServerWebExchange`?

**Trả lời:** `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` với `ReactiveOAuth2AuthorizedClientService`.

**Câu 6.** Vì sao có thể cần truyền `ServerWebExchange` qua attributes?

**Trả lời:** Để web manager/repository có ngữ cảnh request cần thiết khi load/save authorized client.

**Câu 7.** Gọi `authorize()` có chắc luôn gọi token endpoint không?

**Trả lời:** Không. Manager có thể trả authorized client đã lưu khi không cần reauthorize.

**Câu 8.** `refreshToken()` có thể tạo token lần đầu nếu chưa có refresh token không?

**Trả lời:** Không. Refresh token grant cần refresh token đã được AS cấp.

**Câu 9.** `clientCredentials()` có đại diện user OIDC Login không?

**Trả lời:** Không. Grant này dùng danh tính client/service.

**Câu 10.** Vì sao không dùng `block()` trong controller WebFlux?

**Trả lời:** Nó có thể chặn event loop và phá vỡ cách phối hợp reactive; nên dùng `flatMap`/`map`.

**Câu 11.** Khi `authorize()` trả `Mono.empty()`, nên làm gì?

**Trả lời:** Xử lý không có authorization theo policy, ví dụ `switchIfEmpty`, chứ không dùng token giả.

**Câu 12.** Access token mới sau refresh có chứng minh user vừa thực hiện MFA không?

**Trả lời:** Không. OIDC reauthentication/step-up cần luồng và kiểm tra kết quả riêng.

**Câu 13.** Hai provider khác nhau có cùng `sub` có chắc là một user không?

**Trả lời:** Không. Cần xét issuer và ánh xạ tài khoản nội bộ.

**Câu 14.** Có thể dùng ID token để gọi Orders API thay access token không?

**Trả lời:** Không theo mô hình OAuth Resource Server thông thường.

**Câu 15.** Manager đã trả authorized client có thay thế kiểm tra quyền ở API không?

**Trả lời:** Không. Resource Server phải xác minh token, audience/scope và quyền trên tài nguyên.

## Ghi nhớ

- **`OAuth2AuthorizeRequest` là object đầu vào, còn `ReactiveOAuth2AuthorizedClientManager.authorize(...)` trả `Mono<OAuth2AuthorizedClient>`.** Không nhầm request nội bộ này với `OAuth2AuthorizationRequest` của browser redirect.
- **Manager điều phối registration, principal, kho authorized client và reactive provider chain**. Nó có thể cấp token lần đầu, dùng lại token hoặc reauthorize, chứ không luôn gọi token endpoint.
- **`DefaultReactiveOAuth2AuthorizedClientManager` dành cho WebFlux web request** và thường cần `ServerWebExchange` qua context phù hợp; **`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` phù hợp cho background/non-web**.
- **`ReactiveOAuth2AuthorizedClientProvider` chỉ xử lý grant phù hợp**, như Authorization Code, Refresh Token hoặc Client Credentials. Authorization Code vẫn cần browser redirect/callback.
- **Compose `Mono` trong WebFlux; không gọi `block()` hay `subscribe()` thủ công** để lấy token trong request path.
- **WebClient mang access token phải gọi đúng host/audience/scope**; không dùng ID token thay access token và không truyền token đến URL không tin cậy.
- **Bảo vệ principal isolation, refresh token rotation, concurrency và token store**, không log credential và không coi logout cục bộ là token revocation tại AS.
