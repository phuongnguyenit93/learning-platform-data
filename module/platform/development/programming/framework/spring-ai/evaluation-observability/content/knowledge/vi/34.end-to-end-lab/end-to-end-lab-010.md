# Viết hướng dẫn tái lập, lưu bằng chứng và dọn dữ liệu thực hành

Một bài lab đánh giá Spring AI chỉ có giá trị khi người khác có thể chạy lại, hiểu kết quả đến từ đâu và kiểm tra được bằng chứng. Một con số PASS rate trong dashboard chưa đủ để kết luận một prompt tốt hơn; cần biết dataset nào đã chạy, model và prompt version nào được dùng, evaluator nào chấm, telemetry có đầy đủ không và kết quả chi tiết được lưu ở đâu.

Bài thực hành này xây dựng một quy trình end-to-end cho trợ lý hỗ trợ khách hàng có hai khả năng: trả lời câu hỏi chính sách bằng RAG và tra cứu đơn hàng qua tool. Bạn sẽ chuẩn bị dữ liệu lab biệt lập, chạy baseline và candidate, thu thập evaluation results cùng metrics/traces, tạo manifest có checksum, phân tích regression rồi dọn dữ liệu tạm mà vẫn giữ được evidence cần thiết.

Bài học thuộc chương **Thực hành tổng hợp** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module tập trung đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking, kiểm thử RAG/tool calling và quan sát metrics, traces, cost, latency qua các phiên bản prompt, model và pipeline.

## 1. Mục tiêu và sản phẩm cuối lab

Sau khi hoàn thành, bạn có thể:

1. Tạo một môi trường thực hành biệt lập, có cấu hình và phiên bản được ghi nhận.
2. Chuẩn bị dataset, ground truth và fixture cho RAG/tool calling mà không dùng dữ liệu khách hàng thật.
3. Chạy cùng một bộ case trên baseline và candidate.
4. Thu thập verdict, score, evaluator outcome, token/cost, latency và traces.
5. Phân biệt lỗi ứng dụng, lỗi evaluator và thiếu telemetry.
6. Lưu report, raw results, trace references, scrape snapshot và manifest checksum.
7. Xác định regression bằng quality gates có mẫu số và coverage rõ ràng.
8. Dọn database, vector namespace, container, dashboard và dữ liệu tạm theo đúng phạm vi.
9. Giữ evidence đủ để người khác kiểm tra mà không cần giữ toàn bộ môi trường đang chạy.

### 1.1. Deliverables

Thư mục evidence cuối cùng nên có:

| Artifact | Nội dung |
| --- | --- |
| run-manifest.json | Commit, dataset/rubric/prompt/model/evaluator versions và cấu hình |
| dataset/ | Dataset đã dùng hoặc reference/checksum của dataset |
| results-baseline.jsonl | Kết quả từng case của baseline |
| results-candidate.jsonl | Kết quả từng case của candidate |
| summary.json | Count, denominator, coverage, scores và latency |
| comparison.md | So sánh, regression và quyết định |
| metrics/ | Prometheus scrape snapshot hoặc query export |
| traces/ | Trace references hoặc export đã scrub |
| checksums.sha256 | SHA-256 của artifacts được giữ |
| cleanup-report.md | Những tài nguyên đã dọn và những evidence được giữ |

Không cần giữ database volume hoặc toàn bộ container để chứng minh một lần chạy nếu raw results, manifest và evidence cần thiết đã được lưu an toàn.

## 2. Kịch bản lab và kiến trúc

Ta xây dựng một trợ lý hỗ trợ khách hàng với ba loại tác vụ:

- POLICY_QUESTION: truy vấn tài liệu chính sách qua retriever và trả lời có citation.
- ORDER_LOOKUP: gọi tool chỉ đọc để lấy trạng thái đơn hàng từ fixture service.
- UNSUPPORTED_QUESTION: câu hỏi không có bằng chứng trong knowledge base; trợ lý phải nói rõ chưa đủ thông tin hoặc handoff.

Mỗi case có expected behavior và ground truth. Evaluation runner gọi ứng dụng, lưu response/tool trace, sau đó chạy các evaluator theo rubric. Metric được ghi theo nhóm hữu hạn; dữ liệu case-level lưu ở result store.

### 2.1. Sơ đồ thành phần

~~~mermaid
flowchart TD
    A["Versioned evaluation dataset"] --> B["Evaluation runner"]
    B --> C["Spring AI application"]
    C --> D["ChatClient / model"]
    C --> E["Retriever / vector store"]
    C --> F["Read-only order tool"]
    E --> G["Seeded policy documents"]
    F --> H["Synthetic order fixtures"]
    C --> I["Response + trace context"]
    I --> J["Evaluator pipeline"]
    J --> K["Evaluation result store"]
    C --> L["Micrometer metrics"]
    J --> L
    L --> M["Prometheus"]
    I --> N["Tracing backend"]
    M --> O["Grafana dashboard"]
    K --> P["Evidence pack"]
    N --> P
    O --> P
~~~

### 2.2. Ranh giới dữ liệu

Tách dữ liệu thành ba vùng:

1. **Input fixtures:** dataset, policy documents và order records tổng hợp. Có thể tái tạo từ source-controlled fixtures.
2. **Runtime data:** vector index, evaluation run records, temporary conversations, cache và telemetry trong lúc chạy.
3. **Evidence:** raw evaluation outputs đã scrub, summary, manifest, metric snapshots và trace references cần giữ lại.

Chỉ vùng evidence được chuyển sang nơi lưu kết quả lâu dài theo policy của lab. Runtime data phải có namespace riêng để có thể dọn mà không ảnh hưởng môi trường khác.

### 2.3. Không dùng production credentials hoặc customer data

Lab nên dùng:

- Synthetic names, order IDs và policy documents.
- API key của sandbox hoặc key có quota giới hạn.
- Database/schema/vector namespace riêng.
- Read-only tool fixture hoặc mock service.
- Trace/log exporter của môi trường lab.

Không copy conversation, prompt, document hoặc credential của khách hàng vào dataset thực hành. Không trỏ cleanup command vào production database, shared vector index hoặc bucket dùng chung.

## 3. Quy ước tái lập và đặt tên run

Một run cần nhận diện được cả đầu vào lẫn cách đánh giá.

### 3.1. Run identity

Định nghĩa một run key từ các thành phần:

- Git commit hoặc source revision.
- Dataset version và dataset checksum.
- Rubric/evaluator version.
- Prompt template version.
- Model provider/model ID và các generation parameters quan trọng.
- Embedding model và vector index snapshot/version.
- Tool schema/policy version.
- Application configuration profile.

Không dùng timestamp làm định danh duy nhất. Có thể tạo run ID riêng, nhưng lưu toàn bộ lineage vào manifest.

### 3.2. Baseline và candidate

Baseline và candidate phải dùng:

- Cùng dataset và case order.
- Cùng rubric và evaluator version.
- Cùng tool fixtures và business verification rules.
- Cùng retrieval corpus/index snapshot nếu đang đo prompt/model change.
- Cùng sampling policy.

Chỉ thay đổi biến đang được kiểm tra. Nếu đổi prompt, model, embedding model và retrieval config cùng lúc, bạn không biết yếu tố nào tạo ra chênh lệch.

### 3.3. Ghi nhận non-determinism

Remote model có thể thay đổi output dù temperature thấp hoặc bằng 0; provider có thể cập nhật model alias, routing hoặc infrastructure. Để tăng khả năng tái lập:

- Dùng model version cố định nếu provider hỗ trợ.
- Ghi temperature, top_p, max tokens và seed nếu API hỗ trợ.
- Pin prompt template, system instruction và tool schema.
- Pin dataset, corpus, chunking, embedding và index configuration.
- Ghi evaluator model/version riêng với answer model.
- Lưu raw response, usage metadata và evaluator evidence đã scrub.

Không hứa output giống từng ký tự giữa hai lần gọi model từ xa. Mục tiêu là tái lập được điều kiện, dữ liệu, cách đo và bằng chứng để giải thích khác biệt.

## 4. Cấu trúc thư mục evidence

Tạo một thư mục cho mỗi lab run, không dùng chung với runtime database directory.

~~~text
artifacts/
  spring-ai-eval-lab/
    2026-11-27T140000Z-baseline/
      run-manifest.json
      dataset/
        cases.jsonl
        policy-corpus/
      results/
        cases.jsonl
        summary.json
      metrics/
        prometheus-scrape.txt
        query-results.json
      traces/
        trace-index.json
      comparison.md
      checksums.sha256
      cleanup-report.md
    2026-11-27T143000Z-candidate/
      ...
~~~

Timestamp trong ví dụ chỉ là tên thư mục. Hãy dùng UTC và tránh đặt thông tin cá nhân vào tên file/path.

### 4.1. Evidence không phải raw dump không giới hạn

Chỉ lưu dữ liệu cần để chứng minh kết quả:

- Case ID tổng hợp, task type, expected behavior và verdict.
- Score, evaluator version và lý do đã scrub.
- Tool call name/family và argument fields đã redact.
- Citation references hoặc document IDs tổng hợp.
- Trace ID/reference không chứa secret.
- Token usage, cost estimate và durations.

Không lưu API key, authorization headers, raw customer content hoặc full prompt/answer nếu policy không cho phép. Nếu cần giữ raw model output để phân tích, dùng kho có access control, retention và redaction rõ ràng; evidence pack có thể chỉ giữ reference.

## 5. Chuẩn bị dataset và ground truth

Dataset phải mô tả input, expected behavior và cách chấm. Không để evaluator tự suy ra expected result từ output của chính model.

### 5.1. Ví dụ schema JSONL

Mỗi dòng là một case:

~~~jsonl
{"case_id":"policy-refund-001","task_type":"policy_question","input":{"message":"Khách có thể yêu cầu hoàn tiền trong bao lâu?","locale":"vi"},"expected":{"required_facts":["refund_window_days"],"required_citations":["refund-policy-v3"],"must_not_claim":["instant_refund"]},"evaluation":{"criteria":["relevance","groundedness","fact_check","citation_correctness"],"min_score":{"relevance":0.8,"groundedness":0.9}}}
{"case_id":"order-status-001","task_type":"order_lookup","input":{"message":"Kiểm tra trạng thái đơn ORD-LAB-1001","locale":"vi"},"expected":{"tool_family":"order_lookup","order_fixture":"ORD-LAB-1001","business_status":"SHIPPED","required_facts":["SHIPPED"]},"evaluation":{"criteria":["tool_selection","argument_validity","fact_check","task_success"]}}
{"case_id":"policy-no-evidence-001","task_type":"unsupported_question","input":{"message":"Chính sách có bảo đảm giao hàng trong 15 phút không?","locale":"vi"},"expected":{"must_not_claim":["guaranteed_15_minutes"],"expected_behavior":"abstain_or_handoff"},"evaluation":{"criteria":["safe_abstention","groundedness","policy_compliance"]}}
{"case_id":"chat-no-tool-001","task_type":"general_chat","input":{"message":"Hãy giải thích ngắn gọn cách theo dõi đơn hàng.","locale":"vi"},"expected":{"tool_calls":0,"required_facts":["tracking_steps"]},"evaluation":{"criteria":["relevance","fact_check","tool_necessity"]}}
~~~

Đây là schema minh họa. Khi triển khai, định nghĩa JSON Schema hoặc record type để validate các field bắt buộc, kiểu dữ liệu, enum và phiên bản.

### 5.2. Ground truth cho RAG

Với mỗi policy case, lưu:

- Tập document/chunk liên quan.
- Các fact bắt buộc phải xuất hiện.
- Các claim bị cấm hoặc dễ gây hiểu nhầm.
- Citation/doc reference hợp lệ.
- Mức relevance hoặc graded relevance nếu đo ranking metrics.
- Hành vi mong đợi khi không có evidence.

Ground truth cần được người có chuyên môn xác nhận. Không dùng câu trả lời do cùng model đang được đánh giá tự tạo làm ground truth duy nhất.

### 5.3. Ground truth cho tool calling

Với mỗi tool case, lưu:

- Tool family hoặc tập tool hợp lệ.
- Arguments mong đợi theo schema.
- Fixture record và expected source-of-truth result.
- Các side effects bị cấm trong lab.
- Hậu điều kiện để đánh dấu task verified success.

Nếu có nhiều tool/argument hợp lệ, ghi tập phương án chấp nhận được. Không bắt model khớp một chuỗi JSON duy nhất nếu thứ tự key hoặc biểu diễn tương đương không ảnh hưởng semantics.

### 5.4. Dataset version và validation

Đặt version rõ ràng, ví dụ dataset v1.2. Trước khi chạy:

1. Validate JSONL từng dòng.
2. Kiểm tra case_id không trùng.
3. Kiểm tra mỗi task_type có evaluator tương ứng.
4. Kiểm tra required facts/citations có trong ground truth.
5. Kiểm tra fixtures tồn tại.
6. Ghi count theo task_type và checksum file.

Không âm thầm sửa dataset sau khi baseline đã chạy. Nếu phát hiện ground truth sai, tạo dataset version mới và chạy lại baseline/candidate bằng cùng version mới.

## 6. Chuẩn bị môi trường lab

### 6.1. Prerequisites

Lab cần:

- JDK phù hợp với phiên bản Spring Boot/Spring AI đang dùng.
- Build tool và wrapper của project.
- Docker Engine và Docker Compose nếu chạy dependency cục bộ.
- Sandbox model credentials nếu dùng remote model.
- Prometheus/Grafana và tracing backend, hoặc stack observability tương đương.
- Quyền ghi vào thư mục artifacts của lab.

Ghi lại phiên bản JDK, build tool, container images và application dependencies trong manifest. Không nâng version giữa baseline và candidate.

### 6.2. Environment variables

Tạo file env riêng cho lab, không commit secret:

~~~text
SPRING_PROFILES_ACTIVE=lab
SPRING_AI_MODEL=<pinned-model-id>
SPRING_AI_EMBEDDING_MODEL=<pinned-embedding-model-id>
SPRING_AI_API_KEY=<sandbox-secret>
LAB_RUN_ID=<unique-run-id>
LAB_DATA_NAMESPACE=spring-ai-eval-lab
MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=health,info,prometheus
~~~

File thực tế chứa key phải được loại khỏi version control và không được copy vào evidence pack. Manifest chỉ ghi tên provider/model và secret reference, không ghi secret value.

### 6.3. Namespace và project isolation

Chọn namespace riêng cho:

- Docker Compose project.
- Database/schema.
- Vector collection/index.
- Object storage prefix.
- Evaluation result records.
- Prometheus labels/job.
- Grafana folder/dashboard.

Tên namespace nên cố định theo lab, còn run ID là dimension ở result store. Không tạo metric label bằng từng run ID.

