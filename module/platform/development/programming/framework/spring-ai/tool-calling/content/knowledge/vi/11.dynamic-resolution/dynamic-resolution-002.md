# Phân giải tĩnh từ tập ToolCallback đã biết

Trong Spring AI, `ToolCallbackResolver` chịu trách nhiệm tìm callback theo tên tool. Với cách phân giải tĩnh, ứng dụng cung cấp trước một tập `ToolCallback` đã biết; `StaticToolCallbackResolver` dùng tập đó để trả về callback tương ứng khi `ToolCallingManager` cần thực thi một tool call.

Cần phân biệt ba trách nhiệm:

- **Đăng ký tool:** quyết định những định nghĩa tool nào được gửi đến mô hình.
- **Phân giải tool:** tìm implementation tương ứng với tên tool trong yêu cầu của mô hình.
- **Thực thi tool:** gọi callback, truyền đối số và context, rồi nhận kết quả.

`StaticToolCallbackResolver` chỉ làm nhiệm vụ thứ hai. Nó không tự gửi schema đến mô hình và không tự thực thi nghiệp vụ. Bài viết tập trung vào một tập callback hữu hạn, được biết trước khi ứng dụng xử lý request, cùng cách Spring AI 2.x sử dụng resolver trong vòng tool calling.

## 1. ToolCallbackResolver giải quyết vấn đề gì?

Mô hình trả về một tool call có tên, ví dụ `lookupInventory`, và chuỗi JSON arguments:

~~~json
{
  "sku": "SKU-100",
  "warehouse": "HANOI"
}
~~~

Ứng dụng cần tìm implementation có thể xử lý tên tool đó. `ToolCallbackResolver` định nghĩa hợp đồng tra cứu:

~~~java
public interface ToolCallbackResolver {

    @Nullable
    ToolCallback resolve(String toolName);
}
~~~

Phương thức `resolve` nhận tên tool và trả về `ToolCallback` tương ứng. Nếu không tìm thấy, kết quả có thể là `null`.

Một callback chứa cả định nghĩa và logic thực thi:

- `getToolDefinition()` cung cấp tên, mô tả và input schema.
- `getToolMetadata()` cung cấp metadata điều khiển cách xử lý kết quả.
- `call(toolInput)` hoặc `call(toolInput, toolContext)` thực thi tool.

Resolver chỉ tìm callback. `ToolCallingManager` mới là thành phần điều phối việc thực thi: nhận tool call, tìm callback, gọi callback, thu thập tool result và tạo lịch sử hội thoại tiếp theo.

## 2. Phân giải tĩnh từ một tập callback đã biết

`StaticToolCallbackResolver` là implementation của `ToolCallbackResolver` dùng một registry tĩnh. Constructor nhận danh sách callback:

~~~java
public StaticToolCallbackResolver(List<ToolCallback> toolCallbacks)
~~~

Ví dụ, ứng dụng có hai tool đọc dữ liệu:

~~~java
ToolCallback inventoryLookup = ...;
ToolCallback customerLookup = ...;

ToolCallbackResolver resolver =
    new StaticToolCallbackResolver(
        List.of(inventoryLookup, customerLookup)
    );
~~~

Khi cần tìm tool:

~~~java
ToolCallback callback = resolver.resolve("lookupInventory");

if (callback == null) {
    throw new IllegalArgumentException("Không tìm thấy tool được yêu cầu");
}
~~~

Tập callback được xác định khi tạo resolver. Ứng dụng biết trước những tool có thể được phân giải; không cần truy vấn database hoặc gọi dịch vụ discovery từ xa cho mỗi lần tra cứu.

Điều này phù hợp khi:

- Danh sách tool ổn định theo cấu hình ứng dụng.
- Tool được tạo từ các Spring bean hoặc factory lúc khởi động.
- Muốn kiểm tra và kiểm soát tập callback trước khi cho phép phân giải.
- Cần một cách tra cứu đơn giản, ít phụ thuộc hạ tầng bên ngoài.

Nếu danh sách tool cần thay đổi theo thời gian thực, tenant hoặc quyền người dùng, một registry tĩnh dùng chung có thể không phù hợp. Khi đó, cân nhắc tạo tập callback riêng theo request hoặc triển khai resolver có chiến lược tra cứu động.

## 3. Luồng phân giải và thực thi

