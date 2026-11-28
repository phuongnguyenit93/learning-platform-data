# So sánh cùng độ dài trong constant-time comparison của chữ ký HMAC

**So sánh cùng độ dài** là điều kiện thiết kế quan trọng trước khi verifier so sánh chữ ký HMAC. Client thường gửi một **chuỗi Base64/hex**, nhưng HMAC-SHA256 tạo một **tag nhị phân 32 byte**. Server phải giải mã chuỗi đúng hợp đồng, **bắt buộc tag nhận được có độ dài mà server quy định**, tính lại tag mong đợi trên canonical request, rồi mới so sánh **toàn bộ hai tag cùng độ dài**. Không được lấy độ dài tag do client gửi làm độ dài để cắt tag mong đợi.

Bài thuộc chương **Constant-time comparison**, module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Module thiết kế xác thực HTTP request bằng **shared secret** và **canonical request** chứa method, URI, signed headers hoặc body theo hợp đồng ký; thực hành kiểm tra HMAC, chống replay bằng timestamp/nonce, quản lý key rotation, thử nghiệm proxy/gateway và tách **xác thực** khỏi **phân quyền**. Trọng tâm của bài là **quy tắc hai tag cùng độ dài** và giới hạn của kiểm tra constant-time trong một hệ thống HTTP thực.

**Ghi nhớ ngay từ đầu:** Với hợp đồng HMAC-SHA256 **full tag**, phép kiểm tra đúng là:

~~~text
expectedTag = HMAC_SHA256(secret, canonicalRequestBytes) // 32 byte
receivedTag = strictDecode(X-Signature)                  // phải 32 byte

valid = length(expectedTag) == 32
    AND length(receivedTag) == 32
    AND MessageDigest.isEqual(expectedTag, receivedTag)
~~~

Nếu chuỗi chữ ký có đúng alphabet nhưng chỉ giải mã được **16 byte**, kết quả phải là **reject**, không phải so sánh 16 byte đầu. Kiểm tra độ dài là một phần của **chính sách giao thức**, còn `MessageDigest.isEqual` giải quyết yêu cầu **không kết thúc sớm vì nội dung byte khác nhau**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **độ dài tag HMAC nhị phân**, **độ dài chuỗi chữ ký được encode** và **độ dài canonical request**.
2. Giải thích vì sao so sánh cùng độ dài là tiền điều kiện hợp lý cho việc so sánh full HMAC tag, nhưng **không đủ** để tuyên bố cả verifier constant-time.
3. Phân tích các lỗi so sánh **prefix, truncation theo input**, zero-padding và so sánh chuỗi Base64.
4. Áp dụng `MessageDigest.isEqual` trong Java 17 với hai `byte[]` đã được kiểm tra đúng **32 byte**.
5. Thiết kế luồng xác thực gồm strict parsing, HMAC recomputation, kiểm tra timestamp/nonce, key rotation và authorization.
6. Viết kiểm thử tag đúng, tag thiếu/thừa byte, sai byte đầu/cuối, body/URI bị sửa, replay và key đã thu hồi.

## 2. Ba kiểu độ dài không thể đánh đồng

Ví dụ một request:

~~~http
POST /v1/transfers?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-11
X-Timestamp: <unix-epoch-seconds>
X-Nonce: <32-lowercase-hex-characters>
X-Content-SHA256: <64-lowercase-hex-characters>
X-Signature: <base64-standard-padded-signature>

{"transferId":"t-123","amount":50000}
~~~

Các chuỗi `<...>` chỉ là placeholder mô tả format. Khi request thật được gửi, signer điền giá trị đã tính toán.

| Dữ liệu | Ý nghĩa | Độ dài trong hợp đồng mẫu |
| --- | --- | --- |
| `bodyBytes` | Byte JSON thực gửi, không phải chuỗi JSON được server serialize lại | Phụ thuộc request |
| `SHA256(bodyBytes)` | Digest không khóa để ràng buộc body vào canonical | **32 byte** |
| `x-content-sha256` | Digest body đã chuyển sang hex lowercase | **64 ký tự ASCII** |
| `canonicalRequestBytes` | Method + raw URI + signed fields + body digest, mã hóa UTF-8 | Phụ thuộc dữ liệu, **không cố định 32 byte** |
| `expectedTag` | `HMAC_SHA256(secret, canonicalRequestBytes)` do verifier tính | **32 byte** |
| `receivedTag` | Byte thu được sau khi decode `X-Signature` | **Bắt buộc 32 byte** |
| `X-Signature` Base64 chuẩn, có padding | Cách đưa 32-byte tag vào HTTP header | **44 ký tự ASCII**, kết thúc một `=` |
| `X-Signature` Base64url, không padding | Một định dạng **khác** có thể dùng ở giao thức khác | **43 ký tự ASCII** |
| `X-Signature` hex lowercase | Một định dạng **khác** nữa | **64 ký tự ASCII** |

Vì 32 byte chia 3 được 10 nhóm đủ và dư 2 byte, biểu diễn Base64 chuẩn cần \(44\) ký tự với **một dấu `=` cuối**. Số ký tự **44** thuộc *wire encoding*, trong khi số byte cần so sánh là **32**. Không được đem `X-Signature` dài 44 ký tự so với `expectedTag` 32 byte hoặc so hai chuỗi bằng `String.equals` rồi mặc định bảo đảm chống timing attack.

### 2.1. HMAC tag và body digest có thể đều dài 32 byte nhưng không tương đương

~~~text
bodyHash = SHA256(bodyBytes)                  // không có secret
macTag   = HMAC_SHA256(secret, canonical)    // có secret
~~~

Body digest bảo đảm verifier biết nội dung byte nào phải được đưa vào canonical; HMAC mới là phần xác thực có khóa. Nếu so sánh `x-content-sha256` với `X-Signature` vì chúng cùng “liên quan SHA-256”, việc xác thực đã sai từ gốc.

### 2.2. “Cùng độ dài” không phải “cùng nội dung”

Hai tag đều dài 32 byte nhưng một byte khác nhau sẽ **không** được xác thực:

~~~text
expectedTag = [ 32 byte do server tính ]
receivedTag = [ 32 byte do client gửi ]

32 == 32              -> chỉ PASS kiểm tra độ dài
secureEqual(...)       -> vẫn có thể FALSE
~~~

Hợp đồng kiểm tra độ dài **trước**, rồi kiểm tra toàn bộ nội dung tag; không chọn một trong hai.

## 3. Lỗ hổng so sánh độ dài do client quyết định

### 3.1. Lỗi prefix matching

