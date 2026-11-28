# Chất lượng khi vận hành: Lấy mẫu yêu cầu thật để đánh giá sau khi xử lý

## 1. Vì sao cần lấy mẫu traffic production?

Một bộ benchmark cố định giúp so sánh prompt, model và retriever trong môi trường kiểm soát. Nhưng người dùng thật đặt câu hỏi đa dạng hơn: cách diễn đạt khác nhau, ngữ cảnh hội thoại dài, tài liệu mới, dữ liệu thiếu, tool timeout và nhiều trường hợp hiếm mà dataset hiện tại chưa có.

Nếu chỉ đánh giá bằng benchmark, nhóm phát triển có thể bỏ lỡ những lỗi chỉ xuất hiện trong traffic thật. Nếu chạy evaluator trên mọi request production, chi phí model judge, thời gian xử lý và lượng dữ liệu cần bảo vệ có thể tăng nhanh. **Lấy mẫu yêu cầu thật** tạo ra một tập con có kiểm soát để kiểm tra chất lượng sau khi ứng dụng đã xử lý request.

Bài học thuộc chương **Chất lượng khi vận hành** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline.

Mục tiêu là xây dựng một quy trình lấy mẫu có thể giải thích: biết request nào đủ điều kiện, vì sao được chọn, xác suất được chọn là bao nhiêu, dữ liệu nào được giữ lại, evaluator nào đã chạy và kết quả được dùng ra sao.

Sau bài học, bạn có thể:

- Chọn đúng đơn vị lấy mẫu trong một ứng dụng có nhiều model calls và tool calls.
- Phân biệt evaluation sampling với distributed trace sampling.
- Thiết kế random, stratified, risk-based và reservoir sampling.
- Kết hợp mẫu ngẫu nhiên đại diện với mẫu tập trung vào lỗi hiếm.
- Lưu inclusion probability và policy version để diễn giải kết quả thống kê.
- Chụp context cần thiết tại thời điểm xử lý mà không lưu toàn bộ traffic vô thời hạn.
- Chạy evaluator bất đồng bộ sau response và kiểm soát queue, retry, concurrency, chi phí.
- Đánh giá relevance, factuality, retrieval, tool execution và chất lượng đầu ra trên traffic thật.
- Theo dõi coverage, sampling bias và chất lượng theo từng cohort.

## 2. Đơn vị lấy mẫu là interaction, không phải từng span

Một yêu cầu người dùng có thể tạo ra nhiều hoạt động bên trong:

~~~mermaid
flowchart TD
    USER["Một user request"] --> CHAT["ChatClient invocation"]
    CHAT --> RETRIEVAL["Retrieval / reranking"]
    CHAT --> MODEL1["Model operation #1"]
    MODEL1 --> TOOL["Tool execution"]
    TOOL --> MODEL2["Model operation #2"]
    MODEL2 --> ANSWER["Assistant response"]
    ANSWER --> EVAL["Post-response evaluation"]
~~~

Nếu lấy mẫu từng span độc lập, một evaluation case có thể chỉ giữ lại model call thứ hai mà thiếu câu hỏi, retrieval context hoặc tool result. Khi đó evaluator không thể đánh giá đầy đủ câu trả lời cuối.

Đơn vị mặc định nên là **interaction** hoặc **assistant turn** mà người dùng nhìn thấy. Tất cả model operations, advisor executions, retrieval spans và tool calls liên quan cần được nối về interaction đó.

| Đơn vị | Dùng khi nào | Rủi ro nếu dùng sai |
| --- | --- | --- |
| User request | Một API request tương ứng một tác vụ | Một request có thể chứa nhiều assistant turns |
| Interaction / assistant turn | Một kết quả AI cần đánh giá | Cần định nghĩa rõ khi tool loop hoặc retry tạo nhiều model calls |
| Conversation | Đánh giá chất lượng cả phiên hội thoại | Một conversation dài có thể chứa nhiều chủ đề và nhiều câu trả lời |
| Model operation | Phân tích một lần gọi model | Không đại diện cho trải nghiệm đầu-cuối của người dùng |
| Trace | Điều tra execution path và latency | Trace không nhất thiết chứa prompt, response hoặc evidence cần cho evaluator |
| Span | Phân tích một bước cụ thể | Lấy mẫu span riêng dễ làm mất quan hệ ngữ cảnh |

Tạo một interactionId ở tầng ứng dụng và gắn nó vào các event/span liên quan bằng trace context hoặc correlation metadata phù hợp. interactionId dùng để nối dữ liệu trong event store; không đưa nó thành metric label có cardinality cao.

## 3. Evaluation sampling khác trace sampling

Hai loại sampling giải quyết hai mục tiêu khác nhau:

| Khía cạnh | Evaluation sampling | Trace sampling |
| --- | --- | --- |
| Đối tượng | Interaction, assistant turn hoặc evaluation case | Distributed trace và các spans của trace |
| Mục tiêu | Chọn nội dung thật để đánh giá chất lượng | Giảm lượng telemetry traces cần lưu |
| Dữ liệu cần có | Input, response, RAG context/evidence và metadata cần thiết | Span attributes, events, timing và trace relationships |
| Kết quả | Evaluation job, scores, verdict và review case | Trace được export hoặc loại bỏ |
| Đơn vị quyết định | Thường là interaction | Trace ID |
| Hệ thống thực hiện | Application sampling policy / evaluation pipeline | SDK sampler hoặc collector tail sampler |

Spring AI cung cấp observations và metrics cho các thành phần như ChatClient, Advisor, ChatModel, EmbeddingModel và VectorStore. Những observations giúp đọc thời gian và execution path. Tuy nhiên, prompt/completion thường không được export mặc định vì dữ liệu có thể lớn và nhạy cảm. Vì vậy, **một trace được giữ lại không tự động có đủ nội dung để chạy evaluator**.

