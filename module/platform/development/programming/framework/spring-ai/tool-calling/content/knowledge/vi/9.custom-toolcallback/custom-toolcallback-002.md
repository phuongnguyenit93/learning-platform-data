# Xây dựng ToolDefinition với JSON Schema riêng

`ToolDefinition` là hợp đồng mà Spring AI gửi cho mô hình để mô hình biết một công cụ có tên gì, dùng để làm gì và cần cung cấp những tham số nào. Khi công cụ có cấu trúc đầu vào đặc biệt, cần ràng buộc schema cụ thể hoặc không thể mô tả chính xác bằng chữ ký Java, ứng dụng có thể tự xây dựng `ToolDefinition` với JSON Schema riêng.

`ToolDefinition` chỉ mô tả công cụ. Nó không thực thi logic nghiệp vụ và không xác thực dữ liệu runtime. Phần thực thi thuộc về `ToolCallback`. Vì vậy, khi xây dựng công cụ tùy chỉnh, cần thiết kế cả hai phần: schema rõ ràng để mô hình tạo arguments phù hợp và callback đủ chặt chẽ để kiểm tra arguments trước khi gọi service.

## ToolDefinition mô tả điều gì?

Trong Spring AI, `ToolDefinition` có ba thành phần:

| Thành phần | Ý nghĩa | Tác động đến tool calling |
| --- | --- | --- |
| `name` | Tên định danh của công cụ | Mô hình dùng tên này trong tool call; tên phải duy nhất trong tập công cụ của một request. |
| `description` | Mô tả mục đích và cách sử dụng công cụ | Giúp mô hình quyết định khi nào nên gọi công cụ và chọn công cụ nào. |
| `inputSchema` | JSON Schema mô tả arguments | Hướng dẫn mô hình tạo JSON đầu vào theo cấu trúc, kiểu dữ liệu và trường bắt buộc. |

`ToolDefinition` được cung cấp bởi `ToolCallback.getToolDefinition()`. Khi mô hình trả về yêu cầu gọi công cụ, Spring AI dùng tên công cụ để phân giải callback tương ứng; callback nhận chuỗi JSON arguments và trả về kết quả dạng chuỗi để đưa vào vòng hội thoại.

Ranh giới trách nhiệm có thể tóm tắt như sau:

- `ToolDefinition`: mô tả công cụ cho mô hình.
- `ToolCallback`: thực thi công cụ trong ứng dụng.
- Service nghiệp vụ: kiểm tra quyền, áp dụng quy tắc miền và truy cập hệ thống dữ liệu.

Mô hình chỉ đề xuất lời gọi và arguments. Ứng dụng chịu trách nhiệm thực hiện hoặc từ chối yêu cầu đó.

## Khi nào cần JSON Schema riêng?

Spring AI có thể tự sinh schema từ chữ ký phương thức, record hoặc kiểu input của `FunctionToolCallback`. Cách tự sinh phù hợp với phần lớn công cụ thông thường. Schema riêng hữu ích khi:

- Cần cấu trúc lồng nhau, union type, enum hoặc ràng buộc định dạng cụ thể.
- Hợp đồng đầu vào phải tương thích với một API hoặc giao thức đã tồn tại.
- Cần kiểm soát chính xác tên trường, trường bắt buộc và mô tả mà mô hình nhìn thấy.
- Định nghĩa công cụ được tạo động từ cấu hình hoặc metadata bên ngoài.
- Callback là adapter đến dịch vụ từ xa, MCP server hoặc hệ thống không có method Java tương ứng.
- Chữ ký Java đơn giản không thể thể hiện đầy đủ hợp đồng mà provider yêu cầu.

Nếu schema chỉ gồm một vài trường đơn giản, nên ưu tiên cơ chế tự sinh từ `inputType` và `@ToolParam`. Khi dùng schema riêng, ứng dụng phải tự bảo đảm schema và phần parser trong callback luôn đồng bộ.

