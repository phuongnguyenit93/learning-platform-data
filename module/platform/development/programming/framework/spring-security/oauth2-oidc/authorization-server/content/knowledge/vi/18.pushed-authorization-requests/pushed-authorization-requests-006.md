# Áp dụng chính sách bắt buộc PAR cho từng client

**Pushed Authorization Requests (PAR)** là cơ chế chuẩn hóa trong **RFC 9126**, cho phép OAuth 2.0/OpenID Connect (OIDC) client gửi các tham số authorization request trực tiếp đến Authorization Server qua một kết nối HTTP back-channel, rồi dùng một `request_uri` ngắn hạn để đưa trình duyệt người dùng tới Authorization Endpoint. Thay vì đặt tất cả `scope`, `redirect_uri`, `state`, `nonce`, `code_challenge` và những tham số mở rộng trên URL trình duyệt, client **đẩy** chúng lên máy chủ trước và nhận về một tham chiếu.

Trong nhiều tổ chức, không phải client nào cũng chuyển sang PAR cùng lúc. Ứng dụng xử lý thanh toán hoặc dữ liệu nhạy cảm có thể **bắt buộc PAR**, trong khi một web client nội bộ cũ được phép dùng authorization request thông thường trong giai đoạn chuyển đổi. Bài toán trực tiếp của bài học là: **cấu hình và thực thi chính sách bắt buộc PAR cho từng client, không chỉ bật `/oauth2/par` cho toàn bộ máy chủ**.

Bài thuộc chương **PAR** của mô-đun **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, trong lộ trình học thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng **Spring Security** và **Spring Authorization Server** trong ứng dụng Spring Boot.

> **Phân biệt quan trọng:** “Authorization Server **hỗ trợ** PAR” nghĩa là endpoint `/oauth2/par` có thể nhận yêu cầu. “Client X **bắt buộc** PAR” nghĩa là Authorization Endpoint phải **từ chối** mọi yêu cầu authorization trực tiếp của X nếu không có một `request_uri` hợp lệ **đã được tạo bởi PAR Endpoint và gắn với X**. Hai việc này không đồng nghĩa.

**Phạm vi phiên bản:** Các ví dụ cấu hình sử dụng **Spring Authorization Server 1.5.x** với Spring Security 6.5.x/Spring Boot 3.x. PAR được đưa vào Spring Authorization Server từ **1.5**. Trong Spring Security 7.x, Authorization Server đã được tích hợp vào Spring Security, nhưng tên API và khả năng bật chính sách cần được đối chiếu tài liệu của phiên bản thực tế. Các ví dụ dưới đây tránh giả định có một setter `requirePushedAuthorizationRequests(true)` trong `ClientSettings.Builder` của 1.5.x: **setter này không có trong API chính thức của phiên bản đó**.

## 1. Vì sao một số client phải dùng PAR?

Một URL authorization request truyền thống có dạng:

```text
GET https://login.example.com/oauth2/authorize
    ?response_type=code
    &client_id=payments-portal
    &redirect_uri=https%3A%2F%2Fpayments.example.com%2Flogin%2Foauth2%2Fcode%2Fcentral
    &scope=openid%20payments.read
    &state=RANDOM_STATE
    &code_challenge=CHALLENGE_VALUE
    &code_challenge_method=S256
    &nonce=RANDOM_NONCE
```

Dù HTTPS bảo vệ dữ liệu trên đường truyền, **phần query** vẫn đi qua trình duyệt và có thể xuất hiện trong lịch sử, công cụ quan sát, log reverse proxy hoặc các tích hợp không được cấu hình phù hợp. Nếu yêu cầu có tham số `authorization_details`, `claims` hoặc dữ liệu nhạy cảm về nghiệp vụ, URL có thể quá dài hoặc làm lộ thông tin không cần thiết.

PAR giúp:

1. **Giảm dữ liệu authorization request xuất hiện ở front-channel**: trình duyệt chủ yếu nhận `client_id` và `request_uri`.
2. **Xác minh sớm** client, callback, scope và một số điều kiện policy tại PAR Endpoint.
3. **Ràng buộc** một authorization request đã lưu với client đã đẩy request.
4. **Hạn chế sửa đổi tham số qua URL** vì máy chủ tra nội dung gốc từ tham chiếu đã lưu.
5. **Tạo chính sách bắt buộc theo mức rủi ro**: client nhạy cảm không thể quay lại luồng URL truyền thống để né quy tắc.

PAR không tự ngăn mọi hành vi phishing, XSS, CSRF, lạm dụng phiên, callback mở hoặc token bị đánh cắp. Trong Authorization Code Flow, vẫn cần **PKCE**, `state`, kiểm tra redirect URI, client authentication thích hợp, OIDC validation và kiểm tra access token tại Resource Server.

### 1.1. Bài toán nhiều client

Giả sử Central Login có ba ứng dụng:

| Client | Đặc tính | Chính sách PAR | Lý do |
|---|---|---|---|
| `payments-portal` | Confidential BFF, dữ liệu thanh toán nhạy cảm | **Bắt buộc** | Giảm front-channel parameters; không cho fallback |
| `reports-console` | Confidential app, thông tin nội bộ | **Bắt buộc** | Hợp đồng tích hợp yêu cầu PAR và PKCE |
| `legacy-staff-portal` | Confidential web app cũ | **Chưa bắt buộc** trong giai đoạn migration | Cần thời gian nâng cấp OAuth client |
| `mobile-public` | Public mobile client | Tùy threat model và khả năng hỗ trợ | Vẫn dùng `none` + PKCE; PAR không làm public client có secret |

Cả bốn client có thể gặp cùng một **PAR Endpoint**. Điều khác biệt là **hành vi tại Authorization Endpoint đối với từng client ID**, không phải tạo bốn URL PAR khác nhau.

## 2. PAR hoạt động qua hai HTTP request và bước đổi code

```mermaid
sequenceDiagram
    autonumber
    participant Client as payments-portal (BFF)
    participant PAR as POST /oauth2/par
    participant Browser as Trình duyệt
    participant Authorize as GET /oauth2/authorize
    actor User as Người dùng
    participant Token as POST /oauth2/token

    Client->>Client: Tạo state, nonce, PKCE verifier/challenge
    Client->>PAR: POST form tham số authorize + client authentication
    PAR->>PAR: Xác minh client, redirect URI, grant, scope, PKCE
    PAR-->>Client: 201 Created: request_uri + expires_in
    Client-->>Browser: 302 /oauth2/authorize?client_id=...&request_uri=...
    Browser->>Authorize: GET /oauth2/authorize với request_uri
    Authorize->>Authorize: Kiểm tra request_uri, client binding, expiry, policy
    Authorize->>User: Login và consent nếu cần
    Authorize-->>Browser: Redirect callback với code + state
    Browser-->>Client: Callback code + state
    Client->>Client: Xác minh state và lấy verifier của giao dịch
    Client->>Token: Đổi code + verifier + client authentication
    Token-->>Client: Access token / ID token theo policy
```

**Lưu ý:** PAR **không thay thế** Authorization Code Flow. Authorization Server vẫn phát authorization code, client vẫn đổi code ở `/oauth2/token`. PAR chỉ thay **cách vận chuyển và liên kết authorization request** trước bước người dùng xác thực/cấp quyền.

### 2.1. POST PAR chứa gì?

Ví dụ một confidential client:

```http
POST /oauth2/par HTTP/1.1
Host: login.example.com
Authorization: Basic <base64(payments-portal:client-secret)>
Content-Type: application/x-www-form-urlencoded

response_type=code&client_id=payments-portal&redirect_uri=https%3A%2F%2Fpayments.example.com%2Flogin%2Foauth2%2Fcode%2Fcentral&scope=openid%20payments.read&state=RANDOM_STATE&code_challenge=CHALLENGE&code_challenge_method=S256&nonce=RANDOM_NONCE
```

