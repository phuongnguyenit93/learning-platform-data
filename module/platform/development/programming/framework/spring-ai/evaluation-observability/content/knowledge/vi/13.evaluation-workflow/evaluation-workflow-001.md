# Tổ chức luồng tạo phản hồi, thu thập ngữ cảnh và chấm điểm

Trong một ứng dụng Spring AI, đánh giá câu trả lời không bắt đầu ở nút “Chấm điểm”. Để kết luận một câu trả lời có **liên quan**, **được bằng chứng hỗ trợ** hay **đúng sự thật**, trước đó hệ thống phải tạo câu trả lời trong điều kiện xác định và giữ lại đúng những dữ liệu đã tham gia vào lần tạo ấy.

Hãy xét một chatbot RAG trả lời chính sách hoàn phí. Người dùng hỏi: “Gói Pro được hoàn phí trong bao lâu?”. Chính sách **giả định** đang có hiệu lực quy định **14 ngày**. Nếu chatbot trả lời “30 ngày”, điều quan trọng không chỉ là ghi `FAIL` mà còn xác định: retriever đã lấy tài liệu nào, tài liệu nào thực sự đi vào prompt, model có nhận kết quả tool nào không, câu trả lời cuối cùng ra sao, và evaluator dựa trên dữ liệu nào để chấm.

Bài học trong chương **Quy trình đánh giá** của module **SPRING_AI_EVALUATION_OBSERVABILITY** trình bày cách tổ chức toàn bộ chuỗi **đọc ca kiểm thử → tạo phản hồi → thu thập ngữ cảnh và bằng chứng thực thi → chấm điểm → tổng hợp kết quả → phân tích traces, metrics, token, chi phí và độ trễ**. Quy trình áp dụng cho cả RAG và tool calling, đồng thời hỗ trợ phát hiện hồi quy khi thay prompt, model hoặc pipeline.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Thiết kế một evaluation run có dataset và cấu hình được phiên bản hóa.
2. Phân biệt **reference context** (nguồn chuẩn), **retrieved context** (kết quả truy xuất) và **effective context** (thông tin thực tế đưa vào model).
3. Biết thời điểm cần thu thập question, documents, prompt version, model response, tool events, usage và trace ID.
4. Tổ chức kiểm tra xác định (schema/tool arguments), kiểm tra retrieval, relevance, groundedness và factual correctness.
5. Hiểu cách dùng các abstraction `Evaluator`, `EvaluationRequest` và `EvaluationResponse` trong Spring AI mà không trộn lẫn điểm chấm với bằng chứng thực thi.
6. Lưu trạng thái `PASS`, `FAIL`, `NOT_EVALUATED` hoặc lỗi thực thi theo từng metric thay vì chỉ một điểm chung.
7. Tính tỷ lệ đạt với mẫu số rõ ràng, nối verdict với ca kiểm thử và trace phục vụ điều tra.
8. Thiết kế workflow có thể chạy lại trong CI và được mở rộng cho giám sát chất lượng production.

## 2. Bức tranh tổng thể: ba luồng dữ liệu gặp nhau

Quy trình đánh giá có ba luồng dữ liệu khác nhau:

- **Expectation:** dữ liệu kiểm thử, reference facts, reference documents, rubric, expected tool behavior.
- **Execution:** câu hỏi thực thi, tài liệu truy xuất, context đã ghép, câu trả lời thật, tool calls, thời gian, token và lỗi.
- **Judgment:** các phép kiểm và evaluator so sánh expectation với execution để đưa ra verdict.

~~~mermaid
flowchart TD
    A["Dataset có nhãn<br/>question + expected facts + rubric"] --> B["Evaluation runner"]
    B --> C["Spring AI application"]
    C --> D["Retriever / VectorStore"]
    D --> E["Context thực sự vào prompt"]
    E --> F["ChatModel và tool calls nếu có"]
    F --> G["Final answer + citations"]
    C -.-> H["Execution evidence<br/>document IDs, tool events, trace"]
    D -.-> H
    E -.-> H
    F -.-> H
    G --> I["Evaluation stage"]
    H --> I
    A --> I
    I --> J["Verdicts theo metric<br/>+ reasons + evidence refs"]
    J --> K["Aggregate + regression<br/>+ release decision"]
    H --> L["Metrics / traces / cost<br/>điều tra nguyên nhân"]
    L --> K
~~~

Trong sơ đồ, `Evaluation runner` là thành phần tổ chức do dự án xây dựng. Spring AI cung cấp các API để gọi model, truy xuất tài liệu và một số evaluator; nó **không tự động quản lý toàn bộ dataset, rubric, run manifest, kho evidence và release gate** theo cấu trúc minh họa.

### 2.1. Năm bất biến của workflow

1. **Mỗi kết quả phải thuộc đúng một execution attempt.** Nếu chạy cùng case hai lần, phải phân biệt hai lần thực thi.
2. **Dữ liệu kỳ vọng không được thay thế dữ liệu thực.** `expectedDocumentIds` không phải `actualRetrievedDocumentIds`.
3. **Context dùng chấm groundedness phải là context model thực sự nhận được.** Kết quả retriever có thể khác context cuối sau lọc, cắt ngắn hoặc ghép prompt.
4. **Mỗi verdict phải ghi phương pháp chấm và tình trạng evidence.** Không có bằng chứng thì không tự gán PASS.
5. **Telemetry mô tả thực thi; rubric mô tả chất lượng.** HTTP 200, token usage hoặc trace thành công không đủ để kết luận nội dung đúng.

## 3. Giai đoạn A — Thiết kế một evaluation case có thể chạy lại

Bắt đầu từ một nhiệm vụ và nguồn sự thật. Trong ví dụ giả định, dịch vụ *Sao Mai* có tài liệu `policy-v3#refund-pro` quy định gói Pro được yêu cầu hoàn phí trong 14 ngày kể từ ngày mua. Tài liệu `policy-v2#refund-pro` trước đó ghi 30 ngày nhưng đã hết hiệu lực.

Một record kiểm thử tối thiểu:

~~~json
{
  "caseId": "POLICY-001",
  "datasetVersion": "policy-eval-v1",
  "question": "Gói Pro có thể hoàn phí trong bao lâu?",
  "referenceFacts": [
    "Thời hạn yêu cầu hoàn phí là 14 ngày kể từ ngày mua"
  ],
  "referenceDocumentIds": ["policy-v3#refund-pro"],
  "expectedRetrievalIds": ["policy-v3#refund-pro"],
  "forbiddenClaims": ["Thời hạn 30 ngày", "Hoàn phí vô điều kiện"],
  "expectedBehavior": "Trả lời đúng thời hạn và dẫn nguồn hiện hành",
  "tags": ["rag", "policy", "vi", "factual"],
  "rubricVersion": "policy-rubric-v1"
}
~~~