Ngược lại, một interaction được chọn để đánh giá có thể không có trace đầy đủ nếu trace sampling đã loại bỏ spans. Khi cần liên kết trace cho các mẫu evaluation, hãy phối hợp hai policy hoặc lưu một trace reference cùng metadata envelope. Không coi hai tỷ lệ sampling là một.

### 3.1. Head sampling và tail sampling

- **Head sampling** quyết định sớm khi trace bắt đầu, thường dựa trên xác suất hoặc thuộc tính sẵn có ở đầu request.
- **Tail sampling** chờ thêm spans để quyết định theo kết quả cuối như error, latency hoặc attributes được tạo ra trong quá trình xử lý.
- **Evaluation sampling** có thể quyết định trước hoặc sau khi có response, tùy chiến lược và dữ liệu cần đánh giá.

Tail sampler cần giữ state của trace trong lúc chờ quyết định. Với OpenTelemetry Collector tail sampling processor, các spans của cùng trace phải được route tới cùng collector instance để quyết định nhất quán. Cần cấu hình thời gian chờ, giới hạn số traces và bộ nhớ phù hợp; trace đến muộn sau quyết định có thể không ảnh hưởng quyết định ban đầu.

Không dùng tail sampling như một evaluator. Tail sampler chỉ chọn traces; nó không kiểm tra câu trả lời có liên quan hoặc có căn cứ hay không.

## 4. Thiết kế hai giai đoạn: chọn mẫu và giữ evidence

Lấy mẫu sau khi xử lý có một điểm cần giải quyết: evaluator cần input, response và context, nhưng nếu ứng dụng chỉ quyết định chọn mẫu sau khi response hoàn tất thì dữ liệu có thể đã bị bỏ đi.

Một thiết kế production nên tách **metadata envelope** khỏi **evidence payload**:

1. Khi request bắt đầu, tạo interactionId và metadata envelope nhỏ: tenant scope, task family, provider, requested model, prompt/retriever version, timestamp và trace reference.
2. Trong lúc xử lý, thu thập các outcome signals cần cho policy: HTTP status, tool failure, latency, timeout, token usage status và evaluator pre-check nếu có.
3. Chọn interaction theo baseline random policy hoặc các điều kiện sau xử lý.
4. Chỉ promote evidence payload của interaction được chọn sang evaluation store.
5. Xóa staging data không được chọn theo TTL đã định.
6. Chạy evaluator bất đồng bộ và ghi kết quả gắn với snapshot version.

~~~mermaid
flowchart TD
    REQ["Request starts"] --> ENV["Create interaction envelope"]
    ENV --> RUN["Run ChatClient / RAG / tools"]
    RUN --> OUTCOME["Capture outcome metadata"]
    OUTCOME --> POLICY{"Sampling policy"}
    POLICY -->|Selected| EVIDENCE["Promote protected evidence"]
    POLICY -->|Not selected| PURGE["Expire temporary evidence"]
    EVIDENCE --> QUEUE["Evaluation queue"]
    QUEUE --> JUDGE["Evaluator workers"]
    JUDGE --> RESULT["Versioned evaluation result"]
    RESULT --> DATASET["Review / dataset pipeline"]
~~~

### 4.1. Baseline random sample cần được quyết định sớm

Nếu cần đánh giá nội dung input/response nhưng không muốn giữ raw content cho mọi request, chọn một phần traffic ngay khi request bắt đầu. Với các request được chọn, hệ thống có thể tạo evidence snapshot được bảo vệ và chỉ đưa đi đánh giá sau khi response hoàn tất.

Đây vẫn là hậu kiểm: việc chọn mẫu xảy ra trước, còn evaluator chạy sau khi có kết quả. Lợi ích là không cần lưu raw prompt và response của mọi request.

### 4.2. Risk-based sample cần outcome signals

Một số trường hợp chỉ biết sau khi xử lý:

- HTTP/model/tool error.
- Timeout hoặc latency vượt ngưỡng.
- Stream bị cancel.
- Retrieval trả context rỗng.
- Tool loop vượt số vòng cho phép.
- Response bị cắt hoặc có safety/refusal marker.

Để chọn các trường hợp này, policy cần metadata outcome. Nếu muốn đánh giá nội dung, dùng một trong hai cách:

- Có candidate evidence store mã hóa với TTL ngắn, giới hạn dung lượng và quyền truy cập; chỉ promote payload khi policy chọn.
- Giữ reference tới evidence đã được ứng dụng lưu theo một chính sách hợp lệ, rồi chỉ cấp quyền truy cập cho evaluation worker khi được chọn.

Không âm thầm bật logging toàn bộ prompt/completion để phục vụ risk sampling. Việc giữ evidence phải có mục đích, phạm vi và retention rõ ràng.

## 5. Các chiến lược lấy mẫu

Không có một tỷ lệ phù hợp cho mọi ứng dụng. Chọn phương pháp theo mục tiêu: ước lượng chất lượng traffic chung, tìm lỗi hiếm, so sánh cohort hay điều tra sự cố.

### 5.1. Simple random sampling

Mỗi interaction đủ điều kiện có cùng xác suất được chọn là p.

Ví dụ, p = 0,02 nghĩa là chọn khoảng 2% traffic. Với 50.000 interactions, số mẫu kỳ vọng khoảng 1.000, nhưng số thực tế dao động ngẫu nhiên.

Ưu điểm:

- Dễ giải thích và dễ triển khai.
- Phù hợp ước lượng chất lượng chung nếu mẫu được chọn đúng cách.
- Không phụ thuộc evaluator pre-score hoặc người dùng gửi feedback.

Giới hạn:

- Lỗi hiếm có thể không xuất hiện trong mẫu.
- Một số task family ít traffic có thể có quá ít mẫu.
- Không đảm bảo đủ số lượng cho từng model hoặc language.

### 5.2. Stratified sampling

Chia traffic thành các strata trước khi lấy mẫu. Các chiều phân tầng có thể gồm:

- Task family: hỏi đáp, tóm tắt, phân loại, code assistant.
- Pipeline: direct chat, RAG, tool calling, multi-step agent.
- Provider hoặc model family.
- Language hoặc region.
- Traffic channel hoặc tenant tier.
- Outcome class: success, retry, timeout, tool failure.

Mỗi stratum có thể dùng tỷ lệ khác nhau. Ví dụ:

| Stratum | Tỷ lệ mẫu minh họa | Lý do |
| --- | ---: | --- |
| Direct chat success | 1% | Baseline đại diện |
| RAG success | 3% | Cần kiểm tra retrieval grounding |
| Tool calling | 5% | Nhiều bước và nhiều failure modes |
| Timeout/tool error | 100% trong quota giới hạn | Điều tra các trường hợp thất bại |
| Language ít traffic | 10% | Tránh cohort quá nhỏ |

Các tỷ lệ trên chỉ là ví dụ. Nếu tăng tỷ lệ ở một stratum, kết quả tổng hợp phải tính đến xác suất chọn khác nhau; nếu không, mẫu sẽ đại diện quá mức cho các nhóm được oversample.

### 5.3. Risk-based sampling

Chọn nhiều hơn các interaction có tín hiệu rủi ro:

- Model error hoặc provider error.
- Latency rất cao.
- Retrieval score thấp hoặc context rỗng.
- Tool execution thất bại.
- Safety filter kích hoạt.
- Token usage hoặc finish reason bất thường.
- Response ngắn bất thường hoặc bị truncation.
- User feedback negative đã được gửi.

Risk-based sampling hữu ích để phát hiện và chẩn đoán lỗi. Tuy nhiên, **không thể dùng riêng mẫu rủi ro để ước lượng tỷ lệ lỗi của toàn traffic** nếu xác suất được chọn phụ thuộc vào chính tín hiệu lỗi.

Giữ một baseline random sample bên cạnh risk sample. Baseline giúp ước lượng chất lượng chung; risk sample giúp tìm các tình huống cần điều tra.

### 5.4. Systematic sampling

Chọn mỗi request thứ k theo thứ tự arrival, ví dụ mỗi 100 request chọn một. Cách này dễ thực hiện và tạo phân bố đều theo thời gian, nhưng có thể bị bias nếu traffic có chu kỳ trùng với k: batch job, lịch campaign hoặc pattern theo giờ.

Nếu dùng systematic sampling, randomize điểm bắt đầu và kiểm tra phân bố mẫu theo thời gian, channel và task family.

### 5.5. Reservoir sampling

Khi chỉ có một luồng request và chưa biết tổng số interactions, reservoir sampling giữ một tập mẫu có kích thước cố định N. Mỗi interaction mới có cơ hội thay thế một phần tử đang giữ, sao cho sau khi xử lý M interactions, mọi interaction có xác suất N/M được giữ.

Cách này hữu ích khi chọn mẫu đại diện cho một cửa sổ hoặc batch đã hoàn tất. Với production online cần đánh giá ngay, thường dễ triển khai random selection theo interactionId hơn.

### 5.6. Adaptive sampling

Có thể thay đổi tỷ lệ theo thời gian hoặc tình trạng hệ thống, ví dụ tăng sampling khi:

- Vừa rollout model/prompt mới.
- Quality guardrail giảm.
- Error/latency tăng.
- Một task family vừa xuất hiện.
- Có incident đang được điều tra.

Khi tỷ lệ thay đổi, lưu policy version và xác suất chọn thực tế của từng interaction. Không so sánh trực tiếp hai giai đoạn có sampling policy khác nhau mà không điều chỉnh.

## 6. Kết hợp baseline và targeted sample

Một chính sách thực tế thường có ba phần:

1. **Baseline random:** một tỷ lệ nhỏ, ổn định trên traffic đủ điều kiện.
2. **Stratified sample:** tăng mẫu ở những nhóm có ý nghĩa sản phẩm hoặc ít traffic.
3. **Risk/incident sample:** chọn các interaction có error, latency hoặc quality signals bất thường.

~~~mermaid
flowchart TD
    I["Eligible interaction"] --> B{"Baseline random selected?"}
    I --> S{"Stratum quota selected?"}
    I --> R{"Risk / incident rule matched?"}
    B --> UNION["Combine decisions"]
    S --> UNION
    R --> UNION
    UNION -->|Yes| KEEP["Select for evaluation"]
    UNION -->|No| DROP["Do not promote evidence"]
~~~

Nếu một interaction khớp nhiều policy, cần xác định cách tính xác suất inclusion.

Có hai cách:

- **Policy precedence:** một rule quyết định chính, các rule khác chỉ gắn reason code. Ví dụ incident rule có ưu tiên cao nhất; nếu không khớp thì áp dụng stratified rule; cuối cùng là baseline random.
- **Independent random policies:** nếu các rule random độc lập với xác suất p1, p2, ..., xác suất được chọn ít nhất một lần là:

\[
P(\text{selected}) = 1 - \prod_i (1-p_i)
\]

Ví dụ hai policy độc lập có p1 = 1% và p2 = 5%, xác suất inclusion tổng là 5,95%, không phải 6%. Công thức chỉ đúng khi các phép chọn độc lập và cùng áp dụng cho interaction đó.

Không cộng các tỷ lệ policy một cách tùy tiện. Ghi inclusion probability cuối cùng, selection reasons và policy version vào sample record.

## 7. Chọn tỷ lệ và kích thước mẫu

