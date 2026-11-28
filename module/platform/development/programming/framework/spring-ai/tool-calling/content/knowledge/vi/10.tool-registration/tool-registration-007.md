# Phát hiện trùng tên giữa nhiều nguồn công cụ

Trong Spring AI, mô hình gọi công cụ bằng tên được công bố trong `ToolDefinition`. Khi ứng dụng kết hợp công cụ từ nhiều nguồn như phương thức `@Tool`, `FunctionToolCallback`, callback tự triển khai và MCP server, tất cả tên công cụ cùng xuất hiện trong một request phải duy nhất. Nếu hai callback cùng công bố tên `search`, mô hình không có cách phân biệt callback nào cần được thực thi.

Vấn đề không phụ thuộc vào hai callback có cùng lớp Java hay không. Hai callback khác implementation, khác schema hoặc đến từ hai MCP server khác nhau vẫn xung đột nếu `getToolDefinition().name()` trả về cùng một chuỗi. Vì vậy, cần kiểm tra tên hiệu lực sau khi các nguồn đã tạo callback và trước khi đưa tập callback vào `ChatClient` hoặc `ChatModel`.

## Vì sao trùng tên gây lỗi?

Tên công cụ là khóa định tuyến khi Spring AI nhận tool call từ mô hình. Mô hình trả về tên cùng JSON arguments; `ToolCallingManager` dùng tên đó để tìm callback tương ứng. Nếu có hai callback cùng tên, việc định tuyến trở nên mơ hồ.

Ví dụ hai nhóm nghiệp vụ cùng khai báo phương thức `search`:

```java
class CustomerTools {
    @Tool(description = "Tìm khách hàng theo tên hoặc email")
    public String search(String query) {
        return "Kết quả khách hàng";
    }
}

class ProductTools {
    @Tool(description = "Tìm sản phẩm theo tên hoặc SKU")
    public String search(String query) {
        return "Kết quả sản phẩm";
    }
}
```

Nếu không đặt tên rõ ràng, cả hai công cụ có thể cùng dùng tên mặc định `search`. Mô hình không thể chọn một trong hai bằng cách dựa vào kiểu Java hoặc tên class. Nó chỉ gửi tên công cụ mà nó đã nhận trong định nghĩa.

Đặt tên rõ ràng ngay ở nơi khai báo:

```java
class CustomerTools {
    @Tool(name = "customers_search", description = "Tìm khách hàng theo tên hoặc email")
    public String search(String query) {
        return "Kết quả khách hàng";
    }
}

class ProductTools {
    @Tool(name = "products_search", description = "Tìm sản phẩm theo tên hoặc SKU")
    public String search(String query) {
        return "Kết quả sản phẩm";
    }
}
```

Tên mới thể hiện cả miền nghiệp vụ và hành động. Mô hình có thể chọn đúng công cụ, log cũng dễ đọc hơn, và người phát triển dễ tìm nguồn tạo callback.

## Các nguồn có thể tạo ra tên trùng

Một tập công cụ của request có thể được lắp ghép từ nhiều kiểu khai báo:

| Nguồn | Cách tạo tên | Ví dụ xung đột |
| --- | --- | --- |
| Đối tượng có phương thức `@Tool` | Dùng `name` trong annotation; nếu bỏ qua thì dùng tên phương thức | Hai class đều có method `search`. |
| `FunctionToolCallback` | Tên truyền vào `FunctionToolCallback.builder(name, function)` | Hai bean function đều đăng ký `lookup`. |
| Custom `ToolCallback` | Tên trả về từ `getToolDefinition().name()` | Callback nội bộ và callback adapter cùng dùng `getCustomer`. |
| `ToolCallbackProvider` | Tên trong từng callback mà provider trả về | Hai provider cung cấp callback `search`. |
| MCP server | Tên tool do MCP server công bố và callback adapter giữ lại | Hai server đều công bố tool `search`. |

Một lỗi thường gặp là mỗi nhóm được phát triển và kiểm thử riêng nên tên không trùng trong phạm vi cục bộ. Khi ứng dụng ghép các nhóm thành một request, xung đột mới xuất hiện. Hãy xem danh sách công cụ cuối cùng mà request sẽ sử dụng, không chỉ xem từng class riêng lẻ.

