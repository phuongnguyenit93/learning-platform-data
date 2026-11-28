# Timing attack khi so sánh chữ ký HMAC trong HTTP request authentication

> **Chương:** Constant-time comparison  
> **Chủ đề:** Timing attack  
> **Phạm vi module:** `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION` — Thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request bảo vệ method, URI, headers hoặc body. Người học thực hành kiểm tra chữ ký, chống replay với timestamp/nonce, key rotation, thử nghiệm proxy/gateway, đồng thời phân biệt authentication và authorization.

## 1. Timing attack là gì và vì sao liên quan đến HMAC?

**Timing attack** là một dạng **side-channel attack**: đối thủ suy luận thông tin từ thời gian chương trình phản hồi hoặc thực hiện một phép toán, thay vì đọc trực tiếp giá trị bí mật. Trong xác thực HTTP bằng HMAC, chỗ cần đặc biệt chú ý là **so sánh tag HMAC mà server vừa tính** với **tag mà client gửi**.

Một HMAC HTTP request thông thường có luồng:

~~~text
Request HTTP
  method + path/query + signed headers + raw body
                |
                v
        Canonical request bytes
                |
    secret key + HMAC-SHA-256
                |
                v
      expectedTag = 32 byte
                |
                +---- so sánh ---- receivedTag = decode(X-Signature)
                                      |
                                      v
                              accept hoặc reject
~~~

Phép HMAC có thể hoàn toàn đúng về toán học nhưng ứng dụng vẫn lộ thông tin qua **cách so sánh hai tag**. Câu lệnh so sánh không cẩn thận có thể dừng ngay khi thấy byte đầu tiên khác nhau. Khi đó thời gian thực hiện có thể phụ thuộc vào **vị trí byte sai đầu tiên**, vốn là thông tin phụ thuộc vào expected tag mà attacker không biết.

**Điểm học tập:** dùng phép so sánh phù hợp với dữ liệu mật mã có độ dài cố định, thay vì tự viết vòng lặp dừng sớm hoặc so sánh chuỗi tùy tiện. Tuy vậy, “so sánh tag ở thời gian ít phụ thuộc dữ liệu” **không** có nghĩa toàn bộ HTTP endpoint có thời gian phản hồi hoàn toàn không đổi.

### 1.1. Một ví dụ rất nhỏ

Giả sử expected tag (rút ngắn để dễ quan sát, **không phải độ dài HMAC-SHA-256 production**) là:

~~~text
Expected: [A1 B2 C3 D4]
Input 1:  [00 B2 C3 D4]   -> khác ở byte 1
Input 2:  [A1 00 C3 D4]   -> khác ở byte 2
Input 3:  [A1 B2 C3 00]   -> khác ở byte 4
~~~

Nếu bộ so sánh duyệt từ trái sang phải và `return false` khi gặp byte khác:

~~~text
Input 1: kiểm tra 1 byte rồi dừng
Input 2: kiểm tra 2 byte rồi dừng
Input 3: kiểm tra 4 byte rồi dừng
~~~

Số bước này phụ thuộc vào **độ dài prefix trùng với expected tag**. Về nguyên tắc, nếu có thể gửi nhiều chữ ký tùy chọn và đo được tín hiệu thời gian đủ chính xác qua nhiều lần thử, attacker có thể khai thác tín hiệu đó như một **timing oracle**.

Với HMAC-SHA-256 đầy đủ 32 byte và một API Internet có jitter, rate limit và anti-replay, khai thác thực tế có thể rất khó. Điều đó **không làm phép so sánh dừng sớm trở thành một thiết kế an toàn**. Lỗi có thể trở nên nguy hiểm hơn trong môi trường nội bộ, local process, tag bị rút ngắn hoặc một endpoint có độ trễ rất ổn định.

### 1.2. Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả timing side channel và giải thích vì sao **early-exit comparison** có thể rò vị trí byte khác đầu tiên.
2. Phân biệt **constant-time comparison của tag** với **constant-time behavior của toàn bộ request verifier**.
3. Sử dụng đúng `MessageDigest.isEqual` trong Java 17 để so sánh **hai byte array tag có độ dài cố định**.
4. Kiểm tra chữ ký HMAC-SHA-256 **đầy đủ 32 byte** sau strict Base64URL decoding; reject truncated tag, encoding không chuẩn và signed headers bị trùng.
5. Thiết kế canonical request gắn method, URI, headers, body digest, client ID/key ID, audience, timestamp và nonce.
6. Viết test minh họa early-exit **bằng số lần so sánh**, không dựa vào một benchmark thời gian dễ nhiễu.
7. Phân tích các timing oracles khác từ key lookup, parsing, path rewrite, error response và key rotation.
8. Kết hợp so sánh HMAC với chống replay, kiểm thử gateway và authorization trên resource thực.

## 2. Threat model: attacker đo được những gì?

Timing attack không đòi hỏi attacker nhìn thấy shared secret hay expected tag. Attacker thường có thể:

- Gửi request đến một API và tự chọn nhiều byte của `X-Signature`, path, query hoặc body.
- Quan sát **thời gian phản hồi**, trạng thái HTTP hoặc các khác biệt hành vi.
- Gửi lại nhiều request hoặc đo nhiều lần, trong giới hạn policy và môi trường mạng.
- Nếu ở gần server, quan sát tín hiệu ít bị jitter hơn so với Internet công cộng.

Attacker **không mặc nhiên** có khả năng quan sát CPU cycle hoặc kiểm soát network jitter. Cần phân biệt mức độ rủi ro theo ranh giới:

| Môi trường | Đặc điểm kênh thời gian | Cần xử lý thế nào |
|---|---|---|
| Gọi hàm tại cùng tiến trình | Tín hiệu số thao tác có thể rõ hơn | Không để so sánh tag dừng sớm |
| Tiến trình khác cùng máy | Cache, scheduler và tài nguyên dùng chung gây nhiễu nhưng cũng mở side channel | Dùng primitives đã thiết kế cho dữ liệu mật mã |
| Mạng nội bộ độ trễ thấp | Dễ thu mẫu lặp hơn | Constant-time tag compare, rate limit và kiểm soát oracle |
| Internet qua CDN/TLS/gateway | Có jitter, retry, cache, load balancing | Không dựa vào jitter để che lỗi; test toàn tuyến |
| API chỉ cho nonce một lần | Khó lặp một request giống hệt | Vẫn cần constant-time; attacker có thể tạo request mới nếu có quyền truy cập endpoint |