Tỷ lệ phần trăm không tự nói lên mẫu có đủ lớn hay không. 1% của một triệu request là 10.000 mẫu; 1% của 500 request chỉ khoảng 5 mẫu.

Với mục tiêu ước lượng một tỷ lệ trong tổng thể lớn, công thức gần đúng cho cỡ mẫu ngẫu nhiên đơn giản là:

\[
n_0 = \frac{z^2 p(1-p)}{e^2}
\]

Trong đó:

- z là quantile theo confidence level; với 95% thường dùng z ≈ 1,96.
- p là tỷ lệ kỳ vọng; nếu chưa biết, p = 0,5 cho cỡ mẫu bảo thủ nhất.
- e là sai số tuyệt đối mong muốn.

Ví dụ 95% confidence, p = 0,5 và sai số ±5 điểm phần trăm:

\[
n_0 \approx \frac{1,96^2 \times 0,5 \times 0,5}{0,05^2}
\approx 384,16
\]

Có thể làm tròn lên khoảng 385 mẫu cho ước lượng đơn giản trong điều kiện giả định của công thức. Cỡ mẫu thực tế cần điều chỉnh theo population size, non-response, clustering, nhiều strata và mục tiêu so sánh.

### 7.1. Cỡ mẫu cho cohort

Nếu muốn so sánh RAG với direct chat, không chỉ tính tổng sample size. Mỗi cohort cần đủ mẫu để ước lượng riêng. Một mẫu 1.000 interactions nhưng chỉ có 12 tool calls không đủ để kết luận về chất lượng tool calling.

Theo dõi:

- Số interaction đủ điều kiện trong mỗi cohort.
- Số interaction được chọn.
- Số evidence payload thực sự sẵn sàng.
- Số evaluation job thành công.
- Số case bị reviewer loại hoặc đánh dấu không đủ dữ liệu.

### 7.2. Mẫu ít không đồng nghĩa tỷ lệ bằng 0

Nếu một stratum không có sample trong cửa sổ, dashboard cần hiển thị “không đủ dữ liệu”. Nếu không có defect trong 20 mẫu, điều đó không chứng minh defect rate bằng 0. Báo cáo tỷ lệ cùng sample count và confidence interval.

### 7.3. Điều chỉnh theo population size

Khi tổng số interactions hữu hạn và mẫu chiếm tỷ lệ lớn, có thể áp dụng finite population correction:

\[
n = \frac{n_0}{1 + \frac{n_0-1}{N}}
\]

Trong đó N là tổng số interactions đủ điều kiện trong population. Đây là công thức điều chỉnh cho sampling không hoàn lại trên population hữu hạn; không dùng máy móc cho dữ liệu traffic có phụ thuộc theo thời gian hoặc cohort.

## 8. Inclusion probability và trọng số thống kê

Khi mỗi interaction có xác suất chọn khác nhau, phải lưu xác suất inclusion của nó.

Ví dụ:

| Interaction | Stratum | Inclusion probability | Weight |
| --- | --- | ---: | ---: |
| A | Direct chat | 0,01 | 100 |
| B | RAG | 0,05 | 20 |
| C | Tool failure | 1,00 | 1 |
| D | Language ít traffic | 0,10 | 10 |

Weight cơ bản là:

\[
w_i = \frac{1}{\pi_i}
\]

Trong đó πi là xác suất inclusion của interaction i.

Nếu oversample tool failures, một lỗi tool trong sample không đại diện cho cùng tỷ trọng traffic như một direct chat sample. Khi ước lượng tỷ lệ hoặc mean trên toàn population, có thể dùng weighted ratio estimator:

\[
\hat{\mu} =
\frac{\sum_{i \in sample} w_i y_i}
{\sum_{i \in sample} w_i}
\]

Với y_i là outcome cần ước lượng, ví dụ evaluator pass = 1, fail = 0. Phải bảo đảm xác suất inclusion đã được tính đúng và mọi interaction trong population mục tiêu có xác suất được chọn khác 0.

Nếu chỉ báo cáo kết quả của từng stratum riêng, có thể trình bày tỷ lệ quan sát trong stratum cùng sample count; khi tổng hợp toàn traffic, cần dùng trọng số theo thiết kế mẫu và population shares.

## 9. Ghi lại sample decision

Một sample record nên giải thích được vì sao interaction được chọn:

~~~json
{
  "sampleId": "sample-01JXYZ",
  "interactionId": "interaction-7f4b",
  "assistantTurnId": "turn-2",
  "samplingPolicyVersion": "production-eval-v4",
  "samplingUnit": "ASSISTANT_TURN",
  "selected": true,
  "selectionReasons": [
    "BASELINE_RANDOM",
    "RAG_STRATUM"
  ],
  "stratum": "RAG_SUCCESS",
  "inclusionProbability": 0.0298,
  "samplingWeight": 33.56,
  "selectedAt": "2026-11-27T12:00:00Z",
  "evidenceStatus": "READY"
}
~~~

Các ID và số liệu chỉ là ví dụ. inclusionProbability và samplingWeight trong ví dụ cần được tính từ policy thật, không hardcode. Lưu thêm seed/key version hoặc deterministic bucket reference nếu selection dùng hash. Không lưu secret salt trực tiếp trong sample record.

Các trường nên có:

- Sample ID và interaction reference.
- Sampling unit.
- Policy version.
- Selected flag và selection reason.
- Stratum và cohort.
- Inclusion probability và sampling weight.
- Timestamp quyết định.
- Evidence reference và evidence status.
- Evaluator status sau khi chạy.

## 10. Lấy mẫu ổn định bằng hash của interactionId

Với baseline random, một cách thực hiện ổn định là hash một interactionId do server tạo cùng secret salt thành bucket từ 0 đến 9.999. Nếu tỷ lệ chọn là 2%, chọn bucket nhỏ hơn 200.

