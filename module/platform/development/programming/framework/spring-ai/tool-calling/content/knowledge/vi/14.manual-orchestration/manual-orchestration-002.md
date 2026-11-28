# Tắt vòng lặp tự động theo cơ chế của phiên bản đang dùng

Spring AI có thể tự thực hiện chu trình gọi công cụ: gửi định nghĩa công cụ cho mô hình, nhận tool call, chạy callback, gửi kết quả trở lại mô hình và lặp đến khi mô hình trả lời cuối cùng. Cách này tiện cho ứng dụng thông thường. Nhưng có những trường hợp ứng dụng cần dừng trước khi công cụ chạy, xin phê duyệt, kiểm tra từng tool call, phát tiến độ qua SSE/WebSocket hoặc áp dụng quy tắc riêng giữa các lượt.

Cách tắt vòng lặp tự động phụ thuộc phiên bản Spring AI và API bạn đang dùng. Spring AI 1.x đặt vòng lặp bên trong từng `ChatModel`; từ Spring AI 2.0, vòng lặp nội bộ đó đã bị loại bỏ và `ChatClient` dùng `ToolCallingAdvisor` để tự điều phối. Vì vậy, không thể dùng một cấu hình duy nhất cho cả hai thế hệ.

Bài này tập trung vào cách nhận biết cơ chế của phiên bản, tắt đúng tầng tự động, tự thực hiện vòng gọi bằng `ToolCallingManager` và giữ các giới hạn, quyền truy cập cùng lịch sử hội thoại khi ứng dụng nắm quyền điều phối.

## Trước hết, xác định vòng lặp nằm ở đâu

| Phiên bản | Cơ chế mặc định | Cách chuyển sang điều khiển thủ công |
|---|---|---|
| Spring AI 1.0.x | Mỗi implementation `ChatModel` có vòng thực thi tool nội bộ. | Đặt `internalToolExecutionEnabled(false)` trong `ToolCallingChatOptions`. Sau đó caller kiểm tra response và gọi `ToolCallingManager`. |
| Spring AI 2.0.x–2.1.x | `ChatModel` không còn tự thực thi tool call. `ChatClient` tự đăng ký `ToolCallingAdvisor` để điều phối vòng lặp. | Với `ChatClient`, tắt auto-registration bằng `AdvisorParams.toolCallingAdvisorAutoRegister(false)` cho một request hoặc property toàn cục. Với `ChatModel` trực tiếp, caller đã sở hữu vòng lặp; không cần tắt một vòng lặp nội bộ không còn tồn tại. |

Sự thay đổi lớn xảy ra khi chuyển từ 1.x sang 2.0:

- Ở 1.x, gọi `chatModel.call(prompt)` với tool có thể thực thi tool và gọi mô hình lại trước khi trả về response cuối. Muốn tự điều khiển, cần tắt internal execution.
- Ở 2.x, `chatModel.call(prompt)` trả về response thô của mô hình, bao gồm tool call nếu có. Nó không thực thi callback. Đường `ChatClient` được bổ sung `ToolCallingAdvisor`, advisor này tự quản lý vòng lặp trừ khi bạn opt out.

Hãy kiểm tra phiên bản Spring AI thực tế trong dependency management và xác định code đang gọi `ChatClient` hay `ChatModel` trước khi đổi cấu hình.

## Spring AI 2.x: tắt ToolCallingAdvisor cho một request

Trong Spring AI 2.0 trở lên, `DefaultChatClient` tự đăng ký `ToolCallingAdvisor`. Advisor này nhận response của mô hình, thực thi tool call bằng `ToolCallingManager`, thêm kết quả vào lịch sử rồi gửi lịch sử trở lại mô hình. Nó tiếp tục cho đến khi không còn tool call.

Để tắt vòng lặp tự động chỉ cho một request, thêm `AdvisorParams.toolCallingAdvisorAutoRegister(false)`:

```java
String response = chatClient.prompt()
        .user("Thời tiết ở Hà Nội hôm nay thế nào?")
        .tools(weatherTools)
        .advisors(AdvisorParams.toolCallingAdvisorAutoRegister(false))
        .call()
        .content();
```

Khi tắt auto-registration, `.tools(...)` vẫn gửi định nghĩa công cụ cho mô hình. Khác biệt là response chứa tool call không được thực thi tự động. Caller nhận được `ChatClientResponse` hoặc `ChatResponse` để kiểm tra và quyết định bước tiếp theo.

