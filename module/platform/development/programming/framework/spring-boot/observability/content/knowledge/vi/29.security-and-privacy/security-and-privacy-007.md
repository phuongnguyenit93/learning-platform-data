# PII trong tags

Một ứng dụng Spring Boot ghi metric cho endpoint tìm kiếm khách hàng. Để debug, developer thêm email, customer ID và số điện thoại vào metric tags. Dashboard ban đầu rất tiện vì có thể lọc request của một người cụ thể. Nhưng mỗi giá trị tạo thêm time series, dữ liệu cá nhân lan sang metrics backend, dashboard, alert, bản sao lưu và hệ thống export. Khi telemetry được lưu lâu hoặc chia sẻ cho nhiều nhóm, phạm vi truy cập dữ liệu vượt xa mục đích debug ban đầu.

Bài **PII trong tags** thuộc chương **Security và privacy** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Nguyên tắc:** Không đưa PII trực tiếp vào metric tags hoặc thuộc tính telemetry có khả năng được export rộng rãi. Metrics cần dimensions hữu hạn, ổn định và không định danh cá nhân. Nếu cần điều tra một người dùng hoặc request cụ thể, dùng correlation ID ngẫu nhiên có kiểm soát trong logs/traces với access policy, retention và redaction phù hợp. Hashing không tự động biến dữ liệu cá nhân thành dữ liệu vô danh.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích PII và vì sao telemetry có thể làm lộ dữ liệu cá nhân.
2. Nhận diện direct identifiers và quasi-identifiers trong tags, logs, traces và baggage.
3. Hiểu cardinality, chi phí và rủi ro khi đưa user-specific values vào metric labels.
4. Thiết kế low-cardinality dimensions thay cho email, phone, customer ID và IP.
5. Phân biệt anonymization, pseudonymization, masking, hashing và redaction.
6. Giảm thiểu dữ liệu tại instrumentation/source trước khi export.
7. Dùng allowlist và normalization cho metric tags.
8. Cấu hình redaction/filtering cho logs, traces và Collector pipelines.
9. Quản lý access, retention, sampling và data governance cho telemetry.
10. Kiểm thử để bảo đảm PII không xuất hiện trong exported signals.

## 2. PII là gì trong observability?

PII (personally identifiable information) là thông tin có thể nhận diện một cá nhân trực tiếp hoặc khi kết hợp với dữ liệu khác. Phạm vi định nghĩa pháp lý thay đổi theo jurisdiction và ngữ cảnh xử lý; khi xây policy cần theo luật áp dụng và privacy/legal team của tổ chức.

Ví dụ dữ liệu có thể là PII hoặc dữ liệu nhạy cảm:
- Họ tên, email, số điện thoại.
- Địa chỉ nhà, ngày sinh.
- Số giấy tờ định danh, tài khoản ngân hàng.
- Customer/user ID nếu liên kết được với một người.
- IP address, device identifier hoặc location data trong nhiều bối cảnh.
- Session ID, access token, cookie hoặc credential có thể cho phép truy cập tài khoản.
- Nội dung request/response chứa thông tin cá nhân.

Một giá trị không phải tên hoặc email vẫn có thể nhận diện người khi kết hợp với dữ liệu khác. Timestamp chính xác, IP, region nhỏ và product choice có thể tạo quasi-identifier. Phân loại theo data inventory, purpose, khả năng liên kết và chính sách tổ chức.

## 3. PII có thể xuất hiện ở đâu trong telemetry?

Telemetry gồm metrics, traces, logs và resource/context attributes. PII có thể lọt vào nhiều điểm:

| Signal/location | Ví dụ rủi ro | Tác động |
|---|---|---|
| Metric tags | user.id, email, phone | Cardinality tăng, dữ liệu lan rộng |
| Span attributes | customer.email, request.body | Trace backend lưu nội dung cá nhân |
| Span name | GET /users/alice@example.com | PII xuất hiện trong index/name |
| Events/exceptions | Exception message chứa SQL/input | Nội dung nhạy cảm được export |
| Logs/MDC | Request payload, authorization header | Log search dễ truy vấn dữ liệu cá nhân |
| Baggage | customer.email propagate qua services | PII nhân bản qua network boundary |
| Resource attributes | Tenant/user-specific values | Gắn PII vào telemetry của process |
| Exemplars/correlation | Context liên kết identity | Có thể nối metric với dữ liệu định danh |

Kiểm tra cả instrumentation tự động. HTTP instrumentation có thể ghi route template an toàn hơn raw URL, nhưng high-cardinality URL/query attributes hoặc header capture có thể chứa dữ liệu nhạy cảm nếu cấu hình không phù hợp.

