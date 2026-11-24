# Metric validation success và failure

Một API có thể xác minh hàng nghìn access token mỗi giây. Khi token hợp lệ, request được tiếp tục; khi token sai chữ ký, hết hạn, sai issuer hoặc sai audience, hệ thống phải từ chối. Nếu chỉ nhìn HTTP status hoặc log từng request, đội vận hành khó biết bao nhiêu token được xác minh thành công, vì sao token bị từ chối, validator có đang lỗi phụ thuộc hay không và sự cố ảnh hưởng tới API nào.

**Metric validation success và failure** là cách đo có cấu trúc kết quả xác minh token, thời gian xử lý và lỗi của các thành phần phụ thuộc như JWKS, introspection hoặc cache. Metrics giúp phát hiện cấu hình issuer sai, khóa ký bị xoay, token hết hạn hàng loạt, tấn công dò token hoặc Authorization Server mất khả dụng.

Bài học thuộc chương **Observability** của mô-đun **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Chủ đề gắn với mô hình tin cậy và vòng đời token bảo mật: phân biệt JWT, opaque token, access token, refresh token; kiểm tra claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại trong OAuth 2.0/OIDC.

Sau bài này, bạn có thể:

- Thiết kế metrics cho validation thành công, token bị từ chối và lỗi hạ tầng.
- Phân biệt **authentication/validation** với **authorization** để thống kê đúng nguyên nhân.
- Định nghĩa metric name, label có cardinality kiểm soát và không chứa token/PII.
- Theo dõi JWT, opaque token, JWKS, introspection và cache.
- Viết truy vấn PromQL để theo dõi tỷ lệ, số lượng, latency và xu hướng failure.
- Thiết lập dashboard, alert và test để bảo đảm instrumentation phản ánh đúng quyết định bảo mật.

## 1. Đo điều gì khi xác minh token?

Một request đến resource server thường đi qua các bước:

1. Đọc header Authorization và parse Bearer token.
2. Xác định loại token và validation profile được phép.
3. Với JWT: xác minh chữ ký, issuer, audience, thời gian và claims bắt buộc.
4. Với opaque token: gọi introspection hoặc cơ chế xác minh do Authorization Server (AS) cung cấp.
5. Kiểm tra trạng thái thu hồi và các ràng buộc như sender constraint nếu có.
6. Khi token hợp lệ, thực hiện **authorization** theo scope, route/action, tenant và quyền trên tài nguyên.
7. Ghi nhận kết quả, trả response và chuyển request nếu được phép.

Metrics cần phản ánh đúng từng giai đoạn:

| Giai đoạn | Câu hỏi vận hành | Ví dụ kết quả |
|---|---|---|
| Parse credential | Có Bearer header đúng cấu trúc không? | missing, malformed, parsed |
| Token validation | Chứng cứ có hợp lệ theo issuer/profile không? | accepted, rejected, error |
| Dependency | JWKS/introspection/cache có hoạt động không? | success, timeout, unavailable |
| Authorization | Chủ thể có quyền gọi action này không? | allow, deny |
| HTTP handling | API trả kết quả gì? | 2xx, 401, 403, 5xx |

**Không gộp tất cả vào một metric auth_failed.** Token hết hạn là validation rejection; introspection timeout là dependency error; token hợp lệ nhưng thiếu orders:write là authorization denial. Ba tình huống cần cách xử lý và alert khác nhau.

## 2. Phân biệt validation failure, authorization denial và dependency error

Đây là quy tắc quan trọng nhất khi thiết kế metric:

| Tình huống | Validation | Authorization | Phân loại metric |
|---|---|---|---|
| Token có chữ ký, issuer, audience và thời gian hợp lệ | Thành công | Có thể tiếp tục | outcome=accepted |
| JWT chữ ký sai | Bị từ chối | Chưa thực hiện | outcome=rejected, reason=invalid_signature |
| JWT hết hạn | Bị từ chối | Chưa thực hiện | outcome=rejected, reason=expired |
| Sai issuer hoặc audience | Bị từ chối | Chưa thực hiện | outcome=rejected, reason tương ứng |
| Opaque token introspection trả active=false | Bị từ chối | Chưa thực hiện | outcome=rejected, reason=inactive |
| Introspection timeout | Chưa xác minh được | Không được cấp quyền | outcome=error, reason=introspection_timeout |
| JWKS không thể lấy khóa mới cần thiết | Chưa xác minh được | Không được cấp quyền | outcome=error, reason=jwks_unavailable |
| Token hợp lệ nhưng thiếu scope | Thành công | Bị từ chối | Authorization decision=deny, reason=insufficient_scope |
| Token hợp lệ nhưng sai tenant/resource ownership | Thành công | Bị từ chối | Authorization decision=deny, reason theo policy |
| Không có Bearer header | Không có token để xác minh | Chưa thực hiện | Credential parse=missing; không tính là malformed JWT |

