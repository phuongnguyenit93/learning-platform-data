# Decode signature: giải mã chữ ký HMAC trước khi xác minh HTTP request

Trong **HMAC request authentication**, chữ ký thường được gửi qua HTTP dưới dạng **chuỗi ký tự** trong header, còn kết quả thật của thuật toán HMAC là **dãy byte**. Khi nhận request, server phải **decode signature** theo đúng encoding đã công bố, kiểm tra độ dài tag, tự tính HMAC từ canonical request và shared secret, sau đó so sánh **tag bytes**. Chỉ giải mã Base64 thành công **không** chứng minh request hợp lệ.

Bài **Decode signature** thuộc chương **Encoding chữ ký** của module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Module này thiết kế xác thực HTTP request bằng shared secret và canonical request chứa method, URI, header hoặc body theo hợp đồng ký. Bài tập trung vào việc biến **chuỗi chữ ký nhận từ HTTP thành byte một cách chặt chẽ**, tránh diễn giải mơ hồ giữa Base64, Base64url và hex; đồng thời liên hệ với canonical request, timestamp/nonce chống replay, key rotation, kiểm thử proxy/gateway và việc phân biệt **authentication** với **authorization**.

**Nguyên tắc:** Encoding không làm tăng tính bảo mật của HMAC. Nó chỉ đưa một tag nhị phân lên kênh truyền văn bản. Server phải chọn **một encoding và một dạng canonical duy nhất** cho mỗi phiên bản signing contract, không tự thử lần lượt các decoder cho tới khi có một kết quả khớp.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **tag bytes**, **encoded signature string**, **body digest** và **canonical request bytes**.
2. Giải thích khác biệt giữa Base64 chuẩn có padding, Base64url không padding và hexadecimal; tính được chiều dài của chữ ký HMAC-SHA256.
3. Thiết kế bộ giải mã chữ ký **strict**: một header duy nhất, ASCII đúng alphabet, đúng độ dài, đúng padding, không whitespace và **round-trip canonical**.
4. Viết Java 17 dùng `Base64.getDecoder()`, `Base64.getUrlDecoder()`, `HexFormat` và `MessageDigest.isEqual` để giải mã/so sánh tag.
5. Xây luồng kiểm tra key ID, body digest, canonical method/URI/headers, timestamp, nonce và key rotation mà không nhầm decode với verify.
6. Kiểm thử chữ ký sai format, bị cắt ngắn, đổi encoding, bị proxy sửa, replay và request có HMAC đúng nhưng không đủ quyền.

## 2. Phân biệt bốn đối tượng rất dễ nhầm

Giả sử client tạo một request thanh toán:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-11
X-Timestamp: <epoch-seconds>
X-Nonce: <32-lowercase-hex-characters>
X-Content-SHA256: <64-lowercase-hex-characters>
X-Signature: <base64-tag>

{"orderId":"ord-123","amount":50000}
~~~

Các placeholder `<...>` được thay bằng giá trị thật khi gửi request. Phân biệt:

| Đối tượng | Dữ liệu ví dụ | Ai tạo? | Dùng ở bước nào? |
| --- | --- | --- | --- |
| **Body bytes** | UTF-8 của JSON đã serialize | HTTP client | Tính digest, gửi body thật và xác minh tính toàn vẹn. |
| **Body digest** | `lowerHex(SHA256(bodyBytes))`: 64 ký tự hex | Client và verifier độc lập | Đưa vào canonical request đã được ký; **không phải** chữ ký HMAC. |
| **Canonical request bytes** | UTF-8 của version + method + raw URI + signed fields + body hash | Client/verifier theo contract | Là **message** đầu vào của HMAC. |
| **Raw HMAC tag** | `HMAC_SHA256(secret, canonicalBytes)`: **32 byte** | Signer/verifier độc lập | Đây là giá trị **phải so sánh**. |
| **Encoded signature** | Base64 của 32 byte HMAC, 44 ký tự theo contract ví dụ | Client gửi, verifier decode | Chỉ là **biểu diễn truyền tải** của raw tag. |

~~~mermaid
flowchart TD
    B["Body bytes thực gửi"] --> D["SHA-256 → body digest"]
    D --> C["Canonical request: method, URI, headers, digest"]
    K["Shared secret"] --> M["HMAC-SHA256"]
    C --> M
    M --> T["Raw tag: 32 bytes"]
    T --> E["Encode Base64 để gửi X-Signature"]
    E --> W["HTTP request"]
    W --> V["Verifier: decode X-Signature thành bytes"]
    V --> Q["So sánh với HMAC tự tính trên request thực nhận"]
~~~

Không dùng `SHA256(Base64(signature))` thay cho xác minh HMAC. Cũng không được coi việc một chuỗi “decode được” là bằng chứng bên gửi biết shared secret. Bất kỳ ai cũng có thể tự tạo một chuỗi Base64 có đúng 44 ký tự.

## 3. Base64 chuẩn, Base64url và hex: khác nhau ở wire format

Kết quả HMAC là byte tùy ý, có thể chứa `0x00`, `0xff` hoặc byte không in được. Vì HTTP header thường trao đổi giá trị text, cần encoding để biểu diễn byte thành ký tự dễ truyền.

| Encoding | Alphabet và padding | Tag HMAC-SHA256 **32 byte** | Java 17 |
| --- | --- | --- | --- |
| **Base64 chuẩn, có padding** | `A–Z a–z 0–9 + /`, đuôi `=` theo độ dài | **44 ký tự**, đuôi một `=` | `Base64.getEncoder()` và `Base64.getDecoder()` |
| **Base64url, không padding** | `A–Z a–z 0–9 - _`, không có `=` | **43 ký tự** | `Base64.getUrlEncoder().withoutPadding()` và `Base64.getUrlDecoder()` |
| **Hex chữ thường** | `0–9 a–f` | **64 ký tự** | `HexFormat.of()` |