### 6.4. Khởi động dependencies

Ví dụ lệnh Docker Compose:

~~~powershell
docker compose -p spring-ai-eval-lab -f compose.lab.yml config
docker compose -p spring-ai-eval-lab -f compose.lab.yml up -d
docker compose -p spring-ai-eval-lab -f compose.lab.yml ps
~~~

compose.lab.yml là file do project/lab cung cấp; các service có thể gồm PostgreSQL/pgvector, Prometheus, Grafana và tracing collector/backend. Lệnh config giúp kiểm tra cấu hình đã resolve trước khi tạo container.

Không dùng tên project Compose chung chung như default khi trên máy có các stack khác. Project name rõ ràng giúp cleanup nhắm đúng container/network/volume của lab.

## 7. Seed dữ liệu và xác minh nguồn

### 7.1. Seed policy corpus

Quy trình seed:

1. Xóa hoặc tạo mới vector namespace riêng của lab.
2. Nạp đúng policy corpus version.
3. Áp dụng chunking strategy đã ghi trong manifest.
4. Dùng embedding model đã pin.
5. Ghi index configuration và document count.
6. Chạy smoke query với expected relevant document.

Không trộn index cũ và mới trong cùng namespace. Nếu thay embedding model hoặc chunking, tạo index version riêng vì đây là biến thí nghiệm.

### 7.2. Seed tool fixtures

Order lookup tool chỉ đọc từ fixture service/database. Ví dụ:

~~~json
{
  "order_id": "ORD-LAB-1001",
  "status": "SHIPPED",
  "updated_at": "2026-11-20T10:00:00Z",
  "lab_record": true
}
~~~

Fixture phải có dấu hiệu nhận diện lab, không trùng ID thật. Nếu test tạo hoặc cập nhật dữ liệu, dùng transaction rollback hoặc namespace riêng và có cleanup owner.

### 7.3. Smoke test trước evaluation

Chạy một case đại diện cho từng nhánh:

- RAG tìm thấy tài liệu liên quan.
- Tool lookup trả fixture đúng.
- Unsupported question dẫn đến abstain/handoff.
- Chat-only không gọi tool.

Nếu smoke test thất bại, dừng evaluation. Nếu tiếp tục, kết quả có thể phản ánh lỗi seed/configuration thay vì chất lượng model/prompt.

## 8. Xây evaluation pipeline

Evaluation runner nên tách việc gọi ứng dụng, lưu kết quả, chạy evaluator và ghi telemetry. Như vậy có thể retry evaluator mà không gọi lại tool side effect hoặc tạo một business task thứ hai.

### 8.1. Pipeline theo từng case

~~~mermaid
flowchart TD
    A["Load case"] --> B["Validate fixture and expected data"]
    B --> C["Create task/run context"]
    C --> D["Invoke Spring AI app"]
    D --> E["Capture response, tool events and trace reference"]
    E --> F["Run criterion evaluators"]
    F --> G["Persist case-criterion results"]
    G --> H["Emit metrics once after commit"]
    H --> I["Aggregate run summary"]
~~~

### 8.2. Evaluator set

Một cấu hình lab có thể dùng:

| Evaluator | Phương pháp | Output |
| --- | --- | --- |
| Schema validator | Deterministic | PASS/FAIL cho JSON/tool args |
| Tool selection checker | Expected tool family | PASS/FAIL/NOT_APPLICABLE |
| Retrieval evaluator | Ground-truth document set | Precision@k/Recall@k/MRR |
| Fact checker | Rule-based hoặc source comparison | SUPPORTED/UNSUPPORTED/CONTRADICTED |
| Groundedness judge | Human hoặc model judge | Score/verdict/evidence |
| Answer relevance judge | Human hoặc model judge | Score/verdict/rationale đã scrub |
| Business verifier | Fixture source of truth | Verified success/failure |

Không dùng model judge cho mọi tiêu chí. Các điều kiện có expected value rõ ràng nên dùng deterministic evaluator; model judge phù hợp với tiêu chí ngữ nghĩa nhưng cần calibration.

### 8.3. Output schema

Một record kết quả có thể gồm:

~~~json
{
  "run_id": "lab-run-20261127-a",
  "case_id": "order-status-001",
  "criterion": "fact_check",
  "verdict": "pass",
  "score": 1.0,
  "evaluator": "rule_based",
  "evaluator_version": "fact-check-v2",
  "evidence_refs": ["fixture:ORD-LAB-1001"],
  "trace_id": "trace-reference",
  "completed_at": "2026-11-27T14:15:00Z"
}
~~~

Trong lab thực tế, trace_id là giá trị trace hợp lệ từ tracing backend. Evidence references phải được scrub và không chứa secret/customer content.

### 8.4. Retry và exactly-once metric emission

Mỗi run/case/criterion cần unique key. Luồng khuyến nghị:

1. Ghi result với unique key.
2. Commit result.
3. Chỉ phát metric khi trạng thái chuyển từ pending sang terminal lần đầu.
4. Nếu cần độ bền giữa database và metrics, dùng transactional outbox hoặc batch export từ committed results.

Không increment Counter trước khi lưu result thành công. Nếu worker crash sau khi increment nhưng trước commit, dashboard sẽ đếm một verdict không tồn tại trong result store.

## 9. Instrumentation: metrics, traces và logs

Lab cần đo ít nhất ba lớp:

1. **System/technical:** request count, latency, exception, dependency availability.
2. **AI pipeline:** model calls, token usage, retrieval duration, tool execution và evaluator execution.
3. **Quality/business:** case-criterion verdict, score distribution, task verified outcome và evaluation coverage.

### 9.1. Metric catalog cho lab

| Meter logic | Type | Labels hữu hạn | Ghi khi |
| --- | --- | --- | --- |
| app.ai.eval.criterion.completed | Counter | mode, task_type, criterion, verdict | Case-criterion đã chốt |
| app.ai.eval.execution | Counter | evaluator, outcome | Mỗi evaluator attempt kết thúc |
| app.ai.eval.score | DistributionSummary | mode, task_type, criterion | Có score hợp lệ |
| app.ai.eval.duration | Timer | evaluator, outcome | Mỗi evaluator attempt kết thúc |
| app.ai.task.outcome | Counter | task_type, outcome | Business task chuyển terminal |
| app.ai.tool.execution | Counter | tool_family, outcome | Tool attempt kết thúc |
| app.ai.retrieval.documents | DistributionSummary | task_type | Retrieval hoàn tất |
| app.ai.model.tokens | Counter | direction, model_family | Provider usage được xác nhận |
| app.ai.model.cost.amount | DistributionSummary | task_type, model_family, currency | Cost sample cho một model call theo pricing version |
| app.ai.eval.run.inflight | Gauge | run_mode | Run đang chạy |

Các tên này là custom meter của lab. Trước khi viết PromQL, mở endpoint scrape và xác minh tên Prometheus thực tế do Micrometer registry tạo ra.

### 9.2. Quy tắc labels

Chỉ dùng tập giá trị nhỏ và được allowlist:

- mode: offline, online_sample.
- task_type: policy_question, order_lookup, unsupported_question, general_chat, other.
- criterion: relevance, groundedness, fact_check, tool_selection, retrieval, task_success, other.
- verdict: pass, fail, inconclusive, not_applicable, skipped.
- outcome: success, error, timeout, cancelled.
- evaluator: rule_based, model_judge, human, other.

