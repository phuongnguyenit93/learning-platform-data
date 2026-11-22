# 8.1. `OAuth2AuthorizationRequest` và các tham số gửi tới provider

## 1. `OAuth2AuthorizationRequest` là gì?

Trong ứng dụng **Spring Security OAuth 2.0/OIDC Client**, bước đầu của luồng **Authorization Code** thường là đưa trình duyệt đến **Authorization Endpoint** của Authorization Server (provider). URL chuyển hướng này mang các tham số để provider biết **ứng dụng nào đang yêu cầu quyền**, **người dùng cần cấp những quyền gì** và **kết quả sẽ quay về đâu**.

Spring Security mô hình hóa yêu cầu đó bằng lớp:

~~~java
org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest
~~~

`OAuth2AuthorizationRequest` là **đối tượng mô tả một authorization request**. Nó chứa dữ liệu cần thiết để tạo URL gửi đến provider, đồng thời có thể mang những thông tin **nội bộ ứng dụng** cần cho các bước tiếp theo. Trong luồng Authorization Code, đối tượng này thường được tạo khi trình duyệt truy cập:

~~~http
GET /oauth2/authorization/corporate HTTP/1.1
Host: portal.example.com
~~~

Sau đó Spring Security dựng authorization request và trả về phản hồi chuyển hướng:

~~~http
HTTP/1.1 302 Found
Location: https://idp.example.com/oauth2/authorize?response_type=code&client_id=portal-web&...
~~~

Lớp `OAuth2AuthorizationRequest` **không phải** HTTP request để đổi authorization code thành token. Bước đổi code lấy access token diễn ra **sau callback**, thông thường là một HTTP POST từ backend tới **Token Endpoint**, với các tham số và quy tắc bảo mật khác.

Cần nắm rõ bốn khái niệm liên quan:

| Thành phần | Trách nhiệm chính |
| --- | --- |
| `ClientRegistration` | Cấu hình **tĩnh** của một OAuth2 client: client ID, grant type, scopes, provider endpoints, redirect URI template |
| `OAuth2AuthorizationRequest` | Thể hiện **một lần khởi tạo cấp quyền**: URL authorization, `state`, redirect URI đã mở rộng, tham số bổ sung và metadata nội bộ |
| `OAuth2AuthorizationResponse` | Thể hiện kết quả từ Authorization Endpoint, như `code` hoặc lỗi do provider trả về |
| `OAuth2AuthorizedClient` | Đại diện client đã được cấp quyền, chứa access token và có thể có refresh token; dùng ở giai đoạn sau |

**Ý chính:** `ClientRegistration` cho biết *cách ứng dụng được đăng ký với provider*; `OAuth2AuthorizationRequest` mô tả *một lần yêu cầu cấp quyền cụ thể*.

## 2. Authorization Request nằm ở đâu trong luồng OAuth2/OIDC?

Một luồng OIDC Authorization Code thường bao gồm:

~~~mermaid
sequenceDiagram
    actor Browser as Trình duyệt
    participant App as Spring Security OAuth2 Client
    participant Store as AuthorizationRequestRepository
    participant IdP as OIDC Provider

    Browser->>App: GET /oauth2/authorization/corporate
    App->>App: Tìm ClientRegistration, tạo OAuth2AuthorizationRequest
    App->>Store: Lưu request gắn với phiên/state
    App-->>Browser: 302 Location: Authorization Endpoint + parameters
    Browser->>IdP: GET /authorize?response_type=code&...
    IdP->>Browser: Xác thực người dùng, xin consent (nếu cần)
    IdP-->>Browser: 302 redirect_uri?code=...&state=...
    Browser->>App: GET callback?code=...&state=...
    App->>Store: Tải/xóa authorization request đã lưu
    App->>App: Đối chiếu state và các thông tin liên quan
    App->>IdP: POST Token Endpoint: code + client authentication + code_verifier (khi có PKCE)
    IdP-->>App: Access token, ID Token (OIDC), ...
    App-->>Browser: Hoàn tất login/phiên ứng dụng
~~~

Trình duyệt thực sự **đi đến Authorization Endpoint**. Nó không tự gửi `client_secret` tới provider và không trực tiếp thực hiện token exchange ở backend web app.

Ở phía Servlet, Spring Security có các thành phần thường gặp:

- `OAuth2AuthorizationRequestRedirectFilter`: phát hiện yêu cầu khởi động authorization và đưa trình duyệt đến URL của provider.
- `OAuth2AuthorizationRequestResolver`: giải quyết `registrationId` và tạo `OAuth2AuthorizationRequest` tương ứng; triển khai mặc định là `DefaultOAuth2AuthorizationRequestResolver`.
- `AuthorizationRequestRepository<OAuth2AuthorizationRequest>`: lưu và lấy authorization request trong khoảng thời gian giữa redirect và callback; triển khai mặc định phổ biến là `HttpSessionOAuth2AuthorizationRequestRepository`.
- `OAuth2LoginAuthenticationFilter`: xử lý callback trong luồng OAuth2 Login; phối hợp đối chiếu thông tin đã lưu và thực hiện xác thực tương ứng.

Trong WebFlux có bộ API reactive tương ứng, ví dụ `OAuth2AuthorizationRequestRedirectWebFilter`, `ServerOAuth2AuthorizationRequestResolver`, `DefaultServerOAuth2AuthorizationRequestResolver` và `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>`. Tên class và điểm mở rộng phải khớp **Servlet/WebFlux** và phiên bản Spring Security dự án đang sử dụng.

## 3. Các thuộc tính chính của `OAuth2AuthorizationRequest`

Lớp này cung cấp những dữ liệu như:

| Thuộc tính/getter | Ý nghĩa | Thường xuất hiện trong URL gửi provider? |
| --- | --- | --- |
| `getAuthorizationUri()` | URL Authorization Endpoint nhận request | Là **địa chỉ đích** của redirect |
| `getAuthorizationGrantType()` | Kiểu grant liên quan, thường `authorization_code` | Không bắt buộc xuất hiện thành tham số riêng |
| `getResponseType()` | Loại phản hồi yêu cầu, thường `code` | Có: `response_type=code` |
| `getClientId()` | Định danh OAuth2 client | Có: `client_id` |
| `getRedirectUri()` | Callback URI cụ thể mà provider sẽ redirect về | Thường có: `redirect_uri` |
| `getScopes()` | Tập scope được yêu cầu | Có thể có: `scope=openid profile...` |
| `getState()` | Giá trị liên kết request/response, chống giả mạo | Có: `state` |
| `getAdditionalParameters()` | Các tham số mở rộng cho Authorization Endpoint | Có, với các mục được cấu hình để phát ra URL |
| `getAttributes()` | Dữ liệu **nội bộ** phục vụ Spring Security/ứng dụng | **Không tự động** gửi thành query parameters |
| `getAuthorizationRequestUri()` | URI cuối cùng dùng để chuyển hướng | Đây là URL hoàn chỉnh sau khi tổng hợp/encode |

Các getter nêu trên là những điểm cần biết của đối tượng. Tên trường trong `OAuth2AuthorizationRequest` không phải lúc nào cũng giống 100% tên parameter trên giao thức; Spring Security phải ánh xạ và **URL-encode** các giá trị trước khi phát redirect.

Ví dụ `attributes` có thể giữ thông tin phục vụ giao dịch, như registration ID hoặc PKCE code verifier. Trái lại, `additionalParameters` dành cho các parameter mở rộng mà Authorization Server cần nhận tại Authorization Endpoint. **Không chuyển bí mật từ `attributes` sang `additionalParameters` chỉ để “cho provider nhìn thấy”.**

### 3.1. `authorizationUri` khác `authorizationRequestUri`

Hai tên rất dễ nhầm:

- **`authorizationUri`:** địa chỉ Authorization Endpoint được khai báo bởi provider, ví dụ `https://idp.example.com/oauth2/authorize`.
- **`authorizationRequestUri`:** URL hoàn chỉnh bao gồm endpoint và query string như `response_type`, `client_id`, `state`, `code_challenge` và các tham số bổ sung.

Khi dùng Spring Security mặc định, hãy để framework dựng URI cuối cùng và encode. Nếu tự dựng URL, cần xử lý đúng query parameters và tránh **encode hai lần**, làm mất `state` hoặc thay đổi `redirect_uri`.

## 4. Các tham số cốt lõi gửi đến provider

Ví dụ Authorization Code/OIDC phổ biến:

~~~text
https://idp.example.com/oauth2/authorize
  ?response_type=code
  &client_id=portal-web
  &redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcorporate
  &scope=openid%20profile%20email
  &state=RANDOM_UNPREDICTABLE_VALUE
  &code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
  &code_challenge_method=S256
  &nonce=RANDOM_OIDC_NONCE
~~~

Dòng trên được xuống hàng để dễ đọc; thực tế giá trị trong HTTP `Location` thường là **một URL duy nhất**. Đây là ví dụ giải thích cấu trúc, không phải những giá trị `state`/`nonce` có thể dùng lại trong production.

| Parameter | Chuẩn/ngữ cảnh | Ý nghĩa | Chú ý |
| --- | --- | --- | --- |
| `response_type=code` | OAuth 2.0 Authorization Code | Yêu cầu provider trả authorization code sau khi người dùng cho phép | Giá trị `code` ứng với grant này |
| `client_id` | OAuth 2.0 | Cho provider biết ứng dụng nào đang yêu cầu cấp quyền | **Không phải secret**; có thể xuất hiện trong URL |
| `redirect_uri` | OAuth 2.0 | Địa chỉ provider đưa trình duyệt về sau authorization | Phải đúng URI được provider cho phép; kiểm tra chặt chẽ |
| `scope` | OAuth 2.0/OIDC | Những quyền/phạm vi client yêu cầu | Chuỗi các scope cách nhau bằng khoảng trắng theo chuẩn |
| `state` | OAuth 2.0 | Liên kết authorization response với request đã tạo | Cần ngẫu nhiên, khó đoán, lưu để đối chiếu ở callback |
| `code_challenge` | PKCE (RFC 7636) | Bản dẫn xuất từ code verifier | Gửi trên **authorization request** |
| `code_challenge_method=S256` | PKCE | Nêu thuật toán dẫn xuất challenge | `S256` được ưu tiên so với `plain` |
| `nonce` | OpenID Connect | Liên kết ID Token với yêu cầu xác thực và giúp giảm replay | OIDC-specific; không thay thế `state` |

Trong Authorization Code, `response_type` thường là `code`, còn `authorization-grant-type` tại registration cũng là `authorization_code`. Hai cách biểu diễn khác nhau: một là **tham số giao thức trong Authorization Endpoint**, một là **grant type cấu hình của client**.

### 4.1. `client_id` và `redirect_uri`

`client_id` được provider cấp cho ứng dụng và xác định đăng ký client đang yêu cầu quyền. Đừng gửi `client_secret` trên browser redirect: secret thuộc cơ chế client authentication ở Token Endpoint hoặc một phương thức xác thực client khác.

`redirect_uri` có ba điểm cần đặc biệt chú ý:

1. Nó phải trỏ tới callback mà browser **truy cập được**. Ví dụ portal công khai qua HTTPS phải dùng URL công khai đó, không dùng hostname container nội bộ.
2. Provider cần đối chiếu với những URI đã đăng ký theo chính sách của nó. Tốt nhất đăng ký **URI chính xác** thay vì wildcard mở rộng.
3. Nếu request gửi `redirect_uri`, token exchange cũng cần sử dụng giá trị tương ứng theo quy định của authorization code flow; bất nhất có thể dẫn đến `invalid_grant`.

Với Spring Security OAuth2 Login Servlet, callback mặc định thường là:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Ví dụ `registrationId=corporate`, base URL của browser là `https://portal.example.com` thì redirect URI là:

~~~text
https://portal.example.com/login/oauth2/code/corporate
~~~

Khi app ở sau reverse proxy, cấu hình forwarded headers hoặc khai báo public redirect URI đúng cách; không để host header không đáng tin cậy điều khiển URI đăng ký.

### 4.2. `scope` và khác biệt giữa OAuth2/OIDC

Scopes là các giá trị provider định nghĩa hoặc chuẩn hóa. Ví dụ:

~~~text
scope=openid profile email
~~~

