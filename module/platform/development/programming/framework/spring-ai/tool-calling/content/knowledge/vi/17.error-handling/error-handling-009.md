# Tránh lặp vô hạn việc sửa đối số và tránh tiết lộ bí mật trong lỗi

Khi tool từ chối arguments, ứng dụng có thể gửi lỗi đã chuẩn hóa trở lại mô hình để mô hình sửa và gọi lại. Cơ chế này hữu ích khi một trường sai định dạng hoặc thiếu giá trị có thể suy ra từ hội thoại. Nhưng nếu mọi lỗi đều được trả về bằng nguyên văn exception, mô hình có thể lặp lại cùng một tool call, thử nhiều biến thể không hợp lệ hoặc nhận được thông tin nội bộ như SQL, hostname, token và chi tiết xác thực.

Có hai việc phải làm cùng lúc: **giới hạn số lần mô hình được sửa arguments** và **kiểm soát chính xác nội dung lỗi được gửi về mô hình**. Spring AI cung cấp `ToolExecutionExceptionProcessor` để chọn lỗi nào được chuyển thành tool response và lỗi nào phải ném về ứng dụng. Các giới hạn tool call của `DefaultToolCallingManager` hoặc vòng lặp do ứng dụng quản lý giúp dừng chuỗi gọi lặp.

## 1. Vì sao vòng sửa arguments có thể không dừng?

Giả sử mô hình gọi `lookup_order` với `orderId` sai định dạng. Tool ném `IllegalArgumentException`, framework chuyển lỗi thành tool response, rồi mô hình nhận thông tin lỗi và thử lại. Nếu lần tiếp theo vẫn sai, chu trình có thể lặp:

1. Mô hình gửi arguments không hợp lệ.
2. Tool validation từ chối.
3. Exception processor gửi lỗi lại mô hình.
4. Mô hình tạo arguments mới nhưng vẫn sai.
5. Tool chạy lại và tiếp tục từ bước 2.

Ngay cả khi mỗi lần gọi đều kết thúc, vòng hội thoại vẫn tiêu tốn token, thời gian, quota và tài nguyên của service. Với tool có side effect, việc gọi lặp còn có thể tạo thao tác trùng nếu ứng dụng không có idempotency.

Không phải mọi lỗi đều có thể sửa bằng cách đổi arguments. Nếu người gọi không có quyền, dịch vụ nguồn đang lỗi hoặc dữ liệu không tồn tại, yêu cầu mô hình “thử lại” không giải quyết được nguyên nhân.

## 2. Phân biệt các loại retry

Không gộp mọi lần thử lại thành một bộ đếm chung. Mỗi loại retry có chủ thể và cách dừng khác nhau:

| Loại | Ai thực hiện? | Ví dụ | Cách giới hạn |
| --- | --- | --- | --- |
| Model correction | Mô hình tạo tool call mới sau khi nhận validation feedback | Sửa `orderId` hoặc định dạng ngày | Số lần sửa cho mỗi tool và tổng tool call trong một turn |
| Tool loop | `ToolCallingAdvisor` hoặc vòng lặp ứng dụng gọi mô hình và tool nhiều lượt | Mô hình liên tiếp gọi search rồi lookup | Số vòng, số tool call, deadline và ngân sách token |
| Infrastructure retry | Ứng dụng/service gọi lại dependency | HTTP 503, timeout tạm thời | Backoff, jitter, timeout và idempotency |
| LLM request retry | Client gọi lại provider khi request chat lỗi tạm thời | Mất kết nối hoặc rate limit provider | Retry policy của HTTP client, deadline và quota |

Model correction chỉ nên áp dụng cho lỗi đầu vào có thể khắc phục. Infrastructure retry phải do ứng dụng quản lý vì ứng dụng biết thao tác có idempotent hay không và biết khi nào dependency hồi phục. Không yêu cầu mô hình lặp tool call để thay thế retry policy của HTTP client hoặc service.

## 3. Phân loại lỗi trước khi quyết định phản hồi

Trước khi gửi lỗi cho mô hình, xác định lỗi có thể sửa từ arguments hay cần caller/application xử lý:

| Loại lỗi | Ví dụ | Có nên gửi feedback để mô hình sửa? |
| --- | --- | --- |
| Input validation | `orderId` sai format, `pageSize` vượt miền cho phép | Có, nếu nêu được trường sai và quy tắc hợp lệ |
| Thiếu thông tin người dùng | Không có ngày giao hàng hoặc mã khách hàng | Không yêu cầu mô hình tự bịa; cần hỏi người dùng |
| Business rejection | Đơn hàng đã đóng, không thể hủy | Thường không; trả kết quả nghiệp vụ hoặc yêu cầu hành động khác |
| Not found | Không có đơn hàng phù hợp | Trả `NOT_FOUND` nếu caller được phép biết; không lặp cùng truy vấn |
| Authentication/authorization | Session hết hạn, caller không có quyền | Ném về caller hoặc trả lỗi chung; không để mô hình dò quyền |
| Dependency transient | Timeout, 429, 503 | Retry ở service với giới hạn; không yêu cầu mô hình gọi lặp |
| Internal failure | Null bất ngờ, lỗi serialize, lỗi cấu hình | Ném về caller; mô hình chỉ nên nhận thông báo chung nếu workflow cho phép |

Một lỗi input chỉ được xem là có thể sửa khi schema và ngữ cảnh cung cấp đủ thông tin để sửa. Nếu thiếu dữ liệu mà chỉ người dùng mới biết, phản hồi nên yêu cầu bổ sung dữ liệu thay vì khuyến khích mô hình đoán.

## 4. Spring AI xử lý lỗi tool như thế nào?

Khi callback thực thi thất bại, Spring AI dùng `ToolExecutionException` để biểu diễn lỗi. `ToolExecutionExceptionProcessor` quyết định một trong hai hướng:

- Trả về một chuỗi lỗi đã chuẩn hóa để framework đưa vào tool response cho mô hình.
- Ném exception lên caller để ứng dụng xử lý.

Với Spring Boot starter, `DefaultToolExecutionExceptionProcessor` thường được tự cấu hình. Hành vi mặc định rất quan trọng: message của `RuntimeException` được gửi về mô hình; checked exception và `Error` được ném lên caller. Vì vậy, một `IllegalArgumentException` có message chứa câu SQL, URL nội bộ hoặc giá trị bí mật có thể bị đưa thẳng vào hội thoại.

Có thể cấu hình mặc định ném lỗi về caller:

```yaml
spring:
  ai:
    tools:
      throw-exception-on-error: true
```

Khi bật thuộc tính này, lỗi tool được ném cho ứng dụng xử lý thay vì chuyển thành message để mô hình tự sửa. Cách này phù hợp khi muốn fail fast hoặc khi không có loại lỗi nào an toàn để gửi lại mô hình. Nếu cần cho phép sửa một số lỗi input, dùng custom `ToolExecutionExceptionProcessor` để chỉ mở một tập lỗi có thể khắc phục và ném tất cả lỗi còn lại.

## 5. Thiết kế lỗi đầu vào an toàn và có cấu trúc

Không dùng message exception làm hợp đồng giữa tool và mô hình. Hãy tạo một cấu trúc lỗi nhỏ, chỉ chứa mã ổn định, lời hướng dẫn ngắn và tên trường cần sửa:

```java
import java.util.List;

public record ToolInputError(
        String status,
        String code,
        String message,
        List<String> fields,
        boolean correctionAllowed) {
}
```

Ví dụ phản hồi có thể sửa:

```json
{
  "status": "ERROR",
  "code": "INVALID_ORDER_ID",
  "message": "orderId phải có dạng ORD- theo sau bởi 6 chữ số.",
  "fields": ["orderId"],
  "correctionAllowed": true
}
```

Phản hồi chỉ nêu trường và quy tắc, không echo giá trị mô hình đã gửi. Không đưa raw arguments, stack trace, exception class, SQL hoặc nội dung header vào response. `correctionAllowed` là gợi ý cho mô hình; bộ đếm ở ứng dụng mới là cơ chế thực sự dừng retry.

Đối với lỗi không được phép sửa, không trả `correctionAllowed=true`. Với lỗi quyền hoặc lỗi nội bộ, thông thường không gửi chi tiết lỗi cho mô hình mà ném về caller.

## 6. Chỉ lưu thông tin an toàn trong exception

Đừng tạo exception bằng cách nối raw input hoặc thông tin hạ tầng vào message:

```java
// Không an toàn: message có thể bị gửi lại mô hình hoặc ghi vào log.
throw new IllegalArgumentException(
        "Invalid orderId=" + orderId + " for database " + jdbcUrl);

// Tốt hơn: exception chỉ mang code và tên field đã được kiểm soát.
throw new CorrectableToolInputException(
        "INVALID_ORDER_ID", List.of("orderId"));
```

