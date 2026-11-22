# 2.5. Authorization Code Grant và các bước trao đổi mã

## 1. Authorization Code Grant giải quyết bài toán gì?

Giả sử một ứng dụng web viết bằng Spring Boot cần cho người dùng đăng nhập qua một nhà cung cấp danh tính (Identity Provider, viết tắt là IdP) và sau đó gọi API thay mặt người dùng. Ứng dụng không nên yêu cầu người dùng nhập mật khẩu của IdP vào form do chính ứng dụng quản lý. Thay vào đó, trình duyệt chuyển người dùng đến IdP, IdP xác thực người dùng và chuyển họ trở lại ứng dụng cùng một **authorization code** (mã ủy quyền) ngắn hạn. Ứng dụng dùng mã này để xin token qua một kết nối trực tiếp đến máy chủ ủy quyền.

Cách làm đó là **Authorization Code Grant** của OAuth 2.0. Điểm cốt lõi là tách hai kênh:

- **Front channel:** luồng điều hướng qua trình duyệt; chứa yêu cầu cấp quyền và sau đó là authorization code.
- **Back channel:** kết nối HTTP từ OAuth client đến token endpoint của Authorization Server; dùng để đổi code lấy token. Trong kiến trúc web server thông thường, kết nối này không đi qua JavaScript trong trình duyệt.

OAuth 2.0 chủ yếu giải quyết **ủy quyền truy cập tài nguyên**. Khi thêm OpenID Connect (OIDC), ứng dụng dùng cùng Authorization Code Flow để **đăng nhập/xác thực danh tính**; phản hồi token có thêm ID Token và các quy tắc kiểm tra danh tính. Hai khái niệm liên quan nhưng không đồng nghĩa: access token phục vụ API, còn ID Token mô tả lần xác thực cho client.

Ví dụ xuyên suốt bài học sử dụng:

- Ứng dụng Spring Boot: `https://app.example.com`
- Authorization Server / OIDC Provider: `https://id.example.com`
- Client registration ID trong Spring Security: `demo`
- Callback đã đăng ký: `https://app.example.com/login/oauth2/code/demo`

Các tên miền là minh họa. Khi triển khai thật phải thay bằng endpoint và client registration do nhà cung cấp cấp phát.

## 2. Những vai trò và dữ liệu xuất hiện trong luồng

| Thành phần | Vai trò |
|---|---|
| **Resource Owner** | Người dùng cho phép ứng dụng truy cập phạm vi dữ liệu được yêu cầu. |
| **User Agent** | Trình duyệt điều hướng đến trang đăng nhập/đồng ý của IdP rồi trở lại ứng dụng. |
| **OAuth Client / Relying Party** | Ứng dụng Spring Boot tạo yêu cầu ủy quyền, nhận code, đổi token và quản lý phiên đăng nhập. |
| **Authorization Server (AS) / OpenID Provider (OP)** | Xác thực người dùng, quyết định chấp thuận quyền, cấp code và token; nếu hỗ trợ OIDC thì phát hành ID Token. |
| **Resource Server** | API kiểm tra access token và trả tài nguyên tương ứng với quyền được cấp. |

Các giá trị quan trọng cần phân biệt:

| Giá trị | Sinh ra ở đâu? | Dùng để làm gì? |
|---|---|---|
| `client_id` | Cấu hình đăng ký client tại AS | Xác định ứng dụng đang yêu cầu ủy quyền. Không phải bí mật. |
| `client_secret` | AS cấp cho *confidential client*, nếu phương thức xác thực client yêu cầu | Chứng minh danh tính của client tại token endpoint; chỉ giữ tại server. |
| `redirect_uri` | Client gửi trong yêu cầu ủy quyền; đã đăng ký với AS | Địa chỉ AS trả trình duyệt về sau khi xử lý yêu cầu. |
| `scope` | Client yêu cầu; AS quyết định phạm vi được cấp | Ví dụ `openid profile email` cho OIDC hoặc scope API của hệ thống. |
| `state` | Client tạo ngẫu nhiên cho từng yêu cầu | Ghép callback với yêu cầu ban đầu; hỗ trợ chống CSRF và phản hồi bị cài cắm. |
| `code` | AS phát hành sau khi yêu cầu ủy quyền được chấp thuận | Giá trị ngắn hạn, chỉ sử dụng một lần để đổi token. |
| `code_verifier` | Client tạo ngẫu nhiên nếu dùng PKCE | Bí mật tạm thời chứng minh bên đổi code là bên đã khởi tạo yêu cầu. |
| `code_challenge` | Dẫn xuất từ `code_verifier` | Gửi đến authorization endpoint và được AS gắn với code. |
| `nonce` | Client tạo nếu dùng OIDC nonce | Liên kết ID Token với yêu cầu xác thực tương ứng, hạn chế replay. |
| `access_token` | AS phát hành tại token endpoint | Cho phép gọi API trong phạm vi/quyền hạn và thời gian hiệu lực được cấp. |
| `id_token` | OpenID Provider phát hành trong OIDC | Cho client biết thông tin về sự kiện xác thực và chủ thể đã đăng nhập. |
| `refresh_token` | AS có thể phát hành tùy chính sách | Xin access token mới theo các điều kiện mà AS quy định. |

