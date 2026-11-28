# Gom đủ tên và đối số từ các phần tool call trước khi thực thi

Khi dùng streaming, mô hình có thể tạo một tool call theo nhiều phần nhỏ. Một chunk có thể chỉ chứa một đoạn JSON arguments, một chunk khác mới bổ sung tên hoặc ID của lời gọi. Trong lúc mô hình vẫn đang sinh dữ liệu, chuỗi arguments có thể chưa phải JSON hợp lệ và tên công cụ có thể chưa hoàn chỉnh. Vì vậy, ứng dụng cần phân biệt **delta dùng để hiển thị tiến độ** với **tool call hoàn chỉnh đủ điều kiện thực thi**.

Trong Spring AI 2.1.0, các phần streaming được biểu diễn bằng `ToolCallPart`. Phần có cờ `partial` là delta để giao diện hiển thị khi mô hình đang viết lời gọi. Nó không phải một tool call hoàn chỉnh: `AssistantMessage.getToolCalls()` và `hasToolCalls()` bỏ qua các phần partial; `MessageAggregator` cũng bỏ qua partial `ToolCallPart`. Sau đó, model adapter phát một `ToolCallPart` hoàn chỉnh ở cùng vị trí. Chỉ lời gọi hoàn chỉnh này mới được dùng cho `ToolCallingManager`.

## Vì sao không thực thi ngay khi nhận một chunk?

Giả sử mô hình cần gọi `lookupOrder` với đối số `orderId` và `includeItems`. Provider có thể phát nội dung theo nhiều delta:

```text
Chunk 1: tool id = call_91, name = lookupOrder, arguments = "{\"orderId\":"
Chunk 2: tool id = call_91, name = lookupOrder, arguments = "\"ORD-2048\","
Chunk 3: tool id = call_91, name = lookupOrder, arguments = "\"includeItems\":"
Chunk 4: tool id = call_91, name = lookupOrder, arguments = "true}"
Chunk cuối: tool call hoàn chỉnh
            id = call_91
            name = lookupOrder
            arguments = {"orderId":"ORD-2048","includeItems":true}
```

Nếu gọi service ở Chunk 1, JSON còn dang dở. Nếu chỉ nhìn Chunk 2, ứng dụng vẫn chưa biết toàn bộ đối số. Nếu thực thi sau Chunk 4 nhưng trước khi response kết thúc, ứng dụng có thể bỏ lỡ một tool call khác trong cùng phản hồi hoặc một phần dữ liệu cuối cùng mà provider chuẩn hóa thêm.

Một tool call chỉ đủ điều kiện thực thi khi ứng dụng nhận được biểu diễn hoàn chỉnh với:

- ID của tool call để liên kết tool result với yêu cầu ban đầu.
- Tên công cụ đầy đủ để phân giải đúng `ToolCallback`.
- Toàn bộ JSON arguments đã hoàn tất.
- Kết thúc của phản hồi mô hình hoặc tín hiệu hoàn tất tương ứng từ adapter.

Không parse một đoạn arguments partial như JSON cuối cùng, không suy đoán phần còn thiếu và không gọi service bằng dữ liệu đang được sinh.

## Các phần của tool call trong Spring AI 2.1.0

Spring AI 2.1.0 dùng mô hình message gồm các `MessagePart` có thứ tự. Nội dung assistant có thể chứa `TextPart`, `ReasoningPart`, `ToolCallPart` hoặc các phần khác. Khi stream, một phần có thể được phát thành delta trước khi phiên bản hoàn chỉnh của nó xuất hiện.

