# Lộ trình từ một ca đánh giá đến theo dõi toàn bộ ứng dụng

Khi mới xây dựng chatbot với Spring AI, nhiều nhóm chỉ kiểm thử bằng một câu hỏi: gửi yêu cầu, đọc câu trả lời và nhận định “có vẻ đúng”. Khi có người dùng thật, cách làm này nhanh chóng mất hiệu quả. Nhóm phải trả lời những câu hỏi khó hơn: phiên bản prompt mới có làm hỏng câu cũ không, bộ truy xuất có lấy đúng tài liệu không, lời gọi công cụ có tuân thủ quyền không, p95 latency tăng ở bước nào, và chi phí trên mỗi nhiệm vụ thành công đã thay đổi ra sao?

Một lộ trình phù hợp bắt đầu rất nhỏ: **một trường hợp đánh giá có kỳ vọng và bằng chứng rõ ràng**. Sau đó mở rộng có kiểm soát thành dataset, kiểm thử nhiều lớp, điều kiện phát hành và hệ thống quan sát production. Mỗi chặng tạo một đầu ra có thể kiểm chứng trước khi chuyển sang chặng tiếp theo.

Trong module **SPRING_AI_EVALUATION_OBSERVABILITY**, mục tiêu cuối cùng là kết hợp đánh giá chất lượng bằng tập dữ liệu, relevance, fact checking và kiểm thử RAG/tool calling với đo metrics, traces, token, chi phí và độ trễ. Kết quả phải giúp nhóm xác định nguyên nhân suy giảm theo từng phiên bản prompt, model hoặc pipeline.

## 1. Bạn sẽ xây dựng được gì?

Sau bài học, người học có thể:

- Xác định một **ca đánh giá tối thiểu** gồm câu hỏi, kỳ vọng, nguồn chuẩn, rubric và điều kiện đạt.
- Lưu **bằng chứng thực thi**: answer thực tế, tài liệu RAG thực tế, lời gọi tool, phiên bản cấu hình và trace.
- Mở rộng một ca thành dataset có độ bao phủ, nhãn, nhóm rủi ro và kết quả so sánh baseline/candidate.
- Tổ chức cách chấm relevance, groundedness, factual correctness và hành vi tool mà không trộn lẫn chúng.
- Tích hợp bộ đánh giá vào kiểm thử định kỳ/CI với các release gate cụ thể.
- Bật cơ chế quan sát của Spring AI/Spring Boot, đọc latency, lỗi, token và chi phí theo từng bước.
- Thiết kế theo dõi chất lượng khi vận hành với lấy mẫu, nhãn được xác minh và xử lý dữ liệu nhạy cảm.
- Khép vòng phản hồi: lỗi production → xác minh bằng chứng → thêm case hồi quy → chạy lại trước phát hành.

Đây là bài **lộ trình triển khai**, vì vậy mỗi giai đoạn đều có mục đích, đầu vào, công việc và một tiêu chí hoàn thành.

## 2. Sơ đồ toàn bộ lộ trình

~~~mermaid
flowchart TD
    A["0. Chọn nhiệm vụ và nguồn đúng"] --> B["1. Viết một ca đánh giá"]
    B --> C["2. Chạy và thu evidence thật"]
    C --> D["3. Chấm bằng rubric và assertions"]
    D --> E["4. Mở rộng thành dataset"]
    E --> F["5. So baseline và candidate"]
    F --> G{"Đạt release gate?"}
    G -- "Không" --> H["Sửa thành phần gây lỗi"]
    H --> F
    G -- "Có" --> I["6. Triển khai có kiểm soát"]
    I --> J["7. Metrics, traces, online quality"]
    J --> K["8. Điều tra và thêm ca hồi quy"]
    K --> E
~~~

Đừng hiểu các bước như những sản phẩm độc lập. **Cùng một ca kiểm thử** cần được liên kết qua các chặng bằng `caseId`, `runId` và `attemptId`. Khi phân tích một ca sai trên dashboard, nhóm phải tìm lại được kỳ vọng ban đầu, output thực tế và kết quả chấm của đúng lần chạy đó.

### Bản đồ đầu ra của từng chặng

| Chặng | Sản phẩm tối thiểu | Câu hỏi phải trả lời được |
| --- | --- | --- |
| 0. Xác định phạm vi | Nhiệm vụ, nguồn sự thật, rủi ro, ngân sách | “Đúng” nghĩa là gì? |
| 1. Một ca | Case có input, expected facts, rubric | Tình huống này đạt hay trượt thế nào? |
| 2. Bằng chứng | Attempt có answer, context, tool events | Ứng dụng thực sự làm gì? |
| 3. Chấm | Verdict có lý do và phiên bản bộ chấm | Vì sao đạt/trượt? |
| 4. Dataset | Nhiều ca và phân nhóm, có phiên bản | Bộ đánh giá bao phủ lỗi nào? |
| 5. So sánh | Báo cáo baseline/candidate, gate | Có thể phát hành phiên bản mới không? |
| 6. Triển khai | Staging/canary, rollback criteria | Phiên bản mới có an toàn khi đưa vào lưu lượng thật? |
| 7. Quan sát | Metrics, traces, mẫu chất lượng | Chất lượng và hiệu năng thực tế đang thay đổi ra sao? |
| 8. Phản hồi | Root-cause note và regression case mới | Làm sao tránh lỗi tái diễn? |

## 3. Chặng 0 — Chọn một nhiệm vụ đủ nhỏ và nguồn chuẩn

Dùng một chatbot nội bộ giả định cho dịch vụ *Sao Mai*. Hệ thống có thể trả lời chính sách hoàn phí từ tài liệu bằng RAG và đọc trạng thái đơn hàng qua tool.

Để thực hành, thống nhất **dữ liệu giả định**, không phải chính sách của doanh nghiệp thật:

- Tài liệu chính thức hiện hành `policy-v3#pro-refund`: gói Pro có thời hạn yêu cầu hoàn phí **14 ngày kể từ ngày mua**.
- Tài liệu `policy-v2#pro-refund` đã hết hiệu lực: từng quy định **30 ngày**.
- Tool `getOrderStatus` trả trạng thái hiện tại của đơn khi backend xác thực quyền truy cập.
- Nếu tài liệu không nói tới ngoại lệ, chatbot không được tự tạo ra ngoại lệ.

Ba nhóm mục tiêu cần tách ngay từ đầu:

| Mục tiêu | Kỳ vọng | Phép đo |
| --- | --- | --- |
| **Đúng nghiệp vụ** | Nêu đúng 14 ngày, không dùng chính sách cũ | Factual correctness so với nguồn hiện hành |
| **Đúng luồng xử lý** | Có tài liệu RAG phù hợp, gọi tool khi cần, không vượt quyền | Retrieval/tool assertions |
| **Đúng mức dịch vụ** | Trả lời trong ngưỡng thời gian và ngân sách đã xác định | Latency, error rate, token, cost |

