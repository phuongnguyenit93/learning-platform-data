# Kiểm thử `mockOAuth2Client()` và lời gọi `WebClient` có `OAuth2AuthorizedClient`

> Phạm vi: **Spring Security cho ứng dụng WebFlux (reactive)**; tập trung kiểm thử OAuth 2.0 Client đã được cấp quyền và xác nhận access token được đưa vào HTTP request đi ra. Các ví dụ Java sử dụng Java 17+, Spring Security 6.x/7.x và JUnit 5. Đây là bài về **OAuth2 Client**, không phải cách xác minh chữ ký JWT tại Resource Server.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `ClientRegistration`, `OAuth2AuthorizedClient`, `ReactiveOAuth2AuthorizedClientManager` và `ServerOAuth2AuthorizedClientRepository`.
2. Dùng `WebTestClient.mutateWith(mockOAuth2Client("catalog"))` để cấp một authorized client giả cho request WebFlux, không gọi authorization server thật.
3. Tùy chỉnh `registrationId`, `principalName`, `accessToken`, scopes và `ClientRegistration` cho các nhánh kiểm thử.
4. Truyền authorized client từ `@RegisteredOAuth2AuthorizedClient` vào `WebClient` bằng `.attributes(oauth2AuthorizedClient(client))` và kiểm tra header `Authorization: Bearer ...` trên request đi ra.
5. Biết giới hạn của mock: nó không kiểm chứng grant flow, refresh token, xác thực OAuth2 login hoặc kết nối đến dịch vụ ngoài; những phần đó cần phép thử riêng.

## 2. Hiểu đúng đối tượng và đường đi của token

| Thành phần | Vai trò | Điều cần kiểm thử |
| --- | --- | --- |
| `ClientRegistration` | Cấu hình client: `registrationId`, `clientId`, grant type, token URI, scopes… | Chọn đúng đăng ký OAuth2 |
| `OAuth2AccessToken` | Token được cấp, có `tokenValue`, thời điểm hiệu lực, scopes | Giá trị Bearer thực sự được gửi |
| `OAuth2AuthorizedClient` | Gắn `ClientRegistration` và access token với `principalName` | Controller/service nhận đúng client |
| `ServerOAuth2AuthorizedClientRepository` | Lưu/nạp authorized client theo ngữ cảnh server request | Mock client xuất hiện trong quá trình xử lý WebFlux |
| `ReactiveOAuth2AuthorizedClientManager` | Tìm, cấp mới hoặc tái ủy quyền/refresh tùy provider | Không gọi IdP thật khi bài test chỉ cần token giả |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Filter của `WebClient`, chọn authorized client và gắn Bearer vào HTTP request đi ra | Header của request downstream đúng token |

Luồng thường gặp:

```text
HTTP GET /catalog
  -> WebFlux Security / ServerWebExchange
  -> @RegisteredOAuth2AuthorizedClient("catalog")
     (lấy OAuth2AuthorizedClient từ ngữ cảnh được cấu hình)
  -> WebClient.get().attributes(oauth2AuthorizedClient(client))
  -> ServerOAuth2AuthorizedClientExchangeFilterFunction
  -> Authorization: Bearer <access-token>
  -> downstream resource server
```

`mockOAuth2Client()` tác động vào phía **request đến ứng dụng** trong `WebTestClient`: nó sắp xếp một authorized client giả trong cơ chế repository mà Spring Security Test cung cấp. Nó **không tự thêm Bearer vào WebClient** nếu WebClient chưa gắn OAuth2 filter hoặc application chưa chọn authorized client. Vì vậy phải kiểm tra cả hai ranh giới: *inbound client resolution* và *outbound request*.

### Phân biệt ba nhóm mock dễ nhầm

- `mockOAuth2Client()`: chuẩn bị `OAuth2AuthorizedClient`; tự nó **không tạo authenticated `SecurityContext`**.
- `mockOAuth2Login()` hoặc `mockOidcLogin()`: mô phỏng người dùng đã đăng nhập OAuth2/OIDC, tạo `Authentication` và gắn authorized client đi kèm.
- `mockJwt()`: mô phỏng `JwtAuthenticationToken` cho **Resource Server** nhận Bearer token; không thay thế `mockOAuth2Client()` trong bài toán WebClient OAuth2 Client.

Nếu endpoint yêu cầu `authenticated()`, chỉ `mockOAuth2Client()` có thể chưa đủ: bổ sung một authentication phù hợp, chẳng hạn `.mutateWith(mockUser("alice"))`, hoặc dùng `mockOAuth2Login()` nếu đúng kịch bản đăng nhập. Việc đăng nhập và quyền gọi dịch vụ ngoài là hai khái niệm độc lập.