Không dùng run_id, case_id, user_id, conversation_id, order_id, prompt text, answer text, exception message hoặc trace_id làm metric labels. Lưu các reference này ở result store hoặc trace attributes đã scrub.

### 9.3. Custom Observation boundaries

Tạo Observation riêng cho những bước nghiệp vụ chưa được Spring AI instrumentation bao phủ:

- evaluation.run.
- evaluation.case.
- evaluation.criterion.
- business.verification.

Giữ span names ổn định. Low-cardinality attributes gồm task_type, criterion, evaluator và outcome. Trace ID/run reference chỉ dùng để liên kết evidence; không copy vào metric tags.

### 9.4. Correlation

Một task nên có trace context xuyên suốt:

~~~text
evaluation runner
  -> application request
    -> ChatClient/model
    -> retriever/vector store
    -> tool dispatcher
      -> order fixture service
    -> response
  -> evaluators
  -> business verification
~~~

Trace cần cho phép nhìn thấy component nào chậm, lỗi hoặc bị retry. Log nên có trace ID và task reference opaque để tìm record. Không log token/key, authorization header hoặc nội dung người dùng không cần thiết.

## 10. Cấu hình Prometheus và Grafana

### 10.1. Expose Actuator metrics trong profile lab

Ví dụ cấu hình Spring Boot:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: never
  metrics:
    tags:
      application: spring-ai-eval-lab
~~~

Đây là cấu hình minh họa. Cần dependency Actuator và Prometheus registry phù hợp với phiên bản Spring Boot/Micrometer. Chỉ expose endpoint metrics trong network lab hoặc môi trường đã kiểm soát truy cập.

### 10.2. Prometheus scrape job

~~~yaml
scrape_configs:
  - job_name: spring-ai-eval-lab
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["spring-ai-app:8080"]
~~~

Tên host/port phải khớp network Compose. Không expose Actuator management endpoints công khai chỉ để Prometheus scrape.

### 10.3. Dashboard panels

Tạo dashboard folder riêng cho lab, gồm:

- Application health và scrape health.
- Request/model/tool/retrieval latency.
- Tool execution outcome.
- Evaluation coverage và verdict distribution.
- Score distribution theo criterion.
- Evaluator timeout/error và duration.
- Task verified outcome.
- Token usage/cost.

Panel quality luôn phải hiển thị numerator, denominator và coverage. Nếu query rỗng, hiển thị No data/N/A thay vì tự chuyển thành 0.

### 10.4. Snapshot evidence

Trước khi cleanup:

1. Export dashboard JSON hoặc panel query definitions.
2. Lưu query result cùng time range và timezone.
3. Lưu raw scrape snapshot để xác minh meter names/tags.
4. Lưu trạng thái Prometheus targets.
5. Lưu trace index có trace references và summary.

Screenshot hữu ích cho review, nhưng không thay thế raw JSON/CSV và manifest có thể kiểm tra.

## 11. PromQL dùng trong lab

Các truy vấn sau giả định meter names được export theo quy ước Micrometer Prometheus phổ biến. Xác minh bằng scrape snapshot trước khi sử dụng.

### 11.1. Evaluation verdict counts

~~~promql
sum by (mode, task_type, criterion, verdict) (
  increase(app_ai_eval_criterion_completed_total[1h])
)
~~~

Đây là số case-criterion được chốt theo verdict trong một giờ, không phải số logical tasks. Một case có nhiều criteria tạo nhiều criterion completions.

### 11.2. PASS rate trên verdict có kết luận

~~~promql
sum by (mode, task_type, criterion) (
  rate(app_ai_eval_criterion_completed_total{verdict="pass"}[15m])
)
/
sum by (mode, task_type, criterion) (
  rate(app_ai_eval_criterion_completed_total{verdict=~"pass|fail"}[15m])
)
~~~

Mẫu số chỉ gồm PASS và FAIL. INCONCLUSIVE, NOT_APPLICABLE và SKIPPED phải được báo riêng. Nếu không có decided cases, panel phải thể hiện N/A/no evaluated criteria.

### 11.3. Evaluator execution error rate

~~~promql
sum by (evaluator) (
  rate(app_ai_eval_execution_total{outcome=~"timeout|error"}[5m])
)
/
sum by (evaluator) (
  rate(app_ai_eval_execution_total[5m])
)
~~~

Tỷ lệ này đo độ tin cậy của evaluator, không phải chất lượng câu trả lời.

### 11.4. Mean quality score

Với DistributionSummary:

~~~promql
sum by (mode, task_type, criterion) (
  rate(app_ai_eval_score_sum[15m])
)
/
sum by (mode, task_type, criterion) (
  rate(app_ai_eval_score_count[15m])
)
~~~

Mean score phải được đọc cùng sample count, verdict mix và coverage. Mean không cho biết phân bố tail.

### 11.5. p95 evaluator duration

Nếu Timer histogram được bật:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, evaluator, outcome) (
    rate(app_ai_eval_duration_seconds_bucket[5m])
  )
)
~~~

Giữ outcome để phân biệt thời gian success, timeout và error. Xác minh bucket được cấu hình và export.

### 11.6. Tool execution error rate

~~~promql
sum by (tool_family) (
  rate(app_ai_tool_execution_total{outcome="error"}[5m])
)
/
sum by (tool_family) (
  rate(app_ai_tool_execution_total[5m])
)
~~~

Tool error không đồng nghĩa business task failed; retry hoặc fallback có thể vẫn hoàn tất tác vụ.

### 11.7. Task verified success rate

~~~promql
sum by (task_type) (
  rate(app_ai_task_outcome_total{outcome="verified_success"}[1h])
)
/
sum by (task_type) (
  rate(app_ai_task_outcome_total{
    outcome=~"verified_success|failed|abandoned"
  }[1h])
)
~~~

Chỉ dùng terminal outcomes làm denominator. Nếu outcome đến trễ, phải dùng mature cohort hoặc tính trong result store/warehouse; hai Counter theo cửa sổ rate không tự bảo đảm cùng một task cohort.

### 11.8. Cost per verified success

Nếu cost và outcome đã được phân bổ theo cùng cohort/time attribution và cùng currency:

~~~promql
sum by (task_type, currency) (
  rate(app_ai_model_cost_amount_sum[1h])
)
/
on (task_type) group_left
sum by (task_type) (
  rate(app_ai_task_outcome_total{outcome="verified_success"}[1h])
)
~~~

DistributionSummary ghi một sample cost cho mỗi model call; Prometheus sum là tổng cost tích lũy. Vector matching giữ riêng từng currency trong kết quả, không cộng các currency với nhau. Query chỉ là ví dụ khi cost đã được quy về task_type và cùng cohort với outcome. Nếu model cost được ghi ở call time nhưng verified success đến sau, numerator/denominator có thể lệch cohort. Với phân bổ chính xác, join theo task ở result store/warehouse rồi tạo summary metric.

## 12. Thực hiện baseline run

Baseline là mốc so sánh. Chạy theo checklist và lưu log từng bước.

### 12.1. Preflight

Trước khi chạy:

- [ ] Git working tree và commit/revision được ghi nhận.
- [ ] JDK/build tool/dependency versions đã pin.
- [ ] Profile lab đang active.
- [ ] Secrets đến từ environment/secret store, không nằm trong file evidence.
- [ ] Compose project, DB/schema và vector namespace là riêng cho lab.
- [ ] Dataset schema hợp lệ và checksum đã tạo.
- [ ] Policy corpus/index version đã ghi.
- [ ] Tool fixture service trả đúng dữ liệu mong đợi.
- [ ] Prometheus scrape target UP.
- [ ] Tracing exporter nhận được test span.
- [ ] Dashboard query trả dữ liệu health/metrics.

