# So sánh signature khi xác minh HTTP request bằng HMAC

Trong **HMAC request authentication**, việc nhận được header `X-Signature` không có nghĩa request đã được xác thực. Verifier phải **tự tạo lại canonical request từ dữ liệu HTTP thực nhận**, dùng **đúng shared secret** để tính **HMAC tag mong đợi**, giải mã chữ ký client gửi thành **tag bytes**, rồi so sánh **hai tag đầy đủ** bằng phép so sánh phù hợp với dữ liệu mật mã. Đó là trọng tâm của thao tác **so sánh signature**.

Bài thuộc chương **Xác minh request**, module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Phạm vi module là thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request ràng buộc method, URI, header hoặc body theo hợp đồng; thực hành xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt **authentication** với **authorization**. Bài học tập trung vào **bước so sánh signature**, đồng thời làm rõ những điều kiện phải thỏa mãn **trước và sau** phép so sánh.

**Tư tưởng cốt lõi:** So sánh HMAC không phải so sánh hai chuỗi văn bản tùy ý. Nó là kiểm tra **hai mảng byte có đúng độ dài tag do server quy định**: tag do client gửi sau khi decode và tag do server tính lại từ chính request được xử lý.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **encoded signature**, **decoded tag**, **body digest**, **canonical request bytes** và **expected tag**.
2. Giải thích vì sao phải kiểm tra **format, full tag length và canonical encoding** trước khi so sánh.
3. Dùng `MessageDigest.isEqual(byte[], byte[])` trong Java 17 thay cho kiểu so sánh kết thúc sớm hoặc so sánh prefix, hiểu cả **giới hạn của khái niệm constant-time**.
4. Dựng lại HMAC-SHA256 trên method, raw URI, signed headers, body digest, key ID, timestamp/nonce và so sánh tag **trên byte**.
5. Xác định thứ tự kiểm tra phù hợp để không claim nonce cho request giả, không xử lý nghiệp vụ trước xác thực, không mở đường downgrade khi key rotation.
6. Tạo bộ kiểm thử chữ ký hợp lệ, sai đầu/cuối tag, tag ngắn/dài, khác encoding, request bị thay đổi, replay và request thiếu quyền.

## 2. Chính xác chúng ta đang so sánh những gì?

Client gửi một request ví dụ:

~~~http
POST /v1/orders?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-11
X-Timestamp: <unix-epoch-seconds>
X-Nonce: <32-lowercase-hex-characters>
X-Content-SHA256: <64-lowercase-hex-characters>
X-Signature: <base64-standard-padded-hmac-sha256>

{"orderId":"ord-123","amount":50000}
~~~

Các chuỗi `<...>` là **placeholder**; request thật phải chứa giá trị cụ thể. Đối chiếu khái niệm:

| Đối tượng | Cách tạo | Kích thước/định dạng trong hợp đồng ví dụ | Có phải thứ đem so sánh HMAC? |
| --- | --- | --- | --- |
| Body bytes | Byte JSON thực gửi/nhận | `byte[]`, phụ thuộc request | Không; dùng để tính SHA-256. |
| Body digest | `SHA256(bodyBytes)` | 32 byte, biểu diễn 64 hex chữ thường | Không; nằm trong canonical. |
| Canonical request | Method + raw URI + các signed fields theo hợp đồng | Byte UTF-8; LF, không LF cuối | Không; là **thông điệp đầu vào** HMAC. |
| Shared secret | Key store cấp cho client và verifier | Ví dụ 32 byte ngẫu nhiên | Không; là **khóa** của HMAC, không gửi trên HTTP. |
| Expected tag | `HMAC_SHA256(secret, canonicalBytes)` phía verifier | **32 byte** | **Có**. |
| Supplied tag | Decode `X-Signature` phía client | **32 byte** nếu đúng contract | **Có**. |
| Encoded signature | Base64 chuẩn padded của supplied tag | **44 ký tự ASCII**, cuối một `=` | Không so sánh text thay cho tag bytes. |

Phép so sánh cuối cùng:

~~~text
expectedTag = HMAC_SHA256(secretBytes, UTF8(canonicalRequest))
suppliedTag = StrictBase64Decode(X-Signature)

ACCEPT_SIGNATURE =
    length(suppliedTag) == 32
    AND length(expectedTag) == 32
    AND secureEqual(expectedTag, suppliedTag)
~~~

**Tính chính xác của chữ ký chỉ bao phủ những trường đã được đưa vào canonical.** Nếu bỏ method hoặc path ra khỏi dữ liệu ký, phép so sánh đúng vẫn không phát hiện thay đổi ở phần bị bỏ sót.

## 3. Vì sao không dùng `Arrays.equals`, `String.equals` hay prefix comparison?

### 3.1. So sánh kết thúc sớm và quan sát thời gian

Một thuật toán so sánh không phù hợp với tag bí mật có thể:

~~~java
// KHÔNG KHUYẾN NGHỊ: dừng ở byte đầu tiên không khớp.
static boolean insecureEquals(byte[] expected, byte[] supplied) {
    if (expected.length != supplied.length) {
        return false;
    }
    for (int i = 0; i < expected.length; i++) {
        if (expected[i] != supplied[i]) {
            return false;
        }
    }
    return true;
}
~~~

Nếu thời gian chạy phụ thuộc **vị trí byte đầu tiên sai**, một đối thủ đo nhiều lần có thể cố suy luận prefix khớp thông qua sai lệch thời gian. Trên mạng công cộng, nhiễu lớn, nhưng thiết kế an toàn **không nên chủ động tạo tín hiệu phụ thuộc nội dung secret** khi có phương án tốt hơn.

Trong Java 17, dùng:

~~~java
import java.security.MessageDigest;

// Hai tag đã được kiểm tra đúng 32 byte ở bước trước.
boolean signatureMatches =
    MessageDigest.isEqual(expectedTag, suppliedTag);
~~~

