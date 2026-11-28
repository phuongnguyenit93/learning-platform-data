# Content encoding trong body canonicalization của HMAC request

> **Chương:** Body canonicalization  
> **Đề bài:** Content encoding  
> **Bối cảnh module:** Thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request bao gồm method, URI, header hoặc body theo hợp đồng ký. Bài học tập trung vào HTTP `Content-Encoding`, ảnh hưởng của nén/giải nén đối với byte body dùng để ký, kiểm thử proxy/gateway, và mối quan hệ với timestamp/nonce chống replay, key rotation cùng authorization.

## 1. Content encoding là gì?

Trong HTTP, **Content-Encoding** là trường mô tả **content coding đã áp dụng lên representation data** (nội dung được gửi). Một trường hợp phổ biến là client nén JSON bằng gzip trước khi gửi:

~~~http
POST /v1/orders?mode=preview HTTP/1.1
Host: api.example.test
Content-Type: application/json
Content-Encoding: gzip
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <base64url-hmac>

<bytes-cua-GZIP-dung-khong-phai-JSON-raw>
~~~

Ở đây:

- `Content-Type: application/json` cho biết **kiểu dữ liệu representation sau khi giải mã content coding** là JSON.
- `Content-Encoding: gzip` cho biết những byte **đang được truyền làm request content** là representation đã được nén bằng gzip.
- Nếu server muốn parse JSON, nó phải **giải nén gzip** trước khi giải mã UTF-8/JSON.
- Nếu signing contract quy định **ký body bytes đã nén**, sender phải băm **đúng các byte gzip được gửi**, không băm JSON sau giải nén.
- Nếu signing contract quy định **ký bytes sau giải nén**, cả hai phía phải áp dụng quy tắc decompress, giới hạn tài nguyên và xử lý proxy giống nhau. Đây là một lựa chọn khác, không tự tương đương.

**Content encoding không phải mã hóa bảo mật (encryption).** gzip làm giảm kích thước biểu diễn dữ liệu, nhưng không cung cấp tính bí mật, tính toàn vẹn hoặc bằng chứng ai gửi request. HTTPS/TLS bảo vệ kênh truyền; HMAC ràng buộc các thành phần request đã được hợp đồng ký.

### 1.1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt `Content-Encoding`, `Content-Type`, `Transfer-Encoding`, `Accept-Encoding` và `Content-Length`.
2. Giải thích vì sao **cùng nội dung JSON** nhưng hai gzip payload có thể khác byte và dẫn tới **MAC khác nhau**.
3. Chọn rõ **representation bytes trước khi giải nén** hay **decoded bytes sau khi giải nén** làm nguồn băm body.
4. Viết hợp đồng ký cố định thuật toán, header encoding, raw target, body digest và signed metadata.
5. Dùng JDK 17 thực hành nén gzip, băm SHA-256 trên encoded bytes, tạo HMAC-SHA-256, đối chiếu tag và giải nén có giới hạn sau xác minh.
6. Kiểm thử biến đổi body qua reverse proxy/gateway, lỗi content coding, compression bomb và cache/transcoding.
7. Kết hợp content encoding với timestamp/nonce, key rotation và authorization theo principal/tài nguyên thật.

## 2. Phân biệt năm khái niệm HTTP dễ nhầm

| Trường/khái niệm | Ví dụ | Chức năng | Ảnh hưởng đến HMAC |
|---|---|---|---|
| **Content-Type** | `application/json` | Mô tả media type của representation | Nên ký nếu parser hoặc business logic phụ thuộc media type |
| **Content-Encoding** | `gzip` | Mô tả content coding của representation | Phải có quy tắc rõ; nên ký khi nó quyết định cách hiểu body |
| **Transfer-Encoding** | `chunked` (HTTP/1.1) | Mã hóa truyền tải/framing của HTTP message | Không đồng nghĩa `Content-Encoding`; body bytes dùng ký thường lấy **sau khi giải transfer framing** |
| **Accept-Encoding** | `gzip, br` | Cho biết content codings client chấp nhận cho **response** | Không tự cho biết request body đã được nén hay chưa |
| **Content-Length** | `128` | Độ dài content bytes theo HTTP framing nếu trường được dùng hợp lệ | Với gzip request, phản ánh **kích thước encoded content**, không phải JSON sau giải nén |
| **Raw body bytes tại điểm verify** | Mảng byte `byte[]` | Dữ liệu thực mà HTTP stack chuyển cho ứng dụng sau xử lý framing | Phải xác định rõ nó còn encoded hay đã bị middleware decompress |

Lưu ý: `Transfer-Encoding: chunked` thuộc cách đóng gói message của HTTP/1.1, không dùng như một content coding. HTTP/2/3 không vận chuyển body bằng `Transfer-Encoding: chunked` theo kiểu HTTP/1.1. Nếu hợp đồng ký **encoded representation body**, sender và receiver nên cùng tính digest trên **content bytes đã bỏ transfer framing**, chứ không băm những ký tự `chunk-size` hoặc ranh giới frame trên dây.

### 2.1. Ba lớp byte trong một request

Giả sử một JSON document:

~~~json
{"orderId":"o-123","amount":150000}
~~~

Quá trình gửi có thể là:

~~~text
A. Semantic object:
   orderId=o-123, amount=150000
            |
            v
B. JSON serialize thành UTF-8:
   7B 22 6F 72 64 65 72 49 64 22 ... 7D
            |
            v   Content-Encoding: gzip
C. Encoded representation bytes:
   1F 8B 08 ... (gzip data và trailer)
            |
            v   HTTP message framing / TLS
D. Byte stream trên kết nối:
   request headers + framing + payload
~~~

Khi ký **theo lớp C**, digest là `SHA-256(gzipBytes)`. Ký theo lớp B nghĩa là `SHA-256(utf8JsonBytes)`. Ký theo lớp A đòi hỏi **canonical serialization có đặc tả riêng**; hai đối tượng JSON tương đương chưa chắc cho cùng byte serialization.

Không có phép HMAC nào tự biết lớp nào là “đúng”. **Hợp đồng ký quyết định**, và hai đầu phải có khả năng tái dựng chính xác đầu vào đó.

## 3. Vì sao Content-Encoding làm chữ ký dễ sai?

