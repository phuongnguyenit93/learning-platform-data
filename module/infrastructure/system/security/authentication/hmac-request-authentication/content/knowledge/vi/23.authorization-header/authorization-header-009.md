# Header injection

Trong HTTP request authentication, **header injection** xảy ra khi dữ liệu do một bên không đáng tin kiểm soát khiến HTTP parser, proxy, gateway, logging layer hoặc ứng dụng **tạo ra, chấp nhận, hợp nhất hay diễn giải các header fields khác với hợp đồng ban đầu**. Với HMAC, hậu quả có thể nghiêm trọng hơn một lỗi parse thông thường: verifier tính chữ ký trên **một tập header/URI/metadata**, nhưng backend hoặc thành phần khác lại quyết định identity, route, quyền hoặc payload dựa trên **một cách diễn giải khác**.

Các dạng thường gặp gồm CRLF/control-character injection, **duplicate Authorization headers**, khác biệt giữa tên header viết hoa/thường, header folding lịch sử, dấu phẩy được hợp nhất sai, HTTP/2 → HTTP/1.1 conversion, HTTP request smuggling, spoof các header `X-Forwarded-*` hoặc `X-Authenticated-*`, và nhầm lẫn giữa authentication schemes. Không phải dạng nào cũng trực tiếp tạo ra một HMAC tag hợp lệ; điểm chung là **phá ranh giới tin cậy giữa dữ liệu caller gửi và dữ liệu hệ thống xác minh/sử dụng**.

Bài này thuộc chương **Authorization header** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Mô-đun hướng dẫn xác thực HTTP request bằng HMAC với **shared secret** và **canonical request** gồm method, URI, signed headers hoặc body; người học cần xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt **authentication** với **authorization**.

> **Nguyên tắc cốt lõi:** HTTP parser phải chặn framing/control-byte nhập nhằng; gateway và verifier phải thống nhất chính xác **một Authorization field, một authentication scheme, một set signed fields và một request semantics**. Nếu các tầng có khả năng hiểu khác nhau, **từ chối request** thay vì thử các cách parse/canonicalization khác nhau đến khi HMAC khớp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích header injection và những điều kiện khiến nó ảnh hưởng đến HMAC authentication.
2. Phân biệt **CRLF injection**, **duplicate-header ambiguity**, **header concatenation**, **request smuggling** và **trusted-proxy header spoofing**.
3. Thiết kế cú pháp `Authorization` chứa metadata HMAC có version, giới hạn kích thước và format rõ ràng.
4. Bảo đảm chỉ **một** Authorization field hợp lệ được phép đến verifier.
5. Nêu vì sao canonical request phải được tái tạo từ **request tại signing boundary** mà không tin canonical string caller khai.
6. Viết Java 17 strict parser và decoder cho `Authorization: HMAC-V1 ...`.
7. Sử dụng `javax.crypto.Mac`, `MessageDigest.isEqual` và header adapter một cách phù hợp.
8. Kiểm thử HTTP/1.1, HTTP/2, gateway/proxy rewrites, duplicate fields, spoofed identity và smuggling-related parser differentials.
9. Kết hợp xác thực HMAC với timestamp/nonce, key lifecycle, authorization và audit an toàn.
10. Phân biệt lỗi **ký request không khớp** với lỗi **parser nhìn nhận request khác nhau**.

## 2. Header injection có ý nghĩa gì trong bài toán HMAC?

HTTP request về mặt ứng dụng thường được diễn giải thành:

~~~text
start-line / HTTP/2 pseudo-headers
header fields
message body

    -> request method
    -> target / path / query
    -> named header values
    -> body bytes
~~~

HMAC bảo vệ một canonical representation được hai phía thỏa thuận:

~~~text
expectedTag = HMAC(secretBytes, canonicalRequestBytes)
~~~

Nhưng nếu:

~~~text
Verifier nhìn: Authorization = HMAC-V1 credential của A
Handler nhìn:  Authorization hoặc identity header của B
~~~

hoặc:

~~~text
Verifier hash body/URI của request X
Router xử lý body/URI của request Y
~~~

thì HMAC có thể chứng minh một điều **khác** với điều ứng dụng dùng để đưa ra quyết định. Không thể khắc phục tình huống này chỉ bằng cách chọn SHA-384 thay SHA-256, hoặc so HMAC tag constant-time hơn; phải sửa **parsing và trust boundary**.

### 2.1. Header injection không đồng nghĩa HMAC forgery

Attacker không biết shared secret thường **không thể tự tạo HMAC hợp lệ** cho canonical bytes bị thay đổi. Tuy nhiên, attacker có thể:

- Lợi dụng verifier và handler chọn **hai giá trị khác nhau** từ các duplicate headers.
- Làm gateway tạo hoặc giữ lại một identity header không đáng tin.
- Đẩy parser vào trường hợp một tầng thấy **một request**, tầng khác thấy **hai requests**.
- Tái sử dụng signed request cũ khi nonce/replay gate không được triển khai đúng.
- Kết hợp các signed và unsigned fields khiến business semantics thay đổi trong khi MAC của signed subset không đổi.

Đây là lý do phải xem xét cả **ngữ nghĩa của request đã được ký** và **ngữ nghĩa cuối cùng được thực thi**.

### 2.2. Các lớp vấn đề khác nhau

| Dạng | Ví dụ | Ranh giới bị ảnh hưởng |
| --- | --- | --- |
| CRLF injection | Giá trị chứa carriage return + line feed để tạo field mới | Bytes → HTTP header parser |
| Header duplication | Có hai field `Authorization` | Multiplicity/first-wins/last-wins |
| Case variation | `Authorization` và `authorization` | HTTP field name case-insensitivity |
| Comma coalescing | Proxy gộp hai Authorization values bằng dấu phẩy | Field list semantics |
| obs-fold | Dòng header tiếp theo bắt đầu bằng whitespace | Legacy folding và normalization |
| HTTP request smuggling | Framing mâu thuẫn giữa proxy/backend | Message boundary |
| Forwarded-header spoofing | Caller khai `X-Authenticated-User` | Identity giữa gateway/backend |
| Canonicalization mismatch | Header/URI bị chuẩn hóa không nhất quán | Signed request vs routed request |
| Scheme confusion | `Basic`, `Bearer`, `HMAC-V1` xử lý bởi nhiều filters | Authentication routing |
| Response header injection | Dữ liệu user bị phản chiếu thành `Location`/`Set-Cookie` | Server response generation |

Không phải mọi mục trên đều là cùng một lỗ hổng; bài học phân tích chúng trong phạm vi một endpoint HMAC có nhiều trung gian HTTP.

## 3. CRLF injection và ranh giới của HTTP parser

Trong HTTP/1.1, các header lines được phân tách bằng **CRLF**, tức byte `0x0D` theo sau byte `0x0A`. Nếu một ứng dụng ghép chuỗi không đáng tin để tạo raw HTTP header mà không validate, ký tự phân dòng có thể tạo thêm header field hoặc thay message boundary.

Ví dụ **dữ liệu độc hại minh họa**, không phải một request hợp lệ được phép xử lý:

~~~text
X-Client-Label: partnerA\r\nX-Authenticated-User: admin
~~~

Nếu một component mắc lỗi tự ghép raw headers:

~~~text
"X-Client-Label: " + untrustedLabel + "\r\n"
~~~

nó có thể biến `\r\n` trong giá trị thành dòng header mới. **HTTP parser chuẩn và HTTP client/server libraries hiện đại cần từ chối CR/LF control bytes trong field value**, không được “sanitize bằng cách xóa ký tự rồi tiếp tục xác thực” theo những quy tắc khác nhau.

### 3.1. Các nguồn đưa ký tự điều khiển vào header

- User input được đặt trực tiếp vào custom authentication/identity header.
- Giá trị từ URL/query/body được copy sang header bằng gateway script.
- Proxy metadata được lấy từ `X-Forwarded-*` do Internet tự khai.
- Code tự serialize HTTP request hoặc tự dựng response header bằng string concatenation.
- Dữ liệu không tin cậy được sử dụng để tạo header khi gọi downstream.
- Chuyển đổi HTTP/2 ↔ HTTP/1.1 hoặc adapter có cách kiểm tra control bytes khác nhau.

**Biện pháp:** Sử dụng HTTP libraries chuẩn, validate trường ở biên nhận, từ chối CTL/CR/LF theo contract, không đưa chuỗi không tin cậy vào raw header framing.

### 3.2. CRLF trong Java String là dữ liệu không hợp lệ

~~~java
String attackerValue = "partner-a\r\nX-Authenticated-User: admin";

// Không được ghi trực tiếp attackerValue vào raw HTTP header line.
~~~

Trong Java source, `\r` và `\n` là các escape sequences biểu diễn CR và LF. HTTP adapter phải từ chối field value chứa các ký tự đó **trước khi canonicalize hoặc chuyển tiếp**.

### 3.3. Không chỉ kiểm `\r\n` liền nhau

Một policy strict nên xem xét cả:

- `CR` đơn lẻ.
- `LF` đơn lẻ.
- `NUL` và các C0 control bytes khác.
- `DEL`.
- Tab/whitespace ngoài vị trí đã công bố.
- Non-ASCII/Unicode trong metadata HMAC nếu contract chỉ cho ASCII.
- Header length vượt giới hạn.
- Duplicate names và field values bị gộp.

Không chỉ thay chuỗi `"\r\n"` bằng `""`: attacker có thể dùng biểu diễn khác, và các tầng khác nhau có thể normalize khác nhau. Với authentication header, **reject** là mặc định an toàn hơn “repair”.

## 4. Duplicate Authorization: cùng tên field nhưng nhiều giá trị

Tên HTTP field **không phân biệt chữ hoa/thường**. Đây là các tên tương đương:

~~~http
Authorization: HMAC-V1 ...
authorization: HMAC-V1 ...
AUTHORIZATION: HMAC-V1 ...
~~~

Nếu caller gửi cả ba, request chứa **ba occurrences của cùng một field**, không phải ba identity channels riêng. `Authorization` không phải một list field tùy ý có thể nối các credentials bằng dấu phẩy rồi xem như một credential.

Ví dụ nhập nhằng:

~~~http
Authorization: HMAC-V1 partner-a-k3.1800000030.6bfb21974a08417199273b09ca49a3ec.<tagA>
authorization: Bearer <tokenB>
~~~

Một tầng có thể lấy header đầu; tầng khác lấy header cuối; một proxy khác có thể gộp hai giá trị thành một chuỗi có dấu phẩy. Nếu gateway xác thực identity A nhưng backend chọn B, **principal của request đã ký và principal của request được xử lý không còn thống nhất**.

### 4.1. Chính sách khuyến nghị: exactly one Authorization field

Với HMAC endpoint V1 trong bài:

1. HTTP edge phát hiện **mọi occurrences** của `Authorization`, so tên **case-insensitive**.
2. Nếu không có field: từ chối vì thiếu thông tin xác thực.
3. Nếu nhiều hơn một field: từ chối, **kể cả nội dung trùng nhau**.
4. Nếu field đã bị proxy merge thành một chuỗi có comma ngoài grammar: từ chối.
5. Chỉ sau đó mới parse authentication scheme và credential grammar.
6. Backend cũng thực thi một contract thống nhất; gateway không được che sự nhập nhằng.

### 4.2. Vì sao getHeader() có thể không đủ?

Một API framework thường trả **một** giá trị:

~~~java
String value = request.getHeader("Authorization");
~~~

Nhưng nếu incoming request có nhiều Authorization lines, `getHeader` có thể chọn một giá trị theo behavior của container, còn tầng khác chọn giá trị khác. Vì vậy cần một HTTP adapter có khả năng kiểm tra số occurrences trước khi các middleware gộp/loại/trích một field.

Với Servlet:

~~~java
Enumeration<String> values = request.getHeaders("Authorization");
~~~

hữu ích để kiểm tra các giá trị container **còn giữ lại**, nhưng không đảm bảo luôn nhìn được **toàn bộ raw header occurrences trước reverse proxy**. Edge/gateway phải reject ambiguity **từ sớm**, không chỉ trông vào application container sau các phép rewrite.

### 4.3. Header name case normalization

Không tự viết logic kiểu:

~~~java
if (name.equals("Authorization")) {
    // Chỉ đúng với chữ A viết hoa.
}
~~~

Khi làm việc trên raw HTTP field names, dùng so sánh không phân biệt case theo quy tắc ASCII HTTP; HTTP/2 yêu cầu tên field ở dạng lowercase, và chuyển HTTP/2 → HTTP/1.1 không được tạo ra một cách chọn header khác nhau. Trong Java adapter đã có `getHeaders("Authorization")`, vẫn cần biết gateway/container có phát hiện duplicate names trước merge hay không.

## 5. HTTP header coalescing và dấu phẩy

Một số HTTP field definitions cho phép cú pháp **danh sách**, nên có thể kết hợp occurrences bằng dấu phẩy theo luật tương ứng. **Không được tự áp dụng quy tắc này cho Authorization credentials**.

Nếu proxy chuyển:

~~~http
Authorization: HMAC-V1 <credentialA>
Authorization: Bearer <credentialB>
~~~

thành:

~~~http
Authorization: HMAC-V1 <credentialA>, Bearer <credentialB>
~~~

hệ thống có thể phát sinh:

- Gateway hiểu credential A, backend parse B.
- Parser split trên comma dù grammar HMAC V1 không cho comma.
- Filter Basic/Bearer chạy trước filter HMAC.
- Audit log chọn identity khác với security context.
- Một phần Authorization bị bỏ qua thay vì bị từ chối.

**Thiết kế đúng:** HMAC-V1 grammar **không chứa comma**, và request có multiple Authorization fields phải bị reject ở biên chưa gộp. Đừng “split theo comma rồi lấy cái đầu” hay “thử từng credential”.

## 6. Authentication scheme confusion

`Authorization` là kênh HTTP authentication; scheme thông báo cách diễn giải credentials. Nhiều API cùng triển khai `Basic`, `Bearer` và HMAC có thể có middleware routing phức tạp.

Ví dụ endpoint chỉ cho phép HMAC:

~~~http
Authorization: HMAC-V1 <credential>
~~~

Không nên:

- Nhận `Basic` hoặc `Bearer` trên endpoint HMAC rồi chuyển principal ngầm.
- Thử Basic/Bearer/HMAC tuần tự trên cùng một giá trị “đến khi có một cái hợp lệ”.
- Cho phép client tự chọn `algorithm=none` hoặc “HMAC scheme version 0” không được policy cho phép.
- Dùng `X-Api-Key` hay cookie như fallback mà không có endpoint policy rõ ràng.
- Bỏ qua Authentication result của gateway rồi tạo principal từ header do client gửi.

### 6.1. Scheme token và field name có quy tắc khác nhau

Theo HTTP authentication, **authentication scheme names được so sánh case-insensitive**. Hợp đồng V1 có thể chấp nhận `HMAC-V1`, `hmac-v1` hoặc `Hmac-V1` nhưng **đưa về cùng phiên bản**, không suy version từ string tự do.

Ngược lại, key ID, nonce, signature encoding và các thành phần trong canonical request có thể yêu cầu case-sensitive/canonical representation. Chỉ vì scheme name không phân biệt case **không có nghĩa** mọi metadata đều được lowercase.

### 6.2. Tối thiểu hóa surface

Nếu endpoint luôn yêu cầu HMAC, filter kiểm tra đúng một scheme. Với endpoint nhiều schemes, cần explicit routing order, scope, issuer/credential separation và principal construction policy; tránh một request được “upgrade identity” từ header do caller tự khai.

## 7. Hợp đồng minh họa Authorization HMAC-V1

Để minh họa strict parsing, bài chọn một protocol đơn giản, **không phải chuẩn HMAC Authentication chung của Internet**.

~~~http
Authorization: HMAC-V1 partner-a-k3.1800000030.6bfb21974a08417199273b09ca49a3ec.<43-char-base64url-signature>
~~~

Credential phần sau dấu cách gồm **bốn segments** phân tách bằng dấu chấm:

~~~text
<keyId>.<unixSeconds>.<nonceHex>.<tagBase64Url>
~~~

| Thành phần | Grammar V1 |
| --- | --- |
| Scheme | `HMAC-V1`, so tên scheme case-insensitive |
| Separator sau scheme | **Đúng một** ASCII space |
| Key ID | `[A-Za-z0-9_-]{1,64}`, không chứa dot |
| Timestamp | `0` hoặc `[1-9][0-9]{0,18}`; parse vào `long` |
| Nonce | `[0-9a-f]{32}` (16 byte random lowercase hex) |
| Signature | `[A-Za-z0-9_-]{43}`, Base64URL **no padding** |
| Decoded tag | **32 byte** HMAC-SHA256 đầy đủ |
| Total header length | Giới hạn theo max của grammar, ví dụ không quá **256 chars** |
| Header count | **Chính xác một** Authorization field |
| Control/Unicode | Chỉ ASCII theo grammar; reject CTL, tabs, CR/LF, Unicode |
| Authentication fallback | Không có Basic/Bearer fallback cho endpoint này |
| Audience | Do service/credential policy xác nhận, không do caller tự chọn tùy ý |

Đây là **hợp đồng minh họa**. Nếu API phải tương thích một scheme HMAC đã được đối tác định nghĩa, cần dùng chính grammar của scheme đó và xây parser tương ứng, không tự đổi wire format.

### 7.1. Ưu điểm của grammar cố định

- Dễ từ chối dấu phẩy, whitespace lạ, dấu chấm dư hoặc auth-params lặp.
- Dễ parse theo `Pattern.matcher(...).matches()`, không phải split/trim tự do.
- Metadata được giới hạn length trước decode và key lookup.
- Không có khả năng client khai thêm signed-header names trong chính Authorization mà verifier âm thầm bỏ qua.
- Signature được strict Base64URL decode và so **byte tag**, không so string theo prefix.
- Protocol version rõ ràng; muốn thay algorithm/key format phải tạo version mới với policy riêng.

