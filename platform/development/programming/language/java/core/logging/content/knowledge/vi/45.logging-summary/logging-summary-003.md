# Checklist nội dung log trong Java: từ code review đến nghiệm thu production

## 1. Mục đích và cách dùng checklist

Một hệ thống có thể đã bật SLF4J, Logback hoặc Log4j2 nhưng log vẫn **không hữu ích**: dòng log không nói rõ sự kiện, thiếu request ID, đánh dấu `SUCCESS` trước khi transaction commit, ghi sai mức ERROR hoặc vô tình chứa token, mật khẩu và dữ liệu cá nhân. **Checklist nội dung log** là bộ câu hỏi kiểm tra **từng log event và hợp đồng dữ liệu của nó** trước khi code được merge hoặc triển khai.

Tài liệu này là bài tổng kết cho **Java Core Logging**, không phụ thuộc vào một logging backend cụ thể. Với mỗi lời gọi logger hoặc structured event, reviewer cần xác nhận:

1. **Có nên ghi sự kiện này không?** Mục đích vận hành, an ninh hoặc audit là gì?
2. **Ghi tại thời điểm nào?** Attempted, accepted, denied, committed, completed hay failed?
3. **Ghi ở level nào?** DEBUG, INFO, WARN hay ERROR phản ánh đúng mức độ?
4. **Đã đủ ngữ cảnh chưa?** Service, event type, operation/request/trace ID, route, outcome.
5. **Các trường có đúng kiểu và nguồn tin cậy không?** Status number, duration có đơn vị, actor đã xác thực.
6. **Có thông tin bí mật hoặc không cần thiết không?** Authorization, Cookie, PII, payload, URL chứa token.
7. **Có đọc, truy vấn và liên kết được không?** JSONL hợp lệ, field schema ổn định, event ID có thể tìm kiếm.
8. **Có đo và kiểm thử được không?** Positive/negative cases, escape, async, redaction, actual encoder output.

**Mục tiêu không phải càng nhiều log càng tốt.** Một log đạt chuẩn chứa **đúng thông tin, ở đúng nơi, đúng thời điểm**, đủ để chẩn đoán nhưng không trở thành nguồn rò rỉ hoặc làm nghẽn hệ thống.

## 2. Checklist ngắn cho mỗi dòng log trước khi merge

Dùng bảng này như một **PR review gate**:

| Câu hỏi | PASS khi | Dấu hiệu FAIL |
| --- | --- | --- |
| **Purpose** | Có tình huống tìm kiếm/alert/audit rõ ràng | `logger.info("Here")` không giúp trả lời điều gì |
| **Event identity** | Có `event.name`/mã cố định | Phụ thuộc parse câu tiếng Anh tự do |
| **Timing** | Outcome đã được xác nhận tại đúng mốc | Ghi “thành công” trước commit |
| **Severity** | Level phù hợp tác động thực tế | Mọi 4xx đều ERROR |
| **Context** | Service, request/operation/trace ID khi có | Không phân biệt được hai request |
| **Schema** | Field names/types/units nhất quán | `duration_ms` nhưng số liệu là nanosecond |
| **Source trust** | Actor, tenant và route lấy từ nguồn đáng tin | Lấy identity từ `X-User-ID` |
| **Safety** | Không ghi password, token, card data, raw body | Log toàn object request |
| **Bounded size** | Message/stack trace có giới hạn phù hợp | Log multi-MB trong vòng lặp |
| **Actionable** | Có mã lỗi hoặc safe reason code phù hợp | “Something went wrong” |
| **No duplication** | Mỗi tầng có trách nhiệm rõ | Một exception log ERROR 4 lần |
| **Testability** | Có test field/type/secret và output | Chỉ assert rằng mock logger được gọi |

Nếu một yêu cầu không áp dụng, nên ghi rõ **N/A và vì sao**. Ví dụ startup event không có HTTP request ID; đó không tự động là lỗi.

## 3. Checklist quyết định “có cần log sự kiện này?”

Trước khi viết `logger.info(...)`, hãy hỏi:

- [ ] Event có phục vụ troubleshooting, vận hành, phân tích bảo mật hoặc audit rõ ràng?
- [ ] Đã có metric/tracing tốt hơn để biểu diễn tín hiệu có tần suất cao chưa?
- [ ] Nếu không ghi event này, nhóm trực còn đủ dữ liệu tìm root cause không?
- [ ] Có một log tương đương đã được ghi tại boundary khác không?
- [ ] Event giúp phân biệt **nguyên nhân** hoặc **kết quả**, thay vì kể lại từng bước hiển nhiên?
- [ ] Có cần event ở mọi request hay chỉ khi trạng thái chuyển đổi/thất bại?
- [ ] Nếu tần suất tăng 100 lần, log có còn hữu ích và an toàn về chi phí?
- [ ] Nếu cần audit, sự kiện này có yêu cầu lưu bền vững khác application log thông thường không?

**Không nên log từng iteration** hoặc mỗi lần getter được gọi, trừ khi có nhu cầu chẩn đoán đặc biệt và mức DEBUG được kiểm soát. **Không nên im lặng** với những thay đổi quyền, credential compromise, security denial hoặc business commit có nghĩa vụ audit, chỉ vì chúng làm tăng volume.

### Phân biệt event và metric

Một ứng dụng có 1.000 request/s không nhất thiết cần 1.000 INFO “request started” từ mỗi helper method. Có thể:

- Dùng access event tối giản tại HTTP boundary.
- Ghi event nghiệp vụ ở điểm outcome thực sự.
- Dùng metric counter/histogram cho throughput và latency.
- Dùng trace cho đường đi qua nhiều service.
- Ghi WARN/ERROR khi có vấn đề cần chú ý.

**Sampling log** có thể giảm chi phí chẩn đoán, nhưng thay đổi tính đại diện. Không sampling tùy tiện audit/security event cần bảo toàn.

## 4. Checklist tên sự kiện: “Điều gì đã xảy ra?”

Một log nên có **event name ổn định, có khả năng lập chỉ mục**, ví dụ:

| Tình huống | Event code tốt | Không nên chỉ ghi |
| --- | --- | --- |
| Đơn hàng hoàn tất | `checkout.completed` | `"All good"` |
| Đơn hàng bị từ chối | `checkout.rejected` | `"Cannot do that"` |
| Dependency lỗi | `dependency.call_failed` | `"Exception!"` |
| Login bị từ chối | `authentication.failed` | `"Wrong password for..."` |
| Quyền bị từ chối | `authorization.denied` | `"Bad user"` |
| Token được cấp | `token.issued` | JWT/token thật |
| Job được nhận | `job.accepted` | `"Job done"` |
| Worker hoàn tất | `job.completed` | `"202 returned"` |
| Cấu hình thay đổi | `configuration.changed` | Dump config mới có secret |

**Checklist:**

- [ ] Event name chọn từ catalog/enum có owner, không là chuỗi do client tự gửi.
- [ ] Tên mô tả **sự kiện đã diễn ra**, không dự báo kết quả chưa biết.
- [ ] Có ngữ nghĩa phân biệt `started`, `accepted`, `failed`, `completed` và `committed`.
- [ ] Event code được version/review khi đổi, tránh làm hỏng dashboard/alert.
- [ ] Có nguồn sinh event rõ: auth handler, controller boundary, business transaction hay worker.
- [ ] Không nhét dynamic ID vào tên, như `checkout.completed.123456`, gây cardinality cao.
- [ ] Không dùng một event name cho hai hành động nghiệp vụ khác semantics.