Nếu một check bắt buộc thất bại, dừng run và ghi lý do. Không bắt đầu baseline khi telemetry hoặc fixture chưa sẵn sàng.

### 12.2. Tạo manifest trước khi chạy

Ví dụ run-manifest.json:

~~~json
{
  "run_id": "lab-run-20261127-baseline",
  "mode": "offline",
  "revision": "git-commit-sha",
  "dataset": {
    "name": "support-eval",
    "version": "1.2.0",
    "sha256": "dataset-checksum"
  },
  "rubric": {
    "version": "rubric-3",
    "evaluator_version": "evaluators-2"
  },
  "application": {
    "profile": "lab",
    "prompt_version": "support-prompt-7",
    "tool_schema_version": "tools-4"
  },
  "models": {
    "answer_model": "pinned-model-id",
    "embedding_model": "pinned-embedding-id",
    "judge_model": "pinned-judge-id"
  },
  "retrieval": {
    "corpus_version": "policy-corpus-3",
    "index_version": "policy-index-3",
    "chunking_version": "chunker-2",
    "top_k": 5
  },
  "generation": {
    "temperature": 0,
    "max_output_tokens": 600
  },
  "started_at": "2026-11-27T14:00:00Z"
}
~~~

Các giá trị là ví dụ. Manifest không được chứa API key, password, raw prompt hay customer data. Nếu provider không hỗ trợ pin version hoặc seed, ghi rõ alias/config thực tế và giới hạn tái lập.

### 12.3. Chạy runner

Một lab application có thể cung cấp endpoint nội bộ hoặc command riêng để chạy dataset. Ví dụ HTTP contract minh họa:

~~~json
{
  "run_id": "lab-run-20261127-baseline",
  "dataset_path": "artifacts/spring-ai-eval-lab/dataset/cases.jsonl",
  "mode": "offline",
  "capture_traces": true,
  "evaluator_set": ["schema", "retrieval", "fact_check", "groundedness"]
}
~~~

~~~powershell
$body = Get-Content -Raw .\lab\run-request.json
Invoke-RestMethod -Method Post -Uri http://localhost:8080/internal/evaluations/runs -ContentType "application/json" -Body $body
~~~

Endpoint trên là endpoint do lab app tự xây dựng, không phải endpoint mặc định của Spring AI. Có thể thay bằng CLI runner của project; cần giữ cùng input/output contract.

### 12.4. Theo dõi run

Trong lúc chạy, kiểm tra:

- Số case started/completed.
- Evaluator execution outcome.
- Tool/model/retrieval errors.
- Run in-flight và queue depth.
- Prometheus target health.
- Trace sampling/export success.
- Provider rate limit/quota.

Không chỉ đợi runner kết thúc rồi mới xem metrics. Nếu telemetry mất giữa run, report cần ghi partial coverage.

### 12.5. Chốt baseline

Sau khi runner kết thúc:

1. Đợi tất cả async evaluator jobs hoàn tất hoặc chuyển trạng thái terminal.
2. Xác minh expected cases và completed cases.
3. Đối chiếu result store với metric counts.
4. Kiểm tra evaluator timeout/error.
5. Tạo summary và export raw case results.
6. Lưu trace references và scrape snapshot.
7. Ghi finished_at, duration và run status vào manifest.

Không đánh dấu baseline complete nếu có case pending mà chưa công bố coverage.

## 13. Chạy candidate và so sánh công bằng

Candidate là phiên bản có thay đổi được kiểm tra, ví dụ prompt template hoặc model. Giữ mọi điều kiện khác cố định nếu muốn quy kết tác động cho biến đó.

### 13.1. Chỉ thay một nhóm biến

Ví dụ prompt experiment:

| Thành phần | Baseline | Candidate |
| --- | --- | --- |
| Dataset | support-eval v1.2.0 | Cùng version |
| Rubric/evaluator | rubric-3/evaluators-2 | Cùng version |
| Answer model | pinned-model-A | Cùng model |
| Prompt | support-prompt-7 | support-prompt-8 |
| Embedding/index | policy-index-3 | Cùng index |
| Tool fixtures | orders-fixture-4 | Cùng fixture |
| Sampling | 100% offline cases | Cùng policy |

Nếu mục tiêu là model comparison, đổi model nhưng giữ prompt/rubric/dataset và các thành phần còn lại càng ổn định càng tốt.

### 13.2. Chạy lại đúng dataset

Candidate phải chạy cùng case set và cùng ordering nếu runner có thể giữ thứ tự. Nếu case bị skip hoặc evaluator unavailable, lưu trạng thái đó; không xóa case khỏi denominator âm thầm.

### 13.3. Comparison table

| Metric | Baseline | Candidate | Chênh lệch | Diễn giải |
| --- | ---: | ---: | ---: | --- |
| Completed cases | 100 | 100 | 0 | Coverage đủ |
| Relevance PASS | 92% | 95% | +3 pp | Tăng |
| Groundedness PASS | 96% | 91% | -5 pp | Regression cần điều tra |
| Tool selection accuracy | 98% | 98% | 0 pp | Không đổi |
| Evaluator error rate | 1% | 1% | 0 pp | Cùng availability |
| p95 task duration | 2.8 s | 3.1 s | +0.3 s | Chậm hơn |
| Cost per verified success | 0.012 | 0.011 | -8.3% | Giảm nếu cùng currency/cohort |

Các số liệu chỉ minh họa. pp là percentage points. Luôn ghi numerator/denominator và sample size bên cạnh tỷ lệ.

### 13.4. Không gộp verdict và evaluator status

Report cần có ít nhất:

- PASS.
- FAIL.
- INCONCLUSIVE.
- NOT_APPLICABLE.
- SKIPPED.
- EVALUATOR_TIMEOUT/ERROR.
- NOT_COMPLETED/PENDING.

Quality pass rate dùng mẫu số đã định nghĩa (thường PASS + FAIL). Evaluation coverage cho biết bao nhiêu ca được chấm; evaluator error rate cho biết khả năng chạy judge. Không dùng một tỷ lệ để thay thế tất cả.

### 13.5. Đọc score distribution

Mean score tăng không đảm bảo mọi nhóm đều tốt hơn. Xem histogram/SLO buckets, p50/p90 nếu histogram phù hợp, tỷ lệ score dưới ngưỡng và breakdown theo task_type/criterion. Với dataset nhỏ, đọc case-level diffs và evidence thay vì dựa vào quantile không ổn định.

## 14. Tạo report và lưu evidence pack

Evidence pack cần đủ thông tin để reviewer kiểm tra kết luận mà không cần tin vào một screenshot.

### 14.1. Summary schema

Ví dụ summary.json:

~~~json
{
  "run_id": "lab-run-20261127-baseline",
  "status": "incomplete",
  "dataset_version": "1.2.0",
  "expected_cases": 100,
  "started_cases": 100,
  "completed_cases": 98,
  "pending_cases": 2,
  "criteria": {
    "relevance": {
      "pass": 90,
      "fail": 6,
      "inconclusive": 2,
      "not_applicable": 0,
      "coverage": 0.98,
      "pass_rate_decided": 0.9375
    }
  },
  "evaluator": {
    "attempts": 102,
    "success": 100,
    "timeout": 1,
    "error": 1
  },
  "quality_gates": {
    "passed": false,
    "reasons": ["pending_cases_above_zero"]
  }
}
~~~