Trong vòng tool calling, mô hình chỉ trả về yêu cầu. Ứng dụng chịu trách nhiệm tìm callback và gọi nó.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as ChatClient
    participant M as Mô hình
    participant A as ToolCallingAdvisor
    participant T as ToolCallingManager
    participant R as StaticToolCallbackResolver
    participant B as ToolCallback

    U->>C: Yêu cầu tra cứu tồn kho
    C->>M: Prompt và tool definitions
    M-->>A: Tool call lookupInventory + JSON
    A->>T: Yêu cầu thực thi tool calls
    T->>T: Tìm callback trong request tool set
    alt Callback đã gắn vào request
        T->>B: call(JSON arguments, ToolContext)
        B-->>T: Tool result
    else Callback không có trong request và fallback bật
        T->>R: resolve("lookupInventory")
        R-->>T: ToolCallback tương ứng hoặc null
        alt Tìm thấy callback
            T->>B: call(JSON arguments, ToolContext)
            B-->>T: Tool result
        else Không tìm thấy callback
            T-->>A: Tool không được phân giải
        end
    else Callback không có trong request và fallback tắt
        T-->>A: Tool không được phép thực thi
    end
    T-->>A: ToolExecutionResult
    A->>M: Lịch sử hội thoại có tool result
    M-->>C: Câu trả lời cuối
    C-->>U: Kết quả
~~~

Các bước chính:

1. Ứng dụng tạo hoặc cấu hình các `ToolCallback`.
2. Resolver giữ tập callback đã biết.
3. Request cung cấp các tool definition phù hợp để mô hình có thể lựa chọn.
4. Mô hình trả về tool call với tên và đối số.
5. `ToolCallingManager` tìm callback theo tên. Nếu callback không có trong tập tool của request và cơ chế fallback được bật, manager có thể hỏi resolver.
6. Manager gọi callback, truyền JSON arguments và `ToolContext`.
7. Kết quả được đưa vào lịch sử hội thoại để mô hình tạo câu trả lời tiếp theo.

Một điểm cần nhớ: có callback trong resolver không đồng nghĩa mô hình đã nhìn thấy tool definition. Việc công bố tool cho mô hình và việc tìm callback khi thực thi là hai bước riêng biệt.

## 4. Tạo StaticToolCallbackResolver từ callback cụ thể

Giả sử ứng dụng đã có hai callback:

~~~java
public record InventoryQuery(String sku, String warehouse) {}

@Bean
ToolCallback lookupInventory(InventoryService inventoryService) {
    return FunctionToolCallback.builder(
            "lookupInventory",
            (InventoryQuery query) ->
                inventoryService.lookup(query.sku(), query.warehouse())
        )
        .description("Tra cứu tồn kho theo SKU và mã kho.")
        .inputType(InventoryQuery.class)
        .build();
}

@Bean
ToolCallback lookupCustomer(CustomerService customerService) {
    return FunctionToolCallback.builder(
            "lookupCustomer",
            customerService::lookup
        )
        .description("Tra cứu khách hàng theo mã khách hàng.")
        .inputType(CustomerQuery.class)
        .build();
}
~~~

Có thể tạo resolver từ các callback bean:

~~~java
@Configuration(proxyBeanMethods = false)
class ToolResolutionConfiguration {

    @Bean
    ToolCallbackResolver toolCallbackResolver(
            List<ToolCallback> toolCallbacks) {

        return new StaticToolCallbackResolver(toolCallbacks);
    }
}
~~~

Spring inject các bean có kiểu `ToolCallback` vào danh sách. Resolver sau đó có thể tìm callback bằng tên.

Cách này phù hợp khi ứng dụng muốn resolver biết toàn bộ tập callback bean đã đăng ký. Tuy nhiên, một resolver toàn cục có thể chứa cả tool nhạy cảm. Nếu cần allowlist hẹp, hãy inject các callback cụ thể thay vì gom tất cả:

~~~java
@Bean
ToolCallbackResolver readOnlyToolResolver(
        @Qualifier("lookupInventory") ToolCallback inventory,
        @Qualifier("lookupCustomer") ToolCallback customer) {

    return new StaticToolCallbackResolver(
        List.of(inventory, customer)
    );
}
~~~

