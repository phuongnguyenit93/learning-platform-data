# 29.11. Kiểm thử client manager, refresh và lưu authorized client

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client** chạy trên Servlet stack, login thành công mới chỉ là một phần của hệ thống. Khi ứng dụng gọi downstream API, `OAuth2AuthorizedClientManager` phải phối hợp nhiều thành phần để:

- Tìm đúng `ClientRegistration`.
- Tải `OAuth2AuthorizedClient` đã có của principal từ repository/service.
- **Tái sử dụng access token** còn hiệu lực mà không gọi token endpoint không cần thiết.
- **Refresh access token** khi gần hết hạn hoặc đã hết hạn, nếu có refresh token hợp lệ.
- Lưu access token/refresh token mới sau khi reauthorization thành công.
- Xử lý `invalid_grant` hoặc lỗi khác theo failure policy.
- Không trộn token giữa các principals, registrations và tenants.

Đây là những hành vi phải được **kiểm thử riêng** thay vì mặc định rằng “Spring Security tự quản lý token nên không cần test”.

Bài này tập trung vào **29. Kiểm thử Servlet**: dùng JUnit 5, Spring Security Test, `MockHttpServletRequest`/`MockHttpServletResponse`, `OAuth2AuthorizedClientService` và fake token-response client để kiểm tra hành vi của manager mà **không cần kết nối Authorization Server thật**.

Sau bài học, bạn có thể:

1. Phân biệt `ClientRegistrationRepository`, `OAuth2AuthorizedClientRepository`, `OAuth2AuthorizedClientService` và `OAuth2AuthorizedClientManager`.
2. Hiểu manager load token, gọi provider, xử lý kết quả, save token và failure như thế nào.
3. Dựng test fixture `ClientRegistration`, principal, access/refresh tokens và request/response Servlet.
4. Kiểm tra token còn hạn được tái sử dụng, không refresh.
5. Kiểm tra token đã hết hạn được refresh khi có refresh token.
6. Sử dụng `RefreshTokenOAuth2AuthorizedClientProvider` với fake `OAuth2AccessTokenResponseClient` thay vì gọi token endpoint thật.
7. Kiểm tra refresh token rotation R1 → R2 và việc ghi lại authorized client.
8. Kiểm tra expired token không có refresh token hoặc grant không được hỗ trợ.
9. Kiểm tra `invalid_grant` và xóa authorized client theo failure handler.
10. Kiểm tra principal/registration isolation trong store.
11. Kiểm tra custom success/failure handlers, repository interaction và persistence.
12. Biết khi nào dùng `DefaultOAuth2AuthorizedClientManager` và khi nào dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager`.
13. Phân biệt test bằng fake provider, mock HTTP token endpoint và integration test đa instance.
14. Thiết kế test về clock skew, concurrent refresh, lỗi lưu, logout và token revocation.
15. Không nhầm OIDC login test `oidcLogin()` với kiểm thử refresh token và authorized client persistence.

---

## 1. Bối cảnh: Portal gọi Orders API nhiều lần

Giả sử ứng dụng **Orders Portal** đăng nhập nhân viên qua OIDC và gọi Orders API bằng OAuth access token.

~~~text
Browser
  -> Orders Portal (Servlet session)
      -> OAuth2AuthorizedClientManager
          -> Authorized client repository/service
          -> OAuth2AuthorizedClientProvider
          -> Authorization Server token endpoint khi cần
      -> Orders API (Bearer access token)
~~~

Một user Alice đăng nhập lúc 09:00. Authorization Server trả:

~~~text
access_token = A1
expires_at   = 10:00
refresh_token = R1
registrationId = orders-client
principalName = alice
~~~

Các request tiếp theo tạo ra ba tình huống:

| Thời điểm | Trạng thái | Hành vi mong muốn |
|---|---|---|
| 09:05 | A1 vẫn còn hạn | Dùng lại A1, không refresh |
| 09:59:30 | A1 gần hết hạn theo clock skew | Có thể refresh bằng R1 |
| 10:10 | A1 hết hạn, R1 hợp lệ | Xin A2 và lưu token mới |

Nếu AS sử dụng refresh token rotation:

~~~text
R1 -> token endpoint -> A2 + R2
~~~

thì store cần cập nhật **cả A2 và R2**. Nếu chỉ cập nhật access token mà giữ refresh token cũ, lần refresh sau có thể thất bại hoặc kích hoạt reuse detection.

### 1.1. Test cần chứng minh điều gì?

Không chỉ kiểm tra `manager.authorize(...)` trả về object khác null.

Cần quan sát:

1. Authorization context manager đã dùng.
2. Provider nào được gọi và có gửi refresh request hay không.
3. Token nào được trả.
4. Có lưu `OAuth2AuthorizedClient` mới hay không.
5. Store đang chứa access/refresh tokens nào sau lệnh.
6. Khi lỗi, store có bị xóa hoặc giữ lại đúng policy không.
7. Alice và Bob có bị dùng chung token không.

### 1.2. Những lỗi thường bị bỏ qua

- Token còn hạn nhưng mỗi API call lại xin token mới.
- Token hết hạn nhưng refresh không được kích hoạt.
- Token refresh thành công nhưng không lưu R2.
- Repository key thiếu principal nên Alice dùng token Bob.
- `invalid_grant` nhưng token cũ còn nằm trong cache.
- Refresh hai request đồng thời làm R2 bị ghi đè bằng R1.
- Background job dùng manager phụ thuộc `HttpServletRequest`.
- Test chỉ mock `manager.authorize()` nên không kiểm tra manager thật.

## 2. Sơ đồ trách nhiệm của các thành phần

~~~mermaid
flowchart TD
    A["Application gọi authorize()"] --> M["OAuth2AuthorizedClientManager"]
    M --> REG["ClientRegistrationRepository"]
    M --> STORE["OAuth2AuthorizedClientRepository / Service"]
    STORE --> M
    M --> P["OAuth2AuthorizedClientProvider"]
    P --> D{"Token còn hạn / grant?"}
    D -->|"Reuse"| M
    D -->|"Refresh cần thiết"| TOKEN["OAuth2AccessTokenResponseClient"]
    TOKEN -->|"Token response"| P
    P -->|"AuthorizedClient mới"| M
    M -->|"Success handler: save"| STORE
    M -->|"Failure handler: remove/policy"| STORE
    M --> A
~~~

Sơ đồ ở mức khái niệm. Trong code, manager có thể gọi provider ngay cả khi token đang còn hạn; **provider trả `null`** để báo không cần/không thể thực hiện reauthorization. Khi đó manager thường trả lại authorized client hiện có.

### 2.1. `ClientRegistrationRepository`

Lưu **cấu hình client**, chẳng hạn:

~~~text
registrationId = orders-client
clientId = portal-web
authorizationGrantType = authorization_code
authorizationUri = ...
tokenUri = ...
scope = orders.read
~~~

Nó không lưu access token riêng của Alice.

### 2.2. `OAuth2AuthorizedClient`

Đại diện cho authorization đã cấp cho một principal và registration:

~~~text
registration = orders-client
principalName = alice
accessToken = A1
refreshToken = R1
~~~

### 2.3. `OAuth2AuthorizedClientRepository`

Giao diện dành cho ngữ cảnh Servlet web request:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
        String clientRegistrationId,
        Authentication principal,
        HttpServletRequest request);

void saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal,
        HttpServletRequest request,
        HttpServletResponse response);

void removeAuthorizedClient(
        String clientRegistrationId,
        Authentication principal,
        HttpServletRequest request,
        HttpServletResponse response);
~~~

Repository có thể dựa trên session hoặc ủy quyền lưu cho `OAuth2AuthorizedClientService`.

### 2.4. `OAuth2AuthorizedClientService`

API lưu/đọc/xóa authorized client theo `registrationId` và `principalName`, không yêu cầu Servlet request:

~~~java
<T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
        String clientRegistrationId, String principalName);

void saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal);

void removeAuthorizedClient(
        String clientRegistrationId, String principalName);
~~~

Có thể triển khai in-memory, JDBC hoặc custom persistent store.

### 2.5. `OAuth2AuthorizedClientManager`

Điều phối cách lấy authorized client cho ứng dụng. Hai implementation quan trọng:

| Manager | Ngữ cảnh thường dùng |
|---|---|
| `DefaultOAuth2AuthorizedClientManager` | Trong Servlet request/response |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Background jobs, service layer ngoài Servlet request |

### 2.6. `OAuth2AuthorizedClientProvider`

Quyết định grant cụ thể:

- `authorizationCode()`.
- `refreshToken()`.
- `clientCredentials()`.
- Những provider tùy chỉnh nếu ứng dụng hỗ trợ.

Provider có thể trả authorized client mới hoặc `null` khi không thể/không cần thực hiện grant.

## 3. Vòng đời một lệnh `authorize()`

Ví dụ application code gọi:

~~~java
OAuth2AuthorizedClient client =
        authorizedClientManager.authorize(authorizeRequest);
~~~

Một luồng xử lý điển hình:

1. Manager tìm registration và/hoặc authorized client hiện có.
2. Dựng `OAuth2AuthorizationContext` chứa registration, principal, authorized client và attributes.
3. Gọi authorized client provider chain.
4. Nếu provider trả `null`, manager có thể trả authorized client cũ.
5. Nếu provider trả client mới, manager gọi success handler để lưu.
6. Nếu provider báo authorization failure, manager gọi failure handler.
7. Kết quả được trả về application hoặc exception được truyền ra.

### 3.1. Ba kết quả cần phân biệt

| Kết quả của provider | Hành vi manager thường thấy | Ý nghĩa |
|---|---|---|
| `null` khi client cũ tồn tại | Trả client cũ | Không có reauthorization mới |
| `OAuth2AuthorizedClient` mới | Gọi success handler, trả client mới | Authorization/refresh thành công |
| Exception | Gọi failure handler rồi truyền lỗi | Grant hoặc token endpoint thất bại |

### 3.2. Không đồng nhất provider invocation và network request

Manager có thể gọi `RefreshTokenOAuth2AuthorizedClientProvider.authorize(...)` cho mỗi lần application gọi `authorize()`.

Khi access token còn hạn, provider **không nhất thiết gọi token endpoint**. Test nên đếm số lần fake token-response client được gọi, không chỉ đếm provider invocation.

### 3.3. Không có refresh token không có nghĩa có authorization code mới

Refresh provider không thể xin access token mới nếu không có refresh token. Với Authorization Code flow, việc bắt đầu interactive browser redirect là trách nhiệm của OAuth2 Login/Authorization Request filters, **không phải một token endpoint call mà manager tự nghĩ ra**.

## 4. Test dependencies

### 4.1. Maven

~~~xml
<dependencies>
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

`spring-security-test` cần cho các MockMvc security helpers nếu bạn test controller; những test manager thuần JUnit cũng có thể dùng `spring-test`/Mockito/AssertJ từ Boot test starter.

### 4.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 4.3. Vì sao không cần AS production?

Trong unit/component tests, fake `OAuth2AccessTokenResponseClient` có thể trả token response do test dựng. Nhờ vậy bạn kiểm tra manager/provider/storage mà không gửi refresh token qua mạng.

Nhưng HTTP request serialization, Basic client authentication, network timeout hoặc AS-specific JSON response vẫn cần **HTTP integration test** riêng.

## 5. Dựng `ClientRegistration` test fixture

Registration phải có đủ thông tin mà grant/provider yêu cầu.

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;

public final class TestRegistrations {

    private TestRegistrations() {}

    public static ClientRegistration orders() {
        return ClientRegistration
                .withRegistrationId("orders-client")
                .clientId("portal-test-client")
                .clientSecret("test-secret-not-production")
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .authorizationUri("https://op.example.test/authorize")
                .tokenUri("https://op.example.test/token")
                .scope("openid", "orders.read")
                .clientName("Orders Test Client")
                .build();
    }
}
~~~

### 5.1. Những giá trị quan trọng

- `registrationId`: dùng để load/save token theo client.
- `clientId`: OAuth client được AS đăng ký.
- `authorizationGrantType`: grant ban đầu.
- `tokenUri`: nơi provider sẽ gọi trong flow thực.
- `scope`: phạm vi token.
- `redirectUri`/`authorizationUri`: cần với Authorization Code registration.

### 5.2. Không cần discovery thật trong test này

Nếu chỉ test manager bằng fake token response, registration fixture có thể khai báo endpoints giả và không cần gọi `issuer-uri` metadata discovery.

Nếu dùng Spring Boot context tự build ClientRegistration từ `issuer-uri`, có thể xuất hiện network discovery khi khởi tạo. Nên tách test fixture/repository để không liên lạc OP production.

### 5.3. Không dùng credential thật

`clientSecret` ở đây chỉ là chuỗi giả. Mọi access/refresh token fixtures cũng phải là dữ liệu giả.

## 6. Tạo access token và refresh token giả

Token APIs:

~~~java
import java.time.Instant;
import java.util.Set;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

public final class TestTokens {

    private TestTokens() {}

    public static OAuth2AccessToken accessToken(
            String value,
            Instant issuedAt,
            Instant expiresAt) {

        return new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                value,
                issuedAt,
                expiresAt,
                Set.of("orders.read"));
    }

    public static OAuth2RefreshToken refreshToken(
            String value,
            Instant issuedAt) {

        return new OAuth2RefreshToken(value, issuedAt);
    }
}
~~~

### 6.1. Clock dùng chung cho test

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock clock = Clock.fixed(
        Instant.parse("2026-11-16T10:00:00Z"),
        ZoneOffset.UTC);
~~~

Test cố định clock giúp không bị fail ngẫu nhiên ở ranh giới thời gian.

### 6.2. Token còn hạn

~~~text
now = 10:00:00
accessToken.expiresAt = 11:00:00
clockSkew = 60 seconds

=> Chưa cần refresh.
~~~

### 6.3. Token sắp hết hạn

~~~text
now = 10:00:00
accessToken.expiresAt = 10:00:20
clockSkew = 60 seconds

=> Có thể refresh sớm.
~~~

### 6.4. Token hết hạn

~~~text
now = 10:00:00
accessToken.expiresAt = 09:59:00

=> Refresh nếu có R1 và grant/provider hỗ trợ.
~~~

## 7. Test harness cho Servlet manager

Dùng các thành phần thật ở mức in-memory:

~~~java
import org.springframework.security.oauth2.client.registration
        .InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.client
        .InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web
        .AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web
        .DefaultOAuth2AuthorizedClientManager;

var registration = TestRegistrations.orders();

var registrations =
        new InMemoryClientRegistrationRepository(registration);

var service =
        new InMemoryOAuth2AuthorizedClientService(registrations);

var repository =
        new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(service);

var manager =
        new DefaultOAuth2AuthorizedClientManager(
                registrations, repository);
~~~

### 7.1. Vì sao chọn `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`?

Với principal đã authenticated, repository có thể ủy quyền lưu/đọc qua `OAuth2AuthorizedClientService`. Vì thế test có thể kiểm tra service chứa token mới sau khi manager authorize.

Ở luồng anonymous, implementation có thể dùng session-backed repository khác. Bài này chủ yếu test **authenticated principal**.

### 7.2. Principal cho test manager

Không bắt buộc khởi tạo OIDC Login nếu chỉ muốn test manager.

~~~java
import org.springframework.security.authentication
        .UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.AuthorityUtils;

var alice = UsernamePasswordAuthenticationToken.authenticated(
        "alice",
        "test-only",
        AuthorityUtils.createAuthorityList("ROLE_USER"));
~~~

Manager cần một `Authentication` để xác định principal name. Authentication ở đây là fixture test; nó **không** đại diện OIDC authentication flow thật.

### 7.3. Servlet request/response giả

~~~java
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

var servletRequest = new MockHttpServletRequest();
var servletResponse = new MockHttpServletResponse();
~~~

### 7.4. Xây `OAuth2AuthorizeRequest`

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;

OAuth2AuthorizeRequest authorization =
        OAuth2AuthorizeRequest
                .withClientRegistrationId("orders-client")
                .principal(alice)
                .attribute(
                        HttpServletRequest.class.getName(),
                        servletRequest)
                .attribute(
                        HttpServletResponse.class.getName(),
                        servletResponse)
                .build();
~~~

Hai attributes request/response giúp `DefaultOAuth2AuthorizedClientManager` có Servlet context cần thiết mà không dựa vào một HTTP request thực hoặc `RequestContextHolder` toàn cục.

### 7.5. Vì sao không chỉ gọi `manager.authorize()`?

Interface manager không có parameterless authorization. Nó cần `OAuth2AuthorizeRequest` chỉ rõ client/principal và, đối với Servlet manager, request context.

Nếu không truyền Servlet request/response hoặc không có request context ở thread, test có thể lỗi vì thiếu request attributes.

## 8. Cấu hình fake refresh token response client

Muốn test **logic refresh thật của Spring Security provider** nhưng không gọi AS, sử dụng `RefreshTokenOAuth2AuthorizedClientProvider` với fake response client.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.oauth2.client
        .RefreshTokenOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.endpoint
        .OAuth2AccessTokenResponse;

AtomicInteger refreshHttpCalls = new AtomicInteger();

RefreshTokenOAuth2AuthorizedClientProvider provider =
        new RefreshTokenOAuth2AuthorizedClientProvider();

provider.setClock(clock);
provider.setClockSkew(Duration.ofSeconds(60));

provider.setAccessTokenResponseClient(grant -> {
    refreshHttpCalls.incrementAndGet();

    // Không có HTTP thật. grant chứa refresh token của flow.
    org.assertj.core.api.Assertions.assertThat(
            grant.getRefreshToken().getTokenValue())
            .isEqualTo("refresh-R1");

    return OAuth2AccessTokenResponse
            .withToken("access-A2")
            .tokenType(OAuth2AccessToken.TokenType.BEARER)
            .expiresIn(3600)
            .refreshToken("refresh-R2")
            .scopes(Set.of("openid", "orders.read"))
            .build();
});

manager.setAuthorizedClientProvider(provider);
~~~

### 8.1. Fake này vẫn kiểm thử provider decision

`RefreshTokenOAuth2AuthorizedClientProvider` thực sự quyết định có nên refresh không dựa trên:

- Access token expiry.
- Clock và clock skew.
- Refresh token có tồn tại không.
- Authorization context.

Chỉ phần **HTTP token exchange** được fake bằng callback trả `OAuth2AccessTokenResponse`.

### 8.2. Không nhầm với mock toàn bộ manager

Nếu bạn viết:

~~~java
when(manager.authorize(any()))
        .thenReturn(newAuthorizedClient);
~~~

thì không kiểm tra được manager có load/save authorized client hay không. Fake token-response client là mức mô phỏng **sâu hơn** và hữu ích hơn cho hành vi manager/provider/storage.

### 8.3. Không hardcode clock hiện tại

Một fake response có `expiresIn(3600)`. Provider có thể tạo token timestamps dựa trên response và đồng hồ. Với test refresh branch, điều quan trọng là access token *cũ* được xây nhất quán với fixed clock để kích hoạt/không kích hoạt refresh đúng dự kiến.

## 9. Test 1 — Token còn hạn được tái sử dụng

Mục tiêu:

~~~text
Repository đang chứa:
  registration = orders-client
  principal = alice
  accessToken = access-A1 (còn hạn)
  refreshToken = refresh-R1

manager.authorize():
  -> trả lại access-A1
  -> không gọi token response client
  -> không tạo refresh token mới
~~~

### 9.1. Tạo authorized client còn hạn

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

Instant now = clock.instant();

OAuth2AuthorizedClient active =
        new OAuth2AuthorizedClient(
                registration,
                "alice",
                TestTokens.accessToken(
                        "access-A1",
                        now.minusSeconds(300),
                        now.plusSeconds(3600)),
                TestTokens.refreshToken(
                        "refresh-R1",
                        now.minusSeconds(300)));
~~~

### 9.2. Lưu client vào repository

~~~java
repository.saveAuthorizedClient(
        active,
        alice,
        servletRequest,
        servletResponse);
~~~

### 9.3. Gọi manager và kiểm tra

~~~java
OAuth2AuthorizedClient result =
        manager.authorize(authorization);

assertThat(result).isNotNull();

assertThat(result.getAccessToken().getTokenValue())
        .isEqualTo("access-A1");

assertThat(refreshHttpCalls.get())
        .isZero();

OAuth2AuthorizedClient stored =
        service.loadAuthorizedClient(
                "orders-client", "alice");

assertThat(stored.getAccessToken().getTokenValue())
        .isEqualTo("access-A1");

assertThat(stored.getRefreshToken().getTokenValue())
        .isEqualTo("refresh-R1");
~~~

### 9.4. Ý nghĩa assertion

- Token cũ được tái sử dụng.
- Không xảy ra refresh HTTP giả.
- Store vẫn giữ access/refresh token cũ.

Nếu muốn xác minh **không phát sinh lần save nào** khi tái sử dụng, có thể dùng repository spy và `Mockito.verify(..., never()).saveAuthorizedClient(...)`; nhưng cần reset spy sau bước seed dữ liệu.

### 9.5. Đừng chỉ assert token bằng object identity

Manager có thể trả cùng object hoặc object tương đương tùy implementation. Assertion trên token values/expiry và interactions ổn định hơn kỳ vọng `assertSame` không được contract bảo đảm.

## 10. Test 2 — Token hết hạn được refresh và ghi vào store

Mục tiêu:

~~~text
Before:
  access = access-A1 (expired)
  refresh = refresh-R1

Provider calls fake token response client:
  refresh-R1 -> access-A2 + refresh-R2

After:
  manager returns access-A2
  service stores access-A2 + refresh-R2
~~~

### 10.1. Seed expired authorized client

~~~java
Instant now = clock.instant();

OAuth2AuthorizedClient expired =
        new OAuth2AuthorizedClient(
                registration,
                "alice",
                TestTokens.accessToken(
                        "access-A1",
                        now.minusSeconds(7200),
                        now.minusSeconds(60)),
                TestTokens.refreshToken(
                        "refresh-R1",
                        now.minusSeconds(7200)));

repository.saveAuthorizedClient(
        expired,
        alice,
        servletRequest,
        servletResponse);
~~~

### 10.2. Authorize với refresh provider

~~~java
OAuth2AuthorizedClient refreshed =
        manager.authorize(authorization);
~~~

### 10.3. Kiểm tra kết quả

~~~java
assertThat(refreshed).isNotNull();

assertThat(refreshed.getAccessToken().getTokenValue())
        .isEqualTo("access-A2");

assertThat(refreshed.getRefreshToken().getTokenValue())
        .isEqualTo("refresh-R2");

assertThat(refreshHttpCalls.get())
        .isEqualTo(1);
~~~

### 10.4. Kiểm tra storage sau refresh

~~~java
OAuth2AuthorizedClient persisted =
        service.loadAuthorizedClient(
                "orders-client", "alice");

assertThat(persisted).isNotNull();

assertThat(persisted.getAccessToken().getTokenValue())
        .isEqualTo("access-A2");

assertThat(persisted.getRefreshToken().getTokenValue())
        .isEqualTo("refresh-R2");
~~~

Đây là assertion **quan trọng**: thành công của manager không đủ nếu token mới chỉ nằm trong biến local nhưng chưa được save vào repository/service.

### 10.5. Kiểm tra registration và principal

~~~java
assertThat(persisted.getClientRegistration()
        .getRegistrationId())
        .isEqualTo("orders-client");

assertThat(persisted.getPrincipalName())
        .isEqualTo("alice");
~~~

Nếu test chỉ kiểm tra access token value mà không kiểm tra principal/registration, bạn có thể bỏ sót lỗi ghi token vào record của người khác.

## 11. Test 3 — Refresh sớm do clock skew

Nhiều applications cần refresh trước thời điểm expiry để tránh access token hết hạn giữa lúc request đang đi tới API.

Giả sử:

~~~text
Clock now = 10:00:00
Access expiresAt = 10:00:20
Clock skew = 60s

Token chưa hết hạn theo đồng hồ,
nhưng nằm trong ngưỡng refresh.
~~~

Test:

~~~java
Instant now = clock.instant();

OAuth2AuthorizedClient almostExpired =
        new OAuth2AuthorizedClient(
                registration,
                "alice",
                TestTokens.accessToken(
                        "access-A1",
                        now.minusSeconds(300),
                        now.plusSeconds(20)),
                TestTokens.refreshToken(
                        "refresh-R1",
                        now.minusSeconds(300)));

repository.saveAuthorizedClient(
        almostExpired, alice, servletRequest, servletResponse);

OAuth2AuthorizedClient result =
        manager.authorize(authorization);

assertThat(result.getAccessToken().getTokenValue())
        .isEqualTo("access-A2");

assertThat(refreshHttpCalls.get())
        .isEqualTo(1);
~~~

### 11.1. Điều test xác minh

- Refresh provider dùng clock skew.
- Không chờ token hết hạn chính xác mới refresh.
- Manager lưu kết quả mới qua success handler.

### 11.2. Không đặt clock skew quá lớn mù quáng

Skew quá lớn có thể tạo token refresh thừa, tăng tải AS và gây concurrency issues.

Skew cần dựa trên latency, clock synchronization và policy của AS/API.

### 11.3. Để test không flaky

Dùng `Clock.fixed(...)` hoặc thời điểm token cách xa boundary. Không dùng `Instant.now()` rải rác rồi kỳ vọng exact expiry branch khi test chạy nhanh/chậm khác nhau.

## 12. Test 4 — Không có refresh token

Một `OAuth2AuthorizedClient` có thể chỉ có access token:

~~~java
OAuth2AuthorizedClient withoutRefreshToken =
        new OAuth2AuthorizedClient(
                registration,
                "alice",
                TestTokens.accessToken(
                        "expired-A1",
                        now.minusSeconds(3600),
                        now.minusSeconds(120)));
~~~

Khi chỉ cấu hình refresh-token provider, nó **không thể refresh** vì không có refresh token.

### 12.1. Kỳ vọng quan trọng

Không nên viết test kỳ vọng manager tự trả A2 mà không có grant/cơ chế cấp token phù hợp.

Với một authorized client cũ mà provider trả `null`, manager có thể trả client cũ; **application không được xem token expired đó là sử dụng được**.

### 12.2. Assertion hành vi

~~~java
repository.saveAuthorizedClient(
        withoutRefreshToken,
        alice,
        servletRequest,
        servletResponse);

OAuth2AuthorizedClient result =
        manager.authorize(authorization);

assertThat(refreshHttpCalls.get()).isZero();

// Nếu manager trả lại client cũ,
// application phải có chính sách reauthorize/fail.
assertThat(result.getAccessToken().getTokenValue())
        .isEqualTo("expired-A1");
~~~

Đây là ví dụ theo behavior của `DefaultOAuth2AuthorizedClientManager` với refresh-only provider và client đã lưu. Nếu ứng dụng thêm provider/handler tùy chỉnh, hãy xác định contract mới trong test.

### 12.3. Authorization Code cần browser flow

Nếu token đã hết hạn và không refresh được, ứng dụng có thể cần bắt đầu lại Authorization Code flow để user/AS cấp token mới.

Không gọi token endpoint bằng một authorization code không tồn tại.

### 12.4. Khi API trả 401

Nếu access token hết hạn/không còn hợp lệ, outbound API client có thể nhận 401. Ứng dụng cần xử lý reauthorization/session UX theo policy, không retry mãi với token expired.

## 13. Test 5 — `invalid_grant` khi refresh

Authorization Server có thể từ chối refresh token vì:

- Refresh token đã hết hạn.
- Refresh token bị revoke.
- Refresh token đã được rotate và R1 cũ không còn hợp lệ.
- Refresh token reuse detection.
- Client/grant policy thay đổi.

Đối với `invalid_grant`, Spring Security default failure handling thường xóa authorized client cũ để tránh liên tục sử dụng token không còn hợp lệ.

### 13.1. Fake token response client ném lỗi

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;

provider.setAccessTokenResponseClient(grant -> {
    throw new OAuth2AuthorizationException(
            new OAuth2Error(
                    "invalid_grant",
                    "Refresh token invalid",
                    null));
});
~~~

### 13.2. Gọi manager và kiểm tra exception

~~~java
import org.springframework.security.oauth2.client.ClientAuthorizationException;

assertThatThrownBy(() ->
        manager.authorize(authorization))
        .isInstanceOf(ClientAuthorizationException.class);
~~~

### 13.3. Kiểm tra record đã bị remove

~~~java
OAuth2AuthorizedClient persisted =
        service.loadAuthorizedClient(
                "orders-client", "alice");

assertThat(persisted).isNull();
~~~

Test này giả định manager dùng default failure handler phù hợp, repository lưu authenticated principal qua service và provider chuyển lỗi refresh thành authorization failure đúng loại.

### 13.4. Không phải mọi lỗi đều dẫn tới xóa token

Một lỗi mạng tạm thời hoặc AS 503 không tự động có nghĩa refresh token bị thu hồi.

Failure handler và policy ứng dụng cần phân biệt:

- `invalid_grant`: thường remove stale authorized client.
- 5xx/timeouts: có thể retry có giới hạn.
- Invalid client/misconfiguration: alert/stop retry vô ích.
- Domain permission/API 403: thường không sửa được bằng refresh.

### 13.5. Không swallow exception trong test

Một test chỉ `assertDoesNotThrow` rồi bỏ qua kết quả có thể che lỗi token store/AS. Kiểm tra cả exception type, error code và post-failure storage state theo policy.

## 14. Test 6 — Save handler được gọi sau authorization thành công

Manager có `OAuth2AuthorizationSuccessHandler`. Với cấu hình mặc định Servlet, handler có thể lưu authorized client vào repository.

Có thể thử riêng nhánh success bằng một fake provider:

~~~java
import org.springframework.security.oauth2.client
        .OAuth2AuthorizedClientProvider;

OAuth2AuthorizedClientProvider fakeProvider = context -> {
    ClientRegistration reg = context.getClientRegistration();

    return new OAuth2AuthorizedClient(
            reg,
            context.getPrincipal().getName(),
            TestTokens.accessToken(
                    "new-access",
                    clock.instant(),
                    clock.instant().plusSeconds(3600)));
};

manager.setAuthorizedClientProvider(fakeProvider);
~~~

### 14.1. Test lần đầu chưa có authorized client

~~~java
OAuth2AuthorizedClient result =
        manager.authorize(authorization);

assertThat(result.getAccessToken().getTokenValue())
        .isEqualTo("new-access");

assertThat(service.loadAuthorizedClient(
        "orders-client", "alice"))
        .isNotNull();
~~~

### 14.2. Đây là test orchestration, không phải Authorization Code grant thật

Fake provider tự trả authorized client để kiểm tra manager save, **không mô phỏng OP phát authorization code**.

Nếu muốn kiểm tra Browser Authorization Code flow, phải dùng test OAuth2 Login filters/callback với mock OP.

### 14.3. Spy repository

Khi cần kiểm tra chính xác số lần save:

~~~java
OAuth2AuthorizedClientRepository spyRepository =
        org.mockito.Mockito.spy(repository);
~~~

Sau đó tạo manager với spy repository và dùng:

~~~java
org.mockito.Mockito.verify(spyRepository,
        org.mockito.Mockito.times(1))
        .saveAuthorizedClient(
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.eq(alice),
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any());
~~~

Nếu trước đó bạn seed dữ liệu bằng spy, cần `clearInvocations(...)` hoặc reset sau bước setup; nếu không, save ban đầu có thể làm assertion sai.

## 15. Test 7 — Provider trả `null` thì không save token mới

Một provider có thể thấy token còn hạn và trả `null`.

~~~java
OAuth2AuthorizedClientProvider noReauthorization =
        context -> null;

manager.setAuthorizedClientProvider(noReauthorization);
~~~

Khi repository đã có A1:

~~~java
OAuth2AuthorizedClient result =
        manager.authorize(authorization);

assertThat(result.getAccessToken().getTokenValue())
        .isEqualTo("access-A1");
~~~

### 15.1. Phân biệt load và save

Manager có thể gọi repository `loadAuthorizedClient` để tìm record. Nhưng vì provider không trả token mới, default success handler không cần save một authorization mới.

Nếu đây là yêu cầu quan trọng, dùng spy để kiểm tra absence of save sau khi seed.

### 15.2. Null khi chưa có authorized client

Nếu không có record cũ và provider không hỗ trợ grant hiện tại, manager có thể trả `null`. Application cần xử lý trạng thái “chưa được authorized” thay vì dereference token.

~~~java
OAuth2AuthorizedClient client =
        manager.authorize(authorization);

if (client == null) {
    // Initiate a supported authorization flow or fail clearly.
}
~~~

Không dùng `NullPointerException` làm cơ chế điều hướng user.

## 16. Test 8 — Principal isolation

Giả sử Alice và Bob cùng dùng registration `orders-client`.

~~~text
orders-client + alice -> A-alice / R-alice
orders-client + bob   -> A-bob   / R-bob
~~~

### 16.1. Seed hai principals

~~~java
var bob = UsernamePasswordAuthenticationToken.authenticated(
        "bob",
        "test-only",
        AuthorityUtils.createAuthorityList("ROLE_USER"));

OAuth2AuthorizedClient aliceClient =
        new OAuth2AuthorizedClient(
                registration,
                "alice",
                TestTokens.accessToken(
                        "A-alice",
                        now.minusSeconds(100),
                        now.plusSeconds(3600)));

OAuth2AuthorizedClient bobClient =
        new OAuth2AuthorizedClient(
                registration,
                "bob",
                TestTokens.accessToken(
                        "A-bob",
                        now.minusSeconds(100),
                        now.plusSeconds(3600)));

service.saveAuthorizedClient(aliceClient, alice);
service.saveAuthorizedClient(bobClient, bob);
~~~

### 16.2. Kiểm tra isolation

~~~java
assertThat(service.loadAuthorizedClient(
        "orders-client", "alice")
        .getAccessToken().getTokenValue())
        .isEqualTo("A-alice");

assertThat(service.loadAuthorizedClient(
        "orders-client", "bob")
        .getAccessToken().getTokenValue())
        .isEqualTo("A-bob");
~~~

### 16.3. Test qua manager

Có thể tạo hai `OAuth2AuthorizeRequest` cùng registration nhưng principal khác nhau, xác minh manager trả đúng token.

Không lưu `currentAccessToken` vào biến static hoặc cache key chỉ theo registration ID.

### 16.4. OIDC principal name và issuer

Nếu application dùng `sub` làm principal name và hỗ trợ nhiều issuers, hai OP có thể phát cùng `sub`. Với custom store, cần thiết kế namespace/identity mapping theo `iss` + `sub` hoặc local user ID ổn định, tránh cross-provider collision.

## 17. Test 9 — Registration isolation

Một user có thể có nhiều OAuth clients:

~~~text
alice + orders-client  -> orders token
alice + reports-client -> reports token
~~~

### 17.1. Khóa lưu trữ

Thông thường authorized client store phân biệt registration ID và principal name.

### 17.2. Không dùng token sai resource

Nếu Orders API cần token `aud=orders-api`, không lấy token của `reports-client` gửi thay.

### 17.3. Test sai registration

~~~text
Authorize request:
  registrationId = reports-client
  principal = alice

Expected:
  Không load orders-client token.
~~~

### 17.4. Resource Server validation vẫn cần

Dù manager trả token của đúng registration, Orders API vẫn phải xác minh issuer/audience/scope. Client-side test không chứng minh API sẽ chấp nhận token.

## 18. Test 10 — Lưu vào JDBC hoặc custom persistent store

`InMemoryOAuth2AuthorizedClientService` phù hợp cho unit/component test. Khi production dùng JDBC/Redis/custom store, cần kiểm tra implementation thật.

### 18.1. Những dữ liệu phải giữ

Một authorized client record thường phải bảo toàn:

- Registration ID.
- Principal name/identity namespace.
- Access token value.
- Token type.
- Scopes.
- Issued-at và expires-at.
- Refresh token value nếu có.
- Refresh token timestamps nếu được lưu.
- Version/concurrency metadata nếu hệ thống dùng.

### 18.2. JDBC persistence test

Một integration test có thể:

1. Tạo test database/schema.
2. Save authorized client A1/R1.
3. Tạo repository/service instance mới.
4. Load lại record.
5. So sánh token values và timestamps.
6. Refresh thành A2/R2.
7. Load lại qua instance mới.
8. Kiểm tra record là A2/R2.
9. Xóa record rồi xác minh không còn.
10. Rollback/cleanup sau test.

### 18.3. Serialization không được làm mất refresh token

Với Redis/JSON hoặc custom DTO, test phải chắc chắn refresh token không bị rơi khi serialize/deserialize và expiry timestamps còn chính xác.

### 18.4. Bảo vệ token trong storage

Access/refresh tokens là credentials nhạy cảm. Production store cần kiểm soát access, mã hóa khi phù hợp, backup retention và logs redaction.

Test chỉ dùng token giả; không ghi raw refresh token production.

## 19. Service manager cho background jobs

`DefaultOAuth2AuthorizedClientManager` dành cho ngữ cảnh Servlet request.

Với scheduled job không có `HttpServletRequest`, dùng:

~~~java
import org.springframework.security.oauth2.client
        .AuthorizedClientServiceOAuth2AuthorizedClientManager;

var backgroundManager =
        new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                service);
~~~

### 19.1. `client_credentials`

Một registration:

~~~java
ClientRegistration reporting =
        ClientRegistration.withRegistrationId("reporting-client")
                .clientId("reporting-job")
                .clientSecret("test-only")
                .authorizationGrantType(
                        AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://as.example.test/token")
                .scope("reports.read")
                .build();
~~~

### 19.2. Manager cần provider thích hợp

~~~java
import org.springframework.security.oauth2.client
        .OAuth2AuthorizedClientProviderBuilder;

backgroundManager.setAuthorizedClientProvider(
        OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build());
~~~

Trong test thật, thay HTTP token-response client bằng fake để không gọi AS.

### 19.3. Principal cho machine-to-machine

~~~java
OAuth2AuthorizeRequest authorizeRequest =
        OAuth2AuthorizeRequest
                .withClientRegistrationId("reporting-client")
                .principal("reporting-job")
                .build();
~~~

`reporting-job` là khóa kỹ thuật để lưu authorized client, không phải một human OIDC user.

### 19.4. Không cần Servlet request/response

`AuthorizedClientServiceOAuth2AuthorizedClientManager` sử dụng service store trực tiếp. Không cần `MockHttpServletRequest`/`MockHttpServletResponse`.

### 19.5. Test hai ngữ cảnh tách biệt

| Use case | Manager/test |
|---|---|
| OIDC Portal gọi API trong request | `DefaultOAuth2AuthorizedClientManager` |
| Scheduled reporting job | `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
| Browser OIDC login callback | Spring Security OAuth2 Login integration |
| API xác minh Bearer token | Resource Server tests |

