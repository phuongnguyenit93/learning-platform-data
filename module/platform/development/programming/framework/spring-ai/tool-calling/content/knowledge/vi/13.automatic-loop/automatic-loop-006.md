# Thứ tự advisor và thành phần nằm trong hoặc ngoài vòng lặp

Khi dùng tool calling với `ChatClient`, một yêu cầu của người dùng có thể tạo ra nhiều lượt gọi mô hình: mô hình yêu cầu công cụ, ứng dụng thực thi công cụ, kết quả được gửi lại mô hình, rồi mô hình tiếp tục cho đến khi tạo câu trả lời cuối cùng. Trong Spring AI 2.0 trở đi, `ToolCallingAdvisor` quản lý chu trình này ngay trong advisor chain. Vì vậy, thứ tự advisor quyết định advisor nào chạy một lần cho toàn bộ request và advisor nào chạy lại ở từng lượt của vòng tool calling.

Để đặt advisor đúng vị trí, cần hiểu `ToolCallingAdvisor` là ranh giới của vòng lặp. Advisor có order nhỏ hơn ranh giới chạy ở bên ngoài; advisor có order lớn hơn được đặt phía sau ranh giới và chạy trong mỗi iteration. Sự khác biệt này ảnh hưởng trực tiếp đến cách nạp/lưu memory, thực hiện RAG, ghi log, đo metric và bổ sung prompt.

## Trước tiên cần phân biệt Spring AI 1.x và 2.0+

Kiến trúc tool calling thay đổi đáng kể giữa hai dòng phiên bản. Không thể áp dụng cùng một cách diễn giải advisor order cho cả hai.

| Phiên bản | Vòng tool calling nằm ở đâu? | Advisor có thể chạy giữa các lượt tool call không? |
| --- | --- | --- |
| Spring AI 1.0.x | Bên trong từng implementation của `ChatModel`, sử dụng `ToolCallingManager` | Không. Advisor chain của `ChatClient` bao quanh một lần gọi `ChatModel`; các lượt gọi mô hình nội bộ diễn ra bên trong lần gọi đó. |
| Spring AI 2.0 trở đi | Trong advisor chain, do `ToolCallingAdvisor` quản lý | Có. Advisor nằm sau `ToolCallingAdvisor` được gọi lại khi advisor này lặp qua các lượt. |

Ở Spring AI 1.x, `ChatModel` tự kiểm tra phản hồi có tool call, nhờ `ToolCallingManager` thực thi callback, thêm kết quả vào lịch sử và gọi mô hình tiếp. Advisor của `ChatClient` chỉ thấy request trước khi đi vào `ChatModel` và response sau khi toàn bộ vòng nội bộ kết thúc. Nếu cần quan sát từng lượt trong 1.x, phải dùng user-controlled tool execution hoặc một cơ chế điều phối riêng.

Từ Spring AI 2.0, `ToolCallingAdvisor` đưa vòng lặp vào advisor chain. `ChatClient` tự đăng ký advisor này khi có công cụ, trừ khi ứng dụng tắt auto-registration. Khi gọi `ChatModel` trực tiếp ở kiến trúc mới, model trả về phản hồi thô có thể chứa tool call; caller phải tự thực thi công cụ và gọi model tiếp, hoặc dùng `ChatClient` để có vòng lặp tự động.

Phần còn lại tập trung vào mô hình `ToolCallingAdvisor` của Spring AI 2.0+. Khi bảo trì dự án Spring AI 1.x, hãy dùng phần so sánh trên để hiểu vì sao advisor order không thể đặt một advisor vào giữa các lượt gọi nội bộ của `ChatModel`.

## Vòng lặp do ToolCallingAdvisor quản lý

`ToolCallingAdvisor` là một recursive advisor. Nó gọi phần advisor chain nằm phía sau nó, kiểm tra phản hồi của mô hình, thực thi tool call nếu có và gọi lại phần chain phía sau với lịch sử đã cập nhật. Chu trình dừng khi phản hồi không còn tool call đủ điều kiện thực thi, hoặc khi có điều kiện kết thúc như công cụ `returnDirect`.