Ví dụ `event.name=payment.completed` chỉ hợp lý sau khi có bằng chứng thanh toán hoàn tất; HTTP `202 Accepted` hoặc việc gửi yêu cầu tới gateway không đủ.

## 5. Checklist thời điểm phát log và tính đúng của outcome

**Thời điểm log quyết định tính trung thực.** Các mốc không tương đương:

```text
Request received
    │
    ▼
Authentication / authorization
    │
    ▼
Business validation
    │
    ▼
Transaction begin
    │
    ▼
Business state changed
    │
    ▼
Transaction committed
    │
    ▼
Downstream delivery or asynchronous completion
```

Ví dụ:

- `checkout.started`: workflow bắt đầu, không nói thành công.
- `checkout.rejected`: business rule đã từ chối.
- `checkout.accepted`: yêu cầu đã được nhận để xử lý async.
- `checkout.completed`: nghiệp vụ thực sự đạt điều kiện hoàn tất.
- `checkout.failed`: đã xác nhận failure theo logic tương ứng.
- `audit.role.granted`: role change đã commit theo contract, không phải mới gọi `save()`.

**Checklist:**

- [ ] Event được phát tại mốc mà code thật sự biết trạng thái.
- [ ] Outcome `SUCCESS`/`FAILED`/`DENIED`/`ACCEPTED` có định nghĩa riêng.
- [ ] HTTP status được ghi theo ranh giới đo; không suy thành business commit.
- [ ] Retry và duplicate dùng operation ID/attempt ID để phân biệt.
- [ ] Nếu transaction rollback, không còn event “đã commit” sai.
- [ ] Nếu event cần bền vững cùng transaction, đã đánh giá outbox/audit store.
- [ ] Asynchronous job dùng hai mốc accepted/completed khi cần.
- [ ] Lỗi trước authentication không gán người dùng đã xác thực từ username tự khai.

**Một quy tắc kiểm thử quan trọng:** với transaction rollback, kiểm không có event `COMMITTED` sai; với job 202, kiểm có event `ACCEPTED` và event completion do worker riêng phát.

## 6. Checklist mức log: DEBUG, INFO, WARN, ERROR

| Level | Dùng khi | Không nên dùng khi |
| --- | --- | --- |
| TRACE | Chi tiết rất sâu, có thời hạn và nguồn dữ liệu an toàn | Dump secret hoặc bật toàn production lâu dài |
| DEBUG | Dữ liệu chẩn đoán trong phạm vi package/service | Ghi mọi object đầy đủ bất kể privacy |
| INFO | Trạng thái hệ thống và nghiệp vụ có ý nghĩa | Log mỗi vòng lặp không có giá trị |
| WARN | Bất thường có thể phục hồi hoặc cần chú ý | Mỗi business validation từ chối đều WARN |
| ERROR | Lỗi cần điều tra/tác động khả năng xử lý | Mọi 400/401/404 đều ERROR |
| FATAL/SEVERE | Tùy backend, mức lỗi nghiêm trọng nhất | Cho rằng mọi facade đều có cùng enum |

SLF4J thường dùng `WARN`; JUL dùng `WARNING`; Log4j2 có các mức riêng. **Không lấy tên enum của backend này làm output chắc chắn của backend khác.**

- [ ] Level dựa trên **tác động và nhu cầu phản ứng**, không chỉ HTTP status.
- [ ] WARN/ERROR đủ ít và đủ chất lượng cho alerting.
- [ ] Không ghi ERROR cùng exception ở tất cả tầng nếu không bổ sung thông tin.
- [ ] Không dùng mức thấp để cố ý giấu audit/security event bắt buộc.
- [ ] DEBUG disabled không làm tính toán formatting/`toString()` đắt không cần thiết.
- [ ] Khi tăng level tạm thời, có owner, phạm vi, thời điểm rollback và privacy check.
- [ ] Test effective logger level **và appender/handler filter** khi kỳ vọng event xuất hiện.

Ví dụ **SLF4J trích đoạn**, không phải Java độc lập:

```java
if (logger.isDebugEnabled()) {
    logger.debug("diagnostic_summary={}", buildSafeDebugSummary());
}
```

Việc dùng parameterized message không làm một hàm tạo đối số đắt trở nên lazy: Java vẫn tính `buildSafeDebugSummary()` trước lời gọi `debug` nếu không có guard/supplier thích hợp.

## 7. Checklist trường cơ bản trong mỗi structured event

Mẫu schema tối thiểu có thể gồm:

| Field | Kiểu gợi ý | Required? | Người chịu trách nhiệm |
| --- | --- | --- | --- |
| `@timestamp` | ISO-8601 UTC string | Thường có | Encoder/event source |
| `level` | enum string | Có | Logging backend |
| `service.name` | string | Có | Trusted deployment config |
| `environment` | string | Thường có | Trusted deployment config |
| `schema.version` | integer | Có nếu có contract | Event schema owner |
| `event.name` | stable string | Có với business/security events | Event producer |
| `message` | concise string | Có thể | Business/event producer |
| `request_id` | validated string | HTTP events khi có | Edge/application boundary |
| `trace_id` | 32 lower-hex string | Khi có valid trace | Tracing instrumentation |
| `span_id` | 16 lower-hex string | Khi có active span | Tracing instrumentation |
| `http.route` | trusted route template | HTTP routed events | Framework/router |
| `http.method` | controlled string | HTTP events | HTTP instrumentation |
| `http.status_code` | integer | Completed HTTP events | HTTP boundary |
| `duration_ms` | integer/long | Timed event | Monotonic timer |
| `outcome` | controlled enum | Event-dependent | Business/security layer |
| `error.code` | controlled string | Với error có mã | Error classification |
| `operation_id` | safe string | Job/transaction cần correlation | Workflow owner |
| `actor.id` | potentially sensitive string | Audit theo chính sách | Verified security context |

**Không có schema required duy nhất cho mọi dòng**: startup, GC, HTTP access, background job và audit có các trường khác nhau. Schema nên được quy định **theo event class hoặc event.name**, có field bắt buộc và field tùy chọn rõ ràng.

### Checklist theo field

- [ ] Tên thống nhất qua các service và version.
- [ ] JSON number vẫn là number, boolean vẫn là boolean; không stringify mọi thứ.
- [ ] Duration có đơn vị trong tên và rõ mốc bắt đầu/kết thúc.
- [ ] Timestamp có timezone, không phụ thuộc locale máy.
- [ ] Value null, missing và empty string có semantics khác nhau và được test.
- [ ] Field có chiều dài tối đa hoặc enum khi thích hợp.
- [ ] Không có duplicate JSON keys hoặc xung đột với trường encoder tự sinh.
- [ ] Không có field tùy ý được chèn từ JSON request hoặc metadata không tin cậy.
- [ ] Có schema version/migration khi đổi tên hoặc kiểu dữ liệu.

## 8. Checklist log message: ngắn, có nghĩa, không chứa dữ liệu sống

Một structured log tốt vẫn có thể có `message` để người vận hành đọc nhanh, nhưng message **không nên là nơi nhét hết dữ liệu**.

**Nên:**

```text
event.name=checkout.rejected
message="Checkout rejected by inventory policy"
error.code="OUT_OF_STOCK"
http.status_code=409
```

**Không nên:**

```text
"Checkout rejected for username=user@example.com, token=eyJ..., body={...}"
```

Checklist:

- [ ] Message trả lời “điều gì đã xảy ra”, không kể quá dài.
- [ ] Ưu tiên event code và structured fields để filter; message chỉ bổ trợ.
- [ ] Không nối trực tiếp raw input của client vào string.
- [ ] Nếu có dữ liệu do người dùng gửi, field/value được validation, escaping và giới hạn độ dài.
- [ ] Không có password/token/cookie/session ID/card data.
- [ ] Không tạo thông điệp sai ngữ nghĩa khi ngoại lệ hoặc rollback.
- [ ] Không log lặp cùng lỗi ở nhiều tầng mà thiếu context mới.
- [ ] Có message an toàn ngay cả khi chuyển level INFO sang DEBUG.
- [ ] Message có Unicode/CRLF/quotes vẫn được encode an toàn cho JSONL.

**Thông điệp “Error: null”** hoặc “Failure!” không đủ nếu có thể thêm safe reason code và bước xử lý; nhưng đừng thay bằng full request dump.

## 9. Checklist thời gian: timestamp, duration và clock

Hai trường dễ gây lỗi nhất là **timestamp** và **duration**.

| Field | Cách làm phù hợp | Lỗi thường gặp |
| --- | --- | --- |
| `@timestamp` | UTC/offset rõ, từ event source | `LocalDateTime.toString()` thiếu timezone |
| `ingested_at` | Collector/backend thêm lúc nhận | Nhầm thành thời điểm event xảy ra |
| `duration_ms` | Tính delta từ monotonic clock | Lấy `currentTimeMillis` có thể bị chỉnh giờ |
| `timeout_ms` | Thời hạn cấu hình để gọi dependency | Nhầm với elapsed time thật |
| `retry_delay_ms` | Delay giữa các lần thử | Ghi nhầm nanosecond |
| `event.sequence` | Sequence nếu hệ thống thực sự quản lý | Tự suy thứ tự tuyệt đối từ timestamp |

Ví dụ elapsed time trong Java:

```java
// Trích đoạn JDK17; chỉ phép đo, không phải chương trình độc lập.
long start = System.nanoTime();
try {
    performBusinessOperation();
} finally {
    long elapsedMs =
            java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start);
    recordDurationMetric(elapsedMs);
}
```

**Đơn vị và ranh giới phải phù hợp:** nếu chạy async, `finally` của phương thức HTTP có thể diễn ra trước khi worker hoàn tất. Không gắn `duration_ms` vào event `completed` khi chỉ mới submit job.

- [ ] Timestamp parse được và có offset UTC rõ.
- [ ] Duration không âm; phần trăm/tỷ lệ có tên và đơn vị thích hợp.
- [ ] Không đo duration bằng hai wall-clock timestamps dễ bị clock adjustment.
- [ ] Có test boundary thời gian, timeout và slow dependency.
- [ ] Với logger async, nhận biết event time khác ingestion time và không coi lag là latency nghiệp vụ.
- [ ] Không dùng wall-clock timestamps để suy exactly-once ordering của distributed system.

## 10. Checklist correlation và trace context

Mỗi request/job dài hạn có thể cần nhiều ID, nhưng chúng **không tương đương**:

| Trường | Ý nghĩa | Nguồn đáng tin |
| --- | --- | --- |
| `request_id` | Correlation của HTTP request | Server/gateway sinh hoặc validate |
| `trace_id` | Liên kết distributed trace | Tracing instrumentation |
| `span_id` | Span hiện tại | Tracing instrumentation |
| `operation_id` | Workflow qua retry/queue | Business orchestration |
| `event.id` | Phân biệt event/replay/duplicate | Event producer có cơ chế ID |
| `job_id` | Định danh job | Job scheduler/queue |
| `tenant.id` | Scope tenant | Authenticated tenant context |
| `actor.id` | Principal thực hiện hành động | Security context đã xác thực |

Checklist:

- [ ] ID được validate format/length trước log; không dùng trực tiếp string bất kỳ từ header.
- [ ] Trace ID không được coi là xác thực danh tính người dùng.
- [ ] Một request phát nhiều event có request/trace ID nhất quán.
- [ ] Hai request khác nhau không bị lẫn context sau thread reuse.
- [ ] Async worker có context được truyền minh bạch, không mong `ThreadLocal` tự qua thread khác.
- [ ] Event ngoài HTTP (scheduler/startup) có chính sách field vắng mặt.
- [ ] Không đưa baggage chứa PII/token vào mọi log qua MDC.
- [ ] Nếu actor/tenant cần lưu, lấy từ verified principal; áp access control/retention tương ứng.
- [ ] Không dùng request/user/trace ID làm metric labels có cardinality không giới hạn.

## 11. Checklist log exceptions: đủ chẩn đoán nhưng không leak

Khi xảy ra exception, cần biết:

- **Loại lỗi** và safe error code.
- **Bước xử lý/dependency class** gây lỗi.
- **Outcome**: retry, fallback, failed, partial success.
- **Request/operation ID** để điều tra.
- **Lỗi có ảnh hưởng người dùng hay không**, theo HTTP/business boundary.
- **Stack trace** chỉ khi đã review và sink có quyền/retention phù hợp.

### Mẫu tốt và không tốt

```java
// Trích đoạn dùng SLF4J, không biên dịch độc lập.
logger.error("Checkout dependency failed: code={} operation_id={}",
        "INVENTORY_UNAVAILABLE", safeOperationId);

// RỦI RO: exception có thể chứa raw URL/query/token từ HTTP client.
logger.error("HTTP client failed: {}", httpException.getMessage());

// RỦI RO: DTO.toString() có thể in email/token/card data.
logger.error("Checkout request failed: {}", requestDto);
```

Một stack trace có thể hữu ích, nhưng message của Throwable và nested causes đôi khi chứa URL, response body hoặc payload. **Không coi `logger.error("...", exception)` là an toàn tuyệt đối** chỉ vì tham số là Throwable.

- [ ] Có safe code và boundary phù hợp để quy nhóm lỗi.
- [ ] Không log raw request/response body hoặc secret trong exception.
- [ ] Không có stack trace lặp trên mọi retry/tầng.
- [ ] Nếu có retry, event có `attempt`/`max_attempts` hoặc equivalent khi cần.
- [ ] Lỗi đã xử lý thành công bằng fallback không bị báo ERROR như outage nếu policy không yêu cầu.
- [ ] Khi cần full trace, chỉ ghi vào sink có quyền và cơ chế redaction được kiểm thử.
- [ ] Test trường hợp exception message chứa canary giả.

## 12. Checklist bảo mật: dữ liệu tuyệt đối không đưa vào log mặc định

**Nhóm dữ liệu cần loại ở nguồn:**

1. Password, OTP, MFA seed, recovery code, reset password token.
2. `Authorization`/Bearer token/JWT/access token/refresh token.
3. Cookie, Set-Cookie, session identifier, CSRF secret, private/API key.
4. PAN, CVV, payment credentials và dữ liệu thanh toán không cần thiết.
5. Raw request/response body của endpoint nhạy cảm.
6. Query/path chứa token, email, bệnh án hoặc ID riêng tư.
7. Chữ ký webhook, webhook secret hoặc full URL có signed query.
8. Nhiều trường PII không được phê duyệt như email, phone, địa chỉ, hồ sơ cá nhân.
9. Secret từ configuration/environment exception, SQL bind parameters.
10. Headers như `Referer`, `User-Agent` hoặc forwarded headers chưa được kiểm soát, có thể mang dữ liệu ngoài ý muốn.

**Checklist security bắt buộc:**

