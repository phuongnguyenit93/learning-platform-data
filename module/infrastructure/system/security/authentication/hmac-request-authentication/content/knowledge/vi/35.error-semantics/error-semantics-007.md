# Nonce đã dùng: ngữ nghĩa lỗi chống replay trong xác thực HMAC

## 1. Khi HMAC hợp lệ nhưng request vẫn không hợp lệ

Trong mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client dùng **shared secret** để tạo chữ ký HMAC cho **canonical request** gồm phương thức HTTP, URI, một số header và/hoặc body digest theo hợp đồng. Server xác minh bằng đúng secret được đăng ký cho key ID, kiểm tra trạng thái credential, timestamp và nonce, rồi mới phân quyền.

Chữ ký HMAC trả lời câu hỏi “request này có được tạo bởi bên biết secret và các trường đã ký có còn nguyên vẹn không?”. Nó **không** trả lời câu hỏi “request này đã được xử lý trước đây chưa?”. Người có một bản sao request đã ký đúng có thể phát lại nó trong cửa sổ hiệu lực chữ ký.

**Nonce** (*number used once*) là giá trị định danh một lần gửi, được ký cùng timestamp và các trường quan trọng. Server ghi nhận nonce bằng thao tác nguyên tử. Khi request mới dùng lại nonce thuộc cùng phạm vi, hệ thống kết luận **nonce đã dùng** và từ chối trước khi thực thi nghiệp vụ.

Ví dụ:

~~~http
POST /api/payments HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-a
X-Key-Id: partner-a-k4
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: 90f03696-0b90-4cb1-9240-52cf53cc81bb
X-Signature: <base64-hmac-sha256>

{"paymentId":"pay-101","amount":250000}
~~~

Chữ ký ở đây là placeholder minh họa. Lần gửi thứ nhất có thể thành công nếu HMAC, timestamp, nonce, quyền và dữ liệu hợp lệ. Nếu gửi lại **y hệt request**, chữ ký HMAC vẫn đúng, nhưng nonce đã được claim và request sau phải bị từ chối.

**Bất biến cần bảo vệ:** trong phạm vi replay key đã công bố, mỗi nonce chỉ có **một lần claim thành công** khi chữ ký còn hợp lệ, kể cả khi nhiều gateway/instance xử lý đồng thời.

## 2. Phân biệt nonce used, request authenticated và business committed

“Nonce đã dùng” có nghĩa: **replay store ghi nhận nonce từng được claim** trong cửa sổ bảo vệ. Nó **không** khẳng định nghiệp vụ đã commit hoặc client đã nhận response.

| Sự kiện | Điều chứng minh | Điều không chứng minh |
| --- | --- | --- |
| HMAC hợp lệ | Người gửi biết secret tương ứng với credential/key ID | Request chưa từng được gửi |
| Timestamp trong cửa sổ | Request đủ mới theo hợp đồng thời gian | Không có bản sao request |
| Nonce claim lần đầu | Chưa có lần claim hợp lệ trước trong scope | Giao dịch đã thành công |
| Principal authenticated | Danh tính được xác nhận | Có quyền trên mọi tenant/resource |
| Authorization allowed | Có quyền theo policy của action/target | Giao dịch đã commit |
| Business transaction committed | Side effect cụ thể đã được lưu theo giao dịch | Client chắc chắn đã thấy response |

Ví dụ gateway nhận HMAC hợp lệ, claim nonce N1 rồi chuyển tới service. Service ghi DB, nhưng HTTP response bị mất trên mạng. Client không biết kết quả. Gửi lại N1 bị từ chối **replay**, dù giao dịch đầu có thể đã thành công.

Ngược lại, gateway đã claim N1 rồi backend gặp lỗi trước khi ghi DB. N1 vẫn đã dùng, dù giao dịch **chưa** thành công. Vì vậy, không sử dụng nonce store để suy diễn kết quả payment hay order.

### Trạng thái replay store

| Kết quả | Ý nghĩa | Hành vi an toàn |
| --- | --- | --- |
| `FIRST_USE` | Ghi key nonce mới thành công | Có thể đi tiếp sau các kiểm tra khác |
| `ALREADY_USED` | Key nonce đã tồn tại | Từ chối replay |
| `OUT_OF_WINDOW` | Timestamp không còn hoặc chưa trong cửa sổ | Từ chối trước nghiệp vụ |
| `MALFORMED` | Nonce/header thiếu, trùng, quá dài hoặc sai format | Từ chối request |
| `UNKNOWN` / `UNAVAILABLE` | Không biết claim có thành công không vì store lỗi/timeout | **Fail closed**, không coi là nonce mới |

Không có trạng thái “được phép chạy tạm vì Redis đang lỗi” trong một hệ thống cam kết chống replay.

## 3. Phải ký nonce và timestamp trong canonical request

Một hợp đồng HMAC minh họa `HMAC-REQUEST-V1` có thể tạo chuỗi UTF-8 sau, dùng `LF` làm dấu phân cách và không thêm `LF` cuối:

~~~text
HMAC-REQUEST-V1
POST
/api/payments
application/json
partner-a
partner-a-k4
2026-11-28T04:00:00Z
90f03696-0b90-4cb1-9240-52cf53cc81bb
<sha256-hex-cua-raw-body-bytes>
~~~

Chuỗi trên là ví dụ **cấu trúc**, không phải vector có digest/HMAC thực. Hợp đồng phải cố định cách xử lý URI/query, header trùng, percent-encoding, ký tự xuống dòng, charset, body rỗng, tên key và version.

Với nonce đã được đưa vào canonical bytes:

- Kẻ ngoài thay `X-Nonce` sau khi client ký → chữ ký HMAC phải sai.
- Kẻ ngoài thay `X-Timestamp` sau khi ký → chữ ký phải sai.
- Sao chép nguyên request, không sửa gì → HMAC vẫn hợp lệ nhưng replay store phải từ chối.
- **Chính client** dùng secret của mình ký request mới với cùng nonce → HMAC có thể đúng, nhưng replay guard vẫn từ chối nếu scope yêu cầu nonce duy nhất.

