# Tránh cộng trùng thời gian hoặc số lần gọi giữa các lớp

## 1. Vì sao dashboard AI thường hiển thị những con số tưởng như mâu thuẫn?

Một yêu cầu của người dùng đi qua nhiều lớp:

1. HTTP controller nhận request.
2. Service gọi ChatClient.
3. ChatClient chạy advisor chain.
4. Advisor có thể gọi RAG, memory hoặc các advisor khác.
5. ChatModel gửi request tới nhà cung cấp model.
6. Model yêu cầu tools, ứng dụng thực thi tools rồi gọi model thêm lần nữa.
7. Kết quả được trả về service và HTTP response.

Mỗi lớp có thể tạo observation, span hoặc timer riêng. Một ChatClient call có thể mất 3 giây; một advisor span cũng có thể gần 3 giây; model spans cộng lại 1,8 giây; tool spans cộng lại 0,7 giây. Nếu cộng tất cả các con số này, dashboard sẽ báo hơn 8 giây cho một request vốn chỉ mất 3 giây.

Đó không nhất thiết là lỗi instrumentation. Các lớp đang đo **những ranh giới khác nhau**, và nhiều phép đo bao gồm thời gian của lớp bên trong.

Tương tự, một user turn có thể tạo một ChatClient invocation, ba model operations, hai tool executions và nhiều advisor invocations. Cộng các count đó thành “tổng số AI calls” sẽ trộn những đơn vị không cùng nghĩa.

Bài này thuộc chương **ChatClient và advisor** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module học cách đánh giá ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân regression qua các phiên bản prompt, model và pipeline.

Sau bài, bạn có thể:

- Giải thích vì sao thời gian ChatClient, advisor, model và tool có thể lồng nhau.
- Phân biệt inclusive duration, self time và wall-clock duration.
- Đếm đúng ChatClient invocations, model operations, tool executions và advisor invocations.
- Đọc các series seconds_sum và seconds_count mà không cộng trùng.
- Tính mean, rate và percentile theo đúng tầng.
- Tránh double count token usage và tránh gắn nhầm metric với span.
- Thiết kế dashboard, trace review và evaluation budget theo cùng một đơn vị đo.

## 2. Bắt đầu bằng việc xác định đơn vị đo

Trước khi viết PromQL hoặc tạo dashboard, hãy định nghĩa mỗi chỉ số đang đếm điều gì.

| Đơn vị | Một đơn vị được ghi nhận khi nào? | Câu hỏi nó trả lời |
|---|---|---|
| HTTP request | Một request vào endpoint | Người dùng/API gọi ứng dụng bao nhiêu lần? |
| User turn | Một lượt hội thoại logic | Có bao nhiêu lượt người dùng yêu cầu trợ lý? |
| ChatClient invocation | Một lần gọi call() hoặc stream() | ChatClient xử lý bao nhiêu lần? |
| Advisor invocation | Một lần advisor thực sự chạy | Advisor được thực thi bao nhiêu lần? |
| Model operation | Một lần gọi ChatModel.call() hoặc stream() | Model được gọi bao nhiêu lần? |
| Model round | Một iteration của tool/recursive loop | Vòng điều phối gọi model bao nhiêu lần? |
| Tool execution | Một lần ứng dụng thực thi một tool | Công cụ thực sự chạy bao nhiêu lần? |
| Vector operation | Một thao tác add/query/delete/upsert | Vector store được truy cập bao nhiêu lần? |

Các đơn vị có quan hệ một-nhiều. Ví dụ:

~~~text
1 HTTP request
  1 user turn
    1 ChatClient invocation
      3 advisor invocations của cùng một advisor do recursive loop
      3 ChatModel operations
      2 tool executions
      1 vector query
~~~

Không có phép cộng hợp lệ kiểu:

~~~text
1 ChatClient + 3 model + 2 tools + 3 advisors = 9 AI calls
~~~

Con số 9 không đại diện cho user turns, ChatClient invocations, model operations hay tool executions. Nếu cần một chỉ số “tổng operations”, phải định nghĩa rõ loại operation nào được tính và vì sao chúng có thể cộng được.

## 3. Spring AI đo thời gian ở những ranh giới nào?

Spring AI sử dụng Micrometer Observation cho các thành phần chính. Những observation thường gặp:

| Observation | Ranh giới đo | Ý nghĩa duration |
|---|---|---|
| spring.ai.chat.client | ChatClient call() / stream() | Thời gian thực hiện toàn invocation |
| spring.ai.advisor | Một lần thực thi advisor | Thời gian advisor, gồm cả advisor bên trong mà nó gọi |
| gen_ai.client.operation | ChatModel call() / stream() | Thời gian model operation hoàn tất |
| spring.ai.tool | Tool execution | Thời gian thực thi tool |
| db.vector.client.operation | VectorStore operation | Thời gian thao tác vector store |

