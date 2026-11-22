# Kiểm thử proof bị thay đổi, phát lại, sai khóa hoặc sai yêu cầu

## 1. Vì sao cần kiểm thử proof-of-possession?

Trong OAuth 2.0 Resource Server, một Bearer access token có thể được sử dụng bởi bất kỳ bên nào sở hữu chuỗi token. Nếu token bị lộ qua log, browser storage, proxy hoặc downstream service, kẻ lấy được token có thể thử sử dụng nó trong thời gian token còn hiệu lực.

**Proof-of-possession (PoP)** bổ sung bằng chứng rằng caller đang sở hữu một khóa riêng tương ứng với khóa đã được ràng buộc vào access token. Với cơ chế **DPoP — Demonstrating Proof of Possession**, client tạo một proof JWT cho từng HTTP request. Resource Server xác minh chữ ký proof, kiểm tra khóa có khớp access token và xác minh proof mô tả đúng request hiện tại.

Bài này tập trung vào việc kiểm thử các tình huống:

- Proof bị sửa sau khi ký.
- Proof được ký bằng khóa khác với khóa ràng buộc trong access token.
- Proof cũ bị phát lại.
- Proof mô tả sai HTTP method hoặc target URI.
- Proof chứa access-token hash sai.
- Proof có thời gian phát hành, nonce hoặc key ID không hợp lệ.
- Client gửi Bearer token ở endpoint bắt buộc DPoP.
- Reverse proxy làm thay đổi cách Resource Server nhìn thấy scheme/host/path.
- Key rotation làm token cũ và proof mới không còn cùng một cặp khóa.

**Mục tiêu kiểm thử** là chứng minh Resource Server chỉ chấp nhận một proof hợp lệ cho đúng access token và đúng HTTP request, đồng thời từ chối các biến thể bị sửa, phát lại hoặc dùng sai ngữ cảnh.

## 2. DPoP proof gắn access token với một khóa

### 2.1. Các thành phần tham gia

DPoP có ba thành phần chính:

1. **Access token:** token do Authorization Server cấp. Token được ràng buộc với public key bằng confirmation claim `cnf.jkt`.
2. **DPoP proof JWT:** client ký bằng private key tương ứng. Proof chứa public JWK và thông tin request.
3. **Resource Server:** xác minh access token, proof signature, key binding và các claims mô tả request.

Luồng đơn giản:

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>AS: Token request + DPoP proof
    AS->>AS: Verify proof và ghi nhận key thumbprint
    AS-->>C: DPoP-bound access token (cnf.jkt)
    C->>RS: Authorization: DPoP access_token + DPoP proof
    RS->>RS: Verify access token và cnf.jkt
    RS->>RS: Verify proof signature, htm, htu, ath, iat, jti, nonce
    RS-->>C: Resource response hoặc DPoP error
~~~

Ở token endpoint, DPoP proof chứng minh client đang giữ private key trong quá trình xin token. Khi access token được phát hành, AS ràng buộc token với public key tương ứng. Ở Resource Server, proof mới được gửi cho **mỗi request** để chứng minh client vẫn giữ private key đó.

### 2.2. DPoP khác Bearer token như thế nào?

| Đặc điểm | Bearer | DPoP-bound access token |
|---|---|---|
| Credential gửi đến API | `Authorization: Bearer ...` | `Authorization: DPoP ...` |
| Bằng chứng sở hữu khóa | Không bắt buộc | Có DPoP proof JWT |
| Ràng buộc khóa trong access token | Không yêu cầu | `cnf.jkt` chứa JWK thumbprint |
| Proof theo từng request | Không | Có |
| Chống token bị lấy cắp đơn lẻ | Hạn chế | Kẻ tấn công còn cần private key phù hợp |
| Replay protection | Dựa vào token lifetime/revocation và controls khác | Cần freshness, nonce và replay policy |
| TLS | Vẫn bắt buộc | Vẫn bắt buộc |

DPoP không mã hóa access token và không thay thế TLS. Nó cũng không tự xác định user identity hoặc quyền trên resource; các việc đó vẫn thuộc access token validation và authorization.

### 2.3. Header của request

Một request minh họa:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <DPoP_PROOF_JWT>
~~~

Hai giá trị có nhiệm vụ khác nhau:

- `Authorization` chứa access token được ràng buộc khóa.
- `DPoP` chứa proof JWT cho request hiện tại.

Không gửi proof JWT vào vị trí access token. Không mặc định một Bearer token bất kỳ trở thành DPoP-bound chỉ vì request có header `DPoP`.

## 3. Cấu trúc DPoP proof JWT

### 3.1. JOSE header

DPoP proof là JWT có chữ ký bất đối xứng. Header điển hình:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<PUBLIC-X>",
    "y": "<PUBLIC-Y>"
  }
}
~~~

Các điểm cần kiểm soát:

- `typ` phải là `dpop+jwt` theo DPoP profile.
- `alg` phải là thuật toán bất đối xứng được server cho phép; không chấp nhận `none` hoặc thuật toán ngoài allowlist.
- `jwk` chứa public key dùng xác minh proof.
- Không đưa private JWK members như `d`, `p`, `q` vào proof header.
- `jwk` là public key do client gửi; bản thân nó chưa được tin cho đến khi thumbprint khớp với access token confirmation claim.

### 3.2. Payload claims

Một proof cho request tới Orders API có thể có:

~~~json
{
  "jti": "proof-8b9c1d",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1794700800,
  "ath": "<BASE64URL-SHA256-OF-ACCESS-TOKEN>",
  "nonce": "<SERVER-PROVIDED-NONCE>"
}
~~~

Ý nghĩa:

| Claim | Ý nghĩa | Kiểm thử quan trọng |
|---|---|---|
| `jti` | ID duy nhất của proof | Phát lại cùng proof phải bị phát hiện |
| `htm` | HTTP method | Phải khớp method thực tế |
| `htu` | HTTP target URI, không gồm query và fragment theo DPoP | Phải khớp URI thực tế theo quy tắc chuẩn hóa |
| `iat` | Thời điểm tạo proof | Từ chối proof quá cũ hoặc ở tương lai ngoài clock skew |
| `ath` | Hash access token gửi cùng request | Token khác hoặc hash sai phải bị từ chối |
| `nonce` | Nonce do server cấp, nếu server yêu cầu | Nonce thiếu, cũ hoặc không đúng phải bị từ chối |

