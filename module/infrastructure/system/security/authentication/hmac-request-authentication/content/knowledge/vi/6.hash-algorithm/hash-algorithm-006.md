# Algorithm deprecation: ngừng sử dụng thuật toán hash và HMAC một cách an toàn

## 1. Algorithm deprecation là gì?

**Algorithm deprecation** là quá trình tuyên bố một thuật toán mật mã hoặc một phiên bản giao thức ký **không còn phù hợp cho các triển khai mới**, lập kế hoạch chuyển đổi các hệ thống đang sử dụng nó và cuối cùng ngừng chấp nhận nó. Trong các hệ thống có tuổi đời dài, đây không đơn thuần là đổi tên thuật toán trong mã nguồn: thuật toán có thể xuất hiện trong key, signature header, canonical request, API gateway, client SDK, kho lưu chữ ký hoặc quy tắc xác minh.

Bài thuộc chương **Hash algorithm** của module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Phạm vi module là **xác thực HTTP request bằng HMAC với shared secret và canonical request** chứa phương thức, URI, header hoặc body theo hợp đồng; thực hành xác minh chữ ký, chống replay với timestamp/nonce, key rotation, kiểm thử proxy/gateway và phân biệt authentication với authorization. Trong phạm vi đó, bài **Algorithm deprecation** tập trung vào việc lựa chọn, theo dõi, thay thế và ngừng hỗ trợ thuật toán **hash/HMAC** một cách có kiểm soát.

Ví dụ hệ thống cũ có client gửi:

```http
POST /v1/orders HTTP/1.1
X-Key-Id: merchant-legacy-01
X-Signature-Version: hmac-v1-sha1
X-Timestamp: 2026-11-28T02:05:00Z
X-Nonce: mH0M5c9vL3rT7pQ2
X-Signature: <HMAC-SHA1 dưới dạng hex>
```

Một phiên bản mới nên sử dụng hợp đồng ký được chuẩn hóa và thuật toán phù hợp hơn, chẳng hạn `HmacSHA256`. Nếu server vẫn chấp nhận `hmac-v1-sha1` vô thời hạn, một client hoặc endpoint lỗi thời có thể trở thành mắt xích yếu; nếu server bỏ phiên bản cũ ngay lập tức mà không chuẩn bị, những client chưa nâng cấp sẽ mất khả năng gọi API. Vì vậy cần đồng thời giải quyết **an toàn giao thức** và **tính tương thích khi triển khai**.

## 2. Phân biệt deprecated, disabled, revoked và compromised

| Trạng thái | Ý nghĩa | Hành động vận hành |
| --- | --- | --- |
| **Supported** | Phiên bản/thuật toán được phép dùng theo chính sách hiện hành. | Chấp nhận theo đúng key scope, contract và kiểm soát bảo mật. |
| **Deprecated** | Không phát hành thêm credential hoặc client mới dùng thuật toán đó; phiên bản cũ có thể được cho phép tạm thời. | Cảnh báo, đo lượng sử dụng, lên lịch ngừng hỗ trợ. |
| **Sunset / disabled** | Server dừng chấp nhận chữ ký phiên bản đó. | Từ chối request phiên bản cũ, hướng dẫn client nâng cấp. |
| **Key revoked** | Một credential/key ID cụ thể không còn tin cậy. | Từ chối **mọi** chữ ký dùng key đó dù thuật toán có thể vẫn hỗ trợ. |
| **Key compromised** | Secret nghi bị lộ hoặc đã bị lộ. | Thu hồi/rotate khẩn cấp, điều tra và xử lý rủi ro; không chờ đến lịch sunset. |

**Deprecation là chính sách hỗ trợ thuật toán/giao thức**, còn **rotation/revocation là chính sách vòng đời khóa**. Chúng liên quan chặt chẽ nhưng không thay thế nhau. Một request có MAC được tính đúng bằng khóa bị thu hồi vẫn phải bị từ chối. Ngược lại, thay key mới nhưng tiếp tục chọn thuật toán cũ không hoàn tất một chương trình algorithm migration.

### Vì sao thuật toán bị deprecated?

Các nguyên nhân thường gặp gồm:

- Có phân tích mật mã mới làm giảm mức tin cậy đối với thuật toán hoặc kích thước đầu ra.
- Chứng nhận, tiêu chuẩn hoặc chính sách an toàn của tổ chức thay đổi.
- Hạ tầng, SDK hoặc thư viện không còn hỗ trợ an toàn một thuật toán.
- Hợp đồng ký cũ có **canonicalization mơ hồ**, thiếu method/URI/body, không chống replay hoặc cho phép client chọn thuật toán tùy ý.
- Kích thước khóa, độ dài MAC bị cắt (truncation), hoặc cách phân phối shared secret không còn đáp ứng mô hình đe dọa.

Không phải mọi lần sunset đều bắt nguồn từ việc phát hiện một cuộc tấn công thực tế. Có thể chủ động loại bỏ thuật toán trước khi nó trở thành rủi ro, nhất là đối với giao thức API dự kiến tồn tại nhiều năm.

## 3. SHA-1, MD5, SHA-256 và những nhận định dễ nhầm

Một hệ thống HMAC có thể dùng **hash function** bên trong HMAC, đồng thời dùng **hash function khác** để tính digest của HTTP body. Cần đánh giá **cả hai**:

```text
bodyHash       = SHA-256(bodyBytes)
canonicalBytes = UTF-8(method + URI + selectedHeaders + bodyHash + ...)
requestMac     = HMAC-SHA256(sharedSecret, canonicalBytes)
```

Trong ví dụ này, `SHA-256` ở dòng đầu là **unkeyed hash**; `HMAC-SHA256` ở dòng cuối là **MAC có khóa**. Đổi một trong hai thuật toán đều thay đổi hợp đồng ký và phải được cả client lẫn server triển khai đồng bộ.

| Thuật toán | Đánh giá cho hệ thống HMAC request mới | Điểm cần hiểu đúng |
| --- | --- | --- |
| **MD5** / `HmacMD5` | Tránh đưa vào thiết kế mới; lên kế hoạch loại bỏ phiên bản cũ theo chính sách. | Collision attack lên **MD5 hash không khóa** không tự động đồng nghĩa kẻ tấn công có thể giả mạo mọi `HmacMD5`; vẫn là lựa chọn legacy khó biện minh cho API mới. |
| **SHA-1** / `HmacSHA1` | Không chọn cho giao thức HMAC HTTP mới; chuyển sang HMAC-SHA-256 hoặc thuật toán được tổ chức phê duyệt. | Các collision thực tế của **SHA-1 hash** không trực tiếp cho phép giả mạo HMAC-SHA1 với secret chưa bị lộ; quyết định sunset còn dựa trên an toàn dài hạn và policy. |
| **SHA-256** / `HmacSHA256` | Lựa chọn thông dụng, phù hợp cho HMAC request authentication hiện đại. | MAC đầy đủ dài **32 byte**; vẫn cần secret đủ mạnh, canonical input đúng và replay protection. |
| **SHA-512** / `HmacSHA512` | Có thể dùng nếu protocol, provider và chính sách thống nhất. | MAC đầy đủ dài **64 byte**; không mặc nhiên an toàn hơn ở mọi cấu hình do vấn đề key/contract vẫn tồn tại. |
| **SHA-3** / biến thể HMAC-SHA3 | Có thể cân nhắc theo yêu cầu môi trường và khả năng hỗ trợ đồng bộ. | Việc provider có thuật toán và cách đặt tên JCA cụ thể phải được kiểm tra; không tự giả định mọi client đều hỗ trợ. |

**Điểm cốt lõi:** tác động của va chạm (*collision*) đối với một hash thuần và khả năng giả mạo HMAC (*MAC forgery*) là **hai mô hình bảo mật khác nhau**. Vì thế không kết luận đơn giản rằng “SHA-1 có collision nên mọi HMAC-SHA1 đã có thể bị giả mạo”; cũng không lấy nhận định đó làm lý do để tiếp tục dùng HMAC-SHA1 vô hạn.

Khi đưa ra chính sách chính thức, cần đối chiếu yêu cầu pháp lý, hướng dẫn mật mã của tổ chức, phiên bản tiêu chuẩn hiện hành và thời hạn hỗ trợ của những nền tảng đang sử dụng. Các tài liệu tham khảo nền tảng gồm **RFC 2104** (HMAC), **RFC 4231** (HMAC-SHA test vectors), **NIST SP 800-131A** (chuyển đổi thuật toán/độ dài khóa) và tài liệu JCA provider được triển khai. Không nên áp dụng một mốc cấm chung cho mọi mục đích sử dụng chỉ từ tên hash.

### Độ dài MAC và truncation