Đoạn mã dưới đây **nguy hiểm**:

~~~java
// SAI: suppliedTag có độ dài do người gửi kiểm soát.
boolean ok = java.util.Arrays.equals(
    java.util.Arrays.copyOf(expectedTag, suppliedTag.length),
    suppliedTag
);
~~~

Nếu kẻ tấn công gửi **1 byte**, phép kiểm tra chỉ đòi 1 byte đầu đúng. Với tag HMAC phân bố gần ngẫu nhiên, xác suất đoán đúng một byte là khoảng \(2^{-8}\), dễ hơn cực nhiều so với đoán đúng full 32-byte tag với xác suất lý tưởng \(2^{-256}\) cho một lần đoán, nếu khóa và HMAC được dùng đúng. Trường hợp `suppliedTag.length == 0` còn có thể khiến hai mảng rỗng so sánh bằng nhau!

| Độ dài attacker gửi | Độ khó đoán tag theo số bit của prefix | Có chấp nhận trong HMAC-SHA256 full-tag contract? |
| ---: | ---: | --- |
| 0 byte | 0 bit; mảng rỗng có thể so sánh bằng nhau | **Không** |
| 1 byte | 8 bit | **Không** |
| 4 byte | 32 bit | **Không** |
| 8 byte | 64 bit | **Không** |
| 16 byte | 128 bit | **Không** |
| 31 byte | 248 bit | **Không** |
| **32 byte** | **256 bit của full tag** | **Có thể tiếp tục so sánh** |
| 33 byte | Không phải full HMAC-SHA256 tag | **Không** |

Các con số ở cột giữa mô tả **số bit của giá trị tag cần đoán trong mô hình lý tưởng**, không phải cam kết an toàn tổng thể. An toàn thực tế còn phụ thuộc entropy của key, số lần thử, replay protection, policy thuật toán và việc HMAC không bị triển khai sai.

**Cách đúng:** định nghĩa `EXPECTED_TAG_BYTES = 32` trong server policy và từ chối ngay khi `receivedTag.length != 32`, bất kể byte đầu có giống HMAC mong đợi hay không.

### 3.2. Zero-padding cũng không phải cách sửa

Một đoạn code “tự cân bằng độ dài” dễ bị viết sai:

~~~java
// SAI: không tự lấp tag ngắn bằng byte 0 hoặc cắt tag dài.
byte[] normalized = java.util.Arrays.copyOf(receivedTag, 32);
boolean ok = java.security.MessageDigest.isEqual(
    expectedTag, normalized
);
~~~

`Arrays.copyOf` **thêm các byte 0** khi input ngắn và **cắt bỏ** khi input dài. Điều này tạo một quy tắc chấp nhận biểu diễn khác với contract full tag, dù ở một số trường hợp so sánh vẫn không khớp. Nó phá tính rõ ràng về độ dài; không được chuyển “mã lỗi format” thành “mã tag đã chuẩn hóa”.

### 3.3. Truncated HMAC có thể là một thiết kế riêng, không phải lựa chọn của request

Một số giao thức thực sự định nghĩa **truncated MAC** với một độ dài **cố định từ trước**, có phân tích độ an toàn tương ứng. Việc đó **khác hoàn toàn** với cho client gửi 8, 12, 16 hay 32 byte tùy ý và server chọn `suppliedTag.length` để so sánh.

Nếu API định hỗ trợ một tag ngắn hơn, phải lập **version/algorithm policy riêng**, yêu cầu đúng độ dài duy nhất của phiên bản, đánh giá số lần yêu cầu có thể thử, quản trị key và cách migration. Bài này cố định **HMAC-SHA256 full 32 byte**. Không triển khai fallback “nếu không khớp 32 byte thì thử 16 byte”.

## 4. Constant-time có và không có nghĩa gì?

### 4.1. Vòng lặp dừng tại byte sai đầu tiên

Ví dụ không phù hợp cho MAC:

~~~java
static boolean earlyReturnEquals(byte[] expected, byte[] received) {
    if (expected.length != received.length) {
        return false;
    }
    for (int i = 0; i < expected.length; i++) {
        if (expected[i] != received[i]) {
            return false; // Thời gian phụ thuộc vị trí sai đầu tiên.
        }
    }
    return true;
}
~~~

Khi byte đầu sai, hàm có thể kết thúc sớm hơn khi 31 byte đầu đúng và byte cuối sai. Chênh lệch thời gian có thể là một **side channel** nếu đối thủ gửi nhiều phép thử và thống kê được tín hiệu. HTTP có jitter và nhiều nguyên nhân thay đổi độ trễ, nhưng không nên dựa vào “mạng đủ nhiễu” như một cơ chế an toàn.

### 4.2. So sánh bitwise tổng hợp lỗi

Một mô hình dễ hiểu (mang tính giáo dục, **không thay thế thư viện chuẩn**) cho các mảng đã biết bằng nhau về độ dài:

~~~java
static boolean educationalEqualLengthCompare(
        byte[] expected, byte[] received) {
    if (expected.length != 32 || received.length != 32) {
        return false;
    }
    int diff = 0;
    for (int i = 0; i < 32; i++) {
        diff |= expected[i] ^ received[i];
    }
    return diff == 0;
}
~~~

Vòng lặp kiểm tra đủ 32 vị trí và không trả về sớm theo byte không khớp. Tuy nhiên, **không suy ra từ source code Java rằng máy thực thi có thời gian tuyệt đối không đổi**: JIT, tối ưu hóa compiler, CPU cache và thao tác xung quanh còn tác động. Đó là lý do production nên dùng API chuyên dụng thay vì tự triển khai primitive so sánh.

### 4.3. Java 17: `MessageDigest.isEqual`

~~~java
import java.security.MessageDigest;

// Phải xác minh trước rằng cả hai tag dài đúng 32 byte.
boolean matches =
    expectedTag.length == 32 &&
    receivedTag.length == 32 &&
    MessageDigest.isEqual(expectedTag, receivedTag);
~~~

`MessageDigest.isEqual(byte[], byte[])` là API của JCA thiết kế để so sánh dữ liệu digest/tag theo cách tránh **kết thúc sớm vì byte đầu không khớp**. Tài liệu JDK mô tả thời gian tính toán phụ thuộc vào độ dài của mảng đầu tiên, không phụ thuộc nội dung hai mảng theo các điều kiện API quy định. Việc ta cố định **expectedTag.length == 32** và **receivedTag.length == 32** giúp loại trừ độ dài tùy ý khỏi đường so sánh mật mã.

