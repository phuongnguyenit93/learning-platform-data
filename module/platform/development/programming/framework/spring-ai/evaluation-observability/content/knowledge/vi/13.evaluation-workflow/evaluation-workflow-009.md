# Giữ khả năng truy ngược báo cáo đến từng đầu vào và bằng chứng

Một báo cáo đánh giá Spring AI cho biết tỷ lệ factual correctness giảm từ 98% xuống 91%. Con số này báo động, nhưng đội phát triển vẫn chưa biết phải mở dữ liệu nào để tìm nguyên nhân. Họ cần lần ngược từ chỉ số trong báo cáo đến các case tạo nên mẫu số, từng attempt, câu hỏi đầu vào, prompt thực tế, tài liệu RAG đã truy xuất, context gửi vào model, câu trả lời, tool events, verdict của evaluator và trace kỹ thuật.

Nếu báo cáo chỉ lưu một con số và vài dòng nhận xét, việc điều tra sẽ phải chạy lại ứng dụng hoặc phỏng đoán. Chạy lại có thể cho answer khác vì model có tính xác suất, corpus đã thay đổi hoặc provider đã cập nhật model alias. Bằng chứng lúc sự cố xảy ra có thể đã mất.

**Data provenance và evidence lineage** giải quyết vấn đề này bằng cách lưu nguồn gốc, phiên bản, quan hệ và tính toàn vẹn của dữ liệu tạo nên một kết quả đánh giá. Mỗi kết luận trong báo cáo phải dẫn được tới các bản ghi và artifact đã tạo ra nó; mỗi artifact quan trọng phải cho biết nó đến từ đâu, thuộc run/attempt nào, được tạo khi nào và có thể kiểm chứng ra sao.

Trong module **SPRING_AI_EVALUATION_OBSERVABILITY**, khả năng truy ngược giúp nhóm giải thích vì sao relevance, fact checking, RAG hoặc tool calling đạt hay không đạt; đối chiếu prompt/model/pipeline; và nối quality verdict với metrics, traces, token, chi phí và độ trễ. Mục tiêu là tạo một chuỗi bằng chứng có thể kiểm tra, có kiểm soát truy cập và đủ bền vững cho việc audit.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt provenance, lineage, evidence, trace và report artifact.
2. Thiết kế chuỗi truy ngược từ summary metric tới case, attempt và đầu vào thực tế.
3. Xác định các input/version cần lưu cho dataset, prompt, model, RAG, tool, evaluator và report builder.
4. Phân biệt template prompt với prompt/context thực tế đã gửi tới model.
5. Lưu retrieval results, effective context, tool events, answer và evaluator evidence bằng định danh ổn định.
6. Dùng manifest bất biến, content digest và schema version để kiểm tra tính toàn vẹn.
7. Nối evidence với Spring AI observations/traces mà không giả định mọi trace luôn tồn tại.
8. Thiết kế report drill-down và liên kết bằng chứng cho từng verdict.
9. Xử lý dữ liệu thiếu, redaction, quyền truy cập và thời hạn lưu trữ.
10. Đánh giá mức độ tái lập thực tế khi provider/model hoặc dữ liệu bên ngoài thay đổi.
11. Xây mô hình provenance bằng Java, JSON và JUnit.
12. Tạo quy trình điều tra một regression từ báo cáo đến nguyên nhân đã được xác minh.

## 2. Các khái niệm cần phân biệt

Những từ dưới đây liên quan chặt chẽ nhưng không thay thế nhau.

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Provenance** | Dữ liệu này đến từ đâu, ai/tác vụ nào tạo ra? | Answer được sinh bởi model nào, từ input nào? |
| **Lineage** | Các dữ liệu/artifact liên kết và biến đổi qua những bước nào? | Dataset → retrieval → context → answer → verdict |
| **Evidence** | Bằng chứng cụ thể hỗ trợ hoặc bác bỏ một kết luận là gì? | Document ID, answer ref, tool result, reference fact |
| **Trace** | Request đi qua các thành phần và thời gian ra sao? | ChatClient → VectorStore → ChatModel → tool |
| **Manifest** | Một run được cấu hình bằng những phiên bản/tham số nào? | Dataset digest, prompt version, model, rubric |
| **Report artifact** | Báo cáo được tạo từ dữ liệu và quy tắc nào? | summary.json, failures.jsonl, report.md |

Một trace kỹ thuật không tự chứng minh answer đúng. Một document ID được lưu không tự chứng minh model đã nhận nội dung tài liệu đó. Một verdict PASS không đủ audit nếu thiếu rubric, judge version và evidence refs.

### 2.1. Tư duy truy ngược

Bắt đầu từ câu hỏi của reviewer:

> Tại sao case POLICY-017 bị factual correctness FAIL trong run candidate-v5?

Một chuỗi truy ngược có thể là:

1. Report metric → case outcome POLICY-017.
2. Case outcome → accepted attempt ID.
3. Attempt → input snapshot và prompt/context refs.
4. Generation → model/provider, parameters, actual answer.
5. RAG → retrieved document IDs, ranking, effective context.
6. Reference → policy source và ngày hiệu lực.
7. Evaluator → rubric, judge, verdict, feedback.
8. Trace → thời gian retrieval/model và lỗi runtime liên quan.
9. Report builder → quy tắc aggregate và phiên bản tạo báo cáo.

Nếu một mắt xích không có dữ liệu, report phải chỉ ra rõ evidence nào thiếu. Không được tự suy ra nội dung đã không được capture.

## 3. Mô hình lineage từ dataset tới báo cáo

Một evaluation result không xuất hiện từ một lời gọi model duy nhất. Nó là sản phẩm của nhiều nguồn dữ liệu và bước xử lý.

~~~mermaid
flowchart TD
    A["Dataset snapshot + reference labels"] --> B["Case input + conversation context"]
    M["Run manifest + resolved config"] --> B
    B --> C["Prompt assembly / advisors"]
    C --> D["Retrieval + effective context"]
    D --> E["ChatModel request / response"]
    E --> F["Tool calls and results, if any"]
    F --> G["Final answer + execution outcome"]
    G --> H["Evaluator + rubric + judge"]
    R["Reference facts / trusted sources"] --> H
    D --> H
    H --> I["Metric verdicts + evidence refs"]
    G --> J["Metrics / traces / usage"]
    I --> K["Case outcome"]
    J --> K
    K --> L["Summary / failure list / report"]
    M --> L
~~~

Sơ đồ mô tả quan hệ logic; pipeline cụ thể có thể có nhiều model calls, nhiều tool rounds, query rewriting, reranking hoặc nhiều evaluator. Lineage nên phản ánh **các sự kiện thực tế** của attempt, không ép mọi run vào một đồ thị cố định chỉ có một model call.

### 3.1. Một nguyên tắc thiết kế

Mỗi artifact quan trọng có:

- Một định danh ổn định.
- Loại dữ liệu và schema version.
- Nguồn tạo ra và thời điểm.
- Quan hệ parent/child hoặc input/output.
- Run, case và attempt liên quan.
- Content digest nếu cần kiểm tra integrity.
- Quyền truy cập và retention policy.
- Trạng thái capture: available, redacted, sampled, expired, unavailable hoặc not applicable.

### 3.2. Hai hướng điều hướng

**Forward lineage:** từ dataset/input đi tới retrieval, answer, verdict và report.

**Backward lineage:** từ metric/report đi ngược tới các case, attempt và evidence nguồn.

Một hệ thống điều tra tốt hỗ trợ cả hai hướng. Forward lineage giúp hiểu tác động khi thay corpus/prompt; backward lineage giúp giải thích một con số hoặc lỗi cụ thể.

## 4. Định danh và khóa liên kết

Không dùng tên file hoặc thứ tự dòng làm định danh chính. Những giá trị này có thể đổi khi artifact được di chuyển hoặc report được xuất lại.

| ID | Phạm vi | Ví dụ |
| --- | --- | --- |
| runId | Một logical evaluation run | support-eval-v5 |
| caseId | Một tình huống trong dataset | POLICY-017 |
| attemptId | Một lần thực thi case | POLICY-017-attempt-2 |
| modelCallId | Một model invocation | model-call-8f31 |
| toolCallId | Một lần gọi tool | tool-call-a42c |
| artifactId | Một input/output/evidence artifact | artifact-answer-991 |
| evaluationId | Một lần chấm | eval-judge-v2-781 |
| metricVerdictId | Một verdict của metric | verdict-factual-17 |
| traceId / spanId | Telemetry correlation | ID do tracing system cấp |
| reportId | Một bản report cụ thể | report-v5-2026-05-18 |

