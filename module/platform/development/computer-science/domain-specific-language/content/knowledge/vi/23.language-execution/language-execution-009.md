# Quan sát và ghi log

## 1. Observability trong thực thi DSL

Một DSL (*Domain-Specific Language*) thường được thực thi bởi interpreter, virtual machine, rule engine hoặc workflow runtime. Khi một chương trình DSL chạy, người vận hành cần biết nó đã đi qua những bước nào, vì sao một rule được chọn, dữ liệu nào dẫn đến kết quả, thời gian được tiêu thụ ở đâu và lỗi phát sinh tại vị trí nào.

**Quan sát hệ thống (*observability*)** là khả năng suy ra trạng thái và hành vi bên trong của hệ thống từ những tín hiệu mà hệ thống phát ra. Trong runtime DSL, observability giúp trả lời các câu hỏi như:

- Lần thực thi nào đang chạy và chạy trên phiên bản DSL nào?
- Rule hoặc workflow step nào đã được đánh giá?
- Điều kiện của rule cho kết quả true hay false?
- Hành động nào đã được gọi và mất bao lâu?
- Dữ liệu nào được đọc hoặc thay đổi?
- Vì sao execution thất bại, bị retry, timeout hoặc bị hủy?
- Một request chậm do parser, semantic evaluation, host service hay database?
- Người dùng hoặc hệ thống nào đã thay đổi rule và triển khai phiên bản đó?

Ba tín hiệu thường được dùng là **logs, metrics và traces**:

| Tín hiệu | Trả lời câu hỏi | Ví dụ trong DSL |
|---|---|---|
| Logs | Điều gì đã xảy ra tại một thời điểm? | Rule discount-rule được đánh giá và trả false |
| Metrics | Hành vi thay đổi theo thời gian ra sao? | Số lần chạy, tỷ lệ lỗi, p95 execution duration |
| Traces | Một request đi qua những thành phần nào? | API → DSL runtime → rule → inventory service |

Ba tín hiệu bổ sung cho nhau. Log cung cấp sự kiện chi tiết, metric cho thấy xu hướng và mức độ, trace cho biết quan hệ thời gian giữa các bước trong một lần xử lý.

Quan sát và ghi log là một phần của thiết kế runtime. Nếu chỉ bổ sung log sau khi hệ thống gặp sự cố, có thể đã thiếu execution ID, source mapping hoặc thông tin phiên bản cần thiết để tái dựng hành vi.

## 2. Phân biệt log, metric, trace và audit

### 2.1. Log

Log là bản ghi một sự kiện hoặc trạng thái tại một thời điểm. Ví dụ:

~~~json
{
  "timestamp": "2026-11-15T10:30:00Z",
  "level": "INFO",
  "event": "rule.evaluated",
  "execution_id": "exec-7f31",
  "rule_id": "large-order",
  "result": true,
  "duration_ms": 2.4
}
~~~

Log thường có timestamp, severity, event name, context và dữ liệu mô tả. Structured log lưu dữ liệu theo field để có thể lọc và truy vấn.

### 2.2. Metric

Metric là số liệu được tổng hợp theo thời gian hoặc theo nhóm. Ví dụ:

- Số lần DSL execution mỗi phút.
- Tỷ lệ execution thành công.
- Số lỗi theo rule ID.
- Thời gian đánh giá rule.
- Số lần retry.
- Độ dài queue.
- Số execution đang hoạt động.

Metric thường được lưu dưới dạng time series. Không nên tạo metric label có giá trị thay đổi liên tục như execution ID hoặc user ID vì số lượng time series có thể tăng không giới hạn (*high cardinality*).

### 2.3. Trace

Trace biểu diễn hành trình của một request hoặc execution qua nhiều component. Trace gồm các span; mỗi span có thời gian bắt đầu, kết thúc, quan hệ cha-con và metadata.

Ví dụ:

~~~text
HTTP request
  └── DSL execution
       ├── Parse / load compiled rule
       ├── Evaluate rule: eligibility
       ├── Call inventory service
       └── Evaluate rule: apply-discount
~~~

Trace giúp nhận ra thời gian bị tiêu thụ ở đâu và một lỗi downstream ảnh hưởng đến execution nào.

### 2.4. Audit record

Audit record ghi lại hành động quan trọng cần có khả năng truy cứu, ví dụ:
- Ai tạo hoặc sửa rule.
- Ai phê duyệt và triển khai phiên bản mới.
- Phiên bản nào được kích hoạt hoặc rollback.
- Ai thay đổi capability hoặc quyền.
- Một hành động nghiệp vụ nhạy cảm được yêu cầu bởi execution nào.

Audit phục vụ trách nhiệm giải trình và điều tra. Nó có yêu cầu về tính toàn vẹn, quyền truy cập và thời gian lưu khác với log vận hành thông thường.

Không nên xem log thông thường là audit trail đáng tin cậy nếu log có thể bị sửa hoặc xóa mà không có kiểm soát.

## 3. Mục tiêu quan sát ở cấp DSL runtime

Runtime nên cung cấp đủ tín hiệu để người dùng và đội vận hành hiểu hành vi mà không phải đọc toàn bộ mã nguồn implementation.

Các mục tiêu chính:

1. **Theo dõi vòng đời:** biết execution bắt đầu, kết thúc, thất bại, timeout hoặc bị hủy.
2. **Giải thích quyết định:** biết rule nào được xét, điều kiện cho kết quả gì và nhánh nào được chọn.
3. **Định vị lỗi:** liên kết exception với rule, expression, source file và line/column.
4. **Đo hiệu năng:** phân biệt thời gian parse, evaluate, gọi host function và I/O.
5. **Theo dõi side effect:** biết capability nào được gọi và kết quả ở mức được phép ghi nhận.
6. **Hỗ trợ audit:** liên kết hành động quan trọng với actor, version và execution.
7. **Phát hiện bất thường:** nhận biết error rate, timeout, retry hoặc resource usage tăng.
8. **Tái lập sự cố:** lưu đủ metadata để hiểu lại điều kiện thực thi khi sự cố xảy ra.

Mức chi tiết nên phụ thuộc môi trường. Development có thể bật trace từng expression; production thường dùng log sự kiện và trace có chọn lọc để kiểm soát chi phí và dữ liệu.

## 4. Vòng đời một lần thực thi

Một execution DSL có thể đi qua các trạng thái:

~~~text
CREATED
   |
   v
QUEUED
   |
   v
STARTED
   |
   v
RUNNING
   |--------------------|
   v                    v
SUCCEEDED             FAILED
   |
   +----> CANCELLED (nếu bị hủy trong lúc chạy)
~~~

Tùy runtime, có thể có thêm trạng thái RETRYING, TIMED_OUT, REJECTED hoặc PARTIALLY_COMPLETED. Cần định nghĩa rõ trạng thái kết thúc và chuyển trạng thái hợp lệ.

Một event log cho vòng đời:

~~~json
{"event":"execution.created","execution_id":"exec-7f31"}
{"event":"execution.started","execution_id":"exec-7f31","dsl_version":"3.2"}
{"event":"execution.succeeded","execution_id":"exec-7f31","duration_ms":18.7}
~~~

Mỗi execution nên có định danh ổn định để liên kết các event. Nếu một request tạo nhiều child execution, cần thêm parent execution ID hoặc trace ID.

### 4.1. Execution ID

Execution ID nhận diện một lần chạy cụ thể. Không dùng tên rule làm execution ID vì cùng một rule có thể được chạy đồng thời nhiều lần.

ID có thể được tạo tại API gateway hoặc DSL runtime. Nó cần được truyền qua các component và xuất hiện trong log, trace và error report.

### 4.2. Trace ID và span ID

Trace ID liên kết các span thuộc cùng một request phân tán. Span ID nhận diện một operation cụ thể. Execution ID là định danh miền DSL; Trace ID là định danh observability. Hai ID có thể được liên kết nhưng không nên mặc định là một.

### 4.3. Parent-child execution

Một workflow có thể gọi sub-workflow hoặc rule khác. Khi đó:
- Parent execution ID xác định execution gọi.
- Child execution ID xác định execution con.
- Trace parent span xác định quan hệ thời gian.
- Rule/workflow version cho biết nội dung nào được thực thi.

Điều này giúp phân biệt gọi lồng nhau với nhiều execution độc lập.

## 5. Thiết kế event model cho DSL

Thay vì ghi log bằng câu văn tùy ý ở mọi nơi, runtime nên xác định một tập event có tên và schema ổn định.

Một số event phổ biến:

| Event | Khi phát | Field hữu ích |
|---|---|---|
| execution.created | Tạo execution | execution_id, actor, request_id |
| execution.started | Bắt đầu chạy | dsl_version, runtime_version |
| execution.completed | Hoàn tất | status, duration_ms |
| execution.failed | Thất bại | error_code, phase, source_location |
| rule.matched | Pattern rule khớp | rule_id, match_count |
| rule.evaluated | Điều kiện được đánh giá | rule_id, result, duration_ms |
| step.started | Workflow step bắt đầu | step_id, attempt |
| step.completed | Step hoàn tất | step_id, duration_ms |
| capability.called | Gọi host capability | capability, duration_ms |
| state.changed | State thay đổi | entity_type, changed_fields |
| execution.cancelled | Execution bị hủy | reason, actor |
| resource.limit_exceeded | Vượt giới hạn | limit_name, observed_value |

Tên event cần nhất quán giữa phiên bản runtime. Khi đổi schema, cần version hoặc chính sách tương thích để consumer không bị hỏng.

### 5.1. Event không đồng nghĩa với log line

Một event là dữ liệu có cấu trúc và ý nghĩa ổn định. Nó có thể được gửi đến logger, tracing system, message broker hoặc audit store. Một log line chỉ là một cách xuất event.

Thiết kế event model trước giúp runtime có thể thay backend logging mà không thay đổi semantics của DSL.

### 5.2. Không ghi mọi node theo mặc định

AST có thể chứa hàng nghìn node. Ghi một log cho mọi node trong production có thể tạo lượng dữ liệu lớn, tăng latency và làm chi phí lưu trữ cao.

Nên chọn mức instrumentation:
- Execution-level events cho mọi lần chạy.
- Rule/step events cho những phần có giá trị chẩn đoán.
- Expression-level trace chỉ bật theo sampling, debug mode hoặc execution được chọn.

