# Không export secret trong telemetry

Một request thanh toán đi qua API Gateway, Order Service và Payment Service. Khi điều tra lỗi, ứng dụng ghi toàn bộ request headers, query parameters và exception message vào span attributes hoặc logs. Một header Authorization, cookie phiên đăng nhập hoặc access token bất ngờ xuất hiện trong OTLP payload. Khi exporter gửi telemetry tới Collector và backend, secret đã rời khỏi process ứng dụng và có thể được lưu ở nhiều hệ thống, bản sao lưu hoặc vùng lưu trữ khác nhau.

Bài **Không export secret trong telemetry** thuộc chương **OTLP export** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Nguyên tắc cốt lõi:** Phòng ngừa phải bắt đầu tại nơi telemetry được tạo: không thu thập secret vào span, metric, log, event, baggage hoặc Resource. Collector processors là lớp phòng thủ bổ sung để xóa/lọc dữ liệu trước khi export tiếp, không phải lý do để ứng dụng gửi mọi thứ lên Collector. Phân biệt secret trong OTLP exporter headers/TLS credentials dùng xác thực đường truyền với secret trong telemetry payload là dữ liệu quan sát không được chứa credential.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Nhận diện secret có thể rò vào traces, metrics, logs, baggage, Resource attributes và exception events.
2. Phân biệt exporter authentication headers với telemetry attributes/body.
3. Thiết kế data minimization và allowlist ngay trong instrumentation Spring Boot.
4. Tránh log Authorization, Cookie, Set-Cookie, access token, password, API key, request body và dữ liệu thanh toán.
5. Quản lý OTLP endpoint credentials bằng secret management, environment injection và TLS/SSL bundle.
6. Cấu hình Collector attributes, filter, redaction và transform processors.
7. Hiểu giới hạn processor với log body, nested payload và exporter headers.
8. Kiểm tra traces, metrics và logs trước khi dữ liệu rời hệ thống.
9. Kiểm thử bằng canary secret giả và xác nhận nó không xuất hiện trong backend.
10. Lập quy trình phản ứng khi secret đã bị export nhầm.

## 2. Secret có thể xuất hiện ở đâu?

Telemetry không chỉ gồm span names và durations. Instrumentation có thể ghi attributes, events, exception messages, log body, baggage hoặc Resource attributes. Nếu code gắn trực tiếp input người dùng hoặc headers vào các trường này, OTLP exporter sẽ gửi chúng cùng dữ liệu quan sát.

| Thành phần | Ví dụ rủi ro | Vị trí có thể lộ |
|---|---|---|
| Span attributes | http.request.header.authorization, user.password, db.connection_string | Span/trace payload |
| Span events | Exception message chứa token hoặc SQL parameter | Event attributes |
| Span name | URL có query string chứa token/email | Span name |
| Baggage | access-token, session-id, email | Propagation headers và downstream telemetry |
| Logs | Authorization header, cookie, raw request body | Log body/attributes/MDC |
| Metrics | user_id/order_id/token làm tag | Metric labels/data points |
| Resource attributes | process.command_line chứa credential | Resource gắn với nhiều telemetry |
| Exception | Message hoặc stack metadata chứa dữ liệu nhạy cảm | Logs/traces |
| OTLP exporter headers | api-key, Authorization: Bearer ... | HTTP/gRPC metadata tới Collector/backend |

Secret không chỉ là password. Cần xem xét access/refresh token, API key, private key, session cookie, database password, signed URL, payment credentials, client secrets, webhook secrets và thông tin cá nhân có thể định danh hoặc truy cập tài khoản.

### 2.1 Ví dụ dữ liệu không được ghi

~~~http
Authorization: Bearer eyJhbGciOi...
Cookie: SESSION=abc123
X-Api-Key: sk_live_example
~~~

Không copy các giá trị này vào baggage, span attributes, log statements, MDC, metrics tags hoặc exception context. Nếu cần xác nhận authentication hoạt động, ghi kết quả đã chuẩn hóa (ví dụ authentication.outcome=success) thay vì credential.

### 2.2 Secret trong URL cũng là secret