**Quan trọng:** kiểm tra `receivedTag.length != 32` rồi reject **có thể có thời gian khác** với request chứa tag 32 byte. Điều đó **không tự là lỗ hổng timing của bí mật**: độ dài chữ ký do bên gửi chọn, đã bị giao thức công khai quy định và có thể từ chối sớm. Mục tiêu là tránh làm **thời gian khi so sánh full tag phụ thuộc prefix bí mật nào đã khớp**. Không thể suy ra toàn bộ HTTP request verification có “constant-time end-to-end” chỉ vì dùng một hàm.

### 4.4. Độ dài nào được xem là công khai, điều gì cần bảo vệ?

| Yếu tố | Có thể thay đổi thời gian? | Gợi ý thiết kế |
| --- | --- | --- |
| Encoded signature sai số ký tự | Có, vì fail format sớm | Giới hạn kích thước, reject theo contract. |
| Decoded tag dài 0/16/33 byte | Có, vì fail length sớm | Độ dài do attacker chọn; không dùng để cắt expected tag. |
| Hai full tag 32 byte khác ở byte đầu hay cuối | **Không nên** tạo sai biệt theo vị trí byte | Dùng `MessageDigest.isEqual` trên hai tag cố định. |
| Key ID tồn tại hay không | Có, do tra key store | Giới hạn enumeration, response và chính sách lookup theo threat model. |
| Body dài 100 byte hay 1 MB | Có, do đọc/hash body | Giới hạn body; không thể bắt mọi request chạy cùng thời gian. |
| Replay nonce đã dùng hay chưa | Có, do store/network I/O | Atomic claim, response hạn chế thông tin, chống flood. |
| Authorization của mỗi resource | Có, do truy vấn dữ liệu | Tách khỏi kiểm tra MAC và quản trị side channel ở cấp hệ thống. |

## 5. Kiểm tra độ dài ở bước nào trong verifier?

~~~mermaid
flowchart TD
    A["Request tại ingress đáng tin"] --> B["Strict HTTP parse, giới hạn kích thước, chặn duplicate"]
    B --> C["Đọc đúng một X-Signature"]
    C --> D["Kiểm tra encoding canonical và decode"]
    D --> E{"Received tag đúng 32 bytes?"}
    E -->|Không| X["Authentication reject"]
    E -->|Có| F["Kiểm tra method, URI, signed headers, body digest"]
    F --> G["Tra đúng secret theo client ID/key ID và policy"]
    G --> H["Tạo canonical bytes, tính expected HMAC-SHA256"]
    H --> I{"Expected tag 32 bytes và isEqual?"}
    I -->|Không| X
    I -->|Có| J["Freshness + atomic nonce claim"]
    J -->|Replay/hết hạn| X
    J -->|Hợp lệ| K["Authorization, idempotency và nghiệp vụ"]
~~~

Đây là **luồng minh họa**. Một số kiểm tra định dạng/timestamp có thể được thực hiện trước HMAC để giảm chi phí; điều kiện không thay đổi là **không công nhận identity, không claim nonce cho MAC giả và không thực thi nghiệp vụ khi MAC chưa hợp lệ**.

Quy trình chi tiết:

1. **HTTP parser/ingress:** từ chối framing mâu thuẫn, giới hạn header/body, các header bảo mật trùng/mơ hồ, CR/LF injection, request smuggling. Không coi một header `X-Verified` do client gửi là bằng chứng.
2. **Encoded signature:** lấy đúng **một** `X-Signature`. Kiểm tra alphabet/ASCII/padding đúng hợp đồng, không dùng `trim()` hoặc MIME decoder để cứu chuỗi sai.
3. **Decode:** chuyển Base64 thành `byte[]`; bắt buộc tag đúng **32 byte**, kiểm tra round-trip canonical.
4. **Request fields:** lấy method, raw path/query, signed header values và body bytes từ **request được thực thi**, không dựa vào lời client tự gửi về canonical string.
5. **Key lookup:** dùng client ID + key ID để tra secret theo server policy, kiểm tra hiệu lực/thu hồi, audience, algorithm và route. Client ID trước HMAC chỉ là **tên tra cứu chưa được xác thực**.
6. **Recompute:** tính lại body SHA-256; dựng canonical request theo version, thứ tự field, LF, UTF-8; tính HMAC-SHA256.
7. **Compare:** xác nhận expected tag dài 32 byte, so sánh **toàn bộ** với received tag 32 byte bằng `MessageDigest.isEqual`.
8. **Replay:** kiểm tra freshness timestamp đã ký, nonce mới và atomic claim trên shared store; idempotency cho thao tác có side effect.
9. **Authorization:** quyết định client có quyền method/action/tenant/resource hay không, kể cả khi HMAC khớp.

## 6. Hợp đồng HMAC-EQUAL-LENGTH-V1

Để ví dụ Java kiểm tra được byte chính xác, dùng hợp đồng riêng cho endpoint tạo chuyển khoản mô phỏng:

| Thuộc tính | Policy mẫu |
| --- | --- |
| Version | `HMAC-EQUAL-LENGTH-V1` |
| Method | `POST` chính xác, case-sensitive |
| Raw request target | `/v1/transfers?currency=VND` |
| Audience | `transfers-api` do verifier quy định |
| Signed fields | Client ID, key ID, timestamp, nonce, Content-Type, body hash |
| Body | Byte JSON thực nhận; `SHA256(bodyBytes)` hex lowercase |
| Canonical string | Các dòng có thứ tự cố định, nối LF, UTF-8, **không LF cuối** |
| Signature encoding | Base64 chuẩn padded, đúng 44 ASCII chars |
| Tag length | HMAC-SHA256 full **32 byte**, không cho client chọn |
| Key | Shared secret chọn theo `client ID + key ID` từ trusted key store |
| Replay | Freshness + nonce claim nguyên tử sau HMAC |

Canonical request:

~~~text
HMAC-EQUAL-LENGTH-V1
POST
/v1/transfers?currency=VND
audience:transfers-api
x-client-id:partner-42
x-key-id:key-2026-11
x-timestamp:<unix-epoch-seconds>
x-nonce:<32-lowercase-hex-characters>
content-type:application/json
x-content-sha256:<64-lowercase-hex-characters>
~~~

Các giá trị trong `<...>` là placeholder; signer phải thay bằng giá trị thực. HMAC được tính:

~~~text
canonicalBytes = UTF8(joinWithLF(exactCanonicalLines))
expectedTag    = HMAC_SHA256(sharedSecret, canonicalBytes)
wireSignature  = Base64StandardPadded(expectedTag)
~~~

