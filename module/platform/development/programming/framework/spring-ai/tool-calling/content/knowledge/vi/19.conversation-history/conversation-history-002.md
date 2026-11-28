# Giữ cặp tool request và tool response hợp lệ trong hội thoại

Khi mô hình yêu cầu gọi một công cụ, lịch sử hội thoại phải giữ lại yêu cầu đó cùng kết quả trả về tương ứng. Một assistant message có thể chứa một hoặc nhiều tool call; ứng dụng thực thi các call rồi thêm tool response khớp với từng call trước khi gửi lượt tiếp theo cho mô hình.

Nếu lịch sử chỉ còn tool response mà mất assistant tool request, hoặc còn tool request nhưng thiếu kết quả, nhiều model provider sẽ từ chối hội thoại vì chuỗi message không hợp lệ. Nếu ghép kết quả bằng tên công cụ thay vì định danh của từng call, hai lần gọi cùng một công cụ trong một lượt có thể bị ghép nhầm.

Spring AI 2.x biểu diễn tool request bằng `AssistantMessage` và tool response bằng `ToolResponseMessage`. Từ Spring AI 2.1.0, nội dung message còn được mô hình hóa thành các `MessagePart` có thứ tự, gồm `ToolCallPart` và `ToolResultPart`. Bài học này giải thích cách giữ đúng cấu trúc, ghép cặp theo tool-call ID, lưu và khôi phục lịch sử, cũng như xử lý các trường hợp ID bị thiếu hoặc một lượt đang chờ kết quả.

Sau bài học, bạn có thể:

- Phân biệt assistant tool request và tool response trong conversation history.
- Giải thích vai trò của `AssistantMessage.ToolCall`, `ToolResponseMessage` và `ToolResultPart`.
- Ghép mỗi kết quả với đúng tool call bằng ID và kiểm tra tên công cụ.
- Giữ nguyên thứ tự và các message part khi lưu, đọc lại hoặc compact lịch sử.
- Chọn cách lưu lịch sử phù hợp với `ToolCallingAdvisor`, `ChatMemory` hoặc Session Memory.
- Phát hiện orphan request, orphan response, duplicate ID và lượt đang chờ xử lý.
- Kiểm thử serialization, resume và tính hợp lệ của transcript trước khi gửi lại mô hình.

## 1. Vì sao phải giữ cặp request/response?

Tool calling là một phần của giao thức hội thoại giữa ứng dụng và model provider. Mô hình không chỉ trả về tên hàm để ứng dụng chạy; nó tạo một assistant message có yêu cầu gọi công cụ. Sau khi ứng dụng thực thi, kết quả phải được gửi lại trong một tool response message liên kết với yêu cầu đó.

Một chu kỳ thông thường có dạng:

```text
UserMessage
    Người dùng hỏi về đơn hàng

AssistantMessage
    ToolCall(id=call_order, name=get_order_status, arguments=...)
    ToolCall(id=call_stock, name=get_inventory, arguments=...)

ToolResponseMessage
    ToolResult(id=call_order, name=get_order_status, content=...)
    ToolResult(id=call_stock, name=get_inventory, content=...)

AssistantMessage
    Câu trả lời tổng hợp của mô hình
```

Hai tool call có thể cùng xuất hiện trong một assistant message. Mỗi call cần một kết quả tương ứng trước khi ứng dụng gửi phần tiếp theo của hội thoại cho mô hình. Một kết quả thiếu, lặp hoặc ghép sai ID có thể khiến provider không chấp nhận transcript hoặc khiến mô hình hiểu sai dữ liệu.

Lịch sử còn cần giữ nguyên vai trò của từng message. Không chuyển tool request thành `UserMessage`, không ghép tool result vào một đoạn văn bản assistant tùy ý và không chỉ lưu nội dung text nếu message có chứa tool call.

## 2. Các kiểu message và trường dữ liệu quan trọng

Trong Spring AI, `AssistantMessage.ToolCall` chứa thông tin của một yêu cầu công cụ:

