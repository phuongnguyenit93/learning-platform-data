# 2.4. Authorization grant, authorization code, access token và refresh token

## 1. Bức tranh tổng thể

OAuth 2.0 là cơ chế **ủy quyền truy cập**: một ứng dụng (client) được cấp quyền gọi API của một hệ thống khác mà không cần nhận mật khẩu người dùng. Trong OpenID Connect (OIDC), OAuth 2.0 còn là nền tảng cho quy trình **xác thực người dùng**, nhưng OAuth 2.0 thuần không tự định nghĩa đăng nhập hay danh tính.

Giả sử một ứng dụng Spring Boot muốn hiển thị đơn hàng của người dùng:

| Vai trò | Trách nhiệm | Trong ví dụ |
| --- | --- | --- |
| Resource owner | Chủ thể quyết định quyền truy cập, thường là người dùng | Người sở hữu đơn hàng |
| Client | Ứng dụng xin quyền truy cập | Spring Boot web app |
| Authorization server | Xử lý ủy quyền và phát hành token | OAuth 2.0 / OIDC provider |
| Resource server | Bảo vệ API và kiểm tra token | API đơn hàng |

Các thuật ngữ trong tên bài thuộc những lớp khác nhau:

| Thuật ngữ | Là gì? | Mục đích chính |
| --- | --- | --- |
| **Authorization grant** | Phương thức hoặc quy trình giúp client có cơ sở xin token | Chọn cách ủy quyền thích hợp cho ngữ cảnh |
| **Authorization code** | Mã ngắn hạn, một lần sử dụng, nhận qua redirect ở Authorization Code flow | Đổi lấy token tại token endpoint |
| **Access token** | Credential cho phép truy cập tài nguyên trong phạm vi nhất định | Gửi đến resource server để gọi API |
| **Refresh token** | Credential cho phép xin access token mới mà không cần người dùng lặp lại toàn bộ quy trình ủy quyền | Gửi tới token endpoint, nếu đã được cấp |
| **ID token** (OIDC) | Bằng chứng xác thực người dùng được phát hành cho OIDC client | Xác nhận danh tính đăng nhập, không thay access token gọi API |

**Grant không phải là một token.** Authorization code không phải access token. Refresh token không phải quyền truy cập API. Đặc biệt, ID token và access token có thể cùng ở dạng JWT nhưng mục đích, audience và quy tắc xác minh khác nhau.

## 2. Những authorization grant cần biết

`grant_type` là tham số tại **token endpoint** cho biết client đang sử dụng loại grant nào.

| Grant | Ai được ủy quyền? | Khi nào dùng? | Có authorization code? |
| --- | --- | --- | --- |
| **Authorization Code** (`authorization_code`) kèm PKCE | Người dùng thông qua client | Web app, SPA, mobile app có đăng nhập tương tác | Có |
| **Client Credentials** (`client_credentials`) | Chính client/service | Giao tiếp service-to-service không có người dùng tương tác | Không |
| **Refresh Token** (`refresh_token`) | Quyền đã được cấp trước đó | Xin access token mới khi có refresh token hợp lệ | Không |
| **Device Authorization** (`urn:ietf:params:oauth:grant-type:device_code`) | Người dùng xác thực trên thiết bị khác | Smart TV, CLI, thiết bị nhập liệu hạn chế | Không dùng authorization code của Authorization Code flow |
| **Implicit** (`response_type=token`) | Người dùng | Thiết kế browser client cũ, không khuyến nghị cho ứng dụng mới | Không |
| **Resource Owner Password Credentials** (`password`) | Người dùng nhưng client trực tiếp nhận mật khẩu | Thiết kế cũ, không khuyến nghị | Không |

OAuth 2.0 có thể mở rộng grant. Khi chọn grant, cần hỏi: ứng dụng đang hành động **thay người dùng** hay **dưới danh nghĩa chính service**? Với **Spring Security OAuth 2.0 OIDC Client**, luồng trọng tâm cho web login thường là **Authorization Code + PKCE**. Client Credentials dùng khi cần token cho một tác vụ backend không có người dùng.