Ở PAR Endpoint, client xác thực theo cơ chế tương ứng với loại client và registration. Confidential client có thể dùng `client_secret_basic`, `private_key_jwt` hoặc phương thức được hỗ trợ; public client dùng `none` sẽ không có secret để chứng minh danh tính. Đối với public client, phải đánh giá các ràng buộc chống lạm dụng và PKCE riêng.

**Không gửi `request_uri` trong request POST tới PAR Endpoint.** RFC 9126 yêu cầu từ chối yêu cầu PAR chứa tham số `request_uri`, vì tham số này chỉ được server cấp sau khi request được chấp nhận.

### 2.2. Phản hồi PAR thành công

```http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store

{
  "request_uri": "urn:ietf:params:oauth:request_uri:OPAQUE_REFERENCE",
  "expires_in": 60
}
```

`request_uri` là **tham chiếu đến nội dung authorization request đã được server chấp nhận/lưu**, không phải authorization code, access token hoặc một URL tùy ý để browser fetch về. `expires_in` là số giây tham chiếu còn được chấp nhận; con số `60` chỉ minh họa, không phải giá trị mặc định mà mọi phiên bản Spring bảo đảm.

### 2.3. Trình duyệt chỉ mang tham chiếu

Sau khi nhận `request_uri`, client chuyển hướng trình duyệt:

```http
GET /oauth2/authorize?client_id=payments-portal&request_uri=urn%3Aietf%3Aparams%3Aoauth%3Arequest_uri%3AOPAQUE_REFERENCE HTTP/1.1
Host: login.example.com
```

Không ghép lại `scope` hoặc `redirect_uri` mới vào URL này để thay đổi request gốc. Server phải sử dụng **nội dung đã push** cùng các kiểm tra binding. Client vẫn giữ `state`, `nonce` và `code_verifier` trong trạng thái giao dịch riêng để xác minh callback/token response.

## 3. Điều kiện của request_uri theo RFC 9126

| Quy tắc | Ý nghĩa | Lỗi cần phòng tránh |
|---|---|---|
| Do PAR Endpoint phát | Không chấp nhận tham chiếu từ client tự tạo | “Có request_uri thì cho qua” |
| Không đoán được | Giá trị chứa phần ngẫu nhiên mật mã đủ mạnh | ID tuần tự hoặc giá trị dễ đoán |
| Gắn với client đã push | `client_id` ở authorize phải khớp client của PAR | Client A dùng request_uri của B |
| Có hạn dùng | Hết `expires_in` phải bị từ chối | Trình duyệt mở lại URL cũ nhiều giờ sau |
| Dùng một lần theo định hướng RFC | Client chỉ sử dụng `request_uri` một lần; server nên enforce one-time trừ trường hợp hỗ trợ reload hợp lệ | Replay / request swapping |
| Không nhận tham số chồng lấn trái policy | Authorization request không được âm thầm bị sửa bởi query mới | Nâng scope, đổi redirect, thay state |
| Xác minh authorization như thường lệ | PAR không miễn các kiểm tra grant, consent, PKCE, redirect | “Đã push nên chắc chắn hợp lệ mãi mãi” |

**RFC 9126:** Client **phải chỉ dùng một request URI một lần**. Authorization Server **nên** coi tham chiếu là một lần, nhưng có thể cho phép yêu cầu lặp vì browser reload. Vì vậy, kiểm thử cần phân biệt replay trái phép với hành vi reload mà phiên bản máy chủ hỗ trợ; không tuyên bố mọi request thứ hai luôn bị từ chối trong mọi cấu hình.

### 3.1. request_uri không phải URL để backend tùy tiện tải xuống

Với PAR, giá trị `request_uri` do Authorization Server phát và có thể là một **URN opaque**. Không đưa nó vào một HTTP client rồi đi fetch một URL do client tự cung cấp: cách này dễ dẫn đến SSRF nếu triển khai sai. Framework phải tra tham chiếu từ nguồn dữ liệu tin cậy, đối chiếu client binding, expiry và trạng thái.

### 3.2. TTL của request_uri không phải thời gian đăng nhập

Thời gian sống của `request_uri` xác định cửa sổ bắt đầu sử dụng tham chiếu ở Authorization Endpoint, **không đồng nhất** với thời hạn access token, authorization code, refresh token hay session đăng nhập. Khi login/consent có nhiều bước, cần kiểm thử hành vi TTL/khôi phục saved request của phiên bản cụ thể.

Client nên thực hiện POST `/oauth2/par` **gần thời điểm redirect tới `/oauth2/authorize`**, thay vì pre-push hàng loạt trước vài phút. Khi tham chiếu hết hạn, cần khởi tạo một PAR mới theo đúng contract; không nới TTL vô hạn để che lỗi kiến trúc.

## 4. Chính sách bắt buộc PAR: hỗ trợ và cưỡng chế khác nhau

RFC 9126 cho phép **Authorization Server áp dụng bắt buộc PAR toàn cục hoặc riêng từng client**. Nếu client phải dùng PAR, một authorization request trực tiếp thiếu `request_uri` được cấp bởi PAR Endpoint phải bị từ chối với lỗi `invalid_request`.

### 4.1. Bốn trường hợp tại Authorization Endpoint

| Client | Request tới `/oauth2/authorize` | Kết quả kỳ vọng |
|---|---|---|
| `payments-portal` bắt buộc PAR | Có `client_id` và **không có `request_uri`** | **Từ chối `invalid_request`** |
| `payments-portal` bắt buộc PAR | Có `request_uri` hợp lệ do chính client push | Tiếp tục login/consent theo policy |
| `legacy-staff-portal` chưa bắt buộc PAR | Authorization request truyền thống hợp lệ | Có thể tiếp tục |
| `legacy-staff-portal` chưa bắt buộc PAR | Dùng PAR hợp lệ | Vẫn có thể tiếp tục; “không bắt buộc” không có nghĩa “cấm PAR” |

Không dùng danh sách endpoint mở/đóng để thay cho policy per-client. Một endpoint `/oauth2/par` hoạt động nhưng client high-risk vẫn có thể gửi authorize request trực tiếp nếu máy chủ không **thực thi** quy tắc từ chối.

### 4.2. Chỗ thực thi đúng

- **PAR Endpoint** xác thực client nếu áp dụng, nhận và xác minh pushed request, lưu dữ liệu tham chiếu.
- **Authorization Endpoint** phải áp **điều kiện bắt buộc PAR theo client**, trước khi phát authorization code hoặc chuyển sang bước consent/login không cần thiết.
- **OAuth2AuthorizationService** hoặc kho trạng thái của framework chịu trách nhiệm thông tin request/code và các ràng buộc liên quan.
- **Token Endpoint** vẫn kiểm tra authorization code, PKCE, client authentication và redirect binding.

Chỉ thêm một cờ vào database hoặc UI quản lý client **không tự cưỡng chế** request ở Authorization Endpoint.

## 5. Giới hạn của API Spring Authorization Server 1.5.x

Spring Authorization Server 1.5.x có:

- `OAuth2AuthorizationServerConfigurer.pushedAuthorizationRequestEndpoint(...)` để tùy chỉnh PAR Endpoint;
- `AuthorizationServerSettings.Builder.pushedAuthorizationRequestEndpoint("/oauth2/par")` để đặt đường dẫn;
- `OAuth2PushedAuthorizationRequestEndpointFilter` và `OAuth2PushedAuthorizationRequestAuthenticationProvider`;
- `OAuth2AuthorizationEndpointConfigurer` để tùy chỉnh authorization request/consent và các provider;
- `RegisteredClient`, `ClientSettings` và `RegisteredClientRepository` cho metadata client.

