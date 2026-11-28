# Chọn kết thúc bằng lỗi hay trả thông báo cho mô hình khi vượt giới hạn

Spring AI giới hạn số lần một tool được gọi trong một lượt hội thoại để ngăn vòng lặp không kiểm soát và chi phí tăng ngoài dự kiến. Khi vượt giới hạn, ứng dụng có hai lựa chọn: **THROW** để dừng lượt xử lý bằng lỗi, hoặc **RETURN_ERROR_RESPONSE** để bỏ qua lần gọi vượt hạn và gửi một tool result báo lỗi cho mô hình.

Chọn **THROW** khi giới hạn là ranh giới dừng cứng, chẳng hạn thao tác có tác động phụ, workflow cần người vận hành xử lý hoặc ứng dụng không muốn mô hình tự tìm cách tiếp tục. Chọn **RETURN_ERROR_RESPONSE** khi thao tác an toàn, lỗi có thể phục hồi và mô hình có thể dùng thông tin còn lại để trả lời, hỏi thêm dữ liệu hoặc chọn một hướng xử lý hợp lệ khác.

Hai chế độ chỉ quyết định cách `DefaultToolCallingManager` xử lý lần gọi vượt hạn. Chúng không thay đổi giá trị giới hạn, không hoàn tác tool đã chạy thành công và không thay thế kiểm tra quyền nghiệp vụ.

`ToolCallLimitBehavior` và hai lựa chọn này có từ Spring AI 2.0.1.

## 1. Giới hạn tool call bảo vệ điều gì?

Một lượt tool calling có thể gồm nhiều vòng mô hình. Mô hình có thể gọi cùng một tool nhiều lần để phân trang, tìm kiếm bổ sung hoặc kiểm tra kết quả. Nhưng nó cũng có thể lặp lại một tool do hiểu sai trạng thái, chọn chiến lược không hiệu quả hoặc không nhận ra đã có đủ dữ liệu.

Spring AI cung cấp hai loại giới hạn:

- **Giới hạn theo tool:** số lần một tool có thể được gọi trong một lượt.
- **Giới hạn tổng:** số tool call tối đa của tất cả tool cộng lại trong một lượt.

Các giới hạn mặc định của `DefaultToolCallingManager` trong Spring AI 2.1:

| Giới hạn | Giá trị mặc định | Ý nghĩa |
| --- | ---: | --- |
| Mỗi tool | 40 | Mỗi tên tool có thể được gọi tối đa 40 lần trong một lượt |
| Tổng tất cả tool | 150 | Tất cả tool cộng lại không vượt quá 150 lần trong một lượt |
| Hành vi khi vượt hạn | `THROW` | Ném `ToolCallLimitExceededException` |

Giá trị mặc định khá rộng để hỗ trợ những tác vụ hợp lệ như phân trang hoặc nhiều bước tra cứu, đồng thời vẫn chặn vòng lặp kéo dài. Ứng dụng nên điều chỉnh theo đặc điểm nghiệp vụ, chi phí và mức độ rủi ro của từng nhóm tool.

~~~mermaid
flowchart TD
    A[Nhận tool call từ mô hình] --> B[Đếm số lần gọi trong lượt]
    B --> C{Còn trong giới hạn?}
    C -->|Có| D[Thực thi ToolCallback]
    C -->|Không| E{onLimitExceeded}
    E -->|THROW| F[Ném ToolCallLimitExceededException]
    E -->|RETURN_ERROR_RESPONSE| G[Bỏ qua callback và tạo ToolResponse lỗi]
    D --> H[Thêm kết quả vào conversation history]
    G --> H
    H --> I[Ứng dụng hoặc advisor quyết định bước tiếp]
~~~

## 2. Cấu hình giới hạn bằng builder

Có thể cấu hình trực tiếp khi tạo `ToolCallingManager`:

~~~java
import org.springframework.ai.model.tool.ToolCallLimitBehavior;
import org.springframework.ai.model.tool.ToolCallingManager;