Với Resource Server request mang access token, `ath` là một phần bắt buộc của DPoP proof theo RFC 9449. Không dùng hash của chuỗi token đã decode hoặc của JSON claims; hash được tính trên **giá trị access token thực tế** được gửi trong Authorization header.

### 3.3. Access token confirmation claim

Một JWT access token DPoP-bound có thể chứa:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "jkt": "<JWK-THUMBPRINT>"
  }
}
~~~

`cnf.jkt` là thumbprint của public JWK mà client dùng để ký DPoP proofs. Với opaque access token, Resource Server cần lấy confirmation information từ introspection response theo contract của AS.

**Không xác thực proof chỉ bằng cách kiểm tra chữ ký với JWK nhúng trong proof.** Kẻ tấn công có thể tự tạo key pair và ký proof bằng key của họ. Resource Server còn phải tính thumbprint của public JWK đó và so sánh chính xác với `cnf.jkt` trong access token đã được xác minh.

## 4. JWK thumbprint và kiểm tra khóa ràng buộc

### 4.1. Thumbprint xác định public key

DPoP sử dụng JWK thumbprint theo RFC 7638. Với một public JWK, thumbprint được tạo từ tập member bắt buộc và biểu diễn JSON canonical theo loại key, sau đó SHA-256 và Base64URL encoding.

Ví dụ EC P-256, các thành phần canonical liên quan gồm:

~~~json
{
  "crv": "P-256",
  "kty": "EC",
  "x": "<PUBLIC-X>",
  "y": "<PUBLIC-Y>"
}
~~~

Với RSA, các member chính gồm `e`, `kty` và `n`. Không đưa private parameters hoặc optional members không thuộc canonical set vào thumbprint calculation.

Không tự nối chuỗi JSON tùy ý rồi hash. Thứ tự member và cách canonicalize phải tuân RFC 7638.

### 4.2. Hai lỗi khóa cần phân biệt

**Trường hợp A — Chữ ký proof sai:**

- Header proof chứa public key K1.
- Proof được ký bằng private key K2.
- Chữ ký không verify được bằng K1.
- Kết quả: proof signature invalid.

**Trường hợp B — Chữ ký đúng nhưng access token bound với key khác:**

- Header proof chứa public key K2.
- Proof được ký đúng bằng private key K2.
- Access token có `cnf.jkt` của K1.
- Chữ ký proof hợp lệ, nhưng thumbprint K2 không khớp token binding K1.
- Kết quả: reject vì key binding mismatch.

Hai trường hợp phải có fixture và assertion riêng. Nếu chỉ test chữ ký sai, suite chưa chứng minh được bước so sánh `cnf.jkt` hoạt động.

### 4.3. Ma trận khóa

| Access token `cnf.jkt` | Proof public JWK | Proof signature | Expected |
|---|---|---|---|
| K1 thumbprint | K1 | K1 ký | Tiếp tục kiểm tra claims khác |
| K1 thumbprint | K1 | K2 ký | Reject: signature invalid |
| K1 thumbprint | K2 | K2 ký | Reject: key binding mismatch |
| K2 thumbprint | K2 | K2 ký | Tiếp tục kiểm tra claims khác |
| Thiếu `cnf.jkt` | K1 | K1 ký | Reject nếu endpoint yêu cầu DPoP-bound token |
| `cnf.jkt` sai format | K1 | K1 ký | Reject token/binding theo contract |

Một proof chỉ được xác minh bằng public key trong proof header sau khi kiểm tra cấu trúc và algorithm policy. Kết quả xác minh signature chưa đủ để chấp nhận request.

## 5. Các lớp kiểm tra proof tại Resource Server

Một pipeline dễ hiểu có thể chia thành các bước:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Parse DPoP scheme + proof header"]
    B --> C["Validate access token"]
    C --> D{"Token valid và DPoP-bound?"}
    D -->|Không| X["Reject token"]
    D -->|Có| E["Parse proof JOSE header"]
    E --> F["Check typ, alg, public JWK"]
    F --> G["Verify proof signature"]
    G --> H["Compute JWK thumbprint"]
    H --> I{"Thumbprint == cnf.jkt?"}
    I -->|Không| Y["Reject key binding"]
    I -->|Có| J["Validate htm, htu, ath, iat, nonce"]
    J --> K["Atomic replay check for jti"]
    K --> L{"Proof fresh and unused?"}
    L -->|Không| Z["Reject replay/invalid proof"]
    L -->|Có| M["Continue authorization"]
~~~

Thứ tự chi tiết có thể khác theo implementation, nhưng các điều kiện bảo mật phải được thực thi trước khi business handler chạy.

### 5.1. Kiểm tra access token trước

Resource Server phải xác minh token theo issuer/audience/signature/expiry hoặc introspection contract. Với DPoP-bound token, kiểm tra `cnf.jkt` và xác định token type phù hợp.

Không lấy `cnf.jkt` từ một token chưa được xác minh rồi coi nó là trust anchor. Nếu access token là JWT, decoder phải xác minh chữ ký và claims trước. Nếu opaque, introspection phải trả kết quả active và confirmation data theo contract.

### 5.2. Kiểm tra proof header và signature

- `typ` đúng.
- `alg` nằm trong allowlist asymmetric algorithms.
- `jwk` có key type/curve/size được hỗ trợ.
- Không có private key material.
- Signature verify thành công với public JWK nhúng.
- Không dùng `jku` hoặc URL tùy ý do proof gửi để tải key.
- Thumbprint của public JWK khớp `cnf.jkt`.

### 5.3. Kiểm tra claims gắn với request