- [ ] **Field allowlist** được ưu tiên so với regex blacklist cho raw object.
- [ ] Không có raw body/header/query/URI trên auth/token/payment/reset routes.
- [ ] Endpoint lạ dùng `UNMATCHED`/route class an toàn, không fallback raw URL.
- [ ] Error handler/HTTP client/framework DEBUG không phát sinh secret.
- [ ] Token trong log đã lưu không “được an toàn” chỉ nhờ dashboard masking.
- [ ] Nếu cần pseudonymization, có đánh giá re-identification và mục đích xử lý.
- [ ] Event security/audit có actor/outcome lấy từ nguồn đã xác thực.
- [ ] Có test canary qua app file/stdout/collector/index/export trong phạm vi cho phép.
- [ ] Có cách xử lý token lộ: revoke/rotate và bảo toàn bằng chứng theo policy.

**Đừng đánh đồng “chưa thấy secret” với “đã kiểm thử mọi nguồn”.** Tomcat access log, gateway, Java HTTP client, APM và collector có thể ghi khác với SLF4J application logger.

## 13. Checklist kiểm soát dữ liệu từ client và log forging

Một attacker có thể cố chèn newline hoặc ký tự điều khiển vào header, query hoặc message để tạo dòng giả:

```text
X-Request-ID: req-123\n2026-11-10 ERROR admin granted
```

Nếu formatter text không neutralize dữ liệu này, người đọc có thể hiểu nhầm thành hai bản ghi độc lập. JSON encoder chuẩn escape CR/LF trong string, nhưng log forging còn có thể xuất hiện khi event bị export sang CSV/HTML/terminal.

