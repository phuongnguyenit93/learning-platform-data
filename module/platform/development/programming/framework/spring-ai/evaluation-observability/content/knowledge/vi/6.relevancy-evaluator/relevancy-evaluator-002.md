# RelevancyEvaluator: Cung cấp câu hỏi, phản hồi và dữ liệu hỗ trợ

## 1. Mục tiêu của bài học

Một ứng dụng Spring AI dùng RAG hoặc gọi công cụ có thể trả lời rất tự nhiên nhưng vẫn **lạc câu hỏi**, **bỏ qua dữ liệu liên quan** hoặc **dựa trên tài liệu không đúng với lượt chạy**. Muốn đánh giá chất lượng phản hồi, bộ đánh giá phải nhìn thấy cùng một bộ thông tin làm căn cứ, thay vì chỉ nhìn thấy một câu trả lời tách rời.

Trong Spring AI, `RelevancyEvaluator` nhận một `EvaluationRequest` gồm ba phần:

1. **Câu hỏi của người dùng (`userText`):** hệ thống được yêu cầu giải quyết việc gì?
2. **Phản hồi của mô hình (`responseContent`):** hệ thống thực sự trả lời thế nào?
3. **Dữ liệu hỗ trợ (`dataList`):** tài liệu RAG hoặc dữ liệu tham chiếu giúp xác định phản hồi có phù hợp với câu hỏi và ngữ cảnh hay không?

Bài này đi sâu vào **cách chuẩn bị, truyền và kiểm tra ba đầu vào**. Đây là một bước trong việc đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu kiểm thử, bên cạnh fact checking, kiểm thử luồng RAG/công cụ và quan sát metrics, traces, chi phí, độ trễ qua các phiên bản prompt/model/pipeline.

Sau bài học, bạn có thể tạo `EvaluationRequest` đúng kiểu dữ liệu; viết ví dụ kiểm thử một trường hợp; lấy các `Document` đã truy xuất trong RAG để chấm; và tránh những sai lệch do truyền sai câu hỏi, sai phản hồi hoặc sai nguồn.

## 2. Nhìn toàn cảnh: một trường hợp đánh giá cần những gì?

Giả sử ứng dụng tư vấn chính sách cho người mua hàng:

| Vai trò | Giá trị ví dụ |
| --- | --- |
| Câu hỏi | “Đơn hàng trực tuyến được yêu cầu đổi trả trong bao lâu?” |
| Tài liệu A (truy xuất) | “Khách có thể yêu cầu đổi trả đơn hàng trực tuyến trong vòng 14 ngày kể từ khi nhận hàng.” |
| Tài liệu B (truy xuất) | “Sản phẩm đổi trả phải đáp ứng điều kiện nguyên trạng theo chính sách.” |
| Câu trả lời | “Khách được yêu cầu đổi trả trong 14 ngày kể từ khi nhận hàng.” |

Người đánh giá xem **câu trả lời có trả lời đúng câu hỏi dựa trên các tài liệu được cung cấp không**. Với ví dụ trên, đây là một trường hợp *được kỳ vọng là phù hợp*; kết quả của LLM chấm có thể thay đổi theo model và prompt đánh giá.

~~~mermaid
flowchart TD
    U["Câu hỏi gốc"] --> Q["userText: String"]
    R["Retriever / dữ liệu công cụ"] --> D["dataList: List<Document>"]
    A["Câu trả lời cuối cùng"] --> C["responseContent: String"]
    Q --> ER["EvaluationRequest"]
    D --> ER
    C --> ER
    ER --> E["RelevancyEvaluator.evaluate(...)"]
    E --> V["EvaluationResponse: isPass()"]
~~~

Ba đầu vào có các vai trò **khác nhau**. Nếu đưa đáp án kỳ vọng của người viết test vào `dataList` trong khi mô hình sinh câu trả lời chưa từng thấy dữ liệu đó, phép đánh giá không còn phản ánh đúng lượt RAG thực tế. Tương tự, nếu `userText` không phải câu hỏi được đem đi xử lý, judge có thể đánh trượt một câu trả lời vốn đúng trong ngữ cảnh thực.

