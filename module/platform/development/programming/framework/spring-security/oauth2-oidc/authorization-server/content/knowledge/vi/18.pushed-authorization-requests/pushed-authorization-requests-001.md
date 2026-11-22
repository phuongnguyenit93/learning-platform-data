# Mục đích của Pushed Authorization Requests

> **Chương: PAR.** Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**: học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Trọng tâm của bài là **Pushed Authorization Requests (PAR) giải quyết vấn đề gì**, luồng giao thức theo **RFC 9126**, giá trị bảo mật và giới hạn của PAR khi triển khai thực tế.

## 1. Vấn đề của authorization request đi qua trình duyệt

Trong Authorization Code Flow thông thường, OAuth2/OIDC Client đưa người dùng tới authorization endpoint của Authorization Server bằng một URL chứa nhiều tham số:

```http
GET /oauth2/authorize?response_type=code
    &client_id=portal-web
    &redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal
    &scope=openid%20profile%20orders.read
    &state=STATE_RANDOM
    &nonce=NONCE_RANDOM
    &code_challenge=PKCE_CHALLENGE
    &code_challenge_method=S256
Host: login.example.vn
```

Đây là ví dụ **trình bày trên nhiều dòng cho dễ đọc**; request thực tế phải là một URL được encode hợp lệ. Những giá trị viết hoa là placeholder, không dùng trực tiếp trong môi trường thật.

Cơ chế này đơn giản và được hỗ trợ rộng rãi, nhưng có ba nhược điểm cơ bản:

1. **Tính toàn vẹn của request trước khi server xử lý:** các tham số nằm trong URL mà trình duyệt chuyển tiếp. HTTPS bảo vệ kết nối tới authorization endpoint, nhưng tự nó không chứng minh mọi tham số trong URL đều do **client đã đăng ký** tạo ra. Việc sửa `scope`, `redirect_uri`, `claims` hoặc ngữ cảnh giao dịch cần được kiểm soát ở AS.
2. **Quyền riêng tư:** query string có thể xuất hiện trong browser history, reverse proxy/access log, telemetry, Referer hoặc ảnh chụp màn hình. Các tham số mở rộng như `claims`, `authorization_details`, `login_hint` có thể chứa thông tin nhạy cảm hơn một scope thông thường.
3. **Giới hạn độ dài URL:** authorization request lớn (nhiều claim, rich authorization details, Request Object) có thể chạm giới hạn của trình duyệt, gateway, WAF hoặc proxy.

**PAR (RFC 9126)** giải quyết ba vấn đề này bằng cách chuyển **phần lớn dữ liệu authorization request khỏi URL trình duyệt** sang một kết nối trực tiếp từ client tới Authorization Server. <https://www.rfc-editor.org/rfc/rfc9126.html>

### 1.1. Ví dụ thực tế

Giả sử hệ thống có:

- **Authorization Server/OpenID Provider:** `https://login.example.vn`.
- **Confidential client:** `portal-web` chạy ở `https://portal.example.vn`.
- **Callback:** `https://portal.example.vn/login/oauth2/code/portal`.
- **Resource Server:** `https://api.example.vn` với scope `orders.read`.
- **Dữ liệu cần xin quyền:** `openid profile orders.read`, `state`, `nonce` và PKCE S256.

Trong luồng thông thường, những tham số trên đều ở URL khi bắt đầu xác thực. Với PAR, backend `portal-web` **POST bộ tham số trực tiếp đến `/oauth2/par` trước**, nhận một `request_uri` tham chiếu ngắn hạn, sau đó mới điều hướng trình duyệt tới `/oauth2/authorize?client_id=...&request_uri=...`.

Kết quả: trình duyệt không cần mang toàn bộ nội dung authorization request ban đầu, còn Authorization Server đã có cơ hội xác thực client và kiểm tra đầu vào **trước khi người dùng tương tác**.

## 2. PAR là gì và không phải là gì?

**Pushed Authorization Requests** là một cơ chế khởi tạo authorization request gồm **hai chặng**:

1. **Back-channel:** client gửi HTTP POST đến **Pushed Authorization Request Endpoint** ở AS, chứa các tham số của authorization request và thông tin xác thực client theo phương thức đã đăng ký.
2. **Front-channel:** client đưa user agent đến authorization endpoint thông thường, chủ yếu với `client_id` và **`request_uri` do AS vừa cấp**. AS tìm lại request đã được đẩy và tiếp tục đăng nhập/consent/authorization code như bình thường.

```mermaid
flowchart LR
    Client["OAuth2/OIDC Client<br/>portal-web"] -->|"POST trực tiếp<br/>/oauth2/par + request data"| AS["Authorization Server"]
    AS -->|"201: request_uri + expires_in"| Client
    Client -->|"302 đến /oauth2/authorize?<br/>client_id&request_uri"| Browser["Trình duyệt"]
    Browser -->|"GET /oauth2/authorize<br/>chỉ mang tham chiếu"| AS
    AS -->|"Đăng nhập / consent, sau đó code + state"| Browser
    Browser -->|"Callback hợp lệ"| Client
    Client -->|"POST /oauth2/token<br/>code + code_verifier"| AS
```

