# 21.9. `ServerOAuth2AuthorizedClientExchangeFilterFunction` trong `WebClient`

Trong **Spring Security OAuth 2.0/OIDC Client trên Reactive stack (Spring WebFlux)**, ứng dụng không chỉ đăng nhập người dùng qua OpenID Connect mà còn có thể gọi các API downstream bằng access token được Authorization Server cấp. Để kết hợp hệ thống **OAuth2 Authorized Client** của Spring Security với HTTP client `WebClient`, Spring cung cấp lớp **`ServerOAuth2AuthorizedClientExchangeFilterFunction`**.

Lớp này là một `ExchangeFilterFunction`: nó tham gia vào chuỗi xử lý outbound HTTP request của WebClient, tìm hoặc yêu cầu một **`OAuth2AuthorizedClient`** phù hợp, rồi đưa **access token** vào header `Authorization: Bearer ...` khi gửi request. Nếu cấu hình manager và grant cho phép, việc cấp hoặc làm mới access token có thể được xử lý qua hạ tầng OAuth2 Client, không cần mỗi service tự gọi Token Endpoint.

Điểm khó của chủ đề nằm ở bốn câu hỏi: **token của ai**, **thuộc ClientRegistration nào**, **được gửi tới API nào**, và **phải làm gì khi token hết hạn hoặc API từ chối**. Trong Reactive stack, cần thêm câu hỏi thứ năm: **Authentication và ServerWebExchange có được truyền đúng qua Reactor context không?**

Bài này hướng dẫn cách cấu hình lớp filter, lựa chọn authorized client tường minh, sử dụng cùng `WebClient` và `ServerHttpSecurity`, xử lý refresh/HTTP 401/403, chống gửi nhầm Bearer token, và phân biệt HTTP request theo user với scheduled job bên ngoài request.

## 1. Bài toán thực tế: WebFlux gọi một API sau OIDC Login

Giả sử một portal WebFlux cung cấp dashboard báo cáo:

1. Người dùng truy cập `/dashboard`.
2. Spring Security thực hiện OIDC Login với một OpenID Provider.
3. Authorization Code Flow hoàn tất: Spring nhận và xác minh ID Token, tạo `OidcUser`.
4. Ứng dụng lưu trạng thái `Authentication` và `OAuth2AuthorizedClient` đã được cấp token.
5. Controller/service gọi `https://reports-api.example.test/v1/reports`.
6. Reports API yêu cầu **access token** có scope `reports.read` và audience phù hợp.

HTTP request tới Reports API cần dạng:

```http
GET /v1/reports HTTP/1.1
Host: reports-api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
Accept: application/json
```

Nếu tự lấy token từ một map session rồi ghép header ở mỗi controller, ứng dụng dễ gặp những lỗi:

- Chọn nhầm token của user khác.
- Dùng ID Token OIDC thay cho access token.
- Gửi access token của API A tới API B.
- Không kiểm tra token đã hết hạn.
- Bỏ sót refresh token rotation và cập nhật storage.
- Retry vô hạn khi API trả `401 invalid_token` hoặc `403 insufficient_scope`.
- Đọc `SecurityContextHolder` kiểu Servlet trong WebFlux dù Reactive security context không được quản lý bằng ThreadLocal theo cùng cách.

`ServerOAuth2AuthorizedClientExchangeFilterFunction` giúp thống nhất phần **OAuth2 token selection/attachment** trên WebClient. Nó không tự thay thế **authorization nghiệp vụ**, không đảm bảo mọi token đều được mọi API chấp nhận, và không thể biến một request chưa được người dùng cấp quyền thành một phiên OIDC hợp lệ chỉ bằng cách thêm filter.

## 2. Mô hình kiến trúc tổng quan

```mermaid
flowchart LR
    Browser["Browser / người dùng"] --> Web["Spring WebFlux endpoint"]
    Web --> Security["Reactive SecurityContext"]
    Web --> Client["WebClient"]
    Client --> Filter["ServerOAuth2AuthorizedClientExchangeFilterFunction"]
    Filter --> Manager["ReactiveOAuth2AuthorizedClientManager"]
    Manager --> Registrations["ReactiveClientRegistrationRepository"]
    Manager --> Storage["ServerOAuth2AuthorizedClientRepository / Service"]
    Manager --> Token["Authorization Server / Token Endpoint"]
    Filter --> API["Resource Server / Reports API"]
    API --> Client
```

Một request cụ thể:

```mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Portal as WebFlux Portal
    participant Filter as OAuth2 WebClient Filter
    participant Manager as Reactive Client Manager
    participant Store as Authorized Client Store
    participant AS as Authorization Server
    participant API as Reports API

    User->>Portal: GET /reports
    Portal->>Filter: WebClient GET /v1/reports
    Note over Portal,Filter: attributes(clientRegistrationId("company"))
    Filter->>Manager: authorize(registration + principal)
    Manager->>Store: Tìm authorized client
    alt Token còn được dùng theo chính sách
        Store-->>Manager: OAuth2AuthorizedClient
    else Cần cấp hoặc làm mới token và grant cho phép
        Manager->>AS: Token Endpoint request
        AS-->>Manager: Access token mới (+ refresh token mới?)
        Manager->>Store: Cập nhật authorized client
    end
    Manager-->>Filter: OAuth2AuthorizedClient
    Filter->>API: Authorization: Bearer access_token
    API-->>Filter: HTTP response
    Filter-->>Portal: Mono/ClientResponse
    Portal-->>User: Kết quả báo cáo hoặc lỗi phù hợp
```

Sơ đồ là **mô hình khái quát**: manager/provider có thể trả authorized client hiện có mà không gọi Token Endpoint, hoặc không có cách authorize nếu chưa có grant phù hợp. Không suy ra mỗi request WebClient đều phải xin một access token mới.

## 3. Phân biệt OAuth2 Login, OAuth2 Client và Resource Server

Một ứng dụng WebFlux có thể sử dụng ba khả năng khác nhau của Spring Security:

| Khả năng | Mục đích | Thành phần thường thấy |
|---|---|---|
| **`oauth2Login`** | Người dùng đăng nhập vào portal bằng OP/OIDC | `ServerHttpSecurity.oauth2Login`, `OidcUser` |
| **`oauth2Client`** | Ứng dụng lấy/quản lý token để gọi API thay mặt user hoặc chính Client | `ReactiveOAuth2AuthorizedClientManager`, WebClient OAuth2 filter |
| **`oauth2ResourceServer`** | Chính ứng dụng đóng vai API và xác minh Bearer token từ caller | `oauth2ResourceServer().jwt()` hoặc opaque token |

Trong bài này, WebFlux portal là một **OAuth2 Client** khi gọi Reports API. Reports API là **Resource Server**.

Đăng nhập OIDC thành công không đồng nghĩa với việc access token nhận được **có quyền truy cập mọi API**. Token phải được cấp cho đúng resource/audience, đúng scope và được Resource Server chấp nhận.

### 3.1. Access token khác ID Token

- **ID Token**: JWT do OpenID Provider cấp để Client xác minh danh tính của user.
- **Access token**: credential dùng gọi API theo quyền đã được cấp.
- **Refresh token**: credential dùng xin access token mới tại Token Endpoint nếu được cấp.

WebClient OAuth2 filter gắn **access token** vào `Authorization` header. Không đưa `OidcUser#getIdToken().getTokenValue()` vào đó.

### 3.2. `OAuth2AuthorizedClient` là gì?

`OAuth2AuthorizedClient` kết hợp:

```text
OAuth2AuthorizedClient
  ├─ ClientRegistration
  │    ├─ registrationId
  │    ├─ clientId
  │    └─ authorizationGrantType / provider metadata
  ├─ principalName
  ├─ OAuth2AccessToken
  │    ├─ tokenValue
  │    ├─ issuedAt / expiresAt
  │    └─ scopes
  └─ OAuth2RefreshToken? (nullable)
```

