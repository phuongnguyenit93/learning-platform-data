# RelevancyEvaluator: Khởi tạo evaluator với ChatClient.Builder phù hợp

## 1. Bối cảnh và mục tiêu

Trong một ứng dụng Spring AI có Retrieval-Augmented Generation (RAG), câu trả lời được sinh ra từ **câu hỏi người dùng** và **tài liệu truy xuất**. Để đánh giá câu trả lời có phù hợp với hai thành phần này hay không, Spring AI cung cấp `RelevancyEvaluator`, một implementation của `Evaluator`. Thành phần này sử dụng một mô hình ngôn ngữ đóng vai trò **judge** để đưa ra kết quả đạt hoặc không đạt.

Một câu hỏi triển khai dễ bị bỏ qua là: **nên truyền `ChatClient.Builder` nào vào `RelevancyEvaluator`?** Nếu builder trỏ đến sai mô hình, mang theo advisor RAG, chat memory, tool hoặc system prompt của trợ lý, quá trình chấm có thể tốn thêm chi phí, bị nhiễu hoặc trả kết quả không đúng định dạng.

Trong module `SPRING_AI_EVALUATION_OBSERVABILITY`, việc chọn builder cho evaluator gắn trực tiếp với mục tiêu **đánh giá theo tập dữ liệu** và theo dõi **chất lượng, traces, metrics, chi phí, độ trễ** khi thay prompt, model và pipeline. Bài này tập trung vào kỹ thuật **khởi tạo và cấu hình evaluator**; nó cũng giải thích cách dùng evaluator đó trong một phép thử RAG.

Sau bài học, bạn sẽ:

1. Phân biệt `ChatModel`, `ChatClient` và `ChatClient.Builder` khi tạo bộ chấm.
2. Khởi tạo `RelevancyEvaluator` theo hai cách API hỗ trợ.
3. Chọn mô hình và cấu hình builder phù hợp với bài toán đánh giá.
4. Tách bộ chấm khỏi các advisor, tools và mặc định của ứng dụng trả lời.
5. Biết cách đưa evaluator vào Spring Boot, kiểm thử và quan sát kết quả.

## 2. Phân biệt ChatModel, ChatClient và ChatClient.Builder

Ba thành phần đều liên quan đến việc gọi mô hình, nhưng có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `ChatModel` | API của mô hình chat (OpenAI, Ollama hoặc provider khác), nơi xử lý yêu cầu sinh nội dung | Model trả lời câu hỏi hoặc model chuyên chấm |
| `ChatClient.Builder` | Cấu hình để tạo `ChatClient`: model, options, mặc định prompt, advisors, tools và các thiết lập liên quan | `ChatClient.builder(judgeModel)` |
| `ChatClient` | Client được build để thực hiện lời gọi chat | `builder.build().prompt().user(...).call().content()` |
| `RelevancyEvaluator` | Xây dựng prompt đánh giá từ dữ liệu test, dùng `ChatClient.Builder` để gọi judge rồi diễn giải phán quyết | `new RelevancyEvaluator(judgeBuilder)` |

Một luồng RAG thường có **hai vai trò mô hình**:

~~~mermaid
flowchart LR
    Q["Câu hỏi"] --> RET["Retriever"]
    RET --> DOC["Tài liệu truy xuất"]
    Q --> GEN["Answer ChatClient"]
    DOC --> GEN
    GEN --> ANS["Câu trả lời"]
    Q --> REQ["EvaluationRequest"]
    DOC --> REQ
    ANS --> REQ
    REQ --> EVAL["RelevancyEvaluator"]
    B["Judge ChatClient.Builder"] --> EVAL
    EVAL --> J["Judge ChatModel"]
    J --> RESULT["EvaluationResponse"]
~~~

Mô hình sinh câu trả lời (*answer model*) và mô hình chấm (*judge model*) **có thể là cùng một model hoặc khác nhau**. Với bộ kiểm thử cần so sánh các bản prompt/model, một judge model được kiểm soát độc lập giúp phép đo nhất quán hơn. Dùng một model cho cả hai vai trò vẫn hợp lệ ở ví dụ học tập hoặc hệ thống có ngân sách nhỏ, nhưng có thể mang thiên lệch chung và khó phân tích khi model thay đổi.

