# Nonce expiration

Trong xác thực HTTP request bằng HMAC, **nonce** (*number used once*) là giá trị gắn với một request nhằm giúp server phát hiện việc **phát lại (replay)** một request đã được ký trước đó. Khác với chữ ký HMAC, nonce không tự xác minh tính toàn vẹn; nó cần được **đưa vào canonical request được ký** và được server theo dõi bằng một kho lưu trạng thái có tính nguyên tử.

**Nonce expiration** là chính sách xác định **server phải nhớ một nonce đã được dùng trong bao lâu**. Thời hạn lưu không nên được chọn tùy tiện hoặc đồng nhất máy móc với TTL của cache. Một nonce bị xóa quá sớm có thể cho phép một **signed request vẫn nằm trong cửa sổ timestamp hợp lệ** được chấp nhận lần nữa. Lưu quá lâu lại tăng chi phí bộ nhớ, có thể gây quá tải replay store và làm khó vận hành.

Bài học thuộc chương **Nonce**, mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Mô-đun thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request chứa method, URI, header và/hoặc body theo hợp đồng ký; đồng thời cần quản lý key rotation, kiểm thử proxy/gateway và phân biệt authentication với authorization.

> **Nguyên tắc cốt lõi:** Một nonce đã dùng phải tiếp tục được ghi nhớ **trong suốt khoảng thời gian mà bất kỳ bản phát lại của signed request tương ứng còn có thể vượt qua kiểm tra freshness**. Việc key trong Redis tự hết hạn chỉ an toàn khi lúc đó request cũng đã **hết khả năng được chấp nhận theo timestamp/key policy**, kể cả sai lệch đồng hồ và giới hạn triển khai.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **nonce uniqueness**, **nonce lifetime**, **request timestamp freshness**, **cache TTL** và **idempotency**.
2. Giải thích vì sao xác minh HMAC thành công không tự ngăn replay.
3. Suy ra cửa sổ chấp nhận của một signed timestamp và tính giới hạn lưu nonce tương ứng.
4. Phát hiện lỗi **TTL bằng max-age nhưng bỏ qua allowed future skew**.
5. Thiết kế replay key namespace theo audience và credential/key ID để tránh va chạm hoặc bypass giữa dịch vụ.
6. Sử dụng thao tác **atomic insert-if-absent kèm expiration** trong một kho trạng thái dùng chung.
7. Viết Java 17 để kiểm tra timestamp, nonce format, chính sách expiration và các trường hợp biên.
8. Xử lý clock drift, multiple nodes, Redis eviction, store outage, retries và key rotation.
9. Xây dựng unit tests, concurrency tests và end-to-end tests qua gateway, đồng thời tách authentication khỏi authorization.

## 2. Vị trí của nonce trong HTTP request đã ký

Một HTTP request minh họa:

~~~http
POST /v1/orders?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1800000030
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <hmac-sha256-base64url-tag>

{"orderId":"order-42","amount":125000}
~~~

Một canonical request minh họa được tạo từ method, canonical path/query, signed headers, audience và body digest:

~~~text
HMAC-REQUEST-V1
POST
/v1/orders
currency=VND
audience:orders-api
content-type:application/json
x-key-id:partner-a-k3
x-timestamp:1800000030
x-nonce:6bfb21974a08417199273b09ca49a3ec
body-sha256:<sha256-of-raw-body-hex>
~~~

Các dòng được nối bằng LF, encode UTF-8 và HMAC ký **đúng byte canonical request** theo contract. `X-Signature` chứa tag đầu ra, không nằm trong chính canonical bytes tạo ra tag đó.

**Vì timestamp và nonce đều được ký**, attacker không thể đơn giản thay `X-Nonce` hoặc `X-Timestamp` của một request đã capture mà vẫn giữ nguyên HMAC tag hợp lệ.

Tuy nhiên, nếu attacker gửi lại **toàn bộ** request cũ không thay đổi byte nào, HMAC vẫn khớp. Để phát hiện, server cần một replay store ghi nhận rằng **nonce này đã từng được chấp nhận**.

### 2.1. Nonce không phải secret

Trong hợp đồng ví dụ:

- Client sinh **16 byte ngẫu nhiên** từ nguồn CSPRNG.
- Client encode thành **32 ký tự hex chữ thường**.
- Server kiểm tra đúng định dạng.
- Nonce nằm trong signed metadata, có thể nhìn thấy trên HTTP request.
- Nonce phải **khó trùng trong phạm vi credential và khoảng hiệu lực**, không nhất thiết phải bí mật.
- Giá trị nonce chỉ trở thành dấu hiệu “đã dùng” khi server **ghi thành công** vào replay store theo chính sách.

Việc chuỗi nonce trông ngẫu nhiên không chứng minh nó chưa từng được dùng. Server phải theo dõi việc sử dụng.

### 2.2. Nonce và timestamp bổ trợ nhau

| Cơ chế | Chặn được gì? | Không tự giải quyết gì? |
| --- | --- | --- |
| HMAC của canonical request | Sửa method/URI/header/body đã ký mà không biết secret | Replay nguyên request |
| Signed timestamp | Request quá cũ hoặc vượt tương lai cho phép | Replay trong cửa sổ thời gian |
| Signed nonce + replay store | Request lặp lại cùng nonce trong phạm vi lưu trữ | Request mới dùng nonce mới nhưng lặp nghiệp vụ |
| Idempotency store | Thực hiện cùng event/operation nhiều lần theo business key | Không thay việc xác thực HMAC |
| Authorization | Principal có quyền thao tác resource hay không | Không tự bảo vệ tag hoặc replay |

**Nonce expiration** là điểm kết nối giữa timestamp freshness và replay store TTL.

## 3. Nonce expiration là gì?

Khi một signed request đã vượt HMAC verification, freshness checks và được chấp nhận, server ghi replay key:

~~~text
namespace: audience + keyId
nonce:     6bfb21974a08417199273b09ca49a3ec

replayKey: hmac-nonce:v1:orders-api:partner-a-k3:<nonce>
value:     seen
expiry:    do server quyết định
~~~

Nếu một request khác dùng cùng replay key **trước khi record hết hạn**, server từ chối nó là replay.

Nếu replay record đã hết hạn và bị loại bỏ, kho trạng thái có thể coi nonce là “chưa thấy”. Khi đó hệ thống **chỉ còn chặn request cũ nếu freshness/key policy đã bảo đảm request không thể chấp nhận nữa**.

Vì vậy có hai điều kiện thời gian riêng:

1. **Request validity window:** Cho đến khi nào timestamp/credential còn làm request có thể hợp lệ?
2. **Nonce retention window:** Đến khi nào server giữ replay record ngăn sử dụng lại cùng nonce?

Chính sách an toàn cần làm cho retention window **bao phủ đủ request validity window sau lần dùng đầu**, thay vì kết thúc trước nó.

### 3.1. Phân biệt ba khái niệm expiration

| Thuật ngữ | Thời điểm kết thúc | Tác dụng |
| --- | --- | --- |
| **Timestamp freshness** | Khi timestamp rơi ngoài cửa sổ tuổi request | Ngăn chấp nhận signed request quá cũ/tương lai |
| **Nonce retention / TTL** | Khi kho replay store được phép quên một nonce đã ghi | Ngăn dùng lại cùng nonce trong khoảng còn hiệu lực |
| **Credential expiration** | Khi key record hết hiệu lực hoặc bị thu hồi | Không cho credential tiếp tục xác thực request |

