# 30.4. mockOAuth2Client() cho lời gọi dùng authorized client

Trong ứng dụng **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client** dùng **Spring WebFlux**, việc một request đã được xác thực và việc ứng dụng có **access token được ủy quyền để gọi API khác** là hai vấn đề liên quan nhưng khác nhau. Một controller có thể đang phục vụ user đã đăng nhập bằng OIDC, đồng thời cần `OAuth2AuthorizedClient` của registration `reports-api` để gắn bearer token vào `WebClient`. Một background hoặc BFF flow khác có thể dùng `client_credentials`, không cần người dùng đăng nhập tương tác.

Khi kiểm thử WebFlux controller có tham số `@RegisteredOAuth2AuthorizedClient`, ta **không cần chạy một OpenID Provider thật, mô phỏng trang consent, đổi authorization code rồi lưu token** chỉ để làm cho controller nhận được một authorized client. Spring Security Test cung cấp **`SecurityMockServerConfigurers.mockOAuth2Client()`** cho `WebTestClient`: mutator này cung cấp một `OAuth2AuthorizedClient` giả trong ngữ cảnh trao đổi request, qua cơ chế `ServerOAuth2AuthorizedClientRepository` của test.

Ví dụ cốt lõi:

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOAuth2Client;

webTestClient
        .mutateWith(mockOAuth2Client("reports-api"))
        .get()
        .uri("/reports")
        .exchange();
```

Tuy nhiên, cần phân biệt rõ **“đã có authorized client”** với **“đã authenticated”** và với **“downstream API thật đã cho phép truy cập”**. `mockOAuth2Client()` chỉ là công cụ tạo trạng thái test; token giả của nó **không phải token được OP ký và không được kiểm tra tại Authorization Server**.

> **Nguyên tắc:** Sử dụng `mockOAuth2Client()` khi mục tiêu là kiểm thử code **tiêu thụ một authorized client đã có**. Dùng `mockOidcLogin()`/`mockOAuth2Login()` để kiểm thử **authenticated principal**. Nếu cần chứng minh `Authorization: Bearer ...` được gửi sang API, phải kiểm soát/quan sát **outbound WebClient**. Nếu cần kiểm chứng OAuth2 grant, refresh hoặc OP discovery/ID Token validation, phải có lớp test khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `ClientRegistration`, `OAuth2AuthorizedClient`, `OAuth2AccessToken`, `Authentication` và nơi lưu authorized client trong WebFlux.
2. Dùng `WebTestClient.mutateWith(mockOAuth2Client("registration-id"))` để giả lập client đã được ủy quyền.
3. Biết dữ liệu mặc định và cách thay `accessToken(...)`, `principalName(...)`, `clientRegistration(...)`.
4. Kiểm thử controller sử dụng `@RegisteredOAuth2AuthorizedClient("...")`.
5. Kết hợp authorized client với `mockOidcLogin()` hoặc `mockOAuth2Login()` khi endpoint yêu cầu authenticated user.
6. Phân biệt `mockOAuth2Client()` với `mockJwt()` dành cho inbound Resource Server authentication.
7. Kiểm thử `ServerOAuth2AuthorizedClientExchangeFilterFunction` và helper `oauth2AuthorizedClient(...)` bằng một downstream HTTP stub.
8. Kiểm tra đúng bearer token, scope, registration ID, principal name và hành vi với nhiều registrations.
9. Giới hạn phạm vi mock: không khẳng định token endpoint/refresh/revocation/JWT signature được kiểm tra.
10. Khắc phục các lỗi test WebFlux do thiếu `springSecurity()`, sai repository, sai principal hoặc nhầm mock với real HTTP integration.

## 2. Bài toán mẫu: Portal gọi Reports API

Giả sử Reports Portal có endpoint:

```text
GET /reports/summary
```

Để lấy báo cáo, backend gọi:

```text
GET https://reports-api.example.org/summary
Authorization: Bearer <access-token>
```

Trong ứng dụng thật, access token nằm trong `OAuth2AuthorizedClient` được Spring Security quản lý theo registration ID và principal; nó có thể đến từ authorization code login, client credentials hoặc token refresh.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant SEC as Spring Security WebFlux
    participant C as ReportsController
    participant R as ServerOAuth2AuthorizedClientRepository
    participant W as OAuth2 WebClient Filter
    participant API as Reports API
    B->>SEC: GET /reports/summary (session cookie)
    SEC->>C: Authenticated request context
    C->>R: Resolve authorizedClient("reports-api")
    R-->>C: OAuth2AuthorizedClient + access token
    C->>W: WebClient request với oauth2AuthorizedClient(client)
    W->>API: GET /summary, Authorization: Bearer token
    API-->>W: 200 JSON
    W-->>C: Response body
    C-->>B: 200 JSON/report
```

Với `mockOAuth2Client()`, test **đi thẳng vào điểm đã có authorized client**:

```mermaid
flowchart TD
    T["WebTestClient"] --> M["mutateWith(mockOAuth2Client)"]
    M --> S["Mock ServerWebExchange / test session"]
    S --> AR["Test ServerOAuth2AuthorizedClientRepository"]
    AR --> P["Controller @RegisteredOAuth2AuthorizedClient"]
    P --> F["OAuth2 WebClient filter"]
    F --> X["HTTP stub thay Reports API"]
    X --> A["Assert: đúng bearer, scope, response"]
```

Không có bước login tương tác với OP hoặc xin token thật, trừ khi bản thân application/test configuration cố ý kích hoạt thêm flow khác.

## 3. Phân biệt các object trong OAuth2 Client

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| `ClientRegistration` | `reports-api` | Cấu hình client: registration ID, client ID, grant, endpoints, scopes |
| `OAuth2AccessToken` | `test-reports-token` | Access token và metadata: token type, issuedAt, expiresAt, scopes |
| `OAuth2AuthorizedClient` | Registration + principalName + access token | Trạng thái một client đã được authorize để ứng dụng gọi tài nguyên |
| `Authentication` | `OAuth2AuthenticationToken` / authenticated principal | Cho biết request user nào được xác thực trong SecurityContext |
| `ServerOAuth2AuthorizedClientRepository` | WebSession-based repository | Lưu/đọc authorized client gắn với server exchange |
| `ReactiveOAuth2AuthorizedClientService` | In-memory/JDBC/custom reactive store | Dịch vụ lưu authorized client ở tầng backend |
| `ReactiveOAuth2AuthorizedClientManager` | Manager/provider chain | Authorize/re-authorize; có thể dùng cache hoặc token endpoint |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Filter của `WebClient` | Gắn bearer token của client phù hợp vào outbound request |

### 3.1. Client registration khác authorized client

`ClientRegistration` chỉ là **cấu hình**:

```text
registrationId = reports-api
clientId       = reports-portal
grant          = authorization_code
tokenUri       = https://idp.example.org/oauth2/token
```

`OAuth2AuthorizedClient` là **trạng thái sau khi đã có token**:

```text
clientRegistration  = reports-api
principalName       = user
accessToken         = test-reports-token
accessToken.scopes  = [reports.read]
```

Có registration không đồng nghĩa token đã được cấp. `mockOAuth2Client()` giúp test tạo sẵn authorized client mà không phải đi qua grant.

### 3.2. Authorized client không phải SecurityContext

`SecurityContext` chứa `Authentication` của request; authorized client chứa token để ứng dụng gọi API.

```text
SecurityContext:
  Authentication.principal.name = user
  authorities = [ROLE_USER]

AuthorizedClientRepository:
  (reports-api, user)
    accessToken = test-reports-token
```

User có thể đã authenticated nhưng **chưa cấp access token cho registration `reports-api`**. Ngược lại, backend có thể có service authorized client từ `client_credentials` dù request không có browser-authenticated user.

### 3.3. Registration ID khác OAuth2 client ID

`registrationId` trong test, ví dụ `reports-api`, là khóa Spring Security; còn `clientId` có thể là `reports-portal-web` do Authorization Server cấp. Không dùng `clientId` thay `registrationId` trong annotation `@RegisteredOAuth2AuthorizedClient("...")`.

### 3.4. Principal name là một phần của lookup

Authorized client thường được xác định bởi **registration ID + principal name**, tùy repository/service implementation. Vì thế test phải chú ý:

```text
(reports-api, user)   != (reports-api, alice)
(reports-api, alice)  != (inventory-api, alice)
```

Nếu mock principal là `user` nhưng controller/manager tìm token theo `alice`, lookup có thể không thấy client hoặc cố khởi động authorization flow. `principalName("...")` giúp kiểm tra ranh giới này.

## 4. mockOAuth2Client() thực sự làm gì?

Spring Security Test có các overloads:

```java
mockOAuth2Client()
mockOAuth2Client("reports-api")
```

Cả hai trả về `SecurityMockServerConfigurers.OAuth2ClientMutator`, một configurer cho `WebTestClient`. Mutator hỗ trợ:

```java
.accessToken(OAuth2AccessToken token)
.principalName(String principalName)
.clientRegistration(ClientRegistration registration)
.clientRegistration(Consumer<ClientRegistration.Builder> configurer)
```

Nó cung cấp một `OAuth2AuthorizedClient` **trong test ServerWebExchange**, thông qua `ServerOAuth2AuthorizedClientRepository` mà Spring Security Test sử dụng, để code resolve client như khi client đã được lưu ở session. Giá trị token có tính **khai báo**: không cần là JWT hợp lệ hoặc được Authorization Server chấp nhận.

### 4.1. Dữ liệu mặc định

Theo tài liệu Spring Security Test, fixture mặc định cung cấp các dữ liệu cơ bản:

| Thuộc tính | Giá trị minh họa mặc định được tài liệu mô tả |
|---|---|
| `ClientRegistration.clientId` | `test-client` |
| `ClientRegistration.clientSecret` | `test-secret` |
| `OAuth2AuthorizedClient.principalName` | `user` |
| `OAuth2AccessToken.scopes` | `read` |
| `registrationId` | Theo overload/tham số được chọn |

Không dựa vào fake `test-secret` để kiểm bảo mật secret. Và không dựa vào token string mặc định khi kiểm header quan trọng: **đặt token cố định có chủ đích trong test** để assertion dễ hiểu.

### 4.2. Những điều mutator không làm

`mockOAuth2Client()` **không**:

- Gọi Authorization Server để xin token.
- Chạy authorization code + PKCE + state + nonce.
- Xác minh chữ ký JWT/ID Token.
- Tạo authenticated `OidcUser` cho mọi trường hợp.
- Tự biến token test thành token được downstream API thật tin cậy.
- Chứng minh token refresh/revocation hoặc exception handling của provider.
- Mock sẵn response JSON của Reports API.
- Bảo đảm application đang dùng đúng production `ReactiveOAuth2AuthorizedClientService`.

Hãy chọn lớp kiểm thử khác cho những hợp đồng này.

## 5. So sánh các mutators liên quan

| Mutator | Thứ được mô phỏng | Nên dùng khi |
|---|---|---|
| `mockUser()` | Authentication kiểu user/password trong reactive SecurityContext | Endpoint chỉ cần principal/roles |
| `mockOAuth2Login()` | `OAuth2AuthenticationToken` và OAuth2User; hỗ trợ authorized client cùng flow | Test OAuth2 Login user |
| `mockOidcLogin()` | `OAuth2AuthenticationToken` và OidcUser/ID Token giả | Test OIDC Login principal/claims |
| **`mockOAuth2Client()`** | **`OAuth2AuthorizedClient` trong test repository/session** | **Test code dùng authorized client, bất kể user login bằng cách nào** |
| `mockJwt()` | `JwtAuthenticationToken` cho **inbound bearer token** | Test Resource Server JWT authentication |
| `mockOpaqueToken()` | `BearerTokenAuthentication` cho inbound opaque token | Test Resource Server opaque token |

### 5.1. Ví dụ phân biệt

```text
Controller cần @AuthenticationPrincipal OidcUser
    -> mockOidcLogin()

Controller cần @RegisteredOAuth2AuthorizedClient("reports-api")
    -> mockOAuth2Client("reports-api")

Controller cần cả OidcUser và reports-api token
    -> mockOidcLogin() + mockOAuth2Client("reports-api")

Inbound API bảo vệ bằng Authorization: Bearer JWT
    -> mockJwt()
```

`mockJwt()` chứng minh Resource Server chấp nhận một `JwtAuthenticationToken` giả trong test; nó không tự cung cấp `OAuth2AuthorizedClient` để outbound `WebClient` gọi API.

### 5.2. mockOidcLogin có thể đi kèm authorized client

Trong Spring Security Test, `mockOidcLogin()` và `mockOAuth2Login()` cũng có thể chuẩn bị authorized client gắn với login registration, tùy cấu hình mutator. Nhưng nếu controller cần **một registration khác** (ví dụ user login bằng `company-login` rồi gọi API bằng `reports-api`), vẫn nên khai báo rõ `mockOAuth2Client("reports-api")` để test đúng client mục tiêu.

Đừng dựa vào việc một fixture login ngẫu nhiên có đúng scopes/registration ID mà service đang cần.

## 6. Dependencies cho kiểm thử WebFlux

Ví dụ Maven:

```xml
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
```

Nếu dùng Gradle, dependencies tương ứng:

```gradle
implementation 'org.springframework.boot:spring-boot-starter-webflux'
implementation 'org.springframework.boot:spring-boot-starter-security'
implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.security:spring-security-test'
```

Thông thường để Spring Boot quản lý version của Spring Security/Spring Test theo BOM. Không trộn tùy tiện `spring-security-test` khác major với Spring Security runtime vì các API test có thể không tương thích.

### 6.1. Import chính xác

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOAuth2Client;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOAuth2Login;
```

Package này là **Reactive test hỗ trợ WebTestClient**. Không nhập nhầm class có tên gần giống trong `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors`, vốn dành cho Servlet/MockMvc.

## 7. Cấu hình WebTestClient với Spring Security

Với test gắn trực tiếp vào `ApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

class ReactiveReportTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }
}
```

Đây là **phần setup** trong một test có Spring Test Context tương ứng (`@SpringBootTest`/`@WebFluxTest` + các beans cần thiết). `springSecurity()` bổ sung Spring Security test support vào WebTestClient mock-server binding, giúp mutators như `mockOAuth2Client()` được nhận diện.

### 7.1. Không nhầm với WebTestClient kết nối tới server thật

`mockOAuth2Client()` được thiết kế để biến đổi **mock `ServerWebExchange`**, không phải để đẩy một authorized client vào session của một server đang chạy qua TCP. Nếu dùng:

```java
WebTestClient.bindToServer().baseUrl("http://localhost:8080")
```

thì mutator có thể không hoạt động hoặc báo không hỗ trợ vì không có mock server filter context. Để test live server, hãy dùng cookie/session/identity setup được hỗ trợ hoặc test provider riêng; không coi `mutateWith` là endpoint “thêm token” cho server thật.

### 7.2. Auto-configured WebTestClient

Một Spring Boot test có thể inject `WebTestClient` đã được cấu hình với security test support theo test slice/auto-configuration. Nhưng không giả định mọi `WebTestClient` lấy từ `bindToController` hoặc custom builder tự có mutator plumbing. Nếu thấy `mockOAuth2Client` không phát huy tác dụng, hãy kiểm **binding strategy và `springSecurity()` setup** trước khi thay code business.

### 7.3. Test context cần đúng reactive stack

Nếu project có cả MVC và WebFlux starters, Spring Boot có thể chọn Servlet application mode theo defaults. Với bài này, cần **WebFlux ServerHttpSecurity + SecurityWebFilterChain**, không phải Servlet `HttpSecurity + SecurityFilterChain`.

## 8. Controller minh họa đọc authorized client

Đầu tiên viết một endpoint nhỏ để quan sát đúng object đã được inject, **không trả token về browser**.

```java
import java.util.Set;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation
        .RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

record ClientSummary(
        String registrationId,
        String principalName,
        Set<String> scopes) {}

@RestController
class AuthorizedClientProbeController {

    @GetMapping("/internal/client-summary")
    Mono<ClientSummary> summary(
            @RegisteredOAuth2AuthorizedClient("reports-api")
            OAuth2AuthorizedClient authorizedClient) {

        return Mono.just(new ClientSummary(
                authorizedClient.getClientRegistration()
                        .getRegistrationId(),
                authorizedClient.getPrincipalName(),
                authorizedClient.getAccessToken().getScopes()));
    }
}
```

**Chỉ dùng endpoint này cho test hoặc nội bộ được bảo vệ.** Nó không trả token string, nhưng principal và scopes cũng có thể là thông tin nhạy cảm. Production thường không cần expose dữ liệu này.

Điểm cần hiểu:

- Annotation `@RegisteredOAuth2AuthorizedClient("reports-api")` yêu cầu Spring Security resolve authorized client với registration ID đó.
- Tham số là `OAuth2AuthorizedClient`, không phải `Authentication`.
- Client có thể được lấy từ test repository khi dùng mutator.
- Trả `Mono<ClientSummary>` phù hợp WebFlux, không cần `block()`.

### 8.1. Test đơn giản nhất

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOAuth2Client;

class AuthorizedClientProbeTest {

    @Autowired
    WebTestClient client; // Được setup với reactive security test support.

    @Test
    void resolvesMockAuthorizedClient() {
        client.mutateWith(mockOAuth2Client("reports-api"))
                .get()
                .uri("/internal/client-summary")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.registrationId").isEqualTo("reports-api")
                .jsonPath("$.principalName").isEqualTo("user")
                .jsonPath("$.scopes[0]").isEqualTo("read");
    }
}
```