## 6. Structured logging

### 6.1. Vì sao cần log có cấu trúc?

Log dạng văn bản:

~~~text
Rule large-order evaluated true in 2.4ms for execution exec-7f31
~~~

dễ đọc nhưng khó truy vấn ổn định. Nếu format thay đổi, parser log có thể thất bại.

Structured log lưu field riêng:

~~~json
{
  "event": "rule.evaluated",
  "execution_id": "exec-7f31",
  "rule_id": "large-order",
  "result": true,
  "duration_ms": 2.4
}
~~~

Có thể lọc theo rule ID, đếm kết quả true/false hoặc tổng hợp thời gian mà không phải phân tích câu văn.

### 6.2. Field chuẩn

Một schema log runtime có thể gồm:

| Field | Ý nghĩa |
|---|---|
| timestamp | Thời điểm sự kiện |
| level | Mức độ nghiêm trọng |
| event | Tên event ổn định |
| service | Service hoặc runtime phát event |
| environment | dev, staging, production |
| execution_id | Lần chạy DSL |
| trace_id | Trace phân tán |
| span_id | Span hiện tại |
| parent_execution_id | Execution cha nếu có |
| dsl_version | Phiên bản ngôn ngữ hoặc module |
| rule_id | Rule đang được xử lý |
| step_id | Workflow step |
| source_uri | File hoặc resource nguồn |
| source_range | Vị trí trong source |
| duration_ms | Thời lượng |
| status | Kết quả |
| error_code | Mã lỗi ổn định |

Không phải event nào cũng cần mọi field. Schema nên yêu cầu field cốt lõi và cho phép field bổ sung có kiểm soát.

### 6.3. Context propagation

Context gồm thông tin cần truyền xuyên qua các lời gọi:
- Execution ID.
- Trace/span context.
- Tenant hoặc workspace ID ở dạng định danh được phép.
- Actor hoặc service identity.
- DSL version.
- Deadline và cancellation signal.

Khi DSL gọi host function, context nên được truyền tự động hoặc qua API rõ ràng. Không nên yêu cầu mỗi helper tự tạo lại execution ID vì có thể làm đứt liên kết log.

### 6.4. Correlation ID

Correlation ID giúp liên kết các log của một yêu cầu nghiệp vụ qua nhiều service. Nó có thể được nhận từ request header hoặc tạo tại biên hệ thống.

Cần xác thực và giới hạn độ dài của ID do client cung cấp. Không đưa trực tiếp chuỗi tùy ý vào log nếu chưa escape hoặc kiểm tra, vì có thể gây log injection.

## 7. Log level và chính sách sử dụng

Các mức thường gặp:

| Level | Dùng khi | Ví dụ |
|---|---|---|
| TRACE | Chi tiết từng bước rất nhỏ | Giá trị trung gian của expression trong debug |
| DEBUG | Thông tin phục vụ phát triển | Rule match và scope lookup |
| INFO | Sự kiện vận hành bình thường | Execution hoàn tất |
| WARN | Tình huống bất thường nhưng vẫn tiếp tục | Rule bị bỏ qua do optional field thiếu |
| ERROR | Một operation thất bại | Execution thất bại vì capability timeout |
| FATAL | Runtime không thể tiếp tục phục vụ | Runtime initialization thất bại nghiêm trọng |

Không nên ghi mọi kết quả false của rule ở mức WARN. Điều kiện false có thể là hành vi bình thường của business rule. Level phản ánh mức độ bất thường hoặc cần hành động, không phải giá trị Boolean.

Một chính sách hợp lý:
- INFO cho vòng đời execution và các hành động quan trọng.
- DEBUG cho quyết định rule và thông tin scope.
- TRACE cho expression-level details.
- WARN cho retry, fallback hoặc cấu hình thiếu có thể phục hồi.
- ERROR cho execution hoặc operation thất bại.

Mức log có thể thay đổi theo môi trường, nhưng không nên thay đổi ngữ nghĩa của chương trình.

## 8. Quan sát rule engine

Rule engine cần giải thích vì sao rule được chọn hoặc không được chọn.

Ví dụ:

~~~text
rule "eligible-customer" {
    when customer.active and customer.balance > 0
    then grantBenefit(customer)
}
~~~

Một trace chi tiết có thể ghi:
- Rule ID và version.
- Thời điểm bắt đầu đánh giá.
- Kết quả của từng predicate nếu debug được bật.
- Kết quả tổng hợp của điều kiện.
- Action được gọi hoặc bị bỏ qua.
- Thời gian đánh giá.
- Diagnostic nếu biểu thức thất bại.

### 8.1. Rule matched và rule fired

Hai khái niệm cần phân biệt:
- **Matched:** pattern hoặc điều kiện tìm kiếm dữ liệu thỏa điều kiện để rule được xem xét.
- **Fired:** action của rule thực sự được thực thi.

Một rule có thể matched nhưng không fired do guard false, priority, conflict resolution hoặc chính sách salience. Log nên thể hiện giai đoạn cụ thể để người vận hành hiểu vì sao action không chạy.

### 8.2. Giải thích điều kiện

Có thể cung cấp execution explanation:

~~~text
Rule: eligible-customer
customer.active = true
customer.balance > 0 = false
overall condition = false
action = skipped
~~~

Explanation này hữu ích khi debug rule nghiệp vụ. Tuy nhiên, giá trị dữ liệu có thể nhạy cảm; production nên ưu tiên ghi kết quả và field name, chỉ hiển thị giá trị khi được phép.

### 8.3. Priority và conflict resolution

Nếu nhiều rule cùng match, engine có thể chọn theo priority hoặc conflict set. Event nên ghi:
- Rule candidates.
- Rule được chọn.
- Lý do rule khác bị trì hoãn hoặc bỏ qua.
- Thứ tự thực thi nếu có ý nghĩa.

Không cần ghi toàn bộ candidate set ở mọi execution nếu khối lượng lớn. Có thể bật trace chi tiết cho execution được điều tra.

## 9. Quan sát workflow và state machine

Workflow có nhiều step, transition và trạng thái. Các event cần cho biết:
- Step nào bắt đầu.
- Step nào hoàn thành.
- Transition nào được chọn.
- Retry lần thứ mấy.
- Timeout deadline.
- Compensation nào được gọi.
- Workflow đang ở trạng thái nào.

Ví dụ log:

~~~json
{"event":"step.started","execution_id":"exec-91","step_id":"reserve-stock","attempt":1}
{"event":"step.completed","execution_id":"exec-91","step_id":"reserve-stock","duration_ms":34,"status":"SUCCEEDED"}
{"event":"step.started","execution_id":"exec-91","step_id":"capture-payment","attempt":1}
{"event":"step.failed","execution_id":"exec-91","step_id":"capture-payment","error_code":"PAYMENT_TIMEOUT"}
{"event":"step.started","execution_id":"exec-91","step_id":"release-stock","attempt":1,"kind":"COMPENSATION"}
~~~

### 9.1. Retry

Khi retry, cần phân biệt:
- Một execution duy nhất với nhiều attempt.
- Một step có nhiều attempt.
- Một retry mới tạo execution ID mới hay giữ ID cũ.

Thông thường có thể giữ execution ID và tăng attempt number, đồng thời tạo span mới cho từng attempt. Điều này giúp tính tỷ lệ retry và thời gian tổng.

### 9.2. Timeout và cancellation

Timeout và cancellation là hai nguyên nhân khác nhau:
- Timeout: deadline đã hết.
- Cancellation: actor hoặc parent execution yêu cầu dừng.

Log nên có reason, deadline, actor hoặc parent signal nếu có. Không nên chỉ ghi chung là execution failed.

### 9.3. Durable workflow

Workflow có thể chạy trong nhiều giờ hoặc nhiều ngày. Không nên giữ một span mở liên tục trong toàn bộ thời gian nếu tracing backend có giới hạn. Có thể tạo span theo từng segment, lưu execution state và liên kết bằng trace ID hoặc workflow ID.

## 10. Đo hiệu năng bằng metrics

### 10.1. Các metric cốt lõi

| Metric | Loại thường dùng | Ý nghĩa |
|---|---|---|
| dsl_executions_total | Counter | Tổng số execution |
| dsl_execution_failures_total | Counter | Tổng số execution thất bại |
| dsl_execution_duration_seconds | Histogram | Phân bố thời gian chạy |
| dsl_rule_evaluations_total | Counter | Số lần đánh giá rule |
| dsl_rule_duration_seconds | Histogram | Thời gian đánh giá rule |
| dsl_step_retries_total | Counter | Số lần retry step |
| dsl_active_executions | Gauge | Số execution đang chạy |
| dsl_queue_depth | Gauge | Số execution chờ |
| dsl_capability_calls_total | Counter | Số lần gọi capability |
| dsl_resource_limit_hits_total | Counter | Số lần chạm giới hạn |

Metric cần có đơn vị và semantics rõ. Ví dụ duration dùng seconds trong hệ thống metrics để dễ kết hợp và tổng hợp.

### 10.2. Counter, gauge và histogram

- **Counter:** chỉ tăng, ví dụ số execution hoàn tất.
- **Gauge:** có thể tăng hoặc giảm, ví dụ số execution đang hoạt động.
- **Histogram:** ghi phân bố quan sát, ví dụ execution duration.

Histogram cho phép tính percentile như p50, p95 và p99 tùy hệ thống. Trung bình có thể che khuất các execution rất chậm, vì vậy cần theo dõi tail latency.

### 10.3. Cardinality

Metric label nên dùng các giá trị có tập hữu hạn hoặc được kiểm soát:
- Environment.
- Runtime version.
- Result status.
- Rule group.
- Error category.

Tránh dùng execution ID, trace ID, raw user ID hoặc giá trị input làm label. Các giá trị này phù hợp hơn trong logs hoặc traces có kiểm soát.

### 10.4. SLO và alert

Một SLO có thể quy định:
- 99.9% execution hoàn tất thành công trong khoảng thời gian xác định.
- p95 duration dưới một ngưỡng.
- Tỷ lệ timeout dưới giới hạn.
- Queue delay không vượt quá thời gian cho phép.

Alert nên gắn với hành động vận hành cụ thể. Alert theo từng lỗi đơn lẻ có thể gây nhiễu; nên dùng tỷ lệ, cửa sổ thời gian và mức ảnh hưởng.

