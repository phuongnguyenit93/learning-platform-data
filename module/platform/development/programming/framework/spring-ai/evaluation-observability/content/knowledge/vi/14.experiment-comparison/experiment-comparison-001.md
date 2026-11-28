# Thiết kế so sánh theo cùng một tập tình huống

> **Chương:** So sánh thí nghiệm
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI theo tập dữ liệu, relevance, fact checking, các luồng RAG/tool calling; kết hợp metrics, traces, chi phí và độ trễ để phát hiện suy giảm chất lượng giữa các phiên bản prompt, model, pipeline.
>
> **Bối cảnh công nghệ:** Java 21, Spring Boot 4.2.x và Spring AI 2.1.x. Mọi số liệu ví dụ dưới đây là giả lập để minh họa phương pháp, không phải kết quả benchmark thực nghiệm.

## 1. Vì sao phải so sánh trên cùng tập tình huống?

Giả sử một trợ lý RAG báo cáo:

- Bản A: **86% PASS**.
- Bản B: **91% PASS**.

Hai con số này **chưa chứng minh B tốt hơn**. Có thể A chạy 100 câu khó, B chỉ chạy 80 câu dễ. A dùng tập tài liệu cũ, B dùng tập mới. Judge của hai bản có thể đã đổi model hoặc rubric. Thậm chí B có thể sửa được nhiều câu nhưng làm hỏng những câu trước đây A trả đúng.

Muốn so sánh công bằng, cần thực thi A và B trên **cùng dataset và cùng các case ID**, định nghĩa kết quả giống nhau, rồi đối chiếu **từng cặp case**. Phương pháp này gọi là *paired comparison*.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Đăng ký trước giả thuyết, biến thay đổi, primary metric và guardrails.
2. Tạo dataset được version hóa và ghép kết quả A/B theo `case_id`, không phụ thuộc thứ tự chạy.
3. Chọn đúng **frozen-context** hay **end-to-end comparison** khi đánh giá prompt, model, retriever hoặc pipeline RAG.
4. Tách quality `PASS/FAIL` khỏi lỗi generator, judge, tool và tình huống không đủ context.
5. Tính bảng bốn ô **both pass / A-only / B-only / both fail**, mức cải thiện theo *điểm phần trăm* và paired coverage.
6. So sánh retrieval, tool assertions, latency, token, chi phí và traces trên cùng định nghĩa chỉ số.
7. Đưa ra quyết định phát hành với đánh giá độ bất định, nguy cơ lệch judge và quality gate minh bạch.

## 2. Nguyên tắc paired comparison

Một **case** là đơn vị tình huống có ID ổn định, câu hỏi, dữ liệu nguồn và nhãn chuẩn. Một **arm** là biến thể của hệ thống: A (baseline) hoặc B (candidate). Một **run** là lần chạy một arm trên một dataset đã chốt.

Điều kiện tối thiểu:

\[
\operatorname{CaseIds}(A)=\operatorname{CaseIds}(B)
\]

Không chỉ cần **số lượng** bằng nhau mà phải là **chính những ID ấy**, cùng phiên bản nội dung câu hỏi, nhãn chuẩn và split.

| Câu hỏi kiểm tra | Thiết kế đúng |
|---|---|
| Hai arm có cùng câu hỏi? | Khóa dataset revision/digest; so tập `case_id` |
| Hai arm có cùng kỳ vọng chất lượng? | Khóa labels, rubric, judge, scoring policy |
| Có chủ đích thay gì? | Khai báo trong experiment plan và đối chiếu manifest diff |
| RAG sử dụng bằng chứng nào? | Lưu context *thực sự* cấp vào generator mỗi arm |
| Tool có được gọi đúng? | So tool name/typed arguments bằng assertion xác định |
| Có case lỗi kỹ thuật? | Công bố `GENERATION_ERROR`, `EVALUATION_ERROR` và coverage |
| Có thể kiểm tra sự khác biệt? | Ghi answer, snapshot, model/prompt versions và telemetry references |

**Cùng dataset là điều kiện cần nhưng chưa đủ.** Hai arm đều chạy đủ 120 case nhưng được chấm bằng rubric khác nhau thì tỷ lệ PASS không cùng ý nghĩa.

## 3. Xác định câu hỏi nghiên cứu trước khi chạy

Công thức lập giả thuyết:

> Thay đổi **X** trong pipeline Spring AI sẽ cải thiện **Y** trên dataset **D** và không vi phạm các giới hạn **Z** về độ trễ, lỗi kỹ thuật, chi phí hoặc an toàn.

Ví dụ:

> Thay system prompt từ `answer-v3` sang `answer-v4` sẽ làm tăng **fact-check pass rate** trên `vi-rag-regression-v5`, trong khi **relevance** không suy giảm quá 1 điểm phần trăm và **p95 generator latency** không tăng quá 20%.

### Biến thay đổi và biến cần giữ cố định

| Mục tiêu | Biến chủ đích | Giữ cố định khi có thể |
|---|---|---|
| So system prompt | Prompt revision | Dataset, model, context, judge/rubric, options |
| So generator model | Model ID/deployment | Prompt, dataset, context, judge/rubric |
| So reranker | Reranker algorithm/model | Corpus/index, ground truth, generator và judge |
| So top-k | Retrieval top-k | Dataset, corpus/index, embedding và scoring policy |
| So embedding | Embedding model + rebuilt index | Dataset, corpus, retrieval metric definition |
| So tool schema | Tool contract/selection | Case IDs, sandbox fixture và tiêu chí tool correctness |
| So judge | Judge model | **Recorded answers/context**, rubric và human labels |
| So toàn pipeline | Bundle prompt + retriever + model | Dataset và evaluation policy; **không suy diễn nguyên nhân riêng** |

Một thử nghiệm có thể thay nhiều thành phần nếu mục tiêu là đánh giá **hệ thống B trọn gói**. Khi đó chỉ có thể kết luận “B có kết quả khác A trên tập này”, không thể tự quy hiệu quả cho riêng prompt hay model.

## 4. Sơ đồ thực nghiệm hai nhánh

~~~mermaid
flowchart TD
  D["Dataset D bất biến: case IDs + labels"] --> A["Baseline A"]
  D --> B["Candidate B"]
  A --> SA["Execution snapshot A"]
  B --> SB["Execution snapshot B"]
  SA --> JA["Evaluator E cố định"]
  SB --> JB["Evaluator E cố định"]
  JA --> OA["Case outcomes A"]
  JB --> OB["Case outcomes B"]
  OA --> P["Join theo case_id"]
  OB --> P
  P --> M["Paired quality + coverage + errors"]
  M --> R["Metrics / traces / token / cost"]
  R --> G["Quality gate + review + quyết định"]
~~~

**Baseline A** nên có một run manifest và report đã xác minh. **Candidate B** dùng cùng dataset/scoring policy nhưng thay các biến được khai báo. Nếu muốn đổi judge, hãy **tái chấm answer snapshots của cả A và B bằng cùng judge mới** thay vì so pass rate của judge cũ với judge mới.

### Experiment plan mẫu

~~~yaml
experiment_id: "prompt-grounding-001"
question: "Prompt mới có giảm hallucination?"
hypothesis: "prompt-v4 tăng groundedness không vượt giới hạn cost"
dataset:
  id: "vi-policy-rag-regression"
  revision: "v5"
  digest: "sha256:replace-with-actual-digest"
primary_metric: "paired_fact_check_delta_pp"
guardrails:
  - "paired_evaluation_coverage"
  - "relevance_regression_pp"
  - "generator_p95_latency_ms"
  - "estimated_cost_usd_per_case"