Đây là **snippet minh họa** trong test context có controller/configuration và endpoint được phép truy cập. Nếu application yêu cầu authenticated request, `mockOAuth2Client()` **một mình không tự tạo Authentication**; test sẽ cần thêm `mockOidcLogin()`/`mockOAuth2Login()` hoặc một Authentication phù hợp như mục tiếp theo.

## 9. Endpoint protected: kết hợp mockOidcLogin() với mockOAuth2Client()

Trong Portal thực tế, `/reports/summary` thường yêu cầu user đã đăng nhập.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/login", "/error")
                        .permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(oauth2 -> {})
                .build();
    }
}
```

Ví dụ một test:

```java
import org.junit.jupiter.api.Test;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOAuth2Client;

@Test
void authenticatedOidcUserCanResolveReportsClient() {
    client
        .mutateWith(mockOidcLogin())
        .mutateWith(mockOAuth2Client("reports-api"))
        .get().uri("/internal/client-summary")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.registrationId").isEqualTo("reports-api");
}
```

Mục tiêu của hai mutators:

```text
mockOidcLogin():
    Reactive SecurityContext -> OidcUser/Authentication giả

mockOAuth2Client("reports-api"):
    Authorized Client Repository -> reports-api token giả
```

Khi hai phần tồn tại trong cùng request test, controller vừa qua được authorization policy `authenticated()`, vừa nhận authorized client đúng registration.

### 9.1. Principal phải khớp trong trường hợp repository yêu cầu

Mặc định test helper có principal name `user`. Nếu tự đặt OIDC subject thành `alice` nhưng `mockOAuth2Client()` vẫn để `user`, tùy lookup flow bạn có thể thấy khác biệt.

Ví dụ:

```java
.mutateWith(mockOAuth2Client("reports-api")
        .principalName("alice"))
```

Chỉ chọn `alice` nếu Authentication được dùng trong test cũng đại diện `alice` theo hợp đồng. Không cố sửa principal string ngẫu nhiên để test “xanh” mà không hiểu quyền sở hữu token.

### 9.2. Test không có login nhưng có authorized client

Một client credentials service thường không có interactive OIDC user. `mockOAuth2Client` vẫn có thể dùng khi endpoint/service đã được phép tiếp cận token bằng cơ chế authentication khác. Nhưng nếu security policy yêu cầu `authenticated()`, request **vẫn phải có một Authentication hợp lệ** hoặc được cho phép bởi matcher. Đó là **security của endpoint**, độc lập việc token có sẵn cho outbound API.

Không tự disable `authorizeExchange(...)` toàn bộ ứng dụng chỉ để giải quyết test thiếu authenticated principal.

## 10. Tùy chỉnh access token và scopes

Với business logic kiểm scope `reports.read`:

```java
import java.time.Instant;
import java.util.Set;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

OAuth2AccessToken reportsToken = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "test-reports-token",
        Instant.now().minusSeconds(30),
        Instant.now().plusSeconds(3600),
        Set.of("reports.read"));
```

Sử dụng:

```java
client.mutateWith(mockOidcLogin())
      .mutateWith(mockOAuth2Client("reports-api")
              .accessToken(reportsToken))
      .get().uri("/internal/client-summary")
      .exchange()
      .expectStatus().isOk()
      .expectBody()
      .jsonPath("$.scopes[0]").isEqualTo("reports.read");
```

Điểm quan trọng:

- `tokenValue` là chuỗi fixture, không phải token JWT thật.
- `issuedAt` và `expiresAt` là thời gian test có chủ đích.
- `scopes` là metadata mà application có thể kiểm tra.
- Việc token test có scope `reports.read` **không chứng minh API thật sẽ công nhận scope**.

### 10.1. Scope là dữ liệu của access token

Một user có `ROLE_USER` trong Authentication không có nghĩa access token có `reports.read`. Ngược lại, access token có `reports.read` không tự cấp cho browser user quyền xem mọi báo cáo; controller/Resource Server vẫn phải kiểm object-level authorization.

```text
Authentication.authorities:
  ROLE_USER

AuthorizedClient.accessToken.scopes:
  reports.read
```

Khi test hai thứ, chuẩn bị dữ liệu tách biệt và assert đúng policy layer.

### 10.2. Test thiếu scope

Giả sử controller có:

```java
if (!authorizedClient.getAccessToken()
        .getScopes().contains("reports.read")) {
    return Mono.error(
            new ResponseStatusException(
                    HttpStatus.FORBIDDEN,
                    "Required scope missing"));
}
```

Test:

```java
OAuth2AccessToken insufficientToken = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "test-no-reports-scope",
        Instant.now().minusSeconds(10),
        Instant.now().plusSeconds(3600),
        Set.of("profile"));

client
    .mutateWith(mockOidcLogin())
    .mutateWith(mockOAuth2Client("reports-api")
            .accessToken(insufficientToken))
    .get().uri("/reports/summary")
    .exchange()
    .expectStatus().isForbidden();
```

HTTP 403 là kỳ vọng **nếu chính ứng dụng có rule kiểm scope như trên**. `mockOAuth2Client()` không tự chặn request vì thiếu `reports.read`; test phải kiểm business validation thực sự có trong controller/service.

### 10.3. Scope không phải authority tự động của principal

Mutator đặt scopes trên `OAuth2AccessToken`. Nó không bảo đảm principal trong `ReactiveSecurityContextHolder` được cấp `SCOPE_reports.read` như khi có một inbound Resource Server JWT.

Nếu method security có:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
```

thì đó là kiểm authorities của `Authentication`, không trực tiếp đọc scopes trong `OAuth2AuthorizedClient`. Test phải cấu hình Authentication/authorities tương ứng hoặc thay policy cho đúng requirement.

## 11. Tùy chỉnh principalName()

`OAuth2AuthorizedClient.getPrincipalName()` mô tả resource owner/service principal mà client được liên kết:

```java
client.mutateWith(mockOAuth2Client("reports-api")
        .principalName("service:report-sync"))
      .get().uri("/internal/client-summary")
      .exchange();
```

Trường hợp này mô phỏng authorized client của một service task, không nhất thiết human OIDC Login.

### 11.1. Các key phải thống nhất

```text
Authorized Client:
  registrationId = reports-api
  principalName  = alice

Authentication:
  name           = alice
```

Nếu code tìm authorized client theo `(reports-api, bob)`, nó không được nhận token của Alice. Đây là bất biến quan trọng trong ứng dụng có nhiều người dùng hoặc service identities.

### 11.2. Không dùng tên người dùng do request tự khai

Một anti-pattern nguy hiểm:

```java
String principal = exchange.getRequest()
        .getQueryParams().getFirst("user");
// Sau đó load authorized client cho principal này.
```

Người dùng có thể sửa `?user=alice` thành `?user=bob`. Trong ứng dụng thực, principal phải đến từ Authentication do server tin cậy hoặc từ danh tính service được quản lý, không từ query/header browser tùy ý.

Test với `principalName("alice")` chỉ xác nhận application xử lý một fixture; muốn chống cross-user token leakage phải có negative tests với user B/registration khác.

## 12. Tùy chỉnh ClientRegistration

Mutator cho phép override registration với builder consumer:

```java
client
    .mutateWith(mockOAuth2Client("reports-api")
        .clientRegistration(builder -> builder
            .clientId("reports-web-test")
            .clientName("Reports API Test Client")))
    .get().uri("/internal/client-summary")
    .exchange();
```

Ở đây builder bắt đầu từ cấu hình mặc định của test mutator rồi chỉnh các field được hỗ trợ. Các phương thức cụ thể của `ClientRegistration.Builder` tùy version và loại registration. `clientName` chỉ là nhãn metadata, không tự thay token audience hoặc quyền user.

### 12.1. Dùng một ClientRegistration đầy đủ

Khi test cần redirect URI, grant type, scopes, token URI hoặc provider metadata cụ thể, tạo registration tường minh:

```java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

ClientRegistration reportsRegistration =
        ClientRegistration.withRegistrationId("reports-api")
                .clientId("reports-web-test")
                .clientSecret("test-only-not-real-secret")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .authorizationUri(
                        "https://idp.example.invalid/authorize")
                .tokenUri(
                        "https://idp.example.invalid/token")
                .scope("openid", "reports.read")
                .build();

client.mutateWith(mockOAuth2Client()
        .clientRegistration(reportsRegistration))
      .get().uri("/internal/client-summary")
      .exchange();
```

Những URI thuộc `example.invalid` là placeholder không dùng cho network; test `mockOAuth2Client` không phải thực hiện authorization code flow. Nếu code test vô tình gọi token endpoint, cần mock HTTP layer tương ứng thay vì đổi URI sang provider thật.

### 12.2. Lấy ClientRegistration từ Reactive repository

Spring Security docs đưa ra pattern:

```java
@Autowired
ReactiveClientRegistrationRepository registrations;

// Trong test setup (không phải WebFlux request handler):
ClientRegistration registration =
        registrations.findByRegistrationId("reports-api").block();

client.mutateWith(mockOAuth2Client()
        .clientRegistration(registration))
      .get().uri("/reports/summary")
      .exchange();
```

`block()` ở đây chạy **trong code test setup** để lấy fixture, không phải trong Reactive controller/filter đang phục vụ request. Trong production reactive path nên compose `Mono` thay vì gọi `block()`.

Nếu `findByRegistrationId(...)` trả empty, test phải báo thiếu configuration rõ ràng, không im lặng tạo registration sai.

### 12.3. Test không cần client secret production

Test được phép dùng một chuỗi fake như `test-only-not-real-secret`. Không load secrets production chỉ để cho `mockOAuth2Client()` hoạt động. Token fixture và client registration ở đây chỉ là dữ liệu test.

## 13. WebClient: truyền authorized client vào outbound request

Trong WebFlux, `ServerOAuth2AuthorizedClientExchangeFilterFunction` có thể dùng `OAuth2AuthorizedClient` được truyền qua request attributes:

```java
import static org.springframework.security.oauth2.client.web.reactive
        .function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction
        .oauth2AuthorizedClient;

@GetMapping("/reports/summary")
Mono<String> getReport(
        @RegisteredOAuth2AuthorizedClient("reports-api")
        OAuth2AuthorizedClient authorizedClient) {

    return reportsWebClient
            .get()
            .uri("/summary")
            .attributes(oauth2AuthorizedClient(authorizedClient))
            .retrieve()
            .bodyToMono(String.class);
}
```

### 13.1. Filter phải có trên WebClient

`oauth2AuthorizedClient(authorizedClient)` đặt một attribute để OAuth2 WebClient filter sử dụng. Nếu `reportsWebClient` không gắn `ServerOAuth2AuthorizedClientExchangeFilterFunction`, một WebClient thông thường **không tự đọc attribute đó và không tự thêm Authorization header**.

Ví dụ cấu hình:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive
        .function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
WebClient reportsWebClient(
        ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {

    var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
            authorizedClientManager);

    return WebClient.builder()
            .baseUrl("https://reports-api.example.org")
            .filter(oauth2)
            .build();
}
```

Đây là mã minh họa cấu hình Reactive OAuth2 WebClient. Tùy Spring Security version, nếu cần xử lý 401/403 để xóa authorized client cũ, bạn còn phải cấu hình `ReactiveOAuth2AuthorizationFailureHandler` phù hợp; không suy luận rằng manager constructor sẽ tự có mọi cleanup behavior.

### 13.2. Vì sao dùng explicit authorized client?

Với:

```java
.attributes(oauth2AuthorizedClient(authorizedClient))
```

controller thể hiện rõ **token nào được chọn cho request nào**. Điều này thường an toàn hơn bật:

```java
oauth2.setDefaultOAuth2AuthorizedClient(true);
```

rồi để mọi outbound request trên cùng WebClient nhận token mặc định của authenticated user. Token có thể rò sang API không phải audience/đích được phép nếu client được tái sử dụng tùy tiện.

### 13.3. Mốc kiểm thử

`mockOAuth2Client()` chứng minh controller **lấy được object**. Để chứng minh token được truyền tới API, còn phải quan sát:

```http
GET /summary HTTP/1.1
Host: reports-api.example.org
Authorization: Bearer test-reports-token
```

Không test bằng cách trả access token ra browser. Hãy dùng HTTP stub/ExchangeFunction test double ở **đầu outbound**, không gửi request tới API production.

## 14. Kiểm thử outgoing Bearer header bằng ExchangeFunction stub

`ExchangeFunction` là ranh giới HTTP exchange của `WebClient`. Ta có thể thay nó bằng một function trả response giả và ghi lại request.

### 14.1. Fake downstream exchange

```java
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import reactor.core.publisher.Mono;

AtomicReference<ClientRequest> capturedRequest =
        new AtomicReference<>();

ExchangeFunction downstreamStub = request -> {
    capturedRequest.set(request);
    return Mono.just(
            ClientResponse.create(HttpStatus.OK)
                    .header(
                            HttpHeaders.CONTENT_TYPE,
                            MediaType.TEXT_PLAIN_VALUE)
                    .body("report-ok")
                    .build());
};
```

Mẫu này không gửi network request. `ClientRequest` có headers và URL để test kiểm chính xác bearer token và target. `AtomicReference` là công cụ test; trong concurrent tests cần tách fixture per-test để tránh state race.

### 14.2. Gắn OAuth2 filter trước stub

```java
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive
        .function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

// Test bean/fixture: manager dùng test implementation phù hợp.
ReactiveOAuth2AuthorizedClientManager manager =
        authorizeRequest -> Mono.just(testAuthorizedClient);

WebClient reportsWebClient = WebClient.builder()
        .baseUrl("https://reports-api.example.invalid")
        .filter(
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                        manager))
        .exchangeFunction(downstreamStub)
        .build();
```

`testAuthorizedClient` là `OAuth2AuthorizedClient` được test tạo riêng; manager trên chỉ là **fixture Reactive** để tránh gọi token endpoint. Đây là snippet về cấu hình WebClient trong test, chưa phải app test context đầy đủ.

Nếu controller được inject một bean `WebClient` khác, test sẽ **không** quan sát được request. Khi tích hợp qua `@SpringBootTest`/`@WebFluxTest`, cần thay đúng bean `reportsWebClient` hoặc inject stub vào bean đó; đừng tạo một WebClient không được code under test dùng.

### 14.3. Assert bearer token và đích gửi

Giả sử test đã gọi controller:

```java
ClientRequest actual = capturedRequest.get();

assertThat(actual).isNotNull();
assertThat(actual.url().getHost())
        .isEqualTo("reports-api.example.invalid");
assertThat(actual.headers().getFirst(HttpHeaders.AUTHORIZATION))
        .isEqualTo("Bearer test-reports-token");
```

Đặt access token bằng `mockOAuth2Client("reports-api").accessToken(...)` trong WebTestClient request để kết nối đúng fixture với controller. Không sử dụng access token thật cho assertion.

### 14.4. Một phương án gọn: kiểm WebClient filter riêng

Trước khi tích hợp toàn controller, có thể kiểm trực tiếp filter:

```java
OAuth2AuthorizedClient authorizedClient = testAuthorizedClient;

String body = reportsWebClient.get()
        .uri("/summary")
        .attributes(oauth2AuthorizedClient(authorizedClient))
        .retrieve()
        .bodyToMono(String.class)
        .block(); // Chỉ trong unit/integration TEST.

assertThat(body).isEqualTo("report-ok");
assertThat(capturedRequest.get().headers()
        .getFirst(HttpHeaders.AUTHORIZATION))
        .isEqualTo("Bearer test-reports-token");
```

Đoạn này kiểm **WebClient bearer forwarding**, không dùng `mockOAuth2Client()` vì không có incoming `ServerWebExchange`. Cả hai cấp test bổ sung nhau:

1. `WebTestClient + mockOAuth2Client`: argument resolution tại inbound controller.
2. `WebClient + ExchangeFunction stub`: outbound Authorization header.
3. Test tích hợp kết hợp hai cấp: controller nhận client từ mock repository rồi truyền qua filter.

### 14.5. Phân biệt stub manager và mockOAuth2Client

Nếu dùng:

```java
ReactiveOAuth2AuthorizedClientManager manager =
        authorizeRequest -> Mono.just(testAuthorizedClient);
```

manager fixture có thể trả client dù không có repository entry. Một test **chỉ** dựa vào fake manager như vậy không chứng minh `@RegisteredOAuth2AuthorizedClient` lấy đúng registration từ repository. Hãy chọn assertion theo mục tiêu và tránh để fake manager che giấu lỗi thiếu authorized client trong test chính.

## 15. Bộ test mẫu: chỉ scope hợp lệ mới gọi Reports API

Một controller đầy đủ hơn:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation
        .RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
class ReportsController {

    private final WebClient reportsWebClient;

    ReportsController(WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    @GetMapping("/reports/summary")
    Mono<String> summary(
            @RegisteredOAuth2AuthorizedClient("reports-api")
            OAuth2AuthorizedClient authorizedClient) {

        if (!authorizedClient.getAccessToken().getScopes()
                .contains("reports.read")) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.FORBIDDEN,
                    "Missing reports.read scope"));
        }

        return reportsWebClient.get()
                .uri("/summary")
                .attributes(oauth2AuthorizedClient(authorizedClient))
                .retrieve()
                .bodyToMono(String.class);
    }
}
```

Đoạn code cần static import của `oauth2AuthorizedClient` (như mục 13) và một bean `WebClient` đúng. Nếu trong application có nhiều WebClient beans, nên dùng `@Qualifier("reportsWebClient")` hoặc constructor injection rõ ràng thay vì dựa vào chọn ngẫu nhiên.