- [ ] Không dùng string input làm field name, logger name hoặc file path.
- [ ] Các ID/header được validation, giới hạn ký tự và độ dài.
- [ ] Chuỗi đi vào JSON được escape đúng `"`, `\`, CR/LF, tab và control chars.
- [ ] JSONL một event chiếm một dòng vật lý, kể cả message có newline logic.
- [ ] Không để stack trace raw nhiều dòng phá contract một-event-một-dòng nếu parser yêu cầu JSONL.
- [ ] Logs CSV/HTML khi export có bảo vệ theo context để tránh formula/HTML injection.
- [ ] Không in chuỗi untrusted ra terminal/ticket ở chế độ raw khi đang điều tra.
- [ ] Test malicious strings và dài bất thường ở cả success/error paths.

**Structured logging là một điều kiện thuận lợi, không tự làm dữ liệu an toàn.** Bất kỳ field giá trị nào cũng cần policy.

## 14. Checklist độ chi tiết: “đủ” không phải “mọi thứ”

Ví dụ một event checkout **đủ hữu ích**:

```json
{
  "event.name": "checkout.rejected",
  "service.name": "checkout-api",
  "http.route": "/orders/{id}/checkout",
  "http.status_code": 409,
  "duration_ms": 4,
  "error.code": "OUT_OF_STOCK",
  "outcome": "DENIED",
  "request_id": "req_102"
}
```

Không nhất thiết phải ghi full request body, object Product/Customer, nội dung response, toàn bộ HTTP headers, SQL query có bind values hoặc các frame stack trace của business rejection.

Hỏi:

- [ ] Nếu bỏ một field, điều tra có còn trả lời được câu hỏi vận hành không?
- [ ] Nếu thêm một field, có làm tăng cardinality, dung lượng hoặc rủi ro privacy không?
- [ ] Field có thể lấy từ metric/trace/query nghiệp vụ khi cần, thay vì copy mọi thứ vào log không?
- [ ] Với list/array, có giới hạn số item và độ sâu không?
- [ ] Với payload lớn, có thể log **kích thước/loại** thay vì nội dung không?
- [ ] Với retries, có thể log tổng kết/aggregation thay vì mỗi lần stack trace?
- [ ] Có nguy cơ các service cùng log trùng một request ở nhiều hop không?

**Một bản ghi “rất đầy đủ” nhưng gây disk-full hoặc lộ secret là một bản ghi kém chất lượng.**

## 15. Checklist structured JSON: schema, parser, kiểu dữ liệu

Một example contract:

```json
{"@timestamp":"2026-11-10T03:15:00Z","schema.version":1,"level":"INFO","service.name":"checkout-api","event.name":"checkout.completed","http.status_code":200,"duration_ms":12,"outcome":"SUCCESS","request_id":"req_101"}
```

Một số lỗi khó nhận bằng mắt:

| Lỗi | Vì sao sai? | Assertion cần có |
| --- | --- | --- |
| `"http.status_code":"200"` | Numeric aggregation bị lỗi | JSON parser: integer |
| `"duration_ms":"12"` | Type string, unit có thể sai | Numeric + range |
| `"success":"true"` | Boolean bị stringify | Boolean true/false |
| `"trace_id":null` | Không rõ thiếu hay không có trace | Contract nullable/optional |
| `"event.name"` đổi tên | Alert/filter cũ không khớp | Contract name/type test |
| Field bị lặp | Parser có thể lấy key đầu/cuối khác nhau | Strict duplicate detection khi cần |
| Một event nhiều dòng vật lý | JSONL ingest có thể reject | 1 JSON object/line |
| Nested/flat shape thay đổi | `http.status_code` khác `http.status_code` lồng object | JSON path/shape assertion |

- [ ] Event có `schema.version` khi contract yêu cầu.
- [ ] Required fields có mặt và đúng type, không chỉ `contains("status")`.
- [ ] Optional fields có semantics vắng/null nhất quán.
- [ ] Encoder output thực tế từ Logback/Log4j2/JUL được test, không chỉ mock logger.
- [ ] Không có collision giữa MDC, fluent key-value fields và các fields encoder tạo sẵn.
- [ ] Cập nhật encoder/collector có consumer contract test với dashboard/index.
- [ ] JSONL UTF-8 và exception serialization có test escaping.
- [ ] Không đổi enum level/event mà bỏ qua phiên bản schema/migration.

## 16. Checklist dành riêng cho HTTP access log

HTTP access event nên giúp trả lời request tới đâu và xử lý ra sao **mà không lộ raw URL**.

| Nội dung | Gợi ý |
| --- | --- |
| Method | `GET`/`POST` từ HTTP instrumentation, validate/normalize |
| Route | Framework matched template `/orders/{id}` hoặc category |
| Status | Integer 100–599 ở điểm completion thích hợp |
| Latency | Mili giây/giây có tên field thể hiện đơn vị |
| Request ID | Đã validate; correlation, không là user identity |
| Trace ID | Khi instrumentation thực sự có context |
| Source/hop | gateway/server/app boundary rõ để tránh đếm trùng |
| Request/response size | Chỉ số byte khi có mục đích, không body |

- [ ] Không dump `Authorization`, `Cookie`, `Set-Cookie`.
- [ ] Không ghi raw `getRequestURI()` hay query cho endpoint chứa token/PII.
- [ ] Dùng route template/class cho endpoint chưa match.
- [ ] Phân biệt response status tại filter `finally` với status cuối của request async/SSE.
- [ ] Container access log (Tomcat), gateway và app filter có owners riêng.
- [ ] Một event HTTP 401 không được tự chuyển thành “password sai” nếu auth system chưa kết luận.
- [ ] Metrics HTTP không dùng request ID, token hoặc raw URL làm metric label.

## 17. Checklist dành cho security/audit events

**Security event** thường trả lời xác thực/phân quyền có thành công không; **audit event** trả lời ai thực hiện hành động gì trên tài nguyên nào với kết quả nào. Chúng có yêu cầu khác application DEBUG log.

Một event audit có thể là:

```json
{
  "event.name": "role.granted",
  "actor.type": "USER",
  "actor.id": "user_42",
  "target.type": "USER",
  "target.id": "user_91",
  "outcome": "COMMITTED",
  "operation_id": "op_19"
}
```

Checklist:

- [ ] Actor là **principal đã xác thực**, không phải username/email do client tự khai.
- [ ] Tách `actor`, `executor/service`, `initiated_by`, `target` khi có delegation/job.
- [ ] Action/target/outcome lấy từ business state đáng tin.
- [ ] Đúng mốc transaction commit; `202 Accepted` không đánh dấu completed.
- [ ] Có event ID/operation ID để đối soát retry/duplicate khi cần.
- [ ] Access, retention, legal hold, integrity và quyền export được quy định.
- [ ] Không log token/OTP/secret để “đủ bằng chứng”.
- [ ] Audit bắt buộc không chỉ tồn tại trong async debug queue có thể discard.
- [ ] Nếu dùng outbox, sự kiện có thể gửi lại; consumer có idempotency/dedup policy.
- [ ] Khi audit sink hỏng, hành vi nghiệp vụ được quyết định bằng chính sách rõ, không âm thầm mất event.
- [ ] Test các trường hợp anonymous, service account, impersonation và async job.
- [ ] Không bịa actor/outcome khi tái dựng sự kiện quá khứ.

**Một JSON event đẹp không thay thế được audit integrity.** Event có thể hợp schema nhưng có actor/outcome sai hoặc biến mất trước khi lưu.

## 18. Checklist background job, retry và async

Với scheduler, queue worker hoặc `CompletableFuture`:

- [ ] Log đủ `job_id`/`operation_id`/`attempt` để tìm workflow qua nhiều lần thử.
- [ ] Có sự phân biệt `queued`/`started`/`retry_scheduled`/`completed`/`failed`.
- [ ] Outcome không bị ghi “completed” ngay khi gọi `submit`.
- [ ] Retried request không được tính như giao dịch mới nếu nghiệp vụ dùng idempotency key.
- [ ] Executor identity là service account; human initiator chỉ khi liên kết đã xác minh.
- [ ] Correlation metadata được truyền qua message header/DTO an toàn, không chở token để log.
- [ ] MDC được snapshot/restore theo scope worker, không rò qua thread pool.
- [ ] Lỗi timeout/poison message và DLQ có event reason code an toàn.
- [ ] Số lượng retries/lag nên có metric, tránh spam lỗi ở mỗi vòng.
- [ ] Nếu async logger sink chậm, event có thể chờ/drop; phải biết policy.

Một event `job.accepted` và event `job.completed` có **hai thời điểm và có thể hai trace context khác nhau**; dùng `operation_id` để liên kết dài hạn, không giả định chỉ cần cùng một thread-local.

## 19. Checklist về event cardinality, kích thước và hiệu năng

**Tính chất “có ích” của một event cũng phụ thuộc chi phí vận hành.**

- [ ] Tần suất event/s ở INFO/WARN/ERROR đã được ước tính dưới tải bình thường và burst.
- [ ] Không log object graph sâu, file binary hoặc JSON payload rất lớn.
- [ ] Không serialise expensive DTO khi logger level đang disabled.
- [ ] Không gọi logger trong tight loop với nội dung trùng nếu không thực sự cần.
- [ ] Dùng rate limit/sampling có đánh giá tác động thống kê, tách khỏi audit bắt buộc.
- [ ] Trường phục vụ metrics được giữ low-cardinality.
- [ ] Có giới hạn message/stacktrace length và kiểm thử oversized inputs.
- [ ] Biết queue của AsyncAppender đầy sẽ block hay discard và ảnh hưởng tới p99.
- [ ] Có metric dropped events, sink errors, backlog và ingest lag.
- [ ] Khi bật DEBUG tạm, có rollback owner và timebox; privacy rules vẫn áp dụng.

**Không kết luận “async logger nhanh hơn nên luôn tốt hơn”.** Hàng đợi đầy có thể chặn request hoặc bỏ log. Appender/collector thành công cục bộ cũng chưa chứng minh backend đã indexed toàn bộ dữ liệu.

## 20. Java 17 chạy độc lập: tự kiểm “nội dung log đạt checklist”

Ví dụ sau dùng **JDK 17 thuần** và **java.util.logging (JUL)**, không cần Maven, SLF4J hay Spring. Mục đích không phải viết JSON encoder production mới mà tạo **một bộ quy tắc kiểm tra nội dung event**:

- Hai sự kiện `checkout.completed` và `checkout.rejected` được tạo với schema allowlist.
- Có `event.name`, `level`, timestamp, service, trusted route, numeric status/duration, outcome, request ID và trace ID.
- Chuỗi canary giả nằm trong request input nhưng **không được đưa vào event**.
- Sự kiện thành công và bị từ chối có level/outcome/error code phù hợp.
- `validate` từ chối missing required field, wrong type và field cấm ngoài allowlist.
- `json` là serializer tối giản cho String/Integer/Long/Boolean; message có newline được escape.
- Dùng JUL Logger + custom Handler để kiểm cả **logger thực sự đã phát event**; stdout chỉ báo PASS cố định.

**Lưu ý:** code không tạo HTTP server, không ghi file, không gửi collector, không bảo đảm audit delivery hoặc semantics ngoài mô hình giả. Serializer chỉ phục vụ bài học, không xử lý mọi Unicode surrogate/nested JSON; ứng dụng thật nên dùng encoder JSON chuyên dụng và test parse bằng thư viện như Jackson.

Tạo file **`LogContentChecklistDemo.java`**:

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogContentChecklistDemo {
    private static final Set<String> REQUIRED = Set.of(
            "@timestamp", "schema.version", "level", "service.name",
            "event.name", "http.route", "http.status_code",
            "duration_ms", "outcome", "request_id", "trace_id",
            "message");

    private static final Pattern REQUEST_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");
    private static final Pattern TRACE_ID =
            Pattern.compile("[0-9a-f]{32}");

    record Input(
            String requestId,
            String traceId,
            String authorization,
            String requestBody) {}

    private static Map<String, Object> create(
            Input input,
            String eventName,
            int status,
            long elapsedMs,
            String message) {

        boolean completed = "checkout.completed".equals(eventName);
        boolean rejected = "checkout.rejected".equals(eventName);
        if (!completed && !rejected) {
            throw new IllegalArgumentException("Unknown event");
        }

        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("@timestamp", "2026-11-10T03:15:00Z");
        fields.put("schema.version", 1);
        fields.put("level", completed ? "INFO" : "WARNING");
        fields.put("service.name", "checkout-api");
        fields.put("event.name", eventName);
        fields.put("http.route", "/orders/{id}/checkout");
        fields.put("http.status_code", status);
        fields.put("duration_ms", elapsedMs);
        fields.put("outcome", completed ? "SUCCESS" : "DENIED");
        fields.put("request_id", input.requestId());
        fields.put("trace_id", input.traceId());
        fields.put("message", message);
        if (rejected) {
            fields.put("error.code", "OUT_OF_STOCK");
        }

        // Không đọc input.authorization() hay input.requestBody().
        validate(fields);
        return fields;
    }

    private static String text(Map<String, Object> fields, String key) {
        Object value = fields.get(key);
        if (!(value instanceof String s) || s.isBlank()) {
            throw new IllegalArgumentException("Bad string field: " + key);
        }
        return s;
    }

    private static void validate(Map<String, Object> fields) {
        Set<String> allowed = new HashSet<>(REQUIRED);
        if (fields.containsKey("error.code")) {
            allowed.add("error.code");
        }
        if (!fields.keySet().equals(allowed)) {
            throw new IllegalArgumentException("Bad set of fields");
        }

        Instant.parse(text(fields, "@timestamp"));
        if (!(fields.get("schema.version") instanceof Integer version)
                || version != 1) {
            throw new IllegalArgumentException("Bad schema version");
        }
        if (!"checkout-api".equals(text(fields, "service.name"))) {
            throw new IllegalArgumentException("Bad service");
        }
        if (!"/orders/{id}/checkout".equals(
                text(fields, "http.route"))) {
            throw new IllegalArgumentException("Bad route");
        }
        if (!REQUEST_ID.matcher(
                text(fields, "request_id")).matches()) {
            throw new IllegalArgumentException("Bad request ID");
        }
        if (!TRACE_ID.matcher(
                text(fields, "trace_id")).matches()) {
            throw new IllegalArgumentException("Bad trace ID");
        }
        if (!(fields.get("http.status_code") instanceof Integer status)
                || !(fields.get("duration_ms") instanceof Long duration)
                || duration < 0L) {
            throw new IllegalArgumentException("Bad numeric fields");
        }
        if (text(fields, "message").length() > 120) {
            throw new IllegalArgumentException("Message too long");
        }

        String event = text(fields, "event.name");
        String level = text(fields, "level");
        String outcome = text(fields, "outcome");
        if ("checkout.completed".equals(event)) {
            if (status != 200 || !"INFO".equals(level)
                    || !"SUCCESS".equals(outcome)
                    || fields.containsKey("error.code")) {
                throw new IllegalArgumentException("Bad completion");
            }
        } else if ("checkout.rejected".equals(event)) {
            if (status != 409 || !"WARNING".equals(level)
                    || !"DENIED".equals(outcome)
                    || !"OUT_OF_STOCK".equals(
                            text(fields, "error.code"))) {
                throw new IllegalArgumentException("Bad rejection");
            }
        } else {
            throw new IllegalArgumentException("Unknown event");
        }
    }

    private static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        String hex = Integer.toHexString(c);
                        out.append("\\u")
                                .append("0".repeat(4 - hex.length()))
                                .append(hex);
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static String json(Map<String, Object> fields) {
        validate(fields);
        StringBuilder out = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> field : fields.entrySet()) {
            if (!first) {
                out.append(',');
            }
            first = false;
            out.append(quote(field.getKey())).append(':');
            Object v = field.getValue();
            if (v instanceof String s) {
                out.append(quote(s));
            } else if (v instanceof Integer || v instanceof Long
                    || v instanceof Boolean) {
                out.append(v);
            } else {
                throw new IllegalArgumentException("Unsupported type");
            }
        }
        return out.append('}').toString();
    }

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    private static void expectInvalid(Map<String, Object> event) {
        try {
            validate(event);
            throw new AssertionError("Invalid event accepted");
        } catch (IllegalArgumentException expected) {
            // Điều kiện không hợp lệ phải bị từ chối.
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.content.checklist");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        List<String> captured = new ArrayList<>();
        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    captured.add(record.getMessage());
                }
            }
            @Override public void flush() {}
            @Override public void close() {}
        };
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        String canary = "FAKE_SECRET_CANARY_508";
        Input first = new Input(
                "req_101", "4bf92f3577b34da6a3ce929d0e0e4736",
                "Bearer " + canary, "password=" + canary);
        Input second = new Input(
                "req_102", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "Bearer " + canary, "card=" + canary);

        try {
            Map<String, Object> good = create(
                    first, "checkout.completed", 200, 12L,
                    "Checkout\ncompleted");
            Map<String, Object> rejected = create(
                    second, "checkout.rejected", 409, 4L,
                    "Inventory rejected checkout");

            logger.log(Level.INFO, json(good));
            logger.log(Level.WARNING, json(rejected));

            check(captured.size() == 2, "Wrong event count");
            check(good.get("http.status_code") instanceof Integer,
                    "Status must be integer");
            check(good.get("duration_ms") instanceof Long,
                    "Duration must be long");
            check(good.get("outcome").equals("SUCCESS"),
                    "Incorrect outcome");
            System.out.println("PASS 1: event schema and meaning");

            String line = captured.get(0);
            check(line.contains("\"http.status_code\":200"),
                    "Numeric JSON missing");
            check(line.contains("\"message\":\"Checkout\\ncompleted\""),
                    "Newline escape missing");
            check(line.indexOf('\n') < 0 && line.indexOf('\r') < 0,
                    "JSONL physical newline found");
            System.out.println("PASS 2: JSONL values and escaping");

            Map<String, Object> missing = new LinkedHashMap<>(good);
            missing.remove("request_id");
            expectInvalid(missing);

            Map<String, Object> wrongType = new LinkedHashMap<>(good);
            wrongType.put("http.status_code", "200");
            expectInvalid(wrongType);

            Map<String, Object> extra = new LinkedHashMap<>(good);
            extra.put("authorization", first.authorization());
            expectInvalid(extra);
            System.out.println("PASS 3: missing, type and extra fields");

            check(!captured.get(0).contains(canary)
                    && !captured.get(1).contains(canary),
                    "Secret canary leaked");
            check(captured.get(0).contains("\"request_id\":\"req_101\"")
                    && !captured.get(0).contains("req_102"),
                    "First ID wrong");
            check(captured.get(1).contains("\"request_id\":\"req_102\"")
                    && !captured.get(1).contains("req_101"),
                    "Second ID wrong");
            System.out.println("PASS 4: privacy and correlation");
            System.out.println("ALL CONTENT CHECKS PASSED");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 LogContentChecklistDemo.java
java LogContentChecklistDemo
```

