# Giả lập ChatModel với phản hồi có hoặc không có tool call

Trong một ứng dụng Spring AI sử dụng tool calling, mô hình có thể **trả lời trực tiếp** hoặc **yêu cầu ứng dụng gọi một công cụ**. Hai nhánh này cần được kiểm thử độc lập để phát hiện các lỗi như gọi tool khi không cần thiết, không gọi tool khi mô hình đã yêu cầu, gọi lặp, mất kết quả khi đưa vào lượt hội thoại tiếp theo hoặc trả câu trả lời cuối trước khi callback hoàn tất.

Không nên dùng API LLM thật để kiểm thử logic điều phối cơ bản. Phản hồi thực tế thay đổi theo model, prompt, sampling và trạng thái dịch vụ, nên khó tái hiện lỗi. Thay vào đó, **giả lập `ChatModel` bằng những `ChatResponse` xác định trước**, rồi kiểm tra số lượt gọi, nội dung prompt, các tool callback được thực thi và kết quả mà người dùng nhận được.

Trong module `SPRING_AI_TOOL_CALLING`, bài này tập trung vào kiểm thử ranh giới giữa `ChatModel`, `ChatClient`, `ToolCallingAdvisor`, `ToolCallback` và `ToolContext`. Mục tiêu là xác nhận ứng dụng chịu trách nhiệm thực thi công cụ đúng lúc, đúng tham số, đúng quyền và đúng số lần, chứ không chỉ xác nhận một câu trả lời văn bản.

## 1. Phân biệt hai đường xử lý

Với Spring AI 2.1.x, `ChatModel.call(Prompt)` là API mức thấp: nó chỉ trả về phản hồi của model. **`ChatModel` không tự thực thi tool call.** Nếu ứng dụng sử dụng `ChatModel` trực tiếp, ứng dụng phải tự kiểm tra `ChatResponse.hasToolCalls()` và điều phối `ToolCallingManager`.

Ngược lại, khi dùng `ChatClient` và đăng ký tools, `ToolCallingAdvisor` được tự động thêm vào chuỗi advisor theo cấu hình mặc định. Advisor phát hiện tool calls, gọi `ToolCallingManager`, ghi kết quả tool vào hội thoại, rồi gọi mô hình thêm một lượt cho tới khi nhận câu trả lời không chứa tool call.

~~~mermaid
flowchart TD
    A[Request của người dùng] --> B[Fake ChatModel trả ChatResponse]
    B --> C{hasToolCalls?}
    C -->|Không| D[Trả câu trả lời cuối, không gọi tool]
    C -->|Có| E[ToolCallingAdvisor kiểm tra yêu cầu]
    E --> F[ToolCallingManager gọi ToolCallback]
    F --> G[ToolResponseMessage với callId và kết quả]
    G --> H[ChatModel nhận prompt của lượt tiếp theo]
    H --> B
~~~

| Đối tượng được kiểm thử | Phản hồi giả lập | Kỳ vọng |
| --- | --- | --- |
| `ChatModel` trực tiếp | Không có tool call | `hasToolCalls() == false`; không thực thi callback |
| `ChatModel` trực tiếp | Có tool call | `hasToolCalls() == true`; callback vẫn chưa chạy |
| `ChatClient` + tool advisor | Không có tool call | Một lượt model, không chạy callback |
| `ChatClient` + tool advisor | Tool call rồi câu trả lời cuối | Callback chạy đúng một lần; model được gọi lại với tool result |
| `ChatClient` + tool advisor | Nhiều tool call liên tiếp | Thực thi đúng chuỗi đã kiểm soát và dừng ở câu trả lời cuối |

Đừng áp dụng ngữ nghĩa Spring AI 1.x cho bài này: phiên bản cũ có vòng thực thi tool bên trong nhiều `ChatModel` cụ thể. Từ 2.0, vòng lặp đó chuyển sang `ToolCallingAdvisor` hoặc được ứng dụng điều khiển thủ công.

