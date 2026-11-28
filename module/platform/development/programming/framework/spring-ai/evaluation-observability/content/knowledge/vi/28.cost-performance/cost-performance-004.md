# Đo chất lượng trên mỗi mức chi phí và độ trễ

## 1. Đừng chọn model chỉ bằng điểm chất lượng hoặc giá thấp

Một ứng dụng Spring AI có thể tạo câu trả lời rất tốt nhưng tốn nhiều token, gọi tool nhiều lần và phản hồi chậm. Một cấu hình khác có thể rẻ, nhanh nhưng bỏ sót evidence hoặc trả lời sai ở các case quan trọng. Chỉ nhìn quality score, average cost hay latency riêng lẻ sẽ không cho biết cấu hình nào phù hợp để vận hành.

Mục tiêu của bài này là đánh giá **chất lượng đạt được trên mỗi mức chi phí và độ trễ**. Nhóm cần biết:

- Cấu hình có vượt qua các yêu cầu chất lượng bắt buộc không?
- Để hoàn thành một task thành công, hệ thống tiêu tốn bao nhiêu?
- Người dùng phải chờ bao lâu, đặc biệt ở p95/p99?
- Khi tăng concurrency, chất lượng, cost và latency thay đổi ra sao?
- Có cấu hình nào vừa rẻ hơn, nhanh hơn mà vẫn đạt chất lượng bằng hoặc cao hơn không?
- Nếu phải đánh đổi, cấu hình nào đáp ứng SLO và budget với rủi ro chấp nhận được?

Trong module SPRING_AI_EVALUATION_OBSERVABILITY, phép đo này nối evaluation dataset, relevance, fact checking, RAG/tool correctness với usage, cost ledger và telemetry. Mỗi candidate phải được đánh giá trong cùng điều kiện để quyết định thay prompt, model, retriever, reranker hoặc tool policy có bằng chứng.

**Không có một tỷ lệ quality/cost duy nhất phù hợp cho mọi hệ thống.** Hãy xác định quality gates và SLO trước; sau đó so sánh cost và latency của các candidate vượt qua các ngưỡng đó.

### Kết quả học tập

Sau bài này, người học có thể:

1. Định nghĩa quality, cost và latency ở cùng đơn vị task.
2. Tính cost per successful task và các chỉ số cost-quality.
3. Đo end-to-end latency, TTFT, per-operation latency và tail latency.
4. Thiết lập quality gates, latency SLO và cost budget.
5. Dùng Pareto frontier để nhận diện candidate không bị candidate khác vượt trội.
6. Thiết kế benchmark công bằng, paired comparison và phân tích độ bất định.
7. Đọc kết quả theo task type, tenant, model, prompt và pipeline version.
8. Chọn candidate theo ràng buộc chất lượng, chi phí, độ trễ và rủi ro.

## 2. Ba trục phải đo cùng nhau

Ba nhóm số liệu có quan hệ nhưng không thay thế nhau:

| Trục | Câu hỏi | Ví dụ |
|---|---|---|
| Quality | Hệ thống có làm đúng việc không? | Relevance, factual correctness, groundedness, tool success |
| Cost | Mỗi kết quả tiêu tốn bao nhiêu tài nguyên/tiền? | USD/request, USD/successful task, tokens/task |
| Latency | Người dùng phải chờ bao lâu? | End-to-end p95, TTFT, tool latency |

~~~mermaid
flowchart TD
    A["Evaluation dataset + rubric"] --> Q["Quality metrics and hard gates"]
    B["Usage events + price catalog"] --> C["Cost per task / successful task"]
    D["Traces + request timestamps"] --> L["Latency SLO and percentiles"]
    Q --> E{"Candidate passes mandatory gates?"}
    C --> E
    L --> E
    E -->|No| R["Reject or investigate"]
    E -->|Yes| P["Compare Pareto frontier"]
    P --> S["Choose candidate under product constraints"]
    S --> V["Canary / production validation"]
~~~

Quality score cao không bù được hard-gate violation. Cost thấp không bù được p95 vượt SLO. Latency nhanh không bù được câu trả lời sai. Quyết định cần giữ các điều kiện bắt buộc riêng trước khi tối ưu phần còn lại.

## 3. Chọn đơn vị đo thống nhất

Trước khi tính bất kỳ tỷ lệ nào, xác định một đơn vị công việc có ý nghĩa nghiệp vụ:

| Đơn vị | Ý nghĩa | Dùng khi |
|---|---|---|
| Request | Một request API | Theo dõi traffic và trải nghiệm endpoint |
| Task | Một mục tiêu nghiệp vụ hoàn chỉnh | Tính cost/quality theo kết quả |
| Attempt | Một lần thử thực hiện task | Phân tích retry và lỗi |
| Successful task | Task đáp ứng tiêu chí thành công đã định nghĩa | Unit economics |
| Evaluation case | Một case trong dataset | So sánh candidate trên benchmark |
| Evaluation run | Một lượt chạy dataset | Tính ngân sách và regression |
| Conversation/session | Một chuỗi nhiều request liên quan | Đo trải nghiệm hội thoại dài |

Một task có thể tạo nhiều request hoặc nhiều model calls. Ví dụ, người dùng hỏi về đơn hàng; ứng dụng gọi ChatModel để chọn tool, gọi API đơn hàng, sau đó gọi ChatModel lần nữa để diễn giải. Nếu lấy mỗi model call làm mẫu số thì cost per task sẽ bị đánh giá thấp.

### Định nghĩa success trước khi đo

Một task chỉ được tính là successful khi đáp ứng điều kiện đã công bố, chẳng hạn:

- Câu trả lời đáp ứng intent và rubric tối thiểu.
- Claims quan trọng có evidence và factual correctness đạt ngưỡng.
- RAG lấy đúng tài liệu cần thiết nếu task yêu cầu RAG.
- Tool được gọi đúng, arguments hợp lệ và side effect được xác nhận.
- Không vi phạm policy hoặc hard gate.
- Kết quả được trả trong deadline/SLO nếu deadline là một phần của nghiệp vụ.

