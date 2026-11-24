# PKCE and confidential client

## Mục tiêu học tập

Trong học phần **Token Security Fundamentals**, **Proof Key for Code Exchange (PKCE)** thường được giới thiệu như biện pháp bảo vệ **public client** như ứng dụng mobile hoặc SPA. Điều dễ gây hiểu nhầm là: **confidential client đã có client secret, private-key JWT hoặc mTLS để xác thực với Authorization Server thì có cần PKCE nữa không?**

**Có — confidential client nên dùng PKCE khi thực hiện Authorization Code flow, ngay cả khi nó cũng xác thực client tại token endpoint.** Hai cơ chế bảo vệ những điều kiện tin cậy khác nhau: client authentication chứng minh danh tính ứng dụng tại token endpoint, còn PKCE ràng buộc **authorization code của một giao dịch** với bên đã tạo **code verifier** cho giao dịch đó. PKCE là một lớp bảo vệ bổ sung, không biến client secret thành thừa và không thay thế xác minh callback, session hoặc quyền truy cập token.

Sau bài này, bạn có thể:

1. Phân biệt **confidential client**, **public client**, **client authentication**, **PKCE**, `state` và **sender-constrained token**.
2. Giải thích vì sao confidential client vẫn có nguy cơ **authorization code interception**, **code injection** hoặc **đánh tráo giao dịch** ngay cả khi giữ được client secret.
3. Tạo đúng **`code_verifier`**, tính **`code_challenge`** bằng `S256` theo RFC 7636 và diễn giải kiểm tra tại token endpoint.
4. Theo dõi toàn bộ luồng **Authorization Code + PKCE + client authentication** cho web backend/Backend for Frontend (BFF).
5. Quản lý transaction binding với `state`, session, issuer, redirect URI và thời hạn; không để `code_verifier` bị lộ qua URL/log.
6. Cấu hình ví dụ **Spring Security** để confidential OAuth Client chủ động dùng PKCE; hiểu trách nhiệm riêng của Client và Authorization Server.
7. Phân tích các lỗi triển khai, token issuance/validation, nguy cơ token bị đánh cắp hoặc phát lại và xây dựng ma trận kiểm thử.

## 1. Confidential client là gì?

OAuth 2.0 phân loại **Client** dựa trên **khả năng bảo vệ thông tin xác thực** trong môi trường triển khai.

| Loại Client | Ví dụ | Khả năng giữ credential | Cần lưu ý |
|---|---|---|---|
| **Public client** | SPA trực tiếp làm OAuth Client, mobile/native app, ứng dụng phân phối cho người dùng. | Không thể bảo vệ một shared client secret như bí mật thực sự trước người sử dụng môi trường. | Dùng Authorization Code + PKCE và bảo vệ callback, token storage, XSS/callback interception. |
| **Confidential client** | Web backend, BFF, service chạy trên hạ tầng được kiểm soát. | Có khả năng bảo vệ client secret, private key hoặc TLS client certificate nếu cấu hình/vận hành đúng. | Vẫn cần PKCE khi dùng Authorization Code, cùng client authentication và kiểm soát phiên. |

Một **web app có cả browser JavaScript và backend** cần xác định *thành phần nào đóng vai OAuth Client*. Nếu BFF giữ credential, khởi tạo authorization request, xử lý callback và đổi code **phía server**, BFF có thể là confidential OAuth Client. Điều đó **không làm JavaScript ở browser tự nhiên trở thành confidential client**.

### Những điều dễ nhầm

- `client_id` là **định danh**, không phải secret; bất kỳ ai cũng có thể biết.
- **Client secret** chứng minh quyền sử dụng credential của confidential client với AS trong phạm vi cơ chế đã đăng ký.
- **`code_verifier`** là bí mật **ngắn hạn, riêng từng lần authorization** để hoàn tất PKCE.
- **Authorization code** là giá trị tạm thời được trả qua front channel (trình duyệt/redirect), **không phải access token**.
- **Access token** được cấp tại token endpoint và chỉ dùng cho Resource Server đúng audience/scope.
- **OIDC ID token** dành cho Client/Relying Party, không dùng thay access token ở API.

## 2. PKCE bảo vệ điều gì?

**PKCE (RFC 7636)** tạo một mối liên hệ mật mã giữa:

1. **Bước bắt đầu authorization request:** Client tạo `code_verifier` bí mật và gửi **dẫn xuất công khai** `code_challenge` lên authorization endpoint.
2. **Bước đổi authorization code:** Client gửi lại **`code_verifier`** tới token endpoint; AS chứng minh verifier phù hợp với challenge đã gắn với **chính authorization code đó**.

~~~text
Tạo trong Client:
    code_verifier  = giá trị ngẫu nhiên entropy cao, riêng mỗi transaction
    code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
    method         = S256

Authorization request:
    client_id, redirect_uri, state, scope,
    code_challenge, code_challenge_method=S256

Token request:
    authorization_code, redirect_uri, code_verifier,
    client authentication nếu Client là confidential

Authorization Server:
    verify code belongs to client and transaction
    AND compute S256(code_verifier) == stored code_challenge
    AND enforce single-use, TTL, grant and client authentication
~~~

`code_challenge` không cần được giữ bí mật; nó được đưa qua front channel. **`code_verifier` không được gửi trong authorization request**: chỉ được dùng tại token endpoint qua kênh HTTPS trong bước đổi code.

### PKCE giải quyết vấn đề nào?

Giả sử attacker có được authorization code từ callback/log/redirect. Nếu token endpoint yêu cầu đúng verifier chưa bị lộ, **chỉ nắm code là chưa đủ** để đổi thành access token. PKCE còn giúp giảm nguy cơ một số kiểu **code injection / authorization response substitution**, khi code của giao dịch khác bị cấy vào callback để Client thật đổi hộ: code của giao dịch attacker không khớp verifier mà Client lưu cho giao dịch hiện tại.

**Giới hạn:** PKCE không tự phòng mọi dạng đánh cắp token. Nếu attacker kiểm soát server đang giữ verifier, chiếm session, lấy cả code và verifier, hoặc có access token đã phát hành, cần thêm những biện pháp bảo vệ tương ứng.

## 3. Confidential client đã có client authentication — tại sao vẫn dùng PKCE?

### Hai điều kiện kiểm tra khác nhau

| Cơ chế | Bằng chứng do ai cung cấp? | Gắn với cái gì? | Câu hỏi được trả lời |
|---|---|---|---|
| **Client authentication** | Client secret, signed assertion hoặc mTLS client certificate. | **Danh tính Client/credential đã đăng ký**, thường sống qua nhiều transaction. | “Bên gọi token endpoint có chứng minh được credential của confidential client không?” |
| **PKCE** | `code_verifier` sinh ngẫu nhiên và giữ cho **một transaction**. | **Authorization code** được cấp từ authorization request chứa challenge. | “Code này có được đổi trong đúng ngữ cảnh sở hữu verifier ban đầu không?” |
| **`state` / transaction binding** | Giá trị ngẫu nhiên gắn với phiên và authorization request. | **Authorization response ↔ giao dịch khởi tạo** phía Client. | “Callback này có thuộc lượt đăng nhập/kết nối đang chờ không?” |
| **OIDC `nonce`** (khi dùng) | Giá trị gắn request và ID token theo OIDC. | **ID token / xác thực user**. | “ID token này có khớp giao dịch OIDC và yêu cầu nonce không?” |
| **DPoP/mTLS-bound access token** | Private key/proof hoặc chứng chỉ ở **lúc gọi RS**. | **Access token đã phát hành** với sender key/cert. | “Caller hiện tại có thể sử dụng khóa/chứng chỉ mà token ràng buộc không?” |