## Những điểm cần kiểm tra trong Spring AI 1.0.x

Spring AI yêu cầu tên công cụ duy nhất trong toàn bộ tập công cụ cung cấp cho một chat request. `ToolCallingChatOptions` có phương thức `validateToolCallbacks(...)` để kiểm tra một danh sách callback. MCP `SyncMcpToolCallbackProvider` và `AsyncMcpToolCallbackProvider` cũng kiểm tra tên trùng khi tổng hợp công cụ từ các MCP client; provider đồng bộ ném `IllegalStateException` nếu phát hiện tên trùng giữa các server.

Với `ChatClient` trong Spring AI 1.0.x, công cụ runtime được truyền vào request sẽ thay thế tập công cụ mặc định của builder khi cả hai cùng được cấu hình. Đừng giả định hai tập mặc định và runtime luôn được hợp nhất. Tuy nhiên, một request vẫn có thể có tên trùng khi chính tập runtime được ghép từ nhiều nguồn, hoặc khi ứng dụng tự tổng hợp các callback trước khi đăng ký.

Khi gọi `ChatModel` trực tiếp, ứng dụng thường tự tạo `ToolCallingChatOptions`. Hãy kiểm tra danh sách callback sau khi đã hợp nhất các nguồn và trước khi gửi prompt. Không nên dựa vào việc một provider hoặc model cụ thể có thể phát hiện trùng tên ở thời điểm nào đó; kiểm tra tập callback tại ranh giới đăng ký giúp lỗi được phát hiện sớm và có thông tin nguồn rõ ràng.

## Thu thập callback từ nhiều nguồn

Ví dụ dưới đây lấy callback từ hai nhóm `@Tool`, một function callback và một MCP provider. Mỗi nguồn được gắn nhãn để thông báo lỗi có thể chỉ ra nơi tạo callback.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.ai.support.ToolCallbacks;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.ToolCallbackProvider;

record ToolSource(String sourceName, List<ToolCallback> callbacks) {}

List<ToolSource> sources = List.of(
        new ToolSource("customer-tools", Arrays.asList(ToolCallbacks.from(new CustomerTools()))),
        new ToolSource("product-tools", Arrays.asList(ToolCallbacks.from(new ProductTools()))),
        new ToolSource("inventory-function", List.of(inventoryCallback)),
        new ToolSource("mcp-provider", Arrays.asList(mcpToolCallbackProvider.getToolCallbacks()))
);
```

`ToolCallbacks.from(...)` chuyển các phương thức `@Tool` thành `ToolCallback`. Function callback có thể được tạo bằng `FunctionToolCallback.builder(...)`. Provider như MCP trả về mảng callback qua `getToolCallbacks()`.

Lưu ý: nếu một `ToolCallbackProvider` tự phát hiện tên trùng trong nội bộ, lời gọi `getToolCallbacks()` có thể ném lỗi trước khi danh sách được chuyển đến bước kiểm tra chung. Với MCP provider, trường hợp này xảy ra khi hai MCP server được tổng hợp và cùng công bố một tên. Phần xử lý MCP ở phía dưới trình bày cách lọc hoặc đổi tên trước khi tổng hợp.

## Viết bước kiểm tra trùng tên có thông tin nguồn

Có thể tự kiểm tra danh sách callback bằng `getToolDefinition().name()`. Hàm sau vừa phát hiện tên trùng vừa liệt kê nguồn đã đăng ký tên đó:

```java
static List<ToolCallback> flattenAndValidate(List<ToolSource> sources) {
    List<ToolCallback> callbacks = new ArrayList<>();
    Map<String, List<String>> originsByName = new LinkedHashMap<>();

    for (ToolSource source : sources) {
        for (ToolCallback callback : source.callbacks()) {
            String toolName = callback.getToolDefinition().name();

            originsByName.computeIfAbsent(toolName, key -> new ArrayList<>())
                    .add(source.sourceName() + "/" + callback.getClass().getSimpleName());
            callbacks.add(callback);
        }
    }

    List<String> duplicates = originsByName.entrySet().stream()
            .filter(entry -> entry.getValue().size() > 1)
            .map(entry -> entry.getKey() + " <- " + String.join(", ", entry.getValue()))
            .toList();

    if (!duplicates.isEmpty()) {
        throw new IllegalStateException(
                "Trùng tên tool trong tập đăng ký: " + String.join("; ", duplicates));
    }

    return List.copyOf(callbacks);
}
```

Sử dụng kết quả đã kiểm tra để đăng ký công cụ:

```java
List<ToolCallback> callbacks = flattenAndValidate(sources);