### 4.1. ID cần bất biến trong phạm vi của nó

- Retry cùng logical case tạo attemptId mới.
- Một model call retry tạo call attempt mới hoặc call event mới, nhưng vẫn liên kết về case attempt.
- Chấm lại bằng judge version mới tạo evaluationId mới.
- Xuất lại report bằng report builder mới tạo reportId mới.
- Resume cùng logical run giữ runId, tạo resumeSessionId riêng nếu cần.
- Thay dataset/prompt/model/pipeline theo hợp đồng đánh giá thường tạo run mới.

Không tái sử dụng attemptId cho lần chạy mới chỉ vì cùng caseId.

### 4.2. Không dùng trace ID thay case ID

Một case có thể có nhiều traces do retries hoặc evaluator calls; một trace có thể chứa nhiều spans. Trace sampling cũng có thể khiến không có trace. Vì vậy, lưu liên kết attemptId → traceId/spanIds khi thực có, nhưng vẫn giữ định danh nghiệp vụ độc lập.

## 5. Run manifest: ảnh chụp cấu hình của phép đánh giá

Manifest mô tả **đánh giá đã được chạy như thế nào**. Nó cần lưu giá trị đã resolve, không chỉ tên alias hoặc đường dẫn cấu hình có thể thay đổi.

Ví dụ:

~~~yaml
schemaVersion: evaluation-run-manifest-v1
run:
  runId: support-eval-candidate-v5
  createdAt: "2026-05-18T10:00:00Z"
  runType: FULL_REGRESSION
  environment: ci
  commitId: "resolved-commit-sha"
  buildId: "build-2481"

dataset:
  datasetId: support-regression
  version: v5
  snapshotRef: artifact://datasets/support-regression/v5
  contentDigest: "sha256:..."
  selectedCaseCount: 500

application:
  springAiVersion: "resolved-version"
  promptTemplateVersion: support-prompt-v7
  promptTemplateDigest: "sha256:..."
  pipelineVersion: rag-v4
  advisorConfigurationDigest: "sha256:..."

model:
  provider: example-provider
  requestedModelId: chat-model-stable
  resolvedModelId: "provider-resolved-revision-if-available"
  parameters:
    temperature: 0
    maxOutputTokens: 800

rag:
  corpusVersion: policy-v3
  indexSnapshotRef: artifact://indexes/policy-v3
  embeddingModel: embedding-v2
  chunkingVersion: chunker-v3
  retrievalTopK: 5
  filterConfigurationDigest: "sha256:..."

tools:
  toolSchemaVersion: support-tools-v4
  fixtureVersion: order-fixtures-v2
  authorizationPolicyVersion: auth-policy-v3

evaluation:
  rubricVersion: support-rubric-v3
  judgeProvider: example-provider
  judgeModel: judge-model-v2
  judgePromptDigest: "sha256:..."
  aggregationPolicyVersion: aggregate-v2

report:
  reportBuilderVersion: report-builder-v3
  outputSchemaVersion: evaluation-report-v2
~~~

Các giá trị minh họa. Đây là schema do hệ thống đánh giá thiết kế, không phải file cấu hình Spring AI bắt buộc.

### 5.1. Manifest cần giá trị đã resolve

Nếu manifest chỉ lưu model alias stable, sau vài ngày alias có thể trỏ sang model revision khác. Lưu requested ID và resolved ID nếu provider cung cấp. Nếu không thể pin revision, ghi rõ giới hạn reproducibility.

Tương tự, đường dẫn latest-index hoặc current-rubric không đủ. Hãy lưu snapshot/version/digest và reference bất biến có thể truy xuất.

### 5.2. Phân biệt cấu hình dự kiến với cấu hình thực thi

Manifest mô tả cấu hình run dự kiến. Attempt-level provenance ghi cấu hình và metadata thực tế quan sát được: model response metadata, tool selection, actual retrieval results, retry count và effective context. Nếu runtime/provider tự thay đổi tham số, report cần ghi nhận khác biệt thay vì giả định manifest đã phản ánh hết.

## 6. Theo dấu từng đầu vào của case

Dataset case có thể chứa nhiều trường, nhưng report không nhất thiết phải lưu raw input trong mọi nơi. Cần giữ đủ thông tin để xác định **input nào đã được dùng**, bằng artifact ref có quyền truy cập.

Một input record có thể gồm:

~~~json
{
  "artifactId": "input-POLICY-017-v1",
  "artifactType": "CASE_INPUT",
  "schemaVersion": "case-input-v2",
  "runId": "support-eval-candidate-v5",
  "caseId": "POLICY-017",
  "source": {
    "datasetId": "support-regression",
    "datasetVersion": "v5",
    "sourceRecordId": "POLICY-017",
    "sourceRef": "artifact://datasets/support-regression/v5/POLICY-017"
  },
  "content": {
    "storageRef": "secure://evidence/input/POLICY-017",
    "contentDigest": "sha256:...",
    "redactionProfile": "evaluation-safe-v2"
  },
  "createdAt": "2026-05-18T10:00:01Z"
}
~~~

### 6.1. Ghi input đã chuẩn hóa và input thực sự gửi

Có thể có nhiều dạng input:

- Raw dataset record.
- Input sau schema validation/normalization.
- Conversation history sau khi chọn các lượt liên quan.
- Query sau khi rewrite.
- Prompt variables sau khi template binding.
- Prompt/context cuối cùng gửi cho model.

Nếu các bước này có thể làm thay đổi nội dung, hãy lưu quan hệ derivedFrom và digest/ref cho từng phiên bản cần điều tra.

### 6.2. Không chỉ lưu template prompt

Ví dụ template:

~~~text
Bạn là trợ lý chính sách.
Hãy trả lời dựa trên tài liệu sau:
{context}
Câu hỏi: {question}
~~~

Template này không cho biết model đã thực sự nhận context nào. Prompt thực tế còn phụ thuộc variables, system/developer instructions, conversation history, advisors, query rewrite và truncation.

Để truy ngược generation, cần lưu template version/digest **và** rendered/effective request hoặc các phần cấu thành đủ để tái dựng, theo chính sách bảo vệ dữ liệu. Nếu không được phép lưu raw prompt, lưu secure reference, digest và redacted representation; phải nói rõ rằng digest không thể thay thế nội dung để review ngữ nghĩa.

### 6.3. Input lineage của hội thoại nhiều lượt

Với memory, ghi các message IDs/lượt được đưa vào context, session/conversation reference đã pseudonymize, memory policy/version và thao tác trim/summarize. Không chỉ ghi session ID rồi giả định toàn bộ history đã được model nhận.

## 7. Provenance của prompt assembly và model invocation

Một model invocation nên truy được:

- modelCallId và parent attempt.
- Provider, requested/resolved model ID.
- Prompt template version/digest.
- Rendered input hoặc secure reference.
- Generation parameters thực tế.
- Tool definitions/schema được cung cấp.
- Thời điểm gọi, timeout/retry metadata.
- Response reference, finish reason và usage.
- Trace/span reference nếu có.

### 7.1. Ví dụ model call record

~~~json
{
  "modelCallId": "model-call-8f31",
  "runId": "support-eval-candidate-v5",
  "caseId": "POLICY-017",
  "attemptId": "POLICY-017-attempt-1",
  "callSequence": 1,
  "provider": "example-provider",
  "requestedModelId": "chat-model-stable",
  "resolvedModelId": "model-revision-if-exposed",
  "promptArtifactRef": "secure://evidence/rendered-prompt/8f31",
  "promptDigest": "sha256:...",
  "parameterSnapshotRef": "artifact://model-params/8f31",
  "toolSchemaVersion": "support-tools-v4",
  "requestStartedAt": "2026-05-18T10:00:03Z",
  "responseReceivedAt": "2026-05-18T10:00:04Z",
  "status": "SUCCEEDED",
  "responseArtifactRef": "secure://evidence/model-response/8f31",
  "usage": {
    "inputTokens": 1680,
    "outputTokens": 185
  },
  "traceRef": {
    "traceId": "actual-trace-id",
    "spanId": "actual-span-id"
  }
}
~~~

Dữ liệu chỉ minh họa. Nếu provider không trả resolved model revision hoặc usage, lưu NOT_PROVIDED/UNKNOWN thay vì bịa giá trị.

