# iat, jti, nonce và kiểm soát phát lại theo cơ chế được triển khai

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, một access token hợp lệ có thể bị sao chép và gửi lại nhiều lần nếu kẻ tấn công lấy được token. Với bearer token, đây là đặc tính của credential: Resource Server chấp nhận người trình đúng token theo policy, không biết người gửi có phải thiết bị ban đầu hay không. Vì vậy, hệ thống cần hiểu rõ những claim và cơ chế chống phát lại nào thực sự có tác dụng.

Ba tên thường gặp là **`iat`**, **`jti`** và **`nonce`**. Chúng không phải ba cách viết khác nhau của cùng một biện pháp:

- **`iat` (Issued At)** cho biết JWT được phát hành vào thời điểm nào. Ứng dụng có thể dùng nó để giới hạn tuổi tối đa của token hoặc proof, nhưng bản thân timestamp không ngăn một token bị gửi lại.
- **`jti` (JWT ID)** là định danh của một JWT. Nó chỉ giúp phát hiện replay khi verifier có một cơ chế lưu trạng thái để nhận ra ID đã được sử dụng hoặc đã bị thu hồi.
- **`nonce`** là giá trị ngẫu nhiên dùng để liên kết một thông điệp/token với một giao dịch cụ thể. OIDC dùng nonce để ràng buộc ID token với authentication request; DPoP có thể dùng server nonce để tăng độ mới của proof. Hai cách dùng này có mục đích và nơi xác minh khác nhau.

Trong hệ thống **token ràng buộc khóa**, các claim trên cần được đặt đúng vào cơ chế **proof-of-possession** như **DPoP** hoặc **mutual TLS (mTLS)**. Chỉ thêm `iat`, `jti` hoặc `nonce` vào JWT access token không tự biến bearer token thành token ràng buộc với private key của client.

> **Quy tắc cốt lõi:** kiểm tra thời gian, định danh và nonce theo đúng protocol đã phát hành; nếu cần chống replay thực sự, phải có trạng thái hoặc bằng chứng sở hữu khóa. Không coi một claim tồn tại là bằng chứng nó đã được kiểm tra.

Bài học thuộc chương **Token ràng buộc khóa**. Nội dung đi từ semantics của từng claim tới bearer replay, OIDC nonce, DPoP proof, mTLS certificate binding, cách triển khai trong Spring Security Servlet/WebFlux, dữ liệu cần lưu, thời hạn cache và kiểm thử.

## 1. Ba claim, ba vai trò khác nhau

| Claim | Ý nghĩa chuẩn | Dùng để làm gì? | Không tự làm được gì? |
|---|---|---|---|
| **`iat`** | Thời điểm JWT được phát hành (NumericDate) | Giới hạn tuổi token/proof, phát hiện timestamp bất thường | Không chứng minh token mới chỉ vì timestamp có vẻ gần hiện tại; không ngăn replay |
| **`jti`** | Định danh duy nhất của JWT theo issuer | Correlate/audit, denylist thu hồi, replay cache cho proof một lần | Không phát hiện lần gửi thứ hai nếu không có state và policy |
| **`nonce`** | Giá trị ngẫu nhiên gắn với một giao dịch/challenge | Ràng buộc ID token với OIDC request; challenge trong DPoP | Không phải một replay database; không thay chữ ký, audience, expiry hay sender binding |

### 1.1. Một ví dụ để phân biệt

JWT access token minh họa:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-842",
  "aud": ["orders-api"],
  "iat": 1893459000,
  "exp": 1893459600,
  "jti": "at-7c4e8d...",
  "scope": "orders.read"
}
~~~

Các trường có ý nghĩa:

- `iat` cho biết thời điểm phát hành; verifier có thể từ chối token quá cũ theo policy.
- `exp` xác định thời điểm hết hạn; token không được chấp nhận sau mốc này, có thể tính clock skew theo cấu hình.
- `jti` đặt tên cho token; nếu AS/RS triển khai denylist hoặc token-use tracking, nó có thể là khóa tra cứu.
- `aud` xác định API được phép nhận token; không được bỏ qua chỉ vì `iss` và chữ ký đúng.

Token trên **vẫn là bearer token**. Nếu attacker sao chép toàn bộ chuỗi JWT, họ có thể gửi lại cùng token tới `orders-api` cho tới khi token hết hạn hoặc RS nhận được trạng thái thu hồi. `iat` không ngăn điều đó. `jti` không ngăn điều đó nếu không có replay/denylist state. `nonce` cũng không tự động hiện diện hay có ý nghĩa cho access token này.

## 2. `iat`: thời điểm phát hành và giới hạn tuổi token

### 2.1. Semantics của `iat`

RFC 7519 định nghĩa `iat` là **Issued At**: thời điểm JWT được phát hành, biểu diễn dưới dạng NumericDate (số giây kể từ Unix epoch, có thể là giá trị số thực theo định nghĩa). Claim này có thể được dùng để xác định tuổi của JWT.

Ví dụ:

~~~json
{
  "iat": 1893459000,
  "exp": 1893459600
}
~~~

Trong ví dụ, token được phát hành lúc 10:10:00 và hết hạn lúc 10:20:00 nếu quy đổi timestamp theo UTC tương ứng. Khoảng cách giữa `iat` và `exp` là 10 phút.

`iat` khác `exp`:

- `iat` trả lời “token được phát hành khi nào?”
- `exp` trả lời “token không còn được chấp nhận từ khi nào?”
- `nbf` trả lời “token chưa được chấp nhận trước thời điểm nào?”

Không nên thay một validator `exp` bằng kiểm tra `iat`. Một token có `iat` mới vẫn có thể đã hết hạn nếu `exp` ở quá khứ; một token có `exp` xa vẫn có thể quá cũ so với policy nếu `iat` quá xa.

### 2.2. Kiểm tra `iat` trong tương lai

Nếu `iat` nằm xa trong tương lai so với đồng hồ Resource Server, có thể có:

- Đồng hồ AS/RS không đồng bộ.
- Token bị chỉnh sửa hoặc ký bởi nguồn không đúng.
- Lỗi cấu hình NumericDate/time zone.
- Một issuer phát hành token với clock sai.

Chữ ký hợp lệ không loại trừ lỗi clock. Có thể cho phép một **clock skew nhỏ, được định nghĩa rõ**, nhưng không chấp nhận timestamp tương lai tùy ý.

Ví dụ policy:

~~~text
now = 10:10:00
iat = 10:10:20
allowed future skew = 30 seconds
=> có thể chấp nhận điều kiện iat

now = 10:10:00
iat = 10:30:00
allowed future skew = 30 seconds
=> từ chối
~~~

### 2.3. Giới hạn tuổi tối đa

Một số API cần token mới hơn một ngưỡng nhất định, ví dụ token được phát hành trong 15 phút gần nhất. Policy:

~~~text
iat <= now + allowedFutureSkew
AND
now - iat <= maxTokenAge + allowedClockSkew
~~~

Đây là một ràng buộc **freshness** bổ sung. Nó có thể giới hạn thời gian token bị đánh cắp được sử dụng, nhưng không ngăn replay trong cửa sổ đó. Attacker gửi lại token 30 giây tuổi vẫn thỏa điều kiện max-age 15 phút.

### 2.4. `iat` không thay `exp`

Anti-pattern:

~~~java
if (jwt.getIssuedAt().isAfter(Instant.now().minusSeconds(300))) {
    accept(jwt);
}
~~~