```java
public record ToolCall(
    String id,
    String type,
    String name,
    String arguments
) {}
```

Các trường có ý nghĩa:

- `id`: định danh của lần gọi công cụ do provider trả về.
- `type`: loại tool call theo giao thức provider.
- `name`: tên công cụ mà mô hình yêu cầu.
- `arguments`: chuỗi JSON chứa đối số.

`AssistantMessage.getToolCalls()` trả danh sách các call trong assistant message. Tên công cụ có thể lặp trong cùng một lượt; vì vậy, `name` không đủ để định danh một lần gọi cụ thể.

Trong cách biểu diễn tương thích cũ, `ToolResponseMessage.ToolResponse` là record chứa `id`, `name` và `responseData`:

```java
public record ToolResponse(
    String id,
    String name,
    String responseData
) {}
```

Từ Spring AI 2.1.0, `ToolResponseMessage` lưu nội dung dưới dạng danh sách `ToolResultPart`. Mỗi result part có thể giữ:

| Trường | Ý nghĩa |
|---|---|
| `id` | ID của tool call mà kết quả trả lời; có thể null nếu provider không phát ID |
| `name` | Tên công cụ; có thể null nếu adapter không biết tên |
| `content` | Danh sách `MessagePart` chứa nội dung kết quả, có thể gồm text hoặc media |
| `isError` | Cho biết tool result được đánh dấu là lỗi |
| `payload` | Dữ liệu riêng của provider cần giữ để replay nếu có |
| `attributes` | Metadata an toàn để serialize, ví dụ provider item ID |

Đọc `ToolResponseMessage.getResults()` khi cần đầy đủ cấu trúc, bao gồm media và cờ lỗi. `getResponses()` chỉ là view tương thích lấy phần text của từng kết quả; nó không thể hiện nội dung mà một chuỗi text không mang được.

## 3. `MessagePart` giữ thứ tự nội dung

Từ Spring AI 2.1.0, `AssistantMessage`, `UserMessage` và `ToolResponseMessage` có thể chứa một danh sách `MessagePart` theo đúng thứ tự. Các loại part quan trọng gồm:

- `TextPart`: một đoạn văn bản.
- `ReasoningPart`: dữ liệu reasoning của model nếu provider cung cấp.
- `ToolCallPart`: một tool call, bọc `AssistantMessage.ToolCall`.
- `ToolResultPart`: kết quả của một tool call.
- `MediaPart`: hình ảnh, âm thanh, video hoặc tài liệu.
- `UnknownPart`: giữ nguyên một phần dữ liệu provider mà phiên bản hiện tại chưa mô hình hóa.

Ví dụ một assistant message có thể chứa text, tool call rồi lại có một text part khác. Không nên tái tạo message chỉ từ `getText()` vì cách đó làm mất các phần không phải text. Tương tự, `ToolResponseMessage.getResponses()` chỉ trả text; dùng `getResults()` khi cần giữ media, error flag và provider payload.

Một số provider gắn dữ liệu đặc biệt vào `OpaquePayload`, chẳng hạn chữ ký reasoning hoặc token cần gửi lại nguyên vẹn. Khi lưu lịch sử cho cùng provider, giữ payload và attributes theo message part. Nếu bỏ chúng hoặc chuyển mọi nội dung thành plain text, request tiếp theo có thể không còn hợp lệ theo giao thức của provider.

## 4. Quy tắc ghép cặp: ID trước, thứ tự khi provider không có ID

Quy tắc chung là ghép `ToolResultPart.id()` với `AssistantMessage.ToolCall.id()`. Sau khi tìm được ID, kiểm tra thêm tên công cụ nếu cả request và result đều có tên.

Không ghép chỉ bằng tên công cụ. Ví dụ, một lượt có thể gọi `get_weather("Hanoi")` và `get_weather("Paris")`. Hai call có cùng `name` nhưng khác ID và arguments. Nếu dùng tên làm khóa, kết quả thời tiết có thể bị đảo.

