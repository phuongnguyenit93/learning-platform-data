# 2.3. Authorization Endpoint, Token Endpoint và Redirect URI

Trong ứng dụng dùng **Spring Security OAuth 2.0/OIDC Client**, đăng nhập qua một nhà cung cấp danh tính (Identity Provider, viết tắt là IdP) thường dựa trên **Authorization Code Flow**. Ba địa chỉ xuất hiện liên tục trong luồng này là **Authorization Endpoint**, **Token Endpoint** và **Redirect URI**. Hiểu rõ bên nào sở hữu từng địa chỉ, dữ liệu nào được truyền qua đó và Spring Security xử lý ở bước nào giúp cấu hình đăng nhập đúng, đồng thời tránh các lỗi như `redirect_uri_mismatch`, `invalid_grant` hoặc mất `state`.

## 1. Phân biệt ba địa chỉ ngay từ đầu

| Thành phần | Nằm ở đâu? | Ai gọi? | Vai trò chính |
|---|---|---|---|
| **Authorization Endpoint** | Authorization Server/IdP | Trình duyệt được Client điều hướng tới | Bắt đầu yêu cầu ủy quyền, xác thực người dùng, xin sự đồng ý nếu cần và trả **authorization code** |
| **Token Endpoint** | Authorization Server/IdP | Ứng dụng Client gọi trực tiếp từ máy chủ | Đổi authorization code hợp lệ lấy token; có thể xử lý thêm các grant khác |
| **Redirect URI** (callback URL) | Ứng dụng Client | Trình duyệt quay về sau khi IdP xử lý yêu cầu | Nhận `code` và `state` (hoặc thông tin lỗi) để Client tiếp tục hoàn tất đăng nhập |

Ví dụ trong một hệ thống giả định:

- Authorization Endpoint: `https://id.example.test/oauth2/authorize`.
- Token Endpoint: `https://id.example.test/oauth2/token`.
- Redirect URI: `https://app.example.test/login/oauth2/code/company`.

Hai endpoint đầu thuộc **IdP**; Redirect URI thuộc **ứng dụng Spring**. Đường dẫn thật do từng nhà cung cấp quyết định, vì vậy không được mặc định mọi IdP đều dùng `/authorize` hay `/token`.

Có thêm một URL dễ bị nhầm với cả ba: `/oauth2/authorization/company`. Đây là **đường dẫn khởi động đăng nhập ở phía Spring Security Client**, với `company` là `registrationId`. Nó không phải Authorization Endpoint của IdP, cũng không phải callback nhận authorization code.

### OAuth 2.0 và OpenID Connect (OIDC) liên quan ra sao?

OAuth 2.0 mô tả cơ chế một Client nhận quyền truy cập tài nguyên thông qua access token. **OIDC bổ sung tầng xác thực danh tính trên OAuth 2.0**. Khi Client yêu cầu scope `openid` và IdP hỗ trợ OIDC, kết quả đăng nhập theo Authorization Code Flow thường có thêm **ID Token** để Client xác minh danh tính người dùng.

- **Authorization code:** giá trị tạm thời, dùng một lần, để đổi token; không phải token dùng gọi API.
- **Access token:** bằng chứng về quyền truy cập API hoặc tài nguyên được bảo vệ; không nên coi là một thông tin định danh thay cho ID Token.
- **ID Token:** token OIDC chứa các claim về sự kiện xác thực và danh tính; Client phải xác minh chữ ký và các claim quan trọng.
- **Refresh token:** có thể được cấp tùy cấu hình, chính sách và grant; không phải lần đăng nhập nào cũng có.