Không ghi raw URL nếu query parameters có access_token, id_token, signed download URL, password reset token, email, số điện thoại hoặc dữ liệu tìm kiếm riêng tư. Ưu tiên route template như /orders/{orderId}, không phải URL đã resolve có giá trị thực. Nếu cần quan sát query parameter, chỉ ghi tên parameter hoặc giá trị đã được phân loại/ẩn danh đúng chính sách.

## 3. Phân biệt exporter credentials với telemetry payload

OTLP exporter gửi request tới Collector bằng HTTP hoặc gRPC. Để xác thực, exporter có thể đính kèm header, token, client certificate hoặc sử dụng TLS/mTLS. Đây là thông tin bảo vệ kênh vận chuyển, không phải metadata nghiệp vụ của trace.

~~~mermaid
flowchart LR
    A["Spring Boot application"] --> B["OTLP exporter"]
    B -->|"TLS/mTLS + auth header"| C["Collector receiver"]
    B -->|"Telemetry payload"| C
    C --> D["Processors: filter/redact"]
    D --> E["Backend exporter"]
    E --> F["Observability backend"]
~~~

| Dữ liệu | Ví dụ | Cách bảo vệ |
|---|---|---|
| Exporter credential | Authorization header, API key, client certificate | Secret manager, runtime injection, TLS/mTLS, least privilege |
| Telemetry content | Span attributes, log body, metric labels, Resource attributes | Data minimization, allowlist, redaction/filtering |
| Collector backend credential | Token gửi tới vendor backend | Secret management ở Collector |
| Trace context | Trace ID, Span ID, sampled flag | Propagation theo protocol; không phải secret xác thực |

Không đưa exporter token vào baggage hoặc span attribute để debug exporter. Header xác thực cũng không nên được ghi trong HTTP client wire logs hoặc debug logs. Collector cần tránh log header nhạy cảm theo cấu hình receiver/exporter và chính sách vận hành.

## 4. Data minimization: không thu thập thì không phải xóa

OpenTelemetry không thể tự xác định mọi trường nào nhạy cảm với nghiệp vụ. Người triển khai instrumentation phải quyết định dữ liệu nào cần quan sát và chịu trách nhiệm bảo vệ telemetry. Cách an toàn nhất thường là không thu thập dữ liệu nhạy cảm ngay từ đầu.

Checklist trước khi thêm attribute:
1. **Mục đích:** field này trả lời câu hỏi vận hành nào?
2. **Tính cần thiết:** có thể dùng trạng thái tổng hợp, enum hoặc route template thay dữ liệu thô không?
3. **Phạm vi:** signal nào thực sự cần field này?
4. **Nhạy cảm:** field có thể chứa credential, PII, tài chính hoặc dữ liệu pháp lý không?
5. **Cardinality:** giá trị có gần như duy nhất mỗi request không?
6. **Retention/access:** ai đọc backend, dữ liệu giữ bao lâu và ở region nào?
7. **Kiểm thử:** có test chứng minh secret không xuất hiện trong payload không?

| Thay vì ghi | Hãy cân nhắc |
|---|---|
| Authorization header | authentication.outcome=success/denied |
| Cookie/session token | session.present=true |
| Raw SQL có parameter | db.system.name, operation name, query template đã loại literals |
| Full URL/query string | http.route=/orders/{orderId} |
| Payment card number | payment.method=card, result=approved |
| Email khách hàng | customer.type=registered hoặc region hợp lệ |
| Exception message thô có token | exception.type và error.category đã chuẩn hóa |

Không hash dữ liệu nhạy cảm rồi mặc định xem nó là vô hại. Hash email/phone hoặc ID có miền giá trị nhỏ có thể bị dò ngược bằng từ điển; hashing cũng tạo giá trị ổn định cho phép liên kết hoạt động người dùng.

## 5. Tránh ghi secret tại Spring Boot instrumentation

### 5.1 Không log toàn bộ HTTP headers

Tránh:

~~~java
// KHÔNG LÀM: có thể ghi Authorization, Cookie, API key...
log.debug("Request headers: {}", request.getHeaders());
~~~

Thay bằng metadata đã allowlist:

~~~java
log.debug("Incoming request method={} route={} contentType={}",
        request.getMethod(),
        routeTemplate,
        safeContentType);
~~~

