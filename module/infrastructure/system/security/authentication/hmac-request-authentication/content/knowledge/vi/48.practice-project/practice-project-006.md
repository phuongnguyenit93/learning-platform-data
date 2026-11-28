# Dự án thực hành: Thêm replay protection cho HTTP request xác thực bằng HMAC

## 1. Đề bài và sản phẩm cần bàn giao

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, client và server dùng **shared secret** để tạo/xác minh HMAC trên **canonical request**. Các thành phần được ký có thể bao gồm HTTP method, URI, header và/hoặc body theo hợp đồng. Request có chữ ký hợp lệ được xác thực, nhưng **chữ ký hợp lệ không tự động ngăn replay**: người có quyền quan sát request có thể gửi lại chính các byte cũ khi chữ ký vẫn còn hiệu lực.

Chương **Dự án thực hành** yêu cầu người học tự xây thêm một lớp **replay protection** vào pipeline HMAC đã có. Bài **Thêm replay protection** đi từ đặc tả, thiết kế dữ liệu, triển khai Java 17/Spring Security, kiểm thử đồng thời qua nhiều instance đến runbook vận hành. Sản phẩm mong muốn là một HTTP API chỉ cho phép **lần sử dụng đầu tiên của một nonce hợp lệ trong phạm vi đã xác thực**, đồng thời giữ nguyên các bảo đảm khác: key rotation, ràng buộc canonical request qua gateway/proxy, phân biệt authentication/authorization và không thực thi nghiệp vụ sau khi bị từ chối.

**Yêu cầu đầu ra của bài thực hành:**

1. Client sinh một **nonce ngẫu nhiên đủ mạnh**, gửi cùng timestamp và đưa cả hai vào dữ liệu được ký.
2. Server kiểm tra định dạng và khoảng thời gian của timestamp, nhưng **không cấp Authentication** trước khi MAC được xác minh.
3. Nonce được **claim bằng thao tác nguyên tử** ở kho dùng chung giữa các replica, chỉ **sau MAC hợp lệ**.
4. Replay của cùng nonce trong phạm vi thích hợp bị từ chối; lỗi nonce store phải **fail closed**.
5. Có kiểm thử positive, negative, race condition, key rotation, key/tenant scope, TTL và gateway.
6. Có bằng chứng request bị từ chối **không tạo side effect**; không nhầm anti-replay với idempotency.

> **Ranh giới công việc:** mã trong bài là blueprint thực hành theo Java 17, Spring Boot/Spring Security và Redis. Các interface HTTP/security adapter cần được nối với dự án của người học. Đây không phải một service được triển khai sẵn, cũng không thay thế việc kiểm thử Redis failover, cấu hình proxy và các phiên bản Spring cụ thể trong môi trường thực tế.

## 2. Mô hình tấn công: vì sao HMAC đúng vẫn chưa đủ?

Giả sử client gửi:

~~~http
POST /public/v1/orders?mode=preview HTTP/1.1
Host: api.example.test
X-Key-Id: client-fixture-v1
X-Timestamp: 2026-11-28T10:00:00Z
X-Nonce: AQIDBAUGBwgJCgsMDQ4PEA
X-Signature: D4TD+lq81gzVZKX8seubN7V+83JGXgMTsftMsYEMxGQ=
Content-Type: application/json

{"amount":125000}
~~~

Đây là request **synthetic** với credential giả để minh họa, không phải dữ liệu sản xuất. Kẻ tấn công không biết shared secret nhưng có thể sao chép **nguyên request**, kể cả chữ ký, timestamp và nonce. Nếu server chỉ tính lại HMAC, request thứ hai vẫn có chữ ký đúng về mặt mật mã.

Replay có thể gây:

- Tạo đơn hàng, chuyển tiền, gửi email hoặc cấp quyền nhiều lần.
- Đẩy số lần gọi downstream API, queue và database lên bất thường.
- Khai thác việc retry ở nhiều region hoặc nhiều instance không chia sẻ state.
- Tái sử dụng credential đang hợp lệ dù người phát request không giữ secret.

**Timestamp** chỉ thu hẹp cửa sổ replay; **nonce** ngăn sử dụng lại trong cửa sổ đó. **Idempotency key** xử lý lặp về mặt nghiệp vụ, kể cả khi request được ký lại bằng timestamp/nonce mới. Ba cơ chế này bổ trợ nhau, không thay thế nhau.

### 2.1. Bốn trường hợp cần phân biệt

| Trường hợp | HMAC | Timestamp | Nonce | Kết quả mong đợi |
|---|---|---|---|---|
| Request mới, đúng hợp đồng | Hợp lệ | Trong window | Chưa dùng | Tiếp tục authentication/authorization |
| Gửi lại nguyên request đã thành công | Hợp lệ | Còn trong window | Đã claim | **Từ chối replay** |
| Request cũ ngoài window, nonce không tồn tại | Hợp lệ | Hết hạn | Chưa dùng | **Từ chối freshness** |
| MAC giả nhưng nonce lấy từ request thật | Không hợp lệ | Có thể còn hạn | Có thể chưa dùng | **Từ chối MAC; không claim nonce** |

Case cuối đặc biệt quan trọng. Nếu server ghi nonce vào Redis **trước** khi kiểm tra HMAC, attacker có thể cố chiếm nonce của người khác, gây denial-of-service mà không cần biết secret.

## 3. Chốt hợp đồng request được ký

Không có một định dạng HTTP HMAC canonical mặc định cho mọi API. Bài thực hành giả định profile `HMAC-V1` ký tám dòng, nối bằng **LF (0x0A)**, mã hóa UTF-8, **không có LF cuối**:

~~~text
HMAC-V1
<UPPERCASE_METHOD>
<TRUSTED_PUBLIC_RAW_PATH>
<TRUSTED_PUBLIC_RAW_QUERY_OR_EMPTY>
<KEY_ID>
<UTC_TIMESTAMP>
<NONCE_BASE64URL_NO_PADDING>
<LOWERCASE_HEX_SHA256_OF_EXACT_BODY_BYTES>
~~~

Sau đó:

~~~text
bodyDigest = lowercaseHex(SHA256(exactBodyBytes))
canonicalBytes = UTF8(joinWithLF(theEightFields))
macBytes = HMAC-SHA256(secretBytes, canonicalBytes)
signatureHeader = standardBase64WithPadding(macBytes)
~~~

Các quyết định của profile ví dụ:

| Thành phần | Định dạng | Kiểm tra bắt buộc |
|---|---|---|
| `X-Key-Id` | ASCII token, độ dài giới hạn | Đúng một header; lookup chỉ là hint, không phải danh tính |
| `X-Timestamp` | UTC canonical `Instant.toString()`, ví dụ `2026-11-28T10:00:00Z` | Được ký, parse strict, server clock kiểm tra |
| `X-Nonce` | **16 byte random** → Base64URL **22 ký tự**, không `=` | Được ký, decode/re-encode canonical; uniqueness phía client |
| `X-Signature` | Base64 chuẩn có padding, HMAC-SHA256 đầy đủ 32 byte | Decode/length/canonical input theo profile; so sánh byte |
| URI | Public raw path/query đáng tin | Không dùng header forwarded do client giả |
| Body | Exact bytes được ký | Có giới hạn size; không JSON parse/serialize lại |

Giá trị `AQIDBAUGBwgJCgsMDQ4PEA` trong mẫu là nonce **cố định để kiểm thử**, không đủ ngẫu nhiên để dùng trong request thật. Trong production, mỗi request phải tạo nonce mới bằng CSPRNG.

**Nonce và timestamp là các trường được ký.** Nếu một client gửi lại request với nonce mới nhưng giữ signature cũ, MAC phải sai. Nếu signer và verifier không đưa timestamp/nonce vào canonical, anti-replay sẽ không có ranh giới tin cậy.

## 4. Golden vector để kiểm tra signer trước khi thêm nonce store

Để khoanh vùng lỗi, xác nhận request mẫu có HMAC đúng **trước** khi viết logic Redis. Bộ vector được tính từ secret giả:

~~~yaml
profile: HMAC-V1
algorithm: HmacSHA256
method: POST
public_raw_path: /public/v1/orders
public_raw_query: mode=preview
key_id: client-fixture-v1
timestamp: "2026-11-28T10:00:00Z"
nonce: AQIDBAUGBwgJCgsMDQ4PEA
body_utf8_no_trailing_newline: '{"amount":125000}'
body_bytes: 17
body_sha256_lowerhex: d54eaa73c7311358ffca8cc4b09475974cd2b0384840fefd75d8b4bde639fb85
secret_utf8_only_for_testing: test-replay-secret-for-fixture
canonical_utf8_bytes: 170
expected_signature_base64: D4TD+lq81gzVZKX8seubN7V+83JGXgMTsftMsYEMxGQ=
~~~

**Canonical text:**

~~~text
HMAC-V1
POST
/public/v1/orders
mode=preview
client-fixture-v1
2026-11-28T10:00:00Z
AQIDBAUGBwgJCgsMDQ4PEA
d54eaa73c7311358ffca8cc4b09475974cd2b0384840fefd75d8b4bde639fb85
~~~

Chỉ có **170 byte UTF-8** trong canonical; newline sau dòng cuối của code fence **không thuộc** message được ký.

Khi chạy test, hãy dùng golden vector literal làm **expected value độc lập**, không tạo expected bằng chính hàm signer đang test. Muốn kiểm tra đa ngôn ngữ, xuất cùng vector qua SDK Java, Go hoặc JavaScript độc lập.

## 5. Thiết kế pipeline: claim nonce ở vị trí nào?

~~~mermaid
flowchart TD
    A[HTTP request tới ingress] --> B[Giới hạn size, parse singleton headers, route policy]
    B --> C[Trusted public method/path/query + exact body]
    C --> D[Resolve key record + trạng thái key/profile]
    D --> E[Recompute canonical + verify HMAC]
    E -->|MAC sai| X[401; không claim nonce]
    E -->|MAC đúng| F[Validate signed timestamp freshness]
    F -->|Expired/future/malformed| X
    F -->|Hợp lệ| G[Atomic claim nonce trong shared Redis]
    G -->|Key đã tồn tại| R[401 replay; không handler]
    G -->|Store unavailable| U[503 fail closed; không handler]
    G -->|Claim thành công| H[Tạo Authentication từ verified key record]
    H --> I{Authorization}
    I -->|403 thiếu quyền| J[403; không handler]
    I -->|Đủ quyền| K[Handler + business idempotency]
~~~

**Bất biến quan trọng:**

~~~text
Nếu business handler được thực thi:
  MAC đã hợp lệ
  AND key/profile đang được server cho phép
  AND timestamp còn trong window
  AND nonce đã được claim thành công nguyên tử
  AND principal có đủ quyền trên effective resource.
~~~

Có thể kiểm tra cú pháp và timestamp sớm hơn để chặn input rác; nhưng **không được dùng nonce của request chưa xác thực để chặn request hợp lệ**, và không được tạo principal chỉ từ `X-Key-Id`.

**Vị trí authorization:** trong pipeline minh họa, nonce được claim **trước** kiểm tra quyền. Vì vậy request có HMAC hợp lệ nhưng thiếu quyền có thể tiêu thụ nonce rồi nhận 403. Đây là semantics hợp lệ nếu được ghi rõ; retry phải dùng nonce mới nhưng **không thể tự sửa lỗi thiếu quyền**. Không hoàn tác nonce claim chỉ vì downstream trả 403/500.

## 6. Thiết kế timestamp window và TTL một cách có chứng minh

Giả sử server chấp nhận timestamp `T` trong khoảng đối xứng:

\[
now-W \le T \le now+W
\]

với `W = 300 s` (5 phút). Hai biên đều được chấp nhận theo **hợp đồng ví dụ**.

### 6.1. Timestamp nào được nhận?

Giả sử server clock đang ở `2026-11-28T10:00:00Z`:

| Timestamp đã ký | Kết quả freshness |
|---|---|
| `09:54:59Z` | Hết hạn, từ chối |
| `09:55:00Z` | Đúng biên quá khứ, chấp nhận |
| `10:00:00Z` | Chấp nhận |
| `10:05:00Z` | Đúng biên tương lai, chấp nhận |
| `10:05:01Z` | Timestamp tương lai quá mức, từ chối |

Trong thực tế, lựa chọn window phải cân bằng clock skew thực tế, độ trễ mạng và replay exposure. Không tự động nới window chỉ để giảm 401.

### 6.2. Tại sao TTL = W chưa chắc đủ?

Một request có timestamp `T` được nhận **sớm nhất** khi server time là `T-W`, và có thể còn hợp lệ đến `T+W`. Khoảng giữa hai thời điểm dài **2W**.

Ví dụ:

~~~text
T                = 10:00:00 UTC
First accepted   = 09:55:00 UTC
Last acceptable  = 10:05:00 UTC
Window           = ±5 phút
Potential reuse interval = 10 phút
~~~

Nếu nonce được lưu chỉ 5 phút từ lần nhận đầu, nó sẽ hết TTL lúc 10:00 trong khi chữ ký có thể còn hợp lệ thêm 5 phút. Attacker có thể replay sau khi entry bị xóa.

**Chiến lược an toàn:**

1. Chọn TTL cố định ít nhất **`2W + safety margin`** để dễ phân tích; hoặc
2. Tính TTL từ **thời điểm hết hiệu lực thật của timestamp**:

~~~text
lastAcceptableTime = signedTimestamp + W
ttl = lastAcceptableTime - now + storageSlack
~~~

Ở cách 2, nonce được giữ đến sau thời điểm cuối mà request vẫn được chấp nhận. `storageSlack` là biên an toàn cho clock skew, độ trễ, độ chính xác TTL, replication; giá trị này phải được xác định theo vận hành thực và thời gian sống dữ liệu. Ví dụ lab dùng 2 giây chỉ để minh họa, **không phải** mặc định production.

### 6.3. Đồng hồ lệch giữa các replica

Nếu replica A chấp nhận timestamp tại biên sớm còn replica B chấp nhận tại biên muộn do clock skew, TTL cần xét cả độ lệch đã cho phép. Các node phải đồng bộ thời gian, theo dõi NTP/clock drift và có chính sách reject/fail closed khi không thể tin thời gian.

TTL không sửa được lỗi **nonce store bị mất dữ liệu/evict sớm**. Nếu Redis restart/failover khiến entry vừa claim biến mất trước khi signature hết hạn, replay có thể được nhận. Cần chọn persistence/replication/eviction policy phù hợp hoặc ngừng nhận request trong trường hợp không bảo đảm replay state.

## 7. Client: sinh nonce đúng cách

Với một profile dùng nonce ngẫu nhiên 128-bit, Java 17 có thể sinh 16 byte từ `SecureRandom` rồi đưa vào header ở dạng Base64URL không padding:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class HmacNonceGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    private HmacNonceGenerator() {}

    public static String freshNonce() {
        byte[] nonceBytes = new byte[16]; // 128 bits
        RANDOM.nextBytes(nonceBytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(nonceBytes); // 22 ASCII chars
    }
}
~~~

**Không dùng** timestamp một mình, `Random` không dành cho mật mã, auto-increment ID hoặc UUID tạo bằng hàm không bảo đảm entropy theo contract. `UUID.randomUUID()` dùng CSPRNG trên Java thông dụng, nhưng Base64URL của 16 random bytes có định dạng đơn giản hơn để kiểm tra ở ví dụ này.

Phía server không thể chứng minh nonce do client sinh có đủ entropy chỉ từ 22 ký tự. Hãy đảm bảo SDK chính thức sinh nonce đúng, phát hành test vector và giới hạn replay; không dựa vào “regex hợp lệ” làm bằng chứng ngẫu nhiên.

**Thứ tự ở client:**

~~~text
1. Chuẩn bị exact method, public URI/query, body bytes.
2. Tạo timestamp từ clock UTC, nonce mới từ CSPRNG.
3. Tạo canonical request bao gồm timestamp + nonce.
4. HMAC bằng secret của key ID/profile hiện hành.
5. Gửi đúng bytes/headers đã ký; không serialize body lại.
6. Khi retry, dùng timestamp/nonce mới và ký lại toàn bộ request.
7. Với lệnh ghi, giữ business idempotency key theo hợp đồng.
~~~

Một request được ký trước rồi đổi nonce trong header mà không ký lại sẽ bị từ chối vì MAC sai; đây là hành vi cần có.

## 8. Backend: tách replay policy khỏi storage

Để dễ kiểm thử và thay Redis, định nghĩa interface tối thiểu:

~~~java
import java.time.Duration;

public interface NonceClaimStore {
    /**
     * @return true nếu claim đầu tiên thành công, false nếu đã tồn tại.
     * @throws RuntimeException khi store không thể xác nhận atomic claim.
     */
    boolean claimOnce(
            String verifiedClientId,
            String nonce,
            Duration ttl);
}
~~~

**Điều kiện đầu vào:** `verifiedClientId` là định danh phía server sau khi HMAC được xác minh; nó không được lấy nguyên từ header tenant/role chưa xác thực. Nếu client ID chỉ unique trong tenant, scope phải bao gồm **verified tenant identity**. Interface không expose thao tác “check then insert” riêng, vì điều đó tạo race condition.

### 8.1. Triển khai Redis bằng SET NX PX

Với Spring Data Redis, một implementation minh họa:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class RedisNonceClaimStore implements NonceClaimStore {
    private final StringRedisTemplate redis;

    public RedisNonceClaimStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private static String replayKey(String clientId, String nonce) {
        // Length-prefix ngăn nhập nhằng khi ghép clientId với nonce.
        String material =
                clientId.length() + ":" + clientId + ":" + nonce;
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(material.getBytes(StandardCharsets.UTF_8));
            return "hmac:nonce:v1:" + HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException impossibleOnNormalJdk) {
            throw new IllegalStateException(
                    "Required SHA-256 unavailable",
                    impossibleOnNormalJdk);
        }
    }

    @Override
    public boolean claimOnce(
            String verifiedClientId, String nonce, Duration ttl) {
        if (ttl == null || ttl.isNegative() || ttl.isZero()) {
            throw new IllegalArgumentException("TTL must be positive");
        }
        String key = replayKey(verifiedClientId, nonce);
        // Spring Data Redis: SET key value NX PX theo Duration.
        Boolean created = redis.opsForValue()
                .setIfAbsent(key, "1", ttl);
        if (created == null) {
            throw new IllegalStateException(
                    "Nonce claim outcome unavailable");
        }
        return created;
    }
}
~~~

**Tính nguyên tử:** Redis xử lý kiểm tra key chưa tồn tại và set key+TTL như **một lệnh**; không viết `exists()` rồi `set()`. Redis store **phải dùng chung** giữa mọi replica nhận traffic cho cùng identity.

Ví dụ Redis CLI có ý nghĩa tương đương:

~~~text
SET hmac:nonce:v1:<sha256-of-scope-and-nonce> 1 NX PX 602000
~~~

Con số `602000 ms` minh họa `2×300s + 2s`; code ở bước tiếp theo tính TTL động theo timestamp. **Không dùng key Redis chứa raw secret hoặc toàn bộ request**. Hash của verified scope và nonce tạo key có độ dài cố định, giảm rò rỉ và tránh Redis key quá dài; không dùng `X-Key-Id` chưa verified làm namespace tenant.

**Cảnh báo failover:** một lệnh SET thành công trên node cũ nhưng chưa replicate trước failover có thể bị mất ở Redis cấu hình replication bất đồng bộ. Nếu yêu cầu replay protection nghiêm ngặt qua failover, phải đánh giá consistency/durability, topology, cơ chế fencing/replication acknowledgement và thiết kế fail-closed tương ứng; `SET NX PX` đơn lẻ không tự chứng minh exactly-once xuyên mọi thảm họa.

### 8.2. Chính sách TTL, memory eviction và namespace