Hãy dùng `chatClientResponse()` thay vì `content()` khi cần đọc tool call:

```java
ChatClientResponse response = chatClient.prompt()
        .user(question)
        .tools(tools)
        .advisors(AdvisorParams.toolCallingAdvisorAutoRegister(false))
        .call()
        .chatClientResponse();

ChatResponse chatResponse = response.chatResponse();
if (chatResponse != null && chatResponse.hasToolCalls()) {
    // Kiểm tra tên tool và arguments trước khi thực thi.
}
```

`content()` chỉ phù hợp khi bạn cần nội dung văn bản cuối. Khi đang điều khiển thủ công, đọc `ChatResponse` để biết mô hình đã trả tool call hay đã hoàn tất câu trả lời.

## Spring AI 2.x: tắt auto-registration toàn cục

Nếu toàn bộ ứng dụng dùng auto-configured `ChatClient` đều cần tự điều phối, đặt property:

```properties
spring.ai.chat.client.tool-calling.enabled=false
```

Property này ngăn `ChatClient` tự đăng ký `ToolCallingAdvisor`. Định nghĩa công cụ vẫn có thể được gửi đến mô hình; response có tool call được trả cho ứng dụng mà không tự chạy callback.

Chỉ dùng cấu hình toàn cục khi mọi luồng liên quan đều có code tự xử lý tool call. Nếu một request vẫn cần vòng tự động, hãy dùng opt out theo request hoặc tạo cấu hình/client riêng phù hợp. Với `ChatClient` được tạo thủ công ngoài auto-configuration, kiểm tra cách builder được cấu hình trong ứng dụng; property Boot chủ yếu điều khiển auto-configuration.

## Spring AI 1.x: tắt vòng lặp nội bộ của ChatModel

Trong Spring AI 1.0.x, `ChatModel` tự thực thi tool call theo mặc định. Để nhận response thô và tự quyết định khi nào chạy callback, đặt `internalToolExecutionEnabled(false)`:

```java
ToolCallback[] tools = ToolCallbacks.from(new WeatherTools());

ToolCallingChatOptions chatOptions = ToolCallingChatOptions.builder()
        .toolCallbacks(tools)
        .internalToolExecutionEnabled(false)
        .build();

Prompt prompt = new Prompt(
        "Thời tiết ở Hà Nội hôm nay thế nào?",
        chatOptions
);

ChatResponse response = chatModel.call(prompt);
```

Sau khi đặt cờ này, `ChatModel` trả response có tool call để caller xử lý. Caller dùng `ToolCallingManager.executeToolCalls(prompt, response)`, cập nhật prompt bằng conversation history mới rồi gọi model tiếp.

Đây là cơ chế dành cho 1.x. Không thêm `internalToolExecutionEnabled(false)` vào ví dụ 2.x với kỳ vọng nó sẽ tắt `ToolCallingAdvisor`: vòng lặp của `ChatClient` trong 2.x nằm ở advisor chain, không còn nằm trong `ChatModel`.

## Tự điều phối vòng gọi bằng ChatClient trong Spring AI 2.x

Khi đã tắt `ToolCallingAdvisor`, ứng dụng chịu trách nhiệm cho mỗi lượt. Quy trình gồm:

1. Gửi câu hỏi cùng tập `ToolCallback` và tắt auto-registration.
2. Kiểm tra response có tool call hay không.
3. Nếu không có tool call, trả nội dung cuối cho caller.
4. Nếu có, kiểm tra từng tên tool, đối số, quyền và điều kiện nghiệp vụ.
5. Dùng `ToolCallingManager` thực thi các tool call được phép.
6. Nếu kết quả yêu cầu `returnDirect`, trả kết quả theo hợp đồng của ứng dụng và dừng.
7. Nếu cần tiếp tục, tạo prompt mới từ `ToolExecutionResult.conversationHistory()` và gửi lại mô hình với cùng tập công cụ cùng cấu hình opt out.
8. Lặp đến khi có câu trả lời cuối hoặc đạt giới hạn do ứng dụng đặt.

Ví dụ minh họa theo API Spring AI 2.1.0:

```java
ToolCallback[] tools = ToolCallbacks.from(new WeatherTools());

ToolCallingChatOptions chatOptions = ToolCallingChatOptions.builder()
        .toolCallbacks(tools)
        .build();

ToolCallingManager toolCallingManager = ToolCallingManager.builder().build();
String question = "Thời tiết ở Hà Nội và Đà Nẵng hôm nay thế nào?";

Prompt prompt = new Prompt(List.of(new UserMessage(question)), chatOptions);

ChatClientResponse response = chatClient.prompt()
        .user(question)
        .options(chatOptions)
        .advisors(AdvisorParams.toolCallingAdvisorAutoRegister(false))
        .call()
        .chatClientResponse();

int iteration = 0;
int maxIterations = 8;

while (response.chatResponse() != null
        && response.chatResponse().hasToolCalls()) {

    if (++iteration > maxIterations) {
        throw new IllegalStateException("Đã vượt giới hạn vòng tool calling");
    }

    // Kiểm tra allowlist, arguments, authorization và yêu cầu phê duyệt tại đây.
    ToolExecutionResult result = toolCallingManager.executeToolCalls(
            prompt,
            response.chatResponse()
    );

    if (result.returnDirect()) {
        return renderDirectToolResult(result);
    }

    prompt = new Prompt(result.conversationHistory(), chatOptions);

    response = chatClient.prompt()
            .messages(result.conversationHistory())
            .options(chatOptions)
            .advisors(AdvisorParams.toolCallingAdvisorAutoRegister(false))
            .call()
            .chatClientResponse();
}

return response.chatResponse()
        .getResult()
        .getOutput()
        .getText();
```

`renderDirectToolResult(...)` là hàm của ứng dụng để chuyển kết quả công cụ thành kiểu trả về cuối. Nếu method không trả `String`, hãy thay kiểu trả về theo hợp đồng endpoint. Không gửi tiếp kết quả `returnDirect` trở lại mô hình.

`executeToolCalls(...)` xử lý các tool call có trong response. Nếu một response chứa nhiều tool call và chỉ một số call cần phê duyệt, không chuyển cả response cho manager trước khi quyết định. Hãy kiểm tra toàn bộ batch và tạm dừng nếu còn call chưa được duyệt. Nếu cần pause/resume từng call mà vẫn giữ vòng lặp advisor, cân nhắc Tool Call Confirmation; nếu cần chính sách dispatch riêng cho từng call, ứng dụng phải tự xây dựng bước điều phối phù hợp.

Điểm dễ bỏ sót là phải tắt auto-registration ở cả request đầu tiên và mọi request tiếp theo. Nếu quên ở một vòng sau, `ToolCallingAdvisor` có thể được thêm lại và framework tiếp tục tự chạy vòng lặp, làm mất quyền kiểm soát mà ứng dụng vừa thiết lập.

## Tự điều phối trực tiếp bằng ChatModel trong Spring AI 2.x

Nếu không cần advisor chain của `ChatClient`, có thể gọi `ChatModel` trực tiếp. Trong 2.x, `ChatModel` không tự chạy tool loop, nên không cần cấu hình opt out:

```java
ToolCallback[] tools = ToolCallbacks.from(new WeatherTools());

ToolCallingChatOptions chatOptions = ToolCallingChatOptions.builder()
        .toolCallbacks(tools)
        .build();

ToolCallingManager toolCallingManager = ToolCallingManager.builder().build();
Prompt prompt = new Prompt(question, chatOptions);
ChatResponse response = chatModel.call(prompt);

int iteration = 0;
int maxIterations = 8;

while (response.hasToolCalls()) {
    if (++iteration > maxIterations) {
        throw new IllegalStateException("Đã vượt giới hạn vòng tool calling");
    }

    ToolExecutionResult result = toolCallingManager.executeToolCalls(prompt, response);

    if (result.returnDirect()) {
        return renderDirectToolResult(result);
    }

    prompt = new Prompt(result.conversationHistory(), chatOptions);
    response = chatModel.call(prompt);
}

return response.getResult().getOutput().getText();
```

Ở đường này, `ChatModel` chỉ gửi tool definitions và trả response. `ToolCallingManager` thực thi tool call và tạo conversation history có assistant tool-call message cùng tool response message. Caller gửi lịch sử đó trong prompt kế tiếp.

Trong Spring Boot có auto-configuration, `ToolCallingManager` thường đã có bean mặc định. Chỉ tự tạo manager khi ứng dụng cần cấu hình riêng hoặc không dùng auto-configuration; tránh tạo nhiều manager với policy khác nhau mà không có chủ đích.