Nếu nonce/timestamp **không nằm trong nội dung được ký**, attacker có thể thay chúng mà không làm chữ ký sai. Dùng Redis lúc này không sửa được lỗi giao thức.

### Timestamp, nonce, request ID, idempotency key là bốn khái niệm khác nhau

- **Timestamp:** hạn chế thời gian một request đã ký còn được xem xét.
- **Nonce:** định danh một lần gửi để phát hiện việc dùng lại bằng chứng HMAC.
- **Request ID / correlation ID:** phục vụ truy vết; không nhất thiết được ký hoặc có độ duy nhất toàn cục.
- **Idempotency key:** định danh **một ý định nghiệp vụ**, dùng để lặp lại an toàn nếu kết quả gửi trước chưa rõ; có vòng đời và data store riêng.

Một idempotency key có thể giữ nguyên trên nhiều lần thử với **nonce mới**. Không dùng nonce làm idempotency key hoặc coi nonce đã dùng là bằng chứng nghiệp vụ đã commit.

## 4. Thứ tự xác thực, claim nonce và phân quyền

Pipeline gợi ý:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Giới hạn kích thước, parse method/URI/header/body"]
    B --> C{"Timestamp/nonce đúng format và cửa sổ?"}
    C -->|Không| Z["Từ chối authentication"]
    C -->|Có| D["Tra đúng credential và kiểm tra ACTIVE/client enabled"]
    D --> E{"Canonical request + HMAC hợp lệ?"}
    E -->|Không| Z
    E -->|Có| F["Atomic claim (credentialId, nonce)"]
    F -->|ALREADY_USED| R["Replay: từ chối authentication"]
    F -->|UNKNOWN| U["Fail closed: dependency unavailable"]
    F -->|FIRST_USE| G["Tạo principal tin cậy"]
    G --> H{"Authorization tenant/action/resource?"}
    H -->|Không| Y["403 / 404 theo policy"]
    H -->|Có| I["Controller và nghiệp vụ"]
~~~

**Điều bắt buộc:** chỉ **ghi nonce sau khi đã xác minh HMAC đúng**. Nếu ghi trước khi chứng minh người gửi sở hữu secret, người ngoài có thể đoán/biết nonce của một request hợp lệ rồi gửi request giả để “chiếm” nonce đó (*nonce poisoning*). Việc từ chối request sai format hoặc timestamp ngoài cửa sổ có thể diễn ra sớm để tiết kiệm tài nguyên, nhưng **không ghi replay record** từ request chưa xác minh chữ ký.

Trong chính sách ở sơ đồ, một request có HMAC hợp lệ nhưng **không có quyền tenant** vẫn claim nonce trước khi bước authorization từ chối. Lần phát lại y nguyên cũng sẽ bị từ chối. Đây là hành vi hợp lệ nếu được công bố trong thiết kế. Không được cho nghiệp vụ thực thi **trước** khi claim nonce thành công.

### Race condition: hai request đến cùng lúc

~~~mermaid
sequenceDiagram
    participant A as Gateway A
    participant B as Gateway B
    participant S as Shared Replay Store
    participant P as Payment Service
    A->>S: SET nonce N1 IF ABSENT + TTL
    B->>S: SET nonce N1 IF ABSENT + TTL
    S-->>A: FIRST_USE
    S-->>B: ALREADY_USED
    A->>P: Xét authorization và nghiệp vụ
    B-->>B: Từ chối replay, không gọi service
~~~

Không dùng quy trình `GET nonce` rồi `SET nonce` theo hai lệnh tách biệt: cả hai node có thể cùng đọc “chưa tồn tại”. Sử dụng **insert-if-absent nguyên tử kèm TTL**, ví dụ `SET ... NX PX ...` tại Redis hoặc unique insert trong database.

## 5. Scope của replay key phải cố định và đáng tin

Một cách phổ biến là:

~~~text
replayKey = (credentialId, nonce)
~~~

Trong đó `credentialId` do credential registry phía server xác định sau khi xác minh key ID và HMAC, **không** phải namespace do client tự đặt tùy ý.

| Scope | Ưu điểm | Rủi ro/câu hỏi |
| --- | --- | --- |
| `(credentialId, nonce)` | Phân tách nhiều client/key version; rõ với HMAC | Nonce có thể trùng qua key version nhưng contract vẫn cho phép |
| `(clientId, nonce)` | Bảo vệ reuse qua nhiều key của cùng client | Cần chủ thể client đáng tin, phối hợp rotation |
| `(tenantId, nonce)` | Có thể hợp nghiệp vụ đặc thù | Dễ gây xung đột client khác trong tenant hoặc mở đường nếu tenant claim thay đổi |
| `nonce` toàn cục | Đơn giản về mặt lý thuyết | False positives giữa các client, chi phí lưu giữ lớn |

Không đưa `requestedTenantId` vào replay key chỉ vì API đa tenant. Nếu cùng credential có grant đến nhiều tenant, việc dùng `(keyId, tenantId, nonce)` có thể tạo nhiều namespace cho một nonce; chỉ làm vậy khi hợp đồng thực sự yêu cầu và đã chứng minh không có nguy cơ bypass.

### Tạo nonce như thế nào?

Với các client chạy trên nhiều máy, nên dùng CSPRNG, chẳng hạn UUIDv4 đủ entropy hoặc 128 bit random mã hóa Base64url/hex. Nonce cần:

- Được sinh **mới cho mỗi lần gửi**.
- Có giới hạn chiều dài, ký tự được chấp nhận và định dạng chuẩn.
- Không chứa secret, thông tin cá nhân, timestamp làm nguồn duy nhất.
- Được đưa vào canonical bytes cùng key ID và timestamp.
- Không phụ thuộc vào việc các client instances có đồng bộ counter hay không.

Không coi `X-Request-Id` tự khai là nonce nếu ID này có thể lặp hoặc không được ký.