Redis cần cấu hình memory headroom và eviction policy không khiến nonce keys bị xóa trước khi timestamp hết hiệu lực. Nếu Redis memory pressure làm eviction các entry replay, hệ thống có thể chấp nhận lại request cũ. Cần đo memory, quota, eviction counters, TTL và error rate; alert khi sắp mất khả năng giữ state.

Khi thay đổi cách đặt key (`hmac:nonce:v1:...` → `v2`), **không tự ý xóa namespace cũ** trong lúc còn request được ký còn hợp lệ. Một thay đổi encoding của nonce cũng cần test các biểu diễn tương đương để tránh duplicate detection lệch.

## 9. Java 17: ReplayGuard kiểm tra timestamp rồi claim

Code dưới tách logic thời gian khỏi Redis để có thể unit test bằng `Clock.fixed`.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.Base64;
import java.util.regex.Pattern;

public final class ReplayGuard {
    private static final Pattern NONCE_TOKEN =
            Pattern.compile("[A-Za-z0-9_-]{22}");

    private final Clock clock;
    private final Duration window;
    private final Duration storageSlack;
    private final NonceClaimStore store;

    public static final class ReplayRejected extends RuntimeException {
        public ReplayRejected() {
            super("Invalid freshness or replay"); // public 401 chung
        }
    }

    public ReplayGuard(
            Clock clock,
            Duration window,
            Duration storageSlack,
            NonceClaimStore store) {
        if (window.isNegative() || window.isZero()
                || storageSlack.isNegative() || storageSlack.isZero()) {
            throw new IllegalArgumentException("Invalid replay durations");
        }
        this.clock = clock;
        this.window = window;
        this.storageSlack = storageSlack;
        this.store = store;
    }

    public void assertFreshAndClaim(
            String verifiedClientId,
            String rawTimestamp,
            String rawNonce) {

        // Adapter đã kiểm tra các headers là singleton, length bounded.
        Instant signedAt;
        try {
            signedAt = Instant.parse(rawTimestamp);
        } catch (DateTimeParseException | NullPointerException invalid) {
            throw new ReplayRejected();
        }
        // Profile này bắt buộc UTC dạng canonical Instant.toString().
        if (!signedAt.toString().equals(rawTimestamp)) {
            throw new ReplayRejected();
        }
        if (rawNonce == null
                || !NONCE_TOKEN.matcher(rawNonce).matches()) {
            throw new ReplayRejected();
        }
        byte[] nonceBytes;
        try {
            nonceBytes = Base64.getUrlDecoder().decode(rawNonce);
        } catch (IllegalArgumentException malformed) {
            throw new ReplayRejected();
        }
        if (nonceBytes.length != 16
                || !Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(nonceBytes).equals(rawNonce)) {
            throw new ReplayRejected();
        }

        Instant now = clock.instant();
        if (signedAt.isBefore(now.minus(window))
                || signedAt.isAfter(now.plus(window))) {
            throw new ReplayRejected();
        }
        Duration ttl = Duration
                .between(now, signedAt.plus(window))
                .plus(storageSlack);
        if (ttl.isNegative() || ttl.isZero()) {
            throw new ReplayRejected();
        }

        // Chỉ được gọi khi MAC đã verify; false = replay.
        // Nếu Redis throw/unknown result: caller chuyển thành 503,
        // tuyệt đối KHÔNG biến exception thành "true".
        if (!store.claimOnce(verifiedClientId, rawNonce, ttl)) {
            throw new ReplayRejected();
        }
    }
}
~~~

**Giới hạn có chủ đích:**

- `window` và `storageSlack` lấy từ **cấu hình tin cậy**, không lấy từ HTTP header. Ví dụ lab: 300s và 2s.
- `verifiedClientId` không được `null` trong luồng gọi thực tế; adapter phải yêu cầu verified key record/principal trước khi gọi.
- Timestamp parse strict và canonical string là quy tắc **profile này**; profile dùng epoch seconds, precision khác hay offset khác cần parser/vector riêng.
- `ReplayRejected` chỉ đại diện credential/freshness rejection (thường 401); lỗi kho Redis cần được phân loại **unavailable** và trả 503 qua Spring Security/HTTP error handler.
- Kiểm tra thời gian nên diễn ra gần lúc claim. Nếu request phải chờ queue lâu, không nên dựa vào timestamp đã được kiểm tra quá sớm.
- Khi dùng clock/TTL giữa nhiều node, phải cộng thêm biên vận hành và kiểm chứng theo latency/skew thực; 2 giây ở lab không chứng minh đủ cho production.

### 9.1. Vì sao lưu nonce theo client, không theo key ID?

Trong thời gian key rotation, cùng một client có thể ký bằng K1 và K2. Nếu anti-replay namespace chỉ là `keyId + nonce`, cùng nonce có thể đi qua cả hai key. Khi policy yêu cầu nonce unique trên **client identity**, scope theo client đã xác minh giúp bảo vệ xuyên key version.

Tuy nhiên nếu hệ thống cho phép một client có nhiều independent applications/tenants, scope phù hợp có thể là `verifiedTenantId + verifiedClientId + nonce` hoặc một identity server-owned khác. **Đừng vô tình dùng cùng namespace toàn cục cho mọi client** và khiến nonce trùng của hai đối tác khác nhau chặn nhau.

Nonce scope giải quyết **reuse của nonce**, không giải quyết hai request khác nonce cùng thực hiện một payment; tầng nghiệp vụ vẫn cần idempotency.

## 10. Tích hợp vào Spring Security: đúng thứ tự và đúng lỗi

Một authentication service có thể điều phối:

~~~java
// Pseudocode tích hợp: interfaces và HTTP adapter do dự án cung cấp.
public VerifiedPrincipal authenticate(SignedHttpRequest request) {
    validateSingletonAndBoundedHeaders(request);
    validateProtectedRouteAndBodySize(request);

    KeyRecord key = keyRepository.resolve(request.keyId());
    // Unknown/revoked/expired/profile disallowed -> 401.
    // Store unavailable -> 503; không coi timeout là NOT_FOUND.

    byte[] exactBody = request.exactBodyBytes();
    String canonical = canonicalizer.forTrustedPublicTarget(
            request, exactBody);
    if (!hmacVerifier.matches(
            key.secretBytes(), canonical, request.signature())) {
        throw genericUnauthorized();
    }

    // Lúc này client identity dựa trên key đã verify.
    replayGuard.assertFreshAndClaim(
            key.verifiedClientId(),
            request.timestamp(),
            request.nonce());

    return principalFactory.fromVerifiedKey(key);
}
~~~

**Đây là pseudocode**, không phải method có đầy đủ class/import. Tham số `SignedHttpRequest` phải bảo toàn raw canonical fields và exact body bytes. Nếu API ký signed headers khác, phải bổ sung chúng vào canonicalizer; đừng chỉ ký path/body mà bỏ trường khác của hợp đồng.