## Spring AI 1.x: vòng lặp thủ công với ToolCallingManager

Ví dụ đầy đủ cho đường `ChatModel` trong 1.x:

```java
ToolCallback[] tools = ToolCallbacks.from(new CustomerTools());

ToolCallingChatOptions chatOptions = ToolCallingChatOptions.builder()
        .toolCallbacks(tools)
        .internalToolExecutionEnabled(false)
        .build();

ToolCallingManager toolCallingManager = ToolCallingManager.builder().build();
Prompt prompt = new Prompt(question, chatOptions);
ChatResponse response = chatModel.call(prompt);

int iteration = 0;
int maxIterations = 8;

while (response.hasToolCalls()) {
    if (++iteration > maxIterations) {
        throw new IllegalStateException("Đã vượt giới hạn vòng tool calling");
    }

    ToolExecutionResult result = toolCallingManager.executeToolCalls(prompt, response);

    if (result.returnDirect()) {
        return renderDirectToolResult(result);
    }

    prompt = new Prompt(result.conversationHistory(), chatOptions);
    response = chatModel.call(prompt);
}

return response.getResult().getOutput().getText();
```

Khác biệt chính với ví dụ 2.x là cờ `internalToolExecutionEnabled(false)`. Nếu bỏ cờ này trong 1.x, `ChatModel` có thể tự thực thi tool trước khi caller nhận được response; khi đó vòng lặp thủ công không còn kiểm soát được điểm dừng.

## Không phải lúc nào cũng cần tắt toàn bộ vòng lặp

Tắt tự động điều phối là cách mạnh nhất để nắm từng bước, nhưng nó cũng chuyển nhiều trách nhiệm sang ứng dụng. Trước khi opt out, hãy xác định bạn thực sự cần kiểm soát điều gì.

| Nhu cầu | Cách tiếp cận nên cân nhắc |
|---|---|
| Cần người dùng duyệt một tool call nhạy cảm | Dùng Tool Call Confirmation để tạm dừng vòng lặp tại điểm cần duyệt. |
| Muốn ghi nhận hoặc phát tiến độ mỗi lượt | Đặt custom advisor bên trong vòng `ToolCallingAdvisor`; không nhất thiết phải tự viết loop. |
| Muốn thay đổi tool set hoặc kiểm tra điều kiện giữa các lượt | Mở rộng `ToolCallingAdvisor` bằng hook phù hợp. |
| Muốn tự điều khiển lịch sử, phê duyệt, quota hoặc dừng theo tín hiệu bên ngoài | Tắt auto-registration và điều phối bằng `ToolCallingManager`. |
| Không muốn advisor chain và cần tích hợp vào workflow engine khác | Gọi `ChatModel` trực tiếp và tự quản lý loop. |

Nếu chỉ cần xem mỗi tool call, custom advisor bên trong vòng lặp thường giữ được composition, memory và observability tốt hơn. Full opt out phù hợp khi ứng dụng thực sự cần sở hữu từng iteration.

## Những trách nhiệm nhận về khi tự điều phối

Khi vòng lặp tự động bị tắt, `ToolCallingManager` vẫn giúp phân giải và thực thi callback. Nhưng ứng dụng cần quản lý phần điều phối xung quanh:

- **Lịch sử hội thoại:** luôn giữ assistant message chứa tool call và tool response tương ứng. Dùng `ToolExecutionResult.conversationHistory()` làm đầu vào cho lượt tiếp theo; không chỉ gửi lại câu hỏi ban đầu.
- **Tập công cụ:** giữ đúng callback/ToolCallingChatOptions ở các vòng sau; kiểm tra tên tool duy nhất và allowlist theo request.
- **Authorization:** xác thực người dùng và kiểm tra quyền trên từng tài nguyên ở thời điểm thực thi. Mô hình chọn tool không phải là phê duyệt.
- **Phê duyệt:** dừng trước khi chạy thao tác có tác động nếu cần xác nhận của con người; không thực thi trước rồi mới hỏi.
- **Giới hạn vòng:** đặt `maxIterations`, timeout tổng, ngân sách token/chi phí và điều kiện dừng theo nghiệp vụ.
- **Giới hạn tool call:** giữ giới hạn của `ToolCallingManager` theo từng tool và tổng số lần gọi trong lượt. Giới hạn vòng LLM và giới hạn tool call là hai lớp khác nhau.
- **Lỗi:** phân biệt lỗi JSON, lỗi phân quyền, lỗi nghiệp vụ và lỗi hạ tầng; không lặp vô hạn khi tool thất bại.
- **`returnDirect`:** nếu `ToolExecutionResult.returnDirect()` là `true`, kết thúc loop và trả kết quả theo hợp đồng của ứng dụng.
- **Observability:** tự ghi nhận thời gian, số lượt, tool name và trạng thái. Khi tự điều khiển ngoài advisor loop, các advisor/observation vốn chạy bên trong vòng tự động có thể không còn được áp dụng cho từng iteration.
- **Đồng thời và hủy:** hỗ trợ cancellation, timeout và không chia sẻ mutable conversation state giữa các request.

