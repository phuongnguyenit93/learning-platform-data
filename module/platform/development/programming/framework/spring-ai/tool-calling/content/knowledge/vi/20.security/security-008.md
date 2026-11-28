# Đánh giá tác động của công cụ mặc định và phân giải fallback

Spring AI có hai cơ chế dễ bị nhầm khi kiểm soát công cụ: **default tools** và **resolution fallback**. `defaultTools(...)` quyết định công cụ nào được gắn vào mọi request của một `ChatClient` và được gửi cho mô hình. `ToolCallbackResolver` cùng resolution fallback quyết định ứng dụng có thể tìm và thực thi một callback theo tên hay không, kể cả khi callback đó không được gắn vào request hiện tại.

Hai cơ chế này tạo ra hai đường mở rộng phạm vi thực thi khác nhau. Một tool nhạy cảm đặt trong `defaultTools` sẽ được cung cấp cho mọi request từ client đó. Một tool không được cung cấp cho request vẫn có thể được gọi nếu resolution fallback bật và resolver tìm thấy tên tool. Vì vậy, việc chỉ kiểm tra danh sách tool gửi cho mô hình là chưa đủ để đánh giá quyền thực thi.

Trong Spring AI 2.1.0, resolution fallback mặc định là `false`. Từ 2.0.1, các tool gắn với request là tập tool duy nhất được phép thực thi theo cơ chế mặc định. Bật fallback sẽ khôi phục hành vi tra cứu trên resolver toàn ứng dụng; nếu resolver chứa nhiều callback, một tool không được dự định cho request vẫn có thể trở nên khả dụng khi mô hình trả về đúng tên.

Sau bài học, bạn có thể:

- Phân biệt công cụ được quảng bá qua `defaultTools` với callback có thể phân giải qua resolver.
- Hiểu cách `ChatClient.defaultTools(...)` và request `.tools(...)` kết hợp.
- Hiểu cách `ToolCallbackResolver` mặc định thu thập callback từ Spring context.
- Đánh giá tác động bảo mật của `spring.ai.tools.resolution.fallback.enabled`.
- Thiết kế resolver allowlist và chọn tool theo quyền đã xác thực.
- Phân biệt precedence của `ChatClient` với `ChatModel` trực tiếp.
- Kiểm thử cả tool list gửi mô hình và callback thực sự có thể được thực thi.

## 1. Hai cơ chế, hai câu hỏi khác nhau

Khi một request gọi `ChatClient`, có hai câu hỏi cần trả lời:

1. **Mô hình được biết đến những công cụ nào?** Đây là tập tool definitions gắn vào request qua `defaultTools(...)` và `.tools(...)`.
2. **Ứng dụng có thể thực thi callback nào khi nhận tool call?** Đây là tập callback có trong request, cộng với callback được tìm thêm qua `ToolCallbackResolver` nếu resolution fallback bật.

| Cơ chế | Thành phần | Tác động |
| --- | --- | --- |
| Default tools | `ChatClient.Builder.defaultTools(...)` | Gắn tool vào mọi request tạo từ builder; tool definitions được gửi cho mô hình. |
| Request tools | `ChatClient` request `.tools(...)` | Bổ sung tool cho request hiện tại; với `ChatClient`, nó cộng thêm vào default tools. |
| Tool resolver | `ToolCallbackResolver` | Tra cứu callback theo tên tool. Bản mặc định dựa trên callback bean và provider trong Spring context. |
| Resolution fallback | `spring.ai.tools.resolution.fallback.enabled` | Cho phép `ToolCallingManager` tìm callback không có trong request qua resolver và thực thi nó. |

Default tools làm rộng **tập tool được cung cấp cho mọi request**. Fallback làm rộng **tập callback có thể được thực thi ngoài request**. Tắt fallback không loại bỏ các tool đã được gắn vào request; không đưa tool nhạy cảm vào default tools cũng chưa đủ nếu fallback toàn cục vẫn bật.

## 2. Default tools trong ChatClient

