# Chẩn đoán sự cố: Kết quả đánh giá dao động khi code và bộ dữ liệu không đổi

## 1. Vì sao cùng một bài đánh giá lại cho kết quả khác nhau?

Một evaluation run có thể cho điểm 0,86 vào buổi sáng và 0,79 vào buổi chiều dù nhóm không sửa code hoặc dataset. Điều này không nhất thiết là lỗi của pipeline tính điểm. Ứng dụng AI có nhiều thành phần có thể thay đổi kết quả trong lúc file và commit vẫn giữ nguyên:

- Chat model có sampling, backend serving hoặc model revision thay đổi.
- Evaluator dùng một LLM khác để chấm câu trả lời, và chính evaluator cũng có thể dao động.
- Retriever truy vấn vector index đang được cập nhật, dùng approximate nearest-neighbor search hoặc filter phụ thuộc dữ liệu runtime.
- Tool lấy trạng thái từ database, API bên ngoài, đồng hồ hệ thống hoặc dịch vụ có dữ liệu thay đổi.
- Conversation memory, cache, feature flag hoặc cấu hình môi trường làm input thực tế khác nhau.
- Retry, timeout, rate limit, concurrency và streaming làm một số request đi qua đường xử lý khác.
- Evaluation harness chia sẻ mutable state, chạy song song hoặc dùng random seed không được kiểm soát.
- Aggregate score thay đổi vì số case hoàn tất, denominator, subgroup mix hoặc cách gộp attempt khác nhau.

Vì vậy, câu “code và dataset không đổi” chưa chứng minh hai lần chạy đã dùng cùng một request, context, model revision, evaluator, runtime configuration và execution path.

**Mục tiêu chẩn đoán:** xác định phần nào của kết quả đang dao động — retrieval, model output, evaluator verdict, tool result, runtime execution hay phép tổng hợp — rồi cô lập nguồn biến thiên bằng snapshot và repeated trials.

Bài học thuộc chương **Chẩn đoán sự cố** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời theo dõi metrics, traces, chi phí và độ trễ để phát hiện suy giảm qua từng phiên bản prompt, model và pipeline.

Sau bài học, bạn có thể:

- Phân biệt stochastic variation, evaluator variance, data drift, runtime drift và measurement error.
- Kiểm tra input thực tế thay vì chỉ kiểm tra file dataset.
- Lưu reproducibility envelope cho từng evaluation run.
- Dùng repeated trials để đo within-case variance.
- Tách biến thiên của generator khỏi biến thiên của LLM judge.
- Phân biệt attempt-level result với unique-case result.
- Đọc confidence interval và tránh kết luận từ sample nhỏ.
- Dùng Spring AI ChatModel/ChatClient options để kiểm soát tham số có hỗ trợ.
- Cố định retrieval context, tool results, memory và clock khi cần cô lập model.
- Theo dõi retry, timeout, provider revision, retrieval fingerprints và evaluator disagreement.
- Thiết kế runbook để xác định nguyên nhân và quyết định rerun, hold hoặc incident.

## 2. Phân biệt dao động ngẫu nhiên và suy giảm có hệ thống

Không phải mọi score delta đều là regression. Hãy phân loại hiện tượng trước khi sửa pipeline.

| Loại biến thiên | Dấu hiệu | Ví dụ |
| --- | --- | --- |
| Model stochasticity | Cùng prompt/context nhưng raw response khác nhau giữa attempts | Cách diễn đạt, thứ tự ý hoặc tool proposal thay đổi |
| Provider/backend drift | Cùng model alias nhưng output phân bố thay đổi theo thời gian | Provider chuyển serving revision hoặc hardware path |
| Evaluator variance | Raw response giống nhau nhưng judge verdict/score thay đổi | LLM judge chấm PASS ở run này, FAIL ở run khác |
| Retrieval variance | Cùng query nhưng document IDs/ranks khác | ANN search, index update, filter hoặc query embedding thay đổi |
| External-state variance | Tool result khác nhau | Order status, inventory, exchange rate hoặc policy effective date đổi |
| Runtime variance | Chỉ lỗi dưới concurrency/load hoặc một environment | Timeout, retry, race condition, shared memory |
| Dataset/aggregation variance | Per-case results ổn định nhưng overall score đổi | Denominator, coverage hoặc subgroup distribution khác |
| Measurement noise | Delta nhỏ, confidence intervals chồng lấn | Sample size thấp hoặc metric có variance lớn |

### 2.1. Stochasticity không đồng nghĩa với bug

Một model có thể trả nhiều câu trả lời khác nhau nhưng đều đáp ứng rubric. Nếu response khác wording nhưng claims, evidence và task outcome vẫn đúng, exact-string comparison sẽ báo false regression.

Ngược lại, model có thể trả câu gần như giống nhau nhưng một con số hoặc điều kiện quan trọng bị thay đổi. Khi đó cần đánh giá theo claim và dimension thay vì chỉ so text similarity.

### 2.2. Dao động và drift khác nhau

- **Dao động (variance):** kết quả thay đổi qua attempts nhưng không có xu hướng ổn định theo thời gian.
- **Drift:** phân bố kết quả thay đổi có hệ thống theo model revision, provider rollout, corpus version, traffic cohort hoặc thời gian.
- **Regression:** thay đổi làm quality hoặc operational behavior vượt khỏi acceptance criteria đã xác định.
- **Measurement error:** phép đo hoặc denominator sai khiến score không phản ánh behavior thật.

Đừng kết luận drift từ hai điểm đo. Cần đủ runs, metadata và cùng measurement contract để phân biệt noise với thay đổi có hệ thống.

## 3. Bản đồ nguồn gây dao động

Một cách hữu ích là đi từ đầu vào tới verdict và kiểm tra từng boundary.

~~~mermaid
flowchart TD
    A["Evaluation case"] --> B["Input / prompt rendering"]
    B --> C["Retrieval / context assembly"]
    C --> D["Chat model"]
    D --> E["Tool execution / memory"]
    E --> F["Final response"]
    F --> G["Evaluator / judge"]
    G --> H["Per-case verdict"]
    H --> I["Run aggregation"]
    I --> J["Reported score"]
    B -. "config / shared state" .-> X["Runtime & test harness"]
    C -. "index / filters / ANN" .-> X
    D -. "provider / sampling / backend" .-> X
    E -. "external data / clock / retries" .-> X
    G -. "judge model / rubric" .-> X
    H -. "coverage / denominator" .-> X