Không phải cứ Redis key đã hết TTL thì request tự động hết hạn. Ngược lại, nếu timestamp đã hết hạn, request cần bị từ chối **dù replay key đã bị xóa**.

## 4. Mô hình thời gian: max-age và future skew

Định nghĩa:

- `t_s`: signed timestamp của request, tính bằng Unix seconds.
- `t_now`: đồng hồ server tại thời điểm kiểm tra, cũng là Unix seconds.
- `A`: tuổi request tối đa được chấp nhận (**max past age**), ví dụ 300 giây.
- `F`: mức lệch tương lai tối đa cho phép (**max future skew**), ví dụ 30 giây.
- `M`: biên an toàn cho clock skew giữa nodes, độ trễ xử lý và sai số TTL/triển khai.

Một chính sách freshness phổ biến:

\[
t_{\mathrm{now}}-A \le t_s \le t_{\mathrm{now}}+F
\]

Tương đương, với **một signed timestamp đã cố định**:

\[
t_s-F \le t_{\mathrm{now}} \le t_s+A
\]

Nghĩa là request có thể được chấp nhận từ thời điểm server nhìn thấy nó **không quá xa trong tương lai** cho tới thời điểm server nhìn thấy timestamp **không quá cũ**.

**Điểm quan trọng:** Khoảng thời gian mà một signed timestamp có thể nằm trong cửa sổ freshness dài tối đa khoảng:

\[
A+F
\]

khi xét từ mép sớm nhất của cửa sổ đến mép muộn nhất. Vì vậy, giữ nonce đúng `A` giây tính từ lần chấp nhận đầu **có thể chưa đủ**.

### 4.1. Ví dụ cụ thể: TTL 300 giây là chưa đủ

Giả sử:

~~~text
maxPastAge       A = 300 giây
maxFutureSkew    F = 30 giây
serverNow        t0 = 1_800_000_000
signedTimestamp ts = 1_800_000_030
~~~

Ở thời điểm `t0`, timestamp của request nằm **30 giây trong tương lai**, đúng bằng ngưỡng được chấp nhận.

Request sẽ tiếp tục vượt kiểm tra freshness cho đến:

~~~text
lastFreshServerTime = ts + A
                    = 1_800_000_330
~~~

Nếu lần đầu nonce được ghi lúc `t0` với TTL chỉ **300 giây**:

~~~text
nonce record expires at 1_800_000_300
request freshness ends at 1_800_000_330
~~~

Xuất hiện khoảng **30 giây** trong đó:

- Replay record đã hết hạn.
- Signed request vẫn nằm trong cửa sổ timestamp chấp nhận.
- HMAC trên request gốc vẫn đúng.
- Nếu chỉ kiểm tra “nonce hiện có trong Redis hay không”, một bản replay có thể lọt qua.

Đây là một lỗi **nonce expiration quá sớm**.

### 4.2. TTL đủ dài trong ví dụ

Một chính sách đơn giản:

~~~text
maxPastAge           = 300 giây
maxFutureSkew        = 30 giây
safetyMargin         = 30 giây
nonceRetentionTtl    = 360 giây
~~~

Nếu nonce được ghi tại `t0`, key còn được lưu tới khoảng `t0 + 360`, sau thời điểm signed timestamp hết khả năng vượt freshness trong ví dụ (`t0 + 330`).

**360 giây chỉ là giá trị minh họa**, không phải con số an toàn cho mọi API. Phải xác định clock drift, dữ liệu time source, key TTL thực tế và biên vận hành của hệ thống trước khi chọn retention.

### 4.3. Công thức bảo thủ để chọn TTL cố định

Với request được chấp nhận khi `t_s ≤ t_now + F`, và còn fresh tới `t_s + A`:

\[
\text{nonceTtl} \ge A + F + M
\]

Đây là cách chọn **TTL cố định bảo thủ** từ thời điểm nonce được ghi, khi `M` đủ bao phủ clock skew giữa các node/store và các sai lệch triển khai liên quan.

Có thể dùng phương án chính xác hơn: tính **deadline lưu nonce** từ signed timestamp:

\[
\text{retainUntil} \ge t_s+A+M
\]

và chuyển deadline thành TTL dương tại lúc ghi. Nhưng phải xử lý overflow, ranh giới inclusive, chênh lệch clock và độ trễ từ lúc xác minh tới lúc store ghi. Với API thông thường, TTL cố định có biên an toàn có thể đơn giản và dễ kiểm toán hơn.

### 4.4. Không lấy TTL từ một header do client tự khai

Đừng làm:

~~~text
X-Nonce-TTL: 5
server.SET(replayKey, seen, EX 5)
~~~

Attacker có thể tự yêu cầu xóa nonce sớm hơn thời gian signed request còn hợp lệ. Dù trường TTL này được ký, client sở hữu secret cũng có thể cố tình ký một giá trị quá ngắn; **server phải áp dụng min retention theo policy của mình**.

Nếu contract hỗ trợ signed `expiresAt`, server vẫn cần kiểm tra tính hợp lệ, maximum lifetime, algorithm/key policy và ranh giới clock trước khi dùng giá trị đó để điều chỉnh retention.

## 5. Inclusive boundaries và giây cuối cùng

Phép kiểm tra:

~~~text
ts >= now - A
ts <= now + F
~~~

thường dùng dấu **bằng**, tức request ở đúng biên vẫn còn hợp lệ. Khi `now = ts + A`, request còn vượt qua freshness; chỉ khi đồng hồ vượt biên mới bị từ chối.

Vì vậy không nên thiết kế “nonce hết hạn chính xác tại `ts + A` rồi chắc chắn an toàn” nếu chính sách còn cho phép request ở đúng thời điểm đó, hoặc đồng hồ/expiry có độ phân giải khác nhau.

Cần thêm biên an toàn để tránh off-by-one, clock drift và sự khác biệt giữa Unix seconds integer với thời gian có phần lẻ. Không phụ thuộc vào việc store xóa key đúng nanosecond; nhiều hệ thống dùng TTL với độ phân giải giây/millisecond và xử lý expiration theo clock của store.

### 5.1. So sánh window bằng phép toán an toàn overflow

Tính trực tiếp `now - A` hoặc `now + F` trên số `long` không có giới hạn có thể overflow trong trường hợp input bất thường.

Một helper rõ ràng cần:

- Từ chối timestamp âm nếu contract chỉ cho Unix epoch seconds không âm.
- Parse timestamp canonical decimal, không nhận `+`, dấu cách hay số milliseconds nhầm seconds.
- Kiểm tra phép cộng/trừ với số lớn.
- Tính theo `Instant`/`Clock` hoặc số nguyên có giới hạn, không dùng thời gian local timezone.

## 6. Một hợp đồng NonceExpirationV1 có thể triển khai

Ví dụ cho service `orders-api`:

| Thành phần | Quy tắc |
| --- | --- |
| HMAC | HMAC-SHA256 full 32-byte tag, Base64URL no padding |
| Signed metadata | `X-Key-Id`, `X-Timestamp`, `X-Nonce` |
| Nonce format | 16 byte random → 32 ký tự lowercase hex |
| Timestamp | Unix epoch **seconds** dạng decimal canonical |
| Max past age | **300 giây** |
| Max future skew | **30 giây** |
| Retention safety margin | **30 giây** (ví dụ, phải kiểm định theo môi trường thật) |
| Replay key TTL | **360 giây**, cố định từ lúc ghi lần đầu |
| Replay namespace | protocol version + audience + key ID + nonce |
| Store semantics | Atomic insert-if-absent kèm TTL |
| Khi nonce đã tồn tại | Reject replay |
| Khi replay store không sẵn sàng | **Fail closed** đối với API nhạy cảm |
| Key policy | Đúng key ID, algorithm, audience và trạng thái còn hiệu lực |
| Authorization | Principal/action/resource/tenant được kiểm tra độc lập |

