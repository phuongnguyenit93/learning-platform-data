# Message integrity trong xác thực HMAC cho HTTP request

## 1. Message integrity có nghĩa là gì?

**Message integrity (tính toàn vẹn thông điệp)** là khả năng phát hiện việc nội dung đã được bảo vệ của một HTTP request bị thay đổi kể từ khi bên gửi tạo chữ ký. Trong cơ chế **HMAC request authentication**, client và server biết cùng một **shared secret**; client tính HMAC trên biểu diễn chuẩn của request (**canonical request**), còn server tự dựng lại biểu diễn đó và tính HMAC để đối chiếu.

Chủ đề này thuộc phần **Tổng quan HMAC request auth** của module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`: thiết kế xác thực HTTP request bằng shared secret, quy định phương thức/URI/header/body nào được ký, chống replay bằng timestamp/nonce, quản lý key rotation và kiểm thử tương tác với proxy/gateway. Mục tiêu ở đây là hiểu chính xác **tính toàn vẹn bảo vệ những byte nào**, cách kiểm chứng và giới hạn của sự bảo vệ đó.

Giả sử một client gửi lệnh thanh toán:

```http
POST /v1/payments?currency=VND HTTP/1.1
Content-Type: application/json

{"account":"A123","amount":100000}
```

Nếu `amount` bị đổi thành `900000` hoặc URI bị đổi sang tài nguyên khác **và các giá trị đó nằm trong dữ liệu được ký**, chữ ký HMAC server tính lại sẽ khác chữ ký client gửi. Server phải từ chối request. Nếu hệ thống chỉ ký body mà bỏ qua phương thức hoặc URI, HMAC **không** phát hiện việc thay đổi những phần bị bỏ qua.

Phân biệt các khái niệm liên quan:

| Khái niệm | HMAC request authentication cung cấp gì? |
| --- | --- |
| **Integrity** | Phát hiện thay đổi đối với **các thành phần được ký**; không tự bảo vệ field nằm ngoài hợp đồng ký. |
| **Authentication** | Một chữ ký đúng là bằng chứng bên tạo chữ ký biết shared secret tương ứng với key ID; việc gắn key đó với danh tính client do server quản lý. |
| **Confidentiality** | **Không có**: HMAC không mã hóa request. Vẫn cần HTTPS/TLS để bảo vệ dữ liệu trên đường truyền. |
| **Replay protection** | **Không tự có**: một request và chữ ký hợp lệ có thể bị gửi lại nếu không kiểm tra timestamp, nonce hoặc cơ chế tương đương. |
| **Authorization** | **Không quyết định quyền**: request có chữ ký đúng vẫn phải qua kiểm tra client có được phép thao tác tài nguyên hay không. |
| **Non-repudiation** | Không bảo đảm theo nghĩa chữ ký số bất đối xứng: cả hai bên biết shared secret đều có thể tạo HMAC. |

### Vì sao `SHA-256(body)` đơn thuần chưa đủ?

Hash thường giúp phát hiện thay đổi **khi giá trị hash kỳ vọng được tin cậy**, nhưng nếu kẻ tấn công có thể sửa cả body lẫn hash gửi kèm, họ chỉ cần tính lại hash. HMAC dùng khóa bí mật:

```text
bodyDigest = SHA-256(bodyBytes)
canonical  = canonicalize(method, target, selectedHeaders, bodyDigest)
signature  = HMAC-SHA256(sharedSecret, UTF8(canonical))
```

Vì không biết `sharedSecret`, bên tấn công không thể tạo chữ ký hợp lệ cho nội dung đã sửa với xác suất thực tế đáng kể, giả sử thuật toán và khóa được dùng an toàn. Độ mạnh này không bù đắp được hợp đồng ký thiếu field, key bị lộ hoặc server tái sử dụng dữ liệu không đúng cách.

## 2. Ranh giới bảo vệ: ký đúng những gì server sẽ xử lý

Một request đi từ client qua load balancer, reverse proxy hoặc API gateway trước khi vào ứng dụng. Các thành phần này có thể viết lại path, query, header hoặc body. Hai phía cần thống nhất **điểm quan sát request** và **biểu diễn byte** được ký.

| Thành phần | Nên bảo vệ như thế nào? | Điều gì xảy ra nếu bỏ qua? |
| --- | --- | --- |
| HTTP method | Ký giá trị như `POST`, `PUT`, `DELETE`. | Chữ ký có thể bị dùng với thao tác khác nếu các điều kiện khác cũng trùng. |
| Request target | Ký raw path và raw query theo quy tắc rõ ràng. | Kẻ tấn công có thể đổi ID tài nguyên, tham số lọc hoặc đích thao tác. |
| Header ảnh hưởng cách diễn giải | Ký các header được hợp đồng xác định, ví dụ `Content-Type` và key ID. | Đổi cách xử lý body hoặc ngữ cảnh xác thực mà chữ ký không phát hiện. |
| Body | Ký byte body trực tiếp hoặc hash được tính từ **byte body thực nhận**. | Payload có thể bị sửa mà server vẫn chấp nhận chữ ký trên phần còn lại. |
| Timestamp và nonce | Đưa vào canonical request **và** kiểm tra độ mới/trùng lặp ở server. | Có thể thay metadata hoặc phát lại request đã ký. |
| Header không được ký | Chỉ dùng cho thông tin không ảnh hưởng quyết định bảo mật/nghiệp vụ, hoặc có lớp bảo vệ riêng. | Những header này vẫn có thể thay đổi mà HMAC không phát hiện. |

**Quy tắc thiết kế:** những giá trị server dùng để quyết định *làm gì, lên tài nguyên nào, với dữ liệu nào, dưới danh tính nào* phải được bao phủ bằng chữ ký hoặc bằng một ràng buộc bảo mật tương đương. Đặc biệt, không chỉ ký JSON `amount` rồi bỏ qua `account`, `currency` hay endpoint.

## 3. Ví dụ hợp đồng ký HMAC-SHA256 phiên bản 1

Hãy xem **một hợp đồng minh họa** cho client gọi `POST /v1/payments`. Đây là quy ước do hai hệ thống thống nhất, không phải định dạng HMAC HTTP duy nhất hay một chuẩn chung được mọi gateway hỗ trợ.

**Request gửi đi:**

```http
POST /v1/payments?currency=VND&mode=instant HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: merchant-2026-11
X-Timestamp: 2026-11-28T02:05:00Z
X-Nonce: x3V89b7mT2k5pQ8z
X-Signature: <64 ký tự hex viết thường>

