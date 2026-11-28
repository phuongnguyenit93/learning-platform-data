# Kiểm tra thay đổi tên metric, span và thuộc tính semantic convention

Sau khi nâng Spring AI, ứng dụng vẫn chạy và endpoint /actuator/prometheus vẫn trả dữ liệu, nhưng dashboard tool latency bỗng về zero. Một truy vấn khác không còn tìm thấy span `tool_call lookup_order`. Nguyên nhân có thể là instrumentation đã đổi `gen_ai.operation.name` từ `framework` sang `execute_tool`, đổi contextual span name, thêm tag mới, hoặc Spring Boot đổi cách xuất long-task timer.

Bài này hướng dẫn **kiểm tra thay đổi tên metric, span và thuộc tính semantic convention khi nâng Spring AI**. Ta sẽ phân biệt tên observation, tên span, metric name và tag; lập ma trận thay đổi từ Spring AI 1.x sang 2.x; cập nhật Prometheus/Grafana; kiểm tra OpenTelemetry conventions; rồi triển khai migration có kiểm soát để không làm mất tín hiệu vận hành.

Bài thuộc chương **Nâng cấp** của mô-đun **SPRING_AI_EVALUATION_OBSERVABILITY**. Mô-đun đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool workflow; đồng thời đo metrics, traces, chi phí và độ trễ để tìm nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline. Việc nâng cấp observability cần bảo toàn khả năng theo dõi các luồng đó qua nhiều release.

> **Nguyên tắc:** không coi tên observation, tên span, tên metric backend và attribute là một thứ. Kiểm tra từng lớp trên đúng phiên bản Spring AI, Spring Boot, Micrometer và exporter đang chạy.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt observation name, contextual span name, metric name và attribute/tag.
2. Đối chiếu observability conventions của Spring AI 1.0.x/1.1.x với 2.0.x/2.1.x.
3. Nhận diện thay đổi tool span `tool_call` → `execute_tool`.
4. Cập nhật giá trị `gen_ai.operation.name` và các thuộc tính tool mới.
5. Nhận diện thuộc tính ChatClient/Advisor đã deprecated, được thay thế hoặc thay đổi cardinality.
6. Hiểu vì sao Prometheus có thể đổi hậu tố active metric dù observation name không đổi.
7. Phân biệt conventions riêng của Spring AI với OpenTelemetry GenAI semantic conventions.
8. Cập nhật PromQL, Grafana dashboards, alerts và recording rules.
9. Kiểm tra dữ liệu telemetry thực tế qua Actuator, Prometheus và trace backend.
10. Xây dựng migration checklist và compatibility tests cho mỗi lần nâng cấp.

## 2. Bốn lớp tên cần phân biệt

Một operation có thể mang bốn dạng tên khác nhau ở các lớp instrumentation và export.

| Lớp | Ví dụ | Được dùng ở đâu? |
|---|---|---|
| **Observation name** | `spring.ai.tool` | Micrometer Observation; tên meter gốc |
| **Contextual span name** | `tool_call lookup_order` hoặc `execute_tool lookup_order` | Span hiển thị trong trace backend |
| **Prometheus metric name** | `spring_ai_tool_seconds_count` | Time series sau khi Micrometer chuẩn hóa tên |
| **Attribute/tag** | `gen_ai.operation.name=execute_tool` | Phân loại span và dimension của metric |

Tên observation có thể giữ nguyên trong khi span name hoặc tag value đổi. Tương tự, tên metric ở Prometheus có thể thay đổi do phiên bản Spring Boot/Micrometer, dù Spring AI vẫn phát cùng observation.

### 2.1. Observation name

Observation là đơn vị instrumentation ở Spring ecosystem. Spring AI tạo observation quanh các operation như ChatClient, advisor, model, tool và vector store.

Ví dụ:

- `spring.ai.chat.client`
- `spring.ai.advisor`
- `gen_ai.client.operation`
- `spring.ai.tool`
- `db.vector.client.operation`

Observation name thường được dùng làm tên meter gốc. Nó không nhất thiết là tên span hiển thị trong trace.

### 2.2. Contextual span name

Micrometer Observation có thể tạo span name theo convention và context. Tool observation có tên gốc `spring.ai.tool`, nhưng contextual name chứa action và tool name. Đây là nơi Spring AI thay đổi `tool_call` thành `execute_tool` trong migration lên 2.0.

Không viết dashboard hoặc trace search chỉ dựa trên một chuỗi span name nếu instrumentation có contextual name. Nên giữ thêm attribute ổn định để lọc operation.

### 2.3. Metric name và tag

Một Timer của Micrometer có thể được export thành nhiều series:

- `_seconds_count`: số operation hoàn tất;
- `_seconds_sum`: tổng thời gian;
- `_seconds_max`: thời gian lớn nhất trong cửa sổ đo;
- active long-task timer: số lượng/thời gian operation đang chạy.

Tag của Micrometer được export thành label. Ví dụ `gen_ai.operation.name` thành `gen_ai_operation_name` trong Prometheus.

Vì vậy, dashboard có thể hỏng khi **tag value** thay đổi dù metric name vẫn tồn tại. Hãy kiểm tra cả tên series lẫn label set.

## 3. Ma trận thay đổi chính theo phiên bản

Bảng này tổng hợp các mốc được xác nhận từ Spring AI 1.0.9 reference, Javadocs 1.1.x, migration notes 2.0 và reference 2.1.0. Một số khác biệt nằm ở Spring Boot/Micrometer exporter chứ không phải Spring AI.