Signature **không nằm trong canonical** để tránh tự tham chiếu. Đối với content encoding, method override, Host/authority, query duplicate hoặc proxy rewrite, verifier và backend cần một **policy rõ ràng** để bảo đảm ngữ nghĩa được bảo vệ. Bài chọn `Content-Type: application/json` và một raw target cố định; header không nằm trong phạm vi ký **không được âm thầm quyết định identity, effective method, tenant hoặc resource**.

### 6.1. Tại sao ký key ID?

Key ID là metadata để verifier tìm khóa, **chưa chứng minh identity** trước khi MAC khớp. Nếu key ID không nằm trong canonical, một proxy có thể thay nó và làm verifier dùng sai key/policy; nếu key lookup có alias hoặc dùng chung key, còn có thể dẫn tới nhập nhằng. Ràng buộc client ID và key ID trong canonical, đồng thời kiểm tra key đang active, đúng audience và scope, làm rõ khóa nào đang được dùng.

### 6.2. Encoding nên được validate strict

Với Base64 chuẩn padded của HMAC-SHA256 32 byte:

~~~text
Decoded bytes: 32
Encoded chars: 44
Alphabet:      A-Z a-z 0-9 + /
Padding:       đúng một '=' cuối
~~~

Java Base64 decoder có thể chấp nhận một số biến thể **không padding**. Vì vậy contract không chỉ gọi `Base64.getDecoder().decode`: nó xác nhận format, độ dài và **encode lại để đối chiếu chính tắc**. Nếu hệ thống muốn Base64url không padding, phải dùng hợp đồng khác gồm alphabet `-`, `_` và 43 ký tự, chứ không tự thử decoder thay thế cho request thất bại.

## 7. Java 17: full-tag HMAC-SHA256 với hai mảng cùng 32 byte

Chương trình dưới đây có thể đặt trong một file `EqualLengthHmacExample.java` trên Java 17. Nó mô phỏng client và verifier cùng một tiến trình, không gửi HTTP ra mạng. Chương trình:

- Tạo secret test bằng `SecureRandom`, body JSON UTF-8 và nonce 16 byte ngẫu nhiên.
- Tính HMAC-SHA256 từ canonical request, truyền chữ ký bằng Base64 chuẩn padded.
- Decode chữ ký **strict** và yêu cầu `receivedTag.length == 32`.
- Tra bản ghi key theo identity/key ID, kiểm tra key active/revoked và tính lại HMAC.
- So sánh hai mảng **cùng 32 byte** bằng `MessageDigest.isEqual`, sau đó claim nonce.
- Test tag đúng; tag sai byte đầu/cuối; tag rỗng/ngắn/dài; body bị sửa; key revoked; replay và timestamp hết hạn.

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

