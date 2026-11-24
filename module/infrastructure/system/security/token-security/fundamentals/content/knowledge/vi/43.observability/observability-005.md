# Metric refresh reuse detection

## Mục tiêu

Refresh token thường có thời hạn dài hơn access token và được dùng để xin access token mới. Khi authorization server áp dụng **refresh token rotation**, mỗi lần refresh thành công sẽ tiêu thụ token cũ và phát hành token kế tiếp. Nếu một refresh token đã bị tiêu thụ lại xuất hiện trong yêu cầu mới, đó có thể là dấu hiệu token bị đánh cắp và phát lại.

**Metric refresh reuse detection** giúp đội vận hành quan sát số lần phát hiện refresh token bị sử dụng lại, mức độ ảnh hưởng, hành động thu hồi token family và thay đổi bất thường theo thời gian. Metric cần hỗ trợ phát hiện sự cố mà không biến token, người dùng hoặc tenant thành nhãn có cardinality cao.

Sau bài này, bạn có thể:

- Mô tả cách rotation và reuse detection tạo ra tín hiệu bảo mật.
- Chọn metric phản ánh request refresh, rotation, reuse, thu hồi token family và độ trễ.
- Thiết kế nhãn metric có cardinality giới hạn, không chứa token hoặc định danh cá nhân.
- Ghi security event đủ để điều tra mà không lưu bearer token hoặc refresh token nguyên văn.
- Tạo dashboard và cảnh báo dựa trên tốc độ, tỷ lệ reuse và hành động thu hồi.
- Phân biệt replay thật với request đồng thời, retry hoặc lỗi cấu hình client.
- Kiểm thử rằng reuse detection được ghi nhận và token family được xử lý theo chính sách.

## 1. Refresh token rotation tạo ra tín hiệu reuse như thế nào?

Refresh token cho phép client xin access token mới mà không yêu cầu người dùng đăng nhập lại. Vì refresh token có giá trị cao, authorization server cần giới hạn khả năng bị đánh cắp và sử dụng lại.

Với rotation, một token chỉ được dùng một lần trong luồng bình thường:

1. Client gửi refresh token hiện tại, ký hiệu `RT₀`.
2. Authorization server xác minh token, client binding và trạng thái token family.
3. Server đánh dấu `RT₀` đã tiêu thụ và phát hành access token mới cùng refresh token kế tiếp `RT₁`.
4. Client lưu `RT₁` và loại bỏ `RT₀`.
5. Nếu `RT₀` được gửi lại sau khi đã tiêu thụ, server nhận ra token cũ xuất hiện lần nữa và ghi nhận sự kiện reuse.

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant DB as Token Family Store
    C->>AS: Refresh với RT0
    AS->>DB: Kiểm tra RT0 và trạng thái family
    DB-->>AS: RT0 còn hiệu lực
    AS->>DB: Atomically consume RT0, tạo RT1
    AS-->>C: Access token mới + RT1
    C->>AS: Gửi lại RT0 đã tiêu thụ
    AS->>DB: Tra cứu RT0
    DB-->>AS: RT0 đã consumed
    AS->>DB: Ghi nhận reuse, áp dụng revoke policy
    AS-->>C: Từ chối refresh
~~~

Khi reuse được xác nhận, authorization server có thể thu hồi refresh token family hoặc các token hậu duệ liên quan theo chính sách. Điều này giới hạn khả năng kẻ tấn công tiếp tục dùng token mới mà client hợp pháp đã nhận.

**Một JWT có chữ ký hợp lệ không tự cho biết nó đã được dùng hay chưa.** Nếu muốn phát hiện refresh token JWT bị phát lại, hệ thống vẫn cần trạng thái phía server, chẳng hạn `jti`, token family và trạng thái đã tiêu thụ. Với opaque refresh token, server thường lưu fingerprint/hash an toàn cùng trạng thái token. Một hệ thống hoàn toàn stateless không thể xác định chính xác token đã được dùng một lần trước đó chỉ bằng cách kiểm tra chữ ký.

