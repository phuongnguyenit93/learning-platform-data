# 30.6. Kiểm thử ReactiveOAuth2UserService và ánh xạ claims

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client sử dụng WebFlux**, một người dùng có thể được xác thực thành công tại OpenID Provider (OP) nhưng ứng dụng vẫn cần xử lý nhiều bước **sau khi nhận token**:

- Tải thông tin người dùng từ **UserInfo Endpoint** khi giao thức, scopes và provider cho phép.
- Chuyển thuộc tính của provider thành một `OAuth2User` hoặc `OidcUser` mà ứng dụng có thể sử dụng.
- Lựa chọn một **principal name** bền vững, phân biệt đúng issuer, subject và tenant.
- Chuyển thông tin đã được xác minh thành **Spring Security authorities**.
- Kiểm tra user có thuộc tenant, đã được kích hoạt hoặc được phép truy cập ứng dụng hay không.
- Xử lý lỗi từ provider, database, mapping service hoặc những claims bắt buộc bị thiếu theo chính sách.
- Trả kết quả dưới dạng **`Mono<OAuth2User>` hoặc `Mono<OidcUser>`**, không làm tắc event loop.

Những hành vi này thường được triển khai hoặc mở rộng qua **`ReactiveOAuth2UserService`**. Chúng cần được kiểm thử riêng, bởi một test WebFlux kiểu:

```java
webTestClient.mutateWith(mockOidcLogin())
    .get().uri("/account/me")
    .exchange()
    .expectStatus().isOk();
```

chỉ **giả lập trạng thái user đã OIDC login**. Nó **không** tự chạy mã của custom `ReactiveOAuth2UserService`, không lấy UserInfo thật và không xác minh toàn bộ cơ chế tạo authorities của ứng dụng.

Bài học này hướng dẫn thiết kế các test cho **reactive user service** và **claim mapping** bằng JUnit Jupiter, Reactor Test `StepVerifier`, fixture OIDC/OAuth2, fake dependencies và test provider HTTP khi cần. Ví dụ đi từ unit test đơn giản tới integration test có WebFlux Security, tập trung vào **giá trị trả về, loại principal, nguồn dữ liệu đáng tin, lỗi, tính bất đồng bộ và ranh giới bảo mật đa provider/tenant**.

> **Tư duy quan trọng:** tách ba câu hỏi: **(1) token/identity đã được xác minh đúng chưa; (2) user service có biến dữ liệu đã xác minh thành principal/authorities đúng không; (3) endpoint có thực thi authorization đúng không?** Mỗi câu hỏi cần một lớp test phù hợp; không xem một mock login thành công là bằng chứng cả ba lớp đã an toàn.

## 1. `ReactiveOAuth2UserService` nằm ở đâu trong hệ thống?

Một luồng **Authorization Code + OIDC** trên WebFlux thường có dạng:

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant W as Spring Security WebFlux Client
    participant O as OpenID Provider
    participant U as Reactive OIDC User Service
    participant M as App Mapping / Membership Service

    B->>W: GET /oauth2/authorization/company
    W-->>B: Redirect tới authorization endpoint
    B->>O: Login, MFA, consent
    O-->>B: Callback với code và state
    B->>W: GET /login/oauth2/code/company
    W->>W: Correlate request/state, token exchange
    W->>O: Trao đổi authorization code
    O-->>W: ID Token + Access Token
    W->>W: Xác minh ID Token theo OIDC
    W->>U: loadUser(OidcUserRequest)
    opt Flow có UserInfo
        U->>O: GET userinfo_endpoint với Access Token
        O-->>U: UserInfo claims
    end
    U->>M: Ánh xạ issuer/sub, kiểm tra membership/roles
    M-->>U: Trusted application authorities
    U-->>W: Mono<OidcUser>
    W->>W: Tạo Authentication/SecurityContext
    W-->>B: Phiên đăng nhập hoặc phản hồi tiếp theo
```

**`ReactiveOAuth2UserService` xử lý việc tải/tạo principal**, còn việc xác minh authorization code, chữ ký ID Token, issuer, audience, state/nonce/PKCE và quản lý phiên thuộc các thành phần khác của Spring Security/OIDC flow.

Khi custom service được viết sai, người dùng có thể gặp:

- Đã xác thực nhưng thiếu role vì mapping dùng sai claim.
- Được cấp `ROLE_ADMIN` chỉ vì provider trả chuỗi `"admin"` không đáng tin.
- Hai users từ hai issuers có cùng `sub` bị gộp thành một principal.
- `Mono.empty()` làm authentication không có kết quả rõ ràng.
- Lỗi HTTP UserInfo bị nuốt và fallback sang authorities quyền rộng.
- Blocking database/HTTP call chạy trên Reactor event loop.
- Lúc gặp lỗi không có bằng chứng audit phù hợp nhưng log lại lộ Access Token/ID Token.

Các lỗi ấy cần được test **tại chính service**, không chỉ kiểm tra controller trả HTTP 200.

## 2. Phân biệt hai kiểu user service reactive

Interface chung trong Spring Security:

```java
package org.springframework.security.oauth2.client.userinfo;

public interface ReactiveOAuth2UserService<
        R extends OAuth2UserRequest,
        U extends OAuth2User> {

    Mono<U> loadUser(R userRequest);
}
```

Đây là hình thức API khái quát để hiểu generic bounds; source code framework cụ thể có thể chứa thêm annotation hoặc các chi tiết phiên bản.

Hai cách sử dụng quan trọng:

| Tình huống | Generic service | Principal | Thành phần thường gặp |
|---|---|---|---|
| **OAuth2 Login thông thường, không bắt buộc OIDC** | `ReactiveOAuth2UserService<OAuth2UserRequest, OAuth2User>` | `OAuth2User` | `DefaultReactiveOAuth2UserService` hoặc implementation tùy chỉnh |
| **OIDC Login** | `ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` | `OidcUser` | `OidcReactiveOAuth2UserService` hoặc implementation tùy chỉnh |

### 2.1. OAuth2 User Service

Một OAuth2 provider có thể trả user attributes từ UserInfo-like endpoint riêng, ví dụ:

```json
{
  "id": "12345",
  "login": "alice",
  "display_name": "Alice"
}
```

Service chuyển response thành một `OAuth2User` và xác định thuộc tính dùng làm name.

### 2.2. OIDC User Service

Với OIDC, **ID Token** cung cấp những claims tiêu chuẩn như:

```json
{
  "iss": "https://id.example.test",
  "sub": "subject-42",
  "aud": "web-client",
  "email": "alice@example.test"
}
```

OP còn có thể cung cấp **UserInfo**, ví dụ:

```json
{
  "sub": "subject-42",
  "name": "Alice Example",
  "preferred_username": "alice",
  "email": "alice@example.test"
}
```

OIDC User Service có trách nhiệm tạo một `OidcUser` đại diện cho user theo dữ liệu đã được xác minh trong ngữ cảnh OIDC.

**Không đánh đồng hai interface generic:** một controller yêu cầu `OidcUser` cần principal OIDC, không phải chỉ một `DefaultOAuth2User` với các attributes có tên giống OIDC claims.

### 2.3. Test phải nhắm đúng implementation

Nếu code production dùng custom:

```java
ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
```

thì test dùng generic:

```java
ReactiveOAuth2UserService<OAuth2UserRequest, OAuth2User>
```

không tự kiểm tra code OIDC custom đó. Hãy xác định đúng bean, delegate và flow mà Spring Security đang gọi.

## 3. Nguồn claims: ID Token, UserInfo và dữ liệu nội bộ

Ba nguồn dữ liệu thường xuất hiện:

| Nguồn | Ai tạo? | Dùng làm gì? | Ranh giới tin cậy |
|---|---|---|---|
| **ID Token** | OP phát hành trong OIDC flow | Xác thực user tại RP, issuer/subject/audience và claims | Phải được xác minh đúng chữ ký, issuer, audience, thời gian, nonce khi yêu cầu |
| **UserInfo** | OP trả về theo Access Token | Bổ sung thông tin profile và claims khác | Chỉ nhận từ endpoint OP đúng; `sub` phải khớp ID Token theo OIDC |
| **Application membership/roles DB** | Ứng dụng hoặc nguồn policy được ủy quyền | Quyết định quyền nghiệp vụ, tenant membership, account status | Phải kiểm tra theo identity đã xác minh và policy hiện hành |

Ví dụ:

```text
ID Token:
  iss = https://id.example.test
  sub = subject-42

UserInfo:
  sub = subject-42
  preferred_username = alice

Internal DB:
  (iss, sub) -> tenant alpha -> ROLE_REPORT_VIEWER
```

**Đừng cấp `ROLE_ADMIN` trực tiếp từ một chuỗi profile tùy ý chỉ vì UserInfo có trường `"role": "admin"`.** Việc có tin role claim nào hay không cần một hợp đồng rõ với OP và chính sách mapping được phê duyệt.

### 3.1. `sub` không duy nhất trên mọi issuer

Hai OP có thể cùng có:

```text
issuer A, sub = 1001
issuer B, sub = 1001
```

Nhưng đó có thể là **hai người khác nhau**. Định danh OIDC cần được xét theo cặp:

```text
(issuer, subject)
```

Đây là trường hợp cần test đặc biệt trong hệ thống multi-provider hoặc multi-tenant.

### 3.2. Email chỉ nên dùng như profile trừ khi có policy riêng

Email có thể:

- Không có.
- Không được xác minh.
- Thay đổi.
- Bị tái sử dụng.
- Trùng giữa hai issuers.
- Có normalization rules khác nhau.

Dùng email làm display/contact data phù hợp hơn việc mặc định coi nó là identity key bất biến. Unit test nên có cases **thiếu email**, **email thay đổi** và **hai issuer cùng email**.

### 3.3. Authorities khác claims

`OidcUser.getClaims()` trả dữ liệu claims. `OidcUser.getAuthorities()` trả các `GrantedAuthority` mà Spring Security dùng trong các checks như:

```java
.hasAuthority("report:read")
.hasRole("TENANT_ADMIN")
```

Một claim `"roles": ["TENANT_ADMIN"]` không tự biến thành `ROLE_TENANT_ADMIN` nếu code mapping chưa thực hiện. Tests phải kiểm tra **đúng authority strings** thay vì chỉ assert claim còn tồn tại.

## 4. Các cấp kiểm thử cần phân chia

| Test layer | Test đối tượng nào? | Tool phù hợp | Điều chưa được chứng minh |
|---|---|---|---|
| **Unit test mapping function** | Chuyển Map claims → profile/authority | JUnit + AssertJ | Không chứng minh WebFlux wiring |
| **Reactive user service unit test** | `loadUser(request)`, Mono values/errors | Reactor `StepVerifier` + fake delegate | Không chứng minh OP/JWKS thật |
| **UserInfo HTTP integration test** | HTTP request/response và OIDC UserInfo parsing | Local stub server + reactive service | Không nhất thiết chứng minh full login |
| **WebFlux authorization test** | Route/method security với principal | `WebTestClient` + `mockOidcLogin()` | Không gọi user service |
| **Full OIDC flow integration** | Callback, code exchange, ID Token/JWKS và service wiring | Test OP/stub, WebFlux app | Chưa chứng minh browser cookie behavior |
| **Browser E2E** | Redirect/cookie/SSO UX | Browser với test OP | Không thay unit tests lỗi mapping |

**Tránh gom tất cả vào một test quá lớn.** Nếu một authority bị thiếu, unit test mapping sẽ nêu nguyên nhân nhanh hơn E2E; nếu có lỗi nonce/callback thì `mockOidcLogin()` không thể phát hiện.

## 5. Các dependencies cần thiết

Với Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("io.projectreactor:reactor-test")
}

tasks.test {
    useJUnitPlatform()
}
```