Một số provider không trả tool-call ID. Trong trường hợp đó, `ToolResultPart.id()` có thể là null. Chỉ dùng ghép theo vị trí khi adapter/provider bảo đảm thứ tự result tương ứng với thứ tự call trong cùng response. Nếu thứ tự không được bảo đảm hoặc chỉ một phần ID bị thiếu, coi mapping là mơ hồ và không tự đoán.

`ToolCallDecisions.toolCallKeys(...)` trong luồng xác nhận của Spring AI cũng minh họa cách xử lý ID không duy nhất: dùng ID khi nó có mặt và duy nhất; nếu ID thiếu hoặc trùng, dùng khóa vị trí như `#0`, `#1`. Đây là khóa quyết định cho confirmation, không thay đổi ID gốc trong message history.

## 5. Ví dụ lịch sử hợp lệ với nhiều tool call

Giả sử người dùng hỏi trạng thái đơn hàng và số lượng tồn kho. Mô hình tạo hai tool call:

```json
{
  "role": "assistant",
  "tool_calls": [
    {
      "id": "call_order_01",
      "type": "function",
      "name": "get_order_status",
      "arguments": "{\"orderId\":\"ORD-104\"}"
    },
    {
      "id": "call_stock_02",
      "type": "function",
      "name": "get_inventory",
      "arguments": "{\"sku\":\"KB-104\"}"
    }
  ]
}
```

Ứng dụng thực thi từng công cụ rồi thêm hai kết quả tương ứng:

```json
{
  "role": "tool",
  "tool_results": [
    {
      "tool_call_id": "call_order_01",
      "name": "get_order_status",
      "content": "{\"status\":\"PROCESSING\"}"
    },
    {
      "tool_call_id": "call_stock_02",
      "name": "get_inventory",
      "content": "{\"availableQuantity\":12}"
    }
  ]
}
```

Đây là JSON minh họa giao thức, không phải cấu trúc serialize nguyên văn của mọi provider. Trong Spring AI, request nằm trong `AssistantMessage`, còn các kết quả nằm trong `ToolResponseMessage` với các result part. Sau khi hai result đã được thêm, mô hình mới nhận history cập nhật để tổng hợp câu trả lời.

## 6. Để `ToolCallingAdvisor` quản lý lịch sử trong vòng lặp

Với `ChatClient`, `DefaultChatClient` tự đăng ký `ToolCallingAdvisor`. Advisor gửi prompt tới mô hình, nhận tool call, chuyển chúng cho `ToolCallingManager`, thêm tool result vào conversation history rồi gọi mô hình tiếp. Các vòng này được quản lý trong cùng một lần `.call()` hoặc `.stream()`.

```java
ChatClient chatClient = ChatClient.builder(chatModel).build();

String answer = chatClient.prompt()
    .user("Kiểm tra trạng thái ORD-104 và tồn kho SKU KB-104")
    .tools(orderTools, inventoryTools)
    .call()
    .content();
```

Trong đường này, không cần tự dựng `AssistantMessage` hoặc `ToolResponseMessage`. Advisor giữ history của các iteration và bảo đảm tool result được đưa lại mô hình trước khi kết thúc lượt. Đây là lựa chọn phù hợp khi ứng dụng không cần tự kiểm soát từng bước.

Không tự thêm một `ToolResponseMessage` thứ hai sau khi advisor đã thực thi callback. Làm như vậy có thể tạo result trùng hoặc khiến history không còn khớp với các tool call mà model đã phát ra.

## 7. Khi tự điều phối bằng `ChatModel`

Nếu gọi `ChatModel` trực tiếp trong Spring AI 2.x, model chỉ trả response có thể chứa tool call; nó không tự thực thi callback. Ứng dụng dùng `ToolCallingManager.executeToolCalls(...)` để thực thi và nhận `ToolExecutionResult.conversationHistory()`.

