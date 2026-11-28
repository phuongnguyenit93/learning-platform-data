# Đọc authorization header

## 1. Vì sao đọc Authorization header là bước bảo mật quan trọng của custom authentication filter?

Khi client gọi API dùng **HMAC với shared secret**, request thường mang một **chỉ dẫn xác thực**: client đang sử dụng credential nào, phiên bản hợp đồng ký nào, timestamp/nonce nào và giá trị HMAC cuối cùng. Một vị trí quen thuộc để mang các thông tin đó là HTTP **`Authorization` header**.

Ví dụ học tập:

```http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Idempotency-Key: pay-903
Authorization: HMAC version="1", clientId="merchant-42", keyId="key-2026-b", timestamp="1790000020", nonce="QEFCQ0RFRkdISUpLTE1OTw", signature="BIDLsx2PdbdEYe4oQWGE95T1PDrFhPsKSYNLOS5PJUo"

{"paymentId":"p-903","amount":125000,"currency":"VND"}
```

Để request này trở thành một **verified principal**, server không thể chỉ gọi `request.getHeader("Authorization")` rồi tách chuỗi theo dấu phẩy. Phải xác định chính xác **một header**, parse theo một **hợp đồng xác thực có phiên bản**, ràng buộc các selectors `clientId/keyId` với HMAC input, chọn đúng shared secret, xác minh **raw HMAC bytes**, kiểm tra thời gian/nonce và chỉ sau đó đưa danh tính vào Spring Security `SecurityContext`.

Sai ở giai đoạn **đọc header** có thể gây:

- Lẫn **HMAC, Basic và Bearer** khi API hỗ trợ nhiều kiểu xác thực.
- **Header smuggling/ambiguity** khi có nhiều trường `Authorization`, gateway và application chọn giá trị khác nhau.
- Nhận sai key ID/client ID do parsing mơ hồ, dấu phẩy nằm trong quoted string hoặc whitespace khác nhau.
- Không ký `version/clientId/keyId` nên attacker có thể tác động đến credential selection.
- Trả authentication success chỉ dựa vào header syntactically valid thay vì xác minh MAC.
- Gán `SecurityContext` quá sớm, bỏ qua bước chống replay hoặc bỏ qua authorization trên resource.
- Lộ raw signature, access key IDs hoặc thông tin nhạy cảm khi log toàn bộ Authorization header.

Bài **Đọc authorization header** thuộc chương **Custom authentication filter** trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Phạm vi module là xác thực HTTP request với HMAC shared secret và canonical method/URI/headers/body, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và tách biệt authentication với authorization. Vì vậy phần đọc header sẽ được nối với **toàn bộ pipeline HTTP HMAC**, nhưng trọng tâm vẫn là **API contract, parsing và vị trí tích hợp Spring Security**.

Bạn cần đạt được:

- Phân biệt tên field **`Authorization`** với **authentication scheme** bên trong giá trị của field.
- Biết vì sao `getHeader()` không đủ để bảo vệ trước duplicated headers.
- Đọc và validate một HMAC authorization value bằng **strict grammar**; không dùng `split(",")`, `contains("HMAC")` hoặc parser tolerant ngoài hợp đồng.
- Thiết kế canonical request **ký version, clientId, keyId, timestamp, nonce** và body semantics nhưng **không tự ký output signature**.
- Tạo Java 17 parser/filter dùng Spring Security Servlet/`OncePerRequestFilter`, chỉ cấp principal khi verifier trả thành công.
- Xử lý lỗi **401 vs 403 vs 503**, các scheme khác, proxy rewrite, nonce và key rotation.
- Kiểm tra với golden SHA-256/HMAC-SHA256 bytes độc lập, negative cases và integration tests.

**Tư tưởng nền:** Header chỉ chứa một **lời khai chưa đáng tin**. Parser làm rõ cú pháp, HMAC verifier xác minh lời khai, anti-replay giới hạn một lần sử dụng, và authorization quyết định hành động nào được phép.

## 2. `Authorization` trong HTTP: tên field, scheme và credentials

### 2.1. Đừng đồng nhất tên header với phương thức xác thực

Các ví dụ có cùng **tên header** nhưng **ngữ nghĩa khác**:

```http
Authorization: Basic dXNlcjpwYXNz
Authorization: Bearer eyJhbGciOi...
Authorization: HMAC version="1", clientId="merchant-42", keyId="key-2026-b", timestamp="1790000020", nonce="QEFCQ0RFRkdISUpLTE1OTw", signature="BIDLsx2PdbdEYe4oQWGE95T1PDrFhPsKSYNLOS5PJUo"
```

Trong HTTP authentication framework, **auth-scheme** (ví dụ `Basic`, `Bearer`) xác định cách diễn giải credentials. Scheme names có tính **case-insensitive**, còn format tham số và case của values phụ thuộc **hợp đồng của scheme**. HMAC scheme trong bài là một **giao thức tùy chỉnh để học**, **không** phải cú pháp chuẩn mặc định được tất cả gateway hay Spring Security hỗ trợ tự động.

Không được:

```java
// SAI: chỉ tìm substring "HMAC" trong mọi header value.
if (authorization.contains("HMAC")) {
    securityContext.setAuthenticated(true);
}
```

Cũng không được dùng chung một parser cho Bearer/JWT và HMAC rồi đoán nghĩa của `signature`. Một endpoint chỉ hỗ trợ HMAC phải **reject scheme không được hỗ trợ**; nếu có nhiều cơ chế, cấu hình **SecurityFilterChain/request matcher rõ ràng**, không silent downgrade từ Bearer sang HMAC hoặc ngược lại.

### 2.2. Một field `Authorization` không có nghĩa tự động đáng tin

```text
HTTP request
  ├─ Method + raw URI + body            (client/proxy input)
  ├─ Authorization: HMAC ...            (client input)
  │    ├─ version       (untrusted)
  │    ├─ clientId      (untrusted selector)
  │    ├─ keyId         (untrusted selector)
  │    ├─ timestamp     (untrusted, later signed)
  │    ├─ nonce         (untrusted, later signed)
  │    └─ signature     (untrusted tag to compare)
  └─ X-Idempotency-Key                   (business identifier to sign)

Parser → Credentials(untrusted)
Lookup → Secret and owner from trusted store
MAC + time + atomic nonce → VerifiedPrincipal
Authorization → permit/deny resource action
```

Đặc biệt, `clientId` và `keyId` **không phải bằng chứng** về danh tính. Chúng giúp server lookup đúng credential, nhưng verified owner phải đến từ **trusted credential record** sau khi MAC và freshness hợp lệ.

### 2.3. Header names case-insensitive; values theo hợp đồng riêng

Các HTTP header names tương đương:

```http
Authorization: HMAC ...
authorization: HMAC ...
AUTHORIZATION: HMAC ...
```

Server phải đọc field `Authorization` **case-insensitive**, phù hợp HTTP/1.1 và HTTP/2/3. Nhưng không được tùy ý lowercase toàn bộ value:

```text
HMAC vs hmac            : scheme names case-insensitive
clientId vs clientid    : parameter names theo grammar riêng của V1
merchant-42 vs Merchant-42 : client ID case-sensitive theo V1
key-2026-b vs KEY-2026-B : KeyId case-sensitive theo V1
Base64url tag             : case-sensitive bytes/text
```

Nếu proxy đổi case của `clientId`/`keyId` hoặc Base64url signature, server có thể chọn nhầm key hoặc MAC mismatch. Lowercase **header name** hợp lệ không đồng nghĩa lowercase **header value** cũng hợp lệ.

### 2.4. Header là input bí mật/nhạy cảm về vận hành

Authorization header có thể chứa Bearer token hoặc MAC signature; trong HMAC scheme này nó **không chứa raw shared secret**, nhưng raw tag và metadata có thể nhạy cảm cho logging, troubleshooting, traffic correlation hoặc replay within freshness window. **Không log toàn bộ Authorization header**, không gửi nó về client trong error, không thêm làm label metric, không ghi vào access logs/trace baggage hoặc exception `toString()`.

Nếu client gửi raw secret thay vì signature trong Authorization, đó là **thiết kế giao thức khác và nguy hiểm**; HMAC header của bài chỉ mang selector/nonce/timestamp/tag, không mang secret.

## 3. Threat model khi đọc `Authorization`

### 3.1. Duplicated headers: `getHeader()` có thể chọn một giá trị

Request độc hại:

```http
Authorization: HMAC version="1", clientId="merchant-42", keyId="key-2026-a", timestamp="1790000020", nonce="QEFCQ0RFRkdISUpLTE1OTw", signature="6fkOmJSyLX1T-nTZn51okmf5AM-ihQ7uX8V-vCATqWY"
authorization: Bearer attacker-controlled-value
```

Một gateway có thể lấy **giá trị đầu**, một backend dùng **giá trị cuối**, hoặc reverse proxy coalesce thành một field có dấu phẩy. Kết quả: gateway/backend có thể **xác thực các credential khác nhau cho cùng một request**.

Ở Servlet, `request.getHeader("Authorization")` thường trả **một** giá trị nếu có nhiều occurrences; nó không tự bảo đảm field xuất hiện **đúng một lần**. Dùng `request.getHeaders("Authorization")` để kiểm tra số giá trị **còn nhìn thấy** là một bước quan trọng.

**Giới hạn bắt buộc:** nếu proxy/gateway **đã gộp, bỏ bớt hoặc normalize** duplicated headers trước khi Servlet nhận request, application không thể khôi phục số occurrences ban đầu. Vì vậy **ingress phải reject duplicates trước coalescing**; filter lại kiểm tra các values còn hiện diện và strict grammar, tạo defense in depth.

### 3.2. Không split theo dấu phẩy một cách tổng quát

Authorization custom scheme có thể dùng comma-separated auth parameters. Tuy nhiên **quoted strings theo HTTP** có thể có dấu phẩy hoặc escape trong những biến thể giao thức cho phép:

```http
Authorization: Something name="alpha,beta", token="..."
```

Đoạn code:

```java
// SAI cho một generic Authorization auth-param parser.
String[] parts = rawAuthorization.split(",");
```

không hiểu quoted strings/escaping, không phân biệt multiple credentials, và dễ xử lý duplicate param bằng cách **ghi đè vào Map**. Phương án an toàn cho bài này là **định nghĩa V1 grammar rất hẹp**: fixed parameter order, six double-quoted ASCII fields, **không cho comma/quote/escape trong values**, fixed separators. Một regular expression anchored có thể parse **đúng contract hẹp này**, nhưng **không được** tuyên bố đó là parser tổng quát theo tất cả auth-param của HTTP.

Nếu sản phẩm muốn hỗ trợ thứ tự tham số tùy ý, BWS/OWS và quoted-pairs đầy đủ, phải viết hoặc dùng **state-machine parser đã được review**, reject duplicates/unknown params và có test grammar độc lập. **Đừng nới grammar im lặng** bằng `trim()`, `split(",")` hoặc lấy “first valid parameter”.

### 3.3. CRLF, obs-fold, Unicode và whitespace

Các inputs cần được reject theo hợp đồng lab:

- Header value chứa `\r` hoặc `\n`, kể cả attempt header injection; HTTP server/gateway nên chặn ở tầng parse.
- Tabs, nhiều spaces bất thường, OWS ở vị trí không được grammar định nghĩa, tham số thiếu quote.
- Unicode confusables, zero-width spaces hoặc full-width punctuation trong IDs/parameter names.
- Không phân biệt `clientId` với `clientid` nếu contract đã quy định spelling chính xác.
- Duplicate/unknown parameters; không được cho attacker gửi `keyId="A", keyId="B"` rồi chọn một.
- Giá trị quá dài gây regex CPU/heap stress, event log/metrics phình to.
- Base64url không canonical hoặc có padding `=`, ký tự `+`, `/` theo V1 no-padding policy.

**Cần phân biệt tầng:** servlet container có thể remove OWS ở đầu/cuối header value theo HTTP parsing rules; parser chỉ validate representation **sau container**, nên phải nêu rõ ingress normalizations được phép và test trực tiếp raw-wire nếu cần chống ambiguity.

### 3.4. Không sửa lỗi protocol bằng parsing “tolerant”

Một hệ thống có thể muốn nhận cùng lúc:

```http
Authorization: HMAC keyId=abc,signature=xyz
Authorization: HMAC keyId="abc", signature="xyz"
Authorization: hmac Signature="xyz", KeyId="abc"
```

Nếu tất cả được chấp nhận không có version/grammar tường minh, signer/verifier ở các ngôn ngữ/gateways rất dễ khác nhau. **Hợp đồng chính xác, có version, dễ kiểm thử** tốt hơn “đoán” cách client gửi. Khi cần migration, dùng protocol version và capability negotiation được thiết kế, không tự thử lần lượt parser cũ/mới khi HMAC fail.

## 4. Hợp đồng `Authorization: HMAC ...` của bài

### 4.1. Grammar V1 nghiêm ngặt, có chủ đích

Bài định nghĩa **`HTTP-HMAC-AUTHZ-HDR-V1`** (giao thức minh họa). **Một** header `Authorization` hợp lệ có cấu trúc **chính xác**:

```text
HMAC version="1", clientId="<id>", keyId="<id>", timestamp="<epochSeconds>", nonce="<base64url22>", signature="<base64url43>"
```

Ví dụ:

```http
Authorization: HMAC version="1", clientId="merchant-42", keyId="key-2026-b", timestamp="1790000020", nonce="QEFCQ0RFRkdISUpLTE1OTw", signature="BIDLsx2PdbdEYe4oQWGE95T1PDrFhPsKSYNLOS5PJUo"
```

Cách diễn giải:

| Parameter | Cú pháp | Độ tin cậy / ý nghĩa |
| --- | --- | --- |
| `version` | Literal `"1"` | Chọn hợp đồng canonicalization, **được MAC-bind** |
| `clientId` | ASCII `[A-Za-z0-9._-]{1,64}` | Untrusted selector, owner phải được verify |
| `keyId` | ASCII `[A-Za-z0-9._-]{1,64}` | Untrusted credential version selector |
| `timestamp` | Canonical positive epoch seconds, ≤19 chữ số và fit signed long | Được ký, so với trusted server clock |
| `nonce` | 16 raw bytes → Base64url **22 ký tự**, no padding | Được ký, dùng atomic anti-replay |
| `signature` | 32 raw HMAC-SHA256 bytes → Base64url **43 ký tự**, no padding | Output HMAC; **không đưa tag vào signed input** |