### 7.2. Một case có nhiều model calls

Tool calling thường có vòng lặp:

1. Model chọn tool và tạo arguments.
2. Ứng dụng thực thi tool.
3. Kết quả tool được đưa lại vào conversation.
4. Model tạo answer cuối.

Mỗi model invocation phải có callSequence/parent relation và artifact refs riêng. Không chỉ lưu request đầu tiên và final answer rồi tuyên bố đã truy vết đầy đủ.

## 8. RAG provenance: truy được từ câu trả lời tới tài liệu thực sự

RAG cần nhiều hơn danh sách document IDs. Một report có thể nói retrieval hit@5 PASS nhưng không thể giải thích nếu không biết query, filters, thứ tự kết quả và context cuối.

### 8.1. Retrieval event

Một retrieval record nên lưu:

- Query thực tế đã gửi tới retriever (hoặc secure ref).
- Query rewrite/version nếu có.
- VectorStore/index/corpus snapshot.
- Embedding model/version.
- Filters, tenant/scope và top-k.
- Danh sách retrieved IDs theo thứ tự.
- Score/rank nếu API cung cấp.
- Chunk ID, document version và source metadata.
- Latency, error và trace span ref.

Ví dụ:

~~~json
{
  "retrievalId": "retrieval-31",
  "attemptId": "POLICY-017-attempt-1",
  "queryArtifactRef": "secure://evidence/retrieval-query/31",
  "corpusVersion": "policy-v3",
  "indexSnapshotRef": "artifact://indexes/policy-v3",
  "embeddingModel": "embedding-v2",
  "topK": 5,
  "filters": {
    "locale": "vi",
    "status": "CURRENT"
  },
  "results": [
    {
      "documentId": "policy-v3#refund-pro",
      "chunkId": "refund-pro-chunk-02",
      "rank": 1,
      "score": 0.91,
      "documentVersion": "v3"
    },
    {
      "documentId": "faq-v2#refund",
      "chunkId": "faq-refund-chunk-01",
      "rank": 2,
      "score": 0.82,
      "documentVersion": "v2"
    }
  ],
  "traceRef": null
}
~~~

Score và filter fields là ví dụ; không phải mọi VectorStore đều trả cùng metadata.

### 8.2. Retrieved documents khác effective context

Pipeline có thể rerank, filter, deduplicate, compress, summarize, cắt token hoặc ghép context theo cửa sổ. Vì thế cần phân biệt:

1. **Retrieved set:** các tài liệu/chunk retriever trả về.
2. **Selected set:** các chunk còn lại sau rerank/filter.
3. **Effective context:** nội dung thực sự đi vào model request.

Nếu chỉ lưu retrieved set, không biết tài liệu nào bị loại hoặc nội dung nào đã bị cắt. Groundedness cần actual effective context; retrieval metrics cần actual retrieved results.

### 8.3. Context assembly record

~~~json
{
  "contextAssemblyId": "context-assembly-31",
  "attemptId": "POLICY-017-attempt-1",
  "derivedFrom": ["retrieval-31"],
  "selectedChunkIds": ["refund-pro-chunk-02"],
  "excludedChunkIds": ["faq-refund-chunk-01"],
  "truncationApplied": true,
  "effectiveContextRef": "secure://evidence/effective-context/31",
  "effectiveContextDigest": "sha256:...",
  "tokenEstimate": 720
}
~~~

Không suy effective context từ document ID nếu không capture content hoặc secure artifact reference. Khi context không được capture, verdict groundedness phải phản ánh giới hạn bằng NOT_EVALUATED hoặc trạng thái evidence gap theo rubric.

## 9. Tool provenance: ghi lời gọi, quyền và kết quả

Một tool call là một sự kiện quan trọng trong chuỗi hành vi AI. Cần biết model yêu cầu gì, ứng dụng thực thi gì và backend thực sự trả kết quả nào.

### 9.1. Những trường nên lưu

- toolCallId, attemptId, modelCallId đã đề xuất tool.
- Tool name và schema version.
- Arguments đã sanitize hoặc secure reference.
- Validation outcome.
- Authorization decision và policy version.
- Backend operation/request ID.
- Execution status, duration và error code.
- Result reference/digest.
- Idempotency key reference nếu có.
- Trace/span reference.

### 9.2. Ví dụ tool event

~~~json
{
  "toolCallId": "tool-call-a42c",
  "attemptId": "ORDER-004-attempt-1",
  "requestedByModelCallId": "model-call-91",
  "toolName": "getOrderStatus",
  "toolSchemaVersion": "support-tools-v4",
  "argumentsRef": "secure://evidence/tool-args/a42c",
  "argumentDigest": "sha256:...",
  "validationStatus": "VALID",
  "authorization": {
    "decision": "DENY",
    "policyVersion": "auth-policy-v3",
    "reasonCode": "ORDER_NOT_OWNED_BY_USER"
  },
  "backendOperationId": "backend-request-71",
  "executionStatus": "DENIED",
  "resultRef": "secure://evidence/tool-result/a42c",
  "durationMs": 38,
  "traceRef": null
}
~~~

Ví dụ mô tả ca bảo mật được từ chối. DENIED có thể là kết quả đúng theo test expectation và được chấm authorization PASS. Không đánh đồng với technical error.

### 9.3. Không dùng prompt làm ranh giới quyền

Provenance phải lưu quyết định authorization từ backend đáng tin cậy. Một model có thể đề xuất tool call, nhưng ứng dụng/backend mới là nơi xác minh user, tenant, resource ownership và quyền thực hiện.

Với tool side effect, ghi idempotency/operation refs và trạng thái đối soát; không lưu secret hoặc toàn bộ thông tin thanh toán vào report.

## 10. Answer và evaluator provenance

### 10.1. Answer artifact

Lưu answer cuối và liên kết với model call/tool results tạo ra nó. Nếu answer được post-process, cite, redact hoặc chuyển format sau generation, tạo artifact/transform event riêng thay vì ghi đè response gốc.

Ví dụ:

~~~json
{
  "answerArtifactId": "answer-POLICY-017-1",
  "attemptId": "POLICY-017-attempt-1",
  "finalModelCallId": "model-call-8f31",
  "toolCallIds": [],
  "contentRef": "secure://evidence/answers/POLICY-017-1",
  "contentDigest": "sha256:...",
  "postProcessingVersion": "answer-renderer-v2",
  "createdAt": "2026-05-18T10:00:05Z"
}
~~~

### 10.2. Evaluator input phải truy được

Một verdict relevance/groundedness/factual correctness cần biết:

- Question/input reference.
- Actual answer artifact.
- Effective context (nếu metric cần).
- Reference facts/documents.
- Rubric version.
- Judge model/provider/prompt version nếu dùng LLM judge.
- Human reviewer hoặc rule engine version nếu áp dụng.
- Evaluation attempt ID và timestamp.
- Feedback/reason code và evidence refs.

### 10.3. Ví dụ metric verdict

~~~json
{
  "metricVerdictId": "verdict-factual-17",
  "evaluationId": "eval-judge-v2-781",
  "caseId": "POLICY-017",
  "attemptId": "POLICY-017-attempt-1",
  "metric": "factualCorrectness",
  "status": "FAIL",
  "reasonCode": "WRONG_POLICY_WINDOW",
  "rubricVersion": "support-rubric-v3",
  "judgeVersion": "judge-v2",
  "inputRefs": [
    "input-POLICY-017-v1",
    "answer-POLICY-017-1",
    "policy-v3#refund-pro"
  ],
  "evidenceRefs": [
    "secure://evidence/answers/POLICY-017-1",
    "artifact://policy/policy-v3/refund-pro"
  ],
  "feedback": "Answer states 30 days; current reference states 14 days."
}
~~~

Feedback là ví dụ và cần được xử lý ngôn ngữ/ẩn danh phù hợp. Không dùng feedback làm metric label có cardinality cao.

### 10.4. Judge retry và re-evaluation phải khác nhau

Retry cùng judge/rubric trên cùng evidence sau timeout có thể thuộc cùng evaluation operation với attempt riêng. Chấm lại bằng judge hoặc rubric version mới là evaluation mới. Không ghi đè verdict cũ, vì reviewer cần biết kết quả nào được dùng trong report tại thời điểm phê duyệt.

## 11. Lineage của metrics, traces, token và chi phí

