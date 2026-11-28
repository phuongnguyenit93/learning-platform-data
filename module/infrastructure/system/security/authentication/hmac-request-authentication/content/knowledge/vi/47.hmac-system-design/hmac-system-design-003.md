# Chọn canonical format cho xác thực HTTP request bằng HMAC

## 1. Bài toán thiết kế: ký đúng những byte mà server tin cậy

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client tạo **HMAC** bằng shared secret trên một **canonical request**; server tái tạo đúng chuỗi byte đó và xác minh chữ ký. Hợp đồng ký cần xác định phương thức HTTP, URI/path/query, header hoặc body theo phạm vi bảo vệ, đồng thời ràng buộc timestamp/nonce để chống replay, định danh key để phục vụ rotation và principal để tiếp tục phân quyền.

Ở góc nhìn **Thiết kế HMAC system**, chọn canonical format không chỉ là chọn cách nối vài chuỗi. Đây là lựa chọn **ngữ nghĩa mà chữ ký xác thực**: hai cách viết HTTP nào được xem là cùng một request? Những phần nào bắt buộc có cùng byte? Lớp gateway có được phép rewrite không? Khi HMAC hợp lệ, controller có chắc đang xử lý chính dữ liệu vừa được xác minh không?

Giả sử client gửi:

~~~http
POST /v1/orders?item=book&quantity=1 HTTP/1.1
Content-Type: application/json
X-HMAC-Key-Id: client-a-k1
X-HMAC-Timestamp: 1795834800
X-HMAC-Nonce: 54e74014b5f248d0

{"deliveryAddress":"A","amount":100000}
~~~

Nếu client ký `/v1/orders?item=book&quantity=1` nhưng gateway đổi thứ tự query; hoặc verifier ký body bytes trước transform còn handler đọc body sau transform, sẽ có **signature mismatch** hoặc tệ hơn là **mismatch giữa dữ liệu được ký và dữ liệu thực thi**. Nếu hợp đồng bỏ body, attacker có khả năng sửa payload ở một trust boundary có thể thay `amount` mà vẫn giữ HMAC hợp lệ. Nếu hợp đồng ký một biểu diễn query nhưng framework cho handler lấy giá trị cuối của duplicate parameter, verifier và nghiệp vụ có thể hiểu khác nhau dù HMAC đúng.

Mục tiêu bài học:

- Chọn giữa định dạng ký **raw request-target**, **normalized URI/query** và **structured parameters** theo ràng buộc hệ thống.
- Viết hợp đồng byte-level cho version, algorithm, keyId, method, path, query, signed headers, timestamp, nonce và body digest.
- Phân biệt **biểu diễn wire**, **canonical bytes** và **ý nghĩa nghiệp vụ**; kiểm soát sự nhập nhằng giữa các lớp.
- Thiết kế quy trình signer/verifier qua proxy/gateway, có algorithm allowlist, credential binding, freshness và anti-replay.
- Cài đặt serializer Java 17 nhất quán, tạo test vector và kiểm thử HMAC độc lập.
- Lập kế hoạch migration/rotation, observability và authorization sau xác thực.

> **Quy ước:** Bài sử dụng một *hợp đồng minh họa* tên `hmac-v1`. Nó **không** tuyên bố có một canonical format mặc định áp dụng cho mọi API. Mỗi tổ chức phải thống nhất contract, cấu hình tầng HTTP/proxy và khả năng tương thích của client trước khi phát hành.

## 2. Threat model: sự khác biệt biểu diễn dẫn tới điều gì?

HMAC bảo vệ byte trong thông điệp đã ký với giả định shared secret còn an toàn. Nhưng sự an toàn của toàn API còn phụ thuộc vào việc các lớp hiểu những byte đó thống nhất.

| Điểm sai khác | Ví dụ | Hậu quả có thể xảy ra |
|---|---|---|
| Method | `get` / `GET`, method override header | Client/verifier ký một method nhưng handler thực thi method khác |
| Path | `/a/../admin`, `%2F`, double slash | Router, proxy và verifier chọn route khác nhau |
| Query order | `a=1&b=2` / `b=2&a=1` | False reject nếu policy cho phép hoán vị nhưng các bên không thống nhất |
| Query duplicates | `role=user&role=admin` | Một lớp chọn giá trị đầu, lớp khác chọn giá trị cuối |
| Percent encoding | `%2f`, `%2F`, `%252F` | Sai số lần decode hoặc chuẩn hóa escape |
| Plus/space | `q=a+b`, `q=a%20b` | Form decoding làm `+` thành space ngoài ý muốn |
| UTF-8/Unicode | `%C3%A9` vs `e%CC%81` | Biểu diễn byte hoặc code point khác nhau |
| Header names/values | `Content-Type`/`content-type`, whitespace, multi-value | Client và server ký khác; attacker lợi dụng header ambiguity |
| Authority/Host | Gateway thay `Host`, tenant route phụ thuộc hostname | Ký URI path nhưng nghiệp vụ chọn tenant theo host chưa ký |
| Body | JSON serialize lại, gzip decompression, chunked transport | Hash khác hoặc business dùng body khác dữ liệu được xác minh |
| Signature metadata | keyId/algorithm/version không được ràng buộc | Đường xử lý có thể bị chọn nhầm hoặc downgrade |
| Time and replay | Epoch milliseconds vs seconds; nonce store theo từng pod | Request bị reject sai hoặc replay qua instance khác |

**Mục tiêu an ninh:** Với mọi request được chấp nhận, dữ liệu mà verifier cho rằng đã xác thực phải có **một cách diễn giải duy nhất** và phù hợp với dữ liệu handler sử dụng. Trường hợp request không đáp ứng hợp đồng thì **từ chối**, không âm thầm thử nhiều cách canonicalization đến khi có một chữ ký khớp.

### 2.1. Ba kiểu thất bại cần phân biệt

1. **False reject (tính tương thích):** client và verifier có cùng ý định nhưng tạo canonical bytes khác nhau. Ví dụ một phía sort query, phía kia giữ thứ tự.
2. **Signing confusion (tính toàn vẹn):** HMAC hợp lệ theo verifier nhưng request được handler hiểu khác dữ liệu đã ký. Ví dụ duplicate query key bị chọn first-wins ở verifier và last-wins ở controller.
3. **Credential compromise (mất quyền kiểm soát secret):** attacker có shared secret hoặc quyền dùng signer và có thể tạo HMAC đúng cho request tùy ý. Canonicalization không tự xử lý được việc này; phải thu hồi key/client và khôi phục môi trường.

Timestamp và nonce chống **replay các request đã ký**, nhưng không giải quyết hai vấn đề đầu và không cứu được secret đã lộ.

## 3. Chọn chiến lược: raw target, normalized target hay semantic object?