### Reuse khác với token không hợp lệ

Không phải mọi refresh request thất bại đều là reuse:

| Trường hợp | Ý nghĩa | Có tăng metric reuse không? |
| --- | --- | --- |
| Token đã được tiêu thụ và được gửi lại, family còn được nhận diện | Có tín hiệu replay | Có |
| Token hết hạn | Vượt thời hạn | Không |
| Token bị thu hồi chủ động | Không còn được phép dùng | Không, trừ khi policy phân loại riêng và có bằng chứng reuse |
| Token không tồn tại hoặc sai định dạng | Không nhận diện được token | Không |
| Chữ ký/token binding sai | Token không qua xác thực | Không |
| Token hiện tại được refresh thành công | Rotation bình thường | Không |
| Request thứ hai đến đồng thời với request thứ nhất | Có thể là race/retry hoặc replay | Phân loại theo kết quả atomic state transition |

Định nghĩa sự kiện phải chặt chẽ. Nếu gộp mọi lỗi refresh vào `reuse_detected`, dashboard sẽ phóng đại rủi ro và cảnh báo không còn hữu ích.

## 2. Xác định sự kiện và vòng đời cần đo

Trước khi tạo metric, thống nhất các trạng thái của refresh token:

- `issued`: token được phát hành.
- `active`: token hiện có thể dùng.
- `consumed`: token đã được dùng trong một lần rotation.
- `revoked`: token bị thu hồi theo chính sách.
- `expired`: token đã hết hạn.
- `reuse_detected`: token ở trạng thái đã tiêu thụ xuất hiện lại trong request mới và được xác định là reuse.

Một token family liên kết các refresh token được phát hành qua các lần rotation cho cùng một phiên cấp quyền. Ví dụ:

~~~text
family F
  RT0: active → consumed
  RT1: active → consumed
  RT2: active → revoked  (sau khi reuse RT0 được xác nhận)
~~~

Tín hiệu quan trọng gồm:

1. Số refresh request và kết quả của chúng.
2. Số rotation thành công.
3. Số reuse được xác nhận.
4. Số token family bị thu hồi vì reuse.
5. Độ trễ của thao tác refresh.
6. Lỗi lưu trữ token family, transaction hoặc dependency ảnh hưởng đến khả năng phát hiện reuse.

Nên đo cả **tín hiệu bảo mật** lẫn **sức khỏe của cơ chế phát hiện**. Nếu database kiểm tra trạng thái family gặp lỗi và server fail closed, metric lỗi dependency giúp phân biệt một đợt từ chối do hạ tầng với một đợt replay thật.

## 3. Bộ metric đề xuất

Tên metric dưới đây dùng quy ước Prometheus. Tùy thư viện instrumentation, tên nội bộ có thể được chuyển đổi khi export.

| Metric | Loại | Ý nghĩa |
| --- | --- | --- |
| `security_refresh_token_requests_total` | Counter | Tổng refresh request, phân loại bằng outcome |
| `security_refresh_token_rotations_total` | Counter | Số lần rotation thành công |
| `security_refresh_token_reuse_detected_total` | Counter | Số lần reuse đã được xác nhận |
| `security_refresh_token_family_revocations_total` | Counter | Số token family bị thu hồi, phân loại bằng reason |
| `security_refresh_token_family_revocation_failures_total` | Counter | Số lần thu hồi family thất bại hoặc transaction rollback |
| `security_refresh_token_validation_failures_total` | Counter | Lỗi xác minh không phải reuse, ví dụ expired hoặc invalid binding |
| `security_refresh_token_store_errors_total` | Counter | Lỗi đọc/ghi trạng thái token family |
| `security_refresh_token_request_duration_seconds` | Histogram | Độ trễ xử lý refresh request |
| `security_refresh_token_active_families` | Gauge | Số family đang active, nếu hệ thống có thể tính chính xác và chi phí phù hợp |