## 2. Chọn đúng loại kiểm thử

| Tầng kiểm thử | Nên giả lập gì? | Điều muốn khẳng định |
| --- | --- | --- |
| Unit test của service nghiệp vụ | Không cần ChatModel | Validation, authorization, idempotency và trạng thái nghiệp vụ |
| Unit test của callback | Service/mock repository | Parsing, ToolContext, lỗi và side effect |
| Component test `ChatClient` | Fake `ChatModel` và tool có bộ đếm | Vòng gọi mô hình → công cụ → mô hình |
| Test điều phối `ChatModel` thủ công | Fake `ChatModel` + `ToolCallingManager` | Ứng dụng kiểm tra `hasToolCalls()` và tự quyết định dừng |
| Integration test thật | Model/provider thử nghiệm trong môi trường cô lập | Tương thích provider, schema, streaming và cấu hình triển khai |

Hai nhánh **có tool** và **không có tool** thuộc component test, không nhất thiết phải khởi động toàn bộ `@SpringBootTest`. Một fake chạy ngay trong JVM nhanh, ổn định và có thể kiểm tra chính xác số lượt gọi. Integration test dùng provider thật chỉ nên bổ sung, không thay thế những assertion xác định.

## 3. Dựng phản hồi ChatResponse có và không có tool call

Một `ChatResponse` thường chứa các `Generation`; mỗi `Generation` chứa `AssistantMessage`. Với Spring AI 2.1.x, `AssistantMessage.ToolCall` là record có bốn thành phần:

- `id`: định danh một tool call trong phản hồi, dùng ghép kết quả trả về.
- `type`: thường là `function` đối với tool function calling.
- `name`: tên tool phải khớp với tool definition đã đăng ký.
- `arguments`: JSON string chứa tham số mà mô hình đề xuất.

Phản hồi chỉ có văn bản:

~~~java
static ChatResponse textReply(String content) {
    AssistantMessage message = AssistantMessage.builder()
        .content(content)
        .build();

    return new ChatResponse(List.of(new Generation(message)));
}
~~~

Phản hồi yêu cầu gọi tool:

~~~java
static ChatResponse lookupOrderCall() {
    AssistantMessage.ToolCall call = new AssistantMessage.ToolCall(
        "call-001",
        "function",
        "lookup_order",
        "{\"orderId\":\"ORD-100\"}"
    );

    AssistantMessage message = AssistantMessage.builder()
        .content("")
        .toolCalls(List.of(call))
        .build();

    return new ChatResponse(List.of(new Generation(message)));
}
~~~

Kiểm tra fixture trước khi dùng:

~~~java
assertThat(textReply("Xin chào").hasToolCalls()).isFalse();
assertThat(lookupOrderCall().hasToolCalls()).isTrue();
~~~

Đừng tạo fixture chỉ chứa chuỗi `"calling lookup_order"` trong phần text và mong framework nhận ra tool call: đó vẫn chỉ là văn bản. Tương tự, JSON xuất hiện trong một câu trả lời cũng không tự trở thành lời gọi công cụ. Một tool call hợp lệ phải nằm trong `AssistantMessage.ToolCall`, gắn với `AssistantMessage` của response.

## 4. Fake ChatModel trả phản hồi theo kịch bản

Ta cần một fake có các đặc điểm:

1. Nhận lần lượt các `ChatResponse` xác định trước.
2. Ghi lại mỗi `Prompt` mà hệ thống gửi tới model.
3. Báo lỗi ngay nếu ứng dụng gọi model nhiều hơn số lượt dự kiến.
4. Không thực hiện HTTP request hoặc gọi provider thật.

Ví dụ fake dùng cho các test blocking:

~~~java
static final class ScriptedChatModel implements ChatModel {

    private final Deque<ChatResponse> responses = new ArrayDeque<>();
    private final List<Prompt> prompts = new ArrayList<>();

    ScriptedChatModel(ChatResponse... script) {
        for (ChatResponse reply : script) {
            responses.addLast(reply);
        }
    }