Đoạn này chỉ kiểm token mới phát hành trong 5 phút; nó không kiểm chữ ký, issuer, audience, expiry, not-before hay scope. Một JWT hết hạn nhưng có `iat` mới vẫn không được chấp nhận. Tương tự, một token có `iat` cũ nhưng `exp` còn xa có thể bị policy max-age từ chối.

### 2.5. `iat` trong DPoP proof

Trong DPoP (RFC 9449), `iat` của **proof JWT** giúp RS/AS xác định proof có đủ mới không. Proof thường chỉ được chấp nhận trong một cửa sổ thời gian ngắn. Đây là kiểm tra freshness của proof cho một HTTP request, khác với `iat` của access token có tuổi thọ dài hơn.

Không nhầm:

| Vị trí `iat` | Ý nghĩa |
|---|---|
Access token JWT | Token được phát hành lúc nào; có thể dùng max token age theo policy |
OIDC ID token | Token xác thực được OP phát hành lúc nào; RP kiểm thời gian theo OIDC |
DPoP proof JWT | Bằng chứng sở hữu khóa cho HTTP request được tạo lúc nào; RS kiểm cửa sổ proof |
Client assertion JWT | Assertion xác thực client được tạo lúc nào; AS kiểm freshness/replay theo profile |

Một validator được viết cho access token không nên mặc định áp cùng ngưỡng cho DPoP proof, ID token và client assertion.

## 3. `jti`: định danh JWT và giới hạn của replay detection

### 3.1. `jti` là identifier, không phải cơ chế stateful

RFC 7519 định nghĩa `jti` là JWT ID, một định danh cho JWT. Issuer nên bảo đảm giá trị đủ duy nhất để tránh xác suất collision. Claim này hữu ích cho:

- Correlation/audit một token cụ thể.
- Denylist khi token bị revoke.
- Phát hiện proof JWT bị sử dụng lại.
- Chống replay cho các assertion một lần, nếu verifier ghi nhận ID đã dùng.

Nhưng chỉ thêm `jti` vào payload không ngăn một request thứ hai. Nếu RS xử lý token hoàn toàn stateless, nó không có thông tin để biết `jti` đã xuất hiện trong request trước.

### 3.2. Hai chính sách khác nhau: denylist và one-time-use

**Denylist/revocation**:

~~~text
token jti = J
store contains (issuer, J) -> revoked
=> reject
~~~

**One-time-use replay cache**:

~~~text
proof jti = P
first use: atomically record P -> accept
second use: P already exists -> reject
~~~

Hai chính sách khác nhau:

- Denylist lưu các token bị thu hồi; token không có trong store vẫn có thể dùng nhiều lần trong thời hạn hợp lệ.
- Replay cache lưu các proof đã sử dụng; một proof đã dùng không được sử dụng lần thứ hai trong cửa sổ chống replay.

Không áp one-time-use cho mọi access token OAuth thông thường nếu protocol/client được thiết kế để tái sử dụng token đó trên nhiều request. Bearer access token thường được dùng lặp lại trong suốt thời hạn của nó; việc chặn mọi lần dùng thứ hai sẽ phá hợp đồng đó. Muốn chống replay token bearer, cần sender-constrained token hoặc một policy thu hồi/freshness thích hợp.

### 3.3. Namespace `jti` theo issuer

Hai issuer có thể cùng phát hành `jti=12345`. Do đó không nên dùng riêng `jti` làm khóa toàn cục.

Khóa logic:

~~~text
revocation-key = (verified-issuer, jti)
proof-replay-key = (proof-key-thumbprint, jti)
~~~

Tùy loại proof, có thể cần thêm client/tenant/endpoint namespace. Quan trọng là khóa phải được xây từ **thông tin đã xác minh**, không dùng issuer tùy ý trong token chưa kiểm chữ ký.

### 3.4. Collision, entropy và cách phát hành

Issuer nên tạo `jti` bằng một nguồn ngẫu nhiên an toàn hoặc cơ chế identifier có xác suất collision cực thấp trong phạm vi token được phát hành. Không dùng bộ đếm dễ đoán nếu token ID có thể bị lợi dụng để dò/đoán cache entry. `jti` không cần là bí mật để thực hiện chức năng định danh, nhưng không nên để lộ thông tin nội bộ nhạy cảm trong giá trị của nó.

### 3.5. Atomicity trong replay cache

Nếu hai request giống nhau đến đồng thời, cách làm:

~~~text
if not exists(jti):
    insert(jti)
    accept
else:
    reject
~~~

có race condition nếu kiểm tra và insert là hai thao tác không nguyên tử. Cả hai request có thể cùng thấy “chưa tồn tại” rồi cùng được chấp nhận.

Phải dùng thao tác **atomic insert-if-absent / SET NX / unique constraint**:

~~~text
insert-if-absent(key, ttl)
  inserted = true  -> first use, accept
  inserted = false -> replay, reject
~~~

Với hệ thống nhiều instance, replay store phải được chia sẻ hoặc đồng bộ đủ mạnh. Cache local trong mỗi pod không phát hiện proof bị gửi tới pod khác.

### 3.6. TTL của replay entry

Replay entry cần tồn tại ít nhất tới khi proof không còn hợp lệ:

~~~text
entry TTL >= maxProofAge + allowedClockSkew
~~~

Hoặc, nếu verifier tính thời điểm hết hạn proof cụ thể:

~~~text
entry TTL = proofExpiry - now + safetyMargin
~~~

Không giữ entry vô thời hạn vì sẽ tăng memory/storage. Không đặt TTL ngắn hơn cửa sổ chấp nhận proof, nếu không proof cũ có thể được replay sau khi entry hết hạn nhưng timestamp vẫn được chấp nhận.

## 4. `nonce`: gắn token/proof với một giao dịch

`nonce` là một giá trị thường được tạo ngẫu nhiên bởi bên nhận hoặc client theo protocol. Nó giúp chứng minh một thông điệp được tạo để đáp ứng một giao dịch/challenge cụ thể, thay vì chỉ là một token hợp lệ được phát hành trước đó.

Tuy nhiên, `nonce` có nhiều ngữ cảnh:

1. **OIDC nonce:** RP tạo giá trị trong authentication request và kiểm tra ID token trả về có cùng giá trị.
2. **DPoP server nonce:** AS/RS phát challenge để client đưa nonce vào DPoP proof tiếp theo.
3. **Nonce của một protocol khác:** chỉ có ý nghĩa theo đúng đặc tả của protocol đó.

Không dùng nonce của OIDC để thay nonce của DPoP, hoặc lấy một claim `nonce` bất kỳ trong access token làm bằng chứng request hiện tại mới.

## 5. OIDC nonce: ràng buộc ID token với authentication request

### 5.1. Luồng OIDC

Khi bắt đầu OpenID Connect authentication, RP có thể tạo nonce ngẫu nhiên và lưu nó gắn với authentication transaction:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant RP as OIDC Relying Party
    participant OP as OpenID Provider
    RP->>RP: Generate random nonce N
    RP->>RP: Store N with auth transaction
    B->>OP: Authorization request + nonce=N
    OP-->>B: Redirect with authorization response
    B->>RP: Authorization code
    RP->>OP: Token request
    OP-->>RP: ID token with nonce=N
    RP->>RP: Verify ID token signature/iss/aud/time
    RP->>RP: Compare ID token nonce with stored N
    RP-->>B: Complete login if all checks pass
~~~