ToolCallingManager toolCallingManager = ToolCallingManager.builder()
    .maxCallsPerTool(12)
    .maxCallsPerTool("search_orders", 4)
    .maxTotalToolCalls(30)
    .onLimitExceeded(ToolCallLimitBehavior.THROW)
    .build();
~~~

Trong ví dụ:

- Mỗi tool được gọi tối đa 12 lần.
- Riêng `search_orders` được gọi tối đa 4 lần.
- Tổng số lần gọi mọi tool trong một lượt không vượt quá 30.
- Khi bất kỳ giới hạn nào bị vượt, manager áp dụng chính sách `THROW`.

Muốn mô hình nhận thông báo lỗi để quyết định bước tiếp theo, đổi chính sách:

~~~java
ToolCallingManager toolCallingManager = ToolCallingManager.builder()
    .maxCallsPerTool(12)
    .maxCallsPerTool("search_orders", 4)
    .maxTotalToolCalls(30)
    .onLimitExceeded(ToolCallLimitBehavior.RETURN_ERROR_RESPONSE)
    .build();
~~~

`onLimitExceeded(...)` là chính sách chung của manager. Nó áp dụng cho cả giới hạn theo tool và giới hạn tổng, không cấu hình riêng một hành vi cho từng tool. Nếu các workflow cần chính sách khác nhau, hãy dùng manager/configuration phù hợp cho từng workflow hoặc tự đặt lớp điều phối giới hạn riêng.

## 3. Cấu hình bằng Spring Boot properties

Có thể đặt các giới hạn trong `application.properties`:

~~~properties
spring.ai.tools.limits.max-calls-per-tool-default=12
spring.ai.tools.limits.max-calls-per-tool.search_orders=4
spring.ai.tools.limits.max-total-tool-calls=30
spring.ai.tools.limits.on-limit-exceeded=THROW
~~~

Để gửi thông báo giới hạn cho mô hình:

~~~properties
spring.ai.tools.limits.on-limit-exceeded=RETURN_ERROR_RESPONSE
~~~

Các thuộc tính chính:

| Property | Ý nghĩa | Mặc định |
| --- | --- | ---: |
| `spring.ai.tools.limits.max-calls-per-tool-default` | Số lần tối đa cho mỗi tool | 40 |
| `spring.ai.tools.limits.max-calls-per-tool.<name>` | Ghi đè giới hạn cho tool có tên cụ thể | Không có |
| `spring.ai.tools.limits.excluded-tools` | Danh sách tool được miễn giới hạn theo tool | Rỗng |
| `spring.ai.tools.limits.max-total-tool-calls` | Tổng số tool call tối đa trong một lượt | 150 |
| `spring.ai.tools.limits.on-limit-exceeded` | `THROW` hoặc `RETURN_ERROR_RESPONSE` | `THROW` |

Giá trị `-1` có thể dùng để tắt giới hạn tương ứng. Ví dụ, đặt `max-calls-per-tool-default=-1` tắt giới hạn mặc định theo tool; đặt `max-total-tool-calls=-1` tắt giới hạn tổng. Với một tool cụ thể, đặt giới hạn riêng `-1` hoặc thêm tên vào `excluded-tools` để miễn giới hạn theo tool.

Một tool được miễn giới hạn theo tên vẫn được tính vào giới hạn tổng. Không tắt giới hạn tổng chỉ để tránh một tool bị chặn; điều đó sẽ bỏ đi lớp bảo vệ chung cho toàn lượt.

## 4. THROW: dừng khi vượt giới hạn

Với `ToolCallLimitBehavior.THROW`, `DefaultToolCallingManager` ném **ToolCallLimitExceededException** và dừng batch tool call tại thời điểm phát hiện vi phạm.

Exception cung cấp thông tin để ứng dụng ghi nhận và xử lý:

- `getToolName()`: tên tool vượt giới hạn; trả về `null` nếu vượt giới hạn tổng.
- `getLimit()`: giá trị giới hạn bị vượt.
- `getPartialToolExecutionResult()`: kết quả một phần của batch hiện tại, gồm các tool result đã hoàn tất và thông báo tổng hợp cho call bị chặn.
- `buildGeneration()`: tạo một `Generation` biểu diễn việc vượt giới hạn.

Ví dụ khi ứng dụng gọi `ToolCallingManager` trực tiếp:

~~~java
import org.springframework.ai.model.tool.ToolCallLimitExceededException;
import org.springframework.ai.model.tool.ToolExecutionResult;

try {
    ToolExecutionResult result =
        toolCallingManager.executeToolCalls(prompt, chatResponse);

    // Tiếp tục với conversationHistory() nếu thực thi thành công.
}
catch (ToolCallLimitExceededException ex) {
    String toolName = ex.getToolName();
    int limit = ex.getLimit();
    ToolExecutionResult partial = ex.getPartialToolExecutionResult();

    auditService.recordLimitBreach(toolName, limit);
    checkpointService.savePartialToolResult(partial);
    throw ex;
}
~~~

Ví dụ trên giả định ứng dụng có `auditService` và `checkpointService`. Tùy chính sách, tầng gọi có thể chuyển exception thành HTTP 429, trạng thái workflow cần can thiệp hoặc lỗi nghiệp vụ có mã riêng. Không nên trả stack trace hoặc thông tin nội bộ của callback cho người dùng cuối.

### Khi dùng ChatClient và ToolCallingAdvisor

Trong vòng lặp tự động của `ChatClient`, `ToolCallingAdvisor` bắt `ToolCallLimitExceededException` và trả việc vượt giới hạn như response cuối. Response này chứa một `Generation` duy nhất, có finish reason `ToolCallLimitExceededException.FINISH_REASON`.

Nếu một số tool call trong cùng batch đã chạy thành công trước khi giới hạn bị chạm, các kết quả đó được giữ trong metadata `ToolCallLimitExceededException.METADATA_PARTIAL_TOOL_RESPONSES`. Chúng không bị biến thành những generation song song có thể bị hiểu nhầm là các câu trả lời thay thế.

Vì vậy, `THROW` ở tầng manager có hai biểu hiện:

| Cách gọi | Biểu hiện |
| --- | --- |
| Gọi `ToolCallingManager.executeToolCalls(...)` trực tiếp | Exception truyền về ứng dụng để xử lý |
| Dùng `ChatClient` với `ToolCallingAdvisor` mặc định | Advisor bắt exception và kết thúc vòng bằng response báo vượt giới hạn |

Nếu ứng dụng tự viết vòng lặp `ChatModel`, cần tự bắt exception và quyết định dừng, lưu kết quả một phần hoặc chuyển trạng thái cho workflow. Không có advisor bên ngoài để xử lý thay ứng dụng.

### Khi nào nên chọn THROW?

Chọn `THROW` khi vượt hạn phải kết thúc lượt hiện tại:

- Tool có tác động ghi, thanh toán, hoàn tiền, xóa hoặc gửi thông báo.
- Việc tiếp tục có thể gây tác dụng phụ không thể đảo ngược.
- Vượt hạn cho thấy workflow sai trạng thái hoặc có dấu hiệu lặp bất thường.
- Ứng dụng cần chuyển sang hàng đợi xử lý thủ công hoặc yêu cầu người vận hành xem xét.
- Mô hình không được tự chọn một phương án khác sau khi chạm ranh giới an toàn.

`THROW` không tự hoàn tác những tool đã chạy trước đó. Nếu batch có nhiều tool call, một số thao tác có thể đã hoàn tất trước khi giới hạn bị phát hiện. Ứng dụng cần lưu kết quả một phần, dùng idempotency key và có quy trình bù trừ nếu nghiệp vụ yêu cầu.

## 5. RETURN_ERROR_RESPONSE: cho mô hình biết đã vượt giới hạn

