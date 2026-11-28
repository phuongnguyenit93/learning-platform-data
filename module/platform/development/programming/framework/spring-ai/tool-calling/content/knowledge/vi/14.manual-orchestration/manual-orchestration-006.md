# Giữ đúng tool call ID, thứ tự thông điệp và kết quả

Khi tự điều phối tool calling trong Spring AI, ứng dụng phải giữ nguyên mối liên hệ giữa yêu cầu gọi tool của mô hình và kết quả thực thi. Mỗi yêu cầu có một **tool call ID**; kết quả phải trả lời đúng ID đó, giữ đúng tên tool và xuất hiện trong lịch sử hội thoại sau thông điệp assistant chứa yêu cầu gọi tool.

Một vòng lặp có thể gọi nhiều tool trong cùng một lượt. Nếu thực thi song song, thứ tự hoàn thành có thể khác thứ tự mô hình yêu cầu. Ứng dụng vẫn phải tạo các tool result theo thứ tự của danh sách tool call ban đầu và ghép đúng ID. Nếu ghép nhầm, bỏ sót hoặc đảo thông điệp, provider có thể từ chối request tiếp theo hoặc mô hình nhận kết quả của tool khác.

Bài viết sử dụng Spring AI 2.1 và tập trung vào đường đi dữ liệu từ `ChatResponse` đến `ToolResponseMessage`, cách dùng `ToolCallingManager` để giữ lịch sử, cách tự ghép message khi có executor riêng và cách kiểm thử nhiều tool call.

## 1. Vì sao tool call ID quan trọng?

Một tool call không chỉ là tên hàm và JSON arguments. Trong `AssistantMessage.ToolCall`, Spring AI biểu diễn mỗi yêu cầu bằng bốn trường:

| Trường | Ý nghĩa |
|---|---|
| `id` | Định danh của lần gọi tool cụ thể do model/provider trả về |
| `type` | Loại tool call, thường là `function` |
| `name` | Tên tool mà ứng dụng cần phân giải |
| `arguments` | Chuỗi JSON chứa đối số |

Ví dụ, mô hình yêu cầu hai lần gọi cùng một tool:

~~~json
{
  "tool_calls": [
    {
      "id": "call_inv_01",
      "type": "function",
      "name": "lookupInventory",
      "arguments": "{\"sku\":\"SKU-100\",\"warehouse\":\"HANOI\"}"
    },
    {
      "id": "call_inv_02",
      "type": "function",
      "name": "lookupInventory",
      "arguments": "{\"sku\":\"SKU-200\",\"warehouse\":\"DANANG\"}"
    }
  ]
}
~~~

Hai call có cùng `name` nhưng là hai thao tác độc lập. `call_inv_01` tra cứu SKU-100; `call_inv_02` tra cứu SKU-200.

Kết quả phải giữ đúng cặp:

- `call_inv_01` nhận kết quả tra cứu SKU-100.
- `call_inv_02` nhận kết quả tra cứu SKU-200.

Không dùng tên tool làm khóa duy nhất vì một tool có thể được gọi nhiều lần trong cùng một response. Không tự sinh ID mới cho kết quả, vì ID đó không khớp với yêu cầu mà mô hình đã gửi.

## 2. Thứ tự message trong một vòng tool calling

Một cuộc hội thoại có tool call cần giữ trình tự message:

~~~mermaid
sequenceDiagram
    participant U as User
    participant M as ChatModel
    participant A as AssistantMessage
    participant T as ToolCallback
    participant R as ToolResponseMessage

    U->>M: UserMessage
    M-->>A: AssistantMessage chứa tool calls
    Note over A: call_01 và call_02 theo thứ tự model trả về
    A->>T: Thực thi từng call với arguments tương ứng
    T-->>R: ToolResponse cho call_01
    T-->>R: ToolResponse cho call_02
    Note over R: ID, tên và thứ tự khớp với assistant tool calls
    R->>M: Gửi lại toàn bộ conversation history
    M-->>U: AssistantMessage cuối cùng
~~~

Lịch sử tối thiểu cho lượt có tool call gồm:

1. Các message trước đó, bao gồm `UserMessage`.
2. `AssistantMessage` chứa danh sách tool call mà mô hình vừa yêu cầu.
3. `ToolResponseMessage` chứa kết quả tương ứng cho từng tool call.
4. Response assistant tiếp theo sau khi mô hình nhận kết quả.

