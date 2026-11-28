# Clock skew trong xác thực HTTP request bằng HMAC

## 1. Clock skew là gì và vì sao timestamp đúng chữ ký vẫn có thể bị từ chối?

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client và server chia sẻ **shared secret** để ký và xác minh HTTP request bằng HMAC. Canonical request có thể chứa HTTP method, raw URI/query, những header được chọn, digest của raw body, **timestamp** và **nonce**. Timestamp giới hạn thời gian một request đã ký có thể được chấp nhận; nonce giúp nhận diện việc phát lại cùng request; key rotation kiểm soát secret nào còn hiệu lực; **authorization** vẫn kiểm tra quyền trên tài nguyên thực tế sau authentication.

**Clock skew** là độ lệch giữa các đồng hồ được dùng để tạo và kiểm tra timestamp. Cùng một thời điểm thực tế, đồng hồ client có thể hiển thị nhanh hơn server 25 giây hoặc chậm hơn 2 phút. Hai replica của server cũng có thể lệch nhau, đặc biệt khi hệ thống đồng bộ giờ lỗi hoặc vừa khởi động. Vì vậy, một request có HMAC **hoàn toàn hợp lệ về mặt mật mã** vẫn có thể bị từ chối vì timestamp nằm ngoài chính sách thời gian.

Ví dụ tại thời điểm giả định `2026-01-01T12:00:00Z`, verifier thấy:

```text
Server wall clock:            2026-01-01T12:00:00Z
Client A clock (đúng):        2026-01-01T12:00:00Z
Client B clock (nhanh +25s):  2026-01-01T12:00:25Z
Client C clock (chậm -120s):  2026-01-01T11:58:00Z
Client D clock (nhanh +90s):  2026-01-01T12:01:30Z
```

Nếu API cho phép request **cũ tối đa 300 giây** và timestamp **ở tương lai tối đa 30 giây**, B/C còn trong cửa sổ, còn D bị từ chối — dù client D biết đúng secret và tự tạo HMAC mới.

Điểm quan trọng: **“chữ ký đúng” và “thời gian chấp nhận được” là hai điều kiện độc lập, cùng bắt buộc đạt**. Khi phát sinh lỗi time window, tuyệt đối không sửa canonical request, tự thay timestamp, bỏ kiểm tra HMAC hoặc nới cửa sổ tùy ý để “làm client chạy được”.

Bài **“Clock skew”**, thuộc chương **“Timestamp”**, tập trung vào tính toán cửa sổ thời gian, sự khác biệt giữa wall clock và monotonic clock, chính sách đồng bộ đồng hồ, cách thiết kế TTL nonce, xử lý upload dài, Java 17 `Clock`, kiểm thử đa replica và phản ứng khi đồng hồ không đáng tin.

### Kết quả cần đạt

Sau bài này, bạn có thể:

1. Phân biệt **clock skew**, **clock drift**, **network delay**, **request queueing** và **replay**.
2. Định nghĩa chính xác cửa sổ timestamp **quá khứ** và **tương lai** theo epoch seconds, xử lý biên bao gồm hay loại trừ.
3. Viết bộ kiểm tra timestamp Java 17+ bằng `Clock` được inject, không phụ thuộc timezone máy.
4. Giải thích vì sao **nonce TTL phải bao phủ toàn bộ khoảng thời gian một timestamp có thể được chấp nhận**, kể cả lệch giữa các replica.
5. Thiết kế thứ tự verify HMAC → check timestamp → atomic nonce reserve → authorization và các kiểm tra có thể từ chối sớm.
6. Đưa ra chính sách fail-closed khi NTP/clock health lỗi, không biến một timestamp đã ký thành “vé thông hành vô hạn”.
7. Kiểm thử proxy/gateway, HTTP/2, key rotation, độ trễ upload và clock skew bất đối xứng.

## 2. Phân biệt skew, drift, latency và replay

Để xử lý lỗi, trước tiên phải phân biệt **nguyên nhân khác nhau** khiến server thấy timestamp lệch.

| Thuật ngữ | Nghĩa chính | Ảnh hưởng đến HMAC authentication |
| --- | --- | --- |
| **Clock skew / offset** | Độ lệch thời gian giữa hai clock tại một thời điểm, ví dụ client đi nhanh +25 giây | Timestamp client có thể ở tương lai so với server, hoặc quá cũ. |
| **Clock drift** | Sự thay đổi offset theo thời gian do oscillator chạy nhanh/chậm | Client có thể ban đầu đúng, rồi lệch thêm sau vài giờ/ngày không đồng bộ. |
| **Network latency** | Thời gian truyền request từ lúc ký đến lúc server kiểm tra | Timestamp trở nên **cũ hơn**, ngay cả khi hai clock chính xác. |
| **Queue / retry delay** | Request bị chờ ở client SDK, proxy, queue hoặc trước khi verify body | Timestamp có thể hết hạn; cần ký lại attempt hợp lệ nếu chính sách cho phép. |
| **Clock step / correction** | Đồng hồ wall clock nhảy tới hoặc lùi do hệ điều hành/NTP/operator | Một loạt request có thể bị loại hoặc chấp nhận ngoài chính sách nếu không kiểm soát clock health. |
| **Replay** | Gửi lại request đã ký mà không được phép | Timestamp chỉ giới hạn thời gian; **nonce** mới chặn lần dùng thứ hai trong cửa sổ. |

Giả sử:

```text
realSigningTime = t
clientClock     = t + delta
arrivalTime     = t + delay
serverClock     = arrivalTime + serverOffset

signedTimestamp - serverNow = delta - delay - serverOffset
```

Với `delta > 0`, client có clock chạy nhanh; `delay` thường làm timestamp nhìn **bớt ở tương lai** khi request tới server. Với client clock chạy chậm, latency có thể làm request càng **quá khứ**. Vì vậy lỗi “timestamp expired” không nhất thiết do đồng hồ client hỏng: HTTP upload dài, SDK xếp hàng và gateway timeout cũng có thể gây ra.

### 2.1 Phép kiểm tra không nên chỉ dùng một con số “skew”

Một lựa chọn phổ biến nhưng dễ thiếu rõ ràng là:

```text
abs(serverNow - signedTimestamp) <= 300
```

Nó tạo cửa sổ **đối xứng ±300 giây**, đồng nghĩa chấp nhận timestamp **ở tương lai 5 phút**. Điều này có thể không cần thiết, vì các client có clock chạy đúng thường chỉ cần dung sai tương lai nhỏ. Một cấu hình **bất đối xứng** cho phép:

- Request quá khứ nhiều nhất **300 giây**, để chịu network delay và retry ngắn.
- Request tương lai nhiều nhất **30 giây**, để chịu client đồng hồ chạy nhanh ít.
- Từ chối cả hai phía khi vượt quá ngưỡng.

Đây là **ví dụ policy**, không phải giá trị chuẩn bắt buộc. API upload lớn hoặc IoT không đồng bộ thường xuyên có thể cần thiết kế khác; phải cân nhắc replay window, tính sẵn sàng, lưu nonce và hiệu quả đồng bộ thời gian.

## 3. Định nghĩa chính xác cửa sổ freshness

Ta chọn chính sách giả định:

```text
maxPastAge     = 300 giây
maxFutureSkew  = 30 giây

accept khi:
    serverNow - 300 <= signedTimestamp <= serverNow + 30
```

Hai đầu mút **được chấp nhận** theo contract của bài. Viết dưới dạng chênh lệch:

```text
delta = signedTimestamp - serverNow

accept nếu: -300 <= delta <= +30
reject nếu: delta < -300  hoặc  delta > +30
```

| Server time cố định | Timestamp đã ký | Chênh lệch `signed − now` | Kết quả |
| --- | --- | --- | --- |
| `12:00:00Z` | `11:55:00Z` | `-300s` | **Chấp nhận**, biên quá khứ. |
| `12:00:00Z` | `11:54:59Z` | `-301s` | Từ chối: quá cũ. |
| `12:00:00Z` | `12:00:00Z` | `0s` | Chấp nhận. |
| `12:00:00Z` | `12:00:30Z` | `+30s` | **Chấp nhận**, biên tương lai. |
| `12:00:00Z` | `12:00:31Z` | `+31s` | Từ chối: quá xa tương lai. |

