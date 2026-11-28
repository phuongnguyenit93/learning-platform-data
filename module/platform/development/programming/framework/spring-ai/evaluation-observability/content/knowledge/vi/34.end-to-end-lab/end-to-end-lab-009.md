# Thiết lập kiểm tra hồi quy trong CI với ngân sách giới hạn

Một thay đổi prompt, model, retriever, tool schema hoặc pipeline có thể cải thiện một nhóm câu hỏi nhưng làm hỏng nhóm khác. Chạy toàn bộ evaluation dataset trên mọi pull request thường tốn token, tiền và thời gian; bỏ qua regression test thì lỗi chất lượng chỉ lộ ra sau khi phát hành. Cần thiết kế CI gate có ngân sách rõ: mỗi thay đổi chạy đúng tập test cần thiết, theo dõi quality và cost, rồi mở rộng phạm vi khi có rủi ro.

Bài học thuộc chương **Thực hành tổng hợp** của module `SPRING_AI_EVALUATION_OBSERVABILITY`. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện suy giảm qua các phiên bản prompt, model và pipeline. Vì vậy, regression gate cần kiểm tra chất lượng đầu ra cùng vận hành, chi phí và provenance của từng candidate.

Sau bài học, bạn có thể:

- Thiết kế nhiều tầng evaluation từ smoke test đến full regression.
- Chọn dataset đại diện và phân tầng theo rủi ro.
- Đặt ngân sách cho số cases, model calls, judge calls, tokens, tiền và thời gian CI.
- So sánh candidate với baseline bằng quality gates và non-inferiority thresholds.
- Giảm nhiễu từ judge/model không deterministic.
- Dùng cache, fixture và idempotency để tránh chi phí lặp.
- Lưu evaluation artifacts và liên kết chúng với commit/prompt/model/pipeline versions.
- Tích hợp gate vào pull request, nightly run và release pipeline.
- Xử lý lỗi, timeout, budget exhaustion và inconclusive results đúng cách.

## 1. Vì sao cần regression gate có ngân sách?

Regression evaluation trả lời một câu hỏi cụ thể: **candidate có làm chất lượng hoặc vận hành suy giảm so với baseline trong phạm vi đã kiểm tra hay không?**

Một ứng dụng Spring AI có nhiều biến số:

- System/developer prompt và prompt template.
- Model/provider/model version/decoding parameters.
- Embedding model, vector index, chunking và retrieval filters.
- Reranker, topK, query rewrite và context assembly.
- Tool definitions, schema, permissions và orchestration.
- Rubric, judge model, evaluator implementation và threshold.

Một thay đổi có thể tác động khác nhau tới từng nhóm use cases. Ví dụ prompt mới tăng groundedness cho câu hỏi chính sách nhưng làm tool selection kém hơn; model mới giảm latency nhưng tăng hallucination; topK cao hơn tăng recall nhưng đẩy token cost vượt budget.

### 1.1. Regression test phải đo nhiều trục

| Trục | Ví dụ metric | Câu hỏi |
|---|---|---|
| Quality | relevance, groundedness, correctness, tool accuracy | Answer có tốt hơn hoặc ít nhất không tệ đi? |
| Reliability | timeout rate, invalid output, tool error rate | Pipeline có hoàn tất ổn định không? |
| Latency | p50/p95, retrieval duration, model duration | Response có chậm hơn không? |
| Cost | input/output tokens, estimated cost, retries | Candidate có vượt ngân sách không? |
| Safety | policy violations, leakage, unsafe tool actions | Có vi phạm guardrails không? |
| Coverage | case count, slice coverage, evaluator coverage | Test có đại diện các use cases quan trọng không? |

Không gộp mọi thứ vào một điểm trung bình. Quality có thể tăng trong khi safety hoặc cost xấu đi; gate cần ngưỡng riêng cho các chỉ số quan trọng.

### 1.2. Ngân sách là một phần của thiết kế test

Một CI run cần giới hạn:

- Số cases được chạy.
- Số model calls và judge calls.
- Input/output tokens.
- Chi phí ước tính tối đa.
- Thời gian wall-clock.
- Số retries và concurrency.
- Dung lượng artifact/trace được lưu.

Ngân sách phải được kiểm tra trước khi bắt đầu các calls tốn tiền và cập nhật trong khi chạy. Nếu chỉ kiểm tra sau khi toàn bộ dataset hoàn tất, gate đã vượt budget rồi.

### 1.3. Regression gate không thay thế production monitoring

CI dùng dataset có kiểm soát và replay được. Production monitoring quan sát phân phối traffic thật, drift và sự cố ngoài dataset. Hai nguồn bổ sung cho nhau:

```text
Pull request / release candidate
  -> deterministic fixtures
  -> bounded regression evaluation
  -> quality + cost + latency gate

Production traffic
  -> metrics / traces / sampled feedback
  -> drift and incident detection
  -> add representative cases to dataset
  -> future regression runs
```

Khi production phát hiện lỗi mới, thêm case tái hiện vào dataset để regression gate ngăn lỗi quay lại.

## 2. Phân tầng CI: không chạy full dataset ở mọi pull request

Một chiến lược hiệu quả chia evaluation thành các tầng. Tầng nhanh chạy thường xuyên; tầng sâu chạy khi thay đổi có rủi ro cao, theo lịch hoặc trước release.

### 2.1. Các tầng tham chiếu

| Tier | Trigger | Dataset | Mục tiêu thời gian | Ngân sách |
|---|---|---|---|---|
| T0 — Local/unit | Mỗi commit | Fake model, fixed fixtures | Vài giây đến vài phút | Không gọi provider thật |
| T1 — PR smoke | Mỗi pull request | 10–30 cases đại diện | 2–5 phút | Rất thấp |
| T2 — PR targeted | File/area có ảnh hưởng | 20–100 cases theo slice | 5–12 phút | Thấp, có cap |
| T3 — Nightly regression | Hằng đêm | Dataset rộng hơn | 15–60 phút | Ngân sách ngày |
| T4 — Release qualification | Trước release/model/prompt rollout lớn | Full critical + stratified dataset | Theo release window | Ngân sách được phê duyệt |

Các con số là ví dụ khởi đầu. Điều chỉnh theo provider latency, dataset size, CI concurrency và mức rủi ro của sản phẩm.

### 2.2. T0: unit tests không gọi model thật

T0 xác minh logic deterministic:

- Prompt assembly và variable substitution.
- JSON/schema validation.
- Retrieval ranking/merge với fixture cố định.
- Tool routing, permissions và idempotency.
- Retry/deadline/budget accounting.
- Evaluation aggregation và threshold calculations.
- Telemetry tags, span parentage và redaction.

Fake ChatModel có thể trả response đã định trước. Tầng này phát hiện lỗi logic nhanh và không tiêu token.

### 2.3. T1: PR smoke suite

Smoke suite phải nhỏ nhưng bao phủ các đường quan trọng:

- Một câu hỏi đơn giản có answer trực tiếp.
- Một RAG case có evidence rõ.
- Một câu hỏi không đủ evidence để kiểm tra abstention.
- Một case yêu cầu tool read-only.
- Một case tool bị policy deny.
- Một case có output schema/structured response.
- Một case biên hoặc ngôn ngữ/format quan trọng.

Không chọn chỉ các câu dễ. Smoke suite cần có ít nhất một case có khả năng phát hiện hallucination, retrieval miss hoặc tool misuse.

### 2.4. T2: targeted suite theo phạm vi thay đổi

Chọn slice dựa trên files/config changed:

| Thay đổi | Slice nên chạy |
|---|---|
| Prompt template | Case thuộc prompt/feature đó và negative cases |
| Retriever/chunking/topK | RAG cases theo document type/index/filter |
| Embedding/index | Retrieval relevance và recall slices |
| Tool schema/permissions | Tool selection, argument validity, deny/allow |
| Model/provider | Critical cases trên nhiều task types |
| Judge/rubric | Calibration set, adjudicated cases và judge agreement |
| Orchestration/retry | Timeout, fallback, partial result, retry budget |
| Cost/telemetry code | Token/cost accounting, metrics, trace and redaction tests |