| Thành phần | Spring AI 1.0.x/1.1.x | Spring AI 2.0.x/2.1.x | Ảnh hưởng |
|---|---|---|---|
| Tool observation name | `spring.ai.tool` | `spring.ai.tool` | Meter gốc vẫn là tool observation |
| Tool span contextual name | `tool_call <tool-name>` | `execute_tool <tool-name>` | Trace search/grouping theo span name cần sửa |
| Tool `gen_ai.operation.name` | `framework` | `execute_tool` | Prometheus label/filter thay đổi |
| Tool `spring.ai.kind` | `tool_call` | `tool_call` | Giá trị này vẫn mô tả loại API của Spring AI |
| Tool `spring.ai.tool.definition.name` | Có | Có | Tiếp tục dùng để group theo tool |
| Tool `spring.ai.tool.type` | Chưa có trong convention cũ đã đối chiếu | Thêm mới, mặc định `function` | Có thêm label/dimension |
| Tool `spring.ai.tool.call.id` | Chưa có trong convention cũ đã đối chiếu | Thêm span attribute | Liên kết proposal/callback; không dùng làm metric tag |
| Advisor name | High-cardinality | Low-cardinality | Có thể thay đổi số metric series |
| Advisor `spring.ai.advisor.type` | Deprecated | Không còn trong bảng convention hiện hành | Không dùng làm dimension mới |
| Active timer Prometheus | `*_active_count` trong tài liệu Spring Boot 3/Spring AI 1.0 | `*_active_seconds_count/sum/max` trong metrics reference 2.1.1-SNAPSHOT | Cần cập nhật query theo Spring Boot/Micrometer |
| GenAI provider key | Spring AI dùng `gen_ai.system` | Spring AI 2.1 vẫn tài liệu hóa `gen_ai.system` | Không tự đổi thành OTel `gen_ai.provider.name` nếu chưa đổi instrumentation |

### 3.1. Điểm migration quan trọng nhất: tool calling

Spring AI upgrade notes cho 2.0 ghi rõ bốn thay đổi:

1. Span name: `tool_call <tool-name>` thành `execute_tool <tool-name>`;
2. `gen_ai.operation.name`: `framework` thành `execute_tool`;
3. Thêm `spring.ai.tool.type`, ví dụ `function`;
4. Thêm `spring.ai.tool.call.id` vào span để giữ ID tool call do chat model nhận diện.

Đây là thay đổi có thể làm dashboard và trace query mất kết quả mà không làm ứng dụng fail startup. Một truy vấn đang lọc `gen_ai_operation_name="framework"` để lấy tool calls sẽ không còn đúng sau migration.

### 3.2. Không nhầm `spring.ai.kind` với `gen_ai.operation.name`

Trong tool observation hiện hành:

- `gen_ai.operation.name=execute_tool`: mô tả operation;
- `gen_ai.system=spring_ai`: provider/framework tạo observation;
- `spring.ai.kind=tool_call`: loại framework API;
- `spring.ai.tool.definition.name`: canonical tool name;
- `spring.ai.tool.type=function`: loại tool.

Hai attribute đầu có ý nghĩa khác với `spring.ai.kind`. Đừng thay mọi filter `framework` thành `execute_tool` nếu filter đó đang dùng cho ChatClient hoặc Advisor. Với các observation framework-level này, `framework` vẫn là giá trị được tài liệu Spring AI 2.1 mô tả.

## 4. Đối chiếu ChatClient và Advisor attributes

Ngoài tool calling, một số thuộc tính của ChatClient/Advisor đã được đánh dấu deprecated hoặc thay đổi cardinality.

### 4.1. ChatClient

Spring AI 1.0.9 reference liệt kê các high-cardinality attributes cũ:

| Thuộc tính cũ | Trạng thái/ý nghĩa trong 1.0.9 | Thay thế được tài liệu chỉ ra |
|---|---|---|
| `spring.ai.chat.client.advisor.params` | Deprecated | Conversation ID chuyển sang `spring.ai.chat.client.conversation.id` |
| `spring.ai.chat.client.system.params` | Deprecated | `gen_ai.prompt` |
| `spring.ai.chat.client.system.text` | Deprecated | `gen_ai.prompt` |
| `spring.ai.chat.client.user.params` | Deprecated | `gen_ai.prompt` |
| `spring.ai.chat.client.user.text` | Deprecated | `gen_ai.prompt` |
| `spring.ai.chat.client.tool.function.names` | Deprecated | `spring.ai.chat.client.tool.names` |
| `spring.ai.chat.client.tool.function.callbacks` | Deprecated | `spring.ai.chat.client.tool.names` |

Trong reference Spring AI 2.1, danh sách ChatClient high-cardinality keys hiện hành gồm:

- `spring.ai.chat.client.advisors`;
- `spring.ai.chat.client.conversation.id`;
- `spring.ai.chat.client.tool.names`.

Trang hiện hành không còn liệt kê các trường deprecated nói trên. Khi nâng cấp, hãy chuyển dashboard sang các field được hỗ trợ hiện tại và kiểm tra trace thực tế trước khi xóa hoàn toàn tương thích với dữ liệu cũ.

### 4.2. Advisor

| Thuộc tính | Spring AI 1.0.x | Spring AI 2.1 |
|---|---|---|
| `gen_ai.operation.name` | Low-cardinality, `framework` | Low-cardinality, `framework` |
| `gen_ai.system` | Low-cardinality, `spring_ai` | Low-cardinality, `spring_ai` |
| `spring.ai.advisor.type` | Low-cardinality, deprecated | Không còn trong bảng convention hiện hành |
| `spring.ai.advisor.name` | High-cardinality | Low-cardinality |
| `spring.ai.advisor.order` | High-cardinality | High-cardinality |

Việc chuyển `spring.ai.advisor.name` từ high-cardinality sang low-cardinality có thể làm dimension này xuất hiện trên metrics. Chỉ nên giữ advisor names là tập hữu hạn, ổn định; không tạo tên advisor động theo user, request hay session.

