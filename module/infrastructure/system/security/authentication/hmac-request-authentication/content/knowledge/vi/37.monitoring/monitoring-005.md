# Metric timestamp failure trong xác thực HMAC

## 1. Vì sao phải đo lỗi timestamp?

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, client và server dùng **shared secret** để tính và xác minh HMAC trên **canonical request** đã thống nhất. Tùy hợp đồng, canonical request có method, URI, các header được ký và/hoặc digest của body. Cơ chế này xác thực tính toàn vẹn và quyền sử dụng secret; timestamp và nonce bổ sung khả năng chống phát lại, còn quyền truy cập tài nguyên được kiểm tra ở tầng **phân quyền**.

Ở chương **Monitoring**, bài **Metric timestamp failure** tập trung vào việc biến kết quả kiểm tra timestamp thành số liệu vận hành có thể giải thích và cảnh báo. Một hệ thống có chữ ký HMAC đúng vẫn có thể từ chối request nếu timestamp quá cũ hoặc quá xa trong tương lai. Nguyên nhân có thể là đồng hồ client lệch, request bị giữ quá lâu tại gateway/proxy, client dùng lại request đã ký khi retry, sai định dạng thời gian hoặc lưu lượng giả mạo.

Ví dụ request:

~~~http
POST /api/signed/payments HTTP/1.1
X-Key-Id: merchant-a-v2
X-Timestamp: 2026-11-28T03:20:00Z
X-Nonce: 401c8f19-e01c-4bbc-bfa3-91b2412682a6
X-Signature: <base64-hmac-sha256>
Content-Type: application/json

{"amount":125000,"currency":"VND"}
~~~

Giả sử hợp đồng dùng timestamp UTC và cửa sổ chấp nhận **±5 phút**. Nếu đồng hồ service là `03:30:00Z`, timestamp trong ví dụ sẽ bị từ chối là quá cũ. Con số ±5 phút chỉ là **ví dụ**, không phải mặc định chung của HMAC. Cửa sổ thực tế phải được thỏa thuận, cân đối thời gian mạng, đồng hồ và rủi ro replay.

Sau bài học, người học có thể:

1. Định nghĩa đúng một *timestamp failure* và phân biệt nó với signature failure, nonce replay và lỗi hạ tầng.
2. Thiết kế các metric **counter**, tỷ lệ lỗi, latency và nhãn có cardinality giới hạn.
3. Tích hợp Micrometer vào Java/Spring Security mà không log giá trị nhạy cảm hoặc nhãn chưa được xác thực.
4. Dùng Prometheus/Grafana để phân biệt lỗi client clock, thay đổi gateway và tấn công tạo request sai.
5. Kiểm thử các ngưỡng thời gian, số lần tăng counter, trạng thái HTTP và phản ứng khi nhiều replica cùng phục vụ traffic.

## 2. Timestamp failure nằm ở bước nào?

Một bộ xác thực HMAC thường thực hiện những công việc sau:

~~~mermaid
flowchart TD
    A[Request vào API yêu cầu HMAC] --> B[Kiểm tra header bắt buộc, cú pháp và giới hạn]
    B --> C{Timestamp hợp lệ theo clock server?}
    C -- Missing/malformed/old/future --> D[Đếm timestamp rejection]
    D --> E[401 chung; dừng request]
    C -- Hợp lệ --> F[Tra key đang hiệu lực và verify HMAC canonical]
    F -- Sai --> G[401 credential failure]
    F -- Đúng --> H[Atomic claim nonce]
    H -- Đã dùng --> I[401 replay failure]
    H -- Kho nonce lỗi --> J[503, fail closed]
    H -- Chấp nhận --> K[Authenticated principal]
    K --> L{Đủ authority / đúng resource?}
    L -- Không --> M[403]
    L -- Có --> N[Handler nghiệp vụ]
~~~

Đây là **một thứ tự xử lý minh họa**, trong đó kiểm tra timestamp sớm để loại bỏ request hết hạn và giảm chi phí truy xuất key/HMAC. Hệ thống khác có thể chọn xác minh MAC trước rồi mới đánh giá timestamp để thay đổi đặc tính bảo mật và khả năng quan sát. **Điều bắt buộc là xác định rõ thứ tự, phạm vi metric và giữ phản hồi bên ngoài nhất quán.**