`ChatClient.Builder.defaultTools(...)` đăng ký công cụ dùng chung cho mọi request được tạo từ builder đó. Có thể truyền object có method `@Tool`, `ToolCallback`, `ToolCallbackProvider`, array hoặc collection của các loại này.

```java
ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultTools(currentTimeTool, publicCatalogLookupTool)
        .build();
```

Mọi request từ `chatClient` đều có `currentTimeTool` và `publicCatalogLookupTool` trong danh sách tool. Đây là cách tiện lợi cho capability an toàn, thực sự dùng chung, chẳng hạn lấy giờ hiện tại hoặc tra cứu catalog công khai.

Không đặt các công cụ thay đổi dữ liệu, gửi thông báo, xóa tài nguyên, phê duyệt hoặc quản trị vào default set chỉ vì chúng được dùng ở một số màn hình. Default tools được chia sẻ trên tất cả request từ cùng builder, kể cả request không có nhu cầu nghiệp vụ tương ứng.

### Request-level tools được cộng thêm, không thay thế default tools

Trong Spring AI 2.1.0, `.tools(...)` trên request của `ChatClient` thêm công cụ vào default set:

```java
ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultTools(currentTimeTool)
        .build();

String answer = chatClient.prompt()
        .user("Tra cứu đơn hàng ORD-42")
        .tools(orderLookupTool)
        .call()
        .content();
```

Request này cung cấp cả `currentTimeTool` và `orderLookupTool` cho mô hình. `.tools(orderLookupTool)` không loại bỏ `currentTimeTool` khỏi default set.

| Cấu hình ChatClient | Tool definitions được gửi cho mô hình |
| --- | --- |
| Chỉ `defaultTools(a, b)` | `a`, `b` ở mọi request từ client |
| Chỉ request `.tools(a, b)` | `a`, `b` ở request đó |
| `defaultTools(a)` và request `.tools(b)` | `a` và `b` |
| `defaultTools(a, b)` và request `.tools(c)` | `a`, `b`, `c` |

Hệ quả bảo mật: không thể dùng `.tools(allowedForThisUser)` để thu hẹp một default set đã chứa tool quản trị. Nếu một nhóm request cần capability khác nhau, hãy giữ client mặc định chỉ có tool dùng chung an toàn hoặc tạo client riêng với default set được kiểm soát rõ ràng.

## 3. ToolCallback bean không tự động trở thành default tool

Một `ToolCallback` bean có thể được inject và truyền rõ ràng vào request:

```java
@Configuration(proxyBeanMethods = false)
class OrderToolConfiguration {

    @Bean
    ToolCallback orderLookupTool(OrderQueryService orderQueryService) {
        return FunctionToolCallback
                .builder("lookup_order", orderQueryService::lookup)
                .description("Tra cứu đơn hàng theo mã")
                .inputType(OrderLookupRequest.class)
                .build();
    }
}
```

Sau đó:

```java
chatClient.prompt()
        .user("Tra cứu đơn ORD-42")
        .tools(orderLookupTool)
        .call()
        .content();
```

Việc bean tồn tại trong `ApplicationContext` giúp Spring quản lý callback và có thể đưa callback vào resolver mặc định. Nó không tự có nghĩa callback được gửi đến mọi request của `ChatClient`. Muốn làm default tool, phải cung cấp nó qua `.defaultTools(...)`; muốn giới hạn theo request, truyền nó qua `.tools(...)` sau khi ứng dụng xác định quyền.

Từ Spring AI 2.0, không dùng lại cách khai báo bean `Function`/`Supplier`/`Consumer` thuần rồi tham chiếu bằng `toolNames(...)` của `SpringBeanToolCallbackResolver`. Cơ chế đó đã bị loại bỏ; hãy đăng ký `ToolCallback` bean tường minh.

## 4. ToolCallbackResolver làm gì?

`ToolCallbackResolver` là interface tra cứu callback bằng tên:

```java
public interface ToolCallbackResolver {
    @Nullable
    ToolCallback resolve(String toolName);
}
```

Spring AI 2.1.0 tự cấu hình `StaticToolCallbackResolver` với:

- Các `ToolCallback` bean trong Spring ApplicationContext.
- Các callback do `ToolCallbackProvider` bean cung cấp.
- MCP providers được loại khỏi bước đăng ký tĩnh mặc định để tránh gọi mạng và liệt kê tool từ các MCP server ngay khi khởi động.

Resolver là nguồn tra cứu nội bộ mà `ToolCallingManager` sử dụng trong cả advisor-controlled và user-controlled execution. Nó không phải danh sách tool definitions tự động được gửi đến mô hình.

Có thể thay resolver mặc định bằng một bean riêng khi cần chiến lược tra cứu khác, ví dụ từ database, classpath hoặc nguồn remote:

```java
@Bean
ToolCallbackResolver toolCallbackResolver(List<ToolCallback> toolCallbacks) {
    return new StaticToolCallbackResolver(toolCallbacks);
}
```

Ví dụ trên chỉ minh họa cách tạo resolver từ danh sách callback. Trong hệ thống phân quyền, danh sách đầu vào phải được kiểm soát cẩn thận; nếu truyền toàn bộ callback bean vào resolver rồi bật fallback, phạm vi thực thi sẽ rộng theo chính danh sách đó.

## 5. Resolution fallback là gì?

Thông thường, `ToolCallingManager` thực thi callback đã gắn vào request. Nếu mô hình trả về một tool call có tên không nằm trong callback list của request, manager có thể thử tra cứu tên đó qua `ToolCallbackResolver` khi resolution fallback được bật.

```text
Model response: tool call "delete_customer"
                    |
                    v
       Có callback delete_customer trong request?
                    |
             +------+------+
             |             |
            Có            Không
             |             |
       Thực thi callback   Fallback enabled?
                           |
                    +------+------+
                    |             |
                   Có            Không
                    |             |
             Resolver.resolve   Từ chối phân giải
                    |             |
             Có callback?        Không thực thi
                    |
              +-----+-----+
              |           |
             Có          Không
              |           |
          Thực thi     Không tìm thấy
```

Property điều khiển fallback:

```properties
spring.ai.tools.resolution.fallback.enabled=false
```

Giá trị mặc định trong Spring AI 2.1.0 là `false`. Khi tắt, chỉ callback gắn với request mới được thực thi. Khi bật:

```properties
spring.ai.tools.resolution.fallback.enabled=true
```

một tool call không có trong request có thể được phân giải theo tên từ resolver và thực thi nếu resolver trả về callback tương ứng.

Khi tự tạo `ToolCallingManager`, có cùng tùy chọn trên builder:

```java
ToolCallingManager toolCallingManager = ToolCallingManager.builder()
        .toolCallbackResolver(toolCallbackResolver)
        .resolutionFallbackEnabled(false)
        .build();
```

Đừng nhầm fallback với việc tự động gửi tool definition cho mô hình. Fallback không nhất thiết thêm tool vào prompt; nó mở rộng khả năng thực thi khi response của mô hình chứa tên tool mà request không đính kèm.

## 6. Thay đổi quan trọng từ Spring AI 2.0.1

Trước Spring AI 2.0.1, `DefaultToolCallingManager` có thể tự tìm callback trong resolver toàn ứng dụng khi mô hình gọi một tool không được gắn vào request. Hành vi đó khiến callback bean có thể được thực thi chỉ vì resolver biết tên của nó.

Từ 2.0.1, resolution fallback bị tắt mặc định. Theo cấu hình mặc định, các tool gắn qua `.tools(...)`, `.defaultTools(...)` hoặc `ToolCallingChatOptions.toolCallbacks(...)` là tập callback được phép thực thi trong request đó.

| Hành vi | Trước 2.0.1 | Từ 2.0.1 và 2.1.0 |
| --- | --- | --- |
| Fallback tra cứu callback bean không gắn request | Bật theo hành vi mặc định cũ | Tắt theo mặc định |
| Chỉ callback gắn request được thực thi | Không bảo đảm | Có, khi fallback giữ mặc định `false` |
| Muốn khôi phục fallback cũ | Không cần bật | Phải bật property hoặc builder switch |

