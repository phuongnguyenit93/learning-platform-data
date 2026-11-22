# 9.3. Liên kết callback với state, nonce và PKCE verifier đã lưu

## 1. Bài toán: callback có thật sự thuộc lần đăng nhập do ứng dụng khởi tạo?

Trong ứng dụng **Spring Security OAuth 2.0/OIDC Client**, quá trình đăng nhập bằng Authorization Code không diễn ra trong một HTTP request duy nhất. Ứng dụng tạo **authorization request**, đưa trình duyệt tới Authorization Server/OpenID Provider, rồi nhận một **callback** chứa authorization code hoặc lỗi. Giữa hai lần browser chạm ứng dụng có thể có nhiều bước: người dùng nhập mật khẩu, thực hiện MFA, chọn tài khoản hoặc chấp thuận quyền.

Câu hỏi bảo mật quan trọng là:

> **Làm sao ứng dụng biết callback vừa nhận là kết quả của đúng authorization request đã khởi tạo, và những token nhận được thuộc đúng giao dịch đó?**

Ba cơ chế bổ trợ lẫn nhau:

1. **`state`:** giúp ứng dụng nối **authorization response trên callback** với **authorization request** đã lưu và chống giả mạo luồng chuyển hướng.
2. **OIDC `nonce`:** nếu ứng dụng đã gửi nonce trong yêu cầu xác thực OIDC, ứng dụng phải liên kết **ID Token** vừa nhận với giá trị nonce của **yêu cầu ban đầu**.
3. **PKCE `code_verifier`:** ứng dụng giữ một bí mật ngẫu nhiên theo *từng authorization request*; Authorization Server chỉ cho đổi authorization code lấy token khi `code_verifier` khớp `code_challenge` đã gắn với code.

Đây là ba lần kiểm tra ở **những vị trí khác nhau** của luồng. Không nên coi `state`, `nonce` và `code_verifier` là ba tên gọi của cùng một chuỗi hoặc nghĩ rằng kiểm tra một giá trị là đủ thay thế hai giá trị kia.

**Phạm vi bài học:** OAuth2 Client dùng Authorization Code, đặc biệt **OAuth2 Login/OIDC Login** trong Spring Security Servlet và WebFlux. Một ứng dụng chỉ dùng `client_credentials` để gọi API không có browser callback, nên không có vòng đời `state`/nonce/PKCE kiểu này.

## 2. Trình tự và vị trí kiểm tra

~~~mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant C as Spring Security OAuth2 Client
    participant R as Request repository / Session
    participant P as Authorization Server / OIDC Provider

    B->>C: GET /oauth2/authorization/corporate
    C->>C: Tạo state, PKCE verifier/challenge, OIDC nonce (nếu dùng)
    C->>R: Lưu OAuth2AuthorizationRequest và dữ liệu correlation
    C-->>B: 302 Location: /authorize?...&state=...&code_challenge=...&nonce=...
    B->>P: GET Authorization Endpoint
    P->>P: Xác thực người dùng / chấp thuận
    P-->>B: 302 redirect_uri?code=...&state=...
    B->>C: GET /login/oauth2/code/corporate?code=...&state=...
    C->>R: Tải request gốc theo session/state; dùng một lần
    R-->>C: Authorization request đã lưu
    C->>C: Kiểm tra state và ngữ cảnh request
    C->>P: POST Token Endpoint: code + code_verifier + client authentication
    P->>P: Kiểm tra verifier với challenge đã nhận
    P-->>C: Access token, ID Token (OIDC), ...
    C->>C: Xác minh ID Token; đối chiếu nonce nếu đã gửi
    C-->>B: Đăng nhập thành công / thiết lập phiên
~~~

Trong một luồng lý tưởng, **không tạo lại những giá trị ngẫu nhiên ở callback**. Ứng dụng cần lấy lại dữ liệu thuộc **chính authorization request trước đó**. Nếu dữ liệu đã lưu bị mất, callback không còn đủ căn cứ để được tin cậy.

| Giá trị | Tạo ở đâu? | Gửi đi ở đâu? | Lưu lại ở đâu? | Ai đối chiếu? |
| --- | --- | --- | --- | --- |
| `state` | OAuth2 Client khi khởi tạo flow | Query của Authorization Request; provider phản hồi lại trên callback | Authorization request repository hoặc cơ chế lưu được bảo vệ | **OAuth2 Client** khi nhận callback |
| `nonce` | OIDC Client khi khởi tạo yêu cầu xác thực có nonce | Authorization Request; provider đưa claim `nonce` vào ID Token theo flow | Dữ liệu của yêu cầu OIDC ban đầu, phía client | **OIDC Client** khi xác minh ID Token |
| `code_verifier` | OAuth2 Client khi áp dụng PKCE | **Token Request**, sau callback; không gửi ở authorization URL | Dữ liệu gắn với authorization request, phía client | **Authorization Server** so với challenge đã lưu |
| `code_challenge` | OAuth2 Client tính từ `code_verifier` | Authorization Request | Authorization Server gắn với authorization code | **Authorization Server** khi nhận verifier |
| Authorization `code` | Authorization Server sau khi người dùng cấp quyền | Callback về `redirect_uri`, sau đó Token Request | Thường xử lý ngắn hạn, dùng một lần | Authorization Server kiểm tra code, client, redirect URI, PKCE |
| ID Token | Provider sau token exchange trong OIDC Code Flow | Token Response qua back-channel | Client xử lý/bảo vệ theo nhu cầu | **OIDC Client** kiểm tra chữ ký, issuer, audience, thời hạn, nonce khi có |

Bảng trên phản ánh các **đối tượng chịu trách nhiệm**. Chi tiết Spring Security lưu request trong session, lưu PKCE verifier như attribute hay dùng repository khác có thể thay đổi theo cấu hình và phiên bản; nguyên tắc bất biến là **dữ liệu cần đối chiếu phải tồn tại từ lúc khởi tạo đến đúng bước xác minh**.

## 3. `OAuth2AuthorizationRequest`: điểm chung để giữ ngữ cảnh

Spring Security dùng `OAuth2AuthorizationRequest` để biểu diễn một authorization request cụ thể:

~~~java
org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest
~~~

Đối tượng này có những thuộc tính quan trọng:

| Getter | Vai trò trong callback/correlation |
| --- | --- |
| `getState()` | `state` ngẫu nhiên được gửi tới provider và cần đối chiếu khi callback |
| `getClientId()` | Client ID mà request ban đầu dùng |
| `getRedirectUri()` | Redirect URI đã chọn cho giao dịch, cần nhất quán khi đổi code |
| `getAuthorizationUri()` | Authorization Endpoint đã dùng để bắt đầu flow |
| `getScopes()` | Scope được yêu cầu |
| `getAdditionalParameters()` | Những tham số thêm vào Authorization Endpoint, như `code_challenge` hoặc `nonce` nếu được cấu hình |
| `getAttributes()` | Metadata **nội bộ** cần cho callback/token exchange, chẳng hạn PKCE verifier tùy cấu hình |
| `getAuthorizationRequestUri()` | URL hoàn chỉnh dùng để redirect browser tới provider |

Lưu ý phân biệt:

- **`additionalParameters`** là tập tham số được đưa vào Authorization Request gửi provider, sau khi Spring Security dựng và mã hóa URL.
- **`attributes`** là dữ liệu nội bộ của `OAuth2AuthorizationRequest`, **không tự động** trở thành query parameters trong URL.
- **`ClientRegistration`** mô tả cấu hình client/protocol đã đăng ký, còn `OAuth2AuthorizationRequest` chứa dữ liệu **riêng cho một lần authorize**, bao gồm giá trị ngẫu nhiên chỉ có ý nghĩa trong giao dịch đó.

Trong quá trình OAuth2 Login, ứng dụng cần giữ `OAuth2AuthorizationRequest` (hoặc tập dữ liệu tương đương được bảo vệ) từ lúc redirect cho đến lúc callback. Nếu customizer hoặc repository tùy chỉnh vô tình làm mất `attributes` chứa PKCE verifier, token exchange có thể không gửi được verifier tương ứng dù `state` vẫn hợp lệ.

## 4. Ràng buộc callback bằng `state`

### 4.1. `state` ngăn điều gì?

Giả sử một ứng dụng có callback:

~~~text
https://portal.example.com/login/oauth2/code/corporate
~~~

Khi đăng nhập, browser quay lại:

~~~http
GET /login/oauth2/code/corporate?code=AUTH_CODE&state=RANDOM_STATE HTTP/1.1
Host: portal.example.com
Cookie: JSESSIONID=...
~~~

Nếu ứng dụng chỉ nhìn thấy `code` và lập tức đổi lấy token mà **không đối chiếu flow ban đầu**, kẻ tấn công có thể tìm cách đưa callback thuộc giao dịch khác vào phiên của nạn nhân. Đây là nhóm nguy cơ **login CSRF**, authorization response injection hoặc login session confusion.

`state` giúp client nhận biết callback có thuộc authorization request đã khởi tạo trong đúng ngữ cảnh hay không:

1. Khi bắt đầu login, client tạo một giá trị **khó đoán**, thích hợp cho correlation.
2. Client lưu authorization request cùng giá trị này trong repository gắn với ngữ cảnh phù hợp, thường là HTTP session của browser.
3. Client gửi `state` trong query của authorization URL.
4. Provider phản hồi lại `state` trên callback theo giao thức.
5. Client tải authorization request gốc và **đối chiếu giá trị state từ callback** với state đã lưu.
6. Nếu không tìm được request tương ứng, state thiếu hoặc không khớp, client phải **từ chối callback** thay vì suy diễn rồi tiếp tục token exchange.

Một chuỗi `state` có format đẹp hoặc dài không tự tạo được bảo mật nếu nó được hard-code hoặc có thể đoán trước. `state` phải được tạo mới cho mỗi giao dịch và cần có đủ entropy.

### 4.2. Vì sao không chỉ kiểm tra định dạng state?

Hai giá trị cùng hợp lệ về kiểu dữ liệu chưa đủ:

~~~text
Session A đã lưu state: HJae2...mK1
Callback nhận state:  hfd99...zQ7
~~~

Dù cả hai đều là chuỗi ngẫu nhiên, callback trên phải bị từ chối vì **không khớp**. Bước kiểm tra quyết định nằm ở việc client có một authorization request ban đầu đáng tin cậy để so sánh.

Ngược lại, nếu chỉ nhìn thấy một state trong callback nhưng không tìm được request gốc, không được cho phép callback bằng cách tạo request mới với state lấy từ URL: làm thế sẽ biến cơ chế correlation thành phép kiểm tra vô nghĩa.

### 4.3. Có thể dùng `state` để nhớ trang quay về sau login không?

Nghiệp vụ thường muốn trở về trang ban đầu, ví dụ `/orders/123`. **Không nên dùng state ngẫu nhiên như một URL redirect do client bên ngoài cung cấp.**

Cách thiết kế phổ biến là giữ **return URL đã kiểm tra** trong session hoặc một storage được bảo vệ và liên kết với giao dịch. Sau khi callback hợp lệ, dùng thông tin nội bộ đó để chuyển người dùng về một đường dẫn được phép.

Nếu ứng dụng dùng dữ liệu có cấu trúc trong state, cần thiết kế bảo vệ tính toàn vẹn, chống replay, ràng buộc phiên/tenant và xử lý open redirect đúng cách. Không tự chế một cơ chế state thay thế mặc định nếu không có yêu cầu kiến trúc rõ ràng.

## 5. PKCE: giữ `code_verifier` để đổi đúng authorization code

### 5.1. PKCE bổ sung cơ chế ràng buộc nào?

**Proof Key for Code Exchange (PKCE, RFC 7636)** khiến một authorization code chỉ có thể đổi thành token khi bên đổi code chứng minh mình biết `code_verifier` đã dùng để tạo `code_challenge` ngay từ đầu.

Với phương thức `S256`:

~~~text
code_verifier  = giá trị ngẫu nhiên theo từng giao dịch, phù hợp yêu cầu RFC 7636
code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
~~~

Ví dụ được nêu trong RFC 7636:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge:
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Trong **Authorization Request**:

~~~http
GET /authorize?response_type=code&client_id=portal-web&state=...&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256 HTTP/1.1
Host: idp.example.com
~~~

Trong **Token Request**, sau callback:

~~~http
POST /token HTTP/1.1
Host: idp.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=AUTH_CODE&redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcorporate&code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
~~~

HTTP ở trên chỉ minh họa body của grant; **client authentication** cũng phải được áp dụng theo cấu hình client và hợp đồng với Authorization Server. Với confidential client, có thể cần `client_secret_basic`, `client_secret_post`, private-key JWT hoặc phương thức khác. Không nhúng secret vào Authorization URL.

Cần nhớ:

- **`code_challenge` xuất hiện ở Authorization Endpoint**, được thiết kế để công bố.
- **`code_verifier` không được gửi trong Authorization Request**; client cần giữ đến khi thực hiện Token Request.
- **Authorization Server mới là bên xác minh PKCE** khi đổi code. Client không tự chứng minh verifier đúng chỉ bằng cách so sánh local với challenge; một token response thành công từ server tuân thủ giao thức phản ánh việc kiểm tra của server.
- Cả verifier và challenge phải **gắn với đúng giao dịch**. Tạo verifier mới ở callback sẽ không khớp challenge ban đầu.
- `S256` là lựa chọn được ưu tiên; không tự hạ xuống `plain` để vượt lỗi provider khi chưa hiểu rủi ro và khả năng tương thích.

### 5.2. PKCE có thay `state` được không?

Không nên loại bỏ `state` khi đã dùng PKCE chỉ vì cả hai góp phần bảo vệ authorization flow.

- **`state`** liên kết authorization response trên browser callback với yêu cầu đã lưu và phiên/ngữ cảnh khởi tạo.
- **PKCE** ràng buộc authorization code với verifier do client giữ, làm giảm hiệu quả của việc đánh cắp/chèn code.
- Hai cơ chế được kiểm tra ở **các bước khác nhau** và hỗ trợ phòng vệ nhiều lớp.

Có những profile giao thức hoặc cơ chế bảo vệ thay thế được chuẩn hóa, nhưng trong các ứng dụng Spring Security OAuth2 Login phổ biến, giữ đúng behavior an toàn mặc định là cách triển khai hợp lý.

### 5.3. Khi nào Spring Security thêm PKCE?

Trong các phiên bản Spring Security hiện đại, resolver mặc định có thể tự áp dụng PKCE với một số client, đặc biệt **public client** cấu hình authentication method `none`. Đối với một confidential client mà bạn muốn bật PKCE rõ ràng và provider hỗ trợ, có thể tùy biến resolver.

Ví dụ Servlet:

~~~java
@Configuration
class LoginSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
            registrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(builder ->
            OAuth2AuthorizationRequestCustomizers.withPkce().accept(builder));

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
~~~

Các kiểu trong ví dụ thuộc Spring Security Servlet: `HttpSecurity`, `SecurityFilterChain`, `ClientRegistrationRepository`, `DefaultOAuth2AuthorizationRequestResolver` và `OAuth2AuthorizationRequestCustomizers`. `@Bean`/`@Configuration` đến từ Spring. Phần `import` được lược bỏ để tập trung vào luồng.

Customizer `withPkce()` quản lý cách thêm challenge/method và dữ liệu verifier nội bộ theo hợp đồng của Spring Security. Khi dùng nó, **không tự tạo một verifier khác trong code xử lý callback**. Nếu provider không hỗ trợ PKCE hoặc yêu cầu một chính sách riêng, cần quyết định dựa trên metadata/tài liệu IdP.

## 6. OIDC `nonce`: liên kết ID Token với yêu cầu xác thực

OIDC mở rộng OAuth2 để chuẩn hóa xác thực danh tính. Trong OIDC Code Flow, sau khi client đổi authorization code thành công, Token Endpoint có thể trả **ID Token** cùng access token.

Giả sử Authorization Request gửi:

~~~text
response_type=code
scope=openid profile
state=RANDOM_STATE
nonce=RANDOM_NONCE
~~~

Provider phát ID Token chứa claim tương ứng:

~~~json
{
  "iss": "https://idp.example.com/realms/employees",
  "sub": "248289761001",
  "aud": "portal-web",
  "exp": 1910000000,
  "iat": 1909999700,
  "nonce": "RANDOM_NONCE"
}
~~~

Payload minh họa cho các claim; **không sử dụng thời gian mẫu để kiểm thử token thật**.

OIDC Client phải xác minh ID Token theo chính sách chuẩn, gồm **chữ ký/khóa được tin cậy, issuer, audience, thời hạn**, và **nonce** nếu request đã gửi `nonce`. Nên áp dụng thêm những kiểm tra như `azp` hoặc chính sách khác khi profile/token yêu cầu.

Điểm phân biệt:

- `state` nằm trong **authorization response trên callback**.
- `nonce` nằm trong **ID Token** được phát hành sau token exchange, khi nonce đã được gửi.
- ID Token có thể là JWT, nhưng **việc đọc JSON payload không đồng nghĩa token hợp lệ**.
- `nonce` không thay thế kiểm tra chữ ký, `iss`, `aud`, `exp` hoặc các yêu cầu của OIDC.
- Không sử dụng **access token** như ID Token chỉ vì access token cũng là JWT.

### 6.1. Nonce được lưu và đối chiếu như thế nào?

Ở giai đoạn authorization request, client cần giữ đủ dữ liệu để nhận biết **nonce gốc của lần đăng nhập**. Ở giai đoạn callback, sau khi đổi code lấy token và thực hiện các kiểm tra ID Token phù hợp, client đối chiếu nonce từ token với giá trị mong đợi.

Nếu customizer thêm `nonce` vào Authorization Request, nó cũng phải bảo đảm thành phần OIDC token validation **được cung cấp giá trị mong đợi tương ứng**. Chỉ viết:

~~~java
builder.additionalParameters(params ->
    params.put("nonce", "MY_NONCE"));
~~~

**không chứng minh** toàn bộ vòng đời nonce đã được tích hợp an toàn: nếu không lưu/đối chiếu nonce tương ứng, query parameter đó chỉ là dữ liệu được gửi đi mà không có cơ chế correlation đầy đủ.

Một số triển khai có thể biến đổi cách biểu diễn nonce khi gửi/giữ nội bộ; người phát triển nên sử dụng **khả năng chuẩn của Spring Security/IdP** hoặc cơ chế rõ ràng, nhất quán thay vì giả định raw nonce luôn nằm ở một key attributes tự đặt.

### 6.2. Nonce có bắt buộc trong mọi OAuth2 flow?

Không. `nonce` là khái niệm của **OIDC authentication request**, không phải tham số bắt buộc cho mọi OAuth2 Authorization Code request. Trong **OIDC Authorization Code Flow**, nonce có thể là tùy chọn theo trường hợp chuẩn; khi client đã gửi nonce, ID Token phải mang nonce thích hợp và client phải kiểm tra theo yêu cầu của OIDC.

Trong các flow OIDC khác, quy định về nonce có thể khác. Bài học này tập trung vào **Authorization Code callback** của Spring Security OAuth2/OIDC Client, không giả định mọi flow đều có cùng bộ tham số.