**Tuy nhiên:** `ClientSettings.Builder` của 1.5.x **không công bố** method `requirePushedAuthorizationRequests(boolean)`; `ClientSettings` cũng không có getter `isRequirePushedAuthorizationRequests()` trong API chính thức. Vì vậy đoạn sau **không phải mã hợp lệ** cho phiên bản đó:

```java
// KHÔNG TỒN TẠI trong ClientSettings.Builder của SAS 1.5.x:
ClientSettings.builder()
    .requirePushedAuthorizationRequests(true)
    .build();
```

Có hai hướng triển khai chính sách ứng dụng:

1. **Repository policy riêng:** Ví dụ `ParPolicyRepository` ánh xạ `RegisteredClient.id` với `requirePar`, được quản trị cùng client registration.
2. **Setting mở rộng có chủ sở hữu rõ ràng:** Dùng `ClientSettings.Builder.setting("app.security.require_par", Boolean.TRUE)` và đọc lại bằng `getSetting(...)`; ứng dụng tự bảo đảm persistence, migration và xử lý enforcement.

Ví dụ tiếp theo sử dụng **setting mở rộng**, vì nó giúp giải thích tính **per-client** ngay tại nơi xây `RegisteredClient`. Tên `app.security.require_par` là **quy ước riêng trong bài**, **không phải** key chuẩn mà Spring tự động hiểu hoặc metadata RFC tự động công bố.

### 5.1. Không nhầm metadata RFC với API builder

RFC 9126 định nghĩa tên metadata:

- `pushed_authorization_request_endpoint`: khả năng/địa chỉ PAR của Authorization Server.
- `require_pushed_authorization_requests` tại **Authorization Server metadata**: thông báo máy chủ yêu cầu PAR cho **mọi** authorization request theo policy toàn cục.
- `require_pushed_authorization_requests` tại **client metadata**: thông báo **client đó** chỉ được khởi tạo authorization qua PAR.

Trong deployment **trộn client bắt buộc và client chưa bắt buộc**, không công bố một boolean toàn cục `require_pushed_authorization_requests=true` vì điều đó gây hiểu nhầm rằng **tất cả** client đều bắt buộc. Cần có kênh truyền thông/tài liệu onboarding hoặc dynamic client metadata được thiết kế riêng cho chính sách từng client.

Nếu triển khai Dynamic Client Registration, hãy kiểm tra phiên bản framework có thực sự hỗ trợ lưu và công bố field metadata này hay chưa. Không tự cho rằng việc gọi `.setting("app.security.require_par", true)` tạo ra dữ liệu `require_pushed_authorization_requests` trong discovery hoặc client registration response.

## 6. Đăng ký hai RegisteredClient có chính sách khác nhau

Ví dụ dưới đây dùng **Spring Authorization Server 1.5.x** và `ClientSettings` mở rộng. Hai client đều dùng Authorization Code, PKCE, client authentication; chỉ một client được đánh dấu **bắt buộc PAR**.

```java
package example.authserver.config;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

@Configuration(proxyBeanMethods = false)
public class ClientRegistryConfig {

    public static final String REQUIRE_PAR =
            "app.security.require_par"; // Setting do ứng dụng định nghĩa.

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    RegisteredClientRepository registeredClientRepository(
            PasswordEncoder encoder, Environment env) {

        RegisteredClient payments = RegisteredClient
            .withId("payments-portal-registration")
            .clientId("payments-portal")
            .clientSecret(encoder.encode(
                env.getRequiredProperty("PAYMENTS_CLIENT_SECRET")))
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                "https://payments.example.com/login/oauth2/code/central")
            .scope(OidcScopes.OPENID)
            .scope("payments.read")
            .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .setting(REQUIRE_PAR, true)
                .build())
            .build();

        RegisteredClient legacy = RegisteredClient
            .withId("legacy-staff-registration")
            .clientId("legacy-staff-portal")
            .clientSecret(encoder.encode(
                env.getRequiredProperty("LEGACY_CLIENT_SECRET")))
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                "https://staff.example.com/login/oauth2/code/central")
            .scope(OidcScopes.OPENID)
            .scope("profile")
            .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(false)
                .setting(REQUIRE_PAR, false)
                .build())
            .build();

        return new InMemoryRegisteredClientRepository(List.of(payments, legacy));
    }
}
```

### 6.1. Ý nghĩa từng lớp cấu hình

| Thành phần | Chức năng | Điều gì **không** tự xảy ra? |
|---|---|---|
| `clientId` | Nhận diện client giao thức | Không phải credential |
| `clientSecret` / `client_secret_basic` | Xác thực confidential client tại PAR/token endpoint | Không thay `request_uri`, PKCE, consent |
| `authorization_code` | Cho phép flow có người dùng | Không bắt buộc PAR |
| `requireProofKey(true)` | Yêu cầu Authorization Code + PKCE | Không tự bắt buộc PAR |
| `requireAuthorizationConsent(...)` | Chính sách người dùng chấp thuận scope | Không quyết định PAR |
| `setting(REQUIRE_PAR,true)` | **Lưu policy riêng** cho client | **Không tự thực thi** nếu thiếu validation/guard |
| `redirectUri` | Callback allowlist | Không được nới wildcard chỉ vì dùng PAR |

**Production:** Không nên phụ thuộc vào `InMemoryRegisteredClientRepository` để lưu chính sách thật. Với JDBC/repository tùy chỉnh, phải bảo đảm setting mở rộng được serialize/deserialize đúng, giữ `RegisteredClient.id` ổn định và đồng bộ giữa nhiều node. Không thay đổi `client_id`/ID nội bộ một cách tùy tiện vì authorization/consent có thể tham chiếu tới registration.

## 7. Cưỡng chế bắt buộc PAR tại Authorization Endpoint

Mấu chốt không phải chỉ sửa PAR Endpoint. Client có thể bỏ qua `/oauth2/par` và gửi thẳng:

```http
GET /oauth2/authorize?response_type=code&client_id=payments-portal&redirect_uri=https%3A%2F%2Fpayments.example.com%2Flogin%2Foauth2%2Fcode%2Fcentral&scope=openid%20payments.read&state=SAMPLE_STATE&code_challenge=CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: login.example.com
```

Nếu policy của `payments-portal` là bắt buộc PAR, Authorization Server phải từ chối **trước khi cấp code**, dù `response_type`, `redirect_uri`, `scope` và PKCE đều hợp lệ.

### 7.1. Hai tầng kiểm tra cần giữ

**Tầng 1 — Kiểm tra per-client:** Client được đặt `REQUIRE_PAR=true` thì yêu cầu HTTP đi vào `/oauth2/authorize` phải mang **một** `request_uri` không rỗng. Yêu cầu trực tiếp thiếu tham chiếu bị từ chối `invalid_request`.

**Tầng 2 — Kiểm tra giao thức chuẩn:** `request_uri` có thực sự do PAR Endpoint tạo, còn hạn, gắn với đúng client, không dùng lại trái policy và dẫn tới request đã được xác minh không? **Spring Authorization Server** phải tiếp tục kiểm tra các điều kiện này. Tầng 1 chỉ nhìn **sự hiện diện** tham số, **không đủ** để chứng minh PAR hợp lệ.

Không tạo một bộ lọc tự nhận `request_uri=anything` là hợp lệ và tự phát code. Sau guard, request phải đi vào **Authorization Endpoint gốc của Spring**.