`HmacSHA256` thường xuất **256 bit (32 byte)**. Một số giao thức cho phép cắt MAC còn 128 bit hoặc độ dài khác. Nếu làm vậy, **độ dài phải là một phần của hợp đồng ký cố định**, không để caller tự hạ độ dài. MAC càng ngắn thì khả năng thử giả mạo bằng đoán ngẫu nhiên càng tăng, nhất là khi server cho phép quá nhiều lần thử; đánh giá phải xét cả số lần xác minh, rate limit và yêu cầu bảo mật của hệ thống.

Nên ưu tiên **đầy đủ 32 byte HMAC-SHA256** cho API mới nếu không có ràng buộc định dạng cần truncation. Khi migrate khỏi một giao thức cũ có MAC rút ngắn, phải thay cả độ dài kỳ vọng và encoding; đừng so sánh mỗi phần đầu của MAC mới theo độ dài do client gửi.

## 4. Vì sao “fallback” là nguồn downgrade attack?

**Downgrade attack** là việc kẻ tấn công khiến hai bên dùng cơ chế yếu hơn hoặc chấp nhận điều kiện bảo mật thấp hơn dự kiến. Một lỗi thường gặp:

```text
if (verifyWithSha256(request)) {
    accept();
} else if (verifyWithSha1(request)) {
    accept(); // fallback ngầm
}
```

Lỗi thiết kế này khiến server **tự thử thuật toán cũ** khi một chữ ký mới thất bại, bất kể credential hay client đó có được phép ký theo phiên bản cũ hay không. Nó cũng khó giám sát vì server không có nguyên tắc rõ ràng về phiên bản mà request phải tuân theo.

Mô hình an toàn hơn là:

1. Server có **danh sách phiên bản ký được cấu hình**; mỗi phiên bản gắn cố định với thuật toán MAC, digest, canonicalization và encoding.
2. Credential được ràng buộc với tập phiên bản được phép và có thời điểm hết hạn hỗ trợ; client **không thể dùng header để tự mở rộng tập này**.
3. Request khai báo đúng **một** phiên bản hợp lệ; version/algorithm phải được ràng buộc vào nội dung được ký (hoặc phiên bản giao thức dẫn xuất từ ngữ cảnh tin cậy).
4. Server xác minh **một lần theo phiên bản đã xác định**; chữ ký sai thì từ chối, **không tự thử thuật toán khác**.
5. Khi qua ngày sunset, xóa phiên bản khỏi allowlist; **không fallback** chỉ vì client cũ gặp lỗi.

Chỉ ký string `alg=HmacSHA256` **chưa đủ** để chống downgrade nếu server vẫn cho phép client chọn `HmacSHA1` tùy ý. **Phải có chính sách version theo credential/route và thời điểm sunset**. Phiên bản cũ có thể vẫn được phép cho một nhóm key cũ trong thời gian chuyển tiếp, nhưng những key mới phải được khóa chặt vào phiên bản mới.

## 5. Thiết kế phiên bản ký tách biệt và khó nhầm lẫn

Giả sử service chuyển từ `hmac-v1-sha1` sang `hmac-v2-sha256`. Hãy xem đây là **hai giao thức ký có version**, không chỉ thay tên `Mac.getInstance()`.

Ví dụ request ở phiên bản mới:

```http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.payments.example.test
Content-Type: application/json
X-Key-Id: merchant-v2-2026-11
X-Signature-Version: hmac-v2-sha256
X-Timestamp: 2026-11-28T02:05:00Z
X-Nonce: dvUQzA22XNt4R4e-Pn0EHw
X-Signature: <64 lowercase hex characters>

{"account":"A123","amount":100000}
```

Hợp đồng phiên bản 2 minh họa:

```text
HMAC-REQUEST-V2-HMAC-SHA256
POST
https://api.payments.example.test
/v1/payments?currency=VND
content-type:application/json
x-key-id:merchant-v2-2026-11
x-signature-version:hmac-v2-sha256
x-timestamp:2026-11-28T02:05:00Z
x-nonce:dvUQzA22XNt4R4e-Pn0EHw
<64 lowercase hex characters of SHA-256(bodyBytes)>
```

Đây là **contract minh họa**, không phải tiêu chuẩn chung cho mọi API. Dòng đầu cố định version và thuật toán, các dòng nối bằng **LF (`0A`)**, UTF-8, **không có LF cuối**, tên header trong canonical là chữ thường. Dòng body digest là placeholder mô tả, không đưa nguyên dấu `<`/`>` vào chữ ký. `bodyBytes` phải là byte payload thực được handler xử lý.

