# RelevancyEvaluator: Mục đích đánh giá sự phù hợp với câu hỏi và ngữ cảnh

## 1. Vì sao cần đánh giá relevancy?

Trong ứng dụng Spring AI, mô hình có thể trả lời bằng một đoạn văn trôi chảy nhưng lại **không giải quyết đúng câu hỏi**, hoặc đưa ra thông tin **không phù hợp với những tài liệu mà hệ thống vừa truy xuất**. Điều này thường xảy ra trong luồng Retrieval-Augmented Generation (RAG): câu hỏi của người dùng được dùng để tìm tài liệu, tài liệu được đưa vào prompt, rồi mô hình sinh câu trả lời.

Ví dụ, một trợ lý tra cứu chính sách bán hàng nhận:

- **Câu hỏi (query):** “Khách mua hàng trực tuyến có thể đổi trả trong bao lâu?”
- **Ngữ cảnh truy xuất (context):** “Đơn hàng trực tuyến được yêu cầu đổi trả trong vòng 14 ngày kể từ khi nhận hàng.”
- **Câu trả lời A:** “Khách có thể yêu cầu đổi trả trong vòng 14 ngày kể từ khi nhận hàng.”
- **Câu trả lời B:** “Bạn có thể theo dõi tình trạng đơn hàng trong mục Đơn hàng của tôi.”

Cả A và B đều có thể đúng về mặt ngôn ngữ. Tuy nhiên, chỉ A trực tiếp trả lời câu hỏi và bám vào ngữ cảnh đã cung cấp. Một bài kiểm thử truyền thống chỉ xác nhận HTTP 200, phản hồi không rỗng hoặc JSON đúng cấu trúc sẽ không phát hiện được vấn đề ở B.

**RelevancyEvaluator** của Spring AI giúp kiểm tra tính phù hợp của câu trả lời với **câu hỏi ban đầu và ngữ cảnh được cung cấp**, bằng cách dùng một mô hình AI khác (hoặc cùng mô hình) đóng vai trò người chấm. Đây là một tín hiệu chất lượng cho các phiên bản prompt, model và pipeline RAG; nó không tự chứng minh toàn bộ câu trả lời là đúng sự thật.

Sau bài này, bạn có thể:

1. Phân biệt sự phù hợp với câu hỏi, sự phù hợp với tài liệu nguồn và độ chính xác thực tế.
2. Hiểu dữ liệu đầu vào và cơ chế ra quyết định của `RelevancyEvaluator`.
3. Viết một bước đánh giá bằng Java, tích hợp vào kiểm thử RAG.
4. Đọc và tổng hợp kết quả để tìm nguyên nhân suy giảm chất lượng qua các phiên bản.

## 2. “Phù hợp” ở đây gồm những mối quan hệ nào?

Xét ba thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `query` / `userText` | Câu hỏi thực sự của người dùng | “Thời hạn đổi trả đơn online?” |
| `context` / `dataList` | Những đoạn tài liệu mà ứng dụng sử dụng làm căn cứ | “Được đổi trả trong 14 ngày từ ngày nhận hàng.” |
| `response` / `responseContent` | Câu trả lời được mô hình tạo ra | “Thời hạn là 14 ngày.” |

Hai câu hỏi kiểm tra quan trọng là:

- **Câu trả lời ↔ câu hỏi:** Nội dung phản hồi có giải quyết điều người dùng hỏi hay chỉ nói về một chủ đề gần giống?
- **Câu trả lời ↔ ngữ cảnh:** Phản hồi có ăn khớp với tài liệu được cấp hay đưa ra chi tiết không có cơ sở, thậm chí mâu thuẫn với tài liệu?

Ngoài ra còn một mối quan hệ khác cần đo **riêng**: tài liệu được truy xuất có liên quan đến câu hỏi hay không (**retrieval relevance**). Nếu bộ truy xuất lấy nhầm tài liệu về vận chuyển thay vì đổi trả, lỗi đã xuất hiện trước khi mô hình bắt đầu trả lời. `RelevancyEvaluator` nhìn vào bộ ba câu hỏi – câu trả lời – ngữ cảnh, nhưng chỉ một phán quyết cuối không thể chỉ rõ lỗi nằm ở truy xuất hay sinh câu trả lời.

