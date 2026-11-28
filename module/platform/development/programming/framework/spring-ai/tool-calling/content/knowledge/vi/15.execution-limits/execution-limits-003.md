# Cấu hình hạn mức chung và ngoại lệ theo khả năng phiên bản

Một vòng tool calling có thể yêu cầu mô hình gọi đi gọi lại cùng một công cụ, hoặc yêu cầu nhiều công cụ trong một lượt. Nếu không có giới hạn, một lỗi trong prompt, kết quả công cụ hoặc quyết định của mô hình có thể khiến ứng dụng thực thi quá nhiều lần, tăng chi phí và tải lên dịch vụ nghiệp vụ.

Spring AI bổ sung hạn mức gọi công cụ theo từng lượt người dùng từ phiên bản **2.0.1**. Cơ chế này có hai lớp: giới hạn mặc định cho mỗi tên công cụ và giới hạn tổng số lần gọi của tất cả công cụ. Ứng dụng có thể đặt ngoại lệ cho một số công cụ, chọn cách xử lý khi chạm ngưỡng và cấu hình qua Spring Boot properties hoặc `ToolCallingManager.Builder`.

Các bản Spring AI 1.x và 2.0.0 chưa có cơ chế hạn mức tích hợp này. Nếu phải giữ các phiên bản đó, ứng dụng cần tự điều khiển vòng gọi công cụ và đếm số lần gọi trước khi thực thi.

## Hạn mức bảo vệ điều gì?

Hạn mức của Spring AI kiểm soát số lần callback được yêu cầu thực thi trong một lượt hội thoại. Có hai loại:

| Loại hạn mức | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Per-tool limit | Giới hạn số lần một công cụ có cùng tên được gọi trong một lượt | `orders_search` tối đa 12 lần. |
| Total tool-call limit | Giới hạn tổng số lần gọi của tất cả công cụ trong một lượt | Toàn bộ công cụ cộng lại tối đa 120 lần. |

Một phản hồi của mô hình có thể chứa nhiều tool call. Mỗi lần gọi trong phản hồi đó đều được tính. Vì vậy, hạn mức không đồng nghĩa với số vòng lặp của advisor: một iteration có thể yêu cầu nhiều công cụ, và một công cụ có thể được gọi ở nhiều iteration.

Hạn mức này cũng không phải timeout, giới hạn số token, giới hạn tốc độ request của provider hay giới hạn số callback được đăng ký. Các cơ chế đó cần được cấu hình riêng. Ví dụ, giới hạn 120 tool call không ngăn một callback duy nhất chạy trong 10 phút; ứng dụng vẫn cần timeout cho lời gọi service.

## Khả năng theo phiên bản Spring AI

| Phiên bản | Hạn mức tích hợp | Cách kiểm soát |
| --- | --- | --- |
| Spring AI 1.0.x / 1.1.x | Chưa có giới hạn số lần gọi theo tool hoặc tổng lượt trong `DefaultToolCallingManager.Builder` | Chuyển sang user-controlled execution và tự đếm trong vòng lặp. |
| Spring AI 2.0.0 | Chưa có tool-call limits tích hợp | Dùng vòng lặp do ứng dụng điều khiển hoặc một cơ chế điều phối tùy chỉnh. |
| Spring AI 2.0.1 trở đi | Có per-tool limit, total limit, ngoại lệ theo tên và chính sách khi vượt ngưỡng | Dùng `spring.ai.tools.limits.*` hoặc `ToolCallingManager.Builder`. |

Các hạn mức mặc định trong Spring AI 2.0.1 trở đi là:

| Hạn mức | Giá trị mặc định |
| --- | ---: |
| Số lần gọi một tool trong một lượt | 40 |
| Tổng số tool call trong một lượt | 150 |
| Cách xử lý khi vượt ngưỡng | `THROW` |

Các giá trị mặc định áp dụng ngay cả khi ứng dụng không khai báo properties. Chúng được thiết kế để ngăn vòng lặp bất thường nhưng vẫn đủ rộng cho nhiều workflow có phân trang hoặc nhiều bước. Nếu workflow hợp lệ cần nhiều lần gọi hơn, hãy điều chỉnh rõ ràng thay vì tắt toàn bộ giới hạn một cách mặc định.

## Phạm vi đếm: một lượt người dùng