**Ràng buộc cần thiết:**

| Thành phần | Quy tắc phiên bản 2 |
| --- | --- |
| `X-Signature-Version` | Đúng một giá trị `hmac-v2-sha256`, nằm trong canonical; không cho phép `alg=none` hay biến thể tùy ý. |
| MAC algorithm | `HmacSHA256` cố định, chỉ chọn từ version ở phía server. |
| Body digest | `SHA-256` trên **body bytes thực nhận**; không tin digest do client khai báo. |
| Signature encoding | Hex thường, **đúng 64 ký tự** cho MAC 32 byte đầy đủ. |
| Method, audience, URI | Method viết hoa, service authority và raw path/query được ký; server đối chiếu audience với route thật. |
| Signed headers | `Content-Type`, key ID, version, timestamp và nonce trong ví dụ; từ chối duplicate signed headers/CR-LF. |
| Key ID | Tra secret cùng trạng thái, service/tenant scope và phiên bản được phép trong kho khóa tin cậy. |
| Timestamp/nonce | Phải được ký **và** được kiểm tra freshness và uniqueness để chống replay. |

Nếu giao thức cũ dùng cách ký, digest hoặc byte encoding khác, verifier phiên bản 1 phải bảo toàn **đúng hợp đồng cũ** trong thời gian chuyển đổi. Đừng dùng một hàm “canonical chung” rồi hy vọng kết quả ký cũ không đổi sau khi thay field; sự thay đổi format là thay đổi protocol.

### Domain separation và key separation

Prefix `HMAC-REQUEST-V2-HMAC-SHA256` đóng vai trò **domain separation** cho dữ liệu ký: cùng bộ field không bị nhầm với hợp đồng dùng prefix khác. Tuy nhiên prefix/version **không phải biện pháp thay thế quản lý khóa**. Khi migrate, nên phát hành **key ID và shared secret mới** cho phiên bản 2; ràng buộc credential mới chỉ cho phép v2. Đồng thời tách key giữa các môi trường, service hoặc tenant để tránh chữ ký được dùng ở phạm vi khác.

Khi một request có version `hmac-v2-sha256` nhưng key ID chỉ được phép `hmac-v1-sha1`, server phải **từ chối**. Khi phiên bản 1 đã sunset, request v1 dùng MAC đúng và key từng hợp lệ cũng bị **từ chối**.

## 6. Ví dụ Java 17+: chọn thuật toán bằng policy, xác minh đúng một phiên bản