- `openid` báo hiệu yêu cầu đăng nhập theo **OpenID Connect**.
- `profile` và `email` là những OIDC scopes phổ biến; dữ liệu thực tế phụ thuộc IdP, consent và claim release policy.
- `offline_access` có ngữ nghĩa OIDC liên quan đến xin quyền truy cập ngoại tuyến; cách cấp refresh token, yêu cầu consent và hỗ trợ cụ thể phụ thuộc provider.
- Scope nghiệp vụ như `orders.read` hay `report.read` phụ thuộc Resource Server và chính sách Authorization Server.

`scope` chỉ là **yêu cầu**. Provider có thể từ chối, giới hạn hoặc trả lại tập scope được cấp khác. Ứng dụng không được giả định rằng vì đã gửi `scope=orders.admin` thì access token chắc chắn có quyền đó.

### 4.3. `state` liên kết request và response

`state` là một giá trị khó đoán do client tạo trước khi redirect. Provider gửi lại `state` trong callback để client đối chiếu với authorization request đã lưu.

~~~text
Client tạo state = st_abc...     →     /authorize?...&state=st_abc...
Provider chuyển về callback          /login/oauth2/code/corporate?code=...&state=st_abc...
Client tải request đã lưu, so sánh  →    state phải khớp
~~~

`state` giúp chống **CSRF trong authorization flow**, và là thành phần quan trọng để ràng buộc callback với yêu cầu hợp lệ đã được khởi tạo. Giá trị phải đủ entropy, không dễ đoán, dùng đúng vòng đời. Đừng xây state chỉ bằng username, email, timestamp hoặc session ID lộ ra ngoài.

Nếu cần nhớ “người dùng muốn quay về trang nào sau login”, ứng dụng nên giữ thông tin trong storage phía server/session hoặc dùng cơ chế được bảo vệ/chính sách xác minh chặt chẽ. **Đừng biến `state` thành một URL redirect tùy ý do người ngoài điều khiển**, vì có thể tạo lỗ hổng open redirect hoặc rò dữ liệu.

## 5. PKCE: `code_challenge` được gửi đi, `code_verifier` phải được giữ lại

**Proof Key for Code Exchange (PKCE)** bổ sung cơ chế ràng buộc authorization code với bên đã khởi tạo flow. Với `S256`:

~~~text
code_verifier  = giá trị ngẫu nhiên, entropy cao, 43–128 ký tự hợp lệ
code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
~~~

Ví dụ giá trị kiểm chứng theo RFC 7636:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge:
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM

code_challenge_method:
S256
~~~

Trong **authorization request**, client gửi `code_challenge` và `code_challenge_method`. Sau khi nhận authorization code, client mới gửi **`code_verifier` tới Token Endpoint**. Provider tự tính challenge từ verifier và đối chiếu với giá trị gắn với code.

~~~mermaid
sequenceDiagram
    participant C as OAuth2 Client
    participant AS as Authorization Server
    C->>C: Sinh code_verifier ngẫu nhiên
    C->>C: Tính code_challenge = S256(verifier)
    C->>AS: Authorization request: code_challenge + method=S256
    AS-->>C: Callback: authorization code (+ state)
    C->>AS: Token request: code + code_verifier
    AS->>AS: Tính lại challenge và so sánh
    AS-->>C: Token nếu mọi điều kiện đều hợp lệ
~~~

**Không gửi `code_verifier` qua browser URL**. Spring Security có thể giữ nó trong `attributes` của `OAuth2AuthorizationRequest` hoặc trong dữ liệu gắn với flow mà token request component có thể truy xuất. Bản `code_challenge` mới nằm trong `additionalParameters` và xuất hiện trên authorization URL.

PKCE đặc biệt quan trọng đối với public clients như native/mobile và SPA, đồng thời cũng được khuyến khích áp dụng với confidential clients khi provider hỗ trợ. Nó **không thay thế** kiểm tra `state`, `redirect_uri`, client authentication hay xác minh ID Token.

Ở các phiên bản Spring Security hiện đại, `DefaultOAuth2AuthorizationRequestResolver` tự bật PKCE trong một số cấu hình client, ví dụ client được nhận diện là public (phương thức xác thực client `none`). Có thể bật PKCE có chủ đích cho client khác qua customizer khi provider hỗ trợ; không nên giả định mọi registration/phiên bản đã bật PKCE chỉ vì dùng authorization code.

## 6. OIDC `nonce` và các tham số đăng nhập bổ sung

Khi `scope` bao gồm `openid` và provider hỗ trợ OIDC, `nonce` là một giá trị được client sinh để liên kết một lần yêu cầu xác thực với **ID Token**. Provider đưa `nonce` vào ID Token tương ứng, cho phép client kiểm tra token thuộc đúng lần đăng nhập mong đợi theo yêu cầu của flow.

| Giá trị | Nơi xuất hiện | Được kiểm tra ở đâu? | Mục tiêu |
| --- | --- | --- | --- |
| `state` | Authorization Request và authorization response callback | Client đối chiếu callback với request đã lưu | Ràng buộc redirect/callback, chống CSRF trong authorization flow |
| `nonce` | Authorization Request và claim `nonce` trong ID Token | OIDC client kiểm tra ID Token theo yêu cầu flow | Ràng buộc ID Token với yêu cầu xác thực, giảm replay |
| `code_challenge` | Authorization Request | Authorization Server đối chiếu với verifier khi đổi code | Ràng buộc authorization code với client khởi tạo |
| `code_verifier` | Token Request (không nằm trong authorization URL) | Authorization Server | Chứng minh bên đổi code sở hữu verifier |

**Đừng nhầm ba giá trị này.** Cả ba thường là dữ liệu ngẫu nhiên nhưng phục vụ các lớp xác thực/ủy quyền khác nhau.

### 6.1. Các tham số OIDC chuẩn thường gặp

| Tham số | Ý nghĩa | Ví dụ/ghi chú |
| --- | --- | --- |
| `prompt` | Yêu cầu cách provider tương tác với người dùng | `login`, `consent`, `select_account`, `none` (theo OIDC và khả năng provider) |
| `login_hint` | Gợi ý định danh đăng nhập | Thường là email hoặc username; **không phải bằng chứng xác thực** |
| `max_age` | Thời gian tối đa kể từ lần xác thực gần nhất, tính bằng giây | `max_age=0` có thể yêu cầu xác thực mới |
| `acr_values` | Mức hoặc phương thức xác thực mong muốn | Các giá trị cụ thể do hệ thống/IdP thống nhất |
| `ui_locales` | Ngôn ngữ/giao diện người dùng ưu tiên | `vi en` |
| `claims` | Yêu cầu claim cụ thể, có thể là cấu trúc JSON được encode | Kích thước URL và hỗ trợ provider cần được cân nhắc |
| `id_token_hint` | ID Token trước đó được dùng làm gợi ý trong một số flow | Không tùy tiện đưa token nhạy cảm vào URL nếu không cần |

