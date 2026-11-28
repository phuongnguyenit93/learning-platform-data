# Document sampling và giới hạn dữ liệu

> **Chương:** Tài liệu vận hành  
> **Bối cảnh:** Spring Modulith mô tả ranh giới application module và quan sát tương tác giữa các module trong ứng dụng Spring Boot. Khi đưa tracing vào production, đội vận hành phải ghi lại chính sách sampling, giới hạn kích thước telemetry, dữ liệu được phép thu thập, retention và ngân sách lưu trữ. Bài này hướng dẫn lập tài liệu có thể kiểm tra, so sánh giữa các release và dùng làm căn cứ khi điều tra sự cố.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Lập hồ sơ sampling có version, owner, phạm vi áp dụng và ngày hiệu lực.
2. Ghi rõ head sampling, parent-based sampling và tail sampling theo từng service/environment.
3. Ước lượng số span, dung lượng export và dung lượng lưu trữ theo traffic, tỷ lệ lấy mẫu và retention.
4. Tài liệu hóa giới hạn attributes, events, links, payload, queue, batch và Collector.
5. Đặt quy tắc data minimization, phân loại dữ liệu nhạy cảm và thời hạn lưu telemetry.
6. Phân biệt giới hạn của SDK, Collector, metrics backend và trace backend.
7. Kiểm chứng thay đổi sampling/limits và lưu bằng chứng vận hành sau mỗi lần rollout.

## 1. Vì sao phải document sampling và data limits?

Sampling quyết định trace nào được ghi nhận hoặc giữ lại. Data limits quyết định mỗi span, batch hoặc hệ thống backend có thể tiếp nhận bao nhiêu dữ liệu. Hai chính sách này ảnh hưởng trực tiếp tới:

- Khả năng điều tra lỗi và latency.
- Chi phí network, CPU, memory, index và storage.
- Số lượng span được gửi tới Collector và trace backend.
- Khả năng tìm kiếm theo module, service, operation và error.
- Nguy cơ dữ liệu cá nhân, token hoặc payload nghiệp vụ lọt vào telemetry.
- Khả năng đáp ứng retention, access control và yêu cầu xóa dữ liệu.

Nếu chỉ ghi một con số như "sampling 10%" thì tài liệu vận hành chưa đủ. Người trực cần biết tỷ lệ đó áp dụng ở đâu, sampler nào quyết định, trace lỗi có được giữ không, Collector nhận bao nhiêu span, backend lưu bao lâu và khi vượt giới hạn thì dữ liệu nào bị drop.

Với Spring Modulith, cần phân biệt ba nguồn bằng chứng:

| Nguồn | Vai trò | Sampling trace có tác động trực tiếp không? |
| --- | --- | --- |
| Module graph /actuator/modulith | Mô tả module và dependency kiến trúc | Không |
| Event metrics như module.events.published | Đếm hoạt động publish event | Không theo trace sampler |
| Module entry spans / distributed traces | Mô tả đường thực thi được instrument | Có |

Không dùng số trace đã lưu để suy ra chính xác số event đã publish hoặc số lần module được gọi. Trace là dữ liệu lấy mẫu; module graph và metrics có vòng đời riêng.

## 2. Hồ sơ sampling phải trả lời những câu hỏi nào?

Một hồ sơ vận hành nên cho biết:

1. **Scope:** service, module, môi trường, route hoặc workload nào được áp dụng?
2. **Decision point:** SDK head sampler, upstream gateway hay Collector tail sampler quyết định?
3. **Policy:** tỷ lệ root trace, parent-based behavior, điều kiện giữ lỗi/chậm và baseline?
4. **Propagation:** các service có dùng cùng propagation format và kế thừa sampled decision không?
5. **Capacity:** spans/second, bytes/second, queue size, batch size và Collector memory dự kiến?
6. **Data limits:** giới hạn attribute, event, link, value length và payload ở mỗi tầng?
7. **Data classification:** attribute nào được phép, cần redact hoặc bị cấm?
8. **Retention:** thời gian lưu theo môi trường và nhóm dữ liệu?
9. **Ownership:** ai phê duyệt, ai vận hành, ai nhận alert?
10. **Change control:** thay đổi có thời hạn, cách rollback và bằng chứng xác nhận?

### 2.1. Mẫu hồ sơ cho một service

Ví dụ cấu trúc có thể đưa vào tài liệu vận hành của từng service:

~~~yaml
service: shop-service
environment: production
policy_version: "2026-11"
owner: team-commerce
reviewed_at: "2026-11-27"

sampling:
  decision_point: sdk-head
  sampler: parent-based-trace-id-ratio
  root_probability: 0.10
  keep_errors: false
  keep_slow_traces: false
  baseline_policy: "10% of eligible root traces"

propagation:
  format: W3C
  parent_based: true
  async_boundaries:
    - receipt-worker
    - order-event-listener

limits:
  span_attributes: 128
  span_events: 128
  span_links: 128
  attribute_value_length: "implementation default; verify SDK"
  collector_queue: 4096
  batch_size: 512

data:
  allowed_attributes:
    - module.identifier
    - module.invocation-type
    - http.request.method
  prohibited:
    - authorization headers
    - payment credentials
    - request or response bodies
  retention:
    traces: "approved production retention"
    logs: "separate policy"