Nếu thay đổi ảnh hưởng nhiều components hoặc dependency graph không xác định được, mở rộng lên critical suite hoặc nightly tier.

### 2.5. T3/T4: phát hiện regression rộng

Nightly suite theo dõi drift và tích lũy evidence; release suite đánh giá candidate có ảnh hưởng rộng. Có thể chạy nhiều seeds hoặc repeated trials cho các metrics có variance cao, nhưng phải dành ngân sách riêng cho việc lặp.

Không biến nightly failure thành tự động chặn mọi pull request nếu failure đến từ provider outage hoặc judge flakiness. Phân loại failure trước khi áp dụng release gate.

## 3. Xây dataset đại diện và quản lý test slices

Dataset nhỏ nhưng có cấu trúc tốt thường hữu ích hơn một tập ngẫu nhiên lớn. Mỗi case nên có input, expected behavior, evaluation criteria, risk tier và metadata để chọn slice.

### 3.1. Một evaluation case cần gì?

| Field | Mục đích |
|---|---|
| `case_id` | ID ổn định, không chứa thông tin cá nhân |
| `feature` | Use case/feature |
| `task_type` | RAG, direct answer, tool use, structured output |
| `risk_tier` | critical/high/normal |
| `input_ref` | Input fixture hoặc protected artifact reference |
| `expected_behavior` | Expected facts, action, refusal hoặc abstention |
| `evidence_refs` | Source/document fixtures cần thiết |
| `rubric_version` | Rubric dùng để chấm |
| `tags` | Slice metadata có cardinality được kiểm soát |
| `owner` | Người chịu trách nhiệm nội dung case |

Không đưa raw customer data hoặc secret vào repository dataset. Dùng synthetic/anonymized fixtures và kiểm soát quyền truy cập artifact.

### 3.2. Phân tầng theo task và rủi ro

Ví dụ các slices:

- `rag_policy`: hỏi đáp dựa trên policy documents.
- `rag_no_evidence`: câu hỏi ngoài corpus hoặc evidence thiếu.
- `tool_read`: gọi tool truy vấn trạng thái.
- `tool_write_guarded`: tool có side effect và permission checks.
- `structured_output`: output phải theo JSON schema.
- `multilingual`: câu hỏi nhiều ngôn ngữ.
- `long_context`: context lớn và nhiều distractors.
- `safety_critical`: câu hỏi có hậu quả cao nếu trả sai.

Một case có thể thuộc nhiều slices. Khi lấy mẫu, tránh đếm một case nhiều lần trong tổng ngân sách nếu runner không cố ý chạy lại.

### 3.3. Chọn cases theo risk-weighted sampling

Có thể dùng score để ưu tiên:

\[
priority_i = impact_i \times likelihood_i \times uncertainty_i
\]

Trong đó:

- `impact`: hậu quả nếu case lỗi.
- `likelihood`: xác suất thay đổi ảnh hưởng tới case.
- `uncertainty`: độ thiếu chắc chắn của behavior/model/evaluator.

Đây là cách xếp thứ tự, không phải xác suất thống kê. Critical safety/tool permission cases nên được giữ trong mọi PR smoke run, kể cả khi sampling ngẫu nhiên không chọn chúng.

### 3.4. Stratified sampling

Thay vì lấy 30 cases ngẫu nhiên từ 1.000 cases, phân bổ theo strata:

| Slice | Tỷ lệ minh họa | Số cases trong smoke 30 |
|---|---:|---:|
| RAG normal | 40% | 12 |
| RAG no-evidence | 15% | 5 |
| Tool use | 20% | 6 |
| Structured output | 10% | 3 |
| Multilingual/edge | 10% | 3 |
| Safety-critical | 5% | 1 |

Đây chỉ là minh họa. Safety-critical có thể cần được include theo danh sách bắt buộc thay vì phân bổ tỷ lệ.

### 3.5. Dataset versioning

Mỗi run phải biết chính xác:

- Dataset version/commit.
- Case IDs và slice selection.
- Expected behavior/evidence fixture versions.
- Rubric/evaluator versions.
- Prompt/model/pipeline/index versions.

Không sửa expected answer âm thầm để candidate mới pass. Thay đổi dataset hoặc rubric cần review riêng và lưu lý do.

## 4. Định nghĩa ngân sách trước khi gọi model

Budget cần cụ thể và có đơn vị. Một con số “chạy tối đa 5 phút” không đủ nếu provider call vẫn tiếp tục sau khi job timeout; một cap “100 cases” cũng không đủ nếu mỗi case có nhiều model/tool/judge calls.

### 4.1. Các giới hạn độc lập

| Budget | Đơn vị | Ví dụ |
|---|---|---:|
| Case budget | cases/run | 30 |
| Model call budget | calls/run | 60 |
| Judge call budget | calls/run | 30 |
| Input token budget | tokens/run | 120.000 |
| Output token budget | tokens/run | 25.000 |
| Estimated cost budget | USD/run | 2,00 |
| Wall-clock budget | seconds/run | 300 |
| Retry budget | extra attempts/run | 10 |
| Concurrency budget | active calls | 4 |

Các giá trị trên chỉ là ví dụ. Mỗi team cần chọn cap theo giá provider, độ trễ và mức criticality.

### 4.2. Ước tính trước run

Một ước tính đơn giản:

\[
C_{\text{estimated}} =
N_{\text{cases}} \times
(C_{\text{model}} + C_{\text{judge}} + C_{\text{embedding}})
\]

Trong đó cost mỗi thành phần được ước lượng theo token usage lịch sử hoặc upper bound của fixture. Nếu có retries/tools/multiple turns, cộng số calls dự kiến tương ứng.

Ước tính không thay thế runtime accounting. Dùng upper bound hoặc safety margin để tránh chọn run có expected cost sát cap.

### 4.3. Tính token cost

Với một model pricing có đơn giá input/output theo một triệu tokens:

\[
C_{\text{model}} =
\frac{T_{\text{in}}}{10^6}P_{\text{in}} +
\frac{T_{\text{out}}}{10^6}P_{\text{out}}
\]

Nếu provider tính thêm cached input, reasoning tokens, image/audio tokens hoặc tool-related charges, đưa chúng vào cost model theo pricing contract. Không giả định mọi model có cùng đơn giá.

### 4.4. Budget gate hai giai đoạn

Trước run:

1. Chọn tier và case set.
2. Ước tính calls/tokens/cost.
3. Từ chối hoặc hạ tier nếu estimate vượt cap.
4. Cấp budget còn lại cho run.

Trong run:

1. Reserve budget trước mỗi external call.
2. Ghi actual usage sau response.
3. Cộng retry attempts và judge calls.
4. Ngăn call mới khi hết bất kỳ hard cap nào.
5. Kết thúc job và ghi rõ `BUDGET_EXHAUSTED` nếu không thể hoàn tất.

### 4.5. Reserve trước khi dispatch

Nếu nhiều workers chạy song song, kiểm tra budget rồi cùng lúc gửi requests có thể vượt cap. Cần atomic reservation hoặc một coordinator quản lý shared budget:

```text
reserve(estimated_max_cost, estimated_max_tokens)
  if reservation denied:
      mark case as NOT_RUN_BUDGET
  else:
      invoke dependency
      reconcile reservation with actual usage
```

Reservation phải được release/reconcile khi call fail trước khi provider tính phí, hoặc điều chỉnh theo usage thực tế nếu provider trả usage metadata.

## 5. Thiết kế Quality Gate và baseline

Gate phải xác định trước chỉ số nào bắt buộc đạt, chỉ số nào được phép trade-off và mức suy giảm tối đa có thể chấp nhận.

### 5.1. Baseline là gì?

