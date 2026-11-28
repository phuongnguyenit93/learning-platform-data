# Đặt tên span và thuộc tính có giá trị chẩn đoán

Một trace có thể chứa đầy đủ các spans mà vẫn khó điều tra nếu chúng mang tên chung chung như `process`, `request` hoặc `callModel`, không có metadata về phiên bản prompt, model, retriever, tool và outcome. Ngược lại, nếu tên span chứa nguyên văn câu hỏi, user ID hoặc mã đơn hàng, trace trở nên khó tổng hợp, tốn chi phí lưu trữ và có thể làm lộ dữ liệu nhạy cảm. Thiết kế tốt cần trả lời được hai câu hỏi: **span đang đo operation nào?** và **những thuộc tính nào giúp giải thích điều gì đã xảy ra?**

Bài học thuộc chương **Thiết kế trace** của module `SPRING_AI_EVALUATION_OBSERVABILITY`. Module này giúp đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance/fact checking, kiểm thử RAG/tool calling, đồng thời theo dõi metrics, traces, chi phí và độ trễ qua các phiên bản prompt, model và pipeline. Vì vậy, quy ước span ở đây cần phục vụ cả chẩn đoán vận hành lẫn phân tích evaluation.

Sau bài học, bạn có thể:

- Đặt tên span ổn định, mô tả operation và không chứa dữ liệu theo từng request.
- Chọn attributes có ích cho HTTP, retrieval, embedding, vector store, reranker, model, tool và judge.
- Phân biệt resource attributes, span attributes, events, logs và metrics.
- Thiết kế low-cardinality metric dimensions và high-cardinality trace details đúng chỗ.
- Dùng Micrometer Observation trong Spring Boot/Spring AI để ghi metadata theo allowlist.
- Phân tích trace theo prompt/model/index/rubric version mà không làm lẫn lỗi kỹ thuật với câu trả lời sai.

## 1. Span name trả lời “đang làm gì?”

**Tên span** mô tả một operation có thời gian bắt đầu/kết thúc. Nó nên cho người xem trace biết công việc đang được thực hiện, không phải toàn bộ dữ liệu đầu vào hoặc kết quả của công việc.

Một tên tốt:

- Ổn định giữa các request và các lần chạy cùng loại operation.
- Dùng từ ngữ thể hiện hành động hoặc ranh giới công việc.
- Đủ cụ thể để phân biệt retrieval, rerank, generation, tool execution và evaluation.
- Không nhúng ID, câu hỏi, document title, URL có query, exception message hay nội dung người dùng.
- Không thay đổi theo prompt variant, tenant, case ID hoặc model alias nếu mục tiêu là cùng một loại operation.

Ví dụ:

| Không nên | Nên dùng | Lý do |
|---|---|---|
| `process` | `app.ai.answer` | Biết đây là operation trả lời |
| `call-12345` | `app.ai.model.generate` | Không tạo tên riêng cho từng request |
| `search-policy-tenant-A` | `app.rag.vector.search` | Không nhúng tenant vào tên |
| `ask-How-do-I-return` | `app.rag.query.rewrite` | Không đưa raw question vào span name |
| `tool-DH-001` | `app.ai.tool.execute` | Không đưa mã đơn vào tên |
| `judge-prompt-B-rag-017` | `app.ai.evaluation.case` | Giữ tên ổn định, đưa version/case vào metadata phù hợp |

### 1.1. Đặt tên theo operation, không theo implementation detail

Nếu code thay từ PostgreSQL sang một vector database khác nhưng operation nghiệp vụ vẫn là “tìm bằng chứng”, tên span nghiệp vụ `app.rag.retrieve` có thể giữ nguyên. Span con của data client sẽ thể hiện implementation cụ thể như PostgreSQL/HTTP/gRPC.

Tách hai lớp:

```text
app.rag.retrieve                     [business operation]
└── CLIENT POST /collections/search  [transport operation]

app.rag.retrieve                     [business operation]
└── DB CLIENT SELECT policy_chunks   [database operation]
```

Không dùng `app.rag.pgvector.retrieve` nếu muốn giữ một dashboard so sánh cùng operation qua các backend. Backend có thể được biểu diễn bằng attribute `app.rag.store.type` hoặc resource/service metadata phù hợp.

### 1.2. Không đưa dữ liệu động vào tên

Một span name như `answer.case-001.variant-B` khiến mỗi case/variant tạo một tên khác nhau. Điều đó làm trace query, dashboard và thống kê khó quản lý. Hãy dùng:

```text
span.name = app.ai.answer
attributes:
  app.ai.prompt.version = prompt-B
  app.ai.evaluation.case_id = rag-001
```

Các thuộc tính động vẫn phải qua chính sách cardinality và bảo mật. `case_id` có thể hữu ích khi tra một trace cụ thể, nhưng không nên biến thành label của metric.

## 2. Quy ước đặt tên cho ứng dụng Spring AI

Nên có namespace riêng cho operation do ứng dụng định nghĩa, ví dụ `app.ai.` và `app.rag.`. Tên dưới đây là **quy ước đề xuất**, không phải tên mặc định được Spring AI cam kết phát ra:

| Operation | Span name gợi ý | Phạm vi đo |
|---|---|---|
| Trả lời nghiệp vụ | `app.ai.answer` | Toàn bộ luồng tạo answer |
| ChatClient request | Observation/framework span hiện có hoặc `app.ai.chatclient.call` | Chuỗi advisor và xử lý chat |
| Viết lại câu hỏi | `app.rag.query.rewrite` | Chuẩn hóa query trước retrieval |
| Tạo query embedding | `app.rag.query.embed` | Một lần embedding query thực tế |
| Retrieval tổng | `app.rag.retrieve` | Tìm kiếm và chuẩn hóa candidates |
| Vector search | `app.rag.vector.search` | Một operation truy vấn vector store |
| Keyword search | `app.rag.keyword.search` | Một operation tìm kiếm từ khóa |
| Hợp nhất kết quả | `app.rag.results.merge` | Deduplicate/fusion nhiều nguồn |
| Reranking | `app.rag.rerank` | Sắp xếp lại candidates |
| Dựng context | `app.rag.context.build` | Chọn và lắp ghép evidence |
| Kiểm tra citation | `app.rag.citation.validate` | Xác minh source references |
| Model generation | `app.ai.model.generate` | Một lượt gọi model logic |
| Tool dispatch | `app.ai.tool.dispatch` | Chọn và kiểm tra tool |
| Tool execution | `app.ai.tool.execute` | Thực thi callback/tool |
| Evaluation run | `app.ai.evaluation.run` | Một run đánh giá |
| Evaluation case | `app.ai.evaluation.case` | Chấm một case |
| Judge model call | `app.ai.judge.generate` | Một lượt gọi model judge |
| Lưu kết quả | `app.ai.evaluation.persist` | Ghi verdict/artifact |

### 2.1. Không nhân đôi spans framework

Spring Boot, Micrometer, Spring AI, HTTP clients, JDBC drivers hoặc OpenTelemetry Java agent có thể đã tạo observations/spans cho một số thao tác. Trước khi thêm span thủ công:

1. Chạy một request đại diện với tracing được bật.
2. Mở trace và xác định các spans đã tồn tại.
3. Kiểm tra tên, parent, duration và attributes.
4. Chỉ thêm span nghiệp vụ khi cần một ranh giới chưa có hoặc cần tổng hợp nhiều bước.
5. Không bọc lại đúng một HTTP/SQL/model request bằng một span khác cùng ý nghĩa chỉ để tăng số lượng spans.