**Giới hạn của V1:** Các giá trị A/F/M minh họa, không phải tiêu chuẩn toàn cầu. Nếu các node có clock drift lớn hơn biên M, TTL 360 giây không còn chắc chắn bao phủ toàn bộ acceptance window. Phải có đồng bộ đồng hồ, vận hành có cảnh báo hoặc tăng margin hợp lý.

### 6.1. Namespace cần đủ thông tin

Một replay key có thể có dạng:

~~~text
hmac-nonce:v1:orders-api:partner-a-k3:6bfb21974a08417199273b09ca49a3ec
~~~

Tối thiểu nên đưa vào namespace:

- **Protocol version** để tránh chia chung namespace sai format.
- **Audience/service** để chống nhầm nonce giữa các service.
- **Credential/key ID** hoặc principal namespace được contract chỉ định.
- **Nonce** đã validate.

Không ghép chuỗi tự do chứa delimiter chưa kiểm soát. Nếu key ID/audience có ký tự bất kỳ, hãy encode length-prefix hoặc hash một cấu trúc đã được encode xác định. Không bao giờ tin một replay namespace tự khai từ client.

### 6.2. Key ID hay principal ID trong namespace?

Có hai lựa chọn:

- **Theo key ID:** Nonce chỉ cần unique dưới một credential cụ thể, phù hợp khi mỗi key ID có secret riêng và key ID được HMAC ký.
- **Theo principal ID:** Muốn cấm sử dụng cùng nonce trên nhiều credentials của một principal trong thời kỳ rotation.

Không có một lựa chọn đúng cho mọi hệ thống. Nhưng **phải xác định rõ scope** và sử dụng nhất quán ở client, server và test. Với V1, ta chọn **audience + key ID + nonce** vì mỗi key ID chọn chính xác một secret/key record; nếu muốn nonces unique xuyên các keys của một principal, phải thiết kế policy đó riêng.

### 6.3. Không reset TTL khi phát hiện replay

Nếu nonce đã tồn tại, request trùng phải bị từ chối và **không kéo dài TTL một cách tùy tiện**:

~~~text
first use  -> insert nonce with TTL
replay     -> exists -> reject, TTL giữ nguyên
~~~

Nếu mỗi replay gia hạn TTL, attacker có thể giữ key sống lâu bằng cách gửi lặp, tăng áp lực bộ nhớ và biến retention thành một chính sách khác với thiết kế ban đầu.

## 7. Java 17: tạo nonce đúng định dạng

Client cần tạo nonce mới cho mỗi signed request:

~~~java
import java.security.SecureRandom;
import java.util.HexFormat;

public final class NonceGeneratorV1 {
    private final SecureRandom random = new SecureRandom();

    public String newNonce() {
        byte[] bytes = new byte[16];
        random.nextBytes(bytes);

        // 16 byte -> 32 ký tự hex ASCII chữ thường.
        return HexFormat.of().formatHex(bytes);
    }
}
~~~

Điểm chính:

- `SecureRandom` là nguồn CSPRNG trong Java; không dùng `Math.random()` cho nonce bảo mật.
- Nonce không bắt buộc bí mật, nhưng phải đủ khó đoán/trùng trong namespace.
- Client không nên dùng nonce cố định từ ví dụ trong production.
- Nonce phải được đưa vào **canonical request đã ký** trước khi tính HMAC.
- Retry HTTP có thể cần **nonce mới và HMAC mới**, tùy idempotency policy.

### 7.1. Đừng dùng timestamp thay nonce

~~~text
Bad nonce: 1800000000
Bad nonce: requestCounterPerJvmWithoutSharedCoordination
Bad nonce: constant "abc"
~~~

Timestamp một mình không bảo đảm uniqueness khi nhiều requests cùng giây. Counter local có thể lặp sau restart hoặc khi nhiều instances chạy song song. Nếu chọn counter có phân vùng/định danh instance, phải phân tích tính unique bền vững và key lifecycle; CSPRNG 128-bit là lựa chọn đơn giản để bắt đầu.

## 8. Java 17: kiểm tra cửa sổ freshness an toàn

Ví dụ Java 17, phép tính theo Unix seconds:

~~~java
import java.time.Clock;
import java.util.regex.Pattern;

public final class SignedTimestampV1 {
    public static final long MAX_PAST_AGE_SECONDS = 300L;
    public static final long MAX_FUTURE_SKEW_SECONDS = 30L;

    private static final Pattern CANONICAL_DECIMAL =
            Pattern.compile("(0|[1-9][0-9]{0,18})");

    private SignedTimestampV1() {}

    public static long parse(String value) {
        if (value == null
                || !CANONICAL_DECIMAL.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid timestamp");
        }
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException tooLarge) {
            throw new IllegalArgumentException("Invalid timestamp");
        }
    }

    public static boolean isFresh(long signedTimestamp, Clock clock) {
        long now = clock.instant().getEpochSecond();

        if (signedTimestamp < 0 || now < 0) {
            return false;
        }

        try {
            long earliestAccepted =
                    Math.subtractExact(now, MAX_PAST_AGE_SECONDS);
            long latestAccepted =
                    Math.addExact(now, MAX_FUTURE_SKEW_SECONDS);

            return signedTimestamp >= earliestAccepted
                    && signedTimestamp <= latestAccepted;
        } catch (ArithmeticException overflow) {
            return false;
        }
    }
}
~~~

**Vì sao dùng `Clock`?**

- Cho phép unit tests với `Clock.fixed(...)`, không cần ngủ thật để chờ expiration.
- Mọi server có thể dùng UTC và epoch seconds, không phụ thuộc timezone hiển thị.
- Dễ mô phỏng timestamp quá cũ, vừa đúng biên và tương lai vượt skew.
- Production có thể cấp `Clock.systemUTC()` và giám sát sai lệch đồng hồ.

Trong production, kiểm tra timestamp lexical format và HMAC phải dùng **một representation thống nhất**. Không parse `001800000000` thành số rồi ký lại thành `1800000000` mà không có contract rõ; cách làm đó dễ tạo signer/verifier mismatch.

### 8.1. Thời gian local không phải Unix epoch seconds

Không dùng `LocalDateTime.now()` rồi tính tay timezone để xác minh timestamp từ client. Unix epoch seconds là mốc UTC tuyệt đối; timezone chỉ ảnh hưởng cách trình bày, không phải phép kiểm tra tuổi request.

### 8.2. Clock skew giữa các nodes

Nếu một node có đồng hồ nhanh hơn node khác, request mà node này coi hết hạn có thể vẫn được node khác coi fresh. Đặt `M` và giám sát đồng bộ clock (NTP/clock discipline) phù hợp với kiến trúc. Với hệ thống nhiều vùng, cần đánh giá sai lệch lớn nhất, failover và thời gian store ghi/đọc.

Không dùng `System.nanoTime()` để so với Unix timestamp của HTTP header; nó là đồng hồ **tương đối**, không phải epoch timestamp. Nó có thể dùng để đo interval trong một process, nhưng không để xác minh expiry xuyên nodes.

## 9. Java 17: chính sách TTL và atomic claim

Tách **policy thời gian** khỏi **store implementation** giúp kiểm thử rõ ràng:

~~~java
import java.time.Duration;
import java.util.regex.Pattern;

public final class NonceExpiryPolicyV1 {
    public static final long MAX_PAST_AGE = 300L;
    public static final long MAX_FUTURE_SKEW = 30L;
    public static final long SAFETY_MARGIN = 30L;

    public static final Duration NONCE_TTL =
            Duration.ofSeconds(
                    MAX_PAST_AGE + MAX_FUTURE_SKEW + SAFETY_MARGIN);

    private static final Pattern NONCE =
            Pattern.compile("[0-9a-f]{32}");
    private static final Pattern KEY_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,80}");

    private NonceExpiryPolicyV1() {}

    public static String replayKey(
            String audience, String keyId, String nonce) {

        if (!"orders-api".equals(audience)
                || keyId == null || !KEY_ID.matcher(keyId).matches()
                || nonce == null || !NONCE.matcher(nonce).matches()) {
            throw new IllegalArgumentException("Invalid replay key");
        }

        return "hmac-nonce:v1:" + audience
                + ":" + keyId + ":" + nonce;
    }

    public interface AtomicReplayStore {
        /**
         * Atomically insert key only if absent, with TTL on creation.
         *
         * @return true if inserted; false if key already exists.
         * @throws ReplayStoreUnavailableException on uncertain/store errors.
         */
        boolean putIfAbsentWithTtl(
                String key, String value, Duration ttl);
    }

    /**
     * PRECONDITION: HMAC already verified, timestamp freshness checked.
     * Call exactly once at the replay admission boundary.
     */
    public static boolean claimVerifiedNonce(
            String audience, String keyId, String nonce,
            AtomicReplayStore store) {

        String key = replayKey(audience, keyId, nonce);
        return store.putIfAbsentWithTtl(key, "seen", NONCE_TTL);
    }
}
~~~

Ở đây `ReplayStoreUnavailableException` là loại lỗi minh họa của ứng dụng; bạn có thể định nghĩa riêng hoặc để adapter ném một runtime exception phù hợp. **Không** biến exception thành `true` rồi coi request đã được chấp nhận.

### 9.1. Điều kiện tiên quyết quan trọng

`claimVerifiedNonce` **không tự tính HMAC** và **không tự kiểm tra timestamp**. Chỉ gọi nó **sau khi**:

1. HTTP parser chấp nhận request không nhập nhằng.
2. Key record đúng trạng thái/audience đã được chọn.
3. Verifier tái tạo canonical bytes từ request thực nhận.
4. Expected HMAC so với presented signature đã **khớp**.
5. Timestamp đã ký còn nằm trong freshness window.

Nếu gọi claim trước HMAC, attacker có thể gửi request giả mạo với một nonce dự đoán/quan sát được để **chiếm nonce entry**, ngăn request hợp lệ sử dụng nonce đó.

### 9.2. Tại sao không reset TTL trên duplicate?

Store method phải có tính chất:

~~~text
if key does not exist:
    create key and TTL in ONE atomic action -> inserted=true
else:
    leave existing value and TTL unchanged -> inserted=false
~~~

Không dùng kiểu “GET key rồi SET key” vì hai requests đồng thời có thể cùng thấy key chưa tồn tại. Không gọi `EXPIRE` riêng sau khi `SETNX` nếu hai thao tác có thể bị ngắt ở giữa; có thể tạo key không có TTL, gây lưu vô hạn.

## 10. Redis: atomic insert-if-absent với TTL

Với Redis, pattern phù hợp cho trường hợp này:

~~~redis
SET hmac-nonce:v1:orders-api:partner-a-k3:6bfb21974a08417199273b09ca49a3ec seen NX EX 360
~~~

Ý nghĩa:

- `SET`: tạo replay entry.
- `NX`: chỉ tạo khi key chưa tồn tại.
- `EX 360`: tạo cùng TTL **360 giây**.
- Redis trả `OK` nếu chèn thành công, không trả `OK` khi key đã có (client library có thể biểu diễn thành null/false).
- Lệnh duy nhất bảo đảm **atomic claim** trên một Redis primary/instance thích hợp.

Lưu ý: Trong vận hành nhiều primary/region, **không tự suy rằng ghi bất đồng bộ qua replica hoặc multi-master eventually consistent sẽ có cùng tính linearizable**. Phải chứng minh mọi verifier cùng dùng một replay authority có tính nguyên tử theo phạm vi chấp nhận hoặc chọn một lưu trữ/cơ chế phối hợp khác phù hợp.

### 10.1. Pseudocode adapter

~~~java
// PSEUDOCODE: API cụ thể khác nhau theo Lettuce/Jedis/Spring Data.
boolean putIfAbsentWithTtl(
        String key, String value, Duration ttl) {

    // Một thao tác Redis: SET key value NX EX ttlSeconds.
    Object reply = redis.executeSetNxEx(
            key, value, ttl.getSeconds());

    if (reply == STORE_TIMEOUT_OR_UNKNOWN_RESULT) {
        throw new ReplayStoreUnavailableException();
    }

    return reply == REDIS_OK;
}
~~~

Trong production, nếu request tới Redis timeout sau khi server **có thể đã ghi key**, kết quả là **không chắc chắn**. Không nên retry thao tác nghiệp vụ như thể nonce chưa được dùng; với API nhạy cảm, từ chối/fail closed và yêu cầu caller dùng cơ chế retry/idempotency an toàn.

### 10.2. Eviction khác expiration

**Expiration** là xóa key theo TTL đã định nghĩa. **Eviction** là store xóa key **trước TTL** vì memory pressure hoặc chính sách bộ nhớ, có thể mở lại cửa sổ replay.

Vì vậy:

- Dùng capacity planning, quota, memory metrics và eviction alerts.
- Với kho replay trọng yếu, cân nhắc chính sách memory/eviction **không làm biến mất nonce đang hiệu lực** (ví dụ cấu hình phù hợp với fail-closed).
- Khi store hết bộ nhớ và không thể ghi nonce, request không được tự đi tiếp.
- Giám sát evicted keys, insert errors, latency và replication consistency.

Không cho rằng Redis đã cấu hình EXPIRE thì replay defense chắc chắn hoạt động khi chịu áp lực bộ nhớ.

### 10.3. Ước lượng dung lượng

Số nonce cần lưu xấp xỉ:

\[
\text{activeNonceEntries} \approx \text{acceptedRequestRatePerSecond}\times \text{retentionSeconds}
\]

Ví dụ API có nhiều nghìn yêu cầu ký mỗi giây và retention vài phút có thể tạo rất nhiều keys đồng thời. Cần dự trù key overhead, sharding, metrics, load testing và chống lạm dụng, thay vì hạ TTL xuống mức không đủ an toàn chỉ để tiết kiệm RAM.

## 11. Fixed TTL hay deadline theo signed timestamp?

Hai thiết kế có thể đúng nếu đáp ứng policy.

### 11.1. Fixed TTL đủ bảo thủ

~~~text
ttl = maxPastAge + maxFutureSkew + safetyMargin
~~~

Ưu điểm:

- Dễ code và kiểm tra.
- Không cần gửi expiry riêng.
- Từ thời điểm nonce được ghi, lưu đủ lâu ngay cả khi request có timestamp ở tương lai cho phép.
- Redis `SET NX EX` đơn giản.

Nhược điểm:

- Một request có timestamp gần hết hạn vẫn giữ nonce đủ TTL cố định, tốn bộ nhớ lâu hơn cần thiết.
- Cần xác định safety margin thật phù hợp với clock/drift và cấu hình cluster.