### 15.1. Happy path

```java
OAuth2AccessToken readToken = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "test-reports-token",
        Instant.now().minusSeconds(30),
        Instant.now().plusSeconds(3600),
        Set.of("reports.read"));

client.mutateWith(mockOidcLogin())
      .mutateWith(mockOAuth2Client("reports-api")
              .accessToken(readToken))
      .get().uri("/reports/summary")
      .exchange()
      .expectStatus().isOk()
      .expectBody(String.class).isEqualTo("report-ok");
```

Để test thật sự pass, inject `reportsWebClient` có fake downstream response `"report-ok"` và SecurityWebFilterChain phù hợp.

### 15.2. Thiếu scope

```java
OAuth2AccessToken noReadScope = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "test-no-scope",
        Instant.now().minusSeconds(30),
        Instant.now().plusSeconds(3600),
        Set.of("profile"));

client.mutateWith(mockOidcLogin())
      .mutateWith(mockOAuth2Client("reports-api")
              .accessToken(noReadScope))
      .get().uri("/reports/summary")
      .exchange()
      .expectStatus().isForbidden();
```

Nếu dùng `capturedRequest`, assert **downstreamStub không được gọi**. Chỉ test trả 403 vẫn chưa chứng minh controller không gửi token trong một side-effect trước khi kiểm scope.

### 15.3. Không có Authentication

```java
client.mutateWith(mockOAuth2Client("reports-api")
        .accessToken(readToken))
      .get().uri("/reports/summary")
      .exchange()
      .expectStatus().is3xxRedirection();
```

Kỳ vọng redirect phù hợp **nếu security entry point của ứng dụng là OIDC Login redirect**. Với API-first configuration, response có thể là 401. Điểm cần kiểm là request **không được chấp nhận chỉ vì có authorized client test**, khi route yêu cầu authenticated user.

## 16. Khi nào dùng mockOAuth2Client() thay vì mock WebClient?

Hai test doubles ở hai ranh giới khác nhau:

| Ranh giới | Cách test | Điều được chứng minh |
|---|---|---|
| Incoming WebFlux request | `WebTestClient + mockOAuth2Client` | Controller/resolver lấy được authorized client |
| Authenticated user | `mockOidcLogin`/`mockOAuth2Login` | SecurityContext/authorities/claims trong request |
| Authorized client manager | Fake/mock `ReactiveOAuth2AuthorizedClientManager` | Service gọi đúng registration/principal/context |
| Outbound HTTP to API | Stub `ExchangeFunction`, WireMock/MockWebServer | Bearer header/URL/method/body/status |
| Token endpoint | Fake Authorization Server/token server | Grant requests, token parsing, errors, retries |
| OIDC Login end-to-end | Test OP/discovery/JWKS/callback server | State, nonce, code exchange, ID Token validation |

Nếu controller chỉ trả dữ liệu lấy từ authorized client, không cần HTTP stub. Nếu controller gọi downstream API, `mockOAuth2Client()` **không** tự làm API trả 200; vẫn phải mock network boundary.

### 16.1. Test bằng manager mock

Khi logic gọi:

```java
authorizedClientManager.authorize(
        OAuth2AuthorizeRequest.withClientRegistrationId("inventory-api")
                .principal("service:import")
                .build())
```

thì có thể cần mock/fake manager để verify chính xác `registrationId`/principal thay vì chỉ dùng `mockOAuth2Client` ở inbound request. Trên WebFlux, method thực tế là reactive `ReactiveOAuth2AuthorizedClientManager.authorize(OAuth2AuthorizeRequest)` trả `Mono<OAuth2AuthorizedClient>`.

Đừng nhầm manager của **Servlet** (`OAuth2AuthorizedClientManager`) với manager của **Reactive**.

### 16.2. Test client_credentials flow

`client_credentials` thường có service principal, không cần human OIDC user. `mockOAuth2Client("inventory-api").principalName("service:import")` phù hợp khi method nhận **một authorized client đã cấp**. Nếu method **tự yêu cầu token mới** qua manager thì chỉ mock inbound client chưa đủ; phải fake manager/token response client hoặc dựng test Authorization Server.

## 17. Nhiều registrations: không gửi nhầm token

Một Portal có thể có:

```text
reports-api:
  access token: test-reports-token
  audience: reports-api

inventory-api:
  access token: test-inventory-token
  audience: inventory-api
```

Khi controller gọi Reports API, không được dùng token của Inventory API chỉ vì hai client thuộc cùng user.

### 17.1. Tạo hai authorized clients ở test

```java
var reports = mockOAuth2Client("reports-api")
        .principalName("user")
        .accessToken(new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "test-reports-token",
                Instant.now().minusSeconds(30),
                Instant.now().plusSeconds(3600),
                Set.of("reports.read")));

var inventory = mockOAuth2Client("inventory-api")
        .principalName("user")
        .accessToken(new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "test-inventory-token",
                Instant.now().minusSeconds(30),
                Instant.now().plusSeconds(3600),
                Set.of("inventory.read")));

client.mutateWith(mockOidcLogin())
      .mutateWith(reports)
      .mutateWith(inventory)
      .get().uri("/reports/summary")
      .exchange();
```

Đây là một pattern test có nhiều client fixtures. Behavior khi nhiều mutators áp lên cùng exchange phụ thuộc test plumbing và cách session repository xử lý; xác minh bằng test logic và tránh chia sẻ global client/session giữa các tests. Nếu project dùng custom repository khác, chuẩn bị fixture qua chính repository đó.

### 17.2. Assert đúng header

```text
GET Reports API
  Authorization: Bearer test-reports-token

Không được:
  Authorization: Bearer test-inventory-token
```

Không chỉ kiểm response body. Nếu HTTP stub luôn trả 200 bất kể header, một lỗi chọn registration vẫn có thể bị bỏ qua.

### 17.3. Nguy cơ default authorized client

Nếu `ServerOAuth2AuthorizedClientExchangeFilterFunction` được cấu hình sử dụng default authorized client, một WebClient dùng cho nhiều hosts có thể gửi token user tới endpoint ngoài ý định. Test security nên kiểm:

- API A nhận token A.
- API B nhận token B hoặc không nhận token.
- Một URL do browser tự cung cấp không được phép nhận bearer token.
- Missing registration/authorized client **fail closed**, không fallback sang service token toàn cục.

## 18. Với multi-tenant, principalName phải có ý nghĩa

Giả sử North và South cùng một OAuth2 provider:

```text
tenant North -> reports-north -> token North
tenant South -> reports-south -> token South
```

Test cần xác nhận:

1. Request tenant North chọn `reports-north`.
2. Token North chỉ đi đến Reports North API.
3. User của North không thể đổi query `tenant=south` rồi lấy client South.
4. Các principal names hoặc storage keys không bị trùng theo cách rò token cross-tenant.
5. Resource Server tự xác minh audience/tenant, không chỉ tin header do Portal thêm.

`mockOAuth2Client()` giúp tạo fixtures, **không tự thực hiện tenant authorization**.

### 18.1. Cặp issuer + subject

Nếu OIDC Login từ hai issuers khác nhau có cùng `sub`, không được tự coi là cùng user. Khi test một authorized client theo `principalName`, hiểu rõ application đã ánh xạ external identity bằng `(iss, sub)` hay chưa.

Một fake principalName cố định “user” là tiện để kiểm controller, nhưng không chứng minh production storage an toàn khi có nhiều tenants/providers.

### 18.2. Test token storage isolation

Nếu custom `ReactiveOAuth2AuthorizedClientService` dùng Redis/JDBC với tenant namespace, hãy test service/store riêng. Mutator `mockOAuth2Client()` dùng test repository không thay thế integration test của production storage schema, encryption, refresh token rotation và key lookup.

## 19. Token hết hạn và refresh: giới hạn của mockOAuth2Client()

`OAuth2AuthorizedClient` có access token và có thể có refresh token. Khi token sắp hết hạn, `ReactiveOAuth2AuthorizedClientManager` hoặc WebClient filter có thể cố re-authorize/refresh tùy cấu hình.

### 19.1. Token còn hạn: phù hợp để test forwarding

Trong bài, token fixture thường có:

```java
Instant.now().plusSeconds(3600)
```

để tránh vô tình kích hoạt refresh khi test mục tiêu chỉ là gắn bearer header. Điều này giữ test đơn giản và tách khỏi network.

### 19.2. Token hết hạn: test khác

```java
OAuth2AccessToken expired = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "expired-test-token",
        Instant.now().minusSeconds(3600),
        Instant.now().minusSeconds(30),
        Set.of("reports.read"));
```

Chỉ đặt một expired token trong `mockOAuth2Client` **chưa đủ** chứng minh refresh hoạt động. Muốn test refresh:

- Cần authorized client có refresh token phù hợp.
- Có `ReactiveOAuth2AuthorizedClientManager`/provider chain hỗ trợ `refresh_token`.
- Token response client được stub để trả token mới hoặc lỗi.
- Có persistence/repository để kiểm token mới được lưu/đọc đúng.
- Test concurrent refresh và `invalid_grant` riêng nếu business yêu cầu.

Không gọi OP thật hoặc dùng refresh token production chỉ để làm test.

### 19.3. No refresh token

Nếu authorized client không có refresh token, WebClient/manager có thể không thể refresh theo `refresh_token` grant; flow có thể yêu cầu reauthorization. Hành vi phụ thuộc authorized client provider chain và cấu hình login/client credentials, không phải quyền năng của `mockOAuth2Client`.

### 19.4. Điều không thể kết luận

Một test với `mockOAuth2Client("reports-api").accessToken(expired)` mà controller vẫn trả 200 không chứng minh Token Endpoint tự gia hạn được token; có thể fake manager đã trả client khác hoặc stub API bỏ qua authorization. Đặt assertion đúng điểm: token exchange call, resulting token, storage update và downstream header.

## 20. OAuth2AuthorizedClientRepository trong WebFlux test

`ServerOAuth2AuthorizedClientRepository` có vai trò gắn `OAuth2AuthorizedClient` với `ServerWebExchange` (thường WebSession). `mockOAuth2Client()` dùng cơ chế test để cung cấp client cho exchange đang xử lý.

### 20.1. Không đọc nhầm ReactiveOAuth2AuthorizedClientService

Có hai abstraction:

```text
ServerOAuth2AuthorizedClientRepository
  - gắn với ServerWebExchange và Authentication
  - phù hợp request/session-aware WebFlux

ReactiveOAuth2AuthorizedClientService
  - load/save/remove theo registration + principal
  - phù hợp backend store, service-level access
```

Nếu ứng dụng thật chỉ dùng custom `ReactiveOAuth2AuthorizedClientService`, nhưng test tiêm một authorized client vào test repository khác, test có thể xanh trong khi production lookup sai store. Khi mục tiêu là contract của custom service/manager, hãy mock/inject đúng implementation đó.

### 20.2. @RegisteredOAuth2AuthorizedClient resolution

Annotation dựa trên OAuth2 Client argument resolver và authorized client infrastructure phù hợp. Một test có thể fail nếu:

- SecurityWebFilterChain/OAuth2 Client integration chưa được cấu hình.
- Test context không có resolver/registration cần thiết.
- Registration ID không khớp.
- Repository test entry không được đưa vào cùng exchange.
- Principal/authentication khác với entry.
- Application dùng custom resolver không đọc test repository.

Đừng chữa bằng cách chuyển controller sang `@RequestParam("access_token")`. Bearer token không nên lấy tùy tiện từ browser query.

### 20.3. Với test bindToController

`WebTestClient.bindToController(new Controller(...))` có thể thiếu `HandlerMethodArgumentResolver` từ OAuth2 Client configuration nếu bạn không đăng ký WebFlux security/application context tương ứng. Đối với `@RegisteredOAuth2AuthorizedClient`, cách dễ ổn định thường là `bindToApplicationContext(context).apply(springSecurity())` với các beans thật/cần thiết của module.

Nếu cố ý tạo slice hẹp, phải đăng ký argument resolver/filters và authorized client repository một cách chủ đích.

## 21. WebTestClient và annotation authorization

Trong ứng dụng có method security:

```java
@PreAuthorize("hasRole('REPORT_VIEWER')")
@GetMapping("/reports/summary")
Mono<String> summary(...) { ... }
```

`mockOAuth2Client()` không tự cấp `ROLE_REPORT_VIEWER` cho Authentication. Test cần:

```java
client.mutateWith(mockOidcLogin()
        .authorities(
                new SimpleGrantedAuthority("ROLE_REPORT_VIEWER")))
      .mutateWith(mockOAuth2Client("reports-api")
              .accessToken(readToken))
      .get().uri("/reports/summary")
      .exchange();
```

`mockOidcLogin().authorities(...)` là API tùy biến Authentication principal/authorities của mutator theo Spring Security Test. Đồng thời phải bật Reactive method security trên application/test context khi muốn kiểm `@PreAuthorize`.

Không nhầm:

```text
ROLE_REPORT_VIEWER trong Authentication
    -> web/method authorization của Portal

reports.read scope của authorized client token
    -> quyền mà API downstream có thể xét
```

Hai lớp kiểm soát có thể cùng cần thỏa.

## 22. Negative tests không nên bỏ qua

### 22.1. Registration sai

```text
Controller yêu cầu @RegisteredOAuth2AuthorizedClient("reports-api")
Test chỉ chuẩn bị inventory-api
```

Kỳ vọng phụ thuộc infrastructure: không có client, trả lỗi/redirect khởi động authorize, hoặc manager cố cấp token mới. Trong test cô lập, cấu hình manager/provider để **không gọi OP ngoài ý định**. Assertion quan trọng là **không dùng token Inventory cho Reports API**.

### 22.2. Sai principal

```text
Authentication user = alice
AuthorizedClient stored for bob
```

Hệ thống không được để Alice lấy token của Bob từ repository/service. Test production storage/resolution và multi-user separation riêng, vì một in-memory fake manager luôn trả cùng client có thể che giấu lỗi.

### 22.3. Thiếu scope

Access token thiếu `reports.read` phải được xử lý theo policy. Nếu Portal không kiểm scope mà API downstream trả 403, test stub API phải mô phỏng 403 thay vì luôn trả success.

### 22.4. Downstream 401

API trả 401 có thể kích hoạt failure handling/removal authorized client tùy cấu hình `ServerOAuth2AuthorizedClientExchangeFilterFunction`. Để test:

1. Stub API trả 401 (và header OAuth2 error phù hợp khi cần).
2. Kiểm response từ Portal theo error mapping contract.
3. Nếu có failure handler, verify nó được gọi và xóa đúng authorized client.
4. Không khẳng định mọi 401 đều xóa client; phụ thuộc failure handler và nội dung lỗi.

### 22.5. Downstream 403

403 thường là thiếu quyền/scope/resource policy, không tự nghĩa là token hết hạn. Không cho manager retry token acquisition vô hạn chỉ vì API trả 403. Với test, verify error mapping, audit và không leak token.

### 22.6. Downstream 5xx/timeout

`mockOAuth2Client()` chỉ tạo token; test HTTP stub phải trả 5xx hoặc timeout/error publisher để kiểm retry, fallback và exception handling. Dùng `StepVerifier`/virtual time ở service-level tests nếu có Reactor retry/backoff để tránh chờ thật.

### 22.7. Không có authorized client

Nếu endpoint cần authorized client nhưng không được inject, chọn expected behavior theo contract. Không tự làm null dereference rồi kỳ vọng mọi tình huống là 500; ứng dụng nên có error handling rõ hoặc quản lý reauthorization hợp lệ.

### 22.8. Bảo vệ token khỏi gửi sai host

Test với một URL giả không được allowlist:

```text
GET /proxy?target=https://untrusted.example.invalid
```

Endpoint không được cho browser chọn bất kỳ destination rồi chuyển bearer token; `ServerOAuth2AuthorizedClientExchangeFilterFunction` có thể gắn token vào HTTP request mà code tạo ra nếu bạn truyền authorized client. Kiểm host allowlist/URI construction riêng.

## 23. Test matrix khuyến nghị

| Test | Authentication | Authorized client | Downstream stub | Kỳ vọng |
|---|---|---|---|---|
| Happy path | `mockOidcLogin()` | `mockOAuth2Client("reports-api")` với scope đúng | 200 | API được gọi với đúng bearer |
| Anonymous | Không có | Có test client | Không gọi | 401/302 theo security entry point |
| Authenticated nhưng không có client | Có | Không | Không gọi hoặc flow authorize giả | Hành vi thiếu client rõ |
| Sai registration | Có | `inventory-api` | Không gọi Reports bằng token Inventory | Không rò token |
| Sai principal | Alice | Client của Bob | Không dùng token Bob | Bị từ chối/không resolve |
| Thiếu scope | Có | Token chỉ có `profile` | Không gọi hoặc API 403 | 403 theo policy |
| Scope hợp lệ | Có | Token có `reports.read` | 200 | Data thành công |
| API trả 401 | Có | Token hợp lệ trong test | 401 + OAuth error | Failure handler/error mapping đúng |
| API trả 403 | Có | Token đúng | 403 | Không biến thành login success |
| API timeout | Có | Token đúng | `Mono.error`/timeout | Error contract và retry budget |
| Expired token | Có | Token expired | Token client fake riêng | Test refresh/re-auth riêng |
| Multiple clients | Có | Reports + Inventory | Stub kiểm từng host | Không chéo bearer |
| Multi-tenant | Có | North + South | Stub kiểm tenant API | Không cross-tenant |
| Client credentials | Service authentication/policy | Service authorized client | 200 | Dùng service token đúng |
| Test isolation | Per request fixtures | Per test repository state | Per test stub | Không rò sang test khác |