~~~

| Boundary | Snapshot hoặc fingerprint cần so |
| --- | --- |
| Input | Rendered messages, locale, history, variable values |
| Prompt | Template hash, prompt version, output schema |
| Retrieval | Query vector version, document IDs, ranks, scores, filters |
| Context | Exact ordered context content/hash, truncation và token count |
| Model | Provider, requested/reported model, revision, endpoint, options |
| Tool/memory | Arguments, fixture result, authorization, memory snapshot |
| Evaluator | Judge model/revision, prompt, rubric, thresholds |
| Aggregation | Completed cases, skipped/failed cases, denominator, weighting |
| Runtime | App build, dependencies, config, concurrency, retries, clock |

## 4. Trước tiên hãy xác minh input thực tế có giống nhau

Dataset file không phải lúc nào cũng là toàn bộ input của model. Một case có thể ghép thêm:

- System prompt được render từ template.
- Conversation history hoặc memory summary.
- Retrieved documents lấy từ vector store.
- Metadata filters theo user/tenant.
- Tool definitions và kết quả tool.
- Current date/time hoặc locale.
- Feature flags, tenant settings hoặc runtime prompt variables.

Nếu một trong các thành phần này thay đổi, hai run không còn là cùng một experiment.

### 4.1. So sánh rendered request

Lưu hash của rendered messages sau khi áp dụng template và advisors. Hash cần dựa trên canonical representation có thứ tự rõ ràng, gồm role, content, tool schema và relevant metadata.

Không chỉ hash raw dataset row. Hai run có cùng row nhưng khác advisor order, memory, retrieval context hoặc tool schema sẽ tạo request khác.

### 4.2. So sánh context theo thứ tự

Với RAG, lưu:

- Query đã được rewrite.
- Document/chunk IDs và source versions.
- Rank và score.
- Metadata filters.
- Thứ tự chunks được đưa vào prompt.
- Content hash của từng chunk.
- Token count trước/sau truncation.
- Context window budget và truncation policy.

Một tập document IDs giống nhau nhưng thứ tự hoặc phần text bị cắt khác nhau vẫn có thể làm model trả lời khác.

### 4.3. Dùng hai chế độ replay

- **Frozen replay:** sử dụng lại exact context, tool results và prompt snapshot để cô lập generation/evaluator.
- **Live pipeline replay:** chạy lại retrieval, tools và memory như production để kiểm tra biến thiên của toàn pipeline.

Chạy frozen replay trước để xác định model/evaluator có dao động hay không. Sau đó chạy live replay để kiểm tra các thành phần dữ liệu/runtime.

## 5. Model/provider là nguồn biến thiên đầu tiên cần kiểm tra

### 5.1. Temperature thấp không đảm bảo deterministic

Temperature điều chỉnh sampling behavior. Giá trị thấp thường làm output tập trung hơn, nhưng không bảo đảm cùng một response qua mọi lần gọi.

Ngoài temperature, output còn có thể chịu ảnh hưởng của:

- top-p, top-k hoặc provider-specific sampling options.
- Seed, nếu provider/model hỗ trợ.
- Model alias trỏ tới backend revision khác.
- Quantization, serving implementation và hardware.
- Reasoning effort hoặc hidden provider settings.
- Tool choice và parallel tool calling.
- Stop sequences, output token limits và response format.
- Provider-side retry, routing và safety layers.

Giữ temperature cố định là một biện pháp kiểm soát, không phải bằng chứng reproducibility tuyệt đối.

### 5.2. Model alias không phải immutable revision

Một model name dạng latest, alias theo family hoặc deployment endpoint có thể trỏ tới implementation khác theo thời gian. Lưu cả:

- Requested model name.
- Response-reported model name nếu có.
- Provider deployment/version nếu được cung cấp.
- Endpoint/region.
- Provider request ID.
- Timestamp và rate-limit metadata.
- Spring AI/provider SDK version.

Nếu provider không công bố immutable revision, ghi rõ giới hạn này. Không tuyên bố có thể tái tạo byte-for-byte một response khi serving backend đã thay đổi mà không có revision reference.

### 5.3. Retry có thể làm thay đổi response được chấm

Một logical evaluation request có thể có nhiều HTTP/model attempts. Nếu attempt đầu timeout sau khi provider đã xử lý, client có thể retry và nhận một response khác. Cần phân biệt:

- Logical case/run.
- Application invocation.
- Provider request attempt.
- Retry attempt.
- Final response được đưa vào evaluator.

Không âm thầm ghi đè response đầu bằng response retry. Lưu attempt metadata và chính sách chọn kết quả cuối.

## 6. Kiểm soát generation options trong Spring AI

Spring AI cung cấp ChatOptions portable và các options riêng của provider. Không phải mọi provider đều hỗ trợ cùng một tham số.

Ví dụ với OpenAI Chat Model, có thể pin model, temperature và seed cho một experiment:

~~~java
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.openai.OpenAiChatOptions;
import org.springframework.ai.chat.model.ChatResponse;

public class ReproducibleGeneration {

    private final ChatModel chatModel;

    public ReproducibleGeneration(ChatModel chatModel) {
        this.chatModel = chatModel;
    }

    public String generate(String userText) {
        OpenAiChatOptions options = OpenAiChatOptions.builder()
                .model("gpt-4o-mini")
                .temperature(0.0)
                .seed(42)
                .maxTokens(500)
                .build();

        ChatResponse response = chatModel.call(
                new Prompt(userText, options));

        return response.getResult().getOutput().getText();
    }
}
~~~

Đây là ví dụ dành cho OpenAI-compatible Spring AI integration và model hỗ trợ các options trên. Seed của OpenAI được tài liệu hóa là beta/best-effort; nó không bảo đảm response giống hệt nếu backend hoặc serving implementation thay đổi. Không chuyển seed thành giả định portable cho mọi ChatModel.

Một số model reasoning không hỗ trợ temperature. Kiểm tra capability của model cụ thể thay vì gửi cùng một bộ options cho tất cả provider.

### 6.1. Pin toàn bộ options liên quan

Trong experiment manifest, lưu:

- Model và deployment revision.
- Temperature, top-p, top-k nếu có.
- Seed nếu hỗ trợ.
- Max output tokens hoặc max completion tokens phù hợp.
- Stop sequences.
- Frequency/presence penalties.
- Response format/schema.
- Tool choice và parallel tool settings.
- Reasoning effort nếu provider hỗ trợ.
- Streaming/non-streaming mode.

Không thay đồng thời temperature và top-p khi không hiểu tương tác của chúng. Nếu thay option, tạo experiment mới và ghi rõ dimension đang kiểm tra.

### 6.2. Kiểm tra requested model và actual model

Nếu provider trả model ID trong response metadata, lưu nó cùng result. Khi requested model giữ nguyên nhưng actual model thay đổi, phân loại thành provider/model serving drift và so sánh các cohort riêng.

## 7. Evaluator cũng có thể dao động

Một lỗi phổ biến là chỉ lặp lại generation, nhưng mỗi lần lại dùng một LLM judge khác nhau để chấm. Khi score thay đổi, nhóm không biết candidate response khác nhau hay judge khác nhau.

Spring AI Evaluator nhận EvaluationRequest gồm user text, context data và response content. RelevancyEvaluator và FactCheckingEvaluator có thể dùng model để tạo verdict. Vì evaluator cũng là một model call, nó có thể có sampling, backend drift, retry và lỗi provider riêng.

### 7.1. Cô lập generator và judge

Thực hiện hai thí nghiệm:

1. **Generator variance:** cố định input/context, chạy nhiều generation attempts, lưu raw response; sau đó chấm các responses bằng một quy trình judge đã pin.
2. **Judge variance:** chọn một tập raw responses cố định, gửi cùng response/context nhiều lần cho judge và đo mức độ nhất quán.

Nếu raw responses ổn định nhưng judge verdict thay đổi, điều tra evaluator. Nếu raw responses thay đổi còn judge ổn định trên cùng input, điều tra generator.

### 7.2. Pin evaluator

Lưu:

- Judge provider/model/revision.
- Judge prompt/template hash.
- Rubric version.
- Threshold và output parser version.
- Context snapshot và response snapshot.
- Retry/timeout policy.
- Evaluator request ID và result.

Không dùng evaluator version mới chỉ cho candidate trong khi baseline dùng judge cũ. Nếu cần nâng cấp judge, chạy calibration experiment riêng trên human-reviewed labels.

### 7.3. Kiểm tra judge agreement

Chọn một calibration set có nhãn do người đánh giá độc lập xác minh. So sánh judge-human agreement, false pass, false fail và disagreement theo task family.

Với critical factual/safety cases, không dùng majority vote của một LLM judge lặp nhiều lần để biến verdict thành ground truth. Cần evidence và human adjudication theo policy.

### 7.4. Spring AI evaluator request

Một evaluation request cần giữ cùng query, context và response khi đo judge variance:

~~~java
EvaluationRequest request = new EvaluationRequest(
        testCase.userText(),
        testCase.pinnedContext(),
        capturedResponse);

EvaluationResponse verdict = evaluator.evaluate(request);
~~~

testCase.pinnedContext() cần cung cấp List<Content> tương ứng với API Spring AI đang dùng. Lưu verdict cùng evaluator fingerprint và response hash để có thể xác định judge đã chấm đúng artifact nào.

## 8. Retrieval và vector search có thể làm kết quả dao động

Ngay cả khi query text không đổi, kết quả retrieval có thể khác vì:

- Vector index đang được cập nhật trong lúc evaluation chạy.
- Approximate nearest-neighbor search có yếu tố thuật toán hoặc concurrency.
- Query embedding model/config khác.
- Embedding vectors hoặc metadata bị backfill.
- Similarity threshold/top K/filter thay đổi.
- Reranker có sampling hoặc model revision khác.
- Document status/effective date thay đổi.
- Search consistency/replica lag khác nhau.

### 8.1. Lưu retrieval fingerprint

Tạo fingerprint cho ordered result list, ví dụ hash của:

- Document/chunk IDs.
- Source version.
- Rank.
- Score đã normalize/round theo policy.
- Filter expression/version.
- Index snapshot/version.
- Query embedding model/version.

Nếu fingerprint thay đổi, hãy điều tra retrieval trước khi kết luận generation regression.

### 8.2. Tách vector search khỏi RAG generation

Chạy riêng:

- Query embedding snapshot.
- Vector search trên frozen index.
- Retrieval result comparison.
- Context assembly.
- Generation trên pinned context.

Nếu vector search khác nhau nhưng frozen-context generation ổn định, nguồn biến thiên nằm ở retrieval/index. Nếu retrieval ổn định nhưng generation dao động, chuyển sang model/provider.

### 8.3. Đừng dùng live index làm immutable test fixture

Một evaluation dataset có thể giữ nguyên query nhưng vector store vẫn thay đổi. Với benchmark cần reproducibility, dùng versioned collection/index hoặc lưu retrieved context snapshot. Live retrieval test vẫn cần thiết, nhưng phải được báo cáo là một experiment khác.

## 9. Tools, memory và dữ liệu bên ngoài

Tool output có thể thay đổi theo thời gian dù model và prompt không đổi.

| Nguồn | Vì sao thay đổi | Cách cố định trong replay |
| --- | --- | --- |
| Order/inventory API | Trạng thái nghiệp vụ mới | Fixture theo record version/time |
| Search/web API | Nội dung và ranking thay đổi | Snapshot response hoặc archived fixture |
| Clock/date | Thời điểm hiện tại khác | Inject fixed Clock |
| Random service | Random value mới | Seeded generator hoặc fixture |
| Database query | Transaction mới hoặc replica lag | Snapshot/transaction fixture |
| Memory | Conversation history được cập nhật | Versioned memory snapshot |
| Feature flag | Cohort/config khác | Pin flag values trong manifest |
| Authorization | Principal/role/tenant khác | Fixed test identity và permission fixture |

### 9.1. Không gọi side-effecting tools trong repeated evaluation

Nếu model có thể gọi payment, email, order update hoặc destructive action, dùng fake tool hoặc sandbox. Mỗi attempt cần có isolated state. Không replay cùng case nhiều lần vào production tool thật.

### 9.2. Fixed clock