### 11.2. Deadline theo timestamp

Một lựa chọn khác tính:

~~~text
freshnessEnd     = signedTimestamp + maxPastAge
retentionEnd     = freshnessEnd + safetyMargin
remainingTtl     = retentionEnd - serverNow
~~~

Nếu tính theo đơn vị giây, phải chú ý inclusive bound, overflow, clock skew và delay từ `serverNow` tới lúc Redis tạo key. Thêm margin để tránh key hết trước khi **mọi verifier** coi request stale.

**Nguy cơ:** Nếu client gửi signed timestamp quá xa tương lai và verifier quên kiểm tra `F` trước khi tính TTL, nó có thể tạo replay record với TTL cực lớn, gây tiêu hao bộ nhớ. Vì vậy phải xác minh HMAC và freshness trước khi đặt deadline.

### 11.3. Khi nào được rút ngắn TTL theo key expiration?

Nếu key record có `acceptUntil` đáng tin và hệ thống đảm bảo **tất cả verifier sẽ từ chối credential đó** sau thời điểm ấy, có thể phân tích một retention deadline ngắn hơn:

~~~text
retainUntil = min(timestampFreshnessEnd, credentialAcceptUntil)
              + operationalSafetyMargin
~~~

Nhưng chỉ làm vậy khi toàn bộ key-status propagation, cache invalidation và clock skew đã được kiểm chứng. Đơn giản hơn là giữ TTL theo freshness window và để key expiration là lớp từ chối bổ sung.

## 12. Race condition: hai request đến đồng thời

Luồng dễ sai:

~~~text
Node A: GET nonceKey -> missing
Node B: GET nonceKey -> missing
Node A: SET nonceKey
Node B: SET nonceKey
Node A: accept
Node B: accept
~~~

Hai instance đều chấp nhận **cùng signed request** dù nonce được lưu.

Luồng đúng:

~~~text
Node A: SET nonceKey seen NX EX 360 -> OK     -> continue
Node B: SET nonceKey seen NX EX 360 -> exists -> reject replay
~~~

Chỉ một request có thể thắng **atomic claim** trong cùng replay authority. Đây là thuộc tính correctness độc lập với việc TTL dài bao nhiêu.

### 12.1. Không chỉ dùng local in-memory cache

~~~java
// Không đủ khi có nhiều application instances.
ConcurrentHashMap<String, Long> seenNonces;
~~~

Một local map chỉ biết requests đi qua **một JVM**. Load balancer có thể đưa cùng signed request tới node khác với map khác. Khi chạy nhiều nodes, cần shared store có semantics nguyên tử hoặc một routing/coordination scheme được chứng minh tương đương.

### 12.2. Multi-region replication

Nếu hai regions có hai replay stores chỉ đồng bộ **eventually consistent**, cùng nonce có thể được chấp nhận ở cả hai trước khi replication hội tụ.

Tùy threat model, giải pháp gồm:

- Một replay authority nhất quán cho scope credential/audience.
- Sticky routing có cơ chế chống bypass/failover được kiểm soát.
- Transactional database với unique constraint và consistency tương ứng.
- Cơ chế consensus/coordination nếu cần chống replay mạnh xuyên vùng.

Không gắn nhãn “distributed Redis” là đủ nếu semantics chỉ eventual replication.

## 13. Crash, timeout và trạng thái không chắc chắn

Một request có thể gặp sự cố sau khi nonce đã được claim nhưng trước khi business transaction hoàn tất.

~~~text
HMAC OK
timestamp OK
nonce claimed
application crashes
business action chưa hoàn thành
~~~

Trong trường hợp này, **không nên xóa nonce để cho phép replay nguyên request** như một cách retry tùy tiện: một đường xử lý khác có thể đã thực hiện một phần hoặc toàn bộ thao tác.

Thay vào đó:

- Client tạo một **signed request mới** với nonce mới nếu được contract cho phép retry.
- Business layer dùng **idempotency key/event ID** và transactional/idempotency store để tránh tác động trùng.
- Response có thể báo trạng thái xử lý chưa xác định, và hệ thống cung cấp API tra cứu operation status.
- Không gắn nonce TTL với thời gian hoàn thành business transaction; đó là hai thời hạn khác nhau.

### 13.1. Tránh rút TTL vì request thất bại authorization

Giả sử request có MAC hợp lệ, nonce mới, nhưng principal không có quyền với resource. Có nên “trả lại” nonce để thử lại?

Không nên tự động trả lại. Nếu replay gate nằm **trước authorization**, nonce đã claim thì coi là đã dùng; nếu authorization nằm trước gate, cần đảm bảo không thực thi thao tác hoặc tạo race/timing oracle không mong muốn. Thiết kế nên có một **admission order** nhất quán và không xóa nonce theo exception ngẫu nhiên.

Với API nhạy cảm, policy đơn giản là **nonce đã claim thì không được tái sử dụng**, bất kể business thành công hay lỗi.

## 14. Replay và idempotency không giống nhau

Một client có thể tạo hai requests:

~~~text
Request 1:
  idempotencyKey = order-42
  timestamp      = T1
  nonce          = N1
  signature      = HMAC(K, canonical(T1,N1,body))

Request 2:
  idempotencyKey = order-42
  timestamp      = T2
  nonce          = N2
  signature      = HMAC(K, canonical(T2,N2,body))
~~~

Cả hai đều có nonce mới, timestamp hợp lệ và HMAC đúng. **Replay gate không xem request 2 là cùng nonce**. Nhưng business layer cần nhận ra cả hai cùng một order operation để không tính phí/tạo đơn hai lần.

| Vấn đề | Giải pháp | Thời hạn lưu |
| --- | --- | --- |
| Replay nguyên signed request | Nonce store theo signed credential/time window | Theo freshness + skew/margin |
| Retry same business operation bằng signed request mới | Idempotency store theo operation/event key đã ký | Theo yêu cầu nghiệp vụ, có thể dài hơn nhiều |
| Thực thi lại do message delivery | Durable event deduplication/transaction | Theo semantics queue/workflow |
| Credential bị thu hồi | Key registry/revocation policy | Theo key lifecycle |

Không tự lấy `X-Request-Id` hoặc tracing header **không được ký** làm idempotency key đáng tin; attacker có thể thay nó mà HMAC trên các field khác vẫn đúng.

## 15. Key rotation và nonce expiration

Một client chuyển từ k2 sang k3:

~~~text
partner-a-k2 -> secret v2, RETIRING
partner-a-k3 -> secret v3, ACTIVE
~~~

Có vài trường hợp:

- **K2 vẫn được chấp nhận:** Nonce dùng dưới k2 vẫn phải được lưu đủ lâu cho tới khi signed requests dùng k2 không còn fresh hoặc key không còn được phép.
- **K2 đã revoked:** Request ký bằng k2 phải bị từ chối độc lập với việc nonce entry còn/hết hạn.
- **K3 vừa ACTIVE:** Có thể dùng namespace nonce theo key ID k3. Không cho key ID tự khai chọn secret khác mà không kiểm tra HMAC.
- **Re-key cùng key ID:** Không nên thay secret dưới cùng một ID rồi thử các bí mật cũ/mới tùy tiện; làm mơ hồ audit/revocation và replay scope.

### 15.1. Có nên xóa toàn bộ nonce entries của key cũ?

Không nên xóa sớm chỉ vì client “đã được thông báo chuyển key”. Trong khoảng overlap, request ký bằng k2 vẫn có thể được chấp nhận. Nếu xóa các nonce của k2 trước khi k2 thực sự bị từ chối tại **mọi node**, replay window có thể mở lại.

