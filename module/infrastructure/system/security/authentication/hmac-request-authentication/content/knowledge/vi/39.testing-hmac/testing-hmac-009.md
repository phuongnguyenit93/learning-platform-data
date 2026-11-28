# Expired timestamp test — kiểm thử timestamp hết hạn trong xác thực HMAC

## 1. Mục tiêu và bối cảnh

Trong cơ chế **xác thực HTTP request bằng HMAC**, client và server cùng biết một shared secret. Client tạo chữ ký từ một **canonical request** theo hợp đồng ký đã thống nhất; server tính lại chữ ký và so sánh. Hợp đồng có thể bao gồm HTTP method, URI (path và query), một số header, dấu thời gian (timestamp), nonce và hash của body. Chữ ký hợp lệ chứng minh rằng request được tạo bởi bên có secret tương ứng và các thành phần đã ký không bị thay đổi.

Tuy nhiên, một request đã được ký đúng **vẫn có thể bị kẻ tấn công gửi lại** sau khi bị ghi nhận trên đường truyền, log hoặc hệ thống trung gian. `Expired timestamp test` kiểm tra rằng server từ chối một request có timestamp quá cũ, **kể cả khi chữ ký HMAC hoàn toàn hợp lệ**.

Sau bài này, người học có thể:

- Xác định rõ cửa sổ chấp nhận timestamp và điểm biên hết hạn.
- Tạo test sử dụng đồng hồ cố định, tái hiện được mà không dùng `sleep`.
- Phân biệt lỗi timestamp hết hạn, timestamp không hợp lệ, chữ ký sai và nonce bị dùng lại.
- Thiết kế thêm test cho proxy/gateway, lệch đồng hồ, key rotation và replay trong hệ thống phân tán.

> **Phạm vi:** Đây là ví dụ cho module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Header và thứ tự trường trong canonical request dưới đây là **hợp đồng minh họa**. Khi triển khai, hai đầu phải tuân thủ đúng một hợp đồng ký đã phiên bản hóa; tuyệt đối không tự thay đổi quy tắc canonicalization giữa client và server.

## 2. Timestamp hết hạn nghĩa là gì?

Giả sử giao thức dùng `X-HMAC-Timestamp` là số **giây Unix epoch** (UTC), mỗi request có `X-HMAC-Nonce` riêng và chính giá trị timestamp đó được đưa vào chuỗi ký.

Một request minh họa:

~~~http
POST /v1/transfers?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-HMAC-Timestamp: <unix-epoch-seconds>
X-HMAC-Nonce: 8f7d2c4a9b10
X-HMAC-Signature: <64-hex-characters>

{"amount":1000}
~~~

Hợp đồng canonical hóa **đơn giản hóa cho bài học** là nối các dòng theo đúng thứ tự sau bằng ký tự LF (`\n`), dùng UTF-8:

~~~text
POST
/v1/transfers?currency=VND
<raw-X-HMAC-Timestamp>
<raw-X-HMAC-Nonce>
<lowercase-hex-SHA256-of-body-bytes>
~~~

Ở đây method được chuyển thành chữ hoa; path/query lấy theo định dạng đã thỏa thuận; body hash tính trên **đúng các byte thực sự được ký**. Vì timestamp và nonce nằm trong canonical request, thay timestamp hoặc nonce trên một request cũ mà không tính lại HMAC sẽ làm chữ ký sai.

Đặt:

- `now`: thời điểm hiện tại phía verifier, lấy **một lần** từ đồng hồ server.
- `ts`: timestamp đã parse thành `Instant`.
- `maxAge = 300 s`: tuổi tối đa của request (5 phút).
- `futureSkew = 60 s`: mức cho phép đồng hồ client chạy nhanh hơn server.

Với chính sách của ví dụ, server chỉ chấp nhận timestamp thỏa mãn:

\[
\boxed{now - 300s \leq ts \leq now + 60s}
\]

Vì vậy, **hết hạn** khi `ts < now - 300s`. Timestamp tương lai quá xa (`ts > now + 60s`) cũng bị từ chối nhưng là một lỗi riêng, không phải "expired". Tại đúng các ranh giới `now - 300s` và `now + 60s`, request còn nằm trong cửa sổ hợp lệ. Đây là lựa chọn *inclusive boundary* của ví dụ; hệ thống dùng phép so sánh khác phải ghi rõ hợp đồng và test tương ứng.

