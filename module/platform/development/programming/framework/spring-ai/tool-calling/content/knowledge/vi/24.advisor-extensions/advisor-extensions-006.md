# Bổ sung trường vào schema bằng AugmentedToolCallbackProvider khi hỗ trợ

Một công cụ Spring AI thường có các tham số nghiệp vụ cố định: `orderId` để tra cứu đơn hàng, `customerId` để xem hồ sơ hoặc `keyword` để tìm tài liệu. Đôi khi ứng dụng muốn mô hình cung cấp **thông tin bổ sung về chính lần gọi công cụ** như mục đích truy vấn, loại câu trả lời sẽ dùng kết quả, hoặc nhãn phục vụ phân tích. Những thông tin này có ích cho việc quan sát, nhưng không nhất thiết phải thêm tham số vào mọi method `@Tool`.

`AugmentedToolCallbackProvider<T>` của Spring AI cho phép bọc các callback hiện có rồi **bổ sung các thuộc tính vào JSON Schema đầu vào mà model nhìn thấy**. Model được yêu cầu trả thêm các trường đó; callback bọc sẽ trích xuất chúng thành một Java `record` và gửi cho một `Consumer`. Theo cấu hình mặc định, các trường tăng cường được **loại khỏi JSON arguments trước khi gọi tool gốc**. Nhờ vậy, method nghiệp vụ không cần thay đổi chữ ký.

Khả năng này **phụ thuộc phiên bản Spring AI**: tài liệu chính thức của nhánh 1.1.x và 2.x mô tả `AugmentedToolCallbackProvider`, còn tài liệu 1.0.9 không mô tả API này. Bài học hướng dẫn theo Spring AI **2.1.0**, đồng thời nêu rõ cách đăng ký khác ở 1.1.x và các phương án thay thế khi phiên bản đang dùng không hỗ trợ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **input schema augmentation** với việc sửa method nghiệp vụ, sửa tool result và truyền `ToolContext`.
- Giải thích luồng model nhìn thấy schema mở rộng, gửi JSON arguments, consumer nhận metadata rồi delegate được gọi.
- Tạo Java `record` với `@ToolParam` để mô tả các trường bổ sung.
- Sử dụng `AugmentedToolCallbackProvider.builder()` với `toolObject(...)`, `argumentType(...)` và `argumentConsumer(...)`.
- Phân biệt `toolObject(...)` và `delegate(ToolCallbackProvider)`.
- Hiểu `removeExtraArgumentsAfterProcessing(true/false)` và tác động lên tool gốc.
- Kiểm tra điều kiện hỗ trợ theo phiên bản và tên API của `ChatClient`.
- Giữ metadata do model tự tạo ở mức **không đáng tin**, không dùng làm định danh, phân quyền hoặc bằng chứng chắc chắn.
- Kiểm thử schema, payload gửi cho delegate, metadata event và trường hợp model trả giá trị thiếu/sai.
- Tránh thêm trường thừa làm tăng token, xung đột tên hoặc rò rỉ dữ liệu qua logs.

## Cần mở rộng đầu vào khi nào?

Giả sử tool hiện tại chỉ cần một mã đơn hàng:

~~~java
@Tool(description = "Tra cứu trạng thái đơn hàng theo mã")
public OrderStatus getOrderStatus(String orderId) {
    return orderService.findStatus(orderId);
}
~~~

Model được cung cấp schema chỉ có `orderId`. Nhưng trợ lý đôi khi cần đánh dấu **kết quả sẽ dùng để làm gì**: trả lời trực tiếp cho người dùng, đối chiếu với nguồn khác hoặc tổng hợp vào báo cáo. Thay vì sửa hàng chục method thành:

~~~java
// Không nên thêm trường phụ chỉ để telemetry vào mọi method.
public OrderStatus getOrderStatus(
        String orderId,
        String requestPurpose,
        String answerSection) { /* ... */ }
~~~

ứng dụng có thể giữ nguyên chữ ký của tool gốc, rồi khai báo `requestPurpose` và `answerSection` ở lớp augmentation.

Các trường nên thể hiện **thông tin mà model có thể ước lượng từ cuộc hội thoại**. Chúng không phù hợp để yêu cầu model cung cấp tenant ID đáng tin cậy, user ID đã xác thực, access token, mã phê duyệt hoặc thời điểm đọc dữ liệu từ server.

| Nhu cầu | Cơ chế phù hợp | Ai cung cấp dữ liệu? |
|---|---|---|
| `orderId` để tra cứu | Tham số `@Tool` / input schema gốc | Model từ yêu cầu người dùng |
| `requestPurpose` để phân loại nhu cầu | Augmented input schema | Model mô tả ngắn |
| `answerSection` cho phân tích nội dung | Augmented input schema | Model tự chọn |
| `tenantId`, `userId`, quyền truy cập | `ToolContext` và security principal | Backend đã xác thực |
| `requestId`, trace ID | `ToolContext` / observability context | Backend |
| `retrievedAt` của API nguồn | Metadata từ gateway/service | Ứng dụng hoặc nguồn |
| Kết quả và thông tin nguồn trả cho model | Tool result DTO | Callback/service nghiệp vụ |

**Điểm mấu chốt:** schema augmentation làm model tạo thêm **đối số đầu vào**, không biến dữ liệu model tạo thành ngữ cảnh nội bộ đáng tin.

## Luồng xử lý trước và sau khi augmentation

### Không dùng augmentation

