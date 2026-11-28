# Chữ ký request trong HMAC request authentication

Trong cơ chế **HMAC request authentication**, client và server cùng giữ một khóa bí mật (*shared secret*). Client tạo chữ ký từ các thành phần được quy định của HTTP request; server độc lập tạo lại chữ ký rồi so sánh. Cách làm này thường dùng khi một dịch vụ backend gọi API của đối tác, webhook có xác thực hoặc các hệ thống nội bộ cần chứng minh bên gửi đang nắm giữ khóa đã cấp.

Bài học thuộc chương **Tổng quan HMAC request auth**, tập trung trả lời ba câu hỏi: **ký những gì, tạo chữ ký như thế nào và server kiểm tra ra sao**. Để một chữ ký thực sự có ý nghĩa, hai bên còn phải thống nhất cách biểu diễn request (*canonical request*), xử lý timestamp/nonce chống phát lại (*replay*), quản lý khóa khi xoay vòng và xác định ranh giới proxy/gateway. Chữ ký hợp lệ xác thực request theo khóa đã cấp; **quyền truy cập tài nguyên vẫn phải được kiểm tra riêng**.

## 1. Chữ ký request là gì?

HMAC (*Hash-based Message Authentication Code*) kết hợp một hàm băm mật mã với khóa bí mật. Với HMAC-SHA256:

```text
signature = HMAC-SHA256(secret, UTF8(canonicalRequest))
```

- `secret` là dãy byte bí mật được cấp riêng cho client, không gửi trong request.
- `canonicalRequest` là biểu diễn văn bản **xác định và không mơ hồ** của các phần request cần bảo vệ.
- Chữ ký thường được mã hóa Base64URL (không padding) hoặc hex để truyền trong HTTP header. Mã hóa chỉ là định dạng truyền tải, không phải bước mã hóa bảo mật.

Ví dụ, nếu chữ ký bao phủ phương thức, đường dẫn, query string và hash của body, việc đổi `POST` thành `GET`, sửa số tiền trong JSON hay đổi tham số query đều làm thay đổi dữ liệu đầu vào HMAC. Khi server dùng đúng khóa và đúng quy tắc canonicalization, chữ ký không còn khớp.

HMAC cung cấp **tính toàn vẹn** cho những trường đã ký và **bằng chứng bên gửi biết khóa chung**. Nó không tự mã hóa body, không chứng minh duy nhất một cá nhân đã gửi request (vì hai bên cùng biết khóa), cũng không tự ngăn replay. Do đó, vẫn cần HTTPS, timestamp/nonce và kiểm tra phân quyền.

## 2. Thiết kế một hợp đồng ký thống nhất

Không tồn tại một chuẩn canonical request dùng chung cho mọi API HMAC. Mỗi hệ thống phải công bố **hợp đồng ký có phiên bản**, gồm thuật toán, thứ tự trường, cách lấy từng trường, bảng mã, định dạng chữ ký và quy tắc kiểm tra. Ví dụ dưới đây là một hợp đồng minh họa đủ cụ thể để triển khai client/server; khi tích hợp API thực tế, phải tuân theo đúng hợp đồng của API đó.

### 2.1. Header và dữ liệu được ký

| Thành phần | Ví dụ | Vai trò trong hợp đồng minh họa |
| --- | --- | --- |
| HTTP method | `POST` | Viết hoa ASCII, ký để chống đổi phương thức. |
| Raw request-target | `/v1/payments?dryRun=false&tag=a&tag=b` | Path và query **đúng thứ tự, đúng ký tự percent-encoding** mà hai bên thống nhất; không gồm scheme, host hay fragment. |
| `Content-Type` | `application/json` | Ký giá trị sau khi bỏ khoảng trắng/tab ở hai đầu; không có header thì dùng chuỗi rỗng. |
| `X-Content-SHA256` | Base64URL của SHA-256 body | Hash của byte body thực tế, bao gồm cả body rỗng. |
| `X-Client-Id` | `partner-01` | Định danh client để tìm thông tin khóa/chính sách. |
| `X-Key-Id` | `key-2026-11` | Định danh phiên bản khóa, phục vụ xoay khóa. |
| `X-Timestamp` | `1795800000` | Unix epoch tính bằng **giây**, ở UTC; chống dùng request quá cũ/quá sớm. |
| `X-Nonce` | Chuỗi Base64URL ngẫu nhiên | Giá trị dùng một lần, ngăn phát lại request trong cửa sổ thời gian. |
| `X-Signature` | Base64URL của HMAC-SHA256 | Chữ ký để server xác minh; bản thân giá trị này **không** được đặt vào canonical request. |

