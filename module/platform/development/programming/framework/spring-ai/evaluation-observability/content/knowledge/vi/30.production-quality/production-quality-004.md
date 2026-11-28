# Chất lượng khi vận hành: Phân biệt thay đổi dữ liệu, prompt, mô hình và công cụ

## 1. Vì sao phải tìm đúng nguồn gây thay đổi?

Một câu trả lời AI có thể khác hôm qua dù người dùng tưởng rằng họ đã gửi cùng một câu hỏi. Có thể dữ liệu đầu vào đã khác, prompt được cập nhật, model alias trỏ sang revision mới hoặc tool trả về dữ liệu khác. Cũng có thể nhiều yếu tố cùng thay đổi trong một lần release.

Nếu chỉ nhìn điểm relevance giảm hoặc câu trả lời mới khác câu trả lời cũ, nhóm phát triển chưa thể kết luận nguyên nhân. Thay đổi có thể đến từ:

- **Dữ liệu:** câu hỏi, lịch sử hội thoại, hồ sơ người dùng, tài liệu RAG hoặc dữ liệu nghiệp vụ đã thay đổi.
- **Prompt:** system instructions, template, biến được render, advisor order, memory context hoặc output schema đã thay đổi.
- **Mô hình:** provider, model revision, deployment, generation parameters, routing hoặc fallback đã thay đổi.
- **Công cụ:** tool được cung cấp, tên, mô tả, JSON schema, quyền, implementation, dependency hoặc kết quả thực thi đã thay đổi.

Bốn nhóm này tương tác với nhau. Prompt mới có thể khiến model chọn tool khác; tool trả về dữ liệu mới làm câu trả lời khác; model revision mới có thể diễn giải cùng prompt theo cách khác. Muốn xác định nguồn gây thay đổi, cần lưu được cấu hình và dữ liệu của từng interaction, sau đó so sánh trong điều kiện có kiểm soát.

Bài học thuộc chương **Chất lượng khi vận hành** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline.

Sau bài học, bạn có thể:

- Nhận diện bốn nhóm thay đổi và các thành phần con bên trong mỗi nhóm.
- Phân biệt thay đổi có chủ đích với thay đổi ngoài dự kiến.
- Tạo run manifest để ghi lại dữ liệu, prompt, model và tool thực sự đã dùng.
- So sánh hai lần chạy trên cùng input và cùng context.
- Thiết kế replay, shadow run, canary và controlled experiment.
- Dùng Spring AI observations và traces để truy nguyên execution path.
- Xác định khi nào cần kiểm tra một yếu tố riêng lẻ và khi nào phải kiểm tra tương tác giữa nhiều yếu tố.
- Kết luận dựa trên evidence, evaluator, human review và operational metrics.

## 2. Một kết quả AI có nhiều đầu vào hơn câu hỏi người dùng

Một lời gọi ChatClient không chỉ phụ thuộc vào chuỗi câu hỏi nhìn thấy trên giao diện. Kết quả thực tế thường phụ thuộc vào một execution context rộng hơn:

~~~mermaid
flowchart TD
    USER["User request"] --> DATA["Data and conversation context"]
    DATA --> PROMPT["Rendered prompt and advisors"]
    PROMPT --> MODEL["Provider and model revision"]
    MODEL --> ROUTE{"Tool call requested?"}
    ROUTE -->|No| ANSWER["Final response"]
    ROUTE -->|Yes| TOOL["Tool registry and execution"]
    TOOL --> RESULT["Tool result"]
    RESULT --> MODEL
    ANSWER --> EVAL["Evaluation and review"]
    EVAL --> QUALITY["Observed quality"]
~~~

Có thể mô hình hóa kết quả như:

\[
Y = f(D, P, M, T, R)
\]

Trong đó:

- D: dữ liệu và context.
- P: prompt cùng cấu hình pipeline.
- M: model/provider và generation settings.
- T: tool registry, schema và implementation.
- R: runtime environment, network, policy và các dependency liên quan.
- Y: response, tool actions và các quality outcomes.

Đây là mô hình tư duy để phân tích nguyên nhân. Trong production, các thành phần có thể phụ thuộc lẫn nhau và có yếu tố ngẫu nhiên. Không nên xem hàm f là hoàn toàn xác định.

### 2.1. Phân biệt output khác với quality giảm

Hai response khác nhau không có nghĩa response mới kém hơn. Ví dụ:

- Model mới trả lời ngắn hơn nhưng vẫn đầy đủ và chính xác.
- Prompt mới thay đổi định dạng JSON nhưng giữ nguyên ý nghĩa.
- RAG index mới ưu tiên tài liệu vừa cập nhật.
- Tool trả về trạng thái đơn hàng mới vì nghiệp vụ đã thay đổi.

Hãy phân biệt ba câu hỏi:

1. **Behavior changed:** đầu ra hoặc execution path có thay đổi không?
2. **Cause changed:** thành phần nào đã thay đổi và có thể giải thích khác biệt không?
3. **Quality regressed:** thay đổi đó có làm relevance, factuality, safety, task success, latency hoặc cost vượt guardrail không?

Một dashboard tốt hiển thị riêng change signals và quality outcomes. Không tự động coi mọi behavior change là regression.

## 3. Bốn nhóm thay đổi và dấu hiệu nhận biết

| Nhóm | Những gì có thể thay đổi | Dấu hiệu thường gặp |
| --- | --- | --- |
| Data | User input, history, memory, RAG corpus, retrieval result, business record | Cùng prompt/model nhưng context hoặc evidence khác |
| Prompt | Template, system instruction, variables, examples, advisor order, format constraints | Input/context giống nhau nhưng rendered prompt khác |
| Model | Provider, requested/reported model, revision, parameters, routing, fallback | Prompt và dữ liệu giống nhau nhưng output, finish reason, token usage hoặc latency khác |
| Tool | Tool set, description, schema, authorization, implementation, dependency, result | Tool selection, arguments, execution status hoặc result khác |

Ngoài bốn nhóm, cần ghi nhận **runtime/environment** như network, rate limits, database state, feature flags, application build và configuration. Nếu không, nhóm phát triển có thể quy nhầm lỗi runtime thành model regression.

