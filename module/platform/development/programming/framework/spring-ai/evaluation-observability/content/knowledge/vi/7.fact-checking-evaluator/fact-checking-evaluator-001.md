# FactCheckingEvaluator: Mục đích kiểm tra phát biểu có được tài liệu hỗ trợ

## 1. Vì sao cần kiểm tra phát biểu dựa trên tài liệu?

Trong ứng dụng hỏi đáp sử dụng Spring AI, mô hình ngôn ngữ có thể tạo ra một câu trả lời trôi chảy, đúng chủ đề nhưng chứa thông tin không có trong tài liệu mà hệ thống cung cấp. Đây là một dạng **hallucination** (thông tin do mô hình tự suy diễn hoặc bịa ra). Với ứng dụng RAG (Retrieval-Augmented Generation), yêu cầu quan trọng thường không chỉ là câu trả lời nghe có lý mà còn là **mọi phát biểu thực tế quan trọng phải được ngữ cảnh truy xuất hỗ trợ**.

Ví dụ, một hệ thống hỏi đáp chính sách nhận được tài liệu:

> Khách hàng gói Premium có thể yêu cầu hoàn tiền trong vòng 7 ngày kể từ ngày thanh toán. Chính sách không áp dụng cho gói Standard.

Từ tài liệu đó, hãy xét ba câu trả lời:

| Phát biểu của AI | Đánh giá dựa trên tài liệu | Giải thích |
| --- | --- | --- |
| “Gói Premium có thời hạn yêu cầu hoàn tiền là 7 ngày.” | **Được hỗ trợ** | Tài liệu nêu trực tiếp quyền yêu cầu hoàn tiền và thời hạn. |
| “Khách hàng Standard có thể yêu cầu hoàn tiền trong 7 ngày.” | **Bị tài liệu phủ định** | Tài liệu nói rõ chính sách không áp dụng cho Standard. |
| “Tiền sẽ được chuyển về tài khoản trong 24 giờ.” | **Không đủ bằng chứng** | Tài liệu không đề cập thời gian chuyển tiền thực tế. |

Phát biểu thứ ba có thể đúng ở một hệ thống thanh toán cụ thể, nhưng **không thể kết luận đúng từ nguồn chứng cứ hiện có**. Sự phân biệt này là trọng tâm của `FactCheckingEvaluator`.

Trong phạm vi module **SPRING_AI_EVALUATION_OBSERVABILITY**, chúng ta học cách đánh giá chất lượng ứng dụng Spring AI qua dữ liệu, tiêu chí relevance, fact checking và luồng RAG hoặc gọi công cụ; đồng thời quan sát metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm giữa các phiên bản prompt, model và pipeline. `FactCheckingEvaluator` giải quyết trực tiếp một câu hỏi trong chuỗi đánh giá đó: **“Phát biểu do AI tạo ra có căn cứ trong tài liệu đã cung cấp không?”**

## 2. `FactCheckingEvaluator` thực sự kiểm tra điều gì?

`FactCheckingEvaluator` là một triển khai của giao diện `Evaluator` trong Spring AI. Nó dùng một mô hình đánh giá (thường gọi là *judge*) để kiểm tra mối quan hệ giữa hai đầu vào:

- **Document / context / evidence:** văn bản tham chiếu mà hệ thống cho phép dùng làm căn cứ, chẳng hạn điều khoản sản phẩm, trích đoạn tài liệu nội bộ, kết quả truy xuất hoặc kết quả thực thi công cụ đã được ghi nhận.
- **Claim:** phát biểu cần xác minh, thường lấy từ câu trả lời của mô hình sinh nội dung.

Về mặt logic, evaluator cố gắng trả lời câu hỏi:

> Nếu chỉ biết nội dung tài liệu D, ta có đủ cơ sở để chấp nhận phát biểu C không?

Đây là bài toán *grounded factuality* hay *evidence-based support*. Nó có quan hệ gần với suy luận kéo theo (*entailment*): nếu tài liệu nêu “Hà Nội là thủ đô Việt Nam” thì phát biểu “Thủ đô của Việt Nam là Hà Nội” được hỗ trợ dù cách diễn đạt khác nhau.