Ở bước này chưa có câu trả lời do ứng dụng sinh. `referenceFacts` và `expectedRetrievalIds` được dùng làm tiêu chuẩn để đánh giá **sau khi** execution kết thúc.

### 3.1. Rubric nên gắn với loại lỗi cụ thể

| Tiêu chí | Điều kiện PASS | Cần dữ liệu nào |
| --- | --- | --- |
| **Answer relevance** | Trả lời đúng vấn đề thời hạn hoàn phí | Question + actual answer |
| **Retrieval hit@k** | Tìm được nguồn hiện hành bắt buộc trong top-k | Expected IDs + actual retrieved IDs |
| **Groundedness / faithfulness** | Khẳng định quan trọng được context thực tế hỗ trợ | Actual answer + effective context |
| **Factual correctness** | Phù hợp nguồn chuẩn hiện hành | Actual answer + verified reference facts/documents |
| **Citation accuracy** | Nguồn được dẫn thực sự hỗ trợ nội dung | Answer citations + tài liệu nguồn |
| **Tool behavior** | Chọn đúng tool/args, xử lý đúng kết quả và quyền | Expected tool action + actual tool events |
| **Operational budget** | Latency và chi phí nằm trong giới hạn được đặt | Duration + usage + đơn giá tương ứng |

**Relevance khác correctness.** Câu “30 ngày” có thể rất liên quan đến câu hỏi nhưng sai quy định. **Groundedness khác factual correctness.** Nếu model dựa đúng vào tài liệu cũ ghi 30 ngày, groundedness theo tài liệu đã truy xuất có thể đạt nhưng factual correctness theo chính sách hiện hành vẫn thất bại.

### 3.2. Cần thêm các ca âm

Một dataset chỉ có câu hỏi dễ sẽ làm báo cáo quá lạc quan. Thêm trường hợp không có nguồn, tài liệu mâu thuẫn, chính sách hết hiệu lực, câu hỏi đa điều kiện, thiếu quyền và tool timeout.

Ví dụ câu hỏi: “Nếu có mã khuyến mãi thì gói Pro có thể hoàn phí sau 30 ngày không?”. Khi reference documents không nói tới ngoại lệ, expected behavior là **thừa nhận tài liệu chưa đủ** và đề nghị kiểm tra nguồn có thẩm quyền; chatbot không nên tự bịa ngoại lệ.

## 4. Giai đoạn B — Khởi tạo evaluation run và cố định cấu hình

**Case** nói cần kiểm tra gì. **Run** nói tất cả ca sẽ được thực thi bằng cấu hình nào. **Attempt** nói một ca cụ thể thực sự được chạy lần nào.

Một run manifest minh họa:

~~~yaml
runId: policy-eval-2026-05-18-baseline
datasetVersion: policy-eval-v1
executionEnvironment: staging
promptVersion: policy-prompt-v2
modelVersion: model-baseline
embeddingVersion: embedding-v1
corpusVersion: policy-v3
indexVersion: policy-index-v3
pipelineVersion: rag-v1
retrievalTopK: 4
toolSchemaVersion: tools-v1
rubricVersion: policy-rubric-v1
judgeVersion: judge-config-v1
~~~

Đây là định dạng do nhóm tự định nghĩa. Trong dự án thật, phải ghi tên model/provider và thông số thực tế, không tạo phiên bản hư cấu rồi dùng để giải thích kết quả.

### 4.1. Vì sao cần ba định danh riêng?

| Định danh | Mục đích |
| --- | --- |
| `caseId` | Nhận diện tình huống có kỳ vọng cố định |
| `runId` | Nhận diện một đợt đánh giá theo cấu hình cụ thể |
| `attemptId` | Nhận diện một lần thực thi thực tế của case trong run |
| `traceId` | Truy ngược các span trong tracing backend nếu có trace |
| `evaluationId` | Nhận diện một lần chấm bằng metric/rubric/judge cụ thể |

Một case có thể có nhiều attempt trong cùng run để đo độ dao động. Một attempt có thể được chấm lại bởi nhiều rubric/judge mà **không chạy lại model**. Cần giữ verdict cũ và gắn version khác cho verdict mới.

### 4.2. Thiết kế phép thử công bằng

Khi so baseline/candidate, cố định hoặc ghi rõ sự thay đổi của dataset, nguồn chuẩn, corpus/index, prompt, model, tool fixtures, temperature, giới hạn token, rubric, judge và điều kiện tải. Nếu thay cả model và evaluator, pass rate đổi có thể do cách chấm thay vì do chất lượng chatbot.

Đối với model có tính xác suất, một lần chạy không thể mô tả toàn bộ biến thiên. Với ca có rủi ro cao hoặc khi chênh lệch nhỏ, nên chạy lặp và báo số lần thực hiện.

## 5. Giai đoạn C — Tạo phản hồi bằng pipeline Spring AI

Một pipeline RAG điển hình gồm:

~~~text
Question
  → query preprocessing (nếu có)
  → embedding / VectorStore retrieval
  → filter / rerank / chunk selection
  → build effective context
  → ChatClient / ChatModel
  → tool calls (nếu có) và các lần ChatModel tiếp theo
  → final answer + citations
~~~

**Thu evidence ngay tại ranh giới đang tạo dữ liệu**, thay vì cố khôi phục toàn bộ đường đi từ câu trả lời cuối.

### 5.1. Phân biệt ba loại context

| Loại | Định nghĩa | Sử dụng đúng |
| --- | --- | --- |
| **Reference context** | Tài liệu/ngữ cảnh chuẩn được người có chuyên môn xác nhận | Kiểm tra factual correctness và chất lượng retrieval |
| **Retrieved context** | Các `Document` retriever trả về trong lần chạy | Tính hit@k, precision/recall khi có nhãn |
| **Effective context** | Phần ngữ cảnh cuối cùng thực sự đưa vào prompt/model | Kiểm tra groundedness và giải thích hành vi generation |

