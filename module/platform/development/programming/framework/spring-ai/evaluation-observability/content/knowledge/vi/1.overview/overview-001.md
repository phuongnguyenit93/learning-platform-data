# Đánh giá và quan sát ứng dụng AI là gì?

Một ứng dụng dùng Spring AI có thể trả lời trôi chảy nhưng sai tài liệu, truy xuất nhầm ngữ cảnh, gọi nhầm công cụ hoặc phản hồi quá chậm. Vì đầu ra của mô hình ngôn ngữ có tính xác suất và phụ thuộc vào prompt, dữ liệu, model cũng như trạng thái hệ thống, việc kiểm tra một vài câu hỏi thủ công không đủ để biết ứng dụng có đang hoạt động tốt hay không.

**Evaluation (đánh giá)** giúp trả lời: *Ứng dụng có tạo ra kết quả đúng, phù hợp và đáng tin cậy không?* **Observability (khả năng quan sát)** giúp trả lời: *Ứng dụng đã xử lý yêu cầu như thế nào, mất thời gian ở đâu, tiêu thụ bao nhiêu tài nguyên và vì sao chất lượng thay đổi?*

Trong module **SPRING_AI_EVALUATION_OBSERVABILITY**, hai nhóm kỹ thuật này được kết hợp để đánh giá bằng tập dữ liệu, kiểm tra `relevance` và `fact checking`, kiểm thử luồng RAG hoặc gọi công cụ, đồng thời theo dõi metrics, traces, token, chi phí và độ trễ qua các phiên bản prompt, model, pipeline.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt kiểm thử tính đúng đắn thông thường với đánh giá chất lượng câu trả lời do AI sinh ra.
- Xây dựng tập dữ liệu đánh giá có câu hỏi, đáp án kỳ vọng, nguồn bằng chứng và tiêu chí đạt.
- Phân biệt độ phù hợp của câu trả lời, mức độ được bằng chứng hỗ trợ và chất lượng truy xuất tài liệu.
- Hiểu vai trò của `RelevancyEvaluator` và `FactCheckingEvaluator` trong Spring AI, cùng giới hạn của đánh giá bằng LLM.
- Đọc metrics, traces, token usage và ước tính chi phí để định vị nguyên nhân suy giảm chất lượng, tốc độ hoặc hiệu quả vận hành.
- So sánh các phiên bản prompt, model và pipeline bằng một quy trình đo lường có thể lặp lại.

## 2. Evaluation và observability khác nhau thế nào?

Trong ứng dụng truyền thống, một bài kiểm thử thường so sánh đầu ra với giá trị xác định: gọi hàm tính thuế với một đầu vào thì kỳ vọng một con số cụ thể. Với AI, hai câu trả lời khác cách diễn đạt vẫn có thể đều đúng; ngược lại, câu trả lời nghe hợp lý có thể chứa một con số bịa ra.

| Khía cạnh | Evaluation | Observability |
| --- | --- | --- |
| Câu hỏi chính | Kết quả có đạt yêu cầu không? | Hệ thống đã làm gì và vì sao có kết quả đó? |
| Đối tượng đo | Câu trả lời, tài liệu truy xuất, quyết định gọi tool, tính an toàn | Request, bước truy xuất, lời gọi model/tool, thời gian, lỗi, token |
| Dữ liệu đầu vào | Dataset, đáp án tham chiếu, tiêu chí, phản hồi người đánh giá | Metrics, traces, logs, metadata, events |
| Kết quả điển hình | Tỷ lệ đạt `relevance`, `faithfulness`, `Recall@k`, đúng tool | p95 latency, lỗi theo bước, token/request, chi phí/request |
| Thời điểm | Trước phát hành, hồi quy định kỳ, lấy mẫu trên production | Trong quá trình chạy thử và vận hành thực tế |
| Giới hạn | Có thể biết câu trả lời sai nhưng chưa biết nguyên nhân kỹ thuật | Có thể biết lời gọi nhanh và không lỗi nhưng chưa biết câu trả lời đúng hay sai |

Ví dụ: một chatbot tư vấn chính sách trả lời “khách hàng được hoàn phí trong 30 ngày”, trong khi tài liệu ghi “14 ngày”. Evaluation phát hiện câu trả lời không được nguồn hỗ trợ. Observability có thể cho biết hệ thống đã truy xuất nhầm tài liệu cũ, lấy sai đoạn văn, bỏ qua bước retrieval hoặc dùng prompt/model mới.

**Hai lớp đo lường bổ sung cho nhau:** chất lượng đầu ra là mục tiêu; dấu vết thực thi là bằng chứng giúp tìm nguyên nhân.