| Khái niệm | Ý nghĩa |
|---|---|
| **PAR endpoint** | HTTP API nhận authorization request trước khi điều hướng người dùng; mặc định trong Spring Authorization Server 1.5.x là `/oauth2/par` khi endpoint được cấu hình |
| **Authorization endpoint** | Endpoint tương tác với người dùng và tiếp tục cấp quyền, mặc định `/oauth2/authorize` |
| **`request_uri`** | Tham chiếu khó đoán, có thời hạn ngắn, gắn với đúng client và request đã lưu |
| **`expires_in`** | Thời gian tính bằng giây mà tham chiếu có hiệu lực; không phải access token TTL |
| **OAuth authorization code** | Mã được phát **sau** khi authorization thành công, rồi đổi token tại `/oauth2/token` |
| **ID Token/access token** | Token chỉ xuất hiện ở các bước cấp token phù hợp, **không phải response của PAR** |

**Điểm cốt lõi:** PAR **không** tự đăng nhập người dùng, không phát authorization code/access token/ID Token và không tự cấp consent. Thành công của `POST /oauth2/par` chỉ nghĩa là AS đã chấp nhận **đầu vào authorization request** ở giai đoạn chuẩn bị và trả một tham chiếu để tiếp tục luồng.

### 2.1. Không nhầm `request_uri` với các URI/token khác

- `request_uri` của PAR **không phải** `redirect_uri` của client. `redirect_uri` vẫn là callback đã đăng ký, nơi browser quay về **sau authorization**.
- `request_uri` của PAR **không phải** `authorization_code`, access token, refresh token, ID Token hoặc client secret.
- Tham chiếu PAR dạng `urn:ietf:params:oauth:request_uri:...` **không nhất thiết là URL có thể GET trực tiếp**. Giá trị đó giúp **Authorization Server tự tra request**; client/user agent không tự truy cập URN để lấy dữ liệu gốc.
- `request_uri` được phép xuất hiện trong URL trình duyệt nhưng vẫn cần bảo vệ khỏi replay, swapping và log ngoài ý muốn.

## 3. So sánh luồng truyền thống và luồng PAR

| Tiêu chí | Authorization request trực tiếp | Authorization request sử dụng PAR |
|---|---|---|
| Nơi client gửi request data | Query URL qua user agent | HTTP POST trực tiếp tới AS qua HTTPS |
| URL browser trước login | Có `response_type`, `redirect_uri`, `scope`, `state`, PKCE và extensions | Thường chỉ có `client_id` và `request_uri` |
| Xác thực client **trước login** | Thường chưa có bước client authentication ở authorization endpoint | PAR áp dụng quy tắc client authentication của token endpoint cho request trực tiếp |
| Khả năng sửa tham số trên browser URL | Các tham số ban đầu nằm trong front-channel; AS phải validate chặt | AS sử dụng bản request đã nhận qua back-channel, ràng buộc với client |
| Rủi ro lộ dữ liệu request qua URL | Cao hơn nếu request chứa dữ liệu nhạy cảm | Giảm đáng kể, nhưng **không loại bỏ mọi rò rỉ** |
| Request dài/rich details | Dễ gặp giới hạn URL | Dữ liệu lớn nằm ở POST body; vẫn cần giới hạn kích thước |
| Phụ thuộc hạ tầng | Authorization endpoint | Thêm PAR endpoint, persistence/cache và client HTTP |
| PKCE, `state`, `nonce` | Vẫn cần theo loại luồng | **Vẫn cần**, không bị thay thế bởi PAR |
| Login và consent | Tại AS | **Không thay đổi bản chất** |
| Token endpoint | Đổi code lấy token | **Cùng token endpoint**, code vẫn phải được kiểm tra |

**Lợi ích lớn nhất của PAR** là AS nhận **một yêu cầu toàn vẹn hơn về mặt kênh truyền**, từ client trực tiếp (có thể được xác thực) trước khi trình duyệt xuất hiện. Tính toàn vẹn này dựa vào HTTPS, client authentication phù hợp và việc AS lưu/ràng buộc request; **PAR không tự tạo chữ ký số trên request payload**.

## 4. Toàn bộ luồng theo RFC 9126

### 4.1. Bước 1 — Client chuẩn bị request và PKCE

Client tạo dữ liệu giao dịch độc lập:

```text
client_id:          portal-web
response_type:      code
redirect_uri:       https://portal.example.vn/login/oauth2/code/portal
scope:              openid profile orders.read
state:              STATE_RANDOM
nonce:              NONCE_RANDOM
code_verifier:      PRIVATE_PKCE_VERIFIER
code_challenge:     BASE64URL(SHA256(code_verifier))
code_challenge_method: S256
```

Giữ `code_verifier`, `state` và `nonce` cùng authorization transaction phía client. **Không gửi `code_verifier` vào PAR request**; chỉ gửi `code_challenge`. Có thể bổ sung các tham số mở rộng như `resource`, `claims` hoặc `authorization_details` nếu AS và client hỗ trợ.

### 4.2. Bước 2 — Client POST đến PAR endpoint

Với confidential client đăng ký phương thức `client_secret_basic`, một request minh họa:

```http
POST /oauth2/par HTTP/1.1
Host: login.example.vn
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_CREDENTIALS_REDACTED
Accept: application/json

client_id=portal-web&response_type=code&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&scope=openid%20profile%20orders.read&state=STATE_RANDOM&nonce=NONCE_RANDOM&code_challenge=PKCE_S256_CHALLENGE&code_challenge_method=S256
```

Lưu ý:

1. PAR endpoint là **HTTPS URL** và nhận **POST** với body `application/x-www-form-urlencoded` mã hóa UTF-8 theo RFC 9126.
2. Client authentication dùng phương thức đã đăng ký; `Basic ...` chỉ phù hợp confidential client sử dụng `client_secret_basic`. Những cơ chế như `private_key_jwt`/mTLS có cách gửi chứng cứ riêng. Với public client, chính sách về danh tính, authentication method và khả năng hỗ trợ PAR cần được xác nhận theo profile/phiên bản triển khai.
3. Request body chứa **tham số authorization request bình thường**, ngoại trừ **không được gửi tham số `request_uri` vào PAR request**.
4. Không truyền client secret trong URL, không để token/secret thật trong ví dụ và không bật access log chứa toàn bộ POST body trên endpoint này.

