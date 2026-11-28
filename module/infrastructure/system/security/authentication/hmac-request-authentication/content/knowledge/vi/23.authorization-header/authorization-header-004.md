# Signed headers field trong Authorization header khi xác thực HMAC

> **Chương:** Authorization header  
> **Bài học:** Signed headers field — xác định chính xác những HTTP headers nào tham gia vào canonical request và được chữ ký HMAC bảo vệ.  
> **Phạm vi:** `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION` — xây dựng xác thực HTTP request bằng shared secret và canonical request chứa method, URI, signed headers hoặc body theo hợp đồng; chống replay bằng timestamp/nonce, key rotation, kiểm thử proxy/gateway và phân biệt xác thực với phân quyền.

## 1. SignedHeaders là gì và giải quyết vấn đề nào?

Một HTTP request mang nhiều headers, nhưng không phải header nào cũng có ý nghĩa như nhau. Có header dùng để định tuyến, header quyết định cách đọc body, header định danh client, header chứa timestamp/nonce, và header do proxy tự bổ sung. Khi xác thực HMAC, server phải biết **chính xác những field nào đã được client ký**.

Một profile minh họa sử dụng HTTP `Authorization` với custom authentication scheme:

```http
POST /v1/transfers?mode=commit HTTP/1.1
Host: payments.example.test
Content-Type: application/json
X-Timestamp: 1795800000
X-Nonce: QW7TqnhFEcB7hKrLNZ5IQA
X-Idempotency-Key: transfer-101
Authorization: HMAC-SHA256 Credential="partner-01/key-2026-11", SignedHeaders="content-type;host;x-idempotency-key;x-nonce;x-timestamp", Signature="<base64url-hmac-tag>"

{"transferId":"transfer-101","amountMinorUnits":100000}
```

Trong header `Authorization`, ba tham số minh họa có vai trò:

| Tham số | Ý nghĩa | Quy tắc bảo mật |
| --- | --- | --- |
| `Credential` | Client ID và key ID để server chọn shared secret | **Được ràng buộc vào canonical bytes**, không phải bằng chứng nhận dạng khi chưa xác minh MAC |
| `SignedHeaders` | Danh sách **tên HTTP headers** tham gia HMAC | Phải canonical, đúng bộ bắt buộc, không cho client âm thầm bỏ header nhạy cảm |
| `Signature` | Tag HMAC-SHA256 ở dạng Base64URL không padding | Decode thành bytes và so với MAC do server tính |

`SignedHeaders` **không phải một HTTP header độc lập** trong ví dụ. Nó là **tham số của trường HTTP `Authorization`**. Nói “signed headers field” ở đây tức danh sách định danh những field được đưa vào phép ký, không đồng nghĩa việc ký nguyên văn toàn bộ header `Authorization`.

**Đây là signing profile tự thiết kế cho mục đích học tập**, không phải định dạng chuẩn áp dụng cho mọi dịch vụ. Một số hệ thống như AWS Signature Version 4 có khái niệm `SignedHeaders` riêng, nhưng không được tùy tiện dùng cú pháp/thuật toán của chúng thay cho hợp đồng API hiện tại.

### 1.1 Vì sao không ký “mọi header”?

Một số header có thể thay đổi khi request đi qua HTTP stack:

- `Connection`, `Keep-Alive`, `Transfer-Encoding` và các *hop-by-hop headers*;
- `Content-Length` khi proxy đổi cách truyền hoặc giải nén;
- `User-Agent`, `Via`, tracing/correlation headers;
- Các header được CDN, API gateway hoặc load balancer thêm vào;
- Các header thể hiện cùng ngữ nghĩa nhưng có biểu diễn khác theo HTTP/1.1 và HTTP/2.

Ký không chọn lọc làm client/server thường xuyên tạo MAC khác nhau vì hạ tầng thay đổi những field không liên quan nghiệp vụ.

### 1.2 Vì sao không chỉ ký body?

Nếu chỉ ký raw JSON body:

```text
HMAC(secret, SHA256(body))
```

attacker có thể tìm cách đổi `POST` thành method khác, thay target, `Host`, Content-Type, timestamp, tenant/operation header hoặc nonce. HMAC vẫn có thể khớp nếu các trường đó **không nằm trong canonical bytes**, dẫn tới sai ngữ cảnh xác thực.

**SignedHeaders giúp ràng buộc những metadata quan trọng vào tag**, còn method, URI và body hash vẫn được ký riêng theo signing contract.

### 1.3 Mục tiêu học tập

Sau bài này, người học cần:

1. Hiểu khác biệt giữa `Authorization` header, tham số `SignedHeaders` và các HTTP headers thực tế được ký.
2. Thiết kế danh sách required/optional signed headers không cho phép *header stripping* hoặc *unsigned-header confusion*.
3. Canonicalize header names/values theo quy tắc **cụ thể, có version**.
4. Ràng buộc `SignedHeaders` và `Credential` vào HMAC để không bị sửa bằng tag cũ.
5. Phát hiện header thiếu, trùng tên khác casing, multi-value, whitespace và CRLF injection.
6. Kiểm thử HTTP/1.1 `Host` với HTTP/2 `:authority` qua proxy/gateway.
7. Triển khai và kiểm thử signer/verifier Java 17 có timestamp, nonce, key policy và anti-replay.

## 2. Cấu trúc Authorization header: có gì được ký?

Profile `hmac-signedheaders-v1` minh họa:

```text
Authorization: HMAC-SHA256 Credential="<clientId>/<keyId>", SignedHeaders="<semicolon-separated-names>", Signature="<base64url-tag>"
```

Ví dụ giá trị:

```text
HMAC-SHA256 Credential="partner-01/key-2026-11", SignedHeaders="content-type;host;x-idempotency-key;x-nonce;x-timestamp", Signature="bVd8...example..."
```

Chuỗi `bVd8...example...` chỉ để minh họa, **không phải chữ ký Base64URL hợp lệ**. Khi kiểm thử thực, phải thay bằng tag 32 bytes được HMAC-SHA256 tính và encode thành **43 ký tự Base64URL không padding**.

### 2.1 Grammar minh họa, không áp dụng đoán mò

Một grammar **cố định** giúp tránh việc client, gateway và verifier phân tích một header theo nhiều cách:

```text
authorization-value =
    "HMAC-SHA256 Credential=\"" credential "\", "
    "SignedHeaders=\"" signed-header-names "\", "
    "Signature=\"" signature-base64url "\""

credential = client-id "/" key-id
client-id = 1..64 ký tự ASCII [A-Za-z0-9._-]
key-id = 1..64 ký tự ASCII [A-Za-z0-9._-]

signed-header-names =
    "content-type;host;x-idempotency-key;x-nonce;x-timestamp"

signature-base64url = chính xác 43 ký tự [A-Za-z0-9_-]
```

Đây là **một dạng cú pháp hẹp do API chọn**, không phải toàn bộ grammar của HTTP authentication framework. Những dịch vụ khác có thể dùng tên scheme, parameter order, token/quoted-string và escaping khác; không được cho phép các biến thể đó khi profile hiện tại không định nghĩa.

Theo profile trên, verifier phải từ chối:

- Scheme khác, chẳng hạn `Bearer`, `Basic` hoặc `HMAC` không đúng tên.
- Thiếu `Credential`, `SignedHeaders` hoặc `Signature`.
- Parameter bị lặp, đảo thứ tự, chèn dấu phẩy, thêm spaces hoặc escape quotes khác format đã quy định.
- Client/key ID không đúng grammar hoặc không thuộc policy.
- Header `Authorization` xuất hiện nhiều lần, kể cả khi tên khác casing.
- Tag sai alphabet, sai độ dài, padding hoặc decode không canonical.

**Không nên viết `authorization.split(",")` một cách tùy tiện** khi một grammar rộng hơn có thể chứa quoted-string hoặc escape. Với profile hẹp của bài, có thể dùng **một parser/regex đã anchor chính xác toàn bộ chuỗi**; với grammar phức tạp hơn cần parser đúng chuẩn/cấu trúc rõ.

### 2.2 Tại sao không ký toàn bộ chuỗi Authorization?

Nếu chuỗi Authorization chứa `Signature=<tag>`, lấy toàn bộ nó làm input HMAC sẽ tạo **phụ thuộc vòng**: cần biết tag để dựng input, nhưng phải có input mới tính được tag.

Cách giải quyết:

- **Không** đưa chính giá trị `Signature` vào canonical message.
- Đưa **Credential và SignedHeaders** (đã parse/validate) vào canonical message như những trường được ràng buộc.
- Dùng các **HTTP header values thực tế** tương ứng SignedHeaders để dựng các dòng canonical.
- Đưa method, target, audience, body digest và profile version vào message.
- Tính MAC rồi mới xây chuỗi Authorization cuối cùng.

Đây là một cách thiết kế; nhiều giao thức khác dùng tên credential scope hoặc format canonical khác. Điều không thay đổi là **không để lựa chọn field ký có thể bị sửa ngoài phạm vi MAC**.

## 3. Chọn tập signed headers: bảo mật quan trọng hơn linh hoạt tùy ý

Profile bài học yêu cầu **đúng năm headers**:

```text
content-type;host;x-idempotency-key;x-nonce;x-timestamp
```

Danh sách này là **lowercase ASCII**, **sắp theo thứ tự byte từ điển tăng dần**, ngăn cách bằng dấu `;`, **không có khoảng trắng**, không trùng. Bản thân chuỗi danh sách cũng xuất hiện trong canonical request.

| Header | Tại sao ký? | Chú ý |
| --- | --- | --- |
| `content-type` | Quyết định diễn giải raw body | Profile chọn chính xác `application/json` |
| `host` | Ràng buộc authority đích | HTTP/2 cần mapping `:authority` đúng policy |
| `x-idempotency-key` | Ràng buộc business operation khi retry | Retry cùng nghiệp vụ giữ key này |
| `x-nonce` | Ràng buộc một signed attempt, chống sửa nonce | Base64URL 16 random bytes, server claim một lần |
| `x-timestamp` | Ràng buộc thời điểm ký để giới hạn replay window | Unix epoch seconds strict |

Ngoài năm header này, **method, raw target, profile, audience và body digest cũng được ký** nhưng không nằm trong `SignedHeaders` vì chúng **không phải HTTP field names** trong danh sách.

### 3.1 Danh sách do client khai không được quyết định chính sách bảo vệ

Một thiết kế sai:

```text
Server:
  fields = Authorization.SignedHeaders
  verify only fields listed by client
  accept when MAC matches
```

Nếu client giữ secret nhưng không đáng tin ở mức chính sách, nó có thể ký request bỏ `x-nonce` hoặc `x-timestamp` và yêu cầu server chỉ xác minh hai headers khác. Khi đó cơ chế replay bị bypass **bằng một request được ký hợp lệ**.

Server phải:

1. Có **policy bắt buộc** về tên headers với từng endpoint/signing profile.
2. Kiểm tra tất cả field bắt buộc thực sự xuất hiện một lần.
3. Kiểm tra `SignedHeaders` đúng tập policy; với profile của bài còn phải đúng **thứ tự canonical**.
4. Không nhận field name ngoài allowlist nếu có thể tác động vào xác thực/nghiệp vụ.
5. Không bỏ kiểm tra signed timestamp/nonce chỉ vì client gửi một danh sách ngắn hơn.

Trong một profile hỗ trợ optional signed headers, có thể cho một superset được cho phép, nhưng **bộ bắt buộc vẫn không thể bị loại** và mỗi thêm/bớt làm thay đổi canonical bytes/signature. Điều kiện cho phép phải được thiết kế/kiểm thử với semantics của backend; không được tự áp dụng mô hình optional vào profile fixed-list đang dùng.

### 3.2 Một trường nghiệp vụ không ký có thể phá toàn bộ bảo vệ

Giả sử backend dựa trên:

```http
X-Tenant-Id: tenant-A
```

nhưng trường này **không** nằm trong signed headers, không được suy ra từ principal đáng tin và không bị gateway cố định. Attacker có thể sửa nó sang `tenant-B` mà MAC trên các trường còn lại vẫn đúng.

Có hai thiết kế an toàn:

- Đưa `x-tenant-id` vào required signed headers và ràng buộc authorization với principal/tenant; hoặc
- Không tin giá trị client gửi, mà suy tenant từ client identity đã xác thực và server-side policy.

**Một trường không ký không mặc nhiên là field có thể tin dùng**. Trường không ảnh hưởng quyết định bảo mật hoặc nghiệp vụ có thể được bỏ khỏi signed set, nhưng phải được phân loại có chủ đích.

### 3.3 Không tự chọn SignedHeaders từ mọi header có mặt

Một sai lầm ở client:

```text
signedHeaders = sort(allPresentRequestHeaders())
```

Header của HTTP client có thể được thêm sau khi signer chạy: `Content-Length`, `User-Agent`, trace context hoặc proxy metadata. Nếu signer dựa vào “mọi header hiện có” mà request trên wire khác, server sẽ tính canonical khác.

**Chốt signed field allowlist trước khi dựng request**, tạo các giá trị đã ký một lần, và bảo đảm chính các values đó đi tới verifier. Mọi thay đổi hạ tầng vào trường đã ký phải được xử lý ở trust boundary hoặc từ chối.

## 4. Header names: lowercase ASCII và sắp thứ tự ổn định

HTTP field names **không phân biệt hoa/thường**. Các tên sau cùng chỉ một field name về ngữ nghĩa:

```http
Content-Type: application/json
content-type: application/json
CONTENT-TYPE: application/json
```

Signing profile có thể normalize **tên** thành ASCII lowercase:

```text
Content-Type       -> content-type
HOST               -> host
X-Idempotency-Key  -> x-idempotency-key
X-Nonce            -> x-nonce
X-Timestamp        -> x-timestamp
```

Nhưng phải **không** tự lowercase values hoặc Unicode text.

### 4.1 Sắp xếp SignedHeaders

Danh sách canonical của bài:

```text
content-type;host;x-idempotency-key;x-nonce;x-timestamp
```

Vì chỉ dùng ASCII lowercase và dấu `-`, phép sắp xếp ordinal theo bytes đã được định nghĩa ổn định giữa Java, Go, Python, Node.

Không dùng locale-specific collation cho field names; không tự thay `-` bằng `_`, không đổi hoa/thường bằng thuật toán Unicode khi chưa validate token ASCII.

### 4.2 Không bỏ qua tên trùng chỉ vì khác casing

Request:

```http
X-Nonce: QW7TqnhFEcB7hKrLNZ5IQA
x-nonce: AAAAAAAAAAAAAAAAAAAAAA
```

Nếu verifier lấy giá trị đầu mà backend lấy giá trị sau, chữ ký có thể được xác minh cho **nonce khác nonce được xử lý**.

Profile của bài **từ chối mọi duplicate signed field**, kể cả:

- Trùng tên đúng casing.
- Hai tên chỉ khác hoa/thường.
- Một framework trả về danh sách nhiều values.
- Gateway gộp thành chuỗi comma-separated khi field không có quy tắc list semantics tương ứng.

Không có quy tắc phổ quát rằng mọi HTTP header có thể gộp bằng dấu phẩy. Với `Authorization` và các trường `x-nonce`/`x-timestamp` của bài, phải yêu cầu **chính xác một giá trị**.

## 5. Header values: canonicalize rõ ràng, tránh parser differential

HTTP field name và field value có các quy tắc khác nhau. Có thể lowercase tên `Content-Type`, nhưng **không thể mặc định lowercase giá trị** hoặc biến đổi Unicode tùy ý.

Profile minh họa quy định cho năm signed header values:

1. Dữ liệu trong profile là **ASCII in được** (`U+0020` đến `U+007E`).
2. Từ chối `CR`, `LF`, `NUL`, các control characters, `DEL`, Unicode non-ASCII và tab `HTAB` trong **giá trị signed fields** của profile.
3. Loại bỏ **ASCII space U+0020** ở đầu/cuối.
4. Chuẩn hóa mỗi chuỗi nhiều spaces U+0020 bên trong thành **một** space.
5. Giá trị cuối cùng không được rỗng, phải qua validation của header đó.
6. Backend phải sử dụng cùng giá trị ngữ nghĩa sau canonicalization, không một raw value khác với verifier.
7. Nếu một field khác đòi hỏi quoted-string, structured fields hoặc byte values phức tạp, phải tạo **profile canonicalization riêng**.

Ví dụ:

```text
"   application/json   " -> "application/json"
"transfer-101"          -> "transfer-101"
"transfer  101"         -> "transfer 101" (nhưng bị idempotency grammar từ chối)
"\ttransfer-101"        -> REJECT (tab bị cấm theo profile)
"part\r\nX-Role:admin"  -> REJECT (CR/LF injection)
```

Vì năm values đều bị ràng buộc bởi grammar nghiêm ngặt, đa số khoảng trắng nội bộ sẽ bị validation từ chối. Quy tắc canonical spaces vẫn được nêu cụ thể để không có hai implementation tự chọn khác nhau.

### 5.1 Vì sao không gọi `String.trim()` rồi coi là đủ?

`String.trim()`, `strip()`, `replaceAll("\\s+", " ")` và parser HTTP có thể xử lý nhiều loại whitespace khác nhau. Với dữ liệu ký, phải định nghĩa **đúng ký tự nào** bị loại/giữ.

Trong profile này, chỉ ASCII space `0x20` được trim/collapse. Tab bị từ chối, thay vì silently normalize. Điều này tránh client chấp nhận một variant mà proxy/backend giải thích khác.

### 5.2 Header value chứa dấu phẩy hoặc nhiều values

Một số HTTP fields là danh sách hợp lệ, một số không. Với profile hiện tại, `Content-Type`, `Host`, timestamp, nonce và idempotency key đều phải cung cấp **một giá trị canonical duy nhất**.

```http
X-Timestamp: 1795800000, 1795800001
```

Phải từ chối vì không khớp grammar timestamp, **không chọn phần tử đầu hoặc cuối**.

Một profile khác muốn ký header list-value (ví dụ `Accept`) phải định nghĩa chính xác cách parse, ordering, quotes, repeated lines và canonical formatting. Không copy logic gộp dấu phẩy từ header khác mà thiếu specification.

