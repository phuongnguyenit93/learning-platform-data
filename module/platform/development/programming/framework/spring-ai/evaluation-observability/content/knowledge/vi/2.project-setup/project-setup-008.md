# Ghi lại phiên bản để tái lập thí nghiệm

> **Chương:** Thiết lập dự án
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí, độ trễ để nhận diện nguyên nhân suy giảm chất lượng theo phiên bản prompt, model và pipeline.
>
> **Nền tảng minh họa:** Java 21, Spring Boot 4.2.x và Spring AI 2.1.x. Các phiên bản cụ thể trong ví dụ là **giá trị mẫu**; thí nghiệm thực phải ghi lại đúng bản đã triển khai. Bài này tập trung vào phương pháp tái lập, không yêu cầu gọi nhà cung cấp model hoặc sửa hạ tầng sản xuất.

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

1. Phân biệt **lặp lại một lần chạy**, **tái lập kết quả**, **truy nguyên nguồn gốc** và **so sánh có kiểm soát** trong ứng dụng AI.
2. Xác định những phiên bản cần ghi khi đánh giá câu trả lời, RAG, tool calling và mô hình chấm điểm.
3. Tạo **run manifest** và **case result** có schema rõ ràng, gắn nguồn dữ liệu với checksum, Git commit và cấu hình được phép lưu.
4. Kiểm tra trước khi chạy rằng dataset, corpus/index, prompt, rubric và môi trường khớp baseline.
5. Thiết kế thử nghiệm A/B thay đổi có chủ đích và báo cáo sự khác biệt về relevance, fact checking, token, chi phí, độ trễ.
6. Nhận ra giới hạn của `temperature=0`, seed và model ID khi sử dụng dịch vụ LLM từ xa.

### Tình huống xuất phát

Ngày thứ Hai, trợ lý RAG trả lời đúng 93/100 câu. Ngày thứ Năm, cùng lệnh chạy chỉ đúng 86/100. Nếu không ghi lại phiên bản, nhóm có thể đặt ra nhiều giả thuyết nhưng khó kiểm chứng: liệu corpus đã bổ sung tài liệu, vector index được tái dựng, model provider đổi backend, prompt có thêm một câu, judge được nâng cấp, hay đơn giản là một số request trả lỗi và bị tính thành `FAIL`?

Giải pháp không chỉ là lưu một tên model. Cần lưu **một bản mô tả đầy đủ điều kiện thí nghiệm**, cùng **dấu vết kết quả từng tình huống** và **khả năng kiểm tra tính toàn vẹn** của những artifact liên quan.

## 2. Ba mức độ có thể gọi là “tái lập”

| Mức | Kỳ vọng | Khi nào khả thi? |
|---|---|---|
| **Tái hiện chính xác dữ liệu đầu vào** | Cùng câu hỏi, prompt sau render, danh sách context/tool output và cấu hình | Khả thi nếu đã snapshot dữ liệu, version và hash đầy đủ |
| **Tái chạy cùng workflow** | Dùng cùng mã, dependency, pipeline, endpoint, model ID, dataset/index và rubric | Khả thi về mặt quy trình, nhưng output LLM hosted có thể khác |
| **Tái tạo cùng chất lượng thống kê** | Kết quả tổng hợp gần baseline trong khoảng dao động đã biết | Đòi hỏi đủ mẫu, kiểm soát biến, lặp lại chạy và định nghĩa sai số |

**Không đồng nhất ba mức trên.** Ngay cả khi `temperature=0`, lời gọi LLM qua API vẫn có thể trả khác do version model được provider cập nhật, thay đổi hạ tầng, độ chính xác số, chính sách an toàn, caching hoặc hành vi sampling. Một seed do provider hỗ trợ có thể giúp ổn định nhưng không luôn bảo đảm **bit-for-bit deterministic**.

Trong một kiểm thử offline với fake model, ta có thể kỳ vọng JSON output chính xác. Với thí nghiệm live model, nên đặt mục tiêu **điều kiện chạy được kiểm chứng và kết quả có thể so sánh** thay vì đòi mọi token đầu ra không đổi.

### Bốn thuật ngữ nên thống nhất

- **Reproducibility (tái lập):** đội khác có thể dùng mô tả, artifact và môi trường phù hợp để tái chạy quy trình và kiểm tra kết luận.
- **Repeatability (lặp lại):** cùng nhóm thực hiện lại dưới điều kiện gần như không đổi, kiểm tra sự dao động.
- **Traceability (truy nguyên):** từ một verdict tìm ra câu hỏi, context, generator, judge, phiên bản và traces có liên quan.
- **Auditability (khả năng kiểm toán):** có bằng chứng ai thay dataset/rubric, khi nào triển khai, dữ liệu nào đã dùng và tiêu chí quyết định được áp dụng.

## 3. Hãy xác định “đơn vị thí nghiệm” trước khi ghi version

Một **run** là một lần thực thi trên tập case xác định bằng cùng chính sách, mã và cấu hình được chốt trước. Một **case attempt** là một lần thực thi một tình huống; retry là attempt mới chứ không âm thầm ghi đè.

~~~mermaid
flowchart TD
  A["Run manifest: cấu hình đã khóa"] --> B["Dataset revision + case IDs"]
  B --> C["Case attempt: câu hỏi, context, tool results"]
  C --> D["Generator output và trạng thái kỹ thuật"]
  D --> E["Scoring: deterministic + LLM judge"]
  E --> F["Case result: PASS/FAIL/ERROR"]
  D --> G["Metrics + traces + token/cost"]
  E --> G
  F --> H["Run report + baseline comparison"]
  G --> H
~~~

Có hai đường ghi dữ liệu khác nhau:

1. **Report của thí nghiệm:** ghi những artifact và verdict có version, phục vụ so sánh.
2. **Observability:** ghi các hoạt động vận hành (duration, errors, token usage, traces) để xác định nguyên nhân.

Một trace ID có thể giúp tìm request trong backend observability, nhưng **không thay cho run manifest**: traces có sampling, retention và có thể bị xóa sau một khoảng thời gian.

## 4. Ma trận phiên bản phải đóng băng

| Nhóm | Những gì cần ghi | Nếu thay mà không ghi sẽ gây gì? |
|---|---|---|
| **Mã nguồn** | Git commit, trạng thái working tree, build artifact ID/hash | Không biết logic nào đã chạy |
| **Runtime** | Java version/vendor, OS/architecture cần thiết, container image digest | Sự khác biệt thư viện/runtime hoặc hạ tầng bị bỏ sót |
| **Dependency** | Spring Boot, Spring AI BOM, resolved dependencies, build plugins | Một dependency transitively được nâng mà không được nhận ra |
| **Generator** | Provider, model ID/deployment, tùy chọn request, model revision nếu provider có trả | Kết quả sinh bị gán sai cho prompt |
| **Judge** | Provider/model, rubric/prompt chấm, parsing schema, thresholds, calibration revision | Điểm PASS/FAIL đổi dù answer không đổi |
| **Prompt** | Template revision + content hash, hệ thống/role messages, tham số render | Thí nghiệm tưởng giữ nguyên prompt nhưng thực chất khác |
| **Dataset** | Dataset ID/revision/hash, split, số case, ground-truth label revision | Mẫu số và nhãn chấm không còn giống |
| **RAG corpus** | Document snapshot, IDs, versions, chunking config, embedding model | Cùng câu hỏi nhưng truy xuất từ dữ liệu khác |
| **Retriever/index** | Vector store, collection/schema, index build ID, top-k, filter, reranking version | Không xác định lỗi từ retrieval hay generator |
| **Tool calling** | Tool schema/version, sandbox fixtures, API contract, quyền và output snapshot | Hai lần test đang gọi các tool khác nhau |
| **Evaluation pipeline** | Scorer logic, aggregation policy, pass threshold, failure classifications | Tỷ lệ pass không còn so sánh được |
| **Telemetry** | Environment, observation schema, sampling, exporter config version | Metrics/traces đổi format hoặc chỉ còn mẫu lấy ngẫu nhiên |
| **Chi phí** | Token categories, đơn giá và ngày áp dụng, currency, cache/retry policy | So sánh giá sai khi bảng giá/provider đổi |