Ví dụ retriever trả về 8 đoạn, nhưng advisor chỉ đưa 5 đoạn đầu vào prompt để giữ giới hạn token. Khi chấm groundedness, 3 đoạn bị loại **không** phải bằng chứng model đã nhìn thấy. Khi chấm retrieval, cả 8 đoạn có thể vẫn thuộc tập kết quả được đo, tùy định nghĩa metric.

Nếu có tóm tắt, nén ngữ cảnh, đổi thứ tự hoặc định dạng lại, nên lưu phiên bản bước chuyển đổi và nội dung/tham chiếu của **kết quả sau chuyển đổi**.

### 5.2. Ví dụ Java: tạo response và giữ đúng ngữ cảnh đã dùng

Đoạn ví dụ sau minh họa một nhánh RAG **tự ghép prompt**, giúp thấy rõ điểm thu bằng chứng. Đây là mã minh họa trong ứng dụng đã có `VectorStore` và `ChatClient`; phần quản lý run, quyền truy cập, token budget và lưu evidence cần được tích hợp theo dự án.

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;

public final class RagResponseRunner {

    public record ResponseEvidence(
            String question,
            List<Document> retrievedDocuments,
            List<Document> effectiveDocuments,
            String effectiveContext,
            String finalAnswer) {}

    private final VectorStore vectorStore;
    private final ChatClient chatClient;

    public RagResponseRunner(VectorStore vectorStore, ChatClient chatClient) {
        this.vectorStore = vectorStore;
        this.chatClient = chatClient;
    }

    public ResponseEvidence execute(String question) {
        SearchRequest search = SearchRequest.builder()
                .query(question)
                .topK(4)
                .build();

        List<Document> results = vectorStore.similaritySearch(search);
        List<Document> retrieved =
                results == null ? List.of() : List.copyOf(results);

        // Chỉ sử dụng kết quả đã lọc/sắp xếp trong prompt.
        // Ví dụ này đưa toàn bộ retrieved context vào model.
        List<Document> effective = retrieved;

        String context = effective.stream()
                .map(d -> "[" + d.getId() + "] " + d.getText())
                .collect(Collectors.joining("\n\n"));

        String answer = chatClient.prompt()
                .system("""
                        Trả lời bằng tiếng Việt theo tài liệu được cung cấp.
                        Không bịa thông tin nếu tài liệu chưa đủ căn cứ.
                        """)
                .user("Câu hỏi:\n" + question
                        + "\n\nTài liệu:\n" + context)
                .call()
                .content();

        return new ResponseEvidence(
                question, retrieved, effective, context, answer);
    }
}
~~~

Với pipeline có `Advisor` RAG tự động, chỉ gọi `ChatClient` rồi ghi documents ở một chỗ khác **không bảo đảm** đó là context advisor thực sự đưa vào model. Cần thiết kế cách capture ở đúng điểm sau retrieval và sau bước ghép/cắt context. Nếu context chứa dữ liệu nhạy cảm, có thể lưu bằng tham chiếu có phân quyền thay vì ghi raw content vào trace.

### 5.3. Nếu retrieval không tìm được tài liệu

Một run có thể trả danh sách rỗng. Điều đó cần được ghi **rõ ràng**, không thay bằng tài liệu chuẩn từ dataset. Câu trả lời thích hợp có thể là “không đủ dữ liệu” nếu rubric yêu cầu từ chối suy đoán.

Nếu pipeline trả lời sai mà không truy xuất được nguồn, evaluation nên phân biệt:

- **Retrieval failure:** không tìm thấy reference document cần thiết.
- **Answer quality failure:** model tự suy đoán hoặc bịa.
- **Technical failure:** request lỗi/timeout và không có câu trả lời hợp lệ.

Ba nhóm lỗi này có thể đồng thời xuất hiện nhưng không nên bị gộp thành một cờ `error=true`.

## 6. Giai đoạn D — Thu thập evidence của RAG, model và tool

Lưu answer là cần thiết nhưng chưa đủ. Một evidence record nên có dữ liệu thực tế để giải thích **vì sao** answer xuất hiện.

~~~json
{
  "runId": "policy-eval-2026-05-18-baseline",
  "caseId": "POLICY-001",
  "attemptId": "attempt-POLICY-001-01",
  "questionRef": "dataset:POLICY-001",
  "retrieval": {
    "topK": 4,
    "retrievedDocumentIds": [
      "policy-v2#refund-pro",
      "faq-old-refund"
    ],
    "effectiveContextIds": [
      "policy-v2#refund-pro",
      "faq-old-refund"
    ],
    "indexVersion": "policy-index-v3"
  },
  "response": {
    "finalAnswer": "Gói Pro có thể hoàn phí trong 30 ngày.",
    "citationIds": ["policy-v2#refund-pro"]
  },
  "toolInvocations": [],
  "telemetry": {
    "traceId": "example-trace-id",
    "totalLatencyMs": 1420,
    "modelInputTokens": 1250,
    "modelOutputTokens": 78
  }
}
~~~

Các tên trường và con số minh họa; đây **không** phải record tự động có sẵn trong Spring AI. `traceId` chỉ được ghi như một liên kết thật nếu hệ thống tracing đã phát sinh trace đó.

### 6.1. Với tool calling, phải thu thêm hành động thực

Khi model gọi `getOrderStatus`, việc final answer nói “đang giao” không chứng minh nó đã tra backend. Cần có:

- Tên tool thực tế được gọi và định danh lần gọi.
- Đối số thực tế sau bước kiểm tra dữ liệu và quyền.
- Trạng thái tool: `SUCCESS`, `ERROR`, `DENIED`, `TIMEOUT`...
- Dữ liệu tool trả về hoặc tham chiếu an toàn đến kết quả.
- Số lần gọi, thứ tự, retry và thời lượng.
- Với tool có tác dụng phụ, **hậu điều kiện tại backend**: giao dịch có được commit đúng một lần không?

Ví dụ expected tool behavior:

~~~json
{
  "caseId": "ORDER-001",
  "question": "Đơn DH-123 của tôi đang ở đâu?",
  "expectedTool": "getOrderStatus",
  "expectedArguments": {"orderId": "DH-123"},
  "testFixtureResult": {"status": "IN_TRANSIT"},
  "expectedAnswerFacts": ["Đơn đang được giao"],
  "checks": ["toolSelection", "toolArguments", "resultUsage", "authorization"]
}
~~~

Một attempt giả định ghi:

~~~json
{
  "caseId": "ORDER-001",
  "attemptId": "attempt-ORDER-001-01",
  "toolInvocations": [
    {
      "toolCallId": "tool-1",
      "name": "getOrderStatus",
      "arguments": {"orderId": "DH-123"},
      "authorization": "ALLOWED",
      "status": "SUCCESS",
      "result": {"status": "IN_TRANSIT"},
      "durationMs": 180
    }
  ],
  "finalAnswer": "Đơn DH-123 đang được giao."
}
~~~

Các dữ liệu test nên đến từ fake/stub/sandbox đối với tool gây thay đổi trạng thái. **Phân quyền phải được thực thi tại backend/tool**, không thể chỉ giao cho prompt hoặc evaluator.

### 6.2. Với retry và nhiều lượt model

Một request gọi tool có thể dẫn đến:

~~~text
ChatModel call #1 → tool request
Tool invocation #1 → tool result
ChatModel call #2 → final answer
~~~

Có thể có thêm vòng gọi hoặc retry. Vì vậy cần lưu **từng model call** và cộng token usage theo các lời gọi thực tế. Đừng nhầm tổng duration của request với duration của một lời gọi model; cũng đừng mặc định một attempt luôn có một lần gọi model.

### 6.3. Evidence tối thiểu và riêng tư

Một hệ thống vận hành thật không nên gắn nguyên văn prompt, tool args, user ID hay nội dung tài liệu riêng tư làm nhãn metric. Có thể giữ `caseId`, `attemptId`, `traceId`, document IDs/version, trạng thái và tham chiếu đến evidence store có phân quyền, quy tắc che dữ liệu và thời gian lưu.

Nếu không được phép lưu nội dung ngữ cảnh, báo cáo phải chỉ rõ **không đủ evidence để kiểm chứng groundedness trên lần chạy đó**; một metric thành công kỹ thuật không thay thế được nội dung.

## 7. Giai đoạn E — Chấm điểm theo lớp và theo bằng chứng

Sau khi response và evidence đã được thu, cần chấm **từng tiêu chí với nguồn dữ liệu thích hợp**, không dùng một bộ chấm cho mọi vấn đề.

### 7.1. Ma trận nguồn để chấm

| Metric | Kỳ vọng/nguồn chuẩn | Evidence thực tế | Phương pháp phù hợp |
| --- | --- | --- | --- |
| `retrievalHit@k` | Expected doc IDs | Retrieved IDs trong top-k | Assertion |
| `Recall@k` | Bộ tài liệu liên quan đã gắn nhãn đầy đủ | Retrieved IDs | Công thức xác định |
| `answerRelevance` | Câu hỏi + rubric | Final answer | Evaluator hoặc human review |
| `groundedness` | Quy tắc mọi khẳng định cần có bằng chứng | Final answer + **effective context** | Fact-checking/groundedness evaluator |
| `factualCorrectness` | Reference facts/documents đã xác minh | Final answer | Quy tắc + human/LLM judge có rubric |
| `citationAccuracy` | Nguồn chính thức hỗ trợ khẳng định | Citation IDs và nội dung được dẫn | Kiểm tra nguồn |
| `toolSelection` / `toolArguments` | Tool và tham số mong đợi | Actual invocations | Contract assertion |
| `toolResultUsage` | Kết quả tool/fixture | Final answer | Assertion/rubric |
| `toolSideEffect` | Trạng thái backend mong đợi | Hậu điều kiện thực | Integration test |
| `latencyBudget` / `costBudget` | Giới hạn định trước | Timings, tokens, giá | Công thức/threshold |

**Groundedness không phải kiểm tra mọi sự thật ngoài đời.** Nó đánh giá câu trả lời có được context cung cấp hỗ trợ hay không. Để biết câu trả lời có đúng so với chính sách hiện hành, cần reference data độc lập đã được xác minh.

### 7.2. Relevance và fact checking trong Spring AI

Spring AI có abstraction `Evaluator`, `EvaluationRequest`, `EvaluationResponse`. Những evaluator như `RelevancyEvaluator` hỗ trợ đánh giá sự liên quan; `FactCheckingEvaluator` dùng ngữ cảnh để kiểm tra câu trả lời có được hỗ trợ không. Cách tạo bean hoặc builder có thể thay đổi theo phiên bản Spring AI, nên mã ví dụ dưới đây **nhận các evaluator đã được cấu hình sẵn**.

~~~java
import java.util.List;

import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;
import org.springframework.ai.evaluation.Evaluator;

public final class AnswerScoring {

    public record Score(
            String attemptId,
            String metric,
            String rubricVersion,
            boolean passed,
            String feedback) {}

    public List<Score> score(
            String attemptId,
            String question,
            String answer,
            List<Document> effectiveDocuments,
            Evaluator relevanceEvaluator,
            Evaluator groundingEvaluator) {

        EvaluationRequest input = new EvaluationRequest(
                question, effectiveDocuments, answer);

        EvaluationResponse relevance = relevanceEvaluator.evaluate(input);
        EvaluationResponse grounded = groundingEvaluator.evaluate(input);

        return List.of(
                new Score(attemptId, "answerRelevance", "relevance-v1",
                        relevance.isPass(), relevance.getFeedback()),
                new Score(attemptId, "groundedness", "grounding-v1",
                        grounded.isPass(), grounded.getFeedback()));
    }
}
~~~

Trong ví dụ, `effectiveDocuments` phải tương ứng **chính xác** với context model đã sử dụng. Nếu ứng dụng biến đổi/nén tài liệu, cần giữ phiên bản bằng chứng phản ánh biến đổi. Một evaluator nhận source khác sẽ chấm một tình huống khác.

Code trên minh họa đường thành công; workflow thật cần bao quanh evaluator bằng xử lý lỗi, ghi phiên bản judge và lưu trạng thái chưa đánh giá nếu timeout. Không nên diễn giải `isPass()` thành “đã được xác minh mọi sự thật” khi chỉ dùng evaluator kiểm tra theo context.

### 7.3. Kiểm tra xác định trước khi gọi LLM judge

Những điều có thể kiểm chính xác nên dùng assertions:

~~~java
import java.util.List;
import java.util.Set;

public final class DeterministicChecks {

    public static boolean containsRequiredSource(
            List<String> retrievedIds,
            String requiredDocumentId) {
        return retrievedIds.contains(requiredDocumentId);
    }

    public static boolean calledExpectedTool(
            Set<String> actualToolNames,
            String expectedToolName) {
        return actualToolNames.contains(expectedToolName);
    }