| Thành phần | Ý nghĩa | Cách sử dụng |
|---|---|---|
| `ToolCallPart` partial | Một phần thông tin của tool call, thường gồm ID/tên và đoạn arguments mới | Hiển thị tiến độ; không thực thi |
| `ToolCallPart` complete | Toàn bộ tool call đã hoàn tất | Dùng để tạo `AssistantMessage` có tool calls và chuyển tới manager |
| `StreamingParts` | Thuộc tính đánh dấu phần partial/complete và vị trí của phần trong stream | Giúp phân biệt delta, phần hoàn chỉnh và vị trí content block |
| `MessageAggregator` | Gom các chunk của một lần model response thành một `ChatResponse` | Chờ aggregation xong rồi mới kiểm tra `hasToolCalls()` |
| `ToolCallingManager` | Tìm và gọi callback theo tool call hoàn chỉnh | Chỉ chạy sau khi response đã được tổng hợp |

Một phần partial có thể mang một đoạn arguments rất ngắn, thậm chí là chuỗi rỗng. Tên hoặc ID cũng có thể đến ở một delta riêng. Một số provider gửi cả tên và arguments ngay từ delta đầu tiên; một số khác chia nhỏ chúng. Ứng dụng không được giả định cấu trúc cố định cho từng chunk.

## Phân biệt delta tiến độ và tool call hoàn chỉnh

Trong Spring AI 2.1.0, có thể nhận biết partial `ToolCallPart` bằng `StreamingParts.isPartial(part)`:

```java
chatModel.stream(prompt)
        .doOnNext(response -> response.getResults().forEach(generation -> {
            for (MessagePart part : generation.getOutput().getParts()) {
                if (part instanceof ToolCallPart toolCallPart
                        && StreamingParts.isPartial(part)) {

                    AssistantMessage.ToolCall delta = toolCallPart.toolCall();
                    progressPublisher.publish(
                            delta.id(),
                            delta.name(),
                            delta.arguments());
                }
            }
        }));
```

`progressPublisher` là thành phần giao diện hoặc SSE do ứng dụng định nghĩa. Đoạn code chỉ gửi thông tin tiến độ; nó không gọi `ToolCallback` và không chuyển `delta.arguments()` vào service. UI nên chấp nhận ID/tên chưa xuất hiện ở delta đầu tiên, hiển thị trạng thái đang tạo và cập nhật khi có thêm dữ liệu.

Không dùng `.stream().content()` nếu giao diện cần xem các phần tool call. Các delta arguments không phải text content, nên `content()` không phát chúng như nội dung văn bản. Hãy dùng `.stream().chatResponse()` hoặc `ChatModel.stream(...)` để quan sát cấu trúc message parts.

## Nhiều tool call có thể được phát xen kẽ

Một phản hồi có thể chứa nhiều tool call. Provider có thể phát các delta xen kẽ theo content block:

```text
Response R-17
  index 0: call_A / lookupCustomer / arguments fragment 1
  index 1: call_B / lookupOrders   / arguments fragment 1
  index 0: call_A / lookupCustomer / arguments fragment 2
  index 1: call_B / lookupOrders   / arguments fragment 2
  index 0: complete lookupCustomer(...)
  index 1: complete lookupOrders(...)
```

Không nối tất cả fragments thành một chuỗi duy nhất. Mỗi tool call phải giữ đúng nhóm và thứ tự của nó. Streaming metadata dùng chỉ số content block để phân biệt các phần, còn response ID phân biệt các lần model response khác nhau. Khi tự xây dựng một collector phục vụ UI hoặc adapter, khóa trạng thái theo response ID và index của part; trong phần trạng thái đó mới theo dõi ID, tên và arguments tương ứng.

ID của tool call dùng để liên kết kết quả thực thi với yêu cầu trong giao thức hội thoại. Index của part dùng để ghép các phần trong stream. Hai giá trị có mục đích khác nhau; không thay index bằng vị trí phần tử trong một `List` mới được tạo ở mỗi chunk.

## `MessageAggregator` xử lý phần streaming như thế nào?

Với Spring AI 2.1.0, `MessageAggregator` tổng hợp các chunk của một lần gọi model thành một `ChatResponse`. Các phần có index được sắp theo vị trí content block và nhóm theo response ID. Tuy nhiên, partial `ToolCallPart` được bỏ qua trong message đã tổng hợp; model adapter cần phát thêm `ToolCallPart` hoàn chỉnh ở cùng index. Các delta partial vẫn có thể được quan sát trên stream thô để hiển thị tiến độ.

