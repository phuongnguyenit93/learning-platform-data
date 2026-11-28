# Khác biệt tên công cụ, schema và kiểu dữ liệu được chấp nhận

> **Phạm vi:** Spring AI **2.1.0**, tập trung vào cách mô hình nhận diện công cụ qua `name`, đọc `inputSchema` và sinh đối số JSON. Ví dụ dùng `@Tool`, `ToolCallback`, `@ToolParam` và `ToolContext`; các quy tắc của từng nhà cung cấp có thể thay đổi theo API, phiên bản mô hình và chế độ gọi công cụ.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao cùng một `ToolCallback` chạy được với mô hình A nhưng bị từ chối hoặc tạo đối số sai với mô hình B.
2. Đặt tên công cụ ổn định, tránh xung đột tên khi phối hợp công cụ nội bộ và MCP.
3. Thiết kế JSON Schema đủ rõ và đủ đơn giản để nhiều nhà cung cấp hiểu; phân biệt **trường bắt buộc**, **trường có thể bỏ qua** và **giá trị `null`**.
4. Chọn kiểu dữ liệu phù hợp cho đối số: chuỗi, số, boolean, enum, mảng, đối tượng, ngày giờ, tiền tệ.
5. Kiểm tra cả tính tương thích với provider lẫn quy tắc nghiệp vụ, quyền truy cập trước khi thực thi.

## 2. Ba lớp hợp đồng trong tool calling

Người dùng hỏi “Kho A còn 5 sản phẩm SKU-01 không?”. Ứng dụng dùng Spring AI để công bố một công cụ kiểm tra tồn kho. Mô hình nhìn thấy **định nghĩa** công cụ, có thể yêu cầu gọi bằng tên và JSON, nhưng **ứng dụng Java** mới là bên thực thi truy vấn kho.

```text
Java @Tool / ToolCallback
      │ tạo ToolDefinition { name, description, inputSchema }
      ▼
Spring AI ChatClient ── chuyển định nghĩa sang API của provider ──► Mô hình
      ▲                                                          │
      │                                             yêu cầu tool_name + JSON
      │                                                          ▼
ToolCallingAdvisor / ToolCallingManager ── tra tên, chuyển kiểu, gọi Java method
      │
      └── kết quả công cụ ──► mô hình ──► câu trả lời cuối
```

Ba lớp cần phân biệt:

| Lớp | Quyết định điều gì? | Rủi ro tương thích |
| --- | --- | --- |
| **Spring AI** | Sinh `ToolDefinition` từ Java, chuyển callback thành công cụ, điều phối kết quả | Tên trùng, schema sinh ra không như dự tính, ánh xạ JSON sang Java lỗi |
| **API của provider** | Định dạng danh sách tools, quy tắc tên, phần JSON Schema được hỗ trợ, chế độ strict | HTTP 400 khi tên/schema không hợp lệ, tính năng không được hỗ trợ |
| **Mô hình cụ thể** | Có gọi công cụ hay không; chọn công cụ và tạo giá trị đối số | Chọn sai công cụ, thiếu trường, kiểu không đúng dù request đã được API chấp nhận |

Một mục “Tool calling: Yes” trong bảng hỗ trợ của Spring AI chỉ chứng minh integration có đường đi tool calling. Nó **không đảm bảo** mọi mô hình của provider đều hiểu mọi schema, mọi kiểu Java hoặc trả đối số chính xác.

## 3. Khác biệt về tên công cụ

### 3.1. Tên là khóa định tuyến, không phải nhãn hiển thị

Trong Spring AI:

- `@Tool(name = "...")` dùng tên tường minh; nếu bỏ qua, mặc định là tên phương thức Java.
- `ToolDefinition.name()` được gửi tới mô hình. `ToolCallingManager` dựa vào tên mà mô hình trả về để tìm callback.
- `description` giải thích **khi nào** và **vì sao** sử dụng công cụ; tên ngắn gọn vẫn nên đi kèm mô tả chính xác.

Hãy chọn một tập quy tắc **bảo thủ để dễ di chuyển giữa provider**:

| Tiêu chí | Quy ước ứng dụng nên áp dụng |
| --- | --- |
| Ký tự | Chữ ASCII `a-z`, chữ số `0-9`, dấu gạch dưới `_` |
| Ký tự đầu | Bắt đầu bằng chữ cái |
| Độ dài | Không quá 64 ký tự |
| Cách đặt | `snake_case`, có động từ và đối tượng: `lookup_stock_v1` |
| Ý nghĩa | Tên cố định theo hợp đồng; mô tả rõ đầu vào, kết quả, trường hợp sử dụng |
| Duy nhất | Không có hai công cụ cùng tên trong tập công cụ của một request |

Đây là **quy ước liên provider được đề xuất**, không phải một biểu thức chính quy bắt buộc của tất cả nhà cung cấp. Chẳng hạn, một số API chấp nhận dấu gạch ngang hoặc dấu chấm, nhưng sử dụng chúng có thể làm mất tính di động.

| Tên | Đánh giá | Vì sao |
| --- | --- | --- |
| `lookup_stock_v1` | Nên dùng | Đơn giản, nhất quán, có phiên bản hợp đồng |
| `lookupStock` | Có thể dùng | Hợp lệ ở nhiều API nhưng khó chuẩn hóa với tên dạng `snake_case` |
| `Kiểm tra kho` | Tránh | Khoảng trắng, dấu tiếng Việt không phù hợp với nhiều API |
| `stock/check()` | Tránh | Dấu `/` và ngoặc có thể bị từ chối |
| `lookup_stock_v1` xuất hiện hai lần | Lỗi thiết kế | Tên không còn xác định duy nhất callback cần gọi |

Theo tài liệu Spring AI 2.1.0, `ChatClient` kiểm tra tên trùng khi hợp nhất các công cụ từ `.defaultTools(...)` và `.tools(...)` và có thể ném `IllegalStateException`. Nếu tự xây vòng lặp trực tiếp trên `ChatModel` với danh sách callback thủ công, không được giả định có cùng bước kiểm tra đó; hãy xác minh tên duy nhất trước khi gửi request. Với MCP, tiền tố tên giữa các MCP server không tự giải quyết mọi trường hợp trùng tên với công cụ Java tại chỗ.

**Đổi tên có tác động tới khả năng tương thích:** tên mà mô hình trả về phải khớp tên callback ở request hiện tại. Nếu thay `lookup_stock_v1` bằng `lookup_stock_v2`, cần cập nhật test, allowlist, metric và mọi cấu hình provider chọn công cụ theo tên; không “đổi nhãn” tùy tiện trong thời gian chạy.

## 4. Schema là hợp đồng mà mô hình đọc

`ToolDefinition` của Spring AI gồm `name()`, `description()` và `inputSchema()`. `inputSchema` là chuỗi JSON Schema mô tả đối số, thường có một **object** gốc với `properties`, `type`, `description` và `required`. Với phương thức `@Tool`, Spring AI sử dụng `JsonSchemaGenerator` để suy schema từ tham số; `FunctionToolCallback` cũng có thể tạo schema từ `inputType`.

Ví dụ công cụ đọc tồn kho:

```java
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.ai.tool.ToolContext;

record StockResult(String sku, long available, boolean enough) {}

interface StockService {
    StockResult check(String tenantId, String sku, int units, String warehouseCode);
}

final class StockTools {

    private final StockService stockService;

    StockTools(StockService stockService) {
        this.stockService = stockService;
    }

    @Tool(
        name = "lookup_stock_v1",
        description = "Kiểm tra số lượng tồn của một SKU. " +
                      "Chỉ dùng khi người dùng hỏi tình trạng còn hàng; " +
                      "không tạo đơn, giữ hàng hoặc thay đổi kho."
    )
    public StockResult lookupStock(
        @ToolParam(description = "Mã SKU, ví dụ PEN-031")
        String sku,

        @ToolParam(description = "Số đơn vị cần kiểm tra; số nguyên từ 1 đến 1000")
        Integer units,

        @ToolParam(
            description = "Mã kho; bỏ qua để dùng kho mặc định",
            required = false
        )
        String warehouseCode,

        ToolContext toolContext
    ) {
        if (sku == null || !sku.matches("[A-Z0-9-]{3,32}")) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (units == null || units < 1 || units > 1000) {
            throw new IllegalArgumentException("Số lượng không hợp lệ");
        }

        Object rawTenant = toolContext.getContext().get("tenantId");
        if (!(rawTenant instanceof String tenantId) || tenantId.isBlank()) {
            throw new SecurityException("Thiếu tenant đã xác thực");
        }

        return stockService.check(tenantId, sku, units, warehouseCode);
    }
}
```