Đây là fragment dependencies, không phải `build.gradle.kts` độc lập. Spring Boot dependency management/BOM nên quản lý các phiên bản tương thích; không tự ghim `spring-security-test` hoặc Reactor Test vào một phiên bản khác xa runtime.

Với Maven:

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
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

### 5.1. Vì sao cần `reactor-test`?

`reactor-test` cung cấp:

- `StepVerifier`: xác nhận signals từ `Mono`/`Flux`.
- `PublisherProbe`: xác nhận publisher có được subscribe/request/cancel đúng.
- Virtual time utilities: test logic dựa trên thời gian mà không phải chờ clock thật, khi phù hợp.
- Các utility hỗ trợ những tình huống Reactor đặc thù.

Ở đây, trọng tâm là:

```java
StepVerifier.create(service.loadUser(userRequest))
    .assertNext(user -> {
        // Kiểm tra principal/claims/authorities
    })
    .verifyComplete();
```

### 5.2. Vì sao cần `spring-security-test`?

Khi test route WebFlux sau login, có thể dùng:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;
```

Nhưng **unit test của `ReactiveOAuth2UserService` không nhất thiết cần mockOidcLogin**; nó có thể gọi `loadUser` trực tiếp với `OidcUserRequest` fixture.

### 5.3. Không dùng production secrets trong tests

`client-secret`, Access Token, Refresh Token, ID Token được dùng trong tests phải là **synthetic fixtures**. Không lấy token người dùng thật để đưa vào `src/test` hoặc CI logs.

## 6. Cấu trúc một lớp test hợp lý

Ví dụ:

```text
src/
  main/
    java/com/example/security/
      TenantMappingReactiveOidcUserService.java
      TenantRoleLookup.java
      SecurityConfiguration.java
  test/
    java/com/example/security/
      OidcRequestFixtures.java
      TenantMappingReactiveOidcUserServiceTest.java
      OAuth2ProfileMappingServiceTest.java
      OidcWebFluxAuthorizationTest.java
      OidcUserInfoIntegrationTest.java
```

Mục đích:

- **Fixtures** tạo `OidcUserRequest`, ID Token, UserInfo và OAuth2AccessToken giả.
- **Unit test** gọi service trực tiếp, không cần application context.
- **WebFlux test** kiểm tra endpoint/security filters sau khi principal đã được inject.
- **HTTP integration test** kiểm tra UserInfo/OP khi cần.

Đừng đặt production Bean dùng token fixture test vào `src/main` chỉ để thuận tiện. Test infrastructure phải được cô lập.

## 7. Tạo `OidcUserRequest` giả lập

`ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` nhận `OidcUserRequest` chứa:

- `ClientRegistration`.
- `OAuth2AccessToken`.
- `OidcIdToken`.
- Những additional parameters khi flow/API hỗ trợ.

Một fixture Java:

```java
package com.example.security;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;

public final class OidcRequestFixtures {

    private OidcRequestFixtures() {}

    public static ClientRegistration registration() {
        return ClientRegistration.withRegistrationId("company")
            .clientId("test-web-client")
            .clientSecret("synthetic-test-secret")
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .authorizationUri("https://id.example.test/authorize")
            .tokenUri("https://id.example.test/token")
            .jwkSetUri("https://id.example.test/jwks")
            .issuerUri("https://id.example.test")
            .userInfoUri("https://id.example.test/userinfo")
            .userNameAttributeName("sub")
            .scope("openid", "profile")
            .build();
    }

    public static OidcIdToken idToken() {
        return new OidcIdToken(
            "synthetic-id-token",
            Instant.parse("2026-01-01T00:00:00Z"),
            Instant.parse("2030-01-01T00:00:00Z"),
            Map.of(
                "iss", "https://id.example.test",
                "sub", "subject-42",
                "aud", List.of("test-web-client"),
                "tenant_id", "alpha"
            )
        );
    }

    public static OAuth2AccessToken accessToken() {
        return new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "synthetic-access-token",
            Instant.parse("2026-01-01T00:00:00Z"),
            Instant.parse("2030-01-01T00:00:00Z"),
            Set.of("openid", "profile")
        );
    }

    public static OidcUserRequest request() {
        return new OidcUserRequest(
            registration(),
            accessToken(),
            idToken()
        );
    }
}
```

**Quan trọng:** constructor của `OidcIdToken` trong fixture đặt claims trực tiếp; **nó không ký hoặc xác minh JWT**. Đây là lựa chọn có chủ đích cho unit test mapping đã nằm *sau* bước OIDC validation. Không dùng fixture này để tuyên bố token giả có thể vượt qua verifier thực.

### 7.1. Tách fixture khỏi provider thật

Các hosts dưới `example.test` là giả lập. Không được có test tự động truy cập production OP để tải metadata hoặc JWKS mỗi lần chạy unit suite.

### 7.2. Kiểm soát thời gian

Dùng `Instant` cố định để tests dễ tái lập. Khi code của bạn kiểm tra token expiry, có thể dùng `Clock` được inject để tránh test phụ thuộc ngày chạy.

Đừng dùng `Instant.now()` rải rác trong cả fixtures và assertions rồi gây flaky tests ở ranh giới expiration.

### 7.3. Mỗi registration là một identity boundary

Nếu ứng dụng có `company` và `partner`, fixture nên tạo ClientRegistrations riêng biệt với issuer/client ID phù hợp. Đừng dùng một registration cho hai issuers rồi vô tình test thành công dù user/token bị trộn.

## 8. Tạo `OidcUser` giả lập không gọi mạng

Từ fixture trên, ta có thể tạo một user:

```java
package com.example.security;

import java.util.Map;
import java.util.Set;

import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;

public final class OidcUserFixtures {

    private OidcUserFixtures() {}

    public static OidcUser userWithUserInfo() {
        var idToken = OidcRequestFixtures.idToken();

        var userInfo = new OidcUserInfo(Map.of(
            "sub", "subject-42",
            "name", "Alice Example",
            "email", "alice@example.test"
        ));

        var oidcAuthority =
            new OidcUserAuthority(idToken, userInfo);

        return new DefaultOidcUser(
            Set.of(oidcAuthority),
            idToken,
            userInfo,
            "sub"
        );
    }

    public static OidcUser userWithoutUserInfo() {
        var idToken = OidcRequestFixtures.idToken();

        return new DefaultOidcUser(
            Set.of(new OidcUserAuthority(idToken)),
            idToken,
            "sub"
        );
    }
}
```

Fixture này phục vụ test mapper **đã nhận được một `OidcUser` hợp lệ về cấu trúc**. Nó không thực hiện UserInfo HTTP call và không chứng minh rằng claims được provider ký.

### 8.1. Vì sao cần cả hai biến thể?

UserInfo có thể không được gọi hoặc không được cấp tùy flow, scopes, policy và provider. Code mapping không nên NPE khi:

```java
oidcUser.getUserInfo() == null
```

Test nên kiểm tra những trường hợp cần và không cần UserInfo.

### 8.2. UserInfo phải có cùng subject

Một nguyên tắc cốt lõi OIDC:

```text
ID Token sub = subject-42
UserInfo sub = subject-42
```

Nếu UserInfo trả `sub` khác, response **không được gộp vào user đã xác thực**. Test cho hành vi xác minh mismatch cần thực thi logic của **OIDC user service/parser thật hoặc validation wrapper**; không chỉ tạo `DefaultOidcUser` từ hai Map rồi mong constructor tự chứng minh request HTTP được kiểm tra.

### 8.3. Tên principal

`DefaultOidcUser(..., "sub")` dùng `sub` làm name claim. Nếu production chọn một name attribute khác, test cần phản ánh chính xác, nhất là khi authorized client store dùng `principalName` làm một phần khóa.

## 9. Xây user service ánh xạ authorities dựa trên membership đáng tin

Giả sử OP xác thực user, nhưng **quyền xem báo cáo** do hệ thống nội bộ quản lý. Ứng dụng muốn thêm `ROLE_REPORT_VIEWER` khi user có membership hợp lệ, không tin một claim `role` tự phát.

Định nghĩa service tra role reactive:

```java
package com.example.security;

import java.util.Set;
import reactor.core.publisher.Mono;

public interface TenantRoleLookup {

    Mono<Set<String>> rolesFor(
        String issuer,
        String subject
    );
}
```

Ý nghĩa:

- `issuer` và `subject` lấy từ OIDC identity đã được xác minh.
- Return value có thể là `ROLE_REPORT_VIEWER` hoặc quyền theo policy.
- Implementation production có thể dùng Reactive Mongo/R2DBC/WebClient, nhưng phải non-blocking hoặc được cách ly khỏi event loop nếu không thể tránh blocking.
- Contract của ví dụ: `Mono.empty()` = không tìm thấy membership; tập role rỗng = không được phép vào ứng dụng tenant.

### 9.1. Cách viết wrapper user service

```java
package com.example.security;

import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.ReactiveOAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

import reactor.core.publisher.Mono;