Một số prompt hoặc tool dựa trên “hôm nay”, “trong 24 giờ qua” hoặc ngày hiệu lực. Trong test, inject Clock cố định thay vì gọi Instant.now() rải rác. Ghi timezone và locale để tránh cùng timestamp nhưng render date khác.

### 9.3. Reset memory và cache

Mỗi case cần session/conversation ID riêng hoặc memory state được reset có kiểm soát. Cache key phải bao gồm các version ảnh hưởng output như prompt, model, corpus và authorization scope. Nếu cache được giữ giữa attempts, ghi cache hit/miss để giải thích response lặp hoặc khác.

## 10. Runtime, concurrency và test harness

Một evaluation suite có thể ổn định khi chạy đơn lẻ nhưng dao động khi chạy song song.

Các nguồn thường gặp:

- Shared mutable list/map trong tool fixtures.
- Dùng chung conversation ID hoặc memory store.
- Test order phụ thuộc vào cache hoặc database state.
- Concurrent writes vào vector store.
- Thread-local observation/security context không được propagate.
- Race condition trong async callbacks.
- Rate limit khi nhiều worker gọi cùng provider.
- Timeout/backoff làm attempts hoàn tất trong thứ tự khác.
- Test dùng static clock/random state không reset.

### 10.1. Kiểm tra serial trước parallel

Chạy một suite theo ba chế độ:

1. Một case, một worker.
2. Nhiều cases tuần tự.
3. Nhiều cases song song với concurrency production-like.

Nếu chỉ chế độ 3 dao động, ưu tiên điều tra shared state, rate limit, queueing, connection pool và context propagation.

### 10.2. Tách fixture state theo attempt

Mỗi attempt nên có:

- Tool fixture scope riêng.
- Conversation/memory scope riêng.
- Idempotency key riêng hoặc được thiết kế theo logical case.
- Database transaction/test namespace riêng.
- Trace context riêng.
- Cleanup rõ ràng sau khi hoàn tất.

Không để hai attempts cùng mutate một fixture object.

### 10.3. Phân biệt retry với repeated trial

- **Retry:** phục hồi một lần thực thi bị lỗi tạm thời; không phải một sample độc lập của model behavior.
- **Repeated trial:** cố ý gọi lại cùng case để đo stochasticity.
- **Replay:** tái hiện một lần thực thi bằng snapshot đã lưu.

Không cộng retry và repeated trials vào cùng denominator. Nếu retry chỉ được thực hiện cho attempts lỗi, tỷ lệ output pass trên attempts sẽ bị bias.

## 11. Reproducibility envelope

Mỗi run nên lưu một envelope đủ để giải thích input và execution environment.

| Nhóm | Trường gợi ý |
| --- | --- |
| Identity | run ID, case ID/version, attempt ID |
| Dataset | dataset version, content hash, split |
| Application | build/commit, dependency lock, Spring Boot/Spring AI version |
| Prompt | template version/hash, rendered message hash |
| Model | provider, requested/actual model, revision, endpoint/region |
| Options | temperature, top-p/top-k, seed, token limits, response format |
| Retrieval | query embedding version, index version, ordered result fingerprint |
| Context | document/chunk versions, content hashes, order, token count |
| Tools | schema version, arguments hash, fixture/result version |
| Memory | conversation ID scope, memory snapshot version |
| Evaluator | judge model/revision, prompt/rubric/parser/threshold versions |
| Runtime | environment, feature flags, locale, timezone, clock |
| Execution | concurrency, retry count, timeout, cache hit/miss |
| Observability | trace/span IDs, provider request IDs, timestamps |
| Result | raw response reference/hash, verdict, score, outcome |

Không cần lưu mọi raw content vào metric hoặc log. Dùng secure immutable snapshot references, content hashes và retention/access policy. Với dữ liệu nhạy cảm, redaction phải giữ cấu trúc cần thiết cho reproduction.

### 11.1. Reproducibility levels

| Mức | Khả năng |
| --- | --- |
| L0 — Aggregate only | Chỉ có overall score; không đủ để điều tra |
| L1 — Case identified | Biết case nào dao động nhưng thiếu execution inputs |
| L2 — Request snapshot | Có rendered input/context và versions |
| L3 — Full execution envelope | Có model/provider, evaluator, tools, runtime và traces |
| L4 — Controlled replay | Có thể replay frozen inputs/tools/index trong môi trường pin được |

L4 vẫn không bảo đảm byte-identical output từ hosted model nếu provider không giữ immutable backend và deterministic execution.

## 12. Quy trình điều tra theo từng bước

~~~mermaid
flowchart TD
    A["Score changed; code and dataset appear unchanged"] --> B["Compare run manifests and coverage"]
    B --> C{"Same rendered request and context?"}
    C -->|No| D["Inspect prompt, memory, retrieval, filters, runtime"]
    C -->|Yes| E{"Same raw model response?"}
    E -->|No| F["Inspect model revision, sampling, provider, retries"]
    E -->|Yes| G{"Same evaluator verdict?"}
    G -->|No| H["Inspect judge model, rubric, parser and threshold"]
    G -->|Yes| I{"Same per-case results?"}
    I -->|No| J["Inspect tools, external state, concurrency and attempts"]
    I -->|Yes| K["Inspect denominator, weighting and aggregation"]
    D --> L["Create isolated replay"]
    F --> L
    H --> L
    J --> L
    K --> M["Recompute from immutable result store"]
    L --> N["Repeat controlled trials"]
    N --> O["Classify variance vs drift vs regression"]
    M --> O
~~~

### 12.1. Bước 1 — Kiểm tra coverage và denominator

So sánh:

- Expected case count.
- Completed unique cases.
- Skipped cases.
- Candidate execution failures.
- Evaluator errors/inconclusive.
- Retry attempts.
- Duplicate result rows.
- Weighting theo task family.

Nếu chỉ 90/100 cases hoàn tất ở run A nhưng 100/100 ở run B, score có thể đổi dù từng case không đổi. Không mặc định bỏ các failures khỏi denominator; định nghĩa policy rõ.

### 12.2. Bước 2 — So rendered input và retrieval

So prompt hash, context hash, ordered document IDs, memory snapshot, tool definitions và feature flags. Nếu khác, chưa cần điều tra model sampling.

### 12.3. Bước 3 — So raw generation