**Authorization code không phải access token.** Client không dùng `code` để gọi API, không đọc code như bằng chứng đăng nhập, và không trao code cho một client khác.

## 3. Toàn cảnh Authorization Code Flow

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng / trình duyệt
    participant C as Spring Security OAuth Client
    participant AS as Authorization Server / OIDC Provider
    participant API as Resource Server

    U->>C: GET /private
    C-->>U: 302 tới /oauth2/authorization/demo
    U->>C: GET /oauth2/authorization/demo
    C-->>U: 302 tới authorization endpoint (state, PKCE, scope...)
    U->>AS: GET /authorize?response_type=code&...
    AS->>U: Đăng nhập và/hoặc đồng ý quyền truy cập
    AS-->>U: 302 redirect_uri?code=...&state=...
    U->>C: GET /login/oauth2/code/demo?code=...&state=...
    Note over C: Kiểm tra state và yêu cầu ủy quyền đã lưu
    C->>AS: POST /token (code, redirect_uri, client auth, code_verifier)
    AS-->>C: access_token (+ id_token, refresh_token nếu áp dụng)
    Note over C: Kiểm tra ID Token nếu là OIDC
    C-->>U: Tạo phiên đăng nhập; chuyển về trang đã yêu cầu
    C->>API: Authorization: Bearer access_token
    API-->>C: Dữ liệu theo quyền được cấp
    C-->>U: Nội dung ứng dụng
~~~

Sơ đồ thể hiện trường hợp ứng dụng web Spring Boot có backend giữ token. Khi người dùng đã có phiên tại IdP, bước nhập mật khẩu có thể được bỏ qua; khi chưa có sự đồng ý cần thiết, IdP có thể hiển thị màn hình consent. Các màn hình đó không làm thay đổi cách trao đổi authorization code.

### Bước 1 — Client khởi tạo yêu cầu ủy quyền

Người dùng mở đường dẫn cần đăng nhập. Spring Security xác định cần xác thực qua OAuth 2.0/OIDC và bắt đầu một yêu cầu ủy quyền.

Ví dụ yêu cầu gửi đến AS sau khi đã mã hóa các tham số URL:

~~~http
GET /authorize?response_type=code
    &client_id=spring-web-client
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fdemo
    &scope=openid%20profile%20email
    &state=RANDOM_STATE
    &code_challenge=BASE64URL_SHA256_OF_VERIFIER
    &code_challenge_method=S256
    &nonce=RANDOM_NONCE HTTP/1.1
Host: id.example.com
~~~

Đây là biểu diễn nhiều dòng để dễ đọc; trên thực tế request URL là một dòng hợp lệ.

Ý nghĩa của các tham số:

- `response_type=code` thông báo client muốn nhận **authorization code**, không yêu cầu access token xuất hiện trực tiếp trong URL callback.
- `client_id` định danh ứng dụng đã đăng ký tại IdP.
- `redirect_uri` phải khớp với URI được AS chấp nhận cho client đó; đây là địa chỉ nhận callback.
- `scope` nêu quyền muốn xin. Sự có mặt của `openid` chuyển yêu cầu sang ngữ cảnh OIDC.
- `state` là giá trị ngẫu nhiên được lưu cùng yêu cầu ban đầu để đối chiếu ở callback.
- `code_challenge` và `code_challenge_method=S256` là phần đầu của cơ chế PKCE.
- `nonce` được dùng khi client yêu cầu và kiểm tra nonce trong ID Token.

Ở bước này client **chưa có authorization code hoặc access token**. Đồng thời, client phải lưu thông tin yêu cầu ban đầu (chẳng hạn `state`, `redirect_uri`, thông tin PKCE, và các tham số cần thiết) để sử dụng tại callback.

### Bước 2 — Authorization Server xác thực và lấy sự đồng ý

Trình duyệt đến authorization endpoint do IdP quản lý. Tại đây AS có thể thực hiện những việc sau:

1. Kiểm tra `client_id`, `redirect_uri`, `response_type`, `scope` và các tham số được hỗ trợ.
2. Xác thực người dùng hoặc sử dụng phiên SSO sẵn có.
3. Yêu cầu consent nếu chính sách buộc người dùng chấp thuận quyền.
4. Nếu yêu cầu hợp lệ và được chấp thuận, phát hành code gắn với client, redirect URI và thông tin ràng buộc liên quan (bao gồm PKCE nếu đã yêu cầu).

Mật khẩu, MFA hoặc phương thức đăng nhập người dùng thực hiện tại IdP. Ứng dụng Spring Boot không nhận mật khẩu IdP trong quá trình này.

### Bước 3 — Trình duyệt nhận callback chứa code và state

Sau khi chấp thuận, AS trả một HTTP redirect:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/demo?code=AUTH_CODE_ABC&state=RANDOM_STATE
~~~

Trình duyệt sau đó gọi callback ở ứng dụng:

~~~http
GET /login/oauth2/code/demo?code=AUTH_CODE_ABC&state=RANDOM_STATE HTTP/1.1
Host: app.example.com
~~~

Ứng dụng cần đối chiếu `state` với giá trị đã lưu cho chính yêu cầu khởi tạo. Nếu state không khớp, thiếu dữ liệu yêu cầu ban đầu hoặc callback đến sai ngữ cảnh, client phải dừng luồng, không dùng code để gọi token endpoint.