    @Override
    public ChatResponse call(Prompt prompt) {
        prompts.add(prompt);
        if (responses.isEmpty()) {
            throw new AssertionError(
                "Ứng dụng gọi ChatModel nhiều hơn kịch bản dự kiến");
        }
        return responses.removeFirst();
    }

    @Override
    public ChatOptions getOptions() {
        return ChatOptions.builder().build();
    }

    // Fake này chỉ phục vụ API blocking.
    @Override
    public Flux<ChatResponse> stream(Prompt prompt) {
        return Flux.error(new UnsupportedOperationException(
            "Dùng fake streaming riêng cho kiểm thử stream"));
    }

    List<Prompt> capturedPrompts() {
        return List.copyOf(prompts);
    }

    int remainingReplies() {
        return responses.size();
    }
}
~~~

Fake này không tự trả thêm một phản hồi trống khi hết kịch bản. Nếu xảy ra vòng lặp tool ngoài dự kiến, test sẽ thất bại ở lượt gọi kế tiếp, giúp phát hiện sớm lỗi không có điều kiện dừng.

Nếu dùng Mockito thay vì tự viết fake, có thể cấu hình `when(model.call(any(Prompt.class))).thenReturn(reply1, reply2)` và dùng `ArgumentCaptor<Prompt>`. Tuy nhiên, Mockito không tự phát hiện lượt gọi thừa nếu bạn không `verify` số lượt; scripted fake cho biết chính xác kịch bản nào đã bị tiêu thụ.

## 5. Tool kiểm thử có bộ đếm thực thi

Fake model không đồng nghĩa fake tool. Cần một tool callback đơn giản, có thể quan sát được để biết liệu `ToolCallingManager` đã thực sự chạy code hay chưa:

~~~java
static final class OrderTools {

    private final AtomicInteger invocations = new AtomicInteger();

    @Tool(
        name = "lookup_order",
        description = "Tra cứu trạng thái đơn hàng theo mã")
    public String lookupOrder(
            @ToolParam(description = "Mã đơn hàng")
            String orderId) {

        invocations.incrementAndGet();
        if (!"ORD-100".equals(orderId)) {
            throw new IllegalArgumentException("Unknown order");
        }
        return "PAID:" + orderId;
    }

    int calls() {
        return invocations.get();
    }
}
~~~

Tên `lookup_order` ở annotation phải giống `name` trong fixture tool call. `arguments` phải là JSON có field `orderId` trùng với tham số được mô hình hóa trong schema. `AtomicInteger` giúp test đếm chính xác ngay cả khi một phần logic sau này được thực thi trên luồng khác.

Đối với tool ghi dữ liệu thật, không nên kiểm thử bằng cách gọi cơ sở dữ liệu thanh toán, gửi email hay API sản xuất. Hãy thay các dependency sau tool bằng fake repository hoặc mock service; tiếp tục kiểm tra quyền, idempotency và hiệu ứng nghiệp vụ trong các test chuyên biệt.

## 6. Bài kiểm thử JUnit 5 hoàn chỉnh

Dưới đây là một lớp test tự chứa cho đường blocking, sử dụng Spring AI 2.1.x, JUnit Jupiter và AssertJ. Không cần API key, Docker hoặc model server. Với project Spring Boot, dependency `spring-boot-starter-test` thường cung cấp JUnit và AssertJ; đảm bảo project cũng có Spring AI `ChatClient`/`ChatModel` API tương ứng với BOM đang dùng.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.ToolResponseMessage;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.model.Generation;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.model.tool.ToolCallingChatOptions;
import org.springframework.ai.tool.ToolCallbacks;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import reactor.core.publisher.Flux;

import static org.assertj.core.api.Assertions.assertThat;

class ToolCallingChatModelTest {

    static ChatResponse textReply(String text) {
        return new ChatResponse(List.of(new Generation(
            AssistantMessage.builder().content(text).build()
        )));
    }