Một vòng điển hình:

1. `ChatClient` tạo request và bắt đầu advisor chain.
2. Các advisor bên ngoài chuẩn bị request, chẳng hạn nạp memory hoặc kiểm tra metadata.
3. `ToolCallingAdvisor` bắt đầu vòng lặp và gọi các advisor nằm phía sau nó.
4. Advisor cuối cùng của framework gửi prompt đến `ChatModel`.
5. Nếu mô hình trả về tool call, `ToolCallingAdvisor` chuyển yêu cầu cho `ToolCallingManager`.
6. `ToolCallingManager` phân giải `ToolCallback`, thực thi callback và thu thập kết quả.
7. `ToolCallingAdvisor` thêm yêu cầu gọi công cụ cùng kết quả vào lịch sử, rồi gọi lại phần advisor chain phía sau nó.
8. Khi mô hình trả về câu trả lời không còn tool call, `ToolCallingAdvisor` kết thúc vòng và trả response về các advisor bên ngoài.

```mermaid
sequenceDiagram
    actor User as Người dùng
    participant Client as ChatClient
    participant Outer as Advisor ngoài vòng lặp
    participant Loop as ToolCallingAdvisor
    participant Inner as Advisor trong vòng lặp
    participant Model as ChatModel
    participant Manager as ToolCallingManager
    participant Callback as ToolCallback

    User->>Client: Gửi yêu cầu
    Client->>Outer: ChatClientRequest
    Outer->>Loop: Request đã chuẩn bị
    Loop->>Inner: Iteration 1
    Inner->>Model: Prompt + tool definitions
    Model-->>Inner: Tool call
    Inner-->>Loop: ChatClientResponse
    Loop->>Manager: Thực thi tool call
    Manager->>Callback: Gọi callback
    Callback-->>Manager: Tool result
    Manager-->>Loop: ToolExecutionResult
    Loop->>Inner: Iteration 2 + lịch sử tool
    Inner->>Model: Prompt đã cập nhật
    Model-->>Inner: Câu trả lời cuối
    Inner-->>Loop: Final response
    Loop-->>Outer: Final response
    Outer-->>Client: ChatClientResponse
    Client-->>User: Câu trả lời
```

`ToolCallingAdvisor` là ranh giới giữa hai vùng advisor. `ToolCallingManager` và `ToolCallback` được gọi bên trong chu trình, ở khoảng giữa hai lần gọi mô hình. Chúng không phải advisor trong chain, nhưng là thành phần thực thi được vòng lặp sử dụng.

## Quy tắc order: thấp hơn ở ngoài, cao hơn ở trong

Advisor chain của Spring AI được sắp xếp theo `getOrder()`:

- Giá trị order nhỏ hơn có precedence cao hơn và xử lý request trước.
- Advisor chain có cách hoạt động như stack: advisor vào trước xử lý response sau cùng.
- Nếu hai advisor có cùng order, thứ tự thực thi không được bảo đảm.

Trong Spring AI 2.0+, `ToolCallingAdvisor` mặc định có order `Ordered.HIGHEST_PRECEDENCE + 300`. Vì nó tạo một chain con chỉ gồm các advisor đứng sau nó, có thể phân chia như sau:

| Order tương đối | Vị trí | Hành vi |
| --- | --- | --- |
| Nhỏ hơn `ToolCallingAdvisor` | Ngoài vòng lặp | Chạy một lần trước vòng; xử lý response cuối sau khi vòng kết thúc. |
| Bằng `ToolCallingAdvisor` | Không nên dùng | Thứ tự không được bảo đảm khi các advisor có cùng order. |
| Lớn hơn `ToolCallingAdvisor` | Trong vòng lặp | Chạy lại ở mỗi iteration của vòng tool calling. |

Ví dụ với các offset mặc định:

```java
Ordered.HIGHEST_PRECEDENCE + 200  // advisor ngoài vòng lặp
Ordered.HIGHEST_PRECEDENCE + 300  // ToolCallingAdvisor mặc định
Ordered.HIGHEST_PRECEDENCE + 400  // advisor trong vòng lặp
```