## 11. Distributed tracing và host capability

DSL runtime thường gọi service hoặc API của ứng dụng chủ. Trace giúp liên kết thời gian xử lý trong DSL với thời gian xử lý ở service ngoài.

Ví dụ:

~~~text
HTTP /orders
  └── evaluate DSL
       ├── rule: validate-order
       ├── capability: inventory.reserve
       │    └── HTTP inventory service
       └── capability: payment.capture
            └── HTTP payment service
~~~

### 11.1. Span boundaries

Nên tạo span cho operation có ý nghĩa:
- Toàn bộ DSL execution.
- Mỗi workflow step quan trọng.
- Mỗi capability call.
- Các thao tác I/O hoặc truy vấn có thời gian đáng kể.

Không nhất thiết tạo span cho mọi arithmetic expression vì overhead và số span có thể rất lớn.

### 11.2. Context propagation qua capability

Khi runtime gọi capability, truyền trace context đến client library để downstream service tiếp tục cùng trace. Nếu không truyền context, trace bị tách thành nhiều phần không liên hệ.

### 11.3. Exception và span status

Khi operation thất bại, span cần ghi status/error theo convention của tracing system. Cần giữ error code ổn định và tránh đưa toàn bộ payload nhạy cảm vào exception event.

## 12. Source mapping và execution explanation

Một runtime hữu ích cần liên kết execution data với vị trí trong DSL source.

Ví dụ:

~~~text
rules/pricing.dsl:18:9
rule "large-order"
when order.total >= threshold
     ^^^^^^^^^^^^^^^^^^^^^^^^^
~~~

### 12.1. Source span

AST node nên giữ:
- Source URI hoặc file ID.
- Start offset.
- End offset.
- Line và column.
- Có thể có mapping về macro hoặc generated source.

Khi interpreter đánh giá node, runtime có thể đính source span vào event hoặc diagnostic.

### 12.2. Compiled artifact

Nếu DSL được compile sang bytecode hoặc native code, cần debug metadata ánh xạ instruction về source node. Nếu optimizer gộp hoặc loại bỏ node, mapping có thể là nhiều-một hoặc không có vị trí trực tiếp.

### 12.3. Explain API

Runtime có thể cung cấp API trả explanation có cấu trúc:

~~~json
{
  "execution_id": "exec-7f31",
  "rule_id": "large-order",
  "decision": "FIRED",
  "condition_result": true,
  "source": {
    "uri": "rules/pricing.dsl",
    "line": 18,
    "column": 9
  },
  "duration_ms": 2.4
}
~~~

Explain API hữu ích cho UI quản trị và hỗ trợ khách hàng. Nó nên tách khỏi raw debug log để có schema ổn định và kiểm soát quyền truy cập.

## 13. Ghi log lỗi và exception

### 13.1. Error categories

Nên phân loại lỗi theo giai đoạn:
- Parse error.
- Semantic validation error.
- Type error.
- Runtime evaluation error.
- Capability error.
- Timeout.
- Cancellation.
- Resource limit exceeded.
- Internal runtime failure.

Mã lỗi nên ổn định qua các phiên bản để dashboard và automation có thể phân loại.

### 13.2. Diagnostic fields

Một error event có thể gồm:

~~~json
{
  "event": "execution.failed",
  "execution_id": "exec-7f31",
  "error_code": "DSL-CAPABILITY-004",
  "phase": "CAPABILITY_CALL",
  "rule_id": "reserve-stock",
  "source_uri": "rules/order.dsl",
  "line": 22,
  "column": 5,
  "retryable": true
}
~~~

Không nhất thiết log stack trace đầy đủ ở mọi nơi. Stack trace có thể chứa thông tin nội bộ, đường dẫn file hoặc dữ liệu nhạy cảm. Nên lưu exception detail ở nơi được kiểm soát và log reference ID.

### 13.3. Root cause và cascading errors

Một capability timeout có thể làm step thất bại, workflow thất bại và request trả lỗi. Nếu log mỗi lớp như một lỗi độc lập, dashboard có thể đếm một sự cố thành nhiều lỗi.

Nên liên kết cause chain:
- Root error code.
- Parent operation.
- Child span.
- Retry attempt.
- Final execution status.

Có thể ghi một event error gốc và các event trạng thái cấp cao hơn tham chiếu cùng cause ID.

### 13.4. Retryable và non-retryable

Error event nên cho biết có thể retry hay không theo chính sách runtime. Tuy nhiên, retry cần xét idempotency và side effect. Một payment capture đã thành công ở phía provider nhưng response bị timeout có thể không an toàn nếu gọi lại mà không có idempotency key.

## 14. Privacy và bảo vệ dữ liệu trong log

Log có thể vô tình lưu dữ liệu cá nhân, bí mật hoặc thông tin nghiệp vụ nhạy cảm. Observability cần được thiết kế theo nguyên tắc tối thiểu dữ liệu.

### 14.1. Data minimization

Chỉ ghi những field cần thiết để vận hành và điều tra. Ví dụ:
- Ghi customer reference đã được token hóa thay vì email hoặc số điện thoại.
- Ghi số lượng item thay vì toàn bộ danh sách sản phẩm.
- Ghi kết quả predicate thay vì toàn bộ object input.
- Ghi capability name và status thay vì request body.