- `htm` bằng HTTP method thực tế.
- `htu` bằng URI đích thực tế theo DPoP URI comparison rules.
- `ath` là hash của access token đang gửi.
- `iat` nằm trong freshness window.
- `jti` chưa được dùng.
- `nonce` hợp lệ nếu server đã yêu cầu nonce.

Chỉ sau các bước này request mới được tiếp tục tới URL authorization, method security và business ACL.

## 6. Kiểm thử proof bị thay đổi sau khi ký

### 6.1. Thay payload nhưng giữ signature cũ

Một DPoP proof JWT có compact form:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Nếu thay `htm` từ `GET` thành `DELETE` nhưng giữ signature cũ, signed input thay đổi và chữ ký phải thất bại.

Fixture:

~~~text
1. Tạo proof hợp lệ cho GET /api/orders/42.
2. Decode payload trong test.
3. Đổi htm thành DELETE.
4. Giữ nguyên signature.
5. Gửi proof đã sửa đến verifier.
6. Expected: signature validation failure.
~~~

Không dùng fixture sửa payload rồi ký lại bằng cùng private key để đại diện cho “tampering”. Trường hợp ký lại là một proof mới có chữ ký hợp lệ; nó cần được kiểm tra ở lớp claims, binding và replay.

### 6.2. Thay JOSE header

Tạo các biến thể:

- `typ` đổi từ `dpop+jwt` sang `JWT`.
- `alg` đổi sang `none`.
- `alg` đổi sang thuật toán không được phép.
- `jwk` bị thay bằng public key khác nhưng signature giữ nguyên.
- `jwk` chứa private member.
- Header malformed hoặc thiếu `jwk`.

Expected result: từ chối proof trước khi business authorization. Không để parser fallback sang một JWT validator chung chấp nhận token không phải DPoP.

### 6.3. Sửa signature

Thay một byte trong signature hoặc ký bằng key không tương ứng với JWK trong header. Verifier phải từ chối.

Không cần kiểm tra rằng mọi mutation đều cho cùng một error string; điều cần bảo vệ là **không có mutation nào được chấp nhận** và error category đủ để chẩn đoán mà không lộ credential.

## 7. Kiểm thử proof phát lại (replay)

### 7.1. Vì sao `jti` quan trọng?

DPoP proof được tạo cho một request cụ thể. `jti` cung cấp identifier duy nhất để Resource Server có thể phát hiện proof đã dùng trước đó.

Một test replay cơ bản:

~~~text
Request A:
  token = T
  proof = P (jti = J)
  Expected: accepted

Request B:
  token = T
  proof = P (same compact proof, same jti = J)
  Expected: rejected as replay
~~~

Nếu request thứ hai được chấp nhận, server có thể không lưu replay state, lưu không đúng phạm vi, hoặc cache không chia sẻ giữa các instance.

### 7.2. Replay cache nên có đặc tính gì?

Một replay store thực tế cần:

- **Atomic insert-if-absent:** hai request đồng thời với cùng proof không được cùng thắng.
- **Bounded TTL:** entry tồn tại ít nhất trong khoảng proof còn có thể được chấp nhận, có xét clock skew.
- **Key namespace:** thường kết hợp thumbprint và `jti` để tránh collision giữa clients.
- **Distributed visibility:** nhiều Resource Server instances phải chia sẻ replay state nếu load balancer có thể đưa replay sang node khác.
- **Capacity control:** không cho attacker gửi vô hạn proof IDs làm cạn bộ nhớ.
- **Failure policy:** nếu replay store không sẵn sàng, không âm thầm bỏ qua replay protection khi đây là yêu cầu bảo mật bắt buộc.

Pseudocode:

~~~java
String replayKey = thumbprint + ":" + proofJti;

boolean firstUse = replayStore.putIfAbsent(
    replayKey,
    expiresAt
);

if (!firstUse) {
    throw new InvalidDpopProofException("Proof was already used");
}
~~~

`putIfAbsent` cần là thao tác atomic ở storage. Một chuỗi `get` rồi `put` riêng rẽ có race condition: hai threads cùng thấy key chưa tồn tại rồi cùng chấp nhận.

### 7.3. TTL và clock skew

Giả sử server chấp nhận proof có `iat` không cũ hơn 5 phút và clock skew 30 giây. Replay entry phải sống đủ lâu để proof không thể được chấp nhận lại trong cửa sổ đó.

Không xóa replay entry ngay khi request hoàn tất. Nếu xóa tức thời, attacker có thể gửi lại compact proof trong cùng freshness window.

TTL cụ thể phụ thuộc policy freshness, distributed clock và storage behavior. Ghi giá trị này trong cấu hình/test manifest, không hard-code con số từ ví dụ thành chuẩn chung.

### 7.4. Replay đồng thời trên nhiều nodes

Test concurrency:

~~~text
Node A receives proof P
Node B receives proof P at almost the same time

Expected:
  exactly one request may pass replay check
  the other request must be rejected
~~~

Dùng shared replay store hoặc abstraction có semantics tương đương. Local in-memory map trên từng JVM không đủ nếu hệ thống chạy nhiều instances.

### 7.5. Nonce và replay cache bổ sung nhau

Server có thể yêu cầu nonce qua response header `DPoP-Nonce`. Client đưa nonce vào proof tiếp theo. Nonce làm proof khó được tạo trước hoặc tái sử dụng ngoài server context.

Nonce không nên được coi là thay thế hoàn toàn cho replay detection nếu policy cần chống cùng một proof được gửi lặp. Test cả nonce validation lẫn `jti` replay behavior.

## 8. Kiểm thử proof sai HTTP method (`htm`)

### 8.1. Method phải khớp request thật

Proof:

~~~json
{
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42"
}
~~~

Request thực:

~~~http
DELETE /api/orders/42 HTTP/1.1
~~~

Expected: reject proof vì method mismatch.

### 8.2. Test matrix

| Proof `htm` | HTTP request method | Expected |
|---|---|---|
| GET | GET | Qua bước method check |
| GET | POST | Reject |
| POST | DELETE | Reject |
| PATCH | PATCH | Qua bước method check |
| get | GET | Reject nếu không đúng canonical method representation |
| Missing | GET | Reject |
| Wrong type (number/array) | GET | Reject |