**Không cơ chế nào là tên khác của cơ chế còn lại.**

### Tình huống 1 — Attacker chỉ đánh cắp authorization code

Nếu confidential client bảo vệ client secret thật tốt, attacker ngoài hệ thống thường **không thể tự** đổi code tại token endpoint vì không xác thực được Client. Nhưng PKCE vẫn là một **lớp phòng thủ độc lập**:

- Khi có lỗi cấu hình, rò rỉ credential hoặc nhiều thành phần có thể sử dụng client authentication, kẻ chỉ cầm code vẫn cần **verifier của đúng transaction**.
- Nếu authorization code được truy xuất từ một kênh không mong muốn, verifier làm giảm khả năng code bị đổi trái phép khi riêng client authentication không đủ trong cấu hình thực tế.

Không diễn giải rằng client authentication **hoàn toàn vô dụng** hoặc PKCE **bảo đảm tuyệt đối** khi secret bị lộ; hai bí mật có thể cùng bị lộ nếu cùng nằm trong một môi trường bị chiếm.

### Tình huống 2 — Authorization code bị cấy vào callback của Client

Đây là tình huống đặc biệt quan trọng đối với confidential client.

Một attacker cố gửi **authorization code được phát từ giao dịch khác** đến callback của Client thật. Nếu Client thiếu ràng buộc giao dịch và vô tình đổi code bằng **client credential của chính mình**, nó có thể tạo một session hoặc token context sai user — dù secret **chưa hề bị lộ**.

PKCE giảm rủi ro vì Client lưu verifier **riêng cho request đang chờ**. Code lấy từ giao dịch khác phải được AS gắn với challenge khác, nên không khớp verifier Client gửi cho lượt hiện tại. **`state`, kiểm tra issuer/authorization response và session binding** vẫn rất quan trọng vì code injection là vấn đề có nhiều biến thể.

### Tình huống 3 — Trình duyệt và backend có ranh giới khác nhau

Một BFF confidential client:

- Có thể giữ `client_secret` trong secret manager.
- Tạo `code_verifier` và giữ trong session/transaction store **phía server**.
- Đưa browser qua AS bằng redirect chứa `code_challenge`.
- Nhận callback với code, sau đó đổi code tại backend bằng **verifier** và **client authentication**.

Chữ “confidential” nói về khả năng giữ **credential của client**, không khẳng định **front channel** qua browser không thể bị tấn công. Đó chính là lý do PKCE vẫn có ích.

## 4. Cách tạo `code_verifier` đúng chuẩn

RFC 7636 quy định `code_verifier`:

- Có độ dài **43–128 ký tự**.
- Chỉ gồm tập ký tự không dành riêng (*unreserved*) theo chuẩn: chữ cái `A–Z`, `a–z`, số `0–9`, dấu `-`, `.`, `_` và `~`.
- Là giá trị **không thể đoán được**, mới cho từng authorization transaction; cách sinh được khuyến nghị tạo **32 byte ngẫu nhiên mật mã** rồi mã hóa Base64URL **không padding** để có chuỗi **43 ký tự**.

Không dùng:

~~~text
code_verifier = "123456"
code_verifier = client_id + current_timestamp
code_verifier = sha256(client_secret)  # tái sử dụng giữa các transaction
code_verifier = httpSessionId
code_verifier = email hoặc user ID
~~~

Những cách trên có thể không đáp ứng độ dài/entropy hoặc làm verifier dự đoán được, dùng lại được. **Không tái sử dụng một verifier chung cho nhiều người dùng hoặc nhiều lượt đăng nhập**.

### Java minh họa sinh cặp verifier/challenge

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

record PkceValues(String verifier, String challenge) {}

final class PkceGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder BASE64URL =
            Base64.getUrlEncoder().withoutPadding();

    static PkceValues generate() throws NoSuchAlgorithmException {
        byte[] randomBytes = new byte[32]; // 256 bit entropy
        RANDOM.nextBytes(randomBytes);

        String verifier = BASE64URL.encodeToString(randomBytes);
        byte[] sha256 = MessageDigest.getInstance("SHA-256").digest(
                verifier.getBytes(StandardCharsets.US_ASCII));
        String challenge = BASE64URL.encodeToString(sha256);
        return new PkceValues(verifier, challenge);
    }
}
~~~

Từ 32 byte ngẫu nhiên, Base64URL không padding cho chuỗi **43 ký tự** thuộc tập ký tự PKCE cho phép. `challenge` được tính trên **chuỗi verifier ASCII**, không phải trực tiếp trên 32 byte ngẫu nhiên ban đầu. Không thay `SecureRandom` bằng `Random` hoặc ghép timestamp.

**Ví dụ chỉ tạo giá trị PKCE**, chưa tạo một OAuth Client hoạt động. Khi dùng Spring Security/OAuth library đã hỗ trợ PKCE, ưu tiên chức năng thư viện thay vì tự triển khai toàn bộ logic giao thức.

### Công thức S256

\[
\operatorname{code\_challenge}
=\operatorname{BASE64URL\_NO\_PADDING}
\left(\operatorname{SHA256}\left(\operatorname{ASCII}(\operatorname{code\_verifier})\right)\right)
\]

Đây là **SHA-256**, không phải mã hóa bất đối xứng, không dùng client secret làm key và không phải HMAC.

### Vector kiểm thử của RFC 7636

~~~text
code_verifier:
  dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge_method:
  S256

code_challenge:
  E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Nếu cách triển khai `S256` không tạo ra challenge này từ verifier tương ứng, hãy kiểm tra **ASCII**, SHA-256, **Base64URL** (không phải Base64 chuẩn), và việc loại dấu padding `=`.

## 5. Luồng Authorization Code + PKCE cho confidential client

Giả sử:

~~~text
OAuth Client:          shop-bff
Client type:           confidential
Authorization Server:  https://auth.example.test
Redirect URI:          https://shop.example.test/login/oauth2/code/shop
Resource Server:       orders-api
Requested scope:       openid orders:read
PKCE method:           S256
Client authentication: client_secret_basic (minh họa)
~~~

### Sơ đồ tuần tự

~~~mermaid
sequenceDiagram
    actor U as User
    participant B as Browser
    participant C as Shop BFF (confidential client)
    participant AS as Authorization Server
    participant RS as Orders API
    U->>B: Đăng nhập để xem đơn
    B->>C: GET /login
    C->>C: Tạo state S, verifier V, challenge S256(V)
    C->>C: Lưu S, V, issuer và ngữ cảnh trong transaction store
    C-->>B: Redirect tới AS với challenge và state
    B->>AS: GET /authorize, client_id, state, S256 challenge
    AS->>AS: Verify client registration, redirect, login/consent
    AS-->>B: Redirect với code K và state S
    B->>C: GET callback?code=K&state=S
    C->>C: Kiểm tra state, issuer, session, đúng transaction
    C->>AS: POST /token: K + V + client_secret_basic qua HTTPS
    AS->>AS: Verify client authentication, code, PKCE, redirect, TTL, one-time
    AS-->>C: Access token cho orders-api; ID token nếu OIDC
    C->>C: Lưu token phía server, tạo hoặc xoay session
    C-->>B: Set-Cookie session HttpOnly; Secure
    B->>C: GET /orders kèm session cookie
    C->>RS: Authorization: Bearer access token cho Orders
    RS->>RS: Verify iss/aud/scope/exp và owner/tenant
    RS-->>C: Chỉ đơn được phép