Nếu cần quan sát authentication, log kết quả đã chuẩn hóa, không ghi credential:

~~~java
log.info("Authentication completed outcome={} mechanism={}",
        "success",
        "oauth2");
~~~

Không ghi raw header map chỉ để biết request có được gửi đúng. Một số HTTP instrumentation tự capture headers theo cấu hình; kiểm tra allowlist của instrumentation library và tắt capture nhạy cảm.

### 5.2 Không đưa raw request/response body vào logs hoặc spans

~~~java
// KHÔNG LÀM
log.info("Payment request body={}", requestBody);
span.tag("payment.request", requestBody);
~~~

Payload thanh toán có thể chứa số thẻ, địa chỉ, token hoặc dữ liệu khách hàng. Thay bằng các trường an toàn:

~~~java
log.info("Payment request received method={} currency={} amountBand={}",
        paymentMethod,
        currency,
        amountBand);
~~~

Chỉ chọn amountBand nếu nghiệp vụ cho phép và dải giá trị không làm lộ dữ liệu nhạy cảm.

### 5.3 Sanitize exception messages

Exception có thể bao gồm URL có query token, connection string hoặc SQL chứa parameter. Không mặc định mọi exception message đều an toàn để log hoặc gắn vào span.

~~~java
try {
    paymentGateway.authorize(command);
} catch (PaymentGatewayException ex) {
    observation.error(ex);
    log.warn("Payment authorization failed type={} category={}",
            ex.getClass().getSimpleName(),
            "provider_error");
    throw ex;
}
~~~

Đoạn minh họa ghi loại exception và category. Cần kiểm tra handler mặc định vì tracing/logging instrumentation có thể tự thêm exception event hoặc message; sanitize ở nơi tạo dữ liệu và cấu hình handler phù hợp nếu exception có thể chứa secret.

## 6. Không đưa secret vào baggage, MDC, Resource hoặc metric tags

**Baggage** được propagate rộng qua nhiều service bằng W3C baggage header. Không đưa token, cookie, email hoặc raw user input vào baggage. Chỉ cho phép key cần thiết, ví dụ channel hoặc deployment cohort đã chuẩn hóa.

**MDC** xuất hiện trong log event khi encoder/pattern đọc key. Nếu đặt credential vào MDC, nhiều log statements trong cùng scope có thể vô tình ghi nó. MDC cũng cần cleanup/restore qua async boundaries để tránh rò context giữa worker tasks.

**Resource attributes** gắn với telemetry của service/instance, thường được lặp/nhóm qua nhiều spans, metrics và logs. Không đặt database URL có password, process command line chứa --password, cloud credential hoặc secret mount contents vào Resource.

**Metric tags** có thể nhân bản dữ liệu nhạy cảm và làm cardinality tăng nhanh. Không gắn user token, email, account ID hoặc payment reference vào tags. Dùng metric dimensions nhỏ và tổng hợp.

## 7. Quản lý OTLP exporter credentials

Spring Boot hiện hỗ trợ cấu hình endpoint, headers và compression cho OTLP exporters. Có thể cấu hình chung cho traces/logs/metrics hoặc riêng từng signal tùy phiên bản/property group. Header có thể chứa Authorization bearer token hoặc api-key.

Ví dụ cấu hình chung minh họa:

~~~yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://otel-collector.example.internal:4318
      compression: gzip
      headers:
        Authorization: <injected-secret>
~~~

Placeholder trên đại diện giá trị được inject từ secret management hoặc môi trường runtime; không viết token thật vào source control, Dockerfile, image layer, config map công khai hoặc file sample dùng chung. Cú pháp binding/injection cần theo phiên bản Spring Boot và platform.

Một số integration/phiên bản có cấu hình riêng cho từng exporter, ví dụ traces, logs hoặc Micrometer metrics. Đọc property reference của đúng Spring Boot version; không giả định management.opentelemetry.otlp.headers cấu hình mọi registry metrics ngoài Micrometer.

### 7.1 Dùng Secret Manager hoặc platform secret injection

Nguồn credential nên là hệ thống quản lý secret (Vault, cloud secret manager, Kubernetes Secret được bảo vệ, workload identity hoặc cơ chế tương đương).

