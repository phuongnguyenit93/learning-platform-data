# Lưu cấu hình prompt, mô hình, dữ liệu và tham số của mỗi lần chạy

Một báo cáo đánh giá Spring AI cho biết “bản B đạt 94%, bản A đạt 89%”. Kết quả này chưa đủ để khẳng định bản B tốt hơn nếu nhóm không biết **hai lần chạy đã dùng prompt, model, corpus, dữ liệu test và bộ chấm nào**.

Ví dụ, bản B có thể dùng prompt mới nhưng đồng thời dùng tài liệu chính sách đã cập nhật, model của nhà cung cấp đã đổi phiên bản và evaluator chấm theo rubric dễ hơn. Khi đó điểm số tăng không chỉ phản ánh hiệu quả của prompt. Một trường hợp khác: báo cáo ghi cùng tên model, nhưng tên đó chỉ là **alias** trỏ tới một phiên bản được nhà cung cấp cập nhật sau đợt chạy trước; nhóm cũng không thể khẳng định mọi điều kiện được giữ nguyên.

Giải pháp là thiết kế **run manifest**: bản mô tả cấu hình và nguồn dữ liệu của mỗi đợt đánh giá, có danh tính, thời điểm, phiên bản, tham số và dấu kiểm toàn vẹn. Run manifest phải liên kết với **execution attempts**, **kết quả evaluator** và **bằng chứng vận hành** như traces, metrics, token và chi phí.

Trong chương **Quy trình đánh giá** của module **SPRING_AI_EVALUATION_OBSERVABILITY**, việc lưu cấu hình giúp người học đánh giá chất lượng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling, đồng thời xác định vì sao prompt, model hoặc pipeline thay đổi làm chất lượng, độ trễ và chi phí tăng giảm.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích tại sao mỗi evaluation run cần một manifest và tại sao chỉ lưu `runId` là chưa đủ.
2. Phân biệt **cấu hình mong muốn**, **cấu hình đã được resolve** và **bằng chứng thực tế của mỗi attempt**.
3. Thiết kế cấu trúc lưu phiên bản prompt, model, dữ liệu, embedding/index, retrieval, tool, memory, evaluator và tham số vận hành.
4. Phân biệt version tag với content digest; biết lúc nào cần lưu snapshot bất biến thay vì chỉ một tên thân thiện.
5. Lưu metadata theo các lớp `run → case → attempt → call → verdict` để hỗ trợ retry, tool calling và nhiều lượt gọi model.
6. Cảnh giác với model alias, dữ liệu động, provider-side changes và tính xác suất của LLM khi nói về khả năng tái lập.
7. Xây một ví dụ Java ghi manifest mà không ghi đè bản cũ và không đưa bí mật vào báo cáo.
8. So sánh hai run trên cùng hệ quy chiếu và phân loại thay đổi do ứng dụng, dữ liệu, hạ tầng hay bộ chấm.
9. Kết nối manifest với traces, token, chi phí, độ trễ và release gate cho CI/CD.
10. Bảo vệ dữ liệu nhạy cảm khi lưu prompt, context, tool arguments và metadata.

## 2. Run manifest là gì?

**Run manifest** là bản ghi có cấu trúc mô tả một lần tổ chức đánh giá, gồm:

- **Danh tính run:** `runId`, thời điểm bắt đầu, môi trường, người hoặc hệ thống kích hoạt.
- **Nhiệm vụ và dataset:** dataset ID/version, danh sách case hoặc snapshot, nhãn và nguồn tham chiếu.
- **Cấu hình ứng dụng:** prompt, model/provider, tham số sinh, RAG, tool calling, memory/advisors.
- **Cấu hình đánh giá:** bộ rubric, evaluator/judge, cách tính pass rate, các ca bắt buộc.
- **Cấu hình thực thi:** concurrency, retry, timeout, rate limit, random seed nếu có, mã ứng dụng và dependencies.
- **Liên kết bằng chứng:** nơi lưu answer/context/tool events, trace, metrics và bảng điểm.
- **Trạng thái:** `CREATED`, `RUNNING`, `COMPLETED`, `PARTIAL`, `FAILED` hoặc `CANCELLED`.

Manifest là **hợp đồng dữ liệu do nhóm phát triển thiết kế**. Spring AI có nhiều API hỗ trợ gọi model, RAG, tool và evaluator, nhưng không nên giả định Spring AI tự tạo đầy đủ manifest theo cấu trúc này.

### 2.1. Manifest không phải log request

| Loại dữ liệu | Phạm vi | Mục đích |
| --- | --- | --- |
| **Run manifest** | Một đợt đánh giá với cấu hình xác định | Biết “đang thử phiên bản nào” |
| **Case/dataset record** | Tình huống nghiệp vụ | Biết “đang mong đợi điều gì” |
| **Attempt evidence** | Một lần thực thi một case | Biết “đã xảy ra điều gì” |
| **Model/tool call event** | Một lần gọi trong attempt | Biết “component nào được gọi, với tham số và kết quả gì” |
| **Evaluation verdict** | Một metric chấm một attempt | Biết “đạt hay không, theo rubric/judge nào” |
| **Trace/metrics** | Đường đi request và tập yêu cầu vận hành | Biết “bước nào chậm/lỗi, hệ thống sử dụng tài nguyên ra sao” |

**Không nên dồn tất cả nội dung request vào manifest.** Manifest mô tả cấu hình và liên kết tới evidence; answer, context và tool result được lưu theo attempt trong kho thích hợp có kiểm soát truy cập.

### 2.2. Quan hệ giữa run và attempt