Phương thức Java vẫn phải kiểm tra tenant/quyền truy cập trên bản ghi trong `StockService`. `ToolContext` nhận dữ liệu từ ứng dụng, **không phải đối số do mô hình tự sinh**; không nhận `tenantId` từ một tham số có thể bị prompt điều khiển.

Cách truyền công cụ và ngữ cảnh ở lớp sử dụng:

```java
String answer = ChatClient.create(chatModel)
    .prompt()
    .user("Kho còn 5 sản phẩm PEN-031 không?")
    .tools(new StockTools(stockService))
    .toolContext(Map.of("tenantId", authenticatedTenantId))
    .call()
    .content();
```

`ChatClient` trong Spring AI 2.1.0 điều phối vòng lặp thông qua `ToolCallingAdvisor`; `ChatModel.call(...)` trực tiếp chỉ trả về yêu cầu gọi công cụ, còn ứng dụng phải tự xử lý vòng lặp nếu dùng API cấp thấp.

### 4.1. Đọc schema thực tế thay vì đoán từ chữ ký

Với ví dụ trên, ý nghĩa mong muốn của đầu vào có thể mô tả bằng schema **minh họa, rút gọn**:

```json
{
  "type": "object",
  "properties": {
    "sku": {
      "type": "string",
      "description": "Mã SKU, ví dụ PEN-031"
    },
    "units": {
      "type": "integer",
      "description": "Số đơn vị cần kiểm tra; từ 1 đến 1000"
    },
    "warehouseCode": {
      "type": "string",
      "description": "Mã kho; bỏ qua để dùng kho mặc định"
    }
  },
  "required": ["sku", "units"]
}
```

*Đây là mô hình khái niệm, không phải cam kết về chuỗi JSON chính xác mà một phiên bản `JsonSchemaGenerator` xuất ra.* Có thể kiểm tra sản phẩm thực bằng:

```java
ToolCallback[] callbacks = ToolCallbacks.from(new StockTools(stockService));
for (ToolCallback callback : callbacks) {
    ToolDefinition definition = callback.getToolDefinition();
    System.out.println(definition.name());
    System.out.println(definition.inputSchema());
}
```

Đặt imports tương ứng cho `ToolCallback`, `ToolCallbacks` và `ToolDefinition` trong mã thực tế. Nếu schema sinh ra không đáp ứng API mục tiêu, hãy sửa kiểu/annotation hoặc tạo `ToolDefinition` tường minh rồi kiểm tra lại với provider đó.

### 4.2. `required`, bỏ qua và `null` là ba ý khác nhau

Giả sử `warehouseCode` là tùy chọn:

- **Bỏ qua:** `{"sku":"PEN-031","units":5}` — không có key `warehouseCode`.
- **Gửi `null`:** `{"sku":"PEN-031","units":5,"warehouseCode":null}` — có key nhưng giá trị rỗng kiểu JSON.
- **Gửi chuỗi rỗng:** `{"sku":"PEN-031","units":5,"warehouseCode":""}` — có key là chuỗi; chưa chắc cùng nghĩa với hai tình huống trên.

Trong Spring AI, `@ToolParam(required = false)` (hoặc `@Nullable` theo tài liệu) dùng để biểu thị tham số không bắt buộc. Nhưng nhà cung cấp có thể yêu cầu biểu diễn schema khác. Ví dụ **OpenAI function calling ở strict mode** yêu cầu mọi field trong `properties` đều được liệt kê trong `required` và `additionalProperties: false` cho mỗi object. Khi muốn biểu đạt “không có giá trị”, schema strict thường dùng union kiểu `["string", "null"]`, như sau:

```json
{
  "type": "object",
  "properties": {
    "sku": {"type": "string"},
    "units": {"type": "integer"},
    "warehouseCode": {"type": ["string", "null"]}
  },
  "required": ["sku", "units", "warehouseCode"],
  "additionalProperties": false
}
```

Hai schema này **không tương đương**: schema strict luôn có key `warehouseCode`, nhưng cho phép giá trị `null`. Đừng cho rằng chỉ thêm `@ToolParam(required = false)` sẽ tự động tạo schema strict đúng yêu cầu của OpenAI. Chế độ strict và cách cấu hình nó tùy API/provider; cần xem **payload cuối cùng gửi lên provider**, không suy từ annotation Java.

### 4.3. Mô tả giúp lựa chọn, schema giúp tạo đối số

`@Tool(description = "...")` nên trả lời rõ: công cụ làm gì, khi nào gọi và giới hạn tác dụng. `@ToolParam(description = "...")` nêu định dạng và ý nghĩa từng trường. Những mô tả này làm tăng cơ hội mô hình chọn đúng, nhưng **không phải bộ kiểm tra dữ liệu hay chính sách phân quyền**.

Ví dụ, lời mô tả “`units` từ 1 đến 1000” không bảo đảm mô hình sẽ luôn trả số trong khoảng đó. Code phải kiểm tra phạm vi ngay cả khi dùng strict schema.

## 5. Khác biệt kiểu dữ liệu được chấp nhận

Java có hệ kiểu phong phú hơn JSON. Mô hình thường sinh **JSON**, sau đó Spring AI/Jackson chuyển thành tham số Java. Vì thế cần kiểm tra **cả khả năng biểu diễn trong JSON Schema lẫn khả năng chuyển kiểu khi chạy**.

| Kiểu ở biên công cụ | Biểu diễn JSON nên ưu tiên | Điểm dễ sai và cách xử lý |
| --- | --- | --- |
| `String`, mã SKU/ID | `"PEN-031"` | Giữ ID dưới dạng chuỗi, đặc biệt nếu có số 0 đầu; kiểm tra pattern/độ dài |
| `int`/`Integer`, `long`/`Long` | `5` | JSON integer; không mặc định chấp nhận `"5"`, `5.5` hay giá trị vượt miền Java |
| `double`/`Double` | `12.5` | JSON number; lưu ý NaN, Infinity không phải JSON chuẩn |
| `boolean`/`Boolean` | `true` / `false` | Không dựa vào ép kiểu từ `"yes"` hoặc `"true"` |
| `enum` | `"AVAILABLE"` | Giới hạn bằng `enum` trong schema; xử lý tên lạ và chữ hoa/thường |
| `List<String>` / `List<DTO>` | `["A","B"]` / `[{"code":"A"}]` | Khai báo `items`; tránh danh sách quá lớn hoặc phần tử hỗn hợp |
| Java `record` / DTO | `{"sku":"PEN-031","units":5}` | Trường lồng nhau tăng độ phức tạp; xem schema thực tế |
| `Map<String, Object>` | `{"key":"value"}` | Key động khó ràng buộc, dễ xung đột với provider strict; ưu tiên DTO xác định |
| `Optional<T>` / `@Nullable T` | Thiếu key hoặc `null` tùy hợp đồng | Đánh giá cách sinh schema và Jackson ánh xạ; tránh đồng nhất hai trường hợp |
| `LocalDate`, `Instant`, `UUID` | Chuỗi ISO-8601 / UUID chuẩn | Chỉ rõ format trong mô tả; tự parse, kiểm tra múi giờ và tính hợp lệ |
| `BigDecimal` / tiền tệ | Chuỗi thập phân hoặc số nguyên đơn vị nhỏ nhất | Tránh dựa vào làm tròn floating point; quy định đơn vị và kiểm tra chính xác |
| `byte[]` / file / ảnh | Không dùng trực tiếp như “input ảnh” tùy ý | Tool arguments JSON khác với kênh multimodal; thiết kế ID tài nguyên hoặc API riêng |
| Kiểu đa hình / `oneOf` / cấu trúc đệ quy | Nếu có thể, chia thành công cụ hoặc DTO phẳng | Một số provider chỉ hỗ trợ tập con JSON Schema |