Không cần định nghĩa tất cả SLO của một hệ thống lớn ở chặng đầu tiên. Hãy chọn một ngưỡng thực hành có thể đo và ghi rõ rằng đó là **giả định của bài tập**, chẳng hạn “p95 latency dưới 2,5 giây khi chạy bộ tải đã chọn”.

**Tiêu chí hoàn thành chặng 0:** có mô tả nhiệm vụ, nguồn chuẩn và ít nhất một lỗi không chấp nhận. Không phát biểu chung chung “model phải thông minh”.

## 4. Chặng 1 — Viết ca đánh giá đầu tiên

Một ca chất lượng tốt không chỉ có câu hỏi và một đoạn đáp án lý tưởng. Cần đủ thông tin để người khác độc lập quyết định đúng/sai.

~~~json
{
  "datasetVersion": "refund-eval-v1",
  "caseId": "REFUND-001",
  "question": "Gói Pro có thể yêu cầu hoàn phí trong bao lâu?",
  "referenceDocumentIds": ["policy-v3#pro-refund"],
  "expectedFacts": [
    "Thời hạn là 14 ngày kể từ ngày mua"
  ],
  "forbiddenClaims": [
    "Thời hạn là 30 ngày",
    "Hoàn phí vô điều kiện"
  ],
  "expectedRetrievalIds": ["policy-v3#pro-refund"],
  "expectedBehavior": "Nêu thời hạn và dẫn nguồn hiện hành",
  "tags": ["rag", "vi", "policy", "factual"],
  "rubricVersion": "refund-rubric-v1"
}
~~~

Tại sao cần nhiều trường?

**`question`** xác định đầu vào thực. **`expectedFacts`** chứa thông tin bắt buộc đúng, nhưng không ép model dùng đúng từng chữ. **`forbiddenClaims`** liệt kê các kết luận đặc biệt nguy hiểm hoặc sai. **`referenceDocumentIds`** là nguồn để xác minh tính đúng theo nghiệp vụ. **`expectedRetrievalIds`** là nhãn phục vụ đánh giá retriever; nó chưa nói gì về dữ liệu thực sự được tìm thấy. **`rubricVersion`** giúp biết ca được chấm theo tiêu chí nào.

### 4.1. Viết rubric không mơ hồ

Cho câu trên, thiết lập:

| Tiêu chí | PASS khi | FAIL khi |
| --- | --- | --- |
| Relevance | Trả lời trực tiếp thời hạn hoàn phí gói Pro | Chỉ nói về giá gói hoặc chủ đề khác |
| Factual correctness | Thời hạn 14 ngày kể từ ngày mua, không mâu thuẫn nguồn hiện hành | Nêu 30 ngày hoặc quy định sai |
| Groundedness | Mọi khẳng định quan trọng được context thực tế đưa vào model hỗ trợ | Thêm điều kiện không có trong context |
| Retrieval hit@k | Nguồn `policy-v3#pro-refund` có trong top-k được chấm | Không tìm được nguồn bắt buộc |
| Citation accuracy | Trích dẫn đúng nguồn hỗ trợ khẳng định | Dẫn nguồn không liên quan/hết hiệu lực |

Trong thực tế, các tiêu chí có thể cần mức `UNKNOWN` nếu thiếu evidence và `NOT_APPLICABLE` nếu không liên quan. Không có retrieved context thì **không thể khẳng định** groundedness đã đạt, dù câu trả lời tình cờ đúng 14 ngày.

### 4.2. Một ca nên chứa tình huống âm

Ngay khi có một ca cơ bản, thêm một ca hỏi thông tin **không được tài liệu xác nhận**:

> “Nếu tôi mua gói Pro bằng mã khuyến mãi thì có được hoàn phí sau 30 ngày không?”

Nếu chính sách đã biết không quy định ngoại lệ đó, rubric cần ghi kỳ vọng “không tự khẳng định được ngoại lệ; thừa nhận thiếu dữ liệu và hướng dẫn kiểm tra kênh có thẩm quyền”. Đây là bước đầu đánh giá **khả năng từ chối suy đoán**.

**Tiêu chí hoàn thành chặng 1:** một người khác có thể đọc case và giải thích rõ vì sao câu “30 ngày” trượt, còn câu “14 ngày” có nguồn hợp lệ đạt.

## 5. Chặng 2 — Chạy ứng dụng và ghi bằng chứng thực thi

Sau khi có case, chạy câu hỏi qua **pipeline thật đang thử nghiệm**. Kết quả phải ghi riêng với kỳ vọng.

~~~mermaid
flowchart LR
    T["Test case"] --> R["Spring AI app"]
    R --> V["Retriever"]
    V --> C["Context vào model"]
    C --> M["ChatModel"]
    M --> O["Answer + citations"]
    R -.-> E["Execution evidence"]
    V -.-> E
    C -.-> E
    M -.-> E
    O -.-> E
~~~

Các dữ kiện cần nắm theo **đúng một attempt**:

- `runId`: một đợt đánh giá với cấu hình cụ thể.
- `attemptId`: một lần thực thi câu hỏi; nếu chạy lặp, tạo attempt khác.
- `promptVersion`, `modelVersion`, `pipelineVersion`, `corpusVersion`, `indexVersion`.
- Document IDs, phiên bản, thứ tự được truy xuất và các đoạn thực tế đưa vào model.
- Answer thực tế và citations.
- Tool events thực tế nếu có: tên, đối số an toàn, trạng thái, kết quả, hậu điều kiện.
- Trace ID, số model calls, lỗi/retry, latency và usage nếu sẵn có.

Ví dụ attempt giả định:

~~~json
{
  "runId": "baseline-rag-v1",
  "caseId": "REFUND-001",
  "attemptId": "baseline-rag-v1-REFUND-001-1",
  "configuration": {
    "promptVersion": "policy-prompt-v1",
    "modelVersion": "model-baseline",
    "pipelineVersion": "rag-v1",
    "corpusVersion": "policy-corpus-v3",
    "topK": 3
  },
  "retrieval": [
    {"documentId": "policy-v2#pro-refund", "rank": 1}
  ],
  "actualContextDocumentIds": ["policy-v2#pro-refund"],
  "answer": "Gói Pro được hoàn phí trong 30 ngày.",
  "citations": ["policy-v2#pro-refund"],
  "toolCalls": [],
  "telemetry": {
    "traceId": "example-baseline-trace-1",
    "totalLatencyMs": 1100,
    "modelInputTokens": 1300,
    "modelOutputTokens": 82
  }
}
~~~

Đây là **schema minh họa do ứng dụng tự lưu**, không phải một định dạng Spring AI tự sinh. Nó cho thấy lỗi có thể bắt đầu từ việc lấy nguồn đã hết hiệu lực.

### 5.1. Expected và actual phải tách riêng

Nếu ca mong `policy-v3` nhưng ứng dụng chỉ truy xuất `policy-v2`, **không được** thay danh sách `actualContextDocumentIds` bằng danh sách `expectedRetrievalIds` khi chấm. Làm vậy sẽ khiến evaluator nhìn thấy dữ liệu lý tưởng thay vì dữ liệu ứng dụng thật có, che mất retrieval failure.