Hàm `MessageDigest.isEqual` được thiết kế cho so sánh byte trong ngữ cảnh mật mã, tránh kiểu trả về sớm theo vị trí byte không khớp. **Không suy ra toàn bộ HTTP verifier là constant-time**: độ dài không hợp lệ, lỗi Base64, key lookup, body parser, router, timestamp và nonce store có các nhánh/thời gian xử lý khác nhau. Với hợp đồng HMAC-SHA256 full tag, hãy **kiểm tra cả hai đều dài 32 byte** trước phép so sánh.

### 3.2. Không dùng `String.equals` để so sánh Base64

~~~java
// Tránh: so sánh chữ ký như text thay cho raw tag bytes.
boolean equalsText = expectedBase64.equals(receivedBase64);
~~~

Vấn đề có hai mặt. Thứ nhất, `String.equals` không được cam kết là phép so sánh bảo mật không phụ thuộc vị trí sai; thứ hai, Base64 có thể có nhiều cách biểu diễn text nếu decoder/hợp đồng cho phép padding tùy ý hoặc pad bits không canonical. Hợp đồng ví dụ chọn **một định dạng duy nhất**, decode nó và **so sánh trên byte**.

### 3.3. Lỗi đặc biệt nghiêm trọng: so sánh chỉ theo độ dài client gửi

~~~java
// SAI: client tự gửi 1 byte thì server chỉ so 1 byte.
// boolean ok = Arrays.equals(
//     Arrays.copyOf(expectedTag, suppliedTag.length), suppliedTag);

// SAI: cắt expected HMAC thành một prefix tùy ý để "tương thích".
// byte[] expectedPrefix = Arrays.copyOf(expectedTag, 8);
~~~

Nếu được phép chọn tag length rất ngắn, attacker có thể thử tag cho tới khi prefix khớp với xác suất cao hơn nhiều so với tag đầy đủ. Contract **không chấp nhận việc client tự chọn tag length**. HMAC-SHA256 toàn phần có 32 byte; nếu một giao thức chủ động dùng **truncated MAC**, độ dài đó phải được quyết định **trước** bằng phiên bản thuật toán và policy server, phù hợp phân tích bảo mật, không phải thay đổi linh động khi request đến.

### 3.4. Không dùng digest không khóa thay HMAC

~~~text
SAI:
    SHA256(canonicalRequest) == suppliedSignature

ĐÚNG theo hợp đồng:
    HMAC_SHA256(sharedSecret, canonicalRequest) == suppliedTag
~~~

Một SHA-256 không có khóa chỉ chứng minh hai bên có cùng **dữ liệu**, không xác minh người gửi có quyền sử dụng secret. Ngược lại, mã hóa HMAC tag bằng Base64 hay hex **không thêm khóa** và không tăng độ mạnh thuật toán.

## 4. Chuẩn hóa chữ ký truyền qua HTTP trước khi so sánh

Hợp đồng **HMAC-SIGNATURE-COMPARE-V1** trong bài yêu cầu:

| Thuộc tính | Giá trị |
| --- | --- |
| Thuật toán HMAC | `HmacSHA256` cố định theo server policy |
| Độ dài tag | Đúng **32 byte** |
| Encoding trong header | **Base64 chuẩn có padding** (RFC 4648 basic alphabet) |
| Độ dài encoded text | Đúng **44 ký tự ASCII** |
| Cấu trúc text | 43 ký tự `A-Z a-z 0-9 + /` và đúng một `=` cuối |
| Header chứa chữ ký | Chính xác **một** `X-Signature`; tên header không phân biệt case |
| Whitespace | Không SP, tab, CR/LF, obs-fold bên trong giá trị |
| Canonical encoding | Decode rồi encode lại phải trùng **hoàn toàn** chuỗi gốc |
| So sánh HMAC | `MessageDigest.isEqual` giữa **hai mảng 32 byte** |

Ví dụ cách kiểm tra độc lập:

~~~java
import java.util.Base64;

static byte[] decodeFullHmacSha256Tag(String value) {
    if (value == null || !value.matches("[A-Za-z0-9+/]{43}=")) {
        return null;
    }
    try {
        byte[] tag = Base64.getDecoder().decode(value);
        if (tag.length != 32 ||
            !Base64.getEncoder().encodeToString(tag).equals(value)) {
            return null;
        }
        return tag;
    } catch (IllegalArgumentException malformed) {
        return null;
    }
}
~~~

**Tại sao cần round-trip?** Decoder của một số thư viện có thể chấp nhận Base64 không padding hoặc pad bits không canonical. Verifier có thể decode ra đúng 32 byte nhưng nên **từ chối text ngoài hợp đồng** thay vì âm thầm có nhiều biểu diễn cho một tag. Round-trip là kiểm tra biểu diễn, còn **HMAC comparison mới kiểm tra tính hợp lệ của tag**.

**Không được** chuyển sang `Base64.getMimeDecoder()` hoặc gọi `trim()`, rồi tiếp tục nếu format gốc sai. MIME decoder có chính sách linh hoạt với ký tự ngoài alphabet không thích hợp cho signed security header trong giao thức này.

Nếu chọn **Base64url không padding** thay vì Base64 chuẩn, tag 32 byte sẽ có **43 ký tự**, decoder là `Base64.getUrlDecoder()`, re-encoder là `Base64.getUrlEncoder().withoutPadding()` và alphabet là `[A-Za-z0-9_-]`. Đó là **một hợp đồng khác**; không tự thử cả hai decoder. Hex chữ thường cũng là lựa chọn khác, tag 32 byte thành 64 ký tự và có quy tắc kiểm tra riêng.

### 4.1. Vấn đề duplicate header

~~~http
X-Signature: AAAA...=
x-signature: BBBB...=
~~~

Tên header HTTP không phân biệt chữ hoa/thường, nên đây là **hai field line cùng tên**. Nếu gateway lấy giá trị đầu còn backend lấy giá trị cuối, phép so sánh của verifier có thể bảo vệ **một input khác** input downstream sử dụng. Đừng trông chờ `getHeader("X-Signature")` đã đủ để chứng minh request gốc có đúng một field line.

**Ingress/HTTP parser đáng tin phải reject duplicate security headers trước khi thông tin duplicate bị gộp mất**, đặc biệt `X-Signature`, `X-Key-Id`, `X-Client-Id`, `X-Timestamp`, `X-Nonce`, `X-Content-SHA256` và các header điều khiển route/body. Không sử dụng header do client tự đặt như `X-Verified: true` để bỏ qua HMAC.