`HIGHEST_PRECEDENCE` có giá trị số nhỏ nhất. Do đó `+200` vẫn nhỏ hơn `+300`, còn `+400` lớn hơn `+300`. Không nên đọc các con số này như mức ưu tiên càng lớn càng chạy trước; trong Spring `Ordered`, số nhỏ hơn mới có precedence cao hơn.

Một advisor ngoài vòng có thể sửa prompt trước khi vòng bắt đầu và xử lý kết quả cuối cùng sau khi vòng kết thúc. Advisor trong vòng nhận request/response của từng iteration; nó có thể quan sát từng lần gọi mô hình, bổ sung dữ liệu theo từng lượt hoặc ghi metric riêng cho từng lượt.

## Thành phần nào nằm trong và ngoài vòng lặp?

| Thành phần | Vị trí thường gặp | Lý do |
| --- | --- | --- |
| `ChatClient` request và response | Bao ngoài toàn bộ chain | Đại diện cho một lượt tương tác của ứng dụng. |
| Advisor có order nhỏ hơn `ToolCallingAdvisor` | Ngoài | Chuẩn bị request một lần và xử lý response cuối một lần. |
| `ToolCallingAdvisor` | Ranh giới vòng lặp | Quyết định khi nào thực thi tool call và gọi iteration tiếp theo. |
| Advisor có order lớn hơn `ToolCallingAdvisor` | Trong | Được gọi lại cho mỗi model iteration. |
| Advisor cuối gửi request đến `ChatModel` | Trong | Mỗi iteration cần một lần gọi mô hình. |
| `ToolCallingManager` | Trong, giữa các model iteration | Phân giải và thực thi tool call từ response. |
| `ToolCallback` | Trong, khi có tool call | Chạy logic công cụ và trả kết quả cho manager. |
| `ChatMemory` | Tùy order của memory advisor | Có thể chỉ nạp/lưu lịch sử cuối cùng hoặc xử lý cả tool transcript theo từng iteration. |

Không phải mọi request đều chạy nhiều iteration. Nếu mô hình trả lời trực tiếp, advisor trong vòng chỉ chạy một lần. Nếu mô hình gọi công cụ nhiều lượt liên tiếp, advisor trong vòng sẽ được gọi lại theo từng lượt mô hình. Nếu công cụ có `returnDirect = true`, vòng có thể dừng ngay sau khi công cụ trả kết quả.

## Advisor ngoài vòng: nạp memory một lần, lưu kết quả cuối

`MessageChatMemoryAdvisor` mặc định có order `Ordered.HIGHEST_PRECEDENCE + 200`, nhỏ hơn order mặc định của `ToolCallingAdvisor` là `+300`. Vì vậy, memory advisor mặc định nằm ngoài vòng lặp.

Hành vi của memory ngoài vòng:

1. Nạp lịch sử hội thoại trước khi model được gọi lần đầu.
2. Chuyển prompt đã có lịch sử vào vòng tool calling.
3. Không nhìn thấy các tool call request và tool response trung gian.
4. Khi vòng lặp hoàn tất, lưu user message và assistant response cuối cùng.

Trong cấu hình này, `ToolCallingAdvisor` tự quản lý lịch sử trung gian bên trong vòng. Đây là cấu hình phù hợp nếu repository của memory không cần lưu các message đặc biệt như `AssistantMessage` có tool call và `ToolResponseMessage`.

Ví dụ cấu hình để memory ở ngoài vòng:

```java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.advisor.MessageChatMemoryAdvisor;
import org.springframework.ai.chat.client.advisor.ToolCallingAdvisor;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
class ChatClientConfiguration {

    @Bean
    ChatClient chatClient(ChatModel chatModel, ChatMemory chatMemory) {
        var memoryAdvisor = MessageChatMemoryAdvisor.builder(chatMemory)
                .order(Ordered.HIGHEST_PRECEDENCE + 200)
                .build();

        var toolCallingAdvisor = ToolCallingAdvisor.builder()
                .advisorOrder(Ordered.HIGHEST_PRECEDENCE + 300)
                .build();

        return ChatClient.builder(chatModel)
                .defaultAdvisors(memoryAdvisor, toolCallingAdvisor)
                .build();
    }
}
```

