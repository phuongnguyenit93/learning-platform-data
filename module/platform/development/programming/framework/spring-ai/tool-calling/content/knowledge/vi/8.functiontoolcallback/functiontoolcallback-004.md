# Cung cấp tên, mô tả và schema đầu vào

**FunctionToolCallback** cho phép công bố một hàm Java như một công cụ mà mô hình có thể yêu cầu ứng dụng thực thi. Khi tạo callback, ứng dụng cần cung cấp ba thông tin quan trọng: tên tool, mô tả mục đích và schema đầu vào. Spring AI đóng gói các thông tin đó thành **ToolDefinition**, sau đó liên kết definition với function thực thi.

Tên giúp hệ thống nhận diện chính xác công cụ. Mô tả giúp mô hình hiểu lúc nào nên gọi và cần dùng công cụ cho việc gì. Schema cho mô hình biết phải gửi những trường nào, kiểu dữ liệu nào và trường nào bắt buộc. Ba phần này tạo thành hợp đồng giữa mô hình và ứng dụng.

## 1. FunctionToolCallback nằm ở đâu trong tool calling?

Spring AI hỗ trợ nhiều cách định nghĩa tool. **@Tool** phù hợp khi muốn đánh dấu trực tiếp một phương thức; **MethodToolCallback** phù hợp khi cần tạo callback từ một phương thức cụ thể; **FunctionToolCallback** phù hợp khi logic đã được biểu diễn bằng **Function**, **Supplier**, **Consumer**, **BiFunction**, lambda hoặc method reference.

FunctionToolCallback chuyển function thành một **ToolCallback**. Callback cung cấp definition cho mô hình và nhận dữ liệu JSON để chuyển thành kiểu Java rồi gọi function. Ứng dụng vẫn sở hữu logic thực thi và chịu trách nhiệm kiểm tra dữ liệu, xác thực quyền cũng như xử lý kết quả.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Spring
    participant Client as ChatClient
    participant Model as Mô hình
    participant Callback as FunctionToolCallback
    participant Service as Dịch vụ nghiệp vụ

    App->>Client: Gửi prompt kèm ToolCallback
    Client->>Model: Prompt + ToolDefinition
    Model-->>Client: Tool call + JSON arguments
    Client->>Callback: Chuyển JSON đầu vào
    Callback->>Callback: Deserialize thành DTO
    Callback->>Service: Gọi function
    Service-->>Callback: Kết quả nghiệp vụ
    Callback-->>Client: Tool result dạng String
    Client->>Model: Gửi tool result
    Model-->>Client: Câu trả lời cuối
    Client-->>App: Trả nội dung
~~~

Khi dùng **ChatClient**, Spring AI điều phối vòng gọi công cụ: gửi definition, nhận tool call, tìm callback, thực thi, gửi kết quả về mô hình và tiếp tục cho đến khi mô hình tạo câu trả lời cuối. Nếu gọi **ChatModel** trực tiếp ở API mức thấp, ứng dụng phải tự xử lý vòng gọi công cụ; chỉ gửi tool definition không đồng nghĩa callback sẽ tự chạy.

## 2. Ba phần của ToolDefinition

ToolDefinition là hợp đồng mà mô hình nhìn thấy. Nó có ba trường:

| Trường | Ý nghĩa | Câu hỏi cần trả lời |
| --- | --- | --- |
| **name** | Tên định danh của tool | Mô hình cần yêu cầu gọi công cụ nào? |
| **description** | Mô tả mục đích và cách sử dụng | Khi nào nên gọi công cụ này? |
| **inputSchema** | JSON Schema của dữ liệu đầu vào | Cần gửi những trường nào và theo kiểu gì? |

Một tool definition tốt giúp mô hình chọn đúng công cụ và tạo được đối số có cấu trúc. Nó không cấp quyền truy cập cho mô hình và cũng không thay thế các kiểm tra phía ứng dụng.

## 3. Cung cấp tên tool

Tên được truyền vào đối số đầu tiên của builder:

~~~java
FunctionToolCallback.builder(
    "lookup_inventory",
    inventoryService::lookup
)
~~~

Tên này là định danh phía tool calling. Nó không bắt buộc trùng với tên phương thức Java. Ví dụ, phương thức có thể tên là **findAvailableStock**, trong khi tên công cụ công bố cho mô hình là **lookup_inventory**.

Một tên tốt nên:

- Duy nhất trong toàn bộ tập tool được cung cấp cho cùng một yêu cầu chat.
- Thể hiện hành động và đối tượng nghiệp vụ, chẳng hạn **lookup_inventory** hoặc **find_order_status**.
- Ổn định khi đổi tên lớp hoặc phương thức nội bộ.
- Tránh tên quá chung như **process**, **execute** hoặc **get_data**.