Spring AI đếm tool call trong lượt hiện tại, bắt đầu từ `UserMessage` gần nhất. Manager tìm các `ToolResponseMessage` trong lịch sử của lượt đó để xác định số lần công cụ đã được gọi.

Điều này có ba hệ quả:

1. Tool call từ lượt người dùng trước không làm cạn hạn mức của lượt mới, dù các message cũ vẫn được nạp từ chat memory.
2. Các tool call ở nhiều iteration trong cùng một lượt được cộng dồn.
3. Hạn mức được tính lại từ conversation history mỗi lần manager thực thi; manager không giữ bộ đếm mutable dùng chung giữa các request.

Do đó, một `ToolCallingManager` có thể được chia sẻ giữa các request đồng thời mà bộ đếm của người dùng này không làm tăng bộ đếm của người dùng khác. Ứng dụng vẫn phải bảo đảm conversation history của từng request không bị trộn lẫn.

Ví dụ, trong một lượt người dùng, mô hình gọi `orders_search` 4 lần, `inventory_lookup` 2 lần rồi `orders_search` thêm 3 lần. Tổng số lần gọi là 9; số lần của `orders_search` là 7. Nếu lượt tiếp theo bắt đầu bằng một `UserMessage` mới, các lần gọi trước đó không được cộng vào lượt mới.

## Cấu hình hạn mức chung bằng Spring Boot

Với ứng dụng dùng Spring Boot auto-configuration, có thể khai báo hạn mức chung trong `application.yml`:

```yaml
spring:
  ai:
    tools:
      limits:
        max-calls-per-tool-default: 40
        max-total-tool-calls: 120
        on-limit-exceeded: THROW
```

Trong ví dụ, mỗi tool được gọi tối đa 40 lần trong một lượt và toàn bộ công cụ có tổng cộng tối đa 120 lần. `on-limit-exceeded` chọn cách manager xử lý khi một trong hai ngưỡng bị vượt.

Có thể đặt các giá trị tương đương trong `application.properties`:

```properties
spring.ai.tools.limits.max-calls-per-tool-default=40
spring.ai.tools.limits.max-total-tool-calls=120
spring.ai.tools.limits.on-limit-exceeded=THROW
```

Không cần khai báo lại các giá trị mặc định nếu chúng phù hợp. Khai báo tường minh thường hữu ích khi muốn tài liệu hóa chính sách vận hành và tránh việc nhóm phát triển hiểu nhầm các giá trị mặc định.

## Đặt ngoại lệ cho từng công cụ

Một số công cụ có đặc điểm sử dụng khác nhau. Công cụ tìm kiếm có thể được gọi nhiều lần để phân trang; công cụ lấy thời gian hiện tại có thể không cần giới hạn riêng; công cụ hoàn tiền cần giới hạn thấp hơn để giảm rủi ro.

Spring AI cho phép override per-tool limit bằng tên công cụ:

```yaml
spring:
  ai:
    tools:
      limits:
        max-calls-per-tool-default: 40
        max-calls-per-tool:
          orders_search: 12
          inventory_lookup: 8
          payments_refund: 2
        excluded-tools:
          - getCurrentTime
        max-total-tool-calls: 120
        on-limit-exceeded: THROW
```

Quy tắc trong ví dụ:

- `orders_search` có giới hạn riêng là 12 lần, thay cho mặc định 40.
- `inventory_lookup` tối đa 8 lần.
- `payments_refund` tối đa 2 lần trong một lượt.
- `getCurrentTime` được miễn per-tool limit.
- Tất cả các công cụ, kể cả công cụ được miễn per-tool limit, vẫn được tính vào `max-total-tool-calls` là 120.

Tên dùng trong map phải khớp với tên được công bố trong `ToolDefinition.name()`. Hãy dùng tên ổn định, không phụ thuộc tên class Java hoặc tên bean nếu chúng khác với tên tool mà mô hình nhìn thấy.

### Ngoại lệ bằng giá trị `-1`

Có thể dùng `-1` để tắt một giới hạn:

```yaml
spring:
  ai:
    tools:
      limits:
        max-calls-per-tool-default: 40
        max-calls-per-tool:
          report_export: -1
          orders_search: 12
        max-total-tool-calls: 120
```

