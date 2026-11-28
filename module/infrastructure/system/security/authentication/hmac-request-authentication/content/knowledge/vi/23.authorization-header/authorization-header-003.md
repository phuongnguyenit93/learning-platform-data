# Signature field trong Authorization header khi xác thực HTTP request bằng HMAC

> **Chương:** Authorization header  
> **Đề bài:** Signature field  
> **Phạm vi:** `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION` — Thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request bao gồm method, URI, signed headers và/hoặc body. Bài tập trung vào trường chứa **signature trong Authorization**, kiểm tra cú pháp, lựa chọn key và so chữ ký; đồng thời kết nối timestamp/nonce chống replay, key rotation, proxy/gateway và ranh giới authentication–authorization.

## 1. "Signature field" là thành phần nào của HTTP?

Khi client gửi HTTP request có HMAC, nó cần truyền **tag HMAC** cho receiver. Tag là byte nhị phân (HMAC-SHA-256 đầy đủ có **32 byte**), trong khi HTTP `Authorization` là một trường có cú pháp văn bản.

Trong nhiều API, thông tin được đóng gói vào `Authorization` như một **authentication scheme** với các tham số. Bài này định nghĩa hợp đồng minh họa:

~~~http
POST /v1/orders?mode=commit HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
Authorization: HMAC-SHA256 client_id="merchant-17", key_id="k-2026-11", signature="<base64url-tag>"

{"orderId":"o-123","amount":150000}
~~~

Trong dòng `Authorization`:

- `HMAC-SHA256` là **authentication scheme do ứng dụng này định nghĩa**, không phải một scheme chuẩn được mọi server/browser hiểu.
- `client_id="merchant-17"` khai báo định danh client; ban đầu **chưa đáng tin**.
- `key_id="k-2026-11"` chỉ định credential record để tra shared secret, **không chứa secret**.
- `signature="..."` là **signature parameter**, mang **Base64URL không padding** của tag HMAC-SHA-256 32 byte; giá trị hợp lệ phải dài **43 ký tự**.

**Quan trọng:** bài nói về **tham số `signature` nằm trong `Authorization` của custom scheme**, **không** phải HTTP field `Signature: ...` theo RFC 9421 hay token `Bearer ...` của OAuth. Các giao thức đó có định dạng, phạm vi ký và cơ chế xác minh riêng.

### 1.1. Authorization header không đồng nghĩa kết quả authorization

Tên trường `Authorization` là một thuật ngữ lịch sử trong HTTP: nó **mang credentials** để server xác thực request. Nó **không tự chứng minh** client có quyền gọi endpoint, đọc payment hay sửa tài nguyên tenant khác.

~~~text
Authorization request field
        |
        v
  Parse credential syntax
        |
        v
  Look up shared secret by verified binding
        |
        v
  Rebuild canonical HTTP request
        |
        v
  Verify HMAC tag / timestamp / nonce
        |
        v
  Authenticated principal: merchant-17
        |
        v
  Authorization: may merchant-17 perform action on resource X?
~~~

Một request có `signature` đúng vẫn có thể **bị từ chối 403** do thiếu quyền nghiệp vụ. Cùng lúc, một `Authorization` có format hợp lệ nhưng tag sai chưa bao giờ tạo ra authenticated principal.

### 1.2. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt `Authorization` field, auth-scheme, auth-param `signature`, tag HMAC raw bytes và HTTP `Signature`/`Signature-Input` của RFC 9421.
2. Mô tả cách truyền client ID, key ID và tag trong **một** `Authorization` credential; tránh nhầm credential identifier với shared secret.
3. Thiết kế grammar không nhập nhằng, kiểm soát duplicate headers, duplicate params, OWS, quoted string và Base64URL canonical.
4. Cố định thuật toán, format signature, chiều dài MAC và các thành phần HTTP được ký; không cho attacker chọn thuật toán yếu.
5. Xác minh HMAC bằng Java 17 `Mac.getInstance("HmacSHA256")` và `MessageDigest.isEqual` sau khi decode đúng **32 byte**.
6. Ràng buộc method, raw target, Content-Type, client/key IDs, timestamp, nonce và raw body digest vào canonical request.
7. Phân tích lỗi khi gateway/proxy rewrite headers/path/body, khác biệt giữa `Authorization` và `Proxy-Authorization`, rủi ro logging/cache.
8. Kết hợp freshness/nonce store, key rotation, principal isolation và authorization, rồi viết negative tests/golden fixtures.

## 2. Cấu trúc Authorization theo HTTP và hợp đồng HMAC

### 2.1. Authorization là một HTTP field có grammar riêng

`Authorization` là HTTP request field chứa **credentials** cho một protection space. Mô hình ngữ pháp chung trong HTTP authentication có dạng ý tưởng:

~~~abnf
Authorization = credentials
credentials   = auth-scheme [ 1*SP ( token68 / #auth-param ) ]
auth-param    = token BWS "=" BWS ( token / quoted-string )
~~~

Trong `auth-param`, `token` là tên tham số; giá trị có thể là token hoặc quoted-string. HTTP auth-scheme và tên auth-param **không phân biệt hoa/thường theo grammar chung**; cách hiểu **giá trị** là tùy định nghĩa của scheme. Khả năng có nhiều khoảng trắng hoặc quoted-pair được HTTP grammar cho phép trong những vị trí nhất định, **không có nghĩa** ứng dụng được bỏ qua bất đồng giữa các parser.

Hợp đồng bài chọn **một tập con cố định của cú pháp trên**, để có thể demo parser strict thay vì tự xây một HTTP generic authentication framework:

~~~text
Authorization: HMAC-SHA256 client_id="<client>", key_id="<key>", signature="<tag>"
~~~

Lưu ý có **dấu phẩy** giữa các `auth-param`, không phải dấu chấm phẩy. `signature` là giá trị **nằm trong quotes**; quotes không phải một phần của tag khi decode.

**Các tham số không phải HTTP fields riêng:** `client_id`, `key_id` và `signature` là các phần của **một** `Authorization` field. Hợp đồng yêu cầu **đúng ba tham số**, đúng thứ tự, không có tham số lạ hay lặp.

### 2.2. Định dạng `hmac-authorization-v1` của bài

| Thành phần | Quy tắc minh họa |
|---|---|
| HTTP field name | `Authorization`, nhận dạng tên field không phân biệt hoa/thường |
| Field occurrences | **Đúng một**, reject thiếu hoặc duplicate |
| Scheme | `HMAC-SHA256`, nhận dạng auth-scheme không phân biệt hoa/thường |
| Auth params | Chính xác `client_id`, `key_id`, `signature` theo thứ tự cố định |
| Param names | Không phân biệt hoa/thường, nhưng client/key values **case-sensitive** |
| Khoảng trắng | Chính xác một SP sau scheme và một SP sau hai dấu phẩy, theo subset v1 |
| Quoted string | Có cặp `"..."`; nội dung bên trong theo alphabet chặt |
| Client ID | `[A-Za-z0-9_-]{1,64}`, không phải email hoặc bearer token |
| Key ID | `[A-Za-z0-9_-]{1,64}`; lookup cùng client và audience |
| Signature text | `[A-Za-z0-9_-]{43}`, Base64URL không padding |
| Tag raw bytes | **Đúng 32 byte** HMAC-SHA-256 đầy đủ, không cắt ngắn |
| Canonicality | Decode 32 byte rồi Base64URL encode no-pad phải ra **chính giá trị input** |
| Duplicate auth-param | Reject kể cả hai `signature` trùng nhau |
| Chữ ký chứa dấu `=` padding | Reject |
| Tham số `algorithm` do client đưa thêm | Reject; algorithm cố định trong version |
| HTTP `Proxy-Authorization` | **Không** được xem là `Authorization` của origin API |
| Nonce/timestamp | Chuyển trong `X-Nonce`/`X-Timestamp` riêng, được ký HMAC |
| Format errors | Reject, không tự fallback sang Basic, Bearer, hex hoặc RFC 9421 |

**Đây là giao thức học tập có version riêng.** Một hệ thống thật có thể dùng `Signature:` structured fields, `Authorization: HMAC <token68>` hoặc auth-params ở thứ tự khác. Không đem parser strict dưới đây vào một API mà không so khớp đầy đủ tài liệu của API đó.

### 2.3. Vì sao chọn subset strict thay vì parser “thông minh”?

Một parser có thể chấp nhận các chuỗi “gần giống”:

~~~text
Authorization: HMAC-SHA256 client_id=merchant-17, key_id=k1, signature=...
Authorization: HMAC-SHA256 signature="...", client_id="merchant-17", key_id="k1"
Authorization: HMAC-SHA256 client_id="merchant-17", key_id="k1", signature="...", signature="..."
Authorization: HMAC-SHA256 client_id="merchant-17", key_id="k1", signature="...", algorithm="none"
Authorization: HMAC-SHA256 client_id="merchant-17", key_id="k1", signature="..." ,foo="x"
~~~

Dù một số kiểu whitespace/parameter order có thể là cú pháp HTTP chung hợp lệ, **hợp đồng v1 chỉ nhận một serialization**, giúp kiểm thử và xử lý ở gateway dễ nhất quán. Đặc biệt, không được **“first wins”** hoặc **“last wins”** khi `signature`, `client_id`, `key_id` lặp.

Cần nhớ **HTTP parser** thực thi framing và các kiểm tra cơ bản trước khi ứng dụng nhìn thấy field value. Parser ở ví dụ không thay thế HTTP/1.1/2 parser chuyên dụng; HTTP adapter phải kiểm tra đủ **occurrences của Authorization** trước khi chọn giá trị.

## 3. Signature field bên trong Authorization: tag chứ không phải secret

### 3.1. Từ raw HMAC đến signature text

HMAC-SHA-256 hoạt động với byte arrays:

\[
\mathrm{tag}=\mathrm{HMAC\text{-}SHA256}(K,\mathrm{canonicalBytes})
\]

Với HMAC-SHA-256 đầy đủ:

~~~text
HMAC output:             32 bytes = 256 bits
Base64URL no-padding:    43 ASCII characters
Standard Base64 padded:  44 characters
Hex lowercase:           64 characters
~~~

`Base64URL` và `hex` chỉ là hai cách mã hóa **cùng tag**, không thay đổi sức mạnh mật mã. Trong contract này, client phải đưa **43 ký tự Base64URL không padding** vào tham số `signature`; receiver không tự đoán encoding.

Base64URL khác Base64 thường ở hai ký tự: `+`→`-` và `/`→`_`. Dấu `=` padding có thể tồn tại trong Base64 thông thường nhưng bị cấm ở hợp đồng này.

### 3.2. Strict decode và canonical representation

Bên nhận phải:

1. Tách đúng **một** `signature` trong `Authorization` credential đã parse.
2. Kiểm tra alphabet `[A-Za-z0-9_-]`, đúng **43 ký tự**.
3. Dùng URL-safe decoder để lấy byte array, reject nếu decode lỗi.
4. Đòi kết quả **32 byte**.
5. Encode lại bằng URL-safe no-padding; reject nếu không **bằng chính xác** chuỗi input.
6. Tính lại expected tag từ canonical request và đúng shared secret.
7. So hai **raw 32-byte arrays** bằng primitive phù hợp, không so text có dừng sớm.

Với 32 byte, ký tự Base64URL cuối chứa **hai pad bits không dùng**, phải bằng 0 trong canonical encoding. Một số decoder có thể bỏ qua các bit này, khiến **hai signature texts khác nhau decode ra cùng tag**. Round-trip giúp loại biểu diễn không chuẩn, để log/validator/gateway không hiểu khác nhau.

~~~java
byte[] received = Base64.getUrlDecoder().decode(signatureText);
if (received.length != 32) reject();

String canonical = Base64.getUrlEncoder()
        .withoutPadding().encodeToString(received);
if (!canonical.equals(signatureText)) reject();

byte[] expected = mac.doFinal(canonicalRequestBytes);
boolean matches = MessageDigest.isEqual(expected, received);
~~~

**Đừng** thay `MessageDigest.isEqual` bằng `String.equals` trên signature text để làm bước xác minh mật mã. Đặc biệt tránh phép so byte dừng ngay tại mismatch đầu tiên; nó có thể gây timing side channel phụ thuộc vào prefix trùng của expected tag. Phép so tag phù hợp **không khiến toàn bộ pipeline** constant-time: parsing, key lookup, body hashing, nonce store và authorization vẫn có thời gian khác nhau.

### 3.3. Signature param phải chứa **tag**, không chứa secret

Một số cách đóng gói sai:

~~~http
Authorization: HMAC-SHA256 client_id="merchant-17", key_id="secret-value", signature="..."
Authorization: HMAC-SHA256 client_id="merchant-17", key_id="k1", signature="my-password"
Authorization: HMAC-SHA256 client_id="merchant-17", key_id="k1", signature="<raw-binary-bytes>"
~~~

`key_id` là ID công khai để **tra secret nằm ở server/key store**, không phải secret. Signature là **tag dẫn xuất** từ secret và request, không phải secret có thể gửi để server lookup. Shared secret chỉ nằm trong sender/key store bảo mật, không đưa lên URL, headers hay body.

Ngay cả khi `Authorization` chỉ chứa derived tag, nó vẫn là **credential-bearing field**, có thể hữu ích cho replay khi timestamp/nonce bảo vệ không đầy đủ. Dùng TLS, log redaction, giới hạn lưu giữ và không tiết lộ signature trong lỗi.

## 4. Phân biệt nhiều cách ký HTTP dễ bị nhầm

### 4.1. Custom HMAC Authorization vs RFC 9421

| Phương án | Ví dụ wire representation | Cần lưu ý |
|---|---|---|
| **Custom `Authorization` HMAC** của bài | `Authorization: HMAC-SHA256 client_id="...", key_id="...", signature="..."` | Signature là **auth-param** trong một field; grammar do API định nghĩa |
| HTTP Message Signatures theo **RFC 9421** | `Signature-Input: sig1=...` và `Signature: sig1=:...:` | Dùng Structured Fields, signature base, covered components; **không đồng nhất** với custom scheme |
| Bearer token | `Authorization: Bearer <token>` | Token có thể đại diện một grant; không phải raw HMAC per-request |
| Basic | `Authorization: Basic <token68>` | User/password encoding; phải dùng TLS; không phải HMAC request signature |
| Proxy credentials | `Proxy-Authorization: ...` | Credentials cho proxy, không cho origin server |
| `X-Signature` của ứng dụng khác | `X-Signature: <encoded MAC>` | Tách signature thành field riêng, khác grammar/canonical contract |

**Không “đoán” RFC 9421 chỉ vì nhìn thấy chữ `Signature`.** RFC 9421 định nghĩa cách tạo signature base/parameters và cách biểu diễn trong hai HTTP fields `Signature-Input`, `Signature`; đây là chuẩn có semantics khác. Nếu triển khai RFC 9421, phải tuân theo chuẩn đó thay vì thay tên header trong demo này.

### 4.2. Vì sao `Authorization` không phải phần tự tham chiếu trong canonical request?

Nếu đưa **toàn bộ raw `Authorization` field** (bao gồm `signature`) vào dữ liệu được ký:

~~~text
canonicalRequest = ... + Authorization(signature=???)
signature = HMAC(secret, canonicalRequest)
~~~

ta tạo **vòng tự tham chiếu**. Hợp đồng v1 chọn:

- **Không** đưa `Authorization` nguyên field vào canonical bytes.
- Đưa **client ID** và **key ID đã parse** thành hai dòng canonical request, để thay credential selectors làm MAC khác/lookup sai.
- Cố định **scheme/algorithm/serialization** theo `hmac-authorization-v1`; không cho chọn scheme/algorithm tùy tiện.
- Đưa timestamp, nonce, method, raw target, Content-Type và SHA-256 raw body vào canonical request.

Như vậy signature field nằm ngoài nội dung ký, còn các metadata quan trọng được ràng buộc bằng chữ ký. Đừng để ứng dụng nhận thêm một field unsigned có thể đổi hành vi xử lý nghiệp vụ mà không thuộc covered components.

### 4.3. Signature không phải request ID hoặc nonce

| Trường | Thay đổi trong một retry hợp lệ | Mục đích |
|---|---|---|
| `signature` | **Có**: ký lại canonical bytes mới | Chứng minh tính toàn vẹn và sở hữu secret |
| `X-Nonce` | **Có**: nonce mới mỗi attempt | Chống replay byte-for-byte/request đã ký |
| `X-Timestamp` | **Có**: timestamp tại attempt mới | Giới hạn tuổi request |
| `client_id` | Thường không | Principal/tenant selector |
| `key_id` | Có thể đổi khi key rotation | Chọn secret hợp lệ |
| `X-Idempotency-Key` nếu có | **Giữ nguyên** cho cùng logical operation | Tránh double side effects sau timeout |

HMAC signature **không được dùng thay** business idempotency key: hai attempts hợp lệ của cùng thao tác có nonce/timestamp khác nên tạo hai tags khác nhau.

## 5. Canonical HTTP request: chữ ký bảo vệ những gì?

Contract minh họa `hmac-authorization-v1`, chỉ hỗ trợ `POST` đối với đường dẫn `/v1/orders`, với query `?mode=preview` hoặc `?mode=commit`:

| Dòng | Thành phần | Quy tắc |
|---|---|---|
| 1 | Version | Literal `hmac-authorization-v1` |
| 2 | Audience | Literal `orders-api-production` |
| 3 | HTTP method | `POST`, đúng method xử lý |
| 4 | Raw request-target | `/v1/orders?mode=commit`, grammar giới hạn, không tự normalize |
| 5 | Content-Type | `application/json`, canonical lowercase/trim |
| 6 | Client ID | Giá trị `client_id` đã parse từ Authorization |
| 7 | Key ID | Giá trị `key_id` đã parse từ Authorization |
| 8 | Timestamp | `X-Timestamp`, Unix epoch seconds thập phân canonical |
| 9 | Nonce | `X-Nonce`, 16 random bytes/Base64URL no-padding |
| 10 | Body digest | SHA-256 raw request body bytes, hex chữ thường |

Nối các dòng bằng **LF (`\n`)**, không có LF cuối, mã hóa UTF-8. Dùng `Mac.getInstance("HmacSHA256")` với secret thuộc đúng `(audience, client_id, key_id)`, sau đó chuyển 32-byte tag thành Base64URL no-padding để đặt trong `signature` auth-param.

~~~text
hmac-authorization-v1
orders-api-production
POST
/v1/orders?mode=commit
application/json
merchant-17
k-2026-11
1795824000
b75sZVQmhTBcfnX-bNbGqw
<sha256-lowercase-hex-of-exact-body-bytes>
~~~

Dòng cuối là **placeholder**; khi ký thật phải hash đúng bytes của request sau HTTP framing tại điểm verify, trước mọi transform không được hợp đồng cho phép.

**Lưu ý về gateway:** path/query có thể thay khi reverse proxy strip prefix, decode percent escapes hoặc rewrite route. Request body có thể đổi nếu gateway decompress/recompress, JSON middleware serialize lại, hoặc content coding không thống nhất. Nếu HMAC được tính trên representation khác, chữ ký sẽ không khớp hoặc — nghiêm trọng hơn — business handler có thể xử lý nội dung khác nội dung đã verify. Để đơn giản, demo yêu cầu **không có Content-Encoding request**, đúng `application/json` và raw target grammar chặt; HTTP adapter thật phải thi hành các ràng buộc đó.

### 5.1. Ràng buộc key selection và chống cross-tenant confusion

Receiver **không** được chỉ tìm một key bằng `key_id` rồi tin bất kỳ `client_id` nào client đưa. Đúng hơn:

~~~text
1. Parse (client_id, key_id, signature) từ Authorization.
2. Dùng (audience cấu hình server, client_id, key_id)
   làm khóa lookup trong key store đáng tin.
3. Key record xác nhận owner clientId/audience, state hợp lệ.
4. Kiểm tra timestamp và canonical inputs.
5. Tính HMAC bằng secret của chính record được phép verify.
6. So expected 32-byte tag với received 32-byte tag.
7. Sau MAC đúng mới reserve nonce và tạo principal từ key record.
8. Authorization theo action/resource/tenant thực sự.
~~~

**Không** duyệt tất cả secret rồi chấp nhận secret nào khớp; điều đó có thể gây cross-tenant identity confusion, độ trễ phụ thuộc vị trí key và DoS. **Không** coi client ID trong Authorization là principal tin cậy trước khi HMAC thành công.

### 5.2. Key rotation và algorithm policy

| Key state | Xử lý |
|---|---|
| `ACTIVE` | Cho phép verify theo chính sách |
| `VERIFY_ONLY` | Cho phép verify trong overlap trước deadline do server quản lý |
| `REVOKED` | Reject dù raw HMAC tag được tính đúng bằng key cũ |
| Key không thuộc client/audience | Reject, không thử key tenant khác |
| Key không tồn tại | Reject, không fallback một secret chung |

Nếu client chuyển từ `key_id="old"` sang `key_id="new"`, đó là **hai secrets khác nhau**. Receiver chỉ xác minh với secret được chỉ định và có quyền verify; không tự thử nhiều secrets “để may ra khớp”. Nonce scope nên ổn định theo **(audience, authenticatedClientId, nonce)** nếu replay policy là mỗi nonce dùng một lần **xuyên key rotation**.

### 5.3. Timestamp và nonce không thể bỏ

MAC đúng chỉ chứng minh request đã được ký và không bị sửa. Nếu attacker sao chép nguyên `Authorization`, `X-Timestamp`, `X-Nonce`, method, raw target và body, thì tag HMAC **vẫn đúng** trong cửa sổ time.

Chính sách học tập:

~~~text
X-Timestamp = Unix epoch seconds canonical
freshness   = now - 300 <= timestamp <= now + 300
X-Nonce     = 16 byte CSPRNG, Base64URL no-padding 22 chars
nonce scope = (audience, authenticatedClientId, canonicalNonce)
reserve     = atomic insert-if-absent SAU MAC đúng
nonce TTL   = >= 600 seconds + operational margin
example TTL = 660 seconds
~~~

Với Redis, thao tác tương đương `SET key 1 NX EX 660` tạo key và TTL **trong cùng một lệnh**. `EX` tính **giây**; `PX 660000` tính **mili giây**. `PX 660` chỉ là 0,66 giây, quá ngắn. Nếu store bắt buộc nhưng unavailable, phải **fail closed**. TTL cần tính trên **toàn khoảng thời gian timestamp có thể được chấp nhận**, không chỉ ±300 giây từ thời điểm request đầu tiên.

Không reserve nonce trước MAC — attacker có thể gửi `Authorization` giả và chiếm nonce của client thật. Với hệ thống nhiều node, nonce store phải có **atomicity giữa tất cả các verifier**; `ConcurrentHashMap` trong một JVM không đủ.

## 6. Parse Authorization an toàn qua HTTP stack

### 6.1. Duplicate field occurrences

Tình huống nguy hiểm:

~~~http
Authorization: HMAC-SHA256 client_id="merchant-a", key_id="ka", signature="..."
authorization: HMAC-SHA256 client_id="merchant-b", key_id="kb", signature="..."
~~~

Hai dòng là **cùng field name** vì HTTP field names không phân biệt chữ hoa/chữ thường. Proxy có thể lấy dòng đầu, backend lấy dòng cuối hoặc gộp chúng. Hợp đồng yêu cầu **đúng một occurrence**, reject nếu nhiều, kể cả khi hai values giống nhau. Không dùng `getHeader("Authorization")` và mặc định rằng thư viện bảo đảm không có duplicate ở tầng wire.

Nếu proxy gộp values thành chuỗi có dấu phẩy, strict parser phải reject thay vì ngầm chọn credential đầu. Dấu phẩy **bên trong** một Authorization value lại được dùng để phân tách auth-params; cần parser hiểu **đúng grammar**, không chỉ thử `split(",")[0]` hoặc lấy mọi phần tử giữa hai dấu phẩy làm separate credentials.

### 6.2. Quoted values, control characters và OWS

Hợp đồng v1 nhận:

~~~http
Authorization: HMAC-SHA256 client_id="merchant-a", key_id="key-1", signature="ABC..."
~~~

Nó không nhận:

~~~text
Authorization: HMAC-SHA256 client_id = "merchant-a", key_id="key-1", signature="..."
Authorization: HMAC-SHA256 client_id="merchant-a",key_id="key-1",signature="..."
Authorization: HMAC-SHA256 client_id="merchant-a", key_id="key-1", signature="..." ,signature="..."
Authorization: HMAC-SHA256 client_id="merchant-a", key_id="key-1", signature="..."\r\nX-Key-Id: attacker
~~~

Một số hình thức spacing khác có thể được grammar HTTP chung cho phép, nhưng **không thuộc subset giao thức minh họa**. HTTP adapter cần reject CR/LF, NUL, obs-fold sai chuẩn và request smuggling ngay ở parsing. Lớp ứng dụng vẫn giới hạn length/ASCII và dùng **full-match regex** trên field value đã được HTTP parser xử lý OWS ở biên theo chính sách. Không tự cố parse/normalize một chuỗi header chứa ký tự điều khiển.

**Không log nguyên Authorization.** Header này có thể chứa bearer token/Basic credential ở những routes khác và signature HMAC trong route hiện tại. Structured logging phải redaction, tránh đưa giá trị vào traces, APM, exception và error messages.

### 6.3. Không chấp nhận algorithm confusion

Các giá trị sau **không thuộc contract**:

~~~http
Authorization: Bearer eyJ...
Authorization: Basic dXNlcjpwYXNz
Authorization: HMAC-SHA1 client_id="...", key_id="...", signature="..."
Authorization: HMAC-SHA256 client_id="...", key_id="...", signature="...", algorithm="none"
~~~

Client không có quyền tự giảm độ mạnh thuật toán, gửi `HMAC-SHA1` hay tag truncated rồi yêu cầu server thử nhiều thuật toán. Nếu chuyển sang signature algorithm khác, định nghĩa **version mới**, policy key rotation và golden fixtures mới.

Đừng đồng nhất `Authorization: Signature ...` từ một ứng dụng khác với RFC 9421. Giá trị của HTTP `Authorization` phải được diễn giải theo scheme mà API **đã công bố**, không theo sự giống tên.

## 7. Gateway, proxy, cache và log: bảo vệ signature field theo đúng ranh giới

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway / WAF
    participant V as HMAC Verifier
    participant K as Key Store
    participant N as Shared Nonce Store
    participant A as Authorization
    C->>C: Canonical bytes, HMAC tag, auth-param signature
    C->>G: POST + Authorization + X-Timestamp + X-Nonce
    G->>V: Giữ signed method/target/headers/body
    V->>V: Check unique Authorization, parse strict, decode MAC
    V->>K: Lookup clientId/keyId/audience
    K-->>V: Allowed key record + secret
    V->>V: Validate freshness và full HMAC
    V->>N: Reserve nonce atomically
    N-->>V: Nonce mới
    V->>A: Authenticated principal
    A->>A: Resource-level permission check
~~~

### 7.1. Trường hợp cần test end-to-end

| Thành phần thay đổi | Rủi ro | Biện pháp |
|---|---|---|
| Gateway xóa `Authorization` | Receiver không có credential | Reject; kiểm cấu hình forward |
| Gateway chuyển `Authorization` vào `Proxy-Authorization` | Origin API không nhận đúng field | Không coi hai field tương đương |
| Proxy rewrite `client_id/key_id` hoặc đổi case **giá trị** | Lookup sai, MAC mismatch | Không rewrite values; case-sensitive IDs |
| Proxy lower-case tên scheme/param | HTTP scheme/param names case-insensitive | Parser hỗ trợ theo hợp đồng, giữ values |
| CDN/proxy gộp hai `Authorization` fields | Mất multiplicity, auth ambiguity | Reject duplicate tại edge và backend |
| Gateway normalize path/query | Canonical target có thể đổi | Verify trước rewrite hoặc giữ trusted original bytes |
| Gateway tự giải nén request body | Body digest đổi | Bảo toàn raw bytes/coding theo hợp đồng |
| Gateway ký lại request dưới credential khác | Principal boundary thay đổi | Chỉ khi thiết kế trusted delegation riêng |
| Proxy cache trả response trước verify | Bỏ qua auth/freshness/nonce | Không bypass authentication; cache policy đúng |
| Log `Authorization` hoặc signature | Rò credential/tag, hỗ trợ replay khi kiểm soát yếu | Redaction, retention tối thiểu |
| Gateway xác minh HMAC rồi thêm `X-Verified-Client` | Client có thể tự đặt header để giả danh | Strip headers từ internet, kênh proxy–backend tin cậy |

### 7.2. HTTP caching và Authorization

Sự hiện diện của `Authorization` tác động đến quy tắc sử dụng shared cache trong HTTP. Tuy nhiên, **đừng chỉ dựa vào nó** để bảo vệ response nhạy cảm: các quy tắc cache có ngoại lệ theo cache directives, và hệ thống có thể có CDN hoặc cache tùy biến không tuân thủ đủ.

Đối với response chứa thông tin riêng tư, cân nhắc chính sách phù hợp như `Cache-Control: private, no-store` và kiểm thử proxy/CDN thực tế. Không để một response cho merchant A bị cache rồi trả cho merchant B trước bước authentication/authorization. Một request có chữ ký đúng cũng không bảo đảm cached response thuộc principal đang yêu cầu.

### 7.3. Proxy-Authorization không phải Authorization

`Proxy-Authorization` được dùng để cấp credential cho **proxy** trong mô hình HTTP proxy authentication; `Authorization` gửi credential cho **origin server**. Không copy tự động một field thành field còn lại hoặc dùng proxy credential để xác thực nghiệp vụ. Khi có forward proxy/reverse proxy, kiểm thử propagation và trust boundary rõ ràng.

### 7.4. WWW-Authenticate và error responses

Trong HTTP authentication framework, response `401 Unauthorized` thường đi cùng `WWW-Authenticate` challenge tương ứng. Với custom `HMAC-SHA256` scheme, nếu hệ thống quyết định dùng challenge, cần quy định syntax, realm, nonce/challenge semantics và client SDK behavior rõ ràng; **không tự giả định custom header trong ví dụ này đã có quy trình challenge chuẩn**.

Có thể trả lỗi public ở mức:

~~~text
400 Bad Request  -> malformed/ambiguous Authorization hoặc HTTP header
401 Unauthorized -> credential không hợp lệ, key state hoặc MAC fail
403 Forbidden    -> authenticated nhưng không có quyền tài nguyên
503 Service Unavailable -> bắt buộc kiểm nonce store nhưng backend store down
~~~

Mã phản hồi chính xác tùy API contract. Không tiết lộ `expectedHmac`, secret, key existence hay vị trí byte sai. Hạn chế phân biệt lỗi quá chi tiết với người gọi chưa được xác thực để giảm key enumeration/timing oracles.


## 8. Java 17: parse signature trong Authorization và verify HMAC

Ví dụ dưới đây viết bằng **Java 17+**, chỉ sử dụng JDK. Chương trình có các thành phần:

1. `Authorization` chứa custom `HMAC-SHA256` auth-params `client_id`, `key_id` và `signature`.
2. Parser bắt buộc đúng một field và đúng cấu trúc, reject duplicate/parameter dư, control characters, padding hoặc tag sai alphabet.
3. `Base64.getUrlDecoder()` và re-encode không padding để xác nhận **signature canonical**.
4. Key store mô phỏng: lookup chính xác `(audience, clientId, keyId)` và kiểm tra trạng thái `ACTIVE/VERIFY_ONLY/REVOKED`.
5. Canonical request 10 dòng từ method, raw target, Content-Type, parsed credentials, timestamp, nonce và raw body SHA-256.
6. `Mac.getInstance("HmacSHA256")` và `MessageDigest.isEqual` với tag đủ 32 byte.
7. `Clock.fixed` để test cửa sổ ±300 giây; nonce store `ConcurrentHashMap.compute` để minh họa atomic insert trong **một JVM**.
8. Test: đúng/sai auth-param, signature format, HMAC tampering, replay, key rotation, hai client cùng nonce, concurrency và authorization.

**Đây chỉ là demo HTTP authentication core.** Nó nhận một `List<String> authorizationValues` giả lập đã được HTTP adapter lấy ra. Nó không tự xử lý network framing, kiểm tra mọi signed header occurrences, key vault thật, distributed nonce store hay business authorization.

### 8.1. Mã nguồn `AuthorizationSignatureFieldDemo.java`

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class AuthorizationSignatureFieldDemo {
    private static final String VERSION = "hmac-authorization-v1";
    private static final String AUDIENCE = "orders-api-production";
    private static final String ALGORITHM = "HmacSHA256";
    private static final long WINDOW_SECONDS = 300L;
    private static final long NONCE_TTL_SECONDS = 660L;

    // CASE_INSENSITIVE chỉ áp lên scheme và tên các param;
    // capture values giữ nguyên case, dùng cho key lookup và MAC.
    private static final Pattern AUTH_GRAMMAR = Pattern.compile(
            "(?i:HMAC-SHA256) "
          + "(?i:client_id)=\"([A-Za-z0-9_-]{1,64})\", "
          + "(?i:key_id)=\"([A-Za-z0-9_-]{1,64})\", "
          + "(?i:signature)=\"([A-Za-z0-9_-]{43})\"");

    private AuthorizationSignatureFieldDemo() {}

    public record Request(
            String method, String rawTarget, String contentType,
            String timestamp, String nonce, byte[] rawBody) {
        public Request {
            if (rawBody == null) {
                throw new IllegalArgumentException("Missing raw body");
            }
            rawBody = rawBody.clone();
        }
        @Override
        public byte[] rawBody() {
            return rawBody.clone();
        }
    }

    public record Credential(
            String clientId, String keyId, String signature) {}

    public record KeyRef(
            String audience, String clientId, String keyId) {}

    public enum KeyState { ACTIVE, VERIFY_ONLY, REVOKED }

    public record KeyRecord(
            String audience, String clientId, String keyId,
            KeyState state, long verifyOnlyUntilEpochSeconds,
            byte[] sharedSecret) {
        public KeyRecord {
            if (sharedSecret == null || sharedSecret.length != 32) {
                throw new IllegalArgumentException(
                        "Demo key requires exactly 32 bytes");
            }
            sharedSecret = sharedSecret.clone();
        }
        @Override
        public byte[] sharedSecret() {
            return sharedSecret.clone();
        }
    }

    public record Principal(String clientId, String audience) {}

    public record NonceScope(
            String audience, String authenticatedClientId,
            String nonce) {}

    // DEMO ONLY: atomic trong một JVM, không chia sẻ giữa replicas.
    // Không có background cleanup; production dùng store có TTL thật.
    public static final class LocalNonceStore {
        private final ConcurrentHashMap<NonceScope, Long> expiries =
                new ConcurrentHashMap<>();

        public boolean reserve(
                NonceScope scope, long nowSeconds, long ttlSeconds) {
            if (scope == null || ttlSeconds <= 0) {
                throw new IllegalArgumentException("Bad nonce reserve");
            }
            AtomicBoolean inserted = new AtomicBoolean(false);
            expiries.compute(scope, (key, priorExpiry) -> {
                if (priorExpiry != null && priorExpiry > nowSeconds) {
                    return priorExpiry; // Replay, giữ nguyên expiry.
                }
                inserted.set(true);
                return Math.addExact(nowSeconds, ttlSeconds);
            });
            return inserted.get();
        }
    }

    // Chỉ một Authorization occurrence; HTTP stack phải giữ
    // multiplicity, không được gộp hai Authorization fields.
    public static Credential parseAuthorization(
            List<String> authorizationValues) {
        if (authorizationValues == null
                || authorizationValues.size() != 1) {
            throw new IllegalArgumentException(
                    "Exactly one Authorization field required");
        }
        String field = authorizationValues.get(0);
        if (field == null || field.length() > 300) {
            throw new IllegalArgumentException(
                    "Missing/oversized Authorization value");
        }
        // HTTP adapter được kỳ vọng đã xử lý OWS ở hai biên.
        // Đúng subset grammar, full match, không tự trim nội dung.
        Matcher m = AUTH_GRAMMAR.matcher(field);
        if (!m.matches()) {
            throw new IllegalArgumentException(
                    "Authorization does not match HMAC v1 grammar");
        }
        return new Credential(m.group(1), m.group(2), m.group(3));
    }

    private static String identifier(String value) {
        if (value == null || !value.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Bad client/key ID");
        }
        return value;
    }

    public static String formatAuthorization(
            String clientId, String keyId, String signature) {
        identifier(clientId);
        identifier(keyId);
        // Validate trước khi tạo Authorization header.
        decodeSignatureStrict(signature);
        return "HMAC-SHA256 client_id=\"" + clientId
                + "\", key_id=\"" + keyId
                + "\", signature=\"" + signature + "\"";
    }

    public static byte[] decodeSignatureStrict(String text) {
        if (text == null || !text.matches("[A-Za-z0-9_-]{43}")) {
            throw new IllegalArgumentException(
                    "Expected 43 Base64URL no-pad chars");
        }
        final byte[] bytes;
        try {
            bytes = Base64.getUrlDecoder().decode(text);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Malformed Base64URL signature", ex);
        }
        if (bytes.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(bytes).equals(text)) {
            throw new IllegalArgumentException(
                    "Wrong length/non-canonical HMAC tag");
        }
        return bytes;
    }

    private static String signedNonce(String text) {
        // 16 bytes random -> 22 ký tự URL-safe không padding.
        if (text == null || !text.matches("[A-Za-z0-9_-]{22}")) {
            throw new IllegalArgumentException("Bad nonce format");
        }
        final byte[] raw;
        try {
            raw = Base64.getUrlDecoder().decode(text);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Bad nonce", ex);
        }
        if (raw.length != 16
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(raw).equals(text)) {
            throw new IllegalArgumentException("Non-canonical nonce");
        }
        return text;
    }

    public static String newNonce(SecureRandom rng) {
        byte[] random = new byte[16];
        rng.nextBytes(random);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(random);
    }

    private static long parseEpochSeconds(String text) {
        if (text == null || !text.matches("[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException(
                    "Epoch timestamp must use canonical seconds");
        }
        try {
            return Long.parseLong(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Epoch overflow", ex);
        }
    }

    private static boolean inWindow(String timestamp, long nowSeconds) {
        try {
            long delta = Math.subtractExact(
                    parseEpochSeconds(timestamp), nowSeconds);
            return delta >= -WINDOW_SECONDS
                    && delta <= WINDOW_SECONDS;
        } catch (IllegalArgumentException | ArithmeticException ex) {
            return false;
        }
    }

    private static String canonicalContentType(String value) {
        if (value == null || value.length() > 128
                || value.chars().anyMatch(
                        c -> (c < 0x20 && c != '\t') || c > 0x7E)) {
            throw new IllegalArgumentException("Bad Content-Type");
        }
        String canonical = value.trim().toLowerCase(Locale.ROOT);
        if (!"application/json".equals(canonical)) {
            throw new IllegalArgumentException(
                    "Unsupported Content-Type");
        }
        return canonical;
    }

    public static byte[] canonicalBytes(
            Request r, String clientId, String keyId)
            throws GeneralSecurityException {
        if (r == null || !"POST".equals(r.method())) {
            throw new IllegalArgumentException("Only POST supported");
        }
        if (r.rawTarget() == null || !r.rawTarget().matches(
                "/v1/orders\\?mode=(?:preview|commit)")) {
            throw new IllegalArgumentException("Unsupported raw target");
        }
        String client = identifier(clientId);
        String key = identifier(keyId);
        String time = r.timestamp();
        parseEpochSeconds(time); // Không đổi đơn vị hoặc chuỗi đã ký.
        String nonce = signedNonce(r.nonce());
        byte[] rawBody = r.rawBody();
        if (rawBody.length > 64 * 1024) {
            throw new IllegalArgumentException("Raw body too large");
        }
        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(rawBody));
        String canonical = String.join("\n",
                VERSION, AUDIENCE, r.method(), r.rawTarget(),
                canonicalContentType(r.contentType()),
                client, key, time, nonce, bodyHash);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] computeMac(
            byte[] secret, byte[] data)
            throws GeneralSecurityException {
        if (secret == null || secret.length == 0 || data == null) {
            throw new IllegalArgumentException("Bad HMAC input");
        }
        Mac engine = Mac.getInstance(ALGORITHM);
        engine.init(new SecretKeySpec(secret, ALGORITHM));
        return engine.doFinal(data);
    }

    public static String sign(Request r, KeyRecord key)
            throws GeneralSecurityException {
        byte[] tag = computeMac(
                key.sharedSecret(),
                canonicalBytes(r, key.clientId(), key.keyId()));
        String signature = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(tag);
        return formatAuthorization(
                key.clientId(), key.keyId(), signature);
    }

    private static boolean keyMayVerify(
            KeyRecord key, Credential supplied, long nowSeconds) {
        if (key == null || key.state() == null
                || !AUDIENCE.equals(key.audience())
                || !key.clientId().equals(supplied.clientId())
                || !key.keyId().equals(supplied.keyId())) {
            return false;
        }
        return key.state() == KeyState.ACTIVE
                || (key.state() == KeyState.VERIFY_ONLY
                    && nowSeconds <= key.verifyOnlyUntilEpochSeconds());
    }

    // HTTP adapter đã kiểm unique headers/timestamp/nonce và body coding.
    // Authenticated principal chỉ xuất hiện sau MAC+nonce đều hợp lệ.
    public static Principal authenticate(
            Request request, List<String> authorizationValues,
            Map<KeyRef, KeyRecord> keyStore,
            Clock clock, LocalNonceStore nonceStore)
            throws GeneralSecurityException {
        if (request == null || keyStore == null
                || clock == null || nonceStore == null) {
            return null;
        }
        final Credential credential;
        try {
            credential = parseAuthorization(authorizationValues);
        } catch (IllegalArgumentException badHeader) {
            return null;
        }
        KeyRef lookup = new KeyRef(
                AUDIENCE, credential.clientId(), credential.keyId());
        KeyRecord record = keyStore.get(lookup);
        long now = clock.instant().getEpochSecond();
        if (!keyMayVerify(record, credential, now)
                || !inWindow(request.timestamp(), now)) {
            return null;
        }

        final byte[] receivedTag;
        final byte[] expectedTag;
        try {
            receivedTag = decodeSignatureStrict(
                    credential.signature());
            expectedTag = computeMac(
                    record.sharedSecret(),
                    canonicalBytes(
                            request, credential.clientId(),
                            credential.keyId()));
        } catch (IllegalArgumentException badCanonicalInput) {
            return null;
        }
        if (!MessageDigest.isEqual(expectedTag, receivedTag)) {
            return null;
        }

        // Không chứa keyId: nonce được scoped theo principal/audience
        // và vẫn chặn replay xuyên key rotation.
        NonceScope nonceScope = new NonceScope(
                record.audience(), record.clientId(), request.nonce());
        if (!nonceStore.reserve(
                nonceScope, now, NONCE_TTL_SECONDS)) {
            return null;
        }
        return new Principal(record.clientId(), record.audience());
    }

    // Authorization nghiệp vụ là bước riêng; owner lấy từ DB.
    public static boolean mayReadOrder(
            Principal principal, String ownerFromTrustedDb) {
        return principal != null
                && principal.clientId().equals(ownerFromTrustedDb);
    }

    private static void require(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    private static void expectBadHeader(List<String> values) {
        boolean rejected = false;
        try {
            parseAuthorization(values);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        require(rejected, "Authorization must be rejected");
    }

    private static void knownAnswerHmac() throws Exception {
        // RFC 4231, Test Case 1: HMAC-SHA-256.
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0B);
        byte[] message = "Hi There"
                .getBytes(StandardCharsets.US_ASCII);
        String expectedHex =
                "b0344c61d8db38535ca8afceaf0bf12b"
              + "881dc200c9833da726e9376c2e32cff7";
        String actualHex = HexFormat.of().formatHex(
                computeMac(key, message));
        require(expectedHex.equals(actualHex),
                "RFC 4231 known-answer vector");
    }

    private static void concurrentReplayTest(
            Request request, String authorization,
            Map<KeyRef, KeyRecord> keyStore, Clock clock)
            throws Exception {
        int threads = 12;
        LocalNonceStore oneStore = new LocalNonceStore();
        ExecutorService executor = Executors.newFixedThreadPool(threads);
        CountDownLatch ready = new CountDownLatch(threads);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Principal>> results = new ArrayList<>();
        try {
            for (int i = 0; i < threads; i++) {
                results.add(executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    return authenticate(
                            request, List.of(authorization),
                            keyStore, clock, oneStore);
                }));
            }
            require(ready.await(10, TimeUnit.SECONDS),
                    "Workers ready for nonce race");
            start.countDown();
            int accepted = 0;
            for (Future<Principal> f : results) {
                if (f.get() != null) accepted++;
            }
            require(accepted == 1,
                    "Only one request may reserve same nonce");
        } finally {
            start.countDown();
            executor.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        knownAnswerHmac();
        SecureRandom rng = new SecureRandom();
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-28T00:00:00Z"),
                ZoneOffset.UTC);
        long now = clock.instant().getEpochSecond();

        byte[] oldSecret = new byte[32];
        byte[] newSecret = new byte[32];
        byte[] otherSecret = new byte[32];
        rng.nextBytes(oldSecret);
        rng.nextBytes(newSecret);
        rng.nextBytes(otherSecret);

        KeyRecord oldKey = new KeyRecord(
                AUDIENCE, "merchant-17", "key-old",
                KeyState.VERIFY_ONLY, now + 120, oldSecret);
        KeyRecord newKey = new KeyRecord(
                AUDIENCE, "merchant-17", "key-new",
                KeyState.ACTIVE, 0L, newSecret);
        KeyRecord otherClient = new KeyRecord(
                AUDIENCE, "merchant-42", "key-other",
                KeyState.ACTIVE, 0L, otherSecret);
        Map<KeyRef, KeyRecord> keys = new HashMap<>();
        for (KeyRecord k : List.of(oldKey, newKey, otherClient)) {
            keys.put(
                    new KeyRef(k.audience(), k.clientId(), k.keyId()),
                    k);
        }

        byte[] body = "{\"orderId\":\"o-123\",\"amount\":150000}"
                .getBytes(StandardCharsets.UTF_8);
        Request request = new Request(
                "POST", "/v1/orders?mode=commit", "application/json",
                Long.toString(now), newNonce(rng), body);

        String authorization = sign(request, oldKey);
        Credential parsed = parseAuthorization(
                List.of(authorization));
        require(parsed.clientId().equals("merchant-17"),
                "Client parsed");
        require(parsed.keyId().equals("key-old"), "Key parsed");
        require(decodeSignatureStrict(parsed.signature()).length == 32,
                "Full 32-byte HMAC tag");

        // HTTP auth-scheme/parameter names không phân biệt case;
        // values của client/key/tag vẫn được giữ nguyên.
        String variant = authorization
                .replace("HMAC-SHA256", "hmac-sha256")
                .replace("client_id=", "CLIENT_ID=")
                .replace("key_id=", "KEY_ID=")
                .replace("signature=", "SIGNATURE=");
        require(parseAuthorization(List.of(variant))
                .equals(parsed), "Case-insensitive scheme/param names");

        // Negative tests: duplicate, truncated, padded, extra params.
        expectBadHeader(List.of());
        expectBadHeader(List.of(authorization, authorization));
        expectBadHeader(List.of(authorization + ", foo=\"bar\""));
        expectBadHeader(List.of(
                authorization.replace("HMAC-SHA256", "Bearer")));
        expectBadHeader(List.of(
                authorization.replace("signature=\"", "signature=")));
        expectBadHeader(List.of(
                authorization.replace(
                        parsed.signature(), parsed.signature() + "=")));
        expectBadHeader(List.of(
                authorization.replace(
                        parsed.signature(),
                        parsed.signature().substring(0, 42))));
        expectBadHeader(List.of(
                authorization + "\r\nX-Key-Id: attacker"));

        LocalNonceStore nonces = new LocalNonceStore();
        Principal initial = authenticate(
                request, List.of(authorization), keys, clock, nonces);
        require(initial != null
                && "merchant-17".equals(initial.clientId()),
                "HMAC authentication passes");
        require(!mayReadOrder(initial, "merchant-42"),
                "Authentication does not give another tenant access");
        require(mayReadOrder(initial, "merchant-17"),
                "Authorization for owned resource");

        // Replay y nguyên: MAC đúng nhưng nonce đã dùng.
        require(authenticate(
                request, List.of(authorization), keys, clock, nonces)
                == null, "Exact replay is rejected");

        // Rotate key, giữ nonce: still replay (same authenticated client).
        String newKeyAuthorization = sign(request, newKey);
        require(authenticate(
                request, List.of(newKeyAuthorization), keys,
                clock, nonces) == null,
                "Cross-key same-client nonce reuse rejected");

        // Client khác có thể gửi cùng nonce nếu tự ký bằng key riêng.
        Request otherRequest = new Request(
                request.method(), request.rawTarget(),
                request.contentType(), request.timestamp(),
                request.nonce(), request.rawBody());
        String otherAuthorization = sign(otherRequest, otherClient);
        require(authenticate(
                otherRequest, List.of(otherAuthorization), keys,
                clock, nonces) != null,
                "Nonce namespace separated by authenticated client");

        // Sửa tag nhưng format vẫn hợp lệ: MAC fail,
        // và không được poison nonce cho request thật.
        Request protectedRequest = new Request(
                request.method(), request.rawTarget(),
                request.contentType(), request.timestamp(),
                newNonce(rng), request.rawBody());
        String good = sign(protectedRequest, newKey);
        Credential goodCredential = parseAuthorization(List.of(good));
        byte[] badTag = decodeSignatureStrict(
                goodCredential.signature());
        badTag[0] ^= 1;
        String badSignature = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(badTag);
        String badAuthorization = formatAuthorization(
                goodCredential.clientId(),
                goodCredential.keyId(), badSignature);
        require(authenticate(
                protectedRequest, List.of(badAuthorization), keys,
                clock, nonces) == null, "Bad tag rejected");
        require(authenticate(
                protectedRequest, List.of(good), keys,
                clock, nonces) != null,
                "Bad signature must not reserve nonce");

        // Thay signed target/body => MAC fail.
        Request changedTarget = new Request(
                request.method(), "/v1/orders?mode=preview",
                request.contentType(), request.timestamp(),
                newNonce(rng), request.rawBody());
        String unchangedTargetMac = sign(
                new Request(
                        request.method(), request.rawTarget(),
                        request.contentType(),
                        changedTarget.timestamp(),
                        changedTarget.nonce(),
                        changedTarget.rawBody()), newKey);
        require(authenticate(
                changedTarget, List.of(unchangedTargetMac),
                keys, clock, nonces) == null,
                "Target change invalidates MAC");

        Request changedBody = new Request(
                request.method(), request.rawTarget(),
                request.contentType(), request.timestamp(),
                newNonce(rng), "{\"amount\":900000}"
                        .getBytes(StandardCharsets.UTF_8));
        String unchangedBodyMac = sign(
                new Request(
                        changedBody.method(), changedBody.rawTarget(),
                        changedBody.contentType(),
                        changedBody.timestamp(), changedBody.nonce(),
                        body), newKey);
        require(authenticate(
                changedBody, List.of(unchangedBodyMac),
                keys, clock, nonces) == null,
                "Body change invalidates MAC");

        // Key credential đã revoked không được verify.
        KeyRecord revoked = new KeyRecord(
                AUDIENCE, "merchant-17", "key-revoked",
                KeyState.REVOKED, 0L, newSecret);
        keys.put(
                new KeyRef(AUDIENCE, "merchant-17", "key-revoked"),
                revoked);
        Request revokedRequest = new Request(
                request.method(), request.rawTarget(),
                request.contentType(), request.timestamp(),
                newNonce(rng), body);
        require(authenticate(
                revokedRequest, List.of(sign(revokedRequest, revoked)),
                keys, clock, nonces) == null,
                "Revoked key must fail authentication");

        // Stale signed timestamp reject dù có signature đúng.
        Request stale = new Request(
                request.method(), request.rawTarget(),
                request.contentType(), Long.toString(now - 301),
                newNonce(rng), body);
        require(authenticate(
                stale, List.of(sign(stale, newKey)), keys,
                clock, nonces) == null, "Stale request rejected");

        // Đổi client ID trong credential mà giữ MAC cũ:
        // key lookup/ownership hoặc HMAC phải reject.
        String changedIdentity = good.replace(
                "client_id=\"merchant-17\"",
                "client_id=\"merchant-42\"");
        require(authenticate(
                protectedRequest, List.of(changedIdentity),
                keys, clock, new LocalNonceStore()) == null,
                "Client identity must be bound to signature/key");

        // 12 verifier threads cùng một chữ ký, một nonce:
        // trong 1 JVM chỉ có đúng 1 reservation thành công.
        Request racing = new Request(
                request.method(), request.rawTarget(),
                request.contentType(), request.timestamp(),
                newNonce(rng), body);
        concurrentReplayTest(
                racing, sign(racing, newKey), keys, clock);

        System.out.println("PASS Authorization HMAC signature field tests");
    }
}
~~~

### 8.2. Chạy chương trình

Lưu khối mã vào `AuthorizationSignatureFieldDemo.java` và dùng JDK 17+:

~~~bash
javac AuthorizationSignatureFieldDemo.java
java AuthorizationSignatureFieldDemo
~~~

Kết quả kỳ vọng:

~~~text
PASS Authorization HMAC signature field tests
~~~

### 8.3. Ý nghĩa của các tests

| Test | Kỳ vọng |
|---|---|
| RFC 4231 case 1 | JCA HMAC-SHA-256 tính ra correct known-answer bytes |
| Parse `Authorization` hợp đồng | Có đúng một credential với client/key/signature |
| Đổi hoa/thường scheme hoặc param names | Parse vẫn ra cùng values theo HTTP convention |
| Thêm field `Authorization` thứ hai | Reject, không chọn first/last |
| Param lạ/lặp, scheme sai, thiếu quotes | Reject, không có fallback parser |
| Tag 43 ký tự, decode 32 byte | Hợp lệ về format; vẫn phải verify MAC |
| Padding hoặc tag ngắn | Reject |
| MAC đúng và nonce mới | Authentication tạo principal |
| Exact replay | Reject do nonce đã dùng |
| Key mới dùng lại nonce của cùng client | Reject xuyên rotation theo namespace |
| Client khác dùng cùng nonce với secret riêng | Được phép theo per-client nonce policy |
| Tag giả | Reject, không reserve nonce |
| Signed path/query/body đổi | MAC fail |
| Key revoked | Reject dù HMAC vẫn tính được |
| Timestamp quá cũ | Reject |
| Client ID bị đổi trong Authorization | Không tạo principal khác |
| 12 requests đồng thời cùng nonce | **Chỉ một** vượt qua atomic reserve trong demo |
| Principal hợp lệ nhưng resource tenant khác | Authorization deny |

### 8.4. Giới hạn triển khai

- Regex trong demo là **parser cho subset v1**, không phải HTTP grammar parser tổng quát. Bước xử lý framing, OWS và duplicate header occurrences phải do HTTP adapter thực hiện đúng **trước** khi chuyển một `List<String>` vào verifier.
- Nonce store là `ConcurrentHashMap` **không phân tán, không durable, không có eviction nền**; production cần shared atomic store với TTL thực và fail-closed policy.
- `KeyRecord` trong test là in-memory, không thay KMS/secret manager, key provenance, rotation deadlines hoặc tenant authorization thật.
- `authenticate` trả null để đơn giản hóa lỗi; không định nghĩa đầy đủ HTTP `401`/`WWW-Authenticate`, audit metadata, rate limits hay error oracle mitigation.
- Không có servlet filter, JSON schema validator, HTTP/2 gateway, reverse proxy identity boundary, mTLS giữa gateway/backend hoặc cache policy thực.
- Ví dụ chỉ ký một route grammar và raw bytes của body, không tự giải quyết arbitrary URI percent-decoding, query duplicates, transfer-encoding conflicts hoặc request content encoding. **HTTP adapter phải reject các trường hợp không có trong hợp đồng**.
- Không đưa `Authorization` nguyên chuỗi vào canonical request vì tự tham chiếu; thay vào đó ràng buộc client ID/key ID đã parse theo contract.
- `MessageDigest.isEqual` so hai tag 32 byte; phần còn lại của verifier không được suy ra constant-time.
- Tests có RFC 4231 cho engine HMAC, nhưng fixture cho canonical HTTP request và signature nên được **cross-check độc lập** với một implementation ngôn ngữ khác trong STEP 6 hoặc integration tests.


## 9. Ma trận kiểm thử chuyên biệt cho signature field

### 9.1. Cú pháp `Authorization`: đúng, sai và nhập nhằng

| Input | Kiểm tra | Kết quả |
|---|---|---|
| Một `Authorization` đúng custom scheme, đủ 3 params | Parse | **Pass** cú pháp |
| Không có `Authorization` | Multiplicity | Reject |
| Hai `Authorization` fields, dù giống hệt nhau | Multiplicity | Reject |
| `Authorization: Bearer ...` | Auth-scheme | Reject ở HMAC verifier |
| `Authorization: Basic ...` | Auth-scheme | Reject, không tự decode Basic |
| `Authorization: HMAC-SHA1 ...` | Auth-scheme | Reject, không downgrade |
| `HMAC-SHA256` viết thường, params viết hoa | Scheme/param name casing | Pass parse, **giữ nguyên value case** |
| `client_id`/`key_id` viết hoa ở **giá trị** | Identity | Chỉ pass nếu đúng record case-sensitive; không tự lowercase |
| Thiếu `signature` | Required param | Reject |
| Có hai `signature` params | Duplicate param | Reject |
| Có hai `client_id` params | Duplicate identity | Reject |
| Có param `algorithm="none"` | Unexpected param | Reject |
| Đảo thứ tự params | Subset v1 grammar | Reject theo hợp đồng minh họa |
| Dấu `;` thay vì `,` | Auth-param separator | Reject |
| Bỏ quotes quanh tag | Subset v1 grammar | Reject |
| Comma-join hai full Authorization values | Ambiguous credentials | Reject |
| Chuỗi CR/LF, NUL, obs-fold không hợp lệ | HTTP parser/field validation | Reject |
| Field value dài bất thường | Resource limit | Reject |
| Header có SP/HTAB ở biên | HTTP parsing/OWS contract | Adapter xử lý theo policy trước subset parse |
| Field `Proxy-Authorization` thay cho `Authorization` | Field identity | Không thay thế, reject thiếu Authorization |

**Không lấy** kết quả của `getHeader("Authorization")` rồi cho rằng đã phát hiện đầy đủ duplicate fields. Cần test qua HTTP server/gateway thực tế: Servlet/Netty/framework có thể có API trả một value, nhiều values hoặc các giá trị đã bị proxy gộp trước khi app nhận.

### 9.2. Signature text và binary tag

| Signature input | Kết quả |
|---|---|
| 43 ký tự Base64URL no-pad, decoded 32 byte, canonical | Parse/decode pass; còn phải verify MAC |
| 42 ký tự hoặc 44 ký tự | Reject length |
| Chữ ký có dấu `=` padding | Reject theo v1 |
| Base64 thường có `+` hoặc `/` | Reject alphabet |
| Signature hex 64 ký tự | Reject format |
| URL percent escapes `%2F`, `%3D` | Reject, không tự URL-decode |
| Space, tab, Unicode hoặc newline bên trong tag | Reject |
| Ký tự cuối có Base64 pad bits không chuẩn | Reject sau round-trip |
| Đúng 43 ký tự nhưng tag toàn byte 0 | Decode pass; **HMAC phải fail** trừ khi tag expected đúng bất thường |
| Tag bị truncate rồi server so prefix | **Lỗi thiết kế**, reject trước compare |
| Tag từ HMAC-SHA512 64 byte, encode 86 ký tự | Reject độ dài v1 |
| Tag hợp lệ nhưng sai secret | Decode pass, MAC fail |
| Tag hợp lệ nhưng sửa body/URI | Decode pass, MAC fail |
| Tag HMAC đúng nhưng timestamp cũ/nonce replay | MAC pass, **authentication reject** |

Quan sát: `decodeSignatureStrict` trả byte tag cho bước xác minh, **không phải boolean “authenticated”**. Một chuỗi Base64URL đúng format có thể do bất kỳ ai gửi; quyền sở hữu secret chỉ được chứng minh khi MAC tính lại khớp.

### 9.3. Tests bảo vệ signed fields

Cố định request base và signature hợp lệ, sau đó chỉ thay một thành phần:

| Thành phần thay đổi | Kỳ vọng |
|---|---|
| `client_id` trong Authorization | Lookup/ownership/HMAC fail |
| `key_id` trong Authorization | HMAC fail hoặc key không thuộc client |
| Raw method `POST` → `GET` | Canonicalization/route validation fail |
| Raw target `mode=commit` → `mode=preview` | HMAC fail |
| Query tự đổi thứ tự/percent-encoding | Theo contract raw target, HMAC hoặc validation fail |
| Content-Type `application/json` → loại khác | Reject validation |
| Timestamp seconds `t` → `t+1` | MAC fail nếu giữ tag gốc |
| Nonce N1 → N2 | MAC fail nếu giữ tag gốc |
| Body bytes bị thay dù JSON giống về ý nghĩa | HMAC fail với raw-body contract |
| Chỉ đổi case auth-scheme/param names | Parse vẫn giữ client/key/tag; v1 canonical bytes không đổi |
| HTTP header bị duplicate trước gateway | Reject ở HTTP adapter |
| Request gửi lại y nguyên với timestamp còn hợp lệ | HMAC pass nhưng nonce store reject |

Đừng viết test chỉ so hai signature strings mà bỏ qua **quyết định xác thực sau nonce**. Trong HMAC-SHA-256, thay message kỳ vọng làm tag thay với xác suất áp đảo; cryptographic comparison vẫn là phép so bytes, không dựa vào việc nhìn 43 ký tự signature.

### 9.4. Known-answer fixtures độc lập

Mẫu golden fixture cho một request không nhạy cảm:

~~~text
protocolVersion=hmac-authorization-v1
audience=orders-api-production
algorithm=HmacSHA256
signatureEncoding=base64url-no-padding
method=POST
rawTarget=/v1/orders?mode=commit
contentType=application/json
clientId=merchant-test
keyId=k-test1
timestamp=<canonical-epoch-seconds>
nonce=<22-chars-canonical-base64url>
rawBodyBase64=<exact-raw-body-bytes>
testSecretHex=<test-only-32-byte-secret>
expectedCanonicalText=<10-LF-delimited-lines-no-final-LF>
expectedHmacHex=<64-lowercase-hex-chars>
expectedAuthorization=<exact-HMAC-SHA256-auth-param-credential>
~~~

Expected MAC và Authorization **phải được cross-check độc lập** (ví dụ giữa Java và Go/Python, hoặc bằng công cụ tham chiếu đáng tin), không chỉ dùng cùng hàm `sign` để sinh expected rồi tự `verify`. RFC 4231 Test Case 1 giúp kiểm chứng nguyên thủy HMAC-SHA-256 trước khi thử canonical request.

### 9.5. Property-based và fuzz tests

Một bộ test tự động có thể khẳng định:

- **Parse ↔ format:** credentials hợp lệ tạo ra một representation theo v1; parse lại giữ nguyên client ID, key ID và tag text.
- **Unique credential:** zero/multiple `Authorization` field values đều reject.
- **No ambiguous params:** không có hai `signature`/`client_id`/`key_id` được accept.
- **Fixed signature length:** mọi tag accepted đều decode thành đủ 32 byte và re-encode no-pad khớp.
- **MAC binding:** thay một signed field bất kỳ làm verify fail với xác suất áp đảo nếu giữ tag.
- **Key isolation:** `clientId`/`keyId` của tenant A không thể chọn secret của B.
- **Rotation policy:** `VERIFY_ONLY` trong deadline có thể verify, `REVOKED` luôn reject.
- **Replay uniqueness:** cùng nonce của một authenticated client/audience chỉ một request pass; key ID đổi không reset nonce.
- **Authorization independence:** request có MAC/freshness/nonce pass vẫn bị deny khi resource owner khác.
- **Gateway parity:** parser/canonical bytes giống nhau qua HTTP/1.1, HTTP/2 và proxy theo contract.

Fuzz có **giới hạn độ dài, rate và resource use**. Không chạy tấn công brute-force trên production credentials hay third-party endpoints chưa được cho phép.

## 10. Troubleshooting một Authorization signature không khớp

Khi client liên tục nhận 401, điều tra theo thứ tự để tránh vô tình tắt cơ chế bảo mật:

1. **Field thực gửi:** có đúng `Authorization` (không phải `Proxy-Authorization` hay `X-Signature` của một API khác) không?
2. **Hợp đồng scheme:** `HMAC-SHA256` custom v1 đã được hai phía thống nhất chưa? Có bị nhầm RFC 9421 không?
3. **HTTP multiplicity:** có hai `Authorization` fields hoặc gateway đã gộp/loại bỏ field không?
4. **Auth-param parse:** thứ tự `client_id`, `key_id`, `signature`; quotes, dấu phẩy, spaces, case-sensitive values có đúng không?
5. **Signature encoding:** đúng 43 Base64URL no-padding chars, decode đủ 32 byte và round-trip canonical không?
6. **Key lookup:** đúng `(audience, clientId, keyId)`, key state và rotation deadline; có vô tình dùng secret của tenant khác không?
7. **Canonical bytes:** đúng method, raw path/query, signed metadata, Content-Type, raw body hash, UTF-8, LF, không LF cuối?
8. **Gateway:** WAF/proxy có đổi request target, content coding, Content-Type hay body sau khi ký không?
9. **Freshness:** `X-Timestamp` phải là Unix epoch **seconds**, không phải milliseconds; clock skew có vượt ±300 giây không?
10. **Replay:** nonce đã reserve chưa? Retry có dùng nonce mới và ký lại không?
11. **Authorization:** nếu xác thực đã thành công nhưng bị 403, phải kiểm resource/tenant/action, **không chỉnh HMAC key để sửa lỗi thiếu quyền**.

### 10.1. Những tín hiệu log an toàn

Có thể ghi structured fields đã qua validation, tùy chính sách:

~~~text
requestId=trace-7e8...
outcome=AUTHENTICATION_FAILED
failureCategory=signature_format | key_lookup | mac_mismatch |
                timestamp_out_of_window | replay_nonce |
                nonce_store_unavailable | forbidden
serviceAudience=orders-api-production
keyLookupPerformed=true
canonicalVersion=hmac-authorization-v1
headerCountAuthorization=1
signatureLength=43
~~~

**Không ghi:** shared secret, raw Authorization, received/expected full HMAC, response có dữ liệu cá nhân, body nhạy cảm hoặc signature trong URL. Nếu client/key IDs cũng là thông tin nhạy cảm, chỉ log dạng hashed/limited-access. Đối với lỗi từ nguồn không tin cậy, tránh trả ra thông tin phân biệt “key tồn tại nhưng MAC sai” với “key không tồn tại” khi điều đó tạo key enumeration oracle.

### 10.2. Ví dụ câu hỏi chẩn đoán

**Câu hỏi:** Signature có đúng 43 ký tự và decode thành 32 byte, vì sao request vẫn nhận 401?

**Trả lời:** Vì **format pass không chứng minh MAC**. Có thể lookup sai secret, canonical bytes không khớp, timestamp quá cũ, nonce đã dùng, key bị revoke hoặc headers bị proxy rewrite. Phân tầng kiểm tra, không dùng “decode thành công” làm điều kiện accept.

**Câu hỏi:** Client đổi key ID trong Authorization rồi dùng một tag mới ký bằng secret của key mới. Vậy request có được accept?

**Trả lời:** Chỉ nếu key ID mới thực sự thuộc cùng principal/audience, state cho phép verify, canonical request mới ràng buộc key ID, timestamp và nonce hợp lệ. Nếu tái sử dụng nonce đã được client dùng dưới key cũ, policy per-client nonce của bài **vẫn reject**.

**Câu hỏi:** Thêm một auth-param `signature2` để hỗ trợ song song hai thuật toán được không?

**Trả lời:** Không trong v1. Cần version mới, thuật toán được đàm phán theo policy rõ, quy tắc covered components, key rotation, canonicalization và parser tương ứng. Thêm trường không được ký/không được kiểm soát có thể tạo algorithm confusion.

## 11. Các sai lầm phổ biến

1. **Gọi tên `Authorization` rồi mặc định đã phân quyền:** trường này chỉ mang credentials.
2. **Nhầm `signature` auth-param với `Signature` field RFC 9421:** hai giao thức khác nhau.
3. **Dùng `Bearer`/`Basic` decoder cho HMAC custom scheme:** sai grammar và ý nghĩa dữ liệu.
4. **Chấp nhận duplicate Authorization:** proxy/backend có thể chọn credentials khác nhau.
5. **Parse auth-params bằng `split(",")` không kiểm quote/duplicate:** dễ tạo parameter confusion.
6. **Lấy value từ regex không full-match:** một credential hợp lệ có thể bị nối thêm malicious param nhưng vẫn parse pass.
7. **Tự lowercase client/key ID:** danh tính có thể bị nhập nhằng; chỉ case-fold scheme/param names.
8. **Cho client chọn `alg=none`/HMAC-SHA1:** algorithm downgrade.
9. **Nhầm key ID với secret:** lộ secret trong header hoặc chọn sai key record.
10. **Chấp nhận padded/Base64 thường/hex mà không version:** nhiều biểu diễn, parser mismatch.
11. **So HMAC bằng string/prefix:** mở timing side channel hoặc truncated-tag acceptance.
12. **Ký cả raw Authorization chứa signature:** tạo vòng tự tham chiếu.
13. **Không ký client ID/key ID:** header selectors có thể bị đổi gây identity confusion.
14. **Không ký method/URI/body:** chữ ký không ràng buộc hành vi thực tế.
15. **Tự normalize URI, decompress body sau khi ký:** expected MAC khác hoặc business đọc khác verifier.
16. **Không kiểm timestamp/nonce:** replay nguyên request với tag đúng.
17. **Dùng nonce namespace theo key ID không chủ ý:** rotation vô tình làm nonce có thể tái sử dụng.
18. **Tin `X-Verified-Client` từ client Internet:** bypass authentication boundary.
19. **Log toàn bộ Authorization:** lộ credential/tag và dữ liệu nhạy cảm.
20. **Bỏ authorization sau HMAC thành công:** authenticated client vẫn có thể truy cập sai tenant.
21. **Dùng idempotency thay nonce:** hai cơ chế bảo vệ hai loại lặp khác nhau.
22. **Cache response trước auth hoặc cho caller khác:** lộ resource ngay cả khi chữ ký đúng.
23. **Thử mọi secret để xem key nào khớp:** rò key-state, DoS, cross-tenant confusion.
24. **Cho key REVOKED vẫn verify:** toán học MAC đúng không vượt qua key policy.

## 12. Bài tập thực hành

**Bài 1 — Parse wire syntax.** Phân tích `Authorization: HMAC-SHA256 client_id="merchant-17", key_id="k-2026-11", signature="..."`. Thành phần nào là scheme, auth-param name, value, tag? Value nào phải có chính xác 43 ký tự?

**Bài 2 — Signature vs Authorization.** So sánh custom `Authorization` của bài với hai fields `Signature-Input` và `Signature` của RFC 9421. Vì sao không thể chỉ đổi tên header rồi hy vọng verify đúng?

**Bài 3 — Decoder strict.** Viết hàm Java 17 nhận `signature` value, reject padding/dấu `+`/`/`/hex/Unicode, decode đủ 32 byte, encode lại rồi so. Vì sao cần canonical round-trip?

**Bài 4 — Duplicate headers.** Gateway nhận hai `Authorization` fields, backend chỉ lấy value đầu. Hãy mô tả cách hai tầng có thể hiểu khác nhau và chỉ rõ nơi phải reject.

**Bài 5 — Duplicate auth-params.** Client gửi hai tham số `signature` trong một credential. Nếu parser chọn giá trị cuối trong khi WAF kiểm tra giá trị đầu, điều gì có thể xảy ra? Hãy sửa parser.

**Bài 6 — Signed key selector.** Client đang dùng key `old` chuyển sang `new`. Tại sao key ID cần nằm trong canonical bytes dù chính raw Authorization chứa signature không được đưa vào?

**Bài 7 — Canonical target.** Sender ký `/v1/orders?mode=preview` nhưng gateway đổi thành `mode=commit`. So sánh kết quả strict parse, decode Base64URL và cryptographic verify.

**Bài 8 — Body mutation.** Proxy tự reserialize JSON từ `{"amount":150000}` thành `{"amount": 150000}`. HMAC tính trên raw bytes có thể khác thế nào? Nếu muốn hai JSON bytes tương đương cần contract bổ sung nào?

**Bài 9 — Authentication vs authorization.** Merchant A có đúng shared secret và HMAC hợp lệ, timestamp/nonce mới, nhưng yêu cầu order của merchant B. Cần trả kết quả ở những lớp nào?

**Bài 10 — Key rotation và replay.** Cùng nonce N được gửi bằng key cũ rồi gửi bằng key mới của cùng client. Namespace nonce có nên chứa key ID không nếu policy là một nonce một lần cho mỗi client/audience?

**Bài 11 — Gateway challenge.** Phân biệt `Authorization`, `Proxy-Authorization` và `WWW-Authenticate`. Custom scheme cần công bố thêm những gì để client có thể xử lý challenge 401 đúng?

**Bài 12 — Header grammar.** Đánh giá việc thay `client_id="merchant-17"` thành `client_id=merchant-17` hoặc đảo thứ tự các param. Một số kiểu biểu diễn có thể đúng grammar HTTP chung; vì sao custom v1 parser vẫn reject?

**Bài 13 — Incident response.** Phát hiện log đang ghi đầy đủ Authorization header. Nêu các bước giảm rủi ro, kiểm soát retention, đánh giá nonce/timestamp replay window và cập nhật redaction.

**Bài 14 — Test design.** Xây bộ fixture cross-language gồm secret test, method/raw URI, client/key IDs, signed timestamp/nonce, raw body hash, canonical bytes, expected raw HMAC, Base64URL tag và exact Authorization credential.

**Bài 15 — Rate limiting.** Một attacker gửi hàng triệu credentials malformed hoặc key IDs không tồn tại. Thiết kế giới hạn kích thước header, CPU, lookup rate và thông báo lỗi, không tiết lộ secret hay key existence.

## 13. Checklist sản xuất

| Lớp | Điều cần xác nhận |
|---|---|
| **Protocol** | Có một version custom HMAC scheme rõ; không nhầm RFC 9421/Bearer/Basic |
| **Header identity** | Đúng một Authorization, không sử dụng Proxy-Authorization thay thế |
| **Grammar** | Parser full-match; scheme/param casing đúng HTTP; values case-sensitive; reject extras/duplicates |
| **Size & ASCII** | Giới hạn header, token length, control characters và HTTP framing |
| **Encoding** | `signature` 43 Base64URL no-pad chars, decoded 32 bytes, round-trip canonical |
| **Cryptography** | HMAC-SHA-256 full tag; JCA `Mac`; `MessageDigest.isEqual` trên raw byte arrays |
| **Key identity** | Lookup `(audience, clientId, keyId)` từ trusted store; state ACTIVE/VERIFY_ONLY/REVOKED |
| **Canonical request** | Ký method, raw target/query, content type, client/key IDs, timestamp, nonce, body hash |
| **No self-reference** | Không đưa raw Authorization chứa signature vào canonical request |
| **Replay** | Timestamp seconds, bounded skew, 16-byte CSPRNG nonce, atomic shared nonce store, TTL đủ dài |
| **Gateway** | Proxy không rewrite signed fields trước verify; HTTP/1.1/2 normalization kiểm thử |
| **Principal** | Chỉ tạo authenticated principal sau key/MAC/nonce thành công |
| **Authorization** | Kiểm action/resource/owner/tenant bằng dữ liệu server đáng tin |
| **Retry** | Retry dùng nonce/timestamp/HMAC mới; idempotency key ổn định nếu cùng business intent |
| **Caching** | Không bypass auth; private response policy, cache controls và principal scoping |
| **Observability** | Redact Authorization/secret/tag; không phơi expected MAC trong log/error |
| **QA** | RFC 4231 vector, golden canonical fixtures, fuzz parser, signature tamper và gateway integration tests |

## 14. Kết luận

**Signature field trong Authorization header** là cách đóng gói **MAC tag** thành một auth-param của **custom HTTP authentication scheme**. Giá trị `signature` không phải secret, không phải bearer token và không phải `Signature` field của RFC 9421. Với hợp đồng `hmac-authorization-v1`, client gửi một `Authorization` gồm `client_id`, `key_id` và chữ ký Base64URL no-padding của full HMAC-SHA-256 tag.

Thiết kế an toàn yêu cầu **parser không nhập nhằng**, khóa được lookup theo principal/audience đúng, canonical request bảo vệ đầy đủ method/URI/headers/body, strict decode tag 32 byte và so bằng `MessageDigest.isEqual`. Sau khi MAC khớp, receiver vẫn phải **kiểm timestamp, reserve nonce chống replay, quản lý key rotation và authorization theo tài nguyên thực**. Những lớp đó không thay thế nhau; một request có syntax/tag hợp lệ chưa chắc đã được xác thực, và một client được xác thực cũng chưa chắc có quyền thực hiện hành động.

**Tài liệu tham khảo:**

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP authentication framework, `Authorization`, `WWW-Authenticate`, auth-scheme và auth-params.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): request parsing/framing, header field processing và intermediary behavior.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): pseudo-headers và chuyển giao thức.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): `Signature-Input`, `Signature` và covered components; **khác custom HMAC Authorization v1**.
- [RFC 8941 — Structured Field Values for HTTP](https://www.rfc-editor.org/rfc/rfc8941): syntax Structured Fields được RFC 9421 sử dụng.
- [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104): keyed-hash message authentication.
- [RFC 4231 — HMAC-SHA-256 Test Vectors](https://www.rfc-editor.org/rfc/rfc4231): known-answer tests cho HMAC nguyên thủy.
- [RFC 4648 — Base-N Encodings](https://www.rfc-editor.org/rfc/rfc4648): Base64URL, padding và canonical pad bits.
- [Java SE 17 — Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): `HmacSHA256`, `init`, `doFinal`.
- [Java SE 17 — Base64](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html): URL-safe encoder/decoder.
- [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): `isEqual` để so raw HMAC tags.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): tạo nonce CSPRNG.
- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): clock injection, fixed-clock tests.
- [Redis — SET command](https://redis.io/docs/latest/commands/set/): `NX`, `EX` và `PX` cho nonce atomic reservation khi dùng datastore phân tán.