## 5. Kiểm tra HMAC nằm ở đâu trong luồng verify request?

~~~mermaid
flowchart TD
    A["Nhận HTTP request tại trust boundary"] --> B["Parse strict: framing, duplicate, body limit"]
    B --> C["Đọc một X-Signature, validate format và decode tag"]
    C --> D["Kiểm tra method, URI, signed headers, body digest, timestamp format"]
    D --> E["Chọn key theo client ID + key ID; kiểm tra policy"]
    E --> F["Tự dựng canonical bytes; tính expected HMAC-SHA256"]
    F --> G{"MessageDigest.isEqual full tags?"}
    G -->|Sai| X["Authentication failed"]
    G -->|Đúng| H["Kiểm tra freshness và claim nonce nguyên tử"]
    H -->|Đã dùng/quá hạn| X
    H -->|Hợp lệ| I["Authorization + idempotency + nghiệp vụ"]
~~~

Không có một thứ tự tuyệt đối bắt buộc cho mọi kiểm tra **không có side effect**: ví dụ kiểm tra độ dài request, timestamp format và freshness trước HMAC có thể giúp giảm tải. Nhưng phải bảo đảm **không xác nhận identity, không cập nhật nghiệp vụ và không claim nonce cho request giả** trước khi chứng minh HMAC hợp lệ.

| Bước | Kiểm tra | Sai thì xử lý |
| ---: | --- | --- |
| 1 | HTTP framing hợp lệ, body/header dưới giới hạn, không duplicate signed fields | Reject tại ingress, không đưa input mơ hồ đến backend. |
| 2 | Encoded signature đúng alphabet/padding, decode được và đúng **32 byte** | Reject; không so sánh prefix. |
| 3 | Method, raw URI/query và signed headers phù hợp contract | Reject; không dựng canonical từ lời tự khai không tin cậy. |
| 4 | Body digest do verifier tự tính bằng SHA-256 trên **body bytes thực nhận** | Reject khi không khớp digest trong signed header. |
| 5 | Secret theo client ID + key ID đúng policy, algorithm, audience, hiệu lực và route | Reject khi key không hợp lệ/đã thu hồi; không fallback không kiểm soát. |
| 6 | Expected HMAC từ canonical bytes; full-tag secure comparison | Reject khi sai. |
| 7 | Timestamp nằm trong cửa sổ; nonce atomically chưa dùng | Reject replay hoặc clock lệch quá hạn. |
| 8 | Role/scope/tenant/resource và idempotency của hành động | Reject thiếu quyền dù HMAC đúng. |

### 5.1. Authentication error và timing

Có thể chọn **một loại phản hồi public** cho lỗi xác thực chữ ký (chẳng hạn HTTP 401 với mã lỗi tổng quát), nhưng vẫn ghi **mã nguyên nhân an toàn** ở hệ thống quan sát nội bộ: `malformed-signature`, `unknown-key`, `signature-mismatch`, `expired-timestamp`, `replayed-nonce`. Không trả secret, raw signature hoặc canonical có dữ liệu nhạy cảm cho client.

Tránh mô tả sai rằng “trả cùng status code là constant-time”: nhánh decode, key lookup, kiểm tra MAC và nonce I/O vẫn có thời gian khác nhau. Có thể cân nhắc giới hạn tốc độ, chống enumeration, key-lookup policy và đánh giá side channel theo threat model, thay vì chỉ dựa vào một hàm so sánh.

## 6. Canonical request mẫu để thực hành so sánh

Hợp đồng dưới đây chỉ là **ví dụ học tập**, không phải định dạng do chuẩn HTTP bắt buộc:

~~~text
HMAC-SIGNATURE-COMPARE-V1
POST
/v1/orders?currency=VND
audience:orders-api
x-client-id:partner-42
x-key-id:key-2026-11
x-timestamp:<unix-epoch-seconds>
x-nonce:<32-hex-lowercase>
content-type:application/json
x-content-sha256:<sha256-body-64-hex-lowercase>
~~~

Hợp đồng quy định:

1. **Method:** `POST` đúng chữ hoa, không tự uppercase method nhận được vì HTTP method token case-sensitive.
2. **Raw target:** ký `/v1/orders?currency=VND` đúng representation request thực nhận; không decode/reorder query tùy ý hoặc dùng một URI khác để route.
3. **Audience:** `orders-api` được server xác định; không tin một forwarded host do người gửi tự khai.
4. **Identity và key ID:** ràng buộc trong canonical; server chỉ chọn key được cấp cho đúng client, còn hiệu lực và đúng route scope.
5. **Timestamp:** Unix epoch **seconds** dạng ASCII thập phân chính tắc, không dùng milliseconds, spaces hay số âm.
6. **Nonce:** random 128 bit mã hóa thành 32 hex chữ thường, được ký và dùng để chặn replay sau khi HMAC hợp lệ.
7. **Content-Type:** literal `application/json` theo contract; không gộp/trộn duplicate header hoặc thay representation sau xác minh.
8. **Body digest:** `lowerHex(SHA256(bodyBytes))` của byte thực nhận; không serialize lại JSON rồi hash.
9. **Dòng canonical:** nối bằng đúng LF (0x0A), mã hóa UTF-8, **không LF cuối**. Signature text được tạo từ tag HMAC và không nằm trong canonical.

Với cùng secret và canonical bytes, **client và verifier phải tính được cùng 32 tag bytes**. Hợp đồng truyền chữ ký qua `X-Signature` bằng Base64 chuẩn padded, do đó được decode về 32 byte trước khi so sánh.

## 7. Java 17: so sánh full HMAC tag an toàn

Đoạn chương trình tự chứa sau trình bày **trọn luồng** cho endpoint cố định `POST /v1/orders?currency=VND`:

- Client sinh nonce bằng `SecureRandom`, tạo body JSON UTF-8, body digest và canonical request, ký bằng `javax.crypto.Mac` rồi Base64-encode.
- Verifier lấy dữ liệu request được mô phỏng, validate signature encoding, key ID và thời hạn key, tính lại body digest/canonical/HMAC.
- So sánh **đủ 32 byte** bằng `MessageDigest.isEqual`, sau đó claim nonce và áp dụng policy nghiệp vụ riêng.
- Test nhiều kiểu sửa signature và payload, replay, key bị revoke và timestamp.

**Giới hạn có chủ ý:** `SignedRequest` mô phỏng request đã parse, không phải HTTP server parser. Secret được sinh ngẫu nhiên trong cùng tiến trình để minh họa; production phải lấy secret từ key manager, lọc duplicate headers tại trusted ingress, xác thực gateway→backend và dùng nonce store có TTL chung giữa các replica.

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
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SignatureComparisonExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String METHOD = "POST";
    private static final String RAW_TARGET = "/v1/orders?currency=VND";
    private static final String CLIENT_ID = "partner-42";
    private static final String KEY_ID = "key-2026-11";
    private static final String CONTENT_TYPE = "application/json";
    private static final String AUDIENCE = "orders-api";
    private static final long PAST_SECONDS = 300;
    private static final long FUTURE_SECONDS = 60;

    record SignedRequest(
        String method, String target, String clientId, String keyId,
        String timestamp, String nonce, String contentType,
        String bodyHash, String signature, byte[] body
    ) {}

    record KeyRecord(
        String clientId, String keyId, byte[] secret,
        Instant activeFrom, Instant expiresAt, boolean revoked
    ) {}

    // Demo một JVM, không có TTL; production dùng shared atomic store.
    static final class DemoNonceStore {
        private final Set<String> seen = ConcurrentHashMap.newKeySet();

        boolean claim(String clientId, String nonce) {
            return seen.add(clientId + ":" + nonce);
        }
    }

    static String sha256Hex(byte[] body)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(body)
        );
    }

    static byte[] hmac(byte[] secret, byte[] message)
            throws GeneralSecurityException {
        // Không chia sẻ cùng instance Mac giữa các request/threads.
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(message);
    }

    static byte[] decodeFullSignature(String encoded) {
        // Base64 basic padded: 32 byte -> đúng 44 ký tự, dấu '=' cuối.
        if (encoded == null ||
            !encoded.matches("[A-Za-z0-9+/]{43}=")) {
            return null;
        }
        try {
            byte[] tag = Base64.getDecoder().decode(encoded);
            // Round-trip chống biểu diễn Base64 không canonical.
            if (tag.length != 32 ||
                !Base64.getEncoder().encodeToString(tag)
                    .equals(encoded)) {
                return null;
            }
            return tag;
        } catch (IllegalArgumentException malformed) {
            return null;
        }
    }

    static String canonical(String method, String target,
            String clientId, String keyId, String timestamp,
            String nonce, String contentType, String bodyHash) {
        if (!METHOD.equals(method) || !RAW_TARGET.equals(target) ||
            !CLIENT_ID.equals(clientId) || !KEY_ID.equals(keyId) ||
            !CONTENT_TYPE.equals(contentType) ||
            timestamp == null ||
            !timestamp.matches("[1-9][0-9]{0,18}") ||
            nonce == null || !nonce.matches("[0-9a-f]{32}") ||
            bodyHash == null || !bodyHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException(
                "Request không phù hợp signing contract"
            );
        }
        return String.join("\n",
            "HMAC-SIGNATURE-COMPARE-V1",
            method,
            target,
            "audience:" + AUDIENCE,
            "x-client-id:" + clientId,
            "x-key-id:" + keyId,
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "content-type:" + contentType,
            "x-content-sha256:" + bodyHash
        );
    }

    static SignedRequest sign(byte[] secret, Clock clock)
            throws GeneralSecurityException {
        byte[] body = "{\"orderId\":\"ord-123\",\"amount\":50000}"
            .getBytes(StandardCharsets.UTF_8);
        byte[] nonceBytes = new byte[16];
        RANDOM.nextBytes(nonceBytes);
        String nonce = HexFormat.of().formatHex(nonceBytes);
        String timestamp = Long.toString(clock.instant().getEpochSecond());
        String digest = sha256Hex(body);
        String text = canonical(
            METHOD, RAW_TARGET, CLIENT_ID, KEY_ID, timestamp,
            nonce, CONTENT_TYPE, digest
        );
        byte[] tag = hmac(
            secret, text.getBytes(StandardCharsets.UTF_8)
        );
        String signature = Base64.getEncoder().encodeToString(tag);
        return new SignedRequest(
            METHOD, RAW_TARGET, CLIENT_ID, KEY_ID,
            timestamp, nonce, CONTENT_TYPE, digest, signature, body
        );
    }

    static boolean verify(SignedRequest req,
            Map<String, KeyRecord> keyring,
            Clock clock, DemoNonceStore nonces)
            throws GeneralSecurityException {
        if (req == null || req.body() == null ||
            req.body().length > 65536) {
            return false;
        }
        byte[] receivedTag = decodeFullSignature(req.signature());
        if (receivedTag == null) {
            return false;
        }

        // Request fields vẫn chưa đáng tin; kiểm tra format trước lookup.
        final String text;
        try {
            String actualBodyHash = sha256Hex(req.body());
            if (!actualBodyHash.equals(req.bodyHash())) {
                return false;
            }
            text = canonical(
                req.method(), req.target(), req.clientId(), req.keyId(),
                req.timestamp(), req.nonce(), req.contentType(),
                actualBodyHash
            );
        } catch (IllegalArgumentException invalid) {
            return false;
        }

        final long timestamp;
        try {
            timestamp = Long.parseLong(req.timestamp());
        } catch (NumberFormatException invalidNumber) {
            return false;
        }
        long now = clock.instant().getEpochSecond();
        if (timestamp < now - PAST_SECONDS ||
            timestamp > now + FUTURE_SECONDS) {
            return false;
        }

        // Lookup server-side theo client ID + key ID, không lấy key từ HTTP.
        KeyRecord key = keyring.get(req.clientId() + ":" + req.keyId());
        Instant nowInstant = clock.instant();
        if (key == null || key.revoked() ||
            !req.clientId().equals(key.clientId()) ||
            !req.keyId().equals(key.keyId()) ||
            key.secret() == null || key.secret().length < 32 ||
            nowInstant.isBefore(key.activeFrom()) ||
            !nowInstant.isBefore(key.expiresAt())) {
            return false;
        }

        byte[] expectedTag = hmac(
            key.secret(), text.getBytes(StandardCharsets.UTF_8)
        );
        // Đã cố định 32 byte ở phía decode; không so sánh prefix.
        if (expectedTag.length != 32 ||
            !MessageDigest.isEqual(expectedTag, receivedTag)) {
            return false;
        }

        // Không claim nonce nếu HMAC không hợp lệ.
        return nonces.claim(req.clientId(), req.nonce());
    }

    static SignedRequest replaceSignature(
            SignedRequest r, String signature) {
        return new SignedRequest(
            r.method(), r.target(), r.clientId(), r.keyId(),
            r.timestamp(), r.nonce(), r.contentType(),
            r.bodyHash(), signature, r.body()
        );
    }

    static void must(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void rfc4231Vector() throws Exception {
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);
        byte[] tag = hmac(
            key, "Hi There".getBytes(StandardCharsets.US_ASCII)
        );
        String expected =
            "b0344c61d8db38535ca8afceaf0bf12" +
            "b881dc200c9833da726e9376c2e32cff7";
        must(HexFormat.of().formatHex(tag).equals(expected),
            "HMAC-SHA256 RFC 4231 known-answer test thất bại");
    }

    public static void main(String[] args) throws Exception {
        rfc4231Vector();
        byte[] secret = new byte[32]; // Key test; không dùng ở production.
        RANDOM.nextBytes(secret);
        Clock fixed = Clock.fixed(
            Instant.parse("2026-11-28T02:00:00Z"), ZoneOffset.UTC
        );
        KeyRecord active = new KeyRecord(
            CLIENT_ID, KEY_ID, secret,
            Instant.parse("2026-01-01T00:00:00Z"),
            Instant.parse("2027-01-01T00:00:00Z"),
            false
        );
        String keyRef = CLIENT_ID + ":" + KEY_ID;
        Map<String, KeyRecord> activeKeys = Map.of(keyRef, active);
        SignedRequest signed = sign(secret, fixed);

        // Client HTTP Java 17 chỉ được dựng ở đây; không gửi ra mạng.
        HttpRequest httpRequest = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + signed.target()))
            .header("Content-Type", signed.contentType())
            .header("X-Client-Id", signed.clientId())
            .header("X-Key-Id", signed.keyId())
            .header("X-Timestamp", signed.timestamp())
            .header("X-Nonce", signed.nonce())
            .header("X-Content-SHA256", signed.bodyHash())
            .header("X-Signature", signed.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(signed.body()))
            .build();
        must(METHOD.equals(httpRequest.method()),
            "Client method không đúng");
        must(verify(signed, activeKeys, fixed, new DemoNonceStore()),
            "Chữ ký đúng phải được chấp nhận");

        // Tag 32 byte bị đổi byte đầu hoặc byte cuối: format vẫn đúng,
        // nhưng full HMAC comparison PHẢI FAIL.
        byte[] originalTag = decodeFullSignature(signed.signature());
        must(originalTag != null && originalTag.length == 32,
            "Decode tag 32 byte thất bại");
        for (int index : new int[] {0, 31}) {
            byte[] changed = originalTag.clone();
            changed[index] ^= 1;
            SignedRequest modified = replaceSignature(
                signed, Base64.getEncoder().encodeToString(changed)
            );
            must(!verify(modified, activeKeys, fixed, new DemoNonceStore()),
                "Tag sai byte đầu/cuối phải bị từ chối");
        }

        // Cắt tag thành 16 byte (và padding biến đổi) phải bị reject.
        String truncated = Base64.getEncoder().encodeToString(
            Arrays.copyOf(originalTag, 16)
        );
        must(!verify(replaceSignature(signed, truncated),
                     activeKeys, fixed, new DemoNonceStore()),
            "Truncated tag không được chấp nhận");
        must(!verify(
                replaceSignature(
                    signed, signed.signature().substring(0, 43)),
                activeKeys, fixed, new DemoNonceStore()),
            "Base64 thiếu dấu '=' phải bị từ chối");
        must(!verify(
                replaceSignature(signed, signed.signature() + " "),
                activeKeys, fixed, new DemoNonceStore()),
            "Signature có SP cuối phải bị từ chối");
        String urlSafe = Base64.getUrlEncoder().withoutPadding()
            .encodeToString(originalTag);
        must(!verify(replaceSignature(signed, urlSafe),
                     activeKeys, fixed, new DemoNonceStore()),
            "Base64url không padding sai contract");

        // Tính hash lại từ body thực nhận nên đổi byte không thể qua verify.
        byte[] changedBody = signed.body().clone();
        changedBody[0] ^= 1;
        SignedRequest tamperedBody = new SignedRequest(
            signed.method(), signed.target(),
            signed.clientId(), signed.keyId(), signed.timestamp(),
            signed.nonce(), signed.contentType(), signed.bodyHash(),
            signed.signature(), changedBody
        );
        must(!verify(tamperedBody, activeKeys, fixed, new DemoNonceStore()),
            "Body bị sửa phải bị từ chối");

        // Key bị revoke phải bị từ chối dù tag HMAC có thể tính đúng.
        KeyRecord revoked = new KeyRecord(
            CLIENT_ID, KEY_ID, secret,
            active.activeFrom(), active.expiresAt(), true
        );
        must(!verify(signed, Map.of(keyRef, revoked),
                     fixed, new DemoNonceStore()),
            "Key revoked không được xác thực");

        // Replay: cùng request/tag/nonce chỉ được claim một lần.
        DemoNonceStore replayStore = new DemoNonceStore();
        must(verify(signed, activeKeys, fixed, replayStore),
            "Request mới phải verify được");
        must(!verify(signed, activeKeys, fixed, replayStore),
            "Nonce trùng phải bị từ chối");

        Clock late = Clock.offset(fixed, Duration.ofSeconds(301));
        must(!verify(signed, activeKeys, late, new DemoNonceStore()),
            "Timestamp quá cũ phải bị từ chối");
        System.out.println(
            "PASS: RFC4231, full-tag compare, strict encoding, replay"
        );
    }
}
~~~

