# Đối chiếu API evaluator và khả năng hỗ trợ theo phiên bản Spring AI

Một nhóm phát triển nâng Spring AI từ 1.0.x lên 1.1.x rồi 2.x. Bộ kiểm thử RAG trước đây dùng `RelevancyEvaluator` và `FactCheckingEvaluator`. Sau khi nâng cấp, code có thể không biên dịch vì builder hoặc kiểu dữ liệu trong `EvaluationRequest` khác với ví dụ mà nhóm đang tham khảo. Một lỗi khác tinh vi hơn: code vẫn chạy nhưng evaluator dùng một judge model khác, prompt khác hoặc context khác, khiến điểm đánh giá không còn so sánh được với bản phát hành trước.

Bài này giúp bạn **đối chiếu API evaluator và khả năng hỗ trợ theo phiên bản Spring AI**. Ta sẽ xác định package và hợp đồng cốt lõi, so sánh các dòng 1.0.x, 1.1.x, 2.0.x và 2.1.x, chọn constructor/builder tương ứng, xử lý khác biệt giữa tài liệu và Javadocs, rồi xây quy trình nâng cấp có kiểm chứng.

Bài thuộc chương **Nâng cấp** của mô-đun **SPRING_AI_EVALUATION_OBSERVABILITY**. Mô-đun học đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện suy giảm qua từng phiên bản prompt, model và pipeline. Vì vậy, việc nâng evaluator phải bảo toàn cả **khả năng biên dịch** lẫn **tính so sánh của kết quả đánh giá**.

> **Nguyên tắc nâng cấp:** kiểm tra chữ ký trong Javadocs đúng phiên bản dependency đã resolve, sau đó compile và chạy fixture. Không lấy ví dụ từ nhánh snapshot hoặc milestone làm hợp đồng cho bản stable.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Xác định package của evaluator interface, request/response và các evaluator có sẵn.
2. Phân biệt vai trò của `Evaluator`, `EvaluationRequest`, `EvaluationResponse`, `RelevancyEvaluator` và `FactCheckingEvaluator`.
3. Đối chiếu các khả năng chính giữa Spring AI 1.0.x, 1.1.x, 2.0.x và 2.1.x.
4. Chọn constructor hoặc builder phù hợp với phiên bản đang dùng.
5. Hiểu thay đổi kiểu context từ `Content` ở một số milestone sớm sang `Document` trong các Javadocs stable được đối chiếu.
6. Nhận diện điểm không đồng nhất giữa trang hướng dẫn và Javadocs.
7. Cấu hình evaluator bằng một judge model riêng với prompt có thể kiểm soát.
8. Viết test RAG/fact checking có dữ liệu đầu vào và kết quả kỳ vọng rõ ràng.
9. Nâng cấp mà không trộn các artifact Spring AI thuộc nhiều dòng phiên bản.
10. Phân biệt thay đổi API với thay đổi chất lượng do model, prompt, context hoặc dữ liệu đánh giá.

## 2. Bản đồ API evaluator

Spring AI đặt API evaluator trong hai package:

| Package | Thành phần | Vai trò |
|---|---|---|
| `org.springframework.ai.evaluation` | `Evaluator` | Hợp đồng chung để đánh giá một request |
| `org.springframework.ai.evaluation` | `EvaluationRequest` | Đầu vào gồm câu hỏi, context và response |
| `org.springframework.ai.evaluation` | `EvaluationResponse` | Kết quả đánh giá: pass, score, feedback, metadata |
| `org.springframework.ai.chat.evaluation` | `RelevancyEvaluator` | Đánh giá response có liên quan tới câu hỏi và context không |
| `org.springframework.ai.chat.evaluation` | `FactCheckingEvaluator` | Kiểm tra claim có được context hỗ trợ không |

Hai package có ranh giới có chủ ý: kiểu dữ liệu và hợp đồng đánh giá nằm trong `org.springframework.ai.evaluation`; các evaluator dựa trên `ChatClient` nằm trong `org.springframework.ai.chat.evaluation`.

### 2.1. Hợp đồng Evaluator

Interface cốt lõi có dạng:

~~~java
@FunctionalInterface
public interface Evaluator {
    EvaluationResponse evaluate(EvaluationRequest evaluationRequest);
}
~~~

`Evaluator` là functional interface. Vì vậy, một implementation tùy chỉnh có thể dùng class hoặc lambda nếu chỉ cần triển khai một phương thức trừu tượng. Phương thức `evaluate` trả về `EvaluationResponse` đồng bộ; API này không tự cung cấp một test suite, batch runner, threshold policy hay cơ chế lưu kết quả theo dataset.

### 2.2. EvaluationRequest

Trong các Javadocs stable được đối chiếu, request có ba dữ liệu:

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `userText` | `String` | Nội dung người dùng hỏi |
| `dataList` | `List<Document>` | Context hỗ trợ, thường là tài liệu truy xuất từ RAG |
| `responseContent` | `String` | Nội dung do model sinh cần được đánh giá |

Các constructor được công bố trong Javadocs:

~~~java
new EvaluationRequest(userText, dataList, responseContent);
new EvaluationRequest(dataList, responseContent);
new EvaluationRequest(userText, responseContent);
~~~

Dùng constructor có `userText` và `dataList` khi đánh giá relevance của RAG. Với fact checking một claim trên một tài liệu, có thể dùng constructor tương ứng với context và claim theo API phiên bản đang dùng.

### 2.3. EvaluationResponse

`EvaluationResponse` cung cấp các thông tin kết quả quan trọng:

- `isPass()`: criterion có đạt hay không;
- `getScore()`: điểm số nếu evaluator cung cấp;
- `getFeedback()`: phản hồi giải thích;
- `getMetadata()`: metadata bổ sung.

Không giả định mọi evaluator đều tạo score có cùng thang đo. Ví dụ, `RelevancyEvaluator` có thể ánh xạ câu trả lời YES/NO thành điểm nhị phân; evaluator tự viết có thể dùng thang điểm khác. Hãy lưu evaluator ID, version và rubric cùng kết quả.

## 3. Ma trận hỗ trợ theo phiên bản

Bảng dưới đây tóm tắt những API được xác nhận trong tài liệu/Javadocs chính thức đã đối chiếu. Bảng mô tả **khả năng có mặt và hình dạng API**, không thay thế việc kiểm tra dependency thực tế của dự án.