```java
ToolCallback[] callbacks = ToolCallbacks.from(orderTools, inventoryTools);

ToolCallingChatOptions options = ToolCallingChatOptions.builder()
    .toolCallbacks(callbacks)
    .build();

Prompt prompt = new Prompt(
    List.of(new UserMessage(question)),
    options
);

ChatResponse response = chatModel.call(prompt);

while (response.hasToolCalls()) {
    ToolExecutionResult result = toolCallingManager.executeToolCalls(prompt, response);

    // History đã chứa assistant tool request và ToolResponseMessage tương ứng.
    prompt = new Prompt(result.conversationHistory(), options);
    response = chatModel.call(prompt);
}

String finalAnswer = response.getResult().getOutput().getText();
```

Điểm quan trọng là dùng nguyên `result.conversationHistory()` làm đầu vào cho vòng tiếp theo. Không tự chỉ lấy `UserMessage` và `AssistantMessage.getText()`, vì như vậy sẽ bỏ các tool call và tool result cần thiết.

Nếu cần lưu history giữa các request, persist danh sách message hoàn chỉnh từ `conversationHistory()`, bao gồm cả assistant tool call request và tool response. Khi khôi phục, đọc lại đúng thứ tự rồi tạo `Prompt` mới. `ToolCallingManager` không thể sửa một transcript đã mất tool call ID hoặc result tương ứng.

## 8. Tạo `ToolResponseMessage` khi tự xây adapter

Trong hầu hết trường hợp, nên để `ToolCallingManager` tạo tool response. Chỉ tự tạo `ToolResponseMessage` khi đang xây dựng adapter hoặc một tầng tích hợp đặc biệt.

Với kết quả text đơn giản, builder tương thích có thể nhận `ToolResponseMessage.ToolResponse`:

```java
ToolResponseMessage responseMessage = ToolResponseMessage.builder()
    .responses(List.of(
        new ToolResponseMessage.ToolResponse(
            call.id(),
            call.name(),
            resultJson
        )
    ))
    .build();
```

Builder tạo một text-only `ToolResultPart` cho mỗi `ToolResponse`. Nếu cần lưu error flag, media hoặc provider payload, hãy dùng `ToolResultPart` và API `result(...)`/`results(...)` thay vì chỉ dùng danh sách response text.

```java
ToolResultPart resultPart = new ToolResultPart(
    call.id(),
    call.name(),
    List.of(TextPart.of(resultJson)),
    isError,
    null,
    Map.of()
);

ToolResponseMessage responseMessage = ToolResponseMessage.builder()
    .result(resultPart)
    .build();
```

Khi tự dựng response cho nhiều call trong cùng assistant message, thêm một result part cho từng call, giữ ID và thứ tự tương ứng. Nếu callback trả lỗi, biểu diễn rõ trạng thái lỗi trong result part hoặc payload theo giao thức adapter; không biến exception thành một kết quả thành công rỗng.

## 9. Kiểm tra một cặp theo ID

Với provider trả ID duy nhất, có thể kiểm tra request và result bằng map. Ví dụ sau kiểm tra một assistant message và một tool response message:

```java
public static void validateToolPairById(
        AssistantMessage assistant,
        ToolResponseMessage toolResponse) {

    Map<String, AssistantMessage.ToolCall> expected = new LinkedHashMap<>();

    for (AssistantMessage.ToolCall call : assistant.getToolCalls()) {
        if (call.id() == null || call.id().isBlank()) {
            throw new IllegalStateException("Tool call thiếu ID; cần validator theo provider.");
        }
        if (expected.putIfAbsent(call.id(), call) != null) {
            throw new IllegalStateException("Tool call ID bị trùng: " + call.id());
        }
    }

    Map<String, ToolResultPart> actual = new LinkedHashMap<>();

    for (ToolResultPart result : toolResponse.getResults()) {
        if (result.id() == null || result.id().isBlank()) {
            throw new IllegalStateException("Tool result thiếu ID; cần validator theo provider.");
        }
        if (actual.putIfAbsent(result.id(), result) != null) {
            throw new IllegalStateException("Tool result ID bị trùng: " + result.id());
        }

        AssistantMessage.ToolCall call = expected.get(result.id());
        if (call == null) {
            throw new IllegalStateException("Tool result không có request tương ứng: " + result.id());
        }
        if (result.name() != null && !result.name().equals(call.name())) {
            throw new IllegalStateException("Tên tool result không khớp tool request: " + result.id());
        }
    }

    if (!expected.keySet().equals(actual.keySet())) {
        throw new IllegalStateException("Thiếu tool result cho một hoặc nhiều tool call.");
    }
}
```