## Giữ giới hạn và bảo mật khi gọi ToolCallingManager

`ToolCallingManager` không biến arguments do mô hình tạo thành dữ liệu đáng tin cậy. Trước khi thực thi, hãy kiểm tra tên tool trong allowlist của request, xác thực dữ liệu và truyền user/tenant qua `ToolContext` từ security context của ứng dụng.

Spring AI 2.1.0 có giới hạn số lần gọi mặc định trong `DefaultToolCallingManager` (40 lần cho mỗi tool và 150 lần tổng trong một lượt). Có thể cấu hình `spring.ai.tools.limits.*` hoặc builder tương ứng. Không dùng `maxIterations` thay cho các giới hạn này: một iteration có thể chứa nhiều tool call, còn một tool call có thể dẫn đến một lượt mô hình tiếp theo.

Với thao tác ghi, cần tính đến retry và gọi trùng. Dùng idempotency key, kiểm tra trạng thái trước khi chuyển đổi, audit event và xác nhận của người dùng theo chính sách. Đặt timeout cho từng tool và tổng request.

## Streaming khi tự điều phối

Với `.stream()`, không thực thi tool từ các mảnh arguments chưa hoàn chỉnh. Một tool call chỉ được thực thi khi response đã được tổng hợp thành `ChatResponse` hoàn chỉnh. Spring AI cung cấp `ChatClientMessageAggregator` để gom các chunk của từng iteration; ứng dụng có thể đồng thời chuyển tiếp chunk tới SSE/WebSocket.

Luồng tổng quát:

1. Gọi `.stream()` với auto-registration tắt.
2. Chuyển tiếp chunk tới subscriber để hiển thị tiến độ.
3. Dùng aggregator để tạo `ChatClientResponse` hoàn chỉnh.
4. Kiểm tra `chatResponse().hasToolCalls()`.
5. Nếu có, thực thi bằng `ToolCallingManager`, tạo prompt từ conversation history rồi bắt đầu stream tiếp theo.
6. Nếu không có, kết thúc bằng nội dung cuối.

Streaming thủ công phức tạp hơn đường blocking vì phải quản lý subscription, aggregation, cancellation và lỗi của từng Flux. Chỉ triển khai khi UI hoặc workflow thật sự cần các chunk trung gian.

## Kiểm thử cơ chế opt out

Kiểm thử phải chứng minh framework không tự chạy tool và ứng dụng chỉ thực thi sau khi chủ động gọi manager.

| Tình huống | Kết quả cần xác minh |
|---|---|
| Spring AI 2.x, opt out theo request | Response đầu tiên giữ tool call; callback chưa chạy. |
| Spring AI 2.x, auto-registration mặc định | `ToolCallingAdvisor` thực thi tool và lặp cho tới câu trả lời cuối. |
| Spring AI 2.x, global property tắt | Các request từ auto-configured ChatClient không tự chạy tool call. |
| Spring AI 1.x, `internalToolExecutionEnabled(false)` | `ChatModel` trả tool call thô; callback chưa chạy. |
| Spring AI 1.x, bỏ cờ opt out | Hành vi internal tool execution mặc định có thể chạy trước khi caller nhận response. |
| Response không có tool call | Loop kết thúc và trả văn bản cuối. |
| Một response có nhiều tool call | Tất cả call hợp lệ được kiểm tra và xử lý đúng chính sách. |
| Tool call không nằm trong allowlist | Không callback nào ngoài allowlist được thực thi. |
| Tool yêu cầu phê duyệt | Loop dừng trước khi thực thi và chỉ tiếp tục sau quyết định hợp lệ. |
| Tool trả `returnDirect` | Không gửi tool result sang lượt model tiếp theo. |
| Model lặp tool call | Vượt `maxIterations` hoặc quota thì loop dừng an toàn. |
| Tool timeout hoặc ném exception | Lỗi được xử lý theo policy, không lặp vô hạn. |
| Hai request đồng thời | Conversation history, context và danh sách tool không bị trộn. |