Không định nghĩa success đơn giản là HTTP 200 hoặc model trả về chuỗi không rỗng. Request có thể thành công ở transport layer nhưng thất bại về nghiệp vụ.

## 4. Xây quality score có hard gates

Chất lượng ứng dụng AI có nhiều chiều. Một score tổng hợp giúp theo dõi xu hướng, nhưng không nên che khuất từng tiêu chí.

| Dimension | Ví dụ phép đo | Điều kiện cần chú ý |
|---|---|---|
| Relevance | Answer relevance, intent match | Có trả lời đúng câu hỏi không? |
| Factual correctness | Claim accuracy, fact-check pass rate | Claim có đúng với nguồn tin cậy không? |
| Groundedness | Supported claim ratio | Câu trả lời có được evidence hỗ trợ không? |
| Retrieval | Recall@k, context precision, context relevance | Evidence cần thiết có được truy xuất không? |
| Tool correctness | Tool selection, argument validity, execution success | Chọn và gọi đúng tool không? |
| Completeness | Required information coverage | Có thiếu trường/thông tin bắt buộc không? |
| Safety/policy | Violation rate, correct refusal | Có vi phạm policy hoặc từ chối sai không? |
| Format/schema | JSON/schema validation | Output có đúng hợp đồng không? |

### Tách hard gates khỏi score mềm

Ví dụ một task tra cứu số dư:

- Hard gate: không được tiết lộ dữ liệu tenant khác.
- Hard gate: số dư phải lấy từ tool/API được phép.
- Hard gate: tool arguments phải qua validation và authorization.
- Soft score: câu trả lời dễ hiểu, ngắn gọn, đúng ngữ cảnh.

Một candidate đạt style 99/100 nhưng vi phạm authorization vẫn phải fail. Không lấy trung bình để biến lỗi nghiêm trọng thành điểm tổng chấp nhận được.

### Composite score chỉ dùng sau khi xác định gate

Nếu rubric cho phép tổng hợp các chiều mềm, có thể dùng weighted score:

\[
Q = \sum_{j=1}^{m} w_j q_j,\qquad
\sum_{j=1}^{m} w_j = 1
\]

Trong đó q_j là điểm đã chuẩn hóa về cùng thang, w_j là trọng số được xác định trước. Ghi lại rubric version và trọng số. Không thay trọng số sau khi xem kết quả candidate để làm đẹp thứ hạng.

Báo cáo luôn giữ score từng dimension, hard-gate pass rate và sample size bên cạnh composite score.

## 5. Định nghĩa cost theo cùng đơn vị task

Cost nên bao gồm các hoạt động thực sự cần cho task:

- Chat generation, gồm mọi model calls và retries.
- Query embedding, retrieval, reranking.
- Tool/API execution.
- Chi phí evaluator nếu phép đo tính cả evaluation pipeline.
- Shared infrastructure allocation nếu báo cáo unit economics đầy đủ.

Phải công bố scope của metric:

| Metric | Thành phần |
|---|---|
| Candidate execution cost | Model, embedding, retrieval, tools của candidate |
| Evaluation cost | Judge, fact-check, evaluator embeddings/compute |
| Experiment cost | Candidate + evaluation + experiment overhead |
| Fully allocated cost | Candidate + phần shared infrastructure/observability được phân bổ |

Khi so sánh hai candidate, không cộng judge cost vào candidate A nhưng bỏ khỏi candidate B. Có thể báo riêng candidate execution cost và total experiment cost.

### Cost per attempt và cost per successful task

Gọi:

- C_total là tổng cost của tất cả attempts trong cohort.
- N_attempts là số attempts.
- N_success là số task thành công.

Khi đó:

\[
C_{\mathrm{per\ attempt}} =
\frac{C_{\mathrm{total}}}{N_{\mathrm{attempts}}}
\]

\[
C_{\mathrm{per\ successful\ task}} =
\frac{C_{\mathrm{total}}}{N_{\mathrm{success}}}
\]

Cost per successful task bao gồm chi phí của attempts thất bại, retry và task không hoàn tất trong cohort. Nếu N_success = 0, metric không xác định; không gán 0.

Ví dụ: 100 attempts tốn tổng 12 USD, 80 task thành công:

\[
C_{\mathrm{per\ attempt}} = 12/100 = 0.12\ \mathrm{USD}
\]

\[
C_{\mathrm{per\ successful\ task}} = 12/80 = 0.15\ \mathrm{USD}
\]

Nếu chỉ báo 0,12 USD/request, người đọc có thể bỏ qua 20% task thất bại.

## 6. Đo latency đúng với trải nghiệm người dùng

Latency có nhiều điểm bắt đầu/kết thúc. Chọn đúng mốc theo kiểu API:

| Chỉ số | Định nghĩa | Ý nghĩa |
|---|---|---|
| End-to-end latency | Từ lúc nhận request đến lúc trả kết quả hoàn chỉnh | Thời gian task hoàn tất |
| Time to first token (TTFT) | Từ lúc bắt đầu request đến token đầu tiên | Độ phản hồi của streaming |
| Inter-token latency | Khoảng cách giữa các token được stream | Độ mượt khi nhận nội dung |
| Model call latency | Một lần gọi ChatModel | Hiệu năng provider/model |
| Retrieval latency | Embedding + vector search/rerank theo cách đo đã định nghĩa | Độ trễ RAG |
| Tool latency | Thời gian tool thực thi | Độ trễ hệ thống phụ thuộc |
| Queue wait | Thời gian chờ worker/semaphore/rate limit | Tắc nghẽn capacity |

Với non-streaming API, end-to-end thường kết thúc khi response hoàn chỉnh được gửi. Với streaming, phải đo riêng TTFT, inter-token latency và total completion time. Không so TTFT của candidate A với total completion time của candidate B.

### Phân biệt wall-clock và tổng thời gian span