## 20. Full JUnit test skeleton: refresh và persistence

Đoạn sau gom các phần thành một lớp test Servlet thuần với fake token-response client.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.RefreshTokenOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;

import static org.assertj.core.api.Assertions.assertThat;

class ServletAuthorizedClientManagerTest {

    private final Clock clock = Clock.fixed(
            Instant.parse("2026-11-16T10:00:00Z"),
            ZoneOffset.UTC);

    private ClientRegistration registration;
    private Authentication alice;
    private InMemoryOAuth2AuthorizedClientService service;
    private AuthenticatedPrincipalOAuth2AuthorizedClientRepository repository;
    private DefaultOAuth2AuthorizedClientManager manager;
    private MockHttpServletRequest request;
    private MockHttpServletResponse response;
    private AtomicInteger refreshCalls;

    @BeforeEach
    void setUp() {
        registration = ClientRegistration
                .withRegistrationId("orders-client")
                .clientId("portal-test")
                .clientSecret("test-secret")
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationUri(
                        "https://op.example.test/authorize")
                .tokenUri("https://op.example.test/token")
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "orders.read")
                .build();

        var registrations =
                new InMemoryClientRegistrationRepository(
                        registration);

        service =
                new InMemoryOAuth2AuthorizedClientService(
                        registrations);