public final class TenantMappingReactiveOidcUserService
        implements ReactiveOAuth2UserService<OidcUserRequest, OidcUser> {

    private final ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
        delegate;

    private final TenantRoleLookup roleLookup;

    public TenantMappingReactiveOidcUserService(
            ReactiveOAuth2UserService<OidcUserRequest, OidcUser> delegate,
            TenantRoleLookup roleLookup) {

        this.delegate = delegate;
        this.roleLookup = roleLookup;
    }

    @Override
    public Mono<OidcUser> loadUser(OidcUserRequest request) {

        return delegate.loadUser(request)
            .switchIfEmpty(Mono.error(denied()))
            .flatMap(user -> {

                if (user.getIdToken().getIssuer() == null
                        || user.getSubject() == null
                        || user.getSubject().isBlank()) {
                    return Mono.error(denied());
                }

                String issuer =
                    user.getIdToken().getIssuer().toString();

                String subject = user.getSubject();

                return roleLookup.rolesFor(issuer, subject)
                    .switchIfEmpty(Mono.error(denied()))
                    .flatMap(roles -> {

                        if (roles.isEmpty()) {
                            return Mono.error(denied());
                        }

                        Set<GrantedAuthority> authorities =
                            new LinkedHashSet<>(user.getAuthorities());

                        for (String role : roles) {
                            authorities.add(
                                new SimpleGrantedAuthority(role)
                            );
                        }

                        OidcUser mapped =
                            user.getUserInfo() == null
                                ? new DefaultOidcUser(
                                    authorities,
                                    user.getIdToken(),
                                    "sub"
                                  )
                                : new DefaultOidcUser(
                                    authorities,
                                    user.getIdToken(),
                                    user.getUserInfo(),
                                    "sub"
                                  );

                        return Mono.just(mapped);
                    });
            });
    }

    private static OAuth2AuthenticationException denied() {
        return new OAuth2AuthenticationException(
            new OAuth2Error("access_denied")
        );
    }
}
```

Đây là **ví dụ thiết kế policy**: ứng dụng chỉ cho phép user có membership/roles từ backend đăng nhập. Một ứng dụng cho phép user chỉ có identity nhưng chưa có role có thể chọn policy khác; quan trọng là **behavior thiếu membership phải được quyết định tường minh và kiểm thử**.

### 9.2. Vì sao dùng `delegate`?

`delegate` có thể là `OidcReactiveOAuth2UserService` mặc định hoặc một implementation đã được cấu hình để nạp UserInfo/đối chiếu claims. Wrapper chỉ bổ sung **business authority mapping**.

Lợi ích:

- Không tự viết lại giao thức HTTP UserInfo.
- Không thay thế OIDC token validation.
- Có thể fake delegate trong unit tests để chỉ kiểm tra mapping.
- Có thể integration-test delegate riêng với OP stub.
- Giữ identity/authorities gốc khi thêm quyền nội bộ.

### 9.3. Vì sao giữ authorities có sẵn?

`user.getAuthorities()` có thể chứa `OidcUserAuthority` và `SCOPE_...` từ framework. Nếu code thay tất cả bằng một tập roles mới, các thành phần downstream có thể mất thông tin OIDC/client scopes.

Ví dụ dùng:

```java
new LinkedHashSet<>(user.getAuthorities())
```

rồi thêm business roles, thay vì làm mất toàn bộ authorities gốc.

### 9.4. Vì sao không map role bằng `roles.toString()`?

Một tập:

```text
["ROLE_VIEWER", "ROLE_EDITOR"]
```

không nên trở thành **một** authority có giá trị `"[ROLE_VIEWER, ROLE_EDITOR]"`. Phải thêm từng `GrantedAuthority` với string chính xác theo policy.

### 9.5. Không dùng input role từ browser

`TenantRoleLookup` phải lấy quyền từ **nguồn tin cậy**, liên kết với issuer/subject đã xác minh và tenant context được cho phép. Không cho controller nhận `?role=ADMIN` rồi trả `Mono.just(Set.of("ROLE_ADMIN"))`.

## 10. Unit test thành công bằng `StepVerifier`

Khi test mapping, không cần Spring ApplicationContext.

```java
package com.example.security;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.ReactiveOAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TenantMappingReactiveOidcUserServiceTest {

    @Test
    void mapsTrustedRoleWithoutLosingOidcIdentity() {

        OidcUser fakeUser = OidcUserFixtures.userWithUserInfo();

        ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
            delegate = request -> Mono.just(fakeUser);

        TenantRoleLookup lookup = (issuer, subject) -> {
            assertThat(issuer)
                .isEqualTo("https://id.example.test");
            assertThat(subject)
                .isEqualTo("subject-42");

            return Mono.just(Set.of("ROLE_REPORT_VIEWER"));
        };

        var service =
            new TenantMappingReactiveOidcUserService(
                delegate,
                lookup
            );

        StepVerifier.create(
                service.loadUser(OidcRequestFixtures.request())
            )
            .assertNext(user -> {
                assertThat(user.getSubject())
                    .isEqualTo("subject-42");

                assertThat(user.getName())
                    .isEqualTo("subject-42");

                assertThat(user.getEmail())
                    .isEqualTo("alice@example.test");

                assertThat(user.getAuthorities())
                    .extracting(GrantedAuthority::getAuthority)
                    .contains(
                        "OIDC_USER",
                        "ROLE_REPORT_VIEWER"
                    );
            })
            .verifyComplete();
    }
}
```

### 10.1. Test này kiểm tra những gì?

- `loadUser` trả một `Mono` có đúng **một `OidcUser`**.
- Service truyền đúng **issuer + subject** cho membership lookup.
- Principal name dựa trên `sub` trong thiết kế ví dụ.
- OIDC profile vẫn tồn tại sau mapping.
- `ROLE_REPORT_VIEWER` được bổ sung.
- `OidcUserAuthority` gốc không bị mất.
- Publisher **complete**, không emit thêm user thứ hai hay lỗi.

### 10.2. Test không kiểm tra những gì?

- OP có thật sự cấp ID Token này hay không.
- Chữ ký ID Token/JWKS.
- Token endpoint.
- Cách Spring Security chọn user service khi callback.
- Các URL HTTP endpoints.
- Session/CSRF/authorization rules của controller.

Các vấn đề ấy có lớp integration test riêng.

### 10.3. Không dùng `block()` một cách mặc định

Một test có thể gọi `service.loadUser(...).block()`, nhưng `StepVerifier` biểu đạt **reactive signals** rõ hơn:

- `onNext`.
- `onComplete`.
- `onError`.
- Publisher trống.
- Behavior async/cancel nếu cần.

Trong production WebFlux, không gọi `block()` từ reactive security pipeline trên event-loop thread. Trong test, hãy ưu tiên `StepVerifier` để kiểm tra đúng reactive contract.

## 11. Test không có UserInfo

Một user có ID Token nhưng `getUserInfo()` bằng `null` vẫn có thể cần được mapping theo policy.

```java
@Test
void supportsOidcPrincipalWithoutUserInfo() {

    OidcUser noUserInfo =
        OidcUserFixtures.userWithoutUserInfo();

    ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
        delegate = request -> Mono.just(noUserInfo);

    TenantRoleLookup lookup = (issuer, subject) ->
        Mono.just(Set.of("ROLE_REPORT_VIEWER"));

    var service = new TenantMappingReactiveOidcUserService(
        delegate,
        lookup
    );

    StepVerifier.create(
            service.loadUser(OidcRequestFixtures.request())
        )
        .assertNext(user -> {
            assertThat(user.getUserInfo()).isNull();
            assertThat(user.getSubject())
                .isEqualTo("subject-42");
            assertThat(user.getAuthorities())
                .extracting(GrantedAuthority::getAuthority)
                .contains("ROLE_REPORT_VIEWER");
        })
        .verifyComplete();
}
```

Điểm cần kiểm tra là **không bị NPE và không tự tạo profile data không tồn tại**.

### 11.1. Không tự điền email giả

Nếu `email` thiếu, một số domain flows có thể chọn:

- Hiển thị placeholder không nhạy cảm.
- Đề nghị user bổ sung thông tin.
- Từ chối tính năng yêu cầu email đã xác minh.
- Lấy email từ internal profile service sau kiểm tra quyền.

Không tự điền `"unknown@example.org"` và dùng nó làm account-linking identity.

### 11.2. Không bỏ qua issuer/sub

Dù không có UserInfo, `iss`/`sub` từ ID Token phải là thành phần tin cậy của identity context. Unit test mapping cần phân biệt thiếu optional claims với thiếu required identity claims.

## 12. Test `Mono.empty()` từ delegate

Trong reactive service, `Mono.empty()` là một trạng thái riêng, **không phải success và không phải onError**.

Giả sử delegate không trả user:

```java
@Test
void emptyDelegateDoesNotBecomeSuccessfulLogin() {

    ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
        delegate = request -> Mono.empty();

    TenantRoleLookup lookup = (issuer, subject) ->
        Mono.just(Set.of("ROLE_REPORT_VIEWER"));

    var service = new TenantMappingReactiveOidcUserService(
        delegate,
        lookup
    );

    StepVerifier.create(
            service.loadUser(OidcRequestFixtures.request())
        )
        .expectErrorMatches(error ->
            error instanceof OAuth2AuthenticationException
        )
        .verify();
}
```

Wrapper ví dụ chọn:

```java
.switchIfEmpty(Mono.error(denied()))
```

để biến tình huống không có user thành một lỗi authentication có kiểm soát.

### 12.1. Vì sao không tự phát principal mặc định?

Một fallback kiểu:

```java
// SAI: service không tải được user nhưng lại cấp quyền.
return delegate.loadUser(request)
    .switchIfEmpty(Mono.just(adminUser));
```

có thể biến lỗi provider thành **privilege escalation**. Không phát `OidcUser` hoặc authority có quyền rộng khi dữ liệu authentication/identity cần thiết bị thiếu.

### 12.2. Khi nào `Mono.empty()` hợp lệ?

Một số repository/lookup có thể dùng `Mono.empty()` để biểu thị «không tìm thấy». Nhưng tại ranh giới **OIDC login tạo principal**, ứng dụng phải có policy rõ cho việc không có user. Bài này chọn **fail closed** khi không có membership, thay vì để authentication pipeline kết thúc mơ hồ.

## 13. Test không có membership

Một backend có thể xác thực `(issuer,sub)` hợp lệ nhưng chưa được cấp quyền truy cập tenant.

Test lookup trả rỗng:

```java
@Test
void missingMembershipIsDenied() {

    ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
        delegate = request ->
            Mono.just(OidcUserFixtures.userWithUserInfo());

    TenantRoleLookup lookup = (issuer, subject) ->
        Mono.empty();

    var service = new TenantMappingReactiveOidcUserService(
        delegate,
        lookup
    );

    StepVerifier.create(
            service.loadUser(OidcRequestFixtures.request())
        )
        .expectErrorMatches(error ->
            error instanceof OAuth2AuthenticationException ex
                && "access_denied"
                    .equals(ex.getError().getErrorCode())
        )
        .verify();
}
```

Có thể bổ sung case:

```java
TenantRoleLookup lookup = (issuer, subject) ->
    Mono.just(Set.of());
```

và kỳ vọng tương tự, vì ví dụ production service định nghĩa **empty role set = không được phép login**.

### 13.1. Test chính sách, không test giả định

Nếu sản phẩm cho phép người dùng mới đăng nhập nhưng chưa có quyền nghiệp vụ, test có thể kỳ vọng một principal **không có business roles**, và endpoint protected sẽ trả 403. Đó là một policy khác, không sai về mặt giao thức.

Điều phải làm là **viết rõ policy và có negative tests**, không cho hành vi rỗng tình cờ thành admin hoặc thành login thành công ngoài dự kiến.

### 13.2. `access_denied` và thông báo lỗi

Trong ứng dụng thật, hãy map lỗi authentication/authorization sang UX thích hợp mà không công bố:

- Internal user IDs.
- Access Tokens.
- Client secrets.
- Full UserInfo response.
- Database exception details.
- Tenant membership internals không cần thiết.

Test có thể assert error code nhưng không đòi trả stack trace cho browser.

## 14. Test lỗi từ service phụ thuộc

Giả sử DB tra membership bị lỗi:

```java
@Test
void propagatesMembershipLookupFailure() {

    ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
        delegate = request ->
            Mono.just(OidcUserFixtures.userWithUserInfo());

    TenantRoleLookup lookup = (issuer, subject) ->
        Mono.error(new IllegalStateException(
            "Synthetic membership backend failure"
        ));

    var service = new TenantMappingReactiveOidcUserService(
        delegate,
        lookup
    );

    StepVerifier.create(
            service.loadUser(OidcRequestFixtures.request())
        )
        .expectError(IllegalStateException.class)
        .verify();
}
```

Ví dụ wrapper **để lỗi lan truyền**, không tự cấp quyền. Ở integration layer, ứng dụng có thể chuẩn hóa lỗi thành authentication failure với thông điệp an toàn; không nhất thiết để nguyên Java exception đi tới browser.

### 14.1. Không fallback sang role cao

Anti-pattern:

```java
// KHÔNG được làm điều này:
.onErrorResume(error ->
    Mono.just(adminOidcUser)
)
```

Một lỗi database/network không nên làm người dùng được cấp quyền cao hơn.

### 14.2. Cẩn trọng với fallback chỉ còn quyền thấp

Có trường hợp ứng dụng muốn degrade gracefully khi membership service lỗi. Nếu cho người dùng tiếp tục login **không có quyền nhạy cảm**, cần phân tích threat model, policy và test phù hợp. Không tự coi mọi fallback quyền thấp là an toàn nếu application có endpoints chỉ kiểm tra `authenticated()` mà không kiểm tra role.

### 14.3. Test lỗi delegate

Cần có case:

```java
ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
    delegate = request -> Mono.error(
        new IllegalStateException("Synthetic UserInfo failure")
    );