## 4. Nhóm dữ liệu: xác định context thực sự đã đi vào model

### 4.1. User input

Các yếu tố cần kiểm tra:

- Nội dung câu hỏi có khác không?
- Input có được normalize, rewrite hoặc dịch trước khi gửi model không?
- Có attachment, image, file hoặc structured payload mới không?
- Ngôn ngữ, độ dài, entity hoặc task family có thay đổi không?
- Client có gửi metadata, locale, timezone hoặc format preference khác không?

Giữ một input fingerprint hoặc reference có kiểm soát để biết hai lần chạy có cùng input. Hash giúp phát hiện byte-level changes, nhưng không chứng minh hai câu có cùng ngữ nghĩa. Nếu cần semantic equivalence, dùng canonicalization hoặc human review; không coi embedding similarity là bằng chứng tuyệt đối.

### 4.2. Conversation history và memory

Một câu hỏi giống hệt có thể cho kết quả khác nếu lịch sử hội thoại khác:

- Số lượt trước đó thay đổi.
- Memory summary được cập nhật.
- Một message cũ bị cắt do context window.
- Conversation ID trỏ sang memory khác.
- History được lọc hoặc sắp xếp lại.
- System policy hoặc user profile được bổ sung.

Để tái hiện, cần ghi số message, thứ tự role, message IDs/version references và memory snapshot version. Không nhất thiết lưu raw history ở mọi nơi; có thể lưu secure reference tới snapshot đã mã hóa và redaction.

### 4.3. RAG corpus và retrieval result

Với RAG, cần phân biệt corpus thay đổi với cách retriever chọn evidence:

| Thành phần | Metadata nên ghi |
| --- | --- |
| Corpus | Snapshot/version, ingestion watermark, source revision |
| Document | Document ID, document version, content hash, freshness |
| Chunking | Chunker version, chunk size, overlap, chunk ID |
| Embedding | Provider/model/version, dimensions, normalization |
| Index | Index name/version, build timestamp, schema |
| Retrieval | Query rewrite version, filter, tenant scope, topK |
| Reranking | Reranker model/version, rank và score |
| Context assembly | Chunk order, deduplication rule, context token count |

Nếu document ID giống nhau nhưng content hash khác, dữ liệu đã thay đổi. Nếu corpus snapshot giống nhau nhưng retrieved chunk IDs khác, hãy kiểm tra embedding, query rewrite, filter, index build và reranker.

Không so sánh trực tiếp similarity scores từ hai embedding models hoặc hai index configurations khác nhau khi chưa hiệu chỉnh. Score 0,82 ở một model không nhất thiết có cùng ý nghĩa với 0,82 ở model khác.

### 4.4. Business data và external state

Tool hoặc advisor có thể đọc dữ liệu nghiệp vụ từ database, CRM, inventory hay dịch vụ bên ngoài. Cùng một câu hỏi và prompt vẫn phải trả lời khác nếu trạng thái nghiệp vụ thay đổi.

Lưu các thông tin có thể tái hiện:

- Data source và logical dataset version.
- Record revision hoặc event timestamp.
- Query/filter version.
- Read consistency hoặc transaction snapshot nếu quan trọng.
- External API version và response status.
- Cache hit/miss, cache key version và freshness.

Không lưu raw customer records trong telemetry chỉ để so sánh. Dùng opaque references và evidence store được kiểm soát.

## 5. Nhóm prompt: kiểm tra template và prompt đã render

### 5.1. Prompt template version chưa đủ

Một prompt template có thể giữ nguyên version nhưng output khác do biến được render khác. Ví dụ:

~~~text
System: Bạn là trợ lý hỗ trợ khách hàng.
Policy: {{policy_text}}
Locale: {{locale}}
Conversation summary: {{memory_summary}}
Retrieved context: {{retrieved_context}}
User question: {{question}}
Response format: {{output_schema}}
~~~

Nếu locale, policy, memory summary hoặc retrieved context khác, prompt cuối cùng đã khác dù template ID không đổi.

Nên lưu:

- promptTemplateId và immutable version.
- System/developer/user message structure.
- Prompt compiler/renderer version.
- Hash của rendered prompt hoặc secure reference.
- Variable names và giá trị đã redaction.
- Output schema/structured output version.
- Advisor names và order.
- Memory policy và truncation strategy.
- Prompt fragment/source version nếu prompt được ghép từ nhiều module.

### 5.2. Những thay đổi prompt dễ bị bỏ sót

- Đổi một từ trong system instruction.
- Thêm hoặc xóa few-shot examples.
- Đổi thứ tự ví dụ.
- Đổi ngôn ngữ hoặc mức độ chi tiết.
- Thay đổi instruction ưu tiên giữa user input và retrieved content.
- Đổi citation format hoặc JSON schema.
- Thêm policy fragment từ feature flag.
- Đổi advisor order, query rewrite hoặc memory advisor.
- Thay đổi max context hoặc cách cắt prompt.

Một diff văn bản có thể cho biết đoạn nào thay đổi. Nhưng tác động thực tế cần được xác minh trên cùng input, context và model.

### 5.3. Prompt versioning

Dùng version bất biến, không tái sử dụng version cũ sau khi nội dung đã thay đổi. Một manifest nên lưu cả prompt family và version:

~~~json
{
  "prompt": {
    "templateId": "support-answer",
    "version": "v18",
    "rendererVersion": "3",
    "systemPolicyVersion": "policy-2026-11",
    "advisorChain": [
      "memory-advisor-v4",
      "retrieval-advisor-v7",
      "tool-calling-advisor"
    ],
    "outputSchemaVersion": "answer-json-v2",
    "renderedPromptHash": "sha256:example"
  }
}
~~~

Hash trong ví dụ là giả lập. Hash chỉ giúp nhận diện nội dung, không thay thế secure snapshot nếu cần xem hoặc replay prompt.

## 6. Nhóm mô hình: xác định model thực sự đã chạy

### 6.1. Requested model và reported model

Ứng dụng có thể cấu hình một alias hoặc deployment name. Provider có thể trả về model ID/revision khác, hoặc gateway route request sang model khác.

Ghi riêng:

- Provider được cấu hình.
- Requested model/deployment.
- Reported model trong response metadata nếu có.
- Provider endpoint/gateway identity.
- Model revision, deployment revision hoặc digest nếu provider hỗ trợ.
- Fallback model nếu request được route lại.
- Region/zone hoặc serving tier khi nó ảnh hưởng behavior.

Không giả định model alias bất biến. Alias có thể được cập nhật phía provider mà không cần deploy code ứng dụng.

### 6.2. Generation parameters

Cùng model revision nhưng output có thể khác khi thay đổi:

- Temperature.
- Top-p hoặc top-k.
- Max output tokens.
- Stop sequences.
- Frequency/presence penalty.
- Seed nếu provider hỗ trợ.
- Response format/JSON mode.
- Reasoning effort hoặc model-specific parameters.
- Safety settings và provider-side policy.

Ghi giá trị thực tế gửi tới provider, không chỉ giá trị mặc định trong application.yml. Một số adapter có thể bỏ qua hoặc không hỗ trợ parameter; cần phân biệt requested configuration với effective configuration nếu có thể xác minh.

### 6.3. Provider và runtime

Cùng model ID có thể cho latency hoặc output khác do:

- Provider thay đổi serving stack.
- Gateway hoặc load balancer đổi route.
- Model quantization hoặc hardware tier khác.
- Provider rate limit khiến fallback/retry.
- Timeout hoặc cancellation.
- SDK/API version thay đổi serialization.
- Streaming path và non-streaming path khác nhau.

Ghi SDK version, adapter version, endpoint identity, retry count, timeout, HTTP status và effective route. Không lưu API keys, authorization headers hoặc credentials.

### 6.4. Dấu hiệu model change

Khi input, rendered prompt, RAG context và tool set giống nhau nhưng output khác, hãy kiểm tra:

1. Requested model có đổi không?
2. Reported model có đổi không?
3. Provider/gateway route có đổi không?
4. Generation parameters có giống nhau không?
5. Retry/fallback có xảy ra không?
6. API/SDK version có đổi không?
7. Finish reason, token usage và latency có thay đổi không?

Model không phải nguyên nhân mặc định chỉ vì response khác. Nếu không có bằng chứng về model revision hoặc route, kết luận phải giữ ở mức giả thuyết.

## 7. Nhóm công cụ: kiểm tra cả registry và kết quả thực thi

Tool calling gồm hai giai đoạn quan trọng:

1. Model quyết định có gọi tool nào và tạo arguments.
2. Application resolve, authorize và thực thi tool, rồi gửi result lại cho model.

Model không trực tiếp truy cập API phía sau tool. Application chịu trách nhiệm thực thi và kiểm soát quyền. Vì vậy lỗi có thể nằm ở model selection, tool definition, tool authorization, implementation hoặc external service. Spring AI mô tả tool loop qua ChatClient, ToolCallingAdvisor và ToolCallingManager trong tài liệu Tool Calling.

### 7.1. Tool registry và availability

Ghi:

- Tool names được truyền cho model trong request.
- Tool definitions có hiệu lực sau khi kết hợp defaults và per-call tools.
- Tool type và callback implementation version.
- Tool enable/disable state.
- Resolver/registry version.
- Tool selection policy và risk tier.
- Tenant/user authorization scope.
- Feature flags ảnh hưởng tool availability.

Một tool có thể tồn tại trong application context nhưng không được attach vào request cụ thể. Cần ghi tool set thực tế gửi tới model, không chỉ liệt kê toàn bộ tool beans.

### 7.2. Tool description và schema

Model chọn tool dựa trên tên, mô tả và schema. Những thay đổi nhỏ có thể ảnh hưởng routing:

- Tool name đổi.
- Description đổi từ “tra cứu” thành “tra cứu và cập nhật”.
- Parameter đổi tên hoặc kiểu.
- Required/optional field thay đổi.
- Enum values hoặc validation constraints thay đổi.
- Schema version thay đổi.
- Hai tools có mô tả gần giống nhau xuất hiện cùng lúc.

Ghi toolDefinitionHash, schemaVersion và descriptionVersion. Nếu model bắt đầu gọi nhầm tool sau release, so sánh tool definitions trước và sau.

### 7.3. Tool implementation và external dependency

Cùng tool name/schema vẫn có thể trả kết quả khác do implementation hoặc dependency:

- Business logic thay đổi.
- Database query/filter thay đổi.
- API version thay đổi.
- Permission scope hoặc token claims thay đổi.
- Timeout, retry hoặc circuit breaker khác.
- Cache freshness hoặc cache key thay đổi.
- Response converter hoặc result truncation thay đổi.
- External service trả dữ liệu mới.

Ghi tool implementation version, dependency version, status, duration, retry count, error category và sanitized result reference.

### 7.4. Tool output có thể là nguyên nhân downstream

Nếu tool trả dữ liệu sai hoặc thiếu, model có thể tạo câu trả lời sai dù prompt và model không đổi. Khi điều tra, cần đọc theo chuỗi:

~~~mermaid
sequenceDiagram
    participant M as Chat model
    participant A as Spring AI application
    participant T as Tool service
    participant M2 as Chat model

    M->>A: Tool call name + arguments
    A->>A: Resolve and authorize callback
    A->>T: Execute tool
    T-->>A: Result / error
    A->>A: Validate and convert result
    A->>M2: Append tool result to conversation
    M2-->>A: Final answer
~~~

So sánh tool call name, arguments đã redaction, tool result reference, status và version. Đừng chỉ nhìn final answer rồi quy lỗi cho model.

## 8. Runtime và môi trường cũng cần được ghi nhận

Bốn nhóm chính chưa bao phủ mọi thay đổi. Những yếu tố sau có thể làm output hoặc quality khác:

- Application build, dependency lock và Java runtime.
- Spring AI, Spring Boot và SDK versions.
- Feature flags và environment variables.
- HTTP proxy, gateway, DNS và network route.
- Rate limit, quota, retry và timeout.
- Database/index availability.
- Cache state và consistency.
- Clock, locale, timezone và regional settings.
- Safety filters, moderation policy và tenant configuration.

Ghi release ID, config snapshot version, dependency version và effective flags. Không dump toàn bộ environment variables vì có thể chứa secrets.

