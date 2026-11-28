# Giới hạn công cụ được thực thi trong từng yêu cầu

Một ứng dụng Spring AI có thể đăng ký hàng chục công cụ dưới dạng bean, `ToolCallback` hoặc công cụ đến từ MCP. Tuy nhiên, mỗi yêu cầu của người dùng chỉ nên được thực thi một tập công cụ phù hợp với tác vụ và quyền đã xác thực. Nếu mọi công cụ đều được cung cấp mặc định, mô hình có thể nhìn thấy những khả năng không liên quan; nếu cơ chế phân giải theo tên được mở rộng quá rộng, một tool call không nằm trong danh sách của request vẫn có thể tìm được callback và chạy.

Spring AI cung cấp nhiều lớp để kiểm soát phạm vi đó: chọn callback theo từng request, cấu hình `ToolCallbackResolver`, bật hoặc tắt resolution fallback, giới hạn số lần gọi trong một lượt và tự điều phối vòng gọi công cụ khi cần chính sách phức tạp. Các lớp này giải quyết những vấn đề khác nhau. Danh sách công cụ quyết định callback nào có thể được chọn; giới hạn số lần gọi ngăn vòng lặp chạy quá lâu; còn authorization trong ứng dụng quyết định người dùng có được phép thao tác trên tài nguyên cụ thể hay không.

Bài này tập trung vào Spring AI 2.1.0. Hãy đối chiếu lại tài liệu của release line đang dùng vì hành vi đăng ký và phân giải công cụ đã thay đổi so với Spring AI 1.x.

## Phân biệt khả năng nhìn thấy và khả năng thực thi

Có ba câu hỏi cần trả lời riêng:

1. **Mô hình nhìn thấy công cụ nào?** Đây là tập định nghĩa `ToolDefinition` được gửi cùng request.
2. **Spring AI có thể phân giải và thực thi callback nào?** Đây là tập callback mà `ToolCallingManager` được phép tìm khi nhận một tool call.
3. **Người dùng hiện tại có quyền thực hiện hành động nào?** Đây là quyết định của ứng dụng và service nghiệp vụ tại thời điểm thực thi.

Ba tập này thường liên quan nhưng không đồng nhất. Ví dụ, một callback bean có thể tồn tại trong application context nhưng không được gắn vào request. Khi resolution fallback tắt, model không thể thực thi callback đó chỉ bằng cách đoán tên. Khi fallback bật, callback có thể được tìm theo tên dù request không đính kèm nó. Dù callback đã được đính kèm, service vẫn phải kiểm tra người dùng có quyền truy cập dữ liệu hay không.

| Lớp kiểm soát | Câu hỏi được giải quyết | Cơ chế Spring AI hoặc ứng dụng |
|---|---|---|
| Danh sách theo request | Request này được phép dùng những công cụ nào? | `ChatClient.prompt().tools(...)`, `ToolCallingChatOptions.toolCallbacks(...)` hoặc bộ lọc callback của ứng dụng. |
| Phân giải theo tên | Khi model yêu cầu tên tool, callback được tìm ở đâu? | `ToolCallbackResolver` và resolution fallback. |
| Giới hạn số lần gọi | Một công cụ hoặc cả lượt được gọi tối đa bao nhiêu lần? | `ToolCallingManager` tool call limits. |
| Xác thực và phân quyền | Người dùng có được đọc hoặc thay đổi tài nguyên này không? | Security context, `ToolContext`, authorization service và kiểm tra trong service nghiệp vụ. |
| Giới hạn vận hành | Request tiêu thụ tối đa bao nhiêu thời gian, token hoặc tài nguyên? | Timeout, rate limit, concurrency limit và ngân sách do ứng dụng quản lý. |

Không dùng một lớp thay cho lớp khác. Ví dụ, giới hạn tổng số tool call không ngăn người dùng gọi một công cụ mà họ không có quyền; còn không gửi một công cụ cho mô hình cũng không thay thế kiểm tra quyền ở service.

## Chọn callback theo từng request bằng ChatClient