Điều quan trọng là **đường tấn công cụ thể phải tồn tại**. Một request sai cấu trúc có thể bị từ chối trước khi đến HMAC, còn một request có format đúng nhưng tag sai có thể chạm vào phép so sánh. Threat model phải nói rõ attacker kiểm soát trường nào, có bao nhiêu phép thử, và đo tín hiệu ở đâu.

### 2.1. “Biết prefix của tag” có đồng nghĩa biết secret?

Không. Nếu có một timing oracle thực sự làm lộ expected tag của **một message cố định**, rò tag đó **không trực tiếp phục hồi secret HMAC**. Tuy nhiên, nếu kẻ tấn công có thể dựng tag hợp lệ cho một request có ích trước khi timestamp/nonce hết hạn, họ có thể cố giả mạo **request đó**. Điều kiện khai thác thường phụ thuộc số lượt thử, chất lượng tín hiệu, replay policy và tính ổn định của thông điệp.

Không suy ra rằng “HMAC 256 bit thì timing attack là bất khả thi”, cũng không tuyên bố “chỉ cần đo RTT là lấy được 32 byte tag”. Cả hai đều bỏ qua những điều kiện rất cụ thể của oracle và môi trường triển khai.

## 3. Vì sao so sánh dừng sớm nguy hiểm?

### 3.1. Mã so sánh có lỗi

Ví dụ **không được sử dụng trong xác thực thực tế**:

~~~java
static boolean insecureEquals(byte[] expected, byte[] received) {
    if (expected.length != received.length) {
        return false;
    }
    for (int i = 0; i < expected.length; i++) {
        if (expected[i] != received[i]) {
            return false; // Dừng ngay khi byte đầu tiên khác.
        }
    }
    return true;
}
~~~

Nếu tag 32 byte và byte đầu khác nhau, vòng lặp có thể chỉ chạy một lần; nếu 31 byte đầu giống nhau, nó phải chạy thêm nhiều vòng trước khi trả false. Trong môi trường có một timing oracle đủ mạnh, khác biệt này có thể làm lộ thông tin về expected tag.

### 3.2. Các cách “tự sửa” vẫn có rủi ro

Một số cách thường thấy:

~~~java
// Không dùng làm lời giải bảo mật mặc định:
return Arrays.equals(expected, received);

// Không dùng để xác minh MAC vì so trên String:
return expectedHex.equals(receivedHex);

// Không dùng vòng lặp tự viết rồi tuyên bố constant time:
int diff = 0;
for (int i = 0; i < expected.length; i++) {
    diff |= expected[i] ^ received[i];
}
return diff == 0;
~~~

- `Arrays.equals` hoặc `String.equals` là API so sánh giá trị, **không có cam kết bảo mật rằng thời gian không phụ thuộc vị trí byte/ký tự khác**.
- Vòng lặp tích lũy `diff` không tự chứng minh constant-time trên mọi JIT, compiler, architecture và trường hợp **độ dài khác nhau**.
- Bộ so sánh thủ công có thể vô tình thêm một nhánh `break`, một indexed access không an toàn, hoặc logic có thời gian biến thiên theo nội dung.
- So sánh hex/Base64 string còn trộn lẫn **encoding canonicality** với phép so byte MAC.

**Khuyến nghị cho Java 17:** dùng `MessageDigest.isEqual(expectedBytes, receivedBytes)` sau khi xác minh **đúng độ dài 32 byte**, thay vì phát minh một hàm “constant-time” riêng.

### 3.3. API Java cần hiểu đúng mức bảo đảm

`MessageDigest.isEqual(byte[], byte[])` được Java API thiết kế cho phép so sánh digest/tag theo cách thời gian tính toán **không phụ thuộc vào nội dung byte** của các mảng trong điều kiện được API mô tả. Tuy nhiên, việc triển khai có thể phụ thuộc **độ dài mảng** và platform/JDK; cần phân biệt:

~~~text
Bảo đảm ta cần:
   Hai tag hợp lệ đều dài 32 byte.
   Thời gian so không tiết lộ vị trí byte khác đầu tiên.

Không được suy rộng:
   Toàn bộ verify() luôn mất đúng số nanosecond.
   Request invalid format sẽ có cùng thời gian với request valid.
   Key lookup/serialization/nonce store không có side channel.
~~~

Một request có chữ ký chỉ dài 4 byte có thể bị reject ngay ở validation. **Độ dài signature là dữ liệu hiển thị công khai do attacker gửi**, nên việc từ chối sớm vì length sai không làm lộ expected MAC prefix. Điều cần tránh là **branch phụ thuộc vào nội dung expected tag** khi so hai tag đã có độ dài hợp lệ.

## 4. Thiết kế quy tắc so tag HMAC-SHA-256

Trong module này, giả sử hợp đồng mẫu:

~~~text
Algorithm:            HmacSHA256
MAC length:           32 byte (256 bit), KHÔNG truncate
Signature transport:  Base64URL without padding
Encoded length:       43 ASCII characters
Header name:          X-Signature
Header multiplicity:  Exactly one field value
MAC comparison:       MessageDigest.isEqual(expected32, received32)
~~~

### 4.1. Vì sao Base64URL dài 43?

Với 32 byte HMAC:

~~~text
32 byte = 256 bit
Base64URL: ceil(256 / 6) = 43 ký tự nếu không padding
Base64 chuẩn có padding: 44 ký tự
Hex: 64 ký tự
~~~

Đây chỉ là **biểu diễn** của cùng tag 32 byte. Không được so tag dài 43 ký tự với expected hex 64 ký tự, và không được cho client tự chọn algorithm/encoding theo sở thích.

### 4.2. Strict decoding trước khi so sánh

Hợp đồng cần quy định:

1. Từ chối request không có hoặc có **nhiều** `X-Signature` headers.
2. Từ chối header chứa CR/LF/control character, Unicode không phải ASCII hoặc comma-joined values.
3. Nhận đúng **43 ký tự** thuộc alphabet `[A-Za-z0-9_-]`; **không có dấu `=` padding**.
4. Dùng `Base64.getUrlDecoder()`; kết quả bắt buộc **32 byte**.
5. Encode lại bằng `Base64.getUrlEncoder().withoutPadding()` và yêu cầu **bằng đúng chuỗi đầu vào**.
6. Không tự thử `Base64.getDecoder()`, `HexFormat.parseHex()` hoặc MIME decoder nếu hợp đồng chỉ hỗ trợ Base64URL no-pad.
7. Tính lại HMAC từ **canonical request bytes tại đúng trust boundary**, so byte tag với `MessageDigest.isEqual`.