### 3.1. Cùng JSON, khác gzip bytes

Hai client cùng nén chuỗi JSON, nhưng dùng khác compression level, implementation hoặc metadata trong gzip header. Hai payload có thể:

~~~text
gzipBytesA != gzipBytesB
gunzip(gzipBytesA) == gunzip(gzipBytesB)
~~~

Cả hai giải nén thành **cùng JSON bytes**, nhưng:

~~~text
SHA-256(gzipBytesA) != SHA-256(gzipBytesB)   (gần như chắc chắn)
HMAC(K, canonical(..., hashA)) != HMAC(K, canonical(..., hashB))
~~~

Vì thế, nếu hợp đồng ký **encoded bytes**, sender phải gửi **nguyên mảng byte đã ký**; receiver băm **nguyên mảng byte nhận được**, không tự nén lại JSON và không dùng gzip output của một thư viện khác để dựng expected digest.

**Ví dụ cụ thể:** một gzip stream có thể mang thời gian trong bốn byte MTIME của header. Đổi các byte MTIME theo cú pháp gzip hợp lệ không đổi nội dung giải nén, nhưng đổi bytes đã ký. Chương trình Java ở mục 7 có bài test đúng tính chất này.

### 3.2. Content-Encoding absent, identity và gzip

Ba request có thể khác biểu diễn:

~~~text
Request A: không có Content-Encoding
           body = raw UTF-8 JSON

Request B: Content-Encoding: identity
           body = raw UTF-8 JSON

Request C: Content-Encoding: gzip
           body = gzip(raw UTF-8 JSON)
~~~

Trong HTTP, `identity` biểu diễn không có content coding. Tuy nhiên, **signing contract cần nêu rõ** header absent có tương đương với explicit `identity` hay không. Ví dụ của bài này chọn **không chấp nhận explicit identity**, chỉ cho phép:

- **Không có** `Content-Encoding` ⇒ body không áp content coding, dòng canonical encoding rỗng.
- **Có đúng một** `Content-Encoding: gzip` ⇒ body là gzip bytes, dòng canonical encoding bằng `gzip`.
- Mọi giá trị khác hoặc nhiều Content-Encoding ⇒ **reject** theo hợp đồng minh họa.

Đây là chính sách của ví dụ chứ không phải phán quyết rằng mọi HTTP content coding ngoài gzip đều không hợp lệ. Hệ thống thật có thể dùng `br`, `deflate`, `zstd` hoặc chuỗi nhiều coding nếu các phía và hạ tầng hỗ trợ, nhưng mỗi trường hợp đòi hỏi **parser, signature contract và test vectors phù hợp**.

### 3.3. Tên content coding và thứ tự áp dụng

Content coding là tên token HTTP; tên coding được định nghĩa không phân biệt chữ hoa/chữ thường. Vì vậy, ví dụ sẽ chuẩn hóa:

~~~text
Content-Encoding: gzip
Content-Encoding: GZIP
Content-Encoding:  gzip
~~~

về cùng literal canonical `gzip`, sau khi đã parse header an toàn và trim optional whitespace ở đầu/cuối. **Không áp dụng cách chuẩn hóa này lên raw body bytes**.

Nếu dùng nhiều codings, ví dụ:

~~~http
Content-Encoding: gzip, br
~~~

thứ tự có ý nghĩa: sender áp các coding theo thứ tự được nêu; receiver cần decode theo **thứ tự ngược lại**. Không thể sort danh sách coding như danh sách tham số query. Vì hợp đồng bài học chỉ cho một coding, trường này sẽ bị **reject**, không tự chọn coding đầu hoặc cuối.

## 4. Chọn byte body nào để ký?

Có ba chiến lược cần phân biệt:

| Chiến lược | Dữ liệu băm/ký | Ưu điểm | Rủi ro |
|---|---|---|---|
| **A. Ký encoded body bytes** | SHA-256 trên mảng bytes sau content coding nhưng trước giải nén | Rõ byte, phát hiện mọi thay đổi compressed representation | Gateway decompress/recompress làm HMAC fail; cùng JSON có nhiều tag hợp lệ theo từng byte |
| **B. Ký decoded body bytes** | Giải content coding rồi SHA-256 dữ liệu sau decode | Cho phép một số representation nén khác nhau có cùng digest | Phải giải nén **trước MAC** với giới hạn nghiêm; dễ mismatch middleware và bị tiêu thụ tài nguyên |
| **C. Ký canonical media representation** | Giải nén, parse, canonical serialize (ví dụ JSON theo đặc tả) rồi băm | Có thể ổn định trước khác biệt whitespace/serialization | Phức tạp; cần chuẩn hóa đầy đủ số, Unicode, thứ tự field, duplicate keys, encoding; rủi ro parser khác nghĩa |

Không nên tự chuyển từ chiến lược A sang B khi thấy HMAC fail: đó là **đổi giao thức bảo mật**, không phải một bước sửa lỗi vô hại.

**Bài này chọn chiến lược A** cho hợp đồng minh họa `hmac-content-encoding-v1`. Body digest tính từ **encoded representation bytes tại điểm verifier nhận sau HTTP transfer framing**, tức trước bất kỳ bước content decoding nào.

### 4.1. Hệ quả của chiến lược A

Sender:

~~~text
1. JSON serialize (UTF-8) thành rawJsonBytes
2. Nếu dùng gzip: encodedBytes = gzip(rawJsonBytes)
   Nếu không: encodedBytes = rawJsonBytes
3. SHA-256(encodedBytes) -> lowercase hex
4. Tạo canonical request gồm method, target, Content-Type,
   Content-Encoding, client ID, key ID, timestamp, nonce, body hash
5. HMAC-SHA-256(secret, canonical UTF-8 bytes)
6. Gửi ĐÚNG encodedBytes cùng các signed headers và signature
~~~

Receiver:

~~~text
1. HTTP parser kiểm tra framing và cấp encodedBytes sau transfer decoding
2. Giới hạn kích thước encodedBytes và kiểm tra signed headers
3. Xác thực client/key/audience, timestamp và canonical request
4. Tính SHA-256 trên encodedBytes khi CHƯA giải nén
5. So HMAC tag theo dạng chuẩn, sau đó reserve nonce nguyên tử
6. Chỉ sau khi xác thực: gzip-decode nếu header chỉ rõ,
   giới hạn decoded size, parse JSON và làm authorization/business