Điều này **khác với xác minh sự thật tuyệt đối trên thế giới**. Một tài liệu có thể lỗi thời, không đáng tin hoặc sai. Nếu tài liệu sai mà mô hình diễn đạt đúng nội dung tài liệu, bài kiểm tra về độ bám nguồn vẫn có thể cho kết quả *pass*. Muốn đánh giá tính đúng đắn khách quan, cần bổ sung quy trình kiểm chứng nguồn gốc, phiên bản, thời điểm và mức độ tin cậy của chứng cứ.

### Ba trường hợp cần phân biệt

1. **Supported – được hỗ trợ:** chứng cứ nói trực tiếp hoặc cho phép suy ra phát biểu với mức chắc chắn phù hợp.
2. **Contradicted – mâu thuẫn:** chứng cứ khẳng định điều ngược lại với phát biểu.
3. **Insufficient evidence – không đủ thông tin:** chứng cứ không nói về phát biểu hoặc chỉ nói một phần nên chưa thể kết luận.

Về giao diện lập trình, kết quả thường được sử dụng dưới dạng `EvaluationResponse.isPass()` (boolean). Ba nhãn ở trên là **cách phân tích nghiệp vụ** để hiểu nguyên nhân; không nên mặc định `FactCheckingEvaluator` tự trả về ba nhãn riêng. Một kết quả `false` có thể do mâu thuẫn, thiếu bằng chứng hoặc lỗi đánh giá. Nếu hệ thống cần phân biệt từng nguyên nhân, hãy thiết kế bước phân loại/ghi chú bổ sung và kiểm tra tính ổn định của nó.

## 3. Vì sao kết quả này quan trọng đối với RAG?

Luồng RAG lấy dữ liệu từ kho tài liệu rồi đưa các đoạn phù hợp vào prompt trước khi mô hình sinh câu trả lời. Việc truy xuất đúng tài liệu **chưa bảo đảm** mô hình sẽ dùng tài liệu đúng cách: mô hình có thể thêm con số, mở rộng điều kiện, suy luận quá mức hoặc trộn dữ kiện từ những nguồn khác nhau.

~~~mermaid
flowchart TD
    A["Câu hỏi người dùng"] --> B["Retriever lấy các tài liệu liên quan"]
    B --> C["Context đưa vào mô hình sinh"]
    C --> D["Câu trả lời / các claim"]
    B --> E["Tập tài liệu làm bằng chứng"]
    D --> F["FactCheckingEvaluator"]
    E --> F
    F --> G{"Claim được tài liệu hỗ trợ?"}
    G -->|Có| H["Ghi nhận pass / tiếp tục xử lý"]
    G -->|Không hoặc chưa đủ căn cứ| I["Ghi nhận fail, xem lại nguồn và câu trả lời"]
~~~

Nhìn theo từng công đoạn, kết quả fact checking giúp định vị lỗi:

| Hiện tượng | Nguyên nhân cần xem xét | Hướng kiểm tra |
| --- | --- | --- |
| Tài liệu chứa đáp án nhưng câu trả lời thêm dữ kiện không có căn cứ | Prompt hoặc mô hình sinh chưa tuân thủ ngữ cảnh | So sánh claim với từng trích đoạn, xem lại hướng dẫn chỉ trả lời theo nguồn |
| Câu trả lời thiếu căn cứ vì retriever bỏ sót tài liệu cần thiết | Search, embedding, lọc metadata, chunking hoặc `topK` chưa phù hợp | Kiểm tra tài liệu được truy xuất so với tập tài liệu chuẩn |
| Hai tài liệu đưa ra chính sách khác nhau | Phiên bản hoặc ngày hiệu lực không nhất quán | Ưu tiên tài liệu có thẩm quyền, lọc theo ngày và ghi rõ xung đột |
| Câu trả lời đúng theo kiến thức phổ thông nhưng không có trong tài liệu | Nguồn truy xuất không đủ để làm bằng chứng | Bổ sung nguồn hoặc yêu cầu hệ thống trả lời “chưa đủ thông tin” |
| Phát biểu được hỗ trợ nhưng evaluator báo fail | Judge hiểu sai ngôn ngữ, văn cảnh hoặc định dạng đầu ra | Kiểm tra prompt đánh giá, mô hình judge và bộ dữ liệu hiệu chuẩn |