- Inject khi runtime hoặc mount file/SSL bundle có quyền phù hợp.
- Chỉ service/instance cần gửi telemetry mới được đọc credential.
- Dùng token scope hẹp, chỉ cho phép ingest vào tenant/project cần thiết.
- Rotate định kỳ và khi nghi ngờ lộ.
- Không echo environment, in application config hoặc dump bean chứa header.
- Không để secret trong build logs, process command line hoặc diagnostics.
- Ưu tiên workload identity/mTLS khi hạ tầng hỗ trợ thay static long-lived API key.

Không phải môi trường nào cũng dùng cùng secret manager; chọn cơ chế phù hợp platform và kiểm tra nó không đưa credential vào log/metadata phụ.

### 7.2 TLS và mTLS

TLS bảo vệ kết nối và chống nghe lén/chỉnh sửa trên đường truyền. mTLS bổ sung xác thực client bằng certificate. TLS không ngăn secret đã nằm trong telemetry payload được Collector lưu lại; payload cần được làm sạch riêng.

Khi dùng private CA/client certificate, cấu hình SSL bundle hoặc truststore/keystore theo integration Spring Boot/OTLP exporter hiện hành. Không tắt certificate validation để sửa lỗi kết nối; xử lý CA chain và hostname verification đúng cách.

### 7.3 Header secret không thuộc Resource hay Baggage

Không tạo các thuộc tính sau:

~~~text
Resource:
  otlp.authorization = Bearer ...
  collector.api_key = ...

Baggage:
  exporter-token = ...

Span attributes:
  http.request.header.authorization = ...
~~~

Exporter dùng header ở transport layer; không copy nó thành attribute để debug. Nếu cần kiểm tra xác thực, ghi trạng thái kết nối hoặc mã lỗi chuẩn hóa mà không ghi credential.

## 8. Collector processors làm lớp phòng thủ bổ sung

OpenTelemetry Collector có processors xóa, cập nhật, lọc hoặc biến đổi telemetry trước khi gửi tới backend.

| Processor | Tác dụng | Khi dùng |
|---|---|---|
| attributes | Insert/update/delete/hash attributes của spans/logs/metrics | Xóa key cụ thể hoặc biến đổi metadata |
| filter | Drop spans, logs hoặc metric records/data points theo điều kiện | Loại bỏ record không được phép |
| redaction | Giữ allowlist attributes, xóa fields ngoài danh sách và mask giá trị bị chặn | Data minimization tập trung |
| transform | Sửa/đổi/xóa dữ liệu theo OTTL statements/regex | Chuẩn hóa hoặc scrub pattern phức tạp |

**Khai báo processor không tự kích hoạt processor.** Phải thêm nó vào service.pipelines tương ứng. Cần cấu hình từng pipeline traces, metrics và logs; processor chỉ thêm vào traces pipeline không tự bảo vệ log pipeline.

### 8.1 Xóa attributes bằng attributes processor

Ví dụ Collector Contrib:

~~~yaml
processors:
  attributes/drop-sensitive:
    actions:
      - key: user.password
        action: delete
      - key: http.request.header.authorization
        action: delete
      - key: session.id
        action: delete

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [attributes/drop-sensitive, batch]
      exporters: [otlp/backend]
    metrics:
      receivers: [otlp]
      processors: [attributes/drop-sensitive, batch]
      exporters: [otlp/backend]
    logs:
      receivers: [otlp]
      processors: [attributes/drop-sensitive, batch]
      exporters: [otlp/backend]
~~~

Ví dụ minh họa cấu hình processor Contrib và pipeline names; receiver/exporter identifiers phải được khai báo tương ứng trong config triển khai. Attributes processor chỉ tác động attributes trong context được hỗ trợ; **không mặc định xóa secret nhúng trong log body hoặc chuỗi message**. Kiểm tra cấu trúc thực tế của signal.

### 8.2 Redaction processor theo allowlist

Redaction processor có thể xóa attributes không nằm trong allowed list và mask giá trị nằm trong blocked values. Đây là cách tiếp cận allowlist: chỉ giữ keys thực sự cần thiết cho observability.

