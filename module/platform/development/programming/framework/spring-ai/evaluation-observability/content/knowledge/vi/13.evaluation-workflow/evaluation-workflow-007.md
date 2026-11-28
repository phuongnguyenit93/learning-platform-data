# Đưa tiêu chí kiểm tra hồi quy vào CI/CD

Một thay đổi nhỏ trong prompt Spring AI có thể làm câu trả lời tự nhiên hơn nhưng khiến model bỏ qua một nguồn RAG quan trọng. Một lần nâng model có thể cải thiện relevance nhưng làm sai cách gọi tool. Một bản cập nhật corpus có thể khiến retriever lấy tài liệu hết hiệu lực. Nếu nhóm chỉ kiểm tra ứng dụng khởi động được và unit tests truyền qua, những hồi quy chất lượng này có thể đến production mà không ai nhận ra.

Đưa **regression evaluation** vào CI/CD giúp mỗi thay đổi được kiểm tra bằng một tập tình huống đã xác nhận trước khi phát hành. Pipeline có thể chạy kiểm tra xác định cho schema, retrieval IDs và tool contracts; chạy evaluator cho relevance, groundedness và factual correctness; so kết quả với baseline đã duyệt; đồng thời kiểm tra technical completion, latency, token và chi phí.

Trong module **SPRING_AI_EVALUATION_OBSERVABILITY**, nội dung này kết nối đánh giá chất lượng ứng dụng Spring AI với quy trình phát triển phần mềm: dataset, rubric, prompt/model/pipeline versions, RAG/tool tests, metrics và traces. Mục tiêu không phải biến mọi thay đổi thành một batch LLM tốn kém, mà thiết kế các lớp kiểm tra có tốc độ và độ sâu phù hợp với từng giai đoạn phát hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích regression evaluation khác unit test, integration test và kiểm thử thủ công như thế nào.
2. Chọn các lớp kiểm tra phù hợp cho pull request, nightly build, pre-release và sau triển khai.
3. Quản lý dataset, reference facts, prompt, model, corpus/index, tool fixtures và rubric theo phiên bản.
4. Kết hợp assertion xác định với evaluator ngữ nghĩa và human review.
5. Thiết kế CI gate cho relevance, groundedness, factual correctness, retrieval và tool calling.
6. Phân biệt quality regression, technical error, evaluator failure, skip và dữ liệu chưa đủ để kết luận.
7. So sánh candidate với verified baseline theo từng case và metric.
8. Kiểm soát độ dao động của model, quota, concurrency, thời gian và chi phí trong pipeline.
9. Xuất report cùng artifacts để developer tìm được ca hồi quy và trace liên quan.
10. Đưa tiêu chí critical vào release gate và tiếp tục quan sát sau khi deploy.

## 2. Regression evaluation giải quyết vấn đề gì?

**Regression** xảy ra khi một thay đổi làm hành vi vốn đáp ứng yêu cầu trở nên kém hơn. Với AI, hồi quy không chỉ là chương trình crash hoặc API trả sai schema. Một câu trả lời vẫn có thể mạch lạc, đúng ngữ pháp và HTTP 200 nhưng sai dữ kiện, thiếu nguồn hoặc gọi tool sai.

Ví dụ ứng dụng *Sao Mai* (dữ liệu giả định) dùng Spring AI để trả lời chính sách hoàn phí. Tài liệu hiện hành `policy-v3#refund-pro` quy định gói Pro có thời hạn yêu cầu hoàn phí **14 ngày kể từ ngày mua**.

Trước khi thay prompt, test `REFUND-001` trả lời đúng 14 ngày và dẫn nguồn. Sau thay đổi, model trả lời 30 ngày vì context có tài liệu cũ `policy-v2`. Smoke test HTTP vẫn xanh, nhưng factual correctness đã hồi quy.

| Thay đổi | Hồi quy có thể xảy ra | Kiểm tra cần có |
| --- | --- | --- |
| Sửa prompt | Model bỏ qua điều kiện hoặc nguồn | Relevance, groundedness, factual correctness |
| Nâng model/provider | Output format, tool selection hoặc độ ổn định đổi | Semantic eval, schema/tool contract |
| Đổi embedding model | Retrieval ranking thay đổi | Retrieval hit@k, RAG quality |
| Rebuild index/corpus | Tài liệu cũ hoặc thiếu xuất hiện | Source freshness, retrieval regression |
| Sửa tool schema | Model truyền sai args hoặc không gọi tool | Tool selection/arguments/authorization |
| Đổi memory/advisor | Context giữa các lượt bị trộn | Multi-turn isolation và answer quality |
| Thay evaluator/rubric | Điểm thay đổi dù answer không đổi | Judge calibration và chấm lại cùng evidence |

**Regression evaluation không thay thế test phần mềm thông thường.** Nó bổ sung lớp kiểm tra chất lượng hành vi do model, dữ liệu và pipeline tạo ra.

## 3. Đặt regression evaluation ở đâu trong CI/CD?

Không phải mọi commit đều cần chạy toàn bộ dataset và nhiều lần gọi LLM. Một pipeline hiệu quả chia kiểm tra thành nhiều lớp theo thời gian, chi phí và mức rủi ro.

~~~mermaid
flowchart TD
    A["Pull request / commit"] --> B["Static checks + build + unit tests"]
    B --> C["Deterministic AI contract tests"]
    C --> D["Small semantic smoke dataset"]
    D --> E{"PR gates pass?"}
    E -- "Không" --> F["Block merge + report"]
    E -- "Có" --> G["Merge / build candidate"]
    G --> H["Nightly full regression"]
    H --> I["Baseline comparison + slices"]
    I --> J["Pre-release quality / ops gates"]
    J --> K{"Approved?"}
    K -- "Không" --> F
    K -- "Có" --> L["Deploy canary"]
    L --> M["Production metrics + sampled review"]
    M --> N["Verified incidents → regression dataset"]
~~~

### 3.1. Bốn thời điểm kiểm tra

| Thời điểm | Phạm vi | Mục tiêu |
| --- | --- | --- |
| **Pull request** | Unit/contract tests, một tập AI smoke nhỏ, ca critical liên quan thay đổi | Phản hồi nhanh cho developer |
| **Nightly hoặc scheduled** | Dataset regression đầy đủ, chạy lặp ca nhạy cảm, nhóm RAG/tool/memory | Phát hiện hồi quy rộng và biến thiên |
| **Pre-release** | Candidate run so với verified baseline, quality + operational gates | Quyết định phát hành |
| **Post-deploy/canary** | Metrics/traces production và mẫu được review | Phát hiện drift và lỗi ngoài offline dataset |

