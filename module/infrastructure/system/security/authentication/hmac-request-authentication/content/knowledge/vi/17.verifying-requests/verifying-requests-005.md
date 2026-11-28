# Tính expected signature

**Expected signature** là chữ ký mà **server tự tính lại** từ HTTP request đã nhận, canonical request theo hợp đồng và shared secret đáng tin cậy gắn với `keyId` của client. Khi xác minh HMAC, server **không tin** chuỗi chữ ký do client gửi; server dùng chuỗi đó làm **giá trị cần kiểm tra** và tự tính một giá trị kỳ vọng độc lập.

Ví dụ client gửi `X-Signature` kèm request tạo đơn hàng. Verifier xây lại method, path, query, signed headers và digest của chính body nhận được, lấy secret phù hợp từ key registry, chạy `HMAC-SHA256` và so sánh **tag byte** đã tính với tag byte decode từ header. Nếu khác nhau, request không vượt qua xác thực.

Bài thuộc chương **Xác minh request** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Mô-đun thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request chứa method, URI, header hoặc body theo hợp đồng; người học cần biết cả **phép tính expected signature**, chống replay bằng timestamp/nonce, vòng đời key rotation, tương thích proxy/gateway và ranh giới giữa authentication với authorization.

> **Nguyên tắc trung tâm:** Expected signature phải được tính từ **dữ liệu thực nhận tại ranh giới xác minh** và **secret đã tra trong kho tin cậy**. Không được dùng canonical request, secret, algorithm hay “expected hash” do caller tự cung cấp làm nguồn sự thật.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **presented signature**, **expected signature**, **canonical request** và **authenticated principal**.
2. Giải thích vì sao verifier phải tự tái dựng canonical bytes thay vì tin canonical string do client gửi.
3. Thiết kế hợp đồng `HMAC-VERIFY-V1` về method, path, query, signed headers, body digest, encoding và key ID.
4. Viết Java 17 tính expected tag bằng `javax.crypto.Mac` với secret từ key registry.
5. Kiểm tra format Base64URL, decode chữ ký client và so sánh toàn bộ tag bằng `MessageDigest.isEqual`.
6. Xây dựng trình tự xác minh có kiểm tra key status, timestamp, nonce, replay và authorization.
7. Phân tích các lỗi canonicalization, parser differential và gateway rewrite dẫn đến expected ≠ presented.
8. Tạo test vectors và các bài kiểm thử positive/negative cho signer, verifier, rotation, replay và proxy.

## 2. Presented signature khác expected signature

Một HTTP request có thể chứa:

~~~http
POST /v1/orders/42?dryRun=false HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <base64url-tag>

{"status":"confirmed"}
~~~

Các giá trị liên quan:

| Khái niệm | Nguồn | Có đáng tin ngay khi nhận? |
| --- | --- | --- |
| **Presented signature** | Header `X-Signature` do caller gửi | **Không**; cần validate encoding, decode và so sánh |
| **keyId được trình bày** | Header `X-Key-Id` do caller gửi | **Không**; chỉ là khóa tra bản ghi credential |
| **Shared secret** | Kho credential/secret manager phía server | Có thể tin khi kho, access control và lifecycle được bảo vệ |
| **Canonical request** | Server tái tạo từ request thực nhận theo contract | Chỉ tin sau khi parser/validator bảo đảm không nhập nhằng |
| **Expected tag** | `HMAC(secret, canonicalRequestBytes)` do server tự tính | Là giá trị chuẩn để so sánh theo key/contract đã chọn |
| **Authenticated principal** | Bản ghi credential sau khi MAC hợp lệ | Có thể dùng làm identity cho bước authorization |
| **Authorization decision** | Server policy trên principal, action, resource | Không suy ra chỉ từ tag đúng |

Phép kiểm tra cơ bản:

~~~text
receivedRequest
    -> parse & validate
    -> canonicalRequestBytes

keyId
    -> trusted key registry
    -> secretBytes + allowed algorithm + audience + status

expectedTagBytes = HMAC-SHA256(secretBytes, canonicalRequestBytes)
suppliedTagBytes = Base64URLDecode(X-Signature)

macMatches = secureBytesEqual(expectedTagBytes, suppliedTagBytes)
~~~

**Expected tag** là dãy **32 byte** nếu dùng HMAC-SHA256 đầy đủ. “Expected signature” đôi khi được gọi là chuỗi Base64URL/hex của các byte đó; trong code verifier nên ưu tiên **so byte tag**, không cần encode expected tag thành text để so sánh.

### 2.1. Tính lại không có nghĩa copy signature của client

Một cách triển khai sai:

~~~text
expectedSignature = request.header("X-Expected-Signature")
return expectedSignature == request.header("X-Signature")
~~~

Nếu cả hai giá trị đều đến từ caller, việc so sánh không có bất kỳ bảo đảm mật mã nào.

Tương tự, server không được dùng:

~~~text
request.header("X-Secret")
request.header("X-HMAC-Algorithm")
request.header("X-Canonical-Request")
~~~

làm dữ liệu đáng tin để quyết định khóa/thuật toán/canonical bytes. Có thể có protocol metadata được ký và kiểm tra, nhưng **quyền chọn thuật toán, key record và canonicalization policy** vẫn phải do server kiểm soát.

## 3. Nguồn dữ liệu tin cậy khi tính expected signature

### 3.1. Key registry là nguồn của secret và principal

Một bản ghi minh họa:

~~~yaml
keyId: partner-a-k3
principalId: partner-a-service
audience: orders-api
macAlgorithm: HmacSHA256
encoding: base64url-no-padding
secretRef: secrets/orders/partner-a/k3
status: ACTIVE
notBefore: "2026-09-01T00:00:00Z"
acceptUntil: "2027-01-01T00:00:00Z"
~~~

Ví dụ này là **server-side registry record**, không phải nội dung client được phép tự khai. Verifier phải:

- Tra **đúng `keyId`**, không làm fuzzy match hoặc tự chọn khóa theo tag.
- Kiểm tra credential có tồn tại, còn hiệu lực và chưa bị revoke.
- Xác nhận key record cho phép service/audience đang nhận request.
- Chọn đúng algorithm và encoding **từ policy/record đã được phê duyệt**.
- Lấy secret bytes từ secret manager bằng quyền tối thiểu.
- Chỉ đưa principal từ record vào security context **sau khi xác thực thành công**.

`X-Key-Id` không tự chứng minh caller là `partner-a-service`. Nó chỉ nói rằng caller **đang yêu cầu** verifier sử dụng key record ấy. Bằng chứng possession nằm ở HMAC hợp lệ dưới secret của record đó.

### 3.2. Secret phải được giải mã đúng dạng cấp phát

Nếu secret manager lưu 32 byte key dưới dạng Base64, phải decode Base64 thành byte trước khi gọi JCA `Mac`. Nếu kho lưu key dưới dạng hex, phải hex-decode. Không lấy UTF-8 của **chuỗi biểu diễn** nếu hợp đồng nói đó là encoding của khóa nhị phân.

~~~text
HexDecode("3031") -> bytes 30 31
UTF8("3031")      -> bytes 33 30 33 31
~~~

Hai key bytes khác nhau sẽ tạo hai expected tags khác nhau, dù người vận hành tưởng đang dùng “cùng secret string”.

Không đưa secret vào HTTP request, URL, response hoặc log. Key ID thường không bí mật; secret mới là bí mật.

### 3.3. Server phải chọn algorithm một cách có kiểm soát

Không để caller tùy chọn:

~~~http
X-HMAC-Algorithm: none
X-Signature-Encoding: permissive
~~~

rồi verifier tự chuyển behavior. Nếu contract `v1` cho phép `HmacSHA256` và Base64URL không padding, thì server dùng đúng cặp này cho key record phù hợp. Nếu có version `v2` dùng HMAC-SHA384, version/key policy phải rõ và metadata ảnh hưởng xác thực cần được ràng buộc, không phải “thử tất cả thuật toán đến khi khớp”.