## 3. Authorization Code flow từ đầu đến cuối

Ví dụ hệ thống gồm:

- Client: `https://app.example.com` (Spring Boot).
- Authorization server / OIDC provider: `https://id.example.com`.
- Resource server: `https://api.example.com`.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Browser của người dùng
    participant C as Spring Security OAuth2 Client
    participant A as Authorization Server / OIDC Provider
    participant R as Resource Server
    U->>C: Truy cập trang cần đăng nhập
    C-->>U: Redirect đến authorization endpoint (state, PKCE)
    U->>A: Xác thực và chấp thuận quyền khi cần
    A-->>U: Redirect về client với code và state
    U->>C: GET redirect_uri?code=...&state=...
    C->>A: POST token endpoint (code, code_verifier, client authentication)
    A-->>C: access_token (+ refresh_token, id_token)
    C-->>U: Tạo phiên đăng nhập / trả trang
    C->>R: Gọi API với Bearer access_token
    R-->>C: Kết quả API
    C-->>U: Hiển thị dữ liệu
~~~

### Bước 1: Redirect đến authorization endpoint

Client khởi tạo request với `response_type=code`, `client_id`, `redirect_uri` và scope cần xin:

~~~http
GET /oauth2/authorize?response_type=code
    &client_id=web-client
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fdemo
    &scope=openid%20profile%20orders.read
    &state=RANDOM_STATE
    &code_challenge=BASE64URL_SHA256_VERIFIER
    &code_challenge_method=S256
    &nonce=RANDOM_NONCE
Host: id.example.com
~~~

Đây là URL được xuống dòng cho dễ đọc, không phải nguyên văn một HTTP request hợp lệ. Trong hệ thống thật, query string phải được mã hóa đúng.

`scope=orders.read` xin quyền đọc đơn hàng; `openid` biểu thị yêu cầu OIDC. `state` là chuỗi ngẫu nhiên gắn với giao dịch ủy quyền để client đối chiếu callback. `code_challenge` được tạo từ `code_verifier` cho PKCE. `nonce` trong OIDC giúp gắn ID token với giao dịch xác thực và phải được kiểm tra khi có sử dụng.

### Bước 2: Người dùng đăng nhập và cấp phép

Người dùng xác thực **tại authorization server**, không nhập mật khẩu vào OAuth client. Authorization server có thể hỏi người dùng chấp thuận các scope hoặc áp dụng chính sách consent có sẵn. Việc xác thực thành công không đồng nghĩa mọi scope đều được chấp thuận.

### Bước 3: Authorization server trả authorization code

Khi bước ủy quyền thành công, browser được redirect:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/demo?code=SHORT_LIVED_CODE&state=RANDOM_STATE
~~~

Authorization code chỉ tồn tại trong thời gian ngắn, được ràng buộc với client và redirect URI, và **chỉ được dùng một lần**. Code không có chức năng gọi resource server. Nếu code hết hạn, đã dùng, bị đổi redirect URI hoặc không vượt qua kiểm tra PKCE, token endpoint phải từ chối.

### Bước 4: Client đổi code lấy token qua back channel

Sau khi kiểm tra `state`, backend liên hệ **trực tiếp** token endpoint. Ví dụ cho *confidential client* có thể giữ client secret:

~~~bash
curl -X POST "https://id.example.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "web-client:REPLACE_WITH_CLIENT_SECRET" \
  --data-urlencode "grant_type=authorization_code" \
  --data-urlencode "code=SHORT_LIVED_CODE" \
  --data-urlencode "redirect_uri=https://app.example.com/login/oauth2/code/demo" \
  --data-urlencode "code_verifier=ORIGINAL_RANDOM_VERIFIER"
~~~