401 Unauthorized thường tương ứng thiếu hoặc không chấp nhận được credential; 403 Forbidden thường tương ứng principal đã xác thực nhưng không có quyền. API contract có thể có ngoại lệ, nhưng metric phải lưu **lý do nội bộ chính xác**, không chỉ suy luận từ status code.

Không nên tính lỗi AS hoặc timeout thành token invalid. Nếu AS không phản hồi, hệ thống chưa biết token có hợp lệ hay không; thống kê thành invalid sẽ làm sai tỷ lệ từ chối và che giấu lỗi hạ tầng.

## 3. Bộ metrics cốt lõi

Nên bắt đầu bằng một tập metric nhỏ, có định nghĩa và đơn vị rõ:

| Metric logic | Loại | Ý nghĩa |
|---|---|---|
| security.token.validation | Counter | Số lần validation kết thúc theo outcome/reason |
| security.token.validation.duration | Timer/Histogram | Thời gian xử lý validation |
| security.token.validation.dependency | Counter | Lỗi phụ thuộc JWKS, introspection hoặc cache |
| security.token.introspection.requests | Counter | Số request introspection theo kết quả |
| security.token.introspection.duration | Timer/Histogram | Độ trễ gọi AS introspection |
| security.token.jwks.refresh | Counter | Kết quả refresh JWKS |
| security.token.cache.operations | Counter | Hit, miss, error theo loại cache |
| security.authorization.decision | Counter | Quyết định allow/deny sau validation |
| security.authorization.decision.duration | Timer/Histogram | Thời gian áp dụng policy authorization |

Tên metric export thực tế phụ thuộc thư viện và backend. Ví dụ Micrometer có thể dùng tên dạng dấu chấm, sau đó Prometheus naming convention chuyển thành tên snake_case và counter thường có hậu tố _total.

### 3.1. Counter cho validation

Một metric validation nên có outcome rõ ràng:

```text
security_token_validation_total{
  token_format="jwt",
  outcome="accepted",
  reason="none",
  issuer="company_idp",
  resource_server="orders_api"
} 12500
```

Các outcome khuyến nghị:

- accepted: token đã đáp ứng validation profile.
- rejected: token không hợp lệ theo profile hoặc policy xác thực.
- error: không thể hoàn tất xác minh do lỗi dependency/hệ thống.

Reason nên là enum cố định, ví dụ:

| Nhóm | Reason gợi ý |
|---|---|
| Parse | missing, malformed_header, malformed_token |
| Signature/key | invalid_signature, unknown_kid, unsupported_algorithm |
| Issuer/audience | issuer_mismatch, audience_mismatch |
| Time | expired, not_yet_valid, issued_at_invalid, lifetime_exceeded |
| Claim/profile | missing_required_claim, malformed_claim, wrong_token_type |
| Opaque/revocation | inactive, revoked, introspection_invalid_response |
| Dependency | introspection_timeout, introspection_unavailable, jwks_unavailable, cache_error |

Không dùng exception message tự do làm label. Chuyển lỗi thư viện thành mã reason đã định nghĩa để label không tạo vô hạn giá trị.

### 3.2. Histogram cho latency

Đo latency validation để nhận biết:

- JWT validation chậm bất thường dù JWKS đã cache.
- Opaque token tăng độ trễ do introspection.
- Cache miss hoặc JWKS refresh làm tăng latency.
- Một issuer/resource server có vấn đề riêng.

Ví dụ metric logic:

```text
security_token_validation_duration_seconds_bucket
security_token_validation_duration_seconds_sum
security_token_validation_duration_seconds_count
```

Histogram cần bucket phù hợp với đặc tính hệ thống. JWT local validation thường nhanh hơn một lần gọi mạng introspection; có thể theo dõi riêng token_format để không trộn hai phân bố latency khác nhau.

### 3.3. Dependency metrics