### 4.3. Bước 3 — AS xác thực và thẩm định sớm

RFC 9126 yêu cầu AS:

- Áp dụng **client authentication** tương ứng cách xác thực ở token endpoint.
- **Từ chối** PAR request chứa tham số `request_uri`.
- Kiểm tra authorization request như khi nhận ở authorization endpoint: ví dụ `client_id`, `response_type`, `redirect_uri` và `scope` theo registration, PKCE/chính sách khác theo flow.
- Các kiểm tra **cần tương tác người dùng** như login/consent có thể thực hiện sau ở authorization endpoint, không thể coi PAR POST đã hoàn thành chúng.

Một số hệ thống có thể có quy tắc đặc biệt cho redirect URI từng giao dịch của **client được xác thực**, theo RFC 9126 §2.4. **Không mặc định nới exact redirect URI matching** trong Spring Authorization Server; nếu thực sự dùng ngoại lệ này phải có profile/policy, validation và kiểm thử riêng. Hướng mặc định an toàn là redirect URI **khớp chính xác đăng ký**.

### 4.4. Bước 4 — AS trả `request_uri` và `expires_in`

Khi hợp lệ, RFC yêu cầu **HTTP 201 Created** và JSON chứa ít nhất:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-cache, no-store

{
  "request_uri": "urn:ietf:params:oauth:request_uri:PAR_REF_RANDOM",
  "expires_in": 60
}
```

Giá trị trên là **minh họa**; URI thực tế do AS tạo, phải có phần ngẫu nhiên mật mã khó đoán. `expires_in=60` chỉ là ví dụ 60 giây; RFC cho phép AS chọn lifetime và gợi ý khoảng ngắn như 5–600 giây. AS phải **gắn tham chiếu với client** đã gửi request. Không dùng một mã tăng tuần tự dễ đoán làm tham chiếu.

Client lưu `request_uri` trong authorization transaction, dùng nó **một lần** và bắt đầu browser redirect trước khi hết hạn.

### 4.5. Bước 5 — Browser tới authorization endpoint bằng tham chiếu

```http
GET /oauth2/authorize?client_id=portal-web&request_uri=urn%3Aietf%3Aparams%3Aoauth%3Arequest_uri%3APAR_REF_RANDOM HTTP/1.1
Host: login.example.vn
```

AS tra request đã lưu, xác minh giá trị `request_uri` được cấp cho `client_id=portal-web`, còn hiệu lực và chưa bị sử dụng trái chính sách. Sau đó:

1. Thực hiện login nếu chưa có phiên hoặc policy yêu cầu.
2. Hiển thị consent nếu cần.
3. Thực thi validation tại authorization endpoint, đặc biệt khi client policy đã thay đổi kể từ lúc PAR POST.
4. Khi thành công, trả authorization code và `state` về **redirect URI đã được xác minh trong request gốc**.

Không chấp nhận thêm `scope=admin`, `redirect_uri=https://evil.test` hoặc `code_challenge` khác vào request đi qua browser để **ghi đè** request đã push. Chỉ dùng những thông số/ngoại lệ mà RFC, profile và server thực sự cho phép; cách an toàn thường là **tham chiếu không thể bị sửa quyền**.

### 4.6. Bước 6 — Client kiểm tra callback và đổi code

Client nhận callback:

```http
GET /login/oauth2/code/portal?code=AUTH_CODE&state=STATE_RANDOM HTTP/1.1
Host: portal.example.vn
```

Client phải đối chiếu `state` với transaction, kiểm tra issuer/nonce nếu OIDC, dùng `code_verifier` ban đầu và xác thực client khi đổi code qua `POST /oauth2/token`. **PAR không thay Authorization Code, PKCE, code single-use hoặc OAuth2/OIDC callback validation**. Access token/ID Token được nhận ở giai đoạn đổi code, không ở PAR response.

## 5. PAR giúp bảo vệ trước những rủi ro nào?

### 5.1. Giảm lộ request data qua front-channel

Đưa request payload vào back-channel giúp tránh đặt một số trường sau trong URL mà trình duyệt mang đi:

- `scope` dài và chi tiết;
- `claims` của OIDC có thể nhắc tới yêu cầu thông tin người dùng;
- `authorization_details` với chi tiết giao dịch theo Rich Authorization Requests (RAR);
- `resource`/audience được yêu cầu;
- `login_hint` hoặc ngữ cảnh nghiệp vụ nếu ứng dụng có dùng;
- nội dung Request Object lớn khi kết hợp JAR.

**Không suy ra rằng dữ liệu đã được mã hóa đầu cuối hoặc không thể bị quan sát ở backend.** Client, PAR endpoint, reverse proxy, WAF, APM và request storage vẫn xử lý payload; cần hạn chế body logs, mã hóa kết nối, quyền đọc và thời gian lưu.

### 5.2. Giảm thao túng authorization request trong trình duyệt

Khi client đẩy request qua kết nối trực tiếp rồi dùng một `request_uri` bị ràng buộc, browser không thể đơn thuần sửa `scope`, `redirect_uri` hoặc `authorization_details` trong URL để thay đổi bản request đã lưu ở AS. AS cũng có thể từ chối request scope/redirect sai **trước khi chuyển sang login**.