Điểm kỹ thuật quan trọng: constructor nhận **`ChatClient.Builder`**, không nhận `ChatClient` đã `build()` và cũng không nhận trực tiếp `ChatModel`.

## 3. Cách 1: khởi tạo trực tiếp bằng constructor

Đây là cách ngắn gọn nhất khi đã có `ChatModel` của judge:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.chat.model.ChatModel;

// judgeModel đã được cấu hình trước đó.
ChatClient.Builder judgeBuilder = ChatClient.builder(judgeModel);

RelevancyEvaluator evaluator = new RelevancyEvaluator(judgeBuilder);
~~~

Có thể viết ngắn hơn:

~~~java
RelevancyEvaluator evaluator =
        new RelevancyEvaluator(ChatClient.builder(judgeModel));
~~~

Cả hai đều sử dụng prompt đánh giá mặc định của `RelevancyEvaluator`. Bạn không cần tự tạo `ChatClient` bằng cách gọi `build()` trước khi truyền vào constructor.

### Vì sao không truyền một ChatClient đã build?

Đoạn sau sai về kiểu tham số:

~~~java
// KHÔNG ĐÚNG: constructor yêu cầu ChatClient.Builder.
ChatClient judgeClient = ChatClient.builder(judgeModel).build();
RelevancyEvaluator evaluator = new RelevancyEvaluator(judgeClient);
~~~

Cách đúng:

~~~java
ChatClient.Builder judgeBuilder = ChatClient.builder(judgeModel);
RelevancyEvaluator evaluator = new RelevancyEvaluator(judgeBuilder);
~~~

Trong implementation Spring AI 2.1.x, mỗi lần `evaluate(...)`, evaluator lấy thông tin từ `EvaluationRequest`, render prompt và thực hiện lời gọi tương đương:

~~~java
String judgeOutput = chatClientBuilder
        .build()
        .prompt()
        .user(evaluationPrompt)
        .call()
        .content();
~~~

Điều này giải thích vì sao evaluator phải nhận **builder** và vì sao builder đó quyết định model cùng các thiết lập mặc định được dùng cho **lượt gọi chấm**. Đây là mô tả cơ chế của implementation hiện tại; nếu nâng phiên bản Spring AI, hãy xác nhận lại hành vi từ source/API của phiên bản đang chạy.

## 4. Cách 2: dùng RelevancyEvaluator.builder()

Khi cần một cấu hình dễ mở rộng, đặc biệt để **tùy chỉnh `PromptTemplate` của bộ chấm**, hãy dùng builder riêng của `RelevancyEvaluator`:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;

RelevancyEvaluator evaluator = RelevancyEvaluator.builder()
        .chatClientBuilder(ChatClient.builder(judgeModel))
        .build();
~~~

Cách này tương đương về mục đích với constructor trực tiếp khi không thiết lập template bổ sung.

Nếu cần thay tiêu chí chấm:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.chat.prompt.PromptTemplate;

PromptTemplate judgePrompt = new PromptTemplate("""
    Bạn là giám khảo kiểm tra mức độ liên quan của câu trả lời RAG.

    Câu hỏi: {query}
    Câu trả lời: {response}
    Ngữ cảnh hỗ trợ: {context}

    Trả lời YES nếu câu trả lời giải quyết đúng câu hỏi
    và phù hợp với ngữ cảnh. Ngược lại trả lời NO.

    Chỉ xuất ra chính xác một từ: YES hoặc NO.
    """);

RelevancyEvaluator evaluator = RelevancyEvaluator.builder()
        .chatClientBuilder(ChatClient.builder(judgeModel))
        .promptTemplate(judgePrompt)
        .build();
~~~

Ba placeholder **`{query}`**, **`{response}`**, **`{context}`** cần có trong template tùy chỉnh. `RelevancyEvaluator` dùng chúng để chèn câu hỏi, phản hồi và dữ liệu hỗ trợ. Nếu thiếu placeholder, bước render có thể không cung cấp đủ dữ liệu hoặc gặp lỗi tùy template renderer và phiên bản thư viện.

Có **hai builder khác nhau** trong ví dụ:

- `ChatClient.builder(judgeModel)` tạo builder của client gọi **judge model**.
- `RelevancyEvaluator.builder()` tạo builder của **bộ đánh giá**, có các phương thức `chatClientBuilder(...)` và `promptTemplate(...)`.