Bước re-encode quan trọng vì **pad bits** ở ký tự Base64URL cuối phải là 0. Với 32 byte tag, ký tự cuối có **hai bit thấp không mang dữ liệu**; một decoder chấp nhận nonzero pad bits có thể cho hai chuỗi khác nhau cùng giải ra 32 byte. Round-trip chặn biểu diễn không chuẩn này.

### 4.3. Không so một prefix/truncated tag

Tránh:

~~~java
// Sai: so chỉ prefix hoặc số byte do client yêu cầu.
int len = received.length;
return MessageDigest.isEqual(
        Arrays.copyOf(expected, len), received);
~~~

Nếu attacker gửi một tag rất ngắn rồi được server chấp nhận so prefix, độ khó giả mạo có thể giảm từ 256 bit xuống rất ít bit. **Luôn xác nhận received tag đúng 32 byte** và so toàn bộ tag theo hợp đồng này.

Một giao thức dùng truncated HMAC có thể hợp lệ nếu **cố định** chiều dài đủ an toàn và được thiết kế đúng; nhưng không tự biến full HMAC thành “length do client chọn”.

### 4.4. Đặt câu hỏi đúng về thời gian

| Điều kiện | Có nên cố làm thời gian hoàn toàn bằng nhau? | Lý do |
|---|---|---|
| Tag định dạng sai, không đủ 32 byte | Không cần chạy HMAC giả chỉ để che public format | Định dạng công khai |
| Tag đủ 32 byte nhưng byte đầu/cuối sai | **Có, không rò vị trí sai** | Nội dung expected tag không công khai |
| Raw body 0 byte hoặc 1 MB | Không thể mặc nhiên bằng thời gian | Băm SHA-256 tốn thời gian theo số byte |
| Client/key ID khác nhau | Cần đánh giá side channel của lookup | Thời gian truy cập key store có thể biến thiên |
| Nonce đã dùng/ chưa dùng | Có thể có timing và response khác nhau | Replay policy, không nhất thiết rò secret |
| Authorization cho resource khác nhau | Không mặc nhiên constant-time | Cần policy, chống enumeration và leakage theo threat model |

## 5. HMAC request authentication có nhiều ranh giới ngoài phép so tag

Một pipeline đúng không chỉ là:

~~~text
expected = HMAC(secret, bytes)
return MessageDigest.isEqual(expected, received)
~~~

Mà là:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway/Proxy
    participant V as HMAC Verifier
    participant K as Key Store
    participant N as Atomic Nonce Store
    participant A as Authorization
    C->>C: Tạo canonical bytes, HMAC và Base64URL
    C->>G: HTTP + X-Signature + keyId + timestamp + nonce
    G->>V: Request ở điểm verify
    V->>V: Kiểm tra framing, header count và tag format
    V->>K: Tra key theo clientId/keyId/audience
    K-->>V: Key state + secret đúng
    V->>V: Validate timestamp và canonical request
    V->>V: HmacSHA256 và isEqual 32-byte tags
    V->>N: Reserve nonce sau MAC đúng
    N-->>V: Thành công/đã sử dụng
    V->>A: Authenticated principal + parsed request
    A->>A: Check action/resource/tenant
~~~

### 5.1. Canonicalization phải ổn định

Một biến thể hợp đồng ký minh họa `hmac-timing-v1` bao gồm **10 dòng**:

| Dòng | Thành phần | Quy tắc |
|---|---|---|
| 1 | Version | Literal `hmac-timing-v1` |
| 2 | Audience | Literal `payments-api-production` |
| 3 | Method | `POST` theo method thực tế |
| 4 | Raw target | `/v1/transfers?mode=check` hoặc `?mode=commit` |
| 5 | Content-Type | `application/json` |
| 6 | Client ID | `X-Client-Id` |
| 7 | Key ID | `X-Key-Id` |
| 8 | Timestamp | `X-Timestamp`, Unix epoch seconds |
| 9 | Nonce | `X-Nonce`, Base64URL no-padding của 16 byte CSPRNG |
| 10 | Body digest | Lowercase hex SHA-256 của **raw request body bytes** |

Các dòng nối bằng LF (`\n`), không có LF cuối; chuỗi chuyển sang UTF-8. HMAC-SHA-256 tính trên canonical bytes với secret 32 byte của đúng client/key/audience. Signature mang tag Base64URL no-pad **ngoài** canonical string (tránh tự tham chiếu).

Ví dụ:

~~~http
POST /v1/transfers?mode=check HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <base64url-hmac-sha256>

{"transferId":"t-42","amount":150000}
~~~

Canonical string:

~~~text
hmac-timing-v1
payments-api-production
POST
/v1/transfers?mode=check
application/json
merchant-17
key-2026-11
1795824000
b75sZVQmhTBcfnX-bNbGqw
<sha256-hex-cua-raw-body>
~~~

Dòng cuối là **placeholder**: phải tính digest thực từ bytes được nhận. Với body rỗng, digest SHA-256 là:

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Đây chỉ là **hợp đồng học tập** để minh họa; không mặc nhiên tương thích RFC 9421 hoặc các API HMAC của bên thứ ba. Hợp đồng thật phải quy định cả path/query percent-encoding, duplicate signed headers, body encoding, method override và host/audience.

### 5.2. Sai canonical request không sửa được bằng constant-time comparison

Nếu client ký path `/v1/transfers?mode=check` nhưng gateway rewrite thành `/v1/transfers?mode=commit`, expected HMAC tại backend sẽ khác. Dù dùng `MessageDigest.isEqual` đúng, kết quả vẫn **fail** — và **phải fail** khi request bị thay đổi.

Tương tự, nếu tầng policy nhìn một query/path còn router xử lý một giá trị khác vì normalize, MAC đúng cũng không chứng minh authorization đúng. Constant-time comparison **không chữa** các lỗi canonicalization, HTTP parameter pollution hay method confusion.

## 6. Java 17: lỗi so sánh prefix và cách xác minh an toàn

Mã Java sau được viết để **chạy độc lập trên JDK 17+**, không cần Gradle, Spring hoặc thư viện ngoài. Nó có hai phần:

- **Thực nghiệm an toàn bằng số bước:** `prefixComparisons` mô phỏng số byte mà một phép so dừng sớm đọc trước khi trả false. Không phải chương trình khai thác timing trên mạng.
- **Lõi verifier:** strict Base64URL no-pad, HMAC-SHA-256 đầy đủ 32 byte, `MessageDigest.isEqual`, canonical request, cùng unit tests/tampering và vector HMAC chuẩn RFC 4231.