### 7.1. Vì sao ví dụ tạo `Mac` riêng mỗi lần?

`javax.crypto.Mac` là đối tượng có trạng thái. Không nên chia sẻ một instance giữa các request/thread rồi kỳ vọng mỗi phép `update/doFinal` đều độc lập, nếu không có cơ chế đồng bộ/phân tách phù hợp. Ví dụ tạo `Mac` mới cho mỗi phép tính để tránh rò rỉ trạng thái giữa request. Với hệ thống throughput lớn, cần đánh giá tối ưu một cách an toàn và kiểm thử concurrency.

### 7.2. Vì sao không gọi `MessageDigest.isEqual` trên chuỗi Base64?

`MessageDigest.isEqual` nhận **byte[]**; nếu chuyển Base64 text thành UTF-8 rồi so sánh, ta lại phụ thuộc vào việc text được encode canonical giống nhau, thay vì xác minh byte tag gốc. Đúng quy trình là **validate encoding → decode → kiểm tra full tag length → tính expected HMAC → so sánh byte**.

Trong ví dụ, cả hai tag đều có độ dài xác định **32 byte**, tránh phụ thuộc vào độ dài do client tự gửi. Một request có tag dài 16 byte bị từ chối **trước** phép so sánh mật mã; không có cơ chế “so khớp 16 byte trước”.