## Xây dựng ToolDefinition bằng builder

Spring AI cung cấp `ToolDefinition.builder()` để tạo implementation mặc định `DefaultToolDefinition`. Ví dụ một công cụ tra cứu tồn kho theo mã SKU và mã kho tùy chọn:

```java
import org.springframework.ai.tool.definition.ToolDefinition;

ToolDefinition definition = ToolDefinition.builder()
        .name("lookupInventory")
        .description("Tra cứu số lượng tồn kho của một sản phẩm tại kho được chỉ định. Dùng khi cần kiểm tra khả năng đáp ứng đơn hàng.")
        .inputSchema("""
                {
                  "type": "object",
                  "properties": {
                    "sku": {
                      "type": "string",
                      "description": "Mã SKU chính xác của sản phẩm, ví dụ SKU-100"
                    },
                    "warehouseCode": {
                      "type": "string",
                      "description": "Mã kho cần tra cứu; bỏ qua để dùng kho mặc định của ứng dụng"
                    }
                  },
                  "required": ["sku"],
                  "additionalProperties": false
                }
                """)
        .build();
```

`name` và `description` là thông tin mô hình dùng để nhận diện công cụ. `inputSchema` là một chuỗi JSON Schema. Trong ví dụ, `sku` là trường bắt buộc; `warehouseCode` có thể vắng mặt. `additionalProperties: false` thể hiện schema không chấp nhận thuộc tính ngoài danh sách đã công bố.

Builder kiểm tra và đóng gói các giá trị thành `ToolDefinition`; việc tạo builder không có nghĩa schema đã được provider xác nhận hoặc arguments thực tế sẽ hợp lệ. Hãy kiểm tra JSON Schema độc lập và thử với đúng model/provider mà ứng dụng sử dụng.

## Những phần quan trọng trong JSON Schema

Một schema đầu vào thường bắt đầu bằng object, khai báo `properties` và danh sách `required`:

```json
{
  "type": "object",
  "properties": {
    "orderId": {
      "type": "string",
      "description": "Mã đơn hàng, ví dụ ORD-2026-001",
      "pattern": "^ORD-[A-Z0-9-]+$"
    },
    "includeItems": {
      "type": "boolean",
      "description": "Có đưa danh sách mặt hàng vào kết quả hay không"
    },
    "status": {
      "type": "string",
      "enum": ["PENDING", "CONFIRMED", "CANCELLED"]
    }
  },
  "required": ["orderId"]
}
```

Các từ khóa thường dùng:

| Từ khóa | Mục đích | Ví dụ |
| --- | --- | --- |
| `type` | Kiểu JSON của object hoặc thuộc tính | `object`, `string`, `integer`, `boolean`, `array` |
| `properties` | Khai báo các thuộc tính hợp lệ của object | `sku`, `warehouseCode` |
| `required` | Danh sách tên trường phải xuất hiện | `["sku"]` |
| `description` | Giải thích mục đích hoặc định dạng của trường | `Mã SKU chính xác` |
| `enum` | Giới hạn một trường vào tập giá trị hữu hạn | `PENDING`, `CONFIRMED`, `CANCELLED` |
| `pattern` | Ràng buộc chuỗi theo biểu thức chính quy | `^ORD-[A-Z0-9-]+$` |
| `minimum`, `maximum` | Giới hạn số | Số lượng từ 1 đến 50 |
| `items` | Schema của phần tử trong mảng | Mỗi phần tử là chuỗi hoặc object |
| `additionalProperties` | Kiểm soát trường ngoài `properties` | `false` để từ chối trường không khai báo nếu provider hỗ trợ |

### Required, optional và nullable

Trong JSON Schema, `required` là mảng ở cấp object, không phải thuộc tính boolean bên trong mỗi property. Trường không xuất hiện trong mảng `required` là optional. Optional không đồng nghĩa nullable: nếu property có `type: "string"`, giá trị `null` vẫn không hợp lệ khi trường xuất hiện.