## 9. Run manifest: bản ghi cấu hình của một interaction

Một cách hiệu quả để phân biệt nguyên nhân là tạo một manifest cho mỗi interaction hoặc assistant turn. Manifest lưu version/reference của các thành phần đã tham gia tạo output.

~~~json
{
  "interaction": {
    "interactionId": "int-7f4b",
    "assistantTurnId": "turn-03",
    "conversationRef": "conv-opaque",
    "startedAt": "2026-11-27T12:00:00Z"
  },
  "data": {
    "inputHash": "sha256:input-example",
    "historySnapshotVersion": "history-v5",
    "memoryVersion": "memory-v8",
    "corpusVersion": "kb-2026-11-27",
    "indexVersion": "index-v14",
    "retrievalResultHash": "sha256:retrieval-example"
  },
  "prompt": {
    "templateId": "support-answer",
    "version": "v18",
    "rendererVersion": "3",
    "advisorChainVersion": "chain-v6",
    "renderedPromptHash": "sha256:prompt-example"
  },
  "model": {
    "provider": "provider-a",
    "requestedModel": "chat-alias",
    "reportedModel": "chat-revision-42",
    "parameterSetVersion": "generation-v4",
    "sdkVersion": "adapter-2.1"
  },
  "tools": {
    "registryVersion": "tools-v12",
    "definitionsHash": "sha256:tools-example",
    "executions": [
      {
        "name": "lookupOrder",
        "implementationVersion": "4",
        "schemaVersion": "2",
        "status": "SUCCESS"
      }
    ]
  },
  "runtime": {
    "applicationBuild": "2026.11.27.3",
    "featureFlagSet": "flags-v9",
    "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
  }
}
~~~

Các ID, versions và hashes đều là dữ liệu minh họa. Một manifest production nên có schema version, provenance, timestamp và secure references. Không đưa raw prompt, customer records, secrets hoặc tool arguments vào manifest chỉ để dễ debug.

### 9.1. Manifest phải ghi effective configuration

Có khác biệt giữa cấu hình mong muốn và cấu hình thực sự được dùng:

| Requested | Effective evidence |
| --- | --- |
| Model alias | Reported model, gateway route hoặc deployment revision |
| Temperature mặc định | Parameter thực tế gửi tới provider |
| Prompt template version | Rendered prompt hash/reference |
| Tool registry version | Tool names/definitions thực tế trong request |
| Retriever version | Index, filter, chunk IDs thực tế trả về |
| Feature flag config | Flags đã evaluate cho interaction |
| Tool implementation version | Callback build và dependency thực tế |

Nếu provider không trả reported model hoặc revision, ghi rõ UNKNOWN/NOT_REPORTED. Không suy ra version từ alias hoặc timestamp.

### 9.2. Manifest bất biến

Không cập nhật manifest cũ để phản ánh config hiện tại. Nếu phát hiện thiếu metadata, tạo enrichment record có timestamp và provenance riêng. Manifest phải mô tả execution tại thời điểm ban đầu.

## 10. Attribution matrix: tìm thành phần thay đổi đầu tiên

Khi một interaction regression được xác nhận, so manifest của lần tốt và lần lỗi:

| Thành phần | Lần tốt | Lần lỗi | Khác biệt? | Bằng chứng tiếp theo |
| --- | --- | --- | --- | --- |
| Input/history | hash A | hash A | Không | Giữ cố định |
| RAG context | chunks 1,2,3 | chunks 1,4,5 | Có | Replay retrieval |
| Rendered prompt | hash P1 | hash P2 | Có | Diff prompt |
| Model revision | rev 41 | rev 41 | Không | Giữ cố định |
| Tool definitions | schema 2 | schema 3 | Có | Replay tool selection |
| Tool result | status success | status success, payload khác | Có thể | So data source/version |
| Runtime | build 10 | build 11 | Có | Kiểm tra dependency/config |

Đừng chọn nguyên nhân chỉ bằng cách tìm dòng đầu tiên khác nhau. Một thay đổi có thể không ảnh hưởng output, trong khi một thành phần khác mới là nguyên nhân thực. Hãy kiểm tra bằng replay hoặc experiment.

### 10.1. Phân loại evidence

- **Observed change:** manifest hoặc trace chứng minh một giá trị khác.
- **Plausible cause:** thay đổi có cơ chế hợp lý để ảnh hưởng kết quả.
- **Validated cause:** controlled replay/experiment cho thấy thay đổi đó tái tạo hoặc loại bỏ regression.
- **Unresolved:** thiếu snapshot, không thể replay hoặc có nhiều thay đổi tương tác.

Báo cáo incident nên ghi mức độ evidence. Tránh khẳng định nguyên nhân chắc chắn khi chỉ có tương quan thời gian.

## 11. Quy trình điều tra khi chất lượng giảm

~~~mermaid
flowchart TD
    REG["Quality regression detected"] --> CASE["Select affected interactions"]
    CASE --> MANIFEST["Compare run manifests"]
    MANIFEST --> DATA{"Data/context changed?"}
    DATA -->|Yes| DATAREPLAY["Replay with frozen data"]
    DATA -->|No| PROMPT{"Rendered prompt changed?"}
    PROMPT -->|Yes| PROMPTREPLAY["Replay prompt variants"]
    PROMPT -->|No| MODEL{"Model/provider/parameters changed?"}
    MODEL -->|Yes| MODELREPLAY["Compare model revisions"]
    MODEL -->|No| TOOL{"Tool set/schema/result changed?"}
    TOOL -->|Yes| TOOLREPLAY["Replay tool definitions/results"]
    TOOL -->|No| RUNTIME["Inspect runtime, network and dependencies"]
    DATAREPLAY --> EVAL["Run same evaluator and rubric"]
    PROMPTREPLAY --> EVAL
    MODELREPLAY --> EVAL
    TOOLREPLAY --> EVAL
    RUNTIME --> EVAL
    EVAL --> CAUSE["Record evidence and confidence"]
~~~

Các bước:

1. Xác định regression bằng evaluator/human review và chọn các interactions bị ảnh hưởng.
2. Chọn một số case đại diện và case đối chứng đã có quality tốt.
3. Tải run manifests, trace references và evidence snapshots.
4. So sánh data, prompt, model, tools và runtime theo từng phiên bản.
5. Kiểm tra thay đổi nào có mặt trong cohort lỗi nhưng không có ở cohort đối chứng.
6. Replay trên cùng data snapshot và evaluator/rubric version.
7. Thay một yếu tố mỗi lần để kiểm tra giả thuyết ban đầu.
8. Nếu có tương tác, chạy factorial hoặc pairwise experiment.
9. Xác nhận bằng human review khi evaluator không đủ tin cậy.
10. Ghi root cause, contributing factors, mitigation và regression test.

## 12. Replay: giữ cố định dữ liệu để so sánh prompt/model/tool

Replay là cách chạy lại một interaction cũ trong môi trường có kiểm soát. Mục tiêu là thay đổi đúng yếu tố cần kiểm tra.

### 12.1. Frozen input và context

Một replay case nên cố định:

- User input và message roles.
- Conversation history hoặc memory snapshot.
- RAG document/chunk versions và thứ tự context.
- Tool definitions và sanitized tool result fixtures.
- Output schema và evaluator rubric.
- Locale, timezone và các context variables liên quan.

Nếu retrieval index hiện tại khác index cũ, replay bằng cách truy vấn index hiện tại không phải replay chính xác. Cần dùng stored retrieval evidence hoặc snapshot index.

### 12.2. Frozen tool results

Tool thường đọc hoặc ghi dữ liệu bên ngoài. Khi replay:

- Dùng fixture đã redaction cho tool results.
- Mock hoặc record/replay response của downstream service.
- Không thực hiện lại payment, email, delete hoặc update side effect.
- Giữ nguyên tool result order và status nếu đang cô lập prompt/model.
- Tạo test sandbox nếu cần kiểm tra implementation mới.

Nếu muốn kiểm tra tool implementation mới, thay tool execution trong sandbox nhưng giữ input và contract fixture cố định.

### 12.3. Replay không phải lúc nào cũng deterministic

Ngay cả cùng prompt và model, output có thể khác do sampling, provider-side revision, hidden system changes hoặc nondeterministic serving. Nếu provider hỗ trợ seed, ghi seed nhưng vẫn không giả định kết quả hoàn toàn giống nhau.

Chạy nhiều lần cho cùng condition khi cần ước lượng variance. So sánh distributions hoặc evaluator scores, không chỉ so exact string.

## 13. Controlled experiments: thay một yếu tố có chủ đích

### 13.1. One-factor-at-a-time

Khi muốn kiểm tra prompt mới, giữ data, model và tool definitions cố định, chỉ thay prompt. Khi muốn kiểm tra model revision, giữ prompt và data cố định.

Ưu điểm:

- Dễ hiểu và dễ giải thích.
- Phù hợp kiểm tra một giả thuyết cụ thể.
- Dễ xây regression test.

Giới hạn: nếu có tương tác giữa prompt và model, thử từng yếu tố riêng có thể bỏ sót ảnh hưởng kết hợp.

### 13.2. Pairwise comparison

Chọn hai điều kiện khác nhau ở một thành phần:

| Run | Data | Prompt | Model | Tools |
| --- | --- | --- | --- | --- |
| A | D1 | P1 | M1 | T1 |
| B | D1 | P2 | M1 | T1 |

Nếu A và B dùng cùng data/model/tools, khác biệt quality có thể quy cho prompt trong phạm vi thử nghiệm đó.

Tương tự, so M1 với M2 hoặc T1 với T2 trong khi giữ các yếu tố khác cố định.

### 13.3. Factorial experiment

Khi nghi ngờ prompt và model tương tác, có thể chạy thiết kế 2×2:

| Run | Prompt | Model |
| --- | --- | --- |
| A | P1 | M1 |
| B | P2 | M1 |
| C | P1 | M2 |
| D | P2 | M2 |

Thiết kế này cho biết:

- Hiệu ứng chính của prompt.
- Hiệu ứng chính của model.
- Tương tác giữa prompt và model.

Nếu P2 cải thiện trên M1 nhưng làm giảm quality trên M2, không thể kết luận P2 luôn tốt hơn. Cần chọn cấu hình theo workload/cohort hoặc thiết kế prompt phù hợp từng model.

### 13.4. Randomization và sample design

Nếu thử nghiệm trên traffic thật:

- Randomize assignment theo interaction hoặc user/session tùy mục tiêu.
- Giữ assignment ổn định trong một conversation nếu history phụ thuộc model/prompt trước đó.
- Phân tầng theo task family, language và RAG/tool usage.
- Chạy cùng evaluator/rubric version.
- Ghi inclusion probability và exposure.
- Báo confidence interval, sample count và guardrail metrics.
- Không chỉ chọn những request đã có feedback để đánh giá candidate.

Với tool có side effects, chỉ chạy experiment trên môi trường an toàn hoặc dùng tool fixtures. Không để hai arm thực hiện cùng một hành động thật.

## 14. Đọc trace để phân biệt các tầng thay đổi

Trace giúp xem execution path và thời gian của từng operation. OpenTelemetry span có name, parent relationship, timestamps, attributes, events, links và status. Một trace có thể cho biết:

- ChatClient call/stream kéo dài bao lâu.
- Advisor nào được chạy và theo thứ tự nào.
- ChatModel request dùng provider/model nào.
- Tool nào được gọi và thời gian thực thi.
- HTTP call tới gateway hoặc external service có lỗi/timeout không.
- Một async operation có liên kết causal với interaction ban đầu không.

Trace không tự chứa đầy đủ prompt, completion hoặc business data. Cần kết hợp với run manifest và evidence store.

### 14.1. Spring AI observations hữu ích

Theo Spring AI 2.1.0 Observability reference:

| Observation | Dữ liệu có ích |
| --- | --- |
| ChatClient | Call/stream, advisors, conversation ID, tool names |
| Advisor | Advisor name và order |
| ChatModel | `gen_ai.request.model`, `gen_ai.response.model`, sampling parameters, finish reason, token usage |
| Tool | `spring.ai.tool.definition.name`, tool type, call ID, duration và tracing context |
| EmbeddingModel | Embedding operation và provider/model context |
| VectorStore | Vector store operations và timing |