Nonce ràng buộc **ID token được nhận** với request do RP khởi tạo. Nếu attacker phát lại ID token từ một authentication transaction cũ, nonce thường không khớp với transaction hiện tại.

### 5.2. Kiểm tra chính xác

Nếu RP gửi `nonce=N` trong authorization request, OIDC Core yêu cầu ID token tương ứng chứa nonce claim có **giá trị giống chính xác**. RP phải giữ giá trị mong đợi một cách an toàn và so sánh khi xử lý response.

Không:

- Chấp nhận nonce thiếu khi request đã gửi nonce.
- So sánh một phần, prefix hoặc không phân biệt hoa thường tùy tiện.
- Dùng một nonce cố định cho mọi login.
- Lấy nonce kỳ vọng từ query parameter do attacker gửi ở callback.
- Dùng lại nonce sau khi transaction đã hoàn tất.

Nonce nên đủ ngẫu nhiên, gắn với transaction và được tiêu thụ một lần. Lưu trữ/cleanup phải tính đến nhiều tab và concurrent login.

### 5.3. OIDC nonce không phải `state` hoặc PKCE

Các giá trị này bảo vệ những phần khác nhau:

| Cơ chế | Bên tạo | Ràng buộc | Mục đích |
|---|---|---|---|
| `state` | OAuth/OIDC client | Authorization response với request/transaction | Chống CSRF và response mix-up theo flow |
| `nonce` | OIDC RP | ID token với authentication request | Chống replay/mix-up ID token |
| PKCE verifier/challenge | OAuth client | Authorization code với client đã khởi tạo flow | Ngăn code interception/injection |
| DPoP nonce | AS/RS | DPoP proof với challenge gần đây của server | Tăng freshness, chống một số replay |

Không bỏ một cơ chế vì đã bật cơ chế khác. Trong authorization code flow, dùng PKCE theo khuyến nghị hiện đại; dùng `state` để liên kết transaction; dùng OIDC `nonce` khi áp dụng OIDC và xác minh ID token.

### 5.4. OIDC nonce được kiểm ở RP, không phải Resource Server

Trong kiến trúc thông thường:

- `oauth2Login()`/OIDC client xử lý authorization response, ID token và nonce.
- Resource Server xử lý access token được gửi trong `Authorization: Bearer`.

Resource Server không nên yêu cầu mọi access token có OIDC `nonce` chỉ vì API được tích hợp với OIDC. Access token và ID token có profile khác nhau; claim nonce của OIDC phục vụ authentication transaction của RP.

Nếu API nhận một giao thức token tùy chỉnh có nonce, phải định nghĩa rõ issuer, audience, transaction binding, storage và replay semantics. Không tự suy ra từ OIDC Core rằng mọi access token phải có nonce.

## 6. Bearer token replay và sender-constrained token

### 6.1. Vì sao bearer token có thể bị replay?

Bearer token có semantics: bên nào nắm giữ token có thể trình token. Nếu attacker lấy được token từ:

- Browser storage/XSS.
- Mobile device đã bị compromise.
- Reverse proxy/application logs.
- Trace/APM/error reports.
- URL, query string hoặc referrer.
- Network không được bảo vệ bằng TLS.
- Một service trung gian có quyền đọc header.

thì attacker có thể gửi token đó lại tới API. `iat` và `exp` giới hạn cửa sổ, nhưng không chứng minh người gửi là client ban đầu.

### 6.2. Các biện pháp theo mức

| Biện pháp | Tác dụng | Giới hạn |
|---|---|---|
| TLS | Bảo vệ token trên đường truyền | Không ngăn token bị lấy ở endpoint/log/storage |
| Short access-token lifetime | Giới hạn thời gian replay | Không ngăn replay trong thời hạn |
| `jti` denylist | Thu hồi token cụ thể | Cần state và lookup |
| Proof replay cache | Chặn dùng lại cùng proof | Phải atomic, phân tán, TTL đúng |
| OIDC nonce | Ràng buộc ID token với login request | Không ràng buộc bearer API request |
| DPoP | Ràng buộc access token với public key và từng request proof | Client phải giữ private key; RS phải kiểm proof/replay |
| mTLS-bound token | Ràng buộc token với client certificate | Cần PKI/TLS client auth và triển khai đúng |

### 6.3. Token ràng buộc khóa thay đổi mô hình

Với bearer token:

~~~text
Ai có token -> có thể thử sử dụng token
~~~

Với sender-constrained token:

~~~text
Ai có token + có private key/certificate tương ứng
    -> mới có thể tạo bằng chứng được RS chấp nhận
~~~

DPoP dùng public/private key ở tầng HTTP application; mTLS dùng client certificate ở tầng TLS. `iat`, `jti`, nonce hỗ trợ freshness/replay handling của proof, còn `cnf` hoặc certificate thumbprint ràng buộc token với khóa.

## 7. DPoP: `iat`, `jti`, `htm`, `htu`, `ath` và nonce

**Demonstrating Proof of Possession (DPoP)** theo RFC 9449 là cơ chế OAuth để sender-constrain access token bằng public key của client. Client tạo một DPoP proof JWT và gửi kèm request; proof được ký bằng private key, public key nằm trong header proof.

### 7.1. DPoP proof header

Ví dụ minh họa:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "public-x-coordinate",
    "y": "public-y-coordinate"
  }
}
~~~

Header chứa public JWK (không chứa private key). `typ` và thuật toán phải đáp ứng RFC 9449; không chấp nhận `none` hoặc một thuật toán không an toàn do client tùy ý chọn.

### 7.2. DPoP proof payload

Ví dụ:

~~~json
{
  "jti": "proof-unique-9f2a",
  "htm": "GET",
  "htu": "https://api.example.com/orders/123",
  "iat": 1893459000,
  "ath": "base64url-sha256-of-access-token",
  "nonce": "server-issued-nonce"
}
~~~

Các claim chính:

- `jti`: identifier duy nhất của proof; RS/AS có thể dùng để phát hiện proof replay.
- `htm`: HTTP method của request, ví dụ `GET`; phải khớp request thực tế.
- `htu`: HTTP target URI theo quy tắc DPoP; phải khớp URI request sau khi xử lý proxy/normalization đúng.
- `iat`: thời điểm proof được tạo; RS/AS kiểm cửa sổ freshness.
- `ath`: hash access token được ràng buộc với proof khi gửi tới Resource Server.
- `nonce`: challenge do AS/RS phát hành khi cơ chế nonce được dùng.

DPoP proof là **một proof cho một HTTP request**. Client tạo proof mới cho request mới, không tái sử dụng cùng proof JWT cho nhiều request.

### 7.3. Header request

Khi gọi Resource Server, client gửi cả access token và proof:

~~~http
GET /orders/123 HTTP/1.1
Host: api.example.com
Authorization: DPoP ACCESS_TOKEN
DPoP: SIGNED_DPOP_PROOF_JWT
~~~

Với DPoP-bound access token, scheme authorization là `DPoP` theo RFC 9449, không đơn giản coi nó như bearer token không ràng buộc.

### 7.4. Kiểm tra tại Resource Server

RS cần kiểm tra proof theo RFC 9449 và token binding:

1. DPoP JWT signature hợp lệ bằng public JWK trong proof header.
2. `typ` là `dpop+jwt` và `alg` thuộc thuật toán được chấp nhận.
3. Public key thumbprint khớp `cnf.jkt` trong access token đã được xác minh.
4. `htm` khớp method request.
5. `htu` khớp target URI theo quy tắc chuẩn hóa DPoP.
6. `iat` nằm trong cửa sổ freshness được phép.
7. `jti` chưa xuất hiện trong replay cache cho key/proof namespace tương ứng.
8. `ath` khớp hash của access token được trình.
9. Nếu server nonce được yêu cầu, `nonce` phải khớp nonce hợp lệ còn hiệu lực.
10. Access token vẫn phải qua issuer/audience/time/scope validation độc lập.