| Chiến lược | Cách ký | Ưu điểm | Rủi ro/điều kiện |
|---|---|---|---|
| **Raw request-target** | Ký byte URI/path/query nhìn thấy ở ingress | Dễ đối chiếu byte, phân biệt mọi cách viết | Proxy có thể rewrite; không tự loại bỏ mismatch với cách parser nghiệp vụ hiểu query |
| **Normalized path + query** | Canonical hóa URI bằng quy tắc công khai rồi ký | Nhiều dạng wire tương đương có chung signature; hỗ trợ đa client | Phải định nghĩa từng quy tắc, kiểm thử gateway/router/controller; mất an toàn nếu chuẩn hóa không đồng nhất |
| **Structured parameters** | Parse thành trường kiểu dữ liệu rồi serialize canonical | Hợp với API có schema được kiểm soát, có thể giảm ngữ nghĩa mơ hồ | Parsing, duplicate fields, JSON number/Unicode và schema evolution rất phức tạp |
| **Raw body digest + canonical metadata** | Hash exact body bytes, ký digest và các trường khác | Phổ biến, không phụ thuộc serializer JSON của client | Mọi phía phải thống nhất body representation tại điểm ký/verify, kiểm soát streaming |

Không có một lựa chọn đúng tuyệt đối. Nếu hệ thống chỉ có một client và một gateway bảo toàn raw request-target, ký raw có thể đơn giản. Nếu API có nhiều client ngôn ngữ khác nhau và cần chấp nhận thay đổi thứ tự query, canonical query theo hợp đồng rõ ràng có thể phù hợp hơn. Nếu payload JSON rất lớn hoặc multipart, cần cân nhắc hash stream và chính sách biến đổi.

**Lựa chọn cho bài:** Dùng **canonical path chặt**, **canonical query được parse/encode một lần**, **body digest trên exact bytes** và **danh sách trường ký cố định theo phiên bản**. Đây là lựa chọn có tính minh họa; nó **cố tình từ chối** nhiều URL hợp lệ theo HTTP để giảm số trường hợp nhập nhằng trong API nội bộ nhỏ.

### 3.1. Bất biến chọn thiết kế

- **Deterministic:** cùng request input hợp lệ và contract version tạo chính xác cùng byte.
- **Unambiguous:** không có cách giải thích thứ hai làm handler dùng giá trị khác với verifier.
- **Fail closed:** dữ liệu không hỗ trợ, duplicate hoặc sai encoding bị từ chối; không đoán rồi sửa.
- **Bounded:** có giới hạn độ dài và thời gian xử lý; không dùng parser không giới hạn với input attacker.
- **Versioned:** thay logic canonicalization cần version mới, test vectors mới và migration chính thức.
- **Domain-separated:** HMAC cho HTTP request có prefix rõ, tránh dùng cùng message format với loại token hoặc lệnh khác.
- **Bound to credential:** version/algorithm/keyId và chính sách server được kiểm tra và ràng buộc trong dữ liệu ký.

## 4. Hợp đồng `hmac-v1` đề xuất cho ví dụ

### 4.1. Biểu diễn canonical bytes

Đặt `C(request)` là chuỗi 11 dòng dưới đây, nối bằng **một byte LF (0x0A)** giữa các dòng, **không có LF cuối**. Sau cùng, encode toàn chuỗi bằng UTF-8 và tính HMAC trên byte array:

~~~text
HMAC-HTTP-REQUEST
hmac-v1
HMAC-SHA256
<keyId>
<METHOD>
<CANONICAL_PATH>
<CANONICAL_QUERY>
<CONTENT_TYPE>
<TIMESTAMP_SECONDS>
<NONCE>
<BODY_SHA256_LOWER_HEX>
~~~

**Lưu ý:** Có **11 dòng**: dòng 1 là domain separator, dòng 11 là body digest. Dòng query vẫn tồn tại và bằng chuỗi rỗng nếu không có query; trong trường hợp đó chuỗi ký có **hai ký tự LF liên tiếp** ở vị trí giữa canonical path và content type. Không được bỏ dòng rỗng hoặc dùng `trim()` cho cả chuỗi.

Công thức:

\[
\mathrm{bodyDigest} = \mathrm{SHA256}(\mathrm{exactBodyBytes})
\]

\[
\mathrm{signature} = \mathrm{HMAC\mbox{-}SHA256}
\bigl(\mathrm{sharedSecret},\ \mathrm{UTF8}(C(request))\bigr)
\]

Signature truyền qua header được encode thành **64 ký tự lowercase hex**, vì HMAC-SHA256 trả tag 32 byte đầy đủ. Server tính digest từ **body bytes thực nhận**, không tin chỉ vào một header hash do client gửi.

### 4.2. Quy tắc chi tiết từng trường

| Trường | Policy của ví dụ | Cách xử lý không hợp lệ |
|---|---|---|
| Domain | Literal `HMAC-HTTP-REQUEST` | Không được caller thay |
| Version | Literal `hmac-v1`; giao thức phải bind version | Reject version lạ |
| Algorithm | Literal `HMAC-SHA256`, tra từ allowlist server/per-key | Reject unknown hoặc mismatch |
| KeyId | `[A-Za-z0-9_-]{1,64}`; lookup credential active | Reject sai cú pháp/trạng thái |
| Method | Chỉ một trong `GET`, `POST`, `PUT`, `PATCH`, `DELETE` | Reject method lạ hoặc method override |
| Path | `/` hoặc các segment ASCII `[A-Za-z0-9._~-]+`, phân tách bằng `/`; không `.`, `..`, percent escapes, double slash hoặc trailing slash | Reject và không normalize ngầm |
| Query | Không query = dòng rỗng; nếu có, cặp `key=value` cách nhau bằng `&`, key duy nhất sau percent decode | Reject bare key, empty key/segment, duplicate |
| Content-Type | Literal `application/json` cho endpoint mẫu, không nhận suffix/tham số | Reject không đúng contract |
| Timestamp | Unix epoch **giây**, chuỗi số thập phân không dấu, không leading zero (trừ `0`) | Reject malformed và out-of-window |
| Nonce | `[A-Za-z0-9_-]{16,128}`, entropy đủ cao và unique per credential | Reject sai cú pháp hoặc replay |
| Body digest | SHA-256 của exact body bytes, lowercase hex 64 ký tự | Không được client tự quyết định digest |

**Path policy mang tính hạn chế có chủ đích.** API thực có Unicode path, matrix parameters, URL-encoded slash hoặc URL template khác cần một **hợp đồng path riêng**; không copy chính sách này rồi chấp nhận thêm dạng chưa được test.

**Content-Type** là ví dụ một signed metadata field. Ở API có hỗ trợ `application/json; charset=utf-8` hoặc multipart, phải định nghĩa cách parse và canonical hóa media type rõ ràng. Không đổi header value tùy ý trước khi ký và không để handler chọn parser khác từ giá trị chưa được bảo vệ.

### 4.3. Hợp đồng canonical query

Quy tắc dành cho `rawQuery` lấy tại HTTP ingress **trước khi framework diễn giải parameter map**:

1. `null` hoặc chuỗi rỗng tương đương **không có query**, tạo dòng canonical query rỗng.
2. Raw query chỉ được chứa ASCII **unreserved** (`A–Z a–z 0–9 - . _ ~`), dấu `+`, dấu `%` của escape, dấu `&` phân cặp và dấu `=` phân khóa/giá trị. Ký tự non-ASCII thô, dấu cách, dấu `;`, dấu `#` hoặc `?` trong raw query đều bị từ chối.
3. Mỗi cặp bắt buộc có **một khóa không rỗng và dấu `=`**; `x=` hợp lệ, `x` không hợp lệ. Dấu `=` bổ sung trong giá trị phải được percent-encode, không được giữ raw.
4. Decode chuỗi `%HH` **đúng một lần** thành bytes rồi decode bytes bằng UTF-8 **strict**. Reject percent escape sai và UTF-8 malformed. `+` luôn biểu thị **dấu cộng**, không phải dấu cách; dấu cách phải là `%20`.
5. Khóa sau decode phải thuộc `[A-Za-z0-9_.~-]+`, không dài quá 128 byte; giá trị không quá 1.024 byte UTF-8, có thể là Unicode hợp lệ, không chứa ASCII control bytes.
6. Reject khóa trùng **sau decode**, kể cả `a=1&%61=2`. Chính sách này không hỗ trợ array dưới dạng repeated keys; muốn hỗ trợ cần version/schema khác và policy handler thống nhất.
7. Encode lại key/value theo RFC 3986 unreserved: giữ các byte unreserved, những byte còn lại encode `%HH` **uppercase**. Ví dụ `%7e` thành `~`, `%2f` thành `%2F`, dấu `+` thành `%2B`, ký tự khoảng trắng thành `%20`.
8. Sort các cặp theo **canonical encoded key** (ASCII byte order), nối bằng `&`. Vì key unique, không có câu hỏi giữ thứ tự các giá trị trùng.
9. Giới hạn raw query 4.096 ký tự, tối đa 64 cặp, canonical output tối đa 4.096 ký tự; adapter còn cần giới hạn path, headers và body.

| Raw query | Canonical query hoặc kết quả |
|---|---|
| `b=2&a=1` | `a=1&b=2` |
| `a=%7e&b=%2f` | `a=~&b=%2F` |
| `q=hello+world` | `q=hello%2Bworld` |
| `q=hello%20world` | `q=hello%20world` |
| `x=%252F` | `x=%252F`, không decode hai lần |
| `x=%2F` | `x=%2F`, **khác** `%252F` |
| `n=%C3%A9` | `n=%C3%A9`, UTF-8 hợp lệ |
| `a=1&%61=2` | **REJECT** duplicate sau decode |
| `a=1&a=2` | **REJECT** duplicate key |
| `x`, `=a`, `x=1&` | **REJECT** cú pháp nhập nhằng |
| `x=%G0`, `x=%C0%AF` | **REJECT** percent/UTF-8 lỗi |
| `q=a b`, `q=é`, `a=1;b=2` | **REJECT** raw character ngoài hợp đồng |

**Không tự chuẩn hóa Unicode NFC/NFD.** Hai chuỗi có các code point khác nhau có thể được handler coi tương đương theo nghiệp vụ nhưng vẫn có canonical bytes khác. Nếu ứng dụng cần Unicode normalization, phải định nghĩa thuật toán và phiên bản, tránh để database hoặc framework tự biến đổi ngoài hợp đồng.

### 4.4. Body: exact bytes, không ký DTO đã serialize lại

Body digest của **mảng byte rỗng** phải luôn là:

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Không được thay body rỗng bằng "bỏ trường hash". Với JSON, không nên deserialize rồi serialize lại để tính hash: thứ tự property, whitespace, number representation, escaping và Unicode có thể thay byte. Nếu muốn ký một canonical JSON object, cần đặc tả canonical JSON chính thức có quy định về duplicate keys, number/string serialization và kiểm thử độc lập.

Chọn **điểm tính hash**: sau những transformation nào, trước những transformation nào? Với gateway decompress gzip hoặc reserialize JSON, signer/verifier có thể hash byte khác nhau dù hai phía đều dùng SHA-256 đúng. Hợp đồng v1 trong bài giả định **body bytes được chuyển nguyên vẹn từ client signer tới verifier**, và handler đọc từ chính dữ liệu đã xác minh.

Giới hạn body tại adapter ở mức **1 MiB** trong ví dụ. File upload lớn cần stream hashing/chunk signing được thiết kế riêng; không buffer toàn bộ payload không giới hạn chỉ để xác thực.

### 4.5. Signed headers và authority

Ở ví dụ, `Content-Type` được đưa vào canonical bytes và các trường HMAC metadata xuất hiện tường minh. Nhưng các API khác có thể cần ký `Host`/authority, route namespace, tenant ID, content encoding hoặc header quyết định nghiệp vụ. **Phải ký mọi thông tin mà việc thay đổi có thể đổi danh tính endpoint hoặc ý nghĩa request.** Nếu routing/tenant phụ thuộc `Host` và host không nằm trong chữ ký hay một ràng buộc tin cậy tương đương, có thể phát sinh lỗ hổng.

Header names của HTTP là case-insensitive, còn chính sách value do hợp đồng quyết định. Hệ thống cần kiểm tra duplicate headers, coalescing, whitespace và header được thêm bởi proxy **trước khi** tạo canonical bytes. Không được lấy ngẫu nhiên header đầu hoặc cuối nếu nhiều giá trị và không được ký `X-Forwarded-*` do caller tự khai mà không có trust-boundary policy.

## 5. Luồng signer/verifier và ranh giới gateway

~~~mermaid
sequenceDiagram
    participant C as Client signer
    participant G as Gateway / Proxy
    participant V as HMAC verifier
    participant K as Credential store
    participant N as Shared nonce store
    participant H as Handler + authorization

    C->>C: Canonical fields → UTF-8 bytes
    C->>C: HMAC-SHA256(shared secret, canonical bytes)
    C->>G: HTTP request + signature
    G->>V: Forward đúng contract v1
    V->>V: Reject mơ hồ / parse / limits
    V->>K: keyId → secret + algorithm + client policy
    K-->>V: Active credential
    V->>V: Canonical bytes + full HMAC compare
    V->>V: Timestamp trong cửa sổ
    V->>N: Claim nonce atomic sau HMAC hợp lệ
    N-->>V: New hoặc replay
    alt Verify failed
        V-->>C: Authentication reject
    else Verify passed
        V->>H: Principal + verified request bytes
        H->>H: Authorization(resource, principal)
        H-->>C: Business response
    end
~~~

Verifier phải kiểm tra `version`, algorithm allowlist, trạng thái credential và mối liên hệ giữa `keyId` với principal **bằng policy server-side**. Không để header client tự chọn thuật toán JCA tùy ý. Signature phải được decode đúng độ dài, so sánh **byte** bằng cơ chế chống timing leak phù hợp như `MessageDigest.isEqual` trên tag đã có cùng độ dài.