Timestamp là một cơ chế giới hạn thời gian replay; **không thay thế nonce**. Một request có timestamp mới, chữ ký đúng vẫn có thể bị gửi lại nhiều lần **trong 300 giây hợp lệ**. Hệ thống cần đăng ký nonce duy nhất bằng thao tác atomic (ví dụ `SET ... NX` trên Redis với TTL phù hợp) sau khi xác minh thành công. Khi dùng `keyId`, định danh client hoặc tenant, khóa nonce thường phải gắn với phạm vi danh tính thích hợp; tránh để nonce của hai client khác nhau xung đột.

### Tại sao cần kiểm thử điểm biên?

Giả sử đồng hồ server cố định tại `2026-11-28T03:00:00Z`:

| Timestamp ký trên request | Khoảng cách so với `now` | Kết quả về thời gian |
|---|---:|---|
| `now - 301 s` | Cũ hơn 5 phút 1 giây | **REJECT: EXPIRED** |
| `now - 300 s` | Đúng 5 phút | **ACCEPT** nếu các kiểm tra khác đạt |
| `now - 299 s` | Cũ 4 phút 59 giây | **ACCEPT** nếu các kiểm tra khác đạt |
| `now` | Không lệch | **ACCEPT** nếu các kiểm tra khác đạt |
| `now + 60 s` | Nhanh 1 phút | **ACCEPT** nếu các kiểm tra khác đạt |
| `now + 61 s` | Nhanh quá mức | **REJECT: FUTURE** |

Không dùng thời gian thực và đợi 301 giây để tạo tình huống expired: test như vậy chậm, dễ sai theo tải CI và có thể thất bại ở ranh giới milli/microsecond. Dùng `Clock.fixed(...)` hoặc một `Clock` điều khiển được để tính cả `now` lẫn timestamp kiểm thử.

## 3. Thiết kế các kịch bản test

Một phép thử expired đúng nghĩa cần **ký request với timestamp cũ bằng key đúng**, sau đó xác minh trên server có đồng hồ hiện tại cố định. Nếu chỉ sửa header timestamp của một request đã ký, chữ ký sẽ sai; test chỉ chứng minh chống sửa đổi dữ liệu, chưa kiểm chứng chính sách hết hạn.

| Mã | Dữ liệu và thao tác | Kết quả cần xác minh |
|---|---|---|
| E01 | HMAC hợp lệ, `ts = now - 301 s` | Từ chối vì `TIMESTAMP_EXPIRED`; không ghi nonce |
| E02 | HMAC hợp lệ, `ts = now - 300 s` | Chấp nhận ở biên dưới |
| E03 | HMAC hợp lệ, `ts = now - 299 s` | Chấp nhận trong cửa sổ |
| E04 | HMAC hợp lệ, `ts = now + 60 s` | Chấp nhận ở biên trên |
| E05 | HMAC hợp lệ, `ts = now + 61 s` | Từ chối vì `TIMESTAMP_FUTURE` |
| E06 | Thiếu timestamp, chứa khoảng trắng, chữ, thập phân hoặc số vượt giới hạn `long` | Từ chối khi parse/validate, không văng lỗi 500 |
| E07 | Đổi timestamp cũ thành timestamp mới mà giữ nguyên signature | Từ chối vì `SIGNATURE_INVALID` |
| E08 | Gửi lại hai lần một request còn thời hạn, signature đúng và nonce trùng | Lần đầu được nhận, lần sau `NONCE_REPLAY` |
| E09 | HMAC hợp lệ nhưng method, path/query hoặc body bị chỉnh sửa trên đường truyền | Từ chối vì signature không khớp |
| E10 | Request hết hạn được ký bằng key cũ vẫn còn cho phép trong giai đoạn rotation | Vẫn từ chối vì hết hạn |
| E11 | Gửi request qua proxy/gateway có rewrite URI, query hoặc body | Hai bên canonical hóa giống nhau; không phát sinh false expired/signature invalid |

Các kết quả nội bộ trong bảng dùng để phân loại test. API công khai thường chỉ trả lỗi xác thực chung (chẳng hạn HTTP 401, mã lỗi phù hợp với hợp đồng), không tiết lộ secret, chữ ký kỳ vọng hoặc thông tin nhạy cảm. **HTTP 403** dành cho tình huống đã xác thực nhưng không đủ quyền, tùy chính sách API.

## 4. Cài đặt tham chiếu bằng Java 17+