Khai báo exception riêng:

```java
import java.util.List;

public final class CorrectableToolInputException extends RuntimeException {

    private final String code;
    private final List<String> fields;

    public CorrectableToolInputException(String code, List<String> fields) {
        super(code); // Không chứa raw arguments hoặc secret.
        this.code = code;
        this.fields = List.copyOf(fields);
    }

    public String code() {
        return code;
    }

    public List<String> fields() {
        return fields;
    }
}
```

Ví dụ dùng exception trong một tool method:

```java
import java.util.List;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
@Tool(description = "Tra cứu trạng thái đơn hàng theo mã đơn.")
public OrderStatus lookupOrder(
        @ToolParam(description = "Mã đơn dạng ORD- theo sau bởi 6 chữ số") String orderId) {

    if (orderId == null || !ORDER_ID_PATTERN.matcher(orderId).matches()) {
        throw new CorrectableToolInputException(
                "INVALID_ORDER_ID", List.of("orderId"));
    }

    return orderService.findStatus(orderId)
            .orElseThrow(() -> new OrderNotFoundException("ORDER_NOT_FOUND"));
}
```

`ORDER_ID_PATTERN`, `OrderStatus`, `orderService` và `OrderNotFoundException` là kiểu/thành phần của ứng dụng. Ví dụ tập trung vào việc chỉ ném exception correction với code và tên field đã kiểm soát; không nối giá trị `orderId` vào message.

`OrderNotFoundException` là lỗi nghiệp vụ riêng; tùy chính sách riêng tư, tool có thể trả kết quả `NOT_FOUND` hoặc để caller xử lý. Không biến nó thành lỗi định dạng để mô hình thử đổi mã đơn ngẫu nhiên.

Không chỉ message mới có thể rò rỉ dữ liệu. Cause chain, `getLocalizedMessage()`, `toString()`, SQL exception, HTTP client exception và stack trace cũng có thể chứa thông tin nhạy cảm. Không serialize hoặc đưa nguyên exception vào tool result.

## 7. Custom ToolExecutionExceptionProcessor

Processor nên dùng allowlist: chỉ `CorrectableToolInputException` được chuyển thành feedback có cấu trúc; mọi lỗi khác được ném về caller. Không đọc `exception.getMessage()` hoặc `cause.getMessage()` để tạo phản hồi.

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.ai.tool.execution.ToolExecutionException;
import org.springframework.ai.tool.execution.ToolExecutionExceptionProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ToolErrorConfiguration {

    @Bean
    ToolExecutionExceptionProcessor safeToolErrorProcessor(
            ObjectMapper objectMapper) {

        return exception -> {
            Throwable cause = exception.getCause();

            if (cause instanceof CorrectableToolInputException invalidInput) {
                ToolInputError safeError = new ToolInputError(
                        "ERROR",
                        invalidInput.code(),
                        "Một số đối số chưa đúng định dạng. Hãy sửa các trường được liệt kê.",
                        invalidInput.fields(),
                        true);

                try {
                    return objectMapper.writeValueAsString(safeError);
                }
                catch (JsonProcessingException serializationFailure) {
                    // Không chuyển lỗi serialize hoặc cause nội bộ cho mô hình.
                    throw exception;
                }
            }

            // Auth, authorization, dependency và lỗi nội bộ được caller xử lý.
            throw exception;
        };
    }
}
```

Ví dụ dùng `ToolExecutionException.getCause()` để phân loại lỗi. Nếu tool tự triển khai `ToolCallback`, khi thực thi thất bại cần ném `ToolExecutionException` với `ToolDefinition` và cause tương ứng để processor nhận được đúng hợp đồng.

Không dùng một nhánh kiểu `return exception.getCause().getMessage()` cho mọi lỗi. Một exception hợp lệ ở tầng Java không có nghĩa message của nó an toàn để đưa vào hội thoại.

### Khi nào nên ném lỗi thay vì gửi feedback?

- `AccessDeniedException` hoặc lỗi authentication: ném lên caller; không tiết lộ tài nguyên có tồn tại hay không.
- OAuth2 `ClientAuthorizationException`: giữ hành vi ném lại nếu ứng dụng cần quy trình refresh/ủy quyền.
- Timeout, 429, 503 hoặc lỗi database: để service retry policy xử lý; nếu hết retry thì caller nhận lỗi chung.
- Lỗi lập trình hoặc cấu hình: ném lên caller, ghi nhận bằng error ID và xử lý ở tầng ứng dụng.
- Lỗi input có thể sửa: chỉ trả feedback an toàn và chỉ trong ngân sách correction còn lại.

## 8. Giới hạn số lần tool call trong Spring AI 2.x

Từ Spring AI 2.0.1, `DefaultToolCallingManager` hỗ trợ giới hạn số lần một tool được gọi và tổng số tool call trong một turn. Tài liệu hiện hành mô tả mặc định là 40 lần cho mỗi tool và 150 lần tổng cộng. Các mức mặc định này bảo vệ vòng lặp runaway ở mức framework, nhưng thường quá rộng nếu mục tiêu chỉ là cho mô hình sửa arguments một lần.

Có thể cấu hình mức thấp hơn khi tạo manager:

```java
import org.springframework.ai.model.tool.ToolCallLimitBehavior;
import org.springframework.ai.model.tool.ToolCallingManager;
import org.springframework.ai.tool.execution.ToolExecutionExceptionProcessor;
import org.springframework.context.annotation.Bean;