Chỉ kiểm proof signature là chưa đủ. Một proof có chữ ký hợp lệ nhưng được tạo cho `POST /orders/123` không thể được dùng lại cho `GET /orders/123` nếu `htm` được kiểm; proof cho URI khác cũng phải bị từ chối.

### 7.5. Vì sao cần `ath`?

Proof key có thể được dùng để ký nhiều proof. `ath` gắn proof cụ thể với access token đang được gửi. Nếu không kiểm `ath`, proof hợp lệ có thể bị chuyển sang một token khác trong những tình huống không được ràng buộc đúng. RS phải tính hash theo thuật toán/quy tắc RFC 9449, không tự băm chuỗi token theo format tùy ý.

### 7.6. `cnf.jkt` liên kết access token với key

Access token DPoP-bound có thể chứa:

~~~json
{
  "iss": "https://identity.example.com",
  "aud": ["orders-api"],
  "sub": "user-842",
  "cnf": {
    "jkt": "thumbprint-of-client-public-jwk"
  },
  "scope": "orders.read"
}
~~~

`cnf.jkt` là thumbprint của public key. RS tính thumbprint từ JWK trong DPoP proof và so sánh với claim đã được xác minh trong access token. Nếu không khớp, người chỉ có access token nhưng không có private key tương ứng không thể chứng minh quyền sử dụng token.

### 7.7. DPoP server nonce

AS/RS có thể phát một nonce để client đưa vào proof tiếp theo. Luồng khái niệm:

~~~mermaid
sequenceDiagram
    participant C as DPoP Client
    participant RS as Resource Server
    C->>RS: Access token + DPoP proof (no/old nonce)
    RS-->>C: DPoP-Nonce challenge
    C->>C: Create fresh proof with nonce
    C->>RS: Same operation + new proof + server nonce
    RS->>RS: Verify signature, htm, htu, iat, jti, ath, nonce
    RS-->>C: Resource response if valid
~~~

Nonce cần được phát hành và xác minh theo RFC 9449, có thời hạn và phạm vi phù hợp. Server nonce không thay `jti` replay cache trong mọi triển khai; nonce giúp proof được tạo để đáp ứng challenge của server, còn replay detection có thể cần lưu proof IDs.

### 7.8. DPoP `jti` không phải access-token `jti`

Một request DPoP có thể mang:

- `jti` trong **access token JWT**: định danh access token.
- `jti` trong **DPoP proof JWT**: định danh proof cho HTTP request.

Hai giá trị có vòng đời và mục đích khác nhau. Replay cache cho proof phải dùng proof `jti` (và namespace/key binding thích hợp); denylist access token phải dùng access-token `jti` theo issuer. Không dùng chung một cache key không phân biệt loại token.

## 8. mTLS-bound access token

**OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens** (RFC 8705) định nghĩa cách ràng buộc access token với chứng thư client. Trong mô hình này, token có thể chứa confirmation claim:

~~~json
{
  "iss": "https://identity.example.com",
  "aud": ["orders-api"],
  "sub": "service-order-worker",
  "cnf": {
    "x5t#S256": "base64url-certificate-thumbprint"
  },
  "scope": "orders.reconcile"
}
~~~

Resource Server:

1. Xác minh access token.
2. Lấy client certificate đã được xác minh ở TLS connection.
3. Tính SHA-256 thumbprint của certificate theo RFC 8705.
4. So sánh với `cnf.x5t#S256`.
5. Từ chối nếu certificate không khớp hoặc không có certificate theo policy.

Kẻ tấn công chỉ sao chép access token nhưng không có private key của client certificate sẽ không tạo được TLS client authentication tương ứng.

### 8.1. mTLS khác DPoP

| Thuộc tính | DPoP | mTLS-bound token |
|---|---|---|
| Khóa chứng minh | JWK public/private của client | Private key của X.509 client certificate |
| Proof ở đâu? | DPoP JWT trong HTTP header | TLS handshake/client certificate |
| Gắn với request | `htm`, `htu`, `ath`, `jti`, `iat`, optional nonce | TLS connection và certificate thumbprint |
| Replay control | Proof freshness + replay cache/nonce | Certificate-bound transport; TLS bảo vệ từng kết nối |
| Hạ tầng | Cần client tạo/sign DPoP proof | Cần PKI, certificate issuance/rotation và TLS client auth |
| Proxy | Cần xử lý URI/method/headers đúng | Phải bảo toàn/ủy quyền trust của client cert qua TLS terminator |

Không coi mTLS `cnf` là một claim chỉ để log. RS phải thật sự xác minh certificate và so thumbprint.

### 8.2. TLS termination tại reverse proxy

Nếu TLS kết thúc ở load balancer/proxy, ứng dụng phía sau có thể không trực tiếp nhìn thấy client certificate. Khi đó phải có một trust contract:

- Proxy xác thực client certificate.
- Proxy xóa mọi forwarded certificate headers do caller tự gửi.
- Proxy tạo header nội bộ đã được bảo vệ hoặc chuyển certificate identity theo cơ chế được tin cậy.
- Network policy ngăn caller truy cập trực tiếp backend bỏ qua proxy.
- Ứng dụng chỉ tin header từ proxy được xác thực.

Nếu không bảo vệ ranh giới này, attacker có thể tự gửi `X-Client-Cert` giả để giả mạo certificate binding.

## 9. Spring Security: kiểm tra `iat` cho JWT access token

Spring Security Resource Server dùng `JwtDecoder` và `OAuth2TokenValidator<Jwt>` để kiểm tra JWT. Các validator mặc định thường xử lý issuer và các timestamp chuẩn như `exp`/`nbf`; **giới hạn tuổi tối đa dựa trên `iat` là policy bổ sung** mà ứng dụng phải định nghĩa nếu cần.

### 9.1. Validator kiểm tra `iat` và max age

Ví dụ cho Servlet JWT Resource Server:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class IssuedAtValidator implements OAuth2TokenValidator<Jwt> {

    private final Clock clock;
    private final Duration maxAge;
    private final Duration allowedFutureSkew;

    public IssuedAtValidator(
            Clock clock,
            Duration maxAge,
            Duration allowedFutureSkew) {
        this.clock = clock;
        this.maxAge = maxAge;
        this.allowedFutureSkew = allowedFutureSkew;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        Instant issuedAt = jwt.getIssuedAt();
        if (issuedAt == null) {
            return failure("Missing iat");
        }

        Instant now = clock.instant();
        if (issuedAt.isAfter(now.plus(allowedFutureSkew))) {
            return failure("iat is too far in the future");
        }

        if (issuedAt.isBefore(now.minus(maxAge).minus(allowedFutureSkew))) {
            return failure("Access token is too old");
        }

        return OAuth2TokenValidatorResult.success();
    }

    private OAuth2TokenValidatorResult failure(String description) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", description, null));
    }
}
~~~

Ghép validator với issuer/default validators và audience:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(trustedJwkSetUri)
    .build();

OAuth2TokenValidator<Jwt> defaults =
    JwtValidators.createDefaultWithIssuer(expectedIssuer);

