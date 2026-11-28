# Chọn encoding khi thiết kế hệ thống xác thực HTTP request bằng HMAC

## 1. Vì sao encoding là quyết định của giao thức, không chỉ là chi tiết triển khai?

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, một HTTP request được xác thực bằng **HMAC với shared secret** và một **canonical request**. Hợp đồng ký có thể bao gồm phương thức, URI, header và/hoặc digest của body. Verifier còn phải kiểm tra timestamp/nonce chống replay, trạng thái key khi rotation/revocation, các biến đổi qua proxy/gateway và chỉ **phân quyền** sau khi đã xác thực thành công.

Ở chương **Thiết kế HMAC system**, bài **Chọn encoding** tập trung vào câu hỏi nền tảng: **hai hệ thống cần chuyển những dữ liệu gì thành byte, theo quy tắc nào, trước khi tính HMAC và sau khi nhận chữ ký?**

HMAC không ký “nội dung có ý nghĩa tương đương”. HMAC nhận **dãy byte**:

~~~text
MAC = HMAC(secretBytes, messageBytes)
~~~

Nếu Java client gửi UTF-8 nhưng Java server dùng default charset, hoặc client ký chuỗi `%C3%A9` trong query còn gateway decode thành ký tự `é` trước khi verifier ký, hai phía có thể nhận được **MAC khác nhau dù người dùng thấy cùng một URL**.

Ngược lại, lựa chọn encoding/canonicalization nhập nhằng có thể còn nguy hiểm hơn lỗi 401: verifier tưởng đã xác thực request A, nhưng HTTP router hoặc handler lại diễn giải thành request B.

**Sau bài học, người học có thể:**

1. Phân biệt *encoding của secret*, *encoding của canonical message*, *URI percent-encoding*, *body representation* và *encoding chữ ký đầu ra*.
2. Chọn UTF-8, raw URI, SHA-256 body digest và Base64/hex theo **profile ký phiên bản hóa** rõ ràng.
3. Viết Java 17 signer/verifier sử dụng byte chính xác, strict Base64 decoder và so sánh MAC theo byte.
4. Xây golden vector có Unicode, tính đúng body digest, canonical bytes và HMAC, phát hiện lỗi khác biệt Java/Go/JavaScript.
5. Kiểm thử normalization, header duplication, proxy rewrite, replay, key rotation và authorization mà không làm giảm an toàn.

> **Phạm vi:** bài này dùng một profile `HMAC-V1` minh họa. HTTP không có một quy tắc canonical request HMAC duy nhất tự áp dụng cho mọi API. Khi triển khai, chỉ có **hợp đồng được công bố giữa client và server** mới quyết định encoding, signed fields và expected MAC.

## 2. Năm nơi encoding xuất hiện trong một request HMAC

| Vị trí | Input ban đầu | Biểu diễn cần thống nhất | Lỗi phổ biến |
|---|---|---|---|
| **Secret** | Random bytes trong secret manager | Bytes thực, có thể được *lưu* dưới dạng Base64/hex | Dùng UTF-8 của chuỗi Base64 làm khóa thay vì decode |
| **Canonical text** | Method, path/query, metadata ký | Chuỗi có ngữ pháp xác định → **UTF-8 bytes** | Default charset, CRLF/LF, ambiguity delimiter |
| **URI** | Public path và raw query | Percent-encoding/canonical query theo contract | Decode `%2F`, đổi `+`/`%20` hoặc sort sai |
| **Body** | HTTP entity bytes | Hash **đúng byte body** theo tầng contract | Parse JSON rồi serialize lại |
| **Signature** | 32 byte HMAC-SHA256 | Base64 chuẩn, Base64URL hoặc lowercase hex đã chốt | Đổi variant, bỏ/thêm padding, double encoding |

Các quyết định này **độc lập về kỹ thuật nhưng ràng buộc nhau về bảo mật**. Chọn Base64 cho signature không có nghĩa secret cũng phải là Base64 string; chọn UTF-8 cho canonical không có nghĩa phải decode URI trước khi ký; hash body không đồng nghĩa ký một chuỗi body đã được normalize.

### 2.1. Bản thiết kế tham khảo cho profile HMAC-V1

Trong bài, lựa chọn cụ thể:

| Thuộc tính | Quyết định ví dụ |
|---|---|
| Primitive | `HmacSHA256`, MAC 32 bytes |
| Secret | Random bytes 32 bytes, lưu dưới dạng lowercase hex hoặc Base64 nhưng **decode trước khi dùng** |
| Canonical charset | UTF-8, không BOM |
| Line separator | LF byte `0A`, không có LF ở cuối |
| Method | Token uppercase đã được hợp đồng quy định |
| Path | **Public raw path**, từ nguồn đáng tin trước rewrite |
| Query | **Public raw query**, giữ nguyên thứ tự và percent escapes; không gồm `?` |
| Body | SHA-256 của exact entity body bytes mà hai phía ký |
| Body digest trong canonical | Lowercase hex, **64 ký tự ASCII** |
| Timestamp | `2026-11-28T10:00:00Z` — định dạng UTC cố định theo hợp đồng |
| Nonce | Chuỗi ASCII theo grammar/length giới hạn; unique trong replay scope |
| Signature trong HTTP header | **Standard Base64 có padding**, không xuống dòng |
| Signature version | Prefix `HMAC-V1` nằm trong message được ký |

Các lựa chọn này ưu tiên tính **dễ kiểm chứng và interoperability**. Với một API khác, Base64URL không padding hoặc canonical query sort theo chuẩn xác định cũng có thể đúng, miễn là toàn bộ client/server sử dụng cùng một profile được version hóa.

## 3. Chọn encoding từ byte đầu tiên đến wire response

~~~mermaid
flowchart TD
    A[Secret random bytes] --> B[Secret manager: encode hex/Base64 để lưu]
    B --> C[Server/client: decode về key bytes]
    D[Method + trusted public URI + signed metadata] --> E[Canonical grammar]
    F[Raw entity body bytes] --> G[SHA-256]
    G --> H[Lowercase hex body digest]
    H --> E
    E --> I[UTF-8 canonical bytes]
    C --> J[HMAC-SHA256]
    I --> J
    J --> K[MAC 32 bytes]
    K --> L[Base64 standard padded trong X-Signature]
    L --> M[HTTP request]
    M --> N[Server strict decode Base64 về MAC bytes]
    N --> O[So sánh với MAC server tính lại]
    O --> P[Timestamp / atomic nonce + authn]
    P --> Q[Authorization → handler]
~~~

**Ranh giới quan trọng:** encoding là chuyển đổi biểu diễn; encoding **không tạo ra entropy**, không làm secret mạnh hơn, không chống replay và không cấp quyền. Base64 là *binary-to-text encoding*, không phải mã hóa bảo mật (*encryption*).

### 3.1. Hai phép chuyển đổi rất dễ bị viết nhầm

Sai:

~~~java
// config chứa chuỗi "ABEiM0RV...", KHÔNG phải secret bytes.
byte[] wrongKey = base64ConfigValue.getBytes(StandardCharsets.UTF_8);
~~~

Đúng:

~~~java
byte[] actualKey = Base64.getDecoder().decode(base64ConfigValue);
// actualKey là bytes mà bên cấp secret đã phát hành.
~~~

Sai tương tự:

~~~java
// Không gửi dạng UTF-8 của 64 ký tự hex như 32-byte SHA-256 digest.
byte[] wrongDigest = bodyDigestHex.getBytes(StandardCharsets.UTF_8);
~~~

Đúng khi cần bytes:

~~~java
byte[] digestBytes = HexFormat.of().parseHex(bodyDigestHex);
// 64 ký tự hex -> 32 byte.
~~~

Tuy nhiên **canonical V1 của bài** yêu cầu digest ở **dạng hex text**; khi xây canonical string thì phải thêm `bodyDigestHex`, **không** thêm raw digest bytes vào chuỗi LF một cách tùy tiện. Ranh giới định dạng phải được công bố rõ.

## 4. Encoding secret: chọn bytes làm nguồn sự thật

### 4.1. Secret không phải mật khẩu văn bản

Với HMAC-SHA256, nên cấp secret bằng bộ sinh số ngẫu nhiên mật mã, có entropy phù hợp chính sách bảo mật, rồi lưu dưới dạng byte. Có thể dùng ví dụ secret test 32 byte:

~~~text
Secret HEX (32 byte):
00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff

Secret Base64:
ABEiM0RVZneImaq7zN3u/wARIjNEVWZ3iJmqu8zd7v8=
~~~

**Đây là secret giả, công khai, chỉ dành cho test.** Chuỗi HEX và Base64 trên cùng biểu diễn một dãy 32 bytes. Java code phải decode chúng thành bytes trước khi đưa vào `SecretKeySpec`:

~~~java
import java.util.Base64;
import java.util.HexFormat;
import java.util.Arrays;

byte[] fromHex = HexFormat.of().parseHex(
        "00112233445566778899aabbccddeeff"
      + "00112233445566778899aabbccddeeff");
byte[] fromBase64 = Base64.getDecoder().decode(
        "ABEiM0RVZneImaq7zN3u/wARIjNEVWZ3iJmqu8zd7v8=");

if (!Arrays.equals(fromHex, fromBase64)) {
    throw new IllegalStateException("Secret encoding mismatch");
}
~~~

**Không sử dụng** raw `String.getBytes()` với một secret đã được cấp dưới dạng Base64/hex. Nếu API được thiết kế chủ động dùng passphrase, việc biến passphrase thành key cần một **password-based KDF** có thiết kế riêng; không tự coi `passphrase.getBytes(UTF_8)` là secret ngẫu nhiên đủ mạnh.

### 4.2. So sánh các định dạng lưu/trao secret

| Định dạng | Lợi ích | Điểm phải kiểm soát |
|---|---|---|
| Binary / secret manager | Giữ bytes gốc, không có chuyển đổi text không cần thiết | API và giới hạn phân quyền |
| Hex | Dễ kiểm tra byte, không có ký tự `+/=` | Dài gấp đôi bytes, chuẩn hóa lowercase |
| Base64 standard | Ngắn hơn hex, phổ biến | `+`, `/`, `=` và strict decoding |
| Base64URL | Thuận tiện khi có ràng buộc URL-safe | `-`/`_`, padding policy khác |
| Passphrase text | Dễ đọc với con người | Không dùng trực tiếp làm secret HMAC nếu chưa có thiết kế KDF |

Secret storage, rotation và revocation phải tách khỏi việc lựa chọn text encoding. Một key ID mới phải trỏ tới đúng secret bytes và trạng thái hiệu lực. Không đưa secret vào request header, audit log hoặc query, bất kể nó đã được “mã hóa” Base64.

## 5. UTF-8 cho canonical request: quy định cả charset lẫn ngữ pháp

UTF-8 là lựa chọn phổ biến cho text trong giao thức đa ngôn ngữ, nhưng chỉ viết “canonical dùng UTF-8” **chưa đủ**. Cần xác định:

1. Field nào được ký, thứ tự field và biểu diễn field vắng mặt.
2. Separator: `LF`, `CRLF`, null byte, length prefix hay JSON/CBOR canonical.
3. Charset: UTF-8 **không BOM**; cách xử lý code point không hợp lệ.
4. Unicode normalization: NFC, NFD, NFKC hay **không normalization**.
5. Có trim whitespace, lowercase, uppercase hoặc sort field hay không.
6. Giới hạn field length và ký tự control để tránh chuỗi khác nhau ghép thành cùng canonical.
7. Cách ghi version/profile để tránh nhầm thuật toán hoặc semantics.

Ví dụ trong HMAC-V1:

~~~text
HMAC-V1
POST
/public/v1/orders
mode=preview&note=Caf%C3%A9
client-fixture-v1
2026-11-28T10:00:00Z
nonce-enc-001
<SHA256_BODY_LOWERCASE_HEX>
~~~

**Không có newline kết thúc** canonical message. Trong Markdown, code fence có thể hiển thị xuống dòng sau dòng cuối; không lấy trực tiếp toàn bộ code fence làm input HMAC mà không kiểm tra bytes.

### 5.1. Unicode `é` không chỉ có một cách biểu diễn

Hai chuỗi có thể hiển thị tương đương:

~~~text
NFC: "Café" = U+0043 U+0061 U+0066 U+00E9
NFD: "Café" = U+0043 U+0061 U+0066 U+0065 U+0301
~~~

Chúng không phải cùng dãy UTF-8 bytes. Nếu một phía normalize NFC còn phía kia giữ NFD, MAC khác. Với hợp đồng ký **raw query**, `note=Caf%C3%A9` được ký như text ASCII chứa percent escapes, không tự decode thành “Café”. Nếu hợp đồng có canonical Unicode, quy tắc decode, normalization và encode lại phải được mô tả chi tiết, version hóa và test.

**Không mặc định normalize Unicode** trong verifier để “chữa” signature mismatch. Normalization sai có thể làm nhiều request có nghĩa/representation khác nhau bị xem là cùng signed input.

### 5.2. LF, CRLF và BOM

| Dữ liệu | Bytes liên quan | Hệ quả |
|---|---|---|
| LF | `0A` | Separator của profile minh họa |
| CRLF | `0D 0A` | HMAC khác LF |
| UTF-8 BOM | `EF BB BF` | Nếu thêm đầu canonical, HMAC khác |
| Space ASCII | `20` | Khác tab và các Unicode spaces |
| Tab | `09` | Phải reject/định nghĩa nếu field ký không cho phép |
| Unicode replacement `U+FFFD` | `EF BF BD` trong UTF-8 | Che dấu input không hợp lệ nếu decoder silently replaces |

Trong Java, gọi `getBytes(StandardCharsets.UTF_8)` thay vì `getBytes()` không có tham số. Khi nhận input có byte UTF-8 malformed mà hợp đồng yêu cầu text strict, dùng decoder có `CodingErrorAction.REPORT` thay vì để ký tự thay thế `U+FFFD` tạo canonical khác.

### 5.3. Ngăn delimiter injection

Nếu canonical là chuỗi nhiều dòng, một header chưa được kiểm tra chứa CR/LF có thể làm lệch ranh giới field:

~~~text
fieldA = "hello\nadmin"
fieldB = "true"
~~~

Đừng đưa thẳng header này vào `String.join("\n", ...)`. Có hai lựa chọn:

- Với field có grammar hẹp (method, timestamp, nonce, key ID), **reject control characters**, enforce singleton header, giới hạn độ dài/charset.
- Với field tự do, định nghĩa escaping hoặc **length-prefix** canonical format không nhập nhằng, rồi version hóa/test vectors cho profile mới.

Việc servlet container thường cấm một số control characters trên HTTP wire không thay thế kiểm tra hợp đồng. Request có header trùng, folded/trailing whitespace hoặc một proxy chuẩn hóa khác nhau vẫn phải được xử lý theo chính sách.

## 6. Chọn encoding của URI: raw path và query không đồng nghĩa decoded URI

HTTP request-target đã có cơ chế **percent-encoding**. Ký URI cần nói rõ signer/verifier ký:

- **Raw public path/query**, giữ nguyên percent-escape và thứ tự query như client phát ra theo contract; hoặc
- **Canonical URI** đã parse/normalize/sort/encode lại bằng một thuật toán được công bố; hoặc
- **Logical route identifier** do hệ thống xác định qua một trust boundary đáng tin.

Bài này chọn **raw public path** và **raw public query**. Các ví dụ:

| Biểu diễn A | Biểu diễn B | Với raw-path/raw-query HMAC |
|---|---|---|
| `/orders/1` | `/orders/01` | Bytes khác, không tự coi tương đương |
| `/a%2Fb` | `/a/b` | Khác raw path; có rủi ro encoded slash |
| `/a/%2e%2e/admin` | `/admin` | Khác raw path; cần kiểm soát dot segments |
| `note=Caf%C3%A9` | `note=Café` | Khác raw representation |
| `q=hello%20world` | `q=hello+world` | Khác raw query, dù parser form có thể hiểu giống |
| `a=1&b=2` | `b=2&a=1` | Khác raw query theo contract minh họa |
| `role=user` | `role=user&role=admin` | Khác; tránh parameter pollution |
| Không query | `?` không có giá trị | Có thể cần quy ước phân biệt hoặc gộp rõ |

**Percent decoding không phải Base64 decoding.** `%C3%A9` là ba byte percent-encoded biểu diễn UTF-8 của `é`; Base64 là một cơ chế chuyển binary thành text hoàn toàn khác.

### 6.1. `+`, `%20` và quy tắc form encoding

Trong dữ liệu `application/x-www-form-urlencoded`, dấu `+` thường biểu diễn dấu cách. Trong **URL path**, không có quy tắc tổng quát “mọi `+` là dấu cách”. Trong **raw query**, `q=a+b` và `q=a%20b` là hai chuỗi khác nhau cho đến khi một thuật toán canonical query quy định chúng tương đương.

Không dùng `java.net.URLDecoder` dành cho form để canonicalize mọi path/query raw. Nếu API muốn canonical query, phải định nghĩa chính xác percent-decoding, charset, normalization, thứ tự tham số, cách xử lý duplicate và encode lại.

### 6.2. Query có tham số trùng và nhiều cấp diễn giải

Các framework có thể xử lý:

~~~text
role=user&role=admin
~~~

theo first-value, last-value, list hoặc từ chối. Nếu verifier tạo canonical từ `Map<String,String>` làm mất một giá trị nhưng business handler đọc `MultiValueMap` và dùng giá trị khác, MAC có thể **bảo vệ nghĩa A nhưng handler thực thi nghĩa B**.

Ưu tiên reject các duplicate parameters ở trường đơn trị; hoặc ký đầy đủ mọi occurrence theo một canonical query algorithm đã định nghĩa. Một request được chấp nhận phải ràng buộc đúng **effective operation/resource**, không chỉ đúng một chuỗi URI phụ.

### 6.3. Fragment không có trên wire

Đoạn `#fragment` là client-side URL fragment, không thuộc HTTP request-target. Không cố đưa fragment vào HMAC của HTTP request nếu server không thực sự nhận được nó như một field khác. Để có ký tự `#` literal trong query, phải encode theo URL contract (thường `%23`).

### 6.4. Proxy/gateway và “raw URI” có đáng tin?

Ví dụ:

~~~text
Client signs:  /public/v1/orders?mode=preview&note=Caf%C3%A9
Gateway maps:  /orders?mode=preview&note=Caf%C3%A9
Handler sees:  /orders
~~~

Nếu HMAC ký **public URI**, service không thể vô điều kiện lấy internal path `/orders` rồi so sánh với chữ ký client. Có thể:

1. Xác minh HMAC tại edge trước khi rewrite, rồi gửi assertion được bảo vệ và gắn với operation thật; hoặc
2. Chuyển trusted original-target metadata từ ingress, strip/overwrite header giả từ client và xác thực hop gateway→service; hoặc
3. Ký logical route identifier với mapping không nhập nhằng.

**Không tin `X-Original-URI`/`X-Forwarded-*` do client tự gửi.** Với Java Servlet `getRequestURI()` hoặc WebFlux `getURI().getRawPath()`, tên “raw” chỉ nói về representation mà framework đã nhận — không chứng minh gateway trước đó chưa normalize.

Phép thử cần đi qua gateway thật, với percent escapes, double encoding, slash, query order và HTTP/2 `:path` → HTTP/1.1 request-target. Không “chữa” 401 bằng cách loại path/query ra khỏi chữ ký.

## 7. Chọn encoding cho signed headers

Header names trong HTTP không phân biệt hoa/thường, còn **giá trị header** có thể có quy tắc khoảng trắng, kết hợp nhiều field lines hoặc cấm một số ký tự khác nhau theo giao thức/framework.

Nếu hợp đồng ký header, phải ghi:

- Tập header cần ký, tên canonical (thường lowercase ASCII).
- Có ký `Host`, `Content-Type`, `Content-Digest` hay header nghiệp vụ nào không.
- Header có đúng **một giá trị** hay có cho phép nhiều giá trị; cách xử lý duplicate, comma joining.
- Có trim optional whitespace trước/sau không; có collapse khoảng trắng giữa không.
- Thứ tự header canonical và thứ tự signed headers được liệt kê.
- Độ dài tối đa, charset/byte grammar và cách reject control characters.
- Cách gateway thêm, bỏ hoặc viết lại header.

Ví dụ: nếu V1 ký `content-type:application/json`, việc gateway thêm `; charset=utf-8` hoặc đổi thành `Application/Json` có thể làm MAC khác tùy canonical rules. Không tự coi header value case-insensitive chỉ vì **header name** case-insensitive.

**Đừng đưa credential/signature header vào chính danh sách signed fields nếu hợp đồng chưa giải quyết vòng lặp tự ký.** Thông thường `X-Signature` là **output**, còn version/key ID/timestamp/nonce và những metadata cần ràng buộc là **input canonical**.

### 7.1. Khi nào nên ký header hay body digest?

Với HTTP request body:

- Nếu ký raw body bytes, signer và verifier phải quan sát cùng entity bytes đã thỏa thuận.
- Nếu ký một header digest, verifier phải **tự hash body thực tế** và so với header digest, đồng thời bảo đảm header digest nằm trong MAC input.
- Nếu ký media type hoặc content encoding, những field đó cũng phải được canonicalize đúng.