Baseline là candidate đã được chấp nhận và có artifact tái lập:

- Prompt/template version.
- Model/provider/deployment version.
- Decoding parameters.
- Retriever/index/chunking/reranker versions.
- Tool schema/policy versions.
- Dataset and rubric versions.
- Evaluator/judge version.
- Per-case outputs, scores, latency, tokens và costs.

Baseline không chỉ là một điểm tổng hợp trong spreadsheet. Cần lưu per-case results để biết candidate nào thay đổi behavior.

### 5.2. Absolute thresholds và relative thresholds

**Absolute threshold** yêu cầu metric đạt mức tối thiểu, ví dụ:

- Safety violation count = 0.
- Tool permission violations = 0.
- Invalid structured output rate ≤ 1%.
- Critical case success = 100% trên tập critical đã khóa.

**Relative threshold** so với baseline:

\[
\Delta Q = Q_{\text{candidate}} - Q_{\text{baseline}}
\]

Ví dụ candidate không được giảm groundedness hơn 2 percentage points hoặc p95 latency không được tăng hơn 15%.

Nên dùng cả hai: baseline tốt vẫn không cho phép candidate vi phạm safety tuyệt đối; absolute threshold cũng không phát hiện mọi regression so với baseline.

### 5.3. Quality gates theo từng dimension

| Dimension | Gate minh họa | Kiểu |
|---|---|---|
| Critical factual correctness | Không được giảm trên critical cases | Hard |
| Groundedness | Không giảm quá 2 pp | Relative |
| Retrieval relevance | Không giảm quá 3 pp | Relative |
| Tool selection/argument validity | Không giảm quá 1 pp | Relative |
| Policy violation | 0 violations | Hard |
| Invalid output | ≤ 1% | Absolute |
| p95 latency | Không tăng quá 15% | Relative |
| Cost/case | Không tăng quá 10% nếu không có approval | Relative |
| Coverage | Đủ tất cả required slices | Hard |

Các ngưỡng phải được hiệu chỉnh với sản phẩm và độ tin cậy của evaluator. Không copy các con số minh họa thành policy mặc định.

### 5.4. Không chỉ so sánh mean score

Hai candidates có cùng mean nhưng phân phối khác nhau:

- Candidate A ổn định ở mọi slices.
- Candidate B tăng mạnh ở câu hỏi dễ nhưng giảm sâu ở tool/safety-critical cases.

Theo dõi:

- Overall aggregate.
- Per-slice aggregate.
- Critical case outcomes.
- Worst-case/regression list.
- Failure rate và invalid/ERROR rate.

Gate nên kiểm tra cả aggregate và các slices quan trọng.

### 5.5. Regression delta theo từng case

Với case i:

\[
\Delta_i = score_{candidate,i} - score_{baseline,i}
\]

Lập danh sách:

- Cases giảm vượt tolerance.
- Cases đổi PASS sang FAIL.
- Cases đổi tool action hoặc refusal behavior.
- Cases tăng cost/latency bất thường.
- Cases không có kết quả ở một trong hai candidates.

Không chỉ giữ những cases candidate tốt lên; regression triage cần nhìn thấy phần suy giảm.

## 6. Độ tin cậy thống kê và ngưỡng non-inferiority

Model output và LLM judge có variance. Nếu chỉ chạy một lần trên một dataset nhỏ rồi so mean, chênh lệch nhỏ có thể do randomness chứ không phải thay đổi thật.

### 6.1. Percentage points khác percent

Nếu groundedness từ 90% xuống 88%:

- Giảm 2 percentage points (pp).
- Giảm tương đối khoảng 2,22%.

Quality gate nên ghi rõ đơn vị để tránh hiểu sai tolerance.

### 6.2. Confidence interval

Với tỷ lệ pass trên n cases, có thể ước tính confidence interval của proportion. Với sample nhỏ hoặc tỷ lệ gần 0/1, Wilson interval thường phù hợp hơn normal approximation đơn giản.

Một gate có thể yêu cầu lower confidence bound của candidate không thấp hơn baseline quá một margin định trước. Tuy nhiên, các case không độc lập hoàn toàn (nhiều cases cùng tài liệu/feature) có thể làm CI lạc quan. Phân tầng hoặc bootstrap theo nhóm phù hợp hơn nếu dataset có clusters.

### 6.3. Non-inferiority gate

Mục tiêu thường là chứng minh candidate không kém baseline quá mức chấp nhận được:

\[
H_0: Q_c - Q_b \le -\delta
\]
\[
H_1: Q_c - Q_b > -\delta
\]

Trong đó:

- \(Q_c\): quality của candidate.
- \(Q_b\): quality của baseline.
- \(\delta\): non-inferiority margin (mức giảm tối đa chấp nhận).

Nếu dữ liệu không đủ để kết luận, kết quả nên là `INCONCLUSIVE`, không tự động coi là PASS.

### 6.4. Paired comparison

Khi có thể, chạy baseline và candidate trên cùng case set, cùng fixture, cùng rubric. Paired comparison giảm ảnh hưởng của độ khó khác nhau giữa cases.

Nếu model không deterministic, có thể dùng repeated runs/seeds trên một subset calibration để ước lượng variance. Không cần lặp mọi case nhiều lần trong mỗi PR; dùng nightly/release tier cho repeated trials.

### 6.5. Judge disagreement

LLM judge có thể không ổn định hoặc thiên lệch. Với critical cases:

- Dùng human-adjudicated reference set.
- Kiểm tra judge agreement trên calibration set.
- Giữ rubric version cố định khi so candidates.
- Có thể dùng second judge hoặc manual review khi scores sát ngưỡng.
- Không để judge model và candidate model thay đổi cùng lúc mà không tách nguyên nhân.

Nếu evaluator thay đổi, baseline scores cần được tính lại bằng evaluator mới hoặc có calibration bridge; không so trực tiếp hai thang điểm không tương thích.

## 7. Kiểm soát randomness và flakiness

Không thể ép mọi LLM/provider trở nên deterministic tuyệt đối. Tuy nhiên có thể giảm nguồn nhiễu và phân loại flake.

### 7.1. Khóa các yếu tố có thể khóa

Trong CI regression run, ghi và cố định:

- Model ID/deployment revision nếu provider hỗ trợ pin version.
- Temperature, topP, seed nếu API hỗ trợ.
- System prompt và prompt template commit.
- Dataset/evidence fixture version.
- Index snapshot hoặc retrieval fixture.
- Tool mock responses và clock.
- Rubric/evaluator version.
- Timeouts/retry policies.

Nếu provider dùng alias trỏ tới model thay đổi theo thời gian, ghi provider response metadata/deployment ID nếu có.

### 7.2. Tách deterministic tests khỏi live model tests

| Test | Dependency | Dùng để |
|---|---|---|
| Prompt assembly | Fake | Kiểm tra exact messages/variables |
| Tool routing | Fake tool registry | Kiểm tra chọn tool và arguments |
| Retrieval ranking | Fixed vector scores/docs | Kiểm tra algorithm |
| Schema validation | Fixed outputs | Kiểm tra parser/validator |
| Live model regression | Provider thật | Kiểm tra end-to-end quality |
| Judge calibration | Judge model hoặc human labels | Kiểm tra evaluator reliability |

Không dùng live model để test logic đơn giản có thể kiểm tra deterministic.

### 7.3. Retry không nên biến flake thành pass giả

Nếu evaluation call timeout lần đầu rồi thành công ở retry:

- Record attempt failures và final outcome.
- Tính cost của các attempts nếu provider đã tính phí.
- Đếm logical case success riêng với dependency reliability.
- Không xóa dấu vết lỗi chỉ vì lần sau pass.

Nếu test flake do infrastructure, đánh dấu `INFRA_ERROR` hoặc `INCONCLUSIVE` theo policy, không sửa score thành PASS.

### 7.4. Retry test có giới hạn

