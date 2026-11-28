# Chọn chỉ số cho sức khỏe hệ thống và chất lượng câu trả lời

## 1. Dashboard AI cần trả lời hai câu hỏi khác nhau

Một ứng dụng Spring AI có thể vẫn trả HTTP 200 và không có exception, nhưng câu trả lời lại sai, thiếu căn cứ hoặc gọi nhầm tool. Ngược lại, câu trả lời có thể rất tốt nhưng hệ thống mất 12 giây để phản hồi, tiêu thụ quá nhiều tokens hoặc chạm rate limit của nhà cung cấp model.

Vì vậy, một dashboard chỉ hiển thị CPU, HTTP status và latency chưa đủ để vận hành một ứng dụng AI. Cần theo dõi hai mặt:

- **Sức khỏe hệ thống:** ứng dụng có sẵn sàng phục vụ không, phản hồi nhanh hay chậm, có lỗi hoặc nghẽn tài nguyên không, chi phí vận hành có vượt ngân sách không?
- **Chất lượng câu trả lời:** câu trả lời có đúng ý định người dùng, được hỗ trợ bởi bằng chứng, dùng đúng tài liệu và tool, có an toàn và nhất quán không?

Hai nhóm có liên quan nhưng không thay thế nhau. Latency thấp không chứng minh câu trả lời chính xác. Factuality cao trên dataset cũng không chứng minh production đang hoạt động ổn định.

Bài này thuộc chương **Dashboard và cảnh báo** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module học cách đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để tìm nguyên nhân suy giảm theo phiên bản prompt, model và pipeline.

Sau bài, bạn có thể:

1. Chọn các service-level indicators (SLI) cho sức khỏe hệ thống.
2. Xây dựng các chỉ số chất lượng câu trả lời có mẫu số và phạm vi rõ ràng.
3. Phân biệt telemetry có sẵn từ Spring AI với metric chất lượng do ứng dụng định nghĩa.
4. Thiết kế dashboard cho ChatClient, ChatModel, RAG, tools, chi phí và evaluation.
5. Đặt alert dựa trên ảnh hưởng người dùng, SLO và error budget.
6. Phát hiện quality regression trong CI, canary và production.
7. Truy từ alert đến trace, dataset case và phiên bản prompt/model liên quan.

## 2. Phân biệt telemetry vận hành và telemetry chất lượng

Một dashboard nên phân loại dữ liệu trước khi chọn biểu đồ:

| Nhóm | Đo điều gì? | Ví dụ |
|---|---|---|
| System health | Khả năng phục vụ | Availability, latency, throughput, saturation |
| Model/provider | Hoạt động của model | Model operation duration, provider errors, tokens |
| RAG/retrieval | Hoạt động truy xuất | Vector query latency, số documents, recall@k |
| Tool execution | Hoạt động công cụ | Tool success rate, duration, argument validation |
| Answer quality | Chất lượng đầu ra | Relevance, factuality, groundedness, citation correctness |
| Efficiency/cost | Tài nguyên cho một nhiệm vụ | Tokens/turn, cost/successful task, model calls/turn |
| Release health | Thay đổi qua phiên bản | Quality pass rate, latency, cost theo prompt/model version |

Spring AI cung cấp observations cho ChatClient, advisors, ChatModel, EmbeddingModel, ImageModel, VectorStore và tool calling. Chúng giúp biết operation nào chạy, mất bao lâu và có tracing context ra sao.

Spring AI cũng cung cấp Evaluator, RelevancyEvaluator và FactCheckingEvaluator. Tuy nhiên, các score theo dataset, tool correctness, business success rate và quality SLO cần được tổ chức thành evaluation pipeline/metric của ứng dụng. Không suy ra chất lượng câu trả lời chỉ từ observation thành công.

Tài liệu: [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/) và [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html).

## 3. Xác định SLI, SLO và error budget

Trước khi tạo dashboard, cần xác định mục tiêu đo.

- **SLI (Service Level Indicator):** phép đo thể hiện một khía cạnh dịch vụ, ví dụ tỷ lệ request thành công hoặc tỷ lệ phản hồi trong 3 giây.
- **SLO (Service Level Objective):** mục tiêu định lượng trong một khoảng thời gian, ví dụ 99,9% request hợp lệ thành công trong 30 ngày.
- **SLA (Service Level Agreement):** cam kết dịch vụ với khách hàng, thường có hệ quả kinh doanh hoặc hợp đồng.
- **Error budget:** phần sự kiện lỗi được phép có trong kỳ SLO.

Ví dụ SLO vận hành:

| SLI | Định nghĩa ví dụ | SLO minh họa |
|---|---|---:|
| Availability | Tỷ lệ user requests hoàn tất thành công | 99,9% / 30 ngày |
| Latency | Tỷ lệ ChatClient requests hoàn tất trong 4 giây | 95% / 30 ngày |
| Tool reliability | Tỷ lệ tool executions kết thúc thành công | 99,5% / 30 ngày |
| Evaluation quality | Tỷ lệ case factuality pass trên dataset cố định | Ít nhất 95% mỗi release |
| Retrieval quality | Recall@5 trên bộ truy vấn có gold documents | Ít nhất 90% mỗi release |

Các con số trên chỉ là ví dụ để minh họa cách viết mục tiêu. SLO thực tế phải dựa trên nhu cầu người dùng, rủi ro nghiệp vụ, baseline và chi phí vận hành.

Không gộp tất cả thành một “AI health score” duy nhất. Availability và factuality đo hai loại rủi ro khác nhau; một score tổng có thể che khuất một chiều đang suy giảm nghiêm trọng.

### 3.1. Viết SLI thành tỷ lệ good events trên total events

Ví dụ SLI latency:

\[
LatencySLI =
\frac{\text{Số request hoàn tất trong ngưỡng}}
{\text{Tổng request hợp lệ}}
\]

