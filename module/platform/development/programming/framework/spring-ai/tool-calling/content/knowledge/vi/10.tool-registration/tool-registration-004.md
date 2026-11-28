# Kết hợp POJO, ToolCallback và ToolCallbackProvider theo API phiên bản

Spring AI cho phép đăng ký công cụ theo ba mức: truyền trực tiếp POJO có phương thức `@Tool`, truyền `ToolCallback` đã được tạo sẵn, hoặc gom nhiều callback thành một nguồn `ToolCallbackProvider`. Cả ba đều đưa về cùng hợp đồng: mô hình nhìn thấy tên, mô tả và input schema; ứng dụng chịu trách nhiệm thực thi callback và trả kết quả về cuộc hội thoại.

API đăng ký thay đổi giữa Spring AI 1.x và 2.x. Trong 1.x, `ChatClient` tách phương thức cho POJO (`tools`) và callback/provider (`toolCallbacks`). Từ 2.0, `tools(Object...)` và `defaultTools(Object...)` tiếp nhận thống nhất POJO, callback, provider, array và collection. Một số API cũ còn tồn tại trong 2.x nhưng đã deprecated.

Bài viết dùng ví dụ tra cứu tồn kho để giải thích vai trò của từng kiểu đăng ký, cách kết hợp chúng, cách chọn API theo phiên bản và các lưu ý về phạm vi công cụ, quyền truy cập, tên trùng lặp và kiểm thử.

## 1. Ba cách biểu diễn công cụ

### 1.1. POJO có phương thức @Tool

POJO là đối tượng Java thông thường. Một hoặc nhiều phương thức được đánh dấu bằng `@Tool` để Spring AI tạo callback tương ứng.

~~~java
@Component
public class InventoryTools {

    private final InventoryService inventoryService;

    public InventoryTools(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @Tool(
        name = "lookupInventory",
        description = "Tra cứu số lượng tồn kho của một SKU tại một kho."
    )
    public StockView lookupInventory(
            @ToolParam(description = "Mã SKU cần tra cứu") String sku,
            @ToolParam(description = "Mã kho, ví dụ HANOI") String warehouse) {

        return inventoryService.lookup(sku, warehouse);
    }
}
~~~

Khi truyền instance này vào `ChatClient`, Spring AI đọc các phương thức có `@Tool`, tạo định nghĩa và callback cho từng phương thức. Người viết ứng dụng không cần tự tạo `Method` hoặc dựng `ToolDefinition`.

POJO phù hợp khi ứng dụng sở hữu mã nguồn phương thức nghiệp vụ, muốn nhóm các tool liên quan trong cùng lớp và schema có thể suy ra từ chữ ký Java cùng annotation.

Một POJO có thể chứa nhiều phương thức `@Tool`. Mỗi phương thức trở thành một tool riêng; tên tool phải duy nhất trong tập công cụ được gửi đến mô hình.

### 1.2. ToolCallback

`ToolCallback` là hợp đồng thực thi ở mức thấp hơn. Nó đóng gói định nghĩa mà mô hình nhìn thấy và logic xử lý khi ứng dụng nhận yêu cầu gọi tool.

~~~java
public interface ToolCallback {

    ToolDefinition getToolDefinition();

    ToolMetadata getToolMetadata();

    String call(String toolInput);