Với hợp đồng này, `X-Content-SHA256`, `X-Client-Id`, `X-Key-Id`, `X-Timestamp` và `X-Nonce` đều nằm trong dữ liệu ký, nên kẻ tấn công không thể thay chúng mà vẫn giữ nguyên chữ ký hợp lệ. `Content-Type` cũng được ký để tránh diễn giải body theo định dạng khác. Các header ngoài danh sách, chẳng hạn `User-Agent`, không được HMAC bảo vệ; không được dùng chúng như bằng chứng về danh tính hoặc quyền truy cập.

### 2.2. Định dạng canonical request phiên bản `v1`

Ghép **đúng 10 dòng** theo thứ tự sau, ngăn cách bằng `\n` (LF, một byte `0A` khi mã hóa UTF-8), **không thêm LF cuối chuỗi**:

```text
HMAC-SHA256
v1
<UPPERCASE_METHOD>
<RAW_PATH_AND_QUERY>
<CONTENT_TYPE_TRIMMED>
<BASE64URL_SHA256_OF_BODY>
<CLIENT_ID>
<KEY_ID>
<TIMESTAMP_SECONDS>
<NONCE>
```

Quy ước kèm theo:

1. Byte body là payload mà ứng dụng ký/kiểm tra **sau khi bỏ HTTP transfer framing**, nhưng **trước mọi biến đổi nội dung** (ví dụ tự parse rồi serialize lại JSON, giải nén gzip, sửa encoding). Trong ví dụ này, chỉ chấp nhận `Content-Encoding` vắng mặt hoặc `identity` để dễ bảo đảm hai phía thấy cùng byte.
2. Raw request-target bắt đầu bằng `/`, giữ nguyên phân biệt `%2F` với `/`, `%20` với `+`, thứ tự các tham số và tham số query trùng tên. Không tự sắp xếp, decode/re-encode hay bỏ dấu `/` cuối.
3. `Content-Type` chỉ bỏ khoảng trắng ASCII và tab ở **hai đầu**; mọi phần còn lại, kể cả tham số `charset`, giữ nguyên. Header cùng tên không được xuất hiện nhiều lần nếu có thể diễn giải khác nhau.
4. `X-Content-SHA256` dùng SHA-256 của **toàn bộ byte body**, mã hóa Base64URL theo RFC 4648, không có dấu `=` cuối. Body của GET không có nội dung là dãy byte rỗng, không phải chuỗi ký tự `null`.
5. Không chấp nhận CR hoặc LF trực tiếp trong giá trị trường canonical; giới hạn cú pháp và độ dài của client ID, key ID, timestamp, nonce và target ở tầng tiếp nhận HTTP. Nếu cho phép ký header khác, phải định nghĩa rõ cách gộp giá trị và xử lý trùng lặp.

**Lưu ý về Host:** Ví dụ này không đưa `Host` vào canonical request. Vì vậy khóa phải được ràng buộc với đúng API/đối tượng nhận (*audience*) ở server. Khi cùng khóa có thể dùng ở nhiều hostname hoặc dịch vụ, hãy mở rộng phiên bản hợp đồng để ký một `audience` ổn định hay host công khai đã được chuẩn hóa. Không dựa vào Host nội bộ bị proxy thay đổi.

## 3. Từ HTTP request đến chữ ký

Giả sử client định gửi:

```http
POST /v1/payments?dryRun=false&tag=a&tag=b HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-01
X-Key-Id: key-2026-11
X-Timestamp: 1795800000
X-Nonce: 3J90J8f6dhg2X1N-EQGxJw
X-Content-SHA256: <base64url-sha256-of-body>
X-Signature: <base64url-hmac-sha256>

{"amount":120000,"currency":"VND"}
```

Các giá trị trong dấu `<...>` là chỗ giữ chỗ cần được chương trình tính từ byte thật; chúng **không** phải chữ ký hợp lệ để gửi nguyên văn. Quy trình phía client:

1. Tạo body dạng byte UTF-8 **một lần**; không serialize JSON lần thứ hai sau khi ký.
2. Tính `bodyHash = Base64URL_noPadding(SHA256(bodyBytes))`, điền `X-Content-SHA256`.
3. Sinh timestamp hiện tại và nonce đủ ngẫu nhiên (ít nhất 128 bit); gắn client ID và key ID đã cấp.
4. Lập canonical request bằng method, raw target, Content-Type, body hash và các trường định danh/thời gian theo **chính xác** thứ tự ở mục 2.2.
5. Tính `HMAC-SHA256(secret, UTF8(canonicalRequest))`, mã hóa Base64URL không padding rồi đặt vào `X-Signature`.
6. Gửi **đúng byte body và raw target đã ký** qua HTTPS; không để HTTP client, middleware hoặc gateway thay đổi các trường đã ký mà không thiết kế lại hợp đồng.

Chuỗi canonical tương ứng có dạng:

```text
HMAC-SHA256
v1
POST
/v1/payments?dryRun=false&tag=a&tag=b
application/json
<base64url-sha256-of-body>
partner-01
key-2026-11
1795800000
3J90J8f6dhg2X1N-EQGxJw
```

Với body rỗng, SHA-256 có giá trị Base64URL không padding là `47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU`. Đây là hằng số có thể dùng để kiểm thử việc xử lý GET không có body. Body JSON chứa các cặp key giống nhau về ý nghĩa nhưng khác thứ tự, khác khoảng trắng hoặc khác cách biểu diễn số **vẫn tạo hash khác nhau**, vì HMAC bảo vệ byte thực tế, không bảo vệ một JSON object trừu tượng.

## 4. Hiện thực tạo và kiểm tra chữ ký bằng Java

Ví dụ dưới đây dùng Java tiêu chuẩn (JDK 17+), không phụ thuộc framework hay SDK. `RequestData` chứa **byte body nguyên bản** và raw target lấy ở đúng ranh giới nhận request. Bộ phận tích hợp HTTP có trách nhiệm đọc header, kiểm tra định dạng, giới hạn kích thước và tìm đúng shared secret trước khi gọi các hàm này.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;
import java.util.Locale;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacRequestSigner {
    private static final Base64.Encoder B64 =
            Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder B64_DECODER = Base64.getUrlDecoder();

    private HmacRequestSigner() {}

    public record RequestData(
            String method,
            String rawTarget,
            String contentType,
            byte[] body,
            String clientId,
            String keyId,
            String timestamp,
            String nonce) {}

    public record SignedHeaders(String contentSha256, String signature) {}

    public static SignedHeaders sign(RequestData r, byte[] secret) {
        String bodyHash = encode(sha256(r.body()));
        String canonical = canonicalRequest(r, bodyHash);
        String signature = encode(hmacSha256(secret, canonical));
        return new SignedHeaders(bodyHash, signature);
    }

    public static boolean verifySignature(
            RequestData r,
            String receivedBodyHash,
            String receivedSignature,
            byte[] secret) {
        if (receivedBodyHash == null || receivedSignature == null) {
            return false;
        }
        try {
            // So khớp body hash đã gửi với byte body thực nhận.
            // So sánh dạng mã hóa chuẩn cũng loại padding và biến thể khác.
            String actualBodyHash = encode(sha256(r.body()));
            if (!actualBodyHash.equals(receivedBodyHash)) {
                return false;
            }

            String canonical = canonicalRequest(r, receivedBodyHash);
            byte[] expected = hmacSha256(secret, canonical);
            byte[] actual = B64_DECODER.decode(receivedSignature);
            // Không so sánh MAC bằng String.equals hoặc Arrays.equals.
            return MessageDigest.isEqual(expected, actual);
        } catch (IllegalArgumentException ex) {
            return false; // Canonical fields/chữ ký có định dạng không hợp lệ.
        }
    }

    private static String canonicalRequest(RequestData r, String bodyHash) {
        if (r.method() == null || !r.method().matches("[A-Z]+")) {
            throw new IllegalArgumentException("Invalid HTTP method");
        }
        if (r.rawTarget() == null || !r.rawTarget().startsWith("/")) {
            throw new IllegalArgumentException("Invalid raw request-target");
        }
        String ct = r.contentType() == null ? "" : trimOws(r.contentType());
        String[] fields = {
                "HMAC-SHA256", "v1", r.method(), r.rawTarget(), ct,
                bodyHash, r.clientId(), r.keyId(), r.timestamp(), r.nonce()
        };
        for (String field : fields) {
            if (field == null || field.indexOf('\r') >= 0 || field.indexOf('\n') >= 0) {
                throw new IllegalArgumentException("Invalid canonical field");
            }
        }
        return String.join("\n", fields); // Không có newline cuối.
    }

    private static String trimOws(String s) {
        int begin = 0, end = s.length();
        while (begin < end && (s.charAt(begin) == ' ' || s.charAt(begin) == '\t')) {
            begin++;
        }
        while (end > begin && (s.charAt(end - 1) == ' ' || s.charAt(end - 1) == '\t')) {
            end--;
        }
        return s.substring(begin, end);
    }

    private static byte[] sha256(byte[] input) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(input);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static byte[] hmacSha256(byte[] secret, String canonical) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8));
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static String encode(byte[] bytes) {
        return B64.encodeToString(bytes);
    }
}
```

Ví dụ client chuẩn bị dữ liệu ký:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;

// secret là byte khóa được lấy an toàn từ cấu hình/secret manager.
byte[] body = "{\"amount\":120000,\"currency\":\"VND\"}"
        .getBytes(StandardCharsets.UTF_8);
byte[] randomBytes = new byte[16]; // 128 bit nonce
new SecureRandom().nextBytes(randomBytes);
String nonce = Base64.getUrlEncoder().withoutPadding()
        .encodeToString(randomBytes);

HmacRequestSigner.RequestData data = new HmacRequestSigner.RequestData(
        "POST", "/v1/payments?dryRun=false&tag=a&tag=b",
        "application/json", body, "partner-01", "key-2026-11",
        Long.toString(Instant.now().getEpochSecond()), nonce);

HmacRequestSigner.SignedHeaders signed =
        HmacRequestSigner.sign(data, secret);
// Gửi signed.contentSha256() vào X-Content-SHA256;
// gửi signed.signature() vào X-Signature, cùng metadata trong data.
// HTTP client phải gửi chính xác body và rawTarget đã ký.
```

