# 8.7. Áp dụng PKCE cho public client và confidential client

## 1. PKCE nằm ở đâu trong Authorization Code Flow?

Trong **Spring Security OAuth 2.0/OIDC Client**, Authorization Code Grant cho phép ứng dụng đưa người dùng đến Authorization Server (AS) hoặc OpenID Provider (OP) để xác thực và cấp quyền. Khi thành công, AS chuyển trình duyệt về ứng dụng cùng một **authorization code**. Client dùng code đó để gọi **token endpoint**, đổi lấy access token và, với OpenID Connect, thường nhận thêm ID Token.

Vấn đề bảo mật: **authorization code có thể bị chặn, đánh cắp hoặc bị chuyển đến sai bên nhận** khi đi qua kênh điều hướng trình duyệt. Nếu chỉ có code là đủ để đổi token, một bên khác lấy được code có thể tìm cách đổi nó tại token endpoint, đặc biệt khi client không có cách giữ an toàn một bí mật lâu dài.

**PKCE — Proof Key for Code Exchange**, phát âm gần như “pixy”, là cơ chế được chuẩn hóa trong RFC 7636 để ràng buộc **authorization request ban đầu** với **token request đổi code**. PKCE giúp Authorization Server kiểm tra rằng bên đổi code đang giữ một giá trị ngẫu nhiên mà bên khởi tạo yêu cầu đã tạo trước đó.

PKCE ban đầu được thiết kế cho **public client**, nhưng các thực hành OAuth 2.0 hiện đại cũng khuyến nghị áp dụng với **confidential client**. PKCE không yêu cầu thay đổi grant type: vẫn sử dụng `response_type=code` ở authorization endpoint và `grant_type=authorization_code` tại token endpoint.

Các tình huống trong bài:

- **Public client:** ứng dụng không thể giữ client secret lâu dài một cách tin cậy, chẳng hạn ứng dụng native hoặc Single Page Application (SPA) trong trình duyệt.
- **Confidential client:** ứng dụng backend có thể bảo vệ client credential, chẳng hạn Spring Boot web server làm OAuth2/OIDC Client.
- **Authorization Server:** cung cấp authorization endpoint và token endpoint, phải hiểu, lưu và kiểm tra dữ liệu PKCE.
- **Resource Server:** API sử dụng access token sau khi cấp quyền; không phải bên kiểm tra PKCE trong code exchange.

Mục tiêu là hiểu đúng PKCE, phân biệt vai trò của nó với client authentication, `state` và OIDC `nonce`, rồi áp dụng vào cấu hình Spring Security.

## 2. Vì sao chỉ có client secret chưa đủ?

Hãy phân biệt hai vấn đề:

1. **Ai là client đang gọi token endpoint?** Confidential client có thể chứng minh mình bằng `client_secret_basic`, `private_key_jwt` hoặc cơ chế xác thực client tương ứng.
2. **Client đó có phải bên đã khởi tạo chính authorization request tạo ra code này không?** PKCE tạo mối liên kết giữa yêu cầu authorize và yêu cầu đổi code.

Đối với public client, **client secret không thể xem là bí mật** nếu được nhúng vào JavaScript hoặc ứng dụng phân phối đến thiết bị của người dùng. Một secret giống nhau có thể bị trích xuất, nên không thể dùng nó như cơ chế bảo vệ chính cho authorization code. PKCE giải quyết bằng một bí mật ngắn hạn tạo **riêng cho mỗi giao dịch ủy quyền**.

Đối với confidential client, client secret chứng minh định danh ứng dụng nhưng không tự bảo vệ mọi kịch bản **authorization code interception hoặc code injection**. Nếu attacker lấy được code, hoặc đưa code được tạo trong một ngữ cảnh khác vào luồng của client, bảo vệ thêm bằng PKCE giúp buộc code khớp với verifier của đúng giao dịch. Vì vậy **client authentication và PKCE nên được kết hợp**, không phải chọn một trong hai.

| Câu hỏi | Client authentication | PKCE |
|---|---|---|
| Bên gọi token endpoint có được xác thực là client đã đăng ký? | **Có**, nếu client có phương thức xác thực phù hợp. | Không trực tiếp. |
| Bên đổi code có giữ verifier thuộc authorization request đã sinh code? | Không trực tiếp. | **Có**, khi AS xác minh đúng. |
| Bí mật dùng lâu dài hay theo giao dịch? | Thường là secret/khóa dài hạn hoặc vòng đời dài hơn. | Verifier ngẫu nhiên **theo từng authorization request**. |
| Có dùng cho public client không? | Không có secret bảo mật tin cậy theo kiểu confidential client. | **Có**, là cơ chế thiết yếu. |
| Có dùng cho confidential client không? | Có, theo phương thức đã đăng ký. | **Có**, tăng cường bảo vệ code exchange. |
| Có thay thế bảo vệ CSRF và kiểm tra token OIDC? | Không. | Không nên xem là giải pháp bao trùm mọi yêu cầu. |

## 3. Hai giá trị chính: code_verifier và code_challenge

PKCE sử dụng hai giá trị liên quan mật thiết:

- **`code_verifier`:** chuỗi ngẫu nhiên có entropy cao, được tạo khi client bắt đầu một authorization request. Client giữ giá trị này để gửi sau đó tại **token endpoint**.
- **`code_challenge`:** giá trị dẫn xuất từ verifier, gửi tới **authorization endpoint** cùng authorization request. Server gắn challenge với authorization code phát hành.

Khi đổi code, client gửi lại `code_verifier` gốc. Server dẫn xuất challenge từ verifier và so sánh với challenge đã lưu cùng code. Nếu không khớp, trao đổi code phải bị từ chối.

### 3.1. Quy tắc của code_verifier

RFC 7636 định nghĩa `code_verifier` là chuỗi ký tự:

- Độ dài **43–128 ký tự**.
- Dùng các ký tự unreserved: chữ cái A–Z/a–z, chữ số 0–9, dấu `-`, `.`, `_` và `~`.
- Được sinh bằng bộ tạo số ngẫu nhiên an toàn về mật mã, có entropy đủ cao. Khuyến nghị phổ biến là **32 byte ngẫu nhiên** rồi mã hóa Base64URL không padding, cho chuỗi 43 ký tự.

Verifier là **bí mật ngắn hạn của giao dịch**, không phải password người dùng hay client secret. Mỗi lượt khởi tạo authorization request phải tạo một verifier mới; không tái sử dụng verifier cố định cho mọi người dùng, mọi cửa sổ hoặc mọi lần đăng nhập.

### 3.2. Cách tạo S256 code_challenge

Phương thức PKCE được khuyến nghị là **`S256`**:

~~~text
code_challenge = BASE64URL-ENCODE(
    SHA256(ASCII(code_verifier))
)

code_challenge_method = S256
~~~

Chú ý:

- Băm **chuỗi ASCII** của `code_verifier` bằng SHA-256.
- Mã hóa kết quả hash bằng Base64URL, **không có dấu `=` padding**.
- Dùng bảng chữ Base64URL, **không** dùng Base64 tiêu chuẩn có `+` và `/`.
- **Không gửi `code_verifier` trong authorization request**; giá trị được gửi tại token request.
- `code_challenge` có thể xuất hiện trên URL front channel; nó **không cần được giữ bí mật** như verifier.

Một cặp dữ liệu ví dụ được công bố trong RFC 7636:

~~~text
code_verifier:
  dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge (S256):
  E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Cặp giá trị trên chỉ dùng để minh họa hoặc đối chiếu thuật toán. **Không sao chép nguyên cặp ví dụ làm verifier cố định trong ứng dụng thật.**

### 3.3. Phương thức plain và lý do ưu tiên S256

RFC 7636 cũng mô tả phương thức `plain`, trong đó `code_challenge` bằng chính `code_verifier`. Tuy nhiên, nếu cả challenge lẫn verifier đều có thể lộ qua kênh front channel, cách này làm giảm đáng kể tác dụng bảo vệ.

**Ưu tiên `S256`** khi client và AS hỗ trợ; một triển khai hiện đại không nên hạ cấp từ `S256` xuống `plain` chỉ để lách lỗi cấu hình. Nếu AS không hỗ trợ S256, cần kiểm tra chính sách và hợp đồng an toàn của AS thay vì âm thầm bỏ PKCE.

## 4. Toàn cảnh authorization request và token request có PKCE

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng / Trình duyệt
    participant C as OAuth2/OIDC Client
    participant AS as Authorization Server
    participant API as Resource Server

    Note over C: Tạo verifier V; challenge C = BASE64URL(SHA256(V))
    U->>C: Bắt đầu đăng nhập
    C-->>U: Redirect tới authorization endpoint với C, method=S256, state
    U->>AS: Authorization request
    Note over AS: Ghi nhớ C, S256 và ràng buộc với code
    AS->>U: Đăng nhập / consent
    AS-->>U: Redirect về client với code=K và state
    U->>C: Callback với K, state
    Note over C: Đối chiếu state, lấy đúng verifier V của yêu cầu ban đầu
    C->>AS: POST token endpoint: K, V; client auth nếu confidential
    Note over AS: SHA256(V) == challenge đã gắn với K?
    alt Hợp lệ và đủ điều kiện
        AS-->>C: Access token; ID Token nếu OIDC
        C->>API: Authorization: Bearer access_token
        API-->>C: Tài nguyên được cấp quyền
    else Verifier không khớp / code không hợp lệ
        AS-->>C: OAuth2 error, ví dụ invalid_grant
    end
~~~

Sơ đồ áp dụng cho cả public client và confidential client. Khác biệt chính nằm ở **ai thực hiện token request** và **client có thể xác thực bằng một credential bí mật dài hạn hay không**.

### Bước 1 — Tạo verifier và challenge trước khi redirect

Client sinh verifier mới `V1` cho giao dịch `G1` rồi tính challenge `C1`. Client phải lưu được verifier của đúng giao dịch đó đến khi callback trở lại.

Ví dụ trong ứng dụng server-side Spring Security, verifier có thể được lưu trong thuộc tính của `OAuth2AuthorizationRequest`, cùng dữ liệu liên quan đến phiên/authorization request. Trong SPA, thư viện OAuth2 client cần quản lý verifier ở môi trường trình duyệt theo mô hình an toàn thích hợp. Không tùy ý lưu verifier vào URL chuyển hướng hoặc gửi cho IdP khi authorize.

### Bước 2 — Authorization request gửi challenge

Ví dụ yêu cầu OIDC, được xuống dòng cho dễ đọc:

~~~http
GET /authorize?response_type=code
  &client_id=spring-web-client
  &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fdemo
  &scope=openid%20profile
  &state=STATE_RANDOM_1
  &code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
  &code_challenge_method=S256 HTTP/1.1
Host: id.example.com
~~~

Khi thực sự gửi HTTP, query string là **một URL hợp lệ**, không chứa các ngắt dòng trình bày.

Các tham số PKCE chỉ là:

~~~text
code_challenge=<giá trị SHA-256 đã mã hóa Base64URL>
code_challenge_method=S256
~~~

Những tham số còn lại vẫn cần thiết cho Authorization Code Flow: `response_type=code`, `client_id`, `redirect_uri`, `scope`, `state`, và có thể có `nonce` trong OIDC.

Authorization Server kiểm tra yêu cầu, rồi **gắn code_challenge và method với authorization code** nếu phát hành code. Điều này bảo đảm verifier được xác minh ở đúng giao dịch, không so sánh với challenge của bất kỳ yêu cầu nào khác.

### Bước 3 — Callback trả authorization code

Sau khi người dùng hoàn thành xác thực/consent:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/demo?code=CODE_ABC&state=STATE_RANDOM_1
~~~

Client nhận callback, tìm authorization request đã khởi tạo và đối chiếu `state`. Đến lúc này client cần lấy **đúng verifier của request đó**, không được sinh verifier mới.

Nếu trình duyệt mất cookie/session liên kết yêu cầu, callback có thể không thể tìm lại verifier. Khi đó token request sẽ thiếu verifier hoặc gửi sai verifier, dẫn đến lỗi PKCE; cách xử lý là khởi tạo lại flow một cách an toàn.

### Bước 4 — Token request gửi verifier gốc

Ví dụ confidential client dùng `client_secret_basic`:

~~~http
POST /token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_OF_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=authorization_code&code=CODE_ABC&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fdemo&code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
~~~

Ở bước này:

- `grant_type=authorization_code` chọn cơ chế đổi code.
- `code` là authorization code nhận ở callback.
- `redirect_uri` được gửi lại theo yêu cầu giao thức và phải nhất quán với authorization request.
- `code_verifier` là giá trị đã được sinh cho giao dịch này.
- `Authorization: Basic ...` minh họa **client authentication riêng của confidential client**.

Đối với public client không dùng client secret, yêu cầu có thể như sau:

~~~http
POST /token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&client_id=public-browser-client&code=CODE_XYZ&redirect_uri=REGISTERED_REDIRECT_URI&code_verifier=VERIFIER_FOR_THIS_FLOW
~~~

Chi tiết có thể thay đổi theo kiểu client và cách đăng ký với AS. Public client không nhúng một `client_secret` có thể trích xuất vào JavaScript. PKCE không biến public client thành confidential client.

### Bước 5 — AS xác minh challenge, code và client

Khi nhận token request, AS cần kiểm tra đồng thời:

1. Authorization code có tồn tại, chưa hết hạn và chưa được sử dụng.
2. Code được cấp cho client đúng, và `redirect_uri` đáp ứng ràng buộc đã dùng khi authorize.
3. Với code được cấp bằng PKCE, `code_verifier` có mặt, đúng cú pháp và hash dẫn xuất khớp `code_challenge` đã lưu.
4. Nếu client là confidential, client authentication thành công theo phương thức đã đăng ký.
5. Những điều kiện khác của AS (client, grant, chính sách phát hành token) đều được đáp ứng.