Ví dụ sau giữ phần xác thực đủ nhỏ để thấy rõ thứ tự: parse timestamp → kiểm tra cửa sổ thời gian → xác minh HMAC → đăng ký nonce. `NonceStore` là một abstraction; bản lưu trữ thực tế phải hỗ trợ thao tác atomic và TTL xuyên nhiều instance. Ví dụ dùng một key để làm rõ bài kiểm thử; hệ thống nhiều key có thể tra cứu secret theo `keyId` trước khi kiểm HMAC.

**`HmacTimestampExample.java`**

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

public final class HmacTimestampExample {
    private HmacTimestampExample() {}

    public static final long MAX_AGE_SECONDS = 300;
    public static final long FUTURE_SKEW_SECONDS = 60;

    public record Request(
            String method,
            String pathAndQuery,
            String timestamp,
            String nonce,
            byte[] body,
            String signatureHex) {}

    public enum Decision {
        ACCEPTED,
        TIMESTAMP_MISSING,
        TIMESTAMP_INVALID,
        TIMESTAMP_EXPIRED,
        TIMESTAMP_FUTURE,
        SIGNATURE_INVALID,
        NONCE_REPLAY
    }

    @FunctionalInterface
    public interface NonceStore {
        // Phải atomic trong hệ thống thật; expiresAt là thời điểm loại bỏ nonce.
        boolean registerOnce(String nonce, Instant expiresAt);
    }

    public static final class Verifier {
        private final Clock clock;
        private final byte[] secret;
        private final NonceStore nonceStore;

        public Verifier(Clock clock, byte[] secret, NonceStore nonceStore) {
            this.clock = Objects.requireNonNull(clock);
            this.secret = Objects.requireNonNull(secret).clone();
            this.nonceStore = Objects.requireNonNull(nonceStore);
        }

        public Decision verify(Request request) {
            Objects.requireNonNull(request);
            String rawTimestamp = request.timestamp();
            if (rawTimestamp == null || rawTimestamp.isBlank()) {
                return Decision.TIMESTAMP_MISSING;
            }

            // Hợp đồng: epoch seconds không âm, số nguyên dạng thập phân.
            if (!rawTimestamp.matches("0|[1-9][0-9]*")) {
                return Decision.TIMESTAMP_INVALID;
            }

            final Instant timestamp;
            try {
                timestamp = Instant.ofEpochSecond(Long.parseLong(rawTimestamp));
            } catch (NumberFormatException | DateTimeException ex) {
                return Decision.TIMESTAMP_INVALID;
            }

            Instant now = clock.instant(); // Chụp thời điểm một lần.
            if (timestamp.isBefore(now.minusSeconds(MAX_AGE_SECONDS))) {
                return Decision.TIMESTAMP_EXPIRED;
            }
            if (timestamp.isAfter(now.plusSeconds(FUTURE_SKEW_SECONDS))) {
                return Decision.TIMESTAMP_FUTURE;
            }

            if (request.method() == null
                    || request.pathAndQuery() == null
                    || request.nonce() == null
                    || request.nonce().isBlank()
                    || request.body() == null
                    || request.signatureHex() == null) {
                return Decision.SIGNATURE_INVALID;
            }

            final byte[] suppliedSignature;
            try {
                suppliedSignature = HexFormat.of().parseHex(request.signatureHex());
            } catch (IllegalArgumentException ex) {
                return Decision.SIGNATURE_INVALID;
            }

            byte[] expectedSignature = signBytes(secret, request);
            if (suppliedSignature.length != 32
                    || !MessageDigest.isEqual(expectedSignature, suppliedSignature)) {
                return Decision.SIGNATURE_INVALID;
            }

            // Cửa sổ dưới lấy dấu <=, nên giữ nonce qua hết giây biên.
            Instant expiresAt = timestamp.plusSeconds(MAX_AGE_SECONDS + 1);
            return nonceStore.registerOnce(request.nonce(), expiresAt)
                    ? Decision.ACCEPTED
                    : Decision.NONCE_REPLAY;
        }
    }

    // Tiện ích tạo chữ ký ở phía client/test, cùng hợp đồng canonical minh họa.
    public static String signHex(byte[] secret, Request request) {
        return HexFormat.of().formatHex(signBytes(secret, request));
    }