~~~mermaid
flowchart LR
    A["Dataset có nhãn<br/>và tiêu chí"] --> B["Chạy ứng dụng<br/>Spring AI"]
    B --> C["Câu trả lời, nguồn,<br/>lần gọi tool"]
    C --> D["Evaluation<br/>relevance / factuality / RAG"]
    B --> E["Observability<br/>metrics / traces / tokens"]
    D --> F["So sánh phiên bản<br/>và quyết định cải tiến"]
    E --> F
~~~

## 3. Đánh giá chất lượng ứng dụng AI theo từng lớp

Không có một điểm số duy nhất phản ánh mọi khía cạnh của ứng dụng. Hãy chọn tiêu chí dựa trên nhiệm vụ và vị trí có thể xảy ra lỗi.

| Lớp cần kiểm tra | Tiêu chí thường dùng | Câu hỏi kiểm tra |
| --- | --- | --- |
| Câu trả lời | **Answer relevance** (mức độ liên quan) | Câu trả lời có giải quyết đúng câu hỏi không? |
| Câu trả lời có nguồn | **Groundedness / faithfulness** | Mỗi khẳng định quan trọng có được tài liệu đã cung cấp hỗ trợ không? |
| Kiến thức nghiệp vụ | **Factual correctness** | Kết quả có đúng với đáp án hay sự thật đã được xác minh không? |
| Truy xuất RAG | **Recall@k**, **Precision@k**, độ phù hợp của đoạn truy xuất | Bộ truy xuất có tìm được bằng chứng cần thiết không? |
| Trích dẫn | Tỷ lệ trích dẫn đúng nguồn, bao phủ khẳng định | Nguồn được dẫn có thật sự nói điều mà câu trả lời khẳng định không? |
| Gọi công cụ | Chọn đúng tool, đối số hợp lệ, đúng thứ tự, xử lý lỗi | Model có gọi đúng thao tác và dùng đúng kết quả không? |
| Ràng buộc | Cấu trúc JSON, chính sách từ chối, không lộ dữ liệu nhạy cảm | Đầu ra có tuân thủ yêu cầu của hệ thống không? |
| Vận hành | Thời gian, lỗi, token, chi phí | Chất lượng đạt được với độ trễ và ngân sách chấp nhận được không? |

### 3.1. Relevance không đồng nghĩa với đúng sự thật

Xét câu hỏi: “Gói Pro được hoàn phí trong bao lâu?”

- “Gói Pro có chính sách hoàn phí trong 30 ngày” có vẻ **liên quan** đến câu hỏi.
- Nếu tài liệu chính thức quy định **14 ngày**, câu trả lời lại **không được bằng chứng hỗ trợ**.
- “Chính sách Pro áp dụng trong 14 ngày” có thể đúng theo tài liệu, nhưng nếu tài liệu đã hết hiệu lực thì vẫn cần kiểm tra **tính hiện hành** của nguồn.

Do đó, cần tách ba phép đo: câu trả lời *đúng chủ đề*, *được ngữ cảnh cung cấp hỗ trợ*, và *đúng so với nguồn sự thật độc lập hoặc quy định đang có hiệu lực*. Một evaluator kiểm tra dựa trên context không thể tự chứng minh rằng context đó là đúng.

### 3.2. Đánh giá truy xuất và đánh giá sinh câu trả lời

Trong RAG (*Retrieval-Augmented Generation*), model nhận những đoạn tài liệu do bộ truy xuất tìm được. Một lỗi thường xảy ra ở một trong hai khâu:

1. **Retrieval sai:** tài liệu cần thiết không có trong `top-k` kết quả, hoặc đoạn văn bị cắt mất thông tin quan trọng.
2. **Generation sai:** tài liệu đúng đã có, nhưng model hiểu sai, suy diễn thêm hoặc bỏ qua yêu cầu trích dẫn.

Nếu bộ truy xuất trả về 4 tài liệu, trong đó có 2 tài liệu được gắn nhãn liên quan trên tổng số 3 tài liệu liên quan của kho dữ liệu, ta có:

\[
\mathrm{Precision@4} = \frac{2}{4}=0.50
\qquad
\mathrm{Recall@4} = \frac{2}{3}\approx0.67
\]

**Precision@k** đo tỷ lệ kết quả truy xuất là liên quan trong k kết quả; **Recall@k** đo tỷ lệ tài liệu liên quan đã được tìm thấy trong k kết quả. Việc tính hai chỉ số này đòi hỏi tập nhãn tài liệu liên quan đủ tin cậy. Khi dữ liệu chỉ có một đoạn “bằng chứng chính”, có thể bắt đầu bằng chỉ số `hit@k`: đoạn đó có xuất hiện trong top-k hay không.

## 4. Xây dựng dataset đánh giá có thể tái sử dụng

Dataset là một tập trường hợp kiểm thử có thể chạy lại khi đổi prompt, model, embedding, chunk size, bộ lọc hoặc thứ tự advisor.