Đây là cách cấu hình tường minh để nhìn thấy ranh giới order. Trong ứng dụng Spring Boot, `ChatClient` thường tự đăng ký `ToolCallingAdvisor` khi có tool; phần lớn ứng dụng không cần tự tạo advisor này nếu chấp nhận mặc định. Khi tự cấu hình, hãy bảo đảm chỉ có một `ToolAdvisor` trong chain.

Ví dụ trên dùng builder API `.order(...)` của `MessageChatMemoryAdvisor` trong Spring AI 2.1. Một số bản 2.0 dùng tên `.advisorOrder(...)` cho builder này. Hãy dùng đúng tên phương thức của minor version trong dự án; quy tắc so sánh order với `ToolCallingAdvisor` không thay đổi.

## Advisor trong vòng: quan sát từng iteration

Đặt advisor với order lớn hơn `ToolCallingAdvisor` khi cần chạy logic ở từng lượt gọi mô hình. Ví dụ, một advisor audit có thể ghi nhận số iteration, thời gian gọi mô hình, số tool call được trả về hoặc trạng thái sau khi mỗi lượt kết thúc.

```java
import org.springframework.ai.chat.client.advisor.api.CallAdvisor;
import org.springframework.ai.chat.client.advisor.api.CallAdvisorChain;
import org.springframework.ai.chat.client.ChatClientRequest;
import org.springframework.ai.chat.client.ChatClientResponse;
import org.springframework.core.Ordered;

public final class IterationAuditAdvisor implements CallAdvisor {

    private final ToolIterationAudit audit;

    public IterationAuditAdvisor(ToolIterationAudit audit) {
        this.audit = audit;
    }

    @Override
    public String getName() {
        return "iterationAuditAdvisor";
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE + 400;
    }

    @Override
    public ChatClientResponse adviseCall(
            ChatClientRequest request,
            CallAdvisorChain chain) {

        long startedAt = System.nanoTime();
        ChatClientResponse response = chain.nextCall(request);

        this.audit.recordIteration(
                request.prompt(),
                response.chatResponse(),
                System.nanoTime() - startedAt);

        return response;
    }
}
```

`ToolIterationAudit` là service audit do ứng dụng định nghĩa. Ví dụ chỉ minh họa vị trí advisor và điểm có thể quan sát request/response; khi triển khai cần tránh ghi prompt, arguments hoặc kết quả chứa dữ liệu nhạy cảm. Vì class chỉ triển khai `CallAdvisor`, nó áp dụng cho `.call()`. Nếu ứng dụng sử dụng `.stream()`, hãy triển khai thêm `StreamAdvisor` để quan sát luồng streaming tương ứng.

Advisor trong vòng có thể dùng cho:

- Ghi metric và tracing riêng cho từng lần gọi mô hình.
- Ghi nhận tool call request và tool response ở dạng đã lọc.
- Bổ sung hoặc chuẩn hóa prompt trước mỗi iteration.
- Cập nhật danh sách tool khả dụng theo trạng thái của workflow, nếu chính sách cho phép.
- Kiểm tra response của từng lượt trước khi vòng lặp quyết định tiếp tục.

Khi dùng advisor trong vòng, hãy nhớ nó có thể chạy nhiều lần trong một request. Không đặt thao tác chỉ được thực hiện một lần như tạo giao dịch, gửi email hoặc tăng bộ đếm nghiệp vụ không idempotent vào đoạn code sẽ bị gọi lại mỗi iteration.

## Đặt memory vào trong vòng lặp

Có trường hợp memory phải nhìn thấy toàn bộ tool transcript. Ví dụ, ứng dụng muốn lưu từng tool call và kết quả để lần hội thoại sau có thể xem lại công cụ nào đã được gọi, hoặc muốn memory advisor tự xây dựng prompt cho mỗi iteration.