@Bean
ToolCallingManager toolCallingManager(
        ToolExecutionExceptionProcessor safeToolErrorProcessor) {

    return ToolCallingManager.builder()
            .maxCallsPerTool(2)
            .maxCallsPerTool("submit_payment", 1)
            .maxTotalToolCalls(6)
            .onLimitExceeded(ToolCallLimitBehavior.THROW)
            .toolExecutionExceptionProcessor(safeToolErrorProcessor)
            .build();
}
```

Ví dụ cho phép `lookup_order` được gọi tối đa hai lần trong một turn: một lần đầu và một lần sửa. `submit_payment` chỉ được gọi một lần vì đó là thao tác có side effect. Tổng các tool call trong turn không vượt quá sáu.

Giới hạn được tính theo tool call trong turn, không chỉ các lần validation thất bại. Vì vậy, hãy điều chỉnh theo nghiệp vụ: một tool search có thể cần nhiều lần gọi hợp lệ, trong khi tool chuyển tiền hoặc xóa dữ liệu nên có giới hạn thấp hơn và approval riêng.

`ToolCallLimitBehavior.THROW` ném `ToolCallLimitExceededException` khi vượt giới hạn để ứng dụng dừng luồng. `RETURN_ERROR_RESPONSE` bỏ qua lần gọi vượt giới hạn và gửi một tool response báo giới hạn cho mô hình; mô hình có thể tiếp tục, nên lựa chọn này không phải hard stop nếu không có giới hạn bổ sung.

Có thể cấu hình bằng properties:

```yaml
spring:
  ai:
    tools:
      limits:
        max-calls-per-tool-default: 2
        max-calls-per-tool:
          lookup_order: 2
          submit_payment: 1
        max-total-tool-calls: 6
        on-limit-exceeded: THROW
```

Nếu dùng custom `ToolExecutionExceptionProcessor`, bean custom sẽ quyết định cách phân loại lỗi. Thuộc tính `spring.ai.tools.throw-exception-on-error` mô tả hành vi của processor mặc định; không nên giả định nó tự thay đổi logic của processor do ứng dụng cung cấp.

## 9. Spring AI 1.0.x: tự giới hạn vòng lặp

Trong Spring AI 1.0.x, tool execution loop nằm bên trong `ChatModel` theo mặc định. Để ứng dụng tự giới hạn số vòng và số lần gọi, đặt `internalToolExecutionEnabled(false)` rồi dùng `ToolCallingManager` trong vòng lặp do ứng dụng kiểm soát.

| Dòng phiên bản | Cơ chế |
| --- | --- |
| Spring AI 1.0.x | `internalToolExecutionEnabled(false)` và bộ đếm do ứng dụng quản lý |
| Spring AI 2.0.1+ | `DefaultToolCallingManager` có `maxCallsPerTool`, `maxTotalToolCalls` và `ToolCallLimitBehavior` |
| Spring AI 2.x `ChatClient` | `ToolCallingAdvisor` điều phối loop; cấu hình `ToolCallingManager` để áp dụng giới hạn |

Không giả định builder `maxCallsPerTool(...)` và `maxTotalToolCalls(...)` của 2.0.1+ tồn tại trong 1.0.x. Kiểm tra dependency đang dùng trước khi sao chép cấu hình.

```java
import java.util.HashMap;
import java.util.Map;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.model.tool.ToolCallingChatOptions;
import org.springframework.ai.model.tool.ToolCallingManager;
import org.springframework.ai.model.tool.ToolExecutionResult;