**`ClientRegistration` là cấu hình**. **`OAuth2AuthorizedClient` là kết quả Client đã được cấp token**, gắn với một principal. Cả hai không thể dùng thay thế cho nhau.

## 4. Các thành phần Reactive liên quan

| API / class | Vai trò |
|---|---|
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Filter cho WebClient để tìm token, gắn Bearer và có thể xử lý lỗi OAuth2 |
| `ReactiveClientRegistrationRepository` | Lưu cấu hình Client registrations |
| `ClientRegistration` | Một OAuth2 Client đã đăng ký với Authorization Server |
| `ServerOAuth2AuthorizedClientRepository` | Lưu/truy xuất authorized clients trong ngữ cảnh `ServerWebExchange` |
| `ReactiveOAuth2AuthorizedClientService` | Lưu/truy xuất authorized clients bằng reactive API, không tự buộc vào HTTP exchange |
| `ReactiveOAuth2AuthorizedClientManager` | Điều phối authorization/reauthorization |
| `DefaultReactiveOAuth2AuthorizedClientManager` | Manager thường sử dụng cho reactive web requests |
| `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | Manager dựa trên service dành cho tác vụ ngoài `ServerWebExchange` |
| `ReactiveOAuth2AuthorizedClientProvider` | Provider xử lý grant như authorization code, refresh token, client credentials |
| `ReactiveOAuth2AuthorizedClientProviderBuilder` | Xây tổ hợp grant providers |
| `OAuth2AuthorizeRequest` | Chứa registration/principal/context của yêu cầu authorize |
| `OAuth2AuthorizationFailureHandler` dạng reactive | Xử lý thất bại authorization và có thể loại bỏ token lỗi |
| `ServerWebExchange` | Ngữ cảnh HTTP exchange của Spring WebFlux |
| `ReactiveSecurityContextHolder` | Truy cập `SecurityContext` qua Reactor context |

Tên các interface/lớp rất giống Servlet stack, nhưng chúng **không dùng cùng contract**. Ví dụ `OAuth2AuthorizedClientManager` (Servlet) và `ReactiveOAuth2AuthorizedClientManager` không hoán đổi trực tiếp.

## 5. `ServerOAuth2AuthorizedClientExchangeFilterFunction` hoạt động như thế nào?

Trong chuỗi xử lý WebClient:

```text
service/controller tạo ClientRequest
    ↓
WebClient ExchangeFilterFunction chain
    ↓
ServerOAuth2AuthorizedClientExchangeFilterFunction
    ├─ Xác định authorized client cần dùng
    ├─ Có explicit client không?
    ├─ Nếu theo registration: lấy principal và yêu cầu manager authorize
    ├─ Lấy access token phù hợp
    └─ Thêm Authorization: Bearer <token> vào outbound request
    ↓
HTTP connector
    ↓
Resource Server
    ↓
ClientResponse / Mono / Flux
```

Các lựa chọn phổ biến để chọn client:

1. Truyền một **`OAuth2AuthorizedClient` tường minh** vào attributes của WebClient request.
2. Truyền **`clientRegistrationId`** để filter/manager tìm authorized client phù hợp theo principal.
3. Bật chính sách **default authorized client** nếu thực sự cần và hiểu rõ rủi ro.
4. Bật **default registration ID** cho WebClient chuyên biệt, có host cố định và được kiểm soát.

Trong phần lớn mã ứng dụng nhiều integrations, cách **tường minh trên từng request** giúp code rõ và giảm nguy cơ gửi nhầm credential.

## 6. Dependencies cho một Spring Boot WebFlux OAuth2 Client

Ví dụ với Spring Boot 3.x tương thích:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
</dependencies>
```

Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
}
```

Spring Boot quản lý các version phù hợp qua BOM. Không tự trộn nhiều nhánh Spring Security/Core/WebFlux không tương thích.

**Lưu ý:** Nếu thêm cả `spring-boot-starter-web` và `webflux`, auto-configuration có thể ưu tiên ứng dụng Servlet trong cấu hình thông dụng. Bài này giả định server chạy **Reactive WebFlux**, dùng `SecurityWebFilterChain` và `ServerHttpSecurity`. Nếu là Spring MVC chỉ dùng WebClient làm HTTP client, lớp tương ứng thường là `ServletOAuth2AuthorizedClientExchangeFilterFunction`.

## 7. Cấu hình OIDC Client cho người dùng đăng nhập và gọi API

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-op
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - reports.read

        provider:
          company-op:
            issuer-uri: https://login.example.test/realms/company
```

Giải thích:

- `company` là **registration ID** dùng trong Java.
- `openid` yêu cầu OIDC Login.
- `reports.read` là scope API minh họa; issuer và Reports API phải thực sự hỗ trợ.
- `issuer-uri` dùng để khám phá metadata OIDC, Token Endpoint và JWKS khi provider hỗ trợ discovery.
- `redirect-uri` là callback của **Authorization Code Flow**, không phải đường dẫn API downstream.
- `client-secret` phải nằm trong secret manager/biến môi trường hoặc cơ chế tương đương.

Tên miền `example.test` và các credentials là placeholder; code minh họa không thể dùng nguyên trạng để đăng nhập một IdP thật.

### 7.1. Không giả định OIDC login token đủ quyền cho Reports API

Một IdP có thể chỉ cấp access token cho UserInfo Endpoint, hoặc Reports API yêu cầu audience/resource indicator khác. Do đó cần kiểm tra:

- Reports API chấp nhận issuer nào?
- Token được cấp cho audience nào?
- Scope `reports.read` có thực sự được cấp?
- Nếu provider dùng resource-specific access token, Client đã xin token đúng tài nguyên chưa?
- Người dùng hoặc application đã được consent/chính sách cho phép chưa?

Gắn Bearer header thành công không chứng minh API sẽ trả 200.

## 8. Cấu hình Reactive Security

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
```

Cấu hình:

- `oauth2Login` cho phép người dùng đăng nhập OAuth2/OIDC.
- `oauth2Client` kích hoạt những chức năng hỗ trợ OAuth2 Client theo cấu hình Spring Security Reactive.
- `authorizeExchange` bảo vệ các endpoint theo authentication; các rule authorization nghiệp vụ vẫn cần thiết kế riêng.

`SecurityWebFilterChain` là class dành cho WebFlux. Không sử dụng `HttpSecurity`/`SecurityFilterChain` của Servlet ở đây.

### 8.1. OIDC authentication xảy ra ở bước nào?

Spring Security xử lý authorization request, callback, token exchange, kiểm tra ID Token và xây `OidcUser`. WebClient filter của bài này hoạt động **sau/độc lập với bước xác minh user**, khi backend tạo một outbound HTTP call.

Không tự Base64-decode ID Token rồi đưa bất kỳ claim vào `OAuth2AuthorizeRequest` như một bằng chứng người dùng đã đăng nhập.

## 9. Tạo WebClient với constructor nhận repositories

Một cấu hình phổ biến:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration
    .ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server
    .ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportsWebClientConfiguration {

    @Bean("reportsWebClient")
    WebClient reportsWebClient(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        var oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                registrations,
                authorizedClients
            );

        return WebClient.builder()
            .baseUrl("https://reports-api.example.test")
            .filter(oauth2)
            .build();
    }
}
```

Các import dài ở đoạn trên được chia dòng để trình bày. Trong file Java thật, mỗi import phải là một câu lệnh hợp lệ trên một dòng:

```java
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
```