    static ChatResponse toolReply() {
        AssistantMessage.ToolCall call = new AssistantMessage.ToolCall(
            "call-001",
            "function",
            "lookup_order",
            "{\"orderId\":\"ORD-100\"}"
        );
        return new ChatResponse(List.of(new Generation(
            AssistantMessage.builder()
                .content("")
                .toolCalls(List.of(call))
                .build()
        )));
    }

    static final class OrderTools {
        private final AtomicInteger invocations = new AtomicInteger();

        @Tool(name = "lookup_order",
              description = "Tra cứu trạng thái một đơn hàng")
        public String lookupOrder(
                @ToolParam(description = "Mã đơn hàng") String orderId) {
            invocations.incrementAndGet();
            return "PAID:" + orderId;
        }

        int calls() {
            return invocations.get();
        }
    }

    static final class ScriptedChatModel implements ChatModel {
        private final Deque<ChatResponse> responses = new ArrayDeque<>();
        private final List<Prompt> prompts = new ArrayList<>();

        ScriptedChatModel(ChatResponse... script) {
            for (ChatResponse reply : script) {
                responses.addLast(reply);
            }
        }

        @Override
        public ChatResponse call(Prompt prompt) {
            prompts.add(prompt);
            if (responses.isEmpty()) {
                throw new AssertionError("Unexpected extra model call");
            }
            return responses.removeFirst();
        }

        @Override
        public ChatOptions getOptions() {
            return ChatOptions.builder().build();
        }

        @Override
        public Flux<ChatResponse> stream(Prompt prompt) {
            return Flux.error(new UnsupportedOperationException(
                "Blocking test only"));
        }

        List<Prompt> prompts() {
            return List.copyOf(prompts);
        }

        int remaining() {
            return responses.size();
        }
    }

    @Test
    void textOnly_doesNotInvokeToolOrRecallModel() {
        ScriptedChatModel model =
            new ScriptedChatModel(textReply("Xin chào!"));
        OrderTools tools = new OrderTools();
        ChatClient client = ChatClient.builder(model).build();

        String answer = client.prompt()
            .user("Chào bạn")
            .tools(tools)
            .call()
            .content();

        assertThat(answer).isEqualTo("Xin chào!");
        assertThat(tools.calls()).isZero();
        assertThat(model.prompts()).hasSize(1);
        assertThat(model.remaining()).isZero();
    }

    @Test
    void toolCall_executesOnce_thenUsesResultInSecondPrompt() {
        ScriptedChatModel model = new ScriptedChatModel(
            toolReply(),
            textReply("Đơn ORD-100 đã được thanh toán.")
        );
        OrderTools tools = new OrderTools();
        ChatClient client = ChatClient.builder(model).build();

        String answer = client.prompt()
            .user("Đơn ORD-100 đã thanh toán chưa?")
            .tools(tools)
            .call()
            .content();

        assertThat(answer)
            .isEqualTo("Đơn ORD-100 đã được thanh toán.");
        assertThat(tools.calls()).isEqualTo(1);
        assertThat(model.prompts()).hasSize(2);
        assertThat(model.remaining()).isZero();

        Prompt firstPrompt = model.prompts().get(0);
        ToolCallingChatOptions options =
            (ToolCallingChatOptions) firstPrompt.getOptions();
        assertThat(options.getToolCallbacks())
            .extracting(c -> c.getToolDefinition().name())
            .contains("lookup_order");

        Prompt secondPrompt = model.prompts().get(1);
        ToolResponseMessage toolResult = secondPrompt.getInstructions()
            .stream()
            .filter(ToolResponseMessage.class::isInstance)
            .map(ToolResponseMessage.class::cast)
            .findFirst()
            .orElseThrow();

        assertThat(toolResult.getResponses()).hasSize(1);
        var result = toolResult.getResponses().get(0);
        assertThat(result.id()).isEqualTo("call-001");
        assertThat(result.name()).isEqualTo("lookup_order");
        assertThat(result.responseData()).contains("PAID:ORD-100");
    }