Counter tăng đơn điệu trong vòng đời process và có thể reset khi restart. Dùng `rate()` hoặc `increase()` để phân tích theo thời gian thay vì lấy hiệu hai giá trị thô từ các lần scrape.

### Nhãn metric có cardinality giới hạn

Nhãn phù hợp thường là các tập giá trị nhỏ, ổn định:

| Nhãn | Giá trị ví dụ | Lưu ý |
| --- | --- | --- |
| `outcome` | `success`, `invalid`, `expired`, `reuse_detected`, `revoked`, `store_error` | Enum do ứng dụng kiểm soát |
| `client_class` | `web`, `mobile`, `service`, `unknown` | Nhóm client đã chuẩn hóa |
| `issuer` | `primary`, `partner_a` | Alias cấu hình có số lượng giới hạn |
| `reason` | `reuse`, `admin_revocation`, `logout`, `compromise_response` | Chỉ dùng enum |
| `environment` | `prod`, `staging` | Có thể lấy từ resource attributes |

Không đưa các giá trị sau vào label:

- Raw refresh token, access token, JWT, `jti`, `kid` tự do.
- Token family ID, session ID, request ID, trace ID.
- User ID, email, subject, tenant ID không giới hạn.
- IP address, user-agent nguyên văn hoặc URL có path động.
- Exception message hoặc reason string do đầu vào bên ngoài cung cấp.

Mỗi giá trị label mới có thể tạo thêm một time series. Nếu dùng family ID hoặc user ID làm label, số series có thể tăng theo lượng người dùng và gây áp lực lên Prometheus, đồng thời làm lộ dữ liệu định danh.

Nếu cần điều tra một family cụ thể, dùng structured security event hoặc hệ thống log có kiểm soát truy cập; không dùng metric label để thay thế log.

### Đếm request và reuse nhất quán

Một cách thiết kế là mỗi request refresh tăng đúng một lần `security_refresh_token_requests_total` với outcome cuối cùng. Sự kiện reuse cũng tăng `security_refresh_token_reuse_detected_total` riêng để có metric bảo mật chuyên biệt.

~~~text
refresh thành công:
  requests_total{outcome="success"} += 1
  rotations_total += 1

token hết hạn:
  requests_total{outcome="expired"} += 1
  validation_failures_total{reason="expired"} += 1

reuse được xác nhận:
  requests_total{outcome="reuse_detected"} += 1
  reuse_detected_total += 1
  family_revocations_total{reason="reuse"} += 1
~~~

Đặt một nơi chịu trách nhiệm ghi metric để tránh cùng một sự kiện bị tăng hai lần khi exception được xử lý ở nhiều tầng. Nếu transaction commit thất bại, không ghi rằng family đã được thu hồi thành công; hãy có metric riêng cho revoke attempt/failure khi cần.

## 4. Instrumentation với Micrometer

Ví dụ dưới đây minh họa cách ghi metric bằng Micrometer. `outcome`, `clientClass` và `reason` phải là enum hoặc giá trị được chuẩn hóa từ tập cho phép, không lấy nguyên văn từ request.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;

enum RefreshOutcome {
    SUCCESS,
    INVALID,
    EXPIRED,
    REUSE_DETECTED,
    REVOKED,
    STORE_ERROR
}

final class RefreshTokenMetrics {

    private final MeterRegistry registry;

    RefreshTokenMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    void recordRequest(
        RefreshOutcome outcome,
        String clientClass,
        Duration duration
    ) {
        String safeClientClass = normalizeClientClass(clientClass);
        String safeOutcome = outcome.name().toLowerCase();

        Counter.builder("security.refresh.token.requests")
            .tag("outcome", safeOutcome)
            .tag("client_class", safeClientClass)
            .register(registry)
            .increment();

        Timer.builder("security.refresh.token.request.duration")
            .tag("outcome", safeOutcome)
            .tag("client_class", safeClientClass)
            .register(registry)
            .record(duration);
    }