Với `ToolCallLimitBehavior.RETURN_ERROR_RESPONSE`, manager không gọi callback vượt hạn. Thay vào đó, nó tạo một `ToolResponse` có nội dung báo rằng giới hạn đã đạt và thêm kết quả đó vào lịch sử hội thoại.

Mô hình nhận được thông báo như một tool result bình thường. Nó có thể:

- Dừng gọi tool và trả lời dựa trên dữ liệu đã thu thập.
- Giải thích rằng chưa thể hoàn tất vì đã đạt hạn mức.
- Chọn một tool khác nếu giới hạn tổng vẫn còn và tool đó phù hợp.
- Hỏi người dùng để thu hẹp yêu cầu hoặc tiếp tục trong một lượt mới theo chính sách ứng dụng.

Ví dụ với `ChatModel` và `ToolCallingManager`:

Giả sử `options` là `ToolCallingChatOptions` đã gắn callback và context cho lượt hiện tại:

~~~java
ToolExecutionResult result =
    toolCallingManager.executeToolCalls(prompt, chatResponse);

// Tool result báo vượt giới hạn đã nằm trong lịch sử.
Prompt nextPrompt = new Prompt(
    result.conversationHistory(),
    options
);

// Ứng dụng gửi lịch sử có thông báo lỗi về cho mô hình.
ChatResponse nextResponse = chatModel.call(nextPrompt);
~~~

Đoạn mã giả định manager được cấu hình `RETURN_ERROR_RESPONSE`. Khi dùng `ChatClient` với `ToolCallingAdvisor`, advisor tự đưa tool result vào vòng lặp và gọi mô hình tiếp; ứng dụng không cần tự nối lịch sử.

### Khi nào nên chọn RETURN_ERROR_RESPONSE?

Chọn chế độ này khi giới hạn là một thông tin để mô hình điều chỉnh chiến lược:

- Tool chỉ đọc dữ liệu, chẳng hạn tìm kiếm, tra cứu hoặc tổng hợp.
- Mô hình có thể trả lời hữu ích từ những kết quả đã có.
- Có lựa chọn thay thế hợp lệ và vẫn nằm trong ngân sách còn lại.
- Người dùng được lợi khi nhận một câu trả lời một phần hoặc một lời giải thích thay vì kết thúc ngay.

Ví dụ: người dùng yêu cầu tìm tất cả đơn hàng trong một khoảng thời gian. Mô hình gọi `search_orders` nhiều lần để phân trang và chạm giới hạn riêng của tool. Với `RETURN_ERROR_RESPONSE`, mô hình biết rằng không thể gọi thêm trang qua tool đó; nó có thể báo cáo dữ liệu đã thu thập chưa đầy đủ hoặc tóm tắt phần kết quả hiện có.

Không nên kỳ vọng mô hình luôn tự phục hồi. Mô hình có thể tiếp tục yêu cầu cùng tool, chọn một tool khác không phù hợp hoặc đưa ra kết luận thiếu dữ liệu. Ứng dụng vẫn cần kiểm tra câu trả lời, giới hạn vòng mô hình và deadline tổng thể.

## 6. So sánh hai chính sách

| Tiêu chí | `THROW` | `RETURN_ERROR_RESPONSE` |
| --- | --- | --- |
| Callback vượt hạn | Không được thực thi | Không được thực thi |
| Kết quả vượt hạn | `ToolCallLimitExceededException` | Tool response tổng hợp báo đạt giới hạn |
| Mô hình có cơ hội phản hồi tiếp? | Không qua vòng hiện tại; `ToolCallingAdvisor` trả response cuối | Có; error result được gửi lại mô hình |
| Ứng dụng gọi manager trực tiếp | Phải bắt exception | Nhận `ToolExecutionResult` và tự quyết định gọi mô hình tiếp |
| Phù hợp với | Ranh giới dừng cứng, thao tác rủi ro, lỗi cần người xử lý | Tool đọc dữ liệu, tác vụ có thể thu hẹp hoặc trả kết quả một phần |
| Rủi ro chính | Cần xử lý kết quả một phần và trạng thái workflow | Mô hình có thể thử lại hoặc tiếp tục chiến lược không hiệu quả |