        repository =
                new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(
                        service);

        manager =
                new DefaultOAuth2AuthorizedClientManager(
                        registrations, repository);

        alice = UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                "test-only",
                AuthorityUtils.createAuthorityList("ROLE_USER"));

        request = new MockHttpServletRequest();
        response = new MockHttpServletResponse();
        refreshCalls = new AtomicInteger();

        var provider =
                new RefreshTokenOAuth2AuthorizedClientProvider();

        provider.setClock(clock);
        provider.setClockSkew(Duration.ofSeconds(60));

        provider.setAccessTokenResponseClient(grant -> {
            refreshCalls.incrementAndGet();

            assertThat(grant.getRefreshToken().getTokenValue())
                    .isEqualTo("R1");

            return OAuth2AccessTokenResponse
                    .withToken("A2")
                    .tokenType(
                            OAuth2AccessToken.TokenType.BEARER)
                    .expiresIn(3600)
                    .refreshToken("R2")
                    .scopes(Set.of("openid", "orders.read"))
                    .build();
        });

        manager.setAuthorizedClientProvider(provider);
    }

    private OAuth2AuthorizeRequest authorizeRequest() {
        return OAuth2AuthorizeRequest
                .withClientRegistrationId("orders-client")
                .principal(alice)
                .attribute(
                        HttpServletRequest.class.getName(),
                        request)
                .attribute(
                        HttpServletResponse.class.getName(),
                        response)
                .build();
    }

    private void saveOldToken(Instant expiresAt) {
        Instant now = clock.instant();

        var token = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "A1",
                now.minusSeconds(7200),
                expiresAt,
                Set.of("orders.read"));

        var refresh = new OAuth2RefreshToken(
                "R1", now.minusSeconds(7200));

        var authorized = new OAuth2AuthorizedClient(
                registration,
                "alice",
                token,
                refresh);

        repository.saveAuthorizedClient(
                authorized, alice, request, response);
    }

    @Test
    void reusesAccessTokenWhileStillValid() {
        saveOldToken(clock.instant().plusSeconds(3600));

        OAuth2AuthorizedClient result =
                manager.authorize(authorizeRequest());

        assertThat(result.getAccessToken().getTokenValue())
                .isEqualTo("A1");
        assertThat(refreshCalls.get()).isZero();

        OAuth2AuthorizedClient saved =
                service.loadAuthorizedClient(
                        "orders-client", "alice");

        assertThat(saved.getRefreshToken().getTokenValue())
                .isEqualTo("R1");
    }

    @Test
    void refreshesAndPersistsRotatedRefreshToken() {
        saveOldToken(clock.instant().minusSeconds(60));

        OAuth2AuthorizedClient result =
                manager.authorize(authorizeRequest());

        assertThat(result.getAccessToken().getTokenValue())
                .isEqualTo("A2");
        assertThat(result.getRefreshToken().getTokenValue())
                .isEqualTo("R2");
        assertThat(refreshCalls.get()).isEqualTo(1);

        OAuth2AuthorizedClient saved =
                service.loadAuthorizedClient(
                        "orders-client", "alice");

        assertThat(saved).isNotNull();
        assertThat(saved.getAccessToken().getTokenValue())
                .isEqualTo("A2");
        assertThat(saved.getRefreshToken().getTokenValue())
                .isEqualTo("R2");
        assertThat(saved.getPrincipalName())
                .isEqualTo("alice");
        assertThat(saved.getClientRegistration()
                .getRegistrationId())
                .isEqualTo("orders-client");
    }

    @Test
    void refreshesBeforeExpiryWhenWithinClockSkew() {
        saveOldToken(clock.instant().plusSeconds(20));

        OAuth2AuthorizedClient result =
                manager.authorize(authorizeRequest());

        assertThat(result.getAccessToken().getTokenValue())
                .isEqualTo("A2");
        assertThat(refreshCalls.get()).isEqualTo(1);
    }
}
~~~