Điểm này quan trọng với custom `ChatModel` hoặc provider adapter:

- Nếu adapter chỉ phát các partial `ToolCallPart` mà không phát phần hoàn chỉnh, `getToolCalls()` sẽ không có lời gọi để thực thi.
- Adapter phải phát tool call hoàn chỉnh sau các delta, ở cùng index tương ứng.
- Phần hoàn chỉnh là dữ liệu chuẩn để framework tạo `AssistantMessage.ToolCall`.
- Không tự ghép partial thêm lần nữa rồi cộng vào arguments của phần complete, nếu không arguments sẽ bị lặp.

Trong các phiên bản milestone/RC trước 2.1.0 GA, hành vi aggregation của partial tool call từng khác. Khi triển khai theo 2.1.0 GA, hãy tuân theo hợp đồng hiện hành: partial để hiển thị, complete để thực thi.

Nếu tự viết provider adapter, phần chuyển đổi từ giao thức nhà cung cấp sang Spring AI cần có một accumulator nội bộ cho từng content block. Mỗi delta cập nhật ID, tên và arguments của đúng lời gọi; adapter có thể phát `ToolCallPart` partial để UI theo dõi. Khi provider báo function/tool input đã hoàn tất, adapter phát một `ToolCallPart` complete chứa toàn bộ ID, tên và JSON arguments ở cùng index. Nếu provider không cung cấp index, adapter cần tạo index ổn định theo thứ tự content block trước khi phát các phần. Không phát riêng các fragments như thể mỗi fragment là một tool call.

## Gom mỗi vòng streaming trước khi gọi ToolCallingManager

Khi tự điều khiển vòng lặp với `ChatModel`, ứng dụng cần tổng hợp stream của từng vòng trước khi kiểm tra tool call. Mẫu chính thức dùng `MessageAggregator`:

```java
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.model.MessageAggregator;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.model.tool.ToolCallingManager;
import org.springframework.ai.model.tool.ToolExecutionResult;

public String ask(String question) {
    Prompt prompt = new Prompt(question, chatOptions);

    while (true) {
        AtomicReference<ChatResponse> aggregated = new AtomicReference<>();

        new MessageAggregator().aggregate(
                chatModel.stream(prompt)
                        .doOnNext(this::forwardChunkToClient),
                aggregated::set)
                .blockLast();

        ChatResponse response = aggregated.get();
        if (response == null) {
            throw new IllegalStateException("Model stream kết thúc mà không có response.");
        }

        if (!response.hasToolCalls()) {
            return response.getResult().getOutput().getText();
        }

        ToolExecutionResult result =
                toolCallingManager.executeToolCalls(prompt, response);

        if (result.returnDirect()) {
            return convertDirectResult(result);
        }

        prompt = new Prompt(result.conversationHistory(), chatOptions);
    }
}
```

`chatOptions` chứa các `ToolCallback` được phép, context và tùy chọn của request. `forwardChunkToClient(...)` có thể gửi text hoặc tool-call progress tới SSE/WebSocket. `convertDirectResult(...)` là hàm chuyển kết quả direct theo response contract của ứng dụng.

Ví dụ trên là vòng điều phối blocking nên dùng trên thread phù hợp. Không gọi `.blockLast()` trực tiếp trên Reactor event-loop của WebFlux; trong ứng dụng reactive, hãy compose aggregation, kiểm tra response và gọi manager bằng chuỗi reactive không blocking, hoặc chuyển phần blocking sang scheduler chuyên dụng.

Trình tự cần giữ nguyên:

1. Nhận các chunk của một model response.
2. Forward chunk thô cho UI nếu cần hiển thị tiến độ.
3. Đợi `MessageAggregator` hoàn tất và lấy `ChatResponse` đã tổng hợp.
4. Kiểm tra `response.hasToolCalls()` trên response hoàn chỉnh.
5. Chỉ khi có tool call hoàn chỉnh mới gọi `executeToolCalls(prompt, response)`.
6. Dùng `conversationHistory()` cho vòng tiếp theo, trừ khi `returnDirect()` yêu cầu trả kết quả ngay.

Không gọi `executeToolCalls(...)` bên trong `doOnNext` của từng chunk. Callback đó chạy nhiều lần và mỗi lần có thể chỉ có một phần của tool call; làm vậy có thể thực thi lặp, parse JSON lỗi hoặc gọi nhầm tool.

## Dùng ChatClient khi muốn framework tự chạy tool loop

Với `ChatClient`, `ToolCallingAdvisor` mặc định quản lý vòng lặp. Advisor gửi tool definitions cho model, nhận phản hồi, chuyển tool call hoàn chỉnh tới `ToolCallingManager`, thêm tool result vào lịch sử và gọi model tiếp khi cần.

```java
chatClient.prompt()
        .user("Kiểm tra đơn ORD-2048 và thông báo trạng thái")
        .tools(orderTools)
        .stream()
        .chatResponse()
        .subscribe(response -> response.getResults().forEach(generation -> {
            for (MessagePart part : generation.getOutput().getParts()) {
                if (part instanceof ToolCallPart toolCallPart
                        && StreamingParts.isPartial(part)) {
                    AssistantMessage.ToolCall delta = toolCallPart.toolCall();
                    progressPublisher.publish(
                            delta.id(), delta.name(), delta.arguments());
                }
            }
        }));
```

Ở đây, ứng dụng quan sát delta để cập nhật giao diện; `ToolCallingAdvisor` thực thi lời gọi hoàn chỉnh theo vòng tự động. Không gọi manager lần nữa trong subscriber, vì như vậy có thể tạo một đường thực thi thứ hai song song với advisor.

Nếu ứng dụng cần tự kiểm soát từng vòng, có thể tắt auto-registration của `ToolCallingAdvisor` cho request và triển khai vòng lặp riêng. Khi đó phải tự aggregate từng vòng, kiểm tra tool call hoàn chỉnh và gọi manager như ví dụ `ChatModel` ở phần trước. Không vừa để advisor tự chạy tool loop vừa tự thực thi tool call trong subscriber.

## Tự tích lũy delta để hiển thị tiến độ

Giao diện có thể cần ghép các đoạn arguments để hiển thị một JSON đang được tạo. Bộ tích lũy UI cần độc lập với bộ dữ liệu thực thi:

```java
public record ToolCallProgressKey(String responseId, String partIndex) {
}

public final class ToolCallProgress {
    private String id;
    private String name;
    private final StringBuilder arguments = new StringBuilder();

    public void accept(AssistantMessage.ToolCall delta) {
        if (delta.id() != null && !delta.id().isBlank()) {
            this.id = delta.id();
        }
        if (delta.name() != null && !delta.name().isBlank()) {
            this.name = delta.name();
        }
        if (delta.arguments() != null) {
            this.arguments.append(delta.arguments());
        }
    }
}
```

Đây là trạng thái tiến độ để UI hiển thị, không phải object dùng gọi service. Khi triển khai collector, lấy `responseId` từ metadata của response và `partIndex` từ streaming attributes của part; xóa trạng thái khi response kết thúc hoặc bị hủy. Không dùng một `StringBuilder` dùng chung cho mọi tool call.

Đặc biệt, không chuyển `ToolCallProgress` thành `AssistantMessage.ToolCall` rồi gọi callback. Hãy dùng tool call hoàn chỉnh do adapter phát và message aggregator giữ lại. Arguments cuối có thể khác nhẹ so với cách UI ghép delta; ví dụ provider có thể chuẩn hóa một tool call không có arguments thành `{}` ở phần complete.

## Những khác biệt giữa provider cần tính đến

