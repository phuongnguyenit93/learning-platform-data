# Ký không bao phủ body — anti-pattern trong xác thực HTTP request bằng HMAC

## 1. Bối cảnh và mục tiêu

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client và server có chung một **shared secret**. Client tính mã xác thực HMAC trên **canonical request**; server tính lại bằng secret tương ứng rồi so sánh chữ ký. Hợp đồng ký có thể bao gồm phương thức HTTP, URI/path/query, một số header, timestamp, nonce và body. Sau bước xác thực, hệ thống vẫn cần kiểm tra quyền của principal đối với tài nguyên được truy cập.

Một anti-pattern nguy hiểm là **ký method, URI và vài header nhưng không ký body**. Khi đó chữ ký chỉ xác nhận những thành phần đã nằm trong chuỗi ký. Nội dung JSON, form, XML, binary upload hoặc message payload có thể bị thay đổi mà verifier HMAC không phát hiện được, nếu không có một cơ chế bảo vệ tính toàn vẹn khác được thiết kế đúng.

Ví dụ: server nhận một request tạo giao dịch, tính lại HMAC thành công và tưởng rằng cả lệnh chuyển tiền đã được xác thực. Thực tế, nếu chữ ký không bao phủ body, chữ ký **không có ý nghĩa bảo vệ** những trường như số tiền, tài khoản thụ hưởng hoặc tenant nằm trong body.

Sau bài học, người học có thể:

- Mô tả chính xác **điều gì được và không được bảo vệ** khi body vắng mặt trong canonical request.
- Tạo một trường hợp sửa body nhưng vẫn giữ HMAC hợp lệ để kiểm thử lỗ hổng.
- Thiết kế hợp đồng ký ràng buộc **SHA-256 digest của đúng body bytes** vào chữ ký HMAC.
- Phân biệt lỗi chữ ký với lỗi timestamp/nonce, key rotation, gateway transformation và authorization.
- Viết verifier Java 17 và kiểm thử JUnit 5 chứng minh mọi thay đổi body có ý nghĩa phải bị phát hiện.
- Xây dựng checklist xử lý body trên Servlet, WebFlux, proxy/gateway và dịch vụ streaming.

> Phạm vi: Chương **Anti-pattern HMAC** tập trung vào tính toàn vẹn của dữ liệu đã ký. Hợp đồng và header trong ví dụ là minh họa. Không tự áp dụng định dạng canonicalization nếu chưa chốt quy tắc giữa client, gateway và verifier.

## 2. Cơ chế thất bại: chữ ký vẫn đúng nhưng dữ liệu nghiệp vụ đã đổi

### 2.1. Canonical request thiếu body

Giả sử client tạo chữ ký từ bốn dòng sau, nối bằng byte LF:

~~~text
POST
/v1/transfers
1795834800
nonce-a83c
~~~

Chữ ký được tính như sau:

\[
\mathrm{signature} = \mathrm{HMAC\mbox{-}SHA256}(K,\ \mathrm{UTF8}(\mathrm{canonicalRequest}))
\]

Nhưng body **không xuất hiện** trong canonical request:

~~~http
POST /v1/transfers HTTP/1.1
Content-Type: application/json
X-HMAC-Key-Id: merchant-a-k1
X-HMAC-Timestamp: 1795834800
X-HMAC-Nonce: nonce-a83c
X-HMAC-Signature: <valid-signature-for-method-uri-time-nonce>

{"toAccount":"trusted-beneficiary","amount":100000}
~~~

Nếu một đối tượng có thể thay body **trước khi request được verifier chấp nhận lần đầu**, request có thể trở thành:

~~~http
POST /v1/transfers HTTP/1.1
Content-Type: application/json
X-HMAC-Key-Id: merchant-a-k1
X-HMAC-Timestamp: 1795834800
X-HMAC-Nonce: nonce-a83c
X-HMAC-Signature: <same-valid-signature>

{"toAccount":"attacker-beneficiary","amount":900000}
~~~

Method, URI, timestamp và nonce không đổi, nên HMAC trên bốn dòng cũ cũng **không đổi**. Nếu verifier chỉ kiểm tra những trường đó, request vẫn có thể vượt qua xác thực rồi tạo giao dịch khác với ý định ban đầu của client.

Đây là vấn đề **thiếu ràng buộc dữ liệu vào MAC**, không phải một phép tấn công phá thuật toán HMAC-SHA256.

### 2.2. Vì sao các lớp bảo vệ khác chưa đủ?

| Kiểm soát | Có giải quyết việc body không được ký không? | Phân tích |
|---|---|---|
| HTTPS/TLS | Giảm rủi ro sửa dữ liệu trên đường truyền được TLS bảo vệ, **không thay thế** ràng buộc HMAC end-to-end | Có thể có điểm kết thúc TLS ở gateway, service mesh hoặc thành phần trung gian có quyền sửa request |
| Timestamp | Không | Chỉ giới hạn tuổi request; body sửa trên một request còn hạn vẫn có timestamp hợp lệ |
| Nonce | Không | Ngăn dùng lại nonce đã chấp nhận; request bị sửa **trước lần chấp nhận đầu** vẫn có nonce chưa dùng |
| Key rotation | Không | Thay secret không tự thêm body vào canonical request |
| Authorization | Không tự động | Có thể hạn chế thao tác, nhưng không chứng minh client đã ký **đúng payload** handler sử dụng |
| Hash body gửi kèm nhưng **không được ký** | Không đủ | Attacker có thể sửa body và thay hash gửi kèm nếu verifier chỉ so sánh hai giá trị không được MAC bảo vệ |
| Body digest **nằm trong canonical request có HMAC** | Có, trong phạm vi hợp đồng chuẩn | Sửa body bytes làm đổi digest và làm signature không khớp, nếu không có giả định sai ở khâu parse/verify |