Ví dụ, nếu JDBC instrumentation đã tạo span SQL, span `app.rag.vector.search` có thể bao quanh query preparation, filter validation, mapping và kết quả. Span DB child chỉ đo thao tác database. Hai span bổ sung hai góc nhìn; nếu cả hai chỉ là wrapper cho cùng một duration và không có metadata mới, hãy cân nhắc bỏ một lớp.

### 2.2. Tên span và semantic conventions

Với các operation tiêu chuẩn như HTTP, database, RPC và messaging, ưu tiên **semantic conventions** tương ứng của OpenTelemetry hoặc instrumentation đang dùng. Tên và thuộc tính chuẩn có thể thay đổi theo phiên bản convention; khóa phiên bản thư viện/agent và xác minh dữ liệu thực tế khi nâng cấp.

Tên span custom của ứng dụng nên bổ sung ngữ nghĩa nghiệp vụ. Không tự tạo tên HTTP/DB trái quy ước nếu auto-instrumentation đã quản lý ranh giới đó.

## 3. Resource attributes, span attributes, events và metrics

Không phải metadata nào cũng nên gắn vào span. Chọn đúng nơi giúp dữ liệu dễ truy vấn và giảm chi phí:

| Thành phần | Mô tả | Ví dụ |
|---|---|---|
| Resource attributes | Nhận diện service/process/deployment tạo telemetry | `service.name`, `service.version`, `deployment.environment.name` |
| Span attributes | Mô tả một operation cụ thể | `app.ai.prompt.version`, `gen_ai.provider.name` |
| Span events | Sự kiện xảy ra tại một thời điểm trong span | `retry_scheduled`, `context_truncated` |
| Span status | Kết quả vận hành của operation | OK/ERROR hoặc trạng thái mặc định không lỗi |
| Metrics | Số đo tổng hợp trên nhiều operations | p95 latency, request count, token counter |
| Logs | Chi tiết sự kiện có thể gắn trace/span ID | Judge JSON schema invalid, source filter rejected |
| Evaluation result | Verdict theo dataset/rubric và provenance | relevance FAIL, fact checking PASS |

### 3.1. Resource attributes: “service nào đã tạo telemetry?”

Resource attributes thường được thiết lập ở cấp process/deployment, ví dụ:

| Key | Ví dụ | Mục đích |
|---|---|---|
| `service.name` | `answer-api` | Tên service |
| `service.version` | `2.4.1` | Phiên bản ứng dụng |
| `deployment.environment.name` | `staging` | Môi trường chạy |
| `service.namespace` | `ai-platform` | Nhóm service |
| `cloud.region` | `ap-southeast-1` | Vùng triển khai nếu phù hợp |

Đây không phải metadata thay đổi theo từng request. Không đặt prompt version hoặc case ID làm resource attribute, vì chúng thay đổi theo operation và có thể khiến resource identity bị phân mảnh.

### 3.2. Span attributes: “operation này đã chạy với cấu hình nào?”

Ví dụ một span model:

```text
span.name = app.ai.model.generate
attributes:
  gen_ai.operation.name = chat
  gen_ai.provider.name = openai
  gen_ai.request.model = configured-model-alias
  app.ai.prompt.version = answer-prompt-v7
  app.ai.pipeline.version = rag-pipeline-v4
  gen_ai.usage.input_tokens = 640
  gen_ai.usage.output_tokens = 82
```

Các key `gen_ai.*` thuộc hệ semantic conventions GenAI của OpenTelemetry và đã/đang phát triển theo phiên bản. Hãy kiểm tra convention và instrumentation version đang triển khai; không giả định mọi Spring AI release đều phát chính xác các key này. Namespace `app.ai.*` là ví dụ custom của ứng dụng.

### 3.3. Events: “điều gì xảy ra giữa lúc operation chạy?”

Một event phù hợp khi nó là mốc tức thời, không cần duration riêng:

- `retry_scheduled` với attempt number và retry reason đã phân loại.
- `fallback_selected` khi chuyển từ semantic search sang keyword search.
- `context_truncated` khi context vượt budget.
- `citation_rejected` khi một source reference không hợp lệ.
- `tool_policy_denied` khi tool bị chặn bởi policy.

Nếu một thao tác có duration đáng kể hoặc có remote I/O, hãy cân nhắc span riêng. Không tạo một span cho từng token streaming; dùng event/metrics tổng hợp như time-to-first-token và stream cancellation.

### 3.4. Metrics không phải nơi lưu mọi thuộc tính trace

Metrics nên dùng các dimensions có tập giá trị giới hạn, ví dụ operation, provider family, outcome và môi trường. Không thêm `traceId`, `caseId`, raw URL, user ID hoặc document ID làm label. Trace và result store phục vụ điều tra chi tiết; metric phục vụ thống kê tổng hợp.

## 4. Low-cardinality và high-cardinality trong Micrometer

Micrometer Observation phân biệt:

- **Low-cardinality key-values:** có thể được dùng cho cả metrics và traces.
- **High-cardinality key-values:** dành cho tracing/observation detail, không đưa vào metrics dimensions.

Ví dụ:

| Thuộc tính | Phân loại thường phù hợp | Lý do |
|---|---|---|
| `feature=policy_assistant` | Low | Ít tính năng, tập giá trị hữu hạn |
| `operation=retrieve` | Low | Tập operation ổn định |
| `provider=openai` | Low nếu số provider được kiểm soát | Phân nhóm provider |
| `outcome=success/error` | Low | Tập trạng thái nhỏ |
| `prompt.version=prompt-v7` | Tùy policy; có thể low nếu version được giới hạn | Version có thể tăng theo thời gian |
| `trace.id` | High | Gần như mỗi trace một giá trị |
| `evaluation.case_id` | High | Một giá trị cho mỗi case |
| `document.id` | High | Nhiều nguồn dữ liệu |
| `user.id` | High và nhạy cảm | Có thể nhận diện người dùng |
| `raw.question` | Không nên ghi | Dữ liệu nhạy cảm và cardinality vô hạn |

**Low/high cardinality không đồng nghĩa public/private.** Một trường low-cardinality vẫn có thể nhạy cảm, và một trường high-cardinality không tự động được phép ghi. Bảo mật và cardinality là hai phép đánh giá riêng.

### 4.1. Metric cardinality có thể tăng theo tích Descartes

Giả sử một metric có các labels:

- 5 providers
- 8 model families
- 4 outcomes
- 6 environments
- 20 prompt versions

Số series tối đa theo tích là:

\[
5 \times 8 \times 4 \times 6 \times 20 = 19{,}200
\]

Đây là ví dụ minh họa; số series thực còn phụ thuộc tổ hợp label có xuất hiện và backend. Nếu thêm một label `case_id` với hàng chục nghìn giá trị, số series có thể tăng rất nhanh. Dùng metric labels cho các nhóm có giới hạn, còn truy vấn theo case thì mở trace hoặc result artifact.

### 4.2. Đặt high-cardinality vào trace có kiểm soát

Trong trace, một `caseId` hoặc `runId` có thể giúp tìm đúng evaluation record. Chỉ thêm khi:

- Có mục đích điều tra rõ.
- Giá trị không chứa PII/secret.
- Trace backend có quyền truy cập, retention và redaction phù hợp.
- Kích thước attributes được giới hạn.
- Không dùng giá trị này để tạo metric series.

Nếu case ID có thể liên kết tới dữ liệu nhạy cảm, dùng opaque ID hoặc pseudonymous key và lưu mapping ở result store được phân quyền.

## 5. Thuộc tính chẩn đoán cho HTTP và tầng ứng dụng