Nếu timestamp được kiểm tra **trước khi xác minh HMAC**, dữ liệu timestamp và key ID do client tự khai báo vẫn là **không đáng tin**. Một request giả có timestamp sai cũng có thể làm counter tăng. Không coi một lỗi `TOO_OLD` ở giai đoạn này là bằng chứng một đối tác cụ thể bị lệch đồng hồ. Nếu kiểm tra sau MAC, metric có tập request khác: chỉ những request đã vượt qua kiểm tra chữ ký mới tham gia phép đo. Dashboard và cảnh báo phải biết đang đo tập nào.

**Chỉ sau khi chữ ký đã xác minh** mới nên claim nonce để tránh request giả chiếm nonce của request thật. Timestamp hợp lệ **không đồng nghĩa** đã xác thực; còn phải kiểm tra canonical signature, key và chống replay. HMAC hợp lệ cũng chưa có nghĩa principal có quyền gọi endpoint.

## 3. Phân loại lỗi timestamp bằng mã hữu hạn

Không dùng một message tự do như `"Timestamp 2026-... của merchant-a hết hạn"` làm nhãn. Hãy xác định các outcome cố định:

| Mã nội bộ | Điều kiện | Ý nghĩa vận hành |
|---|---|---|
| `valid` | Timestamp parse được, nằm trong cửa sổ cho phép | Bước timestamp đã đạt |
| `missing` | Header timestamp bắt buộc không có | Client thiếu credential hoặc traffic giả |
| `malformed` | Timestamp sai format, bị lặp, quá dài hoặc có giá trị không hợp lệ | SDK sai hợp đồng, bất thường tại gateway hoặc input độc hại |
| `expired` | Timestamp cũ hơn biên dưới | Client clock chậm, retry cũ, request bị queue lâu hoặc phát lại |
| `future` | Timestamp mới hơn biên trên | Client clock nhanh, sai múi giờ, lỗi serialization hoặc traffic giả |

Đặt tên metric và nhãn sao cho ý nghĩa không thay đổi theo thời gian. Ví dụ một version có thể đổi `expired` thành `too_old`, nhưng khi đó dashboard, alert và thống kê dài hạn phải được cập nhật theo phiên bản; tránh đổi tên âm thầm trong lúc rollout.

### Phân biệt với các lỗi khác

| Hiện tượng | Có tính vào timestamp failure? | Sự kiện liên quan |
|---|---|---|
| Timestamp hết hạn | **Có** | `hmac.timestamp.rejected`, reason `expired` |
| Timestamp sai cú pháp | **Có** nếu metric định nghĩa bao gồm lỗi format | `malformed` |
| Chữ ký HMAC sai dù timestamp đúng | **Không** | Signature/credential failure |
| Nonce từng dùng nhưng timestamp còn hợp lệ | **Không** | Replay failure |
| Kho nonce không sẵn sàng | **Không** | Verification unavailable |
| Key cũ đã bị revoke trong key rotation | **Không** | Credential/key failure |
| HMAC đúng nhưng principal thiếu `payments:write` | **Không** | Authorization denied, 403 |
| Request bị proxy biến đổi URI/header/body khiến MAC sai | **Không**, trừ khi chính timestamp bị thay và không đạt check | Canonical/signature failure |

**Không chẩn đoán “timestamp failure” chỉ từ HTTP 401.** API có thể chủ động dùng cùng 401 cho nhiều loại lỗi xác thực để giảm rò rỉ thông tin. Chỉ bộ kiểm tra đã biết kết quả mới được phát một reason nội bộ tương ứng.

## 4. Đồng hồ, cửa sổ chấp nhận và biên thời gian

Giả sử:

- `now` là thời gian lấy từ **clock tin cậy của service** tại thời điểm kiểm tra.
- `ts` là timestamp đã parse của request.
- `W` là độ lệch cho phép theo hợp đồng.

Quy tắc minh họa:

~~~text
ts < now - W    => expired
ts > now + W    => future
otherwise       => valid
~~~

Hai biên `now - W` và `now + W` được xem là **hợp lệ** trong ví dụ. Nếu API chọn biên loại trừ, phải nói rõ và kiểm thử thống nhất. Clock nên là nguồn UTC được đồng bộ; không dùng timestamp tự khai của gateway/client để thay thời gian hiện tại của service. Sử dụng nguồn đồng hồ đã inject giúp test cố định thời gian.

### Những lỗi đồng hồ phổ biến

**Clock skew của client.** Máy đối tác không đồng bộ thời gian hoặc cấu hình sai timezone. Ví dụ client ghi giờ địa phương nhưng gắn hậu tố `Z` như UTC, tạo chênh lệch nhiều giờ. Server phải parse đúng format đã ký và không “tự đoán” timezone để chữa.