### 20.1. Phạm vi của skeleton

- Dùng Spring Security 6.x / Spring Boot 3.x style APIs.
- Test manager/provider/store thực ở mức in-memory.
- Token endpoint là fake callback, không có network.
- Không test OIDC Login và browser callback.
- Không test lưu JDBC/Redis hoặc multi-instance concurrency.
- Không cần `@SpringBootTest` khi trực tiếp xây các đối tượng cần thiết.

### 20.2. Điều quan trọng nhất trong test refresh

Không chỉ assert:

~~~java
assertThat(result.getAccessToken().getTokenValue())
        .isEqualTo("A2");
~~~

mà còn phải load lại từ store:

~~~java
OAuth2AuthorizedClient saved =
        service.loadAuthorizedClient(
                "orders-client", "alice");

assertThat(saved.getRefreshToken().getTokenValue())
        .isEqualTo("R2");
~~~

Điều này bắt lỗi “refresh thành công nhưng chưa persist token mới”.

### 20.3. Không tự gọi token endpoint sản xuất

Tất cả URI là `example.test` và fake token response. Không đưa refresh token thật vào test log hoặc fixture.

## 21. Khi dùng provider chain nhiều grant

Trong ứng dụng thực:

~~~java
OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();

manager.setAuthorizedClientProvider(provider);
~~~