### 7.2. Không coi metadata trong Authorization là đáng tin trước MAC

`keyId`, `timestamp` và `nonce` nằm trong Authorization chỉ là **claims của caller**. Server cần ràng buộc những giá trị này trong canonical request đã ký, dùng keyId để tra trusted key registry, rồi mới chấp nhận principal.

Không dùng timestamp/nonce do header Authorization cung cấp để claim replay store **trước khi HMAC hợp lệ**.

## 8. Canonical request phải bảo vệ metadata HMAC

Ví dụ:

~~~http
POST /v1/orders/42?dryRun=false HTTP/1.1
Host: api.example.test
Content-Type: application/json
Authorization: HMAC-V1 partner-a-k3.1800000030.6bfb21974a08417199273b09ca49a3ec.<signature>

{"status":"confirmed"}
~~~

Canonical text minh họa:

~~~text
HMAC-REQUEST-V1
POST
/v1/orders/42
dryRun=false
audience:orders-api
content-type:application/json
key-id:partner-a-k3
timestamp:1800000030
nonce:6bfb21974a08417199273b09ca49a3ec
body-sha256:<actual-sha256-hex-of-raw-body>
~~~

Các dòng được nối bằng LF và encode UTF-8, không có trailing LF theo contract. `<actual-sha256-hex-of-raw-body>` phải được thay bằng digest thật do **server tính từ raw body bytes**; giá trị trong ví dụ không phải test vector có tag sẵn.

**Authorization header chứa tag đầu ra không nên được đưa nguyên vẹn vào HMAC input**, nếu không tạo phụ thuộc vòng tròn. Tuy nhiên, **keyId, timestamp, nonce và version** có tác động xác thực phải được ràng buộc trong canonical representation. Server có thể đưa một **protocol marker** `HMAC-REQUEST-V1` vào signed bytes và chọn algorithm từ **server-side key policy**.

### 8.1. Bị thay key ID hoặc nonce sẽ ra sao?

Nếu attacker lấy signed request của k3 rồi đổi key ID thành k4:

- Trusted key registry chọn credential k4 (hoặc không có).
- Canonical bytes chứa `key-id:k4` khác.
- Expected HMAC được tính theo secret khác hoặc request bị từ chối.
- Không có cơ chế “thử mọi secret đến khi một cái khớp”.

Nếu attacker đổi nonce giữ nguyên tag, canonical bytes khác và MAC không khớp. Replay store chỉ được ghi sau khi MAC hợp lệ, nên nonce giả không làm bẩn trạng thái.

### 8.2. Signed headers khác với unsigned headers

Nếu business handler dùng `X-Tenant-Id`, `X-Acting-User`, `X-Transfer-Account` hoặc route authority để quyết định quyền, cần chính sách rõ:

- Signed nếu giá trị đó là phần dữ liệu request có ý nghĩa bảo mật.
- Và/hoặc không dùng header do client tự khai làm nguồn quyền.
- Lấy principal/tenant/scope từ key registry và policy server-side.
- Đảm bảo verifier và handler nhìn cùng header values và request target.

Một HMAC đúng trên method/path/body **không chứng minh** một unsigned header `X-Role: admin` đáng tin.

## 9. Header injection đi qua proxy/gateway

Một request có thể đi theo nhiều tầng:

~~~mermaid
flowchart LR
    C[Internet client] --> E[Edge HTTP parser]
    E --> G[API gateway / WAF]
    G --> V[HMAC verifier]
    V --> R[Router and authorization]
    R --> B[Business handler]
~~~

Những biến đổi có thể có:

- HTTP/2 pseudo-headers `:method`, `:scheme`, `:authority`, `:path` được chuyển thành HTTP/1.1 request semantics.
- Header names bị lowercase; gateway gộp/loại/đổi signed header values.
- Duplicate Authorization fields được chọn first-wins hoặc last-wins.
- Path prefix bị strip/rewrite; encoded slash và dot segments được decode khác nhau.
- Query duplicate keys hoặc percent-encoding được xử lý khác nhau.
- JSON body bị parse/serialize lại, khiến SHA-256 raw bytes khác.
- Identity headers được thêm bởi gateway hoặc được client giả mạo.
- Request framing không thống nhất giữa proxy/backend.

### 9.1. Điểm đặt verifier

**Verify tại edge/gateway:** HMAC được xác minh trên external representation trước khi rewrite. Gateway chỉ chuyển authenticated principal qua một internal trust boundary bảo vệ và backend phải chặn đường bypass. Mọi header identity do Internet gửi phải bị strip trước khi gateway gắn thông tin tin cậy.

**Verify tại backend:** Gateway phải giữ signed semantics hoặc dùng mapping đáng tin, được version hóa, mà signer/verifier cùng biết. Không tin `X-Original-URI` do Internet tự khai như một nguồn để khôi phục path đã ký.

### 9.2. Header injection trong proxy-provided identity

Giả sử gateway thêm:

~~~http
X-Authenticated-Client: partner-a-service
~~~

Nếu client Internet cũng được gửi field cùng tên và gateway không xóa nó, backend có thể thấy hai values hoặc lấy value của client. **Không dùng header này làm danh tính** trừ khi gateway xóa giá trị từ upstream, tự tạo giá trị sau xác thực và bảo vệ đường truyền/gateway identity tới backend.

Nên dùng mTLS hoặc cơ chế bảo vệ internal authentication context tương đương, và **chặn trực tiếp truy cập backend** từ Internet.

### 9.3. HTTP request smuggling và framing

Một lớp rủi ro khác là proxy/backend có thể hiểu **message boundaries** khác nhau, ví dụ do xử lý `Content-Length` và `Transfer-Encoding` mâu thuẫn hoặc HTTP/2 downgrade không nhất quán. Điều này có thể làm một tầng xác minh request X còn tầng sau xử lý request Y.

Bài này không hướng dẫn khai thác smuggling; yêu cầu phòng thủ là **parser nghiêm ngặt**, reject framing ambiguity, cấu hình proxy/backend thống nhất, kiểm thử end-to-end bằng request malformed trong môi trường được phép và không tái sử dụng pooled downstream connection với trạng thái framing mơ hồ.

## 10. Java 17: strict parser cho Authorization HMAC-V1

Ví dụ dưới đây cố tình **chỉ chấp nhận một grammar cụ thể**. Không dùng `split(",")` để tìm credential, không gọi `trim()` để sửa request, không phân tích arbitrary `key=value` parameters rồi bỏ qua khóa lạ.

### 10.1. Parser và mô hình credential

~~~java
import java.util.Base64;
import java.util.Enumeration;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class AuthorizationHmacV1 {
    /**
     * Scheme name case-insensitive theo HTTP authentication.
     * Metadata và Base64URL signature vẫn canonical/case-sensitive.
     *
     * Wire format:
     * HMAC-V1 <keyId>.<unixSeconds>.<32-lower-hex-nonce>.<43-char-tag>
     */
    private static final Pattern HEADER = Pattern.compile(
            "(?i:HMAC-V1) "
            + "([A-Za-z0-9_-]{1,64})"
            + "\\.(0|[1-9][0-9]{0,18})"
            + "\\.([0-9a-f]{32})"
            + "\\.([A-Za-z0-9_-]{43})");

    private static final int MAX_HEADER_CHARS = 256;
    private static final int TAG_BYTES = 32;

    public record Credential(
            String keyId, long timestampSeconds,
            String nonceHex, byte[] presentedTag) {}

    private AuthorizationHmacV1() {}

    /**
     * HTTP adapter phải cung cấp tất cả values của Authorization field
     * chưa bị gộp/loại mất bởi thành phần upstream.
     */
    public static String requireSingle(
            Enumeration<String> authorizationValues) {

        if (authorizationValues == null
                || !authorizationValues.hasMoreElements()) {
            throw new IllegalArgumentException(
                    "Missing Authorization header");
        }

        String only = authorizationValues.nextElement();

        if (authorizationValues.hasMoreElements()) {
            // Reject kể cả khi hai values trùng nhau.
            throw new IllegalArgumentException(
                    "Duplicate Authorization header");
        }

        return only;
    }

    public static Credential parse(String rawHeaderValue) {
        if (rawHeaderValue == null
                || rawHeaderValue.isEmpty()
                || rawHeaderValue.length() > MAX_HEADER_CHARS) {
            throw new IllegalArgumentException(
                    "Invalid Authorization");
        }

        // Reject CR, LF, NUL, TAB, DEL, Unicode và các CTL khác.
        for (int i = 0; i < rawHeaderValue.length(); i++) {
            char ch = rawHeaderValue.charAt(i);
            if (ch < 0x20 || ch > 0x7E) {
                throw new IllegalArgumentException(
                        "Invalid Authorization");
            }
        }

        Matcher match = HEADER.matcher(rawHeaderValue);
        if (!match.matches()) {
            // Bác bỏ comma, thêm spaces, auth-params dư, token lạ.
            throw new IllegalArgumentException(
                    "Invalid Authorization");
        }

        final long timestamp;
        try {
            timestamp = Long.parseLong(match.group(2));
        } catch (NumberFormatException malformed) {
            throw new IllegalArgumentException(
                    "Invalid Authorization", malformed);
        }

        String signatureText = match.group(4);
        final byte[] tag;
        try {
            tag = Base64.getUrlDecoder().decode(signatureText);
        } catch (IllegalArgumentException badBase64) {
            throw new IllegalArgumentException(
                    "Invalid Authorization", badBase64);
        }

        // Chặn signature không canonical dù decoder tương đối rộng.
        String canonicalEncoded =
                Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(tag);

        if (tag.length != TAG_BYTES
                || !canonicalEncoded.equals(signatureText)) {
            throw new IllegalArgumentException(
                    "Invalid Authorization");
        }

        return new Credential(
                match.group(1), timestamp, match.group(3), tag);
    }
}
~~~