Một test retry có thể cho phép tối đa một lần rerun để phân biệt transient infrastructure failure. Nếu rerun pass:

- Giữ kết quả ban đầu.
- Gắn trạng thái `FLAKY_RECOVERED`.
- Tạo signal cho owner điều tra.
- Không âm thầm dùng score lần hai thay thế score lần đầu.

Đối với safety-critical checks, một lần FAIL có thể vẫn cần block dù rerun pass, tùy policy.

## 8. Giảm chi phí bằng cache và fixtures

Cache giúp tránh gọi lại cùng operation, nhưng cache sai có thể che regression. Cần xác định rõ thứ gì được cache, cache key gồm những gì và khi nào phải invalidate.

### 8.1. Cache key phải chứa toàn bộ yếu tố ảnh hưởng kết quả

Một evaluation result cache key có thể gồm:

```text
hash(
  case_id,
  input_fixture_version,
  prompt_version,
  model_id_and_revision,
  model_parameters,
  retrieval_index_version,
  pipeline_version,
  tool_fixture_version,
  rubric_version,
  evaluator_version
)
```

Nếu bất kỳ yếu tố nào ảnh hưởng output mà không có trong key, cache có thể trả kết quả cũ cho candidate mới và làm regression gate pass giả.

### 8.2. Cache theo từng tầng

| Artifact | Cache? | Điều kiện |
|---|---|---|
| Dataset parsing | Có | Dataset commit/version giống nhau |
| Document fixture loading | Có | Fixture/index version giống nhau |
| Embeddings | Có thể | Input + embedding model/version + preprocessing giống |
| Retrieval result | Có thể | Query + index snapshot + filters + retriever config giống |
| Model answer | Có thể trong test replay | Prompt/model/config/inputs chính xác giống |
| Judge result | Thận trọng | Answer + rubric + judge version/parameters giống |
| Final aggregate | Có | Tất cả per-case result keys và gate config giống |

Với live model regression, có thể chủ động tắt answer cache để đo behavior candidate. Cache phù hợp hơn cho replay cùng exact configuration hoặc fixtures deterministic.

### 8.3. Không cache kết quả của candidate khác

Cache key cần chứa commit/prompt/model/pipeline versions. Nếu cache key chỉ dùng `case_id`, candidate mới có thể đọc answer hoặc judge score của baseline.

### 8.4. Cache không thay thế budget accounting

Run report cần ghi:

- Cache hit/miss count.
- Calls thực sự gửi ra provider.
- Tokens/cost thực tế.
- Estimated savings.
- Lý do cache miss/invalidation.

Một cached result không nên bị tính như provider call mới; nhưng nó vẫn là một case đã được đánh giá trong coverage report.

### 8.5. Idempotency cho CI reruns

CI có thể bị retry do runner restart hoặc network failure. Dùng run key ổn định:

```text
run_key = (
  commit_sha,
  dataset_version,
  candidate_config_hash,
  tier,
  rubric_version
)

case_result_key = (
  run_key,
  case_id,
  evaluator_version
)
```

Persist result theo key để rerun không tạo duplicate billing/records ngoài ý muốn. Nếu chủ đích muốn rerun model để đo variance, thêm `replicate_id` vào key và tính ngân sách riêng.

## 9. Quản lý concurrency, timeout và provider rate limits

Tăng concurrency rút ngắn CI duration nhưng có thể gây 429, timeout, retry amplification và cost spike. Chọn concurrency theo provider quotas và budget, không chỉ theo số CPU workers.

### 9.1. Giới hạn concurrency theo dependency

Có thể có các semaphore độc lập:

- Candidate model calls: tối đa 3.
- Judge calls: tối đa 2.
- Embedding calls: tối đa 4.
- Tool mock/test service: tối đa 5.

Đây là ví dụ. Judge và candidate model có thể dùng cùng provider quota; nếu vậy coordinator phải chia sẻ rate limit budget thay vì coi chúng độc lập.

### 9.2. Timeout theo từng operation

Thiết lập:

- Per-attempt timeout.
- Logical operation deadline.
- Whole CI job timeout.
- Maximum retry attempts.
- Maximum queue wait.

Deadline của case không nên vượt deadline của job. Khi hết budget/time, không bắt đầu case/call mới.

### 9.3. Retry policy cho provider throttling

Với HTTP 429 hoặc transient 5xx:

- Tôn trọng `Retry-After` nếu có.
- Exponential backoff + jitter.
- Giới hạn attempts và tổng deadline.
- Tính retry requests vào call/cost budget.
- Ghi attempt failures riêng với logical case outcome.

Không retry validation errors, invalid credentials hoặc policy denials như thể chúng là transient.

### 9.4. Fair scheduling

Nếu một slice có nhiều cases chậm, nó không nên chiếm hết concurrency khiến critical cases không chạy. Có thể:

- Ưu tiên critical cases.
- Dùng per-slice concurrency cap.
- Round-robin giữa slices.
- Reserve một phần budget cho mandatory safety/tool cases.

Đảm bảo case selection không bỏ qua slice quan trọng chỉ vì các cases trước đã dùng hết budget.

## 10. CI runner: orchestration và budget enforcement

CI runner nên là coordinator có trách nhiệm chọn cases, reserve budget, dispatch calls, collect results và quyết định gate. Không để mỗi test tự gọi provider mà không có shared accounting.

### 10.1. Pipeline end-to-end

```text
Pull request event
      |
      v
Resolve changed components
      |
      v
Select tier + mandatory cases + targeted slices
      |
      v
Estimate calls / tokens / cost / time
      |
      v
Budget preflight ---- over cap ----> BLOCKED_BUDGET
      |
      v
Run deterministic tests
      |
      v
Run bounded live evaluations
      |
      v
Persist per-case artifacts + traces + metrics
      |
      v
Aggregate by slice and compare baseline
      |
      v
Quality / safety / cost / latency gates
      |
      v
PASS / FAIL / INCONCLUSIVE / INFRA_ERROR
```

### 10.2. Runner phải biết rõ trạng thái từng case

Không chỉ có PASS/FAIL. Dùng trạng thái tường minh:

| Status | Ý nghĩa |
|---|---|
| `PASS` | Case chạy hoàn tất và đạt rubric/gates |
| `FAIL` | Có kết quả hợp lệ nhưng behavior không đạt |
| `INVALID` | Output không thể chấm/không đúng schema |
| `ERROR` | Application/dependency execution lỗi |
| `TIMEOUT` | Operation vượt timeout/deadline |
| `NOT_RUN_BUDGET` | Không chạy vì budget đã hết |
| `SKIPPED` | Không thuộc tier/slice được chọn |
| `INCONCLUSIVE` | Thiếu evidence để quyết định |
| `INFRA_ERROR` | CI/provider/collector infrastructure lỗi |
| `FLAKY_RECOVERED` | Lần đầu lỗi, rerun thành công theo policy |

Không gộp `NOT_RUN_BUDGET`, `SKIPPED` hoặc `INFRA_ERROR` thành PASS. Coverage report phải cho biết denominator là số cases được chọn, đã chạy hay hoàn tất.

### 10.3. Budget manager pseudocode