## 2. Bức tranh toàn bộ Authorization Code Flow

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant C as Spring Security Client
    participant A as Authorization Server / OIDC Provider

    U->>B: Mở trang cần đăng nhập
    B->>C: GET /oauth2/authorization/company
    C->>C: Tạo và lưu state, PKCE verifier
    C-->>B: 302 tới Authorization Endpoint
    B->>A: GET /authorize?response_type=code&...
    A->>U: Xác thực và xin consent nếu cần
    A-->>B: 302 tới Redirect URI với code, state
    B->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>C: Kiểm tra state và yêu cầu đã lưu
    C->>A: POST /token (code, redirect_uri, code_verifier, xác thực Client)
    A-->>C: access_token, id_token (OIDC), ...
    C->>C: Xác minh token và tạo Authentication
    C-->>B: Thiết lập phiên đăng nhập, chuyển tới trang đích
```

Điểm phân tách quan trọng nhất:

**Front channel (qua trình duyệt)** gồm điều hướng tới Authorization Endpoint và chuyển hướng trở lại Redirect URI. **Back channel (kết nối trực tiếp máy chủ tới máy chủ)** gồm lời gọi từ Spring Client đến Token Endpoint. Client secret và token response phải được xử lý trên kênh máy chủ phù hợp, không đưa vào URL của trình duyệt.

## 3. Authorization Endpoint: nơi bắt đầu yêu cầu ủy quyền

### 3.1. Endpoint này làm gì?

Authorization Endpoint nhận một **authorization request** từ Client. Authorization Server có thể yêu cầu người dùng đăng nhập, áp dụng MFA, kiểm tra phiên đăng nhập hiện tại, hiển thị màn hình đồng ý cấp quyền rồi đưa ra quyết định. Trong Authorization Code Flow, kết quả thành công là **authorization code** được chuyển về Redirect URI.

Client thường điều hướng trình duyệt bằng HTTP `302 Location` tới Authorization Endpoint; HTTP `GET` là cách phổ biến. URL thực tế cần lấy từ cấu hình của provider hoặc metadata OIDC, không suy ra từ tên nhà cung cấp.

Ví dụ URL đã rút gọn để minh họa:

```http
GET /oauth2/authorize?response_type=code&client_id=spring-web&
    redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&
    scope=openid%20profile%20email&
    state=RANDOM_STATE&
    code_challenge=BASE64URL_SHA256_VERIFIER&
    code_challenge_method=S256&
    nonce=RANDOM_NONCE HTTP/1.1