change:
  reason: "baseline policy"
  approved_by: "observability-owner"
  expires_at: null
  rollback: "restore previous policy version"
~~~

Đây là mẫu tài liệu, không phải file cấu hình được Spring Boot tự đọc. Thay các giá trị minh họa bằng cấu hình effective, quyết định bảo mật và retention đã được phê duyệt. Không ghi secret hoặc thông tin cá nhân vào hồ sơ.

## 3. Document head sampling

**Head sampling** đưa ra quyết định ở đầu trace, tại SDK hoặc thành phần upstream. Với Spring Boot, property phổ biến là:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Tài liệu Spring Boot 3.5 và 4.x đều nêu mặc định sampling 10% request để tránh làm trace backend quá tải. Property management.tracing.sampling.probability dùng để điều chỉnh tỷ lệ này. Spring Boot 4.x hiện hành còn cho phép chọn sampler OpenTelemetry qua management.opentelemetry.tracing.sampler:

~~~yaml
management:
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
  tracing:
    sampling:
      probability: 0.1
~~~

Các sampler OpenTelemetry được Spring Boot hỗ trợ trong tài liệu hiện hành gồm:

| Sampler | Ý nghĩa |
| --- | --- |
| always-on | Lấy mẫu mọi trace |
| always-off | Loại mọi trace |
| trace-id-ratio | Lấy mẫu theo tỷ lệ dựa trên trace ID |
| parent-based-always-on | Theo quyết định parent; nếu không có parent thì lấy mẫu |
| parent-based-always-off | Theo quyết định parent; nếu không có parent thì loại |
| parent-based-trace-id-ratio | Theo parent; nếu không có parent thì áp dụng xác suất theo trace ID |

Với Spring Boot 3.5, tài liệu tracing mô tả trực tiếp property probability; không mặc định rằng property chọn sampler ở trên có mặt trong mọi minor version 3.5. Với Spring Boot 4.x, kiểm tra danh sách sampler và default trong tài liệu đúng minor version. Ghi rõ phiên bản Spring Boot, Micrometer bridge và OpenTelemetry SDK đang chạy thay vì chỉ sao chép YAML từ một ví dụ khác.

### 3.1. Những gì phải ghi trong hồ sơ head sampling

- Property và giá trị effective sau khi profile/environment override.
- Sampler implementation và phiên bản SDK/bridge.
- Tỷ lệ root trace.
- Parent-based behavior và propagation format.
- Service/gateway nào là điểm đầu tiên đưa ra sampling decision.
- Thời điểm áp dụng và release chứa thay đổi.
- Số trace/span kỳ vọng và sai số thống kê.

Không ghi "10% mỗi service" nếu thực tế sampler parent-based chỉ chọn ở root và child kế thừa sampled decision. Một trace đi qua năm service không có nghĩa mỗi service lại độc lập lấy 10% một lần.

### 3.2. Tỷ lệ xác suất không phải quota

Với 1.000 trace root đủ điều kiện và xác suất 10%, số trace kỳ vọng là 100. Kết quả thực tế có thể cao hoặc thấp hơn; đây không phải cam kết mỗi nhóm 10 request sẽ có đúng một trace.

Nếu cần quota hoặc rate giới hạn theo giây, phải dùng policy phù hợp thay vì diễn giải probability thành giới hạn cứng.

### 3.3. Ghi nhận ngoại lệ tạm thời

Nếu tăng sampling để điều tra incident:

- Ghi service/environment/route được thay đổi.
- Ghi giá trị trước và sau thay đổi.
- Ghi người phê duyệt và ticket/incident liên quan.
- Ghi thời điểm bắt đầu và thời điểm hết hạn.
- Ghi ngân sách tăng thêm cho Collector/backend.
- Ghi điều kiện rollback và người chịu trách nhiệm khôi phục.

Không để sampling probability 1.0 tồn tại vô thời hạn ở production chỉ vì từng hữu ích trong một lần debug.

## 4. Document tail sampling

**Tail sampling** chờ Collector nhận span rồi mới quyết định giữ trace, thường dựa trên lỗi, latency, attributes hoặc tỷ lệ baseline.

Ví dụ policy có thể giữ:

- Trace có span status ERROR.
- Trace có thời gian vượt ngưỡng.
- Một tỷ lệ trace bình thường để làm baseline.

Để tail sampler đánh giá lỗi xảy ra ở cuối request, các service phải gửi đủ span tới Collector. Nếu SDK hoặc gateway head-drop trace trước khi Collector nhận dữ liệu, tail sampler không thể khôi phục trace đó.

### 4.1. Thông tin cần document

| Trường | Cần ghi |
| --- | --- |
| Collector distribution/version | Core, Contrib hoặc bản vendor; version cụ thể |
| Processor | tail_sampling và thứ tự trong traces pipeline |
| decision_wait | Thời gian chờ trước khi quyết định |
| num_traces | Số trace có thể giữ trong bộ nhớ |
| expected_new_traces_per_sec | Ước lượng trace mới mỗi giây |
| Policies | Status, latency, probabilistic, attribute, rate limit hoặc composite |
| Policy combination | Cách policy giữ/drop được kết hợp |
| Routing | Cách đảm bảo span cùng trace đến cùng Collector |
| Memory budget | Bộ nhớ dành cho trace đang chờ quyết định |
| Late spans | Hành vi và metric theo dõi span đến sau decision |
| Overflow | Hành vi khi số trace vượt num_traces |