~~~mermaid
erDiagram
    DATASET_VERSION ||--o{ TEST_CASE : "contains"
    EVALUATION_RUN ||--o{ EXECUTION_ATTEMPT : "executes"
    TEST_CASE ||--o{ EXECUTION_ATTEMPT : "run multiple times"
    EVALUATION_RUN ||--|| RUN_MANIFEST : "described by"
    EXECUTION_ATTEMPT ||--o{ MODEL_CALL : "can invoke"
    EXECUTION_ATTEMPT ||--o{ TOOL_EVENT : "can invoke"
    EXECUTION_ATTEMPT ||--o{ EVALUATION_VERDICT : "scored by"
    EXECUTION_ATTEMPT }o--o| TRACE : "links when available"
~~~

Một case có thể được chạy nhiều lần vì retry, so baseline/candidate hoặc lặp để đo tính biến thiên. Một attempt có thể gọi model hai lần khi xử lý tool, và cũng có thể được chấm lại bằng một evaluator mới. Vì vậy cần phân biệt các ID thay vì chỉ có `caseId`.

## 3. Ba trạng thái cấu hình: khai báo, resolve và quan sát

Điểm dễ gây sai lầm là ghi một giá trị cấu hình trong file nhưng lại coi đó là bằng chứng provider thực sự sử dụng đúng giá trị ấy.

### 3.1. Desired configuration — điều nhóm yêu cầu

Ví dụ một run được khai báo:

~~~yaml
model:
  provider: "example-provider"
  requestedModel: "chat-model-stable"
  temperature: 0.2
  maxOutputTokens: 512
~~~

Đây là điều test harness **muốn gửi**. Nó chưa chứng minh provider đã chấp nhận `temperature=0.2`, đã dùng đúng phiên bản model hoặc đã áp dụng token limit như dự kiến.

### 3.2. Resolved configuration — giá trị thực sự được ứng dụng dùng

Ứng dụng có thể lấy cấu hình từ properties, environment, flags, default của SDK hoặc cài đặt theo từng request. Cần ghi các giá trị **sau khi resolve**:

~~~json
{
  "resolvedConfiguration": {
    "requestedModel": "chat-model-stable",
    "temperature": 0.2,
    "maxOutputTokens": 512,
    "topK": 5,
    "enabledAdvisors": ["rag", "conversation-memory"]
  }
}
~~~

Nếu application properties ghi `topK=5` nhưng lời gọi cụ thể override thành `topK=3`, manifest và attempt evidence phải ghi nhận điểm khác nhau này.

### 3.3. Observed execution — điều thực sự xảy ra

Trong attempt, cần thêm sự kiện từ lời gọi:

~~~json
{
  "modelCall": {
    "requestedModel": "chat-model-stable",
    "responseModelId": "provider-reported-model-id-if-available",
    "status": "SUCCESS",
    "inputTokens": 1800,
    "outputTokens": 235,
    "durationMs": 970
  }
}
~~~

`responseModelId` chỉ có giá trị xác minh khi **provider thực sự trả về** và có ý nghĩa được tài liệu provider giải thích. Nếu provider không trả build/model revision bất biến, hãy ghi “không khả dụng” thay vì tự suy ra từ tên alias.

**Quy tắc:** desired config là ý định; resolved config là giá trị ứng dụng áp dụng; observed execution là bằng chứng request đã thực thi. Chỉ khi phân biệt đủ ba lớp mới tránh việc một bản báo cáo “giống cấu hình” nhưng thực tế khác nhau.

## 4. Một schema manifest đủ dùng

Ví dụ dưới đây mô tả một run của chatbot chính sách giả định *Sao Mai*. Tất cả tên version, model và dữ liệu chính sách chỉ để minh họa; không phải một model hay dataset có thật.

~~~json
{
  "schemaVersion": "evaluation-run-manifest-v1",
  "runId": "policy-eval-2026-05-18-candidate",
  "createdAt": "2026-05-18T09:00:00Z",
  "environment": "staging",
  "application": {
    "service": "support-assistant",
    "buildId": "build-2481",
    "commitId": "source-revision-id",
    "springAiVersion": "recorded-project-version",
    "javaVersion": "21"
  },
  "dataset": {
    "datasetId": "policy-eval",
    "version": "v3",
    "snapshotRef": "artifact:dataset/policy-eval/v3",
    "contentDigestRef": "artifact-metadata:dataset-sha256",
    "caseCount": 100
  },
  "prompt": {
    "templateId": "policy-answer",
    "templateVersion": "v4",
    "templateRef": "artifact:prompt/policy-answer/v4",
    "templateDigestRef": "artifact-metadata:prompt-sha256",
    "variableSchemaVersion": "v2"
  },
  "model": {
    "provider": "example-provider",
    "requestedModelId": "chat-model-stable",
    "temperature": 0.2,
    "topP": 0.9,
    "maxOutputTokens": 512,
    "responseFormat": "text"
  },
  "rag": {
    "corpusVersion": "policy-v3",
    "indexSnapshotRef": "artifact:index/policy-v3",
    "embeddingModelId": "embedding-model-v1",
    "chunkingVersion": "chunker-v2",
    "queryRewriteVersion": "rewrite-v1",
    "retrievalTopK": 5,
    "filterPolicyVersion": "access-filter-v2",
    "rerankerVersion": "none"
  },
  "toolCalling": {
    "toolCatalogVersion": "tools-v2",
    "toolSchemaRef": "artifact:tools/tools-v2",
    "backendFixtureVersion": "fixtures-v4"
  },
  "memory": {
    "policyVersion": "session-memory-v1",
    "caseIsolation": "new-conversation-per-independent-case"
  },
  "evaluation": {
    "rubricVersion": "policy-rubric-v3",
    "judgeVersion": "judge-config-v2",
    "referenceSourceVersion": "policy-v3",
    "criticalCasesRequired": true
  },
  "execution": {
    "maxInFlightCases": 4,
    "maxAttemptsPerCase": 2,
    "perCallTimeoutMs": 25000,
    "batchDeadlineMs": 900000,
    "seed": null
  },
  "privacy": {
    "storeRawPrompt": false,
    "storeRawToolArguments": false,
    "evidencePolicyVersion": "evidence-minimal-v1"
  }
}
~~~

Một bản manifest thật có thể nhỏ hơn. Nên khởi đầu với những trường **quyết định kết quả hoặc giúp giải thích kết quả**, mở rộng khi hệ thống phát triển.

### 4.1. Chọn trường bắt buộc và trường tùy chọn

| Loại trường | Nên bắt buộc? | Lý do |
| --- | --- | --- |
| `schemaVersion`, `runId` | Có | Có thể phân tích và định danh |
| `datasetVersion`/snapshot | Có | Biết bài kiểm thử và kỳ vọng |
| `promptVersion` và cách resolve prompt | Có khi ứng dụng có prompt template | Giải thích nội dung gửi model |
| Model/provider thực được yêu cầu | Có | So sánh, chi phí và latency |
| Model revision thực tế | Khi provider cung cấp | Không nên bịa nếu thiếu |
| `corpus/indexVersion` | Có với RAG | Phân biệt thay đổi nguồn và truy xuất |
| Tool schema/backend fixture | Có với ca tool calling | Phục hồi hành vi và quyền |
| Memory policy/isolation | Có với ca multi-turn | Tránh lẫn hội thoại |
| Rubric/judge | Có nếu chấm ngữ nghĩa | Điểm số phụ thuộc cách chấm |
| Random seed | Nếu model/provider hỗ trợ | Hỗ trợ kiểm soát một phần biến động |
| Quota/load/concurrency | Có khi so latency/cost | Khác tải có thể làm sai so sánh |
| Raw prompt/tool result | Không mặc định | Có thể chứa dữ liệu nhạy cảm |

Khi một loại cấu hình không áp dụng, đánh dấu `NOT_APPLICABLE` hoặc bỏ trường theo schema rõ ràng, **không** điền giá trị giả để trông có vẻ đầy đủ.

## 5. Lưu prompt đúng: template, biến, advisor và prompt thực

Chỉ lưu `promptVersion=4` thường không đủ. Trong Spring AI, prompt thực tế có thể được hình thành từ:

1. System instruction hoặc message template.
2. User message và lịch sử hội thoại.
3. Biến nội dung được chèn vào template.
4. Ngữ cảnh RAG do advisor/retriever cung cấp.
5. Các hướng dẫn hoặc messages từ tool calling.
6. Thao tác cắt ngắn, nén, sắp xếp hoặc chuyển đổi context.
7. Các default hoặc overrides ở `ChatClient`/`ChatModel`.

### 5.1. Phân biệt prompt template và effective prompt

**Prompt template** là cấu trúc có chỗ trống, ví dụ:

~~~text
SYSTEM:
  Bạn là trợ lý hỏi đáp chính sách.
  Chỉ khẳng định điều được nguồn chính thức hỗ trợ.
USER:
  Câu hỏi: [question]
  Bằng chứng: [retrieved_context]
~~~

**Effective prompt/messages** là nội dung sau khi ứng dụng thay `question` và `retrieved_context` bằng dữ liệu thực cho một attempt, cùng các message khác đã được thêm. Effective prompt có thể chứa thông tin nội bộ hoặc dữ liệu cá nhân nên **không mặc định ghi raw vào manifest**.

Một cách tổ chức:

- Trong manifest: `templateId`, `templateVersion`, `templateDigest`, biến nào được phép dùng và schema của biến.
- Trong attempt evidence: phiên bản đã resolve, context document IDs, message roles/order, số token, tham chiếu an toàn tới effective prompt khi chính sách lưu trữ cho phép.
- Trong trace/metrics: duration, status, model ID và tags có cardinality hữu hạn; tránh raw prompt.

### 5.2. Prompt thay đổi do advisor cũng là thay đổi cấu hình

Giữ nguyên template nhưng đổi thứ tự advisors hoặc sửa bộ lọc RAG vẫn có thể làm effective prompt khác hẳn. Nên ghi các thông tin như:

| Thuộc tính | Ví dụ | Khi thiếu sẽ khó giải thích |
| --- | --- | --- |
| `advisorChainVersion` | `advisors-v3` | Vì sao context khác nhau |
| `ragPromptAugmentationVersion` | `rag-format-v2` | Thứ tự và định dạng chứng cứ |
| `memoryWindowPolicy` | `last-6-turns` | Vì sao câu tiếp nối đổi hành vi |
| `contextTruncationPolicy` | `token-budget-v2` | Vì sao nguồn quan trọng bị cắt |
| `citationFormatVersion` | `citation-v1` | Vì sao trích dẫn thay đổi |

Nếu ứng dụng không có các thành phần này, không cần tự bịa version; trường nên phản ánh cấu hình thực.

### 5.3. Hash prompt có tác dụng gì?

Digest như SHA-256 giúp kiểm tra **hai tệp bytes có giống nhau không**. Tuy nhiên:

- Hai template có cùng tên version nhưng digest khác → nội dung đã thay đổi âm thầm hoặc quy trình versioning có lỗi.
- Hai template có digest giống nhau nhưng biến, context hoặc advisor khác → effective prompt vẫn có thể khác.
- Digest không tự cho biết prompt có đúng/đủ/riêng tư hay không.
- Một raw hash của dữ liệu nhạy cảm có cấu trúc dễ đoán có thể làm lộ tín hiệu về nội dung trong một số tình huống; cần mô hình bảo vệ phù hợp, có thể dùng tham chiếu nội bộ và quyền truy cập thay vì phơi hash rộng rãi.

Nên tính digest từ **artifact bất biến được xác định rõ**, không từ file đã được sửa sau khi run kết thúc.

## 6. Lưu model và tham số sinh đúng cách

Khi đánh giá LLM, các tham số ảnh hưởng cả câu trả lời và số token:

| Nhóm | Trường minh họa | Vai trò |
| --- | --- | --- |
| Định danh | Provider, requested model ID, provider-reported revision | Biết model được chọn |
| Sampling | Temperature, top-p, seed (nếu có) | Ảnh hưởng tính đa dạng/ngẫu nhiên |
| Output | Max output tokens, stop sequences, response format | Giới hạn độ dài/hình thức |
| Tool | Danh mục tools, tool choice policy | Ảnh hưởng chọn hành động và số vòng gọi |
| Reasoning options | Tham số reasoning/effort nếu provider hỗ trợ | Có thể tác động latency/token/chi phí |
| Transport | Timeout, retry, region, SDK version | Ảnh hưởng vận hành |
| Pricing | Price table version/currency/effective date | Tính chi phí theo thời điểm |

**Tên trường trong bảng mang tính khái niệm**, không phải mọi provider hay Spring AI model option đều hỗ trợ đầy đủ hoặc có cùng ý nghĩa. Khi một tham số không được provider hỗ trợ, phải ghi rõ thay vì giả định nó có hiệu lực.

### 6.1. “Cùng tên model” chưa chắc cùng model build

Một tên như `model-stable` có thể là alias. Nếu provider cập nhật model đằng sau alias, hai run vẫn ghi cùng requested model nhưng hành vi khác. Nên lưu thêm:

- Model ID được phản hồi sau lời gọi, nếu provider cung cấp.
- Thời điểm chạy và region/endpoint phù hợp.
- SDK/client version và các tùy chọn đã resolve.
- Ghi chú về khả năng pin hoặc không pin được model revision.

**Không tuyên bố tái lập tuyệt đối** khi provider không cung cấp version bất biến. Có thể tái chạy *trong điều kiện gần giống*, chứ chưa chắc tạo cùng output.

### 6.2. Seed không biến LLM thành hàm hoàn toàn xác định

Một số provider hỗ trợ seed, nhưng kết quả vẫn có thể thay đổi theo model build, tính toán backend, thứ tự request hoặc thành phần pipeline ngoài model. Ngay cả khi temperature thấp, đầu ra ngôn ngữ vẫn có khả năng khác cách diễn đạt.

Với ca quan trọng, cân nhắc chạy lặp cùng cấu hình, lưu từng `attemptId` và báo tỷ lệ pass/phạm vi biến động thay vì công bố một lần sinh duy nhất như chân lý.

### 6.3. Runtime overrides phải được ghi theo từng call

Trong một attempt có tool calling:

~~~text
ChatModel call #1: model A, temperature 0.2
Tool getOrderStatus: order DH-123, result IN_TRANSIT
ChatModel call #2: model A, temperature 0.0
~~~

Nếu các lần gọi có option khác nhau, manifest ở cấp run chỉ mô tả **default**; evidence cấp `modelCallId` phải ghi override thực tế. Đồng thời lưu số token của **từng lời gọi**, tránh giả định một attempt = một model request.

## 7. Dữ liệu kiểm thử: version, snapshot, nguồn chuẩn và tính toàn vẹn

Khi so `baseline-v1` và `candidate-v2`, giữ cùng `datasetVersion` là điều kiện quan trọng nhưng chưa đủ nếu file cùng version vẫn bị chỉnh sửa.

### 7.1. Bản ghi dataset nên có

- `datasetId` và `datasetVersion`.
- Snapshot immutable hoặc đường dẫn artifact có content digest.
- `caseCount` và ID các case thuộc run.
- Ngôn ngữ, tags, nhóm rủi ro và quy tắc lấy mẫu.
- Reference facts/documents đã được chuyên gia xác minh.
- Version của nguồn chuẩn và ngày có hiệu lực.
- Quy tắc tạo synthetic cases hoặc seed sampling nếu có.
- Chính sách dùng dữ liệu thật/ẩn danh và retention.

Ví dụ:

~~~yaml
dataset:
  id: support-quality-eval
  version: v5
  snapshotRef: "artifacts/datasets/support-quality-eval/v5.jsonl"
  digestAlgorithm: SHA-256
  digestValue: "computed-at-snapshot-time"
  caseCount: 200
  labelPolicyVersion: label-policy-v2
  referenceCorpusVersion: policy-v3
  split: held-out
~~~

`computed-at-snapshot-time` là chỗ trống mô tả metadata cần tạo từ artifact thực; không phải digest thật.

### 7.2. Không trộn nguồn chuẩn với nguồn truy xuất

Có ba nhóm dữ liệu phải tách:

| Trường | Ý nghĩa | Dùng ở đâu |
| --- | --- | --- |
| `referenceDocuments` | Tài liệu chính thức đã xác minh, làm chuẩn chấm | Factual correctness |
| `retrievedDocuments` | Tài liệu retriever tìm được trong attempt | Retrieval hit@k/Recall@k |
| `effectiveContext` | Nội dung thật model nhận sau lọc, chuyển đổi, cắt ngắn | Groundedness |

Nếu ca `REFUND-001` mong chính sách 14 ngày nhưng retriever lấy tài liệu cũ 30 ngày, câu trả lời 30 ngày có thể grounded theo retrieved context nhưng **factual correctness FAIL**.

Đưa tài liệu chuẩn vào vị trí retrieved context khi chấm sẽ che mất retrieval failure. Run manifest phải ghi nguồn chuẩn của dataset; attempt evidence phải ghi nguồn thực tế được pipeline đưa vào model.

### 7.3. Khi nguồn chính sách thay đổi

Giả sử `policy-v3` đang áp dụng nhưng kỳ sau chuyển sang `policy-v4`. Nếu đáp án mong đợi thay đổi, phải tạo một **bộ nhãn/dataset version mới** hoặc lưu lịch sử thay đổi có thể tái hiện.

Không được âm thầm thay `expectedFacts` của `REFUND-001` trong cùng snapshot rồi so điểm của baseline cũ với candidate mới, bởi hai run đã dùng **hai chuẩn sự thật khác nhau**.

### 7.4. Dataset dùng cho regression khác production sample

- **Regression/held-out dataset:** snapshot được chọn trước và gắn nhãn rõ, dùng để so phiên bản.
- **Production sample:** yêu cầu thực được lấy mẫu theo policy, thường có nhãn đến muộn hoặc thiếu. Cần lưu `samplingPolicyVersion`, xác suất chọn mẫu hoặc cách phân tầng, số chưa review.

Không đưa điểm PASS của mẫu được chọn vì “có dấu hiệu lỗi” để suy ra tỷ lệ PASS toàn production mà không xử lý sai lệch mẫu.

## 8. RAG: cần lưu cả corpus, index và chuỗi biến đổi

Chỉ ghi `retrievalTopK=5` không đủ để tái hiện RAG. Kết quả phụ thuộc nhiều thành phần:

~~~mermaid
flowchart LR
    A["Corpus snapshot"] --> B["Chunker<br/>size / overlap"]
    B --> C["Embedding model"]
    C --> D["Vector index"]
    Q["Question"] --> R["Query rewrite / embedding"]
    D --> S["Retriever + filters"]
    R --> S
    S --> T["Rerank / context assembly"]
    T --> U["ChatModel"]
    U --> V["Answer"]
~~~

### 8.1. Ma trận metadata RAG

| Thành phần | Trường nên lưu | Lỗi khó điều tra nếu thiếu |
| --- | --- | --- |
| Corpus | `corpusVersion`, source IDs, thời điểm hiệu lực | Tài liệu cũ/mới khác nhau |
| Chunking | Chunk size/overlap, splitter version, preprocessing | Thiếu đoạn chứng cứ |
| Embeddings | Provider/model ID, dimension, options | Vector không tương thích |
| Index | Snapshot/rebuild ID, index schema, vector store config | Kết quả tìm thay đổi |
| Query transform | Rewrite prompt/version, query filters | Truy vấn thực tế khác input |
| Retrieval | `topK`, similarity threshold, filter policy, search type | Thiếu/lẫn nguồn |
| Reranking | Reranker model/version, limit | Thứ tự context thay đổi |
| Context assembly | Chọn tài liệu, thứ tự, giới hạn token, định dạng | Bằng chứng bị cắt trước generation |
| Citation | Policy tạo citation, source ID mapping | Dẫn nguồn không hỗ trợ nội dung |

Các trường không phải API bắt buộc của Spring AI. Chúng mô tả những yếu tố ảnh hưởng chất lượng và cần được lấy từ **cấu hình thực tế** của pipeline dự án.

### 8.2. Run config và evidence của từng retrieval không giống nhau

Manifest có thể nói `topK=5`. Nhưng attempt thực tế phải lưu:

~~~json
{
  "caseId": "REFUND-001",
  "attemptId": "run-candidate-REFUND-001-1",
  "retrieval": {
    "requestedTopK": 5,
    "returnedDocumentIds": [
      "policy-v2#refund",
      "policy-v3#refund",
      "faq-billing"
    ],
    "effectiveContextDocumentIds": [
      "policy-v3#refund",
      "faq-billing"
    ],
    "usedFilterVersion": "policy-current-v2"
  }
}
~~~

Trong ví dụ, retriever trả 3 documents và bước context assembly dùng 2. Muốn chấm `retrievalHit@k`, xem kết quả retriever; muốn chấm groundedness, cần context thật model nhận, không chỉ document IDs.

### 8.3. Data freshness là một tham số chất lượng

Một corpus có thể được rebuild hàng ngày; cùng tên `index-latest` hôm qua và hôm nay không nhất thiết có nội dung như nhau. Với đánh giá khoa học hơn, nên lưu snapshot hoặc content digest/version bất biến thay vì chỉ `latest`.

Nếu nguồn được query trực tiếp và không thể snapshot hoàn toàn, báo cáo phải nêu giới hạn tái hiện theo thời điểm truy vấn.

## 9. Tool Calling và Memory: cấu hình cũng phải lưu

Một lỗi thường gặp khi so hai run là tập trung vào model và prompt nhưng quên phiên bản tool schema hoặc memory policy.

### 9.1. Tool Calling

Nên ghi:

- Tên các tools được công bố cho model.
- Version của tool description/schema và `tool choice` policy.
- Backend/API version, môi trường, fixture hoặc snapshot trạng thái đầu.
- Chính sách xác thực, phân quyền, yêu cầu xác nhận và idempotency.
- Timeout, retry, max tool rounds và giới hạn lỗi.
- Cách trả kết quả tool về model và cách ghi nhận output/error.

Ví dụ manifest:

~~~yaml
toolCalling:
  catalogVersion: tools-v3
  exposedTools:
    - getOrderStatus
    - calculateShippingFee
  schemaRef: "artifacts/tools/tools-v3.json"
  fixtureVersion: order-fixtures-v2
  authorizationPolicyVersion: order-access-v4
  maxToolRounds: 3
~~~

Với `refundOrder` có tác dụng phụ, không dùng production thật trong dataset nếu chưa có phương án an toàn. Dùng test doubles hoặc sandbox và kiểm tra hậu điều kiện trong backend. **Prompt/evaluator không thể thay thế cơ chế bảo vệ giao dịch.**

### 9.2. Memory Advisors

Khi chấm hội thoại nhiều lượt, lưu:

- Memory advisor/policy version.
- Cách xác định conversation/session ID.
- Số lượt lịch sử hoặc chiến lược tóm tắt.
- Quy tắc lưu/đọc/expiration và quy tắc reset giữa các case.
- Thứ tự đưa memory cùng RAG context vào prompt.
- Chính sách cô lập người dùng và môi trường.

Hai case chạy song song không được vô tình dùng chung conversation ID và làm nhiễu câu trả lời. Với test nhiều lượt của cùng một case, cần giữ thứ tự lượt trong khi vẫn có thể chạy các case độc lập song song.

### 9.3. Tool và Memory là hai nguồn thay đổi độc lập

Nếu model trả lời trạng thái đơn sai:

- Có thể tool backend trả dữ liệu cũ.
- Có thể model không gọi tool.
- Có thể memory đưa vào trạng thái đơn của lượt trước.
- Có thể tool result đúng nhưng prompt diễn giải sai.
- Có thể quyền truy cập bị áp dụng sai.

Nếu chỉ lưu requested model và prompt version, rất khó phân biệt nguyên nhân. Run manifest cùng attempt/tool/memory evidence tạo thành bằng chứng để khoanh vùng.

## 10. Evaluator và rubric cũng có phiên bản

Kết quả chấm không phải một sự thật bất biến. Trong Spring AI, các evaluator như `RelevancyEvaluator` và `FactCheckingEvaluator` có thể hỗ trợ đánh giá ngữ nghĩa. Khi dùng LLM-as-a-judge, verdict phụ thuộc vào model chấm, prompt chấm, rubric và dữ liệu đưa vào judge.

### 10.1. Nên ghi các trường nào?

| Trường | Ý nghĩa |
| --- | --- |
| `evaluatorId`/`evaluatorVersion` | Loại/phiên bản bộ chấm |
| `rubricVersion` | Tiêu chí PASS/FAIL và mô tả lỗi |
| `judgeModelProvider`/`judgeModelId` | Model dùng để chấm nếu có |
| `judgePromptVersion` | Template hướng dẫn judge |
| `judgeParameters` | Sampling/format/timeout/retry của judge |
| `referenceSourceVersion` | Nguồn chuẩn cho factual correctness |
| `inputEvidenceRefs` | Answer/context nào được judge nhìn |
| `humanReviewPolicyVersion` | Khi nào chuyên gia xác minh |
| `resultSchemaVersion` | Cấu trúc verdict và mức điểm |

Một `passRate` từ `judge-v1` không thể so trực tiếp tuyệt đối với `judge-v2` nếu hai bộ chấm khác rubric hoặc độ nhạy. Có thể chạy lại cả hai judge trên cùng bộ answer/evidence cố định để ước lượng tác động phương pháp.

### 10.2. Chấm relevance và groundedness bằng dữ liệu đúng

- **Relevance:** đối chiếu question và actual answer.
- **Groundedness:** actual answer và **effective context** model đã nhận.
- **Factual correctness:** actual answer và reference facts/documents đã được xác minh.
- **Retrieval metric:** IDs/nhãn tài liệu liên quan và actual retrieved results.
- **Tool correctness:** expected tool, actual tool events và trạng thái backend khi cần.

`FactCheckingEvaluator` dựa trên context được cung cấp để kiểm tra sự hỗ trợ của answer; nó **không mặc nhiên biết chính sách mới nhất nếu context không có nguồn chuẩn**. Luôn diễn giải kết quả theo input và rubric cụ thể.

### 10.3. Trạng thái verdict

Một hệ đánh giá nên phân biệt:

- `PASS`: đủ bằng chứng và đáp ứng tiêu chí.
- `FAIL`: đủ bằng chứng và không đáp ứng tiêu chí.
- `NOT_EVALUATED`: thiếu evidence, evaluator timeout/lỗi, hoặc chưa có nhãn.
- `NOT_APPLICABLE`: metric không áp dụng cho case.
- `EXECUTION_ERROR`: pipeline không tạo response hợp lệ để chấm.

Không tự coi `NOT_EVALUATED` thành PASS. Khi so run, báo cả số ca đã chấm và chưa chấm; nếu evaluator hoạt động khác giữa hai run thì điểm tổng có thể sai lệch dù ứng dụng không đổi.

## 11. Cấu hình vận hành: concurrency, timeout, retry, quota và ngân sách

Nếu đánh giá chất lượng **và** độ trễ/chi phí, các điều kiện chạy là một phần của thí nghiệm.

| Tham số | Tại sao cần lưu |
| --- | --- |
| `maxInFlightCases` | Ảnh hưởng tải, rate limit và độ trễ |
| `maxProviderConcurrentCalls` | Bảo vệ số lời gọi model cùng lúc |
| RPM/TPM budget | 429 hoặc throttle có thể làm chậm batch |
| Timeout model/tool/evaluator | Quyết định tỉ lệ hoàn tất kỹ thuật |
| Retry strategy/backoff | Ảnh hưởng số requests, latency và chi phí |
| Batch deadline | Phân biệt run hoàn tất với run bị ngắt |
| Region/endpoint | Có thể ảnh hưởng latency, availability |
| Cache policy/version | Có thể ảnh hưởng token billing và response time |
| Sampling config | Ảnh hưởng chọn case, tỷ lệ chấm/telemetry |
| Runtime/build | Code Java/Spring AI/SDK, container, dependencies |

### 11.1. Batch có số công việc đồng thời giới hạn

Một batch 200 case chạy `maxInFlight=4` khác với cùng dataset chạy `maxInFlight=32` khi nhà cung cấp có quota hạn chế. Ở mức 32, nhiều case có thể bị 429/timeout hoặc retry; so p95 với mức 4 rồi kết luận prompt làm ứng dụng chậm là không thỏa đáng.

Khi so baseline và candidate, nên giữ điều kiện tải tương đương hoặc công bố rõ chênh lệch. Nếu giới hạn toàn tài khoản bị chia sẻ với những job khác, cần ghi nhận tải bên ngoài trong khả năng cho phép.

### 11.2. Manifest không thay thế sự kiện retry

Manifest có thể nói `maxAttempts=3`, nhưng attempt evidence phải ghi thực tế có retry hay không, lý do và số lần. Một request được tạo câu trả lời đúng sau 3 lần retry có điểm chất lượng PASS nhưng chi phí và độ trễ cao hơn request PASS ngay lần đầu.

Không nên gộp technical failure và quality failure thành một trạng thái chung.

### 11.3. Bảng giá là một phiên bản dữ liệu

Để tính chi phí model theo token:

\[
\text{Cost} =
\frac{\text{inputTokens}\times\text{priceInputPerMillion}}{10^6}
+
\frac{\text{outputTokens}\times\text{priceOutputPerMillion}}{10^6}.
\]

Ví dụ **giá giả định** 2 USD/triệu input tokens và 8 USD/triệu output tokens: 2.000 input cùng 500 output tokens có chi phí ước tính:

\[
\frac{2000\times2+500\times8}{10^6}=0{,}008\;\mathrm{USD}.
\]

Để tái tính kết quả, lưu **bảng giá và ngày hiệu lực**, tách chi phí tạo câu trả lời với chi phí evaluator. Phí thực còn có thể phụ thuộc embedding, reranking, cache, tool, hạ tầng và quy tắc billing của provider.

## 12. Java: cấu trúc manifest bất biến và ghi ra JSON

Ví dụ Java 17+ dùng Jackson và `JavaTimeModule`, thường có thể dùng trong ứng dụng Spring Boot sau khi khai báo dependency tương ứng. Mục tiêu của ví dụ là **thiết kế record và lưu manifest chỉ một lần**, không phải tự động đọc mọi default từ Spring AI.

### 12.1. Khai báo typed records

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.Objects;

public final class EvaluationRunSchema {

    public record PromptConfig(
            String templateId,
            String templateVersion,
            String templateDigest) {}

    public record ModelConfig(
            String provider,
            String requestedModelId,
            Double temperature,
            Double topP,
            Integer maxOutputTokens) {}

    public record DataConfig(
            String datasetId,
            String datasetVersion,
            String datasetDigest,
            String corpusVersion,
            String indexVersion) {}

    public record EvaluationConfig(
            String rubricVersion,
            String judgeVersion) {}

    public record ExecutionConfig(
            int maxInFlight,
            int maxAttempts,
            long perCallTimeoutMs) {}

    public record RunManifest(
            String schemaVersion,
            String runId,
            Instant createdAt,
            String environment,
            String applicationBuild,
            PromptConfig prompt,
            ModelConfig model,
            DataConfig data,
            EvaluationConfig evaluation,
            ExecutionConfig execution,
            Map<String, String> safeExtra) {

        public RunManifest {
            Objects.requireNonNull(runId, "runId");
            Objects.requireNonNull(createdAt, "createdAt");
            Objects.requireNonNull(prompt, "prompt");
            Objects.requireNonNull(model, "model");
            Objects.requireNonNull(data, "data");
            Objects.requireNonNull(evaluation, "evaluation");
            Objects.requireNonNull(execution, "execution");

            // Không dùng input tùy ý làm tên tệp/thư mục.
            if (!runId.matches("[A-Za-z0-9_-]+")) {
                throw new IllegalArgumentException("Invalid runId");
            }
            if (execution.maxInFlight() < 1
                    || execution.maxAttempts() < 1) {
                throw new IllegalArgumentException("Invalid execution limits");
            }

            safeExtra = safeExtra == null
                    ? Map.of() : Map.copyOf(safeExtra);
        }
    }

    private EvaluationRunSchema() {}
}
~~~

`safeExtra` chỉ nên chứa metadata đã được kiểm duyệt và có số lượng hữu hạn; **không** đưa API key, raw prompt, tên người dùng hoặc mật khẩu vào đó. Việc dùng kiểu dữ liệu rõ ràng hạn chế lỗi chính tả tên field và giúp review thay đổi schema.

### 12.2. Ghi JSON không ghi đè file manifest đã có

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public final class RunManifestWriter {

    private final ObjectMapper mapper = new ObjectMapper()
            .registerModule(new JavaTimeModule());

    public Path writeNew(
            Path runDirectory,
            EvaluationRunSchema.RunManifest manifest)
            throws IOException {

        Files.createDirectories(runDirectory);

        Path output = runDirectory.resolve("run-manifest.json");

        // CREATE_NEW từ chối ghi đè nếu đã tồn tại.
        try (OutputStream stream = Files.newOutputStream(
                output,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE)) {

            mapper.writerWithDefaultPrettyPrinter()
                    .writeValue(stream, manifest);
        }

        return output;
    }
}
~~~

Đoạn mã minh họa **chống overwrite**, nhưng chưa phải lưu trữ production chống lỗi giữa chừng: nếu quá trình chết trong lúc ghi, file có thể bị dở dang. Thiết kế hoàn chỉnh nên ghi tệp tạm trong cùng thư mục, đồng bộ dữ liệu phù hợp rồi đổi tên nguyên tử khi filesystem hỗ trợ, xử lý `FileAlreadyExistsException` và kiểm tra manifest sau khi ghi.

Không nên tự động sửa manifest đã được gắn với verdict cũ. Khi phát hiện cấu hình sai, lưu một **run mới** hoặc sự kiện điều chỉnh có audit trail, giữ lại bản lịch sử để giải thích sự khác biệt.

### 12.3. Tạo một manifest có nội dung minh họa

~~~java
import java.time.Instant;
import java.util.Map;

EvaluationRunSchema.RunManifest manifest =
        new EvaluationRunSchema.RunManifest(
                "run-manifest-v1",
                "policy_eval_candidate_v4",
                Instant.parse("2026-05-18T09:00:00Z"),
                "staging",
                "build-2481",
                new EvaluationRunSchema.PromptConfig(
                        "policy-answer", "v4", "sha256-from-artifact-store"),
                new EvaluationRunSchema.ModelConfig(
                        "example-provider", "model-stable", 0.2, 0.9, 512),
                new EvaluationRunSchema.DataConfig(
                        "policy-eval", "v3",
                        "sha256-from-dataset-snapshot",
                        "policy-v3", "index-v3"),
                new EvaluationRunSchema.EvaluationConfig(
                        "policy-rubric-v3", "judge-v2"),
                new EvaluationRunSchema.ExecutionConfig(
                        4, 2, 25000),
                Map.of("task", "policy-rag"));
~~~

Trong dự án thật, **tính digest từ bytes artifact đã lưu**, không dùng chuỗi minh họa `sha256-from-artifact-store` như digest hợp lệ. Đồng thời ghi các field resolved từ cấu hình ứng dụng thực; không điền tay bằng giá trị dự đoán rồi coi là kết quả quan sát.

## 13. Snapshot và content digest: làm thế nào để nhận biết thay đổi ẩn?

Một tag `v1` chỉ là tên do nhóm đặt. Để phát hiện một file bị sửa mà không đổi tag, có thể dùng **content digest**.

### 13.1. Ví dụ Java tính SHA-256 cho tệp artifact

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class ArtifactDigest {

    public static String sha256(Path file) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");

            try (InputStream raw = Files.newInputStream(file);
                 DigestInputStream input =
                         new DigestInputStream(raw, digest)) {

                byte[] buffer = new byte[8192];
                while (input.read(buffer) != -1) {
                    // DigestInputStream cập nhật digest khi đọc.
                }
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    private ArtifactDigest() {}
}
~~~

Khi lưu manifest, có thể ghi `algorithm=SHA-256` cùng giá trị digest thực và tham chiếu đến artifact. Lúc cần tái chạy, đọc lại artifact, tính lại digest và kiểm tra có khớp không.

### 13.2. Digest có giới hạn gì?

- Hash của file không bảo đảm **chất lượng nhãn** hay sự đúng đắn của nguồn.
- Hash giống nhau không bảo đảm mọi nguồn động bên ngoài (provider, database, tool) giống nhau.
- Nếu serialize JSON không theo quy tắc ổn định, hai cấu trúc mang cùng ý nghĩa có thể cho byte khác nhau; cần chọn cách canonicalization hoặc dùng digest trên **artifact bytes chính xác**.
- Một object storage path có nội dung mutable vẫn có rủi ro; nên pin bằng version ID/snapshot và có chính sách bất biến.
- Không đưa digest làm bằng chứng thay cho việc có thể đọc nội dung. Với ca fact checking, người kiểm duyệt vẫn cần truy cập nội dung nguồn có phân quyền.

### 13.3. Những artifact cần kiểm toàn vẹn trước tiên

Ưu tiên:

1. Dataset và nguồn nhãn.
2. Prompt template và rubric/judge prompt.
3. Tool schema, document source snapshot và index metadata.
4. Cấu hình pipeline và test fixture ảnh hưởng trực tiếp kết quả.
5. Báo cáo verdict/metrics sau khi run hoàn thành nếu cần audit.

Không nhất thiết băm mọi span hoặc every individual token. Hãy xác định cấp độ bằng chứng phù hợp với mục tiêu so sánh và chi phí lưu trữ.

## 14. Liên kết manifest với attempt, verdict và trace

Một run có thể gồm 100 case, và một case có thể chạy lặp 3 lần. Trong mỗi attempt, model có thể được gọi nhiều lượt.

### 14.1. Attempt record

~~~json
{
  "runId": "policy_eval_candidate_v4",
  "caseId": "REFUND-001",
  "attemptId": "candidate_v4_REFUND-001_rep1",
  "repeatIndex": 1,
  "startedAt": "2026-05-18T09:01:14Z",
  "endedAt": "2026-05-18T09:01:16Z",
  "effectiveConfigRef": "run-manifest:policy_eval_candidate_v4",
  "actualRetrievedDocumentIds": [
    "policy-v3#refund"
  ],
  "effectiveContextRefs": [
    "secure-context-ref-01"
  ],
  "modelCallIds": ["model-call-001"],
  "toolCallIds": [],
  "answerRef": "secure-answer-ref-01",
  "technicalStatus": "COMPLETED",
  "traceId": "trace-id-if-observed"
}
~~~

Các ID trace/evidence mang tính minh họa. Trong hệ thống thật, chỉ ghi `traceId` khi hệ tracing cung cấp, và không tự chế ID rồi coi nó đã được export.

### 14.2. Verdict record

~~~json
{
  "evaluationId": "candidate_v4_REFUND-001_groundedness_judge2",
  "attemptId": "candidate_v4_REFUND-001_rep1",
  "metric": "groundedness",
  "status": "PASS",
  "rubricVersion": "policy-rubric-v3",
  "judgeVersion": "judge-v2",
  "evidenceRefs": [
    "secure-context-ref-01",
    "secure-answer-ref-01"
  ],
  "feedback": "Các khẳng định chính được ngữ cảnh cung cấp hỗ trợ."
}
~~~

**Một manifest không tự là verdict.** Manifest ghi cách ứng dụng được cấu hình; verdict ghi kết luận theo rubric trên execution evidence. Muốn xác định lỗi, phải đối chiếu cả ba.

### 14.3. Bảng khóa liên kết

| Khóa | Sở hữu dữ liệu | Công dụng |
| --- | --- | --- |
| `runId` | Run manifest | Liên kết cùng đợt thí nghiệm |
| `caseId` | Dataset | Tìm kỳ vọng của tình huống |
| `attemptId` | Execution evidence | Nối answer/context/tool và điểm chấm |
| `modelCallId` | Model usage events | Đếm lượt gọi, token và latency |
| `toolCallId` | Tool events | Kiểm tool name, args/status, side effects |
| `evaluationId` | Verdicts | Tránh ghi đè các lần chấm |
| `traceId`/`spanId` | Tracing | Chẩn đoán thời gian và lỗi của request |
| `artifactDigest` | Artifact store | Xác nhận snapshot đã dùng |

Không dùng `caseId` thay cho `attemptId`: cùng case có nhiều lần chạy với output khác. Cũng không dùng `traceId` làm tên ID duy nhất của ca, vì tracing có thể bị sampling hoặc một workflow có nhiều trace liên quan.

## 15. Mô hình lưu trữ và quy trình đóng băng manifest

Một cấu trúc ví dụ theo run:

~~~text
evaluation-artifacts/
└── policy_eval_candidate_v4/
    ├── run-manifest.json
    ├── artifact-index.json
    ├── case-attempts.jsonl
    ├── model-calls.jsonl
    ├── tool-events.jsonl
    ├── evaluator-verdicts.jsonl
    ├── metrics-summary.json
    └── completion-summary.json
~~~

Đây là **gợi ý tổ chức**, không phải thư mục do Spring AI tự sinh. Những record có dữ liệu nhạy cảm có thể ở kho khác, còn JSONL chỉ giữ reference.

### 15.1. Quy trình ghi theo vòng đời run

~~~mermaid
flowchart TD
    A["Tạo run ID + resolve config"] --> B["Snapshot / pin artifacts"]
    B --> C["Tính digest + validate manifest"]
    C --> D["Ghi manifest mới không overwrite"]
    D --> E["Chạy cases với attempt IDs"]
    E --> F["Ghi evidence + usage + trace refs"]
    F --> G["Chấm metric + lưu verdicts"]
    G --> H["Tổng hợp và ghi trạng thái run"]
    H --> I["Đóng run / lưu completion summary"]
    I --> J["So baseline + candidate"]
~~~

**Manifest mô tả cấu hình nên được đóng băng trước khi chạy.** Nếu có sự kiện ngoài ý muốn, như failover provider hoặc thay đổi model alias được phát hiện khi chạy, ghi vào **observed events hoặc run completion summary**, không âm thầm sửa lại desired config ban đầu.

### 15.2. Trạng thái run không phải tỷ lệ pass

Một run có thể có:

- `COMPLETED`: mọi case có terminal execution outcome theo hợp đồng.
- `PARTIAL`: còn case chưa xử lý/xử lý chưa được ghi nhận.
- `FAILED`: batch không thể hoàn thành vì lỗi runner/hạ tầng nghiêm trọng.
- `CANCELLED`: chủ động dừng.

Cùng lúc, chất lượng có thể có nhiều `PASS`, `FAIL` và `NOT_EVALUATED`. Run `COMPLETED` **không** nghĩa là 100% câu trả lời đạt chất lượng.

### 15.3. Hạn chế sửa manifest sau khi khóa

Nếu phải bổ sung thông tin phát hiện sau khi chạy, hãy tạo một record bổ sung có:

- `runId` và khóa tham chiếu manifest ban đầu.
- Thời điểm phát hiện.
- Trường được điều chỉnh hoặc bổ sung.
- Lý do và nguồn xác minh.
- Người hoặc job tạo.
- Phiên bản mới của report/metadata.

Nhờ vậy, người đọc biết đâu là cấu hình đã khai báo tại thời điểm chạy và đâu là thông tin hiệu chỉnh về sau. Không sửa lịch sử ngầm.

## 16. Dùng manifest để so baseline và candidate công bằng

Mục tiêu của versioning không phải lưu metadata cho đẹp; nó giúp trả lời **thay đổi nào thật sự tạo ra chênh lệch**.

### 16.1. Ví dụ so hai run

| Cấu hình | Baseline | Candidate |
| --- | --- | --- |
| Dataset | `policy-eval-v3` | `policy-eval-v3` |
| Reference facts | `policy-v3` | `policy-v3` |
| Prompt template | `prompt-v4` | `prompt-v5` |
| Model/provider | `model-A` | `model-A` |
| Corpus/index | `index-v3` | `index-v3` |
| Retrieval `topK` | 5 | 5 |
| Tool schema | `tools-v2` | `tools-v2` |
| Judge/rubric | `judge-v2 / rubric-v3` | `judge-v2 / rubric-v3` |
| maxInFlight | 4 | 4 |
| Provider quota regime | Cùng hợp đồng giả định | Cùng hợp đồng giả định |

Nếu chỉ `prompt-v4 → prompt-v5` thay đổi, sự khác biệt về điểm số có cơ sở hơn để quy cho prompt, **nhưng chưa phải chứng minh tuyệt đối** do output ngẫu nhiên, provider model alias hoặc biến động runtime.

### 16.2. Kết quả giả định

Trên cùng 100 case được chấm theo một rubric:

| Metric | Baseline | Candidate |
| --- | ---: | ---: |
| Relevance PASS | 92/100 | 95/100 |
| Groundedness PASS | 96/100 | 93/100 |
| Factual correctness PASS | 94/100 | 93/100 |
| Tool contract tests | 100/100 | 100/100 |
| p95 latency | 2,1 giây | 2,7 giây |
| Input tokens trung bình | 1.200 | 1.850 |
| Estimated model cost/request | 0,004 USD | 0,005 USD |

Số liệu chỉ để luyện phân tích. Candidate cải thiện relevance nhưng groundedness/factual correctness giảm, đồng thời latency và token tăng. Không nên phát hành chỉ vì “điểm chung cao hơn” nếu các gate quan trọng không đạt.

### 16.3. Kiểm tra chênh lệch cấu hình trước khi đọc điểm

Một quy trình so sánh nên làm theo thứ tự:

1. Kiểm `schemaVersion` của hai manifest có tương thích không.
2. So `datasetVersion` và digest của snapshot; không chỉ so tên.
3. So nguồn chuẩn và ngày hiệu lực.
4. So provider/model ID, resolved options và thông tin revision có sẵn.
5. So prompt template digest và advisor chain.
6. So corpus/index/embedding/chunking/retrieval.
7. So tools, memory policy và fixture.
8. So rubric, judge, reference sources và cách tính metric.
9. So concurrency, retry, timeout, region/load và biến môi trường quan trọng.
10. Sau đó mới so **per-case verdicts**, sample size, trace, token, latency và cost.

Nếu hai manifest khác nhiều trường, báo cáo nên nói “có nhiều yếu tố cùng thay đổi” và tránh kết luận chỉ một yếu tố gây ra kết quả.

### 16.4. Dataset và evaluator thay đổi cần cách so riêng

Nếu ca tham chiếu đã được sửa từ “30 ngày” sang “14 ngày” vì chính sách mới, baseline cũ và candidate mới đang được chấm theo **hai chuẩn khác nhau**. Muốn so công bằng, có thể chạy lại cả hai phiên bản ứng dụng trên dataset/source snapshot mới, nếu còn khả thi và an toàn.

Nếu judge đổi từ `judge-v1` sang `judge-v2`, có thể lấy **cùng tập output/evidence đã lưu**, chấm bằng cả hai judge để đo mức dịch điểm do phương pháp chấm; không cần chạy lại model sinh answer chỉ để tách ảnh hưởng judge, miễn evidence đủ.

## 17. Manifest kết hợp observability: tìm nguyên nhân suy giảm

Giả sử factual correctness giảm sau một release. Manifest cho biết các thành phần đã đổi; observability cho biết request cụ thể đi qua thành phần nào, tốn bao lâu và lỗi tại đâu.

### 17.1. Bộ tín hiệu nên liên kết

| Tín hiệu | Nguồn | Ý nghĩa |
| --- | --- | --- |
| `runId`, `releaseVersion` | Manifest và deployment metadata | Khoanh vùng phiên bản |
| `caseId`, `attemptId` | Test harness | Xác định ca thất bại |
| Retrieved docs/context refs | RAG evidence | Phân biệt lỗi truy xuất với sinh |
| Tool events/status | Dispatcher/backend | Kiểm đúng hành động và quyền |
| `traceId`, span durations | Tracing | Xem bước chậm, retry, timeout |
| Token usage/model call count | Provider usage | Giải thích context dài, chi phí |
| Verdict/rubric/judge | Evaluation results | Nêu tiêu chí sai và cách chấm |
| Cost table version | Pricing metadata | Tái tính chi phí đúng thời kỳ |

### 17.2. Ví dụ điều tra

Sau khi đổi prompt, một case hỏi chính sách trả lời “30 ngày”. Run manifest cho thấy `corpusVersion=policy-v3`, nhưng attempt evidence ghi retriever đã trả `policy-v2#refund`. Đây là dấu hiệu cần kiểm tra **index snapshot/filter**, không nên kết luận model sai chỉ từ text.

Nếu attempt evidence lại cho thấy `policy-v3` đã nằm trong effective context nhưng model vẫn nói 30 ngày, hướng điều tra ưu tiên chuyển sang **prompt, model hoặc cách sử dụng bằng chứng**.

Trace có thể cho biết VectorStore chậm hoặc model retry; nó giúp chẩn đoán hiệu năng nhưng **không tự chấm nội dung**. Một lời gọi HTTP 200 cũng có thể hoàn thành rất nhanh mà answer vẫn sai factual correctness.

### 17.3. Dấu hiệu không đủ bằng chứng

Nếu không lưu effective context, không thể kiểm groundedness của attempt chỉ từ `corpusVersion`. Nếu provider không trả usage, không thể tuyên bố số token chính xác bằng cách đoán. Nếu trace sampling bỏ request, phải ghi `traceUnavailable` hoặc tương đương.

Trong mọi trường hợp, **thiếu metadata không nên được thay bằng giá trị tự phỏng đoán** để ép báo cáo ra kết luận.

## 18. Bảo mật và quản trị dữ liệu cấu hình

Manifest có thể bị xem như metadata vô hại, nhưng nó có khả năng chứa thông tin nhạy cảm nếu thiết kế thiếu thận trọng.

### 18.1. Không lưu secrets

Tuyệt đối không ghi vào manifest:

- API keys, bearer tokens, passwords, database credentials.
- Chuỗi kết nối chứa user/password.
- Headers xác thực hoặc kết quả tool chứa session tokens.
- Khóa mã hóa hoặc nội dung bí mật dùng để ký request.

Có thể ghi **tên định danh secret được quản lý** hoặc `secretConfigVersion` theo chính sách, nhưng không ghi giá trị thực. Hash trực tiếp một bí mật có entropy thấp cũng không phải phương án an toàn mặc định.

### 18.2. Raw prompt và dữ liệu kiểm thử

Prompt thực có thể chứa:

- Thông tin cá nhân của người dùng.
- Tài liệu nội bộ từ RAG.
- Trạng thái giao dịch/trả lời tool.
- Lịch sử hội thoại và nội dung có bản quyền.

Nên lưu phiên bản template, content digest và references có quyền. Nếu cần giữ raw evidence để chấm lại, dùng kho riêng có mã hóa, phân quyền, thời hạn lưu và quy trình xóa. Không đưa raw prompt hoặc `userId` làm label của metric Prometheus vì rủi ro dữ liệu và cardinality cao.

### 18.3. Vòng đời bảo quản và audit

Quy định:

1. Ai được đọc manifest và evidence?
2. Dataset/reference source nào được phép dùng?
3. Thời hạn retention của run manifests, raw answers, traces là bao lâu?
4. Khi nhãn nguồn bị sửa, có audit và version mới không?
5. Việc chia sẻ dữ liệu với LLM judge bên ngoài có được phép không?
6. Có cần kiểm duyệt lại dữ liệu trước khi đưa lỗi production vào regression dataset?

Tách quyền quản lý cấu hình và quyền xem raw nội dung nếu cần. **Manifest đầy đủ về kỹ thuật không đồng nghĩa được phép công khai mọi dữ liệu trong đó**.

## 19. Tích hợp vào CI/CD và quy trình phát hành

Một run manifest là thành phần đầu vào của release gate, không chỉ là phụ lục của báo cáo.

### 19.1. Luồng gợi ý

~~~text
Commit / configuration change
  → resolve build + prompt/model/pipeline versions
  → select immutable dataset snapshot and rubric
  → create runId and manifest
  → run evaluation cases with attempt IDs
  → collect actual answer/context/tool evidence
  → compute verdicts and operational metrics
  → validate gate and compare baseline
  → store immutable report + links
  → approve / reject candidate
~~~

Nếu run bị hủy nửa chừng, manifest vẫn tồn tại nhưng `status=PARTIAL` hoặc `FAILED`. Không được báo release gate đã PASS khi một tập ca bắt buộc chưa chạy/chưa chấm.

### 19.2. Release gate minh họa

~~~yaml
releaseGate:
  requiredManifestSchema: run-manifest-v1
  requireDatasetSnapshotDigest: true
  requirePromptArtifactVersion: true
  requireJudgeAndRubricVersions: true
  criticalFunctionalTests: must-pass
  quality:
    groundednessPassRate: ">= 0.95"
    factualCorrectnessPassRate: ">= 0.98"
    criticalCases: must-pass
  operations:
    p95LatencyMs: "<= 2500"
    technicalErrorRate: "<= 0.01"
  statusRequirements:
    incompleteCriticalAttempts: 0
    notEvaluatedCriticalCases: 0
~~~

Đây là **ngưỡng giả định**, không phải mặc định của Spring AI. Tiêu chí thực tế cần dựa vào mức rủi ro, độ tin cậy dataset/nhãn và tải của sản phẩm. Đặc biệt, lỗi phân quyền tool không thể được bù bởi điểm relevance cao.

### 19.3. Artifact tối thiểu để bàn giao

Một bộ bàn giao tốt thường gồm:

- Run manifest với config đã resolve và liên kết snapshot.
- Dataset ID/version và digest.
- Prompt/rubric/judge artifact refs và digest nếu cần.
- Attempt/results với trạng thái đầy đủ.
- Báo cáo quality theo nhóm, số mẫu và lỗi.
- Metrics/traces/usage/cost summary với phương pháp đo.
- Danh sách ca hồi quy mới và quyết định phát hành.

## 20. Bài thực hành: ghi cấu hình và tìm nguyên nhân khi điểm giảm

**Bối cảnh:** chatbot Spring AI tra cứu chính sách hoàn phí giả định bằng RAG, có tool `getOrderStatus` để đọc tình trạng đơn. Nhóm chuẩn bị thử prompt mới và đổi `top-k`.

### Phần A — Tạo baseline manifest

1. Chọn một dataset 20 case có reference facts, nguồn hiện hành, ca thiếu nguồn và ca tool.
2. Ghi `datasetVersion`, prompt template version, model/provider, model options, corpus/index, top-k, tool schema, rubric và judge.
3. Ghi code/build version, môi trường, concurrency/timeout/retry.
4. Tạo snapshot dataset và prompt, tính digest thực từ artifact.
5. Tạo `runId` mới và lưu `run-manifest.json` theo cơ chế không overwrite.

**Đầu ra:** manifest có ít nhất 15 trường cần thiết, không chứa secrets.

### Phần B — Chạy và lưu attempt evidence

Chạy 20 case; mỗi case cần `attemptId` và actual answer. Với case RAG, lưu retrieved document IDs và effective context refs. Với case tool, lưu tool name/args/status/hậu điều kiện khi có. Ghi token, duration và trace ID khi tracing thật tồn tại.

**Đầu ra:** có thể truy ngược `REFUND-001` từ case về answer, context và model call của đúng attempt.

### Phần C — Candidate có một thay đổi

Chỉ đổi prompt template từ `prompt-v4` sang `prompt-v5`, giữ nguyên dataset, model, index, judge, rubric và tải càng tương đồng càng tốt. Tạo run mới, manifest mới và kết quả mới. Dùng một bảng diff để xem những trường thay đổi.

**Đầu ra:** báo cáo có các ca PASS→FAIL và FAIL→PASS, cùng giới hạn phân tích do tính ngẫu nhiên của model.

### Phần D — Candidate thay nhiều biến

Đổi đồng thời `top-k=3 → 5` và corpus snapshot. Chạy đánh giá mới, quan sát groundedness, factual correctness, token và p95. Giải thích vì sao không thể quy mọi thay đổi chất lượng chỉ cho `top-k`.

**Đầu ra:** báo cáo so cấu hình có ghi các yếu tố gây nhiễu và kế hoạch thử lại có kiểm soát.

### Phần E — Thay judge mà không chạy lại model

Nếu đã lưu đủ answer và effective context, tạo phiên bản rubric/judge mới, chấm lại trên cùng attempt evidence rồi so verdict. Phân biệt “điểm đổi vì judge” với “điểm đổi vì model” và lưu `evaluationId` mới.

**Đầu ra:** hai bộ verdict tham chiếu cùng attempt, khác `judgeVersion`/`rubricVersion`.

### Phần F — Kiểm tra chi phí và độ trễ

Tổng hợp token usage, chi phí theo bảng giá giả định và p95 latency từ dữ liệu phân bố phù hợp. Tách chi phí sinh câu trả lời với chi phí chấm. Trường hợp thiếu usage hoặc trace, nêu rõ giới hạn thay vì tạo dữ liệu giả.

**Đầu ra:** bảng gồm chất lượng, technical completion, latency và cost theo run.

### Checklist nghiệm thu

- [ ] Mỗi run có `runId` duy nhất, schemaVersion và timestamp.
- [ ] Dataset snapshot và reference labels có phiên bản bất biến/digest.
- [ ] Prompt template version và ảnh hưởng advisor/context được ghi.
- [ ] Model/provider, resolved options và giới hạn revision được mô tả.
- [ ] RAG corpus/index/chunker/embedding/retrieval params được lưu khi có.
- [ ] Tool schema, fixture, authorization và memory policy được ghi nếu dùng.
- [ ] Evaluator/rubric/judge versions được lưu.
- [ ] Concurrency, timeout, retry và thông tin tải có trong manifest.
- [ ] Manifest không bị overwrite sau run, có completion summary khi kết thúc.
- [ ] Attempt evidence và verdict nối đúng `runId`/`caseId`/`attemptId`.
- [ ] Không lưu secrets và raw dữ liệu nhạy cảm ngoài phạm vi được phép.
- [ ] Báo cáo so baseline/candidate kiểm sự tương thích của config trước khi so điểm.
- [ ] Điểm chất lượng không bị nhầm với HTTP success, latency hoặc cost.
- [ ] Các ca không có bằng chứng/judge lỗi được ghi rõ `NOT_EVALUATED`.

### Câu hỏi tự kiểm tra

1. Vì sao chỉ ghi tên prompt và model không đủ để tái lập một evaluation run?
2. Khác biệt giữa desired, resolved và observed configuration là gì?
3. Khi cùng một `promptVersion` nhưng SHA-256 của template thay đổi, nhóm cần điều tra điều gì?
4. Tại sao cùng `corpusVersion` nhưng index snapshot khác có thể làm RAG cho kết quả khác?
5. Nếu câu trả lời bám đúng tài liệu đã truy xuất nhưng sai chính sách hiện hành, manifest và attempt evidence cần những trường nào để chứng minh?
6. Một case chạy 3 lần có nên dùng chung `attemptId` không? Vì sao?
7. Khi model alias được nhà cung cấp cập nhật mà không đổi tên, cần ghi thông tin nào và còn giới hạn tái lập gì?
8. Nếu judge mới cho điểm cao hơn trên đúng cùng answer/context, liệu có đủ bằng chứng nói prompt tốt hơn?
9. Vì sao phải lưu cấu hình concurrency và quota khi so p95 latency?
10. Có nên lưu `API_KEY`, raw tool arguments hoặc toàn bộ prompt trong `run-manifest.json` không?
11. Khi provider không trả token usage, có được ghi số token “ước lượng” như số liệu usage chính thức không?
12. Nếu một run chỉ hoàn tất 90/100 case, tại sao không được gắn `status=COMPLETED` và thông báo quality pass rate trên cả 100 case?
13. Khi đổi đồng thời prompt, top-k và embedding model, cách kết luận nguyên nhân cải thiện nào là phù hợp?
14. Chấm lại cùng attempt bằng judge mới có thay đổi trace, latency và kết quả truy xuất của execution cũ không?

## 21. Tổng kết

**Lưu cấu hình của mỗi lần chạy** là nền tảng để biến đánh giá Spring AI thành quy trình có thể kiểm chứng và so sánh, thay vì tập hợp các điểm số thiếu bối cảnh. Một **run manifest bất biến** cần nhận diện dataset và nguồn chuẩn, prompt template và cách ghép context, model/provider và tham số, RAG corpus/index/retrieval, tool/memory configuration, evaluator/rubric, cùng điều kiện chạy.

Tuy nhiên, manifest chỉ nói **hệ thống được cấu hình như thế nào**. Muốn biết thực tế xảy ra gì, phải liên kết với `attemptId`, retrieved/effective context, model/tool calls, answer, usage và trace. Muốn biết đáp ứng yêu cầu đến đâu, cần verdict có rubric/judge version và bằng chứng nguồn. Ba lớp **manifest → execution evidence → evaluation result** giúp điều tra chính xác hơn khi chất lượng, token, chi phí hoặc độ trễ thay đổi giữa các phiên bản prompt, model và pipeline.

### Tài liệu tham khảo

- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI — Chat Model API](https://docs.spring.io/spring-ai/reference/api/chatmodel.html)
- [Spring AI — Advisors API](https://docs.spring.io/spring-ai/reference/api/advisors.html)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring Boot — Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Java — MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)