Vì \(32 = 3 \times 10 + 2\), Base64 có 10 nhóm 3 byte tạo 40 ký tự và 2 byte cuối tạo 3 ký tự nội dung + 1 dấu padding: \(44\) ký tự. Base64url **bỏ đúng dấu `=` cuối** theo hợp đồng không padding nên còn \(43\) ký tự. Hex luôn dùng hai ký tự cho một byte, do đó 32 byte thành 64 ký tự.

Các thuật toán khác có độ dài tag khác: HMAC-SHA512 trả 64 byte (Base64 chuẩn padded là 88 ký tự). **Không đoán thuật toán chỉ bằng độ dài encoded signature**; client ID/key ID và policy server phải chốt thuật toán, tag length, encoding trước khi xác minh.

### 3.1. Base64url không phải “Base64 bị cắt dấu =” trong mọi trường hợp

Base64url dùng alphabet **`-` thay `+`** và **`_` thay `/`**. Bỏ padding là một lựa chọn của contract; có giao thức dùng Base64url **có padding**. Vì vậy phải chốt **cả alphabet lẫn chính sách padding**.

~~~text
Base64 chuẩn alphabet đặc biệt: + /
Base64url alphabet đặc biệt:  - _

Ví dụ minh họa các byte FE FF:
Base64 chuẩn: /v8=
Base64url không padding: _v8
~~~

Một tag ngẫu nhiên không nhất thiết có `+` hay `/`, nên có lúc chuỗi Base64 chuẩn và Base64url **trông giống nhau ở phần nội dung**. Không thể suy ra encoding từ việc chuỗi nhìn có ký tự nào. Hợp đồng **phải chọn một loại cụ thể**; verifier không tự động chuyển qua decoder khác sau khi thất bại.

### 3.2. Hex của tag và hex của body digest là hai giá trị khác nhau

Một request có thể dùng:

~~~http
X-Content-SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
X-Signature: <base64-cua-hmac-tag>
~~~

`X-Content-SHA256` có **64 ký tự hex** do SHA-256 trên **body**. `X-Signature` là Base64 trên **HMAC của canonical request**. Hai giá trị có thể đều liên quan SHA-256 nhưng khác vai trò, không thể hoán đổi.

### 3.3. Đừng coi “ít ký tự hơn” là “chữ ký yếu hơn”

Base64url không padding dùng 43 ký tự thay vì 44 vì **bỏ ký tự đánh dấu padding**, không làm mất một byte tag nào. Tag sau decode vẫn có **32 byte**. Ngược lại, nếu cho phép client gửi 8 hoặc 16 byte đầu của tag HMAC-SHA256 mà policy yêu cầu full 32 byte, đó là **truncation** và phải bị từ chối. Encoding và độ dài tag mật mã là hai khái niệm riêng.

## 4. Hợp đồng giải mã chữ ký: chọn đúng một biểu diễn

Giả sử hợp đồng **HMAC-SIGNATURE-DECODE-V1** quy định:

| Hạng mục | Quy định minh họa |
| --- | --- |
| Vị trí chữ ký | Một header duy nhất `X-Signature` |
| Thuật toán | `HmacSHA256` cố định bởi policy server |
| Tag length | **32 byte**, không chấp nhận truncated tag |
| Wire encoding | **Base64 chuẩn, có padding**, không phải Base64url |
| Encoded length | Đúng **44 ký tự ASCII** |
| Cấu trúc Base64 text | **43 ký tự** trong `[A-Za-z0-9+/]` và **một `=` cuối** |
| Canonical encoding | Decode xong encode lại bằng Base64 chuẩn phải **khớp byte-ký-tự chính xác** |
| Whitespace | Không có SP, tab, CR/LF trong giá trị; không trim ngầm |
| Duplicate field | Không chấp nhận hai `X-Signature`, kể cả khác case hoặc trùng giá trị |
| Key selection | Dựa trên `client ID + key ID` đã kiểm tra, tra policy server |
| So sánh | So sánh **tag bytes** với HMAC server tính lại, không so sánh prefix hay Base64 string |

Đây là **hợp đồng ví dụ**, không phải tiêu chuẩn chung của tất cả HTTP HMAC API. Một dịch vụ chọn Base64url không padding phải thay đổi **đầy đủ** regex, decoder, re-encoder và test cases; tốt nhất dùng version khác nếu thay đổi wire contract.

### 4.1. Tại sao cần decode → encode lại để kiểm tra canonical?

Một số decoder Base64 hợp lệ khi thiếu padding hoặc gặp những biến thể text khác. Ví dụ Java `Base64.getDecoder()` có thể decode một chuỗi chưa padding trong nhiều trường hợp; điều đó **không** có nghĩa contract của ta cho phép thiếu `=`.

Ngoài ra, encoding Base64 có các **pad bits** phải bằng 0 để tạo một biểu diễn canonical. Nếu một decoder khoan dung bỏ qua pad bits không canonical, nhiều chuỗi text khác nhau có thể decode ra cùng byte. Với API HMAC mới, nên yêu cầu:

~~~text
decodedBytes = Base64_basic_decoder.decode(signatureText)

length(decodedBytes) == 32
AND
Base64_basic_encoder.encode(decodedBytes) == signatureText
~~~

Round-trip là phép kiểm tra **dạng biểu diễn**, không phải phép kiểm tra tính xác thực. Sau đó mới so sánh HMAC tag bằng shared secret.

### 4.2. Bộ lọc chặt không thay thế HTTP parser

Đầu vào phải đi qua parser tại trust boundary đáng tin, chống header injection, request smuggling và header trùng:

~~~http
X-Signature: abc...
x-signature: def...
~~~