Với HTTP server/client, ưu tiên semantic conventions hiện hành và instrumentation có sẵn. Những key thường gặp trong các phiên bản convention mới:

| Attribute | Ý nghĩa | Ví dụ |
|---|---|---|
| `http.request.method` | HTTP method | `POST` |
| `http.route` | Route template | `/api/answers` |
| `http.response.status_code` | Status trả về | `200` |
| `server.address` | Host/service đích | Host đã chuẩn hóa |
| `error.type` | Loại lỗi đã phân loại | `timeout` |

Tên key chính xác phụ thuộc phiên bản HTTP semantic conventions và instrumentation. Không copy raw URL có query string hoặc path chứa mã đơn làm span name. Dùng route template như `/orders/{id}`.

### 5.1. Attributes cho business operation

Span `app.ai.answer` có thể dùng:

| Key custom | Ví dụ | Ghi chú |
|---|---|---|
| `app.ai.feature` | `policy_assistant` | Nhóm chức năng |
| `app.ai.operation` | `answer` | Loại operation |
| `app.ai.mode` | `rag` | rag/direct/tool-assisted |
| `app.ai.pipeline.version` | `rag-v4` | Version pipeline |
| `app.ai.outcome` | `completed` | Kết quả kỹ thuật đã phân loại |
| `app.ai.fallback.used` | `true` | Có fallback hay không |

Không đặt answer text, user ID hoặc conversation transcript vào những attributes này.

### 5.2. Phân biệt HTTP status với AI quality

Một endpoint có thể trả HTTP 200 với câu trả lời không grounded. Khi đó:

- HTTP span phản ánh request được xử lý và trả response thành công.
- Model span phản ánh provider invocation hoàn tất.
- Evaluation record có thể là `groundedness=FAIL` hoặc `fact_check=FAIL`.

Không set HTTP span ERROR chỉ vì judge chấm answer sai. Ngược lại, judge timeout là lỗi vận hành của evaluation operation, không phải verdict FAIL của answer.

## 6. Thuộc tính cho RAG và truy cập dữ liệu

Một span retrieval nên giúp trả lời: **tìm bằng chiến lược nào, dùng cấu hình nào, có bao nhiêu kết quả và có fallback hay không?** Các thuộc tính cần mô tả operation mà không đưa raw query hoặc tài liệu vào telemetry.

### 6.1. Query rewrite và embedding

| Key gợi ý | Ví dụ | Giá trị chẩn đoán |
|---|---|---|
| `app.rag.query.rewrite.enabled` | `true` | Có viết lại query hay không |
| `app.rag.query.rewrite.strategy` | `llm` / `rule_based` | Cơ chế viết lại |
| `app.rag.embedding.provider` | `configured-provider` | Nguồn embedding |
| `app.rag.embedding.model` | `embed-model-v3` | Model/version embedding |
| `app.rag.embedding.dimension` | `1536` | Kích thước vector |
| `app.rag.embedding.outcome` | `success` / `error` | Kết quả operation |

Không ghi raw query hoặc toàn bộ vector float. Nếu cần so sánh query rewrite, lưu hash hoặc artifact đã redaction trong result store có quyền truy cập; trace chỉ giữ `rewrite.enabled`, strategy, model version và outcome.

### 6.2. Vector search và metadata filter

| Key gợi ý | Ví dụ | Giá trị chẩn đoán |
|---|---|---|
| `app.rag.store.type` | `pgvector` | Loại backend |
| `app.rag.search.strategy` | `semantic` / `hybrid` | Chiến lược truy xuất |
| `app.rag.search.top_k` | `8` | Số candidate yêu cầu |
| `app.rag.search.hit_count` | `6` | Số kết quả thực tế |
| `app.rag.search.filter_applied` | `true` | Code đã áp dụng filter |
| `app.rag.search.filter_policy_version` | `tenant-filter-v2` | Phiên bản policy |
| `app.rag.index.version` | `policy-index-v4` | Phiên bản index |
| `app.rag.search.outcome` | `hit` / `empty` / `error` | Kết quả truy xuất |

`filter_applied=true` chỉ chứng minh ứng dụng ghi nhận đã cấu hình filter; nó **không chứng minh database thực sự thực thi filter đúng**. Integration test phải seed dữ liệu nhiều tenant và xác minh không có document ngoài scope lọt vào.

### 6.3. Reranking và context assembly

| Key gợi ý | Ví dụ | Giá trị chẩn đoán |
|---|---|---|
| `app.rag.reranker.name` | `cross_encoder` | Loại reranker |
| `app.rag.reranker.version` | `rerank-v2` | Version |
| `app.rag.candidates.count` | `20` | Số candidate trước rerank |
| `app.rag.selected.count` | `5` | Số nguồn được chọn |
| `app.rag.context.truncated` | `true` | Context bị cắt |
| `app.rag.context.token_count` | `780` | Token count theo tokenizer/usage đã định nghĩa |
| `app.rag.context.budget` | `1200` | Budget cấu hình |

Các số lượng và version thường hữu ích để phân tích regression. Source IDs, rank và score từng tài liệu có thể có cardinality lớn; chỉ lưu ở trace khi có chính sách rõ, hoặc ưu tiên result store.

### 6.4. Truy cập SQL, JDBC, R2DBC và remote vector APIs

Để chẩn đoán data access, ưu tiên semantic conventions của instrumentation đang dùng. Những nhóm metadata có ích:

- Hệ database hoặc loại transport.
- Operation như SELECT/INSERT hoặc HTTP method.
- Collection/table đã chuẩn hóa nếu convention cho phép.
- Duration, status, error type và retry attempt.
- Backend/cluster version hoặc pool name nếu hữu ích và có giới hạn.

Tránh ghi:

- SQL đầy đủ có literal hoặc bind parameters nhạy cảm.
- URL có query string, API key hoặc tenant token.
- Embedding vector, document text hoặc toàn bộ search request.
- Một giá trị metric label riêng cho mỗi table row/document/user.

Nếu instrumentation SQL tự sinh span, không tạo thêm span custom cho cùng một SQL statement mà không có ý nghĩa mới. Span nghiệp vụ retrieval có thể bọc data span để cung cấp bối cảnh topK, filter policy và index version.

## 7. Thuộc tính cho model generation và streaming

Model invocation cần đủ thông tin để phân biệt **provider, model, operation, prompt version, usage và kết quả vận hành**. Các key GenAI semantic conventions đang được chuẩn hóa theo phiên bản; ví dụ dưới đây là nhóm tên thường gặp, cần kiểm tra schema của instrumentation thực tế.

| Attribute | Ví dụ | Lưu ý |
|---|---|---|
| `gen_ai.operation.name` | `chat` | Chat, embeddings hoặc operation khác |
| `gen_ai.provider.name` | `openai` | Provider |
| `gen_ai.request.model` | `model-alias` | Model được yêu cầu |
| `gen_ai.response.model` | `model-revision` | Model thực tế nếu provider trả về |
| `gen_ai.usage.input_tokens` | `640` | Usage input theo response |
| `gen_ai.usage.output_tokens` | `82` | Usage output theo response |
| `app.ai.prompt.version` | `answer-v7` | Phiên bản prompt của ứng dụng |
| `app.ai.generation.turn` | `2` | Lượt model trong tool loop |
| `app.ai.generation.streamed` | `true` | Có streaming |
| `app.ai.generation.outcome` | `completed` / `timeout` | Kết quả operation |

### 7.1. Tách request model và response model

Ứng dụng có thể yêu cầu alias như `fast-model`, trong khi provider trả về revision cụ thể. Nếu provider cung cấp cả hai, lưu riêng request model và response model. Không tự suy ra revision từ alias hoặc ghi một giá trị không có nguồn xác nhận.