~~~

Các mũi tên giản lược redirect qua browser. Luồng trên **không hứa AS luôn hiện consent**: nếu quyền đã được phê duyệt hợp lệ hoặc policy khác cho phép, AS có thể bỏ qua màn hình mới.

### Bước 1 — Confidential client khởi tạo giao dịch

Backend tạo:

~~~text
transaction_id  = <RANDOM_ID>
browser_session = <SERVER_SIDE_SESSION_REFERENCE>
state           = <RANDOM_STATE>
code_verifier   = <FRESH_43_TO_128_CHAR_VERIFIER>
code_challenge  = S256(code_verifier)
code_method     = S256
issuer          = https://auth.example.test
redirect_uri    = https://shop.example.test/login/oauth2/code/shop
resource        = https://api.example.test/orders
requested_scope = {openid, orders:read}
created_at      = <TIMESTAMP>
~~~

`state`, verifier và issuer phải **cùng thuộc một transaction**. Backend lưu verifier **phía server** và liên kết với browser session, giới hạn TTL và đánh dấu transaction đã hoàn tất sau callback. Không để browser tự khai verifier khi đổi code.

### Bước 2 — Chuyển browser đến authorization endpoint

~~~http
GET /authorize?response_type=code&client_id=shop-bff&redirect_uri=https%3A%2F%2Fshop.example.test%2Flogin%2Foauth2%2Fcode%2Fshop&scope=openid%20orders%3Aread&state=<RANDOM_STATE>&code_challenge=<BASE64URL_S256_CHALLENGE>&code_challenge_method=S256&resource=https%3A%2F%2Fapi.example.test%2Forders HTTP/1.1
Host: auth.example.test
~~~

Đây là request minh họa với placeholder. `resource` là tham số **RFC 8707** nếu AS hỗ trợ; không phải tham số bắt buộc của PKCE. Nếu dùng OIDC, Client có thể cần thêm `nonce` và các ràng buộc response theo profile.

**Không đưa `code_verifier` hoặc `client_secret` vào authorization URL.** Ở đây chỉ có challenge được dẫn xuất.

### Bước 3 — AS phát authorization code

AS kiểm tra client registration, redirect URI, user authentication/consent/policy rồi gắn **challenge + method** với authorization code K:

~~~text
authorization_code K:
  client_id       = shop-bff
  redirect_uri    = https://shop.example.test/login/oauth2/code/shop
  code_challenge  = <BASE64URL_S256_CHALLENGE>
  challenge_method= S256
  subject         = user-123
  scope           = {openid, orders:read}
  resource        = orders-api
  expires_at      = <SHORT_EXPIRY>
  consumed        = false
~~~

Đây là **cấu trúc lưu trữ khái niệm**, không phải schema chuẩn bắt buộc của OAuth. Code phải **ngắn hạn**, **dùng một lần** và bị ràng buộc với client/redirect/grant.

### Bước 4 — Browser quay về callback

~~~http
GET /login/oauth2/code/shop?code=<AUTH_CODE_K>&state=<RANDOM_STATE> HTTP/1.1
Host: shop.example.test
~~~

Client **không** chỉ đọc `code` rồi đổi ngay. Nó cần đối chiếu `state` với transaction/session, xác định đúng AS/issuer theo profile và xác minh callback chưa được xử lý. Nếu callback thiếu/sai state, phiên không khớp hoặc transaction đã hết hạn, **từ chối**.

### Bước 5 — Confidential client đổi code với cả PKCE và client authentication

~~~http
POST /token HTTP/1.1
Host: auth.example.test
Authorization: Basic <BASE64_STANDARD_ENCODED_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=authorization_code&code=<AUTH_CODE_K>&redirect_uri=https%3A%2F%2Fshop.example.test%2Flogin%2Foauth2%2Fcode%2Fshop&code_verifier=<ORIGINAL_CODE_VERIFIER>
~~~

Chỉ có một **client authentication method** được áp dụng theo đăng ký của client. Với `client_secret_basic`, giá trị Basic header dùng **Base64 chuẩn** theo quy tắc RFC 6749 `2.3.1`, không phải Base64URL; thư viện OAuth nên tự tạo header để tránh lỗi encoding.

Nếu AS dùng **private_key_jwt** hoặc **mTLS** để xác thực confidential client, phần client authentication được thay theo phương thức đã đăng ký; **`code_verifier` vẫn cần** khi giao dịch yêu cầu PKCE.

### Bước 6 — AS kiểm tra đồng thời mọi ràng buộc

AS không chỉ kiểm tra “client secret đúng” hoặc “hash verifier đúng”. Tất cả điều kiện cần thiết phải đạt:

~~~text
token_request_allowed iff:
    client authenticated according to its registration
    AND grant_type == authorization_code
    AND code exists, not expired, not consumed
    AND code.client_id == authenticated_client_id
    AND redirect_uri matches code/authorization request
    AND transaction had code_challenge_method == S256
    AND BASE64URL(SHA256(ASCII(code_verifier))) == stored_code_challenge
    AND grant/subject/resource/scopes still pass required policy
~~~

Sau đó AS **tiêu thụ code một cách nguyên tử** để ngăn hai request đổi cùng code. Kiểm tra mật mã nên sử dụng thư viện có cách so sánh phù hợp, không tự tạo cơ chế rút gọn `substring` hoặc so khớp không chính xác.

### Bước 7 — Token được cấp đúng mục đích

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<ACCESS_TOKEN_FOR_ORDERS>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read",
  "id_token": "<ID_TOKEN_IF_OIDC>"
}
~~~

Đây là phản hồi rút gọn **OIDC + OAuth minh họa**; ID token chỉ hiện diện nếu luồng OIDC tương ứng thực sự cấp. Access token có thể là **JWT hoặc opaque**; PKCE không quyết định định dạng token. Nếu AS cấp refresh token, Client cần bảo vệ/thu hồi riêng theo grant và policy.

### Bước 8 — Resource Server vẫn phải phân quyền

Orders API kiểm tra **issuer, signature/introspection, audience, thời hạn, scope, principal và quyền trên từng đơn**. PKCE đã hoàn thành mục tiêu tại **token exchange**, không tự cung cấp bằng chứng rằng caller hiện tại của RS giữ một khóa sender-constrained.

## 6. `S256` và `plain`: không downgrade

RFC 7636 mô tả hai phương pháp challenge:

| Phương pháp | Cách xác định challenge | Đánh giá |
|---|---|---|
| **`S256`** | `BASE64URL(SHA256(ASCII(code_verifier)))`, không padding. | **Lựa chọn chuẩn nên dùng** với client và AS hỗ trợ SHA-256. |
| **`plain`** | `code_challenge = code_verifier`. | Chỉ còn ý nghĩa tương thích trong ngữ cảnh hạn chế; bộc lộ verifier trên front channel và không được chọn khi có S256. |

### Vì sao `plain` là vấn đề?

Với `plain`, `code_verifier` **trùng** `code_challenge` trong authorization request. Bên quan sát được authorization request có thể có luôn verifier, làm suy yếu ý tưởng giữ verifier ngoài front channel. Vì vậy **confidential client mới hay cũ đều nên dùng S256**.