### 5.3 Header values Unicode

Không nên cho phép text Unicode tự do trong một field value rồi giả định HTTP/1.1, HTTP/2, Java Servlet và gateway đều giữ nguyên UTF-8. HTTP header field values có grammar và ràng buộc wire-format riêng.

Nếu nghiệp vụ cần ký Unicode text, chọn một trường ứng dụng có biểu diễn ASCII được quy định hoặc ký raw JSON body/canonical JSON bytes theo hợp đồng. **Không dùng `new String(headerBytes, UTF_8)` và tự động replacement malformed data** làm canonicalization bảo mật.

## 6. Host, authority và HTTP/2: dễ ký sai qua gateway

Ở HTTP/1.1 client thường gửi:

```http
Host: payments.example.test
```

Trong HTTP/2, authority thường xuất hiện dưới dạng pseudo-header:

```text
:authority = payments.example.test
:method    = POST
:path      = /v1/transfers?mode=commit
:scheme    = https
```

**Không được mặc định ký nguyên văn pseudo-header `:authority` như một HTTP field tên `host`**. Signing profile cần quy tắc đưa các trường HTTP/1.1 và HTTP/2 về **canonical authority** tương ứng.

Profile của bài quy định:

- Canonical signed field `host` đại diện cho **authority đích đáng tin**, ở ví dụ là `payments.example.test`.
- Ở HTTP/1.1, adapter kiểm tra `Host` đúng grammar, một giá trị duy nhất.
- Ở HTTP/2, adapter kiểm tra `:authority` và các giá trị Host khác nếu hiện diện theo protocol; từ chối mâu thuẫn/nhập nhằng.
- Gateway bảo vệ trust boundary, chuyển đúng authority đã xác minh tới canonicalizer.
- Demo Java 17 dùng một `Host` tổng hợp để tập trung vào field signing, **không tự cài HTTP/2 parser**.

### 6.1 Port mặc định, tên miền, IPv6

```text
payments.example.test
payments.example.test:443
PAYMENTS.EXAMPLE.TEST
[2001:db8::1]:8443
```

Các biểu diễn có thể tương đương trong một số ngữ cảnh URL, nhưng **không được tự xem là cùng chuỗi ký**. Nếu profile cho phép default-port normalization, host case normalization, IDNA/punycode hoặc IPv6 formatting, phải định nghĩa thuật toán/version, kiểm thử cùng HTTP stack và tránh Host-header injection.

Profile ví dụ đơn giản: chỉ chấp nhận đúng `payments.example.test`, không chấp nhận tự thêm `:443` hay đổi case để tránh suy đoán.

### 6.2 Proxy tự đổi Host

Nếu client ký `payments.example.test` nhưng reverse proxy chuyển request tới `backend.internal` và thay `Host`, verifier ở backend có thể nhận authority khác và tính MAC sai.

Các hướng thiết kế:

1. **Xác minh trước rewrite** tại gateway tin cậy.
2. Gateway truyền canonical authority qua kênh nội bộ được bảo vệ, không tin một `X-Forwarded-Host` do client ngoài tự gửi.
3. Xác minh lại hoặc tạo signature mới giữa gateway và backend bằng identity/key riêng nếu có thay đổi cần thiết.

Không âm thầm bỏ `host` khỏi `SignedHeaders` chỉ vì gateway khó cấu hình: cần xác định host có ảnh hưởng đến routing, tenant, audience và chính sách authorization hay không.

## 7. Định dạng canonical request có danh sách SignedHeaders

Một hợp đồng tự chứa `hmac-signedheaders-v1` định nghĩa:

```text
hmac-signedheaders-v1
payments-api-prod
partner-01/key-2026-11
POST
/v1/transfers?mode=commit
content-type;host;x-idempotency-key;x-nonce;x-timestamp
content-type:application/json
host:payments.example.test
x-idempotency-key:transfer-101
x-nonce:QW7TqnhFEcB7hKrLNZ5IQA
x-timestamp:1795800000
<sha256-lowercase-hex-of-raw-body-bytes>
```

Quy tắc đầy đủ:

1. Các dòng 1–2 là profile version và audience được server policy cho phép.
2. Dòng 3 là **Credential** đã parse từ `Authorization`; đây là giá trị được ràng buộc vào HMAC, không phải bí mật.
3. Method và raw target đã được xác định ở một trust boundary; profile demo yêu cầu đúng `POST` và `/v1/transfers?mode=commit`.
4. Dòng `SignedHeaders` xuất hiện **nguyên dạng canonical** như đã validate.
5. Mỗi header name ở SignedHeaders tạo một dòng `lowercase-name:canonical-value`, đúng thứ tự danh sách.
6. Values không chứa CR/LF, nên ranh giới dòng không bị nhập nhằng.
7. Cuối cùng là SHA-256 digest dạng **64 ký tự hex chữ thường** của raw body bytes.
8. Mọi dòng được nối bằng **một LF `0x0A`**, encode UTF-8, **không có LF cuối và không có BOM**.
9. Tag được tính bằng HMAC-SHA256 với shared secret thuộc đúng client/key/audience/profile.
10. Tag 32 bytes encode Base64URL không padding thành 43 ký tự trong `Signature`.

```text
bodyDigestHex = lowercase_hex(SHA256(rawBodyBytes))
signedHeaderNames = "content-type;host;x-idempotency-key;x-nonce;x-timestamp"

canonicalText = joinWithLF(
    version, audience, credential, method, rawTarget,
    signedHeaderNames,
    "content-type:" + canonical(contentType),
    "host:" + canonical(authority),
    "x-idempotency-key:" + canonical(idempotencyKey),
    "x-nonce:" + canonical(nonce),
    "x-timestamp:" + canonical(timestamp),
    bodyDigestHex
)

expectedTag = HMAC_SHA256(secret, UTF8(canonicalText))
authorizationSignature = BASE64URL_NO_PADDING(expectedTag)
```

**Điểm bảo mật quan trọng:** `SignedHeaders` **và** các dòng header values đều có trong canonical bytes. Nếu attacker thay tên hoặc giá trị bất kỳ mà giữ tag, server phải từ chối.

### 7.1 Vì sao không ký nguyên cả `Authorization`?

`Credential` và `SignedHeaders` được đưa vào canonical text như **dữ liệu đầu vào**, trong khi `Signature` là **kết quả đầu ra**; không tạo vòng lặp. Server dùng Credential chỉ để **chọn candidate key thuộc policy**, rồi xác thực bằng MAC trước khi coi client đã được chứng thực.

### 7.2 SignedHeaders không bao gồm raw body

Raw body bytes được ràng buộc qua `bodyDigestHex`. Nếu body JSON bị đổi `amountMinorUnits` nhưng SignedHeaders vẫn giống, digest đổi → canonical bytes đổi → MAC cũ không khớp.

Không được tự re-serialize JSON trước khi hash nếu profile quy định ký raw bytes. Để body có nghĩa giống nhau sau whitespace/property ordering được ký giống nhau, cần một JSON canonicalization protocol **riêng**, version và kiểm thử cross-language.

### 7.3 Cần tránh nhầm lẫn header với dữ liệu authority/path

`host` là HTTP field được ký, method và raw target là những trường riêng của canonical request. HTTP/2 pseudo headers không nhất thiết tương ứng 1:1 với cấu trúc HTTP/1.1. Phải có adapter đúng profile trước khi xây canonical bytes.

## 8. Tấn công khi SignedHeaders được xử lý không đúng

### 8.1 Bỏ x-nonce khỏi danh sách

Một signer có shared secret nhưng cố gửi:

```text
SignedHeaders="content-type;host;x-idempotency-key;x-timestamp"
```

Nếu server chấp nhận bộ field tự chọn, nonce có thể không được ký. Attacker có thể thay nonce của request cũ hoặc một client bị lỗi có thể bỏ replay control.

**Chính sách an toàn của bài:** verifier so danh sách với **chuỗi required cố định**; thiếu `x-nonce` → từ chối ngay, dù có thể tính được một HMAC cho tập field còn lại.

### 8.2 Bỏ x-timestamp

Nếu client ký nonce nhưng timestamp không được bảo vệ, attacker có thể sửa `X-Timestamp` thành thời gian mới để kéo dài hạn request. Đây là lỗi binding. Chọn required set có cả `x-timestamp` và kiểm tra time window sau MAC.

### 8.3 SignedHeaders có duplicate

```text
SignedHeaders="content-type;host;host;x-idempotency-key;x-nonce;x-timestamp"
```

Danh sách trùng name không được chấp nhận. Nếu parser A giữ duplicate còn parser B dùng Map loại duplicate, kết quả ký/xử lý có thể chênh lệch. Profile yêu cầu **đúng thứ tự và đúng năm tên**.

### 8.4 Case/whitespace biến thể

```text
SignedHeaders="Content-Type;Host;X-Nonce"
SignedHeaders="content-type; host;x-nonce"
SignedHeaders="x-timestamp;x-nonce;host;content-type;x-idempotency-key"
```

Profile từ chối vì danh sách không canonical, không đủ required set hoặc sai order. **Tên HTTP header trong request** vẫn có thể dùng casing khác, nhưng **chuỗi SignedHeaders** phải đúng lowercase/sorted.