~~~mermaid
flowchart LR
    A[Tool gốc: getOrderStatus] --> B[ToolDefinition + inputSchema]
    B --> C[Model]
    C -->|orderId| D[ToolCallback]
    D --> E[OrderService]
    E --> F[Tool result]
~~~

Model chỉ biết tham số `orderId`; Spring AI chuyển arguments cho callback và callback thực thi tool.

### Dùng AugmentedToolCallbackProvider

~~~mermaid
flowchart TD
    A[Tool gốc / ToolCallbackProvider] --> B[AugmentedToolCallbackProvider]
    R[Java record chứa trường mở rộng] --> B
    B --> C[ToolDefinition với inputSchema mở rộng]
    C --> M[Chat Model]
    M -->|JSON: orderId + requestPurpose + answerSection| W[AugmentedToolCallback]
    W --> X[Trích xuất record bổ sung]
    X --> H[AugmentedArgumentEvent]
    H --> U[argumentConsumer]
    W --> P[Loại trường bổ sung nếu bật true]
    P --> D[ToolCallback gốc]
    D --> S[Service nghiệp vụ]
    S --> Z[Tool result]
~~~

Quy trình:

1. Lấy `ToolCallback` gốc cùng `ToolDefinition.inputSchema()`.
2. Dùng kiểu Java `record` để tạo schema cho các trường bổ sung.
3. Hợp nhất schema thành input schema mà model nhìn thấy; **không** thay chữ ký của tool gốc.
4. Model trả tool call chứa các arguments gốc và các trường tăng cường.
5. `AugmentedToolCallback` trích xuất những trường tăng cường thành record; `argumentConsumer` nhận `AugmentedArgumentEvent`.
6. Nếu `removeExtraArgumentsAfterProcessing(true)`, wrapper loại các trường đó khỏi input rồi gọi callback gốc.
7. Kết quả nghiệp vụ trả về cho vòng tool calling như bình thường.

`AugmentedToolCallbackProvider` là một **`ToolCallbackProvider`**, không phải một `Advisor`. Trong chương “Mở rộng advisor”, nó vẫn thuộc **lớp callback/schema** của vòng tool calling; không cần tự tạo một advisor mới chỉ để thêm trường.

## Điều kiện hỗ trợ theo phiên bản

| Phiên bản | Tình trạng tài liệu và API cần dùng | Cách cung cấp cho ChatClient |
|---|---|---|
| Spring AI 1.0.9 | Trang Tool Calling không mô tả `AugmentedToolCallbackProvider`. Không giả định có class này trong dependency. | Nếu thiếu API, tự bọc `ToolCallback` hoặc dùng tham số nghiệp vụ riêng |
| Spring AI 1.1.8 | Có phần *Tool Argument Augmentation*, `AugmentedToolCallbackProvider` và `AugmentedArgumentEvent` | Ví dụ tài liệu dùng `defaultToolCallbacks(provider)` |
| Spring AI 2.0.x | Có package `org.springframework.ai.tool.augment` và các callback wrappers | Ví dụ tài liệu dùng `defaultTools(provider)` |
| Spring AI 2.1.0 | Tài liệu stable tiếp tục mô tả provider, wrapper và utility | `defaultTools(provider)` hoặc `prompt().tools(provider)` |

Khi nâng cấp, cần so sánh cả **Spring AI BOM**, Javadoc và chữ ký `ChatClient`. Một ví dụ dùng `defaultToolCallbacks(...)` cho nhánh 1.1 không thể copy nguyên sang mã theo API 2.1.0 mà không kiểm tra.

### Các điều kiện cần thiết khác

- **Java record:** kiểu augmentation `T` được ràng buộc là `T extends Record`. Dùng Java đủ phiên bản cho record và đúng mức JDK mà Spring AI/BOM yêu cầu.
- **Tool calling:** model/provider phải hỗ trợ khai báo tool và trả JSON arguments theo schema. Provider có thể có yêu cầu riêng về strict schemas và tùy chọn `required`.
- **Schema hợp lệ:** schema gốc phải là JSON Schema đầu vào phù hợp, các tên trường bổ sung không xung đột tên gốc.
- **Tool nguồn tồn tại:** cần object chứa `@Tool` hoặc một `ToolCallbackProvider` hợp lệ.
- **Chính sách logging:** dữ liệu augmented xuất phát từ model, có thể chứa nội dung người dùng hoặc nội dung không an toàn; phải có quy tắc lọc trước khi ghi telemetry.

Đây là API Spring AI quản lý bên phía ứng dụng. Không yêu cầu provider model có một tính năng tên “augmented tool callback” riêng. Model chỉ cần thấy và có thể điền input schema mở rộng.

## Bắt đầu với một tool Java cục bộ

### Bước 1: Giữ method nghiệp vụ gọn

Ví dụ service tra cứu trạng thái đơn hàng và cần áp dụng quyền:

~~~java
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

@Component
public class OrderTools {

    private final OrderQueryService orderQueryService;