### 4.3. Prompt và completion logging

Các property cần phân biệt với span attributes:

- `spring.ai.chat.client.observations.log-prompt`;
- `spring.ai.chat.client.observations.log-completion`;
- `spring.ai.chat.observations.log-prompt`;
- `spring.ai.chat.observations.log-completion`.

Các property này kiểm soát việc ghi nội dung prompt/completion để debug. Chúng không phải metric names hoặc span names. Mặc định đều `false`; bật chúng có thể đưa dữ liệu nhạy cảm vào log/trace.

## 5. Đối chiếu tên metric qua Micrometer và Prometheus

Spring AI đăng ký meter bằng Micrometer với tên dạng lowercase dot notation. Registry/exporter chuyển tên sang format đích.

Ví dụ:

| Observation/meter name | Prometheus series cơ bản |
|---|---|
| `spring.ai.chat.client` | Reference stable 2.1.0 liệt kê `gen_ai_chat_client_operation_seconds_count`; metrics reference 2.1.1-SNAPSHOT dùng prefix `spring_ai_chat_client` |
| `spring.ai.advisor` | `spring_ai_advisor_seconds_count`, `_sum`, `_max` |
| `gen_ai.client.operation` | `gen_ai_client_operation_seconds_count`, `_sum`, `_max` |
| `gen_ai.client.token.usage` | `gen_ai_client_token_usage_total` |
| `spring.ai.tool` | `spring_ai_tool_seconds_count`, `_sum`, `_max` |
| `db.vector.client.operation` | `db_vector_client_operation_seconds_count`, `_sum`, `_max` |

Dấu `...` trong bảng suffix có nghĩa là phần prefix được giữ nguyên và hậu tố thay theo loại meter. Không ghép một chuỗi suffix vào tên gốc rồi giả định mọi registry đều xuất cùng một format.

### 5.1. Meter name và Prometheus name không giống nhau

Với Micrometer:

~~~java
registry.timer("spring.ai.tool");
~~~

Trong Prometheus, tên timer có thể được chuẩn hóa thành `spring_ai_tool_seconds_count`, `spring_ai_tool_seconds_sum` và `spring_ai_tool_seconds_max`.

Trong khi đó, Actuator `/actuator/metrics` truy vấn theo meter name gốc có dấu chấm:

~~~text
/actuator/metrics/spring.ai.tool
~~~

Không dùng `spring_ai_tool_seconds_count` làm selector cho endpoint Actuator metrics. Đây là tên sau khi Prometheus registry chuẩn hóa.

### 5.2. Có khác biệt giữa metrics reference stable và snapshot

Tài liệu observability stable 2.1.0 liệt kê ChatClient series dạng `gen_ai_chat_client_operation_seconds_*`. Metrics reference của nhánh 2.1.1-SNAPSHOT lại mô tả timer prefix `spring_ai_chat_client`, được export thành `spring_ai_chat_client_seconds_*`. Đây là khác biệt giữa hai tài liệu/version line; không nên chọn một tên rồi áp dụng cho mọi bản 2.1.x.

Khi nâng cấp, kiểm tra chính xác Spring AI artifact và Spring Boot/Micrometer đã resolve, rồi scrape `/actuator/prometheus` để xác nhận prefix thật. Ghi rõ version của metrics schema trong dashboard repository và tránh dùng trang SNAPSHOT làm contract cho bản stable.

### 5.3. Active timer thay đổi theo Spring Boot

Tài liệu Spring AI 1.0 và reference observability stable 2.1.0 vẫn liệt kê long-task timer với hậu tố `active_count`. Metrics reference 2.1.1-SNAPSHOT minh họa các series active theo dạng:

- `gen_ai_client_operation_active_seconds_count`;
- `gen_ai_client_operation_active_seconds_sum`;
- `gen_ai_client_operation_active_seconds_max`.

Đây là khác biệt giữa tài liệu stable và snapshot ở lớp Spring Boot/Micrometer export long-task timer. Không kết luận Spring AI đã đổi observation name chỉ vì active series có hậu tố mới. Kiểm tra Spring Boot và Micrometer version trong dependency tree, rồi xác nhận bằng scrape thực tế trước khi sửa query.

## 6. Thay đổi semantic convention của OpenTelemetry

Spring AI sử dụng Micrometer Observation và các attribute mang tiền tố `gen_ai.*`. Các tên này có liên quan đến OpenTelemetry GenAI semantic conventions, nhưng không nên giả định mọi giá trị và operation đều tương đương 1:1.

### 6.1. `gen_ai.system` và `gen_ai.provider.name`

OpenTelemetry semantic convention registry hiện đánh dấu `gen_ai.system` là deprecated và giới thiệu `gen_ai.provider.name`. Tài liệu GenAI conventions mới đã chuyển sang repository riêng `open-telemetry/semantic-conventions-genai`; trang client inference hiện ghi trạng thái conventions là Development, vì vậy cần version hóa schema khi ingest/transform.

Trong khi đó, Spring AI 2.1 reference vẫn mô tả `gen_ai.system`:

- `spring_ai` cho các observation thuộc framework như ChatClient, Advisor và Tool;
- Tên provider, ví dụ `openai`, cho model operation.

Điều này có nghĩa `gen_ai.system=spring_ai` ở một framework span không nhất thiết có nghĩa Spring AI là inference provider. Nó xác định instrumentation system của observation framework-level.

**Không áp dụng transform toàn cục** `gen_ai.system` → `gen_ai.provider.name`. Với model inference span, có thể ánh xạ provider nếu semantics khớp và có quy tắc rõ. Với ChatClient/Advisor/Tool framework observation, cần giữ đúng ý nghĩa framework hoặc dùng namespace riêng.