### 4.2. Ví dụ policy

~~~yaml
processors:
  tail_sampling:
    decision_wait: 30s
    num_traces: 50000
    expected_new_traces_per_sec: 1000
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: keep-slow
        type: latency
        latency:
          threshold_ms: 1000
      - name: baseline
        type: probabilistic
        probabilistic:
          sampling_percentage: 5
~~~

Đây là ví dụ minh họa cho OpenTelemetry Collector Contrib. Cấu trúc, policy types và cách kết hợp có thể thay đổi theo Collector version. Kiểm tra tài liệu processor đúng phiên bản trước khi triển khai.

### 4.3. Yêu cầu định tuyến theo trace ID

Tail sampler giữ trace đang chờ trong bộ nhớ. Tất cả span của cùng một trace phải đến cùng một Collector instance; nếu load balancer phân tán từng span ngẫu nhiên, mỗi instance có thể chỉ thấy một phần trace.

Khi scale Collector:

- Dùng trace-ID-aware load balancing trước tier tail sampling.
- Không chia span của một trace sang nhiều sampler độc lập.
- Đo số trace bị drop trước decision và span đến muộn.
- Tính memory theo trace đang giữ, không chỉ theo tỷ lệ cuối cùng được export.

Một số metric tail sampling cần xem (tên và stability phụ thuộc Collector version):

| Metric | Ý nghĩa vận hành |
| --- | --- |
| otelcol_processor_tail_sampling_sampling_trace_dropped_too_early | Trace bị loại khỏi buffer trước khi có sampling decision |
| otelcol_processor_tail_sampling_sampling_decision_timer_latency | Thời gian chạy sampling decision |
| otelcol_processor_tail_sampling_sampling_late_span_age | Tuổi của span đến sau khi trace đã có decision |
| otelcol_processor_tail_sampling_global_count_traces_sampled | Số trace được đánh giá là sampled/not sampled ở cấp toàn processor |

Xác nhận metric có được bật và scrape ở Collector đang dùng. Không đưa tên metric của bản mới vào alert production nếu bản đang chạy chưa expose chúng.

### 4.4. Ghi rõ trade-off

| Tiêu chí | Head sampling | Tail sampling |
| --- | --- | --- |
| Quyết định | Sớm, ở SDK/upstream | Sau khi Collector nhận span |
| Có thể giữ trace lỗi cuối request | Không nếu đã drop từ đầu | Có nếu nhận đủ span và policy match |
| Tải lên Collector | Giảm từ SDK | Có thể phải nhận 100% span đầu vào |
| Bộ nhớ chờ | Ít state tập trung | Collector giữ trace trong RAM |
| Vận hành phân tán | Đơn giản hơn | Cần routing theo trace ID |
| Rủi ro dữ liệu | Bỏ trace trước khi biết kết quả | Queue/trace buffer đầy hoặc span đến muộn |

## 5. Ước lượng volume và storage budget

Sampling policy nên được đánh giá bằng lưu lượng dự kiến thay vì chọn tỷ lệ tùy ý.

Một công thức ước lượng cơ bản:

~~~text
sampled spans/second
  = traces/second
  × average spans/trace
  × sampling probability

export bytes/second
  = sampled spans/second
  × average encoded bytes/span

daily raw bytes
  = export bytes/second
  × 86,400
~~~

Đây là mô hình sơ bộ. Nó chưa tính resource attributes, batch/protocol overhead, compression, index, replication, metadata và sự khác biệt giữa span nhỏ/lớn.

### 5.1. Ví dụ tính toán

Giả sử:

- 120 trace root/giây.
- Trung bình 8 span/trace.
- Head sampling 10%.
- Trung bình 2 KB/span sau encode.

Tính:

~~~text
sampled spans/s = 120 × 8 × 0.10 = 96 spans/s
export bytes/s  = 96 × 2 KB = 192 KB/s
raw bytes/day   = 192 KB/s × 86,400 = 16.6 GB/day
raw 30 days     ≈ 497.7 GB
~~~

Đây là ước lượng dữ liệu thô. Backend có thể cần dung lượng lớn hơn do index, replication, compression ratio, block metadata và overhead. Cần lấy số liệu thực tế từ Collector/backend để lập ngân sách.

### 5.2. Tail sampling cần hai phép tính

Với tail sampling, phải tách:

1. **Ingress budget:** tất cả span gửi tới Collector để sampler đánh giá.
2. **Retention/export budget:** trace được policy giữ và gửi tiếp tới backend.

Ví dụ nếu Collector nhận 100% trace nhưng chỉ giữ 10% trace, storage backend có thể gần với mức 10% (tùy policy), nhưng network, CPU và bộ nhớ Collector vẫn phải xử lý luồng đầu vào đầy đủ.

Không sizing Collector theo số span sau sampling nếu sampling diễn ra ở Collector.

### 5.3. Ghi assumptions

Trong hồ sơ budget, ghi:

- Request/trace rate trung bình và peak.
- Tỷ lệ trace có lỗi/chậm.
- Span/trace trung bình và p95.
- Kích thước span trung bình và p95.
- Sampling rate theo từng policy.
- Số service và replica.
- Thời gian retention.
- Compression/index/replication factor theo backend.
- Headroom cho burst và incident sampling override.

Ước lượng cần được cập nhật bằng dữ liệu thực tế sau mỗi lần thay đổi traffic hoặc instrumentation.

## 6. Document span, event và link limits

Span có thể chứa attributes, events và links. SDK có thể giới hạn số lượng phần tử được giữ để bảo vệ memory và payload.

Theo OpenTelemetry SDK configuration/specification hiện hành, các giới hạn phổ biến có default thường gặp là:

| Giới hạn | Mặc định thường gặp |
| --- | ---: |
| Span attribute count | 128 |
| Span event count | 128 |
| Span link count | 128 |
| Attribute per event | 128 |
| Attribute per link | 128 |
| Attribute value length | Không giới hạn nếu không cấu hình |

Các con số này là mặc định của OpenTelemetry SDK specification/environment configuration, không phải bảo đảm mọi tracing bridge hoặc Spring Boot version đều expose cùng một property. Kiểm tra SDK thực tế và customizer trước khi ghi vào hồ sơ production.

### 6.1. Giới hạn attributes

Attributes mô tả service, operation và dữ liệu cần điều tra. Nếu vượt attribute count limit, SDK có thể loại bỏ attributes vượt giới hạn. Attribute value length limit có thể cắt ngắn chuỗi dài theo implementation.

Ví dụ attribute hợp lý:

~~~text
module.identifier = "orders"
module.invocation-type = "bean"
http.request.method = "POST"
error.type = "PaymentDeclined"
~~~

Ví dụ dữ liệu nên loại bỏ hoặc redact:

~~~text
authorization = "Bearer ..."
request.body = "{... toàn bộ dữ liệu khách hàng ...}"
payment.card.number = "..."
sql.bind.parameters = "[...]"
~~~

Không dùng span attributes như nơi lưu payload nghiệp vụ.

### 6.2. Giới hạn events

Span events ghi lại mốc quan trọng trong vòng đời span, chẳng hạn exception hoặc một transition có ý nghĩa. Không ghi một event cho mọi vòng lặp, mọi record hoặc mọi message nếu volume không được kiểm soát.

Document:

- Event name và mục đích.
- Attribute nào được phép đi kèm.
- Số event tối đa kỳ vọng trên một span.
- SDK event count limit.
- Cách phát hiện event bị loại khi vượt giới hạn.

### 6.3. Giới hạn links

Span links hữu ích khi một operation liên hệ với nhiều trace context, ví dụ batch consumer gom nhiều message hoặc workflow bất đồng bộ. Link count và attributes per link cũng có thể bị giới hạn.

Nếu hệ thống xử lý batch, ghi rõ:

- Số message tối đa gom vào một batch.
- Số link tối đa gắn lên span.
- Chính sách khi số context nguồn vượt limit.
- Có cần tạo nhiều span/batch nhỏ hơn hay không.

Không mặc định link đầu tiên đại diện cho toàn bộ batch nếu phần còn lại đã bị drop.

## 7. Giới hạn attribute value và payload

Số lượng attribute không phải giới hạn duy nhất. Một span chỉ có vài attribute nhưng mỗi attribute chứa JSON, SQL hoặc request body lớn vẫn có thể tạo payload nặng.

Nên document:

- Maximum attribute value length của SDK.
- Maximum nested value depth nếu SDK hỗ trợ.
- Kích thước batch/request của exporter.
- Giới hạn request body của proxy/Collector/backend.
- Chính sách cắt ngắn, redact hoặc loại bỏ field.

### 7.1. Ví dụ environment variables OpenTelemetry

~~~bash
OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT=128
OTEL_SPAN_EVENT_COUNT_LIMIT=128
OTEL_SPAN_LINK_COUNT_LIMIT=128
OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT=256
OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT=128
OTEL_LINK_ATTRIBUTE_COUNT_LIMIT=128
~~~

Đây là ví dụ theo OpenTelemetry SDK environment variable specification. Không giả định mọi SDK hoặc Micrometer bridge đều hỗ trợ đầy đủ các biến này. Xác nhận SDK version, cấu hình thực tế và log khi attribute/event/link bị discard.

### 7.2. Ưu tiên allowlist

Thiết kế attribute theo allowlist:

| Nhóm | Ví dụ | Chính sách |
| --- | --- | --- |
| Module metadata | module.identifier, module.invocation-type | Cho phép |
| Operation | Tên operation ổn định, HTTP method | Cho phép |
| Result | Status code, error type đã chuẩn hóa | Cho phép có kiểm soát |
| Customer data | Email, phone, address, account number | Không thu thập mặc định |
| Credential | Authorization, cookie, API key, session token | Cấm |
| Payload | Request/response body, message body | Cấm mặc định |
| Database detail | SQL parameter, bind value, full query chứa dữ liệu | Redact hoặc giới hạn nghiêm ngặt |

Allowlist giúp schema ổn định và làm rõ mục đích của từng field.