Điểm quan trọng là observation của advisor được định nghĩa là đo thời gian trong advisor **bao gồm thời gian của các advisor bên trong**. ChatClient observation đo toàn invocation. Model và tool observations đo các operation chuyên biệt hơn.

Vì vậy, các timer này không phải những đoạn thời gian độc lập để cộng lại. Tài liệu Spring AI xác nhận ChatClient đo toàn invocation, còn advisor đo cả thời gian của các advisor bên trong.

## 4. Inclusive duration: thời gian lớp ngoài bao gồm lớp trong

Giả sử chuỗi xử lý có cấu trúc:

~~~mermaid
flowchart TD
    A["ChatClient observation<br/>3.2 s"] --> B["Session advisor<br/>3.1 s"]
    B --> C["ToolCallingAdvisor<br/>2.6 s"]
    C --> D["ChatModel operation #1<br/>0.7 s"]
    C --> E["Tool execution #1<br/>0.3 s"]
    C --> F["ChatModel operation #2<br/>0.6 s"]
    C --> G["Tool execution #2<br/>0.4 s"]
    C --> H["ChatModel operation #3<br/>0.5 s"]
~~~

Các duration trong sơ đồ là ví dụ minh họa. ChatClient span đo thời gian của cả invocation. Session advisor bao gồm thời gian của các advisor và model phía trong. ToolCallingAdvisor có thể bao gồm vòng model/tool mà nó điều phối.

Đây là **inclusive duration**:

- Parent span đo từ lúc operation ngoài bắt đầu đến lúc nó hoàn tất.
- Child spans đo các operation cụ thể xảy ra bên trong.
- Một khoảng thời gian có thể xuất hiện trong duration của nhiều lớp.

Nếu ChatClient mất 3,2 giây và một advisor mất 3,1 giây, không có nghĩa ứng dụng đã tiêu thụ 6,3 giây. Phần lớn 3,1 giây của advisor đã nằm trong 3,2 giây của ChatClient.

### 4.1. Ví dụ một request

Một trace giả định:

| Span | Bắt đầu | Kết thúc | Duration |
|---|---:|---:|---:|
| ChatClient | 0 ms | 3.200 ms | 3.200 ms |
| Session advisor | 10 ms | 3.150 ms | 3.140 ms |
| ToolCallingAdvisor | 500 ms | 3.100 ms | 2.600 ms |
| Model operation 1 | 520 ms | 1.220 ms | 700 ms |
| Tool execution 1 | 1.230 ms | 1.530 ms | 300 ms |
| Model operation 2 | 1.550 ms | 2.150 ms | 600 ms |
| Tool execution 2 | 2.160 ms | 2.560 ms | 400 ms |
| Model operation 3 | 2.580 ms | 3.080 ms | 500 ms |

Tổng model time là 1.800 ms. Tổng tool time là 700 ms. Hai tổng này là các phép đo operation riêng, hữu ích để phân tích nơi sử dụng thời gian.

Nhưng nếu cộng:

~~~text
3.200 + 3.140 + 2.600 + 1.800 + 700 = 11.440 ms
~~~

thì kết quả không phải latency của request. Cùng một khoảng thời gian đã được đo nhiều lần ở các tầng bao nhau.

## 5. Không phải mọi child span đều chạy nối tiếp

Ngay cả khi chỉ xét các span con, cộng duration cũng có thể sai vì chúng có thể chạy song song.

Ví dụ hai tool được thực thi đồng thời:

~~~text
ChatClient invocation: 0 ------------------------- 2.0 s

Model operation:       0.1 ---- 0.7 s
Tool lookupOrder:                    0.8 ---- 1.5 s
Tool getShipment:                    0.8 -------- 1.9 s
Final model operation:                         1.9 -- 2.0 s
~~~

Tool lookupOrder mất 0,7 giây; getShipment mất 1,1 giây. Tổng duration của hai tool là 1,8 giây, nhưng khoảng chờ của batch chỉ khoảng 1,1 giây vì hai tools chạy chồng lấn.

Có ba khái niệm cần tách:

- **Wall-clock duration:** khoảng thời gian từ lúc operation bắt đầu tới lúc kết thúc.
- **Inclusive duration:** thời gian của span, có thể bao gồm thời gian các spans con.
- **Summed operation duration:** tổng duration của các operation riêng lẻ; có thể vượt wall-clock duration khi chúng song song hoặc lồng nhau.