Spring AI phân biệt low-cardinality keys và high-cardinality keys. Low-cardinality keys có thể xuất hiện trong metrics và traces; high-cardinality keys chỉ xuất hiện trong traces. Không dùng unique interaction IDs, raw prompt hoặc tool arguments làm metric tags.

Với tool calling, các thuộc tính arguments và result chỉ được thêm vào span khi bật cấu hình tương ứng. Giữ mặc định tắt trong production nếu chưa có nhu cầu điều tra cụ thể và biện pháp bảo vệ dữ liệu phù hợp.

### 14.2. Prompt và tool content không được export mặc định

Prompt/completion có thể lớn và chứa dữ liệu nhạy cảm nên Spring AI không export chúng mặc định. Tool arguments và results cũng không được export mặc định. Các property bật nội dung quan sát cần được cân nhắc kỹ, chỉ dùng trong môi trường và phạm vi đã kiểm soát.

Để điều tra nội dung, ưu tiên lưu secure evidence reference và dùng reviewer UI có authorization, audit và retention. Trace nên tập trung vào operation metadata.

### 14.3. Correlation giữa application manifest và trace

Tạo interactionId ở application layer và lưu cùng traceId/span references. TraceId dùng để mở execution trace; interactionId dùng để tìm manifest và evaluation case. Không dùng traceId làm metric label vì cardinality cao.

Nếu evaluation worker chạy bất đồng bộ, có thể dùng trace link hoặc event correlation để nối job với interaction ban đầu. Không giả định consumer span luôn nằm trong cùng trace nếu hệ thống tạo trace mới.

## 15. Ví dụ Spring AI: ghi manifest ở application layer

Ví dụ dưới đây minh họa schema cho một interaction. Các version được inject từ configuration hoặc release metadata; chúng không được tự suy ra từ tên class.

~~~java
public record ComponentManifest(
        String dataSnapshotVersion,
        String promptTemplateVersion,
        String promptRendererVersion,
        String provider,
        String requestedModel,
        String modelParameterSetVersion,
        String toolRegistryVersion,
        String applicationBuild) {
}

public record InteractionManifest(
        String interactionId,
        String assistantTurnId,
        String traceId,
        ComponentManifest components,
        String inputHash,
        String renderedPromptHash,
        String retrievalEvidenceRef,
        String toolExecutionSummaryRef,
        java.time.Instant capturedAt) {
}
~~~

Tạo manifest trong application service tại thời điểm xử lý:

~~~java
@Service
public class SupportAssistant {

    private final ChatClient chatClient;
    private final ManifestRepository manifests;
    private final ManifestFactory manifestFactory;

    public SupportAssistant(
            ChatClient.Builder builder,
            ManifestRepository manifests,
            ManifestFactory manifestFactory) {
        this.chatClient = builder.build();
        this.manifests = manifests;
        this.manifestFactory = manifestFactory;
    }

    public String answer(SupportRequest request) {
        InteractionContext context = InteractionContext.start(request);

        ChatResponse response = chatClient.prompt()
                .system("Trả lời dựa trên chính sách và evidence được cung cấp.")
                .user(request.question())
                .call()
                .chatResponse();

        String answer = response.getResult().getOutput().getText();

        InteractionManifest manifest =
                manifestFactory.capture(context, request, response);

        manifests.save(manifest);
        return answer;
    }
}
~~~

Đây là skeleton minh họa; **InteractionContext**, **ManifestFactory** và repository là kiểu do ứng dụng định nghĩa. Với streaming, cần lưu manifest sau khi stream hoàn tất hoặc bị cancel, đồng thời ghi completion status. Nếu cần traceId, đọc từ tracing context trong đúng execution context và lưu rõ khi unavailable.

### 15.1. Version hóa tool definition

Một tool có thể được khai báo như sau:

~~~java
@Component
public class OrderTools {

    private final OrderService orders;

    public OrderTools(OrderService orders) {
        this.orders = orders;
    }

    @Tool(
        name = "lookupOrder",
        description = "Tra cứu trạng thái đơn hàng theo mã đơn"
    )
    public OrderSummary lookupOrder(
            @ToolParam(description = "Mã đơn hàng") String orderId) {
        return orders.lookup(orderId);
    }
}
~~~

Khi thay description, parameter schema hoặc logic của tool, cập nhật version tương ứng. Không chỉ dựa vào Java class name vì implementation có thể thay đổi mà tên class giữ nguyên.

### 15.2. Lưu requested và reported model

ChatModel response metadata có thể cung cấp model và usage information tùy provider. Lưu requested model từ request config và reported model từ response metadata khi có. Nếu provider không trả revision, ghi trạng thái chưa được báo cáo thay vì điền alias làm reported model.

## 16. Diagnostic examples

### 16.1. Câu trả lời sai sau khi cập nhật corpus

Triệu chứng: relevance vẫn cao nhưng fact-check giảm.

Manifest cho thấy:

- Prompt version không đổi.
- Model revision không đổi.
- Tool set không đổi.
- Index version đổi.
- Retrieved chunk IDs và document versions khác.

Giả thuyết: evidence mới thiếu hoặc mâu thuẫn. Hành động:

1. Replay cùng query với retrieval evidence cũ và mới.
2. Chạy fact-check cùng rubric version.
3. So document freshness, rank, filters và chunk content hash.
4. Kiểm tra ingestion/index build.
5. Rollback index hoặc sửa retrieval config nếu regression được xác nhận.

### 16.2. Model bắt đầu gọi nhầm tool

Triệu chứng: tool error tăng sau release prompt.

Manifest cho thấy:

- Data và model revision không đổi.
- Prompt version thay đổi.
- Tool definitions giữ nguyên.
- Tool names được cung cấp giống nhau.
- Tool selection distribution thay đổi.

Hành động:

1. Diff rendered prompt và system instruction.
2. Replay trên cùng input và tool result fixtures.
3. Kiểm tra prompt mới có chỉ dẫn mơ hồ về tool routing không.
4. Human review các tool calls sai.
5. Sửa prompt và thêm test case để ngăn regression.

Nếu tool description/schema cũng đổi, cần chạy thêm pairwise test để tách ảnh hưởng.

