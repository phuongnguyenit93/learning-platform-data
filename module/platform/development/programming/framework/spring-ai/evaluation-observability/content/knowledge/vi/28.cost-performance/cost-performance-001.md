# Tách chi phí sinh câu trả lời, embedding, công cụ và đánh giá

## 1. Một câu trả lời AI có nhiều nguồn chi phí

Một request Spring AI có thể trông như một lần gọi API từ phía người dùng, nhưng bên trong có thể thực hiện nhiều hoạt động có hóa đơn và tài nguyên riêng:

- Gọi ChatModel một hoặc nhiều lần để lập kế hoạch, gọi tool và tạo câu trả lời.
- Tạo embedding cho câu hỏi, hoặc cho tài liệu trong một pipeline ingest chạy trước đó.
- Truy vấn VectorStore, đọc dữ liệu, rerank hoặc lấy tài liệu từ kho lưu trữ.
- Thực thi tool gọi API nghiệp vụ, dịch vụ bên thứ ba, database hoặc compute.
- Chạy evaluator, LLM-as-a-judge, fact checker hoặc model đánh giá relevance.
- Gửi telemetry, lưu trace, metrics, logs và kết quả evaluation.
- Dùng CPU, RAM, GPU, network, storage và các thành phần hạ tầng dùng chung.

Nếu gộp tất cả thành một con số “giá mỗi câu trả lời”, nhóm khó biết chi phí tăng vì model sinh dài hơn, retrieval tốn hơn, tool retry, evaluator chạy thêm lượt hay hạ tầng bị quá tải.

Trong module SPRING_AI_EVALUATION_OBSERVABILITY, việc tách chi phí giúp so sánh prompt, model, retrieval pipeline và tool policy theo cùng dataset. Mỗi thay đổi cần được đánh giá đồng thời về chất lượng, latency và chi phí.

**Nguyên tắc:** đo theo hoạt động tạo ra chi phí, sau đó phân bổ về request, case, attempt, evaluation run, tenant hoặc phiên bản pipeline. Một request có thể có nhiều lần gọi model; một lần ingest tài liệu có thể phục vụ hàng nghìn request; một lượt đánh giá có thể phát sinh chi phí model độc lập với candidate đang được đánh giá.

### Kết quả học tập

Sau bài này, người học có thể:

1. Phân rã chi phí generation, embedding, retrieval/vector DB, tool, evaluator và telemetry/compute.
2. Phân biệt chi phí online của một request với chi phí offline của ingest và evaluation.
3. Tính chi phí token từ usage thực tế và bảng giá có version.
4. Tính chi phí của tool/API theo số lần gọi và đơn giá của nhà cung cấp.
5. Phân bổ chi phí dùng chung cho từng case hoặc tenant theo quy tắc minh bạch.
6. Theo dõi cost per request, cost per successful task, cost per 1,000 cases và cost per tenant.
7. Kết hợp latency, throughput, token usage và chất lượng để chọn tối ưu.
8. Thiết lập budget, quota, retry limit và cảnh báo chi phí.

## 2. Bản đồ chi phí trong một pipeline Spring AI

Một pipeline RAG có tool và evaluator có thể được phân rã như sau:

~~~mermaid
flowchart TD
    R["Evaluation runner / User request"] --> ORCH["Spring AI application"]
    ORCH --> GEN["Chat generation"]
    ORCH --> EMBQ["Query embedding"]
    EMBQ --> VS["Vector database / retrieval"]
    VS --> RR["Optional reranker"]
    RR --> GEN
    GEN -->|tool call request| TOOL["Tool execution / external API"]
    TOOL --> GEN
    GEN --> OUT["Final answer"]
    OUT --> EVAL["Evaluator / judge / fact checker"]
    EVAL --> RESULT["Evaluation result store"]
    INGEST["Offline document ingestion"] --> EMBDOC["Document embeddings"]
    EMBDOC --> VS
    ORCH --> TEL["Metrics / traces / logs"]
    TEL --> OBS["Observability backend"]
    GEN --> BILL["Usage and pricing ledger"]
    EMBQ --> BILL
    EMBDOC --> BILL
    TOOL --> BILL
    EVAL --> BILL
    VS --> BILL
    OBS --> BILL
~~~

| Nhóm chi phí | Hoạt động phát sinh | Đơn vị đo thường gặp |
|---|---|---|
| Chat generation | Input/output tokens, cached tokens, image/audio tokens, model calls | Token theo loại, request/call |
| Embedding | Embed query, embed document/chunk | Input tokens, số item, batch |
| Retrieval/vector DB | Query, read/write, index, storage, replicas | Request, read/write unit, GB/tháng |
| Reranking | Gọi reranker model hoặc dịch vụ | Pair/document, token, request |
| Tool/API | Gọi dịch vụ ngoài, compute hoặc database | Call, operation, compute time, data transfer |
| Evaluation | Judge model, fact-check model, evaluator compute | Judge tokens, số case, CPU/GPU time |
| Observability | Export, ingest, index và lưu telemetry | Span/log volume, metric series, GB/ngày |
| Application infrastructure | App, worker, queue, cache, database | CPU/RAM/GPU, node-hour, storage, network |

Không phải mọi dòng đều có hóa đơn theo request. Vector DB, cluster, logging backend và app runtime thường là chi phí dùng chung theo tháng hoặc theo capacity. Phải giữ riêng **chi phí đo trực tiếp** và **chi phí phân bổ**.

## 3. Chọn đơn vị hạch toán trước khi tính

Một số đơn vị thường được dùng:

| Đơn vị | Định nghĩa | Dùng khi |
|---|---|---|
| Request | Một HTTP/API request đến ứng dụng | Theo dõi trải nghiệm trực tuyến |
| Task | Một mục tiêu nghiệp vụ hoàn chỉnh | So sánh chi phí hoàn thành công việc |
| Attempt | Một lần thử thực hiện task, bao gồm retry | Đo chi phí retry/failure |
| Model call | Một lần gửi request đến model provider | Tính usage và giá model |
| Evaluation case | Một tình huống trong dataset | So sánh chi phí kiểm thử |
| Evaluation run | Một lượt chạy toàn bộ hoặc một phần dataset | Tính ngân sách regression |
| Tenant/project | Đơn vị khách hàng hoặc sản phẩm | Chargeback/showback |
| Pipeline version | Tập hợp prompt, model, retriever, tools và evaluator version | So sánh các cấu hình |

Không đồng nhất request với model call. Một request có thể có hai lần gọi model do tool loop; một attempt có thể được retry ba lần; một evaluation case có thể chạy nhiều candidate và nhiều judge.

### Định danh cần giữ

Một result ledger nên có tối thiểu:

- runId, caseId, attemptId, requestId.
- pipelineVersion, promptVersion, modelConfigVersion.
- datasetVersion, rubricVersion, evaluatorVersion.
- operationType: chat, embedding, retrieval, tool, judge, telemetry.
- provider, model, region hoặc deployment alias.
- usage, unit, unitPrice, currency, priceVersion.
- startedAt, completedAt, status, traceId nếu có.

Các ID duy nhất nên lưu trong result store/ledger hoặc trace attributes đã được bảo vệ. Không đưa caseId, requestId, runId có cardinality cao vào labels Prometheus.

## 4. Công thức tổng chi phí

Một cách phân rã:

\[
C_{\mathrm{total}} =
C_{\mathrm{generation}} +
C_{\mathrm{embedding}} +
C_{\mathrm{retrieval}} +
C_{\mathrm{reranking}} +
C_{\mathrm{tools}} +
C_{\mathrm{evaluation}} +
C_{\mathrm{observability}} +
C_{\mathrm{infrastructure}}
\]

Trong đó:

- C_generation: mọi ChatModel calls trong request, bao gồm retry và follow-up sau tool.
- C_embedding: query embeddings và phần document embeddings được phân bổ.
- C_retrieval: vector DB, document store, search/read/index/storage.
- C_reranking: model hoặc dịch vụ rerank.
- C_tools: API, database, compute và dịch vụ ngoài do tool gọi.
- C_evaluation: judge/fact-check model và compute của evaluator.
- C_observability: ingest/index/retention telemetry.
- C_infrastructure: phần compute/network/storage của ứng dụng và các dịch vụ dùng chung.

Không cộng trùng một khoản. Ví dụ, nếu vector database invoice đã bao gồm storage và query units, không cộng thêm cùng khoản storage từ dashboard nội bộ. Nếu model provider đã tính cached input tokens theo một mức giá riêng, không tính chúng lần nữa như uncached input.

### Hai góc nhìn chi phí

**Direct cost** lấy từ usage và invoice theo hoạt động cụ thể. **Allocated cost** chia chi phí dùng chung theo quy tắc như số request, token, tenant share, CPU time hoặc dung lượng lưu trữ.

Nên báo cáo riêng:

\[
C_{\mathrm{observed}} = \sum C_{\mathrm{direct}}
\]

\[
C_{\mathrm{allocated}} = C_{\mathrm{observed}} + \sum C_{\mathrm{shared\ allocation}}
\]

Nếu chưa có invoice hoặc pricing source đáng tin cậy, đánh dấu estimated, partial hoặc unknown; không gọi một ước tính chưa đầy đủ là actual cost.

## 5. Tách chi phí ChatModel generation

Đây thường là khoản dễ thấy nhất trong ứng dụng AI, nhưng không chỉ là output token.

Một model call có thể tính theo:

- Input tokens: system/developer instructions, user prompt, retrieved context, tool definitions và lịch sử hội thoại.
- Output tokens: câu trả lời, reasoning token nếu provider tính phí riêng, hoặc dữ liệu tool-call được sinh ra.
- Cached input tokens: phần input được provider cache và áp dụng giá riêng.
- Image/audio/video hoặc modality khác: đơn vị tính có thể khác token văn bản.
- Model tier, region, batch/priority service và context window.

### Công thức token

Nếu bảng giá niêm yết theo một triệu token:

\[
C_{\mathrm{generation}} =
\sum_{i=1}^{N_{\mathrm{calls}}}
\frac{
T_{\mathrm{input},i}P_{\mathrm{input},i} +
T_{\mathrm{output},i}P_{\mathrm{output},i} +
T_{\mathrm{cached},i}P_{\mathrm{cached},i}
}{1{,}000{,}000}
\]

Trong công thức trên, `T_input` là số input tokens chưa được tính vào cached input; `T_cached` là cached tokens được billing tách riêng. Nếu provider báo tổng input đã bao gồm cached tokens, hãy trừ phần cached trước khi áp dụng công thức để tránh tính hai lần. Đơn giá phải dùng đúng loại token và đúng model/version/region.

Nếu provider tính theo đơn vị khác (ví dụ image, audio minute, request hoặc character), dùng công thức theo đơn vị billing của provider thay vì quy đổi tùy ý sang text token.

### Mỗi model call phải là một dòng usage

Ví dụ một request có:

1. Model call đầu để quyết định có cần tool.
2. Tool trả dữ liệu.
3. Model call thứ hai để tạo câu trả lời cuối.
4. Một retry model call vì timeout.

Tổng generation cost là tổng usage của cả bốn calls, kể cả call thất bại nếu provider đã tính phí. Không chỉ tính call cuối trả câu trả lời thành công.

## 6. Đọc usage từ Spring AI và provider

Spring AI có thể cung cấp usage metadata trong response của ChatModel. Với API/version cụ thể, response metadata có thể expose prompt/input tokens, generation/output tokens và total tokens. Tên method/type có thể khác theo version và provider adapter.

Ví dụ minh họa cách tiếp cận:

~~~java
ChatResponse response = chatModel.call(prompt);

Usage usage = response.getMetadata().getUsage();

if (usage != null) {
    Integer inputTokens = usage.getPromptTokens();
    Integer outputTokens = usage.getGenerationTokens();
    Integer totalTokens = usage.getTotalTokens();
    // Persist usage with model, provider, requestId and price version.
}
~~~

Đây là ví dụ khái niệm; hãy xác nhận import, kiểu số và API usage của Spring AI release đang dùng. Một số provider không trả đầy đủ usage, đặc biệt với streaming hoặc khi adapter chưa chuyển tiếp usage metadata. Khi thiếu dữ liệu, ghi null/unknown và điều tra provider options; không suy token chính xác từ độ dài ký tự.

### Ba nguồn dữ liệu cần đối chiếu

| Nguồn | Giá trị | Mức tin cậy |
|---|---|---|
| Response usage metadata | Usage theo từng model call | Tốt để liên kết với request nếu provider trả đủ |
| Provider usage/billing API | Tổng usage được provider ghi nhận | Đối chiếu invoice và usage ledger |
| Invoice/billing export | Số tiền thực bị tính | Nguồn đối soát tài chính |

Usage metadata là số đo của request; invoice là số liệu billing cuối cùng. Chúng có thể lệch do rounding, cache, retries, minimum charges, thời gian tổng hợp hoặc các hoạt động ngoài application.

## 7. Tách chi phí embedding khỏi chi phí sinh câu trả lời

Embedding là hoạt động biến văn bản thành vector. Trong RAG, có ít nhất hai loại embedding:

1. **Document embedding:** tạo vector cho tài liệu/chunk khi ingest hoặc re-index.
2. **Query embedding:** tạo vector cho câu hỏi khi người dùng tìm kiếm.

Hai loại có thời điểm và cách phân bổ chi phí khác nhau.

### Document embedding: chi phí offline

Ví dụ pipeline:

~~~text
Document source
  -> parse / clean
  -> split into chunks
  -> batch embedding
  -> vector index write
~~~

Chi phí ingest thường gồm:

- Token hoặc item dùng để embed tất cả chunks.
- Số batch/request đến embedding provider.
- Chi phí parse/OCR nếu có.
- Compute của worker và queue.
- Vector DB write/index/storage.
- Re-embedding khi đổi model, chunking hoặc dữ liệu.

Nếu ingest 100.000 chunks, không nên cộng toàn bộ chi phí đó vào mỗi request truy vấn. Hãy giữ ingestion ledger riêng, rồi phân bổ theo kỳ, tenant, tài liệu hoặc số lượt truy cập nếu business cần unit economics.

### Query embedding: chi phí online

Mỗi câu hỏi RAG có thể tạo một embedding cho query. Chi phí này thường nhỏ hơn generation nhưng tăng theo số query, retries, multi-query retrieval hoặc sub-question decomposition.

\[
C_{\mathrm{embedding}} =
\frac{T_{\mathrm{query}}P_{\mathrm{embedding}}}{1{,}000{,}000}
+ C_{\mathrm{document\ ingest\ allocation}}
\]

Nếu embedding provider tính theo item hoặc request, thay phần token bằng đơn vị billable tương ứng.

### Không tính embedding hai lần

Document embedding đã được ghi nhận trong pipeline ingest. Khi request chỉ truy vấn vector store, chỉ tính query embedding và retrieval cost của request. Phần document ingestion có thể được phân bổ như shared cost, nhưng phải có quy tắc và kỳ phân bổ rõ ràng.

## 8. Tách chi phí VectorStore và retrieval

VectorStore không đồng nghĩa với embedding provider. Một query có thể phát sinh chi phí database dù embedding được tính ở provider khác.

Các khoản có thể có:

- Query/search request.
- Read units hoặc compute units.
- Index/write/upsert/delete.
- Storage của vectors, metadata và payload.
- Replicas, backup, snapshots và retention.
- Network/data transfer.
- Dedicated cluster/node hoặc serverless capacity.

### Retrieval cost per request

Ví dụ một request có:

1. Một query embedding.
2. Một vector similarity search.
3. Một metadata fetch cho top-k chunks.
4. Một rerank call.

Hãy ghi riêng từng operation. Nếu hệ thống dùng hybrid search, có thể có cả vector query và keyword search. Nếu dùng multi-query retrieval, một request có thể phát sinh nhiều query.

### Phân bổ storage

Vector storage là shared cost. Có thể phân bổ theo:

- Bytes/vector hoặc số vectors của tenant.
- Số document/chunk được tenant sở hữu.
- Số query hoặc read units.
- Tỷ lệ sử dụng compute/capacity.

Không phân bổ chỉ theo request count nếu một tenant lưu hàng triệu vectors còn tenant khác lưu vài nghìn, trừ khi đây là quy tắc giá sản phẩm đã công bố.

## 9. Tách chi phí reranking

Reranking thường nhận câu hỏi và danh sách documents/chunks để sắp xếp lại theo relevance. Đây có thể là:

- Một API reranker tính theo số query-document pairs.
- Một ChatModel được dùng để chấm điểm relevance.
- Một model chuyên biệt tính theo token hoặc request.
- Một thuật toán nội bộ chạy CPU/GPU, không có hóa đơn API nhưng tiêu thụ compute.

Ghi rerankerProvider, rerankerModel, số candidate đầu vào, số kết quả giữ lại, usage và latency. Không gộp rerank vào embedding hay generation chỉ vì tất cả đều liên quan đến retrieval.

Một thay đổi từ top-k 5 lên top-k 20 có thể làm rerank tốn hơn, context dài hơn và generation input token tăng. Đánh giá cả ba khoản khi điều chỉnh retrieval.

## 10. Tách chi phí tool và API bên ngoài

Model tool calling và tool execution là hai hoạt động khác nhau:

- Model có thể phát sinh token để chọn tool, tạo tên tool và arguments.
- Ứng dụng thực thi tool, có thể gọi API/database/compute tính phí.
- Sau tool result, model có thể được gọi lại và phát sinh thêm token.

Không cộng tiền thực thi tool vào model token cost. Cũng không bỏ qua model token cost chỉ vì request được gọi là tool call.

### Công thức tool cost

\[
C_{\mathrm{tools}} =
\sum_{j=1}^{N_{\mathrm{tool\ calls}}}
\left(
C_{\mathrm{API},j} +
C_{\mathrm{compute},j} +
C_{\mathrm{data},j}
\right)
\]

Tùy nhà cung cấp, một tool call có thể được tính theo request, record, transaction, compute seconds, GB transfer hoặc tier subscription.

### Tool cost cần theo dõi

| Thuộc tính | Ví dụ |
|---|---|
| Tool name/version | get_order_status, inventory.lookup.v2 |
| Operation | read, search, calculate |
| Calls | số lần thực thi, kể cả retry |
| Status | success, timeout, denied, error |
| Duration | thời gian tool thực thi |
| Billable units | request count, records, compute time |
| Unit price | giá theo hợp đồng/API tier |
| External request ID | ID để đối soát provider nếu được phép |

Không lưu raw arguments/result có PII hoặc secret chỉ để tính chi phí. Phần lớn báo cáo cần tool name, operation class, status, duration và billable units đã chuẩn hóa.

### Retry và side effects

Retry một tool read-only có thể làm tăng API cost và latency. Retry một tool ghi dữ liệu có thể tạo side effect lặp lại nếu thiếu idempotency key. Phải tính cả các attempt bị lỗi nếu provider tính phí; lưu idempotency và retry policy để giải thích chênh lệch.
## 11. Tách chi phí evaluation và LLM-as-a-judge

Evaluation là một pipeline riêng, có thể tiêu thụ model và compute ngay cả khi ứng dụng candidate chỉ được gọi một lần.

Một evaluation run có thể gồm:

- Chạy candidate application trên mỗi case.
- Gọi model để sinh câu trả lời.
- Gọi model judge để chấm relevance, groundedness hoặc style.
- Gọi model fact-check để kiểm tra từng claim.
- Gọi embedding model để tính semantic similarity hoặc tìm evidence.
- Chạy deterministic evaluator bằng code.
- Chạy nhiều judge hoặc nhiều lượt adjudication khi kết quả bất đồng.

Phải phân biệt **candidate cost** và **evaluation cost**:

| Loại | Bao gồm | Dùng để trả lời |
|---|---|---|
| Candidate cost | Generation, query embedding, retrieval, tool | Tốn bao nhiêu để hệ thống thực hiện task? |
| Evaluation cost | Judge model, fact-check model, evaluation embeddings, evaluator compute | Tốn bao nhiêu để đo chất lượng candidate? |
| End-to-end experiment cost | Candidate + evaluation + shared run overhead | Tốn bao nhiêu để hoàn thành một thí nghiệm? |