    void recordReuse(String clientClass) {
        Counter.builder("security.refresh.token.reuse.detected")
            .tag("client_class", normalizeClientClass(clientClass))
            .register(registry)
            .increment();
    }

    void recordFamilyRevocation(String reason) {
        Counter.builder("security.refresh.token.family.revocations")
            .tag("reason", normalizeReason(reason))
            .register(registry)
            .increment();
    }

    private String normalizeClientClass(String value) {
        if ("web".equals(value)) return "web";
        if ("mobile".equals(value)) return "mobile";
        if ("service".equals(value)) return "service";
        return "unknown";
    }

    private String normalizeReason(String value) {
        if ("reuse".equals(value)) return "reuse";
        if ("logout".equals(value)) return "logout";
        if ("admin_revocation".equals(value)) return "admin_revocation";
        return "other";
    }
}
~~~

Tên metric Micrometer được export theo quy tắc của registry. Ví dụ tên dạng dấu chấm có thể được chuyển thành tên Prometheus với dấu gạch dưới và hậu tố `_total` cho counter. Hãy kiểm tra tên thực tế ở endpoint scrape hoặc qua registry trước khi viết PromQL.

Một cách dùng ở tầng xử lý:

~~~java
try {
    RefreshResult result = refreshService.rotate(rawRefreshToken);
    metrics.recordRequest(
        RefreshOutcome.SUCCESS,
        clientClass,
        elapsedSince(startedAt)
    );
    return result;
} catch (RefreshTokenReuseException ex) {
    metrics.recordReuse(clientClass);
    metrics.recordRequest(
        RefreshOutcome.REUSE_DETECTED,
        clientClass,
        elapsedSince(startedAt)
    );
    throw ex;
}
~~~

Đây là minh họa rút gọn. Trong ứng dụng thật, cần bảo đảm metric chỉ ghi một lần ở ranh giới xử lý request. Nếu service đã ghi reuse và controller cũng ghi lại khi bắt exception, counter sẽ bị double count. Tên metric và nhãn phải được thống nhất trong một instrumentation component.

## 5. Security event để điều tra reuse

Metric trả lời câu hỏi **sự kiện xảy ra bao nhiêu lần và xu hướng ra sao**. Khi cần biết sự kiện nào, family nào bị ảnh hưởng và hành động nào đã diễn ra, cần structured security event.

Ví dụ event:

~~~json
{
  "event.name": "oauth.refresh_token.reuse_detected",
  "event.outcome": "failure",
  "event.severity": "high",
  "timestamp": "2026-11-23T10:15:30Z",
  "issuer_alias": "primary",
  "client_class": "mobile",
  "token_family_ref": "hmac:rotating-reference",
  "token_generation": 2,
  "action": "family_revocation_committed",
  "correlation_id": "request-correlation-id"
}
~~~

Các trường này là ví dụ cấu trúc; chỉ đưa vào event các dữ liệu mà hệ thống thực sự có và được phép lưu. `token_family_ref` nên là tham chiếu giả danh được tạo bằng HMAC với khóa quản lý riêng, có thể xoay theo chính sách. Không dùng hash thuần của token làm nhãn metric hoặc ID công khai. Tham chiếu giả danh vẫn có thể là dữ liệu nhạy cảm và cần hạn chế quyền truy cập, thời hạn lưu giữ.

**Không bao giờ ghi:**

- Header `Authorization` hoặc cookie chứa token.
- Raw access token, refresh token hoặc JWT đầy đủ.
- Private key, client secret, mật khẩu hoặc mã xác thực.
- Claims nhạy cảm không cần thiết như email, tên thật, dữ liệu hồ sơ.
- Nội dung request/response có thể chứa token.

Nên ghi event sau khi hành động quan trọng đã có kết quả rõ ràng. Ví dụ, chỉ ghi `family_revocation_committed` khi transaction thu hồi đã commit; nếu chỉ mới bắt đầu, dùng `family_revocation_attempted` và ghi kết quả sau đó. Điều này tránh dashboard báo đã thu hồi trong khi database rollback.