Nếu người dùng từ chối, AS thường chuyển về callback với tham số lỗi thay vì `code`, chẳng hạn:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/demo?error=access_denied&state=RANDOM_STATE
~~~

Đường đi lỗi là một phần bình thường của giao thức và cần được xử lý thành trải nghiệm phù hợp, tránh hiển thị token, mã nội bộ hoặc stack trace cho người dùng.

### Bước 4 — Backend đổi code lấy token tại token endpoint

Sau khi đã kiểm tra callback, OAuth client gửi HTTP POST trực tiếp đến token endpoint. Với *confidential client* dùng phương thức `client_secret_basic`, yêu cầu có dạng:

~~~http
POST /token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=authorization_code&code=AUTH_CODE_ABC&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fdemo&code_verifier=ORIGINAL_HIGH_ENTROPY_VERIFIER
~~~

Giải thích các trường:

- `grant_type=authorization_code` xác định loại grant đang sử dụng.
- `code` là mã vừa nhận từ callback.
- `redirect_uri` phải nhất quán với giá trị đã dùng trong authorization request khi giao thức yêu cầu gửi lại; sự khác biệt làm yêu cầu không hợp lệ.
- `Authorization: Basic ...` minh họa cách client xác thực với AS. Phần Basic chứa thông tin client đã được mã hóa Base64, **không phải mã hóa bảo mật**; vì vậy phải dùng TLS và không ghi log giá trị này.
- `code_verifier` là chuỗi gốc của PKCE, chỉ gửi ở token endpoint. AS tính lại challenge và đối chiếu với challenge đã gắn vào code.

Tập tham số cụ thể phụ thuộc cách đăng ký client. *Public client* không có secret đáng tin cậy thì không gửi `client_secret_basic`; nó thường xác định `client_id` theo quy định của AS và **phải dựa vào PKCE** để ràng buộc code. Một số client dùng `private_key_jwt` hoặc phương thức xác thực khác thay cho shared secret.

AS thực hiện các kiểm tra cơ bản: code có tồn tại, còn hiệu lực, chưa sử dụng, thuộc đúng client, đúng redirect URI, có verifier phù hợp nếu đã sử dụng PKCE và client đã xác thực hợp lệ theo phương thức được đăng ký. Nếu một kiểm tra thất bại, AS trả lỗi và không phát token.

### Bước 5 — Client nhận phản hồi token

Một phản hồi OIDC thành công có thể có dạng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid profile email",
  "id_token": "SIGNED_ID_TOKEN_VALUE",
  "refresh_token": "OPTIONAL_REFRESH_TOKEN_VALUE"
}
~~~

`access_token` dùng cho API; `id_token` xuất hiện khi đây là phản hồi OIDC phù hợp; `refresh_token` phụ thuộc cấu hình, scope, chính sách và quyết định của AS, nên **không được mặc định luôn có**. JSON trên chỉ minh họa các trường phổ biến; giá trị, thời gian hiệu lực và định dạng token thực tế do AS quyết định.

Với OIDC, client cần xác minh ID Token theo yêu cầu của giao thức, bao gồm chữ ký hoặc cơ chế xác minh tương ứng, issuer (`iss`), audience (`aud`), thời gian hiệu lực (`exp`), và `nonce` khi yêu cầu nonce đã được sử dụng. Client cũng xử lý các ràng buộc khác như `azp` hoặc thuật toán ký nếu tình huống đòi hỏi. Spring Security cung cấp các thành phần thực hiện xử lý token và xác thực OIDC trong luồng đăng nhập tiêu chuẩn.

**Chỉ có token không đồng nghĩa với một phiên trình duyệt đã đăng nhập.** Ứng dụng còn cần thiết lập ngữ cảnh xác thực/phiên theo cách phù hợp với kiến trúc của mình. Trong ứng dụng web dùng `oauth2Login()`, Spring Security có thể tạo Authentication rồi lưu vào SecurityContext và phiên HTTP.

### Bước 6 — Gọi API bằng access token

Khi cần truy cập resource server, backend dùng access token:

~~~http
GET /v1/profile HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Resource server kiểm tra access token theo cơ chế của hệ thống (ví dụ xác minh JWT hoặc introspection), sau đó áp dụng audience, scope và chính sách phân quyền. **Resource server không nhận ID Token thay cho access token.**

Ở OIDC, client có thể lấy thông tin danh tính từ ID Token và/hoặc UserInfo Endpoint theo quy tắc của provider. Không nên coi mọi claim trong mọi token là bằng chứng phù hợp để phân quyền gọi API: hãy dựa trên token và chính sách dành cho resource server tương ứng.

## 4. Hiểu đúng PKCE, state và nonce

Ba cơ chế này thường xuất hiện cùng nhau, nhưng bảo vệ các mắt xích khác nhau.

### 4.1. PKCE ràng buộc mã ủy quyền với người khởi tạo

**Proof Key for Code Exchange (PKCE)** giảm nguy cơ kẻ khác lấy được authorization code rồi tự đổi code thành token. Client tạo ngẫu nhiên một `code_verifier` đủ mạnh và dẫn xuất:

~~~text
code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
~~~