**Quy ước lexical của V1:** dấu cách đúng **một ASCII SP** giữa scheme và `version`; separators là `", "`; parameter names/param order **cố định** như trên; mọi value nằm giữa dấu quote ASCII `"` và không chứa dấu quote/escape/comma. Scheme token `HMAC` **case-insensitive**, parameter names và values **case-sensitive** theo contract. Không có extension params ở V1.

Đây là giao thức **hạn chế hơn HTTP auth-param tổng quát** nhằm tránh ambiguity trong lab và cho phép golden vectors tái lập. Một client không tuân thủ phải nhận lỗi xác thực; server không tự “sửa” header giúp client.

### 4.2. Canonical input ký những gì?

Trong `HTTP-HMAC-AUTHZ-HDR-V1`, signer ký các field **đã parse từ Authorization**:

```text
auth-version:1
client-id:merchant-42
key-id:key-2026-b
timestamp:1790000020
nonce:QEFCQ0RFRkdISUpLTE1OTw
```

Cùng với method, path/query, external authority đáng tin, Content-Type, `X-Idempotency-Key` và exact body SHA-256.

**Không ký nguyên `Authorization` header gồm signature** vì sẽ tạo phụ thuộc vòng tròn: muốn tính signature cần biết chính signature đó. Thay vào đó, lấy **những parameters được MAC-bind** làm canonical components, tính tag, rồi đặt tag vào `signature` parameter.

Nếu chọn ký raw Authorization header **trừ signature** ở một giao thức khác, phải định nghĩa byte slicing/quote/whitespace/ordering cực kỳ rõ và chống parser disagreement. Bài dùng parsed canonical fields để giảm bề mặt nhầm lẫn.

### 4.3. Hợp đồng của HTTP request ngoài Authorization

```http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Idempotency-Key: pay-903
Authorization: HMAC version="1", clientId="merchant-42", keyId="key-2026-b", timestamp="1790000020", nonce="QEFCQ0RFRkdISUpLTE1OTw", signature="BIDLsx2PdbdEYe4oQWGE95T1PDrFhPsKSYNLOS5PJUo"

{"paymentId":"p-903","amount":125000,"currency":"VND"}
```

V1 giả định:

1. Chỉ route `POST /v1/payments?currency=VND`, JSON UTF-8, fixed external authority `api.example.test`. Đây là **fixture-specific**; production cần hợp đồng cho mọi route/method.
2. `Authorization`, `Content-Type` và `X-Idempotency-Key` là **singleton fields**; reject duplicates ở ingress trước khi coalesce.
3. `X-Idempotency-Key` được MAC-bind bằng value exact ASCII; không tự đổi khi client retry với key mới.
4. Canonical request gồm **13 dòng** nối UTF-8 LF `0x0A`, **không trailing LF**; tên trường canonical lowercase.
5. Body hash SHA-256 tính trên **exact body bytes**, không parse/serialize lại JSON. HTTP adapter phải cung cấp cùng bytes cho verifier và business handler.
6. Trusted authority được xác định bởi ingress/trusted routing, không tin `X-Forwarded-Host` do client tự đặt.
7. Server lookup một credential theo environment/clientId/keyId, check owner/status/algorithm/validity, MAC, freshness, nonce; **không try-all secrets**.
8. Verified principal chỉ được cấp sau đủ các checks; `authorization` theo scope/action/resource vẫn là bước khác.

### 4.4. Trình tự luồng xử lý

```mermaid
flowchart TD
    A["Public HTTP request"] --> B{"Ingress: duplicate Authorization, framing, limits?"}
    B -- "Invalid" --> X["Reject - no business side effects"]
    B -- "Valid" --> C["Servlet getHeaders Authorization: exactly one visible value"]
    C --> D{"Strict HMAC V1 grammar + Base64url canonical?"}
    D -- "Invalid" --> X
    D -- "Valid" --> E["Credential selectors (UNTRUSTED)"]
    E --> F["Lookup exact client+key in trusted environment"]
    F --> G{"Key owner/state/algorithm valid?"}
    G -- "No" --> Y["Generic auth failure"]
    G -- "Yes" --> H["Canonical HMAC of method/URI/headers/body"]
    H --> I{"Raw HMAC constant-time comparison?"}
    I -- "No" --> Y
    I -- "Yes" --> J["Signed timestamp freshness + shared atomic nonce claim"]
    J --> K{"Accepted once?"}
    K -- "No" --> Y
    K -- "Yes" --> L["VerifiedPrincipal -> Spring SecurityContext"]
    L --> M{"Authorization scope/resource?"}
    M -- "No" --> Z["403/404 by policy, no effect"]
    M -- "Yes" --> N["Tenant-scoped idempotency + business transaction"]
```

## 5. Đọc header đúng cách trong Servlet/Spring Security

### 5.1. `getHeader()` vs `getHeaders()`

```java
// Không đủ để kết luận Authorization xuất hiện đúng một lần:
String value = request.getHeader("Authorization");

// Tốt hơn: kiểm tra mọi value còn nhìn thấy tại Servlet boundary.
Enumeration<String> values =
    request.getHeaders("Authorization");
```

Nếu `Enumeration` rỗng: protected endpoint không có credential → **authentication fail**. Nếu có hơn một value: **reject**; không chọn first/last. Nếu một value nhưng có form bị coalesce hoặc không đúng grammar V1: **reject**.

`request.getHeaderNames()` có thể dùng để thống kê/debug field names nhưng không giúp khôi phục raw duplicate occurrences đã bị proxy/container gộp. Chặn ambiguity **phải bắt đầu từ trusted HTTP ingress**.

### 5.2. Đừng dùng `substring(5)` nếu chưa kiểm scheme và spacing

Code sai:

```java
String raw = request.getHeader("Authorization");
String credentials = raw.substring(5).trim();
// "Basic", "Bearer", empty hoặc malformed sẽ bị hiểu nhầm.
```

Một parser đúng phải kiểm tra **toàn bộ** header value, scheme và grammar; không cắt chuỗi dựa trên chiều dài cố định nếu chưa xác minh shape. Các chỗ dùng `trim()`, `replaceAll("\\s+", " ")` hoặc `toLowerCase()` trên **toàn header** trước parse có thể làm thay đổi client/key ID hoặc MAC text.

V1 chọn **strict parse**; nếu header không đúng, trả failure nhất quán. Đừng trả về một object rỗng rồi filter gọi `chain.doFilter()` để request đi tiếp như anonymous trên endpoint bắt buộc HMAC.

### 5.3. Error semantics và `WWW-Authenticate`

| Tình huống | Xử lý ở authentication boundary | Ghi chú |
| --- | --- | --- |
| Không có Authorization ở route bắt buộc HMAC | `401 Unauthorized` | Có thể đưa challenge cho custom scheme |
| Scheme Basic/Bearer trên HMAC-only route | `401` / reject theo policy | Không fallback sang scheme khác |
| Duplicate/malformed Authorization | Reject (thường `401` hoặc `400` theo API contract) | Không tiết lộ chi tiết credential/owner |
| Unknown ClientId/KeyId, revoked key, bad HMAC | `401` generic | Tránh username/key enumeration |
| Timestamp stale/future hoặc nonce replay | `401` generic | Có internal error classification/rate limits |
| Credential/nonce/KMS store unavailable | `503 Service Unavailable` hoặc failure policy rõ, **fail-closed** | Không được cho qua do outage |
| HMAC/nonce đúng nhưng thiếu permission/resource scope | `403 Forbidden` hoặc `404` theo policy | Là **authorization**, không phải bad signature |
| Retry cùng idempotency key nhưng business intent khác | Conflict, thường `409` | Chỉ sau authentication/authorization |

Có thể dùng:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: HMAC realm="api"
Cache-Control: no-store
```

Đây là **challenge minh họa cho custom scheme**, không được lộ secret/nonce expected/HMAC result. Nếu tổ chức không dùng challenge `HMAC` này, cần document API contract cho client; đừng đưa Bearer challenge trên endpoint chỉ có HMAC.

### 5.4. Logging an toàn khi cần chẩn đoán

**Không log:**

```text
request.getHeader("Authorization")    // full credential fields/tag
raw shared secret hoặc secretRef decrypt response
full X-Signature hoặc HMAC tag
body chứa payment/card/bank details
byte[] canonical request chứa dữ liệu nhạy cảm
```

**Có thể log với quyền truy cập kiểm soát:** request/trace ID, parse error code, supported scheme, key version ID đã mask, verified client ID **sau HMAC**, latency của credential lookup, nonce replay count, auth failure reason nội bộ. Claimed client/key ID trước authn phải được validate/rate-limit/cardinality-limit, không dùng làm unbounded metric labels.

## 6. Golden SHA-256/HMAC-SHA256 vectors độc lập

### 6.1. Exact body và canonical request

Exact UTF-8 JSON body fixture (không có LF cuối):

```json
{"paymentId":"p-903","amount":125000,"currency":"VND"}
```

- Body length: **54 bytes**.
- `SHA-256(body)` lowercase hex: `6c4c3379ec4ee31ee77e54f53acff7099c2e5203ecb6c3eea8e5c3a04523a4ee`.
- Test nonce là 16 bytes `40..4f`, encode Base64url no-padding `QEFCQ0RFRkdISUpLTE1OTw`.
- Test timestamp `1790000020` dùng với fixed clock `1790000000` (cách 20 giây trong future tolerance 30s).
- Canonical request gồm **13 dòng / 304 UTF-8 bytes** cho cả key A và B.

Canonical request cho key B:

```text
HTTP-HMAC-AUTHZ-HDR-V1
POST
/v1/payments
currency=VND
authority:api.example.test
content-type:application/json
auth-version:1
client-id:merchant-42
key-id:key-2026-b
timestamp:1790000020
nonce:QEFCQ0RFRkdISUpLTE1OTw
idempotency-key:pay-903
6c4c3379ec4ee31ee77e54f53acff7099c2e5203ecb6c3eea8e5c3a04523a4ee
```

Để tạo input A, thay đúng dòng `key-id:key-2026-b` bằng `key-id:key-2026-a`. Không normalize path/query/body thêm lần nữa.

### 6.2. Hai bộ key và expected tags

Secret test là **test public data**, không dùng làm production credential:

```text
Key A ID = key-2026-a
Key A 32-byte secret hex (00..1f):
000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f

Key B ID = key-2026-b
Key B 32-byte secret hex (20..3f):
202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f
```

| Golden vector | Canonical bytes | Raw HMAC-SHA256 hex | Base64url no-padding (43 chars) |
| --- | --- | --- | --- |
| **A**: `key-2026-a` + secret A | 304 | `e9f90e9894b22d7d53fa74d99f9d689267f900cfa2850eee5fc57ebc2013a966` | `6fkOmJSyLX1T-nTZn51okmf5AM-ihQ7uX8V-vCATqWY` |
| **B**: `key-2026-b` + secret B | 304 | `0480cbb31d8f75b74461ee28416184f794f53c3ac584fb0a49834b392e4f254a` | `BIDLsx2PdbdEYe4oQWGE95T1PDrFhPsKSYNLOS5PJUo` |

Các giá trị đã được tính **độc lập** với implementation Java ở các phần sau. Golden vector ngăn trường hợp cả signer và verifier cùng mắc lỗi (ví dụ **bỏ key ID khỏi canonical input**) nhưng test `sign() == verify()` vẫn vô tình pass.

**Không dùng timestamp/nonce của fixture trong request thật.** Mỗi attempt phải có nonce CSPRNG mới, timestamp hợp lệ và HMAC mới. Một replay store sẽ reject request thứ hai dùng cùng nonce trong cùng verified client namespace, kể cả key A/B đều còn được chấp nhận trong overlap. Để test hai vectors thuần mật mã, không chạy nonce claim hoặc dùng isolated stores **chỉ trong test**.

### 6.3. Vì sao header parse đúng vẫn có thể HMAC sai?

Xét ba tình huống:

```text
1. Authorization có clientId/keyId đúng grammar,
   nhưng body bị đổi amount sau khi ký
   -> MAC mismatch.

2. Authorization có version/keyId đúng grammar,
   nhưng client ký bằng secret A trong khi khai KeyId B
   -> lookup đúng B, MAC mismatch; KHÔNG thử A.

3. Authorization có HMAC tag hợp lệ của key B,
   nhưng timestamp quá cũ hoặc nonce đã claim
   -> authentication reject; không đến business.
```

Do đó parser **không** được trả `Authentication` thành công. Nó chỉ trả **parsed credentials** chưa được xác thực.

## 7. Java 17: `HmacAuthorizationHeaderV1` đọc đúng một header

### 7.1. Chọn strict parser thay vì generic parser

Class này là một **parser cho đúng grammar hẹp ở `4`**, không phải thư viện tổng quát cho mọi HTTP `Authorization`. Nó dùng `Matcher.matches()` với anchors đầu/cuối và **six named parameters fixed-order**. Scheme token được chấp nhận case-insensitive; mọi value giữ nguyên case. String có leading/trailing whitespace, duplicate parameters, missing quotes, extra fields hoặc unsupported version bị reject.

`getHeaders("Authorization")` kiểm tra các values **còn được servlet nhìn thấy**. Proxy đã coalesce/drop một duplicate trước Servlet là trách nhiệm của raw-wire HTTP ingress.

### 7.2. Class `HmacAuthorizationHeaderV1.java`

```java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Base64;
import java.util.Enumeration;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.security.authentication.BadCredentialsException;

public final class HmacAuthorizationHeaderV1 {
    private static final int MAX_HEADER_CHARS = 768;