## 4. Vì sao PII trong metric tags đặc biệt nguy hiểm?

Metric tags xác định từng meter time series. Nếu thêm user ID hoặc email, mỗi người dùng có thể tạo một hoặc nhiều series.

Ví dụ không an toàn:

~~~java
Counter.builder("app.login.attempts")
        .tag("email", userEmail)
        .tag("customer.id", customerId)
        .register(meterRegistry)
        .increment();
~~~

Giả sử có 100.000 người dùng và mỗi người có vài tag combinations. Số series có thể tăng theo lượng người dùng thay vì theo vài nhóm nghiệp vụ. Hậu quả:
- Registry/backend sử dụng nhiều RAM, storage và index.
- Scrape/ingestion/query chậm và tốn chi phí.
- Dashboard/alert khó tổng hợp.
- Dữ liệu cá nhân được sao chép tới nhiều hệ thống telemetry.
- Khó đáp ứng yêu cầu retention, deletion, access và audit.

Metric tags nên mô tả nhóm có số lượng giá trị hữu hạn, ví dụ operation, outcome, channel, region tổng quát và error.type.

## 5. Thiết kế dimensions an toàn

Thay giá trị cá nhân bằng dimension có ý nghĩa vận hành nhưng bounded:

| Không an toàn | Thay thế phù hợp hơn |
|---|---|
| email=user@example.com | auth.method=password |
| customer.id=83921 | customer.segment=standard |
| phone=+84... | verification.channel=sms |
| raw IP address | network.class=public/private hoặc region tổng quát |
| order.id=... | operation=order.create |
| raw URL có user ID | route=/users/{userId} |
| exception.message | error.type=validation/timeout/constraint |
| raw tenant ID | tenant.tier=free/business/enterprise nếu policy cho phép |

Các thay thế chỉ an toàn nếu giá trị thực sự bounded và không tái nhận diện cá nhân trong bối cảnh cụ thể. Region quá nhỏ, segment quá chi tiết hoặc tenant tier có quá ít thành viên vẫn có thể tạo privacy risk.

### 5.1 Allowlist và normalization

Không gắn trực tiếp input vào tag. Chuẩn hóa về một tập cho phép:

~~~java
enum LoginMethod {
    PASSWORD,
    OIDC,
    SAML,
    UNKNOWN
}

LoginMethod normalizeMethod(String raw) {
    if (raw == null) {
        return LoginMethod.UNKNOWN;
    }
    return switch (raw.toLowerCase(Locale.ROOT)) {
        case "password" -> LoginMethod.PASSWORD;
        case "oidc" -> LoginMethod.OIDC;
        case "saml" -> LoginMethod.SAML;
        default -> LoginMethod.UNKNOWN;
    };
}
~~~

Dùng giá trị enum đã chuẩn hóa:

~~~java
Counter.builder("app.login.attempts")
        .tag("method", normalizeMethod(method).name().toLowerCase(Locale.ROOT))
        .register(meterRegistry)
        .increment();
~~~

Allowlist giúp cardinality bounded và ngăn input tùy ý đi thẳng vào telemetry. Nó không thay thế data classification; một giá trị trong allowlist vẫn có thể nhạy cảm nếu tiết lộ thuộc tính cá nhân.

## 6. Metrics, traces và logs có mục đích khác nhau

Không cố giải quyết mọi nhu cầu bằng cách đưa cùng một trường vào mọi signal:

| Signal | Dùng cho | Nguyên tắc dữ liệu |
|---|---|---|
| Metrics | Xu hướng tổng hợp, SLO, alert | Dimensions bounded, không PII |
| Traces | Luồng request/dependency và latency | Attributes tối thiểu, tránh payload/identity |
| Logs | Chi tiết sự kiện và chẩn đoán | Structured fields, redaction, access/retention |
| Baggage | Propagate context giữa services | Chỉ key/value cần thiết, không secrets/PII |
| Resource attributes | Metadata service/process/deployment | Metadata ổn định, không user/request data |

Nếu cần tìm một request cụ thể, dùng trace ID hoặc correlation ID ngẫu nhiên. ID này vẫn có thể là dữ liệu cá nhân dạng pseudonymous nếu có thể liên kết ngược với user, nên cần access controls và retention phù hợp. Không biến nó thành metric tag.

## 7. Hashing không đồng nghĩa anonymization

Hash email hoặc customer ID không tự động làm dữ liệu vô danh.