| Dòng phiên bản | Evaluator API | RelevancyEvaluator | FactCheckingEvaluator | Kiểu context trong Javadocs stable được kiểm tra |
|---|---|---|---|---|
| **1.0.x** | Có từ dòng 1.0 | Constructor và builder; có thể tùy chỉnh prompt qua builder | Constructor; overload nhận prompt; helper cho Bespoke Minicheck | `List<Document>` trong Javadocs 1.0.9 |
| **1.1.x** | Tiếp tục hỗ trợ | Constructor và builder; builder có `chatClientBuilder` và `promptTemplate` | Có builder với `chatClientBuilder` và `evaluationPrompt` | `List<Document>` trong Javadocs 1.1.x |
| **2.0.x** | Tiếp tục hỗ trợ | Package và hợp đồng evaluate giữ nguyên trong Javadocs 2.0.1 | Builder và helper Bespoke Minicheck vẫn có | `List<Document>` trong Javadocs 2.0.1 |
| **2.1.x** | Tiếp tục hỗ trợ ở stable 2.1.0 | Vẫn có constructor, builder và evaluate | Vẫn có builder, prompt và helper chuyên biệt | Javadocs 2.1.x cho thấy `Document`; trang hướng dẫn stable có ví dụ `Content` cần được đối chiếu |

### 3.1. Dòng 1.0.x

Spring AI 1.0.x đã có `Evaluator`, `EvaluationRequest`, `EvaluationResponse`, `RelevancyEvaluator` và `FactCheckingEvaluator`.

Các cách khởi tạo cơ bản:

~~~java
var relevancyEvaluator =
        new RelevancyEvaluator(ChatClient.builder(judgeChatModel));

var factCheckingEvaluator =
        new FactCheckingEvaluator(ChatClient.builder(judgeChatModel));
~~~

`RelevancyEvaluator` có constructor nhận `ChatClient.Builder` và static `builder()`. `FactCheckingEvaluator` ở Javadocs 1.0.0 có constructor nhận `ChatClient.Builder`, overload nhận thêm evaluation prompt và helper `forBespokeMinicheck`.

Ở dòng này, nếu code cần prompt fact checking riêng, có thể dùng overload constructor được Javadocs phiên bản đó công bố:

~~~java
var evaluator = new FactCheckingEvaluator(
        ChatClient.builder(judgeChatModel),
        "Document: {document}\nClaim: {claim}"
);
~~~

Đừng gọi `FactCheckingEvaluator.builder(...)` trong code 1.0.x chỉ vì đã thấy ví dụ builder ở tài liệu 1.1.x hoặc 2.x. Builder của FactCheckingEvaluator được xác nhận trong Javadocs từ 1.1.0.

### 3.2. Dòng 1.1.x

Dòng 1.1.x giữ package split và hợp đồng `Evaluator.evaluate(EvaluationRequest)`. Builder của `FactCheckingEvaluator` đã xuất hiện, cho phép cấu hình ChatClient và evaluation prompt bằng chuỗi lời gọi rõ ràng:

~~~java
var factCheckingEvaluator = FactCheckingEvaluator
        .builder(ChatClient.builder(judgeChatModel))
        .evaluationPrompt("Document: {document}\nClaim: {claim}")
        .build();
~~~

`RelevancyEvaluator.Builder` có `chatClientBuilder(...)` và `promptTemplate(...)`:

~~~java
var relevancyEvaluator = RelevancyEvaluator.builder()
        .chatClientBuilder(ChatClient.builder(judgeChatModel))
        .promptTemplate(customRelevancyPrompt)
        .build();
~~~

Builder giúp cấu hình rõ ràng khi có prompt riêng. Với `RelevancyEvaluator`, constructor vẫn là cách khởi tạo ngắn gọn; với `FactCheckingEvaluator` ở 1.1.x trở lên, dùng builder public.

### 3.3. Dòng 2.0.x

Javadocs 2.0.1 tiếp tục thể hiện:

- `Evaluator` trong `org.springframework.ai.evaluation`;
- `EvaluationRequest` và `EvaluationResponse` trong cùng package;
- Hai implementation trong `org.springframework.ai.chat.evaluation`;
- `RelevancyEvaluator(ChatClient.Builder)` và `RelevancyEvaluator.builder()`;
- `FactCheckingEvaluator.Builder` với `chatClientBuilder` và `evaluationPrompt`;
- `FactCheckingEvaluator.forBespokeMinicheck(...)`.

Không thấy một thay đổi riêng của evaluator được nêu trong phần migration 2.0 đã đối chiếu. Tuy nhiên, Spring AI 2.0 là một major line gắn với nền tảng Spring Boot 4.1.x theo ma trận tương thích của dự án. Khi nâng từ 1.1.x, phải xử lý cả nâng cấp nền tảng, Java/Spring dependencies và các breaking changes khác của ứng dụng; việc evaluator API còn tương thích không có nghĩa toàn bộ ứng dụng chỉ cần đổi version.

### 3.4. Dòng 2.1.x và trạng thái hiện tại

Tại thời điểm **27-11-2026**, trang releases của dự án đánh dấu Spring AI **2.1.0** là bản stable mới nhất. Trang này cũng liệt kê các nhánh bảo trì 2.0.3, 1.1.8 và 1.0.9.

Trong dòng 2.1.x, Javadocs vẫn có các evaluator và builder nêu trên. Ma trận Spring AI hiện tại ghép 2.1.x với Spring Boot 4.2.x. Nếu dự án vẫn ở Spring Boot 3.5.x, dòng 1.1.x là nhánh tương thích được liệt kê; không nên nâng riêng một artifact evaluator sang 2.1.x để thử nghiệm trong ứng dụng 1.1.x.

**Lưu ý về tài liệu context:** trang hướng dẫn Evaluation Testing của reference stable 2.1.0 hiển thị `List<Content>` trong phần mô tả `EvaluationRequest`, trong khi Javadocs của các bản stable đã đối chiếu như 1.0.9 và 2.0.1, cùng Javadocs 2.1.x, hiển thị `List<Document>`. Đây là điểm không đồng nhất giữa trang hướng dẫn và API reference. Khi biên dịch, hãy ưu tiên Javadocs của đúng artifact/version đã resolve và xác nhận bằng compiler; đừng đổi code production chỉ dựa vào một đoạn ví dụ có thể cũ.

## 4. Chọn đúng evaluator cho đúng câu hỏi

Hai evaluator có mục tiêu khác nhau. Không dùng chúng thay thế lẫn nhau chỉ vì cả hai đều trả `EvaluationResponse`.

| Tiêu chí | RelevancyEvaluator | FactCheckingEvaluator |
|---|---|---|
| Câu hỏi | Response có liên quan và phù hợp với query/context không? | Claim có được document/context hỗ trợ không? |
| Đầu vào quan trọng | Query, response, retrieved context | Claim/response và supporting document |
| Prompt mặc định | Yêu cầu judge trả YES hoặc NO về relevance | Đặt document và claim vào prompt fact checking |
| Trường hợp phù hợp | Đánh giá chất lượng RAG tổng thể ở mức relevance | Kiểm tra tính đúng đắn của phát biểu dựa trên evidence |
| Giới hạn | Có thể đánh giá relevance nhưng không chứng minh mọi claim đúng | Cần evidence; không phải bài kiểm tra kiến thức đóng không có tài liệu |

### 4.1. RelevancyEvaluator