~~~

**Tuyệt đối không** dùng lại decoded JSON từ request body deserializer để dựng SHA-256 khi contract yêu cầu encoded bytes. Điều đó có thể làm mất bytes gốc và tạo hai khái niệm “request đã ký” và “request được xử lý” khác nhau.

### 4.2. Một ví dụ byte-level

~~~text
Original document bytes:  {"x":1}
Without encoding:         UTF-8 bytes -> SHA-256(U)
With gzip:                 gzip bytes -> SHA-256(G)
Content-Encoding absent:  signed encoding field = ""
Content-Encoding gzip:    signed encoding field = "gzip"
~~~

Ngay cả khi `gunzip(G) = U`, hai canonical requests khác cả **encoding field** lẫn **body digest**. Vì thế sender không được ký JSON raw rồi gửi gzip bytes dưới header `Content-Encoding: gzip`, hoặc ngược lại.

## 5. Hợp đồng ký HTTP hmac-content-encoding-v1

Ví dụ chọn **một version rõ ràng** để bài thực hành có thể độc lập với quy tắc của các API khác. Đây không phải định dạng RFC 9421 mặc định.

### 5.1. Các thành phần canonical

| Dòng | Trường | Quy tắc của hợp đồng minh họa |
|---|---|---|
| 1 | Version | Literal `hmac-content-encoding-v1` |
| 2 | HTTP method | Ví dụ chỉ hỗ trợ `POST`, không được đổi khi ký |
| 3 | Raw request target | Encoded path/query theo contract, ví dụ `/v1/orders?mode=preview` |
| 4 | Content-Type | Chấp nhận `application/json`, trim OWS và lowercase |
| 5 | Content-Encoding | **Không có header** ⇒ dòng rỗng; đúng một `gzip` ⇒ literal `gzip`, chuẩn hóa case/OWS |
| 6 | Client ID | `X-Client-Id`, đã được cấp và được ký |
| 7 | Key ID | `X-Key-Id` để lookup secret của client/audience, được ký |
| 8 | Timestamp | `X-Timestamp`, Unix seconds thập phân canonical |
| 9 | Nonce | `X-Nonce`, Base64URL không padding của 16–32 byte ngẫu nhiên |
| 10 | Body digest | Lowercase hex SHA-256 của **encoded request content bytes** |

Ghép các dòng bằng **LF** (`\n`), **không có LF cuối**, mã hóa canonical string bằng UTF-8. Tag là **HMAC-SHA-256 đầy đủ 32 byte**, truyền trong `X-Signature` bằng Base64URL không padding (thường dài 43 ký tự).

Trong ví dụ, `Content-Type: application/json; charset=UTF-8` bị reject vì hợp đồng chỉ nhận chính xác `application/json`. Đây là giới hạn **có chủ đích** để giảm chi tiết nhiễu; một API thật có thể hỗ trợ media-type parameters bằng parser/canonicalization được mô tả và kiểm thử riêng.

### 5.2. Gzip request mẫu

~~~http
POST /v1/orders?mode=preview HTTP/1.1
Host: api.example.test
Content-Type: application/json
Content-Encoding: gzip
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <base64url-hmac-sha256>

<gzip-binary-data>
~~~

Canonical request gồm **10 dòng**:

~~~text
hmac-content-encoding-v1
POST
/v1/orders?mode=preview
application/json
gzip
merchant-17
key-2026-11
1795824000
b75sZVQmhTBcfnX-bNbGqw
<sha256-hex-of-gzip-bytes>
~~~

Dòng cuối là **chỗ giữ chỗ** vì digest tùy chính xác byte gzip thực tế. Không copy literal trong dấu ngoặc vào chữ ký; phải băm mảng gzip bytes đã được tạo cho request này.

### 5.3. Khi request không có Content-Encoding

~~~http
POST /v1/orders?mode=preview HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <base64url-hmac-sha256>

{"orderId":"o-123"}
~~~

Canonical string có **dòng thứ năm rỗng**:

~~~text
hmac-content-encoding-v1
POST
/v1/orders?mode=preview
application/json

merchant-17
key-2026-11
1795824000
b75sZVQmhTBcfnX-bNbGqw
<sha256-hex-of-raw-json-bytes>
~~~

Giả sử request **không có body**, SHA-256 của 0 byte là:

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

**Không nhầm:** body không có content coding **không có nghĩa** body rỗng. Một request có JSON raw bytes và không có `Content-Encoding` vẫn phải băm toàn bộ JSON bytes thực tế. Một **gzip representation của nội dung rỗng** cũng có mảng encoded bytes không rỗng vì gzip có header/trailer; digest của gzip(empty) khác digest của 0 byte.

### 5.4. Các trường ký thêm và audience

Hợp đồng ví dụ đưa Content-Type/Encoding, method, target và body hash vào signature. Nó **không đưa Host vào chuỗi ký**. Để ngăn signature áp dụng chéo dịch vụ, server phải ràng buộc client/key ID với **audience/môi trường dịch vụ** tại key store; nếu cần, đưa audience/authority được xác định từ nguồn đáng tin vào phiên bản canonical request mới.

Signature bảo vệ chỉ những thành phần được ký. Nếu một header chưa ký như `X-Mode` làm thay đổi hành vi nghiệp vụ, phải thêm nó vào hợp đồng ký hoặc loại bỏ ảnh hưởng của header đó.

## 6. Content-Encoding ở gateway và trust boundary

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant G as Gateway / Reverse Proxy
    participant V as HMAC Verifier
    participant K as Key Store
    participant N as Shared Nonce Store
    participant B as Business Handler
    C->>C: Serialize JSON, gzip và ký encoded bytes
    C->>G: HTTPS + Content-Encoding:gzip + signature
    G->>G: Có thể giải nén/chuyển coding
    G->>V: Target, headers, encoded body tại verifier
    V->>K: Tra secret theo client/keyId/audience
    K-->>V: Secret và key status
    V->>V: Kiểm tra header, timestamp và HMAC trên encoded bytes
    V->>N: Reserve nonce nguyên tử
    N-->>V: Thành công
    V->>B: Decode gzip có giới hạn, kiểm tra quyền và xử lý