Một thay đổi chỉ chạm UI không nhất thiết cần chạy toàn bộ LLM dataset. Một thay đổi embedding, chunking, prompt RAG hoặc tool routing nên kích hoạt các suite tương ứng. Dùng mapping giữa file/component thay đổi và bộ test để chọn phạm vi, nhưng vẫn chạy full regression theo lịch và trước release quan trọng.

### 3.2. PR smoke không đại diện toàn bộ chất lượng

Một bộ smoke 10–20 ca có thể phát hiện lỗi hiển nhiên nhanh chóng, nhưng không đủ chứng minh chất lượng toàn hệ thống. Report phải ghi rõ `suite=pr-smoke` và sample size. Không lấy pass rate của smoke suite để thay cho kết quả full dataset.

## 4. Xây một bộ regression dataset đáng tin

CI chỉ kiểm được điều nhóm đã mô tả. Dataset kém chất lượng hoặc thiếu trường hợp quan trọng sẽ tạo ra một pipeline xanh nhưng sản phẩm vẫn sai.

Một test case cần có:

- `caseId` ổn định.
- Input/question và ngữ cảnh đầu vào được kiểm soát.
- Reference facts hoặc expected behavior đã xác minh.
- Reference document IDs khi đánh giá RAG.
- Expected tool behavior khi đánh giá tool calling.
- Metric/rubric áp dụng và severity.
- Tags để chọn suite, ví dụ `rag`, `policy`, `tool`, `multi-turn`, `critical`.
- Nguồn nhãn, ngày hiệu lực và dataset version.

Ví dụ:

~~~json
{
  "caseId": "REFUND-001",
  "question": "Gói Pro được hoàn phí trong bao lâu?",
  "referenceFacts": [
    "Thời hạn yêu cầu hoàn phí là 14 ngày kể từ ngày mua"
  ],
  "referenceDocumentIds": ["policy-v3#refund-pro"],
  "expectedRetrievalIds": ["policy-v3#refund-pro"],
  "forbiddenClaims": ["Thời hạn 30 ngày"],
  "requiredMetrics": [
    "relevance",
    "groundedness",
    "factualCorrectness",
    "retrievalHitAtK"
  ],
  "severity": "CRITICAL",
  "tags": ["rag", "policy", "vi"]
}
~~~

Đây là record giả định. Trong dữ liệu thật, reference facts phải đến từ nguồn có thẩm quyền, được người phụ trách nghiệp vụ xác nhận và gắn thời điểm hiệu lực.

### 4.1. Chia dataset theo mục đích

| Bộ dữ liệu | Dùng ở đâu | Đặc điểm |
| --- | --- | --- |
| **PR smoke** | Mỗi pull request | Nhỏ, ổn định, bao phủ các hành vi trọng yếu |
| **Critical regression** | PR liên quan và pre-release | Ca quyền, dữ kiện, side effect hoặc rủi ro cao |
| **Full regression** | Nightly/pre-release | Bao phủ rộng các nhóm chức năng |
| **Adversarial/edge cases** | Nightly hoặc scheduled | Thiếu nguồn, mâu thuẫn, prompt injection, câu hỏi đa điều kiện |
| **Production-derived** | Scheduled sau review | Ca thật đã ẩn danh, nhãn được xác minh |
| **Performance/load suite** | Pipeline riêng | Đo latency, throughput, quota và cost dưới tải |

### 4.2. Dataset phải có version và snapshot

Không sửa expected facts trực tiếp trong một version đã dùng làm baseline. Khi chính sách thay đổi từ 14 lên 21 ngày, tạo dataset version mới và review nhãn. Nếu sửa nhãn âm thầm, một phép so baseline/candidate sẽ không còn cùng chuẩn sự thật.

Lưu `datasetVersion`, snapshot/content digest, số case, nguồn reference và quy tắc lấy mẫu. Nếu lấy case production, cần kiểm soát dữ liệu cá nhân, bản quyền và quyền sử dụng.

### 4.3. Tránh leakage giữa dữ liệu phát triển và kiểm định

Không dùng toàn bộ held-out regression set để liên tục điều chỉnh prompt cho đến khi model ghi nhớ từng câu. Có thể duy trì:

- Bộ development dùng để tinh chỉnh.
- Bộ regression/held-out có quyền truy cập hạn chế hơn.
- Bộ production-derived mới được review và đưa vào theo quy trình.

Tách theo hội thoại hoặc nguồn tài liệu khi các câu có liên quan mạnh, tránh để các biến thể gần như trùng nhau làm kết quả có vẻ tốt hơn thực tế.

## 5. Phiên bản hóa mọi thứ ảnh hưởng kết quả

Một run CI cần manifest xác định rõ candidate được kiểm thử. Tối thiểu ghi:

~~~yaml
run:
  runId: pr-4821-ai-regression
  suite: pr-smoke
  commitId: "commit-sha"
  buildId: "build-2481"
  environment: ci

dataset:
  id: support-regression
  version: v5
  snapshotRef: artifacts/datasets/support-regression/v5

application:
  springAiVersion: "resolved-project-version"
  promptVersion: support-prompt-v7
  modelProvider: example-provider
  requestedModelId: chat-model-stable
  pipelineVersion: rag-v4

rag:
  corpusVersion: policy-v3
  indexSnapshot: policy-index-v3
  embeddingModel: embedding-v2
  retrievalTopK: 5
  chunkingVersion: chunker-v3

evaluation:
  rubricVersion: support-rubric-v3
  judgeVersion: judge-v2

execution:
  maxInFlightCases: 3
  maxAttempts: 2
  perCallTimeoutMs: 20000
~~~

Schema minh họa do nhóm thiết kế. Các giá trị phải được resolve từ cấu hình thực tế; alias model có thể thay đổi phía provider nên ghi giới hạn revision nếu không pin được.

### 5.1. Prompt version không chỉ là tên template

Advisor chain, memory policy, query rewrite, context assembly và truncation đều có thể thay đổi prompt thực tế. Lưu template version/digest cùng các cấu hình này; ở attempt lưu retrieved documents và effective context refs khi được phép.

### 5.2. Model và judge là hai phiên bản khác nhau