Chỉ thay đổi retention nếu key policy và propagation bảo đảm không có verifier nào chấp nhận request k2 sau thời điểm đó; cần tính clock margin và cache invalidation.

### 15.2. Audience binding và cross-service replay

Nếu cùng credential/secret được dùng ở nhiều service, request có thể bị phát lại tại service khác nếu canonical request không ràng buộc audience/authority phù hợp. Nonce namespace có audience giúp tách trạng thái, nhưng **không thay việc ký và kiểm tra audience**.

Tốt hơn là dùng credentials với scope hẹp, secret tách theo service hoặc signed audience được đối chiếu key record/routing.

## 16. Proxy/gateway và nonce TTL

Luồng thường gặp:

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant G as API Gateway
    participant V as HMAC Verifier
    participant R as Shared Replay Store
    participant A as Application

    C->>G: Signed request với timestamp và nonce
    G->>V: Forward request theo signing contract
    V->>V: Canonicalize, tra key, verify HMAC
    V->>V: Kiểm tra freshness
    V->>R: Atomic claim nonce + TTL
    R-->>V: Inserted hoặc Already exists
    V->>A: Chỉ cho qua khi nonce mới và đủ quyền
~~~

### 16.1. Verifier ở gateway

Khi gateway xác minh chữ ký từ Internet:

- Gateway đọc raw request và signed headers ở ranh giới đã định nghĩa.
- Nonce claim diễn ra ở một replay authority đáng tin.
- Backend nhận authenticated principal/context qua kênh nội bộ bảo vệ, không tin `X-Authenticated-User` do client tự khai.
- Gateway phải đảm bảo mapping route/action tới backend đúng với canonical request đã ký.
- Nếu backend có thêm verifier, phải định nghĩa **có claim lại nonce không**; hai tầng cùng claim một namespace có thể khiến request hợp lệ bị từ chối ở tầng sau.

### 16.2. Verifier ở backend

Nếu backend xác minh:

- Gateway phải giữ nguyên timestamp/nonce/signed components hoặc dùng mapping chính thức theo contract.
- Không tin `X-Original-URI`, `X-Forwarded-Host` hay metadata thời gian do caller tự khai như dữ liệu proxy đáng tin.
- Tất cả backend replicas cần dùng cùng replay authority/consistency guarantee.
- Test HTTP/1.1↔HTTP/2, proxy retries, gateway timeouts và TLS termination.

### 16.3. Gateway retry nội bộ có thể bị coi là replay

Một gateway gửi request tới backend, không nhận response do timeout rồi **retry nguyên signed request**. Với nonce đã claim, lần retry có thể bị từ chối.

Điều này là hành vi bảo vệ hợp lệ, không nhất thiết là bug HMAC. Hệ thống cần thiết kế:

- Retry policy rõ: không tự retry thao tác không idempotent nếu trạng thái không chắc chắn.
- Idempotency key đã ký và server-side idempotency store.
- Mô hình response/operation status khi backend xử lý xong nhưng gateway không nhận ACK.
- Không tắt nonce replay gate chỉ để làm retry “đi qua”.

## 17. Thời điểm kiểm tra và fail-closed policy

Một pipeline an toàn:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Validate framing, request size, signed headers]
    B --> C[Lookup key ID và policy]
    C --> D[Canonicalize method, URI, header, raw body]
    D --> E[HMAC expected tag và constant-time comparison]
    E --> F{HMAC hợp lệ?}
    F -- Không --> X[Từ chối]
    F -- Có --> G{Signed timestamp còn fresh?}
    G -- Không --> X
    G -- Có --> H[Atomic nonce claim + TTL]
    H --> I{Claim thành công?}
    I -- Không/trùng/lỗi --> X
    I -- Có --> J[Principal từ key record]
    J --> K{Có quyền action/resource?}
    K -- Không --> Y[Từ chối authorization]
    K -- Có --> L[Business handler + idempotency]
~~~

Có thể kiểm tra freshness **trước HMAC** để loại sớm timestamp ngoài cửa sổ, miễn là đó chưa phải hành động tin giá trị do client khai. Nhưng **không** đánh dấu nonce trong store trước khi HMAC đúng.

### 17.1. Store timeout: đừng tự cho request qua

Một anti-pattern:

~~~java
try {
    return replayStore.claim(nonce);
} catch (Exception unavailable) {
    return true; // CỰC KỲ NGUY HIỂM cho API nhạy cảm.
}
~~~

Nếu replay store gặp lỗi, attacker có thể replay request trong thời gian đó. Với thanh toán, thao tác nhạy cảm hoặc yêu cầu “at most once” nghiêm ngặt, nên **fail closed**: từ chối hoặc báo tạm thời không thể xác minh anti-replay, không chạy business action.

Không log full signed payload và secret trong quá trình xử lý lỗi store; chú ý retention/security của logs.

### 17.2. Store có thể đã ghi dù client nhận timeout

Nếu lệnh claim gửi tới Redis và response bị mất, không thể biết chắc nonce đã được ghi hay chưa. Khi kết quả không xác định:

- Không giả định “claim failed nên nonce vẫn mới”.
- Không giả định business đã thực thi.
- Phản hồi theo policy có thể thử lại bằng request mới/operation ID.
- Idempotency business store mới là nơi xác minh tác động đã xảy ra.

## 18. Ma trận kiểm thử nonce expiration

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Signature | HMAC sai nhưng nonce chưa thấy | Reject; không claim nonce |
| Signature | Sửa nonce mà giữ tag cũ | HMAC không khớp |
| Signature | Sửa timestamp mà giữ tag cũ | HMAC không khớp |
| Freshness | Timestamp đúng `now - A` | Chấp nhận ở biên nếu policy inclusive |
| Freshness | Timestamp nhỏ hơn `now - A` một giây | Reject expired |
| Freshness | Timestamp đúng `now + F` | Chấp nhận ở biên nếu policy inclusive |
| Freshness | Timestamp lớn hơn `now + F` một giây | Reject future |
| Freshness | Dùng milliseconds thay seconds | Reject ngoài window/format |
| Freshness | Timestamp có dấu `+` hoặc leading zeros | Reject canonical format |
| Nonce input | 32 ký tự hex chữ thường | Hợp lệ về format |
| Nonce input | Nonce quá ngắn/dài, uppercase hoặc `g` | Reject |
| Nonce input | Cùng nonce với timestamp khác, signature mới | Reject trong cùng replay namespace |
| Nonce store | Nonce đầu tiên | Atomic insert thành công |
| Nonce store | Nonce thứ hai | Already exists, reject |
| Nonce store | 2 request đồng thời cùng nonce | Tối đa một request qua claim |
| TTL | `A=300,F=30,ttl=300` | Negative test: TTL quá ngắn, có replay gap |
| TTL | `A=300,F=30,ttl=360` | Nonce được giữ qua toàn bộ window theo margin đã giả định |
| TTL | Future timestamp tại biên `now+F` | Không quên nonce trước `ts+A` |
| TTL | Timestamp gần hết hạn ở lần dùng đầu | Fixed TTL có thể giữ dư nhưng vẫn an toàn |
| TTL | Key hết TTL đúng tại biên inclusive | Test phải xử lý off-by-one/margin |
| TTL | Redis eviction sớm | Phát hiện và không cho silent bypass |
| TTL | Replay không làm reset TTL | Entry giữ expiry ban đầu |
| Clock | Nodes lệch đồng hồ trong giới hạn | Retention bao phủ mọi node |
| Clock | Clock drift vượt margin | Alarm/limit; không tuyên bố window vẫn an toàn |
| Store | GET rồi SET tách rời | Negative test phát hiện race |
| Store | SET NX EX atomic | Một winner |
| Store | SETNX sau đó EXPIRE, crash giữa bước | Negative test phát hiện key thiếu TTL |
| Store | Timeout/unknown result | Fail closed |
| Store | Store unavailable | Không thực thi tác động nhạy cảm |
| Distributed | Node A/B dùng cache độc lập | Negative test phát hiện replay cross-node |
| Distributed | Eventually consistent regional stores | Negative test phát hiện dual accept |
| Rotation | Key k2 ACTIVE/RETIRING | Nonce k2 còn hiệu lực theo window |
| Rotation | Key k2 revoked | Reject ngay cả khi nonce entry đã hết |
| Rotation | K3 secret mới | K3 dùng đúng key record, namespace |
| Gateway | Retry nguyên signed request | Replay reject nếu nonce đã claim |
| Gateway | Proxy rewrite signed URI/body | HMAC reject hoặc verify tại biên đúng |
| Authorization | MAC/nonce đúng, tenant không có quyền | Authorization reject |
| Idempotency | Request mới nonce khác, cùng business event | Business deduplication ngăn tác động lặp |