### 6.1. Mã nguồn hoàn chỉnh

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class TimingSafeHmacDemo {
    private static final String ALGORITHM = "HmacSHA256";
    private static final String VERSION = "hmac-timing-v1";
    private static final String AUDIENCE = "payments-api-production";

    private TimingSafeHmacDemo() {}

    public record Request(
            String method, String rawTarget, String contentType,
            String clientId, String keyId, String timestamp,
            String nonce, byte[] rawBody) {
        public Request {
            if (rawBody == null) {
                throw new IllegalArgumentException("Missing body bytes");
            }
            rawBody = rawBody.clone();
        }
        @Override
        public byte[] rawBody() {
            return rawBody.clone();
        }
    }

    // CHỈ minh họa vấn đề: số phép so phụ thuộc prefix trùng.
    // TUYỆT ĐỐI KHÔNG dùng làm verifier production.
    public static int prefixComparisons(
            byte[] expected, byte[] candidate) {
        if (expected.length != candidate.length) return 0;
        for (int i = 0; i < expected.length; i++) {
            if (expected[i] != candidate[i]) return i + 1;
        }
        return expected.length;
    }

    private static byte[] changedAt(byte[] input, int index) {
        byte[] result = input.clone();
        result[index] ^= 1;
        return result;
    }

    private static String asciiField(String input, int max) {
        if (input == null || input.isEmpty() || input.length() > max
                || input.chars().anyMatch(c -> c < 0x21 || c > 0x7E)) {
            throw new IllegalArgumentException("Bad signed field");
        }
        return input;
    }

    private static String canonicalContentType(String input) {
        if (input == null || input.length() > 128
                || input.chars().anyMatch(
                        c -> (c < 0x20 && c != '\t') || c > 0x7E)) {
            throw new IllegalArgumentException("Bad Content-Type");
        }
        String text = input.trim().toLowerCase(Locale.ROOT);
        if (!"application/json".equals(text)) {
            throw new IllegalArgumentException("Unsupported media type");
        }
        return text;
    }

    public static byte[] canonicalBytes(Request request)
            throws GeneralSecurityException {
        if (request == null || !"POST".equals(request.method())) {
            throw new IllegalArgumentException("Unsupported method");
        }
        String target = asciiField(request.rawTarget(), 2048);
        if (!target.matches(
                "/v1/transfers\\?mode=(?:check|commit)")) {
            throw new IllegalArgumentException("Unsupported raw target");
        }
        String client = asciiField(request.clientId(), 64);
        String keyId = asciiField(request.keyId(), 64);
        String time = asciiField(request.timestamp(), 20);
        String nonce = asciiField(request.nonce(), 24);
        if (!client.matches("[A-Za-z0-9_-]+")
                || !keyId.matches("[A-Za-z0-9_-]+")
                || !time.matches("[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException("Bad metadata");
        }
        final byte[] nonceBytes;
        try {
            nonceBytes = Base64.getUrlDecoder().decode(nonce);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Invalid nonce", ex);
        }
        if (nonceBytes.length != 16
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(nonceBytes).equals(nonce)) {
            throw new IllegalArgumentException("Non-canonical nonce");
        }
        byte[] body = request.rawBody();
        if (body.length > 64 * 1024) {
            throw new IllegalArgumentException("Body too large");
        }
        String bodyHex = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));
        String canonical = String.join("\n",
                VERSION, AUDIENCE, request.method(), target,
                canonicalContentType(request.contentType()),
                client, keyId, time, nonce, bodyHex);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] mac(byte[] secret, byte[] canonical)
            throws GeneralSecurityException {
        if (secret == null || secret.length == 0
                || canonical == null) {
            throw new IllegalArgumentException("Invalid HMAC input");
        }
        Mac engine = Mac.getInstance(ALGORITHM);
        engine.init(new SecretKeySpec(secret, ALGORITHM));
        return engine.doFinal(canonical);
    }

    public static String sign(Request request, byte[] secret)
            throws GeneralSecurityException {
        if (secret == null || secret.length != 32) {
            throw new IllegalArgumentException("32-byte test secret needed");
        }
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(mac(secret, canonicalBytes(request)));
    }

    public static byte[] decodeTagStrict(List<String> fields) {
        // HTTP adapter phải reject duplicate field occurrences
        // trước khi xử lý nếu proxy đã gộp/mất thông tin.
        if (fields == null || fields.size() != 1) {
            throw new IllegalArgumentException(
                    "Exactly one X-Signature required");
        }
        String encoded = fields.get(0);
        if (encoded == null
                || !encoded.matches("[A-Za-z0-9_-]{43}")) {
            throw new IllegalArgumentException(
                    "Expected 43 Base64URL no-padding chars");
        }
        final byte[] decoded;
        try {
            decoded = Base64.getUrlDecoder().decode(encoded);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Invalid Base64URL", ex);
        }
        if (decoded.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(decoded).equals(encoded)) {
            throw new IllegalArgumentException(
                    "Wrong length or non-canonical tag");
        }
        return decoded;
    }

    // Đây chỉ là CORE: không gồm key lookup/clock/nonce/authorization.
    public static boolean verifyMac(
            Request request, byte[] secret, List<String> fields)
            throws GeneralSecurityException {
        if (secret == null || secret.length != 32) return false;
        final byte[] received;
        try {
            received = decodeTagStrict(fields);
        } catch (IllegalArgumentException invalid) {
            return false;
        }
        final byte[] expected;
        try {
            expected = mac(secret, canonicalBytes(request));
        } catch (IllegalArgumentException invalidRequest) {
            return false;
        }
        // Cả hai mảng đều đúng 32 byte tại đây.
        return MessageDigest.isEqual(expected, received);
    }

    private static void require(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    private static void expectInvalid(Runnable operation) {
        boolean rejected = false;
        try {
            operation.run();
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        require(rejected, "Input should be rejected");
    }

    private static void testRfc4231Case1()
            throws GeneralSecurityException {
        // RFC 4231 test case 1: key = 20 byte 0x0B,
        // message = "Hi There", expected HMAC-SHA-256:
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0B);
        byte[] message = "Hi There".getBytes(
                StandardCharsets.US_ASCII);
        String expectedHex =
                "b0344c61d8db38535ca8afceaf0bf12b"
              + "881dc200c9833da726e9376c2e32cff7";
        require(HexFormat.of().formatHex(mac(key, message))
                .equals(expectedHex), "RFC 4231 known-answer");
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        testRfc4231Case1();

        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret);
        byte[] nonceBytes = new byte[16];
        new SecureRandom().nextBytes(nonceBytes);
        String nonce = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(nonceBytes);
        String timestamp = Long.toString(
                Instant.now().getEpochSecond());

        Request request = new Request(
                "POST", "/v1/transfers?mode=check",
                "application/json", "merchant-17", "key-2026-11",
                timestamp, nonce,
                "{\"transferId\":\"t-42\",\"amount\":150000}"
                        .getBytes(StandardCharsets.UTF_8));

        String signature = sign(request, secret);
        byte[] tag = decodeTagStrict(List.of(signature));
        require(tag.length == 32, "Full 32-byte tag");
        require(verifyMac(request, secret, List.of(signature)),
                "Valid HMAC");

        // Không đo wall-clock: đếm số byte mà lối viết sai
        // phải so trước khi gặp mismatch.
        require(prefixComparisons(
                tag, changedAt(tag, 0)) == 1,
                "First-byte mismatch uses one comparison");
        require(prefixComparisons(
                tag, changedAt(tag, 31)) == 32,
                "Last-byte mismatch uses 32 comparisons");

        // Tag 32 byte khác nhưng encode hợp lệ:
        String wrongFirst = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(changedAt(tag, 0));
        String wrongLast = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(changedAt(tag, 31));
        require(!verifyMac(request, secret, List.of(wrongFirst)),
                "First-byte MAC mismatch must fail");
        require(!verifyMac(request, secret, List.of(wrongLast)),
                "Last-byte MAC mismatch must fail");

        Request changedMode = new Request(
                "POST", "/v1/transfers?mode=commit",
                request.contentType(), request.clientId(),
                request.keyId(), request.timestamp(),
                request.nonce(), request.rawBody());
        require(!verifyMac(changedMode, secret, List.of(signature)),
                "Changed signed target must fail");
        Request changedBody = new Request(
                request.method(), request.rawTarget(),
                request.contentType(), request.clientId(),
                request.keyId(), request.timestamp(),
                request.nonce(), "{\"amount\":900000}"
                        .getBytes(StandardCharsets.UTF_8));
        require(!verifyMac(changedBody, secret, List.of(signature)),
                "Changed body must fail");

        // Reject ambiguous/malformed signature representations.
        expectInvalid(() -> decodeTagStrict(List.of()));
        expectInvalid(() -> decodeTagStrict(
                List.of(signature, signature)));
        expectInvalid(() -> decodeTagStrict(
                List.of(signature + "=")));
        expectInvalid(() -> decodeTagStrict(
                List.of(" " + signature)));
        expectInvalid(() -> decodeTagStrict(
                List.of(signature + ",other")));
        expectInvalid(() -> decodeTagStrict(
                List.of(signature + "\r\nX-Key-Id: other")));

        // HMAC code tự nó không chống replay: lần verify thứ hai
        // vẫn đúng; nonce store sẽ từ chối request lặp.
        require(verifyMac(request, secret, List.of(signature)),
                "MAC correctness does not imply freshness");

        System.out.println("PASS HMAC timing-safe comparison tests");
    }
}
~~~