Ở đây `report_export` không có giới hạn riêng theo tên công cụ, còn `orders_search` vẫn bị giới hạn 12 lần. Nếu `max-calls-per-tool-default` là `-1`, mặc định per-tool được tắt cho mọi công cụ chưa có override. Một tool có override dương vẫn có thể bị giới hạn theo giá trị đó.

Để tắt tổng hạn mức, đặt `max-total-tool-calls: -1`. Cần cân nhắc kỹ vì khi tắt tổng hạn mức, các công cụ được miễn per-tool có thể được gọi không giới hạn trong một lượt.

### Dùng `excluded-tools`

`excluded-tools` là danh sách tên công cụ được miễn per-tool limit:

```yaml
spring:
  ai:
    tools:
      limits:
        excluded-tools:
          - getCurrentTime
          - generateCorrelationId
```

Các công cụ này vẫn tính vào tổng số tool call. Đây là điểm quan trọng: miễn giới hạn riêng không có nghĩa miễn toàn bộ hạn mức. Nếu tổng lượt đã chạm ngưỡng, một công cụ trong `excluded-tools` vẫn có thể bị từ chối.

## Chọn hành vi khi vượt hạn mức

Spring AI cung cấp hai lựa chọn qua `spring.ai.tools.limits.on-limit-exceeded`:

| Giá trị | Hành vi | Khi nào phù hợp |
| --- | --- | --- |
| `THROW` | Ném `ToolCallLimitExceededException` khi một lời gọi vượt ngưỡng | Muốn dừng vòng tool calling ngay và để ứng dụng xử lý tình trạng vượt hạn mức. |
| `RETURN_ERROR_RESPONSE` | Bỏ qua lời gọi vượt ngưỡng và tạo tool response chứa thông báo lỗi để gửi lại mô hình | Muốn mô hình biết công cụ đã chạm hạn mức và có cơ hội đưa ra phương án khác. |

`THROW` là mặc định. Với `ToolCallingAdvisor`, advisor bắt ngoại lệ và trả về response cuối biểu thị hạn mức đã bị vượt. Response có finish reason `ToolCallLimitExceededException.FINISH_REASON`. Nếu một batch có một số tool call đã thực thi thành công trước khi chạm ngưỡng, các kết quả đó được giữ trong metadata `METADATA_PARTIAL_TOOL_RESPONSES` của generation cuối.

Với `RETURN_ERROR_RESPONSE`, manager không gọi callback vượt ngưỡng mà tạo một `ToolResponse` báo giới hạn. Mô hình nhận được phản hồi này và có thể chọn hành động khác hoặc giải thích rằng yêu cầu không thể tiếp tục. Nếu mô hình liên tục yêu cầu cùng công cụ, các lần tiếp theo cũng sẽ bị từ chối; ứng dụng vẫn cần kiểm soát vòng lặp, timeout và tổng chi phí.

Khi gọi `ToolCallingManager.executeToolCalls(...)` trực tiếp mà không đi qua `ToolCallingAdvisor`, `THROW` sẽ được ném về caller. Nếu muốn manager trả tool error để caller đưa lại mô hình, hãy chọn `RETURN_ERROR_RESPONSE`.

## Tùy chỉnh bằng ToolCallingManager.Builder

Khi cần cấu hình bằng Java hoặc cần tạo các manager khác nhau cho từng workflow, dùng `ToolCallingManager.Builder`:

```java
import org.springframework.ai.model.tool.ToolCallLimitBehavior;
import org.springframework.ai.model.tool.ToolCallingManager;

ToolCallingManager toolCallingManager = ToolCallingManager.builder()
        .maxCallsPerTool(40)
        .maxCallsPerTool("orders_search", 12)
        .maxCallsPerTool("payments_refund", 2)
        .excludeToolFromLimit("getCurrentTime")
        .maxTotalToolCalls(120)
        .onLimitExceeded(ToolCallLimitBehavior.RETURN_ERROR_RESPONSE)
        .build();
```

Trong builder:

- `maxCallsPerTool(int)` đặt giới hạn mặc định cho từng tool.
- `maxCallsPerTool(String, int)` override giới hạn cho một tên tool.
- `excludeToolFromLimit(String)` miễn per-tool limit cho một tool, kể cả khi đã có override; tool đó vẫn tính vào total limit.
- `maxTotalToolCalls(int)` đặt giới hạn tổng.
- `unlimitedCallsPerTool()` tắt per-tool default limit.
- `unlimitedTotalToolCalls()` tắt total limit.
- `onLimitExceeded(...)` chọn `THROW` hoặc `RETURN_ERROR_RESPONSE`.