Nếu input giống nhau nhưng response khác, kiểm tra provider revision, model options, seed, response metadata, retries, endpoint và timestamp.

### 12.4. Bước 4 — So evaluator

Nếu response hash giống nhưng score khác, chạy cùng response nhiều lần qua pinned judge. Kiểm tra evaluator prompt, rubric, parsing, threshold và judge availability.

### 12.5. Bước 5 — So aggregation

Nếu per-case terminal results giống nhau nhưng overall score khác, tính lại từ immutable result store. Kiểm tra denominator, weighting, duplicate attempts, missing strata và rounding.

## 13. Thiết kế repeated trials đúng cách

Repeated trials giúp đo mức dao động của cùng một case. Chúng không thay thế việc tăng số lượng cases đại diện.

Một protocol cơ bản:

1. Chọn dataset snapshot và critical cases.
2. Pin rendered input, context, tools và evaluator.
3. Chọn số lần lặp trước khi xem kết quả.
4. Ghi mỗi attempt thành một record riêng.
5. Randomize thứ tự case/variant nếu so sánh baseline-candidate.
6. Tách retries do infrastructure khỏi repeated trials có chủ đích.
7. Tính within-case variance và run-level metrics.
8. Báo confidence interval và coverage.
9. Dừng theo protocol đã định, không dừng ngay khi score đạt kỳ vọng.

Nếu mục tiêu là tái hiện một attempt cụ thể, giữ nguyên seed và options. Nếu mục tiêu là ước lượng sampling variance, dùng seed khác nhau cho mỗi trial hoặc bỏ seed theo khả năng provider; ghi seed policy trong run manifest. Không dùng cùng seed cho mọi trial rồi diễn giải kết quả đó là phân bố sampling tự nhiên.

### 13.1. Không để case dễ có trọng số lớn hơn

Nếu case A chạy 20 attempts và case B chạy 2 attempts, pooling toàn bộ attempts sẽ cho case A trọng số lớn hơn. Nếu metric mục tiêu là chất lượng trung bình theo case, tính pass probability của từng case trước rồi aggregate theo case/stratum.

Báo riêng:

- Attempt-level success rate.
- Unique-case coverage.
- Mean per-case pass probability.
- Score variance within case.
- Between-case variance.

### 13.2. Paired trials

Khi so baseline và candidate, chạy cả hai trên cùng cases. Có thể randomize order theo case để giảm order effects. Nếu mỗi variant chạy nhiều attempts, giữ cặp theo case và trial block; không coi mọi attempts là independent cases.

### 13.3. Chọn số lần lặp

Số lần lặp phụ thuộc variance, precision mong muốn, cost và criticality. Bắt đầu bằng pilot để ước lượng variance, sau đó xác định sample plan. Với critical cases có risk cao, có thể cần nhiều attempts hoặc deterministic fixtures; không chọn một con số chung cho mọi task.

## 14. Thống kê để đọc kết quả dao động

### 14.1. Pass rate theo case

Với một case có \(n\) repeated trials và \(x\) lần pass:

\[
\hat{p} = \frac{x}{n}
\]

Ví dụ 8/10 attempts pass cho ước lượng pass probability 0,8. Điều này không có nghĩa case đã được “80% đúng” theo nghĩa ground truth; nó mô tả tần suất pass theo execution/evaluator protocol đang dùng.

Với proportions và sample nhỏ, dùng Wilson confidence interval thay vì chỉ báo point estimate. Với score liên tục, báo mean, standard deviation, median và interquartile range.

### 14.2. Paired score delta

Với mỗi case, tính:

\[
d_i = score_{candidate,i} - score_{baseline,i}
\]

Báo mean/median delta và confidence interval. Paired bootstrap trên case IDs phù hợp khi so sánh hai variant có cùng case set. Nếu có nhiều attempts trong từng case, bootstrap theo case trước rồi mới lấy attempts trong case để tránh giả định mọi attempt độc lập.

### 14.3. Phân biệt within-case và between-case variance

- **Within-case variance:** cùng một case, cùng input, output/verdict dao động.
- **Between-case variance:** các case có độ khó hoặc mức bất định khác nhau.
- **Between-run variance:** run-level differences như provider load, index snapshot hoặc runtime state.
- **Judge variance:** cùng response nhưng evaluator verdict thay đổi.

Không gộp các nguồn này thành một standard deviation duy nhất nếu mục tiêu là xác định root cause.

### 14.4. Statistical significance không thay thế practical significance

Một delta nhỏ có thể statistically significant khi sample rất lớn nhưng không đáng kể về business. Một critical subgroup regression có thể quan trọng dù sample nhỏ và confidence interval rộng.

Đặt trước:
- Minimum practical effect.
- Confidence level.
- Non-inferiority margin nếu cần.
- Critical hard gates.
- Sample/coverage requirements.
- Multiple-comparison policy khi kiểm tra nhiều subgroups.

Nếu sample không đủ, kết luận INCONCLUSIVE thay vì PASS.

## 15. Đọc đúng denominator và run aggregation

Một evaluation pipeline nên phân biệt các cấp:

| Cấp | Ý nghĩa |
| --- | --- |
| Case | Một tình huống duy nhất trong dataset version |
| Trial | Một lần chạy có chủ đích của case |
| Attempt | Một invocation, có thể bao gồm retry |
| Candidate result | Output của model/pipeline |
| Evaluation result | Verdict/score của evaluator |
| Run summary | Aggregate theo một run protocol |

Ví dụ, một case có 3 trials và trial thứ hai có 2 provider attempts do timeout. Có 3 trials, 4 provider attempts và tối đa 3 final candidate results. Không đếm 4 attempts thành 4 independent test cases.

### 15.1. Định nghĩa denominator

- Candidate success rate: số final candidate executions thành công / số logical candidate executions.
- Evaluation coverage: số cases có terminal evaluation result / số eligible unique cases.
- Case pass rate: số unique cases pass theo aggregation rule / số unique cases có kết quả hợp lệ.
- Judge error rate: evaluator infrastructure/parse failures / số judge invocations.
- Retry rate: số retry attempts / số initial invocations.

Nếu evaluator ERROR hoặc INCONCLUSIVE, không tự biến thành FAIL chất lượng candidate. Giữ riêng evaluator health và candidate quality.

### 15.2. Không average các run đã có coverage khác nhau mà không chuẩn hóa