Các operation có thể chạy song song hoặc span lồng nhau. Tổng duration của mọi span có thể lớn hơn wall-clock latency. End-to-end latency phải đo trực tiếp tại request boundary; trace waterfall dùng để giải thích thành phần và quan hệ phụ thuộc.

## 7. Dùng percentile, không chỉ average

Average latency có thể che giấu một nhóm request rất chậm. Theo dõi:

- p50: trải nghiệm điển hình.
- p90: phần lớn request đã hoàn thành.
- p95: tail latency thường dùng cho SLO.
- p99: tail nghiêm trọng, đặc biệt khi có tool/API chậm hoặc queue.
- max: hữu ích khi điều tra, nhưng rất nhạy với outlier.

Ví dụ:

| Candidate | p50 | p95 | p99 |
|---|---:|---:|---:|
| A | 0,9 s | 2,2 s | 5,8 s |
| B | 1,0 s | 1,5 s | 2,4 s |

Candidate A nhanh hơn ở median nhưng có tail tệ hơn. Nếu SLO là p95 dưới 2 giây, A không đạt dù p50 thấp hơn.

### Percentile phải có sample size và window

Ghi số request, khoảng thời gian, workload mix và cách tính percentile. p99 từ 30 samples không ổn định. Với benchmark nhỏ, dùng repeated runs và confidence interval; với production, dùng rolling window đủ traffic và tách theo operation/task type.

## 8. Chuẩn hóa chất lượng, cost và latency trước khi so

Một benchmark công bằng cần giữ các điều kiện:

- Cùng dataset version, rubric version và expected outcomes.
- Cùng task mix và tỷ lệ case khó/dễ.
- Cùng concurrency, request arrival pattern và deadline.
- Cùng region/network path khi so model/provider.
- Cùng cache policy hoặc báo riêng warm/cold cache.
- Cùng cách tính retries, failures và timeout.
- Cùng cost scope, currency và pricing version.
- Cùng sampling/evaluator version.

Nếu candidate B được chạy với cache warm và concurrency thấp, còn A chạy cold cache ở tải cao, không thể quy toàn bộ chênh lệch latency cho model.

### Cohort và stratification

Không chỉ báo một average cho toàn bộ dataset. Chia theo task type:

| Cohort | Ví dụ |
|---|---|
| Simple answer | Câu hỏi ngắn, không RAG/tool |
| RAG lookup | Truy xuất evidence từ VectorStore |
| Tool workflow | Gọi một hoặc nhiều tools |
| Long context | Nhiều chunks/lịch sử dài |
| High-risk | Fact checking, policy hoặc authorization gate |
| Failure/recovery | Timeout, retry, fallback, thiếu evidence |

Candidate có thể tốt trên simple answer nhưng yếu ở tool workflow. Phân tầng giúp tránh Simpson's paradox khi tỷ lệ cohort khác nhau giữa các lần chạy.

## 9. Cost-quality metrics có thể dùng

Không có một chỉ số duy nhất phù hợp mọi tình huống. Một bộ chỉ số gợi ý:

| Metric | Công thức/ý nghĩa |
|---|---|
| Quality pass rate | Successful cases / eligible cases |
| Cost per attempt | Total candidate cost / attempts |
| Cost per successful task | Total candidate cost / successful tasks |
| Cost per quality-pass case | Candidate cost / cases vượt quality gates |
| Cost per 1,000 successful tasks | Cost per successful task × 1.000 |
| Quality points per USD | Điểm chất lượng theo định nghĩa / cost; chỉ dùng để khám phá |
| Latency per successful task | Latency của các task thành công, kèm failure latency riêng |
| Cost per quality point gained | Incremental cost / incremental quality gain so với baseline |

### Cẩn thận với tỷ lệ quality/cost

Lấy quality score chia cho cost có thể tạo thứ hạng sai:

- Candidate có quality thấp vẫn có thể có ratio cao vì cost rất nhỏ.
- Composite score có thể che hard-gate failures.
- Score 0–1 và 0–100 tạo ratio khác nhau nếu không chuẩn hóa.
- Cost gần 0 làm ratio mất ổn định.

Do đó, dùng ratio để khám phá sau khi candidate đã qua quality gates. Quyết định chính nên dựa trên cost per successful task, latency SLO và Pareto frontier.

### Incremental cost per quality gain

Khi candidate B cải thiện chất lượng so với baseline A:

\[
\mathrm{Incremental\ cost/quality\ point} =
\frac{C_B-C_A}{Q_B-Q_A}
\]

Chỉ số này có ý nghĩa khi Q_A và Q_B cùng thang, cùng dataset/rubric và Q_B > Q_A. Nếu quality không tăng, metric không biểu diễn “giá của một điểm cải thiện”. Nếu quality gain rất nhỏ, báo confidence interval và không phóng đại ý nghĩa.
## 10. Pareto frontier: nhận diện candidate không bị vượt trội

Một candidate bị candidate khác **dominate** nếu candidate kia:

- Có quality bằng hoặc cao hơn.
- Có cost bằng hoặc thấp hơn.
- Có latency bằng hoặc thấp hơn.
- Và tốt hơn nghiêm ngặt ở ít nhất một trục.

Candidate không bị candidate nào dominate nằm trên Pareto frontier. Các candidate này đại diện cho những lựa chọn đánh đổi khác nhau.

~~~mermaid
flowchart TD
    A["Collect candidate results"] --> B["Apply mandatory quality gates"]
    B --> C["Remove candidates that fail gates"]
    C --> D["Compare cost and latency at comparable quality"]
    D --> E["Remove dominated candidates"]
    E --> F["Pareto frontier"]
    F --> G["Select by product SLO, budget and risk"]
~~~

Trong không gian cost-latency, điểm càng gần góc dưới bên trái càng tốt, nhưng quality phải đạt ngưỡng. Nếu vẽ ba trục quality, cost và latency, mục tiêu là quality cao, cost thấp và latency thấp.

### Quy tắc so sánh