Ví dụ thứ hai giới hạn registry vào hai tool tra cứu. Việc chọn bean cụ thể giúp tập phân giải thể hiện rõ phạm vi mà resolver được phép biết.

### 4.1. Dùng ToolCallbacks.from với POJO

Nếu công cụ được khai báo bằng phương thức `@Tool`, có thể chuyển POJO thành callback trước khi tạo resolver:

~~~java
ToolCallback[] callbacks = ToolCallbacks.from(inventoryTools);

ToolCallbackResolver resolver =
    new StaticToolCallbackResolver(
        List.of(callbacks)
    );
~~~

Nếu có nhiều POJO:

~~~java
List<ToolCallback> callbacks = new ArrayList<>();

callbacks.addAll(List.of(ToolCallbacks.from(inventoryTools)));
callbacks.addAll(List.of(ToolCallbacks.from(customerTools)));

ToolCallbackResolver resolver =
    new StaticToolCallbackResolver(callbacks);
~~~

Từ đây, resolver chỉ làm việc với `ToolCallback`. Nó không cần biết callback đến từ `@Tool`, `MethodToolCallback`, `FunctionToolCallback` hay implementation tùy chỉnh.

## 5. Resolver mặc định trong Spring Boot

Khi dùng Spring Boot auto-configuration của Spring AI 2.1.0, framework tự cấu hình `StaticToolCallbackResolver` với:

- Các bean kiểu `ToolCallback` trong application context.
- Các callback được tạo từ bean `ToolCallbackProvider`.

MCP provider được loại khỏi quá trình thu thập mặc định để tránh phải liệt kê công cụ từ máy chủ MCP quá sớm. Cách xử lý MCP có cơ chế riêng.

Với trường hợp thông thường, ứng dụng không cần tự tạo resolver bean. Chỉ cần khai báo callback hoặc provider bean, rồi cung cấp công cụ cho request theo cách phù hợp.

Ví dụ callback bean được inject vào request:

~~~java
String answer = chatClient.prompt()
    .user("Kiểm tra SKU-100 tại kho Hà Nội.")
    .tools(lookupInventory)
    .call()
    .content();
~~~

Trong trường hợp này, callback đã được gắn trực tiếp vào request. `ToolCallingManager` có thể tìm callback từ tập tool của request mà không cần dựa vào resolver fallback.

Nếu tự khai báo bean `ToolCallbackResolver`, ứng dụng thay thế chiến lược resolver mặc định. Khi làm vậy, phải bảo đảm registry mới chứa đủ callback mà ứng dụng dự định phân giải. Nếu muốn bao gồm callback được cung cấp từ provider, hãy chủ động đưa các callback đó vào tập mới; không giả định custom resolver tự kế thừa nội dung của resolver mặc định.

## 6. Phân biệt tool được gắn vào request và tool trong resolver

Đây là điểm quan trọng nhất khi dùng Spring AI 2.x.

`ChatClient` cho phép gắn tool trực tiếp:

~~~java
ChatClient client = ChatClient.builder(chatModel)
    .defaultTools(inventoryReadCallback)
    .build();

String answer = client.prompt()
    .user(question)
    .tools(customerReadCallback)
    .call()
    .content();
~~~

Trong 2.x, tool theo request được cộng thêm vào default tools của client. Tập tool cuối cùng được gửi đến mô hình là hợp của hai tập.

Resolver là một registry khác. Nó hỗ trợ tìm callback theo tên khi manager cần phân giải một tool call chưa có trong danh sách callback của request và fallback được bật.

| Trường hợp | Tool definition được gửi đến mô hình? | Có thể thực thi? |
|---|---|---|
| Callback được gắn trực tiếp qua `.tools(...)` | Có | Có |
| Callback được đăng ký qua `.defaultTools(...)` | Có | Có |
| Callback chỉ có trong resolver, fallback tắt | Không tự động | Không qua fallback |
| Callback chỉ có trong resolver, fallback bật | Resolver không tự gửi schema | Có thể được phân giải nếu mô hình trả về đúng tên |
| Callback không có trong request và cũng không có trong resolver | Không | Không |

Không nên dựa vào resolver để thay thế việc cung cấp tool definition. Mô hình cần biết tên, mô tả và schema để lựa chọn tool đáng tin cậy. Một tool chỉ tồn tại trong registry nhưng chưa được công bố có thể không được mô hình lựa chọn đúng.