Ví dụ SLI availability:

\[
AvailabilitySLI =
\frac{\text{Số request thành công}}
{\text{Tổng request hợp lệ}}
\]

Ví dụ SLI factuality:

\[
FactualityPassRate =
\frac{\text{Evaluation cases đạt factuality}}
{\text{Evaluation cases được chấm hợp lệ}}
\]

Mỗi tỷ lệ cần định nghĩa rõ:

- Request/case nào nằm trong mẫu số?
- Timeout, cancellation, evaluator error có được tính là bad event hay được theo dõi riêng?
- Có loại trừ request bị người dùng hủy hoặc input không hợp lệ không?
- Dữ liệu được lấy từ production, canary hay bộ dataset cố định?
- Khoảng thời gian và phiên bản nào đang được so sánh?

Nếu mẫu số thay đổi giữa các phiên bản, tỷ lệ có thể thay đổi dù chất lượng thực không đổi.

## 4. Nhóm chỉ số sức khỏe hệ thống: bốn golden signals

Một cách bắt đầu thực tế là theo dõi bốn nhóm tín hiệu:

| Golden signal | Câu hỏi | Ví dụ chỉ số |
|---|---|---|
| Latency | Người dùng phải chờ bao lâu? | HTTP P95, ChatClient P95, time-to-first-token |
| Traffic | Hệ thống đang xử lý bao nhiêu tải? | Requests/s, ChatClient calls/s, model calls/s |
| Errors | Bao nhiêu request không hoàn tất đúng? | User-visible error ratio, timeout, provider error |
| Saturation | Tài nguyên nào gần hết? | CPU, heap, thread pool, connection pool, in-flight calls |

Với AI, nên bổ sung hai chiều quan trọng:

- **Cost/usage:** tokens, model operations, tool calls, chi phí trên mỗi tác vụ thành công.
- **Quality:** relevance, factuality, retrieval quality, tool correctness và human feedback.

Một hệ thống có thể có traffic tăng nhưng model provider bắt đầu trả 429. Một hệ thống có thể có error rate thấp nhưng tool trả dữ liệu rỗng và model vẫn sinh câu trả lời. Vì vậy, hãy theo dõi cả lớp ứng dụng, lớp model và lớp nghiệp vụ.

## 5. Chọn latency metric đúng với trải nghiệm người dùng

Không có một latency duy nhất cho mọi ứng dụng AI.

| Metric | Bắt đầu/kết thúc | Phù hợp để đo |
|---|---|---|
| HTTP server duration | Nhận HTTP request đến khi trả response | Trải nghiệm API tổng thể |
| ChatClient duration | Bắt đầu call()/stream() đến khi invocation hoàn tất | Toàn bộ xử lý trong ChatClient |
| ChatModel operation duration | Một lần ChatModel call()/stream() | Độ trễ provider/model |
| Tool duration | Bắt đầu đến khi tool execution kết thúc | Công cụ bên ngoài |
| VectorStore duration | Một thao tác query/add/upsert/delete | Kho vector |
| Time to first token (TTFT) | Bắt đầu stream đến token đầu tiên | Cảm nhận tốc độ bắt đầu phản hồi |
| Time between tokens | Khoảng cách giữa các chunks/tokens | Độ mượt của streaming |

Với ChatClient streaming, người dùng có thể nhìn thấy token đầu tiên khá sớm nhưng phải chờ lâu mới có câu trả lời hoàn chỉnh. Vì vậy cần đo cả TTFT và thời gian hoàn tất stream nếu UX phụ thuộc streaming.

Spring AI ghi ChatClient observation khi gọi call() hoặc stream() và đo thời gian thực hiện invocation. ChatModel observation đo thời gian hoàn tất method call/stream. Nếu cần TTFT hoặc inter-token latency, hãy bổ sung instrumentation ở ranh giới stream của ứng dụng.

Tài liệu: [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/).

### 5.1. Không thay latency tổng bằng model latency

ChatClient duration có thể bao gồm advisor chain, memory, retrieval, tool loop, post-processing và nhiều model calls. Model duration chỉ đo operation ở tầng ChatModel.

Nếu ChatClient P95 tăng nhưng model P95 ổn định, hãy điều tra RAG, tools, memory, advisor và service overhead. Nếu model P95 tăng, hãy kiểm tra provider, token count, rate limits, network và retry behavior.

Không cộng duration của ChatClient, advisor, model và tool thành tổng latency. Các khoảng đo có thể lồng nhau hoặc chạy song song.

## 6. Các metric Spring AI có thể dùng trực tiếp

Spring AI 2.1.0 công bố các metric Prometheus cho ChatClient, ChatModel, token usage và VectorStore:

| Metric | Ý nghĩa | Dùng trên dashboard |
|---|---|---|
| gen_ai_chat_client_operation_seconds_count | Số ChatClient operations hoàn tất | Traffic của ChatClient |
| gen_ai_chat_client_operation_seconds_sum | Tổng thời gian ChatClient operations | Mean duration |
| gen_ai_chat_client_operation_seconds_max | Duration lớn nhất quan sát được | High-water mark |
| gen_ai_chat_client_operation_active_count | ChatClient operations đang chạy | In-flight load |
| gen_ai_client_operation_seconds_count | Số model operations hoàn tất | Model call volume |
| gen_ai_client_operation_seconds_sum | Tổng thời gian model operations | Mean model duration |
| gen_ai_client_operation_active_count | Model operations đang chạy | Provider concurrency |
| gen_ai_client_token_usage_total | Tokens do provider báo cáo | Token usage/cost |
| db_vector_client_operation_seconds_count | VectorStore operations hoàn tất | Retrieval/storage volume |
| db_vector_client_operation_seconds_sum | Tổng thời gian VectorStore operations | Mean vector duration |
| db_vector_client_operation_active_count | VectorStore operations đang chạy | Vector DB concurrency |