Ví dụ cụ thể: người dùng hỏi “Gói Standard có được hoàn tiền không?”. Retriever trả đúng chính sách ở phần 1, nhưng AI trả lời “Có, trong vòng 7 ngày”. Mức độ liên quan của câu trả lời với câu hỏi có thể rất cao; tuy nhiên phát biểu này trái với tài liệu, vì vậy nó cần bị đánh dấu không được hỗ trợ.

### Phân biệt với `RelevancyEvaluator`

| Tiêu chí | `RelevancyEvaluator` | `FactCheckingEvaluator` |
| --- | --- | --- |
| Câu hỏi chính | Câu trả lời có phù hợp với truy vấn và ngữ cảnh không? | Phát biểu trong câu trả lời có được chứng cứ hỗ trợ không? |
| Đầu vào trọng tâm | Câu hỏi, câu trả lời, ngữ cảnh | Claim và document/evidence |
| Ví dụ lỗi | Trả lời lạc sang chính sách vận chuyển khi được hỏi về hoàn tiền | Trả lời đúng chủ đề nhưng bịa mức phí hoặc điều kiện |
| Ý nghĩa | Kiểm tra tính liên quan | Kiểm tra độ bám nguồn |

Hai tiêu chí bổ sung cho nhau. Một câu trả lời **relevant vẫn có thể unsupported**, và một phát biểu đúng theo tài liệu vẫn có thể không giải quyết câu hỏi của người dùng.

## 4. Minh họa hoạt động bằng Spring AI

Spring AI định nghĩa giao diện cơ bản:

~~~java
@FunctionalInterface
public interface Evaluator {
    EvaluationResponse evaluate(EvaluationRequest evaluationRequest);
}
~~~

`EvaluationRequest` chứa thông tin yêu cầu đánh giá. Với API Spring AI 2.1.x, có thể tạo request từ `List<Document>` làm chứng cứ và `String` làm claim. Ví dụ sau sử dụng `ChatModel` đã được cấu hình sẵn, nên không phụ thuộc vào nhà cung cấp mô hình cụ thể:

~~~java
import java.util.List;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.FactCheckingEvaluator;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;

public class ClaimSupportChecker {

    private final FactCheckingEvaluator evaluator;

    public ClaimSupportChecker(ChatModel judgeModel) {
        this.evaluator = FactCheckingEvaluator
                .builder(ChatClient.builder(judgeModel))
                .build();
    }

    public boolean isSupported(List<Document> evidence, String claim) {
        EvaluationRequest request = new EvaluationRequest(evidence, claim);
        EvaluationResponse result = evaluator.evaluate(request);
        return result.isPass();
    }
}
~~~

Sử dụng:

~~~java
ClaimSupportChecker checker = new ClaimSupportChecker(judgeModel);

List<Document> evidence = List.of(new Document(
        "Khách hàng gói Premium có thể yêu cầu hoàn tiền trong vòng "
      + "7 ngày. Chính sách không áp dụng cho gói Standard."));

boolean supported = checker.isSupported(
        evidence,
        "Khách hàng gói Standard được yêu cầu hoàn tiền trong 7 ngày.");

// Kỳ vọng về nghiệp vụ: supported == false.
// Kết quả thực tế phụ thuộc judge model và cấu hình đánh giá.
~~~

Trong ví dụ trên, `judgeModel` là `ChatModel` dành cho đánh giá; có thể khác mô hình sinh câu trả lời. Khi đánh giá một ứng dụng thực tế, truyền **đúng các tài liệu mà bước sinh đã nhìn thấy** (hoặc bộ chứng cứ chuẩn được xác định rõ), không đưa vào một tài liệu mới mà mô hình chưa có cơ hội sử dụng rồi coi kết quả là lỗi sinh nội dung.

Spring AI có thể dùng mô hình chuyên cho kiểm tra độ bám nguồn, chẳng hạn Bespoke Minicheck. Với loại mô hình này, API hiện hành có hàm khởi tạo riêng:

~~~java
FactCheckingEvaluator checker = FactCheckingEvaluator
        .forBespokeMinicheck(ChatClient.builder(judgeModel));
~~~

Đây chỉ là lựa chọn judge: `FactCheckingEvaluator` không tự khởi chạy Ollama, tải model hoặc cấu hình endpoint. Những phần đó phải được chuẩn bị trong ứng dụng. Với các bản Spring AI cũ hơn, constructor, package và cách truyền `EvaluationRequest` có thể khác; cần đối chiếu Javadoc đúng phiên bản đang sử dụng.

### Prompt đánh giá có vai trò gì?

Evaluator trình bày document và claim cho judge. Ở các bản API mới, prompt mặc định cho judge tổng quát yêu cầu phản hồi dạng “yes” hoặc “no”. Về ý tưởng, prompt tương đương:

~~~text
Xác định phát biểu dưới đây có được tài liệu hỗ trợ không.
Chỉ trả lời yes nếu tài liệu hỗ trợ; nếu không, trả lời no.

Document: <nội dung chứng cứ>
Claim: <phát biểu cần kiểm tra>
~~~

Cơ chế này giúp việc đánh giá nhất quán hơn, nhưng kết quả vẫn phụ thuộc khả năng hiểu chứng cứ của judge. Tránh dùng một prompt mơ hồ như “Câu trả lời có đúng không?” vì nó dễ khiến judge trả lời dựa trên kiến thức ngoài tài liệu. Nếu tùy biến prompt, phải giữ đúng các biến mà phiên bản Spring AI yêu cầu, chẳng hạn `{document}` và `{claim}`, đồng thời kiểm tra thực nghiệm với các ví dụ pass/fail.

## 5. Khi nào nên tách câu trả lời thành nhiều claim?

Giả sử AI viết:

> Gói Premium cho phép hoàn tiền trong 7 ngày, hỗ trợ 24/7 và hoàn tiền ngay trong một giờ.

Trong khi tài liệu chỉ xác nhận chính sách 7 ngày. Nếu kiểm tra cả câu như một claim duy nhất, kết quả không cho biết **chính xác phần nào** được hỗ trợ. Để phân tích rõ hơn, có thể tách thành ba phát biểu nguyên tử:

1. “Premium cho phép yêu cầu hoàn tiền trong 7 ngày.”
2. “Premium có bộ phận hỗ trợ 24/7.”
3. “Premium hoàn tiền ngay trong một giờ.”

Đánh giá từng claim giúp chỉ ra phát biểu thứ nhất được hỗ trợ và hai phát biểu sau thiếu chứng cứ. Tuy nhiên, **tách claim không phải khả năng tự động được bảo đảm bởi `FactCheckingEvaluator`**; ứng dụng phải tự xây dựng bước tách nếu cần. Cần giữ nguyên chủ thể, thời hạn, điều kiện, lượng từ và phủ định khi tách, bởi chỉ thay “có thể yêu cầu” thành “luôn được hoàn tiền” đã làm thay đổi nội dung cần xác minh.

Một vài quy tắc hữu ích:

- Không bỏ qua các giới hạn như “tối đa”, “chỉ”, “trừ khi”, “từ ngày”, “đối với khách hàng mới”.
- Không kết luận một con số chính xác khi tài liệu chỉ cung cấp khoảng giá trị; ví dụ “từ 2 đến 4 ngày” không bảo đảm “chính xác 2 ngày”.
- Phân biệt dữ kiện được nêu trực tiếp với phép tính có thể suy ra; nếu cần tính toán số học, có thể tính bằng mã rồi kiểm tra đầu vào của phép tính.
- Gắn mỗi claim với mã tài liệu, phiên bản, ngày hiệu lực và đoạn trích đủ ngữ cảnh để điều tra kết quả fail.
- Với câu trả lời dài, dùng mức độ chi tiết hợp lý: quá ít claim dễ bỏ sót lỗi, quá nhiều claim làm chi phí và độ trễ tăng.

## 6. Thiết kế bộ dữ liệu để đánh giá chất lượng fact checking

Để tin được kết quả, hãy tạo một tập đánh giá gồm bộ ba `(document, claim, nhãn chuẩn)`. Ít nhất nên có các trường hợp sau:

| Tài liệu | Claim | Nhãn chuẩn |
| --- | --- | --- |
| “Dịch vụ A hoạt động từ 08:00 đến 18:00 các ngày thứ Hai đến thứ Sáu.” | “Thứ Ba dịch vụ A mở cửa lúc 08:00.” | Supported |
| Cùng tài liệu trên | “Dịch vụ A mở cửa vào Chủ nhật.” | Insufficient evidence (không thấy lịch Chủ nhật) |
| “Dịch vụ B chỉ dành cho khách hàng từ 18 tuổi.” | “Người 16 tuổi đủ điều kiện sử dụng B.” | Contradicted |
| “Phí duy trì là 50.000 đồng mỗi tháng.” | “Phí duy trì là 600.000 đồng cho 12 tháng, nếu không đổi mức phí.” | Supported nếu cho phép tính toán và nêu rõ giả định |
| “Từ ngày 01/07/2026, chính sách C thay thế phiên bản cũ.” | “Chính sách cũ vẫn còn hiệu lực sau ngày 01/07/2026.” | Contradicted theo nguồn đã cho |

Đây là **bộ ví dụ minh họa**, không phải kết quả của một lần chạy mô hình. Khi xây dựng bộ kiểm thử thật, con người cần kiểm tra lại nhãn chuẩn, tính xác thực của nguồn và các trường hợp suy luận không chắc chắn. Nên giữ cả ví dụ dễ và khó: diễn đạt lại, phủ định kép, con số gần giống nhau, tài liệu nhiễu, nhiều đoạn cần kết hợp và nội dung thiếu dữ kiện.

Một phép kiểm thử hồi quy đơn giản là lưu `document`, `claim`, `expectedSupport`, sau đó so sánh nhãn chuẩn với `isPass()` của evaluator. Với dữ liệu ba nhãn, cần xác định rõ cách quy đổi về pass/fail: thường chỉ **Supported** là pass; **Contradicted** và **Insufficient evidence** đều là fail đối với yêu cầu phải có chứng cứ.

Các số đo quan trọng:

- **Support pass rate:** tỷ lệ các claim được evaluator đánh giá là có bằng chứng; chỉ số này giúp theo dõi xu hướng, nhưng **không tự chứng minh câu trả lời đúng** vì judge có thể mắc lỗi.
- **Recall phát hiện claim thiếu hỗ trợ:** trong các claim thực sự unsupported theo nhãn chuẩn, bao nhiêu claim bị evaluator đánh dấu fail? Đây là thước đo quan trọng khi ưu tiên giảm thông tin bịa.
- **False alarm rate:** trong các claim thực sự supported, bao nhiêu claim lại bị đánh dấu fail?
- **Độ trễ và chi phí mỗi lần đánh giá:** số lần gọi judge, thời gian xử lý, token đầu vào/đầu ra và chi phí, nhất là khi tách một câu trả lời thành nhiều claim.

Ký hiệu TP là claim thiếu hỗ trợ được phát hiện đúng, FN là claim thiếu hỗ trợ nhưng bị bỏ sót, FP là claim có hỗ trợ nhưng bị cảnh báo sai, TN là claim có hỗ trợ được nhận diện đúng:

~~~text
Recall phát hiện unsupported = TP / (TP + FN)
False alarm rate          = FP / (FP + TN)
~~~

Khi so sánh các phiên bản, giữ cố định bộ dữ liệu và ghi lại phiên bản judge. Nếu thay đổi đồng thời prompt sinh, retriever, kho tài liệu và judge, việc xác định nguyên nhân thay đổi tỷ lệ pass sẽ khó hơn nhiều.

## 7. Kết nối kết quả với metrics và traces

Trong hệ thống vận hành, fact checking hữu ích nhất khi kết quả có thể được gắn với dữ liệu quan sát của từng yêu cầu:

~~~mermaid
flowchart LR
    R["RAG retrieval"] --> G["Generation"]
    G --> J["Fact-check evaluation"]
    J --> M["Metrics: pass/fail, latency, cost"]
    J --> T["Trace: phiên bản và đoạn xử lý"]
    M --> D["Dashboard / so sánh phiên bản"]
    T --> D