Nếu manager này được dùng với `ToolCallingAdvisor`, truyền nó vào builder của advisor:

```java
ToolCallingAdvisor toolCallingAdvisor = ToolCallingAdvisor.builder()
        .toolCallingManager(toolCallingManager)
        .build();

ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultAdvisors(toolCallingAdvisor)
        .build();
```

Khi tự đăng ký `ToolCallingAdvisor`, bảo đảm chain chỉ có một tool advisor. Nếu ứng dụng đã dùng auto-configuration, chọn một cách cấu hình manager nhất quán để không vô tình tạo một manager custom nhưng vẫn để request chạy qua manager mặc định.

## Khi nào nên dùng properties và khi nào nên dùng builder?

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Một chính sách chung cho toàn ứng dụng | `spring.ai.tools.limits.*` trong cấu hình Spring Boot. |
| Một vài công cụ cần ngưỡng thấp hơn hoặc được miễn per-tool | `max-calls-per-tool.<name>` hoặc `excluded-tools`. |
| Một workflow có tổng hạn mức khác workflow khác | Tạo `ToolCallingManager` và `ToolCallingAdvisor` riêng cho workflow đó. |
| Tự điều khiển tool execution hoặc gọi manager trực tiếp | Cấu hình `ToolCallingManager.Builder` và chọn `RETURN_ERROR_RESPONSE` hoặc tự bắt ngoại lệ. |
| Chạy Spring AI trước 2.0.1 | Tự đếm trong vòng tool execution do ứng dụng kiểm soát. |

Properties là lựa chọn đơn giản khi toàn ứng dụng dùng cùng một chính sách. Builder phù hợp khi chính sách phụ thuộc vào capability hoặc workflow. Tránh tạo nhiều manager có cấu hình không rõ ràng; hãy ghi rõ workflow nào sử dụng manager nào và kiểm thử cấu hình đó.

## Cách xử lý ngoại lệ trong mã ứng dụng

Với `THROW`, `ToolCallLimitExceededException` cung cấp thông tin về giới hạn đã bị chạm:

```java
try {
    ToolExecutionResult result = toolCallingManager.executeToolCalls(prompt, chatResponse);
    // Tiếp tục hội thoại với result.conversationHistory().
}
catch (ToolCallLimitExceededException ex) {
    String toolName = ex.getToolName(); // null nếu vượt tổng hạn mức
    int limit = ex.getLimit();
    ToolExecutionResult partialResult = ex.getPartialToolExecutionResult();

    // Ghi nhận limit breach và xử lý các kết quả đã hoàn tất theo chính sách ứng dụng.
}
```

`getToolName()` trả về tên tool gây vượt per-tool limit; giá trị là `null` nếu vượt total limit. `getLimit()` trả ngưỡng bị vi phạm. `getPartialToolExecutionResult()` giữ kết quả của các tool call đã thực thi trong batch trước khi giới hạn bị chạm, cùng phản hồi lỗi được tạo cho lời gọi bị chặn.

Không nên bỏ qua các kết quả đã thực thi thành công trong batch. Nếu tool có side effect như tạo đơn, gửi thông báo hoặc ghi dữ liệu, ứng dụng cần ghi nhận trạng thái thực thi để tránh chạy lại cùng thao tác khi retry. Hạn mức không tự rollback các thao tác đã hoàn tất.

## Cấu hình hạn mức cho Spring AI 1.x và 2.0.0

Trong Spring AI 1.0.x/1.1.x, `DefaultToolCallingManager.Builder` chưa có `maxCallsPerTool`, `maxTotalToolCalls` hoặc `onLimitExceeded`. `ChatModel` thực hiện vòng tool execution nội bộ theo mặc định. Muốn áp dụng giới hạn, cần chuyển sang user-controlled execution bằng cách tắt internal execution rồi tự đếm các tool call trước khi giao cho manager thực thi.

Ví dụ dưới đây minh họa cách tự kiểm soát trong Spring AI 1.x:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.model.tool.ToolCallingChatOptions;
import org.springframework.ai.model.tool.ToolCallingManager;
import org.springframework.ai.model.tool.ToolExecutionResult;
import org.springframework.ai.support.ToolCallbacks;