**Chỉ cần một bean `reportsWebClient`** cho cách này; các cấu hình khác trong bài là phương án thay thế, không phải đoạn phải dán vào cùng class.

### 9.1. Filter được đăng ký ở đâu?

`WebClient.Builder#filter(...)` thêm một `ExchangeFilterFunction` vào request pipeline:

```java
WebClient.builder()
    .filter(oauth2)
    .build();
```

Không có bước gọi `.apply(oauth2.oauth2Configuration())` như mẫu dành riêng cho **Servlet** variant. Với Reactive `ServerOAuth2AuthorizedClientExchangeFilterFunction`, `.filter(oauth2)` là cách tích hợp trực tiếp, rõ ràng.

### 9.2. Constructor repository có ý nghĩa gì?

Constructor này nhận:

```java
ServerOAuth2AuthorizedClientExchangeFilterFunction(
    ReactiveClientRegistrationRepository clientRegistrations,
    ServerOAuth2AuthorizedClientRepository authorizedClients
)
```

Nó dùng hạ tầng phù hợp **Reactive web request**, quản lý authorized client theo `ServerWebExchange`/principal. Trong các phiên bản Spring Security hiện đại, cách khởi tạo từ repository còn liên quan tới cấu hình failure handler mặc định khi Resource Server báo một số OAuth2 errors. Chi tiết về constructor/failure behavior được giải thích ở mục xử lý lỗi.

## 10. Chọn `clientRegistrationId` tường minh khi gọi API

Lệnh gọi cơ bản:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> reports = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
```

`clientRegistrationId("company")` là static helper trả về một `Consumer<Map<String, Object>>` cho WebClient request attributes. Filter đọc thuộc tính này để biết ClientRegistration được mong muốn.

### 10.1. Vì sao nên chỉ định registration mỗi request?

Một người dùng có thể kết nối nhiều external APIs:

```text
Reactive Authentication = user-782

Authorized Clients:
  company         -> access token dành cho Reports API
  calendar         -> access token dành cho Calendar API
  accounting       -> access token dành cho Billing API
```

Nếu dùng nhầm authorized client:

- Reports API có thể trả 401 do sai audience.
- Billing API có thể trả 403 do thiếu scope.
- Token có thể bị gửi tới bên thứ ba không có quyền nhận nó.
- Log/trace sẽ khó xác định token bắt nguồn từ Client nào.

Vì vậy lựa chọn registration nên thể hiện rõ ngay trong đoạn tạo outbound request.

### 10.2. Nếu chưa có authorized client?

Đối với Authorization Code Grant của user, lần cấp quyền đầu tiên thường đòi browser redirect tới Authorization Server, consent và callback. WebClient filter **không tự tạo một tương tác browser mới chỉ từ một HTTP call** nếu chưa có ngữ cảnh authorization phù hợp.

Tác vụ gửi HTTP request theo user phải dùng `OAuth2AuthorizedClient` đã được cấp hoặc dựa trên flow login/consent của Spring. Nếu thiếu quyền, ứng dụng cần chủ động cung cấp UX kết nối/cấp quyền lại.

## 11. Truyền `OAuth2AuthorizedClient` tường minh

Khi endpoint đã có một authorized client đáng tin, có thể truyền trực tiếp:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

Mono<String> fetchReports(
        WebClient reportsWebClient,
        OAuth2AuthorizedClient authorizedClient) {

    return reportsWebClient.get()
        .uri("/v1/reports")
        .attributes(oauth2AuthorizedClient(authorizedClient))
        .retrieve()
        .bodyToMono(String.class);
}
```

Đây là cách ghi rõ: “request này phải dùng authorized client cụ thể mà tôi đã xác định”.

### 11.1. `@RegisteredOAuth2AuthorizedClient` trên WebFlux controller

Trong cấu hình Spring Security Reactive phù hợp, có thể inject authorized client được quản lý bằng annotation:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@RestController
public class ReportsController {

    private final WebClient reportsApi;

    public ReportsController(
            @Qualifier("reportsWebClient") WebClient reportsApi) {
        this.reportsApi = reportsApi;
    }

    @GetMapping("/reports")
    public Mono<String> reports(
            @RegisteredOAuth2AuthorizedClient("company")
            OAuth2AuthorizedClient authorizedClient) {

        return reportsApi.get()
            .uri("/v1/reports")
            .attributes(oauth2AuthorizedClient(authorizedClient))
            .retrieve()
            .bodyToMono(String.class);
    }
}
```

Đoạn này minh họa dependency injection/argument resolution trong Reactive OAuth2 Client. Hành vi khi authorized client chưa có, cách manager hỗ trợ reauthorization và support của annotation cần phù hợp đúng Spring Security version đang chạy.

**Không lấy object `OAuth2AuthorizedClient` từ JSON do browser gửi rồi coi đáng tin.** Nó phải đến từ repository/manager của ứng dụng với principal ownership được xác minh.

### 11.2. Hai cách chọn client khác nhau thế nào?

| Cách | Dữ liệu đầu vào | Lợi ích | Điều cần nhớ |
|---|---|---|---|
| `clientRegistrationId("company")` | Registration ID | Filter/manager có thể tìm và authorize theo principal | Cần đúng reactive context và grant hỗ trợ |
| `oauth2AuthorizedClient(client)` | Authorized client đã chọn | Rõ chính xác credential gắn vào request | Phải bảo đảm client đúng user/API, hiểu vòng đời token khi truyền object có sẵn |

Không mặc định rằng truyền object `OAuth2AuthorizedClient` tường minh luôn thực hiện **cùng đường reauthorization** như lookup theo registration; hãy đọc behavior của filter/version và nơi object được lấy. Với ứng dụng thường xuyên cần refresh, manager đúng cấu hình nên là điểm điều phối đáng tin.

## 12. Constructor nhận `ReactiveOAuth2AuthorizedClientManager`

Khi muốn tự kiểm soát providers, xử lý refresh hoặc persistence, ta có thể cấu hình manager riêng.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
public class ReactiveManagerConfiguration {

    @Bean("webReactiveAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager webAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        var manager = new DefaultReactiveOAuth2AuthorizedClientManager(
            registrations,
            authorizedClients
        );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Sau đó tạo WebClient:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean("reportsWebClient")
WebClient reportsWebClient(
        @Qualifier("webReactiveAuthorizedClientManager")
        ReactiveOAuth2AuthorizedClientManager manager) {

    var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        manager
    );

    return WebClient.builder()
        .baseUrl("https://reports-api.example.test")
        .filter(oauth2)
        .build();
}
```

Hai ví dụ `reportsWebClient` ở mục 9 và 12 là **hai lựa chọn thay thế**, không dùng cùng lúc với một bean name.

### 12.1. Chọn providers rõ ràng

`ReactiveOAuth2AuthorizedClientProviderBuilder` cho phép xây một tập grant providers, chẳng hạn:

```java
ReactiveOAuth2AuthorizedClientProvider provider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
```

Chỉ bật những grant được ứng dụng sử dụng thực sự. Thêm `refreshToken()` không làm nhà cung cấp tự cấp refresh token. Thêm `authorizationCode()` không tự mở browser trong scheduled task. Thêm `clientCredentials()` không chuyển user consent thành quyền ứng dụng.

### 12.2. Khi nào manager không authorize được?

Có thể xảy ra:

- `registrationId` không tồn tại.
- Manager không có provider cho grant tương ứng.
- Authorized client của user chưa được cấp.
- Không có refresh token nhưng access token hết hạn.
- Token Endpoint trả `invalid_client`, `invalid_grant`, `invalid_scope`.
- Server context/principal không được cung cấp đúng khi cần.