~~~mermaid
flowchart TD
    Q["Câu hỏi người dùng"] --> R["Retriever tìm tài liệu"]
    R --> C["Ngữ cảnh truy xuất"]
    Q --> G["Mô hình tạo câu trả lời"]
    C --> G
    G --> A["Câu trả lời"]
    Q --> E["RelevancyEvaluator"]
    C --> E
    A --> E
    E --> V{"Kết quả đánh giá"}
    V --> P["PASS: phù hợp"]
    V --> F["FAIL: cần phân tích"]
~~~

### Các trường hợp dễ nhầm

| Câu hỏi | Ngữ cảnh | Câu trả lời | Nhận xét |
| --- | --- | --- | --- |
| “Đổi trả trong bao lâu?” | “Trong 14 ngày.” | “Trong 14 ngày.” | Phù hợp với cả câu hỏi và ngữ cảnh. |
| “Đổi trả trong bao lâu?” | “Trong 14 ngày.” | “Có thể xem đơn hàng trên website.” | Lạc trọng tâm câu hỏi. |
| “Đổi trả trong bao lâu?” | “Trong 14 ngày.” | “Trong 30 ngày.” | Đúng chủ đề nhưng mâu thuẫn với ngữ cảnh. |
| “Đổi trả trong bao lâu?” | “Trong 14 ngày.” | “Trong 14 ngày và luôn được hoàn phí vận chuyển.” | Có phần đúng, có thêm khẳng định chưa được tài liệu hỗ trợ. Cần kiểm tra fact checking/groundedness bổ sung. |
| “Đổi trả trong bao lâu?” | Chỉ có chính sách bảo hành | “Không đủ thông tin về đổi trả từ tài liệu hiện có.” | Câu trả lời thừa nhận thiếu căn cứ; cần quy định rõ kỳ vọng cho trường hợp không đủ ngữ cảnh. |

Đây là **nhãn kỳ vọng khi thiết kế tập đánh giá**, không phải kết quả đã chạy thực tế từ `RelevancyEvaluator`. Mô hình chấm có thể bất đồng với người gán nhãn, đặc biệt ở các trường hợp biên.

## 3. RelevancyEvaluator vận hành như thế nào?

Spring AI định nghĩa giao diện đánh giá chung:

~~~java
@FunctionalInterface
public interface Evaluator {
    EvaluationResponse evaluate(EvaluationRequest evaluationRequest);
}
~~~

`RelevancyEvaluator` triển khai `Evaluator`. Khi gọi `evaluate(...)`, thành phần này:

1. Nhận `EvaluationRequest` gồm câu hỏi, danh sách tài liệu ngữ cảnh và câu trả lời.
2. Kết hợp các giá trị này vào một `PromptTemplate` dành cho mô hình chấm.
3. Gọi `ChatClient` của mô hình chấm để yêu cầu quyết định `YES` hoặc `NO`.
4. Chuyển câu trả lời của mô hình chấm thành `EvaluationResponse`.

Prompt mặc định đặt câu hỏi liệu *câu trả lời có phù hợp với thông tin ngữ cảnh dành cho truy vấn hay không*, và yêu cầu chỉ đưa ra `YES` hoặc `NO`. Vì thế, phép đánh giá này dựa vào nhận định ngữ nghĩa của LLM, không phải so khớp từ khóa hoặc tính toán cosine similarity giữa hai embedding.

Các kiểu dữ liệu cần nhớ:

| API | Vai trò |
| --- | --- |
| `EvaluationRequest(String userText, List<Document> dataList, String responseContent)` | Đóng gói một trường hợp cần chấm, kèm tài liệu RAG. |
| `new RelevancyEvaluator(ChatClient.builder(judgeModel))` | Tạo bộ đánh giá với `ChatModel` dùng để chấm. |
| `evaluator.evaluate(request)` | Thực hiện một lượt đánh giá. |
| `EvaluationResponse.isPass()` | Cho biết bộ đánh giá trả kết quả đạt hay không. |
| `EvaluationResponse.getScore()` | Điểm do implementation cung cấp. |

Trong implementation Spring AI 2.1 hiện hành, kết quả được hiểu như sau: nếu đầu ra của mô hình chấm sau khi loại khoảng trắng đầu/cuối bằng đúng `YES` (không phân biệt hoa thường), `isPass()` là `true` và `getScore()` bằng `1.0`; các trường hợp khác trả `false` và `0.0`. Đây là **điểm nhị phân**, không phải xác suất ước lượng 80% hay thang điểm liên tục. Implementation mặc định hiện không cung cấp phần giải thích có ích trong `getFeedback()`.