## 6. Cửa sổ timestamp và TTL nonce phải tương thích

Giả sử hệ thống chấp nhận timestamp lệch tối đa **5 phút** hai chiều:

~~~text
now - W <= signedTimestamp <= now + W
W = 5 phút
~~~

Khi một request đến ở rìa **timestamp tương lai 5 phút**, request đó vẫn có thể được xem là “đủ mới” trong **10 phút tiếp theo**, cho tới khi thời gian server vượt `signedTimestamp + W`.

Vì vậy, TTL cố định tính từ lúc claim cần bao phủ tối đa toàn bộ cửa sổ:

\[
\operatorname{nonceTTL} \ge 2W + \varepsilon
\]

`ε` là khoảng đệm cho skew đồng hồ, độ chính xác thời gian, độ trễ xử lý và đặc tính expiry của store. Nếu `W = 5 phút`, một ví dụ bảo thủ là **11 phút** — không phải một chuẩn bắt buộc cho mọi hệ thống.

Hoặc tính expiry theo timestamp:

~~~text
expireAfter = max(0, signedTimestamp + W + safetyMargin - serverNow)
~~~

Ở cả hai cách, **không được để replay key biến mất trước khi cùng chữ ký vẫn có thể được chấp nhận ở một verifier hợp lệ**. Dùng clock UTC được đồng bộ và kiểm thử biên inclusive/exclusive.

| Timestamp khi server là 04:00:00Z | Chấp nhận với W=5 phút, biên inclusive? |
| --- | --- |
| `03:54:59Z` | Không |
| `03:55:00Z` | Có |
| `04:00:00Z` | Có |
| `04:05:00Z` | Có |
| `04:05:01Z` | Không |

**Lỗi phổ biến:** TTL = 5 phút cho timestamp window ±5 phút. Một nonce được claim khi timestamp ở tương lai có thể hết hạn trong khi chữ ký vẫn được coi là mới. Replay sau thời điểm hết TTL sẽ vượt qua nếu không có lớp bảo vệ khác.

Tại thời điểm nonce đã hết TTL, timestamp của request cũ **bắt buộc** đã hết hạn. Timestamp và nonce bổ sung nhau, không thay thế nhau.

## 7. Redis replay store: nguyên tử nhưng phải xem xét failover

Redis có thể thực hiện claim và expiry trong **một lệnh nguyên tử**:

~~~redis
SET hmac:nonce:v1:<digest-of-key-and-nonce> 1 NX PX 660000
~~~

Trong ví dụ `660000 ms = 11 phút`. `NX` chỉ chấp nhận khi chưa có key. Không làm `SETNX` rồi `EXPIRE` bằng hai lệnh riêng, vì tiến trình có thể chết giữa hai thao tác.

Một primary Redis có thể đảm bảo `SET NX` nguyên tử đối với các request đến chính primary đó. Nhưng **replication bất đồng bộ, split-brain hoặc failover mất dữ liệu** có thể phá cam kết “một nonce chỉ được chấp nhận một lần trên mọi region”. Nếu hệ thống yêu cầu chống replay toàn cục, phải có **miền claim có thẩm quyền/độ nhất quán phù hợp**, hoặc ràng buộc credential vào region cố định và từ chối khi không thể chứng minh trạng thái.

### Mã Spring Data Redis (Servlet / Spring MVC)

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;

import org.springframework.data.redis.core.StringRedisTemplate;

enum ClaimResult {
    FIRST_USE, ALREADY_USED
}

interface ReplayStore {
    ClaimResult claim(
        String credentialId, String nonce, Duration ttl);
}

final class ReplayStoreUnavailableException extends RuntimeException {
    ReplayStoreUnavailableException(String message) {
        super(message);
    }
}

final class RedisReplayStore implements ReplayStore {
    private final StringRedisTemplate redis;

    RedisReplayStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public ClaimResult claim(
            String credentialId, String nonce, Duration ttl) {
        String key = keyOf(credentialId, nonce);

        Boolean inserted =
            redis.opsForValue().setIfAbsent(key, "1", ttl);

        if (inserted == null) {
            throw new ReplayStoreUnavailableException(
                "replay_store_result_unknown");
        }
        return inserted
            ? ClaimResult.FIRST_USE
            : ClaimResult.ALREADY_USED;
    }

    private static String keyOf(
            String credentialId, String nonce) {
        try {
            MessageDigest sha =
                MessageDigest.getInstance("SHA-256");
            byte[] id =
                credentialId.getBytes(StandardCharsets.UTF_8);
            byte[] nonceBytes =
                nonce.getBytes(StandardCharsets.UTF_8);

            // Length-prefix ngăn nhập nhằng khi ghép tuple.
            sha.update(ByteBuffer.allocate(Integer.BYTES)
                .putInt(id.length).array());
            sha.update(id);
            sha.update(nonceBytes);

            return "hmac:nonce:v1:"
                + HexFormat.of().formatHex(sha.digest());
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(
                "SHA-256 unavailable", e);
        }
    }
}
~~~

Mã ví dụ thể hiện **claim có TTL**, không bao gồm cấu hình Redis, TLS, retry và phân loại mọi exception. Redis connection failure/timeout phải được chuyển sang **lỗi phụ trợ xác thực** và fail closed, không coi như `ALREADY_USED` hay `FIRST_USE`. Nếu `SET NX` thành công nhưng response mạng bị mất, caller nhận kết quả **không rõ**; không nên cho request đi tiếp.

Đừng để eviction policy xóa replay key trước TTL khi Redis đầy. Kiểm soát memory limit, keyspace metrics, quyền truy cập, replication, snapshot/durability và failover theo SLA bảo mật.

Với **Spring WebFlux**, không gọi `StringRedisTemplate` blocking trên event loop. Dùng `ReactiveStringRedisTemplate` hoặc một client Redis non-blocking, không `block()`.

## 8. Java 17: kiểm tra nonce sau khi chữ ký đã được xác minh