So sánh theo quy tắc DPoP và HTTP method representation, không tự lowercase/uppercase tùy ý để làm proof sai thành hợp lệ. Client nên tạo `htm` theo method thực tế, thường là uppercase token.

### 8.3. Không chỉ test bằng controller method

Proof validation phải diễn ra trước khi controller thực thi. Integration test cần gửi HTTP request thật qua security chain và xác nhận handler không bị gọi khi `htm` sai. Chỉ unit test một helper so sánh strings chưa chứng minh filter được cắm đúng thứ tự.

## 9. Kiểm thử proof sai target URI (`htu`)

### 9.1. DPoP htu không phải URL tùy ý

`htu` mô tả target URI của request. Theo DPoP, URI này không bao gồm query và fragment. Server cần so sánh với URI đích của request theo URI comparison rules phù hợp, bao gồm xử lý scheme, authority, path và normalization.

Ví dụ proof:

~~~json
{
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42"
}
~~~

Các request cần test:

- Host khác.
- Scheme khác (HTTP thay vì HTTPS).
- Port khác.
- Path khác.
- Path encoding khác.
- Path prefix bị reverse proxy thêm/bỏ.
- URI proof dùng internal host trong khi client gọi external host.
- Query string khác nhưng htu theo chuẩn không mang query.
- Fragment xuất hiện trong proof.

### 9.2. Query string không thuộc `htu`

Ví dụ:

~~~text
Actual request:
https://api.example.test/api/orders/42?view=compact

DPoP htu:
https://api.example.test/api/orders/42
~~~

Không từ chối chỉ vì query string khác nếu implementation đang so sánh đúng theo DPoP URI rule. Ngược lại, không được bỏ qua path hoặc host khác vì cho rằng chúng chỉ là proxy detail.

### 9.3. Reverse proxy và forwarded headers

Trong production, client có thể gọi:

~~~text
https://api.example.test/api/orders/42
~~~

nhưng ứng dụng phía sau proxy nhận kết nối:

~~~text
http://orders-service:8080/api/orders/42
~~~

Nếu Resource Server xây htu từ internal scheme/host, proof hợp lệ do client tạo có thể bị từ chối. Nguy hiểm hơn, nếu server tin mọi `Forwarded` hoặc `X-Forwarded-Host` do client gửi, attacker có thể điều khiển URI comparison.

Cần:

- Chỉ tin forwarded headers từ trusted proxy đã cấu hình.
- Proxy phải strip forwarded headers do client gửi trước khi tự gắn header đáng tin.
- Xác định external scheme/host/port/path sau proxy rewrite.
- Test chính xác context path và path prefix.
- Không cho backend có đường truy cập public bypass proxy trust boundary.
- Không tự normalize URI theo cách rộng hơn chuẩn để proof sai vẫn qua.

Test integration nên chạy cùng proxy configuration mà production sử dụng hoặc mô phỏng đầy đủ trusted forwarded headers.

## 10. Kiểm thử `ath` — proof phải gắn với đúng access token

### 10.1. Tính access-token hash

`ath` được tính bằng:

~~~text
BASE64URL(SHA-256(ASCII(access_token)))
~~~

Hash áp dụng lên **giá trị access token thực tế** được gửi cùng request, không có prefix `DPoP ` và không thêm khoảng trắng.

Ví dụ pseudocode:

~~~java
byte[] digest = MessageDigest.getInstance("SHA-256")
    .digest(accessToken.getBytes(StandardCharsets.US_ASCII));

String ath = Base64.getUrlEncoder()
    .withoutPadding()
    .encodeToString(digest);
~~~

Token OAuth access token là chuỗi ASCII theo contract. Không dùng UTF-8 tùy ý nếu implementation contract yêu cầu ASCII representation; không hash chuỗi đã decode JWT payload.

### 10.2. Test mismatch

| Access token trong Authorization | `ath` trong proof | Expected |
|---|---|---|
| Token T1 | Hash(T1) | Qua bước ath |
| Token T1 | Hash(T2) | Reject |
| Token T2 | Hash(T1) | Reject |
| Token T1 | Missing | Reject tại Resource Server |
| Token T1 | Hash bị sửa 1 ký tự | Reject |
| Token T1 | Hash không Base64URL hợp lệ | Reject |

Đây là kiểm thử quan trọng: proof được ký hợp lệ và key đúng vẫn phải bị từ chối nếu proof gắn với một access token khác.

### 10.3. Không tái sử dụng proof cho request token mới

Nếu client refresh access token, proof cũ có `ath` của token cũ. Client phải tạo proof mới có hash của access token mới, đồng thời dùng `jti` mới và request claims phù hợp.

## 11. Kiểm thử freshness của `iat` và nonce

### 11.1. `iat` cũ hoặc tương lai

Server thường giới hạn khoảng thời gian proof được chấp nhận. Các case:

- `iat` quá cũ.
- `iat` ở tương lai vượt clock skew.
- `iat` thiếu.
- `iat` sai kiểu dữ liệu.
- Clock server lệch.
- Proof nằm đúng ở ranh giới freshness window.

Dùng fixed clock trong tests để expected result deterministic. Không dùng `Thread.sleep` để chờ proof hết hạn.

### 11.2. Nonce challenge flow

Server có thể trả response yêu cầu nonce:

~~~http
HTTP/1.1 401 Unauthorized
DPoP-Nonce: <NEW-NONCE>
WWW-Authenticate: DPoP error="use_dpop_nonce"
~~~

Client phải tạo **proof mới** chứa nonce server yêu cầu, không sửa một proof đã ký trước đó rồi tái dùng signature.

Test:

| Scenario | Expected |
|---|---|
| Server không yêu cầu nonce | Theo policy nonce hiện tại |
| Server yêu cầu nonce, proof thiếu nonce | Challenge use_dpop_nonce |
| Proof chứa nonce mới nhất | Qua nonce check |
| Proof chứa nonce cũ | Reject/challenge theo policy |
| Nonce từ server khác | Reject nếu nonce scoped theo server |
| Client nhận challenge rồi gửi lại nguyên proof cũ | Không chấp nhận; proof mới phải có fresh jti/iat và nonce |
| Nonce header bị proxy strip | Integration test phát hiện client không thể hoàn tất flow |

Nonce nên có entropy phù hợp, được gắn vào đúng server context và không chứa thông tin nhạy cảm. Test nonce rotation/expiry theo policy thực tế.

## 12. Kiểm thử sai khóa và key rotation

### 12.1. Wrong proof key so với `cnf.jkt`

Đây là test cốt lõi:

~~~text
Access token:
  cnf.jkt = thumbprint(K1)

DPoP proof:
  jwk = public(K2)
  signature = valid under private(K2)

Expected:
  signature check passes
  key-binding check fails
  request rejected
~~~

Không viết test chỉ dùng token `cnf.jkt` sai format; cần trường hợp hai key hợp lệ nhưng không tương ứng để chứng minh so sánh binding thật sự hoạt động.

### 12.2. Key rotation ở client

Giả sử client đang dùng K1 và có token T1 bound với K1. Khi client rotate sang K2:

- T1 + proof K1: có thể tiếp tục hợp lệ trong thời hạn T1 và policy.
- T1 + proof K2: phải bị từ chối vì `cnf.jkt` của T1 vẫn là K1.
- Access token mới T2 bound với K2 + proof K2: hợp lệ.
- T2 + proof K1: phải bị từ chối.

Không tự đổi `cnf.jkt` của token cũ ở Resource Server để “hỗ trợ rotation”. Binding là thuộc tính của token đã được AS cấp. Client cần lấy token mới gắn với key mới theo flow phù hợp.

### 12.3. Test key pair cũ và mới

| Access token | Proof key | Expected |
|---|---|---|
| T1 bound K1 | K1 | Accept nếu token/proof còn hạn |
| T1 bound K1 | K2 | Reject |
| T2 bound K2 | K2 | Accept |
| T2 bound K2 | K1 | Reject |
| T1 revoked/expired | K1 | Reject token |
| T1 active nhưng K1 đã bị client xóa | K2 | Reject; client cần token mới |

### 12.4. Phân biệt rotation của issuer và rotation của DPoP client key

Có hai loại key khác nhau:

- **Issuer signing key:** AS dùng ký access token JWT; Resource Server lấy public key từ JWKS.
- **DPoP client key:** client dùng private key ký proof; access token chứa `cnf.jkt` của public key client.

Rotate issuer signing key không tự đổi DPoP client key. Rotate DPoP client key không tự đổi issuer JWKS. Test suite phải giữ hai trục này riêng.

## 13. Kiểm thử downgrade từ DPoP sang Bearer

Một endpoint yêu cầu DPoP-bound access token không nên chấp nhận token đó qua Bearer scheme như thể token bearer thông thường.

Các trường hợp:

| Request | Token | Expected |
|---|---|---|
| `Authorization: DPoP T` + valid proof | T có `cnf.jkt` | Có thể accept |
| `Authorization: DPoP T`, thiếu proof | DPoP-bound | Reject |
| `Authorization: Bearer T` | Cùng DPoP-bound T | Reject nếu endpoint yêu cầu DPoP |
| `Authorization: DPoP T` + proof key khác | T bound K1, proof K2 | Reject |
| `Authorization: Bearer B` | Bearer token riêng được endpoint cho phép | Chỉ accept nếu contract cho phép |
| Cùng request gửi cả Bearer và DPoP credentials | Credentials xung đột | Reject/handle theo policy tường minh |

Không tự hạ DPoP-bound token thành Bearer chỉ vì proof parser lỗi, header DPoP bị thiếu hoặc nonce flow thất bại. Nếu API thực sự hỗ trợ cả Bearer và DPoP, hãy xác định rõ loại token/endpoint và test từng nhánh độc lập.

## 14. Phân biệt lỗi proof và lỗi access token

Một Resource Server cần phản hồi đủ rõ cho client nhưng không làm lộ thông tin nhạy cảm.

| Tình huống | Lớp lỗi | Kết quả thường gặp |
|---|---|---|
| Access token invalid/expired | Token authentication | 401, invalid_token |
| Proof signature invalid | DPoP proof validation | 401, invalid_dpop_proof |
| `htm`/`htu`/`ath` sai | DPoP proof validation | 401, invalid_dpop_proof |
| Proof replay | DPoP replay protection | Reject proof, thường invalid_dpop_proof |
| `cnf.jkt` không khớp proof key | Token/proof binding | Reject; phân loại theo DPoP/token error contract |
| Server yêu cầu nonce mới | Nonce validation | 401, use_dpop_nonce và `DPoP-Nonce` |
| Token hợp lệ, proof hợp lệ nhưng thiếu scope | Authorization | 403, có thể insufficient_scope |
| Replay store/JWKS dependency lỗi | Infrastructure | Fail closed, ghi nhận dependency failure |
| Endpoint chỉ chấp nhận DPoP nhưng request gửi Bearer | Authentication scheme mismatch | Reject theo endpoint contract |

Không biến lỗi infrastructure thành “proof sai” nếu cần theo dõi availability. Không trả 200 kèm JSON mô tả lỗi 401/403. Với DPoP challenge, giữ response headers cần thiết, đặc biệt `DPoP-Nonce` khi yêu cầu client gửi proof mới.

## 15. Thiết kế test fixtures có thể tái tạo

### 15.1. Một fixture nên khai báo gì?

~~~yaml
fixtureSet:
  id: orders-dpop-proof
  version: 2
  issuer: https://id.example.test/realms/orders
  audience: orders-api
  proofProfile: rfc9449
  clock: 2026-11-15T00:00:00Z

keys:
  clientKey:
    kid: dpop-client-k1
    algorithm: ES256
  wrongKey:
    kid: dpop-client-k2
    algorithm: ES256