### Đừng chấp nhận downgrade

Ví dụ sai:

~~~text
Client đã tạo S256 challenge cho transaction.
Attacker sửa hoặc bỏ tham số code_challenge_method.
AS âm thầm đổi sang plain hoặc bỏ kiểm tra PKCE.
=> PKCE mất tác dụng.
~~~

Điều cần thực thi:

1. **Client gửi `code_challenge_method=S256` tường minh.**
2. **AS lưu method/challenge** đã chấp nhận với code, không dựa vào lựa chọn ở token request.
3. **Client registration/policy yêu cầu PKCE** thì request thiếu challenge không được mặc định cấp code không PKCE.
4. Nếu AS yêu cầu S256, giá trị `plain` hoặc method không được hỗ trợ phải bị từ chối thay vì fallback.
5. **Client không tự gửi lại request không PKCE** khi AS báo lỗi về challenge.

## 7. PKCE không thay `state`, issuer hoặc kiểm soát session

Một thiết kế an toàn cho confidential client cần **ràng buộc giao dịch** ở nhiều lớp.

### Vai trò của `state`

`state` thường được Client sinh đủ ngẫu nhiên, lưu gắn với browser session và so sánh khi nhận authorization response. Nó giúp bảo vệ **liên kết request/response** và chống một số dạng **OAuth login CSRF/response injection**. PKCE cũng có thể góp phần bảo vệ chống CSRF trong những điều kiện triển khai nhất định, nhưng **không nên bỏ `state` chỉ vì có PKCE** nếu thiết kế callback/session cần ràng buộc này.

### Vai trò của `iss` khi có nhiều AS

Nếu Client hỗ trợ nhiều issuer, callback không chỉ cần đúng state; Client còn phải xác định **AS nào đã phát hành response**. Có thể dùng `iss` trong authorization response theo **RFC 9207** hoặc cơ chế issuer-binding/mix-up defense được profile hỗ trợ. Không dùng code từ AS A để gọi token endpoint AS B.

### Session binding và session fixation

Khi user bắt đầu login:

~~~text
browser session A:
    pending_state     = S1
    pending_verifier  = V1
    issuer            = AS-A
    redirect_uri      = callback-A
    expiration        = short TTL
~~~

Callback phải được giải quyết **trong đúng session A**. Nếu code từ transaction B đến callback của A thì không được lấy verifier V2 của B một cách tùy tiện. Sau khi đăng nhập thành công, nên **xoay session ID** theo cơ chế session fixation protection.

### OIDC `nonce` và ID token

Với OpenID Connect, Client/Relying Party còn phải kiểm tra ID token theo OIDC: **chữ ký, issuer, audience (thường là client ID), thời hạn và nonce nếu đã dùng hoặc profile yêu cầu**. PKCE không biến ID token thành access token và không thay xác minh OIDC.

### OAuth consent và policy

User đồng ý `orders:read` không cho phép Client tự lấy `orders:write` trong token request. PKCE chỉ ràng buộc code với verifier; **scope/resource/tenant vẫn do AS quyết định**, và RS vẫn kiểm tra quyền object.

## 8. Confidential client nên giữ `code_verifier` ở đâu?

### Mô hình BFF/server-side

Một thiết kế thường phù hợp:

~~~text
Browser:
    chỉ có session cookie ngẫu nhiên, Secure; HttpOnly; SameSite

BFF/server:
    transaction store:
        state -> {verifier, issuer, redirect_uri, resource,
                  scope, browser_session, expiry, used}
    token store:
        access token/refresh token được bảo vệ phía server

Authorization Server:
    authorization code -> {challenge, method, client_id, grant, expiry, used}
~~~

**Không lưu `code_verifier` trong URL, browser history, frontend JavaScript, localStorage, response HTML, access log, reverse-proxy log hoặc analytics.** Nếu bắt buộc truyền qua một thành phần khác của cùng backend, cần giữ bí mật và toàn vẹn của nó qua ranh giới tin cậy.

### Multi-instance / load balancing

Khi BFF chạy nhiều instance:

1. Lưu trạng thái authorization request ở **session store chia sẻ được bảo vệ** hoặc sử dụng thiết kế transaction state có bảo vệ tương đương.
2. Callback rơi vào instance khác vẫn tìm đúng **verifier theo state/session**.
3. Không dùng một biến static toàn cục như `currentVerifier` cho toàn hệ thống.
4. Hạn chế TTL, xóa hoặc đánh dấu **consumed** khi hoàn tất; xử lý concurrent callback một cách nguyên tử.
5. Lưu bí mật theo tenant/client/issuer để tránh **chọn sai verifier** khi user mở nhiều tab hoặc kết nối nhiều AS.

### Mở nhiều tab cùng lúc

Nếu user khởi tạo hai giao dịch:

~~~text
Tab 1: state S1, verifier V1, challenge C1
Tab 2: state S2, verifier V2, challenge C2
~~~

Client phải **giữ hai transaction riêng biệt**. Chỉ lưu một `code_verifier` trong session rồi overwrite bằng lần khởi tạo mới sẽ gây lỗi `invalid_grant` hoặc mở đường cho nhầm ngữ cảnh khi callback tab 1 đến sau.

### Cookie không được coi là kho bí mật mặc định

Cookie `HttpOnly; Secure` giúp hạn chế script đọc và yêu cầu transport an toàn, nhưng nếu đưa trực tiếp verifier vào cookie phía browser, verifier vẫn đi theo request và có thể lộ qua cookie logging hoặc thiết bị. Với **confidential BFF**, thường nên **giữ verifier tại server** và browser chỉ mang session reference phù hợp. Nếu dùng cơ chế stateless transaction được bảo vệ, phải đánh giá mã hóa/toàn vẹn, khóa, replay, độ dài và phạm vi chia sẻ; không mã hóa verifier bằng Base64 rồi coi là bí mật.

## 9. Client authentication trong bước đổi code

Confidential client có thể sử dụng nhiều phương thức xác thực khác nhau tại AS. PKCE bổ sung ở **cùng token request**, không biến phương thức client authentication thành tùy chọn.

| Phương thức | Bằng chứng của Client | Tương tác với PKCE |
|---|---|---|
| **`client_secret_basic`** | HTTP Basic header với client ID/secret theo phương thức đăng ký. | Request đổi code **vẫn gửi `code_verifier`**. |
| **`client_secret_post`** (nếu profile/AS hỗ trợ) | Client ID/secret trong form body qua HTTPS. | PKCE không thay secret; cân nhắc bảo mật và phương thức được khuyến nghị. |
| **`private_key_jwt`** | JWT client assertion được ký bằng private key đã đăng ký. | AS kiểm tra assertion và PKCE **độc lập**. |
| **mTLS client authentication** | Client certificate/khóa trong TLS handshake. | AS kiểm tra TLS identity và `code_verifier`. |

### Quy tắc quan trọng

- **Client ID không phải xác thực client**; phải áp dụng phương thức được đăng ký khi AS yêu cầu.
- Không dùng cả Basic và client secret trong body cùng request chỉ để “chắc ăn”; áp dụng **một client authentication method phù hợp**.
- Secret/private key thường tồn tại **dài hơn một authorization transaction**; verifier là bí mật **một lần** và phải hết hiệu lực khi giao dịch kết thúc.
- Nếu `private_key_jwt` hoặc mTLS bị lỗi, **không bỏ qua client authentication** vì PKCE đã đúng.
- Nếu PKCE sai, **không bỏ qua PKCE** vì secret/private key đã được xác minh.