public final class EqualLengthHmacExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int TAG_BYTES = 32;
    private static final String METHOD = "POST";
    private static final String RAW_TARGET =
        "/v1/transfers?currency=VND";
    private static final String CLIENT_ID = "partner-42";
    private static final String KEY_ID = "key-2026-11";
    private static final String CONTENT_TYPE = "application/json";
    private static final String AUDIENCE = "transfers-api";
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

    // Demo chỉ trong một JVM, không TTL; production dùng shared store.
    static final class DemoNonceStore {
        private final Set<String> used =
            ConcurrentHashMap.newKeySet();

        boolean claim(String clientId, String nonce) {
            return used.add(clientId + ":" + nonce);
        }
    }

    static String bodySha256Hex(byte[] body)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(body)
        );
    }

    static byte[] hmacSha256(byte[] secret, String canonical)
            throws GeneralSecurityException {
        // Mỗi request tạo Mac riêng; Mac là đối tượng có trạng thái.
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(
            canonical.getBytes(StandardCharsets.UTF_8)
        );
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
            throw new IllegalArgumentException("Sai signing contract");
        }
        return String.join("\n",
            "HMAC-EQUAL-LENGTH-V1",
            method, target,
            "audience:" + AUDIENCE,
            "x-client-id:" + clientId,
            "x-key-id:" + keyId,
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "content-type:" + contentType,
            "x-content-sha256:" + bodyHash
        ); // Không có LF cuối.
    }

    // Chỉ chấp nhận Base64 basic padded và HMAC-SHA256 full 32 byte.
    // Không dùng độ dài do client đưa để cắt tag mong đợi.
    static byte[] decodeStrictFullTag(String text) {
        if (text == null ||
            !text.matches("[A-Za-z0-9+/]{43}=")) {
            return null;
        }
        try {
            byte[] tag = Base64.getDecoder().decode(text);
            if (tag.length != TAG_BYTES ||
                !Base64.getEncoder().encodeToString(tag).equals(text)) {
                return null;
            }
            return tag;
        } catch (IllegalArgumentException invalidBase64) {
            return null;
        }
    }

    static SignedRequest sign(byte[] secret, Clock clock)
            throws GeneralSecurityException {
        byte[] body =
            "{\"transferId\":\"t-123\",\"amount\":50000}"
                .getBytes(StandardCharsets.UTF_8);
        byte[] nonceBytes = new byte[16];
        RANDOM.nextBytes(nonceBytes);
        String nonce = HexFormat.of().formatHex(nonceBytes);
        String timestamp = Long.toString(
            clock.instant().getEpochSecond()
        );
        String hash = bodySha256Hex(body);
        String message = canonical(
            METHOD, RAW_TARGET, CLIENT_ID, KEY_ID,
            timestamp, nonce, CONTENT_TYPE, hash
        );
        byte[] tag = hmacSha256(secret, message);
        if (tag.length != TAG_BYTES) {
            throw new IllegalStateException("HMAC provider tag length sai");
        }
        String signature = Base64.getEncoder().encodeToString(tag);
        return new SignedRequest(
            METHOD, RAW_TARGET, CLIENT_ID, KEY_ID,
            timestamp, nonce, CONTENT_TYPE, hash, signature, body
        );
    }

    static boolean verify(SignedRequest request,
            Map<String, KeyRecord> keyring, Clock clock,
            DemoNonceStore nonces)
            throws GeneralSecurityException {
        // Production phải giới hạn toàn bộ HTTP body/header tại ingress.
        if (request == null || request.body() == null ||
            request.body().length > 65536) {
            return false;
        }

        // Gate 1: đúng 32 decoded bytes, không có short/long tag.
        byte[] receivedTag = decodeStrictFullTag(request.signature());
        if (receivedTag == null || receivedTag.length != TAG_BYTES) {
            return false;
        }

        final String message;
        try {
            String actualHash = bodySha256Hex(request.body());
            if (!actualHash.equals(request.bodyHash())) {
                return false;
            }
            message = canonical(
                request.method(), request.target(),
                request.clientId(), request.keyId(),
                request.timestamp(), request.nonce(),
                request.contentType(), actualHash
            );
        } catch (IllegalArgumentException badFields) {
            return false;
        }

        // Freshness dùng server clock; không claim nonce trước HMAC.
        final long timestamp;
        try {
            timestamp = Long.parseLong(request.timestamp());
        } catch (NumberFormatException invalidNumber) {
            return false;
        }
        long nowSeconds = clock.instant().getEpochSecond();
        if (timestamp < nowSeconds - PAST_SECONDS ||
            timestamp > nowSeconds + FUTURE_SECONDS) {
            return false;
        }

        // ID vẫn chưa được xác thực; chỉ dùng cho key lookup có policy.
        KeyRecord key = keyring.get(
            request.clientId() + ":" + request.keyId()
        );
        Instant now = clock.instant();
        if (key == null || key.revoked() ||
            !request.clientId().equals(key.clientId()) ||
            !request.keyId().equals(key.keyId()) ||
            key.secret() == null || key.secret().length < 32 ||
            key.activeFrom() == null || key.expiresAt() == null ||
            now.isBefore(key.activeFrom()) ||
            !now.isBefore(key.expiresAt())) {
            return false;
        }

        byte[] expectedTag = hmacSha256(key.secret(), message);
        // Gate 2: cả expected và received đều là full tag 32 byte.
        if (expectedTag.length != TAG_BYTES ||
            receivedTag.length != expectedTag.length) {
            return false;
        }
        if (!MessageDigest.isEqual(expectedTag, receivedTag)) {
            return false;
        }

        // Chỉ claim nonce khi HMAC hợp lệ.
        return nonces.claim(request.clientId(), request.nonce());
    }

    static SignedRequest withSignature(
            SignedRequest original, String replacement) {
        return new SignedRequest(
            original.method(), original.target(),
            original.clientId(), original.keyId(),
            original.timestamp(), original.nonce(),
            original.contentType(), original.bodyHash(),
            replacement, original.body()
        );
    }

    static void check(boolean condition, String explanation) {
        if (!condition) {
            throw new AssertionError(explanation);
        }
    }

    static void rfc4231Vector() throws Exception {
        byte[] vectorKey = new byte[20];
        Arrays.fill(vectorKey, (byte) 0x0b);
        String actual = HexFormat.of().formatHex(
            hmacSha256(vectorKey, "Hi There")
        );
        String expected =
            "b0344c61d8db38535ca8afceaf0bf12" +
            "b881dc200c9833da726e9376c2e32cff7";
        check(expected.equals(actual),
            "HMAC-SHA256 RFC 4231 test vector sai");
    }

    public static void main(String[] args) throws Exception {
        rfc4231Vector();
        byte[] secret = new byte[32];
        RANDOM.nextBytes(secret); // Chỉ là key demo.
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
        Map<String, KeyRecord> keys = Map.of(keyRef, active);
        SignedRequest signed = sign(secret, fixed);

        // Client java.net.http minh họa; không gửi HTTP ra mạng.
        HttpRequest request = HttpRequest.newBuilder(
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
        check(METHOD.equals(request.method()), "Sai method client");
        check(verify(signed, keys, fixed, new DemoNonceStore()),
            "Request đúng phải được xác thực");

        byte[] fullTag = decodeStrictFullTag(signed.signature());
        check(fullTag != null && fullTag.length == TAG_BYTES,
            "Full decoded tag phải đúng 32 byte");

        // Hai tag CÙNG độ dài nhưng sai byte đầu hoặc cuối phải reject.
        for (int index : new int[] {0, 31}) {
            byte[] tamperedTag = fullTag.clone();
            tamperedTag[index] ^= 1;
            SignedRequest modified = withSignature(
                signed, Base64.getEncoder().encodeToString(tamperedTag)
            );
            check(!verify(modified, keys, fixed, new DemoNonceStore()),
                "Tag sai byte đầu/cuối vẫn phải fail");
        }

        // Độ dài 0/1/16/31/33 đều không được biến thành so sánh prefix.
        for (int length : new int[] {0, 1, 16, 31, 33}) {
            byte[] wrongLengthTag = Arrays.copyOf(fullTag, length);
            String encoded = Base64.getEncoder()
                .encodeToString(wrongLengthTag);
            check(!verify(withSignature(signed, encoded),
                           keys, fixed, new DemoNonceStore()),
                "Tag sai độ dài phải bị từ chối: " + length);
        }

        // Một tag full 32 byte ngẫu nhiên cũng không thể qua HMAC.
        byte[] wrongFullTag = fullTag.clone();
        wrongFullTag[8] ^= 1;
        check(!verify(withSignature(
                    signed, Base64.getEncoder()
                        .encodeToString(wrongFullTag)),
                keys, fixed, new DemoNonceStore()),
            "Tag đủ 32 byte nhưng sai nội dung phải fail");

        // Ngay cả khi JDK decoder có thể nhận Base64 thiếu padding,
        // signing contract vẫn phải reject vì không canonical.
        check(!verify(
                withSignature(
                    signed, signed.signature().substring(0, 43)),
                keys, fixed, new DemoNonceStore()),
            "Thiếu padding phải bị từ chối");

        // Body thay byte phải làm digest hoặc HMAC sai.
        byte[] changedBody = signed.body().clone();
        changedBody[0] ^= 1;
        SignedRequest changed = new SignedRequest(
            signed.method(), signed.target(),
            signed.clientId(), signed.keyId(),
            signed.timestamp(), signed.nonce(),
            signed.contentType(), signed.bodyHash(),
            signed.signature(), changedBody
        );
        check(!verify(changed, keys, fixed, new DemoNonceStore()),
            "Body bị sửa phải bị từ chối");

        // Key bị thu hồi phải reject dù MAC tính bằng key đó vẫn khớp.
        KeyRecord revoked = new KeyRecord(
            CLIENT_ID, KEY_ID, secret,
            active.activeFrom(), active.expiresAt(), true
        );
        check(!verify(
                signed, Map.of(keyRef, revoked),
                fixed, new DemoNonceStore()),
            "Key revoked phải bị từ chối");

        DemoNonceStore replay = new DemoNonceStore();
        check(verify(signed, keys, fixed, replay),
            "Request lần đầu phải được nhận");
        check(!verify(signed, keys, fixed, replay),
            "Replay phải bị nonce store từ chối");

        Clock expired = Clock.offset(
            fixed, Duration.ofSeconds(301)
        );
        check(!verify(signed, keys, expired, new DemoNonceStore()),
            "Timestamp quá hạn phải bị từ chối");
        System.out.println(
            "PASS: 32-byte equal-length HMAC comparison and replay"
        );
    }
}
~~~