### 8.5 Thêm unsigned header điều khiển quyền

```http
X-Role: admin
X-Tenant-Id: tenant-other
X-HTTP-Method-Override: DELETE
```

Nếu backend tin những trường này mà chúng không được ký hoặc cố định bằng policy tin cậy, attacker có thể thay semantics mà HMAC không đổi.

Profile bài học **không cho những headers ngoài tập đã định ảnh hưởng nghiệp vụ**; demo Java từ chối mọi field ngoài `Authorization` và năm signed fields. Production có thể cho phép `User-Agent`/trace headers không nhạy cảm, nhưng phải có allowlist và chặn các trường điều khiển identity, routing hoặc authorization.

### 8.6 Nhầm SignedHeaders với key rotation

Nếu client thay `Credential="partner-01/key-2026-11"` thành key khác, server không được thử ngẫu nhiên các secrets cho đến khi một tag khớp. Credential được ràng buộc vào canonical bytes; resolver phải kiểm tra key ID thuộc đúng client, audience, profile và còn hiệu lực.

**MAC hợp lệ không thể thay thế authorization theo resource/tenant.** Client có key hợp lệ nhưng thiếu quyền vẫn phải bị backend từ chối.

## 9. Java 17: signer và verifier có SignedHeaders field

Bài thực hành bên dưới dùng **chỉ JDK 17** và các HTTP request **mô phỏng bằng record**, không mở kết nối mạng. Lý do: để tập trung vào canonical signed headers, ta cần quan sát chính xác từng field trước khi cho framework HTTP tự rewrite.

Chương trình minh họa:

- Authorization grammar cố định, bao gồm `Credential`, `SignedHeaders` và `Signature`.
- Lowercase field names; reject duplicate header names khác casing và multi-value.
- Canonical header values theo quy tắc ASCII space; từ chối CR/LF, tab và Unicode ngoài profile.
- Required list `content-type;host;x-idempotency-key;x-nonce;x-timestamp`, **không chấp nhận client bỏ một field**.
- Bind `Credential` và `SignedHeaders` vào HMAC-SHA256.
- Kiểm tra tag Base64URL no padding và dùng `MessageDigest.isEqual`.
- Timestamp/nonce đã ký, replay store in-memory chỉ để mô phỏng.
- Kiểm thử sửa signed value, sửa danh sách, đổi key ID, gửi trùng header, exact replay và timestamp hết hạn.

**Giới hạn cố ý:** không có HTTP server/parsing, không có HTTP/2 adapter, không có Redis TTL hoặc business authorization. Những phần đó được thảo luận riêng, không được coi demo là mã production.