**Ví dụ ngược cần phân biệt:**

```json
{"sku": "PEN-031", "units": 5}
```

là đối số hợp lý, nhưng:

```json
{"sku": 31, "units": "năm"}
```

sai loại dữ liệu mong đợi. Lớp chuyển kiểu đôi khi có thể ép `"5"` thành số tùy cấu hình Jackson; không nên coi hành vi ép kiểu đó là cam kết tương thích. Bật kiểm tra đầu vào rõ ràng, báo lỗi có cấu trúc và không cho dữ liệu sai đi tiếp tới hệ thống nghiệp vụ.

### Thiết kế bền vững cho dữ liệu phức tạp

Thay vì:

```java
void updateOrder(Map<String, Object> arbitraryPayload);
```

hãy định nghĩa DTO/record có trường cụ thể và giới hạn:

```java
record OrderLookupRequest(String orderId, String locale) {}
```

Với hai thao tác có hình dạng đối số hoàn toàn khác, chẳng hạn “tra cứu đơn” và “cập nhật địa chỉ”, nên tạo **hai công cụ riêng biệt** có tên, mô tả, quyền và schema riêng. Không dùng một công cụ khổng lồ với nhiều trường chỉ có ý nghĩa theo các nhánh điều kiện mơ hồ.

## 6. Vì sao từng provider có hành vi khác nhau?

Bảng dưới tóm tắt **điểm cần kiểm tra**, không khẳng định tất cả phiên bản mô hình có cùng hạn chế:

| Provider / đường tích hợp | Tên và schema cần để ý | Điều cần thử với mô hình thực |
| --- | --- | --- |
| **OpenAI Chat Completions / Responses** | Function có tên/parameters; strict mode hạn chế tập JSON Schema, yêu cầu `required` đầy đủ và `additionalProperties: false` | Schema có bị API từ chối không; có trả đúng JSON, đúng enum/nullable không; sự khác biệt strict mặc định theo endpoint |
| **Anthropic Claude** | Công cụ người dùng có `name`, `description`, `input_schema`; API cung cấp chế độ strict với quy tắc và giới hạn riêng | Tên, schema lồng nhau, dữ liệu tùy chọn; phân biệt `tool_use` và phản hồi cuối |
| **Google GenAI / Gemini** | `FunctionDeclaration` và schema tham số theo API/SDK Google; tên và hình dạng schema có giới hạn riêng | JSON Schema phức tạp có được chấp nhận không; chế độ chọn công cụ `AUTO`, `ANY`, `VALIDATED` ảnh hưởng kết quả thế nào |
| **Ollama** | Spring AI có integration tool calling, nhưng mức tuân thủ đối số phụ thuộc mô hình nội bộ và phiên bản server | Model có thực sự gọi tool không; JSON có thiếu, sai kiểu hoặc nhiều lần gọi không |
| **OpenAI-compatible endpoint khác** | Dùng giao thức tương thích không đồng nghĩa hỗ trợ toàn bộ hành vi OpenAI | Kiểm thử API thực tế, không suy “compatible” là có strict/tool calling đầy đủ |

Tài liệu so sánh chat model của Spring AI 2.1.0 giúp chọn integration có đường gọi công cụ; vẫn phải thử đúng **tên model, phiên bản, endpoint và tùy chọn** mà sản phẩm triển khai.

Một chiến lược phổ biến là thiết kế **hợp đồng tối giản chung**: tên ASCII đơn giản; schema object gốc, ít cấp lồng nhau, kiểu primitive rõ ràng, enum ít giá trị, đầu vào ngắn. Chỉ dùng `$ref`, `oneOf`/`anyOf`, đối tượng động hoặc constraint phức tạp khi đã kiểm tra provider mục tiêu.