## 3. Cài đặt kiểm thử và chuẩn bị WebClient

Với ứng dụng Spring Boot dùng Gradle Kotlin DSL (minh họa các dependency cần thiết; sử dụng version do Spring Boot BOM quản lý):

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

Cấu hình đăng ký `catalog` dùng grant `client_credentials` (URI giả chỉ dành cho ví dụ, không được gọi trong test dùng mock token):

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          catalog:
            client-id: demo-client
            client-secret: demo-secret
            authorization-grant-type: client_credentials
            scope: item.read
        provider:
          catalog:
            token-uri: https://auth.example.invalid/oauth/token
```

Trong mã ứng dụng, WebClient phải có **reactive OAuth2 filter**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ClientWebConfig {
    @Bean
    WebClient securedWebClient(ReactiveOAuth2AuthorizedClientManager manager) {
        var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
        return WebClient.builder().filter(oauth2).build();
    }
}
```

Đây là class cấu hình dành cho một ứng dụng Spring Boot đã kích hoạt OAuth2 Client; `manager` là bean được cấu hình bởi ứng dụng/auto-configuration. Với môi trường có nhiều `WebClient`, inject đúng bean đã gắn filter. Đừng lấy ví dụ `ServletOAuth2AuthorizedClientExchangeFilterFunction` của Spring MVC để dùng trong WebFlux.

Controller nhận client theo registration ID rồi truyền tường minh vào WebClient:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@RestController
class CatalogController {
    private final WebClient securedWebClient;

    CatalogController(WebClient securedWebClient) {
        this.securedWebClient = securedWebClient;
    }

    @GetMapping("/catalog")
    Mono<String> catalog(
            @RegisteredOAuth2AuthorizedClient("catalog")
            OAuth2AuthorizedClient authorizedClient) {
        return securedWebClient.get()
                .uri("https://resource.example.invalid/items")
                .attributes(oauth2AuthorizedClient(authorizedClient))
                .retrieve()
                .bodyToMono(String.class);
    }
}
```

**Cú pháp import:** Một lệnh Java `import static` phải nằm trên **một dòng trong file nguồn**; khi sao chép đoạn trên, gộp hai dòng `import static ...` thành:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;
```

Đây là hai mảnh mã ứng dụng đặt trong các file Java theo tên class thực tế; endpoint `/catalog` trong ví dụ sẽ cần một downstream giả (MockWebServer, WireMock hoặc ExchangeFunction) khi test để tránh gọi URL `.invalid`. Phần tiếp theo kiểm tra từng ranh giới một cách tách biệt.

## 4. Kiểm thử WebFlux bằng `mockOAuth2Client()`

### 4.1. Cú pháp cơ bản và ý nghĩa

Khi `WebTestClient` đã được cấu hình với Spring Security Test (ví dụ `@SpringBootTest` + `@AutoConfigureWebTestClient` hoặc `bindToApplicationContext(...).apply(springSecurity())`):

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Client;

// Bên trong một @Test, với biến WebTestClient client:
client.mutateWith(mockOAuth2Client("catalog"))
      .get().uri("/client-info")
      .exchange()
      .expectStatus().isOk();
```

Cũng cần gộp lệnh `import static` về một dòng trong file Java:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOAuth2Client;
```

`"catalog"` là **registration ID**, không phải client ID, username hay tên provider. Mặc định Spring Security Test tạo `ClientRegistration` đơn giản (client ID `test-client`, client secret `test-secret`), principal name `user` và access token có scope `read`. Token giả không cần được ký hay được authorization server công nhận.

### 4.2. Thử việc resolve `@RegisteredOAuth2AuthorizedClient`