### 7.2. Ví dụ filter cho per-client policy

Để kiểm tra tham số **trên HTTP request gốc** trước khi Authorization Endpoint giải tham chiếu `request_uri`, có thể đặt một `OncePerRequestFilter` sớm **trong protocol SecurityFilterChain**. Đoạn mã dưới đây thực hiện **tầng 1**; mọi validation tầng 2 vẫn thuộc Spring.

```java
package example.authserver.security;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.oauth2.core.endpoint.OAuth2ParameterNames;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

public final class RequireParForClientFilter extends OncePerRequestFilter {

    // Cùng key đã dùng khi tạo RegisteredClient.
    private static final String REQUIRE_PAR = "app.security.require_par";

    private final RegisteredClientRepository clients;
    private final String authorizationPath;

    public RequireParForClientFilter(
            RegisteredClientRepository clients,
            AuthorizationServerSettings serverSettings) {
        this.clients = clients;
        this.authorizationPath = serverSettings.getAuthorizationEndpoint();
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        // Lọc đúng Authorization Endpoint; không ảnh hưởng /oauth2/par,
        // /oauth2/token, /login, /oauth2/jwks, metadata...
        return !authorizationPath.equals(request.getServletPath());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String[] ids = request.getParameterValues(OAuth2ParameterNames.CLIENT_ID);

        if (ids != null && ids.length != 1) {
            rejectInvalidRequest(response);
            return;
        }

        if (ids == null || !StringUtils.hasText(ids[0])) {
            // Để framework gốc trả lỗi thiếu/không hợp lệ client_id.
            chain.doFilter(request, response);
            return;
        }

        RegisteredClient client = clients.findByClientId(ids[0]);

        if (client == null) {
            // KHÔNG redirect tới callback tự khai báo khi client lạ.
            // Framework gốc phải xử lý client không tồn tại.
            chain.doFilter(request, response);
            return;
        }

        boolean parRequired = Boolean.TRUE.equals(
            client.getClientSettings().getSetting(REQUIRE_PAR));

        if (parRequired) {
            String[] uris = request.getParameterValues(
                OAuth2ParameterNames.REQUEST_URI);

            if (uris == null || uris.length != 1
                    || !StringUtils.hasText(uris[0])) {
                rejectInvalidRequest(response);
                return;
            }
        }

        // Sự hiện diện request_uri chưa đủ tin cậy.
        // Để Spring kiểm tra client binding, expiry, nội dung đã push...
        chain.doFilter(request, response);
    }

    private static void rejectInvalidRequest(
            HttpServletResponse response) throws IOException {
        response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
        response.setContentType("application/json;charset=UTF-8");
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Pragma", "no-cache");
        response.getWriter().write("{\"error\":\"invalid_request\"}");
    }
}
```

**Phạm vi/giới hạn của ví dụ:**

- Đây là **một guard ứng dụng**, không phải filter có sẵn của Spring Authorization Server.
- Nếu `client_id` chưa xác định, filter để **framework** xử lý, không tự suy đoán client từ một `request_uri` chưa xác minh.
- Nếu client bắt buộc PAR nhưng chỉ gửi `request_uri=garbage`, guard cho qua **tầng 1**; framework phải từ chối ở **tầng 2**.
- HTTP `400` với `invalid_request` trả **tại chính máy chủ**, tránh redirect về `redirect_uri` chưa kiểm tra. Nếu thay bằng một OAuth authorization error handler tích hợp, phải bảo toàn ranh giới **không redirect tới URI không đáng tin**.
- `getServletPath()` phù hợp ví dụ servlet với Authorization Endpoint ở một đường dẫn nội bộ. Nếu dùng context path, nhiều issuer, rewrite qua proxy hoặc routing tùy chỉnh, cần kiểm thử và điều chỉnh matcher dựa trên cấu hình thực.
- Nếu production có logic PAR toàn cục/tenant hoặc policy thay đổi thời gian thực, guard phải dùng **cùng nguồn chính sách** với quản trị client. Không lưu một bản allowlist riêng bị lệch trong từng node.

### 7.3. Gắn filter trước endpoint xử lý giao thức

Ví dụ sử dụng API Spring Security 6.x, đặt guard **sớm trước `SecurityContextHolderFilter`** (một filter chuẩn có thứ tự đã biết). Guard chỉ đọc request params và tra registered clients nên **không cần principal từ SecurityContext**.

```java
package example.authserver.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.SecurityContextHolderFilter;

import example.authserver.security.RequireParForClientFilter;

@Configuration(proxyBeanMethods = false)
public class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http,
            RegisteredClientRepository clients,
            AuthorizationServerSettings settings) throws Exception {

        OAuth2AuthorizationServerConfigurer as =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(as.getEndpointsMatcher())
            .with(as, server -> server
                .pushedAuthorizationRequestEndpoint(
                    Customizer.withDefaults()))
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated());

        // Không đánh dấu RequireParForClientFilter là @Component:
        // nó chỉ được đăng ký trong protocol chain ở đây.
        http.addFilterBefore(
            new RequireParForClientFilter(clients, settings),
            SecurityContextHolderFilter.class);

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(
            HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

**Đoạn cấu hình chưa phải một Authorization Server chạy độc lập:** còn cần nguồn ký token/JWK, `OAuth2AuthorizationService`, `OAuth2AuthorizationConsentService`, issuer, user store/password encoder và những bean khác phù hợp với môi trường. Nếu bật OIDC, cần cấu hình OIDC tương ứng. Chúng không được bỏ qua chỉ vì có PAR.

**Lưu ý về filter order:** Spring Security cấu hình filter theo các thứ tự nội bộ; việc đặt guard trước `SecurityContextHolderFilter` đảm bảo nó không phụ thuộc phiên đăng nhập, nhưng đòi hỏi **kiểm thử HTTP thật** để chứng minh guard chạy **trước** `OAuth2AuthorizationEndpointFilter` trên phiên bản đang dùng. Tránh tự đăng ký thêm chính filter này qua servlet container vì có thể khiến filter chạy ngoài protocol chain hoặc hai lần.

### 7.4. Tại sao không chỉ thêm một AuthenticationProvider?

Nếu viết một provider tự kiểm tra PAR rồi gọi `authorizationEndpoint.authenticationProvider(provider)`, thao tác đó thường **thêm** provider vào danh sách. Provider gốc có thể đã xử lý request trước provider mới, khiến policy bị **bypass**. Khi thay đổi provider hoặc converter, phải hiểu và kiểm thử thứ tự; nếu cần **thay** provider gốc, dùng `authorizationEndpoint.authenticationProviders(...)` và bảo toàn validation mặc định.

Trong 1.5.x, `OAuth2AuthorizationCodeRequestAuthenticationProvider` có `setAuthenticationValidator(...)`, nhưng dữ liệu `request_uri` có thể đã trải qua bước giải tham chiếu/conversion. Muốn kiểm tra **tham số của HTTP request ban đầu** một cách chắc chắn, ví dụ chọn guard trước Authorization Endpoint. Nếu triển khai bằng provider validator, phải chứng minh một dấu hiệu **đáng tin** rằng request gốc thật sự đến qua PAR, không chỉ nhìn các tham số đã được resolve.

**Không thay validation redirect URI/scope mặc định** bằng một validator tùy biến chỉ kiểm tra PAR rồi bỏ các kiểm tra khác.

## 8. Bật đường dẫn PAR trong AuthorizationServerSettings

Với Spring Authorization Server 1.5.x, đường dẫn mặc định cho PAR là `/oauth2/par`. Có thể khai báo tường minh:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://login.example.com")
        .authorizationEndpoint("/oauth2/authorize")
        .pushedAuthorizationRequestEndpoint("/oauth2/par")
        .tokenEndpoint("/oauth2/token")
        .build();
}
```