**Stdout chính xác nếu mọi assertion đều thành công:**

```text
PASS 1: event schema and meaning
PASS 2: JSONL values and escaping
PASS 3: missing, type and extra fields
PASS 4: privacy and correlation
ALL CONTENT CHECKS PASSED
```

**Giải thích kết quả:**

- Event đầu mang status `200`, INFO, `SUCCESS`, duration kiểu `Long`; event sau status `409`, JUL `WARNING`, `DENIED` và `OUT_OF_STOCK`.
- `Logger` thật có handler capture, nên ví dụ kiểm được hai event đã qua level filtering trong JUL; không chứng minh backend tập trung đã nhận.
- Input có token và body chứa `FAKE_SECRET_CANARY_508` nhưng builder không đọc chúng để ghi event.
- Missing required field, sai type và field ngoài allowlist được thử như các case **phải fail validation**.
- Newline trong `message` được escape thành `\n` trong JSON, không tạo thêm dòng vật lý trong JSONL.
- Hai request ID khác nhau và log không lẫn ID. **Điều này không thay concurrent MDC/ThreadLocal isolation test** khi tích hợp web/async.
- Serializer chỉ xử lý type hữu hạn và **không phải trình serialize JSON production tổng quát**; integration test phải dùng actual encoder và JSON parser như Jackson.
- Timestamp được cố định để kết quả kiểm thử ổn định, không phải cách tạo timestamp trong môi trường chạy thật.
- Event `rejected` đại diện **business rejection**, không có nghĩa security authorization denial.

## 21. Checklist tích hợp SLF4J, Logback, Log4j2 và JUL

Bài Java 17 ở trên mô phỏng nội dung log bằng JUL; khi chuyển sang thư viện production, phải test **effective output**:

| Tầng | Các câu hỏi kiểm |
| --- | --- |
| SLF4J facade | Có đúng logger name, level và key-value pairs không? |
| Logback | Appender/encoder có serialize MDC/fields? Có duplicated keys? |
| Log4j2 | JSON Template Layout và configuration đúng shape mong muốn? |
| JUL | Logger level và Handler level/filter đều cho phép event? |
| Spring Boot | Structured format tương thích phiên bản, custom config có override? |
| HTTP server | Tomcat/Jetty access log có source độc lập không? |
| Collector | Parser có giữ numeric/boolean types và route đúng index? |
| Backend | Query theo event/trace ID đúng, retention và access control hợp lệ? |