Mã sử dụng một pattern full-match, nên không nhận “chuỗi hợp lệ + suffix bất kỳ”. `String.equals` ở bước **re-encode Base64URL** chỉ so **representation do caller biết**, không được dùng làm phép so bí mật giữa expected HMAC và presented tag; phần HMAC comparison sẽ dùng `MessageDigest.isEqual`.

### 10.2. Một adapter Servlet minh họa

~~~java
import jakarta.servlet.http.HttpServletRequest;

// Nếu dự án dùng Servlet API cũ, package có thể là javax.servlet.*.
public final class HmacAuthorizationServletAdapter {
    private HmacAuthorizationServletAdapter() {}

    public static AuthorizationHmacV1.Credential read(
            HttpServletRequest request) {

        String headerValue = AuthorizationHmacV1.requireSingle(
                request.getHeaders("Authorization"));

        return AuthorizationHmacV1.parse(headerValue);
    }
}
~~~

**Quan trọng:** `getHeaders("Authorization")` chỉ phản ánh những gì Servlet container **đã nhận và giữ lại**. Nếu reverse proxy trước đó đã gộp hai Authorization fields, adapter không thể quay lại raw HTTP packet để biết chính xác occurrences ban đầu. Do vậy:

- Edge HTTP parser/gateway phải kiểm tra header multiplicity trước khi merge.
- Nếu một component không bảo toàn dữ liệu cần phát hiện duplicate, phải chặn ambiguity tại component trước đó.
- Tránh dùng middleware có hành vi “take first authorization token” hoặc “last header wins” không được contract cho phép.
- Bộ kiểm thử phải đi **end-to-end qua gateway và backend**, không chỉ unit test parser Java.

### 10.3. Kết quả parser chưa phải authentication

Sau `parse`, server mới có:

~~~text
keyId claimed by caller
timestamp claimed by caller
nonce claimed by caller
presented 32-byte tag
~~~

Tất cả vẫn là **untrusted claims** cho đến khi được ràng buộc bằng expected HMAC từ trusted credential record và canonical request do server tạo.

Không ghi nonce vào Redis chỉ vì parser nhận được một chuỗi đúng grammar.

## 11. Java 17: canonical request không tin Authorization tự khai

Hợp đồng HMAC-REQUEST-V1 minh họa cho `POST` JSON API:

| Thành phần | Quy tắc |
| --- | --- |
| Method | `POST` đúng case |
| Path | ASCII unreserved segments, không encoded slash/dot hoặc trailing slash trong V1 |
| Query | Unique-key map; `&`/`=`; ASCII unreserved; sort theo key |
| Body | SHA-256 của raw body bytes thực nhận |
| Content-Type | `application/json` chính xác theo policy minh họa |
| Credential metadata | Key ID, timestamp, nonce lấy từ parsed Authorization |
| Audience | `orders-api` xác định từ server route/key policy |
| Encoding | UTF-8; LF giữa các dòng; không LF cuối |
| Tag | Full HMAC-SHA256 32 byte, signature text Base64URL unpadded |

Đây là **giới hạn V1 để học**, không phải một RFC cho mọi URI hoặc MIME types. Production contract có thể cho phép percent-encoding, Unicode, duplicate query keys hoặc charset khác nhưng phải định nghĩa duy nhất semantics và đồng bộ signer/verifier/router.

### 11.1. Canonicalizer Java 17

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;
import java.util.TreeMap;
import java.util.StringJoiner;
import java.util.regex.Pattern;

public final class HmacCanonicalV1 {
    public record Request(
            String method, String rawPath, String rawQuery,
            String contentType, byte[] rawBody) {}

    private static final Pattern PATH =
            Pattern.compile("/|/[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*");
    private static final Pattern QUERY_NAME =
            Pattern.compile("[A-Za-z0-9._~-]+");
    private static final Pattern QUERY_VALUE =
            Pattern.compile("[A-Za-z0-9._~-]*");

    private HmacCanonicalV1() {}

    private static String canonicalPath(String path) {
        if (path == null || path.length() > 2048
                || !PATH.matcher(path).matches()) {
            throw new IllegalArgumentException("Invalid path");
        }

        // Reject dot segments; không normalize rồi âm thầm ký path khác.
        if (!path.equals("/")) {
            for (String seg : path.substring(1).split("/", -1)) {
                if (seg.equals(".") || seg.equals("..")) {
                    throw new IllegalArgumentException("Dot segment");
                }
            }
        }
        return path;
    }

    private static String canonicalQuery(String query) {
        if (query == null) return ""; // Query vắng mặt.
        if (query.isEmpty() || query.length() > 4096) {
            // Present-but-empty query bị V1 từ chối.
            throw new IllegalArgumentException("Invalid query");
        }

        String[] pairs = query.split("&", -1);
        if (pairs.length > 50) {
            throw new IllegalArgumentException("Too many pairs");
        }

        Map<String, String> sorted = new TreeMap<>();
        for (String pair : pairs) {
            int separator = pair.indexOf('=');
            if (separator <= 0
                    || separator != pair.lastIndexOf('=')) {
                throw new IllegalArgumentException("Invalid pair");
            }

            String name = pair.substring(0, separator);
            String value = pair.substring(separator + 1);

            if (!QUERY_NAME.matcher(name).matches()
                    || !QUERY_VALUE.matcher(value).matches()
                    || sorted.putIfAbsent(name, value) != null) {
                throw new IllegalArgumentException(
                        "Invalid or duplicate query parameter");
            }
        }

        StringJoiner joined = new StringJoiner("&");
        for (var e : sorted.entrySet()) {
            joined.add(e.getKey() + "=" + e.getValue());
        }
        return joined.toString();
    }

    public static byte[] canonicalBytes(
            Request request,
            AuthorizationHmacV1.Credential credential)
            throws java.security.NoSuchAlgorithmException {

        if (request == null || credential == null
                || !"POST".equals(request.method())
                || !"application/json".equals(request.contentType())
                || request.rawBody() == null
                || request.rawBody().length > 1024 * 1024) {
            throw new IllegalArgumentException("Invalid signed request");
        }

        String canonicalPath = canonicalPath(request.rawPath());
        String canonicalQuery = canonicalQuery(request.rawQuery());
        String digest = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                        .digest(request.rawBody()));

        String canonicalText = String.join("\n",
                "HMAC-REQUEST-V1",
                request.method(),
                canonicalPath,
                canonicalQuery,
                "audience:orders-api",
                "content-type:" + request.contentType(),
                "key-id:" + credential.keyId(),
                "timestamp:" + credential.timestampSeconds(),
                "nonce:" + credential.nonceHex(),
                "body-sha256:" + digest);

        return canonicalText.getBytes(StandardCharsets.UTF_8);
    }
}
~~~

### 11.2. Các điều kiện để canonicalizer đúng ở HTTP boundary

- `rawPath` là request-target path trước khi middleware/router decode hoặc rewrite theo cách trái contract.
- `rawQuery` phải giữ đủ dấu phân cách và duplicate parameters để phát hiện ambiguity, không phải map đã silently first-wins/last-wins.
- `rawBody` là đúng bytes theo body-signing contract, không phải JSON object được serialize lại với whitespace khác.
- `contentType` lấy từ **đúng một Content-Type field đã validate**; không chọn tùy ý trong duplicates.
- `credential` được parse từ đúng một Authorization field, chưa là identity cho đến khi MAC hợp lệ.
- Route thực tế handler sẽ xử lý phải tương ứng với canonical path/query đã được ký.
- Nếu ingress hỗ trợ Unicode/percent-encoding/path matrix parameters, cần **contract mới rõ ràng**, không tự normalize để “hợp lệ”.

### 11.3. Vì sao không ký nguyên Authorization?

Nếu đưa cả `Authorization: HMAC-V1 ...<signature>` vào message cần tạo signature đó, phép tính tự phụ thuộc vào tag đầu ra. Thay vào đó, protocol ký **metadata có ý nghĩa** (key ID, timestamp, nonce, version marker) và các signed HTTP components; tag được kiểm tra riêng.