Để xem rõ mock đến được controller, thêm một endpoint thử nghiệm nhỏ trong cấu hình test hoặc ứng dụng thử:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ClientInfoController {
    @GetMapping("/client-info")
    Mono<String> info(
            @RegisteredOAuth2AuthorizedClient("catalog")
            OAuth2AuthorizedClient client) {
        return Mono.just(client.getClientRegistration().getRegistrationId()
                + "|" + client.getPrincipalName()
                + "|" + client.getAccessToken().getTokenValue());
    }
}
```

Ví dụ kiểm thử JUnit 5 bên trong **Spring Boot WebFlux test context** đã load controller, OAuth2 Client và WebTestClient:

```java
import java.time.Instant;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOAuth2Client;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ClientInfoTest {
    @Autowired
    WebTestClient client;

    @Test
    void injectedAuthorizedClientHasExpectedIdentityAndToken() {
        Instant now = Instant.now();
        var token = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "fake-access-token",
                now.minusSeconds(10),
                now.plusSeconds(3600),
                Set.of("item.read"));

        client.mutateWith(mockOAuth2Client("catalog")
                    .principalName("alice")
                    .accessToken(token))
                .get().uri("/client-info")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("catalog|alice|fake-access-token");
    }
}
```

Lệnh chạy (đối với dự án Gradle có wrapper): `./gradlew test --tests '*ClientInfoTest'`; trên Windows có thể dùng `gradlew.bat test --tests "*ClientInfoTest"`. JUnit kiểm tra body và status, không in stdout. Các đoạn trên giả định dự án có `@SpringBootApplication`, endpoint được component-scan, registration `catalog` phù hợp và WebFlux test auto-configuration; chúng không tạo thành một ứng dụng độc lập chỉ bằng cách dán một class.

Nếu đường dẫn `/client-info` bị bảo vệ bởi `authenticated()`, phối hợp authentication, ví dụ `client.mutateWith(mockUser("alice")).mutateWith(mockOAuth2Client("catalog").principalName("alice"))`. Chỉ thêm mock user khi kiểm thử đúng hành vi bảo vệ route; nó không tự tạo access token cho WebClient.

### 4.3. Tùy biến mock cho nhánh nghiệp vụ

```java
Instant now = Instant.now();
OAuth2AccessToken token = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "scoped-token",
        now.minusSeconds(5),
        now.plusSeconds(600),
        Set.of("message:read", "item.read"));

client.mutateWith(mockOAuth2Client("catalog")
        .principalName("alice")
        .accessToken(token))
      .get().uri("/client-info")
      .exchange()
      .expectStatus().isOk();
```

Các phương thức của `OAuth2ClientMutator` thường dùng: `accessToken(OAuth2AccessToken)`, `principalName(String)`, `clientRegistration(ClientRegistration)` và `clientRegistration(Consumer<ClientRegistration.Builder>)`. Nếu dùng cấu hình registration thật từ ứng dụng, có thể lấy qua `ReactiveClientRegistrationRepository.findByRegistrationId("catalog")` trong setup test rồi đưa cho `clientRegistration(...)`; chỉ `block()` trong phần *setup đồng bộ của test*, không `block()` trong request handler reactive.

**Scopes là dữ liệu trong access token**, không tự động đồng nghĩa với quyền truy cập endpoint đến ứng dụng. Ví dụ logic `client.getAccessToken().getScopes().contains("message:read")` kiểm tra tập scope của client đi ra, còn `hasAuthority("SCOPE_message:read")` kiểm tra authorities trong authentication đến ứng dụng. Hai nơi có thể cần hai bộ dữ liệu mock khác nhau.

## 5. Chứng minh WebClient gửi đúng `Authorization: Bearer`

Kiểm thử chỉ nhìn body `/client-info` mới chứng minh controller nhận authorized client. Để xác nhận outbound Bearer, cần bắt request ở **lớp `ExchangeFunction` của WebClient** hoặc mock HTTP server và assert header. Dưới đây là class JUnit 5 **độc lập trong project đã có các dependency ở mục 3**; nó không mở socket và không gọi IdP.

Tạo file `src/test/java/example/OAuth2WebClientFilterTest.java`:

```java
package example;

import java.time.Instant;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

class OAuth2WebClientFilterTest {
    @Test
    void sendsBearerHeaderOfExplicitAuthorizedClient() {
        ClientRegistration registration = ClientRegistration
                .withRegistrationId("catalog")
                .clientId("test-client")
                .clientSecret("test-secret")
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://auth.example.invalid/token")
                .build();

        Instant now = Instant.now();
        OAuth2AccessToken token = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "fake-token-123",
                now.minusSeconds(10),
                now.plusSeconds(3600),
                Set.of("item.read"));
        OAuth2AuthorizedClient authorizedClient =
                new OAuth2AuthorizedClient(registration, "alice", token);

        // Khi filter yêu cầu re-authorize, manager giả trả lại client còn hiệu lực.
        ReactiveOAuth2AuthorizedClientManager manager =
                request -> Mono.just(authorizedClient);