Với `ChatClient`, `.defaultTools(...)` cung cấp công cụ cho mọi request được tạo từ client. `.tools(...)` bổ sung công cụ cho request hiện tại. Trong Spring AI 2.1.0, `.tools(...)` không loại bỏ danh sách mặc định.

Nếu cần một allowlist thực sự khác nhau theo từng người dùng hoặc tác vụ, cách đơn giản nhất là tạo client không có danh sách mặc định rộng và chỉ đính kèm callback đã được ứng dụng chọn cho request.

```java
@Service
class SupportChatService {

    private final ChatClient chatClient;
    private final ToolPolicy toolPolicy;

    SupportChatService(ChatModel chatModel, ToolPolicy toolPolicy) {
        this.chatClient = ChatClient.builder(chatModel).build();
        this.toolPolicy = toolPolicy;
    }

    String answer(
            AuthenticatedUser user,
            String question,
            SupportIntent intent) {

        List<ToolCallback> allowedTools = toolPolicy.allowedToolsFor(user, intent);

        if (allowedTools.isEmpty()) {
            return chatClient.prompt()
                    .user(question)
                    .call()
                    .content();
        }

        Map<String, Object> context = Map.of(
                "userId", user.id(),
                "tenantId", user.tenantId()
        );

        return chatClient.prompt()
                .user(question)
                .tools(allowedTools)
                .toolContext(context)
                .call()
                .content();
    }
}
```

`ToolPolicy` là thành phần do ứng dụng xây dựng. Nó xác định tác vụ và quyền từ danh tính đã xác thực, sau đó trả về các callback tương ứng. Không lấy tên công cụ trực tiếp từ nội dung người dùng rồi đăng ký tùy ý.

Ví dụ trên cố ý không gọi `defaultTools(...)`. Nếu client đã có default tools, `.tools(allowedTools)` sẽ nối thêm vào danh sách đó và các công cụ mặc định vẫn xuất hiện trong request. Với một allowlist nghiêm ngặt, hãy tránh đăng ký những công cụ cần lọc làm mặc định; có thể tạo client riêng theo nhóm quyền hoặc quản lý toàn bộ danh sách ở cấp request.

Nếu allowlist rỗng, dùng một đường chat không có tool calling. Đừng dựa vào một danh sách mặc định chứa công cụ nhạy cảm rồi hy vọng request rỗng sẽ loại bỏ chúng.

Hãy kiểm tra cả cấu hình của `ChatModel` bên dưới. Nếu model có `ToolCallingChatOptions.toolCallbacks(...)` mặc định, request-level tools của `ChatClient` sẽ ghi đè callback list đó khi request cung cấp danh sách. Với nhánh không có tool, dùng một model/client không có tool callbacks mặc định hoặc cấu hình rõ ràng một danh sách rỗng theo API của release line đang dùng; đừng để một model dùng chung âm thầm mang theo công cụ từ cấu hình khác.

### Chọn công cụ theo vai trò và tác vụ

Ví dụ một ứng dụng hỗ trợ khách hàng có thể phân chia như sau:

| Người dùng hoặc tác vụ | Công cụ có thể cung cấp | Ví dụ công cụ không nên cung cấp mặc định |
|---|---|---|
| Khách hàng xem đơn của mình | `getMyOrderStatus`, `getShipmentTracking` | `refundOrder`, `changeAccountOwner` |
| Nhân viên hỗ trợ tra cứu | `searchCustomer`, `getOrderDetails`, `getShipmentTracking` | `deleteCustomer`, `issueRefund` nếu chưa có phê duyệt |
| Nhân viên xử lý hoàn tiền đã được cấp quyền | `getOrderDetails`, `calculateRefund`, `requestRefundApproval` | Công cụ quản trị tenant hoặc xóa dữ liệu không liên quan |
| Tác vụ báo cáo | `aggregateOrderMetrics`, `exportApprovedReport` | Công cụ cập nhật đơn hoặc hồ sơ khách hàng |

Đây chỉ là ví dụ về cách phân loại. Quyền thực tế phải được lấy từ hệ thống identity và policy của ứng dụng, không được suy ra từ câu người dùng tự khai như “tôi là quản trị viên”.