scenarios:
  - id: valid-get
    accessTokenBinding: clientKey
    proofKey: clientKey
    method: GET
    uri: https://api.example.test/api/orders/42
    expected: ACCEPT

  - id: wrong-proof-key
    accessTokenBinding: clientKey
    proofKey: wrongKey
    expected: REJECT_BINDING

  - id: replay
    proofKey: clientKey
    reuseSameJti: true
    expectedSecondRequest: REJECT_REPLAY
~~~

Đây là schema ví dụ do dự án tự định nghĩa. Không lưu access token production hoặc private key production trong manifest. Có thể tạo key pair và proof trong test runtime rồi chỉ lưu scenario metadata.

### 15.2. Phân tách expected results

~~~text
tokenValidation: ACCEPT | REJECT
proofSignature: ACCEPT | REJECT
keyBinding: MATCH | MISMATCH
requestBinding: MATCH | MISMATCH
freshness: FRESH | STALE | FUTURE
nonce: VALID | MISSING | INVALID | NOT_REQUIRED
replay: FIRST_USE | REPLAY
authorization: ALLOW | DENY
httpExpected: 200 | 400 | 401 | 403
errorExpected: none | invalid_token | invalid_dpop_proof | use_dpop_nonce
~~~

Một test có thể chứng minh token valid, proof signature valid, nhưng key binding mismatch. Kết quả đó hữu ích hơn một fixture chỉ ghi chung `expected: REJECT`.

### 15.3. Dùng key test, không dùng credential thật

- Sinh EC P-256 hoặc loại key mà implementation cho phép bằng test-only key factory.
- Public JWK được dùng trong proof.
- Private key chỉ ở test process.
- Access token fixture có `cnf.jkt` tính từ public JWK.
- Dùng fixed clock và deterministic IDs khi cần tái lập.
- Không log compact proof/access token trong CI.

## 16. Test factory và helper cho DPoP proof

DPoP proof factory nên nhận request context và access token thay vì hard-code claims.

Pseudocode:

~~~java
DpopProof createProof(
        PrivateKey privateKey,
        PublicJwk publicJwk,
        String accessToken,
        String httpMethod,
        URI targetUri,
        Instant issuedAt,
        String jti,
        String nonce) {

    String ath = base64UrlSha256(accessToken);

    return signDpopJwt(
        header("dpop+jwt", allowedAlgorithm, publicJwk),
        claims(
            "jti", jti,
            "htm", httpMethod,
            "htu", dpopTargetUri(targetUri),
            "iat", issuedAt,
            "ath", ath,
            "nonce", nonce
        ),
        privateKey
    );
}
~~~

Đây là pseudocode mô tả trách nhiệm, không phải một Spring Security API. `signDpopJwt` và `dpopTargetUri` cần tuân JOSE/RFC 9449 rules.

### 16.1. Helper phải dễ tạo proof sai có chủ đích

Không chỉ có một method `validProof()`. Test suite cần tạo được:

- `tamperPayloadAfterSigning`.
- `signWithDifferentKey`.
- `useWrongHtm`.
- `useWrongHtu`.
- `useWrongAth`.
- `useOldIat`.
- `useFutureIat`.
- `omitNonce`.
- `useWrongNonce`.
- `reuseJti`.
- `includePrivateJwkMember`.
- `useUnsupportedAlgorithm`.

Các helper có thể chia thành factory hợp lệ và mutation builders. Mutation phải có tên rõ để người đọc hiểu test đang chứng minh điều gì.

### 16.2. Đừng vô tình làm fixture invalid ở nhiều lớp

Ví dụ test “wrong htm” phải có:

- Signature hợp lệ.
- Proof key khớp `cnf.jkt`.
- `htu` đúng.
- `ath` đúng.
- `iat` hợp lệ.
- `jti` chưa từng dùng.
- Nonce đúng nếu bắt buộc.

Chỉ `htm` sai. Nếu fixture còn sai signature, test sẽ pass vì decoder reject sớm và không hề kiểm tra method binding.

Đây là nguyên tắc quan trọng của negative tests: **mỗi scenario thay đổi một điều kiện chính**, giữ các điều kiện còn lại hợp lệ.

## 17. Kiểm thử với Spring Security và Web stack

### 17.1. Tách proof validator khỏi controller

DPoP proof validation thuộc security/authentication boundary. Nên tích hợp vào Resource Server authentication pipeline hoặc một component bảo mật được gọi trước authorization/handler.

Không đặt logic xác minh proof rải rác trong từng controller. Nếu một endpoint quên gọi helper, API sẽ có đường bypass.

### 17.2. Không giả định mọi Spring Security version có cùng DPoP API

Các abstraction OAuth2 Resource Server chuẩn của Spring Security xử lý access token JWT/opaque. DPoP proof validation và replay protection cần được triển khai qua **cơ chế DPoP được hỗ trợ trong version đang dùng** hoặc extension point phù hợp của ứng dụng.

Trước khi chọn implementation, kiểm tra version-matched Spring Security reference/API. Không tự tạo tên class như `DpopAuthenticationFilter` rồi giả định framework có sẵn. Nếu phải tự tích hợp, cần một design thống nhất cho:

- Resolve access token và token type.
- Verify token và `cnf.jkt`.
- Parse/verify proof JWT.
- Validate request binding/freshness/nonce.
- Atomic replay check.
- Chuyển lỗi thành đúng HTTP challenge.
- Đặt filter đúng thứ tự trước authorization và handler.

### 17.3. Servlet và WebFlux khác nhau

| Servlet | WebFlux |
|---|---|
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| Servlet `Filter` | Reactive `WebFilter` |
| `HttpServletRequest` | `ServerWebExchange` |
| `OncePerRequestFilter` pattern phổ biến | Reactive filter composition |
| Blocking replay store có thể cần quản lý thread | Replay store phải có reactive I/O hoặc boundary không block event loop |

Không copy Servlet filter vào WebFlux app. Với WebFlux, replay store và proof validator phải giữ reactive/non-blocking behavior; không gọi `block()` trong request pipeline.

### 17.4. Vị trí xử lý