Assistant tool-call message phải nằm trước tool response message. Nếu xóa assistant message hoặc chỉ gửi riêng kết quả tool, mô hình sẽ không còn thấy yêu cầu nào mà những kết quả đó đang trả lời.

Trong Spring AI 2.1, `ToolResponseMessage` giữ một danh sách result có thứ tự. Mỗi `ToolResponseMessage.ToolResponse` có ba trường:

- `id`: ID của tool call mà kết quả trả lời.
- `name`: tên tool.
- `responseData`: nội dung kết quả dạng chuỗi.

Do đó, mỗi tool call cần một tool response tương ứng. Giữ nguyên thứ tự call trong message để lịch sử dễ kiểm tra và tương thích với giao thức của provider.

## 3. Cách an toàn nhất: dùng ToolCallingManager

Khi tự điều phối bằng `ChatModel` trong Spring AI 2.x, `ChatModel` chỉ trả response thô. Nó không tự thực thi tool call. `ToolCallingManager` đảm nhiệm việc phân giải callback, thực thi các tool call và tạo `ToolExecutionResult`.

Ví dụ vòng lặp đồng bộ:

~~~java
ChatModel chatModel = ...;

// Spring Boot có thể cung cấp ToolCallingManager tự động.
// Nếu không dùng auto-configuration, tạo manager bằng builder.
ToolCallingManager toolCallingManager =
    ToolCallingManager.builder().build();

ToolCallback[] tools = ToolCallbacks.from(new InventoryTools());

ChatOptions chatOptions = ToolCallingChatOptions.builder()
    .toolCallbacks(tools)
    .build();

Prompt prompt = new Prompt(
    "Tra cứu SKU-100 tại kho HANOI và SKU-200 tại kho DANANG.",
    chatOptions
);

ChatResponse response = chatModel.call(prompt);

while (response.hasToolCalls()) {
    ToolExecutionResult execution =
        toolCallingManager.executeToolCalls(prompt, response);

    if (execution.returnDirect()) {
        // Ứng dụng trả lịch sử có kết quả tool trực tiếp cho caller.
        return execution.conversationHistory();
    }

    // Giữ nguyên lịch sử mà manager đã tạo.
    prompt = new Prompt(execution.conversationHistory(), chatOptions);
    response = chatModel.call(prompt);
}

String finalAnswer = response.getResult().getOutput().getText();
~~~

`executeToolCalls(prompt, response)` xử lý các yêu cầu gọi tool trong response và trả về `ToolExecutionResult`. Thuộc tính `conversationHistory()` chứa các message gốc, assistant tool-call request và tool responses đã thực thi.

Vì vậy, khi dùng manager, hãy dùng nguyên `conversationHistory()` làm message của prompt tiếp theo. Không thêm lại assistant message hoặc tool response lần nữa; làm vậy sẽ tạo bản sao của cùng một lượt gọi.

### 3.1. Những gì manager giữ giúp ứng dụng

| Công việc | Trách nhiệm của ToolCallingManager |
|---|---|
| Đọc tool call | Lấy danh sách call từ assistant response |
| Tìm callback | Phân giải callback theo tên tool |
| Chuyển đối số | Gửi JSON arguments đến callback |
| Truyền context | Chuyển `ToolContext` do ứng dụng cung cấp |
| Thực thi | Gọi callback tương ứng |
| Tạo kết quả | Tạo tool response gắn với call được thực thi |
| Cập nhật lịch sử | Trả về conversation history có assistant call và tool result |
| Return direct | Báo hiệu kết quả cần trả thẳng cho caller |

`ToolExecutionResult.returnDirect()` cho biết kết quả có cần gửi lại mô hình hay trả trực tiếp cho caller. Khi một lượt có nhiều tool call, kết quả chỉ được coi là return-direct nếu tất cả tool được gọi trong lượt đó đều có cấu hình return-direct.

## 4. Tự tạo ToolResponseMessage khi có executor riêng

Trong một số ứng dụng, executor riêng cần điều khiển cách dispatch, chạy song song hoặc ghi nhận kết quả. Khi đó, ứng dụng có thể tự tạo tool response.

Trước hết, lấy đúng assistant message và danh sách call:

~~~java
AssistantMessage assistantMessage =
    response.getResult().getOutput();