~~~

### 6.1. Các phép biến đổi cần kiểm thử

| Hành vi hạ tầng | Điều xảy ra với HMAC theo hợp đồng A | Cách xử lý đúng |
|---|---|---|
| Proxy giữ nguyên Content-Encoding và encoded bytes | Tag có thể xác minh thành công | Cấu hình raw body passthrough, kiểm tra điểm lấy bytes |
| Gateway **giải nén gzip** rồi bỏ Content-Encoding | Body digest và encoding field đổi | **Verify trước giải nén** hoặc thiết kế lại ranh giới bảo mật |
| Gateway giải nén rồi **nén lại gzip** | Gzip bytes có thể khác dù JSON giống | Không tự re-gzip trước verify; verify ở edge nếu cần |
| Proxy đổi case `GZIP` → `gzip` | Ví dụ normalize field, canonical text không đổi | Được nếu đúng một header và bytes không đổi |
| Proxy thêm `Content-Encoding: gzip` nhưng không nén | Tag/semantics thay đổi, nội dung có thể lỗi | Reject; không “sửa” bằng cách bỏ header trong canonical |
| Proxy loại bỏ header gzip nhưng giữ gzip bytes | Receiver không biết phải decode, MAC khác | Reject hoặc sửa cấu hình proxy |
| Hai giá trị `gzip, br` hay duplicate header | Ngoài hợp đồng ví dụ | Reject, không chọn last/first |
| HTTP/1.1 chunked → HTTP/2 DATA frames | Framing khác nhưng representation bytes có thể y nguyên | Băm bytes **sau transfer framing**, không băm chunk markers |
| Reverse proxy rewrite path/query | Canonical target khác | Verify ở đúng ranh giới hoặc dùng trusted original target |
| WAF tự parse body rồi serialize lại | Dữ liệu JSON có thể tương đương nhưng bytes khác | Không reserialize body trước MAC, hoặc thay contract |
| Thay Content-Type sau khi ký | Canonical text khác, parser có thể đổi | Không bỏ qua Content-Type trong signed fields |

### 6.2. Chọn điểm verify

**Kiến trúc 1: verify tại edge, trước biến đổi.** Gateway có HMAC verifier truy cập đúng encoded bytes và original target. Sau khi verify, gateway có thể decode và chuyển principal an toàn đến backend theo ranh giới tin cậy. Nếu gateway chỉ chuyển một header “đã verify” mà backend chấp nhận từ internet, attacker có thể giả header. Cần strip header ngoài, xác thực gateway nội bộ và bảo vệ giao tiếp.

**Kiến trúc 2: backend verify trực tiếp.** Proxy phải **bảo toàn encoded representation**, signed headers và target đúng hợp đồng. HMAC filter cần chạy **trước** middleware decompress/deserializer có thể làm mất raw bytes. Nếu upstream đã transform body, không thể tái tạo chắc chắn gzip bytes ban đầu từ JSON đã giải nén.

Không tin `X-Original-URI`, `X-Original-Content-Encoding` hay `X-Forwarded-*` do internet client tự gửi. Proxy đáng tin phải tự tạo metadata sau khi xóa giá trị client tự khai và bảo vệ kết nối proxy → backend; metadata này cũng không tự thay thế signature kiểm chứng tại ranh giới phù hợp.

### 6.3. Content-Length và nguy cơ đọc nhầm dữ liệu

Với request gzip:

~~~text
JSON raw length:       300 bytes
Gzip encoded length:   140 bytes   (minh họa)
Content-Length:        140        (nếu HTTP/1.1 dùng header này)
Byte body để ký:       140 bytes gzip
Body sau gunzip:       300 bytes JSON
~~~

Không dùng `Content-Length` làm **decoded body length**, và không tự coi `Content-Length: 0` là đồng nghĩa với một gzip stream biểu diễn body rỗng. Header này thuộc HTTP message framing và phải được kiểm tra nhất quán cùng transfer framing; tình huống `Content-Length` / `Transfer-Encoding` mâu thuẫn cần được HTTP stack xử lý an toàn, tránh request smuggling.

## 7. Java 17: ký encoded gzip bytes và xác minh trước khi giải nén

Chương trình sau chạy **chỉ với JDK 17+**, không cần Gradle/JUnit. Nó cho phép **không có Content-Encoding** hoặc **đúng một gzip coding**, đóng băng mảng body tại lúc tạo request, tạo canonical request, ký HMAC và chỉ giải nén sau khi `verifyMac` thành công. Bộ giải nén áp giới hạn decoded bytes để minh họa cách hạn chế compression bomb.

