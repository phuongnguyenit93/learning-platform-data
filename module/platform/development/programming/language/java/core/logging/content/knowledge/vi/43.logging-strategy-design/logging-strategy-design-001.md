# Xác định mục tiêu log trong Java: thiết kế chiến lược ghi log từ nhu cầu thực tế

## 1. Vì sao phải xác định mục tiêu trước khi viết log?

Trong Java, việc gọi `logger.info(...)` rất dễ. Nhưng có nhiều log **không đồng nghĩa hệ thống dễ vận hành hơn**. Khi production xảy ra lỗi, hàng triệu dòng `"starting..."`, `"processing..."` hay `"something failed"` không giúp trả lời các câu hỏi: người dùng nào bị ảnh hưởng, lỗi bắt đầu từ đâu, có cần can thiệp không, lỗi lặp lại trên bao nhiêu request và việc khắc phục đã có hiệu quả chưa.

**Xác định mục tiêu log** là bước đầu tiên trong **thiết kế chiến lược log**: làm rõ **vì sao** cần ghi một loại sự kiện, **ai** dùng dữ liệu đó, **quyết định/hành động nào** sẽ dựa vào nó, và **dấu hiệu kiểm chứng** cho thấy dữ liệu đã đủ, đúng và an toàn.

Mục tiêu không nên viết quá mơ hồ như:

> “Ghi càng nhiều thông tin càng tốt để debug.”

Một mục tiêu có thể kiểm chứng tốt hơn:

> “Khi thanh toán thất bại do hệ thống bên ngoài, on-call có thể tìm được `event=payment.failed`, biết loại lỗi chuẩn hóa, route/service/version bị ảnh hưởng, liên kết trace để điều tra và xác định có cần retry hay không; log không chứa thẻ thanh toán hoặc access token.”

Đối với một hệ thống Java Core Logging, chiến lược phải kết nối mục tiêu với **sự kiện**, **mức log**, **schema**, **vị trí ghi**, **kênh vận chuyển**, **quyền truy cập**, **retention** và **kiểm thử**. Đừng bắt đầu bằng việc chọn một Logback appender hoặc bật DEBUG toàn hệ thống rồi mới hỏi log được dùng vào việc gì.

### 1.1. Đầu ra mong muốn của bước xác định mục tiêu

Sau bước này, nhóm nên có ít nhất:
- Danh sách **các tình huống cần quan sát** và câu hỏi phải trả lời.
- Người sử dụng log và người chịu trách nhiệm **hành động khi sự kiện xuất hiện**.
- **Event catalog**: tên sự kiện chuẩn, điều kiện phát và ý nghĩa.
- **Field allowlist** cùng quy tắc phân loại dữ liệu, không log bí mật.
- Quy tắc **severity, frequency, sampling** và vị trí phát sự kiện.
- Sự phân biệt rõ giữa **application logs**, **metrics**, **traces** và **audit records**.
- Tiêu chí **QA/acceptance**: tìm được event ở đâu, trong khoảng thời gian nào, có đúng số lượng, đúng cấu trúc, không rò dữ liệu và không làm hỏng hiệu năng.

Không phải dự án nào cũng cần một tài liệu dài; service nhỏ có thể dùng một bảng sự kiện một trang. Quan trọng là quyết định được ghi **trước khi log lan ra nhiều lớp** và được cập nhật khi nghiệp vụ hoặc rủi ro thay đổi.

## 2. Phân loại mục tiêu: không phải mọi log có cùng nhiệm vụ

| Nhóm mục tiêu | Câu hỏi cần trả lời | Ví dụ sự kiện | Đối tượng sử dụng |
| --- | --- | --- | --- |
| **Vận hành** | Service có hoạt động, dependency nào lỗi? | `service.started`, `dependency.unavailable` | On-call, SRE |
| **Điều tra lỗi** | Request nào lỗi, ở bước nào, loại lỗi gì? | `order.create_failed` | Developer, support kỹ thuật |
| **Bảo mật** | Có truy cập bị từ chối hoặc hành vi nhạy cảm? | `auth.denied`, `permission.changed` | Security, SOC |
| **Audit nghiệp vụ** | Ai thực hiện thay đổi quan trọng, kết quả đã commit? | `payment.refunded`, `role.granted` | Audit, compliance, nghiệp vụ |
| **Hiệu năng** | Endpoint/dependency nào chậm? | `repository.slow_operation` | SRE, performance engineer |
| **Theo dõi luồng nghiệp vụ** | Đơn hàng đã qua các trạng thái nào? | `order.accepted`, `order.cancelled` | Product/operations |
| **Quản trị thay đổi** | Ai đổi cấu hình, release nào gây ảnh hưởng? | `logging.config_changed`, `release.deployed` | Platform, on-call |
| **Chất lượng tích hợp** | Provider có trả sai schema hoặc timeout không? | `partner.response_invalid` | Integration team |

Các nhóm có thể giao nhau nhưng **không nên gom thành một thứ**. Ví dụ application INFO về `"order created"` không tự thay thế audit trail có yêu cầu tính bền vững, chuỗi thời gian, quyền truy cập, khả năng chứng minh tính toàn vẹn.

OWASP Logging Cheat Sheet phân biệt các mục tiêu operational, security, audit và monitoring; mức chi tiết cần tương xứng với rủi ro và mục đích. Không có một checklist cố định phù hợp mọi loại hệ thống.

### 2.1. Vận hành: cần biết khi nào phải phản ứng

Mục tiêu vận hành tốt không chỉ là “log lỗi DB”, mà là:

- Khi dependency không khả dụng, biết `dependency`, `operation`, `error_type` và `trace_id`.
- Phân biệt outage diện rộng với một request riêng lẻ bằng **metrics** về error rate/timeout/pool saturation.
- Có runbook xác định ai nhận cảnh báo và hành động đầu tiên.

Ví dụ:

```text
ERROR event=dependency.unavailable service=orders
      dependency=inventory-api operation=reserve
      error_type=CONNECT_TIMEOUT request_id=req-104
```

Không cần in toàn bộ URL có token, HTTP Authorization header hay response body nhạy cảm. Event này nên có **định nghĩa rõ**: timeout sau bao lâu, event phát tại tầng nào và có log lặp cho từng retry không.

### 2.2. Điều tra lỗi: cần tìm nguyên nhân mà không log tràn lan

Một lỗi có thể đi từ repository lên service rồi tới HTTP handler. Nếu cả ba đều log stack trace, một failure có ba ERROR records mà không thêm context. Một quy tắc hữu ích là:
- Tầng dưới **ném/translate exception** và có thể thêm diagnostic riêng nếu thực sự có giá trị.
- Tầng sở hữu kết quả cuối (HTTP boundary, message consumer, scheduler) ghi **một event tổng kết** có error type và correlation ID.
- Trace/spans và metrics bổ trợ tìm nguyên nhân, không yêu cầu mọi method in INFO.