OAuth2TokenValidator<Jwt> audience = jwt ->
    jwt.getAudience().contains("orders-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong audience", null));

OAuth2TokenValidator<Jwt> issuedAt =
    new IssuedAtValidator(
        Clock.systemUTC(),
        Duration.ofMinutes(15),
        Duration.ofSeconds(30));

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        defaults, audience, issuedAt));
~~~

`expectedIssuer`, `trustedJwkSetUri` và audience phải đến từ cấu hình được quản lý. Thuật toán ký cũng cần giới hạn theo contract issuer. Ví dụ `maxAge=15 minutes` và skew 30 giây chỉ là policy minh họa; không có giá trị chung cho mọi hệ thống.

### 9.2. Vì sao dùng `Clock`?

Tiêm `Clock` giúp policy thời gian có thể kiểm thử với thời điểm cố định mà không phải chờ. Trong production dùng `Clock.systemUTC()`. Trong test dùng `Clock.fixed(...)` để xác định chính xác token nào mới/cũ.

### 9.3. Không nhầm validator `iat` với replay prevention

Hai request cùng một access token có cùng `iat`. Nếu token nằm trong cửa sổ max age, cả hai đều có thể qua validator. Điều đó là bình thường đối với bearer access token reusable. Muốn từ chối token bị revoke, cần denylist; muốn proof DPoP chỉ dùng một lần, cần replay cache cho proof `jti`.

### 9.4. `iat` thiếu hoặc sai kiểu

Nếu policy bắt buộc `iat`, token không có claim phải bị từ chối. Parser/decoder có thể từ chối claim sai kiểu trước validator; không tự chuyển string tùy ý thành thời gian. Đối với issuer cũ không phát `iat`, cần quyết định tương thích có kiểm soát và thời hạn chuyển đổi; không silently accept token thiếu claim nếu threat model yêu cầu max age.

## 10. Spring Security: `jti` denylist cho access token

Một access-token `jti` có thể hỗ trợ revoke token cụ thể. Để sử dụng:

1. AS phát `jti` đủ duy nhất.
2. Resource Server xác minh JWT trước.
3. RS lấy `iss`, `jti` và `exp` từ `Jwt` đã xác minh.
4. RS kiểm tra `(iss, jti)` trong revocation store.
5. Nếu có entry, authentication bị từ chối.

### 10.1. Interface store cho Servlet

~~~java
public interface RevokedAccessTokenStore {
    boolean isRevoked(String verifiedIssuer, String jwtId);
}
~~~

Một manager có thể bọc manager JWT:

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtAuthenticationToken;

public final class RevocationCheckingAuthenticationManager
        implements AuthenticationManager {

    private final AuthenticationManager delegate;
    private final RevokedAccessTokenStore revokedStore;

    public RevocationCheckingAuthenticationManager(
            AuthenticationManager delegate,
            RevokedAccessTokenStore revokedStore) {
        this.delegate = delegate;
        this.revokedStore = revokedStore;
    }

    @Override
    public Authentication authenticate(Authentication request) {
        Authentication authenticated = delegate.authenticate(request);

        if (!(authenticated instanceof JwtAuthenticationToken jwtAuth)) {
            throw new BadCredentialsException(
                "Expected a verified JWT authentication");
        }

        var jwt = jwtAuth.getToken();
        if (jwt.getIssuer() == null || jwt.getId() == null) {
            throw new BadCredentialsException(
                "Verified issuer and jti are required");
        }

        boolean revoked = revokedStore.isRevoked(
            jwt.getIssuer().toString(), jwt.getId());

        if (revoked) {
            throw new BadCredentialsException("Access token revoked");
        }
        return authenticated;
    }
}
~~~

Đây là mẫu đồng bộ cho Servlet. `delegate` phải là manager sử dụng decoder đã kiểm tra signature/issuer/audience/time. Store nên có index/cache theo issuer và `jti`, giới hạn TTL tới `exp` cộng clock skew. Nếu store lỗi, policy cho API nhạy cảm thường fail closed hoặc trả service-unavailable; không biến lỗi database thành “not revoked”.

### 10.2. Không dùng `jti` chưa xác minh

Không làm:

~~~java
String jti = parseUnverifiedJwt(bearer).get("jti");
if (revocationStore.contains(jti)) {
    reject();
}
// Nếu không có entry thì tự tin token!
~~~

Đây vừa không xác minh token, vừa cho attacker điều khiển lookup key. Dù denylist lookup có thể xảy ra sau parse để tối ưu routing, kết quả chỉ có ý nghĩa khi token đã được xác minh và issuer namespace đáng tin cậy.

### 10.3. TTL và cleanup

Nếu access token hết hạn lúc `exp`, denylist entry có thể được xóa sau:

~~~text
exp + acceptedClockSkew + smallSafetyMargin
~~~

Nếu xóa trước khi RS ngừng chấp nhận token (ví dụ validator cho clock skew 60 giây nhưng denylist TTL chỉ tới `exp`), token có thể lọt qua trong khoảng skew. Đồng bộ TTL với chính sách thời gian thực tế.

### 10.4. `jti` denylist không phải one-time access token

Một token chưa bị revoke có thể được dùng nhiều lần. Store trên chỉ hỏi “token này đã bị thu hồi chưa?”, không hỏi “token này đã từng xuất hiện chưa?”. Nếu muốn mỗi access token chỉ dùng một lần, cần một protocol/contract đặc biệt, stateful consumption và xử lý retry/idempotency của client; không áp mặc định lên OAuth bearer access token.

## 11. DPoP replay cache và Spring Security integration

DPoP yêu cầu verifier kiểm tra proof theo request. `jti` của proof phải được kiểm soát để cùng một proof không được replay trong cửa sổ chấp nhận.

### 11.1. Replay store cho proof

Interface khái niệm:

~~~java
public interface DpopProofReplayStore {
    boolean markIfNew(String key, Duration ttl);
}
~~~

Giá trị trả về:

- `true`: key chưa tồn tại và đã được ghi atomically; proof có thể tiếp tục nếu mọi kiểm tra khác hợp lệ.
- `false`: key đã tồn tại; proof là replay và phải bị từ chối.

Key có thể được xây từ:

~~~text
key = thumbprint(public JWK) + ":" + proof.jti
~~~

Không dùng riêng `jti` nếu namespace nhiều client/key. Thumbprint phải được tính từ JWK đã được kiểm tra và chuẩn hóa theo RFC, không dùng chuỗi header tùy ý.

### 11.2. Pseudocode verifier

~~~text
verifyDpopRequest(request, accessToken, proof):
    parse proof JWT under size/format limits
    verify proof signature with proof public JWK
    require typ = dpop+jwt
    validate allowed asymmetric algorithm
    validate htm == actual HTTP method
    validate htu == normalized external request URI
    validate iat within freshness window
    validate nonce if server nonce policy is enabled
    validate ath == hash(accessToken)

    decode and validate access token independently
    require accessToken.cnf.jkt == thumbprint(proof.publicJwk)

    key = thumbprint(proof.publicJwk) + ":" + proof.jti
    if replayStore.markIfNew(key, proofWindow) == false:
        reject replay

    continue with scope and domain authorization
~~~

Thứ tự cụ thể có thể tối ưu theo cost, nhưng không được ghi nhận `jti` như một proof hợp lệ trước khi các binding cần thiết được xác minh. Nếu attacker có thể gửi proof rác để chiếm `jti` của client khác, replay store có thể bị poison/DoS. Key namespace và validation order rất quan trọng.

### 11.3. Atomic replay check