Không nên kết luận rằng attacker bất kỳ trên Internet có thể sửa body khi toàn bộ tuyến truyền TLS còn an toàn. Kịch bản tấn công cần một **điểm có khả năng thay request**: một TLS terminator/gateway bị lạm dụng, một service nội bộ không đáng tin, client/proxy bị chiếm quyền hoặc một vùng dữ liệu không được bảo vệ. HMAC end-to-end được dùng để kiểm tra tính toàn vẹn **qua ranh giới tin cậy mà nó được thiết kế bảo vệ**.

## 3. Từ anti-pattern đến hợp đồng ký bao phủ body

### 3.1. Chọn một biểu diễn body ổn định

Một giải pháp phổ biến: client và server cùng tính `SHA-256` trên **đúng mảng byte body đã được thống nhất**, rồi đưa chuỗi hex của digest đó vào canonical request trước khi tính HMAC.

\[
\begin{aligned}
\mathrm{bodyHash} &= \mathrm{hexLower}(\mathrm{SHA256}(\mathrm{bodyBytes}))\\
\mathrm{canonical} &= \mathrm{joinLF}(\mathrm{version},\mathrm{algorithm},\mathrm{keyId},\\
&\qquad\mathrm{method},\mathrm{canonicalTarget},\mathrm{contentType},\\
&\qquad\mathrm{timestamp},\mathrm{nonce},\mathrm{bodyHash})\\
\mathrm{signature} &= \mathrm{HMAC\mbox{-}SHA256}(K,\mathrm{UTF8}(\mathrm{canonical}))
\end{aligned}
\]

SHA-256 ở đây là **digest không có khóa**; tính xác thực đến từ HMAC trên cả canonical request có chứa digest đó. Không coi việc đính kèm `X-Body-SHA256` chưa được ký là tương đương với ký body.

Ví dụ hợp đồng ký `hmac-v1`:

| Thành phần | Quy tắc minh họa |
|---|---|
| Version | Literal `HMAC-REQ-V1`; chỉ chấp nhận version đã đăng ký |
| Algorithm | `HMAC-SHA256`; do credential policy cho phép, không tin header tùy ý |
| Credential | `keyId` ánh xạ đến secret và principal đang active |
| Method | Chữ hoa ASCII, ví dụ `POST` |
| Target | Path và query đã canonical hóa thống nhất theo hợp đồng |
| Content-Type | Giá trị chuẩn hóa cố định mà handler thực sự dùng; trong ví dụ `application/json` |
| Timestamp | Epoch seconds UTC, nguyên vẹn trong chuỗi ký |
| Nonce | Chuỗi đủ ngẫu nhiên và duy nhất theo credential/client |
| Body digest | `lowercase hex SHA-256` của đúng body bytes được verifier đọc |
| HMAC tag | Full HMAC-SHA256 32 byte, encode thành 64 lowercase hex |
| Dấu phân cách | Một byte LF giữa các dòng; không có LF ở cuối |

Chuỗi ký của request có body JSON sẽ có dạng:

~~~text
HMAC-REQ-V1
HMAC-SHA256
merchant-a-k1
POST
/v1/transfers
application/json
1795834800
nonce-a83c
<sha256-hex-of-exact-json-bytes>
~~~

Nếu body thay đổi từ `"amount":100000` thành `"amount":900000`, `bodyHash` thay đổi; chữ ký cũ không còn đúng. Server phải tự tính `SHA-256` từ body thực nhận, so sánh HMAC trên digest **tự tính**, không chỉ tin vào digest client gửi.

### 3.2. Các câu hỏi phải chốt trong contract

- **Body nào được băm?** Byte của HTTP representation tại điểm ký/verify nào? Nếu proxy giải nén `Content-Encoding: gzip`, cả hai phía phải thỏa thuận ký bytes đã nén hay đã giải nén. Không được để signer băm dạng này còn verifier băm dạng khác.
- **Body rỗng được xử lý thế nào?** Hash của mảng byte rỗng là một giá trị xác định. Không dùng phép kiểm tra kiểu "body rỗng thì bỏ dòng digest" vì sẽ mở thêm một cách diễn giải.
- **Có ký media type không?** Body `42` có thể được parser hiểu khác tùy `Content-Type`. Ký content type và các header ảnh hưởng ngữ nghĩa nếu cần bảo vệ toàn vẹn của chúng.
- **Path/query được xử lý ra sao?** Các biến thể percent-encoding, dấu `+`, query keys trùng và sắp xếp tham số phải tuân thủ cùng một hợp đồng; không xử lý theo khả năng đoán của mỗi framework.
- **Có giới hạn kích thước không?** Đọc toàn body để hash cần giới hạn, deadline và biện pháp chống tiêu tốn tài nguyên. Với file rất lớn, cần protocol streaming/chunk signing được đặc tả riêng.
- **Handler nhận cùng bytes không?** Dữ liệu được business code xử lý phải là dữ liệu đã được xác minh, tránh thay đổi sau check (time-of-check/time-of-use).
- **Có thể truy xuất digest cho audit không?** Chỉ lưu digest trong hoàn cảnh được phép; không log secret, full signature, body hoặc canonical request nhạy cảm.

