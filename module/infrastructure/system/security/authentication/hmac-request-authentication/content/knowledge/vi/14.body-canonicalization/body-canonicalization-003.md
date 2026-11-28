# Empty body trong body canonicalization của HMAC request authentication

**Empty body** là trường hợp HTTP request có **nội dung dài đúng 0 byte** sau khi lớp HTTP đã xử lý phần đóng khung truyền tải (message framing). Với cơ chế xác thực HTTP request bằng HMAC, “không có byte body” vẫn là một dữ kiện cần được **định nghĩa, ký và xác minh**. Nếu client bỏ qua body digest còn server ngầm thay bằng một giá trị khác, hai phía sẽ tính ra canonical request khác nhau; nếu server không kiểm tra body rỗng thật sự, request có chữ ký đúng có thể được xử lý trên nội dung mà client không hề ký.

Bài **Empty body** thuộc chương **Body canonicalization**, module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Module hướng dẫn thiết kế xác thực HTTP request với **shared secret** và **canonical request** chứa method, URI, signed headers hoặc body theo hợp đồng ký, đồng thời kiểm tra timestamp/nonce chống replay, quản lý key rotation, thử nghiệm proxy/gateway và tách xác thực khỏi phân quyền. Chủ đề của bài là **quy ước canonical cho body 0 byte**, không phải một giao thức HMAC chuẩn có sẵn trong Java.

**Nguyên tắc:** Body 0 byte **vẫn có giá trị SHA-256 xác định**; hệ thống không được tự thay nó bằng chuỗi `null`, `{}`, một dấu cách, giá trị header trống hoặc kết quả “không hash”. Chính sách ký phải bảo đảm verifier kiểm tra đúng **byte thực nhận** trước khi cho phép nghiệp vụ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt body dài 0 byte với body JSON `null`, `{}`, `""`, chuỗi khoảng trắng và body bị mất do middleware đọc stream.
2. Tính đúng `SHA-256(empty bytes)` và đưa digest của body rỗng vào canonical request được **HMAC-SHA256** ký.
3. Giải thích vì sao `Content-Length: 0`, không có `Content-Length` và HTTP chunked/HTTP/2 không nhất thiết tạo các đầu vào HMAC khác nhau khi **message content** đều dài 0 byte.
4. Định nghĩa chính sách cho trường hợp thiếu/present `Content-Type`, `Content-Encoding`, digest header và cách verifier từ chối dữ liệu nhập nhằng.
5. Viết ví dụ Java 17 với `HttpRequest.BodyPublishers.noBody()`, `MessageDigest`, `Mac`, thời gian test cố định và nonce store mô phỏng.
6. Thiết kế kiểm thử request qua proxy/gateway, replay, key rotation, idempotency và phân quyền.

## 2. Body dài 0 byte thực sự có nghĩa gì?

Xét endpoint đánh dấu một tín hiệu hoạt động, không cần JSON payload:

~~~http
POST /v1/heartbeats?probe=primary HTTP/1.1
Host: api.example.test
Content-Length: 0
X-Client-Id: monitor-42
~~~

Request trên có body dài **0 byte**, nếu được HTTP parser tiếp nhận hợp lệ và không có message content theo framing. Các chuỗi sau thì **không** giống body rỗng:

| Dữ liệu phía ứng dụng gửi | Byte body khi dùng UTF-8 | Số byte | Có phải empty body? |
| --- | --- | ---: | --- |
| Không gửi nội dung | `byte[0]` | **0** | **Có**. |
| Chuỗi text rỗng được chuyển thành byte | `"".getBytes(UTF_8)` | **0** | **Có**. |
| Một khoảng trắng | `20` (hex) | 1 | Không. |
| Một dấu xuống dòng LF | `0A` (hex) | 1 | Không. |
| JSON `null` | `6E 75 6C 6C` | 4 | Không. |
| JSON `{}` | `7B 7D` | 2 | Không. |
| JSON `[]` | `5B 5D` | 2 | Không. |
| JSON string rỗng `""` | `22 22` | 2 | Không. |
| BOM UTF-8 ở đầu, không có ký tự khác | `EF BB BF` | 3 | Không. |

**Ý nghĩa nghiệp vụ khác dữ liệu byte:** Một controller có thể diễn giải body rỗng là “không cập nhật trường nào”, hoặc báo lỗi vì endpoint yêu cầu JSON; đó là chính sách ứng dụng. Ở lớp HMAC, câu hỏi đầu tiên đơn giản hơn: **bao nhiêu byte đã được nhận và hash chính xác những byte nào?**

### 2.1. “Không có body” và “body rỗng” có giống nhau khi ký?

Hợp đồng ký có thể quyết định coi **không có message content** và **message content dài 0 byte** là cùng một representation để ký. Ví dụ, sau khi HTTP stack xử lý request hợp lệ:

~~~text
No request content        -> byte[] length = 0
Explicit zero-byte body   -> byte[] length = 0
SHA256 của cả hai         -> cùng một digest
~~~

**Đây là một lựa chọn của hợp đồng**, không phải quy tắc rằng mọi HTTP API phải đồng nhất các trường hợp ở tầng ứng dụng. Nếu nghiệp vụ cần phân biệt **một header có xuất hiện hay không**, hoặc phân biệt body publisher “không có” với một dạng message khác, phải mô tả và ký thêm trạng thái liên quan theo cách có thể xác minh tại server.