Lưu ý: mô hình chấm trả `"YES, because..."` hoặc JSON chứa `"YES"` cũng không khớp định dạng được mong đợi và có thể nhận `FAIL`. Khi tự tạo prompt, phải yêu cầu đầu ra **chính xác một từ**.

## 4. Ví dụ Java: đánh giá một câu trả lời với tài liệu có sẵn

Ví dụ sau minh họa cách tạo dữ liệu đánh giá độc lập với vector database. Giả sử dự án Spring Boot đã cấu hình một `ChatModel` và dependency Spring AI tương ứng.

~~~java
import java.util.List;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;

public final class AnswerRelevancyService {

    private final RelevancyEvaluator evaluator;

    public AnswerRelevancyService(ChatModel judgeModel) {
        this.evaluator = new RelevancyEvaluator(ChatClient.builder(judgeModel));
    }

    public EvaluationResponse evaluate(String question,
                                       List<Document> retrievedDocuments,
                                       String answer) {
        if (retrievedDocuments == null || retrievedDocuments.isEmpty()) {
            throw new IllegalArgumentException("Cần ngữ cảnh để đánh giá RAG");
        }

        EvaluationRequest request = new EvaluationRequest(
                question,
                retrievedDocuments,
                answer
        );

        return evaluator.evaluate(request);
    }
}
~~~

Cách gọi (ví dụ nằm trong một service hoặc test có sẵn `judgeModel`):

~~~java
AnswerRelevancyService service = new AnswerRelevancyService(judgeModel);

String question = "Đơn hàng trực tuyến được đổi trả trong bao lâu?";
List<Document> context = List.of(
    new Document("Đơn hàng trực tuyến được yêu cầu đổi trả " +
                 "trong vòng 14 ngày kể từ khi nhận hàng.")
);
String answer = "Khách hàng có thể yêu cầu đổi trả trong 14 ngày.";

EvaluationResponse result = service.evaluate(question, context, answer);

System.out.println("Pass = " + result.isPass());
System.out.println("Score = " + result.getScore());
~~~

**Cách đọc kết quả:** về mặt nghiệp vụ, trường hợp này được kỳ vọng là `PASS` vì phản hồi trả lời đúng khoảng thời gian và khớp tài liệu. Tuy nhiên, giá trị thực tế phụ thuộc mô hình chấm và phản hồi của nó; đoạn ví dụ chưa phải một phép chạy thực nghiệm.

Hàm trên chủ động chặn `retrievedDocuments` rỗng để người học không nhầm “không tìm được tài liệu” với “câu trả lời không liên quan”. Trong ứng dụng thực, hãy định nghĩa riêng quy trình xử lý khi bộ truy xuất không trả về tài liệu.

## 5. Đặt bước đánh giá vào luồng kiểm thử RAG

Trong RAG, điều quan trọng là chấm bằng **đúng các tài liệu thực sự được đưa vào luồng tạo câu trả lời**. Nếu lấy lại tài liệu bằng một truy vấn khác sau khi sinh đáp án, ngữ cảnh kiểm thử có thể không trùng ngữ cảnh mà mô hình đã thấy.

Spring AI cung cấp `RetrievalAugmentationAdvisor` và metadata chứa các tài liệu truy xuất. Mẫu tích hợp sau dựa trên API Spring AI 2.1; giả sử ứng dụng Spring Boot đã cấu hình một bean `ChatModel` và một bean `VectorStore` chứa dữ liệu kiểm thử:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;
import org.springframework.ai.rag.advisor.RetrievalAugmentationAdvisor;
import org.springframework.ai.rag.retrieval.search.VectorStoreDocumentRetriever;
import org.springframework.ai.vectorstore.VectorStore;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class RagRelevancyExample {

    @Autowired
    private ChatModel chatModel;

    @Autowired
    private VectorStore vectorStore;

    @Test
    void answerShouldMatchRetrievedContext() {
        String question = "Thời hạn đổi trả đơn hàng trực tuyến là bao lâu?";

        RetrievalAugmentationAdvisor ragAdvisor =
                RetrievalAugmentationAdvisor.builder()
                    .documentRetriever(
                        VectorStoreDocumentRetriever.builder()
                            .vectorStore(vectorStore)
                            .build()
                    )
                    .build();

        ChatResponse generated = ChatClient.builder(chatModel).build()
                .prompt(question)
                .advisors(ragAdvisor)
                .call()
                .chatResponse();

        assertThat(generated).isNotNull();

        EvaluationRequest request = new EvaluationRequest(
                question,
                generated.getMetadata().get(
                    RetrievalAugmentationAdvisor.DOCUMENT_CONTEXT
                ),
                generated.getResult().getOutput().getText()
        );

        RelevancyEvaluator evaluator =
                new RelevancyEvaluator(ChatClient.builder(chatModel));

        EvaluationResponse verdict = evaluator.evaluate(request);

        assertThat(verdict.isPass()).isTrue();
    }
}
~~~