### 18.1. Golden tests với clock cố định

Giả sử test:

~~~text
T0 = 1_800_000_000
A  = 300
F  = 30
M  = 30
TTL = 360
~~~

Cases:

~~~text
ts = T0 - 300  -> fresh, đúng biên quá khứ
ts = T0 - 301  -> stale
ts = T0 + 30   -> fresh, đúng biên tương lai
ts = T0 + 31   -> too far future
~~~

Với `ts = T0 + 30`, request còn fresh tới `T0 + 330`; nonce claim lúc `T0` phải còn tồn tại qua khoảng đó.

### 18.2. Unit test Java 17 cho timestamp

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

// Đây là test logic minh họa; có thể dùng JUnit assertTrue/assertFalse.
long t0 = 1_800_000_000L;
Clock fixed = Clock.fixed(
        Instant.ofEpochSecond(t0), ZoneOffset.UTC);

assert SignedTimestampV1.isFresh(t0 - 300, fixed);
assert !SignedTimestampV1.isFresh(t0 - 301, fixed);
assert SignedTimestampV1.isFresh(t0 + 30, fixed);
assert !SignedTimestampV1.isFresh(t0 + 31, fixed);
~~~

Nếu chạy Java với assertion, cần bật `-ea`; trong JUnit dùng assertion API của framework để test chạy độc lập với cờ JVM.

### 18.3. Concurrency test không dùng sleep làm bằng chứng

Một concurrency test nên:

1. Chuẩn bị cùng replay key.
2. Cho nhiều workers bắt đầu gần đồng thời bằng barrier.
3. Mỗi worker gọi **cùng atomic store implementation**.
4. Đếm số worker được trả `inserted=true`.
5. Khẳng định số đó **bằng 1**.
6. Lặp trên môi trường có nhiều application nodes nếu sản phẩm dùng phân tán.

Không dùng `Thread.sleep` để “tạo chắc race”; sleep chỉ là điều phối không xác định và có thể bỏ sót interleaving cần test.

## 19. Lỗi thiết kế thường gặp

### 19.1. Nonce TTL bằng maxPastAge mà quên futureSkew

Nếu request được chấp nhận khi timestamp nằm `F` giây tương lai, thời gian còn fresh tính từ lần dùng đầu có thể dài `A+F`. TTL `A` tạo replay gap. Dùng retention policy đủ bao phủ freshness window và margin.

### 19.2. Chỉ kiểm nonce, bỏ kiểm timestamp

Khi replay entry đã hết hạn, nonce sẽ bị coi mới và request cũ có thể được chấp nhận bất kể tuổi. **Luôn** kiểm signed timestamp trên mọi request.

### 19.3. Ghi nonce trước khi xác minh HMAC

Attacker có thể gửi request giả để lấp store hoặc chiếm nonce của người khác. Chỉ claim nonce sau HMAC hợp lệ, theo pipeline có kiểm soát.

### 19.4. GET rồi SET thay atomic NX

Hai nodes có thể cùng nhận một nonce. Cần insert-if-absent nguyên tử với TTL được thiết lập trong cùng thao tác.

### 19.5. Cache in-memory riêng mỗi node

Replay trượt giữa hai instances. Dùng một replay authority nhất quán theo credential scope.

### 19.6. Không quan tâm Redis eviction

Entry biến mất trước TTL do memory pressure khiến cửa sổ replay có thể mở lại. Theo dõi cấu hình eviction, capacity và fail-closed policy.

### 19.7. TTL reset trên mỗi replay

Attacker có thể gia hạn entry tùy ý, phá capacity assumptions. Duplicate request nên bị reject **không đổi expiry**.

### 19.8. Xóa nonce sau khi nghiệp vụ lỗi

Nếu business action đã xảy ra một phần hoặc response mất, xóa nonce có thể cho phép replay. Không coi nonce là lock nghiệp vụ có thể release tùy trạng thái.

### 19.9. Coi nonce là idempotency key

Nonce mới cho cùng order vẫn có thể hợp lệ. Idempotency business cần khóa/TTL và store riêng.

### 19.10. Coi HMAC đúng là đủ quyền

Client có secret thật có thể ký request tới tenant khác. Authorization phải kiểm tra principal/action/resource/tenant dù nonce mới và chữ ký đúng.

## 20. Tình huống thực tế: webhook thanh toán replay ở giây cuối

Một nhà cung cấp gửi webhook đã ký đến payment API. Hệ thống cho phép:

~~~text
maxPastAge = 300 seconds
futureSkew = 30 seconds
replayStoreTtl = 300 seconds
~~~

Client có đồng hồ nhanh hơn server 30 giây. Request ký `ts = T0+30` được chấp nhận lần đầu tại `T0`, nonce được lưu 300 giây.

Attacker capture và gửi lại nguyên request tại `T0+310`.

- HMAC tag vẫn khớp vì không đổi request.
- Timestamp vẫn fresh: `T0+310 ≤ T0+30+300`.
- Nonce entry đã hết TTL tại `T0+300`.
- Replay store trả “nonce chưa tồn tại”.
- Webhook có nguy cơ được xử lý lần hai.

**Nguyên nhân gốc:** Nonce expiration không bao phủ toàn bộ timestamp freshness window, không phải HMAC sai.

**Khắc phục:**

1. Áp dụng TTL đủ dài, chẳng hạn `A+F+M` sau khi chứng minh margin phù hợp.
2. Luôn kiểm signed timestamp ở mỗi request, không chỉ nonce.
3. Dùng atomic insert-if-absent với TTL trong một lệnh.
4. Đảm bảo nonce store không evict sớm và tất cả nodes dùng chung.
5. Kiểm thử tại `T0+300`, `T0+310`, `T0+330`, `T0+331`.
6. Có idempotency store riêng để webhook event đã xử lý không tạo tác động trùng, kể cả khi caller có thể gửi request mới ký bằng nonce khác.

Điểm kiểm tra quan trọng: tại `T0+330`, request còn fresh nếu policy dùng biên inclusive; tại `T0+331` phải bị từ chối vì quá cũ. Replay entry cần bao phủ tới cuối khoảng chấp nhận và có buffer an toàn.

## 21. Bài tập thực hành