## Chọn callback cho ChatModel trực tiếp

Khi gọi `ChatModel` trực tiếp, truyền danh sách callback trong `ToolCallingChatOptions.toolCallbacks(...)`. Trong Spring AI 2.x, danh sách ở runtime thay thế danh sách tool trong default options của model. Nếu muốn dùng một tập hợp chính xác cho request, hãy tạo danh sách đó trước khi tạo `Prompt`.

```java
List<ToolCallback> allowedTools = toolPolicy.allowedToolsFor(user, intent);

ToolCallingChatOptions options = ToolCallingChatOptions.builder()
        .toolCallbacks(allowedTools)
        .toolContext(Map.of(
                "userId", user.id(),
                "tenantId", user.tenantId()
        ))
        .build();

Prompt prompt = new Prompt(question, options);
ChatResponse response = chatModel.call(prompt);
```

`ChatModel.call(...)` chỉ gửi định nghĩa công cụ và trả response chứa tool call nếu mô hình yêu cầu. Nó không tự thực thi callback hoặc lặp lại hội thoại. Ứng dụng phải dùng `ToolCallingManager` để thực thi và điều phối các lượt tiếp theo. Khi tự điều phối, hãy bảo đảm mỗi vòng lặp vẫn dùng đúng allowlist và giới hạn số lần gọi.

## ToolCallbackResolver và resolution fallback

`ToolCallbackResolver` phân giải tên công cụ thành callback:

```java
public interface ToolCallbackResolver {
    @Nullable
    ToolCallback resolve(String toolName);
}
```

Trong cấu hình mặc định của Spring AI 2.1.0, `StaticToolCallbackResolver` được tạo từ các bean `ToolCallback` trong application context và các công cụ do `ToolCallbackProvider` cung cấp (MCP provider có quy tắc đăng ký riêng để tránh liệt kê eager). Resolver hỗ trợ tìm callback theo tên trong quá trình thực thi.

Việc callback tồn tại trong resolver không có nghĩa nó tự động được gửi cho mô hình trong mọi request. Điểm quyết định là resolution fallback.

**Mặc định trong Spring AI 2.1.0:**

```properties
spring.ai.tools.resolution.fallback.enabled=false
```

Khi fallback tắt, chỉ callback được đính kèm vào request mới có thể được thực thi. Nếu mô hình yêu cầu một tên không thuộc tập callback của request, `ToolCallingManager` không dùng resolver toàn cục để tự tìm một công cụ khác.

Khi bật:

```properties
spring.ai.tools.resolution.fallback.enabled=true
```

một tool call không có trong danh sách request vẫn có thể được phân giải theo tên qua `ToolCallbackResolver` và thực thi. Nếu resolver mặc định nhìn thấy nhiều callback bean, phạm vi thực thi có thể rộng hơn allowlist mà ứng dụng đã gửi cho mô hình.

Với một `ToolCallingManager` tự tạo, tùy chọn tương ứng là:

```java
ToolCallingManager manager = ToolCallingManager.builder()
        .resolutionFallbackEnabled(false)
        .build();
```

Giữ fallback tắt khi mục tiêu là giới hạn công cụ theo request. Chỉ bật khi ứng dụng kiểm soát hoàn toàn danh mục callback mà resolver có thể trả về và đã có chính sách thực thi phù hợp.

### Lưu ý khi nâng cấp từ Spring AI 1.x

Không sao chép nguyên ví dụ dynamic resolution cũ sang Spring AI 2.x. Spring AI 2.0 loại bỏ cách dùng `SpringBeanToolCallbackResolver` để phân giải các bean `Function`, `Supplier`, `Consumer` hoặc `BiFunction` thuần theo `toolNames(...)`; các công cụ cần được đăng ký thành `ToolCallback` rõ ràng. Từ 2.0.1, fallback phân giải callback bean không gắn vào request cũng bị tắt mặc định. Khi nâng cấp, hãy kiểm tra lại nơi đăng ký callback và không bật fallback chỉ để làm cho ví dụ cũ tiếp tục chạy.