### 7.2. Tool loop có nhiều model calls

Một câu trả lời có thể gồm:

```text
app.ai.answer
  ├── app.ai.model.generate  turn=1, result=tool_request
  ├── app.ai.tool.execute   tool=getOrderStatus
  └── app.ai.model.generate  turn=2, result=completed
```

Mỗi model turn là một invocation riêng và có usage riêng. Tổng application token/cost phải cộng các invocation duy nhất; không cộng lần nữa token ở parent span nếu parent chỉ tổng hợp cùng dữ liệu.

### 7.3. Streaming và latency

Đối với streaming, nên phân biệt:

- **Request duration:** từ khi bắt đầu model request tới khi stream kết thúc hoặc bị hủy.
- **Time to first token (TTFT):** từ mốc bắt đầu request đến token đầu tiên được nhận.
- **Inter-token latency:** khoảng cách giữa các token/chunk, thường tổng hợp thành histogram thay vì tạo span từng token.
- **Cancellation:** client đóng kết nối hoặc pipeline bị hủy trước khi hoàn tất.

Không dùng `gen_ai.usage.output_tokens` làm số token cuối cùng nếu stream bị hủy và provider chưa trả usage. Khi thiếu usage, ghi trạng thái unknown/estimated thay vì 0.

## 8. Thuộc tính cho tool calling

Tool span phải cho biết **tool nào được dispatch, có được phép hay không, callback có hoàn thành không và lỗi thuộc tầng nào**. Tên tool thường có tập giá trị nhỏ nếu được đăng ký trước; vẫn cần allowlist và không đưa arguments vào tên.

| Key gợi ý | Ví dụ | Giá trị chẩn đoán |
|---|---|---|
| `app.ai.tool.name` | `getOrderStatus` | Tool được gọi |
| `app.ai.tool.schema.version` | `order-tool-v3` | Phiên bản schema |
| `app.ai.tool.dispatch.outcome` | `accepted` / `denied` | Kết quả dispatch |
| `app.ai.tool.execution.outcome` | `success` / `error` | Kết quả callback |
| `app.ai.tool.retry.count` | `1` | Số retry |
| `app.ai.tool.idempotency` | `supported` | Hỗ trợ idempotency |

### 8.1. Phân biệt dispatch với execution

- **Dispatch:** model đề nghị tool; ứng dụng kiểm tra tên, schema, policy và quyền.
- **Execution:** callback thực sự chạy và có thể gọi HTTP/database.
- **Result handling:** chuẩn hóa kết quả và đưa lại vào model.

Nếu tool bị policy chặn, có thể ghi event `tool_policy_denied` trên span dispatch; không tạo span execution giả như thể callback đã chạy. Nếu callback thực sự gọi service ngoài, client HTTP/DB span là child của tool execution span khi context propagation hoạt động.

### 8.2. Không đưa tool arguments vào attributes theo mặc định

Arguments có thể chứa mã đơn, email, account ID hoặc dữ liệu bí mật. Thay vì ghi:

```text
app.ai.tool.order_id = DH-001
app.ai.tool.customer_email = user@example.com
```

hãy ghi metadata đã chuẩn hóa:

```text
app.ai.tool.name = getOrderStatus
app.ai.tool.arguments.valid = true
app.ai.tool.arguments.schema_version = order-tool-v3
```

Nếu cần so expected arguments với actual arguments trong tool evaluation, lưu payload đã redaction trong artifact riêng có quyền truy cập và retention rõ ràng.

## 9. Thuộc tính cho evaluation và judge

Đối với evaluation, cần phân biệt **execution status** với **quality verdict**. Span cho biết operation chấm đã chạy thế nào; result record cho biết answer đạt rubric hay không.

| Key gợi ý | Ví dụ | Nơi dùng |
|---|---|---|
| `app.ai.evaluation.run_id` | Opaque run ID | Trace/result store; không phải metric label |
| `app.ai.evaluation.case_id` | `rag-017` | High-cardinality trace/result store |
| `app.ai.evaluation.variant` | `prompt-B` | Attribute có giới hạn theo experiment |
| `app.ai.dataset.version` | `policy-eval-v3` | Trace/result manifest |
| `app.ai.rubric.version` | `groundedness-v2` | Trace/result manifest |
| `app.ai.evaluation.execution_status` | `completed` / `error` | Trạng thái chạy evaluator |
| `app.ai.evaluation.verdict` | `PASS` / `FAIL` | Quality verdict nếu được phép trên trace; source of truth là result store |
| `app.ai.evaluation.valid` | `true` / `false` | Có verdict hợp lệ hay không |
| `app.ai.evaluation.score` | `0.82` | Chỉ khi scale/rubric được định nghĩa rõ |

### 9.1. PASS/FAIL không thay thế ERROR/INVALID

Một hợp đồng kết quả nên tách:

| Execution status | Verdict | Ý nghĩa |
|---|---|---|
| `COMPLETED` | `PASS` | Đã chấm và đạt |
| `COMPLETED` | `FAIL` | Đã chấm và không đạt |
| `INVALID` | Không có verdict | Output không hợp đồng hoặc thiếu dữ liệu |
| `ERROR` | Không có verdict | Timeout, rate limit hoặc lỗi hệ thống |

Không ghi `judge.execution_status=PASS` để biểu thị answer tốt; dùng `execution_status=COMPLETED` và `verdict=PASS` nếu evaluator đã chấm hợp lệ. Nếu judge trả lỗi, không biến lỗi thành FAIL nội dung hoặc PASS mặc định.

### 9.2. Liên kết case với trace

Mỗi evaluation record nên lưu:

- `runId`, `caseId`, `variant`, `datasetVersion`, `rubricVersion`.
- `promptVersion`, `modelVersion`, `pipelineVersion`, `indexVersion`.
- `answerTraceId` và nếu cần `answerSpanId`.
- `judgeTraceId` và nếu cần `judgeSpanId`.
- Source IDs/hashes, tool expectations và actual outcomes đã được bảo vệ.
- Relevance, groundedness, fact checking, tool accuracy, execution status.
- Token, latency, estimated cost theo application/judge component.

Các ID này hỗ trợ tra cứu và replay; lưu chúng trong result store có schema/version. Span links có thể nối các traces trong backend, nhưng **không thay thế business correlation**.

## 10. Error, outcome và events: ghi điều có ích cho chẩn đoán

Span name nói operation nào đang chạy; attributes mô tả cấu hình và kết quả; status biểu thị lỗi vận hành. Không dùng một trường `status` chung cho cả HTTP, tool, judge và chất lượng answer vì các khái niệm đó khác nhau.

### 10.1. Phân loại outcome

| Operation | Outcome gợi ý | Span status |
|---|---|---|
| Vector search có hits | `hit` | Không lỗi |
| Vector search không có tài liệu | `empty` | Không lỗi nếu truy vấn hoàn tất bình thường |
| Vector search timeout | `timeout` | ERROR |
| Tool bị policy chặn | `denied` | Thường là quyết định nghiệp vụ/policy, không nhất thiết exception |
| Tool callback ném lỗi | `error` | ERROR |
| Model trả answer bình thường | `completed` | Không lỗi |
| Answer bị fact checking FAIL | `completed` ở span generation; verdict FAIL ở evaluation record | Không tự đặt generation span ERROR |
| Judge timeout | `error` | ERROR trên judge operation |
| Judge trả JSON không hợp đồng | `invalid_output` | Có thể là lỗi validation operation; verdict INVALID |