## 8. Cardinality và data limits của metrics

Sampling trace không phải cách giảm cardinality của metrics. Metric time series được phân biệt bởi tên meter và bộ tag/label.

Ví dụ tốt:

~~~text
module.events.published{module="orders",event="OrderPlaced"}
~~~

Ví dụ nguy hiểm:

~~~text
http.server.requests{trace_id="4bf92f...",order_id="ORD-12345"}
~~~

Trace ID, order ID, user ID hoặc URL chứa ID động có thể tạo ra số lượng time series rất lớn.

### 8.1. Quy tắc tag

- Dùng giá trị hữu hạn, ổn định và có ý nghĩa vận hành.
- Không đưa trace/span ID, order ID, user ID, email hoặc session ID vào metric tags.
- Chuẩn hóa exception thành nhóm/type ổn định thay vì message động.
- Giới hạn tập giá trị route; dùng route template thay cho URL đầy đủ.
- Theo dõi số series và scrape size sau khi thêm tag mới.

### 8.2. Phân biệt metric dimensions và trace attributes

Một trường có thể phù hợp làm trace attribute nhưng không phù hợp làm metric label. Ví dụ, trace ID hữu ích khi tìm một request cụ thể, nhưng không được dùng làm Prometheus label.

Tài liệu schema nên ghi riêng:

| Field | Trace attribute | Metric tag |
| --- | --- | --- |
| module.identifier | Có | Có, nếu tập module hữu hạn |
| http.request.method | Có | Có |
| error.type | Có | Có nếu chuẩn hóa |
| traceId | Context field | Không |
| orderId | Chỉ khi có lý do và chính sách cho phép | Không |
| email | Không | Không |

## 9. Data classification, privacy và retention

Telemetry có thể chứa dữ liệu vận hành và dữ liệu nghiệp vụ. Trước khi bật instrumentation, xác định dữ liệu nào được phép thu thập, ai có thể đọc và lưu bao lâu.

### 9.1. Phân loại dữ liệu

Một cách phân loại vận hành:

| Phân loại | Ví dụ | Quy tắc telemetry |
| --- | --- | --- |
| Public/technical | Service name, module ID, HTTP method | Có thể thu thập |
| Internal operational | Error type, status code, dependency name | Thu thập theo allowlist |
| Confidential business | Giá trị đơn hàng, account reference, pricing detail | Chỉ thu thập khi có mục đích rõ và đã phê duyệt |
| Personal data | Email, phone, address, customer identifier | Tránh thu thập; nếu bắt buộc phải có căn cứ và kiểm soát |
| Secret/authentication | Password, token, cookie, private key | Không thu thập |

Phân loại cụ thể phải theo chính sách dữ liệu của tổ chức và quy định áp dụng. Bảng trên là mẫu kỹ thuật, không thay thế đánh giá pháp lý hoặc chính sách bảo mật nội bộ.

### 9.2. Data minimization

Ưu tiên:

1. Không instrument field không phục vụ câu hỏi vận hành.
2. Chỉ thu thập attribute ổn định, có mục đích rõ.
3. Redact tại nguồn trước khi ghi span/log.
4. Dùng Collector processor như lớp bảo vệ bổ sung.
5. Kiểm tra exporter và backend có giữ raw data hoặc bản sao nào không.

Redact ở Collector không thay thế việc tránh đưa secret vào telemetry tại ứng dụng. Dữ liệu có thể đã tồn tại trong log nội bộ, buffer hoặc network trước khi processor xử lý.

### 9.3. Retention phải được ghi theo từng loại dữ liệu

Không dùng một con số retention chung cho logs, metrics và traces nếu backend/policy khác nhau.

| Dữ liệu | Nội dung hồ sơ cần có |
| --- | --- |
| Traces | Retention theo environment/tenant, tier và loại trace |
| Logs | Retention, index policy và access policy riêng |
| Metrics | Retention của time series và downsampling/rollup |
| Collector buffer | Thời gian giữ trong RAM hoặc persistent queue |
| Alert history | Thời gian giữ notification/audit |
| Backups | Thời hạn, encryption và quy trình xóa theo retention |

Ghi rõ owner, nơi lưu, cách xóa, backup expiry và quy trình xử lý yêu cầu xóa dữ liệu. Retention backend không đồng nghĩa dữ liệu đã bị xóa khỏi mọi backup hoặc export.

## 10. Document Collector và exporter limits

Sampling chỉ là một lớp. Collector và exporter có giới hạn riêng:

| Thành phần | Giới hạn cần ghi |
| --- | --- |
| SDK BatchSpanProcessor | Queue size, batch size, schedule delay, export timeout |
| OTLP exporter | Endpoint, connect/call timeout, retry và payload |
| Collector receiver | Max request/message size, concurrent requests, memory limiter |
| Collector tail sampler | decision_wait, num_traces, policies, overflow và memory |
| Collector batch processor | send_batch_size, timeout và batch behavior |
| Collector exporter | Queue size, retry, timeout, backend endpoint |
| Proxy/load balancer | Request body size, idle timeout, connection limit |
| Trace backend | Ingestion rate, quota, attribute limits, retention và index limits |

### 10.1. SDK queue và batch