Nếu một advisor cắt bớt context vì giới hạn token, nên ghi cả:

1. Tài liệu retriever ban đầu trả về.
2. Tài liệu hoặc nội dung cuối cùng model thực sự nhìn thấy, theo chính sách logging/evidence đã cho phép.

Hai tập này có thể khác nhau. Để chấm groundedness, cần sử dụng context **thực sự có trong prompt cuối**, không mặc định toàn bộ retrieved documents đều được model xem.

### 5.2. Nếu chưa có trace thì sao?

Ở ca đầu tiên, có thể thu output, retrieved IDs và duration bằng test harness. `traceId` chỉ được ghi nếu request có trace thật; không tự tạo chuỗi bất kỳ rồi xem như trace đã tồn tại. Tracing sẽ được bổ sung ở chặng observability.

**Tiêu chí hoàn thành chặng 2:** với một `attemptId`, có thể tìm được answer thật và tài liệu thật đã dùng; không cần đoán điều gì đã xảy ra.

## 6. Chặng 3 — Chấm ca đầu tiên và giải thích nguyên nhân

Đưa expectation và execution evidence vào phép chấm phù hợp. Với dữ liệu ở trên:

| Tiêu chí | Verdict minh họa | Lý do |
| --- | --- | --- |
| Relevance | PASS | Câu trả lời nói đúng chủ đề thời hạn gói Pro |
| Retrieval hit@3 | FAIL | Không tìm thấy `policy-v3#pro-refund` |
| Groundedness theo context cũ | Có thể PASS | Context `policy-v2` thực sự có thể hỗ trợ “30 ngày” |
| Factual correctness | FAIL | Nguồn hiện hành quy định 14 ngày |
| Citation freshness | FAIL | Trích dẫn nguồn đã hết hiệu lực |
| Technical completion | PASS | Lời gọi xử lý thành công về mặt kỹ thuật |
| Latency ≤ 2,5 giây | PASS | 1,1 giây theo ví dụ |

Bảng cho thấy **một case có nhiều kết quả độc lập**. Không thể nói “ứng dụng đúng” vì relevance hoặc HTTP thành công; cũng không thể kết luận “model hỏng” khi chưa xem lỗi truy xuất.

### 6.1. Chọn công cụ chấm theo tính chất yêu cầu

- **Java assertions:** cấu trúc JSON, tham số tool, document IDs, quyền, giới hạn định lượng.
- **Spring AI evaluator:** đánh giá ngữ nghĩa có rubric, ví dụ `RelevancyEvaluator` hoặc `FactCheckingEvaluator`.
- **Human/domain review:** xác minh chính sách, các trường hợp khó, nguồn mâu thuẫn và độ tin cậy của model chấm.
- **Metrics/traces:** đo thực thi, tốc độ và chi phí.

Trong Spring AI, khái niệm `Evaluator` nhận `EvaluationRequest` và trả `EvaluationResponse`. Các API cụ thể có thể khác theo phiên bản thư viện; phần cấu hình evaluator thực tế cần đối chiếu với version đang dùng.

### 6.2. Java: gắn ca, evidence và verdict

Đoạn Java dưới đây là ví dụ **hợp đồng dữ liệu của test harness**. Hàm nhận `Attempt` đã được thu từ ứng dụng thật. `relevanceJudge` và `groundingJudge` là các bean `Evaluator` được cấu hình phù hợp (có thể dùng các evaluator của Spring AI).

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;
import org.springframework.ai.evaluation.Evaluator;

public final class FirstCaseEvaluation {

    public record Case(
            String id,
            String question,
            Set<String> expectedDocumentIds) {}

    public record Attempt(
            String id,
            List<Document> contextActuallyUsed,
            String answer) {}

    public record Verdict(
            String attemptId,
            boolean retrievalHit,
            boolean relevant,
            boolean grounded,
            String relevanceFeedback,
            String groundingFeedback) {}

    public Verdict evaluate(
            Case testCase,
            Attempt attempt,
            Evaluator relevanceJudge,
            Evaluator groundingJudge) {

        Set<String> actualDocumentIds = attempt.contextActuallyUsed()
                .stream()
                .map(Document::getId)
                .collect(Collectors.toSet());

        boolean retrievalHit = actualDocumentIds.containsAll(
                testCase.expectedDocumentIds());

        EvaluationRequest request = new EvaluationRequest(
                testCase.question(),
                attempt.contextActuallyUsed(),
                attempt.answer());

        EvaluationResponse relevance = relevanceJudge.evaluate(request);
        EvaluationResponse grounding = groundingJudge.evaluate(request);

        return new Verdict(
                attempt.id(),
                retrievalHit,
                relevance.isPass(),
                grounding.isPass(),
                relevance.getFeedback(),
                grounding.getFeedback());
    }
}
~~~

Điểm cần chú ý:

1. `contextActuallyUsed` phải được capture từ **lần chạy thật** và đúng phần model đã nhìn thấy. Nếu không có, không được tạo giả để chấm.
2. Kiểm tra `containsAll` phù hợp khi ca có tập ID bắt buộc; nó chỉ là một kiểu **hit của tập nguồn**, không phải phép đo Recall@k đầy đủ khi thiếu nhãn cho toàn bộ tài liệu liên quan.
3. `isPass()` là verdict của evaluator tương ứng; nó **không mặc định** chứng minh factual correctness theo nguồn chuẩn độc lập.
4. Đoạn ví dụ không xử lý ngoại lệ của judge. Trong hệ thống đánh giá hoàn chỉnh, nếu judge timeout hoặc thiếu evidence thì ghi `NOT_EVALUATED` và lý do.
5. Với case chính sách, cần phép chấm riêng dựa trên nguồn hiện hành để phát hiện trường hợp “grounded vào tài liệu cũ nhưng sai sự thật”.

### 6.3. Bước chấm thủ công đầu tiên không được bỏ qua

Với 5–10 ca ban đầu, hãy tự đọc câu trả lời, nguồn và feedback của evaluator. Nếu judge cho PASS khi answer rõ ràng sai, phải sửa rubric hoặc thay cách chấm trước khi mở rộng hàng trăm ca. Một bộ chấm sai sẽ khuếch đại sai lệch của báo cáo.

**Tiêu chí hoàn thành chặng 3:** verdict có metric, lý do, phiên bản rubric/judge và tham chiếu tới `attemptId`. Một câu trả lời sai phải có thể giải thích bằng evidence cụ thể.

## 7. Chặng 4 — Mở rộng từ một ca thành dataset có độ bao phủ

Khi ca đầu tiên hoạt động, **mở rộng theo nhóm lỗi**, thay vì chỉ nhân bản câu hỏi với vài cách diễn đạt.

Gợi ý dataset đầu tiên gồm 24 ca:

| Nhóm | Số ca | Mục tiêu |
| --- | ---: | --- |
| Câu hỏi RAG có nguồn rõ | 6 | Trả lời đúng và có trích dẫn |
| Câu có nhiều điều kiện/số liệu gần giống | 4 | Tránh bỏ sót hoặc nhầm dữ kiện |
| Câu không có đủ nguồn | 4 | Không bịa thông tin hoặc ngoại lệ |
| Câu có tài liệu cũ/mâu thuẫn | 4 | Chọn nguồn hiện hành, kiểm freshness |
| Tool cần gọi đúng | 3 | Tool selection/arguments/result usage |
| Tool timeout/không có quyền | 3 | Xử lý lỗi, bảo vệ truy cập và không báo thành công giả |

Nếu ứng dụng có memory hội thoại, bổ sung bộ multi-turn; giữ conversation ID và trạng thái rõ ràng giữa các case. Nếu nhiều người dùng hoặc tenant, cần ca cô lập dữ liệu và quyền.

### 7.1. Tách bộ phát triển và hồi quy

Có thể tổ chức:

- **Development set:** dùng thường xuyên để thử prompt, model, `top-k` và thứ tự context.
- **Regression set:** ghi những lỗi từng xuất hiện và phải tránh tái diễn.
- **Held-out set:** dành cho đánh giá độc lập trước khi phát hành, hạn chế sửa prompt chỉ nhằm tối ưu từng câu của tập này.

Nếu ca gần như trùng nhau nằm đồng thời ở development và held-out, điểm kiểm định độc lập có thể bị lạc quan. Dataset cần version rõ ràng; thay đổi đáp án chuẩn hoặc nguồn phải được ghi nhận, nhất là khi chính sách thay đổi theo thời gian.

### 7.2. Đánh giá retrieval riêng với generation

Trên các case có nhãn tài liệu, có thể dùng:

\[
\mathrm{Precision@k} =
\frac{\text{Số kết quả truy xuất liên quan trong top-k}}{k}
\]

\[
\mathrm{Recall@k} =
\frac{\text{Số tài liệu liên quan tìm thấy trong top-k}}
{\text{Tổng số tài liệu liên quan đã được gắn nhãn}}
\]

Nếu chỉ biết một đoạn nguồn bắt buộc, `hit@k` đơn giản hơn: có tìm được đoạn đó trong top-k không?

Ví dụ 3 tài liệu được gắn nhãn liên quan, truy xuất top-5 có 2 tài liệu liên quan: `Precision@5 = 2/5 = 40%` và `Recall@5 = 2/3 ≈ 66,7%`. Hai phép đo đòi hỏi nhãn đủ tin cậy; thiếu nhãn không nên suy ra recall.

Sau retrieval, tiếp tục chấm answer relevance, groundedness và factual correctness. **Recall tăng không bảo đảm câu trả lời đúng hơn** nếu context trở nên nhiễu hoặc bị cắt vì giới hạn token.

### 7.3. Với tool calling, chấm hành vi

Một case đọc đơn hàng nên có tối thiểu:

~~~json
{
  "caseId": "ORDER-001",
  "question": "Cho biết trạng thái đơn DH-123 của tôi",
  "expectedTool": "getOrderStatus",
  "expectedArguments": {"orderId": "DH-123"},
  "toolFixture": {"status": "IN_TRANSIT"},
  "expectedAnswerFacts": ["Đơn đang được giao"],
  "checks": [
    "authorization",
    "toolSelection",
    "toolArguments",
    "toolResultUsage"
  ]
}
~~~

Sử dụng môi trường kiểm thử, fake/stub hoặc sandbox khi tool có side effect. Quyền và tính idempotent của thao tác phải được thực thi ở backend, không giao cho prompt hoặc LLM judge bảo đảm.

### 7.4. Công bố điểm theo nhóm

Một bảng điểm cần bao gồm số ca thực chạy, số ca chấm được, số ca PASS/FAIL/UNKNOWN và tỷ lệ theo metric. Tỷ lệ đạt tổng thể đẹp có thể che việc tất cả case “không đủ nguồn” đều thất bại.

**Tiêu chí hoàn thành chặng 4:** dataset có version và ít nhất một ca cho mỗi nhóm rủi ro quan trọng, có thể chạy lại theo cùng hợp đồng bằng chứng.

## 8. Chặng 5 — So baseline và candidate trước khi phát hành

Từ đây, mỗi thay đổi quan trọng đều được đánh giá có đối chứng: prompt, model, retrieval configuration, embedding, chunking, tool schema hoặc một phần pipeline.

### 8.1. Giữ nguyên điều kiện khi thử một biến

Ví dụ muốn tăng `top-k` từ 3 lên 5:

1. Chạy baseline `rag-v1` với `top-k=3` trên dataset đã đóng phiên bản.
2. Giữ nguyên prompt, model, corpus, index, judge/rubric và fixture tool.
3. Chạy candidate `rag-v2` với `top-k=5`.
4. So thay đổi retrieval hit@k, groundedness, factual correctness, tool behavior.
5. Đo latency/token/cost trong điều kiện tải tương đương.
6. Xem từng ca từ PASS sang FAIL, không chỉ điểm bình quân.

Khi buộc phải đổi nhiều phần cùng lúc, ghi rõ giới hạn phân tích nguyên nhân. Nếu đổi cả corpus và model, chỉ số tốt lên chưa chứng minh model là yếu tố cải thiện.

### 8.2. Manifest của một run

~~~yaml
runId: candidate-rag-v2-2026-05-18
datasetVersion: assistant-eval-v2
referencePolicyVersion: policy-v3
promptVersion: prompt-v4
modelVersion: model-candidate
embeddingVersion: embedding-v1
corpusVersion: policy-corpus-v3
indexVersion: vector-index-v3
pipelineVersion: rag-v2
retrievalTopK: 5
toolSchemaVersion: tools-v1
judgeVersion: judge-v1
rubricVersion: quality-rubric-v2
environment: staging
~~~

Thông số là ví dụ. Bản ghi phải phản ánh cấu hình thực; không tự đặt `traceId` hoặc version không có trong hệ thống.

### 8.3. Báo cáo so sánh minh họa

Giả sử một bộ 100 ca được chạy trên cùng dataset/rubric, các con số sau là **giả định**:

| Chỉ số | Baseline | Candidate |
| --- | ---: | ---: |
| Retrieval hit@5 | 88% | 94% |
| Answer relevance PASS | 92% | 95% |
| Groundedness PASS | 97% | 94% |
| Factual correctness PASS | 96% | 93% |
| Tool contract pass | 100% | 100% |
| p95 request latency | 2,1 giây | 3,2 giây |
| Input tokens trung bình | 1.250 | 2.100 |
| Chi phí model ước tính/request | 0,004 USD | 0,006 USD |

Candidate tìm nguồn tốt hơn nhưng factual correctness/groundedness giảm và latency tăng. **Không thể kết luận candidate tốt hơn chỉ từ hit@5.** Cần xem ca fail, documents, prompt và traces; có thể thêm tài liệu cũ hoặc context quá dài.

### 8.4. Release gate phải có tiêu chí riêng

Ví dụ **ngưỡng giả định**, không phải mặc định Spring AI:

~~~yaml
releaseGates:
  software:
    toolAuthorization: must-pass
    toolContract: must-pass
  quality:
    factualCorrectnessPassRate: ">= 0.98"
    groundednessPassRate: ">= 0.95"
    criticalCases: must-pass
  operations:
    p95LatencyMs: "<= 2500"
    technicalErrorRate: "<= 0.01"
    estimatedModelCostUsdPerRequest: "<= 0.01"
~~~

Đừng tạo một điểm trung bình để bù lỗi phân quyền bằng độ trễ tốt hoặc điểm relevance cao. Các ngưỡng phải phù hợp mức rủi ro, dataset đủ đại diện và điều kiện tải. Cần nêu rõ `UNKNOWN/NOT_EVALUATED` được xử lý thế nào ở gate.

**Tiêu chí hoàn thành chặng 5:** báo cáo có thể chỉ ra quyết định giữ/loại candidate với lý do, sự khác biệt config và ít nhất một case hồi quy được điều tra bằng bằng chứng.

## 9. Chặng 6 — Bật observability trước khi triển khai rộng

Đánh giá offline trả lời ứng dụng có đạt rubric không. Để biết *vì sao một request chậm, thất bại hoặc tốn token*, cần có telemetry đi xuyên qua pipeline.

Spring AI có cơ chế observability dựa trên Spring/Micrometer, với hỗ trợ cho nhiều thành phần như `ChatClient`, `ChatModel`, `Advisor`, `VectorStore` và tool calls tùy phiên bản/configuration/provider. Spring Boot Actuator giúp truy cập một số chỉ số khi được cấu hình.

### 9.1. Trước tiên xác định các câu hỏi vận hành

| Câu hỏi | Tín hiệu |
| --- | --- |
| Request hoàn thành về kỹ thuật không? | Request count, error/timeout rate |
| Độ trễ đến từ bước nào? | Trace spans retrieval/model/tool, latency percentiles |
| Model có phải gọi lặp không? | Số model calls, retries, tool rounds |
| Prompt có dài bất thường không? | Input tokens, context size, output tokens |
| Chi phí tăng ở đâu? | Usage theo provider/model, model calls và giá áp dụng |
| Có ít tài liệu hoặc tài liệu cũ không? | Evidence về retrieved IDs, versions, context |
| Câu trả lời sai dù không lỗi kỹ thuật? | Dataset/quality verdict, không phải chỉ metrics |

### 9.2. Cấu hình Spring Boot tối thiểu minh họa

Một ứng dụng có Actuator, registry và tracing dependencies phù hợp có thể bắt đầu với:

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

`/actuator/prometheus` cần registry Prometheus và endpoint được bật; tracing xuất ra collector/backend cần cấu hình exporter, địa chỉ và credentials. Tên metric, tags và observations cụ thể có thể thay đổi theo Spring AI/Spring Boot/provider, nên kiểm tra số liệu thực xuất ra trước khi xây dashboard.

**Không nên ghi nguyên văn prompt/completion/tool arguments theo mặc định** vì chúng có thể chứa dữ liệu nhạy cảm. Dùng metadata hữu ích, tham chiếu evidence có phân quyền, chính sách che dữ liệu và thời gian lưu.

### 9.3. Traces cho một request RAG kết hợp tool

Ví dụ mô hình thời gian của một request:

~~~text
HTTP POST /ask                                  3200 ms
└── ChatClient                                  3050 ms
    ├── RAG Advisor
    │   └── VectorStore query                   400 ms
    ├── ChatModel #1                            1100 ms
    ├── getOrderStatus tool                      550 ms
    └── ChatModel #2                            1000 ms
~~~

Đây là trace **minh họa** về cấu trúc, không phải bằng chứng chạy thực tế. Các span có quan hệ cha/con nên không cộng thời lượng lồng nhau tùy tiện. Nếu cần trải nghiệm streaming, theo dõi thêm **time to first token (TTFT)** ngoài tổng thời gian nhận đầy đủ response.

### 9.4. Đọc số liệu latency đúng cách

**Average latency** dễ che request chậm ở phần đuôi. Dùng `p50` để xem trung vị và `p95/p99` để xem những tình huống chậm, khi có dữ liệu phân bố phù hợp.

Nếu một metric timer chỉ có `count` và `sum`, ta tính được mean:

\[
\mathrm{meanLatency} = \frac{\mathrm{sumLatency}}{\mathrm{count}}
\]

Nhưng **không tính được p95** chỉ từ count và sum; cần histogram, distribution hoặc hệ thống cho phép phân tích phân vị. Khi dùng Prometheus, chỉ có thể dùng `histogram_quantile` nếu có các bucket tương ứng.

### 9.5. Tính token và chi phí

Với giá giả định theo triệu token:

\[
\mathrm{modelCost} =
\frac{\mathrm{inputTokens}}{10^6}\,\mathrm{inputPricePerMillion}
+
\frac{\mathrm{outputTokens}}{10^6}\,\mathrm{outputPricePerMillion}.
\]

Ví dụ một request dùng 2.000 input tokens với giá giả định 2 USD/triệu và 500 output tokens với giá giả định 8 USD/triệu:

\[
\mathrm{modelCost} = \frac{2000\times2+500\times8}{10^6}
=0{,}008\ \mathrm{USD}.
\]

Giá ở đây **chỉ phục vụ minh họa**. Một request tool calling có thể gọi ChatModel hai lần nên phải cộng usage của cả hai. Tổng chi phí thực tế còn có thể gồm embedding, reranking, VectorStore, tool/backend, caching, retries và evaluator. Usage do provider trả về có thể thiếu hoặc khác giữa các cách gọi; báo cáo nên nêu cách tính và nguồn dữ liệu.

**Tiêu chí hoàn thành chặng 6:** có thể mở một trace hoặc báo cáo duration của một attempt để chỉ ra bước chiếm thời gian, biết số model calls và tính được chi phí theo dữ liệu sẵn có, với giới hạn rõ ràng.

## 10. Chặng 7 — Theo dõi toàn bộ ứng dụng khi vận hành

Một điểm số offline trên tập ca cố định không tự chứng minh chất lượng đối với mọi câu hỏi production. Người dùng có thể đặt câu mới, nguồn được cập nhật, tool backend đổi schema hoặc tải tăng. Vì vậy, sau rollout phải đo **sức khỏe kỹ thuật** và **chất lượng nội dung được xác minh**.

### 10.1. Hai bảng điều khiển bổ sung nhau

**Operational dashboard:**

- Request count, technical success/error rate và timeout.
- p50/p95/p99 latency; TTFT khi streaming.
- Thời gian VectorStore, ChatModel, tool; retry, rate limit.
- Input/output tokens, số model calls, chi phí ước tính.
- Phiên bản release, prompt, model, pipeline và dữ liệu khi có thể gắn an toàn.

**Quality dashboard:**