Đừng chỉ viết một test happy path; các lỗi nguy hiểm nhất của OAuth2 Client thường xuất hiện ở **chọn sai registration, principal hoặc outbound destination**.

## 24. Những vấn đề dễ gặp với thời gian và context Reactive

### 24.1. Không block trong handler

Không dùng:

```java
// Không dùng trong Reactive controller:
OAuth2AuthorizedClient client = manager
        .authorize(request)
        .block();
```

Trong ứng dụng, xử lý bằng `Mono`/`flatMap`. Trong một **test setup** ngắn, `block()` để lấy `ClientRegistration` từ test repository có thể chấp nhận theo ví dụ tài liệu, nhưng không copy vào production request path.

### 24.2. Không đặt Authorization header trực tiếp trong incoming WebTestClient

```java
client.get()
      .header(HttpHeaders.AUTHORIZATION, "Bearer test-reports-token")
      .uri("/reports/summary")
```

Đây là **inbound HTTP Authorization header** từ browser tới Portal. Nó có thể dùng khi test Resource Server, nhưng **không** phải cách tạo `OAuth2AuthorizedClient` cho outbound token. Khi Portal dùng OIDC browser session và cần WebClient thay người dùng gọi API, hãy mock đúng client repository/manager.

### 24.3. ReactiveSecurityContextHolder không phải ThreadLocal thông thường

`ReactiveSecurityContextHolder` dựa trên Reactor Context, không nên dùng `SecurityContextHolder.getContext()` trong callback Reactive rồi mặc định nó luôn có user. `mockOidcLogin()` chuẩn bị Authentication theo cơ chế Reactive test, còn `mockOAuth2Client()` chuẩn bị client state qua exchange/repository. Truyền context đúng qua `Mono`/`Flux`.

### 24.4. Subscription và cancellation

Nếu WebClient request bị cancel trước khi exchange hoàn tất, HTTP stub hoặc manager chưa chắc đã được gọi. Khi kiểm interactions, phải subscribe bằng `WebTestClient.exchange()`/`StepVerifier.verify()` chứ không chỉ tạo `Mono`.

### 24.5. Token thời gian sắp hết hạn

Một số OAuth2 authorized client managers xem token là “sắp hết hạn” trước `expiresAt` theo clock skew mặc định. Trong test forwarding, đặt expiresAt đủ xa (ví dụ +1 giờ) để không vô tình kích hoạt refresh.

### 24.6. Clock cố định cho test expiry

Đối với các test chuyên về token expiration/refresh, dùng `Clock.fixed(...)` hoặc abstractions hỗ trợ clock trong component thay vì dựa vào thời gian thực và `Thread.sleep()`. `mockOAuth2Client` không tự điều khiển clock của OAuth2 provider chain.

## 25. Dùng Kotlin trong WebFlux test

Với Kotlin, static import/cách gọi mutator tương tự:

```kotlin
import org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Client
import org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin

@Test
fun reportClientIsAvailable() {
    webTestClient
        .mutateWith(mockOidcLogin())
        .mutateWith(mockOAuth2Client("reports-api"))
        .get()
        .uri("/internal/client-summary")
        .exchange()
        .expectStatus().isOk
        .expectBody()
        .jsonPath("$.registrationId").isEqualTo("reports-api")
}
```

Ví dụ Kotlin assumes WebTestClient và test context được cấu hình với Spring Security. Nếu endpoint kiểm scopes khác mặc định, phải tùy biến `OAuth2AccessToken` như Java. Các API Java builders có thể dùng trực tiếp từ Kotlin hoặc bọc trong helpers để tái sử dụng fixtures.

### 25.1. Test fixture builder tái sử dụng

Một helper ở tầng test có thể tạo token:

```java
static OAuth2AccessToken testAccessToken(
        String value, String... scopes) {

    return new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            value,
            Instant.now().minusSeconds(30),
            Instant.now().plusSeconds(3600),
            Set.of(scopes));
}
```

Chỉ dùng `value` là chuỗi fake có thể phân biệt trong test. Không tạo giá trị trùng token thật và không đưa secrets production vào fixtures.

### 25.2. Helper không thay đổi registration theo browser input

Tái sử dụng fixtures là tốt, nhưng tránh helper:

```java
mockOAuth2Client(request.getQueryParams()
        .getFirst("registrationId"))
```

vì điều đó sẽ khiến test khẳng định hành vi dùng registration do client tự chọn là hợp lệ mà không kiểm allowlist. Trong production, registration phải được chọn theo policy đã xác minh.

## 26. Khi test còn xanh nhưng production vẫn lỗi

`mockOAuth2Client()` **cố tình bỏ qua** nhiều phụ thuộc bên ngoài nên một test controller thành công không bảo đảm integration hoàn chỉnh.

| Production lỗi | Vì sao mock test không bắt được? | Test bổ sung |
|---|---|---|
| `redirect_uri_mismatch` | Không có OIDC authorization redirect | Test Authorization Request/OP |
| `invalid_state` | Không chạy callback/authorization request repository thật | OIDC Login integration test |
| Client secret sai | Không gọi token endpoint | Token HTTP client/OP stub |
| Truststore/Pkix lỗi | Không handshake tới OP | TLS client integration test |
| ID Token issuer/signature lỗi | Token của mock là declarative | OIDC decoder/JWKS test |
| Refresh token `invalid_grant` | Mock sẵn access token còn hạn | Refresh provider/manager integration test |
| Authorized client không lưu ở Redis/JDBC | Dùng test repository riêng | Storage/manager integration test |
| Token sai audience ở Reports API | API stub không validate token | Resource Server integration/contract test |
| Token gửi sai host | Stub không assert URL/header | Outbound request assertion |
| Logout không xóa token | Mutator chỉ khởi tạo fixture | Logout + repository/revocation test |
| Đồng thời hai requests refresh cùng RT | Không có concurrency/rotation | Concurrent manager/token store test |

Đây không phải khuyết điểm của mock. Mục tiêu của nó là **cô lập controller/service sử dụng authorized client**, giúp test nhanh, ổn định và không cần external identity infrastructure.

## 27. Chẩn đoán lỗi trong WebTestClient

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy `mockOAuth2Client` | Chưa có `spring-security-test` hoặc import Servlet test API | Thêm test dependency, import `SecurityMockServerConfigurers` |
| Mutator không áp dụng | `WebTestClient` bindToServer hoặc thiếu mock security test plumbing | Dùng bindToApplicationContext + `springSecurity()` |
| `@RegisteredOAuth2AuthorizedClient` là null/không resolve | Registration ID khác hoặc resolver/repository thiếu | Kiểm `reports-api`, OAuth2 Client config và WebTestClient binding |
| Endpoint trả 302/401 dù có client | Chưa có authenticated principal | Thêm `mockOidcLogin()`/`mockOAuth2Login()` theo policy |
| Endpoint trả 403 | Authorities/business scopes thiếu | Phân biệt Authentication authorities và token scopes |
| WebClient không gửi Bearer | Thiếu OAuth2 filter hoặc request attribute | Gắn `ServerOAuth2AuthorizedClientExchangeFilterFunction` và `oauth2AuthorizedClient` |
| WebClient gửi Bearer sai | Default client/registration bị chọn nhầm | Dùng explicit authorized client, assert header và URL |
| Test vô tình gọi OP thật | Manager/argument resolver cố acquire token | Fake manager/token response client hoặc bổ sung đúng client fixture |
| Test vẫn không thấy token dù đã mutate | Controller dùng custom service chứ không dùng repository của test | Inject/mock đúng storage/manager |
| Scope test không khớp | Token fixture mặc định chỉ có `read` | Dùng `accessToken(...)` với scopes phù hợp |
| Token bị refresh khi không mong muốn | `expiresAt` quá gần/quá khứ | Dùng token còn hạn dài hoặc stub refresh path |
| Nhiều tests ảnh hưởng nhau | Dùng chung mutable repository, mock server, capturedRequest | Tạo fixtures per-test, reset stubs |
| HTTP client trả 200 nhưng token chưa được verify | Stub không kiểm bearer | Assert Authorization header ở outbound |
| Test dùng `mockJwt` nhưng controller cần authorized client | Inbound JWT khác OAuth2 client token | Dùng đúng mutator |
| Có client nhưng principalName sai | Authentication name và stored client owner lệch | Dùng `principalName(...)`/kiểm identity |
| Mỗi test độc lập pass, chạy suite fail | Test order/parallel session hoặc mutable bean state | Isolate test context và fake stores |

### 27.1. Sơ đồ chẩn đoán