Nếu verifier sai, AS từ chối, thường bằng lỗi OAuth2 `invalid_grant`. AS **không được coi việc client xác thực bằng secret thành công là lý do bỏ qua kiểm tra PKCE** khi code đã được gắn challenge.

### Bước 6 — Token được cấp đúng mục đích

Sau khi xác minh thành công, AS có thể trả:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid profile",
  "id_token": "SIGNED_ID_TOKEN_VALUE"
}
~~~

`id_token` xuất hiện trong ngữ cảnh OIDC phù hợp; `refresh_token` có thể được cấp hoặc không, tùy chính sách. PKCE chỉ bảo vệ **khâu trao đổi authorization code**, không tự quyết định scope được cấp hoặc thời hạn access token.

Client tiếp tục xác minh ID Token theo quy tắc OIDC khi dùng OIDC Login, và dùng **access token** để gọi API có quyền tương ứng.

## 5. Public client: khi không thể giữ client secret

### 5.1. Public client là gì?

Một OAuth2 **public client** là ứng dụng không thể bảo vệ bí mật xác thực client lâu dài. Các ví dụ điển hình:

- Ứng dụng JavaScript chạy trong trình duyệt (SPA).
- Ứng dụng native/mobile phân phối đến thiết bị người dùng.
- Ứng dụng desktop hoặc CLI tương tác với người dùng, nếu credential nhúng trong ứng dụng có thể bị trích xuất.

Một secret hardcode trong mã JavaScript hoặc gói ứng dụng mobile **không tạo ra năng lực client authentication đáng tin cậy**, vì tất cả người dùng đều có thể tìm và sao chép giá trị.

Public client vẫn có `client_id`, authorization grant, redirect URI và các scope đã được đăng ký. Chỉ có điều **client_id không phải bí mật**.

### 5.2. Tại sao PKCE đặc biệt quan trọng với public client?

Nếu public client chỉ gửi authorization code tại token endpoint mà không có client authentication và không có PKCE, một bên chiếm được code có thể cố đổi code bằng cách gửi cùng client ID và redirect URI.

Với PKCE:

~~~text
Người khởi tạo yêu cầu:
    code_verifier = V1
    code_challenge = SHA256(V1)

Authorization Server phát code K1 và gắn với challenge của V1.

Kẻ chặn được K1:
    Có K1.
    Không biết V1.

Kẻ tấn công gửi:
    code=K1
    code_verifier=V2

Authorization Server kiểm tra:
    SHA256(V2) != SHA256(V1)
    => Từ chối đổi code.
~~~

Đây là điểm cốt lõi: **code không đủ để nhận token nếu thiếu verifier tương ứng**.

### 5.3. SPA nên xử lý thế nào?

SPA chạy trực tiếp trong browser nên sử dụng thư viện OAuth2/OIDC client phù hợp, thực hiện **Authorization Code Flow with PKCE**. Thư viện cần tự quản lý verifier, state, callback, thời gian sống token và cách tránh lộ token theo kiến trúc ứng dụng.

Không sao chép `client_secret` từ cấu hình backend vào frontend. Không tự thay PKCE bằng “một token tùy ý sinh trong JavaScript” mà AS không biết cách xác minh.

PKCE không loại bỏ rủi ro khi JavaScript độc hại chạy cùng origin: nếu SPA bị XSS hoặc script độc hại chiếm quyền, nó có thể đọc verifier/token mà ứng dụng frontend có quyền truy cập. Vì vậy vẫn cần CSP, kiểm soát dependency, chống XSS, chính sách lưu token thích hợp và bảo vệ callback.

Một phương án kiến trúc khác là **Backend For Frontend (BFF)**: backend Spring Boot giữ token và client credentials, còn browser làm việc với ứng dụng qua session cookie. Trong mô hình BFF, backend đóng vai trò confidential client và **vẫn nên dùng PKCE**.

### 5.4. Native/mobile client nên xử lý thế nào?

Native client thường mở trình duyệt hệ thống để người dùng đăng nhập, nhận callback qua redirect URI đã đăng ký rồi đổi code bằng verifier đã giữ trong ứng dụng.

Các redirect URI có thể là loopback, claimed HTTPS hoặc custom URI scheme tùy nền tảng và yêu cầu AS. Chỉ PKCE **chưa đủ** để đảm bảo bảo mật redirect URI: ứng dụng còn phải tuân thủ hướng dẫn bảo vệ callback cho native apps, quản lý state, không dùng embedded webview kém an toàn và bảo vệ token trên thiết bị.

### 5.5. Spring Boot server có thể được đăng ký là public client không?

Có thể. Một ứng dụng Spring Boot chạy server vẫn có thể dùng một registration không có secret nếu AS đăng ký client đó là public. Tuy nhiên, **client type do khả năng giữ credential và mô hình đăng ký quyết định**, không chỉ do chương trình viết bằng Java hay chạy trên server.

Với ứng dụng web backend do bạn kiểm soát và có thể bảo vệ secret/khóa, mô hình confidential client thường phù hợp hơn. Dù chọn loại nào, PKCE vẫn được dùng để bảo vệ authorization code.

## 6. Confidential client: client authentication + PKCE

### 6.1. Confidential client là gì?

Confidential client có môi trường giữ bí mật xác thực client tin cậy hơn, thường là backend server:

~~~text
Trình duyệt người dùng
    |
    | Redirect / callback chứa authorization code
    v
Spring Boot backend
    |
    | POST /token bằng client authentication + code_verifier
    v
Authorization Server
~~~

Thông thường backend giữ client secret trong secret manager hoặc biến môi trường; browser không nhìn thấy giá trị này. Client có thể dùng `client_secret_basic`, `client_secret_post`, `private_key_jwt` hoặc phương thức đã được AS cấp phép.

### 6.2. PKCE bổ sung được điều gì?

Trong confidential client, client authentication đã làm giảm khả năng một ứng dụng khác đổi code thay mặt client. Nhưng PKCE vẫn hữu ích vì:

- Bảo vệ ràng buộc code với đúng authorization request đã khởi tạo.
- Hạn chế một số tình huống chặn/cài cắm authorization code qua front channel.
- Giúp mô hình an toàn thống nhất giữa các loại client.
- Tương thích với những Authorization Server yêu cầu PKCE cho mọi Authorization Code Grant.
- Cung cấp thêm bằng chứng theo từng giao dịch mà một credential client dài hạn không thể hiện.

Một confidential client nên gửi cả client authentication lẫn `code_verifier` ở token request khi flow dùng PKCE. Không bỏ verifier vì đã có client secret.

### 6.3. PKCE không bảo vệ client secret bị lộ

Nếu client secret/private key bị lộ, cần rotate hoặc thu hồi credential theo chính sách AS. PKCE không làm credential dài hạn bị đánh cắp trở nên vô hại; nó chỉ giúp bảo vệ từng code exchange đã được ràng buộc verifier.