`AuthorizationServerSettings` **xác định URI endpoint**, **không lưu policy client nào bắt buộc PAR**. Nếu đổi thành `/oauth2/v1/par`, cả client PAR-aware, discovery metadata, filter/matcher và reverse proxy phải thống nhất. Guard ở mục 7 nhận `settings.getAuthorizationEndpoint()` để tránh hard-code endpoint.

### 8.1. Vì sao không nên chặn toàn bộ `/oauth2/authorize` ở firewall?

Cả PAR và authorization trực tiếp đều đi qua `/oauth2/authorize`. Nếu chặn hết, ngay cả client dùng PAR cũng không thể cho người dùng đăng nhập. Cần phân biệt **request có request_uri đã được cấp hợp lệ** với request muốn truyền dữ liệu trực tiếp.

Tương tự, chỉ cho phép `/oauth2/par` mà chặn `/oauth2/authorize` hoặc chuyển mọi request đến `/login` sẽ không làm PAR hoàn thành.

### 8.2. HTTPS, issuer và proxy

- `issuer` phải là URL HTTPS công khai mà client, browser và Resource Server tin cậy.
- PAR Endpoint là back-channel nên cần hỗ trợ xác thực client, TLS và giới hạn request body.
- Chỉ tin forwarded headers do reverse proxy đáng tin chuyển vào.
- Tránh trùng hostname nội bộ/pod trong metadata hoặc redirect URI.
- Nếu có nhiều issuer/tenant, chính sách phải được đánh giá theo **đúng issuer và RegisteredClient của tenant**, không lookup client từ một namespace chung không an toàn.

## 9. Thay đổi bắt buộc ở phía OAuth2 Client

**Máy chủ bật bắt buộc PAR nhưng client vẫn tạo redirect trực tiếp** thì đăng nhập sẽ thất bại. Client phải hỗ trợ chuỗi:

1. Tạo authorization request đầy đủ (`state`, PKCE challenge, `nonce`, `scope`, `redirect_uri`).
2. POST tham số qua `/oauth2/par` bằng **client authentication** đúng registration.
3. Đọc response `201 Created`, lưu `request_uri`/`expires_in` với giao dịch.
4. Redirect browser đến `/oauth2/authorize?client_id=...&request_uri=...`.
5. Nhận callback, so khớp `state`, rồi đổi authorization code bằng verifier gốc và client auth nếu cần.
6. Dọn trạng thái giao dịch sau thành công hoặc lỗi.

Spring Security OAuth2 Client có `OAuth2AuthorizationRequestResolver` và `OAuth2AuthorizationRequestRedirectFilter` để khởi tạo Authorization Code Flow. **Đừng mặc định** việc chỉ thêm `pushed-authorization-request-endpoint` vào một file cấu hình `ClientRegistration` sẽ khiến resolver gốc tự thực hiện POST PAR. Cần **PAR-aware client implementation/thư viện** hoặc logic tùy chỉnh được kiểm thử, có quản lý `state`, `code_verifier` và callback.

### 9.1. Cấu hình client truyền thống không tự nâng cấp thành PAR

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          central:
            provider: central
            client-id: payments-portal
            client-secret: "REPLACE_FROM_SECRET_MANAGER"
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, payments.read
        provider:
          central:
            issuer-uri: https://login.example.com
```

Đây là cấu hình **OAuth2 Client registration cơ bản**, **không phải ví dụ client đã hỗ trợ PAR**. Giá trị secret chỉ là placeholder, không commit secret thật. Để qua được guard ở `payments-portal`, ứng dụng phải thực hiện POST PAR trước khi redirect; nếu chưa có khả năng này, **không bật cờ bắt buộc PAR trong production trước khi nâng cấp client**.

### 9.2. Giữ nguyên state và PKCE qua hai bước

Trong Authorization Code + PKCE, `code_verifier` do client giữ, `code_challenge` được đưa vào **pushed request**, và verifier gốc được dùng khi đổi code. Tạo lại verifier sau response PAR sẽ dẫn tới `invalid_grant` ở Token Endpoint.

`state` dùng để liên kết callback với authorization transaction; không tạo state mới khi chuyển từ PAR response sang browser redirect. Tương tự, nếu request OIDC có `nonce`, cần giữ liên kết với ID token validation.

### 9.3. Không đưa tham số nhạy cảm trở lại URL

Nếu sau khi push client vẫn redirect:

```text
/oauth2/authorize?client_id=payments-portal&request_uri=...&
    scope=payments.write&redirect_uri=https://attacker.example/cb
```

thì **thiết kế sai mục đích PAR**. Authorization Endpoint phải sử dụng đúng pushed request và từ chối các giá trị gây xung đột theo profile; không cho query mới nâng quyền hoặc đổi callback. Trong bài toán triển khai, hãy chủ động viết test đối kháng cho tình huống này.

## 10. HTTP/curl: minh họa happy path và đường bị từ chối

### 10.1. Bước 1 — Client push authorization request

Ví dụ BFF confidential client ở môi trường thử nghiệm:

```bash
curl --request POST "https://login.example.com/oauth2/par" \
  --user "$PAYMENTS_CLIENT_ID:$PAYMENTS_CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "response_type=code" \
  --data-urlencode "client_id=payments-portal" \
  --data-urlencode "redirect_uri=https://payments.example.com/login/oauth2/code/central" \
  --data-urlencode "scope=openid payments.read" \
  --data-urlencode "state=$OAUTH_STATE" \
  --data-urlencode "code_challenge=$PKCE_CHALLENGE" \
  --data-urlencode "code_challenge_method=S256" \
  --data-urlencode "nonce=$OIDC_NONCE"
```

Những biến `OAUTH_STATE`, `PKCE_CHALLENGE` và `OIDC_NONCE` cần được tạo an toàn cho từng giao dịch. Ví dụ không tự sinh chúng. Nếu request hợp lệ, nhận JSON `request_uri` và `expires_in`; **không chuyển cả response JSON đến browser** mà chỉ tạo redirect từ giá trị tham chiếu.

Lưu ý `curl --user` có thể xuất hiện trong thông tin dòng lệnh/tiến trình theo môi trường; không sử dụng secret thật trong tài liệu hoặc log CI công khai.

### 10.2. Bước 2 — Chuyển trình duyệt đến Authorization Endpoint

```bash
curl --get --include "https://login.example.com/oauth2/authorize" \
  --data-urlencode "client_id=payments-portal" \
  --data-urlencode "request_uri=$REQUEST_URI"
```

Lệnh mô phỏng HTTP GET, không tự hoàn thành login/consent. Nếu chưa có browser session, server có thể redirect đến trang login; đây là hành vi dự kiến. Trong ứng dụng thật, đây là **browser redirect**, không phải backend tự gọi `curl` rồi thay người dùng hoàn tất login.

### 10.3. Negative test — Bỏ qua PAR bằng authorization URL thông thường

```bash
curl --get --include "https://login.example.com/oauth2/authorize" \
  --data-urlencode "response_type=code" \
  --data-urlencode "client_id=payments-portal" \
  --data-urlencode "redirect_uri=https://payments.example.com/login/oauth2/code/central" \
  --data-urlencode "scope=openid payments.read" \
  --data-urlencode "state=$OAUTH_STATE" \
  --data-urlencode "code_challenge=$PKCE_CHALLENGE" \
  --data-urlencode "code_challenge_method=S256"