## 3. Cấu trúc EvaluationRequest trong Spring AI

Giao diện đánh giá là:

~~~java
@FunctionalInterface
public interface Evaluator {
    EvaluationResponse evaluate(EvaluationRequest evaluationRequest);
}
~~~

Các API chính:

| Kiểu / phương thức | Mục đích |
| --- | --- |
| `EvaluationRequest(String userText, List<Document> dataList, String responseContent)` | Truyền đầy đủ câu hỏi, ngữ cảnh và phản hồi. |
| `getUserText()` | Đọc câu hỏi đã cung cấp. |
| `getDataList()` | Đọc danh sách tài liệu hỗ trợ. |
| `getResponseContent()` | Đọc chuỗi phản hồi cần chấm. |
| `RelevancyEvaluator.evaluate(request)` | Gọi mô hình chấm và trả `EvaluationResponse`. |
| `EvaluationResponse.isPass()` | Đọc phán quyết đạt / không đạt. |

Trong API Spring AI 2.1, `dataList` có kiểu `List<Document>` với `Document` thuộc package `org.springframework.ai.document`. Đừng thay bằng `List<String>` khi gọi constructor ba tham số: hãy chuyển nội dung văn bản thành các đối tượng `Document`.

`EvaluationRequest` còn có các constructor hai tham số dành cho tình huống khác (`userText` và `responseContent`, hoặc `dataList` và `responseContent`). **Với RelevancyEvaluator và RAG, nên dùng constructor ba tham số** để judge có cả truy vấn và nguồn hỗ trợ. Việc một constructor cho phép bỏ ngữ cảnh không có nghĩa cách đó đo được độ phù hợp theo tài liệu nguồn.

### 3.1. Câu hỏi: `userText`

`userText` nên là câu hỏi thực sự mà ứng dụng vừa nhận hoặc xử lý cho lượt đó, không phải một câu do tester viết lại sau khi xem đáp án.

Ví dụ:

~~~java
String userText =
        "Thời hạn đổi trả đơn hàng trực tuyến là bao lâu?";
~~~

Cần lưu ý:

- Giữ nguyên đối tượng người dùng hỏi và điều kiện quan trọng (“trực tuyến”, “từ ngày nhận hàng”).
- Không tráo câu hỏi của case A với phản hồi và tài liệu của case B.
- Với câu hỏi tiếp nối như “Còn đơn mua tại cửa hàng?”, lịch sử hội thoại hoặc truy vấn đã được làm rõ có thể cần được đưa vào **ngữ cảnh đánh giá có chủ đích**; lưu cả câu hỏi gốc và phiên bản làm rõ để truy vết. Không tự sửa nghĩa câu hỏi mà không ghi nhận.
- Không nhét toàn bộ system prompt hoặc trace vào trường `userText` chỉ để judge có thêm thông tin.

### 3.2. Phản hồi: `responseContent`

`responseContent` là văn bản **cuối cùng mà người dùng nhận được**, sau bước sinh câu trả lời:

~~~java
String responseContent =
        "Khách hàng có thể yêu cầu đổi trả trong vòng 14 ngày từ ngày nhận hàng.";
~~~

Đừng truyền prompt đã gửi mô hình, query gửi vector store, nội dung suy luận nội bộ hoặc toàn bộ JSON response nếu mục tiêu là chấm phần văn bản trả lời cho người dùng.

Nếu API sinh trả kết quả có cấu trúc, hãy xác định trường văn bản mà người dùng thực sự đọc và giữ cùng quy ước khi so sánh các phiên bản. Chẳng hạn một trường hợp bao gồm câu trả lời và phần trích dẫn có thể yêu cầu chấm nguyên phản hồi hiển thị, thay vì chỉ câu đầu tiên.

### 3.3. Dữ liệu hỗ trợ: `dataList`

`dataList` là danh sách `Document` chứa bằng chứng hoặc ngữ cảnh để đánh giá:

~~~java
import java.util.List;
import org.springframework.ai.document.Document;

List<Document> supportingData = List.of(
    new Document("Chính sách: đơn online được yêu cầu đổi trả "
        + "trong vòng 14 ngày kể từ ngày nhận hàng."),
    new Document("Điều kiện: sản phẩm phải còn nguyên trạng "
        + "theo quy định đổi trả.")
);
~~~

Mỗi `Document` có phần nội dung văn bản và có thể mang metadata nguồn. Trong test RAG, nên giữ **đúng những chunk đã được truy xuất/cung cấp cho generator**, với nội dung, số lượng và thứ tự tương ứng lượt chạy. Một tài liệu hợp chủ đề nhưng nằm ngoài bộ tài liệu thực tế không nên được thêm vào chỉ để “giúp” judge.

Nếu dữ liệu nằm ở bảng SQL, kết quả API hay kết quả hàm, bạn có thể chuyển phần **đã thực sự được công cụ trả về** thành `Document` để dùng làm ngữ cảnh, rồi xác định rõ ý nghĩa phép chấm trong rubric. Điều này không có nghĩa `RelevancyEvaluator` tự đánh giá độ đúng của công cụ hay độ trung thực của database.

## 4. Ví dụ hoàn chỉnh: chấm ba giá trị được chuẩn bị thủ công

Ví dụ Java đơn giản giúp kiểm tra cách ghép dữ liệu trước khi kết nối retriever. Giả sử dự án đã cấu hình bean `ChatModel` và đang ở một service hoặc bài test có biến `judgeModel`:

~~~java
import java.util.List;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;

public final class RelevancyCheck {

    private final RelevancyEvaluator evaluator;

    public RelevancyCheck(ChatModel judgeModel) {
        this.evaluator =
                new RelevancyEvaluator(ChatClient.builder(judgeModel));
    }

    public EvaluationResponse check(String question,
                                    List<Document> supportingData,
                                    String generatedAnswer) {
        if (question == null || question.isBlank()) {
            throw new IllegalArgumentException("Thiếu câu hỏi");
        }
        if (generatedAnswer == null || generatedAnswer.isBlank()) {
            throw new IllegalArgumentException("Thiếu câu trả lời");
        }
        if (supportingData == null || supportingData.isEmpty()) {
            throw new IllegalArgumentException("Thiếu dữ liệu hỗ trợ");
        }

        EvaluationRequest request = new EvaluationRequest(
                question,
                supportingData,
                generatedAnswer
        );

        return evaluator.evaluate(request);
    }
}
~~~

Cách gọi:

~~~java
RelevancyCheck checker = new RelevancyCheck(judgeModel);

String question = "Đơn online có thể đổi trả trong bao lâu?";
List<Document> sources = List.of(
    new Document("Đơn online được yêu cầu đổi trả trong 14 ngày "
        + "tính từ thời điểm nhận hàng.")
);
String answer = "Khách hàng có 14 ngày kể từ khi nhận hàng để yêu cầu đổi trả.";

EvaluationResponse evaluation = checker.check(
        question,
        sources,
        answer
);

System.out.println("Relevancy pass: " + evaluation.isPass());
~~~

Giá trị `true` là **kỳ vọng hợp lý** đối với ví dụ này, nhưng không thể khẳng định chắc chắn khi chưa chạy với một judge model cụ thể. `RelevancyEvaluator` dùng LLM để đưa ra nhận định; nó không thực hiện so sánh cứng hai chuỗi. Hàm kiểm tra đầu vào ở ví dụ là **quy ước phòng lỗi của ứng dụng**, không phải yêu cầu bắt buộc của toàn bộ Spring AI.

Để kiểm tra dữ liệu đã ghép **trước khi phát sinh chi phí gọi judge**, có thể kiểm tra ba getter:

~~~java
EvaluationRequest request =
        new EvaluationRequest(question, sources, answer);

System.out.println(request.getUserText());
System.out.println(request.getDataList().size());
System.out.println(request.getResponseContent());
~~~