Không chấp nhận body digest chỉ vì nó do client khai báo mà không xác minh lại. Không cho middleware parse JSON rồi serialize khác bytes trước khi tính digest nếu contract là raw body.

## 8. Chọn encoding cho body: bytes trước, object sau

Body có thể là JSON, protobuf, form, XML hoặc binary. **HMAC không biết cú pháp của body**; nó ký dãy byte hoặc digest của dãy byte theo hợp đồng.

Hai JSON:

~~~json
{"note":"Café","qty":2}
~~~

và:

~~~json
{"qty":2,"note":"Café"}
~~~

có thể tương đương về dữ liệu ứng dụng nhưng **khác bytes**, dẫn tới SHA-256/HMAC khác nhau khi ký raw body.

Tương tự:

- Khoảng trắng hoặc LF cuối của JSON làm bytes khác.
- `é` trực tiếp và `\u00e9` trong JSON là hai serialization khác nhau.
- Unicode NFC/NFD làm bytes khác.
- `Content-Encoding: gzip` có thể thay entity representation mà các tầng xử lý quan sát được.
- Reverse proxy có thể giải nén hoặc reserialize, phá hợp đồng ký.

### 8.1. SHA-256 body digest cho canonical text

Giả sử body là **UTF-8 bytes không có newline cuối**:

~~~text
{"note":"Café","qty":2}
~~~

Body này có **24 bytes** UTF-8. SHA-256 lowercase hex:

~~~text
1624a482a44dd3ec217a6586e92be7417e19c83559735e31c79836e88ccbe53b
~~~

Nếu body rỗng, SHA-256 của **mảng byte rỗng** vẫn là một digest hợp lệ — **khác** với việc bỏ trường body khỏi canonical. Hợp đồng cần định nghĩa rõ body absent/empty và cách request GET được xử lý.

### 8.2. Servlet và WebFlux phải bảo toàn body downstream

**Servlet/Spring MVC:** nếu security filter đọc `ServletInputStream` trước, controller có thể không còn body để đọc. `ContentCachingRequestWrapper` cache bytes được đọc nhưng **không mặc nhiên tạo stream phát lại** sau khi filter đã tiêu thụ. Cần wrapper có replay đúng hoặc cơ chế lấy digest không ảnh hưởng handler.

**Spring WebFlux:** `Flux<DataBuffer>` thường chỉ được consume một lần; phải giới hạn body size, xử lý pooled buffers/release đúng và decorates request an toàn để handler nhận body. Không `block()` event loop; không join toàn bộ stream vô hạn để hash payload lớn.

Đây là lý do **chọn raw-body encoding** phải đi kèm lựa chọn về buffering, streaming digest, request size cap và thứ tự “verify trước side effect”.

## 9. Chọn encoding chữ ký: Base64, Base64URL hay hex?

Sau khi HMAC-SHA256 tính xong, kết quả là **32 byte binary**. Để gửi qua HTTP header hoặc URL, cần text encoding.

| Định dạng | Bộ ký tự | Độ dài HMAC-SHA256 | Ưu điểm | Cần quy định |
|---|---|---:|---|---|
| Standard Base64 padded | `A–Z a–z 0–9 + / =` | **44 ký tự**, kết thúc bằng `=` | Phổ biến cho HTTP header | Padding bắt buộc, không newline |
| Base64URL unpadded | `A–Z a–z 0–9 - _` | **43 ký tự** | Phù hợp URL-safe tokens | Không padding, không lẫn variant |
| Lowercase hex | `0–9 a–f` | **64 ký tự** | Dễ debug test, chỉ ASCII đơn giản | Reject uppercase nếu profile yêu cầu lowercase |
| Raw binary | Bất kỳ octet | 32 bytes | Không tăng kích thước | Không phù hợp header text thông thường |

Base64 standard thích hợp với **header**, không cần URL-encode nếu header được xử lý đúng. Khi chữ ký nằm trong **query** (thường cần cân nhắc rủi ro log/cache/referrer), Base64URL giảm các vấn đề `+`, `/`, `=`. Dù vậy, việc đặt signature trong query không phải quyết định chỉ dựa trên encoding; request signing tốt thường dùng header để giảm nguy cơ lộ qua URL logs.

### 9.1. Chọn *một* format cho mỗi profile

V1 trong bài quy:

~~~http
X-Signature: db4nssi0uL3RZRiDDAuCBDvf1FOvab2k/hWipr4+/IY=
~~~

Không tự nhận các biến thể:

~~~text
db4nssi0uL3RZRiDDAuCBDvf1FOvab2k_hWipr4-_IY   # Base64URL unpadded
75be27b2c8b4b8bdd16518830c0b82043bdfd453af69bda4fe15a2a6be3efc86 # hex
~~~

Hai chuỗi trên có thể mã hóa **cùng MAC bytes**, nhưng **khác signature wire format**. Nếu server tự động chấp nhận cả ba để “tương thích”, client/server dễ diverge, parser phức tạp hơn, khó loại bỏ cách encode cũ.

Nếu cần đổi output encoding, hãy phát hành một **profile/version mới** hoặc thêm negotiation có whitelist và contract tests; không cho client chưa xác thực tự quyết định parser/algorithm tùy ý.

### 9.2. Strict Base64 decoding và tính canonical của chuỗi

Java `Base64.getDecoder()` có thể chấp nhận một số đầu vào thiếu padding. Nếu hợp đồng quy định **Base64 standard padded**, chỉ decode thành bytes chưa đủ: phải kiểm tra chuỗi đầu vào đúng alphabet, độ dài, padding và **re-encode ra đúng cùng chuỗi**.

~~~java
import java.util.Base64;
import java.util.regex.Pattern;

public final class StrictHmacMacEncoding {
    private static final Pattern SHA256_B64 =
            Pattern.compile("[A-Za-z0-9+/]{43}=");

    public static byte[] decodeHmacSha256(String text) {
        if (text == null || !SHA256_B64.matcher(text).matches()) {
            throw new IllegalArgumentException("Invalid MAC encoding");
        }
        byte[] bytes;
        try {
            bytes = Base64.getDecoder().decode(text);
        } catch (IllegalArgumentException malformed) {
            throw new IllegalArgumentException(
                    "Invalid MAC encoding", malformed);
        }
        if (bytes.length != 32
                || !Base64.getEncoder().encodeToString(bytes).equals(text)) {
            throw new IllegalArgumentException("Non-canonical MAC encoding");
        }
        return bytes;
    }
}
~~~

Hàm trên áp dụng cho **HMAC-SHA256 full-length output** (32 bytes), **không** áp dụng cho HMAC-SHA512 (64 bytes) hay MAC truncated được định nghĩa chính thức. Không dùng `Base64.getMimeDecoder()` cho signature header nếu protocol không cho phép xuống dòng/whitespace; MIME decoder có thể quá dễ dãi đối với một trường security-sensitive.