Đối với opaque token, theo dõi request introspection, timeout, HTTP error và latency. Đối với JWT, theo dõi JWKS fetch/refresh, unknown kid, cache hit/miss và lỗi xác minh khóa. Những metric này giúp phân biệt:

- Người dùng gửi token sai.
- AS trả active=false.
- AS hoặc mạng đang lỗi.
- Gateway giữ JWKS cũ hoặc không tìm thấy key.
- Cache bị quá tải hoặc lỗi kết nối.

Không ghi giá trị token, raw kid tùy ý hoặc URL do token cung cấp làm label. Nếu cần phân biệt key rotation, dùng trạng thái hữu hạn như refresh_result=success|failure và log sự kiện có kiểm soát.

## 4. Thiết kế labels: cardinality và dữ liệu nhạy cảm

Label giúp lọc metric theo token format, issuer, resource server, outcome và reason. Tuy nhiên, mỗi tổ hợp label tạo một time series. Nếu label nhận giá trị tùy ý theo request, số series có thể tăng không giới hạn, làm tăng chi phí và gây mất ổn định hệ thống metrics.

### 4.1. Labels nên dùng

| Label | Giá trị ví dụ | Quy tắc |
|---|---|---|
| token_format | jwt, opaque, unknown | Tập hữu hạn |
| outcome | accepted, rejected, error | Enum cố định |
| reason | expired, invalid_signature, audience_mismatch | Enum cố định, không phải exception text |
| issuer | company_idp, partner_idp | Alias cấu hình, không lấy raw iss tùy ý |
| resource_server | orders_api, payments_api | Tên service cấu hình |
| validation_profile | user_access, service_access | Tập profile đã định nghĩa |
| dependency | jwks, introspection, cache | Enum |
| dependency_result | success, timeout, unavailable | Enum |
| decision | allow, deny | Enum |
| action | orders_read, orders_create, payments_charge | Action catalog hữu hạn |

### 4.2. Labels không nên dùng

Không đưa các giá trị sau vào Prometheus labels hoặc metric tags:

- Access token, refresh token, raw JWT, opaque token hoặc token fingerprint theo từng request.
- sub, jti, email, username, session ID hoặc client-generated request ID.
- IP address, user-agent hoặc URL đầy đủ có ID động.
- Tenant ID nếu số tenant lớn hoặc tăng theo thời gian; dùng log/tracing có kiểm soát hoặc nhóm tenant theo phân loại hữu hạn nếu thực sự cần.
- Raw issuer URL, arbitrary audience hoặc kid do bên ngoài cung cấp nếu không có giới hạn.
- Exception message, SQL error hoặc dữ liệu lấy trực tiếp từ header/request.

Một hệ có 50.000 tenant và 20 reason có thể tạo hàng triệu series nếu gắn tenant ID vào mọi counter. Metrics là dữ liệu tổng hợp; cần dùng log/event bảo vệ quyền truy cập để điều tra một tenant hoặc request cụ thể.

### 4.3. Phân biệt metric và log

| Dữ liệu | Nơi phù hợp | Ví dụ |
|---|---|---|
| Tổng validation accepted/rejected | Metric | outcome=accepted |
| Lý do từ chối thuộc enum | Metric | reason=expired |
| Request ID/correlation ID | Log hoặc trace | request_id=req-8321 |
| Subject/client cụ thể | Log audit có kiểm soát | client_id=billing-worker-prod |
| Token raw/refresh token | Không ghi log | Không được thu thập |
| Stack trace của dependency error | Log kỹ thuật đã redaction | Lỗi timeout introspection |

Nếu cần liên kết metric với trace, có thể dùng exemplar chứa trace ID theo backend hỗ trợ; không dùng token hoặc subject làm exemplar.

## 5. Đo JWT và opaque token riêng

### 5.1. JWT validation

JWT access token thường được xác minh offline sau khi gateway/resource server có khóa công khai từ JWKS. Metrics nên ghi nhận:

- Kết quả xác minh chữ ký.
- Issuer, audience và token type có hợp lệ không.
- Expiration/not-before và claim profile.
- Unknown kid, JWKS refresh và lỗi lấy khóa.
- Thời gian validation, phân biệt cache hit/miss nếu có.

Một JWT có chữ ký đúng nhưng sai aud phải được tính là rejected, reason audience_mismatch. Một JWT hết hạn là rejected/expired, không phải dependency error. Nếu JWKS endpoint timeout và validator không có khóa cần thiết, kết quả là error/jwks_unavailable.