Host: id.example.test
```

Trong yêu cầu thật, các tham số được ghép thành một URL hợp lệ và URL-encode đúng chuẩn; ví dụ được xuống dòng cho dễ đọc.

| Tham số | Ý nghĩa |
|---|---|
| `response_type=code` | Yêu cầu Authorization Code Flow |
| `client_id` | Mã định danh Client đã đăng ký tại IdP; đây không phải bí mật |
| `redirect_uri` | Địa chỉ callback mà Authorization Server được phép chuyển trình duyệt về |
| `scope` | Quyền truy cập Client yêu cầu; `openid` cho biết đây là yêu cầu OIDC |
| `state` | Giá trị ngẫu nhiên để liên kết phản hồi với yêu cầu ban đầu, giúp chống CSRF và nhầm lẫn phiên |
| `code_challenge` | Giá trị dẫn xuất từ `code_verifier` theo PKCE |
| `code_challenge_method=S256` | Khai báo phương pháp PKCE dùng SHA-256 |
| `nonce` | Giá trị ngẫu nhiên của OIDC để liên kết ID Token với yêu cầu xác thực, giảm nguy cơ replay |

Không phải mọi yêu cầu OAuth 2.0 đều có `nonce`: tham số này thuộc OIDC. Tương tự, `scope=openid` là điểm phân biệt một yêu cầu OIDC với OAuth 2.0 thuần túy.

### 3.2. Authorization Server trả lại những gì?

Sau khi người dùng được xác thực và chấp thuận yêu cầu (nếu cần), Authorization Server điều hướng trình duyệt về callback:

```http
HTTP/1.1 302 Found
Location: https://app.example.test/login/oauth2/code/company?code=ONE_TIME_CODE&state=RANDOM_STATE
```

Ứng dụng nhận được **code**, sau đó phải đổi code tại Token Endpoint. Code có thời gian sống ngắn, thông thường chỉ dùng một lần và được ràng buộc với yêu cầu ban đầu. Không thể dùng code trực tiếp như access token để gọi API.

Nếu người dùng từ chối hoặc việc ủy quyền thất bại, phản hồi có thể là:

```http
HTTP/1.1 302 Found
Location: https://app.example.test/login/oauth2/code/company?error=access_denied&state=RANDOM_STATE
```

Trong trường hợp tham số `redirect_uri` không hợp lệ, Authorization Server **không nên tự động chuyển hướng** đến địa chỉ không được tin cậy. Vì vậy một số lỗi cấu hình sẽ hiện ngay tại IdP thay vì quay về ứng dụng.

### 3.3. `state`, `nonce` và PKCE giải quyết các vấn đề khác nhau

Ba cơ chế này thường xuất hiện chung nhưng không thể thay thế cho nhau:

| Cơ chế | Liên kết gì? | Mục tiêu chính |
|---|---|---|
| **`state`** | Authorization response với yêu cầu Client đã tạo | Phát hiện callback không thuộc phiên/yêu cầu ban đầu, chống login CSRF |
| **`nonce`** (OIDC) | ID Token với yêu cầu xác thực OIDC | Chống tái sử dụng hoặc trộn lẫn ID Token trong những bối cảnh tấn công liên quan |
| **PKCE** | Authorization code với Client đã bắt đầu flow | Khiến kẻ lấy cắp code không thể đổi token nếu không có `code_verifier` |

Với PKCE, Client tạo `code_verifier` ngẫu nhiên, giữ bí mật giá trị này trong suốt flow, sau đó gửi:

```text
code_challenge = BASE64URL(SHA256(code_verifier))
code_challenge_method = S256
```

Chỉ `code_challenge` được gửi qua Authorization Endpoint; `code_verifier` được gửi sau, qua Token Endpoint. Ưu tiên `S256`, đặc biệt với public clients. Với confidential web clients, dùng PKCE vẫn là biện pháp tăng cường hữu ích; có thể bật rõ ràng trong Spring Security khi cần.

`state` và `nonce` phải được tạo ngẫu nhiên cho mỗi yêu cầu, được kiểm tra khi nhận phản hồi phù hợp. Không sử dụng một chuỗi cố định cho tất cả phiên đăng nhập.

## 4. Token Endpoint: nơi đổi code lấy token

### 4.1. Vì sao Token Endpoint phải được gọi ở back channel?

Khi callback đã được Spring Security tiếp nhận và `state` được đối chiếu, Client gửi authorization code trực tiếp đến Token Endpoint qua HTTPS. Trình duyệt **không** cần biết client secret, refresh token hay toàn bộ nội dung token response.

Request thường là HTTP `POST` với body dạng `application/x-www-form-urlencoded`:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=authorization_code&
code=ONE_TIME_CODE&
redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&
code_verifier=ORIGINAL_RANDOM_VERIFIER
```

Ví dụ trên dùng phương thức xác thực Client `client_secret_basic`, thích hợp khi Client là ứng dụng web phía máy chủ có thể bảo vệ secret. Authorization Server có thể hỗ trợ cơ chế khác, như `private_key_jwt` hoặc public client với `client_authentication_method=none`; cần cấu hình theo loại Client đã đăng ký. **Không nhúng client secret vào Authorization Endpoint URL hoặc JavaScript chạy trong trình duyệt.**

Các trường quan trọng:

- `grant_type=authorization_code`: thông báo đang đổi authorization code.
- `code`: đúng code lấy từ callback hiện tại.
- `redirect_uri`: cùng URI đã gửi ở authorization request khi URI đó được cung cấp; Authorization Server kiểm tra sự ràng buộc này.
- `code_verifier`: giá trị gốc khớp với challenge của yêu cầu ban đầu nếu sử dụng PKCE.
- Client authentication: thực hiện theo phương thức đã đăng ký; không có client secret nếu là public client.