Một yêu cầu có thể là:

~~~text
...&prompt=select_account&login_hint=alice%40example.com&ui_locales=vi%20en
~~~

Các tham số có thể làm thay đổi hành vi đăng nhập, ảnh hưởng trải nghiệm người dùng hoặc lộ thông tin định danh trong URL/history/logs. Chỉ gửi **dữ liệu thực sự cần**, và đừng tin trực tiếp `login_hint` lấy từ input chưa được kiểm soát để xác định danh tính.

### 6.2. Tham số mở rộng của provider khác tham số chuẩn

Một số provider có tham số riêng. Ví dụ:

- `access_type=offline` và một số biến thể của `prompt` xuất hiện trong các hướng dẫn dành riêng cho Google OAuth/OIDC.
- `audience` có thể được một số nhà cung cấp yêu cầu để chỉ định API đích, nhưng **không phải tham số bắt buộc chung của RFC 6749**.
- `resource` được chuẩn hóa bởi **RFC 8707 Resource Indicators for OAuth 2.0**, dùng khi Authorization Server hỗ trợ chỉ rõ Resource Server dự kiến.
- `request`, `request_uri` liên quan đến các profile nâng cao như JWT-Secured Authorization Request (JAR) hoặc Pushed Authorization Requests (PAR) nếu provider và client triển khai tương ứng.

Không sao chép mù quáng ví dụ query string từ một provider sang provider khác. Các extension không được hỗ trợ có thể bị bỏ qua hoặc bị từ chối. Đặc biệt, gửi `resource`/`audience` không bảo đảm token được cấp cho API mong muốn nếu provider không hiểu, client không có quyền hoặc policy không cho phép.

## 7. Dữ liệu nào tuyệt đối không đưa lên Authorization URL?

Authorization URL đi qua trình duyệt, có thể xuất hiện trong lịch sử, log reverse proxy, log ingress, công cụ quan sát hoặc một số ngữ cảnh liên quan referrer. Các giá trị nhạy cảm không nên được gửi như query parameters tùy tiện.

| Dữ liệu | Vị trí đúng thông thường | Lý do |
| --- | --- | --- |
| `client_id` | Authorization Request | Định danh công khai của client |
| `client_secret` | Token Endpoint/client authentication theo grant được hỗ trợ | Bí mật client; không được phơi bày qua browser |
| `code_challenge` | Authorization Request | Giá trị đã dẫn xuất, được thiết kế để công bố |
| `code_verifier` | Token Request; giữ nội bộ đến lúc đổi code | Nếu lộ verifier, khả năng bảo vệ của PKCE bị giảm |
| `state` | Authorization Request + callback, đối chiếu phía client | Dùng giá trị ngẫu nhiên, không nhúng thông tin bí mật |
| `nonce` | Authorization Request + ID Token | Dùng giá trị ngẫu nhiên; không nhúng bí mật |
| Access token/refresh token | Token Response và kho lưu trữ bảo vệ của client | Không nhúng vào authorization URL |
| ID Token | Token Response OIDC (trong Authorization Code flow) | Không dùng làm `access_token` hoặc đưa lên URL không cần thiết |
| Mật khẩu người dùng | Giao diện đăng nhập của provider, bảo vệ theo thiết kế provider | OAuth2 client không cần lấy mật khẩu chỉ để tạo authorization request |

**Authorization Code** sau callback cũng là giá trị ngắn hạn có tính nhạy cảm; backend phải đổi code qua kênh thích hợp, sử dụng một lần và tránh ghi log.

## 8. Ví dụ cấu hình Spring Boot và authorization request mặc định

Giả sử một ứng dụng web Servlet muốn cho phép đăng nhập qua OIDC Provider nội bộ. Dependency Gradle điển hình:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-oidc
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-oidc:
            issuer-uri: https://idp.example.com/realms/employees
~~~

`SecurityFilterChain`:

~~~java
@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Các kiểu và annotation được import từ Spring Boot, Spring Framework và Spring Security tương ứng; ví dụ lược bớt `import`.

Khi truy cập `/oauth2/authorization/corporate`:

1. Spring Security tìm `ClientRegistration` theo `registrationId=corporate`.
2. Resolver tìm **Authorization Endpoint** qua provider metadata của `corporate-oidc`.
3. Resolver tạo `OAuth2AuthorizationRequest`, bao gồm `client_id`, `response_type=code`, `redirect_uri` đã mở rộng, scope, state và những tham số bảo mật bổ sung phù hợp.
4. Repository lưu thông tin cần cho callback; trong cấu hình Servlet mặc định phổ biến, dữ liệu được giữ qua **HTTP session**.
5. Browser được chuyển hướng tới IdP.
6. Sau khi provider trả callback, Spring Security dùng dữ liệu đã lưu để tiếp tục xác thực và đổi code thành token.

`issuer-uri` chỉ giúp xác định metadata và thông tin tin cậy về provider; nó **không tự động đổi behavior của authorization request** thành một grant khác.

### 8.1. Hiểu URI hoàn chỉnh được gửi đi

Ví dụ URI sau đã **được percent-encode** ở những giá trị cần thiết:

~~~http
HTTP/1.1 302 Found
Location: https://idp.example.com/realms/employees/protocol/openid-connect/auth?response_type=code&client_id=portal-web&scope=openid%20profile%20email&state=ObfAc2WvD4c8&redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcorporate&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256
~~~

URL là minh họa, không phải mô tả đầy đủ mọi tham số mà mọi phiên bản/provider nhất thiết sẽ phát ra. Đặc biệt, `nonce` có thể được thêm trong luồng OIDC tùy provider/phiên bản/cấu hình; trình tự tham số không quan trọng đối với ý nghĩa giao thức.

