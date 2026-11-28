# Theo dõi lưu lượng, độ trễ, lỗi và mức sử dụng token

## 1. Vì sao cần một bộ chỉ số vận hành riêng cho ứng dụng AI?

Một chatbot có thể nhận 500 yêu cầu mỗi phút nhưng chỉ tạo ra 300 câu trả lời thành công. Một yêu cầu khác có thể gọi model ba lần do tool loop, tiêu thụ 8.000 tokens và mất 7 giây. Nếu dashboard chỉ đếm HTTP requests, bạn sẽ không thấy model đang bị gọi nhiều hơn, token usage tăng hay provider bắt đầu timeout.

Khi vận hành Spring AI, cần trả lời được bốn câu hỏi:

1. **Lưu lượng:** có bao nhiêu yêu cầu đi vào ứng dụng, bao nhiêu ChatClient invocations và bao nhiêu model operations?
2. **Độ trễ:** người dùng chờ bao lâu, ChatClient mất bao lâu, model provider mất bao lâu?
3. **Lỗi:** request nào thất bại, lỗi xảy ra ở ứng dụng, model, tool hay retrieval?
4. **Token usage:** mỗi model dùng bao nhiêu input/output tokens, tốc độ tiêu thụ ra sao và chi phí ước tính thế nào?

Bốn nhóm chỉ số này liên hệ với nhau nhưng có đơn vị đo khác nhau. Một HTTP request có thể gọi nhiều ChatClient invocations; một ChatClient invocation có thể gọi model nhiều lần; mỗi model operation có thể phát sinh nhiều tool calls. Không cộng các count thành một con số “AI requests” chung.

Bài thuộc chương **Dashboard và cảnh báo** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module học đánh giá ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời theo dõi metrics, traces, chi phí và độ trễ để tìm nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline.

Sau bài, bạn có thể:

- Phân biệt HTTP requests, ChatClient invocations, model operations và tool executions.
- Dùng counter, gauge, timer và histogram đúng mục đích.
- Đo throughput, mean latency, P95/P99, in-flight operations và error ratio.
- Theo dõi input/output/total tokens theo model và provider.
- Tính token rate, tokens trên mỗi ChatClient invocation và chi phí ước tính.
- Viết PromQL cho dashboard và alert.
- Điều tra provider throttling, timeout, retry, model loop và token spikes.

## 2. Phân biệt các ranh giới đếm

Trước khi tạo dashboard, xác định mỗi metric đếm một sự kiện nào.

| Ranh giới | Một đơn vị được ghi khi nào? | Ví dụ câu hỏi |
|---|---|---|
| HTTP request | Một request đến endpoint | API nhận bao nhiêu request/giây? |
| User turn | Một lượt hội thoại logic | Có bao nhiêu yêu cầu mới từ người dùng? |
| ChatClient invocation | Một lần gọi call() hoặc stream() | ChatClient được gọi bao nhiêu lần? |
| Model operation | Một lần gọi ChatModel.call() hoặc stream() | Provider nhận bao nhiêu model calls? |
| Tool execution | Một lần tool thực sự chạy | Công cụ nào được thực thi bao nhiêu lần? |
| VectorStore operation | Một lần query/add/upsert/delete | Retrieval có tạo thêm tải không? |

Ví dụ:

~~~text
1 HTTP request
  1 user turn
    1 ChatClient invocation
      3 ChatModel operations
      2 tool executions
      1 VectorStore query
~~~

Trong ví dụ, API nhận một request, nhưng model được gọi ba lần. Model operations không phải user requests. Nếu ứng dụng tự điều phối vòng lặp bằng nhiều ChatClient calls, một user turn còn có thể tạo nhiều ChatClient invocations.

Hãy giữ từng metric ở đúng ranh giới. Khi muốn tính model operations trung bình trên một ChatClient invocation, dùng tỷ lệ giữa hai counter có cùng scope traffic; không cộng hai count với nhau.

## 3. Bốn loại metric cần hiểu trước khi viết PromQL

Prometheus/Micrometer thường dùng bốn loại metric cơ bản:

| Loại | Đặc tính | Dùng cho |
|---|---|---|
| Counter | Chỉ tăng, có thể reset khi process khởi động lại | Tổng requests, errors, tokens |
| Gauge | Có thể tăng hoặc giảm | In-flight requests, queue depth, memory |
| Timer | Đo thời gian và số lần event | Latency của ChatClient/model/tool |
| Histogram | Phân phối các giá trị theo bucket | P50/P95/P99, tỷ lệ nằm trong ngưỡng |

Quy tắc quan trọng:

- Dùng rate() hoặc increase() trên counter/timer count để tính tốc độ hoặc số event trong cửa sổ.
- Không dùng rate() trên gauge như số operation đang chạy.
- Timer có seconds_sum và seconds_count; chia rate của sum cho rate của count để tính mean duration.
- Histogram có thêm _bucket; dùng histogram_quantile() để tính percentile có thể tổng hợp qua nhiều instances.

Prometheus giải thích counter là số tích lũy, gauge là giá trị trạng thái và histogram là phân phối các observation theo bucket. [Prometheus — Metric Types](https://prometheus.io/docs/concepts/metric_types/) · [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/).

## 4. Những metric Spring AI 2.1.0 cần theo dõi

Spring AI 2.1.0 cung cấp Micrometer observations cho ChatClient, ChatModel, tool calling và VectorStore. Với Prometheus, các timer quan trọng gồm:

| Metric | Ý nghĩa |
|---|---|
| gen_ai_chat_client_operation_seconds_count | Số ChatClient operations hoàn tất |
| gen_ai_chat_client_operation_seconds_sum | Tổng thời gian các ChatClient operations |
| gen_ai_chat_client_operation_seconds_max | Duration lớn nhất quan sát được trong cửa sổ gần đây |
| gen_ai_chat_client_operation_active_count | Số ChatClient operations đang chạy |
| gen_ai_client_operation_seconds_count | Số model operations hoàn tất |
| gen_ai_client_operation_seconds_sum | Tổng thời gian model operations |
| gen_ai_client_operation_seconds_max | Duration lớn nhất của model operations |
| gen_ai_client_operation_active_count | Số model operations đang chạy |
| gen_ai_client_token_usage_total | Counter token usage do provider báo cáo |
| db_vector_client_operation_seconds_count | Số VectorStore operations hoàn tất |
| db_vector_client_operation_seconds_sum | Tổng thời gian VectorStore operations |
| db_vector_client_operation_active_count | Số VectorStore operations đang chạy |

Các tags quan trọng của model operation:

- gen_ai_operation_name: loại operation, ví dụ chat hoặc embedding.
- gen_ai_system: provider, ví dụ openai, anthropic hoặc provider tương ứng.
- gen_ai_request_model: model được yêu cầu.
- gen_ai_response_model: model thực tế trả kết quả nếu provider cung cấp.

ChatClient timer đo toàn bộ call()/stream() invocation. Model timer đo từng ChatModel operation. Vì thế một ChatClient invocation có thể tạo nhiều model operations. [Spring AI 2.1.0 — Observability, More Metrics Reference](https://docs.spring.io/spring-ai/reference/observability/).

### 4.1. Active count khác completed count

- *_active_count là gauge cho số operation đang chạy tại thời điểm scrape.
- *_seconds_count là số operation đã hoàn tất.
- *_seconds_sum là tổng duration của các operation đã hoàn tất.

Active count giúp nhìn concurrency và tải đang nằm trong hệ thống. Nó không phải throughput. Để biết model calls mỗi giây, dùng rate(gen_ai_client_operation_seconds_count[5m]), không dùng active count.

## 5. Đo lưu lượng ChatClient

Throughput ChatClient có thể tính từ số invocation hoàn tất trong một đơn vị thời gian.

~~~promql
sum(rate(gen_ai_chat_client_operation_seconds_count[5m]))
~~~

Kết quả là ChatClient invocations mỗi giây trên toàn bộ instances trong query.

Nếu cần tách call và stream, dùng tag spring_ai_chat_client_stream nếu registry xuất tag này:

~~~promql
sum by (spring_ai_chat_client_stream) (
  rate(gen_ai_chat_client_operation_seconds_count[5m])
)
~~~

Cách đọc:

- false: ChatClient call không stream.
- true: ChatClient stream.
- Tổng hai nhóm là throughput ChatClient nếu tất cả operations đều có tag này.

Không đồng nhất ChatClient throughput với HTTP throughput. Một endpoint có thể thực hiện authentication, validation hoặc gọi nhiều ChatClient invocations cho một HTTP request.

## 6. Đo số model operations theo provider và model

Model operation count phản ánh tải thực tế gửi đến model layer:

~~~promql
sum by (gen_ai_system, gen_ai_request_model) (
  rate(
    gen_ai_client_operation_seconds_count{
      gen_ai_operation_name="chat"
    }[5m]
  )
)
~~~

Biểu đồ cho biết số chat model operations mỗi giây, phân tách theo provider và requested model.

Khi count tăng bất thường, kiểm tra:

- ToolCallingAdvisor có tạo nhiều model rounds hơn không?
- Retry hoặc structured-output validation có lặp không?
- Ứng dụng có tự gọi ChatClient nhiều lần không?
- Traffic người dùng có tăng thật không?
- Fallback routing có chuyển traffic sang model khác không?

Model operation count có thể tăng dù số user turns không đổi. Đây là tín hiệu hữu ích để phát hiện prompt hoặc advisor thay đổi làm tăng số lần gọi model.

## 7. Tính tỷ lệ model operations trên mỗi ChatClient invocation

Một chỉ số hiệu quả đơn giản:

\[
ModelOperationsPerChatClient =
\frac{\text{Model operations}}
{\text{ChatClient invocations}}
\]

PromQL:

~~~promql
sum(rate(gen_ai_client_operation_seconds_count{gen_ai_operation_name="chat"}[5m]))
/
sum(rate(gen_ai_chat_client_operation_seconds_count[5m]))
~~~

Ví dụ:

| Chỉ số | Version A | Version B |
|---|---:|---:|
| ChatClient invocations/s | 100 | 100 |
| Model operations/s | 150 | 240 |
| Model operations / ChatClient | 1,5 | 2,4 |

Traffic ChatClient không đổi nhưng số model operations tăng 60%. Có thể tool loop, retry hoặc advisor chain đang làm thêm việc.

Tỷ lệ này chỉ có ý nghĩa nếu model operations trong numerator thuộc cùng phạm vi ChatClient invocations trong denominator. Nếu ứng dụng gọi ChatModel trực tiếp ngoài ChatClient, hãy tách chúng hoặc dùng custom application metrics.

## 8. Đo in-flight operations và concurrency

Số operation đang chạy cho biết hệ thống có đang tích lũy công việc hay không.

ChatClient:

~~~promql
sum(gen_ai_chat_client_operation_active_count)
~~~

Model calls:

~~~promql
sum by (gen_ai_system) (
  gen_ai_client_operation_active_count
)
~~~

VectorStore:

~~~promql
sum by (db_system) (
  db_vector_client_operation_active_count
)
~~~

Nếu throughput không tăng nhưng in-flight model calls tăng liên tục, có thể model latency đang tăng hoặc request bị treo. Nếu cả active ChatClient và active model calls tăng cùng lúc, kiểm tra provider, thread/connection pool, timeout và backpressure.

Đừng kết luận chỉ từ một điểm scrape. Quan sát xu hướng theo thời gian và đối chiếu với request rate, latency và error rate.

## 9. Đo mean latency của ChatClient

Timer cung cấp tổng duration và số operation hoàn tất. Mean latency trong cửa sổ 5 phút:

~~~promql
sum(rate(gen_ai_chat_client_operation_seconds_sum[5m]))
/
sum(rate(gen_ai_chat_client_operation_seconds_count[5m]))
~~~

Đây là mean duration của ChatClient operations đã hoàn tất trong cửa sổ, không phải latency của một request cụ thể.

Nếu muốn chia theo chế độ call/stream:

~~~promql
sum by (spring_ai_chat_client_stream) (
  rate(gen_ai_chat_client_operation_seconds_sum[5m])
)
/
sum by (spring_ai_chat_client_stream) (
  rate(gen_ai_chat_client_operation_seconds_count[5m])
)
~~~

Mean hữu ích để theo dõi xu hướng tổng thể nhưng có thể che khuất một số request rất chậm. Luôn xem thêm percentile hoặc SLO ratio.

## 10. Đo mean latency của ChatModel theo provider

Model latency giúp phân biệt chậm ở provider với chậm ở phần advisor, retrieval hoặc tool execution.

~~~promql
sum by (gen_ai_system, gen_ai_request_model) (
  rate(
    gen_ai_client_operation_seconds_sum{
      gen_ai_operation_name="chat"
    }[5m]
  )
)
/
sum by (gen_ai_system, gen_ai_request_model) (
  rate(
    gen_ai_client_operation_seconds_count{
      gen_ai_operation_name="chat"
    }[5m]
  )
)
~~~

Nếu ChatClient latency tăng nhưng model latency ổn định, điều tra advisor, tools, memory, VectorStore và service overhead.

Nếu model latency tăng trên một provider/model, kiểm tra:

- Provider status, rate limits và quota.
- Input/output token count.
- Model routing và fallback.
- Network/HTTP client latency.
- Retry behavior hoặc provider queueing.

ChatClient duration bao gồm nhiều thành phần và có thể chứa nhiều model calls; không thay user-facing latency bằng model latency.

## 11. Đo P95/P99 bằng histogram

Spring Boot không xuất histogram buckets cho mọi timer theo mặc định. Muốn tính percentile bằng Prometheus, bật histogram cho meter ID tương ứng.

Ví dụ:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        gen.ai.chat.client.operation: true
        gen.ai.client.operation: true
~~~

P95 ChatClient:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(gen_ai_chat_client_operation_seconds_bucket[5m])
  )
)
~~~