### Xác thực Client không phải xác thực user

AS xác thực confidential client ở token endpoint không chứng minh principal có quyền xem **order 42**. AS còn phải quản lý authorization grant của user/tenant và cấp scope/resource phù hợp; Orders API quyết định dữ liệu nào được trả.

## 10. Trách nhiệm của Authorization Server đối với confidential client + PKCE

### Tại authorization endpoint

AS cần:

1. Kiểm tra `client_id` hợp lệ và authorization code grant được cho phép.
2. Kiểm tra redirect URI theo client registration, không redirect code tới host tùy ý.
3. Nếu client/policy yêu cầu PKCE, **bắt buộc có `code_challenge` và `code_challenge_method=S256`** hợp lệ.
4. Không nhận `code_verifier` như một thành phần của authorization request để bỏ qua nguyên tắc giữ bí mật.
5. Xác thực user/consent theo chính sách, giới hạn resource/scope và tenant.
6. Lưu **challenge, method, client, redirect, subject, scope/resource, expiry** cùng authorization code.

### Tại token endpoint

AS cần:

1. Xác thực confidential client bằng phương thức đã đăng ký.
2. Xác minh authorization code: tồn tại, chưa dùng, còn hiệu lực và thuộc client/redirect tương ứng.
3. Đọc `code_verifier` từ **form token request**, kiểm tra cú pháp/độ dài.
4. Tính lại S256 và so với challenge đã được lưu.
5. **Không dùng token request để chọn lại challenge/method** theo ý client, không cho client đổi từ S256 sang plain.
6. Thực thi chính sách grant cuối cùng, phát access token đúng audience/scope, xử lý refresh token theo policy.
7. **Đánh dấu code dùng một lần** và xử lý hai request tranh nhau đổi code.

### Mã giả token endpoint

~~~text
exchangeCode(request):
    client = authenticateRegisteredConfidentialClient(request)
    if client authentication failed:
        return invalid_client

    code = loadAuthorizationCode(request.code)
    if code missing or expired or alreadyConsumed:
        return invalid_grant
    if code.clientId != client.id:
        return invalid_grant
    if not redirectUriMatchesBoundValue(request.redirect_uri, code):
        return invalid_grant

    if code.pkceRequired:
        if code.codeChallengeMethod != "S256":
            return invalid_grant
        verifier = request.code_verifier
        if verifier missing or invalidSyntaxOrLength(verifier):
            return invalid_grant
        actual = BASE64URL_NO_PADDING(SHA256(ASCII(verifier)))
        if not constantTimeEqual(actual, code.storedChallenge):
            return invalid_grant

    if not atomicallyMarkCodeConsumed(code):
        return invalid_grant

    grant = verifyGrantAndCurrentPolicy(code.subject, code.clientId,
                                       code.scope, code.resource)
    if grant denied:
        return appropriateOAuthError

    return issueTokensWithinGrant(grant)
~~~

Đây là mã giả mô hình; thứ tự thực thi tiêu thụ code/policy cần bảo đảm **tính nguyên tử và chống cấp hai token từ cùng code** khi có concurrency hoặc lỗi hệ thống. **Không xây token endpoint riêng chỉ từ pseudocode**; nên dùng Authorization Server/framework được kiểm chứng.

### Mã lỗi

| Lỗi | Mã OAuth thường dùng | Tầng |
|---|---|---|
| Client authentication thất bại | `invalid_client`. | Token endpoint. |
| Code hết hạn, đã dùng, sai redirect/client hoặc verifier không khớp | `invalid_grant`. | Token endpoint. |
| Authorization request thiếu tham số bắt buộc hoặc sai cú pháp PKCE | `invalid_request` hoặc lỗi tương ứng theo profile. | Authorization endpoint. |
| Client không được phép dùng grant/response type | `unauthorized_client` hoặc lỗi tương ứng. | AS. |
| Requested scope không hợp lệ | `invalid_scope`. | AS. |
| User từ chối consent | `access_denied` nếu redirect tới callback hợp lệ. | Authorization endpoint. |

Đừng trả verifier, challenge đầy đủ, client secret, code hoặc access token vào error description/log. Đừng “chữa” `invalid_grant` bằng cách tự bỏ PKCE và thử lại.

## 11. Ví dụ cấu hình Spring Security cho confidential OAuth Client

Với một **Spring Boot web backend/BFF** dùng OAuth2 Login, cấu hình client registration có thể như sau:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          shop:
            provider: company-auth
            client-id: shop-bff
            client-secret: <INJECT_FROM_SECRET_MANAGER>
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - orders:read
        provider:
          company-auth:
            issuer-uri: https://auth.example.test
~~~

**Lưu ý:** giá trị `<INJECT_FROM_SECRET_MANAGER>` chỉ là placeholder, không commit secret thật. Spring property/flow chính xác phụ thuộc phiên bản và provider. Nếu AS không cung cấp discovery/metadata như profile hỗ trợ, cần cấu hình endpoint theo cơ chế tương ứng.

### Tường minh bật PKCE cho confidential client