OpenTelemetry span status có trạng thái mặc định **Unset**, ngoài ra có OK và ERROR. Nhiều instrumentation chỉ đặt ERROR khi có exception hoặc tình huống lỗi theo convention; không cần ép mọi span thành OK. Đặc biệt, HTTP 4xx/5xx có cách diễn giải theo semantic conventions và vai trò client/server; không tự viết một quy tắc chung rằng mọi 4xx đều là ERROR ở mọi span.

### 10.2. Error type nên ổn định và ít giá trị

Ưu tiên:

- `timeout`
- `rate_limited`
- `connection_refused`
- `invalid_response`
- `schema_validation`
- `permission_denied`
- `dependency_unavailable`

Tránh dùng exception message làm attribute hoặc span name. Message có thể chứa raw SQL, URL, prompt fragment, user input hoặc secret. Nếu cần stack trace, dùng cơ chế exception recording của tracing backend đã cấu hình redaction/retention phù hợp.

### 10.3. Events cho các mốc tức thời

Một span retrieval có thể có events:

```text
app.rag.retrieve
  event: cache_miss
  event: semantic_search_started
  event: fallback_selected
  event: context_truncated
  outcome: success
```

Event nên có timestamp và attributes gọn. Nếu semantic search là một operation có remote I/O và duration, tạo child span cho search thay vì chỉ event. Nếu cache miss chỉ là một mốc tức thời, event hoặc attribute là đủ.

### 10.4. Retry và fallback

Ghi:

- Attempt number trong span con hoặc event.
- Retry reason đã phân loại, không phải raw exception message.
- Backoff duration hoặc một span riêng nếu thời gian chờ đáng kể.
- Fallback strategy đã chọn.
- Final outcome sau retry.

Không ghi mọi lần retry thành một span duy nhất rồi mất số request thực tế. Ngược lại, không tạo span cho từng vòng lặp nội bộ không có giá trị chẩn đoán. Quy ước phải phù hợp với retry policy và cách SDK thực hiện retry.

## 11. Đặt attributes theo thời điểm và mục đích truy vấn

Không phải attribute nào cũng biết được khi span bắt đầu. Một số metadata có sẵn từ request/config; số khác chỉ có sau khi operation kết thúc.

### 11.1. Metadata có sẵn khi start

Nên đặt ngay khi tạo span:

- Feature/operation/mode.
- Prompt, pipeline, index, model và rubric version đã chọn.
- Provider và loại backend.
- Sampling/streaming mode nếu biết.
- Experiment variant đã được phân bổ.

Điều này hữu ích nếu sampler hoặc exporter cần biết metadata trước khi span kết thúc.

### 11.2. Metadata chỉ biết sau khi chạy

Ví dụ:

- Hit count và selected document count.
- Final HTTP status hoặc tool outcome.
- Actual token usage.
- Retry count cuối cùng.
- Citation validation outcome.

Có thể ghi bằng observation/span API phù hợp, event hoặc metric riêng. Cần xác minh API/instrumentation có hỗ trợ cập nhật sau khi start và backend có export giá trị cuối hay không. Nếu một attribute cần cho **head sampling**, phải có trước khi sampler ra quyết định; giá trị chỉ biết sau operation không thể quay ngược thay đổi quyết định lấy mẫu.

### 11.3. Không lưu cùng dữ liệu ở mọi tầng

Một request có thể có `promptVersion` trong model span, pipeline version trong RAG span và rubric version trong judge span. Không nhất thiết lặp mọi version trên tất cả spans. Chọn:

- Attribute ở span sở hữu operation.
- Resource attribute cho thông tin deployment/service.
- Business manifest/result record cho bộ phiên bản đầy đủ của một case.
- Metric label chỉ cho dimensions cần dashboard và có cardinality giới hạn.

## 12. Ví dụ Java: Observation với low/high cardinality

Ví dụ dưới đây dùng Micrometer Observation trong service gọi Spring AI ChatClient. Tên span và key `app.ai.*` là quy ước của ứng dụng; các spans model/provider bên trong phụ thuộc instrumentation và phiên bản Spring AI đang dùng.

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.stereotype.Service;

@Service
final class ObservedAnswerService {
    private final ObservationRegistry observations;
    private final ChatClient chatClient;

    ObservedAnswerService(
            ObservationRegistry observations,
            ChatClient.Builder chatClientBuilder) {
        this.observations = observations;
        this.chatClient = chatClientBuilder.build();
    }

    String answer(
            String question,
            String promptVersion,
            String opaqueCaseId) {

        Observation observation = Observation.createNotStarted(
                        "app.ai.answer", observations)
                .lowCardinalityKeyValue(
                        "app.ai.feature", "policy_assistant")
                .lowCardinalityKeyValue(
                        "app.ai.mode", "rag")
                .lowCardinalityKeyValue(
                        "app.ai.operation", "answer")
                .highCardinalityKeyValue(
                        "app.ai.prompt.version", promptVersion);

        // Chỉ thêm opaque case ID nếu trace policy cho phép.
        if (opaqueCaseId != null && !opaqueCaseId.isBlank()) {
            observation.highCardinalityKeyValue(
                    "app.ai.evaluation.case_id", opaqueCaseId);
        }

        return observation.observe(() -> chatClient.prompt()
                .user(question)
                .call()
                .content());
    }
}
```

Trong Micrometer, low-cardinality key-values có thể được dùng cho metrics và traces; high-cardinality key-values dành cho trace detail. `promptVersion` được đặt high-cardinality trong ví dụ để tránh tự động biến mỗi lần phát hành prompt thành metric series mới. Nếu hệ thống có một tập variant nhỏ, được kiểm soát (ví dụ A/B), có thể dùng một attribute/metric dimension riêng cho variant theo policy.

`opaqueCaseId` không phải raw user ID. Nếu ID có thể liên kết với dữ liệu cá nhân, hãy pseudonymize hoặc bỏ khỏi trace; giữ mapping trong result store có phân quyền. Đoạn code minh họa cách gắn tags, không thay thế filter tenant, redaction hoặc evaluation result persistence.

### 12.1. Ví dụ span cho bước retrieval

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.List;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;

final class ObservedPolicyRetriever {
    private final ObservationRegistry observations;
    private final VectorStore vectorStore;

    ObservedPolicyRetriever(
            ObservationRegistry observations,
            VectorStore vectorStore) {
        this.observations = observations;
        this.vectorStore = vectorStore;
    }

    List<Document> retrieve(String query, int topK) {
        Observation observation = Observation.createNotStarted(
                        "app.rag.vector.search", observations)
                .lowCardinalityKeyValue(
                        "app.rag.store.type", "configured-vector-store")
                .lowCardinalityKeyValue(
                        "app.rag.search.strategy", "semantic")
                .lowCardinalityKeyValue(
                        "app.rag.search.top_k", Integer.toString(topK));

        return observation.observe(() -> {
            SearchRequest request = SearchRequest.builder()
                    .query(query)
                    .topK(topK)
                    .build();
            return vectorStore.similaritySearch(request);
        });
    }
}
```

Đây là ví dụ API Spring AI 1.x phổ biến; cần kiểm tra builder/import đúng phiên bản dependency đang khóa. Mẫu này không thêm tenant filter; production phải truyền filter từ identity đáng tin và test backend thực thi filter. `VectorStore` có thể tự gọi embedding model, do đó không tự thêm một embedding span hoặc request thứ hai nếu code không thực hiện operation đó.

### 12.2. Đếm hit/miss bằng metric có cardinality giới hạn

Nếu muốn dashboard số lần retrieval hit/miss, dùng một Counter hoặc metric phù hợp với nhãn outcome nhỏ:

```java
import io.micrometer.core.instrument.MeterRegistry;
import java.util.List;
import org.springframework.ai.document.Document;

final class RetrievalOutcomeMetrics {
    private final MeterRegistry meters;

    RetrievalOutcomeMetrics(MeterRegistry meters) {
        this.meters = meters;
    }

    void record(List<Document> documents) {
        String outcome = documents.isEmpty() ? "empty" : "hit";
        meters.counter(
                "app.rag.retrieval.requests",
                "outcome", outcome,
                "feature", "policy_assistant")
                .increment();
    }
}
```

Không thêm `caseId`, `traceId`, `documentId` hoặc raw query làm tags của Counter. Nếu cần điều tra một lần search cụ thể, mở trace hoặc result record.

## 13. Quy tắc đặt key và value nhất quán

Tên span và attribute key là **hợp đồng dữ liệu** giữa code, dashboard, alert, trace query và pipeline phân tích. Nếu mỗi nhóm dùng một tên khác nhau cho cùng một khái niệm, telemetry sẽ khó tổng hợp.

### 13.1. Dùng namespace rõ ràng

Một quy ước đơn giản:

- Key chuẩn HTTP/DB/GenAI: dùng semantic conventions hiện hành của OpenTelemetry/instrumentation.
- Key riêng cho ứng dụng: bắt đầu bằng namespace như `app.ai.`, `app.rag.` hoặc namespace tổ chức đã thống nhất.
- Không ghi đè key chuẩn bằng ý nghĩa khác.
- Không dùng cùng một key cho hai kiểu dữ liệu khác nhau giữa các services.

Ví dụ:

| Khái niệm | Nên thống nhất | Tránh |
|---|---|---|
| Prompt version | `app.ai.prompt.version` | `prompt`, `promptVer`, `prompt_version` ở từng service |
| Pipeline version | `app.ai.pipeline.version` | `pipeline` khi có nhiều nghĩa |
| Model provider | Semantic convention phù hợp hoặc một custom key thống nhất | `vendor` ở service A, `llm` ở service B |
| Retrieval topK | `app.rag.search.top_k` | `k`, `limit` không rõ phạm vi |
| Judge verdict | `app.ai.evaluation.verdict` | Gộp vào `status` |
| Error type | `error.type` theo convention phù hợp | Raw exception message |

### 13.2. Value phải chuẩn hóa

Chọn tập giá trị có ý nghĩa, viết nhất quán:

```text
outcome = success | empty | error | denied | timeout
mode = direct | rag | tool_assisted
strategy = semantic | keyword | hybrid
cache = hit | miss | bypass | error
verdict = PASS | FAIL | INVALID | ERROR
```

Không để một service ghi `success`, service khác ghi `ok`, service khác ghi `done` nếu chúng cùng biểu thị một trạng thái. Nếu trạng thái khác nhau về ý nghĩa, hãy dùng key riêng thay vì ép chúng vào một enum chung.

### 13.3. Không đưa version vào span name

Không dùng:

```text
app.ai.answer.prompt-v7
app.ai.answer.prompt-v8
app.ai.answer.model-x
```

Nên dùng:

```text
span.name = app.ai.answer
attributes:
  app.ai.prompt.version = prompt-v7
  gen_ai.request.model = model-x
```

Điều này giúp query cùng operation qua nhiều version, đồng thời so sánh latency và error rate theo metadata. Với metrics, chỉ đưa version vào label nếu tập giá trị được giới hạn, có retention và ngân sách cardinality phù hợp.

### 13.4. Giữ value có kiểu dữ liệu đúng

Ưu tiên:

- Boolean cho cờ bật/tắt.
- Integer cho counts, attempt number, token count.
- Number cho score/duration nếu convention quy định.
- String cho enum, version và provider.
- Không serialize cả object JSON lớn thành một string attribute.

Ví dụ `app.rag.search.top_k` nên là integer nếu API hỗ trợ kiểu số; `app.rag.search.filter_applied` nên là boolean; `app.ai.prompt.version` là string. Kiểu nhất quán giúp truy vấn và dashboard chính xác.

## 14. Từ điển attributes tham chiếu cho một pipeline Spring AI

Bảng dưới đây là **attribute dictionary đề xuất** để một nhóm thống nhất trước khi triển khai. Không nhất thiết mọi span phải có mọi key; chỉ ghi trường có ý nghĩa ở operation sở hữu nó.

| Span | Key | Kiểu | Card. gợi ý | Mục đích |
|---|---|---|---|---|
| `app.ai.answer` | `app.ai.feature` | string | Low | Phân nhóm tính năng |
| `app.ai.answer` | `app.ai.mode` | string | Low | direct/rag/tool_assisted |
| `app.ai.answer` | `app.ai.pipeline.version` | string | Theo policy | So phiên bản pipeline |
| `app.rag.retrieve` | `app.rag.search.strategy` | string | Low | semantic/keyword/hybrid |
| `app.rag.retrieve` | `app.rag.search.top_k` | integer | Thường low | Cấu hình topK |
| `app.rag.retrieve` | `app.rag.search.hit_count` | integer | Trace/metric | Số hits |
| `app.rag.retrieve` | `app.rag.index.version` | string | Theo policy | Version index |
| `app.rag.context.build` | `app.rag.context.truncated` | boolean | Low | Context bị cắt |
| `app.ai.model.generate` | `gen_ai.provider.name` | string | Low | Provider |
| `app.ai.model.generate` | `gen_ai.request.model` | string | Theo policy | Model alias |
| `app.ai.model.generate` | `app.ai.prompt.version` | string | Trace detail | Version prompt |
| `app.ai.model.generate` | `gen_ai.usage.input_tokens` | integer | Trace/metric | Input usage |
| `app.ai.model.generate` | `gen_ai.usage.output_tokens` | integer | Trace/metric | Output usage |
| `app.ai.tool.execute` | `app.ai.tool.name` | string | Low nếu allowlist | Tên tool |
| `app.ai.tool.execute` | `app.ai.tool.execution.outcome` | string | Low | Outcome callback |
| `app.ai.evaluation.case` | `app.ai.evaluation.case_id` | string | High | Tra case cụ thể |
| `app.ai.evaluation.case` | `app.ai.rubric.version` | string | Trace detail | Version rubric |
| `app.ai.evaluation.case` | `app.ai.evaluation.verdict` | string | Low nếu dashboard cần | PASS/FAIL/INVALID/ERROR |

Cardinality trong bảng chỉ là gợi ý; số giá trị thực tế, mức nhạy cảm và khả năng truy vấn của backend mới quyết định có nên xuất trường hay không. Với Micrometer, dùng low/high cardinality APIs đúng mục đích. Với OpenTelemetry trực tiếp, đánh giá cả số series của backend metrics, dung lượng trace và quyền riêng tư.

## 15. Kiểm thử naming và attributes

Quy ước chỉ có giá trị khi được kiểm tra. Có thể dùng fake model/retriever và test Observation handler hoặc in-memory span exporter để xác minh **span names, key names, value types và dữ liệu không được phép xuất hiện**.

### 15.1. Kiểm thử hợp đồng naming

Một test nên xác nhận:

1. Tên span là operation ổn định như `app.ai.answer`, không chứa case ID.
2. Key custom nằm trong namespace thống nhất.
3. Prompt/model/index/rubric version xuất hiện ở đúng operation.
4. Metric dimensions không chứa trace/case/document/user IDs.
5. Không có raw prompt, answer, SQL binding hoặc tool argument nhạy cảm trong exported attributes/events.
6. HTTP/DB spans dùng semantic conventions của instrumentation tương ứng, không tự tạo bản sao với tên trái quy ước.