Nếu contract ký signed-header names do client chỉ định, cần validate đúng **allowlist/multiplicity/canonicalization**; không cho caller bỏ một header có ảnh hưởng bảo mật khỏi signed set.

## 12. Java 17: expected HMAC, timing-safe comparison và identity

Một verifier phải lấy secret từ key registry đáng tin:

~~~text
Authorization claims keyId=partner-a-k3
  -> lookup exact registry record
  -> validate status, audience, allowed algorithm, validity window
  -> resolve trusted secret bytes
  -> HMAC(secret, canonicalRequestBytes)
  -> compare tag bytes
~~~

Không lấy `X-Secret`, `X-Signature-Algorithm` hay `X-Canonical-Request` do caller gửi làm nguồn quyết định secret/algorithm/canonical bytes.

### 12.1. HMAC primitive và so tag

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacTagVerifierV1 {
    private HmacTagVerifierV1() {}

    public static boolean matches(
            byte[] trustedSecret,
            byte[] canonicalRequestBytes,
            byte[] presentedTag) throws GeneralSecurityException {

        if (trustedSecret == null || trustedSecret.length == 0
                || canonicalRequestBytes == null
                || presentedTag == null || presentedTag.length != 32) {
            return false;
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(trustedSecret, "HmacSHA256"));

        byte[] expectedTag = mac.doFinal(canonicalRequestBytes);
        return MessageDigest.isEqual(expectedTag, presentedTag);
    }
}
~~~

Trong Java, `Mac` là stateful; ví dụ tạo instance mới cho từng phép tính. Dùng `MessageDigest.isEqual` để tránh tự viết comparator thoát sớm theo byte sai. Tuy nhiên đó chỉ bảo vệ **phép so byte**, không làm toàn bộ key lookup, HTTP parser hoặc response timing trở nên hằng số.

### 12.2. Authentication result tách biệt parser result

Một pipeline an toàn có thể mô tả:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Strict HTTP framing, limits, duplicate checks]
    B --> C[Exactly one Authorization field]
    C --> D[Strict HMAC-V1 credential parse]
    D --> E[Lookup key record + status + audience]
    E --> F[Recreate canonical HTTP bytes]
    F --> G[Calculate expected HMAC and compare full tag]
    G --> H{MAC valid?}
    H -- No --> X[Reject authentication]
    H -- Yes --> I{Timestamp fresh?}
    I -- No --> X
    I -- Yes --> J[Atomic nonce claim]
    J --> K{Nonce new?}
    K -- No or unknown --> X
    K -- Yes --> L[Set trusted principal from key record]
    L --> M{Authorized action/resource?}
    M -- No --> Y[Reject authorization]
    M -- Yes --> N[Business handler with idempotency]
~~~

### 12.3. Principal không được lấy từ client-supplied X headers

Một anti-pattern:

~~~java
// SAI: caller có thể khai header này trước khi xác thực.
String principal = request.getHeader("X-Authenticated-User");
securityContext.setPrincipal(principal);
~~~

Thay vào đó, sau khi MAC hợp lệ, lấy `principalId` từ credential record tương ứng với exact key ID và dùng làm authenticated identity. Một `X-Authenticated-User` do gateway tạo chỉ đáng tin nếu gateway đã xác thực, strip bản client và đường truyền nội bộ được bảo vệ.

### 12.4. Generic errors không thay strict validation

Bên ngoài có thể trả mã lỗi authentication chung cho nhiều nguyên nhân, không tiết lộ key tồn tại/revoked hoặc expected tag. Nhưng bên trong phải ghi nhận **mã nguyên nhân đã redacted** để phân biệt duplicate Authorization, malformed credential, MAC mismatch, replay, authorization denial và store outage.

Không để log raw `Authorization` chứa signature/nonce/metadata còn hạn có thể được dùng để replay request.

## 13. Header injection và chống replay

Ví dụ caller sửa nonce trong Authorization:

~~~text
Original: HMAC-V1 k3.T.N1.sig1
Tampered: HMAC-V1 k3.T.N2.sig1
~~~

Nếu nonce là signed component, `sig1` không hợp lệ cho `N2`. Server phải từ chối ở HMAC trước khi ghi `N2` vào replay store.

### 13.1. Timestamp và nonce phải cùng được ký

Replay defense cần:

- Timestamp Unix seconds ở định dạng canonical, kiểm tra window.
- Nonce được tạo ngẫu nhiên và uniqueness theo credential namespace.
- Nonce nằm trong canonical bytes, không phải một unsigned header.
- Replay store shared across instances, atomic insert-if-absent.
- TTL nonce đủ dài để bao phủ freshness window, future skew và clock margin.
- Khi replay store không chắc chắn/outage, policy fail-closed cho API nhạy cảm.

### 13.2. TTL và future skew

Gọi `A` là max past age, `F` là max future skew và `M` là safety margin. Một chính sách conservative:

\[
\text{nonceTtl} \ge A + F + M
\]

Ví dụ `A=300` giây, `F=30` giây, `M=30` giây → TTL 360 giây. Nếu chỉ giữ nonce 300 giây từ lần nhận đầu trong khi timestamp được ký 30 giây tương lai, replay entry có thể hết trước khi request trở nên stale.

Đừng cho client tùy chọn TTL qua một header như `X-Nonce-TTL` rồi tự rút ngắn retention dưới policy server.

### 13.3. Một nonce không phải một business operation

Client có thể gửi hai signed requests với nonce khác nhau nhưng cùng paymentId. Cả hai có MAC đúng và nonce mới. Replay gate không thay **business idempotency**, nên cần operation ID/idempotency key đã ký và transactional store để tránh tác động trùng.

### 13.4. Không ghi nonce trước MAC

Nếu parser nhận credential đúng grammar rồi ghi nonce trước khi HMAC, attacker có thể copy key ID/nonce nhìn thấy trong request thật, gửi một request MAC sai để chiếm replay entry. Đây là **nonce poisoning**. Admission phải ở **sau** bước MAC và freshness phù hợp.

## 14. Key rotation và header ambiguity

Khi client chuyển key:

~~~text
partner-a-k2 -> RETIRING, secret v2
partner-a-k3 -> ACTIVE, secret v3
~~~

Server chỉ lấy **một** record đúng theo key ID từ parsed Authorization. Không thử secret cũ/mới đến khi tag khớp, không suy thuật toán từ format signature do caller gửi, không cho một Authorization header có nhiều credentials k2/k3.

Một request:

~~~http
Authorization: HMAC-V1 partner-a-k2....
Authorization: HMAC-V1 partner-a-k3....
~~~

phải **bị từ chối do duplicate**, kể cả khi một key đang ACTIVE và key còn lại RETIRING. Client phải gửi **một request với một credential rõ ràng**.

### 14.1. Revocation phải áp dụng trên mọi nodes

Gateway hoặc backend có cache trạng thái key khác nhau có thể chấp nhận credential đã revoked. Điều này không chỉ là header injection, nhưng parser ambiguity và key cache inconsistency có thể tương tác khiến identity khó xác định. Cần policy invalidation/rotation có version, audit và kiểm tra audience.

### 14.2. Algorithm confusion

Không cho caller tự thêm:

~~~http
X-HMAC-Algorithm: none
X-Signature-Encoding: ignore-padding
~~~

rồi verifier thay `HmacSHA256` hoặc bỏ strict format. Algorithm do server contract/key record quyết định. Nếu triển khai HMAC-SHA384/512, tạo version/policy và test vectors riêng.

## 15. Vì sao Authorization header không đồng nghĩa Authorization policy?

Tên header `Authorization` dễ làm nhầm rằng xác minh nó tức là đã **phân quyền**. Thực tế:

**Authentication:** HMAC chứng minh request được ký bằng secret tương ứng credential record và không bị sửa theo signed fields. Kết hợp timestamp/nonce và key status để xác định request đáng tin ở mức xác thực.

**Authorization:** Dựa trên authenticated principal từ registry, action, resource, tenant, scope và policy server-side để quyết định request đó có được phép hay không.

Ví dụ:

~~~http
DELETE /v1/tenants/tenant-B/orders/42 HTTP/1.1
Authorization: HMAC-V1 tenant-a-k3.1800000030.6bfb21974a08417199273b09ca49a3ec.<valid-A-tag>
~~~

Một client tenant A biết secret có thể ký một request tới tenant B. **MAC hoàn toàn có thể hợp lệ**, nhưng hệ thống phải từ chối vì principal A không có quyền trên B.

### 15.1. Injection vào role/tenant headers

Những dữ liệu như:

~~~http
X-Tenant-Id: tenant-B
X-Role: admin
X-Authenticated-User: system
~~~

không được coi là security authority chỉ vì chúng có tên “role/tenant/authenticated”. Nếu được truyền qua gateway, phải xác định trường nào là **client-supplied data** và trường nào là **trusted gateway assertion**. Gateway phải xóa client-supplied identity headers rồi gắn lại sau khi xác thực, và backend bảo vệ đường truyền đó.