## 4. Những biến thể sai vẫn thường gặp

### 4.1. Ký header nhưng bỏ body vì "body đã có trong HTTP"

~~~java
// ANTI-PATTERN: body hoàn toàn vắng mặt trong dữ liệu ký.
String canonical = method + "\n" + pathAndQuery + "\n"
        + timestamp + "\n" + nonce;
byte[] tag = mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8));
~~~

Bất kỳ body nào được gửi cùng method, path/query, timestamp và nonce đó đều có **cùng tag**, miễn là client/server không có ràng buộc khác đối với body.

### 4.2. Chỉ so body với một hash do client tự gửi

~~~text
X-Body-SHA256: <hex-of-body>
X-HMAC-Signature: HMAC(method + URI + timestamp + nonce)
~~~

Nếu `X-Body-SHA256` không tham gia HMAC hoặc một cơ chế authenticated binding khác, attacker có thể thay **cả body lẫn header hash**. Việc server tính lại hash rồi so với header chưa được ký chỉ chứng minh hai thành phần không đáng tin khớp nhau.

### 4.3. Ký một phần JSON thay vì body handler sử dụng

Ví dụ signer chỉ băm `orderId` còn controller đọc `amount`, `toAccount` và `currency`. Việc ký một tập trường được chọn **có thể** là giao thức hợp lệ nếu toàn bộ những trường còn lại được công khai là không đáng tin và không ảnh hưởng quyết định quan trọng. Nhưng nếu handler dựa vào trường không được ký, đây là một lỗ hổng integrity.

Đặc biệt nguy hiểm khi dùng JSON parser khác nhau: duplicate keys (`{"amount":100,"amount":900}`), thứ tự field, escaping, Unicode normalization, số thập phân hay `null` có thể bị hiểu khác. Cách đơn giản và kiểm soát được nhất là ký **exact bytes của body**, rồi để cùng bytes đó đi vào handler đã được bảo vệ.

### 4.4. Băm body sau khi framework biến đổi

Đôi khi server tính hash từ DTO đã deserialize rồi serialize ngược. Tập byte có thể khác request ban đầu vì thứ tự property, whitespace, escaping, số thập phân và định dạng Unicode; lỗi này có thể gây false reject hoặc nguy hiểm hơn là hai cách diễn giải dữ liệu khác nhau.

Nếu muốn ký **canonical JSON thay vì raw bytes**, phải có chuẩn canonical JSON cụ thể, quy định duplicate field, number representation và Unicode, cùng test vector đa implementation. Không tự dùng `ObjectMapper.writeValueAsString(...)` như một chuẩn mật mã.

### 4.5. Chỉ hash body nếu thấy `Content-Length > 0`

Đây là lối tắt sai khi request dùng streaming/chunked transfer hoặc gateway chuyển đổi encoding. Tầng ứng dụng có thể thấy body thực dù `Content-Length` vắng mặt. Hash phải được tính từ **dữ liệu thực được nhận**, không suy từ một header không đủ tin cậy.

### 4.6. Verify một body rồi xử lý body khác

Nếu security filter đọc body để hash nhưng controller sau đó đọc từ một stream/DTO khác đã bị thay đổi, xác thực không bảo vệ dữ liệu được sử dụng. Cần giữ cùng một biểu diễn đã xác minh hoặc bảo đảm đường xử lý bất biến, nhất là với multipart, upload và các pipeline có nhiều transformation.

## 5. Mẫu Java 17: verifier thực sự ràng buộc body

Mẫu dưới đây minh họa một hợp đồng nhỏ để kiểm chứng nguyên lý. Dữ liệu `body` trong `Request` được clone lúc tạo và mỗi lần truy xuất; kết quả HMAC phụ thuộc body bytes thực sự. Tầng HTTP ở production phải tự kiểm soát duplicate header, raw URI, độ lớn body và các transformation tại gateway.