`MessageDigest.isEqual` dùng để so sánh **byte MAC** theo cách hạn chế rò rỉ thời gian qua so sánh từng ký tự. Đầu vào chữ ký nên được giới hạn độ dài và kiểm tra cú pháp trước khi giải mã; ví dụ một HMAC-SHA256 mã hóa Base64URL không padding dài **43 ký tự**. Trong ứng dụng thực, kiểm tra `method`, path/query, header, nonce và body size trước khi tạo `RequestData`; đoạn mã chỉ minh họa phép ký và phép xác minh MAC.

## 5. Server xác minh request theo thứ tự nào?

Đối với một request đến, server nên có pipeline rõ ràng:

1. **Tiếp nhận và giới hạn:** yêu cầu HTTPS, giới hạn byte body/header, từ chối header trùng hoặc cú pháp mơ hồ, xác định raw target đáng tin cậy tại điểm xác minh. Không dùng body đã qua JSON parser để tính hash.
2. **Đọc định danh và thời gian:** kiểm tra client ID/key ID, timestamp đúng cú pháp số giây Unix, nonce đúng cú pháp và đủ độ dài; từ chối timestamp ngoài ngưỡng, ví dụ lệch hơn **300 giây** so với đồng hồ server. Dùng đồng hồ đồng bộ NTP; không coi timestamp do client khai là đáng tin nếu chưa xác minh chữ ký.
3. **Tìm khóa hợp lệ:** tra theo `(clientId, keyId)` và ràng buộc khóa với API/audience, trạng thái hiệu lực, thuật toán. Không chấp nhận key ID bất kỳ do người gửi tự tạo; không cho client yêu cầu thuật toán yếu hay `none`.
4. **Kiểm tra body và MAC:** tính SHA-256 trên byte body thực nhận, đối chiếu `X-Content-SHA256`, dựng canonical request rồi tính HMAC; so sánh chữ ký theo byte. Chữ ký sai → từ chối mà không ghi nhận nonce.
5. **Chống replay theo cách nguyên tử:** sau khi MAC hợp lệ, ghi `(clientId, keyId, nonce)` vào kho lưu trữ có thao tác **put-if-absent nguyên tử**; chỉ chấp nhận khi ghi thành công lần đầu. Các node phải dùng chung kho lưu trữ/miền nonce. Nếu kho này không khả dụng thì từ chối theo chính sách an toàn, không tự bỏ qua kiểm tra.
6. **Phân quyền:** ánh xạ client đã xác thực sang scope/quyền và kiểm tra hành động/tài nguyên/tenant thực tế. Nếu thiếu quyền, trả `403 Forbidden` ngay cả khi chữ ký đúng.