Nếu run A thiếu một subgroup có score thấp, overall score có thể tăng giả tạo. So sánh trên common case set hoặc dùng fixed reference weights và báo coverage từng stratum.

## 16. Spring AI observability hỗ trợ điều tra ra sao?

Spring AI cung cấp observations/metrics/traces cho ChatClient, ChatModel, EmbeddingModel và VectorStore. Điều này giúp xác định latency, request options, token usage, advisor execution và vector operations ở đúng boundary.

Một số thông tin hữu ích trong traces:

- Model request/response model.
- Temperature, top-k/top-p và token limits.
- Finish reason và response ID nếu provider trả.
- Input/output token usage.
- Advisor names/order.
- Vector operation type, top K và similarity threshold.
- Tool names và execution observations.

Prompt/completion và vector search response không được export mặc định vì có thể chứa dữ liệu nhạy cảm. Chỉ bật content logging trong debug scope có access control, redaction và retention phù hợp.

### 16.1. Kết hợp trace với reproducibility envelope

Một trace giúp xem execution path; envelope giúp tái tạo request. Lưu trace/span references trong run result store, không dùng trace ID làm metric label.

### 16.2. Kiểm tra model và HTTP layer

Một logical model call có thể tạo nhiều HTTP attempts. So sánh model observation với HTTP spans để nhận ra retry, timeout hoặc backend/network errors. Nếu model call có latency cao nhưng HTTP layer không tương ứng, kiểm tra queueing, serialization hoặc application-side processing.

## 17. Metrics cho evaluation variance

Các metric sau là custom application metrics; tên không phải mặc định của Spring AI.

| Metric | Loại | Ý nghĩa |
| --- | --- | --- |
| ai_eval_attempts_total | Counter | Số attempts theo stage/outcome |
| ai_eval_cases_terminal_total | Counter | Unique case terminal results theo run outcome |
| ai_eval_cases_inconclusive_total | Counter | Unique cases kết thúc INCONCLUSIVE theo run |
| ai_eval_trials_total | Counter | Số repeated trials có chủ đích |
| ai_eval_judge_invocations_total | Counter | Số lần gọi evaluator |
| ai_eval_judge_errors_total | Counter | Lỗi provider/parser của evaluator |
| ai_eval_provider_retries_total | Counter | Số retry ở provider/client layer |
| ai_eval_retrieval_fingerprint_changes_total | Counter | Retrieval result fingerprint thay đổi |
| ai_eval_score | Histogram | Phân bố score |
| ai_eval_attempt_duration_seconds | Histogram | Duration của attempt |
| ai_eval_case_pass_probability | Gauge | Pass probability tính từ result store |
| ai_eval_coverage_ratio | Gauge | Tỷ lệ unique cases có terminal result |
| ai_eval_run_score_stddev | Gauge | Độ lệch chuẩn score trong run/repeated trials |

Metric labels nên giới hạn ở stage, outcome, task_family, variant, environment và model family/release cohort có cardinality kiểm soát. Không dùng case ID, user ID, prompt hash, trace ID hoặc raw query làm labels.

### 17.1. Attempt outcome rate

~~~promql
sum by (stage, outcome) (
  rate(ai_eval_attempts_total[1h])
)
~~~

Đây là phân bố attempt outcomes. Nó không phải unique-case pass rate vì retries và repeated trials có thể làm tăng số attempts.

### 17.2. Unique case pass rate

~~~promql
sum by (variant, task_family) (
  rate(ai_eval_cases_terminal_total{outcome="PASS"}[1h])
)
/
sum by (variant, task_family) (
  rate(ai_eval_cases_terminal_total{outcome=~"PASS|FAIL"}[1h])
)
~~~

Metric ai_eval_cases_terminal_total phải tăng đúng một lần cho mỗi unique case terminal result trong mỗi run. Counter này chỉ ghi terminal PASS/FAIL dùng cho quality denominator; INCONCLUSIVE được ghi riêng vào ai_eval_cases_inconclusive_total. Nếu case được rerun trong một run, chỉ final aggregate theo policy mới được tính vào counter này. Báo thêm coverage và INCONCLUSIVE; không loại chúng khỏi dashboard.

### 17.3. Evaluator error rate

~~~promql
sum(rate(ai_eval_judge_errors_total[1h]))
/
sum(rate(ai_eval_judge_invocations_total[1h]))
~~~

Tỷ lệ này đo health của judge. Không gộp evaluator errors vào candidate quality failures.

### 17.4. p95 attempt duration

~~~promql
histogram_quantile(
  0.95,
  sum by (le, stage) (
    rate(ai_eval_attempt_duration_seconds_bucket[15m])
  )
)
~~~

### 17.5. Đo variance

Prometheus histogram hữu ích để theo dõi score distribution, nhưng variance theo case/repeated trial thường cần tính từ result store vì phải giữ grouping theo logical case và run. Tính standard deviation, confidence interval và per-case pass probability trong evaluation analytics; export các aggregate bounded dimensions sang metrics.

## 18. Thiết kế evaluation result store

Giữ attempt history append-only để có thể điều tra việc retry hoặc rerun.

Một schema logic có thể gồm:

~~~sql
CREATE TABLE evaluation_run (
    run_id              VARCHAR(80) PRIMARY KEY,
    dataset_version     VARCHAR(120) NOT NULL,
    pipeline_fingerprint VARCHAR(160) NOT NULL,
    evaluator_fingerprint VARCHAR(160) NOT NULL,
    started_at          TIMESTAMP NOT NULL,
    completed_at        TIMESTAMP,
    run_status          VARCHAR(24) NOT NULL
);

CREATE TABLE evaluation_attempt (
    attempt_id          VARCHAR(100) PRIMARY KEY,
    run_id              VARCHAR(80) NOT NULL,
    case_id             VARCHAR(120) NOT NULL,
    trial_no            INTEGER NOT NULL,
    provider_attempt_no INTEGER NOT NULL,
    stage               VARCHAR(32) NOT NULL,
    outcome             VARCHAR(24) NOT NULL,
    score               DOUBLE PRECISION,
    request_fingerprint VARCHAR(160),
    response_hash       VARCHAR(160),
    trace_ref           VARCHAR(160),
    started_at          TIMESTAMP NOT NULL,
    completed_at        TIMESTAMP
);