{"account":"A123","amount":100000}
```

Trong ví dụ này, hợp đồng ký định nghĩa:

1. Algorithm `HmacSHA256`; chữ ký truyền bằng **64 ký tự hex viết thường**.
2. `method` được phép ở dạng chữ hoa; `rawTarget` là **raw path + dấu `?` + raw query** nếu query tồn tại, giữ nguyên thứ tự và percent-encoding. Không có fragment.
3. Chỉ chấp nhận đúng một `Content-Type: application/json`; giá trị này được ký. `X-Key-Id`, `X-Timestamp` dạng UTC ISO-8601 giây và `X-Nonce` cũng được ký; header nhiều giá trị/CR/LF bất hợp lệ phải bị từ chối.
4. `bodyBytes` là byte body HTTP mà application thực sự xử lý sau khi bỏ HTTP transfer framing, **trước khi parse/chỉnh sửa JSON**. Hash dùng SHA-256, biểu diễn bằng 64 ký tự hex viết thường. Server **tự tính hash từ body nhận được**.
5. Canonical string gồm các dòng UTF-8 nối bằng một byte LF (`0A`), đúng thứ tự dưới đây, **không có LF ở cuối**; tên header là chữ thường. `HMAC-SHA256-V1` giúp cố định phiên bản hợp đồng.

```text
HMAC-SHA256-V1
POST
/v1/payments?currency=VND&mode=instant
content-type:application/json
x-key-id:merchant-2026-11
x-timestamp:2026-11-28T02:05:00Z
x-nonce:x3V89b7mT2k5pQ8z
<SHA-256(bodyBytes) dưới dạng hex viết thường>
```

Dòng cuối là **ký hiệu thay thế** cho digest 64 ký tự thực tế, không được đưa nguyên dấu `<...>` vào chuỗi ký. `Host` không nằm trong hợp đồng minh họa này: nếu backend định tuyến/ủy quyền theo host, tenant hoặc authority, **phải ký và đối chiếu thông tin đó**, hoặc buộc nó vào key/route bằng chính sách tin cậy riêng.

Client tạo `X-Signature = hex(HMAC-SHA256(secret, UTF8(canonicalString)))`. Server lấy secret theo `X-Key-Id` từ kho khóa tin cậy, dựng lại canonical string từ **request do server quan sát** rồi tính HMAC. Không dùng canonical string hay body hash do client gửi sẵn làm nguồn sự thật: làm như vậy có thể xác nhận một thông điệp khác với thông điệp ứng dụng đang xử lý.

### Tại sao canonicalization phải chặt chẽ?

Các cặp sau có thể tương đương đối với một bộ phận xử lý HTTP nhưng **khác byte**:

- `?a=1&b=2` và `?b=2&a=1`;
- `/files/a%2Fb` và `/files/a%2fb`;
- JSON `{"amount":100000}` và `{ "amount": 100000 }`;
- `application/json` và `application/json; charset=utf-8`.

Hợp đồng minh họa **không tự chuẩn hóa** các trường hợp này. Nếu client ký một phiên bản còn server xử lý hoặc xác minh phiên bản khác, request hợp lệ có thể bị từ chối; tệ hơn, việc xác minh trên một URI nhưng ứng dụng định tuyến theo URI đã diễn giải khác có thể tạo lỗ hổng. Nếu cần hỗ trợ nhiều biến thể, hãy mô tả và kiểm thử thuật toán chuẩn hóa cụ thể ở cả hai phía, không dựa vào quy tắc ngầm của framework.

Đặc biệt với proxy/gateway:

- Một proxy có thể bỏ/giữ dấu `/` cuối, giải mã `%2F`, đổi thứ tự query, gộp header hoặc điều chỉnh `Content-Type`.
- `Content-Length`, `Transfer-Encoding` và các header hop-by-hop thường thay đổi theo từng hop; chỉ ký chúng khi thật sự kiểm soát được biểu diễn đầu cuối.
- HTTP/2 dùng pseudo-header như `:path`, còn HTTP/1.1 có request-target; adapter phải cung cấp cùng `rawTarget` mà hợp đồng mong đợi.
- Nếu gateway giải nén/chuyển mã body, cần chọn điểm ký sau bước biến đổi đó hoặc không cho phép biến đổi. Cả hai phía phải ký cùng **byte body mà nghiệp vụ tiêu thụ**.

## 4. Xác minh integrity bằng Java 17+

Ví dụ sau tách phần mật mã khỏi HTTP framework để làm rõ thứ tự kiểm tra. Adapter nhận request phải cung cấp `rawTarget`, **snapshot body bytes** và các header đơn trị đã được kiểm tra. Giả định lớp adapter đã từ chối header trùng, newline injection và cách parse request bất nhất; ứng dụng thực tế cần thêm giới hạn kích thước body và kiểm soát thuật toán ở cấu hình cố định.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.HexFormat;
import java.util.function.Function;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacRequestIntegrity {
    private static final Duration CLOCK_SKEW = Duration.ofMinutes(5);
    private static final Duration NONCE_TTL = Duration.ofMinutes(11);

    // body là snapshot byte của payload, không phải JSON đã parse rồi serialize.
    public record SignedRequest(
            String method, String rawTarget, String contentType,
            String keyId, String timestamp, String nonce,
            byte[] body, String signatureHex) {}

    // Triển khai phải insert-if-absent nguyên tử trên kho dùng chung.
    public interface NonceStore {
        boolean claim(String keyId, String nonce, Duration ttl);
    }

    public static String canonical(SignedRequest r)
            throws NoSuchAlgorithmException {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(r.body());
        String bodyHash = HexFormat.of().formatHex(digest);
        return String.join("\n",
                "HMAC-SHA256-V1",
                r.method(),
                r.rawTarget(),
                "content-type:" + r.contentType(),
                "x-key-id:" + r.keyId(),
                "x-timestamp:" + r.timestamp(),
                "x-nonce:" + r.nonce(),
                bodyHash);
    }

    public static byte[] mac(byte[] secret, String canonical)
            throws GeneralSecurityException {
        Mac hmac = Mac.getInstance("HmacSHA256");
        hmac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return hmac.doFinal(canonical.getBytes(StandardCharsets.UTF_8));
    }

    public static boolean verify(
            SignedRequest r,
            Function<String, byte[]> lookupSecret,
            NonceStore nonces,
            Clock clock) throws GeneralSecurityException {
        if (r == null || r.body() == null || r.method() == null
                || r.rawTarget() == null || r.contentType() == null
                || r.keyId() == null || r.timestamp() == null
                || r.nonce() == null || r.signatureHex() == null) {
            return false;
        }
        if (!r.method().matches("[A-Z]+")
                || !r.rawTarget().startsWith("/")
                || r.rawTarget().contains("\r")
                || r.rawTarget().contains("\n")
                || !"application/json".equals(r.contentType())
                || !r.keyId().matches("[A-Za-z0-9._-]{1,128}")
                || !r.nonce().matches("[A-Za-z0-9_-]{16,128}")
                || !r.signatureHex().matches("[0-9a-f]{64}")) {
            return false;
        }

        Instant issuedAt;
        try {
            issuedAt = Instant.parse(r.timestamp());
        } catch (DateTimeParseException ex) {
            return false;
        }
        // Yêu cầu duy nhất cách ghi UTC của timestamp.
        if (issuedAt.getNano() != 0
                || !issuedAt.toString().equals(r.timestamp())
                || Duration.between(clock.instant(), issuedAt)
                        .abs().compareTo(CLOCK_SKEW) > 0) {
            return false;
        }

        byte[] secret = lookupSecret.apply(r.keyId());
        if (secret == null || secret.length == 0) {
            return false;
        }

        byte[] expected = mac(secret, canonical(r));
        byte[] actual = HexFormat.of().parseHex(r.signatureHex());
        if (!MessageDigest.isEqual(expected, actual)) {
            return false;
        }

        // Chỉ ghi nonce sau khi HMAC hợp lệ; trả false nếu đã có nonce.
        return nonces.claim(r.keyId(), r.nonce(), NONCE_TTL);
    }
}
```