Không dùng summed operation duration thay cho wall-clock latency.

## 6. Self time: phần thời gian riêng của một span

Nếu muốn biết một lớp tự tiêu tốn bao nhiêu thời gian ngoài các operation con, cần tính **self time**.

Một cách khái niệm:

\[
SelfTime(parent) =
Duration(parent) - UnionDuration(directChildren)
\]

Trong đó UnionDuration là độ dài hợp của các khoảng thời gian child spans sau khi:

1. Cắt các child intervals theo biên của parent.
2. Sắp xếp các intervals theo thời điểm bắt đầu.
3. Gộp những intervals chồng lấn.
4. Tính tổng độ dài của các khoảng đã gộp.

Không trừ tổng duration của tất cả descendants. Nếu hai child chạy song song, cộng durations của chúng sẽ trừ cùng một thời gian hai lần.

Ví dụ:

~~~text
Parent: 0 ---------------- 1000 ms
Child A:      100 ----- 500 ms
Child B:                400 -------- 800 ms

Duration parent = 1000 ms
Duration A      = 400 ms
Duration B      = 400 ms

Union(A, B)     = 700 ms  (100 -> 800)
Self time       = 1000 - 700 = 300 ms
~~~

Nếu lấy 1000 - 400 - 400, kết quả là 200 ms và sai 100 ms do khoảng 400–500 ms đã bị trừ hai lần.

Self time chỉ đáng tin khi trace có đủ child spans và parent-child relationships chính xác. Nếu sampling, async context propagation hoặc exporter làm thiếu spans, phần thời gian còn lại có thể bị hiểu nhầm là self time.

## 7. Đọc Timer: count và sum thuộc về một loại operation

Micrometer Timer đo cả duration và tần suất của một event. Tối thiểu timer cung cấp:

- count: số operation đã được ghi nhận.
- totalTime: tổng duration của các operation đã ghi nhận.
- Tùy backend còn có max, percentiles và histogram buckets.

Với Prometheus, Spring AI metrics reference dùng các series dạng:

| Series | Ý nghĩa |
|---|---|
| *_seconds_count | Số operation hoàn tất |
| *_seconds_sum | Tổng duration của các operation hoàn tất |
| *_seconds_max | Duration lớn nhất trong time window |
| *_active_count | Số operation đang chạy tại thời điểm scrape |

active_count là gauge cho số operation đang chạy; nó khác count của các operation đã hoàn tất. Không cộng active_count với seconds_count như thể chúng cùng một tập event.

### 7.1. Một sum lớn không có nghĩa một request chậm

Giả sử trong năm phút:

- 1.000 ChatClient invocations.
- Tổng ChatClient time là 3.200 giây.
- Mean ChatClient duration là 3,2 giây.

gen_ai_chat_client_operation_seconds_sum là tổng thời gian của 1.000 invocations trong cửa sổ thống kê, không phải duration của một invocation cụ thể.

Lưu ý tên meter: observation của ChatClient có tên spring.ai.chat.client, nhưng Spring AI 2.1.0 xuất timer ChatClient với base metric gen_ai.chat.client.operation. Khi dùng Prometheus, tên được chuẩn hóa thành gen_ai_chat_client_operation_seconds_sum/count. Không suy tên series bằng cách chỉ thay dấu chấm trong observation name.

Tương tự, gen_ai_client_operation_seconds_sum là tổng duration của tất cả model operations được ghi trong cùng chuỗi metric.

Muốn tính mean duration:

\[
MeanDuration = \frac{\Delta Sum}{\Delta Count}
\]

Trong Prometheus, thường dùng rate(sum) chia rate(count) trên cùng cửa sổ.

## 8. Count giữa các lớp không thể cộng với nhau

Spring AI metrics có các đơn vị khác nhau:

| Metric prefix | Count đếm | Không được hiểu là |
|---|---|---|
| gen_ai_chat_client_operation_seconds_count | ChatClient calls/streams hoàn tất | Số model calls |
| spring_ai_advisor_seconds_count | Advisor executions | Số user turns |
| gen_ai_client_operation_seconds_count | Model operations | Số ChatClient calls |
| spring_ai_tool_seconds_count | Tool executions | Số model rounds |
| db_vector_client_operation_seconds_count | VectorStore operations | Số RAG requests cấp user |