**Không kiểm tra ứng dụng bằng cách so sánh nguyên chuỗi `Location` với một chuỗi cố định**: `state`, PKCE challenge và nonce cần thay đổi giữa các flow, và thứ tự query parameters cũng có thể thay đổi.

## 9. Tự xây `OAuth2AuthorizationRequest` bằng Builder

Có thể tự xây một request để hiểu mô hình dữ liệu của lớp này:

~~~java
OAuth2AuthorizationRequest createRequest(
        String randomState,
        String publicRedirectUri) {

    return OAuth2AuthorizationRequest.authorizationCode()
        .authorizationUri("https://idp.example.com/oauth2/authorize")
        .clientId("portal-web")
        .redirectUri(publicRedirectUri)
        .scopes(Set.of("openid", "profile"))
        .state(randomState)
        .additionalParameters(params -> {
            params.put("prompt", "select_account");
            params.put("ui_locales", "vi en");
        })
        .attributes(attrs -> {
            attrs.put("internalFlowName", "staff-login");
        })
        .build();
}
~~~

Những phần trong ví dụ:

- `authorizationCode()` chọn dạng authorization request có `response_type=code`.
- `authorizationUri(...)` chọn **endpoint đích**.
- `clientId(...)` và `redirectUri(...)` xác định client và callback.
- `scopes(...)` chỉ định các scopes được yêu cầu.
- `state(...)` nhận giá trị đã được **tạo ngẫu nhiên an toàn** từ phía gọi hàm; không bao giờ dùng một chuỗi cố định cho tất cả request.
- `additionalParameters(...)` thêm `prompt`/`ui_locales` mà provider có thể nhận.
- `attributes(...)` giữ `internalFlowName` để sử dụng nội bộ, **không tự động được encode vào authorization URL**.

Đoạn này tập trung vào cấu trúc dữ liệu và chưa tạo/giữ `code_verifier`, `nonce` hay hoàn chỉnh logic callback. **Trong ứng dụng thực tế, nên tùy biến resolver mặc định của Spring Security** để tận dụng state, PKCE, nonce và cơ chế lưu authorization request có sẵn thay vì tự dựng lại toàn bộ authentication flow.

### 9.1. Đọc request sau khi xây

~~~java
OAuth2AuthorizationRequest request =
    createRequest(secureRandomState, publicRedirectUri);

String targetUrl = request.getAuthorizationRequestUri();
Map<String, Object> extra = request.getAdditionalParameters();
Map<String, Object> internal = request.getAttributes();
String state = request.getState();
~~~

Lệnh trên cho thấy:
- `targetUrl` là giá trị thích hợp để dùng làm đích redirect.
- `extra` mô tả các tham số phát ra provider (theo cách Spring dựng URI).
- `internal` dùng ở **client**, không mặc định gửi sang provider.
- `state` phục vụ cả request và callback matching.

Không ghi log toàn bộ đối tượng request trong production: attributes có thể chứa dữ liệu cần bảo vệ như PKCE code verifier, còn URI có state và đôi khi thông tin cá nhân trong `login_hint`.

## 10. Tùy biến authorization request với `OAuth2AuthorizationRequestResolver` (Servlet)

Khi muốn thêm một tham số hợp lệ cho provider như `prompt=select_account`, có thể đặt customizer vào `DefaultOAuth2AuthorizationRequestResolver`:

~~~java
@Configuration
class OAuth2LoginCustomization {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
            registrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(builder -> {
            builder.additionalParameters(parameters ->
                parameters.put("prompt", "select_account"));
        });

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)
                )
            );

        return http.build();
    }
}
~~~

Ở đây:
- `DefaultOAuth2AuthorizationRequestResolver` vẫn thực hiện công việc lấy `ClientRegistration` và chuẩn bị các trường thiết yếu.
- Customizer **bổ sung** một OIDC parameter được provider hỗ trợ.
- Cấu hình trong `oauth2Login(...).authorizationEndpoint(...)` gắn resolver mới vào luồng login.
- Browser tiếp tục sử dụng đường dẫn khởi động `/oauth2/authorization/{registrationId}`.

Các tham số bổ sung phải được provider hỗ trợ. `prompt=select_account` là một tùy chọn OIDC hữu ích với một số provider; provider có thể có hành vi cụ thể khác nhau. Nếu cần thêm các tham số theo từng registration, resolver có thể cần logic kiểm soát theo provider tương ứng.

### 10.1. Cách bật PKCE có chủ đích

Khi Authorization Server hỗ trợ PKCE và muốn áp dụng rõ cho authorization code client, Spring Security cung cấp customizer:

~~~java
var resolver = new DefaultOAuth2AuthorizationRequestResolver(
    registrations, "/oauth2/authorization");

resolver.setAuthorizationRequestCustomizer(builder -> {
    OAuth2AuthorizationRequestCustomizers.withPkce().accept(builder);

    builder.additionalParameters(params -> {
        params.put("prompt", "select_account");
    });
});
~~~

`OAuth2AuthorizationRequestCustomizers.withPkce()` thêm dữ liệu PKCE theo hợp đồng Spring Security: challenge/method cho authorization URL và verifier cần giữ cho token request. Việc gọi thêm `withPkce()` có ý nghĩa khi **provider hỗ trợ PKCE**; với một số public client, Spring Security đã tự bật PKCE theo cấu hình mặc định.

Nếu customizer cũng sửa thêm những giá trị do framework quản lý (ví dụ `state`, `redirect_uri`, `nonce` hoặc PKCE values), bạn phải hiểu đầy đủ tác động tới callback và token exchange. Mẫu thực hành an toàn là **chỉ bổ sung tham số nghiệp vụ cần thiết**, giữ nguyên các kiểm tra bảo mật mặc định.

### 10.2. Thêm `login_hint` động: nguồn dữ liệu nào đáng tin?

Ví dụ người dùng chọn email tài khoản tổ chức trước khi đăng nhập. Có thể đưa email đó vào `login_hint`, nhưng cần xác định rõ nó chỉ là **gợi ý giao diện**. Đừng cho rằng provider đã xác thực người dùng dựa trên tham số này.