### 2.3. Bảo mật: hành vi nào phải quan sát?

Các sự kiện thường cần đánh giá:
- Authentication thành công/thất bại theo threat model; chú trọng các thất bại và mẫu bất thường.
- Authorization denial và privilege changes.
- Tạo/thu hồi credential, thay đổi cấu hình bảo mật.
- Sử dụng chức năng quản trị hoặc “break-glass” được kiểm soát.
- Truy cập/xuất dữ liệu nhạy cảm theo chính sách.
- Input validation thất bại, hành vi vi phạm luồng nghiệp vụ, rate-limit abuse.

**Không log password, OTP, access token, refresh token, session cookie, private key hoặc secret của API**. Security events có thể quan trọng ngay cả khi application log level được hạ; chiến lược phải quy định channel hoặc event classes không được tắt tùy tiện.

### 2.4. Audit: kết quả nghiệp vụ hay chỉ ý định?

`orderRepository.save(order)` đã return **không bảo đảm transaction đã commit**. Nếu audit phải chứng minh một thay đổi đã xảy ra, một dòng INFO trước commit không đủ. Có thể cần một audit store hoặc transactional outbox được lưu cùng transaction, kết hợp identity/authorization, retention và integrity controls.

Vì vậy, mục tiêu phải xác định rõ:

- Ghi **attempt** hay **committed outcome**?
- Cần truy nguyên actor và quyền tại thời điểm thao tác không?
- Ai được quyền đọc/sửa/xuất dữ liệu?
- Mức độ bền vững, lưu giữ và pháp lý được yêu cầu là gì?
- Có bắt buộc dữ liệu vẫn tồn tại khi JVM crash và log exporter down?

Không gán yêu cầu “không bao giờ mất” cho một AsyncAppender in-memory vốn chỉ phục vụ observability best-effort.

## 3. Bắt đầu từ câu hỏi và hành động, không bắt đầu từ log level

Một mẫu phát biểu mục tiêu tốt:

```text
Khi [TÌNH HUỐNG] xảy ra,
[AI] cần trả lời [CÂU HỎI]
để quyết định [HÀNH ĐỘNG]
bằng [EVENT/FIELDS/METRIC/TRACE].
Mục tiêu đạt khi [TIÊU CHÍ KIỂM CHỨNG]
trong phạm vi [BẢO MẬT/CHI PHÍ/THỜI GIAN] đã phê duyệt.
```

Ví dụ một service thanh toán:

| Tình huống | Câu hỏi | Hành động | Tín hiệu | Acceptance |
| --- | --- | --- | --- | --- |
| Provider timeout | Có ảnh hưởng diện rộng? | Bật fallback/circuit breaker theo runbook | Error-rate metric + log `payment.provider_timeout` + trace | Tìm được event, provider alias, timeout category và trace |
| Payment conflict | Khách hàng thử trùng giao dịch? | Giữ idempotency, trả kết quả phù hợp | `payment.duplicate_request` + audit outcome | Không có secret/PII và không tạo thanh toán trùng |
| Login bị từ chối | Bị nhập sai hay có mẫu lạm dụng? | Điều tra/rate limit có điều kiện | `auth.denied` + count theo nhóm an toàn | Event có reason enum, không log mật khẩu |
| Deploy mới | Bản nào bắt đầu lỗi? | Rollback release nếu cần | `service.started`, release/version metrics | Đối chiếu được version với giai đoạn tăng lỗi |
| Query chậm | DB pool chờ hay SQL execute chậm? | Điều chỉnh pool/query, không đoán mù | Timer histogram + trace + slow log | Phân biệt pool wait với SQL duration |
| Khôi phục dịch vụ | Fix đã có tác dụng? | Đóng incident | Error rate, p95, recovery log | SLO/metrics về baseline theo cửa sổ đo |

**Mỗi mục tiêu nên gắn với một người sử dụng và một quyết định.** Nếu không ai sẽ đọc một loại log, không có dashboard/search/runbook nào phụ thuộc và không có nghĩa vụ lưu giữ, cần xem lại việc có nên phát event ở production hay không.

### 3.1. Ba câu hỏi kiểm tra mục tiêu có đủ cụ thể không

1. **Nếu không có event này, chúng ta mất khả năng quyết định điều gì?**
2. **Nếu có event, người nhận có thể làm gì khác so với trước?**
3. **Nếu event sai hoặc thiếu, chúng ta sẽ phát hiện bằng test hay metric nào?**

Ví dụ “log mỗi lần `findById`” thường không vượt được kiểm tra số 2. “Log `repository.slow_operation` khi pool wait vượt ngưỡng, gắn trace ID, để tìm nghẽn pool” thì thường có thể.

## 4. Tách vai trò Logs – Metrics – Traces

Một mục tiêu quan sát không nhất thiết yêu cầu log mới. Hãy chọn tín hiệu đúng:

| Nhu cầu | Tín hiệu ưu tiên | Vì sao |
| --- | --- | --- |
| Rate request/giây, 5xx % | **Metric counter/rate** | Tính trên lưu lượng với nhãn cardinality thấp |
| p95/p99 HTTP latency | **Metric histogram/timer** | Có phân phối và aggregate phù hợp |
| Một request bị lỗi ở bước nào | **Trace** + log liên quan | Thấy span hierarchy và error context |
| Một quyết định nghiệp vụ vừa xảy ra | **Structured log/business event** | Có event type, outcome, reference an toàn |
| Hành động nhạy cảm cần lưu bền | **Audit trail** riêng | Có transaction/integrity/retention contract |
| Heap/CPU/pool pressure | **Infrastructure/application metrics** | Quan sát xu hướng, không spam INFO |
| Chuỗi retry/fallback cụ thể | **Logs + spans** | Thấy attempt và kết quả có ngữ nghĩa |

Ví dụ p99 request latency **không nên** được suy từ vài slow-request logs, vì log có thể bị sampling, filter hoặc drop. Tương tự, nhìn một trace chậm không đủ để khẳng định toàn bộ traffic bị chậm. Phải định nghĩa các metric và phân phối riêng cho quyết định ở cấp hệ thống.

### 4.1. Tương quan giữa các tín hiệu

Các field kết nối hữu ích:
- `service.name`, environment, version/instance: **resource identity**.
- `trace_id`, `span_id` khi đang ở active span: **correlation với trace**.
- `request_id` được tạo có kiểm soát: **điều tra request**.
- `http.route` dạng template, status, method: **lọc theo phạm vi**.
- Event timestamp và duration: **xác định thời điểm và mức ảnh hưởng**.