### 6.2. Chạy ví dụ

Lưu nội dung thành `TimingSafeHmacDemo.java`, sử dụng JDK 17+:

~~~bash
javac TimingSafeHmacDemo.java
java TimingSafeHmacDemo
~~~

Kết quả mong đợi:

~~~text
PASS HMAC timing-safe comparison tests
~~~

### 6.3. Những điều mã ví dụ chứng minh và chưa chứng minh

**Chứng minh bằng kiểm tra logic:**

- Vector RFC 4231 xác nhận HMAC-SHA-256 tạo đúng tag với known-answer độc lập.
- Phép so sánh dừng sớm có số thao tác phụ thuộc vào vị trí mismatch.
- Strict Base64URL decoding loại bỏ tag thiếu/sai format; received tag phải đủ 32 byte.
- `MessageDigest.isEqual` được dùng cho hai tag 32 byte, không so prefix.
- Thay URI/parameter/body sau ký khiến MAC không khớp.
- Verify lại cùng request vẫn khớp ở **lớp MAC**, cho thấy anti-replay phải là bước khác.

**Chưa chứng minh / chưa triển khai:** không đo độ trễ thực tế của JVM qua JIT/GC/CPU/mạng; không có key store, rotation, clock skew, nonce store, signed header multiplicity từ HTTP parser, servlet/gateway hay authorization. Ví dụ dùng secret ngẫu nhiên cho test và body giới hạn 64 KiB. Không được dùng `verifyMac` nguyên trạng làm middleware production.

## 7. Các timing oracle khác ngoài so tag

Sử dụng `MessageDigest.isEqual` là quan trọng nhưng chưa đủ. Nhiều nhánh khác trong verifier có thể làm thời gian khác nhau.

### 7.1. Key lookup và key enumeration

Tưởng tượng:

~~~text
X-Key-Id không tồn tại -> trả 401 rất nhanh
X-Key-Id tồn tại       -> đọc secret, tính HMAC rồi trả 401
~~~

Thời gian và message lỗi có thể vô tình giúp dò **key ID nào tồn tại**. Đây là một loại oracle khác, không trực tiếp làm lộ prefix HMAC. Tùy threat model, một hệ thống có thể cân nhắc thực hiện phép tính HMAC bằng **dummy key cố định nội bộ** cho lookup miss nhằm giảm khác biệt thời gian; nhưng:

- Dummy key phải **không bao giờ** cấp quyền, kể cả nếu MAC khớp.
- Đây không phải yêu cầu chung cho mọi API, và không bảo đảm thời gian toàn pipeline bằng nhau.
- Phải có giới hạn CPU, input size và rate limiting để tránh biến key miss thành DoS.
- Việc sử dụng key giả không được làm mất khả năng phân biệt lỗi nội bộ khi vận hành.

**Ưu tiên:** không cung cấp thông báo tồn tại/key state cho client không tin cậy; phân quyền key theo client/audience, giảm thông tin timing không cần thiết và kiểm thử theo mô hình đe dọa.

### 7.2. Thử mọi secret khi key ID sai

Một lỗi thiết kế:

~~~text
Không tìm thấy keyId
    -> for mỗi secret của mọi tenant
         tính HMAC và so
    -> nếu bất kỳ secret nào đúng thì accept
~~~

Vấn đề không chỉ là thời gian thay đổi theo vị trí key trong vòng lặp. Nó có thể gây **cross-tenant confusion**, tốn CPU và bỏ qua policy rotation/audience. Đúng hơn phải lookup **đúng một key record** theo `(clientId, keyId, audience)`, kiểm tra trạng thái và xử lý fail closed khi record không hợp lệ.