## 7. Xử lý tình huống lỗi trong thực tế

| Triệu chứng | Khả năng nguyên nhân | Cách điều tra |
| --- | --- | --- |
| API trả HTTP 400 trước khi gọi tool | Tên không hợp lệ, schema không được hỗ trợ, strict schema sai | Log mã lỗi provider; chụp **định nghĩa đã lọc dữ liệu nhạy cảm** gửi lên; giảm schema từng bước |
| Mô hình không gọi tool | Mô tả không rõ, model không hỗ trợ, không có công cụ trong request, tool choice không phù hợp | Kiểm tra tools được truyền vào `ChatClient`, khả năng model, prompt và config lựa chọn tool |
| Yêu cầu gọi tên không tồn tại | Tên đã thay đổi, quá trình ghép danh sách tool lỗi, model sinh tên bất thường | Kiểm tra tên trên callback và tên model trả; từ chối tên ngoài danh sách |
| JSON thiếu trường hoặc sai loại | Model chưa tuân schema, `required` không đúng, schema quá phức tạp | Xem `inputSchema`, cách deserialization; trả lỗi có thể xử lý, không tự động “đoán” kiểu |
| `null` gây lỗi ở Java | Khác biệt giữa thiếu key/nullable, primitive Java không nhận `null` | Dùng wrapper type khi cần nullable; quy định giá trị mặc định ở code |
| Gọi được tool nhưng kết quả nghiệp vụ sai | Chưa xác thực tenant/quyền, chưa kiểm tra miền giá trị | Kiểm tra phân quyền trong service, giới hạn số lượng, ID hợp lệ, quyền trên từng tài nguyên |
| Chạy được ở provider A nhưng không chạy ở B | Khác tên, schema subset, model/endpoint khác | Dùng cùng bộ ca kiểm thử trên từng provider và ghi nhận capability cụ thể |

Không nên thực hiện lại một tool có tác dụng phụ chỉ vì mô hình trả JSON sai ở bước sau. Với lệnh thay đổi trạng thái, thiết kế idempotency key, xác nhận quyền và giới hạn retry ở ứng dụng.

## 8. Kiểm thử tính tương thích theo hợp đồng

Nên kiểm tra theo ba vòng, từ rẻ nhất tới thực tế nhất.

**Vòng 1 — Kiểm tra định nghĩa tại Java:** lấy `ToolCallback.getToolDefinition()` và xác minh tên duy nhất, mô tả không rỗng, `inputSchema` parse được; đối chiếu các trường, `required` và dạng dữ liệu với hợp đồng định trước. Đây là cách phát hiện regression khi sửa annotation, DTO hoặc nâng phiên bản Spring AI.

**Vòng 2 — Kiểm tra chuyển kiểu và logic:** chạy callback với input JSON đại diện cho hợp lệ, thiếu trường, `null`, sai kiểu, số quá phạm vi, enum lạ, key thừa, chuỗi rất dài. Xác minh không có đường đi vượt kiểm tra quyền `ToolContext`. Dùng service giả lập để không ghi hệ thống thật.

**Vòng 3 — Kiểm tra với model/provider cụ thể:** gửi các yêu cầu mô phỏng nghiệp vụ tới từng cấu hình mục tiêu; xác nhận provider chấp nhận schema, mô hình chọn đúng tên, tham số hợp lệ, tool được gọi đúng số lần, câu trả lời cuối dựa trên kết quả tool và có cơ chế xử lý khi model không gọi công cụ.

Ví dụ ma trận nhỏ:

| Ca kiểm thử | Mong đợi |
| --- | --- |
| “Còn 5 PEN-031 không?” | Chọn `lookup_stock_v1`, `sku` là chuỗi, `units` là số nguyên 5 |
| “Còn PEN-031 không?” | Hỏi lại số lượng hoặc áp dụng quy tắc mặc định **được ứng dụng định nghĩa rõ** |
| “Kiểm tra -7 sản phẩm” | Chặn bởi kiểm tra `units`; không truy vấn kho |
| Yêu cầu SKU kho của tenant khác | Service từ chối dù model tự tạo đúng hình dạng JSON |
| Provider strict từ chối schema tùy chọn | Dùng schema/DTO phù hợp hoặc chọn chế độ API được hỗ trợ; xác nhận lại bằng test |
| Model trả tên không đăng ký | Không thực thi bất kỳ dịch vụ nào |