**Delay qua gateway/proxy.** Request có thể nằm trong queue, bị retry qua hop trung gian hoặc đi qua nhiều region, khiến timestamp hết hạn trước khi service xác thực. Đo thời gian gateway và service có thể giúp tìm điểm tắc; đừng tự cộng thêm thời gian chờ vào window mà chưa đánh giá replay window.

**Server clock skew giữa replica.** Cùng request có thể được replica A chấp nhận và replica B từ chối nếu đồng hồ khác nhau. Theo dõi sức khỏe đồng bộ thời gian, kiểm thử nhiều replica và dùng cùng chính sách `W`.

**Cửa sổ thời gian rộng.** Tăng `W` có thể làm giảm từ chối do độ trễ, nhưng kéo dài khoảng thời gian chữ ký có thể được gửi lại; phải điều chỉnh TTL của nonce store tương ứng. Không mở rộng cửa sổ chỉ vì dashboard thấy nhiều lỗi `expired` mà chưa xác định nguyên nhân.

**Nhầm thời gian wall-clock và elapsed time.** Dùng `Clock.instant()` để xác minh timestamp theo UTC; dùng đồng hồ đơn điệu (ví dụ `System.nanoTime()`) để đo thời lượng xử lý. Không dùng `System.currentTimeMillis()` để suy ra latency qua những lần đồng hồ hệ thống chỉnh giờ.

## 5. Thiết kế metric an toàn và nhất quán

Nên có một counter đo **mỗi lần chạy bước kiểm tra timestamp** và kết quả đã phân loại:

~~~text
hmac_timestamp_checks_total{
  service="payment-service",
  route="payments.create",
  outcome="rejected",
  reason="expired"
}
~~~

Đây là dạng tên sau khi xuất sang Prometheus. Trong Micrometer có thể đăng ký counter với tên logic `hmac_timestamp_checks`; Prometheus thường xuất thêm hậu tố `_total` cho counter.

### 5.1. Định nghĩa tập mẫu

Một **timestamp check** là một lần request đi vào hàm kiểm tra timestamp và hàm đó kết luận một outcome (`valid`, `missing`, `malformed`, `expired`, `future`). Nên tăng counter **đúng một lần** cho mỗi lần kiểm tra có kết luận, kể cả khi client ngắt kết nối sau khi check.

Nếu request bị từ chối do kích thước body hoặc WAF trước khi đến bước timestamp, nó **không thuộc mẫu số** của `hmac_timestamp_checks_total`. Vì vậy có thể cần thêm:

~~~text
hmac_auth_requests_total{route="payments.create",outcome="accepted|rejected|unavailable"}
~~~

Counter này đo attempt ở một ranh giới xác thực được định nghĩa riêng. Không ghép hai mẫu số khác nhau vào một tỷ lệ. Đặc biệt, một request có thể qua timestamp check rồi thất bại MAC; counter timestamp là `valid`, còn counter authn có thể là `rejected`, và điều đó **không mâu thuẫn**.

Nếu triển khai filter có retry nội bộ để truy vấn khóa hoặc lưu nonce, không tăng timestamp check nhiều lần chỉ vì một HTTP request đang retry dependency. Đếm một attempt tại ranh giới kiểm tra, hoặc ghi riêng số lần gọi dependency nếu cần.

### 5.2. Nhãn nào nên và không nên dùng?

| Nhãn | Khuyến nghị | Lý do |
|---|---|---|
| `service`, `environment` | Có, từ cấu hình server | Tập giá trị hữu hạn |
| `route` | Có, **route ID/template** của server | So sánh endpoint mà không lộ raw URI |
| `outcome` | Có, `accepted` hoặc `rejected` | Giới hạn hai giá trị |
| `reason` | Có, enum `valid/missing/malformed/expired/future` | Đọc được xu hướng lỗi |
| `deployment_version` | Cân nhắc, nếu số version còn giữ nhỏ | Giúp liên hệ thay đổi release nhưng dễ tăng cardinality |
| `key_id`, `client_id`, `tenant_id` | Tránh trên counter tổng quát | Dễ lộ định danh và tăng cardinality |
| `timestamp`, `nonce`, `signature` | **Không** | Giá trị tùy request, có thể nhạy cảm hoặc bị tấn công |
| `request_id`, `trace_id`, `raw_path`, `raw_query` | **Không** | Cardinality gần như vô hạn và có nguy cơ lộ thông tin |
| `client_ip`, `user_agent` | Tránh trên metric này | Khó kiểm soát số giá trị, dễ bị giả mạo |