Rủi ro:
- Email/phone có không gian giá trị dễ đoán; attacker có thể dictionary-attack hash.
- Hash không salt hoặc dùng salt chung có thể liên kết cùng một người giữa systems.
- Stable hash cho phép theo dõi hành vi một cá nhân qua thời gian.
- Hash value vẫn có cardinality gần như theo số người dùng.
- Nếu tổ chức giữ mapping hoặc có thể tái liên kết, dữ liệu thường vẫn là pseudonymous.

Ví dụ không nên làm:

~~~java
String tag = sha256(userEmail);
counter.tag("user", tag);
~~~

Cách này vẫn tạo series theo user và tạo khả năng liên kết lâu dài. Nếu business cần cohort analysis, ưu tiên aggregate theo segment đủ lớn hoặc privacy-preserving analytics được privacy team phê duyệt. Không tự thiết kế hashing scheme cho metric tags để né data policy.

## 8. Redaction, masking, pseudonymization và anonymization

| Kỹ thuật | Ý nghĩa | Lưu ý |
|---|---|---|
| Redaction | Loại bỏ trường/dữ liệu khỏi telemetry | Ưu tiên khi không cần dữ liệu |
| Masking | Thay một phần giá trị bằng ký tự che | Phần còn lại vẫn có thể nhận diện |
| Pseudonymization | Thay identifier bằng token/mã khác, có thể liên kết qua mapping/key | Vẫn cần bảo vệ khi có thể tái liên kết |
| Anonymization | Biến đổi để cá nhân không còn nhận diện được hợp lý | Khó đạt, phải đánh giá re-identification risk |
| Aggregation | Gộp dữ liệu thành nhóm/tổng hợp | Nhóm nhỏ vẫn có thể tiết lộ cá nhân |

Email masking a***@example.com vẫn có thể nhận diện nếu domain hoặc prefix đặc biệt. Chỉ ghi bốn số cuối của tài khoản cũng có thể đủ để liên kết với dữ liệu khác. Hãy loại bỏ trường nếu không có mục đích vận hành rõ ràng.

## 9. Giảm thiểu PII tại source

Redaction tốt nhất diễn ra trước khi dữ liệu đi vào telemetry pipeline:
- Không tạo metric tag từ raw request parameter.
- Không ghi request/response body vào span mặc định.
- Không capture Authorization, Cookie, Set-Cookie hoặc token headers.
- Dùng route templates thay raw paths.
- Chuẩn hóa error.type thay exception message.
- Chỉ thêm baggage fields cần thiết.
- Giữ Resource attributes ở cấp service/deployment, không gắn user context.
- Dùng structured logging với field allowlist.

Ví dụ structured log an toàn hơn:

~~~java
log.info("Login attempt method={} outcome={}",
        normalizedMethod,
        "rejected");
~~~

Tránh:

~~~java
log.info("Login failed email={} password={} body={}",
        email, password, requestBody);
~~~

Không dựa hoàn toàn vào downstream redaction để sửa instrumentation thiếu an toàn. Source minimization giảm nguy cơ dữ liệu nhạy cảm lọt vào buffer, local files, network và exporter khác.

## 10. Redaction cho traces và OpenTelemetry Collector

OpenTelemetry Collector có processors để filter hoặc transform telemetry trước khi export tới backend. Ví dụ có thể xóa attribute nhạy cảm hoặc lọc span/log records theo policy. Cấu hình cụ thể phụ thuộc Collector distribution và phiên bản processor.

Ví dụ minh họa dùng attributes processor:

~~~yaml
processors:
  attributes/remove-sensitive:
    actions:
      - key: user.email
        action: delete
      - key: user.phone
        action: delete
      - key: http.request.header.authorization
        action: delete

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [attributes/remove-sensitive, batch]
      exporters: [otlp]
~~~

Đây là cấu hình minh họa; kiểm tra processor type, attribute names và pipeline schema của Collector version đang triển khai. Processor traces-only không tự động xóa dữ liệu trong metrics/logs pipelines. Phải áp dụng policy cho từng signal và từng pipeline.

Nếu attribute đã được gửi tới Collector, nó đã đi qua network boundary và có thể xuất hiện trong Collector memory/diagnostics. Redaction ở Collector là defense-in-depth; loại bỏ ở source vẫn quan trọng.

## 11. Bảo vệ baggage và context propagation

Baggage được propagate qua service boundaries. Một key được thêm vào baggage có thể lan tới nhiều downstream services và telemetry systems. Không đưa email, phone, customer ID, account number, token hoặc raw session identifiers vào baggage chỉ để tiện tìm kiếm.

Ưu tiên trace ID/span ID do tracing system tạo, correlation ID ngẫu nhiên không mã hóa identity, business category bounded như operation type và tenant tier tổng quát nếu thực sự cần và đã được đánh giá privacy.