**Không cần đưa giá trị secret vào bảng phiên bản.** Chỉ ghi alias/phiên bản secret và identity role nếu cần kiểm toán, không ghi password, API key, bearer token, authorization header hoặc DSN chứa credentials.

## 5. Phiên bản mã nguồn và dependency

### 5.1. Commit không đủ nếu working tree còn thay đổi

Ví dụ commit `abc123` là baseline, nhưng đang có một thay đổi chưa commit trong lớp `RetrievalAdvisor`. Nếu chỉ lưu commit ID, khi tái chạy sẽ lấy mã cũ, không phải logic đã dùng.

Những trường cần ghi:

~~~yaml
source:
  repository_alias: ai-quality-lab
  git_commit: "example-full-commit-sha"
  git_dirty: false
  build_artifact_digest: "sha256:replace-with-real-image-or-jar-digest"
~~~

`git_dirty=true` nghĩa là working tree có thay đổi không được commit. Với regression/release baseline, nên yêu cầu `git_dirty=false` hoặc lưu artifact patch/digest có kiểm soát; **không** tự động đính kèm diff nếu nó có thể chứa secrets.

Trong project thực hành, lệnh minh họa:

~~~bash
git rev-parse HEAD
git status --porcelain
java -version
./mvnw -version
./mvnw dependency:tree
~~~

Lệnh `git status --porcelain` không in nội dung diff, nhưng có thể hiện đường dẫn file nhạy cảm; kiểm tra trước khi đưa stdout vào report công khai. Các lệnh ở đây là **hướng dẫn người học**, không phải lệnh được thực thi trên workspace của nhiệm vụ này.

### 5.2. BOM và resolved graph là hai thông tin khác nhau

Spring AI BOM giúp quản lý **phiên bản module Spring AI**, còn Spring Boot dependency management kiểm soát nhiều dependency framework. Tuy nhiên version khai báo trong BOM không phải lúc nào cũng chứng minh **bản JAR thực được chọn** khi có override hoặc nhiều BOM.

Cần ghi:

~~~yaml
framework:
  java: "21"
  spring_boot: "4.2.0"
  spring_ai_bom: "2.1.0"
  maven_wrapper_version: "record-actual-version"
  resolved_dependency_graph_sha256: "sha256:real-digest-of-normalized-dependency-output"
~~~

**Giới hạn:** checksum của `dependency:tree` phụ thuộc cách chuẩn hóa output, thứ tự và thông tin môi trường. Nếu lưu nguyên output, lưu thành artifact có content hash rồi tham chiếu vào manifest; **định dạng hóa hoặc chuẩn hóa phải ổn định** trước khi so checksum.

Khi dùng Gradle, có thể ghi `dependencies`, `dependencyInsight` và **dependency locking** nếu workflow sử dụng; không giả định chỉ đặt `platform(...)` đồng nghĩa toàn bộ transitive dependency đã được khóa tuyệt đối.

### 5.3. Plugin và container cũng cần version

Ví dụ CI chạy cùng source nhưng khác build plugin/JDK có thể tạo ra artifact khác. Ghi **build tool/wrapper**, toolchain Java, profile active, container image **digest** (không chỉ tag `latest`) và revision của deployment/charts khi chúng ảnh hưởng config.

Tránh ghi OS hostname, tài khoản cá nhân, internal IP/secret path không cần thiết vào một report chia sẻ rộng rãi. Mục tiêu là ghi **đủ biến giải thích** thay đổi, không thu thập mọi thông tin máy.

## 6. Phiên bản model: requested ID khác resolved version

Một application có thể gửi `model="provider-model-alias"`. Provider có thể định tuyến alias đó tới một revision cụ thể và thay revision theo thời gian.

Vì vậy ghi riêng:

| Trường | Ý nghĩa |
|---|---|
| `provider` | Nhà cung cấp hoặc gateway/serving stack |
| `requested_model_id` | Giá trị được cấu hình trong request |
| `resolved_model_version` | Revision/deployment thực trả về **nếu provider cung cấp** |
| `api_version` | Phiên bản API khi endpoint yêu cầu |
| `endpoint_region` | Region/serving deployment khi cần so latency |
| `options` | Temperature, top-p, token limit, tool choice, seed nếu hỗ trợ |
| `system_prompt_revision` | Bản chỉ dẫn hệ thống của generator/judge |
| `response_metadata` | Usage, finish reason, model info được phép lưu |

Ví dụ:

~~~yaml
models:
  generator:
    provider: provider-A
    requested_model_id: "generator-alias"
    resolved_model_version: null  # Provider không trả => ghi null, KHÔNG bịa revision
    temperature: 0.2
    top_p: 1.0
    max_output_tokens: 800
    seed: null                    # Chỉ dùng nếu provider/model hỗ trợ
    account_alias: "staging-generator-project"
  judge:
    provider: provider-B
    requested_model_id: "judge-revision-id"
    resolved_model_version: null
    temperature: 0.0
    account_alias: "staging-judge-project"
~~~

Model options ở trên là **ví dụ cấu hình thí nghiệm**, không phải mọi API/model đều hỗ trợ tất cả tham số. Một số reasoning models có hạn chế riêng về temperature/max tokens/seed; phải lưu **những option thực sự gửi** và không gửi tham số không được hỗ trợ.

### Không thể tái lập chính xác mọi hosted LLM

Ngay cả khi các trường trên đều khớp, provider có thể không cho truy cập lại model revision cũ hoặc thay đổi chính sách nội bộ. Khi đó nên:

1. Ghi nhận **mức tái lập khả thi**: cùng điều kiện yêu cầu hay cùng serving revision.
2. Lưu **execution snapshot** của lần chạy gốc để chấm lại mà không gọi generator.
3. Dùng **dataset có nhãn người**, nhiều lần chạy hoặc confidence interval để đo dao động.
4. Không tuyên bố “cùng model” khi chỉ biết alias mà không biết resolved version.

## 7. Prompt phải ghi cả bản mẫu và nội dung sau render

Trong một ứng dụng RAG, prompt không chỉ là tệp template. Prompt cuối cùng thường gồm:

~~~text
system_template + system_variables
user_template + question
retrieved_context_after_filter/rerank/truncation
conversation_history (nếu có)
tool_descriptions_and_schema (nếu có)
model_options
~~~

Một file template có hash giữ nguyên nhưng context được truy xuất khác sẽ tạo ra request khác. Vì vậy nên tách:

- **Prompt template revision:** Git commit/path/content hash.
- **Prompt render policy:** định dạng ghép context, separator, escape, token truncation, history window.
- **Rendered prompt fingerprint:** hash của bytes cuối cùng **khi được phép xử lý/lưu**, không cần đưa raw nội dung vào report công khai.
- **Evidence snapshot reference:** ID/URI có phân quyền và checksum của đúng context thực sự đưa vào model.

Ví dụ:

~~~yaml
prompts:
  generator:
    template_id: "answer-from-context"
    template_revision: "v7"
    template_sha256: "sha256:replace-with-real-template-digest"
    render_policy_revision: "render-v3"
    rendered_request_sha256: "sha256:restricted-runtime-fingerprint"
  judge:
    template_id: "factuality-judge"
    template_revision: "v2"
    template_sha256: "sha256:replace-with-real-rubric-prompt-digest"
~~~

**Checksum không che được thông tin bí mật của văn bản có entropy thấp.** Nếu nội dung có thể bị đoán trước (ví dụ câu trả lời yes/no hoặc một ID ngắn), hash không được coi là ẩn danh hóa. Với dữ liệu nhạy cảm, cân nhắc HMAC có khóa quản lý riêng hoặc chỉ lưu reference tới kho được bảo vệ; không đưa HMAC key vào report.