### 7.3. Signed headers, parser và format errors

Các request malformed có thể bị reject trước HMAC, ví dụ:

- `X-Signature` thiếu hoặc chứa 12 ký tự thay vì 43.
- Có hai `X-Signature` hoặc signed header bị duplicate.
- Path/query sai percent-encoding, body quá dài.
- Content-Type sai, timestamp không parse được.

Việc **khác thời gian do dữ liệu công khai sai format** không tự động là timing leak của secret. Nhưng các nhánh lỗi trả ra thông tin khác nhau về key tồn tại, principal có quyền, hoặc tag prefix đúng có thể làm tăng bề mặt oracle. Nên có **policy response thống nhất khi thích hợp**, giới hạn input và log nội bộ ở mức cần thiết.

### 7.4. Timestamp/nonce và trạng thái replay

Thời gian trả về của một request đã dùng nonce so với một request có nonce mới có thể khác vì truy cập kho dữ liệu. Đây không nhất thiết là lỗi constant-time comparison, nhưng có thể tiết lộ trạng thái của một request hoặc hoạt động hệ thống.

Trong hệ thống tài chính, cần đánh giá liệu việc cho phép người gọi quan sát “nonce này đã dùng” có gây rò thông tin nhạy cảm hay không. Đừng giải quyết bằng việc bỏ nonce check: **chống replay** là yêu cầu bảo mật độc lập.

### 7.5. Authorization và timing

Sau khi HMAC đúng, việc kiểm tra quyền trên resource có thể tốn thời gian khác nhau cho “resource không tồn tại”, “resource tồn tại nhưng không thuộc tenant” và “resource tồn tại thuộc tenant”. Tùy chính sách chống enumeration, API có thể cần giảm khác biệt status/body/timing. **Authentication không thay thế authorization**, và constant-time tag compare cũng không ngăn việc lộ tồn tại tài nguyên ở tầng nghiệp vụ.

## 8. Chống replay và key rotation sau khi HMAC đúng

### 8.1. Timestamp và nonce chống replay

HMAC chỉ xác nhận **message được ký bằng secret đúng** và vẫn còn nguyên theo hợp đồng. Nếu attacker sao chép nguyên HTTP request cùng signature, phép so tag có thể tiếp tục trả true.

Một policy minh họa:

~~~text
nowSeconds - 300 <= signedTimestamp <= nowSeconds + 300
clientId/keyId/audience đã được xác minh
MAC đúng với secret lookup
nonceScope = (clientId, keyId, audience, nonce)
atomic reserve nonce SAU khi MAC đúng, TTL đủ phủ cửa sổ
~~~

Ví dụ Redis có thao tác tương đương `SET key 1 NX EX 600` cho nonce; điều kiện thời gian ±300 giây và TTL 600 giây là **tham số minh họa** cần được kiểm chứng với clock skew/multi-node. Không làm GET rồi SET (race). Không reserve nonce trước khi MAC đúng vì attacker có thể dùng MAC giả chiếm nonce hợp lệ. Nếu nonce store không khả dụng và anti-replay bắt buộc, phải **fail closed**.

Đối với request có side effect, retry với nonce **mới** vẫn có thể tạo giao dịch lặp. Cần idempotency key và logic nghiệp vụ riêng; nếu key này ảnh hưởng hành vi, nó phải được bảo vệ trong dữ liệu ký.

### 8.2. Key rotation và trạng thái khóa

| Trạng thái key | Ý nghĩa | Kết quả |
|---|---|---|
| `ACTIVE` | Secret có hiệu lực để xác minh | Có thể tính HMAC |
| `VERIFY_ONLY` | Key cũ trong khoảng overlap | Verify theo deadline |
| `REVOKED` | Key bị thu hồi | Reject ngay cả khi HMAC khớp |
| Không thuộc client/audience | Lookup sai principal/dịch vụ | Reject, không thử key tenant khác |
| Không tồn tại | Không có key record hợp lệ | Reject, không fallback secret mặc định |

Một vòng rotate an toàn có thể tạm duy trì key cũ ở trạng thái `VERIFY_ONLY` rồi chuyển sang `REVOKED` sau deadline. Sender phải chuyển sang key ID mới có secret độc lập. Trong Java, mỗi phép tính `Mac` cần được `init` bằng đúng secret; `reset()` không thay secret.

Việc key store trả lời nhanh/chậm cho key ACTIVE, REVOKED hoặc absent có thể là một kênh timing theo threat model. Tuy vậy, giảm thông tin lỗi không đồng nghĩa được bỏ check trạng thái khóa.

## 9. Gateway/proxy và constant-time comparison

Một HMAC verifier có thể so tag an toàn nhưng đứng sau proxy đổi request:

~~~text
Client ký:     POST /v1/transfers?mode=check
Gateway sửa:   POST /v1/transfers?mode=commit
Verifier tính: HMAC trên mode=commit
Kết quả:       MAC không khớp (đúng kỳ vọng)
~~~

| Thay đổi ở gateway/framework | Rủi ro | Test/biện pháp |
|---|---|---|
| Path rewrite / strip prefix | Canonical target khác | Verify trước rewrite hoặc dùng original target đáng tin |
| Query reorder, encode/decode | Hai phía ký khác bytes | Chốt raw/canonical query contract |
| Auto-decompress request body | Body hash đổi | Verify trước biến đổi hoặc theo hợp đồng decoded-body riêng |
| Chuyển HTTP/2 `:path` sang HTTP/1.1 | Thay representation của URI | Test method/target tại điểm verify |
| Gộp `X-Signature` headers | Lost multiplicity / comma-list | Reject ở edge; adapter chỉ nhận một value |
| Proxy/SDK thêm OWS vào field | Strict format có thể reject | Thống nhất HTTP parser/OWS rules |
| Header `X-Key-Id` bị thay | Lookup key sai, MAC fail | Ký header ID, chặn giả mạo metadata nội bộ |
| Gateway tự cấp dấu “verified” | Backend có thể tin header attacker | Strip header của client, xác thực kênh proxy → backend |
| Load balancing qua nhiều node | Nonce local không đồng bộ | Shared atomic nonce store |
| Cache trả response trước verifier | Bỏ qua xác thực hoặc policy | Chặn truy cập private trước auth/cache |

**Không tin `X-Original-URI` hay `X-Verified-Client` do client gửi trực tiếp.** Chỉ proxy đáng tin được phép thiết lập metadata nội bộ sau khi đã strip các giá trị ngoài, bảo vệ kết nối proxy–backend và xác thực đúng ranh giới ký.