private static final int MAX_ROUNDS = 4;
private static final int MAX_CALLS_PER_TOOL = 2;

String runWithBoundedToolLoop(
        ChatModel chatModel,
        ToolCallingManager manager,
        Prompt initialPrompt,
        ToolCallingChatOptions options) {

    Prompt prompt = initialPrompt;
    Map<String, Integer> callsByTool = new HashMap<>();

    for (int round = 0; round < MAX_ROUNDS; round++) {
        ChatResponse response = chatModel.call(prompt);
        if (!response.hasToolCalls()) {
            return response.getResult().getOutput().getText();
        }

        for (var toolCall : response.getResult().getOutput().getToolCalls()) {
            int count = callsByTool.merge(toolCall.name(), 1, Integer::sum);
            if (count > MAX_CALLS_PER_TOOL) {
                throw new ToolLoopLimitException(toolCall.name());
            }
        }

        ToolExecutionResult result = manager.executeToolCalls(prompt, response);
        if (result.returnDirect()) {
            return directResultMapper.toResponse(result);
        }

        prompt = new Prompt(result.conversationHistory(), options);
    }

    throw new ToolLoopLimitException("MAX_ROUNDS");
}
```

Ví dụ minh họa bộ đếm ở cấp một request. `ToolLoopLimitException` và `directResultMapper` là thành phần do ứng dụng định nghĩa. Trong phần khởi tạo `options`, phải đăng ký callbacks và tắt vòng nội bộ:

```java
ToolCallingChatOptions options = ToolCallingChatOptions.builder()
        .toolCallbacks(callbacks)
        .internalToolExecutionEnabled(false)
        .build();