variants:
  baseline:
    id: A
    answer_prompt_revision: "answer-v3"
  candidate:
    id: B
    answer_prompt_revision: "answer-v4"
fixed:
  generator_model: "model-X"
  judge_model: "judge-Y"
  judge_rubric_revision: "fact-check-v2"
  corpus_revision: "policy-corpus-v8"
  index_revision: "vector-index-v12"
  retrieval_top_k: 5
  tool_fixture_revision: "sandbox-tools-v3"
~~~

Đây là **schema do nhóm dự án tự định nghĩa**, không phải property mà Spring AI tự thực thi. Giá trị `replace-with-actual-digest` phải được thay bằng hash thật trong run manifest.

## 5. Dataset dùng chung cần những loại tình huống nào?

Một dataset chỉ có các câu dễ mà model luôn trả đúng sẽ không phát hiện được regression. Nên có:

| Nhóm | Nhãn cần lưu | Điểm rủi ro |
|---|---|---|
| RAG direct | Relevant document IDs, expected claims | Đúng nguồn nhưng diễn giải sai |
| RAG distractor | Nguồn còn hiệu lực và nguồn cũ gây nhiễu | Chọn sai tài liệu |
| RAG multi-hop | Nhiều chứng cứ cần kết hợp | Bỏ sót một bước |
| No-context | `expectAbstention=true` | Bịa câu trả lời khi thiếu bằng chứng |
| Tool mandatory | Expected tool + typed arguments | Chọn sai tool/tham số |
| Tool failure | Fixture timeout/error | Bịa kết quả hoặc retry vô hạn |
| Prompt injection | Context có chỉ dẫn giả mạo | Làm theo chỉ dẫn trong tài liệu |
| Long context | Chuỗi chunks, token budget | Truncation mất dữ kiện quan trọng |

### Ví dụ trích đoạn `cases.jsonl` (4 case trong dataset minh họa lớn hơn)

~~~jsonl
{"id":"rag-001","scenario":"rag","question":"Hạn nộp báo cáo tháng?","expectedDocumentIds":["policy-v3-07"],"expectedClaims":["Trước ngày 05 của tháng kế tiếp"],"expectAbstention":false,"tags":["policy","deadline"]}
{"id":"rag-002","scenario":"rag","question":"Chính sách hiệu lực hiện hành quy định gì?","expectedDocumentIds":["policy-current-04"],"expectedClaims":["Phải dùng tài liệu còn hiệu lực"],"expectAbstention":false,"tags":["distractor"]}
{"id":"noctx-003","scenario":"no_context","question":"Ai đã phê duyệt tài liệu bí mật X?","expectedDocumentIds":[],"expectedClaims":[],"expectAbstention":true,"tags":["abstention"]}
{"id":"tool-004","scenario":"tool","question":"Đơn giả lập TEST-004 đã giao chưa?","expectedToolCalls":[{"name":"getOrderStatus","arguments":{"orderId":"TEST-004"}}],"expectedClaims":["Đang vận chuyển"],"tags":["tool","sandbox"]}
~~~

**Dữ liệu minh họa hoàn toàn giả lập.** Expected claims/expected tool calls là **ground truth dành cho evaluator**, không được chèn vào generator prompt như “đáp án đúng”, nếu không phép thử bị *label leakage*.

### Manifest và kiểm soát thay đổi

~~~yaml
dataset_id: "vi-policy-rag-regression"
revision: "v5"
schema_version: 2
content_sha256: "sha256:replace-with-actual-digest"
case_count: 120
language: vi
split: "held-out-regression"
labels_revision: "human-reviewed-v3"
corpus_snapshot: "policy-corpus-v8"
scenario_counts:
  rag: 80
  tool: 25
  no_context: 15
allowed_environments: [test, staging]
~~~

Khi sửa câu hỏi, labels hoặc expected claims, phải tạo revision mới. Hai file cùng tên `v5` nhưng khác bytes/labels **không được coi là cùng dataset**. Runner nên kiểm tra ID trùng, schema, content hash, số case và referential integrity trước khi chạy.

**Không chỉ kiểm case_count.** Hai run cùng có 120 case nhưng thay 10 ID thì phép đo không còn là paired comparison.

## 6. Frozen-context và end-to-end: hai thiết kế rất khác

### 6.1. Frozen-context — so prompt/model generator

1. Ghi một **snapshot evidence** cho từng question.
2. Cho **cả A và B** nhận đúng context sau filter/rerank/truncation đã khóa.
3. Chỉ thay prompt hoặc generator model theo kế hoạch.
4. Chấm answer A/B theo cùng evidence, judge và rubric.

**Ưu điểm:** cô lập ảnh hưởng của generator; không bị retrieval drift. **Giới hạn:** không đánh giá tác động của retriever hoặc việc corpus/index thay đổi.

### 6.2. End-to-end — so retriever hoặc toàn pipeline

1. A và B nhận cùng `question`, cùng dataset, labels và corpus snapshot.
2. **Nếu retriever là biến chủ đích**, A/B **có thể lấy context khác nhau**.
3. Generator A nhận context A; generator B nhận context B.
4. Judge chấm answer A trên **evidence A**, answer B trên **evidence B**.
5. Đo thêm retrieval recall@k, ranking, context tokens và vector latency.

**Sai lầm thường gặp:** ép B dùng context A khi đang muốn thử reranker B, hoặc cho judge tự truy xuất lại bằng một index mới sau lúc answer đã tạo. Cả hai đều làm đánh giá factuality sai ý nghĩa.

| Thử nghiệm | Cùng context A/B? | Cùng corpus/index? |
|---|---|---|
| Prompt-only | **Có**, frozen | Có |
| Generator model-only | **Có**, nếu muốn cô lập model | Có |
| Retriever/reranker | **Không bắt buộc** | Thường có, trừ index là biến thay đổi |
| Embedding + rebuilt index | **Không** | Corpus giống; index có thể khác và phải ghi rõ |
| Full pipeline | **Không** | Theo manifest của hai pipeline |

## 7. Tool calling phải được chấm hành vi riêng

Với tool workflow, chấm final answer bằng LLM là chưa đủ. Cần biết assistant **đã gọi tool nào, với tham số nào và kết quả gì**.

~~~json
{
  "caseId": "tool-004",
  "toolSchemaRevision": "v2",
  "fixtureRevision": "sandbox-orders-v3",
  "expectedTool": "getOrderStatus",
  "expectedArguments": {"orderId": "TEST-004"},
  "actualTool": "getOrderStatus",
  "actualArguments": {"orderId": "TEST-004"},
  "toolResult": {"status": "IN_TRANSIT"},
  "answer": "Đơn hàng đang được vận chuyển."
}
~~~

Một bài so sánh tool nên chấm **deterministic assertions** cho tool name, typed arguments, số lượt gọi, thứ tự nếu cần và schema hợp lệ. Sau đó dùng judge/human review để chấm câu văn cuối có phản ánh tool output đúng không.

Hai arm nên dùng cùng **sandbox fixture/tool schema revision** trừ khi tool contract là biến đang thử. Không được replay công cụ có side effect lên thanh toán/CRM/email production; dùng mock/sandbox, idempotency và quyền rõ ràng.

## 8. Giữ evaluator và rubric nhất quán

Trong Spring AI 2.1.x, interface `Evaluator` nhận một `EvaluationRequest`. Hai evaluator phổ biến:

- **`RelevancyEvaluator`:** đánh giá answer liên quan question và context.
- **`FactCheckingEvaluator`:** đánh giá claim trong answer có được evidence hỗ trợ.

Ví dụ dựng evaluation input từ đúng context mà generator đã sử dụng:

~~~java
import java.util.List;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;

String question = "Hạn nộp báo cáo tháng khi nào?";
List<Document> contextActuallyUsed =
        List.of(new Document(
            "Báo cáo tháng phải được nộp trước ngày 05 của tháng kế tiếp."));
String answer = "Hạn nộp là trước ngày 05 tháng sau.";

EvaluationRequest request = new EvaluationRequest(
        question, contextActuallyUsed, answer);
// Chấm bằng các evaluator đã cấu hình với cùng judge/rubric.
~~~

Constructor `EvaluationRequest(String, List<Document>, String)` là của dòng Spring AI 2.1; một số tài liệu cũ trình bày `List<Content>`, không nên trộn API hai phiên bản.

### Kiểm soát judge drift

Đóng băng:

- `judge_provider/model` và resolved revision nếu provider công bố;
- judge prompt/rubric, thresholds, output schema, response parsing;
- options (temperature, seed nếu hỗ trợ);
- human calibration set và scoring policy.

Judge có thể mắc **self-preference, verbosity, position bias** và bị prompt injection từ context. Nếu sử dụng **pairwise judge** đọc hai answers cùng lúc, hãy che nhãn A/B và **đảo thứ tự hiển thị** trong một phần thí nghiệm để giảm position bias. Nếu dùng **pointwise PASS/FAIL**, phải giữ cùng rubric trên cả hai arm.

**`isPass()==true` không phải chứng nhận câu trả lời đúng tuyệt đối.** Đo false pass/false fail qua một tập human-labeled calibration, đặc biệt ở bài fact checking có rủi ro.

## 9. Tách execution outcome và assessment outcome

Không được gộp “request hoàn tất” với “answer đúng”:

| Execution | Assessment | Ý nghĩa | Tính vào pass rate nội dung? |
|---|---|---|---|
| `COMPLETED` | `PASS` | Answer đạt rubric | Có |
| `COMPLETED` | `FAIL` | Answer không đạt | Có |
| `COMPLETED` | `EVALUATION_ERROR` | Answer có nhưng judge timeout/parse lỗi | **Không** |
| `GENERATION_ERROR` | `NOT_EVALUATED` | Không có answer hợp lệ | **Không** |
| `NO_CONTEXT` | `ABSTENTION_PASS/FAIL` | Đánh giá khả năng từ chối | Chỉ trong metric phù hợp |
| `SKIPPED` | `NOT_EVALUATED` | Quota/policy/điều kiện không chạy | **Không** |

Một câu có thể trả HTTP 200 nhưng `FAIL` vì nội dung sai. Ngược lại, judge bị 429 sau khi generator đã trả đúng phải ghi `EVALUATION_ERROR`, không tự biến thành generator `FAIL`.

### Các mẫu số phải ghi rõ

\[
\mathrm{PassRate}_A =
\frac{N_{A,\mathrm{PASS}}}
{N_{A,\mathrm{PASS}}+N_{A,\mathrm{FAIL}}}
\]

\[
\mathrm{Coverage}_A =
\frac{N_{A,\mathrm{PASS}}+N_{A,\mathrm{FAIL}}}
{N_{\mathrm{eligibleCases}}}
\]

Tỷ lệ lỗi generation/judge và số skipped phải công bố riêng. Không âm thầm bỏ lỗi rồi chỉ báo tỷ lệ PASS trong số cases “còn sống”.

## 10. Paired coverage: chỉ chấm cặp có verdict hợp lệ của cả hai

Đặt:

\[
P = \{i \in D \mid
\mathrm{Verdict}_{A,i}\in\{\mathrm{PASS},\mathrm{FAIL}\}
\;\text{và}\;
\mathrm{Verdict}_{B,i}\in\{\mathrm{PASS},\mathrm{FAIL}\}\}.
\]

\[
\mathrm{PairedCoverage}=\frac{|P|}{|D_{\mathrm{eligible}}|}.
\]

Nếu dataset có 100 case, A chấm hợp lệ 95, B chấm hợp lệ 90, cả hai **đồng thời chấm hợp lệ ở 87 case**, paired coverage là **87%** (không phải 90% hay 95%).

Các case còn lại phải được **báo riêng nguyên nhân**. Đặc biệt nếu model B thường lỗi ở những câu dài/khó, việc chỉ đo chất lượng trên cặp còn lại có thể thiên lệch theo hướng ưu ái B. Một quality gate cần đặt điều kiện về **coverage và error rate**, không chỉ chất lượng trên cặp hợp lệ.

### Không nên xử lý thiếu dữ liệu như thế nào?

- **Không** tự điền `pass=false` cho judge timeout.
- **Không** ghép câu trả lời dựa vào index trong array.
- **Không** chọn attempt tốt nhất từ nhiều retries mà không khai báo policy.
- **Không** gọi `NOT_APPLICABLE` của tool-only case là thất bại retrieval.
- **Không** so tỷ lệ trên hai mẫu số khác nhau mà gọi là paired delta.

## 11. Run manifest và kết quả từng case

Để tái lập, lưu **experiment definition**, hai run manifests và case results:

~~~text
experiment/
  comparison-plan.yml
  dataset-v5/
    manifest.yml
    cases.jsonl
  baseline-A/
    run-manifest.yml
    case-results.jsonl
  candidate-B/
    run-manifest.yml
    case-results.jsonl
  comparison/
    paired-results.jsonl
    summary.json
    review-notes.md
~~~

Đây là **cấu trúc tham khảo cho dự án học**, không phải những tệp cần tạo trong module hiện tại.

### Ví dụ `run-manifest.yml`

~~~yaml
schema_version: 1
experiment_id: "prompt-grounding-001"
run_id: "prompt-grounding-001-A"
arm: A
environment: staging
started_at_utc: "2026-11-27T09:00:00Z"
source:
  git_commit: "replace-with-full-git-sha"
  dirty_worktree: false
  java_version: "21"
  spring_boot_version: "4.2.0"
  spring_ai_bom_version: "2.1.0"
  artifact_digest: "sha256:replace-with-real-digest"
dataset:
  revision: "v5"
  digest: "sha256:replace-with-real-digest"
  eligible_case_count: 120
generator:
  provider: "provider-X"
  requested_model_id: "generator-model-id"
  resolved_model_revision: null
  prompt_revision: "answer-v3"
  temperature: 0.2
retrieval:
  mode: "frozen-context"
  corpus_revision: "policy-corpus-v8"
  index_revision: "vector-index-v12"
  embedding_model: "embedding-model-id"
  top_k: 5
tool:
  schema_revision: "tool-contracts-v2"
  fixtures_revision: "sandbox-tools-v3"
evaluation:
  judge_model: "judge-model-id"
  rubric_revision: "fact-check-v2"
  calibration_revision: "human-labels-v3"
  scoring_policy_revision: "gate-v3"
execution:
  max_concurrency: 2
  max_retries: 1
  timeout_seconds: 40
telemetry:
  observation_schema_revision: "obs-v2"
  tracing_sampling_probability: 1.0
  trace_backend_alias: "staging-evaluation"
~~~

Manifest B chỉ thay những trường dự kiến trong `comparison-plan.yml`. Nếu ngoài prompt còn thay model/index, báo cáo phải gọi đó là **multiple-change** hoặc **full pipeline comparison**.