Không dùng cùng một tên cho hai callback có hành vi khác nhau. Nếu hai tool cùng xử lý đơn hàng nhưng một tool tra cứu trạng thái còn tool kia hủy đơn, hãy đặt tên riêng để mô hình phân biệt được.

## 4. Viết mô tả để mô hình chọn đúng tool

Mô tả được cung cấp bằng phương thức **description(...)**:

~~~java
FunctionToolCallback.builder(
        "lookup_inventory",
        inventoryService::lookup
    )
    .description("""
        Tra cứu số lượng tồn kho có thể bán theo mã SKU.
        Dùng khi người dùng hỏi một sản phẩm còn hàng hay còn bao nhiêu.
        Công cụ chỉ đọc dữ liệu tồn kho và không thay đổi số lượng.
        """)
~~~

Mô tả nên làm rõ:

1. Công cụ thực hiện hành động gì và trên loại dữ liệu nào.
2. Những câu hỏi hoặc điều kiện nào phù hợp để gọi công cụ.
3. Đầu vào có định dạng hoặc quy ước gì đặc biệt.
4. Công cụ chỉ đọc dữ liệu hay có tác động thay đổi trạng thái.
5. Những giới hạn nghiệp vụ mà mô hình cần biết khi lựa chọn.

Ví dụ, mô tả “Tra cứu sản phẩm” chưa đủ rõ nếu ứng dụng còn có công cụ tìm sản phẩm theo tên hoặc danh mục. Mô tả “Tra cứu số lượng tồn kho có thể bán theo mã SKU; dùng khi người dùng hỏi sản phẩm còn hàng hay không; chỉ đọc dữ liệu” giúp mô hình phân biệt mục đích cụ thể hơn.

Mô tả không phải cơ chế bảo mật. Viết “chỉ quản trị viên được gọi” không thay thế kiểm tra quyền trong ứng dụng. Nếu tool có thể đọc hoặc thay đổi dữ liệu nhạy cảm, service vẫn phải xác thực người dùng và kiểm tra quyền trên tài nguyên.

## 5. Khai báo kiểu đầu vào bằng inputType

Tham số thứ hai của builder là function sẽ được gọi. Phương thức function cần có kiểu đầu vào mà Spring AI có thể chuyển đổi từ JSON. Với function nhận một DTO, cung cấp lớp DTO qua **inputType(...)**:

~~~java
public record InventoryQuery(
    String sku,
    Boolean includeWarehouse
) {}

public record InventoryResult(
    String sku,
    int availableQuantity,
    String warehouseName
) {}
~~~

Ví dụ service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    public InventoryResult lookup(InventoryQuery query) {
        // Truy vấn dữ liệu và áp dụng quy tắc nghiệp vụ tại đây.
        return new InventoryResult(
            query.sku(),
            12,
            Boolean.TRUE.equals(query.includeWarehouse())
                ? "Kho miền Nam"
                : null
        );
    }
}
~~~

Khi cung cấp **InventoryQuery.class**, Spring AI dùng kiểu đầu vào để tạo JSON Schema. Khi nhận JSON arguments, callback cũng dùng kiểu này để chuyển dữ liệu thành đối tượng InventoryQuery trước khi gọi function.

Kiểu đầu vào nên là DTO hoặc record có cấu trúc rõ ràng. Các kiểu dữ liệu đầu vào và đầu ra cần có thể được serialize/deserialize bằng cấu hình chuyển đổi của ứng dụng. DTO công khai với các trường có kiểu rõ ràng giúp hợp đồng dễ hiểu và dễ kiểm thử.

## 6. Mô tả trường và xác định trường bắt buộc

Tên trường và kiểu Java chưa luôn đủ để mô hình hiểu ý nghĩa nghiệp vụ. Có thể dùng **@ToolParam** trên thành phần của record để mô tả từng trường và đánh dấu trường tùy chọn:

~~~java
import org.springframework.ai.tool.annotation.ToolParam;

public record InventoryQuery(
    @ToolParam(
        description = "Mã SKU của sản phẩm, ví dụ SKU-100"
    )
    String sku,

    @ToolParam(
        description = "Có đưa tên kho vào kết quả hay không",
        required = false
    )
    Boolean includeWarehouse
) {}
~~~

Trong ví dụ:

- **sku** là mã định danh sản phẩm mà mô hình cần gửi.
- **includeWarehouse** là tùy chọn; mô hình có thể bỏ qua nếu người dùng không yêu cầu thông tin kho.
- Kiểu **Boolean** cho phép ứng dụng phân biệt giá trị true, false và null khi cần xử lý riêng.

Theo mặc định, các trường đầu vào được xem là bắt buộc. Có thể dùng **@ToolParam(required = false)** để đánh dấu tùy chọn; các metadata tương thích như **@Nullable** hoặc annotation Jackson/Swagger cũng có thể tham gia tạo schema theo quy tắc ưu tiên của Spring AI.

Đặt required đúng rất quan trọng. Nếu mô hình không có cách xác định một giá trị nhưng schema bắt buộc phải gửi, mô hình có thể tự đoán. Chỉ đánh dấu bắt buộc những trường cần thiết và có thể được xác định từ yêu cầu hoặc ngữ cảnh đáng tin cậy.

## 7. Tạo callback hoàn chỉnh bằng FunctionToolCallback

Kết hợp tên, mô tả và kiểu đầu vào để tạo callback:

~~~java
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.function.FunctionToolCallback;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class InventoryToolConfiguration {

    @Bean
    ToolCallback lookupInventory(InventoryService inventoryService) {
        return FunctionToolCallback.builder(
                "lookup_inventory",
                inventoryService::lookup
            )
            .description("""
                Tra cứu số lượng tồn kho có thể bán theo mã SKU.
                Dùng khi người dùng hỏi một sản phẩm còn hàng hay còn bao nhiêu.
                Có thể yêu cầu kèm tên kho nếu người dùng cần.
                Công cụ chỉ đọc dữ liệu tồn kho.
                """)
            .inputType(InventoryQuery.class)
            .build();
    }
}
~~~

Ở đây, Spring inject **InventoryService** vào phương thức **@Bean**. Method reference **inventoryService::lookup** được truyền cho FunctionToolCallback để callback gọi đúng service khi có tool call. Builder tạo ToolDefinition từ tên, mô tả và schema được sinh từ **InventoryQuery**.

Spring AI tự phát hiện các bean có kiểu **ToolCallback** trong application context và cung cấp chúng cho cơ chế phân giải tool. Có thể inject callback bean vào thành phần điều phối chat và truyền nó vào yêu cầu.

## 8. Cung cấp schema JSON tường minh

Trong hầu hết trường hợp, dùng **inputType(...)** để Spring AI sinh schema từ DTO là đủ. Khi cần kiểm soát schema gửi cho mô hình, builder cũng cung cấp **inputSchema(...)** để khai báo JSON Schema tường minh.

Ví dụ:

~~~java
return FunctionToolCallback.builder(
        "lookup_inventory",
        inventoryService::lookup
    )
    .description(
        "Tra cứu tồn kho có thể bán theo mã SKU."
    )
    .inputType(InventoryQuery.class)
    .inputSchema("""
        {
          "type": "object",
          "properties": {
            "sku": {
              "type": "string",
              "description": "Mã SKU, ví dụ SKU-100"
            },
            "includeWarehouse": {
              "type": "boolean",
              "description": "Có đưa tên kho vào kết quả hay không"
            }
          },
          "required": ["sku"],
          "additionalProperties": false
        }
        """)
    .build();
~~~

Hai cách khai báo có mục đích khác nhau:

| Cách | Vai trò |
| --- | --- |
| **inputType(InventoryQuery.class)** | Cung cấp kiểu Java để callback chuyển JSON thành đối tượng đầu vào; Spring AI có thể sinh schema từ kiểu này |
| **inputSchema("...")** | Cung cấp trực tiếp JSON Schema mà mô hình nhìn thấy |

Khi tự khai báo schema, vẫn cần cung cấp **inputType** để callback biết kiểu Java dùng khi deserialize JSON. Cần giữ schema đồng bộ với DTO mà function nhận. Tên trường, kiểu dữ liệu, trường bắt buộc và cấu trúc object phải khớp với dữ liệu mà callback có thể deserialize. Nếu schema yêu cầu một trường nhưng DTO không có, hoặc schema cho phép null trong khi kiểu Java không xử lý được, lời gọi có thể thất bại khi thực thi.

Schema cần có object gốc với **properties** và **required** phù hợp. Các mô tả trường nên nói rõ định dạng, đơn vị, múi giờ hoặc tập giá trị hợp lệ nếu những chi tiết đó ảnh hưởng đến cách tạo đối số. Một số provider chỉ hỗ trợ một tập con JSON Schema, vì vậy cần kiểm tra schema thực tế với model/provider mà ứng dụng triển khai.

## 9. Đưa ToolCallback vào ChatClient