```

Kỳ vọng lỗi không bị biến thành user có quyền. Nếu wrapper dùng `onErrorMap` để chuẩn hóa, test đúng loại lỗi/domain code do policy yêu cầu.

## 15. Test callback async: không gọi blocking API trong mapper

Một reactive implementation có thể vô tình gọi:

```java
// Không phù hợp khi chạy trực tiếp trên event-loop:
UserRoles roles = blockingJdbcRepository.findRoles(userId);
```

bên trong `map(...)` hoặc `flatMap(...)`. Code có thể hoạt động trong test đơn giản nhưng làm tắc event loop khi production có tải.

### 15.1. Đúng về mặt kiểu chưa chắc đúng về runtime

Đoạn sau **vẫn blocking**:

```java
Mono.just(
    blockingRepository.findRoles(userId)
);
```

vì `findRoles` được gọi **trước khi Mono được tạo**.

Một cách thiết kế tốt là sử dụng reactive data access thật:

```java
return roleRepository.findRoles(issuer, subject)
    .map(roles -> mapOidcUser(user, roles));
```

Nếu buộc dùng blocking adapter, cần thiết kế bounded elastic scheduler/isolated executor theo policy thay vì chạy blocking call trên event loop; ví dụ `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`. Đây là biện pháp tích hợp tạm thời, không biến JDBC thành non-blocking.

### 15.2. Unit test không tự chứng minh non-blocking

Một `StepVerifier` chạy nhanh không chứng minh production không block. Cần:

- Code review API dependencies.
- Các test xác nhận reactive subscription và scheduler nếu có custom adapter.
- BlockHound khi phù hợp và tương thích runtime/test stack.
- Quan sát thread pool/event loop trong integration/performance tests.
- Tránh `.block()` và blocking IO trong reactive authentication path.

Không thêm kiểm tra thread name cứng trong mọi unit test, vì scheduler có thể thay đổi theo môi trường.

## 16. Test tính lazy của Publisher

Reactor thường xây một pipeline khi method được gọi, sau đó thực thi khi có subscription.

Một mapping service nên không thực hiện các side effects nhạy cảm **trước subscription** ngoài những thao tác thuần túy cần thiết.

Ví dụ fake:

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger calls = new AtomicInteger();

TenantRoleLookup lookup = (issuer, subject) ->
    Mono.defer(() -> {
        calls.incrementAndGet();
        return Mono.just(Set.of("ROLE_REPORT_VIEWER"));
    });
```

Sau:

```java
Mono<OidcUser> result =
    service.loadUser(OidcRequestFixtures.request());
```

và trước `StepVerifier`, muốn kiểm tra laziness thì cần xác định chính xác **delegate và lookup được gọi tại assembly time hay subscription time**. Trong ví dụ wrapper, `delegate.loadUser(request)` được gọi khi assembly, nhưng HTTP/DB side effect bên trong reactive publisher thường xảy ra khi subscribe.

Sau subscription:

```java
StepVerifier.create(result)
    .expectNextCount(1)
    .verifyComplete();

assertThat(calls.get()).isEqualTo(1);
```

Đây là cách minh họa một **Publisher subscription**, không phải bảo đảm mọi implementation gọi factory function ở cùng thời điểm. Nếu cần xác minh chính xác subscribe/request/cancel, dùng `PublisherProbe`.

### 16.1. `PublisherProbe`

`reactor-test` cung cấp `PublisherProbe` để kiểm tra một publisher có thực sự được subscribe:

```java
import reactor.test.publisher.PublisherProbe;

PublisherProbe<Set<String>> probe =
    PublisherProbe.of(
        Mono.just(Set.of("ROLE_REPORT_VIEWER"))
    );

TenantRoleLookup lookup = (issuer, subject) ->
    probe.mono();
```

Sau khi chạy `StepVerifier` trên service:

```java
probe.assertWasSubscribed();
probe.assertWasRequested();
```

Cách này hữu ích khi có fallback branches: phải chắc rằng role lookup được gọi hoặc không gọi đúng theo điều kiện.

### 16.2. Tránh test over-specification

Không nên bắt test biết mọi internal `map/flatMap` count nếu nghiệp vụ chỉ cần principal đúng. Chỉ test subscription/cancellation khi đó thật sự là một contract quan trọng, ví dụ không gọi membership backend khi identity invalid.

## 17. Test UserInfo claims có đúng `sub` hay không

Trong OIDC, UserInfo response có claim `sub` và nó phải **khớp chính xác** với `sub` của ID Token dùng cho request.

Ví dụ:

```text
ID Token:  sub = "subject-42"
UserInfo:  sub = "subject-99"
```

Response đó không được hợp nhất thành cùng user.

### 17.1. Một unit test mapping đơn giản có thể bỏ sót lỗi

Nếu tạo:

```java
new DefaultOidcUser(
    authorities,
    idToken,
    userInfoWithDifferentSubject,
    "sub"
);
```

và không gọi phần validation UserInfo/OP service thật, test có thể **không phát hiện** mismatch. Test constructor principal không đồng nghĩa test giao thức.

### 17.2. Chọn đúng nơi kiểm tra

Để kiểm tra behavior này:

- Test `OidcReactiveOAuth2UserService` với UserInfo HTTP stub theo API/version đang dùng.
- Hoặc test một validation wrapper explicit so sánh hai subject trước khi tạo mapped principal.
- Trong integration test login, đảm bảo ID Token và UserInfo được liên kết đúng.
- Không dùng `mockOidcLogin()` để khẳng định đã kiểm tra UserInfo subject mismatch.

### 17.3. Test nhiều claim sources

Có thể cần kiểm tra:

| Claim | ID Token | UserInfo | Hành vi mong đợi |
|---|---|---|---|
| `sub` | `subject-42` | `subject-42` | Dùng identity phù hợp. |
| `sub` | `subject-42` | `subject-99` | Reject hoặc fail theo OIDC. |
| `email` | Không có | `alice@example.test` | Profile có thể bổ sung email. |
| `email_verified` | `false` | Không có | Không tự coi email được xác minh. |
| `name` | `Alice` | `Alice Example` | Quy tắc nguồn/merge rõ ràng. |
| `roles` | Không có | `["admin"]` | Không tự cấp admin nếu không có trust policy. |

Các response claims phải được tạo theo đúng fixture/test transport; không gửi Access Token thật tới endpoint giả lập.

## 18. Mapping scopes thành authorities: đừng nhầm claims

Trong Spring Security, authorities từ OAuth2 Login có thể bao gồm:

```text
OIDC_USER
SCOPE_openid
SCOPE_profile
ROLE_REPORT_VIEWER
```

Nhưng scope là quyền được cấp cho OAuth2 **client token**, trong khi role có thể là quyền nghiệp vụ của user tại ứng dụng. Chúng không tự đồng nghĩa.

### 18.1. `hasRole` và `hasAuthority`

`hasRole("ADMIN")` theo convention thường kiểm tra `ROLE_ADMIN`.

`hasAuthority("report:read")` kiểm tra chính xác chuỗi `report:read`.

`hasAuthority("SCOPE_orders.read")` kiểm tra đúng một scope authority nếu principal/authentication đang có authority đó theo mapper.

Test cần đối chiếu chính xác string. Không dùng `hasRole("SCOPE_orders.read")` rồi ngạc nhiên khi authorization thất bại.

### 18.2. Không tự cấp authority từ mọi claim có tên "roles"

Một OP có thể trả role của OP, không phải role của ứng dụng. Nếu production muốn tin một role claim cụ thể, cần giới hạn:

- Issuer tin cậy.
- Client/audience thích hợp.
- Claim location/type/schema.
- Tenant context.
- Quy tắc precedence nếu user thuộc nhiều tenant.
- Allowed values, mapping table.
- Default deny khi claim thiếu/sai.
- Quy trình cập nhật/revocation.

Unit tests phải có cả input hợp lệ và ác ý/sai định dạng.

### 18.3. Authority preservation

Nếu custom mapper chỉ trả:

```java
Set.of(new SimpleGrantedAuthority("ROLE_REPORT_VIEWER"))
```

mà bỏ authorities gốc, downstream có thể mất `OIDC_USER`/scope authorities mà các rule khác phụ thuộc.

Kiểm tra kết quả **có cả authority gốc và application authority mong đợi**, hoặc ghi rõ lý do bạn cố tình loại bỏ một loại authority.

## 19. Test role mapping khi input thay đổi kiểu

Claims từ JSON có thể là:

```json
{"roles": ["viewer", "editor"]}
```

hoặc:

```json
{"roles": "viewer editor"}
```

hoặc:

```json
{"roles": null}
```

hoặc một giá trị khác:

```json
{"roles": {"nested": "unexpected"}}
```

Không cast mù quáng:

```java
@SuppressWarnings("unchecked")
List<String> roles =
    (List<String>) claims.get("roles");
```

nếu provider contract không đảm bảo dữ liệu luôn đúng schema. Một response thay đổi kiểu có thể tạo `ClassCastException` trên luồng login.

### 19.1. Tách pure claim parsing để test

Một function ví dụ nhận claims:

```java
public static Set<String> parseAllowedRoles(
        Map<String, Object> claims) {

    Object raw = claims.get("roles");
    if (!(raw instanceof List<?> values)) {
        return Set.of();
    }

    Set<String> allowed = Set.of(
        "viewer",
        "editor"
    );

    Set<String> mapped = new HashSet<>();

    for (Object value : values) {
        if (!(value instanceof String text)) {
            continue;
        }

        if (allowed.contains(text)) {
            mapped.add(
                "ROLE_" + text.toUpperCase(Locale.ROOT)
            );
        }
    }

    return Set.copyOf(mapped);
}
```

Đây là **ví dụ parser cho một claim đã được trust theo contract riêng**. Không áp dụng nó cho claims từ provider bất kỳ mà chưa có policy: một danh sách role hợp lệ về cú pháp chưa đủ chứng minh user được cấp roles nghiệp vụ.

### 19.2. Test bảng đầu vào

| Input `roles` | Kết quả parser minh họa |
|---|---|
| `["viewer"]` | `ROLE_VIEWER` |
| `["viewer","editor"]` | Hai authorities. |
| `[]` | Tập rỗng. |
| `null` | Tập rỗng. |
| `"viewer"` | Tập rỗng theo contract chỉ nhận List. |
| `["viewer", 123]` | Chỉ chấp nhận entry chuỗi hợp lệ. |
| `["admin"]` | Không cấp role vì nằm ngoài allowlist. |
| `[{"name":"viewer"}]` | Không chấp nhận map. |
| `["VIEWER"]` | Không chấp nhận nếu contract case-sensitive. |

Cần import `Map`, `List`, `Set`, `HashSet` và `Locale`. Tùy schema thật, bạn có thể chọn reject toàn bộ claim sai dạng thay vì bỏ từng phần; **test phải theo đúng policy đã chọn**.

### 19.3. Avoid silent privilege expansion

Không biến mọi chuỗi bất kỳ thành:

```java
new SimpleGrantedAuthority("ROLE_" + input)
```

nếu input có thể chứa `SUPER_ADMIN` hoặc các giá trị ngoài policy. Dùng mapping table/allowlist của ứng dụng, không tạo quyền từ tên tự do.

## 20. Dùng `DefaultReactiveOAuth2UserService` khi không phải OIDC

Ở OAuth2 Login không phải OIDC, service có generic:

```java
ReactiveOAuth2UserService<OAuth2UserRequest, OAuth2User>
```

Một wrapper có thể enrich hoặc normalize các attributes đã nhận:

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.oauth2.client.userinfo.OAuth2UserRequest;
import org.springframework.security.oauth2.client.userinfo.ReactiveOAuth2UserService;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.security.oauth2.core.user.OAuth2User;