**Cách tích hợp:** Client dùng hàm `canonical` tương đương và `mac`, rồi gửi chữ ký hex. Server ánh xạ `X-Key-Id` tới secret trong secret manager, gọi `verify`, và chỉ chuyển cho handler nghiệp vụ khi kết quả là `true`. Thực tế cần bảo đảm dữ liệu `body` bất biến giữa lúc xác minh và lúc xử lý, hoặc truyền chính snapshot đã xác minh cho handler. Adapter cũng cần kiểm tra raw target hợp lệ và ràng buộc method, route, kích thước, header theo contract trước khi sử dụng.

`MessageDigest.isEqual` là cách so sánh byte chữ ký có khả năng kháng timing attack hơn so sánh chuỗi thông thường. Kiểm tra `signatureHex` trước giúp đảm bảo đầu vào có đúng độ dài và encoding. Các lỗi nội bộ khi truy cập secret manager hoặc Redis nên được xử lý theo chính sách lỗi của hệ thống; **không** mặc định cho request đi qua nếu xác minh gặp sự cố.

Để kiểm tra riêng primitive HMAC-SHA256, có thể dùng test vector công khai của RFC 4231 (test case 1): key gồm 20 byte `0x0b`, message ASCII `Hi There`, HMAC kỳ vọng là:

```text
b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7
```

Vector này xác minh **thuật toán HMAC**, chưa đủ xác minh việc dựng canonical request HTTP.

## 5. Integrity khác gì chống replay?

HMAC bảo đảm nội dung có chữ ký không bị thay đổi mà không biết khóa. Nhưng kẻ tấn công có thể gửi lại **nguyên vẹn** `method + URI + headers + body + signature`: chữ ký vẫn đúng. Vì vậy cần:

1. **Timestamp được ký:** từ chối thời điểm ngoài cửa sổ, ví dụ lệch hơn 5 phút so với đồng hồ server; dùng UTC và đồng bộ đồng hồ các node.
2. **Nonce được ký:** mỗi request chọn nonce khó đoán, đủ dài; sau khi chữ ký đúng, server atomically lưu cặp `(keyId, nonce)` với TTL bao trùm khoảng request có thể còn hợp lệ. Trong ví dụ, cửa sổ lệch ±5 phút nên TTL 11 phút có biên an toàn nhỏ.
3. **Kho nonce dùng chung:** các instance ứng dụng phải dùng một kho có phép insert-if-absent nguyên tử (ví dụ Redis `SET key value NX EX <ttl>`), tránh hai request đồng thời cùng vượt qua.
4. **Idempotency riêng cho nghiệp vụ:** xử lý request lặp do retry hoặc mạng không ổn định là một bài toán khác. Có thể thiết kế idempotency key được ký, nhưng không thay thế việc chống replay.