### Phân biệt metric, log và trace

| Tín hiệu | Dùng để trả lời | Dữ liệu phù hợp |
| --- | --- | --- |
| Metric | Bao nhiêu reuse? Có tăng bất thường không? | Counter, histogram, nhãn enum |
| Security log/event | Family nào bị ảnh hưởng? Hành động nào đã commit? | Event có tham chiếu giả danh, lý do, kết quả |
| Trace | Request đi qua service nào và chậm ở đâu? | Span và correlation ID, không mang token |

Trace attribute cũng phải tuân thủ quy tắc bảo vệ dữ liệu. Không gắn raw token vào span, baggage hoặc exception. Nếu trace cần liên kết với security event, dùng correlation ID được tạo ở server và có chính sách truy cập/retention phù hợp.

## 6. Dashboard theo dõi refresh reuse

Một dashboard hữu ích nên trả lời bốn nhóm câu hỏi.

### Mức độ sự kiện

- Reuse được phát hiện theo phút/giờ.
- Số token family đã thu hồi do reuse.
- Tỷ lệ reuse trên tổng refresh request.
- Phân bố theo issuer alias và client class có cardinality thấp.

### Sức khỏe của luồng refresh

- Tổng request refresh và tỷ lệ success/failure.
- Rotation thành công.
- Độ trễ p50, p95, p99.
- Lỗi đọc/ghi token family store.
- Timeout hoặc lỗi database khiến server không thể xác định trạng thái token.

### Hiệu quả phản ứng

- Số family revoke attempt so với revoke committed.
- Số revoke failure hoặc transaction rollback.
- Thời gian từ reuse detection đến revoke commit.
- Số request tiếp tục bị từ chối từ family đã bị thu hồi, nếu hệ thống đo được.

### Phân tích theo nhóm

So sánh `client_class`, issuer alias, environment hoặc deployment version. Không drill-down bằng cách thêm user ID, token family ID hay IP vào metric labels; dùng security event có kiểm soát khi cần điều tra cụ thể.

## 7. PromQL và cảnh báo

Các ví dụ dưới đây giả định exporter tạo đúng tên metric Prometheus đã nêu. Điều chỉnh tên theo kết quả scrape thực tế.

### Tốc độ reuse trong 5 phút

~~~promql
sum by (issuer, client_class) (
  rate(security_refresh_token_reuse_detected_total[5m])
)
~~~

Đồ thị này giúp nhận ra đợt tăng đột ngột. Nếu metric không có nhãn `issuer`, bỏ nhãn đó khỏi phép nhóm.

### Tỷ lệ reuse trên refresh request

~~~promql
sum by (client_class) (
  rate(security_refresh_token_reuse_detected_total[5m])
)
/
clamp_min(
  sum by (client_class) (
    rate(security_refresh_token_requests_total[5m])
  ),
  0.000001
)
~~~

Tỷ lệ này có ý nghĩa khi counter request và reuse cùng phạm vi, cùng cách đếm và cùng cửa sổ thời gian. Dùng `clamp_min` tránh chia cho zero; không diễn giải tỷ lệ ở lưu lượng cực thấp như một ước lượng ổn định.

### Revoke thất bại

~~~promql
sum by (reason) (
  rate(security_refresh_token_family_revocation_failures_total[5m])
)
~~~

Nếu hệ thống chưa có counter riêng cho revoke failure, nên bổ sung metric đó thay vì suy ra thất bại từ số family revoke thấp hơn số reuse. Hai metric có thể khác phạm vi hoặc khác thời điểm commit.

### Ví dụ alert rule