Token usage có tag gen_ai_token_type với các giá trị input, output và total. Khi tính tổng, chọn input + output hoặc total, không cộng cả ba.

Các observation spring.ai.advisor và spring.ai.tool cũng cung cấp tracing/observation để phân tích từng advisor và tool. Tên meter/series xuất ra phụ thuộc Observation handler, registry và cấu hình; kiểm tra metric exposition thực tế trước khi viết query production.

Tài liệu: [Spring AI — Observability, More Metrics Reference](https://docs.spring.io/spring-ai/reference/observability/).

### 6.1. Active count khác completed count

- *_active_count là gauge số operation đang chạy tại thời điểm scrape.
- *_seconds_count là số operation đã hoàn tất.
- *_seconds_sum là tổng duration của những operation đã hoàn tất.

Active count giúp nhìn concurrency và backlog; nó không phải số request mới trong khoảng thời gian. Không cộng active count với completed count thành throughput.

## 7. Chỉ số chất lượng câu trả lời cần đo

Một câu trả lời “đúng” có nhiều chiều. Tùy sản phẩm, có thể chọn:

| Dimension | Câu hỏi đánh giá | Cách đo gợi ý |
|---|---|---|
| Relevance | Có trả lời đúng điều người dùng hỏi không? | RelevancyEvaluator, human rubric |
| Factuality | Các khẳng định có đúng theo nguồn tin không? | FactCheckingEvaluator, gold evidence |
| Groundedness | Câu trả lời có được hỗ trợ bởi context đã truy xuất không? | Claim-to-context checks |
| Completeness | Có bỏ sót phần quan trọng của yêu cầu không? | Rubric theo expected points |
| Citation correctness | Trích dẫn có tồn tại và hỗ trợ claim không? | Citation validation |
| Retrieval quality | Tài liệu liên quan có được lấy về không? | Recall@k, precision@k, MRR, nDCG |
| Tool selection | Model có chọn đúng công cụ không? | Expected tool assertions |
| Tool arguments | Arguments có đúng schema và ý định không? | Schema/semantic validation |
| Tool outcome | Tool có trả dữ liệu hợp lệ không? | Tool success/business assertions |
| Safety/policy | Có tuân thủ chính sách sản phẩm không? | Policy test, moderation, human review |

Không dùng một LLM judge score để đại diện cho tất cả dimensions. Một câu trả lời có thể liên quan nhưng không có căn cứ; retrieval có thể tốt nhưng model diễn giải sai; tool có thể chạy thành công nhưng được gọi với arguments sai.

## 8. Đo relevance và factuality bằng Evaluator

Spring AI cung cấp Evaluator API với hai evaluator hữu ích:

- RelevancyEvaluator: so sánh user query, response và retrieved context để đánh giá câu trả lời có phù hợp với câu hỏi và context không.
- FactCheckingEvaluator: kiểm tra claim trong response có được document/context hỗ trợ không.

Ví dụ quy trình trong integration test:

~~~java
ChatResponse chatResponse = chatClient.prompt(question)
    .advisors(ragAdvisor)
    .call()
    .chatResponse();

EvaluationRequest request = new EvaluationRequest(
    question,
    chatResponse.getMetadata()
        .get(RetrievalAugmentationAdvisor.DOCUMENT_CONTEXT),
    chatResponse.getResult().getOutput().getText()
);

EvaluationResponse result = relevancyEvaluator.evaluate(request);

assertThat(result.isPass()).isTrue();
~~~

Đây là ví dụ rút gọn theo tài liệu Spring AI; cần cấu hình evaluator và context phù hợp với ứng dụng. Evaluation có thể dùng model khác model sinh câu trả lời.

Tài liệu: [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html).

### 8.1. Đánh giá model-as-judge cần có kiểm soát

LLM judge cũng có thể sai, thiên lệch hoặc thay đổi khi model/rubric đổi. Để score có ý nghĩa:

1. Tạo bộ case đã được con người gán nhãn.
2. Xác định rubric và tiêu chí pass/fail rõ ràng.
3. Cố định judge model, prompt và rubric version trong một đợt so sánh.
4. So judge result với human labels để đo agreement.
5. Review các case judge bất đồng hoặc có độ tin cậy thấp.
6. Không coi evaluator error/timeout là pass.
7. Lưu evaluation version và evidence để tái lập kết quả.

Nếu đổi generator model và judge model cùng lúc, không thể biết score đổi do chất lượng generator hay do judge.

## 9. Chỉ số chất lượng cho RAG

Đối với RAG, cần đo riêng retrieval và generation.

**Retrieval metrics:**

- Recall@k: trong top-k documents có bao nhiêu gold-relevant documents được lấy về?
- Precision@k: trong top-k documents có bao nhiêu documents thực sự liên quan?
- MRR: thứ hạng của kết quả liên quan đầu tiên.
- nDCG@k: chất lượng xếp hạng khi relevance có nhiều mức.
- Context precision/recall: context được đưa vào model có tập trung và bao phủ bằng chứng cần thiết không?

**Generation metrics:**

- Relevance: câu trả lời có giải quyết query không?
- Groundedness/factuality: claim có được hỗ trợ bởi context không?
- Citation accuracy: nguồn được trích có hỗ trợ nội dung không?
- Completeness: có bỏ sót ý quan trọng không?

Ví dụ:

| Case | Recall@5 | Relevance | Factuality | Diễn giải |
|---|---:|---|---|---|
| Q-01 | 1,00 | Pass | Pass | Retrieval và generation đều tốt |
| Q-02 | 0,20 | Fail | Pass | Ít evidence được truy xuất; câu trả lời thận trọng |
| Q-03 | 1,00 | Pass | Fail | Có tài liệu đúng nhưng model diễn giải sai |
| Q-04 | 0,80 | Pass | Pass | Đạt tiêu chí, còn khả năng cải thiện retrieval |

Các giá trị chỉ minh họa. Không lấy similarity score của vector store làm recall hoặc factuality. Similarity là tín hiệu xếp hạng, còn relevance/factuality cần gold labels hoặc evaluator phù hợp.

## 10. Chỉ số chất lượng cho tool calling

Một tool invocation có thể thành công về mặt kỹ thuật nhưng sai về nghiệp vụ. Theo dõi ít nhất:

| Metric | Định nghĩa |
|---|---|
| Tool selection accuracy | Tỷ lệ model chọn đúng tool kỳ vọng |
| Argument validity | Tỷ lệ arguments hợp schema và semantic constraints |
| Tool execution success rate | Tỷ lệ tool execution hoàn tất không lỗi |
| Business outcome success | Tỷ lệ tool trả kết quả đáp ứng điều kiện nghiệp vụ |
| Unnecessary tool calls | Số tool calls dư thừa trên mỗi user turn |
| Tool calls per task | Số lần gọi tool trung bình để hoàn thành một tác vụ |
| Authorization rejection | Số lần tool call bị từ chối vì quyền truy cập |

Không dùng spring.ai.tool execution count làm tool correctness. Observation cho biết tool được thực thi, thời gian và metadata; nó không chứng minh model chọn đúng tool hoặc arguments đúng.

Với tool có side effects, đánh giá thêm idempotency, duplicate execution và trạng thái transaction. Không đưa raw arguments hoặc kết quả chứa dữ liệu riêng tư vào metric labels.

## 11. Đo chi phí và hiệu quả trên mỗi tác vụ

Một hệ thống AI có thể tăng chất lượng bằng cách dùng nhiều model calls hoặc retrieval hơn. Dashboard cần cho biết chi phí tăng có tạo ra giá trị hay không.

Các chỉ số hữu ích:

- Input tokens trên mỗi user turn.
- Output tokens trên mỗi user turn.
- Tổng tokens trên mỗi successful task.
- Model operations trên mỗi ChatClient invocation.
- Tool executions trên mỗi successful task.
- Cost trên mỗi 1.000 turns.
- Cost trên mỗi successful task.
- Tỷ lệ cache-read tokens nếu provider hỗ trợ.
- Chi phí theo model/provider và release.

Một công thức khái niệm:

\[
CostPerSuccessfulTask =
\frac{\text{Tổng chi phí model + tool + retrieval}}
{\text{Số tác vụ hoàn tất đạt tiêu chí}}
\]

Giá model thay đổi theo provider, model, cache, region và thời điểm. Hãy lưu bảng giá có version và currency rõ ràng. Không dùng token count như chi phí chính xác nếu chưa áp dụng đúng bảng giá và quy tắc billing.

Spring AI có metric gen_ai_client_token_usage_total cho token usage do provider báo cáo. Một số provider có thể không trả usage cho mọi operation; missing usage cần được ghi nhận riêng thay vì coi như zero-cost.

## 12. Tách online evaluation và offline evaluation

Không phải tiêu chí chất lượng nào cũng có thể chấm chính xác ngay trong request phục vụ người dùng.

| Cách đánh giá | Dữ liệu | Thời điểm | Mục tiêu |
|---|---|---|---|
| Offline evaluation | Golden dataset, gold documents, expected tool calls | CI, trước release, nightly | So sánh prompt/model/pipeline |
| Online sampled evaluation | Một mẫu production conversations | Sau response, bất đồng bộ | Phát hiện drift thực tế |
| Human review | Feedback và sample được chọn | Theo lịch hoặc khi có tranh chấp | Hiệu chỉnh judge và rubric |
| Product feedback | Rating, correction, escalation, task completion | Sau tương tác | Hiểu kết quả người dùng cảm nhận |

Online evaluation bằng model judge có thể tốn tokens, tăng chi phí và thêm latency nếu chạy đồng bộ. Thường nên chạy bất đồng bộ hoặc sampling có kiểm soát, lưu trace/run IDs để liên kết kết quả.

Đừng đưa evaluator vào critical path nếu chưa đo ảnh hưởng của nó đến latency và availability. Nếu evaluator hỏng, câu trả lời phục vụ người dùng vẫn cần có outcome riêng; không để evaluator error biến thành request success hoặc failure một cách vô tình.

## 13. Thiết kế metric names và labels cho chất lượng

Spring AI không tự tạo mọi business quality metrics. Ứng dụng có thể định nghĩa counters/histograms riêng, ví dụ:

~~~text
app_ai_user_requests_total{route,result}
app_ai_request_duration_seconds (histogram; exports bucket/count/sum)
app_ai_tool_executions_total{tool,result}
app_ai_eval_cases_total{criterion,result,prompt_version}
app_ai_quality_score (histogram of normalized evaluator scores)
app_ai_cost_usd_total{model_family}
~~~

Ví dụ labels có phạm vi hữu hạn:

- route: chat, rag, agent.
- result: good, bad, error, skipped.
- criterion: relevance, factuality, tool_selection, citation.
- model_family: danh sách model được kiểm soát.
- prompt_version: release versions có vòng đời hữu hạn.
- tool: tên tool trong danh mục đã đăng ký.

Không dùng user_id, conversation_id, trace_id, case_id, prompt hash hoặc nội dung query làm metric labels. Các giá trị đó tạo cardinality cao; hãy lưu chúng trong trace hoặc evaluation store có quyền truy cập phù hợp.

Spring AI phân loại low-cardinality keys để đưa vào cả metrics và traces, còn high-cardinality keys chỉ vào traces. Prompt/completion và tool arguments/results không được export mặc định vì có thể chứa dữ liệu nhạy cảm.

Tài liệu: [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/).

## 14. Dashboard 1: sức khỏe tổng thể

Dashboard đầu tiên phải trả lời trong vài giây: hệ thống có đang phục vụ tốt không?

Gợi ý các panel:

| Panel | Chỉ số | Cách hiển thị |
|---|---|---|
| Request volume | User requests/s | Time series |
| Availability | Good requests / total requests | Stat + time series |
| Error rate | Bad requests / total requests | Time series |
| ChatClient latency | P50/P95/P99 | Histogram quantile |
| Streaming TTFT | P50/P95 | Time series |
| In-flight operations | Active ChatClient calls | Gauge |
| Saturation | CPU, heap, GC, thread/connection pool | Time series |
| SLO budget | Error budget remaining / burn rate | Stat + time series |

Dùng màu/trạng thái để làm nổi bật vi phạm SLO. Đặt link từ panel latency/error tới trace explorer và log dashboard để điều tra.

## 15. Dashboard 2: model và provider

Dashboard model giúp phân biệt lỗi từ ứng dụng với lỗi hoặc giới hạn của provider.

| Panel | Chỉ số |
|---|---|
| Model operations/s | Số ChatModel calls mỗi giây |
| Model latency | Mean/P95 theo provider/model |
| Provider errors | Error rate, timeout, 429, 5xx |
| In-flight model calls | Concurrency |
| Tokens | Input/output/total tokens theo model |
| Model finish reason | Tỷ lệ stop, length limit, tool calls nếu instrument |
| Fallback rate | Tỷ lệ chuyển sang model dự phòng |
| Cost | Ước tính chi phí theo model và thời gian |

Nếu provider A chậm trong khi provider B ổn định, có thể cần fallback hoặc điều chỉnh routing. Nếu cả hai cùng chậm, hãy xem application saturation, network và request complexity.

## 16. Dashboard 3: RAG và tools

Tách các panel retrieval và tool execution để biết phần nào làm pipeline suy giảm.

**RAG panels:**

- VectorStore query count và latency.
- Query errors/timeouts.
- Documents returned per query.
- Recall@k và precision@k trên evaluation set.
- Context precision/recall.
- Retrieval empty-result rate.
- Index freshness và ingestion lag nếu có pipeline cập nhật dữ liệu.

**Tool panels:**

- Tool executions/s theo tool.
- Tool success/error rate.
- Tool latency P50/P95.
- Argument validation failures.
- Authorization rejections.
- Duplicate/timeout/retry count.
- Tool calls per successful task.

VectorStore observations của Spring AI ghi nhận query/add/upsert/delete duration và tracing. Tool observations ghi tên tool và thời gian hoàn tất. Chỉ số recall, tool selection và business outcome cần được ứng dụng đánh giá riêng.

Tài liệu: [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/).

## 17. Dashboard 4: chất lượng câu trả lời

Dashboard chất lượng nên hiển thị score theo từng dimension, kèm sample size và phiên bản.

| Panel | Metric |
|---|---|
| Relevance pass rate | Pass / evaluated cases |
| Factuality pass rate | Claims/cases được evidence hỗ trợ |
| Groundedness | Tỷ lệ claim được context hỗ trợ |
| Citation correctness | Tỷ lệ citation hợp lệ |
| Retrieval recall@k | Trên dataset có gold documents |
| Tool selection accuracy | Tỷ lệ chọn đúng tool |
| Tool argument accuracy | Tỷ lệ arguments đúng |
| Human feedback | Helpful/unhelpful hoặc correction rate |
| Evaluation coverage | Cases được chấm / cases dự kiến |

Luôn hiển thị:

- Số cases đã chấm.
- Tỷ lệ evaluator errors/skipped.
- Judge model và rubric version.
- Prompt/model/tool-set version.
- Thời gian dữ liệu được thu thập.

Một pass rate 100% trên 5 cases không có độ tin cậy như 98% trên 5.000 cases. Không ẩn sample size sau một phần trăm.

## 18. Dashboard 5: release comparison và cost

Mỗi lần thay prompt, model, retriever hoặc tool definitions cần có so sánh với baseline.

| Chỉ số | Baseline | Candidate | Thay đổi |
|---|---:|---:|---:|
| Relevance pass rate | 94% | 96% | +2 điểm % |
| Factuality pass rate | 95% | 92% | -3 điểm % |
| Tool selection accuracy | 97% | 98% | +1 điểm % |
| ChatClient P95 | 2,8 s | 3,4 s | +0,6 s |
| Tokens/task | 3.100 | 3.800 | +22,6% |
| Cost/successful task | $0,012 | $0,016 | +33,3% |

Số liệu chỉ minh họa. Candidate có thể cải thiện relevance nhưng làm factuality giảm và chi phí tăng. Một dashboard release tốt phải cho thấy cả quality và efficiency, không chỉ một score tổng.

Giữ cố định dataset, judge model, rubric và cấu hình evaluation khi so sánh. Nếu có thay đổi, ghi lại trong report để tránh quy nguyên nhân sai.

## 19. Cấu hình Spring Boot Actuator và histogram

Spring Boot Actuator cung cấp Micrometer registry và endpoint để xem metrics. Ví dụ cấu hình Prometheus và histogram:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus

  metrics:
    tags:
      application: spring-ai-evaluation-observability
    distribution:
      percentiles-histogram:
        gen.ai.chat.client.operation: true
        gen.ai.client.operation: true
        db.vector.client.operation: true

spring:
  ai:
    chat:
      client:
        observations:
          log-prompt: false
          log-completion: false
    tools:
      observations:
        include-content: false
    vectorstore:
      observations:
        log-query-response: false
~~~

Đây là cấu hình minh họa; kiểm tra property prefix và meter ID theo phiên bản Spring Boot/Spring AI của dự án. Prometheus scrape endpoint thường là /actuator/prometheus và cần được expose. Endpoint metrics/Prometheus nên được giới hạn mạng và bảo vệ bằng authentication phù hợp, không mở công khai chỉ để tiện debug.

Tài liệu: [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).

## 20. PromQL cho các chỉ số vận hành

Các query sau dùng tên metric Prometheus của Spring AI 2.1.0 hoặc metric business do ứng dụng định nghĩa.

### 20.1. Mean ChatClient latency

~~~promql
sum(rate(gen_ai_chat_client_operation_seconds_sum[5m]))
/
sum(rate(gen_ai_chat_client_operation_seconds_count[5m]))
~~~

### 20.2. Mean model operation latency theo provider

~~~promql
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_sum{gen_ai_operation_name="chat"}[5m])
)
/
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_count{gen_ai_operation_name="chat"}[5m])
)
~~~