Lợi ích:

- Retry hoặc duplicate event của cùng interaction không làm thay đổi quyết định.
- Có thể tái hiện sample decision khi còn policy/key version.
- Không cần giữ random generator state giữa các application instances.
- Các worker có thể quyết định giống nhau nếu cùng thuật toán và key version.

Pseudocode:

~~~java
int bucket = stableHmacBucket(interactionId, secretKey, 10_000);
boolean selected = bucket < 200; // 2%

SampleDecision decision = new SampleDecision(
        interactionId,
        selected,
        0.02,
        "production-eval-v4",
        "BASELINE_RANDOM");
~~~

Đây là pseudocode; hàm HMAC cần dùng secret key được quản lý bởi secret manager. Không dùng raw user ID, email hoặc prompt làm sampling key. Không ghi secret key vào logs. Khi rotate key, lưu key version và tránh vô tình đổi sample decision của interaction đã xử lý.

Nếu dùng cùng bucket cho nhiều policy, hãy định nghĩa rõ cách kết hợp. Ví dụ một hash bucket có thể tạo sample lồng nhau: mọi interaction được chọn ở 1% cũng nằm trong nhóm 5%. Khi đó xác suất union không phải tổng xác suất độc lập; hãy tính theo rule thực tế.

## 11. Tạo interaction envelope và evidence snapshot

Một interaction envelope nhẹ có thể được ghi cho mọi request:

~~~json
{
  "interactionId": "interaction-7f4b",
  "assistantTurnId": "turn-2",
  "conversationRef": "conv-opaque",
  "provider": "openai",
  "modelFamily": "gpt-family",
  "promptVersion": "support-v12",
  "retrieverVersion": "kb-retriever-v5",
  "taskFamily": "RAG_QA",
  "startedAt": "2026-11-27T12:00:00Z",
  "traceReference": "trace-ref-opaque"
}
~~~

Envelope chứa metadata cần thiết để phân tầng và nối dữ liệu. Nó không nhất thiết chứa prompt, completion hoặc raw context.

Khi interaction được chọn, evidence snapshot có thể gồm:

| Thành phần | Nội dung |
| --- | --- |
| User input | Input đã redaction hoặc secure reference |
| Assistant output | Response đã redaction hoặc secure reference |
| Retrieval evidence | Document/chunk IDs, versions, rank, scores |
| Tool execution | Tool name/version, status, duration và sanitized result reference |
| Model context | Provider, requested/reported model, generation parameters |
| Pipeline context | Prompt, retriever, index, reranker, advisor và tool schema versions |
| Runtime | Latency, TTFT, usage status, token counts và error category |
| Trace | Trace reference, không phải raw trace payload |

### 11.1. Giữ snapshot đúng thời điểm

Không truy vấn lại vector store hiện tại để thay thế context cũ. Corpus hoặc index có thể đã được cập nhật sau khi interaction hoàn tất. Lưu document version, chunk ID và content hash để biết đúng evidence đã được dùng.

Tương tự, không lấy prompt template hiện tại rồi gắn vào interaction cũ. Lưu prompt version hoặc immutable configuration reference.

### 11.2. Evidence không phải log vô thời hạn

Nếu cần lưu raw content để evaluator đọc, lưu ở evidence store riêng có mã hóa, access control, audit và TTL. Sample store chỉ nên giữ reference và metadata. Khi evidence hết retention, sample record có thể chuyển sang trạng thái EXPIRED và không chạy lại được; không tái tạo dữ liệu bằng context hiện tại.

## 12. Chạy evaluator sau khi response hoàn tất

Evaluation job nên chạy bất đồng bộ. User request không cần chờ model judge hoặc fact-checking job kết thúc.

Một flow:

1. Ứng dụng hoàn tất response cho người dùng.
2. Interaction snapshot được đánh dấu COMPLETED.
3. Sampling policy xác nhận interaction được chọn.
4. Outbox event được publish vào queue.
5. Evaluation worker tải evidence theo quyền được cấp.
6. Worker chạy evaluator và lưu result.
7. Case cần xem xét được đưa vào review queue hoặc dataset pipeline.

Spring AI cung cấp interface Evaluator với EvaluationRequest chứa user text, context data và response content. RelevancyEvaluator kiểm tra câu trả lời có liên quan đến câu hỏi và context hay không; FactCheckingEvaluator đánh giá claim có được hỗ trợ bởi context hay không. Chọn evaluator phù hợp với loại interaction; không chạy fact checking nếu không có evidence đáng tin cậy.

### 12.1. Ví dụ gọi evaluator

~~~java
EvaluationRequest request = new EvaluationRequest(
        interaction.userText(),
        interaction.retrievedContents(),
        interaction.responseContent());

EvaluationResponse response = evaluator.evaluate(request);
~~~

Đây là ví dụ khái niệm; evaluator cụ thể và cách tạo request phụ thuộc phiên bản Spring AI. RelevancyEvaluator và FactCheckingEvaluator có thể dùng một model khác với model tạo câu trả lời. Lưu evaluator model, evaluator version, prompt/rubric version và timestamp để kết quả có thể giải thích.

### 12.2. Tách evaluator khỏi model generation

Evaluator là một model operation hoặc tác vụ đánh giá riêng. Nó có token usage, latency và failure rate riêng. Không cộng chi phí evaluator vào chi phí generation mà không phân loại role.

Nếu evaluator dùng cùng provider hoặc model với generation, tránh để dashboard gộp cả hai thành một metric “model latency” duy nhất. Gắn role hoặc operation type có cardinality thấp như GENERATION, EMBEDDING, JUDGE và FACT_CHECK.

### 12.3. Không xem LLM judge là ground truth