### 21.1. Test từng nhánh

- `authorizationCode`: luồng tương tác đã cấp authorized client.
- `refreshToken`: token gần hết hạn, R1 tồn tại.
- `clientCredentials`: service cần token và không có user.
- Provider trả `null` khi grant không áp dụng.

### 21.2. Không test mọi grant bằng một fixture

Nếu registration là `client_credentials`, không dùng một fake human OIDC user làm bằng chứng service authorization.

### 21.3. Thứ tự provider và selection

Provider chain thử các providers theo logic và grant. Test nên xác minh đúng provider được kích hoạt khi context có grant/authorized client phù hợp.

### 21.4. Manager không tự đổi grant bất hợp lệ

Nếu registration có grant `authorization_code` nhưng không có authorization/refresh capability, manager không tự biến nó thành `client_credentials` để “có token”.

## 22. Test custom success/failure handlers

Manager cho phép cấu hình:

~~~java
manager.setAuthorizationSuccessHandler(successHandler);
manager.setAuthorizationFailureHandler(failureHandler);
~~~

### 22.1. Success handler

Có thể dùng để save authorized client vào một repository custom, cập nhật metrics hoặc audit. Test cần xác minh:

1. Handler nhận authorized client đúng.
2. Principal/registration đúng.
3. Save xảy ra đúng một lần với token mới.
4. Nếu save lỗi, ứng dụng xử lý theo policy.
5. Không log raw access/refresh tokens.

### 22.2. Failure handler

Có thể xóa stale authorized client khi `invalid_grant`, hoặc giữ record khi lỗi tạm thời.

Test nên phân biệt:

| Error | Policy có thể chọn |
|---|---|
| `invalid_grant` | Remove stale token, yêu cầu reauthorize |
| Network timeout | Không tự xem R1 đã bị revoke |
| AS 503 | Retry có giới hạn, giữ token theo policy |
| `invalid_client` | Cảnh báo cấu hình/credential |
| API 403 | Không mặc định refresh token |
| API 401 do audience sai | Sửa token contract, refresh có thể vô ích |

### 22.3. Thận trọng khi override default handler

Nếu gọi `setAuthorizationSuccessHandler(...)` rồi chỉ ghi metrics mà quên save, bạn đã thay thế logic lưu mặc định.

Một test manager nên phát hiện store không được cập nhật sau refresh.

### 22.4. Không giả định failure handler được gọi cho mọi API 401

Failure handler của manager xử lý các lỗi trong **client authorization flow**. Một downstream API 401 chỉ tác động authorized-client store nếu outbound client/filter/interceptor của ứng dụng có cấu hình xử lý failure cụ thể.

## 23. Logout, revocation và authorized client cleanup

Local logout thường xóa session/SecurityContext, nhưng có thể không xóa authorized client ở service store ngoài session.

### 23.1. Test cleanup khi logout

Với business requirement “logout phải xóa token của user”:

1. Seed authorized client Alice.
2. Thực hiện logout handler phù hợp.
3. Load service/repository.
4. Assert authorized client record đã bị xóa nếu policy yêu cầu.
5. Không xóa token Bob cùng registration.
6. Nếu gọi AS revocation endpoint, test HTTP request riêng.

### 23.2. Local remove khác token revocation

Xóa record trong database không tự thu hồi token tại Authorization Server. Access token đã cấp có thể còn hiệu lực tới expiry/revocation theo AS/Resource Server policy.

### 23.3. Session-backed vs service-backed records

- Session repository: record có thể đi cùng session.
- JDBC/service store: record có thể tồn tại qua browser logout.
- Custom Redis store: TTL/serialization/cleanup cần được test.

### 23.4. Không xóa mọi tenant tokens khi chỉ một membership thay đổi

Một user có thể được phép ở nhiều tenants. Cleanup phải dựa trên chính sách principal/registration/tenant cụ thể.

## 24. Refresh token rotation và concurrency

Đây là nhóm lỗi thực tế khó phát hiện bằng unit test một thread.

### 24.1. Race đơn giản

~~~mermaid
sequenceDiagram
    participant R1 as Request A
    participant R2 as Request B
    participant S as Authorized Client Store
    participant AS as Authorization Server
    R1->>S: Load A1/R1
    R2->>S: Load A1/R1
    R1->>AS: Refresh R1
    AS-->>R1: A2/R2
    R2->>AS: Refresh R1
    AS-->>R2: invalid_grant / reuse detection
    R1->>S: Save A2/R2
    R2->>S: Remove stale record? (danger)
~~~

Request B có thể xóa record mới mà A vừa lưu nếu failure handler không kiểm tra concurrency/version.

### 24.2. Unit test single-thread không đủ