SLF4J 2.x có **fluent logging API**:

```java
// Trích đoạn tích hợp: cần SLF4J 2.x và logger/backend phù hợp.
logger.atInfo()
      .addKeyValue("event.name", "checkout.completed")
      .addKeyValue("http.status_code", 200)
      .addKeyValue("duration_ms", 12L)
      .addKeyValue("outcome", "SUCCESS")
      .log("Checkout completed");
```

**Không giả định** `addKeyValue` tự biến thành top-level JSON fields giống như demo: backend/layout có thể chỉ in text `key=value`, lồng vào object khác hoặc không giữ đúng type. Để nghiệm thu, capture **actual emitted line**, parse bằng Jackson và kiểm hợp đồng.

Khi dùng Logback `ListAppender`, nó giúp kiểm event trước encoder. Muốn kiểm JSON field thì phải capture sau **encoder thực**. Với async logger, chờ drain bằng cơ chế đồng bộ/lifecycle phù hợp trước assertion, không chỉ ngủ cố định rồi đo may rủi.

## 22. Checklist áp dụng trong Spring MVC / WebFlux

Với HTTP service:

- [ ] Có nơi phát access event sau khi request xử lý ở boundary được định nghĩa.
- [ ] Nếu là Servlet filter, biết khi nào `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` sẵn có.
- [ ] Request bị security layer từ chối trước MVC có thể không có matched route; fallback generic an toàn.
- [ ] Không nhầm `OncePerRequestFilter` với `WebFilter` của WebFlux.
- [ ] Async dispatch/SSE/streaming cần callback hoàn tất khi yêu cầu status/duration cuối.
- [ ] Không log body qua `CommonsRequestLoggingFilter`/debug framework mặc định trên login/token/payment.
- [ ] Proxy/gateway/Tomcat access log có thể xuất raw path/query dù app logger đã lọc.
- [ ] MDC/trace propagation qua `@Async`, thread pools, HTTP clients được cấu hình và test.
- [ ] Không gán actor từ header `X-User-ID` chưa xác minh.
- [ ] Có request ID/trace ID đúng trong event tại điểm tìm kiếm cần thiết.
- [ ] Alerting dựa trên event code/level/outcome ổn định, không regex câu message tự do.

**Đừng bỏ access/security event quan trọng chỉ để chặn payload.** Có thể ghi metadata an toàn mà không đọc raw request.

## 23. Checklist unit tests cho nội dung

| Kiểm thử | PASS khi |
| --- | --- |
| Event name | Tên thuộc catalog, không dynamic |
| Required fields | Đủ trường cho event class |
| Wrong type | `"200"` bị từ chối khi cần integer |
| Invalid duration | Âm hoặc unit sai bị phát hiện |
| Timestamp | Parse được ISO-8601 UTC/offset |
| Missing context | Có policy vắng mặt, không bịa fake trace |
| Wrong actor/tenant | Không nhận ID chưa xác thực |
| Unexpected field | Không tự serialize toàn DTO |
| Sensitive canary | Không xuất trong bất kỳ field/message nào |
| Outcome timing | Chưa commit không ghi COMMITTED |
| Retry | Attempt và operation ID không lẫn |
| Exception | Safe code, không log secret từ Throwable |
| Oversized input | Bị giới hạn/không dump |
| Control chars | JSONL escape đúng, không log forging |
| Disabled DEBUG | Không gọi formatter expensive khi không cần |

**Lưu ý về kiểm thử:** một `assertFalse(log.contains(secret))` trên **một** dòng không đủ chứng minh source khác an toàn; nhưng là unit/regression test hữu ích và nhanh. Cần kết hợp kiểm tra schema/field selection và pipeline end-to-end.

## 24. Checklist integration tests cho output thực

- [ ] Capture output của encoder/layout thực tế đang dùng, không chỉ mock API logger.
- [ ] Parse từng dòng JSON bằng parser độc lập như Jackson; kiểm object shape.
- [ ] Kiểm `isIntegralNumber()` trước `asInt()`/`intValue()`, tránh type coercion che lỗi.
- [ ] Kiểm field required/optional và numeric/boolean/enum/units.
- [ ] Kiểm escaping quote/backslash/CRLF/Unicode và một event trên một dòng.
- [ ] Kiểm event không có duplicate key hoặc collision với fields mặc định.
- [ ] Kiểm INFO/WARN/ERROR bị filter hay đi đúng appender theo cấu hình thật.
- [ ] Kiểm MDC của request A/B không lẫn khi thread pool chạy lại.
- [ ] Kiểm output khi exception/stack trace có message chứa canary.
- [ ] Kiểm queue async drain đúng trước assert số event và dropped policy.
- [ ] Nếu file rolling, thử rollover/retention trên test directory, không trên production.
- [ ] Nếu backend parse nested fields, assertion dùng đúng JSON path/schema.
- [ ] Khi nâng cấp encoder/framework, chạy lại contract test.

Ví dụ **trích đoạn JUnit 5 + Jackson** để kiểm actual JSON line từ test fixture:

```java
// line phải do fixture lấy từ encoder thực, không tự dựng lại bằng giả lập.
com.fasterxml.jackson.databind.JsonNode root =
        new com.fasterxml.jackson.databind.ObjectMapper().readTree(line);

org.junit.jupiter.api.Assertions.assertTrue(root.isObject());
org.junit.jupiter.api.Assertions.assertEquals(
        "checkout.completed", root.path("event.name").asText());
org.junit.jupiter.api.Assertions.assertTrue(
        root.path("http.status_code").isIntegralNumber());
org.junit.jupiter.api.Assertions.assertEquals(
        200, root.path("http.status_code").intValue());
org.junit.jupiter.api.Assertions.assertTrue(
        root.path("duration_ms").isIntegralNumber());
org.junit.jupiter.api.Assertions.assertFalse(
        line.contains("FAKE_SECRET_CANARY_508"));
```

Đây là snippet **không biên dịch độc lập** vì còn phụ thuộc `line`, JUnit 5 và Jackson. Nó minh họa điểm khác biệt giữa **schema test** và tìm chuỗi đơn thuần.

## 25. Checklist E2E: log đến đúng nơi và còn tìm được

Từ góc nhìn hệ thống:

1. [ ] Log có mặt ở source stdout/file với một event ID kiểm thử **không chứa secret**.
2. [ ] Collector nhận đủ event test theo semantics đo được; queue/retry có metric.
3. [ ] Parser giữ type, field names, JSON shape và timestamps.
4. [ ] Backend index đúng environment/service/tenant.
5. [ ] Query theo event name/ID/trace ID trả đúng dữ liệu trong SLO.
6. [ ] Có đánh giá duplicate/replay/drop khi collector retry.
7. [ ] Dashboard và alert không bị phụ thuộc vào message text dễ thay đổi.
8. [ ] Retention của file/node/backend/archive khác nhau được ghi rõ.
9. [ ] Export/snapshot/backup có quyền và vòng đời dữ liệu phù hợp.
10. [ ] Có cảnh báo khi log ingestion lag hoặc sink error tăng.
11. [ ] Security/audit events có quy định độ bền riêng.
12. [ ] Có runbook nếu dashboard trống nhưng source vẫn ghi.