### Resolver không phải điểm phân quyền theo người dùng

Phương thức `resolve(String toolName)` chỉ nhận tên công cụ. Nó không nhận `Authentication`, `ToolContext`, tenant hoặc request ID. Vì vậy, một resolver singleton không thể tự biết người gọi hiện tại là ai chỉ từ chữ ký này.

Nếu cần phân giải động theo người dùng, hãy xác định quyền ở tầng request trước khi tạo danh sách callback, rồi đính kèm danh sách đã lọc. Nếu có yêu cầu đặc biệt buộc phải phân giải trong vòng thực thi, dùng một `ToolAdvisor` hoặc cơ chế điều phối có thể truy cập ngữ cảnh request và kiểm tra policy trước khi dispatch. Tránh dùng `ThreadLocal` để truyền user/tenant vào resolver toàn cục; cách đó dễ sai khi xử lý bất đồng bộ hoặc đồng thời.

Bạn có thể thay `ToolCallbackResolver` bằng bean tùy chỉnh để đọc catalog từ database, classpath hoặc nguồn từ xa. Tuy nhiên, custom resolver vẫn phải giới hạn nguồn callback và không thay thế authorization bên trong callback/service. Với allowlist theo từng request, cách dễ kiểm chứng nhất vẫn là chọn callback trước khi gọi model và giữ fallback tắt.

## Giới hạn số lần gọi trong một lượt

Allowlist kiểm soát công cụ nào có thể chạy. Một mô hình vẫn có thể yêu cầu cùng một công cụ nhiều lần hoặc tạo nhiều tool call trong một lượt. `DefaultToolCallingManager` có giới hạn số lần gọi để bảo vệ ứng dụng khỏi vòng lặp quá dài.

Trong Spring AI 2.1.0, giá trị mặc định là:

| Giới hạn | Mặc định | Ý nghĩa |
|---|---:|---|
| Số lần gọi tối đa cho một tool trong một lượt | 40 | Ngăn một tool bị gọi lặp quá nhiều lần. |
| Tổng số tool call trong một lượt | 150 | Giới hạn tổng số lần gọi của tất cả công cụ. |
| Hành vi khi vượt giới hạn | `THROW` | Ném `ToolCallLimitExceededException` theo mặc định. |

Có thể cấu hình bằng Spring Boot properties:

```properties
# Giới hạn chung cho từng tool trong một lượt
spring.ai.tools.limits.max-calls-per-tool-default=8

# Giới hạn riêng cho công cụ tìm kiếm
spring.ai.tools.limits.max-calls-per-tool.searchOrders=3

# Tổng số tool call tối đa trong một lượt
spring.ai.tools.limits.max-total-tool-calls=12

# THROW hoặc RETURN_ERROR_RESPONSE
spring.ai.tools.limits.on-limit-exceeded=RETURN_ERROR_RESPONSE
```

Tên tool trong property riêng phải khớp với tên được công bố trong `ToolDefinition`. Có thể cấu hình `spring.ai.tools.limits.excluded-tools` để miễn giới hạn theo tool name, nhưng chỉ dùng khi có lý do rõ ràng. Giá trị `-1` tắt giới hạn tương ứng; không nên dùng tùy tiện trong môi trường thật.

### Cấu hình qua ToolCallingManager

Khi tạo manager bằng code, có thể đặt các giới hạn tương tự:

```java
ToolCallingManager manager = ToolCallingManager.builder()
        .maxCallsPerTool(8)
        .maxCallsPerTool("searchOrders", 3)
        .maxTotalToolCalls(12)
        .onLimitExceeded(ToolCallLimitBehavior.RETURN_ERROR_RESPONSE)
        .build();
```

Builder cũng có các phương thức loại trừ một tool khỏi giới hạn hoặc tắt giới hạn hoàn toàn. Hãy ưu tiên giới hạn cụ thể thay vì vô hiệu hóa toàn bộ cơ chế bảo vệ.

### Phạm vi đếm là một lượt hội thoại