Ví dụ giả mã cho các bước cuối:

```text
if timestamp outside [now - 300s, now + 300s]: reject 401
secret = keyStore.findActiveSecret(clientId, keyId, audience)
if secret missing: reject 401
if !verifySignature(request, bodyHashHeader, signatureHeader, secret): reject 401
if !nonceStore.setIfAbsent(clientId, keyId, nonce, ttl = 600s): reject 401
if !permissions.allow(clientId, resource, action, tenant): reject 403
processRequest()
```

Vì thời gian gửi được phép lệch `±300` giây, một timestamp có thể còn được chấp nhận trong cửa sổ rộng tối đa **600 giây**. TTL của nonce từ lần chấp nhận đầu tiên nên bao phủ toàn bộ thời gian còn có thể replay; với chính sách này, dùng ít nhất 600 giây (cộng biên an toàn nếu cần). Redis có thể dùng `SET nonce-key value NX EX 600` để ghi một lần; thao tác `GET` rồi `SET` riêng rẽ tạo race condition và có thể cho phép hai request cùng nonce đi qua đồng thời.

Nếu muốn cho phép retry sau khi mất response, phải thiết kế riêng **idempotency key** và cơ chế trả lại kết quả cũ; không đơn giản bỏ kiểm tra nonce. Nonce ngăn phát lại cùng request đã ký, còn idempotency quản lý tác động nghiệp vụ khi khách hàng gửi lại thao tác.

## 6. Các vấn đề dễ phát sinh ở proxy, gateway và framework

| Tình huống | Hậu quả đối với chữ ký | Cách xử lý |
| --- | --- | --- |
| Gateway đổi `/public/pay` thành `/internal/pay` | Raw target client ký khác raw target ứng dụng xác minh. | Xác minh ở gateway **trước rewrite**, hoặc có một trường target gốc do gateway đáng tin cậy chuyển tiếp và bảo vệ; không tin header target gốc do internet tự gửi. |
| Proxy sắp xếp query, đổi `%2F` thành `/` hoặc chuẩn hóa dấu `/` | Canonical request thay đổi dù ý định nghiệp vụ có thể giống nhau. | Kiểm thử byte/chuỗi raw target trên đường đi; thống nhất một phiên bản canonicalization, tránh rewrite các trường đã ký. |
| Middleware parse rồi serialize JSON, thay đổi khoảng trắng/thứ tự key | SHA-256 body không còn khớp. | Tính hash trên byte gốc, trước mọi parser/transform, và gửi nguyên byte khi ký ở client. |
| Reverse proxy giải nén `Content-Encoding: gzip` | Body server nhìn thấy khác body client ký. | Chỉ cho `identity` trong hợp đồng mẫu hoặc định nghĩa rõ ranh giới ký/xác minh cho nội dung nén. |
| Framework chuẩn hóa `Content-Type` hoặc gộp header trùng | Hai phía ký chuỗi khác nhau; có nguy cơ diễn giải không nhất quán. | Chuẩn hóa đúng quy tắc hợp đồng; reject header trùng/khó phân định ở biên nhận. |
| Server lấy URI đã decode hoặc chỉ lấy route template `/users/{id}` | Chữ ký không bảo vệ đúng path tham số. | Dùng raw request-target đã quy định, ký cả tham số đường dẫn/query của request thực. |
| Load balancer định tuyến nhiều instance | Nonce bị dùng lại trên node khác nếu mỗi node lưu cục bộ. | Dùng nonce store chia sẻ và ghi nguyên tử; đồng bộ đồng hồ các node. |