Ngược lại, việc rotate client secret cũng không thay thế việc sinh verifier ngẫu nhiên riêng cho từng giao dịch.

## 7. So sánh cách triển khai giữa public và confidential client

| Tiêu chí | Public client | Confidential client |
|---|---|---|
| Ví dụ thường gặp | SPA, native/mobile, desktop | Spring Boot backend, BFF |
| Client ID | Có; không phải bí mật | Có; không phải bí mật |
| Client secret/khóa xác thực dài hạn | Không thể giữ bí mật đáng tin cậy | Có thể giữ trong backend/secret manager |
| Client authentication tại token endpoint | Thường đăng ký `none` | Thực hiện theo phương thức được cấp |
| PKCE | **Phải được dùng** trong Authorization Code Flow hiện đại | **Nên dùng** và có thể bị AS yêu cầu |
| `code_verifier` | Giữ theo giao dịch ở môi trường client | Giữ theo giao dịch ở backend/session |
| `code_challenge` | Gửi ở authorization request | Gửi ở authorization request |
| `code_verifier` được gửi lúc nào | Token request | Token request |
| Rủi ro riêng | XSS, local malware, redirect interception, token storage | Secret leakage, session handling, proxy/callback misconfiguration |
| Có thể bỏ state, HTTPS, OIDC validation? | Không | Không |

**Ghi nhớ:** sự khác biệt lớn nhất là khả năng xác thực *client*, còn **PKCE S256 hoạt động cùng một nguyên lý ở cả hai loại client**.

## 8. Áp dụng PKCE trong Spring Security OAuth2 Client

Spring Security hỗ trợ PKCE trong quá trình xây dựng authorization request và dùng `code_verifier` tương ứng trong token request. Ở ứng dụng Spring Boot, nhóm dependency cốt lõi thường gồm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Ví dụ dùng Spring Boot 3.x, ứng dụng **Servlet/MVC**. Với Spring Boot 4.x, các tên starter tương ứng được khuyến nghị gồm `spring-boot-starter-webmvc` và `spring-boot-starter-security-oauth2-client`. Giữ nhất quán BOM/plugin và cách cấu hình với dòng Spring Boot đang dùng.

Một ứng dụng WebFlux sử dụng các lớp reactive tương ứng như `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveClientRegistrationRepository`. Không thay `HttpSecurity` bằng lớp reactive trong cùng một mẫu mã Servlet mà không chuyển toàn bộ cấu hình.

### 8.1. Cấu hình hai ClientRegistration cùng một OIDC Provider

Để minh họa sự khác biệt giữa hai loại client, giả sử AS tạo **hai client registration riêng**:

1. `public-demo` — public client, không có client secret.
2. `server-demo` — confidential web client, được cấp client ID/secret.

Trong `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          public-demo:
            provider: example-idp
            client-id: ${PUBLIC_CLIENT_ID}
            client-authentication-method: none
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
          server-demo:
            provider: example-idp
            client-id: ${SERVER_CLIENT_ID}
            client-secret: ${SERVER_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          example-idp:
            issuer-uri: https://id.example.com
~~~

Điều kiện để chạy ví dụ:

- `https://id.example.com` là issuer OIDC hợp lệ, có discovery metadata và hỗ trợ Authorization Code Flow với PKCE S256.
- Mỗi `client-id` đã được đăng ký đúng loại với AS.
- AS cho phép callback tương ứng, ví dụ `https://app.example.com/login/oauth2/code/public-demo` và `https://app.example.com/login/oauth2/code/server-demo`.
- `SERVER_CLIENT_SECRET` chỉ nằm ở backend và được bảo vệ.
- `PUBLIC_CLIENT_ID` và `SERVER_CLIENT_ID` là hai giá trị thực từ AS; không phải tên registrationId do Spring tự cấp phát.

Đây là ví dụ **hai registration trong cùng một backend Spring Boot** để quan sát cấu hình; nó không thay thế cách triển khai SPA chạy JavaScript với thư viện PKCE ở frontend.

### 8.2. Public client: Spring Security có hỗ trợ PKCE tự động

Trong Spring Security OAuth2 Client, khi một `ClientRegistration` sử dụng `authorization_code` và `client-authentication-method: none`, cơ chế mặc định của authorization request resolver có thể **tự áp dụng PKCE** cho public client. Khi đó yêu cầu khởi tạo tới AS mang `code_challenge` và `code_challenge_method=S256`, còn token request gửi `code_verifier` tương ứng.

Với Servlet OAuth2 Login:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

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

Người dùng khởi tạo authorization request qua:

~~~text
/oauth2/authorization/public-demo
~~~

Spring Security dựa vào `ClientRegistration` để xây request, quản lý dữ liệu theo phiên/giao dịch và xử lý callback mặc định:

~~~text
/login/oauth2/code/public-demo
~~~

**Không tự phát minh controller nhận code** nếu đã dùng `oauth2Login()` theo mặc định. Trình tự xử lý callback, state, PKCE và token exchange do các thành phần Spring Security phối hợp thực hiện.

Vì hỗ trợ tự động và hành vi có thể khác theo phiên bản hoặc custom resolver, khi triển khai thực tế cần xác nhận authorization request đúng theo cấu hình. Quan trọng hơn, AS phải **thực thi PKCE** cho client này; client tự gửi challenge mà AS bỏ qua verifier không tạo được bảo vệ mong muốn.

### 8.3. Confidential client: chủ động thêm PKCE bằng customizer

Với confidential client, việc có client secret **không có nghĩa mọi phiên bản/cấu hình Spring Security mặc định đều bật PKCE**. Có thể chủ động gắn `OAuth2AuthorizationRequestCustomizers.withPkce()` vào resolver.

Ví dụ hoàn chỉnh cho **Servlet stack**:

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

        DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations,
                "/oauth2/authorization"
            );

        resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce()
        );

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**").permitAll()
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

Đoạn cấu hình này **thay thế** `SecurityFilterChain` ở ví dụ trước, không đưa cả hai bean giống nhau vào ứng dụng chỉ để thử hai cách.

Các điểm quan trọng:

- `DefaultOAuth2AuthorizationRequestResolver` tìm `ClientRegistration` theo registrationId từ URL.
- `withPkce()` bổ sung các dữ liệu PKCE cho authorization request khi tương ứng; Spring Security quản lý verifier trong thông tin request để dùng lại lúc đổi code.
- Base URI `/oauth2/authorization` khớp endpoint khởi tạo mặc định trong ví dụ.
- `oauth2Login(...authorizationRequestResolver(resolver))` cho phép Spring Security dùng resolver có PKCE đã tùy chỉnh.
- Khi người dùng truy cập `/oauth2/authorization/server-demo`, authorization request dành cho confidential client có thêm `code_challenge` và `code_challenge_method=S256`.
- Khi callback đến `/login/oauth2/code/server-demo`, token exchange cần cả client authentication lẫn verifier ban đầu.