### 9.1. Một timing test ở local không chứng minh an toàn end-to-end

Nếu test `MessageDigest.isEqual` trong unit test rồi kết luận “endpoint không thể bị timing attack”, ta bỏ qua key lookup, gateway latency, cache behavior, parser, nonce store, authorization và exception handling.

Nên phân tầng kiểm thử:

- **Unit:** decode signature, fixed length, HMAC known-answer, so tag đúng.
- **Component:** HTTP request filter, duplicate headers, route grammar, raw body/target.
- **Integration:** gateway HTTP/1.1/2, rewrite, decompress, key lookup và cache.
- **Security review:** xác định dữ liệu bí mật nào có thể làm thay đổi nhánh/thời gian, rate limit và thông tin lỗi; nếu cần đo timing, dùng phương pháp thống kê và môi trường lặp lại.

## 10. Kiểm thử timing leak một cách có ý nghĩa

### 10.1. Unit tests không dựa vào đo nanosecond

| Trường hợp | Input | Kỳ vọng |
|---|---|---|
| Tag 32 byte, MAC đúng | Ký bằng secret đúng | Verify true |
| Byte đầu sai | Tag có cùng độ dài nhưng đổi byte 0 | Verify false |
| Byte cuối sai | Tag có cùng độ dài nhưng đổi byte 31 | Verify false |
| So sánh dừng sớm minh họa | Số bytes được kiểm tra | Phụ thuộc vị trí mismatch |
| RFC 4231 | Known-answer HMAC-SHA-256 | MAC đúng từng byte |
| Signature thiếu | Không có header | Reject |
| Duplicate signature | Hai field values | Reject |
| Truncated Base64URL | Ít hơn 43 ký tự | Reject |
| Padded Base64URL | Thêm `=` | Reject |
| Non-canonical pad bits | Đổi bit cuối không có dữ liệu | Reject |
| Signature hex | 64 ký tự thay vì 43 | Reject |
| MAC sai nhưng Base64URL hợp lệ | 32 byte bất kỳ khác expected | Verify false |
| Query/body/method đổi sau ký | Giữ tag gốc | Verify false hoặc reject validation |
| Replay cùng tag/timestamp/nonce | HMAC đúng lần hai | Nonce store phải reject |
| Key REVOKED | Tag có thể khớp bằng key cũ | Không tạo authenticated principal |
| Key khác tenant/audience | Key lookup không hợp lệ | Reject |
| Authentication đúng, resource ngoài quyền | Principal có MAC hợp lệ | Authorization deny |

### 10.2. Vì sao không dùng benchmark thời gian đơn giản làm bằng chứng?

Một vòng lặp:

~~~java
long start = System.nanoTime();
boolean matches = MessageDigest.isEqual(expected, candidate);
long elapsed = System.nanoTime() - start;
~~~

**không đủ** để kết luận có hoặc không có timing side channel. Kết quả chịu ảnh hưởng của JIT warm-up, dead-code elimination, CPU frequency scaling, GC, cache, scheduler và thứ tự test. Nhiều phép so có thể bị compiler tối ưu khi input đã biết; benchmark một lần không đo được độ an toàn.

Nếu tổ chức cần đánh giá timing trên runtime thực tế:

1. Định nghĩa **giả thuyết rò rỉ bí mật** cụ thể (ví dụ vị trí mismatch).
2. Chạy trên **fixture cố định**, cô lập môi trường khi có thể, kiểm soát warm-up.
3. **Randomize/interleave** các nhóm test; tránh so một block “byte đầu sai” rồi block “byte cuối sai”.
4. Thu số mẫu đủ lớn, dùng thống kê và confidence interval để đánh giá khác biệt thay vì xem một số trung bình.
5. So sánh với **control** biết trước có early-exit và implementation đúng.
6. Không dùng việc “không tìm thấy chênh lệch” làm bằng chứng tuyệt đối rằng code constant-time.
7. Không chạy phép dò thông tin trên API của bên khác khi chưa được cho phép.

Đối với Java, kiểm tra **khả năng và hợp đồng API của đúng JDK/version** đang triển khai; không tự khẳng định toàn bộ chương trình constant-time chỉ từ kết quả một microbenchmark.

### 10.3. Property-based và fuzz tests

Một số tính chất hữu ích:

- **Determinism:** cùng canonical bytes + secret → cùng HMAC bytes.
- **Equal-length validation:** chỉ nhận tag đúng 32 byte.
- **Canonical Base64URL:** tag có đúng một biểu diễn no-padding được chấp nhận.
- **No prefix acceptance:** tag ngắn trùng nhiều byte đầu vẫn phải reject.
- **Method/URI/body binding:** đổi signed fields → tag khác với xác suất áp đảo.
- **No duplicate signature:** mọi HTTP field occurrences không được bị silently collapsed.
- **Key isolation:** key ID không được dẫn sang secret của client khác.
- **Freshness:** cùng nonce phát lại dù MAC đúng → reject.
- **Policy:** authenticated principal không được truy cập resource không thuộc quyền.

Fuzz chỉ trong hệ thống thử nghiệm có giới hạn thời gian, request size và rate; không dùng production secret hoặc cố brute-force tag thật.

## 11. Authorization sau authentication

Ví dụ merchant `merchant-17` sở hữu shared secret và ký thành công:

~~~http
POST /v1/transfers?mode=commit HTTP/1.1
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <valid-hmac-for-this-request>
~~~

Body có thể yêu cầu chuyển tiền từ một tài khoản thuộc `merchant-42`. Khi đó:

~~~text
Authentication:
  MAC = valid
  Timestamp = in window
  Nonce = new
  Principal = merchant-17

Authorization:
  Action = transfers:commit
  Resource owner = merchant-42
  Principal = merchant-17
  Decision = DENY
~~~

**So sánh constant-time chỉ giải quyết một chi tiết của bước xác thực.** Nó không cho principal quyền dùng mọi tài khoản, không bảo vệ khỏi BOLA, không thay thế kiểm tra tenant và không làm hợp lệ một request có MAC đúng nhưng key đã bị revoke.

## 12. Các lỗi thường gặp