Giới hạn propagation fields và header size. Kiểm tra proxy/gateway không forward baggage không cần thiết tới external services. Không giả định baggage được bảo mật chỉ vì nó là metadata tracing.

## 12. Retention, access và data governance

Telemetry backend có thể lưu dữ liệu lâu hơn log ứng dụng, replicate sang nhiều region và cho nhiều nhóm truy cập. Policy cần định nghĩa:
- Mục đích thu thập cho từng signal.
- Field allowlist và data classification.
- Ai có quyền query raw traces/logs.
- Retention theo signal/environment.
- Cách xử lý export, backup, archive và deletion requests.
- Audit trail cho truy cập dữ liệu nhạy cảm.
- Quy trình incident khi PII đã được export.
- Vendor/region/data residency requirements theo luật áp dụng.

Sampling giảm lượng trace được lưu nhưng không phải privacy control: một trace chứa PII vẫn có thể được sample và export. Redaction phải chạy trước sampling/export theo pipeline policy phù hợp.

## 13. Kiểm thử PII không lọt vào telemetry

Xây test bằng synthetic canary values, không dùng dữ liệu khách hàng thật. Ví dụ:

~~~text
PII_CANARY_EMAIL=privacy-canary-482@example.invalid
PII_CANARY_TOKEN=CANARY_SECRET_DO_NOT_EXPORT_7b31
PII_CANARY_PHONE=+840000000000
~~~

Gửi request chứa canary qua code paths quan trọng, thu telemetry test từ:
- Micrometer MeterRegistry.
- Observation handlers.
- Tracing exporter/test span reporter.
- Logging appender hoặc test log sink.
- Collector output nếu pipeline test có.

Assert canary không xuất hiện trong metric names/tags, span names/attributes/events, baggage, log fields hoặc exported payload. Cũng kiểm tra exception, invalid input, timeout và retry paths.

### 13.1 Kiểm tra cardinality

Gửi nhiều requests với email/customer IDs khác nhau nhưng cùng channel/operation category. Xác nhận meter ID count không tăng theo số user, tag values chỉ nằm trong allowlist, không có raw URL/query/body trong span attributes và logs chỉ có fields đã phê duyệt.

Không chỉ grep một log line; PII có thể nằm trong exception cause, nested attributes hoặc resource metadata.

## 14. Incident response khi PII đã bị export

Nếu phát hiện PII trong metrics/traces/logs:
1. Xác định field, signal, service, thời gian và backend nhận dữ liệu.
2. Ngăn dữ liệu mới tiếp tục đi vào bằng source fix hoặc pipeline filter.
3. Xác định phạm vi retention, replicas, exports, backups và người có quyền truy cập.
4. Thông báo privacy/security owner theo incident process của tổ chức.
5. Đánh giá nghĩa vụ thông báo theo luật/chính sách áp dụng.
6. Xóa hoặc hạn chế dữ liệu theo khả năng backend và retention policy đã phê duyệt.
7. Rotate/revoke credentials nếu secret/token cũng bị lộ.
8. Kiểm tra dashboard, alerts, exemplars và downstream copies.
9. Thêm regression tests với canary values.
10. Ghi lại root cause và thay đổi instrumentation/policy để ngăn tái diễn.

Không giả định xóa một series khỏi dashboard đồng nghĩa dữ liệu đã bị xóa khỏi storage, replicas hoặc backups.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Metric series tăng theo user count | User ID/email làm tag | Bỏ tag cá nhân, dùng bounded segment |
| Trace backend tìm kiếm được email | HTTP/body/header capture hoặc custom attribute | Redact tại source và Collector |
| PII xuất hiện trong logs dù app logger không ghi | Exception message, access log hoặc agent instrumentation | Kiểm tra appenders/agents và exception chain |
| Hash user ID vẫn cardinality cao | Hash vẫn duy nhất theo user | Bỏ identifier khỏi metric dimensions |
| PII lan tới downstream services | Baggage/header propagation | Xóa key và allowlist propagation |
| Collector redaction không hiệu lực | Processor không nằm trong pipeline signal hoặc sai key | Kiểm tra traces/metrics/logs pipelines |
| PII chỉ xuất hiện khi lỗi | Exception message/cause chứa request data | Chuẩn hóa error.type và scrub exception output |
| Resource attribute chứa tenant | Resource tạo từ request context | Chỉ dùng service/process metadata ổn định |
| Không thể xóa dữ liệu khỏi backend | Retention/replication/backup behavior | Theo incident process và backend deletion capabilities |
| Canary test pass nhưng production vẫn lộ | Test thiếu code path/agent/exporter thực tế | Test end-to-end theo production-like pipeline |