    @Test
    void rawChatModelDoesNotExecuteToolAutomatically() {
        ScriptedChatModel model = new ScriptedChatModel(toolReply());
        OrderTools tools = new OrderTools();
        ChatOptions options = ToolCallingChatOptions.builder()
            .toolCallbacks(ToolCallbacks.from(tools))
            .build();

        ChatResponse reply = model.call(
            new Prompt("Tra cứu đơn ORD-100", options));

        assertThat(reply.hasToolCalls()).isTrue();
        assertThat(reply.getResult().getOutput().getToolCalls())
            .hasSize(1);
        assertThat(tools.calls()).isZero();
        assertThat(model.prompts()).hasSize(1);
    }
}
~~~

### Đọc kết quả kiểm thử

Trong `textOnly_doesNotInvokeToolOrRecallModel`, fake chỉ có **một** response là câu trả lời trực tiếp. Test khẳng định callback không chạy và ChatClient không yêu cầu thêm model turn. Nếu code sai và tự gọi model lần hai, fake báo lỗi vì hết kịch bản.

Trong `toolCall_executesOnce_thenUsesResultInSecondPrompt`, fake có **hai** responses: response đầu yêu cầu tool, response thứ hai là câu trả lời cuối. Test khẳng định:

- Công cụ đúng tên đã được cung cấp cho mô hình trong request.
- Callback chạy đúng một lần.
- `call-001` được giữ nguyên khi tạo `ToolResponseMessage`.
- Prompt của lượt hai có kết quả `PAID:ORD-100` từ công cụ.
- Client trả về câu trả lời cuối và không gọi model lượt ba.

Trong `rawChatModelDoesNotExecuteToolAutomatically`, test gọi trực tiếp `ChatModel.call(Prompt)` và nhận một response có tool call, nhưng không có `ToolCallingManager` hay advisor tham gia. Vì thế bộ đếm của callback vẫn bằng 0. Đây là trường hợp dễ nhầm khi chuyển code từ Spring AI 1.x.

**Lưu ý:** `textReply(...)` cuối cùng trong fake không thật sự đọc nội dung tool result rồi tự suy luận. Đó là câu trả lời được lập trình sẵn. Test xác minh **vòng điều phối và việc truyền kết quả**, chứ không chứng minh rằng LLM thực tế sẽ diễn giải đúng trạng thái đơn hàng. Năng lực suy luận và tính đúng đắn ngôn ngữ cần các evaluation hoặc integration test khác.

## 7. Kiểm tra thông điệp ở từng vòng thay vì chỉ so sánh text

Một assertion kiểu `assertThat(answer).contains("đã thanh toán")` là chưa đủ. Code có thể trả câu trả lời định sẵn mà không hề gọi tool, hoặc đã gọi tool hai lần nhưng vẫn trả đúng text.

Nên quan sát đồng thời ba lớp:

| Quan sát | Assertion gợi ý | Bắt được lỗi |
| --- | --- | --- |
| Số lần model chạy | `model.prompts().size()` | Loop chạy thiếu/dư lượt |
| Số lần callback thực thi | Counter hoặc Mockito `verify(times(n))` | Tool bị bỏ qua hoặc lặp side effect |
| Tool definitions gửi tới model | `ToolCallingChatOptions.getToolCallbacks()` | Tool thiếu, sai tên hoặc bị expose quá rộng |
| Lịch sử lượt hai | `Prompt.getInstructions()` có `ToolResponseMessage` | Mất tool result hoặc mất liên kết call ID |
| Nội dung tool result | `ToolResponse.responseData()` | Trả sai dữ liệu hoặc dùng lại kết quả cũ |
| Kết quả cuối | `ChatClient.call().content()` | Không trả nội dung mong đợi |

Tool-call ID là định danh dùng ghép câu trả lời của tool vào đúng lời gọi. Nó không phải idempotency key của hành động nghiệp vụ. Với tool có side effect, service phải có operation ID độc lập và cơ chế chống thực thi lặp.