Không phải mọi provider đều phát tool-call arguments theo cùng cách:

| Provider/adapter | Hành vi streaming có thể gặp | Điều ứng dụng cần làm |
|---|---|---|
| Anthropic | Phát từng input delta trong các `ToolCallPart` partial | Gom theo call/content block để hiển thị; đợi phần complete để thực thi |
| OpenAI Chat Completions | Có thể phát tên/ID và arguments thành nhiều delta | Không giả định delta đầu tiên có đủ tên và arguments |
| OpenAI Responses | Phát các phần tool call theo cấu trúc response item | Giữ response ID và index, đợi complete call |
| Amazon Bedrock Converse | Phát tool use block và input delta; phần complete có thể chuẩn hóa arguments vắng mặt thành `{}` | Dùng complete call làm nguồn thực thi |
| DeepSeek | Có thể phát argument delta; một số endpoint chỉ phát complete call | Hỗ trợ cả stream có delta và stream chỉ có phần complete |
| OpenAI-compatible server khác | Có thể gửi ID và tên ở các delta tách rời hoặc không stream delta tool call | Không suy đoán từ một chunk; dựa vào complete call cuối cùng |

Danh sách provider hỗ trợ và hành vi cụ thể có thể thay đổi theo model/API version. Hãy kiểm thử adapter đang dùng thay vì giả định mọi OpenAI-compatible endpoint có cùng cách phát delta.

## Xử lý stream kết thúc sớm, lỗi hoặc bị hủy

Một tool call chưa có phần hoàn chỉnh không được thực thi. Các trường hợp cần dừng an toàn:

- Stream bị hủy trước khi nhận complete `ToolCallPart`.
- Provider trả lỗi giữa lúc đang phát arguments.
- Response bị cắt cụt hoặc không có phần hoàn chỉnh tương ứng với các delta.
- Custom adapter phát sai index, response ID hoặc không phát complete part.
- JSON arguments hoàn chỉnh nhưng không hợp lệ theo schema hoặc không qua validation của tool.

Trong các trường hợp này, ứng dụng cần báo lỗi hoặc trạng thái hủy ở tầng hội thoại, giải phóng tài nguyên và không gọi downstream bằng phần JSON đang dang dở. Khi nhận complete tool call, callback vẫn phải parse và validate arguments như mọi request khác; hoàn chỉnh về mặt streaming không đồng nghĩa hợp lệ về nghiệp vụ.

Nếu một response có nhiều tool call và một call bị thiếu phần complete, không tự ghép call đó từ các mảnh còn lại để cố chạy một phần batch. Hãy xử lý theo hợp đồng của provider/adapter và chỉ thực thi những tool call mà framework xác định là hoàn chỉnh, đúng cấu trúc và có thể liên kết với phản hồi ban đầu.

## Kiểm thử quá trình gom tool call

Kiểm thử nên mô phỏng chunk sequence thay vì chỉ kiểm tra một `ChatResponse` đã hoàn chỉnh. Các ca quan trọng:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Tên và arguments đến trong một chunk | Aggregator giữ một complete tool call |
| Arguments đến qua nhiều partial chunks | UI nhận được từng delta; manager không chạy từ partial |
| ID và tên đến ở các delta khác nhau | UI collector cập nhật cùng một progress entry; complete call có đủ metadata |
| Hai tool call xen kẽ | Mỗi call giữ đúng index/ID; arguments không bị trộn |
| Một response kết thúc với complete call | `hasToolCalls()` là true sau aggregation |
| Chỉ có partial `ToolCallPart`, không có complete part | Aggregated message không có tool call để thực thi |
| Complete call theo sau partial ở cùng index | Complete call là bản dùng cho execution; không cộng arguments lần hai |
| Bedrock hoàn tất arguments rỗng thành `{}` | Callback nhận giá trị complete đã chuẩn hóa |
| Provider không stream tool-call deltas | Tool loop vẫn chạy từ complete call |
| Stream bị hủy hoặc lỗi trước complete | Không gọi callback |
| Tool arguments complete nhưng JSON sai | Callback validation từ chối trước downstream |
| Nhiều vòng tool calling | Mỗi vòng có aggregator riêng và prompt tiếp theo chứa tool results của vòng trước |