Nonce chưa từng xuất hiện **không đủ** để thay cho xác minh chữ ký; timestamp chưa hết hạn **không đủ** để chống gửi lại cùng request trong cửa sổ. Nên chỉ ghi nonce sau khi kiểm tra HMAC thành công để hạn chế kẻ tấn công chiếm chỗ bằng request giả mạo.

## 6. Key rotation và ý nghĩa đối với integrity

`X-Key-Id` là **định danh khóa**, không phải khóa bí mật. Server chỉ tìm secret từ nguồn quản lý khóa tin cậy và chỉ chấp nhận key ID còn hoạt động. Khi rotation:

- Phát hành khóa mới với key ID mới; client chuyển sang ký bằng khóa mới.
- Trong giai đoạn chuyển tiếp có thể chấp nhận cả khóa cũ và khóa mới theo thời hạn rõ ràng.
- Thu hồi khóa cũ khi hết thời gian chuyển tiếp; request ký bằng khóa bị thu hồi phải thất bại.
- Không thử tất cả secret một cách mù quáng, không cho client tự chọn thuật toán yếu hơn và không để secret trong log hoặc source code.

Vì `X-Key-Id` nằm trong canonical request, sửa key ID sẽ làm thay đổi dữ liệu ký. Việc liên kết key ID tới danh tính client và trạng thái active/revoked thuộc hệ thống quản lý khóa; xác minh HMAC vẫn phải theo sau bằng **authorization** trên API.

## 7. Các trường hợp kiểm thử quan trọng