Một số implementation dùng điều kiện `<` thay vì `<=` ở biên, dẫn đến kết quả khác đúng 1 giây. Cần công bố **tính bao hàm biên**, đơn vị thời gian và cách làm tròn thời gian server. Client Java và server Go/Node/Python phải có test vectors chung.

### 3.1 Epoch seconds, không phải milliseconds hay giờ địa phương

Timestamp của bài là **Unix epoch seconds**, tính theo UTC từ 1970-01-01T00:00:00Z, biểu diễn bằng **chuỗi thập phân ASCII canonical**, ví dụ:

```text
2026-01-01T12:00:00Z  ->  1767268800
```

Không dùng:

- `System.currentTimeMillis()` trực tiếp làm timestamp (đơn vị **milliseconds**).
- Chuỗi datetime có timezone địa phương, ví dụ `01/01/2026 19:00`.
- Thời gian lấy từ `LocalDateTime.now()` rồi giả định UTC mà không biết offset.
- Timestamp dạng floating point seconds, scientific notation hay cộng prefix `+` nếu hợp đồng không cho phép.
- `X-Date` không ký thay cho timestamp HMAC.

**Timestamp phải nằm trong canonical bytes đã ký.** Nếu attacker có thể đổi timestamp mà không làm MAC sai, họ có thể kéo dài thời gian chấp nhận một request cũ.

### 3.2 Quy tắc định dạng nghiêm ngặt

Hợp đồng `CLOCK-V1` dùng:

```text
x-hmac-timestamp:(0|[1-9][0-9]{0,11})
```

Diễn giải: số không, hoặc một chữ số 1–9 theo sau tối đa 11 chữ số; không leading zero, không dấu cộng/trừ, không decimal, không khoảng trắng, không Unicode digit. Regex này giới hạn độ dài; bên server còn phải parse thành số nguyên có kiểm tra lỗi và đối chiếu thời gian.

Ví dụ:

| Header value | Có chấp nhận định dạng? | Vì sao |
| --- | --- | --- |
| `1767268800` | Có | Epoch seconds hợp đồng. |
| `01767268800` | Không | Có leading zero. |
| `1767268800000` | Không | 13 chữ số, thường là milliseconds. |
| `+1767268800` | Không | Prefix cộng không thuộc canonical format. |
| `1767268800.0` | Không | Decimal/floating-point. |
| ` 1767268800 ` | Không ở tầng parser core | HTTP adapter có thể trim OWS theo **hợp đồng header**, sau đó parser nhận đúng value canonical. |
| `١٧٦٧٢٦٨٨٠٠` | Không | Chữ số không phải ASCII. |
| Chuỗi trống hoặc duplicate header | Không | Không phải một timestamp duy nhất. |

Ngay cả timestamp có format hợp lệ cũng bị từ chối nếu quá cũ, quá xa tương lai hoặc server clock health không đạt. **Kết quả format validation không chứng minh MAC**, vì header chưa được xác thực.

## 4. Timestamp phải gắn với canonical request và shared secret

Giả sử client gửi:

```http
POST /v1/tenants/t-42/payments?mode=online HTTP/1.1
Host: payments.example.test
Content-Type: application/json
X-HMAC-Key-Id: partner-17:k3
X-HMAC-Timestamp: 1767268800
X-HMAC-Nonce: 9fc41749ac56ccfd4589b032779f6aee
X-HMAC-Signature: <base64-full-mac>

{"amountMinor":125000,"currency":"VND"}
```

Timestamp ở trên dành cho **fixture thời gian 2026-01-01T12:00:00Z**, **không** dùng nguyên để gửi request trong sản phẩm hiện tại. Header signature là placeholder, không phải chữ ký tính sẵn.

Hợp đồng giảng dạy `HMAC-REQUEST/CLOCK-V1` yêu cầu:

| Thành phần | Giá trị và quy tắc |
| --- | --- |
| Algorithm | HMAC-SHA256, full 32-byte tag; metadata key server ghim algorithm. |
| Method | `POST`, chính xác HTTP method được thực thi. |
| URI | Raw origin-form request target; query giữ nguyên byte/thứ tự theo contract. |
| Audience | `payments-api/prod` từ cấu hình dịch vụ và metadata key server. |
| Signed header | `Content-Type`, `X-HMAC-Key-Id`, `X-HMAC-Timestamp`, `X-HMAC-Nonce` đều singleton, được đưa vào canonical. |
| Timestamp | Epoch seconds canonical, dùng clock phía client lúc tạo chữ ký và clock server để quyết định freshness. |
| Nonce | 16 byte ngẫu nhiên mật mã, encode 32 hex lowercase, khác nhau cho các attempt. |
| Body digest | SHA-256 của **raw body bytes sau HTTP framing**, 64 ký tự hex lowercase; không parse/serialize lại JSON. |
| Encoding | UTF-8, **10 dòng** nối bằng LF `0x0A`, không có LF cuối. |
| Tag transport | Header `X-HMAC-Signature` chứa Base64 chuẩn có padding của **32-byte MAC** (44 ký tự). |
| Window | `maxPastAge=300s`, `maxFutureSkew=30s`, **bao gồm hai biên**. |

Canonical request mẫu (dòng digest phải được thay bằng giá trị thật trước khi ký):

```text
HMAC-REQUEST/CLOCK-V1
HMAC-SHA256
POST
/v1/tenants/t-42/payments?mode=online
audience:payments-api/prod
content-type:application/json
x-hmac-key-id:partner-17:k3
x-hmac-timestamp:1767268800
x-hmac-nonce:9fc41749ac56ccfd4589b032779f6aee
body-sha256:<lowercase-hex-sha256-of-raw-json-bytes>
```

HMAC tính trên **đúng những byte được ký**, không trên các giá trị timestamp đã “sửa” về thời gian hiện tại. Kiểm tra freshness là phép **so policy** sau khi chữ ký đã được xác minh, không phải một phần normalization.

### 4.1 Lỗi bảo mật nếu timestamp không được ký

Một request vốn được ký ngày hôm qua có thể bị attacker phát lại. Nếu timestamp chỉ nằm trong header ngoài canonical và server vẫn tin header đó, attacker có thể thay timestamp thành hiện tại; MAC trên method/URI/body giữ nguyên vẫn pass.

Cách phòng tránh:

- Client đưa **chính xác giá trị** `X-HMAC-Timestamp` vào canonical.
- Server lấy đúng một header timestamp, dùng giá trị đã validate để dựng canonical từ request thật.
- HMAC kiểm tra giá trị đó có bị thay không.
- Chỉ sau khi HMAC đúng mới xem timestamp là **đã được người biết secret xác thực**, nhưng vẫn phải kiểm tra nó có nằm trong time window và đáp ứng chính sách clock health.

Tương tự, nonce cũng phải được ký. Nếu nonce không nằm trong MAC, attacker có thể thay một nonce mới để vượt replay detection.

### 4.2 Ký đúng timestamp không tự tạo “trust” cho đồng hồ client

Bên biết secret có thể tự ký **bất cứ timestamp** nào, kể cả một timestamp cách xa hiện tại hoặc timestamp trong tương lai được client cố tình đặt sai. HMAC bảo đảm *tính xác thực của giá trị mà bên ký đã khai*, không bảo đảm giá trị đó trùng thời gian thực.

Chỉ **server clock đủ tin cậy + freshness policy** mới quyết định timestamp có phù hợp không. Clock skew policy là cơ chế cân bằng **availability và giới hạn replay**, không phải phương pháp chứng minh một sự kiện đã xảy ra đúng thời gian mà client khai.

## 5. Đồng hồ nào nên dùng trong Java và hệ thống phân tán?

### 5.1 Wall clock cho timestamp; monotonic clock cho elapsed duration

| Cơ chế | API Java điển hình | Dùng cho | Không nên dùng cho |
| --- | --- | --- | --- |
| Wall clock / UTC epoch | `Clock.instant()`, `Instant.now(clock)` | Timestamp HTTP được ký, so với server time, audit time | Đo khoảng thời gian nội bộ nếu clock có thể step. |
| Monotonic elapsed time | `System.nanoTime()` | Đo timeout/duration đã trôi qua trong cùng process | Tạo Unix epoch timestamp hoặc so trực tiếp giữa máy khác nhau. |
| Local human time | `LocalDateTime`/`ZonedDateTime` | Hiển thị cho người dùng, lịch địa phương | Canonical timestamp HMAC nếu không có định nghĩa timezone/offset. |