## 4. Hợp đồng minh họa HMAC-VERIFY-V1

Để xây dựng code và ma trận kiểm thử nhất quán, bài này dùng một hợp đồng cố định cho endpoint JSON tại service `orders-api`.

| Thành phần | Quy tắc V1 |
| --- | --- |
| Endpoint minh họa | `POST /v1/orders/{orderId}` |
| MAC algorithm | `HmacSHA256`, **full 32-byte tag** |
| Signature header | `X-Signature`; đúng một giá trị |
| Signature encoding | Base64URL **không padding**, 43 ký tự |
| Key ID | `X-Key-Id`, 1–80 ký tự ASCII theo contract |
| Timestamp | `X-Timestamp`, Unix seconds ở dạng số thập phân canonical |
| Nonce | `X-Nonce`, 16 byte random biểu diễn thành 32 chữ số hex thường |
| Content type | `Content-Type: application/json` |
| Canonical path | `/` hoặc các segment ASCII unreserved, không dot segments/trailing slash trong ví dụ |
| Canonical query | Unordered unique-key map; `&` ngăn cặp, `=` ngăn name/value, ASCII unreserved; sort theo key |
| Audience | `orders-api`, do server policy/record xác nhận |
| Raw body | SHA-256 của **byte body được xác minh**, lowercase hex 64 ký tự |
| Canonical text | UTF-8, các dòng nối LF, không LF cuối |
| Replay | Timestamp window và shared atomic nonce store |
| Authorization | Principal từ credential record, không từ header caller tự khai |

**Đây là hợp đồng phục vụ học tập**, không phải chuẩn chung áp dụng cho mọi HTTP signature. API cần encoded path, URL chứa Unicode, query đa giá trị hoặc các MIME types khác phải chọn canonicalization contract có version phù hợp và kiểm thử parser tương ứng.

### 4.1. Canonical text gồm đúng 10 dòng

~~~text
HMAC-VERIFY-V1
<HTTP_METHOD>
<CANONICAL_PATH>
<CANONICAL_QUERY>
audience:orders-api
content-type:application/json
x-key-id:<KEY_ID>
x-timestamp:<UNIX_SECONDS>
x-nonce:<LOWERCASE_32_HEX>
body-sha256:<LOWERCASE_64_HEX>
~~~

Các dòng được nối bằng một byte LF `0x0A` và **không có LF cuối**. Nếu query vắng mặt, **dòng 4 vẫn tồn tại nhưng rỗng**; tuyệt đối không xóa dòng đó.

Không đưa `X-Signature` vào canonical text tạo ra chính nó vì đây là tag đầu ra cần kiểm tra. Ngược lại, `keyId`, `timestamp` và `nonce` phải nằm trong thông điệp ký, để attacker không thể sửa chúng và giữ tag cũ.

### 4.2. Request minh họa

~~~http
POST /v1/orders/42?dryRun=false HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <43-character-base64url-tag>

{"status":"confirmed"}
~~~

Sau khi tính SHA-256 của **raw bytes** `{"status":"confirmed"}`, server xây:

~~~text
HMAC-VERIFY-V1
POST
/v1/orders/42
dryRun=false
audience:orders-api
content-type:application/json
x-key-id:partner-a-k3
x-timestamp:1790000000
x-nonce:6bfb21974a08417199273b09ca49a3ec
body-sha256:<actual-64-hex-body-digest>
~~~

`<actual-64-hex-body-digest>` là placeholder cần thay bằng digest thật; không phải chữ ký hợp lệ có thể dùng ngay. Timestamp cố định ở ví dụ là dữ liệu mẫu để đối chiếu, không dùng làm timestamp production.

Server encode canonical text thành UTF-8 bytes và tính:

~~~text
expectedTag = HMAC-SHA256(
    secretBytesFromTrustedKeyRecord,
    UTF8(canonicalRequest)
)

suppliedTag = Base64URLDecode(X-Signature)
validMac    = secureCompare(expectedTag, suppliedTag)
~~~

Nếu client thay `dryRun=false` thành `dryRun=true`, hoặc server nhận byte body khác, **expectedTag sẽ khác**. Nếu client thay một header không nằm trong canonical contract, tag có thể vẫn khớp; đó là giới hạn phạm vi signed fields phải được quản trị theo business semantics.

## 5. Verifier phải tái tạo canonical request từ HTTP request thực nhận

**Lỗi nguy hiểm** là tin một chuỗi `X-Canonical-Request` hoặc `X-Body-Hash` do caller gửi mà **không kiểm tra lại** nó có đúng với dữ liệu handler sẽ xử lý hay không.

Giả sử client gửi:

~~~http
POST /v1/orders/42 HTTP/1.1
X-Body-SHA256: <digest-of-benign-body>
X-Signature: <valid-tag-over-that-digest>

{"status":"refunded"}
~~~

Nếu server lấy `X-Body-SHA256` từ header và đưa vào canonical request mà không hash **body thực nhận**, attacker có thể giữ digest cũ nhưng thay raw body. MAC có thể đúng đối với **digest mà attacker khai**, còn handler xử lý payload khác. Một contract có signed body digest cần **tính lại digest từ body bytes**, sau đó đưa chính digest đó vào canonical request.

### 5.1. Thứ tự xử lý bytes và semantics

~~~mermaid
flowchart TD
    A[HTTP request tới verifier] --> B[HTTP parser và body boundary]
    B --> C[Validate method/path/query/signed headers]
    B --> D[Thu raw body bytes đúng contract]
    D --> E[SHA-256 raw body bytes]
    C --> F[Canonical request bytes UTF-8]
    E --> F
    G[Key ID] --> H[Trusted registry và secret]
    F --> I[HMAC expected tag]
    H --> I
    I --> J[So sánh với presented tag]
~~~

Phải xác định body digest là của **bytes nào**. HTTP/1.1 chunk framing không phải byte nội dung body mà ứng dụng nhìn thấy; HTTP/2 chuyển body bằng DATA frames. Nếu `Content-Encoding` được dùng, phải quy định digest trước hay sau giải nén; nếu không cần nén, có thể từ chối content encoding ngoài danh sách.

Đặc biệt, nếu verifier hash body A mà application middleware parse rồi thay thành body B trước handler, HMAC đúng trên A không tự đảm bảo handler thực thi B như mong muốn. Luồng xử lý phải bảo đảm **handler dùng cùng dữ liệu đã xác minh** hoặc một chuyển đổi tin cậy theo contract.

### 5.2. Canonical path và query

Các cặp cần kiểm soát:

~~~text
/v1/orders/42          vs /v1/orders/42/
/v1/files/a%2Fb        vs /v1/files/a/b
/a/../admin            vs /admin
a=1&b=2                vs b=2&a=1
role=user&role=admin   vs role=admin
q=a%26b                vs q=a&b
~~~

Không tự decode/normalize đến khi chữ ký khớp. Nếu verifier xem hai cách biểu diễn giống nhau nhưng router hiểu khác nhau, một tag có thể bảo vệ **một resource** trong khi application xử lý **resource khác**.

Ví dụ contract này chọn path/query nghiêm ngặt và từ chối `%` trong các thành phần nhằm thu hẹp bề mặt nhập nhằng. Hệ thống thật có thể chọn quy tắc khác nhưng **tất cả client, gateway, verifier và router phải cùng hiểu**.

### 5.3. HTTP header canonicalization

Tên header HTTP **không phân biệt hoa/thường**, nên `X-Key-Id` và `x-key-id` có cùng tên. Nhưng nếu caller gửi cả hai với giá trị khác nhau, một HTTP parser có thể lấy giá trị đầu, parser khác lấy giá trị sau hoặc ghép thành một trường.

Verifier cần từ chối các signed headers **trùng hoặc nhập nhằng**; HTTP adapter phải giữ đủ thông tin để phát hiện. Tương tự:

- `Content-Type` phải đúng value theo contract.
- `X-Timestamp` phải được parse với cú pháp canonical và không chứa `+` hay dấu cách mơ hồ.
- `X-Nonce` phải đúng lowercase hex 32 ký tự theo V1.
- Giá trị chứa CR/LF, obs-fold hoặc nhiều giá trị dạng comma ngoài contract phải bị từ chối.
- Signed header names, thứ tự và whitespace normalization phải được version hóa.

## 6. Đầu ra của phép tính expected signature

### 6.1. HMAC-SHA256 tạo tag byte, không phải chuỗi

Với Java JCA:

~~~java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(secretBytes, "HmacSHA256"));
byte[] expectedTag = mac.doFinal(canonicalBytes);
~~~

`expectedTag` là **32 byte**. Nếu protocol dùng HMAC-SHA384 đầy đủ, tag 48 byte; HMAC-SHA512 tạo 64 byte. Không suy thuật toán từ độ dài header do client gửi; dùng algorithm do server policy/key record cho phép.

### 6.2. Khi nào mới encode expected tag?

Có hai cách diễn giải “expected signature”:

- **Expected tag bytes:** Kết quả thô từ `Mac.doFinal(...)`, thích hợp nhất để so sánh mật mã.
- **Expected signature text:** Hex hoặc Base64URL của expected tag; hữu ích cho golden tests và công cụ debug, nhưng không cần thiết cho verifier production.

Nếu contract dùng Base64URL không padding:

~~~text
HMAC-SHA256 tag: 32 byte
Signature text: 43 ký tự Base64URL, không có "="
~~~

Server nên **decode presented text thành 32 byte**, rồi so expected tag bytes với presented tag bytes. So sánh chuỗi văn bản trước khi chuẩn hóa/kiểm tra định dạng có thể đưa vào nhiều representation hoặc lệ thuộc cách encoding.

### 6.3. Không dùng hash không khóa làm expected signature

~~~text
SAI: expected = SHA256(canonicalRequest)
SAI: expected = SHA256(secret || canonicalRequest)
SAI: expected = request.header("X-Body-SHA256")
ĐÚNG: expected = HMAC-SHA256(secretBytes, canonicalRequestBytes)
~~~

SHA-256 của body là một **digest** để ràng buộc payload vào canonical request; nó không thay thế HMAC tag. HMAC phải dùng primitive được thiết kế cho xác thực thông điệp, không tự kết hợp SHA-256 và secret bằng cách nối chuỗi tùy ý.

## 7. Java 17: tạo canonical bytes độc lập trong verifier

Đoạn code này **tự chứa** ở mức contract V1, tập trung vào expected signature. Nó giả định HTTP adapter đã kiểm tra framing và cung cấp **raw path, raw query, đúng một giá trị của mỗi signed header và raw body bytes**. Các giá trị được kiểm tra lại theo một policy V1 nghiêm ngặt.

### 7.1. Record input và canonicalizer

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;
import java.util.StringJoiner;
import java.util.TreeMap;
import java.util.regex.Pattern;

public final class VerifierCanonicalV1 {
    public record Input(
            String method,
            String rawPath,
            String rawQuery,
            String contentType,
            String keyId,
            String timestamp,
            String nonce,
            byte[] rawBody) {}

    private static final Pattern PATH =
            Pattern.compile("/|/[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*");
    private static final Pattern NAME =
            Pattern.compile("[A-Za-z0-9._~-]+");
    private static final Pattern VALUE =
            Pattern.compile("[A-Za-z0-9._~-]*");
    private static final Pattern KEY_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,80}");
    private static final Pattern TIMESTAMP =
            Pattern.compile("(0|[1-9][0-9]{0,18})");
    private static final Pattern NONCE =
            Pattern.compile("[0-9a-f]{32}");

    private VerifierCanonicalV1() {}

    private static String canonicalPath(String rawPath) {
        if (rawPath == null || rawPath.length() > 2048 ||
                !PATH.matcher(rawPath).matches()) {
            throw new IllegalArgumentException("Invalid path");
        }

        if (!rawPath.equals("/")) {
            for (String segment : rawPath.substring(1).split("/", -1)) {
                if (segment.equals(".") || segment.equals("..")) {
                    throw new IllegalArgumentException("Invalid path");
                }
            }
        }
        return rawPath;
    }

    private static String canonicalQuery(String rawQuery) {
        if (rawQuery == null) {
            return ""; // Hoàn toàn không có query.
        }
        if (rawQuery.isEmpty() || rawQuery.length() > 4096) {
            // /path? (query có mặt nhưng rỗng) bị V1 từ chối.
            throw new IllegalArgumentException("Invalid query");
        }

        String[] pairs = rawQuery.split("&", -1);
        if (pairs.length > 50) {
            throw new IllegalArgumentException("Too many query pairs");
        }

        Map<String, String> sorted = new TreeMap<>();
        for (String pair : pairs) {
            int eq = pair.indexOf('=');
            if (eq <= 0 || eq != pair.lastIndexOf('=')) {
                throw new IllegalArgumentException("Invalid query");
            }

            String name = pair.substring(0, eq);
            String value = pair.substring(eq + 1);
            if (!NAME.matcher(name).matches()
                    || !VALUE.matcher(value).matches()
                    || sorted.putIfAbsent(name, value) != null) {
                throw new IllegalArgumentException("Invalid query");
            }
        }

        StringJoiner output = new StringJoiner("&");
        for (var pair : sorted.entrySet()) {
            output.add(pair.getKey() + "=" + pair.getValue());
        }
        return output.toString();
    }

    public static byte[] canonicalBytes(Input req)
            throws GeneralSecurityException {
        if (req == null
                || !"POST".equals(req.method())
                || !"application/json".equals(req.contentType())
                || req.keyId() == null
                || !KEY_ID.matcher(req.keyId()).matches()
                || req.timestamp() == null
                || !TIMESTAMP.matcher(req.timestamp()).matches()
                || req.nonce() == null
                || !NONCE.matcher(req.nonce()).matches()
                || req.rawBody() == null
                || req.rawBody().length > 1024 * 1024) {
            throw new IllegalArgumentException("Invalid signed fields");
        }

        String path = canonicalPath(req.rawPath());
        String query = canonicalQuery(req.rawQuery());

        String bodyDigest = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                        .digest(req.rawBody()));

        String text = String.join("\n",
                "HMAC-VERIFY-V1",
                req.method(),
                path,
                query,
                "audience:orders-api",
                "content-type:" + req.contentType(),
                "x-key-id:" + req.keyId(),
                "x-timestamp:" + req.timestamp(),
                "x-nonce:" + req.nonce(),
                "body-sha256:" + bodyDigest);

        return text.getBytes(StandardCharsets.UTF_8);
    }
}
~~~

**Phạm vi cố ý của V1:**

- Path chỉ chứa ASCII unreserved và slash phân tách, không trailing slash ngoài root, không encoded slash/dot, không Unicode.
- Query có key duy nhất, value có thể rỗng, mỗi cặp có đúng một `=`, phân tách bằng `&`, sort theo key; không hỗ trợ percent-encoding/semicolons/plus.
- Content type chỉ được `application/json`; mọi signed header value phải đúng dạng, không tự trim.
- Method `POST` được cố định cho bài; các API khác phải bổ sung method/route policy và kiểm thử tương ứng.
- Body tối đa 1 MiB như một **giới hạn ví dụ**. HTTP server/gateway cũng cần giới hạn trước khi buffer vào RAM.
- Giá trị audience `orders-api` cố định; verifier kiểm tra credential record tương ứng với audience này.

**Không lấy `rawPath` đã decode từ router hoặc query map đã mất duplicates để đưa vào hàm.** HTTP adapter phải nhận dữ liệu đúng ranh giới tin cậy trước khi verifier chạy; nếu proxy đã rewrite, thiết kế signing boundary phải được xác định và test riêng.

### 7.2. Vì sao code không nhận client-provided body hash?