Một số cấu hình Spring Security mặc định tự bật PKCE cho **public client**, nhưng không nên suy rằng mọi cấu hình confidential client đều tự thêm PKCE. Với ứng dụng cần **bắt buộc PKCE**, có thể tùy chỉnh authorization request resolver theo API Spring Security 6:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OAuthLoginSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {
        DefaultOAuth2AuthorizationRequestResolver resolver =
                new DefaultOAuth2AuthorizationRequestResolver(
                        registrations, "/oauth2/authorization");

        // Thêm code_challenge + S256 và lưu code_verifier
        // trong attributes của authorization request transaction.
        resolver.setAuthorizationRequestCustomizer(
                OAuth2AuthorizationRequestCustomizers.withPkce());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/health").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
~~~

**Ý nghĩa của customizer:** Spring tạo PKCE verifier/challenge cho transaction và dùng verifier đã lưu khi token exchange theo tích hợp OAuth Client của framework. Không tự nhét verifier vào redirect URL hay in ra log.

**Kiểm tra với phiên bản Spring đang dùng:** lớp/API hoặc hành vi mặc định có thể thay đổi theo phiên bản, và nếu ứng dụng đã có **custom AuthorizationRequestRepository**, cần bảo đảm repository đó **lưu và phục hồi đầy đủ attributes chứa verifier**. Nếu thay resolver/repository mà mất attributes, token endpoint sẽ nhận request thiếu verifier.

### Điều quan trọng trong kiến trúc BFF

- Endpoint `/oauth2/authorization/shop` thường khởi tạo luồng login.
- Authorization request cùng `state`/`code_verifier` được quản lý trong session/transaction phù hợp.
- Callback ở `/login/oauth2/code/shop` phải gắn với session đã khởi tạo.
- BFF giữ client secret và OAuth tokens **phía server**, browser chỉ giữ session cookie với `Secure; HttpOnly; SameSite` theo thiết kế.
- Không vô hiệu hóa CSRF cho toàn web application chỉ vì đã có PKCE; phiên cookie vẫn có những điểm cần CSRF defense riêng.
- Với nhiều AS/client registration, kiểm tra issuer/mix-up và không dùng chung verifier giữa registration khác nhau.

### Đoạn test tối thiểu cho cấu hình

Từ request authorization phát ra ở môi trường kiểm thử, xác nhận:

~~~text
response_type=code
client_id=shop-bff
state=<UNPREDICTABLE_VALUE>
code_challenge=<BASE64URL_HASH>
code_challenge_method=S256

Không có:
code_verifier=<RAW_VERIFIER>
client_secret=<CLIENT_SECRET>
~~~

Khi đổi code, request đến token endpoint phải có:

~~~text
grant_type=authorization_code
code=<ISSUED_CODE>
code_verifier=<ORIGINAL_VERIFIER>
client authentication theo registration
~~~

Kiểm tra **AS thực sự từ chối** verifier thiếu/sai và không chấp nhận request code grant không PKCE khi policy buộc phải dùng. Chỉ thấy tham số `code_challenge` ở client chưa chứng minh server enforce đúng.

## 12. PKCE, DPoP và mTLS bảo vệ các thời điểm khác nhau

Trong vòng đời token, ba cơ chế có thể xuất hiện ở **ba điểm**:

~~~mermaid
flowchart LR
    A["Client mở Authorization Code + PKCE"] --> B["AS phát code ràng buộc S256 challenge"]
    B --> C["Confidential Client đổi code + verifier + client auth"]
    C --> D["AS phát access token đúng audience/scope"]
    D --> E["Client gửi access token tới RS"]
    E --> F["RS kiểm tra token + sender proof nếu ràng buộc + authorization"]
~~~

| Cơ chế | Thời điểm chính | Rủi ro nó giảm | Không giải quyết |
|---|---|---|---|
| **PKCE** | Authorization request → **đổi authorization code** tại token endpoint. | Interception/injection của authorization code khi thiếu verifier. | Bản sao access token đã cấp được dùng ở RS. |
| **Client authentication** | Confidential client → AS token endpoint. | Caller không có credential của Client khó xin/đổi token với tư cách Client. | Không tự giới hạn quyền trên từng resource hoặc người giữ bearer token ở RS. |
| **DPoP** | Token issuance/request và mỗi lời gọi có DPoP proof theo profile. | Chỉ sao chép access token mà không dùng được sender key khó gọi RS. | Client bị XSS/chiếm quyền dùng key hoặc API thiếu object authorization. |
| **mTLS certificate-bound access token** | Token issuance/binding và TLS với RS. | Token bị sao chép nhưng không có khả năng dùng certificate-bound key. | Client private key bị chiếm hoặc proxy làm mất TLS client identity. |
| **Scope/audience/RS policy** | Token issuance và mỗi lời gọi API. | Token dùng sai API, sai action hoặc sai object/tenant. | Mật mã chứng minh người giữ token nếu bearer token bị lộ. |

**PKCE không phải sender-constraining access token.** Sau khi Client đã đổi code thành **bearer access token**, kẻ đánh cắp bearer token còn hiệu lực vẫn có thể thử dùng nó nếu không có sender binding/thu hồi phù hợp. PKCE không xuất hiện trong `Authorization: Bearer ...` ở mỗi API request.

## 13. PKCE và vòng đời access/refresh token

### Sau token exchange

Nếu AS phát access token:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "client_id": "shop-bff",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1893456000,
  "exp": 1893456600
}
~~~

Đây là **payload minh họa**, không phải JWT được ký có thể dùng thật. RS vẫn phải xác minh signature/JWKS hoặc introspection opaque, issuer, audience, type, time, scope và quyền owner/tenant.

### Refresh token không dùng lại PKCE verifier

**`code_verifier` là cho authorization code transaction.** Nó không phải secret dài hạn để xin token mới mãi mãi. Khi refresh token được cấp, Client dùng **grant refresh token** tại token endpoint theo chính sách; confidential client vẫn phải xác thực nếu phương thức yêu cầu, và refresh token có thể còn được ràng buộc sender proof hoặc rotation.

~~~http
POST /token HTTP/1.1
Host: auth.example.test
Authorization: Basic <BASE64_STANDARD_ENCODED_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<REFRESH_TOKEN_PLACEHOLDER>
~~~

Không cần `code_verifier` của lượt Authorization Code cũ để đổi refresh token **trừ khi một profile riêng định nghĩa thêm cơ chế khác**; không được tự “tái chế” PKCE verifier thành refresh token.

### Logout và thu hồi

User logout hoặc rút consent không tự làm mọi JWT offline hết hiệu lực ngay; AS/RS cần **TTL, revocation (RFC 7009), introspection (RFC 7662), denylist hoặc permission state** theo mức rủi ro. PKCE đã hoàn tất tại token exchange và không phải cơ chế thu hồi.

### Token bị đánh cắp sau PKCE

Nếu access token nằm trong log, browser history, request tracing hoặc môi trường client bị xâm nhập, PKCE **không giải quyết việc phát lại token đã cấp**. Phòng vệ bao gồm lưu trữ token an toàn, không log credential, TLS, scope/audience hẹp, TTL phù hợp, sender-constrained token khi cần và kiểm tra quyền tại RS.

## 14. Cách nghĩ đúng về các cuộc tấn công

### 14.1. Authorization code interception

Attacker thấy code trên callback URI nhưng **không có verifier**. Nếu Client/AS enforce PKCE S256, việc đổi code không thể thành công chỉ nhờ code. Confidential client authentication cũng giúp chặn attacker độc lập; hai cơ chế bổ sung nhau.

### 14.2. Authorization code injection

Attacker có code từ giao dịch khác rồi cố cấy vào callback của một người dùng trên BFF, khiến BFF xác thực chính nó ở token endpoint để đổi code. Nếu Client dùng verifier riêng của transaction hiện tại và AS bind code với challenge gốc, code bị cấy **không khớp**. `state`/issuer/session binding chặn các biến thể nhầm giao dịch.

### 14.3. PKCE downgrade

Attacker tìm cách bỏ `code_challenge` hoặc ép `plain`. AS phải enforce PKCE theo policy của confidential client và ghi lại method/challenge gắn với code; Client không fallback sang grant không PKCE sau lỗi.

### 14.4. Verifier bị lộ

Nếu BFF ghi verifier vào log hoặc gửi verifier tới browser, attacker có thể lấy **cả code và verifier**. Cần giữ verifier phía server, không ghi log, TTL ngắn, dùng xong xóa. Nếu Client credential cũng bị chiếm, attacker có nhiều khả năng đổi code trái phép.

### 14.5. Login CSRF, session fixation

Nếu Client không ràng buộc callback với phiên đang chờ, attacker có thể cố gắn một phiên tài khoản không mong muốn cho nạn nhân. Dùng `state`, session binding, issuer checks, cookie policy và session ID rotation sau xác thực; PKCE không phải cớ để bỏ các biện pháp này.

### 14.6. Redirect URI/open redirect

Nếu AS chấp nhận redirect URI không đăng ký hoặc Client triển khai open redirect, code có thể tới sai host. PKCE hạn chế lạm dụng code bị lộ nhưng **không hợp thức hóa một redirect URI yếu**.

### 14.7. Client secret bị lộ

Secret bị lộ có thể cho attacker thử xác thực là confidential client. PKCE làm một code cụ thể khó đổi nếu attacker không có verifier của transaction, nhưng **không ngăn attacker khởi tạo luồng mới với client credential bị chiếm** nếu có các điều kiện khác phù hợp. Cần rotation/thu hồi secret, điều tra token đã phát và giới hạn grant.