Có thể cung cấp callback riêng cho một yêu cầu:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryAssistant {

    private final ChatClient chatClient;
    private final ToolCallback lookupInventory;

    public InventoryAssistant(
            ChatClient.Builder chatClientBuilder,
            ToolCallback lookupInventory) {
        this.chatClient = chatClientBuilder.build();
        this.lookupInventory = lookupInventory;
    }

    public String answer(String question) {
        return chatClient.prompt()
            .user(question)
            .tools(lookupInventory)
            .call()
            .content();
    }
}
~~~

Khi gọi **answer(...)**, callback được cung cấp qua **tools(...)** và chỉ sẵn có trong yêu cầu đó. Nếu callback phù hợp với câu hỏi, mô hình có thể tạo yêu cầu gọi tên **lookup_inventory** với JSON arguments theo schema đã công bố. ChatClient điều phối callback và gửi tool result về mô hình để tạo câu trả lời cuối.

Nếu công cụ cần có mặt trong mọi yêu cầu của một ChatClient, có thể đăng ký bằng **defaultTools(...)** khi tạo client. Hãy cân nhắc phạm vi cung cấp tool: các thao tác nhạy cảm hoặc có tác động phụ thường nên được thêm theo từng yêu cầu sau khi ứng dụng đã xác định quyền và mục đích.

Từ Spring AI 2.0, cần đăng ký rõ ràng **ToolCallback** bean cho function-style tool. Cách cũ khai báo một bean Function trần rồi phân giải bằng tên qua **toolNames(...)** đã bị loại bỏ. Dùng **FunctionToolCallback.builder(...)** để tạo callback rõ ràng.

## 10. Các dạng function được hỗ trợ

FunctionToolCallback có thể bọc nhiều kiểu functional interface:

| Kiểu | Dạng đầu vào | Dạng kết quả | Trường hợp dùng |
| --- | --- | --- | --- |
| **Function<I, O>** | Một đối tượng I | Một kết quả O | Tra cứu hoặc xử lý một yêu cầu |
| **Supplier<O>** | Không có đối số | Một kết quả O | Lấy dữ liệu không cần tham số |
| **Consumer<I>** | Một đối tượng I | Không có kết quả nghiệp vụ | Thực hiện một hành động |
| **BiFunction<I, ToolContext, O>** | Đối tượng I và ngữ cảnh tool | Một kết quả O | Cần dữ liệu theo request do ứng dụng cung cấp |

Ví dụ dùng Supplier:

~~~java
ToolCallback serverStatus = FunctionToolCallback
    .builder("get_server_status", statusService::currentStatus)
    .description("Lấy trạng thái hoạt động hiện tại của dịch vụ.")
    .build();
~~~

Ví dụ dùng BiFunction để nhận ngữ cảnh thực thi:

~~~java
import org.springframework.ai.chat.model.ToolContext;

ToolCallback tenantInventory = FunctionToolCallback
    .builder(
        "lookup_tenant_inventory",
        (InventoryQuery query, ToolContext context) ->
            inventoryService.lookupForTenant(
                query,
                (String) context.getContext().get("tenantId")
            )
    )
    .description("Tra cứu tồn kho của SKU trong tenant hiện tại.")
    .inputType(InventoryQuery.class)
    .build();
~~~

Tenant ID trong ví dụ đến từ **ToolContext** do ứng dụng cung cấp, không phải trường do mô hình tự chọn trong JSON. Service vẫn phải kiểm tra quyền truy cập vào dữ liệu của tenant đó.

## 11. Kiểm tra hợp đồng đã tạo

Sau khi build callback, có thể đọc definition mà callback công bố:

~~~java
ToolCallback callback = FunctionToolCallback
    .builder("lookup_inventory", inventoryService::lookup)
    .description("Tra cứu tồn kho có thể bán theo mã SKU.")
    .inputType(InventoryQuery.class)
    .build();

ToolDefinition definition = callback.getToolDefinition();

String name = definition.name();
String description = definition.description();
String inputSchema = definition.inputSchema();
~~~

Việc kiểm tra này hữu ích trong unit test hoặc contract test. Có thể xác minh:

- Tên tool đúng và không trùng với tool khác trong cùng tập.
- Mô tả không rỗng và phản ánh đúng hành vi.
- Schema là JSON hợp lệ.
- Schema có các trường cần thiết, kiểu dữ liệu chính xác và required đúng.
- DTO mà function nhận tương thích với schema đã công bố.