### 7.1. Mã nguồn độc lập

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class ContentEncodingHmacDemo {
    private static final String VERSION = "hmac-content-encoding-v1";
    private static final String ALG = "HmacSHA256";
    private static final int MAX_ENCODED_BYTES = 128 * 1024;
    private static final int MAX_DECODED_BYTES = 64 * 1024;

    private ContentEncodingHmacDemo() {}

    public record Request(
            String method,
            String rawTarget,
            String contentType,
            String contentEncoding,
            String clientId,
            String keyId,
            String timestamp,
            String nonce,
            byte[] bodyBytes) {
        public Request {
            if (bodyBytes == null) {
                throw new IllegalArgumentException("Missing body bytes");
            }
            bodyBytes = bodyBytes.clone();
        }
        @Override
        public byte[] bodyBytes() {
            return bodyBytes.clone();
        }
    }

    // null = header vắng mặt; không gộp "identity" vào absent.
    public static String canonicalEncoding(String header) {
        if (header == null) return "";
        if (header.length() > 64
                || header.chars().anyMatch(
                        c -> (c < 0x20 && c != '\t') || c > 0x7E)) {
            throw new IllegalArgumentException("Bad Content-Encoding");
        }
        String normalized = header.trim().toLowerCase(Locale.ROOT);
        if (!"gzip".equals(normalized)) {
            throw new IllegalArgumentException("Unsupported coding");
        }
        return normalized;
    }

    private static String asciiToken(String value, int max) {
        if (value == null || value.isEmpty() || value.length() > max
                || value.chars().anyMatch(c -> c < 0x21 || c > 0x7E)) {
            throw new IllegalArgumentException("Bad signed field");
        }
        return value;
    }

    public static byte[] canonicalBytes(Request request)
            throws GeneralSecurityException {
        if (request == null || !"POST".equals(request.method())) {
            throw new IllegalArgumentException("Only POST is supported");
        }
        if (!asciiToken(request.rawTarget(), 2048).matches(
                "/v1/orders(?:/[A-Za-z0-9_-]{1,64})?"
              + "(?:\\?mode=(?:preview|commit))?")) {
            throw new IllegalArgumentException("Bad request target");
        }
        String rawType = request.contentType();
        if (rawType == null || rawType.length() > 128
                || rawType.chars().anyMatch(
                        c -> (c < 0x20 && c != '\t') || c > 0x7E)) {
            throw new IllegalArgumentException("Bad Content-Type");
        }
        String type = rawType.trim().toLowerCase(Locale.ROOT);
        if (!"application/json".equals(type)) {
            throw new IllegalArgumentException("Unsupported media type");
        }
        String encoding = canonicalEncoding(request.contentEncoding());
        String client = asciiToken(request.clientId(), 64);
        String keyId = asciiToken(request.keyId(), 64);
        String time = asciiToken(request.timestamp(), 20);
        String nonce = asciiToken(request.nonce(), 43);
        if (!client.matches("[A-Za-z0-9_-]+")
                || !keyId.matches("[A-Za-z0-9_-]+")
                || !time.matches("[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException("Invalid metadata");
        }

        final byte[] nonceBytes;
        try {
            nonceBytes = Base64.getUrlDecoder().decode(nonce);
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("Invalid nonce", e);
        }
        if (nonceBytes.length < 16 || nonceBytes.length > 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(nonceBytes).equals(nonce)) {
            throw new IllegalArgumentException("Invalid nonce encoding");
        }

        byte[] encoded = request.bodyBytes();
        if (encoded.length > MAX_ENCODED_BYTES) {
            throw new IllegalArgumentException("Encoded body too large");
        }
        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(encoded));

        String canonical = String.join("\n",
                VERSION,
                request.method(),
                request.rawTarget(),
                type,
                encoding,
                client,
                keyId,
                time,
                nonce,
                bodyHash);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] hmac(byte[] secret, byte[] input)
            throws GeneralSecurityException {
        if (secret == null || secret.length != 32 || input == null) {
            throw new IllegalArgumentException("Bad key/message");
        }
        Mac mac = Mac.getInstance(ALG);
        mac.init(new SecretKeySpec(secret, ALG));
        return mac.doFinal(input);
    }

    public static String sign(Request request, byte[] secret)
            throws GeneralSecurityException {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(hmac(secret, canonicalBytes(request)));
    }

    // Chỉ xác minh MAC. Key status, clock, nonce store ở tầng receiver.
    public static boolean verifyMac(Request request, byte[] secret,
                                    String signature)
            throws GeneralSecurityException {
        if (signature == null || signature.length() != 43) return false;
        final byte[] received;
        try {
            received = Base64.getUrlDecoder().decode(signature);
        } catch (IllegalArgumentException ex) {
            return false;
        }
        if (received.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(received).equals(signature)) {
            return false;
        }
        byte[] expected = hmac(secret, canonicalBytes(request));
        return MessageDigest.isEqual(expected, received);
    }

    public static byte[] gzip(byte[] source) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (GZIPOutputStream gz = new GZIPOutputStream(output)) {
            gz.write(source);
        }
        return output.toByteArray();
    }

    // Chỉ gọi SAU khi MAC, timestamp và nonce đã hợp lệ.
    // Đầu vào được giới hạn size, decoded output có quota riêng.
    public static byte[] decodeLimited(Request request)
            throws IOException {
        String encoding = canonicalEncoding(request.contentEncoding());
        byte[] encoded = request.bodyBytes();
        if (encoded.length > MAX_ENCODED_BYTES) {
            throw new IllegalArgumentException("Encoded body too large");
        }
        if (encoding.isEmpty()) {
            if (encoded.length > MAX_DECODED_BYTES) {
                throw new IllegalArgumentException("Plain body too large");
            }
            return encoded;
        }
        ByteArrayOutputStream decoded = new ByteArrayOutputStream();
        try (GZIPInputStream input = new GZIPInputStream(
                new ByteArrayInputStream(encoded))) {
            byte[] buffer = new byte[4096];
            int n;
            while ((n = input.read(buffer)) != -1) {
                if (decoded.size() + n > MAX_DECODED_BYTES) {
                    throw new IllegalArgumentException(
                            "Decoded body too large");
                }
                decoded.write(buffer, 0, n);
            }
        }
        return decoded.toByteArray();
    }

    private static void require(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    private static void expectInvalid(Runnable runnable) {
        boolean rejected = false;
        try {
            runnable.run();
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        require(rejected, "Expected rejected input");
    }

    public static void main(String[] args)
            throws GeneralSecurityException, IOException {
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret); // Demo key only.
        byte[] rawJson = ("{\"orderId\":\"o-123\","
                + "\"amount\":150000}").getBytes(StandardCharsets.UTF_8);
        byte[] compressed = gzip(rawJson);

        byte[] nonceBytes = new byte[16];
        new SecureRandom().nextBytes(nonceBytes);
        String nonce = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(nonceBytes);
        String timestamp = Long.toString(Instant.now().getEpochSecond());

        Request original = new Request(
                "POST", "/v1/orders?mode=preview",
                "application/json", "gzip",
                "merchant-17", "key-2026-11",
                timestamp, nonce, compressed);

        String signature = sign(original, secret);
        require(verifyMac(original, secret, signature), "Valid gzip MAC");
        require(Arrays.equals(rawJson, decodeLimited(original)),
                "Decoded JSON must match");

        // Đổi metadata MTIME của gzip; vẫn giải nén cùng JSON.
        byte[] gzipVariant = compressed.clone();
        gzipVariant[4] = (byte) (gzipVariant[4] ^ 0x01);
        Request sameJsonDifferentGzip = new Request(
                original.method(), original.rawTarget(),
                original.contentType(), original.contentEncoding(),
                original.clientId(), original.keyId(),
                original.timestamp(), original.nonce(), gzipVariant);
        require(Arrays.equals(rawJson, decodeLimited(sameJsonDifferentGzip)),
                "Gzip variant still decodes to the same JSON");
        require(!verifyMac(sameJsonDifferentGzip, secret, signature),
                "Changed encoded bytes must fail MAC");

        // Cùng compressed bytes nhưng bỏ Content-Encoding:
        // MAC không được chấp nhận.
        Request removedCoding = new Request(
                original.method(), original.rawTarget(),
                original.contentType(), null,
                original.clientId(), original.keyId(),
                original.timestamp(), original.nonce(), compressed);
        require(!verifyMac(removedCoding, secret, signature),
                "Changed Content-Encoding must fail");

        Request changedTarget = new Request(
                original.method(), "/v1/orders?mode=commit",
                original.contentType(), original.contentEncoding(),
                original.clientId(), original.keyId(),
                original.timestamp(), original.nonce(), compressed);
        require(!verifyMac(changedTarget, secret, signature),
                "Changed request target must fail");

        Request plain = new Request(
                original.method(), original.rawTarget(),
                original.contentType(), null,
                original.clientId(), original.keyId(),
                original.timestamp(), original.nonce(), rawJson);
        require(verifyMac(plain, secret, sign(plain, secret)),
                "Plain JSON with own signature must pass");
        require(!sign(plain, secret).equals(signature),
                "Plain and gzip signatures must differ");
        require(Arrays.equals(rawJson, decodeLimited(plain)),
                "Plain body must not be decompressed");

        require("gzip".equals(canonicalEncoding(" GZIP ")),
                "Content coding token case/OWS");
        expectInvalid(() -> canonicalEncoding("identity"));
        expectInvalid(() -> canonicalEncoding("gzip, br"));
        expectInvalid(() -> canonicalEncoding("gzip\r\nx: y"));

        System.out.println("PASS content-encoding HMAC/gzip checks");
    }
}
~~~