~~~

Một bản ghi đánh giá nên có các trường có ích cho truy vết, ví dụ: `requestId` hoặc `traceId`, `promptVersion`, `modelVersion`, `retrieverVersion`, `documentVersion`, `judgeModel`, `claimId`, `passed`, `evaluationLatencyMs`. Với bằng chứng văn bản, có thể lưu mã tài liệu và đoạn trích đã được kiểm soát quyền truy cập thay vì ghi toàn bộ nội dung nhạy cảm vào log.

Một số metric có thể **tự định nghĩa** cho dashboard là `factcheck_claims_total{result=pass|fail}`, `factcheck_duration_seconds` và `factcheck_judge_calls_total`. Đây là gợi ý thiết kế metric của ứng dụng, **không phải tên metric mặc định được Spring AI cam kết cung cấp**.

Khi thấy tỷ lệ fail tăng sau khi thay đổi prompt hoặc mô hình, dùng trace để đối chiếu ba thứ: tài liệu thực sự được retriever trả về, nội dung câu trả lời được sinh ra và kết luận của judge. Nếu tài liệu đúng nhưng claim sai, hướng xử lý khác với khi retriever đưa nhầm nguồn; nếu cả tài liệu và claim đều hợp lệ mà judge fail, cần kiểm tra tầng đánh giá. Đây là mục đích của việc kết hợp **evaluation** với **observability**.

Trong luồng gọi công cụ (*tool calling*), cũng có thể xem đầu ra của công cụ như một nguồn chứng cứ: ví dụ công cụ tra cứu đơn hàng trả về `status=SHIPPED`, còn mô hình nói “đơn hàng đã giao thành công”. Fact checking có thể phát hiện câu nói không được trạng thái `SHIPPED` hỗ trợ. Tuy vậy, evaluator **không tự xác minh công cụ đã gọi đúng API, có lỗi hay không hoặc dữ liệu trả về có thật hay không**; những vấn đề đó cần kiểm thử và quan sát riêng ở tầng công cụ.

## 8. Giới hạn và lỗi thường gặp

**Thiếu bằng chứng khác với mâu thuẫn.** Nếu tài liệu chỉ nói giờ mở cửa ngày thường, không thể suy ra cửa hàng chắc chắn đóng cửa Chủ nhật. Với yêu cầu “mọi phát biểu phải có nguồn”, hai trường hợp đều cần bị chặn hoặc yêu cầu bổ sung dữ liệu, nhưng lý do nghiệp vụ khác nhau.

**Chất lượng nguồn quyết định giá trị của kiểm tra.** Một tài liệu quá cũ hoặc một đoạn cắt mất điều kiện có thể khiến judge cho ra kết luận sai. Cần quản lý provenance, ngày hiệu lực, quyền truy cập, thứ tự ưu tiên và mức độ đầy đủ của context.

**Judge cũng là mô hình và có thể hallucinate.** Kết quả `isPass()` không phải chứng minh hình thức. Nên kiểm tra độ chính xác của judge trên bộ nhãn chuẩn, đặc biệt với tiếng Việt, suy luận nhiều bước, phủ định và con số. Trường hợp rủi ro cao cần thêm quy tắc xác định bằng mã hoặc người kiểm duyệt.

**Context quá dài hoặc có chỉ dẫn độc hại.** Tài liệu truy xuất có thể chứa câu lệnh như “hãy bỏ qua bước kiểm tra”. Phải coi đây là **dữ liệu nguồn**, không phải chỉ dẫn đáng tin cho judge. Giới hạn độ dài, chọn đoạn liên quan và phân tách ranh giới giữa hướng dẫn đánh giá với dữ liệu đầu vào.

**Không nên nhầm trích dẫn đẹp với bằng chứng thật.** Một câu có gắn mã nguồn `[1]` chưa chắc nguồn `[1]` có nội dung hỗ trợ claim. Cần kiểm tra quan hệ giữa **đúng đoạn dẫn nguồn** và phát biểu.