## 7. Resolution fallback trong Spring AI 2.x

Trước Spring AI 2.0.1, nếu mô hình trả về tên tool không có trong callback list gắn với request, `DefaultToolCallingManager` có thể fallback sang `ToolCallbackResolver` toàn cục để tìm callback.

Từ 2.0.1, hành vi này bị tắt mặc định. Khi fallback tắt, chỉ các callback được gắn với request mới được phép thực thi qua vòng tool calling.

Có thể bật bằng property:

~~~yaml
spring:
  ai:
    tools:
      resolution:
        fallback:
          enabled: true
~~~

Hoặc khi tự tạo `ToolCallingManager`:

~~~java
ToolCallingManager toolCallingManager =
    ToolCallingManager.builder()
        .toolCallbackResolver(toolCallbackResolver)
        .resolutionFallbackEnabled(true)
        .build();
~~~

Mặc định của `resolutionFallbackEnabled` là `false`.

Khi bật fallback, nếu mô hình yêu cầu một tool không có trong tập callback của request, manager có thể gọi resolver để tìm callback theo tên. Cơ chế này hữu ích khi ứng dụng chủ động điều phối bằng tên tool và đã kiểm soát nguồn callback.

Tuy nhiên, fallback làm mọi callback có thể phân giải trở thành ứng viên thực thi nếu mô hình yêu cầu đúng tên, kể cả tool ghi dữ liệu hoặc thao tác phá hủy. Vì vậy, chỉ bật khi resolver được giới hạn rõ ràng và backend vẫn kiểm tra quyền ở thời điểm thực thi.

### 7.1. Khi nào nên bật fallback?

Có thể cân nhắc fallback nếu:

- Ứng dụng có một registry callback tĩnh đã được kiểm soát.
- Một lớp điều phối khác quyết định tên tool cần thực thi.
- Có cơ chế xác thực và phân quyền độc lập trong từng callback.
- Đã kiểm thử tình huống mô hình yêu cầu tên không nằm trong request callback list.

Giữ fallback tắt nếu:

- Tập tool phải thay đổi theo user hoặc tenant.
- Request chỉ được phép thực thi một allowlist rất nhỏ.
- Resolver toàn cục chứa tool nhạy cảm.
- Ứng dụng không có cách kiểm soát những tên tool mà mô hình có thể yêu cầu.

Với phần lớn ứng dụng, gắn callback tường minh bằng `.tools(...)` hoặc `.defaultTools(...)` giúp giới hạn tập tool của request dễ hiểu hơn.

## 8. Khác biệt giữa Spring AI 1.x và 2.x

`ToolCallbackResolver` và `StaticToolCallbackResolver` đã tồn tại từ Spring AI 1.0. Tuy nhiên, cách dùng resolver trong vòng tool calling đã thay đổi.

| Nội dung | Spring AI 1.0.x | Spring AI 2.x |
|---|---|---|
| StaticToolCallbackResolver | Tra cứu callback từ danh sách tĩnh | Vẫn dùng để tra cứu callback từ danh sách tĩnh |
| Default resolver | Thường dùng `DelegatingToolCallbackResolver` để phối hợp nhiều resolver | `StaticToolCallbackResolver` được auto-configure từ callback bean và provider |
| Bare Function/Supplier/Consumer/BiFunction bean | Có `SpringBeanToolCallbackResolver` để tìm theo tên | Cơ chế resolver bean thuần này bị loại bỏ |
| Đăng ký theo tên tool | Có các API theo tên như `toolNames(...)` | Ưu tiên đăng ký `ToolCallback` tường minh |
| Fallback resolver | Resolver được dùng trong luồng phân giải tên tool | Từ 2.0.1, fallback cho tool không gắn request mặc định tắt |

Trong Spring AI 1.0.x, default `DelegatingToolCallbackResolver` có thể kết hợp:

- `SpringBeanToolCallbackResolver`: tìm các bean hàm như `Function`, `Supplier`, `Consumer` và `BiFunction`.
- `StaticToolCallbackResolver`: tìm các `ToolCallback` đã đăng ký.

Từ Spring AI 2.0, mẫu `SpringBeanToolCallbackResolver` và cách đăng ký bare function bean bằng `toolNames(...)` bị loại bỏ. Hãy bọc hàm Java thành `FunctionToolCallback` và đăng ký callback tường minh.