~~~yaml
groups:
  - name: refresh-token-security
    rules:
      - alert: RefreshTokenReuseDetected
        expr: |
          sum by (issuer, client_class) (
            increase(security_refresh_token_reuse_detected_total[5m])
          ) >= 3
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Refresh token reuse detected"
          description: "Reuse events crossed the configured threshold."

      - alert: RefreshTokenFamilyRevocationFailure
        expr: |
          sum(rate(security_refresh_token_family_revocation_failures_total[5m])) > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Refresh token family revocation is failing"
          description: "Investigate token-store or transaction failures."
~~~

Ngưỡng `3` trong ví dụ chỉ để minh họa cú pháp. Môi trường có ít người dùng có thể cần cảnh báo ngay ở một sự kiện đã xác nhận; hệ thống nhiều client có thể cần threshold và baseline riêng. Một reuse đã xác nhận là tín hiệu bảo mật cần xem xét kể cả khi chưa vượt ngưỡng cảnh báo tổng hợp.

Cảnh báo nên tách hai loại:

- **Security alert:** có reuse được xác nhận, đặc biệt khi family bị thu hồi.
- **Reliability alert:** cơ chế kiểm tra trạng thái hoặc thu hồi family đang lỗi, khiến server không thể thực hiện chính sách an toàn.

Không dùng một cảnh báo duy nhất cho cả replay và database outage vì người trực cần hành động khác nhau.

## 8. Phân biệt replay với race condition và retry

Một client có thể gửi hai refresh request gần như đồng thời do:

- Hai thread cùng đọc một refresh token.
- Ứng dụng mobile gửi retry khi response đầu tiên bị mất.
- Proxy hoặc gateway retry request ngoài dự kiến.
- Nhiều instance của client cùng sử dụng một session.
- Người dùng mở nhiều tab và mỗi tab đều cố refresh.

Trong rotation nghiêm ngặt, request đầu có thể tiêu thụ `RT₀` và phát hành `RT₁`; request thứ hai đến ngay sau đó sẽ thấy `RT₀` đã consumed. Về mặt trạng thái, đây là lần sử dụng lại; về nguyên nhân, nó có thể là race hợp pháp hoặc token đã bị đánh cắp. Chỉ metric không thể kết luận ai là kẻ tấn công.

### Cần bảo đảm atomic state transition

Việc kiểm tra và tiêu thụ token phải nguyên tử. Ví dụ ý tưởng:

~~~sql
UPDATE refresh_token
SET status = 'CONSUMED',
    consumed_at = CURRENT_TIMESTAMP
WHERE token_id = :token_id
  AND status = 'ACTIVE';
~~~

Nếu số hàng cập nhật là một, request đã giành quyền tiêu thụ token. Nếu bằng không, server phải đọc trạng thái đáng tin cậy để phân biệt expired, revoked, unknown và previously consumed. Không dùng thao tác read-then-write không khóa vì hai request đồng thời có thể cùng thấy token active và phát hành hai nhánh token family.

### Chọn chính sách concurrency có chủ đích

- Dùng transaction/compare-and-set hoặc cơ chế lưu trữ tương đương để chỉ một request thắng.
- Tránh retry tự động refresh ở nhiều tầng mà không có hợp đồng idempotency.
- Cân nhắc client single-flight: tại một thời điểm chỉ một request refresh cho một phiên.
- Nếu cần idempotent retry, thiết kế khóa idempotency và cách trả lại kết quả an toàn; không cho phép dùng lại token cũ tùy ý trong một grace period rộng.
- Ghi nhận tín hiệu race/retry có thể quan sát được, nhưng không tự động gắn nhãn mọi lần reuse là hành vi ác ý.
- Chính sách revoke family phải nhất quán với threat model và khả năng ảnh hưởng người dùng hợp pháp.

Một grace period có thể giảm false positive nhưng cũng kéo dài cửa sổ replay. Chỉ dùng khi đã phân tích rủi ro, ràng buộc client và có cách bảo vệ kết quả idempotent. Không thêm grace period chỉ để làm dashboard bớt cảnh báo.

## 9. Từ metric đến quy trình phản ứng