- Số mẫu production được chọn để chấm.
- Số đã được chấm và số còn chờ/không thể chấm.
- Relevance, groundedness, factual correctness trên **các mẫu có bằng chứng phù hợp**.
- Citation validity, nguồn hết hiệu lực, tool-behavior failures.
- Điểm theo nhóm câu hỏi, mức rủi ro và release.
- Các sự cố đã được chuyên gia xác minh và regression cases.

Hai dashboard nên có liên kết qua `releaseVersion`, `request/attempt reference` và `traceId`. Một trace có thể không tồn tại do sampling; khi đó phải thể hiện thiếu evidence, không giả lập trace.

### 10.2. Vì sao cần chọn mẫu online?

Hầu hết request thật không có đáp án chuẩn ngay lập tức. Chấm toàn bộ bằng LLM judge hoặc chuyên gia có thể quá tốn chi phí và phát sinh rủi ro quyền riêng tư. Có thể áp dụng:

- **Mẫu ngẫu nhiên:** hỗ trợ ước lượng xu hướng chung khi chọn mẫu đúng và dữ liệu nhãn đủ.
- **Mẫu phân tầng:** chủ động bao phủ RAG, tool calling, câu thiếu nguồn, ngôn ngữ hoặc nhóm nghiệp vụ hiếm.
- **Mẫu rủi ro:** ưu tiên câu không có citation, tool lỗi, nhiều retry hoặc có phản hồi tiêu cực để tìm lỗi nhanh.
- **Mẫu sự cố:** các ca được người dùng/đội vận hành báo cáo và cần chuyên gia xác minh.

**Mẫu lấy theo rủi ro giúp tìm lỗi nhưng không mặc nhiên đại diện toàn traffic.** Không được xem tỷ lệ FAIL của các mẫu ưu tiên là tỷ lệ FAIL toàn production nếu không có phương pháp ước lượng phù hợp.

### 10.3. Ví dụ ba mẫu số khác nhau

Giả sử trong ngày:

~~~text
Tổng request hợp lệ:              10.000
Request hoàn thành về kỹ thuật:     9.900
Request được chọn review:             300
Request đã được chấm:                 240
Request đạt rubric trong số đã chấm:  216
~~~

Ta có:

\[
\mathrm{technicalCompletion} = 9900/10000 = 99\%.
\]

\[
\mathrm{reviewedQualityPassRate} = 216/240 = 90\%.
\]

\[
\mathrm{reviewCoverage} = 240/300 = 80\%.
\]

Những tỷ lệ này nói về **ba tập khác nhau**. Không nên công bố “90% mọi request production đều đúng” nếu chưa kiểm chứng cách chọn mẫu và lượng nhãn còn thiếu. Cũng không nên loại request timeout khỏi mọi báo cáo để làm đẹp điểm chất lượng.

### 10.4. Phát hiện traffic drift và quality regression

Giả sử pass rate của từng nhóm giữ nguyên:

- Câu hỏi thông thường: 95% đạt.
- Câu thiếu nguồn: 60% đạt.

Khi tỷ trọng nhóm thiếu nguồn tăng từ 10% lên 40%, pass rate tổng có thể giảm dù model không kém đi trong từng nhóm. Đây là **thay đổi phân bố câu hỏi**. Ngược lại, tỷ trọng nhóm có thể giữ nguyên nhưng pass rate trong nhóm RAG giảm, gợi ý **quality regression**.

Khi thấy biểu đồ quality giảm, hãy xem:

1. Dataset/rubric/judge/sampling có đổi không?
2. Cỡ mẫu và tỷ lệ chưa chấm là bao nhiêu?
3. Điểm theo nhóm có giảm, hay chỉ cơ cấu nhóm thay đổi?
4. Corpus/index/prompt/model/tool nào vừa được đổi?
5. Những ca lỗi nào có evidence đủ để phân tích?

Không suy ra nguyên nhân từ một đồ thị tổng hợp duy nhất.

### 10.5. Canary và quyết định mở rộng

Trước khi toàn bộ traffic sang phiên bản mới, triển khai có kiểm soát với **canary** nếu sản phẩm/hạ tầng cho phép. So metrics và mẫu chất lượng theo phiên bản trên các nhóm request tương đương. Đặt tiêu chí rollback cho lỗi quyền/tool nghiêm trọng, error rate hoặc latency vượt giới hạn và hồi quy chất lượng đã được xác minh.

Canary là phương thức rollout; **A/B experiment** là thiết kế so sánh các biến thể trên traffic thật, thường cần phân nhóm và phương pháp thống kê phù hợp. Không mặc định mọi canary đã là một A/B test đáng tin.

**Tiêu chí hoàn thành chặng 7:** khi nhìn dashboard có thể phân biệt được tình trạng kỹ thuật, chất lượng trên mẫu có nhãn, coverage của mẫu, thay đổi phân bố và phiên bản liên quan.

## 11. Chặng 8 — Từ cảnh báo đến nguyên nhân và hồi quy

Đây là chặng khép vòng cải tiến. Một dashboard hữu ích không chỉ hiển thị điểm đỏ; nó dẫn tới một case có thể điều tra và kiểm thử lại.

### 11.1. Quy trình sự cố mẫu

Giả sử sau khi phát hành `rag-v2`, factual correctness của nhóm “chính sách hoàn phí” giảm. Quy trình:

1. **Xác nhận tín hiệu:** số mẫu đủ chưa, rubric/judge và cách lấy mẫu có thay đổi không?
2. **Khoanh vùng:** lỗi tập trung ở phiên bản nào, nhóm yêu cầu nào, khung thời gian nào?
3. **Lấy case đại diện:** có quyền xem evidence từ case thực tế đã được xử lý riêng tư.
4. **Đối chiếu với nguồn chuẩn:** câu sai do tài liệu chưa cập nhật hay do model diễn giải?
5. **Đi theo trace:** retrieval có lỗi, tool có 403/timeout, model có retry, context có quá dài?
6. **Tạo giả thuyết:** ví dụ “index còn chính sách cũ” hoặc “context bị cắt mất đoạn mới”.
7. **Kiểm chứng bằng thay đổi nhỏ:** sửa đúng ranh giới nghi vấn, chạy lại case và regression set.
8. **Triển khai có kiểm soát:** quan sát chất lượng và latency/cost sau sửa.

### 11.2. Một báo cáo điều tra đủ dùng

~~~yaml
incidentId: QUALITY-INC-001
affectedRelease: rag-v2
symptom: "Sai thời hạn hoàn phí gói Pro"
caseReference: "REFUND-001"
observedAnswer: "30 ngày"
currentPolicy: "policy-v3, 14 ngày"
attemptRef: "incident-attempt-001"
traceRef: "trace-refund-incident-001"
retrievedDocumentIds:
  - "policy-v2#pro-refund"
hypothesis: "Indexer hoặc filter đang trả tài liệu hết hiệu lực"
verification:
  - "Kiểm tra metadata hiệu lực trong index"
  - "Chạy lại với bộ lọc policy v3"
  - "Đối chiếu retrieval IDs và groundedness/factuality"
regressionCase: "REFUND-001"
status: "UNDER_INVESTIGATION"
~~~