**`HmacBodyBinding.java`**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Objects;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacBodyBinding {
    private HmacBodyBinding() {}

    private static final int MAX_AGE_SECONDS = 300;
    private static final int FUTURE_SKEW_SECONDS = 60;

    public record Request(
            String keyId,
            String method,
            String canonicalTarget,
            String contentType,
            String timestamp,
            String nonce,
            byte[] body,
            String signatureHex) {

        public Request {
            body = Objects.requireNonNull(body, "body").clone();
        }

        @Override
        public byte[] body() {
            return body.clone();
        }
    }

    public enum Decision {
        ACCEPTED, MALFORMED, TIMESTAMP_INVALID,
        TIMESTAMP_EXPIRED, TIMESTAMP_FUTURE,
        SIGNATURE_INVALID, NONCE_REPLAY
    }

    @FunctionalInterface
    public interface NonceStore {
        // Production: atomic, shared across instances, with suitable TTL.
        boolean claimOnce(String scopedNonce, Instant expiresAt);
    }

    public static final class Verifier {
        private final byte[] secret;
        private final Clock clock;
        private final NonceStore nonceStore;

        public Verifier(byte[] secret, Clock clock, NonceStore nonceStore) {
            this.secret = Objects.requireNonNull(secret).clone();
            this.clock = Objects.requireNonNull(clock);
            this.nonceStore = Objects.requireNonNull(nonceStore);
        }

        public Decision verify(Request request) {
            if (request == null
                    || request.keyId() == null
                    || request.method() == null
                    || request.canonicalTarget() == null
                    || request.contentType() == null
                    || request.timestamp() == null
                    || request.nonce() == null
                    || request.signatureHex() == null
                    || !request.keyId().matches("[A-Za-z0-9_-]{1,64}")
                    || !request.method().matches("[A-Z]+")
                    || !request.canonicalTarget().startsWith("/")
                    || request.canonicalTarget().contains("\n")
                    || request.canonicalTarget().contains("\r")
                    || !request.contentType().equals("application/json")
                    || !request.nonce().matches("[A-Za-z0-9_-]{8,128}")) {
                return Decision.MALFORMED;
            }

            if (!request.timestamp().matches("0|[1-9][0-9]*")) {
                return Decision.TIMESTAMP_INVALID;
            }

            final Instant timestamp;
            try {
                timestamp = Instant.ofEpochSecond(
                        Long.parseLong(request.timestamp()));
            } catch (NumberFormatException | DateTimeException ex) {
                return Decision.TIMESTAMP_INVALID;
            }

            Instant now = clock.instant();
            if (timestamp.isBefore(now.minusSeconds(MAX_AGE_SECONDS))) {
                return Decision.TIMESTAMP_EXPIRED;
            }
            if (timestamp.isAfter(now.plusSeconds(FUTURE_SKEW_SECONDS))) {
                return Decision.TIMESTAMP_FUTURE;
            }

            String hex = request.signatureHex();
            if (hex.length() != 64 || !hex.matches("[0-9a-f]{64}")) {
                return Decision.SIGNATURE_INVALID;
            }

            byte[] supplied;
            try {
                supplied = HexFormat.of().parseHex(hex);
            } catch (IllegalArgumentException ex) {
                return Decision.SIGNATURE_INVALID;
            }

            byte[] expected = hmac(secret, canonicalBytes(request));
            if (!MessageDigest.isEqual(expected, supplied)) {
                // Không được claim nonce trước khi HMAC hợp lệ.
                return Decision.SIGNATURE_INVALID;
            }

            // +1 giây giữ nonce qua cả biên timestamp có độ phân giải giây.
            Instant expiresAt = timestamp.plusSeconds(MAX_AGE_SECONDS + 1L);
            String nonceScope = request.keyId() + ":" + request.nonce();
            return nonceStore.claimOnce(nonceScope, expiresAt)
                    ? Decision.ACCEPTED
                    : Decision.NONCE_REPLAY;
        }
    }

    // Chỉ dành cho fixture unit test; signer client thật được triển khai riêng.
    public static String signForTest(Request request, byte[] secret) {
        return HexFormat.of().formatHex(hmac(secret, canonicalBytes(request)));
    }

    private static byte[] canonicalBytes(Request request) {
        final byte[] digest;
        try {
            digest = MessageDigest.getInstance("SHA-256")
                    .digest(request.body());
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }

        String canonical = String.join("\n",
                "HMAC-REQ-V1",
                "HMAC-SHA256",
                request.keyId(),
                request.method().toUpperCase(Locale.ROOT),
                request.canonicalTarget(),
                request.contentType(),
                request.timestamp(),
                request.nonce(),
                HexFormat.of().formatHex(digest));
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] hmac(byte[] secret, byte[] message) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return mac.doFinal(message);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("HMAC-SHA256 unavailable", ex);
        }
    }
}
~~~

**Các quyết định cần hiểu:**

1. `bodyHash` được server **tự tính từ `request.body()`**, sau đó mới tính HMAC. Attacker không thể thay JSON mà giữ nguyên chữ ký nếu không biết secret và không có lỗi thiết kế khác.
2. `MessageDigest.isEqual` so sánh các byte tag đã giải mã; kiểm tra đúng độ dài 32 byte. Không so sánh HMAC bằng phép so sánh chuỗi thông thường.
3. Timestamp được kiểm tra với một snapshot `Clock`; ký timestamp vào HMAC để ngăn sửa riêng thời gian.
4. Nonce chỉ được claim **sau** khi HMAC khớp. Kho nonce thực tế phải atomic, shared giữa mọi verifier và có TTL đủ cho cửa sổ replay.
5. `keyId` trong mã ví dụ chỉ được dùng để tạo scope nonce. **Production phải tra credential từ server**, xác định keyId có active không, chọn secret/algorithm đúng credential, ràng buộc principal và kiểm tra quyền. Constructor dùng một secret để tập trung vào bài học về body.
6. Copy body ngăn các caller đơn giản sửa mảng byte sau khi tạo `Request`; nếu adapter/handler dùng biểu diễn khác, vẫn phải kiểm tra tính nhất quán ở tầng tích hợp.