Nếu một dự án đã có customizer/resolver riêng cho tham số như `prompt`, `login_hint` hoặc `audience`, cần **kết hợp** logic đó với PKCE trong cùng resolver. Tránh thay resolver bằng một cấu hình mới làm mất các giá trị cần thiết hoặc tạo hai cơ chế xử lý không nhất quán.

### 8.4. Mọi confidential client có bắt buộc bật bằng cách này không?

Không nên coi một đoạn Java là câu trả lời duy nhất cho tất cả phiên bản Spring Security. Hành vi mặc định, tích hợp PKCE và API tùy chỉnh có thể thay đổi theo dòng phiên bản và loại client. Trong một dự án cụ thể, điều cần đảm bảo là:

1. Authorization request có `code_challenge`/`code_challenge_method=S256`.
2. AS chấp nhận và lưu challenge với code.
3. Token request chứa đúng `code_verifier`.
4. Khi dùng confidential client, client authentication vẫn được thực hiện.
5. Khi token request không có verifier hoặc verifier sai, AS từ chối.

Tài liệu chính thức của Spring Security cho phiên bản đang dùng và cấu hình AS là nơi xác định API phù hợp. Tránh bỏ bảo vệ PKCE chỉ vì “đã có secret”.

### 8.5. Các bean lưu authorization request

Spring Security cần giữ trạng thái giữa hai yêu cầu HTTP:

~~~text
Request 1: /oauth2/authorization/server-demo
       -> tạo state, verifier, challenge
       -> lưu authorization request
       -> redirect sang AS

Request 2: /login/oauth2/code/server-demo?code=...&state=...
       -> lấy authorization request ban đầu
       -> đối chiếu state
       -> lấy verifier đã lưu
       -> đổi code lấy token
~~~

Trong Servlet, thành phần lưu yêu cầu khởi tạo thường là `AuthorizationRequestRepository<OAuth2AuthorizationRequest>`; triển khai dựa trên HTTP session là một lựa chọn phổ biến. Một custom repository dùng cookie, database hoặc distributed session phải **giữ nguyên dữ liệu PKCE cần thiết**, đặc biệt verifier được framework đặt trong request attributes.

Nếu custom code chỉ serialize các tham số URL mà làm rơi `code_verifier` hoặc dữ liệu correlation, token exchange có thể báo `invalid_grant` dù authorization request ban đầu có challenge hợp lệ.

**Không ghi verifier hoặc toàn bộ authorization request chứa bí mật vào log**. Không gửi verifier qua browser redirect đến AS khi bắt đầu authorize.

## 9. Cách tạo verifier và challenge bằng Java để hiểu thuật toán

Trong ứng dụng Spring Security thông thường, nên để framework tự quản lý PKCE. Để hiểu rõ S256, có thể quan sát cách Java sinh hai giá trị với `SecureRandom`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceValues {

    private static final SecureRandom RANDOM = new SecureRandom();

    private PkceValues() {
    }

    public static String newCodeVerifier() {
        byte[] randomBytes = new byte[32];
        RANDOM.nextBytes(randomBytes);

        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(randomBytes);
    }

    public static String s256Challenge(String verifier) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(
                "SHA-256 is required for PKCE S256", exception);
        }
    }
}
~~~

Cách dùng về mặt thuật toán:

~~~java
String verifier = PkceValues.newCodeVerifier();
String challenge = PkceValues.s256Challenge(verifier);

// Authorization request: gửi challenge và method S256.
// Token request: gửi chính verifier này.
~~~

Điều cần quan sát:

- `SecureRandom` tạo 32 byte ngẫu nhiên có entropy cao.
- Base64URL không padding tạo verifier có ký tự hợp lệ.
- `SHA-256` biến verifier thành digest 32 byte.
- Challenge dùng Base64URL không padding.
- **Verifier và challenge được sinh một lần cho mỗi giao dịch**, sau đó verifier phải được lưu đúng vị trí cho callback.

Đoạn Java này chỉ nhằm minh họa công thức; **không kết hợp nó với `withPkce()` rồi sinh verifier thứ hai**. Nếu đã sử dụng Spring Security PKCE customizer, hãy để framework quản lý nguồn dữ liệu nhất quán.

## 10. PKCE, state và nonce: ba cơ chế không được nhầm lẫn

Trong một OIDC Authorization Code Flow, có thể nhìn thấy cả ba:

~~~http
GET /authorize?response_type=code
  &client_id=spring-web-client
  &scope=openid%20profile
  &state=RANDOM_STATE
  &nonce=RANDOM_NONCE
  &code_challenge=S256_CHALLENGE
  &code_challenge_method=S256 HTTP/1.1
Host: id.example.com
~~~

| Giá trị | Nơi gửi ban đầu | Nơi đối chiếu về sau | Mục tiêu |
|---|---|---|---|
| `state` | Authorization request | Authorization response/callback | Gắn phản hồi với yêu cầu đã khởi tạo; giảm nguy cơ CSRF/nhầm giao dịch. |
| `code_challenge` + `code_verifier` (PKCE) | Challenge ở authorize, verifier ở token endpoint | Token request | Ràng buộc authorization code với bên giữ verifier của yêu cầu ban đầu. |
| `nonce` trong OIDC | Authorization request | Claim `nonce` của ID Token khi đã sử dụng | Liên kết ID Token với lần xác thực OIDC tương ứng, hạn chế replay. |

### 10.1. PKCE có thay thế state hoàn toàn không?

Các hướng dẫn OAuth2 hiện đại xem PKCE là một cơ chế quan trọng và có thể đóng vai trò chống một số kiểu CSRF khi các điều kiện bảo vệ của Authorization Server/client được đáp ứng. Tuy nhiên, trong ứng dụng Spring Security có session/callback và khả năng nhiều provider, **tiếp tục sử dụng `state` theo quy trình mặc định là lựa chọn phù hợp** để tương quan authorization response.

Không bỏ state một cách tùy tiện sau khi bật PKCE. PKCE cũng không thay thế việc phân biệt đúng issuer, client registration, redirect URI hoặc giải quyết mọi nguy cơ login mix-up.

### 10.2. PKCE có kiểm tra ID Token không?

Không. PKCE bảo vệ trao đổi authorization code; ID Token của OIDC vẫn phải được xác minh về:

- chữ ký hoặc phương thức bảo vệ token tương ứng;
- `iss` đúng OpenID Provider đã tin cậy;
- `aud` chứa client ID của ứng dụng;
- `exp` và các điều kiện thời gian;
- `nonce` nếu đã yêu cầu;
- các ràng buộc OIDC khác khi phù hợp.

Kẻ tấn công có thể bị chặn đổi code nhờ PKCE, nhưng client không vì vậy được bỏ qua xác minh ID Token.

### 10.3. PKCE có phải mã hóa code không?

Không. Authorization code thường vẫn xuất hiện trong callback URL; `code_challenge` xuất hiện ở authorization request. PKCE **ràng buộc** việc đổi code với verifier, không “mã hóa” code và không làm code biến mất khỏi front channel.

Do đó vẫn cần HTTPS, callback URI chính xác, code có thời hạn ngắn/dùng một lần, chính sách log và cơ chế tránh rò rỉ URL.