Ví dụ trong bài chọn **zero-byte representation**: verifier chỉ chấp nhận body dài 0 byte, bất kể HTTP/1.1 có `Content-Length: 0` hay framing hợp lệ khác khiến HTTP parser đưa ra cùng 0 byte. Hợp đồng **không ký trực tiếp Content-Length**, vì header framing có thể được HTTP stack/proxy xác định lại; điều đó **không** cho phép bỏ qua kiểm tra framing an toàn.

### 2.2. Đừng nhầm với quy tắc body của response

HTTP response `204 No Content` hoặc response cho `HEAD` có quy tắc truyền nội dung riêng. Bài này bàn về **request content**, nên không suy ra rằng request method `GET` chắc chắn có body 0 byte, hay `POST` luôn phải chứa JSON. Nếu API yêu cầu một method/route không có body, cần **kiểm tra body length thực tế** tại verifier.

## 3. SHA-256 của empty body là giá trị cố định

SHA-256 của **0 byte** (chuỗi đầu vào rỗng, không phải ký tự `0`, `\n` hay chữ `null`) được biết trước:

~~~text
SHA256(empty byte array), hexadecimal lowercase:
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Digest có **32 byte = 256 bit**, biểu diễn hex thành **64 ký tự**. Đây là **test vector công khai**, hoàn toàn không chứa secret.

Java:

~~~java
import java.security.MessageDigest;
import java.util.HexFormat;

byte[] emptyBody = new byte[0];
byte[] sha256 = MessageDigest.getInstance("SHA-256").digest(emptyBody);
String emptyDigest = HexFormat.of().formatHex(sha256);

assert emptyDigest.equals(
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
);
~~~

**Không nhầm body hash với chữ ký HMAC:**

~~~text
bodyDigest = SHA256(bodyBytes)                      // Ai cũng tính được
canonical  = Version + Method + URI + Headers
             + x-content-sha256:bodyDigest
tag        = HMAC_SHA256(sharedSecret, UTF8(canonical))
~~~

Nếu client chỉ gửi:

~~~http
X-Content-SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

thì đó **không phải bằng chứng xác thực**. Kẻ tấn công có thể tính SHA-256 của bất kỳ body nào và tự sửa header. Header digest chỉ được HMAC **bảo vệ khi có mặt trong canonical request** và verifier tính lại từ body bytes thực nhận.

### 3.1. Vì sao không bỏ dòng body hash khi body rỗng?

Một thiết kế dễ sai:

~~~text
if (body.length > 0):
    canonical += "x-content-sha256:" + SHA256(body)
else:
    // Bỏ qua body hash
~~~

Khi hai phía không cùng phân loại “body có mặt” và “body không có mặt”, canonical sẽ khác. Cách này còn tạo hai kiểu hợp đồng mơ hồ mà đối thủ có thể khai thác qua header, parser hoặc gateway.

**Khuyến nghị cho hợp đồng mẫu:** luôn đưa dòng `x-content-sha256:<digest>` vào canonical. Với body 0 byte, digest là giá trị cố định nêu trên. Đồng thời **kiểm tra chính xác body length = 0** nếu endpoint chỉ nhận empty body. Không được suy ra body rỗng chỉ vì header digest công bố hash rỗng.

## 4. Content-Length, Transfer-Encoding và HTTP/2 không phải body

Một message body rỗng có thể được biểu diễn qua các cách đóng khung truyền tải:

~~~http
POST /v1/heartbeats?probe=primary HTTP/1.1
Host: api.example.test
Content-Length: 0
~~~

Hoặc, trong một kết nối mà quy tắc framing cho phép, body được truyền bằng **chunked transfer coding** với chunk kết thúc ngay:

~~~http
POST /v1/heartbeats?probe=primary HTTP/1.1
Host: api.example.test
Transfer-Encoding: chunked

0

~~~

Các byte `0`, `CRLF` của **chunk framing** không phải byte ứng dụng phải đưa vào SHA-256(body), nếu hợp đồng ký trên **message content sau khi loại bỏ transfer framing**. Trên HTTP/2, việc không có DATA bytes và sử dụng END_STREAM cũng có thể cho message content dài 0 byte; số frame truyền tải không phải đầu vào HMAC.

| Tình huống | Body bytes sau HTTP parser hợp lệ | HMAC canonical theo hợp đồng mẫu |
| --- | --- | --- |
| `Content-Length: 0` | 0 byte | SHA-256(empty) cố định. |
| Không có `Content-Length`, request framing xác định không có content | 0 byte | SHA-256(empty) cố định. |
| HTTP/1.1 chunked kết thúc ngay | 0 byte | SHA-256(empty) cố định. |
| HTTP/2 kết thúc stream, không có DATA content | 0 byte | SHA-256(empty) cố định. |
| `Content-Length: 2` và body là `{}` | 2 byte | **Từ chối** theo policy empty body. |
| Proxy tự thêm byte whitespace vào content | Ít nhất 1 byte | **Từ chối**, không tự trim trước hash. |