Một triển khai Redis có thể dùng lệnh tương đương `SET key value NX EX seconds` để bảo đảm check-and-set nguyên tử. Với database, dùng unique constraint/insert transaction. Không dùng:

~~~java
if (!redis.exists(key)) {
    redis.set(key, value, ttl);
}
~~~

vì hai request đồng thời có thể cùng qua `exists` trước khi bất kỳ request nào ghi.

### 11.4. Reverse proxy và `htu`

DPoP `htu` ràng buộc proof với URI request. Nếu app nằm sau reverse proxy:

- `Host`, scheme và path bên ngoài có thể khác backend URI.
- `Forwarded`/`X-Forwarded-*` headers chỉ được tin khi đến từ proxy đã cấu hình.
- Không để client tự đặt forwarded host để làm URI validation khớp với proof giả.
- Chuẩn hóa URI đúng quy tắc RFC 9449, không tự thêm query/fragment hoặc canonicalization khác.
- Test cả path encoding, port, scheme và proxy rewrite.

Nếu resolver dùng URI backend nhưng client ký URI public, tất cả DPoP request hợp lệ có thể bị từ chối. Ngược lại, nếu tin forwarded headers tùy ý, attacker có thể làm proof được xác minh trên URI không đúng.

### 11.5. Spring Security có sẵn DPoP hay cần extension?

Khả năng hỗ trợ DPoP thay đổi theo phiên bản Spring Security và integration của Authorization Server/Resource Server. Không giả định cấu hình `oauth2ResourceServer().jwt()` thông thường tự động:

- Đọc `DPoP` header.
- Kiểm tra proof JWT.
- So `cnf.jkt`.
- Kiểm `ath`, `htm`, `htu`, nonce.
- Dùng replay store phân tán.

Hãy đối chiếu đúng version và provider. Nếu stack không có hỗ trợ DPoP đầy đủ, cần tích hợp một implementation tuân RFC 9449 vào authentication pipeline trước khi cấp Authentication, hoặc dùng một gateway/resource server hỗ trợ. Không viết một filter chỉ parse `jti` rồi gọi đó là DPoP.

## 12. Spring Security WebFlux: xử lý stateful replay checks không blocking

Trong WebFlux, `ReactiveJwtDecoder` và `ReactiveAuthenticationManager` cho phép xác minh token theo reactive chain. Nếu thêm denylist hoặc replay store, lookup phải được compose bất đồng bộ.

### 12.1. Reactive revocation store

~~~java
public interface ReactiveRevokedAccessTokenStore {
    Mono<Boolean> isRevoked(String verifiedIssuer, String jwtId);
}
~~~

Một wrapper `ReactiveAuthenticationManager` có thể làm:

~~~java
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtAuthenticationToken;
import reactor.core.publisher.Mono;

public final class RevocationCheckingReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final ReactiveAuthenticationManager delegate;
    private final ReactiveRevokedAccessTokenStore revokedStore;

    public RevocationCheckingReactiveAuthenticationManager(
            ReactiveAuthenticationManager delegate,
            ReactiveRevokedAccessTokenStore revokedStore) {
        this.delegate = delegate;
        this.revokedStore = revokedStore;
    }

    @Override
    public Mono<Authentication> authenticate(Authentication request) {
        return delegate.authenticate(request)
            .switchIfEmpty(Mono.error(
                new BadCredentialsException("No authentication result")))
            .flatMap(auth -> {
                if (!(auth instanceof JwtAuthenticationToken jwtAuth)) {
                    return Mono.error(new BadCredentialsException(
                        "Expected verified JWT authentication"));
                }

                var jwt = jwtAuth.getToken();
                if (jwt.getIssuer() == null || jwt.getId() == null) {
                    return Mono.error(new BadCredentialsException(
                        "Verified issuer and jti are required"));
                }

                return revokedStore.isRevoked(
                        jwt.getIssuer().toString(), jwt.getId())
                    .flatMap(revoked -> revoked
                        ? Mono.error(new BadCredentialsException(
                            "Access token revoked"))
                        : Mono.just(auth));
            });
    }
}
~~~

Đây là mẫu minh họa reactive; các imports `Mono` và project interfaces cần được cung cấp. `delegate` phải là `JwtReactiveAuthenticationManager` đã dùng `ReactiveJwtDecoder` với issuer/audience/time validators. Không gọi blocking Redis/DB trên Netty event loop và không tự `subscribe()` bên trong manager.

### 12.2. Reactive replay cache

Với DPoP proof, interface có thể là:

~~~java
public interface ReactiveDpopProofReplayStore {
    Mono<Boolean> markIfNew(String proofKey, Duration ttl);
}
~~~

Pipeline:

~~~java
return verifyProofCryptographically(proof)
    .flatMap(verifiedProof -> {
        String replayKey = verifiedProof.keyThumbprint()
            + ":" + verifiedProof.jti();
        return replayStore.markIfNew(replayKey, proofTtl)
            .flatMap(firstUse -> firstUse
                ? Mono.just(verifiedProof)
                : Mono.error(new InvalidDpopProofException(
                    "DPoP proof replayed")));
    });
~~~

`verifyProofCryptographically` ở đây đại diện cho một verifier DPoP đầy đủ; không phải helper có sẵn của Spring Security ở mọi version. Nó phải kiểm header, signature, `htm`, `htu`, `iat`, `ath`, nonce và access-token `cnf` theo RFC 9449. Replay store chỉ là **một phần** của toàn bộ validation.

### 12.3. Reactor Context không thay replay store

Reactor Context giữ SecurityContext cho reactive execution. Nó không phải bộ nhớ dùng chung giữa requests/pods và không tự nhận biết `jti` đã được dùng. Không lưu set các proof IDs trong một biến local của request hoặc Reactor Context rồi coi đó là replay protection phân tán.

## 13. DPoP nonce và OIDC nonce: tránh nhầm lẫn

| Thuộc tính | OIDC `nonce` | DPoP server `nonce` |
|---|---|---|
| Ai tạo? | OIDC RP/client | AS hoặc Resource Server |
| Gắn với | Authentication request | DPoP proof/request |
| Được gửi ở đâu? | Authorization request, rồi xuất hiện trong ID token | DPoP proof JWT |
| Ai xác minh? | OIDC RP | DPoP verifier tại AS/RS |
| Mục đích | Liên kết ID token với login transaction, chống replay/mix-up | Challenge/freshness cho proof, tăng chống replay |
| Thay thế `jti` replay cache? | Không | Không nhất thiết; phụ thuộc policy, vẫn cần xử lý proof replay theo RFC |
| Dùng cho access token thường? | Không mặc định | Chỉ khi DPoP flow yêu cầu |

Một claim tên `nonce` không có semantics toàn cục. Luôn xác định **token/proof profile** đang xử lý trước khi kiểm tra nó.

## 14. Client assertion và replay control

Một số OAuth client dùng JWT client assertion để xác thực với token endpoint. Assertion có thể chứa `iss`, `sub`, `aud`, `exp`, `iat` và `jti` theo profile áp dụng.

AS có thể:

- Kiểm tra audience là token endpoint đúng.
- Kiểm tra thời hạn assertion ngắn.
- Kiểm tra `iat` trong cửa sổ chấp nhận.
- Ghi nhận `jti` để từ chối assertion bị dùng lại.

Đây là **client authentication tại AS**, không phải access-token authentication tại Resource Server. Không tái sử dụng replay cache của client assertion cho DPoP proof hoặc access token mà không phân biệt namespace/semantics.