1. **So tag bằng vòng lặp dừng sớm**: thời gian có thể phụ thuộc vị trí byte sai.
2. **So hex/Base64 string thay cho raw tag bytes**: trộn encoding với cryptographic comparison.
3. **Chỉ so prefix theo chiều dài nhận được**: mở đường chấp nhận tag bị cắt ngắn.
4. **Tự viết hàm “constant-time” rồi tin tuyệt đối**: compiler/JIT/length/branch làm mất bảo đảm.
5. **Bỏ qua chiều dài trước khi so**: nhập nhằng full và truncated HMAC.
6. **Chấp nhận nhiều signature headers**: proxy/app có thể chọn khác nhau.
7. **Không kiểm tra Base64URL canonicality**: nhiều text representations cho cùng tag.
8. **Tưởng `MessageDigest.isEqual` làm cả endpoint constant-time**: key lookup, parser và authorization vẫn biến thiên.
9. **Dùng dummy key để cấp quyền**: dummy path chỉ có thể giảm oracle, luôn phải deny.
10. **Thử tất cả secret của mọi tenant**: rủi ro rò thông tin, DoS và cross-tenant confusion.
11. **Bỏ signed URI/body**: expected tag không bảo vệ hành vi thực tế.
12. **Không chống replay**: request đã ký có thể bị dùng lại.
13. **Không quản lý key rotation/revoke**: secret cũ vẫn có thể được accept.
14. **Không kiểm tra quyền sau MAC**: client thật vẫn có thể truy cập resource ngoài quyền.

## 13. Bài tập thực hành

**Bài 1 — Early exit:** Với expected tag 4 byte `A1 B2 C3 D4`, hãy tính số lần kiểm tra byte khi candidate khác tại byte đầu, thứ hai và cuối theo `insecureEquals`. Thông tin nào đang phụ thuộc vào secret?

**Bài 2 — Full tag:** Vì sao HMAC-SHA-256 tạo 32 byte và Base64URL no-padding thường có 43 ký tự? Điều gì nguy hiểm nếu server chấp nhận tag chỉ 4 byte đúng prefix?

**Bài 3 — Code review:** Sửa đoạn `expectedHex.equals(receivedHex)` thành một luồng verify an toàn hơn trong Java 17: kiểm tra header, Base64URL decode strict, đủ 32 byte, tính HMAC và so raw tag.

**Bài 4 — Benchmark:** Một developer đo `System.nanoTime()` một lần cho hai candidate và kết luận “constant-time”. Những yếu tố nào khiến kết luận không có giá trị? Đề xuất một test logic thay thế.

**Bài 5 — Key existence:** Server trả lỗi rất nhanh cho key ID không tồn tại, chậm hơn cho key tồn tại nhưng HMAC sai. Đây là oracle về thông tin gì? Nó có trực tiếp làm lộ HMAC prefix không?

**Bài 6 — Proxy rewrite:** Client ký `mode=check` nhưng gateway sửa thành `mode=commit` trước verifier. `MessageDigest.isEqual` có bảo đảm request được chấp nhận không? Giải thích kết quả đúng.

**Bài 7 — Replay:** Gửi lại y nguyên request có MAC đúng, timestamp trong cửa sổ và nonce đã dùng. Tại sao lõi `verifyMac` vẫn true nhưng receiver phải reject?

**Bài 8 — Rotation:** Một key chuyển từ `VERIFY_ONLY` sang `REVOKED`, nhưng tag HMAC tính bằng key đó vẫn đúng. Tầng nào quyết định reject?

**Bài 9 — Authorization:** Merchant 17 ký hợp lệ request chuyển tiền từ tài khoản merchant 42. Hãy phân biệt kết quả authentication, anti-replay và authorization.

## 14. Checklist triển khai

| Nhóm | Câu hỏi xác minh |
|---|---|
| **HMAC** | Có dùng JCA `Mac.getInstance("HmacSHA256")` với đúng secret và canonical bytes không? |
| **Tag length** | Có bắt buộc tag **32 byte đầy đủ** thay vì nhận prefix không? |
| **Decode** | Signature đúng 43 ký tự Base64URL no-pad, canonical, một header duy nhất không? |
| **Comparison** | Tag đã decode được so bằng `MessageDigest.isEqual`, không dừng sớm theo prefix không? |
| **Canonicalization** | Method, raw target/query, signed headers và body digest có đúng hợp đồng không? |
| **Key identity** | Client ID/key ID/audience gắn với đúng key và trạng thái rotation không? |
| **Timing oracle** | Response/timing khác nhau có tiết lộ secret hoặc key/resource existence theo threat model không? |
| **Replay** | Timestamp/nonce được ký, nonce store atomically shared, fail closed không? |
| **Gateway** | Proxy có rewrite target/header/body trước khi verify không? |
| **Authorization** | Principal có quyền trên action/resource/tenant thật không? |
| **Testing** | Có known-answer HMAC vectors, negative tests và gateway integration tests không? |
| **Operations** | Có rate limits, size limits, error responses nhất quán và logging không rò secret không? |

## 15. Kết luận

**Timing attack trong xác thực HMAC** khai thác sự phụ thuộc của thời gian xử lý vào dữ liệu bí mật, đặc biệt khi so chữ ký theo kiểu **dừng ngay ở byte sai đầu tiên**. Với Java 17, một cách phòng vệ thực tế là **decode chữ ký strict, xác nhận full 32-byte HMAC-SHA-256 tag rồi so bằng `MessageDigest.isEqual`**; tránh các phép so chuỗi, prefix hoặc vòng lặp tự viết có nhánh dừng sớm. Đây chỉ là **một lớp**: thiết kế hoàn chỉnh vẫn cần canonical request chính xác, secret/key rotation, chống replay bằng timestamp/nonce, kiểm thử proxy/gateway, hạn chế oracle từ key lookup và **authorization độc lập**. Hãy đánh giá rò rỉ thời gian theo threat model thật thay vì tin vào một phép đo nanosecond đơn lẻ.

**Tài liệu tham khảo:**

- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104): HMAC và xác thực thông điệp.
- [RFC 4231 — HMAC-SHA-256 Test Vectors](https://www.rfc-editor.org/rfc/rfc4231): known-answer tests, bao gồm Test Case 1.
- [RFC 4648 — Base-N Encodings](https://www.rfc-editor.org/rfc/rfc4648): Base64URL, padding và biểu diễn canonical.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): method, URI, field values và semantics của HTTP request.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): HTTP framing và intermediary behavior.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): pseudo-header `:method`/`:path` và mapping qua HTTP/2.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): chuẩn tham khảo ký các thành phần HTTP; `hmac-timing-v1` ở đây là **ví dụ học tập**, không tự nhận triển khai RFC 9421.
- [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): `MessageDigest.isEqual`.
- [Java SE 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): `getInstance`, `init` và `doFinal`.
- [Java SE 17 — Base64](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html): URL-safe encoder/decoder và xử lý padding.