Lưu provider/model/options cho generation; lưu riêng judge model/prompt/rubric cho evaluator. Nếu judge đổi, kết quả chấm có thể đổi dù output ứng dụng không đổi.

### 5.3. RAG và tool fixtures phải tái lập được

Với RAG, pin corpus/index snapshot, embedding, chunking, filter và retrieval settings. Với tool, dùng sandbox/test doubles và fixture version; kiểm quyền backend và hậu điều kiện. Không gọi tool production có tác dụng phụ trong CI.

## 6. Kết hợp kiểm tra xác định và evaluator ngữ nghĩa

Một CI suite tốt dùng loại kiểm tra phù hợp với câu hỏi.

| Kiểu kiểm tra | Ví dụ | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **Static/config validation** | Prompt template tồn tại, schema hợp lệ | Nhanh, xác định | Không biết answer có đúng |
| **Deterministic assertions** | Document ID, tool name/args, JSON schema | Ổn định, dễ debug | Không chấm được ngữ nghĩa tự do |
| **Integration tests** | VectorStore, tool sandbox, ChatClient wiring | Kiểm đường đi thật | Chậm hơn, cần môi trường |
| **LLM evaluator** | Relevance, groundedness, factual support | Đánh giá ngữ nghĩa linh hoạt | Có chi phí và độ biến thiên |
| **Human review** | Ca critical, judge disagreement | Có phán đoán nghiệp vụ | Tốn thời gian, khó mở rộng |

### 6.1. Dùng assertion khi câu trả lời có điều kiện chính xác

Nếu tool bắt buộc phải là `getOrderStatus` và `orderId` là `DH-123`, kiểm trực tiếp tool events. Không cần LLM judge để xác định tên tool hoặc ID có khớp hay không.

Nếu reference document bắt buộc phải xuất hiện trong top-k, dùng hit@k. Nếu output bắt buộc là JSON schema, dùng validator xác định.

### 6.2. Dùng evaluator cho tiêu chí ngữ nghĩa

Spring AI có các abstraction `Evaluator`, `EvaluationRequest`, `EvaluationResponse` và evaluator như `RelevancyEvaluator`, `FactCheckingEvaluator` tùy phiên bản. Có thể dùng chúng cho relevance và mức độ câu trả lời được context hỗ trợ.

Ví dụ khái niệm:

~~~java
EvaluationRequest request = new EvaluationRequest(
        question,
        effectiveDocuments,
        actualAnswer);

EvaluationResponse result = evaluator.evaluate(request);

boolean passed = result.isPass();
String feedback = result.getFeedback();
~~~

Đây là minh họa API, không phải cấu hình bean hoàn chỉnh. Kiểm tra constructor/configuration theo phiên bản Spring AI trong dự án. Quan trọng nhất: `effectiveDocuments` phải là ngữ cảnh model thực sự nhận. Dùng reference documents thay cho actual context sẽ che lỗi retrieval.

### 6.3. Không để LLM judge tự quyết mọi gate

Judge có thể nhầm, thiên lệch hoặc thay đổi theo model/prompt. Những điều như authorization, tool arguments, required document IDs, schema và latency budget nên được kiểm bằng logic xác định hoặc backend assertions.

Với factual correctness quan trọng, dùng reference facts đã xác minh, rubric rõ, judge đã hiệu chỉnh và human review cho các ca rủi ro cao. Một evaluator PASS không thay thế kiểm soát quyền hay xác minh giao dịch.

## 7. Thiết kế bộ test theo tầng trong pull request

Một PR pipeline nên tối ưu thời gian phản hồi nhưng vẫn chặn những lỗi có thể phát hiện rẻ.

### 7.1. Tầng 1 — Build và unit tests

- Compile ứng dụng và kiểm dependency.
- Test các hàm xử lý dữ liệu, routing, mapping và parser.
- Kiểm prompt/config schema và điều kiện bắt buộc.
- Kiểm logic aggregation, status và release gate.
- Không gọi model thật nếu test không cần.

### 7.2. Tầng 2 — Deterministic AI contract tests

- Required RAG document ID có trong top-k.
- Filter không trả tài liệu ngoài phạm vi.
- Tool được chọn đúng và arguments đúng schema.
- User không có quyền bị từ chối tại backend.
- JSON response hợp lệ.
- Memory/session ID được cô lập giữa các case.

Có thể dùng fake model, stub vector store và tool sandbox để giữ tính ổn định.

### 7.3. Tầng 3 — Semantic smoke tests

Chọn một tập nhỏ có đại diện:

- Một ca factual critical.
- Một ca thiếu nguồn phải từ chối suy đoán.
- Một ca RAG có tài liệu cũ/mới.
- Một ca tool calling.
- Một ca hội thoại nhiều lượt.
- Một ca citation/format.

Giữ số lượng nhỏ để phản hồi PR nhanh; chạy full suite ở nightly và pre-release. Nếu smoke cần gọi provider thật, dùng quota riêng và concurrency thấp.

### 7.4. PR phải báo đúng phạm vi đã chạy

Không ghi “AI regression passed” nếu chỉ chạy 8 case smoke. Ghi `suiteName`, dataset version, selected/completed/evaluated counts, các metric được kiểm và danh sách case bị skip/NOT_EVALUATED.

## 8. Nightly và pre-release: full regression và repeated runs

Nightly có thể chạy toàn bộ dataset, chia theo nhóm RAG/tool/memory/locale, kiểm tra cả metric và vận hành.

Với các case nhạy cảm có độ biến thiên cao, chạy lặp một số lần. Không chọn kết quả tốt nhất; lưu từng attempt và tính tần suất PASS/FAIL hoặc khoảng bất định theo policy.

Trước release:

1. Xác minh baseline đã được duyệt.
2. Kiểm tra candidate manifest tương thích với dataset/rubric.
3. Chạy full regression hoặc suite đủ điều kiện phát hành.
4. So per-case transitions và critical regressions.
5. Kiểm technical completion, evaluation coverage.
6. So p95 latency, token, cost dưới điều kiện tải tương đương.
7. Tạo report artifacts và áp dụng release gates.

Một nightly run `COMPLETED` có thể vẫn có quality FAIL; trạng thái run chỉ nói việc chạy đã kết thúc, không nói sản phẩm đạt.

## 9. Baseline và quy tắc so sánh trong CI

Baseline phải là một run **đã xác nhận**, có manifest, dataset snapshot, rubric/judge và outcomes đầy đủ. Không dùng alias `latest` không bất biến.

### 9.1. Comparison contract