Timestamp Unix giây có thể kiểm tra theo chính sách, ví dụ `now - 300s <= ts <= now + 60s`; nonce chỉ được **claim atomic** sau khi request thỏa điều kiện chữ ký/freshness. Với nhiều instance, nonce store phải dùng chung một miền uniqueness; nếu không sẵn sàng, **fail closed** thay vì vô hiệu anti-replay.

Việc verified HMAC chỉ tạo **authenticated principal**. Handler vẫn cần `authorization` dựa trên tenant/resource, hạn mức và hành động, kể cả khi client có chữ ký đúng. Với request được ký bằng secret của client đã bị lộ, HMAC không thể phân biệt attacker và client thật; phải thu hồi key và điều tra.

### 5.1. Những quyết định cần chốt với gateway

- **Ingress source:** verifier đọc raw path/query từ nơi nào? Servlet container và HTTP/2 proxy có thể đã decode/normalize trước khi ứng dụng nhận dữ liệu; nếu không lấy được input đúng contract, từ chối hoặc chuyển điểm verify.
- **No unauthorized rewrite:** không âm thầm đổi `%2F`, `+`, duplicate query, `Host`, `Content-Type` hoặc body đã ký. Nếu buộc rewrite, ký/verify tại vị trí phù hợp hoặc đặt version/contract khác.
- **HTTP/1.1 và HTTP/2:** request-target, `:path` và authority có thể được biểu diễn khác; dùng **cùng định nghĩa trường canonical** chứ không dựa vào chuỗi HTTP start-line không còn tồn tại ở HTTP/2.
- **Routing consistency:** verifier và controller phải dùng cùng một ý nghĩa của path/query đã xác minh. Không cho một parser bỏ duplicate trong khi parser khác chọn giá trị cuối.
- **Header control:** từ chối duplicate signed headers và header có CR/LF/multiple values ngoài hợp đồng; test gateway có thể gộp headers.
- **Observability:** ghi request ID, version policy và mã lỗi nội bộ; không log shared secret, full signature, canonical bytes chứa PII hoặc body nhạy cảm.


## 6. Java 17: xây canonical bytes bằng một serializer có kiểm soát

Code dưới đây hiện thực **hợp đồng ví dụ** trong mục 4. Nó cố tình chỉ hỗ trợ path ASCII chặt, query unique keys, body tối đa 1 MiB và `Content-Type: application/json`. Đó là **thiết kế thu hẹp input để giảm nhập nhằng**, không phải parser URL tổng quát.

**`CanonicalRequestV1.java`**

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.StringJoiner;
import java.util.TreeMap;

public final class CanonicalRequestV1 {
    private CanonicalRequestV1() {}

    public static final int MAX_BODY_BYTES = 1_048_576;
    public static final int MAX_QUERY_CHARS = 4_096;
    public static final int MAX_PAIRS = 64;
    private static final String HEX = "0123456789ABCDEF";
    private static final Set<String> METHODS =
            Set.of("GET", "POST", "PUT", "PATCH", "DELETE");

    public record Input(
            String keyId,
            String method,
            String path,
            String rawQuery,
            String contentType,
            String timestampSeconds,
            String nonce,
            byte[] body) {

        public Input {
            body = Objects.requireNonNull(body, "body").clone();
        }

        @Override
        public byte[] body() {
            return body.clone();
        }
    }

    public static byte[] canonicalBytes(Input input) {
        Objects.requireNonNull(input, "input");
        checkToken(input.keyId(), "[A-Za-z0-9_-]{1,64}", "keyId");
        checkToken(input.nonce(), "[A-Za-z0-9_-]{16,128}", "nonce");

        if (input.method() == null || !METHODS.contains(input.method())) {
            throw new IllegalArgumentException("unsupported_method");
        }
        validatePath(input.path());

        // Policy ví dụ: không tự trim, lowercase hoặc thêm charset.
        if (!"application/json".equals(input.contentType())) {
            throw new IllegalArgumentException("unsupported_content_type");
        }

        String ts = input.timestampSeconds();
        if (ts == null || !ts.matches("0|[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException("invalid_timestamp");
        }
        try {
            Long.parseLong(ts); // Cú pháp/range; freshness kiểm ở verifier.
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("invalid_timestamp", ex);
        }

        byte[] body = input.body();
        if (body.length > MAX_BODY_BYTES) {
            throw new IllegalArgumentException("body_too_large");
        }

        String query = canonicalQuery(input.rawQuery());
        String bodyHash = sha256Hex(body);

        String canonical = String.join("\n",
                "HMAC-HTTP-REQUEST",
                "hmac-v1",
                "HMAC-SHA256",
                input.keyId(),
                input.method(),
                input.path(),
                query,                       // Dòng rỗng vẫn được giữ.
                input.contentType(),
                ts,
                input.nonce(),
                bodyHash);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static void checkToken(
            String value, String pattern, String name) {
        if (value == null || !value.matches(pattern)) {
            throw new IllegalArgumentException("invalid_" + name);
        }
    }

    private static void validatePath(String path) {
        if (path == null || path.length() > 1_024
                || !path.matches(
                    "/(?:[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*)?")) {
            throw new IllegalArgumentException("invalid_path");
        }
        for (String segment : path.split("/", -1)) {
            if (".".equals(segment) || "..".equals(segment)) {
                throw new IllegalArgumentException("dot_segment");
            }
        }
        // Raw percent-encoded path, double slash và trailing slash
        // bị regex từ chối theo policy v1.
    }

    public static String canonicalQuery(String rawQuery) {
        if (rawQuery == null || rawQuery.isEmpty()) {
            return "";
        }
        if (rawQuery.length() > MAX_QUERY_CHARS) {
            throw new IllegalArgumentException("query_too_long");
        }

        String[] parts = rawQuery.split("&", -1);
        if (parts.length > MAX_PAIRS) {
            throw new IllegalArgumentException("too_many_pairs");
        }

        Set<String> seenDecodedKeys = new HashSet<>();
        // Sort theo encoded key; tên khóa ASCII unreserved nên ổn định.
        Map<String, String> encodedPairs = new TreeMap<>();

        for (String part : parts) {
            int delimiter = part.indexOf('=');
            if (delimiter <= 0) {
                throw new IllegalArgumentException("invalid_query_pair");
            }

            String key = decodeComponent(
                    part.substring(0, delimiter), 128);
            String value = decodeComponent(
                    part.substring(delimiter + 1), 1_024);

            if (!key.matches("[A-Za-z0-9_.~-]+")) {
                throw new IllegalArgumentException("invalid_query_key");
            }
            if (!seenDecodedKeys.add(key)) {
                throw new IllegalArgumentException("duplicate_query_key");
            }
            encodedPairs.put(encodeComponent(key), encodeComponent(value));
        }

        StringJoiner joiner = new StringJoiner("&");
        for (var entry : encodedPairs.entrySet()) {
            joiner.add(entry.getKey() + "=" + entry.getValue());
        }
        String canonicalQuery = joiner.toString();
        if (canonicalQuery.length() > MAX_QUERY_CHARS) {
            throw new IllegalArgumentException("canonical_query_too_long");
        }
        return canonicalQuery;
    }

    private static String decodeComponent(String raw, int maxBytes) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();

        for (int i = 0; i < raw.length();) {
            char c = raw.charAt(i);
            if (c == '%') {
                if (i + 2 >= raw.length()) {
                    throw new IllegalArgumentException("invalid_escape");
                }
                int hi = hex(raw.charAt(i + 1));
                int lo = hex(raw.charAt(i + 2));
                if (hi < 0 || lo < 0) {
                    throw new IllegalArgumentException("invalid_escape");
                }
                out.write((hi << 4) | lo);
                i += 3;
            } else if (c < 128 && (unreserved(c) || c == '+')) {
                // '+' là literal plus; không đổi thành space.
                out.write(c);
                i++;
            } else {
                throw new IllegalArgumentException("raw_character_not_allowed");
            }
            if (out.size() > maxBytes) {
                throw new IllegalArgumentException("component_too_long");
            }
        }

        byte[] bytes = out.toByteArray();
        for (byte b : bytes) {
            int value = b & 0xFF;
            if (value < 0x20 || value == 0x7F) {
                throw new IllegalArgumentException("control_character");
            }
        }

        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException("invalid_utf8", ex);
        }
    }