Để chạy test trên, cần có dữ liệu mẫu về chính sách đổi trả trong vector store, các dependency kiểm thử và cấu hình truy cập mô hình. Ví dụ dùng cùng một `ChatModel` cho cả sinh câu trả lời và chấm; trong hệ thống thực tế có thể cấu hình một model chấm riêng để giảm thiên lệch. Assertion có thể không ổn định nếu judge model thay đổi hoặc tài liệu truy xuất không phù hợp.

Trong một dự án sử dụng `QuestionAnswerAdvisor`, hãy lấy tài liệu bằng metadata key tương ứng của advisor đó, thay vì mặc định tất cả advisor đều sử dụng `RetrievalAugmentationAdvisor.DOCUMENT_CONTEXT`. Hãy kiểm tra metadata có danh sách tài liệu thực trước khi gửi yêu cầu đánh giá.

## 6. Tùy chỉnh tiêu chí bằng PromptTemplate

Prompt mặc định thích hợp cho đánh giá chung. Với hệ thống có chính sách nghiệp vụ cụ thể, có thể định nghĩa tiêu chí chặt hơn: câu trả lời phải **đúng trọng tâm câu hỏi**, **không mâu thuẫn ngữ cảnh** và **không thêm khẳng định không có căn cứ**.

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.chat.prompt.PromptTemplate;

PromptTemplate rubric = new PromptTemplate("""
    Bạn là người đánh giá câu trả lời của trợ lý RAG.

    Câu hỏi: {query}
    Ngữ cảnh: {context}
    Câu trả lời: {response}

    Chỉ trả lời YES nếu câu trả lời giải quyết đúng câu hỏi,
    phù hợp với ngữ cảnh và không thêm kết luận thiếu căn cứ.
    Trong các trường hợp còn lại, chỉ trả lời NO.

    Đầu ra phải là đúng một từ: YES hoặc NO.
    """);

RelevancyEvaluator evaluator = RelevancyEvaluator.builder()
        .chatClientBuilder(ChatClient.builder(judgeModel))
        .promptTemplate(rubric)
        .build();
~~~

Ba placeholder **`{query}`, `{response}`, `{context}`** là bắt buộc đối với template tùy chỉnh của `RelevancyEvaluator`. Thay đổi rubric sẽ thay đổi định nghĩa “đạt”, do đó khi so sánh kết quả giữa các lần chạy phải ghi lại cả **phiên bản judge prompt**.

Rubric là chỉ dẫn cho mô hình chấm, không phải bộ kiểm chứng logic tuyệt đối. Để kiểm tra độ đúng của từng khẳng định dựa trên tài liệu nguồn, hãy kết hợp `FactCheckingEvaluator` hoặc phương pháp kiểm tra bằng quy tắc/dữ liệu tham chiếu phù hợp. Không đánh đồng `RelevancyEvaluator` với đánh giá factual correctness.

## 7. Dùng tập dữ liệu để so sánh các phiên bản prompt và pipeline

Một phép thử đơn lẻ chỉ cho biết một trường hợp. Để biết thay đổi `topK`, prompt, embedding hoặc model có cải thiện ứng dụng hay không, hãy thiết kế **tập đánh giá cố định** gồm nhiều dạng câu hỏi:

| Mã | Nhóm dữ liệu | Kỳ vọng cần quan sát |
| --- | --- | --- |
| R01 | Câu hỏi trực tiếp, tài liệu chứa đáp án rõ | Trả lời đúng ý và đúng dữ kiện. |
| R02 | Câu hỏi nhiều điều kiện, tài liệu nhiều đoạn | Không bỏ sót điều kiện quan trọng. |
| R03 | Có tài liệu gần nghĩa nhưng sai chủ đề | Phát hiện câu trả lời lạc đề. |
| R04 | Tài liệu mâu thuẫn/đã lỗi thời | Không tự chọn thông tin thiếu cơ sở; xử lý theo chính sách nguồn. |
| R05 | Không có dữ liệu liên quan | Nêu rõ thiếu căn cứ, không tự bịa đáp án. |
| R06 | Trả lời đúng một phần nhưng thêm chi tiết sai | Phát hiện khẳng định thiếu căn cứ bằng đánh giá bổ sung. |