Cách tách trách nhiệm rõ ràng là HMAC verifier tạo **evidence đã xác thực**; replay guard chỉ nhận evidence từ ranh giới tin cậy đó.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.regex.Pattern;
import org.springframework.security.authentication.BadCredentialsException;

// Chỉ được tạo/chuyển vào guard sau khi kiểm tra chữ ký HMAC.
record VerifiedHmacEvidence(
    String credentialId,
    Instant signedAt,
    String nonce
) {}

final class NonceReplayRejectedException
        extends BadCredentialsException {
    NonceReplayRejectedException() {
        super("authentication_failed");
    }
}

public final class NonceReplayGuard {
    private static final Duration WINDOW = Duration.ofMinutes(5);
    private static final Duration TTL = Duration.ofMinutes(11);
    private static final Pattern NONCE =
        Pattern.compile("[A-Za-z0-9_-]{16,128}");

    private final ReplayStore store;
    private final Clock clock;

    public NonceReplayGuard(ReplayStore store, Clock clock) {
        this.store = Objects.requireNonNull(store);
        this.clock = Objects.requireNonNull(clock);
    }

    public void checkAndClaim(VerifiedHmacEvidence proof) {
        if (proof == null
                || proof.credentialId() == null
                || proof.credentialId().isBlank()
                || proof.signedAt() == null
                || proof.nonce() == null
                || !NONCE.matcher(proof.nonce()).matches()) {
            throw new BadCredentialsException(
                "authentication_failed");
        }

        Instant now = clock.instant();
        if (proof.signedAt().isBefore(now.minus(WINDOW))
                || proof.signedAt().isAfter(now.plus(WINDOW))) {
            throw new BadCredentialsException(
                "authentication_failed");
        }

        ClaimResult result = store.claim(
            proof.credentialId(), proof.nonce(), TTL);

        if (result != ClaimResult.FIRST_USE) {
            throw new NonceReplayRejectedException();
        }
    }
}
~~~

Đoạn mã minh họa chọn biên timestamp inclusive; khi bằng `now ± 5 phút` thì còn được xem xét. Trong ứng dụng thực, format timestamp từ header phải được parse và canonical hóa trước đó theo hợp đồng ký.

**Quan trọng:** record `VerifiedHmacEvidence` tự nó không phải một token chống giả. Không xây record này trực tiếp từ JSON do caller gửi. Luồng đúng:

~~~text
parse HTTP + size limits
  → credential lookup by exact key ID + state
  → reconstruct canonical bytes from method/URI/signed headers/body
  → verify HMAC using exactly that credential's secret
  → construct VerifiedHmacEvidence from signed values
  → checkAndClaim nonce atomically
  → create trusted principal
  → authorization by tenant/action/resource
  → business handler
~~~

Mẫu này chưa bao gồm HMAC verifier, secret manager, trạng thái client/tenant, key rotation hay response mapping. Nó tập trung vào chính sách nonce, không phải một authentication provider production đầy đủ.

## 9. Ngữ nghĩa lỗi HTTP khi nonce đã dùng

Khi hệ thống dùng timestamp/nonce làm điều kiện của **HMAC authentication**, nonce đã dùng thường được xem là **authentication failed**. Một public API có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
Cache-Control: no-store
WWW-Authenticate: HMAC realm="api"

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required or invalid.",
  "code": "AUTHENTICATION_FAILED",
  "requestId": "req-6c912"
}
~~~

Đây là **hợp đồng minh họa**, không phải response do Spring Security tự tạo cho HMAC. Nếu chọn HTTP 401, cần challenge `WWW-Authenticate` phù hợp; `HMAC realm="api"` chỉ nên dùng khi API **đã định nghĩa scheme HMAC đó**. `application/problem+json` theo Problem Details cho phép các extension `code`, `requestId` nếu API công bố.

### Có nên nói “nonce đã sử dụng” với client không?

Đối với một API có yêu cầu không để lộ credential, nên **gom** những trường hợp HMAC sai, key không tồn tại/revoked, timestamp sai và nonce trùng thành public `AUTHENTICATION_FAILED`. Lý do `REPLAY_DETECTED` chỉ ghi trong audit/metric bảo mật nội bộ. Nếu trả `NONCE_ALREADY_USED` riêng, kẻ tấn công có thể dùng status/body/timing làm **oracle** để thăm dò hoạt động của credential hoặc request.

Chênh lệch thời gian xử lý vẫn có thể gây lộ thông tin ngay khi body lỗi giống nhau; cần rate limiting, đồng nhất phản hồi ở mức phù hợp, tránh hứa toàn bộ hệ thống mạng/DB có timing constant-time. MAC phải được so sánh bằng thao tác phù hợp như `MessageDigest.isEqual` trên bytes đúng độ dài.

### Tại sao thường không trả 409?

`409 Conflict` thường biểu thị **xung đột trạng thái tài nguyên/nghiệp vụ**. Một nonce trùng làm request không đạt điều kiện authentication, nên `401` thường hợp lý hơn. `409` có thể dành cho trường hợp **idempotency key đã gắn với payload khác** hoặc xung đột business state. Nếu hợp đồng sản phẩm chọn status khác cho replay, phải đặc tả nhất quán và không làm lộ thông tin.

| Tình huống | Mã nội bộ ví dụ | Public status/code đề xuất |
| --- | --- | --- |
| Signature HMAC sai | `SIGNATURE_MISMATCH` | 401 `AUTHENTICATION_FAILED` |
| Nonce đã dùng | `REPLAY_DETECTED` | 401 `AUTHENTICATION_FAILED` |
| Timestamp ngoài cửa sổ | `TIMESTAMP_OUT_OF_WINDOW` | 401 `AUTHENTICATION_FAILED` |
| Credential REVOKED/EXPIRED | `CREDENTIAL_NOT_ACTIVE` | 401 `AUTHENTICATION_FAILED` |
| Nonce/header malformed | `NONCE_MALFORMED` | 401 chung hoặc 400 theo hợp đồng |
| Replay store không khả dụng | `REPLAY_STORE_UNAVAILABLE` | 503 `AUTHENTICATION_UNAVAILABLE`, fail closed |
| HMAC/nonce hợp lệ nhưng không có quyền | `ACCESS_DENIED` | 403 hoặc 404 theo chính sách |
| Idempotency key trùng với payload khác | `IDEMPOTENCY_CONFLICT` | 409 theo hợp đồng |
| Body vượt giới hạn | `PAYLOAD_TOO_LARGE` | 413 |
| Quá rate limit | `RATE_LIMITED` | 429 |