P95 model operation theo provider:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, gen_ai_system) (
    rate(
      gen_ai_client_operation_seconds_bucket{
        gen_ai_operation_name="chat"
      }[5m]
    )
  )
)
~~~

P99 có thể thay 0.95 bằng 0.99.

Histogram phù hợp khi cần tổng hợp latency từ nhiều instances. Percentiles được tính riêng tại từng instance rồi lấy trung bình không phải P95 toàn hệ thống. Prometheus giải thích histogram bucket có thể được tổng hợp trước khi tính quantile; summary quantiles thì không thể cộng/trung bình một cách có ý nghĩa. [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/).

## 12. Đo tỷ lệ request hoàn tất trong ngưỡng latency

Nếu SLO yêu cầu 95% ChatClient operations hoàn tất trong 4 giây, có thể đo trực tiếp tỷ lệ good events bằng histogram bucket le="4":

~~~promql
sum(rate(gen_ai_chat_client_operation_seconds_bucket{le="4"}[5m]))
/
sum(rate(gen_ai_chat_client_operation_seconds_count[5m]))
~~~

Bucket le="4" phải tồn tại trong metric exposition. Nếu không có bucket ở ngưỡng 4 giây, query này không trả về tỷ lệ mong muốn. Hãy cấu hình SLO bucket hoặc histogram boundaries phù hợp.