```text
class Budget:
    max_calls
    max_input_tokens
    max_output_tokens
    max_cost
    deadline
    calls_used = 0
    input_tokens_used = 0
    output_tokens_used = 0
    cost_used = 0
    reserved_calls = 0
    reserved_input_tokens = 0
    reserved_output_tokens = 0
    reserved_cost = 0

    def reserve(estimated_input, estimated_output, estimated_cost):
        with shared_lock:
            if now() >= deadline:
                return DENIED_DEADLINE
            if calls_used + reserved_calls + 1 > max_calls:
                return DENIED_CALL_CAP
            if input_tokens_used + reserved_input_tokens + estimated_input > max_input_tokens:
                return DENIED_INPUT_TOKEN_CAP
            if output_tokens_used + reserved_output_tokens + estimated_output > max_output_tokens:
                return DENIED_OUTPUT_TOKEN_CAP
            if cost_used + reserved_cost + estimated_cost > max_cost:
                return DENIED_COST_CAP
            reserved_calls += 1
            reserved_input_tokens += estimated_input
            reserved_output_tokens += estimated_output
            reserved_cost += estimated_cost
            return Reservation(estimated_input, estimated_output, estimated_cost)

    def reconcile(reservation, actual_usage):
        with shared_lock:
            reserved_calls -= 1
            reserved_input_tokens -= reservation.input_tokens
            reserved_output_tokens -= reservation.output_tokens
            reserved_cost -= reservation.cost
            calls_used += 1
            input_tokens_used += actual_usage.input_tokens
            output_tokens_used += actual_usage.output_tokens
            cost_used += actual_usage.cost

    def release(reservation):
        with shared_lock:
            reserved_calls -= 1
            reserved_input_tokens -= reservation.input_tokens
            reserved_output_tokens -= reservation.output_tokens
            reserved_cost -= reservation.cost
```

Đây là pseudocode dùng shared lock để minh họa atomic reservation. Production runner cần durable reservation/lease nếu workers nằm ở nhiều process hoặc máy khác nhau; cần xử lý reservation expiry, release khi call không được gửi, usage chưa có và provider billing sau timeout. Nếu actual usage vượt estimate, ghi nhận phần vượt và chặn reservation mới cho đến khi budget được đánh giá lại. Không dùng giá trị ước tính bằng 0 khi usage metadata thiếu; ghi `UNKNOWN_USAGE` và áp dụng conservative cap.

### 10.4. Case runner pseudocode

```text
def budgeted_invoke(role, estimate, operation):
    reservation = budget.reserve(
        estimate.input_tokens,
        estimate.output_tokens,
        estimate.cost
    )
    if reservation.denied:
        raise BudgetExhausted(reservation.reason)

    dispatched = false
    try:
        dispatched = true
        response = operation()
        budget.reconcile(reservation, usage_from(response))
        return response
    except Exception as error:
        if dispatched:
            budget.reconcile(reservation, usage_or_unknown(error))
        else:
            budget.release(reservation)
        raise

for case in selected_cases:
    if not run_deadline.has_time_for(case.timeout):
        mark(case, NOT_RUN_BUDGET)
        continue

    try:
        result = evaluate(
            case,
            invoke=budgeted_invoke,
            timeout=case.timeout
        )
        persist(case, result, candidate_fingerprint)
    except BudgetExhausted as error:
        mark(case, NOT_RUN_BUDGET, reason=error.reason)
    except InfrastructureError as error:
        persist_case_error(case, INFRA_ERROR, error)
```

`evaluate` phải gọi `budgeted_invoke` riêng cho từng external call: candidate model, judge, embedding, reranker hoặc dependency có tính phí. Như vậy một case có nhiều calls sẽ reserve nhiều lần và không bị tính nhầm là một call. Runner phải bảo đảm reservation được reconcile/release đúng lifecycle, kể cả khi cancellation hoặc exception xảy ra; production cần xử lý trường hợp request đã gửi nhưng usage metadata không về.

## 11. Ví dụ CI workflow có cap rõ ràng

Ví dụ dưới đây minh họa một workflow YAML kiểu GitHub Actions. Tên commands và file config là contract giả định của project; thay bằng runner thật đang dùng. Mục tiêu là cho thấy gate cần pin inputs, cap run và upload artifact kể cả khi evaluation thất bại.

```yaml
name: ai-regression

on:
  pull_request:
    paths:
      - "prompts/**"
      - "src/**"
      - "evaluation/**"
      - "config/models/**"

jobs:
  deterministic:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Unit and fixture tests
        run: ./gradlew test

  pr-evaluation:
    needs: deterministic
    runs-on: ubuntu-latest
    timeout-minutes: 8
    env:
      EVAL_TIER: pr-smoke
      EVAL_MAX_CASES: "24"
      EVAL_MAX_CANDIDATE_CALLS: "32"
      EVAL_MAX_JUDGE_CALLS: "30"
      EVAL_MAX_TOTAL_CALLS: "68"
      EVAL_MAX_INPUT_TOKENS: "85000"
      EVAL_MAX_OUTPUT_TOKENS: "15000"
      EVAL_MAX_COST_USD: "0.50"
      EVAL_MAX_RETRIES: "6"
      EVAL_CONCURRENCY: "3"
      EVAL_DEADLINE_SECONDS: "300"
    steps:
      - uses: actions/checkout@v4
      - name: Budget preflight
        run: ./gradlew evalPreflight
      - name: Run bounded evaluation
        run: ./gradlew evalRegression
      - name: Upload evaluation artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ai-regression-${{ github.sha }}
          path: build/evaluation-results/
```

Không commit provider API key trong YAML. Dùng CI secret store và cấp quyền chỉ cho job cần gọi provider. Nếu forked pull requests không được phép truy cập secrets, skip live provider suite và báo `INCONCLUSIVE`/`SKIPPED` theo policy; vẫn chạy deterministic suite.

### 11.1. Vì sao cần preflight riêng?

`evalPreflight` nên:

- Xác định changed scope và tier.
- Kiểm tra required cases.
- Đọc baseline artifact.
- Ước lượng call/token/cost budget.
- Xác nhận secrets/provider endpoint được cấu hình.
- Fail sớm nếu config sai hoặc estimate vượt cap.

### 11.2. Vì sao upload artifacts với always?

Khi evaluation FAIL hoặc budget exhausted, per-case results và failure summary vẫn cần được lưu để triage. Không upload raw prompts/secrets; artifact phải tuân theo retention/access policy.

### 11.3. Không để CI timeout là cơ chế budget duy nhất

Job timeout thường dừng process, nhưng provider call có thể đã được gửi và có thể bị tính phí. Runner cần deadline nội bộ, cancel requests và reconcile usage trước khi job kết thúc nếu có thể.

## 12. Lưu evaluation artifacts để tái lập và review

Một gate chỉ trả về dấu X đỏ/xanh không đủ để debug. Cần lưu per-case results, aggregate metrics, config fingerprint và links tới traces/logs đã được redaction.

### 12.1. Run manifest

Mỗi run nên có manifest:

```yaml
run:
  run_id: "ci-2026-11-27-1842"
  commit_sha: "abc123..."
  pull_request: 418
  tier: "pr-smoke"
  started_at: "2026-11-27T18:42:00Z"
  dataset_version: "eval-dataset-v12"
  rubric_version: "rubric-v5"
  evaluator_version: "judge-eval-v3"

candidate:
  prompt_version: "answer-v19"
  model_id: "provider/model-revision"
  model_parameters_hash: "sha256:..."
  retriever_version: "hybrid-v8"
  index_snapshot: "policy-index-2026-11-26"
  tool_schema_version: "tools-v6"
  pipeline_version: "pipeline-v14"

budget:
  max_cases: 24
  max_model_calls: 48
  max_judge_calls: 24
  max_input_tokens: 100000
  max_output_tokens: 20000
  max_cost_usd: 2.00
  max_duration_seconds: 300
```

Giá trị ở đây minh họa. Không ghi API keys, full prompts hoặc customer data vào manifest.

### 12.2. Per-case result

Một result record có thể chứa:

| Field | Ý nghĩa |
|---|---|
| run_id / case_id | Liên kết run và case |
| candidate_fingerprint | Hash config candidate |
| status | PASS/FAIL/INVALID/ERROR/TIMEOUT/... |
| quality_scores | Relevance, groundedness, correctness, tool accuracy |
| failure_reasons | Mã lỗi đã chuẩn hóa |
| latency_ms | Wall-clock và stage durations |
| token_usage | Input/output/cached/reasoning nếu provider hỗ trợ |
| estimated_cost | Cost theo pricing snapshot |
| attempts | Dependency attempts/retries |
| trace_ref | Opaque trace reference nếu có |
| artifact_ref | Reference tới output/evidence artifact có access control |