### 6.2. `gen_ai.operation.name`

OpenTelemetry GenAI convention hiện dùng các operation như `chat`, `generate_content`, `embeddings`, `execute_tool` và nhiều operation khác. Spring AI có các observation framework-level dùng `framework`, chẳng hạn ChatClient và Advisor.

Ví dụ:

| Observation | `gen_ai.operation.name` trong Spring AI 2.1 |
|---|---|
| ChatClient call/stream | `framework` |
| Advisor execution | `framework` |
| Chat model operation | `chat` |
| Embedding model operation | `embeddings`/operation tương ứng |
| Tool execution | `execute_tool` |
| Decision model | `decision` |

Đừng thay mọi giá trị `framework` thành `chat`. Một ChatClient operation có thể bao gồm advisor, model calls, retrieval và tool calls; nó là operation ở tầng framework, không phải một inference call đơn lẻ.

### 6.3. Metric/span names của OTel không phải Spring AI meter names

GenAI semantic conventions mới mô tả inference span `gen_ai.client.inference` và metric `gen_ai.client.inference.duration`, cùng token metrics riêng. Spring AI hiện dùng Micrometer observation `gen_ai.client.operation` và Prometheus series như `gen_ai_client_operation_seconds_count`.

Hai bộ tên này không thể hoán đổi chỉ bằng cách thay dấu chấm hoặc dấu gạch dưới. Chúng có thể đo các boundary khác nhau:

- Spring AI model observation đo thời gian method `ChatModel.call()`/`stream()` theo instrumentation;
- OTel client inference span định nghĩa logical client call tới GenAI service;
- HTTP client span đo từng lần gửi HTTP, có thể bao gồm retry.

Nếu tổ chức muốn chuẩn hóa toàn bộ telemetry theo OTel GenAI convention, hãy xác định boundary, attribute mapping, version và ownership trước; tránh phát đồng thời hai metric cùng ý nghĩa rồi cộng chúng thành số liệu gấp đôi.

## 7. Ví dụ truy vấn Prometheus trước và sau nâng cấp

Giả sử dashboard cũ đo số tool calls theo tool name. Metric prefix `spring_ai_tool` vẫn có thể giữ nguyên, nhưng label `gen_ai_operation_name` thay đổi.

### 7.1. Truy vấn cũ — Spring AI 1.x

~~~promql
sum by (spring_ai_tool_definition_name) (
  rate(spring_ai_tool_seconds_count{
    gen_ai_operation_name="framework"
  }[5m])
)
~~~

### 7.2. Truy vấn mới — Spring AI 2.x

~~~promql
sum by (spring_ai_tool_definition_name) (
  rate(spring_ai_tool_seconds_count{
    gen_ai_operation_name="execute_tool"
  }[5m])
)
~~~

### 7.3. Truy vấn tương thích khi chạy song song hai release

Trong giai đoạn rolling deployment, cả pod 1.x và 2.x có thể cùng gửi metrics. Có thể chấp nhận cả hai operation values:

~~~promql
sum by (spring_ai_tool_definition_name) (
  rate(spring_ai_tool_seconds_count{
    gen_ai_operation_name=~"framework|execute_tool"
  }[5m])
)
~~~

Đây là recording rule tạm thời cho migration window. Sau khi mọi instance đã nâng cấp và dữ liệu cũ hết retention, thu hẹp selector về `execute_tool` để phát hiện nếu một instance cũ quay lại.

### 7.4. Tỷ lệ lỗi tool calls

Metrics reference hiện dùng tag `error` với exception class khi lỗi và `none` khi thành công. Ví dụ:

~~~promql
sum by (spring_ai_tool_definition_name) (
  rate(spring_ai_tool_seconds_count{
    gen_ai_operation_name="execute_tool",
    error!="none"
  }[5m])
)
/
sum by (spring_ai_tool_definition_name) (
  rate(spring_ai_tool_seconds_count{
    gen_ai_operation_name="execute_tool"
  }[5m])
)
~~~

Nếu có thể chia cho zero khi không có call, bọc query bằng `clamp_min` hoặc chỉ hiển thị khi denominator lớn hơn zero. Không gộp exception classes thành một tag có cardinality không kiểm soát.

### 7.5. Token usage

Spring AI export token usage counter `gen_ai_client_token_usage_total` với label `gen_ai_token_type` có giá trị `input`, `output`, `total`.

Ví dụ tổng token input và output theo model:

~~~promql
sum by (gen_ai_request_model, gen_ai_token_type) (
  rate(gen_ai_client_token_usage_total{
    gen_ai_token_type!="total"
  }[5m])
) * 60
~~~

Không cộng cả `input`, `output` và `total`, vì `total` đã bằng tổng hai loại còn lại. Làm như vậy sẽ đếm token hai lần.

## 8. Tên span và trace search trước/sau

Một trace backend thường cho phép lọc theo span name và attributes.

### 8.1. Trước nâng cấp

Ví dụ trace tool span trong Spring AI 1.x:

~~~text
Span name: tool_call lookup_order

Attributes:
  gen_ai.operation.name = framework
  gen_ai.system = spring_ai
  spring.ai.kind = tool_call
  spring.ai.tool.definition.name = lookup_order
~~~

### 8.2. Sau nâng cấp

Trong Spring AI 2.0+:

~~~text
Span name: execute_tool lookup_order

Attributes:
  gen_ai.operation.name = execute_tool
  gen_ai.system = spring_ai
  spring.ai.kind = tool_call
  spring.ai.tool.definition.name = lookup_order
  spring.ai.tool.type = function
  spring.ai.tool.call.id = call_abc123
~~~

`spring.ai.tool.call.id` giúp nối tool span với proposal từ chat model. Đây là high-cardinality span attribute, hữu ích cho trace correlation; không đưa nó thành Prometheus label.