## 8. Biến thể có ToolContext

Trong ứng dụng thực tế, `ToolContext` chuyển những giá trị không dành cho model như tenant hoặc request ID tới callback. Khi test, không để model tự tạo `tenantId` từ JSON arguments. Tạo context ở phía request:

~~~java
String answer = client.prompt()
    .user("Tra cứu ORD-100")
    .tools(orderTools)
    .toolContext(Map.of(
        "tenantId", "tenant-test",
        "requestId", "req-42"
    ))
    .call()
    .content();
~~~

Tool có thể nhận thêm tham số `ToolContext`:

~~~java
@Tool(name = "lookup_order", description = "Tra cứu đơn theo tenant")
public String lookupOrder(
        @ToolParam(description = "Mã đơn hàng") String orderId,
        ToolContext toolContext) {

    String tenantId =
        (String) toolContext.getContext().get("tenantId");
    if (tenantId == null) {
        throw new IllegalStateException("Missing tenant");
    }
    return orderService.findForTenant(tenantId, orderId);
}
~~~

Kiểm thử nên xác nhận `tenantId` đúng được truyền tới service; khi thiếu hoặc sai quyền, callback/service từ chối. Việc gắn context không thay thế xác thực principal và kiểm tra quyền trên tài nguyên. Với `ToolCallingChatOptions`, có thể đọc `getToolContext()` của prompt được fake ghi lại để xác minh các giá trị server đã đặt.

## 9. Các trường hợp âm và ranh giới an toàn

### Tool name không tồn tại

Fake trả `AssistantMessage.ToolCall` có tên `delete_all_orders` nhưng request chỉ đăng ký `lookup_order`. Không được để việc model biết hoặc đoán tên khiến service quản trị chạy. Với cấu hình Spring AI 2.1.x mặc định, resolution fallback tắt: công cụ không được gắn vào request không được tự động resolve. Kiểm tra callback không được gọi; cách lỗi hiển thị hoặc được ném phụ thuộc `ToolExecutionExceptionProcessor` và cấu hình ứng dụng.

### JSON arguments không hợp lệ

Fake có thể trả `arguments = "{bad json"` hoặc thiếu trường bắt buộc. Kiểm tra exception/result được xử lý rõ ràng, không gọi service nghiệp vụ với dữ liệu mặc định tự suy đoán. Một schema hợp lệ không thay thế validation nghiệp vụ.

### Tool ném exception

Ví dụ callback gọi một service trả lỗi `403` hoặc `500`. Test cần xác nhận policy lỗi đã chọn:

- Không retry lỗi authorization/validation.
- Runtime exception có thể được chuyển về model thành tool result với processor mặc định.
- Nếu bật `spring.ai.tools.throw-exception-on-error=true`, caller có thể nhận exception thay vì một phản hồi cuối thông thường.
- Không gửi stack trace, secret hoặc payload nhạy cảm cho model và logs mặc định.

Đừng để fake luôn có một câu trả lời thứ hai “thành công” dù tool trước đó đã thất bại; nếu cần kiểm thử nhánh lỗi, hãy lập kịch bản kết quả đúng với chính sách xử lý lỗi được triển khai.

### Model tiếp tục yêu cầu tool

Một fake có kịch bản `toolCall → toolCall → text` kiểm tra nhiều vòng. Đặt giới hạn iteration và deadline trong ứng dụng hoặc advisor; thêm bài test khi model không ngừng yêu cầu gọi tool. Fake nên thất bại khi số response bị dùng hết thay vì im lặng trả null hoặc lặp cùng câu trả lời.

### Không có tool nhưng mô hình yêu cầu tool

Phải có bài test cho request không đăng ký callback, nhưng model sinh tool call. Đây không phải bằng chứng model đã thực thi hành động. Ứng dụng cần từ chối hoặc xử lý theo chính sách; không tự động lấy công cụ nguy hiểm từ application-wide resolver.