    // V1 CONTRACT:
    // - Scheme HMAC case-insensitive.
    // - Exactly one ASCII SP after scheme.
    // - Six quoted parameters in this exact order.
    // - Exactly ", " between pairs.
    // - No comma, quote, backslash or whitespace in values.
    // - Exact parameter names, case-sensitive.
    //
    // Not an RFC-general auth-param parser!
    private static final Pattern HEADER_V1 = Pattern.compile(
        "\\A(?i:HMAC) version=\"1\", "
      + "clientId=\"([A-Za-z0-9._-]{1,64})\", "
      + "keyId=\"([A-Za-z0-9._-]{1,64})\", "
      + "timestamp=\"([1-9][0-9]{0,18})\", "
      + "nonce=\"([A-Za-z0-9_-]{22})\", "
      + "signature=\"([A-Za-z0-9_-]{43})\"\\z"
    );

    // PARSED credentials are not an authenticated principal.
    public record Credentials(
        String version,
        String clientId,
        String keyId,
        String signedTimestamp,
        String nonceB64url,
        String signatureB64url
    ) {}

    private HmacAuthorizationHeaderV1() {}

    public static Credentials parseExactlyOne(
            HttpServletRequest request) {
        Enumeration<String> values =
            request.getHeaders("Authorization");

        if (values == null || !values.hasMoreElements()) {
            throw new BadCredentialsException(
                "Invalid HMAC credentials");
        }

        String headerValue = values.nextElement();
        if (values.hasMoreElements()) {
            // NEVER select first/last among duplicate fields.
            throw new BadCredentialsException(
                "Invalid HMAC credentials");
        }
        return parseHeaderValue(headerValue);
    }

    public static Credentials parseHeaderValue(
            String authorizationValue) {
        if (authorizationValue == null
                || authorizationValue.length() > MAX_HEADER_CHARS
                || authorizationValue.indexOf('\r') >= 0
                || authorizationValue.indexOf('\n') >= 0) {
            throw new BadCredentialsException(
                "Invalid HMAC credentials");
        }

        Matcher match = HEADER_V1.matcher(
            authorizationValue);
        if (!match.matches()) {
            throw new BadCredentialsException(
                "Invalid HMAC credentials");
        }

        String timestamp = match.group(3);
        try {
            // Reject values outside signed long range, even
            // if they pass the 19-digit lexical grammar.
            Long.parseLong(timestamp);
        } catch (NumberFormatException overflow) {
            throw new BadCredentialsException(
                "Invalid HMAC credentials", overflow);
        }

        String nonce = match.group(4);
        String tag = match.group(5);
        strictBase64url(nonce, 22, 16);
        strictBase64url(tag, 43, 32);

        return new Credentials(
            "1",
            match.group(1), // clientId
            match.group(2), // keyId
            timestamp,
            nonce,
            tag
        );
    }

    public static byte[] strictBase64url(
            String encoded,
            int expectedTextLength,
            int expectedBytes) {
        if (encoded == null
                || encoded.length() != expectedTextLength
                || !encoded.matches("[A-Za-z0-9_-]+")) {
            throw new BadCredentialsException(
                "Invalid HMAC credentials");
        }

        final byte[] decoded;
        try {
            decoded = Base64.getUrlDecoder().decode(encoded);
        } catch (IllegalArgumentException badBase64) {
            throw new BadCredentialsException(
                "Invalid HMAC credentials", badBase64);
        }

        // Enforce no padding, correct pad bits and unique
        // canonical representation, not merely decodability.
        String canonical = Base64.getUrlEncoder()
            .withoutPadding().encodeToString(decoded);
        if (decoded.length != expectedBytes
                || !canonical.equals(encoded)) {
            throw new BadCredentialsException(
                "Invalid HMAC credentials");
        }

        return decoded;
    }
}
```

### 7.3. Từng hàng trong parser có vai trò gì?

| Thành phần | Mục đích an toàn |
| --- | --- |
| `getHeaders` và kiểm `hasMoreElements` | Không tự chọn một trong nhiều Authorization values còn nhìn thấy |
| `MAX_HEADER_CHARS` | Giới hạn memory/regex work và tránh log input khổng lồ |
| `\\A...\\z` và `matches()` | Toàn bộ value phải khớp contract; không chấp nhận trailing garbage |
| `(?i:HMAC)` | Scheme token case-insensitive **mà không lowercase các values** |
| Fixed parameter order/names | Không có ambiguous first/last/unknown param/escaping |
| `Long.parseLong` sau lexical pattern | Từ chối timestamp overflow |
| Strict Base64url regex + re-encode | Không nhận padding/standard alphabet/noncanonical pad bits |
| `BadCredentialsException` | Parse thất bại là authentication failure, không cấp principal |

**Không dùng parsed credentials để tạo SecurityContext trực tiếp.** Có `clientId="merchant-42"` và `keyId="key-2026-b"` không chứng minh người gửi biết secret tương ứng.

### 7.4. Những input phải bị reject

```http
Authorization: Bearer abc
Authorization: Basic Zm9vOmJhcg==
Authorization: HMAC clientId="merchant-42", keyId="key-2026-b"
Authorization: HMAC version="2", clientId="merchant-42", keyId="key-2026-b", timestamp="1790000020", nonce="QEFCQ0RFRkdISUpLTE1OTw", signature="BIDLsx2PdbdEYe4oQWGE95T1PDrFhPsKSYNLOS5PJUo"
Authorization: HMAC version="1", keyId="key-2026-b", clientId="merchant-42", timestamp="1790000020", nonce="QEFCQ0RFRkdISUpLTE1OTw", signature="BIDLsx2PdbdEYe4oQWGE95T1PDrFhPsKSYNLOS5PJUo"
Authorization: HMAC version="1", clientId="merchant-42", keyId="key-2026-b", keyId="evil", timestamp="1790000020", nonce="QEFCQ0RFRkdISUpLTE1OTw", signature="BIDLsx2PdbdEYe4oQWGE95T1PDrFhPsKSYNLOS5PJUo"
```

Tất cả không khớp grammar V1. Không nên thêm một `catch` rồi thử parser Bearer/legacy HMAC một cách không có version policy. Nếu ứng dụng phải cùng hỗ trợ nhiều schemes, sử dụng **route-specific SecurityFilterChain và AuthenticationProvider riêng**, với migration contract được phê duyệt.

## 8. Java 17: tạo canonical request từ parsed credentials

### 8.1. Vì sao không đọc raw body hai lần?

HMAC có thể ký body digest. Servlet request body thường là **one-shot input stream**: đọc để tính SHA-256 trước rồi gọi controller có thể khiến controller nhận body rỗng. `ContentCachingRequestWrapper` của Spring chỉ cache **khi stream được tiêu thụ**; tạo wrapper không tự pre-read hay bảo đảm replay body nếu filter đã đọc trước chain.

Trong production, cần một trong các phương án được review:

- Bounded body-buffering request wrapper đọc body tối đa size policy và **replay same bytes** cho downstream, kể cả semantics Servlet reader/input stream/async.
- Xác minh HMAC tại trusted ingress có quyền đọc exact body bytes, rồi forward **authenticated internal assertion** và body không bị thay đổi.
- Streaming hash/body verification phù hợp architecture, có cơ chế không xử lý side effect trước khi authentication hoàn tất.

**Không** dùng `request.getInputStream().readAllBytes()` không giới hạn trong filter (DoS), rồi hy vọng controller vẫn đọc được body. Ví dụ lớp dưới đây nhận **exactBodyBytes đã được cung cấp tin cậy**; việc tạo wrapper đúng cho mọi Servlet modes thuộc integration layer.

### 8.2. Class `HmacSignedPartsV1.java`

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class HmacSignedPartsV1 {
    public record Parts(
        String method,
        String rawPath,
        String rawQuery,
        String trustedExternalAuthority,
        String contentType,
        String idempotencyKey,
        byte[] exactBodyBytes
    ) {
        public Parts {
            if (exactBodyBytes == null) {
                throw new IllegalArgumentException(
                    "Missing exact body bytes");
            }
            exactBodyBytes = exactBodyBytes.clone();
        }
        @Override
        public byte[] exactBodyBytes() {
            return exactBodyBytes.clone();
        }
    }

    private HmacSignedPartsV1() {}

    public static byte[] canonicalBytes(
            Parts parts,
            HmacAuthorizationHeaderV1.Credentials auth)
            throws GeneralSecurityException {
        if (parts == null || auth == null
                || !"1".equals(auth.version())
                || !"POST".equals(parts.method())
                || !"/v1/payments".equals(parts.rawPath())
                || !"currency=VND".equals(parts.rawQuery())
                || !"api.example.test".equals(
                    parts.trustedExternalAuthority())
                || !"application/json".equals(parts.contentType())
                || parts.idempotencyKey() == null
                || !parts.idempotencyKey().matches(
                    "[A-Za-z0-9._-]{1,64}")
                || parts.exactBodyBytes().length > 65_536) {
            throw new IllegalArgumentException(
                "Unsupported route or malformed signed parts");
        }

        String bodySha = HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256")
                .digest(parts.exactBodyBytes()));

        String canonical = String.join("\n",
            "HTTP-HMAC-AUTHZ-HDR-V1",
            parts.method(),
            parts.rawPath(),
            parts.rawQuery(),
            "authority:" + parts.trustedExternalAuthority(),
            "content-type:" + parts.contentType(),
            "auth-version:" + auth.version(),
            "client-id:" + auth.clientId(),
            "key-id:" + auth.keyId(),
            "timestamp:" + auth.signedTimestamp(),
            "nonce:" + auth.nonceB64url(),
            "idempotency-key:" + parts.idempotencyKey(),
            bodySha
        );
        return canonical.getBytes(StandardCharsets.UTF_8);
    }
}
```

### 8.3. Những assumptions phải rõ trong integration adapter

`Parts.rawPath` ở lab có tên “raw”, nhưng trong Servlet `getRequestURI()` và `getQueryString()` đi qua HTTP server/proxy, có thể chứa encoding hoặc representation đã bị thay trước điểm kiểm tra. Không thể mặc định **mọi** Servlet container và gateway giữ nguyên wire bytes ban đầu.

Hợp đồng production phải chọn representation signed URI rõ ràng, reject ambiguous percent-encoding, duplicate query parameters nếu có ảnh hưởng semantics, path normalization và trusted `Host/:authority`. Nếu một proxy rewrite path/body, cần **verify trước transform** hoặc bảo đảm signed original representation được truyền qua **trusted channel**. Đừng dùng caller-controlled `X-Original-URI` để thay raw request.

`Parts.contentType`/`Parts.idempotencyKey` phải đến từ singleton headers đã validate trước coalescing. `X-Idempotency-Key` nằm ngoài Authorization nhưng **được ký**, để một retry có KeyId/nonce mới vẫn giữ cùng business intent. Không chọn idempotency key từ untrusted duplicated headers.

### 8.4. Rủi ro tự ghép chuỗi với dấu newline

V1 dùng fixed ASCII grammar cho parsed `clientId`/`keyId`/`nonce`/`timestamp`, fixed route/authority/content-type và idempotency key regex không cho LF. Nếu không validate trước mà cho newline trong một signed field:

```text
client-id:merchant-42
key-id:key-A
```

attacker có thể chèn một **dòng canonical giả** rồi signer/verifier diễn giải khác nhau. Đây là lý do field values được kiểm soát grammar và phân tách LF có contract rõ; không dựa vào `trim()` hay string concatenate tự do.

## 9. Java 17: chọn một credential và xác thực HMAC/freshness/replay

### 9.1. Quyết định thiết kế

`HmacAuthnEngineV1` dùng parsed credentials **chỉ làm selectors**. Trusted record gắn `ownerClientId`, `keyId`, thuật toán, state, not-before/expiry và secret. Verifier không được thử tất cả keys khi MAC mismatch. Key A/B có thể cùng được verify trong **overlap có deadline**, nhưng `REVOKED`/`PREPARED` không được chấp nhận.

Sau MAC và freshness check, **nonce claim phải atomic và shared** trên mọi replicas. Replay namespace dùng `(environment,verifiedClientId,rawNonce)`, không chứa KeyId, để key rotation không reset replay state. Nếu nonce store timeout/unknown write result, service **fail-closed**.