    private static byte[] signBytes(byte[] secret, Request request) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return mac.doFinal(canonicalBytes(request));
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("HMAC-SHA256 unavailable", ex);
        }
    }

    private static byte[] canonicalBytes(Request request) {
        try {
            String bodyHash = HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(request.body()));
            String canonical = String.join("\n",
                    request.method().toUpperCase(Locale.ROOT),
                    request.pathAndQuery(),
                    request.timestamp(),
                    request.nonce(),
                    bodyHash);
            return canonical.getBytes(StandardCharsets.UTF_8);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

**Giải thích các quyết định trong ví dụ:**

1. `Clock` được inject nên test kiểm soát `now` chính xác; dùng `Instant` để tránh nhầm UTC với múi giờ cục bộ.
2. Kiểm tra định dạng trước `Long.parseLong`; số quá dài được chuyển thành `TIMESTAMP_INVALID` thay vì làm hỏng luồng xử lý.
3. Dùng `isBefore` / `isAfter` để thể hiện rõ tính bao gồm của hai điểm biên.
4. Không gọi `registerOnce` cho request đã hết hạn hoặc chữ ký sai. Nếu ghi nonce trước rồi request bị từ chối, kẻ tấn công có thể chiếm nonce và làm request hợp lệ bị từ chối về sau.
5. `MessageDigest.isEqual` so sánh byte chữ ký; không so sánh chữ ký bằng `String.equals`. HMAC phải dùng key theo định danh client đã được xác thực và giải pháp quản lý/rotation key phù hợp.
6. `expiresAt = ts + 301 s` giữ nonce vượt qua ranh giới dưới cho phép `ts = now - 300 s` khi timestamp ở độ phân giải giây. TTL và chính sách làm tròn của kho nonce thực tế cần được kiểm tra bằng integration test.

> **Giới hạn có chủ ý của mẫu học tập:** `Request` nhận chuỗi path/query đã canonical hóa và mảng body bytes đã chốt. Triển khai production phải quy định chặt encoding URI, query parameters lặp, duplicate headers, newline/control characters, giới hạn kích thước header/body, canonicalization theo proxy, version hợp đồng ký và key lookup. Client và server nên có test vector cố định được tạo độc lập, tránh cùng dùng một helper sai ở cả hai phía.

## 5. JUnit 5: kiểm thử expired timestamp có thể tái hiện

**`HmacTimestampExampleTest.java`**

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HashSet;
import java.util.Set;

import org.junit.jupiter.api.Test;

class HmacTimestampExampleTest {
    private static final Clock FIXED_CLOCK = Clock.fixed(
            Instant.parse("2026-11-28T03:00:00Z"), ZoneOffset.UTC);
    private static final byte[] SECRET =
            "test-only-shared-secret".getBytes(StandardCharsets.UTF_8);

    // Stub dành riêng cho unit test: mỗi test có một Set mới.
    private final Set<String> seenNonces = new HashSet<>();
    private final HmacTimestampExample.Verifier verifier =
            new HmacTimestampExample.Verifier(
                    FIXED_CLOCK, SECRET,
                    (nonce, expiresAt) -> seenNonces.add(nonce));

    private HmacTimestampExample.Request signedAt(Instant timestamp, String nonce) {
        HmacTimestampExample.Request unsigned = new HmacTimestampExample.Request(
                "POST",
                "/v1/transfers?currency=VND",
                Long.toString(timestamp.getEpochSecond()),
                nonce,
                "{\"amount\":1000}".getBytes(StandardCharsets.UTF_8),
                "");
        return new HmacTimestampExample.Request(
                unsigned.method(),
                unsigned.pathAndQuery(),
                unsigned.timestamp(),
                unsigned.nonce(),
                unsigned.body(),
                HmacTimestampExample.signHex(SECRET, unsigned));
    }

    @Test
    void validSignatureButExpiredTimestampMustBeRejected() {
        var request = signedAt(FIXED_CLOCK.instant().minusSeconds(301), "nonce-01");

        assertEquals(HmacTimestampExample.Decision.TIMESTAMP_EXPIRED,
                verifier.verify(request));
        assertTrue(seenNonces.isEmpty(), "Expired request must not consume nonce");
    }

    @Test
    void exactPastBoundaryIsStillAccepted() {
        var request = signedAt(FIXED_CLOCK.instant().minusSeconds(300), "nonce-02");

        assertEquals(HmacTimestampExample.Decision.ACCEPTED,
                verifier.verify(request));
    }

    @Test
    void timestampInsideWindowIsAccepted() {
        var request = signedAt(FIXED_CLOCK.instant().minusSeconds(299), "nonce-03");

        assertEquals(HmacTimestampExample.Decision.ACCEPTED,
                verifier.verify(request));
    }

    @Test
    void exactFutureBoundaryIsAccepted() {
        var request = signedAt(FIXED_CLOCK.instant().plusSeconds(60), "nonce-04");

        assertEquals(HmacTimestampExample.Decision.ACCEPTED,
                verifier.verify(request));
    }

    @Test
    void timestampTooFarInFutureIsRejected() {
        var request = signedAt(FIXED_CLOCK.instant().plusSeconds(61), "nonce-05");

        assertEquals(HmacTimestampExample.Decision.TIMESTAMP_FUTURE,
                verifier.verify(request));
        assertTrue(seenNonces.isEmpty());
    }

    @Test
    void changingOnlyTimestampCannotRescueExpiredSignature() {
        var expired = signedAt(FIXED_CLOCK.instant().minusSeconds(301), "nonce-06");
        var tampered = new HmacTimestampExample.Request(
                expired.method(), expired.pathAndQuery(),
                Long.toString(FIXED_CLOCK.instant().getEpochSecond()),
                expired.nonce(), expired.body(), expired.signatureHex());

        assertEquals(HmacTimestampExample.Decision.SIGNATURE_INVALID,
                verifier.verify(tampered));
    }

    @Test
    void malformedTimestampIsRejectedSafely() {
        var valid = signedAt(FIXED_CLOCK.instant(), "nonce-07");
        var malformed = new HmacTimestampExample.Request(
                valid.method(), valid.pathAndQuery(),
                "999999999999999999999999999999999",
                valid.nonce(), valid.body(), valid.signatureHex());

        assertEquals(HmacTimestampExample.Decision.TIMESTAMP_INVALID,
                verifier.verify(malformed));
    }

    @Test
    void validRequestCannotBeReplayedWithinFreshnessWindow() {
        var request = signedAt(FIXED_CLOCK.instant(), "nonce-08");

        assertEquals(HmacTimestampExample.Decision.ACCEPTED,
                verifier.verify(request));
        assertEquals(HmacTimestampExample.Decision.NONCE_REPLAY,
                verifier.verify(request));
    }
}
~~~

Điểm mấu chốt ở test đầu tiên: `signedAt` thực sự tạo HMAC cho request mang timestamp cũ. Vì vậy kết quả `TIMESTAMP_EXPIRED` không thể bị nhầm với một request sửa timestamp làm signature không khớp. Kiểm tra `seenNonces.isEmpty()` còn chứng minh logic expired dừng trước khi đăng ký nonce.

Hai test biên kiểm tra phép so sánh có vô tình bị đổi từ `<` thành `<=` hoặc từ `>` thành `>=` hay không. Khi thay đổi chính sách thời gian, cập nhật ví dụ hợp đồng và toàn bộ test biên cùng lúc.

## 6. Kiểm thử tích hợp và các trường hợp dễ bỏ sót

### 6.1. Đồng hồ, độ phân giải và múi giờ

Timestamp theo **giây** phải được đọc là giây, không phải millisecond. Một giá trị epoch millisecond 13 chữ số khi hiểu thành giây có thể vượt phạm vi `Instant` hoặc bị xem là quá xa trong tương lai. Nếu client và server muốn dùng millisecond hoặc ISO 8601, phải đổi đồng bộ hợp đồng ký và parser.

Ở môi trường thực, server cần đồng hồ được đồng bộ phù hợp (ví dụ NTP). Với nhiều instance, các đồng hồ bị lệch khác nhau có thể tạo kết quả chấp nhận/từ chối khác nhau cho cùng request. Test integration nên chạy cùng payload qua từng instance bằng đồng hồ kiểm soát được, kiểm tra số liệu lệch clock và cảnh báo vận hành khi skew lớn. Dùng một snapshot `now` trong một lần verify; không đọc lại đồng hồ ở các bước so sánh biên.

### 6.2. Proxy/gateway và canonical request

Gateway có thể decode/re-encode URL, sắp xếp query, thay `Host`, xử lý body hoặc thay đường dẫn trước khi request tới service. Việc này thường tạo **signature mismatch** chứ không phải expired; test phải chỉ ra đúng nguyên nhân. Kiểm tra end-to-end từ client qua gateway bằng một request **chưa hết hạn** trước, rồi lặp lại cùng đường đi với request đã ký có timestamp hết hạn. Không lấy timestamp mới từ gateway thay cho timestamp client đã ký, trừ khi giao thức quy định rõ bên nào chịu trách nhiệm ký và kiểm thời gian.

Với duplicate `X-HMAC-Timestamp`, giá trị mơ hồ, header thiếu hoặc canonical target không nhất quán, nên từ chối rõ ràng theo hợp đồng. Không âm thầm chọn một trong nhiều timestamp rồi tiếp tục xác thực.

### 6.3. Nonce, replay và phân tán

Một `Set` trong JUnit chỉ mô phỏng trạng thái của **một test**. Với nhiều pod/instance, test tích hợp phải xác nhận hai request cùng nonce gửi đồng thời tới hai instance chỉ có tối đa một request được nhận. Kho nonce cần thao tác đăng ký **atomic**, khóa định danh theo client/tenant thích hợp và TTL bao phủ **toàn bộ** cửa sổ timestamp còn hợp lệ, kể cả phần sai lệch và điểm biên đã chọn.

Cần test thêm rằng expired request **không được ghi nonce** và signature sai **không được ghi nonce**. Nonce hết TTL quá sớm có thể cho phép replay trong thời gian timestamp vẫn còn hiệu lực; TTL quá ngắn là lỗi bảo mật, còn TTL quá dài gây tốn tài nguyên.

### 6.4. Key rotation và giới hạn của xác thực

Trong giai đoạn rotation, server có thể chấp nhận chữ ký bằng cả key cũ và key mới theo chính sách. Điều đó **không gia hạn timestamp**: một request được ký đúng bằng key còn hiệu lực nhưng quá cũ vẫn phải nhận lỗi expired. Nếu hỗ trợ `keyId`, test key lookup, phân quyền sử dụng key và khóa nonce phải nhất quán theo danh tính client.

HMAC + timestamp + nonce cho biết request đủ điều kiện **xác thực** và chống replay theo giới hạn đã định; chúng **không tự cấp quyền** thực hiện chuyển tiền, đọc dữ liệu hoặc gọi endpoint. Sau khi xác thực thành công, hệ thống vẫn phải chạy kiểm tra **phân quyền** riêng cho principal và tài nguyên.

### 6.5. Quan sát lỗi mà không tiết lộ bí mật

Nên có mã kết quả nội bộ như `timestamp_missing`, `timestamp_invalid`, `timestamp_expired`, `timestamp_future`, `signature_invalid` và `nonce_replay` để test/metric phân biệt lỗi. Log có thể lưu mã lỗi, thời điểm server, tuổi request, keyId đã kiểm soát và correlation ID; tránh ghi shared secret, chữ ký đầy đủ, canonical request chứa dữ liệu nhạy cảm hoặc toàn bộ body. Phản hồi public nên thống nhất với contract và chính sách chống lộ thông tin.

## 7. Checklist trước khi hoàn tất bài test

- [ ] Timestamp được ký cùng method, URI và các trường/body theo hợp đồng; không thể thay riêng timestamp để gia hạn hiệu lực.
- [ ] Request **được ký đúng** nhưng `ts < now - maxAge` bị từ chối; điểm biên `ts = now - maxAge` có kỳ vọng rõ ràng.
- [ ] Timestamp tương lai quá xa, thiếu, sai định dạng hoặc overflow bị từ chối ổn định.
- [ ] Test dùng đồng hồ cố định và không phụ thuộc `sleep`, thời gian máy CI hay múi giờ cục bộ.
- [ ] Request hết hạn hoặc chữ ký sai không chiếm nonce; request còn hạn nhưng replay nonce bị từ chối.
- [ ] Proxy/gateway, nhiều instance, TTL nonce và key rotation được kiểm thử theo hợp đồng triển khai.
- [ ] Xác thực HMAC thành công vẫn phải đi qua bước phân quyền của ứng dụng.

**Bài thực hành mở rộng:** Đổi chính sách từ `300 s / 60 s` thành `120 s / 30 s`, sửa test biên và kiểm tra nonce TTL; tạo một integration test đi qua gateway với hai request mang cùng body và chữ ký hợp lệ, trong đó một timestamp nằm ở `now - 120 s` và một timestamp ở `now - 121 s`. Xác nhận request thứ hai bị từ chối đúng vì **expired timestamp**, không phải vì canonicalization hay HMAC sai.