Per-case output có thể chứa answer hoặc snippets; chỉ lưu khi retention/privacy policy cho phép. Bản CI summary nên ưu tiên IDs, scores, reason codes và references.

### 12.3. Aggregate report

Aggregate report cần:

- Selected cases, completed cases, skipped cases và not-run counts.
- Status counts theo PASS/FAIL/INVALID/ERROR/TIMEOUT.
- Coverage theo required slices.
- Overall và per-slice quality scores.
- Confidence intervals hoặc uncertainty indicators khi có.
- Regression list theo case.
- Token/cost/latency distributions.
- Retry, cache hit/miss và infrastructure failure counts.
- Gate decision cùng lý do.

### 12.4. Lưu baseline snapshots

Baseline phải immutable theo fingerprint. Nếu update baseline, tạo baseline version mới và lưu:

- Ai approve.
- Candidate config fingerprint.
- Dataset/rubric/evaluator version.
- Kết quả per-case và aggregate.
- Lý do chấp nhận trade-offs.

Không ghi đè baseline hiện hành trước khi candidate mới qua release approval.

## 13. Quan sát CI run: metrics, traces và cost

CI regression runner cũng là một ứng dụng cần observability. Khi budget bị tiêu nhanh hoặc job chậm, trace và metrics giúp biết calls nằm ở đâu.

### 13.1. Metrics cho evaluation runner

| Metric | Type | Dimensions |
|---|---|---|
| `eval.cases.selected` | Counter/Gauge | tier, feature |
| `eval.cases.completed` | Counter | tier, status |
| `eval.model.calls` | Counter | provider, model alias, role |
| `eval.judge.calls` | Counter | judge alias, rubric |
| `eval.tokens.input` | Counter | model alias, role |
| `eval.tokens.output` | Counter | model alias, role |
| `eval.cost.usd` | Counter | provider, model alias, role |
| `eval.case.duration` | Histogram | task type, tier |
| `eval.budget.remaining` | Gauge | budget type, tier |
| `eval.cache.hit` | Counter | artifact type |
| `eval.retry.attempts` | Counter | dependency, reason |

Không đưa commit SHA, run ID, case ID, trace ID hoặc prompt text vào metric labels. Các IDs này thuộc run manifest/result store.

### 13.2. Trace cho một evaluation case

Một trace có thể mô tả:

```text
eval.run
  └── eval.case
      ├── app.rag.retrieve
      │   ├── retrieval.query_rewrite
      │   └── vector_store.search
      ├── app.ai.model.generate
      │   └── HTTP client request
      ├── app.ai.tool.execute
      └── eval.judge
          └── judge.model.generate
```

Span names nên ổn định. Case ID/run ID chỉ đưa vào trace attributes khi policy cho phép và không đưa vào metric tags.

### 13.3. Tách candidate calls và judge calls

Judge có thể tốn một phần đáng kể budget. Báo cáo phải tách:

- Candidate model input/output tokens.
- Judge model input/output tokens.
- Embedding/reranking costs.
- Tool/dependency calls.
- Retry attempts.

Nếu chỉ báo tổng cost, team khó biết tăng chi phí đến từ candidate hay evaluator.

### 13.4. Cost theo pricing snapshot

Giá model có thể thay đổi. Lưu pricing snapshot/version dùng để tính cost, ví dụ:

- Provider và model/deployment ID.
- Input/output rate.
- Cached input rate nếu có.
- Currency và thời điểm hiệu lực.
- Token categories được tính.

Nếu usage metadata thiếu, ghi estimated/unknown rõ ràng. Không báo cost chính xác khi chỉ có token estimate.

### 13.5. Sampling trace trong CI

PR smoke suite có thể bật sampling 100% vì số cases nhỏ, nhưng full nightly suite có thể cần sampling có chọn lọc để giảm telemetry volume. Metrics và result records phải luôn đầy đủ theo contract, độc lập với trace sampling.

Với failure cases hoặc budget exhaustion, có thể ưu tiên giữ traces theo policy. Không ghi raw prompt/answer chỉ vì trace được giữ lại.

## 14. Quyết định gate: PASS, FAIL, INCONCLUSIVE hay INFRA_ERROR

Một gate thực tế cần hơn hai trạng thái. Nếu mọi thứ khác PASS/FAIL bị gộp thành PASS, hệ thống tạo cảm giác an toàn giả; nếu mọi provider outage thành FAIL, pull request bị chặn bởi infrastructure.

### 14.1. Quy tắc quyết định

| Decision | Điều kiện | CI behavior |
|---|---|---|
| PASS | Đủ coverage, mọi hard gates đạt, relative gates đạt | Cho phép merge theo branch policy |
| FAIL | Có regression hợp lệ hoặc hard safety gate bị vi phạm | Block |
| INCONCLUSIVE | Budget hết, coverage thiếu, CI secrets không có, confidence không đủ | Không tự động pass; yêu cầu rerun/review theo policy |
| INFRA_ERROR | Provider outage, collector/runner unavailable, invalid credentials | Retry/repair infrastructure; không đổi thành quality pass |
| CONFIG_ERROR | Baseline/rubric/dataset/config thiếu hoặc không tương thích | Block cho tới khi sửa config |

### 14.2. Coverage là điều kiện tiên quyết

Ví dụ required coverage:

- Tất cả critical cases đã chạy.
- Tất cả mandatory slices có tối thiểu số cases.
- Không có case `NOT_RUN_BUDGET` trong critical set.
- Judge/evaluator hoạt động và đạt calibration threshold.

Nếu một critical case chưa chạy, overall quality score tốt không thể biến gate thành PASS.

### 14.3. Budget exhaustion

Khi hết budget:

- Dừng dispatch calls mới.
- Hủy calls đang chờ nếu client hỗ trợ.
- Reconcile usage đã nhận.
- Lưu các cases đã hoàn tất.
- Đánh dấu phần còn lại `NOT_RUN_BUDGET`.
- Trả decision `INCONCLUSIVE` hoặc `CONFIG_ERROR` tùy nguyên nhân.

Không tự giảm denominator hoặc bỏ case fail để làm score tăng.

### 14.4. Quality failure và infrastructure failure

Ví dụ:

- Model trả lời sai fact với response hợp lệ: `FAIL`.
- Model provider timeout và không có answer: `TIMEOUT`/`INFRA_ERROR` theo phân loại nguyên nhân.
- Judge trả JSON không hợp lệ: `INVALID`.
- Collector mất trace nhưng answer và evaluation result vẫn có: quality có thể đánh giá được, nhưng observability gate có thể `FAIL` riêng.
- Provider 429 liên tục do CI concurrency quá cao: infrastructure/rate-limit issue; vẫn tính attempts/cost và không bỏ qua reliability signal.

Gate có thể có nhiều sub-decisions: `quality=PASS`, `observability=FAIL`, `cost=PASS`. Overall decision theo policy nghiêm nhất trong các required gates.

### 14.5. Manual override có audit

Nếu cần override:

- Yêu cầu người có thẩm quyền.
- Ghi lý do và phạm vi.
- Lưu gate result gốc.
- Không sửa per-case results để giả thành PASS.
- Tạo follow-up issue nếu có risk còn mở.

## 15. Bảo mật secrets và quyền truy cập trong CI

Evaluation runner gọi model provider và có thể xử lý dữ liệu nhạy cảm. CI pipeline phải kiểm soát secrets, dataset và artifacts.

### 15.1. Secrets

- Lưu API keys trong CI secret manager.
- Cấp secrets chỉ cho job cần gọi provider.
- Không expose secrets cho untrusted forked pull requests.
- Không in environment variables hoặc request headers vào logs.
- Rotate keys và giới hạn quota/project nếu provider hỗ trợ.
- Dùng key riêng cho CI để tách billing/usage khỏi production.

### 15.2. Dataset access