Token endpoint xác minh code, client, redirect URI và PKCE. Với *public client* như browser app hoặc mobile app, **không nhúng client secret** vào mã phân phối cho người dùng; cách xác thực tại token endpoint phải phù hợp loại client/provider.

Một phản hồi có thể là:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile orders.read",
  "refresh_token": "REFRESH_TOKEN_VALUE",
  "id_token": "ID_TOKEN_VALUE"
}
~~~

`expires_in` là số giây token còn hiệu lực tại thời điểm phát hành. Authorization server **không bắt buộc** phát hành refresh token; việc này phụ thuộc grant, scope, loại client và policy. `id_token` chỉ liên quan đến OIDC, không phải thành phần của OAuth 2.0 thuần.

### Bước 5: Client gửi access token cho API

~~~http
GET /orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Resource server quyết định có chấp nhận token và quyền trong token hay không. Access token **không nhất thiết là JWT**: nó có thể là opaque token hoặc một định dạng do authorization server hỗ trợ. JWT access token thường cần kiểm tra chữ ký, `iss` (issuer), `aud` (audience), `exp` và quyền; opaque token có thể được kiểm tra bằng introspection hoặc cơ chế thích hợp của resource server.

## 4. PKCE, state và nonce khác nhau thế nào?

| Cơ chế | Nguy cơ cần giảm | Client phải làm gì? |
| --- | --- | --- |
| **PKCE** | Kẻ tấn công lấy được authorization code rồi đổi code lấy token | Sinh `code_verifier` khó đoán; gửi `code_challenge` ở authorization request; gửi verifier gốc khi đổi code |
| **state** | Callback bị gắn nhầm phiên hoặc request giả mạo (authorization/login CSRF) | Sinh state cho mỗi giao dịch, lưu gắn với phiên và so khớp callback |
| **OIDC nonce** | ID token bị phát lại hoặc không thuộc yêu cầu xác thực mong đợi | Gửi nonce và xác minh giá trị nonce trong ID token khi áp dụng |

PKCE với phương thức **S256** tính:

~~~text
code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
~~~

Giá trị `code_verifier` phải được sinh ngẫu nhiên bằng nguồn mật mã và giữ lại cho giao dịch hiện tại; không đặt verifier vào authorization request. Kể cả khi code bị lộ, người khác không đổi được token nếu thiếu verifier đúng và server kiểm tra PKCE đầy đủ. **PKCE không thay thế state, nonce, redirect URI validation hoặc client authentication.**

Authorization Code + PKCE là lựa chọn nên dùng cho ứng dụng mới, kể cả web backend có client secret. Trong Spring Security, nên để framework quản lý state, callback và việc đổi code thay vì tự dựng servlet xử lý các bước bảo mật này.

## 5. Access token: quyền truy cập có phạm vi và thời hạn

Access token thể hiện một quyền đã cấp cho client trong ngữ cảnh cụ thể. Cần hiểu các thuộc tính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **Issuer** | Máy chủ phát hành token; resource server chỉ tin issuer hợp lệ |
| **Audience/resource** | API đích được phép nhận token, tránh gửi nhầm token của API khác |
| **Scope/authority** | Quyền được cho phép, ví dụ `orders.read` khác `orders.write` |
| **Expiry** | Token có thời hạn; client không nên dùng sau khi hết hạn |
| **Subject/client** | Token có thể gắn người dùng hoặc service, tùy grant |

Access token có loại **bearer**: ai cầm được token có thể sử dụng nó nếu không có ràng buộc bổ sung. Bởi vậy cần HTTPS, nơi lưu trữ phù hợp, hạn dùng ngắn, giới hạn scope/audience và tránh ghi token vào URL, log, analytics hay exception. Với hệ thống hỗ trợ, sender-constrained token (ví dụ DPoP hoặc mTLS) giảm rủi ro lạm dụng khi bearer token bị lấy cắp.