**JWKS cache hit không đồng nghĩa token validation thành công.** Mỗi request vẫn cần kiểm tra signature, issuer, audience, expiry và policy; cache khóa chỉ giảm việc tải public key.

### 5.2. Opaque token và introspection

Opaque token thường cần AS introspection hoặc cơ chế tra cứu trạng thái:

```text
security_token_introspection_requests_total{
  result="active"
}
security_token_introspection_requests_total{
  result="inactive"
}
security_token_introspection_requests_total{
  result="timeout"
}
security_token_introspection_duration_seconds
```

Phân biệt:

- active=false: AS đã phản hồi rằng token không active; đây là kết quả từ chối token.
- Timeout/5xx/response không đọc được: chưa xác minh được; đây là dependency/system error.
- active=true nhưng thiếu audience/scope/expiry thiết yếu: response không đáp ứng hợp đồng; không tự cho phép.
- Cache hit active=true: không phải lần gọi introspection mới. Có thể ghi metric cache riêng; không tính nhầm là AS vừa xác minh token.

Nếu có cache introspection, theo dõi hit/miss và TTL/freshness theo policy. Cache entry phải hết hạn trước token expiry và giới hạn độ trễ thu hồi. Không dùng sliding expiration khiến active=true tồn tại vô hạn.

## 6. Định nghĩa metric contract

Trước khi instrument code, đội phát triển và vận hành nên thống nhất metric contract:

| Thuộc tính | Quy ước đề xuất |
|---|---|
| Tên metric | security.token.validation |
| Loại | Counter |
| Đơn vị | Lần validation |
| Tăng khi nào | Mỗi lần một validation attempt kết thúc |
| Outcome | accepted, rejected, error |
| Reason | Enum có giới hạn |
| Phạm vi | Một resource server/validation profile |
| Không bao gồm | Token raw, subject, request ID, tenant ID tùy ý |

Với metric latency:

| Thuộc tính | Quy ước đề xuất |
|---|---|
| Tên | security.token.validation.duration |
| Loại | Timer/Histogram |
| Đơn vị | Giây |
| Điểm bắt đầu | Trước bước validation |
| Điểm kết thúc | Khi accepted/rejected/error |
| Ghi nhận | Tất cả attempt đã bắt đầu |
| Phân loại | token_format, outcome, issuer, resource_server |

Không đo duration chỉ với request thành công; nếu lỗi timeout không được ghi latency, p95/p99 sẽ trông tốt giả tạo đúng lúc hệ thống đang có vấn đề.

### Mô hình kết quả chuẩn hóa

Một enum nội bộ có thể là:

```java
public enum ValidationOutcome {
    ACCEPTED,
    REJECTED,
    ERROR
}

public enum ValidationReason {
    NONE,
    INVALID_SIGNATURE,
    ISSUER_MISMATCH,
    AUDIENCE_MISMATCH,
    EXPIRED,
    NOT_YET_VALID,
    MALFORMED_CLAIM,
    WRONG_TOKEN_TYPE,
    INACTIVE,
    INTROSPECTION_TIMEOUT,
    JWKS_UNAVAILABLE,
    CACHE_ERROR,
    INTERNAL_ERROR
}
```

INSUFFICIENT_SCOPE không nằm trong validation reason vì đó là authorization denial sau khi token đã được xác minh. Nên có enum riêng cho AuthorizationDecision và AuthorizationReason.

## 7. Ví dụ instrumentation với Micrometer

Ví dụ dưới đây minh họa cách ghi counter và timer trong Java. Các label được truyền từ enum/configuration đã kiểm soát:

```java
public final class TokenValidationMetrics {

    private final MeterRegistry registry;

    public TokenValidationMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public Timer.Sample start() {
        return Timer.start(registry);
    }

    public void record(
            Timer.Sample sample,
            String tokenFormat,
            ValidationOutcome outcome,
            ValidationReason reason,
            String issuerAlias,
            String resourceServer) {

        Tags tags = Tags.of(
            "token_format", tokenFormat,
            "outcome", outcome.name().toLowerCase(Locale.ROOT),
            "reason", reason.name().toLowerCase(Locale.ROOT),
            "issuer", issuerAlias,
            "resource_server", resourceServer
        );

        registry.counter("security.token.validation", tags).increment();
        sample.stop(registry.timer("security.token.validation.duration", tags));
    }
}
```