Khi reuse được xác nhận, quy trình có thể gồm:

1. Xác định event và issuer/client class liên quan.
2. Kiểm tra family revocation đã commit chưa.
3. Đối chiếu các security event cùng tham chiếu giả danh và correlation ID.
4. Kiểm tra dấu hiệu retry/race từ client version, request timing hoặc deployment.
5. Đánh giá các request tiếp theo từ family đã bị thu hồi.
6. Nếu có dấu hiệu compromise, áp dụng quy trình incident response: thu hồi phiên liên quan, yêu cầu xác thực lại và điều tra nguồn rò rỉ.
7. Ghi nhận nguyên nhân gốc và cập nhật policy, client hoặc cảnh báo.

Không tự động khóa toàn bộ user hoặc tenant chỉ vì một metric tăng. Phạm vi phản ứng cần dựa trên bằng chứng, token family liên quan và chính sách của authorization server.

### Metric phục vụ điều tra, không phải kết luận

Một đợt tăng reuse có thể do tấn công, bug trong client, nhiều instance dùng chung token hoặc retry sau timeout. Kết hợp metric với event, trace, phiên bản client và lịch triển khai để tìm nguyên nhân. Không suy ra danh tính hoặc địa chỉ của kẻ tấn công chỉ từ một counter.

## 10. Kiểm thử instrumentation và reuse detection

Test cần kiểm tra cả trạng thái token lẫn telemetry. Không chỉ assert response 401; cần xác minh metric đúng và không ghi nhầm các lỗi khác thành reuse.

| Kịch bản | Trạng thái kỳ vọng | Metric/event |
| --- | --- | --- |
| Refresh token active được dùng lần đầu | Rotation thành công, token kế tiếp được phát hành | Requests success + rotations tăng |
| Refresh token đã consumed được dùng lại | Từ chối; revoke family theo policy | Reuse detected tăng; family revocation committed tăng nếu commit thành công |
| Token hết hạn | Từ chối | Outcome expired; reuse không tăng |
| Token bị admin revoke | Từ chối | Outcome revoked; reason admin_revocation |
| Token không tồn tại | Từ chối | Outcome invalid; reuse không tăng |
| Hai request đồng thời | Chỉ một request tiêu thụ thành công | Một rotation; request còn lại được phân loại theo chính sách concurrency |
| Database lỗi khi đọc trạng thái | Fail closed | Store error tăng; không ghi reuse nếu chưa xác nhận |
| Database rollback khi revoke | Không báo revoke committed | Revoke failure tăng hoặc event attempted/failed |
| Request retry sau timeout | Theo idempotency/concurrency policy | Telemetry cho biết retry/race nếu có tín hiệu |

### Kiểm tra không rò rỉ token

Trong test log capture và metric registry, xác minh:

- Không có raw refresh token trong message, tag hoặc attribute.
- Không có Authorization header hoặc cookie.
- Không có token family ID, user ID hoặc tenant ID trong metric labels.
- Nhãn `outcome`, `client_class`, `reason` chỉ nhận giá trị đã cho phép.
- Security event chỉ lưu tham chiếu giả danh nếu cần correlation và có chính sách retention.
- Counter reuse tăng đúng một lần cho mỗi sự kiện được xác nhận.
- Counter revoke committed chỉ tăng sau khi transaction commit.

### Kiểm tra cảnh báo

Dùng dữ liệu metric test hoặc rule test để xác minh:

- Một đợt reuse vượt ngưỡng tạo alert.
- Reuse đơn lẻ vẫn có thể được tìm trong dashboard/event dù chưa vượt threshold.
- Revoke failure tạo cảnh báo độ tin cậy riêng.
- Lưu lượng thấp không tạo tỷ lệ vô hạn do mẫu số bằng zero.
- Nhãn không làm tăng series theo mỗi user, token hoặc request.