### 20.3. Mean VectorStore query latency

~~~promql
sum by (db_system) (
  rate(db_vector_client_operation_seconds_sum{db_operation_name="query"}[5m])
)
/
sum by (db_system) (
  rate(db_vector_client_operation_seconds_count{db_operation_name="query"}[5m])
)
~~~

### 20.4. P95 ChatClient latency

Bật histogram cho meter ID gen_ai.chat.client.operation, sau đó:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(gen_ai_chat_client_operation_seconds_bucket[5m])
  )
)
~~~

### 20.5. Token usage mỗi phút theo model và token type

~~~promql
sum by (gen_ai_request_model, gen_ai_token_type) (
  rate(gen_ai_client_token_usage_total{gen_ai_token_type!="total"}[5m])
) * 60
~~~

Đây là số tokens theo phút từ usage provider báo cáo. Nếu cần chi phí, kết hợp usage với bảng giá có version; không coi token count là USD.

## 21. PromQL cho quality metrics do ứng dụng định nghĩa

Giả sử ứng dụng ghi counter:

~~~text
app_ai_eval_cases_total{
  criterion="factuality",
  result="pass|fail|error",
  prompt_version="v12"
}
~~~

Tỷ lệ factuality pass:

~~~promql
sum(rate(app_ai_eval_cases_total{criterion="factuality",result="pass"}[1h]))
/
sum(rate(app_ai_eval_cases_total{criterion="factuality",result=~"pass|fail"}[1h]))
~~~