    private static String encodeComponent(String decoded) {
        StringBuilder out = new StringBuilder();
        for (byte b : decoded.getBytes(StandardCharsets.UTF_8)) {
            int value = b & 0xFF;
            if (unreserved(value)) {
                out.append((char) value);
            } else {
                out.append('%')
                        .append(HEX.charAt(value >>> 4))
                        .append(HEX.charAt(value & 0x0F));
            }
        }
        return out.toString();
    }

    private static boolean unreserved(int c) {
        return (c >= 'A' && c <= 'Z')
                || (c >= 'a' && c <= 'z')
                || (c >= '0' && c <= '9')
                || c == '-' || c == '.' || c == '_' || c == '~';
    }

    private static int hex(char c) {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    }

    private static String sha256Hex(byte[] body) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(body);
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

### 6.1. Vì sao serializer phải chặt?

- **Tự tạo canonical bytes**, không ghép một `Map<String,String>` mà framework đã parse khác contract. Query raw được kiểm tra trước khi normalize.
- **Bắt buộc tính body digest**, kể cả body rỗng. Server phải băm bytes mà handler sẽ xử lý; không chỉ so `X-Body-SHA256` do client tự khai.
- **Không dùng `URLDecoder`** cho URI query trong ví dụ, vì URL form decoding có thể đổi `+` thành space; trong hợp đồng này, `+` là dấu cộng literal.
- **Từ chối duplicate sau decode**. Hai raw keys `a` và `%61` cùng biểu thị `a`, nên nếu chỉ kiểm tra duplicate trước decode sẽ tạo lỗ hổng.
- **Không tự chuyển Unicode về NFC/NFD**. Nếu nghiệp vụ yêu cầu Unicode normalization, đó là một quyết định giao thức mới.
- **Dữ liệu nhiều dòng được kiểm soát**: các trường keyId/nonce/method/path/contentType/timestamp phải hợp lệ; query được percent-encode để CR/LF không đi vào chuỗi ký. Không để caller chèn LF vào một dòng rồi tạo canonical format nhập nhằng.
- **Bộ đệm body được copy** để hạn chế thay đổi mảng byte sau khi ký/verify. Tuy nhiên adapter và handler vẫn phải dùng đúng dữ liệu đã xác minh, không đọc từ một stream khác có khả năng thay đổi.

**Giới hạn cố ý:** Code là canonicalizer, **không phải toàn bộ HMAC verifier**. Nó không đọc raw HTTP start-line, không kiểm tra duplicate headers ở gateway, không tra keyId trong credential store, không thực hiện MAC, replay protection hay authorization. Các bước đó thuộc authentication pipeline và phải được kiểm thử tích hợp.

### 6.2. Gắn serializer vào HMAC verifier

Signer/verifier phải dùng output byte của serializer **không qua chỉnh sửa sau đó**:

~~~java
// Minh họa lõi verify (giả sử HTTP adapter và policy đã validate).
byte[] canonical = CanonicalRequestV1.canonicalBytes(input);

Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(secretForVerifiedKeyId, "HmacSHA256"));
byte[] expected = mac.doFinal(canonical);

if (suppliedSignatureBytes.length != 32
        || !MessageDigest.isEqual(expected, suppliedSignatureBytes)) {
    throw new AuthenticationException("invalid_hmac");
}
~~~

`secretForVerifiedKeyId` phải được lấy từ **credential active** sau khi xác nhận `keyId`, client/principal, version và algorithm policy. Không lấy secret từ request, không dùng một secret chung cho tất cả client và không fallback sang key khác khi tag sai.

Đoạn `AuthenticationException` chỉ là **pseudocode cho exception ứng dụng**; tên class do project định nghĩa. Kết quả từ chối công khai nên theo hợp đồng API; mã lỗi chi tiết dành cho audit/monitoring nội bộ. Kiểm tra timestamp và claim nonce atomic theo policy trước khi tạo authenticated principal, rồi thực hiện authorization ở lớp kế tiếp.

## 7. JUnit 5: bộ golden và metamorphic tests

Golden test vector nên có **canonical bytes mong đợi tính độc lập**, không chỉ gọi cùng hàm canonicalizer ở cả signer và verifier rồi kết luận chúng giống nhau. Những bài kiểm tra sau chứng minh phần serializer tạo byte ổn định cho các trường hợp được hợp đồng định nghĩa.

**`CanonicalRequestV1Test.java`**

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Random;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.junit.jupiter.api.Test;

class CanonicalRequestV1Test {
    private static final byte[] TEST_KEY =
            "educational-only-key-not-for-production"
                    .getBytes(StandardCharsets.UTF_8);

    private static CanonicalRequestV1.Input input(
            String query, String body) {
        return new CanonicalRequestV1.Input(
                "client-a-k1",
                "POST",
                "/v1/orders",
                query,
                "application/json",
                "1795834800",
                "nonce-test-000001",
                body.getBytes(StandardCharsets.UTF_8));
    }