### 9.2. Class `HmacAuthnEngineV1.java`

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.Optional;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacAuthnEngineV1 {
    private static final long PAST_SECONDS = 300L;
    private static final long FUTURE_SECONDS = 30L;
    private static final long NONCE_MARGIN_SECONDS = 60L;

    public enum KeyState {
        PREPARED, ACTIVE, VERIFY_ONLY, REVOKED
    }

    public record Credential(
        String ownerClientId,
        String keyId,
        String algorithm,
        KeyState state,
        long notBefore,
        long expiresAt,
        byte[] rawSecret
    ) {
        public Credential {
            if (rawSecret == null) {
                throw new IllegalArgumentException(
                    "Missing key material");
            }
            rawSecret = rawSecret.clone();
        }
        @Override
        public byte[] rawSecret() {
            return rawSecret.clone();
        }
        @Override
        public String toString() {
            return "Credential[redacted]";
        }
    }

    public record VerifiedCaller(
        String environment, String clientId, String keyId
    ) {}

    public interface CredentialStore {
        // ClientId/KeyId are UNTRUSTED lookup selectors.
        // Trusted environment comes from route/server policy.
        Optional<Credential> find(
            String environment,
            String claimedClientId,
            String claimedKeyId);
    }

    public interface NonceStore {
        // Shared atomic insert-if-absent, with expiry.
        // Outage/unknown outcome MUST NOT return success.
        boolean claim(
            String environment, String verifiedClientId,
            byte[] rawNonce, long expiresAtEpochSeconds);
    }

    private HmacAuthnEngineV1() {}

    private static byte[] mac(byte[] secret, byte[] data)
            throws GeneralSecurityException {
        if (secret == null || secret.length < 32) {
            throw new IllegalStateException(
                "Weak or missing HMAC secret");
        }
        Mac hmac = Mac.getInstance("HmacSHA256");
        hmac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return hmac.doFinal(data);
    }

    // Lab helper. Production client obtains a provisioned
    // key and generates fresh nonce/timestamp per attempt.
    public static String signForTest(
            HmacSignedPartsV1.Parts parts,
            HmacAuthorizationHeaderV1.Credentials auth,
            byte[] testSecret) throws GeneralSecurityException {
        byte[] tag = mac(
            testSecret, HmacSignedPartsV1.canonicalBytes(parts, auth));
        return Base64.getUrlEncoder().withoutPadding()
            .encodeToString(tag);
    }

    public static Optional<VerifiedCaller> verify(
            HmacSignedPartsV1.Parts parts,
            HmacAuthorizationHeaderV1.Credentials auth,
            String trustedEnvironment,
            long trustedServerEpochSeconds,
            CredentialStore credentials,
            NonceStore nonces) throws GeneralSecurityException {
        // Strict parser has validated syntactic fields.
        byte[] canonical =
            HmacSignedPartsV1.canonicalBytes(parts, auth);
        byte[] supplied =
            HmacAuthorizationHeaderV1.strictBase64url(
                auth.signatureB64url(), 43, 32);

        Optional<Credential> selected = credentials.find(
            trustedEnvironment, auth.clientId(), auth.keyId());
        if (selected.isEmpty()) return Optional.empty();

        Credential record = selected.get();
        long now = trustedServerEpochSeconds;

        boolean mayVerify =
            record.state() == KeyState.ACTIVE
            || record.state() == KeyState.VERIFY_ONLY;

        if (!mayVerify
                || !auth.clientId().equals(record.ownerClientId())
                || !auth.keyId().equals(record.keyId())
                || !"HmacSHA256".equals(record.algorithm())
                || now < record.notBefore()
                || now >= record.expiresAt()) {
            return Optional.empty();
        }

        byte[] expected = mac(record.rawSecret(), canonical);
        if (!MessageDigest.isEqual(expected, supplied)) {
            return Optional.empty();
        }

        long signedTs = Long.parseLong(auth.signedTimestamp());
        final long earliest, latest, expiry;
        try {
            earliest = Math.subtractExact(now, PAST_SECONDS);
            latest = Math.addExact(now, FUTURE_SECONDS);
            expiry = Math.addExact(
                signedTs, PAST_SECONDS + NONCE_MARGIN_SECONDS);
        } catch (ArithmeticException overflow) {
            throw new IllegalStateException(
                "Unsafe time arithmetic", overflow);
        }

        if (signedTs < earliest || signedTs > latest) {
            return Optional.empty();
        }

        byte[] nonce =
            HmacAuthorizationHeaderV1.strictBase64url(
                auth.nonceB64url(), 22, 16);
        if (!nonces.claim(
                trustedEnvironment,
                record.ownerClientId(), nonce, expiry)) {
            return Optional.empty();
        }

        return Optional.of(new VerifiedCaller(
            trustedEnvironment,
            record.ownerClientId(),
            record.keyId()));
    }
}
```

### 9.3. HMAC hợp lệ không có nghĩa request được phép

Kết quả `VerifiedCaller(clientId="merchant-42",keyId="key-2026-b")` chỉ xác nhận client đã chứng minh sở hữu credential đang được tin. Business layer còn phải kiểm tra **scope**, **operation**, **resource owner/tenant**, amount limits và policy hiện hành.

Ví dụ request được ký HMAC đúng nhưng muốn thanh toán từ một account không thuộc `merchant-42` phải bị **403/404 theo authorization policy**. Không lấy `keyId` làm role, không suy quyền từ header `role=admin` do caller tự gửi.

### 9.4. Vì sao nonce/key rotation không được phụ thuộc riêng KeyId?

Nếu verifier dùng replay key `(clientId,keyId,nonce)`, một client có thể gửi nonce N với key A, rồi ký lại cùng nonce N với key B trong overlap; store coi đó là nonce mới. Để một nonce chỉ được dùng một lần trên một verified client, policy của bài dùng:

```text
(environment, verifiedClientId, rawNonceBytes)
```

Với window `serverNow−300 ≤ signedTs ≤ serverNow+30`, TTL của nonce phải kéo dài đến sau `signedTs+300`, thêm margin để tránh boundary race. Ví dụ `expiry=signedTs+300+60`; nếu request đến ở rìa tương lai +30, TTL kể từ lúc claim có thể tới **390 giây**.

**Không** dùng `request.getHeader("Authorization")` như key của replay store. Nó chứa cả signature và các params, khiến thay một chữ ký/KeyId có thể reset namespace và lưu nhiều dữ liệu nhạy cảm.

## 10. Spring Security Servlet: `OncePerRequestFilter` chỉ cấp principal sau verify

### 10.1. Vị trí filter và nguyên tắc fail-closed

Một **custom authentication filter** thường kế thừa Spring Framework `OncePerRequestFilter` và được đăng ký **bên trong một `SecurityFilterChain` phù hợp**. Nhiệm vụ filter:

1. Nhận request đang thuộc phạm vi HMAC-protected route.
2. Parse **một** `Authorization` header bằng `HmacAuthorizationHeaderV1`.
3. Giao parsed credentials và signed request parts cho authentication service.
4. Nếu engine xác minh HMAC/credential/time/nonce thành công, tạo `Authentication` chứa **verified principal** và gắn vào `SecurityContext` mới.
5. Gọi `filterChain.doFilter` **duy nhất ở nhánh thành công**.
6. Khi thất bại, trả response 401/503 phù hợp, **không gọi downstream business code**, không tiết lộ secret/tag.
7. Clear context trong `finally` để tránh state leak trong request thread.

**Quan trọng:** `OncePerRequestFilter` tránh chạy lặp không chủ ý trong một request dispatch theo cơ chế nội bộ, nhưng không tự giải quyết duplicate Authorization, replay protection, async/error dispatch semantics hoặc transaction idempotency. Những yêu cầu đó là các lớp khác.

### 10.2. Class `HmacAuthenticationFilterV1.java`

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class HmacAuthenticationFilterV1
        extends OncePerRequestFilter {
    public interface RouteAuthenticator {
        // Must verify credential ownership, HMAC, freshness,
        // atomic nonce claim BEFORE returning VerifiedCaller.
        HmacAuthnEngineV1.VerifiedCaller authenticate(
            HttpServletRequest request,
            HmacAuthorizationHeaderV1.Credentials untrusted);
    }

    private final RouteAuthenticator authenticator;

    public HmacAuthenticationFilterV1(
            RouteAuthenticator authenticator) {
        if (authenticator == null) {
            throw new IllegalArgumentException(
                "RouteAuthenticator required");
        }
        this.authenticator = authenticator;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        // HMAC-only stateless chain must not inherit authn
        // from a separate HTTP Basic/session/Bearer mechanism.
        SecurityContextHolder.clearContext();

        final HmacAuthnEngineV1.VerifiedCaller verified;
        try {
            var parsed =
                HmacAuthorizationHeaderV1.parseExactlyOne(request);
            verified = authenticator.authenticate(
                request, parsed);
        } catch (AuthenticationServiceException unavailable) {
            // KMS / credential / replay store unavailable.
            // Never continue without authentication.
            SecurityContextHolder.clearContext();
            response.setHeader("Cache-Control", "no-store");
            response.sendError(
                HttpServletResponse.SC_SERVICE_UNAVAILABLE,
                "Authentication temporarily unavailable");
            return;
        } catch (AuthenticationException invalidCredential) {
            SecurityContextHolder.clearContext();
            response.setHeader("Cache-Control", "no-store");
            response.setHeader(
                "WWW-Authenticate", "HMAC realm=\"api\"");
            response.sendError(
                HttpServletResponse.SC_UNAUTHORIZED,
                "Invalid authentication credentials");
            return;
        }

        if (verified == null) {
            // Defensive guard: adapter must not return null
            // to indicate "anonymous but go ahead".
            SecurityContextHolder.clearContext();
            response.setHeader("Cache-Control", "no-store");
            response.sendError(
                HttpServletResponse.SC_UNAUTHORIZED,
                "Invalid authentication credentials");
            return;
        }

        // HMAC + replay checks completed. No roles from
        // Authorization header are trusted.
        Authentication authentication =
            UsernamePasswordAuthenticationToken.authenticated(
                verified, null, List.of());

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);

        try {
            // Only success reaches protected controller.
            chain.doFilter(request, response);
        } finally {
            // Stateless request; never leak context to
            // another request on the same server thread.
            SecurityContextHolder.clearContext();
        }
    }
}
```

Trong ví dụ, `List.of()` tạo tập authorities rỗng để **không tự cấp role từ Authorization header**. Một hệ thực muốn dùng `hasAuthority(...)` phải tải quyền từ **trusted authorization policy** và bảo đảm thay đổi quyền có hiệu lực; không gán mặc định `ROLE_ADMIN` hoặc suy quyền từ `KeyId`. Có thể để controller/service lấy verified principal rồi gọi policy engine theo operation/resource.

### 10.3. Tại sao filter không tự ghi `SecurityContext` từ parser?

Anti-pattern:

```java
// SAI: syntax valid != cryptographically authenticated.
var parsed = HmacAuthorizationHeaderV1.parseExactlyOne(request);
var auth = UsernamePasswordAuthenticationToken.authenticated(
    parsed.clientId(), null, List.of());
SecurityContextHolder.getContext().setAuthentication(auth);
chain.doFilter(request, response);
```

Chỉ cần attacker biết grammar của header là có thể khai `clientId=merchant-42`, không cần secret. **Phải** xác minh MAC với secret đúng owner, key status, timestamp và atomic nonce trước khi tạo authenticated token.

### 10.4. Thứ tự exception và khả năng sẵn sàng của auth infrastructure

`AuthenticationServiceException` là subtype của `AuthenticationException`, vì vậy code catch **service unavailable trước** generic authentication failure. Adapter nên chuyển lỗi credential store/KMS/nonce store sang `AuthenticationServiceException` để filter trả **503**, không cho traffic đi tiếp. Unknown client, bad MAC, expired/revoked key, replay dùng `BadCredentialsException` hoặc kiểu authentication failure tương đương và nhận **401 generic**.

Không catch `Exception` rồi `chain.doFilter` trong `finally`. Điều đó tạo **fail-open** khi database/cache/secret manager lỗi. Hệ thống có thể chọn 500/503 theo operational policy, nhưng không được cho request chưa xác thực đến business handler.

### 10.5. Filter chỉ chạy ở phạm vi API được bảo vệ

Spring Security không “tự hiểu” `HMAC` chỉ nhờ thấy tên class. Phải lắp filter vào một **HMAC-only `SecurityFilterChain`** cho endpoint phù hợp. Nếu filter bị đăng ký như một Servlet `Filter` toàn cục **và** lại được add vào Security chain, nó có thể chạy hai lần, gây parse/nonce claim trùng hoặc xử lý sai scope. Ví dụ dưới **khởi tạo filter bằng `new` trong chain**, không đánh dấu filter là `@Component`/global servlet bean.

## 11. Gắn request-body reader, verifier và `SecurityFilterChain`

### 11.1. Adapter nối Servlet với lõi xác minh

Định nghĩa một boundary `SignedPartsReader`: ứng dụng phải bảo đảm **đã đọc/capture body có giới hạn và có khả năng replay downstream**, đã kiểm tra singleton signed headers/authority và không tin các forwarded headers do caller tự gửi.

```java
import jakarta.servlet.http.HttpServletRequest;
import java.security.GeneralSecurityException;
import java.time.Clock;
import java.util.Optional;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;

public final class HmacRouteAuthAdapterV1
        implements HmacAuthenticationFilterV1.RouteAuthenticator {

    public interface SignedPartsReader {
        // Must return validated semantic signed fields AND
        // exact body bytes from a trusted replayable body wrapper.
        HmacSignedPartsV1.Parts readTrustedParts(
            HttpServletRequest request);
    }

    private final SignedPartsReader reader;
    private final HmacAuthnEngineV1.CredentialStore credentials;
    private final HmacAuthnEngineV1.NonceStore nonces;
    private final Clock trustedClock;
    private final String trustedEnvironment;

    public HmacRouteAuthAdapterV1(
            SignedPartsReader reader,
            HmacAuthnEngineV1.CredentialStore credentials,
            HmacAuthnEngineV1.NonceStore nonces,
            Clock trustedClock,
            String trustedEnvironment) {
        this.reader = reader;
        this.credentials = credentials;
        this.nonces = nonces;
        this.trustedClock = trustedClock;
        this.trustedEnvironment = trustedEnvironment;
    }

    @Override
    public HmacAuthnEngineV1.VerifiedCaller authenticate(
            HttpServletRequest request,
            HmacAuthorizationHeaderV1.Credentials untrusted) {
        try {
            HmacSignedPartsV1.Parts parts =
                reader.readTrustedParts(request);

            Optional<HmacAuthnEngineV1.VerifiedCaller> result =
                HmacAuthnEngineV1.verify(
                    parts, untrusted, trustedEnvironment,
                    trustedClock.instant().getEpochSecond(),
                    credentials, nonces);

            return result.orElseThrow(() ->
                new BadCredentialsException(
                    "Invalid HMAC credentials"));
        } catch (GeneralSecurityException cryptoFailure) {
            // Crypto provider unavailable/misconfigured.
            throw new AuthenticationServiceException(
                "HMAC verification unavailable", cryptoFailure);
        } catch (IllegalArgumentException malformedRequest) {
            throw new BadCredentialsException(
                "Invalid HMAC credentials", malformedRequest);
        }

        // CredentialStore/NonceStore adapters must throw
        // AuthenticationServiceException on I/O/timeouts.
        // Do NOT silently convert store errors to "allowed".
    }
}
```

Nếu `CredentialStore` hoặc `NonceStore` có lỗi network/IAM/DB, adapters tương ứng phải **ném `AuthenticationServiceException`** hoặc failure không được bỏ qua. Một unchecked runtime exception ngoài dự kiến sẽ dẫn đến error response thay vì authenticated success, vẫn fail-closed; production nên phân loại operational errors có kiểm soát.

### 11.2. Một `SignedPartsReader` có thể lấy body ra sao?

Các yêu cầu tối thiểu:

- Raw body snapshot được tạo bởi **trusted middleware** trước verifier, đọc với **size limit** (ví dụ policy 64 KiB ở fixture này) và có downstream replay bằng Servlet-compatible wrapper.
- Đọc `Content-Type` và `X-Idempotency-Key` bằng singleton validation; duplicate/malformed headers reject trước coalescing.
- Chỉ dùng `request.getMethod()`, `request.getRequestURI()`, `request.getQueryString()` sau khi đã định nghĩa đúng routing/canonicalization ở proxy boundary.
- External authority phải lấy từ **trusted reverse proxy/service configuration**, không dùng một `X-Forwarded-Host` do client tự gửi.
- Body bytes được đưa vào `HmacSignedPartsV1.Parts` **đúng là bytes controller xử lý**. Không parse JSON rồi serialize lại để tính hash.

Minh họa interface-to-request mapping:

```java
// PSEUDOCODE: không phải drop-in body wrapper hoàn chỉnh.
HmacSignedPartsV1.Parts readTrustedParts(
        HttpServletRequest request) {
    byte[] body = trustedBodyBuffer.exactBytes(request);
    String contentType =
        singletonHeader(request, "Content-Type");
    String idem =
        singletonHeader(request, "X-Idempotency-Key");

    return new HmacSignedPartsV1.Parts(
        request.getMethod(),
        trustedCanonicalUri.rawPath(request),
        trustedCanonicalUri.rawQuery(request),
        "api.example.test", // configured trusted external authority
        contentType,
        idem,
        body);
}
```

Đây cố ý là **pseudocode** vì `trustedBodyBuffer`, `singletonHeader` và `trustedCanonicalUri` phải triển khai tùy servlet container/proxy. Không biến các placeholder này thành code production mà chưa xử lý body replay, duplicate headers, request smuggling, async/error dispatch, size limits và trusted authority.

**Lưu ý về `ContentCachingRequestWrapper`:** Spring wrapper chỉ cache bytes khi request body thực sự được đọc, và không tự cung cấp một lần đọc lại InputStream như byte-array replay wrapper khi filter đọc trước controller. Thiết kế cần có explicit buffering/replay ở trusted boundary; không cho body “đã verify” khác body “đã execute”.

### 11.3. Config Spring Security 6 / Spring Boot 3 (Servlet stack)