### Case result phải lưu cả attempt và error

~~~jsonl
{"runId":"prompt-grounding-001-A","arm":"A","datasetRevision":"v5","caseId":"rag-001","attempt":1,"executionStatus":"COMPLETED","assessmentStatus":"EVALUATED","pass":true,"answerRef":"restricted://A/rag-001","evidenceDigest":"sha256:actual-digest","inputTokens":310,"outputTokens":55,"usageStatus":"REPORTED"}
{"runId":"prompt-grounding-001-B","arm":"B","datasetRevision":"v5","caseId":"rag-001","attempt":1,"executionStatus":"COMPLETED","assessmentStatus":"EVALUATED","pass":false,"answerRef":"restricted://B/rag-001","evidenceDigest":"sha256:actual-digest","inputTokens":325,"outputTokens":60,"usageStatus":"REPORTED"}
~~~

`restricted://...` là tham chiếu **giả lập**. Trong dự án thật, evidence/answers nhạy cảm phải lưu tại nơi có quyền và retention. Không đưa API key, full prompt, tool credentials hoặc thông tin người dùng thật vào artifact công khai.

## 12. Giao thức chạy để giảm nhiễu

Các yếu tố thường khiến A/B không công bằng gồm **provider load, warmup/caching, concurrency, rate limits, model alias drift, index update và tool state thay đổi theo thời gian**.

Quy trình khuyến nghị:

1. **Preflight:** kiểm checksum dataset, labels, case IDs, rubric/judge và biến cần giữ cố định.
2. **Warmup (nếu cần):** chạy warmup riêng và định nghĩa trước việc có loại khỏi phép đo hay không.
3. **Interleave hoặc randomize:** chạy A/B theo từng case hoặc hoán đổi thứ tự một cách kiểm soát, ghi seed thứ tự.
4. **Giữ resource budgets tương đương:** concurrency, timeout, retries, generation token budget và quota; nếu API/model khác giới hạn, ghi rõ.
5. **Lưu mọi attempt:** không ghi đè retry và không lấy output tốt nhất một cách tùy ý.
6. **Chấm cùng rubric/judge:** dùng chính evidence mà mỗi variant cấp cho generator.
7. **Join nghiêm ngặt theo ID:** phát hiện missing/duplicate trước khi tổng hợp.
8. **Báo cáo guardrails và độ bất định:** không quyết định từ một pass rate đẹp đơn lẻ.

Một **random seed** giúp tái hiện thứ tự chạy, không bảo đảm hosted LLM cho cùng tokens đầu ra từng lần. Nếu tool có side effect, mọi retry/replay phải chạy trên sandbox hoặc có idempotency được chứng minh.

## 13. Bảng bốn ô của so sánh nhị phân ghép cặp

Với các case được A và B chấm hợp lệ:

| | B PASS | B FAIL |
|---|---:|---:|
| **A PASS** | **both pass (a)** | **A-only pass (b)** |
| **A FAIL** | **B-only pass (c)** | **both fail (d)** |

- **a:** cả hai đạt; **d:** cả hai không đạt.
- **b:** A đạt nhưng B không — *regression* của B.
- **c:** A không đạt nhưng B đạt — *improvement* của B.

\[
N_\mathrm{paired}=a+b+c+d
\]

\[
\mathrm{PassRate}_A=\frac{a+b}{N_\mathrm{paired}},
\quad
\mathrm{PassRate}_B=\frac{a+c}{N_\mathrm{paired}}
\]

\[
\Delta_\mathrm{paired}=
\mathrm{PassRate}_B-\mathrm{PassRate}_A
=\frac{c-b}{N_\mathrm{paired}}.
\]

**\(\Delta\)** là chênh lệch tỷ lệ. Nhân 100 để biểu diễn **điểm phần trăm (percentage points, pp)**, khác với “tăng tương đối 25%”.

### Ví dụ 12 case giả lập

| Nhóm | Số case |
|---|---:|
| both pass, a | 6 |
| A-only pass, b | 1 |
| B-only pass, c | 4 |
| both fail, d | 1 |
| **Tổng** | **12** |

\[
\mathrm{PassRate}_A=(6+1)/12=58.3\%
\]

\[
\mathrm{PassRate}_B=(6+4)/12=83.3\%
\]

\[
\Delta_\mathrm{paired}=(4-1)/12=+25\ \text{điểm phần trăm}.
\]

B sửa được 4 case, nhưng làm hỏng 1 case A từng đạt. **12 mẫu quá ít** để từ đó tuyên bố một cải thiện chắc chắn trên hệ thống thực; cần xem các case trọng yếu và sự bất định.

## 14. Ghép kết quả bằng Java 21 — tuyệt đối không dựa vào vị trí mảng

Trong evaluation chạy song song, B có thể trả kết quả khác thứ tự A. Ghép `aResults.get(i)` với `bResults.get(i)` sẽ tạo cặp sai nếu hai danh sách không cùng thứ tự hoặc có retry.

Ví dụ một lớp Java **thuần JDK** nhận verdict đã được runner chọn theo retry policy và đếm bốn ô:

~~~java
package com.example.aiquality.comparison;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class PairedQualityComparison {
    private PairedQualityComparison() {}

    public record CaseVerdict(
            String caseId,
            String assessmentStatus,
            Boolean pass) {
        public boolean isEvaluated() {
            return "EVALUATED".equals(assessmentStatus) && pass != null;
        }
    }

    public record Summary(
            int totalCaseIds,
            int pairedEligible,
            int bothPass,
            int baselineOnlyPass,
            int candidateOnlyPass,
            int bothFail,
            int excluded) {

        public double baselinePassRate() {
            return pairedEligible == 0 ? Double.NaN :
                (bothPass + baselineOnlyPass) / (double) pairedEligible;
        }

        public double candidatePassRate() {
            return pairedEligible == 0 ? Double.NaN :
                (bothPass + candidateOnlyPass) / (double) pairedEligible;
        }

        public double delta() {
            return pairedEligible == 0 ? Double.NaN :
                (candidateOnlyPass - baselineOnlyPass) / (double) pairedEligible;
        }

        public double pairedCoverage() {
            return totalCaseIds == 0 ? Double.NaN :
                pairedEligible / (double) totalCaseIds;
        }
    }

    public static Summary compare(
            List<CaseVerdict> baseline,
            List<CaseVerdict> candidate) {

        Map<String, CaseVerdict> a = indexUnique(baseline);
        Map<String, CaseVerdict> b = indexUnique(candidate);

        if (a.isEmpty() || !a.keySet().equals(b.keySet())) {
            throw new IllegalArgumentException(
                "Hai run phải có cùng tập case ID và không được rỗng");
        }

        int bothPass = 0;
        int aOnly = 0;
        int bOnly = 0;
        int bothFail = 0;
        int excluded = 0;

        for (String id : a.keySet()) {
            CaseVerdict av = a.get(id);
            CaseVerdict bv = b.get(id);

            if (!av.isEvaluated() || !bv.isEvaluated()) {
                excluded++;
                continue;
            }

            if (av.pass() && bv.pass()) {
                bothPass++;
            } else if (av.pass()) {
                aOnly++;
            } else if (bv.pass()) {
                bOnly++;
            } else {
                bothFail++;
            }
        }

        int total = a.size();
        return new Summary(
            total, total - excluded,
            bothPass, aOnly, bOnly, bothFail, excluded);
    }

    private static Map<String, CaseVerdict> indexUnique(
            List<CaseVerdict> rows) {
        Map<String, CaseVerdict> index = new LinkedHashMap<>();
        for (CaseVerdict row : rows) {
            if (row == null || row.caseId() == null
                    || row.caseId().isBlank()) {
                throw new IllegalArgumentException("caseId không hợp lệ");
            }
            if (index.putIfAbsent(row.caseId(), row) != null) {
                throw new IllegalArgumentException(
                    "Trùng caseId: " + row.caseId());
            }
        }
        return index;
    }
}
~~~