Đây là cách đo tỷ lệ request trong ngưỡng. P95 vẫn hữu ích cho phân phối latency, nhưng tỷ lệ good events thường dễ gắn với SLO và error budget hơn.

## 13. Đo lỗi ở model operation

Spring Boot DefaultMeterObservationHandler có thể thêm tag error vào timer của completed observations. Khi registry xuất tag này, có thể tính tỷ lệ model operations kết thúc bằng exception:

~~~promql
sum(rate(
  gen_ai_client_operation_seconds_count{
    gen_ai_operation_name="chat",
    error!="none"
  }[5m]
))
/
sum(rate(
  gen_ai_client_operation_seconds_count{
    gen_ai_operation_name="chat"
  }[5m]
))
~~~

Query này giả định series có tag error và giá trị thành công là none. Hãy kiểm tra meter thực tế tại /actuator/metrics/gen.ai.client.operation hoặc /actuator/prometheus trước khi áp dụng.

Nếu metric không có tag error, hãy tạo application counter cho model failures hoặc dùng HTTP/provider observations tương ứng. Không lọc theo message exception động vì nó tạo cardinality lớn.

## 14. Phân biệt lỗi transport, model và lỗi nghiệp vụ

Một request có thể hoàn tất kỹ thuật nhưng không đạt kết quả mong muốn.

| Loại lỗi | Ví dụ | Nơi đo phù hợp |
|---|---|---|
| HTTP/application | 400, 401, 500 | HTTP server metrics |
| Provider/transport | Timeout, 429, 5xx | ChatModel hoặc HTTP client observation |
| Model response | Output bị cắt, finish reason không mong muốn | Model metadata và app metric |
| Tool execution | Tool callback ném exception | Tool observation |
| Retrieval | VectorStore timeout hoặc không tìm thấy context | VectorStore observation và retrieval metric |
| Business outcome | Trả nhầm đơn hàng hoặc thiếu thông tin | Application outcome counter |
| Answer quality | Không liên quan, hallucination, thiếu citation | Evaluation pipeline |

Không dùng HTTP 200 làm bằng chứng câu trả lời tốt. Model có thể trả một response hợp lệ về giao thức nhưng sai về nội dung. Cần counter nghiệp vụ và evaluation score riêng.

### 14.1. Error ratio ở tầng user request

Ví dụ ứng dụng tự định nghĩa hai counters:

~~~text
app_ai_requests_total
app_ai_request_failures_total
~~~

Tỷ lệ lỗi:

~~~promql
sum(rate(app_ai_request_failures_total[5m]))
/
sum(rate(app_ai_requests_total[5m]))
~~~

Increment app_ai_request_failures_total khi request không hoàn thành theo contract của endpoint. Quy định rõ timeout, cancellation, validation failure và business rejection có được tính vào SLI hay không.