`System.nanoTime()` không mang epoch time và không đồng bộ giữa các host. Nó chỉ hỗ trợ tính **thời lượng** bằng hiệu hai mốc trong cùng runtime. Không dùng nó làm timestamp gửi trong HTTP.

Trong khi đó, `Clock.systemUTC()` cho wall clock theo UTC, thuận tiện cho timestamp nhưng có thể chịu NTP adjustment, pause/suspend hoặc sửa giờ hệ thống. Vì vậy, các API an ninh quan trọng cần **health check clock** ngoài việc chỉ gọi `Instant.now()`.

### 5.2 NTP/time synchronization là kiểm soát vận hành

Để giảm skew:

1. Đồng bộ clock của client/server qua dịch vụ thời gian được tổ chức cho phép (NTP/chrony hoặc nguồn thời gian tin cậy tương đương).
2. Giám sát **offset so với nguồn chuẩn**, độ ổn định, lần đồng bộ cuối, trạng thái mất đồng bộ và bước nhảy clock.
3. Đảm bảo các replica, region, gateway và worker tham gia quyết định bảo mật có **time synchronization policy** nhất quán.
4. Định nghĩa ngưỡng health cho clock, ví dụ offset tuyệt đối so với nguồn đáng tin vượt giới hạn thì **không xác minh request như bình thường**.
5. Có runbook cho VM/container suspend/resume, host reboot, NTP source lỗi, leap-second event và thay đổi môi trường.
6. Dùng số liệu clock skew và lỗi timestamp để phát hiện client bị lệch đồng hồ, **không tự mở rộng cửa sổ** cho từng client không kiểm soát.

**Không giả định chạy trong container làm đồng hồ độc lập chính xác.** Container thường dùng wall clock của host; một host sai giờ có thể làm toàn bộ replica trên đó sai theo.

### 5.3 Leap seconds, DST và time zone

Unix epoch seconds và `Instant` cho phép protocol tránh chuyển đổi theo giờ địa phương hoặc daylight-saving time (DST). Giờ mùa hè không nên làm timestamp HMAC nhảy một giờ nếu bạn dùng UTC epoch seconds đúng.

Các hệ thống thời gian có thể áp dụng **leap-second handling** hoặc **clock smearing** khác nhau. Điều quan trọng với HMAC request không phải tranh luận cách hiển thị giây nhuận, mà là đảm bảo nguồn clock được quản lý, các replica không lệch vượt tolerance và có test/alert cho sự cố đồng bộ. **Không chuyển sang `LocalDateTime`** để “sửa” lỗi do lệch timezone: nguyên nhân thường nằm ở cách parse hoặc đồng bộ clock, không phải ở HMAC.

## 6. Java 17+: policy kiểm tra timestamp bằng Clock được inject

Mã Java sau cài đặt chính sách `CLOCK-V1`: timestamp Unix epoch seconds dạng chuỗi ASCII canonical; cửa sổ **[-300s, +30s]** tính theo **whole seconds** của đồng hồ server; biên được chấp nhận.

**Thiết kế deliberately narrow:** lớp này chỉ quyết định freshness. Nó **không** tự xác minh HMAC, reserve nonce hoặc cấp quyền. Caller phải ghép nó vào pipeline xác thực đầy đủ.

### 6.1 `SignedTimestampPolicy`: không dùng `Math.abs` hoặc parse tự do

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.regex.Pattern;

public final class SignedTimestampPolicy {
    public enum Verdict {
        ACCEPT,
        MALFORMED,
        TOO_OLD,
        TOO_FAR_IN_FUTURE
    }

    private static final Pattern EPOCH_SECONDS =
            Pattern.compile("(0|[1-9][0-9]{0,11})");

    private final Clock serverClock;
    private final Duration maxPastAge;
    private final Duration maxFutureSkew;

    public SignedTimestampPolicy(
            Clock serverClock,
            Duration maxPastAge,
            Duration maxFutureSkew) {

        this.serverClock = Objects.requireNonNull(serverClock);
        this.maxPastAge = Objects.requireNonNull(maxPastAge);
        this.maxFutureSkew = Objects.requireNonNull(maxFutureSkew);

        if (maxPastAge.isNegative() || maxFutureSkew.isNegative()
                || maxPastAge.getNano() != 0
                || maxFutureSkew.getNano() != 0) {
            throw new IllegalArgumentException(
                    "Windows must be whole nonnegative seconds");
        }
    }

    public Verdict check(String signedEpochSeconds) {
        if (signedEpochSeconds == null
                || !EPOCH_SECONDS.matcher(signedEpochSeconds).matches()) {
            return Verdict.MALFORMED;
        }

        final Instant signed;
        try {
            signed = Instant.ofEpochSecond(
                    Long.parseLong(signedEpochSeconds));
        } catch (RuntimeException invalid) {
            // Bao gồm lỗi parse/Instant range.
            return Verdict.MALFORMED;
        }

        // Chốt độ phân giải giây của contract; tránh tranh luận
        // 0.7 giây ở biên khi client ký epoch seconds integer.
        Instant nowSecond = Instant.ofEpochSecond(
                serverClock.instant().getEpochSecond());

        Instant earliest = nowSecond.minus(maxPastAge);
        Instant latest = nowSecond.plus(maxFutureSkew);

        if (signed.isBefore(earliest)) {
            return Verdict.TOO_OLD;
        }
        if (signed.isAfter(latest)) {
            return Verdict.TOO_FAR_IN_FUTURE;
        }
        return Verdict.ACCEPT;
    }
}
```

**Tại sao dùng `Instant` thay vì `Math.abs(now - signed)`?**

- Phép trừ trên `long` có thể overflow nếu xử lý input lớn hoặc timestamp âm chưa validate.
- `Math.abs(Long.MIN_VALUE)` vẫn âm vì không biểu diễn được giá trị tuyệt đối dương tương ứng.
- Dùng hai biên rõ ràng dễ audit và hỗ trợ **cửa sổ bất đối xứng**, thay vì ép một `abs` đối xứng không có chủ ý.
- `Clock` được inject giúp unit test có thể đóng băng server time bằng `Clock.fixed`.

**Giới hạn của ví dụ:** Trong production, cấu hình các duration cũng cần giới hạn trên theo policy (không cho truyền `Duration.ofDays(3650)`). `serverClock.instant()` không chứng minh clock đang healthy; hãy bổ sung thành phần kiểm tra clock health và **fail-closed** khi không thể tin wall time. Với `Instant` cực hạn hoặc duration cấu hình quá lớn, phép cộng/trừ có thể ném exception; coi đó là lỗi cấu hình và từ chối, không làm fallback pass.

### 6.2 Kiểm thử hai biên bằng `Clock.fixed`

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
        Instant.parse("2026-01-01T12:00:00Z"),
        ZoneOffset.UTC);

SignedTimestampPolicy policy = new SignedTimestampPolicy(
        fixed, Duration.ofSeconds(300), Duration.ofSeconds(30));

check(policy.check("1767268800"),
        SignedTimestampPolicy.Verdict.ACCEPT);             // now
check(policy.check("1767268500"),
        SignedTimestampPolicy.Verdict.ACCEPT);             // -300s
check(policy.check("1767268499"),
        SignedTimestampPolicy.Verdict.TOO_OLD);            // -301s
check(policy.check("1767268830"),
        SignedTimestampPolicy.Verdict.ACCEPT);             // +30s
check(policy.check("1767268831"),
        SignedTimestampPolicy.Verdict.TOO_FAR_IN_FUTURE);  // +31s
check(policy.check("01767268800"),
        SignedTimestampPolicy.Verdict.MALFORMED);
check(policy.check("1767268800000"),
        SignedTimestampPolicy.Verdict.MALFORMED);

// Helper của test; không phải API có sẵn trong JDK.
static void check(
        SignedTimestampPolicy.Verdict actual,
        SignedTimestampPolicy.Verdict expected) {
    if (actual != expected) {
        throw new AssertionError(
                "Expected " + expected + " but got " + actual);
    }
}
```

Trong một file Java thực tế, khai báo helper `check` bên trong class test thay vì ở top-level script nếu chạy dưới dạng `javac`. Những giá trị số trên là fixtures cố định, **không** phải timestamps có thể tiếp tục gửi trong production.

### 6.3 Mô phỏng skew bằng Clock.offset

Java `Clock.offset` hữu ích để test client nhanh/chậm so với server, mà không thay system clock thật:

```java
Clock server = Clock.fixed(
        Instant.parse("2026-01-01T12:00:00Z"),
        ZoneOffset.UTC);

Clock clientAhead25s = Clock.offset(
        server, Duration.ofSeconds(25));
Clock clientAhead90s = Clock.offset(
        server, Duration.ofSeconds(90));
Clock clientBehind120s = Clock.offset(
        server, Duration.ofSeconds(-120));

SignedTimestampPolicy verifier = new SignedTimestampPolicy(
        server, Duration.ofSeconds(300), Duration.ofSeconds(30));

String ahead25 = Long.toString(
        clientAhead25s.instant().getEpochSecond());
String ahead90 = Long.toString(
        clientAhead90s.instant().getEpochSecond());
String behind120 = Long.toString(
        clientBehind120s.instant().getEpochSecond());

if (verifier.check(ahead25)
        != SignedTimestampPolicy.Verdict.ACCEPT) {
    throw new AssertionError("Allowed future skew rejected");
}
if (verifier.check(ahead90)
        != SignedTimestampPolicy.Verdict.TOO_FAR_IN_FUTURE) {
    throw new AssertionError("Excessive future skew accepted");
}
if (verifier.check(behind120)
        != SignedTimestampPolicy.Verdict.ACCEPT) {
    throw new AssertionError("Allowed past skew rejected");
}
```

Đây là cách test đúng **policy clock skew**, không yêu cầu NTP thật. Với integration test đa replica, cần tạo các clock giả lập **khác nhau cho từng verifier** để phát hiện chính sách trả kết quả khác nhau khi các node không đồng bộ.

## 7. Timestamp ở phía client: ký vào lúc nào?

Một client signer dùng Java 17 có thể tạo timestamp:

```java
import java.security.SecureRandom;
import java.time.Clock;
import java.util.HexFormat;

public final class HmacFreshnessFields {
    private static final SecureRandom RNG = new SecureRandom();

    private HmacFreshnessFields() {}

    public record Values(String epochSeconds, String nonceHex) {}

    public static Values newAttempt(Clock clientClock) {
        byte[] nonce = new byte[16];
        RNG.nextBytes(nonce);

        return new Values(
                Long.toString(clientClock.instant().getEpochSecond()),
                HexFormat.of().formatHex(nonce));
    }
}
```

Cách dùng:

```java
HmacFreshnessFields.Values freshness =
        HmacFreshnessFields.newAttempt(Clock.systemUTC());

String timestampHeader = freshness.epochSeconds();
String nonceHeader = freshness.nonceHex();

// Đưa ĐÚNG hai chuỗi vào canonical bytes trước khi HMAC.
```

### 7.1 Tạo timestamp càng gần thời điểm gửi càng tốt

Trình tự an toàn hơn:

```text
Serialize/freeze body bytes
    -> xây raw request target + signed headers
    -> tạo timestamp và nonce mới cho attempt này
    -> đưa timestamp, nonce vào canonical request
    -> HMAC secret trên canonical bytes
    -> gửi snapshot đúng như đã ký
```

Nếu request nằm trong hàng đợi vài phút **sau khi ký** rồi mới được gửi, chữ ký vẫn đúng nhưng timestamp có thể quá cũ khi server nhìn thấy. SDK cần quy định thời gian tối đa giữa sign và send; nếu vượt ngưỡng, **ký lại một attempt mới** với nonce mới, sau khi đã bảo đảm replay/idempotency của operation.

### 7.2 “Tự cộng offset client” có phải giải pháp không?

Một client có clock bị lệch có thể muốn hiệu chỉnh timestamp dựa vào giờ server:

- **Ưu tiên sửa/sync wall clock** qua hạ tầng đáng tin.
- Nếu SDK dùng server-time hint, phải lấy từ **endpoint HTTPS được xác thực**, tính cả network RTT/uncertainty, giới hạn độ lệch chấp nhận và lưu telemetry; không dùng thông tin thời gian do bên thứ ba hoặc một HTTP header chưa xác thực tự khai.
- Không để attacker gửi `X-Server-Time` hoặc giả `Date` rồi ép client ký timestamp tùy ý.
- Không để client tự gửi `X-Clock-Offset` và yêu cầu server cộng offset đó vào freshness check; như vậy bên có key có thể tự nới cửa sổ không có giới hạn.
- Khi vượt time window, **không tạo lại cùng signed attempt với nonce cũ** mà không tính đến server có thể đã chấp nhận attempt trước đó.

Nếu server cung cấp thông báo `timestamp_out_of_window` và một mốc server time cho hỗ trợ vận hành, cần cân nhắc **khả năng attacker dùng response để suy ra thời gian hoặc dò key ID**, và xác thực kênh truyền. Bên server không nên thay timestamp client trong canonical để làm chữ ký “khớp”.

### 7.3 Retry, queue và idempotency

Đối với yêu cầu có side effect như thanh toán:

1. Attempt đầu tiên có timestamp/nonce/HMAC riêng.
2. Nếu timeout, server **có thể đã xử lý thành công** mặc dù client không nhận được response.
3. Attempt retry muốn qua freshness/replay policy có thể cần **timestamp và nonce mới** cùng chữ ký HMAC mới.
4. Để không tạo giao dịch trùng, dùng **idempotency key** gắn với principal/operation/payload; nếu header do client cung cấp ảnh hưởng nghiệp vụ thì phải ký nó hoặc áp dụng kiểm soát tương đương.
5. **Nonce không phải idempotency key**. Nonce chống dùng lại cùng signed attempt; idempotency chống lặp ý định nghiệp vụ qua **nhiều attempt hợp lệ**.

## 8. Skew và TTL nonce: hai công thức phải được thiết kế cùng nhau

Timestamp giới hạn khoảng thời gian request được chấp nhận. **Nonce store** ngăn request đã ký bị sử dụng lại trong khoảng đó. Nếu TTL nonce quá ngắn, request cũ vẫn có timestamp hợp lệ trong khi dấu vết nonce đã hết hạn; attacker có thể **replay lần thứ hai** dù MAC đúng.

### 8.1 Khoảng chấp nhận tối đa của một timestamp

Với timestamp cố định `T` và clock server hoàn toàn chính xác:

```text
T hợp lệ khi:
  now - maxPastAge <= T <= now + maxFutureSkew

Suy ra:
  T - maxFutureSkew <= now <= T + maxPastAge

Độ dài khoảng một T có thể được chấp nhận:
  maxPastAge + maxFutureSkew
```

Với `maxPastAge = 300` và `maxFutureSkew = 30`:

```text
Earliest acceptable server now = T - 30s
Latest acceptable server now   = T + 300s
Max acceptance lifetime        = 330s
```

Nếu nonce được reserve ngay lần chấp nhận sớm nhất, dấu vết phải còn tồn tại đến sau lần chấp nhận muộn nhất; **TTL chỉ 300 giây là thiếu** cho cửa sổ ví dụ. Một TTL 360 giây có thể được chọn cho demo với 30 giây dự phòng **nếu tất cả giả định về lệch đồng hồ và độ trễ được đáp ứng**.

### 8.2 Replica skew có thể kéo dài khoảng replay

Nếu nhiều replica có clock lệch nhau tới `±ε` so với thời gian chuẩn, request có thể được chấp nhận sớm hơn trên node chạy nhanh/chậm theo từng phía và muộn hơn trên node khác. Một biên bảo thủ cho khoảng tồn tại của một timestamp theo thời gian thực là:

```text
requiredNonceTtl >= maxPastAge
                    + maxFutureSkew
                    + 2 * maxServerClockError
                    + operationalSafetyMargin
```

Đây là **mô hình dự phòng đơn giản** dưới giả định từng replica lệch tối đa `±maxServerClockError`. Cần tính thêm clock behavior của **nonce store**, delay commit/replication, eventual consistency và chính sách thời điểm reserve; không lấy công thức làm chứng minh chính xác cho mọi kiến trúc.

Ví dụ nếu:

```text
maxPastAge          = 300s
maxFutureSkew       = 30s
maxServerClockError = 5s  mỗi replica
safetyMargin        = 20s

TTL tối thiểu theo mô hình = 300 + 30 + 2*5 + 20 = 360s
```