**Với Base64URL:** cần dùng `Base64.getUrlDecoder()` và, nếu contract không padding, kiểm tra định dạng không có `=` rồi re-encode bằng `withoutPadding()` để xác nhận canonical. **Với hex:** kiểm tra 64 ký tự lowercase `[0-9a-f]{64}`, parse bằng `HexFormat` và re-encode lowercase đúng chuỗi. Không “auto detect” định dạng từ độ dài rồi fallback.

### 9.3. So sánh bytes, không so sánh text

Sau strict decode, verifier tính `expectedMacBytes` từ canonical request và so sánh bằng primitive phù hợp, ví dụ:

~~~java
boolean matches = MessageDigest.isEqual(
        expectedMacBytes, suppliedMacBytes);
~~~

Không dùng `String.equals` trên Base64 như thay thế một kiểm tra MAC byte-level có chủ đích. `MessageDigest.isEqual` giúp tránh các kiểu so sánh byte dừng sớm thông thường, nhưng không bảo đảm toàn bộ request/key lookup có thời gian hoàn toàn giống nhau. Bảo vệ chống dò key ID/profile còn đòi hỏi policy errors, rate limits và đo đạc riêng.

## 10. Golden vector hoàn chỉnh có Unicode và query percent-encoding

Bộ vector dưới là **dữ liệu giả đã tính trước** bằng một phép tính mật mã tách khỏi lớp Java mẫu. Có thể lưu thành expected literals trong test SDK/server để phát hiện khác biệt encoding.

~~~yaml
profile: HMAC-V1
algorithm_jca: HmacSHA256
secret_hex: "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
secret_base64: "ABEiM0RVZneImaq7zN3u/wARIjNEVWZ3iJmqu8zd7v8="
method: POST
public_raw_path: /public/v1/orders
public_raw_query: mode=preview&note=Caf%C3%A9
key_id: client-fixture-v1
timestamp: "2026-11-28T10:00:00Z"
nonce: nonce-enc-001
body_utf8_no_trailing_newline: '{"note":"Café","qty":2}'
body_bytes_count: 24
body_sha256_lowerhex: "1624a482a44dd3ec217a6586e92be7417e19c83559735e31c79836e88ccbe53b"
canonical_utf8_bytes_count: 176
expected_hmac_sha256_lowerhex: "75be27b2c8b4b8bdd16518830c0b82043bdfd453af69bda4fe15a2a6be3efc86"
expected_signature_base64_padded: "db4nssi0uL3RZRiDDAuCBDvf1FOvab2k/hWipr4+/IY="
same_mac_base64url_unpadded: "db4nssi0uL3RZRiDDAuCBDvf1FOvab2k_hWipr4-_IY"
~~~

### 10.1. Canonical text chính xác

~~~text
HMAC-V1
POST
/public/v1/orders
mode=preview&note=Caf%C3%A9
client-fixture-v1
2026-11-28T10:00:00Z
nonce-enc-001
1624a482a44dd3ec217a6586e92be7417e19c83559735e31c79836e88ccbe53b
~~~

**Phần ký có 176 bytes UTF-8, không có LF cuối.** Nội dung canonical trên chỉ có ký tự ASCII vì Unicode body đã được đưa vào SHA-256 và query được biểu diễn bằng percent-encoding ASCII. Điều này không biến body “Café” thành ASCII: **byte của body vẫn là UTF-8 chứa `C3 A9`** cho ký tự `é`.

Nếu Java client tạo JSON khác thứ tự field, thêm khoảng trắng/newline, dùng `"Caf\u00e9"` thay vì `"Café"`, hoặc gateway decode/rewrite query, vector sẽ thay đổi theo đúng thiết kế.

### 10.2. Kiểm tra ba chiều của vector

1. Body có 24 bytes, SHA-256 đúng 32 bytes, hex digest có 64 ký tự.
2. Canonical UTF-8 có 176 bytes, dùng đúng tám dòng, bảy LF, không BOM/LF cuối.
3. HMAC-SHA256 có 32 bytes, Base64 standard padded đúng 44 ký tự và bằng literal trong vector.

Làm cả ba giúp khoanh vùng nguyên nhân: body encoding, canonical encoding hay signature output encoding.

## 11. Java 17: signer và verifier cho một encoding profile cố định

