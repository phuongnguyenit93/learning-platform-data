# Cơ chế tự đăng ký advisor khi dùng ChatClient theo phiên bản

Spring AI cần một thành phần điều phối vòng lặp tool calling: gửi prompt và danh sách tool đến mô hình, nhận tool call, thực thi callback, đưa kết quả trở lại mô hình rồi tiếp tục cho đến khi mô hình trả lời bình thường. Thành phần điều phối này thay đổi theo phiên bản.

- **Spring AI 1.x:** vòng thực thi tool nằm bên trong từng implementation của `ChatModel`. Khi dùng `ChatClient` và cung cấp tool, model tự thực hiện các lượt gọi tiếp theo.
- **Spring AI 2.0.x:** vòng lặp được chuyển ra khỏi `ChatModel` sang `ToolCallingAdvisor`. `ChatClient` tự đăng ký advisor khi request có tool.
- **Spring AI 2.1.x:** `DefaultChatClient` tự đăng ký `ToolCallingAdvisor` trong advisor chain, kể cả khi tool được một advisor khác bổ sung lúc chạy. Cơ chế này có thể được tắt toàn cục hoặc theo từng request.

Hiểu đúng thay đổi này giúp tránh hai lỗi thường gặp: thêm advisor thủ công trong khi `ChatClient` đã tự đăng ký, khiến vòng lặp bị cấu hình trùng; hoặc gọi trực tiếp `ChatModel` trong 2.x rồi chờ tool tự chạy dù model chỉ trả về yêu cầu gọi tool.

## 1. Advisor tham gia vào tool calling như thế nào?

`Advisor` là thành phần nằm trong chuỗi xử lý của `ChatClient`. Advisor có thể đọc hoặc thay đổi request trước khi gửi đến mô hình, tiếp nhận response sau khi mô hình trả lời, hoặc điều phối thêm các lượt gọi.

`ToolCallingAdvisor` là advisor chuyên trách vòng đời thực thi tool. Nó kết hợp `ToolCallingManager` để phân giải và gọi callback. Khi mô hình trả về tool call, advisor thực thi tool rồi gửi lịch sử hội thoại có tool result trở lại mô hình. Quá trình tiếp tục cho đến khi response không còn tool call hoặc một điều kiện kết thúc khác được áp dụng.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as ChatClient
    participant A as ToolCallingAdvisor
    participant M as ChatModel
    participant T as ToolCallingManager
    participant B as ToolCallback

    U->>C: Câu hỏi
    C->>A: ChatClientRequest
    A->>M: Prompt + tool definitions
    M-->>A: Tool call + JSON arguments
    A->>T: Thực thi tool call
    T->>B: Gọi callback
    B-->>T: Tool result
    T-->>A: ToolExecutionResult
    A->>M: Lịch sử hội thoại + tool result
    M-->>A: Response tiếp theo
    Note over A,M: Lặp lại nếu response còn tool call
    A-->>C: Câu trả lời cuối
    C-->>U: Nội dung phản hồi
~~~

Mô hình chỉ yêu cầu gọi tool và cung cấp đối số. Ứng dụng vẫn kiểm soát callback nào được cung cấp, việc xác thực quyền, thao tác nghiệp vụ và kết quả được trả về. `ToolCallingAdvisor` tự động hóa vòng lặp; nó không chuyển quyền thực thi API nghiệp vụ sang mô hình.

## 2. So sánh cơ chế theo phiên bản