Nếu cần điều tra theo đối tác, hãy dùng log bảo vệ quyền truy cập và một định danh đã kiểm chứng sau xác thực, hoặc dashboard chuyên dụng có chính sách dữ liệu và cardinality rõ ràng. **Không dùng `X-Key-Id` từ request chưa xác thực làm metric label.** Attacker có thể tạo hàng triệu giá trị ngẫu nhiên gây bùng bộ nhớ metrics.

### 5.3. Metric bổ trợ

Ngoài counter chính, cân nhắc:

- `hmac_auth_verification_duration_seconds` dưới dạng histogram/timer theo route và outcome đã kiểm soát, để phát hiện verifier chậm.
- Metric về health của NTP/clock synchronization trên server từ hạ tầng đáng tin, tách khỏi timestamp do client gửi.
- Latency từ ingress đến service nếu có cách đo đáng tin cậy giữa các hop; không trừ trực tiếp hai đồng hồ lệch nhau mà không đồng bộ.
- Counters riêng cho `replay_rejected`, `signature_invalid` và `verification_unavailable` để so sánh tương quan.
- Tỷ lệ request bị từ chối do timestamp cùng lượng traffic thực tế; chỉ theo dõi con số tuyệt đối rất dễ hiểu nhầm khi QPS thay đổi.

Đối với clock skew được suy ra từ `ts - now`, đừng đưa chênh lệch chưa xác thực vào metric histogram mặc định nếu không kiểm soát giá trị. Header do attacker gửi có thể làm nhiễu phân phối; chỉ đo ở phạm vi phù hợp, giới hạn giá trị tuyệt đối và ghi rõ có/không yêu cầu MAC hợp lệ.

## 6. Ví dụ Java 17+ kiểm tra timestamp có thể kiểm thử

Để tránh lỗi do thời gian thực trong unit test, tách validator khỏi HTTP filter và inject `Clock`.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.Objects;

public final class HmacTimestampValidator {
    public enum Result {
        VALID, MISSING, MALFORMED, EXPIRED, FUTURE
    }

    private final Clock clock;
    private final Duration allowedSkew;

    public HmacTimestampValidator(Clock clock, Duration allowedSkew) {
        this.clock = Objects.requireNonNull(clock);
        this.allowedSkew = Objects.requireNonNull(allowedSkew);
        if (allowedSkew.isNegative() || allowedSkew.isZero()) {
            throw new IllegalArgumentException("allowedSkew must be positive");
        }
    }

    public Result check(String rawTimestamp) {
        if (rawTimestamp == null) {
            return Result.MISSING;
        }
        if (rawTimestamp.isBlank() || rawTimestamp.length() > 40) {
            return Result.MALFORMED;
        }

        final Instant signedAt;
        try {
            // Ví dụ chấp nhận định dạng Instant.parse (UTC/offset ISO-8601).
            // Nếu contract yêu cầu duy nhất 'yyyy-MM-ddTHH:mm:ssZ',
            // phải dùng parser/validation nghiêm ngặt tương ứng.
            signedAt = Instant.parse(rawTimestamp);
        } catch (DateTimeParseException invalid) {
            return Result.MALFORMED;
        }

        Instant now = clock.instant();
        if (signedAt.isBefore(now.minus(allowedSkew))) {
            return Result.EXPIRED;
        }
        if (signedAt.isAfter(now.plus(allowedSkew))) {
            return Result.FUTURE;
        }
        return Result.VALID; // Hai biên tính cả dấu bằng.
    }
}
~~~

**Phạm vi của ví dụ:** hàm chỉ đánh giá thời gian; nó chưa chứng minh header đã được ký bằng HMAC. Adapter HTTP phải xử lý header **trùng**, thiếu, kích thước quá lớn, không đúng charset/format và kiểm tra đúng contract, rồi verifier tiếp tục kiểm tra signature, trạng thái key và nonce.

Nếu yêu cầu timestamp bắt buộc dạng `2026-11-28T03:20:00Z` không có phần giây lẻ và offset khác, `Instant.parse` có thể chấp nhận nhiều dạng rộng hơn mong muốn. Cần áp dụng format nghiêm ngặt **trước** khi chấp nhận `VALID`. Đặc biệt, không parse theo múi giờ mặc định của JVM hoặc tự thêm `Z` khi client gửi timestamp không có timezone.

### 6.1. Đếm kết quả bằng Micrometer