Lưu thành `SignedHeadersDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.HexFormat;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SignedHeadersDemo {
    private static final String PROFILE = "hmac-signedheaders-v1";
    private static final String AUDIENCE = "payments-api-prod";
    private static final String CREDENTIAL =
            "partner-01/key-2026-11";
    private static final String METHOD = "POST";
    private static final String TARGET =
            "/v1/transfers?mode=commit";
    private static final String HOST = "payments.example.test";
    private static final String REQUIRED =
            "content-type;host;x-idempotency-key;"
            + "x-nonce;x-timestamp";
    private static final String ALGORITHM = "HmacSHA256";
    private static final long PAST = 300;
    private static final long FUTURE = 60;

    private static final Set<String> SIGNED = Set.of(
            "content-type", "host", "x-idempotency-key",
            "x-nonce", "x-timestamp");

    // Đây là grammar HẸP của profile demo, không phải
    // parser tổng quát cho mọi Authorization scheme.
    private static final Pattern AUTH = Pattern.compile(
            "^HMAC-SHA256 Credential=\""
            + "([A-Za-z0-9._-]{1,64}/[A-Za-z0-9._-]{1,64})"
            + "\", SignedHeaders=\""
            + "([a-z0-9-]+(?:;[a-z0-9-]+)*)"
            + "\", Signature=\"([A-Za-z0-9_-]{43})\"$");

    private SignedHeadersDemo() {}

    enum Result {
        ACCEPTED, BAD_FORMAT, BAD_AUTHORIZATION,
        BAD_CREDENTIAL, BAD_SIGNATURE, EXPIRED,
        FUTURE_TIMESTAMP, REPLAY, STORE_UNAVAILABLE
    }

    static final class StoreFailure extends Exception {
        StoreFailure(String reason) {
            super(reason);
        }
    }

    interface ReplayStore {
        boolean claimOnce(String key) throws StoreFailure;
    }

    // Chỉ để minh họa trong một JVM; không TTL/durability.
    static final class DemoReplayStore implements ReplayStore {
        private final Set<String> claimed =
                ConcurrentHashMap.newKeySet();

        @Override
        public boolean claimOnce(String key) {
            return claimed.add(key);
        }
    }

    // Record snapshot: header map và body không thay đổi sau ký.
    public record WireRequest(
            String method,
            String rawTarget,
            Map<String, List<String>> headers,
            byte[] body) {

        public WireRequest {
            if (headers == null) {
                throw new IllegalArgumentException("Missing headers");
            }
            Map<String, List<String>> copy =
                    new LinkedHashMap<>();
            for (Map.Entry<String, List<String>> e
                    : headers.entrySet()) {
                if (e.getKey() == null || e.getValue() == null) {
                    throw new IllegalArgumentException("Null header");
                }
                copy.put(e.getKey(), List.copyOf(e.getValue()));
            }
            headers = Collections.unmodifiableMap(copy);
            body = body == null ? null : body.clone();
        }

        @Override
        public byte[] body() {
            return body == null ? null : body.clone();
        }
    }

    record AuthorizationParts(
            String credential, String signedHeaders,
            String signature) {}

    static Map<String, String> singleHeaders(WireRequest r) {
        Map<String, String> normalized = new LinkedHashMap<>();

        for (Map.Entry<String, List<String>> e
                : r.headers().entrySet()) {
            String sourceName = e.getKey();
            if (!sourceName.matches("[A-Za-z0-9-]{1,64}")) {
                throw new IllegalArgumentException(
                        "Invalid header name");
            }
            String name = sourceName.toLowerCase(Locale.ROOT);
            if (!name.equals("authorization")
                    && !SIGNED.contains(name)) {
                // Profile này chỉ mô phỏng 6 headers.
                // Server thật cho phép header khác khi an toàn.
                throw new IllegalArgumentException(
                        "Unsigned field not allowed");
            }
            if (e.getValue().size() != 1
                    || e.getValue().get(0) == null
                    || normalized.containsKey(name)) {
                throw new IllegalArgumentException(
                        "Duplicate or missing header value");
            }
            normalized.put(name, e.getValue().get(0));
        }
        return normalized;
    }

    static AuthorizationParts parseAuthorization(String value) {
        if (value == null) {
            throw new IllegalArgumentException("Missing Authorization");
        }
        Matcher matcher = AUTH.matcher(value);
        if (!matcher.matches()) {
            throw new IllegalArgumentException("Invalid Authorization");
        }
        return new AuthorizationParts(
                matcher.group(1), matcher.group(2), matcher.group(3));
    }

    // Chỉ cho ASCII printable; trim/collapse ASCII SPACE.
    static String canonicalValue(String raw) {
        if (raw == null || raw.length() > 1024) {
            throw new IllegalArgumentException("Bad header value size");
        }
        StringBuilder canonical = new StringBuilder();
        boolean pendingSpace = false;

        for (int i = 0; i < raw.length(); i++) {
            char c = raw.charAt(i);
            if (c < 0x20 || c > 0x7E) {
                // Reject CR/LF, HTAB, DEL và non-ASCII.
                throw new IllegalArgumentException(
                        "Unsupported header character");
            }
            if (c == ' ') {
                if (canonical.length() > 0) {
                    pendingSpace = true;
                }
                continue;
            }
            if (pendingSpace) {
                canonical.append(' ');
                pendingSpace = false;
            }
            canonical.append(c);
        }
        if (canonical.length() == 0) {
            throw new IllegalArgumentException("Blank header value");
        }
        return canonical.toString();
    }

    static boolean validNonce(String nonce) {
        if (nonce == null
                || !nonce.matches("[A-Za-z0-9_-]{22}")) {
            return false;
        }
        try {
            byte[] raw = Base64.getUrlDecoder().decode(nonce);
            return raw.length == 16
                    && Base64.getUrlEncoder().withoutPadding()
                            .encodeToString(raw).equals(nonce);
        } catch (IllegalArgumentException malformed) {
            return false;
        }
    }

    static byte[] canonicalBytes(
            WireRequest request, AuthorizationParts authorization)
            throws GeneralSecurityException {
        if (request == null
                || !METHOD.equals(request.method())
                || !TARGET.equals(request.rawTarget())
                || !CREDENTIAL.equals(authorization.credential())
                || !REQUIRED.equals(authorization.signedHeaders())
                || request.body() == null
                || request.body().length == 0
                || request.body().length > 1_048_576) {
            throw new IllegalArgumentException("Invalid signed fields");
        }

        Map<String, String> headers = singleHeaders(request);
        Map<String, String> values = new LinkedHashMap<>();
        for (String name : REQUIRED.split(";")) {
            String value = headers.get(name);
            if (value == null) {
                throw new IllegalArgumentException(
                        "Missing signed header: " + name);
            }
            values.put(name, canonicalValue(value));
        }

        if (!"application/json".equals(values.get("content-type"))
                || !HOST.equals(values.get("host"))
                || !values.get("x-idempotency-key")
                        .matches("[A-Za-z0-9._-]{1,80}")
                || !values.get("x-timestamp")
                        .matches("[1-9][0-9]{9,11}")
                || !validNonce(values.get("x-nonce"))) {
            throw new IllegalArgumentException(
                    "Invalid signed header semantics");
        }

        String bodyHashHex = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                        .digest(request.body()));

        List<String> lines = new ArrayList<>();
        lines.add(PROFILE);
        lines.add(AUDIENCE);
        lines.add(authorization.credential());
        lines.add(request.method());
        lines.add(request.rawTarget());
        lines.add(authorization.signedHeaders());

        for (String name : REQUIRED.split(";")) {
            lines.add(name + ":" + values.get(name));
        }
        lines.add(bodyHashHex);

        return String.join("\n", lines)
                .getBytes(StandardCharsets.UTF_8);
    }

    static byte[] hmac(byte[] secret, byte[] message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(new SecretKeySpec(secret, ALGORITHM));
        return mac.doFinal(message);
    }

    static String newNonce(SecureRandom random) {
        byte[] bytes = new byte[16];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    static String authorizationHeader(String signature) {
        return "HMAC-SHA256 Credential=\"" + CREDENTIAL
                + "\", SignedHeaders=\"" + REQUIRED
                + "\", Signature=\"" + signature + "\"";
    }

    static WireRequest signForDemo(
            byte[] secret, byte[] body, Clock clock,
            SecureRandom random, String idempotencyKey)
            throws GeneralSecurityException {
        Map<String, List<String>> headers = new LinkedHashMap<>();
        headers.put("Host", List.of(HOST));
        headers.put("Content-Type", List.of("application/json"));
        headers.put("X-Idempotency-Key", List.of(idempotencyKey));
        headers.put("X-Nonce", List.of(newNonce(random)));
        headers.put("X-Timestamp", List.of(
                Long.toString(clock.instant().getEpochSecond())));

        WireRequest draft = new WireRequest(
                METHOD, TARGET, headers, body);
        AuthorizationParts unsigned =
                new AuthorizationParts(CREDENTIAL, REQUIRED, "");

        String signature = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(hmac(
                        secret, canonicalBytes(draft, unsigned)));

        headers.put("Authorization",
                List.of(authorizationHeader(signature)));
        return new WireRequest(METHOD, TARGET, headers, body);
    }

    static Result verify(
            byte[] resolvedSecret, WireRequest request,
            Clock clock, ReplayStore store)
            throws GeneralSecurityException {
        if (resolvedSecret == null || resolvedSecret.length < 32
                || request == null || clock == null || store == null) {
            return Result.BAD_FORMAT;
        }

        final Map<String, String> headers;
        try {
            headers = singleHeaders(request);
        } catch (IllegalArgumentException badWireHeaders) {
            return Result.BAD_FORMAT;
        }

        final AuthorizationParts auth;
        try {
            auth = parseAuthorization(headers.get("authorization"));
        } catch (IllegalArgumentException badAuth) {
            return Result.BAD_AUTHORIZATION;
        }

        // Demo giả lập resolver chỉ chấp nhận một Credential.
        // Production: resolver theo client/key/audience/profile.
        if (!CREDENTIAL.equals(auth.credential())) {
            return Result.BAD_CREDENTIAL;
        }
        if (!REQUIRED.equals(auth.signedHeaders())) {
            return Result.BAD_AUTHORIZATION;
        }

        final byte[] provided;
        try {
            provided = Base64.getUrlDecoder().decode(
                    auth.signature());
        } catch (IllegalArgumentException invalidTag) {
            return Result.BAD_AUTHORIZATION;
        }
        if (provided.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(provided)
                        .equals(auth.signature())) {
            return Result.BAD_AUTHORIZATION;
        }

        final byte[] expected;
        try {
            expected = hmac(
                    resolvedSecret, canonicalBytes(request, auth));
        } catch (IllegalArgumentException invalidSignedFields) {
            return Result.BAD_FORMAT;
        }

        if (!MessageDigest.isEqual(expected, provided)) {
            return Result.BAD_SIGNATURE;
        }

        // Signed timestamp và nonce lấy từ chính header đã ký.
        long signedAt = Long.parseLong(
                canonicalValue(headers.get("x-timestamp")));
        long now = clock.instant().getEpochSecond();

        long oldest;
        long newest;
        try {
            oldest = Math.subtractExact(now, PAST);
            newest = Math.addExact(now, FUTURE);
        } catch (ArithmeticException overflow) {
            return Result.BAD_FORMAT;
        }

        if (signedAt < oldest) {
            return Result.EXPIRED;
        }
        if (signedAt > newest) {
            return Result.FUTURE_TIMESTAMP;
        }

        String nonce = canonicalValue(headers.get("x-nonce"));
        String replayKey = "hmac-replay:v1:" + AUDIENCE
                + ":partner-01:" + nonce;
        try {
            return store.claimOnce(replayKey)
                    ? Result.ACCEPTED
                    : Result.REPLAY;
        } catch (StoreFailure unavailable) {
            return Result.STORE_UNAVAILABLE;
        }
    }

    static WireRequest replaceHeader(
            WireRequest source, String name, String value) {
        Map<String, List<String>> headers =
                new LinkedHashMap<>(source.headers());
        headers.put(name, List.of(value));
        return new WireRequest(
                source.method(), source.rawTarget(),
                headers, source.body());
    }

    static String header(WireRequest request, String name) {
        return singleHeaders(request).get(name);
    }

    public static void main(String[] args) throws Exception {
        SecureRandom rng = new SecureRandom();
        byte[] secret = new byte[32];
        rng.nextBytes(secret);

        Clock clock = Clock.fixed(
                Instant.parse("2026-11-28T02:00:00Z"),
                ZoneOffset.UTC);
        byte[] body = (
                "{\"transferId\":\"transfer-101\","
                + "\"amountMinorUnits\":100000}"
        ).getBytes(StandardCharsets.UTF_8);

        WireRequest first = signForDemo(
                secret, body, clock, rng, "transfer-101");
        DemoReplayStore store = new DemoReplayStore();

        System.out.println("First: "
                + verify(secret, first, clock, store));
        System.out.println("Exact replay: "
                + verify(secret, first, clock, store));

        // Đổi signed idempotency key nhưng giữ signature.
        WireRequest changedValue = replaceHeader(
                first, "X-Idempotency-Key", "transfer-102");
        System.out.println("Tampered signed value: "
                + verify(secret, changedValue, clock, store));

        // Đổi SignedHeaders nhưng giữ tag cũ.
        String oldAuth = header(first, "authorization");
        String changedList = oldAuth.replace(
                "SignedHeaders=\"" + REQUIRED + "\"",
                "SignedHeaders=\"content-type;host;x-nonce;x-timestamp\"");
        WireRequest missingField = replaceHeader(
                first, "Authorization", changedList);
        System.out.println("Removed required signed field: "
                + verify(secret, missingField, clock, store));

        // Header có hai tên khác casing nhưng cùng ý nghĩa.
        Map<String, List<String>> duplicated =
                new LinkedHashMap<>(first.headers());
        duplicated.put("x-nonce",
                List.of(header(first, "x-nonce")));
        WireRequest duplicateNonce = new WireRequest(
                first.method(), first.rawTarget(),
                duplicated, first.body());
        System.out.println("Duplicate nonce header: "
                + verify(secret, duplicateNonce, clock, store));

        // Kiểm tra field name không phân biệt casing.
        Map<String, List<String>> recased =
                new LinkedHashMap<>(first.headers());
        String v = recased.remove("X-Idempotency-Key").get(0);
        recased.put("x-idempotency-key", List.of(v));
        WireRequest sameHeaderDifferentCase = new WireRequest(
                first.method(), first.rawTarget(),
                recased, first.body());
        System.out.println("Header name casing normalized: "
                + verify(secret, sameHeaderDifferentCase,
                        clock, new DemoReplayStore()));

        // Sửa Credential sang key ID không thuộc policy.
        String changedCredential = oldAuth.replace(
                "partner-01/key-2026-11",
                "partner-01/key-2026-10");
        WireRequest wrongKey = replaceHeader(
                first, "Authorization", changedCredential);
        System.out.println("Unrecognized key ID: "
                + verify(secret, wrongKey, clock, store));

        // Ký hợp lệ một timestamp đã quá hạn.
        WireRequest expired = signForDemo(
                secret, body,
                Clock.offset(clock, Duration.ofSeconds(-301)),
                rng, "transfer-101");
        System.out.println("Expired but valid HMAC: "
                + verify(secret, expired, clock, store));

        WireRequest retry = signForDemo(
                secret, body, clock, rng, "transfer-101");
        System.out.println("Re-signed new attempt: "
                + verify(secret, retry, clock, store));

        ReplayStore unavailable = key -> {
            throw new StoreFailure("timeout");
        };
        WireRequest forFailure = signForDemo(
                secret, body, clock, rng, "transfer-101");
        System.out.println("Replay store unavailable: "
                + verify(secret, forFailure, clock, unavailable));
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac -encoding UTF-8 SignedHeadersDemo.java
java SignedHeadersDemo
```