### 8.3. Cập nhật trace query

| Query cũ | Query mới |
|---|---|
| Span name bắt đầu bằng `tool_call ` | Span name bắt đầu bằng `execute_tool ` |
| `gen_ai.operation.name = framework` trong tool span | `gen_ai.operation.name = execute_tool` |
| Group theo `spring.ai.tool.definition.name` | Giữ group theo tool name |
| Không có `spring.ai.tool.type` | Có thể filter/group theo tool type |
| Không có `spring.ai.tool.call.id` | Có thể correlate proposal/result bằng call ID |

Trong migration window, trace query có thể chấp nhận cả hai span name. Không dùng span name làm contract duy nhất cho application logic; trace adapter nên nhận diện tool spans bằng combination của operation attribute, kind và tool name.

## 9. Cardinality: tag nào được dùng cho metrics?

Spring AI phân biệt low-cardinality và high-cardinality key values:

- Low-cardinality values được thêm vào metrics và traces;
- High-cardinality values chỉ được thêm vào traces.

| Attribute | Dùng cho metrics? | Dùng cho traces? | Lý do |
|---|---:|---:|---|
| `gen_ai.operation.name` | Có | Có | Tập operation hữu hạn |
| `gen_ai.system` | Có | Có | Framework/provider hữu hạn |
| `gen_ai.request.model` | Có | Có | Model names thường có tập triển khai hữu hạn |
| `spring.ai.tool.definition.name` | Có | Có | Tool registry có tập tên hữu hạn |
| `spring.ai.tool.type` | Có | Có | Loại tool có tập giá trị nhỏ |
| `spring.ai.advisor.name` (2.1) | Có | Có | Chỉ an toàn nếu tên advisor ổn định |
| `spring.ai.advisor.order` | Không | Có | Giá trị/order có thể thay đổi theo cấu hình |
| `spring.ai.tool.call.id` | Không | Có | Mỗi lần gọi có ID riêng |
| `spring.ai.chat.client.conversation.id` | Không | Có | ID theo hội thoại |
| `spring.ai.tool.call.arguments` | Không | Chỉ khi opt-in và đã bảo vệ | Có thể chứa PII/secrets |
| `spring.ai.tool.call.result` | Không | Chỉ khi opt-in và đã bảo vệ | Có thể chứa dữ liệu nghiệp vụ nhạy cảm |

Một key có mặt trên span không có nghĩa nó nên trở thành metric label. Nếu đưa conversation ID hoặc tool call ID vào metrics, số time series có thể tăng theo traffic và gây áp lực lên Prometheus.

### 9.1. Advisor name chuyển từ high sang low cardinality

Trong Spring AI 1.0 reference, `spring.ai.advisor.name` nằm trong bảng high-cardinality. Trong Spring AI 2.1, nó nằm trong low-cardinality keys của Advisor observation. Điều này làm nó xuất hiện trên meter tags theo convention mới.

Trước khi tận dụng dimension mới, hãy kiểm tra advisor names có hữu hạn và ổn định không. Tránh tạo advisor name bằng cách nối user ID, request ID hoặc tenant ID.

## 10. Quy trình migration dashboard và alert

Không sửa hàng loạt query ngay khi đọc release notes. Hãy xác định dữ liệu thực tế mà từng version phát ra.

### 10.1. Lập inventory trước nâng cấp

Ghi lại cho mỗi dashboard/alert:

- Metric name hoặc observation name;
- Label/tag đang dùng để lọc;
- Span name và span attributes;
- Backend/exporter và version;
- Query owner, threshold và thời gian lưu dữ liệu;
- Mục đích đo: ChatClient latency, model latency, tool count, tool failure, token usage hay vector-store latency.

Ví dụ inventory:

| Dashboard panel | Dữ liệu hiện tại | Thay đổi cần kiểm tra |
|---|---|---|
| Tool calls/min | `spring_ai_tool_seconds_count`, `gen_ai_operation_name=framework` | Value thành `execute_tool` |
| Tool latency | `spring_ai_tool_seconds_sum/count` | Metric prefix và label set |
| Tool error rate | `error!="none"` | Giữ error tag, đổi operation filter |
| Tool type breakdown | Chưa có | Thêm `spring_ai_tool_type` sau nâng cấp |
| Trace search | Span `tool_call *` | Span `execute_tool *`, call ID mới |
| Advisor latency | `spring_ai_advisor` | Advisor name nay là low-cardinality |
| Model in-flight | `*_active_count` | Kiểm tra `*_active_seconds_count` theo Boot version |

### 10.2. Chạy old và new query trong migration window

Khi rolling deployment, Prometheus có thể thu thập series từ cả version cũ và mới. Dùng selector tương thích tạm thời:

~~~promql
sum by (spring_ai_tool_definition_name) (
  rate(spring_ai_tool_seconds_count{
    gen_ai_operation_name=~"framework|execute_tool"
  }[5m])
)
~~~

Ghi rõ thời điểm bắt đầu/kết thúc migration. Sau khi mọi instance đã nâng cấp và retention đã xóa dữ liệu cũ, bỏ `framework` khỏi selector để phát hiện nếu một instance cũ quay lại.

### 10.3. Recording rule để ổn định dashboard

Nếu có nhiều dashboard, tạo recording rule dùng chung:

~~~yaml
groups:
  - name: spring-ai-observability-compat
    interval: 30s
    rules:
      - record: spring_ai:tool_calls_per_second:rate5m
        expr: |
          sum by (spring_ai_tool_definition_name) (
            rate(spring_ai_tool_seconds_count{
              gen_ai_operation_name=~"framework|execute_tool"
            }[5m])
          )
~~~