Ví dụ Micrometer tạo sẵn năm `Counter` theo các nhãn hữu hạn. `routeId` phải là giá trị **được chọn từ registry cấu hình server**, không phải nguyên chuỗi URL hoặc header do client gửi:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.EnumMap;
import java.util.Map;

public final class HmacTimestampMetrics {
    private final Map<HmacTimestampValidator.Result, Counter> counters =
            new EnumMap<>(HmacTimestampValidator.Result.class);

    public HmacTimestampMetrics(
            MeterRegistry registry, String serviceId, String routeId) {
        for (HmacTimestampValidator.Result result :
                HmacTimestampValidator.Result.values()) {

            String outcome = result == HmacTimestampValidator.Result.VALID
                    ? "accepted" : "rejected";
            String reason = result.name().toLowerCase(java.util.Locale.ROOT);

            counters.put(result, Counter.builder("hmac_timestamp_checks")
                    .description("HMAC timestamp validation outcomes")
                    .tag("service", serviceId)
                    .tag("route", routeId)
                    .tag("outcome", outcome)
                    .tag("reason", reason)
                    .register(registry));
        }
    }

    public void record(HmacTimestampValidator.Result result) {
        counters.get(result).increment();
    }
}
~~~

Mỗi lần gọi `check` xong, một thành phần điều phối sẽ tăng counter một lần:

~~~java
HmacTimestampValidator.Result result =
        timestampValidator.check(singleTimestampHeader);
timestampMetrics.record(result);

if (result != HmacTimestampValidator.Result.VALID) {
    // Một phản hồi 401 chung; không cho request chạy nghiệp vụ.
    authenticationEntryPoint.commence(request, response, invalidCredentials);
    return;
}

// Tiếp tục xác minh key/HMAC canonical và atomic nonce claim.
// Chỉ khi toàn bộ xác thực thành công mới tạo Authentication.
~~~

Đây là **pseudocode ở lớp phối hợp** với Servlet/Spring Security; `request`, `response` và `invalidCredentials` được cung cấp bởi filter thực tế. Trong WebFlux, luồng tương đương phải trả `Mono<Void>`, không gọi `block()`, và context bảo mật được truyền qua Reactor Context.

Nên gắn metric ở **một nơi duy nhất** sau quyết định của timestamp validator. Không cùng lúc tăng counter trong filter, verifier, entry point và global exception handler; nếu không một request có thể tăng counter nhiều lần. Nếu một filter bỏ qua một route không yêu cầu HMAC, cũng không ghi `MISSING` chỉ vì route không có header.

**Tùy framework**, có thể truyền kết quả dưới dạng một record/evaluation object chứa `Result` thay vì dùng exception cho mọi nhánh; điều này giúp metric nhận lý do chính xác và response vẫn là 401 chung.

## 7. Đọc kết quả trên Prometheus

Giả sử exporter tạo metric `hmac_timestamp_checks_total` với các nhãn `service`, `route`, `outcome`, `reason`.

### 7.1. Lưu lượng timestamp bị từ chối

~~~promql
sum by (service, route, reason) (
  rate(hmac_timestamp_checks_total{outcome="rejected"}[5m])
)
~~~

Đơn vị là **request check bị từ chối mỗi giây**, tính theo cửa sổ 5 phút. Có thể xem riêng `expired`, `future` và `malformed` để xác định nhóm lỗi trội hơn.

### 7.2. Tỷ lệ timestamp failure

~~~promql
sum by (service, route) (
  rate(hmac_timestamp_checks_total{outcome="rejected"}[5m])
)
/
clamp_min(
  sum by (service, route) (
    rate(hmac_timestamp_checks_total[5m])
  ),
  1e-9
)
~~~

Kết quả là một **tỷ lệ từ 0 đến 1** theo các series có dữ liệu phù hợp. Nhân 100 khi trình bày dưới dạng phần trăm. `clamp_min` chỉ tránh chia cho 0 khi mẫu số rất nhỏ, **không** bảo đảm tỷ lệ có ý nghĩa thống kê ở lưu lượng thấp; cần theo dõi lượng mẫu và tránh cảnh báo chỉ từ một vài request.

### 7.3. Tổng số request bị timestamp rejection trong cửa sổ

~~~promql
sum by (service, route, reason) (
  increase(hmac_timestamp_checks_total{outcome="rejected"}[15m])
)
~~~

`increase` trên counter giúp xem lượng sự kiện ước tính qua cửa sổ 15 phút và phù hợp dashboard điều tra. Khi instance restart, counter trong tiến trình trở về 0; Prometheus xử lý reset theo semantics của counter, không dùng raw difference của hai lần scrape để thay.