Khi thử prompt mới, giữ dataset, reference source, model, judge, tool fixtures và điều kiện tải tương đương nếu mục tiêu là cô lập tác động prompt. Khi cố ý thử model hoặc index mới, ghi rõ intended change và các biến gây nhiễu.

Ghép kết quả theo `caseId`, không theo thứ tự dòng hay thứ tự task hoàn thành. Một case có nhiều attempts cần policy chọn kết quả; giữ retry history.

### 9.2. Bảng chuyển trạng thái

| Baseline → Candidate | Ý nghĩa | Xử lý |
| --- | --- | --- |
| PASS → PASS | Giữ hành vi đạt | Theo dõi |
| PASS → FAIL | Regression | Điều tra, có thể block |
| FAIL → PASS | Đã cải thiện | Xác minh evidence |
| FAIL → FAIL | Lỗi còn tồn tại | Theo dõi/sửa |
| PASS → ERROR | Technical regression | Kiểm provider/pipeline |
| PASS → NOT_EVALUATED | Thiếu bằng chứng chấm | Không xem là PASS |
| PASS → SKIPPED | Coverage regression | Kiểm skip policy |

### 9.3. Không chỉ nhìn net pass rate

Candidate có thể sửa 10 ca nhưng làm hỏng 4 ca khác. Net +6 PASS không xóa 4 regressions. Nếu một regression thuộc tool authorization hoặc dữ kiện critical, gate có thể block ngay.

## 10. Định nghĩa quality gates và coverage gates

Ví dụ policy giả định:

~~~yaml
qualityGate:
  datasetVersion: support-regression-v5
  rubricVersion: support-rubric-v3
  minEvaluatedCoverage: 0.98
  minFactualCorrectnessPassRate: 0.98
  minGroundednessPassRate: 0.95
  maxCriticalPassToFail: 0
  criticalCases: must-pass

executionGate:
  minTechnicalCompletion: 0.99
  maxTechnicalErrorRate: 0.01
  criticalCasesSkipped: 0
  criticalCasesNotEvaluated: 0

operationsGate:
  p95LatencyMs: 2500
  maxEstimatedModelCostUsdPerRequest: 0.01
~~~

Ngưỡng chỉ minh họa, phải được chọn theo sản phẩm và cỡ mẫu.

### 10.1. Quality pass rate

\[
\mathrm{qualityPassRate}
=\frac{N_{\mathrm{PASS}}}
{N_{\mathrm{PASS}}+N_{\mathrm{FAIL}}}.
\]

Chỉ tính trên verdict PASS/FAIL của metric hoặc aggregate đã định nghĩa. Công bố thêm số NOT_EVALUATED, SKIPPED và technical errors. Nếu mẫu số bằng 0, ghi N/A, không ghi 0% hoặc 100%.

### 10.2. Technical completion

\[
\mathrm{technicalCompletion}
=\frac{N_{\mathrm{COMPLETED}}}
{N_{\mathrm{eligible}}}.
\]

Ca skip hợp lệ phải được báo riêng và không lặng lẽ biến mất. Critical case bị skip cần gate riêng.

### 10.3. Evaluation coverage

\[
\mathrm{evaluationCoverage}
=\frac{N_{\mathrm{PASS}}+N_{\mathrm{FAIL}}}
{N_{\mathrm{COMPLETED}}}.
\]

Nếu judge lỗi hoặc thiếu evidence, coverage giảm. Điều đó phải ảnh hưởng gate khi metric bắt buộc.

### 10.4. Gate theo severity

Một critical FAIL không nên được bù bằng nhiều ca dễ PASS. Có thể áp dụng:

- Critical tool authorization: phải PASS tất cả.
- Critical factual cases: không có PASS→FAIL.
- Required metric NOT_EVALUATED: block hoặc manual review.
- Noncritical cases: ngưỡng pass rate theo nhóm.
- Technical errors: ngưỡng riêng.
- Latency/cost: giới hạn riêng.

Gate nên được phê duyệt trước khi nhìn kết quả candidate để tránh thay đổi tiêu chuẩn nhằm làm pipeline xanh.

## 11. Không để test flaky làm mất niềm tin vào CI

LLM output có tính xác suất; provider có thể throttling; evaluator có thể dao động. Một test flaky lúc xanh lúc đỏ khiến developer bỏ qua cảnh báo.

### 11.1. Phân biệt ba loại không ổn định

| Loại | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Nondeterministic model | Câu trả lời thay cách diễn đạt | Chấm theo rubric/ngưỡng, chạy lặp ca nhạy cảm |
| Infrastructure flaky | 429, timeout, network | Retry có giới hạn, quota, timeout, báo riêng |
| Evaluator flaky | Judge không nhất quán | Calibrate, human review, fixed judge version |

### 11.2. Không retry đến khi xanh

Chính sách “retry until pass” che giấu lỗi thật và làm sai xác suất. Nếu có retry kỹ thuật, giới hạn số lần và lưu tất cả attempts. Nếu chạy lặp có chủ đích, dùng quy tắc thống kê đã công bố, không lấy output tốt nhất.

### 11.3. Dùng assertion bền vững

Tránh so sánh toàn bộ câu văn bằng exact string khi mục tiêu là semantic correctness. Dùng exact match cho IDs, schema, tool arguments; dùng evaluator/rubric cho nội dung ngôn ngữ. Khi tiêu chí có số liệu chính xác như 14 ngày, nên kết hợp rule kiểm dữ kiện với evaluator để kiểm diễn đạt.

### 11.4. Theo dõi flaky rate

Ghi số lần một case thay đổi PASS/FAIL qua repeated runs, judge version và provider/model. Những case không ổn định nên được review và cải thiện rubric/dataset; đừng tự động hạ severity hoặc bỏ khỏi suite.

## 12. Giữ pipeline an toàn và kiểm soát chi phí

CI thường có quyền truy cập secrets và có thể chạy trên pull request. Cần thiết kế để test không làm lộ key hoặc thực thi side effects.

### 12.1. Secrets và external provider

- Dùng secret store của CI; không ghi API key vào manifest, log hoặc artifact.
- Không expose provider secrets cho pull request từ fork không tin cậy.
- Tách credential dev/test khỏi production.
- Hạn chế quyền và quota theo job.
- Mask headers, tokens và tool arguments nhạy cảm trong logs.
- Không gửi raw production context sang LLM judge nếu chưa được phép.

### 12.2. Tool fixtures và side effects