Với `ReactiveOAuth2AuthorizedClientManager#authorize(...)`, kết quả là `Mono<OAuth2AuthorizedClient>`; trong một số trường hợp không có kết quả authorization được hỗ trợ, Mono có thể rỗng. Không coi mọi lần gọi luôn phát ra authorized client thành công.

## 13. Chọn token theo `Authentication` và `ServerWebExchange`

Reactive stack dùng Reactor context để truyền thông tin bảo mật qua pipeline, thay vì dựa vào ThreadLocal kiểu Servlet cho mọi bước async.

`ServerOAuth2AuthorizedClientExchangeFilterFunction` hỗ trợ các request attributes để cung cấp ngữ cảnh khi cần:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.authentication;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.serverWebExchange;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;
```

Ví dụ minh họa khi service có một `Authentication` đáng tin và `ServerWebExchange` hiện tại:

```java
public Mono<String> fetchForAuthenticatedUser(
        Authentication userAuthentication,
        ServerWebExchange exchange) {

    return reportsWebClient.get()
        .uri("/v1/reports")
        .attributes(clientRegistrationId("company"))
        .attributes(authentication(userAuthentication))
        .attributes(serverWebExchange(exchange))
        .retrieve()
        .bodyToMono(String.class);
}
```

Cần imports tương ứng:

```java
import org.springframework.security.core.Authentication;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;
```

Đây là một mẫu minh họa truyền context **đã xác minh**, không phải lời khuyên rằng mọi request bắt buộc phải thêm cả ba attributes. Trong nhiều Spring Security WebFlux flows, Authentication có thể được tìm thông qua Reactive SecurityContext và exchange có thể được integration cung cấp sẵn. Nhưng khi pipeline được tạo và subscribe ở những ngữ cảnh khác nhau, truyền tường minh giúp code dễ hiểu và tránh phụ thuộc ngầm.

### 13.1. Không cho caller tùy ý chọn Authentication

Rất nguy hiểm nếu endpoint nhận một username trong request và tự tạo Authentication “đã xác thực” để lấy token của user đó.

```java
// KHÔNG ĐƯỢC coi một String do browser nhập
// là bằng chứng để chọn token của user khác.
String principalName = request.getQueryParams().getFirst("userId");
```

Quyền sử dụng OAuth2AuthorizedClient của user phải được kiểm tra tại **nội bộ**, dựa trên session/authentication thật, mapping tài khoản và ownership.

### 13.2. Reactor context không tự tồn tại trong mọi background task

Một job `@Scheduled` hoặc queue consumer có thể không có `ServerWebExchange` và không có user `SecurityContext`.

- Nếu job dùng **quyền ứng dụng**, thường dùng `client_credentials` với service-based reactive manager.
- Nếu job dùng **quyền user đã ủy quyền**, phải lấy đúng authorized client đã lưu kèm consent/refresh token và kiểm tra ownership.
- Không nên tạo một `ServerWebExchange` giả rồi ép repository dựa trên web session hoạt động ngoài request.

### 13.3. Tránh `block()` để lấy Authentication

Không làm:

```java
// Không nên trong request handling WebFlux:
Authentication auth =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication())
        .block();
```

Reactive flow nên sử dụng `Mono`, `flatMap` và các operator thích hợp:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> authorizedRequest() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .switchIfEmpty(Mono.error(
            new IllegalStateException("No authenticated security context")
        ))
        .flatMap(authentication ->
            reportsWebClient.get()
                .uri("/v1/reports")
                .attributes(clientRegistrationId("company"))
                .attributes(
                    ServerOAuth2AuthorizedClientExchangeFilterFunction
                        .authentication(authentication)
                )
                .retrieve()
                .bodyToMono(String.class)
        );
}
```

Phương thức trên minh họa truyền Authentication qua Reactor context. Trong ứng dụng thực, cần xác minh `authentication.isAuthenticated()` và áp chính sách authorization trước khi lấy dữ liệu, không chỉ kiểm tra object có tồn tại. Với trường hợp không cần đọc Authentication trực tiếp, dùng các attributes/annotation chuẩn sẽ ngắn gọn hơn.

## 14. Nguy cơ `setDefaultOAuth2AuthorizedClient(true)`

Một phương thức của filter:

```java
oauth2.setDefaultOAuth2AuthorizedClient(true);
```

cho phép filter sử dụng authorized client gắn với OAuth2 authentication hiện tại làm mặc định, ngay cả khi request WebClient không chỉ định registration.

Tính năng này rất tiện cho demo nhưng **nguy hiểm nếu bật trên một WebClient dùng chung nhiều API**.

### 14.1. Ví dụ lộ token

Giả sử:

```java
@Bean
WebClient sharedWebClient(
        ReactiveClientRegistrationRepository registrations,
        ServerOAuth2AuthorizedClientRepository authorizedClients) {

    var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        registrations, authorizedClients);

    oauth2.setDefaultOAuth2AuthorizedClient(true);

    return WebClient.builder()
        .filter(oauth2)
        .build();
}
```

Sau đó ở một service:

```java
sharedWebClient.get()
    .uri("https://unknown-host.example.test/public-data")
    .retrieve()
    .bodyToMono(String.class);
```

Nếu filter gắn access token mặc định vào HTTP request tới domain khác, credential của người dùng có thể bị lộ. Rủi ro xuất hiện ngay cả khi API đó vốn không cần OAuth2.

**Nguyên tắc:** không bật default authorized client trên một WebClient có thể gửi request tới URL do user chọn hoặc nhiều origins khác nhau.

### 14.2. `setDefaultClientRegistrationId(...)` cũng cần giới hạn phạm vi

Có thể đặt:

```java
oauth2.setDefaultClientRegistrationId("company");
```

Điều này khiến request thiếu lựa chọn tường minh có thể dùng registration `company`. Nếu WebClient chỉ được dùng cho một Resource Server cố định, chính sách default có thể hợp lý. Nhưng nó vẫn tạo rủi ro nếu client bị tái sử dụng cho host khác.

Một thiết kế chặt hơn:

```text
reportsWebClient
  baseUrl: https://reports-api.example.test
  OAuth2 registration: company
  only relative routes from a controlled set

calendarWebClient
  baseUrl: https://calendar-api.example.test
  OAuth2 registration: calendar

publicWebClient
  no OAuth2 filter
```

### 14.3. Đừng ghép URL tùy ý từ input

Mẫu nguy hiểm:

```java
@GetMapping("/proxy")
public Mono<String> proxy(@RequestParam String url) {
    return sharedWebClient.get()
        .uri(url)
        .attributes(clientRegistrationId("company"))
        .retrieve()
        .bodyToMono(String.class);
}
```

User có thể yêu cầu backend truy cập host ngoài ý muốn, dẫn đến **SSRF và token exfiltration**. Hãy dùng base URL/allowlist server-side, route cố định và kiểm soát redirect/cross-origin header forwarding.

Không được dựa vào giả định “HTTP client chắc chắn loại Authorization header khi redirect sang host khác” nếu chưa kiểm tra connector/version và thiết kế redirect policy.

## 15. Xử lý access token hết hạn và refresh token

Access token thường có thời hạn, ví dụ 30 phút. Authorized client có:

```text
accessToken.expiresAt = 11:00 UTC
refreshToken          = RT-1 (nếu provider cấp)
```

Khi WebClient gọi API lúc 10:59:50, manager/provider có thể đánh giá token sắp hết hạn và thực hiện Refresh Token Grant nếu được cấu hình.