Tuy nhiên, một attacker có thể **đánh cắp, đoán hoặc tráo `request_uri`**. Vì vậy:

- Tham chiếu phải ngẫu nhiên mật mã, không đoán được.
- Phải ràng buộc tham chiếu với đúng `client_id` và policy.
- Client sử dụng tham chiếu **một lần**, AS nên dùng một lần (có thể có ngoại lệ hạn chế cho browser reload theo RFC).
- `state`, PKCE và `nonce` (OIDC) vẫn quan trọng để chống **request URI swapping**, CSRF và nhầm giao dịch.

### 5.3. Xác thực client sớm

Trong Authorization Code Flow thông thường, authorization endpoint thường nhận `client_id` mà chưa yêu cầu client chứng minh nắm secret/private key. PAR tạo một điểm **giao tiếp trực tiếp trước browser** để AS xác thực confidential client theo phương thức đã đăng ký và kiểm tra quyền gửi authorization request.

Điều này giúp chặn sớm:

- yêu cầu giả mạo client khi không có credential hợp lệ;
- redirect URI hoặc scope không đúng policy;
- rich request bất hợp lệ;
- traffic không mong muốn trước khi user phải trải qua login/consent.

**Không nhầm xác thực client với xác thực người dùng.** PAR có thể chạy trước khi biết người dùng nào sẽ đăng nhập; server chưa nên coi một user đã chấp thuận bất kỳ scope nào chỉ vì PAR request nhận `201`.

### 5.4. Hỗ trợ authorization request lớn

PAR sử dụng body POST thay vì URL browser, phù hợp khi request chứa nhiều ngữ cảnh và dữ liệu cấu trúc. Dù vậy **server phải giới hạn body size, timeout và rate** để chống lạm dụng tài nguyên. Không nên dùng PAR để lưu vô hạn JSON hoặc tệp lớn.

## 6. So sánh PAR, PKCE, JAR, JARM và OIDC

Các công nghệ này bảo vệ những điểm khác nhau:

| Cơ chế | Giải quyết chủ yếu | Có thay thế PAR không? |
|---|---|---|
| **PAR — RFC 9126** | Đẩy request qua back-channel, rút gọn front-channel, xác thực/validate sớm | Chính là cơ chế đang học |
| **PKCE — RFC 7636** | Ràng buộc authorization code với `code_verifier` khi đổi token | **Không**; dùng cùng PAR |
| **`state`** | Gắn authorization response với request ở phía client, bảo vệ CSRF/nhầm transaction | **Không**; vẫn nên có và kiểm tra |
| **OIDC `nonce`** | Ràng buộc ID Token với yêu cầu đăng nhập OIDC | **Không**; vẫn cần theo flow |
| **JAR — RFC 9101** | Đóng gói các tham số authorization request thành **JWT Request Object** có chữ ký và có thể mã hóa | Có thể **kết hợp** JAR + PAR để có bảo đảm mật mã riêng |
| **JARM** | Bảo vệ **authorization response** bằng JWT theo profile | Không; bảo vệ giai đoạn **phản hồi**, không phải đẩy request |
| **RAR — RFC 9396** | Biểu diễn yêu cầu ủy quyền giàu cấu trúc qua `authorization_details` | Không; PAR là kênh hữu ích để mang RAR |
| **Authorization Code + client auth** | Phát code và đổi code lấy token theo grant | PAR **không** phải grant type mới |

### 6.1. PAR không tự ký JWT Request Object

Một PAR request có thể truyền **tham số form thường**. Với HTTPS và client authentication, AS có bằng chứng về kênh nhận/khách hàng gửi và có thể lưu yêu cầu toàn vẹn theo thiết kế. Nhưng nếu sản phẩm đòi hỏi **bằng chứng chữ ký số trên chính request payload**, khả năng xác minh độc lập hoặc không thể phủ nhận, hãy xem **JAR (RFC 9101)** và có thể gửi Request Object qua PAR.

Với JAR + PAR, có thể gửi tham số `request` chứa signed Request Object trong PAR POST theo profile được hỗ trợ. Khi client phải dùng signed Request Object, AS phải enforce đúng policy, không chuyển sang chấp nhận form tự do chỉ vì PAR POST đã xác thực.

### 6.2. PAR không loại bỏ các dữ liệu nhạy cảm ở callback

PAR giảm lượng **authorization request data** trong browser URL lúc **bắt đầu** luồng. Nhưng callback Authorization Code Flow vẫn thường chứa `code` và `state`. Client vẫn cần:

- callback chuyên dụng, không nhúng third-party script/analytics;
- `Referrer-Policy: no-referrer` và `Cache-Control: no-store` khi phù hợp;
- không log query string nhạy cảm;
- đổi code nhanh, sử dụng PKCE, redirect sang URL sạch;
- xác minh token/issuer/nonce theo OAuth2/OIDC.

Không quảng bá PAR như một giải pháp “không còn dữ liệu OAuth trong trình duyệt”.

## 7. Vòng đời `request_uri`, replay và tính nhất quán

RFC 9126 yêu cầu một `request_uri` có tham chiếu **khó đoán** và **gắn đúng client**; client **MUST** chỉ sử dụng nó một lần. AS **SHOULD** xử lý một lần, có thể cho phép một số trường hợp tải lại trang theo chính sách; **MUST từ chối tham chiếu đã hết hạn**.

Một bản ghi server-side có thể có cấu trúc minh họa:

```text
PushedAuthorizationRequest {
  requestUri:   "urn:ietf:params:oauth:request_uri:PAR_REF_RANDOM"
  clientId:     "portal-web"
  redirectUri:  "https://portal.example.vn/login/oauth2/code/portal"
  scopes:       ["openid", "profile", "orders.read"]
  state:        "STATE_RANDOM"
  nonce:        "NONCE_RANDOM"
  codeChallenge:"PKCE_CHALLENGE"
  method:       "S256"
  issuedAt:     "2026-11-16T10:00:00Z"
  expiresAt:    "2026-11-16T10:01:00Z"
  consumed:     false
  policyVersion:42
}
```

Đây là **mô hình khái niệm**, không phải schema hoặc API chính thức của Spring. Trong production, cần:

1. **TTL và dọn dẹp:** loại request hết hạn, không giữ vô hạn; giới hạn số PAR request chưa sử dụng mỗi client.
2. **Ràng buộc client:** khi browser gửi `client_id` và `request_uri`, không cho client A dùng tham chiếu được tạo cho client B.
3. **Ngăn replay:** xử lý tiêu thụ tham chiếu theo cơ chế phù hợp, ưu tiên atomicity nếu nhiều pod; mọi ngoại lệ browser reload phải được thiết kế hẹp.
4. **Không tin tham số sửa ở front-channel:** tham số bổ sung không được âm thầm thay scope/callback đã push.
5. **Revalidate policy khi cần:** nếu redirect URI, scope hoặc client credential bị revoke giữa lúc push và lúc authorize, AS phải áp dụng quy tắc hiện tại hoặc từ chối, không dùng “approval vĩnh viễn” từ bước POST.
6. **Bảo vệ storage:** nội dung PAR có thể chứa claims hoặc dữ liệu nghiệp vụ nhạy cảm, cần quyền đọc tối thiểu, retention ngắn và không log nguyên văn.
7. **Consistency khi scale:** mọi AS pod xử lý `/oauth2/authorize` phải tìm được request đã push ở pod khác, hoặc hệ thống phải có cơ chế lưu/truy cập nhất quán.

### 7.1. Một vài tấn công điển hình

| Tấn công/sự cố | Nguy cơ | Cơ chế bảo vệ |
|---|---|---|
| Guess `request_uri` | Truy cập hoặc lạm dụng request của người khác | Tham chiếu CSPRNG, high entropy, TTL ngắn |
| URI swapping | Thay `request_uri` để chuyển người dùng vào request khác | Client state/PKCE/nonce, binding client, transaction validation |
| URI replay | Dùng lại tham chiếu khi user đã authorize | One-time/controlled replay policy |
| Cross-client reference | Client B dùng tham chiếu của A | Server-side binding `client_id` |
| Open redirect | Lái authorization code sang attacker origin | Validate redirect URI và policy, không chấp nhận URI tùy ý |
| Client policy changed | Request cũ còn scope/redirect đã bị revoke | Kiểm tra policy ở bước authorize nếu cần, từ chối |
| Body/log leakage | Dữ liệu nhạy cảm lộ qua proxy/APM | HTTPS, không ghi body, giảm retention |
| PAR endpoint DoS | Client push nhiều request lớn nhưng không dùng | Rate limiting, body-size bound, TTL, quota |
| Lost PAR response | Client không nhận được `request_uri` | Không chuyển browser đến URL tự chế; tạo lại một transaction an toàn theo policy |

## 8. Metadata: client tìm PAR endpoint ở đâu?

Theo RFC 9126, Authorization Server có thể công bố khả năng PAR trong **OAuth 2.0 Authorization Server Metadata** (RFC 8414), ví dụ:

```http
GET /.well-known/oauth-authorization-server HTTP/1.1
Host: login.example.vn
Accept: application/json
```

Ví dụ cấu trúc metadata (rút gọn):

```json
{
  "issuer": "https://login.example.vn",
  "authorization_endpoint": "https://login.example.vn/oauth2/authorize",
  "token_endpoint": "https://login.example.vn/oauth2/token",
  "pushed_authorization_request_endpoint": "https://login.example.vn/oauth2/par",
  "require_pushed_authorization_requests": false
}
```

| Trường metadata | Ý nghĩa |
|---|---|
| `pushed_authorization_request_endpoint` | URL endpoint để client POST request trực tiếp; sự hiện diện cho biết server **có thể hỗ trợ** PAR |
| `require_pushed_authorization_requests` | Nếu `true`, AS yêu cầu authorization requests phải đi qua PAR theo policy toàn server |
| Metadata theo **client** cùng tên | Một client riêng có thể bị yêu cầu dùng PAR ngay cả khi toàn server không bắt buộc |

**Chú ý:** JSON trên là **minh họa**. Đừng khẳng định instance đang chạy có PAR chỉ vì thấy đường dẫn trong tài liệu Spring hoặc có một field cấu hình trong code. Kiểm tra **metadata thực tế**, phương thức hỗ trợ và test POST PAR. Nếu AS yêu cầu PAR, request đến authorization endpoint **không có `request_uri` được PAR cấp** phải bị từ chối `invalid_request` theo RFC 9126.

Với OIDC, client có thể đọc Provider Configuration ở `/.well-known/openid-configuration` nếu OP hỗ trợ OIDC; vẫn phải kiểm tra issuer và các endpoint đang công bố. Không giả định hai discovery document có tất cả field giống hệt nhau ở mọi sản phẩm/phiên bản.

## 9. Spring Authorization Server hỗ trợ PAR ra sao?

Spring Authorization Server 1.5.x hỗ trợ giao thức **RFC 9126** qua:

- `OAuth2AuthorizationServerConfigurer.pushedAuthorizationRequestEndpoint(...)`;
- `OAuth2PushedAuthorizationRequestEndpointConfigurer`;
- `OAuth2PushedAuthorizationRequestEndpointFilter`;
- `OAuth2PushedAuthorizationRequestAuthenticationProvider`;
- `AuthorizationServerSettings.Builder.pushedAuthorizationRequestEndpoint(...)`.

Đường dẫn mặc định được liệt kê ở cấu hình server là **`/oauth2/par`**. Đây là endpoint OAuth2, không phải UserInfo/OIDC logout và **không yêu cầu bật OIDC** để sử dụng PAR cho một OAuth2 Authorization Code Flow. Nếu đăng nhập OIDC, phần `openid` và xử lý ID Token vẫn thuộc cấu hình OIDC riêng.

### 9.1. Khung cấu hình endpoint

Ví dụ Java/Spring Boot dưới đây thể hiện **vị trí cấu hình PAR** trong filter chain (tham khảo Spring Authorization Server 1.5.x). Nó chưa bao gồm toàn bộ các bean cho một Authorization Server chạy được:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerParConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer server =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(server.getEndpointsMatcher())
            .with(server, authorizationServer ->
                    authorizationServer.pushedAuthorizationRequestEndpoint(
                            Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

        return http.build();
    }

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .issuer("https://login.example.vn")
                .pushedAuthorizationRequestEndpoint("/oauth2/par")
                .build();
    }
}
```

Các điểm cần hiểu:

- `securityMatcher(server.getEndpointsMatcher())` áp filter chain đúng tập OAuth2 endpoints, bao gồm endpoint được cấu hình qua PAR.
- `pushedAuthorizationRequestEndpoint(Customizer.withDefaults())` thể hiện vị trí cấu hình PAR. Việc endpoint được bật/khai báo metadata/hoạt động thực tế còn phải kiểm chứng ở **phiên bản và runtime**; không nên giả định chỉ gọi configurer là đã hoàn tất tất cả policy.
- `issuer("https://login.example.vn")` giữ issuer public ổn định khi chạy sau reverse proxy.
- `pushedAuthorizationRequestEndpoint("/oauth2/par")` trong settings đặt **đường dẫn**, không tự định nghĩa “bắt buộc mọi client phải dùng PAR”.
- Chưa có `RegisteredClientRepository`, signing keys/JWK (nếu cần JWT), login/consent, token/authorization services và filter chain cho user login. Phải bổ sung theo kiến trúc ứng dụng.

**Cần phân biệt hỗ trợ endpoint và enforce PAR:** RFC cho phép AS yêu cầu PAR ở mức toàn server hoặc từng client. Không suy rằng có một method `ClientSettings.requirePushedAuthorizationRequests(true)` ở mọi phiên bản Spring Authorization Server. Nếu phiên bản dùng không cung cấp sẵn cấu hình enforce, cần implement policy/validator trước khi xử lý authorization request trực tiếp và kiểm thử kỹ; không chỉ công bố `require_pushed_authorization_requests=true` trong JSON mà vẫn chấp nhận request thường.

### 9.2. Khai báo client dùng Authorization Code + PKCE

```java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

static RegisteredClient portalClient(String hashedSecret) {
    return RegisteredClient.withId("registration-portal-web")
            .clientId("portal-web")
            .clientSecret(hashedSecret)
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                    "https://portal.example.vn/login/oauth2/code/portal")
            .scope(OidcScopes.OPENID)
            .scope(OidcScopes.PROFILE)
            .scope("orders.read")
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build())
            .build();
}
```

Đây là **phương thức factory** phải đưa vào class và lưu qua `RegisteredClientRepository`. `hashedSecret` là hash được tạo bằng `PasswordEncoder`; secret bản rõ chỉ dành cho client và phải được phân phối qua secret manager. `requireProofKey(true)` bắt buộc PKCE; **không phải flag kích hoạt PAR**.

### 9.3. Vai trò của OAuth2 Client

Phía `portal-web` phải thực sự:

1. Sinh `state`/`nonce`/PKCE trước khi điều hướng người dùng.
2. Gửi PAR POST bằng HTTP client có TLS và client authentication phù hợp; xử lý status `201`, `request_uri` và `expires_in`.
3. Lưu transaction gắn tham chiếu với browser/session, issuer và PKCE verifier.
4. Tạo authorization URL bằng `request_uri` vừa nhận (không gắn thêm toàn bộ request data).
5. Trên callback, đối chiếu `state`, dùng verifier tương ứng để đổi code và xác minh ID Token nếu là OIDC.

**Không mặc định** ứng dụng Spring Security OAuth2 Login tự chuyển mọi authorization request qua PAR chỉ vì Authorization Server công bố endpoint. Tùy version, cần client library/configuration/resolver hỗ trợ PAR và kiểm thử request thực tế. Nếu viết tùy biến, giữ hành vi state/session/PKCE của Spring Security; đừng tự tạo callback controller thiếu validation.

## 10. Trình tự kiểm thử PAR trong môi trường local/staging

### 10.1. Kiểm tra metadata

```bash
curl -fsS https://login.example.vn/.well-known/oauth-authorization-server \
  | jq '{issuer, authorization_endpoint, pushed_authorization_request_endpoint, require_pushed_authorization_requests}'
```

Trường `pushed_authorization_request_endpoint` cần đúng URL HTTPS public và khớp AS đang chạy. Lệnh này chỉ đọc metadata, **không chứng minh** toàn bộ PAR flow đã vận hành hoặc được enforce.

### 10.2. Kiểm tra một PAR request hợp lệ

Để tránh đưa secret thật vào command-line/history, thực hiện bài test bằng HTTP client có credential store được bảo vệ. Với dữ liệu giả, ví dụ ý tưởng:

```http
POST /oauth2/par HTTP/1.1
Host: login.example.vn
Content-Type: application/x-www-form-urlencoded
Authorization: Basic TEST_CREDENTIAL_REDACTED