Mọi dữ liệu là ví dụ. Một hypothesis phải được ghi là **giả thuyết** cho đến khi có phép thử và evidence tương ứng.

### 11.3. Cập nhật dataset sau sự cố

Khi một lỗi production đã được xác minh:

- Ẩn thông tin nhạy cảm và chuẩn hóa đầu vào.
- Gắn đúng nguồn đang hiệu lực, expected facts/action và lý do fail.
- Gán `caseId` mới hoặc cập nhật ca cũ theo version.
- Thêm vào regression set và chạy lại baseline/candidate.
- Kiểm tra tác động của bản sửa lên cả nhóm khác, latency và chi phí.

Nếu bộ dữ liệu thay đổi đáp án vì chính sách mới, phải ghi **dataset version mới**. Nếu chỉ đổi judge/rubric, cần phân biệt chênh lệch do **cách chấm** với chênh lệch do hệ thống.

**Tiêu chí hoàn thành chặng 8:** một lỗi thực tế đã chuyển thành case có nhãn và lý do, chạy được trong lần kiểm tra phát hành tiếp theo.

## 12. Kết nối dữ liệu ở quy mô toàn ứng dụng

Bắt đầu từ một case, cấu trúc dữ liệu nên mở rộng theo quan hệ:

~~~mermaid
erDiagram
    DATASET ||--o{ CASE : "contains"
    EVALUATION_RUN ||--o{ ATTEMPT : "executes"
    CASE ||--o{ ATTEMPT : "evaluated in"
    ATTEMPT ||--o{ EVIDENCE : "emits"
    ATTEMPT ||--o{ VERDICT : "scored by"
    VERDICT }o--o{ EVIDENCE : "references"
    ATTEMPT }o--o| TRACE : "may link"
~~~

Đây là mô hình lưu trữ gợi ý, không phải database schema có sẵn của Spring AI.

### 12.1. Bộ khóa tối thiểu

| Khóa | Mục đích | Lỗi nếu thiếu |
| --- | --- | --- |
| `datasetVersion` | Biết nhãn/source/rubric của bộ ca | So điểm với hai bộ dữ liệu khác nhau |
| `caseId` | Nhận diện tình huống nghiệp vụ | Không biết case nào hồi quy |
| `runId` | Nhận diện đợt thử cấu hình | Không biết điểm thuộc candidate nào |
| `attemptId` | Nhận diện một lần thực thi cụ thể | Ghép nhầm output hoặc context giữa các lần chạy |
| `traceId` | Tìm các span của request (khi có) | Khó chẩn đoán bước chậm/lỗi |
| `promptVersion`, `modelVersion`, `pipelineVersion` | Giải thích thay đổi ứng dụng | Không biết yếu tố nào đã đổi |
| `corpusVersion`, `indexVersion` | Theo dõi nguồn RAG | Không phát hiện nguồn lỗi thời |
| `rubricVersion`, `judgeVersion` | Giải thích thay đổi cách chấm | Tưởng ứng dụng hồi quy khi judge đổi |
| `toolSchemaVersion` | Theo dõi hợp đồng công cụ | Khó nhận biết sai lệch args/cách gọi |

Một attempt có thể gọi ChatModel nhiều lần vì tool calling hoặc retry. Dữ liệu usage/cost nên được cộng theo **các lời gọi thực tế**, tránh giả định một attempt tương đương một model call.

### 12.2. Tối thiểu hóa dữ liệu nhạy cảm

Không cần đưa toàn bộ prompt, tài liệu, tên người dùng và tool arguments vào dashboard. Có thể lưu ID/tham chiếu an toàn với evidence store có phân quyền. Áp dụng ẩn dữ liệu, mã hóa, giới hạn thời gian lưu và chính sách lấy mẫu. Các tag metrics nên có cardinality thấp, chẳng hạn `operation`, `releaseVersion`, `provider`; tránh raw prompt và user ID.

Nếu không thể lưu nội dung vì chính sách riêng tư, cần ghi rõ metric nào **không thể xác minh**. Một trace thành công không đủ để chấm factual correctness.

## 13. Kế hoạch triển khai thực tế theo ba mức độ

Không cần xây toàn bộ hệ thống giám sát phức tạp từ ngày đầu. Có thể tăng phạm vi theo mức trưởng thành:

| Mức | Những gì đã có | Dấu hiệu sẵn sàng lên mức tiếp |
| --- | --- | --- |
| **MVP kiểm chứng** | 1–5 ca có nguồn, answer và verdict với lý do | Có thể giải thích từng ca PASS/FAIL bằng evidence |
| **Regression có phiên bản** | Dataset theo nhóm, run manifest, baseline/candidate, CI gate | Phát hiện ca hồi quy và có quyết định release rõ |
| **Production feedback loop** | Metrics/traces, sampling/review, quality trends, incident → case mới | Liên kết được quality failure với thực thi và cải tiến định kỳ |

### 13.1. Những việc nên tự động hóa sớm

- Ghi `attemptId`, config versions và một record evidence cho mỗi ca.
- Tính retrieval hit/đối số tool/JSON schema bằng assertions.
- Chạy regression sau mỗi thay đổi prompt, model, corpus hoặc tool schema.
- Ghi error rate, latency/tokens theo release mà không thu nội dung nhạy cảm ngoài nhu cầu.
- Báo cáo cả PASS/FAIL/UNKNOWN và số ca thực chấm.

### 13.2. Những việc vẫn cần người có chuyên môn

- Xác minh nguồn chuẩn và hiệu lực chính sách.
- Rà soát các trường hợp khó, mơ hồ, có tác động nghiệp vụ lớn.
- Đánh giá false positive/negative của LLM-as-a-judge.
- Xác định ngưỡng phù hợp cho release gate và xử lý ngoại lệ.
- Xác định các giới hạn lưu dữ liệu, quyền truy cập và cách phản ứng sự cố.

Tự động hóa giúp có tốc độ và độ nhất quán, nhưng không thay được nguồn sự thật, rubric rõ và trách nhiệm xử lý lỗi.

## 14. Các bẫy khiến lộ trình thất bại

**Chỉ tạo nhiều câu hỏi mà không có nhãn.** Không thể chấm đúng/sai một cách có kiểm chứng. Cần expected facts, nguồn và rubric.

**Chạy evaluator trên nguồn chuẩn thay vì tài liệu truy xuất thật.** Làm mất khả năng phát hiện RAG retrieval failure.

**Đo “chất lượng” bằng HTTP success hoặc latency.** Đây là sức khỏe kỹ thuật; câu trả lời có thể sai trong request thành công.

**Tối ưu mỗi relevance.** Câu sai dữ kiện vẫn có thể rất liên quan; cần groundedness, factual correctness và bằng chứng tool.

**Bỏ qua test xác định cho các chức năng có tác dụng phụ.** Tool refund/transfer phải kiểm quyền và hậu điều kiện ở backend. LLM judge không phải lớp bảo vệ giao dịch.

**Không quản lý dataset/judge versions.** Khi điểm đổi, không biết do hệ thống, nguồn hay bộ chấm.

**So pass rate với mẫu số khác mà không công bố.** 90/100, 90/95 và 90/90 là các tình huống rất khác nhau. Cần báo số ca chưa chấm.

**Dùng mẫu production được chọn vì có lỗi rồi công bố tỷ lệ lỗi toàn hệ thống.** Mẫu rủi ro không mặc nhiên đại diện cho traffic; cần thiết kế lấy mẫu/ước lượng rõ.

**Log mọi prompt và công cụ để “có đủ evidence”.** Dữ liệu có thể nhạy cảm, tăng chi phí và rủi ro. Thu tối thiểu, gắn tham chiếu an toàn và phân quyền.

**Đổi tất cả thành phần trong một lần rồi khẳng định nguyên nhân.** Muốn chứng minh cải tiến, cần so sánh trong điều kiện được kiểm soát hoặc nêu rõ yếu tố gây nhiễu.

**Chỉ chạy offline một lần rồi ngừng đánh giá.** Tài liệu, câu hỏi người dùng, provider, tool backend và chi phí có thể thay đổi dù code không đổi.

## 15. Bài thực hành cuối bài — Từ một case đến dashboard

**Bài toán:** xây một trợ lý Spring AI tra cứu chính sách giả định qua RAG và đọc trạng thái đơn qua `getOrderStatus`. Hãy thực hiện theo bốn vòng, mỗi vòng giữ lại bằng chứng.

### Vòng 1: Một ca đánh giá

Tạo `REFUND-001`: “Gói Pro hoàn phí trong bao lâu?”. Nguồn chính sách đúng là 14 ngày. Chạy ứng dụng, lưu answer và tài liệu truy xuất thực tế. Chấm relevance, groundedness, factual correctness và retrieval hit@k riêng.

**Sản phẩm:** một JSON chứa case, một JSON chứa attempt và một JSON chứa các verdict, liên kết bằng ID.

### Vòng 2: Mở thành bộ hồi quy

Thêm 15–20 ca gồm câu không có nguồn, chính sách cũ, câu nhiều điều kiện, tool thành công và tool timeout/403. Lưu phiên bản dataset và run manifest. So hai cấu hình `top-k=3` và `top-k=5`, ghi ca PASS→FAIL.

**Sản phẩm:** báo cáo baseline/candidate có số ca và bảng điểm theo nhóm, cùng các lỗi tiêu biểu.

### Vòng 3: Thêm telemetry

Bật Actuator/metrics và tracing phù hợp trong môi trường kiểm thử. Thu duration retrieval/model/tool, p95 theo một tập chạy có đủ mẫu, usage model và ước tính chi phí. Gắn trace ID với attempt khi trace thật tồn tại.

**Sản phẩm:** có thể mở một case fail và xác định bước gây chậm hoặc lỗi, với giới hạn đo rõ ràng.

### Vòng 4: Mô phỏng production và phản hồi

Tạo 200 request giả định với hai nhóm “có nguồn” và “thiếu nguồn”, mô phỏng phân bố yêu cầu thay đổi. Lấy mẫu 40 request (ghi rõ cách lấy mẫu), chấm một phần và để một số `PENDING_REVIEW`. Báo pass rate trên tập đã chấm, review coverage, error rate và latency/cost. Chọn một ca lỗi được xác minh để đưa vào regression set.

**Sản phẩm:** dashboard/báo cáo tách kỹ thuật và chất lượng, cùng một case mới được bổ sung vào tập đánh giá ngoại tuyến.

### Checklist nghiệm thu

- [ ] Mỗi case có ID, expectation, nguồn hoặc lý do không có nguồn, rubric version.
- [ ] Mỗi attempt có answer thực, retrieved context/tool events và config versions.
- [ ] Verdict phân biệt PASS, FAIL, UNKNOWN/NOT_EVALUATED.
- [ ] Không dùng dữ liệu kỳ vọng thay cho evidence của pipeline.
- [ ] Có báo cáo nhóm lỗi RAG, tool calling và kết quả hồi quy.
- [ ] Gate về quyền/tool bắt buộc được kiểm bằng phần mềm đáng tin.
- [ ] Có chỉ số latency, token, error và cost với phạm vi đo rõ ràng.
- [ ] Mẫu production có sampling policy, số được chấm và số còn thiếu nhãn.
- [ ] Một quality failure có thể truy ngược về attempt và trace khi có.
- [ ] Ít nhất một lỗi được chuyển thành case hồi quy chạy lại được.

### Câu hỏi tự kiểm tra

1. Vì sao một case có câu hỏi và câu trả lời mẫu nhưng không có rubric/nguồn chưa đủ để xây bộ đánh giá tốt?
2. Model trả lời đúng “14 ngày” dù retriever không tìm thấy `policy-v3`. Những tiêu chí nào có thể đạt và tiêu chí nào không?
3. Khi `FactCheckingEvaluator` cho PASS với tài liệu cũ, cần kiểm tra gì để biết câu trả lời đúng chính sách hiện hành?
4. Vì sao `caseId`, `attemptId` và `traceId` không thể dùng thay thế nhau?
5. Dataset mở rộng nên theo nhóm lỗi nào để tránh chỉ học thuộc câu dễ?
6. Khi tăng `top-k` từ 3 lên 5, vì sao phải đo cả groundedness, tokens và latency?
7. HTTP 200, p95 thấp nhưng tool thiếu kiểm tra quyền. Có thể phát hành chỉ nhờ điểm vận hành tốt không?
8. Một dashboard online có 240 ca được chấm trên 300 mẫu từ 10.000 request. Tỷ lệ PASS phải ghi rõ mẫu số nào?
9. Khi điểm production giảm nhưng tỷ lệ từng nhóm giữ nguyên, cần kiểm tra thay đổi gì?
10. Khi điểm relevance giảm ngay sau khi đổi judge, làm sao phân biệt lỗi ứng dụng với lỗi phương pháp chấm?
11. LLM judge bị timeout có thể ghi verdict PASS vì câu trả lời hoàn thành không?
12. Khi một lỗi từ production đã được xác minh, các thông tin nào cần chuyển vào regression set?

## 16. Kết luận

Lộ trình đánh giá và quan sát một ứng dụng Spring AI bắt đầu bằng **một ca có kỳ vọng kiểm chứng được**, sau đó liên kết ca ấy với **execution evidence**, **verdict theo rubric**, **dataset có phiên bản**, **so sánh baseline/candidate**, **release gate**, **metrics/traces** và **giám sát chất lượng production**.

Mỗi bước làm tăng quy mô nhưng vẫn giữ câu hỏi căn bản: *ca nào, chạy ở phiên bản nào, đã xảy ra điều gì, được chấm theo chuẩn nào, và kết luận có thể kiểm chứng bằng bằng chứng nào?* Khi quy trình này được duy trì, nhóm có thể cải thiện prompt, model, RAG và tool calling mà vẫn kiểm soát được lỗi hồi quy, độ trễ và chi phí.

### Tài liệu tham khảo chính thức

- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring Boot — Production-ready Features (Actuator)](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