    public OrderTools(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @Tool(
        name = "getOrderStatus",
        description = "Tra cứu trạng thái đơn hàng thuộc quyền người dùng"
    )
    public OrderStatus getOrderStatus(
            @ToolParam(description = "Mã đơn hàng cần tra cứu") String orderId,
            ToolContext toolContext) {

        String tenantId =
                (String) toolContext.getContext().get("tenantId");
        String userId =
                (String) toolContext.getContext().get("userId");

        return orderQueryService.getVisibleStatus(
                tenantId, userId, orderId
        );
    }
}
~~~

`OrderQueryService` và `OrderStatus` là kiểu nghiệp vụ minh họa. Dù model chọn đúng `orderId`, service vẫn phải xác minh user thuộc tenant và có quyền xem đơn hàng. `ToolContext` do backend tạo trong request, không do model tạo.

### Bước 2: Khai báo các trường mở rộng bằng record

~~~java
import org.springframework.ai.tool.annotation.ToolParam;

public record ModelUseMetadata(
    @ToolParam(
        description = "Mục đích sử dụng kết quả, mô tả ngắn gọn",
        required = false
    )
    String requestPurpose,

    @ToolParam(
        description = "Nhãn sử dụng: SUMMARY, CROSS_CHECK hoặc OTHER",
        required = false
    )
    String answerSection
) {}
~~~

Hai trường là **tùy chọn**. Model có thể không cung cấp chúng, và không được ép model bịa một mục đích hoặc một nhãn không xác định.

`@ToolParam` ở các component của record giúp `ToolInputSchemaAugmenter` tạo tên, mô tả, kiểu và thông tin required. Nếu field thực sự bắt buộc theo hợp đồng, có thể đặt `required = true`; khi đó model được yêu cầu cung cấp giá trị nhưng backend **vẫn phải kiểm tra**. Đánh dấu required không biến giá trị thành đáng tin.

### Bước 3: Bọc tool bằng AugmentedToolCallbackProvider

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.ai.tool.augment.AugmentedToolCallbackProvider;

@Configuration(proxyBeanMethods = false)
public class AugmentedToolConfiguration {