Đây là ví dụ theo API Micrometer; cần điều chỉnh theo phiên bản và cách đặt tên metric trong dự án. Chỉ gọi record **một lần cho mỗi attempt kết thúc**. Không ghi accepted ở decoder rồi lại ghi accepted ở filter cho cùng một request, nếu không counter sẽ đếm gấp đôi. Cần chọn một ranh giới instrumentation rõ ràng, ví dụ kết quả validation cuối cùng tại resource server.

Với authorization, dùng metric riêng:

```java
registry.counter(
    "security.authorization.decision",
    Tags.of(
        "decision", "deny",
        "reason", "insufficient_scope",
        "action", "orders_create",
        "resource_server", "orders_api"
    )
).increment();
```

Không lấy request URI trực tiếp làm label vì path có thể chứa ID động. Map route/action sang tên catalog cố định.

## 8. Prometheus query cho success và failure

Giả sử exporter tạo counter:

```promql
security_token_validation_total
```

### 8.1. Tốc độ validation theo outcome

```promql
sum by (outcome) (
  rate(security_token_validation_total[5m])
)
```

Biểu đồ này cho thấy số lần accepted/rejected/error mỗi giây trong cửa sổ 5 phút.

### 8.2. Tỷ lệ rejected trên các attempt đã có kết quả

```promql
sum(rate(security_token_validation_total{outcome="rejected"}[5m]))
/
clamp_min(
  sum(rate(security_token_validation_total{outcome=~"accepted|rejected"}[5m])),
  1e-9
)
```

Mẫu số loại error ra vì đó là request chưa xác định token hợp lệ hay không. Theo dõi error rate riêng:

```promql
sum(rate(security_token_validation_total{outcome="error"}[5m]))
/
clamp_min(sum(rate(security_token_validation_total[5m])), 1e-9)
```

Tỷ lệ rejected tăng không tự động có nghĩa hệ thống lỗi: có thể là bot dò token, client gửi token hết hạn, sai cấu hình audience hoặc đợt deploy làm issuer thay đổi. Cần xem reason, traffic và dependency metrics.

### 8.3. Failure theo reason và API

```promql
sum by (reason, resource_server) (
  rate(security_token_validation_total{outcome="rejected"}[5m])
)
```

Một đợt audience_mismatch tăng riêng ở payments_api có thể là client đang dùng token sai audience. expired tăng đồng loạt sau deploy có thể liên quan clock skew hoặc token lifetime. invalid_signature tăng sau key rotation có thể là JWKS refresh/cache.

### 8.4. Latency p95/p99

```promql
histogram_quantile(
  0.95,
  sum by (le, token_format) (
    rate(security_token_validation_duration_seconds_bucket[5m])
  )
)
```

Theo dõi p95/p99 riêng cho JWT và opaque token; opaque introspection có network latency khác local JWT validation. Nếu exporter dùng tên metric khác, thay bằng tên thực tế trong registry.

### 8.5. Introspection timeout

```promql
sum(rate(security_token_introspection_requests_total{result="timeout"}[5m]))
```

Theo dõi thêm tỷ lệ timeout trên tổng introspection request và p95 latency để tránh alert chỉ dựa trên số tuyệt đối khi traffic biến động.

## 9. Dashboard vận hành

Một dashboard cho token validation nên có các nhóm:

| Panel | Dữ liệu | Mục đích |
|---|---|---|
| Validation volume | accepted/rejected/error rate | Biết lưu lượng và outcome |
| Reject reasons | expired, invalid signature, issuer/audience mismatch, malformed claim, inactive | Nhận biết nguyên nhân từ chối |
| Validation latency | p50/p95/p99 theo token format | Phát hiện suy giảm hiệu năng |
| JWT key health | JWKS refresh success/failure, unknown kid, cache hit/miss | Phát hiện vấn đề xoay khóa |
| Opaque/introspection health | request rate, timeout, 4xx/5xx, latency, active/inactive | Phát hiện AS hoặc mạng lỗi |
| Authorization decisions | allow/deny theo action/reason | Phân biệt token hợp lệ nhưng thiếu quyền |
| HTTP result | 2xx/401/403/5xx theo route/service | Đối chiếu tác động tới API |
| Dependency health | AS, cache, network error | Tìm nguồn gây lỗi |