Không gán judge token vào token usage của candidate. Nếu so sánh prompt A và B, judge cost phải được báo riêng; nếu không, một candidate có thể bị coi là đắt hơn chỉ vì evaluator gọi thêm một model.

### Công thức evaluation cost

\[
C_{\mathrm{evaluation}} =
C_{\mathrm{judge\ generation}} +
C_{\mathrm{fact\ check}} +
C_{\mathrm{evaluation\ embedding}} +
C_{\mathrm{deterministic\ compute}}
\]

Deterministic evaluator có thể không tạo model API bill, nhưng vẫn dùng CPU, memory và thời gian worker. Nếu dùng LLM-as-a-judge, ghi model/version, rubric version, input/output usage, số lượt judge và retries.

### Một case có thể bị đánh giá nhiều lần

Ví dụ:

1. Judge relevance.
2. Judge factual correctness.
3. Fact-check từng claim.
4. Adjudicator xử lý trường hợp hai judge bất đồng.

Đây là bốn hoạt động có thể phát sinh bốn lần model call. Có thể giảm chi phí bằng cách gộp tiêu chí vào một prompt judge nếu độ tin cậy vẫn đạt yêu cầu, hoặc dùng deterministic checks cho các điều kiện có thể xác minh bằng code.

Không dùng một điểm judge duy nhất làm bằng chứng cho mọi tiêu chí. Tối ưu chi phí evaluator phải giữ rubric, calibration, inter-rater agreement và hard gates.

## 12. Chi phí evaluation theo dataset và run

Khi chạy regression trên dataset, số case không phải yếu tố duy nhất quyết định ngân sách.

Các biến ảnh hưởng:

- Số lượng case và số candidate/prompt/model cần so sánh.
- Số attempt mỗi case do retry hoặc flaky provider.
- Số model calls trong mỗi attempt.
- Số judge và fact-check calls.
- Kích thước context/reference gửi vào evaluator.
- Số embedding operations.
- Tỷ lệ case được chọn để human review/adjudication.

Ước tính sơ bộ:

\[
C_{\mathrm{run}} \approx
N_{\mathrm{cases}} \times
N_{\mathrm{candidates}} \times
\left(
C_{\mathrm{candidate/case}} +
C_{\mathrm{judge/case}}
\right)
+ C_{\mathrm{shared}}
\]

Đây là mô hình ngân sách, không phải số tiền invoice. Dùng distribution thực tế của usage để dự báo tốt hơn; không chỉ nhân average nếu một số case có tool loop/context rất lớn.

### Chạy thử một mẫu trước khi chạy toàn bộ

Trước khi chạy 10.000 cases:

1. Chọn một tập pilot đại diện gồm case thường, case dài, RAG, tool, lỗi và boundary.
2. Đo usage và cost theo từng operation.
3. Tính median, p90/p95 và max usage/cost mỗi case.
4. Ước lượng tổng run theo phân bố case type.
5. Đặt budget cap và concurrency phù hợp.
6. Chạy batch nhỏ, so actual usage với dự báo rồi mới mở rộng.

Case khó hoặc có context lớn có thể tạo cost tail dài. Chỉ dùng average để lập budget dễ đánh giá thấp chi phí thực.

## 13. Chi phí telemetry và hạ tầng quan sát

Observability giúp tìm nguyên nhân suy giảm chất lượng, nhưng cũng có chi phí:

- Trace ingest, indexing, storage và retention.
- Log ingest, parsing, indexing và archive.
- Metrics storage, cardinality và query compute.
- Network transfer giữa app, Collector và backend.
- Collector CPU/memory, queue và replicas.
- Dashboard/query workloads.

Sampling trace giảm số spans được gửi, nhưng không thay thế redaction hoặc retention policy. Một trace được giữ vẫn có thể chứa payload lớn và nhạy cảm.

### Chi phí do cardinality

Metric label có giá trị duy nhất như requestId, caseId, userId hoặc raw prompt có thể tạo hàng triệu time series. Điều này làm tăng memory, index size, ingest và query cost.

Dùng low-cardinality dimensions như:

- application/service.
- environment/region.
- model/provider alias đã chuẩn hóa.
- operation type.
- task type.
- outcome/status class.

Giữ requestId, caseId, runId và traceId trong trace/result store có phân quyền, không làm metric labels.

### Tối ưu trace volume có chủ đích

- Sampling theo môi trường và risk.
- Tail sampling để ưu tiên lỗi/chậm nếu kiến trúc routing hỗ trợ.
- Filter attributes không cần thiết trước export.
- Không capture raw prompt/completion mặc định.
- Giới hạn retention theo nhu cầu điều tra và chính sách dữ liệu.
- Theo dõi dropped spans và exporter queue để không hiểu nhầm backend trống là hệ thống không lỗi.

## 14. Ví dụ tính chi phí một request

Giả sử một request RAG có một query embedding, một lần vector search, hai ChatModel calls do tool loop và một lượt judge. Các đơn giá sau **hoàn toàn giả định để minh họa phép tính**, không phải bảng giá của nhà cung cấp:

| Hoạt động | Usage | Đơn giá giả định |
|---|---:|---:|
| Chat input | 2.500 tokens | 2,00 USD / 1 triệu tokens |
| Chat output | 500 tokens | 8,00 USD / 1 triệu tokens |
| Query embedding | 40 tokens | 0,10 USD / 1 triệu tokens |
| Judge input | 1.500 tokens | 1,00 USD / 1 triệu tokens |
| Judge output | 200 tokens | 4,00 USD / 1 triệu tokens |
| Vector search | 1 query | Chưa có đơn giá |
| Tool API | 1 call | Chưa có đơn giá |

Generation:

\[
C_{\mathrm{chat}} =
\frac{2500 \times 2 + 500 \times 8}{1{,}000{,}000}
= \$0.009
\]

Query embedding:

\[
C_{\mathrm{embedding}} =
\frac{40 \times 0.10}{1{,}000{,}000}
= \$0.000004
\]

Judge:

\[
C_{\mathrm{judge}} =
\frac{1500 \times 1 + 200 \times 4}{1{,}000{,}000}
= \$0.0023
\]

Tổng phần model có thể tính:

\[
C_{\mathrm{known}} = 0.009 + 0.000004 + 0.0023
= \$0.011304
\]

Con số trên **chưa phải total request cost** vì chưa có đơn giá vector DB, tool API, document-ingest allocation, observability và infrastructure. Hãy báo cáo là known model cost/partial cost, không đổi nhãn thành total.

Nếu model call đầu và follow-up có usage khác nhau, tính từng call riêng rồi cộng; bảng trên đã gộp tổng usage chat để đơn giản hóa ví dụ.

## 15. Phân bổ chi phí document ingestion