| Trục | Hướng tốt hơn |
|---|---|
| Quality pass rate / factual correctness | Cao hơn |
| Cost per successful task | Thấp hơn |
| End-to-end p95 / TTFT | Thấp hơn |
| Retry/error rate | Thấp hơn |
| Tool correctness / hard-gate pass | Cao hơn, bắt buộc đạt ngưỡng |

Không dùng Pareto frontier để hợp thức hóa candidate vi phạm hard gate. Loại candidate không đạt điều kiện bắt buộc trước khi tìm frontier.

## 11. Ví dụ chọn candidate bằng quality gates và Pareto frontier

Giả sử nhóm thử bốn candidate trên cùng dataset, rubric và workload. Các số sau hoàn toàn giả định:

| Candidate | Quality pass | Factual correctness | Tool correctness | Cost/attempt | Cost/success | p95 latency | Hard gates |
|---|---:|---:|---:|---:|---:|---:|---|
| A | 96,0% | 98,0% | 99,5% | 0,12 USD | 0,125 USD | 1,8 s | Pass |
| B | 92,0% | 94,0% | 97,0% | 0,07 USD | 0,076 USD | 1,2 s | Fail |
| C | 97,0% | 99,0% | 99,8% | 0,10 USD | 0,103 USD | 1,6 s | Pass |
| D | 96,5% | 98,5% | 100% | 0,11 USD | 0,114 USD | 1,3 s | Pass |

Giả sử hard gates yêu cầu:

- Quality pass rate ít nhất 95%.
- Factual correctness ít nhất 98%.
- Tool correctness ít nhất 99,5%.
- Không có critical policy/authorization violation.
- End-to-end p95 không quá 2 giây.

Candidate B bị loại vì quality và factual correctness dưới ngưỡng, dù cost và latency thấp nhất. Candidate C và D đạt các ngưỡng. Candidate A bị C dominate vì C có quality cao hơn, cost thấp hơn và p95 thấp hơn.

C và D đều còn trên Pareto frontier:

- C có quality cao hơn và cost thấp hơn.
- D có p95 latency thấp hơn và tool correctness cao hơn.

Nếu product ưu tiên chất lượng và chi phí trong giới hạn p95 2 giây, chọn C. Nếu một workflow cần phản hồi nhanh hơn và tool correctness là ưu tiên cao, D có thể phù hợp hơn. Quyết định phụ thuộc SLO và risk policy đã định nghĩa trước.

### Kiểm tra phép tính cost per successful task

Với candidate C, nếu cost trung bình là 0,10 USD cho mỗi attempt và 97% attempts thành công:

\[
C_{\mathrm{success,C}} =
\frac{0.10}{0.97}
\approx 0.10309\ \mathrm{USD}
\]

Với candidate D:

\[
C_{\mathrm{success,D}} =
\frac{0.11}{0.965}
\approx 0.11399\ \mathrm{USD}
\]

Candidate C rẻ hơn trên mỗi task thành công; candidate D nhanh hơn ở p95. Bảng trên không thay thế confidence interval và phân tích theo cohort.

## 12. Thiết lập quality gate, latency SLO và cost budget

Một policy vận hành nên xác định:

| Loại ràng buộc | Ví dụ |
|---|---|
| Quality gate | Factual correctness >= 98% |
| Tool gate | Tool arguments valid = 100% với operation nhạy cảm |
| Safety gate | Critical policy violation = 0 trong test suite |
| Latency SLO | End-to-end p95 <= 2 giây |
| Streaming SLO | TTFT p95 <= 700 ms |
| Cost budget | Cost per successful task <= 0,15 USD |
| Reliability | Timeout/error rate <= ngưỡng đã định |

Các ngưỡng trên chỉ là ví dụ. Chọn ngưỡng từ nhu cầu người dùng, mức rủi ro, hợp đồng và baseline production.

### Phân biệt SLO với budget

- **SLO** mô tả mục tiêu trải nghiệm/chất lượng trong một cửa sổ đo.
- **Budget** giới hạn khoản chi được phép cho request, tenant, run hoặc kỳ.
- **Hard gate** là điều kiện không được vi phạm, bất kể score trung bình.

Một candidate có thể đạt cost budget nhưng vi phạm latency SLO. Candidate khác có thể đạt latency nhưng vượt budget. Cần xác định hành vi khi vượt ngưỡng: chặn, degrade, fallback, queue hoặc cảnh báo.

### Error budget và quality budget

Nếu tổ chức dùng error budget cho reliability, có thể theo dõi tương tự cho task success hoặc quality pass rate. Ví dụ đặt tỷ lệ task không đạt factual correctness tối đa trong một cửa sổ. Với lỗi nghiêm trọng như cross-tenant data leak, không dùng tỷ lệ trung bình để cho phép một số lần vi phạm; đó là hard gate bằng 0.

## 13. Thiết kế benchmark công bằng

So sánh candidate phải kiểm soát các yếu tố có thể làm sai kết luận:

### Dataset và rubric

- Cùng dataset version, case IDs và expected evidence.
- Giữ phân bố simple/RAG/tool/long-context/high-risk.
- Cùng rubric, threshold và judge version.
- Không thay test cases sau khi xem kết quả candidate.
- Có holdout set để tránh tuning quá khớp vào regression suite.

### Hạ tầng và tải

- Cùng region, network route và provider tier nếu có thể.
- Cùng concurrency và arrival pattern.
- Warm-up trước khi đo steady state.
- Tách warm cache và cold cache.
- Ghi provider quota, rate limits, queueing và throttling.
- Đo CPU/memory/GPU và worker saturation của ứng dụng.

### Usage và cost

- Cùng price catalog version hoặc tính thêm normalized cost theo cùng rate.
- Cùng currency và allocation policy.
- Tính cả retries và failed attempts.
- Tách candidate execution cost với evaluation cost.
- Không bỏ những requests timeout hoặc bị provider tính phí.

## 14. Paired evaluation và kiểm soát biến thiên