Tool gọi đọc trạng thái nên dùng stub/sandbox với fixture version cố định. Tool tạo giao dịch, hoàn tiền, gửi email hoặc thay đổi dữ liệu phải được fake/mock hoặc chạy trong môi trường cô lập. Kiểm tra authorization ở backend; prompt không phải ranh giới bảo mật.

### 12.3. Concurrency và rate limits

Giới hạn số case in-flight và provider calls; kiểm soát RPM/TPM bằng rate limiter dùng chung theo quota. Một runner có 4 worker vẫn có thể vượt quota nếu mỗi case tạo nhiều model calls hoặc nhiều CI jobs cùng chạy.

### 12.4. Chia budget theo pipeline stage

| Stage | Mục tiêu | Budget gợi ý |
| --- | --- | --- |
| Unit/contract | Nhanh, xác định | Không gọi LLM thật |
| PR semantic smoke | Phát hiện lỗi sớm | Dataset nhỏ, concurrency thấp |
| Nightly full | Độ bao phủ rộng | Quota và cost budget cao hơn, có giới hạn |
| Pre-release repeated critical | Độ tin cậy ca rủi ro | Lặp có chủ đích, lưu mọi attempt |
| Production sample | Theo dõi drift | Sampling policy và ngân sách riêng |

### 12.5. Theo dõi chi phí

\[
\mathrm{estimatedCost}
=\frac{\mathrm{inputTokens}\cdot\mathrm{inputPricePerMillion}}{10^6}
+\frac{\mathrm{outputTokens}\cdot\mathrm{outputPricePerMillion}}{10^6}.
\]

Đây là công thức ước tính; lưu bảng giá/version và cộng usage của từng model call, kể cả generation, tool round và judge. Tách cost ứng dụng khỏi cost evaluator. Chi phí thực có thể thêm embedding, reranking, retry, cache và hạ tầng.

## 13. Ví dụ Java: regression contract test cho RAG và tool

Ví dụ sau minh họa assertion xác định trên evidence đã được ứng dụng thu thập. Nó không gọi provider thật và không thay thế integration test.

~~~java
import java.util.List;
import java.util.Set;

public final class AiRegressionAssertions {

    public record RetrievalEvidence(
            List<String> retrievedDocumentIds,
            List<String> effectiveContextDocumentIds) {}

    public record ToolEvent(
            String toolName,
            String orderId,
            String authorization,
            String status) {}

    public static void assertRequiredSourceRetrieved(
            RetrievalEvidence evidence,
            String requiredDocumentId) {

        if (!evidence.retrievedDocumentIds()
                .contains(requiredDocumentId)) {
            throw new AssertionError(
                    "Required source missing: " + requiredDocumentId);
        }
    }

    public static void assertSourceReachedModelContext(
            RetrievalEvidence evidence,
            String requiredDocumentId) {

        if (!evidence.effectiveContextDocumentIds()
                .contains(requiredDocumentId)) {
            throw new AssertionError(
                    "Required source was not in effective context");
        }
    }

    public static void assertExpectedToolCall(
            List<ToolEvent> events,
            String expectedTool,
            String expectedOrderId) {

        boolean matched = events.stream().anyMatch(event ->
                expectedTool.equals(event.toolName())
                && expectedOrderId.equals(event.orderId())
                && "ALLOWED".equals(event.authorization())
                && "SUCCESS".equals(event.status()));

        if (!matched) {
            throw new AssertionError(
                    "Expected authorized tool invocation was not observed");
        }
    }

    public static void assertNoUnexpectedTool(
            List<ToolEvent> events,
            Set<String> allowedTools) {

        boolean unexpected = events.stream()
                .anyMatch(event -> !allowedTools.contains(event.toolName()));

        if (unexpected) {
            throw new AssertionError("Unexpected tool invocation");
        }
    }

    private AiRegressionAssertions() {}
}
~~~

### 13.1. Retrieved document và effective context khác nhau

`assertRequiredSourceRetrieved` kiểm retriever trả nguồn trong tập kết quả; `assertSourceReachedModelContext` kiểm tài liệu đó có thực sự đi vào context cuối. Một pipeline có thể retrieve đúng tài liệu nhưng lọc/cắt nó trước khi gọi model.

Để kiểm groundedness, cần context thực và answer; chỉ kiểm document ID chưa đủ để chứng minh mọi claim đều được hỗ trợ.

### 13.2. Test không được dựa vào biến trạng thái dùng chung

Mỗi case cần evidence gắn đúng `caseId`/`attemptId`. Không dùng biến global như `lastRetrievedDocuments` hay `currentQuestion` giữa các worker chạy song song. Với multi-turn, giữ session riêng cho từng case và đúng thứ tự lượt.

## 14. JUnit: kiểm tra contract và regression rules

Một test JUnit đơn giản có thể kiểm các assertion trên:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class AiRegressionAssertionsTest {

    @Test
    void requiredSourceMustBeRetrievedAndPassedToModel() {
        var evidence = new AiRegressionAssertions.RetrievalEvidence(
                List.of("policy-v3#refund"),
                List.of("policy-v3#refund"));

        assertDoesNotThrow(() ->
                AiRegressionAssertions.assertRequiredSourceRetrieved(
                        evidence, "policy-v3#refund"));

        assertDoesNotThrow(() ->
                AiRegressionAssertions.assertSourceReachedModelContext(
                        evidence, "policy-v3#refund"));
    }

    @Test
    void retrievedButFilteredSourceIsARegression() {
        var evidence = new AiRegressionAssertions.RetrievalEvidence(
                List.of("policy-v3#refund"),
                List.of("faq-general"));

        assertThrows(AssertionError.class, () ->
                AiRegressionAssertions.assertSourceReachedModelContext(
                        evidence, "policy-v3#refund"));
    }

    @Test
    void requiredToolMustUseExpectedArgumentsAndAuthorization() {
        var events = List.of(
                new AiRegressionAssertions.ToolEvent(
                        "getOrderStatus", "DH-123", "ALLOWED", "SUCCESS"));

        assertDoesNotThrow(() ->
                AiRegressionAssertions.assertExpectedToolCall(
                        events, "getOrderStatus", "DH-123"));
    }

    @Test
    void wrongToolArgumentsFailEvenIfToolNameMatches() {
        var events = List.of(
                new AiRegressionAssertions.ToolEvent(
                        "getOrderStatus", "DH-999", "ALLOWED", "SUCCESS"));

        assertThrows(AssertionError.class, () ->
                AiRegressionAssertions.assertExpectedToolCall(
                        events, "getOrderStatus", "DH-123"));
    }

    @Test
    void unexpectedToolIsRejected() {
        var events = List.of(
                new AiRegressionAssertions.ToolEvent(
                        "refundOrder", "DH-123", "ALLOWED", "SUCCESS"));

        assertThrows(AssertionError.class, () ->
                AiRegressionAssertions.assertNoUnexpectedTool(
                        events, Set.of("getOrderStatus")));
    }
}
~~~