Mỗi trường hợp nên chứa:

- **ID và câu hỏi:** định danh ổn định, đầu vào gần với lời hỏi thực tế.
- **Đáp án/tiêu chí kỳ vọng:** những ý bắt buộc phải có, những ý không được xuất hiện, điều kiện cần từ chối.
- **Nguồn tham chiếu:** ID và phiên bản tài liệu hoặc kết quả tool đã được kiểm chứng.
- **Kỳ vọng retrieval/tool:** tài liệu phải tìm được, công cụ nên gọi, tham số và hành vi dự kiến.
- **Nhãn phân nhóm:** đơn giản, đa bước, hỏi không có dữ liệu, dữ liệu mâu thuẫn, tiếng Việt, lỗi công cụ...
- **Phiên bản:** version dataset, version kho tài liệu và thời điểm xác nhận nguồn.

Ví dụ giả định: hệ thống hỏi đáp về dịch vụ *Sao Mai* có chính sách nội bộ `policy-v3`, trong đó “gói Pro được hoàn phí trong 14 ngày; gói Basic không hỗ trợ hoàn phí”. Đây là dữ liệu minh họa, không phải chính sách của một doanh nghiệp thực.

~~~json
{
  "datasetVersion": "refund-eval-v1",
  "cases": [
    {
      "id": "refund-pro-001",
      "question": "Gói Pro có thể hoàn phí trong bao lâu?",
      "expectedFacts": ["Gói Pro: 14 ngày"],
      "relevantDocumentIds": ["policy-v3#refund"],
      "expectedBehavior": "Trả lời 14 ngày và dẫn đúng tài liệu",
      "tags": ["rag", "normal", "vi"]
    },
    {
      "id": "refund-basic-002",
      "question": "Gói Basic có được hoàn phí không?",
      "expectedFacts": ["Gói Basic không hỗ trợ hoàn phí"],
      "relevantDocumentIds": ["policy-v3#refund"],
      "expectedBehavior": "Không tự tạo ngoại lệ",
      "tags": ["rag", "negative", "vi"]
    },
    {
      "id": "refund-exception-003",
      "question": "Nếu bị lỗi thanh toán thì thời hạn hoàn phí có đổi không?",
      "expectedFacts": [],
      "relevantDocumentIds": [],
      "expectedBehavior": "Thừa nhận tài liệu chưa đủ thông tin, đề nghị kiểm tra quy định",
      "tags": ["rag", "insufficient-context", "vi"]
    }
  ]
}
~~~

Một trường hợp tốt phải cho phép người chấm xác định *vì sao* đạt hoặc không đạt. Với câu hỏi không đủ dữ liệu, câu trả lời “chưa thể xác định” có thể là kết quả **đúng**; ép model luôn đưa ra con số sẽ làm tăng hallucination.

### 4.1. Bao phủ nhiều nhóm lỗi

Dataset không nên chỉ gồm câu hỏi thuận lợi. Cần có biến thể diễn đạt, câu đa ý, số liệu gần giống nhau, tài liệu đã hết hiệu lực, thông tin không tìm thấy, ngữ cảnh gây nhiễu, tool trả lỗi hoặc chậm, và trường hợp cần xác nhận trước khi thực hiện hành động.

Tách các nhóm kết quả theo tag. Tỷ lệ đạt chung 95% không đủ hữu ích nếu nhóm “không có nguồn” chỉ đạt 50%. Lưu các trường hợp sai đã phát hiện từ production vào bộ hồi quy sau khi ẩn thông tin cá nhân và được rà soát.

### 4.2. Đánh giá offline và online

**Offline evaluation** chạy trên bộ dữ liệu có nhãn trước khi phát hành. Nó giúp so sánh phiên bản trong điều kiện tương tự nhau, nhưng khó bao phủ mọi tình huống thực.

**Online evaluation** sử dụng dữ liệu được lấy mẫu trong môi trường vận hành, phản hồi người dùng, đánh giá của chuyên gia và các sự kiện lỗi. Cần kiểm soát quyền riêng tư, dữ liệu nhạy cảm và độ lệch mẫu; không nên mặc định rằng mọi lượt nhấn “thích” đều chứng minh câu trả lời đúng.

Với cùng dataset, cần cố định hoặc ghi rõ phiên bản corpus/index, cấu hình `top-k`, prompt, model, tham số sinh, cấu hình tool và chính sách chấm. Nếu đổi cả nguồn dữ liệu và model mà không ghi lại, khó xác định nguyên nhân cải thiện hoặc suy giảm.

## 5. Evaluation trong Spring AI

Spring AI cung cấp giao diện `Evaluator` với phương thức `evaluate(EvaluationRequest)`. Kết quả là `EvaluationResponse`, cho phép truy cập trạng thái đạt hay không đạt bằng `isPass()`, cùng thông tin phản hồi bằng `getFeedback()`.