```mermaid
flowchart TD
    A["WebClient request với registrationId"] --> B["Manager tìm authorized client"]
    B --> C{"Token còn phù hợp?"}
    C -->|Có| D["Gắn access token hiện tại"]
    C -->|Không| E{"Có refresh token và provider?"}
    E -->|Có| F["POST /token grant_type=refresh_token"]
    F --> G{"Refresh thành công?"}
    G -->|Có| H["Lưu access/refresh token mới"]
    H --> D
    G -->|Không| I["Xử lý lỗi OAuth2, có thể reauthorize"]
    E -->|Không| J["Không thể refresh chỉ bằng dữ liệu hiện tại"]
    D --> K["Gọi Resource Server"]
```

### 15.1. Tại sao không refresh thủ công trong mỗi service?

Nếu controller tự kiểm tra `expiresAt` rồi gọi Token Endpoint, code dễ:

- Dùng refresh token cũ sau rotation.
- Gửi hai refresh requests đồng thời.
- Không lưu refresh token mới.
- Bỏ qua policy clock skew.
- Làm lỗi `invalid_grant` lặp vô hạn.
- Không đồng bộ giữa các node.

Thay vào đó, sử dụng `ReactiveOAuth2AuthorizedClientManager` và `ReactiveOAuth2AuthorizedClientProvider`, kết hợp storage/phân quyền phù hợp.

### 15.2. Refresh token rotation và nhiều requests đồng thời

Hai WebClient requests của cùng user có thể cùng phát hiện access token gần hết hạn:

```text
Request A đọc RT-1 → gửi refresh → nhận RT-2
Request B đã đọc RT-1 → gửi refresh → invalid_grant
```

Nếu Authorization Server có cơ chế refresh token reuse detection, token family có thể bị thu hồi. Cần cân nhắc single-flight refresh, locking/optimistic concurrency và cách lưu client mới nhất, đặc biệt ở hệ thống nhiều pods.

`ReactiveOAuth2AuthorizedClientService` dùng database hoặc Redis không tự động bảo đảm chỉ có **một** refresh request trên toàn cluster. Đây là vấn đề synchronization cần thiết kế theo provider và workload.

### 15.3. User login session khác token API

Người dùng có thể vẫn còn WebFlux `WebSession` và `SecurityContext` hợp lệ trong khi refresh token dùng gọi Calendar API đã bị thu hồi. Ứng dụng có thể đánh dấu external connection `RECONNECT_REQUIRED` và yêu cầu người dùng cấp quyền lại, thay vì logout toàn bộ portal theo mặc định.

Đây là một quyết định nghiệp vụ/bảo mật cần được tách khỏi filter mechanism.

## 16. Lỗi Token Endpoint và lỗi Resource Server khác nhau

Khi dùng OAuth2 Client, có ít nhất hai chỗ phát sinh lỗi:

1. **Token Endpoint:** manager/provider xin hoặc refresh token.
2. **Resource Server:** WebClient đã gắn Bearer token và gửi API call.

Ví dụ:

```text
Token Endpoint:
  400 invalid_grant
    -> refresh token expired/revoked/rotated/wrong Client

Resource Server:
  401 invalid_token
    -> access token không được chấp nhận

Resource Server:
  403 insufficient_scope
    -> access token thiếu quyền yêu cầu
```

| Lỗi | Nguồn | Hướng xử lý |
|---|---|---|
| `invalid_client` | Token Endpoint | Kiểm tra Client ID, secret, phương thức Client authentication |
| `invalid_grant` | Token Endpoint | Không retry vô hạn refresh token cũ; dọn authorized client lỗi, reauthorization khi cần |
| `invalid_scope` | Token Endpoint | Sửa scope/consent/client policy |
| HTTP 401 `invalid_token` | Resource Server | Kiểm tra expiry, audience, revocation; cập nhật token/connection đúng policy |
| HTTP 403 `insufficient_scope` | Resource Server | Yêu cầu scope/role đúng, không refresh bằng cùng scope vô hạn |
| HTTP 429 | Token Endpoint hoặc API | Backoff/Retry-After có giới hạn |
| HTTP 5xx / network timeout | Token Endpoint hoặc API | Retry có chính sách; cẩn trọng với refresh token rotation |

Không mặc định mọi `401` đều do access token hết hạn, hoặc mọi `403` là lỗi login.

## 17. Failure handler của filter và hai constructors

Một chi tiết quan trọng của `ServerOAuth2AuthorizedClientExchangeFilterFunction` là **hành vi xử lý Resource Server authorization failures** có thể khác nhau theo cách khởi tạo.

### 17.1. Khi dùng repositories constructor

Khi tạo filter bằng:

```java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    reactiveClientRegistrationRepository,
    serverOAuth2AuthorizedClientRepository
);
```

các phiên bản Spring Security hỗ trợ thiết lập failure handler mặc định để chuyển những OAuth2 errors phù hợp (thường từ phản hồi HTTP 401/403 có `WWW-Authenticate` Bearer error) thành thao tác loại bỏ authorized client không còn nên tiếp tục dùng.

### 17.2. Khi dùng manager constructor

Khi tạo filter bằng:

```java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    reactiveOAuth2AuthorizedClientManager
);
```

**Không mặc định cùng một authorization failure handler đã được cài như repository constructor.** Nếu cần cơ chế xóa/invalidate authorized client trên Resource Server `invalid_token`, phải kiểm tra API và gắn handler phù hợp:

```java
oauth2.setAuthorizationFailureHandler(
    yourReactiveAuthorizationFailureHandler
);
```

Biến `yourReactiveAuthorizationFailureHandler` chỉ là placeholder. Trong code thật phải dùng implementation của `ReactiveOAuth2AuthorizationFailureHandler` thích hợp với repository/service đang quản lý token, và policy xóa được giới hạn theo đúng registration/principal.

### 17.3. Failure handler của manager khác filter failure handler

Phân biệt:

- **Manager failure handler:** xử lý lỗi lúc authorize/refresh tại Token Endpoint, ví dụ `invalid_grant`.
- **WebClient filter failure handler:** xử lý OAuth2 error mà Resource Server trả sau outbound API request.

Đừng thay manager handler bằng một custom logger vô tình bỏ cleanup `invalid_grant`. Cũng đừng để WebClient filter xóa refresh token đang hợp lệ với mọi HTTP 403 thiếu scope.

### 17.4. Không xóa token vô điều kiện trên 401/403

Có thể gặp:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Điều này khác:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Với `invalid_token`, có tình huống cần không dùng lại access token cũ. Với `insufficient_scope`, xóa authorized client thường không cấp thêm quyền. Chính sách handler cần dựa trên **OAuth2 error code**, source và security requirements.

Không gửi một POST/PUT có side effects lại vô hạn chỉ vì handler vừa làm mất token cũ; retry nghiệp vụ cần idempotency riêng.

## 18. `retrieve()`, `exchangeToMono()` và xử lý lỗi

`WebClient` cung cấp reactive responses:

```java
Mono<String> response = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
```

`retrieve()` mặc định biến HTTP 4xx/5xx thành exception phù hợp khi response được consume. Có thể xử lý domain error:

```java
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

Mono<String> reports = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class)
    .onErrorResume(WebClientResponseException.Unauthorized.class, ex ->
        Mono.error(new IllegalStateException(
            "Reports API did not accept the access token"
        ))
    );
```

Đây là mẫu biểu diễn lỗi, không phải production error policy. Không đưa raw `WWW-Authenticate` headers chứa dữ liệu bất thường hoặc full response body ra frontend.

Một cách khác là kiểm soát status trong `exchangeToMono(...)`:

```java
Mono<String> reports = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company"))
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(String.class);
        }
        if (response.statusCode().value() == 403) {
            return Mono.error(
                new IllegalStateException("Reports access denied")
            );
        }
        return response.createException().flatMap(Mono::error);
    });
```

Với reactive HTTP client, cần bảo đảm response body được consume/release theo cơ chế của Spring; `exchangeToMono` giúp quản lý lifecycle của body được trả từ handler.