Đặt mã trong `ContentEncodingHmacDemo.java` và chạy:

~~~bash
javac ContentEncodingHmacDemo.java
java ContentEncodingHmacDemo
~~~

Kết quả kỳ vọng:

~~~text
PASS content-encoding HMAC/gzip checks
~~~

### 7.2. Kết quả test chứng minh điều gì?

1. Một gzip request được ký trên encoded bytes và kiểm tra lại bằng cùng secret có MAC hợp lệ.
2. `gzipVariant` thay **một byte MTIME ở gzip header**, vẫn giải nén thành **cùng JSON bytes**, nhưng MAC gốc **không còn khớp**. Đây chính là khác biệt giữa byte identity và semantic equivalence.
3. Giữ nguyên gzip body nhưng **bỏ Content-Encoding** sẽ làm canonical encoding line khác: MAC không khớp.
4. Đổi raw request target `mode=preview` thành `mode=commit` nhưng giữ tag cũ: MAC không khớp.
5. Gửi JSON chưa nén có thể có HMAC hợp lệ **riêng** theo hợp đồng, nhưng không dùng lại chữ ký của gzip representation.
6. Chỉ Content-Encoding absent hoặc gzip được hỗ trợ; explicit `identity` hay nhiều coding bị từ chối.

**Giới hạn:** sample chưa triển khai HTTP server/filter, không chạy timestamp/nonce store và không tra key state. Nó cũng chỉ cho một tập raw targets hẹp và `Content-Type` đơn giản. Hệ thống production cần xử lý duplicate HTTP headers, body size trước buffer, HTTP framing, proxy, charset/media type parameters và authentication/authorization đầy đủ.

### 7.3. Vì sao giải nén phải có giới hạn?

Một payload gzip rất nhỏ có thể giải nén thành lượng dữ liệu lớn. Nếu application tự động decompress trước khi áp giới hạn, attacker có thể tiêu tốn RAM/CPU (**compression bomb**). Nên có nhiều lớp giới hạn:

- **Maximum encoded size** trước khi buffer hoặc tính digest.
- **Maximum decoded size** được kiểm tra theo số byte thực đọc từ decoder.
- Giới hạn **thời gian/CPU**, số content codings lồng nhau (ví dụ chỉ cho phép một), request rate và concurrency.
- Kiểm tra **CRC/trailer/gzip integrity**, dữ liệu truncated, illegal gzip member và định dạng content không hợp lệ.
- Kiểm soát **tỷ lệ nén** và dữ liệu có thể gây tải CPU lớn nếu threat model yêu cầu.
- Không cho decoded content được sử dụng trước khi MAC/anti-replay/authorization đầy đủ, trừ khi có thiết kế trust boundary cụ thể.

Trong ví dụ `decodeLimited` chặn tổng byte đầu ra và đầu vào, nhưng **không thay** timeouts, request rate limits và kiểm soát tài nguyên ở server thật.

## 8. Test matrix: algorithm, body và gateway

### 8.1. Unit tests theo content coding

| Test | Input / hành động | Expected |
|---|---|---|
| Plain JSON | Không có Content-Encoding, hash raw JSON bytes | HMAC hợp lệ nếu ký đúng |
| Gzip JSON | Content-Encoding gzip, hash gzip bytes | HMAC hợp lệ nếu ký đúng |
| Cùng JSON, khác gzip metadata | Gzip variant và giữ tag cũ | **MAC fail** |
| Gzip body, bỏ header gzip | Không đổi body, giữ tag | **MAC fail** |
| Plain body, thêm header gzip | Không đổi body, giữ tag | **MAC fail**, decoder có thể reject |
| `Content-Encoding: GZIP` | Same bytes, normalized token `gzip` | Có thể cho cùng MAC theo contract |
| Explicit `identity` | Ngoài hợp đồng | Reject |
| `gzip, br` | Multiple codings | Reject |
| Unknown coding `zstd` | Chưa được hỗ trợ trong contract | Reject |
| Header lặp `Content-Encoding` | Parser ambiguous | Reject |
| Gzip truncated/CRC sai, nhưng HMAC hợp lệ từ client có key | Không giải nén/parse thành công | Reject ở decoder sau auth |
| Raw body quá lớn | Vượt max encoded size | Reject trước khi xử lý |
| Decoded body quá lớn | Gzip bomb vượt max decoded size | Reject sau khi giới hạn |
| Ký JSON raw nhưng gửi gzip bytes | Body digest khác | MAC fail |
| Ký gzip bytes nhưng verifier hash decoded JSON | Test bất đồng hợp đồng | Không tương thích; cần sửa luồng |
| Content-Type đổi từ JSON sang kiểu khác | Giữ tag cũ | MAC fail hoặc reject media type |
| Path/query/method thay đổi | Giữ tag cũ | MAC fail hoặc reject raw target |
| Signature Base64URL malformed | Tag sai độ dài/encoding | Reject |