## 10. Spring Security: trả 401 ở đúng ranh giới

Trong Spring MVC với Spring Security 6, `AuthenticationProvider`/replay guard có thể ném `BadCredentialsException` khi nonce đã dùng. Một custom `OncePerRequestFilter` tự gọi `AuthenticationManager` phải bắt `AuthenticationException` ở đúng vị trí và gọi `AuthenticationEntryPoint`, vì `ExceptionTranslationFilter` nằm phía sau không tự bắt lỗi ném **trước khi** nó được gọi.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as HMAC Filter
    participant M as AuthenticationManager
    participant N as Replay Guard + Store
    C->>F: Request HMAC với nonce N1
    F->>M: authenticate(token chưa tin cậy)
    M->>N: checkAndClaim sau HMAC hợp lệ
    N-->>M: NonceReplayRejectedException
    M-->>F: AuthenticationException
    F-->>C: 401 chung qua AuthenticationEntryPoint
    Note over F,C: Không chạy controller, không có side effect
~~~

Một cấu trúc handler đúng là **chỉ bắt lỗi từ bước xác thực**, không bọc cả `chain.doFilter` vào một `catch(AuthenticationException)` có thể ghi response lỗi lần thứ hai nếu controller/downstream đã commit response:

~~~java
Authentication authenticated;
try {
    authenticated =
        authenticationManager.authenticate(hmacAttempt);
} catch (AuthenticationException ex) {
    SecurityContextHolder.clearContext();
    authenticationEntryPoint.commence(request, response, ex);
    return;
}

// Đây là phần tiếp theo sau khi authenticate thành công.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);
try {
    chain.doFilter(replayableRequest, response);
} finally {
    SecurityContextHolder.clearContext();
}
~~~

Đoạn code là **khung bên trong filter**, chưa bao gồm các biến và lớp adapter tạo canonical request. Nếu replay store timeout hoặc trả kết quả không biết, xử lý là **dependency failure**, không biến thành 401 “nonce đã dùng” một cách giả tạo và càng không gọi `chain.doFilter`.

`@RestControllerAdvice` không đảm bảo bắt exception từ security filter trước `DispatcherServlet`. Với **Spring WebFlux**, dùng `ReactiveAuthenticationManager`, `ServerAuthenticationEntryPoint` và Reactor Context; tránh dùng Redis client blocking trên event loop.

### Double registration cũng tạo false replay

Nếu filter HMAC vừa được đăng ký làm Servlet filter toàn cục vừa được thêm vào `SecurityFilterChain`, nó có thể chạy hai lần cho **cùng request**. Lần đầu claim nonce thành công, lần hai thấy USED và trả 401. Đây là lỗi cấu hình, không phải attacker replay. Kiểm thử thứ tự filter, dispatch `REQUEST`/`ASYNC`/`ERROR` và các đường matcher của security chain.

## 11. Retry, timeout và idempotency: ba ngữ nghĩa khác nhau

Sau khi gửi một request có nonce N1, client có thể nhận timeout hoặc 503. Không nên tự động gửi lại **y nguyên HMAC signature và nonce**.

| Tình huống client thấy | Điều có thể đã xảy ra | Hành động phù hợp |
| --- | --- | --- |
| 401 chung | Key/signature/timestamp/nonce không đạt | Không retry mù; kiểm tra ký và trạng thái credential |
| Timeout không có response | N1 có thể đã claim; nghiệp vụ có thể đã commit | Query trạng thái hoặc idempotent retry bằng nonce/signature mới |
| 503 từ replay store | Claim có thể không thực hiện hoặc kết quả mơ hồ | Fail closed; retry theo policy với nonce mới |
| 403 thiếu quyền tenant | Principal đã xác thực nhưng không được phép | Sửa quyền/policy, không chỉ đổi nonce |
| 409 idempotency conflict | Một key nghiệp vụ đã dùng cho payload khác | Giải quyết conflict, không bypass bằng nonce mới |
| 429 rate limit | Quota bị vượt | Tôn trọng `Retry-After`, ký lại khi đến thời điểm retry |
| 2xx hoặc 201 | Nghiệp vụ hoàn tất theo response | Không phát lại cùng request |

Ví dụ một ý định tạo payment:

~~~text
Business intent: CREATE_PAYMENT(payment-101)
Idempotency-Key: payment-101

Attempt 1:
  Timestamp: T1
  Nonce: N1
  Signature: HMAC(canonical request với T1, N1)
  Outcome: network timeout (unknown)

Attempt 2:
  Timestamp: T2 mới
  Nonce: N2 mới
  Signature: HMAC(canonical request với T2, N2)
  Idempotency-Key: payment-101 (GIỮ NGUYÊN)
  Outcome: cùng business result nếu idempotency được triển khai đúng

Malicious replay:
  Timestamp: T1
  Nonce: N1
  Signature: signature cũ
  Outcome: bị chặn bởi replay/timestamp
~~~

**Nonce mới chỉ chứng minh “lần gửi mới”, không tự ngăn double payment.** Idempotency key cần được ký/bound vào request và ràng buộc với principal, tenant, loại action, payload digest. Server phải áp dụng uniqueness và transaction/idempotency store đủ bền để cùng một business intent không sinh side effect kép. Việc này độc lập với replay store.

## 12. Có nên xóa nonce khi downstream trả 500 hoặc 403?