Ví dụ:

~~~java
@Bean
ToolCallback lookupInventory(InventoryService inventoryService) {
    return FunctionToolCallback.builder(
            "lookupInventory",
            inventoryService::lookup
        )
        .description("Tra cứu tồn kho theo SKU và kho.")
        .inputType(InventoryQuery.class)
        .build();
}
~~~

Trong 2.x, bean này có thể được phát hiện bởi resolver tĩnh mặc định. Để mô hình sử dụng tool trong request thông thường, vẫn nên truyền callback qua `.tools(...)` hoặc `.defaultTools(...)`. Việc bean được phát hiện và việc tool được gắn vào request là hai việc khác nhau.

## 9. Khi nào cần custom ToolCallbackResolver?

`StaticToolCallbackResolver` phù hợp khi tập callback đã biết và không cần tra cứu nguồn dữ liệu ngoài. Nếu logic chọn callback phụ thuộc vào thông tin động, có thể triển khai `ToolCallbackResolver` riêng.

Ví dụ khái niệm:

~~~java
@Component
class AllowlistToolResolver implements ToolCallbackResolver {

    private final Map<String, ToolCallback> callbacks;

    AllowlistToolResolver(List<ToolCallback> allowedCallbacks) {
        this.callbacks = allowedCallbacks.stream()
            .collect(Collectors.toUnmodifiableMap(
                callback -> callback.getToolDefinition().name(),
                Function.identity()
            ));
    }

    @Override
    public ToolCallback resolve(String toolName) {
        return callbacks.get(toolName);
    }
}
~~~

Ví dụ này vẫn dùng tập callback đã biết, nhưng tự xây map bất biến để tra cứu. Nó không phải resolver theo tenant hoàn chỉnh; muốn phân quyền theo request thì cần đưa ngữ cảnh xác thực vào thiết kế resolver hoặc thực hiện kiểm tra trong callback.

Nếu phải truy vấn database, registry từ xa hoặc service discovery mỗi lần gọi, custom resolver có thể thực hiện việc đó. Khi ấy cần thêm timeout, cache, xử lý lỗi nguồn dữ liệu và giới hạn số lần tra cứu. Không nên biến resolver thành nơi thực hiện nghiệp vụ; resolver chỉ nên tìm implementation, còn callback xử lý thao tác.

Với danh sách tĩnh nhỏ hoặc vừa, `StaticToolCallbackResolver` đơn giản hơn và dễ kiểm thử hơn một resolver tùy chỉnh.

## 10. Kiểm soát bảo mật cho registry tĩnh

Một registry toàn cục có thể chứa callback có mức độ rủi ro khác nhau. Fallback khiến mọi callback có thể phân giải trở thành ứng viên thực thi, vì vậy không nên xem resolver như cơ chế phân quyền.

Một số nguyên tắc:

- Chỉ đưa callback cần thiết vào registry.
- Tách callback đọc dữ liệu khỏi callback ghi dữ liệu hoặc tạo giao dịch.
- Không đăng ký tool nhạy cảm vào resolver dùng chung nếu không có lý do rõ ràng.
- Kiểm tra user, tenant và quyền ở callback hoặc service nghiệp vụ.
- Lấy danh tính từ security context hoặc `ToolContext` do máy chủ cấp.
- Không tin tenant ID, user ID hoặc role do mô hình gửi trong JSON arguments.
- Đặt timeout, giới hạn số lần gọi và xử lý lỗi an toàn.
- Không ghi API key, token, dữ liệu cá nhân hoặc toàn bộ arguments nhạy cảm vào log.

Nếu danh sách tool phụ thuộc quyền người dùng, cách an toàn thường là xây dựng allowlist callback theo request và truyền tường minh cho `ChatClient`. Một static resolver toàn cục chỉ nên chứa các callback thực sự được phép phân giải trong phạm vi toàn ứng dụng.

## 11. Kiểm thử StaticToolCallbackResolver