Report quality cần liên kết được với telemetry để tìm nguyên nhân suy giảm hoặc chi phí tăng.

| Dữ liệu | Liên kết nên có | Câu hỏi điều tra |
| --- | --- | --- |
| End-to-end latency | run/case/attempt, request span | Case chậm ở stage nào? |
| Retrieval latency | retrieval event/span | VectorStore hay reranker chậm? |
| Model latency | modelCallId/span | Provider/model nào chậm? |
| Tool latency | toolCallId/backend operation | Tool/backend nào chậm? |
| Token usage | modelCallId và provider usage | Call nào dùng nhiều token? |
| Cost estimate | usage + price table version | Tính theo bảng giá nào? |
| Retry count | call/attempt + reason | Vì sao phát sinh request bổ sung? |
| Quality verdict | answer/context/reference refs | Vì sao FAIL? |
| Trace | traceId/spanId thật | Chuỗi thực thi kỹ thuật nào liên quan? |

### 11.1. Không gắn metrics với dữ liệu cardinality cao

Metrics backend phù hợp với labels có tập giá trị hữu hạn như stage, provider, status, model_family, suite. Không đưa raw prompt, user ID, case ID, trace ID hoặc URL có tham số vào metric labels.

Lưu IDs trong report/evidence store; metrics có thể được phân tích theo run/group thông qua artifact hoặc hệ thống truy vấn phù hợp.

### 11.2. Trace và evidence store có vai trò khác nhau

Trace thường có sampling và retention ngắn hơn evidence artifacts. Evidence store giữ answer/context/reference refs theo policy; trace giải thích thời gian và quan hệ giữa spans.

Lưu trace ID khi có, và trạng thái rõ khi không có. Không tự dựng trace từ log hoặc dùng trace ID giả. Nếu trace hết hạn nhưng evidence còn, report vẫn có thể kiểm nội dung nhưng không thể khẳng định xem lại được spans.

### 11.3. Cost cần lưu bảng giá và phương pháp

Một công thức ước tính:

\[
\mathrm{modelCost} =
\frac{\mathrm{inputTokens}\times\mathrm{inputPricePerMillion}}{10^6}
+
\frac{\mathrm{outputTokens}\times\mathrm{outputPricePerMillion}}{10^6}.
\]

Để tính lại được, lưu provider/model, usage theo từng model call, đơn vị tiền, priceTableVersion, timestamp/region nếu bảng giá phụ thuộc và cách tính cache/retry. Tách generation cost, evaluator cost và hạ tầng/tool cost.

## 12. Evidence graph và quan hệ derivedFrom

Một tập các JSON records rời rạc vẫn chưa đủ nếu không có quan hệ rõ ràng. Nên biểu diễn lineage bằng các node và edge.

### 12.1. Node types gợi ý

- DATASET_SNAPSHOT
- REFERENCE_SOURCE
- CASE_INPUT
- PROMPT_TEMPLATE
- RENDERED_PROMPT
- RETRIEVAL_EVENT
- CONTEXT_ASSEMBLY
- MODEL_CALL
- TOOL_EVENT
- ANSWER_ARTIFACT
- EVALUATION
- METRIC_VERDICT
- TRACE
- REPORT_ARTIFACT

### 12.2. Edge types gợi ý

| Edge | Ý nghĩa |
| --- | --- |
| CONTAINS | Dataset snapshot chứa case |
| DERIVED_FROM | Artifact được tạo từ input/artifact khác |
| USED_BY | Artifact được dùng ở bước sau |
| EMITTED_BY | Artifact do model/tool/evaluator tạo |
| EVALUATED_AGAINST | Answer được so với reference |
| OBSERVED_BY | Operation được quan sát bởi trace/metric |
| AGGREGATED_INTO | Verdict/case được tổng hợp vào report |
| SUPERSEDES | Artifact/version mới thay thế phiên bản trước |
| REDACTED_FROM | Bản redacted được tạo từ bản gốc |

### 12.3. Ví dụ graph

~~~mermaid
flowchart LR
    DS["Dataset snapshot"] --> CASE["Case input"]
    REF["Reference policy v3"] --> VERDICT["Factual verdict"]
    CASE --> PROMPT["Rendered prompt"]
    RET["Retrieved chunks"] --> CTX["Effective context"]
    PROMPT --> MC["Model call"]
    CTX --> MC
    MC --> ANSWER["Answer artifact"]
    ANSWER --> VERDICT
    CTX --> VERDICT
    RET --> RETRIEVAL["Retrieval evidence"]
    TOOL["Tool event"] --> ANSWER
    VERDICT --> CASEOUT["Case outcome"]
    CASEOUT --> REPORT["Report artifact"]
    TRACE["Trace spans"] -. "observes" .-> MC
    TRACE -. "observes" .-> RET
~~~

Trong hệ thống thật, graph có thể lưu dưới dạng relational foreign keys, document references, event log hoặc graph database. Không nhất thiết phải triển khai graph database; điều quan trọng là quan hệ có thể truy vấn và không bị mất khi xuất report.

## 13. Content digest, canonicalization và integrity

Một digest giúp kiểm tra artifact bytes có bị thay đổi so với lúc lưu hay không. Nhưng digest không chứng minh nội dung đúng, nguồn có thẩm quyền hoặc artifact được tạo từ pipeline đáng tin cậy.

### 13.1. Hash nội dung

Ví dụ SHA-256:

~~~text
contentDigest = SHA256(artifactBytes)
sha256:3d7f... (illustrative)
~~~

Nếu cùng bytes đầu vào, SHA-256 cho cùng digest. Khi tải artifact, tính lại digest và so sánh với manifest/metadata đã lưu.

### 13.2. Canonicalization trước khi hash structured data

JSON có thể biểu diễn cùng dữ liệu nhưng khác thứ tự keys, khoảng trắng hoặc cách escape. Nếu hash serialized JSON tùy ý, hai biểu diễn tương đương có thể cho digest khác nhau.

Cần quy định canonical serialization: encoding UTF-8, thứ tự keys ổn định, cách biểu diễn số/null, Unicode normalization nếu cần và loại bỏ field volatile như timestamp nếu digest chỉ nhằm kiểm nội dung logic.

Không được bỏ qua field có ý nghĩa nghiệp vụ. Ghi canonicalizationVersion để biết digest được tạo theo quy tắc nào.

### 13.3. Java: tính SHA-256 cho bytes đã canonicalize

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class ContentDigest {

    public static String sha256(byte[] canonicalBytes) {
        try {
            byte[] digest = MessageDigest
                    .getInstance("SHA-256")
                    .digest(canonicalBytes);

            return "sha256:" + HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(
                    "SHA-256 is required by the Java platform",
                    impossible);
        }
    }

    private ContentDigest() {}
}
~~~

Hàm trên nhận bytes đã được canonicalize. Nó không tự serialize object hoặc bảo đảm canonical JSON. Hãy tách canonicalization khỏi hashing để có thể kiểm thử từng bước.

### 13.4. Digest và chữ ký có vai trò khác nhau

Digest giúp phát hiện nội dung đổi khi so với digest tin cậy. Nếu cần xác minh artifact được phát hành bởi hệ thống/đơn vị nào, có thể dùng chữ ký số hoặc MAC với key được quản lý an toàn. Không lưu signing key trong report. Hash một file mà attacker có thể sửa cả file lẫn digest cùng lúc không chứng minh nguồn gốc.

## 14. Report phải truy ngược tới nguồn tạo ra con số

Một summary metric không nên chỉ có value 0.91. Nó cần mô tả phạm vi và tập dữ liệu dùng để tính.

Ví dụ:

~~~json
{
  "reportId": "report-candidate-v5-2026-05-18",
  "runId": "support-eval-candidate-v5",
  "metric": "factualCorrectnessPassRate",
  "value": 0.9286,
  "numerator": 455,
  "denominator": 490,
  "unit": "ratio",
  "denominatorDefinition": "Evaluated PASS + FAIL verdicts only",
  "datasetSnapshotRef": "artifact://datasets/support-regression/v5",
  "rubricVersion": "support-rubric-v3",
  "aggregationPolicyVersion": "aggregate-v2",
  "includedVerdictRefs": {
    "queryRef": "report-query:factual-pass-v2",
    "artifactRef": "artifact://reports/candidate-v5/factual-verdict-ids"
  },
  "excludedCounts": {
    "notEvaluated": 8,
    "technicalError": 2,
    "skipped": 0
  }
}
~~~