    public static boolean withinLatencyBudget(
            long observedMillis,
            long budgetMillis) {
        return observedMillis <= budgetMillis;
    }
}
~~~

Đây là các phép kiểm **một phần**: có đúng tên tool không chưa đủ để bảo đảm đối số, quyền, số lần gọi và hậu điều kiện. Trong RAG, ID tài liệu tồn tại chưa chứng minh tài liệu còn hiệu lực hoặc được model dùng đúng.

### 7.4. Xử lý trường hợp thiếu dữ liệu hoặc evaluator lỗi

Thiết kế verdict nên phân biệt:

| Trạng thái | Khi nào dùng | Ví dụ |
| --- | --- | --- |
| **PASS** | Có đủ evidence, tiêu chí đạt | Answer đúng 14 ngày theo nguồn |
| **FAIL** | Có đủ evidence, tiêu chí không đạt | Answer nêu 30 ngày |
| **NOT_EVALUATED** | Chưa thể chấm do thiếu evidence hoặc evaluator lỗi | Không lưu effective context cần thiết |
| **NOT_APPLICABLE** | Tiêu chí không liên quan case | Case không yêu cầu tool |
| **EXECUTION_ERROR** | Không tạo được response hợp lệ do lỗi runtime | Provider timeout, request thất bại |

Không tự chuyển `NOT_EVALUATED` thành PASS. Nếu một request timeout, không có output để đánh giá chất lượng; nhưng timeout vẫn phải được tính vào technical success rate và end-to-end task success trong phạm vi tương ứng.

## 8. Giai đoạn F — Lưu verdict kèm bằng chứng và metadata chấm

Một verdict đủ thông tin cần trả lời: **ai/điều gì chấm, chấm attempt nào, bằng metric nào, theo rubric nào và dùng evidence nào?**

~~~json
{
  "evaluationId": "eval-POLICY-001-factual-v1",
  "runId": "policy-eval-2026-05-18-baseline",
  "caseId": "POLICY-001",
  "attemptId": "attempt-POLICY-001-01",
  "metric": "factualCorrectness",
  "status": "FAIL",
  "rubricVersion": "policy-rubric-v1",
  "evaluator": {
    "type": "reviewed-rule",
    "version": "factual-v1"
  },
  "feedback": "Câu trả lời nêu 30 ngày, nhưng policy-v3 quy định 14 ngày.",
  "evidenceRefs": [
    "answer:attempt-POLICY-001-01",
    "reference:policy-v3#refund-pro"
  ],
  "traceId": "example-trace-id"
}
~~~

Đây là schema của **hệ thống đánh giá tự thiết kế**, không phải JSON chuẩn có sẵn từ Spring AI. Khi dùng LLM judge, nên lưu `judgeModelVersion`, `judgePromptVersion`, `rubricVersion` và các bằng chứng đầu vào.

### 8.1. Vì sao cần lưu feedback, không chỉ điểm?

Hai ca có `FAIL` cùng metric có thể yêu cầu sửa khác nhau:

- Case A fail vì retriever bỏ mất `policy-v3` → xem index, query, filter, chunk.
- Case B fail dù context có `policy-v3` → xem prompt, cách ghép context, model, sinh câu trả lời.
- Case C fail do tool trả `403` nhưng model báo thành công → xem diễn giải tool và xử lý lỗi.
- Case D fail vì judge hiểu sai rubric → sửa quy trình chấm, không mặc định lỗi ứng dụng.

`feedback` không tự chứng minh nguyên nhân; nó là lý do sơ bộ cần đối chiếu evidence. Các ca quan trọng nên có review của người am hiểu nghiệp vụ.

### 8.2. Một attempt có thể có nhiều verdict