### Các giả định quan trọng của đoạn code

- `CaseVerdict` là dữ liệu **đã phân loại** từ pipeline thực thi/đánh giá; một generator error có `assessmentStatus="NOT_EVALUATED"` và `pass=null`.
- Hàm tính kết quả cho **một tiêu chí nhị phân đã chọn** (ví dụ fact checking trên RAG cases đủ điều kiện). Khi dataset có tool-only/no-context, phải xác định tập eligible của từng metric **trước khi tính** và công bố mẫu số tương ứng, không tự ép mọi tiêu chí thành một PASS/FAIL chung.
- `indexUnique` từ chối **case trùng**; hàm `compare` từ chối **set case IDs khác nhau**. Không âm thầm bỏ case chỉ vì B không trả về row.
- `excluded` đếm **các cặp có ít nhất một verdict không hợp lệ**, không phải số generator errors riêng của A hoặc B; báo cáo đầy đủ cần thêm breakdown.
- Ví dụ chưa kiểm tra `dataset_revision`, label revision, rubric/judge model. **Preflight** phải thực hiện những kiểm tra đó trước khi gọi hàm.
- `Double.NaN` nghĩa là không thể tính vì mẫu rỗng. Khi xuất JSON, dùng `null` cùng `reason=NO_ELIGIBLE_PAIRS` thay vì ghi `NaN` không hợp lệ trong JSON tiêu chuẩn.
- Nếu một case có nhiều attempts, phải chọn attempt theo **retry policy được version hóa** trước khi gọi `compare`; không lựa kết quả tốt nhất một cách tùy tiện.

## 15. Unit test cho paired comparator

Đoạn kiểm thử JUnit 5 xác minh cách ghép theo ID, kể cả khi B trả results theo thứ tự đảo:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import com.example.aiquality.comparison.PairedQualityComparison;
import com.example.aiquality.comparison.PairedQualityComparison.CaseVerdict;

class PairedQualityComparisonTest {

    private static CaseVerdict row(String id, boolean pass) {
        return new CaseVerdict(id, "EVALUATED", pass);
    }

    @Test
    void joinsByCaseIdNotByArrayPosition() {
        List<CaseVerdict> a = List.of(
            row("case-1", true),
            row("case-2", true),
            row("case-3", false),
            row("case-4", false));

        List<CaseVerdict> b = List.of(
            row("case-4", false),
            row("case-3", true),
            row("case-2", false),
            row("case-1", true));

        var result = PairedQualityComparison.compare(a, b);

        assertEquals(4, result.totalCaseIds());
        assertEquals(4, result.pairedEligible());
        assertEquals(1, result.bothPass());
        assertEquals(1, result.baselineOnlyPass());
        assertEquals(1, result.candidateOnlyPass());
        assertEquals(1, result.bothFail());
        assertEquals(0.0, result.delta(), 0.000001);
    }

    @Test
    void rejectsMissingCaseIds() {
        assertThrows(IllegalArgumentException.class, () ->
            PairedQualityComparison.compare(
                List.of(row("case-1", true), row("case-2", false)),
                List.of(row("case-1", true))));
    }

    @Test
    void doesNotTurnJudgeErrorIntoQualityFail() {
        var result = PairedQualityComparison.compare(
            List.of(
                row("case-1", true),
                new CaseVerdict("case-2", "EVALUATION_ERROR", null)),
            List.of(
                row("case-2", true),
                row("case-1", false)));

        assertEquals(2, result.totalCaseIds());
        assertEquals(1, result.pairedEligible());
        assertEquals(1, result.excluded());
        assertEquals(0.5, result.pairedCoverage(), 0.000001);
    }
}
~~~

Đây là **mã hướng dẫn**, chưa được build hoặc chạy trong phạm vi viết bài. Người học có thể đưa vào project Java 21 có JUnit 5 rồi chạy tests. Nếu dùng JDK khác, điều chỉnh cách viết record hoặc các API phù hợp.

## 16. Đánh giá độ bất định thống kê khi case được ghép cặp

Hai số `b = A-only pass` và `c = B-only pass` là các **discordant pairs** — những cặp mà kết quả A/B khác nhau. Chúng chứa thông tin quan trọng để xem có bằng chứng về thay đổi hướng PASS/FAIL hay không.

Với outcome nhị phân và cặp case độc lập, một phép kiểm định phù hợp là **McNemar's test**. Khi số discordant pairs nhỏ, có thể dùng **exact McNemar** tính từ phân phối nhị thức thay vì xấp xỉ chi-square.

### Ví dụ tính exact p-value

Với bảng 12 case giả lập có `b=1`, `c=4`, số cặp bất đồng `n_d=5`. Dưới giả thuyết hai hướng bất đồng có xác suất ngang nhau, p-value exact hai phía:

\[
p_{\mathrm{exact}}
= 2 \times \frac{\binom{5}{0}+\binom{5}{1}}{2^5}
= 2 \times \frac{1+5}{32}
= 0.375.
\]

Mặc dù candidate có delta **+25 điểm phần trăm**, ví dụ `n=12` cho thấy **chưa đủ bằng chứng mạnh** để chắc chắn candidate tốt hơn trong quần thể câu hỏi thực tế. Kết quả này còn phụ thuộc độ đại diện của dataset và độ ổn định của judge.

**Không nên dùng một p-value duy nhất để quyết định phát hành.** Cần xem kích thước hiệu quả, độ lớn rủi ro hồi quy, confidence interval, false pass, technical errors, chi phí và các trường hợp nghiệp vụ trọng yếu.

### Nếu nhiều case đến từ cùng một tài liệu

McNemar giả định các **cặp giữa những case** tương đối độc lập. Nếu 100 câu đều rút ra từ một chính sách dài, chúng có thể tương quan mạnh. Khi đó:

- Dùng **clustered/stratified resampling** phù hợp theo tài liệu, chủ đề hoặc người đánh giá.
- Không diễn giải 100 câu tương quan như 100 quan sát độc lập hoàn toàn.
- Cân nhắc mở rộng tập tình huống sang nhiều chính sách, nhóm nghiệp vụ và độ khó.

### Khoảng tin cậy cho hiệu quả paired

Một hướng thực tế là **paired bootstrap**:

1. Lấy mẫu lại **các case ID ghép cặp** có hoàn lại.
2. Giữ verdict A và B đi cùng một ID ở mỗi lần lấy mẫu.
3. Tính delta mới cho mỗi mẫu bootstrap.
4. Lấy khoảng phân vị hoặc phương pháp CI thích hợp; nếu có clustering thì resample **theo cụm**.
5. Ghi seed, số lần lặp và chính sách xử lý case lỗi.

Việc bootstrap **riêng từng arm rồi ghép lại** làm mất cấu trúc phụ thuộc trong cặp, không phù hợp mục tiêu paired comparison.

## 17. Báo cáo theo phân nhóm — đừng để trung bình che regression

Một model có thể cải thiện tổng thể nhưng làm giảm chất lượng ở nhóm quan trọng:

| Nhóm tình huống | A pass / eligible | B pass / eligible | Câu hỏi cần điều tra |
|---|---:|---:|---|
| RAG hỏi đáp ngắn | 40/50 | 45/50 | B sửa được những claim nào? |
| RAG context dài | 12/20 | 10/20 | B bị truncation hoặc bỏ sót evidence? |
| Tool calling | 18/20 | 19/20 | Có gọi đúng tool arguments? |
| No-context | 8/10 | 8/10 | Từ chối khi thiếu nguồn có đúng policy? |

Các số **giả lập**; khi lập báo cáo thật cần đưa **paired coverage và số lỗi** theo từng scenario/tag, không chỉ pass rate. Nếu nhóm safety-critical chỉ có vài case, đừng để cải thiện trên hàng trăm câu dễ che mất một regression nghiêm trọng.

Lưu ý nguy cơ **Simpson's paradox**: tổng hợp có thể bị ảnh hưởng bởi tỷ trọng nhóm. Cố định dataset/weights giúp giảm lỗi này, nhưng nếu A/B bị mất verdict trên những case khác nhau thì nhóm paired eligible vẫn có thể không đại diện cho tập gốc.

## 18. Đánh giá retrieval khi so RAG end-to-end

Khi so retriever/reranker/index, lưu **retrieved document IDs** của cả hai arm và ground-truth relevant IDs.

Các metric tiêu biểu:

- **Hit@k:** có ít nhất một relevant document trong top-k.
- **Recall@k:** tỷ lệ relevant documents đã biết có mặt trong top-k.
- **MRR:** nghịch đảo thứ hạng của relevant hit đầu tiên.
- **NDCG@k:** xếp hạng có đánh giá mức độ liên quan, cần labels dạng graded relevance.

### Ví dụ recall@3

Ground truth gồm `["doc-A","doc-B"]`.

- Retriever A trả `["doc-A","doc-C","doc-D"]`.
- Retriever B trả `["doc-A","doc-B","doc-D"]`.

\[
\mathrm{Recall@3}_A=\frac{1}{2}=0.5,\qquad
\mathrm{Recall@3}_B=\frac{2}{2}=1.0.
\]

B tìm đủ nguồn hơn trên case này, **nhưng chưa chứng minh final answer B đúng hơn**: generator có thể vẫn diễn giải sai dữ kiện. Vì thế cần **retrieval metrics và groundedness** độc lập.

Nếu đang so `top-k=5` với `top-k=10`, không gọi `Recall@5` của A và `Recall@10` của B là cùng một metric:

- Nếu muốn đánh giá **ranking quality**, so tại một k cố định.
- Nếu muốn đánh giá **system-level quality**, ghi context thật đã cấp generator, mức k và token budget khác nhau, rồi so answer và chi phí.
- Nếu ground-truth source IDs không tồn tại, `Recall@k` là **NOT_APPLICABLE**, không tự suy từ answer của LLM.

## 19. So sánh hành vi tool calling

Đối với tool workflow, quality có nhiều lớp:

| Lớp | Phép đo | Cần judge? |
|---|---|---|
| Tool selection | Đúng tên tool cần gọi | Không, so bằng code |
| Argument validity | JSON/schema/types/values chính xác | Không |
| Sequence | Đúng số lượt/thứ tự tool khi bắt buộc | Không |
| Execution | Tool trả success/timeout/5xx | Không, là trạng thái kỹ thuật |
| Output use | Answer phản ánh đúng tool result | Judge/rule/human review |
| Business side effects | Không thực thi thay đổi trái phép | Policy/authorization assertions |

Một tool có thể trả HTTP 200 và assistant vẫn gọi **sai order ID**. Không cho verdict cuối “PASS” che một tool misuse có rủi ro. Với tool lỗi thực sự, ghi `TOOL_ERROR` hoặc trạng thái tương ứng trong execution; không coi backend timeout là câu trả lời sai về mặt ngữ nghĩa.

## 20. So latency, token và cost một cách nhất quán

Chất lượng có thể tăng nhưng với chi phí không chấp nhận được. Cần đo **cùng định nghĩa** ở cả A và B:

| Tín hiệu | Điều cần cố định hoặc ghi lại |
|---|---|
| User-facing latency | Đo từ request đến answer, không cộng judge offline |
| Evaluation latency | Bao gồm retrieval, generation, judging, report write |
| Generator p50/p95 | Cùng loại request, warmup, concurrency và cửa sổ đo |
| Vector latency | Top-k/index version, filter và embedding config |
| Tool latency | Sandbox/provider state, retry/timeout policy |
| Token usage | Input/output, cached/reasoning usage khi có, retries |
| Cost | Model ID, rate card, currency, ngày và token categories |

### Đơn giá trên một triệu token

\[
C_{\mathrm{model}}
=\frac{T_{\mathrm{input}}}{10^6}P_{\mathrm{input}}
+\frac{T_{\mathrm{output}}}{10^6}P_{\mathrm{output}}.
\]

\[
C_{\mathrm{case}}
=C_{\mathrm{generator}}+C_{\mathrm{judge,relevance}}
+C_{\mathrm{judge,factuality}}+C_{\mathrm{embedding/retrieval/tool}}.
\]

**Spring AI BOM không lưu bảng giá model.** Provider có thể thay giá hoặc có cached/reasoning tokens, batch discount; cần ghi giá áp dụng theo ngày và model. Nếu usage thiếu, ghi `USAGE_MISSING`, **không đặt cost bằng 0**.

Khi so A/B chạy ở hai thời điểm khác nhau:

- **Actual cost:** theo giá thật thời điểm mỗi run, phản ánh billing.
- **Normalized cost:** có thể tính lại với **cùng rate card** để so hiệu quả token/call. Phải ghi rõ hai số này không cùng ý nghĩa.

### Độ trễ paired và p95

Với mỗi case có timing A/B hợp lệ:

\[
\Delta t_i=t_{B,i}-t_{A,i}.
\]

Có thể phân tích **median/mean paired delta**, tỷ lệ B chậm hơn và latency distribution mỗi arm. Cần nhớ:

\[
p95(t_B)-p95(t_A)\ne p95(t_B-t_A)
\]

trong trường hợp tổng quát. Đừng gọi trung bình hoặc maximum là p95. Với Prometheus muốn ước lượng p95 từ histogram phải có **buckets** và đủ số mẫu.

## 21. Kết hợp Spring AI Observability với dữ liệu thí nghiệm

Spring AI ghi nhận nhiều observation khi các thành phần thực sự được gọi:

| Observation/metric logic | Gợi ý điều tra |
|---|---|
| `spring.ai.chat.client` | Duration toàn ChatClient/advisors |
| `spring.ai.advisor` | Thời gian các advisors |
| `gen_ai.client.operation` | Thời gian gọi ChatModel/EmbeddingModel |
| `gen_ai.client.token.usage` | Token usage provider trả về |
| `db.vector.client.operation` | Query/add/upsert/delete trên VectorStore |
| `spring.ai.tool` | Tool execution, status/exception |
| `app.ai.evaluation.case` (tự định nghĩa) | Thời gian một case chạy trong evaluator |

Tên observation logic có thể được chuẩn hóa sang time series Prometheus có dấu gạch dưới và hậu tố như `_seconds_count`, `_total`. Không giả định metric xuất hiện khi chưa có operation tương ứng.

### Tách generator và judge

Hai vai trò có thể dùng cùng model ID. Khi đó chỉ lọc theo model không biết được lời gọi nào dùng sinh câu trả lời hay đánh giá. Thêm **role** có tập giá trị giới hạn: `generator`, `judge_relevance`, `judge_fact` và `embedding`.