Các số liệu chỉ minh họa. Trong báo cáo thật, numerator/denominator phải đúng theo quy tắc đã công bố; ví dụ này không được hiểu là denominator luôn bao gồm NOT_EVALUATED.

### 14.1. Từ summary drill-down tới case

Khi mở metric, reviewer cần có thể:

1. Xem numerator/denominator và aggregation policy.
2. Mở tập verdict IDs đã được tổng hợp.
3. Lọc theo PASS/FAIL/NOT_EVALUATED.
4. Mở case outcome và accepted attempt.
5. Mở evidence refs cho answer, context, reference và evaluator.
6. Mở trace spans nếu trace còn tồn tại.
7. Xem config/version từ manifest.

Nếu report chỉ lưu queryRef nhưng query không còn chạy được do data store đã thay đổi, hãy lưu snapshot của tập ID hoặc kết quả truy vấn cần thiết theo policy.

### 14.2. Failure list cũng cần lineage

Một failure row tối thiểu có runId, caseId, attemptId, metric, reason code, severity, rubric/judge version và evidence refs. Với lỗi RAG, thêm retrieval/context refs; với tool, thêm tool event/backend operation refs; với lỗi kỹ thuật, thêm error stage và trace ref nếu có.

### 14.3. Report builder cũng là một phần của provenance

Hai report được tạo từ cùng verdicts nhưng khác aggregation logic có thể cho số khác nhau. Lưu reportBuilderVersion, outputSchemaVersion, query/filter definition và thời điểm tạo. Khi xuất lại report, tạo reportId mới hoặc revision rõ ràng; không âm thầm thay artifact đã dùng phê duyệt.

## 15. Missing evidence: ghi rõ điều không thể truy ngược

Không phải hệ thống nào cũng capture được mọi dữ liệu. Sampling, provider metadata, privacy policy, storage expiry hoặc instrumentation gap có thể làm thiếu evidence.

Dùng trạng thái có nghĩa:

| Evidence status | Ý nghĩa |
| --- | --- |
| AVAILABLE | Artifact có thể truy xuất và kiểm digest |
| REDACTED | Có bản redacted theo policy; raw data có thể bị hạn chế |
| SAMPLED_OUT | Không được capture do sampling policy |
| NOT_CAPTURED | Pipeline không thu thập trường này |
| EXPIRED | Đã hết retention hoặc bị xóa theo policy |
| ACCESS_DENIED | Artifact tồn tại nhưng người xem không có quyền |
| NOT_APPLICABLE | Không áp dụng cho case |
| UNKNOWN | Không xác định được trạng thái |

### 15.1. Missing trace không có nghĩa missing answer

Trace sampling có thể loại span nhưng answer/evidence store vẫn có. Report có thể kết luận nội dung dựa trên evidence còn tồn tại, nhưng phải nói không có trace để phân tích latency/span.

### 15.2. Missing effective context ảnh hưởng groundedness

Nếu không có actual context, không thể khẳng định answer được hỗ trợ bởi context nào. Verdict groundedness nên là NOT_EVALUATED hoặc evidence gap theo rubric. Không dùng expected/reference documents để thay thế.

### 15.3. Missing provider usage ảnh hưởng cost

Nếu provider không trả usage cho một timeout, cost có thể unknown. Report nên hiển thị unknown/estimated và nêu phương pháp, không gán 0.

### 15.4. Evidence không tồn tại phải tạo cảnh báo integrity

Nếu manifest nói có artifact ref nhưng artifact store trả not found hoặc digest mismatch, đây không chỉ là missing field. Nó là lỗi integrity/provenance, cần đánh dấu report không đầy đủ và cân nhắc block approval nếu artifact critical.

## 16. Quyền riêng tư, redaction và retention

Evidence lineage có thể chứa prompt, conversation history, context tài liệu, tool arguments, answer và user data. Khả năng truy ngược không đồng nghĩa mọi người đều được xem raw data.

### 16.1. Chia lớp dữ liệu

| Lớp | Ví dụ | Quyền gợi ý |
| --- | --- | --- |
| Report summary | Counts, rates, versions | Reviewer/engineering theo phạm vi |
| Operational metadata | Latency, tokens, status, trace IDs | SRE/engineering |
| Redacted evidence | Input/answer đã ẩn danh | QA/reviewer được phép |
| Raw evidence | Prompt/context/tool payload nguyên bản | Hạn chế theo need-to-know |
| Secrets | API keys, credentials, signing keys | Không đưa vào evidence/report |

### 16.2. Redaction cần lineage riêng

Không ghi đè raw artifact bằng bản đã che dữ liệu. Tạo artifact mới với:

- derivedFrom trỏ raw artifact.
- redactionProfile/version.
- redactedAt.
- digest của bản redacted.
- người/quy trình tạo và quyền truy cập.

Raw artifact và bản redacted có thể có retention khác nhau. Nếu raw artifact bị xóa theo policy, lineage nên giữ trạng thái EXPIRED/DELETED_BY_POLICY và metadata tối thiểu hợp lệ.

### 16.3. Không đưa raw content vào metrics tags

Không gắn prompt, answer, user ID, document content hoặc tool arguments vào Micrometer tags. Tags có thể được export tới nhiều backend và tạo high cardinality. Dùng artifact refs trong hệ thống có quyền; log/trace attributes cũng phải tuân thủ privacy và cardinality policy.

### 16.4. Access log cho việc xem evidence

Với evidence nhạy cảm, ghi audit event cho người hoặc service đọc artifact, mục đích, thời điểm và authorization outcome. Không ghi nội dung nhạy cảm vào chính access log.

## 17. Tính tái lập: truy ngược không đồng nghĩa chạy lại sẽ y hệt

Cần phân biệt bốn mức:

| Mức | Có thể đảm bảo điều gì? | Điều kiện |
| --- | --- | --- |
| **Traceability** | Biết input, config, evidence và quy trình tạo kết quả | Provenance refs đầy đủ |
| **Integrity** | Phát hiện artifact đã thay đổi | Digest/chữ ký và trusted metadata |
| **Re-executability** | Có đủ dữ liệu để chạy lại cùng pipeline gần tương đương | Snapshot, dependencies, config |
| **Bitwise reproducibility** | Output giống hệt từng byte | Cần môi trường/model/runtime xác định; thường không đảm bảo với provider hosted |

Một model hosted có thể thay đổi implementation phía server, dù requested model ID không đổi. Temperature bằng 0 không bảo đảm mọi provider trả cùng output. Retrieval có thể phụ thuộc index snapshot, ranking implementation và dữ liệu động.

Vì vậy, ưu tiên **lưu actual evidence** để giải thích kết quả đã xảy ra; lưu cấu hình và snapshot để tái thực thi khi khả thi. Không hứa bitwise reproducibility nếu provider không cho pin revision.

### 17.1. Re-evaluation khác rerun generation

Nếu muốn đổi judge/rubric, chấm lại answer/context đã lưu. Nếu muốn thử prompt/model mới, tạo generation run mới. Nếu muốn đo stochasticity, chạy repeated attempts có chủ đích. Các thao tác này có mục đích và định danh khác nhau.

### 17.2. Provenance của thay đổi dữ liệu chuẩn

Khi policy đổi, reference source và dataset labels mới phải có version, effective date, approval và quan hệ supersedes. Report lịch sử phải tiếp tục trỏ đúng chuẩn đã dùng lúc đánh giá, không tự cập nhật theo tài liệu mới nhất.

## 18. Java: mô hình provenance có kiểu rõ ràng

Ví dụ Java 17+ sau mô tả các định danh và liên kết tối thiểu. Đây là model trung lập với provider, không phải class có sẵn trong Spring AI.

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

public final class EvaluationProvenance {

    public record ArtifactRef(
            String artifactId,
            String artifactType,
            String schemaVersion,
            String storageRef,
            String contentDigest,
            String evidenceStatus) {

        public ArtifactRef {
            Objects.requireNonNull(artifactId);
            Objects.requireNonNull(artifactType);
            Objects.requireNonNull(schemaVersion);
            Objects.requireNonNull(evidenceStatus);
        }
    }

    public record VersionSnapshot(
            String datasetVersion,
            String datasetDigest,
            String promptVersion,
            String modelProvider,
            String requestedModelId,
            String resolvedModelId,
            String pipelineVersion,
            String corpusVersion,
            String rubricVersion,
            String judgeVersion,
            String reportBuilderVersion) {}