```

**Kết quả kỳ vọng đối với filter ví dụ:** HTTP `400` với `{"error":"invalid_request"}`, **không có redirect chứa authorization code**. Nếu request vẫn chuyển đến login hoặc cấp code, cần kiểm tra guard có chạy đúng protocol chain và trước endpoint hay không.

### 10.4. Negative test — Tham chiếu giả

```bash
curl --get --include "https://login.example.com/oauth2/authorize" \
  --data-urlencode "client_id=payments-portal" \
  --data-urlencode "request_uri=urn:ietf:params:oauth:request_uri:FAKE"
```

Filter ví dụ chỉ xác nhận **có** tham số; **Spring Authorization Server** phải từ chối vì tham chiếu **không hợp lệ**. Nếu request giả vẫn tới được bước cấp code, đó là lỗi nghiêm trọng ở tầng xử lý PAR request URI.

### 10.5. Legacy client vẫn được phép authorize trực tiếp

```bash
curl --get --include "https://login.example.com/oauth2/authorize" \
  --data-urlencode "response_type=code" \
  --data-urlencode "client_id=legacy-staff-portal" \
  --data-urlencode "redirect_uri=https://staff.example.com/login/oauth2/code/central" \
  --data-urlencode "scope=openid profile" \
  --data-urlencode "state=$OAUTH_STATE" \
  --data-urlencode "code_challenge=$PKCE_CHALLENGE" \
  --data-urlencode "code_challenge_method=S256"
```

Nếu các tham số khác hợp lệ, legacy client có thể tiếp tục luồng xác thực. **Không bắt buộc PAR** không đồng nghĩa “bỏ qua redirect URI/PKCE/state” hoặc “được mọi quyền”; tất cả validation giao thức vẫn giữ nguyên.

## 11. Metadata, tính tương thích và thông báo cho client

### 11.1. Discovery metadata

Một Authorization Server hỗ trợ PAR có thể công bố:

```json
{
  "issuer": "https://login.example.com",
  "authorization_endpoint": "https://login.example.com/oauth2/authorize",
  "pushed_authorization_request_endpoint": "https://login.example.com/oauth2/par",
  "token_endpoint": "https://login.example.com/oauth2/token"
}
```

Ví dụ không phải metadata đầy đủ. Khi áp **một chính sách global bắt buộc PAR cho mọi client**, metadata chuẩn cho phép:

```json
{
  "require_pushed_authorization_requests": true
}
```

**Nhưng với deployment mixed** (chỉ `payments-portal` và `reports-console` bắt buộc), không tự công bố boolean toàn cục `true`. Chính sách per-client có thể được truyền qua client registration metadata, tài liệu onboarding hoặc API quản trị tin cậy tùy triển khai.

### 11.2. Đừng nhầm PAR với JAR và FAPI

| Công nghệ | Cơ chế | Quan hệ |
|---|---|---|
| **PAR (RFC 9126)** | Client gửi authorization parameters qua back-channel, nhận `request_uri` | Trọng tâm bài học |
| **JAR (RFC 9101)** | Authorization Request được đóng gói bằng Request Object JWT ký/mã hóa nếu áp dụng | Có thể kết hợp PAR; không tự bật chỉ bởi PAR |
| **PKCE (RFC 7636)** | Ràng buộc authorization code với verifier của client | Vẫn phải dùng trong Authorization Code theo policy |
| **FAPI Security Profiles** | Yêu cầu bảo mật cao cho API tài chính và tương tự | Có thể yêu cầu PAR, JAR và biện pháp khác tùy profile cụ thể |

PAR **không tạo chữ ký không thể chối bỏ** cho toàn bộ authorization request chỉ nhờ dùng HTTPS và client authentication. Nếu đối tác yêu cầu Request Object JWT ký, phải triển khai và kiểm thử JAR riêng thay vì cho rằng `/oauth2/par` đã đáp ứng.

## 12. Thiết kế rollout chính sách theo từng client

Chuyển tất cả client từ authorization trực tiếp sang bắt buộc PAR trong một lần có thể gây gián đoạn đăng nhập. Một rollout an toàn nên có **vòng đời cấu hình per-client** rõ ràng.

### 12.1. Bốn trạng thái vận hành đề xuất

| Trạng thái | PAR request | Authorization trực tiếp | Dùng khi |
|---|---|---|---|
| **Legacy** | Cho phép nếu client hỗ trợ | Cho phép | Ứng dụng chưa nâng cấp |
| **Ready/Observe** | Cho phép | Cho phép và ghi số liệu | Đang test client đã hỗ trợ PAR |
| **Required** | Cho phép | **Từ chối `invalid_request`** | Đã xác nhận client hoạt động hoàn chỉnh với PAR |
| **Disabled/Revoked** | Từ chối theo policy | Từ chối | Client bị thu hồi/quá hạn hợp đồng |

Ví dụ `ClientSettings.setting(..., Boolean)` chỉ biểu diễn **hai trạng thái Required vs Not required**, không có sẵn enum hay vòng đời bốn trạng thái. Nếu sản phẩm cần đủ bốn trạng thái, thiết kế `ParPolicyRepository` riêng hoặc nâng cấp metadata quản trị; đừng dùng boolean để ngầm đại diện cho mọi trạng thái.

### 12.2. Các bước chuyển đổi cho một client

1. **Inventory:** Xác định owner, client ID, loại client, grant, redirect URI, nơi build authorization request và thư viện OAuth2 Client.
2. **Đánh giá:** Client có thể POST PAR trước redirect không? Quản lý `state`/PKCE/nonce xuyên suốt được không?
3. **Cấu hình:** Hoàn thiện PAR Endpoint, registered client, auth method và yêu cầu PKCE.
4. **Test staging:** Happy path, direct bypass, expired `request_uri`, wrong-client URI, bad scope/redirect, login/consent và concurrent sessions.
5. **Observe:** Bật client hỗ trợ PAR nhưng vẫn chấp nhận direct request, đo tỷ lệ PAR và lỗi.
6. **Require:** Bật `REQUIRE_PAR=true` đúng client, rollout nhất quán qua các node.
7. **Monitor:** Theo dõi `invalid_request`, `invalid_client`, `invalid_scope`, tỷ lệ login lỗi và thời gian từ POST PAR đến GET authorize.
8. **Rollback có kiểm soát:** Nếu cần, thay policy của client theo quy trình thay đổi bảo mật; không tắt kiểm tra redirect URI/PKCE hay mở mặc định cho mọi client.

### 12.3. Nguồn cấu hình phải thống nhất

Nếu node A xem `payments-portal` là Required còn node B xem là Legacy, load balancer có thể khiến một phiên login lúc thành công lúc thất bại. Cần bảo đảm `RegisteredClientRepository`, `app.security.require_par`, `OAuth2AuthorizationService` và issuer/settings thống nhất giữa các node. Khi thay đổi, có version/updatedAt để audit và xác định node đã tải cấu hình mới.

## 13. Kiểm thử: bắt buộc PAR phải chứng minh không bypass được

### 13.1. Ma trận integration test

| Test case | Client / Request | Kỳ vọng |
|---|---|---|
| Happy path bắt buộc PAR | `payments-portal` push thành công, authorize bằng URI, login/consent, token exchange | Cấp token theo policy |
| Direct request bị cấm | `payments-portal` gửi authorize đủ scope/PKCE nhưng **không request_uri** | `invalid_request`, không cấp code |
| Blank request_uri | `request_uri=` | Từ chối |
| Duplicate request_uri | Hai giá trị khác nhau | Từ chối |
| Fake request_uri | URI tự tạo không có trong kho PAR | Từ chối |
| Expired request_uri | Dùng sau `expires_in` | Từ chối |
| Wrong-client URI | URI tạo bởi client A, GET authorize với `client_id` của B | Từ chối; không cấp code |
| Replay/reload | Dùng URI lại sau khi đã được tiêu thụ | Theo policy one-time của implementation; không cấp lại trái quy định |
| Query override | URI hợp lệ nhưng thêm scope cao hơn/redirect sai vào browser URL | Không được nâng scope hoặc đổi callback |
| Redirect sai lúc push | `/oauth2/par` nhận callback ngoài registration | Từ chối ở PAR Endpoint |
| Scope sai lúc push | Xin scope chưa đăng ký | Từ chối |
| PAR client secret sai | Basic secret không đúng | `invalid_client`; không cấp URI |
| Missing state | Client không tạo/đối chiếu state | Test phía OAuth2 Client phải ngăn callback sai |
| PKCE missing | Client `requireProofKey(true)` nhưng thiếu challenge/verifier | Không hoàn tất cấp token |
| Consent | Client cần consent; scope được push | Trang consent hiển thị quyền đúng, xử lý chấp thuận/từ chối |
| Legacy direct | `legacy-staff-portal` dùng authorize trực tiếp đúng chuẩn | Tiếp tục đăng nhập |
| Legacy PAR | `legacy-staff-portal` dùng PAR | Có thể tiếp tục khi endpoint hỗ trợ |
| Chỉ thay setting | Bật `REQUIRE_PAR=true` nhưng không cấu hình guard | Test phải **phát hiện bypass**, không cho pass |
| Đổi endpoint path | `/oauth2/par` chuyển sang `/oauth2/v1/par` | Client/discovery/routing nhất quán |
| Multi-node | POST PAR node A, GET authorize node B | Truy vấn được request URI và chính sách đúng |
| Không lộ dữ liệu | Thử log/referer/analytics | Không lộ pushed form, client secret, code, verifier |
| Revocation/expiry | Client bị disabled hoặc URI quá hạn | Không cấp code/token |

**Đặc biệt quan trọng:** Test thiếu `request_uri` chỉ chứng minh **tầng 1**, trong khi test URI giả/hết hạn/sai client chứng minh **tầng 2**. Phải kiểm tra cả hai. Một test nhìn thấy HTTP `201` từ `/oauth2/par` chưa chứng minh bắt buộc PAR đã được áp ở Authorization Endpoint.

### 13.2. Test mức filter bằng MockMvc

Đoạn sau minh họa ý định test (fixture/authentication cấu hình tùy dự án):

```java
// Test intent: payments-portal bắt buộc PAR nhưng truy cập trực tiếp.
mvc.perform(get("/oauth2/authorize")
        .param("response_type", "code")
        .param("client_id", "payments-portal")
        .param("redirect_uri",
                "https://payments.example.com/login/oauth2/code/central")
        .param("scope", "openid payments.read")
        .param("state", "test-state")
        .param("code_challenge", "test-challenge")
        .param("code_challenge_method", "S256"))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.error").value("invalid_request"));