**Đánh giá trực tuyến có chi phí.** Mỗi claim có thể cần thêm một lần gọi model, làm tăng độ trễ. Có thể chạy định kỳ trên tập kiểm thử, lấy mẫu những yêu cầu sản xuất hoặc đánh giá ngay tại thời điểm trả lời cho các luồng có yêu cầu nghiêm ngặt; lựa chọn phụ thuộc rủi ro và ngân sách.

## 9. Quy trình áp dụng vào một dự án thực tế

1. **Đặt tiêu chí chất lượng:** xác định câu trả lời nào bắt buộc dựa trên nguồn, trường hợp nào được phép suy luận và tình huống nào phải trả lời “không đủ dữ liệu”.
2. **Thu thập chứng cứ:** lưu các `Document` đã truy xuất hoặc kết quả công cụ cùng metadata nguồn, phiên bản và thời điểm.
3. **Chọn đơn vị kiểm tra:** một phát biểu ngắn hoặc các claim nguyên tử được tách từ câu trả lời dài.
4. **Chạy `FactCheckingEvaluator`:** cung cấp chứng cứ và claim cho judge được cấu hình phù hợp; lưu `isPass()` cùng dữ liệu cần truy vết.
5. **Phân tích fail:** tách lỗi retrieval, lỗi sinh nội dung, nguồn cũ/xung đột và lỗi judge; không mặc định lỗi nằm ở mô hình sinh.
6. **Theo dõi qua phiên bản:** chạy lại một tập dữ liệu cố định sau khi đổi prompt, model, chiến lược truy xuất hoặc pipeline, rồi so sánh tỷ lệ phát hiện lỗi, cảnh báo sai, chi phí và độ trễ.

**Tình huống vận dụng:** doanh nghiệp dùng RAG trả lời về chính sách hoàn tiền. Sau khi nâng cấp prompt, tỷ lệ câu trả lời có trích dẫn tăng nhưng tỷ lệ claim được tài liệu hỗ trợ giảm. Nhờ lưu `traceId`, tập tài liệu truy xuất và kết quả fact checking theo phiên bản, nhóm kỹ thuật nhận thấy mô hình thường suy rộng quy định dành cho Premium sang Standard. Họ sửa hướng dẫn sinh câu trả lời và bổ sung các test claim đối nghịch để ngăn lỗi tái diễn. Đây là cách `FactCheckingEvaluator` chuyển một vấn đề “AI đôi lúc trả lời sai” thành dữ liệu có thể kiểm chứng và cải thiện.

## 10. Tự kiểm tra mức độ hiểu bài

- Một phát biểu có thể đúng ngoài đời nhưng bị đánh giá không được hỗ trợ bởi tài liệu hay không? Vì sao?
- Nếu evaluator trả về `false`, làm sao phân biệt nguồn thiếu thông tin với nguồn mâu thuẫn và judge đánh giá sai?
- Vì sao một câu trả lời có thể vượt qua kiểm tra relevance nhưng không vượt qua fact checking?
- Khi tỷ lệ fact-check fail tăng sau khi cập nhật hệ thống RAG, cần xem những phần nào của trace trước khi quy trách nhiệm cho mô hình?
- Nếu tài liệu ghi “hỗ trợ trong vòng 2–4 ngày” mà AI khẳng định “luôn xử lý trong 2 ngày”, phát biểu này đã được tài liệu bảo đảm chưa?

## Tài liệu tham khảo

- [Spring AI — Evaluation Testing / FactCheckingEvaluator](https://docs.spring.io/spring-ai/reference/api/testing.html): mục đích của fact checking và giao diện evaluator.
- [Spring AI — FactCheckingEvaluator Java API 2.1.0](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/chat/evaluation/FactCheckingEvaluator.html): phương thức `evaluate`, builder và cấu hình Bespoke Minicheck.
- [Spring AI — EvaluationRequest Java API 2.1.0](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/evaluation/EvaluationRequest.html): các constructor nhận tài liệu và câu trả lời.
- [Spring AI — Evaluators (tài liệu phát triển 2.1.x)](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/evaluation/evaluators.html): cách truyền `Document` làm evidence, prompt và ví dụ với Minicheck. Khi sử dụng, đối chiếu phiên bản thư viện thực tế.