Điểm chung quan trọng: cả hai chế độ đều chặn callback vượt giới hạn. `RETURN_ERROR_RESPONSE` chỉ thay đổi cách thông báo và điều phối tiếp; nó không cho phép gọi vượt hạn.

## 7. Phân biệt giới hạn tool call với lỗi khi thực thi tool

Không nhầm chính sách vượt giới hạn với chính sách xử lý exception do callback ném ra. Đây là hai cơ chế riêng:

| Tình huống | Cơ chế cấu hình |
| --- | --- |
| Tool được gọi quá số lần cho phép | `spring.ai.tools.limits.on-limit-exceeded` |
| Tool được phép gọi nhưng service phát sinh lỗi | `ToolExecutionExceptionProcessor` và `spring.ai.tools.throw-exception-on-error` |

`spring.ai.tools.throw-exception-on-error` điều khiển lỗi thực thi tool. Theo mặc định, `DefaultToolExecutionExceptionProcessor` gửi message của `RuntimeException` về mô hình; checked exception và `Error` luôn được ném lại. Property `true` yêu cầu ném lỗi tool cho caller; `false` gửi lỗi về mô hình theo processor mặc định.

~~~properties
# Chính sách khi chạm giới hạn số lần gọi
spring.ai.tools.limits.on-limit-exceeded=RETURN_ERROR_RESPONSE

# Chính sách cho exception phát sinh bên trong callback
spring.ai.tools.throw-exception-on-error=false
~~~

Hai property trên không thay thế nhau. Ví dụ, một lần gọi `search_orders` vẫn còn hạn mức nhưng database bị timeout: đó là lỗi thực thi tool. Nếu `search_orders` đã chạm giới hạn trước khi callback được gọi, đó là lỗi giới hạn tool call.

## 8. Đếm giới hạn theo lượt như thế nào?

Giới hạn được tính trong **lượt hiện tại**, bắt đầu từ `UserMessage` gần nhất. Manager đếm các `ToolResponseMessage` từ điểm đó trở đi, không lấy toàn bộ lịch sử các lượt cũ làm số lần gọi của lượt mới.

Điều này có một số hệ quả:

- Lịch sử cũ được `ChatMemory` nạp trước lượt mới không làm tăng bộ đếm của lượt hiện tại.
- Manager tính lại số lần gọi từ prompt history mỗi khi thực thi; bộ đếm không nằm trong một field mutable dùng chung.
- Có thể chia sẻ một `ToolCallingManager` giữa các request đồng thời mà không làm trộn bộ đếm nội bộ.
- Khi khôi phục workflow, prompt phải giữ các tool response của những vòng trước trong cùng lượt. Nếu ứng dụng chỉ gửi một phần lịch sử, manager không thể đếm những response đã bị bỏ khỏi prompt.

Nếu cần giới hạn theo ngày, theo người dùng, theo tenant, theo API key hoặc theo tổng chi phí của nhiều lượt, hãy bổ sung rate limiter hoặc quota service ở tầng ứng dụng. Giới hạn của `DefaultToolCallingManager` không phải quota dài hạn.

## 9. Giới hạn tool call không thay thế giới hạn vòng mô hình

`maxCallsPerTool` và `maxTotalToolCalls` giới hạn số tool response trong một lượt. Chúng không đặt ra một ngân sách tổng quát cho mọi lần gọi mô hình.

Với `RETURN_ERROR_RESPONSE`, mô hình được phép nhìn thấy thông báo giới hạn và tiếp tục. Nếu nó cứ yêu cầu một tool đã chạm hạn mức, manager tiếp tục từ chối callback đó; nhưng workflow vẫn cần giới hạn số vòng mô hình, thời gian và token để bảo vệ tài nguyên.

Nên kết hợp:

- Giới hạn theo tool và tổng tool call trong manager.
- Số vòng gọi mô hình tối đa trong orchestrator hoặc workflow.
- Deadline cho toàn lượt và timeout cho từng service.
- Ngân sách token/chi phí nếu có yêu cầu.
- Chính sách retry hữu hạn và idempotency cho thao tác ghi.

Đừng tăng giới hạn hoặc tắt giới hạn chỉ để làm biến mất lỗi. Nếu workload hợp lệ cần nhiều lần gọi hơn, hãy đo số lần thực tế, tăng giới hạn có chủ đích và giữ giới hạn tổng.

## 10. Chọn chính sách theo loại nghiệp vụ

| Loại tool | Chính sách thường phù hợp | Lý do |
| --- | --- | --- |
| Tìm kiếm, tra cứu chỉ đọc | `RETURN_ERROR_RESPONSE` | Mô hình có thể tóm tắt dữ liệu hiện có hoặc báo chưa đầy đủ |
| Phân trang dữ liệu | `RETURN_ERROR_RESPONSE` | Mô hình có thể dừng phân trang và giải thích phạm vi đã đọc |
| Kiểm tra trạng thái nghiệp vụ | Tùy trường hợp | Có thể trả một phần nếu an toàn; dừng nếu vượt hạn cho thấy workflow bất thường |
| Gửi email hoặc thông báo | `THROW` | Tránh lặp gửi và chuyển lỗi sang xử lý rõ ràng |
| Thanh toán, hoàn tiền, đặt lệnh | `THROW` | Cần dừng workflow và kiểm tra trạng thái giao dịch |
| Xóa hoặc thay đổi quyền truy cập | `THROW` | Không để mô hình tự chọn tiếp sau khi chạm giới hạn |

Đây là định hướng ban đầu. Hành vi cuối cùng phải dựa trên hậu quả của tool, khả năng đảo ngược, idempotency và chính sách nghiệp vụ của hệ thống.

## 11. Kiểm thử hành vi vượt giới hạn

Nên kiểm thử cả hai chính sách với giới hạn nhỏ để không cần gọi tool hàng chục lần:

| Ca kiểm thử | Cấu hình | Điều cần xác minh |
| --- | --- | --- |
| Chưa chạm giới hạn theo tool | `maxCallsPerTool(2)` | Hai lần gọi hợp lệ chạy callback |
| Chạm giới hạn theo tool | `maxCallsPerTool(1)` | Lần gọi tiếp theo không chạy callback |
| Chạm giới hạn tổng | `maxTotalToolCalls(2)` | Tool thứ ba bị chặn dù tên khác |
| `THROW` trực tiếp | Manager + `THROW` | Ném `ToolCallLimitExceededException` với đúng tool/limit |
| `THROW` trong ChatClient | Advisor mặc định | Trả response cuối có finish reason vượt giới hạn |
| Kết quả một phần | Batch có call hợp lệ trước call vượt hạn | Kết quả đã hoàn tất được giữ lại |
| `RETURN_ERROR_RESPONSE` | Manager + `RETURN_ERROR_RESPONSE` | Không gọi callback vượt hạn; lịch sử có tool response báo lỗi |
| Model nhận thông báo | ChatModel/ChatClient tiếp tục vòng | Mô hình được cung cấp error result và có thể kết thúc |
| Tool bị miễn giới hạn riêng | `excludeToolFromLimit(...)` | Tool không bị giới hạn theo tên nhưng vẫn tính vào tổng |
| Lượt hội thoại mới | Bắt đầu bằng `UserMessage` mới | Bộ đếm lượt trước không ảnh hưởng lượt mới |
| Khôi phục từ checkpoint | History thiếu các tool response trước đó | Kiểm tra ứng dụng khôi phục đầy đủ history hoặc quota ngoài |
| Nhiều request đồng thời | Dùng chung manager | Không trộn bộ đếm giữa request |