### 4.2. Token response

Kết quả thành công có thể có dạng:

```json
{
  "access_token": "eyJ...access-token-example",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid profile email",
  "id_token": "eyJ...id-token-example",
  "refresh_token": "optional-refresh-token"
}
```

Dữ liệu này chỉ là ví dụ, không phải token thật. `id_token` xuất hiện trong OIDC Authorization Code Flow; `refresh_token` có thể vắng mặt. Access token đôi khi là JWT, đôi khi là chuỗi opaque: Client không nên tự giả định định dạng access token.

Đối với đăng nhập OIDC, Spring Security cần xác minh ID Token, bao gồm những điểm như chữ ký, issuer (`iss`), audience (`aud`), thời gian hết hạn (`exp`) và `nonce` nếu request có gửi. Sau khi xác thực thành công, Spring tạo đối tượng `Authentication` trong security context. Access token được dùng khi Client cần gọi tài nguyên được bảo vệ; ID Token phục vụ xác nhận danh tính người dùng.

### 4.3. Token Endpoint báo lỗi gì?

Token Endpoint thường trả về HTTP error và JSON, ví dụ:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "Authorization code is invalid or expired"
}
```

`invalid_grant` có thể xảy ra khi code hết hạn, đã dùng, thuộc Client khác, callback URI không khớp hoặc PKCE verifier không đúng. `invalid_client` liên quan việc xác thực Client không thành công. Phải phân biệt lỗi **trên callback/front channel** với lỗi **trong trao đổi token/back channel** để tìm nguyên nhân chính xác.

Token Endpoint không chỉ phục vụ authorization code: tùy Authorization Server và grant được cho phép, nó còn có thể xử lý refresh token hoặc client credentials. Trong bài này ta tập trung vào authorization code của Spring Security OAuth2 Login.

## 5. Redirect URI: điểm callback của Client

### 5.1. Redirect URI không thuộc Authorization Server

Redirect URI là một URL mà **ứng dụng Client tiếp nhận**. Authorization Server chỉ dùng nó làm đích điều hướng trình duyệt sau bước xác thực/ủy quyền. Callback cần được khai báo trước trong cấu hình đăng ký Client tại IdP.

Với Spring Security OAuth2 Login theo mặc định:

```text
https://app.example.test/login/oauth2/code/company
                         └──────┬──────┘
                       registrationId = company
```

Đường dẫn `/login/oauth2/code/{registrationId}` thường do bộ lọc đăng nhập của Spring Security xử lý, không cần tự viết một `@GetMapping` để nhận code. Spring sẽ đọc query parameter, truy lại authorization request ban đầu, kiểm tra `state`, thực hiện token exchange rồi thiết lập đăng nhập.

### 5.2. Tại sao URI phải được đăng ký chính xác?

Authorization Server cần biết chắc code chỉ được gửi đến một callback đã được Client cho phép. Cấu hình đúng phải nhất quán ở ba nơi:

1. Redirect URI được đăng ký tại trang quản trị IdP.
2. `redirect_uri` xuất hiện trong authorization request do Spring tạo.
3. `redirect_uri` gửi khi đổi code tại Token Endpoint (nếu được gửi trong authorization request).

Chẳng hạn, nếu IdP đã đăng ký:

```text
https://app.example.test/login/oauth2/code/company
```

thì những URL sau thường **không tương đương**:

```text
http://app.example.test/login/oauth2/code/company
https://app.example.test:8443/login/oauth2/code/company
https://app.example.test/login/oauth2/code/other
https://app.example.test/login/oauth2/code/company/
```

Scheme, host, port, path và dấu gạch chéo cuối có thể tạo ra khác biệt. Từng Authorization Server áp dụng quy tắc đối sánh cụ thể; một số hỗ trợ ngoại lệ được chuẩn hóa cho địa chỉ loopback trong ứng dụng native. Đừng dựa vào wildcard redirect URI hoặc URL động thiếu kiểm soát trong môi trường production.

### 5.3. Vì sao Redirect URI là điểm nhạy cảm về bảo mật?

Nếu cho phép callback bất kỳ, kẻ tấn công có thể tìm cách nhận code qua một tên miền do họ kiểm soát. Vì vậy:

- Đăng ký danh sách callback cụ thể, ưu tiên HTTPS đối với ứng dụng triển khai thật.
- Tránh open redirect, tức callback lại chuyển tiếp người dùng đến một URL bên ngoài không được kiểm tra.
- Không đưa access token, refresh token hoặc client secret lên query string, lịch sử trình duyệt và log truy cập.
- Không ghi toàn bộ giá trị `code`, `state` hay token vào log vận hành.
- Đảm bảo callback quay về đúng phiên trình duyệt đã khởi tạo đăng nhập để Spring đối chiếu `state`.

URI `http://localhost:8080/login/oauth2/code/company` có thể được dùng trong phát triển cục bộ nếu IdP cho phép đăng ký callback tương ứng; điều đó không biến HTTP công khai trên Internet thành lựa chọn an toàn.