CREATE TABLE evaluation_case_result (
    run_id              VARCHAR(80) NOT NULL,
    case_id             VARCHAR(120) NOT NULL,
    terminal_outcome    VARCHAR(24) NOT NULL,
    pass_probability    DOUBLE PRECISION,
    score_mean          DOUBLE PRECISION,
    score_stddev        DOUBLE PRECISION,
    trial_count         INTEGER NOT NULL,
    PRIMARY KEY (run_id, case_id)
);
~~~

Đây là schema minh họa. evaluation_attempt giữ mọi invocation/retry; evaluation_case_result lưu một terminal aggregate cho case trong run. Có thể bổ sung foreign keys, indexes, JSON metadata và partitioning theo retention policy.

Không ghi raw prompts hoặc tool payload nhạy cảm vào bảng metric. Dùng secure snapshot references và quyền truy cập phù hợp.

## 19. Ví dụ Java: chạy repeated trials và lưu từng attempt

Ví dụ sau chạy tuần tự để loại trừ shared state/concurrency trước. Nó không tự retry lỗi provider; retry policy nên nằm ở lớp riêng và được ghi nhận riêng.

~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.openai.OpenAiChatOptions;

public class RepeatedTrialRunner {

    private final ChatModel chatModel;
    private final AttemptRepository attemptRepository;

    public RepeatedTrialRunner(
            ChatModel chatModel,
            AttemptRepository attemptRepository) {
        this.chatModel = chatModel;
        this.attemptRepository = attemptRepository;
    }

    public List<TrialOutput> run(
            EvaluationCase testCase,
            int trialCount) {

        List<TrialOutput> outputs = new ArrayList<>();

        for (int trial = 1; trial <= trialCount; trial++) {
            Instant startedAt = Instant.now();

            try {
                OpenAiChatOptions options = OpenAiChatOptions.builder()
                        .model("gpt-4o-mini")
                        .temperature(0.0)
                        .seed(42 + trial)
                        .maxTokens(500)
                        .build();

                ChatResponse response = chatModel.call(
                        new Prompt(testCase.userText(), options));

                String text = response.getResult().getOutput().getText();

                TrialOutput output = TrialOutput.success(
                        testCase.caseId(),
                        trial,
                        text,
                        startedAt,
                        Instant.now());

                attemptRepository.append(output);
                outputs.add(output);
            }
            catch (RuntimeException ex) {
                TrialOutput failure = TrialOutput.error(
                        testCase.caseId(),
                        trial,
                        safeErrorCode(ex),
                        startedAt,
                        Instant.now());

                attemptRepository.append(failure);
                outputs.add(failure);
            }
        }

        return List.copyOf(outputs);
    }

    private String safeErrorCode(RuntimeException exception) {
        return exception.getClass().getSimpleName();
    }
}
~~~

EvaluationCase, TrialOutput và AttemptRepository là application-owned types. Trong RAG evaluation, thay testCase.userText() bằng request renderer nhận exact pinned context. Không để mỗi trial truy vấn live vector store nếu mục tiêu là đo generation variance.

Trong production, dùng injected Clock thay Instant.now() để test time-dependent code. Đoạn code dùng clock hệ thống để minh họa; fixed clock thuộc test harness.

### 19.1. Gộp trials theo case

Sau khi có attempts, tính pass probability hoặc score distribution cho từng case. Không cộng số attempts thành số cases.

~~~java
public record CaseTrialSummary(
        String caseId,
        int trials,
        int passed,
        double passProbability) {

    public static CaseTrialSummary from(
            String caseId,
            int trials,
            int passed) {
        if (trials <= 0 || passed < 0 || passed > trials) {
            throw new IllegalArgumentException("Invalid trial counts");
        }

        return new CaseTrialSummary(
                caseId,
                trials,
                passed,
                (double) passed / trials);
    }
}
~~~

Nếu có evaluator ERROR/INCONCLUSIVE, lưu các trạng thái riêng và xác định rule xử lý trước khi tính passProbability. Không tự coi missing verdict là FAIL hoặc PASS.

## 20. Ma trận chẩn đoán nhanh

| Quan sát | Nguồn cần ưu tiên | Bước tiếp theo |
| --- | --- | --- |
| Rendered request hash khác | Prompt rendering, history, memory, feature flags | So template variables và advisor chain |
| Retrieval fingerprint khác | Vector index, query embedding, filters, ANN | Replay frozen index/query |
| Context hash giống, raw response khác | Model/provider/sampling | Pin options, model revision và lặp frozen request |
| Raw response giống, verdict khác | Evaluator/judge | Lặp judge trên response snapshot |
| Tool result khác | External state, clock, database | Fixture tool và fixed clock |
| Chỉ dao động khi parallel | Shared state, rate limit, queueing | Serial replay và isolated fixtures |
| Attempt errors tăng | Provider/network/timeout | So HTTP spans, retry và rate-limit headers |
| Per-case outcomes giống, overall score khác | Denominator/aggregation | Recompute từ immutable result store |
| Chỉ một subgroup dao động | Locale, task family, source type | Stratified analysis |
| Score đổi cùng provider response model | Provider/backend rollout | Tách cohort theo actual model revision |
| Score thay sau rubric update | Evaluator drift | Calibration set và judge-human agreement |

## 21. Quy trình khắc phục theo runbook

1. Ghi nhận run IDs, dataset version, pipeline fingerprint và score delta.
2. Kiểm tra coverage, completed unique cases, skipped cases và denominator.
3. Chọn các case có score thay đổi lớn nhất và các critical cases.
4. So rendered request/context hashes.
5. So retrieval document IDs/ranks và tool fixture outputs.
6. Nếu inputs giống, so model/provider metadata và raw responses.
7. Nếu response giống, chạy repeated judge trials.
8. Chạy frozen replay tuần tự để loại trừ concurrency và external state.
9. Chạy live replay để kiểm tra retrieval/tool/runtime drift.
10. Tính per-case pass probability, score variance và confidence intervals.
11. Phân loại stochastic variation, systematic drift, infra failure hoặc measurement error.
12. Chỉ thay đổi một nguồn tại một thời điểm.
13. Chạy regression suite và human audit trên các case bị ảnh hưởng.
14. Ghi root cause, evidence, remediation và release decision.

### 21.1. Khi nào nên rerun?