Để một trường nhận chuỗi hoặc `null`, schema JSON Schema tổng quát có thể dùng:

```json
{
  "type": ["string", "null"]
}
```

Một số provider hoặc chế độ strict chỉ hỗ trợ một tập con JSON Schema và có thể yêu cầu cách biểu diễn khác, ví dụ union bằng `anyOf` hoặc bắt buộc khai báo tất cả thuộc tính trong `required`. Hãy xem tài liệu của endpoint/model và schema cuối cùng mà integration gửi đi. Không nên giả định mọi từ khóa JSON Schema đều được mọi provider chấp nhận.

### Schema phải mô tả đúng hợp đồng nghiệp vụ

Mô tả càng rõ thì mô hình càng dễ tạo arguments đúng. Hãy ghi rõ định dạng mã, đơn vị, múi giờ, phạm vi số, giá trị enum và ý nghĩa khi bỏ qua trường. Không đưa thông tin bí mật hoặc thông tin xác thực vào schema. Schema là dữ liệu gửi đến nhà cung cấp mô hình.

## ToolCallback thực thi theo ToolDefinition riêng

Để sử dụng schema riêng và kiểm soát cách phân tích arguments, có thể triển khai `ToolCallback`. Ví dụ sau minh họa công cụ tra cứu tồn kho bằng Jackson:

```java
import java.util.Iterator;
import java.util.Set;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;

public final class InventoryLookupTool implements ToolCallback {

    private static final Set<String> ALLOWED_FIELDS = Set.of("sku", "warehouseCode");

    private final ObjectMapper objectMapper;
    private final InventoryService inventoryService;
    private final ToolDefinition toolDefinition;

    public InventoryLookupTool(
            ObjectMapper objectMapper,
            InventoryService inventoryService) {
        this.objectMapper = objectMapper;
        this.inventoryService = inventoryService;
        this.toolDefinition = ToolDefinition.builder()
                .name("lookupInventory")
                .description("Tra cứu số lượng tồn kho theo SKU và mã kho tùy chọn")
                .inputSchema("""
                        {
                          "type": "object",
                          "properties": {
                            "sku": {
                              "type": "string",
                              "description": "Mã SKU chính xác, ví dụ SKU-100",
                              "pattern": "^SKU-[A-Z0-9-]{1,32}$"
                            },
                            "warehouseCode": {
                              "type": "string",
                              "description": "Mã kho; bỏ qua để dùng kho mặc định"
                            }
                          },
                          "required": ["sku"],
                          "additionalProperties": false
                        }
                        """)
                .build();
    }

    @Override
    public ToolDefinition getToolDefinition() {
        return this.toolDefinition;
    }

    @Override
    public String call(String toolInput) {
        if (toolInput == null || toolInput.isBlank()) {
            throw new IllegalArgumentException("Arguments không được để trống");
        }

        final JsonNode arguments;
        try {
            arguments = this.objectMapper.readTree(toolInput);
        }
        catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Arguments của lookupInventory không phải JSON hợp lệ", ex);
        }

        if (arguments == null || !arguments.isObject()) {
            throw new IllegalArgumentException("Arguments phải là một JSON object");
        }

        Iterator<String> fieldNames = arguments.fieldNames();
        while (fieldNames.hasNext()) {
            String fieldName = fieldNames.next();
            if (!ALLOWED_FIELDS.contains(fieldName)) {
                throw new IllegalArgumentException("Thuộc tính không được hỗ trợ: " + fieldName);
            }
        }

        JsonNode skuNode = arguments.get("sku");
        if (skuNode == null || !skuNode.isTextual() || skuNode.asText().isBlank()) {
            throw new IllegalArgumentException("sku là chuỗi bắt buộc và không được để trống");
        }

        String sku = skuNode.asText();
        if (!sku.matches("SKU-[A-Z0-9-]{1,32}")) {
            throw new IllegalArgumentException("sku không đúng định dạng");
        }

        String warehouseCode = null;
        JsonNode warehouseNode = arguments.get("warehouseCode");
        if (warehouseNode != null) {
            if (!warehouseNode.isTextual() || warehouseNode.asText().isBlank()) {
                throw new IllegalArgumentException("warehouseCode phải là chuỗi không rỗng nếu được cung cấp");
            }
            warehouseCode = warehouseNode.asText();
        }

        InventorySummary summary = this.inventoryService.findStock(sku, warehouseCode);
        try {
            return this.objectMapper.writeValueAsString(summary);
        }
        catch (JsonProcessingException ex) {
            throw new IllegalStateException("Không thể chuyển kết quả tồn kho thành JSON", ex);
        }
    }
}
```