### 7.4. Phân biệt “client clock” và “lỗi gateway”

Một dashboard có thể đặt cạnh nhau:

| Panel | Câu hỏi |
|---|---|
| Timestamp rejection theo `reason` | `expired` hay `future` đang tăng? |
| Timestamp failure rate theo route | Chỉ một API hay nhiều API cùng bị? |
| Timestamp checks/giây | Có đủ volume để kết luận không? |
| Signature/replay rejection | Timestamp tăng có đồng thời tăng lỗi MAC hoặc replay? |
| Gateway request duration và upstream queue | Delay mới phát sinh ở hop nào? |
| Clock sync health theo instance | Có replica nào lệch đồng hồ không? |
| Deployment/config changes | Có đổi format timestamp, window, proxy hay SDK không? |

Nếu một route tăng `expired` ngay sau thay đổi proxy, cần kiểm tra queue/retry và cách chuyển tiếp request. Nếu `future` tăng ở một số client đã xác thực, kiểm tra clock và timezone của client qua kênh hỗ trợ an toàn. Nếu `malformed` tăng đột biến toàn hệ thống, kiểm tra version SDK/hợp đồng parse và cả lưu lượng từ chối giả mạo.

**Không tự kết luận lỗi của một đối tác chỉ từ key ID chưa xác thực hoặc một biểu đồ 401.** Dữ liệu trước khi MAC hợp lệ có thể bị attacker tạo ra; cần kết hợp request correlation, log nội bộ có quyền và thông tin đã được kiểm chứng.

## 8. Cảnh báo có ngữ cảnh

Một cảnh báo timestamp failure nên dựa trên **tỷ lệ + lượng mẫu + thời gian kéo dài**, thay vì chỉ một request sai. Ví dụ minh họa để đội vận hành điều chỉnh bằng dữ liệu thực:

~~~text
Điều kiện ứng viên:
- Timestamp failure rate > 2% trong 10 phút
- Ít nhất 200 timestamp checks trong 10 phút
- Có biến động rõ so với baseline cùng route
- Kèm nhãn route và reason có cardinality giới hạn

Không dùng ngưỡng trên như một SLO mặc định cho mọi hệ thống.
~~~

Để tránh nhiễu, có thể phân loại:

- **Cảnh báo tích hợp:** `expired` hoặc `future` tăng kéo dài sau thay đổi SDK/gateway, kèm tỷ lệ khách hợp lệ bị ảnh hưởng được xác minh bằng dữ liệu có quyền.
- **Cảnh báo hạ tầng:** đồng hồ của một replica lệch hoặc NTP không đồng bộ, hoặc latency gateway tăng rõ rệt.
- **Cảnh báo nghi ngờ lạm dụng:** `malformed`/`missing` tăng nhanh đồng thời nhiều request không vượt qua signature check; cần đối chiếu với rate-limit/WAF, không coi đó là bằng chứng chắc chắn của tấn công.
- **Cảnh báo chống replay:** `replay_rejected` tăng cần dashboard/metric khác, vì timestamp và nonce là hai cơ chế khác nhau.

Một ngưỡng quá nhạy làm on-call mệt mỏi; ngưỡng quá rộng che mất lỗi khách hàng. Điều chỉnh theo baseline, tần suất request, thời gian phục vụ và mức độ ảnh hưởng nghiệp vụ. Tránh đưa client ID/key ID vào alert label; thay bằng route và correlation/trace từ hệ thống log có quyền khi cần điều tra một trường hợp.

## 9. Kiểm thử timestamp metric và HTTP behavior

Kiểm thử được thực hiện ở nhiều mức, nhưng một bài toán phải kiểm tra **cả trạng thái bảo mật lẫn giá trị counter**. Một metric đúng không bù được filter đã lỡ chuyển request sai thời gian vào controller.

### 9.1. Unit test biên thời gian với Clock cố định

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class HmacTimestampValidatorTest {
    private final HmacTimestampValidator validator =
            new HmacTimestampValidator(
                    Clock.fixed(
                            Instant.parse("2026-11-28T03:30:00Z"),
                            ZoneOffset.UTC),
                    Duration.ofMinutes(5));

    @Test
    void checksBothSkewBoundaries() {
        assertEquals(HmacTimestampValidator.Result.VALID,
                validator.check("2026-11-28T03:25:00Z")); // Biên dưới
        assertEquals(HmacTimestampValidator.Result.VALID,
                validator.check("2026-11-28T03:35:00Z")); // Biên trên
        assertEquals(HmacTimestampValidator.Result.EXPIRED,
                validator.check("2026-11-28T03:24:59Z"));
        assertEquals(HmacTimestampValidator.Result.FUTURE,
                validator.check("2026-11-28T03:35:01Z"));
    }

    @Test
    void treatsMissingAndMalformedSeparately() {
        assertEquals(HmacTimestampValidator.Result.MISSING,
                validator.check(null));
        assertEquals(HmacTimestampValidator.Result.MALFORMED,
                validator.check("not-a-timestamp"));
    }
}
~~~