Nên dùng model giả lập để tạo response có/không có tool call, nhiều tool call, lỗi và chuỗi nhiều iteration. Integration test cần xác minh số lần gọi callback, nội dung conversation history và việc opt out được áp dụng ở mọi request trong loop.

## Bài tập thực hành

Tạo luồng hỗ trợ khách hàng cần phê duyệt trước khi hoàn tiền:

1. Tạo `refundTools` gồm công cụ đọc chi tiết đơn và công cụ yêu cầu hoàn tiền.
2. Trong Spring AI 2.1.0, tắt auto-registration theo request bằng `AdvisorParams.toolCallingAdvisorAutoRegister(false)`.
3. Gửi câu hỏi đầu tiên và đọc `ChatClientResponse.chatResponse()`.
4. Nếu mô hình yêu cầu tra cứu, kiểm tra allowlist rồi gọi `ToolCallingManager.executeToolCalls(...)`.
5. Nếu mô hình yêu cầu hoàn tiền, dừng loop và tạo yêu cầu phê duyệt cho nhân viên; chưa thực thi callback ghi.
6. Sau khi được duyệt, thực thi hành động bằng luồng được kiểm soát, cập nhật conversation history và gọi mô hình tiếp nếu cần.
7. Đặt giới hạn tối đa 6 iteration, giới hạn tool call và timeout.
8. Viết test chứng minh callback hoàn tiền không chạy trước khi phê duyệt.
9. Viết một ví dụ 1.0.x với `internalToolExecutionEnabled(false)` và ghi rõ khác biệt API.

Bạn hoàn thành khi có thể chỉ ra chính xác tầng nào đang tự điều phối trong phiên bản dự án, chứng minh opt out ngăn callback tự chạy và chứng minh ứng dụng chỉ thực thi các tool call đã qua kiểm tra.

## Danh sách kiểm tra trước khi triển khai

- [ ] Đã xác định phiên bản Spring AI và API đang dùng (`ChatClient` hay `ChatModel`).
- [ ] Với 1.x, đã đặt `internalToolExecutionEnabled(false)` khi cần tự điều khiển `ChatModel` loop.
- [ ] Với 2.x `ChatClient`, đã tắt auto-registration theo request hoặc bằng property toàn cục.
- [ ] Với 2.x `ChatModel` trực tiếp, không dựa vào cờ 1.x để tắt loop nội bộ đã bị loại bỏ.
- [ ] Mọi request tiếp theo trong loop thủ công đều giữ trạng thái opt out.
- [ ] Dùng `chatClientResponse()`/`ChatResponse` để phát hiện tool call thay vì chỉ đọc `.content()`.
- [ ] Dùng `ToolCallingManager` và `ToolExecutionResult.conversationHistory()` để thực thi và nối lịch sử đúng thứ tự.
- [ ] Xử lý `returnDirect`, lỗi, phê duyệt và trường hợp không có tool call.
- [ ] Có `maxIterations`, timeout, quota tool call và điều kiện hủy.
- [ ] Allowlist, authentication và authorization được kiểm tra trước mỗi lần dispatch.
- [ ] Context và lịch sử hội thoại được cô lập theo request.
- [ ] Đã đánh giá observability/advisors bị bỏ qua khi tự điều khiển ngoài vòng advisor.
- [ ] Có unit test và integration test cho cả đường tự động lẫn thủ công.

Tắt vòng lặp tự động là thay đổi quyền điều phối: framework ngừng tự thực thi và caller nhận trách nhiệm quản lý từng iteration. Hãy chọn đúng cơ chế của phiên bản, giữ lịch sử hội thoại, kiểm tra từng tool call và đặt giới hạn rõ ràng để vòng thủ công vẫn an toàn và có thể vận hành.

## Tài liệu tham khảo

- [Spring AI 2.1.0 – Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 – ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1.0 – ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html)
- [Spring AI 1.0.9 – Tool Calling](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html)
- [Spring AI Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)