Dashboard dùng recording rule thay vì lặp lại filter theo từng version. Khi migration kết thúc, chỉ cần sửa rule một lần.

### 10.4. Không gộp active và completed duration

Active long-task timer biểu diễn operation đang chạy. Timer completed biểu diễn operation đã kết thúc. Đừng cộng `active_seconds_sum` vào `seconds_sum` để tính tổng latency; hai series có lifecycle và ý nghĩa khác nhau.

## 11. Xác minh telemetry thực tế trong ứng dụng

Tài liệu cho biết convention dự kiến. Registry của ứng dụng cho biết dữ liệu đang được phát ra với dependency và cấu hình thực tế.

### 11.1. Kiểm tra meter gốc qua Actuator

Nếu metrics endpoint đã được expose, kiểm tra meter name gốc:

~~~text
GET /actuator/metrics/spring.ai.tool
GET /actuator/metrics/gen_ai.client.operation
GET /actuator/metrics/spring.ai.advisor
~~~

Dùng tên có dấu chấm như Micrometer registry, không dùng tên Prometheus đã đổi thành underscore.

### 11.2. Kiểm tra series qua Prometheus endpoint

~~~text
GET /actuator/prometheus
~~~

Tìm các series:

~~~text
spring_ai_tool_seconds_count
spring_ai_tool_seconds_sum
spring_ai_tool_seconds_max
gen_ai_client_operation_seconds_count
gen_ai_client_token_usage_total
~~~

Kiểm tra cả label names và values:

- `gen_ai_operation_name`;
- `gen_ai_system`;
- `spring_ai_kind`;
- `spring_ai_tool_definition_name`;
- `spring_ai_tool_type`;
- `error`.

Nếu meter có nhưng series không có, kiểm tra registry/exporter, meter filter, metrics enablement và việc operation đã hoàn tất hay chưa.

### 11.3. Kiểm tra trace backend

Thực hiện ít nhất một request có tool call thành công và một request có tool call lỗi. Xác nhận:

- Tool span có tên contextual đúng version;
- Parent/child relation vẫn đúng trong trace;
- `gen_ai.operation.name` có giá trị đúng;
- `spring.ai.tool.definition.name` có canonical tool name;
- `spring.ai.tool.type` và `spring.ai.tool.call.id` có mặt ở version mới;
- Error span có status/error attributes phù hợp;
- Arguments/result không bị export khi chưa bật filter.

Spring AI mặc định không export tool arguments/result. Property `spring.ai.tools.observations.include-content` mặc định `false`; chỉ bật sau khi có policy redaction và kiểm tra quyền truy cập.

### 11.4. Kiểm tra dependency tree

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.ai,org.springframework.boot,io.micrometer
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Không suy luận active metric suffix chỉ từ Spring AI version. Spring Boot và Micrometer version ảnh hưởng cách timer được export.

## 12. Kiểm thử compatibility cho metrics và spans

Hãy tạo integration fixture cho từng release line. Dùng tool callback stub và model provider test double nếu phù hợp; không cần gọi hệ thống production.

| Test | Tình huống | Kỳ vọng |
|---|---|---|
| **TC01 — ChatClient observation** | Gọi `ChatClient.call()` | Có observation `spring.ai.chat.client` |
| **TC02 — ChatClient streaming** | Gọi `ChatClient.stream()` | Có observation, stream tag đúng |
| **TC03 — Model operation** | Gọi ChatModel | Có `gen_ai.client.operation` |
| **TC04 — Token usage** | Provider trả usage metadata | Counter token có input/output/total |
| **TC05 — Tool observation name** | Thực thi tool | Observation gốc `spring.ai.tool` |
| **TC06 — 1.x tool operation** | Chạy fixture với Spring AI 1.0.x/1.1.x | `gen_ai.operation.name=framework` |
| **TC07 — 1.x tool span name** | Trace tool call ở 1.x | Contextual name `tool_call <tool-name>` |
| **TC08 — 2.x tool operation** | Chạy fixture với Spring AI 2.x | `gen_ai.operation.name=execute_tool` |
| **TC09 — 2.x tool span name** | Trace tool call ở 2.x | Contextual name `execute_tool <tool-name>` |
| **TC10 — Tool type** | Tool function được thực thi | Có `spring.ai.tool.type=function` |
| **TC11 — Tool call ID** | Model trả tool call ID | Span có `spring.ai.tool.call.id` |
| **TC12 — Tool name** | Nhiều tool khác nhau | Có `spring.ai.tool.definition.name` |
| **TC13 — Error tag** | Tool callback ném exception | `error` khác `none` |
| **TC14 — Tool content off** | Không bật include-content | Không có raw arguments/result |
| **TC15 — Tool content on** | Bật trong fixture đã redact | Có content theo policy test |
| **TC16 — Advisor name cardinality** | Chạy advisor có tên cố định | Tag behavior khớp version |
| **TC17 — Advisor type** | Dùng 2.1 convention | Không phụ thuộc `spring.ai.advisor.type` |
| **TC18 — Conversation ID** | Chat memory bật | ID chỉ nằm ở trace/high-cardinality |
| **TC19 — Prometheus timer** | Scrape sau operation hoàn tất | Có count/sum/max |
| **TC20 — Active timer** | Giữ operation chạy trong lúc scrape | Active series đúng Spring Boot version |
| **TC21 — Mixed release labels** | Scrape pod 1.x và 2.x cùng lúc | Query compatibility đếm cả hai operation values |
| **TC22 — OTel provider mapping** | Export span sang OTLP | Không đổi `gen_ai.system` toàn cục sai ngữ nghĩa |
| **TC23 — No duplicate accounting** | Export cùng operation qua nhiều pipeline | Dashboard không cộng trùng series |
| **TC24 — Regression dashboards** | Chạy sample traffic sau migration | Panel/alert không bị rỗng ngoài dự kiến |