## 6. Liên hệ với Spring Boot và Spring Security

### 6.1. Các đường dẫn mặc định cần nhớ

| Đường dẫn hoặc thuộc tính | Bên sở hữu | Ý nghĩa |
|---|---|---|
| `/oauth2/authorization/{registrationId}` | Spring Client | URL người dùng/trình duyệt gọi để **bắt đầu** đăng nhập |
| `authorization-uri` | IdP | URL Authorization Endpoint, dùng trong yêu cầu chuyển hướng |
| `token-uri` | IdP | URL Token Endpoint, dùng cho đổi authorization code |
| `/login/oauth2/code/{registrationId}` | Spring Client | Callback mặc định nhận phản hồi từ IdP |
| `redirect-uri` | Cấu hình Client | Mẫu URL callback mà Spring gửi cho IdP |
| `issuer-uri` (OIDC) | Metadata IdP | Địa chỉ issuer dùng khám phá các endpoint và khóa xác minh của provider |

Tên `registrationId` (ví dụ `company`) chỉ là khóa cấu hình phía Spring. Nó không nhất thiết trùng với `client_id` mà IdP cấp.

Trong Servlet stack, hai thành phần đáng chú ý là:

- `OAuth2AuthorizationRequestRedirectFilter` xử lý URL bắt đầu OAuth2, tạo authorization request, lưu các dữ liệu cần đối chiếu (thường gắn với HTTP session) và điều hướng đến IdP.
- `OAuth2LoginAuthenticationFilter` xử lý callback của login flow và chuyển việc xác thực/trao đổi code cho hạ tầng Spring Security OAuth2 Login.

Các thành phần hỗ trợ khác như `ClientRegistrationRepository`, `OAuth2AuthorizedClientService` hoặc `OAuth2AuthorizedClientRepository` giữ thông tin Client và các authorized client/token theo cơ chế cấu hình. Người viết ứng dụng thường không cần tự dựng HTTP request đến Token Endpoint.

### 6.2. Cấu hình OIDC provider bằng `issuer-uri`

Ứng dụng Spring Boot 3 và Spring Security 6 có thể bắt đầu với dependency `spring-boot-starter-oauth2-client` và cấu hình minh họa sau:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            scope: openid, profile, email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          company:
            issuer-uri: https://id.example.test/realms/company