List<AssistantMessage.ToolCall> calls =
    assistantMessage.getToolCalls();
~~~

Không tự tạo lại các tool call từ JSON đã parse. Hãy giữ nguyên đối tượng call mà model trả về để bảo toàn ID, tên và arguments.

Sau khi thực thi từng call, tạo `ToolResponse` bằng ID và tên lấy trực tiếp từ call đó:

~~~java
List<ToolResponseMessage.ToolResponse> toolResponses =
    calls.stream()
        .map(call -> {
            String responseData = executeToolSafely(
                call.name(),
                call.arguments()
            );

            return new ToolResponseMessage.ToolResponse(
                call.id(),
                call.name(),
                responseData
            );
        })
        .toList();
~~~

Tạo message kết quả:

~~~java
ToolResponseMessage toolResponseMessage =
    ToolResponseMessage.builder()
        .responses(toolResponses)
        .build();
~~~

Sau đó nối message theo đúng thứ tự:

~~~java
List<Message> nextMessages =
    new ArrayList<>(prompt.getInstructions());

nextMessages.add(assistantMessage);
nextMessages.add(toolResponseMessage);

Prompt nextPrompt = new Prompt(nextMessages, chatOptions);
ChatResponse nextResponse = chatModel.call(nextPrompt);
~~~

Các đoạn trên là mẫu cho đường thực thi tùy chỉnh. `executeToolSafely` đại diện cho hàm dispatch do ứng dụng triển khai: tìm callback được phép, xác thực arguments, truyền context và chuyển lỗi thành kết quả an toàn. Nếu không cần custom executor, hãy để `ToolCallingManager` thực hiện các bước này.

Lưu ý: `ToolResponseMessage.Builder.responses(List)` tạo các result dạng văn bản. Trong Spring AI 2.1, khi cần giữ nội dung phong phú như media hoặc cờ lỗi trong `ToolResultPart`, dùng `result(...)`, `results(...)` hoặc `parts(...)` và đọc bằng `getResults()`. `getResponses()` chỉ là góc nhìn text của các result part.

## 5. Nhiều tool call trong cùng một lượt

Một response có thể chứa nhiều tool call. Có hai chiến lược thực thi:

- **Tuần tự:** phù hợp khi tool sau phụ thuộc kết quả tool trước hoặc thao tác có thứ tự nghiệp vụ.
- **Song song:** phù hợp khi các call độc lập và không chia sẻ trạng thái có thể xung đột.

Dù dùng chiến lược nào, danh sách tool response cuối cùng phải tương ứng với thứ tự ban đầu của `assistantMessage.getToolCalls()`.

Ví dụ:

| Vị trí trong assistant message | Tool call ID | Tool | Arguments |
|---:|---|---|---|
| 0 | `call_01` | `lookupInventory` | SKU-100 |
| 1 | `call_02` | `lookupInventory` | SKU-200 |
| 2 | `call_03` | `lookupCustomer` | CUS-50 |

Giả sử `call_03` hoàn thành trước, `call_01` hoàn thành thứ hai và `call_02` hoàn thành cuối cùng. Khi ghép kết quả, thứ tự vẫn là `call_01`, `call_02`, `call_03`. Thời điểm hoàn thành không được quyết định vị trí result trong message.

### 5.1. Chạy song song nhưng thu kết quả theo thứ tự gốc

Có thể giữ một future cho mỗi call trong danh sách ban đầu:

~~~java
List<CompletableFuture<ToolResponseMessage.ToolResponse>> pending =
    calls.stream()
        .map(call -> CompletableFuture.supplyAsync(() -> {
            String data = executeToolSafely(
                call.name(),
                call.arguments()
            );

            return new ToolResponseMessage.ToolResponse(
                call.id(),
                call.name(),
                data
            );
        }, executor))
        .toList();

// Stream này duyệt futures theo thứ tự gốc của calls,
// dù các tác vụ có thể hoàn thành theo thứ tự khác.
List<ToolResponseMessage.ToolResponse> orderedResponses =
    pending.stream()
        .map(CompletableFuture::join)
        .toList();
~~~

Danh sách `pending` được tạo theo thứ tự `calls`. Gọi `join()` lần lượt trên danh sách này sẽ thu kết quả theo đúng thứ tự đầu vào, kể cả khi future phía sau đã hoàn thành sớm hơn.