## 11. Một số lớp bảo vệ bổ sung cho public và confidential client

PKCE chỉ là một thành phần trong mô hình bảo mật của Authorization Code Grant.

### 11.1. Redirect URI phải được kiểm soát

Provider cần áp dụng allowlist và quy tắc so khớp redirect URI an toàn cho client. Nếu callback có thể bị chuyển đến một URL không thuộc ứng dụng, code có thể bị lộ trước khi client có cơ hội đổi token.

PKCE giúp giảm hậu quả của code interception nhưng **không hợp thức hóa redirect URI bị mở tùy ý**.

### 11.2. HTTPS và client authentication vẫn quan trọng

Dùng TLS cho authorization/token endpoints và các redirect URI production phù hợp. Public client không có secret tin cậy; confidential client cần giữ secret/private key ở backend. HTTP Basic với client secret chỉ là một phương thức truyền credential, **Base64 không phải mã hóa bảo mật**.

### 11.3. Authorization code phải ngắn hạn và dùng một lần

AS phải ràng buộc code với client, callback và challenge; từ chối code hết hạn, dùng lại hoặc không hợp lệ. Một code không được đổi thành token vô hạn lần, dù verifier khớp.

### 11.4. Không để verifier xuất hiện ở nơi không cần thiết

Không đưa `code_verifier` vào:

- URL authorize;
- query parameter callback;
- URL gửi sang site khác;
- log, monitoring event hoặc exception message công khai;
- JavaScript public trong mô hình backend confidential client.

Verifier được giữ ở đúng phía client khởi tạo giao dịch và chỉ gửi trong token request đến đúng AS.

### 11.5. Không chấp nhận PKCE downgrade

Một AS hỗ trợ PKCE cần buộc verifier khớp với challenge đã gắn code. Nếu client đăng ký là public client và AS yêu cầu PKCE, authorization request thiếu challenge phải bị xử lý theo chính sách bắt buộc, thay vì âm thầm cấp code không có ràng buộc.

Nếu attacker có thể loại bỏ challenge khi authorize và AS vẫn chấp nhận code không PKCE, cơ chế chống chặn code có thể bị hạ cấp. Vì vậy **cả client và AS đều có trách nhiệm duy trì yêu cầu PKCE**.

### 11.6. Token và phiên ứng dụng vẫn cần được bảo vệ

Sau code exchange, access token và refresh token (nếu có) cần được bảo vệ tùy kiến trúc. Trong backend Spring Boot, token nên ở kho authorized client phù hợp, không đưa ra trình duyệt vô cớ. Session cookie nên được cấu hình an toàn.

PKCE không ngăn kẻ đã lấy được access token sử dụng token đó trong mọi tình huống. Khi cần bảo vệ token theo sender, hệ thống có thể dùng những cơ chế riêng như DPoP hoặc mTLS nếu AS/API hỗ trợ; chúng giải quyết vấn đề khác và không mặc nhiên được thay thế bởi PKCE.

## 12. Đọc authorization request trong Spring Security để hiểu PKCE

Từ trình duyệt, khởi tạo login:

~~~text
http://localhost:8080/oauth2/authorization/public-demo
http://localhost:8080/oauth2/authorization/server-demo
~~~

Giả sử provider cho phép callback localhost trong môi trường phát triển. Với công cụ mạng trong browser, thường thấy chuỗi redirect:

~~~text
GET /oauth2/authorization/server-demo
    302 Location: https://id.example.com/authorize?...

GET https://id.example.com/authorize
    response_type=code
    client_id=...
    state=...
    code_challenge=...
    code_challenge_method=S256

GET /login/oauth2/code/server-demo?code=...&state=...
    Spring Security xử lý callback
~~~

Các giá trị cần đọc trong authorization request:

- `response_type=code`: đang dùng Authorization Code Flow.
- `code_challenge_method=S256`: client dùng PKCE với SHA-256.
- `code_challenge`: challenge phải có giá trị khác nhau qua các request với verifier riêng.
- `state`: Spring Security dùng để tương quan callback.
- `redirect_uri`: khớp callback mà AS đã cho phép.
- `client_id`: đúng registration phía provider.

**Không thể chỉ dựa vào DevTools browser để kết luận token request đã gửi verifier đúng trong mô hình server-side.** POST `/token` được Spring Boot backend thực hiện trực tiếp tới AS. Nên xác nhận bằng logging có kiểm soát, dữ liệu trace đã che bí mật, hoặc quan sát request hợp lệ ở môi trường kiểm thử, tránh in `code_verifier`/access token ra console và log production.

### 12.1. Đừng tự đổi code bằng tay để “thử PKCE” trên production

Nếu sao chép code từ callback rồi gửi lại token endpoint, code có thể đã được Spring Security đổi một lần và bị vô hiệu hóa. Request thứ hai sẽ báo `invalid_grant`, không nhất thiết là lỗi PKCE.

Để xác minh hành vi PKCE, sử dụng một giao dịch mới trong môi trường kiểm thử và công cụ phù hợp theo chính sách hệ thống. Không ghi lại code/token/secret có thể dùng thực trong báo cáo hay tài liệu.

## 13. Phân tích kịch bản bảo mật

### Kịch bản A — Public client có PKCE, attacker chỉ lấy được code

Giả sử client tạo verifier `V1` và challenge `C1`, AS phát code `K1`. Attacker chặn được `K1` nhưng không có `V1`.

Nếu AS kiểm tra PKCE đúng, request đổi code bằng verifier ngẫu nhiên `V2` bị từ chối. Đây là tình huống PKCE được thiết kế để giảm thiểu.

### Kịch bản B — Confidential client có secret nhưng không có PKCE

Client sử dụng client authentication hợp lệ khi đổi code, nhưng một authorization code không được ràng buộc với verifier riêng theo yêu cầu authorize.

Client secret giúp bảo vệ token endpoint khỏi những bên không thể xác thực client, nhưng không đem lại cùng bằng chứng theo **từng authorization request** như PKCE. Với mô hình hiện đại, nên bổ sung PKCE cho cả confidential client.

### Kịch bản C — Confidential client có secret và PKCE

Attacker nắm được một authorization code nhưng không có verifier. Ngay cả nếu một endpoint bị cấu hình cho phép một request từ client hợp lệ, AS vẫn phải yêu cầu verifier khớp challenge của code trước khi cấp token.

Đây là lớp kiểm tra bổ sung độc lập với xác thực client.

### Kịch bản D — Verifier bị lưu sai giao dịch

Người dùng mở hai phiên đăng nhập gần nhau:

~~~text
Giao dịch G1: verifier V1 -> challenge C1 -> code K1
Giao dịch G2: verifier V2 -> challenge C2 -> code K2
~~~

Nếu custom code lấy nhầm `V2` để đổi `K1`, AS từ chối dù cả verifier đều có cú pháp hợp lệ. Vì thế không lưu verifier vào một biến global dùng chung cho mọi request.