    private static byte[] hmac(byte[] canonical) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(TEST_KEY, "HmacSHA256"));
        return mac.doFinal(canonical);
    }

    @Test
    void canonicalLinesHaveFixedOrderAndNoTrailingLf() {
        var bytes = CanonicalRequestV1.canonicalBytes(
                input("b=2&a=1", ""));
        String canonical = new String(bytes, StandardCharsets.UTF_8);
        String[] lines = canonical.split("\n", -1);

        assertEquals(11, lines.length);
        assertEquals("HMAC-HTTP-REQUEST", lines[0]);
        assertEquals("hmac-v1", lines[1]);
        assertEquals("HMAC-SHA256", lines[2]);
        assertEquals("client-a-k1", lines[3]);
        assertEquals("POST", lines[4]);
        assertEquals("/v1/orders", lines[5]);
        assertEquals("a=1&b=2", lines[6]);
        assertEquals("application/json", lines[7]);
        assertEquals("1795834800", lines[8]);
        assertEquals("nonce-test-000001", lines[9]);
        assertEquals(
            "e3b0c44298fc1c149afbf4c8996fb924"
            + "27ae41e4649b934ca495991b7852b855",
            lines[10]);
        assertFalse(canonical.endsWith("\n"));
    }

    @Test
    void noQueryStillHasAnExplicitEmptyCanonicalLine() {
        String canonical = new String(
                CanonicalRequestV1.canonicalBytes(input(null, "")),
                StandardCharsets.UTF_8);
        String[] lines = canonical.split("\n", -1);
        assertEquals(11, lines.length);
        assertEquals("", lines[6]);
        assertEquals("application/json", lines[7]);
    }

    @Test
    void equivalentUniqueQueryOrderProducesIdenticalBytes() {
        assertArrayEquals(
                CanonicalRequestV1.canonicalBytes(input("b=2&a=1", "x")),
                CanonicalRequestV1.canonicalBytes(input("a=1&b=2", "x")));
        assertEquals("a=~&b=%2F",
                CanonicalRequestV1.canonicalQuery("b=%2f&a=%7e"));
    }

    @Test
    void plusAndSpaceHaveDifferentCanonicalRepresentations() {
        assertEquals("q=hello%2Bworld",
                CanonicalRequestV1.canonicalQuery("q=hello+world"));
        assertEquals("q=hello%20world",
                CanonicalRequestV1.canonicalQuery("q=hello%20world"));
        assertNotEquals(
                CanonicalRequestV1.canonicalQuery("q=a+b"),
                CanonicalRequestV1.canonicalQuery("q=a%20b"));
    }

    @Test
    void percentDecodeRunsOnlyOnce() {
        assertEquals("x=%252F",
                CanonicalRequestV1.canonicalQuery("x=%252F"));
        assertEquals("x=%2F",
                CanonicalRequestV1.canonicalQuery("x=%2f"));
        assertNotEquals(
                CanonicalRequestV1.canonicalQuery("x=%252F"),
                CanonicalRequestV1.canonicalQuery("x=%2F"));
    }

    @Test
    void duplicateAfterDecodeMustBeRejected() {
        for (String raw : List.of("a=1&a=2", "a=1&%61=2")) {
            assertThrows(IllegalArgumentException.class,
                    () -> CanonicalRequestV1.canonicalQuery(raw), raw);
        }
    }

    @Test
    void malformedQueryAndInvalidUtf8AreRejected() {
        for (String raw : List.of(
                "a", "=x", "x=1&", "x=1&&y=2", "a=%",
                "a=%G0", "a=%C0%AF", "a=%FF", "a=%00",
                "a=%0D%0A", "a=bad value", "a=1;b=2",
                "a=1=2", "a=é")) {
            assertThrows(IllegalArgumentException.class,
                    () -> CanonicalRequestV1.canonicalQuery(raw), raw);
        }
    }

    @Test
    void rejectsUnsupportedOrAmbiguousPath() {
        for (String path : List.of(
                "/a/../admin", "/a/%2F/b", "//admin",
                "/v1/orders/", "/v1/./orders", "/a?x=1")) {
            var input = new CanonicalRequestV1.Input(
                    "client-a-k1", "POST", path, "x=1",
                    "application/json", "1795834800",
                    "nonce-test-000001", new byte[0]);
            assertThrows(IllegalArgumentException.class,
                    () -> CanonicalRequestV1.canonicalBytes(input), path);
        }
    }

    @Test
    void changingBodyInvalidatesThePreviousHmac() throws Exception {
        byte[] signed = hmac(CanonicalRequestV1.canonicalBytes(
                input("currency=VND", "{\"amount\":100000}")));
        byte[] tampered = hmac(CanonicalRequestV1.canonicalBytes(
                input("currency=VND", "{\"amount\":900000}")));

        // Cùng keyId, method, path/query, timestamp, nonce.
        // Chỉ thay body trước khi request được verify.
        assertFalse(MessageDigest.isEqual(signed, tampered));
    }

    @Test
    void bodyArrayIsDefensivelyCopied() {
        byte[] supplied = "data".getBytes(StandardCharsets.UTF_8);
        var input = new CanonicalRequestV1.Input(
                "client-a-k1", "POST", "/v1/orders", "",
                "application/json", "1795834800",
                "nonce-test-000001", supplied);

        byte[] before = CanonicalRequestV1.canonicalBytes(input);
        supplied[0] = 'X';
        byte[] accessor = input.body();
        accessor[0] = 'Y';

        assertArrayEquals(before, CanonicalRequestV1.canonicalBytes(input));
    }

    @Test
    void enforcesBoundsOnQueryAndBody() {
        assertThrows(IllegalArgumentException.class,
                () -> CanonicalRequestV1.canonicalQuery(
                        "x=" + "a".repeat(4096)));

        var oversized = new CanonicalRequestV1.Input(
                "client-a-k1", "POST", "/v1/orders", "",
                "application/json", "1795834800",
                "nonce-test-000001",
                new byte[CanonicalRequestV1.MAX_BODY_BYTES + 1]);

        assertThrows(IllegalArgumentException.class,
                () -> CanonicalRequestV1.canonicalBytes(oversized));
    }

    @Test
    void randomPermutationsOfUniqueKeysAreEquivalent() {
        Random random = new Random(0x5EEDL);
        String[] values = {"", "abc", "%7e", "%2F", "+", "%C3%A9"};

        for (int iteration = 0; iteration < 1_000; iteration++) {
            java.util.ArrayList<String> pairs = new java.util.ArrayList<>();
            int count = 1 + random.nextInt(12);
            for (int i = 0; i < count; i++) {
                pairs.add("k" + i + "="
                        + values[random.nextInt(values.length)]);
            }
            String first = CanonicalRequestV1.canonicalQuery(
                    String.join("&", pairs));
            Collections.shuffle(pairs, random);
            assertEquals(first, CanonicalRequestV1.canonicalQuery(
                    String.join("&", pairs)));
            assertEquals(first, CanonicalRequestV1.canonicalQuery(first));
        }
    }
}
~~~

### 7.1. Bổ sung test độc lập signer ↔ verifier

Những JUnit test trên dùng **cùng Java canonicalizer**, vì vậy chúng kiểm tra tính nhất quán nội bộ nhưng chưa đủ bảo đảm tương thích đa ngôn ngữ. Cần phát hành các vector với:

- Raw HTTP request-target và body bytes **không nhạy cảm**.
- Từng trường sau parse, canonical query, 11 dòng canonical, độ dài và **canonical bytes dưới dạng hex**.
- Shared secret **chỉ dành cho test vector**, HMAC-SHA256 tag mong đợi.
- Negative vectors: malformed percent, duplicate query, raw Unicode, timestamp sai, nonce lặp, body đổi, algorithm/key mismatch.
- Kết quả chạy từ ít nhất **hai implementation độc lập** (ví dụ Java client và một verifier trong ngôn ngữ khác), đi trực tiếp và qua gateway.