Trong ứng dụng thật, tránh in trực tiếp câu hỏi, tài liệu và phản hồi vào log nếu chúng có thể chứa dữ liệu riêng tư.

## 5. Truyền chính xác tài liệu hỗ trợ từ một lượt RAG

Một lỗi phổ biến là chạy RAG để sinh câu trả lời, rồi gọi retriever **lần thứ hai** để lấy “context cho evaluator”. Vì truy vấn, chỉ số vector, filter, thứ tự xếp hạng hoặc dữ liệu có thể khác, bạn đang chấm với tài liệu mà generator chưa chắc đã nhìn thấy.

Cách phù hợp hơn là lấy danh sách `Document` mà **lượt RAG đã sử dụng**. Tài liệu tham chiếu Spring AI 2.1 hướng dẫn lấy context qua metadata key của `RetrievalAugmentationAdvisor`:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;
import org.springframework.ai.rag.advisor.RetrievalAugmentationAdvisor;
import org.springframework.ai.rag.retrieval.search.VectorStoreDocumentRetriever;
import org.springframework.ai.vectorstore.VectorStore;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class RagRelevancyInputTest {

    @Autowired
    ChatModel chatModel;

    @Autowired
    VectorStore vectorStore;

    @Test
    void useExactlyTheRetrievedDocuments() {
        String question = "Thời hạn đổi trả đơn online là bao lâu?";

        RetrievalAugmentationAdvisor ragAdvisor =
                RetrievalAugmentationAdvisor.builder()
                        .documentRetriever(
                                VectorStoreDocumentRetriever.builder()
                                        .vectorStore(vectorStore)
                                        .build())
                        .build();

        ChatResponse chatResponse = ChatClient.builder(chatModel)
                .build()
                .prompt(question)
                .advisors(ragAdvisor)
                .call()
                .chatResponse();

        assertThat(chatResponse).isNotNull();

        List<Document> retrieved = chatResponse.getMetadata().get(
                RetrievalAugmentationAdvisor.DOCUMENT_CONTEXT);

        assertThat(retrieved).isNotNull().isNotEmpty();

        String answer = chatResponse.getResult()
                .getOutput()
                .getText();

        assertThat(answer).isNotBlank();

        EvaluationRequest request =
                new EvaluationRequest(question, retrieved, answer);

        RelevancyEvaluator evaluator =
                new RelevancyEvaluator(ChatClient.builder(chatModel));

        EvaluationResponse verdict = evaluator.evaluate(request);

        assertThat(verdict.isPass()).isTrue();
    }
}
~~~

**Điều kiện chạy:** test cần có `VectorStore` đã nạp tài liệu mẫu về đổi trả, bean `ChatModel`, dependency Spring AI RAG và test, cùng cấu hình model hợp lệ. Đây là **integration test có gọi mô hình thật**, nên kết quả có thể thay đổi và có chi phí/độ trễ. Nếu muốn dùng judge model riêng, inject và truyền một bean `ChatModel` riêng vào `RelevancyEvaluator`.

Từ ví dụ trên, chú ý ba nguồn dữ liệu:

| Tham số truyền vào `EvaluationRequest` | Dữ liệu lấy từ |
| --- | --- |
| `question` | Biến chứa câu hỏi ban đầu gửi `ChatClient` |
| `retrieved` | `chatResponse.getMetadata().get(RetrievalAugmentationAdvisor.DOCUMENT_CONTEXT)` |
| `answer` | `chatResponse.getResult().getOutput().getText()` |

Metadata key phụ thuộc advisor/luồng RAG đã dùng. Nếu ứng dụng chuyển sang `QuestionAnswerAdvisor` hoặc một pipeline tùy biến, hãy lấy context từ đúng cơ chế mà luồng đó cung cấp. Không giả định mọi advisor chia sẻ cùng metadata key.

Nếu ứng dụng lọc, nén, bỏ chunk hoặc thay đổi tài liệu **sau retrieval nhưng trước generation**, cần lưu bộ context cuối cùng mà generator đã nhận; chỉ lấy danh sách của một bước retrieval trước đó có thể không đủ để tái hiện.