Thông thường **không xóa nonce sau khi đã claim**, kể cả khi authorization từ chối hoặc nghiệp vụ thất bại. Nếu xóa nonce theo HTTP status, một request đã ký có thể được gửi lại nhiều lần, trong khi một số side effect đã xảy ra trước lỗi.

~~~text
T0: Client gửi signed request nonce N1
T1: HMAC hợp lệ
T2: Nonce store claim N1 thành công
T3: Payment service phát event vào queue
T4: Database transaction rollback
T5: Client nhận 500
T6: Nếu xóa N1, cùng request có thể replay và phát event lần nữa
~~~

Replay guard bảo vệ **tính một lần của bằng chứng xác thực**, không bảo đảm tất cả side effect có tính nguyên tử. Nếu muốn “exactly once business effect” phải kết hợp transaction, idempotency, outbox hoặc cơ chế tương đương.

Trong chính sách claim trước authorization, request HMAC đúng nhưng thiếu grant có thể trả 403 và **nonce vẫn USED**. Đây là lựa chọn cần được ghi rõ để đội client không hiểu nhầm “403 tức nonce còn dùng được”.

## 13. Gateway, region và nhiều điểm xác minh HMAC

Có hai kiến trúc thông dụng.

**A — Gateway verify HMAC:** gateway kiểm tra signature, state, timestamp/nonce, rồi chuyển principal được xác thực đến backend bằng **mTLS hoặc assertion nội bộ được verify**. Backend không nên claim lại **chính replay key client** nếu request này đã được gateway claim; assertion nội bộ có thể có **cơ chế replay riêng** (ví dụ `jti`).

**B — Backend verify HMAC:** gateway định tuyến và giữ nguyên signed method/URI/header/body theo hợp đồng, backend tự claim nonce trong kho dùng chung. Proxy rewrite path hoặc giải nén body mà không có hợp đồng rõ sẽ gây signature mismatch.

Các sự cố phân tán:

| Thiết kế lỗi | Hậu quả |
| --- | --- |
| `HashSet` lưu nonce riêng trong mỗi JVM | Phát lại qua instance khác có thể thành công |
| Redis primary khác nhau ở hai region, chỉ replicate async | Hai region có thể đều claim cùng nonce |
| Failover mất write vừa thành công | Nonce đã dùng có thể “biến mất” |
| Eviction xóa replay record trước TTL | Request cũ có thể được nhận lại |
| Gateway và backend cùng claim một key | Request hợp lệ có thể bị chặn ở bước thứ hai |
| Retry y nguyên request sang gateway dự phòng | Lần sau có thể nhận 401 replay, kết quả lần đầu vẫn chưa rõ |
| Gateway bỏ qua nonce khi registry/store lỗi | Fail open, rủi ro replay |
| Client giả `X-Authenticated-Client` qua đường bypass gateway | Có thể vượt luôn cả HMAC nếu backend tin header |

Nếu cam kết chống replay **toàn cầu**, cần kiểm thử dưới chính topology và failure mode thực tế; một lệnh Redis atomic tại một primary không tự chứng minh consistency xuyên nhiều primary/region.

## 14. Key rotation, trạng thái credential và phân quyền tenant

Nonce luôn được xét trong **bối cảnh credential đang được phép xác thực**:

- Request khai key K4 phải dùng **secret của K4**, không thử K3 nếu chữ ký sai.
- K3 đã `REVOKED` phải bị từ chối dù HMAC tính bằng secret cũ vẫn đúng và nonce mới.
- Khi K3 và K4 cùng `ACTIVE` trong rotation window, scope nonce theo credential có thể cho cùng chuỗi nonce ở hai namespace; client vẫn nên sinh nonce mới cho từng request.
- Client bị `DISABLED` hoặc tenant bị `DISABLED` phải bị từ chối theo policy, không dùng key version mới để bypass.
- Registry cache cũ có thể giữ key `ACTIVE` sau revoke; cần freshness, invalidation hoặc fail closed theo cam kết thu hồi.
- Một request HMAC hợp lệ với nonce mới **không tự có quyền** trên tenant khác: authorization vẫn kiểm tra principal, target tenant, action và resource.

Không đưa tenant do client khai vào Redis replay namespace một cách tùy tiện. Nếu một credential được cấp grant cho nhiều tenant, việc tách nonce theo tenant có thể mở đường dùng lại cùng nonce khi thay tenant, trừ khi contract và policy đảm bảo an toàn.

## 15. Replay store thất bại: UNKNOWN không phải NEW

Một API có thể gặp:

~~~text
SET NX returns TRUE   → FIRST_USE
SET NX returns FALSE  → ALREADY_USED
SET NX timeout/error  → UNKNOWN
~~~

Trong trường hợp `UNKNOWN`, server không biết ghi nhận nonce đã thành công hay chưa; **không cho request đi tiếp**. Phản hồi có thể là 503 theo hợp đồng, có alert và correlation ID. Không fallback sang local cache; nếu nhiều gateway mỗi bên “tạm lưu riêng”, anti-replay mất tính toàn cục.

Bảng fault injection:

| Tình huống | Kỳ vọng |
| --- | --- |
| Redis timeout/connection refused | Fail closed, không gọi controller |
| Redis trả null/unknown | Fail closed, không tự giả định nonce mới |
| `SET NX` trả false | Từ chối replay, public error chung |
| Đã ghi Redis nhưng mất response | Không chạy nghiệp vụ khi không chắc kết quả |
| Failover ngay sau ghi | Test durability/độ mới theo SLA |
| Replica stale | Không dựa vào replica read yếu để quyết định claim |
| Redis out-of-memory/eviction | Alert, fail closed nếu không bảo đảm retention |
| TTL quá ngắn khi timestamp còn hợp lệ | Phát hiện bằng test ở mốc biên |
| Backend lỗi sau khi nonce đã claim | Nonce vẫn USED, retry business qua idempotency |

## 16. Ma trận kiểm thử nonce đã dùng