### Kịch bản E — AS bỏ qua verifier

Client gửi challenge khi authorize, nhưng AS phát token cho code ngay cả khi `code_verifier` không có hoặc sai.

Đây là **lỗi bảo vệ PKCE phía Authorization Server**. Chỉ bật customizer trên client không đảm bảo an toàn nếu AS không thực thi đối chiếu.

### Kịch bản F — SPA bị XSS

PKCE có thể giúp chống attacker chỉ chặn được authorization code qua redirect, nhưng nếu mã JavaScript độc hại đang chạy trong chính origin SPA, attacker có thể đọc dữ liệu mà SPA có thể đọc.

Cách bảo vệ cần bao gồm giảm XSS, cách quản lý token an toàn, thư viện OAuth2 tin cậy và cấu hình browser thích hợp. PKCE không thay thế những biện pháp này.

### Kịch bản G — Client có PKCE nhưng callback sai issuer

Ứng dụng tích hợp nhiều IdP và nhận response từ provider không tương ứng với yêu cầu khởi tạo.

PKCE không thay thế việc ràng buộc đúng issuer/provider. Ứng dụng phải liên kết authorization request với đúng registration, kiểm tra `state`, issuer/ID Token theo giao thức và ngăn nhầm lẫn provider.

## 14. Lỗi thường gặp khi cấu hình PKCE

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Authorization endpoint báo thiếu PKCE | Client không gửi `code_challenge` hoặc `code_challenge_method` | Bật PKCE S256 trong resolver/client library; xác nhận policy AS. |
| Token endpoint trả `invalid_grant` | Verifier sai/thiếu, code hết hạn/dùng lại, redirect URI sai hoặc client không khớp | Kiểm tra tương quan giao dịch và từng điều kiện; không khẳng định ngay chỉ do PKCE. |
| Callback báo `invalid_state` | State không khớp hoặc mất authorization request/session | Kiểm tra cookie, session, load balancer, đường callback và repository lưu request. |
| Public client gửi client secret nhưng AS từ chối | Client được đăng ký `none` hoặc secret không hợp lệ | Bỏ secret nhúng ở public client; dùng client ID và PKCE theo registration. |
| Confidential client gửi PKCE nhưng token request thiếu secret/khóa | Cấu hình client authentication không đúng | Bật đúng phương thức đã đăng ký; PKCE không thay client authentication. |
| Đã bật `withPkce()` nhưng không tìm thấy verifier lúc callback | Custom `AuthorizationRequestRepository` làm rơi request attributes hoặc phiên bị mất | Giữ dữ liệu authorization request giữa redirect và callback. |
| Verifier thay đổi trước token request | Sinh mới hoặc dùng biến global cho nhiều login | Sinh một lần cho từng giao dịch và lưu theo state/request. |
| `S256` challenge không khớp dù verifier tưởng đúng | Dùng Base64 chuẩn, có padding, băm sai encoding hoặc trim verifier | Dùng ASCII + SHA-256 + Base64URL không padding; không sửa verifier sau khi sinh. |
| AS chỉ chấp nhận `plain` | AS quá cũ hoặc cấu hình không tương thích | Kiểm tra khả năng và chính sách nâng cấp; không âm thầm hạ cấp. |
| Spring Security dùng Servlet nhưng cấu hình class reactive | Import sai API stack | Dùng `HttpSecurity`/`SecurityFilterChain` cho Servlet; reactive classes cho WebFlux. |
| Đăng nhập OIDC thành công nhưng API báo `401` | Access token không hợp lệ/không đúng audience hoặc hết hạn | Kiểm tra access token và cấu hình resource server; không phải lỗi PKCE nếu code đã đổi thành công. |
| Mất đăng nhập khi callback qua nhiều instance | Session lưu cục bộ hoặc cookie/forwarded headers cấu hình sai | Dùng session store và routing phù hợp; bảo đảm callback nhìn thấy request ban đầu. |
| Client `server-demo` không tìm thấy | Registration ID không tồn tại hoặc tên khác | Đồng bộ URL `/oauth2/authorization/{registrationId}` với repository. |
| Callback URL `http` thay vì `https` sau reverse proxy | `{baseUrl}` dùng scheme/host nội bộ | Cấu hình forwarded headers đáng tin cậy và redirect URI đã đăng ký. |

### 14.1. Phân biệt lỗi PKCE và lỗi client authentication

Lỗi `invalid_client` thường liên quan client authentication: secret/khóa sai, phương thức xác thực không phù hợp, header thiếu hoặc registration không hợp lệ.

Lỗi `invalid_grant` có thể xuất phát từ code không hợp lệ, redirect URI không khớp, PKCE verifier sai hoặc những điều kiện khác. Phải xem **error description và hành vi AS trong ngữ cảnh an toàn** thay vì đoán dựa vào duy nhất mã lỗi.

### 14.2. Thứ tự khoanh vùng sự cố

Khi login lỗi, có thể lần lượt xác định:

1. Client đã gửi authorization request đúng registration ID chưa?
2. Có challenge S256 hay không?
3. AS có yêu cầu và lưu challenge với code không?
4. Callback có đi về đúng redirect URI và state không?
5. Client có lấy lại đúng authorization request/verifier không?
6. Token request có gửi verifier cùng code và client authentication phù hợp không?
7. AS trả lỗi gì, ở bước nào?
8. Sau khi nhận token, OIDC validation/authorization của ứng dụng có thành công không?

Đây là thứ tự quan sát luồng giao thức, không phải quy trình đọc log chứa bí mật. Khi tạo trace/debug log, phải che code, token, verifier và credential.

## 15. Áp dụng trong ứng dụng có nhiều client registrations

Một ứng dụng có thể vừa có public registration vừa có confidential registration, hoặc nhiều confidential registrations với provider khác nhau:

~~~text
Registration "mobile":
  Client type: public
  Client authentication: none
  PKCE: S256

Registration "web":
  Client type: confidential
  Client authentication: client_secret_basic
  PKCE: S256

Registration "enterprise":
  Client type: confidential
  Client authentication: private_key_jwt
  PKCE: S256
~~~

Các registration có thể cùng grant `authorization_code` nhưng khác client ID, callback, scope và token endpoint. **PKCE verifier phải thuộc đúng authorization request và registration**. Không lưu một verifier dùng cho cả ba registrations hoặc tự lấy challenge từ một request khác.

Spring Security chọn registration theo đường dẫn khởi tạo `/oauth2/authorization/{registrationId}` và dữ liệu đã lưu; custom resolver phải giữ tương quan chính xác để callback dùng đúng registration.

Nếu trong ứng dụng nhiều issuer, cần bảo vệ thêm các vấn đề issuer mix-up bằng cơ chế tương quan provider và xác minh token đúng issuer. PKCE tự nó không xác nhận rằng token đến từ một issuer đáng tin cậy.

## 16. Ví dụ lựa chọn cấu hình theo tình huống

### 16.1. Ứng dụng Spring Boot MVC có backend giữ secret