Để memory advisor chạy trong vòng, đặt order lớn hơn `ToolCallingAdvisor`, ví dụ `Ordered.HIGHEST_PRECEDENCE + 400`:

```java
var toolCallingAdvisor = ToolCallingAdvisor.builder()
        .advisorOrder(Ordered.HIGHEST_PRECEDENCE + 300)
        .disableInternalConversationHistory()
        .build();

var memoryAdvisor = MessageChatMemoryAdvisor.builder(chatMemory)
        .order(Ordered.HIGHEST_PRECEDENCE + 400)
        .build();

ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultAdvisors(toolCallingAdvisor, memoryAdvisor)
        .build();
```

Khi memory advisor ở trong vòng, cần tránh để cả memory advisor và `ToolCallingAdvisor` cùng quản lý, ghi lại lịch sử iteration. Vì vậy, khi tự tạo `ToolCallingAdvisor`, gọi `.disableInternalConversationHistory()` để advisor chỉ chuyển phần thông điệp phù hợp xuống chain và để memory advisor quản lý lịch sử theo từng lượt.

Nếu dùng `ToolCallingAdvisor` auto-registered bởi `DefaultChatClient`, framework có thể nhận biết `MemoryAdvisor` được đặt bên trong vòng và tự tắt internal history. Hành vi tự động này phụ thuộc phiên bản; nếu tự xây dựng advisor hoặc thay thế builder, hãy cấu hình rõ ràng và kiểm tra tài liệu của minor version đang dùng.

Memory repository cũng phải hỗ trợ lưu các message của tool calling. Nếu repository chỉ hỗ trợ user/assistant text đơn giản, việc đưa memory vào trong vòng có thể làm mất hoặc không xử lý đúng tool call request và tool response. Hãy xác nhận khả năng lưu các message này trước khi đổi order.

## Chọn vị trí cho các advisor phổ biến

| Loại advisor | Vị trí gợi ý | Khi nào chọn vị trí đó? |
| --- | --- | --- |
| Chat memory | Ngoài vòng theo mặc định | Chỉ cần nạp lịch sử trước request và lưu câu trả lời cuối. |
| Chat memory | Trong vòng | Cần lưu và khôi phục từng tool call cùng tool response. |
| Audit tổng thể request | Ngoài vòng | Cần một bản ghi cho toàn bộ yêu cầu và kết quả cuối cùng. |
| Metric theo model iteration | Trong vòng | Cần đo riêng từng lần gọi mô hình. |
| RAG/retrieval advisor | Ngoài vòng | Chỉ cần truy xuất một lần và dùng kết quả xuyên suốt vòng. |
| RAG/retrieval advisor | Trong vòng | Mỗi iteration cần truy xuất lại dựa trên tool result hoặc ngữ cảnh mới. |
| Prompt normalization | Ngoài vòng | Chuẩn hóa một lần trước khi bắt đầu xử lý. |
| Prompt augmentation theo iteration | Trong vòng | Bổ sung hướng dẫn hoặc dữ liệu thay đổi sau từng tool call. |
| Kiểm tra kết quả cuối | Ngoài vòng | Chỉ cần kiểm tra câu trả lời hoàn chỉnh. |
| Kiểm tra từng model response | Trong vòng | Cần chặn hoặc sửa response ở mỗi iteration trước khi tiếp tục. |

Không có vị trí tốt cho mọi advisor. Hãy xác định dữ liệu advisor cần quan sát và số lần nó phải chạy. Nếu advisor cần biết tool call trung gian, đặt nó trong vòng. Nếu advisor chỉ cần request đầu vào và kết quả cuối, đặt ngoài vòng để tránh chạy lặp không cần thiết.

## Điều chỉnh ranh giới bằng cấu hình

Spring Boot cho phép điều chỉnh vị trí auto-registered `ToolCallingAdvisor` bằng property:

```yaml
spring:
  ai:
    chat:
      client:
        tool-calling:
          advisor-order: -2147483348
```