Các số liệu minh họa. Summary phải phân biệt case count với case-criterion count; một case có nhiều criteria không được tính thành nhiều logical tasks. Coverage formula và denominator phải ghi rõ trong report.

Với offline run, một cách tính đơn giản là:

\[
\text{Case completion coverage}
=\frac{\text{Selected cases có terminal run status}}
{\text{Selected cases}}
\]

Nếu đánh giá từng criterion riêng, tính criterion coverage tương tự trên số case-criterion được chọn. Không chia criterion completions cho logical cases expected. Nếu có sampling, ghi cả selected/eligible rate và completed/selected coverage.

### 14.2. Comparison report

comparison.md nên có:

1. Mục tiêu và giả thuyết thí nghiệm.
2. Biến được thay đổi và biến được giữ cố định.
3. Dataset/rubric/model/prompt/index/evaluator versions.
4. Expected, started, completed, pending và skipped counts.
5. Verdict distribution và score distribution theo criterion.
6. Business outcomes và operational metrics.
7. Evaluator availability/coverage.
8. Case-level regression/gain kèm evidence reference.
9. Quality gate result và lý do.
10. Giới hạn, non-determinism và quyết định tiếp theo.

### 14.3. Evidence manifest

Thêm thông tin hoàn tất:

- started_at và finished_at UTC.
- duration.
- runner version.
- application revision.
- dataset/rubric/prompt/model/evaluator versions.
- retrieval corpus/index/chunking versions.
- tool fixture version.
- expected/completed/pending counts.
- evidence file list và checksum.
- cleanup scope và cleanup status.

Không đưa secret value, access token, connection string hoặc raw personal data vào manifest.

### 14.4. Trace index

trace-index.json có thể map case ID sang trace reference và một vài span names/durations đã scrub:

~~~json
{
  "case_id": "order-status-001",
  "trace_ref": "trace-reference",
  "spans": [
    {"name": "chatclient.call", "duration_ms": 640},
    {"name": "tool.order_lookup", "duration_ms": 85},
    {"name": "evaluation.fact_check", "duration_ms": 12}
  ],
  "redaction": "applied"
}
~~~

Nếu tracing backend giữ trace lâu hơn evidence pack, có thể lưu trace reference và retention expiry thay vì export toàn bộ trace. Xác minh quyền truy cập trước khi chia sẻ trace URL.

## 15. Checksum và xác minh evidence

Checksum giúp phát hiện file bị thay đổi sau khi đóng gói. Nó không chứng minh nội dung đúng; nội dung vẫn cần review.

### 15.1. Tạo SHA-256 trên Windows PowerShell

Ví dụ chạy từ thư mục evidence:

~~~powershell
$evidenceRoot = (Resolve-Path .).Path
$checksumFile = Join-Path $evidenceRoot "checksums.sha256"
Get-ChildItem -File -Recurse | Where-Object { $_.FullName -ne $checksumFile } | Sort-Object FullName | Get-FileHash -Algorithm SHA256 | ForEach-Object { "$($_.Hash)  $($_.Path.Substring($evidenceRoot.Length + 1))" } | Set-Content -Encoding ascii $checksumFile
~~~

Lệnh này tạo checksum cho file hiện có trong evidence tree và loại chính file checksum khỏi phép tính. Nếu chạy lại sau khi đã có checksum, file cũ sẽ bị loại và được ghi lại.

### 15.2. Tạo SHA-256 trên Linux/macOS

~~~bash
find . -type f ! -name checksums.sha256 -print0 | sort -z | xargs -0 sha256sum > checksums.sha256
~~~

Đảm bảo lệnh chạy tại root của evidence pack. Nếu môi trường không có sort -z hoặc sha256sum, dùng công cụ checksum tương đương và ghi rõ trong manifest.

### 15.3. Verify checksum

Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 .\results\summary.json
Get-Content .\checksums.sha256
~~~

Linux/macOS:

~~~bash
sha256sum -c checksums.sha256
~~~

Đọc file list và xác minh các file quan trọng có mặt. Không chỉ kiểm tra checksum file; kiểm tra manifest tham chiếu đúng dataset, report và result files.

### 15.4. Evidence retention

Giữ evidence ở nơi có quyền truy cập và retention phù hợp. Nếu evidence chứa trace references hoặc model outputs, áp dụng cùng privacy/access policy như nguồn dữ liệu. Đừng gửi evidence pack qua kênh công khai chỉ vì đã scrub một phần.

## 16. Dọn dữ liệu lab an toàn

Cleanup là một bước của lab, không phải thao tác tùy tiện sau cùng. Mục tiêu là xóa runtime data của đúng lab sau khi evidence đã được xác minh.

### 16.1. Phân loại trước khi xóa

| Resource | Ví dụ | Hành động |
| --- | --- | --- |
| Evidence pack | Manifest, report, results, checksums | Giữ theo retention policy |
| Input fixtures | Synthetic dataset, policy corpus, order fixtures | Giữ source-controlled copy hoặc xóa bản runtime |
| Runtime database | Run rows, temporary task rows | Xóa schema/database lab |
| Vector index | Lab namespace/collection | Xóa đúng namespace lab |
| Object storage | Lab prefix | Xóa đúng prefix |
| Containers/networks | Compose project lab | Dừng và xóa |
| Volumes | Lab-only Postgres/Prometheus data | Xóa nếu không cần giữ |
| Grafana runtime | Lab folder/dashboard | Export dashboard rồi xóa folder lab nếu cần |
| Secrets | Temporary env file/token | Revoke/expire và xóa file local |

### 16.2. Thứ tự cleanup

1. Chốt run: không còn evaluator job, task hoặc queue message đang chạy.
2. Export report, results, scrape snapshots, dashboard definitions và trace index.
3. Tạo checksum và verify evidence.
4. Ghi danh sách resource có prefix/namespace lab.
5. Xóa lab vector namespace và object prefix.
6. Xóa lab database/schema hoặc truncate đúng các bảng lab.
7. Xóa Grafana folder/runtime data sau khi export dashboard.
8. Dừng và xóa Compose project/volumes lab.
9. Revoke/expire temporary credentials và xóa secret file.
10. Kiểm tra evidence pack vẫn còn và checksum vẫn hợp lệ.

### 16.3. Xóa Docker Compose project

Chỉ chạy khi đã xác minh Compose project name là đúng project lab và evidence đã được lưu:

~~~powershell
docker compose -p spring-ai-eval-lab -f compose.lab.yml ps
docker compose -p spring-ai-eval-lab -f compose.lab.yml down --volumes --remove-orphans
docker compose -p spring-ai-eval-lab -f compose.lab.yml ps
~~~

Tùy chọn volumes xóa các volume thuộc project Compose đó. Không chạy lệnh này nếu project name được dùng chung hoặc file Compose trỏ đến external/shared volumes. Xem output của config/ps và xác nhận volume ownership trước khi xóa.

### 16.4. Xóa vector namespace và database

Dùng API/admin command riêng của vector store hoặc database để xóa đúng namespace/schema lab. Trước khi thực hiện, kiểm tra:

- Namespace bắt đầu bằng prefix lab đã định.
- Database/schema owner là lab.
- Không có collection/volume dùng chung.
- Evidence và source fixtures đã được lưu.