Không dùng `trace_id`, `request_id` hay `user_id` làm **metric labels** cho mỗi request. Chúng có cardinality cao. Log/trace có thể giữ một số identifier đã qua đánh giá privacy, còn metrics nên tổng hợp bằng các nhãn như route template/status class/operation.

## 5. Xây event catalog từ các hành trình quan trọng

Đối với ứng dụng web Java, hãy đi từ **critical user journeys**: login, checkout, thanh toán, cập nhật quyền, đồng bộ job, xử lý message. Tại mỗi hành trình, đánh dấu:
- Bắt đầu/hoàn tất hay chỉ sự kiện outcome?
- Decision point và failure mode quan trọng?
- Dependency nào có thể timeout?
- Sự kiện nào mang rủi ro bảo mật/audit?
- Tầng nào đủ ngữ cảnh để ghi và không tạo duplicate?
- Có metric/trace nào đã cung cấp cùng thông tin?

Một **event catalog** minh họa:

| Event name | Trigger | Level gợi ý | Trường tối thiểu | Chủ sở hữu |
| --- | --- | --- | --- | --- |
| `service.started` | Startup đã sẵn sàng | INFO | service, version, environment | Bootstrap |
| `http.request.completed` | Request hoàn tất | INFO/sample hoặc chỉ metrics | method, route, status, duration, trace | HTTP observation |
| `auth.denied` | Quyền bị từ chối | WARN/INFO tùy threat policy | auth method, reason enum, route, request ID | Security boundary |
| `order.created` | Order đã xác nhận trạng thái phù hợp | INFO/business hoặc audit | event, outcome, order alias an toàn | Use-case owner |
| `payment.provider_timeout` | Hết timeout provider | ERROR/WARN theo retry ownership | provider alias, operation, error type, trace | Integration boundary |
| `storage.slow_operation` | Vượt threshold truy cập DB | WARN có điều kiện | operation, datasource, duration | Repository instrumentation |
| `message.delivery_failed` | Hết retry và chuyển DLQ | ERROR | queue, attempt count, error type | Message consumer |
| `permission.changed` | Quyền đã được thay đổi thành công | Audit/security | actor reference được duyệt, action, target, outcome | Authorization/audit |
| `logging.config_changed` | Đổi level/sink/filter quan trọng | Audit/INFO | change ID, config version, actor role | Platform |
| `dependency.recovered` | Từ degraded trở lại healthy | INFO | dependency, recovery window | Health controller |

**Không nên trói một event name vào nội dung message tự do.** Event code ổn định giúp query qua các version. Ví dụ `payment.provider_timeout` giữ nguyên dù message hiển thị tiếng Việt/tiếng Anh khác nhau.

### 5.1. Trigger phải có định nghĩa chính xác

“Phát `order.created` khi tạo đơn hàng” còn mơ hồ:
- Khi bắt đầu request?
- Khi validation xong?
- Khi repository `save()` return?
- Sau transaction commit?
- Khi event đã xuất vào message broker?

Nếu mục tiêu là theo dõi **kết quả nghiệp vụ đã commit**, event phải được phát từ một nguồn phản ánh commit theo contract (post-commit callback nếu chỉ best-effort, transactional outbox/audit store khi yêu cầu bền vững). Dùng các tên khác nhau cho attempt và result, ví dụ `order.create_attempted` vs `order.created`.

### 5.2. Không bắt buộc một event cho mỗi method

Một use case có thể gọi nhiều repository/services. Nếu mọi method in một event INFO, lượng log sẽ tăng nhanh, nhưng truy tìm lỗi lại khó. Thay vì thế:
- Boundary ghi **request summary** hoặc metric.
- Service ghi **business outcome** quan trọng.
- Adapter ghi **diagnostic** khi có failure/latency bất thường.
- Security module ghi các event có yêu cầu an toàn riêng.
- Trace có spans cho các bước cần điều tra chi tiết.

## 6. Chọn mức log theo ý nghĩa, không theo cảm xúc

Trong SLF4J/Logback/Log4j 2, các mức quen thuộc là TRACE, DEBUG, INFO, WARN, ERROR. JUL có tên khác (FINEST/FINER/FINE, INFO, WARNING, SEVERE).

| Mức thường gặp | Cách hiểu | Nên dùng cho |
| --- | --- | --- |
| TRACE | Chi tiết rất sâu, thường tắt | Debug từng pha/thuật toán có điều kiện |
| DEBUG | Context kỹ thuật hữu ích khi điều tra | Cache strategy, decision path, query metadata |
| INFO | Sự kiện đời sống bình thường có giá trị | Startup, thay đổi cấu hình, business milestone |
| WARN | Bất thường nhưng hệ thống còn có thể xử lý | Retry đáng chú ý, fallback, degraded mode |
| ERROR | Thao tác thất bại hoặc mất khả năng phục vụ cần xử lý | Failure cuối, dependency outage, DLQ exhausted |

Một HTTP `404` do người dùng yêu cầu bản ghi không tồn tại **không tự là ERROR**. Một lần retry thành công có thể là WARN/DEBUG theo policy. Ngược lại, một thay đổi quyền truy cập thành công có thể là sự kiện audit quan trọng dù không có exception.

**Severity và alert không giống nhau.** Không nên gửi pager cho từng ERROR; điều kiện alert phải dựa trên mức ảnh hưởng, tần suất, SLO, rủi ro và runbook. Một dòng ERROR có thể đại diện một request thất bại đã được client retry, không có outage.

### 6.1. Khi nào nên thay level và khi nào không được tắt?

- Production mặc định thường giữ INFO/WARN/ERROR có chọn lọc.
- DEBUG/TRACE chỉ mở theo logger/package, thời gian và phạm vi đã phê duyệt.
- Các security/audit events bắt buộc cần được bảo đảm theo policy riêng; không để một thay đổi root level vô tình loại toàn bộ sự kiện quan trọng.
- Với log volume cao, ưu tiên giảm **sự kiện không có giá trị** trước khi chỉ tăng ngưỡng logger global.

Đổi level từ dashboard/runtime API cần quyền, audit và kế hoạch khôi phục. Ví dụ Spring Boot Actuator `/actuator/loggers` có thể sửa level runtime, nhưng thay đổi không tự cập nhật source of truth/config file.

## 7. Thiết kế schema: đủ trả lời câu hỏi nhưng không thừa dữ liệu

Một event có thể có **common envelope**:

```json
{
  "timestamp": "2026-11-10T10:15:20.123Z",
  "severity": "ERROR",
  "event": "payment.provider_timeout",
  "service.name": "orders-service",
  "deployment.environment": "production",
  "service.version": "2026.11.1",
  "operation": "authorize_payment",
  "outcome": "FAILED",
  "error_type": "UPSTREAM_TIMEOUT",
  "duration_ms": 1500,
  "http.route": "/api/orders",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7"
}
```