Document embedding thường xảy ra trước request. Để tính unit economics, tổ chức có thể phân bổ chi phí ingest theo một kỳ hoặc vòng đời tài liệu.

Ví dụ:

- Tổng ingest cost của một tập tài liệu: 120 USD.
- Có 60.000 query trong kỳ phân bổ.
- Phần ingest cost phân bổ trung bình: 120 / 60.000 = 0,002 USD/query.

Đây chỉ là quy tắc phân bổ minh họa. Nó không có nghĩa mỗi query đã phát sinh một lần embedding tài liệu. Nếu query volume thấp hoặc tài liệu được sử dụng lâu dài, có thể chọn kỳ phân bổ theo tháng/quý hoặc theo tenant.

Một cách khác là phân bổ theo số chunk được tenant sở hữu:

\[
C_{\mathrm{tenant\ ingest}} =
C_{\mathrm{total\ ingest}}
\times
\frac{\mathrm{tenant\ chunks}}{\mathrm{all\ chunks}}
\]

Quy tắc phải được ghi trong cost ledger để có thể giải thích và đối soát. Khi re-index do thay embedding model hoặc chunk size, ghi một ingestion event/version mới; không ghi đè chi phí lịch sử.

## 16. Cost ledger: lưu một dòng cho mỗi hoạt động billable

Không nên chỉ lưu một trường totalCost trên request. Một ledger chi tiết cho phép truy vết từ số tiền về usage và bảng giá.

Ví dụ schema:

~~~yaml
costEvent:
  eventId: evt-000123
  requestId: req-000456
  runId: eval-run-2026-11-27-a
  caseId: rag-return-014
  attemptId: 1
  operationType: chat_generation
  provider: provider-a
  model: model-family-x
  usage:
    inputTokens: 2500
    outputTokens: 500
    cachedInputTokens: 0
  pricing:
    currency: USD
    unit: per_1m_tokens
    inputPrice: 2.00
    outputPrice: 8.00
    cachedInputPrice: null
    priceVersion: provider-price-2026-11
  amount:
    value: 0.009
    status: estimated
  traceId: 4bf92f3577b34da6a3ce929d0e0e4736
~~~

Đây là schema minh họa, không phải format billing chuẩn của Spring AI. amount.status nên phân biệt actual, estimated, partial và unknown. Không ghi credentials hoặc raw prompt trong cost ledger.

### Các trường nên có cho mọi operation

| Trường | Ý nghĩa |
|---|---|
| eventId | ID duy nhất của cost event |
| operationType | generation, embedding, retrieval, tool, judge, telemetry |
| owner IDs | request/task/attempt/run/tenant |
| provider/resource | provider, model, vector DB, tool hoặc service |
| usage + unit | Số lượng và đơn vị billing |
| unitPrice + currency | Đơn giá và tiền tệ |
| priceVersion | Phiên bản bảng giá/hợp đồng |
| amount + status | Số tiền và mức độ xác thực |
| timestamp | Thời điểm phát sinh |
| source | response usage, provider API, invoice hoặc allocation rule |

Nếu provider invoice tổng hợp theo ngày hoặc theo project thay vì request, có thể cần reconciliation job để ghép tổng usage/invoice với cost events. Đừng tạo cảm giác precision theo request khi nguồn chỉ có số tổng theo ngày.

## 17. Phân bổ cost về request, case, run và tenant

Một hoạt động có thể thuộc trực tiếp một request, nhưng chi phí dùng chung phải phân bổ.

| Cost event | Cách gắn |
|---|---|
| Chat generation | Request ID + model call ID |
| Query embedding | Request ID + embedding operation ID |
| Document embedding | Ingestion run + document/index version |
| Vector DB query | Request ID + operation count/units |
| Vector DB storage | Tenant/index share theo kỳ |
| Tool API | Request ID + tool execution ID |
| Judge call | Evaluation run + case + judge attempt |
| Evaluator compute | Evaluation run hoặc case theo worker time |
| Observability storage | Service/environment share, hoặc trace/log volume |
| App infrastructure | Service/tenant share theo CPU, memory, request hoặc capacity |

### Cost per successful task

Chỉ chia tổng chi phí cho số request thành công có thể che giấu chi phí retry và thất bại. Nên theo dõi:

\[
\mathrm{Cost\ per\ successful\ task} =
\frac{\mathrm{Total\ cost\ of\ all\ attempts}}
{\mathrm{Number\ of\ successful\ tasks}}
\]

Ví dụ, 100 attempts có 80 task thành công và tổng cost 12 USD:

\[
12 / 80 = \$0.15 \text{ per successful task}
\]

Đây là unit economics theo kết quả cuối. Đồng thời báo cost per attempt và failure rate để thấy phần lãng phí.

### Cost per 1,000 evaluation cases

\[
\mathrm{Cost/1{,}000\ cases} =
\frac{\mathrm{Evaluation\ run\ cost}}
{\mathrm{Cases\ evaluated}} \times 1000
\]

Khi so sánh run, giữ nguyên cách tính candidate/evaluator/shared allocation và ghi số case thực sự hoàn thành. Không so một run đã judge toàn bộ cases với run mới chỉ chạy candidate mà không ghi khác biệt.

## 18. Kết hợp chi phí với latency và throughput

Chi phí thấp không tự động có nghĩa hệ thống hiệu quả. Một model rẻ hơn nhưng chậm gấp ba hoặc làm tăng retry có thể làm cost per successful task cao hơn.

Các số đo cần đi cùng:

| Chỉ số | Câu hỏi |
|---|---|
| Cost per request | Một request trung bình tốn bao nhiêu? |
| Cost per successful task | Chi phí để hoàn thành đúng một task là bao nhiêu? |
| p50/p95/p99 latency | Người dùng chờ bao lâu và tail latency ra sao? |
| Time to first token (TTFT) | Streaming bắt đầu trả nội dung nhanh đến đâu? |
| Inter-token latency | Khoảng cách giữa các token có ổn định không? |
| Throughput | Hệ thống xử lý được bao nhiêu request/token mỗi giây? |
| Retry rate | Bao nhiêu operation phải thử lại? |
| Error rate | Bao nhiêu request/model/tool operation thất bại? |
| Quality score/hard gates | Câu trả lời có đúng và hành vi tool có an toàn không? |

### Không cộng p95 của từng span để ra p95 end-to-end

Latency các span có thể lồng nhau hoặc chạy song song. p95 của retrieval cộng p95 của model không bằng p95 của request. Đo end-to-end latency trực tiếp ở request; dùng trace waterfall để giải thích thành phần chậm.

### Throughput và concurrency

Concurrency cao có thể tăng throughput đến một ngưỡng, sau đó queueing, rate limits và provider throttling làm latency tăng. Thử nghiệm cần ghi concurrency, request mix, warm/cold cache, model/provider quota và tỷ lệ lỗi. So sánh hai model ở tải khác nhau không tạo kết luận công bằng.