Khi có thể, chạy cùng một case trên nhiều candidate. Đây là paired comparison: mỗi candidate nhận cùng input/reference và được chấm theo cùng rubric.

Lợi ích:

- Giảm biến thiên do case khó/dễ khác nhau.
- Cho phép xem candidate nào thắng/thua trên từng case.
- Phát hiện regression cục bộ dù average không đổi.
- Hỗ trợ bootstrap confidence interval trên chênh lệch paired.

Ví dụ:

| Case | Candidate A | Candidate B | Kết quả |
|---|---|---|---|
| RAG-001 | Pass | Pass | Tie |
| RAG-002 | Pass | Fail | A thắng |
| TOOL-003 | Fail | Pass | B thắng |
| FACT-004 | Pass | Pass | Tie |

Không chỉ báo tổng pass rate. Xem số case A thắng, B thắng, tie và nhóm lỗi cụ thể.

### Thứ tự chạy và provider drift

Provider model có thể thay backend version hoặc tải theo thời gian. Nếu chạy toàn bộ A trước rồi toàn bộ B sau, chênh lệch thời điểm có thể ảnh hưởng kết quả. Có thể interleave/randomize thứ tự case/candidate hoặc chạy song song có giới hạn để giảm temporal bias.

Ghi timestamp, model alias/deployment, region, provider headers/version nếu có. Nếu provider không đảm bảo model weights cố định, ghi rõ đây là benchmark trên dịch vụ hosted tại thời điểm chạy.

## 15. Độ bất định và ý nghĩa thống kê

Quality pass rate là một ước lượng từ sample, không phải chân lý tuyệt đối. Với tỷ lệ gần 95% trên 20 cases, một case thay đổi có thể làm score biến động 5 điểm phần trăm.

Nên báo:

- Số cases/attempts thực sự được đánh giá.
- Pass rate và số successes/failures.
- Confidence interval cho pass rate.
- Paired difference giữa candidate và baseline.
- Kết quả theo cohort và hard-gate counts.

### Bootstrap cho paired comparison

Với hai candidate chạy trên cùng case set:

1. Lưu cặp kết quả A/B cho từng case.
2. Lấy mẫu lại các case theo bootstrap, giữ cặp A/B cùng nhau.
3. Tính chênh lệch quality, cost và latency metric cho mỗi sample.
4. Lặp đủ số vòng.
5. Lấy percentile interval của phân bố chênh lệch.

Giữ cặp giúp bảo toàn cấu trúc paired. Nếu một task có nhiều attempts phụ thuộc nhau, resample theo task/case cluster thay vì coi mọi attempt là độc lập.

### Không chỉ dựa vào p-value

Một khác biệt nhỏ có thể có ý nghĩa thống kê nhưng không có ý nghĩa sản phẩm. Báo effect size, confidence interval, hard-gate failures và chi phí/latency thực tế. Định nghĩa trước mức cải thiện tối thiểu có ý nghĩa (minimum practical effect).

## 16. Đo latency dưới tải và tránh benchmark sai

Latency phụ thuộc không chỉ model mà còn concurrency, queue, provider quota và request mix.

Một benchmark tải cần xác định:

- Arrival model: closed-loop (client chờ response rồi gửi tiếp) hay open-loop (request đến theo tốc độ định trước).
- Concurrency/arrival rate.
- Warm-up và thời lượng steady state.
- Timeout/deadline.
- Request mix.
- Retry policy.
- Cache hit ratio.
- Provider rate limit và 429/5xx.

Closed-loop test có thể che queueing vì khi server chậm, client tự giảm tốc độ gửi request. Open-loop phù hợp để quan sát backlog dưới arrival rate cố định nhưng cần kiểm soát overload.

### Đo end-to-end và thành phần

Ghi các mốc:

1. Request accepted.
2. Queue start/end.
3. Retrieval start/end.
4. Mỗi model call start/end.
5. Mỗi tool start/end.
6. First token.
7. Final token/response complete.

Trace waterfall giúp giải thích latency. Request timer là nguồn chính để tính end-to-end SLO. Không cộng p95 của các span thành p95 request.

## 17. Đánh giá quality-cost-latency theo cohort

Một candidate có thể có average tốt nhưng thất bại ở nhóm high-risk. Tách cohort trước khi quyết định:

| Cohort | Quality cần xem | Cost cần xem | Latency cần xem |
|---|---|---|---|
| Simple answer | Relevance, correctness | Cost/success | p95 response |
| RAG | Recall, groundedness, factual correctness | Embedding + retrieval + generation | Retrieval + end-to-end |
| Tool workflow | Tool selection/arguments/success | Model loop + API calls | Tool + end-to-end |
| Long context | Completeness, evidence coverage | Input tokens/cached tokens | TTFT + completion |
| High-risk | Hard gates, authorization, factual correctness | Cost of checks/retries | Deadline/SLO |
| Failure recovery | Correct fallback/refusal | Cost of failed attempts | Recovery latency |

### Weighted business mix

Nếu product có workload mix đã biết, có thể tính weighted aggregate:

\[
M_{\mathrm{weighted}} = \sum_{k=1}^{n} s_k M_k,
\qquad \sum_{k=1}^{n}s_k=1
\]

Trong đó s_k là tỷ trọng cohort được xác định từ traffic hoặc kế hoạch sản phẩm. Giữ cả số liệu từng cohort; không chỉ công bố weighted average. Khi traffic mix thay đổi, weighted score cũng thay đổi dù từng cohort không đổi.

## 18. Đọc cost spike cùng trace và usage

Khi cost per successful task tăng, drill-down theo hoạt động:

| Dấu hiệu | Nguyên nhân có thể |
|---|---|
| Input tokens/request tăng | Prompt/history/context phình to |
| Output tokens tăng | Model trả lời dài hoặc không dừng đúng |
| Model calls/task tăng | Tool loop, planner, retries, fallback |
| Query embeddings tăng | Multi-query retrieval, retries hoặc cache miss |
| Vector reads tăng | Top-k lớn, filter yếu, repeated search |
| Tool calls/task tăng | Tool selection lặp hoặc tool chaining |
| Judge cost tăng | Thêm evaluator/rubric hoặc adjudication |
| Cost tăng nhưng usage ổn định | Rate/region/tier/FX thay đổi |
| Cost per success tăng | Failure rate/retry tăng hoặc success rate giảm |