Tên HTTP header **không phân biệt hoa/thường**, vì vậy đây là **cùng một trường xuất hiện hai lần**. Nếu gateway lấy giá trị đầu, backend lấy giá trị cuối hoặc tự gộp thành một chuỗi, verifier có thể xác minh một chữ ký trong khi tầng khác hành xử theo giá trị khác. **Từ chối duplicate trước khi chúng bị library gộp mất dấu vết**.

Không dùng `Base64.getMimeDecoder()` cho chữ ký bảo mật trong header của hợp đồng này: MIME decoder có thể bỏ qua một số ký tự ngoài alphabet, không phù hợp chính sách text chính tắc. Cũng không gọi `trim()`/`replaceAll("\\s", "")` để làm một header mơ hồ trở nên hợp lệ.

## 5. Luồng xác minh: decode signature ở đúng vị trí

~~~mermaid
flowchart TD
    A["HTTP request đến trusted ingress"] --> B["Parse strict: framing, duplicate, limits"]
    B --> C["Lấy đúng một X-Signature; kiểm tra 44 ASCII chars"]
    C --> D["Base64 decode + độ dài tag + canonical round-trip"]
    D --> E["Chọn secret theo client ID / key ID, kiểm tra policy"]
    E --> F["Xác minh method, raw URI, signed headers và body digest"]
    F --> G["Dựng lại canonical bytes, HMAC-SHA256"]
    G --> H{"MessageDigest.isEqual(expected, received)?"}
    H -->|Không| X["Reject authentication"]
    H -->|Có| I["Claim nonce nguyên tử, kiểm tra replay"]
    I -->|Nonce trùng| X
    I -->|Nonce mới| J["Authorize và xử lý idempotency/nghiệp vụ"]
~~~

Chi tiết thứ tự có thể được tối ưu để tránh tốn CPU, ví dụ kiểm tra timestamp hợp lệ về format và giới hạn kích thước trước khi tính HMAC. Nhưng **không có quyền thực hiện side effect trước khi HMAC hợp lệ, nonce được xử lý và authorization hoàn thành**.

Một cách xử lý có cấu trúc:

1. **Parser/ingress:** xác nhận HTTP framing hợp lệ, giới hạn độ dài request, không duplicate security headers, không CR/LF/HTAB trong `X-Signature`, không có nguồn identity giả từ proxy.
2. **Xác thực format chữ ký:** header có đúng 44 ký tự ASCII theo alphabet Base64 chuẩn và đúng một `=` cuối; từ chối thiếu, rỗng, URL-safe, thừa padding hoặc ký tự ngoài alphabet.
3. **Decode:** dùng decoder Base64 chuẩn; phải trả **chính xác 32 byte**; encode lại và đối chiếu text để chặn biểu diễn không canonical.
4. **Key lookup:** dựa vào client ID và key ID lấy từ request, tra secret cùng policy thuật toán, trạng thái key, audience và route; đây chỉ là giá trị **được khai báo** cho tới khi HMAC xác minh thành công.
5. **Freshness/body/URI:** kiểm tra timestamp, nonce, method, raw request target, signed headers và tính SHA-256 của **body bytes thực nhận**. Không tin body hash client tự công bố nếu server chưa tính lại.
6. **HMAC:** dựng canonical đúng thứ tự, LF, UTF-8; tính `Mac.getInstance("HmacSHA256")` với secret đã chọn.
7. **So sánh bytes:** dùng `MessageDigest.isEqual` cho hai tag đầy đủ 32 byte, không so sánh prefix, không dùng `String.equals` trên Base64 text để giả định constant-time.
8. **Replay và quyền:** claim nonce nguyên tử trong store dùng chung sau HMAC; kiểm tra idempotency key đã ký nếu có side effect; xác thực danh tính **không đồng nghĩa phân quyền**.

### 5.1. Nếu tag decode được nhưng HMAC sai

Đó là **authentication failure**, không phải lý do tự “cứu” bằng:

- Thử Base64url, rồi hex, rồi MIME decoder cho đến khi thành công.
- Thử truncate tag dài thành 16 byte hoặc so sánh một prefix có độ dài do client chọn.
- Thử lần lượt nhiều biến thể canonical request, bỏ method/URI/body hash, hoặc đổi thứ tự signed headers.
- Thử vô hạn nhiều secret/algorithm hoặc key version ngoài policy được cho phép.
- Sử dụng chữ ký do client gửi làm shared secret hoặc bỏ qua bước xác minh trong chế độ compatibility.

Những cách này có thể mở đường downgrade, parser differential hoặc bỏ bảo vệ một phần request. Nếu cần nâng cấp format, hãy phát hành **version contract mới với tập test vectors rõ ràng** và kiểm soát quyền tương thích tại server.

## 6. Canonical request được HMAC ký trong ví dụ

Hợp đồng dùng chính xác các dòng sau, nối bằng **LF byte 0x0A**, không có LF cuối và mã hóa thành **UTF-8**:

~~~text
HMAC-SIGNATURE-DECODE-V1
POST
/v1/payments?currency=VND
audience:payments-api
x-client-id:partner-42
x-key-id:key-2026-11
x-timestamp:<unix-seconds>
x-nonce:<32-lowercase-hex-characters>
content-type:application/json
x-content-sha256:<64-lowercase-hex-characters>
~~~

Quy tắc ký:

- **Method:** `POST` viết hoa chính xác; HTTP method token phân biệt hoa/thường.
- **Raw request target:** `/v1/payments?currency=VND`, bao gồm path và query theo contract; proxy không được âm thầm thay percent-encoding, route hoặc query.
- **Audience:** `payments-api` từ policy verifier, không đọc từ header forwarded do client tự khai.
- **Client/key ID:** gửi trong signed headers, để server chọn đúng secret và key rotation policy.
- **Timestamp/nonce:** Unix epoch seconds dạng thập phân chính tắc, nonce 16 byte ngẫu nhiên mã hóa 32 ký tự hex chữ thường; đều nằm trong phạm vi HMAC.
- **Content-Type/body:** chỉ chấp nhận `application/json` theo ví dụ; tính `SHA256(bodyBytes)` rồi đưa digest hex chữ thường vào canonical.
- **X-Signature:** không đưa vào chính canonical để tránh vòng tự tham chiếu. Nó là Base64 trên tag HMAC-SHA256 đầy đủ 32 byte.

Khi verifier nhận HTTP request, nó không lấy một `canonical` do client gửi rồi tin ngay; nó **tự dựng lại từ request thực nhận** và chính sách ký đã công bố. Nếu body, method, raw URI hoặc signed headers thay đổi, HMAC tính lại phải khác.

## 7. Java 17: giải mã strict Base64, kiểm tra tag rồi chống replay

Chương trình dưới đây tự tạo một request test, không thực sự gửi traffic ra mạng. Nó sử dụng `HttpRequest` để minh họa header, `MessageDigest` cho SHA-256 body, `Mac` cho HMAC-SHA256, `Base64.getDecoder()` cho signature và `MessageDigest.isEqual` để xác minh tag.