| ID | Kịch bản | Kết quả bắt buộc |
| --- | --- | --- |
| N-01 | HMAC đúng, nonce mới | Claim một lần và xét tiếp |
| N-02 | Gửi lại y nguyên request cùng instance | Từ chối, không side effect |
| N-03 | Replay tới instance thứ hai | Từ chối nếu cùng miền bảo vệ |
| N-04 | Hai request cùng nonce đồng thời | Chính xác một claim thành công |
| N-05 | Cùng nonce nhưng body khác, ký lại đúng | Từ chối theo scope credential |
| N-06 | Cùng nonce nhưng timestamp mới, ký lại đúng | Từ chối khi record còn hiệu lực |
| N-07 | Đổi nonce sau ký | HMAC sai, không claim nonce mới |
| N-08 | Chữ ký sai nhưng nonce trùng | Không cho attacker chiếm nonce |
| N-09 | Timestamp cũ hơn `now-W` | Từ chối |
| N-10 | Timestamp đúng biên `now±W` | Kết quả theo contract |
| N-11 | Timestamp ở rìa tương lai | TTL còn tới hết thời gian signature valid |
| N-12 | TTL quá ngắn, record hết khi signature còn valid | Test phát hiện cấu hình không an toàn |
| N-13 | Hai credential khác nhau cùng nonce | Theo scope key đã công bố |
| N-14 | Cùng credential/nonce đổi tenant | Không mở namespace khác tùy ý |
| N-15 | Key K3 REVOKED, nonce mới | Từ chối credential |
| N-16 | K3/K4 cùng ACTIVE khi rotation | Dùng đúng key ID/secret |
| N-17 | Client hoặc tenant DISABLED | Từ chối |
| N-18 | Nonce rỗng/quá dài/sai charset | Từ chối input |
| N-19 | Hai header nonce trong cùng request | Từ chối ambiguity |
| N-20 | Replay store timeout/unknown | Fail closed, không 2xx |
| N-21 | Claim xong controller 500 | Nonce vẫn USED |
| N-22 | Mất HTTP response sau commit | Retry bằng nonce mới + idempotency key cũ |
| N-23 | Idempotency key cũ + payload khác | Conflict nghiệp vụ theo contract |
| N-24 | HMAC đúng, thiếu grant tenant | 403/404 theo policy, không ghi trái quyền |
| N-25 | Filter đăng ký hai lần | Phát hiện double claim sai |
| N-26 | Proxy rewrite URI | HMAC khớp hợp đồng hoặc từ chối |
| N-27 | Replication lag xuyên region | Không double-accept nếu cam kết global |
| N-28 | Redis eviction nonce key sớm | Không được tạo replay thành công |
| N-29 | Record nonce còn nhưng timestamp đã hết hạn | Timestamp vẫn chặn |
| N-30 | Body/nonce đúng nhưng target resource tenant B | Authorization từ chối nếu thiếu grant |

### Unit test Java 17, JUnit 5

Ví dụ dùng một fake store **chỉ cho unit test**, không hỗ trợ TTL hoặc nhiều node:

~~~java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;

class NonceReplayGuardTest {
    static final class FakeStore implements ReplayStore {
        final Set<String> seen = ConcurrentHashMap.newKeySet();

        @Override
        public ClaimResult claim(
                String credentialId, String nonce, Duration ttl) {
            return seen.add(credentialId + ":" + nonce)
                ? ClaimResult.FIRST_USE
                : ClaimResult.ALREADY_USED;
        }
    }

    private final Instant now =
        Instant.parse("2026-11-28T04:00:00Z");

    private NonceReplayGuard guard(ReplayStore store) {
        return new NonceReplayGuard(store,
            Clock.fixed(now, ZoneOffset.UTC));
    }

    @Test
    void firstUseAcceptedAndSecondRejected() {
        FakeStore store = new FakeStore();
        NonceReplayGuard guard = guard(store);
        VerifiedHmacEvidence proof =
            new VerifiedHmacEvidence(
                "key-a-v2", now, "nonce-for-unit-test-001");

        assertDoesNotThrow(() -> guard.checkAndClaim(proof));
        assertThrows(NonceReplayRejectedException.class,
            () -> guard.checkAndClaim(proof));
    }

    @Test
    void oldTimestampDoesNotClaimNonce() {
        FakeStore store = new FakeStore();
        NonceReplayGuard guard = guard(store);

        assertThrows(BadCredentialsException.class,
            () -> guard.checkAndClaim(new VerifiedHmacEvidence(
                "key-a-v2", now.minusSeconds(301),
                "nonce-for-unit-test-002")));
        assertEquals(0, store.seen.size());
    }

    @Test
    void onlyOneConcurrentClaimWins() {
        NonceReplayGuard guard = guard(new FakeStore());
        AtomicInteger accepted = new AtomicInteger();

        IntStream.range(0, 100).parallel().forEach(i -> {
            try {
                guard.checkAndClaim(new VerifiedHmacEvidence(
                    "key-a-v2", now, "nonce-for-unit-test-003"));
                accepted.incrementAndGet();
            } catch (NonceReplayRejectedException expected) {
                // Các lần còn lại phải từ chối.
            }
        });

        assertEquals(1, accepted.get());
    }
}
~~~

Đây chỉ là **test trạng thái và concurrency trong một JVM**. Cần thêm integration test với Redis thật, giả lập failover, store timeout và TTL; test E2E qua ít nhất hai gateway/region để chứng minh phạm vi replay thực tế. Dùng signer HMAC **độc lập với verifier** và test body/URI/header không bị biến đổi qua proxy. Đặt Clock cố định trong unit test để tránh kiểm thử thời gian không ổn định.

## 17. Observability và phân biệt lỗi nội bộ với public API

Theo dõi các mã nội bộ như `REPLAY_DETECTED`, `TIMESTAMP_OUT_OF_WINDOW`, `SIGNATURE_MISMATCH`, `KEY_REVOKED`, `REPLAY_STORE_UNAVAILABLE`. Public response có thể cùng `AUTHENTICATION_FAILED` cho nhiều lỗi để giảm khả năng dò credential.