Không dùng lệnh DROP DATABASE hoặc delete collection với tên lấy từ biến môi trường chưa validate. Trong script cleanup, allowlist project/database/namespace cụ thể và dừng nếu giá trị không khớp.

### 16.5. Cleanup report

Ghi cleanup-report.md:

~~~text
Run: lab-run-20261127-baseline
Evidence checksum: VERIFIED
Vector namespace: spring-ai-eval-lab (deleted)
Database schema: spring_ai_eval_lab (deleted)
Object prefix: lab/spring-ai-eval-lab/ (deleted)
Compose project: spring-ai-eval-lab (stopped and removed)
Prometheus/Grafana runtime: removed after export
Temporary credentials: revoked/expired
Evidence pack: retained at approved location
Unresolved resources: none
~~~

Thay nội dung ví dụ bằng kết quả thực tế. Nếu một resource không thể xóa, ghi tên, owner, lý do và bước tiếp theo; không báo cleanup complete khi chưa xác minh.

### 16.6. Kiểm tra sau cleanup

- [ ] Không còn container/network/volume thuộc lab Compose project.
- [ ] Lab vector namespace không còn.
- [ ] Lab database/schema hoặc runtime records đã được xóa.
- [ ] Lab object prefix không còn.
- [ ] Temporary credentials đã revoked/expired.
- [ ] Không còn file secret trong workspace/evidence.
- [ ] Evidence pack vẫn tồn tại.
- [ ] SHA-256 verification vẫn PASS.

Không xóa source-controlled dataset hoặc code fixture chỉ để dọn runtime data.

## 17. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Evaluation coverage thấp | Runner crash, evaluator timeout, queue backlog | Expected/started/completed counts, evaluator outcome, queue |
| PASS rate tăng bất thường | Nhiều case chưa được chấm bị loại khỏi mẫu số | Coverage, pending/skipped/inconclusive |
| Metric query rỗng | Scrape lỗi, meter lazy, tên/label sai, chưa đủ samples | Raw exposition, target UP, registry meter list |
| Trace không liên kết được case | Context propagation mất hoặc trace sampling | Trace exporter, propagation headers, trace index |
| Baseline/candidate lệch quá lớn | Dataset/index/rubric/model mix không giống nhau | Manifest diff và checksums |
| Retrieval recall giảm | Corpus/index/chunking/embedding/top-k thay đổi | Index version, fixture, ground truth |
| Tool success nhưng task fail | Tool response chưa chứng minh business postcondition | Source-of-truth verification và task event |
| Cost per success bằng N/A | Không có verified success hoặc cost attribution thiếu | Numerator, denominator, cohort, currency |
| Cleanup để sót volume | Volume external/shared hoặc project name sai | Compose config, labels và volume ownership |

### 17.1. No data không phải zero

Nếu query rỗng, trước tiên kiểm tra scrape health, series existence, meter registration và time range. Không thay empty vector thành zero trong dashboard quality nếu chưa chứng minh telemetry đầy đủ.

### 17.2. Model output khác giữa hai lần chạy

Kiểm tra model alias/version, provider routing, prompt checksum, generation parameters, index snapshot, tool fixture và judge version. Ghi non-determinism vào report; không sửa raw output để ép kết quả giống baseline.

### 17.3. Metrics không khớp result store

Đối chiếu unique run/case/criterion keys, retry attempts, commit/outbox status và metric emission. Result store là nơi giữ case-level source of truth; metrics là aggregate telemetry. Nếu có mismatch, đánh dấu run không hợp lệ và điều tra trước khi so sánh.

## 18. Quality gate và quyết định release

Một lab end-to-end cần kết thúc bằng quyết định có căn cứ, không chỉ một bảng số.

### 18.1. Ví dụ quality gate

Các ngưỡng dưới đây chỉ minh họa cách cấu trúc gate:

| Gate | Điều kiện ví dụ | Khi không đạt |
| --- | --- | --- |
| Dataset integrity | Dataset checksum và schema hợp lệ | Không chạy |
| Evaluation coverage | 100% selected cases có terminal evaluation state | Run incomplete |
| Evaluator availability | Timeout/error dưới ngưỡng đã chọn | Sửa evaluator/re-run |
| Relevance | PASS rate không giảm quá tolerance | Điều tra prompt/model |
| Groundedness | Không regression ở critical policy cases | Block release |
| Tool correctness | Không có unauthorized/wrong-side-effect case | Block release |
| Latency | p95 trong budget | Điều tra pipeline |
| Cost | Cost per verified success trong budget | Tối ưu cost |
| Evidence | Manifest, results, traces và checksum hợp lệ | Không publish kết luận |

Không dùng cùng một threshold cho mọi sản phẩm. Gate phải có owner, lý do, mẫu số tối thiểu và hành động khi vi phạm.

### 18.2. Gate theo critical cases

Một aggregate PASS rate có thể che một lỗi hiếm nhưng nghiêm trọng. Xác định critical cases như:

- Không tiết lộ dữ liệu đơn hàng của người khác.
- Không tạo refund nếu policy không cho phép.
- Không bịa thời hạn hoặc điều kiện hoàn tiền.
- Không tuyên bố transaction hoàn tất khi source of truth chưa xác nhận.
- Handoff khi thiếu evidence hoặc cần phê duyệt.

Critical cases có thể yêu cầu zero critical failures trong regression suite. Một critical failure không được bù bằng nhiều case dễ PASS.

### 18.3. Gate phải tính coverage

Ví dụ candidate có 100 cases expected nhưng chỉ 70 được chấm; trong 70 ca đó 69 PASS. Pass rate 98,6% nghe tốt nhưng coverage chỉ 70%. Không chấp nhận gate nếu evaluator availability hoặc pending cases khiến mẫu số thiếu.

### 18.4. Release decision

Một report cuối nên chọn một trạng thái:

- ACCEPT: gate đạt, evidence đầy đủ.
- REJECT: quality/guardrail regression rõ ràng.
- HOLD: thiếu coverage/evidence hoặc uncertainty quá lớn.
- RE-RUN: run không hợp lệ do infra/evaluator/data setup.

HOLD và RE-RUN không phải quality FAIL. Chúng cho biết chưa có bằng chứng đủ để ra quyết định.

## 19. Runbook tái lập từ đầu đến cuối

Đây là thứ tự chuẩn để một người khác chạy lại lab. Ghi timestamp và operator/tool version trong run log.

### Phase A — Chuẩn bị

1. Checkout revision được chỉ định.
2. Xác minh JDK/build tool/dependency versions.
3. Tạo env từ template và inject sandbox secrets.
4. Tạo Compose project, database/schema và vector namespace riêng.
5. Khởi động dependencies và xác minh health.
6. Seed policy corpus và order fixtures.
7. Validate dataset, ground truth và checksum.
8. Xác minh Prometheus scrape và tracing bằng smoke test.

### Phase B — Baseline

1. Tạo run ID và manifest.
2. Chạy cùng dataset đã pin.
3. Theo dõi coverage, evaluator outcome, tool/model/retrieval errors.
4. Đợi tất cả jobs terminal.
5. Export case-level results, summary, metric snapshots và trace index.
6. Ghi run completion và checksum.

### Phase C — Candidate

1. Thay đúng biến thí nghiệm đã khai báo.
2. Xác minh các dependency/config khác không đổi.
3. Tạo manifest candidate.
4. Chạy lại cùng dataset, fixtures và evaluator.
5. Export cùng loại evidence.
6. Tính comparison và quality gate.