Đây là validator nghiêm ngặt cho trường hợp mọi call đều có ID duy nhất. Với provider có thể bỏ ID, dùng validator theo hợp đồng adapter: xác nhận số lượng request/result bằng nhau và ghép theo vị trí chỉ khi adapter đảm bảo thứ tự. Không bỏ qua phần tử thiếu rồi tiếp tục ghép bằng tên công cụ.

Trong một lượt có nhiều assistant tool-call message hoặc nhiều tool-response message, validator cấp conversation cần giữ tập call đang chờ qua các message và chỉ cho phép chuyển sang lượt tiếp theo khi tất cả call của lượt đã có result hợp lệ.

## 10. Các lỗi cấu trúc thường gặp

| Lỗi | Vì sao không hợp lệ | Cách xử lý |
|---|---|---|
| Có assistant tool call nhưng thiếu tool response | Model provider nhận được yêu cầu chưa có kết quả | Tiếp tục thực thi, trả error result hoặc giải quyết trạng thái pending trước lượt mới |
| Có tool response nhưng không có assistant tool call trước đó | Result không có request làm căn cứ | Loại bỏ bản ghi lỗi hoặc khôi phục đúng assistant message từ nguồn tin cậy |
| Result dùng sai ID | Mô hình có thể gắn kết quả vào call khác | Ghép theo ID và xác minh tên; từ chối transcript không khớp |
| Một call có hai result | Mô hình nhận kết quả lặp cho cùng yêu cầu | Chặn duplicate ID hoặc dùng ledger chống ghi lặp |
| Hai call cùng tên bị ghép theo name | Kết quả của arguments khác nhau có thể bị đảo | Dùng ID duy nhất; fallback vị trí theo adapter nếu thiếu ID |
| Chỉ lưu text của assistant | Tool call structure và arguments bị mất | Persist `AssistantMessage` đầy đủ và các message part |
| Chỉ lưu `getResponses()` | Media, error flag và payload có thể mất | Dùng `ToolResponseMessage.getResults()` |
| Cắt history giữa request và response | Lượt mới bắt đầu bằng một tool request mồ côi | Compact theo turn, không cắt giữa cặp |
| Ghi tool result thành user message | Sai vai trò giao thức | Dùng `ToolResponseMessage` |

## 11. Lưu lịch sử: ChatMemory và Session Memory

Trong Spring AI 2.1.0, `ChatMemory` và `MessageChatMemoryAdvisor` đã deprecated để chuyển sang Session Memory. Cần phân biệt hai nhu cầu:

**Giữ history trong một vòng tool calling.** `ToolCallingAdvisor` mặc định tự giữ đầy đủ lịch sử trong vòng lặp, gồm user message, assistant tool-call request và tool response. Mô hình nhận toàn bộ history cần thiết giữa các iteration.

**Lưu transcript qua nhiều request.** Nếu chỉ dùng `MessageChatMemoryAdvisor` ở vị trí mặc định bên ngoài `ToolCallingAdvisor`, memory nạp history trước vòng lặp và lưu user message cùng câu trả lời assistant cuối sau khi vòng lặp kết thúc. Nó không lưu các tool request và tool response trung gian. Đây là mặc định an toàn với repository chỉ hỗ trợ user/assistant message.

Nếu cần lưu cả tool transcript bằng API cũ, memory advisor phải nằm bên trong vòng lặp và repository phải serialize được cả assistant tool-call message lẫn `ToolResponseMessage`. Không phải mọi `ChatMemoryRepository` đều hỗ trợ các kiểu message này. Khi đặt memory bên trong loop, tránh để cả memory và `ToolCallingAdvisor` cùng ghi history; advisor tự động xử lý việc này, còn advisor được tạo thủ công cần cấu hình `.disableInternalConversationHistory()`.