## 8. Dataset version: từ case đến ground truth

Dataset evaluation nên là **artifact bất biến** sau khi chốt run, có danh sách ID ổn định và split rõ ràng.

### Ví dụ manifest của bộ tình huống

~~~yaml
dataset:
  dataset_id: "vi-rag-regression"
  revision: "v5"
  schema_version: 2
  content_sha256: "sha256:replace-with-actual-file-digest"
  case_count: 120
  split: "regression-held-out"
  labels_revision: "human-reviewed-v3"
  source_snapshot: "policy-corpus-2026-11"
  pii_policy: "synthetic-and-approved"
  tags:
    - rag
    - tool
    - no_context
~~~

Nếu có 120 case ở run A và 117 ở run B mà vẫn gọi cả hai là “dataset v5”, tỷ lệ PASS không còn đối chiếu công bằng. Runner cần **đếm case, validate ID không trùng, kiểm checksum và split** trước khi chạy.

### Case JSONL có expected outcome

~~~jsonl
{"id":"rag-001","scenario":"rag","question":"Hạn nộp báo cáo tháng?","expectedDocumentIds":["policy-v3-chunk-07"],"expectedClaims":["Trước ngày 05 tháng kế tiếp"],"expectAbstention":false}
{"id":"rag-002","scenario":"no_context","question":"Ai đã duyệt tài liệu chưa công bố X?","expectedDocumentIds":[],"expectedClaims":[],"expectAbstention":true}
{"id":"tool-003","scenario":"tool","question":"Trạng thái đơn giả lập TEST-003?","expectedToolCalls":[{"name":"getOrderStatus","arguments":{"orderId":"TEST-003"}}],"expectedClaims":["Đang vận chuyển"]}
~~~

JSONL trên là **fixture minh họa**, không phải dữ liệu đã benchmark. Nhãn `expectedClaims`, `expectedDocumentIds` và expected tool arguments chỉ dành cho test runner, **không lộ cho generator** dưới dạng gợi ý trong prompt.

### Version nhãn cũng phải riêng

Một case có thể giữ nguyên câu hỏi nhưng được sửa ground truth sau khi chuyên gia phát hiện một chính sách mới. Khi đó:

- **Question revision** có thể không đổi.
- **Label revision** đã thay đổi và phải được ghi nhận.
- **Corpus snapshot** có thể cần cập nhật theo chính sách hiệu lực mới.
- Baseline cũ phải được phân loại lại hoặc báo “không tương đương”; không im lặng cộng chung.

Các split train/dev/regression/holdout nên được quản lý rõ để tránh **overfitting vào tập regression** khi đội liên tục tinh chỉnh prompt trên chính các case đang dùng để báo quality.

## 9. RAG cần đóng băng corpus, embedding và index

Một lời gọi RAG thường đi qua embedding query, vector search, filter, reranking, chunk selection và context assembly. Nếu một trong các bước thay đổi, answer có thể khác dù generator model giống nhau.

| Biến RAG | Version hoặc cấu hình cần lưu |
|---|---|
| Source corpus | Document IDs, source version, snapshot/build time, content hash |
| Parser/preprocessing | Parser/chunk cleaning revision, encoding/normalization |
| Chunking | Chunk size, overlap, splitting algorithm, metadata |
| Embedding | Model provider/model ID, chiều vector, config, revision |
| Vector storage | Engine, collection/index/table name, schema và build ID |
| Retrieval | Similarity threshold, top-k, filters, hybrid weighting |
| Reranker | Model/algorithm, parameters, selection policy |
| Context assembly | Thứ tự chunks, truncation, token budget, deduplication |
| Runtime evidence | Chính `retrieved_document_ids` và context đã đưa vào prompt |

### Ví dụ cấu hình và snapshot

~~~yaml
retrieval:
  corpus_revision: "policy-corpus-v8"
  chunker_revision: "recursive-split-v3"
  chunk_size: 800
  chunk_overlap: 100
  embedding:
    model_id: "embedding-model-id"
    dimension: 1536
  vector_store:
    engine: pgvector
    index_revision: "policy-pgvector-build-20261127"
  search:
    top_k: 5
    filter_revision: "active-policy-only-v2"
    reranker_revision: "none"
  context_assembly_revision: "context-layout-v4"
~~~

**Dimension 1536 và các giá trị khác là ví dụ.** Phải đọc chiều vector, embedding model và index build thực tế. Không thể giả định đổi embedding model mà không rebuild index vẫn cho kết quả so sánh được.

### Giữ context đúng như generator đã thấy

Nếu run A dùng chunks `[A, B, C]` nhưng khi chấm lại judge tự gọi vector store và nhận `[A, D, E]`, kết quả fact checking bị thay đổi bởi **evidence mới**.

Quy trình đúng:

1. Retrieval thực thi một lần cho một attempt.
2. Lưu danh sách chunks **sau rerank và truncation** (hoặc reference bảo vệ + hash).
3. Generator nhận đúng những chunks ấy.
4. `EvaluationRequest` của judge nhận **cùng evidence**.
5. Muốn chấm lại sau này, đọc execution snapshot chứ không âm thầm chạy lại retrieval.

Để đánh giá riêng **retrieval recall@k**, vẫn cần ground-truth source IDs trong dataset; đừng dùng chỉ lời chấm của judge để kết luận retriever đã tìm đúng.

## 10. Tool calling: version schema, kết quả và side effect

Khi trợ lý gọi công cụ, cần phân biệt **hợp đồng công cụ** và **thời điểm/dữ liệu mà công cụ trả về**.

Ví dụ `getOrderStatus(orderId)` có thể đổi schema từ `status: "IN_TRANSIT"` sang `deliveryState: "moving"`. Nếu không ghi schema revision, một lần nâng tool có thể bị quy nhầm thành model gọi sai tham số.

~~~yaml
tools:
  registry_revision: "tools-v4"
  fixtures_revision: "sandbox-orders-v2"
  allowed_environment: "staging"
  contracts:
    - name: getOrderStatus
      schema_revision: "v2"
      mode: sandbox
  capture_policy:
    record_tool_name: true
    record_normalized_arguments: true
    record_redacted_output: true
    redact_personal_data: true
~~~

Một attempt dùng tool cần lưu:

~~~json
{
  "tool": "getOrderStatus",
  "schemaRevision": "v2",
  "request": {"orderId": "TEST-003"},
  "result": {"status": "IN_TRANSIT"},
  "resultFixtureRevision": "sandbox-orders-v2",
  "status": "SUCCESS"
}
~~~

Các giá trị là fixture giả. Với tool có side effect, **không replay trực tiếp một request ghi dữ liệu production** để cố tái lập; dùng mock/sandbox, idempotency key và approval cần thiết. Nếu tool trả dữ liệu theo thời gian thực (giá, tồn kho, trạng thái đơn), cần lưu snapshot hoặc ít nhất thời điểm/response version được phép lưu.

**Deterministic tool assertions** nên chấm tên tool, arguments đã chuẩn hóa và thứ tự/nhiều lần gọi khi nghiệp vụ yêu cầu. Judge LLM dùng để đánh giá cách diễn giải, **không thay thế** assertion cho contract có thể so bằng code.

## 11. Judge và rubric là một phần của phiên bản thí nghiệm

Một bộ evaluator có thể gồm:

- **Relevance:** answer có liên quan question/context không?
- **Fact checking/groundedness:** các claim có được đúng evidence hỗ trợ không?
- **Abstention:** từ chối phù hợp khi thiếu tài liệu?
- **Tool behavior:** gọi đúng tool/arguments, có mô tả kết quả đúng?