~~~mermaid
erDiagram
    TEST_CASE ||--o{ EXECUTION_ATTEMPT : "chạy nhiều lần"
    EVALUATION_RUN ||--o{ EXECUTION_ATTEMPT : "chứa"
    EXECUTION_ATTEMPT ||--o{ EVIDENCE : "thu được"
    EXECUTION_ATTEMPT ||--o{ EVALUATION_VERDICT : "chấm nhiều metric"
    EVALUATION_VERDICT }o--o{ EVIDENCE : "tham chiếu"
~~~

Nếu chấm lại cùng attempt bằng judge mới, hãy tạo một verdict mới với version/evaluation ID riêng. Giữ verdict cũ để biết điểm thay đổi do **ứng dụng** hay do **bộ chấm**.

## 9. Giai đoạn G — Tổng hợp theo dataset và so sánh phiên bản

Khi chạy nhiều ca, mỗi metric có thể có mẫu số khác nhau. Cần lưu số:

- `attemptedCount`: số attempt đã thử.
- `technicalCompletedCount`: số attempt tạo phản hồi hợp lệ về kỹ thuật.
- `evaluatedCount`: số attempt có verdict PASS/FAIL cho metric.
- `passedCount`, `failedCount`, `notEvaluatedCount`.
- Số case quan trọng bị hồi quy và các nhóm lỗi.

Ví dụ giả định:

~~~text
Run candidate-v2
  Attempts attempted:                 100
  Technical completions:               96
  Groundedness evaluated:              93
  Groundedness PASS:                   89
  Groundedness FAIL:                    4
  Groundedness NOT_EVALUATED:           3
  Execution errors:                     4
~~~

Tỷ lệ groundedness **trên ca đã chấm**:

\[
\mathrm{passRate}_{\mathrm{evaluated}}=\frac{89}{93}\approx95{,}7\%.
\]

Tỷ lệ technical completion:

\[
\mathrm{technicalCompletion}=\frac{96}{100}=96\%.
\]

Không nên công bố “95,7% toàn bộ request thành công về chất lượng” vì có 4 request lỗi kỹ thuật và 3 response chưa chấm được. Nếu định nghĩa end-to-end success yêu cầu response hoàn tất **và** groundedness PASS, cần công bố cách đếm và mẫu số riêng, xử lý những ca thiếu nhãn theo chính sách đã xác định.

### 9.1. Báo cáo theo nhóm

| Nhóm case | Số đã chấm | PASS | FAIL | Nhận xét |
| --- | ---: | ---: | ---: | --- |
| Chính sách có nguồn | 40 | 39 | 1 | 1 ca sai trích dẫn |
| Chính sách nguồn mâu thuẫn | 20 | 15 | 5 | Cần xem phiên bản nguồn |
| Thiếu thông tin | 15 | 11 | 4 | Model còn tự đoán |
| Tool calling | 18 | 17 | 1 | Một ca diễn giải sai tool result |

Bảng là minh họa cho **các nhóm có số ca đã chấm**; tổng mẫu riêng không nhất thiết bằng ví dụ 100 attempts trước đó. Việc báo chi tiết từng nhóm quan trọng hơn chỉ nhìn một tỷ lệ chung vì lỗi dễ tập trung ở nhóm rủi ro.

### 9.2. So baseline và candidate bằng cùng quy tắc

Ví dụ thay `top-k` từ 3 lên 5, giữ model/prompt/dataset/rubric/nguồn tương đương:

| Metric trên cùng tập đánh giá | Baseline | Candidate | Cần xem thêm |
| --- | ---: | ---: | --- |
| Retrieval hit@k | 87% | 94% | Nguồn nào mới tìm được? |
| Answer relevance PASS | 92% | 95% | Ca nào tăng/giảm? |
| Groundedness PASS | 97% | 94% | Có tài liệu nhiễu/cũ trong context? |
| Factual correctness PASS | 96% | 93% | Có dùng sai phiên bản chính sách? |
| p95 latency | 2,0 giây | 3,1 giây | Retrieval hay model chậm? |
| Input tokens trung bình | 1.200 | 2.050 | Prompt có dài hơn không? |
| Chi phí model ước tính/request | 0,004 USD | 0,006 USD | Tăng có xứng đáng với chất lượng? |

Các số liệu **giả định**. Candidate có hit@k cao hơn nhưng chất lượng cuối và độ trễ kém hơn. Không thể kết luận “tăng `top-k` là tốt” nếu chỉ nhìn retrieval metric. Cần truy lại những ca chuyển PASS→FAIL và điều tra context/trace.

### 9.3. Release gate phải tách rủi ro

Một gate minh họa:

~~~yaml
releaseGates:
  datasetVersion: policy-eval-v1
  rubricVersion: policy-rubric-v1
  functional:
    authorizationAndToolContract: must-pass
  quality:
    factualCorrectnessPassRate: ">= 0.98"
    groundednessPassRate: ">= 0.95"
    criticalCases: must-pass
    notEvaluatedCriticalCases: 0
  operations:
    p95LatencyMs: "<= 2500"
    technicalErrorRate: "<= 0.01"
~~~

Đây là ngưỡng dành cho bài tập, không phải tiêu chuẩn Spring AI. Lỗi phân quyền tool hoặc lộ dữ liệu không thể “bù” bằng relevance cao. Chọn gate dựa trên rủi ro, chất lượng dataset, độ tin cậy bộ chấm và mức tải thực.

## 10. Giai đoạn H — Gắn chấm điểm với observability

Evaluation trả lời **kết quả có đạt không**; observability giải thích **request đã làm gì, tốn bao lâu và lỗi ở đâu**. Trong Spring AI, cơ chế observation của hệ sinh thái Spring/Micrometer có thể cung cấp metrics/traces cho `ChatClient`, `ChatModel`, `Advisors`, `VectorStore` và tool calls tùy phiên bản và cấu hình.

### 10.1. Trace giúp khoanh vùng lỗi và độ trễ

~~~text
HTTP POST /ask                                  3.0 s
└── ChatClient                                  2.8 s
    ├── RAG / VectorStore query                 0.4 s
    ├── ChatModel call #1                       1.0 s
    ├── Tool getOrderStatus                     0.3 s
    └── ChatModel call #2                       1.1 s
~~~

Một trace thường có các span cha–con; không cộng thời gian span cha với các span con như những khoản độc lập. Trong request streaming, nên phân biệt `time to first token` với tổng thời gian hoàn tất nếu cần đo trải nghiệm.

Các tên span/metric được instrument thực tế có thể khác nhau theo Spring AI/Spring Boot/provider. Nếu trace bị lấy mẫu và không xuất hiện, báo **không có trace** thay vì tạo ID giả.

### 10.2. Cấu hình ban đầu minh họa

Với ứng dụng Spring Boot có Actuator, registry và tracing dependencies phù hợp:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  tracing:
    sampling:
      probability: 0.1
~~~

Cấu hình này minh họa việc bật endpoint và lấy mẫu trace. `/actuator/prometheus` yêu cầu registry Prometheus tương thích; cần cấu hình exporter/collector cho traces. Phải bảo vệ endpoint vận hành và cân nhắc không ghi raw prompt, completion, tool arguments theo mặc định.

### 10.3. Token usage và chi phí

Nếu provider trả usage của mỗi model call, chi phí ước tính theo bảng giá tương ứng có thể tính:

\[
\mathrm{modelCost}=
\frac{\mathrm{inputTokens}\times \mathrm{inputPricePerMillion}}{10^6}
+
\frac{\mathrm{outputTokens}\times \mathrm{outputPricePerMillion}}{10^6}.
\]

Ví dụ giá **giả định** 2 USD/triệu input token và 8 USD/triệu output token; 2.000 input và 500 output tokens tương đương:

\[
(2000\times2+500\times8)/10^6=0{,}008\;\mathrm{USD}.
\]

Nếu một request có hai lời gọi model do tool calling, cộng usage của cả hai. Tổng chi phí còn có thể bao gồm embedding, reranking, vector store, tool backend, evaluator và retry; usage có thể khác nhau theo provider và streaming. Đây là **ước tính theo giả định**, không phải số tiền hóa đơn chắc chắn.

### 10.4. Phân biệt metric tổng và evidence từng attempt

| Tín hiệu | Thuộc phạm vi | Dùng để làm gì |
| --- | --- | --- |
| `traceId`, tool events, retrieved docs | Một attempt cụ thể | Điều tra một case FAIL |
| Token input/output của model call | Một lời gọi model | Tính usage và chi phí request |
| p95 latency | Tập request trong cửa sổ đo | Phát hiện nhóm request chậm |
| Quality pass rate | Các ca được chấm hợp lệ | So sánh chất lượng theo rubric |
| Error rate | Tất cả request thuộc phạm vi vận hành | Phát hiện lỗi kỹ thuật |

Không thể suy p95 chỉ từ `count` và `sum` của timer; cần histogram hoặc phân bố dữ liệu phù hợp. Không thể suy factual correctness chỉ từ HTTP 200 hay metrics của model.

## 11. Giai đoạn I — Hoàn thiện luồng cho RAG có tool calling

Trong thực tế, một request có thể vừa truy xuất tài liệu, vừa gọi tool lấy thông tin động và sinh câu trả lời sau khi có kết quả tool. Workflow phải giữ **thứ tự và nguyên nhân** của từng bước:

~~~mermaid
sequenceDiagram
    participant E as Evaluation runner
    participant A as Spring AI app
    participant R as Retriever
    participant M as ChatModel
    participant T as Tool/backend
    participant S as Scoring stage

    E->>A: case input + attempt ID
    A->>R: query + filter
    R-->>A: retrieved docs
    Note over A: Lưu retrieved và effective context
    A->>M: prompt + effective context
    M-->>A: tool call request
    A->>T: tool name + args sau kiểm tra quyền
    T-->>A: tool result / error
    A->>M: result + next messages
    M-->>A: final answer
    A-->>E: answer + tool events + evidence refs
    E->>S: expectation + actual evidence
    S-->>E: verdicts + feedback
~~~

Không phải ca nào cũng có tool; với một số model/framework, thứ tự callbacks hoặc cách tool execution được instrument có thể khác. Sơ đồ chỉ mô tả những bằng chứng **phải liên kết**.

### 11.1. Ba trạng thái lỗi cần phân biệt

**Retrieval sai:** không tìm thấy `policy-v3`. Chỉ số hit@k fail; ưu tiên điều tra index, bộ lọc, chunk, embedding.

**Tool sai:** model gọi `refundOrder` thay cho `getOrderStatus`, hoặc tool trả `403` nhưng answer nói thành công. Kiểm tra tool events, backend và cách model nhận/diễn giải kết quả.

**Generation sai:** document hoặc tool result đúng đã có, nhưng answer diễn giải sai. Kiểm tra prompt, effective context, model và rubric chấm.

Các lỗi có thể đồng thời xảy ra. Một case FAIL không nên bị gắn nhãn nguyên nhân duy nhất khi evidence chưa đủ.

### 11.2. Test contract của tool trước khi chấm ngữ nghĩa

Với tool có thể tạo giao dịch, cần test xác định:

1. Người dùng có quyền với đối tượng không?
2. Có cần xác nhận hành động không?
3. Tham số đúng schema và nghiệp vụ không?
4. Tool thực thi đúng số lần, không gây tác dụng phụ lặp?
5. Hậu điều kiện có đúng ở hệ thống nguồn không?

Nếu các câu trên không đạt, chấm relevance của final answer không thể “hợp thức hóa” hành động sai. Dùng test double/sandbox khi chạy dataset có thao tác làm thay đổi dữ liệu.

## 12. Lưu kết quả sao cho có thể chạy lại và truy vết

Một cách tổ chức ví dụ:

~~~text
evaluation/
└── policy-eval-2026-05-18-baseline/
    ├── run-manifest.json
    ├── attempts.jsonl
    ├── retrieval-evidence.jsonl
    ├── tool-events.jsonl
    ├── evaluation-verdicts.jsonl
    └── summary.json
~~~

Đây là cấu trúc gợi ý; không phải thư mục mặc định của Spring AI và không có nghĩa ứng dụng cần lưu raw content trong mọi file.

### 12.1. Những invariant nên được kiểm

- Mỗi `attemptId` thuộc đúng một `runId` và `caseId`.
- Mỗi verdict tham chiếu đúng attempt, metric và rubric/judge version.
- Những retrieved/context/tool evidence được dùng để chấm thuộc **chính attempt đó**.
- Không ghép answer của attempt A với context của attempt B.
- Nếu thiếu evidence cần thiết, verdict là `NOT_EVALUATED` thay vì PASS.
- Nếu chấm lại cùng attempt bằng judge mới, kết quả cũ vẫn được giữ.
- Các ca lỗi kỹ thuật và chưa chấm phải được báo trong tổng số attempts.

### 12.2. Khi nào có thể chấm lại mà không chạy pipeline?

Nếu lưu đủ **actual answer, effective context, reference facts và rubric**, có thể chạy một evaluator mới trên cùng execution evidence để kiểm tra sai lệch của bộ chấm. Việc đó **không tạo lại retrieval**, **không đo lại latency** và **không chứng minh hành vi tool cũ** nếu các bằng chứng ấy không được ghi. Khi thay corpus/index/tool, phải chạy pipeline lại để đo kết quả mới.

## 13. Mở rộng từ offline sang giám sát chất lượng production

Offline evaluation dùng ca đã biết và nguồn có nhãn. Production có lượng câu hỏi lớn, thay đổi liên tục và thường thiếu reference answer ngay lúc request đến. Do đó không thể đưa mọi request thật vào cùng pipeline đánh giá với giả định có ground truth.

Một workflow online thực dụng:

~~~text
Production request
  → ứng dụng Spring AI xử lý và phát safe telemetry
  → chọn mẫu theo policy rõ ràng
  → tạo review record với evidence refs được phép lưu
  → kiểm tra xác định + evaluator + human review nếu cần
  → cập nhật PASS / FAIL / PENDING / NOT_EVALUATED
  → tổng hợp theo release và nhóm yêu cầu
  → điều tra lỗi có bằng chứng
  → đưa ca đã xác minh vào regression dataset
~~~

### 13.1. Mẫu số và lệch chọn mẫu

Giả sử có 10.000 request thật, chọn 300 để review, chấm được 240 và có 216 PASS. **Tỷ lệ PASS trên tập đã chấm** là `216/240=90%`; đây chưa phải tỷ lệ đúng trên toàn bộ 10.000 request nếu không chứng minh tính đại diện và xử lý các nhãn còn thiếu.

Mẫu lấy theo rủi ro (ưu tiên câu có tool lỗi, nguồn mâu thuẫn, phản hồi tiêu cực) rất hữu ích để **tìm lỗi**, nhưng có thể làm tỷ lệ FAIL cao hơn phân bố traffic thật. Cần lưu sampling policy, tỷ lệ chọn mẫu, nhóm trường hợp và trạng thái chờ nhãn.

### 13.2. Khi điểm giảm, có thể do những nguyên nhân khác nhau

| Biểu hiện | Giả thuyết cần kiểm |
| --- | --- |
| Pass rate giảm, traffic nhiều câu khó hơn | Input distribution shift |
| Pass rate giảm sau đổi prompt, các nhóm tương tự nhau | Quality regression |
| Groundedness giảm, retrieval hit@k giảm | Retrieval/corpus/index |
| Groundedness giảm, retrieval không đổi | Prompt/model/context assembly |
| Verdict đổi nhưng answer/evidence giữ nguyên | Judge/rubric thay đổi |
| p95 tăng, tool span tăng | Tool/backend latency hoặc retry |
| Token tăng, factuality không cải thiện | Context dư, prompt dài hoặc model calls tăng |

Một tương quan thời gian trên dashboard chưa chứng minh quan hệ nhân quả. Dùng case và trace để hình thành giả thuyết, rồi kiểm tra bằng thay đổi có kiểm soát.

## 14. Bài thực hành hoàn chỉnh

**Bối cảnh:** xây chatbot Spring AI RAG trả lời chính sách giả định của *Sao Mai*, có thêm tool đọc trạng thái đơn hàng. Mục tiêu là tạo một workflow offline đánh giá đủ bằng chứng rồi mở rộng sang observability.

### Phần A — Một ca và một attempt

Tạo ca `POLICY-001` có question, reference facts, expected document và rubric. Chạy ứng dụng một lần. Ghi `runId`, `attemptId`, retrieved docs, effective context, answer, citations và latency.

**Kiểm tra:** nếu model nói “30 ngày”, phải chỉ ra nó có hay không có `policy-v3` trong context thực tế.

### Phần B — Chấm nhiều lớp

Chấm retrieval hit@k bằng assertion; chấm relevance/groundedness bằng evaluator; chấm factual correctness so với reference policy. Tách PASS/FAIL/NOT_EVALUATED và ghi lý do.

**Kiểm tra:** một câu có thể relevance PASS, groundedness PASS theo nguồn cũ nhưng factual correctness FAIL theo chính sách hiện hành.

### Phần C — Thêm tool calling

Tạo ca `ORDER-001`, fixture backend trả `IN_TRANSIT` cho đơn `DH-123`. Thu tool invocation thực và final answer. Chấm tool name, args, authorization, result usage và latency.

**Kiểm tra:** nếu chatbot đoán “đang giao” mà không gọi tool bắt buộc, tool-behavior phải FAIL dù câu chữ trùng expected answer.

### Phần D — Mở rộng dataset và so phiên bản

Tạo thêm 15–20 ca về nguồn mâu thuẫn, thiếu dữ liệu, lỗi tool và câu hỏi đa điều kiện. Chạy baseline rồi candidate với một thay đổi có chủ đích như `top-k=3` → `top-k=5`. Lập bảng điểm theo nhóm, ghi các ca PASS→FAIL và so token/cost/latency.

**Kiểm tra:** không chọn candidate chỉ vì hit@k tăng nếu groundedness hoặc factual correctness giảm.

### Phần E — Gắn telemetry và feedback

Bật metrics/traces phù hợp, thu trace cho các attempt khi có, tính latency và usage. Mô phỏng một mẫu request production, ghi tình trạng được chấm/chưa chấm. Chọn một lỗi đã xác minh để bổ sung vào regression set.

**Kiểm tra:** có thể đi từ verdict của case FAIL tới actual context, tool events và trace để đề xuất đúng vị trí cần sửa.

### Checklist nghiệm thu

- [ ] Case có ID, câu hỏi, reference facts và rubric version.
- [ ] Run có dataset/prompt/model/corpus/index/pipeline versions.
- [ ] Attempt lưu answer thật và tài liệu thật; expectation tách khỏi execution.
- [ ] Có cả retrieved context và effective context khi chúng có thể khác nhau.
- [ ] Verdict có metric, trạng thái, feedback và evidence references.
- [ ] Kiểm tra xác định chạy cho document IDs, tool args/quyền/hậu điều kiện.
- [ ] Evaluator ngữ nghĩa có version và xử lý NOT_EVALUATED.
- [ ] Báo cáo pass rate ghi mẫu số và số ca bị lỗi/chưa chấm.
- [ ] Có số liệu error rate, latency, token và cost phù hợp.
- [ ] Một case FAIL có thể truy ngược tới attempt và trace khi có.
- [ ] Candidate được so với baseline trên phạm vi tương đương.
- [ ] Ca lỗi production đã xác minh có thể thêm vào dataset hồi quy.

### Câu hỏi tự kiểm tra

1. Vì sao `referenceDocuments` và `retrievedDocuments` phải là hai trường khác nhau?
2. Nếu retriever trả 8 đoạn nhưng model chỉ nhận 5 đoạn, nên chấm groundedness dựa trên tập nào?
3. Khi answer nói “30 ngày” và context thực tế là tài liệu cũ ghi “30 ngày”, relevance, groundedness và factual correctness có thể khác nhau thế nào?
4. Vì sao một `caseId` có thể có nhiều `attemptId`?
5. Nếu evaluator timeout sau khi response được tạo thành công, nên ghi trạng thái nào và tính vào chỉ số nào?
6. Nếu tool trả `403` nhưng chatbot nói “thành công”, cần thu thêm evidence gì?
7. Khi `top-k` tăng mà input tokens và p95 latency tăng, cần kiểm tra bước nào trước khi quyết định triển khai?
8. Một pass rate `89/93` có thể được công bố là “89% của 100 request thành công” không? Vì sao?
9. Có thể chấm lại một attempt bằng judge mới mà không chạy lại RAG không? Điều kiện nào cần được đáp ứng?
10. Khi benchmark tốt nhưng production giảm chất lượng, cần kiểm tra traffic mix, nguồn tài liệu và judge như thế nào?

## 15. Tổng kết

Tổ chức workflow đánh giá trong Spring AI là xây dựng một chuỗi có thể truy vết: **dataset và rubric → run có phiên bản → execution attempt → retrieved/effective context, tool events, final answer → evaluator verdict → báo cáo và bằng chứng vận hành**.

Trong chuỗi đó, **evaluation** dùng relevance, groundedness, factual correctness và kiểm tra hành vi để xác định kết quả đáp ứng yêu cầu tới đâu; **observability** dùng metrics, traces, token, chi phí và độ trễ để giải thích một lần chạy đã diễn ra thế nào và nguyên nhân nào đáng điều tra. Khi giữ riêng expectation, actual evidence và verdict, nhóm có thể tìm đúng khâu retrieval, generation hay tool gây lỗi, đồng thời so sánh các phiên bản prompt, model và pipeline một cách có cơ sở.

### Tài liệu tham khảo

- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI — Vector Store API](https://docs.spring.io/spring-ai/reference/api/vectordbs.html)
- [Spring Boot — Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