Khi nâng cấp từ 2.0.0 hoặc nhánh cũ hơn, hãy kiểm tra ứng dụng có phụ thuộc vào việc mô hình gọi tên một callback bean mà request không đính kèm hay không. Nếu có, hãy thay bằng việc cung cấp callback rõ ràng theo request hoặc đánh giá lại resolver và quyền thực thi trước khi bật fallback.

## 7. Rủi ro bảo mật khi bật fallback toàn ứng dụng

Giả sử ứng dụng có các bean:

- `lookup_order`: tra cứu đơn hàng.
- `cancel_order`: hủy đơn hàng.
- `delete_customer`: xóa hồ sơ khách hàng.
- `grant_admin_role`: cấp quyền quản trị.

Một request thông thường chỉ gắn `lookup_order`. Nếu fallback tắt, các callback khác không được tìm thêm để thực thi từ resolver. Nếu fallback bật và resolver mặc định chứa các bean tương ứng, một tool call có tên `delete_customer` hoặc `grant_admin_role` vẫn có thể được phân giải dù request không đính kèm những công cụ đó.

Điều này tạo ra một dạng mở rộng quyền ngoài dự kiến:

1. Ứng dụng có callback đặc quyền trong Spring context.
2. Resolver toàn ứng dụng biết các callback đó.
3. Request hiện tại không chủ định cung cấp công cụ đặc quyền.
4. Fallback cho phép manager tra cứu tên tool không có trong request.
5. Nếu model/provider trả tool call có tên khớp, callback có thể được thực thi.

Tên tool không phải bí mật và việc không gửi tool definition không phải ranh giới bảo mật. Mô hình có thể tạo tên tool do hallucination, bị ảnh hưởng bởi prompt injection trong dữ liệu truy xuất hoặc nhận chỉ dẫn từ nội dung không đáng tin cậy. Nếu fallback bật, resolver có thể biến một tên ngoài request thành hành động thực tế.

Tác động đặc biệt lớn với:

- Công cụ ghi, xóa, gửi thông báo hoặc kích hoạt workflow.
- Công cụ quản trị tài khoản, role, permission hoặc cấu hình.
- Công cụ đọc dữ liệu đa tenant hoặc dữ liệu cá nhân.
- Công cụ gọi hệ thống ngoài bằng credential dịch vụ có quyền rộng.
- Tool provider từ nguồn remote hoặc MCP mà ứng dụng không kiểm soát đầy đủ.

Spring AI cảnh báo rõ rằng bật fallback khiến mọi tool có thể truy cập qua resolver trở thành công cụ có thể thực thi khi mô hình gọi tên, bao gồm công cụ có mức rủi ro cao và công cụ phá hủy dữ liệu.

## 8. Hai cấu hình độc lập có thể mở rộng quyền cùng lúc

Hãy xem hai ví dụ:

**Trường hợp A — default tools có công cụ nhạy cảm, fallback tắt:**

```java
ChatClient client = ChatClient.builder(chatModel)
        .defaultTools(orderLookupTool, deleteCustomerTool)
        .build();
```

`deleteCustomerTool` được gửi cho mô hình ở mọi request từ client này và được gắn vào request. Fallback tắt không bảo vệ được trường hợp này vì tool đã có trong request.

**Trường hợp B — default tools chỉ có công cụ đọc, fallback bật:**

```java
ChatClient client = ChatClient.builder(chatModel)
        .defaultTools(orderLookupTool)
        .build();
```

```properties
spring.ai.tools.resolution.fallback.enabled=true
```

Mô hình chỉ được gửi định nghĩa `orderLookupTool`, nhưng nếu resolver chứa `deleteCustomerTool`, tên đó vẫn có thể được phân giải và thực thi khi mô hình trả về tool call tương ứng.