int defaultPerToolLimit = 8;
int totalLimit = 30;
Map<String, Integer> perToolOverrides = Map.of("orders_search", 12);
Set<String> excludedTools = Set.of("getCurrentTime");

Map<String, Integer> callsByTool = new HashMap<>();
int totalCalls = 0;

ToolCallingChatOptions options = ToolCallingChatOptions.builder()
        .toolCallbacks(ToolCallbacks.from(new OrderTools()))
        .internalToolExecutionEnabled(false)
        .build();

ToolCallingManager manager = ToolCallingManager.builder().build();
Prompt prompt = new Prompt("Tra cứu các đơn hàng phù hợp", options);
ChatResponse response = chatModel.call(prompt);

while (response.hasToolCalls()) {
    List<AssistantMessage.ToolCall> batch = response.getResult().getOutput().getToolCalls();

    if (totalLimit >= 0 && totalCalls + batch.size() > totalLimit) {
        throw new IllegalStateException("Đã vượt total tool-call limit");
    }

    Map<String, Long> requestedByTool = batch.stream().collect(
            Collectors.groupingBy(AssistantMessage.ToolCall::name, Collectors.counting()));

    for (Map.Entry<String, Long> entry : requestedByTool.entrySet()) {
        String toolName = entry.getKey();
        if (excludedTools.contains(toolName)) {
            continue;
        }

        int limit = perToolOverrides.getOrDefault(toolName, defaultPerToolLimit);
        int alreadyCalled = callsByTool.getOrDefault(toolName, 0);
        if (limit >= 0 && alreadyCalled + entry.getValue() > limit) {
            throw new IllegalStateException("Đã vượt per-tool limit: " + toolName);
        }
    }

    // Chỉ tăng bộ đếm sau khi toàn bộ batch đã qua bước kiểm tra.
    requestedByTool.forEach((name, count) ->
            callsByTool.merge(name, Math.toIntExact(count), Integer::sum));
    totalCalls += batch.size();

    ToolExecutionResult execution = manager.executeToolCalls(prompt, response);
    prompt = new Prompt(execution.conversationHistory(), options);
    response = chatModel.call(prompt);
}