### 7.3. Giới hạn kỹ thuật của chương trình

- `SignedRequest` chứa các giá trị được mô phỏng. Production phải dùng HTTP parser đáng tin để đọc **chính xác một** signed header, method, raw path/query và body bytes, rồi xác minh dữ liệu backend **thực sự dùng** không bị rewrite sau khi verify.
- `KeyRecord` và `Map` chỉ mô phỏng key store; cần kiểm tra audience, method/route scope, client status, key rotation overlap/revoke và permission tại hệ thống thật. Mẫu endpoint có audience `orders-api` và method/target cố định.
- `DemoNonceStore` chỉ nguyên tử trong một JVM và **không TTL**. Multi-replica cần nonce store dùng chung, kiểm tra TTL/freshness và chống race; một key retry nghiệp vụ phải có idempotency riêng.
- Ví dụ chỉ kiểm tra một format Base64 chuẩn có padding. Nếu hỗ trợ Base64url hoặc một tag length khác, phải định nghĩa **phiên bản contract** tương ứng thay vì fallback decoder tự do.
- Mã không gửi request thật qua HTTP/2 hoặc gateway. Integration tests phải kiểm tra cùng raw URI, signed headers và body representation xuyên qua các hop.
- Chương trình minh họa authentication; **không thực thi authorization** vì không có cơ sở dữ liệu tenant/resource, nên việc PASS ở đây chỉ nghĩa là đã xác minh request theo policy demo.

## 8. So sánh signature và các kiểu lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý đúng |
| --- | --- | --- |
| `Arrays.equals` hoặc vòng lặp trả sớm khi tag khác | Có thể làm thời gian phụ thuộc vị trí sai | Dùng `MessageDigest.isEqual` trên full tag cố định chiều dài. |
| So sánh Base64 string chưa decode | Dễ phụ thuộc biểu diễn, không có cam kết timing thích hợp | Validate encoding strict, decode thành byte, so sánh tag bytes. |
| So sánh prefix ngắn do client gửi | Mở rộng khả năng đoán/brute-force | Chặn tag ngắn, tag dài, dùng full 32 byte theo policy. |
| Không kiểm tra độ dài HMAC | Sai thuật toán/truncated tag có thể lọt nếu logic cắt | Khóa thuật toán và tag length tại server. |
| So sánh `SHA256(body)` với `X-Signature` | SHA-256 không khóa nên không authentication | Tính HMAC trên toàn bộ canonical có body digest. |
| Tin tag có đúng 44 ký tự là hợp lệ | Kẻ tấn công có thể tạo Base64 bất kỳ | Tính expected HMAC bằng secret và so sánh tag thực. |
| Dùng cùng secret nhưng khác canonicalization | Client đúng key nhưng verify sai hoặc có ambiguity | Định nghĩa method/URI/header/body bytes, thứ tự, LF, UTF-8. |
| Trộn Base64, Base64url và hex bằng fallback | Parser ambiguity/downgrade | Mỗi version có đúng một encoding, strict round-trip. |
| Dùng HMAC đúng với key ID do client thay đổi | Có thể chọn sai identity/key/policy | Key ID được ký, key store tra theo đúng client và trạng thái. |
| Claim nonce trước khi verify | Attacker có thể đốt nonce hợp lệ hoặc DoS | Claim nguyên tử chỉ sau khi tag khớp. |
| Đặt authorization trước xác thực | Có thể tin client ID chưa được xác minh | Chỉ dùng identity cho quyền sau verify HMAC và freshness. |

### 8.1. So sánh signature không chứng minh cả request đều được bảo vệ

Một expected HMAC có thể khớp hoàn hảo ngay cả khi **một header không ký** được backend dùng làm chỉ thị bảo mật. Ví dụ:

~~~http
POST /v1/orders?currency=VND HTTP/1.1
X-HTTP-Method-Override: DELETE
X-Signature: <valid-signature-for-POST>
~~~

Nếu `X-HTTP-Method-Override` không nằm trong phạm vi ký và middleware sau verifier đổi effective method thành DELETE, backend có thể làm thao tác **không được ràng buộc trong canonical**. Thiết kế an toàn nên **vô hiệu hóa method override** trên các route được HMAC bảo vệ hoặc quy định rõ effective method trong hợp đồng ký, kiểm soát trước routing/authorization.

HMAC comparison xác thực **message mà ta đưa vào HMAC**, không tự quyết định message đó đã bao phủ toàn bộ ngữ nghĩa request.