### 14.2. Redaction và masking

Có thể dùng schema-aware redaction:
- Ẩn password, token và API key.
- Mask một phần email hoặc số tài khoản nếu thực sự cần nhận diện.
- Loại bỏ header xác thực.
- Chặn các field được phân loại secret.
- Escape newline và control characters để tránh log injection.

Redaction nên được thực hiện trước khi dữ liệu được gửi ra backend log, không chỉ ở dashboard.

### 14.3. Access control

Phân quyền theo vai trò:
- Operator xem execution status và metric.
- Developer xem diagnostics và source mapping.
- Security/audit role xem audit record.
- Người dùng tenant chỉ xem execution thuộc tenant được phép.

Không nên giả định mọi người có quyền xem log đều có quyền xem source DSL hoặc dữ liệu context.

### 14.4. Retention và deletion

Quy định:
- Thời gian lưu log vận hành.
- Thời gian lưu audit record.
- Cách xóa hoặc ẩn dữ liệu theo yêu cầu hợp lệ.
- Cách xử lý bản sao trong backup và archive.
- Cách giữ trace link khi dữ liệu chi tiết đã hết hạn.

Retention nên phù hợp mục đích và chính sách dữ liệu của hệ thống.

## 15. Log injection và dữ liệu không tin cậy

DSL source, identifier, string literal và input context có thể do người dùng cung cấp. Nếu nối trực tiếp vào log text, ký tự newline hoặc escape có thể giả mạo log entry.

Ví dụ một identifier hoặc string chứa newline có thể tạo dòng log giả nếu logger không encode đúng.

Biện pháp:
- Dùng structured logging thay vì nối chuỗi.
- Escape control characters.
- Giới hạn độ dài field.
- Chuẩn hóa encoding.
- Không đưa raw source vào log mặc định.
- Kiểm tra dữ liệu do client cung cấp trước khi dùng làm correlation ID hoặc label.
- Không cho phép source text ghi đè field hệ thống như severity hoặc timestamp.

Log backend cũng cần giới hạn quyền ghi và chống giả mạo khi audit yêu cầu tính toàn vẹn.

## 16. Sampling và kiểm soát chi phí

Trace và debug log chi tiết có thể tạo lượng dữ liệu lớn.

### 16.1. Head-based sampling

Quyết định sampling được đưa ra ở đầu trace. Ví dụ chỉ lấy một tỷ lệ nhỏ request thành công, nhưng luôn lấy request có điều kiện ưu tiên được xác định từ trước.

Ưu điểm là đơn giản và giảm chi phí sớm. Hạn chế là chưa biết request có lỗi trước khi quyết định.

### 16.2. Tail-based sampling

Quyết định sau khi trace đã có đủ dữ liệu. Có thể ưu tiên:
- Trace có error.
- Trace vượt latency threshold.
- Trace có retry nhiều lần.
- Trace thuộc nhóm điều tra.

Cách này hữu ích nhưng cần buffer và tài nguyên để giữ trace trước khi quyết định.

### 16.3. Log sampling

Có thể sample các event lặp lại có tần suất cao, nhưng cần giữ:
- Error events.
- State transitions quan trọng.
- Audit records.
- Event đánh dấu giới hạn tài nguyên.
- Một số mẫu success để có baseline.

Audit record không nên bị loại ngẫu nhiên bởi sampling nếu chính sách yêu cầu ghi đầy đủ.

### 16.4. Dynamic verbosity

Runtime có thể cho phép bật debug theo:
- Một execution ID.
- Một rule ID.
- Một tenant đã được phê duyệt.
- Một khoảng thời gian ngắn.
- Một request điều tra.

Cần có thời hạn tự tắt và giới hạn quyền để tránh vô tình bật trace chi tiết trên toàn hệ thống.

## 17. Tách log vận hành, debug và audit

Ba luồng dữ liệu có mục tiêu khác nhau:

| Loại | Mục tiêu | Đặc tính |
|---|---|---|
| Operational logs | Vận hành và xử lý sự cố | Có thể sample, retention ngắn hơn |
| Debug traces | Phân tích chi tiết execution | Có thể rất lớn, bật có chọn lọc |
| Audit records | Trách nhiệm giải trình | Toàn vẹn, kiểm soát quyền, retention theo chính sách |

Không nên dùng cùng một storage policy cho cả ba. Audit có thể cần append-only hoặc integrity protection; debug trace có thể chỉ giữ trong thời gian ngắn.

## 18. Ví dụ: structured logging cho DSL runtime

Một interface khái niệm:

~~~java
interface DslObserver {
    void onExecutionStarted(ExecutionContext context);
    void onRuleEvaluated(RuleEvent event);
    void onStepCompleted(StepEvent event);
    void onExecutionFailed(ExecutionError error);
}
~~~

Runtime phát event:

~~~java
observer.onExecutionStarted(context);

try {
    RuleResult result = engine.evaluate(rule, context);

    observer.onRuleEvaluated(
        new RuleEvent(
            context.executionId(),
            rule.id(),
            result.matched(),
            result.duration()
        )
    );
} catch (DslException error) {
    observer.onExecutionFailed(
        ExecutionError.from(context, rule, error)
    );
    throw error;
}
~~~