Dashboard nên hỗ trợ lọc theo issuer alias, resource server, token format và môi trường. Tránh dashboard có dropdown chứa hàng chục nghìn tenant, subject hoặc token fingerprint.

### Success rate không phải mục tiêu duy nhất

Một tỷ lệ validation success cao có thể là dấu hiệu tốt, nhưng cũng có thể do validator vô tình fail open và chấp nhận token sai. Tỷ lệ rejected cao có thể là hệ thống bảo vệ đang hoạt động đúng trước một đợt dò quét.

Do đó:

- Theo dõi accepted/rejected/error riêng biệt.
- Đo dependency availability/latency riêng.
- Kiểm thử token sai vẫn bị từ chối trong khi AS/cache lỗi.
- Theo dõi authorization deny riêng để phát hiện client thiếu scope hoặc cố gọi action ngoài quyền.
- Đối chiếu metrics với audit event và HTTP outcome, không tối ưu một con số success rate đơn lẻ.

## 10. Alert: cảnh báo đúng điều cần điều tra

| Tín hiệu | Ý nghĩa có thể có | Hành động điều tra |
|---|---|---|
| error tăng đột ngột | AS, JWKS, cache hoặc network không khả dụng | Kiểm tra dependency, timeout, deploy và circuit breaker |
| invalid_signature tăng mạnh | Token bị sửa, key mismatch hoặc cấu hình issuer/JWKS sai | Kiểm tra key rotation, kid, issuer và nguồn phát hành |
| audience_mismatch tăng ở một API | Client gửi token cho resource server khác | Kiểm tra client registration, token exchange và route |
| expired tăng đồng loạt | Token lifetime, clock skew hoặc refresh flow | Kiểm tra NTP, AS clock và refresh behavior |
| unknown_kid tăng liên tục | AS xoay khóa hoặc bị flood kid giả | Kiểm tra JWKS, rate limit forced refresh |
| Introspection timeout/p95 tăng | AS hoặc mạng chậm | Kiểm tra AS saturation, DNS, TLS, connection pool |
| inactive tăng | Token bị thu hồi/hết hiệu lực hoặc client dùng token cũ | Kiểm tra logout, revocation và refresh |
| Authorization insufficient_scope tăng | Client gọi action chưa được cấp quyền | Kiểm tra scope mapping, release và client behavior |
| Validation latency tăng nhưng dependency ổn | CPU/parser/crypto/cache contention | Profile validator, kích thước token và concurrency |

Alert nên có ngưỡng theo traffic baseline, cửa sổ thời gian và mức độ ảnh hưởng. Ví dụ: cảnh báo khi introspection timeout ratio vượt ngưỡng trong 5 phút và số request tối thiểu đủ lớn; tránh alert một timeout đơn lẻ ở hệ thống ít traffic.

### Availability SLI cho validator

Có thể định nghĩa availability của bước validation dependency dựa trên số lần xác minh hoàn tất, tách khỏi tỷ lệ token hợp lệ:

```text
validation_completion =
  accepted + rejected

validation_dependency_error =
  error caused by unavailable dependency
```

Ví dụ SLI:

```promql
1 -
(
  sum(rate(security_token_validation_total{outcome="error"}[5m]))
  /
  clamp_min(sum(rate(security_token_validation_total[5m])), 1e-9)
)
```

Đây chỉ là SLI minh họa. Cần phân loại error để chỉ tính lỗi dependency/hệ thống vào availability; lỗi lập trình hoặc lỗi nội bộ có thể được theo dõi riêng. **Rejected token không phải lỗi availability**: validator đã hoàn thành và bảo vệ đúng khi từ chối credential không hợp lệ.

## 11. Kiểm thử instrumentation

Metrics cũng là một phần của security behavior. Nếu metric sai, đội vận hành có thể kết luận sai về sự cố. Tạo test cho cả kết quả và side effect instrumentation:

| Ca test | Input | Metric mong đợi |
|---|---|---|
| JWT hợp lệ | Chữ ký, issuer, audience, thời gian và claims hợp lệ | accepted tăng 1 |
| JWT chữ ký sai | Payload bị sửa sau khi ký | rejected/invalid_signature tăng 1 |
| JWT hết hạn | exp đã qua | rejected/expired tăng 1 |
| JWT sai audience | aud không chứa API | rejected/audience_mismatch tăng 1 |
| Claim malformed | exp sai kiểu hoặc thiếu claim bắt buộc | rejected/malformed_claim hoặc reason cụ thể tăng 1 |
| Opaque inactive | Introspection trả active=false | rejected/inactive tăng 1 |
| Introspection timeout | AS không phản hồi | error/introspection_timeout tăng 1, không tăng rejected |
| JWKS unavailable | Không lấy được khóa cần thiết | error/jwks_unavailable tăng 1 |
| Token đúng nhưng thiếu scope | Scope không cho action | Validation accepted tăng 1; authorization deny/insufficient_scope tăng 1 |
| Token sai tenant | Tenant binding không khớp resource | Validation có thể accepted; authorization deny tăng |
| Không có Bearer header | Request không có credential | Parse missing; không tăng malformed JWT |
| Cache hit | Introspection result còn fresh | Cache hit tăng; không giả lập một AS introspection mới |
| Một request qua nhiều filter | Cùng validation attempt | Chỉ tăng counter validation một lần |
| Token raw chứa dữ liệu nhạy cảm | Gửi token test có marker | Không xuất hiện trong metric label, log hoặc trace |
| Label bất thường | kid, subject hoặc URL rất dài | Bị map thành enum/alias hoặc không đưa vào label |

Kiểm tra thêm histogram count tăng đúng một lần, Timer ghi cả accepted/rejected/error, và metric vẫn được ghi khi exception xảy ra. Không để exception thoát trước finally khiến latency/error attempt không được quan sát.

### Test bằng metric registry trong Java

Ví dụ kiểm tra counter với Micrometer SimpleMeterRegistry:

```java
@Test
void recordsExpiredTokenAsRejected() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    TokenValidationMetrics metrics = new TokenValidationMetrics(registry);

    Timer.Sample sample = metrics.start();
    metrics.record(
        sample,
        "jwt",
        ValidationOutcome.REJECTED,
        ValidationReason.EXPIRED,
        "company_idp",
        "orders_api"
    );

    Counter counter = registry.find("security.token.validation")
        .tags(
            "token_format", "jwt",
            "outcome", "rejected",
            "reason", "expired",
            "issuer", "company_idp",
            "resource_server", "orders_api"
        )
        .counter();

    assertThat(counter).isNotNull();
    assertThat(counter.count()).isEqualTo(1.0);
}
```

Đây là ví dụ theo API Micrometer; cần điều chỉnh theo phiên bản và cách đặt tên metric trong dự án. Nên có test tương tự cho ERROR và authorization denial, đồng thời xác nhận không có tag động.

## 12. Bảo vệ metrics endpoint

Metrics endpoint có thể tiết lộ topology, issuer alias, traffic, trạng thái dependency và mẫu hoạt động bảo mật. Không để endpoint quản trị này công khai chỉ vì nó không trả token.

Thực hành:

- Chỉ Prometheus/collector hoặc hệ thống monitoring được phép truy cập endpoint metrics.
- Dùng mạng nội bộ, authentication và TLS/mTLS khi phù hợp.
- Không expose claims, token raw, user/tenant identifier hoặc exception chi tiết trong metric.
- Tách metrics vận hành khỏi audit logs có dữ liệu nhạy cảm.
- Giới hạn label/cardinality và bảo vệ dashboard/query access.
- Theo dõi chính exporter/collector để phát hiện scrape failure, dropped samples và ingestion lag.
- Không để metrics instrumentation làm chậm đường xác minh token; dùng registry và label set có giới hạn.

Metrics có thể giúp phát hiện hành vi tấn công nhưng không thay thế audit log, SIEM hay trace. Counter tổng hợp không đủ để điều tra một request cụ thể; log/audit cần correlation ID và chính sách bảo vệ riêng.