### 8.2. Golden fixtures cần lưu

Để tránh test xanh giả, hãy tạo bộ fixture với các trường:

~~~text
algorithm=HmacSHA256
contractVersion=hmac-content-encoding-v1
clientId=merchant-test
keyId=k1
method=POST
rawTarget=/v1/orders?mode=preview
contentType=application/json
contentEncoding=gzip
encodedBodyBase64=<base64-cua-byte-gzip-co-dinh>
expectedBodySha256Hex=<sha256-cua-encodedBodyBase64-sau-decode>
expectedCanonicalText=<10-dong-chinh-xac>
expectedMacHex=<HMAC-test-key-tren-canonical-UTF8>
~~~

Expected canonical và HMAC phải được tạo/đối chiếu bằng **implementation độc lập** hoặc vector đã kiểm tra, không chỉ gọi hai hàm sign và verify của cùng một thư viện. Gzip payload phải được lưu như **mảng byte cố định** (ví dụ Base64), không sinh gzip lại bằng toolchain khác trong mỗi lần chạy CI rồi mong digest trùng. Thêm vector RFC 4231 để xác minh `HmacSHA256` độc lập.

### 8.3. Integration tests qua proxy/gateway

Chạy các trường hợp sau qua đường production-like:

~~~text
Client -> TLS endpoint -> CDN/WAF -> gateway
       -> HTTP server -> HMAC filter -> content decoder
       -> JSON parser -> authorization -> business
~~~

Với mỗi ca, ghi nhận bằng fixture/test log **không nhạy cảm**:

1. Encoded body bytes + SHA-256 ở sender.
2. Encoding header, body bytes và body hash ở **đúng điểm HMAC verifier**.
3. Content bytes sau decode và JSON object mà handler thực sự nhìn thấy.
4. Route/target, principal, key state, timestamp/nonce và authorization decision.
5. Gateway có tự giải nén, recompress, thay Content-Length, convert HTTP/2 hoặc rewrite URI không.

Khi xảy ra mismatch, **đừng bỏ Content-Encoding khỏi chữ ký để “cho chạy được”**: trước tiên phải xác định có thành phần nào đổi bytes sau khi sender ký. Nếu cần gateway biến đổi content, hãy đặt authentication trước điểm biến đổi và thiết kế trust boundary nội bộ minh bạch.

## 9. Timestamp, nonce và key rotation độc lập với nén

Một request đã ký gzip bytes đúng vẫn có thể bị **replay** vì attacker có thể sao chép nguyên encoded body, headers và tag.

### 9.1. Pipeline receiver

~~~mermaid
flowchart TD
    A["Nhận request + encoded body"] --> B["Kiểm tra framing, limit và signed headers"]
    B --> C["Lookup secret theo clientId/keyId/audience"]
    C --> D{"Key được phép verify?"}
    D -- Không --> X["Reject"]
    D -- Có --> E["Kiểm tra timestamp trong cửa sổ"]
    E --> F["Canonical method/target/Content-Encoding/body hash"]
    F --> G{"HMAC đúng?"}
    G -- Không --> X
    G -- Có --> H["Atomic reserve nonce"]
    H --> I{"Nonce mới?"}
    I -- Không --> X
    I -- Có --> J["Giải Content-Encoding với giới hạn"]
    J --> K["Parse JSON, tạo principal và authorization"]
~~~

Điều kiện minh họa:

~~~text
nowSeconds - 300 <= signedTimestamp <= nowSeconds + 300
nonceScope = (clientId, keyId, audience, nonce)
reserve nonce atomically sau khi MAC đúng
TTL phủ toàn bộ thời gian timestamp có thể còn hợp lệ
~~~

Với cửa sổ ±300 giây, TTL khoảng 600 giây từ lần reserve có thể phù hợp theo chính sách ví dụ. Kho nonce phải **chia sẻ giữa các node** và dùng primitive atomic (ví dụ tương đương `SET key 1 NX EX 600` trong Redis). Không dùng `GET` rồi `SET`; hai request đồng thời có thể cùng vượt qua. Nếu kho nonce không sẵn sàng và chống replay bắt buộc, **fail closed**.

### 9.2. Key rotation

| Key state | Hành vi |
|---|---|
| `ACTIVE` | Có thể verify request với secret tương ứng |
| `VERIFY_ONLY` | Chỉ verify trong cửa sổ chuyển tiếp đã phê duyệt |
| `REVOKED` | Reject dù gzip body và MAC đều hợp lệ về mặt toán học |
| Key ID thuộc client/audience khác | Reject; không thử secret tenant khác |
| Key ID không tồn tại | Reject; không fallback secret mặc định |

Không chia sẻ một `Mac` có trạng thái giữa nhiều request/threads. Mỗi phép HMAC dùng `Mac.init` với secret đúng của key record; `Mac.reset()` không thay khóa. Rotation không cho phép ngầm đổi từ ký encoded body sang decoded body; đó là **thay phiên bản giao thức**, nên cần negotiation/rollout và test riêng.

## 10. Authentication và authorization sau content decoding

Giả sử merchant 17 có secret hợp lệ và ký payload gzip chứa:

~~~json
{"orderId":"order-99","action":"refund","amount":150000}
~~~

Server decompress JSON và tìm thấy `order-99` thuộc merchant 42:

~~~text
Authentication:
    principal = merchant-17
    method = POST
    target = /v1/orders?mode=preview
    contentEncoding = gzip
    signedEncodedBody = verified
    nonce = fresh