```

**Đoạn trên không phải test tích hợp hoàn chỉnh**: fixture `mvc` phải khởi chạy đúng Spring context, protocol SecurityFilterChain, `RegisteredClientRepository` và filter guard. Một PKCE challenge thực trong happy path phải có định dạng hợp lệ; ở case bị từ chối sớm vì thiếu PAR, giá trị minh họa chỉ giúp xác nhận guard chạy trước các bước còn lại.

### 13.3. Test client với HTTP thật

Một kiểm thử end-to-end nên giữ browser session/cookie và chạy:

1. Client tạo state/verifier/nonce đúng; POST PAR.
2. Xác nhận response `201`, `request_uri` và `expires_in`.
3. Browser mở authorize bằng đúng URI; nếu chưa login thì đăng nhập.
4. Consent nếu cần, callback có code/state hợp lệ.
5. Client kiểm tra state, đổi code với verifier gốc.
6. Resource Server nhận access token, kiểm tra `aud`, scope, tenant và quyền thao tác.

Để test **hai tab đồng thời**, tạo hai pushed requests với state/verifier khác nhau. Không lưu một `currentRequestUri` hoặc `currentVerifier` toàn cục bị ghi đè.

### 13.4. Không bỏ qua test phiên bản

Ở mỗi lần cập nhật Spring Security/Spring Authorization Server, kiểm tra:

- Filter guard có chạy trước Authorization Endpoint không;
- `AuthorizationServerSettings` có trả đúng URI không;
- PAR Endpoint còn hỗ trợ converter/provider như trước không;
- Dữ liệu `request_uri` còn truy vấn được sau redirect/login/consent không;
- Schema JDBC/persistence có lưu custom client setting và authorization state đúng không;
- Client SDK còn tạo PAR và lưu state/PKCE đúng không.

## 14. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `POST /oauth2/par` trả 404 | Spring Authorization Server quá cũ, configurer chưa áp dụng hoặc path khác | Kiểm tra phiên bản ≥ 1.5, endpoint settings và route |
| `/oauth2/par` trả `invalid_client` | Secret/method sai hoặc client không tồn tại | So khớp registration và client authentication |
| `/oauth2/par` trả `invalid_scope` | Scope không nằm trong allowlist | Sửa yêu cầu quyền, không nới mọi client |
| `/oauth2/par` trả lỗi redirect | Callback không khớp registration | Sửa đúng redirect URI/issuer/proxy |
| `/oauth2/authorize` vẫn nhận direct request của client Required | Chưa gắn guard, sai thứ tự filter hoặc policy không được đọc | Test bypass, kiểm tra filter order và settings |
| Client vừa bật Required đã bị lỗi login | Client chưa chuyển sang POST PAR | Nâng cấp client trước khi bắt buộc |
| `request_uri` không tìm thấy sau login | Hết TTL, state không lưu/không đồng bộ giữa node | Kiểm tra expiry, saved request và authorization store |
| `request_uri` đúng nhưng client ID khác | Tham chiếu thuộc một client khác | Từ chối, không gỡ client binding |
| Scope/consent trống khi qua PAR | Lỗi mapping hoặc phiên bản/framework regression | Kiểm thử pushed scopes và custom consent page |
| Gặp redirect loop | Login/session/SecurityFilterChain sai | Kiểm tra thứ tự chain, CSRF/session, cookie |
| Token endpoint `invalid_grant` | Verifier không khớp, code hết hạn/đã dùng | Không tạo lại PKCE giữa PAR và token request |
| PAR nhận URI giả lạ hoặc URL quá dài | Input validation/rate limiting thiếu | Giới hạn body, chống DoS, xác thực client |
| Metadata báo mọi client phải PAR nhưng legacy vẫn direct được | Cấu hình global metadata mâu thuẫn policy | Sửa metadata hoặc hoàn tất migration |
| Không có claim API cần | PAR không phải token customizer | Xem token settings/customizer và Resource Server policy |
| Một node nhận PAR, node khác từ chối URI | Kho trạng thái hoặc issuer không đồng bộ | Shared authorization store, đồng bộ policy |
| URL front-channel lại chứa claims nhạy cảm | Client push rồi vẫn nối query cũ | Chỉ redirect với client ID + request URI |

### 14.1. Không “sửa” lỗi bằng cách bỏ các lớp bảo vệ khác

Nếu PAR thất bại vì callback mismatch, **đừng mở wildcard redirect URI**. Nếu nhận `invalid_grant` ở token endpoint, **đừng tắt PKCE**. Nếu browser reload khiến URI quá hạn, **đừng cho request_uri sống vô hạn**. Hãy sửa đúng nguồn lỗi trong client, authorization storage, clock, routing hoặc UX.

## 15. Vận hành và quan sát chính sách per-client

### 15.1. Chỉ số cần theo dõi

Nên giám sát theo client và môi trường:

- Tỷ lệ `POST /oauth2/par` thành công/thất bại;
- Tỷ lệ direct authorization bị từ chối vì `require_par`;
- Tỷ lệ `request_uri` hết hạn, đã dùng, sai client;
- Thời gian từ PAR response tới browser GET authorize;
- Login và consent success/failure, authorization code/token errors;
- Client version không hỗ trợ PAR;
- Tải PAR Endpoint, số lượng request vượt kích thước, rate limit `429`;
- Sai lệch cấu hình client giữa các node.

Các sự kiện audit nên ghi `client_id`, policy decision, endpoint, correlation ID, nhóm lỗi và thời gian xử lý. **Không ghi nguyên** client secret, `request_uri`, code, verifier, access/refresh token, cookie, raw authorization request chứa dữ liệu cá nhân.

### 15.2. Tính nhất quán dữ liệu

PAR dựa trên trạng thái được lưu tạm theo request reference, vì vậy nhiều instance cần kho/truy xuất nhất quán. Đồng thời bảo đảm `RegisteredClientRepository` cập nhật chính sách cùng phiên bản để tránh node A “Required” nhưng node B “Legacy”. Có thể dùng JDBC hoặc một store phù hợp với khả năng Spring Authorization Server đang chạy; tránh tuyên bố một loại storage mặc định luôn giải quyết concurrency/replay mà không kiểm thử.

### 15.3. Phương án ứng cứu

Nếu phát hiện một client bắt buộc PAR vẫn có thể authorize trực tiếp, coi đây là **security regression**. Cần:

1. Xác nhận request đã đi qua filter chain/host/issuer đúng.
2. Kiểm tra client policy từ repository và dữ liệu cache.
3. Kiểm tra filter order; xác minh direct request bị chặn **trước cấp code**.
4. Gắn cảnh báo tạm cho client, chặn ở ứng dụng theo quy trình an toàn nếu cần.
5. Kiểm thử lại request_uri hợp lệ, hết hạn, sai client và tình huống query override.
6. Phân tích phạm vi token/code đã phát trước khi vá, quyết định thu hồi nếu có rủi ro.

Đừng sửa bằng cách chặn mọi `/oauth2/authorize` ở mạng hoặc vô hiệu tính năng đăng nhập của tất cả client.

## 16. Bài tập thực hành

**Đề bài:** Hệ thống có `payments-portal` và `legacy-staff-portal`. Cả hai đều dùng Authorization Code + PKCE. `payments-portal` bắt buộc PAR; `legacy-staff-portal` chưa bắt buộc. Cùng issuer `https://login.example.com` và chung PAR Endpoint `/oauth2/par`.