## 13. Lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Gộp invalid token và introspection timeout | Che giấu lỗi AS, làm sai rejection rate | Tách rejected và error |
| Đếm thiếu scope là validation failure | Không phân biệt authn/authz | Metric authorization riêng |
| Dùng HTTP 401/403 làm reason duy nhất | Không biết nguyên nhân cụ thể | Reason enum nội bộ |
| Label bằng raw sub, jti, token | Cardinality cực lớn và rò dữ liệu | Không dùng identifier theo request làm tag |
| Label bằng exception message | Mỗi message tạo time series mới | Map exception sang enum |
| Đếm validation ở nhiều filter | Counter tăng gấp đôi | Chọn một instrumentation boundary |
| Chỉ ghi metric success | Failure/timeout không được quan sát | Ghi accepted/rejected/error và duration cho mọi attempt |
| Chỉ đo tỷ lệ success | Có thể che giấu fail-open hoặc tấn công | Dashboard nhiều outcome, negative test |
| Cache hit bị tính là introspection request | Đánh giá sai tải AS | Metric cache và AS request riêng |
| JWKS cache hit được xem là token valid | Bỏ qua claim validation | Tách cache key fetch với validation result |
| Ghi token vào log khi lỗi | Token có thể bị replay | Redaction và reason code |
| Không giới hạn label tenant/path | Prometheus quá tải | Alias/route catalog hữu hạn |
| Alert theo số lỗi tuyệt đối | False positive khi traffic tăng | Dùng rate/ratio, baseline và minimum traffic |
| Không test metric khi exception | Thiếu dữ liệu đúng lúc sự cố | Timer/counter trong finally hoặc wrapper an toàn |

## 14. Checklist triển khai

- **Metric contract:** định nghĩa validation attempt, outcome, reason, latency và điểm ghi nhận.
- **Tách lớp:** parse, token validation, dependency, authorization và HTTP response có metrics riêng.
- **JWT:** theo dõi signature/issuer/audience/time/claim failure, unknown kid và JWKS refresh.
- **Opaque:** theo dõi active/inactive, introspection latency/timeout và cache freshness.
- **Labels:** chỉ dùng enum, issuer alias, resource server và action catalog; không có token, subject, tenant ID tùy ý hoặc URL động.
- **Latency:** ghi histogram cho accepted/rejected/error, phân biệt JWT và opaque.
- **Dashboard:** volume, outcome, reason, latency, dependency health, authorization deny và HTTP result.
- **Alert:** dùng rate/ratio, baseline, thời gian và minimum traffic; rejected không bị coi là availability error.
- **Instrumentation tests:** xác nhận mỗi attempt chỉ ghi một lần, reason đúng, cache hit không giả thành AS call và không có secret trong telemetry.
- **Metrics endpoint:** hạn chế truy cập, TLS/auth phù hợp, cardinality được kiểm soát.
- **Incident response:** kết hợp metric với log/audit/trace đã redaction; không dựa vào metric để truy tìm token cụ thể.

### Bài tập suy luận

Trong 5 phút, orders-api ghi nhận:

| Outcome/reason | Số lần |
|---|---:|
| accepted | 9.000 |
| rejected/expired | 500 |
| rejected/audience_mismatch | 300 |
| error/introspection_timeout | 200 |

**Câu hỏi 1:** Tỷ lệ rejected trên các lần validation đã có kết quả là bao nhiêu?

**Đáp:** Có 9.800 lần đã có kết quả (accepted + rejected), trong đó 800 lần bị từ chối. Tỷ lệ là khoảng **8,16%**. Hai trăm timeout không được đưa vào mẫu số này vì chưa xác định token hợp lệ hay không.

**Câu hỏi 2:** Có thể kết luận 8,16% là lỗi hệ thống không?

**Đáp:** Không. expired có thể là client dùng token cũ; audience_mismatch có thể là cấu hình client sai hoặc hành vi dò quét. Phải phân tích reason và đối chiếu release/traffic.

**Câu hỏi 3:** Hai trăm timeout nên được theo dõi ở đâu?

**Đáp:** outcome=error, reason=introspection_timeout, cùng latency/error rate của AS. Đây là tín hiệu availability/dependency, không phải token invalid.

**Câu hỏi 4:** Nếu token hợp lệ nhưng thiếu orders:write, ghi metric nào?

**Đáp:** Validation accepted; authorization deny/insufficient_scope. Cách ghi này giữ đúng ranh giới xác thực và phân quyền.

**Nguyên tắc cốt lõi:** *Metric tốt cho biết validator đã chấp nhận, từ chối hay không thể hoàn tất; nó không làm lộ token và không đánh đồng token sai với hệ thống xác minh đang lỗi.* Khi outcome, reason, latency và labels được định nghĩa nhất quán, đội vận hành có thể phát hiện sự cố mà vẫn giữ được ranh giới bảo mật.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [Prometheus — Metric types](https://prometheus.io/docs/concepts/metric_types/)
- [Prometheus — Instrumentation practices](https://prometheus.io/docs/practices/instrumentation/)
- [Micrometer — Timers and counters](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