1. **Tính replay gap:** Với `A=120` giây, `F=20` giây, nonce TTL chỉ 120 giây, hãy tính khoảng thời gian một request có timestamp tương lai tại biên có thể còn fresh sau khi key bị xóa.
2. **Thiết kế retention:** Đưa ra công thức TTL cho môi trường nhiều nodes, nói rõ giả định clock skew và safety margin.
3. **Unit tests:** Viết JUnit tests cho `SignedTimestampV1.parse` và `isFresh` với boundary, leading zeros, timestamps âm và overflow.
4. **Atomic claim:** Tạo fake store có `putIfAbsentWithTtl` nguyên tử, kiểm tra claim một lần thành công, lần sau thất bại.
5. **Redis integration:** Gọi `SET key value NX EX ttl` từ một Java Redis client và xác minh duplicate không reset TTL; chạy concurrency test thực.
6. **Failure modes:** Mô phỏng Redis outage, timeout với kết quả không xác định, memory eviction và cross-region replication lag. Đề xuất fail-closed behavior.
7. **Gateway retry:** Một gateway retry nguyên signed request do mất response; giải thích vì sao replay gate reject và idempotency/operation status giải quyết nghiệp vụ như thế nào.
8. **Rotation:** Trong overlap k2/k3, thiết kế namespace nonce theo key ID và kiểm tra request ký bằng key revoked không thể được chấp nhận sau khi nonce entry hết hạn.
9. **Authorization:** Client tenant A gửi HMAC đúng, nonce mới, timestamp hợp lệ cho order tenant B; chỉ ra bước bắt buộc từ chối quyền.

## 22. Checklist triển khai Nonce expiration

- [ ] Signed timestamp và nonce là thành phần của canonical request được HMAC bảo vệ.
- [ ] Key ID, algorithm, audience và secret được tra từ key registry đáng tin, không do client tự quyết.
- [ ] Nonce có format rõ và nguồn tạo đủ ngẫu nhiên/unique.
- [ ] Freshness window nêu rõ max past age và allowed future skew.
- [ ] Các biên timestamp inclusive/exclusive được định nghĩa và test.
- [ ] TTL nonce bao phủ **max past age + future skew + margin** hoặc deadline tương đương đã kiểm chứng.
- [ ] Clock drift, multiple nodes và store clock được tính vào margin thực tế.
- [ ] Không cho client tự hạ TTL bằng header bất kỳ.
- [ ] Luôn kiểm freshness, kể cả khi nonce entry không còn trong store.
- [ ] Nonce được claim **sau khi HMAC hợp lệ** và freshness đã qua.
- [ ] Claim có tính nguyên tử cùng expiration: `SET ... NX EX ...` hoặc tương đương.
- [ ] Duplicate nonce bị từ chối, không gia hạn TTL tùy tiện.
- [ ] Replay namespace có audience, credential/key ID và nonce, không nhập nhằng delimiter.
- [ ] Mọi verifier trong scope dùng một replay authority có consistency phù hợp.
- [ ] Không dùng local-only cache khi có nhiều nodes trừ khi có routing/coordination được chứng minh.
- [ ] Redis eviction/outage/timeouts không mở bypass; có metrics, capacity plan và fail-closed policy.
- [ ] Key rotation/revocation không xóa replay records quá sớm trong overlap.
- [ ] Gateway retry, proxy rewrite và HTTP signing boundary có policy rõ ràng.
- [ ] Idempotency key/event ID được bảo vệ và lưu riêng theo yêu cầu nghiệp vụ.
- [ ] Authorization theo principal/action/resource/tenant diễn ra độc lập với MAC/replay.
- [ ] Có unit boundary tests, atomic concurrency tests, storage integration tests và end-to-end gateway tests.

## 23. Câu hỏi tự kiểm tra

1. **Nonce expiration là gì?** Thời điểm server được phép quên rằng một nonce đã dùng, không phải timestamp expiration của request.
2. **HMAC hợp lệ có ngăn replay nguyên request không?** Không; cùng message và secret cho cùng tag.
3. **Vì sao nonce cần nằm trong dữ liệu ký?** Để attacker không thay nonce mà vẫn giữ tag cũ.
4. **Tại sao TTL bằng maxPastAge có thể thiếu?** Vì future skew cho phép timestamp trong tương lai; freshness còn kéo dài tối đa `A+F` từ lần nhận sớm nhất.
5. **Với `A=300,F=30` và timestamp tại future bound, khi nào request hết fresh?** Tại thời điểm server vượt `t_s+300`, nếu policy inclusive.
6. **Nonce TTL có phải giá trị do client quyết định không?** Không; server phải áp min retention theo contract/trust policy.
7. **Vì sao phải kiểm timestamp ngay cả khi replay key đã hết hạn?** Vì store không đủ thông tin để quyết định request còn fresh hay không.
8. **Tại sao phải dùng atomic put-if-absent?** Để hai verifier không cùng chấp nhận một nonce chưa từng thấy.
9. **Redis `SET NX EX` giúp gì?** Kết hợp insert-only-if-absent và TTL trong một thao tác nguyên tử.
10. **Có thể dùng cache local trên mỗi JVM trong hệ thống nhiều nodes không?** Không đủ nếu replay có thể đến node khác.
11. **Vì sao eviction nguy hiểm?** Nó có thể xóa nonce trước TTL và mở lại replay gap.
12. **Có nên reset TTL mỗi lần replay không?** Không; duplicate phải reject và giữ nguyên expiration.
13. **Nếu replay store timeout, có nên bỏ qua check không?** Với API nhạy cảm, không; fail closed.
14. **Nonce có thay idempotency key không?** Không; nonce bảo vệ request replay, idempotency bảo vệ tác động nghiệp vụ trùng.
15. **Key đã revoked nhưng nonce hết TTL có được chấp nhận không?** Không; key policy phải từ chối độc lập.
16. **HMAC đúng, nonce mới, timestamp fresh có cho quyền truy cập tenant khác không?** Không; authorization riêng vẫn bắt buộc.

## 24. Tài liệu tham khảo và hướng đọc tiếp

- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Cơ chế HMAC dựa trên shared secret.
- **RFC 4231 — Identifiers and Test Vectors for HMAC-SHA-224/256/384/512.** Known-answer tests để kiểm tra tính HMAC.
- **RFC 9110 — HTTP Semantics.** Nền tảng method, header fields và request semantics liên quan signed fields.
- **RFC 3986 — URI Generic Syntax.** Những khác biệt giữa raw/canonical path/query có thể ảnh hưởng HMAC.
- **Redis SET command documentation.** Tùy chọn `NX` và `EX`/`PX` để ghi nonce cùng TTL nguyên tử.
- **Java SE 17 — `SecureRandom`, `Clock`, `Instant`, `Mac`, `MessageDigest.isEqual`.** API tạo nonce, xử lý thời gian và xác minh HMAC.

**Kết luận:** **Nonce expiration an toàn phải được suy từ toàn bộ cửa sổ mà signed request còn có thể được chấp nhận**, chứ không từ một TTL cache tùy ý. Với freshness policy cho phép tuổi quá khứ `A` và lệch tương lai `F`, TTL cố định bảo thủ thường cần ít nhất `A+F` cộng biên vận hành phù hợp; nếu không, nonce có thể biến mất trong khi request vẫn fresh. Kết hợp TTL đúng với **HMAC bảo vệ timestamp/nonce, atomic shared replay store, clock discipline, key rotation, gateway signing boundary, idempotency và authorization** mới tạo thành cơ chế chống replay đáng tin.