**Lưu ý bảo mật lớn:** `Content-Length`, `Transfer-Encoding` và một số tình huống không thống nhất parser có thể tạo lỗi **HTTP request smuggling**. Không được cố tính HMAC để “chữa” request có framing mâu thuẫn, ví dụ đầu vào HTTP/1.1 bị parser cho là có cả hai cách xác định body không nhất quán. **Ingress phải reject framing mơ hồ, header trùng nhạy cảm và dữ liệu thừa** theo chính sách HTTP stack, trước khi đẩy request cho verifier hay backend.

### 4.1. Content-Encoding lại là chuyện khác

**Content-Encoding: gzip** nói đến representation của content, **khác** với `Transfer-Encoding: chunked`. Một biểu diễn gzip của nội dung logic rỗng có thể vẫn có **nhiều byte nén**. Nếu client băm byte gzip còn verifier giải nén rồi băm 0 byte, tag sẽ khác.

Hợp đồng mẫu **không hỗ trợ content coding**: `Content-Encoding` phải **vắng mặt**, không được gửi `gzip` hoặc một giá trị khác. Verifier kiểm tra vắng mặt trước khi xác nhận empty body. Nếu ứng dụng khác cần gzip, nó phải định nghĩa có ký **encoded bytes** hay **decoded bytes**, vị trí giải nén, giới hạn tài nguyên và cách bảo vệ header quyết định representation.

## 5. Content-Type: vắng mặt hay có giá trị?

`Content-Type` diễn tả loại representation nếu content được gửi, nhưng HTTP không bắt buộc mọi request có empty body phải kèm một header nhất định. Những yêu cầu sau có thể được ứng dụng diễn giải khác nhau:

~~~http
POST /v1/heartbeats?probe=primary HTTP/1.1
Content-Length: 0
~~~

~~~http
POST /v1/heartbeats?probe=primary HTTP/1.1
Content-Length: 0
Content-Type: application/json
~~~

Ở cả hai request, body vẫn có thể là 0 byte. **Có/không có Content-Type là metadata**, không làm xuất hiện byte body.

Trong bài chọn chính sách **rất chặt cho endpoint heartbeat**:

- Body phải **dài đúng 0 byte**.
- `Content-Type` phải **vắng mặt**; nếu client gửi `Content-Type: application/json` cũng bị từ chối, dù body rỗng.
- `Content-Encoding` phải **vắng mặt**.
- Dòng canonical chứa các marker nội bộ **`body-state:empty`**, **`content-type:absent`** và **`content-encoding:absent`**. Những dòng này là **giá trị được hợp đồng xác định**, không phải header mà client được tự khai báo.
- Header `X-Content-SHA256` **bắt buộc** chứa đúng SHA-256 của 0 byte; verifier xác minh header này và body thực nhận.

Đây là **một lựa chọn thiết kế của bài học**, **không phải quy tắc chung** yêu cầu API nào có body rỗng cũng phải bỏ `Content-Type`. Nếu API cần chấp nhận `Content-Type: application/json` khi body 0 byte, hãy ghi rõ lựa chọn đó trong contract, kiểm tra chính xác giá trị trên server và đưa trạng thái/value tương ứng vào canonical.

### 5.1. Không ký “absent” rồi bỏ qua kiểm tra hiện diện

Một lỗi thiết kế nguy hiểm:

~~~text
canonical có "content-type:absent"
server KHÔNG kiểm tra request có Content-Type thật hay không
backend vẫn dùng Content-Type nếu client gửi tới
~~~

Khi đó kẻ tấn công có thể thêm header ảnh hưởng cách backend parse mà HMAC vẫn hợp lệ, vì marker `absent` không phản ánh request thật. Do đó mọi marker “vắng mặt” chỉ an toàn khi verifier **kiểm tra thuộc tính vắng mặt ở trust boundary** và router/backend không được ghi đè chính sách sau xác thực.

## 6. Hợp đồng canonical request: HMAC-EMPTY-BODY-V1

Để có một bài toán rõ ràng, định nghĩa endpoint:

~~~text
Method          = POST
Raw target      = /v1/heartbeats?probe=primary
Audience        = monitoring-api
Body            = đúng 0 byte
Content-Type    = vắng mặt
Content-Encoding= vắng mặt
~~~

Client gửi các header ứng dụng:

~~~http
POST /v1/heartbeats?probe=primary HTTP/1.1
Host: api.example.test
X-Client-Id: monitor-42
X-Key-Id: key-2026-11
X-Timestamp: <epoch-seconds>
X-Nonce: <32-lowercase-hex>
X-Content-SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
X-Signature: <base64-hmac-sha256-full-tag>
Content-Length: 0
~~~

Các giá trị `<...>` là placeholder dùng để mô tả format. `X-Signature` và `Content-Length` **không nằm trong canonical**; chữ ký không thể tự ký chính nó, còn `Content-Length` là framing được xử lý riêng tại ingress.

Canonical string chính xác cho hợp đồng mẫu:

~~~text
HMAC-EMPTY-BODY-V1
POST
/v1/heartbeats?probe=primary
audience:monitoring-api
body-state:empty
content-encoding:absent
content-type:absent
x-client-id:monitor-42
x-key-id:key-2026-11
x-timestamp:<epoch-seconds>
x-nonce:<32-lowercase-hex>
x-content-sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

**Quy tắc byte**:

1. Nối các dòng theo **đúng thứ tự** trên bằng **LF (byte 0A)**, không có LF ở cuối; mã hóa UTF-8.
2. Method bắt buộc là **`POST` viết hoa** và raw target phải khớp route và query thực thi.
3. Audience `monitoring-api` lấy từ cấu hình dịch vụ đáng tin; không tin `X-Forwarded-Host` do client/proxy ngoài tự khai.
4. Ba dòng `body-state:empty`, `content-encoding:absent`, `content-type:absent` là **policy assertions**, và verifier kiểm tra **đúng** body rỗng/vắng header.
5. `x-client-id` và `x-key-id` là giá trị header đã kiểm tra; server chọn đúng secret theo client/key ID, trạng thái hiệu lực và audience.
6. `x-timestamp` là epoch seconds ASCII thập phân chính tắc; `x-nonce` là 16 byte ngẫu nhiên mã hóa 32 hex chữ thường. Server kiểm tra timestamp trong cửa sổ và claim nonce nguyên tử sau HMAC.
7. `x-content-sha256` có đúng **64 ký tự hex chữ thường** từ SHA-256 của body bytes thực nhận, kể cả khi body có 0 byte.
8. Ký toàn bộ canonical bằng **HMAC-SHA256** với secret đủ entropy; tag đầy đủ **32 byte**, truyền bằng Base64 chuẩn có padding (thường 44 ký tự).

**Không** cho phép client tự chọn bỏ dòng body hash, tự đổi `body-state`, thay version hoặc khai thuật toán yếu khi HMAC thất bại. Với hợp đồng khác, phải dùng version/policy khác có test vectors rõ ràng.

### 6.1. Tại sao ký thêm `body-state:empty` khi đã có digest?

Về mặt mật mã, SHA-256(empty) đã ràng buộc byte content là rỗng theo giả định về hàm băm; marker `body-state:empty` là **domain/policy marker** giúp mô tả ngữ nghĩa endpoint rõ ràng, không tăng “số bit an toàn” của HMAC. Lợi ích thực tế là tránh dùng lại cùng một canonical template cho endpoint cho phép body có nội dung nếu quy tắc body khác nhau.

Nhưng marker **không thay được** kiểm tra request body length thực tế. Một verifier luôn ký giá trị literal `empty` mà vẫn cho backend đọc body tùy ý là **sai thiết kế**.

## 7. Java 17: ký và xác minh POST không có body

Đoạn Java sau là **chương trình test tự chứa**. Client và verifier trong cùng một tiến trình dùng secret 32 byte được sinh bằng `SecureRandom` **chỉ cho mục đích minh họa**; trong hệ thống thật, secret phải được cấp an toàn qua secret manager cho cả hai bên. Chương trình tạo `HttpRequest` bằng `BodyPublishers.noBody()` nhưng **không gửi request ra mạng**.