Đây là mã minh họa. Observer nên không làm thay đổi kết quả DSL. Nếu backend log bị lỗi, runtime cần chính sách rõ: bỏ event, buffer, retry có giới hạn hay fail execution. Thông thường, lỗi ghi log không nên làm thay đổi semantics nghiệp vụ, trừ khi event đó là audit bắt buộc và hệ thống chủ ý dùng fail-closed.

### 18.1. Observer overhead

Instrumentation có chi phí:
- Tạo event object.
- Đọc clock.
- Serialize field.
- Gửi qua queue.
- Lưu hoặc truyền network.

Nên đo overhead và dùng asynchronous exporter có bounded queue. Nếu queue đầy, cần chính sách drop hoặc backpressure rõ ràng.

### 18.2. Không làm thay đổi semantics

Observer không nên:
- Sửa biến DSL.
- Thay đổi thứ tự rule.
- Gọi lại capability.
- Giữ lock lâu làm thay đổi concurrency.
- Ném exception ngẫu nhiên vào execution path.

Nếu instrumentation có thể tác động đến thời gian hoặc thứ tự side effect, cần xem xét kỹ để tránh thay đổi hành vi quan sát được của chương trình.

## 19. Kiến trúc observability cho DSL runtime

Một kiến trúc khái niệm:

~~~text
DSL Program
    |
    v
DSL Runtime
    |
    +---- Execution Events ----> Structured Logger ----> Log Store
    |
    +---- Measurements --------> Metrics SDK ----------> Metrics Backend
    |
    +---- Spans ----------------> Tracing SDK ----------> Trace Backend
    |
    +---- Audit Events ---------> Audit Pipeline -------> Protected Store
    |
    +---- Diagnostics ----------> Error API / IDE
~~~

Các thành phần:
- **Instrumentation API:** nơi runtime phát event, metric và span.
- **Context provider:** quản lý execution ID, trace context và version.
- **Logger/exporter:** serialize và gửi log.
- **Metrics recorder:** cập nhật counter, gauge và histogram.
- **Tracer:** tạo span và liên kết parent-child.
- **Audit pipeline:** lưu sự kiện cần bảo đảm toàn vẹn.
- **Diagnostic service:** trả lỗi cho API hoặc IDE.
- **Policy layer:** áp dụng redaction, sampling, retention và access control.

Có thể dùng OpenTelemetry làm API và convention chung cho traces, metrics và logs nếu hệ sinh thái hỗ trợ. Không nhất thiết runtime phải phụ thuộc trực tiếp vào một vendor backend.

## 20. Dashboard và truy vấn vận hành

Dashboard nên trả lời câu hỏi cụ thể, không chỉ hiển thị nhiều biểu đồ.

Một số dashboard hữu ích:

### 20.1. Runtime overview

- Executions per second.
- Success/error rate.
- p50/p95/p99 duration.
- Active executions.
- Queue depth.
- Resource limit hits.

### 20.2. Rule performance

- Top rule theo tổng thời gian.
- Rule có p95 cao.
- Rule có error rate cao.
- Rule được đánh giá nhiều nhưng hiếm khi fire.
- Tỷ lệ cache hit nếu có compiled rule cache.

### 20.3. Workflow health

- Step failure rate.
- Retry count.
- Timeout count.
- Thời gian chờ giữa các step.
- Compensation execution.
- Workflow stuck hoặc quá thời hạn.

### 20.4. Error investigation

Một truy vấn điều tra thường đi từ:
1. Error code hoặc execution status.
2. Execution ID.
3. Trace ID.
4. Rule/step ID.
5. DSL version.
6. Source location.
7. Downstream capability span.

Cần giữ các field liên kết này nhất quán để chuyển từ dashboard sang log và trace mà không phải đoán.

## 21. Logging khi thực thi song song

DSL runtime có thể chạy nhiều rule hoặc workflow step đồng thời. Log cần giữ được quan hệ mà không phụ thuộc thứ tự dòng log.

Các nguyên tắc:
- Gắn execution ID và span ID cho từng event.
- Có parent-child relation.
- Dùng timestamp có độ chính xác phù hợp.
- Không giả định event đến backend theo thứ tự phát.
- Ghi attempt number và worker ID nếu cần.
- Dùng event sequence number trong một execution nếu thứ tự logic quan trọng.
- Tránh dùng một mutable logging context dùng chung giữa các thread.

Với concurrency, thứ tự timestamp có thể khác thứ tự logic do buffering hoặc clock skew. Trace parent-child và sequence metadata đáng tin cậy hơn việc chỉ sắp xếp log line theo timestamp.

## 22. Replay và tái lập sự cố

Để tái lập execution, có thể cần:
- DSL source hoặc artifact version.
- Runtime version.
- Transformation/compiler version nếu có.
- Input context đã được lưu theo chính sách dữ liệu.
- Clock hoặc timestamp logic.
- Random seed nếu dùng random.
- External response snapshot hoặc reference.
- Capability version/configuration.
- Execution policy và resource limits.