### 18.1. Không làm mất thông tin authorization failure cần thiết

Nếu một tầng HTTP filter xử lý Bearer errors để loại token lỗi, nhưng ứng dụng tự rewrite toàn bộ 401/403 trước khi filter thấy response theo cách không phù hợp, cơ chế failure handling có thể không nhận được thông tin cần thiết. Cần hiểu thứ tự WebClient filter chain và API behavior của phiên bản đang dùng.

### 18.2. Timeout trong WebClient

```java
import java.time.Duration;

Mono<String> reports = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class)
    .timeout(Duration.ofSeconds(8));
```

`timeout` giúp giới hạn việc chờ của reactive chain; chưa thay thế toàn bộ connect/response timeout của HTTP connector. Đừng dùng `.block(Duration...)` trên Netty event-loop.

Với Token Endpoint refresh có rotation, timeout còn có rủi ro: Authorization Server có thể đã tiêu thụ refresh token trước khi response về Client. Không retry cùng refresh token vô hạn nếu không biết request trước đã thành công hay chưa.

## 19. WebClient chạy ngoài HTTP request: service-to-service

Một scheduled job hoặc queue consumer có thể không có `ServerWebExchange` của người dùng. Trong môi trường này, cách quản lý phù hợp thường là:

- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.
- `ReactiveOAuth2AuthorizedClientService`.
- `client_credentials` cho tác vụ đại diện cho chính ứng dụng.
- Principal service name **ổn định** để lưu/tìm authorized client.

### 19.1. Cấu hình một service-based manager

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
public class ServiceOAuth2ClientConfiguration {