    String call(String toolInput, ToolContext toolContext);
}
~~~

`ToolDefinition` chứa tên, mô tả và JSON input schema. `ToolMetadata` chứa metadata điều khiển cách framework xử lý kết quả, ví dụ có trả kết quả trực tiếp cho caller hay gửi lại cho mô hình.

Spring AI có sẵn các implementation như:

- `MethodToolCallback`: tạo callback từ một phương thức Java.
- `FunctionToolCallback`: tạo callback từ `Function`, `Supplier`, `Consumer` hoặc `BiFunction`.

Ứng dụng cũng có thể tự triển khai `ToolCallback` khi cần điều khiển đầy đủ việc gọi dịch vụ từ xa, chuyển đổi dữ liệu hoặc tích hợp hệ thống tool riêng.

Dùng callback trực tiếp khi callback đã được tạo ở lớp cấu hình hoặc module dùng chung, cần schema/metadata tùy chỉnh, muốn inject callback như Spring bean hoặc muốn kết hợp nhiều loại tool trong cùng request.

### 1.3. ToolCallbackProvider

`ToolCallbackProvider` là nguồn cung cấp một hoặc nhiều `ToolCallback`. Interface này có phương thức `getToolCallbacks()` để trả về các callback mà provider quản lý.

~~~java
public interface ToolCallbackProvider {
    ToolCallback[] getToolCallbacks();
}
~~~

Provider không thay thế callback; nó đóng vai trò tập hợp hoặc nguồn phân phối callback.

Spring AI cung cấp các implementation như:

- `MethodToolCallbackProvider`: tạo callback từ các đối tượng có phương thức `@Tool`.
- `StaticToolCallbackProvider`: giữ một tập callback tĩnh.
- Các provider MCP: lấy callback từ công cụ được công bố bởi MCP server.

Ví dụ tạo provider từ POJO:

~~~java
@Bean
ToolCallbackProvider inventoryToolProvider(InventoryTools inventoryTools) {
    return MethodToolCallbackProvider.builder()
        .toolObjects(inventoryTools)
        .build();
}
~~~

Provider hữu ích khi một nhóm công cụ cần được đóng gói và truyền như một đơn vị, hoặc khi nguồn công cụ được xác định tại thời điểm cấu hình.

## 2. Quan hệ giữa POJO, ToolCallback và ToolCallbackProvider

Ba kiểu này là ba mức biểu diễn và đóng gói của cùng một tập tool.

~~~mermaid
flowchart TD
    A["POJO có phương thức @Tool"] --> B["MethodToolCallbackProvider hoặc ToolCallbacks.from(...)"]
    B --> C["Một hoặc nhiều ToolCallback"]
    D["MethodToolCallback / FunctionToolCallback"] --> C
    E["Custom ToolCallback"] --> C
    C --> F["ToolCallbackProvider (tùy chọn để gom nhóm)"]
    C --> G["ChatClient"]
    F --> G
    A --> G
    G --> H["ToolCallingAdvisor / ToolCallingManager"]
    H --> I["Thực thi callback"]
    I --> J["Tool result"]
    J --> G
~~~

| Kiểu | Trách nhiệm | Ví dụ |
|---|---|---|
| POJO | Khai báo phương thức nghiệp vụ bằng annotation | `InventoryTools` |
| ToolCallback | Đại diện cho một tool có schema và logic thực thi | `MethodToolCallback` |
| ToolCallbackProvider | Cung cấp một tập callback | `MethodToolCallbackProvider` |
| ChatClient | Nhận các nguồn tool và gửi định nghĩa đến mô hình | `ChatClient` |
| ToolCallingManager | Tìm và thực thi callback khi có tool call | `ToolCallingManager` |

Một POJO có thể được Spring AI chuyển thành callback trực tiếp trong request. Nếu cần giữ callback để tái sử dụng, có thể dùng `ToolCallbacks.from(...)` hoặc `MethodToolCallbackProvider`. Nếu callback đã tồn tại, có thể đăng ký trực tiếp mà không cần bọc lại thành POJO.

## 3. Đăng ký POJO trực tiếp

Cách ngắn gọn nhất là truyền instance có phương thức `@Tool` trực tiếp cho `ChatClient`:

~~~java
String answer = chatClient.prompt()
    .user("Kiểm tra tồn kho SKU-100 tại kho Hà Nội.")
    .tools(inventoryTools)
    .call()
    .content();
~~~

Spring AI tạo callback từ các phương thức được đánh dấu `@Tool` trong `inventoryTools` và đưa định nghĩa tool vào request.

Nếu công cụ cần dữ liệu server-side như tenant ID, hãy truyền qua `toolContext`:

~~~java
String answer = chatClient.prompt()
    .user(question)
    .tools(inventoryTools)
    .toolContext(Map.of("tenantId", authenticatedTenantId))
    .call()
    .content();
~~~

`authenticatedTenantId` phải lấy từ principal hoặc security context đã xác thực. Không lấy giá trị này từ câu hỏi của người dùng hoặc yêu cầu mô hình tự sinh ra.

### 3.1. Đăng ký POJO làm công cụ mặc định

Nếu một nhóm tool luôn cần có mặt với mọi request của một `ChatClient`, có thể đăng ký ở cấp builder:

~~~java
ChatClient chatClient = ChatClient.builder(chatModel)
    .defaultTools(inventoryTools)
    .build();
~~~

Công cụ mặc định được chia sẻ bởi các request tạo từ builder đó. Đây là cách phù hợp cho tool đọc dữ liệu phổ biến, có quyền truy cập rộng và ít rủi ro.

Không nên đưa tool xóa dữ liệu, tạo giao dịch hoặc thao tác chỉ dành cho một vai trò thành default tool dùng chung. Với những công cụ như vậy, hãy kiểm tra quyền rồi mới cung cấp theo từng request.

## 4. Chuyển POJO thành callback tường minh

Khi muốn giữ callback để inject hoặc truyền qua nhiều lớp, dùng tiện ích `ToolCallbacks.from(...)`:

~~~java
ToolCallback[] inventoryCallbacks =
    ToolCallbacks.from(inventoryTools);
~~~

Mỗi phương thức `@Tool` tạo ra một callback trong mảng. Có thể truyền mảng này vào API đăng ký tool của `ChatClient`.

Nếu muốn đóng gói mảng callback thành provider:

~~~java
ToolCallbackProvider inventoryProvider =
    ToolCallbackProvider.from(inventoryCallbacks);
~~~

Hoặc dùng `MethodToolCallbackProvider` để tạo provider trực tiếp từ POJO:

~~~java
ToolCallbackProvider inventoryProvider =
    MethodToolCallbackProvider.builder()
        .toolObjects(inventoryTools)
        .build();
~~~

Cả hai cách đều trả về provider cung cấp các callback. `MethodToolCallbackProvider` phù hợp khi nguồn là các đối tượng có phương thức `@Tool`; `ToolCallbackProvider.from(...)` phù hợp khi callback đã được tạo sẵn.

### 4.1. Kết hợp nhiều POJO

Provider có thể nhận nhiều đối tượng tool:

~~~java
@Bean
ToolCallbackProvider businessToolProvider(
        InventoryTools inventoryTools,
        CustomerTools customerTools,
        OrderTools orderTools) {

    return MethodToolCallbackProvider.builder()
        .toolObjects(inventoryTools, customerTools, orderTools)
        .build();
}
~~~

Các phương thức `@Tool` trong các đối tượng được tổng hợp thành một tập callback. Trước khi đưa provider vào request, cần bảo đảm tên tool không trùng nhau.

Cách gom nhóm này phù hợp khi một trợ lý nghiệp vụ cần nhiều nhóm chức năng có ranh giới rõ ràng, ví dụ tra cứu sản phẩm, khách hàng và đơn hàng.

## 5. Đăng ký ToolCallback trực tiếp

Khi callback đã được tạo, truyền nó trực tiếp vào `ChatClient`.

Ví dụ tạo callback bằng `FunctionToolCallback`:

~~~java
public record InventoryQuery(
    String sku,
    String warehouse
) {}

@Bean
ToolCallback lookupInventoryCallback(InventoryService inventoryService) {
    return FunctionToolCallback.builder(
            "lookupInventory",
            (InventoryQuery query) ->
                inventoryService.lookup(query.sku(), query.warehouse())
        )
        .description("Tra cứu số lượng tồn kho theo SKU và kho.")
        .inputType(InventoryQuery.class)
        .build();
}
~~~

Inject callback vào nơi cần dùng:

~~~java
String answer = chatClient.prompt()
    .user(question)
    .tools(lookupInventoryCallback)
    .call()
    .content();
~~~

Callback có thể được đăng ký làm mặc định:

~~~java
ChatClient chatClient = ChatClient.builder(chatModel)
    .defaultTools(lookupInventoryCallback)
    .build();
~~~

Cách này hữu ích khi muốn công bố tool từ một service method hoặc lambda, đồng thời kiểm soát tên, mô tả, input type và schema.

Nếu dùng callback tự triển khai, cần bảo đảm tên tool duy nhất, input schema khớp dữ liệu mà `call(...)` xử lý, context được chuyển đúng cách, kết quả có định dạng phù hợp và exception được xử lý theo chính sách an toàn của ứng dụng.

## 6. Kết hợp POJO, ToolCallback và ToolCallbackProvider trong cùng request

Từ Spring AI 2.x, các API `tools(Object...)` và `defaultTools(Object...)` nhận nhiều kiểu biểu diễn tool. Có thể trộn POJO, callback và provider trong một lời gọi:

~~~java
String answer = chatClient.prompt()
    .user(question)
    .tools(
        inventoryTools,
        lookupInventoryCallback,
        customerToolProvider
    )
    .toolContext(Map.of("tenantId", authenticatedTenantId))
    .call()
    .content();
~~~

Trong ví dụ:

- `inventoryTools` là POJO chứa phương thức `@Tool`.
- `lookupInventoryCallback` là callback đã được tạo trước.
- `customerToolProvider` cung cấp một nhóm callback.
- `toolContext` truyền dữ liệu server-side cho lần thực thi.

Đây là cách đăng ký linh hoạt khi một request cần kết hợp công cụ từ nhiều nguồn. Tuy nhiên, tập tool cuối cùng vẫn cần được kiểm tra tên trùng lặp và quyền truy cập trước khi gửi cho mô hình.

## 7. Khác biệt API giữa Spring AI 1.x và 2.x

`ToolCallbackProvider` và `ToolCallback` đã có từ Spring AI 1.0. Khác biệt đáng chú ý nằm ở cách `ChatClient` tiếp nhận chúng và cách framework quản lý vòng thực thi tool.

### 7.1. Các phương thức đăng ký

| Nhu cầu | Spring AI 1.0.x | Spring AI 2.x |
|---|---|---|
| Truyền POJO có `@Tool` theo request | `tools(pojo)` | `tools(pojo)` |
| Truyền callback theo request | `toolCallbacks(callbacks)` | `tools(callbacks)` |
| Truyền provider theo request | `toolCallbacks(provider)` | `tools(provider)` |
| POJO mặc định | `defaultTools(pojo)` | `defaultTools(pojo)` |
| Callback/provider mặc định | `defaultToolCallbacks(...)` | `defaultTools(...)` |
| Kết hợp nhiều kiểu trong một lời gọi | Dùng phương thức theo từng loại | `tools(Object...)` hỗ trợ trộn POJO, callback, provider, array và collection |

Trong Spring AI 1.0.x, các API `toolCallbacks(...)` và `defaultToolCallbacks(...)` được dùng cho `ToolCallback` hoặc `ToolCallbackProvider`. POJO có `@Tool` vẫn được truyền qua `tools(...)` và `defaultTools(...)`.

Từ Spring AI 2.0, `tools(Object...)` và `defaultTools(Object...)` hợp nhất cách đăng ký. Có thể truyền nhiều loại tool trong cùng một lời gọi. Các phương thức `toolCallbacks(...)` và `defaultToolCallbacks(...)` được giữ lại trong một số bản 2.x để tương thích nhưng đã deprecated; nên ưu tiên API mới.

### 7.2. Khác biệt về hợp nhất tool mặc định và tool theo request

Đây là thay đổi ảnh hưởng trực tiếp đến cách thiết kế quyền:

- Trong Spring AI 1.0.x, nếu request cung cấp tool riêng, tập tool ở request có thể thay thế tập tool mặc định.
- Trong Spring AI 2.1.0, `.tools(...)` theo request được cộng thêm vào `.defaultTools(...)`. Tập tool cuối cùng là hợp của hai tập.

Ví dụ:

~~~java
ChatClient chatClient = ChatClient.builder(chatModel)
    .defaultTools(inventoryReadTools)
    .build();

String answer = chatClient.prompt()
    .user(question)
    .tools(orderWriteCallback)
    .call()
    .content();
~~~

Trong Spring AI 2.1.0, request trên có cả `inventoryReadTools` mặc định và `orderWriteCallback` theo request.

Điều này quan trọng khi kiểm soát công cụ theo vai trò. Nếu một tool nhạy cảm không được phép xuất hiện trong một số request, đừng đăng ký nó trong default tools của một client dùng chung. Hãy tạo client có tập default phù hợp hoặc quản lý tập tool theo ngữ cảnh trước khi gửi request.

### 7.3. Thay đổi từ Spring AI 1.x sang 2.x

| API hoặc hành vi cũ | Cách dùng trong 2.x |
|---|---|
| `toolCallbacks(...)` trên ChatClient request | Dùng `tools(...)` |
| `defaultToolCallbacks(...)` trên builder | Dùng `defaultTools(...)` |
| `tools(Consumer<ToolSpec>)` | Đã bị loại bỏ; truyền trực tiếp POJO, callback hoặc provider |
| `toolNames(...)` và `SpringBeanToolCallbackResolver` | Đã bị loại bỏ |
| Bare `Function` bean được tìm theo tên | Khai báo bean kiểu `ToolCallback`, ví dụ `FunctionToolCallback` |
| Vòng thực thi nội bộ của từng `ChatModel` | Dùng `ChatClient` với `ToolCallingAdvisor` hoặc tự điều phối bằng `ToolCallingManager` |

Trong 1.x, có thể khai báo một bean `Function` và để resolver tìm theo tên tool. Từ 2.0, cách này đã bị loại bỏ. Hãy tạo `FunctionToolCallback` tường minh rồi đăng ký callback.

Ví dụ migration:

~~~java
// Mẫu cũ ở 1.x: bean hàm thuần được tìm bằng toolNames(...)
@Bean
Function<InventoryQuery, StockView> lookupInventory(
        InventoryService inventoryService) {
    return inventoryService::lookup;
}
~~~

~~~java
// Mẫu 2.x: đăng ký ToolCallback tường minh
@Bean
ToolCallback lookupInventory(
        InventoryService inventoryService) {

    return FunctionToolCallback.builder(
            "lookupInventory",
            inventoryService::lookup
        )
        .description("Tra cứu tồn kho theo SKU và kho.")
        .inputType(InventoryQuery.class)
        .build();
}
~~~

Trong 2.x, inject callback và đưa vào request:

~~~java
String answer = chatClient.prompt()
    .user(question)
    .tools(lookupInventory)
    .call()
    .content();
~~~

### 7.4. ChatClient và ChatModel trực tiếp

Ở Spring AI 1.x, mỗi implementation `ChatModel` có thể tự quản lý vòng tool calling nội bộ. Từ 2.0, vòng thực thi này đã được đưa ra khỏi `ChatModel`.

Với 2.x:

- Dùng `ChatClient` để framework tự đăng ký `ToolCallingAdvisor` và thực thi vòng gọi tool.
- Nếu gọi `ChatModel.call(prompt)` trực tiếp, response có thể chứa yêu cầu gọi tool nhưng callback không tự chạy.
- Khi cần tự điều phối, ứng dụng phải kiểm tra tool call trong response và dùng `ToolCallingManager` để thực thi, sau đó gửi lịch sử hội thoại cập nhật cho mô hình.

Đừng bê nguyên ví dụ điều phối tool của 1.x sang 2.x mà không kiểm tra phiên bản. Việc chỉ truyền callback trong options của `ChatModel` không đồng nghĩa callback sẽ tự được thực thi trong 2.x.

## 8. ToolCallbackProvider trong ứng dụng Spring

Có thể khai báo provider thành bean để tái sử dụng:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryToolConfiguration {

    @Bean
    ToolCallbackProvider inventoryToolProvider(
            InventoryTools inventoryTools,
            CustomerTools customerTools) {

        return MethodToolCallbackProvider.builder()
            .toolObjects(inventoryTools, customerTools)
            .build();
    }
}
~~~

Ở Spring AI 2.x, inject provider vào client:

~~~java
@Configuration
class AssistantConfiguration {