Một test refresh thành công chứng minh path thông thường, không chứng minh distributed concurrency an toàn.

### 24.3. Thiết kế concurrency test

Có thể dùng:

- `CountDownLatch` để hai threads cùng load R1.
- Fake AS phát A2/R2 lần đầu, từ chối R1 lần hai.
- Repository in-memory custom có version/CAS.
- Assertions rằng final record không bị xóa/ghi đè sai.
- Test nhiều application instances nếu dùng shared JDBC/Redis store.

### 24.4. Các chiến lược

- Single-flight refresh theo principal/registration.
- Distributed lock khi cần.
- Optimistic locking/version hoặc compare-and-swap.
- Failure removal theo token version thực tế.
- Retry có kiểm soát, không reuse R1 tùy ý.
- Không gửi nhiều refresh request đồng thời nếu AS rotate nghiêm ngặt.

### 24.5. Không mặc định manager xử lý mọi race phân tán

`DefaultOAuth2AuthorizedClientManager` phối hợp provider/storage, nhưng việc atomic refresh trên nhiều process phụ thuộc repository, handler và kiến trúc ứng dụng.

## 25. Kiểm thử lỗi storage

Khi custom JDBC/Redis store bị lỗi:

- Load fail: ứng dụng phải tránh trả nhầm token.
- Save fail sau refresh: A2/R2 có thể chỉ có trong memory, store vẫn A1/R1.
- Remove fail sau invalid_grant: record stale còn tồn tại.
- Serialization fail: token mất timestamps/scopes.
- Network partition: hai instances nhìn thấy states khác nhau.

### 25.1. Fake repository throws

Dùng Mockito:

~~~java
doThrow(new IllegalStateException("Storage unavailable"))
        .when(repository)
        .saveAuthorizedClient(any(), any(), any(), any());
~~~

Chỉ hoạt động nếu `repository` là Mockito mock/spy đã cấu hình. Test cần xác định expected exception/fallback policy của hệ thống.

### 25.2. Đừng silently swallow persistence errors

Nếu refresh thành công nhưng save thất bại, backend có thể tiếp tục dùng A2 cho request hiện tại, nhưng lần sau lại load A1/R1 cũ.

Phải có error handling/metrics để phát hiện vấn đề, không coi refresh là hoàn chỉnh nếu yêu cầu persistence.

### 25.3. Test recovery

Sau khi store phục hồi, flow có thể cần reauthorization/refresh lại hoặc xử lý stale record. Test dựa trên AS rotation policy thật của hệ thống.

## 26. HTTP-level refresh test với fake Authorization Server

Fake `OAuth2AccessTokenResponseClient` không kiểm tra HTTP request encoding. Để test phần HTTP thật, cần một test Authorization Server như WireMock, MockWebServer hoặc mock HTTP transport phù hợp version.

### 26.1. Contract cần xác minh

Refresh HTTP request thường có:

~~~http
POST /oauth2/token HTTP/1.1
Host: as.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CLIENT_CREDENTIALS>

grant_type=refresh_token&refresh_token=R1
~~~

Client authentication method và parameters cụ thể phụ thuộc client registration/AS policy.

### 26.2. Fake token response

~~~json
{
  "access_token": "A2",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "R2",
  "scope": "orders.read"
}
~~~

### 26.3. Assert đúng HTTP behavior

- Gọi đúng token endpoint host.
- Dùng `grant_type=refresh_token`.
- Gửi đúng R1.
- Client authentication method đúng (Basic/Post/private_key_jwt...).
- Đọc đúng A2/R2, expires_in và scopes.
- Xử lý AS 400 `invalid_grant` đúng.
- Không log Authorization header/refresh token.
- Không follow redirect tới host ngoài ý muốn kèm secret/token.

### 26.4. API response client thay đổi theo version

Spring Security có các HTTP client implementations cho token endpoint khác nhau giữa phiên bản, chẳng hạn RestTemplate-based và RestClient-based variants.

Bài dùng **interface `OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>`** làm seam ổn định để test manager. Khi test HTTP serialization, chọn implementation cụ thể tương thích phiên bản framework trong dự án.

### 26.5. Không gọi Authorization Server production

Dùng fake HTTP server và credentials giả, tuyệt đối không đưa R1 production vào test fixtures.

## 27. MockMvc test phối hợp với `oidcLogin()`

`oidcLogin()` hữu ích khi cần một browser OIDC Authentication cho controller:

~~~java
mvc.perform(get("/orders")
                .with(oidcLogin()))
        .andExpect(status().isOk());
~~~

Nhưng nó không tự chứng minh:

- Authorized client manager refresh A1 bằng R1.
- Token endpoint trả A2/R2.
- Repository lưu token mới.
- HTTP client gửi A2 thay ID token tới Orders API.
- Refresh token rotation phân tán đúng.

### 27.1. Chia test theo tầng

| Tầng | Công cụ |
|---|---|
| Controller sau OIDC Login | `MockMvc` + `oidcLogin()` |
| Manager/provider refresh | Unit/component test + fake token response |
| AuthorizedClientService persistence | JDBC/Redis integration test |
| Outbound API Authorization header | Mock HTTP client/server |
| OIDC Authorization Code callback | Login filter + fake OP |
| Resource Server Bearer validation | `jwt()` và decoder tests |
| Concurrent refresh nhiều nodes | Concurrency/integration tests |

### 27.2. Không chỉ mock manager ở controller test rồi kết luận refresh đúng

Nếu controller test chỉ làm:

~~~java
when(manager.authorize(any()))
        .thenReturn(fakeAuthorizedClient);
~~~

bạn mới xác minh controller gọi manager. Cần test manager riêng như các mục trên.

## 28. Bẫy trong thực tế: token cấp cho API nào?

Một manager có thể trả A2 đúng refresh flow nhưng Orders API vẫn trả 401 nếu token sai audience hoặc issuer.

### 28.1. Client authorization success khác Resource Server acceptance

~~~text
Manager:
  A2 tồn tại, expiresAt còn hạn.

Orders API:
  issuer hợp lệ?
  audience = orders-api?
  scopes đủ?
  subject/tenant có quyền?
~~~

Hai tầng khác nhau.

### 28.2. Không dùng ID token để thay access token

OIDC ID token dành cho Relying Party. `OAuth2AuthorizedClient.getAccessToken()` là nơi lấy OAuth access token đã cấp cho client.

### 28.3. API 403 không tự cần refresh

Nếu A2 thiếu scope `orders.write` hoặc user không có quyền object, refresh theo cùng grant không tự mở rộng quyền.

### 28.4. Token reuse không có nghĩa token chưa bị revoke

Nếu access token còn hạn theo `expiresAt` nhưng đã bị revoke tại AS, manager có thể tái sử dụng A1 theo local metadata. Resource Server vẫn có thể từ chối.

Test cần hiểu tradeoff giữa expiry, revocation freshness và introspection/RS validation.

## 29. Test plan tổng hợp

| Tình huống | Bằng chứng cần assert |
|---|---|
| No authorized client, provider can issue | New token saved |
| No authorized client, provider returns null | Manager returns null/appropriate state |
| Access token còn hạn | No token endpoint call; A1 reused |
| Access token gần hết hạn | Refresh theo clock skew |
| Access token đã hết hạn + R1 | A2 được trả |
| Refresh response có R2 | Store giữ R2 |
| Refresh response không có R2 | Behavior giữ/sử dụng token theo provider/AS contract |
| Expired + không refresh token | Không fake ra A2 |
| `invalid_grant` | Failure policy và stale client removal |
| AS timeout/503 | Không xóa nhầm token theo policy |
| Save success | Load lại đúng token |
| Save failure | Exception/handling theo policy |
| Principal Alice vs Bob | Token isolation |
| Registration orders vs reports | Token isolation |
| Tenant issuer/subject collision | Không trộn identity/token |
| Browser logout | Session/store cleanup theo policy |
| Refresh concurrent | Không mất R2 khi race |
| Client credentials job | Service manager, no Servlet request |
| HTTP token exchange | Form params, client auth, response parsing |
| API call | Bearer access token đúng host/audience |
| OP authentication callback | Test riêng, không dùng manager unit test |