import reactor.core.publisher.Mono;

public final class ProfileMappingReactiveOAuth2UserService
        implements ReactiveOAuth2UserService<
            OAuth2UserRequest, OAuth2User> {

    private final ReactiveOAuth2UserService<
        OAuth2UserRequest, OAuth2User> delegate;

    public ProfileMappingReactiveOAuth2UserService(
            ReactiveOAuth2UserService<
                OAuth2UserRequest, OAuth2User> delegate) {

        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2User> loadUser(
            OAuth2UserRequest request) {

        return delegate.loadUser(request)
            .map(user -> {

                Object id = user.getAttributes().get("id");

                if (!(id instanceof String externalId)
                        || externalId.isBlank()) {
                    throw new IllegalArgumentException(
                        "Required external id is missing"
                    );
                }

                Map<String, Object> normalized =
                    new LinkedHashMap<>(user.getAttributes());

                normalized.put(
                    "app_external_key",
                    request.getClientRegistration()
                        .getRegistrationId() + ":" + externalId
                );

                return (OAuth2User) new DefaultOAuth2User(
                    user.getAuthorities(),
                    normalized,
                    "app_external_key"
                );
            });
    }
}
```

**Chú ý thiết kế:** key `registrationId + ":" + externalId` chỉ minh họa namespacing. Trong hệ thống thực, cần thêm issuer/provider trust, parsing/normalization của external ID và account linking. Không dùng một chuỗi này để tự cấp quyền truy cập dữ liệu hoặc liên kết user mà thiếu xác minh.

### 20.1. Test plain OAuth2 attributes

Tạo fake OAuth2 user:

```java
OAuth2User fake = new DefaultOAuth2User(
    Set.of(new SimpleGrantedAuthority("OAUTH2_USER")),
    Map.of(
        "id", "external-42",
        "login", "alice"
    ),
    "id"
);

ReactiveOAuth2UserService<OAuth2UserRequest, OAuth2User>
    delegate = request -> Mono.just(fake);
```

Tạo `OAuth2UserRequest`:

```java
var request = new OAuth2UserRequest(
    OidcRequestFixtures.registration(),
    OidcRequestFixtures.accessToken()
);
```

Đoạn này dùng registration fixture từ bài OIDC chỉ để tránh lặp cấu hình; trong project thực nên có fixture OAuth2-only với provider/registration của flow tương ứng.

Test:

```java
var service =
    new ProfileMappingReactiveOAuth2UserService(delegate);

StepVerifier.create(service.loadUser(request))
    .assertNext(user -> {
        assertThat(user.getName())
            .isEqualTo("company:external-42");
        assertThat(user.getAttributes())
            .containsEntry(
                "app_external_key",
                "company:external-42"
            );
    })
    .verifyComplete();
```

### 20.2. Vì sao phân biệt OIDC test?

`DefaultOAuth2User` không có `OidcIdToken` hoặc OIDC-specific `getUserInfo()`. Nếu production dùng `OidcUser`, dùng class và generic OIDC phù hợp trong test, tránh kiểm thử nhầm code path.

## 21. Kiểm tra mapping issuer và tenant

Với multi-tenant:

```text
tenant alpha -> issuer https://id.alpha.example
tenant beta  -> issuer https://id.beta.example
```

Cùng `sub="1001"` ở hai issuers không chứng minh cùng user.

### 21.1. Ma trận test identity

| Issuer | Subject | Tenant | Kỳ vọng |
|---|---|---|---|
| A | `1001` | alpha | Tìm membership alpha của identity A/1001. |
| A | `1002` | alpha | Không dùng roles của A/1001. |
| B | `1001` | beta | Không dùng roles của A/1001. |
| B | `1001` | alpha | Reject nếu policy không cho B vào alpha. |
| A | thiếu `sub` | alpha | Reject; không fallback email. |
| metadata issuer khác ID Token issuer | bất kỳ | alpha | Reject ở OIDC validation/registration boundary. |

### 21.2. Test phải dùng nguồn tenant đã xác thực

Nếu ứng dụng lấy tenant từ query:

```text
?tenant=alpha
```

không được coi đó là bằng chứng user có membership trong alpha. Với custom lookup, nên truyền **trusted tenant context** gắn với session, client registration, issuer hoặc membership đã xác minh.

Một user có thể được phép chuyển tenant, nhưng mỗi lần chuyển phải kiểm tra quyền, không chỉ đổi string.

### 21.3. Đừng làm user service tự fetch arbitrary issuer

`ReactiveOAuth2UserService` không nên nhận một URL bất kỳ từ browser rồi tải UserInfo ở đó. `ClientRegistration`/provider metadata phải đến từ nguồn tin cậy; outbound HTTP tới UserInfo endpoint cần destination policy để tránh SSRF/token exfiltration.

## 22. Kiểm tra không dùng email làm unique identity

Một test quan trọng:

```text
Issuer A:
  sub=subject-A
  email=shared@example.test

Issuer B:
  sub=subject-B
  email=shared@example.test
```

Nếu application mapping tìm user chỉ bằng email và gộp hai accounts, có thể gây account takeover.

Test nên assert:

- Khóa identity dựa trên **issuer + subject** đã xác minh.
- Email chỉ dùng làm attribute/lookup hỗ trợ theo policy.
- Không tự link external identity B vào account A chỉ vì email giống.
- Quyền của issuer A không được tự cấp cho issuer B.

### 22.1. `email_verified` chưa đủ cho mọi account linking

Ngay cả khi hai OP đều có `email_verified=true`, điều đó không tự bảo đảm hai external identities có cùng quyền với một internal account. Sản phẩm cần một quy trình account linking được ủy quyền và kiểm tra các trường hợp email tái sử dụng/compromise.

### 22.2. Test absence of claims

Nếu UserInfo thiếu `preferred_username`, tên hiển thị hoặc email, service phải có policy: bỏ qua, fallback profile field khác hoặc reject feature. Đừng để claim optional thiếu dẫn tới `NullPointerException` bất ngờ.

## 23. Đặc thù Reactive: `Mono` có ba kết quả chính

Trong reactive user service:

```text
Mono<OidcUser>
  |
  +-- onNext(user) -> onComplete
  |
  +-- onComplete không có user
  |
  +-- onError(error)
```

Cần test riêng:

| Signal | Ý nghĩa | Behavior trong ví dụ |
|---|---|---|
| `onNext(user), onComplete` | Mapping thành công | Trả principal với authorities đúng. |
| `onComplete` trống | Không có identity/membership | Chuyển thành `access_denied`. |
| `onError` | HTTP/DB/validation lỗi | Không cấp quyền; propagate/translate theo policy. |

Một test chỉ dùng:

```java
.expectNextCount(1)
```

mà không kiểm tra field/authorities có thể bỏ qua bug mapping. Dùng `assertNext(...)` cho business properties, rồi `verifyComplete()`.

### 23.1. Kiểm tra không emit hai users

`Mono` chỉ phát tối đa một phần tử. Nếu custom service ghép nhiều sources/records, phải chọn account deterministically hoặc reject ambiguity; không lấy phần tử đầu tùy ý từ nhiều external identities.

### 23.2. Test cancellation khi cần

Nếu reactive pipeline có side effects hoặc external calls dài, test cancellation có thể quan trọng để tránh tiếp tục xử lý sau khi authentication request bị hủy. Reactor Test hỗ trợ các APIs cancel/PublisherProbe; không cần test mọi method nếu không có behavior đặc biệt, nhưng phải hiểu cancellation trong WebFlux.

### 23.3. Không subscribe thủ công trong `loadUser`

Sai:

```java
roleLookup.rolesFor(issuer, sub)
    .subscribe(roles -> updateSomeGlobalState(roles));

return delegate.loadUser(request);
```

Đoạn này tách công việc thành side effect ngoài chuỗi `Mono`, khó quản lý lỗi, cancellation và context. Thay vào đó composition bằng `flatMap`/`map` để role lookup là một phần của authentication pipeline.

## 24. Những giới hạn khi mock delegate

Khi unit test:

```java
ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
    delegate = request -> Mono.just(fakeUser);
```

ta **đã bỏ qua** các bước trong delegate thật, như:

- Tạo UserInfo HTTP request.
- Gắn Access Token vào Authorization header.
- Parse response.
- Xử lý HTTP 401/403/5xx.
- Kiểm tra OIDC `sub` khớp.
- Quy tắc khi UserInfo endpoint không có.
- Provider-specific claim normalization bên trong delegate.

Điều này là đúng nếu test chỉ nhằm **business role mapping**.

### 24.1. Test delegate riêng

Để kiểm tra HTTP UserInfo:

1. Dùng một OP/UserInfo stub ở môi trường test.
2. Cấu hình `ClientRegistration` test với issuer, token URI và UserInfo URL đã biết.
3. Gọi `OidcReactiveOAuth2UserService.loadUser(request)` hoặc authentication integration phù hợp.
4. Xác nhận outbound request chứa token fixture đúng nơi.
5. Trả UserInfo JSON với `sub` đúng/sai, malformed JSON và lỗi HTTP.
6. Kiểm tra principal hoặc error signal.
7. Không cho stub endpoint request đi tới production host.
8. Hạn chế logging raw token, ngay cả token synthetic khi dùng patterns dễ copy sang production.

Tùy phiên bản Spring Security, cách tùy chỉnh `WebClient`/transport của built-in service có thể khác. Kiểm tra extension points của phiên bản project khi triển khai test HTTP, không giả định một setter cụ thể tồn tại trong mọi bản.

### 24.2. Đừng test built-in service bằng một fake đã thay toàn bộ behavior

Nếu test chỉ gọi wrapper với fake delegate rồi nói «UserInfo sub mismatch đã được xử lý», assertion thiếu lớp thực thi validation. Hãy viết test đúng lớp.

## 25. Test UserInfo HTTP bằng server giả lập

Một integration test cần test server có thể cung cấp:

```http
GET /userinfo HTTP/1.1
Host: localhost:<test-port>
Authorization: Bearer synthetic-access-token
```

Và response:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sub": "subject-42",
  "name": "Alice Example"
}
```

Các trường hợp cần kiểm tra:

| Response | Kỳ vọng |
|---|---|
| 200 + `sub` đúng | Tạo/merge UserInfo theo policy. |
| 200 + `sub` khác | Reject. |
| 200 nhưng thiếu `sub` | Reject UserInfo theo OIDC contract. |
| 401 | Không trả principal có quyền giả. |
| 403 | Không fallback sang role rộng hơn. |
| 429 | Rate-limit/backoff theo policy, không retry vô hạn. |
| 500 | Login failure/degrade theo policy rõ. |
| Body rỗng/sai JSON | Error signal được xử lý. |
| Body quá lớn | Giới hạn kích thước/cấu hình HTTP client. |
| Redirect tới host khác | Không gửi token sang destination chưa duyệt. |
| Timeout | Không treo event loop hoặc giữ session vô hạn. |

### 25.1. WireMock hay MockWebServer?

Cả hai có thể phục vụ HTTP responses giả, nhưng **không bắt buộc** cho unit test `ReactiveOAuth2UserService` bằng fake delegate.

Khi dùng, tạo server trên localhost hoặc interface test riêng, dùng dynamic port, clean state giữa tests. Không hardcode một port dễ conflict khi CI chạy song song.

### 25.2. HTTP stub không xác minh ID Token thật

Ngay cả khi service gọi UserInfo thật qua local stub, test vẫn có thể sử dụng `OidcIdToken` fixture không ký. Muốn kiểm tra **ID Token signature/issuer/audience/nonce**, phải có test token decoder/authentication component hoặc full OIDC flow integration với test signing keys.

### 25.3. Không cho HTTP fixture nhận real token

Dù test chạy localhost, tránh dùng client secret/Access Token thật làm request. Test server access logs và CI output có thể lưu toàn bộ Authorization header.

## 26. `WebTestClient` và `mockOidcLogin()`: mục tiêu khác

Trong reactive WebFlux, `spring-security-test` hỗ trợ:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;
```

Một request:

```java
webTestClient
    .mutateWith(mockOidcLogin()
        .idToken(token -> token.claim("sub", "subject-42")))
    .get()
    .uri("/account/me")
    .exchange()
    .expectStatus().isOk();
```

cho phép test controller đang nhận một OIDC principal đã được xác thực.

### 26.1. Vì sao không gọi `loadUser`?

`mockOidcLogin()` inject test authentication trực tiếp ở tầng WebFlux Security, thay vì thực thi:

```text
Authorization Code -> token endpoint -> ID Token validation
    -> ReactiveOAuth2UserService.loadUser()
```

Do đó:

- Test controller đọc `OidcUser` được.
- Test `hasRole`/`hasAuthority` được nếu authorities được cấp trong mock.
- Không kiểm tra HTTP UserInfo.
- Không chạy application role mapper tự động nếu mapper nằm trong user service.
- Không kiểm tra provider configuration/callback thật.

### 26.2. Hai test cần tồn tại song song

**Unit test service**:

```java
StepVerifier.create(mappingService.loadUser(request))
    .assertNext(user -> {
        // Verify mapped authorities/claims.
    })
    .verifyComplete();
```

**WebFlux route test**:

```java
webTestClient.mutateWith(mockOidcLogin()
        .authorities(
            new SimpleGrantedAuthority("ROLE_REPORT_VIEWER")
        ))
    .get().uri("/reports")
    .exchange()
    .expectStatus().isOk();
```

Test thứ hai kiểm tra **route khi authority đã tồn tại**, không kiểm tra authority ấy có được mapping chính xác từ external identity trong user service hay không.

## 27. Dựng WebFlux controller đơn giản

Ví dụ:

```java
package com.example.web;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class AccountController {

    @GetMapping("/account/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal OidcUser principal) {

        return Mono.just(
            Map.of(
                "sub", principal.getSubject()
            )
        );
    }
}
```

Test WebFlux:

```java
package com.example.web;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(AccountController.class)
class AccountControllerWebFluxTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void oidcUserSeesOwnSubject() {
        webTestClient
            .mutateWith(mockOidcLogin()
                .idToken(token ->
                    token.claim("sub", "subject-42")
                ))
            .get()
            .uri("/account/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.sub").isEqualTo("subject-42");
    }
}
```

Đây là **WebFlux slice**; nếu application có custom security configuration hoặc service dependencies, cần import/mocking phù hợp để filter chain/method security có hiệu lực theo mục tiêu test.

### 27.1. Không trộn MockMvc với WebTestClient reactive

Servlet MockMvc helper là:

```java
SecurityMockMvcRequestPostProcessors.oidcLogin()
```

Reactive WebFlux helper là:

```java
SecurityMockServerConfigurers.mockOidcLogin()
```

Dùng đúng loại server/application context. Một project có `WebClient` không tự có nghĩa server WebFlux nếu vẫn dùng Spring MVC.

### 27.2. `@WebFluxTest` và full context

`@WebFluxTest` chỉ load reactive web slice. Với integration test cấu hình OAuth2 Login và user service thật, dùng `@SpringBootTest` cùng `WebTestClient` được bind phù hợp, có thể kết hợp `@AutoConfigureWebTestClient` theo setup.

Nếu test slice thiếu user service Bean, đừng mock trống rồi tuyên bố integration wiring đã được xác minh.

## 28. Test route authorization sau khi mapping

Một policy:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/reports/**")
        .hasRole("REPORT_VIEWER")
    .anyExchange()
        .authenticated()
);
```