Rerun khi có lý do cụ thể như provider timeout, evaluator infrastructure error hoặc incomplete coverage. Giữ attempt cũ và ghi lý do rerun.

Không rerun vô hạn cho đến khi có một score đẹp. Số trials, retry policy, stopping rule và acceptance criteria cần được định trước.

### 21.2. Khi nào phải hold release?

Hold khi:

- Critical case dao động giữa PASS và FAIL mà chưa giải thích được.
- Judge disagreement tăng vượt calibration tolerance.
- Provider revision không được nhận diện và output distribution thay đổi.
- Retrieval/context snapshot không thể xác minh.
- Coverage hoặc sample size chưa đạt yêu cầu.
- Aggregate score tốt hơn nhưng critical subgroup suy giảm.
- Evaluator/infra failures bị tính nhầm thành quality PASS.

## 22. Checklist kiểm tra production

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Chạy lại cùng frozen request | Rendered input/context hash giống nhau |
| Temperature thấp | Không mặc định kết luận deterministic |
| Seed được cấu hình | Ghi nhận provider/model support và giới hạn best-effort |
| Model alias giữ nguyên | Kiểm tra actual model/revision nếu có |
| Judge chấm cùng response nhiều lần | Có judge variance và agreement metrics |
| RAG dùng live index | Retrieval fingerprint và index version được ghi |
| Tool phụ thuộc thời gian | Clock/fixture có thể pin |
| Memory dùng chung | Mỗi case/trial có isolated state |
| Chạy suite song song | Serial/parallel comparison phát hiện race |
| Provider retry | Mỗi provider attempt được ghi riêng |
| Evaluator timeout | Không biến thành candidate quality FAIL |
| Coverage thay đổi | Denominator và subgroup mix được báo |
| Repeated trials | Attempt count không bị hiểu là unique-case count |
| Candidate/base paired run | Cùng case set, randomized order và evaluator |
| Raw prompt/completion logging | Có redaction, access control và retention |
| Critical result dao động | Hold và human review theo policy |
| Run kết thúc | Manifest, attempts, traces và decision log được lưu |

## 23. Bài tập thực hành

### Bài 1. Phân loại nguồn dao động

Tạo một case có cùng user input nhưng cho phép thay đổi model output, judge verdict, retrieval context và tool result. Thiết kế thí nghiệm để nhận diện từng nguồn.

### Bài 2. Frozen request replay

Lưu rendered prompt và retrieved context snapshot. Chạy model 10 lần với options cố định. Báo response hash, score, pass probability và standard deviation.

### Bài 3. Đo judge variance

Chọn 20 raw responses đã cố định. Chạy cùng Evaluator nhiều lần và so với human-reviewed labels. Tính agreement và disagreement theo task family.

### Bài 4. Tách retrieval và generation

Chạy live retrieval nhiều lần để phát hiện fingerprint changes. Sau đó replay exact pinned context qua model để kiểm tra generation variance.

### Bài 5. Phân biệt retry và repeated trial

Mô phỏng provider timeout có retry và 5 repeated trials có chủ đích. Lưu attempt/trial numbers riêng và tính denominator đúng.

### Bài 6. Kiểm tra serial và parallel

Chạy cùng suite tuần tự và song song. Dùng isolated tool fixture/memory scopes. Xác định race hoặc rate-limit effects.

### Bài 7. Tính confidence interval

Với 30 cases, chạy 5 trials/case. Tính per-case pass probability, aggregate theo case, và bootstrap confidence interval bằng case-level resampling.

### Bài 8. Điều tra score tổng hợp dao động

Tạo hai run có cùng per-case results nhưng khác coverage hoặc subgroup mix. Recompute score trên common case set và fixed reference weights.

### Bài 9. Xây runbook

Thiết kế dashboard hiển thị attempts, unique cases, coverage, judge errors, retries, retrieval fingerprint changes, p95 latency và score variance. Viết điều kiện hold/release.

## 24. Tổng kết

Kết quả đánh giá có thể dao động dù code và dataset file không đổi vì execution thực tế còn phụ thuộc model/provider, evaluator, retrieval, tools, memory, runtime và cách tổng hợp.

- Xác minh rendered input, context và pipeline fingerprint trước khi điều tra model.
- Phân biệt model stochasticity, provider drift, judge variance, retrieval variance, external-state variance và measurement error.
- Pin model options khi provider hỗ trợ; temperature thấp hoặc seed không bảo đảm deterministic tuyệt đối.
- Tách generator variance khỏi evaluator variance bằng frozen responses và repeated judge trials.
- Giữ retrieval snapshots, tool fixtures, memory state và clock để replay có kiểm soát.
- Chạy serial trước parallel để phát hiện shared state, concurrency và rate-limit effects.
- Lưu từng trial/attempt append-only; phân biệt retry, repeated trial và unique case.
- Tính pass probability theo case và dùng confidence intervals; tránh coi repeated attempts là independent cases.
- Giữ evaluator health, candidate quality và coverage ở các denominator riêng.
- Dùng Spring AI observations/traces để điều tra ChatClient, ChatModel, advisors và VectorStore.
- Chỉ kết luận regression khi evidence, sample và acceptance criteria đủ; trạng thái chưa rõ phải là INCONCLUSIVE.

Khi một score thay đổi, câu hỏi đầu tiên không phải “model có kém đi không?” mà là “hai lần chạy đã thực sự đo cùng một thứ chưa?”. Reproducibility envelope, frozen replay và repeated trials giúp trả lời câu hỏi đó bằng evidence thay vì suy đoán.

## Tài liệu tham khảo

- [Spring AI Reference — Chat Model API](https://docs.spring.io/spring-ai/reference/api/chatmodel.html): ChatModel, Prompt, portable ChatOptions và model-specific options.
- [Spring AI Reference — OpenAI Chat](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html): temperature, seed best-effort, request options, retries và provider metadata.
- [Spring AI Reference — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): Evaluator, EvaluationRequest, RelevancyEvaluator và FactCheckingEvaluator.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): observations, metrics và traces cho ChatClient, ChatModel, advisors, EmbeddingModel và VectorStore.
- [Prometheus Documentation — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): latency/score distribution và percentile aggregation.
- [OpenTelemetry Semantic Conventions — Generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/): model request/response metadata và GenAI operation attributes.