### 10.1. Spring MVC/Servlet

Tích hợp vào `OncePerRequestFilter` hoặc `AuthenticationProvider` tùy kiến trúc. Khi authentication thành công, đặt `Authentication` vào `SecurityContext` rồi cho filter chain đi tiếp. Khi thất bại, dùng `AuthenticationEntryPoint`; không để handler chạy trước khi replayGuard hoàn tất.

Một điểm dễ sai: HMAC filter đọc `ServletInputStream` để hash body rồi controller không còn gì để đọc. `ContentCachingRequestWrapper` mặc định **không tự cung cấp stream replay** sau khi filter đã consume. Cần cơ chế body buffering/replay có giới hạn hoặc streaming digest phù hợp.

### 10.2. Spring WebFlux

`ServerWebExchange` và `Flux<DataBuffer>` yêu cầu xử lý bất đồng bộ. Nếu dùng Redis reactive, triển khai `ReactiveStringRedisTemplate` hoặc client reactive với primitive NX + TTL; **không block event loop** bằng `StringRedisTemplate`/`block()`. Khi consume body, quản lý pooled buffers và decorate request để downstream đọc được bytes theo contract.

Ở cả hai stack, **mọi protected route** phải đi qua HMAC verifier và replayGuard; đừng để alias path, gateway rewrite hay multiple security chains tạo `permitAll` fallback.

### 10.3. 401, 403 và 503

| Điều kiện | HTTP minh họa | Quy tắc |
|---|---|---|
| MAC không khớp, key unknown/revoked | **401** | Credential invalid; không lộ key existence |
| Timestamp ngoài window hoặc nonce replay | **401** | Không chạy handler, không disclose nonce state |
| Header timestamp/nonce malformed | **400/401** theo contract | Từ chối trước side effect |
| HMAC hợp lệ nhưng thiếu authority/tenant access | **403** | Authentication thành công, authorization thất bại |
| Redis/nonce store/key store unavailable | **503** | Không thể xác minh an toàn; fail closed |
| Request body quá lớn | **413** | Không buffer vô hạn |

Response 401 cần challenge `WWW-Authenticate` phù hợp với scheme do API định nghĩa. Không trả “nonce N của client A đã tồn tại”, secret, expected MAC hoặc canonical bytes nhạy cảm cho caller.

## 11. Unit tests với Clock.fixed và fake atomic store

Trước khi kết nối Redis, dùng fake store **cho test đơn JVM**:

~~~java
import java.time.Duration;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public final class FakeNonceClaimStore implements NonceClaimStore {
    private final Set<String> used = ConcurrentHashMap.newKeySet();
    private volatile boolean unavailable;

    @Override
    public boolean claimOnce(String clientId, String nonce, Duration ttl) {
        if (unavailable) {
            throw new IllegalStateException("NONCE_STORE_UNAVAILABLE");
        }
        return used.add(clientId.length() + ":" + clientId + ":" + nonce);
    }

    public void unavailable(boolean value) {
        this.unavailable = value;
    }

    public void reset() {
        used.clear();
        unavailable = false;
    }
}
~~~

Fake trên đảm bảo atomic claim trong JVM nhờ `ConcurrentHashMap.newKeySet().add(...)`, nhưng **không tự expire theo TTL** và không chứng minh Redis/failover nhiều replica. Cần test TTL/fault riêng bằng backend thật hoặc test clock/expiry store có kiểm soát.

### 11.1. Test request mới, replay và lỗi store

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ReplayGuardTest {
    private FakeNonceClaimStore store;
    private ReplayGuard guard;
    private static final String T = "2026-11-28T10:00:00Z";
    private static final String N = "AQIDBAUGBwgJCgsMDQ4PEA";

    @BeforeEach
    void setup() {
        store = new FakeNonceClaimStore();
        guard = new ReplayGuard(
                Clock.fixed(Instant.parse(T), ZoneOffset.UTC),
                Duration.ofSeconds(300),
                Duration.ofSeconds(2),
                store);
    }

    @Test
    void firstUseSucceedsButSecondUseFails() {
        assertDoesNotThrow(
                () -> guard.assertFreshAndClaim("client-a", T, N));
        assertThrows(ReplayGuard.ReplayRejected.class,
                () -> guard.assertFreshAndClaim("client-a", T, N));
    }

    @Test
    void sameNonceOnAnotherVerifiedClientIsIndependent() {
        guard.assertFreshAndClaim("client-a", T, N);
        assertDoesNotThrow(
                () -> guard.assertFreshAndClaim("client-b", T, N));
    }

    @Test
    void expiredTimestampIsRejected() {
        assertThrows(ReplayGuard.ReplayRejected.class,
                () -> guard.assertFreshAndClaim(
                        "client-a", "2026-11-28T09:54:59Z", N));
    }

    @Test
    void futureTimestampIsRejected() {
        assertThrows(ReplayGuard.ReplayRejected.class,
                () -> guard.assertFreshAndClaim(
                        "client-a", "2026-11-28T10:05:01Z", N));
    }

    @Test
    void storeFailureMustNotBeTreatedAsSuccess() {
        store.unavailable(true);
        assertThrows(IllegalStateException.class,
                () -> guard.assertFreshAndClaim("client-a", T, N));
        // HTTP adapter phải map store failure -> 503, không 2xx.
    }

    @Test
    void malformedNonceIsRejected() {
        assertThrows(ReplayGuard.ReplayRejected.class,
                () -> guard.assertFreshAndClaim(
                        "client-a", T, "nonce-001"));
    }
}
~~~

Các test này cố định clock **trên server verifier**, không chỉ trong signer test. Không dùng `Thread.sleep` để chờ 5 phút; kiểm thử biên bằng cách inject clock hoặc advance thời gian trong fixture.

### 11.2. Test hai biên freshness

~~~java
@Test
void exactWindowBoundariesAreAccepted() {
    // Mã đặt trong ReplayGuardTest, dùng hai nonce khác nhau.
    String nonceA = "AQIDBAUGBwgJCgsMDQ4PEA";
    String nonceB = "ERITFBUWFxgZGhscHR4fIA";
    assertDoesNotThrow(() -> guard.assertFreshAndClaim(
            "client-a", "2026-11-28T09:55:00Z", nonceA));
    assertDoesNotThrow(() -> guard.assertFreshAndClaim(
            "client-a", "2026-11-28T10:05:00Z", nonceB));
}
~~~

Trong production, chuẩn nonce phải bao gồm ký tự/độ dài và phương pháp sinh đã chốt; hai chuỗi trên chỉ là fixture kiểm tra format. Test này không chứng minh ẩn số skew đa replica, nhưng bảo vệ semantics **inclusive boundary** của policy minh họa.