Định dạng ký khác nhau về một byte LF, khoảng trắng, Unicode code point hay digest body sẽ tạo tag khác. Đừng "chữa" sự khác biệt bằng cách dùng `trim()`, tự đổi case giá trị hoặc bỏ thành phần gây lỗi khỏi chữ ký.

## 8. Kiểm thử end-to-end: từ canonical bytes tới nghiệp vụ

Serializer đúng không đủ nếu gateway thay request, controller bind query theo cách khác, nonce store phân tách theo từng instance hoặc handler đọc body khác với dữ liệu đã xác minh. Vì vậy bộ test phải chạy qua **signer → gateway → HTTP adapter → verifier → authorization → handler**.

### 8.1. Ma trận kiểm thử bắt buộc

| ID | Dữ liệu/thao tác | Kỳ vọng |
|---|---|---|
| CF-01 | Key active, HMAC đúng, timestamp/nonce mới, body nguyên vẹn | Pass authentication rồi áp dụng authorization |
| CF-02 | Hoán vị cặp query có **key duy nhất** | Cùng canonical bytes |
| CF-03 | `q=a+b` so với `q=a%20b` | Khác canonical bytes và tag |
| CF-04 | `x=%2f` so với `x=%2F` | Cùng canonical bytes |
| CF-05 | `x=%2F` so với `x=%252F` | Khác canonical bytes |
| CF-06 | `role=user&role=admin` hoặc `a=1&%61=2` | Reject duplicate trước handler |
| CF-07 | `x=%`, `x=%G0`, `x=%C0%AF`, raw Unicode hoặc control | Reject có kiểm soát, không gây unhandled 500 |
| CF-08 | `/a/../admin`, `//admin`, `/a%2Fb` | Reject theo path policy v1 |
| CF-09 | Body thay một byte, giữ signature cũ, **nonce chưa dùng** | Reject HMAC |
| CF-10 | `Content-Type` thay ngoài hợp đồng | Reject contract/HMAC |
| CF-11 | Thay keyId/algorithm/version/nonce sau khi ký | Reject policy hoặc chữ ký |
| CF-12 | Timestamp `now - 301s`, ký lại đúng | Reject expired |
| CF-13 | Timestamp `now - 300s`, ký lại đúng | Pass freshness tại biên dưới |
| CF-14 | Timestamp `now + 60s`, ký lại đúng | Pass freshness tại biên trên |
| CF-15 | Timestamp `now + 61s`, ký lại đúng | Reject future |
| CF-16 | Hai request đúng HMAC có cùng keyId+nonce đến hai instance đồng thời | Tối đa một lần pass |
| CF-17 | Key đã revoke, HMAC đúng, timestamp và nonce mới | Reject credential |
| CF-18 | Algorithm không allowlist hoặc sai per-key policy | Reject |
| CF-19 | HMAC đúng nhưng principal truy cập resource tenant khác | Deny authorization |
| CF-20 | Nonce store unavailable | Fail closed; không tạo side effect |
| CF-21 | Request qua gateway rewrite path/query/headers/body | Reject nếu mất tính nhất quán của contract |
| CF-22 | Raw query/header/body quá lớn hoặc input fuzz bất thường | Reject bounded, không exhaustion |

**Giữ biến độc lập:** Với CF-09, phải sửa body **trước lần gửi đầu tiên**; nếu phát lại request đã được chấp nhận, nonce store có thể reject và che giấu lỗi không ký body. Với CF-17, phải ký đúng bằng key đã revoke, dùng timestamp và nonce **mới**, vì request expired không chứng minh revocation có hiệu lực. Với CF-12 đến CF-15, phải tạo chữ ký mới cho đúng timestamp đang thử.

### 8.2. Kiểm tra verifier và handler có cùng ý nghĩa

Ở staging, dùng một fixture không nhạy cảm để ghi:

- Request ID, policy version, gateway/verifier build và canonical bytes digest của **cả signer lẫn verifier**.
- Canonical path/query được verifier xử lý và giá trị query thực tế handler bind được.
- Digest của body đã verify và đúng body bytes handler sử dụng.
- Principal đã được xác thực, tenant/resource và kết quả authorization.
- Trạng thái claim nonce, timestamp freshness và kết quả nghiệp vụ/transaction ID.

Nếu verifier reject duplicate query nhưng handler vẫn nhận request đó, hoặc verifier băm một body trong khi controller đọc một stream khác, đó là lỗi tích hợp. Trường hợp framework không thể cung cấp raw path/query như hợp đồng cần, phải chuyển điểm verify sang trust boundary phù hợp hoặc thiết kế một version khác; không nên tin rằng mọi API đặt tên `getRawPath()` đều bảo toàn original wire bytes.

### 8.3. Body streaming và gateway

Trong Servlet/MVC, một wrapper cache body thường chỉ cache **khi stream đã được đọc**. Gọi `getContentAsByteArray()` quá sớm có thể trả mảng rỗng, trong khi handler đọc body thật sau đó. Cần có adapter đọc với giới hạn, tạo digest và bảo đảm handler dùng lại **cùng bytes đã xác minh**.

Trong WebFlux, body là stream reactive. Không subscribe hai lần tùy tiện; cần buffer/decorate có hạn mức và quản lý memory/`DataBuffer` lifecycle. Với upload lớn, cân nhắc streaming digest hoặc chunk signing có thứ tự và final marker. **Không thực hiện side effect không thể đảo ngược trước khi xác minh xong dữ liệu liên quan.**

Proxy có thể chuyển HTTP/2 sang HTTP/1.1, giải nén payload, normalize query hoặc gộp header. Cần kiểm tra **cả input phía client, dữ liệu tại gateway và dữ liệu verifier/handler nhận**, theo hợp đồng version cụ thể. Không chữa signature mismatch bằng cách thử nhiều normalization rồi chấp nhận lựa chọn đầu tiên khớp.

## 9. Version migration, key rotation và replay

### 9.1. Thay canonical format là thay protocol

Bất kỳ thay đổi nào về thứ tự trường, signed headers, path/query normalization, Unicode encoding, content type, body digest hay dấu LF đều có thể làm HMAC cũ không hợp lệ. Quy trình nên là:

1. Ghi **Architecture Decision Record** mô tả thay đổi, rủi ro, client bị ảnh hưởng và điều kiện rollback.
2. Phát hành `hmac-v2` với golden/negative test vectors độc lập.
3. Triển khai verifier hỗ trợ v2 **theo policy version trên từng credential/client**; không fallback v2 → v1 nếu HMAC v2 sai.
4. Cập nhật signer của client và, nếu cần, cấp `keyId` mới để ràng buộc version/algorithm rõ.
5. Chạy canary trực tiếp và qua gateway, đối chiếu canonical bytes lẫn dữ liệu handler.
6. Theo dõi tỷ lệ request theo version/key generation và đặt thời hạn chấm dứt v1.
7. Thu hồi credential/version cũ; gửi request HMAC **đúng theo v1** để xác nhận chính sách thực sự từ chối.