Giá trị trên tương đương `Ordered.HIGHEST_PRECEDENCE + 300` trong Java. Trong cấu hình thực tế, nên giữ một hằng số hoặc chú thích giải thích phép tính thay vì rải số âm khó đọc trong nhiều file. Advisor muốn chạy ngoài phải có order nhỏ hơn giá trị ranh giới; advisor muốn chạy trong phải có order lớn hơn.

Nếu thay đổi `advisor-order`, hãy xem lại tất cả advisor đang có. Ví dụ, nếu chuyển ranh giới từ `+300` xuống `+100`, memory advisor mặc định `+200` sẽ từ vị trí ngoài chuyển vào trong vòng. Một thay đổi order có thể làm đổi số lần gọi advisor và cách memory lưu lịch sử dù không sửa code của advisor đó.

Có thể tắt auto-registration toàn cục:

```yaml
spring:
  ai:
    chat:
      client:
        tool-calling:
          enabled: false
```

Hoặc tắt cho một request:

```java
String response = chatClient.prompt("Tra cứu đơn hàng")
        .tools(orderTools)
        .advisors(AdvisorParams.toolCallingAdvisorAutoRegister(false))
        .call()
        .content();
```

Khi tắt `ToolCallingAdvisor`, tool definitions vẫn có thể được gửi đến mô hình, nhưng các tool call trong response sẽ không tự được thực thi bởi advisor. Ứng dụng phải tự kiểm tra response, gọi `ToolCallingManager` và gửi kết quả trở lại mô hình, hoặc dùng một `ToolAdvisor` tùy chỉnh thay thế.

## Trường hợp gọi ChatModel trực tiếp

Khi ứng dụng gọi `ChatModel` trực tiếp, không có `ChatClient` advisor chain và cũng không có ranh giới order của `ToolCallingAdvisor`. Ứng dụng nhận `ChatResponse`, kiểm tra `hasToolCalls()`, gọi `ToolCallingManager.executeToolCalls(...)`, tạo prompt mới từ conversation history rồi gọi model tiếp.

```java
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.model.tool.ToolCallingChatOptions;
import org.springframework.ai.model.tool.ToolCallingManager;
import org.springframework.ai.model.tool.ToolExecutionResult;
import org.springframework.ai.support.ToolCallbacks;

ToolCallingManager toolCallingManager = ToolCallingManager.builder().build();

ChatOptions options = ToolCallingChatOptions.builder()
        .toolCallbacks(ToolCallbacks.from(new OrderTools()))
        .build();

Prompt prompt = new Prompt("Tra cứu đơn hàng ORD-100", options);
ChatResponse response = chatModel.call(prompt);

while (response.hasToolCalls()) {
    ToolExecutionResult execution = toolCallingManager.executeToolCalls(prompt, response);
    prompt = new Prompt(execution.conversationHistory(), options);
    response = chatModel.call(prompt);
}

String answer = response.getResult().getOutput().getText();
```

Trong cách này, vòng lặp do code ứng dụng điều khiển. Ví dụ giả định các tool không dùng `returnDirect`; nếu có, ứng dụng cần kiểm tra `execution.returnDirect()` và trả kết quả tool theo hợp đồng của mình thay vì gọi model thêm. Nếu cần logging, memory hoặc validation ở từng iteration, hãy đặt các bước đó trực tiếp trong vòng `while` hoặc xây dựng một orchestrator riêng. Không thể mong đợi `getOrder()` của `ChatClient` advisor tác động đến lời gọi `ChatModel` độc lập.

## ReturnDirect và điều kiện kết thúc vòng

Mặc định, kết quả tool được gửi lại mô hình dưới dạng `ToolResponseMessage` để mô hình tiếp tục suy luận. Nếu tool có metadata `returnDirect = true`, `ToolCallingAdvisor` có thể trả kết quả tool trực tiếp về client và kết thúc vòng mà không gọi mô hình thêm.