~~~yaml
processors:
  redaction/safe-fields:
    allow_all_keys: false
    allowed_keys:
      - http.request.method
      - http.route
      - http.response.status_code
      - service.name
      - deployment.environment.name
      - error.type
    blocked_values:
      - "Bearer .*"
      - ".*@.*"
~~~

Tên field và syntax phụ thuộc phiên bản/distribution Collector Contrib và processor stability. Ví dụ minh họa ý tưởng; xác minh schema của binary đang triển khai trước khi áp dụng. Allowlist quá chặt có thể xóa fields cần để điều tra; test trên dữ liệu đại diện.

### 8.3 Transform processor và log body

Transform processor sử dụng OpenTelemetry Transformation Language (OTTL) để đặt, sửa, xóa attributes hoặc log body trong những context được hỗ trợ. Ví dụ xóa key khỏi span:

~~~yaml
processors:
  transform/remove-secret:
    error_mode: ignore
    trace_statements:
      - context: span
        statements:
          - delete_key(attributes, "user.password")
          - delete_key(attributes, "http.request.header.authorization")
~~~

Log body có thể là string hoặc structured map; phải dùng OTTL context/statements phù hợp. Không dựa vào regex chung để nhận diện mọi token: format, encoding và nested objects thay đổi. Tốt nhất là không đưa secret vào body ban đầu.

### 8.4 Filter processor

Filter processor phù hợp khi cần drop cả record/span/metric theo điều kiện. Nhưng drop nguyên span có thể làm mất dữ liệu điều tra không nhạy cảm cùng secret. Ưu tiên xóa đúng attribute khi có thể; chỉ drop record khi không thể làm sạch an toàn hoặc policy yêu cầu.

## 9. Pipeline order và vùng bảo vệ

Collector processors chạy theo thứ tự trong pipeline. Một processor redaction đặt sau debug sink có thể quá muộn đối với nhánh nhận trước nó. Mọi output path phải đi qua lớp scrubber cần thiết trước khi rời trust boundary.

~~~mermaid
flowchart TD
    A["OTLP receiver"] --> B["Early validation / allowlist"]
    B --> C["Attributes / redaction / transform"]
    C --> D["Batch"]
    D --> E["Authorized backend exporter"]
    C --> F["Optional secondary exporter"]
    F --> G["Other approved destination"]
~~~

Kiểm tra:
- Có debug exporter hoặc logging exporter nhận payload trước redaction không?
- Có nhiều pipelines cùng dùng receiver nhưng chỉ một pipeline có scrubber không?
- Có connector/exporter bypass Collector gửi thẳng tới vendor không?
- Collector internal logs có vô tình ghi auth headers hoặc payload values không?
- Có retry queue hoặc file storage chứa payload chưa được scrub không?

Collector chỉ bảo vệ những đường đi qua Collector đó. Nếu application gửi telemetry thẳng tới vendor, cần bảo vệ tại ứng dụng và exporter path đó.

## 10. Giới hạn redaction

Redaction ở Collector là defense-in-depth, không phải giấy phép ghi dữ liệu nhạy cảm vào telemetry.

- Secret có thể nằm trong span.name, event name, log body, stack trace hoặc nested attributes, không chỉ attribute phẳng.
- Một processor có thể hỗ trợ traces nhưng không hỗ trợ cùng mức maturity cho logs/metrics; kiểm tra stability status của version triển khai.
- Regex không phát hiện mọi token encoding, base64, URL encoding, multiline hoặc custom formats.
- Value đã hash vẫn có thể liên kết lại cá nhân nếu miền đầu vào nhỏ hoặc có thể dò.
- Processor lỗi hoặc bị bỏ khỏi pipeline có thể khiến telemetry đi thẳng tới exporter.
- Collector không thể làm sạch dữ liệu đã được backend lưu trước đó.
- Khi fan-out nhiều exporters, đảm bảo tất cả nhánh tuân chính sách.

**Đừng coi “đã có Collector” là bằng chứng không có secret.** Cần test payload cuối cùng ở từng destination.

## 11. Kiểm soát span/log/metric instrumentation

### 11.1 HTTP header capture