### 15.2. Ví dụ assertion trên Observation handler

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.ArrayList;
import java.util.List;

final class RecordingObservationHandler
        implements ObservationHandler<Observation.Context> {
    final List<String> names = new ArrayList<>();

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }

    @Override
    public void onStart(Observation.Context context) {
        names.add(context.getName());
    }
}

final class ObservationTestFixture {
    static ObservationRegistry registryWith(
            RecordingObservationHandler handler) {
        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig().observationHandler(handler);
        return registry;
    }
}
```

Fixture trên ghi nhận tên observations khi start. Để kiểm tra attributes, handler có thể lưu snapshot các key-values từ `Observation.Context` trong callback; cần dùng API accessor phù hợp với Micrometer version của dự án. Không nên viết test dựa trên một internal implementation detail không được API công khai bảo đảm.

### 15.3. Test span attributes bằng exporter

Với OpenTelemetry in-memory exporter, kiểm tra span đã export:

```text
assert span.name == "app.ai.answer"
assert span.attributes["app.ai.feature"] == "policy_assistant"
assert span.attributes["app.ai.prompt.version"] == "answer-v7"
assert span.attributes does not contain "raw.question"
assert span.attributes does not contain "user.email"
assert span.name does not contain caseId
```

Đây là pseudocode assertion, không phải API cụ thể của exporter. Khi test chạy qua Micrometer Tracing bridge, hãy thu spans từ đúng SDK/bridge đang được ứng dụng sử dụng để bảo đảm test quan sát dữ liệu thật sự sẽ được export.

### 15.4. Kiểm tra low/high cardinality

Một integration test có thể phát 100 requests với 100 case IDs khác nhau:

- Trace spans có thể chứa opaque case IDs theo policy.
- Metric series không tăng thêm 100 giá trị label case ID.
- Metric dimensions chỉ gồm feature, operation, outcome và variant có giới hạn.
- Tổng số metric series nằm trong ngân sách cardinality đã đặt.

Không cần hardcode một con số series chung cho mọi backend; xác định budget theo hệ metrics đang sử dụng.

## 16. Điều tra một regression bằng tên span và attributes

Giả sử prompt A và B cùng chạy trên dataset version `policy-eval-v3`. B có fact checking giảm, latency tăng và chi phí cao hơn. Một trace có naming/attributes tốt giúp phân tích:

| Quan sát | Attribute/span cần xem | Giả thuyết cần kiểm tra |
|---|---|---|
| Retrieval chậm hơn | `app.rag.search.top_k`, `app.rag.index.version`, DB span duration | TopK/filter/index/query plan thay đổi |
| Nguồn cũ xuất hiện | `index.version`, filter policy version, source IDs trong result store | Index stale hoặc filter hiệu lực sai |
| Context lớn hơn | `context.token_count`, `context.truncated` | Reranker giữ nhiều chunks hoặc chunk size đổi |
| Model latency tăng | `gen_ai.request.model`, prompt version, input tokens | Model khác hoặc prompt/context dài hơn |
| Tool calls tăng | `app.ai.tool.name`, generation turn, dispatch outcome | Prompt/model thay đổi cách chọn tool |
| Judge ERROR tăng | Judge provider/model, `error.type`, retry count | Rate limit, timeout hoặc schema drift |
| Fact checking giảm | Rubric version, selected source IDs, answer trace | Source/answer thay đổi hoặc judge/rubric đổi |
| Cost tăng | Usage theo từng model invocation/component | Nhiều turns, context lớn hoặc model đắt hơn |

### 16.1. Ví dụ so sánh hai trace

```text
Variant A
  app.rag.vector.search
    top_k=5, hit_count=5, index=v2
  app.rag.context.build
    token_count=480, truncated=false
  app.ai.model.generate
    model=fast-alias, input_tokens=620

Variant B
  app.rag.vector.search
    top_k=12, hit_count=12, index=v3
  app.rag.context.build
    token_count=1180, truncated=true
  app.ai.model.generate
    model=fast-alias, input_tokens=1320