## 9. Proxy/gateway, HTTP/2 và trust boundary

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy không tin cậy
    participant G as Trusted ingress
    participant V as HMAC verifier
    participant N as Shared nonce store
    participant B as Backend
    C->>P: POST, raw URI, signed headers, body, signature
    P->>G: Có thể reorder header/chỉnh request
    G->>V: Parse strict và cung cấp dữ liệu thực nhận
    V->>V: Recompute canonical + HMAC, full tag compare
    alt HMAC đúng, timestamp hợp lệ
        V->>N: Atomic claim(client ID, nonce)
        alt Nonce mới
            N-->>V: Success
            V->>B: Identity và request đã xác minh
            B->>B: Authorization và idempotency
        else Nonce trùng
            N-->>V: Replayed
            V-->>C: Reject
        end
    else Tag sai hoặc policy không hợp lệ
        V-->>C: Reject authentication
    end
~~~

| Tình huống qua proxy/gateway | Chữ ký sẽ bị ảnh hưởng thế nào? | Điều kiện để an toàn |
| --- | --- | --- |
| Gateway đổi vị trí các header khác tên | Nếu canonical phụ thuộc wire order sẽ sai | Xác định signed header set/order cố định. |
| HTTP/2 dùng `:method`, `:path` | Không có request line như HTTP/1.1 | Dựng cùng method/raw request target logic theo contract. |
| Proxy tự lower-case **tên** header | Header name case-insensitive | Canonical hóa tên; không tự đổi header value. |
| Proxy normalize percent-encoding/raw query | Canonical bytes hoặc route có thể lệch | Verify ở boundary đáng tin, thống nhất representation với backend. |
| Proxy giải nén/sửa body | Body bytes thay đổi | Ký digest của representation đã định nghĩa; không transform bất ngờ. |
| Proxy thêm `X-Verified: true` hoặc `X-User-Id` | Có thể bypass authn hoặc mạo danh nếu backend tin | Ingress xóa header không tin cậy; xác thực hop nội bộ. |
| Proxy phát lại nguyên request | HMAC **vẫn khớp** | Timestamp/nonce dùng chung giữa replica, TTL đúng. |
| Gateway route theo effective method khác method đã ký | Verifier và backend không đồng ý hành động | Bảo đảm route/authorization dùng cùng method/URI đã được xác minh. |

Nếu HMAC được verify ở gateway rồi backend tin kết quả, gateway→backend phải có kênh xác thực và chặn truy cập trực tiếp backend; identity nội bộ phải được truyền qua cơ chế không thể bị client bên ngoài giả mạo. Không suy ra rằng một header `X-Verified` có thể tự đóng vai trò bằng chứng xác minh HMAC.

## 10. Replay, key rotation và authorization sau phép so sánh

### 10.1. Chữ ký trùng khớp vẫn có thể bị phát lại

HMAC đúng trên request `POST` không ngăn kẻ tấn công **ghi lại rồi gửi nguyên request**. Với timestamp còn hạn, full tag vẫn so sánh bằng nhau. Hợp đồng cần ký `x-timestamp` và `x-nonce`, sau đó kiểm tra:

- Freshness theo **server clock**, ví dụ tối đa 300 giây ở quá khứ và 60 giây ở tương lai (đây là **policy minh họa**, không phải thông số bắt buộc của HMAC).
- Nonce đủ ngẫu nhiên, tối thiểu ví dụ 128 bit để tránh trùng ngẫu nhiên; cùng identity/audience phải không được tái sử dụng trong cửa sổ.
- Nonce store **nguyên tử, dùng chung giữa mọi replica**, có TTL đến khi timestamp không còn được chấp nhận cộng safety margin.
- Chỉ claim nonce **sau khi signature đã verify**, tránh request giả làm tiêu thụ một nonce mà client hợp lệ sắp dùng.

Retry nghiệp vụ với **nonce và timestamp mới** vẫn được coi là request mới về mặt replay protection. Với hành động tạo thanh toán, xóa dữ liệu, kích hoạt workflow, cần **idempotency key đã được ký**, theo dõi kết quả nghiệp vụ và thực hiện logic nguyên tử để tránh side effect lặp.

### 10.2. Đúng HMAC nhưng key không còn được chấp nhận

Key ID là identifier dùng **lookup** secret và policy, không phải bằng chứng identity tự thân. Trong key rotation, server có thể duy trì key cũ và key mới còn hiệu lực trong một giai đoạn overlap rõ ràng; **mỗi request phải được verify đúng key mà key ID đã ký chỉ tới**, kiểm tra audience, algorithm, key status (active/revoked), thời hạn và route scope. Không thử nhiều key cho đến khi khớp rồi tự gán identity mới.

Một signature so sánh đúng với secret đã bị thu hồi **vẫn phải bị từ chối**. Khả năng tính được MAC không đồng nghĩa key đang được cấp quyền sử dụng.

### 10.3. Xác thực khác phân quyền

Ngay cả sau khi:

~~~text
Signature format PASS
Full-tag comparison PASS
Timestamp PASS
Nonce claim PASS
~~~

backend vẫn phải kiểm tra client có quyền gọi method, route, tenant và resource cụ thể. **Authentication** chứng minh request gắn với secret hợp lệ và dữ liệu ký không bị thay đổi; **authorization** quyết định có được thực hiện thao tác đó hay không. HMAC không tự thay thế role/scope/ACL, quota hoặc idempotency.

## 11. Ma trận kiểm thử so sánh signature

Mỗi ca độc lập nên dùng nonce mới hoặc nonce store mới; với replay, giữ nguyên nonce. Kiểm thử unit trên Java và integration thực tế qua proxy/gateway với cùng test vectors.