Mỗi record nên lưu `caseId`, `question`, `expectedBehavior` hoặc nhãn chuyên gia, và dữ liệu nguồn cần thiết. Sau mỗi lần chạy, lưu thêm `answer`, `retrievedDocumentIds`, `modelVersion`, `promptVersion`, `retrieverConfig`, `judgeModelVersion`, `judgePromptVersion` và `isPass`. Không mặc định một nhãn `PASS` tự động đồng nghĩa với nhãn người đánh giá.

Ví dụ tính tỷ lệ đạt trên một tập kiểm thử:

~~~text
relevancy_pass_rate = số trường hợp isPass == true / tổng số trường hợp đánh giá hợp lệ
~~~

Nếu lần A có 84/100 câu đạt và lần B có 91/100 câu đạt trên **cùng tập dữ liệu và cùng rubric**, có thể nói tỷ lệ quan sát tăng từ 84% lên 91%. Nhưng vẫn cần xem những câu nào chuyển từ đạt sang trượt và ngược lại; tỷ lệ tăng không bảo đảm rằng factual accuracy hay trải nghiệm thực tế cũng tăng.

Để đo độ tin cậy của **bộ chấm**, hãy chọn một tập con có nhãn do con người xác lập và đối chiếu kết quả judge: tỉ lệ phát hiện đúng trường hợp không phù hợp, tỉ lệ loại nhầm câu trả lời tốt, cùng các ví dụ bất đồng. Nếu thay judge model hay judge prompt, coi đó là thay đổi hệ thống đo và hiệu chuẩn lại trước khi kết luận chất lượng sản phẩm tăng hay giảm.

## 8. Kết hợp relevance với metrics và traces để tìm nguyên nhân

`RelevancyEvaluator` tạo ra **tín hiệu đánh giá chất lượng**. Nó không tự thay thế hạ tầng quan sát ứng dụng. Trong module đánh giá và observability của Spring AI, nên kết hợp tín hiệu này với traces, độ trễ và token usage của cả luồng:

| Tín hiệu | Câu hỏi điều tra |
| --- | --- |
| Relevancy pass rate theo phiên bản | Chất lượng câu trả lời đổi như thế nào? |
| ID và số lượng tài liệu truy xuất; `topK`; ngưỡng similarity | Retriever có đưa đúng nguồn vào prompt không? |
| Prompt version và model version | Thay đổi prompt/model nào đi cùng suy giảm chất lượng? |
| Thời gian retrieval, generation và evaluation | Bước nào đang làm tăng latency? |
| Token usage và chi phí ước tính theo mô hình | Chi phí phát sinh từ trả lời và từ lượt LLM chấm là bao nhiêu? |
| Nhóm câu hỏi và nhãn chuyên gia | Nhóm use case nào phát sinh lỗi nhiều nhất? |

Có thể thực hiện phân tích theo thứ tự:

1. **Tìm case trượt** và tái hiện đúng `query`, tài liệu được truy xuất, `response`, judge prompt và phiên bản mô hình.
2. **Kiểm tra retrieval:** nếu tài liệu không trả lời câu hỏi, xem cách chia chunk, embedding, filter, `topK` và dữ liệu nguồn.
3. **Kiểm tra generation:** nếu context đã đúng nhưng câu trả lời lạc đề, xem prompt, giới hạn context, hướng dẫn trích dẫn và tham số mô hình.
4. **Kiểm tra judge:** nếu câu trả lời tốt bị đánh trượt, xem rubric, cách parse `YES`/`NO`, sự bất đồng ngôn ngữ và tính ổn định của judge.
5. **Kiểm tra vận hành:** đối chiếu thay đổi chất lượng với độ trễ, token usage và chi phí; lượt gọi judge cũng tiêu thụ tài nguyên.

Ví dụ: sau khi giảm `topK` từ 5 xuống 2, latency cải thiện nhưng relevancy pass rate của câu hỏi nhiều điều kiện giảm. Traces và danh sách tài liệu truy xuất có thể giúp xác định mô hình đang thiếu đoạn chứa điều kiện thứ hai. Khi đó, cần đánh giá lại chiến lược retrieval thay vì chỉ sửa câu prompt cuối cùng.