// Lớp kiểm tra của Spring AI là một hàng rào bổ sung cho danh sách callback.
ToolCallingChatOptions.validateToolCallbacks(callbacks);

String answer = chatClient.prompt()
        .user("Tìm khách hàng và kiểm tra sản phẩm liên quan")
        .toolCallbacks(callbacks.toArray(ToolCallback[]::new))
        .call()
        .content();
```

Kiểm tra riêng giúp thông báo lỗi chứa cả tên nguồn, trong khi `ToolCallingChatOptions.validateToolCallbacks(...)` là kiểm tra bổ sung của Spring AI. Nên gọi hàm kiểm tra ở lúc khởi tạo cấu hình hoặc xây dựng tool set, không đợi đến khi người dùng gửi request đầu tiên.

## Tách tên theo miền nghiệp vụ

Giải pháp đơn giản nhất là đặt tên tường minh và thống nhất quy ước. Một số mẫu thường dùng:

| Nhóm nghiệp vụ | Mẫu tên | Ví dụ |
| --- | --- | --- |
| Khách hàng | `customers_<action>` | `customers_search`, `customers_get` |
| Đơn hàng | `orders_<action>` | `orders_search`, `orders_cancel` |
| Kho hàng | `inventory_<action>` | `inventory_lookup`, `inventory_reserve` |
| Thanh toán | `payments_<action>` | `payments_get_status`, `payments_refund` |
| Tìm kiếm từ MCP server | `<server>_<action>` | `crm_search`, `catalog_search` |

Với `@Tool`, khai báo `@Tool(name = "orders_get")`. Với function callback, truyền tên có namespace vào builder:

```java
ToolCallback inventoryLookup = FunctionToolCallback
        .builder("inventory_lookup", inventoryService::lookup)
        .description("Tra cứu tồn kho theo mã SKU")
        .inputType(InventoryRequest.class)
        .build();
```

Tên cần ngắn, ổn định và có nghĩa. Không dùng tên class Java làm namespace ngầm vì mô hình chỉ nhìn thấy tên tool công bố; đổi class không nên vô tình đổi contract.

## Xử lý xung đột từ nhiều MCP server

MCP server là nguồn công cụ độc lập. Hai server có thể cùng cung cấp tên phổ biến như `search`, `read_file` hoặc `get_status`. Trong Spring AI 1.0.9, `SyncMcpToolCallbackProvider` có constructor nhận một `BiPredicate<McpSyncClient, McpSchema.Tool>` để lọc tool trong lúc discovery. Có thể chọn một nguồn sở hữu tên bị trùng:

```java
Set<String> namesOwnedByLocalTools = Set.of("search");

ToolCallbackProvider mcpProvider = new SyncMcpToolCallbackProvider(
        (client, tool) -> !namesOwnedByLocalTools.contains(tool.name()),
        mcpSyncClients);

ToolCallback[] mcpCallbacks = mcpProvider.getToolCallbacks();
```

Trong ví dụ, công cụ `search` do local tool đảm nhiệm nên mọi MCP tool cùng tên bị loại khỏi provider. Các tool MCP có tên khác vẫn được giữ lại. Nếu muốn giữ một trong nhiều MCP tool trùng tên, predicate có thể kiểm tra client cụ thể và chỉ nhận tool từ server được chọn.

Nếu cần sử dụng tất cả công cụ trùng tên từ các MCP server, có thể tạo provider riêng cho từng client, lấy callback riêng rồi bọc callback để đổi tên hiển thị trước khi hợp nhất. Wrapper chỉ đổi `ToolDefinition.name()`; lời gọi thực thi vẫn được chuyển đến callback gốc:

```java
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.ai.tool.metadata.ToolMetadata;

final class NamespacedToolCallback implements ToolCallback {