### 7.1. Tách riêng kiểm tra độ dài khỏi so sánh mật mã

Trong `verify` có hai cổng:

~~~java
// Gate 1: đầu vào sau decode phải có đúng độ dài theo server policy.
if (receivedTag == null || receivedTag.length != TAG_BYTES) {
    return false;
}

// Gate 2: HMAC từ thuật toán đã chọn cũng phải có đúng độ dài.
if (expectedTag.length != TAG_BYTES ||
    receivedTag.length != expectedTag.length) {
    return false;
}
return MessageDigest.isEqual(expectedTag, receivedTag);
~~~

Gate 1 ngăn attacker quyết định độ dài MAC bằng dữ liệu gửi vào; Gate 2 tránh lỗi thuật toán hoặc policy làm so sánh khác format. Trong ví dụ `Mac.getInstance("HmacSHA256")` luôn trả tag 32 byte theo provider phù hợp; kiểm tra độ dài expected ở Gate 2 là một bất biến rõ ràng, không phải cách “rút ngắn” tag.

### 7.2. Không được nhầm “cùng độ dài” với “bắt buộc chạy mọi bước như nhau”

Một request gửi `X-Signature: abc` bị loại trước khi HMAC được tính. Điều đó là hợp lý vì **độ dài và format là dữ liệu công khai do client kiểm soát** và hệ thống cần chống lạm dụng tài nguyên. Với hai request có **tag đã decode đúng 32 byte**, việc so sánh nội dung được giao cho `MessageDigest.isEqual` thay vì vòng lặp early return.

Đừng dùng các vòng `Thread.sleep` ngẫu nhiên để “làm constant-time” hay thử ép mọi request HTTP có độ trễ giống nhau. Cần đúng primitive, rate limiting, quan sát thời gian, chính sách lỗi và threat model hợp lý.

### 7.3. Giới hạn của mã minh họa

- `SignedRequest` là record test đã parse. Server thật phải reject **duplicate signed headers**, request smuggling, CR/LF, framing mâu thuẫn và lấy raw URI/body thực nhận ở **trust boundary** đáng tin.
- `KeyRecord` chỉ biểu diễn vài trường của key store. Production cần kiểm soát client status, audience, route scope, phiên bản thuật toán, thời gian key rotation và chính sách revoke; secret nên nằm trong hệ thống quản lý khóa an toàn.
- `DemoNonceStore` chỉ đồng bộ trong **một JVM** và không TTL. Production dùng storage chia sẻ với atomic claim và TTL bao phủ toàn bộ cửa sổ timestamp; riêng nghiệp vụ side effect cần idempotency.
- Mẫu chỉ xác minh HMAC theo endpoint cố định và không thực sự cấp quyền. Backend vẫn phải thực thi **authorization** theo identity/tenant/resource.
- Không chạy request thật qua proxy/gateway. Cần integration test bảo đảm same signed method/raw path/query, headers và body xuyên qua HTTP/1.1, HTTP/2 và các hop.
- Mẫu dùng Base64 chuẩn padded và tag HMAC-SHA256 full 32 byte; không tự chuyển Base64url, hex hay tag truncated để tăng tỷ lệ “verify thành công”.

## 8. Các lỗi thường gặp khi triển khai so sánh cùng độ dài

| Lỗi | Tác động | Phòng tránh |
| --- | --- | --- |
| Cắt `expectedTag` đến `receivedTag.length` | Cho phép attacker chọn độ mạnh prefix | **Reject tag sai độ dài trước** khi compare. |
| Đệm tag ngắn bằng byte 0 | Âm thầm biến malformed tag thành format khác | Không sửa/normalize byte tag; từ chối. |
| Chấp nhận `expectedTag.length >= suppliedTag.length` | Cho phép MAC truncation không kiểm soát | Bắt buộc cả hai cùng đúng **32 byte**. |
| Dùng `Arrays.equals` trong đường xác thực bí mật | Có thể dừng sớm theo byte sai | Dùng `MessageDigest.isEqual`. |
| So sánh hai chuỗi Base64 bằng `String.equals` | Không có bảo đảm timing phù hợp, dễ sai encoding | Strict decode rồi compare raw bytes. |
| Dùng Base64 decoder “linh hoạt” như MIME decoder | Có thể bỏ qua ký tự ngoài alphabet | Cố định alphabet, padding, round-trip canonical. |
| Xem tag 44 ký tự nghĩa là HMAC đúng | Người lạ cũng tạo được text đúng form | Recompute MAC với shared secret. |
| Dùng key ID từ request làm bằng chứng identity | Attacker có thể tự điền key ID bất kỳ | Tra key để verify, chỉ tin identity sau MAC và policy. |
| Claim nonce trước khi MAC đúng | Attacker có thể đốt nonce của request hợp lệ | Claim sau HMAC hợp lệ. |
| Cố chạy constant-time toàn hệ thống bằng padding delay | Không khắc phục nội dung canonical/logic sai | Correct-by-design verification, giới hạn request và kiểm tra side channel. |
| Bỏ method/URI/body khỏi canonical | HMAC đúng vẫn không bảo vệ hành động thật | Ký đủ ngữ nghĩa và route nhất quán. |

## 9. Proxy/gateway và giới hạn của full-tag comparison

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy không tin cậy
    participant G as Trusted ingress
    participant V as HMAC verifier
    participant N as Shared nonce store
    participant B as Backend
    C->>P: Request + Base64 full tag
    P->>G: Chuyển tiếp hoặc rewrite header/path/body
    G->>V: Strict HTTP parse, raw target và body đã capture
    V->>V: Decode đúng 32-byte tag; canonical + HMAC
    V->>V: MessageDigest.isEqual full tags
    alt MAC đúng, freshness hợp lệ
        V->>N: Atomic claim(client ID, nonce)
        alt Nonce mới
            N-->>V: Accepted
            V->>B: Verified identity và request
            B->>B: Authorization + idempotency
        else Nonce trùng
            N-->>V: Replayed
            V-->>C: Reject
        end
    else MAC sai hoặc tag sai length
        V-->>C: Reject
    end
~~~

Một proxy không biết shared secret thường không thể sửa các trường đã ký và vẫn tạo được HMAC hợp lệ. Nhưng có nhiều trường hợp full-tag comparison **không đủ**:

| Trường hợp | Điều gì có thể sai dù code so sánh đúng? | Thiết kế đúng |
| --- | --- | --- |
| Proxy sửa path/query hoặc percent-encoding | Verifier và router có thể xử lý URI khác nhau | Ràng buộc raw target đã được xử lý, kiểm tra tại boundary phù hợp. |
| Proxy gộp signed header trùng | Mất bằng chứng duplicate; hai hop chọn value khác | Reject tại ingress trước gộp. |
| Gateway đổi Content-Encoding hoặc transform body | Client/verifier hash byte khác | Chốt representation đã ký, reject transform không được quy định. |
| Backend tin `X-Verified: true` do client gửi | Có đường bypass xác thực | Xóa header không tin; xác thực hop nội bộ. |
| Method override sau khi HMAC đã xác minh `POST` | Effective method có thể thành `DELETE` | Vô hiệu hoặc ràng buộc override trong hợp đồng trước routing. |
| Proxy phát lại nguyên request có full tag đúng | HMAC comparison vẫn PASS | Timestamp/nonce store chống replay. |
| Client biết key nhưng gọi tài nguyên ngoài quyền | Chữ ký đúng nhưng authorization sai | ACL/scope/tenant/resource check riêng sau authentication. |

HTTP/2 hoặc HTTP/3 dùng pseudo-header `:method`, `:path` thay vì request line HTTP/1.1. Conversion qua gateway có thể thay đổi biểu diễn URI hoặc tên field; cần test signer/verifier/backend cùng hiểu **method, target, signed header values và body bytes**. **Constant-time comparison không thể sửa một lỗi canonicalization**.

## 10. Timing side channel: đánh giá thực tế và sai lầm khi benchmark

Để đánh giá tính phù hợp của so sánh tag, cần tách:

- **Phân tích code và API:** khẳng định không có vòng lặp do ứng dụng viết sẽ dừng ở byte sai; dùng API chuyên dụng, tag size cố định.
- **Phân tích đe dọa:** ai quan sát được độ trễ, giới hạn số lần thử, độ phân giải thời gian, jitter mạng, vị trí attacker (nội mạng hay Internet), key lookup và cache behavior.
- **Đo đạc có kiểm soát:** chạy test trong môi trường không sản xuất với dữ liệu giả, tập đầu vào đã chọn, đủ số mẫu và phân tích thống kê; không lấy một vài mili-giây khác nhau làm bằng chứng trực tiếp của một timing oracle.
- **Phòng vệ toàn hệ thống:** HTTPS, request rate limit, thông báo lỗi không làm lộ secret, giới hạn CPU/body, chống replay, kiểm tra resource authorization.

**Không nên** viết microbenchmark với `System.nanoTime()` một lần cho “tag sai byte đầu” và một lần cho “sai byte cuối” rồi kết luận đã chứng minh constant-time. JVM có JIT/warm-up, garbage collection, scheduler và nhiều nguồn nhiễu. Kiểm thử timing là hoạt động chuyên sâu, **không thay thế code review và chính sách tag length**.

### 10.1. Có cần ẩn độ dài chữ ký do client gửi không?

Trong hợp đồng mẫu, HMAC-SHA256 full tag 32 byte và Base64 44 ký tự là thông tin **công khai**. Một attacker biết mình vừa gửi 16 hay 33 byte. Server reject nhanh hơn với tag sai chiều dài không tiết lộ một prefix bí mật nào của expected HMAC; đừng ép padding/hashing vô nghĩa để cố làm các lỗi format chạy cùng thời gian.

Điều cần thận trọng hơn là các tín hiệu liên quan **key tồn tại hay không, tenant hoặc resource có tồn tại hay không, quyền truy cập**, vì đó có thể là thông tin không nên lộ. Cùng một HTTP status có thể giúp giảm lộ thông tin, nhưng side channel phải được đánh giá ở cấp hệ thống.

## 11. Replay, rotation và authorization dù hai tag cùng độ dài

### 11.1. Timestamp và nonce vẫn bắt buộc

Khi hacker phát lại nguyên request hợp lệ, `expectedTag` và `receivedTag` vẫn cùng 32 byte **và so sánh bằng nhau**. Vì vậy timestamp/nonce phải được ký trong canonical:

1. Server kiểm tra timestamp bằng **server clock**, ví dụ policy cho phép tối đa 300 giây quá khứ và 60 giây tương lai.
2. Nonce nên sinh từ nguồn ngẫu nhiên mật mã, ví dụ 16 byte của `SecureRandom`.
3. Sau MAC hợp lệ, server **claim nonce nguyên tử** trong store chia sẻ giữa các replica; nếu đã dùng thì reject.
4. TTL nonce phải kéo dài đến hết thời gian timestamp còn có thể được chấp nhận (tính cả biên độ clock/storage).
5. Với request có side effect, retry bằng nonce mới có thể vẫn gây tác dụng lặp; cần **idempotency key đã được ký** và storage nghiệp vụ nguyên tử.

### 11.2. Key rotation không cho phép thay đổi tag length linh động

Trong giai đoạn rotation có thể cùng tồn tại key cũ và mới còn được policy chấp nhận, nhưng mỗi request dùng **một key ID đã ký** trỏ tới **một key record** có audience, algorithm, active window và trạng thái revoke rõ ràng. Server không tự “thử 16 byte tag với key cũ” nếu 32 byte không khớp. Nếu muốn chuyển sang algorithm/tag size khác, hãy lập contract version mới và migration plan.

Key revoked phải bị từ chối **dù full tag 32 byte tính bằng chính secret đó khớp hoàn toàn**.

### 11.3. HMAC đúng không quyết định authorization

Một client có shared secret hợp lệ có thể ký request chuyển khoản của tenant khác. **Authentication** xác nhận request được ký bằng secret hợp lệ và dữ liệu ký không thay đổi; **authorization** kiểm tra client có quyền đối với tenant, tài khoản, hạn mức, amount và hành động `POST` hay không. Hai tag cùng độ dài và khớp là điều kiện xác thực, **không phải giấy phép thực hiện mọi nghiệp vụ**.

## 12. Ma trận kiểm thử

Các ca dưới đây áp dụng cho **HMAC-EQUAL-LENGTH-V1** của bài, HMAC-SHA256 full 32 byte, Base64 chuẩn padded 44 ký tự. Với test replay, giữ cùng nonce; các test khác dùng nonce/store mới.