Đừng nhầm `ChatClient.Builder` với `RelevancyEvaluator.Builder`, và đừng dùng `ChatClient.Builder.defaultSystem(...)` để thay thế hoàn toàn `RelevancyEvaluator.Builder.promptTemplate(...)`. Hai cơ chế cấu hình tác động lên những lớp khác nhau của prompt.

## 5. Thế nào là một ChatClient.Builder “phù hợp”?

Một builder phù hợp phải đưa ra phán quyết đáng tin cậy trên **dữ liệu đánh giá**, có chi phí và độ trễ chấp nhận được, đồng thời không vô tình mang logic xử lý câu hỏi của trợ lý vào lượt chấm.

| Tiêu chí | Mong muốn với judge | Vấn đề khi cấu hình sai |
| --- | --- | --- |
| Mô hình | Model có khả năng đọc hiểu tài liệu/ngôn ngữ của bộ test | Judge không hiểu ngữ cảnh, tạo nhãn sai |
| Mục tiêu prompt | Chỉ chấm câu hỏi + phản hồi + nguồn hỗ trợ | Judge tiếp tục trả lời thay vì chấm |
| Định dạng đầu ra | Chính xác `YES` hoặc `NO` theo rubric | Judge trả câu giải thích/JSON, bị diễn giải thành fail |
| Advisors | Chỉ giữ các advisor thật sự cần cho đánh giá | Memory/RAG làm thay đổi dữ liệu được chấm |
| Tools | Không tự động bật tool nghiệp vụ nếu không cần | Judge tự tra cứu nguồn mới, tốn chi phí, làm lệch phép đo |
| Mặc định user/system | Không xung đột với judge prompt | System prompt của chatbot áp đặt phong cách trả lời |
| Sự ổn định | Cố định model, cấu hình và rubric khi so sánh lần chạy | Pass rate biến động do thay đổi hệ thống đo |
| Vận hành | Có kiểm soát token, timeout, quota, truy vết | Test chạy lâu, lỗi rate limit hoặc vượt ngân sách |

### 5.1. Dùng builder riêng cho judge

Giả sử ứng dụng phục vụ người dùng đang có `answerClient` tích hợp RAG và tools. Hãy tạo **một builder độc lập** để chấm:

~~~java
ChatClient answerClient = ChatClient.builder(answerModel)
        // Có thể gắn RAG advisor hoặc tool ở client trả lời.
        .build();

RelevancyEvaluator relevancyEvaluator =
        new RelevancyEvaluator(ChatClient.builder(judgeModel));
~~~

Nếu có `ChatModel` riêng cho judge, cách này làm rõ nguồn mô hình được dùng. Nó không tự động giữ lại tất cả cấu hình observability hoặc customizer mà Spring Boot cung cấp cho `ChatClient.Builder` đã auto-configure; vấn đề này được phân tích ở phần Spring Boot bên dưới.

**Tránh** kiểu cấu hình sau nếu `sharedBuilder` đã mang advisor RAG, bộ nhớ hội thoại hoặc default tools phục vụ chatbot:

~~~java
// Dễ gây nhiễu nếu sharedBuilder chứa cấu hình của trợ lý trả lời.
RelevancyEvaluator evaluator = new RelevancyEvaluator(sharedBuilder);
~~~

Một advisor RAG ở judge có thể lấy thêm tài liệu dựa trên **cả prompt chấm**; một memory advisor có thể ghép lịch sử hội thoại không thuộc case; tool mặc định có thể thực hiện thêm lời gọi ngoài thiết kế phép thử. Kết quả lúc này khó so sánh và khó truy nguyên.

### 5.2. Chọn model chấm riêng hay dùng lại model trả lời?

**Dùng chung model** phù hợp với demo, proof of concept hoặc môi trường chỉ có một provider. Bạn có thể truyền `ChatClient.builder(chatModel)` cho cả client trả lời và evaluator. Cách này đơn giản nhưng judge và answer có thể bị ảnh hưởng đồng thời khi cấu hình model thay đổi.

**Dùng model riêng** thường phù hợp khi chạy regression suite, so sánh nhiều phiên bản answer model, hoặc cần một thước đo ổn định:

~~~text
answerModelVersion = model-A-v2
judgeModelVersion  = judge-B-v1
judgePromptVersion = relevancy-rubric-v3
datasetVersion     = rag-eval-set-v5
~~~

Muốn kết luận “thay prompt làm pass rate tăng”, nên giữ **judge model, rubric và dataset cố định**. Nếu đổi judge model cùng lúc, kết quả có thể tăng/giảm chỉ vì thước đo thay đổi. Khi thay judge, hãy đối chiếu một tập mẫu đã có nhãn con người.

### 5.3. Giảm tính biến động của phán quyết

Đối với kiểu chấm `YES`/`NO`, thường muốn mô hình ít sáng tạo và trả lời ngắn. Có thể chọn temperature thấp (nếu provider/model hỗ trợ), giới hạn output token phù hợp, ghi rõ system/rubric và yêu cầu chỉ xuất một từ.

Tuy nhiên:

- Cách cấu hình temperature, giới hạn token và seed phụ thuộc phiên bản Spring AI và provider. Một số mô hình không hỗ trợ tất cả options, đặc biệt những mô hình suy luận có quy tắc riêng.
- Temperature bằng 0 **không bảo đảm** kết quả hoàn toàn lặp lại.
- Giới hạn token quá thấp có thể cắt mất phán quyết hoặc khiến câu trả lời rỗng.
- Không nên thay default options trong lúc một regression suite đang chạy.

Với `ChatClient.Builder`, options mặc định được cấu hình qua `defaultOptions(...)`. Hãy dùng `ChatOptions` hoặc options riêng của provider theo API phiên bản đang sử dụng, rồi cố định chúng cho toàn bộ lượt chấm.

## 6. Khởi tạo evaluator trong Spring Boot

Có hai cách triển khai phổ biến; lựa chọn phụ thuộc số lượng model và yêu cầu quan sát.

### 6.1. Ứng dụng chỉ có một ChatModel

Spring Boot với Spring AI có thể auto-configure `ChatClient.Builder` dạng **prototype**, cho phép inject builder vào constructor hoặc `@Bean`.

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SimpleEvaluationConfig {

    @Bean
    RelevancyEvaluator relevancyEvaluator(ChatClient.Builder chatClientBuilder) {
        return new RelevancyEvaluator(chatClientBuilder);
    }
}
~~~

Khi sử dụng:

~~~java
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;
import org.springframework.stereotype.Service;

@Service
public class AnswerQualityService {

    private final RelevancyEvaluator evaluator;

    public AnswerQualityService(RelevancyEvaluator evaluator) {
        this.evaluator = evaluator;
    }

    public EvaluationResponse evaluate(EvaluationRequest request) {
        return evaluator.evaluate(request);
    }
}
~~~

Cách này có lợi khi `ChatClient.Builder` auto-configured đã được gắn các customizer/observability cần thiết. Nhưng bạn phải kiểm tra **các default đã được cấu hình trên builder** có phù hợp với judge hay không. Nếu dự án đăng ký advisor/tool mặc định toàn cục, cần phân tách builder cho evaluator thay vì dùng nguyên cấu hình đó.

### 6.2. Ứng dụng có answer model và judge model riêng

Nếu bạn đã cấu hình một bean `ChatModel` chuyên chấm với tên `judgeChatModel`, có thể inject tường minh:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JudgeEvaluationConfig {

    @Bean
    RelevancyEvaluator relevancyEvaluator(
            @Qualifier("judgeChatModel") ChatModel judgeModel) {

        ChatClient.Builder judgeBuilder = ChatClient.builder(judgeModel);
        return new RelevancyEvaluator(judgeBuilder);
    }
}
~~~

Ví dụ trên **giả định bean `judgeChatModel` đã tồn tại**. Nếu chưa đăng ký, ứng dụng sẽ không khởi động. `@Qualifier` giúp làm rõ lựa chọn khi có nhiều bean cùng kiểu `ChatModel`.

Lưu ý về **observability**: theo tài liệu Spring AI dành cho cấu hình nhiều model, tạo trực tiếp `ChatClient.builder(chatModel)` có thể bỏ qua một số customizer và hạ tầng quan sát mà builder auto-configured của Spring Boot sử dụng. Khi cần bảo toàn tracing/customizer cho client của judge, hãy áp dụng cơ chế `ChatClientBuilderConfigurer` được Spring AI cung cấp cho phiên bản bạn dùng. Hãy kiểm tra cấu hình thực tế thay vì giả định việc tạo builder thủ công tự động có đầy đủ traces.