Mô hình khái quát:

~~~text
HTTP request
  -> Resolve access token
  -> Validate access token / cnf.jkt
  -> Validate DPoP proof
  -> Check replay state
  -> Create authenticated principal
  -> URL authorization / method authorization
  -> Controller
~~~

Một request invalid proof không được tạo authenticated principal rồi chờ controller tự quyết định. Hãy test rằng controller/service không được gọi khi proof bị từ chối.

## 18. Test bằng MockMvc hoặc WebTestClient

### 18.1. Unit tests cho proof validator

Unit tests nên gọi validator với:

- Access token đã được xác minh hoặc token principal test.
- Confirmation thumbprint.
- Compact proof.
- HTTP method/URI context.
- Clock.
- Nonce policy.
- Replay store.

Các tests này chạy nhanh và xác định chính xác lớp nào reject.

### 18.2. Integration tests qua security chain

Với Servlet, dùng `MockMvc`; với WebFlux, dùng `WebTestClient`. Gửi request thực qua security chain với `Authorization: DPoP ...` và `DPoP` header thật được tạo bằng test private key.

Không chỉ dùng helper như `jwt()` hoặc mock `Authentication` rồi kết luận DPoP đã được kiểm tra. Những helper đó có thể bypass proof parser, signature verification và replay store.

### 18.3. Ma trận integration

| Test | Token | Proof | Expected |
|---|---|---|---|
| Valid request | DPoP-bound | Đúng key, htm, htu, ath | Handler được gọi |
| Missing proof | DPoP-bound | Không có `DPoP` header | Reject |
| Tampered payload | DPoP-bound | Signature invalid | Reject |
| Wrong key | `cnf.jkt`=K1 | Proof signed by K2, JWK K2 | Reject binding |
| Wrong method | DPoP-bound | `htm` khác request | Reject |
| Wrong URI | DPoP-bound | `htu` khác target | Reject |
| Wrong token hash | DPoP-bound | `ath` của token khác | Reject |
| Replay | DPoP-bound | Gửi lại cùng proof | Request thứ hai reject |
| Stale proof | DPoP-bound | `iat` quá cũ | Reject |
| Future proof | DPoP-bound | `iat` vượt skew | Reject |
| Nonce required | DPoP-bound | Thiếu nonce | Challenge |
| Nonce retry | DPoP-bound | Proof mới với nonce hợp lệ | Qua nonce check |
| Bearer downgrade | DPoP-bound | Gửi scheme Bearer | Reject theo contract |
| Insufficient scope | DPoP-bound | Proof hợp lệ, scope thiếu | 403 |
| Wrong tenant | DPoP-bound | Proof hợp lệ, tenant ACL sai | Deny domain authorization |

### 18.4. Kiểm tra side effects

Với mọi proof-invalid cases, assert thêm:

- Controller/handler không được gọi.
- Business service không thực hiện write.
- Replay store ghi nhận đúng một lần sử dụng nếu proof hợp lệ.
- Không có access token hoặc private key trong logs.
- Response không lộ raw proof/payload.
- HTTP status/challenge phù hợp.

## 19. Distributed replay protection và resilience

### 19.1. In-memory cache không đủ cho cluster

Giả sử load balancer phân phối:

~~~text
Request 1 -> Node A -> local cache empty -> accept
Replay    -> Node B -> local cache empty -> accept
~~~

Cả hai node có thể chấp nhận cùng proof. Nếu hệ thống yêu cầu replay prevention trên toàn cluster, cần shared store hoặc một cơ chế phân phối có atomic uniqueness semantics.

### 19.2. Test race condition

~~~text
submit(P) concurrently to node-A and node-B

assert acceptedCount == 1
assert rejectedReplayCount == 1
~~~

Không chỉ test tuần tự trên cùng instance. Một local synchronized map không chứng minh distributed behavior.

### 19.3. Replay store unavailable

Nếu replay protection là yêu cầu bắt buộc, khi store lỗi:

- Không silently bypass replay check.
- Không chấp nhận request chỉ vì proof signature hợp lệ.
- Trả lỗi theo availability/error policy đã xác định.
- Ghi metric riêng cho replay store failure.
- Có timeout và capacity controls.

Test timeout, connection refused, store response lỗi và recovery. Không biến lỗi Redis/database thành invalid_dpop_proof nếu nguyên nhân thực tế là dependency unavailable.

### 19.4. TTL và storage abuse

Attacker có thể gửi nhiều proof với `jti` ngẫu nhiên. Replay cache cần:

- TTL hữu hạn theo freshness window.
- Giới hạn kích thước/rate theo client và network policy.
- Key length/claim length limits.
- Reject malformed IDs.
- Monitoring cache size/eviction.
- Không dùng TTL dài vô hạn.

Nếu eviction xóa entry trước khi proof hết freshness, replay có thể được chấp nhận lại. Test eviction behavior và sizing assumptions.

## 20. Kiểm thử URI và proxy trong môi trường thực

DPoP `htu` là nơi integration dễ sai khi ứng dụng đứng sau reverse proxy hoặc API gateway.

### 20.1. External URI phải được xác định nhất quán

Một test matrix proxy có thể gồm:

| Client thấy | Backend thấy | Expected htu comparison |
|---|---|---|
| HTTPS host public | HTTP host nội bộ | Dùng external URI đã được xác định từ trusted proxy config |
| HTTPS + port 443 | HTTPS không ghi port | Theo URI normalization rules |
| Public prefix `/gateway/orders` | Backend path `/orders` | Match theo external target URI mà client ký |
| Host header bị client giả | Proxy đã strip/replace | Không dùng giá trị giả |
| Forwarded proto từ untrusted client | Không được tin | Reject hoặc không dùng header đó |
| Query khác | Cùng target path | Query không thuộc `htu` |
| Path khác | Host giống nhau | Reject |

### 20.2. Trust forwarded headers có điều kiện

Không bật chế độ tin mọi forwarded header từ mọi nguồn. Chỉ chấp nhận headers từ ingress/proxy tin cậy và bảo đảm ingress loại bỏ headers do client gửi trước khi thêm giá trị của mình.