### 15.2. Signed header cũng không trở thành quyền

Ngay cả khi `X-Role: admin` được HMAC ký, chữ ký chỉ chứng minh **caller đã yêu cầu giá trị đó**, không chứng minh policy đã cấp role. Quyền luôn lấy từ server-side registry/policy hoặc một delegated token có cơ chế xác thực và issuer/claims validation riêng.

## 16. Logging, monitoring và phản hồi lỗi

### 16.1. Không ghi raw Authorization vào logs

Một header Authorization có key ID, timestamp, nonce và HMAC tag. Dù HMAC tag không phải secret theo nghĩa mật mã, cả **signed request còn hiệu lực** có thể bị replay nếu rơi vào tay attacker và anti-replay chưa được claim, hoặc một hệ thống không triển khai nonce đúng. Tránh ghi trọn header và sensitive body vào access log/tracing/exporter.

Nên:

- Redact `Authorization` và các credential-bearing headers trước khi log.
- Ghi event codes, request correlation ID, service, outcome và key ID đã được bảo vệ/phân loại theo policy.
- Không log raw request line/payload chứa ký tự điều khiển mà không escaping.
- Không trả expected HMAC, secret ref, prefix-match count hay key registry details ra response.
- Tách reason codes nội bộ khỏi thông điệp authentication chung bên ngoài.

### 16.2. Một bảng lỗi thường gặp

| Lỗi | Xử lý |
| --- | --- |
| Thiếu Authorization | Authentication reject |
| Hai Authorization fields | Reject ambiguous request |
| Scheme ngoài HMAC-V1 | Reject theo endpoint policy |
| CR/LF/CTL trong header | HTTP parser/adapter reject |
| Header quá dài | Reject size limit |
| Base64URL sai format | Reject |
| Key không tồn tại/revoked | Reject không tiết lộ chi tiết credential |
| HMAC mismatch | Reject |
| Timestamp hết hạn | Reject freshness |
| Nonce đã claim | Reject replay |
| Replay store không khả dụng | Fail closed theo policy |
| Principal thiếu quyền | Authorization reject |
| Gateway identity header tự khai | Strip/reject, không cấp principal |

Một số lỗi framing có thể được xử lý trực tiếp ở edge trước khi đến Java controller. **Đừng giả định mọi lỗi đều đi qua cùng một exception handler**; cần e2e tests và monitoring xuyên các tầng.

## 17. Ma trận kiểm thử Header injection

Kiểm thử cần tách **parser behavior**, **signature validation** và **end-to-end proxy semantics**. Một parser unit test chạy với một Java String đơn lẻ không tự phát hiện việc HTTP gateway đã merge hai raw header occurrences thành một value.

### 17.1. Authorization multiplicity và grammar

| Test | Input | Kết quả mong đợi |
| --- | --- | --- |
| Một header hợp lệ | `Authorization: HMAC-V1 ...` | Parse thành credential, chưa authenticated |
| Không có header | Missing Authorization | Reject |
| Hai Authorization giống nhau | Hai raw header occurrences cùng value | Reject duplicate |
| Hai Authorization khác nhau | HMAC và Bearer cùng tồn tại | Reject duplicate |
| Tên khác case | `Authorization` + `authorization` | Reject duplicate |
| Một header có comma | `HMAC-V1 ... , Bearer ...` | Reject grammar |
| Multiple spaces | Hai spaces sau scheme | Reject V1 |
| Tab sau scheme | HTAB thay space | Reject V1 |
| Leading whitespace | ` Authorization: ...` tại raw boundary | Reject invalid HTTP |
| Trailing space | Credential có whitespace cuối | Reject V1 |
| Newline injection | Credential chứa CR+LF | Reject at HTTP edge/parser |
| Bare CR | Credential chứa CR đơn lẻ | Reject |
| Bare LF | Credential chứa LF đơn lẻ | Reject |
| NUL / DEL | `0x00` hoặc `0x7F` trong header | Reject |
| Unicode metadata | Non-ASCII key ID/nonce trong V1 | Reject |
| auth-param dư | Suffix `,role=admin` | Reject |
| Wrong scheme | `Basic`/`Bearer` | Reject endpoint HMAC policy |
| Scheme khác case | `hmac-v1` | Cùng scheme theo contract |
| Unknown version | `HMAC-V2` | Reject trừ khi endpoint đã support |
| Length vượt cap | Header lớn hơn 256 chars | Reject trước decode |
| Key ID rỗng | `HMAC-V1 .ts.nonce.tag` | Reject |
| Key ID chứa dấu chấm | Phát sinh segment dư | Reject |
| Timestamp có leading zero | `000123` | Reject |
| Timestamp có dấu + | `+123` | Reject |
| Timestamp milliseconds | 13-digit value khi thời gian thật tính seconds | Reject theo freshness window |
| Timestamp vượt long | Chuỗi số quá `long` | Reject |
| Nonce sai format | Uppercase hoặc 31 ký tự | Reject |
| Signature base64 chuẩn | Có `+` hoặc `/` | Reject URL-safe grammar |
| Signature padding | Có `=` cuối | Reject V1 no-padding |
| Signature sai độ dài | 42 hoặc 44 ký tự | Reject |
| Signature noncanonical | Decoder có thể nhận nhưng re-encode khác | Reject |
| Valid syntax, wrong HMAC | 43 char nhưng tag sai | Authentication reject |

### 17.2. Canonicalization và signed fields

| Test | Thay đổi | Kỳ vọng |
| --- | --- | --- |
| Same canonical bytes + secret | Cùng request, cùng credential | Expected tag giống |
| Modify method | `POST` → `DELETE` | Tag sai hoặc contract reject |
| Modify path | `/orders/42` → `/orders/43` | HMAC sai |
| Trailing slash | Thêm `/` ngoài root | V1 reject |
| Encoded slash | `%2F` trong path | V1 reject, không decode tùy ý |
| Dot segment | `/a/../b` | V1 reject |
| Query reorder | `b=2&a=1` ↔ `a=1&b=2` | Canonical query V1 giống |
| Query duplicate | `tenant=A&tenant=B` | Reject |
| Encoded separator | `%26`, `%3D` trong V1 | Reject nếu ngoài contract |
| Query absent vs empty | No query vs explicit `?` | Theo V1, explicit empty reject |
| Content-Type altered | `application/json` → `text/plain` | Reject |
| Duplicate Content-Type | Hai values không nhất quán | Reject ở edge/adapter |
| Body byte altered | JSON whitespace/order/value đổi | Digest/HMAC khác |
| Signed key ID altered | k3 → k4 giữ tag | Reject key/MAC |
| Signed nonce altered | N1 → N2 giữ tag | MAC sai |
| Signed timestamp altered | T1 → T2 giữ tag | MAC sai |
| Unsigned header altered | `User-Agent` thay giá trị | MAC có thể giữ nguyên; không dùng nó làm quyền |
| Spoof role | Caller thêm `X-Role: admin` | Không thay trusted principal/authorization |
| Spoof gateway user | Caller thêm `X-Authenticated-User` | Strip/reject, không cấp danh tính |

### 17.3. HTTP/2, gateway và parser differential

| Test | Tình huống | Mục tiêu |
| --- | --- | --- |
| HTTP/2 lowercase field name | `authorization` | Đồng nghĩa với Authorization |
| HTTP/2 duplicate field instances | Nhiều occurrences sau chuyển đổi | Không âm thầm chọn một |
| HTTP/2 → HTTP/1.1 downgrade | Chuẩn hóa header/framing | Không sinh thêm header hoặc đổi signed semantics |
| Gateway merges Authorization | Hai fields thành chuỗi có comma | Verifier reject, không split-and-try |
| Gateway drops first/last field | Hai Authorization trước gateway | Edge reject trước khi mất evidence |
| Gateway rewrites path | `/public/v1/orders` → `/v1/orders` | Signing boundary thống nhất |
| Gateway normalizes query | Duplicate/reorder/percent decode | Signer/verifier/router dùng contract thống nhất |
| Gateway changes body bytes | Re-serialize JSON | HMAC mismatch hoặc verify trước rewrite |
| Request framing ambiguity | Content-Length/Transfer-Encoding conflict | HTTP edge reject |
| Connection reuse after malformed framing | Parser trạng thái mơ hồ | Không reuse request boundary sai |
| Forged forwarded headers | Caller gửi `X-Forwarded-Host` | Không tin nếu proxy không strip/rewrite |
| Forged identity headers | Caller gửi `X-Authenticated-Client` | Backend không tin |
| Direct backend access | Bypass gateway | Chặn tại network/service auth boundary |
| Gateway credential strip | Gateway remove Authorization sau verify | Internal authenticated context được bảo vệ |
| Double verifier | Gateway + backend cùng claim nonce | Xác định owner, không double claim sai |

### 17.4. Replay, rotation và authorization