## 19. Đo cost/quality frontier thay vì chọn model chỉ theo giá

Khi so sánh hai cấu hình, ghi cùng một dataset và rubric:

| Candidate | Quality pass rate | Cost/success | p95 latency | Hard gates |
|---|---:|---:|---:|---|
| Model A + prompt A | 96% | 0.12 USD | 1.8 s | Pass |
| Model B + prompt B | 92% | 0.07 USD | 1.2 s | Có 1 vi phạm |
| Model C + RAG tuned | 97% | 0.10 USD | 1.6 s | Pass |

Các số trong bảng là ví dụ giả định. Candidate B rẻ hơn và nhanh hơn nhưng có hard-gate violation, do đó không thể coi là thay thế tương đương. Candidate C có thể là lựa chọn tốt hơn nếu rubric, sample size và confidence phù hợp.

Một cấu hình nằm trên cost/quality frontier khi không có cấu hình khác vừa rẻ hơn vừa đạt chất lượng bằng hoặc cao hơn trong điều kiện tải tương đương. Cần đưa latency và hard gates vào quyết định, không chỉ quality average.

## 20. Theo dõi cost metrics mà không tạo cardinality cao

Có thể export các metric tổng hợp như:

- ai_cost_usd_total — tổng cost đã chuẩn hóa theo USD và loại operation.
- ai_tokens_total — token usage theo provider/model/token type.
- ai_model_calls_total — số model calls theo operation/status.
- ai_tool_calls_total — số tool calls theo tool/status.
- ai_evaluation_cases_total — số case theo outcome/dataset family.
- ai_request_duration_seconds — latency theo operation.

Đây là tên metric gợi ý do ứng dụng tự thiết kế, không phải metric mặc định Spring AI. Cần định nghĩa đơn vị, counter/gauge/histogram semantics, currency conversion và reset behavior.

### Labels phù hợp

| Nên dùng | Tránh dùng |
|---|---|
| service, environment, region | raw requestId |
| provider, normalized model alias | raw prompt/completion |
| operationType | caseId duy nhất |
| outcome/status class | userId/customerId |
| taskType/category có tập giá trị hữu hạn | external request ID không giới hạn |
| pipelineVersion theo release hữu hạn | arbitrary tool arguments |

Đừng dùng amount làm label; cost amount là value của metric hoặc ledger event. Với nhiều currency, ghi currency thành dimension có tập giá trị hữu hạn và quy đổi trong cost ledger/reporting layer theo FX source/time.
## 21. Tối ưu generation cost mà không làm giảm chất lượng

Các cách thường dùng:

### Giảm input tokens

- Loại lịch sử hội thoại không còn liên quan.
- Rút gọn system/developer instructions nhưng giữ nguyên hard constraints.
- Chỉ đưa retrieved chunks có relevance đủ cao vào context.
- Loại trùng lặp giữa các chunks và metadata.
- Giữ tool schema tối thiểu, rõ ràng và chỉ cung cấp tool cần thiết.
- Dùng prompt template có cấu trúc để tránh gửi lại nội dung dư thừa.

Không cắt context chỉ để giảm token nếu bằng chứng cần thiết bị loại. Đo factual correctness, groundedness và retrieval recall trên dataset trước/sau.

### Giảm output tokens

- Đặt output token budget phù hợp task.
- Yêu cầu format có giới hạn, ví dụ câu trả lời ngắn hoặc JSON schema.
- Không yêu cầu model lặp lại toàn bộ retrieved context.
- Dừng generation khi đã đạt mục tiêu, nếu provider/API hỗ trợ và semantics phù hợp.

Output quá ngắn có thể làm câu trả lời thiếu điều kiện hoặc bằng chứng. Theo dõi cả completeness và unsupported claims.

### Chọn model theo loại tác vụ

- Dùng model nhỏ cho classification, routing hoặc extraction đơn giản nếu chất lượng đủ.
- Dùng model mạnh hơn cho reasoning phức tạp hoặc case rủi ro cao.
- Route sang model khác khi confidence thấp hoặc task cần độ chính xác cao.
- Giữ cùng rubric và test set để so sánh model routing.

Model rẻ hơn chưa chắc rẻ hơn trên mỗi task thành công nếu phải retry hoặc sửa câu trả lời nhiều lần.

## 22. Tối ưu embedding và retrieval

Embedding cost và retrieval quality phụ thuộc số chunks, kích thước chunks, query strategy và tần suất re-index.

Các hướng tối ưu:

- Batch document embedding để giảm overhead request và tận dụng batch pricing nếu provider hỗ trợ.
- Deduplicate tài liệu/chunks trước khi embed.
- Chỉ re-embed documents thay đổi hoặc khi model/index version cần đổi.
- Chọn chunk size/overlap dựa trên recall, relevance và context budget.
- Cache query embeddings cho các truy vấn lặp lại nếu freshness và privacy cho phép.
- Giảm multi-query expansion khi không cải thiện retrieval.
- Dùng metadata filters để giới hạn search space.
- Đo top-k và reranking cost đồng thời với groundedness.

### Không tối ưu bằng cách giảm top-k một cách mù quáng

Top-k thấp có thể giảm vector read, rerank candidates và input tokens. Nhưng nếu bỏ mất evidence quan trọng, evaluator sẽ phát hiện factual correctness hoặc answer completeness giảm.

Thử các cấu hình k trên cùng dataset và ghi:

| Cấu hình | Retrieval recall | Input tokens | Cost/task | Quality pass |
|---|---:|---:|---:|---:|
| k=5 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| k=10 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| k=20 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |

Không điền số liệu ước đoán vào bảng benchmark. Lưu index version, chunking strategy, embedding model và filter để tái lập.

## 23. Tối ưu tool calling

Tool loop có thể làm tăng cả model calls lẫn API calls. Một số hướng:

- Giảm số tool definitions hiển thị cho model bằng routing theo task.
- Dùng schema ngắn và mô tả rõ input/output.
- Gộp các truy vấn read-only có thể thực hiện an toàn thành một tool operation.
- Chạy song song các tool độc lập khi semantics cho phép.
- Cache kết quả read-only có TTL phù hợp.
- Chặn tool calls lặp lại không có tiến triển.
- Giới hạn số vòng tool và tổng thời gian tool.
- Dùng timeout, circuit breaker và idempotency cho operation có side effect.

Gộp tool không được làm mất authorization boundary, auditability hoặc validation. Một tool lớn có quyền rộng có thể tiết kiệm một model round-trip nhưng làm tăng rủi ro bảo mật và chi phí sai sót.

### Theo dõi tool efficiency

Các chỉ số hữu ích:

- Tool calls per successful task.
- Tool retry rate.
- Tool timeout/error rate.
- Tool latency p50/p95.
- Billable units per operation.
- Tỷ lệ tool result thực sự được dùng trong câu trả lời cuối.

Tool được gọi nhưng kết quả không được dùng có thể chỉ ra prompt/tool selection kém. Đừng chỉ tối ưu số call; hãy đánh giá độ đúng của quyết định tool.

## 24. Tối ưu evaluator nhưng giữ chất lượng phép đo

Evaluation cũng cần được quản lý như một hệ thống có budget.

Các lựa chọn:

- Dùng deterministic checks cho schema, required fields, policy gates và tool authorization.
- Dùng judge model cho tiêu chí cần hiểu ngữ nghĩa.
- Chỉ fact-check claims có rủi ro hoặc được rubric yêu cầu.
- Gộp tiêu chí vào một judge call nếu độ tin cậy đã được kiểm chứng.
- Chạy adjudication cho trường hợp bất đồng hoặc gần ngưỡng.
- Dùng stratified sampling cho human review, giữ nguyên hard-gate cases.
- Cache kết quả evaluator chỉ khi input, rubric, judge model và evaluator version giống hệt.

### Cẩn thận với cache evaluator

Nếu prompt candidate, output, retrieved evidence hoặc rubric thay đổi, kết quả cũ không còn hợp lệ. Cache key phải bao gồm các version liên quan. Không tái sử dụng điểm judge của một output cho candidate khác.

Một evaluator rẻ nhưng bias theo model family hoặc rubric không ổn định có thể làm quyết định release sai. Đo calibration và agreement trên tập human-labeled trước khi mở rộng.

## 25. Cache: tiết kiệm cost và latency có điều kiện

Cache có thể áp dụng cho:

| Cache | Có thể tiết kiệm | Điều kiện cần kiểm soát |
|---|---|---|
| Exact response cache | Model generation | Cùng input/context/tenant/policy và dữ liệu còn fresh |
| Query embedding cache | Embedding calls | Cùng normalization, model và embedding version |
| Retrieval cache | Vector DB query | Index version, metadata filter, ACL và freshness |
| Tool result cache | API/database calls | Read-only semantics, TTL, authorization |
| Prompt prefix cache | Input token cost tùy provider | Prefix phải đúng điều kiện cache của provider |
| Evaluation cache | Judge calls | Cùng output, rubric, judge/evaluator version |

Cache hit có thể giảm latency và billable units, nhưng cache key thiếu tenant/ACL có thể trả nhầm dữ liệu. Cache stale có thể làm câu trả lời sai hoặc dùng trạng thái nghiệp vụ cũ. Đưa cache hit/miss và stale rate vào benchmark.

## 26. Batch, concurrency và retry

### Batch

Batching phù hợp với document embedding, evaluation cases và tác vụ offline. Batch có thể giảm overhead và tăng throughput, nhưng làm tăng thời gian chờ của từng item nếu batch phải đợi đủ kích thước.

Đo:

- Batch size.
- Batch wait time.
- Throughput items/tokens per second.
- Error/retry rate.
- Cost per item.

### Concurrency

Concurrency giúp tận dụng quota và compute nhưng có thể gây queueing hoặc rate limit. Tìm mức concurrency đạt throughput tốt mà vẫn giữ latency/error SLO.

### Retry

Retry chỉ nên dùng cho lỗi có thể phục hồi và cần backoff/jitter, maximum attempts và deadline tổng. Retry một request đã được provider tính phí vẫn làm cost tăng.

Không retry lỗi validation, authorization hoặc tool side effect không idempotent như thể đó là lỗi mạng. Lưu attempt count và reason để tính cost per successful task.

## 27. Budget và guardrails cho production

Một hệ thống cost-aware cần giới hạn cả cấp request lẫn cấp tenant/run:

- Max input/output tokens cho từng task type.
- Max model calls và max tool rounds mỗi request.
- Max retry attempts và tổng deadline.
- Max retrieved chunks/context budget.
- Max evaluator calls cho mỗi case/run.
- Quota theo tenant, API key hoặc project.
- Budget theo ngày/tháng và alert theo ngưỡng.
- Circuit breaker khi provider có lỗi hoặc cost vượt ngưỡng.
- Fallback model hoặc graceful degradation có kiểm tra chất lượng.

### Ví dụ policy giới hạn

~~~yaml
aiBudget:
  request:
    maxModelCalls: 4
    maxToolCalls: 3
    maxToolRounds: 2
    maxInputTokens: 12000
    maxOutputTokens: 1200
    maxDurationSeconds: 30
  evaluation:
    maxJudgeCallsPerCase: 2
    maxAttemptsPerCase: 2
  tenant:
    dailyBudgetUsd: 50
    alertThresholdPercent: 80
~~~

Đây là ví dụ cấu hình ứng dụng, không phải property chuẩn Spring AI. Giá trị phải dựa trên task risk, provider limits, product tier và SLO.

### Budget vượt ngưỡng thì làm gì?

Quy định hành vi trước:

1. Chặn request mới của tenant khi vượt hard limit nếu hợp đồng/product policy yêu cầu.
2. Cho phép task ưu tiên cao qua quota riêng nếu đã được cấp.
3. Giảm concurrency hoặc chuyển sang fallback model đã được đánh giá.
4. Trả response degraded/clear error thay vì tiếp tục tool/model loop vô hạn.
5. Giữ audit event và cost ledger để giải thích quyết định.

Không âm thầm đổi model hoặc bỏ bước fact-check trong một task rủi ro cao chỉ để giảm hóa đơn.

## 28. Dashboard cost và performance

Một dashboard vận hành hữu ích nên chia thành các góc nhìn:

| Panel | Metric/measure | Mục đích |
|---|---|---|
| Cost overview | Cost by operation/provider/model | Xác định nhóm chi phí tăng |
| Unit economics | Cost/request, cost/successful task | Theo dõi hiệu quả sản phẩm |
| Token usage | Input/output/cached tokens | Phát hiện prompt/context phình to |
| Embedding | Query/document tokens, batch count | Tách online query khỏi offline ingest |
| Tool | Calls, billable units, retry, latency | Phát hiện tool loop và API đắt |
| Evaluation | Judge tokens, cost/case, run cost | Lập ngân sách regression |
| Latency | p50/p95/p99 per operation và end-to-end | Xác định tail latency |
| Quality | Pass rate, factual correctness, hard gates | Không đánh đổi chất lượng âm thầm |
| Reliability | Error, timeout, retry, queue | Giải thích cost spike và latency |

### Drill-down nên theo thứ tự

1. Chọn environment và time range.
2. Chọn service/pipeline version.
3. Chọn operation type/provider/model alias.
4. Xem aggregate cost/usage và latency.
5. Mở result ledger theo request/run/case để xem hoạt động chi tiết.
6. Mở trace nếu trace đã được sample và lưu.