```

Bộ đếm là biến cục bộ trong một lần điều phối, vì vậy không trộn số lần gọi giữa các request đồng thời. Nếu ứng dụng dùng một vòng lặp thủ công trong Spring AI 2.x, cũng cần giới hạn số round và tool call; khi dùng `ChatClient`, có thể tắt auto `ToolCallingAdvisor` cho request và tự quản lý từng vòng.

## 10. Đừng để mô hình tự retry lỗi hạ tầng

Khi service phía sau bị timeout, ứng dụng có thể retry bằng chính sách có giới hạn. Ví dụ, với một GET idempotent, có thể retry tối đa hai lần với exponential backoff và jitter. Với thao tác tạo đơn hoặc thanh toán, chỉ retry nếu có idempotency key và service đảm bảo cùng key không tạo side effect lặp.

Không gửi lỗi chi tiết như `Connection refused to db-prod-03:5432` cho mô hình rồi yêu cầu gọi tool lại. Mô hình không thể sửa database hoặc khôi phục mạng. Nếu retry hết hạn, ném lỗi về caller và trả một thông báo chung ở tầng API.

Phân biệt rõ:

- Retry nội bộ service: cùng một yêu cầu nghiệp vụ, có giới hạn và chính sách idempotency.
- Model correction: arguments mới do mô hình sinh sau khi nhận validation feedback.
- Retry LLM request: gọi lại provider khi transport lỗi, không phải gọi lại tool.

Các bộ đếm phải độc lập và cùng chịu deadline tổng của request. Nếu retry từng lớp mà không có ngân sách tổng, số lần gọi thực tế có thể nhân lên rất nhanh.

## 11. Phát hiện việc lặp lại cùng arguments

Giới hạn số lần gọi theo tool là biện pháp nền tảng. Với workflow có nguy cơ mô hình lặp đúng cùng một payload lỗi, có thể bổ sung phát hiện fingerprint:

1. Chuẩn hóa JSON arguments theo thứ tự key ổn định.
2. Tạo fingerprint bằng HMAC-SHA-256 với khóa ứng dụng, trên `toolName + canonicalArguments`.
3. Chỉ so sánh fingerprint sau khi lần gọi trước bị đánh dấu là lỗi validation có thể sửa.
4. Nếu cùng fingerprint xuất hiện lại, dừng correction và yêu cầu người dùng bổ sung thông tin.

Không lưu raw arguments để so sánh và không ghi fingerprint ra log nếu không cần thiết. HMAC giúp tránh việc một hash công khai của giá trị có entropy thấp bị dò ngược. Fingerprint chỉ là lớp bảo vệ bổ sung; vẫn cần max calls, max rounds và deadline.

Không chặn mọi lần gọi lặp cùng tool name và arguments một cách mù quáng. Có tool đọc dữ liệu hợp lệ cần được gọi lại để xác nhận trạng thái. Chỉ đánh dấu một fingerprint là “lặp sai” khi lần trước đã trả về cùng loại validation error.

## 12. Không tiết lộ bí mật trong lỗi và log

Các dữ liệu sau không được đưa vào tool response hoặc thông điệp lỗi gửi cho mô hình:

- Password, API key, access token, refresh token, cookie và Authorization header.
- Connection string, hostname nội bộ, IP, tên database/schema và đường dẫn file nội bộ.
- SQL statement, stack trace, class/package nội bộ và cấu hình hệ thống.
- Raw arguments nếu chúng chứa PII, credential hoặc dữ liệu khách hàng.
- Nội dung phản hồi nguyên bản từ dịch vụ bên thứ ba nếu có thể chứa bí mật.

Phản hồi cho mô hình nên dùng mã ổn định và thông điệp đủ để quyết định bước tiếp theo. Ví dụ: `INVALID_ARGUMENTS`, `RESOURCE_NOT_AVAILABLE`, `OPERATION_NOT_ALLOWED`, `TEMPORARILY_UNAVAILABLE`.

Đối với authorization, không xác nhận tài nguyên có tồn tại nếu caller không có quyền xem nó. Thông điệp chung như “Không thể truy cập tài nguyên được yêu cầu” an toàn hơn việc tiết lộ “đơn hàng tồn tại nhưng thuộc tenant khác”.

Log nội bộ có thể cần thêm thông tin chẩn đoán, nhưng phải có chính sách riêng: che token/PII, giới hạn quyền truy cập, retention phù hợp và correlation ID. Tránh ghi toàn bộ arguments hoặc `exception.getMessage()` một cách tự động. Nếu cần stack trace để debug, bảo đảm exception message đã được làm sạch và log sink được bảo vệ.

## 13. Bảo vệ cả tool result, không chỉ exception

Ngay cả khi exception processor an toàn, tool result thành công vẫn có thể vô tình chứa secret. Kiểm soát output ở DTO/projection trước khi converter serialize:

- Trả đúng các trường mô hình cần, không trả entity hoặc object cấu hình.
- Không trả credential hoặc raw response header.
- Rút gọn payload và loại bỏ PII không liên quan.
- Không đưa nội dung exception vào trường `message` của DTO thành công.
- Kiểm tra dữ liệu từ hệ thống ngoài trước khi đưa lại mô hình.

Tool result thường được gửi lại mô hình để tiếp tục hội thoại. Vì vậy, ranh giới bảo mật áp dụng cho cả kết quả thành công, error response và metadata.

## 14. Kiểm thử bounded correction và redaction

Kiểm thử cần chứng minh cả việc dừng vòng lặp lẫn việc không lộ secret:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Arguments sai lần đầu | Nhận feedback có code và field name an toàn |
| Mô hình sửa đúng ở lần kế tiếp | Tool được thực thi thành công trong ngân sách |
| Cùng arguments sai lặp lại | Vượt giới hạn và vòng lặp dừng |
| Gọi một tool quá số lần | `ToolCallLimitExceededException` hoặc lỗi giới hạn của ứng dụng |
| Tổng tool call vượt ngưỡng | Không thực thi thêm callback |
| Exception chứa secret sentinel | Sentinel không xuất hiện trong tool response |
| Access denied | Lỗi được ném về caller hoặc thông báo chung; không tiết lộ resource |
| Timeout/503 | Retry ở service có giới hạn, không tạo vòng model retry |
| Tool ghi dữ liệu retry | Idempotency ngăn side effect trùng |
| Hai request đồng thời | Bộ đếm correction không dùng chung giữa request |

Ví dụ kiểm thử processor không echo secret:

```java
@Test
void shouldReturnSafeValidationFeedbackWithoutRawValue() throws Exception {
    String secret = "api-key-SHOULD-NEVER-LEAK";
    CorrectableToolInputException cause =
            new CorrectableToolInputException(
                    "INVALID_ORDER_ID", List.of("orderId"));

    ToolExecutionException exception =
            new ToolExecutionException(toolDefinition, cause);

    String response = safeToolErrorProcessor.process(exception);

    assertThat(response).contains("INVALID_ORDER_ID");
    assertThat(response).contains("orderId");
    assertThat(response).doesNotContain(secret);
    assertThat(response).doesNotContain(cause.getMessage());
}
```

Bổ sung test vòng lặp bằng model giả: trả cùng một tool call lỗi nhiều lần, xác minh số lần gọi callback không vượt giới hạn và kết quả cuối là lỗi giới hạn thay vì tiếp tục gọi model. Với custom callback, kiểm tra nó luôn ném `ToolExecutionException` khi thực thi thất bại.

Một assertion quan trọng của test lặp là xác minh callback không được gọi lần thứ ba sau khi đã dùng hết ngân sách hai lần. Đồng thời kiểm tra model-facing response không chứa raw input, exception message hoặc secret sentinel.

## 15. Quan sát mà không ghi lộ dữ liệu

Spring AI có Micrometer observation cho tool call với tên `spring.ai.tool`, ghi nhận tên tool, thời lượng và tracing context. Việc đưa arguments/results vào span attributes là tùy chọn và mặc định tắt trong tài liệu hiện hành vì lý do nhạy cảm.

Theo dõi các metric không chứa nội dung bí mật:

- Số validation failure theo tool và error code.
- Số correction attempt trung bình và tỷ lệ vượt giới hạn.
- Số tool call trên mỗi turn.
- Số lần exception processor ném lỗi về caller.
- Tỷ lệ timeout, 429, 5xx và retry nội bộ.
- Tổng thời gian tool execution và thời gian toàn request.

Gắn `requestId` hoặc trace ID để điều tra, nhưng không dùng raw arguments làm label metric vì cardinality cao và có thể chứa dữ liệu nhạy cảm.

## 16. Checklist triển khai

- [ ] Phân loại validation, business, authorization, transient và internal error.
- [ ] Chỉ cho phép model correction với lỗi input thực sự có thể sửa.
- [ ] Feedback có code ổn định, field name và quy tắc; không echo raw arguments.
- [ ] Custom `ToolExecutionExceptionProcessor` dùng allowlist lỗi có thể gửi về model.
- [ ] Không gửi `exception.getMessage()`, cause message hoặc stack trace cho mô hình.
- [ ] Đặt max calls per tool, max total calls, max rounds và deadline.
- [ ] Dùng `THROW` khi cần dừng cứng sau khi vượt tool call limit.
- [ ] Với Spring AI 1.0.x, tắt internal execution và tự đếm vòng/tool call nếu cần hard limit.
- [ ] Retry lỗi hạ tầng ở service với backoff, jitter và idempotency.
- [ ] Giữ auth/authorization và lỗi nội bộ ở caller boundary.
- [ ] Không lưu counter theo request trong singleton mutable state.
- [ ] Che secret/PII trong log và tracing; giữ arguments/results khỏi span mặc định.
- [ ] Kiểm thử lặp cùng arguments, vượt limit, secret sentinel và side effect retry.

## Tài liệu tham khảo

- [Spring AI 1.0 — Tool Calling: Exception Handling và User-Controlled Execution](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html)
- [Spring AI — Tool Calling: Exception Handling và Tool Call Limits](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [ToolExecutionException API — Spring AI](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/execution/ToolExecutionException.html)
- [ToolExecutionExceptionProcessor API — Spring AI](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/execution/ToolExecutionExceptionProcessor.html)
- [ToolCallLimitBehavior API — Spring AI](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/model/tool/ToolCallLimitBehavior.html)
- [DefaultToolCallingManager.Builder API — Spring AI](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/model/tool/DefaultToolCallingManager.Builder.html)

Vòng sửa arguments chỉ hữu ích khi lỗi có thể khắc phục và phản hồi chỉ tiết lộ thông tin cần thiết. Hãy cho mô hình một cơ hội sửa có giới hạn, dừng khi lặp lại hoặc vượt ngân sách, và để ứng dụng xử lý lỗi quyền, lỗi hạ tầng cùng retry của nghiệp vụ. Một exception an toàn không phải exception đã được che ở giao diện; nó phải được thiết kế an toàn từ lúc tạo, qua processor, tool response, log và tracing.