## 11. Các lỗi quan sát thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gộp mọi refresh failure thành reuse | Cảnh báo giả và số liệu sai | Phân loại invalid, expired, revoked, reuse, store error |
| Chỉ đo số request, không đo family revoke | Không biết phản ứng bảo mật đã hoàn tất chưa | Đo attempt, committed và failure |
| Dùng token ID/user ID làm label | Cardinality cao và lộ định danh | Label enum; correlation ở security event |
| Log raw refresh token để debug | Token có thể bị lấy từ log | Chỉ log event metadata và tham chiếu giả danh |
| Đếm reuse ở nhiều tầng | Counter bị tăng nhiều lần | Chọn một điểm ghi metric có ownership |
| Ghi revoke trước commit | Dashboard báo thành công giả | Ghi committed sau transaction commit |
| Không đo lỗi token store | Replay detection có thể suy giảm âm thầm | Counter lỗi dependency và alert riêng |
| Không tính race condition | Client hợp pháp bị khóa phiên ngoài ý muốn | Atomic update, single-flight/idempotency và phân tích telemetry |
| Dùng grace period rộng | Tăng cửa sổ phát lại | Giới hạn và đánh giá threat model |
| JWT refresh token stateless nhưng tuyên bố có reuse detection | Không có trạng thái để nhận biết token đã dùng | Lưu `jti`/family state hoặc chọn opaque token stateful |

## 12. Checklist triển khai production

- [ ] Rotation tiêu thụ token cũ và phát hành token kế tiếp trong một thao tác nguyên tử.
- [ ] Token family có trạng thái và quan hệ cần thiết để phát hiện token đã dùng lại.
- [ ] Reuse chỉ được ghi khi có bằng chứng token đã consumed được gửi lại.
- [ ] Có counter request, rotation, reuse, family revoke và lỗi token store.
- [ ] Có histogram độ trễ refresh.
- [ ] Metric labels là tập hữu hạn, không chứa token/user/session/family ID.
- [ ] Security event không chứa raw token, cookie hoặc Authorization header.
- [ ] Event phân biệt revoke attempt, committed và failed.
- [ ] Có dashboard cho reuse rate, family revocation và store health.
- [ ] Có alert security riêng với alert reliability.
- [ ] Có chính sách concurrency và retry để xử lý race hợp pháp.
- [ ] Có test expired, revoked, unknown, replay, concurrent refresh và rollback.
- [ ] Có retention, phân quyền và bảo vệ cho security event.
- [ ] Quy trình incident response biết cách thu hồi family và yêu cầu xác thực lại.

## Ghi nhớ

- Refresh token rotation tạo ra quan hệ giữa token cũ và token mới; token đã consumed xuất hiện lại là tín hiệu reuse.
- Metric đếm xu hướng và mức độ; security event hỗ trợ điều tra một lần phát hiện cụ thể.
- Không dùng raw token, user ID hoặc token family ID làm metric label.
- Reuse detection cần trạng thái phía server; chữ ký JWT hợp lệ không chứng minh token chưa từng được sử dụng.
- Request đồng thời và retry có thể tạo tín hiệu giống replay; cần atomic state transition và chính sách concurrency.
- Chỉ ghi family revocation là thành công sau khi transaction đã commit.
- Quan sát cả khả năng phát hiện và khả năng thực hiện thu hồi; store lỗi có thể làm suy yếu toàn bộ cơ chế.

### Tiêu chuẩn tham khảo

- **RFC 6749 — OAuth 2.0 Authorization Framework:** vai trò của refresh token trong token endpoint.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** refresh token rotation, sender-constrained refresh token và phát hiện reuse.
- **RFC 7009 — OAuth 2.0 Token Revocation:** cơ chế thu hồi token.
- **OpenTelemetry Metrics:** instrument, attributes và quy tắc cardinality cho telemetry.
- **Prometheus documentation:** counter, histogram, `rate()`, alerting rules và quản lý time series.
- **Micrometer documentation:** Counter, Timer, MeterRegistry và quy tắc đặt tên metric.