**Không dùng kết quả query không có log làm chứng minh event bị mất.** Kiểm timezone, time window, quyền, index alias, ingestion lag và parser trước khi phân loại đã mất.

## 26. Những lỗi nội dung log thường gặp và cách sửa

| Anti-pattern | Hệ quả | Cách sửa |
| --- | --- | --- |
| `logger.info("Done")` | Không biết hoàn thành gì | `event.name` + status/outcome |
| Ghi SUCCESS trước commit | Sai audit trail | Phát sau điểm xác nhận outcome |
| Mọi HTTP 4xx là ERROR | Alert fatigue | Level theo impact và event class |
| Full request/body trong message | Lộ token/PII, volume lớn | Allowlisted fields |
| Raw URL có reset token | Secret trong path/query | Trusted route template/class |
| `duration_ms` lưu nanoseconds | Số đo sai hàng triệu lần | Unit conversion và test |
| `http.status_code` là string | Histogram/aggregation lỗi | JSON number contract |
| Không có request ID | Không tìm được request liên quan | ID hợp lệ tại edge và propagation |
| Dùng trace ID làm user ID | Sai security attribution | Verified principal |
| `MDC.put` không restore | Rò tenant/request giữa threads | Scope + finally |
| Throwables chứa raw HTTP response | PII lộ qua stack trace | Safe codes và policy exception |
| Log cùng exception ở bốn tầng | Tốn dung lượng, alert trùng | Owner cho boundary |
| Async queue drop INFO âm thầm | Mất khả năng điều tra | Metrics/policy và sink đúng |
| Chỉ test mock logger | Không phát hiện JSON type drift | Test encoder/collector thực |
| Đổi event code tùy ý | Dashboard/filter hỏng | Catalog + schema version |
| DEBUG eager formatting | CPU/alloc tốn khi level tắt | Guard/supplier phù hợp |
| Dùng dynamic event name | Cardinality cao | Enum event + ID ở field riêng |
| Lỗi business thường xuyên bị WARN | Người trực bị nhiễu | Severity policy đúng |
| Log không giới hạn kích thước | Disk đầy, collector lag | Bounded data, rolling/retention |
| Mất log thì dump mọi thứ | Tăng outage và rò bí mật | Triaging theo từng pipeline chặng |

## 27. Bảng đánh giá chất lượng có thể áp dụng cho code review

Có thể dùng một **scorecard gợi ý** cho mỗi event:

| Tiêu chí | Điểm gợi ý |
| --- | ---: |
| Sự kiện cần thiết và có purpose | 10 |
| Event code + timing/outcome đúng | 20 |
| Severity phù hợp | 10 |
| Schema field name/type/units | 15 |
| Context và trusted identity | 15 |
| Privacy/security policy | 20 |
| Testability và vận hành | 10 |
| **Tổng** | **100** |

**Không dùng tổng điểm để bỏ qua lỗi nguy hiểm.** Nếu log chứa password/token, actor sai hoặc event COMMITTED trước khi transaction commit thì **FAIL bắt buộc**, dù các mục còn lại đều tốt.

Một cách đơn giản hơn khi review:

- **Blocker:** lộ secret, sai actor/outcome, log forging, audit bắt buộc có thể mất mà không có policy.
- **Major:** thiếu correlation, event/schema/type/units sai, ERROR spam, thiếu error classification.
- **Minor:** message chưa rõ, field tùy chọn thiếu khi vẫn có cách điều tra khác, style không thống nhất.

Ngưỡng điểm và phân loại chỉ là **mẫu team process**, không phải tiêu chuẩn pháp lý hay kỹ thuật bắt buộc.

## 28. Mẫu checklist đưa vào pull request

Có thể sao chép mẫu dưới đây cho một PR thay logging. Người review nên gắn **bằng chứng test** cho từng câu, thay vì chỉ tick cho đủ.

```markdown
### Logging content review

- [ ] Event này có mục đích troubleshooting/security/audit rõ ràng.
- [ ] Event name thuộc catalog, đúng mốc nghiệp vụ.
- [ ] Level phản ánh impact, không tạo ERROR/WARN spam.
- [ ] Outcome, HTTP status, error code và thời điểm commit đúng.
- [ ] Required structured fields đủ, type và units đúng.
- [ ] Request/trace/operation ID tin cậy, context không lẫn.
- [ ] Actor/tenant từ verified security context nếu có.
- [ ] Không ghi token, password, OTP, cookie, card, raw body/query.
- [ ] Message/exception đã được sanitize và giới hạn kích thước.
- [ ] JSONL escape đúng và không chứa log forging.
- [ ] Test actual encoder output (type/shape/escape).
- [ ] Test canary giả và ít nhất một negative case.
- [ ] Async queue/sink/collector/retention có owner và policy.
- [ ] Dashboard/alert consumer vẫn tương thích sau schema change.

Evidence:
- Test commands and results:
- Log event sample (sanitized):
- Schema version:
- Event owner:
- Known limitations / operational follow-up:
```

Các trường `Evidence` trong mẫu PR là **mẫu để người học điền khi review thật**, không phải dấu TODO trong bài hoặc dữ liệu hệ thống đã kiểm thử.

## 29. Danh sách kiểm tra trước release

- [ ] Có danh mục event của service, với owner và schema version.
- [ ] Các sự kiện INFO/WARN/ERROR có mục đích rõ, không ghi trùng quá nhiều.
- [ ] Timestamp UTC, status number, duration có đơn vị và outcome nhất quán.
- [ ] Structured JSONL được parse bởi encoder/backend thật; không chỉ là chuỗi dựng trong unit test.
- [ ] Correlation IDs được validate/propagate, không rò giữa request hoặc tenant.
- [ ] Event cho async job không nói completed trước completion.
- [ ] Security/audit event lấy actor/outcome đáng tin, bảo toàn theo chính sách.
- [ ] Không có raw secrets, body, headers, query hoặc URL có token.
- [ ] Exception và HTTP client logs đã qua privacy test.
- [ ] Test có canary/CRLF/Unicode/oversized payload và failure paths.
- [ ] Không có field name/type drift làm hỏng dashboard hoặc alert.
- [ ] Event/log volume phù hợp capacity, AsyncAppender overflow policy được biết.
- [ ] File/stdout/collector/backend có rotation/retention/queue health theo owner.
- [ ] DEBUG tạm trên production có scope/expiry/rollback.
- [ ] Người trực có thể tra cứu log qua event name + request/trace/operation ID.
- [ ] Runbook phân biệt log bị filtered, delayed, dropped và chưa indexed.
- [ ] Báo cáo test PASS/FAIL và giới hạn chưa kiểm chứng được ghi trung thực.

**Ghi nhớ:** checklist tốt không hỏi “đã gọi `logger.info` chưa?” mà hỏi **“event này có cần thiết, có đúng thời điểm, đúng độ nghiêm trọng, đúng trường và kiểu dữ liệu, có đủ correlation, không lộ bí mật, và có thể được kiểm chứng từ đầu đến cuối không?”**. Một dòng log chỉ có giá trị khi người vận hành có thể **tin vào ý nghĩa của nó** mà không phải trả giá bằng rủi ro bảo mật hoặc mất ổn định production.

### Tài liệu tham khảo

- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [MITRE — CWE-117: Improper Output Neutralization for Logs](https://cwe.mitre.org/data/definitions/117.html)
- [SLF4J — User Manual and Fluent Logging API](https://www.slf4j.org/manual.html)
- [Logback — Manual: Appenders](https://logback.qos.ch/manual/appenders.html)
- [Logback — Manual: Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html)
- [Apache Log4j — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html)
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [Java 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