Spring AI 2.1.0 stable metrics reference liệt kê rõ các series ChatClient, ChatModel và VectorStore. Advisor và tool observations được mô tả ở trang Observability; khi DefaultMeterObservationHandler chuyển các observation hoàn tất thành Timer, base meter thường theo tên observation là spring.ai.advisor và spring.ai.tool. Vì series cuối còn phụ thuộc Spring Boot, registry và meter filters, hãy xác nhận chúng tại /actuator/metrics trước khi dùng các query ở phần sau.

Một ChatClient invocation có thể gọi ba model operations, hai tool executions và nhiều advisor invocations. Vì thế các count có thể khác nhau mà vẫn đúng.

Ví dụ 1.000 ChatClient invocations có thể tạo:

| Metric | Count |
|---|---:|
| ChatClient invocations | 1.000 |
| Advisor invocations | 4.200 |
| Model operations | 1.850 |
| Tool executions | 1.120 |
| VectorStore operations | 760 |

Không cộng thành 8.930 rồi gọi là “số request AI”. Hãy giữ từng count theo đơn vị của nó.

### 8.1. Một ChatClient invocation có thể gọi model nhiều lần

Với ToolCallingAdvisor, một ChatClient call có thể bao gồm nhiều model operations. Một model response cũng có thể chứa nhiều tool calls. Do đó:

- ChatClient count đo số invocation.
- Model operation count đo số lần ChatModel được gọi.
- Tool count đo số lần tool được thực thi.
- Advisor count đo số lần advisor được chạy.

Nếu ứng dụng tự điều phối loop bằng nhiều ChatClient calls, một user turn có thể tạo nhiều ChatClient invocations. Hãy xác định loop được quản lý bởi framework hay tầng service trước khi đặt dashboard.

## 9. Chọn một nguồn canonical cho mỗi câu hỏi vận hành

Không cần bỏ các metric ở lớp khác. Hãy chọn metric phù hợp với câu hỏi:

| Câu hỏi | Nguồn nên dùng |
|---|---|
| Người dùng chờ bao lâu cho một ChatClient call? | spring.ai.chat.client |
| Model provider mất bao lâu cho một lần gọi? | gen_ai.client.operation |
| Một tool cụ thể mất bao lâu? | spring.ai.tool |
| Advisor nào chiếm nhiều thời gian inclusive? | spring.ai.advisor |
| VectorStore query mất bao lâu? | db.vector.client.operation |
| Endpoint HTTP hoàn tất trong bao lâu? | HTTP server observation |
| Một user turn tạo bao nhiêu model operations? | Model operation count chia ChatClient count, khi cùng scope |
| Một ChatClient tạo bao nhiêu tool executions? | Tool execution count chia ChatClient count, khi cùng scope |

Ví dụ: nếu SLA là thời gian người dùng chờ câu trả lời từ ChatClient, chọn ChatClient duration làm nguồn canonical. Dùng model/tool/advisor durations để phân tích nguyên nhân khi SLA xấu đi.

Không thay SLA ChatClient bằng model duration. Model duration không bao gồm toàn bộ advisor, tools, memory, vector retrieval và overhead khác.

## 10. Tính mean latency đúng theo từng tầng

Metrics reference của Spring AI cung cấp các series Prometheus. Mean duration của ChatModel calls có thể tính:

~~~promql
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_sum{gen_ai_operation_name="chat"}[5m])
)
/
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_count{gen_ai_operation_name="chat"}[5m])
)
~~~

Mean ChatClient duration:

~~~promql
sum(rate(gen_ai_chat_client_operation_seconds_sum[5m]))
/
sum(rate(gen_ai_chat_client_operation_seconds_count[5m]))
~~~

Mean tool duration theo tool:

~~~promql
sum by (spring_ai_tool_definition_name) (
  rate(spring_ai_tool_seconds_sum[5m])
)
/
sum by (spring_ai_tool_definition_name) (
  rate(spring_ai_tool_seconds_count[5m])
)
~~~

Các truy vấn này tính mean trên các operation của **chính metric đó**. Không cộng ChatClient sum với model sum hoặc tool sum rồi chia cho một count chung.

Nếu metric backend hoặc phiên bản Spring Boot xuất tên series khác, hãy kiểm tra /actuator/prometheus hoặc registry thực tế trước khi dùng query.

## 11. Tính tỷ lệ operations trên mỗi ChatClient invocation

Các tỷ lệ sau hữu ích để phát hiện loop tăng bất thường:

### 11.1. Model operations trung bình trên một ChatClient invocation

~~~promql
sum(rate(gen_ai_client_operation_seconds_count{gen_ai_operation_name="chat"}[5m]))
/
sum(rate(gen_ai_chat_client_operation_seconds_count[5m]))
~~~

### 11.2. Tool executions trung bình trên một ChatClient invocation