Một phản hồi API `401 Unauthorized` có thể do token hết hạn, sai issuer/audience, chữ ký không hợp lệ hoặc token bị thu hồi. `403 Forbidden` thường có nghĩa token được nhận diện nhưng thiếu quyền; refresh một token cùng scope sẽ không tự sửa lỗi thiếu quyền.

## 6. Refresh token và vòng đời gia hạn quyền truy cập

Khi access token hết hạn, client có thể xin token mới bằng **Refresh Token grant** nếu authorization server đã cấp refresh token. Người dùng không cần lặp lại bước đăng nhập/consent trong từng lần refresh.

~~~mermaid
flowchart TD
    A["Client cần gọi API"] --> B{"Access token còn hiệu lực?"}
    B -->|Có| C["Gọi API bằng access token"]
    B -->|Không| D{"Có refresh token hợp lệ?"}
    D -->|Có| E["POST /token với grant_type=refresh_token"]
    E --> F{"Refresh thành công?"}
    F -->|Có| G["Lưu access token mới; thay refresh token nếu rotated"]
    G --> C
    F -->|Không| H["Xóa trạng thái token lỗi; ủy quyền/đăng nhập lại"]
    D -->|Không| H
~~~

Ví dụ request từ confidential client:

~~~bash
curl -X POST "https://id.example.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "web-client:REPLACE_WITH_CLIENT_SECRET" \
  --data-urlencode "grant_type=refresh_token" \
  --data-urlencode "refresh_token=REFRESH_TOKEN_VALUE"
~~~

Phản hồi có thể chứa access token mới, thời hạn mới và refresh token mới:

~~~json
{
  "access_token": "NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "NEW_REFRESH_TOKEN_IF_ROTATED",
  "scope": "openid profile orders.read"
}
~~~

Không giả định response refresh lúc nào cũng chứa `refresh_token`. Nếu authorization server trả refresh token **mới** (*rotation*), client phải thay giá trị cũ an toàn; gửi lại token cũ có thể kích hoạt cơ chế phát hiện tái sử dụng và thu hồi cả chuỗi token. Các ứng dụng có nhiều request song song cần tránh hai luồng dùng đồng thời cùng một refresh token trong hệ thống rotation.

Những nguyên tắc bắt buộc khi xử lý refresh:

1. Chỉ gửi refresh token **đến token endpoint**, không đưa vào header gọi resource server hay gửi ra frontend không cần thiết.
2. Bảo vệ token trong lưu trữ, giới hạn truy cập và thời gian sống; không đưa vào log.
3. Refresh token có thể hết hạn hoặc bị thu hồi; client phải xử lý `invalid_grant` và đưa người dùng quay lại ủy quyền khi phù hợp, tránh refresh vô hạn.
4. Scope của token mới không được tự ý mở rộng vượt quyền đã cấp. Xin quyền bổ sung thường cần một authorization request mới.
5. Confidential client cần xác thực đúng khi refresh; public client cần chính sách bảo vệ refresh token như rotation hoặc sender constraint.
6. Scope `offline_access` trong một số OIDC provider có thể liên quan đến cấp refresh token, nhưng **không bảo đảm** provider luôn cấp; phải đọc chính sách cụ thể.

Client Credentials thường chỉ yêu cầu access token mới khi hết hạn và không cần refresh token vì không có phiên ủy quyền tương tác của người dùng.

## 7. ID token trong OIDC khác access token

OIDC dùng ID token để xác nhận kết quả xác thực cho **client**. Một ID token có thể chứa `iss`, `sub`, `aud`, `exp`, `iat` và `nonce` (khi dùng). Client phải xác minh các claim cần thiết, chữ ký và quan hệ với giao dịch đăng nhập.

Ví dụ với ứng dụng hiển thị đơn hàng:

- **“Ai vừa đăng nhập?”** — dùng OIDC principal/ID token đã được xác minh.
- **“Có thể gọi API đơn hàng không?”** — dùng access token được cấp đúng API và scope.
- **“Access token hết hạn rồi?”** — dùng refresh token tại token endpoint nếu được cấp.
- **“Có thể gửi ID token trong `Authorization: Bearer` thay access token không?”** — không; ID token có audience và ngữ nghĩa dành cho OIDC client, không chứng minh quyền gọi API.

Trong Spring Security, `oauth2Login()` có thể xác thực người dùng OIDC; `OAuth2AuthorizedClient` chứa trạng thái token dùng để gọi tài nguyên. **Phiên đăng nhập của web app và vòng đời access token của API là hai khái niệm riêng.**

## 8. Cấu hình và sử dụng Spring Security OAuth 2.0 Client

### 8.1. Đăng ký OIDC client trong Spring Boot

Ví dụ cho server-side web app:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo
            client-id: ${OAUTH2_CLIENT_ID}
            client-secret: ${OAUTH2_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          demo:
            issuer-uri: https://id.example.com/realms/demo
~~~

`issuer-uri` là địa chỉ minh họa, phải thay bằng issuer thật của provider có hỗ trợ discovery. Cần đăng ký chính xác redirect URI, client ID, phương thức xác thực và scope tại authorization server. Client secret là bí mật backend, lấy từ biến môi trường/secret store; không commit giá trị thật.

Ví dụ `SecurityFilterChain` cho Spring Security Servlet:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Đường dẫn `/oauth2/authorization/demo` bắt đầu luồng ủy quyền với registration `demo`. Callback mặc định tương ứng `/login/oauth2/code/demo`. Spring Security tạo, lưu và kiểm tra thông tin trạng thái giao dịch, chuyển code đến token endpoint, xác thực OIDC khi có `openid` và liên kết authorized client với principal. Các đường dẫn, base URL và proxy/HTTPS phải thống nhất với provider.

### 8.2. OAuth2AuthorizedClient và tự động refresh

Hai đối tượng dễ nhầm:

| Kiểu Spring Security | Chức năng |
| --- | --- |
| `ClientRegistration` | Thông tin cấu hình client, provider, scopes, grant type, endpoints |
| `OAuth2AuthorizedClient` | Client registration đã được cấp quyền cho một principal; có access token và refresh token nếu có |
| `OAuth2AuthorizedClientManager` | Thực hiện/tiếp tục việc ủy quyền bằng provider thích hợp, có thể refresh token |
| `OAuth2AuthorizedClientRepository` / `OAuth2AuthorizedClientService` | Nơi load/lưu trạng thái authorized client theo cách triển khai |

Một `OAuth2AuthorizedClientManager` cho ngữ cảnh Servlet request:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class OAuth2ClientConfig {
    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Trong một phương thức có `authentication` của người dùng và manager được inject, client xin authorized client như sau:

~~~java
OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
    .withClientRegistrationId("demo")
    .principal(authentication)
    .build();

OAuth2AuthorizedClient client = authorizedClientManager.authorize(request);
if (client == null) {
    throw new IllegalStateException("OAuth2 client chưa được ủy quyền");
}
String accessToken = client.getAccessToken().getTokenValue();
// Gửi accessToken qua HTTPS tới đúng downstream resource server.
~~~

Hai kiểu trong đoạn minh họa là `org.springframework.security.oauth2.client.OAuth2AuthorizeRequest` và `OAuth2AuthorizedClient`. Manager chỉ có thể refresh khi provider hỗ trợ, refresh token còn hợp lệ và cấu hình lưu trữ/quyền phù hợp; không phải mọi registration đều có refresh token.

Với background job không có Servlet request, cân nhắc `AuthorizedClientServiceOAuth2AuthorizedClientManager` và grant `client_credentials` nếu tác vụ không gắn với người dùng. Với nhiều ứng dụng/instance, cần quyết định cách lưu token bền vững, bảo vệ bí mật và đồng bộ refresh token rotation; tránh lưu toàn bộ token vào biến toàn cục hoặc gửi ra browser mà không có thiết kế phù hợp.

### 8.3. Session web không đồng nghĩa thời hạn token

Ứng dụng có thể vẫn duy trì session đăng nhập trong khi access token đã hết hạn và phải refresh. Ngược lại, refresh token đã bị thu hồi không tự động có nghĩa cookie phiên ứng dụng bị xóa ngay. Thiết kế logout, session timeout, revoke token và hành vi khi refresh thất bại phải phù hợp yêu cầu sản phẩm và provider.

## 9. Tình huống lỗi và cách phân biệt

| Triệu chứng | Khả năng xảy ra | Hướng xử lý |
| --- | --- | --- |
| Callback trả `error=access_denied` | Người dùng/policy từ chối ủy quyền | Hiển thị thông báo và không giả định đã có quyền |
| Callback có code nhưng login không hoàn tất | State lệch, cookie phiên mất, sai redirect URI | Kiểm tra state/session, proxy, HTTPS và callback URL |
| Token endpoint trả `invalid_grant` khi đổi code | Code quá hạn/đã dùng, sai redirect URI hoặc PKCE | Khởi tạo lại Authorization Code flow đúng |
| Token endpoint trả `invalid_client` | Client ID, secret hoặc phương thức xác thực không đúng | Đối chiếu cấu hình client đăng ký ở provider |
| Token response không có refresh token | Provider không cấp cho grant/client/scope này | Thiết kế lại luồng ủy quyền khi token hết hạn |
| Refresh trả `invalid_grant` | Refresh token quá hạn, bị revoke, dùng lại sau rotation | Xóa authorized client cũ và yêu cầu cấp quyền lại |
| API trả `401` | Token hết hạn/sai issuer, audience, chữ ký hoặc bị revoke | Kiểm tra token và resource server; refresh đúng cách nếu có |
| API trả `403` | Token được nhận nhưng thiếu quyền/scope | Kiểm tra scope và policy; refresh cùng scope thường vô ích |
| OIDC login chạy được nhưng API thất bại | Dùng ID token thay access token hoặc sai audience | Gửi đúng access token cho đúng API |

Không ghi vào log toàn bộ callback URL, authorization code, access token, refresh token hoặc client secret. Nên ghi mã lỗi, correlation ID và metadata không nhạy cảm.

## 10. Ba ví dụ lựa chọn đúng grant

**Web app theo người dùng:** người dùng đăng nhập OIDC bằng Authorization Code + PKCE. Spring Boot nhận authorization code qua callback, đổi lấy token, dùng access token đọc đơn hàng; refresh khi cần nếu được cấp refresh token. ID token phục vụ đăng nhập.

**Đồng bộ dữ liệu ban đêm:** service gọi API của service khác bằng Client Credentials. Không có authorization code/phiên người dùng; thường xin access token mới khi hết hạn, thay vì trông đợi refresh token.

**Đăng nhập trên Smart TV:** thiết bị hiển thị mã để người dùng đăng nhập trên điện thoại/máy tính. Dùng Device Authorization grant; mã thiết bị không phải authorization code của Authorization Code flow.

~~~text
Authorization Code + PKCE
  Người dùng đăng nhập/ủy quyền
      -> authorization code (ngắn hạn, một lần)
      -> token endpoint (+ code_verifier)
      -> access token -> gọi resource server
      -> refresh token (nếu được cấp) -> token endpoint -> access token mới

OIDC có thể cấp thêm ID token -> OIDC client xác minh danh tính người dùng.
~~~

Điểm cần giữ đúng khi lập trình Spring Security OAuth 2.0 OIDC Client là: **authorization code chỉ dùng để đổi token, access token chỉ gửi đúng API, refresh token chỉ gửi token endpoint, ID token dành cho xác thực OIDC, và grant quyết định luồng cấp quyền tương ứng với loại ứng dụng.**