Hai evaluator tiêu biểu:

- **`RelevancyEvaluator`:** dùng model chấm xem câu trả lời có phù hợp với câu hỏi và ngữ cảnh cung cấp không.
- **`FactCheckingEvaluator`:** kiểm tra khẳng định trong câu trả lời có được ngữ cảnh/bằng chứng hỗ trợ không. Đây là kiểm tra *grounded factuality*, không phải phép xác minh mọi sự thật trên thế giới.

Ví dụ Java dưới đây minh họa cách đánh giá một câu trả lời RAG bằng một `ChatModel` dành riêng cho việc chấm. `retrievedDocs` phải là **các tài liệu ứng dụng thực sự truy xuất được** trong lần chạy; không được thay bằng tài liệu đáp án chuẩn vì điều đó sẽ che mất lỗi retrieval.

~~~java
import java.util.List;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.FactCheckingEvaluator;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;

public final class RagEvaluationExample {

    public static void evaluate(
            ChatModel judgeModel,
            String question,
            List<Document> retrievedDocs,
            String generatedAnswer) {

        EvaluationRequest request =
                new EvaluationRequest(question, retrievedDocs, generatedAnswer);

        EvaluationResponse relevance =
                new RelevancyEvaluator(ChatClient.builder(judgeModel))
                        .evaluate(request);

        EvaluationResponse groundedness =
                FactCheckingEvaluator.builder(ChatClient.builder(judgeModel))
                        .build()
                        .evaluate(request);

        System.out.println("Relevance: " + relevance.isPass());
        System.out.println("Groundedness: " + groundedness.isPass());

        if (!relevance.isPass() || !groundedness.isPass()) {
            System.out.println("Relevance feedback: " + relevance.getFeedback());
            System.out.println("Groundedness feedback: " + groundedness.getFeedback());
        }
    }
}
~~~

Ví dụ sử dụng API được tài liệu Javadoc Spring AI hiện hành mô tả; chữ ký hoặc cách khởi tạo một số evaluator có thể khác giữa các nhánh phiên bản. `judgeModel` là bean/model được cấu hình trong ứng dụng; chạy đánh giá thực tế sẽ phát sinh lời gọi model và có chi phí. Trong kiểm thử tích hợp, có thể tổng hợp `isPass()` theo từng case và ghi feedback để xem xét; các phép kiểm có tính xác định (định dạng JSON, tham số tool, ID nguồn) nên được kiểm bằng mã thông thường.

**Không xem LLM-as-a-judge là “đáp án tuyệt đối”.** Model chấm cũng có thể sai, thiên lệch theo cách viết, thay đổi giữa các lần chạy và bị ảnh hưởng bởi prompt chấm. Với trường hợp quan trọng:

1. Viết rubric rõ: mỗi tiêu chí đạt/không đạt phải có điều kiện và bằng chứng.
2. Giữ một tập mẫu đã được người có chuyên môn chấm để kiểm tra độ nhất quán của evaluator.
3. Chạy lặp một số ca khó, kiểm tra bất đồng, phân tích false positive/false negative.
4. Cố định phiên bản của judge/prompt chấm khi so sánh hai phiên bản ứng dụng.
5. Phân biệt số điểm theo rubric do nhóm tự thiết kế với trường `isPass()` do evaluator trả về.

## 6. Kiểm thử đầy đủ luồng RAG

Chỉ chấm câu trả lời cuối cùng sẽ bỏ lỡ nguyên nhân đến từ xử lý tài liệu. Một lần đánh giá RAG hữu ích ghi lại chuỗi:

~~~text
Câu hỏi
   ↓
Tiền xử lý / viết lại truy vấn (nếu có)
   ↓
Embedding / VectorStore / bộ lọc metadata
   ↓
Top-k tài liệu + ID, phiên bản, điểm tương đồng
   ↓
Prompt sau khi ghép ngữ cảnh
   ↓
ChatModel tạo câu trả lời
   ↓
Câu trả lời + trích dẫn + kết quả đánh giá
~~~

Tại **khâu truy xuất**, kiểm tra xem các nguồn được gắn nhãn có được tìm thấy hay không, kết quả có vi phạm bộ lọc quyền truy cập không, và tài liệu có đang dùng phiên bản cũ không. Tại **khâu sinh**, kiểm tra câu trả lời có đúng vấn đề, được hỗ trợ bởi ngữ cảnh, dẫn nguồn hợp lệ và biết từ chối khi thiếu bằng chứng không.

Ví dụ phân tích hai lỗi:

| Kết quả | Retrieval | Generation | Hướng xử lý |
| --- | --- | --- | --- |
| Trả lời sai vì không có chính sách 14 ngày | Không tìm thấy `policy-v3#refund` | Model đoán “30 ngày” | Kiểm tra chunking, embedding, filter, index, `top-k` |
| Trả lời sai dù đã có chính sách 14 ngày | Tìm đúng `policy-v3#refund` | Model vẫn nói “30 ngày” | Kiểm tra prompt, cách đưa ngữ cảnh, cấu hình model, yêu cầu trích dẫn |

Nếu thay đổi chunk size hoặc embedding model, cần đánh giá lại retrieval **và** chất lượng đầu ra. Recall cao chưa đảm bảo kết quả tốt nếu câu trả lời cuối cùng diễn giải sai dữ liệu.

## 7. Kiểm thử luồng tool calling

Khi ứng dụng có thể tìm trạng thái đơn hàng, tính phí hoặc tạo yêu cầu hỗ trợ thông qua tool, câu trả lời “đúng văn phong” chưa đủ. Kết quả cần đúng về **hành động**.

Hãy lập các trường kiểm tra: `expectedTool`, `expectedArguments`, `shouldInvoke`, `expectedToolResult` và `expectedFinalResponse`. Đánh giá:

- **Lựa chọn tool:** có gọi đúng chức năng, có tránh gọi khi không cần không?
- **Đối số:** tên trường, kiểu dữ liệu, mã đơn, khoảng thời gian và các điều kiện nghiệp vụ có hợp lệ không?
- **Quyền hạn:** có chặn yêu cầu trái phép và yêu cầu xác nhận cho hành động nhạy cảm không?
- **Xử lý lỗi:** khi tool timeout hoặc trả về “không tìm thấy”, model có phản hồi đúng tình trạng thay vì bịa kết quả không?
- **Hậu điều kiện:** trạng thái hệ thống sau thao tác có khớp với mong đợi không, có gọi lặp gây tác dụng phụ không?

Trong bài kiểm thử, thay tool có tác dụng phụ bằng test double hoặc môi trường cô lập có dữ liệu cố định. Ví dụ, với câu “Xem đơn DH-123”, đầu ra kỳ vọng có thể là gọi `getOrderStatus({"orderId":"DH-123"})` một lần và tóm tắt trạng thái trả về. Nếu model tự nói “đơn đang giao” mà không gọi tool, bài kiểm thử phải thất bại dù câu trả lời nghe hợp lý.

Để tìm lỗi, ghi **tên** tool, kết quả thành công/thất bại, thời gian thực thi và mã lỗi an toàn; không cần lưu toàn bộ tham số có thông tin cá nhân.

## 8. Observability trong Spring AI gồm những gì?

Spring AI dựa vào cơ chế quan sát của hệ sinh thái Spring và **Micrometer**, có khả năng phát sinh metrics và traces cho nhiều thành phần như `ChatClient`, `Advisor`, `ChatModel`, `EmbeddingModel`, `VectorStore` và tool calling. Mức hỗ trợ chi tiết phụ thuộc phiên bản Spring AI, provider/model và cấu hình xuất telemetry.

Ba loại tín hiệu quan trọng:

| Tín hiệu | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| **Metrics** | Các số tổng hợp theo thời gian: request count, duration, errors, token usage | Theo dõi xu hướng, dashboard, cảnh báo |
| **Traces** | Các span nối nhau thành đường đi của một request | Tìm bước gây chậm/lỗi, liên hệ retrieval → model → tool |
| **Logs / events** | Bản ghi sự kiện và ngữ cảnh lỗi | Điều tra lỗi cụ thể, đối chiếu với trace ID |

### 8.1. Bản đồ các bước quan sát

Một request có thể sinh ra nhiều span; ví dụ với RAG và tool calling:

~~~text
HTTP POST /ask
└── ChatClient
    ├── Advisor: kiểm tra bộ nhớ / RAG
    │   └── VectorStore: query
    ├── ChatModel: sinh phản hồi hoặc yêu cầu dùng tool
    ├── Tool: thực thi chức năng (nếu được gọi)
    └── ChatModel: tổng hợp kết quả tool (nếu cần)
~~~

Một số tên observation được Spring AI công bố gồm `spring.ai.chat.client`, `spring.ai.advisor`, `gen_ai.client.operation`, `db.vector.client.operation` và `spring.ai.tool`. Khi truy vết, hãy quan sát **cấu trúc cha–con, thời điểm bắt đầu/kết thúc và trạng thái từng span**; các span có thể lồng nhau, vì vậy không cộng tất cả duration một cách máy móc.

### 8.2. Cấu hình tối thiểu với Spring Boot

Với ứng dụng Spring Boot có Spring AI, thường bắt đầu bằng Spring Boot Actuator và registry phù hợp. Chẳng hạn các dependency Maven sau được quản lý phiên bản bởi BOM tương thích của Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
~~~