    @Bean("serviceReactiveAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager serviceClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

### 19.2. YAML cho `client_credentials`

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-service:
            provider: reporting-as
            client-id: ${REPORTING_SERVICE_CLIENT_ID}
            client-secret: ${REPORTING_SERVICE_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [reports.read]
        provider:
          reporting-as:
            token-uri: https://login.example.test/oauth2/token
```

Grant này không cần user login, `openid`, OIDC ID Token hay browser callback. Nó cấp token cho Client theo chính sách AS. Không dùng nó để giả quyền một người dùng cụ thể.

### 19.3. Reactive service lấy token khi cần

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReportingServiceClient {

    private final ReactiveOAuth2AuthorizedClientManager manager;
    private final WebClient api;

    public ReportingServiceClient(
            @Qualifier("serviceReactiveAuthorizedClientManager")
            ReactiveOAuth2AuthorizedClientManager manager,
            WebClient.Builder builder) {
        this.manager = manager;
        this.api = builder
            .baseUrl("https://reports-api.example.test")
            .build();
    }

    public Mono<String> getDailyReports() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reporting-service")
                .principal("service:reporting-service")
                .build();

        return manager.authorize(request)
            .switchIfEmpty(Mono.error(
                new IllegalStateException("No authorized service client")
            ))
            .flatMap(client ->
                api.get()
                    .uri("/v1/daily")
                    .headers(headers ->
                        headers.setBearerAuth(
                            client.getAccessToken().getTokenValue()
                        )
                    )
                    .retrieve()
                    .bodyToMono(String.class)
            );
    }
}
```

Đây là ví dụ **lấy token từ manager trong một reactive chain**, không dùng Servlet/ServerWebExchange giả. Có thể tích hợp service manager với OAuth2 WebClient filter theo cơ chế phù hợp ở phiên bản của bạn, nhưng điều quan trọng là tránh buộc một background worker phải có Reactive web request context.

### 19.4. Principal name không phải danh tính user

`principal("service:reporting-service")` chỉ là khóa quản lý authorized client cho tác vụ. Nó không xác thực một người dùng hoặc trao quyền của user đó cho service.

Nếu job xử lý dữ liệu user-delegated, cần authorized client đã được user cấp theo authorization code và có cơ chế lưu/refresh phù hợp. Không chọn principal của user khác từ queue payload chưa được xác minh để đọc token họ đã cấp.

## 20. Multi-user và multi-tenant: không trộn token

Một Reactive OAuth2 client có thể có rất nhiều authorized clients:

```text
registration=company, principal=user-A -> access token A
registration=company, principal=user-B -> access token B
registration=calendar, principal=user-A -> access token C
registration=service-reporting, principal=service -> access token D
```

Không được để:

- User B chọn principal của user A.
- Tenant A truyền registration ID của tenant B khi không có quyền.
- Một WebClient global gửi access token D tới API không thuộc service-reporting.
- Controller nhìn thấy email trùng nhau rồi dùng authorized client của user khác.
- Cache key chỉ là `registrationId` mà không tính principal khi token thuộc người dùng.

Một khóa lưu thường mang ý nghĩa `(clientRegistrationId, principalName)`. Với multi-tenant, phải cân nhắc trust boundary tenant/issuer, ngay cả khi tên principal có thể trùng ở các nhà cung cấp khác nhau.

### 20.1. Dữ liệu thuộc người dùng nào?

Spring Security OAuth2 Client giải quyết **quyền cấp token**; service nghiệp vụ vẫn cần xác minh `account_id` và resource ownership. Token hợp lệ không chứng minh user A được đọc mọi report của user B.

### 20.2. Dùng issuer/subject cho OIDC identity mapping

Nếu application có nhiều OIDC providers, danh tính user ngoài thường nên được liên kết với tài khoản nội bộ bằng cặp **`(iss, sub)` đã xác minh**, không dùng email thay thế. Nhưng authorized client selection vẫn cần registration, principal và tenant rõ ràng; đừng chỉ dùng `sub` thô ở môi trường nhiều issuers.

## 21. Cẩn trọng khi dùng Reactor operators

### 21.1. `Mono` và `Flux` thường lazy

Đoạn này mới **tạo pipeline**, chưa chạy request:

```java
Mono<String> result = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
```

Khi framework subscribe vào publisher, pipeline mới được thực thi. Vì vậy:

- Không tự gọi `subscribe()` trong controller rồi trả response ngay.
- Không dùng `block()` trên event-loop.
- Nếu thực thi trong worker background, phải có orchestration subscription thích hợp với lifecycle/job.
- Bảo đảm authentication/exchange được truyền đúng qua Reactor context ở thời điểm thực thi.

### 21.2. Tránh mất security context khi tự tạo pipeline

Ví dụ sai về ý tưởng:

```java
// Không nên khởi tạo công việc nền rồi cho rằng
// nó vẫn có SecurityContext của HTTP request ban đầu.
somePublisher.subscribe();
```

Nếu tác vụ sống lâu hơn request, context cần được quản lý bằng một cơ chế nghiệp vụ/tin cậy riêng. Đừng serialize nguyên `Authentication` hoặc raw token vào message queue mà không kiểm soát bảo mật.

### 21.3. Cần giới hạn concurrency khi API/token endpoint có rate limit

`Flux.flatMap(...)` có thể kích hoạt nhiều outbound calls cùng lúc. Nếu mỗi call yêu cầu một authorized client sắp hết hạn, có thể phát sinh refresh concurrency.

Cân nhắc:

- Giới hạn concurrency theo user/registration.
- Tái sử dụng manager/storage đúng policy.
- Single-flight refresh cho các token có rotation nếu kiến trúc yêu cầu.
- HTTP connection pool/timeout.
- Retry/backoff có giới hạn.
- Không dùng shared mutable static token field.

## 22. Bảo mật khi gắn Bearer token

### 22.1. Chỉ gửi token tới Resource Server đã tin cậy

Access token dạng Bearer có thể cho phép người cầm token gọi API. Vì vậy:

- WebClient có base URL cố định cho đúng API.
- Chỉ cho request tạo relative path từ dữ liệu đã kiểm soát.
- Không sử dụng URL do user nhập để quyết định host nhận token.
- Kiểm soát redirects và forwarding của `Authorization`.
- Tách `publicWebClient` khỏi các OAuth2-enabled WebClients.
- Không log raw token hoặc URL chứa token.
- Giữ HTTPS và xác minh TLS certificate/hostname.

### 22.2. Header nào tuyệt đối không nên log?

```text
Authorization: Bearer <access_token>
Authorization: Basic <client_credentials>
access_token
refresh_token
id_token
client_secret
Authorization Code
session cookie
```

Một log an toàn hơn:

```text
event=reports_api_call
registrationId=company
downstreamService=reports-api
httpStatus=200
durationMs=140
tokenWasAttached=true
```

Không sử dụng token value làm correlation ID. Nếu cần theo dõi identity, dùng identifier nội bộ đã làm sạch theo chính sách dữ liệu.

### 22.3. Error response có thể chứa dữ liệu nhạy cảm

Một API có thể trả error body chứa path, subject, trace hoặc message riêng. Không chuyển nguyên error body từ downstream API ra frontend hoặc hệ thống analytics nếu không được phép.

### 22.4. CSRF và CORS không bị filter thay thế

OAuth2 filter gắn access token vào **outbound backend requests**. Nó không tự thay bảo vệ CSRF của endpoint browser-facing trong Spring Security, cũng không quyết định CORS policy của frontend.

OIDC Login vẫn cần state/PKCE/nonce theo flow, không thể coi việc WebClient gắn token làm các bước này không còn cần thiết.

## 23. Kiểm thử WebClient OAuth2 integration

### 23.1. Những gì cần kiểm tra

Một test có mock Authorization Server/Resource Server có thể xác minh:

1. Request chọn `clientRegistrationId("company")` nhận Bearer access token của registration đúng.
2. Request có explicit authorized client dùng credential đã chọn.
3. Request tới public HTTP client **không** gắn Bearer token.
4. Không bật default token ngoài ý muốn.
5. API trả `401 invalid_token` kích hoạt policy xử lý tương ứng.
6. API trả `403 insufficient_scope` không làm hệ thống retry vô hạn.
7. Khi token cần refresh, manager cập nhật authorized client nếu grant và provider cho phép.
8. Nếu refresh token bị thu hồi, lỗi `invalid_grant` được xử lý và không tái sử dụng token hỏng.
9. Hai users/tenants không truy cập nhầm authorized client của nhau.
10. Redirect tới host lạ không mang token qua.

### 23.2. Test với mock HTTP server

Có thể dùng `MockWebServer`, WireMock hoặc một stub server phù hợp để kiểm tra outbound `Authorization` header và response status.

Điều quan trọng là test **không in token thật**. Dùng access token giả, session/test security context và những giá trị scope/audience giả định.

### 23.3. Test authorization manager độc lập

Với `ReactiveOAuth2AuthorizedClientManager`, bạn có thể dùng một fake manager trả:

```java
Mono.just(mockAuthorizedClient)
```

hoặc:

```java
Mono.empty()
```

để kiểm tra service xử lý kết quả khi có/không có client. Nếu test cần kiểm tra refresh, stub Token Endpoint response hợp lệ và storage side effects; không chỉ mock mỗi WebClient call mà bỏ qua authorized-client lifecycle.

### 23.4. Đừng coi code snippet là test đã chạy

Những đoạn code trong bài nhằm mô tả API và thiết kế. Chúng cần được đặt vào project thực có dependency, ClientRegistration, security chain, test fixtures và phiên bản Spring Security phù hợp. Không suy luận rằng toàn bộ sample đã được build/test thành công chỉ từ việc nó xuất hiện trong tài liệu.

## 24. Bảng lỗi thường gặp và cách khoanh vùng

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| WebClient không gắn Bearer token | Thiếu `clientRegistrationId`/authorized client/default policy | Chọn authorized client tường minh |
| Không tìm được registration | `registrationId` sai hoặc repository khác config | So sánh YAML và Java |
| Không có authorized client của user | Chưa hoàn tất OAuth2 Login/consent hoặc storage/principal không khớp | Kiểm tra flow đăng nhập và kho lưu |
| API 401 dù login thành công | Access token sai audience, expired/revoked hoặc API config sai | Chẩn đoán Resource Server, không chỉ OIDC login |
| API 403 `insufficient_scope` | Scope/quyền không đủ | Xin đúng quyền/consent, không refresh vô hạn |
| Token Endpoint `invalid_grant` | Refresh token expired/rotated/revoked | Dọn state lỗi, reauthorize khi cần |
| `invalid_client` | Client credentials/phương thức xác thực sai | Kiểm tra registration và secret rotation |
| Dùng `Server...FilterFunction` trong Servlet MVC | Nhầm reactive với Servlet integration | Dùng Servlet variant hoặc đổi stack |
| Lỗi khi chạy scheduler | Không có `ServerWebExchange`/principal request | Service-based reactive manager, `client_credentials` |
| Token user A xuất hiện trong request user B | Sai principal/cache key/ownership | Phân vùng authorized client và kiểm tra account |
| Bearer token bị gửi tới public API | Bật `setDefaultOAuth2AuthorizedClient(true)` trên shared WebClient | Tách clients, explicit registration |
| Refresh xảy ra quá nhiều | Token TTL, principal thay đổi, storage/caching, concurrency | Kiểm tra manager/provider, principal key và metrics |
| Không lưu refresh token mới | Sai success handler/storage hoặc race | Cập nhật và đồng bộ authorized client |
| WebClient response bị xử lý nhưng flow không chạy | Publisher chưa được subscribe | Để Spring quản lý subscription, tránh `subscribe()` tùy tiện |
| `block()` gây lỗi ở Netty event loop | Blocking call trong WebFlux | Giữ reactive pipeline, dùng Mono/Flux |
| Filter không lấy được Authentication | Mất Reactor context hoặc chạy ngoài HTTP request | Truyền context đúng hoặc service manager |
| WebClient manager constructor không xóa token lỗi | Thiếu filter failure handler | Cấu hình failure handler phù hợp |
| Retry POST gây giao dịch trùng | Retry thiếu idempotency | Thêm idempotency strategy ở tầng nghiệp vụ |

### 24.1. Thứ tự debug đề xuất

1. **Xác định stack:** WebFlux/reactive hay Servlet/Spring MVC?
2. **Xác định ClientRegistration:** đúng ID, issuer, grant và scopes không?
3. **Xác định principal:** user đã login hay tác vụ service?
4. **Xác định cách chọn client:** attributes `clientRegistrationId` hay explicit authorized client?
5. **Xem authorized client storage:** dữ liệu có tồn tại cho principal/registration?
6. **Xem Token Endpoint:** có refresh attempt và `invalid_grant`/`invalid_client` không?
7. **Xem Resource Server:** 401, 403, Bearer error code, audience/scope?
8. **Xem host outbound:** có đúng API và không redirect sang host lạ?
9. **Kiểm tra Reactor context:** request có bị đẩy ra ngoài scope SecurityContext/exchange?
10. **Kiểm tra failure handler:** constructor/filter/manager có cleanup theo chính sách không?
11. **Kiểm tra concurrency:** nhiều calls có cùng refresh token bị xoay vòng không?
12. **Ghi log an toàn:** không đính kèm access token, refresh token hoặc callback code.

## 25. Các tình huống thực hành

### Bài tập 1: Chọn đúng lớp

Một ứng dụng WebFlux dùng `SecurityWebFilterChain` và `ServerHttpSecurity` muốn WebClient tự gắn OAuth2 access token.

**Gợi ý đáp án:** dùng `ServerOAuth2AuthorizedClientExchangeFilterFunction`, không dùng Servlet variant.

### Bài tập 2: ClientRegistration tường minh

Bạn có `reportsWebClient`. Hãy tạo request tới `/v1/reports` bằng registration `company`.

```java
Mono<String> result = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
```

### Bài tập 3: Người dùng có hai kết nối API

User có authorized clients `company` và `calendar`. Reports API cần token của `company`.

**Gợi ý đáp án:** truyền `clientRegistrationId("company")` hoặc đúng `OAuth2AuthorizedClient`, không phụ thuộc token mặc định.

### Bài tập 4: Shared WebClient bị lộ token

Một WebClient bật `setDefaultOAuth2AuthorizedClient(true)` rồi gọi một URL do browser gửi vào.

**Gợi ý đáp án:** có nguy cơ SSRF/token exfiltration. Tách WebClient, dùng API base URL/allowlist cố định và chọn token tường minh.

### Bài tập 5: Access token hết hạn nhưng có refresh token

**Gợi ý đáp án:** manager/provider cấu hình `refreshToken()` có thể thực hiện Refresh Token Grant và lưu token mới. Không tự gửi refresh request lặp ở mọi service.

### Bài tập 6: API 403 `insufficient_scope`

**Gợi ý đáp án:** cần đánh giá scope/consent của API; refresh cùng scope không tự tăng quyền, không retry vô hạn.

### Bài tập 7: Job `@Scheduled`

Job không có `ServerWebExchange`, cần gọi API bằng client credentials.

**Gợi ý đáp án:** dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` với `ReactiveOAuth2AuthorizedClientService` và service principal ổn định. Không giả tạo web request để lấy token.

### Bài tập 8: Explicit `OAuth2AuthorizedClient`

Controller đã nhận authorized client đáng tin qua annotation, muốn đưa vào WebClient.

```java
webClient.get()
    .uri("/v1/reports")
    .attributes(oauth2AuthorizedClient(client))
    .retrieve()
    .bodyToMono(String.class);
```

**Gợi ý:** bảo đảm client thuộc đúng registration/user và lifecycle phù hợp với việc refresh.

### Bài tập 9: Hai request refresh đồng thời

Request A và B đều dùng RT-1; A nhận RT-2, B bị `invalid_grant`.

**Gợi ý đáp án:** cần kiểm soát concurrency/rotation và token store, không retry RT-1 vô hạn.

### Bài tập 10: Reactive context

Service lấy `Authentication` bằng `SecurityContextHolder.getContext()` kiểu Servlet trong một Reactor chain, đôi khi thấy null.

**Gợi ý đáp án:** dùng cơ chế reactive security context hoặc truyền Authentication/ServerWebExchange phù hợp. Không phụ thuộc ThreadLocal Servlet trong WebFlux.

### Bài tập 11: API 401 sau callback

OIDC Login thành công nhưng Reports API trả `invalid_token`.

**Gợi ý đáp án:** xác minh access token đã được cấp cho đúng audience/scope/resource và còn hợp lệ; ID Token validation thành công không đủ để đảm bảo access token hợp lệ với mọi API.

### Bài tập 12: Không có refresh token

Token response có `access_token` nhưng không có `refresh_token`.

**Gợi ý đáp án:** tùy provider/consent/grant, refresh token có thể không được cấp. Đừng cho rằng bật `.refreshToken()` trong manager là đủ; cần user authorization mới khi quyền hết hiệu lực và provider yêu cầu.

## 26. Checklist khi triển khai production

- [ ] Dự án thực sự chạy **WebFlux Reactive Security** khi dùng Server OAuth2 filter.
- [ ] `SecurityWebFilterChain` và `oauth2Login` / `oauth2Client` được cấu hình phù hợp.
- [ ] ClientRegistration/issuer/Token Endpoint được khai báo từ provider đáng tin.
- [ ] Access token được cấp cho đúng Resource Server và có scope/audience cần thiết.
- [ ] WebClient chọn registration hoặc authorized client **tường minh**.
- [ ] Không bật default authorized client trên shared WebClient gọi nhiều hosts.
- [ ] HTTP host/URL/redirect được kiểm soát, không gửi Bearer token tới untrusted origin.
- [ ] `ReactiveOAuth2AuthorizedClientManager`/repository lưu và tìm token theo đúng principal.
- [ ] Với custom manager constructor, đã xem xét filter failure handler theo version.
- [ ] Token Endpoint `invalid_grant` được phân biệt với Resource Server 401/403.
- [ ] Refresh token rotation và concurrency có policy phù hợp nhiều instances.
- [ ] Background job dùng service-based manager thay vì giả `ServerWebExchange`.
- [ ] Reactor context/Authentication được truyền đúng khi chạy async.
- [ ] Không dùng `block()` trên event-loop hoặc `subscribe()` tùy tiện.
- [ ] Có timeout, retry/backoff giới hạn và idempotency cho side-effecting requests.
- [ ] Không đưa token, code, client secret, cookie vào URL/log/frontend response.
- [ ] Có kiểm thử multi-user, multi-registration, public API, token expiry và failure paths.

## 27. Tài liệu tham khảo chính thức

1. [Spring Security API — ServerOAuth2AuthorizedClientExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html): constructors, attributes, default client và failure handler.
2. [Spring Security Reference — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): tổng quan OAuth2 Client trong WebFlux.
3. [Spring Security Reference — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html): cách người dùng đăng nhập qua OAuth2/OIDC trên reactive stack.
4. [Spring Security Reference — Authorized Clients](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html): quản lý authorized clients và các tích hợp WebClient.
5. [Spring Security API — ReactiveOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientManager.html): contract authorize reactive.
6. [Spring Security API — DefaultReactiveOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/DefaultReactiveOAuth2AuthorizedClientManager.html): manager dùng với reactive web requests.
7. [Spring Security API — AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager.html): manager cho service tier không có ServerWebExchange.
8. [Spring Security API — ReactiveOAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientProviderBuilder.html): cấu hình các grant providers.
9. [Spring Security API — ServerOAuth2AuthorizedClientRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/server/ServerOAuth2AuthorizedClientRepository.html): kho authorized clients theo ServerWebExchange.
10. [Spring Security API — OAuth2AuthorizedClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html): ClientRegistration, principal và tokens.
11. [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): `ExchangeFilterFunction`, Reactor pipelines và HTTP response handling.
12. [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): authorization code, refresh token và các loại grant.
13. [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer`, `invalid_token` và `insufficient_scope`.
14. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): nguyên tắc bảo mật OAuth2 và refresh token.

## 28. Tổng kết

**`ServerOAuth2AuthorizedClientExchangeFilterFunction` là cầu nối giữa `WebClient` và hạ tầng OAuth2 Client trong Spring Security Reactive.** Filter có thể chọn authorized client, phối hợp với `ReactiveOAuth2AuthorizedClientManager`/repository để tìm hoặc tái cấp token khi phù hợp, rồi gắn access token vào outbound `Authorization: Bearer` request.

Để sử dụng an toàn, hãy **chọn rõ ClientRegistration hoặc OAuth2AuthorizedClient**, giữ **principal đúng user/tenant**, giới hạn HTTP destinations, phân biệt lỗi **Token Endpoint** với **Resource Server** và hiểu sự khác biệt về failure handler của các constructors. Đừng bật default authorized client cho WebClient dùng chung nhiều host, đừng dùng ID Token thay access token, và đừng giả định job ngoài HTTP request có sẵn Reactive SecurityContext.

Với những ranh giới này, WebFlux có thể gọi API OAuth2 theo cách non-blocking, quản lý vòng đời token nhất quán và giảm nguy cơ lộ credential hoặc sử dụng nhầm quyền giữa các người dùng, nhà cung cấp và tài nguyên.