Để dễ sao chép/biên dịch, toàn bộ mã nằm trong một lớp `DecodeSignatureExample`. Secret 32 byte được tạo ngẫu nhiên **chỉ cho test nội bộ cùng tiến trình**. Ứng dụng thực phải cấp secret an toàn qua key manager; mọi replica verifier cần có cơ chế lookup và key rotation nhất quán.

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
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class DecodeSignatureExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String METHOD = "POST";
    private static final String RAW_TARGET = "/v1/payments?currency=VND";
    private static final String CLIENT_ID = "partner-42";
    private static final String KEY_ID = "key-2026-11";
    private static final String CONTENT_TYPE = "application/json";
    private static final long PAST_SECONDS = 300L;
    private static final long FUTURE_SECONDS = 60L;

    record SignedRequest(
        String method, String target, String clientId, String keyId,
        String timestamp, String nonce, String bodyHash,
        String signature, byte[] body
    ) {}

    // Demo một JVM, không tự hết hạn; production dùng shared atomic store + TTL.
    static final class DemoNonceStore {
        private final Set<String> seen = ConcurrentHashMap.newKeySet();

        boolean claim(String clientId, String nonce) {
            return seen.add(clientId + ":" + nonce);
        }
    }

    static String sha256Hex(byte[] data)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(data)
        );
    }

    static byte[] hmacSha256(byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonicalBytes);
    }

    static String canonical(String method, String target,
            String clientId, String keyId, String timestamp,
            String nonce, String bodyHash) {
        if (!METHOD.equals(method) || !RAW_TARGET.equals(target) ||
            !CLIENT_ID.equals(clientId) || !KEY_ID.equals(keyId) ||
            timestamp == null ||
            !timestamp.matches("[1-9][0-9]{0,18}") ||
            nonce == null || !nonce.matches("[0-9a-f]{32}") ||
            bodyHash == null ||
            !bodyHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException(
                "Canonical fields không đúng hợp đồng ký"
            );
        }
        return String.join("\n",
            "HMAC-SIGNATURE-DECODE-V1",
            method, target,
            "audience:payments-api",
            "x-client-id:" + clientId,
            "x-key-id:" + keyId,
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "content-type:" + CONTENT_TYPE,
            "x-content-sha256:" + bodyHash
        );
    }

    // Contract: HMAC-SHA256 32 byte, Base64 standard padded 44 ASCII chars.
    // Decoder của JDK có thể chấp nhận một số dạng không padding; round-trip
    // và format check dưới đây chủ động cấm những dạng khác.
    static byte[] decodeSignatureStrict(String encoded) {
        if (encoded == null ||
            !encoded.matches("[A-Za-z0-9+/]{43}=")) {
            return null;
        }
        final byte[] tag;
        try {
            tag = Base64.getDecoder().decode(encoded);
        } catch (IllegalArgumentException malformed) {
            return null;
        }
        if (tag.length != 32 ||
            !Base64.getEncoder().encodeToString(tag).equals(encoded)) {
            return null;
        }
        return tag;
    }

    static SignedRequest sign(byte[] secret, Clock clientClock)
            throws GeneralSecurityException {
        byte[] body = "{\"orderId\":\"ord-123\",\"amount\":50000}"
            .getBytes(StandardCharsets.UTF_8);
        byte[] nonceBytes = new byte[16];
        RANDOM.nextBytes(nonceBytes);
        String nonce = HexFormat.of().formatHex(nonceBytes);
        String timestamp = Long.toString(
            clientClock.instant().getEpochSecond()
        );
        String hash = sha256Hex(body);
        String message = canonical(
            METHOD, RAW_TARGET, CLIENT_ID, KEY_ID, timestamp, nonce, hash
        );
        byte[] tag = hmacSha256(
            secret, message.getBytes(StandardCharsets.UTF_8)
        );
        String signature = Base64.getEncoder().encodeToString(tag);
        return new SignedRequest(
            METHOD, RAW_TARGET, CLIENT_ID, KEY_ID,
            timestamp, nonce, hash, signature, body
        );
    }

    static boolean verify(SignedRequest request, byte[] secret,
            Clock serverClock, DemoNonceStore nonceStore)
            throws GeneralSecurityException {
        // HTTP production phải kiểm tra field duplication, request framing,
        // Content-Type và X-Signature tại parser/ingress đáng tin.
        if (request == null || request.body() == null) {
            return false;
        }
        byte[] suppliedTag = decodeSignatureStrict(request.signature());
        if (suppliedTag == null) {
            return false;
        }

        String computedHash = sha256Hex(request.body());
        if (!computedHash.equals(request.bodyHash())) {
            return false;
        }
        final String message;
        try {
            message = canonical(
                request.method(), request.target(),
                request.clientId(), request.keyId(), request.timestamp(),
                request.nonce(), computedHash
            );
        } catch (IllegalArgumentException invalidFields) {
            return false;
        }

        final long signedSeconds;
        try {
            signedSeconds = Long.parseLong(request.timestamp());
        } catch (NumberFormatException overflow) {
            return false;
        }
        long now = serverClock.instant().getEpochSecond();
        if (signedSeconds < now - PAST_SECONDS ||
            signedSeconds > now + FUTURE_SECONDS) {
            return false;
        }

        byte[] expectedTag = hmacSha256(
            secret, message.getBytes(StandardCharsets.UTF_8)
        );
        // Luôn so sánh full 32-byte tag, không so sánh prefix hoặc String.
        if (!MessageDigest.isEqual(expectedTag, suppliedTag)) {
            return false;
        }

        // Chỉ claim nonce khi HMAC hợp lệ. Production cần TTL và dùng chung
        // nhiều node, không dùng một Set cục bộ như demo.
        return nonceStore.claim(request.clientId(), request.nonce());
    }

    static SignedRequest withSignature(SignedRequest original, String value) {
        return new SignedRequest(
            original.method(), original.target(),
            original.clientId(), original.keyId(),
            original.timestamp(), original.nonce(),
            original.bodyHash(), value, original.body()
        );
    }

    static void rfc4231KnownAnswer() throws Exception {
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);
        byte[] tag = hmacSha256(
            key, "Hi There".getBytes(StandardCharsets.US_ASCII)
        );
        String expectedHex =
            "b0344c61d8db38535ca8afceaf0bf12" +
            "b881dc200c9833da726e9376c2e32cff7";
        if (!expectedHex.equals(HexFormat.of().formatHex(tag))) {
            throw new AssertionError("RFC 4231 HMAC-SHA256 vector sai");
        }
        String wire = Base64.getEncoder().encodeToString(tag);
        if (!Arrays.equals(tag, decodeSignatureStrict(wire))) {
            throw new AssertionError("Decode tag chuẩn không khớp");
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] secret = new byte[32]; // Test-only key, không dùng production.
        RANDOM.nextBytes(secret);
        Clock fixed = Clock.fixed(
            Instant.parse("2026-11-28T02:00:00Z"), ZoneOffset.UTC
        );
        rfc4231KnownAnswer();
        SignedRequest signed = sign(secret, fixed);

        HttpRequest httpRequest = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + signed.target()))
            .header("Content-Type", CONTENT_TYPE)
            .header("X-Client-Id", signed.clientId())
            .header("X-Key-Id", signed.keyId())
            .header("X-Timestamp", signed.timestamp())
            .header("X-Nonce", signed.nonce())
            .header("X-Content-SHA256", signed.bodyHash())
            .header("X-Signature", signed.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(signed.body()))
            .build(); // Không gửi request ra mạng trong ví dụ.

        if (!verify(signed, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Request hợp lệ phải verify thành công");
        }
        if (decodeSignatureStrict(signed.signature()) == null) {
            throw new AssertionError("Base64 chuẩn không decode được");
        }

        // Một padding '=' bị bỏ: JDK có thể decode nhưng contract từ chối.
        SignedRequest noPadding = withSignature(
            signed, signed.signature().substring(0, 43)
        );
        if (verify(noPadding, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Thiếu padding phải bị từ chối");
        }
        // URL-safe unpadded là encoding khác, cho dù cùng tag 32 byte.
        String urlSignature = Base64.getUrlEncoder().withoutPadding()
            .encodeToString(decodeSignatureStrict(signed.signature()));
        if (verify(withSignature(signed, urlSignature),
                secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Base64url sai contract phải bị từ chối");
        }

        String changed = (signed.signature().charAt(0) == 'A' ? "B" : "A")
            + signed.signature().substring(1);
        if (verify(withSignature(signed, changed),
                secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Tag bị sửa phải thất bại HMAC");
        }
        if (verify(withSignature(signed, signed.signature() + " "),
                secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("SP cuối phải bị từ chối");
        }
        String halfTag = Base64.getEncoder().encodeToString(
            Arrays.copyOf(decodeSignatureStrict(signed.signature()), 16)
        );
        if (verify(withSignature(signed, halfTag),
                secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Truncated tag phải bị từ chối");
        }

        // Body đổi sau khi ký: decode vẫn thành công nhưng HMAC/auth thất bại.
        byte[] tamperedBody = signed.body().clone();
        tamperedBody[0] ^= 1;
        SignedRequest tampered = new SignedRequest(
            signed.method(), signed.target(), signed.clientId(),
            signed.keyId(), signed.timestamp(), signed.nonce(),
            signed.bodyHash(), signed.signature(), tamperedBody
        );
        if (verify(tampered, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Body đã sửa phải bị từ chối");
        }

        DemoNonceStore replayStore = new DemoNonceStore();
        if (!verify(signed, secret, fixed, replayStore) ||
            verify(signed, secret, fixed, replayStore)) {
            throw new AssertionError("Replay nonce phải bị từ chối");
        }
        Clock late = Clock.offset(fixed, Duration.ofSeconds(301));
        if (verify(signed, secret, late, new DemoNonceStore())) {
            throw new AssertionError("Timestamp quá cũ phải bị từ chối");
        }
        System.out.println(
            "PASS: " + httpRequest.method() +
            ", RFC4231, strict Base64 decode, HMAC, replay"
        );
    }
}
~~~

### 7.1. Tại sao code kiểm tra alphabet, độ dài rồi mới decode?

`decodeSignatureStrict` chỉ cho phép **43 ký tự Base64 chuẩn và một `=` cuối**, nên tự giới hạn kích thước trước khi cấp phát byte array. Decoder không bị đưa một chuỗi header cực lớn tùy ý. Nó từ chối `-`, `_`, dấu cách, CR/LF, padding thừa, padding sai vị trí và thiếu `=`. Kết quả decode phải có **đúng 32 byte**; sau đó round-trip bảo đảm text đúng dạng canonical.

Hàm này cố ý trả `null` khi dữ liệu không hợp lệ, để verifier có thể trả **một kết quả authentication failure** thay vì làm lộ chi tiết parser hay ném lỗi chưa xử lý. Trong production, cần báo lỗi có mã phân loại an toàn, rate limit và quan trắc, không phản hồi token/key/secret cho caller.

### 7.2. Vì sao phải so sánh raw bytes?

~~~java
// ĐÚNG: so sánh hai full tag sau khi tính HMAC phía server.
boolean valid = MessageDigest.isEqual(expectedTag, suppliedTag);

// SAI: chỉ so sánh N byte đầu do client tự chọn.
// Arrays.equals(
//     Arrays.copyOf(expectedTag, suppliedTag.length), suppliedTag
// );
~~~

So sánh byte giúp tránh sai khác do encoding text, padding hoặc cách chuẩn hóa; `MessageDigest.isEqual` được thiết kế để tránh một số vấn đề timing so với phép so sánh ngừng tại byte sai đầu tiên. Tuy nhiên, **đừng tuyên bố toàn bộ HTTP verifier có thời gian thực thi không đổi**: các bước parse, key lookup, format rejection, kiểm tra độ dài và truy cập nonce store vẫn có độ trễ khác nhau. Chặn tag ngắn và mọi algorithm downgrade là yêu cầu an toàn riêng.

### 7.3. Giới hạn cố ý của mô phỏng

- `SignedRequest` là dữ liệu test, không phải HTTP parser an toàn. Verifier production phải đọc **đúng một** `X-Signature`, kiểm soát duplicate header, framing, CR/LF và nội dung thực nhận tại trusted ingress.
- `HttpRequest` chỉ minh họa cách gửi header và byte body; cần integration test để xác minh proxy/gateway không đổi raw URI, Content-Type, body hoặc signed headers.
- `CLIENT_ID`/`KEY_ID` cố định trong ví dụ. Trong production, server chọn secret theo identity/key ID và kiểm tra trạng thái active, audience, thuật toán, key rotation; client không thể tự quyết định algorithm hoặc tag length.
- `DemoNonceStore` là set trong một JVM, không có TTL. Nhiều verifier phải dùng shared atomic nonce store, TTL đủ dài và xử lý idempotency riêng.
- Code dùng HMAC-SHA256 full 32-byte tag theo contract. **Không** coi Base64URL/hex hoặc HMAC tag length khác là hợp lệ vì chúng cũng có thể decode thành byte.

## 8. Nếu hợp đồng dùng Base64url hoặc hex thì decode thế nào?

Ví dụ ở trên **chỉ chấp nhận Base64 chuẩn có padding**. Một hợp đồng khác có thể chọn Base64url **không padding**:

~~~java
import java.util.Base64;

static byte[] decodeBase64UrlNoPadding32(String text) {
    // HMAC-SHA256 full tag 32 bytes -> 43 ký tự Base64url không padding.
    if (text == null || !text.matches("[A-Za-z0-9_-]{43}")) {
        return null;
    }
    try {
        byte[] tag = Base64.getUrlDecoder().decode(text);
        if (tag.length != 32 ||
            !Base64.getUrlEncoder().withoutPadding()
                .encodeToString(tag).equals(text)) {
            return null;
        }
        return tag;
    } catch (IllegalArgumentException malformed) {
        return null;
    }
}
~~~

Hoặc một hợp đồng ký dùng **hex chữ thường**:

~~~java
import java.util.HexFormat;

static byte[] decodeLowerHex32(String text) {
    if (text == null || !text.matches("[0-9a-f]{64}")) {
        return null;
    }
    try {
        byte[] tag = HexFormat.of().parseHex(text);
        return tag.length == 32 ? tag : null;
    } catch (IllegalArgumentException malformed) {
        return null;
    }
}
~~~

**Quan trọng:** Chỉ áp dụng **một trong các hàm** theo signing contract đã được server xác định. Không viết hàm `decodeAnything()` thử lần lượt Base64, Base64url và hex trên một request. Nếu triển khai hỗ trợ nhiều API versions, việc chọn phiên bản phải được ràng buộc với identity/key/policy và signing transcript, tránh client tự hạ chuẩn ký.

## 9. Các lỗi phổ biến ở HTTP header, URL và proxy/gateway

### 9.1. Chữ ký trong header khác chữ ký nằm trong query

Base64 chuẩn có `+`, `/`, `=`. Trong **HTTP header** thông thường, các ký tự này có thể được biểu diễn trực tiếp theo contract. Nhưng nếu đưa chữ ký vào **query string** hoặc `application/x-www-form-urlencoded`, dấu `+` có thể bị parser form hiểu thành **space**, `=` có thể tương tác với cách tách cặp name/value, và `/` chịu tác động khi được đưa vào một path segment chưa encode đúng.

Không chỉ di chuyển `X-Signature` sang query rồi dùng cùng quy tắc parse. Một signed URL phải có **wire contract riêng**: lựa chọn Base64url, percent-encoding, xử lý query duplicate, thứ tự query, phạm vi canonical và cơ chế tránh ký vòng vào chính chữ ký. Với API bài này, chữ ký nằm ở **một header duy nhất**, không nằm trong URL.

### 9.2. Proxy và HTTP/2 có thể tạo chênh lệch biểu diễn

| Tình huống | Kết quả/rủi ro | Cách bảo vệ |
| --- | --- | --- |
| Proxy thay `+` thành space trong signature | Base64 strict từ chối | Không dùng form decoding cho header; giữ nguyên value đã ký. |
| Gateway trim SP/HTAB quanh signature | Thừa/thiếu ký tự ở wire có thể bị che | Chốt kiểm tra header tại trust boundary; **reject** ngoài contract thay vì tự trim. |
| Có hai `X-Signature` khác case | Gateway lấy cái đầu, backend lấy cái cuối | Reject duplicate trước khi gộp. |
| Proxy gộp `X-Signature: a` và `X-Signature: b` thành `a,b` | Chuỗi mới không đúng signature; parser differential | Reject security header đa trị. |
| HTTP/2 tên header lowercase | `x-signature` trên wire HTTP/2 | Header name HTTP case-insensitive; điều đó không cho phép đổi **value**. |
| Gateway thêm newline trong giá trị | Header injection hoặc decode mơ hồ | Reject CR/LF/obs-fold ở ingress; không dùng MIME decoder. |
| Proxy sửa body nhưng giữ signature | Decode signature vẫn PASS, HMAC phải FAIL | Recompute body digest và canonical từ byte thực nhận. |
| Proxy sửa raw path/query | Decode vẫn PASS, canonical HMAC phải FAIL | Verify tại trust boundary giữ đúng raw target. |
| Client gửi `X-Verified: true` | Backend có thể bypass HMAC nếu tin header | Xóa header ngoài boundary; xác thực gateway→backend. |
| Proxy phát lại nguyên request | Decode và HMAC đều vẫn PASS | Timestamp/nonce store chống replay. |

**Decode đúng không cứu một hợp đồng canonical sai.** Nếu verifier tính HMAC trên URI sau proxy rewrite nhưng backend route theo URI ban đầu, vẫn có nguy cơ sai đối tượng được xác minh. Cần kiểm thử qua các hop, đồng bộ điểm lấy method/raw path/query/header/body và chặn đường truy cập trực tiếp backend bỏ qua verifier.

### 9.3. Không log chữ ký thô

Chữ ký HMAC là dữ liệu xác thực của request trong một cửa sổ nhất định, nên không tự in vào log hoặc error response. Log có thể ghi **contract version, encoding expected, mã lỗi (invalid-format, invalid-length, signature-mismatch), request ID** và thời gian, nhưng tránh ghi shared secret, toàn bộ canonical chứa dữ liệu nhạy cảm, request body hoặc chữ ký có thể bị phát lại.

## 10. Decode, replay, key rotation và authorization

### 10.1. Timestamp và nonce nằm trong canonical, không chỉ ở header rời

Một request dùng signature đã decode hợp lệ **vẫn có thể là replay**. Sau khi HMAC hợp lệ:

1. Server kiểm tra timestamp theo clock của server, với cửa sổ policy rõ ràng (ví dụ quá khứ 300 giây, tương lai 60 giây).
2. Dùng nonce đã ký, ví dụ 16 byte ngẫu nhiên từ `SecureRandom` biểu diễn 32 ký tự hex chữ thường.
3. Claim nonce **nguyên tử** bằng shared store giữa các replica, chỉ sau khi HMAC hợp lệ; reject nonce đã dùng.
4. TTL nonce phải giữ tới khi request không còn được phép bởi cửa sổ timestamp cộng biên độ vận hành, không chỉ giữ một vài giây.

Nếu client retry request kinh doanh bằng **timestamp và nonce mới**, chữ ký mới vẫn decode và verify hợp lệ. Với thanh toán hoặc hành động có tác dụng phụ, cần **idempotency key được ký** và kiểm tra trạng thái nghiệp vụ để ngăn thực hiện trùng.

### 10.2. Key rotation

Signer đưa `x-client-id` và `x-key-id` vào canonical để server chọn đúng shared secret và policy phiên bản key. Server kiểm tra key active, revoked, audience, algorithm và thời hạn, có thể cho phép key cũ trong khoảng overlap được cấu hình. Không dùng chữ ký sai để tự động thử hàng loạt key cũ, thuật toán khác hoặc decoder khác. **Đổi encoding phải nằm trong kế hoạch version/contract**, không để client tự bật “compatibility mode”.

Một key đã bị thu hồi phải bị từ chối dù signature có đúng format Base64, HMAC có thể được tính đúng với secret cũ, và timestamp còn trong cửa sổ.

### 10.3. Authentication không cấp quyền

Signature decode đúng + HMAC đúng xác nhận **tính toàn vẹn các thành phần đã ký** và khả năng sử dụng secret tương ứng. Nó **không** cho phép client sửa mọi đơn hàng, chuyển tiền vượt hạn mức hoặc truy cập tenant khác. Backend phải kiểm tra **authorization** dựa trên identity đáng tin, action, tenant và resource đã được canonical ràng buộc.

## 11. Ma trận kiểm thử decode signature

Với hợp đồng **Base64 chuẩn padded, HMAC-SHA256 full 32 byte**, tạo một signer và verifier test. Mỗi ca độc lập dùng nonce mới hoặc fresh store; riêng ca replay cố ý giữ cùng nonce.

| Ca kiểm thử | Input/thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Happy path | Header có đúng 44 ký tự Base64 chuẩn, HMAC hợp lệ | Decode 32 byte, HMAC PASS; tiếp tục replay/authorization. |
| Test vector RFC 4231 | Key 20 byte `0x0b`, message `Hi There` | Tag HMAC-SHA256 có hex `b0344c61...2e32cff7`. |
| Không có X-Signature | Header thiếu | Reject, không tạo tag giả hay bỏ verify. |
| Header rỗng | `X-Signature:` | Reject format/length. |
| Mất padding | 43 ký tự Base64 chuẩn | Reject **dù decoder khoan dung có thể decode**. |
| Thừa padding | 44 ký tự + `=` | Reject. |
| Padding sai chỗ | Dấu `=` giữa chuỗi | Reject. |
| Base64url không padding | 43 ký tự với alphabet URL-safe | Reject theo contract dùng Base64 chuẩn padded. |
| Hex tag | 64 ký tự hex chữ thường | Reject vì sai encoding dù có thể decode thành 32 byte. |
| Tag cắt ngắn | Base64 của 8/16 byte prefix | Reject length; không so sánh prefix. |
| Tag dài bất thường | Base64 của 33 hoặc 64 byte | Reject length. |
| Ký tự ngoài alphabet | SP, tab, CR/LF, `,`, `:`, dấu `-`/`_` | Reject strict, không trim hoặc dùng MIME decoder. |
| Chữ ký chứa non-ASCII | Ký tự Unicode/UTF-8 trong header value | Reject vì alphabet không hợp lệ. |
| Noncanonical pad bits | Chuỗi decode ra cùng bytes nhưng encode lại không khớp | Reject canonical round-trip. |
| Đổi một ký tự trong tag | Base64 vẫn đúng form, decoded bytes khác | Decode PASS, **HMAC FAIL**. |
| Header trùng | Hai `X-Signature` khác case | Reject tại ingress trước khi gộp. |
| Body bị sửa | Giữ tag, đổi JSON amount | Body digest/HMAC FAIL. |
| URI/method bị sửa | Đổi `POST`/path/query | HMAC hoặc route policy FAIL. |
| Proxy rewrite | Proxy trim/chèn whitespace hoặc đổi nội dung | Không chấp nhận input biến đổi sai contract. |
| Replay | Gửi lại request với cùng timestamp, nonce, tag | Decode/HMAC vẫn đúng; nonce store reject lần sau. |
| Key rotation | Key active/overlap/revoked | Chỉ key còn được policy chấp nhận mới dùng verify. |
| Client không có quyền | Signature HMAC hợp lệ trên tài nguyên tenant khác | Authentication PASS, **authorization DENY**. |

### Câu hỏi tự kiểm tra

1. `Base64.getDecoder().decode(signature)` chạy thành công đã chứng minh client biết shared secret chưa? Vì sao?
2. Tại sao HMAC-SHA256 full 32 byte được mã hóa thành 44 ký tự Base64 chuẩn padded nhưng chỉ 43 ký tự Base64url không padding?
3. Base64url và Base64 chuẩn có nhất thiết khác ký tự trong **mọi** chữ ký không? Verifier nên chọn decoder theo điều gì?
4. Vì sao cần kiểm tra **round-trip canonical** thay vì chấp nhận tất cả chuỗi được decoder chuyển thành 32 byte?
5. Có thể bảo vệ chống forgery bằng cách so sánh 16 byte đầu của tag khi client gửi signature ngắn không? Điều kiện chính sách nào đang bị phá vỡ?
6. Nếu signature decode đúng và HMAC khớp nhưng proxy phát lại nguyên request, server cần cơ chế gì?
7. Vì sao secret rotation và authorization vẫn cần kiểm tra riêng, dù tag và wire encoding đều hợp lệ?

## 12. Checklist triển khai

- [ ] Chốt **một encoding** cho mỗi signing contract: Base64 chuẩn có padding, Base64url có/không padding hoặc hex; không đoán từ chuỗi.
- [ ] Chốt **thuật toán và full/truncated tag length** từ server policy, không để client chọn độ dài so sánh.
- [ ] Chỉ nhận **một** `X-Signature` từ trusted parser; reject duplicate case-insensitive, CR/LF và giá trị bị gộp mơ hồ.
- [ ] Có giới hạn độ dài encoded text **trước decode**, kiểm tra alphabet/ASCII/padding chính xác.
- [ ] Decode bằng đúng thư viện/variant, kiểm tra **số byte tag**, encode lại và so sánh text để xác nhận dạng canonical.
- [ ] Không `trim()`, bỏ whitespace hay dùng MIME decoder để lách qua header sai contract.
- [ ] Tự dựng canonical từ **method, raw URI, signed headers, body bytes/hash** thực nhận; đồng nhất newline LF, UTF-8 và thứ tự field.
- [ ] Chọn secret đúng identity + key ID, kiểm tra key active/rotation, algorithm, audience và scope.
- [ ] Tính HMAC-SHA256 trên canonical bytes và so sánh **full decoded tag** bằng `MessageDigest.isEqual`; không so sánh prefix hoặc thay thế HMAC bằng SHA-256 không khóa.
- [ ] Timestamp và nonce được ký; dùng nonce store nguyên tử có TTL, idempotency cho nghiệp vụ có side effect.
- [ ] Kiểm thử qua proxy/gateway, HTTP/1.1 ↔ HTTP/2, duplicate header, Base64 form vs URL-safe và path/query rewrite.
- [ ] HMAC hợp lệ phải đi tiếp **authorization theo tenant/action/resource**, không tự động cho phép thực thi nghiệp vụ.
- [ ] Không log secret, body nhạy cảm hoặc raw signature; trả mã lỗi xác thực nhất quán và giới hạn tần suất.

**Ghi nhớ:** **Decode signature chỉ là biến chuỗi chữ ký thành tag bytes đúng hợp đồng**, không phải bước xác thực thành công. Một verifier HMAC an toàn phải từ chối encoding mơ hồ, kiểm tra full tag length và canonical representation, tự tính HMAC trên request đã nhận rồi so sánh byte. Chống replay, key rotation, kiểm thử proxy/gateway và phân quyền vẫn cần được thực thi **sau và bên cạnh** bước giải mã chữ ký.