**Một giới hạn quan trọng:** Cửa sổ thời gian và TTL chỉ đúng khi **đồng hồ nằm trong mức sai số được phép**. Nếu một replica nhảy lùi vài phút không được phát hiện, không TTL “bình thường” nào bảo đảm replay không được chấp nhận. Hãy **fail-closed** ở node clock unhealthy, thay vì tăng TTL vô hạn.

### 8.3 Atomic reserve nonce

Một thao tác trên Redis có thể là:

```redis
SET hmac:nonce:payments-api-prod:partner-17:9fc41749ac56ccfd4589b032779f6aee 1 NX EX 360
```

- `NX` ghi nonce **chỉ nếu key chưa tồn tại**, bảo đảm atomic insert khi nhiều replica cùng xử lý.
- `EX` đặt expiration trong cùng thao tác, tránh hai lệnh `SET` và `EXPIRE` không nguyên tử.
- `360` là TTL của ví dụ có phân tích ở trên, không phải giá trị mặc định áp dụng mọi API.
- Namespace nonce phải khớp **replay security domain**. Nếu cần chặn cùng nonce giữa hai key versions đang rotation, dùng scope theo **principal + audience**, không chỉ key ID; với các client song song phải đảm bảo nonce đủ entropy.
- Nếu replay store bị partition, reset, phục hồi snapshot cũ hoặc không đảm bảo atomic/consistency theo thiết kế, phải đánh giá lại ranh giới replay. **Không cho qua** khi không thể reserve chắc chắn.

Trong deployment nhiều region, một Redis riêng mỗi region mà không đồng bộ có thể cho **cùng nonce được chấp nhận ở hai nơi**. Cần một kho nonce chung có bảo đảm thích hợp hoặc kiến trúc partitioning nhất quán theo principal, không chỉ kiểm tra `SET NX` ở từng local cache.

### 8.4 Vì sao phải reserve nonce sau MAC?

Nếu lưu nonce trước khi xác minh MAC, kẻ không biết secret có thể gửi hàng loạt request chứa một key ID hợp lệ và nonce của người khác, làm tiêu hao nonce store hoặc gây **nonce poisoning/DoS**. Luồng phổ biến:

```text
validate public input
  -> lookup allowed key + calculate expected HMAC
  -> compare MAC constant-time
  -> check timestamp policy với clock healthy
  -> atomic reserve nonce
  -> tạo principal và authorization
```

Có thể **reject timestamp rõ ràng sai từ sớm** để tiết kiệm tài nguyên; trước MAC, đó mới là **preflight trên giá trị chưa xác thực**, tuyệt đối không tạo principal hoặc ghi nonce. Khi request quá lớn, cần size/time/admission quota trước khi tiêu thụ body, vì attacker vẫn có thể làm tốn tài nguyên dù chưa biết secret.

## 9. Upload dài: kiểm tra timestamp tại ingress hay lúc verify xong?

Một request ký HMAC trên SHA-256 của **toàn body** chưa thể verify xong trước khi nhận đủ body. Với upload 2 GiB hoặc mạng chậm, quá trình truyền có thể kéo dài 10 phút hoặc hơn, lớn hơn cửa sổ quá khứ 300 giây.

Có hai cách hợp đồng khác nhau:

| Cách chọn mốc thời gian | Ưu điểm | Rủi ro và điều kiện |
| --- | --- | --- |
| **Kiểm tra freshness tại thời điểm verify xong/EOF** | Đơn giản, chặt về thời gian cho phép commit | Upload hợp lệ có thể hết hạn trong quá trình truyền. |
| **Ghi nhận arrival timestamp tại ingress tin cậy, kiểm tra freshness so với arrival** | Hỗ trợ request ký hợp lệ đến trước deadline nhưng truyền body dài | Cần provenance bảo vệ của arrival time, upload duration deadline, replay nonce và chính sách anti-replay xuyên replica; không cho attacker tự khai arrival time. |

Bài chọn **verify-time policy**: timestamp phải hợp lệ **tại thời điểm server đã dựng đủ canonical bytes và kiểm tra HMAC**, không chỉ lúc nhận headers. Một preflight tại ingress có thể giúp từ chối sớm timestamp hiển nhiên sai, nhưng **phải kiểm tra lại** sau EOF.

### 9.1 Điều gì xảy ra nếu ký trước upload 12 phút?

```text
t=0      Client ký và bắt đầu gửi upload.
t=1s     Server thấy header: timestamp còn mới.
t=12min  Server nhận đủ body, tính HMAC.
         Timestamp đã cũ >300s: server từ chối.
```

Đây không phải bug của `HmacSHA256`. Đó là **mismatch giữa độ dài upload và freshness policy**. Không sửa bằng cách cho phép server tự thay timestamp mới khi giữ MAC cũ: như vậy phá cam kết signature.

Các giải pháp hợp lệ:

- Quy định max upload duration phù hợp cửa sổ thời gian.
- Tách upload thành **session khởi tạo đã xác thực**, staging object tạm với hạn dùng, rồi commit sau verify theo một protocol mới.
- Dùng **resumable/chunk-signing** với per-chunk MAC, sequence/chunk index, session binding và anti-replay rõ ràng.
- Chọn acceptance-at-ingress policy có ghi nhận arrival ở trust boundary, kiểm soát duration và replay đầy đủ.
- Nếu nới freshness window cho endpoint đặc thù, phải đánh giá và tăng nonce TTL/quota tương ứng, không đổi ngầm cho mọi API.

### 9.2 Thứ tự xử lý side effect vẫn không đổi

Dù kiểm tra freshness ở ingress hay EOF, **không cho body chưa được HMAC toàn request xác minh tạo side effect**. Nếu cần nhận dữ liệu sớm, spool cách ly và giới hạn dung lượng/timeout; chỉ sau HMAC, replay và authorization mới publish object, ghi DB hoặc gửi message queue. Có thể chuyển dữ liệu qua gateway nhưng phải bảo toàn byte đã ký và bảo vệ trust boundary.

## 10. Java 17+: tích hợp clock policy với HMAC verifier

Đây là **pseudocode pipeline**, vì HTTP adapter, key registry, nonce store và authorization phụ thuộc hệ thống cụ thể. `SignedTimestampPolicy` ở mục 6 là class Java có thể biên dịch độc lập.

```java
// PSEUDOCODE: các interface bên dưới thuộc ứng dụng,
// không phải JDK. Không cho request chưa xác thực tạo side effect.
ValidatedRequest req = ingress.parseAndValidate(httpRequest);

// Format/header occurrence phải được kiểm tra: đúng một keyId,
// timestamp, nonce, chữ ký; URI/raw body/signed headers nhất quán.
String keyId = req.requiredUniqueHeader("X-HMAC-Key-Id");
String timestamp = req.requiredUniqueHeader("X-HMAC-Timestamp");
String nonce = req.requiredUniqueHeader("X-HMAC-Nonce");

// Lookup key chính xác theo ID nhưng chưa tạo principal.
// Policy server ghim secretRef/algorithm/version/audience.
KeyMetadata key = keyRegistry.lookupExactAllowed(keyId);
if (key == null
        || !key.canVerifyNow()
        || !"CLOCK-V1".equals(key.canonicalVersion())
        || !"HmacSHA256".equals(key.algorithm())
        || !"payments-api/prod".equals(key.audience())) {
    rejectAuthenticationGeneric();
    return;
}

// Preflight timestamp chỉ dùng để reject sớm và không tin nó là identity.
if (timestampPolicy.check(timestamp)
        != SignedTimestampPolicy.Verdict.ACCEPT) {
    rejectAuthenticationGeneric();
    return;
}

// Server dựng canonical từ HTTP request thật.
// Ở upload lớn, stream/spool + hash raw body đến EOF hợp lệ trước verify.
byte[] canonical = canonicalizer.buildFromValidatedRequest(req, key);
SecretKey secret = secretStore.loadByTrustedReference(key.secretRef());

if (!hmacVerifier.verifyFullTagConstantTime(
        secret, canonical, req.requiredUniqueHeader("X-HMAC-Signature"))) {
    rejectAuthenticationGeneric();
    return;
}

// Tại điểm chấp nhận cuối cùng, cần clock health,
// timestamp mới và key status/revision còn hiệu lực.
if (!clockHealth.isHealthy()
        || timestampPolicy.check(timestamp)
                != SignedTimestampPolicy.Verdict.ACCEPT
        || !keyRegistry.stillCurrentAndVerifiable(key)) {
    rejectAuthenticationGeneric();
    return;
}

// Kho nonce dùng chung giữa mọi replica; atomic reserve hoặc fail-closed.
// Lỗi store khác nonce trùng; không đổi lỗi store thành "nonce mới".
NonceResult nonceResult = nonceStore.tryReserve(
        key.principalId(), key.audience(), nonce,
        Duration.ofSeconds(360));

if (nonceResult != NonceResult.RESERVED) {
    rejectReplayOrUnavailable(nonceResult);
    return;
}

AuthenticatedPrincipal principal =
        identities.fromVerifiedKey(key);

if (!authorization.canCreatePayment(
        principal, req.actualTenant(), req.actualResource())) {
    rejectForbidden();
    return;
}

paymentsService.createVerifiedPayment(principal, req);
```