Kết quả kỳ vọng về **verdict**, giá trị nonce/signature thay đổi ở mỗi lần chạy:

```text
First: ACCEPTED
Exact replay: REPLAY
Tampered signed value: BAD_SIGNATURE
Removed required signed field: BAD_AUTHORIZATION
Duplicate nonce header: BAD_FORMAT
Header name casing normalized: ACCEPTED
Unrecognized key ID: BAD_CREDENTIAL
Expired but valid HMAC: EXPIRED
Re-signed new attempt: ACCEPTED
Replay store unavailable: STORE_UNAVAILABLE
```

### 9.1 Vì sao những test này có ý nghĩa?

- Thay `X-Idempotency-Key` thành một value khác vẫn đúng grammar, nhưng canonical bytes thay đổi → MAC cũ bị từ chối.
- Xóa `x-idempotency-key` khỏi `SignedHeaders` không chỉ làm MAC khác; nó còn **vi phạm required-set policy**.
- Hai tên `X-Nonce` và `x-nonce` không tạo hai fields khác nhau; adapter phải phát hiện duplicate.
- Đổi casing của tên header **không** làm canonical name đổi, nên request mới vẫn được xác thực (dùng store mới để không vướng replay).
- Đổi `Credential` phải đi qua key policy trước khi MAC; demo từ chối key ID không được phép.
- Signed timestamp hết hạn vẫn có HMAC hợp lệ nhưng bị time gate từ chối.
- Replay nguyên request có MAC đúng nhưng nonce đã claim; retry ký mới được phép qua lớp anti-replay, sau đó vẫn cần idempotency nghiệp vụ.
- Replay store không xác định kết quả phải **fail closed**.

### 9.2 Các giả định của mã demo

Mã không thể thay thế toàn bộ HTTP server:

1. `WireRequest` là dữ liệu mô phỏng; production phải có adapter HTTP/1.1 và HTTP/2 đúng với trust boundary.
2. Demo chỉ chấp nhận **đúng năm signed fields và một Authorization**; server thật phải xử lý an toàn các header bổ sung, framing, Host/:authority và hop-by-hop semantics.
3. `DemoReplayStore` không có TTL, không chia sẻ multi-instance, không durable và không giải quyết multi-region failover.
4. Credential và key ID được cố định; production cần key resolver, chính sách rotation/revocation và phân biệt principals.
5. Demo không parse JSON/schema, không kiểm tra duplicate JSON keys, không thực hiện business authorization hay idempotency store.
6. Ví dụ canonicalizes ASCII spaces theo profile; production phải bảo đảm handler sử dụng **đúng giá trị đã được xác minh**.
7. Không nên gửi request đã ký chứa dữ liệu nhạy cảm qua HTTP plaintext; TLS và quản lý secret an toàn vẫn là yêu cầu độc lập.

## 10. Khi nào SignedHeaders cho phép optional headers?

Một số hệ thống cần ký thêm `x-tenant-id`, `x-operation-mode`, `content-encoding` hoặc một header nghiệp vụ khác ở một số routes.

Có hai cách có chủ đích:

### 10.1 Fixed signed set (dễ kiểm toán)

```text
Required == SignedHeaders
```

Đây là chính sách của bài học. Tất cả requests thuộc một signing profile phải ký đúng tập header, giúp hạn chế chọn field tùy ý và giảm biến thể canonical.

Ưu điểm: đơn giản, dễ tạo golden vectors, chống header omission. Nhược điểm: thay đổi endpoint có thể cần profile mới nếu bộ field nghiệp vụ thay đổi.

### 10.2 Required set + allowed optional set

```text
required = {content-type, host, x-nonce, x-timestamp}
optionalAllowed = {x-idempotency-key, x-tenant-id}

policy:
  required ⊆ signedHeaderNames
  signedHeaderNames ⊆ required ∪ optionalAllowed
  unsigned fields affecting behavior must be rejected or ignored
```

Cách này chỉ an toàn khi **semantics từng endpoint** xác định rõ header nào bắt buộc. Nếu `POST /transfers` cần idempotency key, `x-idempotency-key` phải nằm trong required set cho route đó, không thể chỉ là optional.

Danh sách optional cũng phải canonical sorting, unique, có giới hạn số field/bytes, và **toàn bộ danh sách phải được MAC bảo vệ**.

### 10.3 Đổi danh sách phải đổi profile hay không?

Không phải mọi thay đổi tập optional đều cần version mới nếu profile đã định nghĩa cú pháp và chính sách theo route, nhưng thay đổi **cách parse/normalize header**, bắt buộc một header mới hoặc đổi trust boundary **có thể phá tương thích**. Cần phân tích versioning, golden vectors, SDK rollout và downgrade trước khi triển khai.

Không thêm fallback kiểu “thử danh sách hiện tại, không được thì thử một danh sách cũ” mà không có policy và thời hạn chuyển tiếp rõ; điều đó tăng nguy cơ header stripping hoặc signature confusion.

## 11. SignedHeaders và anti-replay: phải ký timestamp + nonce

Trong bài, `x-timestamp` và `x-nonce` là hai field bắt buộc. Chúng có vai trò khác nhau:

- Timestamp đã ký giới hạn tuổi request.
- Nonce đã ký nhận diện một network attempt.
- Replay store dùng nonce đã chứng thực để chặn request đã dùng.

### 11.1 Cửa sổ timestamp minh họa

`X-Timestamp` là Unix epoch seconds, chuỗi decimal canonical:

```text
[1-9][0-9]{9,11}
```

Server chấp nhận:

\[
now - 300 \le signedAt \le now + 60.
\]

Nếu quá cũ hoặc quá xa tương lai, request phải bị từ chối **ngay cả khi MAC đúng**. Đồng hồ `now` là wall clock của server, không phải thời gian do client hoặc proxy tự khai.

### 11.2 Nonce uniqueness và TTL

Nonce trong profile mã hóa 16 bytes do `SecureRandom` sinh, Base64URL không padding dài 22 ký tự. Không dùng `Random` hay timestamp làm nguồn nonce vì profile yêu cầu tính khó dự đoán và xác suất trùng rất thấp.

Server kiểm tra nonce **sau khi MAC và time hợp lệ**, bằng atomic insert-if-absent trên replay store dùng chung.

Ví dụ:

```redis
SET hmac-replay:v1:payments-api-prod:partner-01:<nonce> 1 NX EX 420
```

Với `PAST=300` giây và `FUTURE=60` giây, một request được nhận sớm nhất lúc `signedAt-60` và muộn nhất lúc `signedAt+300`: khoảng tối đa **360 giây** tính từ lần nhận sớm nhất. TTL `420` trong ví dụ có thêm 60 giây margin, chỉ phù hợp nếu kiến trúc đã đánh giá clock skew, TTL precision và failure modes.

Redis `SET NX EX` atomic trên một primary nhưng không mặc nhiên durable qua failover với replication bất đồng bộ hoặc consistent giữa nhiều primary/regions. Các nghiệp vụ nhạy cảm cần đánh giá store consistency và transaction/idempotency riêng.

### 11.3 Thứ tự kiểm tra

```mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant V as HMAC verifier
    participant R as Replay store
    participant B as Business handler
    C->>C: Chọn SignedHeaders required
    C->>C: Tạo timestamp + nonce; canonical; HMAC
    C->>G: Authorization + các signed headers + body
    G->>V: Forward tại trust boundary
    V->>V: Parse Authorization, required headers, canonical
    V->>V: Resolve key, verify HMAC
    alt MAC không khớp / format không đạt
        V-->>C: Từ chối
    else MAC hợp lệ
        V->>V: Kiểm tra signed timestamp
        V->>R: Atomic claim signed nonce
        alt Nonce trùng hoặc store lỗi
            V-->>C: Từ chối
        else Claim NEW
            V->>B: Authenticated principal + verified request
            B->>B: Authorization và idempotency
        end
    end
```

**Không claim nonce trước MAC**: attacker có thể gửi nonce giả để làm đầy hoặc chiếm replay store. Nếu store timeout hoặc không chắc kết quả claim, không chạy nghiệp vụ (*fail closed*).

## 12. SignedHeaders và retry an toàn

Khi response của một request đã ký bị mất, client không thể suy ra server đã xử lý hay chưa. Mọi attempt mới cần:

- Method/target/body/idempotency key **giữ nguyên** cho cùng operation.
- Timestamp mới phù hợp với thời gian gửi; có thể cùng giây khi retries nhanh.
- Nonce **mới** sinh bằng CSPRNG.
- Chữ ký **mới**, vì timestamp/nonce nằm trong SignedHeaders.
- Key ID có thể thay nếu rotate key nhưng phải dùng secret/key ID còn hiệu lực.
- Danh sách `SignedHeaders` vẫn tuân thủ profile được phép.

```text
Attempt A:
  X-Timestamp=T1
  X-Nonce=N1
  X-Idempotency-Key=transfer-101
  Signature=M1

Attempt B:
  X-Timestamp=T2
  X-Nonce=N2  (mới)
  X-Idempotency-Key=transfer-101  (giữ nguyên)
  Signature=M2  (tính lại từ canonical bytes)
```