    @Bean
    AugmentedToolCallbackProvider<ModelUseMetadata> orderToolProvider(
            OrderTools orderTools,
            MeterRegistry meterRegistry) {

        return AugmentedToolCallbackProvider
                .<ModelUseMetadata>builder()
                .toolObject(orderTools)
                .argumentType(ModelUseMetadata.class)
                .argumentConsumer(event -> {
                    ModelUseMetadata metadata = event.arguments();

                    if (metadata == null) {
                        return;
                    }

                    // Chỉ ghi số đếm, không log rawInput() hoặc text tự do.
                    meterRegistry.counter(
                            "ai.tool.augmented.call",
                            "tool",
                            event.toolDefinition().name()
                    ).increment();

                    // Nếu cần ghi nhãn, chỉ dùng danh sách nhãn đã kiểm tra.
                    String label = switch (
                            metadata.answerSection() == null
                                ? ""
                                : metadata.answerSection()
                    ) {
                        case "SUMMARY" -> "summary";
                        case "CROSS_CHECK" -> "cross_check";
                        default -> "other";
                    };

                    meterRegistry.counter(
                            "ai.tool.augmented.section",
                            "section",
                            label
                    ).increment();
                })
                .removeExtraArgumentsAfterProcessing(true)
                .build();
    }
}
~~~

Các thành phần khác như `MeterRegistry` đến từ hệ thống metrics của ứng dụng. Ví dụ dùng một danh sách nhãn nhỏ, không dùng chuỗi do model tạo trực tiếp làm metric tag vì nguy cơ cardinality cao.

Với `toolObject(orderTools)`, wrapper tạo những callback tương ứng với method `@Tool` có trong object và tăng cường các schema của chúng. Khi muốn chỉ áp dụng cho **một tool**, dùng object có một tool hoặc bọc đúng callback qua `ToolCallbackProvider.from(...)`, tránh tăng cường toàn bộ tool một cách vô ý.

### Bước 4: Đăng ký với ChatClient

Với Spring AI **2.0.x/2.1.0**:

~~~java
ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultTools(orderToolProvider)
        .build();
~~~

Hoặc chỉ thêm provider cho request phù hợp:

~~~java
String answer = chatClient.prompt()
        .user("Kiểm tra trạng thái đơn DH-1024")
        .tools(orderToolProvider)
        .toolContext(Map.of(
                "tenantId", authenticatedUser.tenantId(),
                "userId", authenticatedUser.userId()
        ))
        .call()
        .content();
~~~

Ở đây `authenticatedUser` phải đến từ nguồn xác thực đáng tin cậy của backend.

Với Spring AI **1.1.x**, tài liệu ví dụ sử dụng:

~~~java
ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultToolCallbacks(orderToolProvider)
        .build();
~~~

Không trộn hai dạng đăng ký chỉ để “an toàn hơn”. Hãy sử dụng API của chính phiên bản dự án và không đăng ký cùng một callback hai lần dưới cùng tên.

## Schema trước và sau khi mở rộng

Đây là minh họa khái niệm cho tool `getOrderStatus`. JSON Schema cụ thể có thể chứa thêm các trường như `additionalProperties` hoặc mô tả do generator/version cung cấp.

### Schema gốc

~~~json
{
  "type": "object",
  "properties": {
    "orderId": {
      "type": "string",
      "description": "Mã đơn hàng cần tra cứu"
    }
  },
  "required": ["orderId"]
}
~~~

### Schema tăng cường đưa cho model

~~~json
{
  "type": "object",
  "properties": {
    "orderId": {
      "type": "string",
      "description": "Mã đơn hàng cần tra cứu"
    },
    "requestPurpose": {
      "type": "string",
      "description": "Mục đích sử dụng kết quả, mô tả ngắn gọn"
    },
    "answerSection": {
      "type": "string",
      "description": "Nhãn sử dụng: SUMMARY, CROSS_CHECK hoặc OTHER"
    }
  },
  "required": ["orderId"]
}
~~~

Model có thể gửi:

~~~json
{
  "orderId": "DH-1024",
  "requestPurpose": "Trả lời câu hỏi tiến độ giao hàng",
  "answerSection": "SUMMARY"
}
~~~

`argumentConsumer` nhận record:

~~~java
new ModelUseMetadata(
    "Trả lời câu hỏi tiến độ giao hàng",
    "SUMMARY"
)
~~~

Với `removeExtraArgumentsAfterProcessing(true)`, callback gốc nhận arguments tương đương:

~~~json
{
  "orderId": "DH-1024"
}
~~~

Method `getOrderStatus(String orderId, ToolContext ctx)` không cần tham số `requestPurpose` hay `answerSection`. `ToolContext` tiếp tục được truyền theo request như trước.

> **Lưu ý:** Bộ chuyển schema điều chỉnh **đầu vào tool mà model nhìn thấy**, không tự thêm thuộc tính vào DTO kết quả hoặc thay đổi chữ ký Java. Những gì consumer nhận do model khai báo không được tự coi là telemetry đã được hệ thống xác thực.

## Vai trò các thành phần trong package augment

Spring AI cung cấp các thành phần chính tại `org.springframework.ai.tool.augment`:

| Thành phần | Trách nhiệm |
|---|---|
| `AugmentedToolCallbackProvider<T extends Record>` | Bọc một object chứa tools hoặc một `ToolCallbackProvider` khác, sinh các callback tăng cường |
| `AugmentedToolCallback<T extends Record>` | Bọc một callback riêng, thay input schema và xử lý arguments mở rộng trước khi ủy quyền |
| `AugmentedArgumentEvent<T>` | Chứa `toolDefinition()`, `rawInput()` và `arguments()` |
| `ToolInputSchemaAugmenter` | Utility cấp thấp để bổ sung một/một nhóm trường vào JSON Schema |
| `ToolInputSchemaAugmenter.AugmentedArgumentType` | Mô tả tên, kiểu, description và required của trường mới |

### AugmentedArgumentEvent gồm những gì?

`argumentConsumer(event -> ...)` nhận một event có:

- `event.toolDefinition()`: định nghĩa công cụ liên quan đến lời gọi.
- `event.rawInput()`: JSON nguyên bản của lời gọi tool, gồm cả arguments nghiệp vụ và phần mở rộng.
- `event.arguments()`: record `T` đã trích xuất; theo Javadoc, giá trị có thể `null`.

Consumer có thể nhận các event từ nhiều tool nếu provider bọc một object chứa nhiều method. Khi cần phân luồng xử lý, hãy dùng tên tool từ `event.toolDefinition().name()` và kiểm tra giá trị record.

**Không log toàn bộ `rawInput()`** trong production: nó có thể chứa thông tin người dùng, đối số truy vấn hoặc dữ liệu cá nhân. Nếu cần audit, hãy lưu metadata đã lọc hoặc một mã tương quan backend tạo và tuân thủ retention policy.

### Tool metadata có còn nguyên không?

Javadoc Spring AI 2.1.0 của `AugmentedToolCallback` mô tả `getToolMetadata()` ủy quyền metadata của callback gốc, nhằm giữ các thuộc tính như `returnDirect()` và `requiresConfirmation()`. Vì vậy augment schema không nên tự biến tool đã cần xác nhận thành tool không cần xác nhận.

Dù vậy, với tool có side effect, cần có integration test xác minh policy của đúng phiên bản đang dùng. Đừng dựa vào augmentation như một cơ chế approval, phân quyền hay hạn chế dữ liệu.

## Bọc một ToolCallbackProvider có sẵn

Không phải lúc nào bạn sở hữu class có `@Tool`. Có thể đã có callback từ `FunctionToolCallback`, từ một library hoặc từ MCP client.

Builder hỗ trợ hai nguồn thay thế nhau:

- `.toolObject(existingToolObject)`: quét object chứa method `@Tool` và bọc các callback tạo ra.
- `.delegate(existingProvider)`: lấy các callback từ provider khác rồi bọc chúng.

Ví dụ từ một callback của function:

~~~java
import org.springframework.ai.tool.FunctionToolCallback;
import org.springframework.ai.tool.ToolCallbackProvider;
import org.springframework.ai.tool.augment.AugmentedToolCallbackProvider;

FunctionToolCallback original = FunctionToolCallback
        .builder("lookupOrder", orderService::lookup)
        .description("Tra cứu đơn hàng theo mã")
        .inputType(OrderLookupRequest.class)
        .build();

ToolCallbackProvider originalProvider =
        ToolCallbackProvider.from(original);

AugmentedToolCallbackProvider<ModelUseMetadata> augmented =
        AugmentedToolCallbackProvider
                .<ModelUseMetadata>builder()
                .delegate(originalProvider)
                .argumentType(ModelUseMetadata.class)
                .argumentConsumer(event -> {
                    ModelUseMetadata metadata = event.arguments();
                    if (metadata != null) {
                        metrics.recordToolSelection(
                                event.toolDefinition().name(),
                                metadata.answerSection()
                        );
                    }
                })
                .removeExtraArgumentsAfterProcessing(true)
                .build();
~~~

`metrics.recordToolSelection(...)` là method của ứng dụng cần kiểm tra/sanitise nhãn trước khi ghi; không phải API Spring AI. `OrderLookupRequest`, `OrderService` cũng là kiểu nghiệp vụ minh họa. Có thể dùng `.tools(augmented)` trong request hoặc `.defaultTools(augmented)` trên builder.

Nếu delegate là một MCP `ToolCallbackProvider`, cơ chế schema augmentation vẫn diễn ra ở phía Spring AI client trên callbacks mà provider trả về. Tuy nhiên cần kiểm tra MCP server có chấp nhận extra arguments khi `removeExtraArgumentsAfterProcessing(false)` hay không. Thực tế nên giữ `true` để MCP server nhận đúng schema gốc; đồng thời test callback name, refresh catalog và các trường metadata cần chuyển sang `_meta`.

## removeExtraArgumentsAfterProcessing(true/false)

Đây là cấu hình quyết định **input nào được chuyển cho callback gốc**, không quyết định model có nhìn thấy fields mới hay không.

| Giá trị | Tác động | Khuyến nghị |
|---|---|---|
| `true` (mặc định) | Trích xuất metadata, loại các trường tăng cường trước khi gọi delegate | Mặc định tốt nhất khi không muốn thay hợp đồng tool gốc |
| `false` | Vẫn trích xuất metadata, nhưng giữ các trường bổ sung trong JSON gửi delegate | Chỉ dùng khi delegate rõ ràng chấp nhận hoặc bỏ qua field thừa |

Ví dụ:

~~~java
.removeExtraArgumentsAfterProcessing(true)
~~~

Dù model trả thêm `requestPurpose`, tool gốc chỉ nhận `orderId`.

Nếu đặt:

~~~java
.removeExtraArgumentsAfterProcessing(false)
~~~

tool gốc có thể nhận cả `requestPurpose` và `answerSection`. Với DTO có unknown-property checking, schema validation chặt hoặc MCP server kiểm tra input schema, những trường này có thể gây lỗi. Không bật `false` chỉ vì muốn consumer xử lý metadata — consumer đã nhận record trước khi delegate chạy.

**Nguyên tắc:** nếu không có yêu cầu nghiệp vụ rõ ràng, giữ `true`.

## Thêm trường bằng ToolInputSchemaAugmenter cấp thấp

`AugmentedToolCallbackProvider` là lựa chọn mức cao khi muốn thay schema và xử lý extras trước khi gọi delegate. Khi chỉ muốn thao tác schema, `ToolInputSchemaAugmenter` có API cụ thể.

Ví dụ thêm một thuộc tính:

~~~java
import org.springframework.ai.tool.augment.ToolInputSchemaAugmenter;

String schema = ToolInputSchemaAugmenter.augmentToolInputSchema(
        originalCallback.getToolDefinition().inputSchema(),
        "requestPurpose",
        String.class,
        "Mục đích sử dụng kết quả do model mô tả",
        false
);
~~~

Phương thức trên nhận: schema gốc, tên property, kiểu Java, description và cờ required. Utility còn có overload nhận danh sách `AugmentedArgumentType` và `toAugmentedArgumentTypes(YourRecord.class)` để lấy mô tả fields từ record.

**Cảnh báo:** chỉ sửa `ToolDefinition.inputSchema()` mà không có wrapper xử lý JSON arguments có thể khiến tool gốc nhận tham số ngoài hợp đồng. Nếu cần tăng cường và tách arguments an toàn, dùng `AugmentedToolCallbackProvider` hoặc `AugmentedToolCallback` thay vì sửa schema đơn độc.

### Tránh xung đột tên và cấu trúc

- Không thêm một field cùng tên với tham số gốc, ví dụ thêm `orderId` lần nữa.
- Không tái sử dụng một tên augmented field với hai ý nghĩa khác nhau qua các version.
- Tránh các kiểu dữ liệu phức tạp nếu model/provider không hỗ trợ schema tương ứng.
- Dùng `@ToolParam(description=..., required=...)` rõ nghĩa.
- Không yêu cầu các thông tin mà model không có căn cứ để xác định.
- Nếu schema gốc có `additionalProperties: false`, kiểm tra schema sau augmentation và payload delegate thay vì tự ghép JSON bằng chuỗi.

## Phân biệt augmentation, ToolContext và advisor

Ba cơ chế có chức năng khác nhau:

| Cơ chế | Dữ liệu model có nhìn thấy? | Tác dụng |
|---|---|---|
| Input schema gốc | Có | Các tham số nghiệp vụ của tool |
| Augmented tool input schema | Có | Cho model thêm metadata vào tool arguments |
| `ToolContext` | Không gửi trong tool schema | Dữ liệu request nội bộ do ứng dụng cấp: user, tenant, request ID |
| `ToolCallingAdvisor` | Không phải một schema field | Điều phối vòng gọi model–tool và trả tool result |
| `ToolCallbackProvider` | Model chỉ thấy định nghĩa callback cuối | Cung cấp một hoặc nhiều callbacks cho request |
| Tool result converter | Model thấy output sau khi tool chạy | Chuyển giá trị trả về từ callback sang kết quả tool |

Ví dụ nhu cầu “biết người dùng nào gọi tool” phải dùng principal và `ToolContext`, không dùng:

~~~java
// Không được tin: model có thể tự bịa userId.
public record UnsafeMetadata(String userId, String tenantId) {}
~~~

Tương tự, nếu muốn ghi thời điểm thực tế tool đọc database, backend phải tạo timestamp bằng `Clock`. Một field `readAt` do model tự trả trong augmented JSON không chứng minh khi nào dữ liệu được đọc.

Với chương “Mở rộng advisor”, cần nhớ augmentation diễn ra ở **ranh giới callback**; nó không tự thêm một advisor, không tự thực thi authorization và không thay logic điều phối nhiều vòng của `ToolCallingAdvisor`.

## Dùng metadata model tự tạo một cách an toàn

### Metadata là nhận định của model, không phải bằng chứng

`requestPurpose` hoặc `answerSection` có thể giúp phân tích cách model đang dùng tool, nhưng không phải “sự thật hệ thống”. Model có thể chọn nhãn sai, trả text không tuân mô tả hoặc bị nội dung người dùng tác động.

Vì vậy:

- Chỉ dùng nhãn cho telemetry hoặc gợi ý phân loại mức thấp.
- Không dựa vào nhãn để cấp quyền, chọn tenant hoặc quyết định bỏ qua approval.
- Không để model tự quyết định security classification, role hoặc policy enforcement.
- Không diễn giải `confidence` do model khai báo như xác suất đã hiệu chỉnh hoặc độ tin cậy bảo đảm.
- Không dùng một trường “reasoning” để yêu cầu/trích xuất suy luận nội bộ của model. Nếu cần giải thích quyết định, yêu cầu **mô tả mục đích ngắn, mức cao**; không xem đó là chuỗi suy luận riêng tư.

### Tránh rò rỉ qua logging và metrics

`event.rawInput()` có thể chứa mã khách hàng, câu truy vấn hoặc nội dung nhạy cảm. Không ghi toàn bộ payload nếu chưa có chính sách và biện pháp làm sạch. `event.arguments()` cũng bắt nguồn từ JSON do model tạo.

Nếu ghi metric, phải hạn chế label set:

~~~java
String section = switch (String.valueOf(metadata.answerSection())) {
    case "SUMMARY" -> "summary";
    case "CROSS_CHECK" -> "cross_check";
    default -> "other";
};

counter("ai.tool.section", "section", section).increment();
~~~

Không dùng `requestPurpose` tùy ý làm metric tag. Chuỗi tự do có thể tạo cardinality vô hạn, tăng chi phí và làm hệ thống quan sát quá tải.

Nếu cần lưu text để phân tích, chỉ lưu trong một luồng kiểm soát riêng với retention, quyền truy cập, khử PII và audit. Không thực hiện I/O nặng hoặc chờ lâu ngay trong `argumentConsumer`; đó là một phần của đường thực thi tool, có thể làm tăng latency.

### Consumer có thể lỗi

Javadoc cho phép `event.arguments()` có giá trị `null`. Cần xử lý null, trường thiếu, giá trị không đúng enum và các lỗi deserialize/validation theo hợp đồng của phiên bản.

Nếu consumer throw exception trước khi delegate được gọi, tool call có thể không hoàn tất theo dự kiến. Đối với telemetry không quan trọng, nên dùng đường ghi có giới hạn và chính sách xử lý lỗi rõ ràng; đối với policy bắt buộc, cần validate và trả lỗi an toàn thay vì dựa vào giá trị do model tự tạo.

## Nhiều tool trong một provider

Khi `toolObject(...)` có nhiều method `@Tool`, provider sẽ bọc tất cả callbacks tương ứng. Record augmentation giống nhau có thể được thêm vào mỗi schema.

Ví dụ:

~~~java
@Component
class CustomerTools {
    @Tool(description = "Tra cứu khách hàng")
    CustomerSummary getCustomer(String customerId) { /* ... */ }