Ví dụ dưới dùng **contract HMAC-V1 minh họa**, nhận raw path/query đã được HTTP adapter cung cấp từ trust boundary phù hợp, và body bytes đã capture có giới hạn. Để dễ đọc, class sau chỉ kiểm tra grammar cơ bản; production vẫn phải kiểm tra HTTP method/URI cụ thể, giới hạn input, key state, anti-replay và authorization.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacEncodingV1 {
    private HmacEncodingV1() {}

    private static void requireAsciiField(String field) {
        if (field == null || field.length() > 4096) {
            throw new IllegalArgumentException("Invalid signed field");
        }
        for (int i = 0; i < field.length(); i++) {
            char c = field.charAt(i);
            if (c < 0x21 || c > 0x7E) {
                throw new IllegalArgumentException(
                        "Invalid signed field character");
            }
        }
    }

    public static String canonical(
            String method, String publicRawPath, String publicRawQuery,
            String keyId, String timestamp, String nonce, byte[] body)
            throws GeneralSecurityException {

        requireAsciiField(method);
        requireAsciiField(publicRawPath);
        // Empty query được phép theo HMAC-V1, query không có dấu '?'.
        String query = publicRawQuery == null ? "" : publicRawQuery;
        if (!query.isEmpty()) requireAsciiField(query);
        requireAsciiField(keyId);
        requireAsciiField(timestamp);
        requireAsciiField(nonce);
        if (body == null) {
            throw new IllegalArgumentException("Body byte snapshot required");
        }

        String digestHex = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));

        return String.join("\n",
                "HMAC-V1",
                method,
                publicRawPath,
                query,
                keyId,
                timestamp,
                nonce,
                digestHex);
    }

    public static byte[] macBytes(byte[] secret, String canonical)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8));
    }

    public static String signBase64(
            byte[] secret, String canonical)
            throws GeneralSecurityException {
        return Base64.getEncoder().encodeToString(
                macBytes(secret, canonical));
    }

    public static boolean verifyBase64(
            byte[] secret, String canonical, String suppliedBase64)
            throws GeneralSecurityException {
        final byte[] supplied;
        try {
            supplied = StrictHmacMacEncoding.decodeHmacSha256(
                    suppliedBase64);
        } catch (IllegalArgumentException malformed) {
            return false;
        }
        byte[] expected = macBytes(secret, canonical);
        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

**Giới hạn của code mẫu:** `requireAsciiField` chỉ chặn ASCII control/non-ASCII ở field canonical; nó **không** xác minh URI grammar, percent escapes, duplicate query, method allowlist, key ID format hay timestamp validity. Những kiểm tra đó phải do hợp đồng/parser cụ thể áp dụng. Một path có `%2F` vẫn là ASCII nhưng có thể bị cấm bởi route policy.

### 11.1. Decode secret từ cấu hình rõ ràng

~~~java
byte[] secret = HexFormat.of().parseHex(
        "00112233445566778899aabbccddeeff"
      + "00112233445566778899aabbccddeeff");

String canonical = HmacEncodingV1.canonical(
        "POST",
        "/public/v1/orders",
        "mode=preview&note=Caf%C3%A9",
        "client-fixture-v1",
        "2026-11-28T10:00:00Z",
        "nonce-enc-001",
        "{\"note\":\"Café\",\"qty\":2}"
                .getBytes(StandardCharsets.UTF_8));

String signature = HmacEncodingV1.signBase64(
        secret, canonical);
~~~

Không sử dụng secret hardcoded bên trên ngoài test. Trong production, cấp key bytes từ secret manager/HSM, giữ đúng key ID/tenant/profile và trạng thái active/expired/revoked. Không log mảng byte secret hoặc signature thật.

## 12. JUnit 5: test vector và test âm encoding

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;

class HmacEncodingContractTest {
    private static final byte[] SECRET = HexFormat.of().parseHex(
            "00112233445566778899aabbccddeeff"
          + "00112233445566778899aabbccddeeff");
    private static final byte[] BODY =
            "{\"note\":\"Café\",\"qty\":2}"
                    .getBytes(StandardCharsets.UTF_8);

    private String canonical(String query, byte[] body)
            throws Exception {
        return HmacEncodingV1.canonical(
                "POST", "/public/v1/orders", query,
                "client-fixture-v1",
                "2026-11-28T10:00:00Z",
                "nonce-enc-001", body);
    }

    @Test
    void goldenVectorMatchesExactUtf8AndMac() throws Exception {
        assertEquals(24, BODY.length);
        String original = canonical(
                "mode=preview&note=Caf%C3%A9", BODY);
        assertEquals(176, original.getBytes(StandardCharsets.UTF_8).length);
        assertEquals(
                "db4nssi0uL3RZRiDDAuCBDvf1FOvab2k/hWipr4+/IY=",
                HmacEncodingV1.signBase64(SECRET, original));
        assertTrue(HmacEncodingV1.verifyBase64(
                SECRET, original,
                "db4nssi0uL3RZRiDDAuCBDvf1FOvab2k/hWipr4+/IY="));
    }

    @Test
    void standardBase64AndUrlBase64AreNotInterchangeable()
            throws Exception {
        String original = canonical(
                "mode=preview&note=Caf%C3%A9", BODY);
        String urlSafe = "db4nssi0uL3RZRiDDAuCBDvf1FOvab2k_hWipr4-_IY";
        assertFalse(HmacEncodingV1.verifyBase64(
                SECRET, original, urlSafe));
        assertThrows(IllegalArgumentException.class,
                () -> StrictHmacMacEncoding.decodeHmacSha256(
                        "db4nssi0uL3RZRiDDAuCBDvf1FOvab2k/hWipr4+/IY"));
    }

    @Test
    void changedRawQueryFailsWhenUsingOriginalMac() throws Exception {
        String queryA = "mode=preview&note=Caf%C3%A9";
        String queryB = "note=Caf%C3%A9&mode=preview";
        String original = canonical(queryA, BODY);
        String actual = canonical(queryB, BODY);
        String originalMac = HmacEncodingV1.signBase64(SECRET, original);
        assertFalse(HmacEncodingV1.verifyBase64(
                SECRET, actual, originalMac));
    }

    @Test
    void bodySerializationChangesMac() throws Exception {
        String original = canonical(
                "mode=preview&note=Caf%C3%A9", BODY);
        byte[] differentJson = "{\"qty\":2,\"note\":\"Café\"}"
                .getBytes(StandardCharsets.UTF_8);
        String actual = canonical(
                "mode=preview&note=Caf%C3%A9", differentJson);
        assertFalse(HmacEncodingV1.verifyBase64(
                SECRET, actual,
                HmacEncodingV1.signBase64(SECRET, original)));
    }

    @Test
    void secretHexAndBase64DecodeToIdenticalBytes() {
        byte[] fromBase64 = Base64.getDecoder().decode(
                "ABEiM0RVZneImaq7zN3u/wARIjNEVWZ3iJmqu8zd7v8=");
        assertArrayEquals(SECRET, fromBase64);
    }
}
~~~

Test này giữ signature của query A khi kiểm tra query B. **Không ký lại query B sau mutation**; làm thế sẽ biến negative test thành request hợp lệ. Trong integration test phải dùng nonce mới, timestamp hợp lệ và key active, nếu không 401 có thể do replay/freshness chứ không chứng minh encoding.

### 12.1. Test normalization và percent encoding

Các cặp input quan trọng:

~~~text
note=Caf%C3%A9      vs note=Caf%c3%a9
q=hello%20world     vs q=hello+world
q=%2F               vs q=/
a=1&b=2             vs b=2&a=1
role=user           vs role=user&role=admin
/a%2Fb               vs /a/b
/orders              vs /orders/
~~~

**Raw profile:** các chuỗi khác text theo contract sẽ tạo MAC khác nếu giữ signature cũ. **Canonical URI profile:** một vài biến thể có thể được định nghĩa tương đương; điều kiện bắt buộc là verifier, router, authorization và handler **diễn giải cùng operation/resource**. Test phải có expected policy riêng, không ép mọi alias trả 401.

### 12.2. Fuzz parser và strict decoding

Sinh thêm:

- Invalid percent escapes (`%`, `%Z1`), encoded null, double-encoded slash/dot.
- Duplicate HMAC headers, blank signature, unexpected whitespace, overly long MAC.
- Base64 không padding, MIME newline, Base64URL mixed alphabet, noncanonical trailing bits.
- Lower/uppercase hex, odd-length hex, non-hex characters.
- UTF-8 malformed, surrogate bất hợp lệ ở producer, Unicode combining marks.
- Body gzip/JSON newline/serialization khác nhau, Content-Length không đáng tin.

Chỉ chạy malformed/fuzz traffic trong môi trường được phép, không bắn ồ ạt vào production gateway hoặc endpoint của đối tác thật. Bảo đảm memory, CPU và metrics cardinality có giới hạn.

## 13. Spring Security: nơi nào thực hiện encoding/verification?

Một pipeline hợp lý:

~~~text
HTTP server / proxy trust checks
   ↓
Route matcher + input/header size limits
   ↓
Read signed fields by canonical contract
   ↓
Capture/stream exact body bytes with bounds
   ↓
Lookup key ID → secret bytes + key/profile policy
   ↓
Construct canonical bytes using fixed encoding
   ↓
Decode signature using strict expected variant
   ↓
Compute HMAC and compare bytes
   ↓
Validate freshness, atomically claim nonce
   ↓
Create authenticated principal
   ↓
Spring Security authorization → business handler
~~~

**Authentication vs authorization:** HMAC xác minh request được ký bằng secret của một client/key record còn hiệu lực. Quyền `orders:write` hoặc resource/tenant ownership phải được quyết định từ dữ liệu đáng tin và kiểm tra ở authorization layer. Có chữ ký đúng không đồng nghĩa quyền hợp lệ.

**Header duplication:** một header `X-Signature` có hai giá trị không được để filter chọn first value còn proxy/library khác chọn last value. Quy định rõ singleton, reject duplicates theo contract. Tương tự với key ID, timestamp, nonce và version.

**Failure semantics:** MAC sai hoặc malformed credential thường 401 theo hợp đồng; path malformed có thể 400/404; key store/nonce store unavailable nên fail closed, thường 503; principal xác thực đúng nhưng thiếu quyền là 403. Không gọi controller rồi mới trả 401.

**Filter coverage:** route alias, trailing slash, encoded path hay gateway rewrite không được làm Spring Security matcher bỏ qua HMAC trong khi handler vẫn xử lý.

## 14. Encoding, timestamp, nonce và key rotation

Encoding đúng **không ngăn replay**. Một request được ký đúng có thể bị gửi lại y nguyên trong cửa sổ timestamp.

Vì vậy:

- Timestamp phải có grammar và độ chính xác rõ (ví dụ UTC ISO-8601 với `Z`), là field được ký, kiểm tra bằng server clock tin cậy.
- Nonce có grammar, length và encoding cố định (ví dụ ASCII token hoặc UUID text), cũng phải nằm trong MAC input.
- Sau khi MAC đúng và key/principal đã được xác định, claim nonce **atomically** theo scope đã được xác thực (ví dụ Redis `SET ... NX PX`).
- Nếu nonce store unavailable, request không được cho qua bằng cách “bỏ kiểm tra” — fail closed.
- Nếu chuyển signature profile hoặc key encoding, phải kiểm tra nonce namespace **xuyên phiên bản** để không vô tình cho phép xử lý lặp.
- Key rotation cần phân biệt `keyId`, secret bytes, secret textual encoding và profile. K1/K2 có thể đều active trong overlap nhưng key revoked phải bị từ chối theo policy.

**Một lỗi tinh vi:** secret manager chuyển cấu hình từ hex sang Base64 nhưng code vẫn gọi `HexFormat.parseHex`; hệ thống 401 hàng loạt. Ngược lại, nếu triển khai “thử decode hex, sai thì thử Base64” không có metadata rõ, kết quả khó kiểm toán và có thể tạo ambiguity. Hãy version hóa schema chứa secret, dùng một codec cố định trên mỗi key record và test rotation trước rollout.

### 14.1. Nonce string hay nonce bytes?

Nếu protocol gửi `X-Nonce: nonce-enc-001`, nó có thể quy nonce là ASCII token và ký **literal bytes** của chuỗi đó trong canonical. Nếu protocol gửi random nonce bytes được Base64URL hóa, cần quyết định canonical field chứa:

1. Raw Base64URL text đã kiểm tra canonical, hoặc
2. Bytes nonce sau decode được đưa vào một binary canonical format có length-prefix.

Hai cách không tương đương. Không để một SDK ký text còn verifier ký decoded bytes. Test cả nonce reuse và nonce có biểu diễn Base64 không canonical.

## 15. Quyết định encoding nào cần version mới?

Một số thay đổi phá tương thích, kể cả khi primitive HMAC vẫn là SHA-256:

| Thay đổi | Có phá signature cũ? | Khuyến nghị |
|---|---|---|
| Canonical UTF-8 → platform charset | Có thể | Không thay tùy ý; giữ UTF-8 |
| LF → CRLF | Có | Profile version mới nếu thật sự bắt buộc |
| Raw query → sorted canonical query | Có | Version hóa + golden vectors |
| Raw path → decoded path | Có, và có nguy cơ security mismatch | Đánh giá threat model, test proxy/route |
| Body SHA-256 lowercase hex → Base64 text | Có | Version hóa canonical profile |
| Standard Base64 padded → Base64URL unpadded | Thay wire format; bytes MAC có thể không đổi | Phiên bản hóa wire profile/parser |
| Secret storage Base64 → hex nhưng decode ra cùng bytes | Không, nếu toàn bộ hệ thống nhận **cùng secret bytes** | Migration schema/key metadata, test decode |
| HMAC-SHA256 → HMAC-SHA512 | Có | Profile mới, MAC length/secret policy/test mới |
| Chỉ đổi log format/metrics | Không nên | Không đụng canonical signing logic |

Không tự gọi `Mac.getInstance(clientHeader)` hay thử nhiều codec/algorithm đến khi có kết quả khớp. Client có thể khai profile version nhưng server phải so với allowlist/policy gắn trong key record, không fallback thuật toán yếu/cũ khi MAC profile mới sai.

### 15.1. Kế hoạch triển khai phiên bản mới

1. Công bố V2 contract với charset, URI rules, body digest và MAC output encoding.
2. Phát hành **golden vectors cho V1 và V2**, bao gồm non-ASCII/encoding edge cases.
3. Cấp key/profile mới và chính sách server per-client, không tự dùng secret cũ khi profile/key lifecycle không cho phép.
4. Chạy SDK cross-language, gateway E2E, negative tests và multi-replica replay tests.
5. Cho overlap có thời hạn; theo dõi adoption bằng enum profile **đã parse**, không từ header raw.
6. Chuyển client sang `v2-required` và test **MAC V1 đúng về toán học vẫn phải bị từ chối**.
7. Retire V1, revoke/disable key cũ, xác minh mọi region không còn chấp nhận.

**Không rollback** bằng cách chấp nhận lại key đã revoke hoặc bỏ signed fields chỉ để giảm 401.

## 16. Ma trận test contract tối thiểu trước production

| Case | Điều thiết lập | Kỳ vọng |
|---|---|---|
| Golden vector V1 | Secret decoded hex, UTF-8 body, raw query | HMAC Base64 literal khớp |
| Secret config Base64 | Decode thành 32 bytes y hệt hex | MAC không đổi |
| Secret bị dùng như text | `getBytes` trên Base64 config | MAC sai, không silently accepted |
| Base64URL thay Base64 header | Cùng MAC bytes nhưng sai wire format | Từ chối theo V1 |
| Base64 thiếu padding | Đúng alphabet nhưng không có `=` | Từ chối theo V1 strict |
| MAC bị truncate | 31/16 bytes thay vì 32 | Từ chối |
| Body serialization khác | Thay thứ tự field/Unicode escape | MAC sai nếu raw body được ký |
| CRLF hoặc LF cuối trong canonical | Đổi bytes canonical | Golden vector không khớp |
| Query percent encoding đổi | Giữ chữ ký cũ, gửi query khác | 401 trong raw mode |
| Query trùng tham số | Parser có nhiều values | Reject/verify đầy đủ theo contract |
| Encoded slash/dot path | Test qua gateway | Không verify operation A, execute B |
| Signed header duplicate | Hai giá trị khác nhau | Reject; không parser confusion |
| Malformed UTF-8 | Text field không hợp lệ | Strict reject, không replacement im lặng |
| Timestamp hết window | MAC đúng, timestamp cũ | 401 freshness, không vào handler |
| Replay same nonce | MAC đúng, gửi lại | Atomic reject, không side effect |
| Key mới/key revoked | Correct secret nhưng policy khác | Chấp nhận/từ chối theo lifecycle |
| HMAC hợp lệ nhưng thiếu scope | Principal readonly, route write | 403, không side effect |
| Key/nonce store unavailable | Fault injection staging | 503/fail closed |
| V2-required nhận V1 | V1 MAC đúng | Từ chối, không downgrade |

**Bài test chỉ kiểm tra crypto chưa đủ.** Cần có test HTTP thực chạy qua security chain và gateway thật, khẳng định cả **response status lẫn handler/DB/event không có side effect** đối với request bị từ chối. Một 401 do nonce đã dùng lại không chứng minh lỗi encoding: khi test đổi query/body, dùng nonce mới và timestamp còn hiệu lực.

## 17. Monitoring và chẩn đoán lỗi encoding

Tín hiệu hữu ích:

- `signature_invalid` tăng theo **route ID và profile enum**, đặc biệt ngay sau deploy gateway/SDK.
- `timestamp_invalid`, `nonce_replay`, `key_not_found`, `key_store_unavailable` được **phân biệt nội bộ**.
- Accepted/rejected/unavailable và p95/p99 HMAC duration theo route/profile.
- Số lỗi strict decoder Base64/hex hoặc malformed query/body vượt baseline.
- Sai khác giữa replica/region và giữa HTTP/1.1 ↔ HTTP/2 qua các hop.

**Không đưa** raw `X-Key-Id`, full signature, secret, canonical bytes, nonce, body hash, raw URI/query, IP hoặc request ID vào metric labels. Chúng có thể nhạy cảm và có cardinality lớn. Dùng enum hữu hạn; cần debug sâu thì dùng **synthetic golden vector** và log có quyền/retention kiểm soát.

### 17.1. Triage 401 sau khi đổi SDK/gateway

Kiểm tra theo thứ tự:

1. **Key bytes:** secret manager cấp Base64 hay hex? Server decode đúng chưa? Key ID/profile còn active không?
2. **Canonical grammar:** method, domain prefix, số dòng, LF/CRLF, newline cuối, UTF-8 BOM?
3. **Public URI:** client ký raw path/query nào; gateway có percent-decode, sort, collapse slash hay rewrite?
4. **Headers:** header name/value normalization, duplicate/whitespace và signed headers list?
5. **Body:** exact bytes có thay JSON serialization/gzip/charset/stream không?
6. **MAC output:** Base64 standard/URL, padding và ký tự sai, decode length 32/64?
7. **Freshness/replay:** client clock/NTP, timestamp format và nonce có bị claim từ request trước không?
8. **Authorization:** MAC đúng nhưng 403 thì xét scope/resource, đừng sửa signer.

Đối chiếu **golden-vector body SHA-256, canonical byte count và expected HMAC** từng chặng. Không cần ghi raw secret hay request production vào log chung.

## 18. Architecture Decision Record: tài liệu hóa lựa chọn encoding

Một ADR ngắn giúp người phát triển SDK, gateway và server không tự diễn giải khác nhau:

~~~yaml
decision_id: ADR-HMAC-ENCODING-001
status: Accepted
signature_profile: HMAC-V1
secret:
  canonical_type: opaque_random_bytes
  key_size_bytes: 32
  at_rest_text_format: base64_standard_padded
canonical_request:
  charset: UTF-8
  bom: forbidden
  line_separator: LF
  trailing_line_separator: forbidden
  path: trusted_public_raw_path
  query: trusted_public_raw_query_or_empty_without_question_mark
  body_digest: SHA-256_lowercase_hex_of_exact_body_bytes
  unicode_normalization: none_for_raw_path_query
  field_format: validated_ascii_for_metadata
signature:
  primitive: HmacSHA256
  output_bytes: 32
  header: X-Signature
  encoding: base64_standard_padded
  whitespace: forbidden
  alternative_encodings: rejected
security:
  timestamp: signed_utc
  nonce: signed_atomically_claimed_after_valid_mac
  key_policy: server_owned
  authorization: separate_from_authentication
verification:
  golden_vectors: required
  gateway_end_to_end: required
  cross_language_sdk_tests: required
~~~

**Đây là ADR minh họa, không phải metadata cần tạo trong workspace.** Với dự án thật, chính thức hóa decision qua cơ chế review phù hợp và công bố test vectors có secret giả. Nếu phát hiện một phần canonical khác giữa SDK và backend, phải sửa **contract hoặc implementation**, không chấp nhận vô điều kiện nhiều biểu diễn để che lỗi.

## 19. Checklist quyết định encoding trước khi công bố API

- [ ] Secret được cấp dưới dạng **bytes ngẫu nhiên**; Base64/hex chỉ là format lưu/truyền có metadata rõ.
- [ ] Không coi Base64 là encryption, không đưa secret thật vào URL/log/test.
- [ ] Canonical grammar đầy đủ: version, signed fields, order, missing values, LF/no final newline và UTF-8 không BOM.
- [ ] Text metadata có format/length/charset/CRLF rules; không có delimiter injection.
- [ ] Unicode normalization được quy định (hoặc rõ ràng không dùng), không tự sửa NFC/NFD ngoài contract.
- [ ] URI xác định raw public path/query hay canonical/logical target, kể cả encoding `%2F`, `%20`, `+`, duplicate params.
- [ ] Gateway sanitize forwarded metadata, signed target vẫn ràng buộc với effective handler.
- [ ] Signed headers có canonical names/values, singleton/duplicate policy và signed-header list.
- [ ] Body SHA-256 tính trên **exact bytes**; không parse/serialize lại JSON; downstream body còn khả dụng.
- [ ] Chọn **một** output encoding cho MAC của mỗi profile: standard Base64, Base64URL hoặc hex.
- [ ] Decoder strict: alphabet, padding, canonical re-encode và MAC byte length.
- [ ] MAC được so sánh byte-level; không đưa timing/lookup differences thành oracle chi tiết.
- [ ] HMAC version được đưa vào canonical/domain và được server key policy cho phép.
- [ ] Timestamp và nonce được ký, nonce claim atomically sau MAC; failure của store phải fail closed.
- [ ] Key rotation/revocation/tenant isolation được kiểm chứng; profile/key không tự fallback.
- [ ] HMAC xác thực request, **authorization kiểm tra quyền** sau đó.
- [ ] Có golden vectors Unicode + raw query + body digest + expected MAC độc lập.
- [ ] Có test sai charset/line ending/Base64 variant/padding/URI normalization/headers/body.
- [ ] Có integration test qua Spring Security và proxy/HTTP version thực, assert no side effect.
- [ ] Metrics/log dùng enum hữu hạn, không ghi secret, raw signature, nonce hoặc PII.

## 20. Kết luận

**Chọn encoding** cho HMAC là quyết định về **ngữ nghĩa byte-level** của cả giao thức, không phải việc chọn hàm `Base64.getEncoder()` ở dòng cuối. Một thiết kế đáng tin phải tách năm quyết định: **secret bytes**, **canonical text UTF-8**, **raw/canonical URI**, **exact body bytes/digest**, và **wire encoding của MAC**. Mỗi phép chuyển đổi phải có format, version, test vectors và chính sách xử lý input không hợp lệ.

Chỉ khi client, gateway và server tạo ra **cùng canonical bytes và cùng HMAC bytes**, đồng thời timestamp/nonce vẫn chống replay, key rotation không làm sai secret, authentication không tự cấp authorization và mọi lỗi đều **fail closed**, hệ thống mới đạt mục tiêu. Với HMAC, **“nhìn giống nhau” không đủ — bytes phải đúng, policy cũng phải đúng**.