~~~promql
sum(rate(spring_ai_tool_seconds_count[5m]))
/
sum(rate(gen_ai_chat_client_operation_seconds_count[5m]))
~~~

### 11.3. Advisor invocations trên một ChatClient invocation

~~~promql
sum(rate(spring_ai_advisor_seconds_count[5m]))
/
sum(rate(gen_ai_chat_client_operation_seconds_count[5m]))
~~~

Các tỷ lệ này chỉ có ý nghĩa nếu numerator và denominator cùng môi trường, cùng khoảng thời gian, cùng phạm vi traffic và cùng instrumentation. Nếu một số ChatModel được gọi trực tiếp ngoài ChatClient, model count sẽ không còn là tập con hoàn toàn của ChatClient count.

Đây là **tỷ lệ trung bình**, không phải số operations của từng request. Để tìm request có 8 model calls trong khi phần lớn chỉ có 1–2, cần trace hoặc per-invocation event record.

## 12. P95 và histogram: không trừ percentile giữa các lớp

Giả sử:

- P95 ChatClient latency = 3,5 giây.
- P95 ChatModel operation latency = 1,2 giây.

Không được suy ra P95 advisor/tool overhead bằng:

~~~text
3.5 - 1.2 = 2.3 seconds
~~~

P95 ChatClient và P95 model operation có thể đến từ các requests khác nhau. Một ChatClient có nhiều model operations, và P95 của tập operation không tương ứng P95 của model operation nằm trong request P95.

Muốn đo P95 cho model operations, bật histogram cho timer tương ứng:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        gen_ai.client.operation: true
        gen_ai.chat.client.operation: true
~~~

Ví dụ PromQL:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, gen_ai_system) (
    rate(gen_ai_client_operation_seconds_bucket{gen_ai_operation_name="chat"}[5m])
  )
)
~~~

Để đo P95 ChatClient, bật histogram cho meter ID gen_ai.chat.client.operation như trong cấu hình trên. Query tương ứng:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(gen_ai_chat_client_operation_seconds_bucket[5m])
  )
)
~~~

Hai percentile phải được hiển thị thành hai biểu đồ riêng.

Spring Boot không xuất histogram buckets mặc định cho mọi timer; cần bật cấu hình phù hợp và xác nhận series _bucket đã xuất hiện.

## 13. Token usage cũng có thể bị cộng trùng

Spring AI ghi token usage theo model call. Khi tool loop có nhiều model operations, mỗi lần model có thể tiêu thụ input/output tokens riêng.

Metric gen_ai.client.token.usage có token type:

- input: prompt tokens.
- output: completion tokens.
- total: tổng input và output.

Khi tổng hợp, hãy chọn **input + output** hoặc **total**. Không cộng cả ba loại vì total đã bao gồm hai loại còn lại.

Ví dụ:

| Token type | Count |
|---|---:|
| input | 12.000 |
| output | 2.000 |
| total | 14.000 |

Tổng usage là 14.000 tokens, không phải 28.000.

Nếu ChatResponse cuối của tool loop đã tích lũy usage từ nhiều model rounds, không cộng giá trị cumulative đó lần nữa với từng operation-level usage. Chọn một nguồn dữ liệu nhất quán cho báo cáo chi phí.

Một provider không báo token usage cho một operation có thể không tăng counter. Khi so sánh provider, ghi nhận missing usage thay vì coi missing là zero-cost.

## 14. Tránh đo cùng một đoạn code hai lần bằng custom Timer

Spring AI đã instrument ChatClient, advisor, model và tool. Nếu ứng dụng tự bọc cùng một đoạn bằng Timer hoặc @Timed, nó tạo thêm một metric ở ranh giới khác.

Ví dụ:

~~~java
Timer.Sample sample = Timer.start(meterRegistry);

try {
    return chatClient.prompt()
        .user(question)
        .call()
        .content();
}
finally {
    sample.stop(
        Timer.builder("app.ai.chatclient.wrapper")
            .register(meterRegistry)
    );
}
~~~

Metric app.ai.chatclient.wrapper đo thời gian wrapper service bao quanh ChatClient. Nó có thể hữu ích nếu muốn đo thời gian service wrapper, nhưng gần như bao gồm toàn bộ ChatClient invocation.

Nếu dashboard cộng:

- app.ai.chatclient.wrapper
- spring.ai.chat.client
- spring.ai.advisor
- gen_ai.client.operation

thì cùng một đoạn xử lý được tính nhiều lần.

### 14.1. Khi nào custom Timer vẫn có ích?

Custom Timer hữu ích khi nó đo một boundary khác có ý nghĩa rõ ràng, ví dụ:

- Toàn bộ HTTP endpoint từ lúc nhận request đến lúc serialize response.
- Pipeline orchestration gồm retrieval, ChatClient, post-processing và validation.
- Một bước business operation trước/sau ChatClient.
- Thời gian chờ human approval hoặc external queue.

Đặt tên phản ánh đúng boundary. Ghi rõ metric là inclusive nếu nó bao gồm các operation con. Không đặt tên model.duration cho một Timer đang bọc toàn service.

## 15. HTTP request, ChatClient và model operation là ba lớp khác nhau

Một HTTP request có thể làm nhiều việc trước và sau ChatClient:

~~~text
HTTP server request
  Authentication / authorization
  Input validation
  Application service
    ChatClient invocation
      Advisor chain
      ChatModel operations
      Tool executions
  Response mapping / serialization
HTTP response
~~~

Vì vậy:

- HTTP server duration thường bao gồm ChatClient và các bước ngoài ChatClient.
- ChatClient duration bao gồm advisor chain và các operation bên trong invocation.
- Model duration chỉ đo các ChatModel operations.
- Tool duration chỉ đo tool executions.

Nếu HTTP P95 tăng nhưng ChatClient P95 ổn định, nguyên nhân có thể nằm ngoài ChatClient: authentication, queue, validation, serialization hoặc middleware.

Nếu ChatClient P95 tăng trong khi model P95 ổn định, hãy điều tra advisor, tools, retrieval, memory và application overhead.

Nếu model P95 tăng, hãy xem provider, model, token count, throttling, network và retry behavior.

## 16. Trace spans: dùng khoảng thời gian và quan hệ cha-con

Một trace biểu diễn đường đi của một logical operation qua các lớp. Mỗi span có:

- TraceId: định danh trace.
- SpanId: định danh span.
- ParentSpanId: span cha trực tiếp.
- Start timestamp và end timestamp.
- Attributes, events và status.

Các spans cùng trace có thể lồng nhau hoặc chồng lấn. Quan hệ parent-child biểu diễn quan hệ nhân quả, không có nghĩa duration của chúng là những đoạn thời gian tách rời.

Ví dụ:

~~~text
Trace T1
└─ ChatClient span (0–3200 ms)
   ├─ Session advisor (10–3150 ms)
   │  └─ ToolCallingAdvisor (500–3100 ms)
   │     ├─ ChatModel #1 (520–1220 ms)
   │     ├─ Tool #1 (1230–1530 ms)
   │     ├─ ChatModel #2 (1550–2150 ms)
   │     ├─ Tool #2 (2160–2560 ms)
   │     └─ ChatModel #3 (2580–3080 ms)
   └─ Post-processing advisor (3150–3180 ms)
~~~

Khi đọc trace:

1. Chọn root span hoặc ChatClient span làm mốc wall-clock cho đúng câu hỏi.
2. Xem các child spans để xác định operation cụ thể.
3. Dùng timeline để phát hiện overlap và khoảng chờ.
4. Xem span cha nào bao gồm span con nào.
5. Tìm gaps giữa các spans để phát hiện overhead chưa được instrument.
6. Không cộng durations của mọi spans trong trace.

Nếu thiếu child span do sampling, exporter hoặc context propagation, trace có thể không hoàn chỉnh. Không mặc định phần duration không có child span chính là CPU time của parent.

## 17. Không cộng HTTP client spans vào ChatModel duration

Một số provider có instrumentation ở cả ChatModel layer và HTTP client layer. Ví dụ một request có thể có:

~~~text
gen_ai.client.operation
└─ okhttp.requests
~~~

Trong trường hợp này, HTTP span đo transport request bên trong model operation. Nếu cộng okhttp.requests duration với gen_ai.client.operation duration, request gửi tới provider bị tính hai lần.

HTTP spans hữu ích để phân tích network/transport. ChatModel span hữu ích để đo model operation ở lớp Spring AI. Chọn metric theo câu hỏi và đọc nesting của provider cụ thể.

Spring AI 2.1.0 cũng ghi chú một ngoại lệ ở OpenAI streaming: HTTP span được ghi nhưng có thể không được parent dưới ChatModel span do async SDK chuyển execution sang ForkJoinPool.commonPool() và mất observation context ở ranh giới đó. Vì vậy, thiếu nesting không nhất thiết có nghĩa HTTP request không thuộc model operation.

## 18. Advisor metrics có thể cộng trùng ngay cả khi không có model/tool span

Một advisor chain có thể lồng nhau:

~~~text
ChatClient
└─ Advisor A
   └─ Advisor B
      └─ Advisor C
         └─ ChatModel