**Lưu ý bảo mật:** nội dung câu hỏi, tài liệu truy xuất và câu trả lời có thể chứa dữ liệu nhạy cảm. Khi lưu logs/traces hoặc gửi cho judge model, cần áp dụng chính sách phân quyền, che dữ liệu và lưu giữ tương ứng với hệ thống.

## 9. Những giới hạn cần nhớ

- **LLM-as-a-judge cũng có thể sai.** Kết quả có thể phụ thuộc mô hình chấm, cách diễn đạt rubric, ngôn ngữ, vị trí thông tin trong context và sự thay đổi của nhà cung cấp.
- **Không có “điểm relevance 0–100%” mặc định.** Trong implementation được mô tả ở trên, `getScore()` chỉ là 0 hoặc 1. Trung bình điểm trên tập là tỷ lệ các trường hợp được đánh đạt, không phải xác suất đúng của từng câu.
- **Phù hợp không đồng nghĩa với đúng sự thật.** Một câu trả lời có thể đúng chủ đề nhưng thêm dữ kiện không được nguồn hỗ trợ; cần kiểm tra factual correctness, grounding hoặc tiêu chí nghiệp vụ.
- **Không tự đánh giá chất lượng truy xuất.** Tài liệu sai hoặc thiếu có thể dẫn tới thất bại ở đầu ra. Cần đánh giá retrieval riêng và phân tích nguyên nhân theo từng bước.
- **Mô hình chấm tạo thêm chi phí và độ trễ.** Phù hợp để chạy offline, regression test hoặc lấy mẫu trên traffic; cần cân nhắc nếu dùng như bước chặn đồng bộ cho mọi request.
- **Ngữ cảnh là dữ liệu không tin cậy.** Tài liệu truy xuất có thể chứa chỉ dẫn gây nhiễu (prompt injection). Judge prompt, cách xử lý nội dung và kiểm soát nguồn dữ liệu cần được thiết kế phù hợp.
- **Trường hợp thiếu ngữ cảnh cần quy tắc rõ.** Nếu bài toán mong trợ lý từ chối trả lời khi không có nguồn, hãy đưa trường hợp này vào bộ dữ liệu với nhãn và rubric riêng.

## 10. Thực hành tự kiểm tra

1. Tạo 6 câu hỏi từ một bộ tài liệu nội bộ nhỏ; với mỗi câu, chuẩn bị một câu trả lời phù hợp và một câu trả lời lạc đề hoặc mâu thuẫn.
2. Chấm từng bộ ba `(query, context, response)` bằng `RelevancyEvaluator`. Lưu `isPass` và `getScore()`; nếu cần xem đầu ra `YES`/`NO` thô của judge để phân tích lỗi định dạng, phải thu thập nó qua lớp tích hợp hoặc công cụ quan sát thích hợp.
3. So sánh phán quyết với nhãn do bạn gán thủ công; giải thích từng bất đồng dựa trên ngữ cảnh và rubric.
4. Thay đổi một tham số RAG, ví dụ `topK` hoặc prompt trả lời. Chạy lại **cùng tập dữ liệu, cùng phiên bản judge và cùng rubric**, rồi phân tích các trường hợp bị đổi nhãn.
5. Với một câu trượt, truy theo chuỗi `query → retrieved documents → prompt → response → judge` để xác định lỗi retrieval, generation hay evaluation.

**Ghi nhớ:** Mục đích của `RelevancyEvaluator` là tạo phép đo thực dụng về mức độ câu trả lời **ăn khớp với yêu cầu của người dùng và ngữ cảnh đã cung cấp**. Giá trị của phép đo thể hiện rõ nhất khi chạy trên tập dữ liệu có kiểm soát và đối chiếu cùng thông tin quan sát về model, prompt, retrieval, token usage và latency.

## Tài liệu tham khảo

- [Spring AI Reference — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): giao diện `Evaluator`, `RelevancyEvaluator`, ví dụ tích hợp RAG và tùy chỉnh template.
- [Spring AI API — EvaluationRequest](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/evaluation/EvaluationRequest.html): các constructor và cấu trúc dữ liệu đánh giá.
- [Spring AI API — EvaluationResponse](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/evaluation/EvaluationResponse.html): `isPass()`, `getScore()` và các trường kết quả.
- [Spring AI — RelevancyEvaluator source](https://github.com/spring-projects/spring-ai/blob/main/spring-ai-client-chat/src/main/java/org/springframework/ai/chat/evaluation/RelevancyEvaluator.java): kiểm tra cơ chế đọc `YES`/`NO` và điểm nhị phân của implementation hiện hành.