Tỷ lệ evaluator error cần xem riêng:

~~~promql
sum(rate(app_ai_eval_cases_total{criterion="factuality",result="error"}[1h]))
/
sum(rate(app_ai_eval_cases_total{criterion="factuality"}[1h]))
~~~

Số case được chấm trong một giờ:

~~~promql
sum(increase(app_ai_eval_cases_total{criterion="factuality",result=~"pass|fail"}[1h]))
~~~

Không đánh giá pass rate khi sample quá nhỏ. Có thể chỉ kích hoạt cảnh báo quality regression khi số case hợp lệ trong cửa sổ đạt ngưỡng, ví dụ ít nhất 100 cases. Ngưỡng sample cần được xác định theo độ biến động và độ tin cậy mong muốn.

Nếu evaluator error tăng, đó có thể là lỗi của judge/provider hoặc pipeline evaluation. Không trộn evaluator error với answer fail, vì hai sự kiện cần cách xử lý khác nhau.

## 22. Alert theo SLO và error budget

Một alert tốt báo cho người trực biết có ảnh hưởng người dùng đủ lớn để cần hành động. Prometheus khuyến nghị ưu tiên alert trên triệu chứng ở tầng cao, như latency và error rate của request, rồi dùng dashboard để xác định nguyên nhân.