Giới hạn được tính từ `UserMessage` cuối cùng trong lượt hiện tại. Các `ToolResponseMessage` thuộc lượt trước được lưu trong lịch sử không làm tăng bộ đếm của lượt mới. Manager tính lại từ conversation instructions mỗi lần thực thi, không lưu bộ đếm dùng chung trong instance manager.

Điều này có nghĩa giới hạn mặc định không phải quota theo người dùng mỗi ngày, không phải rate limit theo phút và cũng không phải giới hạn chi phí toàn phiên. Nếu sản phẩm cần quota theo user, tenant, ngày hoặc tháng, hãy bổ sung bộ đếm và chính sách ở tầng ứng dụng.

### Khi vượt giới hạn

Với `THROW`, `DefaultToolCallingManager` ném `ToolCallLimitExceededException`. Khi chạy qua `ToolCallingAdvisor`, advisor bắt ngoại lệ và trả phản hồi thể hiện giới hạn đã bị vượt; các kết quả đã thực thi trước đó trong batch được giữ trong metadata partial responses.

Với `RETURN_ERROR_RESPONSE`, manager bỏ qua lần gọi vượt giới hạn và tạo một tool response báo lỗi để mô hình biết giới hạn đã đạt. Mô hình có thể tiếp tục phản hồi với thông tin hiện có. Khi gọi `ToolCallingManager.executeToolCalls(...)` trực tiếp, đây cũng là lựa chọn để biểu diễn giới hạn thành tool result.

Chọn `THROW` khi caller cần dừng luồng và xử lý lỗi ở lớp ứng dụng. Chọn `RETURN_ERROR_RESPONSE` khi muốn mô hình biết nó cần dừng yêu cầu gọi thêm và tạo câu trả lời phù hợp. Dù chọn cách nào, vẫn cần log số lần gọi và giới hạn đã chạm tới.

## Kết hợp allowlist với ToolContext và authorization

Sau khi chọn callback, truyền danh tính và tenant đã xác thực qua `ToolContext`. Context không được gửi cho mô hình như JSON arguments; nó chỉ đi đến callback lúc thực thi.

```java
Map<String, Object> toolContext = Map.of(
        "userId", authenticatedUser.id(),
        "tenantId", authenticatedUser.tenantId(),
        "requestId", requestId
);

return chatClient.prompt()
        .user(question)
        .tools(allowedTools)
        .toolContext(toolContext)
        .call()
        .content();
```

Trong callback hoặc service, hãy kiểm tra quyền trên tài nguyên cụ thể:

```java
@Tool(description = "Tra cứu trạng thái đơn hàng thuộc tài khoản hiện tại")
public OrderStatusView getMyOrderStatus(
        @ToolParam(description = "Mã đơn hàng do hệ thống cấp") String orderId,
        ToolContext toolContext) {

    String userId = requireString(toolContext, "userId");
    String tenantId = requireString(toolContext, "tenantId");

    return orderQueryService.findStatusForUserAndTenant(
            orderId,
            userId,
            tenantId
    );
}
```

Các helper và service trong ví dụ thuộc ứng dụng. `ToolContext` chỉ cung cấp dữ liệu để kiểm tra; nó không tự xác nhận danh tính hoặc cấp quyền. Service cần từ chối nếu order không thuộc user/tenant hoặc trạng thái nghiệp vụ không cho phép hành động.

Với công cụ ghi dữ liệu, cần thêm xác nhận cho hành động quan trọng, kiểm tra trạng thái hiện tại, idempotency key, audit log và timeout. Việc callback nằm trong allowlist chỉ có nghĩa request được phép yêu cầu công cụ đó; nó không chứng minh mọi đối số mà mô hình tạo đều hợp lệ.

## Danh mục lớn: Tool Search và progressive disclosure

Khi ứng dụng có hàng chục hoặc hàng trăm công cụ, gửi toàn bộ schema trong mọi request làm tăng context, chi phí token và nguy cơ mô hình chọn nhầm. Spring AI cung cấp `ToolSearchToolCallingAdvisor` để triển khai progressive tool disclosure: index danh mục công cụ, đưa một công cụ tìm kiếm vào request, sau đó chỉ đưa các công cụ đã được khám phá vào những lượt tiếp theo.