| Phiên bản | Vị trí điều phối tool loop | Hành vi khi dùng ChatClient | Điểm cần lưu ý |
|---|---|---|---|
| Spring AI 1.0.x và 1.1.x | Bên trong implementation `ChatModel` thông qua `ToolCallingManager` | Cung cấp tool cho ChatClient; model thực hiện vòng gọi tool nội bộ | `internalToolExecutionEnabled` điều khiển việc thực thi nội bộ |
| Spring AI 2.0.0 | `ToolCallingAdvisor` trong advisor chain | `ChatClient` tự đăng ký advisor khi request có tool | Vòng lặp nội bộ trong `ChatModel` đã bị loại bỏ |
| Spring AI 2.0.1 và 2.0.x | `ToolCallingAdvisor` | Cơ chế advisor tiếp tục điều phối; fallback phân giải tool toàn cục bị tắt mặc định từ 2.0.1 | Tool cần được gắn rõ vào request hoặc default tools |
| Spring AI 2.1.x | `ToolCallingAdvisor` | `DefaultChatClient` tự đăng ký advisor mặc định, kể cả khi tool được thêm động bởi advisor khác | Có thể opt out; `ToolAdvisor` marker ngăn đăng ký trùng |

Khác biệt quan trọng nhất nằm giữa 1.x và 2.x: 1.x để từng model implementation điều phối nội bộ, còn 2.x đưa vòng lặp lên tầng advisor của `ChatClient`. Trong 2.1, cơ chế tự đăng ký được mở rộng để hỗ trợ tool có thể chỉ xuất hiện sau khi một advisor khác xử lý request.

## 3. Spring AI 1.x: ChatModel thực hiện vòng lặp nội bộ

Trong Spring AI 1.x, các implementation `ChatModel` có vòng thực thi tool nội bộ. Khi ứng dụng gọi `chatModel.call(prompt)` với tool callbacks, model gọi provider, nhận tool call, dùng `ToolCallingManager` thực thi callback rồi gửi tool result trở lại model. Model tiếp tục gọi cho đến khi không còn tool call.

Vì vậy, ví dụ `ChatClient` đơn giản có thể dùng trực tiếp POJO chứa phương thức `@Tool`:

~~~java
@Component
class InventoryTools {

    private final InventoryService inventoryService;