Đây là **schema ứng dụng minh họa**, không phải raw OTLP JSON bắt buộc. OpenTelemetry Logs Data Model phân biệt `Timestamp`, `ObservedTimestamp`, `SeverityText`, `SeverityNumber`, `Body`, `Attributes`, `Resource`, `TraceId` và `SpanId`. Khi dùng OTel exporter/Collector, ánh xạ tên và kiểu dữ liệu theo semantic conventions/phiên bản thực tế.

Các field nên được xác định:

| Field | Mục đích | Ràng buộc |
| --- | --- | --- |
| `event` | Tên lớp sự kiện ổn định | Enum/catalog, không tự do vô hạn |
| `timestamp` | Định vị trên timeline | UTC/ISO 8601, tránh nhầm ingest time |
| `severity` | Phân loại ưu tiên | Quy tắc nhất quán giữa module |
| `service.name`/version | Xác định nguồn phát | Nhất quán với resource telemetry |
| `operation` | Nghiệp vụ/technical action | Tập giá trị có kiểm soát |
| `outcome` | SUCCESS/FAILED/DENIED/... | Enum, không là exception text |
| `error_type` | Phân loại lỗi | Không chứa raw message có secret |
| `http.route` | Endpoint template | Không dùng raw URI/query/token |
| `duration_ms` | Phân tích trường hợp cụ thể | Numeric, đơn vị rõ |
| `request_id` | Tra cứu request | ID tạo an toàn, không phải session token |
| `trace_id`/`span_id` | Liên kết trace | Chỉ khi context hợp lệ |
| `actor_ref`/`target_ref` | Audit khi cần | Chỉ khi có cơ sở hợp lệ và quyền phù hợp |

**Đủ trường ≠ toàn bộ đối tượng.** Không serialise nguyên `HttpServletRequest`, `User`, entity JPA hoặc DTO login để “có context”. Các object có thể chứa mật khẩu, token, địa chỉ, thông tin sức khỏe hoặc tài chính.

### 7.1. Phân biệt error code với exception message

Thay vì:

```java
log.error("Payment failed: {}", ex.getMessage());
```

ưu tiên loại lỗi đã chuẩn hóa:

```java
log.error("event=payment.provider_timeout provider={} error_type={} trace_id={}",
        "provider-a", "UPSTREAM_TIMEOUT", safeTraceId);
```

Hai đoạn là **snippet SLF4J trong class đã có logger**, không phải file Java tự chạy. `safeTraceId` chỉ nên là ID hợp lệ do tracing/correlation infrastructure cấp. Nếu exception message/cause chứa URL hoặc token, đưa nó vào log có thể làm lộ secret. Giữ Throwable cho debugging **chỉ tại boundary được kiểm soát**, với chính sách lọc dữ liệu và mức truy cập phù hợp.

## 8. Ví dụ Java 17+ chạy độc lập: từ mục tiêu đến sự kiện

Chương trình sau mô phỏng một catalog của ba mục tiêu:

1. **Theo dõi business outcome:** order created.
2. **Theo dõi security denial:** authentication rejected.
3. **Theo dõi operational failure:** payment provider unavailable.

Nó chỉ dùng `java.util.logging` (JUL) của JDK, không có dependencies. Một lớp `Event` yêu cầu tên sự kiện, level, outcome, và một `reason` an toàn. `CaptureHandler` gom log vào bộ nhớ để tạo **stdout hoàn toàn xác định**; cấu hình logger `INFO` để chặn sự kiện chẩn đoán `FINE` không cần thiết trong sản xuất.

Tạo file `LoggingObjectivesDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingObjectivesDemo {
    private record Event(
            String name,
            Level severity,
            String outcome,
            String reason) {
    }

    private static final class CaptureHandler extends Handler {
        private final List<String> lines = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            lines.add(record.getLevel().getName()
                    + " " + record.getMessage());
        }

        @Override public void flush() { }
        @Override public void close() { }

        List<String> lines() {
            return List.copyOf(lines);
        }
    }

    private static void emit(Logger logger, Event event, String requestId) {
        if (!requestId.matches("req-[0-9]{3}")) {
            throw new IllegalArgumentException("INVALID_REQUEST_ID");
        }

        logger.log(event.severity(),
                "event=" + event.name()
                + " outcome=" + event.outcome()
                + " reason=" + event.reason()
                + " request_id=" + requestId);
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.logging.objectives");
        CaptureHandler capture = new CaptureHandler();
        capture.setLevel(Level.ALL);
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);
        logger.addHandler(capture);

        try {
            emit(logger, new Event(
                    "order.created", Level.INFO,
                    "SUCCESS", "NONE"), "req-100");
            emit(logger, new Event(
                    "auth.denied", Level.WARNING,
                    "DENIED", "INVALID_CREDENTIAL"), "req-101");
            emit(logger, new Event(
                    "payment.provider_timeout", Level.SEVERE,
                    "FAILED", "UPSTREAM_TIMEOUT"), "req-102");
            emit(logger, new Event(
                    "repository.cache_lookup", Level.FINE,
                    "SUCCESS", "NONE"), "req-103");

            for (String line : capture.lines()) {
                System.out.println(line);
            }
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac --release 17 LoggingObjectivesDemo.java
java LoggingObjectivesDemo
```

**Stdout chính xác:**

```text
INFO event=order.created outcome=SUCCESS reason=NONE request_id=req-100
WARNING event=auth.denied outcome=DENIED reason=INVALID_CREDENTIAL request_id=req-101
SEVERE event=payment.provider_timeout outcome=FAILED reason=UPSTREAM_TIMEOUT request_id=req-102
```

Giải thích:
- Logger có level INFO nên event FINE `repository.cache_lookup` không xuất ra; đó là lựa chọn của **chiến lược log**, không phải lỗi demo.
- `Event` có tên và outcome chuẩn hóa; không đưa password, token hay exception message vào event.
- `requestId.matches(...)` là **quy tắc kiểm tra input cho demo**, không phải chuẩn định dạng request ID của mọi hệ thống. Trong production nên dùng ID do hệ thống phát hành theo contract, thay vì chỉ dựa vào một regex.
- Handler dùng `isLoggable(record)` và ghi dòng vào list; không chứa timestamp động, nên output xác định.
- `setUseParentHandlers(false)` tránh root handler in thêm dòng và timestamp.
- Các event này mô phỏng trạng thái; **`order.created` trong demo không phản ánh transaction commit thật**. Với audit thật phải lấy sự kiện từ nguồn transactional/durable phù hợp.
- Code **không phải hệ thống observability hoàn chỉnh**: không có backend, retention, TLS, tracing hay metric exporter. Nó chỉ minh họa cách xác định mục tiêu rồi phát log có schema/level nhất quán.

### 8.1. Tại sao catalog tốt hơn message tự do?