**Không gửi lại nguyên Authorization header và nonce cũ** rồi gọi đó là retry an toàn. Nếu server đã claim N1, request đó bị replay store từ chối. Một attempt mới N2 có thể qua anti-replay, nhưng business idempotency store phải ngăn việc chuyển tiền hai lần.

Business idempotency key **không phải nonce**; same operation phải giữ key ổn định, trong khi nonce thay theo attempt.

## 13. Kiểm thử proxy/gateway và các ranh giới tin cậy

| Thành phần/hop | Rủi ro với SignedHeaders | Kiểm thử cần có |
| --- | --- | --- |
| Java HTTP client | Tự thêm/sửa Content-Type hoặc Host | Header value thực trên wire khớp canonical |
| Reverse proxy | Rewrite `Host` hoặc path | Verifier ở đúng boundary; authority mapping chuẩn |
| HTTP/2 gateway | `:authority` ↔ `Host`; lowercase header names | Cùng canonical field `host`, không nhập nhằng |
| CDN | Tự thêm tracing/`Via` headers | Không ảnh hưởng signed set; field mới không điều khiển security |
| Gateway retries | Gửi lại cùng Authorization/nonce | Replay store từ chối; policy retry ở tầng signer |
| Middleware | Merge duplicate `X-Nonce` | Reject duplicate tại hop còn quan sát được |
| JSON handler | Parse/serialize body lần nữa | Digest raw body bytes đúng payload handler dùng |
| Compression | Decompress gzip hoặc thay Content-Encoding | Profile xác định body bytes/encoding rõ |
| Key resolver | Propagation chậm trong rotation | Client/key/audience/profile policy nhất quán |
| Multi-region | Replay store không chia sẻ, key state drift | Global uniqueness/failover theo threat model |
| Backend authorization | Tin `X-Tenant-Id` unsigned | Dùng principal/verified field, không tin ngoài hợp đồng |

### 13.1 Kiểm tra ngay cả khi chỉ đổi casing

Một request HTTP/2 thường dùng lowercase field names. Nếu client ký `Content-Type` và backend thấy `content-type`, danh sách SignedHeaders canonical vẫn phải ổn định. Nhưng nếu **cả hai field xuất hiện như duplicate**, phải reject chứ không coi là hai fields khác.

### 13.2 Host và X-Forwarded-Host không đồng nghĩa

Không để client ngoài gửi:

```http
Host: payments.example.test
X-Forwarded-Host: other-tenant.example.test
```

rồi verifier ký Host nhưng backend dùng `X-Forwarded-Host` không đáng tin để định tuyến tenant. Gateway phải strip/recreate forwarded headers theo trust policy hoặc backend bỏ qua dữ liệu đó.

### 13.3 Signed headers có thể bị framework thay đổi thứ tự trên wire

**Thứ tự xuất hiện của các header lines trên wire không cần là thứ tự SignedHeaders**. Canonicalizer phải thu thập, validate và sắp xếp theo danh sách đã được ký, không phụ thuộc thứ tự mà HTTP library gửi.

Điều phải cố định là **danh sách tên và cách tạo từng canonical header line**, không phải vị trí thực tế của header trong HTTP message.

## 14. Kiểm thử âm tính: bắt lỗi header stripping và canonicalization

| Ca kiểm thử | Đầu vào/thao tác | Kết quả cần đạt |
| --- | --- | --- |
| Đầy đủ five required headers | Authorization hợp lệ, HMAC đúng | Qua MAC; tiếp tục time/nonce |
| Thiếu `x-nonce` trong SignedHeaders | Danh sách rút gọn | Từ chối policy |
| Thiếu `x-timestamp` | Danh sách không đủ | Từ chối policy |
| Thiếu `x-idempotency-key` | Danh sách không đủ | Từ chối policy |
| Thay thứ tự SignedHeaders | Tên giống nhưng order khác | Từ chối danh sách không canonical |
| Tên header viết hoa trong SignedHeaders | `Content-Type` | Từ chối theo grammar lowercase |
| Hai tên trùng trong SignedHeaders | `host;host` | Từ chối |
| Thay value Content-Type | `application/json` → `text/plain` | Từ chối format/MAC |
| Thay idempotency key | String mới đúng grammar, tag cũ | BAD_SIGNATURE |
| Thay timestamp | Timestamp mới đúng grammar, tag cũ | BAD_SIGNATURE |
| Thay nonce | Nonce mới đúng grammar, tag cũ | BAD_SIGNATURE |
| Thay Host | Host khác, tag cũ | Từ chối validation/MAC |
| Đổi casing của header name | `X-Nonce` → `x-nonce` | Vẫn canonical giống nhau |
| Duplicate name khác casing | Cả `X-Nonce` và `x-nonce` | Từ chối duplicate |
| Duplicate Authorization | Hai Authorization values | Từ chối |
| Header gộp comma | `X-Timestamp: t1,t2` | Từ chối grammar |
| CRLF injection | Value chứa `\r\nX-Role: admin` | Từ chối control characters |
| Tab/Unicode ở signed value | Outside profile ASCII printable | Từ chối |
| Extra spaces đầu/cuối | `"  transfer-101  "` | Canonical trim SP theo policy; handler dùng cùng value |
| Multiple internal spaces | Grammar của field không cho | Từ chối sau canonicalization |
| Optional header không được phép | `X-Tenant-Id` ảnh hưởng quyền | Từ chối hoặc bỏ qua theo policy; demo từ chối |
| Thay Credential | Key ID khác, tag cũ | Key policy từ chối hoặc MAC sai |
| Tag padding `=` | Base64URL padding không cho phép | Từ chối |
| Tag hex thay Base64URL | Sai encoding | Từ chối |
| Body JSON reformat | Raw bytes khác, tag cũ | MAC không khớp |
| Timestamp đã hết hạn nhưng HMAC mới đúng | Client ký time cũ | Time gate từ chối |
| Exact replay | Gửi lại cùng Authorization/nonce | Replay store từ chối |
| Retry ký mới | Nonce/signature mới, same operation key | Qua anti-replay, business idempotency xét tiếp |
| Store lỗi | Nonce claim timeout | Fail closed |
| Host rewrite qua proxy | Client/server canonical authority khác | MAC fail hoặc rewrite được hợp đồng xử lý |
| HTTP/2/HTTP/1.1 | `:authority`/`Host` được mapping | Cùng canonical semantics đã định |
| Authorization đúng nhưng tenant sai quyền | Principal không có quyền resource | Authorization nghiệp vụ từ chối |

### 14.1 Golden vectors cần ghi lại bytes, không chỉ text

```text
profile: hmac-signedheaders-v1
algorithm: HmacSHA256
test_secret_hex: <32-byte-test-key>
audience: payments-api-prod
credential: partner-01/key-2026-11
method: POST
raw_target: /v1/transfers?mode=commit
signed_headers: content-type;host;x-idempotency-key;x-nonce;x-timestamp
canonical_header_1: content-type:application/json
canonical_header_2: host:payments.example.test
canonical_header_3: x-idempotency-key:transfer-101
canonical_header_4: x-nonce:<fixed-22-char-base64url>
canonical_header_5: x-timestamp:<fixed-epoch-seconds>
raw_body_utf8_hex: <exact-json-bytes>
body_digest_hex: <64-lowercase-hex>
canonical_request_utf8_hex: <exact-bytes>
hmac_tag_hex: <64-lowercase-hex>
signature_base64url: <43-char-tag>
authorization_header: <exact-value>
```

Các giá trị `<...>` chỉ là placeholders, **không phải vector đã tính**. Khi tạo test vector thật, chọn fixed secret/nonce/timestamp **chỉ trong test**, tính digest và tag với implementation độc lập, đối chiếu giữa Java/Go/Node/Python và thử biến đổi gateway.

### 14.2 Kiểm thử âm tính nên báo lỗi ở đúng lớp

Nếu sửa `X-Timestamp` nhưng giữ tag, kết quả đúng là **BAD_SIGNATURE** trước khi có thể kết luận timestamp expired (giả sử format vẫn hợp lệ). Muốn test time window, phải **ký thật** một request mang timestamp đã cũ bằng secret thử nghiệm.

Nếu xóa `x-nonce` khỏi `SignedHeaders`, kết quả phải là **BAD_AUTHORIZATION / POLICY_REJECTED**, không cố tính MAC với tập thiếu để “cứu tương thích”.