### 9.2. Test counter không bị nhân đôi

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class HmacTimestampMetricsTest {
    @Test
    void incrementsOnlyTheCorrespondingReason() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            HmacTimestampMetrics metrics =
                    new HmacTimestampMetrics(
                            registry, "payment-service", "payments.create");

            metrics.record(HmacTimestampValidator.Result.EXPIRED);
            metrics.record(HmacTimestampValidator.Result.EXPIRED);
            metrics.record(HmacTimestampValidator.Result.VALID);

            assertEquals(2.0, registry.get("hmac_timestamp_checks")
                    .tag("reason", "expired")
                    .counter().count());
            assertEquals(1.0, registry.get("hmac_timestamp_checks")
                    .tag("reason", "valid")
                    .counter().count());
        }
    }
}
~~~

Đây là test của lớp metric, chưa thay thế integration test HTTP. Khi chạy Spring MVC/Spring WebFlux thật, cần kiểm tra request có timestamp hết hạn **trả 401, không gọi handler**, một event metric đúng và không tiết lộ giá trị timestamp/nonce trong response.

### 9.3. Ma trận kiểm thử tích hợp

| Trường hợp | HTTP/behavior | Metric |
|---|---|---|
| Timestamp đúng biên dưới/trên | Tiếp tục xác minh MAC; không tự cho qua toàn bộ request | `valid` tăng một lần mỗi check |
| Timestamp cũ hơn biên | 401; không có side effect | `expired` tăng |
| Timestamp tương lai quá mức | 401; không có side effect | `future` tăng |
| Thiếu header, header rỗng/trùng | 401 hoặc 400 theo policy; dừng | `missing` hoặc `malformed` đúng một lần |
| MAC sai nhưng timestamp hợp lệ | 401; không chạy nghiệp vụ | Timestamp `valid`, MAC failure ở metric khác |
| Timestamp sai **và** MAC sai | Theo thứ tự kiểm tra đã định nghĩa; bên ngoài vẫn lỗi chung | Không ghi thêm kết luận MAC nếu chưa verify |
| Nonce replay với timestamp đúng | 401 replay | Timestamp `valid`; replay metric tăng riêng |
| Key hết hiệu lực trong rotation | 401 credential | Không quy thành timestamp failure |
| Kho nonce/key lỗi | 503; fail closed | Metric hạ tầng riêng, không ghi giả `expired` |
| HMAC hợp lệ nhưng không có quyền | 403; không có side effect | Timestamp `valid`; authorization denied riêng |
| Gateway giữ request quá lâu | 401 `expired` khi vượt window | Tỷ lệ `expired` tăng, đối chiếu gateway latency |
| Replica lệch clock | Có thể cho kết quả khác nhau theo instance | Phát hiện qua metric health đồng hồ/trace |
| Client giả tạo key ID ngẫu nhiên | Từ chối nếu sai | **Không sinh label theo key ID** |
| 2 replica nhận cùng nonce đồng thời | Tối đa một request vượt nonce claim | Timestamp có thể `valid` cho cả hai; replay riêng |
| Route công khai ngoài HMAC security chain | Theo security policy của route | Không tăng metric timestamp HMAC |

### 9.4. Kiểm thử qua gateway/proxy

Ký timestamp và canonical request tại client, gửi qua ingress thật hoặc test gateway tương đương rồi xác minh:

1. Gateway giữ nguyên header timestamp đã ký, kể cả khi rewrite public path; service dùng dữ liệu ký đã được thỏa thuận.
2. Header timestamp trùng hoặc do hop trung gian thêm được xử lý theo hợp đồng; không chọn giá trị đầu/cuối một cách ngẫu nhiên.
3. Request bị queue/timeout vượt cửa sổ nhận 401; metric `expired` tăng, handler không thực thi.
4. Proxy không thể “chữa” timestamp bằng cách ghi lại giá trị mới mà không có chữ ký mới hợp lệ.
5. Client retry với timestamp/nonce mới và chữ ký tính lại; dùng idempotency key riêng cho thao tác ghi để không tạo giao dịch trùng.