`InventoryService` và `InventorySummary` là kiểu nghiệp vụ do ứng dụng định nghĩa. Ví dụ cố ý kiểm tra arguments trong callback dù schema đã mô tả `pattern`, trường bắt buộc và `additionalProperties`. Schema hướng dẫn mô hình và provider; callback phải bảo vệ ranh giới thực thi vì request vẫn có thể sai, bị gọi trực tiếp hoặc đến từ một integration có mức kiểm tra khác.

Trong ví dụ, `call(String toolInput)` nhận JSON arguments. `getToolDefinition()` trả về cùng một định nghĩa đã tạo trong constructor. `getToolMetadata()` có implementation mặc định trong Spring AI; chỉ cần cấu hình metadata riêng khi muốn thay đổi hành vi như `returnDirect` hoặc result converter.

## Đăng ký callback với ChatClient

Có thể đăng ký callback bằng Spring bean để tái sử dụng và inject service cần thiết:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.ai.tool.ToolCallback;

@Configuration(proxyBeanMethods = false)
class InventoryToolConfiguration {

    @Bean
    ToolCallback inventoryLookupTool(
            ObjectMapper objectMapper,
            InventoryService inventoryService) {
        return new InventoryLookupTool(objectMapper, inventoryService);
    }
}
```

Sau đó truyền callback vào request:

```java
String answer = chatClient.prompt()
        .user("Kiểm tra tồn kho sản phẩm SKU-100 tại kho HN-01")
        .toolCallbacks(inventoryLookupTool)
        .call()
        .content();