Client gửi `code_challenge` ở authorization endpoint, nhưng giữ `code_verifier` cho riêng mình đến lúc đổi code. AS lưu ràng buộc giữa challenge và code; khi nhận token request, AS đối chiếu hash của verifier. Kẻ chỉ có code mà không có verifier hợp lệ không đổi được token.

Ví dụ luồng liên kết:

~~~text
Client:
  code_verifier  = chuỗi ngẫu nhiên bí mật cho một yêu cầu
  code_challenge = BASE64URL(SHA256(code_verifier))

Authorization request -> AS:
  code_challenge + code_challenge_method=S256

Callback <- AS:
  code

Token request -> AS:
  code + code_verifier

AS:
  BASE64URL(SHA256(code_verifier)) == code_challenge đã lưu?
  Đúng -> có thể tiếp tục các bước kiểm tra và cấp token
  Sai  -> từ chối trao đổi mã
~~~

Ưu tiên `S256`; không dùng verifier cố định hoặc dùng lại một verifier cho mọi yêu cầu. Client phải liên kết verifier với đúng giao dịch ủy quyền và bảo vệ nó khỏi bị rò rỉ. PKCE đặc biệt thiết yếu cho public client, và cũng là lớp bảo vệ hữu ích cho confidential client. Xác thực bằng client secret và PKCE là hai cơ chế có mục đích khác nhau; có thể sử dụng đồng thời.

### 4.2. State liên kết callback với phiên/yêu cầu ban đầu

`state` là giá trị khó đoán mà client khởi tạo và lưu trước khi redirect người dùng đến IdP. Khi callback quay lại, client so sánh giá trị nhận được với giá trị lưu tương ứng.

Ví dụ: kẻ tấn công cố gửi một đường dẫn `/login/oauth2/code/demo?code=MA_CODE_CUA_KE_TAN_CONG&state=...` đến trình duyệt nạn nhân. Kiểm tra state giúp client từ chối code không gắn với yêu cầu mà chính trình duyệt/phiên nạn nhân đã bắt đầu. Đây là biện pháp chống CSRF và nhầm lẫn luồng đăng nhập.

State cần được sinh riêng cho mỗi yêu cầu và lưu/correlate an toàn. Không thay nó bằng một chuỗi cố định. **PKCE không thay thế đầy đủ vai trò của state trong mọi tình huống**, và state không chứng minh người gọi token endpoint sở hữu verifier như PKCE.

### 4.3. Nonce liên kết ID Token với yêu cầu OIDC

Trong OIDC, client có thể gửi `nonce` khi khởi tạo yêu cầu. Nếu có nonce trong request, OP phải liên kết nonce tương ứng vào ID Token theo quy tắc OIDC, còn client phải kiểm tra giá trị trong ID Token. Điều này giúp phát hiện một ID Token bị phát lại hoặc bị gắn nhầm sang một yêu cầu xác thực khác.

Nonce phục vụ việc xác minh **ID Token**, trong khi state phục vụ tương quan **authorization response** và PKCE phục vụ **token exchange**. Không nên hoán đổi các chức năng này.

| Cơ chế | Giá trị gửi ở authorization request | Giá trị cần đối chiếu về sau | Mục tiêu trực tiếp |
|---|---|---|---|
| `state` | `state` | `state` trong callback | Callback thuộc đúng yêu cầu ban đầu. |
| **PKCE** | `code_challenge` và `S256` | `code_verifier` trong token request | Bên đổi code có verifier đã dùng khi khởi tạo. |
| **OIDC nonce** | `nonce` nếu sử dụng | Claim `nonce` trong ID Token | ID Token thuộc đúng yêu cầu OIDC. |

## 5. Những ràng buộc phải nhớ khi trao đổi authorization code

Một code hợp lệ không phải “vé dùng bao nhiêu lần cũng được”. Authorization Server cần áp dụng các ràng buộc sau:

1. **Thời gian sống ngắn:** authorization code hết hạn nhanh; mã quá hạn không thể đổi token.
2. **Dùng một lần:** sau khi đổi thành công, code không được đổi lần nữa. Nếu nhận lại code đã dùng, AS từ chối; hành vi xử lý token liên quan tuân theo chính sách bảo mật của AS.
3. **Gắn với client:** code được cấp cho client nào thì không được đổi bởi client khác.
4. **Ràng buộc redirect URI:** token request phải thỏa mãn quy tắc đối chiếu redirect URI với authorization request/registration.
5. **Ràng buộc PKCE:** nếu code được cấp qua yêu cầu PKCE, verifier cần được đối chiếu thành công.
6. **Giao tiếp bảo mật:** authorization, callback và token exchange phải tuân thủ yêu cầu TLS của môi trường triển khai; ngoại lệ HTTP trên loopback/localhost cho phát triển chỉ nên theo chính sách cho phép của provider.
7. **Xử lý lỗi rõ ràng:** lỗi xác thực client, code hết hạn, mã dùng lại hoặc verifier sai phải dừng việc tạo phiên đăng nhập.

Đặc biệt, **code đi qua URL callback** nên có thể bị lộ qua lịch sử, proxy log hoặc công cụ giám sát nếu cấu hình không cẩn thận. Vì vậy PKCE, thời hạn ngắn, dùng một lần, HTTPS và chính sách không ghi log bí mật đều quan trọng. Không đưa code, token hay client secret vào URL điều hướng ngoài luồng cần thiết.