Đây là unit test cho contract assertion. Integration test cần xác nhận evidence được capture đúng từ Spring AI advisor/model/tool thật trong môi trường test. Một test tự tạo evidence đúng rồi truyền vào assertion không chứng minh pipeline đã capture đúng nếu chưa kiểm tra integration boundary.

## 15. Ví dụ cấu trúc pipeline CI

CI provider và cú pháp job khác nhau. Dưới đây là **pseudocode YAML trung lập** mô tả thứ tự công việc; không phải file workflow có thể chạy nguyên trạng trong GitHub Actions, GitLab CI hay Jenkins.

~~~yaml
stages:
  - validate
  - contract-tests
  - ai-smoke
  - full-regression
  - compare
  - release-gate

validate:
  run:
    - compile
    - unit-tests
    - validate-prompt-and-dataset-schemas

contract-tests:
  needs: [validate]
  run:
    - rag-retrieval-contract-tests
    - tool-schema-and-authorization-tests
    - memory-isolation-tests

ai-smoke:
  needs: [contract-tests]
  suite: pr-smoke
  limits:
    maxInFlightCases: 2
    maxProviderCalls: 2
    maxAttempts: 1
  run:
    - generate-attempts
    - collect-evidence
    - run-semantic-evaluators
    - write-report

full-regression:
  trigger: nightly-or-release
  suite: full-regression
  limits:
    maxInFlightCases: 4
    maxAttempts: 2
  run:
    - verify-dataset-snapshot
    - execute-all-cases
    - score-required-metrics
    - collect-telemetry

compare:
  needs: [ai-smoke, full-regression]
  run:
    - verify-baseline-approval
    - verify-comparison-contract
    - compare-by-case-id
    - export-regression-list

release-gate:
  needs: [compare]
  run:
    - validate-coverage-and-error-rates
    - validate-quality-and-critical-cases
    - validate-latency-and-cost
    - publish-decision-artifacts
~~~

Trong một CI platform thật, map từng stage vào job/step cụ thể, pin action/plugin/dependency versions, cấu hình artifacts retention và bảo vệ secrets theo cơ chế của nền tảng đó.

### 15.1. PR job phải chạy nhanh và có ý nghĩa

Một PR smoke chỉ cần các ca liên quan thay đổi và một tập critical ổn định. Nếu thay đổi `tool schema`, kích hoạt tool contract suite; nếu thay chunking/embedding, chạy retrieval suite; nếu sửa prompt generation, chạy semantic cases tương ứng.

Nhưng không nên để chọn lọc phụ thuộc hoàn toàn vào đường dẫn file: thay đổi một thư viện dùng chung có thể ảnh hưởng nhiều thành phần. Cần một full suite theo lịch và pre-release để bù giới hạn của test selection.

### 15.2. Artifacts phải được lưu khi pipeline fail

Kể cả khi gate chặn, hãy lưu report summary, failure list, attempt evidence refs, manifest và logs đã xử lý bí mật. Developer cần thấy **case nào fail và vì sao** ngay trong PR, không chỉ dòng “job failed”.

## 16. Chuyển kết quả thành feedback cho pull request

Một comment hoặc report gắn với PR nên ngắn, nhưng có đủ số liệu để ra quyết định.

Ví dụ minh họa:

~~~text
AI Regression — BLOCKED

Suite: pr-smoke
Dataset: support-regression-v5
Baseline: approved-baseline-v4
Candidate: pr-4821

Execution:
  Selected: 20
  Completed: 19
  Technical errors: 1
  Skipped: 0

Quality:
  PASS: 16
  FAIL: 2
  NOT_EVALUATED: 1
  Evaluated pass rate: 16 / 18 = 88.9%

Regressions:
  REFUND-001 — factual correctness PASS -> FAIL
  ORDER-004 — tool arguments mismatch

Operational:
  Provider timeout: 1
  p95 latency: 2.9 s (budget 2.5 s)

Artifacts:
  summary.json
  failures.jsonl
  run-manifest.json
~~~

Đây là ví dụ giả định. Phải đảm bảo counts nhất quán theo policy của report; `NOT_EVALUATED` không được tính vào quality pass-rate denominator, nhưng coverage và technical errors vẫn phải hiển thị.

### 16.1. Link tới failure details

Mỗi dòng lỗi nên có:

- `caseId` và `attemptId`.
- Metric, reason code, severity.
- Expected/actual summary đã xử lý riêng tư.
- Reference/retrieved/effective context refs.
- Tool event refs.
- Prompt/model/pipeline version.
- Trace ref nếu có.
- Gợi ý bước điều tra, không khẳng định root cause khi chưa xác minh.

Không đưa raw prompt, user data, API key hay tool secrets vào comment công khai của PR.

## 17. Tối ưu thời gian và chi phí của CI

Một pipeline AI có thể tốn nhiều thời gian hơn unit tests do network, model generation và evaluator. Có thể tối ưu bằng cách:

1. Chạy unit và deterministic tests trước; fail sớm nếu lỗi rõ.
2. Dùng PR smoke nhỏ, không chạy full dataset ở mọi commit.
3. Tách generation và scoring để chấm lại judge trên evidence đã lưu khi cần.
4. Chạy song song có giới hạn; dùng rate limiter theo provider quota.
5. Chỉ chạy suite liên quan thay đổi nhưng giữ nightly full suite.
6. Cache artifact bất biến như dataset snapshot/index fixture; cache key phải chứa digest/version.
7. Không cache câu trả lời model giữa các phiên bản nếu mục tiêu là đánh giá generation mới.
8. Dùng judge có chi phí phù hợp cho smoke, nhưng không đổi judge âm thầm giữa baseline/candidate.
9. Đặt timeout/retry budget rõ; không retry vô hạn để pipeline xanh.
10. Theo dõi cost theo PR, run, model và evaluator.

### 17.1. Concurrency không thay thế rate limit