## 10. Lỗi triển khai thường gặp

**Gắn reason bằng exception text.** Một message như `"timestamp for merchant-a is 600 seconds old"` không phù hợp làm metric label: nó tăng cardinality và có thể lộ định danh. Dùng enum hữu hạn và log bảo vệ khi cần chi tiết.

**Dùng client time làm clock đối chiếu.** Header timestamp là dữ liệu do client gửi, không thể tự đóng vai trò “thời gian hiện tại đáng tin”. Server phải lấy clock của mình; chỉ sử dụng forwarded metadata trong ranh giới đã xác minh.

**Gộp mọi lỗi 401 thành timestamp failure.** Chữ ký sai, nonce replay hoặc key bị revoke là nguyên nhân khác. Chỉ recorder của bước timestamp được ghi kết quả timestamp.

**Đếm trùng khi retry/filter nhiều tầng.** Nếu gateway và service cùng xuất metric có tên và nhãn giống nhau nhưng khác tập mẫu, dashboard sẽ cộng những attempt không tương đồng. Tách namespace hoặc nhãn `component` cố định, và xác định rõ một sự kiện được đếm ở đâu.

**Đưa key ID/nonce/raw path vào label.** Kẻ tấn công kiểm soát đầu vào có thể tạo vô số time series; còn có thể làm lộ thông tin về client/tenant. Chỉ dùng route ID/template đáng tin và reason cố định.

**Tăng timestamp window để xóa cảnh báo.** Window rộng giảm `expired` nhưng tăng thời gian replay tiềm năng và yêu cầu nonce TTL dài hơn; cần điều tra clock/proxy trước.

**Lưu nonce trước khi xác minh MAC.** Request giả có thể chiếm nonce của request thật. Nonce phải được claim atomically theo phạm vi client/key đáng tin **sau khi HMAC hợp lệ**.

**Nhầm 403 với lỗi timestamp.** Một principal xác thực thành công nhưng không được quyền gọi API là lỗi authorization; metric timestamp vẫn có thể `valid`.

**Không xử lý clock drift của service.** Replica lệch giờ có thể từ chối hàng loạt request hợp lệ. Theo dõi clock health và xác minh ảnh hưởng của NTP/time sync khi deploy nhiều vùng.

## 11. Checklist vận hành

- [ ] Định nghĩa rõ hợp đồng ký HMAC và format timestamp, múi giờ, biên window và quy tắc kiểm tra trước/sau MAC.
- [ ] Dùng `Clock` phía server để đánh giá timestamp và test được các biên thời gian.
- [ ] Timestamp validator trả enum cố định: `valid/missing/malformed/expired/future`.
- [ ] Counter tăng **một lần** mỗi check, có phạm vi/mẫu số được ghi tài liệu.
- [ ] Route/service/reason/outcome lấy từ server hoặc enum, không đưa header/key ID/nonce/timestamp/raw URL vào metric label.
- [ ] 401 chung cho credential/timestamp không hợp lệ, 403 cho lỗi quyền, 503 khi không thể xác minh; không rò nội dung secret/canonical.
- [ ] Timestamp valid không tự tạo Authentication; vẫn kiểm tra HMAC, key còn hiệu lực và nonce chống replay nguyên tử.
- [ ] Dashboard có số lượng request, tỷ lệ lỗi, phân phối reason và health đồng hồ/gateway.
- [ ] Alert kết hợp tỷ lệ, volume, baseline và thời gian duy trì; không kết luận nguyên nhân chỉ từ counter.
- [ ] Test cả 2 biên window, clock skew, qua proxy, nhiều replica, key rotation và fallback khi kho nonce lỗi.
- [ ] Mọi request bị từ chối đều không chạy nghiệp vụ; tránh đếm trùng qua các filter/layer.
- [ ] Metric, log và trace tuân thủ chính sách hạn chế cardinality, dữ liệu nhạy cảm và retention.

**Điểm cần nhớ:** metric timestamp failure chỉ hữu ích khi có **định nghĩa chính xác về thời điểm đo và tập request được đo**. Các mã lỗi hữu hạn giúp phát hiện lệch đồng hồ, request trễ hoặc input bất thường; tuy nhiên dữ liệu trước bước HMAC vẫn do client tự khai báo và có thể bị giả mạo. Thiết kế quan sát đúng phải đi cùng kiểm tra canonical request, signature, nonce, key rotation và authorization để vừa chẩn đoán lỗi tích hợp vừa giữ vững ranh giới bảo mật.