Nên có ít nhất một fixture cố định chứa raw HTTP request, body bytes, canonical string và chữ ký kỳ vọng. Chạy cùng fixture ở client, gateway và server để phát hiện sự khác nhau trong chuẩn hóa. Các ca kiểm thử sau đặc biệt quan trọng:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Request nguyên vẹn, secret đúng, timestamp hợp lệ, nonce mới | **Chấp nhận** sau khi kiểm tra quyền nghiệp vụ. |
| Đổi `amount`, thêm dấu cách vào JSON hoặc đổi byte body | **Từ chối** vì body digest và HMAC thay đổi. |
| Đổi `POST` sang `PUT`, thay path, đổi giá trị/thứ tự query | **Từ chối** theo hợp đồng raw target. |
| Đổi `Content-Type`, key ID, timestamp hoặc nonce nhưng giữ chữ ký cũ | **Từ chối** vì field đã được ký. |
| Chữ ký sai, sai hex/độ dài, không tìm thấy key ID, key bị thu hồi | **Từ chối**. |
| Timestamp ngoài cửa sổ; cùng nonce gửi lại hoặc hai node nhận đồng thời | **Từ chối** theo luật chống replay. |
| Reverse proxy đổi percent-encoding, path, query hoặc body sau khi client ký | Xác minh **thất bại**, phải thống nhất lại ranh giới và cách ký. |
| Rotation: key cũ còn trong grace period, key mới đã active | Chỉ chấp nhận chữ ký đúng theo đúng key ID còn hiệu lực. |
| Sửa một header **không có trong hợp đồng ký** | HMAC có thể **vẫn đúng**; rà soát xem header đó có ảnh hưởng bảo mật hay không. |
| Request có header ký trùng lặp, CR/LF hoặc cách biểu diễn mơ hồ | **Từ chối** ở lớp parse/adapter, không đoán một giá trị để ký. |

Ví dụ lỗi thực tế: client ký `/v1/files/a%2Fb` nhưng proxy giải mã thành `/v1/files/a/b` trước khi server lấy path. Nếu server dựng canonical từ path đã giải mã, chữ ký sẽ không khớp. Nếu server xác minh trên path gốc nhưng router xử lý path sau giải mã, cần xem xét **sự lệch giữa tài nguyên được ký và tài nguyên thực thi**. Cả hai trường hợp đều cho thấy integrity phải được kiểm tra trên biểu diễn gắn chặt với quyết định nghiệp vụ.

## 8. Checklist thiết kế và vận hành

- [ ] Công bố hợp đồng ký có phiên bản: thuật toán, encoding, byte LF, thứ tự field, chuẩn hóa URI/header, raw body và biểu diễn chữ ký.
- [ ] Chỉ có một nguồn giá trị cho từng field được ký; từ chối header mơ hồ, input chứa ký tự phân tách hoặc request không thể chuẩn hóa duy nhất.
- [ ] Server tái tính hash trên body **được ứng dụng sử dụng**; khóa, body và target phải được chụp/giữ nhất quán từ lúc verify đến lúc xử lý.
- [ ] Dùng secret ngẫu nhiên đủ mạnh, lưu an toàn, hỗ trợ key ID/rotation/revocation, so sánh MAC bằng hàm an toàn thời gian và luôn dùng HTTPS.
- [ ] Ký timestamp + nonce và xác minh cả cửa sổ thời gian lẫn nonce nguyên tử; giữ lỗi xác thực ở trạng thái *fail closed*.
- [ ] Kiểm thử xuyên qua gateway, reverse proxy và các phiên bản HTTP với fixture byte cố định; giám sát tỷ lệ lỗi chữ ký nhưng không ghi log secret hoặc toàn bộ payload nhạy cảm.
- [ ] Thực hiện authorization và kiểm soát idempotency ở lớp nghiệp vụ ngay cả khi chữ ký đã hợp lệ.

**Điểm cần nhớ:** HMAC chứng minh **các byte đã được chọn để ký** khớp với chữ ký do bên giữ shared secret tạo ra. Mức độ bảo vệ thực tế phụ thuộc chủ yếu vào hợp đồng canonical request, ranh giới giữa proxy và ứng dụng, cách quản lý khóa, kiểm tra chống replay và việc xử lý đúng những dữ liệu vừa được xác minh.