Các cases:

| Principal | Authority | Request | Kết quả |
|---|---|---|---|
| Anonymous | Không có | `GET /reports` | Yêu cầu authentication. |
| OIDC user | `ROLE_REPORT_VIEWER` | `GET /reports` | Allowed nếu controller thành công. |
| OIDC user | `ROLE_OTHER` | `GET /reports` | 403. |
| OIDC user | Không có business role | `GET /reports` | 403. |

Test:

```java
webTestClient
    .mutateWith(mockOidcLogin()
        .authorities(
            new SimpleGrantedAuthority("ROLE_OTHER")
        ))
    .get()
    .uri("/reports")
    .exchange()
    .expectStatus().isForbidden();
```

### 28.1. `ROLE_REPORT_VIEWER` khác `REPORT_VIEWER`

`hasRole("REPORT_VIEWER")` thường kiểm tra `ROLE_REPORT_VIEWER`.

Test mapping service phải tạo chính xác authority phù hợp với rule. Không chỉ assert tập authorities không rỗng.

### 28.2. Test cả request chưa authenticated

Các browser OAuth2 Login chains có thể redirect tới login page/OP thay vì trả 401. Reactive API chain có thể trả 401. Assertions phải theo **entry point và security chain thực**, không hardcode một status duy nhất cho mọi endpoint.

### 28.3. Method security cần proxy thực

Nếu `@PreAuthorize` nằm trên service Bean, `@WebFluxTest` mock service thường không thực thi method security của production service. Muốn test method security, phải load đúng Bean/proxy và kích hoạt reactive method security theo cấu hình.

## 29. Test lỗi mapping nhưng không rò thông tin

Một custom mapper có thể ném:

```java
new OAuth2AuthenticationException(
    new OAuth2Error("access_denied")
)
```

Đó là security-relevant error. Tests nên kiểm tra:

- Error code rõ ràng theo policy.
- Không có user/role được phát ra sau lỗi.
- Không fallback thành admin.
- Không log raw ID Token/Access Token/Refresh Token.
- Không trả stack trace/UserInfo response cho browser.
- Nếu có audit, chỉ ghi issuer alias, registration, correlation ID, error code đã làm sạch.

### 29.1. Test error signal

```java
StepVerifier.create(service.loadUser(request))
    .expectErrorMatches(error ->
        error instanceof OAuth2AuthenticationException ex
            && "access_denied"
                .equals(ex.getError().getErrorCode())
    )
    .verify();
```

### 29.2. HTTP status của login failure không phải lúc nào là 403

`loadUser` error có thể được Spring Security OAuth2 Login failure handler xử lý bằng redirect hoặc response tùy configuration. Không tự suy rằng mọi `OAuth2AuthenticationException` của login trở thành HTTP 403.

Unit test nên assert reactive error; integration test riêng xác minh failure handler/UX.

### 29.3. Không gọi logs trong test để xác nhận token

Nếu debug, chỉ hiển thị metadata như issuer alias, registration ID, principal diagnostic key và error code. Đừng in raw `request.getAccessToken().getTokenValue()`.

## 30. Test error propagation giữa delegate và lookup

Có hai sources lỗi:

```text
delegate.loadUser()
  |
  +-- lỗi UserInfo/claims
  |
  v
membershipLookup.rolesFor(...)
  |
  +-- lỗi DB/permissions
```

Unit tests nên phân biệt chúng:

| Source | Fake output | Expected behavior |
|---|---|---|
| Delegate | `Mono.just(user)` | Chạy lookup rồi map. |
| Delegate | `Mono.empty()` | Reject, không gọi lookup. |
| Delegate | `Mono.error(error)` | Propagate/normalize, không gọi lookup. |
| Lookup | `Mono.just(roles)` | Map authorities. |
| Lookup | `Mono.just(emptySet)` | Deny theo policy ví dụ. |
| Lookup | `Mono.empty()` | Deny. |
| Lookup | `Mono.error(error)` | Fail closed, không cấp user. |

Có thể dùng `PublisherProbe`, fake counter hoặc Mockito `verify(...)` để xác nhận role lookup **không được gọi khi delegate thất bại**.

### 30.1. Không retry vô hạn ở authentication path

Nếu membership service/network lỗi, retry không giới hạn có thể giữ login requests và gây DoS. Nếu cần retry transient errors, hãy giới hạn số lần, timeout, backoff và chỉ retry những lỗi idempotent phù hợp.

### 30.2. Authenticated nhưng chưa có membership

Một product có thể cho user login rồi hiển thị onboarding page; product khác chặn login nếu chưa được cấp quyền. Unit test phải biểu diễn quyết định đó, không dùng một default từ framework làm policy ngầm.

## 31. Test nhiều registrations và claim name mapping

Một provider trả:

```json
{
  "sub": "subject-42",
  "preferred_username": "alice"
}
```

Provider khác có thể trả:

```json
{
  "sub": "subject-99",
  "preferred_username": "alice"
}
```

Nếu application đặt:

```text
principalName = preferred_username
```

có thể tạo collisions. `OAuth2AuthorizedClientService` trong Servlet/Reactive service variants thường định danh authorized client theo registration ID và principal name; đổi cách đặt principal name có thể gây lỗi load token.

### 31.1. Test registration-specific mapping

Test nên bảo đảm:

- Issuer A và registration A cho principal A.
- Issuer B và registration B cho principal B.
- Một tên hiển thị giống nhau không làm merge identities.
- Đổi role mapping cho tenant A không ảnh hưởng tenant B.
- Client registration lookup không đến từ input URL tùy ý.
- UserInfo endpoint đúng provider.
- Nếu account linking được hỗ trợ, nó dùng một flow xác thực/consent riêng.

### 31.2. Mapping claim type mismatch

Một claim `sub` thiếu/sai dạng không được fallback sang email hoặc username tùy ý. Nếu app cần external ID khác, phải xác định schema provider được tin và validation tường minh.

### 31.3. Test principal name ổn định

Nếu custom mapper tạo `DefaultOidcUser` mới, kiểm tra:

```java
assertThat(user.getName()).isEqualTo("subject-42");
```

Điều này quan trọng khi authorized client store, audit và session logic phụ thuộc `Authentication.getName()`.

## 32. Không vô tình bỏ UserInfo khi map `OidcUser`

Khi tạo một `DefaultOidcUser` mới chỉ từ ID Token:

```java
new DefaultOidcUser(authorities, user.getIdToken(), "sub");
```

trong khi `user.getUserInfo()` trước đó không null, bạn có thể đánh mất thông tin profile đã được tải.

Đoạn wrapper ở trên phân nhánh:

```java
user.getUserInfo() == null
    ? new DefaultOidcUser(
        authorities,
        user.getIdToken(),
        "sub"
      )
    : new DefaultOidcUser(
        authorities,
        user.getIdToken(),
        user.getUserInfo(),
        "sub"
      )
```

Test nên xác minh:

- ID Token còn giữ nguyên claims cần thiết.
- UserInfo vẫn được giữ nếu có.
- `sub`/`getName()` không đổi ngoài ý muốn.
- Authorities cũ được bảo toàn hoặc thay đổi theo policy có chủ đích.
- Không tạo bản sao token/profile trong logs.

### 32.1. Không sửa trực tiếp Map từ framework

Các claims maps có thể immutable. Thay vì mutate `user.getClaims()`, hãy tạo một cấu trúc mới khi cần, tuân thủ constructor/API `DefaultOidcUser`/`DefaultOAuth2User` phù hợp.

### 32.2. Một số claims có thể chồng giữa ID Token và UserInfo

Khi một claim xuất hiện ở cả hai nguồn, behavior merge của implementation có thể ảnh hưởng `getClaims()`. Nếu business logic phụ thuộc precedence, hãy test rõ với framework/version thực, và tránh dùng một claim dễ xung đột làm identity/authorization key khi có lựa chọn đáng tin hơn.