~~~

Nếu A, B và C đều có spring.ai.advisor observations:

- A đo thời gian A + B + C + ChatModel.
- B đo thời gian B + C + ChatModel.
- C đo thời gian C + ChatModel.

Tổng duration của A + B + C lớn hơn nhiều so với wall-clock. Đây là hành vi inclusive được thiết kế để cho biết từng advisor bao phủ bao nhiêu công việc phía sau.

Nếu muốn so sánh advisor nào tốn thời gian nhất, hãy nhớ timer advisor là inclusive. Advisor ngoài cùng thường có duration lớn vì bao gồm nhiều bước hơn. Không xếp hạng advisor bằng cách cộng tất cả duration của chúng.

Để đo self time của một advisor, cần trace đủ child spans và tính phần thời gian không bị child intervals bao phủ, hoặc instrument riêng phần code nội bộ cần đo.

## 19. Một bộ dashboard nên chia thành các tầng

Gợi ý tổ chức dashboard:

| Dashboard section | Metrics chính | Mục đích |
|---|---|---|
| User experience | HTTP request latency, ChatClient latency, error rate | Người dùng đang chờ bao lâu? |
| Model provider | Model operation count, mean/P95, token usage, errors | Model có chậm, đắt hoặc lỗi không? |
| Tool execution | Tool count, mean/P95, error rate theo tool | Tool nào gây chậm hoặc lỗi? |
| Advisor | Advisor invocation count và inclusive duration | Advisor nào chạy nhiều hoặc bao phủ nhiều công việc? |
| Retrieval | VectorStore operation count, mean/P95 | Retrieval có tạo bottleneck không? |
| Efficiency | Model operations/ChatClient, tools/ChatClient, tokens/turn | Một lượt đang cần bao nhiêu công việc? |
| Evaluation quality | Relevance, factuality, tool correctness, pass rate | Tối ưu có làm chất lượng giảm không? |

Đặt các panel theo thứ tự từ trải nghiệm người dùng tới nguyên nhân kỹ thuật. Tránh tạo một panel “Total AI duration” bằng cách cộng các timer ở mọi tầng.

## 20. Đối chiếu hiệu năng với chất lượng evaluation

Giả sử một phiên bản prompt mới tạo ra kết quả:

| Chỉ số | Version A | Version B |
|---|---:|---:|
| Mean ChatClient latency | 2,4 s | 3,1 s |
| Mean model operations / ChatClient | 1,5 | 2,2 |
| Mean tool executions / ChatClient | 0,8 | 1,3 |
| Input tokens / case | 2.100 | 3.400 |
| Factuality pass rate | 91% | 96% |
| Tool correctness pass rate | 95% | 97% |

Các số chỉ minh họa. Version B có chất lượng tốt hơn nhưng latency, model operations, tool executions và tokens đều tăng.

Không thể kết luận Version B tốt hơn hoặc kém hơn chỉ bằng một metric. Cần xem:

- Chất lượng có cải thiện đủ lớn so với chi phí không?
- Model rounds tăng do tool loop, retry hay validation?
- Tool executions tăng vì model gọi thêm công cụ cần thiết hay gọi dư thừa?
- ChatClient latency tăng trong khi model latency ổn định hay cả hai cùng tăng?
- Có request nào bị tail latency cao bất thường?
- Cùng dataset, judge model, rubric và index có được giữ cố định không?

Mục tiêu là tìm trade-off giữa chất lượng, latency và cost trên cùng một đơn vị evaluation case.

## 21. Checklist chống double counting

Trước khi phát hành dashboard hoặc báo cáo hiệu năng:

- [ ] Mỗi metric có định nghĩa đơn vị rõ ràng?
- [ ] Đã phân biệt HTTP requests, user turns và ChatClient invocations?
- [ ] Đã phân biệt ChatClient, advisor, model, tool và vector operations?
- [ ] Đã xác định metric nào là inclusive duration?
- [ ] Không cộng ChatClient duration với advisor/model/tool durations?
- [ ] Không cộng advisor durations lồng nhau?
- [ ] Không cộng duration của các spans song song để suy ra wall-clock?
- [ ] Không dùng seconds_sum như duration của một request?
- [ ] Mean được tính bằng delta/rate của sum chia delta/rate của count?
- [ ] Count của các observation khác nhau không bị cộng thành một tổng giả?
- [ ] P95 được tính riêng cho từng timer/histogram?
- [ ] Không trừ P95 của ChatClient và P95 của ChatModel?
- [ ] Token usage chỉ cộng input + output hoặc total, không cộng cả ba?
- [ ] Không cộng HTTP transport span vào ChatModel span khi chúng lồng nhau?
- [ ] Custom Timer hoặc @Timed có boundary khác và tên rõ ràng?
- [ ] Trace sampling/context propagation đã được tính đến?
- [ ] Dashboard có model/tool/advisor ratios trên cùng scope traffic?
- [ ] Hiệu năng được so cùng dataset và đối chiếu với factuality/relevance?