- Ưu tiên synthetic/anonymized cases.
- Tách restricted datasets khỏi public CI jobs.
- Kiểm soát ai có thể tải artifacts.
- Đặt retention cho raw model outputs/traces.
- Không đưa customer identifiers vào filenames hoặc metric labels.

### 15.3. Artifact redaction

Trước khi upload:

- Redact prompt/answer nếu policy yêu cầu.
- Loại API keys, auth headers, cookies và tool secrets.
- Chỉ lưu evidence snippets cần thiết.
- Giữ opaque references để truy xuất protected artifacts.
- Kiểm tra redaction bằng canary values.

### 15.4. Pull request từ fork

Với pull requests không đáng tin:

- Chạy T0 deterministic tests.
- Có thể chạy offline fixture evaluation.
- Không cấp provider secrets hoặc quyền truy cập dataset restricted.
- Đánh dấu live evaluation `SKIPPED`/`INCONCLUSIVE`.
- Chạy live evaluation sau khi code vào trusted branch hoặc qua approval policy.

Không cho untrusted code đọc secret chỉ vì job có bước regression evaluation.

## 16. Worked example: tính ngân sách PR smoke

Giả sử một pull request thay đổi prompt của policy assistant. Smoke suite có 24 cases:

- 12 RAG normal.
- 4 no-evidence.
- 4 tool read/deny.
- 2 structured output.
- 2 critical facts.

Mỗi case dự kiến:

- 1 candidate model call.
- 1 judge call.
- 1 embedding call chỉ khi cache miss.
- Input candidate trung bình 1.500 tokens.
- Output candidate trung bình 300 tokens.
- Judge input 1.000 tokens và output 120 tokens.

### 16.1. Ước lượng calls

Nếu embedding fixture/cache hit toàn bộ:

\[
N_{\text{candidate}}=24,\quad
N_{\text{judge}}=24,\quad
N_{\text{embedding}}=0
\]

Tổng là 48 model/judge calls. Nếu policy cho phép tối đa một retry trên mỗi case, worst case là 24 extra attempts. Một run-level retry cap 6–8 attempts chủ động giới hạn chi phí; khi cap cạn, các cases còn lại phải được đánh dấu theo lỗi/coverage thực tế. Nếu yêu cầu retry cho mọi case, tăng retry và total-call budgets tương ứng.

### 16.2. Ước lượng tokens

Candidate:

\[
T_{\text{candidate,in}}=24 \times 1.500=36.000
\]
\[
T_{\text{candidate,out}}=24 \times 300=7.200
\]

Judge:

\[
T_{\text{judge,in}}=24 \times 1.000=24.000
\]
\[
T_{\text{judge,out}}=24 \times 120=2.880
\]

Tổng dự kiến:

- Input: 60.000 tokens.
- Output: 10.080 tokens.

Đây là estimate theo trung bình. Budget hard cap nên cao hơn estimate một khoảng có kiểm soát hoặc dùng per-case upper bound; nếu không, vài cases context dài có thể làm run dừng giữa chừng.

### 16.3. Ước lượng cost

Giả sử pricing snapshot minh họa:

- Candidate input: 2 USD / 1M tokens.
- Candidate output: 8 USD / 1M tokens.
- Judge input: 1 USD / 1M tokens.
- Judge output: 4 USD / 1M tokens.

Candidate cost:

\[
\frac{36.000}{10^6}\times2+
\frac{7.200}{10^6}\times8
=0,1296\text{ USD}
\]

Judge cost:

\[
\frac{24.000}{10^6}\times1+
\frac{2.880}{10^6}\times4
=0,03552\text{ USD}
\]

Tổng ước tính là 0,16512 USD, chưa gồm embedding/cache miss, retries, reasoning tokens hoặc các khoản provider-specific. Pricing ở đây chỉ để minh họa cách tính, không phải bảng giá hiện hành.

### 16.4. Đặt cap có safety margin

Một cấu hình có thể đặt:

| Budget | Estimate | Hard cap |
|---|---:|---:|
| Cases | 24 | 24 |
| Candidate calls | 24 | 32 |
| Judge calls | 24 | 30 |
| Input tokens | 60.000 | 85.000 |
| Output tokens | 10.080 | 15.000 |
| Cost | 0,17 USD | 0,50 USD |
| Wall-clock | 150 s | 300 s |

Cap cần được kiểm tra theo actual usage. Nếu run đạt quality gates nhưng chạm hard cost cap và thiếu cases, decision là INCONCLUSIVE, không phải PASS.

### 16.5. Quality decision ví dụ

Baseline và candidate trên cùng 24 cases:

Các quality scores dưới đây là điểm rubric trung bình đã chuẩn hóa trên thang 0–100, không phải tỷ lệ đếm case pass nhị phân; vì vậy có thể có giá trị phần trăm không chia hết cho 24.

| Metric | Baseline | Candidate | Gate |
|---|---:|---:|---|
| Groundedness | 91% | 92% | Không giảm quá 2 pp |
| Retrieval relevance | 94% | 93% | Không giảm quá 3 pp |
| Tool correctness | 100% | 100% | Không regression |
| Critical facts | 2/2 | 2/2 | Bắt buộc 2/2 |
| p95 latency | 2,8 s | 3,0 s | Tăng không quá 15% |
| Cost/case | 0,006 USD | 0,007 USD | Tăng không quá 10% |

Groundedness, retrieval, tool và critical gates đạt. Latency tăng khoảng 7,1%, cost/case tăng khoảng 16,7%; cost gate không đạt nếu không có approval hoặc justification. Candidate không PASS chỉ vì quality score tăng.

## 17. Triage regression và quy trình release

Khi gate FAIL, report cần giúp xác định thay đổi nằm ở prompt, retrieval, model, tool, evaluator hay infrastructure.

### 17.1. Phân loại regression

| Pattern | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Groundedness giảm, retrieval relevance ổn | Prompt/context use hoặc generation model | So prompt, citations, answer claims |
| Retrieval relevance giảm | Index/chunking/embedding/topK/filter | So retrieved source IDs và rank |
| Tool accuracy giảm | Tool schema/description/selection | So tool calls, arguments, policy decisions |
| Invalid output tăng | Structured output/parser/schema | So raw sanitized output và validation errors |
| Cost tăng, quality không đổi | Prompt dài, topK cao, retry/judge calls | So token breakdown và attempts |
| Latency tăng, tokens ổn | Queue, provider latency, connection pool | So traces và wait durations |
| Judge scores đổi đồng loạt | Rubric/judge model/config drift | Kiểm tra evaluator fingerprint/calibration |
| Chỉ một slice giảm | Thay đổi tác động theo feature/language/doc type | Review cases trong slice đó |

### 17.2. Regression triage workflow

1. Xác nhận dataset/rubric/evaluator fingerprints giống baseline.
2. Xác định cases và slices đổi status/score.
3. Mở trace/artifact đã redaction của cases đại diện.
4. So prompt, retrieval evidence, tool calls và model usage.
5. Phân biệt quality failure với provider/CI infrastructure error.
6. Tạo minimal reproducer và thêm case vào regression dataset nếu cần.
7. Chỉ cập nhật baseline sau khi có review/approval và ghi trade-off.

### 17.3. Không sửa expected result để làm gate xanh

Nếu candidate làm behavior thay đổi có chủ đích, expected behavior có thể cần cập nhật. Quy trình:

- Xác định product requirement đã thay đổi.
- Review expected behavior mới độc lập với candidate output.
- Cập nhật dataset version và lý do.
- Chạy baseline/candidate với dataset mới nếu có thể.
- Lưu kết quả cũ để audit.

Không để người sửa prompt tự động sửa expected answer ngay sau khi thấy FAIL mà không có review.

### 17.4. Rollout theo mức tin cậy

Một chu trình release có thể là:

```text
PR smoke PASS
    |
    v
Nightly regression PASS
    |
    v
Release qualification + human review
    |
    v
Canary rollout
    |
    v
Production metrics/traces/feedback
    |
    +---- regression detected ----> rollback / disable feature
    |
    v
Expand rollout
```