**Lưu ý:** `createVerifiedPayment` ở đây **không đọc `Idempotency-Key` chưa được ký**. Contract CLOCK-V1 chỉ nêu các signed fields cơ bản, không tự cấp quyền dùng một header idempotency từ client. Với nghiệp vụ production cần retry an toàn, phải **mở rộng canonical contract để ký `Idempotency-Key`** (hoặc xây dựng một cơ chế idempotency server-side được ràng buộc an toàn) trước khi dùng nó để quyết định hành vi. Không lấy một header chưa ký để trả dữ liệu của giao dịch khác.

### 10.1 Vì sao có hai lần check timestamp trong pipeline?

- **Trước đọc body/secret:** kiểm tra sơ bộ input để giảm tải, **không** xác nhận danh tính.
- **Sau HMAC khi chuẩn bị accept:** đảm bảo timestamp vẫn hợp lệ và clock healthy. Với body lớn, timestamp có thể hết hạn giữa hai lần.

Không bắt buộc mọi triển khai phải làm hai lần; **lần sau** phải nhất quán với acceptance-time policy được công bố. Nếu preflight không đáng tin hoặc tạo leak thông tin nhạy cảm, có thể hoãn kiểm tra freshness đến sau MAC, nhưng vẫn phải có request size/timeout/rate limit.

### 10.2 HMAC đúng, clock lỗi thì sao?

Một node có clock health không đạt không nên nói “HMAC đúng nên cho qua”. Có ba lựa chọn vận hành:

1. **Fail-closed** ngay trên node và chuyển traffic tới node healthy.
2. Dừng nhận request được bảo vệ bằng timestamp, hiển thị tình trạng unavailable thay vì authentication pass.
3. Khôi phục đồng bộ thời gian rồi kiểm tra lại cả key status và replay store trước khi mở traffic.

Không tự bật “infinite time window”, bỏ nonce check hoặc chọn timestamp do client tự khai làm thời gian hiện tại. Nếu cần tính sẵn sàng cao, đầu tư vào redundancy của nguồn thời gian và admission control, không giảm ràng buộc chống replay.

## 11. Skew của nhiều replica và proxy/gateway

Một client gửi đúng một signed request. Replica A có clock nhanh +20 giây, replica B chậm -20 giây:

```text
Client signed timestamp = T

Replica A sees now = realNow + 20s
Replica B sees now = realNow - 20s

At same realNow:
   A tính request cũ hơn thực tế 20s.
   B tính request mới hơn thực tế 20s.
```

Gần biên thời gian, request có thể **pass ở A và fail ở B**. Nếu load balancer retry sang B, việc có cùng nonce chưa chắc tạo kết quả giống nhau vì A có thể đã reserve nonce trước đó. Đó là lý do cần:

- Đồng bộ/giám sát clock tất cả replica.
- Clock health policy, cảnh báo offset vượt tolerance.
- Một replay store có bảo đảm atomic/consistency phù hợp với routing vùng.
- Chính sách retry/idempotency không giả định “request fail ở một node có thể tự retry vô hạn ở node khác”.
- Kiểm thử biên time window đồng thời trên nhiều node với `Clock.offset`.

### 11.1 API gateway có clock khác backend

Nếu gateway xác minh HMAC và chống replay, **clock gateway** dùng để kiểm tra freshness; backend không nên âm thầm kiểm tra lại request bằng một clock khác và trả kết quả thiếu nhất quán mà không có contract. Khi backend còn phải kiểm tra expiry của authorization token/permission, đó là kiểm soát riêng và cần clock khỏe ở backend.

Nếu gateway chỉ chuyển tiếp request và backend mới verify, clock backend quyết định; gateway không được tự khai `X-Verified-At` do client gửi làm server time. Khi dùng **arrival timestamp** tin cậy từ gateway, phải strip/overwrite header do Internet gửi, xác thực kênh và ràng buộc arrival với đúng raw request/route, không để backend tin bất kỳ thời gian forwarded nào.

### 11.2 Proxy rewrite cũng có thể bị hiểu nhầm là lỗi clock

Một request bị trả `401 invalid signature` có thể do:

- `%2F` trong URI bị gateway decode thành slash trước verifier.
- Thứ tự query đổi, signed header được trim khác.
- Body gzip/JSON bị transform, SHA-256 body khác.
- Header `X-HMAC-Timestamp` bị proxy chuẩn hóa hoặc mất duplicate.
- Key ID/secret vừa rotate, node dùng metadata cũ.
- **Timestamp thật sự quá cũ hoặc quá xa tương lai.**

Không nên kết luận mọi `401` là clock skew. Cần phân loại lỗi nội bộ bằng telemetry an toàn và so golden vector byte-level tại điểm ký/verify. Đừng sửa mismatch bằng cách thử nhiều canonical version hay tăng time window bừa bãi.

## 12. Cửa sổ thời gian ảnh hưởng thế nào đến bảo mật?

### 12.1 Bảng trade-off

| Quyết định | Tác động availability | Tác động security/operations |
| --- | --- | --- |
| `maxPastAge` rất nhỏ (vài giây) | Dễ loại request mạng chậm, queue hoặc clock lệch | Giảm replay exposure nhưng yêu cầu sync tốt, nonce storage vẫn cần. |
| `maxPastAge` vài phút | Phù hợp nhiều HTTP API thông thường | Nonce TTL dài hơn, cần rate limit và chống replay. |
| `maxFutureSkew` quá rộng | Client đi nhanh ít gặp lỗi | Mở rộng khoảng chấp nhận cho một timestamp **trước thời điểm nó khai**, tăng lifetime nonce. |
| Chỉ kiểm tra timestamp mà không dùng nonce | Nhiều request cũ vẫn pass trong cửa sổ | Replay cùng signed request có thể tạo side effect lặp. |
| Dùng nonce store per-region rời rạc | Nhanh ở từng region | Cùng signed request có thể được chấp nhận ở nhiều vùng. |
| Bỏ freshness check khi NTP lỗi | Tạm tăng availability | Có thể chấp nhận request cũ/tương lai không giới hạn. |
| Kiểm tra clock health và fail-closed | Có thể gây 503 khi nguồn thời gian lỗi | Giữ được giới hạn an ninh; cần redundancy và runbook. |

Không có một cặp ngưỡng chính xác cho mọi API. Với tài chính, key nhạy cảm, đa region hoặc upload dài, chính sách phải dựa trên threat model, network distribution, nguồn thời gian và SLO. **Tăng window không bao giờ là cách thay thế nonce**.

### 12.2 Timestamp không chứng minh thứ tự nghiệp vụ

Hai request có timestamp bằng nhau, hoặc request B có timestamp lớn hơn A, **không chứng minh B phải được thực thi sau A**. Network có thể reorder; client clock có thể skew; một bên có secret có thể khai một timestamp tương lai vẫn nằm trong window.

Nếu nghiệp vụ cần thứ tự (ví dụ cập nhật số dư, trạng thái giao dịch), dùng **version/sequence/transaction constraints** có cơ chế đồng bộ, không chỉ so timestamp HMAC. Nonce cũng không cấp thứ tự; nonce ngẫu nhiên chỉ là unique attempt identifier.

### 12.3 Không cho client chọn time window

Một số header nguy hiểm nếu server tin:

```http
X-Allowed-Clock-Skew: 86400
X-Request-Accepted-At: 2026-01-01T12:00:00Z
X-HMAC-Ignore-Time: true
```

Trong CLOCK-V1, chúng **không thay đổi** server policy. Nếu sản phẩm cần allowance riêng cho client, phải cấu hình **server-side key/endpoint profile** có hạn mức và lifecycle quản trị; tránh client chỉ ký một header `skew=1day` rồi được tự nới giới hạn. Nếu thay đổi danh sách các field được ký hoặc cách timestamp được diễn giải, ban hành **canonical format version mới** và golden vectors.