Trong Spring AI, `RelevancyEvaluator` và `FactCheckingEvaluator` là các cách triển khai phổ biến; `EvaluationRequest` giữ câu hỏi, document context và answer. Khi thay **judge model** hoặc **rubric prompt**, pass rate có thể đổi dù generator answer vẫn y hệt.

Vì vậy ghi:

~~~yaml
evaluation:
  policy_revision: "quality-policy-v3"
  criteria:
    - relevance
    - fact_check
    - abstention
    - tool_assertions
  judge:
    provider: "provider-B"
    model_id: "judge-model-id"
    rubric_revision: "judge-rubric-v4"
    rubric_sha256: "sha256:actual-rubric-digest"
    output_schema_revision: "judge-verdict-json-v2"
    temperature: 0.0
    calibration_set_revision: "human-labels-v3"
  aggregation:
    rule: "all-mandatory-checks-pass"
    threshold_revision: "gate-v2"
    error_policy: "never-coerce-error-to-fail"
~~~

### Chấm lại cùng snapshot để phát hiện judge drift

Ví dụ thực nghiệm:

~~~text
Recorded answer A, recorded evidence E
  -> Judge J1, rubric R1 -> PASS
  -> Judge J2, rubric R1 -> FAIL
~~~

Kết luận **chưa phải** “generator xấu đi”. Đó là bất đồng giữa hai judge. Cần:

1. Dùng cùng snapshot answer/evidence để giảm biến nhiễu.
2. So theo bộ nhãn do con người chấm và xem false pass/false fail.
3. Lưu cả hai assessment, mỗi assessment có `judge_version` và `rubric_revision`.
4. Nếu đổi judge giữa baseline và candidate, hoặc **chấm lại cả hai bằng judge mới**, hoặc báo hai kết quả **không so trực tiếp**.

Với bài toán rủi ro cao, nên có quy trình human review; một verdict `isPass()==true` không bảo đảm correctness tuyệt đối.

## 12. Run manifest: hợp đồng tối thiểu cho một lần chạy

Mỗi lần chạy nên tạo một tệp manifest có schema/version và lưu cùng report. Ví dụ `reports/runs/eval-staging-20261127-001/manifest.yml`:

~~~yaml
schema_version: 1
run_id: "eval-staging-20261127-001"
created_at_utc: "2026-11-27T12:00:00Z"
environment: staging
purpose: "compare-prompt-v7-to-v8"

source:
  repository_alias: "ai-quality-lab"
  git_commit: "replace-with-full-git-sha"
  git_dirty: false
  artifact_digest: "sha256:replace-with-real-digest"

runtime:
  java_version: "21"
  spring_boot_version: "4.2.0"
  spring_ai_bom_version: "2.1.0"
  resolved_dependencies_digest: "sha256:replace-with-real-digest"
  deployment_image_digest: "sha256:replace-with-real-digest"

dataset:
  id: "vi-rag-regression"
  revision: "v5"
  content_digest: "sha256:replace-with-real-digest"
  case_count: 120
  labels_revision: "human-reviewed-v3"
  split: "regression-held-out"

generator:
  provider: "provider-A"
  requested_model_id: "generator-model-id"
  resolved_model_version: null
  prompt_revision: "answer-v7"
  prompt_digest: "sha256:replace-with-real-digest"
  temperature: 0.2
  max_output_tokens: 800

rag:
  corpus_revision: "policy-corpus-v8"
  embedding_model: "embedding-model-id"
  index_revision: "pgvector-build-v12"
  retrieval_top_k: 5
  reranker_revision: "none"
  context_assembly_revision: "context-layout-v4"

tooling:
  registry_revision: "tools-v4"
  fixture_revision: "sandbox-tools-v2"
  side_effect_policy: "sandbox-only"

evaluation:
  judge_provider: "provider-B"
  judge_model_id: "judge-model-id"
  rubric_revision: "rubric-v4"
  rubric_digest: "sha256:replace-with-real-digest"
  scoring_policy_revision: "quality-policy-v3"
  calibration_revision: "human-labels-v3"

execution:
  concurrency: 2
  timeout_seconds: 30
  max_retries: 1
  ordering: "case-id-ascending"

telemetry:
  service_name: "ai-quality-lab-staging"
  observation_schema_revision: "obs-v2"
  trace_sampling_probability: 1.0
  trace_export_destination_alias: "staging-traces"

cost:
  currency: USD
  pricing_revision: "provider-rates-2026-11-27"
  input_token_price_per_million: null
  output_token_price_per_million: null
  estimation_policy: "only-when-usage-and-price-known"

security:
  credential_reference_alias: "staging-evaluation-worker"
  contains_secret_values: false
  dataset_access_policy: "approved-synthetic-only"
~~~

**Đây là schema tham khảo**, không phải một built-in Spring AI manifest. Các khóa `source`, `generator`, `evaluation`, `telemetry`... chỉ có hiệu lực nếu project viết runner/validator/report writer đọc chúng. Thông tin có dạng `replace-with-...` phải được điền bằng giá trị kiểm chứng được; không lưu một baseline với hash giả như đã hợp lệ.

Đối với môi trường thật, **không nhét toàn bộ manifest vào mỗi trace**. Gắn một số thuộc tính ít giá trị vào telemetry (environment, role, status), còn manifest đầy đủ lưu trong artifact store có version và quyền truy cập.

## 13. Kết quả từng case và từng attempt

Với mỗi run, lưu một record theo case/attempt. Ví dụ JSON Lines:

~~~jsonl
{"runId":"eval-staging-20261127-001","caseId":"rag-001","attempt":1,"executionStatus":"COMPLETED","qualityStatus":"PASS","retrievedIds":["policy-v3-chunk-07"],"evidenceSnapshotRef":"restricted://run-001/case-rag-001","evidenceDigest":"sha256:example","generatorModel":"generator-model-id","judgeModel":"judge-model-id","relevancePass":true,"factCheckPass":true,"inputTokens":410,"outputTokens":65,"usageStatus":"REPORTED","traceRef":"restricted-trace-reference"}
{"runId":"eval-staging-20261127-001","caseId":"rag-002","attempt":1,"executionStatus":"COMPLETED","qualityStatus":"NOT_EVALUATED","retrievedIds":[],"abstentionExpected":true,"relevancePass":null,"factCheckPass":null,"usageStatus":"MISSING","reason":"NO_CONTEXT"}
{"runId":"eval-staging-20261127-001","caseId":"tool-003","attempt":1,"executionStatus":"COMPLETED","qualityStatus":"EVALUATION_ERROR","toolAssertionPass":true,"relevancePass":null,"factCheckPass":null,"errorCode":"JUDGE_TIMEOUT","usageStatus":"UNKNOWN"}
~~~

Những trường `restricted://...` và `sha256:example` là **ký hiệu minh họa**, không phải artifact có thật. Một hệ thống triển khai phải xác định cách lưu context ở nơi được phép và tạo digest thật. Để so kết quả ổn định, dùng `runId + caseId + attempt` làm khóa duy nhất; nếu một case có nhiều lượt judge, ghi thêm `assessmentId/judgeAttempt`.

**Không được xóa lỗi chấm khỏi báo cáo tổng mà không công bố.** Phân biệt:

| Trạng thái | Điều kiện | Cách tính |
|---|---|---|
| `PASS` | Có verdict hợp lệ, đạt rubric | Tử số của pass rate |
| `FAIL` | Có verdict hợp lệ, không đạt | Mẫu số chất lượng |
| `GENERATION_ERROR` | Không tạo answer hợp lệ | Chỉ số lỗi vận hành |
| `EVALUATION_ERROR` | Judge, parsing hoặc chấm lỗi | Chỉ số lỗi evaluator |
| `NO_CONTEXT` | Thiếu evidence | Chấm theo policy abstention; không tự coi FAIL |
| `SKIPPED` | Không chạy do quota/policy | Đếm riêng, công bố số lượng |