## 15. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Khắc phục |
| --- | --- | --- |
| Tin `SignedHeaders` do client tự chọn | Client có key bỏ field bắt buộc | Required-set policy và ký chính danh sách |
| Chỉ ký values, không ký names/list | Header confusion/stripping | Canonical name:value và SignedHeaders trong MAC |
| Ký nguyên `Authorization` gồm Signature | Phụ thuộc vòng | Chỉ bind Credential + SignedHeaders, không bind Signature |
| Sắp header theo thứ tự xuất hiện | Client/server order khác | Canonical sorted names |
| Lowercase cả header values | Đổi nội dung application | Chỉ normalize name; value theo profile |
| Dùng Unicode whitespace normalization tùy tiện | Parser differential | Quy tắc ASCII SP cụ thể và reject controls |
| Cho phép duplicate headers | Verifier/backend chọn khác | Reject duplicate tại ingress |
| Tin `X-Forwarded-Host` từ client | Host/tenant spoofing | Gateway strip/recreate và trust boundary |
| Ký hop-by-hop headers không ổn định | MAC mismatch qua proxy | Chọn stable fields và adapter semantics |
| Bỏ Host vì gateway rewrite | Signature có thể dùng sai authority | Giải quyết mapping/trust, ký audience/authority phù hợp |
| Body digest không dựa trên raw bytes | Signer/verifier/hash khác handler | Dùng đúng bytes theo hợp đồng |
| Thử nhiều key/format đến khi MAC khớp | Downgrade, key confusion | Resolve đúng key/profile policy |
| Timestamp/nonce không signed | Có thể sửa để né replay | Required SignedHeaders và time/nonce gate |
| Replay store không atomic hoặc không chia sẻ | Exact replay qua instance khác | Shared atomic claim + TTL/consistency |
| Idempotency key không signed | Attacker đổi business operation | Required header và business fingerprint |
| MAC đúng ⇒ có quyền | Client vượt tenant/resource | Authorization độc lập |

## 16. Code review checklist cho SignedHeaders

Khi review một triển khai API Java/Spring/Servlet:

1. **Profile:** scheme, version, audience, algorithm, tag encoding/length có được định nghĩa chặt?
2. **Credential:** client ID/key ID có được bind trong MAC và resolve qua policy đang active?
3. **SignedHeaders:** required set và optional set có được định nghĩa theo endpoint?
4. **Header parser:** có reject duplicate Authorization, signed headers và các tên khác casing?
5. **Names:** có lowercase ASCII và sort ordinal theo contract?
6. **Values:** canonical whitespace, CRLF rejection, encoding và single-value semantics có nhất quán với backend?
7. **Authority:** Host/HTTP/2 :authority được mapping như thế nào tại gateway?
8. **Method/URI:** raw target, percent-encoding, query duplicates có được xử lý theo đúng contract?
9. **Body:** raw bytes/canonical JSON và Content-Encoding được ràng buộc thế nào?
10. **MAC:** có dùng `Mac.getInstance("HmacSHA256")` và so tag bytes bằng `MessageDigest.isEqual`?
11. **Replay:** timestamp và nonce đã ký, time window chặt, atomic nonce claim và fail closed?
12. **Rotation:** key ID/version/algorithm policy có ngăn downgrade và giữ scope nonce phù hợp?
13. **Rights:** client giữ secret có bị kiểm tra action/tenant/resource trước khi xử lý?
14. **Idempotency:** retries dùng nonce mới nhưng business key ổn định, tránh side effect lặp?
15. **Gateway:** HTTP/1.1/HTTP/2, proxy rewrite, auto retry, forwarded headers, request smuggling đã được kiểm thử?
16. **Observability:** không log shared secret, expected MAC, raw Authorization signature hay body nhạy cảm?
17. **Interoperability:** có golden vectors bytes cụ thể và negative tests cross-language?

**Review note:** Việc verifier chạy thành công với một SDK duy nhất **chưa chứng minh** canonicalization tương thích qua proxy hoặc chặn toàn bộ header confusion. Kiểm thử âm tính quan trọng ngang test happy path.

## 17. Bài tập thực hành

**Bài 1 — SignedHeaders cơ bản:** Viết canonical headers cho HTTP request với `Content-Type`, `Host`, `X-Timestamp`, `X-Nonce` và `X-Idempotency-Key`. Sắp tên lowercase theo đúng thứ tự, ghép dòng `name:value`, thêm profile/audience/method/target/body digest.

**Bài 2 — Header stripping:** Sửa `SignedHeaders` để bỏ `x-nonce` nhưng giữ tag cũ. Chứng minh verifier theo profile fixed-set từ chối ở policy trước khi claim nonce.

**Bài 3 — Optional policy:** Thiết kế profile cho endpoint `POST /v1/transfers` có thêm `x-tenant-id` bắt buộc và endpoint `GET /v1/status` chỉ cần một số field. Làm rõ route-specific required set và không cho client tùy ý bỏ field có ảnh hưởng quyền.

**Bài 4 — Case-insensitive name:** Ký với `X-Timestamp` rồi gửi với `x-timestamp`. Vì sao MAC có thể giữ đúng? Nếu cả hai xuất hiện thì tại sao phải từ chối?

**Bài 5 — Whitespace/CRLF:** Thử value `"  application/json  "`, tab, CRLF và non-ASCII. So sánh canonical output theo profile, phân tích sự nhất quán giữa server verifier và business handler.

**Bài 6 — HTTP/2 :authority:** Thiết kế adapter lấy `:authority` và ánh xạ sang canonical `host`. Thử Host/:authority mâu thuẫn và proxy rewrite tới internal hostname.

**Bài 7 — HMAC binding:** Thay `X-Idempotency-Key` hoặc `Content-Type` sau ký nhưng giữ signature; giải thích tại sao tag sai hoặc format bị từ chối.

**Bài 8 — Key rotation:** Đổi Credential sang key ID đã thu hồi hoặc key mới và giữ tag cũ; thực hiện resolver kiểm tra policy, chứng minh không thử mọi secret hoặc format để “cứu” request.

**Bài 9 — Replay:** Gửi request hợp lệ hai lần, kiểm tra nonce store. Lần thứ hai HMAC vẫn có thể đúng nhưng phải bị từ chối. Tạo attempt mới có nonce/tag mới và cùng idempotency key để chứng minh tầng nghiệp vụ xử lý retry đúng.

**Bài 10 — Canonical digest:** Ký body JSON raw bytes, sau đó để gateway reformat JSON hoặc giải nén trước verifier; xác định cần version hóa Content-Encoding/trust boundary gì.

**Bài 11 — Fuzz header parsing:** Sinh input có duplicate Authorization, order sai, unknown params, quote escaping, dấu phẩy, newline và strings rất dài. Đảm bảo parser fail closed, không throw exception không được xử lý hoặc phân bổ tài nguyên vô hạn.

**Bài 12 — Cross-language vectors:** Viết signer ở Java 17, verifier ở ngôn ngữ khác; so byte hex canonical, SHA-256 digest, HMAC bytes và Base64URL. Đặc biệt test tên header khác casing và field order khác trên wire.

## 18. Câu hỏi tự kiểm tra

1. Trong ví dụ, `SignedHeaders` là một HTTP header riêng hay tham số trong `Authorization`?
2. Vì sao không đưa toàn bộ `Authorization` chứa `Signature` vào canonical message?
3. Vì sao `Credential` và chính chuỗi `SignedHeaders` phải được ràng buộc trong MAC?
4. Điều gì xảy ra nếu server chấp nhận danh sách signed fields do client tùy chọn mà không có required set?
5. Tên HTTP header khác casing có tạo ra field mới không?
6. Vì sao duplicated `X-Nonce` và `x-nonce` phải bị từ chối?
7. Nên lowercase tên header hay cả values?
8. Vì sao `String.trim()` hoặc `replaceAll("\\s+", " ")` không đủ để làm signing contract?
9. `SignedHeaders` phải dùng thứ tự các headers trên wire hay thứ tự canonical?
10. `Host` trong HTTP/1.1 và `:authority` trong HTTP/2 cần xử lý thế nào?
11. Một unsigned `X-Tenant-Id` có thể nguy hiểm trong điều kiện nào?
12. Tại sao method, raw URI target và body hash không nhất thiết nằm trong `SignedHeaders` nhưng vẫn được ký?
13. Vì sao timestamp và nonce phải là required signed fields khi chống replay?
14. Replay store timeout khi MAC đã đúng thì có được bỏ qua để chạy nghiệp vụ không?
15. Khi retry cùng operation, nonce và idempotency key thay đổi như thế nào?
16. Đổi key ID trong giai đoạn rotation có tự tạo một client identity/operation mới không?
17. HMAC hợp lệ, timestamp mới, nonce chưa dùng có đủ chứng minh client được quyền sửa tài nguyên tenant khác không?
18. Làm sao kiểm thử gateway rewrite mà không nhầm lỗi MAC với lỗi thời gian?
19. Với `content-type;host;x-idempotency-key;x-nonce;x-timestamp`, header nào được thêm vào canonical line format `name:value`?
20. Vì sao một signed header list canonical duy nhất giúp kiểm thử đa ngôn ngữ và chống signature confusion?

**Ghi nhớ:** `SignedHeaders` trong `Authorization` là **hợp đồng công khai về những HTTP fields được HMAC bảo vệ**, không phải giấy phép để client tự bỏ qua timestamp, nonce, authority hoặc header nghiệp vụ quan trọng. Server phải có required-set policy, xác minh **chính danh sách** và từng canonical `name:value` cùng Credential, method, URI và body digest; từ chối duplicate/ambiguous headers, kiểm soát HTTP/2–gateway authority mapping. Sau khi MAC khớp, vẫn phải kiểm tra signed timestamp, atomic nonce claim, key policy, phân quyền theo resource/tenant và idempotency cho retries.