Không nên thêm result vào một danh sách dùng chung ngay khi mỗi tác vụ hoàn thành. Cách đó khiến thứ tự phụ thuộc vào tốc độ của tool và có thể làm kết quả không còn khớp với thứ tự model yêu cầu.

Chỉ chạy song song khi các thao tác độc lập. Nếu hai tool cùng cập nhật một tài nguyên, phụ thuộc dữ liệu hoặc cần thứ tự giao dịch, hãy thực thi tuần tự hoặc dùng cơ chế đồng bộ nghiệp vụ.

## 6. Không nhầm tool call ID với tool name hoặc index

Ba giá trị này có ý nghĩa khác nhau:

| Giá trị | Dùng để làm gì? | Có duy nhất không? |
|---|---|---|
| Tool call ID | Liên kết một response với lần gọi cụ thể | Thường duy nhất trong một reply; phụ thuộc provider |
| Tool name | Tìm callback thực thi | Có thể xuất hiện nhiều lần trong một reply |
| Vị trí trong danh sách | Giữ thứ tự và đối chiếu nội bộ | Duy nhất trong một reply |

Ví dụ, hai lần gọi `lookupInventory` có thể có cùng tên nhưng khác ID và arguments. Nếu dùng `toolName` làm khóa Map để lưu kết quả, lần gọi thứ hai có thể ghi đè lần thứ nhất.

Trong executor tùy chỉnh, có thể giữ index cùng đối tượng call:

~~~java
record IndexedToolCall(
    int index,
    AssistantMessage.ToolCall call
) {}
~~~

Index hữu ích cho việc theo dõi và khôi phục thứ tự. Khi tạo tool response, vẫn lấy ID và tên từ đối tượng call gốc.

### 6.1. Provider thiếu ID hoặc trả ID trùng

Một số provider có thể không trả ID hoặc có thể trả hai call cùng ID. Không nên mặc định ID luôn là khóa duy nhất cho mọi trường hợp.

- Giữ nguyên thứ tự và đối tượng assistant reply gốc.
- Dùng vị trí trong reply làm khóa tương quan nội bộ khi ID thiếu hoặc trùng.
- Không sửa ID trong assistant reply đã nhận.
- Với luồng xác nhận tool call của Spring AI 2.1, dùng `ToolCallDecisions.toolCallKeys(assistantMessage)` để tạo khóa quyết định: ID nếu duy nhất, nếu không thì dùng khóa vị trí như `#0`, `#1`.
- Khóa vị trí của `ToolCallDecisions` phục vụ ánh xạ quyết định xác nhận; không tự ý thay nó vào trường ID của tool response.

Nếu tích hợp provider có quy tắc riêng cho call thiếu ID, cần kiểm tra adapter/provider đó và giữ nguyên dữ liệu mà nó mong đợi. Không tự đoán ID thay thế.

## 7. Xử lý lỗi mà không làm mất liên kết

Nếu một tool thất bại, vòng hội thoại vẫn cần một kết quả gắn với đúng call. Với lỗi có thể phục hồi, ứng dụng có thể trả thông báo lỗi đã làm sạch làm tool result để mô hình giải thích hoặc đề xuất bước tiếp theo.

Ví dụ:

~~~json
{
  "error": "INVENTORY_SERVICE_UNAVAILABLE",
  "message": "Không thể tra cứu tồn kho lúc này. Vui lòng thử lại."
}
~~~

Tool response vẫn phải giữ ID và tên của call ban đầu:

~~~java
new ToolResponseMessage.ToolResponse(
    call.id(),
    call.name(),
    safeErrorJson
);
~~~

Không gửi stack trace, SQL, token, địa chỉ nội bộ hoặc dữ liệu nhạy cảm vào response cho mô hình. Ghi log chi tiết ở phía server với correlation ID phù hợp; trả về mã lỗi và thông điệp an toàn.

Khi dùng `ToolCallingManager`, lỗi callback đi qua `ToolExecutionExceptionProcessor`. Processor có thể chuyển lỗi thành thông điệp tool result hoặc ném lỗi về caller tùy chính sách. Với custom executor, ứng dụng phải tự thực hiện chính sách tương đương và bảo đảm mỗi call trong batch được xử lý rõ ràng.