Header version do client gửi là input không đáng tin: nó phải được **ký** và đối chiếu với policy server-side. Không cho một client tự chọn version yếu hơn khi credential đã chỉ được phép version mới.

### 9.2. Algorithm agility và rotation

Algorithm và canonical format là **hai chính sách khác nhau**. Global allowlist có thể chứa nhiều thuật toán, nhưng mỗi credential nên được cấp **một** algorithm rõ ràng. Không chuyển tên algorithm từ request trực tiếp vào crypto provider hoặc thử mọi secret/algorithm đến khi tag khớp.

Planned key rotation có thể dùng cửa sổ overlap ngắn có phê duyệt, trong đó keyId cũ và mới mỗi cái có metadata riêng. Nếu secret cũ bị lộ hoặc client signer bị chiếm quyền, phải suspend/revoke key nguy cơ và khôi phục môi trường; **không dùng overlap planned rotation** để duy trì key đã compromise.

### 9.3. Freshness và nonce phân tán

Ví dụ contract chọn:

~~~text
now - 300 seconds <= timestamp <= now + 60 seconds
~~~

Nonce phải unique trong scope credential và được claim **atomic** sau khi chữ ký/freshness hợp lệ. Mọi verifier cần một miền anti-replay chung. Một thao tác Redis minh họa:

~~~text
SET hmac:nonce:<verified-key-scope>:<nonce-digest> 1 NX EX 600
~~~

TTL 600 giây chỉ là ví dụ có dự phòng, cần tính theo freshness window, clock skew và vận hành thực tế. Không dùng `GET` rồi `SET` riêng, không chuyển fallback sang per-pod cache khi Redis lỗi, và không coi nonce là idempotency key nghiệp vụ. Khi store không khả dụng phải **fail closed** đối với request cần chống replay.

### 9.4. Authorization sau HMAC

Canonical request có thể chứa `tenantId` hoặc `resourceId`, nhưng HMAC chỉ xác nhận credential có khả năng ký dữ liệu đó. Server phải rút principal từ credential đã xác minh rồi kiểm tra principal có quyền đối với **resource thực tế**. Một request ký đúng vẫn có thể bị HTTP 403 (hoặc deny theo contract). Khi key đã lộ, attacker có thể ký đúng request độc hại; biện pháp là thu hồi/khôi phục client và incident response, không phải chỉnh serializer.

## 10. Decision record và checklist kiến trúc

| Quyết định | Chính sách minh họa | Đánh đổi |
|---|---|---|
| Domain/version | `HMAC-HTTP-REQUEST` + `hmac-v1` | Rõ mục đích, dễ migration |
| Format | 11 dòng UTF-8, byte LF, không LF cuối | Dễ test, phải chặn newline injection |
| Algorithm | `HMAC-SHA256`, per-key policy | Cần thêm version/key mới nếu thay thuật toán |
| Path | ASCII strict, reject percent/dot segments | An toàn cho API mẫu, không phù hợp mọi URL |
| Query | Parse một lần, UTF-8 strict, unique keys, sort + percent-encode | Không hỗ trợ repeated keys/array |
| Content type | `application/json` được ký | Cần mở rộng có version nếu hỗ trợ media type khác |
| Body | SHA-256 exact bytes | Phải giữ cùng representation qua gateway |
| Credential | keyId + policy server-side | Quản lý lifecycle và distribution |
| Replay | Timestamp + nonce store atomic | Tăng stateful dependency, cần fail closed |
| Proxy | Không biến đổi signed fields ngoài contract | Cần test liên thông HTTP/1.1, HTTP/2 |
| Limits | Path/query/body bounded | Có thể từ chối request rất lớn |

**Không dùng nguyên format v1** nếu API cần Unicode/percent-encoded path, repeated query keys, multipart streaming không giới hạn, routing phụ thuộc authority chưa được ký, nhiều content type hoặc semantic JSON canonicalization. Khi đó phải xây một hợp đồng phù hợp với nhu cầu, có schema/byte rules và test vectors riêng; không nới policy ngầm theo client.

Checklist trước khi chấp thuận thiết kế:

- [ ] Có thứ tự trường, separator, charset, empty values, test vector byte-level và version.
- [ ] Có domain separation, algorithm allowlist và ràng buộc keyId với credential active.
- [ ] Path, query, percent-encoding, Unicode, duplicate keys và signed headers có quy tắc rõ.
- [ ] Parser verifier, gateway và handler không diễn giải khác nhau.
- [ ] Hash body được HMAC ràng buộc và handler dùng đúng dữ liệu đã verify.
- [ ] Timestamp/nonce có cửa sổ, atomic claim, TTL, store sharing và fail closed.
- [ ] Tag HMAC kiểm tra đúng độ dài và so sánh bằng byte an toàn.
- [ ] Test vector tạo độc lập ở client/server, có fuzz và kiểm thử qua gateway.
- [ ] Key rotation, revocation, policy rollout và authorization được kiểm thử riêng.
- [ ] Có giới hạn tài nguyên, observability và kế hoạch migration.

## 11. Bài thực hành tổng hợp

**Bối cảnh:** API `POST /v1/orders` nhận JSON body, các tham số `currency` và `orderId`, một client Java 17 và gateway có thể đổi thứ tự query.

1. Viết ra **11 dòng canonical** cho `currency=VND&orderId=123`, một timestamp/nonce cụ thể và body `{"amount":150000}`; tính digest của đúng body bytes.
2. Chứng minh `orderId=123&currency=VND` tạo canonical query tương đương; còn `q=a+b` khác `q=a%20b`, `x=%2F` khác `x=%252F`.
3. Đưa `role=user&%72ole=admin`, `/v1/../admin` và percent escape không hợp lệ vào test; xác minh parser từ chối trước khi handler chạy.
4. Ký body `{"amount":150000}` rồi thay `amount` thành `950000` mà giữ chữ ký, **chưa dùng nonce lần nào**. Xác minh body tampering bị phát hiện bởi HMAC.
5. Chạy fixture qua gateway, đối chiếu canonical bytes và dữ liệu handler; chứng minh request ký đúng nhưng truy cập tenant khác bị authorization từ chối.
6. Đề xuất `hmac-v2` khi chuyển từ ký raw query sang query canonical, có migration policy, keyId/version binding, test vector, canary và hạn chót tắt v1.

**Kết luận:** Chọn canonical format là quyết định an ninh về **chính xác dữ liệu nào được HMAC xác thực**. Thiết kế tốt tạo cùng byte ở client và verifier, loại bỏ request nhập nhằng, bao phủ body và metadata thiết yếu, kiểm chứng qua gateway, phối hợp timestamp/nonce, hỗ trợ key rotation và giữ rõ ranh giới giữa xác thực với phân quyền.