Ví dụ test nguyên tắc không thực thi từ partial:

```java
@Test
void partialToolCallDeltaIsNotExecutable() {
    AssistantMessage partialMessage = assistantMessageWithPartialToolCall(
            "call-91", "lookupOrder", "{\"orderId\":");

    assertThat(partialMessage.getToolCalls()).isEmpty();
    assertThat(partialMessage.hasToolCalls()).isFalse();
}
```

`assistantMessageWithPartialToolCall(...)` là helper test tạo message có `ToolCallPart` được đánh dấu partial. Trong integration test, tạo một stream có nhiều delta và một complete part, chạy `MessageAggregator`, rồi xác minh manager chỉ gọi callback một lần với tên và JSON arguments đầy đủ. Đồng thời test stream chỉ có partial và xác minh mock service không được gọi.

## Checklist triển khai

1. Dùng `StreamingParts.isPartial(part)` để phân biệt delta với phần hoàn chỉnh khi quan sát stream.
2. Chỉ dùng partial `ToolCallPart` cho progress UI; không parse hoặc thực thi chúng.
3. Giữ các delta riêng theo response ID và content block index nếu tự tích lũy tiến độ.
4. Không trộn fragments của nhiều tool call vào cùng một buffer.
5. Đợi complete `ToolCallPart` được phát ở cùng index trước khi thực thi.
6. Dùng `MessageAggregator` để tổng hợp mỗi vòng `ChatModel.stream(...)` trước khi kiểm tra `hasToolCalls()`.
7. Với custom chat model, phát complete tool call; partial-only stream sẽ không tạo tool call có thể thực thi.
8. Chọn `ChatClient`/`ToolCallingAdvisor` nếu muốn framework tự chạy tool loop; không gọi manager lần nữa trong subscriber.
9. Xử lý cancellation, provider error, response truncation và validation failure mà không chạy tool call dở dang.
10. Kiểm thử nhiều tool call xen kẽ, provider khác nhau và trường hợp thiếu complete part.

## Kết luận

Trong streaming tool calling, các phần `ToolCallPart` partial chỉ phản ánh tiến độ mô hình đang tạo tên và arguments. Ứng dụng có thể chuyển chúng tới UI, nhưng không được xem chúng là yêu cầu thực thi. Spring AI 2.1.0 phát tool call hoàn chỉnh sau các delta; `getToolCalls()` và `hasToolCalls()` bỏ qua partial, còn `MessageAggregator` giữ complete part để tạo response có thể thực thi. Khi tự điều phối với `ChatModel`, hãy aggregate toàn bộ từng vòng rồi mới gọi `ToolCallingManager`. Khi dùng `ChatClient`, để `ToolCallingAdvisor` thực thi tool call hoàn chỉnh và chỉ quan sát partial để hiển thị tiến độ. Cách làm này giữ đúng tên, ID và toàn bộ arguments của từng tool call, kể cả khi nhiều lời gọi được phát xen kẽ.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html) — Streaming Tool Call Arguments, partial `ToolCallPart`, `ToolCallingAdvisor` và vòng thực thi.
- [Spring AI 2.1.0 — ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html) — aggregate từng vòng bằng `MessageAggregator` trước khi kiểm tra và thực thi tool call.
- [Spring AI 2.1.0 — Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html) — streaming contract của message parts và thay đổi hành vi partial tool call trong 2.1.0 GA.
- [Spring AI 2.1.0 GA Announcement](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/) — các provider phát argument delta và complete tool call ở cùng index.
- [Spring AI — StreamingParts API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/messages/part/StreamingParts.html) — metadata đánh dấu partial/complete và index của message part.