Chỉ capture headers được allowlist, chẳng hạn một số header correlation không nhạy cảm đã chuẩn hóa. Loại bỏ tối thiểu Authorization, Cookie, Set-Cookie, proxy authorization, API key, custom secret headers và headers mang PII. Property và semantics capture khác nhau giữa instrumentation libraries; kiểm tra từng instrumenter.

### 11.2 Database statements

Không ghi connection strings chứa password hoặc SQL có literal parameter nhạy cảm. Dùng db.system, db.operation.name, tên database được phép và statement template an toàn. Nếu query text được thu thập, xác định liệu parameter có bị inline hay không.

### 11.3 Exception và stack traces

Exception có thể chứa request URL, query token, username, connection string hoặc remote response body. Kiểm tra log message do ứng dụng tạo, exception event do tracing handler thêm, stack trace/suppressed exceptions và error response body được HTTP client instrumentation ghi. Cấu hình exception recording có chủ đích và sanitize message trước khi vào signal pipeline nếu cần.

### 11.4 Metrics không được mang secret

Metric tags thường tồn tại lâu trong time series backend và có index/cardinality cost. Không gắn secret hoặc user identifiers vào labels, kể cả khi có thể hash. Chỉ ghi outcome, route template, protocol, status code hoặc dimensions hữu hạn.

### 11.5 Resource và process metadata

Kiểm tra Resource attributes do auto-detection tạo ra, đặc biệt process.command_line, host identifiers, container labels và custom service metadata. Đừng inject secret qua command-line arguments vì có thể hiển thị trong process metadata hoặc diagnostics.

## 12. Kiểm thử không export secret

Một bài test bảo mật tốt không chỉ kiểm tra configuration; nó xác nhận secret giả không xuất hiện trong serialized telemetry sau cùng.

### 12.1 Canary secret giả

Tạo chuỗi test không có giá trị truy cập thực:

~~~text
FAKE_CANARY_SECRET_DO_NOT_EXPORT_9f23a7
~~~

Đưa canary vào Authorization header giả, cookie giả, query parameter giả, exception message và log body test. Sau khi gửi request, capture telemetry output bằng test exporter hoặc mock OTLP Collector và assert chuỗi canary không xuất hiện trong bất kỳ signal nào.

### 12.2 Kiểm tra serialized OTLP payload

Test nên kiểm tra:
1. Span attributes và events.
2. Resource attributes.
3. Metric attributes/labels.
4. Log body và log attributes.
5. Baggage propagation headers.
6. OTLP exporter headers trong test transport (chỉ dùng credential giả, không ghi ra output).

Không chỉ kiểm tra logger message; secret có thể được thêm tự động bởi instrumentation hoặc exception handler.

### 12.3 Test redaction processor

Gửi OTLP test records có secret fields vào Collector pipeline; xác nhận secret attribute bị xóa/mask, attributes không nhạy cảm vẫn tồn tại, processor được gắn trong mọi signal pipeline, secondary exporters chỉ nhận dữ liệu đã scrub. Kiểm tra riêng field lồng trong log body; không nhầm attributes đã xóa với log body đã scrub.

Dùng payload tổng hợp; không đưa dữ liệu thật của người dùng vào test logs.

### 12.4 Kiểm tra sau rollout

Sau deploy, tìm canary pattern ở backend logs/traces/metrics nếu test có gửi; kiểm tra Collector self-telemetry và exporter errors; xem traces/log records đại diện; xác nhận exporter credentials không xuất hiện trong debug logging. Lặp lại khi thêm instrumentation library hoặc nâng phiên bản Spring Boot/Micrometer/OTel agent.

## 13. Debug: secret đã xuất hiện trong backend

**Tình huống:** Backend trace có attribute http.request.header.authorization chứa bearer token.

1. **Ngăn rò thêm:** tắt instrumentation/capture path gây leak hoặc chặn export field/record tại ingress Collector.
2. **Xác định phạm vi:** traces, logs, metrics, baggage, Resource; service/version/instance; thời gian bắt đầu/kết thúc.
3. **Nguồn tạo:** code tự add attribute, HTTP agent capture, exception handler, log body hay Collector transform.
4. **Đường lan truyền:** service nào nhận/forward baggage; backend và exporter destination nào nhận.
5. **Credential response:** nếu secret thật bị lộ, revoke/rotate credential qua hệ thống sở hữu; không chỉ xóa field trong dashboard.
6. **Data retention:** theo incident/security policy để xóa hoặc hạn chế bản ghi/bản sao nếu có thể và được phép.
7. **Xác minh:** gửi canary test mới, kiểm tra từng destination và theo dõi không tái xuất hiện.
8. **Ngăn tái diễn:** thêm allowlist, instrumentation tests, Collector redaction và review khi dependency thay đổi.