LLM judge có thể sai, thiên lệch theo văn phong hoặc ưu tiên câu trả lời dài. Dùng rubric rõ ràng, calibration trên tập human-reviewed và kiểm tra agreement giữa evaluator với reviewer.

Giữ các trường riêng:

- evaluator score/verdict.
- evaluator model và version.
- rubric version.
- human review verdict.
- evidence reference.
- disagreement status.

Nếu evaluator không đủ context, kết quả nên là INCONCLUSIVE hoặc INSUFFICIENT_EVIDENCE, không ép thành PASS/FAIL.

## 13. Queue, retry và chi phí evaluation

Post-response evaluation có thể tạo backlog khi traffic tăng hoặc provider judge chậm. Queue cần có:

- Bounded concurrency theo provider/model.
- Rate limit và token/cost budget.
- Timeout riêng cho evaluation.
- Retry có exponential backoff và jitter.
- Idempotency key theo sampleId + evaluatorVersion.
- Dead-letter queue cho job lỗi không thể retry.
- Queue age và oldest job age metrics.
- Circuit breaker khi evaluator provider bị lỗi.
- Chính sách ưu tiên cho incident sample và baseline sample.

Không retry vô hạn. Một evaluator job lỗi không nên làm request người dùng thất bại hoặc chặn response đã trả.

### 13.1. Ưu tiên job

Một chính sách ưu tiên có thể là:

1. Incident/security/critical error sample.
2. Regression candidate sau rollout.
3. Baseline random sample.
4. Routine backfill hoặc replay.

Ưu tiên chỉ ảnh hưởng thứ tự xử lý, không được làm thay đổi sample probability đã ghi. Nếu job bị bỏ vì vượt cost budget, ghi rõ SKIPPED_BUDGET thay vì xóa sample record.

### 13.2. Ước lượng chi phí

Chi phí evaluation gần đúng:

\[
C_{eval} =
N_{jobs} \times
(C_{judge\ input} + C_{judge\ output} + C_{retrieval})
\]

Công thức chỉ mang tính khái niệm; cần dùng bảng giá hoặc cost model tương ứng provider, cộng chi phí storage và vận hành nếu cần.

Theo dõi riêng:

- Số interaction được chọn.
- Số evaluation jobs đã chạy.
- Judge input/output tokens.
- Cost estimate theo evaluator model.
- Retry count và failed jobs.
- Evidence storage bytes và retention.

## 14. Tránh sampling bias

Một mẫu có thể sai lệch nếu selection policy chỉ chọn những trường hợp dễ phát hiện hoặc dễ lưu.

Các nguyên tắc:

- Luôn giữ baseline random sample ổn định.
- Không chỉ lấy các interaction có feedback negative.
- Không chỉ lấy trace có error; cần cả successful interactions.
- Không bỏ qua language hoặc task family có traffic thấp.
- Ghi inclusion probability cho mỗi sample.
- Theo dõi evidence availability; nếu một stratum thường thiếu evidence, kết quả đánh giá trên stratum đó sẽ bị lệch.
- Giữ non-selected count để biết sample coverage.
- Khi policy thay đổi, version hóa và phân tích từng giai đoạn riêng.

### 14.1. User feedback không phải random sample

Người dùng tự nguyện đánh giá thường có trải nghiệm rất tốt hoặc rất xấu. Đây là self-selection bias. Giữ feedback samples riêng với production random sample; có thể hợp nhất để điều tra, nhưng không gộp chúng như thể có cùng xác suất inclusion.

### 14.2. Không loại lỗi chỉ vì không có response

Nếu chỉ lấy mẫu các interaction thành công, hệ thống sẽ bỏ qua timeout, provider error, stream cancellation và tool failure. Các outcome này vẫn là những case production cần điều tra.

Với request không có response content, evaluator relevance/fact checking có thể không chạy được. Nhưng vẫn có thể tạo operational evaluation case về availability, error category và latency. Ghi evaluation type riêng.

## 15. Đo chất lượng theo cohort và phiên bản

Khi đã có sample, phân tích theo các chiều có ý nghĩa:

- Prompt version.
- Model/provider và model revision.
- Retriever/index/reranker version.
- Task family và language.
- Direct chat, RAG, tool calling.
- Successful, timeout, error, cancelled.
- Sampling policy version.
- Evaluator/rubric version.

Không gộp các cohort có distribution khác nhau rồi kết luận model mới tốt hơn. Ví dụ model A nhận phần lớn direct chat đơn giản, model B nhận nhiều RAG và tool tasks; điểm trung bình có thể phản ánh khác biệt task mix thay vì model quality.

Khi so sánh candidate versions:

1. Dùng cùng dataset replay để kiểm tra regression trong điều kiện kiểm soát.
2. Dùng production sample để xác nhận hành vi trên traffic thực.
3. Giữ cùng evaluator/rubric version hoặc hiệu chỉnh khi thay đổi.
4. So sánh theo cohort trước khi xem aggregate.
5. Báo sample count và uncertainty cùng score.
6. Theo dõi latency, token usage và cost song song với quality.

## 16. Metrics cho sampling và evaluation pipeline

Các metric sau là ví dụ do ứng dụng tự định nghĩa, không phải tên metric mặc định Spring AI:

| Metric | Ý nghĩa |
| --- | --- |
| ai_eval_sampling_candidates_total | Số interactions đủ điều kiện |
| ai_eval_sampling_decisions_total | Số quyết định theo policy và outcome |
| ai_eval_samples_selected_total | Số interactions được chọn |
| ai_eval_evidence_promoted_total | Số evidence snapshots được promote |
| ai_eval_evidence_expired_total | Số evidence hết TTL hoặc bị xóa |
| ai_eval_jobs_total | Số evaluation jobs theo status |
| ai_eval_job_duration_seconds | Thời gian xử lý evaluation |
| ai_eval_queue_oldest_age_seconds | Tuổi của job lâu nhất trong queue |
| ai_eval_tokens_total | Token usage của evaluator |
| ai_eval_cost_estimated_total | Chi phí evaluator ước lượng |
| ai_eval_outcomes_total | Kết quả PASS/FAIL/INCONCLUSIVE theo dimension |