Không bỏ qua một call bị lỗi rồi gửi response của các call còn lại như thể batch đã hoàn tất. Nếu vẫn tiếp tục, phải tạo một kết quả lỗi có cùng ID cho call thất bại hoặc dừng lượt và xử lý lỗi ở cấp ứng dụng theo hợp đồng đã chọn.

## 8. Return direct và kết thúc vòng lặp

Mặc định, tool result được gửi lại cho mô hình để mô hình tiếp tục suy luận và tạo câu trả lời cuối.

Nếu tool được cấu hình `returnDirect = true`, `ToolCallingManager` có thể yêu cầu ứng dụng trả kết quả trực tiếp mà không gọi mô hình thêm. Kiểm tra `ToolExecutionResult.returnDirect()` trước khi tạo prompt kế tiếp.

Khi có nhiều tool call trong một lượt, `returnDirect()` chỉ là `true` nếu tất cả tool được gọi đều có cấu hình return-direct. Không tự bỏ qua các tool result còn lại chỉ vì một call trong batch có return-direct.

## 9. Streaming: chỉ xử lý tool call hoàn chỉnh

Trong streaming, provider có thể gửi từng phần của tool call. Các phần này có thể chứa ID, tên hoặc một đoạn JSON arguments chưa hoàn chỉnh.

Không thực thi một partial tool call. Một mảnh arguments riêng lẻ thường chưa phải JSON hợp lệ và có thể chưa có đủ ID hoặc tên. Hãy aggregate stream thành response hoàn chỉnh rồi mới kiểm tra `response.hasToolCalls()` và gọi tool.

Spring AI có `MessageAggregator` và `ChatClientMessageAggregator` để ghép các chunk. `AssistantMessage.getToolCalls()` và `hasToolCalls()` bỏ qua các `ToolCallPart` còn partial; tool call hoàn chỉnh được phát sau đó mới được thực thi.

Nếu cần hiển thị tiến độ, có thể gửi các delta đến UI dưới dạng trạng thái đang tạo arguments. Không ghi delta đó thành message tool call hoàn chỉnh trong conversation history.

## 10. Kiểm thử ID, thứ tự và lịch sử

Một bộ test tốt nên kiểm tra cả ba khía cạnh: liên kết ID, thứ tự result và trình tự message.

| Trường hợp | Điều cần xác minh |
|---|---|
| Một tool call | Tool response dùng đúng ID và tên |
| Hai call cùng tool name | Hai result có ID và arguments riêng |
| Nhiều call khác tên | Mỗi result khớp đúng callback |
| Tool hoàn thành không theo thứ tự | Danh sách response vẫn theo thứ tự call ban đầu |
| Một call thất bại | Error result vẫn gắn đúng ID |
| ID thiếu hoặc trùng | Executor dùng index nội bộ, không ghi đè kết quả |
| Assistant message | Được giữ nguyên trong lịch sử |
| Tool response message | Nằm sau assistant tool-call message |
| Lượt model tiếp theo | Nhận toàn bộ lịch sử có tool results |
| Return direct | Không gọi model thêm khi kết quả cần trả trực tiếp |
| Streaming | Partial tool call không bị thực thi |

Ví dụ kiểm thử việc ghép kết quả theo ID:

~~~java
@Test
void toolResponsesKeepCallIdsAndOriginalOrder() {
    AssistantMessage.ToolCall first =
        new AssistantMessage.ToolCall(
            "call_01", "function", "lookupInventory",
            "{\"sku\":\"SKU-100\"}"
        );

    AssistantMessage.ToolCall second =
        new AssistantMessage.ToolCall(
            "call_02", "function", "lookupInventory",
            "{\"sku\":\"SKU-200\"}"
        );

    List<ToolResponseMessage.ToolResponse> responses = List.of(
        new ToolResponseMessage.ToolResponse(
            first.id(), first.name(), "{\"quantity\":12}"
        ),
        new ToolResponseMessage.ToolResponse(
            second.id(), second.name(), "{\"quantity\":4}"
        )
    );

    ToolResponseMessage message = ToolResponseMessage.builder()
        .responses(responses)
        .build();

    assertThat(message.getResponses())
        .extracting(ToolResponseMessage.ToolResponse::id)
        .containsExactly("call_01", "call_02");

    assertThat(message.getResponses())
        .extracting(ToolResponseMessage.ToolResponse::responseData)
        .containsExactly("{\"quantity\":12}", "{\"quantity\":4}");
}
~~~