```

`OIDC_CLIENT_ID` và `OIDC_CLIENT_SECRET` là biến môi trường của ứng dụng, không phải tên/giá trị thật. `issuer-uri` cần trỏ đúng issuer mà IdP công bố, thường có thể khám phá metadata OIDC qua một URL `.well-known/openid-configuration` tương ứng.

Ví dụ metadata trả về có các trường:

```json
{
  "issuer": "https://id.example.test/realms/company",
  "authorization_endpoint": "https://id.example.test/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://id.example.test/realms/company/protocol/openid-connect/token",
  "jwks_uri": "https://id.example.test/realms/company/protocol/openid-connect/certs"
}
```

Trong trường hợp provider hỗ trợ discovery, Spring lấy các endpoint từ metadata và thiết lập cấu hình phù hợp. Do đó Authorization Endpoint và Token Endpoint **không cần tự đặt đường dẫn** nếu thông tin discovery chính xác. Khi provider không hỗ trợ discovery, có thể chỉ định `authorization-uri`, `token-uri`, `user-info-uri`, `jwk-set-uri` và các thuộc tính cần thiết tùy OAuth2/OIDC provider.

Cần đăng ký đúng callback, chẳng hạn:

```text
http://localhost:8080/login/oauth2/code/company
```

cho môi trường local chạy port 8080, và:

```text
https://app.example.test/login/oauth2/code/company
```

cho môi trường production. Các giá trị được đăng ký tại IdP phải phù hợp với URL thực tế mà Spring tạo ở từng môi trường.

### 6.3. Bật OAuth2 Login

Cấu hình Servlet Security đơn giản:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Khi vào `http://localhost:8080/oauth2/authorization/company`, Spring Security tạo authorization request với cấu hình của registration `company` rồi điều hướng trình duyệt đến Authorization Endpoint. Sau khi người dùng đăng nhập thành công và IdP đưa trình duyệt về `/login/oauth2/code/company`, Spring tiếp tục các bước xử lý. Cấu hình ở trên dành cho **web login dùng session**; việc gọi API dưới danh nghĩa Client (`oauth2Client`) hay xác minh bearer token tại API (`oauth2ResourceServer`) là các chức năng khác, dù cùng thuộc hệ sinh thái Spring Security OAuth2.

### 6.4. Bật PKCE rõ ràng cho authorization request

Với loại Client và phiên bản Spring Security cụ thể, hành vi tự động áp dụng PKCE có thể khác nhau. Để yêu cầu PKCE `S256` cho OAuth2 Login, có thể cấu hình resolver:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;

@Configuration
class OAuth2RequestConfig {

    @Bean
    DefaultOAuth2AuthorizationRequestResolver authorizationRequestResolver(
            ClientRegistrationRepository registrations) {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
            registrations, "/oauth2/authorization"
        );
        resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce()
        );
        return resolver;
    }
}
```

Sau đó dùng resolver này trong cấu hình `SecurityFilterChain`:

```java
http.oauth2Login(oauth2 -> oauth2
    .authorizationEndpoint(endpoint -> endpoint
        .authorizationRequestResolver(authorizationRequestResolver)
    )
);
```

Ở đoạn thứ hai, `authorizationRequestResolver` là bean đã được inject vào phương thức tạo `SecurityFilterChain`. Khi kết hợp hai ví dụ, thay phần `.oauth2Login(Customizer.withDefaults())` bằng lời gọi có resolver; tránh cấu hình OAuth2 Login trùng lặp. Spring giữ `code_verifier` gắn với authorization request để dùng khi đổi code. Authorization Server cũng phải hỗ trợ PKCE.

### 6.5. Đổi callback URL có chủ đích

Giả sử ứng dụng muốn callback tại `/auth/callback/company`. Ba phần phải được thay đồng bộ:

**Mẫu callback trong cấu hình Client:**

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
```

**Đường dẫn Spring Security lắng nghe:**

```java
http.oauth2Login(oauth2 -> oauth2
    .redirectionEndpoint(endpoint -> endpoint
        .baseUri("/auth/callback/*")
    )
);
```

**Redirect URI đăng ký tại IdP:**

```text
https://app.example.test/auth/callback/company
```