Session Memory là hướng được khuyến nghị từ Spring AI 2.1.0. Session lưu conversation dưới dạng event log, giữ tool calls và tool results, rồi tạo view cho prompt. Cơ chế compaction theo turn giúp không cắt giữa một lượt đang có tool request và tool response. Với hội thoại dài, đây là cách phù hợp hơn việc cắt một danh sách message theo số phần tử tùy ý.

## 12. Không cắt lịch sử giữa một tool turn

Một turn có thể gồm nhiều vòng model/tool. Khi giới hạn context window hoặc compact transcript, hãy coi cả chuỗi sau là một đơn vị logic:

```text
UserMessage
  -> AssistantMessage (tool calls)
  -> ToolResponseMessage (matching results)
  -> AssistantMessage (tool calls tiếp theo, nếu có)
  -> ToolResponseMessage (matching results)
  -> AssistantMessage (final answer)
```

Nếu chỉ giữ `AssistantMessage` cuối mà xóa tool result trong khi vẫn giữ tool request, provider có thể báo thiếu tool response. Nếu xóa tool request mà giữ result, model nhận một kết quả không có ngữ cảnh gọi. Hãy compact theo ranh giới turn hoàn chỉnh hoặc chuyển phần cũ thành một summary message sau khi turn đã kết thúc.

Không dùng một summary để thay thế tool request đang chờ thực thi. Summary chỉ nên mô tả những gì đã hoàn tất; một tool call pending cần được lưu riêng như trạng thái workflow cho đến khi có kết quả hoặc quyết định từ chối/hủy.

## 13. Xử lý hội thoại đang có tool call pending

Một lượt có thể bị tạm dừng trước khi callback chạy, ví dụ khi tool yêu cầu người dùng xác nhận. Khi đó assistant message chứa tool calls nhưng chưa có `ToolResponseMessage` tương ứng. Đây là trạng thái pending có chủ đích, không phải transcript hoàn tất.

Ứng dụng cần lưu response gốc ở server, đánh dấu các tool call đang chờ và không gửi một lượt mới cho model như thể turn cũ đã hoàn tất. Khi người duyệt quyết định:

1. Lấy đúng paused response từ storage phía server.
2. Xác minh người duyệt có quyền.
3. Tạo một quyết định cho mỗi tool call.
4. Gọi `ToolCallingManager.executeToolCalls(prompt, reply, decisions)`.
5. Thêm tool result vào history rồi tiếp tục mô hình.

Không nhận lại `ChatResponse` từ browser để resume. Người dùng có thể sửa tool name hoặc arguments nếu ứng dụng tin nội dung client gửi lên. Resume cũng cần idempotent để cùng một quyết định không thực thi callback hai lần.

Nếu người dùng bỏ dở confirmation rồi gửi một câu hỏi mới, ứng dụng cần giải quyết các call pending trước khi nhận lượt mới. Session Memory có `SessionTurnAdvisor` để xử lý một paused turn chưa được quyết định bằng kết quả trung tính khi turn mới bắt đầu; nếu muốn mô hình biết rõ người dùng đã từ chối, ứng dụng nên ghi một quyết định deny rõ ràng trước khi tiếp tục.

## 14. Lưu trữ và khôi phục message an toàn

Khi persist conversation history, lưu message theo cấu trúc thay vì chỉ lưu text:

- Loại message (`USER`, `ASSISTANT`, `TOOL`) và thứ tự trong conversation.
- Assistant tool call ID, type, name và raw arguments.
- Từng tool result ID, name, content parts và error flag.
- Thứ tự các `MessagePart`.
- Provider payload và attributes cần thiết để replay.
- Conversation ID, turn ID, thời điểm, trạng thái pending/completed và phiên bản schema lưu trữ.

Nếu có dữ liệu media hoặc provider payload, cần serializer hiểu các kiểu part tương ứng. `UnknownPart` được thiết kế để giữ dữ liệu provider chưa được mô hình hóa; không loại bỏ chỉ vì code ứng dụng chưa dùng đến nó.