Tài liệu: [Prometheus — Alerting](https://prometheus.io/docs/practices/alerting/).

Ví dụ SLO availability là 99,9% trong 30 ngày:

\[
AllowedErrorRatio = 1 - 0.999 = 0.001
\]

Burn rate là tốc độ tiêu thụ error budget so với tốc độ được phép. Burn rate 1 nghĩa là nếu tốc độ lỗi giữ nguyên, budget sẽ vừa hết vào cuối kỳ SLO.

Google SRE gợi ý multi-window, multi-burn-rate alerts. Với SLO 99,9%, ví dụ mức page nhanh là 14,4x trong cửa sổ 1 giờ và 5 phút; mức 6x trong 6 giờ và 30 phút cũng là một mức page tham khảo. Các ngưỡng cần điều chỉnh theo traffic và trách nhiệm trực vận hành.

Tài liệu: [Google SRE — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/).

### 22.1. Ví dụ alert khi user-visible error budget burn nhanh

Metric app_ai_user_requests_total là counter do ứng dụng định nghĩa, với label result="good" hoặc result="bad".

~~~yaml
groups:
  - name: spring-ai-slo
    rules:
      - alert: AiUserRequestErrorBudgetBurnFast
        expr: |
          (
            sum(rate(app_ai_user_requests_total{result="bad"}[1h]))
            /
            sum(rate(app_ai_user_requests_total[1h]))
          ) > (14.4 * 0.001)
          and
          (
            sum(rate(app_ai_user_requests_total{result="bad"}[5m]))
            /
            sum(rate(app_ai_user_requests_total[5m]))
          ) > (14.4 * 0.001)
          and
          sum(increase(app_ai_user_requests_total[5m])) > 100
        for: 2m
        labels:
          severity: page
        annotations:
          summary: "AI user request error budget is burning quickly"
          description: "Check ChatClient traces, provider errors, tools and recent releases."
~~~

Đây là rule minh họa cho SLO 99,9%, không phải cấu hình dùng chung cho mọi hệ thống. Điều kiện số request tối thiểu giúp tránh cảnh báo từ vài request lẻ trong traffic thấp. Với traffic rất thấp, cần synthetic checks hoặc cách đánh giá riêng.

### 22.2. Alert latency theo trải nghiệm người dùng

Với latency SLO, nên đếm tỷ lệ request vượt ngưỡng thay vì chỉ nhìn một con số P95. Ví dụ ứng dụng có histogram app_ai_request_duration_seconds_bucket:

~~~promql
sum(rate(app_ai_request_duration_seconds_count[5m]))
~~~

Tỷ lệ request hoàn tất trong 4 giây có thể tính từ bucket le="4":

~~~promql
sum(rate(app_ai_request_duration_seconds_bucket{le="4"}[5m]))
/
sum(rate(app_ai_request_duration_seconds_count[5m]))
~~~

Metric này đo trực tiếp tỷ lệ good latency events. P95 vẫn hữu ích để quan sát phân phối, nhưng SLO ratio thường thuận tiện hơn để tính error budget.

## 23. Alert quality regression nên khác alert availability

Quality regression thường nên chặn release, cảnh báo đội phát triển hoặc yêu cầu review canary. Nó không nhất thiết phải page on-call như một outage, nhất là khi score đến từ offline evaluator có độ trễ.

Ví dụ quality gate:

~~~text
Dataset: support-questions-v5
Minimum evaluated cases: 500

Factuality pass rate >= 95%
Relevance pass rate >= 94%
Tool selection accuracy >= 97%
Evaluator error rate <= 1%

If any required criterion fails:
  do not promote candidate prompt/model version
  attach failed case IDs and evaluation traces
  require review before rollout
~~~

Đây là chính sách release minh họa. Chọn ngưỡng theo rủi ro nghiệp vụ và baseline.

Nếu có online quality sampling, có thể phát cảnh báo warning khi pass rate giảm dưới ngưỡng trong một cửa sổ đủ lớn. Luôn có minimum sample size, evaluator health và judge version. Không page khi chỉ có một vài sample hoặc khi judge service đang lỗi.

## 24. Phân loại alert theo hành động

| Mức | Ví dụ | Hành động |
|---|---|---|
| Page | User-visible availability/latency SLO burn nghiêm trọng | On-call điều tra ngay |
| Ticket | Error budget tiêu thụ chậm nhưng kéo dài | Tạo công việc khắc phục |
| Warning | Provider 429 tăng, vector latency tăng nhưng SLO chưa vi phạm | Theo dõi và điều tra trong giờ làm |
| Release gate | Factuality/relevance/tool correctness không đạt | Không promote candidate |
| Quality review | Human feedback xấu hoặc judge disagreement tăng | Review sample và hiệu chỉnh rubric |

Tránh tạo alert cho mọi metric kỹ thuật. Ví dụ vector query chậm hơn baseline nhưng ChatClient SLO vẫn tốt có thể là tín hiệu điều tra, chưa chắc cần page. Alert phải gắn với hành động cụ thể và link tới dashboard/runbook.

## 25. Runbook khi dashboard báo suy giảm

Một quy trình điều tra có thể đi theo thứ tự:

1. **Xác nhận ảnh hưởng:** HTTP/ChatClient availability, latency, traffic và error rate có thay đổi không?
2. **Xác định phạm vi:** chỉ một route, model, tenant class, tool hay toàn bộ traffic?
3. **So với release:** có thay prompt, model, tool set, RAG index, evaluator hoặc infrastructure không?
4. **Mở trace:** xem ChatClient, advisors, ChatModel, tools và VectorStore spans.
5. **Kiểm tra provider:** timeout, 429, 5xx, model latency, token usage và fallback.
6. **Kiểm tra retrieval/tool:** empty retrieval, query latency, tool errors, arguments và business result.
7. **Kiểm tra quality:** relevance, factuality, retrieval recall, tool correctness và human feedback.
8. **Đánh giá chi phí:** tokens/task, model operations/task và cost/successful task.
9. **Chọn hành động:** rollback, giảm traffic canary, đổi provider, sửa prompt, cập nhật index hoặc khắc phục tool.
10. **Ghi lại kết quả:** trace IDs, case IDs, prompt/model/rubric versions và quyết định.

Một alert không nên chỉ nói “AI quality is low”. Nó cần cho biết criterion, sample size, release version, baseline và link đến các failed cases.

## 26. Cardinality và bảo vệ dữ liệu

Metric labels nên có số giá trị hữu hạn. Tránh các nhãn như:

- User ID, account ID, tenant ID không giới hạn.
- Conversation ID, trace ID, request ID.
- Dataset case ID hoặc tool call ID.
- Raw prompt, completion, tool arguments/results.
- Query string hoặc document contents.

Các giá trị định danh từng request nên nằm trong traces hoặc evaluation store có quyền truy cập và retention phù hợp. Spring AI đánh dấu conversation ID, danh sách tools và nhiều request details là high-cardinality attributes; chúng phù hợp với traces hơn metrics.

Prompt/completion, tool arguments/results và vector query response không được export mặc định ở các cấu hình tương ứng. Chỉ bật khi có nhu cầu debug rõ ràng, có redaction, access control và thời hạn lưu.

Tài liệu: [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/).

## 27. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ dashboard CPU và HTTP 200 | Bỏ qua câu trả lời sai | Thêm quality evaluation |
| Dùng model latency làm user latency | Bỏ qua advisor/tool/RAG overhead | Theo dõi ChatClient và HTTP duration |
| Gộp mọi quality dimension thành một score | Che khuất factuality hoặc tool failure | Hiển thị từng criterion |
| Dùng similarity score làm factuality | Đánh giá sai retrieval và answer | Dùng gold docs, evaluator và claim checks |
| Chỉ dùng LLM judge | Score có thể thiên lệch hoặc drift | Calibrate với human-labeled set |
| Không hiển thị sample size | Một score nhỏ bị hiểu quá mức | Luôn show evaluated count |
| Coi evaluator error là pass | Quality dashboard bị lạc quan giả | Theo dõi pass/fail/error/skipped riêng |
| Alert theo mọi model/tool latency | Alert fatigue | Page theo user-facing SLO, dùng component metrics để chẩn đoán |
| Dùng conversation ID làm metric label | Cardinality bùng nổ | Dùng trace/evaluation store |
| Coi tool execution success là tool correctness | Tool có thể chạy sai arguments | Đánh giá selection, arguments và business outcome |
| So release nhưng đổi judge/rubric cùng lúc | Không xác định nguyên nhân score đổi | Cố định evaluation setup hoặc tách thí nghiệm |
| Cảnh báo quality khi sample quá nhỏ | False positive | Minimum sample và cửa sổ đủ dài |
| Không đo cost/task | Tối ưu chất lượng nhưng vượt ngân sách | Cost/successful task và tokens/task |
| Không có runbook | Alert không dẫn tới hành động | Link dashboard, trace và release metadata |

## 28. Bài tập tự kiểm tra

### Bài 1 — Service khỏe nhưng câu trả lời sai

HTTP success rate là 99,99%, ChatClient P95 là 1,2 giây nhưng factuality pass rate giảm từ 96% xuống 81%. Dashboard nào cần mở?

**Đáp án:** Dashboard quality và release comparison. Xem failed cases, retrieved context, prompt/model version và judge/rubric version. HTTP success không đo factuality.

### Bài 2 — Model chậm hay RAG chậm?

ChatClient P95 tăng 2 giây nhưng ChatModel P95 không đổi. Cần điều tra gì?

**Đáp án:** Advisor, VectorStore, tools, memory, application queue và post-processing. ChatClient duration bao gồm nhiều phần ngoài model.

### Bài 3 — Similarity score tăng

Vector similarity score trung bình tăng từ 0,72 lên 0,84. Có thể kết luận retrieval quality tốt hơn không?

**Đáp án:** Chưa. Cần đánh giá recall@k, precision@k hoặc ranking metrics trên dataset có gold documents. Similarity score không tự chứng minh relevance.

### Bài 4 — Quality pass rate 100%

Một release có factuality 100% trên 4 cases. Có nên page khi pass rate giảm còn 90% trên 10 cases ở giờ tiếp theo?

**Đáp án:** Không nên chỉ dựa trên phần trăm. Xem sample size, confidence, baseline và evaluator health. Dùng release gate hoặc warning có minimum sample phù hợp.

### Bài 5 — Tool chạy thành công nhưng kết quả sai

Tool execution success rate là 100%, nhưng user feedback báo tra nhầm đơn. Cần thêm metric nào?

**Đáp án:** Tool argument correctness, authorization scope, business outcome correctness và tool selection accuracy. Execution success chỉ cho biết tool không ném lỗi.

### Bài 6 — Tokens tăng sau khi đổi prompt

Tokens/task tăng 35%, factuality tăng 1 điểm phần trăm. Có nên giữ prompt mới?

**Đáp án:** So cost/successful task, latency, quality theo từng criterion và business value. Chạy canary hoặc experiment có cùng dataset/judge/rubric trước khi quyết định.

### Bài 7 — Provider 429 tăng

Model 429 tăng nhưng ChatClient availability vẫn trong SLO nhờ fallback. Cần làm gì?

**Đáp án:** Tạo warning cho provider saturation/rate limits, theo dõi fallback rate và cost. Page khi user-facing SLO hoặc business risk bị ảnh hưởng; đồng thời kiểm tra capacity/quota và routing.

### Bài 8 — Quality alert không có sample

Dashboard báo factuality pass rate 0% nhưng chỉ có một evaluator error và không có case nào được chấm. Có phải regression không?

**Đáp án:** Không đủ dữ liệu để kết luận. Đây có thể là evaluator outage hoặc denominator bằng zero. Theo dõi evaluator errors/coverage riêng và chỉ tính pass rate trên cases được chấm hợp lệ.

## 29. Checklist trước khi đưa dashboard vào production

- [ ] Đã có SLI/SLO cho availability và latency ở tầng người dùng?
- [ ] Đã định nghĩa request nào là good/bad event?
- [ ] Có traffic, error rate, latency và saturation?
- [ ] Có ChatClient, ChatModel, tool và VectorStore observations?
- [ ] Có TTFT nếu ứng dụng streaming?
- [ ] Có token usage và cost trên mỗi successful task?
- [ ] Có relevance, factuality, groundedness và retrieval quality?
- [ ] Có tool selection, argument validity và business outcome?
- [ ] Có evaluator health, sample size và human calibration?
- [ ] Dashboard release có prompt/model/tool-set/rubric versions?
- [ ] Metric labels có cardinality hữu hạn?
- [ ] Prompt, completion, tool content và user identifiers được bảo vệ?
- [ ] Alert ưu tiên triệu chứng user-visible và error budget burn?
- [ ] Quality regression có release gate hoặc canary review?
- [ ] Mỗi alert có runbook và link tới dashboard/trace/case?
- [ ] Đã kiểm tra query với metric exposition thực tế của registry?

## 30. Tài liệu tham khảo

1. [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/): ChatClient, advisors, ChatModel, tools, VectorStore observations và Prometheus metrics.
2. [Spring AI 2.1.0 — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): Evaluator, RelevancyEvaluator, FactCheckingEvaluator và integration testing.
3. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registry, Actuator metrics/Prometheus endpoint, histograms và custom tags.
4. [Prometheus — Alerting](https://prometheus.io/docs/practices/alerting/): alert trên triệu chứng user-visible, hạn chế alert noise và liên kết tới dashboard.
5. [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): histogram, quantiles và aggregation qua nhiều instances.
6. [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): error budget, burn rate và multi-window alerting.
7. [OpenTelemetry — Signals](https://opentelemetry.io/docs/concepts/signals/): phân biệt metrics, traces, logs và context propagation.

*Các ngưỡng SLO, quality gate, PromQL và dashboard panels trong bài là mẫu thiết kế. Hãy hiệu chỉnh theo traffic, rủi ro nghiệp vụ, provider, dataset, judge model và release thực tế. Dashboard cần được kiểm tra bằng dữ liệu thật và runbook cần được diễn tập trước khi dùng làm cơ sở trực vận hành.*