### 16.3. Câu trả lời ngắn và thiếu bước sau khi model upgrade

Triệu chứng: output token count và completion length giảm, INCOMPLETE tăng.

Manifest cho thấy:

- Data và rendered prompt hash giống nhau.
- Model reported revision thay đổi.
- Max output tokens không đổi.
- Tool set không đổi.

Hành động:

1. Replay cùng dataset trên model revision cũ và mới.
2. Chạy nhiều lần nếu generation có variance.
3. So finish reasons, token usage và evaluator results.
4. Kiểm tra provider-side model notes hoặc routing changes.
5. Canary model cũ/mới theo task family trước khi quyết định.

Không kết luận model mới kém chỉ từ response ngắn hơn; cần kiểm tra completeness và factuality.

### 16.4. Tool result khác dù model và prompt giữ nguyên

Triệu chứng: model tạo câu trả lời sai về trạng thái đơn hàng.

Trace cho thấy tool call thành công, nhưng tool result reference trỏ tới data source revision mới.

Hành động:

1. So query/filter và authorization scope.
2. So business record revision và cache freshness.
3. Replay model với tool result fixture cũ và mới.
4. Kiểm tra API contract và result converter.
5. Sửa data/tool layer nếu kết quả mới không đúng nghiệp vụ.

### 16.5. Cả prompt và model cùng đổi

Không thể quy kết bằng so sánh trước/sau đơn giản. Dùng factorial design P1/M1, P2/M1, P1/M2 và P2/M2 trên cùng frozen dataset. Nếu chỉ tổ hợp P2/M2 suy giảm, có thể tồn tại interaction effect; cần ghi kết luận đúng phạm vi thay vì gán toàn bộ lỗi cho prompt hoặc model riêng lẻ.

## 17. Metrics để phát hiện thay đổi theo thành phần

Các metric sau là ví dụ do ứng dụng tự định nghĩa, không phải metric mặc định Spring AI:

| Metric | Mục đích |
| --- | --- |
| ai_interaction_component_change_total | Đếm interaction có component version khác baseline |
| ai_data_snapshot_version_total | Traffic theo data snapshot |
| ai_prompt_version_total | Traffic theo prompt version |
| ai_model_revision_total | Traffic theo reported model/revision |
| ai_tool_registry_version_total | Traffic theo tool registry version |
| ai_tool_schema_change_total | Số interaction dùng tool schema mới |
| ai_tool_execution_total | Tổng số tool executions đủ điều kiện |
| ai_quality_relevance_pass_total | Relevance pass outcomes |
| ai_quality_evaluated_total | Tổng số cases đã có relevance evaluation |
| ai_quality_factcheck_fail_total | Fact-check failures |
| ai_tool_execution_failure_total | Tool execution failures |
| ai_interaction_manifest_missing_total | Interaction thiếu manifest/effective config |

Chỉ dùng labels có cardinality hữu hạn, đã kiểm soát như component family, release cohort, provider, model family hoặc version đang rollout. Nếu prompt version hoặc tool schema version có số lượng lớn, lưu chi tiết trong manifest store và dùng dashboard filter/exemplars để drill down. Không dùng interactionId, traceId, raw prompt, user ID hoặc tool arguments làm metric labels.

### 17.1. Theo dõi phân bố theo model revision

~~~promql
sum by (provider, model_family, reported_revision) (
  rate(ai_model_revision_total[1h])
)
~~~

Chỉ dùng reported_revision làm label nếu số revision hữu hạn và được kiểm soát trong thời gian rollout. Với revision động hoặc cardinality lớn, aggregate ở event analytics thay vì Prometheus.

### 17.2. Theo dõi tool failures

~~~promql
sum by (tool_name, tool_version) (
  rate(ai_tool_execution_failure_total[15m])
)
/
sum by (tool_name, tool_version) (
  rate(ai_tool_execution_total[15m])
)
~~~

Mẫu số cần được instrument cho mọi tool executions đủ điều kiện. Nếu không có execution nào trong cửa sổ, hiển thị không đủ dữ liệu thay vì 0% failure.

### 17.3. Theo dõi quality theo prompt version

~~~promql
sum by (prompt_family, prompt_version) (
  rate(ai_quality_relevance_pass_total[1h])
)
/
sum by (prompt_family, prompt_version) (
  rate(ai_quality_evaluated_total[1h])
)
~~~

So sánh chỉ có ý nghĩa khi cùng evaluator/rubric version, cohort mix và label maturity. Nếu sample probabilities khác nhau, cần weighted estimate ở analytics layer.

## 18. Release ledger và change timeline

Mỗi lần thay đổi production nên tạo release record có:

- Change ID và thời gian deploy.
- Component family: data, prompt, model, tool hoặc runtime.
- Previous version và candidate version.
- Owner và lý do thay đổi.
- Affected cohorts.
- Evaluation dataset và results.
- Canary exposure và guardrail outcome.
- Rollback reference.

Một timeline rõ ràng giúp đối chiếu quality regression với release. Tuy nhiên, thay đổi xảy ra cùng thời điểm chưa đủ chứng minh quan hệ nhân quả. Vẫn cần replay hoặc controlled experiment.

### 18.1. Một release có thể chứa nhiều component changes

Nếu một release cùng lúc đổi prompt, model và tool schema, sau đó quality giảm thì attribution khó. Khi có thể, chia rollout thành các thay đổi độc lập hoặc giữ snapshot đủ chi tiết để chạy factorial replay. Với thay đổi bắt buộc phải đi cùng nhau, đánh giá tổ hợp như một candidate pipeline.

### 18.2. Shadow và canary

- **Shadow:** chạy candidate trên input đã chọn, không trả candidate output cho user; dùng để so sánh behavior và quality.
- **Canary:** route một phần traffic thật tới candidate; đo quality, latency, cost và operational failures.
- **Replay:** chạy lại dataset cố định; phù hợp cô lập data/prompt/model/tool.
- **Rollback:** quay lại version ổn định nếu guardrail bị vi phạm.

Với tool có side effects, shadow/replay phải mock hoặc dùng sandbox. Không gửi lại hành động thật chỉ để đo khác biệt.