Không phải mọi execution đều nên lưu toàn bộ input. Có thể lưu hash, reference đến immutable event store hoặc dữ liệu đã được redaction.

Replay cần phân biệt:
- **Deterministic replay:** cùng input và dependency snapshot tạo cùng hành vi.
- **Diagnostic replay:** chạy lại để quan sát, có thể dùng mock hoặc sandbox.
- **Live retry:** gọi lại service thật, có thể tạo side effect mới.

Không dùng replay như retry nghiệp vụ nếu chưa kiểm soát idempotency.

## 23. Kiểm thử observability

Instrumentation cũng cần được kiểm thử để tránh log thiếu hoặc sai context.

Các loại test:
- Execution thành công phát started và completed.
- Execution thất bại phát error với đúng error code.
- Rule matched và fired được phân biệt.
- Trace ID được truyền qua capability.
- Source location đúng với AST node.
- Redaction loại bỏ secret.
- Log field có schema và kiểu ổn định.
- Metrics counter chỉ tăng theo event tương ứng.
- Retry có attempt number và parent context đúng.
- Observer failure không làm thay đổi kết quả nếu policy yêu cầu non-blocking.
- Sampling không loại bỏ audit record bắt buộc.
- Concurrent executions không trộn context.

Có thể dùng in-memory exporter hoặc test observer để xác nhận event được phát. Không nên kiểm tra bằng cách so sánh toàn bộ câu log nếu message có thể được bản địa hóa; hãy kiểm tra event name và field ổn định.

## 24. Những sai lầm thường gặp

1. **Chỉ ghi text log:** khó truy vấn, tổng hợp và liên kết giữa service.
2. **Không có execution ID:** không thể gom các event thuộc cùng một lần chạy.
3. **Dùng rule ID làm execution ID:** nhiều lần chạy đồng thời bị trộn.
4. **Ghi log mọi AST node trong production:** tạo overhead và dữ liệu quá lớn.
5. **Không giữ source mapping:** lỗi runtime không trỏ được về DSL source.
6. **Gộp matched với fired:** người vận hành không hiểu vì sao action không chạy.
7. **Dùng ID động làm metric label:** cardinality tăng mạnh.
8. **Ghi raw input và secret:** tạo rủi ro rò rỉ dữ liệu.
9. **Không escape dữ liệu:** có thể bị log injection.
10. **Coi log thường là audit:** thiếu tính toàn vẹn và quyền kiểm soát.
11. **Không phân biệt timeout và cancellation:** điều tra sai nguyên nhân.
12. **Không liên kết root cause:** một lỗi downstream bị đếm thành nhiều lỗi độc lập.
13. **Sampling cả audit:** mất bằng chứng cần thiết.
14. **Observer làm chậm hoặc thay đổi execution:** instrumentation ảnh hưởng semantics.
15. **Không đo overhead:** logging trở thành nguyên nhân gây latency.

## 25. Quy trình triển khai quan sát và ghi log

Có thể thực hiện theo các bước:

1. **Liệt kê câu hỏi vận hành:** xác định đội phát triển và vận hành cần biết điều gì về execution.
2. **Định nghĩa execution context:** execution ID, trace ID, parent ID, actor, tenant và DSL version.
3. **Thiết kế event schema:** event name, field, severity và version.
4. **Chọn điểm instrumentation:** execution lifecycle, rule, step, capability và error boundary.
5. **Thiết lập metrics:** counter, gauge, histogram và cardinality policy.
6. **Tích hợp tracing:** span boundaries và context propagation.
7. **Thiết kế diagnostics:** error code, source span, cause chain và retryability.
8. **Tách audit:** xác định event bắt buộc, integrity và retention.
9. **Áp dụng privacy controls:** minimization, masking, redaction, access control và retention.
10. **Thiết lập sampling:** ưu tiên lỗi và latency cao, giữ audit theo chính sách.
11. **Tạo dashboard và alert:** gắn với SLO và hành động cụ thể.
12. **Kiểm thử instrumentation:** schema, context, source mapping, concurrency và observer failure.
13. **Đo overhead:** latency, throughput, memory và lượng dữ liệu phát ra.
14. **Quản lý tương thích:** version event schema và giữ field liên kết ổn định.

Bắt đầu với lifecycle events, error codes, execution ID và một vài metrics cốt lõi thường tạo nền tảng tốt. Sau đó có thể thêm rule trace chi tiết hoặc sampling theo nhu cầu điều tra.

## 26. Kết luận

Quan sát và ghi log giúp hiểu được điều gì xảy ra trong runtime DSL, vì sao rule hoặc workflow tạo ra kết quả và phần nào của hệ thống gây lỗi hoặc chậm. Logs ghi sự kiện, metrics đo xu hướng và mức độ, traces liên kết các bước trong một execution, còn audit records lưu lại hành động cần trách nhiệm giải trình.

Một thiết kế observability tốt cần execution context và ID ổn định, event schema có cấu trúc, source mapping, log level hợp lý, metric cardinality được kiểm soát, trace propagation, diagnostics rõ ràng và chính sách bảo vệ dữ liệu. Instrumentation phải được kiểm thử và đo overhead để cung cấp thông tin hữu ích mà không làm thay đổi hành vi của DSL hoặc tạo thêm rủi ro vận hành.