Những metric/alert hữu ích:

- Tỷ lệ replay theo route/gateway/region và phiên bản hợp đồng ký.
- Số lần Redis timeout, failover, eviction, độ trễ atomic claim.
- Bất thường “nonce đã dùng” xảy ra với mọi request hợp lệ của một service, gợi ý filter bị chạy hai lần hoặc client generator lỗi.
- Đồng hồ bị lệch, timestamp rejection tăng sau deploy proxy hoặc thay timezone.
- Key revoked vẫn có request accepted tại một gateway cache stale.
- Authorization denied sau HMAC thành công, để phân biệt thiếu quyền với replay.
- TTL của replay records so với timestamp window được cấu hình.

Không log shared secret, chữ ký đầy đủ, raw body nhạy cảm, canonical request đầy đủ hoặc nonce thô nếu không thực sự cần. Nếu cần đối chiếu, dùng hash định danh có giới hạn và correlation ID do hệ thống tin cậy tạo. Tránh dùng nonce/credential ID cardinality cao làm nhãn metric.

Audit “nonce claim thành công” **không được** ghi thành “payment completed” khi thiếu xác nhận từ business transaction.

## 18. Bài tập thực hành

Một API có:

~~~text
Timestamp window: +/- 5 phút
Replay key: (keyId, nonce)
Replay TTL: 5 phút
Store: mỗi region có một Redis primary, chỉ replicate bất đồng bộ
Gateway: xác minh HMAC trước khi gọi payment-service
~~~

Client gửi request N1 hợp lệ vào Region A. Gateway A claim N1; backend thực hiện chuyển khoản nhưng response bị mất. Client retry **y nguyên signature và N1** qua Region B, nơi N1 chưa được replicate; payment-service nhận request lần nữa và có thể tạo chuyển khoản thứ hai.

Hãy phân tích:

1. Vì sao HMAC vẫn hợp lệ khi gửi lại cùng request?
2. TTL 5 phút có đủ cho window ±5 phút không?
3. Vì sao replication bất đồng bộ không chứng minh chống replay toàn cục?
4. Atomic claim khác `GET` rồi `SET` như thế nào?
5. Lần gửi lại N1 nên là authentication error hay business conflict?
6. Claim nonce có chứng minh payment đã commit không?
7. Nên dùng nonce và idempotency key thế nào khi thử lại sau network timeout?
8. Vì sao không xóa N1 khi controller trả 500?
9. Nếu K3 đã REVOKED nhưng gateway cache còn ACTIVE, phải xử lý ra sao?
10. Những kiểm thử nào chứng minh không có side effect kép khi gateway failover?

**Hướng giải:** ký nonce/timestamp trong canonical request; TTL phải phủ toàn bộ thời gian chữ ký còn hợp lệ; claim nguyên tử ở một miền đủ consistency. Retry an toàn cần **nonce và chữ ký mới**, giữ **idempotency key** cho cùng business intent và kiểm chứng kết quả giao dịch. Không dùng key REVOKED, không fail open khi replay store lỗi và không suy ra quyền tenant từ HMAC đúng.

## 19. Checklist production cho lỗi “nonce đã dùng”

- Timestamp và nonce đều nằm trong **canonical request được HMAC bảo vệ**.
- Nonce được sinh mới/đủ entropy; độ dài, charset, duplicate header được kiểm tra.
- Credential lookup chọn đúng key ID/version, chỉ dùng secret của key đó; state ACTIVE và client/tenant policy được xét.
- Chỉ claim nonce **sau khi HMAC hợp lệ**, tránh nonce poisoning.
- Scope replay key được đặc tả theo credential/client đáng tin; không để client tự mở namespace.
- Claim atomic trong **một operation với TTL**, không check-then-set.
- TTL bao phủ toàn bộ timestamp acceptance window, có margin cho clock skew/expiry.
- Replay store hoạt động trên toàn phạm vi verifier đã cam kết; failover/replication/eviction đáp ứng mô hình chống replay.
- Không coi Redis timeout/null/unknown là `FIRST_USE`; phải fail closed và cảnh báo.
- Nonce đã claim không bị xóa tùy tiện sau lỗi nghiệp vụ hoặc authorization.
- Error response cho replay nhất quán, không tiết lộ trạng thái nonce/credential nhạy cảm.
- Phân biệt **authentication failure** với **authorization denied** và **business idempotency conflict**.
- Client không retry mù với cùng nonce/signature; dùng nonce mới và idempotency riêng khi an toàn.
- Gateway không rewrite các trường được ký ngoài hợp đồng; backend không tin forwarded/identity header giả.
- Filter không claim nonce hai lần do double registration hoặc ERROR/ASYNC dispatch.
- Có unit test fixed Clock, concurrency, Redis TTL/failover, gateway E2E, retry timeout và side-effect assertions.
- Audit/metrics phân loại `REPLAY_DETECTED` an toàn, không log secret/signature/body nhạy cảm.
- Key rotation, revoke, tenant isolation và resource authorization không bị bypass bởi nonce mới.
- Sự cố store bắt buộc fail closed; không fallback sang state in-memory phân tán.
- Mọi test replay đã chứng minh **không thực hiện lại nghiệp vụ** với cùng lần gửi.

**“Nonce đã dùng” mô tả một bằng chứng HMAC không được sử dụng lần thứ hai, chứ không mô tả kết quả giao dịch.** Thiết kế đúng phải ký nonce, kiểm tra timestamp, claim nguyên tử với TTL đủ dài, bảo vệ qua nhiều gateway/region và phân biệt rõ authentication, authorization và idempotency. Khi kết quả request ban đầu không rõ, tạo request mới với nonce mới chỉ là bước đầu; tính an toàn của retry phụ thuộc thêm vào idempotency và trạng thái nghiệp vụ.