Dùng labels có cardinality hữu hạn như provider, task_family, policy, sample_reason, evaluator_version và status. Không dùng interactionId, traceId, user ID, prompt, response hoặc document ID làm metric labels.

### 16.1. Tỷ lệ được chọn trên eligible interactions

~~~promql
sum(rate(ai_eval_sampling_decisions_total{decision="SELECTED"}[1h]))
/
sum(rate(ai_eval_sampling_decisions_total{
  decision=~"SELECTED|NOT_SELECTED"
}[1h]))
~~~

Đây là tỷ lệ sample trên các interactions đã đủ điều kiện, không phải tỷ lệ trên toàn bộ HTTP requests nếu nhiều HTTP requests không tạo interaction.

### 16.2. Evaluation queue backlog

~~~promql
max(ai_eval_queue_oldest_age_seconds)
~~~

Nếu queue age tăng liên tục, evaluator đang xử lý chậm hơn tốc độ job đến hoặc worker/provider bị giới hạn. Cần theo dõi cả queue depth, worker concurrency và failed jobs.

### 16.3. Tỷ lệ evaluation job thành công

~~~promql
sum(rate(ai_eval_jobs_total{status="SUCCEEDED"}[1h]))
/
sum(rate(ai_eval_jobs_total[1h]))
~~~

Không tính SKIPPED_BUDGET hoặc INCONCLUSIVE như evaluator failure nếu định nghĩa vận hành tách riêng các trạng thái đó.

### 16.4. Theo dõi sample theo stratum

~~~promql
sum by (task_family, sample_reason) (
  rate(ai_eval_samples_selected_total[1h])
)
~~~

Query này cho biết mẫu đến từ nhóm nào. So sánh với eligible traffic theo cùng dimensions để phát hiện stratum bị under-sampled hoặc policy đang chọn quá nhiều.

## 17. Dashboard và cảnh báo

Một dashboard nên có bốn nhóm:

| Nhóm | Nội dung |
| --- | --- |
| Sampling coverage | Eligible, selected, inclusion rate, sample count theo stratum |
| Evaluation pipeline | Queue depth, oldest age, job duration, retry, DLQ |
| Quality | Relevance, fact-check, tool correctness, INCONCLUSIVE rate |
| Cost and operations | Judge tokens/cost, generation latency, tool failures, evidence storage |

Cảnh báo khi:

- Sampling decision rate khác xa policy dự kiến.
- Một stratum quan trọng không có mẫu trong nhiều cửa sổ.
- Evidence promotion thất bại hoặc evidence hết TTL trước khi worker đọc.
- Queue age vượt SLA.
- Evaluator error rate tăng hoặc provider rate limit.
- Judge token usage/cost vượt budget.
- Quality score giảm sau model/prompt/retriever rollout.
- Tỷ lệ INCONCLUSIVE tăng vì context hoặc evidence thiếu.

Không cảnh báo chỉ dựa trên một sample nhỏ. Dùng minimum sample count, cửa sổ thời gian và baseline trước khi tạo incident.

## 18. Bảo vệ dữ liệu và quyền truy cập

Production sampling không phải lý do để sao chép toàn bộ traffic vào kho phân tích.

- Chỉ thu thập payload cần cho evaluator và mục đích đã xác định.
- Redact PII, secrets, credentials và dữ liệu tenant khác trước khi promote.
- Mã hóa evidence store và truyền dữ liệu qua kênh bảo mật.
- Phân quyền riêng cho evaluator workers và reviewer UI.
- Audit việc đọc, tải xuống và export evidence.
- Đặt TTL cho staging và retention cho sampled evidence.
- Tách raw content khỏi metrics và trace attributes.
- Không bật prompt/completion logging toàn cục chỉ để tạo evaluation dataset.
- Không đưa raw prompt, response, document text hoặc tool arguments vào baggage hay metric labels.
- Xóa hoặc ẩn danh evidence theo chính sách dữ liệu; giữ metadata aggregate chỉ khi còn mục đích hợp lệ.

Spring AI không export prompt/completion mặc định vì chúng có thể lớn và nhạy cảm. Tool arguments/results cũng không export mặc định trong observations. Hãy giữ các mặc định bảo vệ này và dùng evidence pipeline có kiểm soát khi cần đánh giá nội dung.

## 19. Quy trình triển khai end-to-end

1. Xác định mục tiêu: ước lượng chất lượng chung, tìm lỗi hiếm, so sánh cohort hay điều tra incident.
2. Chọn sampling unit là interaction hoặc assistant turn.
3. Tạo interactionId và metadata envelope ở đầu request.
4. Xác định baseline random rate và các strata cần theo dõi.
5. Định nghĩa risk rules và quota cho error/latency/tool failures.
6. Tính inclusion probability cho từng policy combination.
7. Lưu sampling policy version, selection reason và weight.
8. Chọn thời điểm giữ evidence: preselect, secure staging TTL hoặc reference tới evidence store.
9. Sau khi response hoàn tất, promote evidence của sample đã chọn.
10. Publish evaluation job qua transactional outbox hoặc cơ chế reliable event.
11. Chạy Evaluator/RelevancyEvaluator/FactCheckingEvaluator bất đồng bộ.
12. Lưu evaluator/rubric version, model, scores, verdict và usage.
13. Đưa trường hợp lỗi hoặc không chắc chắn vào human review.
14. Tạo evaluation cases có provenance từ defects đã xác nhận.
15. Theo dõi sample coverage, queue, cost và quality theo cohort.
16. Version hóa policy và so sánh kết quả trước/sau khi thay đổi.