## 6. Khi dữ liệu hỗ trợ đến từ công cụ (tool calling)

Luồng gọi công cụ có cấu trúc tương tự RAG ở góc nhìn đánh giá: câu hỏi của người dùng, đầu ra công cụ dùng làm căn cứ và câu trả lời cuối của trợ lý.

Ví dụ trợ lý gọi API tra cứu đơn hàng và nhận một kết quả đã được chuẩn hóa:

~~~text
Câu hỏi:
"Đơn hàng DH-204 có được đổi trả không?"

Kết quả từ công cụ tra cứu:
orderId=DH-204
receivedDate=2026-11-20
returnDeadline=2026-12-04
returnEligible=true

Câu trả lời cuối của trợ lý:
"Đơn hàng DH-204 còn đủ điều kiện yêu cầu đổi trả,
hạn cuối là ngày 04/12/2026."
~~~

Nếu mục tiêu là đánh giá câu trả lời **có phù hợp với kết quả công cụ và câu hỏi hay không**, ta có thể đóng gói:

~~~java
String question = "Đơn hàng DH-204 có được đổi trả không?";

String toolOutput = """
        orderId=DH-204
        receivedDate=2026-11-20
        returnDeadline=2026-12-04
        returnEligible=true
        """;

String finalAnswer =
        "Đơn hàng DH-204 đủ điều kiện đổi trả đến ngày 04/12/2026.";

EvaluationRequest request = new EvaluationRequest(
        question,
        List.of(new Document(toolOutput)),
        finalAnswer
);
~~~

Đây là **cách mô hình hóa dữ liệu hỗ trợ để chấm**, không phải tuyên bố `RelevancyEvaluator` tự thu thập kết quả tool hoặc tự hiểu hợp đồng API. Bạn cần lấy kết quả đã trả về ở **chính lượt tool call** và lưu lại quy tắc xử lý kết quả đó.

Trong một chuỗi nhiều tool call, mỗi output có thể cần được chuẩn hóa cùng tên công cụ, thời điểm, tham số và phiên bản dữ liệu để tránh nhập nhằng. Nếu tool chỉ trả mã trạng thái hoặc dữ liệu chưa đủ kết luận, đừng đưa vào `dataList` một thông tin “tự suy ra” mà generator chưa có.

Việc kiểm tra response phù hợp với tool output **không xác minh dữ liệu công cụ là đúng**. Muốn đo độ chính xác nghiệp vụ, cần xác minh kết quả công cụ hoặc so sánh với nguồn chuẩn một cách độc lập.

## 7. Chuẩn hóa dữ liệu để bộ chấm có thể so sánh

### Những quyết định quan trọng

| Vấn đề | Cách xử lý gợi ý | Rủi ro nếu bỏ qua |
| --- | --- | --- |
| Một câu hỏi có nhiều điều kiện | Giữ nguyên điều kiện trong `userText` | Chấm đạt câu trả lời mới giải quyết một phần câu hỏi |
| Câu trả lời chứa nhiều trường | Chấm phần nội dung cuối thực sự hiển thị | Chấm nhầm dữ liệu JSON hoặc text trung gian |
| Nhiều chunk RAG | Giữ đúng nội dung và tập chunk đã được đưa cho generator | Lệch context, kết quả không tái hiện được |
| Chunk có metadata nguồn | Giữ ID nguồn/phiên bản cho điều tra, không giả định metadata tự được judge đọc như bằng chứng | Khó tìm nguyên nhân khi tài liệu sai phiên bản |
| Không truy xuất được tài liệu | Ghi nhận `no_context` và có chính sách test riêng | Đánh đồng lỗi retrieval với lỗi generation |
| Thay đổi truy vấn khi tìm kiếm | Ghi cả câu hỏi gốc và query sau rewrite | Không xác định được vì sao retriever lấy tài liệu khác |
| Context quá dài | Kiểm soát kích thước từ lúc tạo prompt, ghi nhận việc cắt bớt | Judge chấm trên context khác, vượt giới hạn token |
| Dữ liệu nhạy cảm | Che thông tin riêng tư trước khi lưu trace hoặc gửi judge theo chính sách hệ thống | Rò rỉ dữ liệu qua log hoặc nhà cung cấp model |