### returnDirect và confirmation

Tool có `returnDirect=true` có thể kết thúc vòng lặp ngay sau khi thực thi mà không gọi lại mô hình; đừng áp dụng assertion “luôn có hai model calls” cho nhánh đó. Khi một tool cần confirmation, workflow phải dừng để chờ quyết định; không giả lập confirmation bằng cách cho fake trả ngay câu trả lời thành công.

## 10. Kiểm thử streaming khác blocking ở điểm nào?

Bài test trên cố ý chỉ kiểm thử `.call()`. Không tái sử dụng ScriptedChatModel blocking cho `.stream()` mà kỳ vọng hành vi tương đương. Streaming đi qua `Flux<ChatResponse>` và `MessageAggregator`, cần một kịch bản phát chunk đúng thứ tự.

Spring AI 2.1.x có thể phát các `ToolCallPart` từng phần khi model đang streaming arguments. **Partial tool-call delta không phải tool call hoàn chỉnh**: `getToolCalls()` và `hasToolCalls()` bỏ qua các phần này, nên `ToolCallingManager` không được thực thi chỉ vì nhận một fragment JSON. Phản hồi streaming cần phát **complete tool call** sau các delta, để aggregator/advisor nhận dạng một lời gọi có thể thực thi.

Khi mở rộng bài test cho streaming:

1. Tạo fake `ChatModel.stream(Prompt)` trả `Flux` có những chunk đã định nghĩa.
2. Cho fake phát một hoặc nhiều partial argument chunks, rồi phát complete tool call.
3. Xác nhận callback **không** chạy trên partial fragments và chỉ chạy đúng một lần sau complete tool call.
4. Xác nhận tool result được đưa vào iteration tiếp theo và text output cuối khớp.
5. Kiểm thử cancellation, timeout và giới hạn thời gian nếu ứng dụng dùng SSE hoặc WebFlux.

Không gộp trực tiếp mọi `ChatResponse` chunk bằng cách lấy các tool call list rồi nối chuỗi; hãy dùng cơ chế aggregation của Spring AI để tránh tạo tool call trùng hoặc xử lý JSON chưa hoàn chỉnh.

## 11. Ma trận kiểm thử tối thiểu

| Kịch bản | Số model turns mong đợi | Tool executions mong đợi | Xác nhận trọng tâm |
| --- | --- | --- | --- |
| Text-only reply | 1 | 0 | Không tự gọi tool |
| Tool reply, sau đó text | 2 | 1 | Có tool result ở prompt lượt 2 |
| Hai tool calls trong cùng một reply, sau đó text | 2 | 2 | Hai kết quả gắn đúng call ID |
| Tool call ở hai lượt liên tiếp, rồi text | 3 | 2 | Thứ tự và lịch sử đúng |
| Response chứa text nói “call tool” nhưng không có ToolCall | 1 | 0 | Không nhận diện nhầm text |
| Tool name chưa đăng ký | Theo chính sách lỗi | 0 | Không thực thi ngoài allowlist |
| Arguments sai JSON/schema | Theo chính sách lỗi | 0 thành công | Validation trước side effect |
| Tool thiếu quyền | Theo chính sách lỗi | 0 side effect | Authorization tại service |
| Tool returnDirect | 1 | 1 | Không gửi tool result về model |
| Tool yêu cầu confirmation | 1 trước khi duyệt | 0 trước khi duyệt | Pause đúng và không tự chạy |
| Streaming partial ToolCallPart | Theo chunk/turn | 0 ở partial | Chỉ complete call mới được execute |
| Model liên tục gọi tool | Bị chặn bởi limit | Hữu hạn | Không vòng lặp vô hạn |

Số lượt cụ thể phụ thuộc số tool call, `returnDirect`, confirmation và chính sách lỗi. Đừng hardcode một kỳ vọng “tool call luôn làm model gọi đúng hai lần” cho mọi workflow.