Ví dụ `application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  tracing:
    sampling:
      probability: 0.1

spring:
  ai:
    chat:
      client:
        observations:
          log-prompt: false
          log-completion: false
    tools:
      observations:
        include-content: false
~~~

Cấu hình này nêu ý tưởng bật endpoint metrics và lấy mẫu trace, còn địa chỉ/credentials để xuất OTLP phải cấu hình theo hệ thống collector thực tế. Sau khi ứng dụng chạy, có thể kiểm tra `/actuator/metrics` hoặc `/actuator/prometheus` (nếu endpoint và registry đã sẵn sàng). Cần bảo vệ quyền truy cập các endpoint khi triển khai thật.

Spring AI **không xuất toàn bộ prompt, completion và tham số/kết quả tool theo mặc định**, vì chúng có thể chứa dữ liệu nhạy cảm. Chỉ bật các tùy chọn ghi nội dung khi thật cần để gỡ lỗi, có quy tắc lọc/ẩn dữ liệu, phân quyền, thời hạn lưu và môi trường phù hợp.

### 8.3. Đọc metrics thay vì chỉ nhìn dashboard

Các tên Prometheus sau là ví dụ được tài liệu Spring AI mô tả; sự hiện diện và tag thực tế phụ thuộc phiên bản, provider, registry và cấu hình:

| Metric (định dạng Prometheus) | Ý nghĩa |
| --- | --- |
| `gen_ai_chat_client_operation_seconds_count` | Số thao tác ChatClient hoàn thành |
| `gen_ai_chat_client_operation_seconds_sum` | Tổng thời gian các thao tác ChatClient hoàn thành |
| `gen_ai_client_operation_seconds_count` | Số lời gọi model hoàn thành |
| `gen_ai_client_operation_seconds_sum` | Tổng thời gian thực thi model |
| `gen_ai_client_token_usage_total` | Tổng token theo loại input/output/total |
| `db_vector_client_operation_seconds_count` | Số thao tác VectorStore hoàn thành |
| `db_vector_client_operation_seconds_sum` | Tổng thời gian thao tác VectorStore |

Với dữ liệu counter, độ trễ trung bình theo cửa sổ 5 phút có thể tính bằng PromQL:

~~~promql
sum(rate(gen_ai_client_operation_seconds_sum[5m]))
/
sum(rate(gen_ai_client_operation_seconds_count[5m]))
~~~

Đây là **trung bình** của các thao tác model hoàn thành, không phải p95. Muốn đo **p95**, cần có histogram bucket hoặc nguồn phân bố latency tương ứng; không thể suy ra phân vị từ hai số `_sum` và `_count`. Nếu histogram được cấu hình và xuất `_bucket`:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (rate(gen_ai_client_operation_seconds_bucket[5m]))
)
~~~

Với API streaming, **time to first token (TTFT)** là thời gian tới token đầu tiên, còn **total latency** là thời gian hoàn tất toàn bộ phản hồi. Một trace đo tổng thời gian stream không mặc nhiên cung cấp TTFT; nếu yêu cầu nghiệp vụ cần, hãy thêm phép đo riêng ở thời điểm nhận token đầu tiên.

## 9. Token, chi phí và độ trễ

Hai phiên bản có tỷ lệ trả lời đúng tương đương có thể khác xa về chi phí hoặc tốc độ. Vì vậy, nên theo dõi ít nhất:

- **Input/output tokens** trên mỗi request, số lời gọi model, độ dài context, tỷ lệ dùng cache nếu provider hỗ trợ.
- **p50/p95/p99 latency** cho toàn request và từng khâu; timeout, retry, tỷ lệ lỗi theo provider.
- **Chi phí trung bình mỗi câu trả lời thành công**, tổng chi phí theo phiên bản, chi phí riêng của evaluator và embedding.
- **Quality per cost:** mức tăng chất lượng có xứng đáng với phần chi phí và thời gian tăng thêm không?

Spring AI có thể truy cập metadata usage mà provider trả về qua `ChatResponse`. Metric token usage dựa trên dữ liệu được provider/model báo cáo; cần xác nhận các trường có được cung cấp đầy đủ cho provider, phương thức streaming và kịch bản tool đang dùng.

**Cách ước tính đơn giản** (bỏ qua giảm giá cache và các khoản phí khác):

\[
\text{Cost} =
\frac{\text{inputTokens}}{10^6}\times\text{priceInputPerMillion}
+
\frac{\text{outputTokens}}{10^6}\times\text{priceOutputPerMillion}
\]

Ví dụ với **giá giả định để thực hành**, một request dùng 1.800 input tokens và 350 output tokens; giá giả định 2 USD/triệu input tokens và 8 USD/triệu output tokens:

\[
\frac{1800\times2}{10^6}+\frac{350\times8}{10^6}
=0.0064\ \text{USD}
\]

Nếu một câu hỏi dẫn đến hai lời gọi model do tool calling, cần tính cả hai; pipeline RAG còn có thể phát sinh chi phí embedding, reranking và hạ tầng vector store. Model dùng để chấm cũng có chi phí riêng. Bảng giá nhà cung cấp có thể thay đổi, nên không hardcode giá giả định của ví dụ vào báo cáo vận hành.

## 10. Kết hợp kết quả evaluation với trace để tìm nguyên nhân

Hãy đối chiếu thay đổi chất lượng với telemetry từ cùng một phiên bản triển khai. Ví dụ:

| Hiện tượng | Dấu hiệu đối chiếu | Hướng điều tra đầu tiên |
| --- | --- | --- |
| Tỷ lệ câu trả lời có căn cứ giảm | `Recall@k` giảm; nhiều case thiếu tài liệu đúng | Phiên bản tài liệu, index, embedding, filter, chunk size |
| Retrieval vẫn tốt nhưng câu trả lời sai hơn | `Recall@k` ổn định, `faithfulness` giảm | Prompt, thứ tự context, model, tham số sinh |
| p95 request tăng đột ngột | Span VectorStore chiếm phần lớn thời gian | Query vector, index DB, kết nối, tải hệ thống |
| Request chậm trong khi retrieval nhanh | Span ChatModel tăng; output tokens tăng | Model/provider, độ dài prompt/context, max tokens, retry |
| Phản hồi sai sau khi gọi tool | Traces cho thấy tool lỗi hoặc args sai | Tool schema, xác thực, xử lý exception, chuyển kết quả tool cho model |
| Chi phí/request tăng nhưng chất lượng không tăng | Token input tăng, số lần gọi model nhiều hơn | Context dư thừa, vòng gọi tool, retry, chiến lược rerank |

**Ví dụ chẩn đoán:** phiên bản mới có độ trễ p95 tăng từ 2,1 lên 5,0 giây. Span truy xuất trung bình tăng mạnh nhưng span model gần như không đổi. Ta nên đo tiếp thời gian truy vấn vector và kiểm tra index/bộ lọc của VectorStore trước khi vội thay model. Nếu đồng thời `Recall@5` giảm, thay đổi index hoặc cách chunking là giả thuyết có cơ sở hơn.

Đây là **giả thuyết dựa trên số liệu**, chưa phải kết luận tuyệt đối. Cần phân tích theo phiên bản, nhóm yêu cầu, provider, lỗi, thời điểm và cấu hình liên quan; tránh gán các nhãn có cardinality cao như nội dung prompt hoặc user ID vào metrics.

## 11. So sánh phiên bản prompt, model và pipeline

Một quy trình cải tiến có thể lặp lại gồm:

1. **Định nghĩa mục tiêu:** ví dụ “trả lời chính sách có nguồn, không bịa thời hạn, p95 dưới ngưỡng nghiệp vụ”.
2. **Đóng băng tập kiểm thử và tiêu chí:** lưu dataset, rubrics, phiên bản nguồn tham chiếu.
3. **Chạy baseline:** ghi câu trả lời, tài liệu được tìm, quyết định gọi tool, điểm đánh giá và telemetry.
4. **Chỉ thay đổi có chủ đích:** prompt, model hoặc một khâu pipeline; ghi ID cấu hình mới.
5. **Chạy lại và phân tích theo từng nhóm:** xem cả trường hợp cải thiện và hồi quy, không chỉ trung bình.
6. **Áp dụng release gate:** chặn phát hành khi vi phạm tiêu chí bắt buộc; lấy mẫu kiểm tra sau triển khai.

Ví dụ báo cáo **minh họa**, không phải ngưỡng chuẩn của Spring AI:

| Chỉ số trên cùng dataset | Baseline v1 | Candidate v2 | Nhận xét |
| --- | ---: | ---: | --- |
| Answer relevance đạt | 91% | 95% | Tăng |
| Groundedness đạt | 97% | 96% | Giảm nhẹ; cần xem case sai |
| Retrieval Recall@5 | 89% | 93% | Tăng |
| Request p95 latency | 2,1 s | 3,2 s | Vượt ngưỡng giả định 2,5 s |
| Chi phí trung bình/request | 0,005 USD | 0,008 USD | Tăng 60% |

Candidate v2 có chất lượng relevance tốt hơn nhưng chưa đáp ứng mục tiêu thời gian; quyết định triển khai phụ thuộc mức ưu tiên, rủi ro và ngưỡng đã xác định từ trước. Không nên điều chỉnh release gate sau khi thấy điểm của phiên bản mình muốn chọn.

Một báo cáo hữu ích lưu tối thiểu: `runId`, `datasetVersion`, `corpusVersion`, `promptVersion`, `model`, `pipelineVersion`, thời gian chạy, số mẫu, điểm theo nhóm, ngưỡng, lỗi tiêu biểu, latency và cost. Trace ID của những case sai có thể liên kết báo cáo chất lượng với quá trình thực thi.

## 12. Những sai lầm thường gặp

**Chỉ xem HTTP 200 là thành công.** Request thành công về mặt kỹ thuật vẫn có thể chứa lời khuyên sai hoặc dữ liệu bịa. Cần kiểm tra ngữ nghĩa và hậu điều kiện tool.

**Đưa “đáp án chuẩn” vào context của evaluator thay cho tài liệu thực tế truy xuất.** Cách này làm RAG có vẻ tốt hơn thực tế. Phải lưu cả `retrievedDocs` thực tế và `goldenDocs` dùng làm nhãn riêng.

**Dùng cùng một model làm người trả lời và người chấm mà không kiểm soát.** LLM-as-a-judge có thể cùng mắc lỗi; bổ sung phép kiểm dựa trên quy tắc và tập nhãn do con người xác minh.

**Chỉ theo dõi average latency.** Một nhóm người dùng vẫn có thể bị chậm nghiêm trọng dù trung bình đẹp. Hãy quan sát phân bố độ trễ, p95/p99 và kích thước mẫu.

**Nhầm metric token với hóa đơn thực tế.** Usage có thể thiếu dữ liệu, khác cách tính cache, hoặc không gồm phí hạ tầng/evaluator. Đối soát với dữ liệu thanh toán và mô hình giá hiện hành.

**Ghi toàn bộ prompt, thông tin khách hàng và kết quả tool vào trace.** Dữ liệu quan sát phải tuân thủ quyền truy cập, mức tối thiểu cần thiết và quy định lưu trữ. Chỉ bật thu thập nội dung có kiểm soát khi gỡ lỗi.

**So sánh hai lần chạy có dữ liệu nền khác nhau mà không ghi phiên bản.** Corpus, index, prompt chấm hoặc cấu hình model thay đổi có thể làm phép so sánh mất ý nghĩa.

## 13. Bài thực hành gợi ý

Xây dựng một chatbot RAG Spring AI trả lời chính sách giả định của dịch vụ *Sao Mai*. Bắt đầu với 15–20 câu hỏi chia thành ba nhóm: câu có nguồn rõ ràng, câu dễ gây nhầm lẫn và câu không có nguồn. Đặt tài liệu ở kho tìm kiếm, lưu ID nguồn cho từng câu, sau đó:

1. Chạy từng câu qua pipeline và lưu tài liệu đã truy xuất cùng câu trả lời.
2. Chấm thủ công ít nhất một số ca rồi so sánh với `RelevancyEvaluator` và `FactCheckingEvaluator`.
3. Ghi `Recall@k`, tỷ lệ trả lời được bằng chứng hỗ trợ và số trường hợp từ chối đúng khi thiếu dữ liệu.
4. Bật Actuator/metrics/tracing phù hợp; thu độ trễ truy xuất, độ trễ model, token và ước tính chi phí.
5. Thay một yếu tố, chẳng hạn `top-k` từ 3 sang 5, chạy lại cùng dataset và giải thích cả thay đổi chất lượng lẫn tài nguyên.

**Tiêu chí tự kiểm tra:** bạn phải phân biệt được một câu sai do thiếu tài liệu với một câu sai dù tài liệu đã có, chỉ ra span nên xem khi request chậm và trình bày rõ dữ liệu nào được dùng để tính chi phí.

## 14. Ghi nhớ

- **Evaluation** đo mức độ ứng dụng đáp ứng yêu cầu: liên quan, có căn cứ, đúng nghiệp vụ và đúng thao tác.
- **Observability** cho thấy hành trình request, thời gian của từng bước, lỗi và tài nguyên tiêu thụ.
- **RAG** cần đánh giá riêng retrieval và generation; **tool calling** cần đánh giá hành động, đối số và hậu điều kiện.
- **Metrics và traces không tự chứng minh tính đúng đắn nội dung.** Chúng cần kết hợp với dataset, rubric và đánh giá của con người.
- Cải tiến nên được quyết định theo **chất lượng, độ trễ và chi phí trên cùng một bộ tiêu chí**, có lưu phiên bản để phát hiện hồi quy.

### Tài liệu tham khảo chính thức

- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Chat Response Metadata](https://docs.spring.io/spring-ai/reference/api/usage-handling.html)
- [Spring AI — Javadoc `EvaluationRequest`](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/evaluation/EvaluationRequest.html)
- [Spring AI — Javadoc `FactCheckingEvaluator`](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/chat/evaluation/FactCheckingEvaluator.html)