Có thể kiểm thử resolver độc lập mà không cần gọi LLM. Các trường hợp cơ bản:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Tên tool có trong registry | Trả về đúng callback |
| Tên tool không có trong registry | Trả về `null` |
| Tên có khác biệt so với định nghĩa | Không giả định tìm được callback |
| Registry rỗng | Không tìm thấy callback nào |
| Hai callback trùng tên | Ứng dụng kiểm tra danh sách và từ chối cấu hình trước khi tạo resolver |
| Callback được chọn | `ToolCallingManager` gọi đúng callback |
| Fallback tắt | Tool không gắn vào request không được phân giải qua fallback |
| Fallback bật | Tool không gắn vào request có thể được tìm từ resolver |
| Callback không đủ quyền | Backend từ chối trước khi truy cập dữ liệu |

Ví dụ unit test:

~~~java
@Test
void resolvesKnownToolByName() {
    ToolCallback inventoryCallback = mock(ToolCallback.class);

    when(inventoryCallback.getToolDefinition())
        .thenReturn(ToolDefinition.builder()
            .name("lookupInventory")
            .description("Tra cứu tồn kho")
            .inputSchema("""
                {
                  "type": "object",
                  "properties": {
                    "sku": { "type": "string" }
                  },
                  "required": ["sku"]
                }
                """)
            .build());

    ToolCallbackResolver resolver =
        new StaticToolCallbackResolver(List.of(inventoryCallback));

    assertThat(resolver.resolve("lookupInventory"))
        .isSameAs(inventoryCallback);
}
~~~

Kiểm thử tên không tồn tại:

~~~java
@Test
void returnsNullForUnknownTool() {
    ToolCallbackResolver resolver =
        new StaticToolCallbackResolver(List.of());

    assertThat(resolver.resolve("unknownTool")).isNull();
}
~~~

Có thể kiểm thử fallback ở cấp `ToolCallingManager` hoặc integration test với cấu hình Spring Boot. Cần xác minh cả hai trạng thái:

- `spring.ai.tools.resolution.fallback.enabled=false`: chỉ callback được gắn vào request có thể được thực thi.
- `spring.ai.tools.resolution.fallback.enabled=true`: callback còn thiếu có thể được phân giải từ resolver.

Không cần gọi model thật cho unit test resolver. Dùng callback giả lập và tool call có tên/arguments xác định để kiểm tra chính xác nhánh phân giải.

## 12. Quy trình chọn cách phân giải

Có thể quyết định theo các câu hỏi sau:

1. Danh sách tool đã biết và ổn định? Dùng `StaticToolCallbackResolver`.
2. Muốn mô hình chỉ gọi các tool đã gắn vào request? Truyền callback bằng `.tools(...)` hoặc `.defaultTools(...)` và giữ fallback tắt.
3. Muốn manager phân giải tên tool chưa gắn vào request? Cấu hình resolver và bật fallback có kiểm soát.
4. Danh sách tool thay đổi theo user/tenant? Tạo allowlist theo request hoặc dùng resolver có ngữ cảnh và kiểm tra quyền.
5. Tool đến từ nguồn từ xa hoặc MCP? Dùng provider/resolver phù hợp, có timeout và bộ lọc trước khi đưa vào tập được phép.

`StaticToolCallbackResolver` là lựa chọn phù hợp khi ứng dụng đã biết trước tập callback cần hỗ trợ. Nó giúp tra cứu tên tool đơn giản, dễ kiểm thử và dễ kiểm soát. Tuy vậy, ứng dụng vẫn phải tách rõ việc công bố tool cho mô hình, việc phân giải callback và quyền thực thi callback trong từng request.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): ToolCallbackResolver, StaticToolCallbackResolver, registry mặc định, resolution fallback và vòng thực thi.
- [Spring AI 2.1.x — StaticToolCallbackResolver API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/resolution/StaticToolCallbackResolver.html): constructor nhận danh sách ToolCallback và phương thức resolve.
- [Spring AI 2.1.x — ToolCallbackResolver API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/resolution/ToolCallbackResolver.html): hợp đồng phân giải callback theo tên.
- [Spring AI 2.1.0 — Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html): thay đổi resolution fallback từ 2.0.1 và cách bật lại.
- [Spring AI 1.0.x — Tool Calling](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html): DelegatingToolCallbackResolver, StaticToolCallbackResolver và SpringBeanToolCallbackResolver trong 1.x.

Tên API và hành vi fallback phụ thuộc phiên bản. Hãy kiểm tra tài liệu đúng phiên bản BOM của dự án trước khi cấu hình resolver hoặc nâng cấp từ Spring AI 1.x.