Nếu dùng OpenTelemetry BatchSpanProcessor, document các tham số:

~~~text
max-queue-size
max-batch-size
schedule-delay
export timeout
~~~

Queue lớn hơn giúp hấp thụ gián đoạn ngắn nhưng tiêu tốn RAM. Batch lớn có thể giảm số request nhưng tạo payload lớn và tốn memory hơn. Không tăng cả hai mà không đo throughput và heap.

### 10.2. Tail sampler buffer

Tail sampler giữ trace trong bộ nhớ tới khi quyết định. Document:

- Số trace đang chờ.
- Trace arrival rate.
- Kích thước trace trung bình/p95.
- decision_wait.
- num_traces.
- Trace bị drop quá sớm.
- Span đến muộn.
- Memory limiter và restart behavior.

Nếu num_traces không đủ khi traffic tăng, trace có thể bị loại khỏi buffer trước khi có quyết định. Tăng num_traces làm tăng memory; giảm decision_wait có thể làm mất cơ hội nhận span muộn.

### 10.3. Exporter retry không phải persistent delivery

Retry có thể giúp vượt lỗi mạng tạm thời nhưng không biến telemetry thành hàng đợi nghiệp vụ bền vững. Nếu Collector hoặc process dừng khi dữ liệu chỉ nằm trong RAM, batch chưa export có thể mất. Nếu cần buffer qua restart, phải document persistent queue và storage lifecycle của Collector/backend.

## 11. Bảng giới hạn theo từng tầng

| Tầng | Loại giới hạn | Triệu chứng khi vượt | Nơi kiểm tra |
| --- | --- | --- | --- |
| SDK span | Attribute/event/link count | Metadata bị discard | SDK config/log |
| SDK span | Attribute value length | Chuỗi bị cắt hoặc bị loại | SDK config và trace payload |
| SDK processor | Queue capacity | Span drop trước export | Processor metrics/log |
| Exporter | Timeout/payload | Batch gửi thất bại | Exporter logs/metrics |
| Collector receiver | Request size/concurrency | Request bị từ chối | Receiver logs/metrics |
| Tail sampler | Trace buffer capacity | Trace bị drop trước decision | Tail sampling metrics |
| Collector exporter | Retry queue | Queue tăng, send failure | Exporter metrics/log |
| Metrics backend | Series/cardinality | Ingestion chậm hoặc từ chối series | Backend cardinality dashboard |
| Trace backend | Ingestion/index/retention | Trace mất, đến chậm hoặc không query được | Backend status/quota |

Không kết luận trace bị sampling chỉ từ việc thiếu attributes hoặc không thấy trace trên UI. Dữ liệu có thể bị giới hạn ở SDK, drop ở Collector hoặc từ chối ở backend.

## 12. Kiểm chứng sampling và limits sau thay đổi

Mỗi lần thay sampling hoặc data limits cần một bộ kiểm tra có thể lặp lại.

### 12.1. Trước khi thay đổi

- Lưu policy version hiện tại.
- Lưu cấu hình effective của từng service và Collector.
- Ghi baseline spans/second, bytes/second, queue usage và backend ingestion.
- Ghi tỷ lệ error/slow trace và nhu cầu điều tra.
- Xác nhận data classification/allowlist.

### 12.2. Sau khi thay đổi

1. Xác nhận ứng dụng khởi động với đúng config version.
2. Gửi synthetic request qua module boundary.
3. Kiểm tra trace ID, parent-child hoặc span links theo thiết kế.
4. Kiểm tra trace được giữ/loại theo policy.
5. Kiểm tra attribute/event/link không bị mất ngoài dự kiến.
6. Theo dõi SDK/Collector queue và export failure.
7. Đo volume và cardinality so với baseline.
8. Kiểm tra Prometheus scrape và trace backend ingestion.
9. Kiểm tra không có dữ liệu bị cấm trong span/log/metric.
10. Lưu bằng chứng và người xác nhận.

### 12.3. Kiểm tra tỷ lệ sample thực tế

Với head sampling theo xác suất, so sánh số trace root đủ điều kiện và số trace được sample trên một cửa sổ đủ lớn. Kết quả không cần bằng đúng xác suất ở từng cửa sổ nhỏ.

Với tail sampling, dùng decision metrics của Collector để xem số trace được sample, not sampled hoặc dropped theo policy. Phân biệt:

- Policy vote to sample.
- Quyết định cuối cùng sau khi kết hợp các policy.
- Trace bị drop trước khi có decision do buffer pressure.

Một policy giữ trace không bảo đảm trace cuối cùng được export nếu policy drop khác, processor khác hoặc exporter/backend tiếp tục loại dữ liệu.

## 13. Ví dụ tài liệu policy theo môi trường

Các giá trị dưới đây chỉ minh họa cách mô tả, không phải khuyến nghị áp dụng cho mọi hệ thống:

| Môi trường | Sampling | Data limits | Retention | Mục đích |
| --- | --- | --- | --- | --- |
| Local | 100% trong workload nhỏ | SDK defaults | Ngắn, local only | Debug và học tập |
| Test/CI | 100% hoặc policy theo test | Payload giới hạn | Theo vòng đời test | Kiểm tra trace assertions |
| Staging | Tỷ lệ cao hoặc tail policy có kiểm soát | Gần production | Theo thời hạn staging | Xác nhận release |
| Production | Head ratio hoặc tail policy được duyệt | Allowlist và limits đã đo | Theo data policy | Điều tra sự cố với ngân sách ổn định |