## 22. Bài tập tự kiểm tra

### Bài 1 — ChatClient và advisor

Một ChatClient invocation mất 2,8 giây. Advisor A mất 2,7 giây. Có nên báo tổng thời gian là 5,5 giây?

**Đáp án:** Không. Advisor A là span lồng bên trong ChatClient và có thể bao gồm phần lớn thời gian ChatClient.

### Bài 2 — Nhiều model calls

Một ChatClient invocation tạo ba model operations. Count nào phản ánh số lần model được gọi?

**Đáp án:** gen_ai.client.operation count. ChatClient count vẫn là một invocation.

### Bài 3 — Hai tools song song

Hai tool spans cùng chạy trong 500 ms và 700 ms, bắt đầu gần như cùng lúc. Batch wall-clock gần 700 ms hay 1.200 ms?

**Đáp án:** Gần 700 ms nếu chúng thực sự chạy song song và không có overhead khác. Tổng operation duration là 1.200 ms.

### Bài 4 — Timer sum

gen_ai_client_operation_seconds_sum tăng 120 giây trong một phút. Có nghĩa một request mất 120 giây không?

**Đáp án:** Không. Đây là tổng duration của tất cả model operations hoàn tất trong khoảng đo. Cần chia cho count hoặc dùng trace để xem từng request.

### Bài 5 — P95 subtraction

P95 ChatClient là 4 giây, P95 ChatModel là 1 giây. Có thể kết luận P95 advisor/tool overhead là 3 giây không?

**Đáp án:** Không. Hai percentile có thể đến từ các requests/operations khác nhau. Cần phân tích per-trace intervals và critical path.

### Bài 6 — Advisor count

Một advisor nằm sau ToolCallingAdvisor và được gọi ba lần trong một tool loop. Count advisor tăng bao nhiêu?

**Đáp án:** Ba advisor invocations. Nó không có nghĩa ChatClient count hoặc user turn count tăng ba.

### Bài 7 — Token total

Provider báo input 8.000, output 1.000 và total 9.000. Nên cộng bao nhiêu tokens?

**Đáp án:** 9.000. Hoặc cộng input + output = 9.000. Không cộng cả ba thành 18.000.

### Bài 8 — HTTP span lồng trong model span

Một okhttp.requests span dài 900 ms nằm trong gen_ai.client.operation span dài 1.100 ms. Tổng model/HTTP time có phải 2.000 ms?

**Đáp án:** Không. HTTP span là một phần của model operation trong ví dụ này. Dùng HTTP span để phân tích transport, model span để đo operation ở lớp ChatModel.

### Bài 9 — Self time với overlap

Parent dài 1.000 ms. Child A chạy từ 100 đến 500 ms; child B từ 400 đến 800 ms. Self time là bao nhiêu?

**Đáp án:** Hợp các child intervals dài 700 ms, nên self time là 300 ms. Không lấy 1.000 - 400 - 400 vì khoảng 400–500 bị trừ hai lần.

## 23. Tài liệu tham khảo

1. [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): ranh giới ChatClient, Advisor, ChatModel và Tool observations; đặc biệt duration của advisor bao gồm inner advisors.
2. [Spring AI 2.1.0 — Observability, More Metrics Reference](https://docs.spring.io/spring-ai/reference/observability/index.html): tên Prometheus stable cho ChatClient, ChatModel, VectorStore và token usage.
3. [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timer đo latency và event frequency; total time, count, max, percentiles và histogram.
4. [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): cách Observation handlers tạo Timer, spans và logs.
5. [OpenTelemetry — Traces Data Model](https://opentelemetry.io/docs/specs/otel/trace/data-model/): span timing, parent-child relationships, causal relationships và trace structure.
6. [Spring AI — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html): recursive tool loop và advisor composition.
7. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Observation-to-meter handler, per-meter histogram properties và endpoint kiểm tra meter.

*Các metric names và PromQL trong bài dựa trên tài liệu Spring AI 2.1.0/metrics reference. Tên series cuối cùng còn phụ thuộc registry và phiên bản. Trước khi dùng trong production, kiểm tra metric exposition thực tế, sampling, histogram configuration và các provider-specific observations.*