### 12.1. Assertion nên có trong CI

- Kiểm tra observation name và tag values ở từng version line;
- Kiểm tra span contextual name và parent-child relation;
- Kiểm tra Prometheus series sau naming convention;
- Kiểm tra active long-task timer theo Spring Boot version;
- Kiểm tra high-cardinality values không trở thành metric tags;
- Kiểm tra token usage không cộng input/output/total trùng nhau;
- Kiểm tra recording rules xử lý dữ liệu 1.x và 2.x trong giai đoạn rolling deployment;
- Kiểm tra trace content không bật ngoài ý muốn.

## 13. Quy trình nâng cấp observability trong CI/CD

1. **Khóa baseline:** ghi Spring AI BOM, Spring Boot, Micrometer, tracing bridge và exporter.
2. **Inventory dashboards:** xuất PromQL, labels, trace filters, alert rules và recording rules đang dùng.
3. **Đối chiếu release notes:** xác định breaking changes của span name, attribute value, cardinality và metric export.
4. **Tạo fixture:** một ChatClient call, model call, advisor, vector query, tool success và tool failure.
5. **Chạy trên version cũ:** lưu metric exposition, trace snapshots và label sets.
6. **Nâng dependency đồng bộ:** dùng BOM và giữ các module cùng release line.
7. **Chạy trên version mới:** thu cùng fixture với cùng exporter/backend.
8. **Diff telemetry:** so observation names, span names, attributes, metric names, units và cardinality.
9. **Cập nhật query:** đổi operation filters, span search và active timer suffix.
10. **Kiểm tra rolling deployment:** đảm bảo query tạm thời đọc được dữ liệu từ hai version.
11. **Review cardinality/security:** không thêm IDs hoặc raw content vào metric labels.
12. **Phát hành:** giữ recording rules tương thích trong thời gian retention dữ liệu cũ còn tồn tại.

### Checklist trước khi merge

- [ ] Đã phân biệt observation name, span name, metric name và attributes.
- [ ] Đã cập nhật tool span `tool_call` → `execute_tool`.
- [ ] Đã cập nhật `gen_ai.operation.name` cho tool span.
- [ ] Đã kiểm tra `spring.ai.tool.type` và `spring.ai.tool.call.id`.
- [ ] Đã rà các ChatClient/Advisor attributes deprecated.
- [ ] Đã kiểm tra advisor name cardinality.
- [ ] Đã kiểm tra active timer suffix theo Spring Boot/Micrometer.
- [ ] Đã kiểm tra `/actuator/metrics` và `/actuator/prometheus`.
- [ ] Đã kiểm tra trace backend với tool success/error fixtures.
- [ ] Đã cập nhật PromQL, Grafana panels, alerts và recording rules.
- [ ] Đã xác minh không có high-cardinality metric labels.
- [ ] Đã tránh transform `gen_ai.system` toàn cục thành `gen_ai.provider.name`.
- [ ] Đã chạy dashboard regression trong rolling deployment.

## 14. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ sửa metric name, không sửa tag value | Query vẫn rỗng | Kiểm tra label `gen_ai_operation_name` |
| Nghĩ `spring.ai.tool` là span name | Trace search sai | Tách observation name và contextual span name |
| Thay `framework` ở mọi observation | ChatClient/Advisor metrics bị lọc mất | Chỉ đổi filter tool sang `execute_tool` |
| Coi `spring.ai.kind` và `gen_ai.operation.name` là một | Phân loại sai operation | Giữ hai semantics riêng |
| Coi Prometheus series name là meter name | Actuator metrics endpoint không tìm thấy | Query bằng dot notation ở Actuator |
| Gán active timer suffix cho Spring AI | Chẩn đoán sai version | Kiểm tra Spring Boot/Micrometer |
| Đưa tool call ID vào metric label | Cardinality bùng nổ | Chỉ giữ ID trên span |
| Group theo advisor name động | Metrics tốn bộ nhớ | Dùng tên advisor hữu hạn |
| Cộng `input`, `output`, `total` token | Đếm token gấp đôi | Chỉ cộng input+output hoặc total |
| Đổi `gen_ai.system` thành `gen_ai.provider.name` toàn cục | Mất ý nghĩa framework-level | Mapping theo từng loại observation |
| Bật tool content để debug production | Lộ dữ liệu đầu vào/kết quả | Redact và kiểm soát access trước |
| Không kiểm rolling deployment | Dashboard trống khi hai version chạy cùng lúc | Query tương thích có thời hạn |

## 15. Bài luyện tập

### Bài 1 — Tool span không còn xuất hiện

Sau khi nâng Spring AI 1.1 lên 2.0, trace search `tool_call lookup_order` không trả kết quả. Hãy nêu tên span mới và attribute cần kiểm tra.

### Bài 2 — Metric vẫn có nhưng dashboard về zero

Series `spring_ai_tool_seconds_count` vẫn xuất hiện, nhưng panel lọc `gen_ai_operation_name="framework"` trả zero. Cần đổi điều kiện nào?

### Bài 3 — Không thấy tool type ở dashboard

Spring AI 2.x đã có `spring.ai.tool.type`, nhưng dashboard vẫn không group được theo loại tool. Hãy kiểm tra những lớp nào: observation, meter tag, Prometheus label hay exporter.

### Bài 4 — Active metric đổi tên

Ứng dụng nâng từ Spring Boot 3 lên Spring Boot 4 và query `gen_ai_client_operation_active_count` không còn dữ liệu. Bạn cần kiểm tra tên series nào và vì sao?

### Bài 5 — Advisor name xuất hiện trong metrics