**Giới hạn của mã mẫu:** Chưa xử lý HTTP streaming, raw request-target, percent-encoding, header trùng, độ lớn body, query parser, content encoding, key rotation/credential revocation hoặc tác động giao dịch. Các giới hạn đó phải có quy tắc cụ thể ở adapter/gateway và integration tests. Secret thử nghiệm cần được sinh/đưa vào theo chính sách; không hardcode secret production.

## 6. JUnit 5: chứng minh body bị sửa phải làm HMAC sai

Một phép thử hiệu quả cần tạo HMAC **đúng** cho body ban đầu rồi sửa duy nhất body, giữ nguyên method, URI, timestamp, nonce và signature. Nếu verifier trả `SIGNATURE_INVALID`, body đã thực sự được ràng buộc vào chữ ký.

**`HmacBodyBindingTest.java`**

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HashSet;
import java.util.Set;

import org.junit.jupiter.api.Test;

class HmacBodyBindingTest {
    private static final Clock FIXED_CLOCK = Clock.fixed(
            Instant.parse("2026-11-28T03:00:00Z"), ZoneOffset.UTC);

    private static final byte[] SECRET =
            "test-only-secret-with-32-byte-minimum-entropy-placeholder"
                    .getBytes(StandardCharsets.UTF_8);

    private final Set<String> usedNonces = new HashSet<>();

    private final HmacBodyBinding.Verifier verifier =
            new HmacBodyBinding.Verifier(
                    SECRET, FIXED_CLOCK,
                    (nonce, expiresAt) -> usedNonces.add(nonce));

    private static HmacBodyBinding.Request unsigned(
            String json, String nonce) {
        return new HmacBodyBinding.Request(
                "merchant-a-k1",
                "POST",
                "/v1/transfers",
                "application/json",
                Long.toString(FIXED_CLOCK.instant().getEpochSecond()),
                nonce,
                json.getBytes(StandardCharsets.UTF_8),
                "");
    }

    private static HmacBodyBinding.Request withSignature(
            HmacBodyBinding.Request request, String signature) {
        return new HmacBodyBinding.Request(
                request.keyId(),
                request.method(),
                request.canonicalTarget(),
                request.contentType(),
                request.timestamp(),
                request.nonce(),
                request.body(),
                signature);
    }

    private static HmacBodyBinding.Request withBody(
            HmacBodyBinding.Request request, String newJson) {
        return new HmacBodyBinding.Request(
                request.keyId(),
                request.method(),
                request.canonicalTarget(),
                request.contentType(),
                request.timestamp(),
                request.nonce(),
                newJson.getBytes(StandardCharsets.UTF_8),
                request.signatureHex());
    }

    private static HmacBodyBinding.Request signed(
            String json, String nonce) {
        var request = unsigned(json, nonce);
        return withSignature(
                request, HmacBodyBinding.signForTest(request, SECRET));
    }

    @Test
    void acceptsOriginalSignedBody() {
        var request = signed(
                "{\"amount\":100000,\"toAccount\":\"trusted\"}",
                "nonce-0001");
        assertEquals(HmacBodyBinding.Decision.ACCEPTED,
                verifier.verify(request));
    }

    @Test
    void changingAmountButKeepingSignatureIsRejected() {
        var original = signed(
                "{\"amount\":100000,\"toAccount\":\"trusted\"}",
                "nonce-0002");
        var tampered = withBody(original,
                "{\"amount\":900000,\"toAccount\":\"trusted\"}");

        assertEquals(HmacBodyBinding.Decision.SIGNATURE_INVALID,
                verifier.verify(tampered));
        assertTrue(usedNonces.isEmpty(), "MAC failure must not claim nonce");
    }

    @Test
    void changingBeneficiaryButKeepingSignatureIsRejected() {
        var original = signed(
                "{\"amount\":100000,\"toAccount\":\"trusted\"}",
                "nonce-0003");
        var tampered = withBody(original,
                "{\"amount\":100000,\"toAccount\":\"attacker\"}");

        assertEquals(HmacBodyBinding.Decision.SIGNATURE_INVALID,
                verifier.verify(tampered));
    }

    @Test
    void evenWhitespaceChangeCannotReuseRawBodySignature() {
        var original = signed("{\"amount\":100000}", "nonce-0004");
        var changed = withBody(original, "{ \"amount\":100000 }");

        assertNotEquals(
                HmacBodyBinding.signForTest(
                        unsigned("{\"amount\":100000}", "nonce-0004"), SECRET),
                HmacBodyBinding.signForTest(
                        unsigned("{ \"amount\":100000 }", "nonce-0004"), SECRET));
        assertEquals(HmacBodyBinding.Decision.SIGNATURE_INVALID,
                verifier.verify(changed));
    }

    @Test
    void sameBodyAndSameNonceCannotBeAcceptedTwice() {
        var request = signed("{\"amount\":100000}", "nonce-0005");

        assertEquals(HmacBodyBinding.Decision.ACCEPTED,
                verifier.verify(request));
        assertEquals(HmacBodyBinding.Decision.NONCE_REPLAY,
                verifier.verify(request));
    }