Với nhiều `ChatModel`, Spring Boot còn có thể gặp lỗi **ambiguity** khi chọn bean mặc định. Hãy cấu hình qualifier/primary và builder tương ứng theo kiến trúc ứng dụng; không chọn ngẫu nhiên một model chỉ để giải quyết lỗi inject.

### 6.3. Quản lý vòng đời builder

Tạo `RelevancyEvaluator` một lần để tái sử dụng trong các lượt chấm thường hợp lý. Không cần tạo evaluator mới cho mọi case nếu model và rubric không đổi. Nhưng **đừng tiếp tục sửa một `ChatClient.Builder` đang được chia sẻ** với code khác sau khi đã truyền nó cho evaluator; vì implementation có thể gọi `build()` từ builder ở thời điểm đánh giá, thay đổi sau đó có thể tác động đến các lượt test.

Một quy ước dễ kiểm soát:

- Tạo builder judge tại nơi cấu hình.
- Gắn các tùy chọn chung, cần thiết ngay tại đó.
- Truyền builder vào evaluator.
- Dùng evaluator qua dependency injection.
- Đổi judge config bằng cấu hình/phiên bản rõ ràng, thay vì đột ngột mutate builder ở runtime.

## 7. Kiểm tra evaluator hoạt động sau khi khởi tạo

Khởi tạo thành công chỉ xác nhận object tồn tại. Bạn cần chạy một yêu cầu đánh giá để biết judge có được cấu hình đúng không.

Ví dụ ở một lớp tích hợp đã inject `RelevancyEvaluator`:

~~~java
import java.util.List;

import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;

public class RelevancyExample {

    private final RelevancyEvaluator evaluator;

    public RelevancyExample(RelevancyEvaluator evaluator) {
        this.evaluator = evaluator;
    }

    public boolean check() {
        String question = "Đơn hàng trực tuyến được đổi trả trong bao lâu?";

        List<Document> context = List.of(new Document(
                "Chính sách: đơn online có thể yêu cầu đổi trả " +
                "trong vòng 14 ngày từ ngày nhận hàng."));

        String answer = "Thời hạn yêu cầu đổi trả là 14 ngày kể từ khi nhận.";

        EvaluationRequest request =
                new EvaluationRequest(question, context, answer);

        EvaluationResponse result = evaluator.evaluate(request);

        return result.isPass();
    }
}
~~~

Đây là trường hợp **kỳ vọng đạt**, vì câu trả lời nêu chính xác thông tin mà ngữ cảnh cung cấp. Nhưng `isPass()` là phán quyết của **mô hình chấm đang chạy**, không thể khẳng định giá trị trước khi gọi model thật.

Trong Spring AI 2.1.x, `RelevancyEvaluator` diễn giải câu trả lời judge bằng cách loại khoảng trắng đầu/cuối rồi so sánh không phân biệt hoa thường với `YES`:

| Đầu ra văn bản của judge | Kết quả dự kiến trong implementation được mô tả |
| --- | --- |
| `YES` | `isPass() = true`, `getScore() = 1.0` |
| ` yes ` | `isPass() = true`, `getScore() = 1.0` |
| `NO` | `isPass() = false`, `getScore() = 0.0` |
| `YES, because the answer is relevant.` | `isPass() = false` vì có thêm chữ |
| `{"answer":"YES"}` | `isPass() = false` vì output là JSON |
| Chuỗi rỗng / câu trả lời không hợp lệ | Không đạt theo logic so sánh trên |

Điểm số này là **nhị phân**, không phải xác suất “đáp án đúng 100%”. Điều đó khiến rubric yêu cầu đầu ra đúng một từ có vai trò thiết yếu.

Trường hợp lỗi kết nối, hết quota, timeout, xác thực thất bại hoặc exception từ client **khác với một phán quyết `NO` hợp lệ**. Trong test runner, hãy lưu lỗi đó thành trạng thái **evaluation error** riêng để không làm méo tỷ lệ đạt.

## 8. Ví dụ integration test tối thiểu cho Spring Boot