## 33. Kiểm thử timeout và cancellation

Một authentication user service có thể gọi UserInfo endpoint và backend membership. Nếu một downstream không phản hồi, login không nên treo vô hạn.

Ví dụ một policy timeout tại boundary:

```java
return delegate.loadUser(request)
    .timeout(Duration.ofSeconds(5));
```

Đây chỉ là fragment để minh họa giới hạn thời gian; timeout thực cần xét toàn bộ pipeline và nên được cấu hình theo SLA/provider. Không đặt một con số cố định thiếu kiểm chứng cho mọi tenant.

### 33.1. Unit test timeout không cần chờ thời gian thật

`reactor-test` có `StepVerifier.withVirtualTime(...)` để test những operators dựa trên scheduler ảo khi setup đúng.

Tuy nhiên, không phải HTTP network I/O hoặc thư viện bên ngoài đều tuân theo virtual time. Với UserInfo HTTP stub, thường dùng timeout thực ngắn và deterministic stub hoặc mock publisher.

### 33.2. Fail closed khi timeout

Không nên:

```java
.onErrorResume(TimeoutException.class,
    error -> Mono.just(adminUser))
```

Nếu membership không xác định, mặc định không cấp quyền cao. Nếu có offline/last-known-good roles cache, cần expiry, revocation và policy riêng; test phải kiểm tra không dùng quyền đã bị thu hồi.

### 33.3. Cancellation và resource cleanup

Khi request bị cancel, các reactive operators/HTTP clients cần giải phóng tài nguyên phù hợp. Một user service không nên tự `subscribe()` một tác vụ nền không quản lý chỉ để lưu role, vì cancellation/error có thể mất kiểm soát.

## 34. Test HTTP client không gửi token sai đích

Một OIDC user service có thể gọi `userinfo_endpoint` với Access Token. Khi cấu hình dynamic providers/tenants, cần bảo đảm URL này được tin cậy.

Rủi ro:

```text
UserInfo endpoint trong metadata:
  https://untrusted.example/collect

Ứng dụng:
  GET URL đó
  Authorization: Bearer <user-access-token>
```

Đó là **credential exfiltration** nếu metadata/registration chưa được kiểm soát.

### 34.1. Integration test destination

Một HTTP stub có thể ghi nhận:

- Host/path mà request tới.
- Có `Authorization: Bearer synthetic-access-token`.
- Không có client secret/Refresh Token.
- Không follow redirect tới host khác không được phép.
- Có TLS/timeout/destination restrictions theo policy.

Không cần hiển thị raw token cho test caller; có thể so giá trị fixture trong stub server isolation.

### 34.2. Unit test mapping không kiểm tra SSRF

Unit test dùng fake delegate không thực hiện network, nên không thể phát hiện UserInfo destination SSRF. Hãy phân chia các yêu cầu bảo mật theo đúng lớp test.

## 35. Test integration wiring thực sự gọi user service

Một vấn đề thường gặp: class `TenantMappingReactiveOidcUserService` có unit tests pass, nhưng Spring Security production **không dùng class đó**, vì:

- Chưa đăng ký Bean.
- Có nhiều Bean cùng generic type và configuration chọn sai.
- Tùy chỉnh OAuth2 non-OIDC user service thay vì OIDC service.
- SecurityWebFilterChain phù hợp không nhận config.
- Test context khác production.
- Provider-specific registration hoặc chain order khiến flow đi qua một authentication manager khác.

### 35.1. Cần test wiring riêng

Một integration test có thể dùng test OP:

1. Khởi động WebFlux application context chứa security config thật.
2. Dùng ClientRegistration test trỏ tới OP stub.
3. Khởi động login authorization flow có `state`/session context hợp lệ.
4. OP stub phát authorization code/token/ID Token theo cấu hình kiểm thử.
5. Đảm bảo user service custom được gọi.
6. Kiểm tra user sau login mang authorities đúng.
7. Kiểm tra failure khi membership không tồn tại.
8. Không dùng production OP/credentials.

Tùy API của phiên bản Spring Security, cơ chế gắn service trong reactive OAuth2 Login configuration khác Servlet. **Không sao chép mù quáng đoạn Servlet `oauth2Login().userInfoEndpoint().oidcUserService(...)` vào WebFlux** mà chưa xác nhận Reactive DSL/extension point đúng bản.

### 35.2. MockBean có thể che wiring thật

Nếu test thay toàn bộ authentication manager/user service bằng mock trả `OidcUser`, nó không còn chứng minh production mapper được gọi. Có thể dùng **spy** hoặc test stub ở ranh giới HTTP/membership để giữ custom mapping real.

### 35.3. Test đủ sâu nhưng không tạo dependency ngoài cần thiết

Không yêu cầu một browser thật cho mọi unit test. Chỉ các tests xác minh full callback/session/cookie/OP flow mới cần integration/E2E phù hợp.

## 36. Test reactive security context và concurrency

Trong WebFlux, authentication thường nằm trong **Reactor Context**, không chỉ Servlet-style `ThreadLocal`.

Nếu custom mapper dùng:

```java
SecurityContextHolder.getContext()
    .getAuthentication();
```

ở một callback chạy trên thread khác, có thể không thấy ngữ cảnh đúng, hoặc tạo bug do sai giả định.

### 36.1. Dùng identity có trong request

`OidcUserRequest` chứa client registration/access token/ID token liên quan; identity sau delegate có issuer/subject. Với business role lookup, nên truyền **định danh explicit**:

```java
roleLookup.rolesFor(issuer, subject)
```

hơn là để role lookup đọc một ThreadLocal không ổn định.

### 36.2. Test nhiều users song song

Các test đồng thời có thể phát hiện state bị chia sẻ:

```text
User A -> subject-A -> ROLE_VIEWER
User B -> subject-B -> ROLE_EDITOR
```

Không lưu current OIDC user vào một field mutable singleton rồi tái sử dụng giữa requests. `ReactiveOAuth2UserService` có thể là Bean singleton, nhưng `loadUser` phải xử lý input theo từng subscription/request mà không để shared mutable user state bị trộn.

### 36.3. Test concurrent mapping

Có thể dùng `Flux.merge` từ nhiều `Mono<OidcUser>` fixtures với `StepVerifier`; mỗi kết quả phải mang đúng issuer, subject và authorities. Không dựa vào thứ tự trả về của network async calls để liên kết identity.

### 36.4. Tránh cache roles theo email

Nếu cache membership theo email, hai providers có cùng email có thể bị trộn. Cache key phải đủ identity boundary, ví dụ `issuer + sub + tenant` theo trusted policy, và có expiry/invalidation phù hợp.

## 37. Trường hợp account linking và delegated access

Một user có thể login qua company OP và liên kết thêm partner account.

```text
Internal Account employee-42
  |
  +-- Issuer company, sub=subject-C
  |
  +-- Issuer partner, sub=subject-P
```

Custom user service không được tự kết luận hai records là cùng một internal user chỉ vì email giống nhau. Account linking cần quy trình proof-of-control/consent riêng.

### 37.1. Tests cần có

- Identity company chưa linked → không được dùng partner token.
- Hai identities có cùng email → không tự link.
- Linked identity đã được xác minh → mapping vào internal account theo policy.
- Unlink partner → không dùng lại authorized client/roles partner.
- Tenant đổi membership → quyền được cập nhật theo policy.
- Provider issuer migration → không tự reuse token/role issuer cũ.

### 37.2. Không coi Access Token là identity key

Access Token có thể rotate/expire, không phải định danh vĩnh viễn. Dùng issuer/subject đã xác minh và application identity mapping; không lấy Access Token string làm user ID hoặc log key.

## 38. Test security regression theo bảng scenario

| ID | Trường hợp | Fixture/nguồn | Kỳ vọng |
|---|---|---|---|
| R01 | Delegate trả user OIDC bình thường | `Mono.just(user)` | Mapping thành công. |
| R02 | Delegate không có user | `Mono.empty()` | Deny theo policy. |
| R03 | Delegate lỗi HTTP | `Mono.error(...)` | Fail closed; không lookup roles. |
| R04 | Có UserInfo | `OidcUserInfo` hợp lệ | Profile được giữ. |
| R05 | Không có UserInfo | `null` | Không NPE. |
| R06 | UserInfo `sub` mismatch | Stub OP | Reject theo OIDC. |
| R07 | UserInfo thiếu `sub` | Stub OP | Reject. |
| R08 | Membership đúng | Reactive role lookup | Có authority được phép. |
| R09 | Không có membership | `Mono.empty()` | Deny hoặc behavior đã định. |
| R10 | Membership rỗng | Empty `Set` | Không cấp role trái policy. |
| R11 | Membership DB lỗi | `Mono.error(...)` | Không fallback admin. |
| R12 | Cùng `sub`, khác issuer | Hai OIDC fixtures | Identity không bị trộn. |
| R13 | Cùng email, khác subject | Hai OIDC fixtures | Không tự account-link. |
| R14 | Role claim sai kiểu | JSON/Map fixture | Fail/ignore theo contract. |
| R15 | Role ngoài allowlist | Claim `admin` từ nguồn không tin | Không cấp quyền cao. |
| R16 | Mapping thêm role | Trusted lookup | Giữ OIDC authorities gốc. |
| R17 | Principal name | `sub` fixture | Stable identity key. |
| R18 | OAuth2-only provider | `DefaultOAuth2User` | Mapping đúng generic service. |
| R19 | WebFlux route có role | `mockOidcLogin()` | HTTP allowed. |
| R20 | WebFlux route thiếu role | Mock OIDC user | HTTP 403. |
| R21 | UserInfo endpoint lỗi | Stub HTTP | Không trả quyền giả. |
| R22 | UserInfo HTTP timeout | Stub/publisher | Timeout/fail theo policy. |
| R23 | UserInfo URL không tin | Endpoint policy | Không gửi token. |
| R24 | Custom service không được wiring | Full test config | Test phát hiện missing invocation. |
| R25 | Concurrency hai users | Two publishers | Không trộn authorities. |
| R26 | Role lookup không bị gọi khi delegate lỗi | PublisherProbe/Mockito | Không subscription ngoài ý muốn. |
| R27 | Sự cố không log token | Logging assertion nếu cần | Không có raw credential. |
| R28 | Provider change/tenant mismatch | Multiple registrations | Reject/reauthorize đúng boundary. |

Bảng là **kế hoạch bao phủ**, không có nghĩa một unit test duy nhất có thể kiểm tra mọi trường hợp. Những case thuộc HTTP/OP/security wiring cần dùng tầng integration test thích hợp.