    InventoryTools(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @Tool(description = "Tra cứu tồn kho theo SKU và mã kho.")
    StockView lookupInventory(
            String sku,
            String warehouse) {
        return inventoryService.lookup(sku, warehouse);
    }
}
~~~

Dùng tool trong request:

~~~java
String answer = ChatClient.create(chatModel)
    .prompt("Kiểm tra SKU-100 tại kho Hà Nội.")
    .tools(inventoryTools)
    .call()
    .content();
~~~

Trong 1.x, `ChatClient` chuyển tool definitions/callbacks đến `ChatModel`. Vòng lặp tự thực thi nằm trong model implementation; ứng dụng không cần tự thêm một advisor để xử lý từng tool call trong luồng mặc định.

### 3.1. Điều khiển thực thi nội bộ

Trong 1.x, `ToolCallingChatOptions` và một số provider-specific options có thuộc tính `internalToolExecutionEnabled`. Khi tắt, model trả về tool call để ứng dụng tự xử lý thay vì chạy callback tự động.

Ví dụ cấu hình khái niệm:

~~~java
ToolCallingChatOptions options = ToolCallingChatOptions.builder()
    .toolCallbacks(ToolCallbacks.from(inventoryTools))
    .internalToolExecutionEnabled(false)
    .build();
~~~

Tên option và khả năng cấu hình có thể khác theo provider, nhưng đây là mô hình điều khiển của 1.x.

Khi nâng cấp lên 2.0, không tiếp tục dùng thuộc tính này. `internalToolExecutionEnabled` và các property tương ứng đã bị loại bỏ vì vòng thực thi không còn nằm trong `ChatModel`.

## 4. Spring AI 2.0: vòng lặp chuyển sang ToolCallingAdvisor

Từ Spring AI 2.0, vòng thực thi tool nội bộ đã bị loại bỏ khỏi tất cả implementation `ChatModel`. Khi gọi trực tiếp `chatModel.call(prompt)` hoặc `chatModel.stream(prompt)`, ứng dụng nhận response thô từ mô hình; tool call không tự được thực thi.

Cơ chế được chuyển sang `ToolCallingAdvisor`, một recursive advisor chịu trách nhiệm:

1. Gửi request đến advisor/model tiếp theo.
2. Kiểm tra response có tool call hay không.
3. Dùng `ToolCallingManager` thực thi callback.
4. Bổ sung tool call và tool result vào lịch sử hội thoại.
5. Gọi model tiếp lần nữa.
6. Kết thúc khi response không còn tool call.

Trong Spring AI 2.0.0, `ChatClient` tự đăng ký `ToolCallingAdvisor` khi request có tool. Vì vậy, ứng dụng vẫn có thể dùng cú pháp đơn giản:

Tên lớp advisor cũng được đổi trong lần nâng cấp này: `ToolCallAdvisor` ở API cũ được đổi thành `ToolCallingAdvisor` trong 2.0. Việc đổi tên đi cùng với thay đổi lớn hơn: vòng lặp thực thi được chuyển từ `ChatModel` sang advisor của `ChatClient`.

~~~java
String answer = ChatClient.create(chatModel)
    .prompt("Kiểm tra SKU-100 tại kho Hà Nội.")
    .tools(inventoryTools)
    .call()
    .content();
~~~

Không cần gọi `ToolCallingAdvisor.builder()` thủ công trong trường hợp thông thường.

### 4.1. Vì sao không nên gọi ChatModel trực tiếp rồi chờ callback tự chạy?

Ví dụ sau chỉ gọi model một lần:

~~~java
ChatResponse response = chatModel.call(prompt);
~~~

Trong 2.x, nếu response chứa tool call, đó là yêu cầu mà model trả về. `ChatModel` không tự thực thi callback và cũng không tự gọi lại model.

Nếu ứng dụng thực sự cần gọi `ChatModel` trực tiếp, phải tự điều phối bằng `ToolCallingManager`:

~~~java
ChatResponse response = chatModel.call(prompt);

if (response.hasToolCalls()) {
    ToolExecutionResult result =
        toolCallingManager.executeToolCalls(prompt, response);

    Prompt nextPrompt = new Prompt(
        result.conversationHistory(),
        chatOptions
    );

    response = chatModel.call(nextPrompt);
}
~~~

Đoạn code minh họa một lượt xử lý. Ứng dụng thực tế cần lặp lại cho đến khi response không còn tool call, đồng thời giới hạn số lượt và xử lý lỗi. Với phần lớn luồng hội thoại, dùng `ChatClient` để `ToolCallingAdvisor` quản lý vòng lặp sẽ đơn giản hơn.

## 5. Spring AI 2.1: advisor được tự đăng ký ngay cả khi tool được thêm động

Ở Spring AI 2.1, `DefaultChatClient` tự đăng ký `ToolCallingAdvisor` trong advisor chain trừ khi cơ chế này bị tắt hoặc chain đã có một advisor triển khai `ToolAdvisor`.

Điểm thay đổi so với 2.0.0 là advisor được đăng ký ngay cả khi request ban đầu chưa có tool. Điều này quan trọng khi một advisor khác tìm kiếm hoặc bổ sung tool trong lúc xử lý request.

Ví dụ, advisor tìm kiếm có thể bổ sung tool sau khi đọc câu hỏi:

~~~java
ChatClient chatClient = ChatClient.builder(chatModel)
    .defaultAdvisors(toolDiscoveryAdvisor)
    .build();

String answer = chatClient.prompt()
    .user("Tra cứu tình trạng đơn hàng gần nhất của tôi.")
    .call()
    .content();
~~~

Nếu `toolDiscoveryAdvisor` thêm tool vào request tại runtime, `ToolCallingAdvisor` đã có trong chain để tiếp tục xử lý tool call mà model trả về.

Trong trường hợp không có tool nào được thêm và model không trả tool call, advisor kết thúc sau response bình thường. Việc advisor được đăng ký không có nghĩa mọi request đều phải gọi tool.

### 5.1. ToolAdvisor marker và quy tắc chỉ có một tool advisor

`ToolCallingAdvisor` triển khai marker interface `ToolAdvisor`. `DefaultChatClient` kiểm tra advisor chain:

- Nếu chưa có advisor nào triển khai `ToolAdvisor`, `ChatClient` tự đăng ký `ToolCallingAdvisor` mặc định.
- Nếu chain đã có một `ToolAdvisor`, việc tự đăng ký advisor mặc định được bỏ qua.
- Nếu có nhiều advisor tùy chỉnh cùng triển khai `ToolAdvisor`, việc tạo chain thất bại để tránh hai vòng tool calling cùng thực thi một tool call.

Nếu xây dựng custom advisor sở hữu toàn bộ vòng đời tool calling, hãy triển khai `ToolAdvisor` để `ChatClient` nhận biết rằng chain đã có thành phần điều phối tool.

Chain chỉ nên có một advisor sở hữu vòng đời tool calling. Nếu muốn thay advisor mặc định bằng cấu hình riêng, hãy để custom advisor triển khai `ToolAdvisor` hoặc tắt auto-registration cho request trước khi thêm advisor điều phối thủ công.

## 6. Tắt tự đăng ký trên toàn ứng dụng

Spring AI 2.x cung cấp property:

~~~yaml
spring:
  ai:
    chat:
      client:
        tool-calling:
          enabled: false
~~~

Property `spring.ai.chat.client.tool-calling.enabled` mặc định là `true`. Đặt `false` để tắt việc tự đăng ký `ToolCallingAdvisor` cho các `ChatClient` được auto-configure.

Khi tắt:

- Các tool được truyền qua `.tools(...)` vẫn có thể được gửi dưới dạng tool definitions cho model.
- Response có tool call không được tự động thực thi qua advisor mặc định.
- Ứng dụng phải tự điều phối việc gọi callback, ví dụ dùng `ToolCallingManager`.

Property này hữu ích khi ứng dụng muốn kiểm soát vòng lặp tập trung ở một orchestrator riêng hoặc đang xây dựng cơ chế xác nhận tool call trước khi thực thi.

Lưu ý: property điều khiển auto-registration của `ChatClient` được auto-configure. Nếu tự tạo một `ChatClient` với builder riêng, hãy kiểm tra cấu hình builder và advisor chain thực tế thay vì mặc định rằng mọi builder đều nhận cùng property.

## 7. Tắt tự đăng ký cho một request

Không phải request nào cũng cần tắt vòng lặp tự động. Có thể opt out ở từng request bằng `AdvisorParams.toolCallingAdvisorAutoRegister(false)`:

~~~java
ChatClientResponse response = chatClient.prompt()
    .user("Tra cứu tồn kho SKU-100.")
    .tools(inventoryTools)
    .advisors(AdvisorParams.toolCallingAdvisorAutoRegister(false))
    .call()
    .chatClientResponse();
~~~

Request này vẫn gửi tool definitions cho model, nhưng `ToolCallingAdvisor` mặc định không tự chạy callback. Ứng dụng nhận `ChatClientResponse` và có thể kiểm tra `response.chatResponse().hasToolCalls()` trước khi quyết định thực thi.

Nếu muốn dùng advisor tùy chỉnh cho riêng request, có thể kết hợp opt out với advisor đó:

~~~java
String answer = chatClient.prompt()
    .user(question)
    .tools(inventoryTools)
    .advisors(
        AdvisorParams.toolCallingAdvisorAutoRegister(false),
        customToolCallingAdvisor
    )
    .call()
    .content();
~~~

Cách này phù hợp khi một số request cần quy trình kiểm duyệt, xác nhận người dùng, audit hoặc điều phối khác với vòng lặp mặc định.

## 8. Tùy chỉnh ToolCallingAdvisor mặc định trong Spring Boot

Trong đa số ứng dụng, không cần tạo advisor thủ công. Nếu cần thay đổi cấu hình của advisor mặc định, Spring AI 2.1 hỗ trợ hai cách phổ biến.

### 8.1. Điều chỉnh thứ tự advisor

Có thể đặt thứ tự qua property:

~~~yaml
spring:
  ai:
    chat:
      client:
        tool-calling:
          advisor-order: -2147483348
~~~

Giá trị mặc định tương ứng với `Ordered.HIGHEST_PRECEDENCE + 300`. Advisor có order thấp hơn chạy trước khi request đi xuống chain; response quay ngược lại theo thứ tự stack.

Thứ tự ảnh hưởng việc advisor nào chạy bên ngoài và advisor nào chạy bên trong vòng tool calling. Ví dụ, advisor ghi log toàn bộ request/response cuối có thể đặt bên ngoài; advisor cần quan sát từng iteration có thể đặt bên trong vòng lặp.

### 8.2. Cung cấp ToolCallingAdvisor.Builder tùy chỉnh

Spring Boot cho phép khai báo bean `ToolCallingAdvisor.Builder<?>`. Builder này thay thế builder auto-configured và được dùng khi `ChatClient` tự đăng ký advisor.

~~~java
@Configuration
class ToolAdvisorConfiguration {