```

Các giá trị chỉ minh họa. Trace B cho thấy cấu hình retrieval và context khác A; chưa đủ để kết luận nguyên nhân factuality giảm. Cần kiểm tra source IDs, hiệu lực tài liệu, prompt version và golden facts. **Tên span ổn định cho phép so sánh; attributes giải thích sự khác nhau.**

### 16.2. Không suy luận chất lượng từ một attribute đơn lẻ

- `hit_count` cao không đồng nghĩa retrieval relevance cao.
- `context.token_count` thấp không đồng nghĩa context tốt.
- `model.status=success` không đồng nghĩa answer grounded.
- `tool.execution.outcome=success` không đồng nghĩa tool arguments đúng.
- `judge.verdict=PASS` chỉ có ý nghĩa nếu judge output hợp lệ, rubric/version đúng và evaluation case có dữ kiện chuẩn.

Dùng trace để tìm nguyên nhân và result store/dataset để xác minh kết quả.

## 17. Bảo mật, redaction và retention

Tên span và attributes là dữ liệu telemetry, có thể được gửi tới collector/backend tập trung và nhiều nhóm có quyền truy vấn. Một trường có ích khi debug vẫn có thể gây rủi ro nếu chứa dữ liệu cá nhân hoặc bí mật.

### 17.1. Những dữ liệu không nên ghi trực tiếp

- API key, bearer token, cookie, authorization header.
- Email, số điện thoại, địa chỉ hoặc user ID có thể nhận diện.
- Raw prompt, answer, conversation history hoặc retrieved document text.
- SQL có literal/bind values nhạy cảm.
- Tool arguments có account/order IDs hoặc dữ liệu khách hàng.
- Embedding vector và payload request/response đầy đủ.

Nếu cần giữ nội dung để replay/evaluation, lưu trong **artifact/result store** được phân quyền, mã hóa, redaction và retention riêng. Trace chỉ giữ artifact ID/hash nếu policy cho phép; không biến trace backend thành kho prompt không kiểm soát.

### 17.2. Redaction trước khi export

Redaction nên xảy ra trước khi telemetry rời process/trust boundary. Đừng chỉ ẩn một trường trên UI nhưng vẫn export dữ liệu thô tới collector. Xây allowlist attributes thay vì blacklist một vài key đã biết, vì SDK hoặc dependency mới có thể bổ sung trường khác.

### 17.3. Retention theo mục đích

| Dữ liệu | Retention cần cân nhắc |
|---|---|
| Metrics tổng hợp | Theo nhu cầu trend/SLO và chính sách chi phí |
| Traces vận hành thông thường | Ngắn hơn hoặc sampling |
| Traces lỗi/critical | Có thể giữ lâu hơn theo policy |
| Evaluation result/manifest | Theo yêu cầu audit/reproducibility |
| Raw prompt/document artifacts | Ngắn nhất có thể, có phân quyền rõ |

Một trace có thể tồn tại lâu hơn answer artifact hoặc ngược lại. Hãy thiết kế correlation ID và retention đồng bộ để không lưu metadata trỏ tới artifact đã xóa mà không có trạng thái giải thích.

## 18. Bài thực hành: chuẩn hóa span taxonomy cho một ứng dụng Spring AI

**Bối cảnh:** Một chatbot chính sách dùng HTTP API, Spring AI ChatClient, RAG qua PGvector, tool sandbox tra cứu đơn hàng và worker chấm evaluation theo relevance, groundedness, fact checking. Nhóm muốn so sánh prompt A/B và model revisions.

### Phần A — Xây naming convention

1. Liệt kê operations thực tế: answer, query rewrite, embedding, vector search, rerank, context build, model generation, tool dispatch/execution, judge.
2. Đặt span name ổn định theo operation, dùng namespace `app.ai.` và `app.rag.`.
3. Xác định spans HTTP/JDBC/HTTP client do framework tạo và không tạo bản sao.
4. Viết attribute dictionary: key, type, owner span, cardinality, privacy classification và ví dụ value.
5. Chọn semantic conventions phù hợp với HTTP, database, GenAI và messaging.

### Phần B — Instrument và kiểm tra

1. Dùng `ObservationRegistry` để tạo span `app.ai.answer` với feature/mode/operation tags.
2. Dùng high-cardinality trace detail cho opaque case ID hoặc prompt version khi policy cho phép.
3. Bổ sung span retrieval/tool/evaluation ở đúng ranh giới code.
4. Bật tracing bridge/exporter và kiểm tra trace thực trong backend.
5. Dùng fake model/retriever và test handler để xác minh names, attributes và lifecycle.

### Phần C — Đo cardinality và bảo mật

1. Chạy 100 cases khác nhau; kiểm tra metric series không tăng theo case IDs.
2. Đưa email/API key giả vào question và tool arguments; xác minh chúng không xuất hiện trong exported spans.
3. Xác minh raw SQL và query string không lọt vào span names/attributes.
4. Kiểm tra version labels có giới hạn và có owner chịu trách nhiệm cập nhật.
5. Xác minh result store vẫn giữ provenance cần thiết sau khi trace sampling giảm.

### Phần D — Điều tra regression

1. Chạy prompt A/B trên cùng dataset, rubric, corpus/index và evaluation harness.
2. Mở traces, so retrieval strategy/topK/hit count, context token count, model/provider, tool calls và latency.
3. Đối chiếu source IDs/hashes với verified facts để tìm nguyên nhân fact checking FAIL.
4. Phân biệt judge ERROR/INVALID với verdict FAIL hợp lệ.
5. Tổng hợp metrics p95 latency, token/cost theo application/judge component và quality valid coverage.

### Câu hỏi tự kiểm tra

**1. Vì sao không nên đặt case ID vào span name?**  
Vì tên span sẽ có cardinality rất cao, khó nhóm operation và khó xây dashboard ổn định. Dùng tên operation cố định và chỉ đưa opaque case ID vào trace/result store khi policy cho phép.

**2. Có thể đưa prompt version vào low-cardinality metric label không?**  
Có thể nếu tập version được giới hạn và có ngân sách cardinality rõ; nếu version tăng liên tục, nên giữ ở trace/result manifest hoặc dùng metric dimension đã được kiểm soát.

**3. Vector search trả 0 hits có nên đặt span ERROR không?**  
Không nhất thiết. Nếu truy vấn hoàn tất bình thường, outcome có thể là empty; chỉ timeout/exception/lỗi vận hành mới là ERROR. Chất lượng retrieval cần được đánh giá riêng.

**4. Model span có status OK nhưng fact checking FAIL. Có mâu thuẫn không?**  
Không. Span status phản ánh operation hoàn tất về kỹ thuật; fact checking là verdict nội dung từ evaluator.

**5. Vì sao cần tách request model và response model?**  
Ứng dụng có thể yêu cầu một alias nhưng provider trả về revision cụ thể. Ghi riêng giúp biết cấu hình yêu cầu và model thực tế nếu provider cung cấp.

**6. Có nên ghi full SQL để tìm query chậm?**  
Không mặc định. Dùng operation/table đã chuẩn hóa, duration, status và query plan/artifact bảo vệ theo policy; raw SQL/bind values có thể chứa dữ liệu nhạy cảm.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Tên span chung chung `process`/`call` | Không biết operation nào đang chạy | Dùng tên theo operation |
| Nhúng case ID vào span name | Cardinality cao, khó nhóm | Tên ổn định, ID ở trace detail/result store |
| Nhúng prompt version vào span name | Tạo nhiều tên cho cùng operation | Dùng attribute version |
| Tự tạo span trùng HTTP/DB/model instrumentation | Đếm đôi và khó đọc cây trace | Kiểm tra spans sẵn có trước |
| Dùng key custom mỗi service một kiểu | Dashboard và truy vấn không thống nhất | Attribute dictionary chung |
| Dùng raw exception message làm error type | Lộ dữ liệu, cardinality vô hạn | Error type đã phân loại |
| Ghi raw prompt/tool args/SQL bindings | Rò rỉ dữ liệu nhạy cảm | Allowlist, redaction, artifact store |
| Đặt case ID/trace ID làm metric labels | Nổ số time series | Chỉ dùng labels ít cardinality |
| Dùng low-cardinality cho mọi version không giới hạn | Cardinality tăng theo thời gian | Giới hạn version dimensions |
| Gộp execution status và quality verdict | PASS/FAIL bị hiểu sai | Tách COMPLETED/ERROR/INVALID với PASS/FAIL |
| Coi empty retrieval là database error | Đếm sai lỗi vận hành | Outcome empty riêng |
| Coi model success là groundedness PASS | Bỏ lọt hallucination | Evaluation bằng rubric/verified facts |
| Đưa mọi metadata vào mọi span | Trace phình lớn và trùng lặp | Chọn span sở hữu thông tin |
| Đưa event tức thời thành span riêng | Quá nhiều spans | Event nếu không có duration đáng kể |
| Tạo span cho từng token | Overhead và dung lượng lớn | TTFT/histogram/chunk summary |
| Không test attribute schema | Key/value drift qua releases | Contract tests và versioned dictionary |

## 20. Ghi nhớ

- **Span name mô tả operation**, ổn định và không chứa dữ liệu theo từng request.
- **Attributes giải thích operation chạy với cấu hình nào**: feature, provider, model, prompt, pipeline, index, rubric, outcome.
- **Resource attributes** nhận diện service/deployment; **span attributes** mô tả operation; **events** ghi mốc tức thời; **metrics** tổng hợp.
- **Low-cardinality values** có thể làm metric dimensions; high-cardinality details chỉ nên ở traces theo policy. Cardinality và privacy là hai phép đánh giá riêng.
- **Semantic conventions** của HTTP, DB, messaging và GenAI giúp các services dùng schema nhất quán; kiểm tra phiên bản convention/instrumentation.
- **RAG attributes** nên ghi strategy, topK, hit count, filter policy version, index version, reranker và context truncation; source IDs chi tiết thuộc result store hoặc trace được bảo vệ.
- **Model attributes** cần phân biệt provider, request model, response model, prompt version, từng model turn và usage.
- **Tool attributes** nên ghi tool name, schema version, dispatch/execution outcome; không ghi raw arguments theo mặc định.
- **Evaluation** phải tách execution status COMPLETED/ERROR/INVALID với verdict PASS/FAIL và lưu provenance theo run/case/version.
- **Span status OK không đồng nghĩa answer đúng**; relevance, groundedness, fact checking và tool accuracy cần evaluator/golden data riêng.
- **Tên và attributes là hợp đồng telemetry**: cần dictionary, allowlist, test exporter, cardinality budget, redaction và retention.

Đặt tên span và thuộc tính có giá trị chẩn đoán giúp trace Spring AI trở thành dữ liệu có thể truy vấn và so sánh qua nhiều phiên bản. Khi tên operation ổn định, attributes có schema rõ và result records liên kết với đúng run/case/rubric, nhóm phát triển có thể xác định bottleneck, tìm nguyên nhân fact checking hoặc relevance suy giảm, theo dõi token/chi phí và đánh giá thay đổi prompt/model/pipeline bằng bằng chứng thay vì suy đoán từ một log tổng quát.