Nên kiểm thử cả function thực thi riêng và callback được tạo. Một test gọi trực tiếp service không chứng minh schema gửi cho mô hình đã đúng; ngược lại, kiểm tra schema không chứng minh service xử lý dữ liệu đúng.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Mô hình không chọn tool | Mô tả quá chung hoặc không nói rõ khi nào dùng | Viết mô tả cụ thể về hành động, dữ liệu và tình huống gọi |
| Mô hình gửi thiếu trường | Trường cần thiết bị đánh dấu tùy chọn | Xác định lại required và quy tắc mặc định |
| Mô hình gửi sai kiểu | Schema và DTO không thống nhất | Kiểm tra inputType, inputSchema và kiểu Java |
| Callback không deserialize được | JSON không tương thích với DTO hoặc kiểu không được hỗ trợ | Dùng DTO công khai, kiểu rõ ràng và kiểm tra binding |
| Tool name bị trùng | Nhiều callback dùng cùng định danh trong một request | Đặt tên riêng và kiểm tra tập tool cuối cùng |
| Tool bean không được tìm thấy | Chưa đăng ký callback thành bean hoặc chưa truyền vào ChatClient | Khai báo @Bean kiểu ToolCallback và inject đúng callback |
| Thay DTO nhưng schema không đổi như mong đợi | Đang dùng inputSchema tường minh cũ | Cập nhật schema thủ công hoặc bỏ inputSchema để sinh từ inputType |

Không nên dùng mô tả tool để thay thế validation hoặc phân quyền. Mô hình có thể tạo đối số đúng schema nhưng SKU vẫn không tồn tại, người dùng không có quyền xem dữ liệu hoặc trạng thái kho đã thay đổi. Function phải gọi dịch vụ nghiệp vụ có kiểm tra các điều kiện này.

## 13. Nguyên tắc thiết kế

1. **Tên duy nhất và ổn định.** Tên là định danh model dùng để yêu cầu thực thi callback.
2. **Mô tả theo hành vi.** Nêu mục đích, tình huống phù hợp, loại dữ liệu và giới hạn của tool.
3. **Dùng DTO rõ ràng.** Chọn input type có cấu trúc và trường có kiểu dữ liệu cụ thể.
4. **Đặt required đúng.** Không bắt mô hình tự đoán thông tin mà nó không thể biết.
5. **Giữ schema và DTO đồng bộ.** Đặc biệt khi khai báo JSON Schema thủ công.
6. **Giới hạn tool được cung cấp.** Chỉ đưa callback phù hợp với yêu cầu và quyền của người dùng vào ChatClient.
7. **Kiểm tra ở runtime.** Schema không thay thế validation, xác thực, phân quyền hoặc quy tắc nghiệp vụ.
8. **Trả kết quả có kiểm soát.** Chỉ đưa dữ liệu cần thiết trở lại mô hình và không tiết lộ bí mật nội bộ.

## Bài thực hành

Tạo FunctionToolCallback tên **find_customer_profile** để tra cứu hồ sơ khách hàng theo mã khách hàng.

Yêu cầu:

- Tạo record **CustomerQuery** có trường mã khách hàng.
- Tạo kiểu kết quả **CustomerProfile** gồm tên hiển thị và trạng thái tài khoản.
- Dùng function hoặc method reference đến **CustomerService**.
- Cung cấp tên **find_customer_profile** và mô tả rõ tình huống sử dụng.
- Dùng **inputType(CustomerQuery.class)** để sinh schema.
- Bổ sung mô tả trường bằng **@ToolParam**.
- Đăng ký callback thành Spring bean và đưa vào **ChatClient.tools(...)**.
- Kiểm tra definition.name(), description() và inputSchema().
- Kiểm tra mã không tồn tại và quyền truy cập tại service.

Sau khi hoàn thành, hãy tự trả lời: mô hình nhìn thấy ba thông tin nào trong ToolDefinition; inputType giúp ích gì khi chuyển JSON thành Java; khi nào nên tự cung cấp inputSchema?

## Ghi nhớ

Với FunctionToolCallback, builder nhận tên tool và function thực thi. **description(...)** giải thích công cụ làm gì và khi nào nên dùng. **inputType(...)** cung cấp kiểu Java để Spring AI sinh schema và chuyển JSON arguments thành đối tượng đầu vào. Khi cần kiểm soát schema trực tiếp, có thể dùng **inputSchema(...)**, nhưng phải giữ schema đồng bộ với DTO. Callback sau đó được cung cấp cho ChatClient để ứng dụng điều phối thực thi và trả kết quả về mô hình.

## Tài liệu tham khảo

- [Spring AI Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [FunctionToolCallback.Builder API](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/tool/function/FunctionToolCallback.Builder.html)