**Yêu cầu triển khai:**

1. Đăng ký hai `RegisteredClient` với ID ổn định và redirect URI chính xác.
2. Gắn chính sách riêng qua `ClientSettings.setting("app.security.require_par", boolean)` hoặc policy repository.
3. Áp dụng protocol chain có PAR Endpoint và guard trước Authorization Endpoint.
4. Client payments POST PAR, nhận `request_uri`, browser dùng URL chỉ có client ID/request URI.
5. Thực hiện login/consent và code exchange với state/PKCE đúng.
6. Gửi direct authorization request với payments: nhận `invalid_request`, **không nhận code**.
7. Gửi direct authorization request với legacy: vẫn được xử lý theo policy thông thường.
8. Gửi request_uri giả, hết hạn và thuộc client khác: đều bị từ chối.
9. Kiểm tra các grant khác, metadata, multi-node và trường hợp login/consent kéo dài.
10. Chỉ khi tất cả test pass mới bật policy Required ở production.

**Tiêu chí đạt:** Bắt buộc PAR thực sự **theo từng client**, không làm hỏng login của client khác, không tin request_uri giả, không mở rộng scope/redirect, không làm mất PKCE/state và không đưa credential/request payload nhạy cảm lên browser URL.

## 17. Câu hỏi tự đánh giá

1. Hỗ trợ PAR khác bắt buộc PAR ở điểm nào?
2. Tại sao client cần POST `/oauth2/par` **trước** khi redirect browser?
3. Phản hồi PAR thành công có những trường nào, mã HTTP gì và `request_uri` dùng để làm gì?
4. Vì sao `request_uri` phải được ràng buộc với client đã push?
5. Nếu client Required gửi authorization request trực tiếp nhưng vẫn có PKCE đúng, máy chủ phải làm gì?
6. Một `request_uri` không rỗng có đủ chứng minh request đã push hợp lệ không?
7. Vì sao TTL của `request_uri` không đồng nhất với TTL authorization code hoặc session login?
8. Có thể yêu cầu PAR theo từng client trong RFC 9126 không? Global metadata khác per-client metadata ra sao?
9. Tại sao `ClientSettings.Builder.requirePushedAuthorizationRequests(true)` không thể dùng trong Spring Authorization Server 1.5.x?
10. `ClientSettings.setting("app.security.require_par", true)` đã tự enforce policy chưa? Cần thêm thành phần nào?
11. Vì sao một filter cần kiểm tra HTTP authorize request gốc thay vì chỉ nhìn các tham số đã được resolve?
12. Khi thêm AuthenticationProvider mới, nguy cơ bypass nào có thể xảy ra?
13. PAR có thay thế PKCE, consent hoặc OIDC nonce không?
14. Vì sao public client dùng PAR không tự có client secret an toàn?
15. Khi chuyển một client từ Legacy sang Required, test nào phải pass trước?
16. Nếu client POST PAR ở node A nhưng authorize ở node B thất bại, nên kiểm tra điều gì?

## 18. Tài liệu tham khảo chính thức

- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126): giao thức PAR, `request_uri`, `expires_in`, bắt buộc PAR global/per-client, metadata và bảo mật.
- [Spring Authorization Server 1.5.x — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `OAuth2AuthorizationServerConfigurer` và `AuthorizationServerSettings` gồm đường dẫn PAR.
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OAuth2PushedAuthorizationRequestEndpointConfigurer` và `OAuth2AuthorizationEndpointConfigurer`.
- [Spring Authorization Server 1.5.x — ClientSettings.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/ClientSettings.Builder.html): danh sách phương thức builder được hỗ trợ; không có setter require PAR trong 1.5.x.
- [Spring Authorization Server 1.5.x — AbstractSettings.AbstractBuilder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/AbstractSettings.AbstractBuilder.html): method `setting(name, value)` cho metadata ứng dụng.
- [Spring Security — OAuth2 Client Authorization Grant Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): `OAuth2AuthorizationRequestResolver`, Authorization Code + PKCE, client request handling.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE vẫn cần phối hợp với PAR.
- [RFC 9101 — JWT-Secured Authorization Request](https://www.rfc-editor.org/rfc/rfc9101): JAR có thể kết hợp PAR trong các profile cần Request Object.

**Ghi nhớ:** Một Authorization Server **có** `/oauth2/par` chưa chắc đã **bắt buộc PAR cho client nào**. Với Spring Authorization Server 1.5.x, có thể lưu cờ ứng dụng trong `ClientSettings` hoặc policy repository, nhưng phải **thực thi tại Authorization Endpoint**: client Required thiếu `request_uri` hợp lệ phải bị từ chối `invalid_request`. Guard chỉ kiểm tra có tham số; Spring vẫn phải xác minh tham chiếu do PAR Endpoint phát, đúng client, còn hạn và không bị thay đổi trái policy. Giữ PKCE, state, redirect URI validation, consent và kiểm thử negative paths là điều kiện thiết yếu để chuyển đổi PAR theo từng client an toàn trong hệ thống Spring Boot.