Không nên tự thêm “gold answer” của tập kiểm thử vào `dataList` trong một bài đánh giá **tính phù hợp với context thực của pipeline**, vì judge có thể chấm dựa trên đáp án mà generator chưa được cấp. Nếu chủ đích là đánh giá theo **đáp án chuẩn**, hãy xem đó là một tiêu chí khác và lưu tách biệt để không làm sai lệch kết quả so sánh RAG.

### Quy tắc nhanh trước khi gọi evaluator

~~~text
[ ] userText là câu hỏi thuộc chính lượt cần chấm
[ ] responseContent là phản hồi cuối của đúng lượt đó
[ ] dataList gồm các Document thực sự được dùng làm căn cứ
[ ] Không tráo context giữa các case hoặc giữa các phiên bản
[ ] Trường hợp thiếu context đã có chính sách xử lý rõ
[ ] Có ID / version để tái hiện nguồn, prompt, model và judge
[ ] Dữ liệu riêng tư được xử lý theo chính sách áp dụng
~~~

## 8. Kết nối tập dữ liệu đánh giá với observability

Mỗi `EvaluationRequest` là **một trường hợp**. Khi chạy hàng trăm trường hợp, kết quả mới giúp nhận diện thay đổi chất lượng qua từng phiên bản. Mẫu dữ liệu kiểm thử nên lưu **đầu vào có kiểm soát** và dữ liệu quan sát được:

~~~json
{
  "caseId": "return-policy-01",
  "question": "Đơn online được đổi trả trong bao lâu?",
  "expectedBehavior": "Nêu thời hạn 14 ngày tính từ ngày nhận hàng",
  "contextSourceIds": ["returns-policy:v3:chunk-02"],
  "promptVersion": "rag-prompt-07",
  "answerModelVersion": "model-a",
  "judgeModelVersion": "judge-b",
  "judgePromptVersion": "relevancy-rubric-01"
}
~~~

Ví dụ trên là **lược đồ minh họa**, không phải định dạng JSON bắt buộc của Spring AI. Trong thực nghiệm, lưu kèm **nội dung/chữ ký context thực tế, câu trả lời thực tế, phán quyết**, thời gian truy xuất, thời gian sinh, thời gian chấm và token usage; chỉ lưu những trường được phép theo chính sách dữ liệu.

Nếu pass rate giảm sau khi thay prompt hoặc điều chỉnh `topK`, hãy xem chuỗi dữ liệu theo thứ tự:

1. **Câu hỏi:** người dùng có đặt câu hỏi khó hơn, thay đổi ngôn ngữ hoặc thông tin yêu cầu không?
2. **Context:** danh sách tài liệu có bị đổi nguồn, thiếu chunk hoặc lấy sai phiên bản không?
3. **Response:** mô hình có bỏ qua tài liệu hoặc thêm thông tin ngoài context không?
4. **Judge:** phiên bản prompt/model chấm có thay đổi, hoặc cách gửi `EvaluationRequest` có lỗi không?
5. **Vận hành:** traces và metrics cho biết retrieval, generation hay lượt đánh giá đang làm tăng độ trễ/chi phí?

Ví dụ cùng một câu hỏi: phiên bản A truy xuất chunk chính sách “14 ngày”, phiên bản B truy xuất nhầm chunk bảo hành “12 tháng”. Nếu câu trả lời B bị đánh trượt, nguyên nhân gốc có thể là retrieval dù mô hình sinh đã tuân theo đúng context mà nó nhận. **Chỉ số relevancy riêng lẻ chưa đủ để kết luận bước nào có lỗi.**