Giả sử ứng dụng đã có bean `RelevancyEvaluator` từ `@Configuration` ở phần trên, cùng dependency test và quyền truy cập model judge:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class RelevancyEvaluatorIntegrationTest {

    @Autowired
    private RelevancyEvaluator relevancyEvaluator;

    @Test
    void relevantAnswerShouldPass() {
        EvaluationRequest request = new EvaluationRequest(
            "Chính sách đổi trả đơn online là bao nhiêu ngày?",
            List.of(new Document(
                "Người mua có thể yêu cầu đổi trả đơn online " +
                "trong 14 ngày kể từ lúc nhận hàng.")),
            "Đơn online có thời hạn yêu cầu đổi trả 14 ngày."
        );

        var evaluation = relevancyEvaluator.evaluate(request);

        assertThat(evaluation.isPass()).isTrue();
    }
}
~~~

Bài test phụ thuộc vào judge model bên ngoài, nên có thể **không ổn định 100%**, phát sinh phí và độ trễ. Nó cũng không chứng minh toàn bộ pipeline retrieval hoặc thế giới thực đã đúng; nó chỉ kiểm tra evaluator với bộ ba dữ liệu của một case.

Khi đưa evaluator vào kiểm thử RAG thực tế, thay `List.of(new Document(...))` bằng **các tài liệu thực sự được đưa cho generator** (ví dụ ngữ cảnh lấy từ metadata của `RetrievalAugmentationAdvisor`) và thay `responseContent` bằng **câu trả lời cuối của lượt RAG đó**. Không truy xuất tài liệu lần thứ hai chỉ để cấp cho judge, vì có thể làm lệch nguồn đã được sử dụng.

## 9. Tùy biến prompt: giữ rubric trong RelevancyEvaluator

Một `ChatClient.Builder` phù hợp chưa đủ nếu câu hỏi đánh giá không phản ánh mục tiêu nghiệp vụ. Spring AI hỗ trợ đặt rubric riêng thông qua `RelevancyEvaluator.Builder.promptTemplate(...)`.

Ví dụ trợ lý trả lời quy định nội bộ cần đúng câu hỏi và không mâu thuẫn với văn bản nguồn:

~~~java
PromptTemplate rubric = new PromptTemplate("""
    Bạn đang đánh giá độ phù hợp của một câu trả lời RAG.

    USER QUESTION:
    {query}

    ANSWER:
    {response}

    REFERENCE CONTEXT:
    {context}

    Trả lời YES khi nội dung câu trả lời giải quyết đúng câu hỏi,
    phù hợp thông tin tham chiếu và không mâu thuẫn nguồn.
    Nếu không, trả lời NO.

    Bắt buộc chỉ trả lời YES hoặc NO, không thêm ký tự khác.
    """);

RelevancyEvaluator evaluator = RelevancyEvaluator.builder()
        .chatClientBuilder(ChatClient.builder(judgeModel))
        .promptTemplate(rubric)
        .build();
~~~

Phần code trên giả định đã import `PromptTemplate`, `RelevancyEvaluator` và `ChatClient`, đồng thời `judgeModel` tồn tại trong ngữ cảnh chạy.

**Phân biệt ba loại cấu hình**:

| Cấu hình | Tác động |
| --- | --- |
| `ChatClient.Builder.defaultSystem(...)` | Thêm chỉ dẫn system mặc định cho các lời gọi bằng client được build |
| `ChatClient.Builder.defaultAdvisors(...)` | Áp dụng các advisor vào lời gọi của client |
| `RelevancyEvaluator.Builder.promptTemplate(...)` | Xác định **nội dung prompt chấm** dùng ba placeholder `{query}`, `{response}`, `{context}` |

Nếu đã có rubric chuyên dụng, không nên gắn một system prompt mặc định kiểu “Bạn là trợ lý bán hàng, hãy tư vấn sản phẩm” vào judge builder. Nó có thể khiến mô hình trả lời câu hỏi thay vì chỉ đánh giá.

Nếu yêu cầu đánh giá mở rộng thành “chứng minh từng khẳng định được nguồn hỗ trợ”, cân nhắc dùng thêm `FactCheckingEvaluator` hoặc một rubric đánh giá grounding thích hợp. `RelevancyEvaluator` trước hết trả về tín hiệu **mức độ phù hợp**, không thay thế tất cả phép đo độ chính xác.