    private final ToolCallback delegate;
    private final ToolDefinition definition;

    NamespacedToolCallback(String prefix, ToolCallback delegate) {
        this.delegate = delegate;
        ToolDefinition original = delegate.getToolDefinition();
        this.definition = ToolDefinition.builder()
                .name(prefix + "_" + original.name())
                .description(original.description())
                .inputSchema(original.inputSchema())
                .build();
    }

    @Override
    public ToolDefinition getToolDefinition() {
        return this.definition;
    }

    @Override
    public ToolMetadata getToolMetadata() {
        return this.delegate.getToolMetadata();
    }

    @Override
    public String call(String toolInput) {
        return this.delegate.call(toolInput);
    }

    @Override
    public String call(String toolInput, ToolContext toolContext) {
        return this.delegate.call(toolInput, toolContext);
    }
}
```

Ví dụ, callback `search` từ server CRM có thể được công bố thành `crm_search`, còn callback từ server catalog thành `catalog_search`. Không dùng cách đổi tên này để che giấu một xung đột chưa hiểu rõ: hãy kiểm tra hai công cụ có thật sự khác mục đích, schema và quyền truy cập hay không. Nếu chúng thực chất là cùng một chức năng, nên chọn một nguồn duy nhất.

Lưu ý rằng provider được tạo từ nhiều MCP client có thể tự kiểm tra tên trùng trước khi trả callback. Vì vậy, nếu dùng wrapper để giữ cả hai công cụ, hãy lấy callback từ từng client riêng biệt trước khi đổi tên; không gọi một provider tổng hợp đã thất bại do trùng tên rồi mới mong bọc được kết quả.

## Phân biệt lỗi nội bộ provider và lỗi khi ghép toàn request

Có hai thời điểm phát hiện xung đột:

1. **Trong một provider:** provider tự tổng hợp nhiều nguồn con và phát hiện tên trùng ngay khi `getToolCallbacks()` chạy. Ví dụ `SyncMcpToolCallbackProvider` phát hiện hai MCP server cùng công bố `search` và ném `IllegalStateException`.
2. **Giữa các provider/nguồn đã tách riêng:** mỗi nguồn tạo callback thành công, nhưng ứng dụng ghép các callback vào một tập chung. Bước kiểm tra `flattenAndValidate(...)` phát hiện tên trùng trước khi gọi model.

Phân biệt hai trường hợp giúp tìm đúng nơi cần sửa. Nếu lỗi phát sinh trong MCP provider, kiểm tra danh sách MCP client và bộ lọc discovery. Nếu lỗi chỉ xuất hiện sau khi hợp nhất, kiểm tra các nhóm `@Tool`, function callback, custom callback và provider đang cùng được gắn vào request.

## Tránh hiểu nhầm về default tools và runtime tools

Trong Spring AI 1.0.x, nếu cấu hình công cụ mặc định trên `ChatClient.Builder` và đồng thời truyền công cụ runtime cho một request, tập runtime thay thế tập mặc định cho request đó. Cơ chế này không có nghĩa mọi nguồn callback trong ứng dụng tự động được nối vào nhau.

```java
ChatClient client = ChatClient.builder(chatModel)
        .defaultToolCallbacks(commonTools.toArray(ToolCallback[]::new))
        .build();

// Request này dùng runtimeTools thay cho commonTools theo semantics 1.0.x.
String answer = client.prompt()
        .user("Tra cứu đơn hàng")
        .toolCallbacks(runtimeTools.toArray(ToolCallback[]::new))
        .call()
        .content();