    @Bean
    ToolCallingAdvisor.Builder<?> toolCallingAdvisorBuilder(
            ToolCallingManager toolCallingManager) {

        return ToolCallingAdvisor.builder()
            .toolCallingManager(toolCallingManager)
            .advisorOrder(ToolCallingAdvisor.DEFAULT_ORDER);
    }
}
~~~

Ví dụ trên sử dụng `ToolCallingManager` đã được ứng dụng cấu hình để kiểm soát việc phân giải và thực thi callback.

Builder cũng cho phép tùy chỉnh `ToolExecutionEligibilityChecker` để quyết định response nào cần chạy vòng tiếp theo:

~~~java
ToolCallingAdvisor.Builder<?> builder =
    ToolCallingAdvisor.builder()
        .toolExecutionEligibilityChecker(response ->
            response != null && response.hasToolCalls()
        );
~~~

Checker mặc định tiếp tục vòng lặp khi `ChatResponse` có tool call. Chỉ thay checker nếu provider hoặc nghiệp vụ cần điều kiện dừng bổ sung, chẳng hạn kiểm tra finish reason.

Không nên tạo nhiều builder bean cùng kiểu cho một cấu hình nếu không có cơ chế lựa chọn rõ ràng. Auto-configuration chỉ có thể sử dụng một builder phù hợp.

## 9. Advisor order và conversation history

Trong Spring AI 2.1, `ToolCallingAdvisor` có order mặc định là:

~~~java
ToolCallingAdvisor.DEFAULT_ORDER
// Ordered.HIGHEST_PRECEDENCE + 300
~~~

Các advisor có order thấp hơn chạy ở phía ngoài vòng tool calling; advisor có order cao hơn chạy bên trong vòng lặp. Đây là điểm quan trọng khi kết hợp memory, logging, tracing hoặc advisor bổ sung tool.

Mặc định, `ToolCallingAdvisor` tự giữ lịch sử hội thoại qua các iteration, gồm user message, assistant tool call và tool response. Nhờ vậy, các lượt model tiếp theo nhận đủ ngữ cảnh của vòng lặp.

Nếu `MemoryAdvisor` được đặt bên trong vòng lặp, advisor này cần quản lý lịch sử của từng iteration. `DefaultChatClient` nhận biết marker `MemoryAdvisor` và tự tắt internal conversation history của advisor được auto-register trong trường hợp phù hợp. Khi tự tạo `ToolCallingAdvisor` thủ công, cần cấu hình `disableInternalConversationHistory()` nếu memory advisor bên trong đã đảm nhiệm phần lịch sử.

Không thay đổi order tùy tiện. Hãy xác định advisor cần quan sát một lượt model, toàn bộ vòng tool, hay chỉ kết quả cuối rồi mới chọn vị trí.

## 10. Phân biệt tự đăng ký advisor với đăng ký tool

Hai thao tác này độc lập:

- `ToolCallingAdvisor` tự đăng ký để cung cấp vòng điều phối thực thi.
- `.tools(...)` hoặc `.defaultTools(...)` cung cấp các tool definition/callback mà request có thể sử dụng.

Có advisor mà không có tool không tạo ra chức năng nghiệp vụ mới. Có tool definitions mà không có vòng thực thi tự động thì model vẫn có thể yêu cầu tool call, nhưng ứng dụng phải tự xử lý response.

| Cấu hình | Tool definition gửi đến model | Tool call được thực thi tự động |
|---|---|---|
| Có tool, advisor tự đăng ký | Có | Có |
| Có tool, advisor bị tắt | Có | Không |
| Không có tool, advisor tự đăng ký | Không | Không có tool để chạy |
| Có custom ToolAdvisor trong chain | Theo request | Do custom advisor điều phối |
| Gọi ChatModel trực tiếp trong 2.x | Theo prompt/options | Không; ứng dụng tự điều phối |

Việc một bean `ToolCallback` tồn tại trong Spring context cũng không đồng nghĩa tool tự động được cung cấp cho mọi request. Hãy đăng ký tập tool theo request hoặc default tools phù hợp và kiểm tra quyền ở backend.

## 11. Các lỗi thường gặp khi nâng cấp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Nâng cấp lên 2.x nhưng callback không tự chạy khi gọi ChatModel | Vòng lặp nội bộ đã bị loại bỏ khỏi ChatModel | Chuyển sang ChatClient hoặc tự điều phối bằng ToolCallingManager |
| Advisor bị chạy hai lần | Vừa tự đăng ký vừa thêm advisor tùy chỉnh không được nhận diện là ToolAdvisor | Dùng marker ToolAdvisor hoặc tắt auto-registration trước khi thêm advisor thủ công |
| Tool call được trả về nhưng không thực thi | Auto-registration bị tắt hoặc request chỉ có tool definitions | Kiểm tra property và AdvisorParams |
| Tool do advisor khác thêm vào không được thực thi | Dùng bản 2.0.0 chỉ auto-register khi tool có sẵn lúc đầu hoặc tự tắt advisor | Kiểm tra phiên bản; 2.1 auto-register advisor ngay cả khi tool được thêm lúc chạy |
| Lỗi compile với internalToolExecutionEnabled | Đang dùng API 1.x đã bị loại bỏ trong 2.0 | Bỏ option và chuyển sang ToolCallingAdvisor hoặc manual loop |
| Vòng lặp không dừng như mong muốn | Checker hoặc response vẫn báo có tool call | Kiểm tra tool result, finish reason và eligibility checker |
| Memory thiếu tool call/result | Memory advisor đặt sai phía trong/ngoài vòng lặp | Kiểm tra advisor order và cơ chế quản lý history |

Khi nâng cấp, không chỉ kiểm tra compile thành công. Hãy chạy thử một request có tool call thực tế để xác nhận callback chỉ được thực thi một lần cho mỗi tool call và model nhận được tool result trong iteration tiếp theo.

## 12. Kiểm thử cơ chế auto-registration

Nên kiểm tra riêng ba lớp: cấu hình advisor, việc gửi tool definitions và việc thực thi callback.

| Trường hợp | Kết quả cần xác minh |
|---|---|
| Spring AI 1.x, tool được gắn vào ChatClient | ChatModel xử lý vòng gọi tool nội bộ |
| Spring AI 2.0.x, request có tool | ToolCallingAdvisor được tự đăng ký |
| Spring AI 2.1.x, tool được thêm bởi advisor khác | ToolCallingAdvisor mặc định vẫn có mặt trong chain |
| Auto-registration toàn cục bị tắt | Tool definitions vẫn được gửi, callback không tự thực thi |
| Auto-registration bị tắt theo request | Chỉ request đó chuyển sang user-controlled mode |
| Có custom ToolAdvisor | Advisor mặc định không được thêm lần nữa |
| Có hai ToolAdvisor | Chain từ chối cấu hình trùng vai trò |
| Tool call hợp lệ | Callback chạy và tool result quay lại model |
| Response không có tool call | Vòng lặp kết thúc |
| Streaming | Vòng lặp xử lý tool call theo luồng stream đúng cách |

Một integration test nên dùng model giả lập để trả về hai response liên tiếp: response đầu có tool call, response sau là câu trả lời cuối. Xác minh callback được gọi một lần, response thứ hai nhận tool result và kết quả cuối được trả về caller.

Không cần gọi provider AI thật trong unit test. Dành smoke test riêng cho môi trường có credential để kiểm tra khả năng tương thích của model/provider.

## 13. Checklist khi sử dụng ChatClient theo phiên bản

- [ ] Xác nhận phiên bản Spring AI đang dùng từ BOM.
- [ ] Với 1.x, hiểu rằng vòng lặp tool calling nằm trong ChatModel.
- [ ] Với 2.0.x, dùng ChatClient và ToolCallingAdvisor cho vòng lặp tự động.
- [ ] Với 2.1.x, hiểu rằng DefaultChatClient tự đăng ký ToolCallingAdvisor ngay cả khi tool được thêm động.
- [ ] Không thêm một tool advisor thứ hai vào chain mặc định.
- [ ] Dùng `spring.ai.chat.client.tool-calling.enabled=false` nếu cần tắt tự đăng ký toàn cục trong auto-configured ChatClient.
- [ ] Dùng `AdvisorParams.toolCallingAdvisorAutoRegister(false)` nếu chỉ cần tắt cho một request.
- [ ] Khi cần cấu hình riêng, dùng `ToolCallingAdvisor.Builder<?>` hoặc advisor order phù hợp.
- [ ] Khi gọi ChatModel trực tiếp trong 2.x, tự điều phối bằng ToolCallingManager.
- [ ] Kiểm tra tool definitions, callback, ToolContext và quyền truy cập độc lập.
- [ ] Kiểm thử cả call và stream path nếu ứng dụng hỗ trợ streaming.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html): cơ chế recursive advisor, auto-registration, builder, advisor order, marker interface và opt out.
- [Spring AI 2.1.0 — Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html): thay đổi từ 1.x lên 2.0, thay đổi auto-registration trong 2.1 và property cấu hình.
- [Spring AI 2.1.0 — ChatClient API](https://docs.spring.io/spring-ai/reference/api/chatclient.html): auto-configured ChatClient.Builder và cách xây dựng ChatClient.
- [Spring AI 1.0.9 — Tool Calling](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html): vòng thực thi tool trong ChatModel ở 1.x.
- [Spring AI 1.1.8 — Tool Calling](https://docs.spring.io/spring-ai/reference/1.1/api/tools.html): hành vi tool calling của dòng 1.1.x.
- [Spring AI 1.0.9 — Advisors API](https://docs.spring.io/spring-ai/reference/1.0/api/advisors.html): advisor chain, advisor order và cách đăng ký advisor trong 1.x.

Cơ chế tự đăng ký advisor thay đổi theo phiên bản. Hãy xác định rõ ứng dụng đang chạy Spring AI 1.x, 2.0.x hay 2.1.x trước khi thêm, thay thế hoặc tắt `ToolCallingAdvisor`; đồng thời giữ quyền lựa chọn và thực thi tool ở phía ứng dụng.