Nếu chỉ thay một phía, có thể phát sinh `redirect_uri_mismatch` tại IdP hoặc callback đi vào ứng dụng mà không khớp bộ lọc xử lý. Khi đã dùng cấu hình callback tùy chỉnh, vẫn cần bảo đảm URL bắt đầu đăng nhập và yêu cầu authorization request được giữ đúng.

### 6.6. Ứng dụng chạy sau reverse proxy hoặc load balancer

Một lỗi thường gặp: người dùng truy cập `https://app.example.test` nhưng Spring nhận kết nối nội bộ là `http://service:8080`, dẫn tới `{baseUrl}` được mở rộng thành callback nội bộ hoặc sai scheme/port.

Hướng xử lý là cấu hình proxy chuyển tiếp thông tin host/protocol công khai chính xác, và cho Spring Boot xử lý forwarded headers khi triển khai phù hợp, ví dụ:

```yaml
server:
  forward-headers-strategy: framework
```

Chỉ tin cậy forwarded headers từ hạ tầng proxy được kiểm soát; không cho Client bên ngoài tự quyết định host/scheme qua header giả mạo. Nếu cần, đặt rõ `redirect-uri` theo URL công khai của môi trường. Sau đó đối chiếu lại redirect URI trong authorization request với mục đã đăng ký ở IdP.

## 7. Tình huống minh họa từ đầu đến cuối

Giả sử ứng dụng chạy ở `https://portal.example.test`, IdP ở `https://sso.example.test`, registration `staff`, và IdP đã đăng ký callback:

```text
https://portal.example.test/login/oauth2/code/staff
```

Quy trình sẽ diễn ra như sau:

1. Người dùng mở `https://portal.example.test/reports` nhưng chưa đăng nhập.
2. Spring kích hoạt luồng đăng nhập; người dùng có thể được dẫn đến `/oauth2/authorization/staff`.
3. Spring tạo `state`, `nonce` (nếu áp dụng), PKCE challenge và chuyển trình duyệt sang Authorization Endpoint do IdP công bố.
4. IdP xác thực người dùng, rồi trả trình duyệt về `https://portal.example.test/login/oauth2/code/staff?code=...&state=...`.
5. Spring so sánh `state` với yêu cầu đã lưu, sau đó gọi Token Endpoint qua HTTPS để đổi code và `code_verifier` lấy token.
6. Trong OIDC, Spring xác minh ID Token và tạo phiên đăng nhập. Người dùng được chuyển về trang `/reports` theo cơ chế lưu yêu cầu ban đầu.

Đây là ba loại dữ liệu đi trên ba đoạn đường khác nhau:

| Đoạn đường | Dữ liệu điển hình | Có đi qua thanh địa chỉ trình duyệt? |
|---|---|---|
| Spring → Authorization Endpoint qua redirect | `client_id`, `redirect_uri`, `scope`, `state`, `code_challenge`, `nonce` | **Có** |
| Authorization Server → Redirect URI qua redirect | `code`, `state` hoặc `error` | **Có** |
| Spring → Token Endpoint bằng POST trực tiếp | `code`, `code_verifier`, `redirect_uri`, xác thực Client | **Không** |

Vì code xuất hiện trong URL callback, cần tránh ghi log, chia sẻ hoặc chuyển tiếp callback URL không kiểm soát. PKCE, thời gian sống ngắn và kiểm tra callback giúp giảm nguy cơ lộ code, nhưng không thay thế các biện pháp bảo vệ session, HTTPS và redirect URI chính xác.