- **Metric labels hợp lý:** `environment`, `arm` (A/B), `scenario`, `role`, `outcome` enum.
- **Không dùng metric labels:** `case_id`, `run_id`, user ID, prompt, toàn văn tài liệu hoặc tool args.
- **Report store:** ghi run/case IDs, trace reference đã được phép, timestamps và artifact digests.
- **Tracing:** giúp tìm critical path nhưng có sampling và retention; không dùng trace thay run manifest.

### Một truy vấn mean model latency

~~~promql
sum by (gen_ai_request_model) (
  rate(gen_ai_client_operation_seconds_sum[5m])
)
/
sum by (gen_ai_request_model) (
  rate(gen_ai_client_operation_seconds_count[5m])
)
~~~

Đây là **mean latency**, không phải p95. Nếu cùng model ID phục vụ cả A và B, Spring AI metric gốc **không tự có nhãn arm**; dùng observation/report tùy biến hoặc resource-level separation để phân tích đúng hai arm.

## 22. Chẩn đoán hồi quy bằng cặp case và trace

| Triệu chứng | Nghi vấn | Bằng chứng cần xem |
|---|---|---|
| B thiếu nguồn đúng, recall@k giảm | Retrieval/filter/chunking/index | Retrieved IDs, index revision, vector spans |
| Context giống nhau, B bịa số liệu | Generator prompt/model | Rendered prompt, answer, frozen evidence |
| Answer đúng nhưng tool args sai | Tool selection/contract | Tool recorder, expected vs actual arguments |
| Answer A/B giống, judge verdict khác | Judge variance/rubric drift | Judge versions, rubric, calibration |
| B có nhiều `GENERATION_ERROR` | Provider/quota/timeout | Model HTTP traces, retries, error codes |
| B có nhiều `EVALUATION_ERROR` | Judge/parser/format lỗi | Judge traces, verdict schema và coverage |
| Input tokens B tăng | Top-k/prompt/context dài | Context snapshot và usage |
| p95 B tăng nhưng tokens tương đương | Network/DB/provider/tool/concurrency | Trace critical path và warmup |
| Chi phí B tăng dù tokens không tăng | Rate card/model tier/cache khác | Pricing revision và request categories |

Để điều tra, giữ **câu hỏi, answer A/B, evidence từng arm, tool log được phép, verdict và trace reference** của cặp bị thay đổi. Một báo cáo chỉ chứa `caseId` và `FAIL` không đủ để tìm nguyên nhân.

## 23. Quality gate và quyết định phát hành

Thiết kế trước:

1. **Primary metric**: đo đúng giả thuyết (ví dụ paired fact-check delta).
2. **Guardrails**: relevance, tool correctness, coverage, error rate, latency, cost.
3. **Minimum sample/coverage**: yêu cầu đủ cặp hợp lệ và độ đại diện của dataset.
4. **Decision rules**: `PROMOTE`, `REJECT`, `INCONCLUSIVE`, `BLOCKED`.
5. **Human review**: ca an toàn, critical workflows hoặc judge bất đồng.

Ví dụ quality gate:

~~~yaml
quality_gate:
  revision: "paired-gate-v2"
  primary_metric: "paired_fact_check_delta_pp"
  minimum_paired_coverage: 0.98
  minimum_fact_check_delta_pp: 2.0
  maximum_relevance_regression_pp: 1.0
  maximum_generation_error_rate: 0.02
  maximum_evaluation_error_rate: 0.01
  maximum_generator_p95_latency_ratio: 1.20
  maximum_mean_cost_per_case_ratio: 1.15
  human_review_required_for:
    - "safety_critical_regression"
    - "new_tool_permissions"
~~~

Đây là **ngưỡng minh họa**, không phải mặc định của Spring AI. Trong sản phẩm thực, cần xuất phát từ mức rủi ro, baseline, chi phí, khả năng của judge và yêu cầu kinh doanh.

| Trường hợp | Quyết định phù hợp |
|---|---|
| Chất lượng cải thiện, coverage cao, mọi guardrail đạt | Có thể `PROMOTE` sau review |
| Chất lượng tăng nhưng tool permissions sai nghiêm trọng | `REJECT/BLOCKED` |
| Nhiều case judge timeout, kết luận không ổn định | `BLOCKED/INCONCLUSIVE` |
| Delta giảm rõ và có regression quan trọng | `REJECT`/điều tra |
| Delta nhỏ, confidence interval rộng | `INCONCLUSIVE`, bổ sung mẫu/lặp lại |

Không **đổi ngưỡng sau khi thấy kết quả** rồi tuyên bố đó là kế hoạch đăng ký trước. Nếu cần điều chỉnh ngưỡng, tạo policy revision và giải thích thay đổi.

## 24. Bảo vệ dữ liệu và ngăn thiên lệch do judge

LLM-as-a-Judge có thể ưu tiên câu dài (verbosity bias), câu trả lời của cùng họ model (self-preference), câu xuất hiện trước trong pairwise prompt (position bias), hoặc bị chỉ dẫn giả trong context làm sai lệch.

Quy trình giảm rủi ro:

1. Có bộ **human-labeled calibration** gồm case đúng, sai, paraphrase đúng, thiếu nguồn và prompt injection.
2. Theo dõi judge/human agreement, false pass và false fail.
3. Khi so A/B, **giữ judge/rubric cố định**; nếu thay judge thì tái chấm cả hai trên recorded answers/evidence.
4. Với pairwise judge, che nhãn A/B và hoán đổi thứ tự answers.
5. Cho người rà soát ca **A-only/B-only** thuộc nhóm nghiệp vụ quan trọng.

Không gửi secrets, dữ liệu cá nhân, raw prompt/context nhạy cảm đến provider judge nếu chưa có quyền sử dụng. Snapshot được lưu phải có access controls, encryption/retention và quy trình audit phù hợp.

**Hash không đồng nghĩa ẩn danh:** đối với nội dung ngắn hoặc có thể đoán, checksum công khai có thể bị thử dictionary. Cân nhắc lưu reference ở nơi bảo vệ hoặc HMAC có khóa quản lý tách biệt thay vì đăng raw hash của dữ liệu nhạy cảm.

## 25. CI và quy trình chạy nhiều tầng

| Tầng | Khi nào | Mục tiêu |
|---|---|---|
| Unit tests | Mọi PR | Loader, join ID, duplicate/missing, paired summary |
| Offline component tests | Mọi PR | Fake generator/retriever/tool, snapshot/evaluator contract |
| Live smoke | CI được cấp quyền/manual | Kết nối provider, metrics/traces, quota thấp |
| Nightly paired regression | Theo lịch | Dataset có version, A/B hoặc baseline/current, judge cố định |
| Release/canary comparison | Trước triển khai | Quality gate + cost/latency + human review |

**Preflight bắt buộc**:

~~~text
validate(dataset_sha256_a == dataset_sha256_b)
validate(case_ids_a == case_ids_b)
validate(label_revision_a == label_revision_b)
validate(judge_model_a == judge_model_b)
validate(rubric_and_scoring_policy_a == rubric_and_scoring_policy_b)
validate(environment_and_tool_sandbox_allowed)
validate(actual_manifest_diff == intended_changes)
validate(no_duplicate_case_ids)
run_or_load_case_attempts()
resolve_retry_policy_then_pair_by_case_id()
compute_paired_summary_and_coverage()
compare_primary_metric_and_guardrails()
persist_report_and_review()
~~~