Điều này ảnh hưởng đến advisor trong vòng: advisor chỉ chạy ở các iteration thực sự được thực hiện. Không nên giả định luôn có một lượt mô hình sau callback. Nếu cần audit thao tác tool dù kết quả được trả trực tiếp, hãy ghi nhận ngay tại callback hoặc một thành phần quan sát tool execution, không chỉ dựa vào advisor xử lý response cuối.

`ToolCallingAdvisor` mặc định tiếp tục khi response có tool calls. Có thể tùy chỉnh `ToolExecutionEligibilityChecker` để áp dụng điều kiện bổ sung, chẳng hạn kiểm tra finish reason của provider. Khi thay đổi điều kiện, cần kiểm thử cả trường hợp response có tool call nhưng không được phép tiếp tục vòng.

## Streaming và advisor order

`ToolCallingAdvisor` hỗ trợ cả `CallAdvisor` và `StreamAdvisor`. Nếu ứng dụng dùng `.stream()`, advisor quan sát từng iteration cần triển khai phần streaming tương ứng. Một class chỉ triển khai `CallAdvisor` sẽ không tự động quan sát đường stream.

Theo mặc định, ứng dụng thường chỉ nhận luồng kết quả cuối sau khi các iteration tool calling hoàn tất. Nếu cần phát các chunk trung gian của từng iteration, cấu hình streaming tool-call responses theo khả năng của phiên bản Spring AI đang dùng. Khi quan sát stream, cần phân biệt chunk của lần gọi mô hình với tool call/result; không coi mỗi chunk là một iteration hoàn chỉnh.

Với advisor stream, xử lý response thường cần aggregate các chunk của một iteration trước khi quyết định có tool call hay không. Điều này đặc biệt quan trọng khi tự điều khiển vòng lặp ở tầng `ChatModel`.

## Kiểm thử thứ tự và số lần advisor chạy

Nên kiểm thử bằng một model giả hoặc một chuỗi response cố định để tránh phụ thuộc vào quyết định ngẫu nhiên của mô hình thật. Tạo kịch bản gồm hai tool call iteration rồi một response cuối:

| Thành phần | Số lần mong đợi |
| --- | ---: |
| Advisor ngoài vòng | 1 lần vào request và 1 lần xử lý response cuối |
| `ToolCallingAdvisor` | 1 lần quản lý toàn bộ vòng |
| Advisor trong vòng | 3 lần, tương ứng 3 lần gọi mô hình |
| `ChatModel` | 3 lần |
| `ToolCallingManager` | 2 lần nếu mỗi iteration đầu có tool call |
| `ToolCallback` | Theo số tool call thực tế; ví dụ 2 lần |

Các kiểm thử quan trọng:

1. Xác nhận advisor có order thấp hơn `ToolCallingAdvisor` chỉ chạy một lần cho một request.
2. Xác nhận advisor có order cao hơn chạy lại ở mỗi iteration.
3. Xác nhận advisor cùng order không được dùng làm cơ sở cho thứ tự xác định.
4. Xác nhận memory ngoài vòng chỉ lưu user message và assistant response cuối theo cấu hình.
5. Xác nhận memory trong vòng nhận được tool call request và tool response; internal history của `ToolCallingAdvisor` được tắt khi cần.
6. Xác nhận `returnDirect` kết thúc vòng và không phát sinh model iteration tiếp theo.
7. Xác nhận tắt auto-registration khiến tool call không được thực thi tự động.
8. Xác nhận đường `.stream()` dùng advisor triển khai `StreamAdvisor` và xử lý đúng response của từng iteration.
9. Xác nhận gọi `ChatModel` trực tiếp không vô tình phụ thuộc vào `ChatClient` advisor chain.

Một test đơn giản có thể dùng counter trong advisor:

```java
AtomicInteger outerCalls = new AtomicInteger();
AtomicInteger innerCalls = new AtomicInteger();

// Outer advisor: getOrder() = HIGHEST_PRECEDENCE + 200
// Inner advisor: getOrder() = HIGHEST_PRECEDENCE + 400

// Sau một request giả lập có hai tool-call rounds và một final response:
assertThat(outerCalls).hasValue(1);
assertThat(innerCalls).hasValue(3);
```