### 13.1. Ví dụ Spring Boot production head sampling

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Nếu dùng OpenTelemetry sampler cụ thể:

~~~yaml
management:
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
  tracing:
    sampling:
      probability: 0.1
~~~

Đặt sampler và property theo phiên bản Spring Boot thực tế. Lưu lại cấu hình effective vì profile, environment variables hoặc customizer có thể override file YAML.

### 13.2. Ví dụ override tạm thời khi incident

Một thay đổi tạm thời nên có thời hạn:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.5
~~~

Hồ sơ change cần ghi:

- Incident/ticket và câu hỏi cần điều tra.
- Service/route được áp dụng.
- Tỷ lệ cũ/mới.
- Thời điểm bắt đầu, expiry và người phê duyệt.
- Collector/backend capacity đã xác nhận.
- Bước rollback và bằng chứng sau rollback.

Nếu dùng tail sampling, thay đổi policy Collector cũng phải được version hóa và review cùng cấu hình upstream.

## 14. Những lỗi thường gặp khi document

| Lỗi tài liệu | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ ghi "sampling 10%" | Không biết sampler, scope và parent behavior | Ghi decision point, sampler, root probability và propagation |
| Nhầm xác suất với quota | Kỳ vọng sai số trace từng phút | Ghi rõ đây là xác suất thống kê |
| Chỉ ghi tỷ lệ tail sample | Bỏ sót ingress load vào Collector | Tính riêng ingress và retained volume |
| Không ghi Collector version | Policy/metric/config có thể không tương thích | Gắn version vào policy snapshot |
| Không ghi decision_wait/num_traces | Khó giải thích dropped-too-early | Ghi memory budget và tail metrics |
| Không ghi span limits | Attribute/event/link bị mất mà không rõ lý do | Ghi SDK limits và kiểm tra runtime config |
| Dùng trace ID làm metric label | Cardinality tăng mạnh | Giữ ID trong log/trace, không dùng làm metric tag |
| Ghi payload để debug | Rò rỉ PII/secret và tăng storage | Dùng allowlist, redaction và synthetic data |
| Retention ghi chung cho mọi dữ liệu | Không biết logs/traces/metrics bị xóa khi nào | Tách retention theo backend và data class |
| Không có expiry cho debug override | Sampling cao kéo dài gây tăng chi phí | Bắt buộc expiry, owner và rollback |
| Không ghi policy combination | Không hiểu vì sao trace bị drop dù policy match | Document thứ tự/kết hợp keep/drop và test |
| Không cập nhật sau release | Hồ sơ không phản ánh config đang chạy | Version hóa và đối chiếu effective config |

## 15. Runbook khi vượt sampling hoặc data budget

### Bước 1 — Xác định tầng vượt giới hạn

- SDK span limits?
- SDK queue hoặc exporter timeout?
- Collector receiver/tail sampler?
- Collector exporter queue?
- Metrics series/cardinality?
- Trace backend ingestion/index/storage?

Không tăng limit trước khi xác định tầng đang drop hoặc từ chối dữ liệu.

### Bước 2 — Xác định ảnh hưởng

- Service và module nào bị ảnh hưởng?
- Trace lỗi/chậm có còn được giữ không?
- Có mất module spans hay chỉ mất attributes?
- Queue đang tăng hay đã drop?
- Business request/error rate có thay đổi không?
- Dữ liệu nhạy cảm có xuất hiện ngoài allowlist không?

### Bước 3 — Chọn biện pháp

| Nguyên nhân | Biện pháp |
| --- | --- |
| Sampling quá thấp cho incident | Tăng có thời hạn ở scope nhỏ hoặc dùng tail policy phù hợp |
| Collector buffer thiếu | Điều chỉnh num_traces/decision_wait sau khi tính memory và routing |
| SDK queue đầy | Kiểm tra exporter throughput; tăng queue có tính toán hoặc giảm span volume |
| Payload quá lớn | Loại body/SQL/attributes dư thừa; giảm batch hoặc value length |
| Backend ingestion quá tải | Giảm volume, scale ingestion hoặc điều chỉnh quota |
| Metrics cardinality tăng | Loại tag động và giảm số dimension |
| Dữ liệu nhạy cảm xuất hiện | Ngăn thu thập tại nguồn, redact, đánh giá bản sao và quy trình xử lý dữ liệu |

### Bước 4 — Xác nhận phục hồi

- Queue trở về vùng bình thường.
- Export failure/drop không tiếp tục tăng.
- Trace smoke test được tìm thấy theo policy.
- Module spans có attributes cần thiết.
- Metrics cardinality và ingestion ổn định.
- Không còn field bị cấm trong telemetry mới.
- Hồ sơ policy và incident record được cập nhật.

## 16. Bài tập tự kiểm tra

**Câu 1.** Spring Boot đặt probability=0.1. Có thể yêu cầu cứ 100 request phải có đúng 10 trace không? Vì sao?