## 6. Authorization Code Grant trong Spring Security OAuth 2.0 Client

Ở ứng dụng Servlet dựa trên Spring Boot và Spring Security, `oauth2Login()` cung cấp luồng đăng nhập qua OAuth 2.0/OIDC. Nhà phát triển thường cấu hình client registration và endpoint bảo vệ; Spring Security xử lý yêu cầu ủy quyền, callback, trao đổi code và thiết lập ngữ cảnh đăng nhập.

### 6.1. Khai báo thư viện

Ví dụ Gradle trong một dự án Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Ví dụ dùng ứng dụng web Servlet; với WebFlux, cách cấu hình và các thành phần xử lý là kiểu reactive tương ứng.

### 6.2. Khai báo client registration và provider

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          demo-provider:
            issuer-uri: https://id.example.com
~~~

Cần đăng ký trước client `spring-web-client` (hoặc client ID thực tế) tại IdP và cấu hình callback tương ứng. Ví dụ sử dụng OIDC discovery qua `issuer-uri`; provider thực tế phải có metadata discovery hợp lệ tại issuer đã khai báo. Biến môi trường `OIDC_CLIENT_ID` và `OIDC_CLIENT_SECRET` chứa giá trị được cấp. Không đưa secret thật vào mã nguồn hay ví dụ công khai.

Ý nghĩa các trường:

- `registration.demo` định danh cấu hình; `demo` cũng là phần xuất hiện trong các URL mặc định của Spring Security.
- `provider: demo-provider` liên kết registration với dữ liệu nhà cung cấp.
- `authorization-grant-type: authorization_code` chọn Authorization Code Grant.
- `client-authentication-method: client_secret_basic` quy định cách client xác thực tại token endpoint trong ví dụ confidential client này.
- `redirect-uri` trỏ đến callback mặc định của `oauth2Login()` và dùng các placeholder do Spring hỗ trợ.
- `scope: openid` làm đây trở thành đăng nhập OIDC; `profile`, `email` yêu cầu thêm claim được provider hỗ trợ, không bảo đảm mọi claim luôn có.
- `issuer-uri` cho phép khám phá endpoint ủy quyền, token, UserInfo, JWKS và metadata liên quan khi provider hỗ trợ chuẩn.

Đối với ứng dụng thật ở `https://app.example.com`, giá trị callback sau khi mở rộng placeholder là:

~~~text
https://app.example.com/login/oauth2/code/demo
~~~

URI này phải được cho phép trong cấu hình client tại IdP. Nếu chạy cục bộ trên cổng 8080, callback thường là `http://localhost:8080/login/oauth2/code/demo`; chỉ dùng HTTP phát triển khi provider cho phép.

### 6.3. Bật đăng nhập OAuth 2.0/OIDC

Một cấu hình Spring Security thông dụng:

~~~java
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
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Khi người dùng truy cập `/private` chưa được xác thực, Spring Security đưa họ vào tiến trình đăng nhập. Có thể bắt đầu đăng nhập trực tiếp bằng:

~~~http
GET /oauth2/authorization/demo HTTP/1.1
Host: app.example.com
~~~

Đường dẫn này là **endpoint khởi tạo authorization request** mặc định của Spring Security, không phải endpoint ở IdP. Spring tạo request hợp lệ rồi redirect trình duyệt sang AS.

Callback mặc định là:

~~~text
/login/oauth2/code/{registrationId}
~~~

Khi `registrationId = demo`, callback thành `/login/oauth2/code/demo`. Trong luồng tiêu chuẩn, nhà phát triển **không cần tự viết controller** để đọc `code` rồi POST tới token endpoint.

Nếu muốn trình duyệt được chuyển đến trang cụ thể sau khi đăng nhập, dùng cơ chế success handler hoặc saved request phù hợp; đừng thay callback bảo mật bằng một endpoint tự đọc code theo cách ad hoc.

### 6.4. Spring Security xử lý những gì?

| Thành phần / khái niệm | Vai trò trong Authorization Code Flow |
|---|---|
| `ClientRegistration` / `ClientRegistrationRepository` | Cung cấp `client_id`, grant type, scopes, redirect URI và cấu hình provider. |
| `OAuth2AuthorizationRequestRedirectFilter` | Nhận yêu cầu khởi tạo, tạo authorization request, lưu thông tin liên kết và redirect tới AS. |
| `AuthorizationRequestRepository` | Lưu authorization request giữa lúc chuyển đến IdP và khi callback trở lại; với ứng dụng web thường gắn với phiên HTTP. |
| `OAuth2LoginAuthenticationFilter` | Xử lý callback mặc định, dùng thông tin authorization request để thực hiện quy trình xác thực. |
| Thành phần token response client / authentication provider | Gửi authorization code cùng dữ liệu cần thiết đến token endpoint, nhận token và xử lý kết quả. |
| Hỗ trợ OIDC của Spring Security | Xử lý ID Token, xác thực thông tin OIDC và tạo principal tương ứng khi có scope `openid`. |
| `OAuth2AuthorizedClient` và kho lưu tương ứng | Biểu diễn mối liên hệ giữa client registration, principal và token đã được cấp để dùng cho các yêu cầu API sau đó. |
| `SecurityContext` / phiên đăng nhập | Giữ trạng thái người dùng đã xác thực trong ứng dụng web tùy chiến lược session được cấu hình. |