## 19. Checklist kiểm thử attribution

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Cùng input, đổi RAG corpus | Manifest cho thấy corpus/index và retrieved chunks khác |
| Cùng template, đổi prompt variable | Rendered prompt hash khác |
| Cùng prompt, model alias route sang revision mới | Requested và reported model được phân biệt |
| Model fallback sau timeout | Fallback model/route và retry được ghi |
| Tool description thay đổi | Tool definition hash/version khác |
| Tool schema đổi optional thành required | Tool arguments validation có thể thay đổi và được kiểm tra |
| Tool implementation đổi nhưng schema giữ nguyên | Implementation version khác trong manifest |
| Tool result thay đổi do business data | Result reference/revision khác |
| Hai component cùng thay đổi | Controlled replay hoặc factorial test tách được hiệu ứng |
| Prompt content nhạy cảm | Trace không export raw prompt mặc định |
| Tool arguments chứa PII | Không bật export content toàn cục |
| Interaction stream bị cancel | Manifest ghi completion/cancel status |
| Provider không báo model revision | Reported revision có trạng thái UNKNOWN/NOT_REPORTED |
| Manifest thiếu field | Dashboard ghi missing metadata và không kết luận quá mức |
| Replay tool có side effect | Dùng fixture/sandbox, không thực thi hành động thật |

## 20. Quy trình triển khai từng bước

1. Xác định các component có thể làm thay đổi output trong pipeline.
2. Tạo immutable versions cho data snapshot, prompt, model config, tool registry/schema và runtime.
3. Tạo interactionId và run manifest ở application layer.
4. Ghi requested/effective values cùng trạng thái metadata unavailable.
5. Nối manifest với Spring AI observations và trace references.
6. Lưu RAG evidence, tool execution summary và output references có quyền truy cập.
7. Xây dashboard component rollout và quality outcomes.
8. Khi regression xuất hiện, chọn affected interactions và controls.
9. So manifest và trace để lập danh sách giả thuyết.
10. Replay từng component với data/context cố định.
11. Dùng factorial design nếu có tương tác.
12. Human-review các case evaluator không chắc chắn.
13. Ghi root cause và contributing factors trong release/incident ledger.
14. Thêm regression cases vào evaluation dataset.
15. Canary hoặc rollback theo guardrail đã xác định.

## 21. Bài tập thực hành

### Bài 1. Phân biệt data và prompt change

Tạo một query RAG và lưu input hash, retrieved chunk IDs, prompt template version và rendered prompt hash. Thay một document nhưng giữ prompt; sau đó thay prompt variable nhưng giữ document. Xác định manifest fields nào thay đổi trong từng trường hợp.

### Bài 2. Phân biệt model alias và revision

Gửi cùng request qua hai model deployments. Ghi requested model, reported model, provider, generation parameters, finish reason, token usage và latency. Xác định metadata nào không được provider trả về.

### Bài 3. Kiểm tra tool description và schema

Tạo hai phiên bản tool description hoặc JSON schema. Replay cùng input và cùng model trên tool fixtures. So tool selection, arguments validity và final answer.

### Bài 4. Tool implementation và data source

Giữ tool name/schema cố định nhưng thay implementation hoặc fixture result. Kiểm tra final response có thay đổi theo tool result hay không. Ghi status, duration và result reference.

### Bài 5. One-factor-at-a-time

Tạo một case relevance regression. Chạy baseline và candidate với chỉ một thành phần thay đổi mỗi lần. Lưu evaluator/rubric version và so sánh kết quả.

### Bài 6. Factorial prompt/model

Chạy ma trận P1/M1, P2/M1, P1/M2, P2/M2 trên cùng dataset. Tính main effects và interaction effect; giải thích vì sao prompt mới có thể tốt với model này nhưng xấu với model khác.

### Bài 7. Trace investigation

Mở trace của một tool calling interaction. Đối chiếu ChatClient, ChatModel và tool observations với manifest. Xác định tầng nào chậm hoặc lỗi. Kiểm tra trace không chứa raw prompt/tool arguments ngoài chính sách.

### Bài 8. Root cause report

Tạo incident giả lập khi quality giảm sau một release gồm nhiều thay đổi. Viết report gồm observed changes, hypotheses, replay evidence, validated cause, contributing factors, mitigation và regression tests.

## 22. Tổng kết

Để phân biệt thay đổi dữ liệu, prompt, mô hình và công cụ, cần biết chính xác mỗi interaction đã chạy với cấu hình nào:

- Data bao gồm input, history, memory, RAG corpus, retrieved evidence và business state.
- Prompt bao gồm template, rendered variables, advisor chain, memory policy và output schema.
- Model bao gồm provider, requested/reported model, revision, parameters, routing và fallback.
- Tools bao gồm registry, tool names, descriptions, schema, authorization, implementation, dependency và execution result.
- Runtime/environment cũng cần version hóa để tránh quy nhầm nguyên nhân.
- Run manifest bất biến giúp so sánh lần chạy tốt và lỗi.
- Replay trên frozen data/context giúp cô lập từng yếu tố; factorial design giúp nhận ra tương tác.
- Spring AI observations và OpenTelemetry traces cho biết execution path, nhưng không thay thế manifest/evidence store.
- Prompt/completion và tool arguments/results không nên export toàn cục; cần bảo vệ nội dung nhạy cảm.
- Chỉ kết luận root cause khi có evidence đủ mạnh; nếu thiếu snapshot hoặc không thể replay, ghi rõ unresolved.

Khi mỗi thay đổi được ghi version, mỗi interaction có manifest và mỗi regression có thể replay, nhóm phát triển có thể xác định thành phần gây ảnh hưởng, đánh giá candidate một cách công bằng và ngăn lỗi quay lại trong các phiên bản sau.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): ChatClient, Advisor, ChatModel và tool observations; low/high cardinality; model parameters, finish reasons, token usage và mặc định không export prompt/completion.
- [Spring AI 2.1.0 Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): tool loop, ToolCallingAdvisor, ToolCallingManager, tool definitions, callbacks và application-owned execution.
- [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/): spans, parent relationships, attributes, events, links và status.
- [OpenTelemetry — Trace Data Model](https://opentelemetry.io/docs/specs/otel/trace/data-model/): cấu trúc span và quan hệ giữa span attributes, events, links, status.