Với thử nghiệm retriever, **không** kiểm `context_sha_A == context_sha_B` như điều kiện bắt buộc vì context thay đổi là biến đang đo. Hãy kiểm corpus/labels/index hoặc các biến cần cố định **theo thiết kế**.

### Ranh giới tài nguyên

Live tests cần provider **test/staging credentials**, ngân sách, timeout và retry giới hạn. Tool side effects phải sandbox/mock. Không cho CI tự truy cập production corpus chỉ vì tên profile đã được đặt là `test`; quyền thực tế phải do IAM, network policy và database grants ngăn chặn.

## 26. Bài thực hành có hướng dẫn

### Phần A — Đọc bảng paired

Tạo 12 case giả lập:

1. **6 both pass**, **1 A-only**, **4 B-only**, **1 both fail**.
2. Đảo thứ tự kết quả B trước khi ghép.
3. Chạy comparator trong project test của người học.
4. Xác nhận `7/12`, `10/12`, delta `+25 pp`.
5. Liệt kê IDs của **4 case cải thiện** và **1 case hồi quy**.

**Tiêu chí đạt:** ghép đúng theo ID, không phụ thuộc thứ tự mảng; giải thích được tại sao 12 mẫu chưa đủ kết luận chắc chắn.

### Phần B — Bổ sung một judge error

Cho một case B có `assessmentStatus=EVALUATION_ERROR` và `pass=null`, giữ A không đổi:

- Paired eligible giảm từ 12 xuống **11**.
- Paired coverage còn **11/12**.
- Báo ID bị loại cùng nguyên nhân; không điền `FAIL`.
- Tính lại delta trên 11 cặp, đồng thời công bố tỷ lệ lỗi judge B.

**Tiêu chí đạt:** việc một backend judge lỗi không tự làm generator trở nên kém chất lượng.

### Phần C — Prompt A/B trên frozen context

1. Chuẩn bị 20–30 case RAG có nhãn và context snapshot được phép dùng.
2. Giữ model, context, dataset, judge/rubric và token settings không đổi.
3. Chỉ thay `answer-v3` sang `answer-v4`.
4. Chấm relevance và fact checking, lưu paired results.
5. So token, estimated cost, latency và error rates.
6. Kiểm tra thủ công các case B-only/A-only quan trọng.

### Phần D — Retriever A/B end-to-end

1. Dùng cùng corpus snapshot và ground-truth document IDs.
2. Để A/B truy xuất context riêng; lưu IDs, context hashes và top-k.
3. Tính retrieval recall@k với cùng định nghĩa.
4. Sinh answers theo context từng arm; judge dùng đúng evidence của arm ấy.
5. Giải thích một case mà B tìm tài liệu tốt hơn nhưng answer vẫn fail.

### Phần E — Tool calling + cost guardrail

Dùng 10 case sandbox với `getOrderStatus`, invalid args và timeout. Chấm tool selection/arguments bằng code, answer quality bằng judge, ghi token/cost của generator **riêng** judge và quyết định theo guardrail có version.

### Câu hỏi tự kiểm tra

1. Vì sao hai run có cùng số lượng 100 câu chưa chắc so sánh được?
2. Khi so prompt, cần làm gì với retrieved context?
3. Khi so reranker, có nên buộc B dùng context A không?
4. `A-only pass` và `B-only pass` cung cấp thông tin gì?
5. Vì sao `EVALUATION_ERROR` không phải là answer `FAIL`?
6. Nếu A có 95 verdict, B có 90 và đồng thời hợp lệ 87 trên 100 case, paired coverage bằng bao nhiêu?
7. Vì sao `p95_B - p95_A` không luôn bằng p95 của paired latency delta?
8. McNemar được dùng cho loại dữ liệu nào?
9. Phải làm gì khi judge thay đổi giữa baseline và candidate?
10. Những thuộc tính nào không nên làm metric labels?

**Gợi ý:** (1) có thể khác IDs/labels; (2) frozen evidence; (3) không khi retriever là biến cần đo; (4) case hồi quy/cải thiện; (5) lỗi phép đo; (6) 87%; (7) phân vị của hiệu khác hiệu của phân vị; (8) binary paired outcomes; (9) tái chấm cả hai bằng cùng judge/rubric; (10) `run_id`, `case_id`, prompt, user ID, raw context.

## 27. Checklist trước khi công bố một so sánh

- [ ] Có giả thuyết, primary metric và guardrails định nghĩa trước.
- [ ] Dataset ID/revision/digest, labels và case IDs hoàn toàn trùng giữa A/B.
- [ ] Không có case ID trùng, thiếu hoặc thay nội dung mà không đổi revision.
- [ ] Manifest ghi rõ biến chủ đích, những biến cố định và trường khác biệt ngoài ý muốn.
- [ ] Frozen-context hay end-to-end được chọn theo đúng câu hỏi nghiên cứu.
- [ ] Với RAG, judge chấm bằng **evidence thật của mỗi generator**.
- [ ] Với tools, có deterministic assertions và sandbox fixtures/schema revisions.
- [ ] Judge model/rubric/thresholds/calibration được cố định; lỗi judge không bị coi là FAIL.
- [ ] Có bảng bốn ô both pass / A-only / B-only / both fail.
- [ ] Có coverage mỗi arm, paired coverage, generation/evaluation error rates.
- [ ] Chênh lệch được diễn giải bằng **điểm phần trăm**, có mẫu số rõ ràng.
- [ ] Phân tích uncertainty có tính đến paired cases và clustering khi phù hợp.
- [ ] Báo theo scenario, tags, mức độ nghiêm trọng và danh sách case hồi quy.
- [ ] So retrieval recall, tool correctness, latency, token/cost và trace đúng quy ước.
- [ ] Các tính toán cost ghi đơn giá, model, ngày và tình trạng usage.
- [ ] Không chứa secrets, user IDs hoặc raw prompt/context trong metric labels.
- [ ] Run manifests, case snapshots, evidence và quality gate được version hóa.
- [ ] Kết luận PROMOTE/REJECT/INCONCLUSIVE/BLOCKED có bằng chứng và review phù hợp.

## Tài liệu tham khảo

1. [Spring AI — Evaluators (2.1)](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/evaluation/evaluators.html): `RelevancyEvaluator`, `FactCheckingEvaluator`, `EvaluationRequest`.
2. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): observations của ChatClient, ChatModel, VectorStore và tool.
3. [Spring AI — Metrics Reference (2.1)](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/observability/metrics.html): token usage, latency, Prometheus metrics.
4. [Spring AI — RAG](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html): pipeline truy xuất và evidence.
5. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) và [Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer và OpenTelemetry.
6. [NIST Engineering Statistics Handbook](https://www.itl.nist.gov/div898/handbook/): thiết kế thí nghiệm, so sánh và độ bất định.
7. [SciPy — Exact Binomial Test](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html): tham khảo tính McNemar exact từ số discordant pairs.
8. [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): percentiles và histogram metrics.
9. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ secrets, PII trong logs/telemetry.

> **Ghi nhớ:** So sánh Spring AI công bằng không bắt đầu từ hai tỷ lệ PASS mà từ **cùng dataset, cùng định nghĩa phép chấm và ghép cặp theo case ID**. Hãy phân tích những case candidate sửa được hoặc làm hỏng, công bố coverage và lỗi, rồi đối chiếu retrieval, tool behavior, traces, tokens, chi phí và latency trước khi kết luận prompt, model hay pipeline mới thực sự tốt hơn.