## 8. Lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra ở đâu? |
|---|---|---|
| `redirect_uri_mismatch` | URL Spring gửi khác URI đã đăng ký ở IdP; sai scheme, host, port, path hoặc slash | So sánh `redirect_uri` được URL-decode từ authorization request với danh sách callback tại IdP |
| `invalid_client` tại Token Endpoint | Sai `client_id`/secret hoặc phương thức xác thực Client | Cấu hình `registration` của Spring và phương thức client authentication tại IdP |
| `invalid_grant` khi đổi code | Code hết hạn/đã dùng, sai `redirect_uri` hoặc PKCE verifier không khớp | Token request, thời gian sống code và dữ liệu PKCE của flow hiện tại |
| Callback báo lỗi `state` hoặc không tìm thấy yêu cầu ban đầu | Session/cookie bị mất, callback sang host khác, nhiều tab hoặc flow cũ bị ghi đè, cấu hình session không nhất quán | Session, cookie, proxy, `AuthorizationRequestRepository` và chuỗi redirect |
| Đăng nhập thành công tại IdP nhưng callback trả 404 | Path callback không khớp filter/route của Spring | `redirect-uri`, `redirectionEndpoint().baseUri(...)` và filter chain |
| Có access token nhưng ứng dụng không nhận là OIDC login | Thiếu scope `openid` hoặc cấu hình IdP/OIDC metadata không đúng | Scope đã yêu cầu, `issuer-uri`, ID Token và cấu hình provider |
| URL callback có `http://` dù bên ngoài dùng HTTPS | Reverse proxy chưa chuyển hoặc ứng dụng chưa xử lý host/protocol công khai | `Forwarded` / `X-Forwarded-*`, cấu hình proxy và forwarded headers |
| Redirect vòng lặp hoặc luôn quay về login | Phiên xác thực không được lưu/khôi phục, cookie bị chặn hoặc cấu hình nhiều filter chain chưa đúng | Session policy, cookie, security matchers và saved request |

Khi phân tích lỗi, bắt đầu bằng **bước nào thất bại**: không tới được IdP (khởi tạo/Authorization Endpoint), không quay về Client (Redirect URI), quay về được nhưng không đổi token (Token Endpoint), hay đổi token thành công nhưng không tạo được phiên đăng nhập (xác thực OIDC/phiên). Có thể tạm tăng mức log của Spring Security trong môi trường phát triển, nhưng phải che hoặc tránh lưu code, session cookie và token.

## 9. Những nguyên tắc triển khai cần nhớ

- **Phân tách vai trò:** Authorization Endpoint và Token Endpoint do IdP cung cấp; Redirect URI do Client cung cấp và đăng ký với IdP.
- **Dùng Authorization Code Flow với PKCE:** `state` và PKCE xử lý các rủi ro khác nhau, nên duy trì cả hai; với OIDC, dùng `nonce` và xác minh ID Token theo chuẩn.
- **Giữ bí mật phía server:** Client secret và token response không được gửi qua URL browser hay nhúng vào frontend; dùng HTTPS và cơ chế lưu token phù hợp.
- **Đồng bộ callback:** URI trong IdP, authorization request, token request và bộ lọc callback của Spring phải phù hợp.
- **Tận dụng cơ chế Spring Security:** `oauth2Login` thực hiện điều hướng, xử lý callback, code exchange và xác thực; ứng dụng không cần tự viết controller để đổi code trong luồng mặc định.
- **Phân biệt token:** authorization code, access token, ID Token và refresh token có mục đích và vòng đời khác nhau.
- **Đọc metadata provider:** Với OIDC, `issuer-uri` và discovery giúp lấy đúng Authorization Endpoint, Token Endpoint và khóa xác minh thay vì hard-code đường dẫn tùy đoán.

## 10. Tài liệu chuẩn để đào sâu

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization request, redirect endpoint, token request và các loại lỗi.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier`, `code_challenge` và phương thức `S256`.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC Authorization Code Flow, ID Token, `nonce` và quy tắc xác minh.
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): cấu hình `oauth2Login` và Client registration.

Khi nắm được **trình duyệt đi tới Authorization Endpoint**, **trình duyệt quay lại Redirect URI**, và **Spring gọi Token Endpoint trực tiếp**, bạn đã có khung đúng để đọc request, cấu hình Client registration, tìm lỗi callback và giải thích cách Spring Security hoàn tất một lần đăng nhập OIDC.