```

Khi truyền trực tiếp bằng `.toolCallbacks(...)`, công cụ được gắn vào request cụ thể. Cách này giúp kiểm soát rõ công cụ nào được cung cấp trong từng luồng hội thoại. Tránh đăng ký callback có quyền rộng làm công cụ mặc định cho mọi request nếu không cần thiết.

## ToolDefinition và ToolMetadata có vai trò khác nhau

`ToolDefinition` chứa thông tin mô hình nhìn thấy: tên, mô tả và input schema. `ToolMetadata` chứa các thiết lập điều khiển cách Spring AI xử lý callback, chẳng hạn kết quả có được trả thẳng cho client hay gửi lại mô hình để tiếp tục tổng hợp.

| Thành phần | Chứa gì? | Ví dụ |
| --- | --- | --- |
| `ToolDefinition` | Contract công khai cho mô hình | `lookupInventory`, mô tả tra cứu tồn kho, schema có `sku` và `warehouseCode`. |
| `ToolMetadata` | Metadata điều khiển xử lý | `returnDirect`, result converter. |
| `ToolCallback` | Hành vi thực thi | Parse JSON, kiểm tra arguments, gọi `InventoryService`, serialize kết quả. |

Không đưa logic phân quyền vào `ToolDefinition`. Mô tả và schema không phải ranh giới bảo mật. Callback và service cần xác thực người gọi, kiểm tra tenant và quyền truy cập tài nguyên dựa trên ngữ cảnh tin cậy của ứng dụng.

## Thiết kế schema dễ hiểu và ổn định

Một schema tốt nên đáp ứng các nguyên tắc sau:

1. **Tên công cụ duy nhất và có ý nghĩa:** dùng động từ và đối tượng, ví dụ `lookupInventory`, `cancelOrder`, `searchCustomers`.
2. **Description nêu rõ mục đích:** nói công cụ làm gì, khi nào nên gọi và giới hạn quan trọng.
3. **Trường đầu vào có tên cụ thể:** ưu tiên `customerId`, `fromDate`, `warehouseCode` thay vì `value`, `type` hoặc `arg1`.
4. **Required tối thiểu nhưng chính xác:** chỉ bắt buộc trường thật sự cần thiết; mô hình không nên phải bịa giá trị cho trường không có dữ liệu.
5. **Ràng buộc kiểu và miền giá trị:** dùng `enum`, `pattern`, `minimum`, `maximum`, `items` khi provider hỗ trợ.
6. **Tránh trường dư thừa:** không đưa `tenantId`, `userId`, API key hoặc dữ liệu lấy được từ context xác thực vào schema.
7. **Giữ schema đồng bộ với parser:** mọi field được công bố phải có quy tắc xử lý trong callback; mọi field callback dùng phải được mô tả.
8. **Kiểm tra tương thích provider:** một số model/API hỗ trợ JSON Schema ở mức khác nhau; schema quá phức tạp có thể bị từ chối.

Nếu schema thay đổi theo phiên bản API, nên quản lý như một hợp đồng có version. Khi đổi tên trường, kiểu dữ liệu hoặc ý nghĩa của trường, cần cập nhật parser, kiểm thử và mô tả công cụ cùng lúc.

## Xác thực đầu vào và bảo vệ service

JSON Schema không thay thế xác thực runtime. Callback cần kiểm tra:

- JSON có hợp lệ và root có phải object hay không.
- Các trường required có mặt và đúng kiểu không.
- Giá trị có đúng định dạng, giới hạn và tập lựa chọn không.
- Có thuộc tính ngoài schema không, nếu hợp đồng cấm thuộc tính bổ sung.
- Tài nguyên có tồn tại và nằm trong phạm vi người dùng/tenant được phép không.
- Thao tác có cần xác nhận, idempotency, timeout hoặc audit không.

Thông tin xác thực như principal và tenant nên được truyền qua cơ chế context của ứng dụng, không yêu cầu mô hình tạo ra. Nếu callback cần `ToolContext`, có thể override `call(String toolInput, ToolContext toolContext)` để nhận context và chuyển thông tin tin cậy đến service. Không ghi token hoặc credential vào log và không đưa chúng vào kết quả trả lại mô hình.

## Kiểm thử ToolDefinition và callback

Nên kiểm tra schema và hành vi thực thi độc lập trước khi chạy integration với model thật.

### Kiểm tra ToolDefinition

```java
ToolDefinition definition = inventoryLookupTool.getToolDefinition();

assertThat(definition.name()).isEqualTo("lookupInventory");
assertThat(definition.description()).isNotBlank();
assertThat(definition.inputSchema()).contains("\"required\": [\"sku\"]");
assertThat(definition.inputSchema()).contains("warehouseCode");
```

Ngoài kiểm tra chuỗi, nên parse schema bằng thư viện JSON và dùng JSON Schema validator tương thích dialect/schema mà provider yêu cầu để xác nhận các ví dụ hợp lệ và không hợp lệ.

### Kiểm tra callback

```java
String result = inventoryLookupTool.call("""
        {"sku":"SKU-100","warehouseCode":"HN-01"}
        """);