```

Nếu request cần cả công cụ mặc định và công cụ runtime, hãy chủ động tạo một danh sách cuối cùng gồm tất cả callback cần thiết, kiểm tra tên duy nhất rồi truyền danh sách đó theo đúng cách đăng ký của phiên bản đang dùng. Đừng trông chờ vào việc builder tự ghép hai danh sách.

## Kiểm thử tên công cụ

Nên kiểm tra tool set như một phần của kiểm thử cấu hình ứng dụng. Một test đơn giản có thể xác nhận tên sau khi hợp nhất:

```java
@Test
void toolNamesMustBeUniqueAcrossSources() {
    List<ToolSource> sources = List.of(
            new ToolSource("orders", Arrays.asList(ToolCallbacks.from(new OrderTools()))),
            new ToolSource("inventory", Arrays.asList(ToolCallbacks.from(new InventoryTools())))
    );

    List<ToolCallback> callbacks = flattenAndValidate(sources);

    assertThat(callbacks)
            .extracting(callback -> callback.getToolDefinition().name())
            .doesNotHaveDuplicates();
}
```

Ngoài ca thành công, cần có test xác nhận lỗi nêu đúng tên và nguồn xung đột:

```java
@Test
void duplicateToolNamesReportTheirSources() {
    List<ToolSource> sources = List.of(
            new ToolSource("customers", List.of(customerSearchCallback)),
            new ToolSource("catalog", List.of(catalogSearchCallback))
    );

    assertThatThrownBy(() -> flattenAndValidate(sources))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("search")
            .hasMessageContaining("customers")
            .hasMessageContaining("catalog");
}
```

Các tình huống nên kiểm thử:

- Hai `@Tool` class có cùng tên phương thức mặc định.
- Hai `FunctionToolCallback` được tạo với cùng tên.
- Custom `ToolCallback` trùng tên với callback sinh từ annotation.
- Hai `ToolCallbackProvider` cùng trả về một tên.
- Hai MCP server cùng công bố một tool name.
- Bộ lọc MCP loại đúng nguồn bị xung đột.
- Wrapper đổi tên vẫn chuyển `call(...)`, `ToolContext` và `ToolMetadata` đến callback gốc.
- Danh sách công cụ cuối cùng không trùng tên trước khi gửi request.

Không chỉ kiểm tra số lượng callback. Hai callback có thể khác object nhưng cùng tên. Hãy lấy tên từ `getToolDefinition().name()` vì đó là tên thực tế mô hình và bộ điều phối sử dụng.

## Quy trình xử lý khi gặp lỗi trùng tên

1. Lấy tên bị trùng từ thông báo lỗi hoặc duyệt toàn bộ callback trong tool set.
2. Gắn nhãn nguồn cho từng callback: class `@Tool`, function bean, custom callback hay MCP connection.
3. Xác định hai công cụ có cùng mục đích hay là hai chức năng độc lập.
4. Nếu cùng chức năng, chọn một nguồn sở hữu và bỏ nguồn còn lại.
5. Nếu khác chức năng, đặt tên tường minh theo namespace nghiệp vụ hoặc bọc callback để đổi tên.
6. Với MCP provider, xử lý xung đột trong bước discovery bằng filter hoặc tách provider theo từng client trước khi đổi tên.
7. Chạy kiểm tra uniqueness ở startup và unit test để ngăn xung đột quay lại.

Tên công cụ duy nhất giúp mô hình chọn đúng hành động và giúp `ToolCallingManager` định tuyến lời gọi chính xác. Khi ứng dụng có nhiều nguồn công cụ, một bước kiểm tra tập callback cuối cùng cùng quy ước namespace rõ ràng sẽ giúp phát hiện xung đột sớm, giải thích được nguồn gốc và tránh thực thi nhầm công cụ.

## Tài liệu tham khảo

- [Spring AI 1.0.9 Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html)
- [Spring AI 1.0.9 API — ToolCallingChatOptions](https://docs.spring.io/spring-ai/docs/1.0.x/api/org/springframework/ai/model/tool/ToolCallingChatOptions.html)
- [Spring AI 1.0.9 API — ToolCallbacks](https://docs.spring.io/spring-ai/docs/1.0.x/api/org/springframework/ai/support/ToolCallbacks.html)
- [Spring AI 1.0.9 API — SyncMcpToolCallbackProvider](https://docs.spring.io/spring-ai/docs/1.0.x/api/org/springframework/ai/mcp/SyncMcpToolCallbackProvider.html)
- [Spring AI 1.0.9 API — ToolCallback](https://docs.spring.io/spring-ai/docs/1.0.x/api/org/springframework/ai/tool/ToolCallback.html)
- [Spring AI 1.0.9 API — ToolDefinition](https://docs.spring.io/spring-ai/docs/1.0.x/api/org/springframework/ai/tool/definition/ToolDefinition.html)