        AtomicReference<String> sentAuthorization = new AtomicReference<>();
        ExchangeFunction fakeDownstream = request -> {
            sentAuthorization.set(
                    request.headers().getFirst(HttpHeaders.AUTHORIZATION));
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE, "text/plain")
                    .body("items-ok")
                    .build());
        };

        WebClient webClient = WebClient.builder()
                .filter(new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager))
                .exchangeFunction(fakeDownstream)
                .build();

        String body = webClient.get()
                .uri("https://resource.example.invalid/items")
                .attributes(oauth2AuthorizedClient(authorizedClient))
                .retrieve()
                .bodyToMono(String.class)
                .block(); // Chỉ block ở test, không block trong handler WebFlux.

        assertEquals("items-ok", body);
        assertEquals("Bearer fake-token-123", sentAuthorization.get());
    }
}
```

Chạy: `./gradlew test --tests example.OAuth2WebClientFilterTest` (Windows: `gradlew.bat test --tests example.OAuth2WebClientFilterTest`). **Kết quả mong đợi:** JUnit test pass; không có stdout ứng dụng. Nếu bỏ `.filter(...)`, request không có Bearer do OAuth2 filter tạo; nếu bỏ `.attributes(oauth2AuthorizedClient(...))` và chưa khai báo default registration, filter không biết phải chọn authorized client nào. Fake manager ở ví dụ cố ý không kiểm thử cấp token/refresh: mục tiêu chỉ là token đã chọn có được gắn vào request.

Lưu ý: nhiều phiên bản Spring Security gọi lại `ReactiveOAuth2AuthorizedClientManager.authorize(...)` ngay cả khi truyền authorized client tường minh, để xử lý token cần tái ủy quyền. Vì vậy stub manager trong bài test trả lại client còn hiệu lực; giả định "đã truyền explicit client thì manager chắc chắn không được gọi" có thể làm test sai.

### Kiểm thử tích hợp thay thế

Với yêu cầu chứng minh toàn chuỗi `WebTestClient → controller → WebClient → HTTP downstream`, dùng **MockWebServer/WireMock**: trỏ URL downstream vào cổng localhost do mock server cấp, enqueue response `200`, gửi `WebTestClient.mutateWith(mockOAuth2Client(...))`, rồi assert HTTP request mà mock server nhận có `Authorization: Bearer fake-token-123`. Khi đó vẫn có thể cần `mockUser` nếu route bắt buộc authenticated. Không gọi endpoint internet thật và không khởi tạo authorization server thật trong bài test mô phỏng.

## 6. Chọn client theo request: explicit và registration ID

Hai cách phổ biến khi gọi WebClient:

```java
// 1) Đã có OAuth2AuthorizedClient (ví dụ từ controller argument):
webClient.get()
        .uri(resourceUri)
        .attributes(oauth2AuthorizedClient(authorizedClient))
        .retrieve()
        .bodyToMono(String.class);

// 2) Chỉ có registrationId; manager/repository cần giải quyết client:
webClient.get()
        .uri(resourceUri)
        .attributes(clientRegistrationId("catalog"))
        .retrieve()
        .bodyToMono(String.class);