assertThat(result).contains("SKU-100");
verify(inventoryService).findStock("SKU-100", "HN-01");
```

Các ca kiểm thử quan trọng:

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| JSON hợp lệ với `sku` | Callback gọi service với SKU đúng. |
| Bỏ qua `warehouseCode` | Callback chuyển `null` để service dùng kho mặc định theo hợp đồng. |
| Thiếu `sku` | Callback từ chối trước khi gọi service. |
| `sku` sai kiểu hoặc sai định dạng | Callback từ chối đầu vào. |
| JSON không phải object hoặc JSON sai cú pháp | Callback trả lỗi đầu vào có kiểm soát. |
| Có thuộc tính ngoài schema | Callback từ chối trường không được hỗ trợ. |
| Service timeout hoặc không tìm thấy dữ liệu | Lỗi được xử lý theo hợp đồng ứng dụng, không lộ stack trace. |
| Người dùng không có quyền truy cập kho | Service từ chối dù JSON hợp lệ. |

Integration test với model thật hoặc model giả có thể xác nhận provider nhận schema và tạo tool call đúng. Tuy nhiên, unit test của callback vẫn cần thiết vì logic xác thực và quyền phải đúng ngay cả khi không có mô hình tham gia.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Mô hình không gọi công cụ | Tên/mô tả không rõ hoặc công cụ không được gắn vào request | Cải thiện description, kiểm tra `.toolCallbacks(...)` và khả năng tool calling của model. |
| Provider từ chối schema | Dùng từ khóa hoặc cấu trúc không được endpoint hỗ trợ | Kiểm tra dialect và giới hạn schema của provider; giản lược schema nếu cần. |
| Mô hình gửi field sai tên | Schema và parser không đồng bộ hoặc tên field mơ hồ | Dùng một tên chuẩn trong schema, ví dụ và parser; kiểm thử JSON thực tế. |
| Callback không tìm thấy | `name` không khớp tên tool call hoặc trùng với callback khác | Bảo đảm tên duy nhất trong tập công cụ và giữ tên ổn định. |
| JSON hợp lệ nhưng service vẫn nhận dữ liệu sai | Chỉ dựa vào schema, thiếu kiểm tra runtime | Xác thực kiểu, định dạng, giới hạn và quy tắc miền trong callback/service. |
| Kết quả không được mô hình hiểu | Output quá lớn, thiếu cấu trúc hoặc chứa dữ liệu không cần thiết | Trả DTO/JSON tối thiểu với trường và trạng thái rõ ràng. |

## Quy trình triển khai

1. Xác định hợp đồng input mà mô hình cần nhìn thấy.
2. Viết JSON Schema và kiểm tra tính hợp lệ độc lập.
3. Tạo `ToolDefinition` với tên, mô tả và schema.
4. Triển khai `ToolCallback` để parse, xác thực và gọi service.
5. Đăng ký callback theo phạm vi request phù hợp bằng `.toolCallbacks(...)`.
6. Kiểm thử schema, dữ liệu hợp lệ/không hợp lệ, lỗi service và quyền truy cập.
7. Chạy integration test với model/provider mục tiêu để xác nhận schema được chấp nhận và mô hình gọi đúng công cụ.
8. Theo dõi lỗi, thời gian thực thi và kết quả callback trong môi trường vận hành.

Khi tách riêng định nghĩa và thực thi, ứng dụng có thể thay đổi JSON Schema mà không phải thay đổi toàn bộ cấu trúc service, miễn là callback tiếp tục đáp ứng hợp đồng mới. `ToolDefinition` giúp mô hình hiểu cách gọi; `ToolCallback` và service bảo đảm lời gọi được kiểm tra và thực hiện đúng trong ứng dụng.

## Tài liệu tham khảo

- [Spring AI 1.0 Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html)
- [Spring AI 1.0.x API — ToolDefinition](https://docs.spring.io/spring-ai/docs/1.0.x/api/org/springframework/ai/tool/definition/ToolDefinition.html)
- [Spring AI 1.0.x API — ToolCallback](https://docs.spring.io/spring-ai/docs/1.0.x/api/org/springframework/ai/tool/ToolCallback.html)
- [JSON Schema — Object](https://json-schema.org/understanding-json-schema/reference/object)
- [JSON Schema — Types](https://json-schema.org/understanding-json-schema/reference/type)