Canary rollout cần theo dõi production quality proxies, error rate, cost, p95 latency và tool safety. CI pass không đảm bảo mọi traffic production đều nằm trong dataset.

## 18. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chạy full dataset cho mọi PR | CI chậm và tốn chi phí | Tiered suites và targeted slices |
| Chỉ chạy cases dễ | Bỏ sót hallucination/tool misuse | Mandatory negative/critical cases |
| Chỉ dùng mean score | Che regression ở slice nhỏ | Per-slice và per-case gates |
| Không có absolute safety gate | Quality trung bình che policy violation | Hard safety thresholds |
| Chỉ check budget sau run | Chi phí đã vượt cap | Preflight + atomic runtime reservation |
| Không tính judge calls | Underestimate token/cost | Tách candidate/judge budgets |
| Không tính retries | Provider calls/cost vượt estimate | Retry budget riêng |
| Cache key chỉ có case ID | Candidate đọc result baseline | Key đầy đủ candidate fingerprint |
| Retry flake rồi xóa failure đầu | Che reliability regression | Giữ `FLAKY_RECOVERED` |
| Budget hết nhưng coi cases còn lại là PASS | Coverage sai | `NOT_RUN_BUDGET` và INCONCLUSIVE |
| Judge thay đổi cùng candidate | Không biết regression do đâu | Pin evaluator hoặc calibration bridge |
| Dataset thay đổi không version | Baseline không so sánh được | Immutable dataset versions |
| Ghi raw prompts vào CI artifacts | Privacy/security leak | Redaction, protected references, retention |
| Cho fork PR truy cập provider secret | Secret exfiltration | Tách deterministic và trusted live jobs |
| Đếm trace để tính evaluation coverage | Sampling làm sai denominator | Result store độc lập sampling |
| Dùng CI job timeout làm budget | Calls có thể vẫn bị tính phí | Internal deadlines/cancellation/accounting |
| Update baseline ngay sau FAIL | Hợp thức hóa regression | Approval và audit trail |

## 19. Bài thực hành: xây CI regression gate cho Spring AI

**Bối cảnh:** Một policy assistant dùng RAG hybrid, ChatClient, tool tra cứu đơn hàng và judge model chấm relevance/fact checking. Team thay prompt và tăng topK từ 4 lên 6. PR phải chạy nhanh, có cap tiền/token và lưu artifacts để review.

### Phần A — Chuẩn bị dataset

1. Tạo dataset version cố định với 24 smoke cases.
2. Bắt buộc có RAG normal, no-evidence, tool allow/deny, structured output và critical facts.
3. Gắn risk tier, feature, task type và rubric version.
4. Kiểm tra không có customer data/secrets trong fixtures.
5. Chọn baseline immutable.

### Phần B — Thiết kế budget

1. Ước tính candidate/judge/embedding calls.
2. Tính input/output token estimate theo từng role.
3. Lấy pricing snapshot và ước tính cost.
4. Đặt hard caps cho cases, calls, tokens, cost, retries, concurrency và deadline.
5. Thực hiện atomic reserve trước mỗi external call.
6. Khi hết cap, dừng dispatch và đánh dấu cases còn lại `NOT_RUN_BUDGET`.

### Phần C — Chạy CI

1. Chạy T0 deterministic tests.
2. Xác định changed scope và chọn PR smoke/targeted suite.
3. Chạy preflight để kiểm tra baseline, dataset, secrets và budget.
4. Chạy bounded live evaluations với fake tool dependencies.
5. Thu metrics/traces và per-case results.
6. Upload sanitized artifacts kể cả khi gate FAIL.

### Phần D — So sánh và quyết định

1. So candidate/baseline trên cùng cases.
2. Kiểm tra overall và per-slice quality.
3. Kiểm tra critical facts/tool permissions.
4. So p95 latency và cost/case.
5. Kiểm tra coverage và confidence/uncertainty.
6. Trả PASS/FAIL/INCONCLUSIVE/INFRA_ERROR.
7. Triage cases giảm điểm và chỉ update baseline qua approval.

### Câu hỏi tự kiểm tra

**1. Vì sao không chạy full dataset ở mọi PR?**  
Vì mỗi case có thể tạo nhiều model/judge/tool calls, làm CI chậm và tốn chi phí. Tiered suites giữ feedback nhanh và dành full suite cho nightly/release.

**2. Nếu 24 cases được chọn nhưng chỉ 20 cases chạy do cost cap, gate có PASS không?**  
Không nếu required coverage chưa đủ. Phải ghi 4 cases là NOT_RUN_BUDGET và decision INCONCLUSIVE hoặc block theo policy.

**3. Vì sao cache key phải chứa prompt/model/pipeline versions?**  
Để tránh candidate mới lấy answer/judge score từ cấu hình cũ và che regression.

**4. Candidate có quality tăng nhưng cost tăng vượt hard cap thì sao?**  
Gate không PASS theo policy. Cần tối ưu hoặc xin approval có audit nếu trade-off được chấp nhận.

**5. Judge timeout có nghĩa answer FAIL không?**  
Không. Judge execution lỗi hoặc không có verdict hợp lệ. Phân loại ERROR/INCONCLUSIVE, không gán quality FAIL.

**6. Khi rerun flaky test pass, có xóa kết quả fail đầu không?**  
Không. Giữ lần đầu, ghi FLAKY_RECOVERED và điều tra reliability. Với critical checks, policy có thể vẫn block.

**7. Trace bị sampled out có làm mất evaluation result không?**  
Không. Result persistence và metrics coverage phải độc lập trace sampling.

## 20. Ghi nhớ

- **Regression gate** so candidate với baseline trên dataset có version, rubric và evaluator rõ ràng.
- **Tiered CI** dùng deterministic tests cho mọi commit, PR smoke/targeted cho feedback nhanh, nightly/release cho coverage rộng.
- **Dataset slices** cần đại diện task types, negative cases và critical risks; không chỉ lấy câu hỏi dễ.
- **Budget** phải giới hạn cases, model/judge calls, tokens, cost, retries, concurrency và wall-clock.
- **Preflight và runtime reservation** ngăn run bắt đầu khi estimate vượt cap và ngăn workers cùng vượt budget.
- **Quality gates** cần absolute safety thresholds, relative non-inferiority margins và per-slice/per-case checks.
- **Statistical uncertainty** cần được thể hiện; thiếu evidence là INCONCLUSIVE, không phải PASS.
- **Judge/evaluator** phải được pin/calibrate; không đổi judge cùng candidate nếu chưa có calibration bridge.
- **Cache keys** phải chứa mọi versions/config ảnh hưởng kết quả; cache không được che candidate regression.
- **Retries** phải được tính vào calls/cost và không xóa failure ban đầu.
- **Run artifacts** cần manifest, per-case results, aggregate report và immutable baseline snapshots.
- **Metrics/traces** giúp điều tra CI run nhưng trace sampling không được thay đổi coverage hoặc result persistence.
- **CI states** cần tách PASS, FAIL, INCONCLUSIVE, INFRA_ERROR và CONFIG_ERROR.
- **Secrets/dataset/artifacts** phải được bảo vệ; fork PR không được tự động nhận provider credentials.
- **Release rollout** kết hợp CI qualification, human review, canary và production monitoring.

Thiết lập kiểm tra hồi quy trong CI với ngân sách giới hạn giúp nhóm Spring AI nhận ra prompt/model/retrieval/tool changes gây suy giảm trước khi phát hành mà vẫn kiểm soát được token, tiền và thời gian. Khi dataset có cấu trúc, baseline immutable, budget được reserve, quality gates theo slice và artifacts có thể truy vết, CI trở thành một phần đáng tin cậy của vòng lặp cải thiện chất lượng thay vì một batch gọi model tốn kém và khó giải thích.