| Ca kiểm thử | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Happy path | HMAC-SHA256 đúng, Base64 44 ký tự, body/URI/headers nguyên vẹn | Decode 32 byte, tag khớp, freshness/nonce tiếp tục PASS. |
| RFC 4231 | Key 20 byte `0x0b`, message `Hi There` | HMAC-SHA256 hex `b0344c61...2e32cff7`. |
| Sai byte đầu | Flip byte 0 trong supplied tag, encode lại hợp lệ | **HMAC comparison FAIL**. |
| Sai byte cuối | Flip byte 31 trong supplied tag, encode lại hợp lệ | **HMAC comparison FAIL**; không trả về sớm theo vị trí byte. |
| Tag 16 byte | Base64 của 16 byte đầu expected MAC | **Reject length**, không so sánh prefix. |
| Tag 33 byte | Base64 của tag dài hơn policy | Reject, không truncate. |
| Chữ ký bị thiếu | Không có `X-Signature` | Reject. |
| Chữ ký Base64 không padding | Bỏ dấu `=` cuối | Reject theo contract padded. |
| Base64url | 43 ký tự không padding | Reject theo contract Base64 basic padded. |
| Chữ ký có SP/CRLF | Thêm whitespace hoặc newline | Reject từ parser/format, không trim. |
| Duplicate signature | Hai `X-Signature` khác case | Reject ngay tại ingress đáng tin. |
| Pad bits không canonical | Decode ra cùng byte nhưng encode lại khác text | Reject vì round-trip không khớp. |
| Tampering body | Đổi `amount` sau khi ký | Body digest/HMAC FAIL. |
| Tampering path/query | `/v1/orders?currency=USD` | Canonical/HMAC FAIL hoặc route policy reject. |
| Method override | Thêm `X-HTTP-Method-Override: DELETE` | Reject/disable, không cho effective method lệch signed method. |
| Sai key ID | Sửa `X-Key-Id`, giữ tag | Không chọn đúng secret hoặc HMAC FAIL. |
| Key revoked | Có HMAC đúng bằng secret cũ nhưng đã revoke | Reject theo key policy. |
| Timestamp quá hạn | Request bị trì hoãn quá cửa sổ | Reject trước xử lý nghiệp vụ. |
| Replay tuần tự | Gửi lại nguyên request đã dùng nonce | Từ chối lần thứ hai bằng nonce store. |
| Replay song song | Hai replica nhận cùng nonce | Tối đa một atomic claim thành công. |
| Proxy đổi raw URI | Percent-decode/re-encode hoặc rewrite query | Reject hoặc verify tại boundary giữ cùng representation. |
| Proxy đổi signed header | Sửa `X-Client-Id`, Content-Type hoặc body hash | Chữ ký sai hoặc policy reject. |
| Thiếu quyền | Client biết key hợp lệ nhưng sửa đơn hàng tenant khác | Authentication có thể PASS, **authorization DENY**. |

### Câu hỏi tự đánh giá

1. Vì sao decode được 32 byte từ `X-Signature` **chưa** chứng minh request đã được xác thực?
2. Vì sao `MessageDigest.isEqual` phù hợp hơn một vòng lặp trả về ngay tại byte không khớp, và vì sao không được quảng cáo toàn bộ verifier “constant-time”?
3. Với HMAC-SHA256 full tag, server phải xử lý thế nào nếu client gửi một tag 8 hoặc 16 byte?
4. Khi body digest header đúng format nhưng không trùng với SHA-256(body thực nhận), có nên tiếp tục coi chữ ký hợp lệ không?
5. Vì sao hai request `POST /v1/orders?currency=VND` và `POST /v1/orders?currency=USD` không được có cùng canonical message?
6. Sau khi MAC đúng, tại sao phải claim nonce atomically và kiểm tra idempotency cho request có side effect?
7. Một client có HMAC hợp lệ bằng secret chưa hết hạn có tự động được truy cập mọi tenant không? Cơ chế nào quyết định?

## 12. Checklist triển khai

- [ ] Chỉ lấy **một** `X-Signature` từ HTTP parser đáng tin; reject duplicate, framing mơ hồ và header injection.
- [ ] Mỗi signing contract quy định **một** encoding, alphabet, padding, full tag length và version; không tự thử decoder/algorithm khác.
- [ ] Giới hạn chiều dài signature text trước decode; validate ASCII/format, kiểm tra round-trip canonical encoding.
- [ ] Decode chữ ký thành **byte[]**, yêu cầu HMAC-SHA256 full tag **32 byte**; không cho caller quyết định prefix length.
- [ ] Dựng lại canonical request từ **method, raw URI/query, signed headers, body bytes/digest** thực nhận; cùng LF, UTF-8 và thứ tự field.
- [ ] Server chọn secret đúng client ID/key ID theo policy và key rotation; kiểm tra trạng thái key, audience, route scope và thời hạn.
- [ ] Tính expected HMAC-SHA256 từ shared secret và canonical bytes, dùng `MessageDigest.isEqual` trên **hai full tag 32 byte**.
- [ ] Không dùng `String.equals` trên Base64 text, early-return byte-loop, `Arrays.copyOf(expected, supplied.length)` hoặc SHA-256 không khóa thay HMAC.
- [ ] Giao tiếp lỗi xác thực nhất quán, bảo vệ log và đánh giá timing/side-channel cả pipeline, không chỉ một hàm so sánh.
- [ ] Chỉ claim nonce **sau MAC hợp lệ**; shared atomic store có TTL bao phủ cửa sổ timestamp, kiểm tra replay đồng thời.
- [ ] Idempotency key đã ký cho nghiệp vụ side effect; HTTPS và giới hạn tần suất để chống lạm dụng.
- [ ] Test tampering byte đầu/cuối tag, short tag, wrong encoding, malformed/duplicate header, proxy HTTP/1.1 ↔ HTTP/2, raw URI rewrite và key revoked.
- [ ] Sau authentication, thực hiện **authorization theo method/action/tenant/resource**, không tự động cho phép chỉ vì signature bằng nhau.

**Ghi nhớ:** **So sánh signature** không phải thao tác so chuỗi Base64, càng không phải chấp nhận một prefix HMAC theo độ dài do client gửi. Quy trình đúng là **parse nghiêm ngặt → decode tag theo hợp đồng → tự tính HMAC từ canonical request thực nhận → so sánh hai tag đầy đủ bằng `MessageDigest.isEqual` → chống replay và phân quyền**. Một phép so sánh an toàn chỉ có ý nghĩa khi phạm vi ký, nguồn secret và ngữ nghĩa request giữa client, gateway, verifier và backend đều thống nhất.