## 20. Checklist kiểm thử production

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Baseline random với cùng interactionId được retry | Sample decision không đổi theo cùng policy/key version |
| Interaction có nhiều model calls | Chỉ tạo một sample record theo sampling unit đã chọn |
| RAG interaction được chọn | Snapshot giữ document/chunk version và retrieval scores |
| Tool loop có nhiều tool calls | Toàn bộ execution summary liên quan cùng interaction được nối |
| HTTP/model error | Risk sample được chọn theo policy/quota |
| Interaction không có response | Có operational case; không giả vờ chạy relevance evaluator |
| Hai policy cùng chọn một interaction | Inclusion probability được tính đúng, không cộng tỷ lệ tùy tiện |
| Stratum ít traffic | Dashboard thể hiện sample count và thiếu dữ liệu |
| Evidence payload bị thiếu | Job chuyển INCONCLUSIVE/INSUFFICIENT_EVIDENCE |
| Worker nhận duplicate event | Idempotency không chạy evaluator hai lần ngoài chủ đích |
| Evaluator provider timeout | Retry có giới hạn, DLQ và không ảnh hưởng user response |
| Queue vượt budget | Job có status SKIPPED_BUDGET và sample record vẫn còn |
| Trace sampling loại trace | Evaluation evidence vẫn có thể được đánh giá |
| Trace tail sampling giữ error trace | Không nhầm trace retention với evaluation sample selection |
| Sampling policy thay đổi | Policy version và inclusion probability mới được lưu |
| Evidence hết TTL | Job báo EXPIRED, không lấy context hiện tại thay thế |
| Privacy review | PII/secrets được redaction và access được audit |

## 21. Bài tập thực hành

### Bài 1. Baseline random sample

Tạo policy chọn 1% assistant turns bằng hash ổn định của interactionId. Ghi policy version, inclusion probability và sample reason. Gửi duplicate event để xác minh cùng interaction không bị chọn hai lần.

### Bài 2. Stratified RAG và tool calling

Chia traffic thành direct chat, RAG và tool calling. Dùng tỷ lệ khác nhau cho từng stratum. Tính inclusion probability và weight; so sánh raw mean với weighted mean.

### Bài 3. Risk-based sample

Chọn interaction có timeout, tool failure hoặc latency vượt ngưỡng. Đảm bảo baseline random sample vẫn tồn tại để ước lượng chất lượng chung. Kiểm tra quota khi error spike xảy ra.

### Bài 4. Hậu kiểm bằng RelevancyEvaluator

Sau khi response hoàn tất, đưa user input, response và retrieved context vào evaluator worker. Lưu evaluator model/version và verdict. So sánh với một tập human-reviewed cases.

### Bài 5. Tail sampling cho traces

Cấu hình OpenTelemetry Collector tail sampling để giữ trace có error hoặc latency cao. Route spans theo trace ID về cùng collector. Kiểm tra decision wait, memory limit và late spans; so sánh trace sample với evaluation sample.

### Bài 6. Kiểm tra sampling bias

Oversample một task family ít traffic. Tính tỷ lệ raw và weighted. Giải thích vì sao risk sample không đại diện cho population nếu không có inclusion probability.

### Bài 7. Dashboard production

Tạo dashboard gồm eligible/selected counts, sample rate theo stratum, evidence availability, queue age, evaluator success, relevance/fact-check scores, judge cost và latency. Thử trường hợp không có sample để xác minh dashboard hiển thị “không đủ dữ liệu”.

## 22. Tổng kết

Lấy mẫu yêu cầu thật giúp kiểm tra chất lượng AI trong điều kiện người dùng và dữ liệu production, nhưng cần thiết kế như một quy trình có thể giải thích và kiểm toán:

- Chọn interaction hoặc assistant turn làm sampling unit để giữ đầy đủ ngữ cảnh của một kết quả.
- Phân biệt evaluation sampling với head/tail trace sampling; trace được giữ không đồng nghĩa có evidence cho evaluator.
- Kết hợp baseline random với stratified và risk-based sampling.
- Lưu inclusion probability, policy version, reason và weight để diễn giải thống kê.
- Tạo metadata envelope cho traffic; chỉ giữ/promote evidence payload theo policy, quyền truy cập và TTL.
- Chạy evaluator bất đồng bộ sau response, có idempotency, retry limit, queue budget và DLQ.
- Giữ user feedback, evaluator verdict và human review thành các tín hiệu riêng.
- Báo sample count, coverage và uncertainty; không xem mẫu rủi ro là đại diện cho toàn traffic.
- Nối kết quả với prompt/model/retriever versions, RAG evidence, tool execution, latency và cost.

Khi production sampling được thiết kế đúng, các request thật trở thành nguồn evaluation cases có provenance. Nhóm phát triển có thể phát hiện lỗi chưa xuất hiện trong benchmark, xác định cohort bị ảnh hưởng và kiểm tra candidate versions trước khi rollout rộng hơn.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): Evaluator, EvaluationRequest, RelevancyEvaluator và FactCheckingEvaluator.
- [Spring AI 2.1.0 Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): ChatClient, Advisor, ChatModel, EmbeddingModel, VectorStore observations, metrics, traces và mặc định không export prompt/completion.
- [OpenTelemetry Collector Contrib — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor): policy theo trace, decision wait, state/memory và yêu cầu gom spans cùng trace về một collector.
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/): khái niệm head sampling và tail sampling.
- [OpenTelemetry — Trace Context](https://www.w3.org/TR/trace-context/): truyền trace context giữa các service.