String answer = response.getResult().getOutput().getText();
```

Đoạn code là ví dụ về chính sách admission trước khi thực thi một batch:

- Đếm từng tên tool trong batch hiện tại, không chỉ đếm số iteration.
- Kiểm tra tổng hạn mức trước khi gọi `executeToolCalls(...)`.
- Kiểm tra per-tool limit với số lần đã gọi ở các batch trước cộng số lần tool xuất hiện trong batch hiện tại.
- Không áp dụng per-tool limit cho tên trong `excludedTools`; các lần gọi đó vẫn tính vào total limit.
- Chỉ cập nhật bộ đếm sau khi toàn bộ batch hợp lệ, rồi mới giao batch cho manager.

Trong Spring AI 2.0.0, vòng thực thi nội bộ của `ChatModel` đã được loại bỏ. Có thể dùng cùng ý tưởng kiểm tra batch trước `ToolCallingManager.executeToolCalls(...)` trong vòng do ứng dụng điều khiển; bỏ `.internalToolExecutionEnabled(false)` vì tùy chọn đó đã bị loại bỏ từ 2.0.0. Nếu vẫn muốn dùng `ChatClient` tự động, cần xây dựng một tool advisor/manager tùy chỉnh có chính sách đếm tương đương.

Ví dụ manual loop không phải cấu hình tự động toàn ứng dụng. Ứng dụng cần bổ sung xử lý khi vượt ngưỡng, log, timeout và quy tắc cho các thao tác đã thực thi. Nếu chỉ cần hạn mức chuẩn, nâng lên Spring AI 2.0.1 trở đi sẽ đơn giản hơn.

## Chọn hạn mức theo mức độ rủi ro của công cụ

Không nên đặt cùng một ngưỡng cho mọi công cụ mà không xét đến chi phí và tác động của chúng. Có thể bắt đầu từ một chính sách như sau:

| Nhóm công cụ | Ví dụ | Cách đặt hạn mức |
| --- | --- | --- |
| Tra cứu nhẹ | `getCurrentTime`, `getReferenceData` | Có thể miễn per-tool limit nếu chi phí thấp và thao tác an toàn; vẫn giữ total limit. |
| Tìm kiếm/phân trang | `orders_search`, `catalog_search` | Đặt ngưỡng vừa đủ cho số trang hợp lệ của một lượt. |
| Truy vấn tốn tài nguyên | `runAnalytics`, `generateReport` | Đặt ngưỡng thấp và thêm timeout hoặc hàng đợi riêng. |
| Thay đổi dữ liệu | `orders_update`, `customers_update` | Giới hạn thấp, kiểm tra quyền và tính idempotent ở service. |
| Thao tác nhạy cảm | `payments_refund`, `orders_cancel` | Giới hạn rất thấp, yêu cầu xác nhận/phê duyệt khi cần và ghi audit. |

Hạn mức là một lớp bảo vệ vận hành. Nó không thay thế phân quyền, xác nhận của người dùng, idempotency hoặc kiểm tra trạng thái nghiệp vụ. Ví dụ, giới hạn `payments_refund` ở 2 lần không bảo đảm người dùng có quyền hoàn tiền và cũng không bảo đảm hai lần gọi không hoàn tiền trùng cho cùng giao dịch.

## Kết hợp với các giới hạn vận hành khác

Để bảo vệ toàn bộ hệ thống, nên kết hợp tool-call limits với các kiểm soát khác:

- **Timeout cho callback:** giới hạn thời gian truy vấn database, gọi HTTP hoặc chạy tác vụ dài.
- **Rate limit:** giới hạn tần suất request của người dùng hoặc tenant trong một khoảng thời gian, không chỉ trong một lượt chat.
- **Concurrency limit:** giới hạn số callback nặng chạy đồng thời để bảo vệ connection pool và dịch vụ phụ thuộc.
- **Retry có kiểm soát:** giới hạn số lần retry và chỉ retry thao tác an toàn hoặc có idempotency key.
- **Model/token budget:** kiểm soát số lần gọi mô hình, token đầu vào/đầu ra và chi phí theo request.
- **Authorization:** kiểm tra quyền mỗi khi callback thực thi; không dựa vào việc mô hình chỉ nhìn thấy tool nào.
- **Observability:** ghi số lần gọi theo tên tool, thời gian, lỗi và limit breach; tránh log arguments hoặc kết quả nhạy cảm.

`max-total-tool-calls` giới hạn số lần công cụ được gọi trong một lượt, nhưng không giới hạn số lượt người dùng trong ngày hoặc số request đồng thời. Nếu cần quota theo tenant/ngày, hãy triển khai ở tầng ứng dụng hoặc API gateway.

## Kiểm thử hạn mức

Nên kiểm thử cả trường hợp trong ngưỡng, đúng ngưỡng và vượt ngưỡng. Có thể dùng callback giả để kiểm soát số lần thực thi và không cần gọi model thật.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Tool được gọi ít hơn per-tool limit | Callback thực thi bình thường. |
| Tool được gọi đúng bằng per-tool limit | Lời gọi cuối cùng trong ngưỡng được thực thi. |
| Tool được gọi thêm một lần sau per-tool limit | Callback bị chặn theo `on-limit-exceeded`. |
| Một tool có override thấp hơn default | Override được áp dụng cho tool đó. |
| Tool nằm trong `excluded-tools` | Không áp dụng per-tool limit, nhưng vẫn tính vào total limit. |
| Tổng số lần gọi đạt total limit | Lời gọi tiếp theo bị chặn dù tool đó chưa chạm per-tool limit. |
| Một batch có nhiều tool call cùng tên | Tất cả call trong batch được cộng vào per-tool count. |
| Một batch có nhiều tên tool | Mỗi tool được kiểm tra riêng và toàn batch được kiểm tra tổng. |
| Lượt người dùng mới bắt đầu | Bộ đếm của lượt trước không được cộng sang lượt mới. |
| Hai request chạy đồng thời | Bộ đếm của từng lượt không ảnh hưởng lẫn nhau. |
| `THROW` | Manager ném ngoại lệ; kiểm tra tên tool, ngưỡng và partial result. |
| `RETURN_ERROR_RESPONSE` | Callback vượt ngưỡng không chạy; mô hình nhận tool error response. |

Ngoài unit test cho manager, nên có integration test qua `ChatClient` để xác nhận `ToolCallingAdvisor` xử lý đúng ngoại lệ và trả response cuối. Nếu dùng user-controlled execution, kiểm thử cả việc caller nhận ngoại lệ hoặc error response theo cấu hình.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Properties không có tác dụng | Dùng Spring AI trước 2.0.1 hoặc tự tạo manager khác với manager auto-configured | Xác nhận phiên bản và manager thực sự được advisor sử dụng. |
| Một tool bị giới hạn theo giá trị mặc định thay vì override | Key không khớp `ToolDefinition.name()` | Kiểm tra tên tool cuối cùng mà mô hình nhìn thấy. |
| Tool được miễn per-tool nhưng vẫn bị chặn | Total limit đã đạt | Nhớ rằng excluded tool vẫn tính vào tổng số lần gọi. |
| Lượt mới bị tính cả tool call cũ | Conversation history hoặc ranh giới `UserMessage` được xây dựng sai | Kiểm tra lịch sử gửi vào manager và điểm bắt đầu lượt hiện tại. |
| Caller nhận exception dù đã chọn error response | Manager được tạo ở nơi khác với cấu hình mong muốn | Kiểm tra manager được inject vào `ToolCallingAdvisor` hoặc caller trực tiếp. |
| Mô hình tiếp tục gọi tool sau khi nhận lỗi hạn mức | `RETURN_ERROR_RESPONSE` cho phép mô hình thử hướng khác | Giữ total limit, thêm điều kiện kết thúc hoặc chuyển sang thông báo dừng ở ứng dụng. |
| Tác vụ đã chạy trước khi batch chạm ngưỡng | Một số callback trong batch hoàn tất trước khi phát hiện breach | Đọc partial result và bảo đảm side effect có audit/idempotency; không giả định rollback. |
| Hạn mức không ngăn callback chạy quá lâu | Hạn mức đếm số lần gọi, không đếm thời gian | Thêm timeout và concurrency limit riêng. |

## Quy trình cấu hình

1. Xác định phiên bản Spring AI và kiểm tra phiên bản có hỗ trợ `spring.ai.tools.limits.*` hay không.
2. Chọn per-tool default và total limit dựa trên workflow hợp lệ.
3. Đặt override thấp hơn cho công cụ tốn tài nguyên hoặc có tác động phụ.
4. Chỉ miễn per-tool limit cho công cụ thật sự cần gọi lặp; vẫn giữ total limit.
5. Chọn `THROW` nếu ứng dụng cần dừng rõ ràng, hoặc `RETURN_ERROR_RESPONSE` nếu muốn mô hình nhận lỗi và thử cách khác.
6. Nếu dùng builder, bảo đảm `ToolCallingAdvisor` sử dụng đúng `ToolCallingManager` đã cấu hình.
7. Nếu đang ở phiên bản cũ, tự điều khiển vòng lặp và kiểm tra toàn bộ batch trước khi thực thi.
8. Kiểm thử đếm theo lượt, ngoại lệ, partial results, request đồng thời và thao tác có side effect.
9. Kết hợp tool-call limits với timeout, rate limit, concurrency limit, authorization và audit.

Spring AI 2.0.1 trở đi cung cấp hạn mức mặc định đủ dùng cho nhiều trường hợp và cho phép override theo tên công cụ. Hãy xem per-tool limit như chính sách cho từng capability, total limit như hàng rào cuối cho cả lượt, và các kiểm soát ở tầng ứng dụng như lớp bảo vệ cho thời gian, quyền và tác động nghiệp vụ.

## Tài liệu tham khảo

- [Spring AI 2.0 Reference — Tool Calling và Tool Call Limits](https://docs.spring.io/spring-ai/reference/2.0/api/tools.html)
- [Spring AI 2.0.1 API — DefaultToolCallingManager.Builder](https://docs.spring.io/spring-ai/docs/2.0.1/api/org/springframework/ai/model/tool/DefaultToolCallingManager.Builder.html)
- [Spring AI 2.0.1 API — ToolCallLimitBehavior](https://docs.spring.io/spring-ai/docs/2.0.1/api/org/springframework/ai/model/tool/ToolCallLimitBehavior.html)
- [Spring AI 2.0.1 API — ToolCallLimitExceededException](https://docs.spring.io/spring-ai/docs/2.0.1/api/org/springframework/ai/model/tool/ToolCallLimitExceededException.html)
- [Spring AI Upgrade Notes — Tool Call Limits](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)
- [Spring AI 1.0 Reference — User-Controlled Tool Execution](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html)