Prometheus khuyến nghị có tổng số attempts và số failures riêng để tính failure ratio. [Prometheus — Instrumentation](https://prometheus.io/docs/practices/instrumentation/).

## 15. Theo dõi provider HTTP status và throttling

Model operation error không phải lúc nào cũng cho biết chính xác HTTP status của provider. Nếu cần phân biệt 429, 5xx, timeout và network error, instrument HTTP client/provider boundary.

Metric do ứng dụng định nghĩa có thể là:

~~~text
app_ai_provider_http_requests_total{provider,status_code}
~~~

Ví dụ query tỷ lệ 429:

~~~promql
sum by (provider) (
  rate(app_ai_provider_http_requests_total{status_code="429"}[5m])
)
/
sum by (provider) (
  rate(app_ai_provider_http_requests_total[5m])
)
~~~

Nếu instrumentation chỉ cung cấp status_class, có thể đếm nhóm 4xx thay cho status code cụ thể. Không tự giả định HTTP status tag tồn tại trong gen_ai.client.operation; hãy kiểm tra observation và HTTP client metrics của provider.

Khi 429 tăng, xem request rate, in-flight model calls, quota, retry count và fallback rate. Retry quá nhiều có thể làm traffic và token usage tăng thêm, khiến throttling nghiêm trọng hơn.

## 16. Hiểu token usage: input, output và total

Spring AI ghi token usage theo thông tin provider báo cáo qua metric:

gen_ai_client_token_usage_total

Tag gen_ai_token_type có ba loại:

| Token type | Ý nghĩa |
|---|---|
| input | Tokens gửi vào model, gồm prompt/context theo cách provider tính |
| output | Tokens model tạo ra |
| total | Tổng input + output |

Khi tổng hợp, chọn **input + output** hoặc **total**. Không cộng cả ba vì total đã bao gồm input và output.

Provider không báo usage cho một model call thì counter không tăng cho call đó. Missing usage không có nghĩa call tiêu thụ zero tokens. Khi so sánh provider, hãy theo dõi coverage của usage data.

## 17. Đo token rate theo model

Token usage mỗi phút, tách model và token type:

~~~promql
sum by (gen_ai_request_model, gen_ai_token_type) (
  rate(
    gen_ai_client_token_usage_total{
      gen_ai_token_type!="total"
    }[5m]
  )
) * 60
~~~

Query loại total để tránh đếm trùng. Kết quả có input và output tokens mỗi phút theo model.

Nếu muốn xem tổng tokens theo model, dùng duy nhất gen_ai_token_type="total":

~~~promql
sum by (gen_ai_request_model) (
  rate(
    gen_ai_client_token_usage_total{
      gen_ai_token_type="total"
    }[5m]
  )
) * 60
~~~

Token rate tăng có thể do traffic tăng, prompt/context dài hơn, nhiều model rounds hơn hoặc output dài hơn. So sánh cùng lúc ChatClient throughput và model operations để tìm nguyên nhân.

## 18. Tính tokens trung bình trên mỗi ChatClient invocation

Tỷ lệ token efficiency:

\[
TokensPerChatClient =
\frac{\text{Total tokens}}
{\text{ChatClient invocations}}
\]

PromQL minh họa:

~~~promql
sum(rate(
  gen_ai_client_token_usage_total{
    gen_ai_token_type="total"
  }[5m]
))
/
sum(rate(
  gen_ai_chat_client_operation_seconds_count[5m]
))
~~~

Kết quả là tokens trung bình trên một ChatClient invocation trong cửa sổ.

Chỉ số này có thể bị lệch nếu:

- Một số ChatModel calls chạy ngoài ChatClient.
- Provider không báo token usage cho một số calls.
- Có batch/background model operations không thuộc user ChatClient traffic.
- Token counter và ChatClient timer không cùng phạm vi request.

Nếu cần tokens trên mỗi user turn thay vì ChatClient invocation, hãy instrument user-turn counter ở tầng ứng dụng và liên kết đúng scope.

## 19. Từ token usage đến chi phí ước tính

Token count chưa phải chi phí. Mỗi model có thể có giá input/output khác nhau; cached input, batch pricing, region và currency cũng có thể khác.

Công thức cơ bản:

\[
EstimatedCost =
InputTokens \times InputPrice
+
OutputTokens \times OutputPrice
\]

Ví dụ minh họa:

| Model | Input tokens | Output tokens | Giá input / 1M | Giá output / 1M |
|---|---:|---:|---:|---:|
| Model A | 800.000 | 100.000 | $2,00 | $8,00 |
| Model B | 400.000 | 80.000 | $0,50 | $2,00 |

Chi phí Model A:

\[
0.8 \times 2.00 + 0.1 \times 8.00 = \$2.40
\]

Chi phí Model B:

\[
0.4 \times 0.50 + 0.08 \times 2.00 = \$0.36
\]

Tổng ước tính là $2,76 theo bảng giá giả định. Khi chạy production, lấy bảng giá chính thức theo provider/model và lưu version, thời điểm hiệu lực, currency, cache/batch discount và quy tắc làm tròn.

Không hardcode giá model vào dashboard query nếu bảng giá có thể thay đổi. Tốt hơn là ứng dụng hoặc cost pipeline tính chi phí và xuất counter riêng như:

~~~text
app_ai_estimated_cost_usd_total{provider,model_family}
~~~

Không dùng conversation ID hoặc user ID làm metric labels chỉ để tính chi phí từng người; lưu dữ liệu chi tiết ở billing/evaluation store có kiểm soát.

## 20. Phân biệt token spikes với traffic spikes

Khi token rate tăng, hãy so sánh ít nhất bốn biểu đồ:

1. HTTP requests/s hoặc user turns/s.
2. ChatClient invocations/s.
3. Model operations/s.
4. Input/output tokens/minute.

Một số pattern thường gặp:

| Quan sát | Khả năng cần điều tra |
|---|---|
| HTTP traffic tăng, token rate tăng cùng tỷ lệ | Nhiều người dùng hơn |
| ChatClient traffic ổn định, model operations tăng | Tool loop, retry hoặc advisor loop tăng |
| Model operations ổn định, input tokens tăng | Prompt/context dài hơn, history lớn hơn, retrieval trả nhiều documents |
| Input tokens ổn định, output tokens tăng | Completion dài hơn hoặc stop condition thay đổi |
| Tokens tăng cùng 429 và retry | Throttling tạo thêm attempts |
| Tokens/ChatClient tăng sau release | Prompt/model/tool-set/pipeline regression |

Các pattern là giả thuyết điều tra, không phải kết luận tự động. Mở trace và so sánh prompt/model/tool-set versions để xác định nguyên nhân.

## 21. Đo streaming latency: tổng thời gian và TTFT

ChatClient stream observation đo thời gian của invocation tới khi stream hoàn tất. Nó không tự cho biết token đầu tiên xuất hiện sau bao lâu.

Nếu UX cần cảm nhận tốc độ streaming, instrument riêng:

- **TTFT:** thời gian từ subscription tới chunk đầu tiên có nội dung.
- **Inter-token/chunk latency:** khoảng thời gian giữa các chunks.
- **Stream completion time:** thời gian tới terminal signal complete/error/cancel.

Có thể dùng Timer trong Flux.defer() và ghi timestamp ở doOnNext đầu tiên; khi stream kết thúc, ghi timer hoàn tất. Tách cancel khỏi complete vì stream bị client hủy không đồng nghĩa model trả xong.

Không log toàn bộ chunk text chỉ để đo timing. Chỉ lưu timestamp, chunk index hoặc kích thước nếu cần và được phép.

## 22. Dashboard đề xuất cho traffic, latency, errors và tokens

Một dashboard vận hành cơ bản có thể chia thành các hàng:

| Hàng | Panels | Metric |
|---|---|---|
| Traffic | HTTP requests/s, ChatClient/s, model operations/s | Rate của completed counts |
| Latency | ChatClient mean/P95, model mean/P95 | Timer sum/count, histogram |
| Concurrency | Active ChatClient, active model calls | Active gauges |
| Errors | HTTP failure ratio, model error ratio, provider 429/5xx, tool failures | Failure counters hoặc error tag |
| Tokens | Input/output tokens/minute, tokens/ChatClient | Token counter và ratios |
| Cost | Estimated cost/hour, cost/task, cost/model | Cost pipeline |
| Release context | Prompt/model/tool-set version, deployment | Version metadata và annotations |

Luôn hiển thị traffic cùng latency và errors. P95 tăng khi traffic thấp có thể chỉ là vài requests; P95 ổn định khi traffic giảm về zero cũng không có nghĩa dịch vụ khỏe. Cần synthetic request hoặc availability checks nếu service có thể im lặng khi không có traffic.

## 23. Prometheus alert cho lỗi model và token usage

### 23.1. Model operation error ratio

Nếu timer có tag error:

~~~yaml
groups:
  - name: spring-ai-model
    rules:
      - alert: SpringAiModelErrorRatioHigh
        expr: |
          (
            sum(rate(gen_ai_client_operation_seconds_count{
              gen_ai_operation_name="chat",
              error!="none"
            }[5m]))
            /
            sum(rate(gen_ai_client_operation_seconds_count{
              gen_ai_operation_name="chat"
            }[5m]))
          ) > 0.05
          and
          sum(rate(gen_ai_client_operation_seconds_count{
            gen_ai_operation_name="chat"
          }[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Spring AI model error ratio is above 5%"
          description: "Inspect provider, model, timeout, rate limit and recent releases."
~~~

Ngưỡng 5% và traffic tối thiểu chỉ là ví dụ. Cần hiệu chỉnh theo SLO, traffic và provider. Nếu metric không có error tag, dùng application/provider failure counters thay thế.

### 23.2. Token rate vượt ngưỡng

Ví dụ cảnh báo tổng token rate cao:

~~~yaml
groups:
  - name: spring-ai-token-usage
    rules:
      - alert: SpringAiTokenRateHigh
        expr: |
          sum(rate(gen_ai_client_token_usage_total{
            gen_ai_token_type="total"
          }[5m])) > 50000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Spring AI token usage is unusually high"
          description: "Compare traffic, model operations, input/output tokens and recent prompt changes."
~~~

50.000 tokens/giây là giá trị giả định. Alert theo absolute token rate có thể không phù hợp khi traffic biến động. Trong production, cân nhắc alert theo cost budget, tokens trên mỗi task hoặc baseline theo giờ/ngày.

## 24. Điều tra một đợt tăng latency hoặc token usage

Khi dashboard báo bất thường:

1. Kiểm tra HTTP request rate và ChatClient throughput: traffic có tăng không?
2. Kiểm tra model operations/ChatClient: số model rounds có tăng không?
3. Xem model P95 theo provider/model: provider nào đang chậm?
4. Xem active model calls: có concurrency tăng hoặc backlog không?
5. Kiểm tra error ratio, timeout, 429, 5xx và retry.
6. So input/output token rate: phần nào tăng?
7. Mở trace mẫu để xem advisor, retrieval, tool và model operations.
8. So prompt, model, tool-set, retriever và deployment version.
9. Ước tính cost/task và kiểm tra budget.
10. Chạy lại evaluation dataset để xác định quality regression.

Ví dụ: ChatClient throughput giữ nguyên, model operations/ChatClient tăng từ 1,4 lên 2,7 và input tokens/turn tăng 45%. Hãy kiểm tra tool loop, retry advisor, prompt history và RAG context size trước khi tăng quota provider.

## 25. Cardinality và dữ liệu nhạy cảm

Metric labels phải có tập giá trị hữu hạn. Có thể dùng provider, model family, operation name, stream flag hoặc error class nếu danh mục được kiểm soát.

Không dùng các giá trị sau làm metric labels:

- User ID, tenant ID hoặc account ID không giới hạn.
- Conversation ID, trace ID, request ID.
- Prompt text, completion text hoặc hash duy nhất của prompt.
- Tool arguments/results và query text.
- Dataset case ID nếu mỗi case là một giá trị riêng.

Các giá trị duy nhất theo request nên nằm trong trace hoặc evaluation store có access control và retention phù hợp.

Spring AI không export prompt/completion và tool arguments/results mặc định vì chúng có thể chứa dữ liệu nhạy cảm. Không bật logging content toàn cục chỉ để có thêm labels hoặc debug token spikes. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/).

## 26. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng HTTP request count làm model call count | Bỏ sót tool loops và retries | Theo dõi ChatClient và ChatModel riêng |
| Dùng active count làm throughput | Nhầm concurrency với tốc độ xử lý | Dùng rate của completed count |
| Chỉ xem mean latency | Bỏ qua tail latency | Bật histogram và xem P95/P99 |
| Cộng input, output và total tokens | Double count usage | Chọn input + output hoặc total |
| Coi provider không báo usage là zero | Chi phí bị đánh giá thấp | Theo dõi usage coverage |
| Coi HTTP 200 là answer success | Bỏ qua lỗi nghiệp vụ và factuality | Có business outcome/evaluation metrics |
| Coi mọi model error là provider outage | Bỏ qua lỗi validation hoặc ứng dụng | Phân loại lỗi theo boundary |
| Alert theo token rate tuyệt đối | Cảnh báo khi traffic tăng bình thường | So với baseline, cost/task và budget |
| Dùng model latency thay ChatClient latency | Bỏ qua tools/RAG/advisors | Dashboard cả hai |
| Không phân biệt call và stream | Trộn latency của hai kiểu UX | Dùng stream tag và TTFT riêng |
| Dùng conversation ID làm metric label | Cardinality tăng không giới hạn | Dùng traces/evaluation store |
| Không liên kết release version | Khó tìm nguyên nhân regression | Annotate deployment/prompt/model version |

## 27. Bài tập tự kiểm tra

### Bài 1 — Traffic không đổi nhưng model calls tăng

ChatClient invocations/s giữ nguyên ở 50, model operations/s tăng từ 75 lên 150. Tỷ lệ model operations/ChatClient thay đổi thế nào?

**Đáp án:** Tăng từ 1,5 lên 3 model operations trên mỗi ChatClient invocation. Điều tra tool loop, retries, recursive advisors hoặc model calls bổ sung.

### Bài 2 — Active calls tăng

gen_ai_client_operation_active_count tăng từ 10 lên 80, nhưng model calls/s không tăng. Có thể kết luận throughput tăng không?

**Đáp án:** Không. Active count là concurrency snapshot. Có thể operation đang kéo dài hoặc bị treo; kiểm tra latency, timeout và provider status.

### Bài 3 — Sum và count

Trong 5 phút, rate của model operation seconds sum là 24 giây/giây và rate của seconds count là 12 operations/giây. Mean latency là bao nhiêu?

**Đáp án:** 24 / 12 = 2 giây mỗi model operation.

### Bài 4 — Input tokens tăng

Model operations/ChatClient không đổi nhưng input tokens/ChatClient tăng gấp đôi. Cần kiểm tra gì?

**Đáp án:** Prompt length, conversation history, retrieved context size, tool definitions và caching/provider usage semantics.

### Bài 5 — Token type

Provider báo input 100.000, output 20.000 và total 120.000. Tổng usage là bao nhiêu?

**Đáp án:** 120.000 tokens. Không cộng ba giá trị thành 240.000.

### Bài 6 — Error ratio thấp nhưng answer sai

Model error ratio là 0,1%, HTTP success rate là 99,9%, nhưng user feedback báo câu trả lời sai nhiều. Cần bổ sung gì?

**Đáp án:** Relevance/factuality evaluation, retrieval quality, tool correctness và business outcome metrics. Model operation thành công không đảm bảo nội dung đúng.

### Bài 7 — P95 không có dữ liệu

PromQL histogram_quantile() trả về no data. Cần kiểm tra gì?

**Đáp án:** Histogram đã được bật cho đúng meter ID chưa, series _bucket có được xuất không, label le có tồn tại và query selector có khớp series không.

### Bài 8 — Provider 429 tăng và retry tăng

Model 429 tăng, retry cũng tăng và token rate tăng dù user traffic ổn định. Giải thích khả dĩ?

**Đáp án:** Retry làm tăng model attempts và token usage. Cần kiểm tra retry policy, quota, backoff, concurrency và fallback routing.

## 28. Checklist triển khai

- [ ] Đã định nghĩa riêng HTTP request, user turn, ChatClient invocation và model operation?
- [ ] Đã theo dõi ChatClient throughput và model operations/s?
- [ ] Đã có tỷ lệ model operations trên mỗi ChatClient invocation?
- [ ] Đã theo dõi active ChatClient/model operations như gauge?
- [ ] Đã có mean và P95/P99 latency?
- [ ] Đã bật histogram cho meter ID phù hợp?
- [ ] Đã có model/provider error ratio và user-visible error ratio?
- [ ] Đã phân loại timeout, 429, 5xx và business failure?
- [ ] Đã theo dõi input/output/total tokens đúng cách?
- [ ] Đã đo token rate và tokens trên mỗi task?
- [ ] Đã có cost estimation theo model và bảng giá versioned?
- [ ] Đã tách streaming TTFT khỏi completion latency?
- [ ] Đã giới hạn metric label cardinality?
- [ ] Đã xác nhận metric names/tags qua Actuator và Prometheus exposition?
- [ ] Đã liên kết dashboard với trace và deployment/prompt/model versions?
- [ ] Đã có runbook cho token spike, latency spike và provider throttling?

## 29. Tài liệu tham khảo

1. [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/): observations và Prometheus metrics của ChatClient, ChatModel, token usage, tools và VectorStore.
2. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registry, Actuator metrics endpoint, Prometheus scrape endpoint và histogram configuration.
3. [Prometheus — Metric Types](https://prometheus.io/docs/concepts/metric_types/): counter, gauge, histogram và các kiểu metric.
4. [Prometheus — Instrumentation](https://prometheus.io/docs/practices/instrumentation/): request count, in-progress work, failures, latency và cách đo subsystem.
5. [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): _sum, _count, bucket, quantiles và aggregation.
6. [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): timer count, total time, max, percentiles và histogram.
7. [OpenTelemetry — Semantic Conventions for Generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/): tên attributes và semantics cho model operations, token usage và provider.

*Các PromQL, ngưỡng alert và giá model trong bài là ví dụ. Tên metric/tag thực tế phụ thuộc Spring AI, Spring Boot, registry và provider. Trước khi áp dụng production, xác nhận series tại /actuator/prometheus, kiểm tra coverage của token usage và hiệu chỉnh ngưỡng theo traffic, SLO, model pricing và baseline của hệ thống.*