Một run có 70 PASS, 20 FAIL, 8 `EVALUATION_ERROR`, 2 `SKIPPED` trên 100 case có **evaluated pass rate** `70/(70+20)=77,8%` và **coverage** `90/100=90%`. Không dùng `70/100=70%` mà gọi đó là cùng một chỉ số; hãy đặt tên, mẫu số và chính sách rõ ràng.

## 14. Bảo toàn bằng checksum: SHA-256 và giới hạn

**Content hash** xác nhận bytes của artifact không đổi. Hash không chứng minh nội dung đã đúng học thuật, và không giúp tái lập nếu artifact gốc đã bị xóa.

### Java 21: đọc file theo luồng và tính SHA-256

~~~java
package com.example.qualitylab;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class ArtifactDigest {
    private ArtifactDigest() {}

    public static String sha256(Path file) throws IOException {
        final MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 không khả dụng", exception);
        }

        try (InputStream in = Files.newInputStream(file)) {
            byte[] buffer = new byte[8192];
            int size;
            while ((size = in.read(buffer)) != -1) {
                digest.update(buffer, 0, size);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

### Unit test xác nhận checksum thay đổi

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ArtifactDigestTest {
    @TempDir Path temporary;

    @Test
    void changingContentChangesDigest() throws Exception {
        Path data = temporary.resolve("dataset.jsonl");
        Files.writeString(data, "{\"id\":\"a\"}\n");
        String first = ArtifactDigest.sha256(data);

        Files.writeString(data, "{\"id\":\"b\"}\n");
        String second = ArtifactDigest.sha256(data);

        assertNotEquals(first, second);
        assertEquals(first.length(), 64);
    }
}
~~~

Code trên chỉ dùng Java Standard Library và JUnit cho test. Nó **không** là một ứng dụng build hoàn chỉnh nếu chưa tạo package, dependencies và files phù hợp. Checksum thay đổi khi byte-level encoding/newline thay đổi; cần thống nhất UTF-8 và chính sách line endings hoặc lưu nguyên bytes của artifact trong object storage.

### Hai kiểu checksum cần phân biệt

- **Checksum của file:** hash chính xác bytes, tốt cho kiểm tra toàn vẹn bản lưu.
- **Checksum của dữ liệu đã chuẩn hóa:** ví dụ JSON canonicalized theo quy ước riêng, cần ghi cả *normalization version*. Nếu không có quy tắc chuẩn, hash cùng một JSON nhưng đổi thứ tự keys cũng có thể khác.

Đừng hash YAML/JSON rồi mặc định các serialize từ hai thư viện cho cùng digest. Nếu dùng canonicalization, quy trình chuẩn hóa là **một phần của version contract**.

## 15. Lưu artifact và phân quyền theo mức nhạy cảm

Ví dụ cấu trúc:

~~~text
evaluation/
  datasets/
    vi-rag-regression-v5/
      manifest.yml
      cases.jsonl
      labels.jsonl
  prompts/
    answer-v7.md
    judge-rubric-v4.md
  policies/
    quality-policy-v3.yml

reports/
  runs/
    eval-staging-20261127-001/
      manifest.yml
      cases-results.jsonl
      summary.json
      evidence-index.json
      dependency-graph.txt

restricted-evidence-storage/     # Không bắt buộc cùng repository
  execution-snapshots/
  tool-outputs/
  rendered-prompts/
~~~

**Không nhất thiết commit `reports/` vào Git**. Với dữ liệu có thể chứa prompt, context hoặc người dùng, sử dụng artifact/object storage được cấp quyền, TTL/retention và audit. Dataset tổng hợp nhỏ có thể lưu Git; dataset lấy từ production phải đi qua quy trình phê duyệt, loại bỏ dữ liệu nhạy cảm và lưu theo quyền.

### Run ID và dấu thời gian

Dùng `run_id` duy nhất, UTC timestamp theo ISO 8601 và identity của artifact. Nếu thí nghiệm chạy song song, mỗi attempt cần khóa riêng và writer có cơ chế append-only/atomic write. Không dùng tên file chỉ gồm `latest.json` khiến lần chạy sau ghi đè bằng chứng lần trước.

### Immutable baseline

Khi một baseline được duyệt, lưu:

1. Manifest có digest của mọi artifact quan trọng.
2. Results có checksum và bộ metric được định nghĩa.
3. Phiên bản quality gate/scorer.
4. Phê duyệt/version của baseline.

Nếu phải sửa baseline, tạo **baseline revision mới** với lý do và lịch sử thay đổi; không âm thầm chỉnh `PASS`/ `FAIL` của run cũ.

## 16. Preflight: kiểm tra phiên bản trước khi bắt đầu

Một runner chuyên nghiệp nên **fail early** khi thấy cấu hình không tương thích với manifest:

~~~text
1. Resolve code commit, build digest và runtime versions.
2. Validate dataset schema, case_count, unique IDs và dataset checksum.
3. Resolve corpus/index build ID, embedding config và retrieval settings.
4. Resolve template/rubric revisions, content hashes, model IDs/options.
5. Check môi trường, quyền và tool sandbox, nhưng KHÔNG xuất secret values.
6. Verify cost/telemetry policy và resource limits.
7. Freeze manifest -> tạo run ID -> chỉ sau đó chạy các case.
8. Ghi từng result và telemetry refs; finalize summary + checksum.
~~~

### Pseudocode kiểm tra baseline

~~~text
manifest = loadRequestedManifest()
assert manifest.schemaVersion in supportedVersions
assert dataset.sha256 == manifest.dataset.contentDigest
assert dataset.caseCount == manifest.dataset.caseCount
assert template.sha256 == manifest.generator.promptDigest
assert rubric.sha256 == manifest.evaluation.rubricDigest
assert corpus.revision == manifest.rag.corpusRevision
assert index.buildId == manifest.rag.indexRevision
assert environment.name in dataset.allowedEnvironments
assert secretsPresentButNeverLogged()

freeze(runManifest)
executeCases()
persistCaseResultsAndFinalize()
~~~

**Các phép kiểm ở trên là logic mà ứng dụng phải hiện thực**; Spring AI không tự cung cấp một `runManifest` hay `datasetAllowedEnvironments` chuẩn chỉ vì file YAML có các trường đó.

### Điều gì nên gây BLOCKED, điều gì chỉ nên WARN?

| Tình huống | Xử lý khuyến nghị |
|---|---|
 Dataset checksum không khớp | **BLOCKED** nếu so baseline |
 Rubric revision khác trong thí nghiệm “chỉ đổi generator” | **BLOCKED** hoặc tạo experimental comparison mới |
 Model alias đúng nhưng resolved version không kiểm được | **WARN** và ghi mức tái lập hạn chế |
 Một case không có expected source IDs dù scenario là tool-only | Có thể **NOT_APPLICABLE** cho retrieval |
 Thiếu optional token usage | **WARN**, đánh dấu `USAGE_MISSING`, không điền zero |
 Thiếu secret bắt buộc để gọi judge | **BLOCKED** hoặc `EVALUATION_ERROR`, tùy đang preflight hay runtime |
 Trace exporter không khả dụng | Lỗi observability cần ghi; policy quyết định block hay cho chạy với cờ `TELEMETRY_DEGRADED` |

Không nên để một test tự fallback từ index staging sang production chỉ để “chạy được”; quyền truy cập dữ liệu là ranh giới độc lập với việc tái lập.

## 17. Chiến lược replay phù hợp loại câu hỏi

Có hai hướng replay thường được dùng cho RAG:

**A. End-to-end replay:** dùng câu hỏi gốc, chạy retrieval và generation lại từ đầu.

- Kiểm tra pipeline thực tế sau thay đổi.
- Phụ thuộc corpus/index/provider/model ở thời điểm replay.
- Cần so retrieval snapshots và model versions để biết biến nào đổi.

**B. Frozen-context replay:** cấp lại đúng context/tool output được ghi của run trước cho generator hoặc judge.

- Hữu ích để cô lập **tác động của prompt/generator** mà không đổi retrieval.
- Hữu ích để chấm lại **judge/rubric** trên cùng answer.
- Không đo lại được chất lượng retriever hiện tại; chỉ kiểm tra từ bước sau context.

### Ma trận mục đích replay

| Muốn tìm nguyên nhân gì? | Giữ cố định | Cái có thể thay |
|---|---|---|
 Prompt mới ảnh hưởng answer? | Dataset, model, frozen context, judge/rubric | Prompt |
 Retriever mới ảnh hưởng recall? | Dataset, ground-truth labels, corpus, embedding nếu có thể | Retrieval/reranking/index config |
 Model generator mới có tốt hơn? | Dataset, prompt, context, judge/rubric | Generator model |
 Judge mới có khác verdict? | Recorded answers, evidence, rubric | Judge model |
 Rubric mới có công bằng? | Recorded answers/evidence, judge nếu có thể | Rubric |
 Tracing mới có mất span? | Workflow/test cases, telemetry environment | Instrumentation/exporter |

Khi không thể giữ biến cố định (ví dụ provider thu hồi model revision cũ), báo cáo rõ đây là **observational comparison** với biến nhiễu, không khẳng định causal effect của một thay đổi duy nhất.

## 18. Thực nghiệm A/B có kiểm soát

Giả sử cần đánh giá việc nâng generator từ `model-A` lên `model-B`.

~~~yaml
experiment:
  id: "generator-comparison-001"
  hypothesis: "model-B cải thiện groundedness mà không tăng cost quá ngân sách"
  shared:
    dataset_revision: "vi-rag-regression-v5"
    corpus_revision: "policy-corpus-v8"
    index_revision: "policy-pgvector-v12"
    prompt_revision: "answer-v7"
    judge_model: "judge-model-v3"
    rubric_revision: "rubric-v4"
    scoring_policy_revision: "quality-policy-v3"
  variants:
    - id: A
      generator_model: "model-A"
    - id: B
      generator_model: "model-B"
  constraints:
    max_evaluation_attempts_per_case: 2
    error_policy: "exclude_from-quality-denominator-but-report-coverage"
~~~

Vì một phép chấm LLM có thể dao động, nên:

1. Dùng **cùng tập case IDs, labels và context** cho hai biến thể.
2. Chạy trong khoảng điều kiện tương đồng (quota, concurrency, provider load khi có thể).
3. Nếu API/model hỗ trợ seed, ghi lại seed, không xem seed như bảo đảm tuyệt đối.
4. Ghi `PASS/FAIL/EVALUATION_ERROR`, **mẫu số** và **số lần retry**.
5. Dùng kiểm tra theo từng case (paired comparison), không chỉ so một tỷ lệ gộp.
6. Kiểm tra bằng người đối với các case có tranh chấp, đo agreement judge/human.

### So sánh dạng paired cases

| Case | Model A | Model B | Kết luận sơ bộ |
|---|---|---|---|
| `rag-001` | PASS | PASS | Không đổi |
| `rag-002` | FAIL | PASS | B có thể cải thiện |
| `rag-003` | PASS | FAIL | B có thể hồi quy |
| `rag-004` | PASS | EVALUATION_ERROR | **Chưa thể so**, cần xử lý lỗi chấm |

Ví dụ minh họa không phản ánh benchmark thật. Với đánh giá LLM có biến động, nên lưu số lượt chấm và xem sự ổn định của những case sát ngưỡng.

## 19. Quality gate và định nghĩa mẫu số

Một bộ tiêu chí phát hành có thể được version hóa:

~~~yaml
quality_gate:
  revision: "release-gate-v3"
  min_evaluation_coverage: 0.98
  min_relevance_pass_rate: 0.92
  min_fact_check_pass_rate: 0.95
  min_retrieval_recall_at_5: 0.90
  max_generation_error_rate: 0.02
  max_evaluation_error_rate: 0.01
  max_p95_generator_latency_ms: 3000
  max_mean_estimated_cost_usd_per_case: 0.03
~~~

Các ngưỡng trên là **giá trị minh họa**, không phải chuẩn mặc định của Spring AI. Sản phẩm thực cần thiết lập theo rủi ro, baseline, khả năng judge, yêu cầu người dùng và ngân sách.

Định nghĩa rõ:

\[
\text{evaluatedPassRate} =
\frac{N_{\mathrm{PASS}}}
{N_{\mathrm{PASS}} + N_{\mathrm{FAIL}}}
\]

\[
\text{evaluationCoverage} =
\frac{N_{\mathrm{PASS}}+N_{\mathrm{FAIL}}}
{N_{\mathrm{totalCases}}}
\]

\[
\text{evaluationErrorRate} =
\frac{N_{\mathrm{EVALUATION\_ERROR}}}
{N_{\mathrm{totalCases}}}
\]

Đối với một tiêu chí chỉ áp dụng cho **RAG có context**, mẫu số nên là số **eligible RAG cases**; không đưa tool-only/no-context cases vào `fact_check_pass_rate` nếu rubric không hỗ trợ chúng.

**Không cố ép `EVALUATION_ERROR` thành `FAIL`** chỉ để tính điểm dễ. Về mặt rủi ro phát hành, một run có coverage thấp có thể bị chặn bởi gate riêng; nhưng đó là quyết định theo policy, không phải phán đoán câu trả lời sai.

## 20. Ghi metrics, traces, chi phí và độ trễ cùng phiên bản

Spring AI 2.1 và Spring Boot 4.2 có hệ thống observations/metrics cho ChatClient, ChatModel, vector store và tool calling khi những thành phần tương ứng thực thi. Ví dụ tín hiệu logic:

| Tín hiệu | Đo gì | Dùng để lý giải |
|---|---|---|
| `spring.ai.chat.client` | Duration ChatClient/advisors | Phân tích phần overhead của pipeline |
| `gen_ai.client.operation` | Duration gọi mô hình | Độ trễ generator/judge/provider |
| `gen_ai.client.token.usage` | Input/output tokens khi có usage | Kích thước context/output và chi phí |
| `db.vector.client.operation` | Thao tác với VectorStore | Retrieval/index bottleneck |
| `spring.ai.tool` | Lời gọi tool | Tool latency/failure |
| `app.ai.evaluation.case` (tự định nghĩa) | Duration một case evaluation | Tổng thời gian chấm và workflow |

### Kết nối report với telemetry mà không gây cardinality cao

- Dùng các metric dimensions có **ít giá trị**: `environment`, `role` (`generator`, `judge_relevance`, `judge_fact`), `scenario`, `outcome`.
- **Không** dùng `run_id`, `case_id`, prompt, user ID, document ID làm Prometheus metric label.
- Trong case report lưu **trace reference** ở nơi được phép, cộng với run/case ID và timestamps. Trace backend phải có access controls.
- Nếu dùng high-cardinality span attributes, vẫn cần kiểm tra quyền và dữ liệu nhạy cảm; high-cardinality **không đồng nghĩa an toàn để ghi PII**.

Một run manifest lưu cả **observation schema version**; nếu metrics được đổi tên giữa hai release, dashboard phải được di chuyển hoặc có lớp mapping có version.

### Chi phí cần price revision

\[
C_{\mathrm{modelCall}}=
\frac{T_{\mathrm{input}}}{10^6}P_{\mathrm{input}}
+\frac{T_{\mathrm{output}}}{10^6}P_{\mathrm{output}}
\]

**`P` là đơn giá trên một triệu token**, theo loại model và ngày/region/plan áp dụng. Với generator và hai evaluators:

\[
C_{\mathrm{case}}=
C_{\mathrm{generator}}+
C_{\mathrm{relevanceJudge}}+
C_{\mathrm{factJudge}}+
C_{\mathrm{retrieval/embedding/tool}}
\]

Nếu provider cung cấp cached input, reasoning tokens hoặc batch pricing, cần thêm các hạng mục tương ứng. Với usage thiếu, ghi `usage_status=MISSING`, không giả định cost bằng 0.

### Latency cần định nghĩa đoạn đo

- **User-facing latency:** lúc nhận request đến lúc trả answer/lỗi, không cộng judge offline.
- **Evaluation end-to-end latency:** chạy dataset, retrieval, generation, judge, result writes.
- **Per-role p50/p95:** generator vs judge vs vector/tool, trong cùng điều kiện lấy mẫu.

Một `ChatClient` span có thể bao gồm các span con advisor và ChatModel; **không cộng duration cha và con** như hai công việc độc lập. Traces có sampling và có thể không đủ mọi case; dùng case result và aggregate metrics để tính tỷ lệ chất lượng.

## 21. Tách secret, dữ liệu nhạy cảm và version reference

Manifest là bằng chứng cấu hình, **không phải nơi sao lưu API key**:

| Thông tin | Được ghi ở đâu? |
|---|---|
| API key, DB password, OTLP bearer token | Secret manager/volume, không trong Git/report |
| Secret alias/version, identity role | Manifest được bảo vệ nếu cần audit |
| Tên model, options, dataset/index revision | Run manifest |
| Prompt template/rubric không nhạy cảm | Git + content hash |
| Rendered prompt/RAG context có dữ liệu nhạy cảm | Restricted snapshot store, không public report |
| Token usage/cost/quality aggregate | Report/metrics với phân quyền |
| Raw tool input/output có PII | Chỉ store được phép, redaction/retention |

Nếu dùng một hash để “ẩn” email, số điện thoại hoặc short token, vẫn có nguy cơ dictionary attack. Khi cần liên kết mà không phơi bày dữ liệu, cân nhắc HMAC bằng khóa tách khỏi artifact và policy quản trị dữ liệu.

### Không dùng model ID như secrets

Model ID thường là metadata không bí mật, nhưng có thể phản ánh cấu hình nghiệp vụ; xét mức chia sẻ phù hợp. Provider API key là **secret thật**, không nên bao giờ xuất hiện trong `configprops`, trace, log hoặc bản report được chia sẻ.

## 22. Phân tích hồi quy bằng manifest diff

Giả sử run A có fact-check pass rate 95% và run B còn 88%. Trước khi quy cho generator, so:

~~~text
dataset_sha           A == B ?
corpus_revision       A == B ?
index_revision        A == B ?
embedding_model       A == B ?
prompt_revision       A == B ?
generator_model       A != B ?  # Biến chủ đích
judge_model           A == B ?
judge_rubric          A == B ?
scoring_policy        A == B ?
error_coverage        A ~  B ?
provider_model_build  xác minh được không?
~~~

Nếu ngoài generator còn đổi index và judge, **không thể kết luận causal effect của riêng generator**. Có thể:

1. Chạy lại baseline/candidate trên **frozen-context replay**.
2. Chấm cả hai tập answer bằng **cùng judge và rubric**.
3. So retrieval recall độc lập nếu index thay đổi.
4. Đối chiếu trace, tokens, latency, tool failures và lỗi runtime.
5. Yêu cầu review những ca mà judge bất đồng với nhãn người.

### Bảng chẩn đoán nhanh

| Tín hiệu thay đổi | Nghi vấn chính | Bằng chứng cần xem |
|---|---|---|
| Recall@k giảm, fact checking giảm | Corpus/index/chunking/filter/reranking | Source/index revision, retrieved IDs, vector trace |
| Recall@k giữ nguyên, fact checking giảm | Prompt/model/generation | Rendered prompt digest, answer, judge cố định |
| Pass rate giảm chỉ khi đổi judge | Judge/rubric drift | Frozen answer snapshot, human calibration |
| Tool assertions giảm | Tool schema/prompt/tool gateway | Schema revision, recorded arguments, tool spans |
| Latency tăng, token input tăng | Top-k/context/prompt dài hơn | Context size, input tokens, ChatModel duration |
| Traces thiếu nhưng metrics đầy đủ | Sampling/exporter/context propagation | Trace config revision, collector logs, span links |
| Nhiều EVALUATION_ERROR | Judge backend, quota hoặc parsing | Judge model/endpoint, retry/error codes, coverage |
| Cost tăng dù tokens không tăng | Pricing revision/model/tier thay đổi | Rate card, currency, cache/reasoning categories |

## 23. Tình huống một thay đổi có chủ đích

Nhóm muốn kiểm tra **chỉ** ảnh hưởng của prompt:

| Yếu tố | Run A | Run B |
|---|---|---|
| Git commit | `commit-v7` | `commit-v8` (chỉ prompt + metadata) |
| Dataset và labels | `qa-v5` | Giữ nguyên và xác minh digest |
| Corpus/index | `corpus-v8/index-v12` | Giữ nguyên |
| Model generator | `model-X` | Giữ nguyên, kiểm tra resolved version |
| Prompt template | `answer-v7` | `answer-v8` |
| Judge/rubric | `judge-Y/rubric-v4` | Giữ nguyên |
| Lịch chạy/quota | Cùng chính sách | Cùng chính sách |
| Đo | Relevance, factuality, coverage, tokens, p95, cost | Cùng định nghĩa |

Trong report:

~~~text
Hypothesis: prompt-v8 giảm hallucination mà không làm p95 tăng >20%.
Primary metric: fact_check_pass_rate (eligible RAG cases).
Guardrails: relevance, evaluation_coverage, p95 latency, cost/case.
Changed variable: answer prompt template.
Known caveats: hosted model serving revision không được provider công bố.
Decision: chấp nhận / giữ baseline / cần thêm đánh giá.
~~~

Không nên chỉ xuất một con số “+4 điểm factuality” khi thiếu số lượng case, confidence/dao động, lỗi evaluator và chi phí. Nếu thay đổi nhỏ hơn mức noise của judge, phải chạy lặp hoặc bổ sung đánh giá của con người.

## 24. Lỗi thường gặp và cách khắc phục

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hai runs cùng dataset revision nhưng có case khác | File dataset được sửa tại chỗ | Tạo revision mới, lưu checksum và case_count |
| Cùng tên model nhưng answer khác | Alias/provider revision thay đổi hoặc sampling | Ghi requested/resolved version, điều kiện và mức tái lập |
| Relevance/fact-check giảm sau nâng judge | Rubric/judge drift | Rejudge cả baseline và candidate, calibration người chấm |
| Truy xuất khác khi replay | Corpus/index/chunking/filter bị thay | Snapshot index, giữ exact context cho frozen replay |
| Cost/case khác dù token tương tự | Price revision, caching, reasoning, retry | Lưu price source và categories/attempts |
| QA report “tốt lên” nhưng coverage thấp | Nhiều `EVALUATION_ERROR` bị loại không công bố | Công bố mẫu số và evaluation error rate |
| Chỉ lưu Git commit, thiếu local changes | Dirty working tree | Chặn baseline hoặc lưu artifact patch/digest an toàn |
| Hash không giống giữa hai hệ thống | Khác encoding/newline/serialization | Hash raw bytes và giữ nguyên artifact; version hóa normalization |
| Chấm lại mà evidence khác | Judge chạy retrieval lại | Dùng recorded snapshot của generator |
| Tool replay làm thay đổi dữ liệu thật | Gọi lại API có side effect | Sandbox/mocks/idempotency, không replay production write |
| Không tìm được trace cũ | Sampling/retention/exporter | Lưu report độc lập, trace ref chỉ là liên kết bổ trợ |
| Metric cardinality tăng | Dùng run/case IDs làm labels | Dùng role/scenario/outcome, lưu IDs trong report |
| Lộ dữ liệu trong manifest | Ghi raw API key/prompt/context | Dùng secret refs, restricted artifact storage, redaction |
| Một run chạy trên hai model versions | Provider/router thay deployment giữa batch | Ghi model metadata **theo từng attempt**, tách/flag run nếu mismatch |

## 25. Bài thực hành

### Bài A — Tạo run manifest cho demo ba outcome

Với ứng dụng mẫu có **PASS**, **FAIL** và **TECHNICAL_ERROR**:

1. Tạo dataset tổng hợp gồm ba case, khóa `dataset_revision`.
2. Ghi commit và dependency versions của ứng dụng học.
3. Ghi `generator.type=fixture`, `judge.type=deterministic` và `rubric_revision=reference-v1`.
4. Chạy từng case và ghi `executionStatus`, `qualityStatus`, error code và duration.
5. Xuất manifest, case results và một summary có **mẫu số**.

**Tiêu chí đạt:** người khác có thể lấy đúng fixture/version, chạy lại và phân biệt rõ 200+PASS, 200+FAIL, 503+NOT_EVALUATED. Không dùng ba case này để suy diễn accuracy của LLM thực.

### Bài B — Chứng minh checksum phát hiện dữ liệu thay đổi

1. Viết một `cases.jsonl` tổng hợp và tính SHA-256.
2. Sửa một chữ trong ground truth nhưng giữ tên file.
3. Tính lại SHA-256; dùng unit test như `ArtifactDigestTest` xác nhận checksum khác.
4. Cho preflight kiểm tra `expected digest` và yêu cầu **BLOCKED** nếu không khớp.
5. Tạo dataset revision mới thay vì sửa baseline cũ.

**Tiêu chí đạt:** runner không lặng lẽ chấm trên dataset đã thay.

### Bài C — So sánh prompt A/B trên RAG

1. Khóa 20–50 case RAG có ground-truth document IDs và nhãn người.
2. Dùng **frozen context** để tránh retrieval drift.
3. Chạy prompt A/B với model generator cố định; ghi options, provider metadata và lỗi.
4. Chấm bằng cùng judge và rubric; đo `relevance`, `fact_check`, `coverage`.
5. So tokens, cost ước tính, latency; ghi chú giới hạn biến động model hosted.
6. Viết manifest diff, chứng minh **chỉ prompt** được thay có chủ đích.

**Tiêu chí đạt:** báo cáo có các case cải thiện/hồi quy, error count, điều kiện thí nghiệm và kết luận có giới hạn.

### Bài D — Tái chấm bằng judge mới

1. Lưu answer/evidence snapshot của run A.
2. Chấm với judge J1/rubric R1; lưu assessment revision.
3. Chấm cùng snapshot với judge J2/rubric R1; không gọi generator lại.
4. So bất đồng từng case, đối chiếu nhãn người chấm.
5. Tách kết luận **judge disagreement** khỏi **generator regression**.

### Bài E — Tool replay an toàn

Tạo fixture `getOrderStatus("TEST-003")` và ghi tool schema revision, sandbox output, expected arguments. Chạy lại bằng mock. Xác minh không có external write và không được truy cập tài nguyên production.

### Câu hỏi tự kiểm tra

1. Vì sao chỉ có `git_commit` và `model_id` chưa đủ để tái lập một kết quả RAG?
2. Trong live LLM, `temperature=0` có bảo đảm câu trả lời giống nhau từng token không?
3. Khi so prompt A và B, vì sao cần khóa **judge/rubric** và **retrieved context**?
4. Điểm khác nhau giữa content hash của file và version string là gì?
5. Khi judge timeout, báo cáo nên ghi `FAIL` hay `EVALUATION_ERROR`?
6. Vì sao phải lưu embedding model và index build ID khi corpus không đổi?
7. Khi test một tool có side effect, replay an toàn phải làm gì?
8. Chỉ số nào giúp biết pass rate cao là do nhiều case lỗi chấm bị loại?
9. Khi nào cần báo “không thể tái lập bit-for-bit” dù manifest đầy đủ?
10. Vì sao `case_id` phù hợp để liên kết report nhưng không phù hợp làm Prometheus label?

**Gợi ý:** (1) thiếu dataset, prompt, corpus/index, options, judge/rubric và runtime; (2) không; (3) giảm biến nhiễu; (4) hash kiểm bytes, tên version do người/hệ thống đặt; (5) `EVALUATION_ERROR`; (6) chúng quyết định kết quả retrieval; (7) sandbox/mocks/idempotency; (8) `evaluation_coverage` và error rate; (9) hosted model có thể đổi backend hoặc stochastic behavior; (10) cardinality cao và rủi ro lộ thông tin.

## 26. Checklist bàn giao

- [ ] Đã phân biệt reproducibility của **input/workflow** với tính ổn định **đầu ra thống kê**.
- [ ] Run manifest có schema version, UTC timestamp, run ID, Git commit và trạng thái working tree.
- [ ] Có Java/Boot/Spring AI/dependency và build artifact versions kiểm chứng được.
- [ ] Model ghi requested ID, resolved revision nếu có và request options thực sự dùng.
- [ ] Prompt template/rubric có revision và checksum; render/evidence policy đã được định nghĩa.
- [ ] Dataset có ID, revision, checksum, case_count, split và labels revision.
- [ ] Corpus, chunking, embedding, vector index, top-k, filter/reranking được version hóa.
- [ ] Tool contracts/fixtures có revision; tool có side effect không replay vào production.
- [ ] Judge model, rubric, scoring policy, calibration và thresholds được chốt.
- [ ] Execution snapshot giữ đúng context đã đưa cho generator, không bị judge thay đổi.
- [ ] Mỗi case có status tách biệt: `PASS`, `FAIL`, `GENERATION_ERROR`, `EVALUATION_ERROR`, `NO_CONTEXT`, `SKIPPED`.
- [ ] Summary công bố pass rate, coverage, error rates và **mẫu số**.
- [ ] Metrics/traces và chi phí có role/environment, price revision, sampling và observation schema.
- [ ] Không đưa secret, raw prompt nhạy cảm, PII hoặc unique IDs vào metric labels.
- [ ] Baseline bất biến, có checksums và quy trình duyệt bản mới.
- [ ] Khi so A/B, các biến giữ cố định được kiểm tra; giới hạn kết luận được ghi rõ.

## Tài liệu tham khảo

1. [Spring AI — Project Setup](https://docs.spring.io/spring-ai/reference/getting-started.html): Spring AI BOM, compatibility và thiết lập dự án.
2. [Spring AI — Evaluation](https://docs.spring.io/spring-ai/reference/api/testing.html): cấu trúc `EvaluationRequest` và các loại evaluator.
3. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): ChatClient/ChatModel/tool/VectorStore metrics và traces.
4. [Spring AI — RAG](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html): retrieval, advisor và luồng tạo câu trả lời có context.
5. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): profiles, biến môi trường và cấu hình bên ngoài repository.
6. [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, phân phối latency và các mức đo vận hành.
7. [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): context propagation, sampling, OpenTelemetry.
8. [Git — Recording Changes](https://git-scm.com/book/en/v2/Git-Basics-Recording-Changes-to-the-Repository): commit và working tree.
9. [Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): dependency management/BOM và resolved graph.
10. [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): quản lý phiên bản dependencies để tái lập build.
11. [NIST — Reproducibility and Replicability in Science](https://www.nationalacademies.org/publications/25303): cơ sở khái niệm về điều kiện và kết quả thí nghiệm.

> **Ghi nhớ:** Một kết quả Spring AI chỉ so sánh được khi biết **mã, dependency, generator, judge, rubric, dataset, corpus/index, tool và chính sách quan sát** nào đã tạo ra nó. Hãy khóa input, lưu bản ghi từng attempt, công khai mẫu số và mức tái lập khả thi; nhờ đó mọi thay đổi về relevance, fact checking, độ trễ, token và chi phí đều có bằng chứng để truy nguyên.