    public record LineageEdge(
            String fromArtifactId,
            String relation,
            String toArtifactId) {}

    public record AttemptProvenance(
            String runId,
            String caseId,
            String attemptId,
            VersionSnapshot versions,
            List<ArtifactRef> inputs,
            List<ArtifactRef> outputs,
            List<LineageEdge> edges,
            String traceId,
            Instant startedAt,
            Instant endedAt) {

        public AttemptProvenance {
            Objects.requireNonNull(runId);
            Objects.requireNonNull(caseId);
            Objects.requireNonNull(attemptId);
            Objects.requireNonNull(versions);
            inputs = List.copyOf(inputs);
            outputs = List.copyOf(outputs);
            edges = List.copyOf(edges);
        }
    }

    public record MetricVerdictProvenance(
            String evaluationId,
            String verdictId,
            String metric,
            String status,
            String rubricVersion,
            String judgeVersion,
            List<String> inputArtifactIds,
            List<String> evidenceArtifactIds,
            String reasonCode) {

        public MetricVerdictProvenance {
            inputArtifactIds = List.copyOf(inputArtifactIds);
            evidenceArtifactIds = List.copyOf(evidenceArtifactIds);
        }
    }

    public record ReportProvenance(
            String reportId,
            String runId,
            String reportBuilderVersion,
            String outputSchemaVersion,
            List<String> sourceCaseOutcomeIds,
            List<String> sourceVerdictIds,
            List<ArtifactRef> reportArtifacts,
            Instant generatedAt) {

        public ReportProvenance {
            sourceCaseOutcomeIds = List.copyOf(sourceCaseOutcomeIds);
            sourceVerdictIds = List.copyOf(sourceVerdictIds);
            reportArtifacts = List.copyOf(reportArtifacts);
        }
    }

    private EvaluationProvenance() {}
}
~~~

### 18.1. Vì sao dùng ArtifactRef?

Record này mô tả artifact có thể truy cập qua storage reference, nhưng không bắt mọi artifact phải có raw bytes trong report. Ví dụ report chỉ giữ secure reference tới prompt, còn reviewer được cấp quyền qua evidence service.

evidenceStatus cần dùng enum trong triển khai thật để tránh chuỗi tùy ý. storageRef có thể null khi NOT_CAPTURED, nhưng phải validate tổ hợp trường/status.

### 18.2. Không nhồi toàn bộ graph vào một JSON khổng lồ

Có thể lưu các node/edge riêng, hoặc lưu per-attempt manifest cùng refs. Điều quan trọng là có thể truy vấn hiệu quả theo runId, caseId, attemptId, artifactId, evaluationId và reportId.

## 19. Java: validator kiểm tính đầy đủ của lineage

Một validator đơn giản có thể bắt các liên kết bị thiếu trước khi report được publish.

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class ProvenanceValidator {

    public record ValidationIssue(
            String code,
            String subjectId,
            String message) {}

    public static List<ValidationIssue> validate(
            EvaluationProvenance.AttemptProvenance attempt) {

        Set<String> artifactIds = new HashSet<>();
        for (var artifact : attempt.inputs()) {
            if (!artifactIds.add(artifact.artifactId())) {
                return List.of(new ValidationIssue(
                        "DUPLICATE_ARTIFACT_ID",
                        artifact.artifactId(),
                        "Artifact ID appears more than once"));
            }
        }
        for (var artifact : attempt.outputs()) {
            if (!artifactIds.add(artifact.artifactId())) {
                return List.of(new ValidationIssue(
                        "DUPLICATE_ARTIFACT_ID",
                        artifact.artifactId(),
                        "Artifact ID appears more than once"));
            }
        }

        var issues = new java.util.ArrayList<ValidationIssue>();

        for (var edge : attempt.edges()) {
            if (!artifactIds.contains(edge.fromArtifactId())) {
                issues.add(new ValidationIssue(
                        "LINEAGE_SOURCE_MISSING",
                        edge.fromArtifactId(),
                        "Edge source is not in the attempt artifact set"));
            }
            if (!artifactIds.contains(edge.toArtifactId())) {
                issues.add(new ValidationIssue(
                        "LINEAGE_TARGET_MISSING",
                        edge.toArtifactId(),
                        "Edge target is not in the attempt artifact set"));
            }
        }

        for (var output : attempt.outputs()) {
            if ("AVAILABLE".equals(output.evidenceStatus())
                    && (output.storageRef() == null
                    || output.contentDigest() == null)) {
                issues.add(new ValidationIssue(
                        "AVAILABLE_ARTIFACT_WITHOUT_REFERENCE_OR_DIGEST",
                        output.artifactId(),
                        "Available artifact requires a reference and digest"));
            }
        }

        return List.copyOf(issues);
    }

    private ProvenanceValidator() {}
}
~~~

Đây là validator cơ bản, chỉ kiểm các liên kết trong attempt artifact set. Hệ thống thực cần kiểm refs cross-attempt/reference, tồn tại và quyền của artifact store, digest, schema compatibility, parent run/case identity và cycle policy nếu graph không cho phép vòng lặp.

### 19.1. Không biến missing evidence thành lỗi giả

Nếu trace không có do sampling, record có thể là SAMPLED_OUT và không có storage ref. Validator không nên coi mọi artifact không có ref là invalid; nó phải xét evidence status. Ngược lại, một artifact khai báo AVAILABLE nhưng không có ref/digest là lỗi integrity.

## 20. JUnit: kiểm provenance và report links

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class ProvenanceValidatorTest {

    private EvaluationProvenance.ArtifactRef artifact(
            String id, String status, String ref, String digest) {
        return new EvaluationProvenance.ArtifactRef(
                id, "ANSWER", "artifact-v1", ref, digest, status);
    }

    private EvaluationProvenance.AttemptProvenance attempt(
            List<EvaluationProvenance.ArtifactRef> inputs,
            List<EvaluationProvenance.ArtifactRef> outputs,
            List<EvaluationProvenance.LineageEdge> edges) {

        var versions = new EvaluationProvenance.VersionSnapshot(
                "dataset-v1", "sha256:dataset",
                "prompt-v1", "provider", "model-requested",
                "model-resolved", "pipeline-v1", "corpus-v1",
                "rubric-v1", "judge-v1", "report-v1");

        return new EvaluationProvenance.AttemptProvenance(
                "run-1", "case-1", "attempt-1",
                versions, inputs, outputs, edges, null,
                Instant.parse("2026-05-18T10:00:00Z"),
                Instant.parse("2026-05-18T10:00:01Z"));
    }

    @Test
    void validAvailableArtifactHasNoIssues() {
        var input = artifact(
                "input-1", "AVAILABLE", "secure://input/1", "sha256:1");
        var answer = artifact(
                "answer-1", "AVAILABLE", "secure://answer/1", "sha256:2");
        var edge = new EvaluationProvenance.LineageEdge(
                "input-1", "USED_BY", "answer-1");

        var issues = ProvenanceValidator.validate(
                attempt(List.of(input), List.of(answer), List.of(edge)));

        assertTrue(issues.isEmpty());
    }

    @Test
    void missingLineageTargetIsDetected() {
        var input = artifact(
                "input-1", "AVAILABLE", "secure://input/1", "sha256:1");
        var edge = new EvaluationProvenance.LineageEdge(
                "input-1", "USED_BY", "missing-answer");

        var issues = ProvenanceValidator.validate(
                attempt(List.of(input), List.of(), List.of(edge)));

        assertEquals(1, issues.size());
        assertEquals("LINEAGE_TARGET_MISSING", issues.get(0).code());
    }

    @Test
    void availableArtifactWithoutReferenceIsInvalid() {
        var answer = artifact("answer-1", "AVAILABLE", null, null);

        var issues = ProvenanceValidator.validate(
                attempt(List.of(), List.of(answer), List.of()));

        assertEquals(
                "AVAILABLE_ARTIFACT_WITHOUT_REFERENCE_OR_DIGEST",
                issues.get(0).code());
    }

    @Test
    void sampledOutTraceDoesNotRequireStorageReference() {
        var trace = new EvaluationProvenance.ArtifactRef(
                "trace-1", "TRACE", "trace-v1",
                null, null, "SAMPLED_OUT");

        var issues = ProvenanceValidator.validate(
                attempt(List.of(), List.of(trace), List.of()));

        assertTrue(issues.isEmpty());
    }
}
~~~