Counter chỉ là cách minh họa. Test tích hợp nên kiểm tra thêm prompt ở từng iteration, tool response được nối đúng lịch sử và các advisor không làm thay đổi thứ tự message ngoài dự kiến.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Advisor logging chỉ ghi một response cuối | Advisor đang nằm ngoài `ToolCallingAdvisor` | Tăng order để đưa advisor vào phần chain được lặp, nếu cần quan sát từng iteration. |
| Memory không lưu tool call message | Memory advisor nằm ngoài vòng | Đưa memory advisor vào trong vòng và dùng repository hỗ trợ tool messages. |
| Memory ghi lịch sử trùng lặp | Memory advisor trong vòng cùng với internal history của `ToolCallingAdvisor` | Tắt internal conversation history khi memory advisor tự quản lý lịch sử từng lượt. |
| Advisor bị gọi nhiều lần ngoài dự kiến | Order của advisor lớn hơn ranh giới loop | Kiểm tra lại `getOrder()` và giá trị `advisor-order`. |
| Advisor không chạy trong một số request | Auto-registration hoặc tool calling advisor bị tắt; request không có tool | Kiểm tra cấu hình, tham số request và tập tool được gắn. |
| Hai advisor chạy theo thứ tự không ổn định | Chúng có cùng order | Gán order khác nhau, có khoảng cách rõ ràng. |
| Gọi ChatModel trực tiếp nhưng tool không chạy | Đang dùng đường low-level không có `ToolCallingAdvisor` | Tự thực thi vòng bằng `ToolCallingManager` hoặc chuyển sang `ChatClient`. |
| Code xử lý stream không thấy từng iteration | Chỉ triển khai `CallAdvisor` hoặc stream mặc định chỉ phát kết quả cuối | Triển khai `StreamAdvisor` và bật phát intermediate responses nếu cần. |

## Quy trình chọn order

1. Xác định advisor cần chạy một lần hay ở mỗi lần gọi mô hình.
2. Giữ `ToolCallingAdvisor` ở order mặc định `HIGHEST_PRECEDENCE + 300` nếu không có lý do thay đổi.
3. Đặt advisor chạy một lần ở order nhỏ hơn `+300`, ví dụ `+200`.
4. Đặt advisor chạy theo từng iteration ở order lớn hơn `+300`, ví dụ `+400`.
5. Tránh dùng cùng order và tránh đổi `advisor-order` mà không rà soát các advisor hiện có.
6. Nếu memory nằm trong vòng, bảo đảm memory repository lưu được tool messages và chỉ có một thành phần quản lý lịch sử.
7. Kiểm thử số lần advisor chạy bằng response mô hình có thể kiểm soát.
8. Nếu dùng `ChatModel` trực tiếp hoặc Spring AI 1.x, thiết kế vòng điều phối theo kiến trúc của phiên bản đó thay vì áp dụng quy tắc order của `ToolCallingAdvisor`.

Khi hiểu rõ ranh giới của `ToolCallingAdvisor`, việc chọn advisor order trở nên có chủ đích: thành phần xử lý toàn bộ request đặt ngoài vòng, thành phần cần quan sát hoặc thay đổi từng model iteration đặt trong vòng. Điều này giúp memory không ghi trùng, advisor không chạy thừa và các tool call trung gian được quan sát đúng nơi.

## Tài liệu tham khảo

- [Spring AI 1.0.9 Reference — Tool Calling (vòng lặp nội bộ trong ChatModel)](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html)
- [Spring AI 2.0 Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/2.0/api/tools.html)
- [Spring AI 2.0 Reference — ChatClient API và advisor order](https://docs.spring.io/spring-ai/reference/2.0/api/chatclient.html)
- [Spring AI 2.0 Reference — Advisors API](https://docs.spring.io/spring-ai/reference/2.0/api/advisors.html)
- [Spring AI 2.1 Reference — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1 Reference — Recursive Advisors](https://docs.spring.io/spring-ai/reference/api/advisors-recursive.html)