    @Tool(description = "Liệt kê đơn hàng")
    List<OrderSummary> getOrders(String customerId) { /* ... */ }
}
~~~

Nếu bọc cả object bằng `ModelUseMetadata`, cả `getCustomer` và `getOrders` đều được yêu cầu cho phép `requestPurpose` và `answerSection`. Có thể theo dõi tool name trong `AugmentedArgumentEvent.toolDefinition()`.

Cần cân nhắc:

1. Các trường tăng cường có thật sự phù hợp với **mọi** tool không?
2. Có tăng token schema cho những tool không cần metadata không?
3. Có tool đặc biệt như tool ghi dữ liệu hoặc tool của MCP server yêu cầu schema chặt hơn không?
4. Có cần dùng nhiều provider nhỏ thay vì bọc toàn bộ catalog không?

Với danh mục công cụ lớn, augmentation làm mỗi input schema dài hơn và có thể ảnh hưởng chi phí token. Không nên mặc định bọc mọi tool nếu chỉ một vài tool cần metadata phụ.

## Bảo toàn các cơ chế thực thi nghiệp vụ

Schema augmentation không thay thế các cơ chế khác của Spring AI:

- **`ToolCallbackResolver`:** vẫn cần tìm callback theo tên nếu ứng dụng dùng phân giải động.
- **`ToolContext`:** vẫn mang dữ liệu backend đáng tin đến tool.
- **`ToolCallingAdvisor`:** vẫn điều phối vòng tool calling và các lần gọi model.
- **`ToolMetadata.returnDirect`:** vẫn quyết định kết quả có trả thẳng thay vì đưa lại model theo hành vi của phiên bản.
- **`ToolMetadata.requiresConfirmation`:** vẫn quyết định thao tác cần approval khi tính năng tương ứng được bật.
- **Retry/deadline/idempotency:** vẫn là trách nhiệm của lớp service và orchestration.

Một tool có metadata `requiresConfirmation` không được tự động “được phê duyệt” chỉ vì consumer nhận được `requestPurpose = "approved"`. Phê duyệt phải đến từ cơ chế xác nhận đáng tin của ứng dụng.

## Kiểm thử schema augmentation

Nên test ở ít nhất ba mức: sinh schema, gọi callback và tích hợp ChatClient.

### 1. Unit test schema mở rộng

Tạo một tool giả hoặc method `@Tool` và provider bọc tương ứng. Lấy callback đã tăng cường:

~~~java
ToolCallback[] callbacks = augmentedProvider.getToolCallbacks();

assertThat(callbacks).hasSize(1);

JsonNode schema = objectMapper.readTree(
        callbacks[0].getToolDefinition().inputSchema()
);

assertThat(schema.path("properties").has("orderId")).isTrue();
assertThat(schema.path("properties").has("requestPurpose")).isTrue();
assertThat(schema.path("properties").has("answerSection")).isTrue();
assertThat(schema.path("required").toString()).contains("orderId");
~~~

Vì các trường trong `ModelUseMetadata` được đánh dấu `required = false`, cũng kiểm tra `requestPurpose` và `answerSection` không nằm trong mảng `required`. Không so sánh toàn bộ JSON bằng một chuỗi cố định; thứ tự property hoặc chi tiết schema generator có thể khác giữa các phiên bản.

### 2. Unit test consumer và delegate

Dùng object test có một method `@Tool` nhận tham số gốc. Truyền JSON có thêm fields:

~~~java
AtomicReference<ModelUseMetadata> captured = new AtomicReference<>();

AugmentedToolCallbackProvider<ModelUseMetadata> provider =
        AugmentedToolCallbackProvider.<ModelUseMetadata>builder()
                .toolObject(testTools)
                .argumentType(ModelUseMetadata.class)
                .argumentConsumer(e -> captured.set(e.arguments()))
                .removeExtraArgumentsAfterProcessing(true)
                .build();

ToolCallback callback = provider.getToolCallbacks()[0];

String result = callback.call("""
    {
      "orderId": "DH-1024",
      "requestPurpose": "Kiểm tra tiến độ giao hàng",
      "answerSection": "SUMMARY"
    }
    """);

assertThat(captured.get()).isNotNull();
assertThat(captured.get().answerSection()).isEqualTo("SUMMARY");
assertThat(result).contains("DH-1024");
~~~

`testTools` phải là một fixture của test có method `@Tool` trả kết quả chứa mã đơn hàng. Để xác nhận việc strip extras, có thể bọc delegate spy và kiểm tra JSON thực nhận **không chứa** `requestPurpose` và `answerSection`. Nếu `removeExtraArgumentsAfterProcessing(false)`, làm test ngược lại để xác nhận behavior và khả năng delegate chấp nhận field thừa.

### 3. Integration test qua ChatClient

Dùng fake `ChatModel` trả tool call theo schema mới rồi kiểm tra:

1. Model nhận schema có các fields tăng cường.
2. Model trả arguments gồm `orderId` và metadata bổ sung.
3. Consumer nhận một `AugmentedArgumentEvent` đúng tool name.
4. Callback gốc được thực thi một lần với `orderId`.
5. `ToolContext` chứa tenant/user từ request, không bị thay bằng metadata do model tạo.
6. Tool result được trả về model qua `ToolCallingAdvisor` để sinh câu trả lời cuối.
7. Không có lỗi khi model bỏ các trường tùy chọn.
8. Unknown/invalid label được chuẩn hóa hoặc xử lý theo chính sách.
9. Nếu tool gốc yêu cầu approval/returnDirect, metadata vẫn được giữ và kiểm tra đúng.

Nên có test riêng cho callback từ `ToolCallbackProvider.from(...)`, test từ `toolObject(...)` và test khi version dependency không có class augmentation (build của nhánh legacy phải dùng implementation thay thế).

## Khi phiên bản hoặc provider không hỗ trợ

Nếu dự án dùng Spring AI 1.0.x hoặc API thực tế không có `org.springframework.ai.tool.augment.AugmentedToolCallbackProvider`, không giả định rằng chỉ cần copy import từ tài liệu 2.1 là chạy.

Các lựa chọn thay thế:

### Cách A: Thêm tham số vào DTO nghiệp vụ khi trường thực sự cần cho thao tác

Nếu trường bổ sung là một tham số nghiệp vụ bắt buộc, đưa thẳng vào method hoặc DTO:

~~~java
public record SearchRequest(
        String query,
        String desiredFormat
) {}

@Tool(description = "Tìm tài liệu và trả ở định dạng yêu cầu")
public SearchResult search(SearchRequest request) {
    return searchService.search(request);
}
~~~

Cách này rõ ràng hơn augmentation vì `desiredFormat` là một phần hợp đồng của tool, không phải metadata telemetry.

### Cách B: Tự viết ToolCallback wrapper khi version cũ không có API

Một wrapper có thể:

1. Nhận `ToolDefinition` của callback gốc.
2. Tạo schema mở rộng bằng API phù hợp hoặc xử lý JSON Schema có kiểm soát.
3. Khi `call(...)`, parse JSON arguments của model.
4. Lấy các trường bổ sung đưa vào consumer.
5. Xóa các trường đó khỏi JSON trước khi gọi delegate.
6. Giữ nguyên `ToolMetadata` và chuyển tiếp `ToolContext`.
7. Trả nguyên kết quả delegate.

Đây là cách cần nhiều code và test hơn, nhất là với `required`, `additionalProperties` và exception handling. Tránh sửa thô JSON Schema bằng chuỗi.

### Cách C: Dùng ToolContext nếu giá trị phải do ứng dụng cung cấp

Nếu mục tiêu thực chất là user ID, tenant, trace ID hoặc policy version, không cần augmentation. Hãy đặt giá trị vào `ToolContext` từ backend và giữ chúng ngoài JSON Schema gửi model.

## Các lỗi thường gặp

- **Nghĩ augmentation thêm tham số vào method Java:** nó tăng schema model nhìn thấy và bọc callback; method gốc vẫn giữ chữ ký.
- **Nhầm với thay output schema:** API này xử lý **tool input schema**, không biến đổi tool result DTO.
- **Cho rằng metadata do model tạo là đáng tin:** model có thể đoán, bị prompt injection hoặc trả giá trị sai.
- **Dùng augmented field làm tenant/user ID:** phải lấy từ security principal và `ToolContext`.
- **Đặt `required = true` cho trường model không biết:** model có thể bịa thông tin để điền.
- **Không đặt `removeExtraArgumentsAfterProcessing(true)` khi delegate chặt:** JSON thừa có thể gây lỗi.
- **Quên xử lý `event.arguments() == null`:** consumer có thể ném exception.
- **Ghi toàn bộ `rawInput()`:** có thể làm lộ thông tin nhạy cảm trong logs.
- **Dùng text tự do làm metric label:** tạo cardinality lớn và tăng chi phí.
- **Bọc nhiều tool nhưng chỉ một tool cần metadata:** mọi schema đều dài hơn không cần thiết.
- **Dùng `defaultToolCallbacks(...)` của 1.1.x trong code 2.x không kiểm tra:** API đăng ký đã thay đổi.
- **Dùng class không có trong BOM của nhánh 1.0.x:** phải đối chiếu version hoặc viết wrapper tương thích.
- **Bỏ qua approval/authorization vì consumer nhận được nhãn "approved":** đó chỉ là text của model.
- **Chỉnh `ToolDefinition` nhưng quên xử lý JSON khi thực thi:** tool gốc có thể nhận tham số ngoài hợp đồng.

## Checklist trước khi áp dụng

- [ ] Đã xác định Spring AI version và package `org.springframework.ai.tool.augment` có trên classpath.
- [ ] Dùng đúng `defaultToolCallbacks(...)` cho 1.1.x hoặc `defaultTools(...)` cho 2.x theo tài liệu.
- [ ] Model/provider hỗ trợ input schema được mở rộng.
- [ ] Augmented Java type là record với `@ToolParam` rõ nghĩa.
- [ ] Tên augmented fields không trùng tên parameters gốc.
- [ ] Chỉ yêu cầu field mà model có căn cứ để cung cấp.
- [ ] Mặc định strip extras trước khi gọi delegate.
- [ ] Consumer xử lý record null, label sai và lỗi phù hợp.
- [ ] Không dùng augmented metadata làm nguồn phân quyền hay phê duyệt.
- [ ] Không log toàn bộ tool raw input; telemetry được hạn chế cardinality.
- [ ] `ToolContext` vẫn được truyền từ backend, không bị lẫn vào augmented schema.
- [ ] Có test schema/required flags, consumer, delegate input, metadata và ChatClient loop.
- [ ] Tool có side effect vẫn giữ approval, authorization, deadline và idempotency.

## Ghi nhớ

`AugmentedToolCallbackProvider` là wrapper của các `ToolCallback` cho phép **mở rộng input schema** mà model nhìn thấy. Các trường bổ sung được mô tả bằng Java record, trích xuất cho `argumentConsumer` rồi mặc định loại khỏi JSON gửi đến tool gốc. Nó hữu ích cho metadata phân tích hoặc mục đích sử dụng kết quả, **không** phù hợp cho dữ liệu định danh và quyền truy cập do backend phải xác thực.

API có trong tài liệu Spring AI 1.1.x và 2.x; cách đăng ký provider với `ChatClient` khác nhau theo phiên bản. Với Spring AI 1.0.x hoặc môi trường không có API đó, cần dùng DTO nghiệp vụ, `ToolContext` hoặc tự viết callback wrapper. Luôn kiểm tra schema thực tế, payload đến delegate và quyền thực thi nghiệp vụ bằng test, thay vì giả định model điền đúng mọi trường.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling, Tool Argument Augmentation](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.0.2 — Tool Calling, Tool Argument Augmentation](https://docs.spring.io/spring-ai/reference/2.0/api/tools.html)
- [Spring AI 1.1.8 — Tool Calling, Tool Argument Augmentation](https://docs.spring.io/spring-ai/reference/1.1/api/tools.html)
- [Spring AI 1.0.9 — Tool Calling](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html)
- [Spring AI API — AugmentedToolCallbackProvider.Builder](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/tool/augment/AugmentedToolCallbackProvider.Builder.html)
- [Spring AI API — AugmentedArgumentEvent](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/tool/augment/AugmentedArgumentEvent.html)
- [Spring AI API — ToolInputSchemaAugmenter](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/tool/augment/ToolInputSchemaAugmenter.html)