`canonicalBytes` nhận **rawBody` và tính `SHA-256` tại server. Nó không có đối số `clientProvidedBodyHash`. Nhờ vậy attacker không thể chỉ thay body mà vẫn giữ digest khai báo cũ trong canonical request.

Nếu một protocol bắt buộc client gửi `X-Content-SHA256`, verifier phải **tự hash raw body**, kiểm tra digest header trùng với hash thật theo định dạng cố định, và ràng buộc giá trị đó trong chữ ký. Không được xem digest header do client gửi là bằng chứng độc lập.

## 8. Java 17: tính expected tag và so sánh

### 8.1. Tính expected HMAC bằng JCA

~~~java
import java.security.GeneralSecurityException;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class ExpectedHmacSha256 {
    public static final int TAG_LENGTH_BYTES = 32;

    private ExpectedHmacSha256() {}

    public static byte[] calculate(
            byte[] trustedSecret,
            byte[] canonicalBytes) throws GeneralSecurityException {

        if (trustedSecret == null || trustedSecret.length == 0
                || canonicalBytes == null) {
            throw new IllegalArgumentException("Invalid MAC input");
        }

        // Mac là stateful; tạo instance cho mỗi phép tính.
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(trustedSecret, "HmacSHA256"));

        byte[] tag = mac.doFinal(canonicalBytes);
        if (tag.length != TAG_LENGTH_BYTES) {
            throw new GeneralSecurityException("Unexpected HMAC length");
        }
        return tag;
    }
}
~~~

`trustedSecret` đến từ một credential record đã chọn bằng key ID, **không đến từ HTTP request**. Khi cấp phát credential mới, nên dùng secret ngẫu nhiên có entropy cao (ví dụ 32 byte từ CSPRNG). Trong production, giữ secret trong secret manager và tránh debug logs chứa key material.

### 8.2. Strict decode presented signature

Contract V1: HMAC-SHA256 full 32 byte, Base64URL không padding đúng 43 ký tự.

~~~java
import java.util.Base64;
import java.util.regex.Pattern;

public final class SignatureEncodingV1 {
    private static final Pattern FORMAT =
            Pattern.compile("[A-Za-z0-9_-]{43}");

    private SignatureEncodingV1() {}

    public static byte[] decode(String presented) {
        if (presented == null || !FORMAT.matcher(presented).matches()) {
            throw new IllegalArgumentException("Invalid signature");
        }

        final byte[] bytes;
        try {
            bytes = Base64.getUrlDecoder().decode(presented);
        } catch (IllegalArgumentException malformed) {
            throw new IllegalArgumentException("Invalid signature", malformed);
        }

        if (bytes.length != ExpectedHmacSha256.TAG_LENGTH_BYTES
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(bytes).equals(presented)) {
            // Chặn chuỗi không canonical dù decoder chấp nhận.
            throw new IllegalArgumentException("Invalid signature");
        }

        return bytes;
    }
}
~~~

Lưu ý rằng **độ dài/format** của tag là thông tin công khai theo contract; kiểm tra trước HMAC không tiết lộ secret. Tuy nhiên API nên trả lỗi xác thực chung và tránh tiết lộ chi tiết key registry.

### 8.3. So sánh hai tag byte

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;

public final class ExpectedSignatureVerifierV1 {
    private ExpectedSignatureVerifierV1() {}

    public static boolean matches(
            byte[] trustedSecret,
            VerifierCanonicalV1.Input received,
            String presentedSignature) throws GeneralSecurityException {

        final byte[] supplied;
        try {
            supplied = SignatureEncodingV1.decode(presentedSignature);
        } catch (IllegalArgumentException invalidFormat) {
            return false;
        }

        byte[] canonical = VerifierCanonicalV1.canonicalBytes(received);
        byte[] expected = ExpectedHmacSha256.calculate(
                trustedSecret, canonical);

        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

Đây là **bước xác minh tag**, chưa phải toàn bộ authentication middleware. Nếu `matches(...)` trả `true`, request còn phải vượt qua kiểm tra credential status, timestamp/nonce, authorization và validation nghiệp vụ.

**Vì sao không so chuỗi?** Khi cùng một tag có nhiều text representation (ví dụ hex uppercase/lowercase hoặc Base64 có/không padding), việc so chuỗi dễ phụ thuộc vào normalization. Với contract strict ở đây, verifier decode rồi **so toàn bộ bytes**, dùng `MessageDigest.isEqual` thay vì tự viết vòng lặp thoát sớm ở byte đầu tiên khác nhau.

### 8.4. Không so tag bị cắt ngắn

Các cách sai:

~~~text
expectedHex.startsWith(presentedHex)
Arrays.equals(expectedTag[0..7], supplied[0..7])
compareFirst16BytesOnly(...)
~~~

Bài này quy định **full-tag HMAC-SHA256**. Một protocol dùng truncated HMAC cần thiết kế/đánh giá riêng và phải công bố độ dài đầy đủ của phiên bản đó; không tùy tiện nhận prefix do caller gửi.

### 8.5. Không tự encode expected tag để quyết định thuật toán

Server không nên:

~~~text
if len(signature) == 64 -> treat as hex HMAC-SHA256
else if len(signature) == 43 -> treat as Base64URL HMAC-SHA256
else try HMAC-SHA384
~~~

Đây là **algorithm/encoding confusion**. Algorithm được chọn từ contract/key record; signature length chỉ được dùng để **validate đúng format đã chọn**.

## 9. Luồng xác minh end-to-end đúng thứ tự

Một middleware kiểm tra HMAC không chỉ gọi `matches(...)`. Nó cần đưa mỗi phép kiểm tra vào một vị trí có ý nghĩa bảo mật.

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Validate HTTP framing, limits và header duplicates]
    B --> C[Parse keyId, timestamp, nonce, signature]
    C --> D[Lookup key record + allowed policy]
    D --> E[Canonicalize request thật và hash raw body]
    E --> F[Calculate expected HMAC]
    F --> G{Expected và presented tag khớp?}
    G -- Không --> X[Reject authentication]
    G -- Có --> H{Timestamp còn trong window?}
    H -- Không --> X
    H -- Có --> I{Atomic nonce insert thành công?}
    I -- Không --> X
    I -- Có --> J[Principal từ trusted credential]
    J --> K{Authorize action/resource/tenant?}
    K -- Không --> Y[Reject authorization]
    K -- Có --> L[Business handler + idempotency]
~~~

Có thể kiểm tra một số điều kiện rẻ như timestamp format, request size và cửa sổ thời gian **trước phép HMAC** để hạn chế chi phí. Nhưng không được **chiếm nonce trong replay store trước khi MAC hợp lệ**, vì request giả mạo có thể làm bẩn store.

### 9.1. Các lỗi phải phân loại đúng

| Kiểm tra | Ví dụ lỗi | Kết quả |
| --- | --- | --- |
| HTTP parser / limits | `Content-Length` mâu thuẫn framing, header trùng | Từ chối trước canonicalization |
| Signature format | Base64URL sai alphabet, sai độ dài | Không có presented tag hợp lệ |
| Key lookup | Key ID không tồn tại hoặc revoked | Không có credential được phép |
| Canonicalization | Query duplicate, encoded slash ngoài contract | Từ chối canonical request |
| HMAC compare | Expected tag khác presented tag | Xác thực thất bại |
| Freshness | Timestamp cũ hoặc quá xa trong tương lai | Request quá hạn/chưa hợp lệ |
| Replay | Nonce đã thấy trong window | Request trùng |
| Authorization | Principal không có quyền resource | HMAC có thể đúng nhưng thao tác bị cấm |
| Business/idempotency | Event đã xử lý, state transition không hợp lệ | Xử lý theo quy tắc nghiệp vụ |

Phía client có thể nhận một lỗi xác thực chung cho nhiều lỗi ở lớp authentication; log nội bộ có thể lưu **mã nguyên nhân**, không lộ secret, full signature, raw body nhạy cảm hoặc thông tin key registry.

### 9.2. Principal chỉ được thiết lập sau MAC

Một anti-pattern:

~~~text
principal = registry.find(keyId).principalId
securityContext.setPrincipal(principal)
checkHmacLater()
~~~

Nếu handler hoặc filter downstream đọc principal trước khi HMAC hoàn tất, một caller chỉ cần **biết key ID** có thể tạm thời được coi là người sở hữu credential đó.

Đúng hơn:

~~~text
credential = registry.find(keyId)     // chưa authenticated
tagValid = verifyExpectedHmac(...)
if (!tagValid) reject
freshnessAndReplayGate(...)
principal = credential.principalId    // authenticated context
authorize(principal, requestResource)
~~~

Không bao giờ bỏ qua authorization chỉ vì expected và presented tags trùng nhau.

## 10. Timestamp và nonce bảo đảm tính mới, không phải HMAC

### 10.1. Tại sao tag vẫn đúng khi replay?

Giả sử request đã ký được capture nguyên vẹn. Kẻ tấn công gửi lại đúng method, URI, headers, body và `X-Signature`. Với cùng secret và canonical bytes:

~~~text
expectedTag = HMAC(K, M)
presentedTag = HMAC(K, M)
expectedTag == presentedTag
~~~

Do đó bước so HMAC **vẫn thành công**. Chống replay là **một điều kiện riêng** bắt buộc nếu API không cho dùng lại request.

### 10.2. Chính sách timestamp mẫu

Ví dụ:

~~~text
X-Timestamp: Unix seconds, canonical decimal
maxPastAge:   300 seconds
futureSkew:    30 seconds
~~~

Server kiểm tra:

~~~text
timestamp >= now - 300
timestamp <= now + 30
~~~

Có thể viết code so sánh dạng hiệu để hạn chế overflow khi đã parse miền số không âm:

~~~java
public static boolean isFresh(
        long timestamp, long now,
        long maxPastAge, long futureSkew) {

    if (timestamp < 0 || now < 0
            || maxPastAge < 0 || futureSkew < 0) {
        return false;
    }

    if (timestamp <= now) {
        return now - timestamp <= maxPastAge;
    }
    return timestamp - now <= futureSkew;
}
~~~

Không dùng timestamp `1790000000` cố định từ các ví dụ làm giá trị hiện hành. Trong production lấy thời gian thực, có giám sát clock drift và chốt đúng giới hạn cho API.

### 10.3. Atomic nonce store

Sau khi MAC hợp lệ và timestamp nằm trong window:

~~~text
namespace = "hmac:" + audience + ":" + keyId
replayKey = namespace + ":" + nonce

atomicPutIfAbsent(replayKey, marker, TTL)
    inserted -> tiếp tục
    exists   -> reject replay
~~~

Nếu nhiều verifier instances sử dụng cache cục bộ, cùng nonce có thể được chấp nhận đồng thời trên các node. Cần shared store có thao tác nguyên tử như Redis `SET ... NX EX ...` hoặc cơ chế transaction/unique key tương đương.

TTL phải bao phủ **mọi khoảng thời gian mà request timestamp ấy có thể còn được chấp nhận**, tính cả tương lai cho phép và xử lý clock skew. Không dùng thao tác “đọc nonce trước rồi ghi nonce sau” không nguyên tử.

### 10.4. Đúng HMAC + nonce mới vẫn chưa bảo đảm idempotency

Client có thể gửi hai request **khác nonce** nhưng cùng một thao tác tạo giao dịch. Cả hai có chữ ký hợp lệ và qua replay gate vì nonce khác nhau.

Cần idempotency business-level theo event ID/order ID hoặc `Idempotency-Key` được ký, cùng store nghiệp vụ và logic xử lý trùng. Nonce bảo vệ request replay; idempotency bảo vệ tác động nghiệp vụ khi caller retry tạo request mới.

## 11. Key rotation và lựa chọn expected signature

Một client có thể có hai credential trong thời gian chuyển khóa:

~~~text
partner-a-k2 -> HmacSHA256, secret v2, RETIRING
partner-a-k3 -> HmacSHA256, secret v3, ACTIVE
~~~

Server phải chọn **một record đúng với key ID** của request:

~~~text
X-Key-Id = partner-a-k3
  -> lookup k3
  -> kiểm tra audience/status/lifetime
  -> lấy secret v3
  -> expected = HMAC(secret v3, canonicalBytes)
~~~

Không dùng secret v2 để “thử thêm” nếu k3 không khớp; nếu cả hai key ID đang được phép, **mỗi ID ánh xạ một secret của nó**.

### 11.1. Hậu quả khi thử nhiều secret

Một verifier cố thử `k2`, `k3` và mọi bản cũ cho cùng key ID:

- Gây nhầm lẫn credential nào thực sự ký request.
- Làm revocation khó chắc chắn.
- Tăng chi phí xác minh và nguy cơ timing/oracle từ kết quả khác nhau.
- Che lỗi client đã đổi key ID nhưng giữ secret cũ.
- Tạo tình trạng “credential đã thu hồi vẫn có thể ký” nếu fallback tồn tại.

Để rotation đúng, cấp **key ID mới** khi đổi secret, quản lý trạng thái và thời hạn cụ thể. Có thể overlap hữu hạn theo policy đã phê duyệt, nhưng không fallback tùy tiện.

### 11.2. Đổi thuật toán và contract

Nếu di trú từ `HmacSHA256` sang `HmacSHA384`, expected tag đổi từ 32 thành 48 byte. Signature encoding, parser length, key record algorithm và test vectors cũng cần đổi.

Một record `HmacSHA384` phải tính expected HMAC-SHA384, **không tự thử HMAC-SHA256** vì presented signature có 43 ký tự. Algorithm và canonicalization version được xác định từ server policy và record, metadata client khai có thể được ký và cross-check nhưng không là nguồn tự quyết.

### 11.3. Chữ ký có đúng nhưng khóa bị revoke?

Khi secret bị thu hồi, tag mà client tạo ra có thể vẫn **toán học đúng**. Nhưng verifier phải từ chối **do key status** trước hoặc sau phép tính tùy pipeline; không được cấp authenticated principal. Điều này cho thấy **MAC equality không phải toàn bộ authentication policy**.

## 12. Kiểm thử expected signature bằng known-answer vector

Để tách lỗi HMAC primitive khỏi lỗi HTTP canonicalization, hãy kiểm tra trực tiếp JCA với test vector chuẩn.

### 12.1. RFC 4231 — HMAC-SHA256 test case 1

~~~text
Key:    20 byte, byte nào cũng là 0x0b
Data:   ASCII "Hi There"
Expected HMAC-SHA256 hex (64 ký tự):
b0344c61d8db38535ca8afceaf0bf12b
881dc200c9833da726e9376c2e32cff7
~~~

Hai dòng hex được xuống dòng **chỉ để trình bày**; nối liền chúng thành một chuỗi 64 ký tự.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

byte[] key = new byte[20];
Arrays.fill(key, (byte) 0x0b);

byte[] data = "Hi There".getBytes(StandardCharsets.US_ASCII);
byte[] expected = ExpectedHmacSha256.calculate(key, data);

String expectedHex =
        "b0344c61d8db38535ca8afceaf0bf12b"
      + "881dc200c9833da726e9376c2e32cff7";

if (!expectedHex.equals(HexFormat.of().formatHex(expected))) {
    throw new AssertionError("RFC 4231 KAT failed");
}
~~~

Đây là test **HMAC primitive** với message `Hi There`, **không phải** một canonical HTTP request. Nếu test này PASS nhưng HTTP verification lỗi, cần kiểm tra key provisioning, encoding, raw body và canonical bytes, không tự sửa công thức HMAC.

### 12.2. KAT cho expected signature decoder

Có thể tạo signature text từ tag tham chiếu:

~~~java
import java.util.Base64;

String signature = Base64.getUrlEncoder().withoutPadding()
        .encodeToString(expected);

if (signature.length() != 43) {
    throw new AssertionError("Wrong Base64URL tag length");
}
byte[] decoded = SignatureEncodingV1.decode(signature);

if (!Arrays.equals(expected, decoded)) {
    throw new AssertionError("Round-trip mismatch");
}
~~~

Test này kiểm tra encoding/decoding; khi dùng HTTP request thật vẫn cần canonical request, key registry, freshness và authorization.

## 13. Golden tests để tìm lỗi expected ≠ presented

Một **golden fixture** cho client signer và server verifier nên lưu đầy đủ đầu vào đã được phép lưu trong môi trường test:

~~~text
protocolVersion
keyId
testSecretBytesHex
method
rawPath / canonicalPath
rawQuery / canonicalQuery
signedHeaders: names + canonical values
rawBodyBytes
bodySha256Hex
canonicalText
canonicalBytesHex
expectedTagBytesHex
expectedSignatureBase64Url
~~~

Cùng fixture, hai phía phải tính ra:

~~~text
canonicalBytes_client == canonicalBytes_verifier
expectedTag_client == expectedTag_verifier
signature_client == Base64URL(expectedTag_verifier)
~~~

Khi test lỗi, so từng lớp:

1. Secret bytes có đúng không?
2. Method/path/query theo cùng protocol không?
3. Signed headers/metadata cùng tên/giá trị/thứ tự không?
4. SHA-256 raw body cùng byte không?
5. Canonical request bytes có giống chính xác (hex dump) không?
6. Thuật toán HMAC/key ID/audience có giống policy không?
7. Tag byte có đúng không?
8. Chữ ký được encode/decode theo đúng version không?

Không được nhầm “cùng chuỗi trông giống nhau” với “cùng UTF-8 bytes”. CRLF/LF, Unicode NFC/NFD, trailing spaces và percent-encoding có thể làm tag khác.

### 13.1. Expected signature cần được tái tạo từ request server nhận

Đừng chỉ test `calculate(secret, canonicalTextFromClient)` nếu mọi dòng được client khai. Phải có test cho:

~~~text
HTTP client -> gateway -> HTTP adapter -> verifier -> handler
~~~

Verifier phải lấy các signed fields từ **request tại biên đã thỏa thuận**, tái tạo canonical bytes, so tag, và handler phải xử lý đúng method/resource/body đã xác minh.

## 14. Reverse proxy, gateway và parser differential

### 14.1. Vì sao hai bên cùng secret nhưng tag không khớp?

Proxy/gateway có thể:

- Bỏ prefix `/public` trước khi forward path.
- Thêm/bỏ trailing slash hoặc decode `%2F` thành slash.
- Reorder/merge query parameters; xử lý duplicates khác nhau.
- Đổi `Host`/authority hoặc chuyển HTTP/2 ↔ HTTP/1.1.
- Normalize header values, gộp duplicate header hoặc thay `Content-Type`.
- Parse/serialize lại JSON và thay whitespace/thứ tự keys.
- Giải nén body hoặc thay content encoding.

Nếu client ký **request trước biến đổi** nhưng backend tính expected trên **request sau biến đổi**, HMAC sai dù có cùng secret và algorithm.

### 14.2. Hai kiến trúc tin cậy

**Verifier ở gateway:** Kiểm tra HMAC trên external request trước rewrite. Sau đó gateway chuyển principal và request context đáng tin qua kênh nội bộ được bảo vệ. Backend phải chặn bypass và không tin identity header do Internet tự khai. Quy tắc chuyển external signed resource tới internal handler phải được kiểm soát.

**Verifier ở backend:** Gateway phải giữ nguyên signed fields hoặc áp dụng mapping được **quy định trong hợp đồng** mà client/verifier cùng tái dựng. Không được tin `X-Original-URI` hay `X-Forwarded-Host` do caller tự gửi; nếu dùng metadata proxy, proxy phải xóa giá trị client và bảo vệ đường truyền tới verifier.

### 14.3. Example: prefix rewrite

~~~text
Client ký:      POST /public/v1/orders/42
Gateway gửi:    POST /v1/orders/42
Backend ký lại: POST /v1/orders/42
~~~

Nếu contract ký external path, expected tag của backend **khác** presented tag. Giải pháp không phải thử hai path đến khi khớp mà là:

- Đặt verifier trước rewrite; **hoặc**
- Định nghĩa một mapping canonical path đáng tin, áp dụng trước cả signing và verification với version rõ, chứng minh router thực thi đúng resource.

### 14.4. Nguy cơ HMAC đúng trên một request nhưng handler xử lý request khác

Trường hợp nguy hiểm hơn mismatch tag là verifier dùng raw path, còn router decode và resolve dot segments theo cách khác:

~~~text
Raw path có chữ ký:  /v1/tenants/A/%2E%2E/B/orders/42
Router thực thi:     /v1/tenants/B/orders/42
~~~

Một MAC khớp trên raw path **không tự chứng minh** resource đã được authorize là cùng resource handler thực thi. Phải thống nhất đường đi parse → canonicalize → route → authorize. Với contract V1 đơn giản, từ chối percent-encoding và dot-segment ambiguity trước khi xác minh.

## 15. Phân biệt expected signature đúng với authorization

Xét request:

~~~http
DELETE /v1/tenants/tenant-B/orders/42 HTTP/1.1
X-Key-Id: tenant-A-client-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <valid-tag-under-tenant-A-secret>
~~~

Một client A thực sự sở hữu secret có thể tạo tag **đúng** cho bất kỳ canonical request nào mà chính nó chọn, bao gồm request đến resource của tenant B.

Phân biệt:

| Tầng | Điều được chứng minh |
| --- | --- |
| Format validation | Presented tag có đúng cú pháp không |
| Expected HMAC comparison | Request được ký bởi bên biết secret của key record |
| Key policy | Credential còn hoạt động, đúng algorithm/audience/lifetime không |
| Timestamp/nonce | Request còn mới và chưa bị replay không |
| **Authorization** | Principal được phép làm action trên tenant/resource này không |
| Business validation | Transition, số tiền, trạng thái và idempotency hợp lệ không |

Nếu key record thuộc tenant A, việc tag khớp không cho phép xóa đơn của tenant B. Server phải đối chiếu principal/scope từ registry với tenant/resource xác định từ router tin cậy và policy. Không tin `X-Role` hay `X-Tenant-Id` tự khai làm nguồn quyền, kể cả khi header đó đã ký.

## 16. Ma trận kiểm thử tính expected signature

### 16.1. Primitive, secret và encoding

| Test | Thao tác | Kỳ vọng |
| --- | --- | --- |
| RFC 4231 KAT | Key `0x0b` × 20, data `Hi There` | Expected HMAC-SHA256 đúng vector |
| Same K + same M | Tính expected hai lần | Byte tag giống nhau |
| Different K | Đổi một byte secret, giữ M | Tag cũ không khớp với expected mới |
| Different M | Đổi một byte message, giữ K | Tag cũ không khớp |
| Empty message | Canonical bytes rỗng ở primitive test | HMAC trả tag đầy đủ, không exception |
| Hex-decoded key vs UTF-8 string | Cấp cùng secret string có encoding khác | Tag khác, phát hiện provision sai |
| HMAC-SHA256 tag length | Expected `byte[32]` | PASS |
| HMAC-SHA384 record | Tag phải `byte[48]` | Không tự fallback HMAC-SHA256 |
| Null signature | Không có header | Từ chối |
| Signature 42 ký tự | Thiếu 1 char | Từ chối |
| Signature 44 ký tự | Thừa 1 char | Từ chối theo V1 |
| Base64 standard `+`/`/` | Gửi thay Base64URL | Từ chối |
| Base64URL padding `=` | Thêm padding | Từ chối theo no-padding V1 |
| Base64URL noncanonical | Decoder có thể chấp nhận biểu diễn dư | Re-encode check từ chối |
| Signature truncated | Decode ra ít hơn 32 byte | Từ chối |
| Signature header duplicate | Hai header cùng tên (khác case) | Adapter từ chối |
| Không so đầy đủ tag | Kiểm tra chỉ prefix | Test phải phát hiện lỗi implementation |

### 16.2. Canonical request và HTTP semantics

| Test | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Canonical text đúng | Cùng method/path/query/header/body | HMAC khớp |
| Method tampering | `POST` → `DELETE`, giữ tag | HMAC sai hoặc contract từ chối |
| Path tampering | `/orders/42` → `/orders/43` | HMAC sai |
| Trailing slash | `/orders` → `/orders/` | Theo V1 từ chối input ngoài chuẩn |
| Encoded slash | `%2F` trong path | V1 từ chối |
| Dot segments | `/a/../b` | V1 từ chối |
| Query value tampering | `dryRun=false` → `dryRun=true` | HMAC sai |
| Query reorder | `a=1&b=2` và `b=2&a=1` | V1 canonical query giống nhau |
| Duplicate query key | `tenant=A&tenant=B` | V1 từ chối |
| Query rỗng hiện diện | `/path?` | V1 từ chối; khác query vắng mặt |
| Signed header tampering | `Content-Type` khác `application/json` | V1 từ chối |
| Timestamp tampering | Đổi `X-Timestamp`, giữ tag | HMAC sai |
| Nonce tampering | Đổi `X-Nonce`, giữ tag | HMAC sai |
| Key ID tampering | Đổi `X-Key-Id`, giữ tag | Từ chối do record/MAC |
| Body change | Thay một byte raw JSON | Body digest/HMAC sai |
| JSON reserialization | Đổi key order/whitespace | Digest thay đổi, tag không khớp |
| LF vs CRLF | Dòng canonical đổi delimiter | Expected khác |
| Extra LF cuối | Thêm byte `0A` vào canonical text | Expected khác |
| UTF-8 vs charset khác | Byte canonical khác | Expected khác |
| Unsigned telemetry | Đổi `User-Agent` không ký | MAC có thể giữ nguyên; không dùng cho security |
| False body hash header | Khai digest cũ, body mới | Verifier tự hash body và từ chối |

### 16.3. Policy, replay, gateway và authorization

| Test | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Unknown key ID | Registry không có record | Reject |
| Revoked key | Đúng tag với secret cũ | Reject do status |
| Wrong audience | Credential billing gửi tới orders | Reject |
| Algorithm downgrade | Caller yêu cầu `none` | Reject |
| Rotation | k2/k3 đều hợp lệ trong overlap | Mỗi key ID dùng đúng secret |
| Key ID đổi không đổi tag | Tag k2 nhưng header k3 | Reject |
| Timestamp expired | MAC đúng, quá cửa sổ | Reject freshness |
| Future timestamp | Vượt clock skew | Reject |
| Replay sequential | Gửi hai lần cùng nonce | Request sau bị reject |
| Replay concurrent | Hai verifier instances cùng nonce | Atomic store cho tối đa một request |
| Replay store unavailable | Store timeout | Fail-closed theo policy nhạy cảm |
| Gateway rewrite path | External path khác internal path | Cùng signing boundary hoặc reject |
| Gateway rewrite body | JSON serialize lại | Expected khác, hoặc verify trước rewrite |
| Proxy changes framing | HTTP/1.1 ↔ HTTP/2 | Body bytes/semantics đúng contract |
| Host/authority thay đổi | Gateway route sang service khác | Audience/routing policy reject |
| Header parser differential | `X-Key-Id` lặp | Reject |
| Authenticated tenant A → tenant B | Tag đúng, quyền sai | Authorization reject |
| Duplicate business request | Request mới nonce mới, same event | Idempotency xử lý tác động trùng |

## 17. Tình huống thực tế: expected tag khác dù secret đúng

Một đối tác báo rằng client đã tính signature hợp lệ nhưng server trả lỗi xác thực khi gọi API qua reverse proxy:

~~~text
External: POST /public/v1/orders/42?dryRun=false
Internal: POST /v1/orders/42?dryRun=false
~~~

Client dùng secret của `partner-a-k3` để ký canonical path bên ngoài `/public/v1/orders/42`. Backend tự tính expected HMAC với path nội bộ `/v1/orders/42`.

**Triệu chứng:** HMAC-SHA256 primitive KAT PASS ở hai phía; key/secret đúng; expected và presented tags vẫn khác.

**Nguyên nhân:** Canonical bytes **khác tại dòng path** do gateway rewrite, không phải thuật toán HMAC lỗi.

**Khắc phục:** Chọn điểm xác minh tại gateway trước rewrite hoặc công bố một hợp đồng path mapping chính xác có version, metadata proxy tin cậy và kiểm tra route cuối cùng. Không thử một loạt prefix đến khi một tag khớp.

**Bài học:** Trong troubleshooting, so sánh canonical bytes **trước khi** kiểm tra nội dung tag. Nếu message bytes khác, đổi cơ chế so sánh tag không thể tạo chữ ký đúng một cách an toàn.

### 17.1. Sự cố khác: tag khớp nhưng request bị từ chối

Client gửi lại cùng request, same timestamp và nonce. Server tự tính expected HMAC và thấy **tag khớp** nhưng replay store đã ghi nonce lần trước.

**Kết quả đúng:** Reject request vì replay. Không nới lỏng replay policy hoặc xóa nonce nhằm làm request “hợp lệ”.

Nếu client cần retry thao tác nghiệp vụ, phải dùng policy retry/idempotency rõ và ký request mới với nonce mới khi phù hợp, sau đó business layer đảm bảo không tạo tác động trùng.

## 18. Lỗi triển khai thường gặp

### 18.1. Tin expected signature do client khai

Client có thể cung cấp cùng một chuỗi ở hai header và làm so sánh thành công. Không có ý nghĩa xác thực nếu expected không được server tự tính bằng secret tin cậy.

### 18.2. Lookup secret theo tag thay vì key ID

Thử toàn bộ secret trong kho cho đến khi một tag khớp tạo oracle, tăng tải và gây nhầm principal/key status. Tra đúng key ID, áp dụng policy và không fallback tùy tiện.

### 18.3. Dùng raw canonical text do caller gửi

Caller có thể ký một canonical string nhưng handler xử lý dữ liệu khác. Verifier phải tạo canonical bytes từ HTTP request thực nhận và parser policy thống nhất.

### 18.4. Tin body digest header mà không hash raw body

Nếu attacker sửa body nhưng giữ digest được khai, verifier có thể so HMAC của digest cũ mà bỏ qua payload. Bắt buộc hash body bytes thực tế.

### 18.5. Decode path/query nhiều lần hoặc bỏ qua duplicate keys

Verifier và router có thể chọn resource/parameter khác nhau. Chọn canonicalization contract có version, từ chối ambiguity hoặc chứng minh hai tầng tương đương.

### 18.6. So chữ ký bằng string hoặc chỉ prefix

Không dùng `startsWith`, so một vài ký tự hex hay lựa chọn encoding tự do. Chọn một format, strict-decode rồi so byte tag đầy đủ.

### 18.7. Coi MAC hợp lệ là xác thực hoàn chỉnh

Credential có thể revoked; timestamp có thể hết hạn; nonce đã được dùng. Cần kiểm tra toàn bộ trạng thái trước khi tạo authenticated principal.

### 18.8. Đánh dấu nonce trước khi verify

Attacker có thể gửi request giả với nonce của request hợp lệ để chiếm replay entry. Đánh dấu nonce sau MAC và freshness checks, bằng thao tác nguyên tử.

### 18.9. Dùng unsigned tenant/role header làm authorization

Ngay cả khi MAC đúng trên những signed fields khác, caller vẫn có thể tự thêm/sửa header ngoài phạm vi HMAC. Danh tính và quyền phải xuất phát từ trusted principal và policy.

### 18.10. Thử nhiều cách normalize đến khi signature đúng

Đây là cách né lỗi tạm thời nhưng phá ranh giới canonicalization. Hãy sửa hợp đồng signer/verifier/gateway, không sửa bằng một danh sách fallback không kiểm soát.

## 19. Bài tập thực hành

### Bài tập 1 — Tính expected tag từ vector có sẵn

Dùng Java 17 tính HMAC-SHA256 cho key 20 byte `0x0b` và message ASCII `Hi There`. So sánh byte tag với vector RFC 4231. Encode tag bằng Base64URL và kiểm tra decoder `SignatureEncodingV1` round-trip.

### Bài tập 2 — Tạo verifier cho request JSON

Lấy request mẫu `POST /v1/orders/42?dryRun=false`. Cho secret 32 byte test cố định do bài test tự cấp. Tạo canonical bytes từ **request server nhìn thấy**, tính expected tag bằng `ExpectedHmacSha256.calculate` và so với presented signature. Đổi body một byte rồi xác minh tag cũ phải bị từ chối.

### Bài tập 3 — Negative tests canonicalization

Gửi lần lượt `/v1/orders/42/`, `/v1/%2E%2E/admin`, `tenant=A&tenant=B` và `a=1&&b=2`. Giải thích vì sao V1 từ chối **trước khi** coi chúng là một canonical request được hỗ trợ.

### Bài tập 4 — Key rotation

Tạo registry giả lập với k2 và k3, mỗi record có secret riêng; client ký bằng k2 rồi tự sửa key ID thành k3. Verifier phải chọn secret k3 và từ chối tag cũ. Sau đó ký đúng bằng k3 và thử một key bị revoked.

### Bài tập 5 — Replay đồng thời

Giả lập hai verifier nhận **cùng signed request** gần như đồng thời. Cho cả hai tính expected HMAC thành công, rồi dùng shared atomic nonce gate. Chứng minh tối đa một request được đi tiếp.

### Bài tập 6 — Gateway rewrite

Đặt gateway rewrite `/public/v1/orders` thành `/v1/orders`. So sánh canonical path tại client, gateway và backend, quyết định đúng vị trí verify. Test cả HTTP header duplicates và body JSON bị serialize lại.

### Bài tập 7 — Authentication và authorization

Client tenant A có tag HMAC hợp lệ tới `/v1/tenants/B/orders/42`. Hãy xây dựng test kiểm tra: signature đúng, timestamp/nonce hợp lệ, principal là A, nhưng authorization từ chối `DELETE` vì resource thuộc B.

## 20. Checklist triển khai expected signature

- [ ] Verifier nhận **request thực tế** ở trust boundary rõ ràng; không tin canonical string do client tự khai.
- [ ] HTTP parser/gateway kiểm tra framing, header duplicates, size, content encoding và các dạng nhập nhằng.
- [ ] Key ID được parse strict và tra **đúng một server-side record** đang được cho phép.
- [ ] MAC algorithm/encoding/version/audience được chọn theo server contract và key registry, không do caller tùy ý.
- [ ] Shared secret được giải mã đúng dạng lưu trữ, bảo vệ trong secret manager và không log.
- [ ] Method/path/query/header canonicalization có version, unit/golden tests và đồng nhất với router.
- [ ] SHA-256 body digest được **server tính lại** từ đúng raw body bytes; không tin digest header đơn lẻ.
- [ ] Canonical bytes dùng UTF-8, LF, thứ tự field và no-final-LF theo hợp đồng.
- [ ] `X-Signature` được parse đúng một giá trị, strict Base64URL không padding 43 ký tự cho HMAC-SHA256 full-tag.
- [ ] Verifier tính expected HMAC bằng `Mac`, so toàn bộ tag bytes bằng `MessageDigest.isEqual`.
- [ ] Không thử nhiều secret, nhiều thuật toán hay nhiều cách normalize để “cứu” chữ ký sai.
- [ ] Timestamp/nonce được HMAC bảo vệ; freshness window và clock skew kiểm tra rõ.
- [ ] Replay store shared, atomic put-if-absent, TTL bao phủ toàn bộ thời gian request còn hiệu lực.
- [ ] Key rotation/revocation có trạng thái, thời hạn, audit và cache invalidation chính xác.
- [ ] Gateway không thay signed semantics ngoài contract; metadata proxy chỉ tin khi do proxy đáng tin thiết lập.
- [ ] Tạo principal **sau xác thực**, authorization theo action/resource/tenant trước handler.
- [ ] Idempotency bảo vệ nghiệp vụ ngay cả khi caller retry bằng nonce mới.
- [ ] Có KAT RFC 4231, golden canonical bytes, signature format fuzz, tampering tests và e2e gateway tests.
- [ ] Logs/response không làm lộ secret, full sensitive signed requests, key registry hay body dữ liệu cá nhân.

## 21. Câu hỏi tự kiểm tra

1. **Expected signature lấy từ đâu?** Server tự tính bằng secret đáng tin và canonical request bytes từ request thực nhận.
2. **Presented signature có được tin khi parse thành công không?** Không; cần so nó với expected tag và kiểm tra các chính sách khác.
3. **Có thể dùng `X-Canonical-Request` của client để tính expected không?** Không nếu chưa kiểm chứng nó chính xác với request mà handler sẽ xử lý.
4. **Tại sao body digest phải tính lại tại server?** Để phát hiện body bị sửa nhưng digest khai trong header vẫn giữ nguyên.
5. **HMAC-SHA256 expected tag dài bao nhiêu?** 32 byte đầy đủ; Base64URL không padding có 43 ký tự.
6. **Vì sao nên so byte thay vì chuỗi?** Để loại bỏ khác biệt biểu diễn và dùng so sánh phù hợp với kết quả mật mã.
7. **Có thể thử nhiều khóa đến khi HMAC khớp không?** Không nên. Key ID phải xác định một record/secret theo policy rõ.
8. **Nếu key bị revoke nhưng expected tag khớp thì sao?** Từ chối do credential không còn được cho phép.
9. **Vì sao chữ ký đúng vẫn có thể là replay?** Vì cùng request/canonical bytes và secret sẽ cho cùng HMAC, nên cần timestamp/nonce store.
10. **Khi nào được ghi nonce vào replay store?** Sau khi đã xác minh HMAC hợp lệ và qua kiểm tra freshness thích hợp.
11. **Proxy đổi path có ảnh hưởng expected signature không?** Có nếu client ký representation khác với verifier đang dùng.
12. **HMAC đúng có chứng minh quyền xóa tài nguyên của tenant khác không?** Không; phải authorization theo principal và resource.
13. **Vì sao cần golden tests của canonical bytes?** Để phân biệt lỗi HMAC primitive với lỗi chuẩn hóa request hoặc proxy.
14. **Thuật toán MAC do client tự chọn được không?** Không; do server contract và key record cho phép.
15. **Thay một unsigned header tracing có nhất thiết làm MAC khác không?** Không; chỉ các thành phần nằm trong canonical request mới được HMAC ràng buộc.
16. **Một request có nonce mới nhưng cùng business event đã xử lý thì sao?** Replay gate có thể cho qua, nhưng idempotency phải ngăn tác động trùng.

## 22. Tài liệu tham khảo

- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Công thức và nguyên lý HMAC.
- **RFC 4231 — Identifiers and Test Vectors for HMAC-SHA-224/256/384/512.** Known-answer tests cho thuật toán HMAC.
- **NIST FIPS 198-1 — The Keyed-Hash Message Authentication Code (HMAC).** Tham chiếu cơ chế HMAC.
- **RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax.** Nền tảng URI path, query và percent-encoding.
- **RFC 9110 / RFC 9112 — HTTP Semantics / HTTP/1.1.** Header fields, message semantics và parsing liên quan.
- **Java SE 17 — `javax.crypto.Mac`, `javax.crypto.spec.SecretKeySpec`, `java.security.MessageDigest`, `java.util.Base64`.** API Java tạo expected HMAC và kiểm tra tag byte.

**Kết luận:** **Tính expected signature là bước verifier tự chứng minh rằng request thực nhận phù hợp với một tag HMAC được tạo bằng secret của credential hợp lệ.** Điều cốt yếu không phải chỉ gọi `Mac.doFinal`, mà là chọn key đáng tin, tái tạo đúng canonical bytes, hash đúng raw body, strict-decode presented signature và so toàn bộ byte tag. Sau khi MAC khớp vẫn cần kiểm tra timestamp/nonce, key lifecycle, mapping gateway/router và authorization trước khi thực thi nghiệp vụ.