| Test | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| MAC sai với nonce chưa thấy | Request giả | Reject trước replay claim |
| MAC đúng + nonce mới | Credential ACTIVE, timestamp fresh | Claim atomically, tiếp tục policy |
| MAC đúng + nonce trùng | Cùng request replay | Reject replay |
| Future skew biên | Timestamp tại `now+F` | Fresh nếu contract inclusive |
| Timestamp quá cũ | Nhỏ hơn `now-A` | Reject |
| Replay store timeout | Không biết claim thành công chưa | Fail closed theo policy |
| Key ID không tồn tại | Caller tự khai kX | Reject không tiết lộ secrets |
| Key revoked | HMAC đúng dưới key cũ | Reject |
| Key rotation overlap | k2/k3 vẫn có hiệu lực | Mỗi request chọn exact record |
| Header chứa hai key IDs | Hai credentials cùng request | Reject ambiguous |
| Wrong audience | Credential orders gọi payments | Reject |
| Valid MAC, unauthorized tenant | Principal A thao tác tenant B | Authorization reject |
| New nonce, same payment ID | Business retry | Idempotency tránh double effect |

## 18. Tình huống thực tế: gateway và backend chọn hai credentials

Giả sử một API chấp nhận `Authorization` và gateway dùng HMAC verifier trước khi forward đến backend. Một request bất thường chứa:

~~~http
POST /v1/orders/42 HTTP/1.1
Authorization: HMAC-V1 partner-a-k3.1800000030.6bfb21974a08417199273b09ca49a3ec.<valid-A-tag>
authorization: Bearer <another-credential>
~~~

Trong một triển khai lỗi:

1. Gateway HTTP library lấy **giá trị đầu** → xác minh HMAC của A.
2. Gateway chuyển nguyên các field tới backend hoặc gộp theo behavior riêng.
3. Backend security filter lấy **giá trị cuối** → coi request mang Bearer identity B.
4. Router/handler có thể xử lý theo principal B dù gateway đã kiểm tra request ký bởi A.

Đây là **identity confusion**, không phải attacker tự sinh được HMAC của A nếu không có secret. Lỗ hổng xuất hiện do hai tầng **chọn credential khác nhau**.

### 18.1. Khắc phục

- Từ chối **mọi request có hai Authorization fields** ngay tại ingress, bất kể giá trị nào đúng.
- Không merge Authorization thành comma-separated list.
- Chỉ hỗ trợ HMAC-V1 trên endpoint tương ứng; không tự fallback sang Bearer/Basic.
- Cùng policy ở gateway, backend và các HTTP versions.
- Gateway chuyển principal qua **protected internal context**, strip raw client identity claims.
- Backend chặn bypass gateway và không tự suy identity từ proxy headers không tin cậy.
- Có e2e tests phát request malformed trực tiếp vào **edge thực tế**, không chỉ tạo `HttpServletRequest` mock.

### 18.2. Vì sao unit test Java parser vẫn cần nhưng chưa đủ?

`AuthorizationHmacV1.parse` có thể từ chối mọi `CR/LF` và comma trong String; tuy nhiên khi gateway đã drop một Authorization occurrence, Java parser chỉ còn nhận một String sạch và **không có bằng chứng request gốc từng nhập nhằng**.

Vì thế cần **hai lớp kiểm thử**: unit tests cho strict parser và integration tests cho raw HTTP ingress/gateway/proxy/backend boundary. Nếu một tầng không thể nhìn được duplicate state ban đầu, phải chặn nó ở tầng trước.

## 19. Tình huống thứ hai: spoof X-Authenticated-User

Một gateway thiết kế để xác minh HMAC rồi forward:

~~~http
X-Authenticated-User: partner-a-service
X-Authenticated-Tenant: tenant-A
~~~

Nếu gateway **không xóa** các header cùng tên do client gửi trước khi thêm thông tin, backend có thể nhận:

~~~http
X-Authenticated-User: administrator
X-Authenticated-User: partner-a-service
~~~

Một backend dùng first-wins sẽ thấy `administrator`, dù gateway nghĩ mình đã gắn identity an toàn. Đây là header spoofing qua **trust boundary**.

Cách sửa đúng:

1. Strip tất cả client-supplied identity/authorization-context headers tại edge, so field name case-insensitive.
2. Sau khi HMAC, freshness, nonce admission và key policy hợp lệ, gateway tạo principal/tenant từ trusted registry.
3. Truyền internal context qua một kênh có xác thực service-to-service (ví dụ mTLS) hoặc cơ chế integrity-protected assertion.
4. Backend chỉ tin context từ gateway đã xác minh, ngăn direct untrusted access.
5. Authorization vẫn đối chiếu principal/action/resource ở backend.
6. Test both duplicate identity headers và `X-Forwarded-*` spoof.

**Không** đủ nếu chỉ “ký `X-Authenticated-User`” như dữ liệu do client khai: caller sở hữu secret có thể tự yêu cầu role không được cấp. Role phải đến từ policy server hoặc một nguồn được ủy quyền có issuer validation.

## 20. Sai lầm triển khai thường gặp

### 20.1. “String.trim() rồi parse là đủ”

Trim có thể **che đi** whitespace injection hoặc khiến gateway/verifier chấp nhận hai wire representations nhưng router hiểu khác. Hợp đồng nên xác định format canonical và reject ngoài grammar thay vì cố sửa.

### 20.2. “getHeader() trả một chuỗi nên không có duplicate”

`getHeader` thường chỉ expose một value. Gateway/container có thể đã drop/merge occurrences. Kiểm tra raw multiplicity ở edge và dùng `getHeaders` ở nơi có thể.

### 20.3. “Tên Authorization viết hoa mới là hợp lệ”

HTTP field name case-insensitive; `authorization` và `Authorization` là một field name. Nếu dùng logic case-sensitive, attacker có thể tạo duplicate không được phát hiện.

### 20.4. “Authorization có thể gộp bằng comma như mọi header khác”

Không được áp dụng mù quáng list coalescing cho credentials. Protocol HMAC V1 reject comma và duplicate fields.

### 20.5. “CRLF đã bị proxy loại, backend không cần kiểm”

Các tầng có thể thay đổi, route khác hoặc có đường bypass. Edge bắt buộc strict; backend vẫn validate grammar và không tin dữ liệu được forward ngoài contract. Không dựa vào một filter có thể bị bỏ qua.

### 20.6. “Thử từng scheme đến khi một cái thành công”

Tạo scheme/identity confusion và khó kiểm toán. Endpoint policy phải chỉ rõ scheme nào được phép, không fallback không kiểm soát.

### 20.7. “Ký toàn bộ Authorization bao gồm signature”

Tag là đầu ra của phép tính; đưa nguyên tag vào input tạo phụ thuộc vòng. Ký protocol marker và metadata có ý nghĩa rồi so tag riêng.

### 20.8. “Body hash từ header client là đủ”

Nếu server không hash **body bytes thực nhận**, attacker có thể khai digest cũ nhưng gửi body mới. Phải tính lại digest và bảo đảm handler xử lý cùng dữ liệu đã xác minh.

### 20.9. “Proxy X-Original-URI đáng tin vì được đặt tên Original”

Nếu client gửi header đó và proxy không strip/rewrite, nó chỉ là input không đáng tin. Metadata proxy chỉ được tin qua trust boundary được bảo vệ.

### 20.10. “HMAC đúng thì X-Role: admin có hiệu lực”

HMAC chứng minh caller đã gửi value, không chứng minh policy cho phép role. Authorization là một quyết định server-side riêng.

### 20.11. “Nonce được lưu ngay khi parse Authorization”

Request MAC sai vẫn có thể claim/poison nonce. Chỉ ghi replay entry sau MAC và freshness hợp lệ.

### 20.12. “Log Authorization để dễ debug”

Một logged Authorization chứa metadata và HMAC tag có thể là thành phần của signed request còn hạn; có rủi ro rò thông tin/được dùng khi replay. Redact và ghi reason codes thay thế.

## 21. Bài tập thực hành

### Bài tập 1 — Strict grammar

Từ hợp đồng `Authorization: HMAC-V1 kid.ts.nonce.sig`, viết JUnit tests cho `AuthorizationHmacV1.parse` với token hợp lệ, hai spaces sau scheme, tab, CRLF, dấu phẩy, key ID chứa dot, timestamp leading zeros, nonce uppercase và signature sai độ dài.

### Bài tập 2 — Duplicate Authorization

Thiết kế integration test gửi hai Authorization occurrences khác case đến ingress. Kiểm tra request bị reject **trước khi** proxy gộp hoặc drop chúng. So sánh với unit test `getHeaders` và chỉ rõ giới hạn khi proxy đã normalize.

### Bài tập 3 — Gateway identity spoofing

Mô phỏng caller tự gửi `X-Authenticated-User` rồi gateway xác minh HMAC và gắn principal thật. Viết test bảo đảm backend **chỉ** sử dụng trusted identity context, không lấy first/last client field.

### Bài tập 4 — Canonical request