Ngoài test builder, hãy có integration test cho vòng lặp thủ công:

1. Model giả lập trả về assistant message có hai tool call.
2. Callback được gọi với đúng arguments của từng call.
3. Manager hoặc custom executor tạo đủ hai tool response.
4. Lịch sử có assistant message trước tool response message.
5. Lượt model tiếp theo nhận cả hai kết quả.
6. Response cuối không còn tool call và được trả về caller.

Không cần gọi model thật cho unit test. Dùng mock callback và response cố định để kiểm tra thứ tự, ID và số lần gọi chính xác.

## 11. Khác biệt phiên bản cần nhớ

Trong Spring AI 1.x, mỗi implementation `ChatModel` có vòng lặp tool calling nội bộ. Ứng dụng thường không nhìn thấy các message trung gian được trao đổi với model.

Từ Spring AI 2.0, vòng lặp nội bộ được loại bỏ khỏi `ChatModel`. Khi gọi `chatModel.call(prompt)`, ứng dụng nhận response có tool call và phải tự điều phối bằng `ToolCallingManager` hoặc dùng `ChatClient` với `ToolCallingAdvisor`.

Spring AI 2.1 tiếp tục làm rõ mô hình message:

- `AssistantMessage.ToolCall` biểu diễn ID, type, name và arguments.
- `ToolResponseMessage.ToolResponse` biểu diễn ID, tên tool và response text.
- `ToolResponseMessage` chứa ordered result parts.
- `getResults()` trả về các `ToolResultPart`; `getResponses()` trả về góc nhìn text của kết quả.
- Tránh truy cập field `responses` đã deprecated; dùng accessor hoặc builder.

Nếu đang nâng cấp từ 1.x, hãy kiểm tra nơi ứng dụng đang giữ conversation history và chuyển logic nối message vào lớp điều phối của ứng dụng. Không giả định `ChatModel` tiếp tục tự thêm assistant tool-call message và tool response như phiên bản cũ.

## 12. Checklist trước khi gửi lịch sử trở lại model

- [ ] Giữ nguyên assistant message có tool calls từ response gốc.
- [ ] Tạo một tool response cho mỗi tool call được xử lý.
- [ ] Sao chép đúng ID và tên từ từng tool call.
- [ ] Không dùng tool name làm khóa duy nhất.
- [ ] Giữ thứ tự result giống thứ tự call ban đầu.
- [ ] Nếu chạy song song, thu futures theo thứ tự danh sách gốc.
- [ ] Nối assistant message trước tool response message.
- [ ] Không gửi trùng assistant call hoặc tool result trong history.
- [ ] Xử lý lỗi bằng response an toàn hoặc dừng lượt theo chính sách.
- [ ] Kiểm tra `returnDirect()` trước khi gọi model tiếp.
- [ ] Aggregate streaming tool call trước khi thực thi.
- [ ] Kiểm thử trường hợp cùng tên tool, ID thiếu/trùng và hoàn thành không theo thứ tự.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html): manual loop, `ToolCallingManager`, `ToolExecutionResult` và conversation history.
- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): tool execution, result conversion, error handling, tool call limits và user-controlled execution.
- [AssistantMessage.ToolCall API — 2.1.x](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/messages/AssistantMessage.ToolCall.html): cấu trúc ID, type, name và arguments.
- [ToolResponseMessage API — 2.1.x](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/messages/ToolResponseMessage.html): ordered result parts, `getResults()` và `getResponses()`.
- [ToolResponseMessage.ToolResponse API — 2.1.x](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/messages/ToolResponseMessage.ToolResponse.html): ý nghĩa của ID, name và responseData.
- [Tool Call Confirmation — Spring AI 2.1](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/tools/confirmation.html): khóa quyết định theo ID hoặc vị trí khi ID bị thiếu/trùng.

Giữ nguyên tool call ID, assistant message và thứ tự result là điều kiện để mô hình hiểu chính xác kết quả nào trả lời yêu cầu nào. Khi dùng `ToolCallingManager`, Spring AI tạo lịch sử đã ghép; khi tự xây executor, ứng dụng phải bảo đảm mọi kết quả khớp ID và thứ tự của reply ban đầu.