`maxInFlightCases=4` không đảm bảo provider không nhận quá nhiều request/phút. Một case có thể gọi model nhiều lần; nhiều CI jobs cũng có thể chia sẻ quota. Cần giới hạn provider calls và RPM/TPM ở đúng tầng.

### 17.2. Tránh cache làm mất ý nghĩa phép thử

Cache retrieval có thể hợp lý nếu key gồm corpus/index snapshot và query transform version. Nhưng cache generation output khiến candidate prompt mới nhận answer cũ sẽ làm test vô nghĩa. Nếu muốn test cache behavior, hãy xây suite riêng và kiểm cache key/version/invalidation.

### 17.3. Chi phí lỗi cũng phải được tính

Một request timeout sau khi provider đã xử lý một phần vẫn có thể tiêu thụ token hoặc phát sinh billing. Không mặc định cost của technical error bằng 0. Dùng usage provider trả về nếu có, và đánh dấu cost estimate unavailable khi không đủ dữ liệu.

## 18. Xử lý test flaky và sai lệch evaluator

CI phải phân biệt:

- **Model variance:** cùng input, câu trả lời diễn đạt khác hoặc thay verdict.
- **Provider/infrastructure error:** 429, timeout, 5xx, network.
- **Evaluator variance:** judge không nhất quán hoặc prompt judge thay đổi.
- **Dataset instability:** source/index/fixture thay đổi.
- **Test harness defect:** evidence bị ghép nhầm hoặc context không được capture.

### 18.1. Quy tắc xử lý

- Pin dataset, prompt, rubric và judge versions.
- Với ca critical, chạy lặp có chủ đích và lưu mọi attempt.
- Dùng exact assertion cho IDs/schema/tool args; dùng rubric cho ngữ nghĩa.
- Nếu judge không ổn định, hiệu chỉnh với human-labeled sample.
- Retry lỗi kỹ thuật theo ngân sách, giữ lịch sử và phân biệt với repeated evaluation.
- Không tự động loại case flaky khỏi release gate mà không có review/waiver.
- Gắn nhãn `FLAKY_UNDER_REVIEW` nếu cần, nhưng giữ nguyên các outcomes đã quan sát.

### 18.2. Không dùng “retry until green”

Một policy retry đến khi có PASS sẽ làm xác suất pass giả tạo cao. Hãy đặt `maxAttempts` trước, chọn kết quả theo quy tắc định nghĩa trước và báo cả tỉ lệ attempt lỗi. Với repeated runs, báo tần suất PASS/FAIL thay vì chọn lần tốt nhất.

## 19. Release gates và sau triển khai

Một gate mẫu:

~~~yaml
releaseGate:
  comparison:
    baselineApproved: true
    datasetAndRubricCompatible: true
    minPairedCoverage: 0.98
    maxCriticalPassToFail: 0
  quality:
    factualCorrectnessPassRate: ">= 0.98"
    groundednessPassRate: ">= 0.95"
    criticalCases: must-pass
  execution:
    minTechnicalCompletion: 0.99
    criticalCasesSkipped: 0
    criticalCasesNotEvaluated: 0
  operations:
    p95LatencyMs: "<= 2500"
    technicalErrorRate: "<= 0.01"
    maxEstimatedCostUsdPerRequest: 0.01
~~~

Các ngưỡng chỉ minh họa. Một ca critical factual FAIL hoặc tool authorization FAIL có thể block release dù aggregate pass rate đạt. Một ca critical NOT_EVALUATED có thể block vì thiếu bằng chứng, nhưng không cần gán factual FAIL khi chưa biết câu trả lời sai.

### 19.1. Canary và production observation

Offline regression không thể bao phủ mọi câu hỏi, dữ liệu và trạng thái tool production. Sau deploy:

- Theo dõi error rate, p95/p99 latency, retries và provider throttling.
- Theo dõi model calls, token và cost theo phiên bản.
- Lấy mẫu response theo policy được phê duyệt.
- Review các ca factual/groundedness có rủi ro cao.
- Liên kết verdict với trace và safe evidence refs.
- Chuyển incident đã xác minh thành case regression mới.
- Rollback hoặc giảm traffic nếu gate production bị vi phạm.

Mẫu production có bias nếu ưu tiên các ca bị báo lỗi. Phải phân biệt tỷ lệ trong tập review với ước lượng cho toàn traffic.

### 19.2. Cập nhật baseline sau khi candidate được duyệt

Không tự động đặt candidate mới làm baseline ngay khi CI xanh. Cần review report, regressions, critical cases, quality/ops gates và phê duyệt. Sau khi promote, tạo baseline ID mới và giữ baseline cũ để audit/rollback.

## 20. Những lỗi thiết kế CI thường gặp

**Chỉ chạy unit tests và HTTP smoke.** Chúng không kiểm được factual correctness hoặc groundedness.

**Chạy full LLM suite trên mọi PR.** Thời gian và chi phí tăng, developer dễ bỏ qua pipeline; nên phân tầng suite.

**Dùng dataset mutable.** Baseline/candidate có thể đang được chấm trên hai chuẩn khác nhau.

**Không pin rubric/judge.** Điểm đổi có thể do cách chấm chứ không phải ứng dụng.

**Dùng reference docs thay actual context.** Che retrieval regression và tạo groundedness giả.

**Không kiểm tool authorization ở backend.** Prompt không phải biện pháp bảo vệ quyền.

**Coi mọi evaluator PASS là sự thật.** Judge cần calibration và human review cho ca quan trọng.

**Retry cho đến khi xanh.** Làm sai lệch reliability và che lỗi provider.

**Chỉ nhìn aggregate pass rate.** Không thấy PASS→FAIL ở critical case.

**Gộp ERROR, SKIPPED và NOT_EVALUATED vào FAIL hoặc bỏ hẳn.** Sai mẫu số và sai hướng điều tra.

**Không lưu artifacts khi gate fail.** Developer không thể biết case và evidence.

**So p95 trong điều kiện tải khác nhau.** Không thể quy kết latency chỉ do prompt/model.

**Lộ secrets trong CI logs hoặc PR artifacts.** Có thể gây truy cập ngoài ý muốn và rò dữ liệu.

## 21. Bài thực hành: đưa regression evaluation vào pipeline

**Bối cảnh:** một chatbot Spring AI trả lời chính sách bằng RAG và gọi tool `getOrderStatus`. Nhóm muốn đưa kiểm thử chất lượng vào CI mà không làm mỗi pull request mất hàng chục phút.