```

Các đoạn là **mảnh lệnh trong phương thức**, cần biến `webClient`, `resourceUri` và các static import:
```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;
```

Cách 1 truyền đối tượng cụ thể mà `mockOAuth2Client()` tạo. Cách 2 đặt yêu cầu tìm/authorize theo registration ID; để kiểm thử không gọi token endpoint ngoài ý muốn, cấu hình mock manager hoặc repository/registration tương ứng. `setDefaultOAuth2AuthorizedClient(true)` hay `setDefaultClientRegistrationId("catalog")` có thể cho phép không khai báo attribute, nhưng phải thận trọng: mặc định có thể gắn token vào **mọi request** mà WebClient đó gửi, kể cả host không chủ định. Với nhiều downstream, ưu tiên chọn client tường minh trên từng request.

`ReactiveOAuth2AuthorizedClientManager` xử lý vòng đời token: nếu không có client, có thể thực hiện grant; nếu hết hạn, có thể refresh/cấp lại khi provider hỗ trợ. Những nhánh này **không được chứng minh** bởi bài test dùng token và manager giả trả về sẵn.

## 7. Ma trận kiểm thử quan trọng

| Kịch bản | Chuẩn bị | Assert chính |
| --- | --- | --- |
| Authorized client cơ bản | `mockOAuth2Client("catalog")` | Controller nhận đúng registration ID/client |
| Token tùy chỉnh | `.accessToken(token)` | Giá trị Bearer gửi đi đúng chính xác |
| Principal tùy chỉnh | `.principalName("alice")` | Controller nhận `alice`; nếu route authenticated, mock authentication riêng |
| Phân nhánh scope | Token giả có/không có `item.read` | Ứng dụng đi đúng nhánh nghiệp vụ, không suy từ authorities |
| Client bị chọn sai | Hai registration khác nhau, chọn explicit | Không gửi token của client A sang downstream của client B |
| Không có client mặc định | Không truyền attribute, không có default | Xác nhận hành vi khi không resolve được client; không mong tự có Bearer |
| Downstream trả 401/403 | Mock HTTP server trả status tương ứng | Xác nhận cách ứng dụng map lỗi và cơ chế xử lý authorization failure đã cấu hình |
| Token hết hạn | Manager/provider giả trả về token mới hoặc lỗi | Kiểm tra refresh/re-authorization ở test riêng, không kỳ vọng `mockOAuth2Client()` tự refresh |
| Endpoint đòi login | Thêm `mockUser`/`mockOAuth2Login` theo flow | Phân biệt lỗi 401/redirect inbound và lỗi Bearer outbound |

Test HTTP nên assert **giá trị header thực tế** ở điểm downstream. Chỉ xác nhận status `200` của controller không đủ: controller có thể trả body giả, còn WebClient chưa gắn token hoặc đã chọn sai registration.

## 8. Những lỗi phổ biến và cách kiểm tra

1. **Nhầm `mockOAuth2Client` với `mockOAuth2Login`.** Có authorized client nhưng không có authenticated user; route bảo vệ vẫn trả `401` hoặc redirect. Kiểm tra security rules, bổ sung mock authentication tương ứng.
2. **Dùng `mockJwt()` để giả lập outbound OAuth2 Client.** JWT mock tạo principal cho resource server inbound, không nạp `OAuth2AuthorizedClient` cho `@RegisteredOAuth2AuthorizedClient`.
3. **Sai `registrationId`.** `@RegisteredOAuth2AuthorizedClient("catalog")` phải khớp ID đã mock/cấu hình; `clientId` không phải `registrationId`.
4. **Có mock client nhưng WebClient thiếu OAuth2 filter.** Khi đó không có gì tự sinh header Bearer. Kiểm tra bean WebClient được inject, loại filter và request attributes.
5. **Có filter nhưng không chỉ định authorized client.** Nếu không có default, filter có thể chuyển request đi mà không có Bearer. Dùng `oauth2AuthorizedClient(client)` hoặc `clientRegistrationId("catalog")` theo mục đích.
6. **Nhầm scopes trong token với Spring authorities.** `Set.of("item.read")` là `OAuth2AccessToken.getScopes()`; quyền cho `@PreAuthorize` hoặc `authorizeExchange` đến từ Authentication và thường cần mock riêng.
7. **Access token giả đã hết hạn.** Manager có thể cố refresh/cấp lại qua mạng. Dùng token còn hiệu lực khi test header; kiểm thử hết hạn ở test riêng với provider giả.
8. **Bất ngờ gọi authorization server thật.** Cấu hình repository/manager hoặc registration không khớp, khiến grant bắt đầu. Trong test outbound, dùng stub manager/HTTP server; không đưa client secret thật vào test.
9. **Dùng API servlet trong project reactive.** `MockMvc`/`oauth2Client()` kiểu servlet và `ServletOAuth2AuthorizedClientExchangeFilterFunction` khác với `WebTestClient`/`mockOAuth2Client()`/`ServerOAuth2AuthorizedClientExchangeFilterFunction`.
10. **Sử dụng `block()` trong controller/service reactive.** Nó có thể chặn event loop. Trả `Mono`/`Flux` từ WebClient; chỉ `block()` trong ví dụ unit test đồng bộ.
11. **Lộ token trong log.** Chỉ sử dụng giá trị giả để assert; với token thật, kiểm tra sự hiện diện hoặc fingerprint an toàn, không in token hoặc client secret.
12. **Suy diễn quá mức từ mock.** `mockOAuth2Client()` không chứng minh authorization code redirect, PKCE, refresh, lưu session thật, TLS, hay IdP hoạt động; cần integration/end-to-end test tương ứng.

## 9. Tự kiểm tra sau bài

- Giải thích được vì sao `mockOAuth2Client("catalog")` không tự cấp quyền `authenticated()` cho endpoint.
- Chỉ ra chính xác nơi `OAuth2AuthorizedClient` đi từ controller vào `ClientRequest.attributes()`.
- Viết được một test assert `Authorization: Bearer fake-token-123` ở `ExchangeFunction` hoặc mock HTTP server.
- Nêu được sự khác nhau giữa kiểm thử **token forwarding**, **client selection**, **token refresh** và **OAuth2 login**.
- Khi test trả `401`, biết xác định lỗi thuộc inbound security hay outbound downstream.

## Tài liệu đối chiếu

- Spring Security – Testing OAuth 2.0 (Reactive): https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security – Authorized Client Features (Reactive): https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html
- Javadoc – SecurityMockServerConfigurers: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html
- Javadoc – ServerOAuth2AuthorizedClientExchangeFilterFunction: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html