Metrics dashboard không cần chứa mọi request ID. Dùng ledger/trace để drill-down chi tiết, bảo đảm RBAC và privacy.

## 29. Quy trình benchmark cost-performance

Khi thay prompt, model, embedding model, top-k, reranker hoặc tool policy, chạy một benchmark có thể tái lập:

1. Khóa dataset, rubric và evaluation version.
2. Ghi candidate config: prompt, model, retriever, index, tools và cache policy.
3. Chọn request mix đại diện: simple, long context, RAG, tool, boundary, failure.
4. Cố định concurrency, region, quota và warm/cold cache conditions.
5. Thu usage từng model call, embedding operation, vector query, tool call và judge.
6. Thu end-to-end latency, per-operation latency, throughput, retry và error.
7. Chấm quality và hard gates bằng cùng evaluator/human calibration.
8. Tính direct cost, allocated cost, cost per successful task và cost per 1,000 cases.
9. So sánh confidence/variance, không chỉ average.
10. Đưa candidate lên cost/quality/latency frontier và quyết định theo SLO.

### Báo cáo so sánh cần giữ

| Nhóm | Trường |
|---|---|
| Reproducibility | datasetVersion, rubricVersion, candidateVersion |
| Model | provider, model, region, pricingVersion |
| Usage | input/output/cached tokens, embedding units, tool calls |
| Cost | generation, embedding, retrieval, tools, evaluator, infra |
| Performance | p50/p95/p99, TTFT, throughput, retry/error |
| Quality | relevance, factual correctness, groundedness, hard gates |
| Confidence | sample size, variance, CI hoặc human review notes |

Nếu giá provider thay đổi, lưu pricing version để so sánh lịch sử theo giá lúc chạy. Có thể tính thêm normalized cost theo bảng giá hiện tại để so hiệu quả kỹ thuật, nhưng phải giữ cả actual billed cost.

## 30. Bài thực hành: phân rã cost cho một evaluation run RAG

Giả sử một run có 200 cases, hai candidate prompt/model, RAG và một tool read-only. Mỗi candidate được judge bằng một LLM-as-a-judge; một số case có retry.

Thực hiện:

1. Tạo cost ledger event riêng cho mỗi ChatModel call, query embedding, vector query, tool execution và judge call.
2. Ghi riêng document ingestion cost và version của vector index.
3. Thu usage input/output/cached tokens từ provider response metadata.
4. Đối chiếu tổng usage với provider billing export khi có thể.
5. Ghi billable units của vector DB và tool API.
6. Tính evaluator cost riêng với candidate cost.
7. Phân bổ ingestion, storage và observability theo quy tắc đã công bố.
8. Tính cost per attempt, cost per successful task và cost per 1,000 cases.
9. Thu p95 end-to-end latency, tool latency, retrieval latency và retry rate.
10. Chấm relevance, factual correctness và hard gates.
11. So sánh hai candidate trên cùng dataset/rubric/concurrency.
12. Xác định candidate nào đạt quality gate với chi phí và latency phù hợp.

### Câu hỏi tự kiểm

**Câu 1:** Một request RAG có hai model calls vì tool loop. Generation cost tính một hay hai lần?

Tính từng model call theo usage thực tế rồi cộng; tool execution cost được ghi ở nhóm riêng.

**Câu 2:** Document embeddings đã tạo tuần trước. Request hôm nay chỉ query vector store. Có tính lại toàn bộ document embedding cost không?

Không. Chỉ tính query embedding và retrieval cost trực tiếp; document ingestion được lưu riêng hoặc phân bổ theo quy tắc.

**Câu 3:** Judge model tiêu thụ 2.000 input tokens. Có cộng vào candidate model token usage không?

Không. Đây là evaluation cost; báo riêng và có thể cộng vào tổng experiment cost.

**Câu 4:** Một candidate có cost/request thấp hơn nhưng factual correctness thấp hơn và hard gate fail. Có nên chọn không?

Không thể coi là tương đương. Candidate phải đạt quality/hard-gate requirements trước khi tối ưu cost.

**Câu 5:** Vì sao retry cần được tính vào cost per successful task?

Retry tạo thêm model/tool usage và có thể bị tính phí; bỏ qua nó sẽ đánh giá thấp chi phí hoàn thành task.

## 31. Checklist trước khi công bố cost-performance

- [ ] Đã phân rã generation, embedding, retrieval, reranking, tools, evaluation, telemetry và infrastructure.
- [ ] Tách document ingestion cost khỏi online query cost.
- [ ] Ghi usage theo từng model call, bao gồm retry và follow-up sau tool.
- [ ] Cached tokens được tính đúng loại giá và không double-count.
- [ ] Usage metadata được đối chiếu với provider usage/billing khi có thể.
- [ ] Bảng giá có currency, unit, region, model/version và effective date.
- [ ] Unknown/partial/estimated được gắn nhãn rõ ràng.
- [ ] Tool API cost tách khỏi model tool-call token cost.
- [ ] Judge/fact-check cost tách khỏi candidate cost.
- [ ] Shared storage/infra/observability có quy tắc phân bổ.
- [ ] Không cộng trùng khoản đã nằm trong invoice.
- [ ] Cost per successful task tính cả failed/retried attempts trong numerator.
- [ ] Latency, throughput, error, retry và quality được xem cùng cost.
- [ ] Hard gates và factual correctness không bị hy sinh để giảm giá.
- [ ] Metrics labels có cardinality thấp; chi tiết request nằm trong ledger/result store.
- [ ] Budget, quota, max model/tool rounds và retry limits được định nghĩa.
- [ ] Cache key bảo đảm tenant/ACL/freshness và version correctness.
- [ ] Benchmark giữ dataset, rubric, concurrency và candidate version có thể tái lập.

### Tài liệu chính thức để đối chiếu

- Spring AI Observability: https://docs.spring.io/spring-ai/reference/observability/
- Spring AI Chat Models: https://docs.spring.io/spring-ai/reference/api/chatmodel.html
- Spring AI Embeddings: https://docs.spring.io/spring-ai/reference/api/embeddings.html
- Spring AI Vector Stores: https://docs.spring.io/spring-ai/reference/api/vectordbs.html
- Micrometer Observation: https://docs.micrometer.io/micrometer/reference/observation.html
- OpenTelemetry GenAI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/

**Kết luận:** muốn biết một task AI thực sự tốn bao nhiêu, hãy tính từng hoạt động billable và giữ riêng chi phí candidate, evaluation, ingest và hạ tầng dùng chung. Dùng usage thực, bảng giá có version và ledger có thể đối soát; kết hợp cost với latency, throughput, retries và quality gates. Khi đó nhóm có thể tối ưu prompt, model, retrieval, tool và evaluator mà vẫn giải thích được chất lượng cũng như chi phí của từng phiên bản.