Nếu AS không ghi nhận `jti` đã dùng, một assertion hợp lệ có thể bị replay trong cửa sổ hiệu lực tùy contract. Các client assertion profile cần được kiểm tra theo RFC/provider configuration cụ thể.

## 15. Phát hành token và proof đúng cách

### 15.1. Issuer tạo access token

Với JWT access token, AS nên:

- Phát hành `iat`, `exp` và các claims theo token profile.
- Cấp `jti` đủ duy nhất nếu cần định danh/revocation/audit.
- Đặt `aud` đúng Resource Server.
- Không thêm `nonce` tùy tiện rồi tuyên bố token không thể replay.
- Nếu hỗ trợ sender-constrained token, gắn `cnf` đúng public key/certificate đã xác minh.
- Không phát hành token với lifetime dài hơn policy cần thiết.

### 15.2. Client tạo DPoP proof

Cho mỗi request:

1. Tạo `jti` mới, không tái sử dụng proof trước.
2. Đặt `iat` gần thời điểm hiện tại.
3. Đặt `htm` đúng method và `htu` đúng target URI.
4. Đặt `ath` theo access token đang gửi tới RS.
5. Đưa nonce của server vào proof nếu server yêu cầu.
6. Ký proof bằng private key tương ứng với key đã bind access token.
7. Gửi access token và proof trong headers phù hợp.

Private key phải được bảo vệ bằng platform secure storage/keystore/HSM phù hợp; nếu private key bị lấy, DPoP binding mất ý nghĩa với attacker.

### 15.3. Token refresh và key rotation

Nếu access token được bind với DPoP key A, token mới sau refresh có thể:

- Tiếp tục bind key A theo contract; hoặc
- Được cấp bind với key mới B qua một flow được AS hỗ trợ.

Client không thể tự thay `cnf.jkt` trong token. Nếu private key bị mất/compromise, cần thực hiện flow cấp token/key mới và revoke token cũ theo policy.

Với mTLS, certificate rotation cũng cần đồng bộ giữa AS và RS; token cũ gắn thumbprint certificate cũ có thể không dùng được với certificate mới. Đừng bỏ kiểm tra binding để hỗ trợ chuyển đổi.

## 16. Những lỗi triển khai thường gặp

| Anti-pattern | Vì sao sai | Cách xử lý |
|---|---|---|
Chỉ kiểm tra `iat` mới | Token vẫn có thể replay nhiều lần trong cửa sổ | Sender constraint hoặc replay state |
Có `jti` nên nghĩ token one-time | `jti` chỉ là identifier | Dùng store atomic và policy đúng loại token |
Dùng một replay cache local trong từng pod | Replay tới pod khác vẫn qua | Store phân tán/consistency phù hợp |
Dùng riêng `jti` làm cache key | Issuer/client/key khác có thể collision | Namespace bằng verified issuer hoặc proof key thumbprint |
TTL replay entry ngắn hơn proof acceptance window | Proof replay sau khi entry hết hạn | Tính TTL theo freshness window + skew |
Dùng OIDC nonce cho API bearer token | Nonce thuộc login transaction/ID token | Dùng access-token validation và sender constraint |
Dùng nonce cố định cho mọi login | Không gắn với transaction riêng | Random nonce per authentication transaction |
Không so nonce trong ID token | Mất liên kết request/response | RP kiểm exact match |
Dùng DPoP proof nhiều lần | Cùng proof có thể bị replay | Tạo proof mới cho mỗi request |
Chỉ verify DPoP signature | Chưa kiểm method, URI, token, freshness, key binding | Verify đầy đủ RFC 9449 |
Không kiểm `ath` | Proof không ràng buộc đúng access token | Tính và so access-token hash |
Không kiểm `cnf.jkt` | Token có thể dùng với proof key khác | So JWK thumbprint với access token |
Tin `X-Forwarded-Host` tùy ý khi kiểm `htu` | Attacker có thể làm sai URI binding | Trusted proxy configuration |
Dùng `jti` access token làm `jti` proof | Trộn vòng đời và namespace | Tách token ID và proof ID |
Gọi `block()` trong WebFlux replay lookup | Chặn event loop | Reactive store và compose `Mono` |
Chấp nhận token khi replay store timeout | Không xác định proof/token đã bị revoke/replay chưa | Fail closed hoặc lỗi dịch vụ theo SLA |
Yêu cầu OIDC nonce trong mọi access token | Nhầm ID token profile với access token profile | Validate đúng loại token |
Cho rằng mTLS chỉ cần `cnf` claim | Không xác minh certificate tại TLS | So thumbprint với certificate đã xác thực |

## 17. Kiểm thử thời gian, nonce và replay

Một test suite phải chứng minh **điều kiện nào được kiểm tra và state nào được lưu**. Chỉ kiểm token có claim tồn tại là chưa đủ.

### 17.1. Ma trận `iat`

| Token/proof | Kết quả |
|---|---|
`iat` hiện tại, `exp` tương lai, issuer/audience hợp lệ | Qua freshness check |
`iat` xa trong tương lai hơn skew | Reject |
`iat` cũ hơn max age | Reject theo policy |
Thiếu `iat` khi profile yêu cầu | Reject |
`iat` mới nhưng `exp` đã qua | Reject do expiry |
`iat` hợp lệ nhưng chữ ký sai | Reject |
Clock skew trong ngưỡng cấu hình | Xử lý theo policy |

Dùng `Clock.fixed(...)` để test deterministic; không dựa vào `Thread.sleep`.

### 17.2. Ma trận `jti`

| Tình huống | Kết quả |
|---|---|
Hai access token khác nhau có `jti` khác nhau | Cả hai có thể hợp lệ |
Access token `jti` nằm trong denylist cùng issuer | Reject |
Cùng `jti` nhưng issuer khác | Không nhầm thành cùng token |
DPoP proof `jti` lần đầu | Có thể accept nếu mọi check khác đúng |
DPoP proof cùng key + `jti` lần hai | Reject replay |
Hai request đồng thời cùng proof | Chỉ một request thắng atomic insert |
Replay store unavailable | Fail closed hoặc lỗi service theo policy |
Replay entry hết TTL nhưng proof vẫn nằm trong cửa sổ chấp nhận | Test phải phát hiện cấu hình TTL sai |

### 17.3. Ma trận OIDC nonce

- Authorization request tạo nonce ngẫu nhiên N và lưu theo transaction.
- ID token có nonce N, đúng issuer/audience/time/signature → RP có thể hoàn tất login.
- ID token thiếu nonce khi request đã gửi nonce → reject.
- ID token nonce khác N → reject.
- Callback lặp lại với cùng transaction đã tiêu thụ → reject hoặc xử lý idempotently theo flow.
- Hai tab login có hai nonce khác nhau; callback tab A không dùng nonce của tab B.
- Không lấy nonce mong đợi từ query parameter callback.

### 17.4. Ma trận DPoP

| Thay đổi trong proof/request | Kết quả |
|---|---|
Proof signature sai | Reject |
`typ` không phải `dpop+jwt` | Reject |
`alg` không được phép | Reject |
`htm` khác HTTP method | Reject |
`htu` khác request target | Reject |
`iat` quá cũ/quá tương lai | Reject |
`jti` đã dùng trong replay window | Reject |
`ath` không khớp access token | Reject |
JWK thumbprint không khớp access token `cnf.jkt` | Reject |
Nonce bắt buộc nhưng thiếu/sai | Reject/challenge theo RFC |
Proof mới, token binding đúng, scope đúng | Có thể tiếp tục authorization |