## 39. Các lỗi thường gặp khi chạy test

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `Cannot resolve symbol StepVerifier` | Thiếu `reactor-test` ở test scope. | Thêm dependency test đồng bộ Reactor version. |
| `OidcUserRequest` không tìm thấy | Import sai package hoặc thiếu oauth2-client. | Kiểm tra Spring Security version/classpath. |
| Test dùng `OAuth2UserRequest` nhưng service cần `OidcUserRequest` | Sai generic/service type. | Tạo đúng fixture OIDC. |
| Test UserInfo mapper pass nhưng route thiếu role | Spring wiring không dùng service custom. | Test reactive login configuration. |
| `mockOidcLogin()` route pass nhưng service mapping bug | Mock login bypass mapping. | Thêm `StepVerifier` unit test service. |
| `@AuthenticationPrincipal OidcUser` null | Test inject user không phải OIDC principal. | Dùng `mockOidcLogin()`. |
| `@WebFluxTest` không tìm được Bean | Slice không load business dependencies. | Mock/import Bean đúng phạm vi. |
| `getName()` khác mong đợi | Name attribute key hoặc claims khác. | Kiểm tra `DefaultOidcUser` constructor/fixture. |
| Lỗi `ClassCastException` ở roles | Claim sai kiểu dữ liệu. | Parser/schema validation và negative cases. |
| Map claims immutable | Test/custom mapper cố mutate Map. | Copy dữ liệu hoặc tạo principal mới đúng API. |
| Authorities bị mất sau mapper | Tạo set mới không giữ OIDC authorities. | Bảo toàn theo policy và assert. |
| `Mono.empty()` làm login không rõ lỗi | Không có policy cho empty publisher. | `switchIfEmpty`/fail closed. |
| Mapping lỗi nhưng test vẫn success | `onErrorResume` fallback quá rộng. | Assert error path, loại bỏ privilege fallback. |
| Test cứ treo | Blocking IO, Mono không complete hoặc external dependency. | Test fake và timeout/resource cleanup. |
| Test flaky theo ngày | `Instant.now()` và token expiry. | Fixed Clock/Instants. |
| 401 thay vì 403 | Không có authentication đúng. | Xác định entry point/filter chain. |
| 302 thay vì 401 | Browser OAuth2 login redirect. | Dùng đúng WebFlux chain assertion. |
| Test UserInfo gọi OP production | Test registration/issuer-uri bị dùng lại. | Test profile và local stub. |
| Same email hai issuers bị gộp | Mapping theo email thay `iss/sub`. | Security identity boundary. |
| Logout test không xóa token | RP session và authorized client lifecycle riêng. | Test đúng storage/policy. |
| Tests fail khi chạy song song | Shared static mutable principal/lookup/cache. | Per-test fixtures, immutable data. |

### 39.1. Quy trình debug có kiểm soát

```mermaid
flowchart TD
    A["Reactive mapping test lỗi"] --> B{"loadUser có emit user?"}
    B -->|Không, empty| C["Kiểm tra delegate và switchIfEmpty"]
    B -->|Không, error| D{"Lỗi từ delegate hay lookup?"}
    D -->|Delegate| E["UserInfo/OIDC fixture, HTTP stub, sub validation"]
    D -->|Lookup| F["Membership DB/fake, timeout, error policy"]
    B -->|Có| G{"Principal/claims đúng?"}
    G -->|Không| H["Issuer/sub, UserInfo merge, name claim"]
    G -->|Có| I{"Authorities đúng?"}
    I -->|Không| J["Role mapping, allowlist, preservation"]
    I -->|Có| K{"WebFlux route vẫn sai?"}
    K -->|Có| L["mockOidcLogin vs real service wiring, security matcher"]
    K -->|Không| M["Test layer hoàn tất; kiểm tra OP flow nếu mục tiêu yêu cầu"]
```

Đừng debug bằng cách in token values. Chỉ ghi metadata/fixture identifiers vô hại, error code và registration alias.

## 40. Anti-pattern cần tránh

### 40.1. Chỉ test `mockOidcLogin()`

Nó kiểm tra route với authentication đã có, không chạy user service hoặc HTTP UserInfo. Phải có unit tests trực tiếp cho `loadUser`.

### 40.2. Dùng `@WithMockUser` của Servlet trong reactive test một cách vô ý thức

WebFlux Test có mock OIDC authentication riêng. Nếu application cần `OidcUser`, generic mock username/password không kiểm tra đúng principal type.

### 40.3. Map role từ claim chưa có trust policy

`"role": "admin"` không tự đủ quyền `ROLE_ADMIN`. Kiểm tra issuer, schema, allowlist và business policy.

### 40.4. Fallback admin khi lookup lỗi

Một lỗi DB/HTTP không được biến thành cấp quyền rộng. Fail closed theo chính sách.

### 40.5. Bỏ qua `Mono.empty()`

Reactive empty publisher khác error. Test explicit expected behavior.

### 40.6. Dùng blocking repository trực tiếp trên event loop

Không để `block()`/JDBC blocking call trong reactive authentication path mà không có adapter/scheduler phù hợp.

### 40.7. Tạo mới `DefaultOidcUser` rồi làm mất UserInfo

Nếu user có UserInfo, cần giữ nó theo policy hoặc giải thích lý do bỏ. Test profile preservation.

### 40.8. Coi same email là same OIDC identity

Identity cần issuer + subject đã xác minh. Test multi-provider collisions.

### 40.9. Dùng ID Token fixture như bằng chứng signature validation

Constructor fixture không xác minh chữ ký; test decoder/OP flow riêng.

### 40.10. Tự subscribe trong user service

Tách subscription khỏi `Mono` làm lỗi/cancellation khó kiểm soát. Composition bằng `flatMap`/`map`.

### 40.11. Test provider thật ở mọi commit

Dễ flaky, lộ credential và phụ thuộc MFA/network. Dùng synthetic fixtures và test OP riêng.

### 40.12. Để custom user service có state mutable theo request

Một Bean singleton với field `currentUser` có thể trộn principals giữa concurrent WebFlux requests. Dùng variables trong publisher/request context.

### 40.13. Nghĩ UserInfo `sub` được kiểm tra chỉ vì object constructor pass

Test OIDC user-service validation/HTTP integration nếu đó là mục tiêu. Không chỉ mock prevalidated principal.

### 40.14. Cho claim sai kiểu làm app crash không kiểm soát

Dùng parser/schema validation và negative tests. Không cast mọi claim theo giả định.

### 40.15. Không test registration/provider routing

Một service mapping đúng nhưng được gắn sai registration/chain vẫn gây lỗi. Cần integration wiring test.

## 41. Kiến trúc kiểm thử khuyến nghị

```text
                  Spring Security WebFlux OIDC Client
                              |
             +----------------+------------------+
             |                                   |
             v                                   v
      Unit tests                           Integration tests
      No Spring Context                    Spring WebFlux Context
             |                                   |
   OidcUserRequest fixture                  Test ClientRegistration
   Fake OidcUser delegate                   Local OP stub/JWKS
   Fake TenantRoleLookup                    SecurityWebFilterChain
             |                                   |
             v                                   v
   TenantMappingReactiveOidcUserService     Real OIDC Login wiring
             |                                   |
             v                                   v
      Mono<OidcUser>                           User Service
             |                                   |
             v                                   v
        StepVerifier                       Authenticated principal
      - user subject                            |
      - issuer checks                           v
      - profile claims                       WebTestClient
      - authorities                        + mockOidcLogin
      - empty/error                         for route-only tests
      - non-blocking design
             |
             v
     Security regression matrix
       tenant/provider/claim cases

  Additional boundary tests:
    - UserInfo HTTP destination and Bearer token handling
    - JWT/ID Token validation and issuer/audience/nonce
    - Role/membership source trust
    - Multi-tenant account linking
    - Browser cookie/redirect behavior
    - Secure observability and token redaction
```

Cách chia này giúp mỗi lỗi có một nơi dễ xác định: lỗi parsing roles ở unit test, lỗi thiếu user-service wiring ở context test, lỗi token/JWKS ở OP integration test, lỗi SameSite/cookie ở browser test.

## 42. Trình tự triển khai đề xuất

Khi cần viết tests cho `ReactiveOAuth2UserService` và ánh xạ claims:

1. **Xác nhận app dùng Spring WebFlux**, không phải Spring MVC Servlet.
2. **Xác định service đang được chạy**: OAuth2 User Service hay OIDC User Service.
3. **Thêm `reactor-test` và `spring-security-test` vào test scope** với versions đồng bộ BOM.
4. **Tạo fixture `ClientRegistration`, Access Token, ID Token và UserInfo** hoàn toàn synthetic.
5. **Tạo fake delegate** để unit test không gọi mạng.
6. **Tách trusted membership/role lookup** thành dependency có contract reactive rõ.
7. **Dùng `StepVerifier`** để assert values, claims, principal name, authorities và completion.
8. **Giữ issuer/sub identity boundary**; không dùng email làm unique principal key.
9. **Test cả có và không có UserInfo**, giữ profile khi enrich authorities.
10. **Test `Mono.empty()` từ delegate và lookup**, quyết định fail closed theo policy.
11. **Test `Mono.error()` và timeout**, không fallback quyền cao.
12. **Kiểm tra claim schema/type và role allowlist**, không biến mọi chuỗi thành authority.
13. **Kiểm tra authorities gốc không bị mất** khi custom mapper tạo `DefaultOidcUser` mới.
14. **Test multi-provider/tenant collisions** với cùng `sub` hoặc cùng email.
15. **Test concurrency** nếu service có caching/state và tránh mutable singleton user fields.
16. **Dùng `PublisherProbe`** khi cần xác nhận lookup được subscribe đúng branch.
17. **Test UserInfo HTTP và `sub` mismatch** bằng local stub nếu muốn xác minh delegate thật.
18. **Test `mockOidcLogin()` riêng với WebTestClient** để kiểm tra route/method authorization.
19. **Dùng integration test có stub OP** để xác nhận custom reactive user service thật sự được gọi trong login flow.
20. **Không lấy kết quả một tầng test làm bằng chứng tầng khác**: claims mapping, OIDC protocol validation, Resource Server authorization và browser security đều có tests riêng.
21. **Không dùng credentials thật hoặc log raw tokens** trong test/CI.
22. **Giữ failure reports an toàn**, ưu tiên issuer/registration alias, error code và correlation ID nội bộ.
23. **Đảm bảo tests độc lập và deterministic**, không phụ thuộc thứ tự, thời gian hiện tại hoặc OP production.

## 43. Tài liệu tham khảo

- [Spring Security Reference — OAuth2 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Security Reference — OAuth2 Client (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html)
- [Spring Security Reference — WebFlux Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Security Reference — Testing WebFlux OAuth2](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security API — ReactiveOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/ReactiveOAuth2UserService.html)
- [Spring Security API — DefaultReactiveOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/DefaultReactiveOAuth2UserService.html)
- [Spring Security API — OidcReactiveOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcReactiveOAuth2UserService.html)
- [Spring Security API — OidcUserRequest](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserRequest.html)
- [Spring Security API — OidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html)
- [Spring Security API — DefaultOidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/DefaultOidcUser.html)
- [Spring Security API — OidcUserAuthority](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUserAuthority.html)
- [Spring Security API — OAuth2UserRequest](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/OAuth2UserRequest.html)
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Spring Boot Reference — Testing WebFlux](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [OpenID Connect Core 1.0 — ID Token và UserInfo](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

**Kết luận:** kiểm thử **`ReactiveOAuth2UserService`** trong Spring Security WebFlux phải kiểm tra trực tiếp **`Mono<OidcUser>` hoặc `Mono<OAuth2User>`** bằng **`StepVerifier`**, với delegate/UserInfo, ID Token và trusted membership lookup được giả lập có kiểm soát. Test cần xác nhận **issuer + subject, principal name, preserved claims/UserInfo, đúng authority strings, empty/error behavior, tenant isolation và không cấp quyền khi phụ thuộc lỗi**. Dùng **`mockOidcLogin()` với WebTestClient** để kiểm tra endpoint khi principal đã tồn tại, nhưng đừng nhầm nó với test việc nạp user hay ánh xạ claims; các phần **UserInfo HTTP, OIDC signature/issuer/nonce validation và login wiring** cần integration tests ở ranh giới riêng. Khi tách đúng các lớp này, bộ test vừa nhanh, ít phụ thuộc OP thực, vừa phát hiện được những lỗi cấp quyền hoặc trộn danh tính vốn dễ bị che khi chỉ kiểm tra HTTP status thành công.