client_id=portal-web&response_type=code&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&scope=openid%20orders.read&state=TEST_STATE&nonce=TEST_NONCE&code_challenge=TEST_S256_CHALLENGE&code_challenge_method=S256
```

Những giá trị `TEST_*` ở trên là **placeholder**, không phải giá trị PKCE hợp lệ. Test thực tế phải sinh verifier/challenge bằng CSPRNG và SHA-256, cấp client credentials đúng policy. Kỳ vọng response `201 Created` cùng `request_uri` khó đoán và `expires_in` dương, rồi browser GET authorization endpoint với tham chiếu hợp lệ.

### 10.3. Ma trận kiểm thử chức năng và bảo mật

| Ca | Tình huống | Kết quả mong đợi |
|---|---|---|
| 1 | PAR hợp lệ, client auth đúng, PKCE S256 | `201` có `request_uri` và `expires_in` |
| 2 | Client secret sai hoặc method không đúng | Từ chối `invalid_client`/lỗi phù hợp, không cấp tham chiếu |
| 3 | Gửi `GET /oauth2/par` | Không xử lý như POST PAR; theo RFC có thể trả `405` |
| 4 | Gửi `request_uri` trong PAR POST | Bị từ chối |
| 5 | `redirect_uri` không hợp lệ | PAR bị từ chối, không cấp redirect code tới URI lạ |
| 6 | Scope không thuộc registration | PAR bị từ chối (hoặc lỗi policy phù hợp) |
| 7 | Thiếu `code_challenge` khi client bắt buộc PKCE | Bị từ chối ở bước kiểm tra thích hợp |
| 8 | Browser dùng `request_uri` đúng client, trong TTL | AS tiếp tục login/consent/authorization flow |
| 9 | Browser dùng tham chiếu của client A với `client_id` của B | Bị từ chối |
| 10 | Browser dùng tham chiếu đã hết hạn | Bị từ chối theo RFC |
| 11 | Browser gửi lại tham chiếu đã dùng | Bị từ chối theo chính sách one-time; kiểm thử ngoại lệ reload nếu có |
| 12 | Thêm `scope=admin` vào browser URL bên cạnh request_uri | Không làm thay đổi scope đã push |
| 13 | Thêm `redirect_uri` khác vào browser URL | Không vượt qua kiểm tra redirect URI của request gốc |
| 14 | Client policy bị gỡ scope khi tham chiếu chưa hết hạn | Authorization endpoint phát hiện và từ chối/áp policy hiện hành |
| 15 | Bật yêu cầu PAR, sau đó gửi direct `/oauth2/authorize` không có tham chiếu | Bị từ chối `invalid_request` |
| 16 | PAR POST ở pod A, authorize GET ở pod B | Truy xuất cùng request và trạng thái TTL/consume hợp lệ |
| 17 | Hai browser cùng dùng một tham chiếu | Không có double-authorization ngoài chính sách |
| 18 | PAR POST chứa dữ liệu nghiệp vụ nhạy cảm | Proxy/log/tracing không ghi nguyên văn body |
| 19 | PAR POST cực lớn hoặc quá nhiều lần | Body-size quota/rate limit, lỗi an toàn; không cạn tài nguyên |
| 20 | Hoàn tất Authorization Code + PKCE + OIDC | Callback kiểm tra state/nonce, token được đổi đúng client/verifier |

### 10.4. Sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| `POST /oauth2/par` trả `404` | Phiên bản AS không hỗ trợ, PAR chưa được cấu hình, proxy route sai | Kiểm tra configurer, settings, filter-chain và public route |
| `invalid_client` | Client auth ở PAR không khớp registration | Kiểm tra client method/credential, không log secret |
| `invalid_request` vì `request_uri` hoặc `redirect_uri` | Gửi request_uri vào POST hoặc redirect không hợp lệ | Gỡ request_uri khỏi POST, giữ URI callback đã đăng ký |
| PAR trả `201` nhưng browser authorize thất bại | URI hết hạn, khác client, sai encoding, mất request trong cache | Kiểm tra TTL, client binding, storage/session/multi-node |
| Có PAR endpoint nhưng browser vẫn gửi cả scope/claims | Client chưa dùng PAR khi khởi tạo authorization URL | Kiểm tra OAuth2 Client request resolver thực tế |
| Refresh trình duyệt khiến `request_uri` lỗi | Tham chiếu one-time đã dùng | Thiết kế bắt đầu giao dịch mới và thông báo lỗi rõ ràng |
| Redirect URI bị ghi lại theo payload tùy ý | Validator/ngoại lệ PAR redirect quá rộng | Thu hẹp policy; không dùng open redirect |
| URL ngắn nhưng vẫn lộ `code` ở callback | PAR chỉ bảo vệ request đầu vào | Áp PKCE, safe callback, no-referrer/no-store, không log query |
| Chỉ chạy một AS pod, nhiều pod lỗi ngẫu nhiên | Kho pushed request chỉ tồn tại cục bộ | Thiết kế shared storage/cluster routing và test TTL/replay |

## 11. Quyết định khi nào nên yêu cầu PAR

PAR đặc biệt hữu ích khi:

- Ứng dụng xử lý dữ liệu cá nhân/nhạy cảm và không muốn các tham số quyền/claims xuất hiện trong URL trình duyệt.
- Có **rich authorization requests**, fine-grained scopes/consent hoặc dữ liệu giao dịch có cấu trúc.
- Hệ thống yêu cầu **client authentication trước tương tác người dùng**, tăng bảo vệ trước giả mạo hoặc sửa request.
- Tổ chức triển khai security profile cao (ví dụ hệ sinh thái tài chính), yêu cầu tập trung validation tại AS và cần thêm lớp kiểm soát kênh front-channel.
- URL truyền thống quá dài và có nguy cơ lỗi qua proxy, browser hoặc thiết bị di động.

**Đánh đổi cần tính:** thêm một HTTP round trip trực tiếp trước browser redirect, cần client hỗ trợ PAR, thêm endpoint, cache/persistence, TTL và giám sát. Nếu phụ thuộc PAR bắt buộc mà endpoint không sẵn sàng, client không được tự động downgrade sang direct authorization request (vì phá policy); cần báo lỗi phù hợp hoặc thử lại một cách có kiểm soát.

### 11.1. Checklist thiết kế production

- [ ] Có chính sách rõ ràng: PAR **optional**, yêu cầu riêng từng client, hay bắt buộc toàn server.
- [ ] PAR POST chỉ qua HTTPS, áp đúng client authentication và không chấp nhận tham số `request_uri`.
- [ ] AS validate redirect URI, scope, PKCE, request format sớm và kiểm tra lại policy ở thời điểm authorization khi cần.
- [ ] `request_uri` đủ entropy, gắn client, TTL ngắn, được dùng một lần/kiểm soát replay.
- [ ] Pushed request storage có giới hạn, dọn TTL, chia sẻ giữa AS nodes và bảo vệ dữ liệu nhạy cảm.
- [ ] Front-channel chỉ mang tham chiếu; không cho tham số browser ghi đè nội dung đã push.
- [ ] Client giữ `state`, `nonce` và `code_verifier` gắn cùng transaction, kiểm tra callback/token sau đó.
- [ ] Không nhầm PAR với JAR/JARM, Authorization Code grant, PKCE hoặc client authentication.
- [ ] Metadata công bố chính xác PAR endpoint/policy đang được enforce; kiểm thử direct authorize bị từ chối khi PAR bắt buộc.
- [ ] Giới hạn rate/size/timeouts, có observability, audit và secret redaction.
- [ ] Có integration tests trên **đúng phiên bản Spring Authorization Server**, OAuth2 Client và mô hình proxy/cluster thực tế.
- [ ] Có chiến lược triển khai/migration cho client chưa hỗ trợ PAR; không bật bắt buộc đột ngột làm hỏng login hợp lệ.

## 12. Câu hỏi tự kiểm tra

1. Tại sao một URL `/oauth2/authorize` dài với `claims`/`authorization_details` tạo rủi ro về quyền riêng tư và tính toàn vẹn?
2. PAR dùng những endpoint nào, endpoint nào nhận POST và endpoint nào vẫn điều hướng user agent?
3. Response `201` của PAR có trả access token hoặc authorization code không?
4. `request_uri` khác `redirect_uri` và `code_verifier` như thế nào?
5. Tại sao phải gắn `request_uri` với client đã push request?
6. Nếu kẻ tấn công tráo `request_uri` trong trình duyệt, vì sao PKCE, `state` và `nonce` vẫn có giá trị?
7. PAR đã bật thì Authorization Server có thể bỏ kiểm tra scope, redirect URI và user consent ở authorization endpoint không?
8. PAR có tự cung cấp chữ ký số Request Object không? Khi nào cần JAR?
9. Những dữ liệu nhạy cảm nào vẫn có thể xuất hiện trong browser ở bước callback dù đã dùng PAR?
10. Khi PAR là bắt buộc, request trực tiếp tới authorization endpoint không có tham chiếu hợp lệ phải xử lý thế nào?
11. Vì sao hệ thống nhiều AS pod cần chú ý đến TTL, storage và kiểm soát truy cập `request_uri`?
12. Cấu hình đường dẫn `pushedAuthorizationRequestEndpoint("/oauth2/par")` đã đủ để bảo đảm mọi client buộc dùng PAR chưa?

## Tài liệu tham khảo

- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126.html): định nghĩa PAR, request URI, xác thực client, metadata, quy tắc sử dụng một lần và bảo mật.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization endpoint, token endpoint, client authentication và authorization code.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): redirect URI, bảo vệ CSRF/PKCE và các mối đe dọa OAuth2.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE S256, verifier và code challenge.
- [RFC 9101 — JWT-Secured Authorization Request (JAR)](https://www.rfc-editor.org/rfc/rfc9101): signed/encrypted Request Object, kết hợp PAR.
- [RFC 9396 — Rich Authorization Requests (RAR)](https://www.rfc-editor.org/rfc/rfc9396): `authorization_details` cho yêu cầu cấp quyền chi tiết.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): discovery metadata và PAR endpoint URL.
- [Spring Authorization Server — Configuration Model (1.5.x)](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `OAuth2AuthorizationServerConfigurer` và `AuthorizationServerSettings`.
- [Spring Authorization Server — Protocol Endpoints (1.5.x)](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OAuth2PushedAuthorizationRequestEndpointConfigurer`, filter/provider và tùy biến validation.
- [Spring Security — OAuth2 Client Authorization Grant Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): authorization request resolver, PKCE và callback của client.
- [Spring Authorization Server 1.5 GA Announcement](https://spring.io/blog/2025/05/20/spring-authorization-server-1-5-goes-ga/): bổ sung PAR trong Spring Authorization Server 1.5.