Test qua chính proxy configuration hoặc một integration harness tương đương. Nếu test chỉ gọi trực tiếp embedded server, có thể bỏ sót lỗi production do path rewriting.

### 20.3. Canonicalization phải nhất quán

Client và Resource Server cần cùng hiểu target URI. Không tự decode/re-encode path nhiều lần hoặc thay `%2F` thành `/` theo cách làm hai URI khác nhau trở thành một. Dùng URI parsing/comparison theo chuẩn và kiểm thử encoded path, default port, scheme, host và context path.

## 21. Quan sát và phân loại lỗi

Metrics/logs nên phân biệt:

| Category | Ví dụ |
|---|---|
| `token_invalid` | Signature/issuer/audience/expiry access token sai |
| `proof_malformed` | Compact JWT/header/claim malformed |
| `proof_signature_invalid` | Signature không verify |
| `proof_key_mismatch` | JWK thumbprint không khớp `cnf.jkt` |
| `proof_method_mismatch` | `htm` sai |
| `proof_uri_mismatch` | `htu` sai |
| `proof_ath_mismatch` | Hash token sai |
| `proof_stale` | `iat` quá cũ |
| `proof_nonce_invalid` | Nonce thiếu/sai/cũ |
| `proof_replay` | `jti` đã dùng |
| `replay_store_unavailable` | Replay backend lỗi |
| `authorization_denied` | Thiếu scope/role/ACL |

Log an toàn:

~~~text
event=dpop_validation_failed
category=proof_key_mismatch
issuer_alias=orders-sandbox
request_id=req-1024
client_key_thumbprint_prefix=8b31...
~~~

Không log compact access token, compact proof JWT, private JWK hoặc raw nonce nếu nonce được coi là secret ngắn hạn. Không đưa full `jti` hoặc subject vào metrics labels không giới hạn; chọn cách redaction/aggregation phù hợp.

## 22. Quy trình rollout và kiểm thử key-bound tokens

Khi triển khai DPoP hoặc thay đổi policy:

1. Xác định issuer/token profile có hỗ trợ DPoP và cách AS phát hành `cnf.jkt`.
2. Xác định client key algorithm và public JWK types được cho phép.
3. Triển khai proof validation, request binding, nonce và replay store.
4. Chạy unit tests với valid/invalid fixtures.
5. Chạy integration tests qua security chain và reverse proxy.
6. Kiểm tra client retry behavior: mỗi request/retry tạo proof mới.
7. Thử client key rotation với token cũ/mới.
8. Triển khai sandbox/canary và quan sát error categories.
9. Chuyển endpoint sang yêu cầu DPoP theo policy đã công bố.
10. Thu hồi hoặc để hết hạn các token/key cũ theo migration plan.

Không bật DPoP ở Resource Server trước khi AS và clients cùng hỗ trợ token binding/proof contract. Cũng không chấp nhận token DPoP-bound qua Bearer trong giai đoạn chuyển tiếp nếu điều đó phá mục tiêu sender constraint.

## 23. Checklist kiểm thử

- [ ] Access token được xác minh trước khi tin `cnf.jkt`.
- [ ] Token có confirmation thumbprint phù hợp.
- [ ] Proof header `typ` đúng `dpop+jwt`.
- [ ] Chỉ asymmetric algorithms được allowlist.
- [ ] JWK chỉ chứa public key members.
- [ ] Proof signature được xác minh.
- [ ] JWK thumbprint được tính đúng theo RFC 7638.
- [ ] Wrong key signature và key-binding mismatch có test riêng.
- [ ] `htm` phải khớp HTTP method.
- [ ] `htu` phải khớp target URI theo DPoP rules.
- [ ] Query/fragment được xử lý đúng quy tắc `htu`.
- [ ] `ath` được tính từ access token thực tế.
- [ ] `iat` có freshness window và clock skew test.
- [ ] `jti` replay bị từ chối.
- [ ] Replay check atomic và hoạt động qua nhiều nodes.
- [ ] Nonce challenge, retry, expiry và stale nonce được test.
- [ ] Token DPoP-bound không downgrade sang Bearer.
- [ ] Client retry tạo proof mới, jti mới.
- [ ] Key rotation cũ/mới được test độc lập với issuer signing key rotation.
- [ ] Reverse proxy/forwarded headers được trust đúng và test qua ingress.
- [ ] Proof invalid không gọi controller hoặc gây business side effects.
- [ ] Replay store outage không làm mất replay protection.
- [ ] Response errors phân biệt token, proof, nonce và authorization failures.
- [ ] Logs không chứa access token, proof JWT hoặc private key.

## 24. Tổng kết

DPoP proof không chỉ là một JWT có chữ ký. Nó là **bằng chứng cho một request cụ thể**, được ký bằng private key đã ràng buộc với access token. Vì thế Resource Server phải xác minh đồng thời:

1. **Access token:** issuer, audience, signature/active state, thời hạn và `cnf.jkt`.
2. **Proof signature:** header type, algorithm, public JWK và chữ ký.
3. **Key binding:** thumbprint của JWK khớp `cnf.jkt`.
4. **Request binding:** `htm`, `htu` và `ath` đúng request/token.
5. **Freshness/replay:** `iat`, `jti` và nonce theo policy.
6. **Authorization:** scope, tenant, owner và ACL sau khi authentication hoàn tất.

Các test quan trọng nhất phải cô lập từng điều kiện: proof sửa nhưng signature cũ; proof ký bằng key khác; proof đúng chữ ký nhưng sai `cnf.jkt`; cùng proof gửi hai lần; method/URI/token hash sai; nonce thiếu; request qua proxy; và token DPoP-bound bị gửi bằng Bearer scheme.

Khi các test này chạy deterministic trong CI và được kiểm chứng qua security chain thực tế, hệ thống có thể phát hiện lỗi proof validation, replay handling, key rotation và request binding trước khi chúng ảnh hưởng dữ liệu production.

### Tài liệu tham khảo

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)