Điểm quan trọng là **client ký thứ server thực sự xác minh**. Trước khi đưa cơ chế vào production, kiểm thử end-to-end qua đúng đường đi thực tế: SDK/HTTP client → CDN/WAF → load balancer → gateway → ứng dụng. Thử các raw path có percent-encoding, query trùng key, body rỗng, JSON có Unicode và request qua proxy rewrite. Hợp đồng phải chỉ rõ điểm thực hiện xác minh nếu request có biến đổi được phép.

## 7. Khóa bí mật và xoay khóa

- **Cấp khóa:** tạo secret bằng bộ sinh số ngẫu nhiên mật mã; với HMAC-SHA256, dùng khóa ngẫu nhiên **256 bit (32 byte)** là lựa chọn thực tế. Mỗi client/tích hợp nên có khóa riêng; lưu ở secret manager/KMS hoặc kho cấu hình bảo mật, không hard-code hoặc commit vào repository.
- **Định danh khóa:** `X-Key-Id` chỉ chọn **bản ghi khóa đã được server quản lý** cho `X-Client-Id`; key ID không phải secret, cũng không phải một tuyên bố quyền hạn. Luôn kiểm tra trạng thái, thời hạn và audience của khóa.
- **Xoay khóa:** tạo key ID mới, cho server xác minh đồng thời khóa cũ và mới trong thời gian chuyển đổi hữu hạn, cập nhật client sang khóa mới, sau đó thu hồi khóa cũ. Client chỉ nên ký bằng khóa đang được chọn; server tra đúng key ID, tránh thử hàng loạt khóa không giới hạn.
- **Thu hồi:** khi nghi lộ secret, vô hiệu hóa khóa tại server và cấp khóa khác. Cửa sổ nonce và timestamp không thay thế thu hồi khóa, vì người biết secret có thể tạo chữ ký mới hợp lệ.
- **Quan sát vận hành:** log client ID, key ID, kết quả kiểm tra, lý do lỗi dạng mã và correlation ID. Không log secret, giá trị HMAC nguyên văn, dữ liệu nhạy cảm trong body hay nonce đầy đủ nếu không cần thiết. Có rate limit cho các lần xác minh thất bại.

HMAC là cơ chế dùng **khóa đối xứng**: client và server cùng giữ secret. Nó phù hợp với tích hợp máy với máy đã thiết lập tin cậy, nhưng không tạo bằng chứng *non-repudiation* giống một số cách ký bất đối xứng. Khi nhiều bên độc lập phải kiểm tra chữ ký mà không được biết khóa ký, cân nhắc chữ ký số bằng khóa riêng/khóa công khai thay vì shared secret.

## 8. Phân biệt các lớp bảo vệ

| Câu hỏi | Cơ chế đảm nhiệm |
| --- | --- |
| Request có bị sửa các trường đã ký hay không? | HMAC trên canonical request. |
| Bên gửi có sở hữu shared secret đã cấp hay không? | Kiểm tra HMAC với khóa đã được đăng ký; phải bảo vệ secret. |
| Request có bị phát lại trong cửa sổ hiệu lực hay không? | Timestamp ký kèm nonce đã ghi nhận nguyên tử. |
| Dữ liệu có bị đọc trộm trên đường truyền hay không? | HTTPS/TLS; HMAC **không** mã hóa dữ liệu. |
| Client có quyền sửa đơn hàng `order-123` của tenant này hay không? | Authorization tại ứng dụng/API sau authentication. |
| Một thao tác thanh toán retry có được thực hiện hai lần hay không? | Idempotency và ràng buộc nghiệp vụ; nonce chỉ hỗ trợ chống replay. |

Khi chữ ký hợp lệ, server mới biết **request đến từ một bên đang giữ khóa tương ứng** và các thành phần được ký chưa bị đổi dưới giả định khóa an toàn. Nếu khóa thuộc client A nhưng body yêu cầu đọc tài nguyên của client B, chữ ký hợp lệ không cấp phép hành động đó. Vẫn cần kiểm tra tenant, đối tượng tài nguyên, vai trò/scope và các điều kiện nghiệp vụ trên server.

## 9. Kiểm thử có hệ thống

Giả sử cả client và server có cùng khóa, và request gốc hợp lệ, hãy kiểm thử các biến thể sau. Mỗi test cần đi qua cùng adapter HTTP và gateway mà môi trường thật sẽ dùng.