    @Bean
    ChatClient inventoryAssistant(
            ChatClient.Builder builder,
            ToolCallbackProvider inventoryToolProvider) {

        return builder
            .defaultTools(inventoryToolProvider)
            .build();
    }
}
~~~

Nếu ứng dụng có nhiều provider, dùng tên bean hoặc `@Qualifier` để inject đúng nguồn:

~~~java
@Bean
ChatClient orderAssistant(
        ChatClient.Builder builder,
        @Qualifier("orderToolProvider") ToolCallbackProvider orderTools) {

    return builder
        .defaultTools(orderTools)
        .build();
}
~~~

Không nên tạo một provider khổng lồ chứa tất cả công cụ của mọi phân hệ nếu từng trợ lý chỉ cần một tập nhỏ. Nhóm provider theo chức năng giúp kiểm soát phạm vi tool, dễ kiểm thử và tránh gửi quá nhiều schema cho mô hình.

### 8.1. Provider và ToolCallbackResolver

`ToolCallbackResolver` là cơ chế phân giải callback theo tên tool. Spring AI có thể tạo resolver từ các bean `ToolCallback` và các `ToolCallbackProvider` trong application context.

Cần phân biệt hai hành vi:

- Đăng ký callback/provider như bean giúp ứng dụng quản lý và tái sử dụng chúng.
- Đưa callback/provider vào `.tools(...)` hoặc `.defaultTools(...)` mới xác định tập tool gắn với request theo cách tường minh.

Trong Spring AI 2.0.1 trở đi, cơ chế fallback phân giải tool từ toàn bộ resolver khi tool không được gắn vào request bị tắt mặc định. Vì vậy, không nên giả định rằng chỉ cần khai báo `ToolCallback` bean là mọi request đều có thể gọi nó.

Có thể bật fallback qua `spring.ai.tools.resolution.fallback.enabled=true`, nhưng khi đó mọi tool có thể phân giải từ resolver đều có nguy cơ được gọi nếu mô hình yêu cầu đúng tên. Chỉ bật khi resolver đã giới hạn chặt chẽ theo quyền và ngữ cảnh. Với ứng dụng thông thường, đăng ký tool rõ ràng theo request hoặc client dễ kiểm soát hơn.

## 9. Quy tắc thiết kế khi kết hợp nhiều nguồn tool

### 9.1. Không trùng tên tool

Tên tool là định danh mà mô hình dùng để yêu cầu thao tác. Hai callback có cùng tên trong một tập tool sẽ gây mơ hồ.

Ví dụ không nên tạo:

~~~java
ToolCallback inventoryBySku = ...;  // name = lookupInventory
ToolCallback inventoryByCode = ...; // name = lookupInventory
~~~

Hãy đặt tên riêng theo hành động hoặc phạm vi:

- `lookupInventoryBySku`
- `lookupInventoryByWarehouse`
- `searchInventory`

Khi kết hợp POJO, callback và provider, kiểm tra tên trên tập đã hợp nhất, không chỉ kiểm tra riêng từng nguồn. `ChatClient` 2.1.0 kiểm tra tên trùng trong tập tool được đăng ký và báo lỗi khi có xung đột.

### 9.2. Giới hạn công cụ theo request

Chỉ cung cấp những tool cần cho tác vụ hiện tại. Ví dụ:

- Trợ lý tra cứu chỉ nhận tool đọc dữ liệu.
- Trợ lý quản lý đơn chỉ nhận tool xem và cập nhật đơn phù hợp với quyền người dùng.
- Tool thanh toán hoặc xóa dữ liệu chỉ được cung cấp sau bước kiểm tra quyền và xác nhận.

Định nghĩa tool được gửi cho mô hình không phải ranh giới bảo mật. Backend vẫn phải kiểm tra quyền ở mỗi lần thực thi, kể cả khi callback đã được chọn từ một provider tin cậy.

### 9.3. Không lưu trạng thái request trong singleton tool

Các POJO được quản lý bởi Spring thường là singleton. Không lưu tenant ID, user ID hoặc thông tin request vào field có thể bị chia sẻ giữa nhiều request.

Truyền dữ liệu request bằng `ToolContext`:

~~~java
String answer = chatClient.prompt()
    .user(question)
    .tools(inventoryTools)
    .toolContext(Map.of(
        "tenantId", authenticatedTenantId,
        "userId", authenticatedUserId
    ))
    .call()
    .content();
~~~

Method `@Tool` nhận `ToolContext` để lấy dữ liệu đó. Context phải do ứng dụng tạo từ danh tính đã xác thực; không lấy từ JSON arguments mà mô hình sinh ra.

### 9.4. Chọn cách đăng ký phù hợp

| Tình huống | Cách phù hợp |
|---|---|
| Một vài phương thức nghiệp vụ trong module | POJO có `@Tool` |
| Callback có schema hoặc metadata riêng | `ToolCallback` |
| Một nhóm POJO cần gom thành nguồn dùng chung | `MethodToolCallbackProvider` |
| Đã có sẵn danh sách callback | `ToolCallbackProvider.from(...)` hoặc mảng callback |
| Nguồn tool từ MCP server | MCP `ToolCallbackProvider`, đăng ký tường minh |
| Tool thay đổi theo người dùng/request | Tạo tập callback/provider sau khi kiểm tra quyền rồi truyền theo request |

## 10. Kiểm thử đăng ký tool

Kiểm thử nên xác minh cả việc tạo callback lẫn tập tool cuối cùng mà request sử dụng.

| Trường hợp | Nội dung cần xác minh |
|---|---|
| POJO có một phương thức `@Tool` | Tạo đúng một callback với tên và mô tả mong đợi |
| POJO có nhiều phương thức | Mỗi phương thức tạo một callback |
| POJO không có `@Tool` | Provider báo lỗi cấu hình rõ ràng |
| ToolCallback bean | Bean được inject đúng và có ToolDefinition hợp lệ |
| ToolCallbackProvider | `getToolCallbacks()` trả về đúng tập callback |
| Nhiều nguồn tool | Tập callback được hợp nhất đúng theo API phiên bản |
| Tên trùng | Đăng ký bị từ chối hoặc phát hiện trước khi gọi mô hình |
| Tool theo quyền | Người dùng không có quyền không nhận được tool nhạy cảm |
| ToolContext | Context server-side được truyền đến callback |
| API theo version | Dùng đúng phương thức 1.x hoặc 2.x, không còn API deprecated/removed |

Ví dụ kiểm tra provider:

~~~java
@Test
void providerContainsInventoryTool() {
    ToolCallbackProvider provider =
        MethodToolCallbackProvider.builder()
            .toolObjects(new InventoryTools(inventoryService))
            .build();

    ToolCallback[] callbacks = provider.getToolCallbacks();

    assertThat(callbacks)
        .extracting(callback -> callback.getToolDefinition().name())
        .contains("lookupInventory");
}
~~~

Ví dụ kiểm tra callback đã được tạo từ POJO:

~~~java
@Test
void pojoCreatesExpectedCallbacks() {
    ToolCallback[] callbacks = ToolCallbacks.from(inventoryTools);

    assertThat(callbacks)
        .extracting(callback -> callback.getToolDefinition().name())
        .contains("lookupInventory");
}
~~~

Ngoài kiểm thử đơn vị, có thể dùng model giả lập để kiểm tra request chứa đúng tập tool. Không cần gọi provider AI thật trong mỗi lần chạy test. Smoke test với provider thật nên tách riêng để xác minh khả năng tương thích tool calling.

## 11. Checklist khi nâng cấp và triển khai

- [ ] Xác nhận phiên bản Spring AI đang được quản lý bởi BOM.
- [ ] Dùng `tools(...)` cho POJO trong cả 1.x và 2.x.
- [ ] Với 1.x, dùng `toolCallbacks(...)` cho callback/provider.
- [ ] Với 2.x, ưu tiên `tools(Object...)` cho POJO, callback và provider.
- [ ] Với builder, dùng `defaultToolCallbacks(...)` trong 1.x và `defaultTools(...)` trong 2.x.
- [ ] Chuyển bare `Function` bean và `toolNames(...)` sang `ToolCallback` tường minh khi nâng cấp lên 2.x.
- [ ] Không nhầm lẫn bean discovery với việc gắn tool vào request.
- [ ] Kiểm tra quy tắc hợp nhất default tools và request tools theo phiên bản.
- [ ] Đảm bảo tên tool duy nhất trong tập đã hợp nhất.
- [ ] Không đăng ký tool nhạy cảm làm mặc định cho mọi request.
- [ ] Truyền tenant/user context từ nguồn server-side đáng tin cậy.
- [ ] Kiểm thử quyền truy cập và tập tool thực tế trước khi triển khai.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): POJO, ToolCallback, ToolCallbackProvider, đăng ký theo request và default tools.
- [Spring AI 2.1.0 — Tool Specification Reference](https://docs.spring.io/spring-ai/reference/api/tools.html#tool-specification-reference): hợp đồng callback, tool definition, metadata và tool resolution.
- [Spring AI 2.1.0 — Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html): API bị loại bỏ, thay đổi resolver và migration từ 1.x.
- [Spring AI 1.0.9 — Tool Calling](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html): các API `tools`, `toolCallbacks`, `defaultTools` và `defaultToolCallbacks` trong 1.0.x.
- [ToolCallbackProvider API — 1.0.x](https://docs.spring.io/spring-ai/docs/1.0.x/api/org/springframework/ai/tool/ToolCallbackProvider.html): hợp đồng provider và factory `from(...)`.
- [MethodToolCallbackProvider API — 2.1.x](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/method/MethodToolCallbackProvider.html): provider tạo callback từ các phương thức `@Tool`.

Hãy chọn cách đăng ký theo phiên bản Spring AI mà dự án đang dùng. Dù tool được khai báo bằng POJO, callback hay provider, ứng dụng vẫn cần quản lý tập công cụ được phép, kiểm tra quyền ở backend và xác minh schema trước khi gửi request đến mô hình.