Có thể tính tỷ lệ đạt `passRate = số case có isPass() == true / số case được đánh giá hợp lệ`. Chỉ so sánh các lần chạy trên cùng tập case hoặc tập đã kiểm soát độ khó, cùng tiêu chí judge. Cần xem thêm các case chuyển trạng thái `PASS → FAIL` hoặc `FAIL → PASS` và đối chiếu với đánh giá của con người khi cần.

## 9. Những lỗi thường gặp và cách phân biệt

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Câu trả lời đúng nhưng bị chấm trượt | Câu hỏi truyền sai hoặc context không đầy đủ | Đối chiếu ba getter và trace của cùng request |
| Lúc đạt lúc trượt với cùng một case | Judge model có biến động hoặc cấu hình khác | Ghi model, prompt, tham số và phản hồi judge |
| Luồng RAG trả lời sai dù retriever lấy được tài liệu | Tài liệu không được đưa đầy đủ vào prompt, hoặc generation bỏ sót | So sánh retrieved documents với context đến generator |
| Tất cả case thiếu tài liệu đều trượt | `dataList` rỗng trong phép đo dựa trên context | Tách trường hợp `no_context` và quy tắc từ chối trả lời |
| Chỉ số tăng sau khi dùng gold answer làm context | Dữ liệu đánh giá bị “rò rỉ đáp án” vào judge | Chỉ dùng nguồn mà pipeline thực sự có |
| Đánh giá tool output đạt nhưng giá trị nghiệp vụ sai | Công cụ trả dữ liệu sai hoặc đã lỗi thời | Kiểm thử API/tool và nguồn chuẩn riêng |

**Phân biệt:** `RelevancyEvaluator` đo sự ăn khớp của phản hồi với truy vấn và ngữ cảnh cung cấp. Kiểm tra từng khẳng định có được tài liệu chứng minh hay không thường cần `FactCheckingEvaluator` hoặc một bộ kiểm tra groundedness khác. Chất lượng **retrieval** cũng cần phép đo riêng.

## 10. Bài tập thực hành

1. Tạo ba `EvaluationRequest` có **cùng câu hỏi và cùng danh sách tài liệu** nhưng ba phản hồi: đúng trọng tâm, lạc đề, và đúng chủ đề nhưng mâu thuẫn số ngày. Dự đoán kết quả trước khi gọi judge.
2. Thêm một tài liệu thứ hai có điều kiện đổi trả. Quan sát liệu câu trả lời chỉ nêu thời hạn có bị chấm khác khi rubric yêu cầu trả lời đủ điều kiện.
3. Trong một RAG test, lấy `Document` từ metadata của lượt `RetrievalAugmentationAdvisor` và so với danh sách chunk thực sự có trong trace của generator.
4. Tạo một case `no_context` và đề xuất cách kiểm tra hành vi “không đủ dữ liệu để trả lời” mà không đánh đồng với lỗi của các case có đủ context.
5. Lưu `caseId`, `question`, `contextSourceIds`, `response`, `isPass`, `promptVersion` và `judgeModelVersion` cho hai lần chạy; chỉ rõ case nào đổi kết quả và nguyên nhân có bằng chứng.

**Ghi nhớ:** Trong Spring AI, cách cung cấp đúng `userText`, `responseContent` và `List<Document> dataList` quyết định phép đánh giá có thực sự nói về lượt RAG hoặc tool call mà bạn muốn kiểm tra hay không. Hãy **giữ nguyên bằng chứng của cùng lượt chạy** và lưu đủ metadata để tái hiện trước khi so sánh chất lượng, metrics, traces, chi phí và độ trễ giữa các phiên bản.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): ý nghĩa ba trường đầu vào, `RelevancyEvaluator` và ví dụ lấy context từ `RetrievalAugmentationAdvisor`.
- [Spring AI 2.1.0 API — EvaluationRequest](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/evaluation/EvaluationRequest.html): constructor và getter cho câu hỏi, danh sách `Document`, phản hồi.
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html): các thành phần của pipeline RAG và đường đi của tài liệu ngữ cảnh.