Ví dụ chủ động kiểm tra: empty digest chuẩn, chữ ký hợp lệ, body bị thêm `{}`, Content-Type xuất hiện không đúng policy, URI thay đổi, replay, timestamp quá cũ và quá xa tương lai.

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class EmptyBodyHmacExample {
    private static final String METHOD = "POST";
    private static final String TARGET =
        "/v1/heartbeats?probe=primary";
    private static final String CLIENT_ID = "monitor-42";
    private static final String KEY_ID = "key-2026-11";
    private static final String EMPTY_SHA256 =
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final long PAST_SECONDS = 300;
    private static final long FUTURE_SECONDS = 60;

    record SignedRequest(
        String method, String rawTarget, String clientId, String keyId,
        String timestamp, String nonce, String bodyDigest,
        String signature, boolean contentTypePresent,
        boolean contentEncodingPresent, byte[] receivedBody
    ) {}

    // Chỉ minh họa một JVM: không có TTL, không chia sẻ qua replica.
    static final class DemoNonceStore {
        private final Set<String> used =
            ConcurrentHashMap.newKeySet();

        boolean claim(String clientId, String nonce) {
            return used.add(clientId + ":" + nonce);
        }
    }

    static String sha256Hex(byte[] data)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(data)
        );
    }

    static byte[] hmacSha256(byte[] secret, String canonical)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8));
    }

    static String canonical(String method, String rawTarget,
            String clientId, String keyId, String timestamp,
            String nonce, String bodyDigest) {
        if (!METHOD.equals(method) || !TARGET.equals(rawTarget) ||
            !CLIENT_ID.equals(clientId) || !KEY_ID.equals(keyId) ||
            timestamp == null ||
            !timestamp.matches("[1-9][0-9]{0,18}") ||
            nonce == null || !nonce.matches("[0-9a-f]{32}") ||
            !EMPTY_SHA256.equals(bodyDigest)) {
            throw new IllegalArgumentException("Sai canonical policy");
        }
        return String.join("\n",
            "HMAC-EMPTY-BODY-V1",
            method,
            rawTarget,
            "audience:monitoring-api",
            "body-state:empty",
            "content-encoding:absent",
            "content-type:absent",
            "x-client-id:" + clientId,
            "x-key-id:" + keyId,
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "x-content-sha256:" + bodyDigest
        );
    }

    static SignedRequest sign(byte[] secret, Clock clientClock)
            throws GeneralSecurityException {
        byte[] body = new byte[0];
        String digest = sha256Hex(body);
        byte[] nonceBytes = new byte[16];
        RANDOM.nextBytes(nonceBytes);
        String nonce = HexFormat.of().formatHex(nonceBytes);
        String timestamp = Long.toString(
            clientClock.instant().getEpochSecond()
        );
        String canonical = canonical(
            METHOD, TARGET, CLIENT_ID, KEY_ID,
            timestamp, nonce, digest
        );
        String signature = Base64.getEncoder().encodeToString(
            hmacSha256(secret, canonical)
        );
        return new SignedRequest(
            METHOD, TARGET, CLIENT_ID, KEY_ID,
            timestamp, nonce, digest, signature,
            false, false, body
        );
    }

    // Demo verifier: production phải đọc các field từ HTTP parser đáng tin.
    static boolean verify(SignedRequest req, byte[] secret,
            Clock serverClock, DemoNonceStore nonces)
            throws GeneralSecurityException {
        if (req == null || req.receivedBody() == null ||
            req.receivedBody().length != 0 ||
            req.contentTypePresent() || req.contentEncodingPresent() ||
            req.signature() == null) {
            return false;
        }

        // Dùng body bytes thực nhận, KHÔNG mặc định hash rỗng vô điều kiện.
        String actualDigest = sha256Hex(req.receivedBody());
        if (!actualDigest.equals(req.bodyDigest())) {
            return false;
        }

        final String canonical;
        try {
            canonical = canonical(
                req.method(), req.rawTarget(),
                req.clientId(), req.keyId(),
                req.timestamp(), req.nonce(), actualDigest
            );
        } catch (IllegalArgumentException invalidFields) {
            return false;
        }

        final long timestamp;
        try {
            timestamp = Long.parseLong(req.timestamp());
        } catch (NumberFormatException invalidOrOverflow) {
            return false;
        }
        long now = serverClock.instant().getEpochSecond();
        if (timestamp < now - PAST_SECONDS ||
            timestamp > now + FUTURE_SECONDS) {
            return false;
        }

        final byte[] suppliedTag;
        try {
            suppliedTag = Base64.getDecoder().decode(req.signature());
        } catch (IllegalArgumentException invalidBase64) {
            return false;
        }
        if (suppliedTag.length != 32 ||
            !Base64.getEncoder().encodeToString(suppliedTag)
                .equals(req.signature())) {
            return false;
        }
        byte[] expectedTag = hmacSha256(secret, canonical);
        if (!MessageDigest.isEqual(expectedTag, suppliedTag)) {
            return false;
        }

        // Nonce chỉ được claim SAU khi HMAC hợp lệ.
        return nonces.claim(req.clientId(), req.nonce());
    }

    public static void main(String[] args) throws Exception {
        byte[] secret = new byte[32]; // Secret test, không dùng production.
        RANDOM.nextBytes(secret);
        Clock fixed = Clock.fixed(
            Instant.parse("2026-11-28T02:00:00Z"), ZoneOffset.UTC
        );
        SignedRequest request = sign(secret, fixed);

        if (!EMPTY_SHA256.equals(sha256Hex(new byte[0]))) {
            throw new AssertionError("SHA-256 empty test vector sai");
        }

        HttpRequest httpRequest = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + TARGET))
            .header("X-Client-Id", request.clientId())
            .header("X-Key-Id", request.keyId())
            .header("X-Timestamp", request.timestamp())
            .header("X-Nonce", request.nonce())
            .header("X-Content-SHA256", request.bodyDigest())
            .header("X-Signature", request.signature())
            .POST(HttpRequest.BodyPublishers.noBody())
            .build(); // Ví dụ không gửi HTTP request.
        if (!METHOD.equals(httpRequest.method())) {
            throw new AssertionError("Method trên client không khớp");
        }

        if (!verify(request, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Empty body hợp lệ phải verify được");
        }

        // Một JSON object 2 byte KHÔNG phải body rỗng.
        SignedRequest changedBody = new SignedRequest(
            request.method(), request.rawTarget(),
            request.clientId(), request.keyId(), request.timestamp(),
            request.nonce(), request.bodyDigest(), request.signature(),
            false, false, "{}".getBytes(StandardCharsets.UTF_8)
        );
        if (verify(changedBody, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Body {} phải bị từ chối");
        }

        SignedRequest withContentType = new SignedRequest(
            request.method(), request.rawTarget(),
            request.clientId(), request.keyId(), request.timestamp(),
            request.nonce(), request.bodyDigest(), request.signature(),
            true, false, new byte[0]
        );
        if (verify(withContentType, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Content-Type xuất hiện phải bị reject");
        }

        SignedRequest changedTarget = new SignedRequest(
            request.method(), "/v1/heartbeats?probe=other",
            request.clientId(), request.keyId(), request.timestamp(),
            request.nonce(), request.bodyDigest(), request.signature(),
            false, false, new byte[0]
        );
        if (verify(changedTarget, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Thay URI phải bị từ chối");
        }

        DemoNonceStore replayStore = new DemoNonceStore();
        if (!verify(request, secret, fixed, replayStore) ||
            verify(request, secret, fixed, replayStore)) {
            throw new AssertionError("Replay nonce phải bị từ chối");
        }

        Clock late = Clock.offset(fixed, Duration.ofSeconds(301));
        if (verify(request, secret, late, new DemoNonceStore())) {
            throw new AssertionError("Timestamp quá cũ phải bị từ chối");
        }
        SignedRequest future = sign(
            secret, Clock.offset(fixed, Duration.ofSeconds(61))
        );
        if (verify(future, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Timestamp quá xa tương lai phải bị từ chối");
        }

        System.out.println("PASS: empty body, HMAC, URI, replay, freshness");
    }
}
~~~

### 7.1. Phân tích ví dụ

- `BodyPublishers.noBody()` biểu đạt request body rỗng của Java HTTP client; `BodyPublishers.ofByteArray(new byte[0])` cũng cung cấp **0 byte content**. Không dựa vào việc builder có gửi/không gửi `Content-Length: 0` để xác định digest.
- `sha256Hex(new byte[0])` được kiểm tra bằng test vector SHA-256 công khai; **không** dùng `SHA256(UTF8("null"))` hoặc `SHA256(UTF8("{}"))` thay thế.
- `canonical` luôn có dòng `x-content-sha256` và marker `body-state:empty`, trong khi `verify` **kiểm tra body thực nhận có length = 0**, cả `Content-Type` lẫn `Content-Encoding` vắng mặt.
- `MessageDigest.isEqual` dùng so sánh tag HMAC dạng byte; Base64 được decode và kiểm tra đúng **32 byte** theo policy full HMAC-SHA256.
- `Clock.fixed` chỉ để test; production cần đồng hồ server được đồng bộ. `DemoNonceStore` chỉ chống nonce trùng trong **một JVM**, không có TTL và không chia sẻ giữa replica.
- `CLIENT_ID`, `KEY_ID` và secret được cố định/sinh nội bộ để làm rõ luồng. Production tra secret từ key manager theo identity/key ID, kiểm tra key active/revoked và audience, không dùng chung một key bí mật cho mọi client.

### 7.2. Những việc còn thiếu ở production

Hàm `verify` nhận một record test, **không phải HTTP request parser**. Trên server thật cần bảo đảm:

1. Header, method và raw URI đến từ HTTP parser tại **trust boundary đáng tin**, không từ record do client tự dựng.
2. Từ chối **header trùng/mơ hồ** (đặc biệt `Content-Type`, `Content-Encoding`, `X-Content-SHA256`, `X-Timestamp`, `X-Nonce`, `X-Signature`) trước khi các hop gộp thành giá trị khác nhau.
3. Reject framing đáng ngờ (`Content-Length`/`Transfer-Encoding` xung đột, body thừa, request smuggling), áp dụng giới hạn thời gian và kích thước.
4. Trích xuất **body bytes thực nhận** trước khi parser nghiệp vụ hoặc middleware tự diễn giải/biến đổi; kiểm tra có đúng **0 byte** không.
5. Chọn đúng key theo `clientId + keyId`, kiểm tra trạng thái hiệu lực, audience và policy của method/route.
6. Claim nonce nguyên tử sau HMAC trên storage **dùng chung** và có TTL đến hết cửa sổ timestamp.
7. Thực thi **authorization** và idempotency của nghiệp vụ trước khi tạo side effect.

## 8. Những lỗi empty body thường gặp qua proxy/gateway

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy
    participant G as Trusted gateway
    participant V as HMAC verifier
    participant B as Backend
    C->>P: POST + empty content + digest + HMAC
    P->>G: Forward, có thể đổi framing/header
    G->>V: Message content 0 byte + signed fields
    V->>V: Kiểm tra body length, digest, HMAC, nonce
    alt Hợp lệ
        V->>B: Request/identity đã xác minh
        B->>B: Authorization + idempotency
    else Body khác 0 hoặc policy sai
        V-->>C: Từ chối request
    end
~~~

| Tình huống | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Gateway thêm `Content-Length: 0` | Framing thay đổi nhưng body vẫn 0 byte | Theo contract bài, không làm đổi body digest; kiểm tra framing hợp lệ. |
| HTTP/1.1 chunked rỗng chuyển sang HTTP/2 END_STREAM | Representation ở wire khác | Hash message content 0 byte sau framing, không hash chunk marker. |
| Proxy thêm `Content-Type: application/json` | Policy metadata vắng mặt không còn đúng | Reject, không âm thầm coi tương đương. |
| Proxy chuyển `Content-Encoding` thành gzip | Encoded content có thể không rỗng | Reject theo contract không hỗ trợ content coding. |
| Middleware sinh body `{}` cho request trống | Backend xử lý byte khác với byte client ký | Verify trên byte nhận trước biến đổi; reject hoặc dùng hợp đồng riêng cho phép transform. |
| Filter đọc hết body stream trước verifier | Verifier đọc 0 byte dù client đã gửi content | Đặt verifier trước parser hoặc dùng buffering/stream digest đáng tin; không mặc định EOF nghĩa là client gửi rỗng. |
| Proxy/ingress hiểu `Content-Length` và `Transfer-Encoding` khác nhau | Request smuggling, backend có thể đọc thêm byte ngoài vùng verify | Reject framing mâu thuẫn tại ingress, không chấp nhận dựa trên HMAC đơn lẻ. |
| Proxy đổi raw URI/query nhưng body vẫn rỗng | Có thể gọi tài nguyên/thao tác khác | Method và raw URI/query phải được ký, verify tại trust boundary. |
| Gateway dùng `X-Verified: true` từ client | Có thể bypass verifier | Xóa header không đáng tin; bảo vệ hop gateway→backend và chặn đường bypass. |
| Kẻ tấn công phát lại nguyên request | Empty digest và HMAC đều vẫn đúng | Timestamp/nonce store nguyên tử; idempotency nếu có side effect. |

**Một lỗi tinh vi:** Nếu verifier nhận `byte[0]` do một filter trước đó đã tiêu thụ body gốc, kết quả SHA-256(empty) **vẫn đúng** nhưng không phản ánh những byte backend có thể xử lý. Do đó trust boundary phải bảo đảm verifier và handler dùng **cùng message content representation**, hoặc một đối tượng body đã được xác minh không thể bị tráo.

## 9. Replay, key rotation và quyền hạn với request không có body

### 9.1. Không có body không có nghĩa request vô hại

Endpoint không có body vẫn có thể tạo side effect: gửi lệnh khởi động, chốt giao dịch, đổi trạng thái hoặc kích hoạt một workflow chỉ qua method + URI. Ví dụ:

~~~http
POST /v1/jobs/42/execute HTTP/1.1
Content-Length: 0
~~~

Body 0 byte không biến `POST` thành hành động chỉ đọc. Vì vậy phải ký **method, URI/query, identity, timestamp, nonce** và kiểm tra quyền theo tài nguyên/job; không chỉ ký hash rỗng vốn giống nhau cho mọi request.

### 9.2. Timestamp + nonce chống replay

Một canonical với empty body vẫn có giá trị HMAC khác nhau khi `x-timestamp` hoặc `x-nonce` thay đổi. Server dùng timestamp được ký để kiểm tra freshness, ví dụ tối đa 300 giây quá khứ và 60 giây tương lai theo **policy ứng dụng**, rồi **sau khi HMAC hợp lệ** claim nonce nguyên tử trong store chia sẻ.

TTL của nonce cần bao phủ **toàn bộ thời gian một timestamp còn được phép**. Với ví dụ `pastWindow = 300s` và `futureWindow = 60s`, một timestamp ở tương lai 60 giây có thể còn được chấp nhận **khoảng 360 giây** tính từ lần đến đầu tiên; TTL cố định 60 giây là quá ngắn. Có thể lưu nonce đến ít nhất `signedTimestamp + pastWindow + safetyMargin` theo chính sách đồng hồ/storage.

Kẻ tấn công không cần biết key để **replay nguyên request còn hạn** nếu thiếu nonce store. HMAC chỉ bảo vệ sự toàn vẹn của các trường đã ký, không tự ngăn phát lại.

### 9.3. Retry và idempotency

Một client có thể gửi lại cùng ý định nghiệp vụ bằng **timestamp mới, nonce mới, chữ ký mới**. Replay detector khi đó nhận nonce khác và có thể chấp nhận cả hai request. Với endpoint có side effect, phải bổ sung **idempotency key** được ký và cơ chế lưu trạng thái nghiệp vụ nguyên tử. Body rỗng không làm mất nhu cầu này.

### 9.4. Key rotation

Verifier phải tra **shared secret** theo `(clientId, keyId)`, kiểm tra key active, audience, method/route scope, thuật toán và thời hạn. Trong giai đoạn chuyển đổi có thể chấp nhận key cũ và mới theo chính sách được server quy định, nhưng **không** thử ngẫu nhiên nhiều key, nhiều version hoặc bỏ body digest để chữ ký “có cơ hội khớp”. Key revoked phải bị từ chối dù timestamp còn mới.

### 9.5. Xác thực không phải phân quyền

HMAC đúng trên empty request xác nhận bên gửi có khả năng sử dụng secret và dữ liệu đã ký không bị sửa. Nó **không** cho phép client chạy mọi job, xóa dữ liệu tenant khác hoặc bỏ qua quota. Backend cần **authorization** riêng dựa trên client identity, scope, method, resource và tenant.

## 10. Ma trận kiểm thử empty body

Sử dụng secret test, đồng hồ test cố định và nonce khác nhau cho các ca độc lập. Với test replay, dùng lại nguyên timestamp/nonce/tag. Kết quả sau đây dựa trên **HMAC-EMPTY-BODY-V1** của bài, không phải hành vi bắt buộc của mọi API.

| Ca thử | Dữ liệu hoặc thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Empty body hợp lệ | `POST`, đúng URI, body 0 byte, Content-Type/Encoding vắng mặt | Digest SHA-256(empty), HMAC khớp, đi tiếp kiểm tra nonce/quyền. |
| SHA-256 test vector | `new byte[0]` | Hex đúng `e3b0c442...b855`, không phải chuỗi trống. |
| Không có Content-Length | Parser xác định hợp lệ body 0 byte | Cùng digest/canonical so với framing `Content-Length: 0`. |
| Content-Length bằng 0 | HTTP/1.1 framing hợp lệ | Cùng SHA-256(empty). |
| Chunked rỗng | Chunk kết thúc ngay, không có message content | Digest của 0 byte, không hash ký tự `0`/CRLF chunk framing. |
| HTTP/2 no DATA | Stream đóng không có content bytes | Digest của 0 byte. |
| Body là một dấu cách | `20` hex | Reject vì body length = 1. |
| Body là LF | `0A` hex | Reject vì body length = 1; không trim. |
| Body JSON `null` | 4 byte | Reject; không xem semantic “null” là 0 byte. |
| Body JSON `{}` hoặc `[]` | 2 byte | Reject, dù object/array rỗng về ngữ nghĩa. |
| Body JSON string `""` | 2 byte | Reject. |
| Content-Type xuất hiện | `Content-Type: application/json` với 0 byte | Reject theo policy minh họa yêu cầu vắng mặt. |
| Content-Encoding xuất hiện | `gzip` hoặc giá trị khác | Reject theo policy minh họa. |
| Header body hash thiếu | Không gửi `X-Content-SHA256` | Reject; không tự bỏ trường canonical. |
| Header body hash giả | Gửi một digest khác dù body 0 byte | Reject hash hoặc HMAC. |
| Header trùng | Hai `X-Content-SHA256` hoặc `X-Signature` | Reject tại parser/ingress đáng tin. |
| Base64 tag sai độ dài | Chỉ 8 hoặc 16 byte prefix HMAC | Reject vì contract full tag 32 byte. |
| Body được gateway thêm `{}` | Client ký 0 byte, backend nhận 2 byte | Reject, không “sửa” body để hợp lệ. |
| Framing mâu thuẫn | `Content-Length` và `Transfer-Encoding` bị diễn giải khác | Reject ở ingress trước business processing. |
| Đổi method hoặc URI | Thay POST thành DELETE hoặc query `probe=other` | HMAC/route policy sai, reject. |
| Replay tuần tự | Gửi lại nguyên timestamp, nonce và tag | Request sau bị từ chối. |
| Replay song song | Hai replica claim cùng nonce | Tối đa một claim thành công. |
| Retry nghiệp vụ | Cùng ý định, nonce mới, HMAC mới | Cần idempotency để tránh side effect trùng. |
| Key đã thu hồi | Digest/HMAC hợp lệ theo secret cũ | Reject theo policy key status. |
| Thiếu quyền | HMAC hợp lệ trên job/tenant ngoài scope | Authentication có thể PASS, authorization DENY. |

### Câu hỏi tự kiểm tra

1. Vì sao `SHA256(new byte[0])` không phải chuỗi hex rỗng?
2. `Content-Length: 0` khác gì so với body là byte `0x30` (chữ số “0”)? Trường hợp nào phải đưa vào SHA-256?
3. Hai request có cùng empty body hash nhưng method/URI khác nhau có nên có cùng chữ ký HMAC không? Vì sao?
4. `{}` và `null` có thể được framework xem là “rỗng về ý nghĩa” nhưng vì sao không được coi là empty body trong hợp đồng này?
5. Nếu gateway tự thêm Content-Type hoặc middleware đọc mất body, việc HMAC khớp cho empty digest có đủ an toàn không?
6. Vì sao cần nonce store dù timestamp còn trong cửa sổ và tag HMAC-SHA256 đúng?
7. Với POST không có body nhưng chạy một workflow, cần những kiểm tra authorization/idempotency nào?

## 11. Checklist thiết kế và triển khai

- [ ] Định nghĩa **empty body = đúng 0 byte** trên message content representation được HTTP parser tin cậy cung cấp.
- [ ] Dùng **SHA-256 của byte array rỗng**, không thay bằng null/{} hoặc bỏ trường body hash một cách tùy ý.
- [ ] Ký body digest **cùng method, raw URI/query, các signed headers, audience, timestamp/nonce và key ID** theo hợp đồng versioned.
- [ ] Chốt quy tắc cho `Content-Type` và `Content-Encoding`: absent/present có ý nghĩa gì và được verifier kiểm tra thực sự.
- [ ] Không đưa chunk/frame bytes hoặc framing headers tùy ý vào body digest; vẫn **reject framing mâu thuẫn/smuggling** ở ingress.
- [ ] Không tự trim whitespace, JSON parse/serialize lại hoặc coi stream bị middleware tiêu thụ là body client đã gửi 0 byte.
- [ ] Client serialize/xác nhận body 0 byte, có thể dùng `BodyPublishers.noBody()`; verify raw target mà HTTP client thực phát.
- [ ] Verifier tự đọc body bytes, kiểm tra length = 0, tính lại digest, dựng canonical đúng LF/UTF-8 và so sánh HMAC full tag.
- [ ] Key store tra client ID/key ID, kiểm tra thuật toán, audience, thời hạn, key rotation và revoke.
- [ ] Timestamp/nonce được ký; shared nonce store có atomic claim và TTL bao phủ cửa sổ; idempotency bảo vệ side effect.
- [ ] Reverse proxy/gateway không được thay content representation hoặc signed URI/header mà không có hợp đồng xác thực rõ ràng.
- [ ] Backend thực thi **authorization theo identity, action và resource**, không suy ra “body rỗng = hành động vô hại”.
- [ ] Có test vector SHA-256(empty), body dài 1/2/4 byte, content encoding, framing, replay, key rotation và HTTP protocol translation.

**Ghi nhớ:** Empty body không phải một “trường hợp bỏ qua xác thực”. Đó là **dãy 0 byte** với digest SHA-256 cố định `e3b0c442...b855`. Hợp đồng HMAC phải kiểm tra body thực nhận, đưa digest vào canonical request, ràng buộc method/URI/headers, và định nghĩa rõ metadata vắng mặt. Gateway không được âm thầm đổi representation; timestamp/nonce, quản lý key và phân quyền vẫn bắt buộc.