Nếu mỗi service viết:

```text
Login fail
User authentication error
Bad password
Authentication rejected
```

thì dashboard và alert phải tìm nhiều biến thể. Một event code ổn định `auth.denied` kèm `reason=INVALID_CREDENTIAL` dễ lọc và phân tích hơn. Con người vẫn có thể đọc message mô tả, nhưng **đừng dùng free-text message như API phân loại sự kiện chính**.

### 8.2. Một thay đổi nhỏ trong catalog cần QA gì?

Nếu đổi event name từ `auth.denied` thành `authentication.denied`:
- Search queries/dashboards cũ có còn kết quả?
- SIEM detection rules có cần cập nhật?
- Downstream consumer có parse schema cũ không?
- Historical reports có cần alias trong thời kỳ chuyển đổi?
- Event coverage unit/integration tests đã được cập nhật?

Đối với một chương trình đào tạo, bài học quan trọng là **event catalog là một contract vận hành**, không chỉ một convention đặt tên.

## 9. Dùng SLF4J/Logback/Log4j 2 theo chính sách đã định

Trong ứng dụng Java hiện đại, SLF4J cung cấp API thường gặp; Logback hoặc Log4j 2 là backend ghi log. Ví dụ code tích hợp:

```java
// Đoạn code bên trong service đã có org.slf4j.Logger log.
log.info("event=order.created outcome={} request_id={}",
        "SUCCESS", safeRequestId);

log.warn("event=auth.denied reason={} request_id={}",
        "PERMISSION_DENIED", safeRequestId);

log.error("event=payment.provider_timeout "
        + "provider={} error_type={} trace_id={}",
        "provider-a", "UPSTREAM_TIMEOUT", safeTraceId);
```

Đây là các snippet cần dependencies và các biến `safeRequestId`, `safeTraceId` của ứng dụng. Placeholder `{}` **không phải data masking**; nếu đưa token hoặc DTO có PII vào tham số logger thì giá trị vẫn có thể bị render.

Khi thêm structured JSON encoder, cân nhắc kiểu field numeric/boolean thay vì nhét mọi thứ vào một message. Với SLF4J 2 fluent API, có thể thêm key-value pairs theo backend/encoder tương thích:

```java
log.atInfo()
   .addKeyValue("event", "order.created")
   .addKeyValue("outcome", "SUCCESS")
   .addKeyValue("request_id", safeRequestId)
   .log("Order creation finished");
```

**Lưu ý:** `addKeyValue` thuộc SLF4J 2; encoder/layout phải thực sự xuất structured key-values thì mới có JSON fields ở backend. Nếu chỉ dùng PatternLayout in `%msg`, không tự cho rằng các key-value pairs sẽ xuất thành cột truy vấn.

### 9.1. Gắn mục tiêu với cấu hình mức log

Ví dụ `application.properties` của Spring Boot:

```properties
logging.level.root=INFO
logging.level.com.example.orders=INFO
logging.level.com.example.orders.repository=WARN
logging.level.org.springframework=INFO
```

Đây là cấu hình **minh họa**; không phải policy bắt buộc cho mọi dự án. Package `com.example.orders.repository` ở WARN có thể phù hợp nếu không cần DEBUG truy vấn thường xuyên. Đừng tắt logger security/audit theo root-level mà không xem yêu cầu riêng.

Với Logback hoặc Log4j 2, kiểm tra **root/child additivity, appender references, filters, async queue** vì level đúng chưa đủ để bảo đảm event đến đích.

## 10. Xác định vị trí phát log và ownership

Một lỗi thanh toán có thể đi qua:

```text
PaymentHttpClient → PaymentRepository → PaymentService
                                            |
                                      HTTP Handler
```

Nếu mỗi tầng phát `ERROR payment failed`, một sự cố sinh nhiều stack traces. Nên chỉ định:

| Tầng | Thông tin biết rõ | Logging phù hợp |
| --- | --- | --- |
| HTTP client adapter | Connection timeout, response code, retry attempt | DEBUG/structured retry diagnostic |
| Repository | Database/transaction behavior | Slow/error classification khi cần |
| Service | Business decision, fallback, idempotency | Business outcome hoặc audit event |
| HTTP handler/consumer | Final result, response/retry/DLQ | Một failure summary/ERROR |
| Platform/collector | Queue, delivery, export failure | Pipeline metrics và status diagnostics |

**Mỗi event có một owner.** Nếu hai tầng phải ghi hai event cho cùng request, tên/semantics nên khác nhau (`payment.retry_scheduled` và `payment.failed_final`), để không bị đếm nhầm thành hai lỗi độc lập.

### 10.1. Exception không được nuốt chỉ vì đã log

Anti-pattern:

```java
try {
    repository.save(entity);
} catch (RuntimeException ex) {
    log.error("event=order.save_failed", ex);
}
return successResponse;
```

Log không sửa transaction và không biến thất bại thành thành công. Nếu không thể recover, phải propagate/translate exception đúng contract; boundary quyết định status/retry. Không log rồi swallow một lỗi quan trọng.

### 10.2. Thời điểm ghi event nghiệp vụ

Không log `order.committed` ngay sau `repository.save` rồi khẳng định dữ liệu đã commit. JPA `flush` và transaction commit có thể còn ở phía sau. Khi mục tiêu đòi hỏi kết quả bền vững, dùng audit/outbox gắn transaction; nếu chỉ là best-effort notification, mô tả rõ contract của post-commit callback.

## 11. Thiết kế privacy và security như một yêu cầu, không phải bước sửa sau

Chiến lược log phải có **dữ liệu cấm** rõ ràng. Theo OWASP, các loại thường không nên ghi trực tiếp gồm access token, session identifier, password, database connection string, encryption key, dữ liệu cá nhân nhạy cảm và thông tin có mức bảo mật cao hơn hệ thống log cho phép.

| Không nên ghi nguyên gốc | Có thể ghi thay thế khi hợp lệ |
| --- | --- |
| Password, OTP, PIN | `auth_method`, `reason=INVALID_CREDENTIAL` |
| Bearer/access/refresh token | `credential_present=true`, outcome |
| Cookie, session ID | `session_started`/`session_expired`, request ID an toàn |
| API key/client secret | Integration alias/key version không cấp quyền |
| JWT nguyên chuỗi hoặc decoded claims tùy tiện | Token type, validation result |
| Raw Authorization/Cookie headers | Danh sách header names được allowlist hoặc Boolean |
| Raw URI/query chứa token | `http.route` template |
| Login/refresh body | Event type, validation category, không field values |
| Entity/DTO có PII | Loại entity/operation và outcome đã chuẩn hóa |
| SQL bind values | Logical query name, table/entity, error type |
| Full exception message chưa kiểm duyệt | Error class/category và trace ID |
| Private key/DB password | Key alias/config version đã được cho phép |