Không paste secret thật vào ticket, Slack, chat hoặc báo cáo sự cố để chứng minh leak. Dùng tên field, vị trí, thời gian và canary/fingerprint đã được xử lý theo policy.

## 14. Bảng triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Authorization xuất hiện trong span | HTTP header capture hoặc custom tag | Tắt capture, allowlist headers, xóa tại source |
| Cookie xuất hiện ở logs | Request logging/filter ghi toàn header | Redact ở app logger, kiểm tra MDC/encoder |
| Token nằm trong exception | Exception message chứa URL/body/remote response | Sanitize message/exception event và xử lý nguồn |
| Secret nằm trong span name | URL/raw input được dùng làm name | Dùng route template và tên operation ổn định |
| Secret trong baggage downstream | Caller/service ghi credential vào baggage | Xóa field, allowlist baggage, kiểm tra propagation |
| Secret trong metric labels | Dynamic tag lấy từ input | Gỡ tag, đổi dimension hữu hạn, xem cardinality |
| Secret trong Resource | Environment/process metadata có credential | Sửa injection pattern, tạo Resource an toàn |
| Collector redaction không hoạt động | Processor chưa gắn vào pipeline | Kiểm tra service.pipelines cho traces/logs/metrics |
| Attribute đã xóa nhưng log body còn secret | Processor chỉ sửa attributes | Sanitize body ở source hoặc transform đúng context |
| Backend B vẫn nhận secret | Fan-out pipeline bypass scrubber | Đảm bảo mọi exporters nhận dữ liệu đã scrub |
| OTLP export bị 401 | Credential/headers không hợp lệ hoặc hết hạn | Kiểm tra secret injection, scope, rotation; không log token |
| TLS handshake lỗi | CA/certificate/hostname không khớp | Sửa trust chain/SSL bundle, không tắt verification |
| Canary không thấy ở Collector nhưng có ở backend | Có direct exporter hoặc pipeline khác | Kiểm tra mọi đường export và destination |
| Secret quay lại sau nâng cấp | Instrumentation mới thêm fields/headers | Regression canary tests và review semantic attributes |

## 15. Quy trình thiết kế an toàn cho OTLP export

Trước khi bật OTLP export cho production:

1. **Inventory signals:** liệt kê traces, metrics, logs và nơi chúng được tạo.
2. **Data classification:** đánh dấu secrets, PII, financial data và internal infrastructure details.
3. **Source allowlist:** chỉ ghi fields có mục đích, dùng route template và enums chuẩn hóa.
4. **Exporter auth:** cấp credential tối thiểu qua secret management; cấu hình TLS/mTLS.
5. **Collector pipeline:** gắn filter/redaction/attributes/transform processors vào từng pipeline.
6. **Access control:** giới hạn quyền đọc backend, tenant/project và retention.
7. **Canary test:** chứng minh fake secret không có trong serialized payload và backend.
8. **Review upgrades:** kiểm tra capture defaults khi nâng instrumentation, agent, Boot hoặc OTel SDK.
9. **Incident playbook:** biết cách ngăn export, rotate credential và xử lý telemetry đã lưu.

Không bật debug HTTP logging trên production nếu nó có thể in exporter headers hoặc request/response payload. Khi cần chẩn đoán, dùng synthetic credentials/traffic và tắt logging sau thử nghiệm.

## 16. Bài tập tự kiểm tra

**Bài 1 — Phân loại secret.** Một span có attributes Authorization, http.route và response status. Field nào được giữ, field nào phải loại? Giải thích.

**Bài 2 — Exporter header.** Ứng dụng dùng OTLP bearer token trong HTTP Authorization header để xác thực với Collector. Vì sao credential này không được thêm vào span attribute hoặc Resource?