Dùng trace ID để điều tra request đại diện; dùng cost ledger để xem số tiền từng operation; dùng dataset result để xác định task type có regression. Không đưa raw prompt/completion vào metric labels.

## 19. Dashboard cost-quality-latency

Một dashboard nên có các hàng:

| Hàng | Panels |
|---|---|
| Quality | Pass rate, factual correctness, relevance, groundedness, hard-gate failures |
| Unit economics | Cost/attempt, cost/success, cost/quality-pass case |
| Model usage | Calls/task, input/output/cached tokens, retries |
| RAG/tool | Recall@k, vector operations, tool calls/success, tool errors |
| Latency | End-to-end p50/p95/p99, TTFT, retrieval/model/tool p95 |
| Load | Throughput, concurrency, queue wait, saturation, 429/5xx |
| Reliability | Timeout, retry, fallback, incomplete usage |
| Comparison | Candidate vs baseline, delta, confidence interval |

Filter theo environment, task type, pipeline version, model alias, region và time window. RequestId/caseId chỉ dùng trong drill-down có phân quyền, không làm labels cho mọi metric series.

### Metric names gợi ý

Đây là tên do ứng dụng tự thiết kế, không phải meter mặc định của Spring AI:

- ai_tasks_total với labels task_type và outcome.
- ai_quality_gate_failures_total với labels gate và task_type.
- ai_task_cost_usd cho cost theo task.
- ai_task_duration_seconds cho latency theo task.
- ai_ttft_seconds cho time to first token.
- ai_model_calls_total với labels model, operation và status.
- ai_tool_calls_total với labels tool và status.
- ai_task_retries_total với label reason.

Histogram phù hợp với latency; counter phù hợp với số lần; cost cần xác định semantics (counter amount hay distribution per task) và cách aggregate. Đừng đặt user ID, request ID hoặc case ID vào label.

## 20. Quy tắc ra quyết định và rollout

Một quy trình chọn candidate có thể là:

1. Kiểm tra dữ liệu benchmark và sample size.
2. Loại candidate fail hard gates.
3. Loại candidate vượt latency SLO hoặc cost budget.
4. Tính cost per successful task và latency percentiles.
5. Tìm Pareto frontier.
6. So sánh paired results với baseline.
7. Kiểm tra cohort high-risk và long-tail.
8. Chọn candidate theo product priorities đã công bố.
9. Canary trên traffic nhỏ, theo dõi quality/cost/latency thực tế.
10. Mở rộng rollout khi các ngưỡng giữ ổn định.

### Canary cần theo dõi

- Quality signals: complaint, correction, human review, sampled audit và task success.
- Cost: provider usage, cost per successful task, retries và budget.
- Latency: p95/p99, TTFT, queue wait và timeout.
- Reliability: provider errors, tool failures, fallback.
- Safety: hard-gate violations và authorization events.

Có rollback threshold rõ ràng. Một candidate tốt trên offline dataset vẫn có thể suy giảm khi production traffic mix, provider quota hoặc cache state khác.
## 21. Lưu kết quả benchmark để tái lập

Một bảng tổng hợp chỉ hữu ích khi có thể truy ngược về candidate, dataset và run đã tạo ra số liệu. Lưu experiment metadata riêng với kết quả từng case.

### Experiment manifest

~~~yaml
experiment:
  experimentId: cost-quality-latency-2026-11-27
  datasetVersion: rag-tool-regression-v4
  rubricVersion: quality-rubric-v3
  evaluatorVersion: judge-pipeline-v2
  workload:
    concurrency: 20
    arrivalModel: open_loop
    region: ap-southeast
    cacheMode: warm
    timeoutSeconds: 30
  candidates:
    - candidateId: candidate-c
      promptVersion: answer-prompt-12
      modelAlias: model-c
      retrieverVersion: retriever-5
      toolPolicyVersion: tool-policy-3
    - candidateId: candidate-d
      promptVersion: answer-prompt-13
      modelAlias: model-d
      retrieverVersion: retriever-5
      toolPolicyVersion: tool-policy-3
  pricing:
    priceVersion: provider-catalog-2026-11-v2
    currency: USD
  startedAt: 2026-11-27T09:00:00Z
~~~

Đây là schema minh họa. Không ghi API key, prompt bí mật hoặc raw customer data vào manifest. Nếu cần lưu prompt/config đầy đủ, tham chiếu đến artifact có phân quyền và checksum.

### Case result

~~~yaml
caseResult:
  experimentId: cost-quality-latency-2026-11-27
  candidateId: candidate-c
  caseId: rag-order-014
  attemptId: 1
  outcome: success
  quality:
    relevance: 0.98
    factualCorrectness: 1.0
    groundedness: 0.96
    toolCorrectness: 1.0
    hardGatesPassed: true
  cost:
    candidateExecutionUsd: 0.082
    evaluationUsd: 0.006
    allocatedSharedUsd: 0.004
    status: estimated
  latency:
    endToEndMs: 1420
    ttftMs: 380
    retrievalMs: 95
    toolMs: 210
    modelCallsMs: 940
  traceId: 4bf92f3577b34da6a3ce929d0e0e4736
~~~

Kết quả trên là số liệu giả định. Nếu một dimension chưa được đo, để null hoặc ghi missing; không thay bằng 0 vì 0 là một kết quả có nghĩa.

## 22. Liên kết evaluation, cost ledger và trace

Một task result nên liên kết đến:

- Evaluation result: điểm từng rubric, gate outcome, evaluator version.
- Cost events: từng model call, embedding, retrieval, tool và shared allocation.
- Trace: operation spans, parent/child relationships và timing.
- Request/attempt: outcome, timeout, retry, fallback.
- Candidate manifest: prompt/model/retriever/tool policy versions.