**Allowlist mạnh hơn blocklist** khi schema thay đổi. Nếu developer thêm field `sessionProof` vào DTO, việc serialize toàn object có thể lộ nó dù filter chỉ chặn tên `token` và `password`.

### 11.1. Log injection và dữ liệu không tin cậy

Dữ liệu từ HTTP headers, query string hoặc form có thể chứa newline, control characters hoặc JSON delimiters để giả mạo log entry. Không nối raw user input vào message. Khi một field bắt buộc phải xuất, hãy:
- Validate độ dài và tập ký tự theo nhu cầu.
- Encode đúng cho JSON/structured format.
- Chuẩn hóa danh sách reason/status theo enum.
- Giới hạn số byte mỗi event để tránh log flooding.
- Không đặt input vào MDC/ThreadContext một cách bừa bãi.

Một logging encoder “JSON” chỉ giúp escaping đúng khi cấu hình phù hợp, **không tự loại secret**.

### 11.2. Retention và quyền truy cập gắn với mục đích

Nếu mục tiêu là debug ứng dụng, có thể không cần giữ chi tiết DEBUG lâu. Nếu mục tiêu là audit theo nghĩa vụ hợp pháp, có thể cần giữ lâu hơn và có quyền truy cập chặt hơn. Nhưng **không tự đặt một số ngày cố định** cho mọi tổ chức: retention phụ thuộc nhu cầu, hợp đồng, pháp lý, classification và chi phí.

Ngoài thời gian giữ, cần xác định:
- Ai được search, download, export và chia sẻ?
- Có tách security/audit logs khỏi app debug logs không?
- Có mã hóa in transit/at rest, audit truy cập và bảo vệ backup không?
- Có yêu cầu xóa/ẩn dữ liệu cá nhân, và quy trình nào xử lý?
- Kênh Alert/Ticket/Chat có vô tình sao chép credential không?

## 12. Mục tiêu về chất lượng log và khả năng kiểm chứng

Mỗi mục tiêu nên chuyển thành **acceptance criteria** có thể test. Ví dụ:

| Quality attribute | Tiêu chí mẫu | Cách kiểm tra |
| --- | --- | --- |
| **Coverage** | Mọi nhánh provider timeout đều phát event đúng | Unit/integration tests |
| **Correctness** | Outcome/level/event code đúng semantics | Test theo state machine |
| **Correlation** | Có trace/request ID khi context tồn tại | Test HTTP → downstream |
| **Completeness** | Có error type/operation mà không cần raw secret | Schema validation |
| **Uniqueness** | Một failure final không có ba ERROR giống nhau | Count theo event ID/trace |
| **Timeliness** | Canary log tra được trong cửa sổ ingest mục tiêu | End-to-end pipeline check |
| **Privacy** | Synthetic canary token không xuất ở bất kỳ sink | Secret leak tests |
| **Availability** | Mất Collector không làm JVM treo ngoài budget | Fault injection |
| **Cost** | Log volume/ingest rate trong budget | Load test, counters |
| **Durability** | Audit event vẫn tồn tại sau crash theo contract | Transaction/storage test |
| **Consistency** | Event name/schema ổn định qua release | Contract tests |
| **Actionability** | Có owner, dashboard/query và runbook | Incident drill |

Các con số SLO cụ thể phải được nhóm thống nhất. Không nên tuyên bố “100% logs đến backend trong dưới 1 giây” nếu pipeline dùng async, network và storage không có cam kết đo được. Phân biệt **latency của event ingestion** với **duration xử lý request**.

### 12.1. Một ví dụ acceptance viết được thành test

Mục tiêu: “Khi provider timeout, có một event final đủ chẩn đoán mà không lộ credential”.

- Given: payment provider trả timeout cho request với ID giả.
- When: service xử lý hết retry theo policy và trả lỗi cuối.
- Then: có **đúng một** `payment.provider_timeout` final log từ boundary.
- Then: `error_type=UPSTREAM_TIMEOUT` và `provider=provider-a`.
- Then: event có correlation metadata hợp lệ nếu active trace tồn tại.
- Then: không có giá trị Authorization, API key, password hoặc raw request body.
- Then: metric failure counter/histogram vẫn cập nhật độc lập với việc DEBUG logs có bật hay không.

Đây là một **contract kiểm thử** chứ chưa phải code cụ thể của Spring. Nó có thể được tự động hóa bằng appender test, mock provider, integration test và query backend theo môi trường.

## 13. Log volume và chi phí: mục tiêu phải chịu được production traffic

Một mục tiêu log quá chi tiết có thể không khả thi khi hệ thống tăng traffic. Ước lượng sơ bộ:

```text
bytes/second ≈ requests/second
             × events/request
             × average encoded bytes/event

bytes/day ≈ bytes/second × 86,400
```

Ví dụ giả định:
- 1.000 requests/giây.
- Mỗi request ghi 3 log events.
- Mỗi event trung bình 450 bytes sau encode.

Suy ra:

```text
1,000 × 3 × 450 = 1,350,000 bytes/second
1,350,000 × 86,400 = 116,640,000,000 bytes/day
≈ 116.64 GB/day (decimal, chưa tính replicas/index/retention)
```

Con số chỉ là **dung lượng data thô** trong kịch bản ví dụ. Backend indexing, compression, replicas, storage class, egress và retention có thể làm chi phí khác nhiều. Peak traffic, exception stack traces lớn và log bursts thường không bằng trung bình.

Khi giảm volume:
1. Bỏ các events không có mục tiêu rõ.
2. Gộp các log lặp thành một outcome summary.
3. Dùng metrics cho đếm/tần suất thay vì INFO từng lần.
4. Giữ error/security events quan trọng theo policy.
5. Sample những event thường xuyên khi phù hợp, có thể ghi `sampling_rate`.
6. Giới hạn field size, stack trace và payload theo use case.
7. Chọn retention tier theo giá trị, đừng xóa bừa audit.
8. Theo dõi drops, queue depth và backend ingest errors.

**Sampling thay đổi ý nghĩa dữ liệu.** Nếu chỉ giữ 1/10 request summaries, không lấy số dòng raw làm request count tuyệt đối. Metric counter/throughput hoặc phương pháp ước lượng có tính sampling phải được dùng nếu cần số liệu toàn traffic.

### 13.1. Log quá ít cũng có chi phí

Không log gì vì “sợ chi phí” khiến on-call phải bật TRACE trên production lúc khẩn cấp, dễ làm lộ dữ liệu và kéo dài incident. Chiến lược tốt chọn **một số events ổn định, có tín hiệu cao** ở INFO/WARN/ERROR và giữ DEBUG có kiểm soát cho điều tra chuyên sâu.

## 14. Chọn tuyến ghi: stdout, file, remote hay audit storage?