Khi đọc lại, kiểm tra tính toàn vẹn trước khi gửi prompt: không có tool result mồ côi, không thiếu result cho turn đã đánh dấu hoàn tất, không trùng ID và mọi pending call phải thuộc một workflow đang chờ xử lý. Nếu schema lưu trữ đã thay đổi, migrate dữ liệu theo version; không âm thầm bỏ field không nhận diện được.

## 15. Bảo vệ nguồn history

Conversation history có thể chứa arguments do mô hình tạo và những yêu cầu có tác động nghiệp vụ. Nếu client có thể gửi một assistant message tùy ý với tool call và ứng dụng đưa thẳng nó vào `ToolCallingManager`, client có thể tự tạo tool request với arguments do mình chọn.

Vì vậy:

- Lưu và khôi phục lịch sử từ kho dữ liệu phía server gắn với đúng conversation/user/tenant.
- Không nhận `AssistantMessage` tool call hoặc `ChatResponse` paused từ client làm nguồn sự thật.
- Kiểm tra quyền trước khi callback chạy; history hợp lệ không đồng nghĩa caller có quyền thực thi.
- Không cho phép sửa `toolCallId`, tên công cụ hoặc arguments của một response đã được model phát ra.
- Ghi nhận trạng thái đã thực thi để ngăn replay cùng một tool call tạo side effect hai lần.

`ToolContext` là dữ liệu do ứng dụng cung cấp cho callback, không phải nội dung cần lấy từ conversation text. Hãy truyền tenant, user hoặc request context qua cơ chế này và vẫn kiểm tra quyền tại service nghiệp vụ.

## 16. Streaming và message chưa hoàn chỉnh

Trong streaming, provider có thể phát các `ToolCallPart` partial chứa từng mảnh ID, name hoặc arguments. Một fragment arguments thường chưa phải JSON hợp lệ và chưa phải tool call hoàn chỉnh.

Spring AI 2.1.0 đánh dấu các part partial bằng `StreamingParts`. `AssistantMessage.getToolCalls()` và `hasToolCalls()` bỏ qua partial part; `MessageAggregator` cũng không persist các delta đó. Model adapter phải phát complete `ToolCallPart` khi tool call đã hoàn chỉnh. Chỉ khi đó tool loop mới thực thi và tạo response tương ứng.

UI có thể hiển thị tiến trình từ partial part, nhưng không lưu chúng như tool request hoàn chỉnh và không chạy callback từ fragment. Khi cần lưu streaming response, dùng `MessageAggregator`/`ChatClientMessageAggregator` để ghép các part theo index và response ID trước khi persist.

## 17. Kiểm thử tính hợp lệ của cặp tool request/response

Kiểm thử nên bao gồm:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Một tool call và một result cùng ID | Pair hợp lệ |
| Một assistant message có ba call và ba result | Mỗi result khớp đúng ID và tên |
| Hai call cùng tên nhưng ID khác nhau | Kết quả vẫn ghép chính xác theo ID |
| Thiếu một result | Turn bị đánh dấu incomplete; không gửi tiếp như turn hoàn tất |
| Có result không có request | Phát hiện orphan result |
| Duplicate call ID | Từ chối hoặc chuyển sang quy tắc positional được provider hỗ trợ |
| Result dùng ID không tồn tại | Phát hiện mismatch |
| Provider không trả ID | Dùng adapter-specific positional mapping và giữ nguyên thứ tự |
| Serialize rồi deserialize history | Message type, parts, ID, payload và order được giữ nguyên |
| Compaction | Không cắt giữa assistant tool request và tool response |
| Confirmation pending | Reply gốc được giữ ở server và resume đúng một lần |
| Client sửa history | Request bị từ chối hoặc history được lấy từ server thay vì client |
| Streaming partial tool call | Không execute hoặc persist delta; chỉ complete part được dùng |

Ví dụ unit test cho validator theo ID:

```java
@Test
void rejectsToolResultWithUnknownCallId() {
    AssistantMessage assistant = assistantWithToolCalls(
        new AssistantMessage.ToolCall(
            "call_01", "function", "get_order_status", "{\"orderId\":\"ORD-104\"}"
        )
    );

    ToolResponseMessage response = ToolResponseMessage.builder()
        .result(new ToolResultPart(
            "call_other",
            "get_order_status",
            List.of(TextPart.of("{\"status\":\"PROCESSING\"}")),
            false,
            null,
            Map.of()
        ))
        .build();

    assertThatThrownBy(() -> validateToolPairById(assistant, response))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining("không có request tương ứng");
}
```

`assistantWithToolCalls` là fixture của test. Trong integration test, dùng một model giả trả tool call, thực thi callback qua `ToolCallingManager`, sau đó xác nhận `ToolExecutionResult.conversationHistory()` chứa assistant tool request và tool response đúng ID trước khi model được gọi lại.

## 18. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Provider báo thiếu tool response | History còn assistant tool call nhưng result chưa được lưu | Khôi phục hoặc giải quyết pending call trước lượt mới |
| Mô hình nhận nhầm kết quả | Ghép result theo tên thay vì ID | Ghép theo ID và kiểm tra name |
| Tool response biến mất sau khi đọc memory | Repository chỉ lưu user/assistant text | Dùng Session Memory hoặc repository hỗ trợ tool message |
| History bị lỗi sau compaction | Cắt danh sách giữa request và response | Compact theo turn hoàn chỉnh |
| Nội dung reasoning/tool payload bị mất | Serialize bằng `getText()` hoặc bỏ qua `MessagePart` | Lưu toàn bộ part, payload và attributes |
| Một tool call bị chạy lại sau resume | Paused response bị replay hoặc trạng thái executed không được lưu | Idempotency key và execution ledger |
| Result không có ID bị ghép nhầm | Ghép theo tên công cụ, trong khi cùng tool được gọi nhiều lần | Dùng thứ tự theo provider contract hoặc từ chối mapping mơ hồ |
| Client tự tạo tool call | Tin history do client gửi | Dùng conversation store phía server và xác thực quyền |

## 19. Ghi nhớ

- Một assistant tool call cần tool response tương ứng trước khi lượt hội thoại được xem là hoàn tất.
- `AssistantMessage.ToolCall` chứa ID, tên và arguments; `ToolResponseMessage` chứa kết quả của từng call.
- Trong Spring AI 2.1.0, `ToolResponseMessage.getResults()` giữ đầy đủ `ToolResultPart`; `getResponses()` chỉ là view text-only.
- Ghép bằng tool-call ID khi có ID duy nhất; nếu provider không phát ID, chỉ ghép theo vị trí khi adapter bảo đảm thứ tự.
- `ToolCallingAdvisor` tự giữ history trong vòng lặp; manual `ChatModel` path nên dùng `ToolExecutionResult.conversationHistory()`.
- Session Memory lưu event log có tool call và tool result; tránh cắt giữa một turn khi compact history.
- Giữ `MessagePart` order, provider payload và attributes nếu cần replay cùng provider.
- History là dữ liệu thực thi nhạy cảm: lấy từ server, xác thực quyền và chống replay.

Khi lưu hoặc khôi phục hội thoại có tool calling, hãy xem assistant tool request và tool response là hai nửa của cùng một giao dịch giao thức. Giữ nguyên ID, tên, thứ tự và cấu trúc message; kiểm tra mọi call có result hợp lệ trước khi tiếp tục. Dùng `ToolCallingAdvisor` hoặc `ToolCallingManager` để tạo history chuẩn, và dùng Session Memory khi cần lưu đầy đủ transcript qua nhiều request.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling và Memory trong Tool Loop](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 — ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html)
- [Spring AI 2.1.0 API — ToolResponseMessage](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/messages/ToolResponseMessage.html)
- [Spring AI 2.1.0 API — ToolResultPart](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/chat/messages/part/ToolResultPart.html)
- [Spring AI 2.1.0 — Session Memory](https://docs.spring.io/spring-ai/reference/api/session.html)