Các test kiểm validator minh họa, không xác minh rằng Spring AI đã capture đúng mọi event. Integration tests cần kiểm actual instrumentation, artifact persistence, trace correlation và quyền truy cập.

## 21. Spring AI Observability và correlation

Spring AI tích hợp observation với hệ sinh thái Spring/Micrometer; tùy phiên bản, provider, cấu hình và thành phần được instrument, có thể quan sát các thao tác như ChatClient/ChatModel, VectorStore và tool execution.

### 21.1. Observation/trace không phải kho provenance hoàn chỉnh

Observation có thể cung cấp tên operation, low-cardinality metadata, timing, error và trace context. Nhưng thường không nên gửi toàn bộ prompt, context, document content hoặc tool arguments vào span attributes vì quyền riêng tư và cardinality.

Thiết kế nên:

- Dùng observation/trace để mô tả operation và thời gian.
- Dùng runId, caseId, attemptId làm correlation metadata ở nơi phù hợp, theo cardinality/privacy policy.
- Lưu content/evidence trong artifact store có quyền.
- Liên kết trace IDs thật vào attempt record khi tracing backend cấp.
- Giữ status rõ nếu trace bị sampling hoặc hết retention.

### 21.2. Correlation qua nhiều tầng

Khi một request đi qua ChatClient, VectorStore, ChatModel và tool backend, cần giữ correlation giữa operation và attempt. Nếu gọi service khác qua HTTP, truyền trace context theo chuẩn tracing được cấu hình; không tự tạo trace ID tùy ý hoặc nhét ID vào nội dung prompt.

### 21.3. Metrics tags và artifact references

Dùng labels có cardinality hữu hạn như stage/provider/status/suite. Khi cần điều tra case cụ thể, dùng report query hoặc evidence index tìm theo caseId/attemptId. Không biến mọi case thành một metrics time series riêng.

### 21.4. Trace sampled out nhưng attempt vẫn truy được

Attempt record có thể chứa traceStatus=SAMPLED_OUT và traceRef=null, trong khi answer/context/evaluator artifacts vẫn có. Report cần cho phép xem evidence nội dung và thông báo rằng phân tích span không khả dụng.

## 22. Bảo đảm lineage xuyên suốt khi tạo report

Một report bundle có thể gồm:

~~~text
evaluation-reports/
  <report-id>/
    report-manifest.json
    run-manifest.json
    summary.json
    case-outcomes.jsonl
    metric-verdicts.jsonl
    failure-list.jsonl
    evidence-index.jsonl
    lineage-edges.jsonl
    telemetry-summary.json
    report.md
~~~

Đây là cấu trúc gợi ý. Raw evidence có thể nằm ở kho riêng; evidence-index.jsonl chỉ giữ refs, digest, status và quyền. Không cần sao chép dữ liệu nhạy cảm vào report bundle.

### 22.1. Report manifest

Lưu:

- reportId, runId, thời điểm tạo.
- Report builder version và output schema version.
- Run manifest ref/digest.
- Aggregation query/policy version.
- Danh sách artifact IDs hoặc snapshot refs đã dùng.
- Số record đọc vào, bỏ qua và lỗi.
- Content digest của từng output artifact.
- Approval/review metadata nếu report dùng cho release.

### 22.2. Kiểm tra counts và links

Trước khi đánh dấu report hoàn tất:

1. Tổng số case outcomes khớp planned dataset scope hoặc giải thích phần thiếu.
2. Verdict refs được summary dùng đều tồn tại.
3. Mỗi failure row có case/attempt và reason.
4. Artifact refs AVAILABLE có thể đọc và digest khớp.
5. Artifact REDACTED trỏ tới bản redacted hợp lệ.
6. Trace refs được kiểm tra theo retention/backend khi report cam kết có trace.
7. NOT_CAPTURED/EXPIRED/SAMPLED_OUT không bị trình bày thành AVAILABLE.
8. Report schema version và builder version được ghi.
9. Summary numerator/denominator có thể tái tính từ source records.
10. Report artifact digest được lưu trong report manifest.

### 22.3. Immutable report và revision

Báo cáo đã dùng để phê duyệt release cần được giữ nguyên. Nếu sửa labels, đổi aggregation hoặc re-run evaluator, tạo report revision/new report ID với quan hệ supersedes hoặc re-evaluates. Không ghi đè lịch sử đã được duyệt.

## 23. Quy trình điều tra từ một regression report

Ví dụ report cho biết factual correctness giảm. Một quy trình điều tra có thể thực hiện theo thứ tự:

1. Mở metric definition và xác nhận numerator/denominator, dataset, rubric, judge, aggregation policy.
2. Lấy danh sách verdict FAIL và case IDs được tổng hợp.
3. Chọn case có severity cao, mở accepted attempt.
4. Xem input/conversation refs và prompt template/rendered prompt refs.
5. Xem actual retrieved documents, rank, filters và corpus/index version.
6. Mở effective context ref để kiểm nội dung thực sự được gửi vào model.
7. Xem model call records, model metadata, parameters, answer và usage.
8. Nếu có tool, xem requested tool, arguments, authorization, result và hậu điều kiện.
9. Mở evaluator record, rubric, judge version, feedback và reference facts.
10. Mở trace spans nếu còn để tìm latency/error ở từng stage.
11. So với baseline attempt của cùng case.
12. Ghi root cause đã xác minh hoặc giữ hypothesis ở trạng thái chưa xác nhận.

### 23.1. Ví dụ một case RAG

Report: POLICY-017, factual correctness FAIL.

| Bằng chứng | Baseline | Candidate |
| --- | --- | --- |
| Corpus version | policy-v3 | policy-v3 |
| Retrieved top-1 | policy-v3#refund-pro | faq-v2#refund |
| Effective context | Có điều khoản 14 ngày | Có FAQ cũ 30 ngày |
| Answer | 14 ngày | 30 ngày |
| Factual verdict | PASS | FAIL |

Giả thuyết: candidate thay filter/ranking khiến FAQ cũ được ưu tiên. Đây là hướng điều tra; cần xem actual query, filter, index metadata và context artifact để xác nhận.

### 23.2. Ví dụ một case tool

Report: ORDER-004, tool contract FAIL.

- Input ref xác định user/session đã pseudonymize.
- Model call record cho biết tool được đề xuất.
- Tool event cho biết arguments và schema version.
- Authorization record cho biết backend quyết định ALLOW/DENY.
- Backend result ref cho biết trạng thái thực tế.
- Final answer ref cho biết model diễn giải kết quả thế nào.
- Trace ref (nếu có) cho biết thời gian backend và model calls.

Nhờ vậy, nhóm phân biệt được model chọn sai tool, argument mapping sai, backend từ chối đúng, hay model diễn giải kết quả tool sai.

## 24. Audit, governance và kiểm soát thay đổi

Với báo cáo được dùng cho release, audit cần biết ai đã tạo/chấp thuận, những input nào được dùng và có thay đổi gì sau đó.

Một approval record có thể lưu:

~~~json
{
  "approvalId": "approval-104",
  "reportId": "report-candidate-v5-2026-05-18",
  "decision": "APPROVED_WITH_CONDITIONS",
  "reviewerRef": "team-reviewer-identity",
  "approvedAt": "2026-05-19T08:30:00Z",
  "conditions": [
    "Monitor factual correctness in canary",
    "Retain critical-case evidence for review"
  ],
  "reportDigest": "sha256:..."
}
~~~

Ví dụ giả định; reviewer identity nên dùng hệ thống định danh có quyền, không ghi email cá nhân vào artifact công khai nếu không cần.

### 24.1. Audit events nên append-only

Các sự kiện tạo manifest, ghi attempt, chấm verdict, redaction, export report, approval, revoke hoặc retention deletion nên có actor/service, action, object ref và timestamp. Chỉ người có quyền mới được sửa nhãn hoặc thay source facts; thay đổi cần version mới và lý do.

### 24.2. Không để evidence link trở thành quyền truy cập vô hạn

Signed URLs có thể hết hạn; report nên trỏ tới artifact ID qua service authorization thay vì lưu URL bearer token lâu dài. Khi người xem mở link, hệ thống kiểm quyền tại thời điểm truy cập.

### 24.3. Retention phải nhất quán với lineage

Khi raw input bị xóa theo retention, giữ metadata tối thiểu được phép để biết artifact đã hết hạn do policy. Không giữ digest/ref như một cách lách yêu cầu xóa dữ liệu. Nếu cần giữ audit lâu dài, chỉ giữ những trường đã được policy và pháp chế cho phép.