## 7. Nơi lưu dữ liệu correlation trong Spring Security Servlet

### 7.1. Các thành phần tham gia

Một ứng dụng Servlet dùng `oauth2Login()` thường phối hợp:

| Thành phần | Công việc |
| --- | --- |
| `ClientRegistrationRepository` | Tra cứu cấu hình provider/client theo `registrationId` |
| `OAuth2AuthorizationRequestRedirectFilter` | Xử lý endpoint bắt đầu authorize và phát redirect |
| `OAuth2AuthorizationRequestResolver` | Tạo request, bao gồm `state` và các tham số cần thiết |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Lưu/lấy/xóa authorization request trong giai đoạn chuyển hướng |
| `HttpSessionOAuth2AuthorizationRequestRepository` | Triển khai lưu request qua HTTP session phổ biến mặc định |
| `OAuth2LoginAuthenticationFilter` | Tiếp nhận callback, phối hợp xác thực authorization response |
| OAuth2/OIDC authentication provider, token response client | Đổi code lấy token, hoàn thành xác thực/validation |
| `SecurityContext` và session storage | Giữ Authentication sau khi login thành công theo kiến trúc web app |

Có ba loại dữ liệu thường bị nhầm:

1. **`ClientRegistration`:** cấu hình tương đối tĩnh của client, không thể thay thế authorization request mỗi lần login.
2. **`OAuth2AuthorizationRequest`:** trạng thái tạm thời của giao dịch đang chờ callback; cần dữ liệu `state`, PKCE và OIDC nếu áp dụng.
3. **`OAuth2AuthorizedClient`:** dữ liệu **sau khi** được cấp token, gắn registration với access token/refresh token. Nó không phải nơi ứng dụng lấy `state` gốc để xác thực callback trước token exchange.

### 7.2. Mặc định lưu request bằng HTTP session

Khi filter bắt đầu authorization, Spring Security có thể lưu `OAuth2AuthorizationRequest` vào `HttpSessionOAuth2AuthorizationRequestRepository`. Request được truy xuất lại khi callback về với `state` phù hợp.

Ví dụ cấu hình minh họa để làm rõ dependency:

~~~java
@Configuration
class OAuth2SessionCorrelationConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        var requestRepository =
            new HttpSessionOAuth2AuthorizationRequestRepository();

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestRepository(requestRepository)));

        return http.build();
    }
}
~~~

Đoạn này chỉ cấu hình tường minh repository session tương đương với lựa chọn mặc định thông dụng; **không cần tự khai báo** trong mọi ứng dụng. Giá trị chính của nó là chỉ rõ **request được lưu ở đâu giữa hai HTTP lượt**.

Không lưu PKCE verifier hay raw nonce trong một biến `static` dùng chung toàn ứng dụng. Khi nhiều người đăng nhập đồng thời, giá trị chung sẽ bị ghi đè và có thể gây liên kết nhầm giao dịch. Cũng không tự đặt chúng vào một cookie có thể sửa tùy ý mà không có bảo vệ tính toàn vẹn/bí mật phù hợp.

### 7.3. Giữa hai lượt browser, session phải được nối lại

Ví dụ:

~~~text
Lượt 1: GET /oauth2/authorization/corporate
    Browser nhận Set-Cookie: JSESSIONID=abc...; Secure; HttpOnly; ...

Lượt 2: GET /login/oauth2/code/corporate?code=...&state=...
    Browser gửi Cookie: JSESSIONID=abc...

Backend dùng session tương ứng để tìm authorization request gốc.
~~~

Các lỗi phổ biến khi session không được nối lại:

- Cookie `Secure` bị ảnh hưởng do HTTPS termination hoặc cấu hình public scheme sai.
- `SameSite` không phù hợp với cách chuyển hướng/HTTP method của callback; ví dụ form-post callback có hành vi cookie khác với top-level GET.
- Cookie domain/path không bao phủ callback.
- Reverse proxy hoặc load balancer chuyển callback tới instance không thể truy xuất session đã lưu.
- Session hết hạn trong lúc người dùng nhập mật khẩu/MFA.
- Browser xóa, chặn hoặc tách cookie vì chính sách trình duyệt, profile hay partitioning.
- Tạo authorization request mới giữa chừng làm dữ liệu đăng nhập đang chờ bị thay thế theo đặc điểm repository.

Một số ứng dụng lưu session trong **Spring Session + Redis** hoặc storage chia sẻ để nhiều instance cùng đọc được. Trong cách triển khai đó, cần bảo vệ session và cấu hình thời hạn tương thích với vòng đời login. Một session chung cũng phải được tách biệt theo người dùng/browser; không dùng cùng namespace/khóa lưu request cho tất cả phiên.

### 7.4. Nhiều tab đăng nhập cùng lúc

Giả sử một người mở hai tab và khởi tạo hai flow:

~~~text
Tab A → state=A1, verifier=VA, nonce=NA
Tab B → state=B2, verifier=VB, nonce=NB
~~~

Nếu repository chỉ giữ **một authorization request đang chờ cho một session**, request B có thể thay thế request A. Khi callback A tới, Spring không còn request gốc và đăng nhập thất bại.

Điều này khác với tấn công: state mismatch có thể phát sinh do concurrency hợp lệ. Khi cần hỗ trợ nhiều flow đồng thời, repository tùy chỉnh phải quản lý nhiều entry bằng **khóa state khó đoán** và ràng buộc với session/tenant thích hợp, áp dụng TTL và bảo đảm xóa đúng entry. Không chữa lỗi bằng cách bỏ đối chiếu state.

## 8. Nơi lưu dữ liệu correlation trong WebFlux

WebFlux sử dụng các interface/reactive filter tương ứng:

| Servlet | WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `OAuth2AuthorizationRequestRedirectFilter` | `OAuth2AuthorizationRequestRedirectWebFilter` |
| `OAuth2AuthorizationRequestResolver` | `ServerOAuth2AuthorizationRequestResolver` |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` |
| `HttpSessionOAuth2AuthorizationRequestRepository` | `WebSessionOAuth2ServerAuthorizationRequestRepository` |

Ví dụ WebFlux cơ bản:

~~~java
@Configuration
@EnableWebFluxSecurity
class ReactiveLoginSecurity {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/static/**").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Trong WebFlux, authorization request có thể được lưu trong **WebSession** thông qua `WebSessionOAuth2ServerAuthorizationRequestRepository` hoặc một implementation do ứng dụng cung cấp. Vẫn phải bảo đảm **cùng giao dịch từ authorization redirect đến callback**.

Nếu tùy biến repository WebFlux, phải dùng các API xử lý `ServerWebExchange` và trả `Mono` thích hợp. Tránh code blocking (`.block()`, JDBC đồng bộ không được cô lập) trên reactive event loop.

WebFlux và Servlet khác kiểu filter và repository, nhưng ý nghĩa bảo mật giống nhau: **từ callback phải tìm được request gốc; từ request gốc phải lấy đúng state và dữ liệu để hoàn tất token/ID Token validation**.

## 9. Từng bước trong callback phải làm gì?

Từ góc nhìn ứng dụng, callback có thể đi theo thứ tự logic sau. Spring Security thực hiện các bước trong các filter/provider tương ứng; không cần viết tất cả bằng tay nếu dùng mặc định.

### Bước 1 — Nhận authorization response

Thường là một trong hai kiểu:

~~~http
GET /login/oauth2/code/corporate?code=AUTH_CODE&state=S123 HTTP/1.1
~~~

hoặc:

~~~http
GET /login/oauth2/code/corporate?error=access_denied&state=S123 HTTP/1.1
~~~

`code` là credential ngắn hạn được dùng một lần để xin token. Không ghi code đầy đủ ra log.

### Bước 2 — Tìm authorization request đã lưu

Dựa trên session và `state`/ngữ cảnh callback theo cách repository thực thi, Spring Security phải tìm được `OAuth2AuthorizationRequest` ban đầu. Nếu thiếu, có thể xuất hiện lỗi như `authorization_request_not_found` hoặc lỗi correlation tương đương theo cấu hình/phiên bản.

**Không** chấp nhận callback chỉ vì query có `code` hoặc vì client registration tồn tại. `ClientRegistration` là cấu hình tĩnh, không chứng minh browser đã khởi tạo giao dịch.

### Bước 3 — Đối chiếu `state` và xác định client/provider của giao dịch

Spring Security cần ràng buộc phản hồi vào **đúng request ban đầu**, không sử dụng một registration tùy ý chỉ dựa trên dữ liệu không tin cậy do callback cung cấp. Nếu state không khớp hoặc request thiếu, từ chối callback.

Các triển khai phức tạp dùng nhiều Authorization Server/issuer còn phải bảo vệ trước nguy cơ **authorization-server mix-up**: response phải được gắn với provider/client mà request đã định hướng, và khi giao thức/cấu hình yêu cầu cần kiểm tra issuer của authorization response hoặc cách ràng buộc tương đương. Đây là lớp kiểm tra bổ sung, không thay thế state.

### Bước 4 — Token exchange với PKCE verifier đã lưu

Khi callback hợp lệ về mặt request correlation, backend thực hiện Token Request tới Authorization Server tương ứng. Với PKCE, request phải gửi `code_verifier` **đã được tạo ở bước khởi tạo**, không tự sinh verifier mới.

Về cơ bản:

~~~text
POST {token-uri}
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
code=<code-from-callback>
redirect_uri=<same-redirect-uri-when-required>
code_verifier=<original-verifier>
+ client authentication theo client registration
~~~

Provider kiểm tra authorization code, client, redirect URI, hiệu lực/một lần sử dụng, PKCE khi có; thất bại có thể được biểu diễn bằng lỗi như `invalid_grant` hoặc một mã lỗi cụ thể khác.

### Bước 5 — Xác minh token, gồm OIDC nonce nếu đã gửi

Nếu là OIDC Login, Spring Security xác minh ID Token được phát hành bởi đúng provider và cho đúng client. Nếu authorization request có `nonce`, giá trị kỳ vọng phải được đối chiếu theo OIDC; mismatch cần dẫn tới thất bại xác thực.

Đừng dùng `nonce` để kiểm tra access token của API: `nonce` thuộc hợp đồng OIDC ID Token, trong khi access token được Resource Server xác minh issuer/audience/scope/chữ ký hoặc introspection theo cách thích hợp.

### Bước 6 — Hoàn tất xác thực và xử lý dữ liệu một lần

Khi các bước cần thiết thành công, ứng dụng thiết lập `Authentication` và có thể lưu token trong `OAuth2AuthorizedClient`. Dữ liệu authorization request đang chờ không còn nên được tái sử dụng như một giao dịch chưa hoàn tất.

Nếu thất bại, ứng dụng cần trả lỗi/redirect lỗi theo cấu hình và tránh để request đã xử lý có thể được chấp nhận lại không kiểm soát. Cơ chế xóa request phải tuân theo lifecycle của repository và yêu cầu hỗ trợ retry theo thiết kế ứng dụng.

## 10. Cấu hình OIDC Login Spring Boot làm cơ sở

Ví dụ một ứng dụng Spring MVC/Servlet:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corp-oidc
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corp-oidc:
            issuer-uri: https://idp.example.com/realms/employees
~~~

~~~java
@Configuration
class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login-error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Khởi tạo login tại:

~~~text
https://portal.example.com/oauth2/authorization/corporate
~~~

Callback mặc định của Spring Security OAuth2 Login thường là:

~~~text
https://portal.example.com/login/oauth2/code/corporate
~~~

Callback phải trùng URI được đăng ký với IdP. Khi dùng `{baseUrl}` sau reverse proxy, hệ thống cần nhận biết external hostname và HTTPS scheme theo cách an toàn; browser phải gửi lại session cookie đúng domain/path.

Spring Security xử lý việc tạo/lưu authorization request và đối chiếu callback theo mặc định. Ứng dụng **không cần tự viết một controller `/login/oauth2/code/corporate` chỉ để đọc `state` hoặc `code`**. Việc chặn callback bằng custom controller dễ bỏ sót state, PKCE và OIDC token validation.

## 11. Tùy biến authorization request nhưng vẫn giữ correlation

### 11.1. Thêm một tham số provider mà không làm mất PKCE/state

Ví dụ cần thêm `prompt=select_account` cho OIDC provider và bật PKCE có chủ đích:

~~~java
@Configuration
class CustomLoginSecurity {

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            ClientRegistrationRepository clientRegistrations) throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
            clientRegistrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(builder -> {
            OAuth2AuthorizationRequestCustomizers.withPkce().accept(builder);

            builder.additionalParameters(parameters ->
                parameters.put("prompt", "select_account"));
        });

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
~~~

`DefaultOAuth2AuthorizationRequestResolver` vẫn xây dựng flow, gồm state, client registration và các tham số cơ bản. PKCE customizer để Spring Security lưu verifier theo cơ chế mà token exchange sử dụng. `prompt` là tham số mở rộng dành cho OIDC provider có hỗ trợ.

**Không làm các việc sau trong customizer:**

- Ghi đè `state` bằng một hằng số hoặc giá trị lấy trực tiếp từ request browser.
- Thêm `code_verifier` vào query authorization URL thay cho `code_challenge`.
- Làm mất `attributes` chứa metadata nội bộ khi tạo lại `OAuth2AuthorizationRequest`.
- Tự ý sửa `redirect_uri` sang một URI client cung cấp hoặc provider khác.
- Thay đổi `nonce` mà không đảm bảo lưu và đối chiếu ở bước xác minh ID Token.

### 11.2. Vì sao `attributes` dễ bị bỏ quên khi copy request?

Một developer có thể lấy request mặc định rồi dựng request khác chỉ với `clientId`, `redirectUri`, `scopes` và `state`. URL chuyển hướng nhìn có vẻ đúng, nhưng dữ liệu nội bộ của request gốc có thể đã mất: ví dụ PKCE verifier không còn cho Token Request.

Nếu thực sự cần copy/sửa request, hãy hiểu cách builder bảo toàn dữ liệu:

~~~java
OAuth2AuthorizationRequest updated =
    OAuth2AuthorizationRequest.from(original)
        .additionalParameters(params -> params.put("prompt", "login"))
        .build();
~~~

Đoạn này minh họa sửa từ **`original`** để giữ các trường gốc của request, thay vì dựng một request hoàn toàn mới thiếu những thuộc tính khác. Đối tượng `original` phải xuất phát từ luồng tạo request hợp lệ của Spring Security. Không dùng mẫu này như một cách tự tạo callback/request khi `state` không khớp.

### 11.3. Tùy biến repository: trách nhiệm không thể bỏ qua

Khi thay `HttpSessionOAuth2AuthorizationRequestRepository` bằng storage riêng, cần bảo đảm:

- Lưu **đầy đủ đối tượng/request correlation** cần cho state, PKCE, OIDC.
- Ràng buộc record với **đúng browser session**, người khởi tạo hoặc một cơ chế an toàn tương đương.
- Không để người dùng khác/tenant khác đọc hoặc hoàn tất một flow.
- `state` là khóa ngẫu nhiên không dễ đoán; có TTL và cơ chế xóa/consume dùng một lần.
- Có chiến lược cho **nhiều tab** hoặc nhiều login đang chờ.
- Bảo vệ dữ liệu nhạy cảm, đặc biệt PKCE verifier và mọi metadata nội bộ có tính bảo mật.
- Hoạt động đúng trong triển khai nhiều instance và khi session bị rotate/expire.
- Không lưu token/credential trong browser cookie hoặc URL nếu chưa có cơ chế mã hóa, xác thực, chống replay và đánh giá rủi ro phù hợp.

**Repository stateless dựa trên cookie:** có thể triển khai trong một số kiến trúc, nhưng không được coi cookie là an toàn chỉ vì có `HttpOnly`. Nếu cookie chứa verifier hoặc dữ liệu correlation, cần bảo vệ toàn vẹn, độ bí mật khi cần, TTL, scope, replay, SameSite và giới hạn kích thước cookie. Một storage phía server thường dễ quản lý hơn trong ứng dụng web truyền thống.

## 12. Các lỗi correlation phổ biến và cách xác định nguyên nhân

| Triệu chứng | Bước nghi ngờ | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- | --- |
| `authorization_request_not_found` | Tải request ban đầu | Session mất, callback khác instance, request đã hết hạn/xóa, repository không giữ request | Cookie, session store, instance routing, TTL, đường callback |
| `invalid_state_parameter` hoặc state mismatch | Đối chiếu state | Callback không thuộc flow, session bị ghi đè, mở nhiều tab, request bị sửa | Đối chiếu flow ID đã ẩn, session và số lần khởi tạo login |
| Callback chỉ có `error=access_denied` | Authorization Endpoint | Người dùng từ chối consent hoặc policy IdP không cho phép | Kiểm tra error response theo giao thức, không cố token exchange |
| Token Endpoint trả `invalid_grant` | Code/token request | Code hết hạn/đã dùng, redirect URI khác, PKCE sai, clock skew | Kiểm tra cùng request gốc, verifier, code lifecycle |
| Provider báo `invalid_request` khi có PKCE | Authorization Endpoint | Provider không hỗ trợ/chưa cho phép phương thức challenge hoặc parameter sai | Kiểm tra cấu hình IdP và PKCE customization |
| ID Token xác thực thất bại vì nonce | Xác minh OIDC | Nonce không khớp, request gốc mất, custom nonce nhưng không lưu/kiểm tra đúng | Kiểm tra luồng tạo/lưu nonce và validator |
| Login thành công nhưng sai tài khoản mong đợi | Session/login binding | Không ràng buộc đúng state/provider, login CSRF hoặc nhầm flow; cũng có thể người dùng chọn tài khoản khác | Kiểm tra correlation và danh tính đã xác minh từ ID Token |
| Chỉ lỗi sau khi triển khai nhiều instance | Session/storage | Dữ liệu request chỉ nằm trong memory một instance | Session store chung/thiết kế routing phù hợp |
| Chỉ lỗi sau khi đổi reverse proxy | Cookie/redirect | Sai hostname/scheme/path, SameSite/Secure, headers, callback URL | Quan sát browser redirect và cookie theo tuyến mới |
| Thỉnh thoảng lỗi khi mở nhiều tab SSO | Concurrency | Repository chỉ giữ một pending request hoặc request bị thay thế | Thiết kế lưu nhiều state an toàn theo session nếu cần |
| Request có `code_challenge` nhưng token exchange thiếu `code_verifier` | Request attributes/token response client | Customizer/copy request làm mất verifier hoặc token client không truyền nó | Kiểm tra builder, authorization-request storage, token response client |
| `401`/`403` khi gọi API sau login | Giai đoạn khác sau callback | Access token không hợp lệ/thiếu scope hoặc API từ chối quyền | Kiểm tra token dùng cho Resource Server, không sửa state tùy tiện |

Một flow có thể thất bại vì vấn đề **ngữ cảnh lưu trữ** dù provider đang hoạt động tốt. Vì vậy phải phân biệt **request correlation** với **token issuance** và **API authorization**.

### 12.1. Tách lỗi hợp lệ khỏi hành vi tấn công

State mismatch là tín hiệu cần từ chối callback, nhưng không đồng nghĩa mọi sự kiện đều là tấn công. Nó có thể phát sinh bởi:

- Browser back/forward hoặc đăng nhập lặp.
- Hai tab cùng khởi động SSO.
- Session expiration khi nhập MFA quá lâu.
- Cookie/session không được giữ khi callback qua proxy.
- Cấu hình URI khởi tạo/callback không nhất quán.
- Request đã được consume ở callback trước đó rồi bị replay.

Dù nguyên nhân là gì, **hành vi an toàn vẫn là từ chối callback không có request hợp lệ**, sau đó cung cấp cách khởi tạo lại login. Không bỏ validation chỉ để giảm lỗi cho người dùng.

### 12.2. Vì sao retry callback cũ không phải cách khôi phục?

Authorization code thường **ngắn hạn và chỉ dùng một lần**; authorization request trong repository cũng có vòng đời sử dụng một lần. Refresh lại URL callback có thể đưa đến `invalid_grant` hoặc missing authorization request, ngay cả khi lần đầu đã xử lý.

Khi cần thử lại, ứng dụng nên **khởi tạo authorization request mới** bằng endpoint bắt đầu login. Không tái sử dụng code, state hay PKCE verifier từ flow cũ.

## 13. Quan sát và kiểm thử các ràng buộc mà không làm lộ bí mật

### 13.1. Quan sát đúng một flow trong môi trường phát triển

Có thể kiểm tra rằng điểm bắt đầu login trả `302 Location` hợp lệ:

~~~bash
curl -i --max-redirs 0 \
  http://localhost:8080/oauth2/authorization/corporate
~~~

Kết quả có thể gồm:

~~~http
HTTP/1.1 302 Found
Location: https://idp.example.com/oauth2/authorize?response_type=code&client_id=portal-web&state=<redacted>&code_challenge=<redacted>&code_challenge_method=S256
Set-Cookie: JSESSIONID=<redacted>; HttpOnly
~~~

Đây là **minh họa đã che dữ liệu**, không phải request có thể gửi nguyên văn đến provider. Tùy thiết kế, ứng dụng có thể không gửi `nonce` hoặc đã có cơ chế cookie/session khác. Bước kế tiếp cần kiểm tra callback sử dụng cùng phiên và liệu framework có tải được request đã lưu.

Không ghi log hoặc chia sẻ nguyên vẹn `code`, `state`, `nonce`, `code_verifier`, token, session cookie hoặc client secret.

### 13.2. Các ca cần kiểm thử ở tầng bảo mật

| Ca kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| Authorization request và callback hợp lệ cùng session/state | Framework tiếp tục token exchange và xác thực |
| Callback không có state khi flow yêu cầu state | Bị từ chối |
| State từ flow A gửi trong session của flow B | Bị từ chối |
| Callback có state giả/ngẫu nhiên, không lưu | Bị từ chối |
| Callback được gửi lại sau khi xử lý | Không tạo lại xác thực nhờ code/request đã dùng |
| Thử dùng code của flow A với verifier của flow B | Token Endpoint từ chối |
| PKCE challenge bị sửa, verifier gốc giữ nguyên | Token Endpoint từ chối |
| ID Token nonce không khớp khi request đã gửi nonce | OIDC Client từ chối xác thực |
| ID Token hết hạn, issuer/audience sai hoặc chữ ký không hợp lệ | OIDC Client từ chối xác thực |
| Session bị xóa trước callback | Không chấp nhận callback vì thiếu request tương ứng |
| Nhiều tab login trong cùng session | Hoạt động theo thiết kế repository; nếu không hỗ trợ nhiều pending request thì flow mất ngữ cảnh phải bị từ chối an toàn |
| Token request thiếu code verifier khi authorization request có PKCE | Token Endpoint từ chối |
| Cấu hình callback đổi giữa các bước | Bị phát hiện hoặc từ chối theo ràng buộc redirect URI/client |

Không nên khẳng định “test đã pass” chỉ vì login thành công một lần. Các ca phủ định quan trọng vì chúng xác minh rằng callback sai correlation **bị chặn đúng chỗ**.

### 13.3. Ghi nhận telemetry theo giao dịch

Nếu cần quan sát sự cố, hãy log các metadata không nhạy cảm:

- Mốc `authorization_started` và `callback_received` kèm **correlation ID nội bộ tách biệt với state**.
- `registrationId`, loại grant, endpoint hostname (không ghi URL query đầy đủ).
- Tên bước thất bại: tải request, state comparison, token exchange, ID Token validation.
- Nguyên nhân đã làm sạch: session expired, provider error, timeout, không tìm thấy request.

Trong production, hạn chế bật DEBUG/TRACE cho toàn HTTP stack nếu có nguy cơ log header `Authorization` hoặc query/body chứa token, code, verifier và cookie. Việc che dữ liệu nên áp dụng cả ở reverse proxy, gateway và APM.

## 14. Những hiểu nhầm cần tránh

**“Có `state` trong callback nên callback hợp lệ.”** Không. Phải so sánh với state của authorization request mà client đã khởi tạo và lưu trong đúng ngữ cảnh.

**“PKCE verifier và challenge là cùng một giá trị.”** Không. Với `S256`, challenge là giá trị dẫn xuất. Verifier là bí mật client giữ để gửi trong token request.

**“Dùng PKCE rồi có thể lưu verifier trong authorization URL.”** Không. Làm thế khiến verifier bị lộ trên kênh front-channel, làm mất mục tiêu bảo vệ của PKCE.

**“Nonce có thể thay cho state vì cũng là số ngẫu nhiên.”** Không. Nonce dùng để ràng buộc **ID Token** ở bước xác minh OIDC, còn state dùng để ràng buộc **authorization response** trước token exchange.

**“Mỗi lần callback chỉ cần lấy một verifier mới và tính challenge lại.”** Không. Authorization Server đã ràng buộc code với challenge trước đó; cần gửi **verifier gốc**.

**“Thêm nonce query parameter bằng tay thì Spring Security chắc chắn đã kiểm tra.”** Không thể kết luận như vậy. Phải bảo đảm nonce gốc được lưu/ánh xạ tới đúng quy trình OIDC validation trong implementation thực tế.

**“ClientRegistration đã đủ để xử lý callback.”** Không. ClientRegistration là cấu hình dài hạn; callback còn cần authorization request riêng của giao dịch và dữ liệu correlation.

**“Callback trả `code` nghĩa là user đã đăng nhập thành công.”** Không. Cần state matching, token exchange thành công, OIDC ID Token validation khi áp dụng và các kiểm tra bắt buộc khác.

**“Mất session thì có thể bỏ kiểm tra state để người dùng đỡ phải login lại.”** Không. Session/authorization request đã mất thì cần khởi tạo flow mới, không giảm độ bảo vệ chỉ để xử lý lỗi vận hành.

## 15. Tình huống thực hành

### Tình huống A — Mở hai tab đăng nhập

Người dùng bấm SSO trong tab A, sau đó mở tab B và bấm SSO lần nữa. Callback tab A báo missing authorization request.

**Phân tích:** Hai flow có state, verifier và có thể nonce khác nhau. Nếu repository chỉ lưu một pending request trên một session, request B có thể thay request A. Cần quyết định có hỗ trợ đồng thời nhiều login flow hay không; nếu có, triển khai storage cho từng state, TTL và consume một lần an toàn. Không chấp nhận state không khớp.

### Tình huống B — Token Endpoint trả `invalid_grant` dù state đúng

Callback được khớp đúng state nhưng đổi authorization code thất bại. Developer đã tự tái tạo `OAuth2AuthorizationRequest`, chỉ copy state và client ID, bỏ qua `attributes`.

**Phân tích:** PKCE verifier gốc có thể đã bị mất. Token request thiếu verifier hoặc gửi sai verifier nên Authorization Server từ chối. Nên giữ request gốc và dùng customizer chuẩn để bổ sung tham số thay vì dựng lại đối tượng, đồng thời kiểm tra redirect URI và thời hạn code.

### Tình huống C — ID Token có chữ ký hợp lệ nhưng nonce không khớp

IdP trả ID Token đã ký đúng, issuer/audience đúng, nhưng claim `nonce` không trùng nonce gắn với authorization request.

**Phân tích:** Nếu client đã gửi nonce, **phải từ chối ID Token/đăng nhập**. Chữ ký chỉ chứng minh token đến từ issuer tin cậy; nonce mismatch chỉ ra token không liên kết đúng với yêu cầu xác thực mong đợi hoặc flow đã bị xử lý sai.

### Tình huống D — Triển khai sau ingress, callback mất session

Local login chạy được, production đôi lúc callback báo missing authorization request. Browser được redirect về hostname công khai, nhưng cookie session không được gửi tới callback.

**Phân tích:** Kiểm tra `Secure`, `SameSite`, domain/path cookie, forwarded headers, redirect URI, HTTPS termination, session store và routing nhiều instance. Giải pháp là sửa cơ chế duy trì phiên/flow, **không bỏ state matching**.

### Tình huống E — Một service chỉ dùng `client_credentials`

Backend chạy job mỗi đêm để xin token service và gọi Reporting API. Developer muốn thêm `state`, `nonce`, `code_verifier` vào cấu hình để “bảo vệ hơn”.

**Phân tích:** `client_credentials` không có browser authorization redirect/callback kiểu authorization code. Ba giá trị correlation của bài này không thuộc flow đó. Cần bảo vệ client credentials, Token Endpoint, TLS và sử dụng access token đúng audience/scope.

## 16. Câu hỏi ôn tập

**1. Ở callback, client có thể tin tưởng giá trị `state` do browser gửi mà không tìm authorization request đã lưu không?**

Không. `state` phải được liên kết và đối chiếu với **request trước đó do chính client tạo** trong ngữ cảnh an toàn.

**2. Ai xác minh PKCE `code_verifier`?**

**Authorization Server** xác minh verifier ở Token Endpoint bằng cách tính challenge và so sánh với challenge đã được gắn với authorization code ban đầu.

**3. Tại sao không gửi `code_verifier` trong authorization URL?**

Verifier là bí mật chứng minh quyền đổi code. Đưa nó vào front-channel làm mất ý nghĩa bảo vệ chống đánh cắp authorization code của PKCE.

**4. Nếu OIDC authorization request đã gửi nonce nhưng ID Token không có nonce tương ứng, xử lý thế nào?**

OIDC Client phải **từ chối** ID Token/đăng nhập vì không đáp ứng ràng buộc nonce của yêu cầu xác thực.

**5. Lỗi callback mất `OAuth2AuthorizationRequest` có thể do đâu ngoài tấn công?**

Session hết hạn, cookie không được gửi qua proxy, nhiều tab làm mất request đang chờ, request đã bị xóa/dùng một lần, hoặc các instance không dùng session storage thống nhất.

**6. `OAuth2AuthorizedClient` có thay thế `AuthorizationRequestRepository` trong việc kiểm tra state không?**

Không. Authorized client gắn với token **sau khi cấp quyền**, còn request repository giữ dữ liệu **trước callback** để thực hiện correlation và token exchange.

**7. Cách bổ sung PKCE trong Servlet mà vẫn dùng luồng Spring Security là gì?**

Có thể dùng `DefaultOAuth2AuthorizationRequestResolver` cùng `OAuth2AuthorizationRequestCustomizers.withPkce()`, rồi gắn resolver vào `oauth2Login(...).authorizationEndpoint(...)`. Cần kiểm tra phiên bản/thành phần thực tế và hỗ trợ PKCE của provider.

**8. Nếu callback hợp lệ nhưng ID Token có issuer không đúng, có nên cho login thành công vì nonce trùng không?**

Không. **Issuer, audience, signature, expiration** và nonce khi có là những ràng buộc khác nhau. Nonce đúng không bù được ID Token không đáng tin cậy.

## 17. Tài liệu tham khảo chính thức

- [Spring Security Reference — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security Reference — OAuth 2.0 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security Reference — OAuth 2.0 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security Reference — OAuth 2.0 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Security API — OAuth2AuthorizationRequest](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/endpoint/OAuth2AuthorizationRequest.html)
- [Spring Security API — HttpSessionOAuth2AuthorizationRequestRepository](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/HttpSessionOAuth2AuthorizationRequestRepository.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0 — Authentication Request và ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html)

**Ghi nhớ:** Một callback an toàn phải thuộc **authorization request mà ứng dụng đã tạo và còn lưu**. `state` gắn **callback** với request gốc; `code_verifier` gắn **authorization code** với client đã tạo challenge; `nonce` gắn **ID Token OIDC** với lần xác thực đã yêu cầu. Trong Spring Security, hãy giữ nguyên các cơ chế correlation mặc định, bảo vệ session/repository và chỉ tùy biến khi vẫn bảo toàn toàn bộ vòng đời của từng giá trị.