## 12. Race condition: làm sao chứng minh chỉ một claim thành công?

Một lỗi phổ biến:

~~~text
if (redis.get(key) == null) {
    redis.set(key, "1");
    allowRequest();
}
~~~

Khi hai request chạy song song:

~~~text
Replica A: GET nonce -> missing
Replica B: GET nonce -> missing
Replica A: SET nonce -> success
Replica B: SET nonce -> success
Both business handlers run!  # lỗi replay
~~~

Thao tác đúng là **atomic compare-and-set kiểu Redis SET NX PX**. Test cần phát hai request trùng signature/nonce cùng lúc, không thực thi request 1 rồi mới request 2 và gọi đó là race test.

### 12.1. JUnit concurrency test cho fake atomic store

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.Test;

class NonceClaimConcurrencyTest {
    @Test
    void twoThreadsCannotClaimSameNonceTwice() throws Exception {
        FakeNonceClaimStore store = new FakeNonceClaimStore();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            java.util.concurrent.Callable<Boolean> attempt = () -> {
                start.await();
                return store.claimOnce(
                        "client-a", "AQIDBAUGBwgJCgsMDQ4PEA",
                        Duration.ofMinutes(10));
            };
            Future<Boolean> first = pool.submit(attempt);
            Future<Boolean> second = pool.submit(attempt);
            start.countDown();
            int successes =
                    (first.get() ? 1 : 0) + (second.get() ? 1 : 0);
            assertEquals(1, successes);
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Test này kiểm tra interface fake, **chưa kiểm tra Redis hay nhiều pod**. Với Testcontainers/Redis integration, tạo **một Redis dùng chung**, hai `ReplayGuard`/hai server contexts, phát đồng thời signed requests và assert đúng một nonce claim, tối đa một handler invocation.

### 12.2. Test tích hợp Redis thật

Kịch bản:

~~~text
Given:
  Redis thật trong Testcontainers hoặc staging
  2 application instances A/B, cùng nonce namespace
  key active, MAC hợp lệ, timestamp trong window
  nonce N chưa được claim

When:
  gửi đồng thời 2 request giống nhau qua A và B

Then:
  exactly one claim succeeds
  at most one request reaches protected handler
  other request is rejected as replay
  TTL nonce > 0 and covers remaining accepted time
~~~

Nếu **cả hai** request bị 401 do MAC sai hay timestamp hết hạn, test **không PASS**; nó chưa chứng minh atomic replay protection. Nếu cả hai request được phép qua handler, đó là **security failure**.

## 13. Test TTL thực tế và thời điểm mất state

Fake store không expire key nên cần test backend TTL riêng:

| Tình huống | Cách thử | Expected |
|---|---|---|
| Request ở biên quá khứ `T=now-W` | Claim nonce với TTL động | Entry còn tồn tại trong biên slack |
| Request ở biên tương lai `T=now+W` | Claim nonce | TTL gần `2W+slack` |
| TTL đã hết **sau** khi timestamp hết hạn | Gửi replay với cùng signed T | Freshness từ chối, dù key Redis đã mất |
| TTL mất **trước** khi timestamp hết hạn | Giả lập eviction sớm | Test phải FAIL/alert, không coi là replay-safe |
| Redis restart/failover | Làm trong staging, kiểm tra state còn | Không chấp nhận replay nếu còn trong window |
| Đồng hồ replica lệch | Controlled clocks và shared Redis | Không có khoảng tái sử dụng do TTL ngắn |

Một tối ưu có thể dùng TTL dựa trên `signedAt + window` và margin, nhưng phải kiểm thử với **precision của Redis client** (ms vs seconds) và độ chính xác timestamp. Không dùng negative TTL/zero TTL, không cache nonce ở local map khi Redis mất kết nối để “duy trì khả dụng” trên nhiều replica.

**Lưu ý:** khi thời gian đã vượt window, request với timestamp cũ phải bị từ chối **ngay cả nếu Redis không còn nonce entry**. Anti-replay là tổ hợp **freshness + nonce**, không phải TTL store một mình.

## 14. Kết hợp với key rotation và signature migration

Giả sử client có key K1 và K2 trong giai đoạn rotation:

~~~text
K1 (active during overlap) -> verified client = partner-a
K2 (active during overlap) -> verified client = partner-a
                    |
                    v
          shared nonce scope = partner-a
~~~

Kiểm thử:

1. Với K1, ký request dùng nonce N, server chấp nhận lần đầu.
2. Với K2, ký lại **một request hợp lệ về mật mã** dùng đúng N, timestamp trong window.
3. Khi policy yêu cầu nonce unique theo verified client, request K2 phải bị chặn bởi replay, **không** nhận 2xx lần hai.
4. K1 revoked → request ký bằng K1 phải bị từ chối dù MAC đúng.
5. K2 active → request mới với nonce khác vẫn hợp lệ.

Nếu V1/V2 profile có namespace riêng, phải đánh giá **cross-version replay** và tránh phân vùng nonce vô ý. Đừng dùng thuật toán fallback: nếu client bị buộc `v2-required`, V1 phải bị từ chối dù MAC và nonce đều còn hợp lệ.

Key được chọn từ `X-Key-Id` chỉ là hint; principal/tenant/authorities phải lấy từ **verified key record**. Không đưa raw key ID/nonce thành metric label high-cardinality.

## 15. Qua gateway/proxy: nonce đúng nhưng request có thể vẫn sai

Gateway có thể đổi path, reorder query, thay signed headers hoặc đọc/serialize lại body. Nếu verifier nhận canonical khác client, HMAC sai. Nếu **verifier ký một URI nhưng router thực thi URI khác**, đó còn có thể là route-confusion vulnerability.

**Test qua ingress thực:**

- Client ký public method/path/query theo contract, gửi qua gateway rewrite; request hợp lệ vẫn được chấp nhận.
- Đổi signed path/query/header/body **sau khi ký**, giữ MAC/nonce mới: request bị từ chối, **nonce không bị claim** nếu policy claim sau MAC.
- Gửi `X-Original-URI`/`X-Forwarded-*` giả từ client; gateway strip/overwrite metadata, service không coi header giả là trusted signed target.
- Encoded slash `%2F`, dot segments `%2e`, double encoding `%252F` và duplicate query không bypass HMAC hoặc authorization.
- Hai replica sau gateway cùng dùng Redis nonce store; replay qua replica khác vẫn bị từ chối.

Trên Servlet, body capture không được làm controller mất stream; trên WebFlux phải giữ nguyên bytes và không block event loop. Không dùng workaround bỏ path/body khỏi canonical để làm test xanh.

## 16. HTTP contract test: 401 không đủ để kết luận replay PASS

Một integration test phải quan sát:

~~~text
Request A: MAC valid, fresh timestamp, nonce N
    -> 2xx, exactly one handler execution

Request B: exact same request A (same MAC, N, T)
    -> 401 replay, zero additional handler executions

Request C: same client, fresh nonce N2, new signature
    -> 2xx if allowed, subject to business idempotency

Request D: bad MAC, nonce N3 not previously used
    -> 401, nonce N3 NOT claimed

Request E: valid MAC, principal lacks permission
    -> 403, zero protected handler executions

Request F: valid MAC, nonce store unavailable
    -> 503, zero protected handler executions
~~~

**D không được tạo false positive:** nếu nonce N3 bị claim trước khi MAC được xác minh, attacker có thể làm request hợp lệ với N3 bị chặn. **E** có thể vẫn claim nonce theo thiết kế của mục 5; đây không phải lỗi nếu policy ghi rõ. **F** phải fail closed, không được trả 2xx vì “nếu Redis chết thì bỏ qua nonce”.

### 16.1. Gợi ý MockMvc/WebTestClient

Với Spring MVC, `MockMvc` có thể kiểm tra filter chain nếu bật security filters. Với WebFlux, `WebTestClient` nên đi qua `SecurityWebFilterChain` thực. Không dùng `@WithMockUser` để mô phỏng xác thực HMAC trong **test replay**; nó có thể bypass toàn bộ verifier.

Một bộ test production-level nên dùng HTTP client thực qua ingress/proxy và có business spy/DB assertion. Với endpoint tạo thanh toán, dùng **fixture read-only hoặc transaction test** thay vì tạo giao dịch thật trên production.

### 16.2. Tách 401 do MAC, timestamp và replay

Khi kiểm thử changed path/body/query:

1. Tạo **nonce mới chưa claim**.
2. Dùng timestamp hợp lệ, key active và secret đúng.
3. Ký request gốc theo đúng canonical.
4. Chỉ mutate một signed field khi gửi.
5. Assert 401 **vì MAC mismatch** bằng audit reason nội bộ (không đưa ra response công khai).

Khi kiểm thử replay:

1. Gửi một request hợp lệ để nó được **chấp nhận và claim**.
2. Gửi lại **nguyên signed request** khi timestamp vẫn trong window.
3. Assert rejected reason nội bộ là replay và handler không tăng side effect.

Nếu test replay nhận 401 vì clock của test đã chạy quá window, bài test chưa kiểm tra nonce store.

## 17. Observability và runbook vận hành

### 17.1. Metrics nên xuất

| Metric | Nội dung | Lưu ý |
|---|---|---|
| `hmac_auth_total` | accepted/rejected/unavailable | Route template và enum outcome hữu hạn |
| `hmac_replay_rejected_total` | Request bị từ chối do nonce trùng | Chỉ tăng khi HMAC/freshness hợp lệ |
| `hmac_timestamp_rejected_total` | Expired/future/malformed | Phân loại reason an toàn |
| `hmac_nonce_claim_duration_seconds` | p95/p99 latency Redis claim | Histogram, không tag nonce |
| `hmac_nonce_store_errors_total` | Timeout/unavailable/null result | Không gộp thành credential invalid |
| `hmac_nonce_ttl_seconds` | TTL được cấp/đo trong test | Không log raw nonce key |
| `hmac_key_lookup_total` | Found/not-found/unavailable | Không expose key existence ra bên ngoài |
| `hmac_authz_denied_total` | MAC đúng nhưng không đủ quyền | 403 và không handler |

**Không sử dụng** raw nonce, signature, body hash, key ID chưa verified, raw tenant header hoặc full URL/query làm metric label. Chúng có thể nhạy cảm và gây **cardinality explosion** khi attacker gửi input ngẫu nhiên.

### 17.2. Alert và response an toàn

- Replay rejection tăng: kiểm tra retries, SDK nonce reuse, traffic bất thường; đừng mặc định là tấn công đã thành công.
- Timestamp expired/future tăng: xem NTP, client clocks, queue delay; không nới window tùy tiện.
- Redis claim latency tăng: xem network, saturation, connection pool, memory/evictions.
- Key/nonce store unavailable: **fail closed**; liên hệ on-call, không bypass HMAC/replay.
- Nhiều 401 ngay sau gateway deploy: kiểm tra canonical public URI và signed headers, không đổi signature contract âm thầm.
- Nếu nonce keys bị evict/mất do failover: đánh giá replay exposure, incident scope và giao dịch có thể bị xử lý lặp.

Khi nghi replay đã gây side effect, điều tra bằng **business transaction audit**, idempotency records, event IDs, DB writes và downstream traces được bảo vệ; không chỉ xem số lượng HTTP 2xx.

## 18. Các lỗi triển khai nên cố tình cài để chứng minh test đủ mạnh

| Bug được mô phỏng ở staging | Hậu quả | Test phải bắt |
|---|---|---|
| `GET` rồi `SET`, không atomic | Hai replica có thể cùng claim | Concurrency integration |
| Nonce claim trước MAC | Attacker chiếm nonce hợp lệ | Invalid MAC không làm tăng claimed nonce |
| TTL chỉ `W` với timestamp ±`W` | Replay sau expiry trong khi signature còn hạn | TTL boundary |
| Nonce store map local theo pod | Replay qua pod khác được nhận | Multi-replica E2E |
| Redis down thì catch và trả true | Fail-open | Store-unavailable 503 |
| Cache nonce bị eviction sớm | Replay trong window | Redis memory/failover test |
| Scope theo key ID khi rotation | Cross-key reuse | K1/K2 same client + same nonce |
| Client dùng nonce tăng dần | Dễ dự đoán/collision khi restart | Client SDK contract tests |
| Nonce không nằm trong HMAC input | Attacker thay nonce giữ MAC | Changed-nonce negative test |
| Timestamp không nằm trong HMAC input | Attacker sửa freshness | Changed-timestamp negative test |
| 401 sau handler invocation | Side effect trước từ chối | Handler/DB/event assertions |
| 403 bị coi là authn failure và bỏ kiểm quyền | Cross-resource access | Authorization test |
| Gateway trust raw forwarded header | Path/method confusion | Header spoofing E2E |
| Retry với nonce khác tạo 2 payment | Idempotency thiếu | Business idempotency test |

Đây là các **mutation/fault tests trong môi trường được phép**. Không cố tình đưa những bug này lên production để “xem có bị khai thác hay không”.

## 19. Ma trận nghiệm thu theo môi trường

| Kiểm thử | Unit | Staging/integration | Production an toàn |
|---|---|---|---|
| Nonce generator định dạng/uniqueness | Có | Có | SDK telemetry an toàn |
| Golden HMAC+nonce vector | Có | Có | Synthetic signed probe |
| Timestamp boundary bằng fixed clock | Có | Có | Theo health clock/NTP |
| First-use và replay tuần tự | Có | Có qua HTTP | Chỉ probe no-op được duyệt |
| Invalid MAC không claim nonce | Có | Có | Probe có giới hạn |
| Redis NX+TTL atomic | Không chứng minh bằng fake | **Bắt buộc Redis thật** | Theo metrics/health |
| Multi-replica same nonce | Fake threads | **Hai replica+shared Redis** | Không tạo giao dịch thật |
| TTL/Redis eviction/failover | Mô hình | **Fault injection staging** | Monitoring/chaos được phê duyệt |
| Key rotation/cross-key replay | Có | Có | Synthetic keys scope riêng |
| Gateway/path/query/header mutation | Adapter tests | Proxy thật | Spot-check được phép |
| Authn 401 vs authz 403 | Có | Security chain thật | Synthetic restricted route |
| Store down → fail closed | Fake exception | Redis network fault | Không ngắt Redis live tùy tiện |
| Idempotency với retry nonce mới | Có | Business integration | Không tạo lệnh ghi thật |

**Không tuyên bố đạt multi-replica replay protection từ unit test sử dụng `ConcurrentHashMap`.** Thư viện in-memory chỉ chứng minh atomicity trong một JVM; Redis cluster/failover và cấu hình network là những ranh giới khác.

## 20. Checklist bàn giao dự án thực hành

### 20.1. Phần chức năng

- [ ] Client SDK sinh nonce 16 byte CSPRNG → Base64URL 22 ký tự không padding.
- [ ] Timestamp UTC/nonce là **signed fields** của canonical request, không chỉ header đứng ngoài HMAC.
- [ ] Server parse strict, giới hạn header length/duplication, khóa/profile còn hiệu lực.
- [ ] Canonical method/path/query/body đi qua gateway mà không lệch nghĩa.
- [ ] HMAC được verify **trước khi claim nonce**; không tạo Authentication khi MAC sai.
- [ ] Freshness window có chính sách biên rõ, server clock được inject và đồng bộ.
- [ ] Nonce scope dựa trên **verified identity**, phù hợp key rotation/multi-tenant.
- [ ] Redis claim dùng **một thao tác atomic NX + TTL**, không check-then-set.
- [ ] TTL bao phủ toàn bộ thời gian signature còn hợp lệ, kể cả timestamp ở biên tương lai.
- [ ] Redis timeout/null/eviction bất thường không dẫn đến bypass; fail closed.
- [ ] Authentication và authorization là hai bước riêng; 403 không tạo side effect.
- [ ] Business write có idempotency riêng, không coi replay nonce là exactly-once delivery.

### 20.2. Phần kiểm thử và vận hành

- [ ] Có golden vector cố định của MAC chứa timestamp và nonce.
- [ ] Unit tests cho success/replay, timestamp boundary, nonce malformed và store unavailable.
- [ ] Test invalid MAC với nonce mới xác minh nonce **không bị chiếm trước khi verify**.
- [ ] Concurrency test trên fake **và** Redis thật qua ít nhất hai instance.
- [ ] TTL/failover/eviction test chứng minh không có khoảng replay khi timestamp còn valid.
- [ ] Có test K1/K2 rotation, V1/V2 policy, cross-version nonce nếu áp dụng.
- [ ] Có test qua gateway với signed path/query/header/body và header spoofing.
- [ ] Mỗi request bị từ chối đều có assertion **không handler/DB write/event/downstream side effect**.
- [ ] Metrics dùng reason enums/route templates, không log secret, nonce, signature hoặc raw PII.
- [ ] Có rollback/runbook không xóa nonce history, không tắt HMAC hoặc nới window tùy tiện.
- [ ] Thử readiness/latency/503 khi nonce store xuống và cách phục hồi an toàn.

## 21. Bài tự đánh giá: bốn tình huống thực tế

**Tình huống A.** Window ±5 phút, nonce Redis TTL chỉ 5 phút. Request có timestamp T được nhận lúc T-5 phút. Có thể replay lúc T+1 phút không?

**Đáp án:** Có nguy cơ. Redis entry có thể đã hết TTL lúc T, trong khi T+1 phút vẫn nằm trong window đến T+5 phút. Cần TTL bao phủ ít nhất đến khi signed timestamp hết hạn, cộng biên vận hành.

**Tình huống B.** Kẻ tấn công biết nonce N trong một request hợp lệ, gửi một request có MAC sai nhưng nonce N trước người dùng. Nếu người dùng bị 401 replay, bug ở đâu?

**Đáp án:** Nonce đã bị claim **trước MAC hợp lệ** hoặc namespace/reason bị xử lý sai. HMAC phải được verify trước khi đưa nonce vào store; request giả không được chiếm nonce.

**Tình huống C.** Hai request thanh toán giống nhau được ký bằng hai nonce khác nhau, cùng secret, MAC đều đúng. ReplayGuard có ngăn được giao dịch thứ hai?

**Đáp án:** Không. Anti-replay ngăn **nonce reuse**; hai nonce khác nhau là hai request hợp lệ về xác thực. Phải có **business idempotency key** hoặc deduplication ở tầng nghiệp vụ.

**Tình huống D.** Trong lúc rotate K1→K2, cùng client dùng lại nonce N với hai key. Redis key là `keyId + nonce`. Rủi ro gì?

**Đáp án:** Hai namespaces khác nhau nên cả hai có thể claim thành công. Nếu chính sách muốn nonce duy nhất trên client identity, dùng scope **verified client** xuyên key versions và kiểm tra cross-profile replay trong giai đoạn overlap.

## 22. Tổng kết

Thêm **replay protection** không phải chỉ thêm `X-Nonce` vào request và ghi vài giá trị vào cache. Một hệ thống đúng phải kết hợp **HMAC ràng buộc timestamp/nonce**, kiểm tra freshness bằng server clock, **atomic claim** trong kho nonce dùng chung giữa các replica, TTL đủ lớn cho toàn bộ cửa sổ hợp lệ và **fail closed** khi không thể xác minh state.

Trong dự án thực hành này, kết quả đạt yêu cầu khi request mới được xác thực/phân quyền đúng, request phát lại bị chặn **trước side effect**, và test phân biệt được **MAC sai, timestamp sai, nonce trùng, key revoked, thiếu quyền và store unavailable**. Cần tiếp tục giữ canonical request nhất quán qua proxy, key rotation an toàn và **idempotency nghiệp vụ** riêng. Replay protection tốt là kiểm soát *sử dụng lại thông điệp đã ký*, không phải lời hứa rằng mọi tác vụ phân tán chỉ có thể xảy ra đúng một lần.