### Phần A — Tạo bộ test và baseline

1. Tạo dataset 40–60 case gồm nguồn hiện hành/cũ, thiếu nguồn, tool call, quyền và multi-turn.
2. Xác minh reference facts, expected documents và expected tool behavior.
3. Chạy baseline, lưu manifest, actual context, answer, tool events và verdict.
4. Review critical cases và phê duyệt baseline.

**Đầu ra:** immutable dataset, baseline run ID, rubric/judge version và report.

### Phần B — Tạo PR smoke suite

Chọn 8–12 ca đại diện, trong đó có ít nhất một critical factual case, một missing-source case, một RAG freshness case và một tool authorization case. Xây deterministic tests trước, semantic evaluator sau.

**Đầu ra:** suite chạy nhanh, report nêu rõ phạm vi và coverage.

### Phần C — Tích hợp job CI

Tổ chức pipeline:

- Validate/build/unit.
- RAG/tool contract tests.
- PR smoke semantic evaluation.
- Xuất summary và failure artifacts.
- Block khi critical case fail, technical errors vượt ngưỡng hoặc evaluation coverage thiếu.

Dùng secrets test riêng và tool sandbox. Đặt giới hạn concurrency/RPM và timeout.

**Đầu ra:** job có kết quả máy đọc được và developer có thể điều tra lỗi.

### Phần D — Nightly full regression

Chạy toàn bộ dataset và repeated tests cho một số case nhạy cảm. So baseline theo case ID, phân metric và nhóm; lưu retry history, token, latency, cost.

**Đầu ra:** full report, regression list, evaluation gaps và operational summary.

### Phần E — Mô phỏng thay đổi gây hồi quy

Sửa prompt để model ưu tiên tài liệu mới sai cách, hoặc thay filter khiến tài liệu cũ lọt vào context. Xác nhận CI phát hiện `PASS→FAIL` ở case chính sách và chỉ ra actual retrieved/effective context.

Tiếp theo mô phỏng provider timeout hoặc judge timeout. Kiểm tra chúng được phân loại ERROR/NOT_EVALUATED, không bị gán quality FAIL giả.

**Đầu ra:** ba báo cáo khác nhau cho quality regression, technical error và evaluation gap.

### Phần F — Pre-release và canary

Tạo candidate run đầy đủ, kiểm comparison contract, critical gates, latency/cost. Sau khi duyệt, triển khai canary và theo dõi telemetry. Đưa lỗi production đã xác minh vào dataset mới theo quy trình review.

**Đầu ra:** quyết định release có bằng chứng và kế hoạch quan sát sau deploy.

### Checklist nghiệm thu

- [ ] Có dataset snapshot, reference labels và rubric version.
- [ ] Baseline được phê duyệt và có run ID bất biến.
- [ ] PR smoke suite có phạm vi và sample size rõ.
- [ ] Deterministic tests kiểm document IDs, schema, tool args và quyền.
- [ ] Semantic evaluators dùng actual answer/effective context.
- [ ] Tool side effects được sandbox/mock.
- [ ] CI secrets không lộ trong log/artifact.
- [ ] Concurrency, rate limits, timeout và retry có giới hạn.
- [ ] Technical ERROR, quality FAIL, SKIPPED và NOT_EVALUATED được tách.
- [ ] Failure list có case/attempt/reason/evidence refs.
- [ ] Baseline comparison ghép theo case ID và báo PASS→FAIL.
- [ ] Critical regressions và thiếu evidence có gate riêng.
- [ ] p95/token/cost có điều kiện đo rõ.
- [ ] Nightly/pre-release chạy full suite phù hợp.
- [ ] Production incidents được review trước khi thêm vào regression dataset.
- [ ] Candidate chỉ được promote thành baseline sau phê duyệt.

### Câu hỏi tự kiểm tra

1. Vì sao HTTP smoke xanh chưa đủ chứng minh chất lượng ứng dụng Spring AI?
2. PR smoke và nightly full regression khác nhau ở mục tiêu nào?
3. Khi sửa embedding model, nên kích hoạt các bộ kiểm thử nào?
4. Vì sao phải dùng actual effective context để chấm groundedness?
5. Một ca tool trả đúng answer nhưng không gọi tool bắt buộc có thể PASS không?
6. Khi judge timeout sau generation thành công, execution và evaluation status là gì?
7. Tại sao không retry một test cho đến khi có PASS?
8. Baseline alias `latest` có rủi ro gì trong CI?
9. Candidate có pass rate cao hơn nhưng có critical PASS→FAIL; gate nên xử lý thế nào?
10. Vì sao concurrency cap không thay thế RPM/TPM rate limiter?
11. Có thể dùng cache generation output khi đang kiểm prompt mới không? Vì sao?
12. Khi nào cần chạy lặp một case và lưu mọi attempt?
13. Vì sao p95 cần histogram/phân bố thay vì timer sum/count?
14. Làm sao biến một incident production đã xác minh thành regression test mà không đưa dữ liệu nhạy cảm vào CI?
15. Những điều kiện nào cần đạt trước khi candidate trở thành baseline mới?

## 22. Tổng kết

Đưa tiêu chí hồi quy vào CI/CD giúp kiểm tra chất lượng Spring AI ở đúng thời điểm thay đổi được tạo ra: **PR smoke** phản hồi nhanh, **nightly full regression** phát hiện lỗi rộng, **pre-release comparison** bảo vệ baseline đã xác nhận và **post-deploy monitoring** phát hiện drift ngoài dataset.

Một pipeline đáng tin kết hợp **kiểm tra xác định** cho schema, retrieval và tool contracts với **evaluator ngữ nghĩa** cho relevance, groundedness và factual correctness. Nó quản lý dataset/prompt/model/index/rubric theo version, ghép outcomes theo case ID, tách quality FAIL khỏi technical ERROR và NOT_EVALUATED, đồng thời báo coverage, critical regressions, latency, token và cost.

CI xanh chỉ có ý nghĩa khi report cho biết **đã chạy những gì, trên chuẩn nào, có đủ bằng chứng không và những ca quan trọng nào đã thay đổi**. Khi artifacts được lưu, failures truy vết được và release gate được định nghĩa trước, nhóm có thể phát hành các thay đổi prompt, model và pipeline với độ tin cậy cao hơn, rồi dùng incident đã xác minh để tiếp tục cải thiện regression dataset.

### Tài liệu tham khảo

- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring Boot — Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