Mục tiêu log ảnh hưởng đường vận chuyển:

| Mục tiêu | Lựa chọn thường hợp lý | Cần kiểm chứng |
| --- | --- | --- |
| App diagnostics trong container | Structured stdout → shipper/Collector | Log parser, pod metadata, retention |
| Tương quan logs với traces | Encoder/bridge có trace/span IDs | Active context, OTLP pipeline |
| Legacy on-prem file capture | Rolling file + file shipper | Disk quota, rotation, offsets |
| Low-latency remote ingest | Async exporter/appender | Queue/drop/retry/backpressure |
| Security investigation | Central restricted security log store | ACL, audit access, tamper detection |
| Audit giao dịch bền vững | Transactional audit/outbox/database | Commit, crash recovery, replay/dedup |
| Metrics/SLO | Micrometer/OpenTelemetry metrics | Registry, histogram, labels, exporter |

**Một TCP write thành công không chứng minh backend đã lưu log bền vững.** HTTP/OTLP response cũng phải được hiểu theo contract của receiver và các tầng Collector/exporter/queue. Với kênh quan trọng, theo dõi lost events, retry và queue capacity.

Nếu phát cùng event qua stdout shipper và OTLP exporter vào **cùng backend index**, có thể bị duplicate. Điều này ảnh hưởng error count và incident search; chiến lược phải chỉ rõ nguồn phát chính cho từng loại event.

## 15. Xác định ownership, lifecycle và thay đổi chiến lược

Một chiến lược logging cần có chủ sở hữu:

| Hạng mục | Trách nhiệm |
| --- | --- |
| Event catalog | Engineering + service owner |
| Security events/data exclusion | Security/privacy owner |
| Audit retention/durability | Compliance/business owner + platform |
| Shared schema/context | Platform/observability |
| Logger/appender configuration | Service/platform owner |
| Alerts, dashboards, runbooks | On-call/SRE và service owner |
| Version/schema migration | API/event contract owners |
| Secret leak response | Security incident process |

Khi thay đổi một event:
- Tên event có bị dashboard, SIEM hoặc alert query phụ thuộc không?
- Severity thay đổi sẽ tác động sampling/drop policy không?
- Một field bị đổi kiểu string → integer có làm parser thất bại?
- Nếu thêm PII, đã có mục đích hợp pháp và quyền lưu trữ chưa?
- Nếu thay exporter/encoder, có risk duplicate hoặc missing logs?
- Nếu đổi root level, còn những security events bắt buộc không?
- Có kế hoạch rollback/config version và QA sau deploy không?

**Logging policy nên là code-reviewed và versioned contract.** Không cần mọi update phải nặng nề, nhưng thay event name hoặc retention có thể tác động đội vận hành và compliance nhiều hơn thay một câu message.

## 16. Workflow thiết kế mục tiêu log cho một service Java mới

### Bước 1 — Liệt kê user journeys và failure modes

Ví dụ order service:
- Create order thành công, duplicate request.
- Payment provider fail, timeout, retry và fallback.
- Inventory không đủ.
- Database connection pool exhausted.
- Không có quyền tạo order.
- Message bị gửi vào DLQ.
- Deploy/restart, config thay đổi.

### Bước 2 — Viết câu hỏi quyết định

Ví dụ:
- “Có bao nhiêu request trả 5xx sau release?” → metrics.
- “Một payment cụ thể thất bại vì loại lỗi nào?” → structured log.
- “Lời gọi dependency nào tốn 1 giây?” → trace.
- “Ai đã cấp quyền admin và thay đổi có commit chưa?” → audit.

### Bước 3 — Chọn owner của từng event

Boundary cho final failure, service cho business outcome, adapter cho diagnostic riêng, audit subsystem cho privileged actions. Không log cùng một failure dưới tên giống nhau ở mọi tầng.

### Bước 4 — Thiết kế schema và privacy

Chốt event name, severity, required fields, field types, cardinality, max length, sensitive-data exclusions. Dùng route template, reason enum, trace/request ID hợp lệ.

### Bước 5 — Định nghĩa level, sampling và retention

Xác định default production, logger được phép bật DEBUG, rate limit/sampling rules, alert thresholds và dữ liệu bắt buộc không được drop.

### Bước 6 — Chọn sink và cơ chế vận chuyển

Phân biệt app diagnostics best-effort với audit durability. Xác định khả năng chịu outage, queue full/drop, TLS, ingest lag và quyền đọc logs.

### Bước 7 — Viết acceptance test và runbook

Mô phỏng 2xx, 4xx, 5xx, timeout, retry, DB loss, exception, async, Collector outage; xác minh log có đủ context/không rò bí mật và metric/trace vẫn tương quan.

### Bước 8 — Rollout canary và đo thực tế

Theo dõi log volume/chi phí, số sự kiện mỗi request, ingest delay, duplicates, query usability, p95 latency và security canaries. Nếu log nhiều mà vẫn không hỗ trợ quyết định, cập nhật event catalog, **không tăng DEBUG tràn lan**.

## 17. Những sai lầm phổ biến khi xác định mục tiêu log

**Sai lầm 1 — “Ghi mọi thứ để phòng trường hợp cần”.** Kết quả là noise, chi phí và rủi ro lộ dữ liệu. Chỉ giữ event có use case/owner rõ.

**Sai lầm 2 — Chọn INFO/WARN/ERROR trước khi biết sự kiện có nghĩa gì.** Severity trở nên không nhất quán, pager bị alert fatigue.

**Sai lầm 3 — Dùng INFO per-request để đo request rate/p99.** Metrics/histogram phù hợp hơn; logs có thể bị drop/sample.

**Sai lầm 4 — Ghi business success trước transaction commit.** Event không phản ánh kết quả thật; audit cần nguồn transactional.

**Sai lầm 5 — Ghi stack trace ở mỗi tầng.** Một failure bị đếm nhiều lần và khó điều tra.

**Sai lầm 6 — In toàn bộ entity, HTTP body, SQL binds để có context.** Làm lộ password, token và PII; dùng allowlist.

**Sai lầm 7 — Dùng raw URL/user ID làm metric tags.** Cardinality bùng nổ; dùng route template và low-cardinality dimensions.

**Sai lầm 8 — Coi DEBUG là không bao giờ ra production.** DEBUG có thể bật khi incident; vẫn phải tránh secret ngay tại nguồn.

**Sai lầm 9 — Không định nghĩa ai dùng event.** Log tồn tại trong backend nhưng không có truy vấn/runbook nào biết đến nó.

**Sai lầm 10 — Dựa vào collector ACK để tuyên bố audit zero-loss.** Network/backend có queue và crash windows; cần contract durability riêng.

**Sai lầm 11 — Chỉ test code có gọi logger.** Chưa chứng minh level, filter, appender và backend thực nhận event.