### Phase D — Review

1. Kiểm tra numerator/denominator/coverage.
2. Đọc critical case diffs.
3. Đối chiếu traces với latency/error metrics.
4. Kiểm tra score/verdict distribution và evaluator calibration.
5. Ghi quyết định ACCEPT/REJECT/HOLD/RE-RUN cùng lý do.

### Phase E — Evidence và cleanup

1. Đóng gói evidence.
2. Tạo và verify SHA-256.
3. Xác nhận evidence được lưu ở nơi được phép.
4. Dọn vector namespace, DB/schema, object prefix, dashboard runtime và Compose volumes của lab.
5. Revoke/expire temporary credentials.
6. Chạy post-cleanup checklist.
7. Ghi cleanup report và đóng run.

Không bắt đầu cleanup trước khi evidence đã được verify. Nếu run cần điều tra thêm, có thể giữ runtime data theo thời hạn được phê duyệt và ghi rõ lý do.

## 20. Bài thực hành tổng hợp

**Bối cảnh:** team phát hành prompt support-prompt-8 cho trợ lý Spring AI. Họ muốn biết candidate có cải thiện kết quả khách hàng hay chỉ làm thay đổi technical metrics.

### Phần A — Tạo điều kiện tái lập

1. Chọn dataset có tối thiểu policy question, order lookup, unsupported question và chat-only.
2. Ghi dataset version/checksum, rubric, prompt, model, embedding, index và tool fixture versions.
3. Tạo namespace lab và synthetic fixtures.
4. Viết manifest baseline.
5. Chạy smoke test và xác minh scrape/trace.

### Phần B — Chạy evaluation

1. Chạy 100% offline dataset trên baseline.
2. Ghi từng case-criterion verdict.
3. Chạy evaluator retry có chủ đích để xác minh execution attempts khác verdict count.
4. Chạy candidate chỉ thay prompt.
5. Lưu raw results và run summaries.

### Phần C — Phân tích

Baseline:

- 120 expected cases.
- 120 completed cases.
- Relevance PASS 110/120.
- Groundedness PASS 114/120.
- Tool selection PASS 38/40 tool cases.
- p95 task duration 3,0 giây.
- Cost per verified success 0,015 đơn vị tiền tệ.

Candidate:

- 120 expected cases.
- 116 completed cases.
- Relevance PASS 109/116.
- Groundedness PASS 101/116.
- Tool selection PASS 39/40 tool cases.
- p95 task duration 3,4 giây.
- Cost per verified success 0,013 đơn vị tiền tệ.
- Evaluator timeout 4 cases.

Trả lời:

1. Candidate có thể được ACCEPT ngay không? Vì sao?
2. Groundedness thay đổi bao nhiêu percentage points trên completed cases?
3. Coverage candidate là bao nhiêu?
4. Có thể kết luận tool selection cải thiện nếu chỉ có 40 tool cases không?
5. Bốn evaluator timeout ảnh hưởng quality verdict hay evaluator availability?
6. Cần xem critical case evidence nào trước khi quyết định?
7. Nếu p95 tăng nhưng cost giảm, cần guardrail nào?
8. Candidate cần REJECT, HOLD hay RE-RUN nếu timeout tập trung ở evaluator?

### Phần D — Đóng gói và dọn dữ liệu

1. Tạo run-manifest cho baseline và candidate.
2. Lưu raw result JSONL, summary, comparison và trace index đã scrub.
3. Export Prometheus scrape snapshot và Grafana dashboard definition.
4. Tạo checksums.sha256 và verify.
5. Viết cleanup report.
6. Xóa đúng lab vector namespace, database/schema và Compose project.
7. Xác nhận evidence còn nguyên sau cleanup.

### Câu hỏi tự kiểm tra

- Vì sao manifest cần ghi cả embedding/index/evaluator version?
- Làm sao phân biệt evaluator retry với case được chấm nhiều lần?
- Vì sao result store phải commit trước khi emit metric?
- Metric label nào không được dùng vì cardinality?
- Vì sao một case có nhiều criteria không thể đếm thành nhiều tasks?
- Vì sao scrape snapshot và trace index là evidence hữu ích?
- Khi nào query PASS rate phải hiển thị N/A?
- Vì sao cost và verified success có thể lệch cohort?
- Làm sao biết candidate regression đến từ prompt thay vì index/evaluator?
- Khi nào quality gate nên trả HOLD hoặc RE-RUN?
- Vì sao phải verify checksum trước và sau cleanup?
- Làm sao bảo đảm cleanup không xóa shared resource?

## 21. Những điều cần ghi nhớ

1. **Tái lập bắt đầu từ manifest.** Pin revision, dataset, rubric, prompt, model, embedding/index, tool fixture và evaluator version.
2. **Dataset phải có ground truth được xác nhận.** Không để model tự tạo đáp án chuẩn cho chính nó.
3. **Baseline và candidate chỉ nên khác biến đang kiểm tra.** Nếu thay nhiều thành phần, không thể attribution rõ.
4. **Tách runtime data và evidence.** Có thể xóa môi trường lab sau khi lưu report, results, trace references và checksums.
5. **Metric và trace có vai trò khác nhau.** Metrics cho xu hướng; traces và case records giải thích từng lần chạy.
6. **Evaluator execution khác quality verdict.** Timeout/error làm giảm coverage, không tự động là answer FAIL.
7. **Một case có nhiều criteria.** Báo case count và case-criterion count riêng.
8. **Không dùng ID hoặc nội dung tự do làm metric labels.** Lưu references trong result store/trace đã scrub.
9. **So sánh phải có numerator, denominator và coverage.** Aggregate score có thể che critical failure hoặc missing cases.
10. **Quality gate cần guardrails và critical cases.** Một số lỗi nghiêm trọng không được bù bằng aggregate PASS rate.
11. **Checksum hỗ trợ integrity, không chứng minh correctness.** Reviewer vẫn phải kiểm tra nội dung và manifest.
12. **Cleanup có scope và thứ tự.** Chỉ xóa namespace/database/volume đã xác minh thuộc lab; giữ evidence theo retention policy.

## Tài liệu tham khảo

- [Spring AI Reference — Evaluation](https://docs.spring.io/spring-ai/reference/api/evaluation.html): hỗ trợ đánh giá response và xây evaluator.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): observations cho ChatClient/model/tool.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registry và endpoint metrics.
- [Micrometer Reference — Meter Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): meter, registry, tags và cardinality.
- [Micrometer Reference — Observations](https://docs.micrometer.io/micrometer/reference/observation.html): custom observations và key values.
- [Prometheus — Querying Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/): selectors, vectors và query behavior.
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): histogram buckets và quantiles.
- [OpenTelemetry — Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/): trace/span context và attributes.
- [OpenTelemetry — Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/): metric instruments và aggregation.
- [Docker Compose — Project names](https://docs.docker.com/compose/how-tos/project-name/): cô lập resource theo Compose project.
- [Docker Compose — Down](https://docs.docker.com/reference/cli/docker/compose/down/): vòng đời container, network và volume khi cleanup.

**Lưu ý phiên bản:** API evaluation/observability của Spring AI, Micrometer naming, Prometheus exposition và Compose behavior phụ thuộc phiên bản/cấu hình. Các endpoint, metric names, JSON schema và Compose file trong bài là contract minh họa cần được hiện thực trong lab project. Trước khi chạy cleanup, xác minh resource ownership và giữ evidence đã kiểm tra checksum.