### Tránh đếm trùng

Nếu một request có hai model calls, cost ledger có hai events nhưng evaluation case chỉ có một result. Khi aggregate:

- Quality denominator: số task/case được đánh giá.
- Cost numerator: tổng cost events thuộc các attempts trong cohort.
- Latency sample: một end-to-end duration cho mỗi task attempt, cùng quy tắc xử lý timeout.

Không lấy số model calls làm mẫu số quality. Không cộng duration của các span lồng nhau để thay end-to-end latency.

### Correlation keys

Giữ requestId, caseId, attemptId, runId, candidateId và traceId trong result/trace store. Với metrics backend, chỉ dùng labels có cardinality giới hạn như task type, candidate release alias, model family, operation và outcome class.

## 23. Xử lý timeout, cancel và task chưa hoàn tất

Latency của request timeout không phải latency thành công. Nếu chỉ tính p95 trên các response hoàn tất, candidate có nhiều timeout có thể trông nhanh giả tạo vì các request chậm nhất đã bị loại khỏi mẫu.

Hãy báo riêng:

- Completion latency của task hoàn tất.
- Timeout rate và deadline miss rate.
- Failure latency/time-to-failure.
- Cancelled/disconnected requests.
- Cost của attempts chưa hoàn tất nếu provider đã tính phí.
- Success rate theo cùng cohort.

Nếu request bị timeout ở 30 giây, có thể ghi observed time-to-timeout là 30 giây và outcome là timeout. Đừng thay timeout bằng 0 ms hoặc loại khỏi reliability report.

### Cách báo p95

Ghi rõ p95 tính trên completed requests hay all attempts. Với SLO end-to-end, thường cần theo dõi cả latency của completed requests và tỷ lệ deadline miss; một percentile chỉ trên success không phản ánh đầy đủ trải nghiệm. Nếu hệ thống dùng latency distribution có censored observations, chọn phương pháp thống kê phù hợp và mô tả trong report.

## 24. Chọn mẫu và kiểm tra độ ổn định

Số cases cần thiết phụ thuộc độ biến thiên, mức cải thiện cần phát hiện, tỷ lệ lỗi hiếm và cấu trúc paired. Không có một sample size cố định đúng cho mọi benchmark.

### Thực hành chọn mẫu

1. Dùng pilot run để ước lượng pass rate, variance cost và latency distribution.
2. Xác định minimum practical effect cho quality/cost/latency.
3. Chọn sample size đủ để confidence interval hữu ích.
4. Oversample cohort hiếm/rủi ro cao để kiểm tra hard gates.
5. Giữ holdout cases chưa dùng để tuning.
6. Lặp benchmark nếu provider/service có biến thiên lớn theo thời gian.

### Lỗi hiếm cần test riêng

Nếu một lỗi critical xảy ra với xác suất thấp, một dataset nhỏ không chứng minh lỗi đó không tồn tại. Bổ sung adversarial cases, property-based tests, authorization tests và human review. Với hard gate như cross-tenant leakage, cần test theo threat model, không chỉ suy ra từ pass rate tổng.

## 25. Các bẫy khi tổng hợp cost-quality-latency

| Bẫy | Hậu quả | Cách tránh |
|---|---|---|
| Chỉ so average quality | Che giấu cohort thất bại | Báo từng dimension/cohort và hard gates |
| Chỉ so cost/request | Bỏ qua failure/retry | Cost per successful task |
| Chỉ so p50 | Che tail latency | p50/p95/p99 và timeout rate |
| Bỏ timeout khỏi latency | Candidate lỗi trông nhanh | Báo completed latency + deadline misses |
| Gộp judge cost vào một candidate | So sánh lệch scope | Tách candidate và evaluation cost |
| Khác workload mix | Simpson's paradox | Paired cases và stratification |
| Khác cache/concurrency | Benchmark không công bằng | Khóa hoặc báo riêng điều kiện |
| Judge model thay version | Quality score drift | Pin evaluator/rubric và calibration |
| Tối ưu score trung bình | Hard gate bị che | Gate trước composite score |
| Ratio quality/cost quá cao vì cost gần 0 | Thứ hạng mất ý nghĩa | Dùng cost per success sau gate |
| Dùng p95 của span để suy p95 request | Sai do nesting/parallelism | Đo end-to-end trực tiếp |
| Không ghi pricing version | Cost history khó tái lập | Lưu priceVersion/rate snapshot |

## 26. Runbook khi candidate đắt hơn hoặc chậm hơn

Khi benchmark báo cost per successful task tăng:

1. Kiểm tra success rate và failure distribution.
2. Kiểm tra attempts/retries trên mỗi task.
3. So input/output/cached tokens trên mỗi model call.
4. So model calls/task và tool calls/task.
5. Kiểm tra query embedding, top-k, vector reads và rerank.
6. Kiểm tra price version, region, tier và FX.
7. Mở trace của các task có cost cao.
8. Phân tích theo cohort để tìm nhóm gây tăng.

Khi p95 latency tăng:

1. Xác nhận concurrency, arrival rate và request mix không đổi.
2. Kiểm tra queue wait, worker saturation và rate limiting.
3. So retrieval, model, tool và end-to-end spans.
4. Kiểm tra provider 429/5xx, timeout và retry.
5. So TTFT với completion time để xác định chậm trước hay sau token đầu.
6. Phân tích p95 theo cohort và model/region.
7. Kiểm tra cache hit ratio và cold-start.

Khi quality giảm:

1. Xác định dimension/gate giảm.
2. Xem paired cases A/B và failure examples.
3. Kiểm tra retrieval evidence, tool selection/arguments và prompt version.
4. Kiểm tra evaluator drift hoặc rubric changes.
5. Kiểm tra provider model alias/deployment changes.
6. Chặn rollout nếu hard gate hoặc quality SLO không đạt.

## 27. Tối ưu theo nguyên nhân đã đo