`RelevancyEvaluator` gửi query, response và context vào judge model. Prompt mặc định yêu cầu trả YES nếu response phù hợp với query và context, ngược lại trả NO.

Điều này hữu ích để phát hiện:

- Trả lời lạc đề;
- Không sử dụng context đã truy xuất;
- Trả lời không phù hợp với câu hỏi;
- Nội dung response không được hỗ trợ bởi context ở mức tổng thể.

Nó không tự đo retrieval precision/recall, không kiểm tra từng claim riêng biệt và không đảm bảo response không chứa chi tiết sai nếu phần còn lại vẫn có vẻ liên quan.

### 4.2. FactCheckingEvaluator

`FactCheckingEvaluator` đánh giá claim có được context hỗ trợ không. Javadocs mô tả evaluator này dành cho grounded factuality: claim được đối chiếu với document được cung cấp.

Dùng nó khi cần kiểm tra:

- Một phát biểu có được tài liệu hỗ trợ không;
- Response có thêm chi tiết không xuất hiện trong evidence không;
- Một claim quan trọng có mâu thuẫn với context không;
- Kết quả fact checking có pass/fail theo rubric đã xác định.

Không dùng nó như một công cụ hỏi kiến thức tổng quát khi không cung cấp tài liệu tham chiếu. Nếu response dài và chứa nhiều mệnh đề, hãy tách thành atomic claims rồi đánh giá từng claim hoặc thiết kế rubric riêng.

## 5. Dependency và cách cấu hình judge model

Các evaluator có sẵn dùng `ChatClient.Builder`. Vì vậy, ứng dụng cần có Spring AI Chat Client API và một `ChatModel` làm judge. Judge model có thể khác model tạo câu trả lời.

### 5.1. Quản lý version bằng BOM