Đây là ví dụ lắp **HMAC-only chain** cho `/v1/payments`. Giả sử ứng dụng đã cung cấp `CredentialStore`, `NonceStore` và `SignedPartsReader` đúng các hợp đồng ở trên.

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class HmacSecurityConfigV1 {

    @Bean
    @Order(1)
    SecurityFilterChain hmacApiChain(
            HttpSecurity http,
            HmacRouteAuthAdapterV1.SignedPartsReader reader,
            HmacAuthnEngineV1.CredentialStore credentialStore,
            HmacAuthnEngineV1.NonceStore nonceStore,
            Clock trustedClock) throws Exception {

        var authenticator = new HmacRouteAuthAdapterV1(
            reader, credentialStore, nonceStore,
            trustedClock, "prod");

        // new inside chain: avoid auto-registering the filter
        // as a global Servlet Filter Bean/@Component.
        var filter = new HmacAuthenticationFilterV1(
            authenticator);

        http.securityMatcher("/v1/payments")
            .csrf(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth ->
                auth.anyRequest().authenticated())
            .addFilterBefore(
                filter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
```

**Giải thích SecurityFilterChain:**

- `securityMatcher("/v1/payments")` hạn chế chain theo path của ví dụ. Method `POST` được `HmacSignedPartsV1` kiểm tra; production nên khai báo method/path policy rõ, bao gồm OPTIONS/CORS nếu client chạy từ browser.
- Không tự chấp nhận Basic/Bearer/form login trong HMAC-only route. Nếu ứng dụng có nhiều chains, phải cấu hình **ordered matchers không overlap mơ hồ** và catch-all policy **không bỏ lọt endpoint khác**.
- Stateless không dùng session để lưu credential; chỉ đặt authenticated `SecurityContext` cho request đã được verify. Các endpoints dùng cookie/session có CSRF threat model riêng: **không tắt CSRF toàn ứng dụng** vì mẫu stateless này.
- `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` minh họa thứ tự trước các authentication mechanisms thường gặp; cần kiểm tra **thứ tự thực tế** của Spring Security chain khi app có CORS, custom filters, exception handling, authn khác và async dispatch.
- Không đăng ký filter một lần qua `@Component` và một lần qua `addFilterBefore`. Nếu buộc dùng filter bean, xem xét `FilterRegistrationBean#setEnabled(false)` để tránh Servlet auto-registration bên ngoài `springSecurityFilterChain`.
- Ví dụ chưa tự tạo `CredentialStore`/`NonceStore`/`SignedPartsReader` beans. Đây là **integration contracts** phải cung cấp bằng adapter thật và được thử trong môi trường có gateway/DB/Redis/KMS; không phải một ví dụ production “copy là chạy”.

### 11.4. CORS preflight, async và các dispatch types

`OPTIONS` preflight của browser thường **không mang Authorization HMAC**; nếu ứng dụng thật hỗ trợ browser clients, cần trusted CORS config/filter chạy ở đúng vị trí và permit preflight theo policy. Không blanket bypass mọi `OPTIONS`/`HEAD` rồi để business route đổi method qua proxy.

`OncePerRequestFilter` có cơ chế để kiểm soát async/error dispatch, nhưng điều đó không tự đảm bảo **SecurityContext propagation** sang async thread hay filter đã chạy đúng một lần cho mọi tình huống phân tán. Nếu dùng async request processing, test error/async dispatch, trusted principal propagation và không claim nonce hai lần.

### 11.5. Spring MVC `HandlerInterceptor` có thay filter được không?

`HandlerInterceptor` có thể đọc header nhưng thường xảy ra **sau phần lớn Spring Security filter chain**. Nếu tạo authenticated principal ở interceptor, route security decisions đã có thể chạy trước đó, dễ tạo sai trust boundary. **HMAC authentication nên nằm trong SecurityFilterChain hoặc một authentication mechanism chuẩn tương đương**, không chỉ một interceptor dùng `request.setAttribute("clientId",...)`.

Interceptor vẫn hữu ích cho tracing, idempotency middleware hoặc business metrics **sau** khi authentication đã được xác minh; không tự thay thế HMAC verifier.

## 12. Java 17: kiểm thử parser và lõi HMAC bằng golden vectors

### 12.1. Test phải dùng oracle độc lập

Nếu unit test chỉ gọi `sign()` rồi đưa output vào `verify()` của **cùng implementation**, hai hàm có thể **cùng quên ký KeyId** hoặc cùng hash JSON sau khi reserialize nhưng vẫn pass. Golden vectors ở `6` được tính từ **exact canonical bytes** và independent SHA-256/HMAC-SHA256, đóng vai trò external oracle.

Thực hành cần chứng minh:

1. Parser chấp nhận **một** HMAC V1 value đúng; scheme casing không đổi semantics.
2. Parser từ chối duplicate header, Bearer/Basic, v2, wrong order, extra/duplicate params, CRLF, Base64url padding và timestamp overflow.
3. Exact canonical string có **13 dòng / 304 bytes** cho key A/B.
4. HMAC tag A/B khớp **expected independent values**, không chỉ round-trip.
5. A/B có thể verify theo đúng key trong overlap; khi A revoked, HMAC A vẫn toán học đúng nhưng authentication fail.
6. Ký lại bằng key B **cùng nonce** sau A không được vượt replay store shared theo verified client.
7. HMAC sai/bad timestamp không được claim nonce trước; không có downstream business effects.
8. Header/client/key/body bị sửa sau ký không được xác thực.

### 12.2. Class `HmacAuthorizationChecksV1.java`

Ví dụ đặt ở **test source set** của dự án có Spring Security và `spring-test`. `MockHttpServletRequest` giúp kiểm tra các values còn hiển thị ở Servlet API; để test **raw duplicate field lines trước proxy**, vẫn cần HTTP wire/integration tests riêng.

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.BadCredentialsException;

public final class HmacAuthorizationChecksV1 {
    private static final long NOW = 1790000000L;
    private static final String NONCE =
        "QEFCQ0RFRkdISUpLTE1OTw";
    private static final String TAG_A =
        "6fkOmJSyLX1T-nTZn51okmf5AM-ihQ7uX8V-vCATqWY";
    private static final String TAG_B =
        "BIDLsx2PdbdEYe4oQWGE95T1PDrFhPsKSYNLOS5PJUo";

    private static final String HEADER_A =
        "HMAC version=\"1\", clientId=\"merchant-42\", "
      + "keyId=\"key-2026-a\", timestamp=\"1790000020\", "
      + "nonce=\"" + NONCE + "\", "
      + "signature=\"" + TAG_A + "\"";

    private static final String HEADER_B =
        "HMAC version=\"1\", clientId=\"merchant-42\", "
      + "keyId=\"key-2026-b\", timestamp=\"1790000020\", "
      + "nonce=\"" + NONCE + "\", "
      + "signature=\"" + TAG_B + "\"";

    private static byte[] keyA() {
        return HexFormat.of().parseHex(
            "000102030405060708090a0b0c0d0e0f"
          + "101112131415161718191a1b1c1d1e1f");
    }

    private static byte[] keyB() {
        return HexFormat.of().parseHex(
            "202122232425262728292a2b2c2d2e2f"
          + "303132333435363738393a3b3c3d3e3f");
    }

    private static HmacSignedPartsV1.Parts parts() {
        return new HmacSignedPartsV1.Parts(
            "POST", "/v1/payments", "currency=VND",
            "api.example.test", "application/json",
            "pay-903",
            "{\"paymentId\":\"p-903\",\"amount\":125000,"
          + "\"currency\":\"VND\"}"
                .getBytes(StandardCharsets.UTF_8));
    }

    private static HmacAuthnEngineV1.CredentialStore credentials(
            HmacAuthnEngineV1.KeyState oldKeyState) {
        return (env, claimedClient, claimedKeyId) -> {
            if (!"test".equals(env)
                    || !"merchant-42".equals(claimedClient)) {
                return Optional.empty();
            }
            if ("key-2026-a".equals(claimedKeyId)) {
                return Optional.of(new HmacAuthnEngineV1.Credential(
                    "merchant-42", "key-2026-a",
                    "HmacSHA256", oldKeyState,
                    1789990000L, 1790100000L, keyA()));
            }
            if ("key-2026-b".equals(claimedKeyId)) {
                return Optional.of(new HmacAuthnEngineV1.Credential(
                    "merchant-42", "key-2026-b",
                    "HmacSHA256", HmacAuthnEngineV1.KeyState.ACTIVE,
                    1789990000L, 1790100000L, keyB()));
            }
            return Optional.empty();
        };
    }

    private static HmacAuthnEngineV1.NonceStore
            freshNonceStore() {
        record ReplayKey(
            String environment, String verifiedClient,
            String nonceB64url) {}

        Set<ReplayKey> claimed =
            ConcurrentHashMap.newKeySet();
        return (env, client, rawNonce, expiresAt) -> {
            if (expiresAt <= NOW) {
                throw new IllegalStateException(
                    "Bad nonce expiry");
            }
            String encoded = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(rawNonce);
            return claimed.add(new ReplayKey(env, client, encoded));
        };
    }

    @FunctionalInterface
    private interface ParserAction {
        void run();
    }

    private static void expectInvalid(ParserAction action) {
        try {
            action.run();
            throw new AssertionError(
                "Invalid Authorization accepted");
        } catch (BadCredentialsException expected) {
            // Correct reject, not an assertion failure.
        }
    }

    private static void check(
            boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        var authA =
            HmacAuthorizationHeaderV1.parseHeaderValue(HEADER_A);
        var authB =
            HmacAuthorizationHeaderV1.parseHeaderValue(HEADER_B);
        var lowerScheme =
            HmacAuthorizationHeaderV1.parseHeaderValue(
                "hmac" + HEADER_B.substring(4));

        check(authB.equals(lowerScheme),
            "Scheme casing changed parsed semantics");
        check("merchant-42".equals(authB.clientId()),
            "Wrong parsed client ID");
        check("key-2026-b".equals(authB.keyId()),
            "Wrong parsed key ID");

        MockHttpServletRequest one =
            new MockHttpServletRequest("POST", "/v1/payments");
        one.addHeader("Authorization", HEADER_B);
        check(authB.equals(
            HmacAuthorizationHeaderV1.parseExactlyOne(one)),
            "Single header must parse");

        MockHttpServletRequest twice =
            new MockHttpServletRequest("POST", "/v1/payments");
        twice.addHeader("Authorization", HEADER_B);
        twice.addHeader("Authorization", HEADER_A);
        expectInvalid(() ->
            HmacAuthorizationHeaderV1.parseExactlyOne(twice));

        MockHttpServletRequest missing =
            new MockHttpServletRequest("POST", "/v1/payments");
        expectInvalid(() ->
            HmacAuthorizationHeaderV1.parseExactlyOne(missing));

        expectInvalid(() ->
            HmacAuthorizationHeaderV1.parseHeaderValue(
                "Bearer something"));
        expectInvalid(() ->
            HmacAuthorizationHeaderV1.parseHeaderValue(
                HEADER_B.replace("version=\"1\"",
                    "version=\"2\"")));
        expectInvalid(() ->
            HmacAuthorizationHeaderV1.parseHeaderValue(
                HEADER_B.replace(", keyId=", ", unknown=\"x\", keyId=")));
        expectInvalid(() ->
            HmacAuthorizationHeaderV1.parseHeaderValue(
                HEADER_B.replace("clientId=", "clientid=")));
        expectInvalid(() ->
            HmacAuthorizationHeaderV1.parseHeaderValue(
                HEADER_B + "\r\nInjected: true"));
        expectInvalid(() ->
            HmacAuthorizationHeaderV1.parseHeaderValue(
                HEADER_B.replace(
                    "signature=\"" + TAG_B + "\"",
                    "signature=\"" + TAG_B + "=\"")));

        var requestParts = parts();
        check(HmacSignedPartsV1.canonicalBytes(
            requestParts, authA).length == 304,
            "Canonical A length changed");
        check(HmacSignedPartsV1.canonicalBytes(
            requestParts, authB).length == 304,
            "Canonical B length changed");

        check(TAG_A.equals(HmacAuthnEngineV1.signForTest(
            requestParts, authA, keyA())), "A golden HMAC mismatch");
        check(TAG_B.equals(HmacAuthnEngineV1.signForTest(
            requestParts, authB, keyB())), "B golden HMAC mismatch");

        var duringRotation = credentials(
            HmacAuthnEngineV1.KeyState.VERIFY_ONLY);

        // Isolated stores only for independent positive tests.
        check(HmacAuthnEngineV1.verify(
            requestParts, authA, "test", NOW,
            duringRotation, freshNonceStore()).isPresent(),
            "A verify-only should be accepted during overlap");

        check(HmacAuthnEngineV1.verify(
            requestParts, authB, "test", NOW,
            duringRotation, freshNonceStore()).isPresent(),
            "B active should be accepted");

        // Cross-KeyId: same verified client and nonce N
        // must not be accepted twice on one shared store.
        var sharedReplay = freshNonceStore();
        check(HmacAuthnEngineV1.verify(
            requestParts, authA, "test", NOW,
            duringRotation, sharedReplay).isPresent(),
            "A first nonce claim");
        check(HmacAuthnEngineV1.verify(
            requestParts, authB, "test", NOW,
            duringRotation, sharedReplay).isEmpty(),
            "Key rotation must not reset replay state");

        var afterRevoke = credentials(
            HmacAuthnEngineV1.KeyState.REVOKED);
        check(HmacAuthnEngineV1.verify(
            requestParts, authA, "test", NOW,
            afterRevoke, freshNonceStore()).isEmpty(),
            "Revoked A still accepted");
        check(HmacAuthnEngineV1.verify(
            requestParts, authB, "test", NOW,
            afterRevoke, freshNonceStore()).isPresent(),
            "Active B unexpectedly denied");

        // Selector tampering cannot reuse a MAC from another key.
        var wrongTagForB =
            new HmacAuthorizationHeaderV1.Credentials(
                "1", "merchant-42", "key-2026-b",
                "1790000020", NONCE, TAG_A);
        check(HmacAuthnEngineV1.verify(
            requestParts, wrongTagForB, "test", NOW,
            afterRevoke, freshNonceStore()).isEmpty(),
            "A signature must not prove key B");

        AtomicInteger nonceClaims = new AtomicInteger();
        HmacAuthnEngineV1.NonceStore spy =
            (env, client, nonce, expiry) -> {
                nonceClaims.incrementAndGet();
                return true;
            };
        var badMac = new HmacAuthorizationHeaderV1.Credentials(
            "1", "merchant-42", "key-2026-b",
            "1790000020", NONCE,
            "A" + TAG_B.substring(1));
        check(HmacAuthnEngineV1.verify(
            requestParts, badMac, "test", NOW,
            afterRevoke, spy).isEmpty(), "Tampered MAC passed");
        check(nonceClaims.get() == 0,
            "Bad MAC poisoned nonce state");

        // Old timestamp correctly re-signed -> MAC valid,
        // time invalid; no nonce claim.
        var oldTimestamp = new HmacAuthorizationHeaderV1.Credentials(
            "1", "merchant-42", "key-2026-b",
            "1789999000", NONCE, TAG_B);
        String oldTag = HmacAuthnEngineV1.signForTest(
            requestParts, oldTimestamp, keyB());
        var oldSigned = new HmacAuthorizationHeaderV1.Credentials(
            "1", "merchant-42", "key-2026-b",
            "1789999000", NONCE, oldTag);
        check(HmacAuthnEngineV1.verify(
            requestParts, oldSigned, "test", NOW,
            afterRevoke, spy).isEmpty(), "Old timestamp passed");
        check(nonceClaims.get() == 0,
            "Expired request poisoned nonce state");

        // Same nonce concurrently: only one accepted
        // IN THIS JVM TEST STORE (not a distributed guarantee).
        var concurrentReplay = freshNonceStore();
        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Boolean>> calls = new ArrayList<>();
        try {
            for (int i = 0; i < 32; i++) {
                calls.add(pool.submit(() -> {
                    start.await();
                    return HmacAuthnEngineV1.verify(
                        requestParts, authB, "test", NOW,
                        afterRevoke, concurrentReplay).isPresent();
                }));
            }
            start.countDown();
            int successes = 0;
            for (Future<Boolean> call : calls) {
                if (call.get()) successes++;
            }
            check(successes == 1,
                "Expected exactly one nonce winner");
        } finally {
            pool.shutdownNow();
        }

        System.out.println(
            "Strict parser, golden HMAC, rotation, replay OK");
    }
}
```

### 12.3. Kết quả nào chưa được chứng minh bởi test trên?

- `MockHttpServletRequest` chỉ mô phỏng Servlet view, không kiểm tra **proxy đã coalesce/drop duplicated wire headers** hoặc HTTP request smuggling.
- `ConcurrentHashMap.newKeySet()` trong `freshNonceStore()` chỉ atomic ở **một JVM**, không có TTL cleanup và không bảo đảm chống replay khi nhiều replicas/regions.
- Golden MAC chứng minh canonical bytes và HMAC inputs, không chứng minh **trusted body capture** trong production.
- Record `CredentialStore` fake không chứng minh KMS, IAM, secret provisioning, revocation cache propagation hoặc key compromise incident response.
- `VerifiedCaller` không chứng minh caller được phép chuyển tiền từ một account nào đó. Authorization và business side effect tests phải chạy ở controller/repository.
- Test parser không thay cho Spring Security integration tests về filter order, context clearing, 401/503 response, async dispatch, CORS và các schemes khác.

Một test suite tốt cần **chạy integration tests qua HTTP ingress thật** với các request malformed/duplicate và kiểm tra downstream **business invocation count bằng 0** cho mọi authentication failure.

## 13. Pipeline khi nhiều filter và gateway cùng tồn tại

### 13.1. Thứ tự filter có thể biến authn thành authz bug

Một hệ thống có thể có các filter:

```text
Trusted reverse proxy / TLS
  -> Request size + HTTP framing/duplicate-header guard
  -> CORS / routing policy (nếu có)
  -> Spring Security FilterChainProxy
      -> SecurityContext management
      -> Custom HMAC authentication filter
      -> AnonymousAuthenticationFilter (nếu không authn)
      -> AuthorizationFilter
  -> Controller
  -> Transactional business authorization + idempotency
```

Đây là **mô hình thứ tự khái niệm**, không phải khẳng định Spring Security filter order mặc định của mọi phiên bản/cấu hình. Phải xem chain thực tế bằng diagnostics/integration tests. Nếu custom HMAC filter chạy **sau** authorization decision mà vẫn kỳ vọng lập principal, authorization có thể ra quyết định khi chưa có danh tính đúng. Nếu chạy **trước HTTP ingress validator** và container đã coalesce headers, có thể mất bằng chứng duplicate.

### 13.2. Vì sao không để HMAC filter “chỉ đăng nhập nếu có header”?

Một filter có code:

```java
if (request.getHeader("Authorization") == null) {
    chain.doFilter(request, response);
    return;
}
```

có thể hợp lý **trong một chain hỗn hợp có policy rõ** và điểm cuối yêu cầu authentication được bảo vệ bởi AuthorizationFilter, nhưng **không phù hợp với HMAC-only endpoint nếu sau đó có alternate credential/session** vô tình được chấp nhận. Bài chọn HMAC-only chain: **thiếu Authorization = 401** và không có đường silent fallback.

Nếu ứng dụng chủ ý cho phép cả Bearer và HMAC trên cùng một resource, phải thiết kế một **authentication manager/resolver** tách rõ scheme, principal mapping, accepted audiences và downgrade risk; không hack bằng `if (raw.startsWith("Bearer")) continue` rồi để kết quả phụ thuộc filter order.

### 13.3. HMAC authentication khác API authorization

Sau khi HMAC verifier trả principal, service vẫn cần:

```text
VerifiedCaller(environment=prod, clientId=merchant-42)
Operation=payments:create
Resource=account-42
Amount=125000
Tenant scope=merchant-42 / authorized account list
Current permission policy=allows?
```

Một `Authentication` có `isAuthenticated() == true` không có nghĩa `merchant-42` được phép tạo payment từ account của `merchant-73`. Spring Security có thể enforce method/route authorities nhưng **object-level authorization** cần kiểm tra resource ownership trong service/DB; với multi-tenant data phải có tenant predicates, composite FK/RLS theo policy và tránh TOCTOU.

### 13.4. Đọc Authorization khác sử dụng idempotency key

`Authorization` chứa các trường để **xác thực** attempt. `X-Idempotency-Key` nhận diện một **business intent** xuyên retries. Khi retry sau network timeout:

```text
Attempt 1:
  KeyId=key-2026-a
  Timestamp=T1
  Nonce=N1
  Signature=HMAC_A(canonical(T1,N1,keyA,...))
  X-Idempotency-Key=pay-903

Attempt 2:
  KeyId=key-2026-b
  Timestamp=T2
  Nonce=N2
  Signature=HMAC_B(canonical(T2,N2,keyB,...))
  X-Idempotency-Key=pay-903       // giữ nguyên
```

Request thứ hai phải vượt HMAC/freshness/nonce với **attempt mới**, rồi idempotency store lookup theo `(verifiedClient, operation, idempotencyKey)` và stable intent fingerprint. **Không** scope idempotency theo KeyId/nonce/signature/header raw string, vì rotation hoặc retry sẽ khiến cùng payment bị tạo lại.

Authentication failure **không** được trả cached payment response chỉ vì idempotency key khớp. Business authorization hiện hành phải được đánh giá trước khi trả kết quả lưu trữ có dữ liệu nhạy cảm.

### 13.5. Phía proxy/gateway có thể chọn Auth header khác Servlet

Một request có hai Authorization lines có thể bị:

- Proxy trả lỗi ngay (an toàn khi contract cấm duplicates).
- Proxy nối thành một value có dấu phẩy (parser V1 sẽ reject, nếu nguyên value được giữ).
- Proxy bỏ một value, forward value còn lại (Servlet **không thể biết** lúc ingress từng có hai occurrences).
- API gateway chọn Bearer trong khi backend chọn HMAC; hai principals khác nhau.
- Reverse proxy strip Authorization hoàn toàn vì config sai; backend thấy missing header.
- Gateway đổi Host/URI/body khiến canonical MAC mismatch với client.
- Gateway giữ một cached authentication assertion từ phiên bản key đã revoked.

Để bảo vệ chính xác cần **raw-wire duplicate guard ở trusted ingress**, route-specific authentication scheme policy, trusted external request representation, negative tests cross-layer và key revocation propagation. Không cố suy “trước proxy chắc chắn chỉ có một header” từ Servlet API.

### 13.6. Khi backend đã tin gateway thay vì tự verify

Nếu gateway thực hiện HMAC verification:

```text
Client -- HMAC Authorization --> trusted gateway
Gateway: parse, credential lookup, MAC, timestamp, atomic nonce
Gateway -- authenticated internal identity assertion --> backend
Backend: validate gateway identity/assertion, authorize resource
```

Backend **không nên** đọc lại một `X-Verified-Client` do public client có thể gửi. Gateway phải strip forged headers, tạo assertion qua authenticated/mTLS channel hoặc signed internal mechanism, có audience/timestamp/request binding và hạn chế direct backend access. **Không claim nonce hai lần** nếu gateway đã claim và backend chỉ nhận trusted assertion; nếu backend tự verify, phải thống nhất replay ownership.

Filter backend phải áp dụng trust contract **một cách nhất quán**, không tùy tiện tin Bearer/HMAC/forwarded identity dựa trên giá trị header nào có vẻ hợp lệ nhất.

## 14. Ma trận kiểm thử `Authorization` trong custom HMAC filter

Một test nên ghi rõ **raw wire request nếu có, Servlet-visible header values, parsed credentials, selected credential record, canonical bytes, MAC result, nonce claim count, SecurityContext result và business side effects**. Chỉ test `parseHeaderValue("...")` trả đúng ClientId chưa chứng minh ứng dụng an toàn.

### 14.1. Header syntax và duplicate handling

| Test | Input hoặc mutation | Kết quả mong đợi |
| --- | --- | --- |
| H01 | Thiếu `Authorization` trên HMAC-only route | `401`, không chạy business |
| H02 | Một header V1 đúng | Parser trả 6 fields, **chưa** authenticated |
| H03 | Hai Authorization values HMAC hợp lệ | Reject, không chọn first/last |
| H04 | `Authorization` và `authorization` ở raw HTTP | Raw ingress reject duplicate case-insensitive |
| H05 | Proxy coalesce hai Authorization fields | Strict grammar reject resultant ambiguous value |
| H06 | `Authorization: Bearer ...` | Reject ở HMAC-only chain |
| H07 | `Authorization: Basic ...` | Reject; không decode như HMAC |
| H08 | `hmac` / `HMAC` scheme casing | Được parse cùng semantics V1 |
| H09 | `clientId` đổi thành `clientid` | Reject parameter name sai grammar |
| H10 | Đảo vị trí `keyId` và `clientId` | Reject V1 fixed order |
| H11 | Thiếu `timestamp` hoặc `signature` | Reject |
| H12 | Thêm `role="admin"`/unknown param | Reject, không cấp quyền |
| H13 | Duplicate `keyId` bên trong cùng header value | Reject |
| H14 | Quoted string chứa `\\"`/backslash escape | Reject theo grammar V1 |
| H15 | Quoted value chứa dấu phẩy | Reject, không `split(",")` |
| H16 | Dùng TAB thay ASCII SP sau scheme/separator | Reject theo V1 |
| H17 | Hai SP hoặc thiếu space giữa params | Reject |
| H18 | Leading/trailing whitespace ở value sau Servlet parse | Reject nếu còn hiện diện; ingress normalization riêng |
| H19 | CRLF/header injection trong Authorization value | HTTP ingress/strict parser reject |
| H20 | Unicode confusables/zero-width ID | Reject ASCII grammar |
| H21 | Header dài hơn `MAX_HEADER_CHARS` | Reject trước regex và không log raw input |
| H22 | Timestamp 19 số nhưng overflow `long` | Reject khi parse |
| H23 | Nonce sai Base64url alphabet/length/pad bits | Reject trước MAC/claim |
| H24 | Signature có padding `=`, `+`/`/`, sai 43 chars | Reject strict Base64url no-pad |

### 14.2. HMAC, credential selection và replay

| Test | Fixture / mutation | Kết quả mong đợi |
| --- | --- | --- |
| C01 | JSON fixture exact bytes | Body length **54**, SHA-256 `6c4c3379...23a4ee` |
| C02 | Canonical key B | **13 dòng, 304 UTF-8 bytes**, LF/no final LF |
| C03 | Key A `00..1f` | HMAC Base64url `6fkOmJSyLX1T-nTZn51okmf5AM-ihQ7uX8V-vCATqWY` |
| C04 | Key B `20..3f` | HMAC Base64url `BIDLsx2PdbdEYe4oQWGE95T1PDrFhPsKSYNLOS5PJUo` |
| C05 | Signer/verifier bỏ `client-id` khỏi canonical input | Golden test fail |
| C06 | Bỏ `key-id` hoặc `auth-version` khỏi input | Golden test fail |
| C07 | Đổi ClientId sau ký, giữ tag B | MAC mismatch hoặc owner reject |
| C08 | Đổi KeyId B→A, giữ tag B | Reject, không thử secret B sau A |
| C09 | Đổi amount/body byte sau ký | Reject, no business side effect |
| C10 | Đổi method/path/query/authority | Reject hoặc MAC mismatch |
| C11 | Đổi `X-Idempotency-Key` | MAC mismatch |
| C12 | Credential owner khác claimed ClientId | Reject không cấp principal |
| C13 | Credential algorithm ngoài `HmacSHA256` | Reject, không algorithm fallback |
| C14 | Credential `PREPARED` | Reject dù HMAC đúng |
| C15 | Credential `REVOKED` | Reject dù HMAC đúng |
| C16 | Credential `VERIFY_ONLY` trong approved overlap | Có thể verify tới deadline; không dùng nếu compromised |
| C17 | `notBefore` ở tương lai hoặc `expiresAt` đã qua | Reject theo trusted now |
| C18 | HMAC sai nhưng nonce chưa claim | Claim count **0** |
| C19 | HMAC đúng nhưng signed timestamp quá cũ/tương lai | Reject, claim count **0** |
| C20 | Replay signed nonce N dưới cùng verified client | Atomic claim duplicate, reject |
| C21 | Key A→B nhưng reuse nonce N | Reject nếu replay namespace không chứa KeyId |
| C22 | Credential/nonce store outage hoặc unknown outcome | Fail-closed, không dùng fallback/default secret |

### 14.3. Filter, SecurityContext và status responses

| Test | Setup | Kết quả mong đợi |
| --- | --- | --- |
| F01 | Missing header tới HMAC-only endpoint | Response `401`, no `chain.doFilter` |
| F02 | Parser trả `BadCredentialsException` | `401` generic, no raw header in response |
| F03 | Unknown client / invalid MAC | `401` generic, chống enumeration |
| F04 | Credential store throws `AuthenticationServiceException` | `503`, fail-closed |
| F05 | Nonce store timeout hoặc unknown result | `503`/policy outage, **no 200** |
| F06 | Valid HMAC/time/nonce | Tạo `Authentication.isAuthenticated() == true` |
| F07 | Parsed ClientId nhưng MAC chưa verify | Không tạo SecurityContext |
| F08 | HMAC đúng nhưng business authz denied | `403/404` theo policy, **no business effect** |
| F09 | `SecurityContextHolder` sau request/failure | Không còn principal leak tới request sau |
| F10 | Filter đăng ký global servlet bean lẫn Security chain | Test phát hiện double invocation |
| F11 | Non-HMAC endpoint dùng chain khác | Không bị custom filter chặn nhầm |
| F12 | HMAC endpoint bị route matcher bỏ sót | Security integration test fail |
| F13 | HMAC endpoint có session Basic/Bearer cũ | Không silent auth downgrade |
| F14 | HMAC verifier trả `null` | Không coi anonymous là success |
| F15 | Exception trong controller sau authn | SecurityContext được clear trong `finally` |
| F16 | `OPTIONS` CORS preflight cho browser theo policy | CORS handled rõ, không blanket auth bypass |
| F17 | Servlet async/error redispatch | Không double nonce claim/context leak |
| F18 | Filter order với AuthorizationFilter | HMAC principal phải có trước authz decision |
| F19 | HMAC valid nhưng authorities rỗng | Không tự có admin role |
| F20 | Authenticated principal đã revoked business scope | Authorization deny dù MAC valid |
| F21 | `WWW-Authenticate` trên `401` | Challenge đúng HMAC contract, không lộ key |
| F22 | `Cache-Control: no-store` và sanitized logs | Không cache/tiết lộ auth error body |

### 14.4. HTTP proxy/gateway, data safety và distributed state

| Test | Môi trường / sự cố | Kết quả mong đợi |
| --- | --- | --- |
| I01 | HTTP/1.1 → HTTP/2 lowercase **header names** | Canonical semantics giữ nguyên |
| I02 | Proxy lowercases `clientId/keyId/signature` values | Lookup/MAC reject; không tự sửa |
| I03 | Duplicate Authorization split ở edge, merged ở backend | Edge reject; không first/last parser disagreement |
| I04 | Gateway strips Authorization | HMAC-only backend reject, không fall through |
| I05 | Raw URI/query percent encoding bị rewrite | MAC verify đúng boundary hoặc reject |
| I06 | Proxy đổi Host external thành internal DNS | Trusted signed external authority nhất quán |
| I07 | Proxy tự rewrite body JSON | Body digest mismatch hoặc verify trước transform |
| I08 | Filter đọc body rồi controller thấy rỗng | Integration test fail; cần replayable bounded wrapper |
| I09 | Body hơn 64 KiB theo V1 | Reject trước buffering không giới hạn |
| I10 | Hai gateways mỗi bên nonce map local | Integration test bắt double replay acceptance |
| I11 | Shared nonce store atomic across replicas | Một request/nonce, tối đa một winner |
| I12 | Key revocation ở region A, edge B stale cache | Negative canary fail nếu B còn accept old key |
| I13 | Idempotency store keyed theo `KeyId` | Regression phát hiện double payment sau rotation |
| I14 | Payment retry dùng mới key/time/nonce, same idem | Không side effect thứ hai |
| I15 | Invalid HMAC nhưng cache idem có response | Không trả cached sensitive result trước authn |
| I16 | Backend tin `X-Verified-Client` từ caller | Negative test phát hiện principal spoof |
| I17 | Public direct backend route bỏ gateway | Bị chặn hoặc backend verify tương đương |
| I18 | Gateway và backend claim cùng nonce | Test thống nhất một replay owner |
| I19 | KMS/secret manager outage | No fallbacks, no plaintext logs |
| I20 | Multi-tenant `clientId/keyId` trùng giữa tenants | Credential lookup/owner mapping không nhầm tenant |
| I21 | DR restore secret cũ nhưng mất nonce/idempotency | Fail-closed/reconcile trước business |
| I22 | Full Authorization trong access logs/traces | Redaction/security test fail |

**Tổng cộng 90 ca kiểm thử được đánh số**: H01–H24 (24), C01–C22 (22), F01–F22 (22), I01–I22 (22). Những ca trên là **test design**, không hàm ý tất cả đã được chạy. Code phần 12 chỉ bao phủ một tập con; gateway/Servlet raw wire, body wrapper, SecurityFilterChain, DB/Redis/KMS và business authorization cần integration environment riêng.

### 14.5. Property-based tests và metamorphic invariants

Ngoài các fixture cụ thể, fuzz với request values ngắn/có giới hạn:

- Với mọi Authorization value **không khớp V1 grammar đầy đủ**, parser không được tạo `Credentials`.
- Với mọi duplicated Authorization header occurrences ở raw ingress, HTTP route phải reject trước khi gọi HMAC verifier.
- Với mọi thay đổi scheme từ HMAC sang Basic/Bearer, HMAC-only chain không xác thực client.
- Với mọi thay đổi `clientId/keyId/version/timestamp/nonce` **sau khi ký** mà giữ tag, MAC không thể được xác minh hợp lệ (trừ xác suất MAC collision cực nhỏ).
- Với mọi credential record có owner không khớp claimed client hoặc state revoked, không được tạo verified principal dù tag toán học đúng.
- Với mọi nonce N đã claim trong verified client namespace, thay KeyId không cho claim N lần hai trong window.
- Với mọi invalid MAC/time, nonce store claim count phải bằng 0 và business invocation count bằng 0.
- Với mọi storage outage/unknown claim outcome, filter không gọi protected controller.
- Với mọi business authorization deny, HMAC success **không** tạo side effect.
- Với mọi request body bytes đã được ký, bytes mà business controller xử lý phải là **chính bytes đó**, không phải một representation sau parse/proxy transformation khác.
- Với mọi request thread/async context reuse, không có authenticated principal từ request trước bị leak sang request sau.
- Với mọi client retry idempotent sau key rotation, stable business scope/fingerprint giữ nguyên trong khi nonce/time/HMAC được cập nhật.

Một parser test chỉ dùng Java `String` không thể chứng minh raw-wire HTTP duplicate/header smuggling safety. Cần kiểm thử các tầng độc lập và kết quả nghiệp vụ.

## 15. Tình huống lỗi thường gặp và lời giải

### A. “Lấy Authorization rồi cắt năm ký tự đầu”

Filter dùng `request.getHeader("Authorization").substring(5)` để lấy credentials, không kiểm scheme.

**Phân tích:** Với Bearer/Basic/empty header, logic cắt sai hoặc exception; attacker có thể kích hoạt fallback/500. Dùng **strict scheme + full grammar parser**; route-specific HMAC-only chain. Missing/malformed header trả authentication failure, không cho downstream.

### B. “Có hai Authorization headers nhưng getHeader lấy một”

Client gửi `Authorization: HMAC ...` và `authorization: Bearer ...`; gateway/backend đọc giá trị khác.

**Phân tích:** `getHeader()` không đủ để chứng minh uniqueness. Dùng `getHeaders()` ở Servlet để reject nhiều visible values và **ingress raw-wire duplicate guard** trước coalescing. Không có cách khôi phục field đã bị proxy xóa hoặc gộp mất information.

### C. “Split theo dấu phẩy và ghi params vào HashMap”

Một parser nhận `Authorization: HMAC clientId="a,b", keyId="x", ...` và `map.put(key,value)`.

**Phân tích:** Generic quoted-string có comma/escape; split thiếu state machine và Map ghi đè duplicated params. Với V1 của bài, **không cho comma/escape trong values** và fixed-order grammar; nếu cần generic HTTP parser thì viết state-machine chuẩn, reject duplicates/unknowns.

### D. “Header chứa keyId=B nhưng dùng secret A; server thử tiếp A”

Client SDK đang rollout key B nhưng vẫn ký bằng A. Verifier lookup B thấy MAC sai rồi thử mọi secret để giúp client.

**Phân tích:** Đây là **key confusion/downgrade**; khi key A revoked, đường fallback có thể cho attacker tiếp tục ký. KeyId được ký và exact lookup chỉ đúng một credential; sai thì `401`. Sửa provisioning/signing SDK chứ không thử secret khác.

### E. “Parser trả clientId là đã authenticated”

Custom filter tạo `UsernamePasswordAuthenticationToken.authenticated(parsed.clientId(),...)` ngay khi regex parse header thành công.

**Phân tích:** Một attacker chỉ cần biết text format để tự khai client ID. Parser chưa kiểm HMAC. Phải đợi MAC, owner/state, timestamp và atomic nonce claim, rồi tạo `VerifiedPrincipal` từ **trusted record**.

### F. “Tự lowercase toàn bộ Authorization để dễ so sánh”

Header value bị gọi `toLowerCase()` để hỗ trợ HMAC/hmac.

**Phân tích:** Chỉ **scheme token** case-insensitive; `clientId`, `keyId`, nonce và Base64url signature là case-sensitive. Lowercase toàn value làm đổi signed input/credential selector và có thể tạo nhầm client. Dùng regex `(?i:HMAC)` trên scheme riêng.

### G. “Không thể đọc JSON body sau khi HMAC filter chạy”

Filter gọi `getInputStream().readAllBytes()` để hash body, rồi controller nhận empty stream.

**Phân tích:** Servlet body là one-shot. Cần bounded capture/replay request wrapper hoặc verify ở trusted ingress; `ContentCachingRequestWrapper` không tự biến stream đã đọc thành replayable stream. Không dùng unbounded read hoặc parse một body khác với body đã được verify.

### H. “Header parse đúng nhưng amount bị đổi ở proxy”

Gateway/client ký original JSON, proxy sau đó reserialize JSON, backend tính SHA-256 theo bytes mới.

**Phân tích:** HMAC mismatch là an toàn hơn accept; nhưng nếu gateway verify trước proxy transform rồi backend thực thi bytes khác, có integrity gap. Chọn một authentication boundary, signed request representation và downstream body integrity/identity assertion đúng contract.

### I. “HMAC verified rồi sao API trả 403?”

Client dùng key B đúng, MAC/time/nonce pass nhưng operation `payments:create` trên account không thuộc merchant.

**Phân tích:** `401` là authentication failure, `403/404` có thể là authorization/resource policy deny. HMAC chỉ xác thực principal nắm shared secret; không cấp quyền trên mọi tài khoản. Không sửa lỗi bằng cấp `ROLE_ADMIN` cho mọi authenticated token.

### J. “Credential store lỗi, bỏ qua HMAC để duy trì availability”

Verifier gặp KMS timeout nên filter gọi `chain.doFilter` để không gián đoạn request.

**Phân tích:** Đây là **fail-open**. Phải giữ protected business route đóng, báo `503`/controlled failure và alert. Không dùng fallback secret hard-coded hoặc tin clientId header khi store không có record.

### K. “Key A hết hạn nhưng cache vẫn chấp nhận”

Key A bị revoked trong secret manager, nhưng gateway giữ record `ACTIVE` cache dài.

**Phân tích:** HMAC vẫn có thể toán học đúng, nhưng credential không còn được phép verify. Revocation phải propagate/invalidate cache, có bounded staleness/SLA và negative canary tests tại các regions; không coi DB update là rotation hoàn tất.

### L. “Đổi key khiến nonce cũ thành hợp lệ”

Client ký request bằng key A với nonce N, rồi bằng key B vẫn giữ N; replay key ở Redis chứa `keyId`.

**Phân tích:** Cùng principal được dùng N hai lần qua hai key namespaces. Với policy per-client, replay key `(environment,verifiedClient,rawNonce)` không chứa KeyId. Retry hợp lệ cần **nonce mới** và HMAC mới, idempotency key cũ giữ nguyên.

### M. “Có idempotency key nên không cần kiểm MAC retry”

Payment đầu đã commit; request retry có `X-Idempotency-Key: pay-903` nên server trả kết quả cache ngay trước HMAC.

**Phân tích:** Attacker đoán idempotency key có thể nhận cached data. Mọi attempt phải xác thực và authorize hiện hành, rồi mới tra/trả idempotency result theo verified principal+operation+key. Key rotation không được tạo namespace idempotency mới cho cùng intent.

### N. “Gateway đã xác minh HMAC, backend tin X-Verified-Client bên ngoài”

Client ngoài gửi `X-Verified-Client: admin`; backend chấp nhận vì nghĩ gateway đã set.

**Phân tích:** Gateway phải strip header tự khai và tạo **authenticated internal assertion** qua trusted channel; backend không được có direct public route hoặc tin string unverified. HMAC gateway success không thay business authorization trên resource.

### O. “Spring Security filter chạy hai lần”

Class filter gắn `@Component` nên Boot tự đăng ký Servlet Filter, đồng thời config `addFilterBefore` cùng filter trong SecurityFilterChain.

**Phân tích:** Lọc hai lần có thể làm nonce lần hai bị reject hoặc xử lý sai route/order. Ví dụ dùng `new HmacAuthenticationFilterV1(adapter)` chỉ trong Security chain; nếu dùng bean thì tắt Servlet auto-registration có chủ đích và integration test `filter invocation count`.

### P. “Đã parse HMAC trong HandlerInterceptor nên khỏi cần filter”

Interceptor gắn `request.setAttribute("clientId",...)` sau khi Spring Security đã cho request đi qua authorization logic.

**Phân tích:** SecurityContext có thể chưa được thiết lập đúng lúc policy quyết định. Đặt authentication trong Spring Security filter/manager đúng thứ tự. Interceptor phục vụ tracing/business instrumentation, không chỉ khai tenant/client ID thành verified identity.

### Q. “Người dùng trình duyệt gửi OPTIONS, custom filter báo 401”

Preflight CORS không có HMAC Authorization; route matcher/filter cấm mọi request, khiến browser client không thể gửi POST.

**Phân tích:** Cần thiết kế CORS ở trusted ingress/Security chain, cho phép preflight **đúng origin/method/header policy** trước authentication nếu sản phẩm thực sự hỗ trợ browser client. Không cho toàn bộ OPTIONS/HEAD bypass authentication cho protected business operations, và không bật `Access-Control-Allow-Origin: *` trên sensitive endpoints tùy tiện.

### R. “Log nguyên Authorization để debug chữ ký”

Khi HMAC mismatch, filter log raw Authorization, secret, canonical body và exception details.

**Phân tích:** Dữ liệu nhạy cảm và replayable request có thể lọt vào log/trace/vendor platform. Dùng sanitized reason codes, verified principal (nếu đã xác thực), trace ID và metrics đã giới hạn cardinality; bảo vệ quyền truy cập log. **Không** log raw secret/full signature/full body.

## 16. Checklist triển khai Authorization trong custom authentication filter

### 16.1. Header syntax và parser

- [ ] Định nghĩa rõ `Authorization` scheme đang hỗ trợ, ví dụ HMAC V1 của bài, **không** nhầm với Basic/Bearer/JWT.
- [ ] Ghi rõ exact grammar, parameter order/spelling, quote/escape, ASCII spacing, case, length limits và policy extension.
- [ ] Chỉ scheme token case-insensitive; ClientId/KeyId/nonce/signature values theo case-sensitive contract.
- [ ] Ingress từ chối duplicated Authorization **trước coalescing**; filter cũng reject multiple servlet-visible values qua `getHeaders()`.
- [ ] Không dùng `getHeader()` để suy uniqueness; không dùng `split(",")` hoặc lưu các params vào Map rồi ghi đè duplicates.
- [ ] Reject Basic/Bearer hoặc malformed/unknown HMAC version ở HMAC-only route, không tự fallback auth scheme cũ.
- [ ] Regex/parser có anchors toàn value, size limit, ASCII grammar và reject CRLF/obs-fold/Unicode confusables.
- [ ] Strict Base64url no-padding: nonce 16 raw bytes/22 chars; signature 32 raw bytes/43 chars và re-encode canonical.
- [ ] Timestamp canonical epoch seconds nằm trong signed `long`, không overflow và không dùng client time làm trusted clock.
- [ ] Header chứa signature/tag và metadata, **không chứa raw shared secret**; không log full Authorization.

### 16.2. Canonical HMAC, lookup và chống replay

- [ ] Parsed `version/clientId/keyId/timestamp/nonce` **được ký**, không coi các giá trị đó đã xác thực chỉ vì parse thành công.
- [ ] Signature output **không được tự đưa vào HMAC input**, tránh vòng lặp.
- [ ] Signed method/path/query/external authority/Content-Type/idempotency key/body digest được định nghĩa nhất quán theo protocol version.
- [ ] Golden fixture body **54 bytes**, SHA-256 `6c4c3379ec4ee31ee77e54f53acff7099c2e5203ecb6c3eea8e5c3a04523a4ee`.
- [ ] Golden A/B đều **13 dòng, 304 UTF-8 bytes**, full HMAC-SHA256/Base64url tag khớp independent oracle.
- [ ] Body được capture có **size bound**, vừa dùng tính MAC vừa được controller xử lý **đúng exact bytes**, không dùng input stream đã cạn.
- [ ] Không giả định `ContentCachingRequestWrapper` tự cho đọc lại body sau khi filter đọc trước; phải có replayable strategy.
- [ ] Trusted external authority/URI được lấy ở ingress boundary an toàn, không tùy tiện tin public `X-Forwarded-Host`/`X-Original-URI`.
- [ ] Credential lookup theo đúng environment/client/key (và tenant nếu cần), owner/state/algorithm/notBefore/expiry từ trusted store.
- [ ] Sai MAC **không** thử key khác, global secret hoặc thuật toán yếu hơn.
- [ ] HMAC tag raw 32 bytes được so qua `MessageDigest.isEqual` sau strict decode, không truncated tag hoặc text compare.
- [ ] Signed timestamp được kiểm tra trước atomic nonce claim; nonce store shared across replicas/regions.
- [ ] Replay key theo verified principal, không reset chỉ vì key ID thay đổi trong rotation.
- [ ] TTL nonce bao phủ past tolerance, future skew và safety margin; store unavailable/unknown claim result fail-closed.
- [ ] Revoked credential không được xác thực qua cache stale/restore backup; có negative canaries đa gateway.

### 16.3. Spring Security và authorization

- [ ] Authentication đặt trong Spring Security `SecurityFilterChain`, không chỉ trong HandlerInterceptor.
- [ ] `OncePerRequestFilter` chỉ gán SecurityContext sau credential/HMAC/freshness/nonce **đầy đủ**.
- [ ] Filter không gọi `chain.doFilter` trên authentication failure hoặc infrastructure outage.
- [ ] `SecurityContextHolder` được tạo mới và clear `finally`, tránh rò giữa requests/threads.
- [ ] `401` generic cho missing/malformed/bad MAC/revoked/replay; `503` cho KMS/store unavailable; `403/404` cho authorization deny.
- [ ] `WWW-Authenticate` challenge tương thích HMAC contract nếu dùng; response không lộ secret/known-key state.
- [ ] Không cấp roles/scopes theo `clientId`/`keyId`/`role` trong header; dùng trusted authorization policy.
- [ ] Stateless/session/CSRF policy áp đúng HMAC-only route, không blanket disable CSRF cho cookie-backed phần khác.
- [ ] CORS preflight/OPTIONS và async/error dispatch có policy rõ; không bypass protected business methods.
- [ ] Filter được đăng ký đúng **một lần** trong ordered chains; tránh `@Component` auto Servlet registration + `addFilterBefore` trùng.
- [ ] Các API không được HMAC chain match phải có security chain/policy khác, không có endpoint lọt khỏi bảo vệ.
- [ ] HMAC hợp lệ chưa đủ để thanh toán từ resource khác owner: authorization theo principal/action/resource ở tầng business.
- [ ] Idempotency được kiểm tra sau authn/authz; same business intent retry giữ idempotency key, thay nonce/timestamp/HMAC.
- [ ] Payment provider/DB side effects có transaction/unique business references/reconciliation, không kỳ vọng nonce một mình bảo đảm exactly-once.

### 16.4. Gateway, test và observability

- [ ] Header names ở HTTP/1.1/2/3 được xử lý case-insensitive; values được giữ nguyên semantics.
- [ ] Reverse proxy không strip/merge/chọn first Authorization rồi âm thầm đổi principal downstream.
- [ ] Gateway→backend verified identity đi qua authenticated internal assertion, không tin `X-Verified-Client` tự khai từ Internet.
- [ ] Backend direct access bị chặn hoặc thực hiện authentication tương đương.
- [ ] Key rotation/revocation, nonce state, idempotency và authorization duy trì consistency qua failover/DR.
- [ ] Raw-wire tests bao phủ duplicate Authorization, quoted params, Host/:authority, URI normalization, request body rewrite và header injection.
- [ ] Unit tests chứng minh parser strict, golden A/B, wrong KeyId/ClientId, stale timestamp, replay và bad MAC không claim nonce.
- [ ] Spring integration tests chứng minh `401/403/503`, context cleanup, chain order, filter count, CORS/async và **zero unauthorized business side effects**.
- [ ] Logs/traces không chứa raw shared secret, full signature, full Authorization hoặc sensitive body; metric labels có cardinality giới hạn.
- [ ] Đã có incident runbook cho leaked HMAC secret, KMS downtime, gateway misrouting và lost nonce state.
- [ ] Release gate yêu cầu **parse valid không tương đương authenticated**, và **authenticated không tương đương authorized**.

## 17. Bài tập thực hành tổng hợp

### 17.1. Chỉ đổi casing của scheme

Header V1 đang đúng, client đổi `HMAC` thành `hmac`, giữ nguyên mọi tham số và tag.

**Đáp án:** Parser vẫn nhận vì scheme case-insensitive; golden HMAC không đổi vì canonical input dùng **parsed fields** và domain prefix V1, không dùng scheme casing. Nếu lowercase `clientId`/`keyId` hay Base64url tag, contract case-sensitive sẽ bị thay và không còn cùng credential/MAC.

### 17.2. Reverse proxy đã drop duplicated Authorization

Một request public có hai Authorization lines; proxy chỉ forward dòng đầu, backend `getHeaders()` thấy đúng một.

**Đáp án:** Servlet filter không thể biết occurrence đã bị proxy xóa; bắt buộc đặt **raw-wire duplicate rejection tại ingress**. Application strict parser là defense in depth, không thay thế gateway validation.

### 17.3. Key A→B nhưng reuse nonce

Client đã gửi `nonce=N` với key A và được chấp nhận. Khi chuyển key B, client ký lại bằng B với N, HMAC mới hoàn toàn đúng.

**Đáp án:** Replay store scope theo verified client nên lần thứ hai bị reject. Retry hợp lệ cần nonce mới và HMAC mới; nếu cùng payment intent, **idempotency key không đổi**.

### 17.4. HMAC đúng nhưng account khác owner

`merchant-42` có MAC/time/nonce hợp lệ nhưng body ghi account của `merchant-73`.

**Đáp án:** Filter có thể xác thực thành công merchant-42, nhưng authorization nghiệp vụ phải reject, không có side effect. `isAuthenticated()` không chứng minh quyền trên resource.

### 17.5. HMAC store timeout

Secret manager/KMS hoặc shared nonce store mất kết nối trong lúc verify.

**Đáp án:** Filter phải fail-closed, trả `503`/controlled service error và không gọi controller. Không dùng cached default secret/hard-coded key hay tự tin ClientId header.

### 17.6. Filter đọc request body trước controller

Filter dùng `request.getInputStream().readAllBytes()` để hash, rồi controller nhận body rỗng.

**Đáp án:** Không đọc body không giới hạn và không dùng one-shot stream mà không có replay strategy. Cần bounded, Servlet-compatible replayable wrapper hoặc verify ở ingress đáng tin; test controller nhận **exact signed bytes**.

### 17.7. Client đưa thêm `X-Role: admin`

HMAC header đúng, client gửi một header không được ký `X-Role: admin` và backend cấp quyền admin.

**Đáp án:** Đây là lỗi authorization. Dù header `X-Role` có được ký hay không, việc client tự khai role **không cấp quyền**; phải kiểm tra trusted policy/delegation.

### 17.8. Tiêu chí tự đánh giá

Người học cần tự giải thích được tại sao `getHeader()` chưa kiểm uniqueness, vì sao scheme khác parameter values, tại sao cần strict V1 grammar, khi nào parser trả `Credentials` nhưng chưa có `Authentication`, và tại sao body được hash phải giống body thực thi. Về kỹ thuật, người học tái tạo đúng **13-line/304-byte** canonical input, hai golden HMAC tags, rồi chứng minh invalid Authorization, failed MAC, replay hoặc store outage đều **không đi tới business**.

**Kết luận:** *Đọc authorization header* trong custom HMAC filter là một **security boundary**, không phải thao tác tách chuỗi đơn thuần. Server phải đọc đúng một field, phân biệt auth scheme và parse theo versioned grammar có giới hạn; `clientId/keyId/timestamp/nonce` phải được ràng buộc với canonical request. Chỉ khi verifier chọn đúng shared secret, xác minh **raw HMAC, freshness và atomic nonce claim**, Spring Security mới được tạo verified principal. Gateway/proxy, body stream và filter ordering phải được kiểm thử đồng bộ; **authorization, resource ownership và idempotency vẫn là các bước độc lập** sau xác thực.