```mermaid
flowchart TD
    A["Test dùng mockOAuth2Client thất bại"] --> B{"WebTestClient mock binding đúng?"}
    B -- Không --> C["bindToApplicationContext + springSecurity()"]
    B -- Có --> D{"Request qua được authorization policy?"}
    D -- Không --> E["mockOidcLogin / authorities / CSRF nếu áp dụng"]
    D -- Có --> F{"Controller resolve đúng registration/principal?"}
    F -- Không --> G["Kiểm @RegisteredOAuth2AuthorizedClient và repository"]
    F -- Có --> H{"WebClient có OAuth2 filter và attributes?"}
    H -- Không --> I["Gắn filter, truyền explicit authorized client"]
    H -- Có --> J{"Stub nhìn thấy Bearer header đúng?"}
    J -- Không --> K["Kiểm token expiry, manager, client selection"]
    J -- Có --> L{"API stub response/contract đúng?"}
    L -- Không --> M["Status, body, error mapping, timeout/retry"]
    L -- Có --> N["Test passing: đúng hợp đồng đang kiểm"]
```

## 28. Những sai lầm thường gặp

1. **Coi `mockOAuth2Client()` là mock OIDC Login**, trong khi nó chỉ tạo authorized client.
2. **Dùng `mockJwt()` để tạo outbound token**, nhầm Resource Server với OAuth2 Client.
3. **Chỉ tạo `ClientRegistration` rồi chờ controller có access token**, quên authorized client.
4. **Đặt sai `registrationId`** (nhầm với `clientId`/provider ID).
5. **Chỉ test happy path với scopes mặc định `read`**, bỏ qua scope nghiệp vụ.
6. **Tin rằng access token scopes tự thành GrantedAuthorities trong Authentication**.
7. **Quên `mockOidcLogin()` khi endpoint yêu cầu authenticated user**.
8. **Dùng một principalName giả cho mọi user/tenant** rồi bỏ qua cross-user token isolation.
9. **Chỉ assert status 200**, không xác minh outgoing `Authorization: Bearer ...`.
10. **Đặt token trên inbound `WebTestClient.header("Authorization",...)`** rồi nghĩ đó là authorized client.
11. **Quên OAuth2 WebClient filter**, nên `oauth2AuthorizedClient(...)` attribute không có tác dụng.
12. **Dùng default OAuth2AuthorizedClient cho mọi WebClient request**, dễ lộ bearer.
13. **Dùng bean WebClient trong test khác bean controller đang inject**, khiến stub vô hiệu.
14. **Dùng token đã hết hạn cho test forwarding**, vô tình khởi động refresh.
15. **Cho test gọi OP/token endpoint production** để “lấy token cho đúng”.
16. **Kỳ vọng mock test tự xác minh ID Token/JWT signature hoặc PKCE**, vượt phạm vi tool.
17. **Nhầm `ServerOAuth2AuthorizedClientRepository` với `ReactiveOAuth2AuthorizedClientService`**.
18. **Quên apply `springSecurity()` cho mock WebTestClient binding** khi tự dựng client.
19. **Sử dụng `bindToServer()` rồi muốn mutator tiêm vào session thật**.
20. **Gọi `block()` trong Reactive controller** để lấy authorized client.
21. **Bỏ qua downstream 401/403/timeout**, chỉ stub HTTP 200.
22. **Xem fake token của test như credential thật** và gửi ra network.
23. **Không reset mock/captured HTTP requests giữa tests**, tạo flaky tests.
24. **Không kiểm security context sau khi dùng authorized client**, gây lỗ hổng endpoint anonymous.

## 29. Bài tập thực hành

### Bài 1: Đọc authorized client

Tạo endpoint WebFlux:

```text
GET /client/info
-> trả registrationId và scopes (không trả token)
```

Viết test dùng `mockOAuth2Client("reports-api")` và assert registration ID.

### Bài 2: Kiểm scope

Thay access token bằng token có scopes `reports.read`, sau đó bằng token chỉ có `profile`. Kiểm controller chỉ cho phép request có scope cần thiết; test không dựa vào default `read`.

### Bài 3: Kết hợp OIDC Login

Đặt `anyExchange().authenticated()`. Chứng minh:

1. Chỉ `mockOAuth2Client` không bảo đảm request authenticated.
2. Thêm `mockOidcLogin()` làm request qua security policy.
3. Việc authorized client được resolve vẫn độc lập với authorities.

### Bài 4: Kiểm outbound Bearer

Thay Reports API bằng `ExchangeFunction` fake hoặc HTTP stub. Kiểm:

```text
Authorization: Bearer test-reports-token
Host = reports-api.example.invalid
Response body = report-ok
```

Không expose token string qua inbound response để test.

### Bài 5: Nhiều registrations

Tạo `reports-api` và `inventory-api` với token strings khác nhau. Kiểm Reports request chỉ dùng Reports token, kể cả khi cả hai có principalName `user`.

### Bài 6: Refresh token

Tạo expired authorized client và fake `ReactiveOAuth2AuthorizedClientManager`/token response client. Kiểm token request refresh đúng một lần, token mới được đưa vào outbound request và storage update theo policy. Không coi expired access token fixture đơn lẻ là bằng chứng refresh.

## 30. Câu hỏi ôn tập

1. `OAuth2AuthorizedClient` khác `ClientRegistration` và `Authentication` ở điểm nào?
2. Vì sao `mockOAuth2Client()` phù hợp để test `@RegisteredOAuth2AuthorizedClient`?
3. `mockOAuth2Client("reports-api")` đặt authorized client ở đâu trong Reactive test?
4. Bốn phương thức tùy chỉnh quan trọng của `OAuth2ClientMutator` là gì?
5. Những giá trị mặc định nào được tài liệu Spring Security Test nêu?
6. Vì sao client secret/token trong fixture không cần được OP cấp hoặc ký?
7. Tại sao `mockOAuth2Client()` không tự làm endpoint `authenticated()` được truy cập?
8. Khi nào nên kết hợp `mockOidcLogin()` và `mockOAuth2Client()`?
9. `mockJwt()` dùng cho inbound JWT hay outbound OAuth2AuthorizedClient?
10. Vì sao không dùng Authorization header trên `WebTestClient` để mock outbound token?
11. Annotation `@RegisteredOAuth2AuthorizedClient("reports-api")` dùng client ID hay registration ID?
12. `principalName("alice")` ảnh hưởng thế nào đến authorized client lookup?
13. Scope `reports.read` của access token khác `ROLE_REPORT_VIEWER` của Authentication ra sao?
14. Vì sao phải dùng `accessToken(...)` thay vì mặc định `read` để test nghiệp vụ?
15. `oauth2AuthorizedClient(authorizedClient)` làm gì trong `WebClient.attributes(...)`?
16. Nếu WebClient thiếu `ServerOAuth2AuthorizedClientExchangeFilterFunction`, request attribute có tự thêm bearer header không?
17. Vì sao test WebClient cần stub HTTP exchange riêng với `mockOAuth2Client()`?
18. Làm sao xác nhận token không bị gửi sang host không đúng audience?
19. Nếu controller nhận authorized client nhưng API stub luôn trả 200, lỗ hổng test nào có thể bị bỏ qua?
20. Khi manager có thể dùng cache, vì sao không dùng `mockOAuth2Client` để kết luận token acquisition đã thành công?
21. Expired access token fixture có đủ chứng minh refresh grant hoạt động không?
22. `ServerOAuth2AuthorizedClientRepository` khác `ReactiveOAuth2AuthorizedClientService` thế nào?
23. Vì sao `bindToServer()` không phù hợp để mutate mock session của server thật?
24. Trong một test dùng cả OAuth2 Login và client credentials, nên xác minh những key/registration nào?
25. Khi token từ downstream API trả 401 hoặc 403, cần test các lớp nào?
26. Làm sao tránh dùng `principalName` do query parameter của browser cung cấp?
27. Tại sao không nên gọi `block()` trong Reactive controller?
28. Khi nào `mockOAuth2Client()` không đủ và cần mock OP/token endpoint/JWKS riêng?

## Tài liệu tham khảo

- [Spring Security Reference — Testing OAuth 2.0 (Reactive): Testing OAuth 2.0 Clients](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security Reference — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html)
- [Spring Security Reference — Testing Authentication (Reactive)](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
- [Spring Security API — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html)
- [Spring Security API — SecurityMockServerConfigurers.OAuth2ClientMutator](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.OAuth2ClientMutator.html)
- [Spring Security Reference — Reactive OAuth2 Client Core](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html)
- [Spring Security Reference — Reactive Authorized Client Features](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html)
- [Spring Security Reference — OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/)
- [Spring Security API — ServerOAuth2AuthorizedClientExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html)
- [Spring Security API — OAuth2AuthorizedClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html)
- [Spring Security API — ReactiveOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientManager.html)
- [Spring Security API — ServerOAuth2AuthorizedClientRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/server/ServerOAuth2AuthorizedClientRepository.html)
- [Spring Framework Reference — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://datatracker.ietf.org/doc/html/rfc6749)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html)