**Câu 2.** Hệ thống dùng tail sampling giữ mọi trace lỗi, nhưng SDK ở gateway head-drop 90% trace. Collector có thể giữ mọi lỗi không?

**Câu 3.** Ứng dụng tạo 200 trace root/giây, trung bình 6 span/trace, head sample 5%. Ước lượng sampled spans/giây.

**Câu 4.** Vì sao phải tính ingress volume riêng với retained volume khi dùng tail sampling?

**Câu 5.** OpenTelemetry SDK có span attribute limit 128. Điều này có nghĩa attribute value dài bao nhiêu cũng được an toàn không?

**Câu 6.** Vì sao không đưa traceId hoặc orderId vào metric tags?

**Câu 7.** Một span không có exception event dù request lỗi. Hãy nêu các nguyên nhân có thể liên quan tới data limits/instrumentation.

**Câu 8.** Một debug override tăng sampling lên 100%. Hồ sơ change cần có những trường nào?

**Câu 9.** Trace backend giữ 30 ngày. Điều này có nghĩa mọi bản sao telemetry đều bị xóa sau 30 ngày không?

### Gợi ý đáp án

1. Không. Probability là xác suất; số trace thực tế dao động theo thống kê và cửa sổ quan sát.
2. Không. Trace bị head-drop trước Collector không thể được tail sampler khôi phục. Các service upstream phải gửi đủ span tới Collector.
3. 200 × 6 × 0.05 = 60 sampled spans/giây.
4. Collector phải nhận và giữ dữ liệu trước khi quyết định; tỷ lệ giữ cuối cùng không làm giảm ingress load đã phát sinh.
5. Không. Count limit và value length là hai giới hạn khác nhau; chuỗi rất dài vẫn có thể làm payload lớn nếu không giới hạn value length.
6. Chúng có cardinality rất cao và có thể tạo hàng triệu time series; dùng trace/log để tra cứu ID cụ thể.
7. Exception không được instrument thành event, event count limit đã đầy, sampler không record span, exporter/processor drop hoặc instrumentation chỉ đặt status mà không thêm event.
8. Scope, owner, incident/ticket, tỷ lệ cũ/mới, lý do, thời gian bắt đầu, expiry, capacity, rollback và bằng chứng xác nhận.
9. Không. Cần kiểm tra logs, exports, backups, replication và lifecycle của từng backend; retention một hệ thống không tự xóa mọi bản sao.

## 17. Checklist review tài liệu sampling và limits

- [ ] Có service, environment, owner, version và ngày review.
- [ ] Có decision point và sampler cụ thể.
- [ ] Có root probability và parent-based behavior.
- [ ] Có propagation format và service upstream/downstream liên quan.
- [ ] Tail sampling có policy, decision_wait, num_traces, version và routing.
- [ ] Có ước lượng traces/s, spans/trace, bytes/span và storage/retention.
- [ ] Có SDK limits cho attributes, events, links và value length.
- [ ] Có Collector receiver, queue, batch, exporter và backend limits.
- [ ] Có allowlist/prohibited fields và data classification.
- [ ] Có metric cardinality rules; không dùng trace ID/order ID làm label.
- [ ] Có retention riêng cho traces, logs, metrics, buffers và backups.
- [ ] Có change owner, approval, expiry và rollback cho debug override.
- [ ] Đã kiểm chứng sample decision, dropped spans, queue và backend ingestion.
- [ ] Đã xác nhận không có secret/PII ngoài chính sách trong telemetry.

## 18. Ghi nhớ

Document sampling phải mô tả **ai quyết định, quyết định ở đâu, áp dụng cho trace nào và dữ liệu nào được giữ**. Head sampling giảm tải sớm; tail sampling có thể giữ trace lỗi/chậm nhưng Collector phải nhận đủ span, giữ trace trong bộ nhớ và gom các span cùng trace về cùng instance.

Document data limits ở mọi tầng: SDK attribute/event/link/value limits, processor queue/batch, exporter payload/timeout, Collector buffer, metrics cardinality và backend ingestion/retention. Ước lượng volume từ trace rate, spans per trace, sampling rate và bytes per span; với tail sampling phải tính riêng ingress và dữ liệu được giữ. Cuối cùng, dùng allowlist và data minimization, cấm secret/PII không cần thiết, version hóa policy và đặt expiry cho mọi thay đổi tạm thời.

### Tài liệu tham khảo

- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): sampling mặc định, management.tracing.sampling.probability và OpenTelemetry samplers.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): sampling probability và propagation properties.
- [OpenTelemetry — Trace SDK](https://opentelemetry.io/docs/specs/otel/trace/sdk/): head/tail sampling concepts, span recording và span limits.
- [OpenTelemetry — SDK Environment Variables](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/): attribute, event, link count và value length limits.
- [OpenTelemetry — Configuration Types](https://opentelemetry.io/docs/specs/otel/config/types/): cấu hình SpanLimits và các giá trị mặc định.
- [OpenTelemetry Collector Contrib — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor): policy, memory, trace routing, late spans và dropped-too-early.
- [OpenTelemetry Collector — Internal Telemetry](https://opentelemetry.io/docs/collector/internal-telemetry/): theo dõi queue, receiver, processor và exporter.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module entry spans và event metrics.