Một resolver tùy chỉnh hoàn chỉnh có thể:
1. Đọc giá trị gợi ý đã được ứng dụng chấp nhận theo chính sách.
2. Kiểm tra định dạng và giới hạn độ dài.
3. Chỉ thêm cho registration được phép và provider hỗ trợ.
4. Tránh đưa thông tin nhạy cảm vào URL nếu không cần.
5. Giữ nguyên state, nonce, PKCE và redirect URI do Spring Security quản lý.

Nếu cần logic theo `HttpServletRequest` cho từng request, có thể triển khai một lớp bọc `OAuth2AuthorizationRequestResolver` và ủy quyền việc dựng request cốt lõi cho resolver mặc định. Cẩn trọng với hai phương thức `resolve(HttpServletRequest)` và `resolve(HttpServletRequest, String registrationId)` để giữ đúng hành vi Spring Security ở cả hai trường hợp.

## 11. Lưu request giữa redirect và callback

Authorization Request không chỉ là URL. Ứng dụng còn cần giữ dữ liệu tương ứng để khôi phục ngữ cảnh khi browser trở về callback.

### 11.1. Servlet: `AuthorizationRequestRepository`

Hợp đồng Spring Security Servlet:

~~~java
AuthorizationRequestRepository<OAuth2AuthorizationRequest>
~~~

Triển khai thông dụng:

~~~java
HttpSessionOAuth2AuthorizationRequestRepository
~~~

Repository có trách nhiệm lưu, tải và xóa authorization request theo lifecycle tương ứng. Với ứng dụng web dùng session, `JSESSIONID` hoặc cookie session tương đương giữ liên hệ giữa browser và HTTP session ở phía ứng dụng.

Những điểm vận hành:

- **Lưu request trước redirect:** khi provider redirect về, backend phải tải lại được request đã tạo.
- **Liên kết callback:** `state` trên callback được đối chiếu với request đang chờ.
- **Dữ liệu ngắn hạn:** request nên được loại bỏ sau khi xử lý, tránh tái sử dụng cho các callback khác.
- **Session và SameSite:** cấu hình cookie, domain, Secure, SameSite và reverse proxy có thể ảnh hưởng việc callback có mang lại session thích hợp hay không.
- **Ứng dụng nhiều instance:** nếu session ở bộ nhớ từng instance, cần cơ chế điều phối/session storage phù hợp hoặc cấu hình hạ tầng nhất quán; không nên dựa vào sự may mắn của load balancer.
- **Không lưu mọi dữ liệu vào state trên URL:** giữ thông tin tin cậy phía server khi có thể.

Ví dụ đổi base URI khởi tạo request:

~~~java
http.oauth2Login(oauth2 -> oauth2
    .authorizationEndpoint(endpoint -> endpoint
        .baseUri("/sso/authorization")
    )
);
~~~

Khi thay base URI, link bắt đầu login thường đổi thành `/sso/authorization/corporate`. **Đây không phải callback URI**; callback vẫn do `redirectionEndpoint` và đăng ký provider chi phối. Nếu thay callback, phải điều chỉnh đồng bộ ở Spring Security, `redirect-uri` của client và Authorization Server.

### 11.2. WebFlux: repository và resolver reactive

Với WebFlux, các khái niệm tương tự nhưng **API nhận/trả `ServerWebExchange` và `Mono`**:

| Servlet/MVC | Reactive/WebFlux |
| --- | --- |
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `OAuth2AuthorizationRequestResolver` | `ServerOAuth2AuthorizationRequestResolver` |
| `DefaultOAuth2AuthorizationRequestResolver` | `DefaultServerOAuth2AuthorizationRequestResolver` |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` |
| `HttpSessionOAuth2AuthorizationRequestRepository` | `WebSessionOAuth2ServerAuthorizationRequestRepository` |
| `SecurityFilterChain` / `HttpSecurity` | `SecurityWebFilterChain` / `ServerHttpSecurity` |

Ví dụ cấu hình cơ bản:

~~~java
@Configuration
@EnableWebFluxSecurity
class ReactiveLoginSecurity {

    @Bean
    SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Spring Security WebFlux sử dụng resolver và repository tương ứng để giải quyết authorization request và quản lý ngữ cảnh giữa redirect/callback. Khi cần tùy biến cụ thể một parameter trong WebFlux, dùng **server/reactive resolver** của phiên bản Spring Security hiện tại; không inject `HttpServletRequest` hoặc `DefaultOAuth2AuthorizationRequestResolver` của Servlet vào luồng Netty/WebFlux.

Nếu ứng dụng dùng cả Login và OAuth2 Client để gọi API, đừng nhầm storage của **authorization request chưa hoàn tất** với storage của **authorized client sau khi đã có token**. Hai thứ có vòng đời và trách nhiệm khác nhau.

## 12. Tương tác giữa redirect request và token request

Một lỗi phổ biến là sửa authorization request mà quên bước đổi code. Hai HTTP request có bộ tham số khác nhau:

| Parameter/dữ liệu | Authorization Endpoint (qua browser) | Token Endpoint (backend, sau callback) |
| --- | --- | --- |
| `client_id` | Thường có | Có thể có, theo phương thức xác thực client |
| `client_secret` | **Không** | Có thể dùng nếu confidential client và provider quy định |
| `response_type=code` | **Có** | Không |
| `grant_type=authorization_code` | Không | **Có** |
| `redirect_uri` | Thường có | Có khi theo yêu cầu giao thức/provider; phải phù hợp request ban đầu |
| `state` | **Có** | Thường không phải tham số token request |
| `code_challenge`, `code_challenge_method` | **Có khi dùng PKCE** | Không |
| `code_verifier` | **Không** | **Có khi dùng PKCE** |
| `code` | Chưa có | **Có**, lấy từ callback |
| `scope` | Thường có | Thông thường không cần lặp lại khi đổi authorization code |
| Access token/ID Token | Chưa có trong Authorization Code request | Nằm trong token response nếu cấp thành công |

Sơ đồ:

~~~text
(1) GET /authorize?response_type=code&client_id=...&state=...&code_challenge=...
                  |
                  v
(2) GET /login/oauth2/code/corporate?code=...&state=...
                  |
                  v
(3) POST /token
    grant_type=authorization_code
    code=...
    redirect_uri=...
    code_verifier=...                (nếu có PKCE)
    + client authentication          (nếu áp dụng)
                  |
                  v
(4) Token response → Authentication / OAuth2AuthorizedClient
~~~

Provider có thể trả:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.com/login/oauth2/code/corporate?error=access_denied&state=...
~~~

Khi có `error`, đó là **authorization response báo lỗi**. Ứng dụng cần xử lý callback một cách an toàn, đối chiếu state/flow theo giao thức và không hiển thị nội dung lỗi chứa thông tin bí mật.

## 13. Mở rộng theo provider: khả năng tương thích và an toàn

Trước khi thêm một parameter, trả lời ba câu hỏi:

1. **Chuẩn hay provider-specific?** `prompt` là OIDC parameter; `audience` phụ thuộc provider; `resource` có định nghĩa trong RFC 8707 nếu server hỗ trợ.
2. **Giá trị là gì và lấy từ đâu?** Nếu là dữ liệu người dùng, có bị lộ trong URL/log không? Nếu lấy từ query parameter của browser, đã được giới hạn và kiểm soát chưa?
3. **Provider có chấp nhận không?** Cần đối chiếu discovery, tài liệu hoặc cấu hình IdP; một số server từ chối ngay những tham số không hỗ trợ.

Một số vấn đề an toàn quan trọng:

- **Không để client tự ý thay Authorization Endpoint** qua một URL tùy ý từ request; rất dễ dẫn tới SSRF, open redirect hoặc gửi thông tin đăng nhập đến provider giả.
- **Không tắt/ghi đè state validation** khi cần lưu thông tin nghiệp vụ; dùng storage gắn với phiên hoặc cơ chế riêng có bảo vệ phù hợp.
- **Không tự cấp phát cố định PKCE code verifier, nonce hay state** để dễ kiểm tra; mỗi flow phải có giá trị phù hợp và khó đoán.
- **Không đưa bearer token, refresh token, client secret, mật khẩu hoặc PII không cần thiết vào URL**.
- **Không hiểu scope, audience hay login_hint là bằng chứng đã xác thực**; kết quả thực phải được kiểm tra ở callback, token response và Resource Server.
- **Không dùng OAuth2 Login làm Authorization Server**; các API trên mô tả vai trò client.
- **Không thay thế URI validation bằng việc cho phép redirect wildcard rộng**; registration và IdP cần thống nhất callback chính xác.
- **Không xây logic auth chỉ dựa vào việc nhìn thấy `code` trên callback**; còn cần đối chiếu state, PKCE, client/issuer, token validation và những bước tiêu chuẩn khác.

Nếu cần yêu cầu phức tạp với nhiều claims dẫn đến URL vượt giới hạn, có thể nghiên cứu **PAR (RFC 9126)** hoặc **JAR (RFC 9101)** nếu Authorization Server và thư viện client hỗ trợ. Không thể coi việc tự thêm `request_uri` vào `additionalParameters` là đã triển khai đầy đủ PAR: PAR yêu cầu một quy trình push request riêng trước khi redirect.

## 14. Quan sát và xử lý lỗi Authorization Request

### 14.1. Quan sát redirect với HTTP client

Trong môi trường phát triển, có thể kiểm tra response **mà không tự động follow redirect**:

~~~bash
curl -i --max-redirs 0 \
  http://localhost:8080/oauth2/authorization/corporate
~~~

Kỳ vọng có HTTP 302 và `Location` trỏ về Authorization Endpoint của provider. Ví dụ thực tế phụ thuộc ứng dụng có yêu cầu HTTPS, session cookie hay bảo vệ khác hay không.

Chú ý: giá trị `state`, `nonce`, `code_challenge` và cookie session là dữ liệu liên quan đến luồng bảo mật. Chỉ thu thập/chia sẻ thông tin đã được ẩn hoặc rút gọn phù hợp; không đẩy nguyên Authorization URL vào log công khai hay ticket.

### 14.2. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `/oauth2/authorization/corporate` không redirect | Sai `registrationId`, thiếu registration, base URI đã đổi, security chain không bật login | Kiểm tra `ClientRegistration`, endpoint matcher và `oauth2Login()` |
| Provider báo `invalid_request` | Thiếu/sai `response_type`, `redirect_uri`, scope hoặc extension parameter | Xem metadata provider và các tham số thực tế sau URL-encoding |
| Provider báo `invalid_client` | `client_id` sai hoặc client không được phép dùng flow tương ứng | Kiểm tra registration và cấu hình client tại IdP |
| Provider báo `invalid_scope` | Scope chưa được cho phép hoặc sai định dạng | So yêu cầu scope và chính sách provider |
| `redirect_uri_mismatch` | Callback khác URI provider đăng ký | Đối chiếu URI chính xác, HTTPS, forwarded headers và reverse proxy |
| Callback báo lỗi về `state` | Request/session ban đầu mất, state không khớp hoặc bị sửa | Kiểm tra session cookie, request repository, multi-instance và callback |
| Authorization thành công nhưng token exchange thất bại | Code đã dùng/hết hạn, client auth sai, PKCE verifier sai hoặc redirect URI không khớp | Kiểm tra token request đúng flow, logs được che bí mật |
| OIDC ID Token validation thất bại | Issuer/audience/nonce/chữ ký/thời gian không phù hợp | Kiểm tra metadata issuer, đồng hồ, JWKS và mapping flow |
| Browser quay về HTTP/hostname nội bộ | Ứng dụng sau proxy suy ra `{baseUrl}` sai | Cấu hình trusted forwarded headers hoặc redirect URI công khai cố định |
| Provider bỏ qua `prompt`/`login_hint` | Provider không hỗ trợ hoặc có chính sách riêng | Đối chiếu tài liệu provider, không giả định extension được hiểu |
| URL rất dài hoặc `414 URI Too Long` | Nhiều scopes/claims/custom parameters | Giảm dữ liệu trên URL hoặc dùng cơ chế chuẩn phù hợp khi provider hỗ trợ |
| Gửi OAuth2 request nhưng app không lưu được phiên | Cookie/SameSite/session storage hoặc security proxy sai | Quan sát Set-Cookie, Cookie khi callback và repository |

**Chẩn đoán theo thứ tự:** kiểm tra browser được redirect tới **đúng Authorization Endpoint**, URL có các parameter dự kiến, provider có chấp nhận request, browser có quay về callback kèm state/code, và backend có lấy lại được authorization request đã lưu trước khi chuyển sang token exchange.

### 14.3. Ghi log có chọn lọc

Chỉ ghi các trường hỗ trợ vận hành như registration ID, endpoint hostname, bước xử lý, correlation ID nội bộ và mã lỗi đã làm sạch. Tránh log:

- `client_secret`, authorization code, `code_verifier`, access/refresh token, ID Token.
- Giá trị đầy đủ của `state`, `nonce`, session cookie.
- `login_hint`, `claims` hoặc thông tin người dùng khác khi không cần.

Khi cần debug, sử dụng log có thời hạn và công cụ che dữ liệu nhạy cảm. Việc “bật TRACE toàn bộ HTTP” có thể làm lộ credential nếu không được kiểm soát.

## 15. Bài tập tình huống

### Tình huống 1 — Cần người dùng chọn lại tài khoản mỗi lần đăng nhập

**Yêu cầu:** Ứng dụng OIDC muốn đề nghị provider hiển thị lựa chọn tài khoản.

**Hướng tiếp cận:** Giữ resolver mặc định và thêm `prompt=select_account` qua `additionalParameters`, sau khi xác nhận provider hỗ trợ. Không tự thay `state`, PKCE hay `redirect_uri`.

### Tình huống 2 — API yêu cầu scope `reports.read`

**Yêu cầu:** Ứng dụng đăng nhập nhân viên và sau đó gọi Reports API.

**Hướng tiếp cận:** Cấu hình/request scope `reports.read` nếu Authorization Server cho phép. Sau callback, OAuth2 Client sử dụng **access token được cấp** để gọi API; Reports API với vai trò **Resource Server** xác minh token và quyền thực tế. Chỉ có `scope` trên authorization URL chưa chứng minh token đã được cấp quyền.

### Tình huống 3 — OAuth2 callback có `code` nhưng báo “authorization_request_not_found”

**Yêu cầu:** Hệ thống nhiều instance, browser đã đăng nhập được ở IdP nhưng callback lỗi.

**Hướng tiếp cận:** Kiểm tra authorization request đã được lưu ở đâu và liệu callback có cùng session/instance hoặc shared session store không. Đồng thời kiểm tra cookie, SameSite, domain, path, ingress và state. Không giải quyết bằng cách bỏ qua state checking.

### Tình huống 4 — Muốn gửi PKCE verifier trong authorization URL để provider “đọc được ngay”

**Yêu cầu:** Người triển khai định thêm `code_verifier` vào `additionalParameters`.

**Hướng tiếp cận:** Không làm vậy. Chỉ gửi `code_challenge` + `code_challenge_method` trong authorization request; **`code_verifier` phải được giữ lại và gửi tại Token Endpoint** để provider đối chiếu.

### Tình huống 5 — Nhân viên cần login mới dù đã đăng nhập SSO

**Yêu cầu:** Một nghiệp vụ yêu cầu xác thực lại gần thời điểm thực hiện giao dịch.

**Hướng tiếp cận:** Xem xét `prompt=login` và/hoặc `max_age` của OIDC theo yêu cầu bảo đảm mức độ xác thực, đồng thời kiểm tra kết quả xác thực thực tế và claim phù hợp trong ID Token. Provider có thể có khả năng hoặc chính sách riêng; một query parameter đơn lẻ không thay thế kiểm tra assurance của nghiệp vụ.

## 16. Câu hỏi ôn tập

**1. `OAuth2AuthorizationRequest` khác `ClientRegistration` ở đâu?**

`ClientRegistration` là cấu hình đăng ký client, còn `OAuth2AuthorizationRequest` là yêu cầu cấp quyền cho một lần redirect cụ thể, bao gồm state, URI cuối cùng và metadata của flow.

**2. `additionalParameters` và `attributes` khác nhau thế nào?**

`additionalParameters` là những tham số sẽ được thêm vào authorization URL theo cách Spring dựng request. `attributes` là dữ liệu **nội bộ client**, không tự gửi sang provider, ví dụ dữ liệu cần lưu cho các bước tiếp theo.

**3. Có nên gửi `code_verifier` ở Authorization Endpoint?**

Không. Gửi `code_challenge` và phương thức `S256`; giữ verifier để gửi qua Token Endpoint sau khi nhận code.

**4. `state` và `nonce` có thay thế cho nhau không?**

Không. `state` ràng buộc callback với authorization request; `nonce` phục vụ liên kết ID Token với yêu cầu xác thực OIDC. Chúng có mục đích riêng.

**5. `prompt=login` có phải OAuth2 parameter bắt buộc cho mọi provider không?**

Không. Đây là tham số thuộc OIDC/khả năng provider; không phải tham số bắt buộc cho mọi OAuth2 authorization request.

**6. Tại sao đổi `redirect-uri` có thể khiến đăng nhập lỗi?**

Vì provider kiểm tra redirect URI so với đăng ký; token exchange và các bước của client cũng dựa trên callback nhất quán với authorization request ban đầu.

**7. Nếu chỉ có `code` trên callback, có thể đăng nhập người dùng ngay không?**

Không. Cần xác thực flow qua state và các ràng buộc liên quan, đổi code tại Token Endpoint, rồi xác thực token/ID Token và xây dựng Authentication theo chuẩn.

## 17. Tài liệu tham khảo chính thức

- [Spring Security — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — OAuth 2.0 Login Advanced Configuration (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — OAuth 2.0 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security — OAuth 2.0 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Security API — OAuth2AuthorizationRequest](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/endpoint/OAuth2AuthorizationRequest.html)
- [Spring Security API — DefaultOAuth2AuthorizationRequestResolver](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizationRequestResolver.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests (PAR)](https://www.rfc-editor.org/rfc/rfc9126)
- [OpenID Connect Core 1.0 — Authentication Request](https://openid.net/specs/openid-connect-core-1_0.html)

**Ghi nhớ:** `OAuth2AuthorizationRequest` quyết định **provider nhận được authorization URL nào cho một lần cấp quyền cụ thể**. Những giá trị như `client_id`, `response_type`, `scope`, `state`, `code_challenge` và OIDC `nonce` có vai trò khác nhau. Sử dụng resolver/repository của Spring Security để quản lý đúng request, state và PKCE; bổ sung parameter theo hợp đồng provider và luôn giữ bí mật của token flow ở phía client.