## 13. Ma trận kiểm thử clock skew và HMAC request

Dùng `Clock.fixed`/`Clock.offset`, secret chỉ dành cho test, body fixture đúng bytes và nonce store giả lập có thao tác atomic. Mọi test integration nên kiểm tra **không phát sinh side effect** khi authentication, freshness, replay hoặc authorization thất bại.

| Case | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| T01 | Signed timestamp chính xác bằng server epoch second. | Freshness pass nếu HMAC, key, nonce đúng. |
| T02 | `signed − now = -300s`. | **Pass**, biên quá khứ được bao gồm. |
| T03 | `signed − now = -301s`. | Reject `TOO_OLD`. |
| T04 | `signed − now = +30s`. | **Pass**, biên tương lai được bao gồm. |
| T05 | `signed − now = +31s`. | Reject `TOO_FAR_IN_FUTURE`. |
| T06 | Client offset +25s, server clock đúng. | Timestamp trong dung sai tương lai. |
| T07 | Client offset +90s, server clock đúng. | Reject, không tự tăng allowance. |
| T08 | Client offset -120s, delay 1s. | Vẫn có thể pass; tính theo server verify-time. |
| T09 | Client offset -299s và network delay 5s. | Có thể vượt -300s, reject do tổng lệch. |
| T10 | Timestamp milliseconds 13 chữ số. | Reject format, không tự chia 1000 ngoài contract. |
| T11 | Timestamp có leading zero/decimal/`+`/Unicode digit. | Reject canonical syntax. |
| T12 | Timestamp không tồn tại hoặc hai header timestamp. | Reject trước khi chọn một giá trị tùy ý. |
| T13 | Chỉnh timestamp sau khi client tính HMAC. | MAC fail vì timestamp được ký. |
| T14 | Timestamp hợp lệ nhưng HMAC sai. | Authentication fail, không reserve nonce. |
| T15 | HMAC đúng nhưng timestamp quá cũ. | Authentication fail, không chạy nghiệp vụ. |
| T16 | HMAC đúng nhưng timestamp quá xa tương lai. | Authentication fail, không chạy nghiệp vụ. |
| T17 | Clock health bị mất đồng bộ dù HMAC/timestamp nhìn đúng. | Fail-closed hoặc tạm unavailable. |
| T18 | Đồng hồ server nhảy lùi 2 phút. | Phát hiện health/step, không âm thầm cho phép replay kéo dài. |
| T19 | Node A nhanh +20s, node B chậm -20s. | Kiểm thử khác biệt sát biên và cấu hình clock health. |
| T20 | Request pass trên một replica, replay sang replica khác. | Kho nonce dùng chung chặn lần tiếp theo. |
| T21 | Hai request cùng nonce được verify đồng thời trên hai replica. | Chỉ một atomic reserve thành công. |
| T22 | Nonce TTL chỉ 300s với cửa sổ 300+30. | Test phát hiện replay sau TTL ở biên; cấu hình bị từ chối. |
| T23 | Nonce TTL >= 330s + skew/margin phù hợp. | Nonce được giữ suốt lifetime timestamp có thể pass. |
| T24 | Redis/noncestore outage. | Fail-closed, không coi nonce mới. |
| T25 | Kho nonce local riêng từng region. | Test phát hiện replay cross-region; yêu cầu thiết kế consistency. |
| T26 | Client ký rồi giữ trong queue 6 phút. | Verify-time policy reject nếu quá cũ. |
| T27 | Upload 10 phút, preflight ban đầu pass, EOF đã hết hạn. | Reject theo policy kiểm tra lại lúc verify. |
| T28 | Client gửi lại cùng chữ ký sau lỗi mạng. | Nonce replay hoặc expired; không bỏ kiểm tra. |
| T29 | Client ký attempt mới với nonce mới cho cùng payment intent. | Authentication có thể pass; idempotency ngăn trùng nghiệp vụ. |
| T30 | Gateway gửi header `X-Verified-At` do client tự khai. | Backend không tin untrusted time metadata. |
| T31 | Raw URI/query đổi sau khi client ký, timestamp vẫn đúng. | HMAC fail; không đổ lỗi cho skew. |
| T32 | Body được serialize lại sau ký, timestamp vẫn đúng. | Body hash/HMAC fail. |
| T33 | Key revoke lúc request đang upload dù timestamp được ký trước revoke. | Recheck key hiện tại, authentication fail. |
| T34 | Rotation key k3→k4, cả hai ghim cùng CLOCK-V1. | Tra đúng key ID, không thử secret cũ/mới tùy ý. |
| T35 | Header client yêu cầu `X-Allowed-Clock-Skew:86400`. | Không thay đổi window server-side; reject nếu policy cấm header. |
| T36 | HMAC và nonce đúng nhưng principal truy cập tenant ngoài grant. | Authentication pass; authorization reject. |
| T37 | Java/Go/Node dùng fixture epoch 1767268800. | Cùng boundary verdict, canonical bytes và HMAC. |
| T38 | DST/timezone hệ điều hành đổi, epoch seconds không đổi. | Freshness không lệ thuộc giờ hiển thị địa phương. |
| T39 | `Math.abs(Long.MIN_VALUE)` trong comparator cũ. | Test phát hiện overflow; dùng window comparisons an toàn. |
| T40 | Node không thể chứng minh độ chính xác clock, tiếp tục nhận request. | Vi phạm policy; chuyển trạng thái unhealthy/fail-closed. |
| T41 | Timestamp đã ký lệch +30s nhưng request đến chậm 35s. | Đánh giá với thời gian verify thực tế; timestamp có thể pass ở phía quá khứ. |
| T42 | Clock bị sửa tiến lên 1 giờ rồi khôi phục. | Health alert, không tự hồi tố quyền verify hoặc reset nonce state. |

### 13.1 Golden vector nên có những gì?

Một fixture đủ để hai bên làm độc lập cần:

- `canonicalVersion`, algorithm HMAC, key ID và **test secret bytes**.
- Method/raw origin-form target, signed header values, raw body bytes.
- Timestamp epoch seconds **nguyên văn** được ký, nonce và định dạng header.
- Canonical request text/bytes chính xác, UTF-8/LF không có LF cuối.
- Body SHA-256, expected raw HMAC tag 32 byte và Base64 signature.
- Server clock fixture (ví dụ `2026-01-01T12:00:00Z`), `maxPastAge`, `maxFutureSkew`, biên bao gồm.
- Expected `ACCEPT`/`TOO_OLD`/`TOO_FAR_IN_FUTURE`/`MALFORMED` của từng giá trị signed timestamp.
- Nonce store state/TTL, key status/rotation và authorization decision riêng.

Hai implementation có thể cùng sai khi “client dùng signer của server để test”, vì vậy cần một bộ **golden vectors độc lập**. Ngoài test method `check` đơn lẻ, cần kiểm chứng phía server không reserve nonce khi MAC sai, không side effect khi time window fail, và không chọn principal từ key ID chưa xác minh.

## 14. Giám sát clock skew trong production

Các tín hiệu quan trọng:

| Metric / log an toàn | Mục đích |
| --- | --- |
| `hmac_timestamp_too_old_total` | Phát hiện client clock chậm, network queue hoặc upload dài. |
| `hmac_timestamp_too_future_total` | Phát hiện client clock nhanh hoặc server clock chậm. |
| `hmac_timestamp_delta_seconds` | Phân phối chênh lệch **serverNow − signedTimestamp** (chỉ sau khi đã kiểm soát dữ liệu và có thể ưu tiên MAC pass để tránh số liệu giả). |
| `clock_offset_to_reference_seconds` | Đo độ lệch server/replica so với nguồn thời gian tin cậy. |
| `clock_sync_age_seconds` | Phát hiện node lâu không sync. |
| `clock_step_event_total` | Nhận biết clock jump tiến/lùi. |
| `hmac_nonce_replay_total` | Giám sát replay attempts, lưu ý TTL và consistency. |
| `hmac_nonce_store_error_total` | Nguồn fail-closed của anti-replay. |
| `hmac_key_revoked_total` | Tách lỗi key status khỏi clock skew. |
| `hmac_canonical_mismatch_total` | Phân biệt lỗi ký URI/header/body với time window. |
| `hmac_authz_denied_total` | Phân biệt authentication pass nhưng thiếu quyền. |