    @Test
    void expiredTimestampIsRejectedEvenForValidBodyMac() {
        var unsigned = new HmacBodyBinding.Request(
                "merchant-a-k1", "POST", "/v1/transfers",
                "application/json",
                Long.toString(FIXED_CLOCK.instant()
                        .minusSeconds(301).getEpochSecond()),
                "nonce-0006",
                "{\"amount\":100000}".getBytes(StandardCharsets.UTF_8),
                "");
        var expired = withSignature(
                unsigned, HmacBodyBinding.signForTest(unsigned, SECRET));

        assertEquals(HmacBodyBinding.Decision.TIMESTAMP_EXPIRED,
                verifier.verify(expired));
    }

    @Test
    void changingContentTypeWithOldSignatureIsRejected() {
        var request = signed("{\"amount\":100000}", "nonce-0007");
        var changed = new HmacBodyBinding.Request(
                request.keyId(), request.method(), request.canonicalTarget(),
                "text/plain", request.timestamp(), request.nonce(),
                request.body(), request.signatureHex());
        assertEquals(HmacBodyBinding.Decision.MALFORMED,
                verifier.verify(changed));
    }

    @Test
    void emptyBodyAlsoHasDeterministicSignedDigest() {
        var request = signed("", "nonce-0008");
        assertEquals(HmacBodyBinding.Decision.ACCEPTED,
                verifier.verify(request));
    }
}
~~~

**Điểm quan trọng khi đọc test:**

- Test sửa số tiền hoặc người thụ hưởng sử dụng **chữ ký cũ đúng cho body gốc**. Chúng kiểm tra trực tiếp anti-pattern này.
- Test thay whitespace không khẳng định nghiệp vụ JSON thay đổi. Nó chứng minh hợp đồng **ký raw bytes**: byte khác thì digest khác, dù kết quả JSON parse có thể tương đương.
- Test timestamp cũ **ký lại bằng secret thử nghiệm** để kiểm tra freshness riêng; timestamp không cứu được một body bị sửa.
- Nonce replay được test riêng vì anti-replay và body integrity là hai kiểm soát khác nhau.
- Test `Content-Type` minh họa contract fail-closed. Với hệ thống hỗ trợ nhiều media type, phải cho phép có kiểm soát và bind loại nội dung phù hợp vào chữ ký.

### 6.1. Negative test cho implementation sai

Có thể viết một test để **chứng minh lỗ hổng của cách ký cũ** trước khi sửa. Hàm dưới đây cố ý chỉ ký method, URI, timestamp, nonce:

~~~java
static String vulnerableCanonical(HmacBodyBinding.Request r) {
    return String.join("\n",
            r.method(), r.canonicalTarget(), r.timestamp(), r.nonce());
}

// Với hai Request chỉ khác body:
// vulnerableCanonical(original).equals(vulnerableCanonical(tampered)) == true
// nên HMAC trên chuỗi này cũng giống hệt nhau nếu dùng cùng key.
~~~

Test hồi quy cần xác minh code production **không còn sử dụng** format này; các API nhận body nhạy cảm phải dùng canonical request chứa body digest được ký. Nếu có client cũ còn dùng format thiếu body, không được giữ fallback không giới hạn; phải version hóa hợp đồng và có kế hoạch migration/thu hồi.

## 7. Tích hợp an toàn với HTTP framework và gateway

### 7.1. Servlet/Spring MVC

Trong Servlet, body thường là stream chỉ đọc một lần. Một cách dễ sai là tạo `ContentCachingRequestWrapper` rồi gọi `getContentAsByteArray()` **trước khi bất kỳ ai đọc stream**: wrapper này cache dữ liệu **khi nó được đọc**, nên kết quả có thể rỗng. Nếu verifier dùng hash của chuỗi rỗng còn controller đọc body thật sau đó, ràng buộc integrity không còn đúng.

Thiết kế đáng tin phải:

1. Đọc body đúng một lần ở trust boundary được chọn, với giới hạn kích thước, timeout và xử lý lỗi đầy đủ.
2. Lưu **đúng bytes đã đọc** vào cấu trúc immutable/bounded hoặc nguồn lưu tạm được bảo vệ.
3. Tính digest trên bytes đó và xác minh HMAC **trước khi** controller gây side effect.
4. Cấp lại cùng bytes cho handler bằng wrapper có khả năng replay body, hoặc xử lý handler trực tiếp trên buffered data đã xác minh.
5. Từ chối request nếu body bị cắt do vượt giới hạn, stream lỗi, mã hóa không hợp đồng hoặc không thể đọc đầy đủ.
6. Không âm thầm coi body chưa đọc là body rỗng.

Đối với body quá lớn, đừng buffer vô hạn vào RAM; chọn giới hạn rõ ràng hoặc protocol streaming được thiết kế riêng. Nếu dùng temporary file, phải quản lý lifetime, quyền truy cập và dọn dẹp an toàn.

### 7.2. Spring WebFlux và reactive body