Authorization:
    action = orders:refund
    resource = order-99
    resourceOwner = merchant-42
    principal = merchant-17
    decision = DENY
~~~

MAC hợp lệ chứng minh **request đã ký không bị thay đổi theo hợp đồng**, không chứng minh merchant 17 có quyền hoàn tiền cho order 99. Business handler phải kiểm tra **principal, action, resource, owner/tenant**, cả khi body đã được giải nén và parser JSON đã chạy.

Nếu JSON chứa duplicate keys, số dạng khác nhau hoặc các kiểu dữ liệu mơ hồ, application cần chính sách parser/validation để tránh hai tầng hiểu khác nhau. Ký encoded bytes đảm bảo những bytes đó được bảo vệ, nhưng **không tự xác định một ngữ nghĩa JSON duy nhất**.

## 11. Các sai lầm phổ biến

1. **Nhầm Content-Encoding với Content-Type:** gzip là content coding, không phải media type.
2. **Nhầm Content-Encoding với Transfer-Encoding:** chunked framing không tương đương gzip representation.
3. **Dùng Accept-Encoding để suy request body encoding:** trường này liên quan lựa chọn coding cho response.
4. **Hash decoded JSON khi sender ký gzip bytes:** verifier dùng sai message.
5. **Nén lại JSON trước verify:** gzip output có thể khác byte dù nội dung tương đương.
6. **Không ký Content-Encoding:** attacker có thể thay cách server diễn giải cùng mảng body.
7. **Tự chấp nhận explicit identity:** làm lệch contract absent header nếu không quy định tương đương.
8. **Cho phép nhiều Content-Encoding rồi sort:** coding order có nghĩa, không thể sắp xếp tùy ý.
9. **Không giới hạn decompression:** dễ bị compression bomb hoặc tiêu thụ tài nguyên.
10. **Verify sau khi middleware đã decode:** raw encoded bytes có thể đã mất.
11. **Chỉ test trực tiếp app:** không phát hiện gateway tự giải nén/recompress hoặc chuyển HTTP framing.
12. **Tưởng HMAC chống replay:** cần timestamp/nonce và atomic store.
13. **Tưởng MAC hợp lệ cho phép mọi hành động:** cần authorization theo tài nguyên sau decode.

## 12. Bài tập thực hành

**Bài 1 — Năm khái niệm:** Một POST có `Content-Type: application/json`, `Content-Encoding: gzip`, `Accept-Encoding: br` và `Transfer-Encoding: chunked` trong HTTP/1.1. Hãy giải thích vai trò từng trường và xác định byte nào được đưa vào SHA-256 theo `hmac-content-encoding-v1`.

**Bài 2 — Gzip variant:** Cùng JSON được nén thành hai gzip streams hợp lệ có metadata khác nhau. Khi signer hash encoded bytes, hai chữ ký có phải bằng nhau không? Nếu muốn coi chúng tương đương phải thay hợp đồng thế nào?

**Bài 3 — Identity vs gzip:** So sánh request không có Content-Encoding với request `Content-Encoding: identity` và `Content-Encoding: gzip`. Trường hợp nào được contract bài học chấp nhận?

**Bài 4 — Gateway decompress:** Client ký gzip body, gateway tự giải nén thành JSON rồi bỏ header gzip trước backend. Tại sao backend HMAC fail? Hãy thiết kế vị trí xác minh phù hợp.

**Bài 5 — Content-Length:** Encoded gzip body dài 140 byte, giải nén ra 300 byte. Trong HTTP/1.1 với Content-Length, trường này mô tả độ dài nào? Vì sao không lấy nó làm decoded size limit?

**Bài 6 — Compression bomb:** Attacker có key hợp lệ và gửi một gzip body nhỏ giải nén thành dữ liệu lớn. Chặn ở bước nào, đặt những giới hạn nào và vì sao giới hạn encoded size là chưa đủ?

**Bài 7 — Replay:** Request gzip có MAC đúng được gửi lại với cùng nonce và timestamp. Điều gì phải xảy ra? Vì sao gzip/Content-Encoding không liên quan đến tính mới?

**Bài 8 — Authorization:** Merchant A có chữ ký HMAC hợp lệ cho compressed JSON yêu cầu hoàn tiền tài nguyên của merchant B. Sau khi giải nén, tầng nào cần từ chối và dựa trên dữ liệu gì?

## 13. Kết luận

**Content encoding là một yếu tố thuộc biểu diễn byte của HTTP request content**, vì vậy nó phải được thiết kế cùng **body canonicalization** và chữ ký HMAC. Quy tắc quan trọng nhất là chọn rõ **ký encoded bytes hay decoded bytes**, đưa `Content-Encoding` vào hợp đồng và kiểm thử mọi tầng có thể thay đổi representation. Hợp đồng ví dụ ký **gzip bytes trước khi giải nén**, xác minh cả encoding field và body digest, rồi mới decode có giới hạn. Bảo vệ hoàn chỉnh còn cần quản lý key rotation, timestamp/nonce chống replay, kiểm thử proxy/gateway và **authorization độc lập theo tài nguyên thực**.

**Tài liệu tham khảo:**

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): content codings, `Content-Encoding`, `Content-Type` và `Content-Length`.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): message framing và `Transfer-Encoding`.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): HTTP/2 message semantics và DATA frames.
- [RFC 1952 — GZIP File Format Specification](https://www.rfc-editor.org/rfc/rfc1952): gzip header, MTIME, compressed data và trailer.
- [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104): keyed-hash message authentication.
- [RFC 4231 — Test Vectors for HMAC-SHA-256](https://www.rfc-editor.org/rfc/rfc4231): kiểm chứng HMAC bằng vector độc lập.
- [RFC 9530 — Digest Fields](https://www.rfc-editor.org/rfc/rfc9530): content/representation digest fields, khác với keyed MAC.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): tham khảo chuẩn ký HTTP components; `hmac-content-encoding-v1` trong bài chỉ là **hợp đồng học tập**, không mặc nhiên tuân thủ RFC 9421.
- [Java SE 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): API HMAC chuẩn của JCA.
- [Java SE 17 — GZIPInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html): giải gzip stream; ứng dụng phải tự áp giới hạn đầu ra.