Lưu ý: tên API và tùy chọn cấu hình chi tiết có thể khác giữa các dòng phiên bản Spring Security; cách hoạt động giao thức Authorization Code Grant vẫn dựa trên cùng các bước.

### 6.5. Ví dụ đọc danh tính của người dùng đã đăng nhập

Trong bài toán OIDC, một controller có thể nhận principal do Spring Security tạo:

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of("subject", user.getSubject());
    }
}
~~~

Ở ví dụ này `subject` đến từ thông tin OIDC đã qua luồng xử lý xác thực. Tránh hiển thị access token, refresh token hoặc ID Token trên trang chỉ để kiểm tra đăng nhập.

Nếu ứng dụng chỉ dùng OAuth 2.0 mà không yêu cầu `openid`, principal và cơ chế nạp thông tin người dùng có thể khác; không mặc định ép thành `OidcUser`.

### 6.6. PKCE trong cấu hình Spring Security

Với public client, `client-secret` không phải bí mật có thể giữ an toàn, và `client-authentication-method` thường là `none`; PKCE là thành phần bắt buộc cần quan tâm. Các phiên bản Spring Security hiện đại có hỗ trợ PKCE trong quá trình tạo authorization request, bao gồm tình huống public client. Với confidential client, có thể chủ động bật PKCE để bảo vệ thêm code exchange.

Một cách cấu hình minh họa cho luồng Servlet là gắn customizer PKCE vào resolver:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PkceSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
                registrations, "/oauth2/authorization");
        resolver.setAuthorizationRequestCustomizer(
                OAuth2AuthorizationRequestCustomizers.withPkce());

        http
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth -> oauth
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
~~~

Đây là **phương án thay thế** cho bean `SecurityFilterChain` ở mục 6.3, không thêm cả hai bean y hệt vào cùng một dự án. Hãy kiểm tra API của phiên bản Spring Security đang dùng và yêu cầu PKCE của provider. Resolver phải lưu được dữ liệu cần thiết để sau callback, token request gửi đúng `code_verifier`. Không tự sinh một verifier mới trong lúc đổi token.

### 6.7. Session đăng nhập và token truy cập API là hai trạng thái khác nhau

Sau OAuth login, người dùng có thể tiếp tục truy cập các trang được bảo vệ nhờ session cookie của ứng dụng. Khi backend cần gọi API thay mặt người dùng, nó dùng `OAuth2AuthorizedClient` tương ứng để truy xuất access token. Cookie phiên **không phải** access token của resource server.

Vì vậy cần phân biệt:

- `oauth2Login()` tập trung vào việc xác thực người dùng với ứng dụng web và thiết lập principal.
- `oauth2Client()`, `OAuth2AuthorizedClientManager` và các cơ chế authorized client hỗ trợ lấy, quản lý và sử dụng token cho API. Chúng có thể được kết hợp với luồng đăng nhập nhưng không đồng nghĩa với một yêu cầu đăng nhập mới mỗi lần gọi API.
- Resource Server độc lập kiểm tra access token. Client không thể dùng việc “đã đăng nhập thành công” để bỏ qua kiểm tra token của API.

Điều này đặc biệt quan trọng trong ứng dụng vừa phục vụ giao diện web vừa gọi nhiều API downstream.

## 7. Hai biến thể thường gặp

### 7.1. Confidential client: Spring Boot backend giữ secret

Với ứng dụng có backend tin cậy, client thường được đăng ký dạng confidential. Server giữ secret trong cấu hình an toàn hoặc hệ thống quản lý bí mật; trình duyệt chỉ tham gia các redirect. Khi token exchange, backend xác thực với AS theo phương thức đã đăng ký.

Luồng phù hợp:

~~~text
Trình duyệt ── redirect ──> IdP
Trình duyệt <── code qua redirect ── IdP
Trình duyệt ── callback(code, state) ──> Spring Boot
Spring Boot ── POST /token + client auth + PKCE ──> IdP
Spring Boot <── tokens ── IdP
~~~

Secret không nên xuất hiện trong JavaScript, HTML, response gửi ra trình duyệt, URL hoặc log.

### 7.2. Public client: không có secret bền vững

Ứng dụng native hoặc SPA chạy trong môi trường không thể bảo mật client secret được xem là public client. Nó vẫn có thể dùng Authorization Code Grant nhưng phải áp dụng PKCE phù hợp và các biện pháp bảo vệ riêng cho nền tảng.

Ví dụ trường chính của token request có thể là:

~~~http
POST /token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&client_id=public-client&code=AUTH_CODE_ABC&redirect_uri=REGISTERED_REDIRECT_URI&code_verifier=ORIGINAL_VERIFIER
~~~

Không sao chép cấu hình `client-secret` của server sang SPA. Cách lưu token, xử lý callback, CORS và quản lý phiên của public client cần thiết kế riêng; ví dụ Spring Boot server ở bài này đại diện cho trường hợp web backend.

## 8. OAuth 2.0 thuần so với OIDC Code Flow