### 17.5. MockMvc/WebTestClient và kiểm thử integration

`mockJwt()`/`jwt()` có thể tạo Authentication giả lập và bỏ qua `JwtDecoder`, DPoP verifier hoặc replay store. Chúng phù hợp để test HTTP authorization sau authentication, nhưng không chứng minh:

- `iat` validator thật đã chạy.
- `jti` store được gọi atomically.
- OIDC nonce được so với transaction đã lưu.
- DPoP `ath`, `htm`, `htu`, `cnf.jkt` được kiểm.
- Replay proof bị chặn giữa nhiều application instances.

Với Servlet, gửi Bearer token/JWT đã ký bằng test key qua filter chain. Với WebFlux, gửi request thật qua `WebTestClient` và compose reactive manager/store. Dùng Redis/test database hoặc fake store có atomic semantics để kiểm concurrency. Test DPoP nên dùng client keypair test, proof signer và verifier thực tế của hệ thống.

## 18. Vận hành replay protection trong hệ thống phân tán

### 18.1. Consistency quan trọng hơn chỉ có cache

Giả sử:

~~~text
Request proof P -> RS instance A -> cache A: not found -> accept
Replay proof P  -> RS instance B -> cache B: not found -> accept
~~~

Replay protection local không đủ. Các instance cần cùng một replay store hoặc một cơ chế partition/routing bảo đảm proof cùng namespace được kiểm tra tại một nơi duy nhất có tính nhất quán đủ mạnh.

### 18.2. Availability và fail-closed

Nếu DPoP replay store không truy cập được, RS không biết proof đã dùng chưa. Lựa chọn:

- **Fail closed:** từ chối request hoặc trả lỗi service-unavailable; phù hợp khi replay prevention là yêu cầu bắt buộc.
- **Fail open:** chấp nhận proof dù không kiểm được replay; tăng availability nhưng mất bảo đảm chống replay trong khoảng lỗi.

Đây là quyết định threat model/SLA, không phải một chi tiết cache. Không silently fail open.

### 18.3. Capacity và cardinality

DPoP proof có thể phát sinh một entry mỗi request. Cần:

- TTL ngắn nhưng đủ cửa sổ proof.
- Storage có throughput phù hợp.
- Key hashing/namespacing để không lưu dữ liệu nhạy cảm thừa.
- Metrics cho cache hit/replay reject/store latency/error.
- Rate limit theo client/key để ngăn replay-store exhaustion.
- Cleanup tự động theo TTL.

Không log toàn bộ proof JWT hoặc private/public key material; log proof outcome, key thumbprint rút gọn và request correlation ID theo chính sách.

### 18.4. Idempotency khác replay prevention

Một client có thể gửi lại một HTTP operation hợp lệ vì timeout không biết server đã xử lý hay chưa. Replay prevention DPoP chặn **cùng proof**; client có thể tạo proof mới cho request mới. Với POST tạo đơn hàng, proof mới vẫn có thể thực hiện cùng nghiệp vụ lần nữa. Vì vậy API cần **Idempotency-Key** hoặc business idempotency theo contract cho thao tác không được lặp.

Không dùng `jti` proof để thay idempotency key nghiệp vụ; hai cơ chế bảo vệ các lớp khác nhau:

- DPoP `jti`: proof JWT không được dùng lại.
- Idempotency key: một business operation không bị thực thi hai lần do retry.

## 19. Quy trình chọn cơ chế theo yêu cầu

| Yêu cầu | Cơ chế phù hợp | Điều cần triển khai |
|---|---|---|
Giới hạn token quá cũ | `iat` + max-age validator | Clock, skew, max age, test |
Thu hồi JWT cụ thể trước `exp` | `jti` denylist | Store issuer-scoped, TTL, consistency |
Chống replay một DPoP proof | Proof `jti` replay cache | Atomic insert, TTL, distributed store |
Ràng buộc ID token với login request | OIDC `nonce` | RP transaction storage và exact match |
Tăng freshness cho DPoP proof | DPoP server nonce | Issue/validate nonce theo RFC 9449 |
Chống replay bearer token bị đánh cắp | DPoP hoặc mTLS-bound token | Private key/certificate binding và RS enforcement |
Thu hồi opaque access token | RFC 7662 introspection | `active`, audience/resource binding, cache TTL |
Ngăn retry tạo nghiệp vụ trùng | Idempotency key | Business store/atomic operation |

Không chọn `iat`, `jti` hay `nonce` chỉ vì claim đó dễ thêm vào JWT. Hãy bắt đầu từ threat:

1. Attacker có thể replay **access token** hay **proof JWT**?
2. Có cần chặn lần thứ hai hay chỉ cần revoke một token?
3. Có cần chứng minh caller sở hữu private key không?
4. Server có trạng thái dùng chung không?
5. Mức độ trễ tối đa chấp nhận được là bao nhiêu?
6. Token profile nào quy định semantics của claim?

## 20. Kết luận

~~~text
iat
  = WHEN was this JWT issued?
  -> freshness / max-age / future-time validation
  -> does not stop replay by itself

jti
  = WHICH JWT/proof is this?
  -> audit / denylist / replay cache key
  -> needs state and atomic policy to detect reuse

nonce
  = WHICH transaction/challenge is this bound to?
  -> OIDC request <-> ID token
  -> DPoP server challenge <-> proof
  -> semantics depend on protocol

SENDER CONSTRAINT
  DPoP: cnf.jkt + signed per-request proof
  mTLS: cnf.x5t#S256 + authenticated client certificate

REPLAY DEFENSE
  freshness + correct binding + state/atomicity
  + distributed enforcement + explicit failure policy
~~~

`iat`, `jti` và `nonce` là các building blocks có mục đích riêng. `iat` hỗ trợ kiểm tra freshness; `jti` cung cấp định danh để denylist hoặc phát hiện proof bị dùng lại khi có state; OIDC `nonce` ràng buộc ID token với authentication request. Không claim nào tự chứng minh caller sở hữu khóa hoặc làm bearer access token trở thành one-time credential.

Trong kiến trúc **token ràng buộc khóa**, DPoP kết hợp public-key binding (`cnf.jkt`) với proof cho từng HTTP request, còn mTLS ràng buộc token với certificate đã được xác minh (`cnf.x5t#S256`). Resource Server cần kiểm tra đầy đủ chữ ký, audience, thời gian, request binding, token binding và replay state theo đúng profile. Với Spring Security, các validator JWT chuẩn là nền tảng; denylist/replay cache và DPoP/mTLS integration cần được kết nối vào authentication pipeline một cách tường minh, đặc biệt trong WebFlux phải giữ I/O bất đồng bộ.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): `iat`, `jti`, `nonce`, `exp`, `nbf` và NumericDate.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC authentication request, ID Token validation và nonce.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof JWT, `jti`, `iat`, `htm`, `htu`, `ath`, nonce và `cnf.jkt`.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS client authentication và `cnf.x5t#S256`.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token profile.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): replay, sender-constrained tokens và bảo vệ OAuth deployments.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, refresh token và authorization grants.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer-token semantics và threat model.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): tính JWK thumbprint dùng trong key binding.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái token.
- [Spring Security Reference — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, validators và authorities.
- [Spring Security Reference — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder` và WebFlux authentication.
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OIDC client authentication và ID token processing.
- [Spring Security API — OAuth2TokenValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2TokenValidator.html): custom JWT claim validation.