### 14.8. Authorization Server mix-up

Khi một Client hỗ trợ nhiều AS, attacker có thể cố khiến Client nhận code từ issuer A nhưng xử lý như issuer B. Giữ issuer trong transaction, xác minh authorization response issuer (RFC 9207 khi hỗ trợ) và token endpoint đúng AS; PKCE không là thay thế hoàn chỉnh cho mix-up defense.

### 14.9. RS bỏ qua audience/object quyền

PKCE hoàn hảo ở Authorization Code không sửa lỗi Billing API nhận token `aud=orders-api`, hoặc Orders cho user đọc đơn khác tenant. RS phải tiếp tục kiểm tra issuer/audience/scope/tenant/owner và token revocation theo chính sách.

## 15. Các ngộ nhận điển hình

| Ngộ nhận | Vì sao sai? | Thiết kế đúng |
|---|---|---|
| “PKCE chỉ dành cho mobile/SPA.” | PKCE hữu ích cả cho confidential client dùng Authorization Code. | Enforce **S256** và client auth đồng thời. |
| “Có client secret thì PKCE không còn giá trị.” | Secret xác thực Client; PKCE gắn **một code** với verifier của giao dịch. | Defense in depth, đặc biệt tránh code injection. |
| “Dùng PKCE thì bỏ client authentication.” | PKCE không chứng minh danh tính confidential client đã đăng ký. | Giữ client auth được cấu hình. |
| “Client ID là bí mật của PKCE.” | `client_id` công khai. | Verifier phải được tạo ngẫu nhiên và giữ ngắn hạn. |
| “Code challenge phải giữ bí mật.” | Challenge có thể đi qua front channel. | **Verifier** cần bảo mật. |
| “S256 hash trực tiếp random bytes.” | RFC 7636 hash ASCII của **verifier string**. | Dùng đúng công thức rồi Base64URL không padding. |
| “`plain` an toàn như `S256`.” | Plain phơi verifier ở authorization request. | Dùng `S256`; chặn downgrade. |
| “Một verifier cho cả ngày là tiện.” | Không gắn riêng từng transaction; nếu lộ, ảnh hưởng nhiều code. | Verifier mới cho mỗi lần bắt đầu luồng. |
| “Chỉ có code_challenge trong URL là đủ.” | AS có thể không enforce ở token endpoint. | Test verifier sai/thiếu, code không PKCE và reuse. |
| “Có PKCE thì không cần state.” | Session/callback/issuer binding còn độc lập. | Dùng state hoặc cơ chế transaction binding an toàn cùng PKCE. |
| “PKCE bảo vệ token khi bị copy sau login.” | Nó bảo vệ **code exchange**, không ràng buộc người gửi AT tại RS. | TTL, lưu token đúng và DPoP/mTLS khi cần. |
| “Refresh token được đổi bằng verifier cũ.” | Verifier chỉ cho code grant ban đầu. | Refresh token flow riêng, client auth và rotation nếu cần. |
| “Confidential client = mọi browser JS đều bí mật.” | Frontend vẫn là môi trường dễ bị quan sát/XSS. | Backend giữ secret/verifier/tokens, browser giữ session. |
| “Đã dùng PKCE thì có quyền với mọi order.” | PKCE không là authorization policy. | RS kiểm tra scope và owner/tenant. |

## 16. Ma trận kiểm thử PKCE cho confidential client

Giả sử `shop-bff` là confidential client, AS yêu cầu `S256`, Client dùng `state` và lưu verifier ở backend. Orders API yêu cầu access token `aud=orders-api` có `orders:read`.

| Trường hợp | Kết quả kỳ vọng | Mục tiêu bảo mật |
|---|---|---|
| Client gửi challenge S256 hợp lệ, đổi code bằng verifier đúng + client auth đúng | **Cấp token nếu grant/policy hợp lệ**. | Luồng chuẩn. |
| Confidential client gửi secret đúng nhưng **không có verifier** | **Từ chối token exchange** nếu code yêu cầu PKCE. | Client auth không bỏ PKCE. |
| Verifier sai một ký tự | **Từ chối**, thường `invalid_grant`. | So S256 chính xác. |
| Code bị đổi với verifier của transaction khác | **Từ chối**. | Binding code với đúng giao dịch. |
| Có verifier đúng nhưng client secret sai | **Từ chối**, thường `invalid_client`. | PKCE không bỏ client auth. |
| Client dùng private_key_jwt đúng và verifier đúng | **Có thể cấp** theo grant/policy. | Client auth method độc lập PKCE. |
| Client không có `code_challenge` nhưng policy yêu cầu PKCE | **Từ chối authorization request**. | Không downgrade. |
| Client gửi `plain` trong khi AS yêu cầu `S256` | **Từ chối**. | Không chấp nhận method yếu. |
| Authorization request dùng S256, token request muốn đổi sang plain | **Từ chối**. | Method đã cố định với code. |
| `code_verifier` quá ngắn, quá dài hoặc có ký tự không hợp lệ | **Từ chối**. | Thực thi RFC 7636 syntax. |
| Client dùng Base64 chuẩn có `+`/`/`/padding thay Base64URL challenge | **Từ chối nếu không khớp chuẩn**. | Tránh lỗi encoding. |
| S256 của verifier RFC 7636 test vector sai | **Unit test thất bại**. | Xác minh thuật toán. |
| Client tái sử dụng code đã đổi | **Từ chối lần thứ hai**. | Code một lần. |
| Code hết hạn | **Từ chối**. | Giới hạn replay. |
| `redirect_uri` trong token request không khớp bound value | **Từ chối**. | Redirect binding. |
| Code dành cho client A, client B cố đổi | **Từ chối** dù có verifier của code. | Client binding. |
| Callback có `state` không khớp phiên đang chờ | **Client từ chối**. | Login CSRF/response injection defense. |
| Hai tab login tạo hai verifier; callback tab 1 đến sau tab 2 | **Mỗi tab dùng đúng verifier**, không overwrite. | Multi-transaction isolation. |
| Callback đi đến BFF instance khác và không tìm được verifier | **Từ chối an toàn**, không bỏ PKCE. | Multi-node transaction store. |
| `code_verifier` xuất hiện trong redirect URL/log | **Audit/test phải phát hiện và loại bỏ**. | Bảo vệ bí mật transaction. |
| User từ chối consent nhưng Client vẫn thử code cũ | **Không cấp grant/token mới**. | Consent và code lifecycle. |
| Client hỗ trợ hai AS, callback issuer không khớp transaction | **Từ chối**. | Mix-up defense. |
| Token sau PKCE có `aud=billing-api` gửi Orders | **RS từ chối**. | Audience validation độc lập PKCE. |
| Token đúng audience/scope nhưng order khác owner/tenant | **RS từ chối**. | Object authorization. |
| Access token bearer bị sao chép sau khi PKCE hoàn tất | **Vẫn có nguy cơ lạm dụng**. | PKCE không tự sender-constrain AT. |
| Refresh token bị thu hồi, Client thử refresh | **AS từ chối refresh**. | Grant/revocation lifecycle. |
| Attacker biết code + challenge nhưng không có verifier/credential | **Không đổi token bằng riêng các thông tin đó**. | Challenge không phải verifier. |

Khi kiểm thử tích hợp, cần thấy **request tới AS authorization endpoint**, **token request**, **session/client transaction store** và **quyết định của RS**. Chỉ kiểm tra rằng HTTP redirect có `code_challenge` **không đủ** để chứng minh hệ thống bảo vệ code exchange.