| Nguyên nhân | Thử nghiệm tối ưu | Guardrail |
|---|---|---|
| Prompt/context dài | Rút gọn history, deduplicate context | Factual correctness, completeness |
| Model calls nhiều | Giảm tool loop, routing đơn giản | Tool correctness, task success |
| Output dài | Giới hạn output phù hợp task | Completeness, answer quality |
| Retrieval chậm | Tối ưu filter/index/cache | Recall@k, groundedness |
| Top-k lớn | Thử k nhỏ hơn hoặc rerank | Evidence recall, factual correctness |
| Tool chậm | Parallelize độc lập, timeout/cache read-only | Authorization, idempotency |
| Model p95 cao | Thử model/region khác hoặc fallback | Quality gates, provider limits |
| Retry cao | Sửa root cause, backoff/jitter | Reliability, idempotency |
| Judge cost cao | Dùng deterministic checks cho điều kiện xác định | Calibration, agreement |
| Cache miss | Cache theo version/tenant/ACL đúng | Freshness, privacy, correctness |

Không triển khai tối ưu chỉ vì cost hoặc latency giảm trong một run nhỏ. Chạy lại benchmark, kiểm tra holdout và canary để xác nhận hiệu quả.

## 28. Bài thực hành: tìm candidate tốt cho RAG có tool

Chuẩn bị:

- Dataset gồm simple answer, RAG lookup, tool workflow, long-context và high-risk cases.
- Rubric có relevance, factual correctness, groundedness, tool correctness và hard gates.
- Ba candidate khác nhau về model/prompt/retriever hoặc tool policy.
- Usage/cost ledger và tracing cho từng request.
- Load test với concurrency và arrival rate xác định.

Thực hiện:

1. Khóa dataset, rubric, evaluator version và price catalog.
2. Chọn success definition và hard gates trước khi chạy.
3. Chạy pilot để xác định sample size và workload mix.
4. Chạy paired evaluation trên cùng cases cho từng candidate.
5. Thu quality dimensions, gate failures và human review sample.
6. Tính candidate cost per attempt và cost per successful task.
7. Tách evaluation cost và allocated infrastructure cost.
8. Thu end-to-end p50/p95/p99, TTFT, retrieval/tool/model latency.
9. Ghi timeout, retries, fallback và provider errors.
10. Phân tích theo cohort; tìm Pareto frontier sau khi áp hard gates.
11. Bootstrap paired differences cho quality/cost nếu sample size phù hợp.
12. Chọn candidate đáp ứng SLO và budget, giải thích trade-off.
13. Chạy canary, theo dõi rollback thresholds và so với offline baseline.

### Câu hỏi tự kiểm

**Câu 1:** Candidate B rẻ hơn 40% nhưng factual correctness dưới hard gate. Có nên đưa vào Pareto frontier?

Không. Loại candidate fail hard gates trước khi so frontier.

**Câu 2:** Candidate A có p50 nhanh hơn nhưng p95 chậm hơn và timeout nhiều hơn. Chỉ số nào cần xem?

Xem p50/p95/p99, timeout/deadline miss và request mix. Không chọn chỉ từ p50.

**Câu 3:** Candidate có cost/attempt thấp hơn nhưng success rate giảm. Chỉ số nào phản ánh tốt hơn?

Cost per successful task, vì numerator gồm cost của attempts trong cohort còn denominator là task thành công.

**Câu 4:** Vì sao phải tách judge cost khỏi candidate execution cost?

Judge là chi phí đo lường. Gộp không nhất quán có thể làm candidate trông đắt hơn chỉ vì số lượt evaluator khác nhau.

**Câu 5:** Có thể cộng p95 retrieval, p95 model và p95 tool để ra p95 end-to-end không?

Không. Span có thể lồng nhau hoặc song song. Đo end-to-end trực tiếp và dùng trace để giải thích thành phần.

## 29. Checklist trước khi chọn candidate

- [ ] Success definition được xác định theo task, không chỉ HTTP status.
- [ ] Hard gates và quality thresholds được chốt trước benchmark.
- [ ] Dataset/rubric/evaluator versions được pin.
- [ ] Candidate config và provider/model alias được ghi rõ.
- [ ] Cùng task mix, region, cache mode, concurrency và arrival pattern.
- [ ] Candidate cost scope giống nhau; judge/shared cost được tách.
- [ ] Retry, timeout, fallback và failed attempts được tính đúng.
- [ ] Cost per successful task được báo cùng cost per attempt.
- [ ] End-to-end p50/p95/p99 và TTFT được đo đúng mốc.
- [ ] Timeout/deadline misses không bị loại khỏi reliability report.
- [ ] Kết quả được phân tầng theo RAG, tool, long-context và high-risk.
- [ ] Sample size, confidence interval và practical effect được báo.
- [ ] Candidate fail hard gates bị loại trước Pareto comparison.
- [ ] Pareto frontier được tính trên các trục đã định nghĩa.
- [ ] Giá/usage có priceVersion và reconciliation status.
- [ ] Canary có quality/cost/latency thresholds và rollback plan.

### Tài liệu chính thức để triển khai

- Spring AI Observability: https://docs.spring.io/spring-ai/reference/observability/
- Micrometer Observation: https://docs.micrometer.io/micrometer/reference/observation.html
- OpenTelemetry GenAI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- Prometheus Histograms and Summaries: https://prometheus.io/docs/practices/histograms/
- FinOps Framework: https://www.finops.org/framework/

**Kết luận:** chọn cấu hình AI bằng chất lượng đạt được, chi phí cho task thành công và latency trong điều kiện tải đại diện. Áp hard gates và SLO trước, sau đó mới tìm Pareto frontier và cân nhắc trade-off. Benchmark paired, lưu đầy đủ versions, phân tích theo cohort và xác nhận bằng canary giúp nhóm tối ưu prompt/model/RAG/tool mà không đánh đổi độ đúng hoặc trải nghiệm người dùng một cách âm thầm.