Dùng `HmacCanonicalV1` tạo canonical bytes cho method/path/query/Content-Type/body. Thay một byte raw body và chứng minh SHA-256 body digest/HMAC tag thay đổi. Kiểm tra duplicate query names và encoded path bị reject theo V1.

### Bài tập 5 — Key rotation

Có k2 và k3, mỗi ID gắn secret riêng. Gửi Authorization có tag tính bằng k2 nhưng key ID k3; phải reject. Gửi hai Authorization values (k2/k3) cùng request; phải reject duplicate chứ không thử cả hai.

### Bài tập 6 — Replay poisoning

Tạo request MAC sai với key ID và nonce hợp format, sau đó kiểm tra replay store **không có entry mới**. Gửi request MAC đúng với nonce ấy; nó chỉ được claim một lần bằng atomic insert.

### Bài tập 7 — HTTP versions

Gửi các test case qua HTTP/1.1 và HTTP/2, gồm tên `authorization` lowercase và duplicate occurrences. Theo dõi gateway/nginx/server adapter nhận được gì. Không kết luận chỉ từ mock request; test đúng deployed path.

### Bài tập 8 — Authorization khác authentication

Client A ký một request hợp lệ đến resource tenant B. HMAC và nonce gate phải xử lý đúng; authorization phải từ chối action trên tenant B. Không dùng role/tenant do client tự khai để cấp quyền.

### Bài tập 9 — Operational review

Xem cấu hình WAF/gateway/logging cho Authorization. Xác định duplicate-field handling, header size limits, stripping identity headers, request framing checks, backend bypass protection và logs được redacted thế nào. Ghi thành checklist triển khai.

## 22. Checklist phòng vệ Header injection

- [ ] Ingress HTTP parser từ chối CR/LF, NUL/CTL và framing ambiguity trong header fields.
- [ ] Giới hạn tổng kích thước headers và riêng Authorization trước parse/decode.
- [ ] Tên HTTP field được so case-insensitive, kể cả khi HTTP/2 lowercase.
- [ ] Chính xác **một** Authorization occurrence; reject duplicates kể cả values giống nhau.
- [ ] Gateway không merge Authorization như arbitrary comma-separated list.
- [ ] Scheme được chọn theo endpoint policy; không Basic/Bearer fallback vào HMAC endpoint.
- [ ] HMAC scheme/version metadata được parse strict, full-match; không split/trim phục hồi input bất thường.
- [ ] Key ID/timestamp/nonce/tag format, length, ASCII và Base64URL canonical có kiểm tra.
- [ ] HMAC algorithm/encoding được chọn từ server-side contract/key record, không từ header không đáng tin.
- [ ] Verifier tái dựng canonical bytes từ request thực nhận theo signing boundary.
- [ ] Key ID, timestamp, nonce và version marker được ràng buộc vào chữ ký; không ký vòng lặp cả tag.
- [ ] Signed headers có allowlist, xử lý duplicates/whitespace/casing rõ ràng.
- [ ] Raw body digest được server tự tính và handler sử dụng cùng semantics đã xác minh.
- [ ] Gateway/backend/router không bất đồng về path/query/authority/body đã ký.
- [ ] HTTP/2→HTTP/1.1 conversion và Content-Length/Transfer-Encoding ambiguity được kiểm thử.
- [ ] Client-supplied `X-Forwarded-*`/`X-Authenticated-*` bị strip hoặc chỉ dùng theo trusted-proxy policy.
- [ ] Internal authenticated context được bảo vệ (mTLS/assertion hoặc tương đương); backend không bị bypass.
- [ ] HMAC tag full-length được so bằng `MessageDigest.isEqual`, không so prefix.
- [ ] Nonce chỉ được claim sau MAC hợp lệ và freshness; shared atomic store có TTL phù hợp.
- [ ] Key rotation/revocation không thử nhiều secret tùy tiện, áp exact credential policy.
- [ ] Authentication principal đến từ trusted registry; authorization theo action/resource/tenant độc lập.
- [ ] Logs/tracing redacted Authorization và sensitive headers; lỗi bên ngoài không lộ key registry.
- [ ] Có unit tests, raw HTTP ingress tests, gateway integration tests, replay/rotation/authz tests.
- [ ] Mọi parser ambiguity được **reject**, không sửa request bằng nhiều bước normalize để cứu chữ ký.

## 23. Câu hỏi tự kiểm tra

1. **Header injection là gì?** Dữ liệu không đáng tin khiến HTTP headers hoặc semantics bị tạo/diễn giải khác với hợp đồng.
2. **CRLF injection có thể gây điều gì?** Nếu serializer/parser lỗi, CRLF trong value có thể tạo header line mới hoặc thay message boundary.
3. **HTTP field name có phân biệt case không?** Không; `Authorization` và `authorization` cùng tên.
4. **Có được nhận hai Authorization fields trùng giá trị không?** V1 từ chối vì multiplicity nhập nhằng.
5. **Vì sao không nối Authorization values bằng comma?** Credentials không phải list field tùy ý; có thể tạo parser/scheme confusion.
6. **Scheme HMAC-V1 có nên so case-sensitive không?** Authentication scheme token theo HTTP được so case-insensitive; metadata vẫn theo grammar của protocol.
7. **Tại sao getHeader() không đủ để phát hiện duplicates?** Có thể chỉ trả một value; edge/proxy đã merge/drop occurrences.
8. **Nếu parser Java reject CRLF có cần test gateway không?** Có; injection/normalization xảy ra trước khi vào Java có thể đã làm mất evidence.
9. **Key ID do Authorization header khai có đáng tin ngay không?** Không; chỉ dùng tra trusted credential, MAC phải khớp trước khi tạo principal.
10. **Vì sao không đưa nguyên Authorization cùng signature vào canonical request?** Tag là kết quả đầu ra; ký nguyên tag tạo phụ thuộc vòng.
11. **Có cần ký nonce và timestamp không?** Có; nếu không attacker có thể thay metadata mà giữ tag cũ.
12. **Khi nào ghi nonce?** Sau MAC hợp lệ và freshness, bằng atomic replay claim.
13. **Gateway `X-Authenticated-User` có đáng tin nếu client cũng gửi nó?** Không, trừ khi edge strip client field và internal context được bảo vệ.
14. **HMAC đúng có đồng nghĩa caller được quyền sửa tenant khác không?** Không; authorization phải kiểm tra principal và resource.
15. **Có thể sửa HMAC mismatch do proxy bằng cách thử nhiều canonicalizations không?** Không; phải xác định signing boundary và contract thống nhất.
16. **Tại sao phải kiểm thử HTTP/1.1 và HTTP/2?** Chuyển đổi/normalization và parser behavior có thể khác.
17. **Nếu body bị reserialize sau HMAC, có an toàn không?** Chỉ khi transformation được tin cậy và semantics được bảo đảm theo contract; tốt nhất handler dùng đúng dữ liệu đã xác minh.
18. **Vì sao log raw Authorization không an toàn?** Có thể tiết lộ credential metadata và một phần signed request có giá trị cho replay trong window.

## 24. Tài liệu tham khảo và hướng đọc thêm

- **RFC 9110 — HTTP Semantics.** Trường `Authorization`, HTTP authentication scheme, field names, field value parsing và list-field semantics.
- **RFC 9112 — HTTP/1.1.** Message framing, CRLF và yêu cầu xử lý header/folding.
- **RFC 9113 — HTTP/2.** Field name lowercase, pseudo-headers và chuyển đổi semantics.
- **RFC 3986 — Uniform Resource Identifier: Generic Syntax.** Raw path/query và percent-encoding ảnh hưởng canonical request.
- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Nền tảng shared-secret MAC.
- **RFC 4231 — HMAC-SHA-224/256/384/512 Test Vectors.** Known-answer tests cho HMAC primitive.
- **Java SE 17 API — `javax.crypto.Mac`, `MessageDigest.isEqual`, `Base64`, `Pattern`.** Nền tảng crypto và strict signature decoding.
- **Jakarta Servlet API — `HttpServletRequest.getHeaders`.** Ví dụ quan sát các field values được container expose; không thay raw ingress validation.
- **OWASP guidance — HTTP header injection, HTTP request smuggling và trusted proxy boundaries.** Khung kiểm tra ứng dụng đa tầng.

**Kết luận:** **Header injection trong HMAC authentication là lỗi phá ranh giới diễn giải HTTP request**, không chỉ là một chuỗi có CRLF. Một verifier có thể tính HMAC đúng nhưng gateway/router/backend lại chọn credential, signed headers, target hoặc principal khác do duplicate fields, header coalescing, scheme confusion hoặc spoofed proxy identity. Phòng vệ cần **HTTP parser nghiêm ngặt, đúng một Authorization field, protocol grammar cố định, canonical request thống nhất, trusted proxy boundary, HMAC tag verification, timestamp/nonce replay gate, key rotation và authorization độc lập**. Hãy từ chối request nhập nhằng tại điểm sớm nhất, kiểm thử end-to-end qua chính đường proxy/gateway triển khai và không lấy thành công của một parser unit test làm bằng chứng toàn bộ hệ thống an toàn.