## 12. Các lỗi thường gặp khi giả lập ChatModel

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Test chỉ so sánh câu trả lời cuối | Không phát hiện tool bị bỏ qua/lặp | Kiểm tra count và prompt history |
| Trả chuỗi JSON trong content để giả tool call | `hasToolCalls()` vẫn false | Tạo `AssistantMessage.ToolCall` |
| Dùng sai tên tool trong fixture | Tool manager không tìm thấy callback | Đồng bộ annotation `@Tool(name=...)` |
| Fake tiếp tục trả một response cuối vô hạn | Che giấu lỗi vòng lặp | Queue hữu hạn, fail fast khi hết |
| Gọi `ChatModel` trực tiếp nhưng đòi callback chạy | Hiểu sai kiến trúc 2.x | Dùng `ChatClient` hoặc tự gọi `ToolCallingManager` |
| Giả lập cùng lúc cả ChatModel và ToolCallingManager | Không kiểm tra được kết nối thực giữa các lớp | Mock đúng ranh giới; giữ manager/advisor thật ở component test |
| Dùng external API trong unit test | Chậm, dễ flaky và gây side effect | Fake model, mock downstream |
| Không kiểm tra ToolContext | Bỏ sót lỗi tenant/user scope | Assert context server cấp và quyền ở service |
| Cho streaming fake chỉ phát partial tool calls | Không có complete call để execute | Phát complete ToolCallPart sau deltas |
| Dựa vào một model provider duy nhất | Không thấy khác biệt schema/provider | Thêm contract/integration tests riêng |

## Bài thực hành

Xây một assistant chỉ đọc có hai tool `lookup_order` và `lookup_customer`. Tạo `ScriptedChatModel` có thể phát:

1. Câu trả lời văn bản không có tool call.
2. Một tool call `lookup_order` rồi câu trả lời cuối.
3. Hai tool call trong cùng một response rồi câu trả lời cuối.
4. Tool call có tên không được đăng ký.
5. Tool call chứa JSON sai hoặc chỉ đến tài nguyên không được phép.

Viết JUnit assertions để xác nhận số model turns, số callback executions, tool-call IDs, nội dung `ToolResponseMessage`, `ToolContext` và cơ chế dừng. Sau đó tạo fake stream riêng phát partial tool-call arguments và complete tool call; bảo đảm không thực thi callback ở giai đoạn partial.

**Câu hỏi tự kiểm tra:** Vì sao `ChatResponse.hasToolCalls() == true` không đồng nghĩa công cụ đã chạy? Tại sao cần assert `ToolResponseMessage` ở prompt thứ hai thay vì chỉ kiểm tra câu trả lời cuối? Vì sao không thể dùng cùng một scripted fake blocking để khẳng định tính đúng đắn của streaming?

## Ghi nhớ

Giả lập `ChatModel` bằng các `ChatResponse` xác định trước là cách kiểm thử ổn định nhất cho nhánh có và không có tool call. Trong Spring AI 2.1.x, `ChatModel` trả phản hồi thô, còn `ChatClient` với `ToolCallingAdvisor` điều phối tool callback và gọi mô hình lại. Kịch bản không có tool phải cho kết quả ngay với 0 executions; kịch bản có tool phải thực thi đúng callback, ghi kết quả kèm call ID vào lịch sử rồi nhận câu trả lời cuối. Luôn kiểm tra số lượt, arguments, tool result, quyền, điều kiện dừng và side effect; đừng chỉ so sánh text.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html)
- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1.0 — ChatClient](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI Javadocs 2.1.x — AssistantMessage.Builder](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/messages/AssistantMessage.Builder.html)
- [Spring AI Javadocs 2.1.x — ChatResponse](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/model/ChatResponse.html)
- [Spring AI Javadocs 2.1.x — ToolResponseMessage](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/messages/ToolResponseMessage.html)
- [Spring AI 2.1.0 — Streaming Tool Call Arguments](https://docs.spring.io/spring-ai/reference/api/tools.html#streaming-tool-call-arguments)