Ví dụ sau minh họa cơ chế **deprecation bằng allowlist trên mỗi credential**. Để thấy rõ xử lý tương thích, nó định nghĩa hai version và hai thuật toán `HmacSHA1` (legacy) và `HmacSHA256` (mới). **Không chọn HmacSHA1 cho giao thức mới**; chỉ bật legacy khi thật sự còn client chưa migrate và có hạn sunset. Để đơn giản, cả hai version trong ví dụ dùng cùng **schema canonical minh họa** nhưng có prefix version khác nhau; hệ thống đang vận hành phải triển khai schema **thực tế của từng version**, không đổi lại format cũ.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.HexFormat;
import java.util.Set;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacDeprecationDemo {
    private static final HexFormat HEX = HexFormat.of();
    private static final Duration SKEW = Duration.ofMinutes(5);
    private static final Duration NONCE_TTL = Duration.ofMinutes(11);

    enum Version {
        V1("hmac-v1-sha1", "HmacSHA1", "HMAC-REQUEST-V1-HMAC-SHA1", 20),
        V2("hmac-v2-sha256", "HmacSHA256",
                "HMAC-REQUEST-V2-HMAC-SHA256", 32);

        final String wireName;
        final String macAlgorithm;
        final String canonicalPrefix;
        final int macBytes;

        Version(String wireName, String macAlgorithm,
                String canonicalPrefix, int macBytes) {
            this.wireName = wireName;
            this.macAlgorithm = macAlgorithm;
            this.canonicalPrefix = canonicalPrefix;
            this.macBytes = macBytes;
        }

        static Version parse(String wire) {
            for (Version v : values()) {
                if (v.wireName.equals(wire)) return v;
            }
            return null; // Không tự fallback
        }
    }

    record Request(
            String version, String method, String origin, String rawTarget,
            String contentType, String keyId, String timestamp, String nonce,
            byte[] body, String signatureHex) {}

    record Credential(
            byte[] secret, boolean active, Set<Version> allowedVersions) {}

    interface CredentialStore {
        Credential find(String keyId);
    }

    interface NonceStore {
        // Implement bằng insert-if-absent nguyên tử trên kho dùng chung.
        boolean claim(String keyId, String nonce, Duration ttl);
    }

    static byte[] canonicalBytes(Request r, Version version)
            throws GeneralSecurityException {
        String bodyHash = HEX.formatHex(
                MessageDigest.getInstance("SHA-256").digest(r.body()));
        // Prefix và header version gắn schema vào thuật toán cụ thể.
        String message = String.join("\n",
                version.canonicalPrefix,
                r.method(),
                r.origin(),
                r.rawTarget(),
                "content-type:" + r.contentType(),
                "x-key-id:" + r.keyId(),
                "x-signature-version:" + r.version(),
                "x-timestamp:" + r.timestamp(),
                "x-nonce:" + r.nonce(),
                bodyHash);
        return message.getBytes(StandardCharsets.UTF_8);
    }

    static byte[] mac(byte[] secret, Version version, byte[] message)
            throws GeneralSecurityException {
        Mac instance = Mac.getInstance(version.macAlgorithm);
        instance.init(new SecretKeySpec(secret, version.macAlgorithm));
        return instance.doFinal(message);
    }

    static boolean verify(
            Request r, CredentialStore credentials,
            NonceStore nonces, Clock clock)
            throws GeneralSecurityException {
        if (r == null || r.version() == null || r.method() == null
                || r.origin() == null || r.rawTarget() == null
                || r.contentType() == null || r.keyId() == null
                || r.timestamp() == null || r.nonce() == null
                || r.body() == null || r.signatureHex() == null) return false;

        Version version = Version.parse(r.version());
        if (version == null) return false;

        // Ví dụ có một service/route đã biết và signed headers đơn trị.
        // HTTP adapter phải loại duplicate headers, CR/LF và body quá lớn.
        if (!"POST".equals(r.method())
                || !"https://api.payments.example.test".equals(r.origin())
                || !r.rawTarget().matches("/[A-Za-z0-9/_.~%-]+(?:\\?[A-Za-z0-9=&_.~%-]*)?")
                || !"application/json".equals(r.contentType())
                || !r.keyId().matches("[A-Za-z0-9._-]{1,128}")
                || !r.nonce().matches("[A-Za-z0-9_-]{16,128}")
                || !r.signatureHex().matches(
                        "[0-9a-f]{" + (version.macBytes * 2) + "}")) {
            return false;
        }

        Instant sent;
        try {
            sent = Instant.parse(r.timestamp());
        } catch (DateTimeParseException ex) {
            return false;
        }
        if (sent.getNano() != 0
                || !sent.toString().equals(r.timestamp())
                || Duration.between(clock.instant(), sent)
                        .abs().compareTo(SKEW) > 0) {
            return false;
        }

        Credential credential = credentials.find(r.keyId());
        if (credential == null || !credential.active()
                || credential.secret() == null
                || credential.secret().length == 0
                || credential.allowedVersions() == null
                || !credential.allowedVersions().contains(version)) {
            return false; // Key v2 không thể tự chọn version legacy.
        }

        byte[] expected = mac(
                credential.secret(), version, canonicalBytes(r, version));
        byte[] received = HEX.parseHex(r.signatureHex());
        if (!MessageDigest.isEqual(expected, received)) {
            return false; // Không thử lại với thuật toán khác.
        }

        // Chỉ ghi nonce khi MAC hợp lệ; sau đó còn phải authorization.
        return nonces.claim(r.keyId(), r.nonce(), NONCE_TTL);
    }
}
```

**Giải thích giới hạn của ví dụ:**

- `Version.parse` chỉ nhận hai giá trị khai báo trước; **không** dùng trực tiếp tên thuật toán do caller gửi vào `Mac.getInstance`.
- `allowedVersions` là chính sách **ở server**. Credential mới có thể được cấu hình `Set.of(Version.V2)`; credential cũ chuyển tiếp dùng `Set.of(Version.V1, Version.V2)` khi thật sự cần. Khi sunset v1, loại `V1` khỏi policy hoặc xóa hỗ trợ phiên bản đó.
- Demo xác minh đúng **một thuật toán**. Kết quả không đúng thì trả `false`, tránh cơ chế “thử SHA-256, sai thì thử SHA-1”.
- `canonicalBytes` và parser URI chỉ minh họa cách cấu trúc thông điệp; **adapter production** phải kiểm tra percent-encoding chuẩn, query trùng, HTTP parser ambiguity, body length, signed-header duplicate và phải bảo đảm router xử lý **chính request đã xác minh**.
- Demo dùng SHA-256 cho body digest của cả hai version để tránh thêm một biến thể. **Phiên bản cũ thực tế có thể khác** và phải áp dụng đúng hợp đồng cũ để giữ tương thích trong cửa sổ chuyển đổi.
- `verify` kiểm tra timestamp, nonce nhưng không tự thực hiện **authorization**. Nonce store phải dùng insert-if-absent nguyên tử dùng chung cho các instance; nếu kho nonce lỗi, dịch vụ nên fail closed. Việc server gọi `credentials.find` cần bảo đảm key scope/tenant/route đã được kiểm tra bằng nguồn tin cậy.

Đoạn ví dụ có thể dùng như nền tảng cho adapter HTTP thật, nhưng chưa phải middleware production đầy đủ. Tuyệt đối không coi việc MAC hợp lệ là bằng chứng client có mọi quyền trên API.

## 7. Quy trình migration theo giai đoạn

Không có một công tắc chung để thay mọi phiên bản HMAC. Một kế hoạch thực tế cần phối hợp giữa server, client SDK, API gateway, hệ thống lưu key và bộ phận vận hành.

| Giai đoạn | Việc cần thực hiện | Điều kiện hoàn thành |
| --- | --- | --- |
| **0. Inventory** | Liệt kê API/tenant/client, key ID, thuật toán MAC, body hash, canonical schema, độ dài chữ ký, gateway và thư viện Java đang dùng. | Biết chính xác các đường đi còn legacy. |
| **1. Define v2** | Công bố contract HMAC-SHA256, encoding, key scope, replay policy, version và ngày sunset v1. | Có golden fixtures dùng chung client/server/gateway. |
| **2. Deploy verifier** | Cho server hỗ trợ v2 cùng một phạm vi v1 được whitelist; gắn policy theo credential, không fallback. | Các request v2 hợp lệ và v1 được phép chạy qua kiểm thử end-to-end. |
| **3. Provision keys** | Cấp shared secret và key ID mới riêng cho v2; phân phối bằng kênh an toàn, không log. | Client thử nghiệm ký bằng v2 thành công trên môi trường kiểm thử. |
| **4. Migrate clients** | Cập nhật SDK, bật v2 theo từng nhóm, quan sát `signature_version` và tỷ lệ xác minh thất bại. | Lưu lượng v1 giảm, không ảnh hưởng tác vụ quan trọng. |
| **5. Sunset legacy** | Chặn key/route chỉ còn v1, thu hồi key legacy; bỏ v1 khỏi allowlist đúng ngày đã thông báo. | Không còn request v1 được chấp nhận; có cảnh báo cho client chưa chuyển. |
| **6. Cleanup** | Loại code, configuration và test path thực thi v1 khỏi phiên bản sản phẩm; giữ test fixture lưu trữ nếu cần audit. | Không còn cơ chế legacy âm thầm phục hồi qua rollback. |

### Triển khai an toàn qua nhiều node

Ở hệ thống phân tán, một phần backend có thể đã chấp nhận v2 trong khi node khác chưa cập nhật. Dùng **một chính sách deployment nhất quán** trước khi phát hành SDK/client v2. Tương tự, proxy có thể sửa URI/header, làm chữ ký v2 sai dù thuật toán HMAC-SHA256 đúng. Nên test cả **direct integration** và **đường đi thật qua load balancer/gateway**, bao gồm HTTP/1.1 và HTTP/2 nếu hệ thống hỗ trợ.

Không để client tự “rơi về v1” khi nhận `401`, timeout hoặc lỗi mạng. Những tín hiệu này có thể do attacker gây ra hoặc là lỗi không liên quan thuật toán. Một client chỉ được dùng v1 khi có **cấu hình chuyển tiếp được kiểm soát rõ ràng**, theo credential và thời hạn còn hiệu lực; không tự xoay thuật toán đến khi được chấp nhận.

### Theo dõi adoption mà không rò rỉ secret

Có thể ghi metrics theo `signature_version`, loại lỗi, key ID đã được làm mờ hoặc định danh tổng hợp, route, môi trường và client SDK version. Tránh log shared secret, raw chữ ký đầy đủ và payload nhạy cảm. Các chỉ số hữu ích:

- Tỷ lệ request ký v1/v2 theo **ngày, route, tenant và SDK**.
- Lỗi “unsupported version”, “invalid signature”, “expired timestamp”, “duplicate nonce” và “revoked key” theo nhóm; phản hồi công khai có thể là lỗi xác thực chung.
- Client nào chưa phát sinh request v2, thời hạn key và ngày sunset.
- Lỗi không tương thích giữa các instance, gateway hoặc thư viện sau deploy.

Rollback chỉ nên quay lại một **phiên bản triển khai có chính sách bảo mật còn được phê duyệt**. Một bản rollback không được lặng lẽ mở lại HMAC-SHA1 cho mọi credential mới hoặc bỏ bước kiểm tra replay.

## 8. Tách algorithm migration khỏi key rotation và replay protection

Ba việc cần quản lý riêng:

1. **Algorithm migration:** đổi `HmacSHA1` → `HmacSHA256`, định dạng MAC, canonical contract và policy chấp nhận version.
2. **Key rotation:** đổi shared secret và key ID; thay secret cũ bằng secret mới theo thời hạn, liên kết mỗi key với trạng thái active/revoked, tenant/service scope và version được phép.
3. **Replay protection:** timestamp và nonce phải là field **được ký** trong canonical request, đồng thời server kiểm tra cửa sổ thời gian, lưu nonce nguyên tử với TTL phù hợp.

Một request dùng HMAC-SHA256 hoàn toàn đúng vẫn có thể bị phát lại nếu server không kiểm tra timestamp/nonce. Tương tự, một request dùng v2 vẫn có thể là request **không được phép** nếu caller thiếu authorization cho tài nguyên. Đổi thuật toán không tự giải quyết các vấn đề này.

Nếu key v1 đã bị compromise, cần **thu hồi ngay key đó** và phát hành key mới; đừng dựa vào việc nâng thuật toán với **cùng secret đã lộ**. Nếu hệ thống cho phép đồng thời hai phiên bản dùng cùng secret trong giai đoạn chuyển tiếp, phải đánh giá phạm vi chấp nhận và nguy cơ nhầm domain/canonical; ưu tiên secret độc lập để giảm ảnh hưởng chéo.

## 9. Kiểm thử deprecation và chống downgrade

Để kiểm thử tích hợp, tạo bộ golden fixtures chứa `algorithm/version`, key ID, secret test bytes, canonical request bytes, body bytes, signature bytes kỳ vọng và verdict. Các fixture nên bao phủ cả phiên bản đang hỗ trợ và phiên bản bị sunset; không đặt secret production vào fixture.

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| Key v2, request `hmac-v2-sha256`, canonical đúng, timestamp hợp lệ, nonce mới. | **Chấp nhận** sau khi kiểm tra authorization. |
| Key v2 nhưng request khai `hmac-v1-sha1`. | **Từ chối** ngay do key policy không cho phép v1. |
| Key legacy được cấp quyền v1 tạm thời, HMAC-SHA1 đúng, trước ngày sunset. | Có thể **chấp nhận** trong giai đoạn chuyển tiếp nếu mọi kiểm tra còn lại đạt. |
| Cùng request legacy sau khi bỏ v1 khỏi allowlist. | **Từ chối**, dù chữ ký HMAC-SHA1 vẫn tính đúng. |
| Request khai `alg=none`, `HmacMD5` hoặc version lạ. | **Từ chối**, không thử thuật toán do caller chỉ định. |
| Signature v2 sai, nhưng nếu dùng HMAC-SHA1 lại khớp với một nội dung nào đó. | **Từ chối**: không fallback sang v1. |
| Thay `X-Signature-Version`, key ID, method hoặc raw URI mà giữ chữ ký. | **Từ chối** vì canonical bytes thay đổi hoặc key policy không khớp. |
| MAC v2 bị cắt ngắn 8/16 byte rồi gửi. | **Từ chối** theo hợp đồng yêu cầu đủ 32 byte (64 ký tự hex). |
| Thay byte body, sửa thứ tự query hoặc đổi `Content-Type`. | MAC của request đã sửa khác; chữ ký cũ thất bại. |
| Gateway rewrite path, percent-encoding, header hoặc decompress body trước verify. | Phát hiện mismatch; sửa điểm verify/canonicalization theo contract, không tắt xác minh. |
| Request HMAC-SHA256 đúng nhưng timestamp ngoài cửa sổ hoặc nonce trùng. | Chống replay **từ chối**. |
| Request HMAC-SHA256 đúng nhưng key revoked, tenant/route sai hoặc thiếu quyền. | **Từ chối** theo key scope/authorization. |
| Triển khai rolling deploy: một node vẫn chỉ hiểu v1, một node hiểu v2. | Kiểm thử phát hiện bất nhất; hoàn tất rollout server trước khi chuyển client. |
| Hệ thống gặp lỗi secret manager/nonce store. | **Fail closed**, không chấp nhận request vì “lỗi hạ tầng”. |

### Bài tập thực hành

Giả sử hệ thống có hai client:

```text
client-old:  keyId=old-17, allowedVersions={V1}, sunset=2027-01-31
client-new:  keyId=new-42, allowedVersions={V2}
```

Hãy thực hiện:

1. Ký hai request cùng body bằng v1 và v2 **theo đúng từng contract**, so sánh canonical bytes, algorithm name, MAC length và signature encoding.
2. Thay header version từ v2 sang v1 nhưng không ký lại; giải thích vì sao verifier phải từ chối trước hoặc tại bước xác minh.
3. Cố gửi chữ ký v1 với `new-42`; kiểm tra key policy ngăn downgrade.
4. Chuyển `old-17` sang key mới v2, thực hiện key rotation và kiểm tra nonce/replay vẫn hoạt động.
5. Giả lập hết hạn hỗ trợ v1, xác minh `old-17` không còn được chấp nhận dù signature trước đây đúng.
6. Chạy golden fixture qua gateway có URL rewrite để xác định khác biệt do canonical input, không phải do lựa chọn thuật toán.

Với từng bước, ghi lại **version, key scope, canonical bytes, MAC được tính, replay result và authorization result**. Đây là cách tách lỗi migration khỏi lỗi mật mã hoặc lỗi nghiệp vụ.

## 10. Checklist để ngừng hỗ trợ thuật toán an toàn

- [ ] Lập inventory những thuật toán hash/HMAC, độ dài MAC, phiên bản canonical và client SDK đang hoạt động.
- [ ] Chọn thuật toán hiện hành theo policy; ưu tiên HMAC-SHA256 với secret đủ mạnh cho giao thức request mới.
- [ ] Phân biệt rủi ro collision của hash thuần với an toàn thực tế của HMAC; không đánh đồng nhưng cũng không duy trì legacy vô hạn.
- [ ] Định nghĩa phiên bản giao thức được ký, algorithm mapping cố định, encoding, body hash, method/URI/header và audience rõ ràng.
- [ ] Bỏ `algorithm` tùy ý do client chỉ định; dùng allowlist/version policy theo key ID và route, không fallback sau khi MAC sai.
- [ ] Dùng secret và key ID mới cho version mới, có thời hạn rotation/sunset/revocation và scope theo tenant/service.
- [ ] Giữ timestamp/nonce trong canonical, chống replay bằng nonce store dùng chung với thao tác nguyên tử.
- [ ] So sánh MAC dạng byte với hàm phù hợp, từ chối sai format/độ dài và xử lý lỗi theo nguyên tắc fail closed.
- [ ] Kiểm thử client/server/gateway với golden fixtures, các trường hợp downgrade, version sunset, proxy rewrite và rolling deploy.
- [ ] Thông báo lịch sunset, theo dõi adoption, hỗ trợ client nâng cấp và sau cùng loại bỏ code path legacy được thực thi.
- [ ] Sau xác thực HMAC luôn kiểm tra authorization; TLS vẫn cần để xác minh server và bảo mật đường truyền.

**Điểm cần nhớ:** *Algorithm deprecation* là **thay đổi có kiểm soát cả giao thức ký và chính sách chấp nhận**, không phải chỉ thay `HmacSHA1` bằng `HmacSHA256` trong một dòng Java. Một quá trình chuyển đổi an toàn cần version rõ ràng, khóa/scope phù hợp, canonical bytes nhất quán, giai đoạn tương thích có giới hạn, chống downgrade, chống replay và ngày sunset được thực thi thật.