| Kịch bản | Kết quả kỳ vọng | Điều chứng minh |
| --- | --- | --- |
| Method, raw target, body, header đã ký và khóa đều khớp; nonce chưa dùng | Xác thực thành công | Hai phía có cùng canonical request và key. |
| Thay một byte trong `amount` sau khi ký | `401` | Body hash/chữ ký phát hiện sửa payload. |
| Đổi thứ tự `tag=a&tag=b` thành `tag=b&tag=a` | `401` | Query order là một phần raw target theo hợp đồng. |
| Đổi `Content-Type` sau khi ký | `401` | Giá trị header này được bao phủ bởi MAC. |
| Body JSON tương đương về ngữ nghĩa nhưng khác whitespace | `401` | Ký byte body chứ không ký biểu diễn dữ liệu đã parse. |
| Timestamp lệch quá 300 giây | `401` | Cửa sổ thời gian bị thực thi. |
| Phát lại cùng request/chữ ký/nonce trong cửa sổ | `401` từ lần thứ hai | Nonce được lưu nguyên tử, chia sẻ giữa các node. |
| Đổi key ID sang khóa khác mà không ký lại | `401` | Key ID nằm trong canonical request và khóa tra cứu đúng client. |
| Dùng khóa cũ sau khi đã thu hồi | `401` | Quy tắc key rotation/revocation có hiệu lực. |
| Chữ ký đúng nhưng client thiếu quyền trên tài nguyên | `403` | Authentication và authorization được tách rõ. |
| Gateway rewrite path trước khi app xác minh | Từ chối hoặc xác minh ở điểm đã định | Hợp đồng nhất quán qua proxy. |

Nên bổ sung kiểm thử chữ ký rỗng/sai Base64URL, header trùng, timestamp không phải số, nonce quá ngắn, payload vượt giới hạn, timeout/non-availability của nonce store và cạnh tranh hai request song song cùng nonce. Với triển khai nhiều ngôn ngữ, tạo **test vector chung**: byte secret giả dùng trong test, request gốc, canonical string, body hash, chữ ký mong đợi; dùng cùng vector kiểm tra Java, Go, Node.js hoặc các SDK khác. Điều này giúp phát hiện lỗi khác nhau về UTF-8, ký tự xuống dòng, encoding và URI trước khi tích hợp thật.

## 10. Bài thực hành

Hãy triển khai một cặp client/server nhỏ cho endpoint `POST /v1/payments` dựa trên hợp đồng `v1`:

1. Client đọc secret từ cấu hình bảo mật, tạo body JSON dạng byte, timestamp và nonce ngẫu nhiên; sau đó ký method, raw target, Content-Type, body hash và metadata.
2. Server giữ lại byte body trước khi parse, kiểm tra chữ ký HMAC bằng khóa tìm theo `(clientId, keyId)`; thử sửa một ký tự body để xác nhận bị từ chối.
3. Dùng kho nonce có thao tác nguyên tử; gửi đồng thời hai request cùng nonce và xác minh chỉ một request có thể qua bước chống replay.
4. Đặt ứng dụng sau gateway có rewrite prefix; quan sát vì sao chữ ký sai và chọn điểm xác minh theo hợp đồng. Thử cả path có `%2F` và query có tham số trùng tên.
5. Thêm hai key ID để mô phỏng giai đoạn rotation, vô hiệu khóa cũ, rồi thêm kiểm tra scope/tài nguyên để quan sát trường hợp `401` khác `403`.

**Tự kiểm tra hiểu bài:** Nếu server chỉ ký body mà không ký method/path thì request có thể bị chuyển sang thao tác khác nào? Nếu dùng timestamp mà không có nonce, đối phương có thể gửi lại request bao nhiêu lần trong thời gian hợp lệ? Nếu gateway đổi path sau khi client ký, ở thành phần nào nên xác minh? Nếu chữ ký đúng nhưng client không có quyền của tenant được chỉ định, server phải quyết định thế nào?

Một thiết kế HMAC request auth đáng tin cậy bắt đầu bằng **hợp đồng canonical request thật rõ ràng**, sau đó mới là lệnh gọi hàm HMAC. Chữ ký chỉ mạnh khi dữ liệu được ký, byte được gửi/nhận, khóa, replay store và việc phân quyền đều được xử lý nhất quán từ client qua gateway đến ứng dụng.