## 10. Quan sát chi phí, độ trễ và kết quả của judge

Khởi tạo builder của judge còn liên quan tới hạ tầng đo lường. Mỗi lượt `evaluate(...)` dùng mô hình để chấm; nó có thể tạo thêm request, token và latency ngoài chi phí sinh câu trả lời.

Ví dụ một hệ thống RAG đo:

~~~text
request_id = rag-eval-0127
answer_model = model-A
judge_model = model-J
prompt_version = answer-prompt-08
judge_prompt_version = relevancy-rubric-03
dataset_version = return-policy-test-v04

retrieval_latency_ms = 120
generation_latency_ms = 840
evaluation_latency_ms = 410
relevancy_pass = true
~~~

Đây là một **ví dụ định dạng record quan sát**, không phải metric/tên thuộc tính được Spring AI tự động sinh đúng như vậy. Tùy cấu hình Micrometer/Observation và provider, bạn có thể thu được các span, token usage và metadata khác nhau. Cần xác minh thực tế trên ứng dụng trước khi dựa vào một trường metric cụ thể.

Nên ghi nhận, ở nơi phù hợp với chính sách dữ liệu:

- ID case, phiên bản dataset, prompt trả lời, model trả lời và pipeline RAG.
- Phiên bản judge model, judge rubric và options (nếu có).
- Trạng thái `PASS`, `FAIL` hoặc `EVALUATION_ERROR` cùng lý do lỗi nếu khả dụng.
- Độ trễ của retrieval, generation, judge; token usage và chi phí ước tính tương ứng.
- ID của tài liệu hỗ trợ thực sự được gửi vào evaluator, có thể kèm hash hoặc version.

Nếu sau khi nâng answer model, pass rate giảm nhưng judge model và rubric giữ nguyên, các trace và document ID giúp phân biệt lỗi **retrieval**, **generation** và tình trạng judge không ổn định. Nếu **cùng lúc đổi judge**, kết quả hai lần chấm không còn dùng cùng thước đo: cần đối chiếu lại tập mẫu chuẩn.

Tách chi phí judge ra khỏi chi phí phục vụ người dùng giúp bạn không tính nhầm tăng latency hoặc token do kiểm thử thành vấn đề của model trả lời. Trong production, có thể chạy đánh giá theo mẫu, trong batch hoặc ngoài đường xử lý đồng bộ để kiểm soát tài nguyên.

## 11. Các lỗi khi khởi tạo và cách xử lý

| Hiện tượng | Khả năng cao | Cách kiểm tra |
| --- | --- | --- |
| Java báo constructor không nhận `ChatClient` | Truyền object từ `build()` thay vì builder | Dùng `new RelevancyEvaluator(ChatClient.builder(judgeModel))` |
| Lỗi “chatClientBuilder cannot be null” | Truyền `null` hoặc quên cấu hình evaluator builder | Cung cấp `.chatClientBuilder(...)` trước `build()` |
| Spring Boot báo nhiều bean `ChatModel` | Không phân biệt answer model và judge model | Dùng `@Qualifier` hoặc cấu hình bean phù hợp |
| Mọi case gần như đều fail | Judge trả giải thích/JSON thay vì `YES` | Kiểm tra rubric và đầu ra judge; chỉ nhận một từ |
| Judge gọi retrieval/tool không mong muốn | Builder mang advisor hoặc default tools của ứng dụng | Dùng cấu hình judge riêng |
| Chạy local có trace nhưng judge không có span | Builder được tạo thủ công bỏ qua customizer/observability | Kiểm tra `ChatClientBuilderConfigurer`, registry và cấu hình provider |
| Test chậm hơn sau khi bật đánh giá | Mỗi case thêm một lời gọi LLM judge | Đo latency theo giai đoạn, giới hạn batch/concurrency |
| Một case thay đổi nhãn giữa các lần chạy | Judge model, options/rubric hoặc provider thay đổi | Cố định phiên bản và ghi lại nhãn cùng dữ liệu đầu vào |
| Judge đánh đạt dù câu trả lời chứa chi tiết bịa | Rubric relevance quá rộng hoặc thiếu phép kiểm groundedness | Kết hợp fact checking và nhãn kiểm tra con người |

### Checklist trước khi dùng evaluator trong regression suite