**Bài 3 — Data minimization.** Exception message chứa signed URL. Hãy đề xuất cách ghi lỗi để vẫn điều tra được mà không ghi URL/token.

**Bài 4 — Collector processor.** Bạn khai báo attributes processor để xóa user.password nhưng backend vẫn nhận secret trong log body. Vì sao? Cần kiểm tra và xử lý ở đâu?

**Bài 5 — Pipeline coverage.** Collector có traces pipeline dùng redaction, nhưng logs và metrics pipeline không dùng processor. Điều gì có thể xảy ra? Làm thế nào bảo đảm tất cả destination được scrub?

**Bài 6 — Hashing.** Developer hash email rồi ghi vào baggage. Vì sao hash không tự động biến email thành dữ liệu vô danh? Khi nào nên bỏ hẳn field?

**Bài 7 — TLS.** OTLP exporter lỗi certificate verification. Vì sao tắt hostname verification không phải cách sửa đúng? Nêu bước kiểm tra CA và certificate.

**Bài 8 — Leak response.** Một access token thật đã xuất hiện trong traces backend. Nêu thứ tự hành động: ngăn export, rotate/revoke, xử lý dữ liệu lưu và regression testing.

### Gợi ý trả lời

1. Giữ route template và status code nếu cần; xóa Authorization. Không giữ raw header.
2. Header là thông tin xác thực transport; span/Resource có thể được lưu, tìm kiếm và forward rộng. Không copy credential vào telemetry.
3. Log exception type, error category, dependency và correlation ID; sanitize URL/message, không log raw signed URL.
4. Attributes processor chỉ sửa attributes; log body là vùng khác. Sanitize tại app hoặc transform log body với OTTL phù hợp; test payload cuối.
5. Logs/metrics vẫn có thể chuyển secret. Gắn processor vào mọi signal pipeline và mọi exporter branch.
6. Miền email dễ dò bằng dictionary và hash ổn định vẫn cho phép correlation; thường nên bỏ hoặc dùng dữ liệu phân loại không định danh.
7. Kiểm tra SAN/hostname, CA chain, truststore/SSL bundle, certificate expiry và endpoint; giữ verification bật.
8. Chặn đường phát sinh, revoke/rotate secret, xác định phạm vi, xử lý retention/copies theo incident policy, thêm canary tests và xác nhận không tái diễn.

## 17. Tài liệu tham khảo chính thức

- [OpenTelemetry — Handling Sensitive Data](https://opentelemetry.io/docs/security/handling-sensitive-data/): data minimization, sensitive attributes và Collector processors.
- [OpenTelemetry — Security Best Practices](https://opentelemetry.io/docs/security/config-best-practices/): bảo vệ Collector/export pipeline và cấu hình an toàn.
- [OpenTelemetry — Transforming Telemetry](https://opentelemetry.io/docs/collector/transforming-telemetry/): attributes, filter, redaction và transform processors.
- [OpenTelemetry Collector — Configuration](https://opentelemetry.io/docs/collector/configuration/): receivers, processors, exporters và service pipelines.
- [Collector Contrib — Attributes Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/attributesprocessor): insert/update/delete/hash attribute values.
- [Collector Contrib — Redaction Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/redactionprocessor): allowlist và blocked values cho telemetry attributes.
- [Collector Contrib — Transform Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/transformprocessor): OTTL transformation cho spans, logs và metrics.
- [OpenTelemetry — OTLP Exporter Configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/): endpoint, headers và transport configuration.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): OTLP endpoint, headers, compression và exporter properties.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): các property cấu hình OTLP hiện hành.

**Ghi nhớ:** Đừng export secret vào telemetry rồi hy vọng Collector sẽ luôn xóa đúng. Không thu thập credential ngay từ instrumentation; dùng allowlist cho span/log/metric/baggage/Resource; quản lý exporter auth bằng secret management và TLS; tiếp tục áp dụng redaction/filtering ở mọi Collector pipeline như lớp phòng thủ thứ hai. Kiểm thử bằng canary giả trên payload đã serialize và backend. Nếu secret thật đã bị export, revoke/rotate credential và xử lý dữ liệu đã lưu theo quy trình incident, vì xóa một attribute ở lần export tiếp theo không thu hồi các bản ghi cũ.