Cùng một mẫu redirect và token exchange có thể phục vụ hai mục tiêu:

| Nội dung | OAuth 2.0 Authorization Code Grant | OIDC Authorization Code Flow |
|---|---|---|
| Mục đích chính | Cấp quyền truy cập tài nguyên | Xác thực danh tính người dùng, đồng thời có thể xin quyền API |
| Scope đặc trưng | Phụ thuộc resource/API, ví dụ `read:orders` | Có `openid`, có thể thêm `profile`, `email` |
| Kết quả token endpoint | Thường có access token; refresh token tùy chính sách | Có access token và ID Token; refresh token tùy chính sách |
| Bằng chứng danh tính cho client | OAuth 2.0 không tự định nghĩa ID Token | ID Token có các claim, chữ ký và quy tắc xác minh theo OIDC |
| Principal sau Spring Security login | Phụ thuộc provider và cấu hình xử lý user info | Thường là `OidcUser` trong luồng `oauth2Login()` |

Ví dụ: một ứng dụng muốn lấy danh sách đơn hàng cần access token có quyền đọc đơn hàng; ID Token không thay thế scope dành cho API đó. Ngược lại, chỉ nhận access token từ một OAuth provider không tự bảo đảm client đã có quy trình đăng nhập OIDC chuẩn. Nếu mục tiêu là login liên thông danh tính, hãy cấu hình OIDC provider và scope `openid`.

## 9. Lỗi phổ biến và cách khoanh vùng

| Triệu chứng | Khả năng nguyên nhân | Nơi kiểm tra |
|---|---|---|
| IdP báo `invalid_redirect_uri` hoặc từ chối authorization request | Callback không được đăng ký, sai scheme/host/port/path | Client registration tại IdP và `redirect-uri` trong Spring |
| Callback quay về nhưng báo `invalid_state` hoặc không tìm thấy authorization request | Mất session/cookie, state không trùng, nhiều request chồng chéo, proxy/cấu hình callback sai | Session, cookie, cấu hình SameSite, URL thực tế và bộ lưu authorization request |
| Token endpoint trả `invalid_grant` | Code đã hết hạn, đã dùng, không thuộc client/redirect URI đúng, hoặc PKCE verifier sai | Thứ tự callback → token request, thời gian xử lý, code binding và verifier |
| Token endpoint trả `invalid_client` | Client ID/secret sai hoặc phương thức xác thực client không đúng | Registration trong IdP, `client-authentication-method`, secret |
| Token endpoint báo lỗi liên quan `code_verifier` | Không gửi verifier, sinh mới verifier hoặc challenge và verifier không tương ứng | Nơi tạo PKCE và nơi lưu yêu cầu gốc |
| Đăng nhập OAuth thành công nhưng không nhận được ID Token | Yêu cầu chưa phải OIDC, thiếu `openid` hoặc provider không hỗ trợ OIDC | Scope, metadata provider, phản hồi token |
| ID Token bị từ chối | Sai issuer/audience, chữ ký, thời gian hiệu lực hoặc nonce | Cấu hình issuer, đồng hồ hệ thống, JWKS và các claim |
| Lấy được token nhưng API trả `403 Forbidden` | Token thiếu scope/quyền hoặc API áp chính sách từ chối | Scope được cấp, audience và chính sách resource server |
| API trả `401 Unauthorized` | Token không hợp lệ, hết hạn, gửi sai loại token hoặc thiếu header Bearer | Header Authorization, tính hợp lệ và thời gian sống của access token |
| Chạy sau reverse proxy bị callback sai `http`/`https` | Ứng dụng nhìn thấy scheme/host nội bộ, forwarded headers không được cấu hình tin cậy | Proxy, cấu hình forwarded headers và `{baseUrl}` khi Spring dựng redirect URI |

Các mã lỗi OAuth cần đọc cùng ngữ cảnh phản hồi thực tế. Chẳng hạn `invalid_grant` có thể do nhiều nguyên nhân khác nhau; không nên kết luận ngay rằng chỉ có code hết hạn.

### Quan sát luồng khi phát triển

Có thể chẩn đoán theo chuỗi sự kiện:

1. Xác nhận trình duyệt đi đến đúng `/oauth2/authorization/demo` rồi được redirect sang authorization endpoint.
2. Kiểm tra request gửi AS có `response_type=code`, đúng `client_id`, `redirect_uri`, scope và thông số PKCE nếu đã bật.
3. Kiểm tra callback đến đúng `/login/oauth2/code/demo` và client vẫn giữ được thông tin request ban đầu để kiểm tra `state`.
4. Nếu callback hợp lệ nhưng đăng nhập thất bại, xem lỗi trao đổi token ở backend (mã lỗi, HTTP status và cấu hình provider), không in toàn bộ code hay token.
5. Nếu đã đăng nhập nhưng API lỗi, kiểm tra access token, scope/audience, cấu hình resource server và quyền người dùng riêng biệt với OIDC login.

Trong DevTools của trình duyệt thường nhìn thấy các bước redirect qua front channel. Với mẫu backend này, POST tới token endpoint diễn ra **giữa Spring Boot và AS**, nên không xuất hiện như một yêu cầu JavaScript từ trang web. Không tự tái hiện code exchange bằng cách gửi code từ trình duyệt đến token endpoint khi hệ thống đang sử dụng Spring Security làm confidential client.