1. **Đúng mô hình:** xác nhận builder gắn với judge model được chọn, không dùng nhầm model trả lời.
2. **Đúng hành vi client:** không có default advisor, chat memory, tool hoặc system prompt có thể làm biến dạng lượt chấm.
3. **Đúng rubric:** template có `{query}`, `{response}` và `{context}`; yêu cầu output `YES`/`NO`.
4. **Đúng dữ liệu:** `EvaluationRequest` khớp câu hỏi, tài liệu hỗ trợ và phản hồi của **cùng lượt chạy**.
5. **Đúng cách ghi nhận:** tách kết quả judge từ lỗi kỹ thuật và lưu phiên bản judge/rubric/dataset.
6. **Đúng giới hạn vận hành:** theo dõi token, quota, timeout, retry, latency và chi phí judge.
7. **Đúng chính sách dữ liệu:** loại bỏ hoặc che thông tin nhạy cảm trước khi gửi judge bên ngoài hay ghi logs/traces.

## 12. Bài tập thực hành

### Bài tập 1: so sánh hai cách khởi tạo

Viết hai đoạn code tạo `RelevancyEvaluator` từ cùng `judgeModel`:

- Constructor trực tiếp: `new RelevancyEvaluator(ChatClient.builder(judgeModel))`.
- Builder của evaluator: `RelevancyEvaluator.builder().chatClientBuilder(...).build()`.

Dùng cùng một `EvaluationRequest`; xác định điểm giống và khác của hai cách khi không có template tùy chỉnh.

### Bài tập 2: xác định builder bị nhiễu

Giả sử ứng dụng có `answerClient` đã dùng `QuestionAnswerAdvisor` và `MessageChatMemoryAdvisor`. Giải thích vì sao lấy builder từ client đó để làm judge có thể gây sai lệch. Sau đó viết `@Bean` riêng cho evaluator dùng `judgeChatModel`.

### Bài tập 3: kiểm soát định dạng output

Tạo một rubric tiếng Việt yêu cầu đúng một từ `YES` hoặc `NO`. Chạy thử một trường hợp khớp ngữ cảnh và một trường hợp lạc đề. Ghi rõ lần nào judge tạo output không đúng định dạng, nếu có; tách lỗi định dạng khỏi nhận định về chất lượng câu trả lời.

### Bài tập 4: chấm RAG qua các phiên bản

Chuẩn bị một tập tối thiểu 10 case có nhãn tham chiếu. Chạy hai phiên bản answer prompt với **cùng judge model và rubric**. Lưu `caseId`, pass/fail, model version, prompt version, latency và token usage của lượt chấm. Phân tích ít nhất hai case đổi trạng thái, đối chiếu với tài liệu hỗ trợ từng lượt.

## 13. Tổng kết

`RelevancyEvaluator` cần một **`ChatClient.Builder` cấu hình cho vai trò judge**. Cách đơn giản nhất là `new RelevancyEvaluator(ChatClient.builder(judgeModel))`; khi cần rubric riêng, dùng `RelevancyEvaluator.builder().chatClientBuilder(...).promptTemplate(...).build()`.

Giữ model chấm, rubric và nguồn dữ liệu nhất quán giữa các lần chạy giúp phép đo relevance có giá trị khi so sánh các bản prompt/model/pipeline. Tách builder của judge khỏi advisor, tools và system prompt của trợ lý; đồng thời theo dõi chi phí, token và độ trễ của chính lượt đánh giá để xác định nguyên nhân suy giảm chất lượng một cách có căn cứ.

## Tài liệu tham khảo

- [Spring AI Reference — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): `RelevancyEvaluator`, `EvaluationRequest`, prompt mặc định và custom prompt.
- [Spring AI Reference — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html): tạo `ChatClient.Builder`, cấu hình mặc định và dùng nhiều model.
- [Spring AI API — RelevancyEvaluator.Builder](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/evaluation/RelevancyEvaluator.Builder.html): `chatClientBuilder(...)`, `promptTemplate(...)` và `build()`.
- [Spring AI source — RelevancyEvaluator.java](https://github.com/spring-projects/spring-ai/blob/main/spring-ai-client-chat/src/main/java/org/springframework/ai/chat/evaluation/RelevancyEvaluator.java): cơ chế build client, render prompt và diễn giải `YES`/`NO`.