**Sai lầm 12 — Không tính retention, quyền đọc và bản sao.** Log có thể được xuất sang alert, ticket và backup; cần giới hạn theo mục đích.

**Sai lầm 13 — Không version schema.** Đổi event name làm gãy dashboard, SIEM detection, integration consumers.

**Sai lầm 14 — Đếm “số dòng ERROR” là “số sự cố”.** Một incident có nhiều requests, retries và duplicate logging; cần metrics và event semantics rõ.

**Sai lầm 15 — Cố dùng một kênh cho tất cả.** Security/audit, request diagnostics và performance metrics có privacy, durability và retention khác nhau.

## 18. Ma trận QA trước khi phát hành chiến lược

| Case | Điều cần chứng minh |
| --- | --- |
| HTTP 200 | Summary/metric đúng policy, không spam INFO ở mỗi method |
| 404 do không tìm thấy | Không mặc định ERROR hạ tầng |
| Auth denied | Security event đúng reason, không lộ credential |
| 5xx exception | Một final failure log, error type + trace, không log trùng 3 tầng |
| DB timeout | Phân biệt timeout với not found; có metric/trace cần thiết |
| Retry thành công | Attempts và final outcome có semantics không nhập nhằng |
| Retry hết hạn | Có failure cuối, không nuốt lỗi |
| Transaction rollback | Không có “committed success” giả |
| Audit privileged change | Actor/action/outcome theo policy và contract lưu bền |
| Async/worker thread | Correlation ID được propagate đúng scope |
| Logger level thay đổi | Event quan trọng vẫn có theo policy |
| Structured JSON | Field types, names, escaping và schema được verify |
| Token canary | Không lọt vào message, args, throwable, MDC, spans, metrics |
| Log injection | Newline/control characters không tạo event giả |
| Load test | CPU, storage, collector queue, request latency trong budget |
| Collector down | Ứng dụng không bị treo ngoài timeout, loss/drop được quan sát |
| Dual ingest | Không duplicate một logical event trong cùng index |
| Event schema migration | Old queries/alerts được cập nhật có kiểm thử |
| Metrics p95/p99 | Có histogram thích hợp và nhãn cardinality thấp |
| Retention/privacy | Access, export, delete và backup policy được áp dụng |
| End-to-end canary | Event đến đúng sink và có thể tìm bằng event code/ID |

Nếu chỉ QA output console thì chưa kiểm tra pipeline. Với hệ thống centralized logging, cần xác minh source → encoder → shipper/collector → backend và chú ý event timestamp khác ingest timestamp. Tuy nhiên, chạy mọi failure injection trên production có thể gây gián đoạn; nên test trước ở staging hoặc môi trường cô lập với dữ liệu tổng hợp.

## 19. Mẫu tài liệu mục tiêu log có thể điền cho từng event

```yaml
# Tài liệu yêu cầu minh họa, không phải logback/log4j2 config.
event_name: "payment.provider_timeout"
purpose: "Khoanh vùng provider timeout và hỗ trợ quyết định fallback"
consumer: "Orders on-call"
owner: "Payments service team"
trigger: "Hết retry budget và thanh toán thất bại"
severity: "ERROR"
source_boundary: "Payment application service"
required_fields:
  - "service.name"
  - "service.version"
  - "operation"
  - "provider_alias"
  - "error_type"
  - "trace_id"
excluded_fields:
  - "authorization"
  - "access_token"
  - "card_number"
  - "payment_payload"
sampling: "Giữ final failure; policy riêng cho success diagnostics"
delivery: "Central app logs; best-effort theo pipeline hiện hành"
retention: "Theo chính sách đã phê duyệt"
acceptance:
  - "Một final error event cho một failed request"
  - "Có correlation để tìm trace khi được sampling"
  - "Synthetic token canary không xuất ở các sinks"
  - "Collector failure được giám sát độc lập"
```

Tài liệu này có thể được lưu cạnh ADR hoặc event catalog của service, review cùng code/observability dashboards. Giá trị trong ví dụ không phải một tiêu chuẩn cứng cho mọi tổ chức; **retention, zero-loss và audit** phải được quyết định theo yêu cầu thực tế.

## 20. Checklist quyết định mục tiêu trước khi code

1. **Mục đích:** incident response, debugging, security, audit, business monitoring hay performance?
2. **Người dùng:** ai tra cứu, alert cho ai và ai có quyền hành động?
3. **Câu hỏi:** event giúp trả lời điều gì mà metrics/traces hiện tại chưa có?
4. **Trigger:** phát lúc attempt, failure, retry hay commit? Có tránh double-log không?
5. **Schema:** event name, timestamp, level, outcome, error type, service, version, trace ID?
6. **Dữ liệu cấm:** password, token, cookie, PII, SQL binds, raw request/exception?
7. **Tín hiệu phù hợp:** log, metric, trace hay audit storage?
8. **Chi phí:** events/request, payload size, ingest/day, retention, sampling?
9. **Độ tin cậy:** queue/drop/retry/Collector outage, audit durability?
10. **Truy cập:** quyền search/export, TLS, encryption, retention và backups?
11. **Kiểm chứng:** tests tìm đúng log, đúng số lượng, đúng level/schema, không rò secret?
12. **Vận hành:** dashboard/query/runbook, alerting, owner và kế hoạch thay đổi schema?

**Kết luận:** Một chiến lược log tốt không bắt đầu bằng việc “ghi bao nhiêu dòng” mà bắt đầu bằng **“chúng ta cần trả lời câu hỏi gì để đưa ra quyết định nào?”**. Từ đó mới lựa chọn sự kiện, nơi phát, mức log, field schema, tín hiệu tương ứng, chi phí và bảo vệ dữ liệu. Khi mục tiêu đủ rõ để viết thành acceptance test, log mới trở thành tài sản vận hành hữu ích thay vì nhiễu trong production.

## Tài liệu tham khảo

- [OWASP – Logging Cheat Sheet: Purpose, events to log, data to exclude và testing](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- [OpenTelemetry – Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/).
- [OpenTelemetry – Observability Signals](https://opentelemetry.io/docs/concepts/signals/).
- [OpenTelemetry – Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/).
- [OpenTelemetry – Java instrumentation](https://opentelemetry.io/docs/languages/java/).
- [SLF4J – User Manual, fluent logging](https://www.slf4j.org/manual.html).
- [Logback – Logging Architecture](https://logback.qos.ch/manual/architecture.html).
- [Apache Log4j 2 – Log Levels](https://logging.apache.org/log4j/2.x/manual/customloglevels.html).
- [Spring Boot – Logging configuration](https://docs.spring.io/spring-boot/reference/features/logging.html).
- [Oracle Java 17 – java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html).
- [Micrometer – Timers and histograms](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).