## 10. Nguyên tắc bảo mật khi triển khai

Một triển khai Authorization Code Grant an toàn cần giữ các nguyên tắc sau:

- Sử dụng HTTPS trên môi trường thật; đăng ký redirect URI chính xác và hạn chế URI có thể bị điều khiển tùy ý.
- Sinh `state` ngẫu nhiên theo từng giao dịch và xác minh tại callback; bảo vệ session/cookie lưu dữ liệu tương quan.
- Sử dụng PKCE `S256`, lưu verifier đúng với từng authorization request; nhất là với public client.
- Không đưa client secret vào browser hoặc mobile app; chọn phương thức xác thực client phù hợp với loại client.
- Không dùng authorization code nhiều lần, không lưu code như access token, không cố bỏ qua lỗi `invalid_grant`.
- Không in access token, refresh token, ID Token, client secret hoặc authorization code vào log ở môi trường thật; kiểm soát cả proxy/access log và công cụ giám sát.
- Kiểm tra ID Token theo OIDC khi xác thực người dùng; dùng access token đúng audience và scope để gọi resource server.
- Giữ cấu hình issuer, redirect URI và metadata provider nhất quán khi chạy sau load balancer/reverse proxy.
- Áp dụng bảo vệ CSRF thông thường cho các thao tác thay đổi dữ liệu trong ứng dụng; `state` của OAuth không thay thế cơ chế CSRF cho toàn bộ HTTP endpoint.
- Dùng cơ chế quản lý token/authorized client của framework phù hợp với yêu cầu session, hết hạn và làm mới; không tự lưu token tùy tiện vào URL hoặc localStorage khi kiến trúc server có thể giữ an toàn hơn.

## 11. Tự kiểm tra hiểu biết bằng một tình huống

Một ứng dụng gửi authorization request chứa `state=S1` và `code_challenge=C1`. Sau khi người dùng đăng nhập, trình duyệt đến callback với `code=K1&state=S1`.

**Ứng dụng có thể lập tức coi người dùng đã đăng nhập chưa?** Chưa. Client phải đối chiếu `state` với yêu cầu đã lưu, đổi `K1` tại token endpoint bằng các thông tin đúng (bao gồm `code_verifier` tương ứng với `C1` và xác thực client nếu cần), xử lý phản hồi, kiểm tra ID Token nếu là OIDC và chỉ sau đó thiết lập ngữ cảnh đăng nhập.

**Nếu kẻ khác lấy được `K1` nhưng không có verifier thì sao?** Với PKCE được AS thực thi đúng, kẻ đó không chứng minh được mình sở hữu verifier nên không thể đổi code thành token chỉ bằng `K1`.

**Nếu callback có `state=S2` thay vì `S1` thì sao?** Client phải từ chối callback do không khớp yêu cầu đã khởi tạo, kể cả khi code nhìn có vẻ hợp lệ.

**Nếu ứng dụng gửi lại `K1` sau khi đã đổi thành công thì sao?** AS phải từ chối mã dùng lại. Ứng dụng không thể dùng một authorization code để lấy token vô hạn lần; vòng đời token và refresh token là vấn đề khác.

**Nếu API từ chối access token dù OIDC login đã thành công thì sao?** Kiểm tra audience, scope, hiệu lực token và chính sách API. Đăng nhập thành công chứng minh người dùng đã được xác thực với client; nó không tự cấp quyền truy cập mọi tài nguyên.

## 12. Ghi nhớ luồng trao đổi mã

Authorization Code Grant đi qua chuỗi **authorization request → user authentication/consent → callback có code và state → kiểm tra callback → backend token request → xác minh phản hồi → dùng token theo đúng mục đích**.

Trong Spring Security OAuth 2.0/OIDC Client, những endpoint thường phải nhớ là:

| URL / endpoint | Phía sở hữu | Mục đích |
|---|---|---|
| `/oauth2/authorization/{registrationId}` | Spring Security client | Khởi tạo authorization request và redirect đến IdP. |
| Authorization endpoint, ví dụ `https://id.example.com/authorize` | IdP / AS | Nhận yêu cầu ủy quyền; xác thực/consent; cấp code qua redirect. |
| `/login/oauth2/code/{registrationId}` | Spring Security client | Nhận callback, đối chiếu request, tiếp tục đổi code lấy token. |
| Token endpoint, ví dụ `https://id.example.com/token` | IdP / AS | Kiểm tra code, client authentication và PKCE; phát hành token. |
| UserInfo endpoint, nếu OIDC provider hỗ trợ và client sử dụng | OpenID Provider | Cung cấp claim về người dùng theo cơ chế OIDC. |
| Endpoint API được bảo vệ | Resource Server | Nhận access token, kiểm tra quyền và trả dữ liệu. |

Một cách nhớ ngắn: **trình duyệt vận chuyển code; client đổi code; AS cấp token; API kiểm tra access token; OIDC client kiểm tra ID Token để đăng nhập.** Mỗi vai trò có một trách nhiệm riêng, và các bước kiểm tra `state`, PKCE, client authentication cùng OIDC validation làm cho toàn bộ luồng đáng tin cậy.