## 16. Playbook: loại PII khỏi metric tags

**Tình huống:** Metric login attempts đang có tag email và số series tăng theo lượng người dùng.

1. Xác định meter name, tag keys và nơi tạo meter.
2. Dừng tạo tag từ email/phone/customer ID tại source.
3. Thay bằng dimensions bounded như auth.method, outcome và channel đã allowlist.
4. Kiểm tra instrumentation tự động có capture HTTP headers, query parameters hoặc user context không.
5. Xác định metric backend đã lưu series cũ và retention/deletion policy.
6. Triển khai source fix và Collector filter phù hợp cho traces/logs nếu cần.
7. Gửi synthetic canary values qua login success/failure paths.
8. Xác nhận canary không xuất hiện trong metrics, traces, logs hoặc baggage.
9. Theo dõi series count/cardinality và error rate sau deploy.
10. Thực hiện incident/privacy review nếu dữ liệu thật đã được export.

Đừng chỉ đổi dashboard query để ẩn tag. Cần ngăn dữ liệu mới được ghi và đánh giá bản sao đã lưu.

## 17. Bài tập tự kiểm tra

**Bài 1 — Cardinality.** Vì sao tag customer.id làm tăng series và chi phí backend ngay cả khi ID đã hash?

**Bài 2 — Pseudonymization.** Hash email có làm dữ liệu hoàn toàn anonymous không? Nêu ít nhất hai lý do.

**Bài 3 — Dimension design.** Thay email trong login metric bằng những dimensions nào có ích mà bounded?

**Bài 4 — Signal choice.** Khi cần tìm request cụ thể, vì sao trace ID/correlation ID trong logs/traces phù hợp hơn metric tag?

**Bài 5 — Baggage.** Vì sao customer email trong baggage nguy hiểm hơn một custom log field cục bộ?

**Bài 6 — Collector.** Tại sao xóa attribute ở traces pipeline không bảo đảm metrics và logs cũng đã được redacted?

**Bài 7 — Sampling.** Sampling có thay thế redaction không? Giải thích.

**Bài 8 — Incident.** PII đã xuất hiện trong backend telemetry và được replicate. Nêu các bước containment, assessment và remediation.

### Gợi ý trả lời

1. Mỗi ID tạo một tag combination/series; hash không làm giảm số giá trị duy nhất.
2. Email dễ dictionary attack; stable hash cho phép liên kết cùng người; mapping/key có thể tái liên kết.
3. auth.method, outcome, channel hoặc user.segment có tập giá trị allowlist và đủ lớn để tránh tái nhận diện.
4. Trace/correlation ID hỗ trợ điều tra một event mà không tạo time series riêng cho từng request/user.
5. Baggage có thể propagate qua nhiều process và boundary, nhân bản dữ liệu sang downstream systems.
6. Collector có pipeline riêng cho traces, metrics và logs; processor phải được áp dụng đúng signal.
7. Không. Sample chỉ giảm số records; record được chọn vẫn có thể chứa PII.
8. Chặn ingest mới, xác định phạm vi/backend/replicas/backup/access, thông báo owner, đánh giá nghĩa vụ, xóa/hạn chế theo policy, regression tests và ghi nhận root cause.

## 18. Tài liệu tham khảo chính thức

- [OpenTelemetry — Sensitive Data](https://opentelemetry.io/docs/security/handling-sensitive-data/): nhận diện và xử lý dữ liệu nhạy cảm trong telemetry.
- [OpenTelemetry Collector — Transform Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/transformprocessor): filter/transform attributes và telemetry data.
- [OpenTelemetry Collector — Attributes Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/attributesprocessor): insert, update, hash hoặc delete attributes theo policy.
- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/): chuẩn hóa attribute names và signal conventions.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation context, handlers và conventions.
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): giới hạn/chuẩn hóa meter IDs và tags.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing propagation, baggage và span configuration.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging configuration và structured logging.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu cần loại trừ, bảo vệ và quản lý logs.
- [NIST Privacy Framework](https://www.nist.gov/privacy-framework): quản trị privacy risk và data processing lifecycle.

**Ghi nhớ:** Telemetry có thể sao chép dữ liệu cá nhân qua metrics backend, trace storage, log index, Collector và backup. Giữ metric tags bounded và không định danh; giảm thiểu dữ liệu tại source; allowlist fields; redaction theo từng signal; bảo vệ baggage, access và retention. Hash không tự động anonymize và cũng không giải quyết cardinality. Dùng synthetic canary tests để kiểm tra toàn pipeline, và xử lý PII đã export như một incident có phạm vi lưu trữ/replication cụ thể.