Với `THROW`, kiểm tra `getPartialToolExecutionResult()` để bảo đảm kết quả của tool đã chạy không bị bỏ qua. Với `RETURN_ERROR_RESPONSE`, kiểm tra `ToolResponseMessage` được thêm vào history và callback vượt hạn không được gọi.

## 12. Checklist triển khai

Trước khi chọn chính sách, hãy trả lời:

- Giới hạn theo tool và giới hạn tổng đã phù hợp với workload hợp lệ chưa?
- Tool chỉ đọc hay có tác động phụ?
- Nếu chặn tool, mô hình còn có thể trả lời hữu ích từ dữ liệu hiện có không?
- Nếu mô hình tiếp tục, có nguy cơ lặp lại yêu cầu hoặc tiêu tốn thêm token không?
- Có giới hạn số vòng mô hình và deadline tổng thể không?
- Khi dùng `THROW`, ứng dụng có lưu hoặc xử lý kết quả một phần không?
- Khi dùng `RETURN_ERROR_RESPONSE`, mô hình có được hướng dẫn không kết luận vượt quá dữ liệu đã có không?
- Các tool ghi có idempotency và kiểm tra quyền tại service không?
- Quota theo người dùng/tenant/ngày có được kiểm soát ở tầng phù hợp không?
- Log và metrics có phân biệt limit breach với tool execution error không?

## Bài thực hành

Một assistant hỗ trợ đơn hàng có ba tool:

- `search_orders`: tìm đơn hàng theo bộ lọc.
- `get_order_detail`: xem chi tiết một đơn hàng.
- `issue_refund`: thực hiện hoàn tiền.

Hãy cấu hình:

1. `search_orders` tối đa 3 lần mỗi lượt.
2. `get_order_detail` tối đa 5 lần mỗi lượt.
3. Tổng số tool call tối đa 8 lần mỗi lượt.
4. Khi vượt giới hạn tìm kiếm, trả thông báo cho mô hình để mô hình có thể báo dữ liệu chưa đầy đủ.
5. Khi workflow hoàn tiền vượt giới hạn, kết thúc bằng lỗi và yêu cầu người vận hành kiểm tra.

Vì `onLimitExceeded` là chính sách chung của một `ToolCallingManager`, hãy thiết kế cách tách workflow hoặc lớp điều phối để hai loại nghiệp vụ có hành vi khác nhau. Viết test xác nhận callback `issue_refund` không bị thực thi ngoài giới hạn và các kết quả tra cứu đã hoàn tất vẫn được bảo toàn.

Sau khi hoàn thành, hãy giải thích vì sao `RETURN_ERROR_RESPONSE` không có nghĩa là tăng giới hạn, và vì sao giới hạn tool call không thay thế quota theo người dùng hoặc theo ngày.

## Ghi nhớ

`THROW` là lựa chọn dừng cứng: `DefaultToolCallingManager` ném `ToolCallLimitExceededException`, mang theo giới hạn bị vượt và kết quả thực thi một phần. Trong `ChatClient`, `ToolCallingAdvisor` chuyển exception thành response cuối; khi gọi manager trực tiếp, ứng dụng phải bắt exception. `RETURN_ERROR_RESPONSE` bỏ qua callback vượt hạn và thêm tool result báo lỗi để mô hình có cơ hội quyết định bước tiếp theo. Chọn chính sách theo mức độ rủi ro và khả năng phục hồi, đồng thời luôn đặt giới hạn vòng mô hình, deadline, quota nghiệp vụ và kiểm tra quyền ở các lớp tương ứng.

## Tài liệu tham khảo

- [Spring AI — Tool Calling: Tool Call Limits](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [ToolCallLimitBehavior API — Spring AI 2.1.x](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/model/tool/ToolCallLimitBehavior.html)
- [ToolCallLimitExceededException API — Spring AI 2.1.x](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/model/tool/ToolCallLimitExceededException.html)
- [DefaultToolCallingManager API — Spring AI 2.1.x](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/model/tool/DefaultToolCallingManager.html)