Nên ghi nhận các kết quả riêng: **schema accepted rate**, **tool selection accuracy**, **argument validity**, **authorization denial** và **business success rate**. Không nên chỉ đo “mô hình có trả câu trả lời hay không”.

## 9. Checklist khi đưa công cụ sang mô hình khác

1. Kiểm tra provider và **model cụ thể** có hỗ trợ tool calling ở endpoint đang dùng.
2. Xuất toàn bộ `ToolDefinition` sau khi cấu hình; so khớp tên, mô tả, schema và tên trùng.
3. Dùng tên ngắn, ổn định, tránh ký tự đặc biệt; có kế hoạch nâng phiên bản contract.
4. Giữ DTO đầu vào rõ ràng; phân biệt thiếu giá trị, `null` và chuỗi rỗng.
5. Tránh kiểu động và schema phức tạp nếu không cần; kiểm tra strict mode trước khi bật.
6. Kiểm tra chuyển kiểu, miền dữ liệu, phân quyền, tenant, idempotency tại Java/service.
7. Chạy tập tình huống giống nhau trên các model/provider; ghi rõ kết quả theo phiên bản.
8. Khi đổi model hoặc nâng Spring AI, chạy lại kiểm thử tương thích; đừng suy đoán từ model cũ.

### Những điểm riêng của Spring AI 2.1 cần nhớ

- `@Tool`/`ToolCallback` xác định hợp đồng ở ứng dụng; nhà cung cấp/mô hình mới quyết định mức tiếp nhận schema và chất lượng đối số.
- Trong kiến trúc **Spring AI 2.x**, `ToolCallingAdvisor` ở `ChatClient` thực thi vòng gọi công cụ. Cơ chế vòng lặp nội bộ theo `ChatModel` của **Spring AI 1.x** đã được thay thế; không sao chép nguyên ví dụ 1.x rồi giả định vòng lặp vẫn chạy.
- Cách đăng ký bean `Function` và phân giải tên tool ở Spring AI 1.x khác 2.x; 2.x ưu tiên `ToolCallback`/`@Tool` tường minh. Hãy đối chiếu tài liệu nâng cấp trước khi chuyển mã cũ.

## 10. Tài liệu tham khảo và phạm vi xác minh

- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): `@Tool`, `ToolCallback`, `ToolDefinition`, JSON Schema, `ToolContext`, tên trùng và vòng lặp.
- [Spring AI — Chat Model Comparison](https://docs.spring.io/spring-ai/reference/integrations/models/comparison.html): khả năng tool calling theo integration.
- [Spring AI — Ollama Chat](https://docs.spring.io/spring-ai/reference/api/chat/ollama-chat.html), [Google GenAI Chat](https://docs.spring.io/spring-ai/reference/api/chat/google-genai-chat.html): đặc điểm tích hợp và cấu hình lựa chọn tool.
- [OpenAI — Function Calling](https://developers.openai.com/api/docs/guides/function-calling), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs): strict mode và giới hạn JSON Schema.
- [Anthropic — Define Tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools), [Strict Tool Use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use): hợp đồng `input_schema` và kiểm tra strict.
- [Google GenAI SDK — FunctionDeclaration](https://googleapis.github.io/js-genai/release_docs/interfaces/types.FunctionDeclaration.html): quy định tên và cấu trúc tham số ở SDK.

**Ghi chú phiên bản:** nội dung lấy mốc Spring AI **2.1.0** (bản stable tại thời điểm biên soạn, 11/2026). Tính năng của provider có thể đổi độc lập với Spring AI; những nhận xét về tương thích là chỉ dẫn thiết kế và cần được xác nhận bằng bộ kiểm thử cho môi trường triển khai.