Ví dụ Maven rút gọn:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.ai</groupId>
            <artifactId>spring-ai-bom</artifactId>
            <version>${spring-ai.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-client-chat</artifactId>
    </dependency>

    <!-- Chọn starter của provider dùng làm judge model. -->
    <dependency>
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-starter-model-openai</artifactId>
    </dependency>
</dependencies>
~~~

Đây là ví dụ cho Maven và OpenAI provider. Nếu dùng Ollama, Anthropic, Bedrock hoặc provider khác, thay starter bằng artifact tương ứng. Không khai báo version riêng cho từng Spring AI module khi đã dùng BOM; nếu không, có thể resolve các module khác dòng.

`spring-ai-client-chat` chứa ChatClient và evaluator implementations. Provider starter cung cấp cấu hình model để `ChatClient.Builder` có thể gọi judge. Nếu dự án đã có các dependency này qua một starter khác, tránh khai báo trùng không cần thiết.

### 5.2. Tách judge model khỏi generation model

Ví dụ cấu hình bean dưới đây dùng API FactCheckingEvaluator từ 1.1.x trở lên. Với 1.0.0, thay phần tạo bean FactCheckingEvaluator bằng constructor public của dòng đó.

~~~java
@Configuration
class EvaluationConfiguration {

    @Bean
    RelevancyEvaluator relevancyEvaluator(ChatModel judgeChatModel) {
        return new RelevancyEvaluator(
                ChatClient.builder(judgeChatModel));
    }

    @Bean
    FactCheckingEvaluator factCheckingEvaluator(
            ChatModel judgeChatModel) {
        return FactCheckingEvaluator.builder(
                ChatClient.builder(judgeChatModel))
                .build();
    }
}
~~~

Ví dụ dùng cùng một bean để minh họa. Trong production, có thể tạo model riêng cho evaluator với cấu hình nhiệt độ thấp, giới hạn output và chi phí phù hợp. Không nhất thiết dùng cùng model/provider với model tạo response.

### 5.3. Chú ý quan hệ giữa ChatClient và ChatModel

Các evaluator dùng `ChatClient.Builder` làm đầu vào cấu hình, nhưng public factory/constructor khác nhau theo phiên bản. Hãy tạo builder từ judge model:

~~~java
ChatClient.Builder judgeClientBuilder =
        ChatClient.builder(judgeChatModel);
~~~

`RelevancyEvaluator` nhận builder qua constructor hoặc builder riêng. `FactCheckingEvaluator` dùng constructor public ở 1.0.0 và static builder từ 1.1.x trở lên. Đừng truyền `ChatClient` đã build nếu chữ ký yêu cầu `ChatClient.Builder`.

## 6. Ví dụ sử dụng EvaluationRequest trong RAG

Ví dụ sau giả định retrieval pipeline đã trả về danh sách `Document` và generation model đã tạo response. Tập context dùng cho evaluator cần chính là evidence mà pipeline đã cung cấp cho model, không phải một truy vấn retrieval mới có thể trả ra tài liệu khác.

~~~java
import java.util.List;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;

public class RagEvaluationExample {

    public EvaluationResponse evaluate(
            ChatModel judgeChatModel,
            String question,
            List<Document> retrievedDocuments,
            String generatedAnswer) {

        var evaluator = new RelevancyEvaluator(
                ChatClient.builder(judgeChatModel));

        var request = new EvaluationRequest(
                question,
                retrievedDocuments,
                generatedAnswer
        );

        return evaluator.evaluate(request);
    }
}
~~~

Sử dụng kết quả:

~~~java
EvaluationResponse result = evaluate(
        judgeChatModel,
        question,
        retrievedDocuments,
        generatedAnswer
);

if (!result.isPass()) {
    throw new AssertionError(
            "RAG response failed relevance evaluation: "
                    + result.getFeedback());
}
~~~

Trong test thực tế, nên lưu feedback, score nếu có và metadata cùng với sample ID. Không chỉ giữ boolean rồi bỏ toàn bộ lý do thất bại.

### 6.1. Fact checking một claim

Ví dụ với `FactCheckingEvaluator` trên 1.1.x trở lên:

~~~java
var evaluator = FactCheckingEvaluator.builder(
        ChatClient.builder(judgeChatModel)).build();

String evidence =
        "The service was introduced in version 1.0.0.";
String claim =
        "The service was introduced in version 2.0.0.";

var request = new EvaluationRequest(
        List.of(new Document(evidence)),
        claim
);

EvaluationResponse result = evaluator.evaluate(request);

assertThat(result.isPass()).isFalse();
~~~

Với Spring AI 1.0.0, tạo evaluator bằng constructor public thay vì builder:

~~~java
var evaluator = new FactCheckingEvaluator(
        ChatClient.builder(judgeChatModel));
~~~

Trong constructor hai tham số, context là danh sách tài liệu và response content là claim cần kiểm tra. Khi cần truyền thêm câu hỏi người dùng để phục vụ rubric, dùng constructor ba tham số.

### 6.2. Giữ đúng context đã dùng khi generation

Một sai lầm phổ biến là generation sử dụng retrieved documents ở thời điểm T1, nhưng evaluator chạy retrieval lại ở T2. Hai context khác nhau có thể tạo ra hai verdict khác nhau, khiến ta không biết model đã trả lời đúng theo evidence nào.

Hãy capture chính xác:

- Danh sách document đã gửi tới generation model;
- Document IDs và metadata cần thiết;
- Thứ tự/phiên bản context nếu pipeline có reranking hoặc compression;
- Nội dung response đã sinh;
- Prompt/model/tool version của lần chạy.

Không chỉ truy vấn lại vector store bằng câu hỏi ban đầu rồi gọi đó là context gốc.

## 7. Tùy chỉnh prompt theo API của từng dòng

### 7.1. RelevancyEvaluator với custom PromptTemplate

Builder của `RelevancyEvaluator` cho phép cấu hình `PromptTemplate`. Template cần giữ ba placeholder:

- `query` — câu hỏi người dùng;
- `response` — câu trả lời cần đánh giá;
- `context` — context hỗ trợ.

Ví dụ:

~~~java
PromptTemplate promptTemplate = new PromptTemplate("""
    You are an evaluator for a retrieval-augmented assistant.

    Determine whether the answer addresses the user's query
    and is supported by the supplied context.

    Return only YES or NO.

    Query:
    {query}

    Answer:
    {response}

    Context:
    {context}

    Verdict:
    """);

RelevancyEvaluator evaluator = RelevancyEvaluator.builder()
        .chatClientBuilder(ChatClient.builder(judgeChatModel))
        .promptTemplate(promptTemplate)
        .build();
~~~

Nếu thiếu placeholder hoặc thay tên placeholder mà không cập nhật logic render, evaluator có thể không nhận đủ dữ liệu. Giữ các placeholder hợp đồng và chỉ thay phần rubric/wording.

### 7.2. FactCheckingEvaluator với custom prompt

Từ dòng 1.0.x, có thể truyền prompt vào constructor overload được Javadocs stable 1.0.0 công bố. Từ dòng 1.1.x, builder cho phép đặt prompt bằng `evaluationPrompt`:

~~~java
FactCheckingEvaluator evaluator = FactCheckingEvaluator
        .builder(ChatClient.builder(judgeChatModel))
        .evaluationPrompt("""
                Document: {document}
                Claim: {claim}

                Decide whether the document supports the claim.
                Return only YES or NO.
                """)
        .build();
~~~

Tên placeholder `document` và `claim` phản ánh hợp đồng prompt fact checking. Nếu thay đổi prompt, hãy giữ chúng hoặc kiểm tra implementation của phiên bản đang dùng để biết biến nào được render.

### 7.3. Prompt thay đổi là thay đổi evaluator

Ngay cả khi Java API không đổi, việc sửa prompt có thể làm verdict thay đổi. Vì vậy, hãy version hóa:

- Evaluator implementation/version;
- Prompt template/version;
- Judge model và model parameters;
- Dataset version;
- Context construction/reranking version;
- Threshold và cách tổng hợp score.

Không gộp một prompt mới vào cùng baseline rồi kết luận model generation đã cải thiện.

## 8. Khác biệt constructor và builder cần lưu ý

Không phải hai evaluator có cùng lịch sử builder. Đây là điểm dễ gặp compile error khi nâng từ 1.0.x lên 1.1.x.

| API | Spring AI 1.0.0 | Spring AI 1.1.x trở lên trong Javadocs đã đối chiếu |
|---|---|---|
| `new RelevancyEvaluator(ChatClient.Builder)` | Có | Có |
| `RelevancyEvaluator.builder()` | Có | Có |
| `RelevancyEvaluator.Builder.chatClientBuilder(...)` | Có | Có |
| `RelevancyEvaluator.Builder.promptTemplate(...)` | Có | Có |
| `new FactCheckingEvaluator(ChatClient.Builder)` | Có | Không còn là public factory; dùng builder |
| `new FactCheckingEvaluator(ChatClient.Builder, String)` | Có | Constructor được quản lý nội bộ; dùng builder với `evaluationPrompt` |
| `FactCheckingEvaluator.forBespokeMinicheck(...)` | Có | Có |
| `FactCheckingEvaluator.builder(ChatClient.Builder)` | Chưa có trong Javadocs 1.0.0 đã đối chiếu | Có |
| `FactCheckingEvaluator.Builder.evaluationPrompt(...)` | Chưa có trong Javadocs 1.0.0 đã đối chiếu | Có |

### 8.1. Code tương thích 1.0.x

Nếu cần hỗ trợ cả 1.0.0, dùng constructor public đã được công bố:

~~~java
var relevancy = new RelevancyEvaluator(
        ChatClient.builder(judgeChatModel));

var factChecking = new FactCheckingEvaluator(
        ChatClient.builder(judgeChatModel));

var factCheckingWithPrompt = new FactCheckingEvaluator(
        ChatClient.builder(judgeChatModel),
        "Document: {document}\nClaim: {claim}"
);
~~~

`RelevancyEvaluator.builder()` cũng đã có trong Javadocs 1.0.0:

~~~java
var relevancy = RelevancyEvaluator.builder()
        .chatClientBuilder(ChatClient.builder(judgeChatModel))
        .promptTemplate(customPrompt)
        .build();
~~~

### 8.2. Code dùng builder cho FactCheckingEvaluator từ 1.1.x

Khi baseline là 1.1.x, 2.0.x hoặc 2.1.x, có thể viết:

~~~java
var factChecking = FactCheckingEvaluator.builder(
            ChatClient.builder(judgeChatModel))
        .evaluationPrompt("Document: {document}\nClaim: {claim}")
        .build();
~~~

Không có cùng một public constructor/builder cho generic `FactCheckingEvaluator` chạy xuyên cả 1.0.0 và 1.1.x trở lên. Nếu phải hỗ trợ đồng thời, dùng factory riêng theo version/source set hoặc tách module adapter theo baseline. Trường hợp dùng Bespoke Minicheck, helper `forBespokeMinicheck(ChatClient.Builder)` được công bố ở cả 1.0.0 và các Javadocs mới hơn, nên có thể dùng làm điểm chung sau khi xác nhận đúng provider/model.

### 8.3. Helper cho Bespoke Minicheck

Javadocs 1.0.0 đã công bố `FactCheckingEvaluator.forBespokeMinicheck(ChatClient.Builder)`. Đây là helper cấu hình evaluator cho model Bespoke Minicheck. Model judge phải được cấu hình đúng provider/runtime mà bạn sử dụng; helper không tự cài Ollama, tải model hay tạo endpoint.

~~~java
var evaluator = FactCheckingEvaluator.forBespokeMinicheck(
        ChatClient.builder(minicheckChatModel));
~~~

Dùng một judge model chuyên fact checking có thể giảm chi phí hoặc cải thiện tốc độ cho tác vụ phù hợp, nhưng vẫn cần đo false positive/false negative trên dataset của dự án.

## 9. Nâng cấp giữa các dòng phiên bản

### 9.1. Từ milestone sang stable 1.0.x

Một số milestone rất sớm dùng `List<Content>` trong `EvaluationRequest`. Javadocs 1.0.0-M4 thể hiện kiểu này; các mốc sau đó đã chuyển sang `Document`. Javadocs stable 1.0.9 dùng `List<Document>`.

Nếu dự án đang ở milestone, hãy kiểm tra chính xác mốc đang resolve. Đừng suy ra chữ ký stable từ ví dụ M4, và đừng thay đổi context type khi chưa xác nhận dependency.

### 9.2. Từ 1.0.x lên 1.1.x

- Giữ package `org.springframework.ai.evaluation` cho request/response/interface.
- Giữ package `org.springframework.ai.chat.evaluation` cho evaluator implementations.
- Dùng `List<Document>` trong `EvaluationRequest` theo Javadocs stable 1.0.9/1.1.x.
- Có thể chuyển FactCheckingEvaluator từ constructor sang builder nếu muốn dùng `evaluationPrompt` theo API 1.1.x.
- Nếu dùng RelevancyEvaluator builder, giữ `query`, `response`, `context` trong custom template.

Không bắt buộc đổi toàn bộ constructor sang builder nếu ứng dụng không cần custom prompt. Một thay đổi ít nhất có thể giảm rủi ro làm thay đổi behavior không chủ ý.

### 9.3. Từ 1.1.x lên 2.0.x

- Đồng bộ toàn bộ Spring AI artifacts qua BOM 2.0.x.
- Đảm bảo Spring Boot baseline phù hợp với dòng 2.0.x.
- Kiểm tra migration guide của 2.0 cho toàn bộ ứng dụng, đặc biệt các module model, advisors, tool calling và dependency bên thứ ba.
- Giữ các evaluator imports và request/response mapping nếu Javadocs của bản 2.0.x đang dùng xác nhận cùng hợp đồng.
- Chạy lại evaluator golden set vì model provider, prompt hoặc context pipeline có thể đã thay đổi trong cùng đợt nâng cấp.

Javadocs 2.0.1 vẫn cho thấy `Evaluator.evaluate(EvaluationRequest)` và các implementation trong `org.springframework.ai.chat.evaluation`. Không nên coi điều đó là bằng chứng rằng mọi thành phần RAG/tool hoặc mọi integration của ứng dụng không có breaking change.

### 9.4. Từ 2.0.x lên 2.1.x

- Nâng đồng bộ BOM và provider starter lên cùng dòng 2.1.x.
- Kiểm tra Spring Boot baseline 4.2.x theo ma trận tương thích hiện tại của Spring AI.
- Xác nhận `EvaluationRequest` trên Javadocs đúng phiên bản, đặc biệt vì trang hướng dẫn stable 2.1.0 và Javadocs hiển thị kiểu context không đồng nhất.
- Compile test tối thiểu tạo `EvaluationRequest` từ `List<Document>`.
- Chạy lại baseline và lưu evaluator/prompt/model versions để phân biệt API migration với thay đổi judge behavior.

Không sử dụng `2.1.1-SNAPSHOT` làm bằng chứng cho khả năng của bản stable 2.1.0. Snapshot là mã đang phát triển; API có thể thay đổi trước khi phát hành.

## 10. Quy trình xác minh API trong dự án

Một trang hướng dẫn có thể cũ, Javadocs có thể thuộc nhánh khác và dependency resolution có thể kéo về version không như mong muốn. Hãy xác minh từ dependency đang được build.

### 10.1. Kiểm tra dependency tree

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.ai
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm tra tất cả artifact Spring AI cùng một dòng. Nếu thấy một module 1.1.x và module khác 2.0.x trong cùng runtime, xử lý dependency management trước khi debug evaluator.

### 10.2. Kiểm tra compile contract

Tạo một compile test nhỏ chứa các imports và constructor/builder dự định dùng:

~~~java
import java.util.List;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.FactCheckingEvaluator;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;

class EvaluatorApiCompatibilityTest {

    void compileAgainstResolvedSpringAi(
            ChatModel judgeModel,
            String question,
            String answer) {

        List<Document> context = List.of(
                new Document("A service was introduced in version 1.0.")
        );

        EvaluationRequest request =
                new EvaluationRequest(question, context, answer);

        RelevancyEvaluator relevancy =
                new RelevancyEvaluator(ChatClient.builder(judgeModel));

        FactCheckingEvaluator factChecking =
                new FactCheckingEvaluator(ChatClient.builder(judgeModel));

        EvaluationResponse result = relevancy.evaluate(request);
        boolean passed = result.isPass();
    }
}
~~~

Đây là compile-contract sample; test thực thi cần cấu hình judge provider thật hoặc test double phù hợp. Khi nhắm riêng 1.1.x trở lên, thêm một compile test cho builder FactCheckingEvaluator.

### 10.3. Kiểm tra Javadocs đúng artifact

Khi có lỗi compile:

1. Xác nhận version đã resolve từ dependency tree;
2. Mở Javadocs đúng version, không dùng URL `current` nếu đang build version cũ;
3. Kiểm tra package, constructor và method;
4. Kiểm tra kiểu generic của `EvaluationRequest.getDataList()`;
5. Đối chiếu source artifact nếu Javadocs có điểm không rõ;
6. Biên dịch một sample nhỏ trước khi sửa toàn bộ integration.

Đừng dùng import tự động từ IDE để đoán package. Hai nhóm class evaluator và core evaluation nằm ở hai package khác nhau.

## 11. API evaluator hỗ trợ gì và không thay thế điều gì?

`Evaluator` là primitive để đánh giá một request. Nó giúp gọi judge model theo hợp đồng chung và nhận một kết quả có cấu trúc cơ bản.

| Nhu cầu | Evaluator API có sẵn | Phần ứng dụng cần bổ sung |
|---|---|---|
| Đánh giá relevance của một response | `RelevancyEvaluator` | Dataset, threshold và aggregation |
| Fact check claim theo context | `FactCheckingEvaluator` | Claim splitting, evidence selection và review |
| Dùng judge model riêng | `ChatClient.Builder` | Cấu hình provider, budget và retry |
| Tùy chỉnh prompt | Builder/constructor tùy phiên bản | Prompt versioning và regression baseline |
| Chạy một request | `evaluate(EvaluationRequest)` | Batch runner, concurrency, rate limit |
| Lưu kết quả | `EvaluationResponse` trả dữ liệu | Persistence, sample ID, trace links, history |
| So sánh nhiều phiên bản | Không tự có | Evaluation pipeline và dashboard |

API evaluator không tự cung cấp dataset registry, orchestration, batch scheduling, metrics aggregation, trace correlation hay một bộ rubric toàn diện cho RAG/tool calling. Đây là các lớp cần xây trong evaluation pipeline của ứng dụng.

### 11.1. Không xem judge verdict là ground truth

RelevancyEvaluator và FactCheckingEvaluator đều dựa trên model để đưa ra phán đoán. Kết quả có thể thay đổi theo judge model, prompt, temperature, context, provider hoặc model revision.

Với tiêu chí quan trọng, nên:

- Kết hợp deterministic assertions với judge score;
- Dùng một tập human-labeled samples để hiệu chỉnh;
- Theo dõi false pass và false fail;
- Giữ model/prompt/dataset version;
- Đặt ngưỡng và quy tắc xử lý `INCONCLUSIVE` ở application layer;
- Không cho judge tự xác nhận một business effect mà audit ledger chưa chứng minh.

## 12. Bảo toàn khả năng so sánh khi nâng evaluator

Một dự án có thể compile thành công sau nâng cấp nhưng điểm evaluator thay đổi. Điều đó không tự động chứng minh model generation tốt hơn hoặc tệ hơn.

Các yếu tố có thể làm verdict thay đổi:

- Judge model/provider hoặc model revision;
- Temperature, max output tokens, retry và timeout;
- Default prompt hoặc custom prompt;
- Kiểu context, thứ tự document, metadata và truncation;
- Dataset sample, expected labels hoặc cách tách claim;
- Spring AI evaluator implementation;
- Provider response parsing hoặc định dạng đầu ra judge.

### 12.1. Lưu metadata cho mỗi lần evaluation

Một evaluation record nên có tối thiểu:

| Metadata | Mục đích |
|---|---|
| `sampleId` và `datasetVersion` | Xác định test case và snapshot dữ liệu |
| `springAiVersion` | Phiên bản thư viện thực thi evaluator |
| `evaluatorType` và `evaluatorVersion` | Phân biệt evaluator và adapter tùy chỉnh |
| `promptVersion` | Xác định rubric/prompt |
| `judgeModel` và `judgeModelRevision` | Xác định model chấm |
| `judgeParameters` | Temperature, token cap, seed nếu provider hỗ trợ |
| `contextVersion`/`retrievalVersion` | Xác định evidence đã gửi cho judge |
| `generationModel` và `promptVersion` | Xác định hệ thống đã tạo response |
| `pass`, `score`, `feedback` | Kết quả evaluator |
| `latency`, `tokenUsage`, `cost` | Đo vận hành evaluator |
| `traceId`/`evaluationRunId` | Truy vết lần chạy |

Không cần nhét tất cả metadata vào metric tags. Lưu chi tiết trong evaluation result store; metrics chỉ nên dùng các dimensions có cardinality thấp.

### 12.2. Chạy cùng một golden set trước và sau nâng cấp

Quy trình đề xuất:

1. Chốt dataset version và giữ nguyên samples;
2. Lưu prompt/model/config của generation và judge;
3. Chạy evaluator trên baseline version;
4. Nâng Spring AI và chạy lại cùng fixture;
5. So sánh pass rate, score distribution, feedback category, latency và token/cost;
6. Phân loại thay đổi do API, prompt, judge model, context hay generation model;
7. Review các sample chuyển từ PASS sang FAIL và ngược lại;
8. Chỉ cập nhật baseline sau khi có lý do và phê duyệt của nhóm phụ trách.

Nếu muốn đo riêng tác động của Spring AI version, giữ judge model, prompt, context và dataset không đổi. Nếu một provider/model đã bị thay thế, ghi rõ đó là một biến độc lập trong thí nghiệm.

### 12.3. Không so score khác thang đo

`EvaluationResponse.getScore()` không đảm bảo mọi evaluator hoặc custom evaluator dùng cùng thang đo. Trước khi tổng hợp score giữa các phiên bản, xác định:

- Score range;
- Mapping từ raw judge response sang score;
- Threshold pass/fail;
- Cách xử lý output không hợp lệ;
- Cách xử lý timeout/retry;
- Quy tắc cho verdict không đủ evidence.

Với evaluator mặc định trả verdict nhị phân, pass rate và confusion matrix trên tập có nhãn thường dễ giải thích hơn việc tự tạo một điểm tổng hợp không có định nghĩa.

## 13. Hướng dẫn chọn API theo tình huống

| Tình huống dự án | API nên chọn | Ghi chú tương thích |
|---|---|---|
| RAG integration test đơn giản | `RelevancyEvaluator(ChatClient.Builder)` | Constructor có trong các dòng đã đối chiếu |
| RAG cần rubric riêng | `RelevancyEvaluator.builder()` | Builder và `promptTemplate` có trong Javadocs 1.0.0 trở lên |
| Fact check ở Spring AI 1.0.0 | `new FactCheckingEvaluator(ChatClient.Builder)` | Constructor public trong Javadocs 1.0.0 |
| Fact check tùy prompt ở 1.0.0 | `new FactCheckingEvaluator(ChatClient.Builder, String)` | Overload public được Javadocs 1.0.0 công bố |
| Fact check ở 1.1.x/2.x | `FactCheckingEvaluator.builder(ChatClient.Builder)` | Cấu hình prompt bằng `evaluationPrompt` |
| Dùng Bespoke Minicheck | `FactCheckingEvaluator.forBespokeMinicheck(...)` | Helper có trong Javadocs 1.0.0 và các dòng mới hơn đã kiểm tra |
| Tiêu chí nghiệp vụ riêng | Custom `Evaluator` hoặc evaluator wrapper | Tự định nghĩa rubric, persistence và verdict |
| Đánh giá chuỗi tool/trace | Deterministic evaluator của ứng dụng + evidence trace | Hai evaluator có sẵn không tự chấm tool sequence |

### 13.1. Khi nào nên viết custom Evaluator?

Viết custom evaluator nếu tiêu chí không phải relevance hoặc grounded fact checking, ví dụ:

- Tool bắt buộc phải được gọi trước tool khác;
- Tool write chỉ được gọi khi precondition thỏa;
- Final answer phải trích dẫn đúng document ID;
- Agent không được khẳng định side effect khi ledger chưa xác nhận;
- Một response phải tuân theo JSON schema hoặc business policy cụ thể.

Giữ deterministic checks cho điều kiện có thể kiểm tra bằng code. Dùng judge model cho phần ngữ nghĩa khó biểu diễn thành rule. Không giao quyền quyết định side effect cho một evaluator chỉ trả YES/NO.

## 14. Kiểm thử compatibility và chất lượng sau nâng cấp

| Test | Tình huống | Kỳ vọng |
|---|---|---|
| **TC01 — Package contract** | Compile imports của Evaluator, request/response và hai evaluator | Không có package drift ngoài version đã chọn |
| **TC02 — 1.0 Relevancy constructor** | Tạo `RelevancyEvaluator(ChatClient.Builder)` | Compile trên 1.0.0 |
| **TC03 — 1.0 Relevancy builder** | Dùng builder, chatClientBuilder, promptTemplate | Compile trên 1.0.0 |
| **TC04 — 1.0 FactChecking constructor** | Tạo evaluator bằng constructor public | Compile trên 1.0.0 |
| **TC05 — 1.0 FactChecking prompt** | Dùng constructor có evaluationPrompt | Compile trên 1.0.0 |
| **TC06 — 1.1 FactChecking builder** | Dùng builder(...).evaluationPrompt(...).build() | Compile trên 1.1.x |
| **TC07 — 2.x package contract** | Compile evaluator imports trên 2.0.x/2.1.x | Package và method khớp Javadocs đúng version |
| **TC08 — Context generic** | Tạo request từ `List<Document>` | Compile với stable API đã resolve |
| **TC09 — Milestone compatibility** | Build với artifact M4 dùng `List<Content>` | Không trộn signature milestone vào stable |
| **TC10 — Judge model isolation** | Dùng judge model riêng | Request được gửi đến đúng model |
| **TC11 — Relevance positive** | Response phù hợp context | PASS theo rubric |
| **TC12 — Relevance negative** | Response lạc đề | FAIL theo rubric |
| **TC13 — Fact check positive** | Claim được evidence hỗ trợ | PASS |
| **TC14 — Fact check negative** | Claim mâu thuẫn evidence | FAIL |
| **TC15 — Missing evidence** | Claim không có context hỗ trợ | Không kết luận supported |
| **TC16 — Prompt placeholders** | Thiếu query/response/context hoặc document/claim | Test phát hiện cấu hình sai |
| **TC17 — Judge invalid output** | Model trả nội dung ngoài YES/NO hoặc format mong đợi | Ghi lỗi/unknown theo policy |
| **TC18 — Timeout/retry** | Judge provider timeout | Retry/terminal outcome được ghi rõ |
| **TC19 — Dataset repeatability** | Chạy cùng sample nhiều lần | Variance được đo và ghi nhận |
| **TC20 — Context identity** | Evaluator nhận chính context generation đã dùng | Không retrieval lại ngoài ý muốn |
| **TC21 — Prompt version drift** | Thay prompt evaluator | Baseline mới có version riêng |
| **TC22 — Model revision drift** | Judge model thay revision | Kết quả được phân cohort |
| **TC23 — Dependency alignment** | BOM resolve nhiều version Spring AI | CI phát hiện artifact lệch dòng |
| **TC24 — Regression report** | So sánh baseline và candidate | Có sample-level diff và aggregate metrics |

### 14.1. Các assertion cần có trong CI

- Compile test cho API version mục tiêu;
- Kiểm tra dependency tree không trộn Spring AI release lines;
- Positive và negative fixtures cho từng evaluator;
- Kiểm tra prompt placeholders;
- Lưu evaluator/model/prompt/dataset versions;
- Kiểm tra context được chuyển nguyên vẹn theo hợp đồng;
- Ghi latency, usage và lỗi judge;
- Không xem lỗi hạ tầng hoặc judge timeout như một verdict PASS;
- Xuất diff theo sample để reviewer xem các trường hợp đổi verdict.

## 15. Quy trình nâng cấp evaluator trong CI/CD

1. **Khóa baseline:** ghi Spring AI BOM, Spring Boot, Java, provider starter và judge model.
2. **Kiểm tra release line:** xác định phiên bản stable tương thích với Spring Boot hiện tại.
3. **Đọc Javadocs đúng version:** kiểm tra package, constructors, builders và generic types.
4. **Cập nhật dependency đồng bộ:** dùng BOM, không pin lẻ từng module.
5. **Sửa API tối thiểu:** chỉ đổi constructor/builder hoặc kiểu context khi compiler yêu cầu.
6. **Chạy compile-contract test:** bắt package/signature mismatch sớm.
7. **Chạy golden evaluation set:** dùng dataset và prompt version đã khóa.
8. **So sánh kết quả:** pass rate, false pass/fail, feedback, latency, token usage và cost.
9. **Kiểm tra trace:** xác nhận evaluator call có trace/span và correlation IDs cần thiết.
10. **Review regression:** mở các sample đổi verdict và xác định nguyên nhân.
11. **Cập nhật baseline:** chỉ khi thay đổi đã được hiểu và chấp nhận.
12. **Phát hành:** ghi version matrix và hướng dẫn rollback nếu judge behavior suy giảm.

### Checklist trước khi merge nâng cấp

- [ ] Spring AI artifacts dùng cùng một BOM/version line.
- [ ] Spring Boot tương thích với Spring AI line đã chọn.
- [ ] Imports của evaluator và core evaluation đúng package.
- [ ] `FactCheckingEvaluator` dùng constructor hoặc builder đúng phiên bản.
- [ ] `EvaluationRequest` dùng context type theo Javadocs của artifact đã resolve.
- [ ] Không dùng API từ milestone/snapshot trong source stable.
- [ ] Judge model và generation model được xác định rõ.
- [ ] Prompt placeholders được kiểm tra.
- [ ] Golden dataset được giữ nguyên trong phép so sánh.
- [ ] Evaluator/model/prompt/dataset versions được ghi.
- [ ] CI có positive/negative tests và compile-contract tests.
- [ ] Regression report có sample-level verdict diff.

## 16. Bài luyện tập

### Bài 1 — Chọn constructor đúng phiên bản

Dự án đang dùng Spring AI 1.0.0. Bạn cần tạo FactCheckingEvaluator với custom prompt. Dùng API nào? Vì sao builder ở ví dụ 1.1.x không phù hợp?

### Bài 2 — Nâng lên 1.1.x

Sau nâng cấp, code gọi `new FactCheckingEvaluator(ChatClient.Builder)` không compile. Bạn cần chuyển sang API nào? Các placeholder trong prompt là gì?

### Bài 3 — Kiểu context

Một ví dụ milestone 1.0.0-M4 dùng `List<Content>`, nhưng Javadocs stable 1.0.9 dùng `List<Document>`. Dự án đang resolve 1.0.9. Bạn chọn kiểu nào và kiểm tra ở đâu?

### Bài 4 — Phân biệt relevance và fact checking

Response trả lời đúng chủ đề nhưng có một con số sai so với tài liệu. Nên dùng evaluator nào để kiểm tra claim sai? Vì sao relevance pass không đủ?

### Bài 5 — Judge model riêng

Generation model là một model lớn; judge model là một model nhỏ. Cần truyền object nào cho evaluator? Vì sao API nhận ChatClient.Builder?

### Bài 6 — Kết quả thay đổi sau nâng cấp

Sau khi nâng Spring AI, pass rate tăng từ 82% lên 91%. Hãy liệt kê các biến cần kiểm tra trước khi kết luận chất lượng generation được cải thiện.

### Bài 7 — Snapshot và stable

Một đoạn hướng dẫn 2.1-SNAPSHOT dùng kiểu Document, trang testing stable 2.1.0 hiển thị Content. Bạn xử lý sự khác biệt thế nào trước khi merge?

### Bài 8 — Fact checking closed-book

Bạn muốn hỏi evaluator “Thủ đô của một quốc gia là gì?” mà không cung cấp context. FactCheckingEvaluator có phù hợp không? Nêu cách chọn phương pháp đánh giá.

### Bài 9 — Tool workflow

Bạn cần xác nhận agent gọi lookup_order trước create_ticket. Có nên dùng RelevancyEvaluator để chấm thứ tự tool không? Hãy đề xuất lớp kiểm tra phù hợp.

### Bài 10 — Compatibility matrix

Một thư viện nội bộ phải hỗ trợ Spring AI 1.0.x và 2.1.x. Nêu cách tổ chức adapter/factory để không gọi FactCheckingEvaluator builder mới trong runtime 1.0.x.

### Gợi ý đáp án

1. Dùng constructor public `new FactCheckingEvaluator(ChatClient.Builder, String)` được Javadocs 1.0.0 công bố. Builder FactCheckingEvaluator chưa có trong API 1.0.0 đã đối chiếu.
2. Dùng `FactCheckingEvaluator.builder(ChatClient.Builder).evaluationPrompt(...).build()`. Giữ `document` và `claim` trong prompt.
3. Dùng `List<Document>` vì dependency đang resolve là stable 1.0.9; kiểm Javadocs 1.0.x và compile test.
4. Dùng FactCheckingEvaluator để kiểm claim với evidence. RelevancyEvaluator chỉ kiểm response có phù hợp query/context tổng thể hay không.
5. Tạo `ChatClient.Builder` từ judge `ChatModel` bằng `ChatClient.builder(judgeChatModel)`, rồi truyền builder cho evaluator.
6. Kiểm judge model/revision, prompt, temperature, dataset, context, retrieval/reranking, evaluator implementation và provider parsing.
7. Kiểm Javadocs đúng artifact/version và compile test. Không dùng snapshot làm hợp đồng cho stable; nếu reference prose không khớp Javadocs, ghi lại discrepancy và dùng chữ ký binary đã resolve.
8. Không phù hợp vì FactCheckingEvaluator là grounded fact checking, cần document/context. Dùng benchmark closed-book có answer key hoặc evaluator phù hợp với rubric kiến thức.
9. Dùng deterministic action/trace evaluator nối proposal, dispatch và callback bằng IDs; RelevancyEvaluator không chấm thứ tự thực thi.
10. Tạo module adapter theo version line hoặc build profiles/source sets. Factory của 1.0 dùng constructor; factory 1.1+/2.x dùng builder. Chỉ expose interface nội bộ ổn định cho phần code chung.





## Tài liệu tham khảo

- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): hợp đồng Evaluator, RelevancyEvaluator, FactCheckingEvaluator và ví dụ RAG.
- [Spring AI 1.0.0 — Evaluator Javadocs](https://docs.spring.io/spring-ai/docs/1.0.0/api/org/springframework/ai/evaluation/Evaluator.html): interface và phương thức evaluate.
- [Spring AI 1.0.0 — RelevancyEvaluator Javadocs](https://docs.spring.io/spring-ai/docs/1.0.0/api/org/springframework/ai/chat/evaluation/RelevancyEvaluator.html): constructor, builder và evaluate.
- [Spring AI 1.0.0 — FactCheckingEvaluator Javadocs](https://docs.spring.io/spring-ai/docs/1.0.0/api/org/springframework/ai/chat/evaluation/FactCheckingEvaluator.html): constructor, custom prompt overload và helper Minicheck.
- [Spring AI 1.0.0-M4 — EvaluationRequest Javadocs](https://docs.spring.io/spring-ai/docs/1.0.0-M4/api/org/springframework/ai/evaluation/EvaluationRequest.html): kiểu Content ở milestone sớm.
- [Spring AI 1.0.x — API Index](https://docs.spring.io/spring-ai/docs/1.0.x/api/index-all.html): Javadocs stable 1.0.x, bao gồm EvaluationRequest với Document.
- [Spring AI 1.1.0 — FactCheckingEvaluator.Builder](https://docs.spring.io/spring-ai/docs/1.1.0/api/org/springframework/ai/chat/evaluation/FactCheckingEvaluator.Builder.html): builder và evaluationPrompt.
- [Spring AI 1.1.x — RelevancyEvaluator.Builder](https://docs.spring.io/spring-ai/docs/1.1.x/api/org/springframework/ai/chat/evaluation/RelevancyEvaluator.Builder.html): cấu hình ChatClient và PromptTemplate.
- [Spring AI 2.0.1 — RelevancyEvaluator Javadocs](https://docs.spring.io/spring-ai/docs/2.0.1/api/org/springframework/ai/chat/evaluation/RelevancyEvaluator.html): API evaluator trên dòng 2.0.x.
- [Spring AI 2.0.1 — EvaluationRequest Javadocs](https://docs.spring.io/spring-ai/docs/2.0.1/api/org/springframework/ai/evaluation/EvaluationRequest.html): kiểu context Document và các constructor.
- [Spring AI stable — RelevancyEvaluator Javadocs](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/chat/evaluation/RelevancyEvaluator.html): API của bản stable hiện hành.
- [Spring AI stable — FactCheckingEvaluator Javadocs](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/chat/evaluation/FactCheckingEvaluator.html): builder, helper Minicheck và evaluate của bản stable hiện hành.
- [Spring AI stable — EvaluationRequest Javadocs](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/evaluation/EvaluationRequest.html): constructor và kiểu context trong API reference stable.
- [Spring AI 2.1.x — Evaluators Reference](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/evaluation/evaluators.html): tài liệu evaluator của nhánh 2.1 đang phát triển; chỉ dùng để tham khảo snapshot.
- [Spring AI Releases](https://github.com/spring-projects/spring-ai/releases): trạng thái phát hành và release notes.
- [Spring AI Repository](https://github.com/spring-projects/spring-ai): ma trận Spring Boot tương thích theo các nhánh Spring AI.

**Kết luận:** API evaluator có mặt xuyên các dòng Spring AI 1.x và 2.x đã đối chiếu, nhưng cách tạo FactCheckingEvaluator thay đổi rõ giữa 1.0.x và 1.1.x trở lên. RelevancyEvaluator đã có constructor và builder từ 1.0.0; FactCheckingEvaluator dùng constructor public ở 1.0.0 rồi chuyển sang builder trong các dòng mới. Khi nâng cấp, hãy dùng BOM đồng bộ, đọc Javadocs đúng artifact, xác minh kiểu Document/Content bằng compiler và chạy lại golden dataset với judge/prompt/context được version hóa. Nhờ vậy, bạn có thể tách lỗi API khỏi thay đổi chất lượng đánh giá và giữ được khả năng so sánh giữa các phiên bản.