Sau nâng cấp, số series tăng theo `spring_ai_advisor_name`. Bạn cần kiểm tra convention nào và giới hạn cardinality ra sao?

### Bài 6 — OpenTelemetry provider key

Một collector rule đổi mọi `gen_ai.system` thành `gen_ai.provider.name`. Vì sao điều này có thể sai với span ChatClient của Spring AI?

### Bài 7 — Token usage

Dashboard token cộng ba label `input`, `output`, `total`. Vì sao tổng bị cao hơn thực tế? Viết truy vấn đúng.

### Bài 8 — Tool call ID

Nhóm vận hành muốn lọc metrics theo từng `spring.ai.tool.call.id`. Có nên thêm ID này thành Prometheus label không? Đề xuất cách truy vết.

### Bài 9 — Mixed deployment

Một nửa pod dùng Spring AI 1.x và nửa còn lại dùng 2.x. Viết selector tạm thời để đếm tool calls từ cả hai nhóm.

### Bài 10 — Migration checklist

Nêu các fixture tối thiểu phải chạy trước khi merge thay đổi Spring AI observability.

### Gợi ý đáp án

1. Span mới là `execute_tool lookup_order`; kiểm tra `gen_ai.operation.name=execute_tool`, `spring.ai.tool.definition.name` và `spring.ai.tool.call.id`.
2. Đổi filter tool sang `gen_ai_operation_name="execute_tool"`; chỉ áp dụng cho tool observation, không áp dụng cho ChatClient/Advisor.
3. Kiểm tra low-cardinality key có được tạo, meter có đăng ký, Prometheus exposition có label `spring_ai_tool_type` và exporter không loại bỏ label.
4. Kiểm tra `gen_ai_client_operation_active_seconds_count`; đây là khác biệt export long-task timer của Spring Boot/Micrometer, không nhất thiết là đổi observation name.
5. `spring.ai.advisor.name` chuyển từ high sang low cardinality. Đảm bảo tên advisor hữu hạn, ổn định, không gắn user/request ID.
6. `gen_ai.system=spring_ai` ở ChatClient biểu thị framework instrumentation. Không thể coi `spring_ai` là provider inference rồi đổi thành `gen_ai.provider.name` mà không xác định semantics.
7. Không cộng cả ba. Dùng `gen_ai_token_type!="total"` để cộng input và output, hoặc lọc riêng `gen_ai_token_type="total"`.
8. Không. Đây là high-cardinality ID. Dùng span attribute và trace search để mở đúng tool call.
9. `gen_ai_operation_name=~"framework|execute_tool"` trong migration window; xóa `framework` sau khi hết dữ liệu cũ.
10. ChatClient call/stream, model call, advisor, vector query, tool success, tool error, Prometheus scrape, active timer và trace correlation.

## Tài liệu tham khảo

- [Spring AI 1.0 — Observability](https://docs.spring.io/spring-ai/reference/1.0/observability/index.html): observations, low/high-cardinality keys, tool calling và Prometheus metrics ở dòng 1.0.x.
- [Spring AI 2.1 — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): convention hiện hành của ChatClient, Advisor, model, tool và vector store.
- [Spring AI — Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html): thay đổi tool span name, `gen_ai.operation.name`, `spring.ai.tool.type` và `spring.ai.tool.call.id` khi nâng lên 2.0.
- [Spring AI 2.1-SNAPSHOT — Metrics Reference](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/observability/metrics.html): cách observation được chuyển thành Prometheus series, active timers, token usage và query ví dụ; đây là tài liệu snapshot, cần xác minh theo bản Spring Boot đang resolve.
- [Spring AI 1.1.1 — DefaultToolCallingObservationConvention Javadocs](https://docs.spring.io/spring-ai/docs/1.1.1/api/org/springframework/ai/tool/observation/DefaultToolCallingObservationConvention.html): convention và default observation name `spring.ai.tool`.
- [Spring AI 1.1.1 — Constant Field Values](https://docs.spring.io/spring-ai/docs/1.1.1/api/constant-values.html): xác nhận `DefaultToolCallingObservationConvention.DEFAULT_NAME`.
- [Micrometer — Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html): dot notation, backend naming conventions và tag naming.
- [Spring Boot 3.5 — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): Actuator/Micrometer metrics và endpoint.
- [Spring Boot 4.1 — Metrics](https://docs.spring.io/spring-boot/4.1/reference/actuator/metrics.html): metrics endpoint, registry và long-task timer trên dòng Boot 4.x.
- [OpenTelemetry — GenAI Attribute Registry](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/): trạng thái deprecated của `gen_ai.system` và replacement `gen_ai.provider.name`.
- [OpenTelemetry GenAI — Client Inference](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/client-inference.md): inference span, span name và metric `gen_ai.client.inference.duration`.
- [OpenTelemetry GenAI — Execute Tool](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/execute-tool.md): conventions cho tool execution span và `gen_ai.tool.name`.

**Kết luận:** nâng cấp observability cần kiểm tra riêng observation name, contextual span name, metric series và attributes. Spring AI 2.0 thay tool span `tool_call` bằng `execute_tool`, đổi `gen_ai.operation.name` từ `framework` sang `execute_tool`, đồng thời thêm tool type và tool call ID. Advisor name và một số ChatClient attributes cũng thay đổi cách sử dụng/cardinality; Spring Boot/Micrometer có thể đổi hậu tố active timer độc lập với Spring AI. Hãy kiểm tra telemetry thực tế, cập nhật query theo version, giữ high-cardinality IDs ở traces và chỉ chuẩn hóa sang OpenTelemetry conventions khi semantics đã được xác định. Khi làm được điều đó, dashboard, alerts và trace search sẽ tiếp tục phản ánh đúng chất lượng RAG/tool workflow qua các lần nâng cấp.