## 17. Tình huống tự luyện

**Tình huống A — Client secret đã đủ?** Web backend đã giữ client secret trong vault và dùng HTTPS. Có nên tắt PKCE cho đỡ phức tạp?

**Giải thích:** Không nên. Client authentication bảo vệ danh tính ứng dụng ở token endpoint; PKCE ràng buộc code với transaction, bổ sung phòng thủ cho code interception/injection. Dùng cả hai trong Authorization Code flow.

**Tình huống B — Attacker có code của user khác.** Attacker gửi code từ transaction X tới callback transaction Y của BFF. BFF có client secret hợp lệ. Điều gì giúp phát hiện?

**Giải thích:** Client phải đối chiếu `state`/session/issuer, và AS kiểm tra verifier V-Y khác challenge của code X; code injection không được hợp thức hóa bởi client secret.

**Tình huống C — Code challenge lộ ở URL.** Attacker đọc được `code_challenge` trong authorization request. Có phải PKCE đã thất bại?

**Giải thích:** Không. Challenge được phép hiển thị ở front channel. Giá trị cần giữ bí mật là **verifier**, được tạo ngẫu nhiên entropy cao và không thể thực tế suy ra từ challenge S256.

**Tình huống D — S256 sai công thức.** Một developer tính SHA-256 trực tiếp trên 32 byte ngẫu nhiên thay vì ASCII của verifier đã Base64URL-encode. Vì sao AS từ chối?

**Giải thích:** Hai chuỗi dữ liệu đầu vào khác nhau nên challenge khác. RFC 7636 yêu cầu `S256 = BASE64URL(SHA256(ASCII(code_verifier)))`.

**Tình huống E — Public frontend hay confidential BFF?** SPA gọi `/oauth2/authorization/shop` trên BFF; BFF giữ verifier và client secret, đổi code và chỉ trả session cookie. Ai là OAuth Client trong giao dịch?

**Giải thích:** **BFF** là OAuth Client confidential theo kiến trúc đó; JavaScript/browser là user agent giao tiếp với BFF và đi qua redirect. Nếu SPA tự đổi code/giữ token thì mô hình khác, thường là public client.

**Tình huống F — Mất verifier sau load balancing.** Authorization request khởi tạo ở instance A; callback đến instance B không có session store dùng chung. Có thể bỏ PKCE và thử đổi code với client secret?

**Giải thích:** Không. Phải có transaction store/session routing đáng tin để lấy đúng verifier, hoặc **từ chối an toàn và khởi tạo lại**. Fallback bỏ PKCE là lỗi bảo mật.

**Tình huống G — Hai tab.** Tab 1 dùng V1, tab 2 dùng V2. Ứng dụng chỉ lưu một trường `verifier` và V2 overwrite V1. Điều gì xảy ra?

**Giải thích:** Callback tab 1 có thể thất bại vì dùng sai verifier. Cần lưu transaction **theo state/session** thay vì biến verifier chung.

**Tình huống H — Client Credentials có cần PKCE?** Một batch worker sử dụng `grant_type=client_credentials` để xin token service. Có cần thêm `code_challenge`?

**Giải thích:** PKCE được thiết kế cho **Authorization Code flow**; Client Credentials **không có authorization code** để ràng buộc. Worker vẫn cần client authentication, scope/audience, bảo vệ secret/token và sender binding nếu policy yêu cầu.

**Tình huống I — DPoP khác PKCE thế nào?** Client đã dùng S256 thành công rồi bị lộ bearer access token còn hạn. Tại sao attacker vẫn có thể gọi Orders?

**Giải thích:** PKCE chỉ bảo vệ **đổi code thành token**. Bearer token bị sao chép vẫn có thể dùng ở RS. DPoP/mTLS-bound access token có thể yêu cầu bằng chứng khóa/chứng chỉ ở request API để giảm rủi ro này.

**Tình huống J — Code sai AS.** BFF hỗ trợ hai issuer; callback chứa code từ AS-A nhưng BFF xử lý bằng token endpoint AS-B. Có thể nhờ PKCE tự sửa không?

**Giải thích:** Không. Client phải ràng buộc issuer/token endpoint với transaction và kiểm tra response issuer theo cơ chế phù hợp, tránh authorization server mix-up.

## Checklist triển khai PKCE cho confidential client

1. **Xác định đúng Client:** BFF/backend có thực sự giữ credential và đổi code phía server không; không nhúng shared secret vào SPA.
2. **Dùng PKCE khi Authorization Code:** kể cả confidential client; chọn `S256` và không tự fallback sang `plain` hoặc không PKCE.
3. **Sinh verifier đúng:** 43–128 ký tự unreserved, entropy cao (32 byte CSPRNG → Base64URL không padding), **mới cho mỗi transaction**.
4. **Tính challenge đúng:** `BASE64URL(SHA256(ASCII(code_verifier)))`, phương thức `S256` ghi rõ ở authorization request.
5. **Giữ verifier bí mật:** server-side transaction store, TTL ngắn, không log, không đặt vào URL/HTML/browser storage.
6. **Ràng buộc giao dịch:** `state`, browser session, client ID, redirect URI, issuer, scope/resource, thời hạn và kiểm soát multi-tab.
7. **Client authentication không được bỏ:** Basic/private-key JWT/mTLS đúng registration ở token endpoint **cùng verifier**.
8. **AS enforce cả hai:** code bound to client/redirect/challenge, verifier syntax + S256, one-time code và no-downgrade.
9. **Bảo vệ OAuth callback:** kiểm tra state, issuer/mix-up khi nhiều AS, PKCE transaction, session fixation protection.
10. **Chọn framework phù hợp:** Spring Security withPkce() khi cần tường minh; kiểm tra authorization request repository và token exchange thực tế.
11. **Bảo vệ token sau PKCE:** access/ID/refresh token đúng mục đích, no logging, TTL, revoke/rotation và proof-of-possession nếu cần.
12. **RS vẫn kiểm tra authorization:** trusted issuer, signature/introspection, audience, exp/nbf, scope và quyền owner/tenant/resource.
13. **Kiểm thử đường từ chối:** không verifier, sai verifier, sai code/client/redirect/state/issuer, plain downgrade, replay, tab concurrency và cache/session lỗi.

## Ghi nhớ

**PKCE không chỉ dành cho public client.** Với **confidential client** thực hiện **Authorization Code flow**, **client authentication** chứng minh danh tính ứng dụng ở token endpoint, còn **PKCE S256** ràng buộc **authorization code** với **code verifier bí mật của chính authorization transaction**. Cần giữ cả hai: verifier ngẫu nhiên mới, lưu ngắn hạn phía backend, challenge dẫn xuất công khai, AS kiểm tra code/verifier/client/redirect và chỉ cấp token theo grant thực tế. **`state`, issuer/session binding, consent, policy và object-level authorization** vẫn cần thiết. PKCE ngăn nhiều kiểu lạm dụng authorization code nhưng **không tự ngăn bearer access token bị đánh cắp hoặc phát lại sau khi token đã cấp**; vòng đời token, scope/audience, thu hồi và DPoP/mTLS khi cần là những lớp bảo vệ tiếp theo.

### Tài liệu tham khảo

- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [OpenID Connect Core 1.0 — Authorization Code Flow và ID Token](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security Reference — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