| Default tools | Fallback | Đánh giá |
| --- | --- | --- |
| Chỉ tool an toàn | Tắt | Phạm vi dễ kiểm soát nhất; request cần thêm tool phải đính kèm rõ ràng. |
| Có tool nhạy cảm | Tắt | Tool nhạy cảm vẫn được quảng bá và gắn vào mọi request của client. |
| Chỉ tool an toàn | Bật | Tool ngoài request trong resolver vẫn có thể thực thi. |
| Có tool nhạy cảm | Bật | Hai đường mở rộng quyền cùng tồn tại; phạm vi rủi ro lớn nhất. |

Đánh giá bảo mật phải kiểm tra đồng thời default tool set, request tool set, resolver contents và fallback setting.

## 9. Cấu hình mặc định an toàn

Với ứng dụng thông thường, giữ fallback tắt:

```properties
spring.ai.tools.resolution.fallback.enabled=false
```

Chỉ đưa công cụ thực sự dùng chung và có mức rủi ro phù hợp vào `defaultTools`. Công cụ theo vai trò, tenant hoặc hành động nên được chọn tại request sau khi xác thực người dùng:

```java
public String ask(String question, AuthenticatedActor actor) {
    List<ToolCallback> allowedTools = new ArrayList<>();
    allowedTools.add(orderLookupTool);

    if (authorizationService.hasCapability(actor, "ORDER_CANCEL")) {
        allowedTools.add(orderCancellationTool);
    }

    return chatClient.prompt()
            .user(question)
            .tools(allowedTools)
            .toolContext(Map.of(
                    "actorId", actor.id(),
                    "tenantId", actor.tenantId()))
            .call()
            .content();
}
```

Ví dụ giả định `chatClient` không có default tools nhạy cảm. `.tools(allowedTools)` cộng thêm vào defaults; vì vậy hãy bảo đảm default set đã được thu hẹp trước khi dựa vào danh sách request-level.

Danh sách `allowedTools` phải được tạo từ principal đã xác thực và quyền do server kiểm tra. Không lấy role, actor ID hoặc tenant ID từ prompt hay tool arguments. Service nghiệp vụ vẫn phải kiểm tra quyền trên từng tài nguyên ở thời điểm thực thi.

## 10. Khi nào cần custom ToolCallbackResolver?

Nếu ứng dụng thực sự cần fallback, hãy thay resolver toàn ứng dụng bằng resolver chỉ biết các callback được phép phân giải trong phạm vi thiết kế đó.

Ví dụ allowlist tĩnh chỉ gồm các công cụ đọc không nhạy cảm:

```java
@Bean
ToolCallbackResolver toolCallbackResolver(
        ToolCallback currentTimeTool,
        ToolCallback publicCatalogLookupTool) {

    return new StaticToolCallbackResolver(List.of(
            currentTimeTool,
            publicCatalogLookupTool));
}
```

Sau đó mới bật fallback nếu thực sự cần:

```properties
spring.ai.tools.resolution.fallback.enabled=true
```

Trong cấu hình này, resolver không biết `deleteCustomerTool` hoặc `grantAdminRoleTool`, nên fallback không thể tìm các callback đó. Tuy vậy, callback trong allowlist vẫn phải tự xác thực và phân quyền.

`ToolCallbackResolver.resolve(String toolName)` chỉ nhận tên tool, không nhận request tool list hoặc `ToolContext`. Vì thế, resolver tĩnh toàn ứng dụng không tự biết request hiện tại thuộc tenant nào hoặc actor nào. Nếu cần quyết định theo người dùng, hãy ưu tiên tạo danh sách callback theo request và giữ fallback tắt. Một resolver động phải có thiết kế truyền context/authorization rõ ràng, an toàn với blocking và reactive execution, không dựa vào mutable state hoặc `ThreadLocal` dùng chung giữa các request.

Không nên viết resolver trả về bất kỳ bean nào chỉ cần tên khớp. Resolver phải áp dụng allowlist rõ ràng và không được dùng việc mô hình biết tên tool như bằng chứng người dùng có quyền.

## 11. Phân biệt ChatClient với ChatModel trực tiếp

Quy tắc kết hợp tool mặc định khác nhau giữa hai API:

| API | Tool mặc định | Tool theo request |
| --- | --- | --- |
| `ChatClient` | `.defaultTools(a)` áp dụng mọi request từ client | `.tools(b)` cộng thêm, kết quả là `a + b` |
| `ChatModel` | `ToolCallingChatOptions.toolCallbacks(a)` nằm trong default options | Request options có `toolCallbacks(b)` thay thế default options; model chỉ thấy `b` |

Ví dụ `ChatModel` trực tiếp:

```java
ChatModel chatModel = buildChatModelWithDefaults(
        List.of(orderLookupTool, currentTimeTool));

ToolCallingChatOptions requestOptions = ToolCallingChatOptions.builder()
        .toolCallbacks(List.of(orderCancellationTool))
        .build();

ChatResponse response = chatModel.call(
        new Prompt("Hủy đơn ORD-42", requestOptions));
```

Trong ví dụ, request options thay thế default tool options của `ChatModel`. Nếu muốn kết hợp, ứng dụng phải tự tạo danh sách gồm cả default và request callbacks.

Tuy nhiên, nếu resolution fallback bật, callback không có trong request vẫn có thể được tìm qua resolver. Vì vậy, request options thay thế default list không phải cách chặn fallback. Hai cơ chế cần được kiểm tra riêng.

## 12. MCP và các nguồn tool bên ngoài

MCP tool được biểu diễn bằng `ToolCallback` và có thể kết hợp với tool nội bộ trong `ChatClient`. MCP client auto-configuration tạo `ToolCallbackProvider`, nhưng các MCP providers được loại khỏi static resolver mặc định để tránh gọi mạng liệt kê tool sớm. Ứng dụng phải inject và cung cấp MCP provider qua `.tools(...)` hoặc `.defaultTools(...)`.

Khi kết hợp local tools và MCP tools:

- Chỉ kết nối MCP server đáng tin cậy và xác thực nguồn server.
- Dùng `McpToolFilter` để giới hạn tool từ server bên ngoài.
- Tránh tên tool trùng giữa local và remote; `ChatClient` kiểm tra danh sách hợp nhất và báo lỗi nếu trùng.
- Nếu tự điều phối bằng `ChatModel`, tự gọi `ToolCallingChatOptions.validateToolCallbacks(...)` trên danh sách đã hợp nhất; nếu không, tên trùng có thể khiến callback đầu tiên được chọn mà không có lỗi rõ ràng.
- Không bật fallback rộng chỉ để làm cho MCP tool được tìm tự động; hãy wire provider và callback theo request.

## 13. Authorization phải được kiểm tra ở callback/service

Việc chọn tool theo request giảm số hành động mô hình có thể yêu cầu, nhưng không thay thế kiểm tra quyền. Mô hình vẫn có thể gửi arguments sai, đoán ID tài nguyên hoặc bị ảnh hưởng bởi nội dung không đáng tin cậy.

```java
@Component
public class OrderTools {

    private final OrderService orderService;
    private final CurrentActor currentActor;
    private final OrderAuthorizationService authorizationService;

    public OrderTools(
            OrderService orderService,
            CurrentActor currentActor,
            OrderAuthorizationService authorizationService) {
        this.orderService = orderService;
        this.currentActor = currentActor;
        this.authorizationService = authorizationService;
    }

    @Tool(description = "Hủy một đơn hàng mà người dùng hiện tại có quyền hủy")
    public CancellationResult cancelOrder(
            @ToolParam(description = "Mã đơn hàng") String orderId,
            ToolContext toolContext) {

        AuthenticatedActor actor = currentActor.requireAuthenticated();
        authorizationService.requireCanCancel(actor, orderId);
        return orderService.cancel(orderId, actor.tenantId());
    }
}
```

Trong ví dụ, actor lấy từ security layer phía server; `ToolContext` có thể truyền thêm request/tenant context do server tạo. Service phải xác minh quyền trên đơn hàng cụ thể, không dựa vào việc tool có xuất hiện trong prompt.

Với tool có tác động lớn, kết hợp:

- Kiểm tra quyền actor/tenant/resource ở service.
- Confirmation trước hành động khó đảo ngược.
- Idempotency key để tránh thực thi trùng khi retry.
- Audit log cho actor, tool, resource và kết quả.
- Rate limit, timeout và giới hạn số tool call.
- Result filtering để không trả dữ liệu ngoài phạm vi người dùng.

## 14. Kiểm thử tác động của default tools và fallback

Kiểm thử cần bao phủ cả tool definitions gửi cho mô hình và callback có thể được thực thi. Chỉ xác minh prompt có đúng tool list là chưa đủ nếu fallback bật.

| Kịch bản | Cấu hình | Kết quả mong đợi |
| --- | --- | --- |
| Request gắn callback rõ ràng | Fallback `false` | Callback trong request được thực thi. |
| Callback bean tồn tại nhưng không gắn request | Fallback `false` | Không được resolver fallback để thực thi. |
| Callback bean tồn tại nhưng không gắn request | Fallback `true`, resolver có callback | Callback có thể được phân giải và thực thi theo tên. |
| Callback không nằm trong resolver | Fallback `true` | Không tìm thấy callback; không thực thi. |
| Tool nhạy cảm nằm trong `defaultTools` | Fallback `false` | Tool vẫn xuất hiện trong mọi request của client. |
| Request `.tools(allowed)` với default set nhạy cảm | Fallback `false` | Danh sách là union; tool nhạy cảm vẫn xuất hiện. |
| ChatModel request options có callback riêng | Fallback `false` | Request tool list thay thế default tool options. |
| ChatModel request options thay thế defaults | Fallback `true` | Resolver vẫn có thể tìm callback vắng mặt trong request. |
| Actor không có quyền gọi tool | Bất kỳ | Service từ chối, không tạo side effect. |
| Model trả tên tool lạ | Fallback `false` | Không được gọi callback ngoài request. |
| Tool name trùng giữa local và MCP | ChatClient | Request thất bại với lỗi tên trùng; không chạy nhầm callback. |

Ví dụ kiểm thử resolver allowlist:

```java
@Test
void resolverOnlyExposesExplicitlyAllowedTools() {
    ToolCallbackResolver resolver = new StaticToolCallbackResolver(
            List.of(currentTimeTool, publicCatalogLookupTool));

    assertThat(resolver.resolve("current_time")).isSameAs(currentTimeTool);
    assertThat(resolver.resolve("public_catalog_lookup"))
            .isSameAs(publicCatalogLookupTool);
    assertThat(resolver.resolve("delete_customer")).isNull();
}
```

Ví dụ kiểm thử manager khi fallback tắt:

```java
@Test
void doesNotResolveUnattachedToolWhenFallbackIsDisabled() {
    ToolCallingManager manager = ToolCallingManager.builder()
            .toolCallbackResolver(allApplicationToolsResolver)
            .resolutionFallbackEnabled(false)
            .build();

    Prompt prompt = promptWithOnly(orderLookupTool);
    ChatResponse response = responseRequesting("delete_customer");

    assertThatThrownBy(() -> manager.executeToolCalls(prompt, response))
            .isInstanceOf(IllegalStateException.class);

    verifyNoInteractions(deleteCustomerService);
}
```

Đây là test minh họa ranh giới thực thi; helper tạo prompt/response và callback được lược bỏ. Hãy kiểm tra exception cụ thể theo phiên bản Spring AI đang dùng. Bài test quan trọng nhất là service nhạy cảm không bị gọi khi tool không nằm trong request và fallback tắt.

## 15. Quan sát và audit mà không làm lộ dữ liệu

Spring AI phát Micrometer observations cho tool call dưới tên `spring.ai.tool`, bao gồm tên tool, metadata, thời gian thực thi và tracing context khi có tracer. Arguments và results có thể được xuất thành span attributes nhưng mặc định bị tắt vì lý do nhạy cảm.

Khi giám sát fallback và default tools:

- Ghi nhận tool name, request ID, actor đã xác thực và quyết định authorization.
- Phân biệt callback đến từ request list hay được resolver fallback tìm thấy nếu ứng dụng có instrumentation phù hợp.
- Theo dõi số lần fallback hit và tên tool được phân giải.
- Không ghi token, secret, toàn bộ arguments hoặc dữ liệu cá nhân nếu không có nhu cầu và chính sách rõ ràng.
- Cảnh báo khi fallback được bật ở môi trường production hoặc resolver chứa tool có mức rủi ro cao.
- Rà soát tool inventory và quyền của callback bean/provider khi thêm tích hợp mới.

## 16. Quy trình đánh giá trước khi bật fallback

Chỉ bật fallback sau khi trả lời được các câu hỏi sau:

1. Tại sao tool không thể được cung cấp rõ ràng bằng `.tools(...)` hoặc `.defaultTools(...)`?
2. Resolver hiện tại chứa chính xác những callback nào?
3. Có callback ghi, xóa, quản trị hoặc đọc dữ liệu nhạy cảm trong resolver không?
4. Có provider nào tạo callback động hoặc lấy callback từ hệ thống ngoài không?
5. Resolver có allowlist và kiểm soát tên tool không?
6. Mỗi callback có tự xác thực và phân quyền actor/tenant/resource không?
7. Có test chứng minh tool ngoài request không thể chạy khi fallback tắt và chỉ tool allowlist chạy được khi fallback bật không?
8. Có audit, rate limit, idempotency và confirmation cho hành động nhạy cảm không?
9. Có thể dùng một client hoặc manager riêng với resolver giới hạn hơn không?
10. Có theo dõi và cảnh báo các lần fallback resolution không?

Nếu không cần tra cứu callback ngoài request, giữ fallback tắt và cung cấp tool rõ ràng cho từng request. Nếu cần fallback cho một nhóm tool an toàn, thay resolver toàn ứng dụng bằng allowlist có chủ đích và vẫn kiểm tra quyền trong service.

## Những điểm cần nhớ

- `defaultTools(...)` cung cấp tool cho mọi request từ một `ChatClient` builder; request `.tools(...)` cộng thêm, không thay thế.
- `ToolCallback` bean được đưa vào resolver mặc định nhưng không tự động trở thành tool definition của mọi request.
- `ToolCallbackResolver` tra cứu callback theo tên; resolver mặc định dựa trên các `ToolCallback` bean và `ToolCallbackProvider` bean (MCP providers bị loại khỏi đăng ký tĩnh mặc định).
- Resolution fallback mặc định `false` trong Spring AI 2.1.0; từ 2.0.1 chỉ callback gắn với request được thực thi theo cơ chế mặc định.
- Bật fallback cho phép manager phân giải và thực thi callback có trong resolver dù callback không được gắn vào request.
- Default tools và fallback là hai đường mở rộng phạm vi khác nhau; phải đánh giá cả hai.
- `ChatClient` hợp nhất default và request tools; `ChatModel` request options thay thế default tool options.
- Không dùng việc ẩn tool khỏi prompt làm authorization. Service phải kiểm tra actor, tenant và tài nguyên ở thời điểm thực thi.
- Nếu bật fallback, dùng resolver allowlist, audit, confirmation và kiểm thử tên tool ngoài request.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/2.1/api/tools.html)
- [Spring AI 2.1.0 Reference — Defining Tools](https://docs.spring.io/spring-ai/reference/2.1/api/tools/defining.html)
- [Spring AI 2.1.0 Reference — ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/2.1/api/tools/chatmodel-tool-calling.html)
- [Spring AI Upgrade Notes — Tool Resolution Fallback Disabled by Default](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)
- [Spring AI 2.1.0 Reference — MCP Tools](https://docs.spring.io/spring-ai/reference/2.1/api/tools.html)

Các hành vi và ví dụ trong bài dựa trên Spring AI 2.1.0. Khi nâng cấp hoặc dùng phiên bản khác, hãy kiểm tra lại default tool precedence, resolver auto-configuration và property fallback trong tài liệu đúng phiên bản; không suy luận từ hành vi của Spring AI 1.x hoặc 2.0.0 trước 2.0.1.