**Mục tiêu:** người dùng đăng nhập OIDC vào một portal; backend giữ access token và session.

Cách tiếp cận:

- Registration là **confidential client**.
- Spring Security Servlet `oauth2Login()` xử lý Authorization Code Flow.
- Token endpoint dùng client authentication đã đăng ký.
- Bật PKCE S256, chẳng hạn qua `withPkce()` khi cần bảo đảm đối với phiên bản/cấu hình hiện tại.
- Lưu authorization request/verifier theo phiên, bảo vệ cookie/session.
- Xác minh ID Token OIDC và quản lý authorized client/token ở backend.

Đây thường là thiết kế phù hợp cho Spring Boot web application có khả năng giữ bí mật.

### 16.2. SPA được phục vụ tĩnh bởi Spring Boot nhưng chạy trong browser

**Mục tiêu:** mã JavaScript chạy trong browser tự thực hiện OAuth2 authorization code flow.

Cách tiếp cận:

- Browser app là **public client**, không thể giữ client secret.
- SPA dùng OAuth2/OIDC client library hỗ trợ Authorization Code + PKCE.
- AS phải thực thi PKCE, đăng ký redirect URI của SPA và chính sách CORS/token endpoint khi phù hợp.
- Không giả định `oauth2Login()` ở backend tự điều khiển token exchange do SPA thực hiện; đây là hai mô hình client khác nhau.

Nếu thay bằng BFF để token được giữ ở server, backend Spring Boot lại trở thành confidential OAuth2 client cho luồng đó.

### 16.3. Spring Boot tích hợp IdP nội bộ yêu cầu PKCE cho mọi client

**Mục tiêu:** bất kể web confidential hay public client, AS đều bắt buộc S256.

Cách tiếp cận:

- Cấu hình mỗi client registration với grant `authorization_code` và phương thức client authentication phù hợp.
- Bật S256 cho mọi authorization request.
- Đảm bảo token request có `code_verifier` đúng cho mỗi code.
- AS từ chối authorization request thiếu challenge hoặc token request sai verifier theo policy.
- Quan sát luồng khi triển khai, đặc biệt custom resolver và store phiên.

Không bỏ qua chính sách bắt buộc của AS chỉ vì một thư viện từng có hành vi mặc định khác.

## 17. Một bài tập tư duy về PKCE

Giả sử hai yêu cầu đăng nhập được khởi tạo đồng thời:

~~~text
G1: verifier = V1, challenge = C1, code = K1
G2: verifier = V2, challenge = C2, code = K2
~~~

**Câu hỏi 1.** Có thể dùng `V2` để đổi `K1` không?

**Trả lời:** Không. AS cần kiểm tra challenge dẫn xuất từ `V2` với `C1` đã gắn `K1`; hai giá trị không khớp, nên phải từ chối.

**Câu hỏi 2.** Nếu client là confidential và gửi đúng client secret, có thể bỏ `V1` để đổi `K1` không?

**Trả lời:** Không nếu `K1` đã được cấp kèm PKCE. Client authentication và kiểm tra PKCE là các điều kiện bổ sung nhau.

**Câu hỏi 3.** Nếu client đổi `K1` thành công rồi gửi lại `K1` kèm `V1`, có nhận thêm token không?

**Trả lời:** Không. Authorization code phải được dùng một lần; verifier khớp không cho phép đổi lại code đã sử dụng.

**Câu hỏi 4.** Nếu biết `C1` từ URL authorize, có lấy lại được `V1` không?

**Trả lời:** Khi verifier được sinh ngẫu nhiên đủ mạnh và dùng S256, việc suy ngược từ challenge đến verifier không khả thi trong mô hình đe dọa dự kiến. Nếu client dùng verifier dễ đoán hoặc cố định, bảo vệ sẽ yếu đi.

**Câu hỏi 5.** Trong OIDC, PKCE đã khớp thì có thể bỏ kiểm tra `nonce` hoặc chữ ký ID Token không?

**Trả lời:** Không. PKCE kiểm tra tính liên tục của code exchange; nonce và ID Token validation bảo vệ mục tiêu khác.

**Câu hỏi 6.** Một SPA có client ID và một client secret hardcode trong JavaScript thì được coi là confidential client không?

**Trả lời:** Không. Bí mật hardcode trong JavaScript không thể bảo vệ đáng tin cậy; SPA vẫn là public client.

**Câu hỏi 7.** `code_challenge_method=S256` đi ở authorization request hay token request?

**Trả lời:** Ở authorization request cùng challenge. Token request mang verifier gốc để AS tự tính và đối chiếu.

**Câu hỏi 8.** Token request lỗi `invalid_grant` có chắc là PKCE sai không?

**Trả lời:** Không. Code hết hạn, dùng lại, redirect URI hoặc client binding sai cũng có thể dẫn đến lỗi này.

## 18. Ghi nhớ theo từng thành phần

| Thành phần/giá trị | Public client | Confidential client |
|---|---|---|
| `response_type=code` | Có | Có |
| `code_challenge` và `code_challenge_method=S256` | Gửi khi authorize | Gửi khi authorize |
| `code_verifier` | Sinh riêng, giữ theo giao dịch | Sinh riêng, giữ theo giao dịch |
| `state` | Tạo và đối chiếu khi callback | Tạo và đối chiếu khi callback |
| `client_id` | Có | Có |
| `client_secret`/private key | Không lưu bí mật lâu dài đáng tin cậy | Lưu ở backend và dùng theo registration |
| Token request | `code` + `code_verifier` và tham số phù hợp | `code` + `code_verifier` **và** client authentication |
| Thực thể kiểm tra PKCE | Authorization Server | Authorization Server |
| Sau khi nhận token | Bảo vệ token theo môi trường public | Bảo vệ token trong backend, quản lý session |
| OIDC ID Token validation | Vẫn bắt buộc khi dùng OIDC | Vẫn bắt buộc khi dùng OIDC |

Điều cần nhớ là **PKCE không phải một grant mới**. Nó thêm **bằng chứng theo từng giao dịch** vào Authorization Code Grant. Client gửi `code_challenge` khi bắt đầu authorize và gửi `code_verifier` gốc khi đổi code; AS phải ràng buộc cả hai với cùng authorization code. **Public client cần PKCE** vì không thể dựa vào secret nhúng trong ứng dụng, còn **confidential client nên dùng PKCE cùng với client authentication** để bảo vệ tốt hơn.

Trong Spring Security OAuth2/OIDC Client, hãy dùng khả năng PKCE của framework, cấu hình đúng loại `ClientRegistration`, và đảm bảo dữ liệu authorization request được lưu xuyên suốt callback. Với Servlet, `OAuth2AuthorizationRequestCustomizers.withPkce()` kết hợp `DefaultOAuth2AuthorizationRequestResolver` là một cách chủ động bật PKCE cho confidential client; với public client, Spring Security hỗ trợ PKCE trong luồng đăng ký không xác thực client. Trong cả hai trường hợp, **khâu xác minh cuối cùng phải được thực thi bởi Authorization Server**.