Trong WebFlux, request body thường là luồng `Flux<DataBuffer>`. Việc subscribe để hash rồi để controller subscribe thêm lần nữa có thể dẫn đến body rỗng, body đã tiêu thụ hoặc xử lý không xác định. Nếu cần verify trước handler, phải thiết kế cơ chế **buffer/decorate** request với giới hạn bộ nhớ và lifecycle rõ ràng, hoặc cơ chế streaming authentication phù hợp. Cần xử lý reference-counted buffer và hủy subscription đúng cách; không giữ raw body trong log.

Đừng thực thi business side effect khi signature còn chưa được xác minh đầy đủ. Với streaming, nếu xử lý dữ liệu theo chunk trước khi xác minh tag cuối, lỗi MAC phát hiện muộn có thể không đảo ngược được side effect.

### 7.3. Proxy, gateway và content encoding

| Tình huống | Triệu chứng | Yêu cầu xử lý |
|---|---|---|
| Gateway giải nén gzip | Client ký compressed bytes, server hash decompressed bytes | Chốt điểm ký/verify hoặc giữ nguyên representation |
| Gateway parse rồi serialize JSON | Body bytes thay đổi dù dữ liệu tương đương | Tránh rewrite đã ký hoặc thống nhất protocol canonical JSON |
| Multipart/form-data | Boundary, metadata, line endings thay đổi | Xác định byte representation và signed headers |
| Chunked transfer | Không có `Content-Length` | Hash body bytes thực, không suy từ header |
| Query/path rewrite | HMAC fail dù body không đổi | Tách lỗi canonical URI khỏi body digest |
| Reverse proxy thay `Content-Type` | Handler hiểu dữ liệu khác | Bind content type hoặc từ chối thay đổi ngoài contract |
| Gateway có quyền sửa body | HMAC chỉ bảo vệ phần verifier kiểm tra sau rewrite | Đặt điểm xác minh/trust boundary phù hợp và test end-to-end |

Không ký hop-by-hop headers như `Transfer-Encoding` một cách tùy tiện nếu gateway được phép thay đổi chúng. **Body representation** được bảo vệ phải được xác định theo một hợp đồng độc lập với cách HTTP vận chuyển từng chunk.

### 7.4. Body lớn, upload và streaming

Với upload lớn, có thể thiết kế ký digest cho toàn bộ payload theo luồng rồi chỉ thực hiện hành động khi digest/HMAC được xác minh xong. Nếu cần xử lý từng chunk trước khi có toàn bộ dữ liệu, phải có protocol chunk signing có thứ tự, chống cắt ngắn, xác định final chunk và semantics rollback/idempotency. Không dùng đoạn code `byte[] body` trên cho upload không giới hạn kích thước.

## 8. Ma trận kiểm thử tích hợp và security regression

| ID | Dữ liệu kiểm thử | Kết quả mong đợi | Điều được chứng minh |
|---|---|---|---|
| B01 | Body gốc + HMAC đúng + ts/nonce mới | Chấp nhận xác thực | Positive baseline |
| B02 | Sửa `amount` sau ký, giữ HMAC cũ | Reject signature | Body integrity |
| B03 | Sửa `toAccount` sau ký | Reject signature | Chống thay người thụ hưởng |
| B04 | Đổi khoảng trắng/thứ tự JSON field, giữ signature cũ | Reject với contract ký raw bytes | Không có rewrite ngầm |
| B05 | Body rỗng được ký đúng; sau đó thêm một byte | Reject signature | Không bỏ qua empty body |
| B06 | Body có UTF-8 và Unicode, sửa một byte | Reject signature hoặc reject encoding | Byte-level integrity |
| B07 | Header `Content-Type` bị sửa ngoài contract | Reject signature hoặc reject contract | Metadata binding |
| B08 | Query/path bị sửa sau ký | Reject signature | Canonical request vẫn bảo vệ URI |
| B09 | Signature đúng nhưng ts `now - 301s` | Reject expired | Freshness tách biệt |
| B10 | Signature đúng, nonce đã claim trước đó | Reject replay | Atomic nonce |
| B11 | Key đã revoke nhưng ký body mới đúng | Reject credential | Key lifecycle |
| B12 | HMAC đúng, caller khác tenant truy cập resource | Deny authorization | Xác thực khác phân quyền |
| B13 | Gateway giải nén hoặc reserialize body ngoài contract | Reject hoặc áp dụng contract được thống nhất | End-to-end invariance |
| B14 | Parser nhận duplicate JSON fields | Theo policy reject hoặc xử lý duy nhất đã định | Không nhập nhằng nghiệp vụ |
| B15 | Body quá lớn, bị cắt hoặc stream lỗi | Reject, không chạy handler | Giới hạn tài nguyên |

**Không chỉ nhìn HTTP status.** Trong môi trường test có thể ghi reason nội bộ: `body_digest_mismatch`, `signature_invalid`, `timestamp_expired`, `nonce_replay`, `credential_revoked` hoặc `authorization_denied`. Với body digest được tính trong canonical request, trường hợp B02/B03 thường biểu hiện là `signature_invalid`; không bắt buộc phải có mã lỗi riêng cho body.

### 8.1. Phân biệt kiểm thử toàn vẹn và replay

Nếu lấy request đã được server chấp nhận rồi gửi lại với body khác, nó có thể bị từ chối vì **nonce replay** ngay cả khi verifier không bao phủ body. Đó là một test không đủ mạnh để chứng minh body integrity.