| Ca kiểm thử | Input/thao tác | Kết quả mong đợi |
| --- | --- | --- |
| HMAC hợp lệ | Cả hai full tag dài 32 byte và byte bằng nhau | MAC comparison PASS; tiếp tục replay và quyền. |
| RFC 4231 known-answer | Key 20 byte `0x0b`, message `Hi There` | HMAC-SHA256 hex `b0344c61...2e32cff7`. |
| Received tag 0 byte | Base64 của byte array rỗng | Reject; **không** so hai mảng rỗng. |
| Received tag 1 byte | Base64 của 1-byte prefix | Reject; không giảm độ khó xuống 8 bit. |
| Received tag 8/16 byte | Base64 của prefix | Reject theo policy full 32 byte. |
| Received tag 31 byte | 31-byte prefix | Reject, không chấp nhận “gần đủ”. |
| Received tag 33 byte | Dãy có thêm một byte | Reject, không cắt về 32 byte. |
| Sai byte đầu, đủ 32 byte | Lật byte index 0 của received tag | `MessageDigest.isEqual` FAIL. |
| Sai byte cuối, đủ 32 byte | Lật byte index 31 của received tag | `MessageDigest.isEqual` FAIL, không trả kết quả đúng do chỉ so prefix. |
| Sai byte giữa, đủ 32 byte | Lật byte index 8 | FAIL dù độ dài giống nhau. |
| Base64 thiếu padding | 43 ký tự thay vì 44 | Reject theo wire contract. |
| Base64 có whitespace | SP/CRLF trong encoded signature | Reject format, không `trim()`. |
| Base64url 43 ký tự | `-`/`_` alphabet URL-safe, no padding | Reject vì sai contract (dù tag bytes có thể giống). |
| Digest body sai | JSON body bị đổi sau ký | Reject SHA-256/body/HMAC. |
| Method/URI bị đổi | `POST` đổi `DELETE` hoặc query khác | Reject contract hoặc HMAC sai. |
| Header bảo mật trùng | Hai `X-Signature` hay hai `X-Key-Id` | Ingress reject trước khi gộp. |
| HTTP/2 ↔ HTTP/1.1 | Proxy sắp xếp lại header khác tên | Verify đúng nếu canonicalization đã định nghĩa và dữ liệu ký không đổi. |
| Proxy đổi raw path/body | HMAC verifier/backend có nguy cơ khác ngữ nghĩa | Reject hoặc bảo vệ original request trong trusted boundary. |
| Key revoked | HMAC đúng bằng key không còn hiệu lực | Reject theo key policy. |
| Timestamp quá hạn | MAC đúng nhưng quá 300 giây | Reject freshness. |
| Replay tuần tự | Hai request cùng HMAC/nonce | Nonce store từ chối lần hai. |
| Replay đồng thời | Hai replica claim cùng nonce | Tối đa một atomic claim thành công. |
| Thiếu quyền tenant/resource | HMAC đầy đủ đúng và nonce mới | Authentication PASS, authorization DENY. |

### Câu hỏi tự kiểm tra

1. Tại sao server phải kiểm tra cả `receivedTag.length == 32` và `expectedTag.length == 32` trước `MessageDigest.isEqual`?
2. Nếu verifier cắt expected HMAC theo `suppliedTag.length`, attacker gửi tag 0 hoặc 1 byte có thể gây lỗi gì?
3. Vì sao “cùng độ dài” chưa chứng minh tag hợp lệ hoặc toàn bộ verifier constant-time?
4. Một contract dùng truncated HMAC cố định khác gì so với tag length do client tự yêu cầu trên mỗi request?
5. `MessageDigest.isEqual` có ngăn proxy thay body hoặc header ngoài canonical không? Nếu không, thiết kế cần gì?
6. Tại sao có thể reject nhanh request Base64 sai length mà vẫn xem đường so sánh full tag là an toàn trước prefix timing leak?
7. Vì sao HMAC đúng vẫn cần timestamp/nonce, key rotation và authorization?

## 13. Checklist triển khai

- [ ] Hợp đồng quy định **tag length cố định**: HMAC-SHA256 full **32 byte** trong bài, không dựa vào client input.
- [ ] Chỉ chấp nhận **một** signature encoding đã định nghĩa: Base64 chuẩn padded 44 ký tự; không fallback sang Base64url/hex.
- [ ] HTTP parser đáng tin reject duplicate signed header, request smuggling, header injection và body vượt giới hạn.
- [ ] Decode signature **strict**, kiểm tra alphabet/padding/ASCII, round-trip canonical và đúng **32 byte**.
- [ ] **Không** so prefix, tự cắt/đệm tag hay biến một tag ngắn thành full tag.
- [ ] Dựng lại canonical từ method, raw URI/query, signed headers và body bytes thực nhận; bảo đảm newline/UTF-8/thứ tự chính xác.
- [ ] Chọn đúng secret theo client ID/key ID, kiểm tra audience, thuật toán, key active/revoked và key rotation.
- [ ] Tính expected tag từ `HmacSHA256`; đảm bảo hai mảng cùng **32 byte** và dùng `MessageDigest.isEqual`.
- [ ] Không dùng `String.equals` trên Base64, early-return byte loop hoặc so SHA-256 không khóa thay cho HMAC.
- [ ] Có test tag sai byte đầu/cuối, ngắn/dài, zero bytes, padding bất thường, body/URI tampering, key revoked và replay.
- [ ] Timestamp/nonce nằm trong chữ ký; claim nonce sau MAC hợp lệ bằng shared atomic store có TTL đúng; idempotency cho side effect.
- [ ] Reverse proxy/gateway phải giữ đúng ngữ nghĩa request đã ký, không cho backend bypass xác thực bằng header tự khai.
- [ ] Log/anomaly monitoring và rate limiting không làm lộ secret; đánh giá timing side channel ở **cấp pipeline**, không chỉ một dòng so sánh.
- [ ] Sau authentication, **authorization theo tenant, action và resource** là bước riêng bắt buộc.

**Kết luận:** Trong constant-time comparison của chữ ký HMAC, **so sánh cùng độ dài** nghĩa là verifier buộc cả expected tag và received tag khớp **đúng độ dài của thuật toán được server chấp nhận**, rồi mới so sánh **toàn bộ byte** bằng primitive thích hợp. Với HMAC-SHA256 full tag, đó là **32 byte**, không phải “ít nhất 1 byte đúng” và không phải 44 byte của chuỗi Base64. Điều kiện này chống lỗi prefix/truncation và giảm rò rỉ vị trí byte sai, nhưng bảo mật request vẫn phụ thuộc canonicalization, key policy, replay protection, proxy/gateway và authorization.