Có thể bật advisor này bằng cấu hình:

```properties
spring.ai.chat.client.tool-search-advisor.enabled=true
```

Tool search giúp mô hình khám phá đúng công cụ và giảm số schema được gửi trong mỗi lượt. Tuy nhiên, tìm thấy một công cụ không đồng nghĩa người dùng có quyền thực thi nó. Hãy xây dựng catalog/search index theo nhóm quyền hoặc bảo đảm bước chọn và thực thi vẫn áp dụng policy. Không đưa công cụ nhạy cảm vào một catalog chung rồi xem kết quả tìm kiếm như cơ chế phân quyền.

Nếu cần điều kiện động giữa các vòng gọi, phê duyệt trước thao tác phá hủy, giới hạn ngân sách hoặc chọn nguồn tool từ xa theo request, có thể mở rộng `ToolCallingAdvisor`. Advisor có các hook trước/sau mỗi lượt để thay đổi tập tool, kiểm tra điều kiện hoặc dừng vòng lặp. Với trường hợp đơn giản, per-request allowlist và fallback tắt dễ kiểm thử hơn một vòng lặp tùy chỉnh.

## Khi cần tự điều khiển vòng gọi công cụ

`ChatClient` tự đăng ký `ToolCallingAdvisor` và quản lý vòng lặp mặc định. Nếu muốn tự kiểm tra từng tool call trước khi thực thi, có thể tắt auto-registration cho một request bằng:

```java
.advisors(AdvisorParams.toolCallingAdvisorAutoRegister(false))
```

Sau đó caller kiểm tra `ChatResponse.hasToolCalls()`, gọi `ToolCallingManager.executeToolCalls(...)` và quyết định có gửi lượt tiếp theo hay không. Cách này cho phép chèn bước phê duyệt hoặc kiểm tra policy giữa các lượt, nhưng ứng dụng phải tự giữ lịch sử hội thoại, allowlist, giới hạn số vòng và quan sát hoạt động.

Nếu tự điều khiển loop, hãy kiểm tra từng tên tool trong allowlist trước khi dispatch. Không chỉ kiểm tra ở đầu request rồi giữ một danh sách callback toàn cục có thể thay đổi trong lúc vòng lặp đang chạy.

## Kiểm thử giới hạn công cụ theo request

Hãy kiểm tra cả danh sách công cụ được gửi đến model và callback thực sự có thể thực thi. Một câu trả lời cuối đúng không chứng minh allowlist hoạt động đúng.

| Tình huống | Kết quả cần xác minh |
|---|---|
| User A chỉ có quyền xem đơn hàng | Request chỉ nhận callback tra cứu đơn; không có callback hoàn tiền. |
| User B có quyền hoàn tiền | Callback hoàn tiền chỉ được thêm sau khi policy xác nhận quyền. |
| Request thêm `.tools(...)` vào client có defaults | Xác nhận runtime tools được nối thêm; defaults vẫn còn. |
| Client không có defaults và request truyền allowlist | Model chỉ nhìn thấy callback đã chọn cho request. |
| Tool bean tồn tại nhưng không gắn vào request, fallback tắt | Tool call tới tên đó không được resolver toàn cục tự thực thi. |
| Tool bean tồn tại nhưng không gắn vào request, fallback bật | Kiểm tra callback có thể được phân giải theo tên; xác nhận đây là hành vi được cho phép. |
| Một tool bị gọi quá giới hạn | Manager áp dụng `THROW` hoặc `RETURN_ERROR_RESPONSE` đúng cấu hình. |
| Tổng số tool call vượt giới hạn | Vòng gọi dừng hoặc nhận tool error theo policy. |
| Hai request đồng thời thuộc hai tenant | Mỗi callback chỉ nhận context của đúng request. |
| Tool search trả về công cụ nhạy cảm | Policy vẫn chặn nếu user không có quyền thực thi. |
| Model gửi tool name không có trong allowlist | Callback không được thực thi; ghi nhận sự kiện từ chối an toàn. |