Để kiểm tra B02/B03 đúng, mỗi ca nên tạo request **mới với nonce chưa dùng**, signer ký body gốc, sau đó bộ test sửa body **trước lần gửi đầu** và giữ chữ ký cũ. Nếu HMAC verifier thiếu body binding, request có thể được chấp nhận. Với verifier đúng, nó phải fail signature.

Tương tự, nếu kiểm thử key revocation với timestamp quá hạn, kết quả expired không chứng minh revoke có hiệu lực. Mỗi kiểm thử cần kiểm soát biến độc lập.

### 8.2. Kiểm thử đa instance/gateway

Chạy cùng test qua client → gateway → verifier → controller, ghi fingerprint của dữ liệu test do từng lớp nhận. Đặc biệt kiểm tra rằng bytes đã được băm là bytes business handler dùng hoặc được giải mã từ chính bytes đó. Với nhiều instance, nonce claim phải có tính atomic xuyên instance; thay đổi body không được làm hệ thống lách qua key/algorithm/timestamp policy.

## 9. Khắc phục khi phát hiện hệ thống đang ký thiếu body

Nếu phát hiện endpoint có body nhạy cảm mà HMAC không bao phủ body, cần đánh giá mức độ ảnh hưởng theo quyền caller, ranh giới tin cậy và những thành phần có khả năng sửa payload.

1. **Khoanh vùng:** xác định endpoint, client, protocol version và loại body chưa được ký. Phân biệt endpoint read-only không có body với endpoint tạo side effect.
2. **Giảm rủi ro tức thời:** hạn chế endpoint nguy hiểm, kiểm soát gateway có quyền sửa body, áp dụng authorization/transaction hold phù hợp. Không tự cho rằng TLS bù đắp đầy đủ cho một yêu cầu integrity end-to-end.
3. **Thiết kế phiên bản ký mới:** thêm digest của đúng body bytes và metadata cần bảo vệ vào canonical request. Gắn contract version với key/credential policy để tránh fallback sang bản yếu.
4. **Cập nhật signer và verifier:** phát hành golden vectors, ký toàn bộ body representation, xác minh trước xử lý nghiệp vụ, giới hạn kích thước và quản lý replay.
5. **Chạy regression/security tests:** B01–B15, có client/verifier độc lập và test end-to-end qua gateway.
6. **Di chuyển client:** theo dõi sử dụng version cũ, có thời hạn migration; sau hạn, **từ chối** định dạng ký thiếu body ở các endpoint được bảo vệ. Không tạo lựa chọn "thử format cũ nếu format mới fail".
7. **Điều tra hậu quả nếu có bằng chứng khai thác:** truy request ID, keyId, dữ liệu giao dịch/ledger và thời điểm; bảo toàn chứng cứ theo incident process.
8. **Duy trì kiểm soát:** thêm test vào CI, review các endpoint mới và theo dõi mismatch tăng sau thay đổi proxy hoặc payload serialization.

Nếu secret cũng bị lộ hoặc client signer bị chiếm quyền, chỉ thêm body digest không đủ; attacker có secret vẫn có thể ký một body độc hại. Khi đó cần **revoke/rotate credential**, khôi phục client và điều tra sự cố riêng.

## 10. Checklist review và bài thực hành

- [ ] Contract chỉ rõ canonical request bao phủ body bytes hoặc digest **được HMAC ràng buộc**.
- [ ] Verifier tự băm body thực nhận và handler sử dụng đúng dữ liệu đã xác minh.
- [ ] Body rỗng, body lớn, upload và encoding có quy tắc rõ; không hash dựa vào `Content-Length`.
- [ ] `Content-Type` và các metadata quyết định cách hiểu body được kiểm soát/đưa vào hợp đồng ký.
- [ ] Không dùng JSON parse-serialize ngầm như một cách canonicalization mật mã.
- [ ] Gateway và framework không làm lệch representation đã ký ngoài hợp đồng.
- [ ] Test sửa số tiền/tài khoản **trước lần gửi đầu** bị từ chối dù nonce/timestamp còn hợp lệ.
- [ ] Các test signature, timestamp, nonce, key revocation và authorization được tách biệt, biết rõ nguyên nhân reject.
- [ ] Nonce store atomic xuyên instance; secret/key rotation không biến bản ký cũ thành fallback không giới hạn.
- [ ] Log/metric không tiết lộ shared secret, body nhạy cảm hoặc signature đầy đủ.

**Bài thực hành:** Cho một client ký `POST /v1/transfers` trên method, URI, timestamp và nonce, nhưng bỏ body. Hãy viết một test tạo chữ ký cho body `{"amount":100000,"toAccount":"trusted"}`, sau đó thay body thành `{"amount":900000,"toAccount":"attacker"}` với cùng chữ ký và nonce **chưa từng gửi**. Chứng minh verifier cũ có thể chấp nhận request sửa đổi. Tiếp theo, bổ sung SHA-256 digest của exact body bytes vào canonical request; tạo golden vector và viết test để chứng minh request cũ chỉ được nhận khi body **không bị sửa**. Cuối cùng, thử lại qua gateway có khả năng nén/giải nén body và xác nhận verifier/handler dùng cùng representation theo hợp đồng.