## 25. Những sai lầm thường gặp

**Chỉ lưu summary score.** Không thể tìm case tạo nên thay đổi.

**Chỉ lưu prompt template.** Không biết prompt/context thực tế đã gửi model.

**Dùng expected documents thay actual retrieved/effective context.** Che retrieval failure và làm groundedness sai.

**Dùng trace ID thay attempt ID.** Một case có thể có nhiều trace hoặc không có trace do sampling.

**Cho rằng trace thành công chứng minh answer đúng.** Trace mô tả đường đi kỹ thuật, không phải nguồn sự thật.

**Lưu raw prompt/context vào metrics tags.** Tạo high cardinality và rủi ro lộ dữ liệu.

**Không version judge/rubric/report builder.** Không giải thích được điểm thay đổi do cách chấm hay cách tổng hợp.

**Dùng alias latest/stable làm snapshot.** Cấu hình có thể thay đổi âm thầm.

**Hash dữ liệu không canonicalize.** Digest khác nhau vì formatting hoặc bỏ qua field có ý nghĩa.

**Coi digest chứng minh nội dung đúng.** Hash chỉ kiểm tính toàn vẹn tương đối với digest tin cậy.

**Không phân biệt NOT_CAPTURED và NOT_APPLICABLE.** Reviewer hiểu nhầm evidence thiếu thành không cần thiết.

**Ghi đè answer/verdict cũ khi retry hoặc re-evaluate.** Mất lịch sử và không tái giải thích report đã duyệt.

**Đưa tool secrets hoặc dữ liệu cá nhân vào report.** Vi phạm quyền truy cập và có thể lộ thông tin.

**Giữ report nhưng xóa hết source records mà không có retention design.** Link không còn truy được và không biết vì sao.

## 26. Bài thực hành: truy ngược một verdict tới đầu vào và evidence

**Bối cảnh:** một chatbot Spring AI dùng RAG trả lời chính sách và tool getOrderStatus. Một report candidate cho biết POLICY-017 factual correctness FAIL, ORDER-004 tool contract FAIL và p95 latency tăng.

### Phần A — Tạo manifest và định danh

1. Tạo run manifest ghi dataset snapshot/digest, prompt, model, pipeline, corpus/index, tool schema, rubric/judge và report builder.
2. Chọn IDs ổn định cho run, case, attempt, model call, tool call, artifact và verdict.
3. Ghi schema version và canonicalization version.

**Đầu ra:** manifest bất biến và ID registry cho run.

### Phần B — Capture một case RAG đầy đủ

Với POLICY-017, ghi input ref, rendered prompt ref, retrieval query/results, selected chunks, effective context ref, model call/answer, reference source và evaluator verdict. Kiểm tra mỗi artifact có parent/derivedFrom phù hợp.

**Đầu ra:** lineage từ dataset tới factual verdict.

### Phần C — Capture một case tool

Với ORDER-004, ghi model call đề xuất tool, schema version, arguments ref, authorization decision, backend operation/result, final answer và metric verdict. Kiểm thử một ca DENY đúng mong đợi.

**Đầu ra:** tool event provenance và quyền truy ngược.

### Phần D — Nối telemetry

Liên kết trace/span IDs thật nếu có, model/retrieval/tool latency, token usage và cost estimate với attempt. Với trace sampled out hoặc usage không được provider cung cấp, ghi trạng thái missing tương ứng.

**Đầu ra:** telemetry summary có nguồn và phạm vi đo.

### Phần E — Tạo report drill-down

Xuất summary, case outcomes, verdicts, failure list, evidence index và lineage edges. Mở từ factual pass-rate tới verdict ID, case, attempt, effective context và reference. Xác minh report builder/aggregation version.

**Đầu ra:** report bundle có thể truy ngược.

### Phần F — Kiểm integrity và quyền

Tính SHA-256 trên bytes canonicalized, kiểm digest khi đọc artifact. Thử một artifact bị thay đổi, một ref bị thiếu, một trace sampled out và một artifact bị access denied. Xác nhận report hiển thị trạng thái chính xác, không tạo evidence giả.

**Đầu ra:** validation report, access policy và missing-evidence inventory.

### Checklist nghiệm thu

- [ ] Manifest có run ID và snapshot/version/digest cho input chính.
- [ ] Mỗi case và attempt có ID ổn định.
- [ ] Prompt template và prompt/context thực tế được phân biệt.
- [ ] Actual retrieval results và effective context có refs riêng.
- [ ] Model call, parameters, response và usage được liên kết.
- [ ] Tool call có schema, arguments, authorization và result provenance.
- [ ] Verdict có rubric/judge version và input/evidence refs.
- [ ] Report metric có numerator, denominator và aggregation policy.
- [ ] Failure list truy được tới attempt và evidence.
- [ ] Trace refs là ID thật hoặc trạng thái missing được ghi rõ.
- [ ] Metrics tags không chứa raw prompt/user ID/case ID.
- [ ] Artifact digest dùng canonicalization version xác định.
- [ ] Digest được kiểm khi đọc; không tuyên bố hash chứng minh nội dung đúng.
- [ ] Redaction tạo artifact mới và có lineage.
- [ ] Access/retention policy áp dụng cho raw và redacted evidence.
- [ ] Report builder/schema version được lưu.
- [ ] Missing/expired/sampled-out evidence không bị biến thành AVAILABLE.
- [ ] Report đã duyệt không bị ghi đè âm thầm.

### Câu hỏi tự kiểm tra

1. Provenance khác lineage ở điểm nào?
2. Vì sao trace thành công không chứng minh factual correctness PASS?
3. Một prompt template có đủ để tái dựng request model đã nhận không?
4. Retrieved document IDs khác effective context như thế nào?
5. Khi judge chấm answer, những artifact refs nào cần có?
6. Vì sao attemptId và traceId không thể thay thế nhau?
7. Nếu provider không cung cấp resolved model revision, manifest nên ghi gì?
8. Content digest có chứng minh reference facts đúng nghiệp vụ không?
9. Vì sao cần canonicalize JSON trước khi hash?
10. Trace sampled out nhưng answer/context còn có thể audit phần nào?
11. Khi effective context bị thiếu, groundedness nên được báo thế nào?
12. Làm sao liên kết p95 latency với model call và tool span của một case?
13. Vì sao report builder version ảnh hưởng khả năng giải thích summary?
14. Redaction nên ghi đè raw artifact hay tạo artifact mới có derivedFrom?
15. Khi raw evidence hết retention, report nên thể hiện trạng thái gì?
16. Làm sao chứng minh một failure row đã được tổng hợp vào summary?
17. Vì sao không đưa case ID và trace ID làm metric labels?
18. Nếu judge version đổi, nên retry evaluator hay tạo evaluation mới?

## 27. Tổng kết

Một báo cáo đánh giá Spring AI chỉ có thể được tin cậy và điều tra khi **mỗi kết luận có đường dẫn về nguồn tạo ra nó**. Run manifest xác định dataset, prompt, model, corpus/index, tool schema, rubric, judge và report builder. Case/attempt provenance ghi input thực tế, retrieval, effective context, model calls, tool events, answer và verdict. Evidence graph liên kết các artifact bằng ID và quan hệ DERIVED_FROM, USED_BY, EVALUATED_AGAINST và AGGREGATED_INTO.

Metrics và traces bổ sung góc nhìn vận hành, nhưng không thay thế evidence nội dung. Trace có thể sampled out; provider có thể không cung cấp resolved revision hoặc usage; raw evidence có thể bị redaction hay hết retention. Những giới hạn đó phải được ghi rõ. Digest giúp phát hiện thay đổi bytes khi đối chiếu với metadata tin cậy, nhưng không chứng minh dữ liệu đúng. Tái thực thi cũng không bảo đảm output giống từng byte khi model/provider bên ngoài thay đổi.

Khi report giữ runId, caseId, attemptId, artifactId, evaluationId, version, digest, quyền truy cập và lineage đầy đủ, reviewer có thể lần từ một chỉ số tới đúng input, context, answer, reference, evaluator và trace đã tạo ra kết quả. Đó là nền tảng để giải thích regression, kiểm toán quyết định release và cải thiện chất lượng qua từng phiên bản prompt, model và pipeline.

### Tài liệu tham khảo

- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring Boot — Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [OpenTelemetry — Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [Java — MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