Nên tách logic chọn tool thành một `ToolPolicy` hoặc service có unit test. Test các vai trò, tenant, trạng thái tài nguyên và tác vụ khác nhau. Integration test cần xác minh callback list cuối cùng, fallback, giới hạn số lần gọi và context được chuyển đúng.

## Bài tập thực hành

Xây dựng một endpoint hỗ trợ khách hàng với hai vai trò:

1. Tạo `customerTools` gồm `getMyOrderStatus` và `getShipmentTracking`.
2. Tạo `supportAgentTools` gồm `searchCustomer`, `getOrderDetails` và `requestRefundApproval`.
3. Viết `ToolPolicy.allowedToolsFor(user, intent)` để trả callback list theo quyền đã xác thực.
4. Tạo `ChatClient` không có default tools và đính kèm allowlist qua `.tools(...)` cho từng request.
5. Truyền `userId`, `tenantId` và `requestId` qua `ToolContext`; kiểm tra quyền trong service.
6. Giữ `spring.ai.tools.resolution.fallback.enabled=false`, sau đó thử bật trong môi trường kiểm thử để quan sát khác biệt.
7. Cấu hình tối đa 3 lần gọi cho `searchCustomer` và 8 lần gọi tổng trong một lượt.
8. Thử một yêu cầu khiến mô hình lặp tool call; xác minh giới hạn dừng đúng cách.
9. Thử hai request đồng thời của hai tenant và xác minh không rò callback/context.

Bạn hoàn thành khi có thể chứng minh rằng tập công cụ được chọn theo người dùng và tác vụ, callback ngoài allowlist không được thực thi, service từ chối truy cập trái quyền và vòng lặp bị chặn khi vượt giới hạn.

## Danh sách kiểm tra trước khi triển khai

- [ ] Đã xác định tập công cụ tối thiểu cần thiết cho từng loại request.
- [ ] Công cụ nhạy cảm không được đăng ký làm default cho client dùng chung nếu không cần thiết.
- [ ] Allowlist được tạo từ danh tính và policy đã xác thực, không lấy từ tên tool do người dùng tự khai.
- [ ] `ChatClient` không có default tools ngoài phạm vi nếu cần allowlist nghiêm ngặt.
- [ ] Đã hiểu `.tools(...)` nối thêm vào `.defaultTools(...)` trong Spring AI 2.1.0.
- [ ] `spring.ai.tools.resolution.fallback.enabled` được giữ `false` trừ khi có chính sách rõ ràng.
- [ ] Nếu dùng custom resolver, đã kiểm soát danh mục callback mà resolver có thể trả về.
- [ ] Mỗi callback/service kiểm tra quyền trên tài nguyên theo user và tenant.
- [ ] `ToolContext` được tạo theo request và không dùng chung state mutable.
- [ ] Có giới hạn số lần gọi mỗi tool và tổng số tool call trong một lượt.
- [ ] Có quota theo user/tenant ở tầng ứng dụng nếu sản phẩm yêu cầu giới hạn dài hạn.
- [ ] Có timeout, rate limit, giới hạn concurrency và kiểm soát kích thước đầu vào/kết quả.
- [ ] Tool search chỉ phục vụ khám phá; policy vẫn kiểm tra quyền thực thi.
- [ ] Có kiểm thử allowlist, fallback, context, authorization và tool call limits.

Giới hạn công cụ theo từng yêu cầu là một chính sách nhiều lớp: chọn đúng callback cho request, không cho resolver mở rộng danh sách ngoài dự kiến, giới hạn số lần gọi và kiểm tra quyền ở nơi thực thi nghiệp vụ. Khi bốn lớp này được kiểm tra độc lập, ứng dụng có thể mở rộng catalog công cụ mà vẫn giữ được phạm vi hành động của từng request.

## Tài liệu tham khảo

- [Spring AI 2.1.0 – Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 – Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI 2.1.0 – ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html)
- [Spring AI Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)