Không log shared secret, MAC kỳ vọng, chữ ký đầy đủ hoặc raw URL/body chứa token/PII. Với chênh lệch timestamp, **giá trị do client chưa được HMAC xác minh có thể là dữ liệu giả**; đừng đưa nó trực tiếp vào dashboard như bằng chứng NTP của client đã sai. Nên tách metric **preflight untrusted timestamp** khỏi **verified-client skew**.

### Runbook khi tỷ lệ `timestamp_out_of_window` tăng

1. Xác nhận phân loại lỗi: HMAC đã đúng nhưng freshness fail, hay canonical/key/secret mismatch?
2. Kiểm tra đồng hồ của các replica/gateway và trạng thái time sync; xác định có clock step/suspend/reboot không.
3. Xem phân phối chênh lệch thời gian theo SDK version, endpoint, route, region và các client đã được xác thực, tránh cardinality không giới hạn.
4. Kiểm tra request queue/backoff, retry, proxy buffering và thời gian streaming body.
5. Đối chiếu contract epoch seconds, không có milliseconds, timezone hay leading zero.
6. Hướng dẫn client sửa time sync; **không** âm thầm nới window hoặc bỏ nonce.
7. Nếu sửa `maxPastAge`/`maxFutureSkew` theo quyết định bảo mật, cập nhật nonce TTL, test vectors, rollout config và monitoring đồng bộ; kiểm tra cả các replica và vùng.
8. Đánh giá thêm key rotation, revocation propagation, clock health và không có business side effect trong thời gian lỗi.

### Kịch bản server clock không đáng tin

Khi đồng hồ hệ thống mất sync, hai tình huống nguy hiểm:

- **Server nhanh quá:** request hợp lệ bị cho là quá cũ; gây availability incident.
- **Server chậm quá:** request quá cũ theo thời gian thực có thể bị xem là còn hợp lệ; nếu nonce store/TTL cũng không nhất quán, replay exposure tăng.

Phản ứng đúng là **fail-closed và chuyển traffic sang node clock healthy**, kết hợp cảnh báo vận hành, chứ không điều chỉnh expected HMAC hoặc timestamp từ header client.

## 15. Bài tập tình huống: lệch 25 giây, kho nonce TTL 5 phút và hai region

**Bối cảnh:** Một API thanh toán ký `POST /v1/payments` bằng HMAC-SHA256. Canonical request gồm method/raw URI, Content-Type, key ID, timestamp, nonce và SHA-256(raw body). Client ở region A có đồng hồ **nhanh hơn giờ chuẩn 25 giây**. Server cấu hình:

```text
maxPastAge     = 300s
maxFutureSkew  = 30s
nonce TTL      = 300s
Clock health   = chưa giám sát
Region A/B     = hai kho nonce Redis độc lập
```

SDK ký request lúc 12:00 theo thời gian chuẩn, timestamp ghi `12:00:25`. Request đến region A trong 1 giây, MAC hợp lệ và được xử lý. Attacker giữ nguyên request ký đó và thử gửi lại tới region B ngay sau đó; region B chưa biết nonce. Nhiều phút sau, request lại được gửi tới một replica có đồng hồ chạy chậm.

**Câu hỏi:** Điều gì có thể xảy ra và phải sửa ở đâu?

**Lời giải:**

1. **Skew +25s được chấp nhận** ở request đầu nếu server clock đúng và policy cho phép tương lai 30 giây. Timestamp nằm trong cửa sổ, MAC vẫn phải đúng.
2. **Replay giữa region:** Nếu A/B dùng hai nonce stores độc lập, cùng signed request có thể được accept ở B vì nonce chưa có, dù HMAC và timestamp đều giống. Phải dùng một replay domain có **atomic/consistent reservation** xuyên các đường nhận request phù hợp.
3. **TTL 300s không đủ** với policy `300+30=330s`. Nonce có thể hết hạn trong khi timestamp còn được chấp nhận, nhất là ở các biên tương lai. Cần TTL dựa trên **toàn acceptance lifetime**, cộng dự phòng clock error/operational latency.
4. **Clock chưa được giám sát** khiến giả định TTL và cửa sổ time không đáng tin. Nếu một replica chậm vượt tolerance, nó có thể chấp nhận request vốn đã quá cũ theo thời gian thực. Cần health check và fail-closed trên node unhealthy.
5. **Không thể giải quyết bằng cách chỉ so HMAC constant-time**: một bản replay của signed request cũ có MAC hợp lệ. Điều chặn replay là timestamp hợp lệ **và nonce chưa dùng**, với kho nonce đúng phạm vi.
6. **Authorization vẫn độc lập:** Ngay cả client có secret hợp lệ và signed timestamp mới cũng không tự có quyền thao tác một merchant/tenant khác. Backend phải kiểm tra principal được cấp theo key metadata với resource thực thi.
7. **Retry thanh toán:** Nếu client ký lại bằng timestamp/nonce mới sau timeout, có thể tạo request authenticated mới; business cần idempotency key được ký hoặc kiểm soát tương đương để không tạo payment thứ hai.
8. **Kiểm thử:** Mô phỏng `Clock.offset(±20s)` ở replica; hai request cùng nonce vào hai region; ký ở biên +30s; chờ TTL 300s và replay trước khi timestamp hết hạn; outage time sync; key revoke; principal thiếu quyền. Mọi đường từ chối phải không phát sinh side effect.

### Câu hỏi tự kiểm tra

1. Clock skew và clock drift khác nhau thế nào?
2. Vì sao một HMAC hợp lệ có thể đi kèm lỗi timestamp quá cũ hoặc quá xa tương lai?
3. Với cửa sổ [-300s,+30s], các timestamp lệch -300 và +30 được xử lý thế nào?
4. Vì sao `Math.abs(now - signed) <= 300` không tương đương cửa sổ bất đối xứng?
5. `System.currentTimeMillis()` và `Instant.now(clock).getEpochSecond()` khác đơn vị gì?
6. Vì sao cần sử dụng `Clock.fixed` và `Clock.offset` trong unit test?
7. Khi server clock không sync, phép kiểm tra timestamp có còn đáng tin không?
8. Vì sao dùng `System.nanoTime()` để tạo Unix timestamp là sai?
9. Timestamp đã được ký có chứng minh client clock chính xác không?
10. Với `maxPastAge=300` và `maxFutureSkew=30`, vì sao nonce TTL 300 giây có thể thiếu?
11. Khi các replica có sai số clock lên tới ±5 giây, cần thêm những thành phần nào vào TTL dự phòng?
12. Vì sao Redis `SET NX EX` phải atomic và cần kho dùng chung hoặc partitioning nhất quán?
13. Nếu ký trước upload 10 phút và kiểm tra freshness sau EOF, policy của bài quyết định ra sao?
14. Nếu API muốn dùng arrival timestamp ở gateway, cần bảo vệ nguồn timestamp thế nào?
15. Khi timestamp client quá xa tương lai, có nên tự chấp nhận nếu chữ ký HMAC vẫn đúng?
16. Nonce chống replay khác idempotency nghiệp vụ như thế nào?
17. Khi key bị revoke giữa upload, timestamp ký trước thời điểm revoke có cho phép key tiếp tục verify không?
18. Client có secret hợp lệ tự ký request tới tenant ngoài grant sẽ bị chặn ở bước nào?
19. Tại sao lỗi gateway rewrite URI không nên được “sửa” bằng tăng clock skew window?
20. Những trường nào cần có trong golden vector để Java, Go và Node có cùng kết quả freshness?

**Ghi nhớ:** **Clock skew** là độ lệch đồng hồ giữa người ký và người xác minh, không phải lỗi thuật toán HMAC. Hãy **ký timestamp**, thống nhất epoch seconds/UTC, định nghĩa cửa sổ quá khứ–tương lai với biên rõ ràng, dùng **server clock có health check**, và không tin timestamp client là giờ thực. Dùng **nonce reserve nguyên tử** với TTL phủ toàn bộ lifetime có thể chấp nhận (kể cả lệch replica), kiểm soát upload/queue/retry và key rotation. Sau HMAC + freshness + anti-replay, **authorization** vẫn phải kiểm tra principal và tài nguyên thực tế; nới cửa sổ hoặc bỏ nonce không phải giải pháp cho lỗi đồng bộ thời gian.