## 30. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `No thread-bound request found` | Dùng Servlet manager ngoài request | Truyền mock request/response hoặc service manager |
| `authorize()` trả null | Không có client và provider không thể authorize | Grant/provider/registration |
| Token expired vẫn được trả | No refresh token/provider returned null | Cần reauthorization policy |
| Token luôn refresh | Clock skew quá lớn hoặc expiry sai | Fixed Clock/expiresAt |
| Không bao giờ refresh | Thiếu refresh token/provider hoặc clock | Provider chain/token |
| Refresh trả A2 nhưng store còn A1 | Success handler/save không chạy | Repository/service wiring |
| Refresh R2 bị mất | Serialization/persistence không cập nhật refresh token | Load sau save |
| `invalid_grant` liên tục | Record stale không bị remove | Failure handler |
| Refresh R1 bị dùng hai lần | Concurrency/rotation race | Lock/CAS |
| Bob thấy token Alice | Store key thiếu principal | Principal isolation |
| Orders nhận reports token | Chọn sai registration ID | Registration isolation |
| API 401 dù A2 còn hạn | Audience/issuer/revocation | Resource Server |
| API 403 | Scope/owner/tenant thiếu | Domain policy |
| Test manager gọi AS thật | Token response client chưa fake | Fake transport |
| Test gọi issuer discovery | ClientRegistration từ issuer-uri | Test registration fixture |
| Test `@WebMvcTest` không có manager | Bean chưa nạp | Import/mocks phù hợp |
| Mockito verify save nhiều hơn dự kiến | Seed qua spy đã count | Clear invocations sau seed |
| Test flaky ở expiry | Dùng Instant.now trôi theo test | Fixed Clock |
| Redis load lỗi token object | Serializer/version | Persistent store integration |

## 31. Những hiểu nhầm thường gặp

**“Manager luôn gọi token endpoint khi authorize.”**

Không. Access token còn hạn thường được tái sử dụng.

**“Provider không trả token mới nghĩa là manager luôn trả null.”**

Không. Nếu đã có authorized client, manager có thể trả client cũ.

**“Expired access token không refresh được sẽ tự tạo authorization code.”**

Không. Authorization Code cần browser/AS authorization flow.

**“Refresh thành công là đã được lưu.”**

Chưa chắc nếu success handler bị override hoặc store lỗi. Phải load lại kiểm tra.

**“Khi AS rotate R1 thành R2, chỉ cần lưu A2.”**

Không. Phải lưu refresh token mới khi được phát.

**“`invalid_grant` giống lỗi mạng 503.”**

Không. Removal/retry policies thường khác nhau.

**“`DefaultOAuth2AuthorizedClientManager` dùng tốt trong scheduled job không có request.”**

Không nên. Dùng service manager cho non-web context.

**“`oidcLogin()` đủ kiểm tra refresh token.”**

Không. Nó mock OIDC principal, không chạy token lifecycle.

**“In-memory store test đã chứng minh JDBC/Redis serializer an toàn.”**

Không. Cần persistence integration test riêng.

**“Manager xử lý atomic refresh trên nhiều servers.”**

Không nên mặc định. Storage/concurrency cần thiết kế và test.

**“Access token chưa hết hạn nên API chắc chấp nhận.”**

Không. API còn issuer/audience/revocation/scope/ownership rules.

## 32. Tình huống thực hành

### A. Portal gọi Orders API nhiều lần

A1 còn hạn trong 30 phút.

**Test:** seed A1/R1, gọi manager, assert không gọi fake token-response client và trả A1.

### B. Token hết hạn

A1 đã expired, R1 hợp lệ.

**Test:** fake AS trả A2/R2, assert result và stored record đều có A2/R2.

### C. Token gần hết hạn

A1 còn 20 giây, clock skew 60 giây.

**Test:** refresh xảy ra sớm đúng một lần.

### D. AS không cấp refresh token

Chỉ có A1, sau đó expired.

**Test:** manager không tự sinh R1 hoặc A2; application xử lý reauthorization.

### E. Refresh token bị revoke

Fake AS trả `invalid_grant`.

**Test:** exception/failure handler và stale-client removal theo policy.

### F. Background reporting job

Job chạy ngoài request dùng `client_credentials`.

**Test:** service manager với principal kỹ thuật, không cần Servlet request.

### G. Hai users cùng registration

Alice và Bob dùng Orders OAuth client.

**Test:** store và manager trả token riêng theo principal.

### H. Hai API registrations

Alice có Orders token và Reporting token.

**Test:** không lẫn tokens giữa registration IDs.

### I. Hai requests refresh cùng R1

AS có refresh token rotation.

**Test:** concurrency harness với latch, CAS/store version, đảm bảo R2 cuối cùng không bị xóa bởi một lỗi stale request.

### J. Sau refresh API vẫn trả 401

A2 có audience dành cho Billing API.

**Test:** manager refresh có thể đúng, nhưng API contract/audience sai; test Resource Server riêng.

## 33. Câu hỏi tự kiểm tra

**1. `ClientRegistrationRepository` lưu gì?**

Cấu hình OAuth client như client ID, grant type, endpoints, scopes.

**2. `OAuth2AuthorizedClientService` lưu gì?**

Authorized client access/refresh tokens theo registration và principal.

**3. Khi nào nên dùng `DefaultOAuth2AuthorizedClientManager`?**

Khi có Servlet request/response context.

**4. Với background job nên dùng manager nào?**

`AuthorizedClientServiceOAuth2AuthorizedClientManager`.

**5. Vì sao cần MockHttpServletRequest/Response?**

Để Servlet manager/repository xử lý request context trong test không có HTTP thật.

**6. Manager có luôn gọi token endpoint không?**

Không. Token còn hạn có thể được tái sử dụng.

**7. Refresh provider dựa vào gì?**

Token expiry/clock skew, refresh token và authorization context.

**8. Vì sao dùng fixed clock?**

Tránh test bị flaky ở expiry boundary.

**9. Fake token-response client giúp test gì?**

Provider refresh decision và manager/store mà không gọi AS qua mạng.

**10. Khi refresh trả A2/R2 cần assert gì?**

Manager trả A2/R2 và repository/service lưu lại A2/R2.

**11. Nếu success handler bị override mà quên save thì sao?**

Refresh có thể trả token mới nhưng store còn token cũ.

**12. `invalid_grant` thường cần làm gì?**

Xử lý authorization failure và thường remove stale client theo policy.

**13. Có nên xóa token trên mọi timeout không?**

Không tự động. Timeout có thể là lỗi tạm thời, không chứng minh R1 đã bị revoke.

**14. Nếu token expired không có refresh token, manager có tự xin authorization code không?**

Không. Cần authorization flow phù hợp.

**15. Vì sao test principal isolation?**

Tránh Alice dùng token Bob khi cùng registration.

**16. Vì sao test registration isolation?**

Tránh gửi token của API/AS này tới API khác.

**17. In-memory test có chứng minh JDBC/Redis persistence đúng không?**

Không. Cần integration test store.

**18. `oidcLogin()` có kiểm thử refresh token rotation không?**

Không.

**19. Nếu hai requests cùng refresh R1 thì nguy cơ gì?**

Rotation race, invalid_grant hoặc xóa/ghi đè R2.

**20. Manager trả access token còn hạn có đảm bảo API chấp nhận không?**

Không. Resource Server còn issuer, audience, scope, revocation và domain authorization.

## Ghi nhớ

- **`OAuth2AuthorizedClientManager` điều phối load → provider decision → save/failure**, không đơn giản là một HTTP token client.
- **`ClientRegistrationRepository` lưu cấu hình client**, còn **`OAuth2AuthorizedClientRepository`/`Service` lưu access/refresh tokens theo registration và principal**.
- **Token còn hạn nên được tái sử dụng**, tránh token endpoint calls không cần thiết.
- **Refresh provider cần clock, clock skew và refresh token**; test bằng fake `OAuth2AccessTokenResponseClient` để xác minh logic refresh mà không dùng AS thật.
- **Sau refresh, kiểm tra cả result và record đã lưu**, đặc biệt access token mới A2 và refresh token rotation R2.
- **`invalid_grant`, timeout, 503 và API 403 không có cùng failure policy**. Không remove/retry mù quáng.
- **Servlet manager cần request/response context**; background service dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager`.
- **Không trộn authorized clients giữa users, registrations, issuers hoặc tenants**. Token store/cache keys cần đúng trust boundary.
- **Concurrency và persistence thật cần integration tests**; in-memory single-thread test không chứng minh Redis/JDBC atomic rotation an toàn.
- **`oidcLogin()` chỉ mô phỏng principal OIDC**, không thay manager/token refresh tests; OIDC callback, HTTP token endpoint và Resource Server validity cũng cần các test riêng.
