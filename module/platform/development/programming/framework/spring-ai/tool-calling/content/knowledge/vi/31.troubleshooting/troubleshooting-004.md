# Lỗi schema, required field, null và chuyển đổi đối số

Trong **SPRING_AI_TOOL_CALLING**, mô hình ngôn ngữ không trực tiếp gọi một phương thức Java. Mô hình nhìn thấy tên tool, mô tả và **JSON Schema**; nó tạo một tool call gồm tên và JSON arguments. Ứng dụng Spring AI tìm `ToolCallback` tương ứng, chuyển những arguments đó thành đối số Java, rồi mới thực thi `@Tool` hoặc hàm nghiệp vụ.

Một lỗi nhỏ như đặt sai tên field, đánh dấu một trường là bắt buộc dù người dùng không biết giá trị, gửi `null` vào tham số `int`, hoặc gửi JSON string thay vì number có thể khiến tool thất bại trước khi code nghiệp vụ chạy. Việc mô hình trả lời “không tra cứu được” không cho biết lỗi nằm ở schema, JSON, mapper, reflection, quyền truy cập hay API phía sau.

Bài học này tập trung vào **chẩn đoán đúng tầng**, tái hiện được lỗi bằng test không cần LLM thật, rồi sửa hợp đồng tool mà không vô tình làm suy yếu validation hoặc authorization. Ví dụ sử dụng các API Spring AI 2.x: `@Tool`, `@ToolParam`, `ToolCallback`, `ToolContext`, `MethodToolCallback`, `FunctionToolCallback` và `ToolExecutionExceptionProcessor`. Những khác biệt theo phiên bản phải được đối chiếu với dependency thực tế của dự án.

## 1. Đặt lỗi vào đúng đường đi thực thi

~~~mermaid
flowchart TD
    U[Người dùng gửi yêu cầu] --> CLIENT[ChatClient + ToolCallingAdvisor]
    CLIENT --> DEF[ToolDefinition: name, description, inputSchema]
    DEF --> MODEL[ChatModel chọn tool và tạo arguments JSON]
    MODEL --> RESOLVE[ToolCallingManager tìm ToolCallback]
    RESOLVE --> PARSE[Phân tích cú pháp JSON]
    PARSE --> BIND[Đối chiếu tên field và kiểu tham số Java]
    BIND --> VALIDATE[Validation và authorization của ứng dụng]
    VALIDATE --> EXEC[Method/Function thực thi]
    EXEC --> CONVERT[Chuyển tool result thành String]
    CONVERT --> CLIENT

    PARSE -- JSON sai --> ERR1[Lỗi JSON]
    BIND -- Thiếu/sai kiểu --> ERR2[Lỗi argument binding]
    VALIDATE -- Quy tắc sai --> ERR3[Lỗi nghiệp vụ/quyền]
    EXEC -- Downstream lỗi --> ERR4[Lỗi dịch vụ ngoài]
~~~

Khi gặp một stack trace hay kết quả lỗi, trước tiên hỏi:

1. **Tool name có đúng không?** Nếu không, đây là lỗi phân giải tool, chưa phải lỗi schema.
2. **JSON có phân tích được không?** Nếu không, chưa đến bước chuyển kiểu Java.
3. **Tên arguments và kiểu dữ liệu có khớp schema/method không?** Nếu không, đây là lỗi binding/conversion.
4. **Đối số đã chuyển thành Java đúng nhưng không hợp lệ nghiệp vụ?** Đây là validation/domain error.
5. **Đã qua validation và authorization nhưng REST/SDK lỗi?** Đây là integration error.
6. **Method chạy xong nhưng model không nhận được kết quả?** Xem result converter và tool-message protocol.

Việc phân loại này tránh sửa sai tầng, ví dụ chỉnh prompt để “model không gửi null” trong khi server cần bắt buộc xác thực null trước khi gọi API.

## 2. Ba hợp đồng phải đồng nhất

| Lớp hợp đồng | Nơi khai báo | Vai trò |
|---|---|---|
| **Tool definition** | `ToolDefinition.name()`, `description()`, `inputSchema()` | Cho model biết tên tool, tình huống sử dụng, trường cần gửi |
| **Java signature / DTO** | Method `@Tool` hoặc `FunctionToolCallback.inputType(...)` | Xác định kiểu thực sự được callback nhận |
| **Business validation** | Application service, Bean Validation/validator, authorization | Xác định giá trị hợp lệ và người dùng được phép làm gì |

**JSON Schema không phải là bộ kiểm tra nghiệp vụ đáng tin cậy.** Nó giúp model tạo arguments đúng hơn; một model/provider vẫn có thể trả JSON sai hoặc thiếu. Spring AI và các provider cũng không phải lúc nào áp dụng schema cứng giống nhau.

Ví dụ một tool:

~~~java
public final class OrderTools {

    private final OrderService service;

    public OrderTools(OrderService service) {
        this.service = service;
    }

    @Tool(
        name = "get_order_status",
        description = """
            Tra cứu trạng thái đơn hàng được phép xem.
            Dùng khi người dùng hỏi đơn hàng đang ở bước nào.
            Không dùng để sửa hoặc hủy đơn.
            """
    )
    public OrderStatusResult getOrderStatus(
            @ToolParam(description = "Mã đơn, ví dụ ORD-8F31A2")
            String orderNumber,
            @ToolParam(
                description = "Ngôn ngữ trả kết quả, vi hoặc en",
                required = false
            )
            String language,
            ToolContext context) {

        Actor actor = requireServerActor(context);
        return service.getAuthorizedStatus(
            actor,
            requireOrderNumber(orderNumber),
            normalizeLanguage(language)
        );
    }
}
~~~

`OrderService`, `Actor`, `requireServerActor(...)`, `requireOrderNumber(...)` và `normalizeLanguage(...)` là code của ứng dụng. Mã đơn được model cung cấp, nhưng actor/tenant phải do server đưa qua `ToolContext`.

## 3. Xem inputSchema thực tế, không đoán từ annotation

Khi model tạo sai arguments, bước chẩn đoán đầu tiên là nhìn vào **schema mà Spring AI thực sự gửi cho model**, không chỉ mở mã nguồn Java và suy đoán.

~~~java
OrderTools tools = new OrderTools(orderService);

ToolCallback callback = Arrays.stream(
        ToolCallbacks.from(tools)
    )
    .filter(it -> it.getToolDefinition().name()
        .equals("get_order_status"))
    .findFirst()
    .orElseThrow();

ToolDefinition definition =
    callback.getToolDefinition();

System.out.println(definition.name());
System.out.println(definition.description());
System.out.println(definition.inputSchema());
~~~

Ví dụ đầu ra rút gọn, minh họa ý tưởng:

~~~json
{
  "type": "object",
  "properties": {
    "orderNumber": {
      "type": "string",
      "description": "Mã đơn, ví dụ ORD-8F31A2"
    },
    "language": {
      "type": "string",
      "description": "Ngôn ngữ trả kết quả, vi hoặc en"
    }
  },
  "required": ["orderNumber"]
}
~~~

Bộ schema thực tế có thể thêm metadata hoặc cấu trúc khác tùy cách Spring AI sinh schema và các annotation. Không lấy JSON giả định trên để coi là output bất biến; hãy snapshot/assert những phần quan trọng từ `getToolDefinition().inputSchema()`.

Cần đối chiếu ba thứ:

1. **Schema được phát hành**: model được hướng dẫn gửi gì?
2. **JSON thật model trả**: model đã gửi gì?
3. **Java signature và mapper**: callback đang cố đọc những tên và kiểu nào?

Không cần gửi raw prompt hoặc thông tin nhạy cảm vào production log để chẩn đoán; dùng fixture JSON đã redaction và tên tool/schema version.

## 4. Phân biệt lỗi cú pháp JSON với lỗi schema

Một JSON có thể sai về **cú pháp**:

~~~text
{"orderNumber":"ORD-8F31A2",}
~~~

Dấu phẩy cuối là không hợp lệ trong JSON chuẩn. Hoặc:

~~~text
{orderNumber:"ORD-8F31A2"}
~~~

Key không đặt trong dấu ngoặc kép, cũng không phải JSON chuẩn.

Ngược lại, JSON sau hợp lệ về cú pháp nhưng có thể **không hợp schema**:

~~~json
{
  "orderNumber": 12345,
  "language": ["vi", "en"]
}
~~~

Nếu schema yêu cầu `orderNumber` và `language` là string, JSON trên không đúng kiểu. Model có thể tạo JSON đúng cú pháp mà method callback vẫn không thể chuyển được thành đối số.

| Lớp lỗi | Ví dụ | Hành động |
|---|---|---|
| Parsing | JSON thiếu dấu ngoặc hoặc dấu phẩy | Kiểm tra payload/model/provider và parser |
| Shape | Top-level array thay cho object | Kiểm tra JSON Schema `type: object` |
| Property name | `order_number` thay vì `orderNumber` | Sửa hợp đồng/cách ánh xạ tên field |
| Requiredness | Thiếu `orderNumber` | Bổ sung field hoặc hỏi người dùng |
| Type | Số/array thay vì string | Sửa DTO/schema và validation |
| Range/enum | `priority: "critical"` không có trong enum | Hạn chế miền giá trị rõ ràng |
| Domain | Mã đơn đúng dạng nhưng không tồn tại | Trả lỗi nghiệp vụ an toàn |

Chẩn đoán phải ghi rõ **lỗi thuộc tầng nào**. Không gộp mọi lỗi thành “model hallucination”.

## 5. Required trong JSON Schema có nghĩa gì?

Trong JSON Schema, từ khóa `required` ở **một object** liệt kê **tên các property bắt buộc phải xuất hiện**.

~~~json
{
  "type": "object",
  "properties": {
    "orderNumber": { "type": "string" },
    "language": { "type": "string" }
  },
  "required": ["orderNumber"]
}
~~~

Các JSON:

~~~json
{"orderNumber":"ORD-8F31A2"}
~~~

Hợp schema về sự hiện diện trường bắt buộc.

~~~json
{"language":"vi"}
~~~

Thiếu `orderNumber` nên không hợp schema.

Tuy nhiên, `required` **chỉ nói về sự hiện diện của key**, không tự động bảo đảm value khác `null`. Ví dụ JSON dưới đây có key `orderNumber` nhưng value `null`:

~~~json
{"orderNumber": null}
~~~

Nếu schema ghi `"type":"string"` thì value `null` không hợp kiểu. Nếu schema cho phép `null` thì tình huống khác. Đây là lý do phải **tách “thiếu key” và “key có giá trị null”** trong bộ test.

## 6. Required/optional trong Spring AI

Với method `@Tool` của Spring AI 2.x, tham số được xem là **required theo mặc định**. Có thể đánh dấu optional bằng:

- `@ToolParam(required = false)`.
- `@JsonProperty(required = false)` của Jackson.
- `@Schema` của Swagger với chế độ not-required phù hợp phiên bản.
- `@Nullable` của Spring Framework hoặc JSpecify.

Mức ưu tiên áp dụng theo quy tắc của Spring AI; tài liệu đặt `@ToolParam` ưu tiên cao. Khi dùng kết hợp nhiều annotation có thể mâu thuẫn, đừng đoán kết quả: **kiểm tra generated schema**.

Ví dụ:

~~~java
@Tool(description = "Tìm đơn theo trạng thái tùy chọn")
public List<OrderSummary> searchOrders(
        @ToolParam(description = "Từ khóa tìm kiếm")
        String query,
        @ToolParam(
            description = "Trạng thái lọc, có thể bỏ qua",
            required = false
        )
        OrderStatus status) {
    return orderService.search(query, status);
}
~~~

`query` required; `status` optional. Nếu model không gửi `status`, method có thể nhận `null` theo cơ chế binding và phiên bản. Dù optional ở schema, code vẫn phải định nghĩa rõ `null` nghĩa là gì.

**Không đánh dấu một field là required khi model không có cách xác định nó.** Ví dụ `tenantId`, token, user role hoặc approval state phải lấy từ server, không yêu cầu model “đoán” chúng để lấp schema.

## 7. Missing field, explicit null, empty string và blank string

Bốn tình huống khác nhau:

| JSON | Diễn giải | Policy gợi ý |
|---|---|---|
| `{}` | Không có property | Nếu required thì từ chối |
| `{"language":null}` | Property có mặt, value null | Chỉ chấp nhận khi nghiệp vụ cho phép |
| `{"language":""}` | String rỗng | Có thể thay default hoặc từ chối |
| `{"language":"   "}` | Chỉ chứa whitespace | Trim/normalize rồi kiểm tra |
| `{"language":"vi"}` | Giá trị có ý nghĩa | Xác thực miền giá trị rồi xử lý |

Không viết `if (value == null)` và cho rằng đã xử lý mọi trường hợp thiếu input: chuỗi rỗng, giá trị khoảng trắng, array rỗng và object rỗng cần quy tắc riêng.

Đặc biệt, **optional không đồng nghĩa nullable** trong mọi thiết kế. Một trường có thể “được phép bỏ qua, nhưng nếu xuất hiện thì phải là string hợp lệ”. JSON Schema biểu diễn hai yêu cầu đó độc lập.

Ví dụ schema:

~~~json
{
  "type": "object",
  "properties": {
    "language": {
      "type": "string",
      "enum": ["vi", "en"]
    }
  },
  "required": []
}
~~~

Schema trên cho phép **vắng** `language`, nhưng `"language":null` không hợp kiểu.

Nếu thực sự muốn cho phép null:

~~~json
{
  "type": "object",
  "properties": {
    "language": {
      "type": ["string", "null"],
      "enum": ["vi", "en", null]
    }
  }
}
~~~

Đừng tự thêm `"null"` vào schema chỉ để làm test qua; hãy quyết định ý nghĩa nghiệp vụ và bảo đảm Java method xử lý được value tương ứng.

## 8. Tránh primitive optional: null không gán được vào int/boolean

Đây là một trong những lỗi dễ gặp khi dùng method tool:

~~~java
@Tool(description = "Liệt kê đơn hàng")
public List<OrderSummary> listOrders(
        @ToolParam(required = false)
        int pageSize) {
    return service.list(pageSize);
}
~~~

Model có thể bỏ qua `pageSize` vì schema đánh dấu optional. Khi binding tạo ra `null` rồi gọi reflection với tham số primitive `int`, Java không thể unbox `null` thành `int`. Tùy phiên bản, lỗi có thể là `IllegalArgumentException` khi `Method.invoke(...)`, thậm chí không đi qua processor xử lý lỗi tool như kỳ vọng.

**Giải pháp:** dùng wrapper `Integer`/`Boolean`/`Long` cho optional, rồi kiểm tra/default rõ ràng:

~~~java
@Tool(description = "Liệt kê đơn hàng theo trang")
public List<OrderSummary> listOrders(
        @ToolParam(
            description = "Số bản ghi, từ 1 đến 100; bỏ qua để lấy 20",
            required = false
        )
        Integer pageSize,
        ToolContext context) {

    Actor actor = requireServerActor(context);

    int effectivePageSize =
        pageSize == null ? 20 : pageSize;

    if (effectivePageSize < 1 ||
        effectivePageSize > 100) {
        throw new InvalidToolInputException(
            "pageSize phải trong khoảng 1..100"
        );
    }

    return service.listAuthorized(
        actor, effectivePageSize
    );
}
~~~

Nếu field thật sự bắt buộc và bạn dùng primitive, vẫn phải test model gửi thiếu hoặc null; đừng cho rằng schema sẽ chặn tuyệt đối. Với thao tác nghiệp vụ quan trọng, một DTO có validation tường minh thường dễ bảo trì hơn việc dựa vào unboxing của reflection.

Một issue trong Spring AI 2.0.0 đã ghi nhận tình huống thiếu primitive khiến `IllegalArgumentException` thoát ra ngoài thay vì luôn được bọc thành `ToolExecutionException`. **Không suy rộng rằng mọi phiên bản đều có cùng bug hoặc đã được sửa**: test hành vi ở đúng version đang dùng.

## 9. Type mismatch: string, number, boolean, enum, date

Model có thể gửi value khác kiểu mà method chờ đợi.

| Java target | JSON đúng về kiểu | JSON sai/nguy cơ |
|---|---|---|
| `String` | `"ORD-8F31A2"` | `123`, array, object |
| `Integer` | `10` | `"ten"`, `10.8`, object |
| `BigDecimal` | `12.50` (number) | `"twelve"`, boolean |
| `Boolean` | `true` / `false` | `"yes"` hoặc `1` |
| `Status enum` | `"SHIPPED"` | `"shipped now"` nếu enum không tương ứng |
| `LocalDate` | `"2026-11-27"` (string hợp định dạng) | `"tomorrow"` nếu không có parser đặc biệt |
| `List<String>` | `["A","B"]` | `{"one":"A"}` |
| DTO lồng nhau | object theo field | string JSON đã escape hoặc array |

Một số mapper có thể tự chuyển `"42"` thành số `42`, tùy Jackson configuration. **Không dựa vào coercion ngầm** cho trường có ý nghĩa bảo mật hoặc tài chính. Xác định rõ contract và kiểm tra điều kiện nghiệp vụ sau khi binding.

Ví dụ với thời gian:

~~~java
@Tool(description = "Đặt lịch theo ngày ISO-8601")
public AppointmentResult schedule(
        @ToolParam(description = "Ngày theo yyyy-MM-dd")
        String date,
        ToolContext context) {

    LocalDate parsed;
    try {
        parsed = LocalDate.parse(
            date, DateTimeFormatter.ISO_LOCAL_DATE
        );
    }
    catch (DateTimeParseException ex) {
        throw new InvalidToolInputException(
            "Ngày phải theo yyyy-MM-dd"
        );
    }

    return service.schedule(
        requireServerActor(context),
        parsed
    );
}
~~~

Dùng `String` và parse tường minh là một lựa chọn khi cần kiểm soát thông báo lỗi và timezone. Có thể nhận `LocalDate` trực tiếp nếu mapper hỗ trợ, nhưng vẫn cần test dạng dữ liệu provider trả.

## 10. Enum: schema có giá trị nhưng model gửi biến thể khác

Ví dụ:

~~~java
public enum OrderStatus {
    CREATED, PAID, SHIPPED, DELIVERED
}

@Tool(description = "Lọc đơn theo trạng thái")
public List<OrderSummary> filter(
        @ToolParam(description = "Trạng thái đơn hàng")
        OrderStatus status) {
    return service.filter(status);
}
~~~

Nếu model gửi:

~~~json
{"status":"shipped"}
~~~

trong khi mapper chỉ chấp nhận `SHIPPED`, binding có thể thất bại. Không nên bật enum coercion tùy ý rồi xem mọi giá trị gần giống là hợp lệ.

Một số hướng sửa:

1. Mô tả allowed enum values rõ ràng.
2. Kiểm tra schema generated có liệt kê enum không.
3. Nếu domain dùng tên người dùng tự nhiên, tạo **adapter** chuyển một tập alias được cho phép sang enum.
4. Nếu không khớp, trả lỗi input có cấu trúc thay vì đoán một trạng thái khác.
5. Với trường ảnh hưởng giao dịch/tiền, từ chối giá trị chưa rõ và yêu cầu xác nhận.

Ví dụ normalize alias ở application service:

~~~java
static OrderStatus parseStatus(String value) {
    if (value == null) {
        throw new InvalidToolInputException(
            "Thiếu trạng thái"
        );
    }

    return switch (value.trim().toUpperCase(Locale.ROOT)) {
        case "CREATED" -> OrderStatus.CREATED;
        case "PAID" -> OrderStatus.PAID;
        case "SHIPPED" -> OrderStatus.SHIPPED;
        case "DELIVERED" -> OrderStatus.DELIVERED;
        default -> throw new InvalidToolInputException(
            "Trạng thái không được hỗ trợ"
        );
    };
}
~~~

Đây là adapter hợp lệ khi nghiệp vụ chấp nhận phân biệt chữ hoa/thường; đừng normalize tùy tiện nếu enum có ý nghĩa pháp lý hoặc nhạy cảm.

## 11. Nested object và collections

Khi một tool dùng object lồng nhau, hãy đảm bảo schema và kiểu Java mô tả **cùng cấu trúc**.

Ví dụ request:

~~~java
public record Address(
    String city,
    String postalCode
) {}

public record DeliveryQuoteRequest(
    String orderNumber,
    Address destination,
    List<String> services
) {}
~~~

Tool dạng function:

~~~java
@Bean
ToolCallback deliveryQuoteTool(
        DeliveryQuoteService service) {

    return FunctionToolCallback
        .builder(
            "estimate_delivery",
            (DeliveryQuoteRequest request) ->
                service.estimate(request)
        )
        .description(
            "Ước lượng phí giao cho một đơn hàng và địa chỉ."
        )
        .inputType(DeliveryQuoteRequest.class)
        .build();
}
~~~

Input hợp kiểu:

~~~json
{
  "orderNumber": "ORD-8F31A2",
  "destination": {
    "city": "Da Nang",
    "postalCode": "550000"
  },
  "services": ["STANDARD", "EXPRESS"]
}
~~~

Các lỗi phổ biến:

- `destination` được gửi dưới dạng string `"Da Nang"` thay vì object.
- `services` là một string `"EXPRESS"` thay vì array.
- `postalCode` bị model biến thành number khiến mất số 0 đầu.
- Một nested field bắt buộc bị đánh dấu optional hoặc ngược lại.
- DTO record chỉ có constructor hoặc annotation chưa được mapper nhận diện theo cấu hình.
- Model gửi property lạ và mapper đang im lặng bỏ qua.

Đừng cố chữa bằng `Map<String,Object>` không ràng buộc nếu workflow cần hợp đồng ổn định. DTO cụ thể giúp test nested schema và validation tốt hơn.

## 12. Field thừa và additionalProperties

Giả sử schema chỉ có `orderNumber` và `language`. Model lại trả:

~~~json
{
  "orderNumber": "ORD-8F31A2",
  "language": "vi",
  "tenantId": "tenant-b",
  "debug": true
}
~~~

Nếu mapper bỏ qua field lạ, method có thể vẫn chạy, khiến người phát triển tưởng là schema đã từ chối các field đó. Nếu mapper từ chối property lạ, có thể xuất hiện mapping exception.

Đối với công cụ nghiệp vụ nhạy cảm:

- Xem `additionalProperties` trong generated schema.
- Kiểm tra chính sách chấp nhận/reject extra fields tại **boundary** của ứng dụng.
- Không biến `tenantId`, role hoặc token do model gửi thành thông tin xác thực.
- Nếu cần augmentation, dùng công cụ augmentation có contract tách biệt; không tự gộp bất kỳ field nào model gửi vào service input.
- Test cả unknown fields và key gần đúng như `orderID`, `order_id`.

**Không mặc định annotation đặt tên field sẽ tự cập nhật mọi đường binding.** Một JSON Schema có tên property khác với tên Java method parameter có thể khiến parser và reflection không đồng bộ; hãy kiểm tra bằng callback test.

## 13. Tên tham số Java và compiler -parameters

Với method tool, Spring AI phải ánh xạ key của JSON object sang tham số Java. Nếu tên tham số không còn trong metadata bytecode do cấu hình compiler hoặc reflection, schema có thể xuất hiện tên chung hoặc không như mong đợi. Ở Java, tên tham số thật khi dùng reflection thường cần biên dịch với cờ `-parameters`.

Ví dụ method:

~~~java
@Tool(description = "Tính phí giao hàng")
public Quote quote(String postalCode, Integer quantity) {
    return service.quote(postalCode, quantity);
}
~~~

Model cần tạo:

~~~json
{
  "postalCode": "550000",
  "quantity": 2
}
~~~

Nếu callback lại đi tìm `arg0`/`arg1` trong JSON, binding không khớp.

### Gradle

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

### Maven

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <configuration>
    <parameters>true</parameters>
  </configuration>
</plugin>
~~~

Khi chẩn đoán:

1. Kiểm tra Java compiler đã tạo metadata hay chưa.
2. In `method.getParameters()[i].getName()` trong test.
3. Kiểm tra `definition.inputSchema()`.
4. Thực thi `ToolCallback.call(...)` trực tiếp với JSON dùng đúng key.
5. Với method ở dependency bên ngoài không kiểm soát compiler, cân nhắc wrapper DTO/function tool có hợp đồng tường minh.

Không cần thay đổi toàn bộ hệ thống build chỉ vì một lỗi tool; trước tiên xác nhận metadata và version.

## 14. FunctionToolCallback và MethodToolCallback có lỗi binding khác nhau

Cả hai đều hiện diện dưới `ToolCallback` nhưng cách nhận arguments khác nhau.

| Loại | Kiểu đầu vào | Điểm cần kiểm tra |
|---|---|---|
| `MethodToolCallback` | Các tham số của một Java method | Tên tham số, thứ tự, wrapper/primitive, reflection |
| `FunctionToolCallback` | Một input type/DTO của function | JSON ↔ DTO, record/class constructor, nested fields |
| Custom `ToolCallback` | JSON String và context trực tiếp | Parser/custom validation do ứng dụng tự chịu trách nhiệm |

`FunctionToolCallback`:

~~~java
public record InventoryQuery(
    String sku,
    Integer maxResults
) {}

@Bean
ToolCallback inventoryTool(InventoryService inventory) {
    return FunctionToolCallback.builder(
            "lookup_inventory",
            (InventoryQuery query) ->
                inventory.lookup(query)
        )
        .description("Tra cứu tồn kho theo SKU")
        .inputType(InventoryQuery.class)
        .build();
}
~~~

`MethodToolCallback` tạo từ method:

~~~java
Method method = ReflectionUtils.findMethod(
    OrderTools.class,
    "getOrderStatus",
    String.class,
    String.class,
    ToolContext.class
);

MethodToolCallback callback = MethodToolCallback.builder()
    .toolDefinition(
        ToolDefinitions.builder(method)
            .description("Tra cứu trạng thái đơn hàng")
            .build()
    )
    .toolMethod(method)
    .toolObject(orderTools)
    .build();
~~~

Đối với `MethodToolCallback`, `toolObject` phải được cung cấp cho instance method, còn static method không cần instance. `ToolContext` là tham số đặc biệt, không có mặt trong JSON Schema do mô hình cung cấp.

Không dùng `Optional`, `CompletableFuture`, `Future`, `Mono`, `Flux` hoặc functional types làm tham số/return type của method tool rồi mong framework tự serialize như DTO đồng bộ. Spring AI có giới hạn được tài liệu hóa với các kiểu này; dùng wrapper/nullable hoặc adapter phù hợp.

## 15. Lỗi deserialize DTO record và constructor

Một `record` Java thường thích hợp làm input của function tool, nhưng code vẫn có thể lỗi nếu:

- JSON key không khớp component name.
- DTO có nested record nhưng JSON thiếu object cha.
- Jackson không biết deserialize một kiểu tùy chỉnh.
- Trường ngày giờ không có module/format tương ứng.
- Mapper được tùy biến có cấu hình naming strategy khác contract tool.
- Input chứa số vượt phạm vi kiểu Java, ví dụ một `long` quá lớn.
- Field required ở generated schema khác những gì constructor/service mong đợi.

Ví dụ:

~~~java
public record TransferRequest(
    String sourceAccount,
    String destinationAccount,
    BigDecimal amount
) {}
~~~

Các trường phải được validation ở service trước bất kỳ giao dịch thật nào. Một JSON hợp cấu trúc như:

~~~json
{
  "sourceAccount": "A-001",
  "destinationAccount": "B-009",
  "amount": -100.00
}
~~~

có thể deserialize thành công nhưng **không hợp nghiệp vụ**. Không nhầm “mapping pass” với “được phép chuyển tiền”.

Với tool có side effect, validation tiền tệ, idempotency và authorization theo tài khoản phải nằm ở server. Chọn giá trị mặc định cho `amount` khi thiếu là một thiết kế nguy hiểm.

## 16. Bean Validation không tự thay thế tool argument validation

Annotation Jakarta Validation giúp mô tả quy tắc:

~~~java
public record SearchQuery(
    @NotBlank
    String query,
    @Min(1)
    @Max(100)
    Integer limit
) {}
~~~

Tuy nhiên, không nên giả định Spring AI sẽ tự kích hoạt giống Spring MVC `@RequestBody @Valid` trên mọi đường `ToolCallback.call(...)`. Nếu muốn chắc chắn, hãy gọi validator hoặc đưa quy tắc vào application service:

~~~java
public List<SearchResult> searchAuthorized(
        SearchQuery input,
        Actor actor) {

    Set<ConstraintViolation<SearchQuery>> violations =
        validator.validate(input);

    if (!violations.isEmpty()) {
        throw new InvalidToolInputException(
            "Tham số tìm kiếm không hợp lệ"
        );
    }

    authorization.requireCanSearch(actor);
    return repository.search(
        actor.tenantId(),
        input.query(),
        input.limit()
    );
}
~~~

Lưu ý: một `limit` optional để `null` sẽ không tự thỏa mãn quy tắc `@Min(1)` như thể đã có giá trị. Hãy quyết định default trước khi validate hoặc dùng validation nhóm phù hợp.

**Validation và authorization phải fail closed.** Khi `ToolContext` thiếu actor, không “cho phép vì model đã chọn đúng tool”.

## 17. ToolContext không phải một field trong JSON arguments

Để kiểm thử lỗi thiếu field, tránh nhầm `ToolContext` với object do model gửi.

~~~java
@Tool(description = "Xem trạng thái đơn")
public OrderStatusResult getStatus(
        String orderNumber,
        ToolContext context) {

    Actor actor = requireActor(context);
    return service.getStatus(actor, orderNumber);
}
~~~

Model nên gửi:

~~~json
{"orderNumber":"ORD-8F31A2"}
~~~

Không phải:

~~~json
{
  "orderNumber":"ORD-8F31A2",
  "context": {
    "actor":"admin",
    "tenantId":"tenant-b"
  }
}
~~~

Ở server:

~~~java
Actor actor = actorFactory.fromAuthentication(authentication);

String answer = chatClient.prompt()
    .user(question)
    .tools(orderTools)
    .toolContext(Map.of("actor", actor))
    .call()
    .content();
~~~

`ToolContext` không được gửi đến model như JSON Schema field. Một lỗi `Missing authenticated actor` không được “sửa” bằng cách đưa `tenantId` vào `@ToolParam`; phải sửa đường truyền context server-side.

## 18. Phân biệt lỗi trả về và lỗi được ném

Một callback có thể gặp lỗi trước khi method chạy, trong method, hoặc khi serialize kết quả. Cách lỗi được biểu diễn phụ thuộc Spring AI version, callback implementation và cấu hình processor.

Trong Spring AI 2.x:

- Khi tool thực thi ném exception, framework có cơ chế `ToolExecutionException` và `ToolExecutionExceptionProcessor`.
- Processor có thể chuyển lỗi thành tool result để mô hình phản hồi hoặc ném lỗi ra caller.
- Không phải mọi lỗi parse/binding/reflection đều mặc nhiên đi vào cùng processor; lỗi trước khi gọi method có thể khác lỗi trong thân method.
- `DefaultToolExecutionExceptionProcessor` có chính sách với `RuntimeException` và lỗi khác; cần đối chiếu version/cấu hình.

Vì vậy, khi viết code xử lý lỗi, **không chỉ catch `ToolExecutionException`** rồi tuyên bố mọi schema failure đều được xử lý. Hãy test cụ thể `callback.call(...)` trong version đang dùng với payload thiếu/sai kiểu.

### Hai chiến lược phản hồi lỗi

1. **Fail to caller:** lỗi quyền, lỗi hệ thống không thể phục hồi, schema misconfiguration; trả HTTP/application error an toàn.
2. **Structured recoverable tool error:** lỗi input có thể sửa, cho model hoặc người dùng cơ hội cung cấp trường còn thiếu, nhưng giới hạn số vòng thử.

Ví dụ error result an toàn:

~~~json
{
  "ok": false,
  "code": "INVALID_TOOL_ARGUMENT",
  "field": "orderNumber",
  "message": "Cần mã đơn hàng đúng định dạng ORD-..."
}
~~~

Không gửi stack trace, raw SQL, credential, thông tin khách hàng hoặc payload nội bộ vào tool result. Dù lỗi được trả cho model, model vẫn không được tự cấp quyền.

## 19. Chẩn đoán theo một bảng quyết định

| Triệu chứng | Khả năng cao | Bước kiểm tra đầu tiên |
|---|---|---|
| Model không gọi tool | Tool description mơ hồ, tool không được đăng ký | `getToolDefinition()` và `.tools(...)` |
| “No tool found” | Tên tool khác, resolver/allowlist | Tool name và danh sách callback của request |
| JSON parse error | Arguments không phải JSON hợp lệ | Lưu fixture đã redaction, kiểm tra cú pháp |
| Field Java luôn `null` | JSON key khác tên tham số | Generated schema và parameter metadata |
| “Missing required field” | Schema bắt buộc nhưng model không có dữ liệu | `required` và prompt/user input |
| `IllegalArgumentException` khi invoke | `null` vào primitive hoặc kiểu không khớp | Method signature và JSON payload |
| `InvalidFormatException` | Enum/date/number sai format | Kiểu đích và Jackson configuration |
| `MismatchedInputException` | Array/object/string không đúng shape | Nested DTO và schema |
| Giá trị mặc định bất ngờ | Mapping bỏ qua field hoặc primitive default | DTO constructor, mapper, service |
| Tool chạy nhưng trả sai tenant | Lỗi authorization, không phải schema | Actor từ `ToolContext`, repository filter |
| Tool trả lỗi thô cho model | Error processor/mapping không an toàn | Exception message, redaction |
| `ChatClient.stream()` lỗi giữa chừng | Partial tool-call arguments bị xử lý sớm hoặc publisher hủy | Đường streaming và complete tool calls |
| Tool result không serialize | Return type không hỗ trợ / converter lỗi | Result converter và DTO output |

Các tên Jackson exception có thể xuất hiện bên trong exception khác; hãy xem **cause chain** an toàn, không chỉ message ngoài cùng.

## 20. Quy trình tái hiện lỗi theo từng tầng

Một quy trình gỡ lỗi có thể lặp lại:

1. **Cố định môi trường:** Java version, Spring AI version, provider/model, mapper configuration, build compiler flags.
2. **Ghi tool identity:** name, description và schema version; xác minh tool được gắn vào request.
3. **Trích JSON lỗi đã loại bỏ dữ liệu nhạy cảm:** giữ shape/type/field names, thay giá trị bí mật bằng fixture.
4. **Kiểm tra JSON syntax:** parse bằng JSON parser độc lập.
5. **Kiểm tra JSON Schema:** required, type, enum, nested object, additional properties.
6. **Gọi ToolCallback trực tiếp:** loại bỏ biến động của model để cô lập binding.
7. **Đặt spy tại service:** xác định method có được gọi hay chưa và nhận kiểu/giá trị nào.
8. **Kiểm tra authorization và validation:** lỗi có nằm sau binding không?
9. **Kiểm tra output converter:** kết quả có được serialize đúng và an toàn không?
10. **Tạo regression test:** giữ payload đã gây lỗi dưới dạng fixture sau khi sửa.

Các bước này thường nhanh hơn việc đổi prompt ngẫu nhiên và gọi model lại nhiều lần.

## 21. Kiểm thử trực tiếp ToolCallback không cần LLM

Đây là cách quan trọng nhất để phân biệt lỗi framework binding và lỗi model tạo JSON.

~~~java
@ExtendWith(MockitoExtension.class)
class OrderToolsCallbackTest {

    @Mock
    OrderService orderService;

    private ToolCallback callback;
    private Actor actor;

    @BeforeEach
    void setup() {
        OrderTools tools = new OrderTools(orderService);

        callback = Arrays.stream(
                ToolCallbacks.from(tools)
            )
            .filter(it -> it.getToolDefinition()
                .name().equals("get_order_status"))
            .findFirst()
            .orElseThrow();

        actor = new Actor("user-1", "tenant-a");
    }

    @Test
    void validArgumentsCallService() {
        when(orderService.getAuthorizedStatus(
                eq(actor), eq("ORD-8F31A2"), eq("vi")))
            .thenReturn(new OrderStatusResult(
                "ORD-8F31A2", "SHIPPED"
            ));

        callback.call(
            """
            {"orderNumber":"ORD-8F31A2","language":"vi"}
            """,
            new ToolContext(Map.of("actor", actor))
        );

        verify(orderService).getAuthorizedStatus(
            actor, "ORD-8F31A2", "vi"
        );
    }
}
~~~

Các type `Actor`, `OrderStatusResult`, `OrderService` và helper method của `OrderTools` cần định nghĩa nhất quán trong test project; đoạn minh họa không thay một test compile trong repository thực. Mục tiêu là khẳng định `callback.call(String,ToolContext)` đi qua chính đường parse/bind mà Spring AI dùng khi model gọi tool.

Đối với negative tests, **không chốt cứng mọi loại exception** nếu dự án chưa chốt version: có phiên bản ném lỗi gốc, có phiên bản bọc vào `ToolExecutionException`. Nên assert bất biến ở service không bị gọi khi input sai, và xác định exception type chính xác sau khi kiểm thử trên dependency thực tế.

## 22. Bộ test missing/null/sai kiểu theo ma trận

Xây dựng những case có input riêng:

| Case | JSON arguments | Mong đợi tại business boundary |
|---|---|---|
| Valid required | `{"orderNumber":"ORD-8F31A2"}` | Có thể chạy với default language |
| Missing required | `{}` | Không gọi service nghiệp vụ |
| Null required | `{"orderNumber":null}` | Bị từ chối |
| Empty required | `{"orderNumber":""}` | Bị từ chối |
| Blank required | `{"orderNumber":"   "}` | Bị từ chối |
| Wrong type | `{"orderNumber":100}` | Từ chối hoặc normalize theo policy rõ |
| Optional missing | `{"orderNumber":"ORD-8F31A2"}` | Sử dụng default cho language |
| Optional explicit null | `{"orderNumber":"ORD-8F31A2","language":null}` | Chỉ chấp nhận theo policy đã định |
| Optional wrong type | `{"orderNumber":"ORD-8F31A2","language":[]}` | Từ chối |
| Extra field | `{"orderNumber":"ORD-8F31A2","role":"admin"}` | Không được nâng quyền |
| Nested mismatch | `{"destination":"Da Nang"}` | Từ chối nếu destination là object |
| Enum mismatch | `{"status":"SHIP NOW"}` | Từ chối hoặc alias theo contract |

Có hai mức assert:

- **Schema-level test:** JSON có khớp định nghĩa công khai?
- **Runtime-level test:** callback/service có xử lý input an toàn và đúng nghiệp vụ?

Một test có thể chỉ chứng minh “backend không thực thi” mà không chứng minh framework ném thông báo đẹp; cần kiểm tra thêm error contract nếu sản phẩm yêu cầu model tự phục hồi.

## 23. Test JSON Schema không bằng cách so toàn chuỗi

So sánh nguyên chuỗi `inputSchema()` dễ tạo false failures khi thứ tự property hoặc formatting thay đổi. Nên parse thành `JsonNode` và assert cấu trúc quan trọng:

~~~java
@Test
void toolSchemaMarksRequiredCorrectly() throws Exception {
    ToolDefinition definition =
        callback.getToolDefinition();

    JsonNode root = new ObjectMapper()
        .readTree(definition.inputSchema());

    assertThat(root.path("type").asText())
        .isEqualTo("object");

    List<String> required = new ArrayList<>();
    root.path("required").forEach(node ->
        required.add(node.asText())
    );

    assertThat(required).contains("orderNumber");
    assertThat(required).doesNotContain("language");
    assertThat(root.path("properties").has("orderNumber"))
        .isTrue();
}
~~~

Nên thêm assertion:

- `ToolContext` không có trong `properties`.
- Required field được đánh dấu đúng sau khi đổi annotation.
- Enum values/field types không bị thay đổi ngoài ý muốn.
- Field nhạy cảm như `tenantId`/token không được công bố.
- Input DTO nested vẫn có type/required đúng.
- Tool name/description không bị mất sau refactor.

Khi schema thay đổi có chủ đích, cập nhật contract tests và đánh giá ảnh hưởng đến model/provider cùng một lần.

## 24. Kiểm thử null primitive như một regression riêng

Một test đặc biệt nên bảo đảm thay đổi chữ ký Java không tạo lại lỗi:

~~~java
@Tool(description = "Tìm danh sách đơn")
public List<OrderSummary> find(
        @ToolParam(required = false)
        Integer limit) {

    int safeLimit = limit == null ? 20 : limit;

    if (safeLimit < 1 || safeLimit > 100) {
        throw new InvalidToolInputException(
            "limit không hợp lệ"
        );
    }

    return service.find(safeLimit);
}
~~~

Test:

~~~java
@Test
void absentOptionalLimitUsesDefault() {
    ToolCallback callback = Arrays.stream(
            ToolCallbacks.from(new SearchTools(service))
        )
        .filter(it -> it.getToolDefinition()
            .name().equals("find"))
        .findFirst()
        .orElseThrow();

    callback.call("{}");

    verify(service).find(20);
}
~~~

Với code production, test thêm `{"limit":null}`, `{"limit":0}`, `{"limit":101}` và `{"limit":"large"}`. Nếu muốn một hành vi cụ thể khi null, viết nó rõ trong method hoặc adapter thay vì dựa vào default của primitive.

Test cũng nên chặn việc ai đó refactor `Integer` ngược thành `int` mà không cập nhật schema/validation.

## 25. Streaming và tool-call fragments chưa phải JSON hoàn chỉnh

Khi dùng `chatClient.stream()`, một số provider gửi từng mảnh arguments:

~~~text
part 1: {"order
part 2: Number":"ORD
part 3: -8F31A2"}
complete: {"orderNumber":"ORD-8F31A2"}
~~~

Một chunk riêng lẻ có thể không phải JSON hợp lệ. **Không gọi `ToolCallback.call(...)` từ một fragment** hoặc tự deserialize từng delta như lời gọi hoàn chỉnh.

Spring AI 2.x có `ToolCallPart` và `StreamingParts` phân biệt partial tool-call arguments. `ToolCallingAdvisor` chỉ thực thi khi có tool call hoàn chỉnh theo giao thức model/provider.

Nếu tự điều phối streaming, phải:

1. Ghép fragments theo đúng **tool call ID**.
2. Không trộn arguments của các tool calls trong cùng response.
3. Chờ sự kiện complete theo provider/framework.
4. Sau khi có JSON hoàn chỉnh, mới validate/bind và thực thi.
5. Gắn `ToolResponseMessage` đúng ID và thứ tự.
6. Không lưu raw arguments nhạy cảm vào telemetry mặc định.

Một lỗi “Unexpected end-of-input” có thể xuất phát từ việc parse **partial chunk**, không phải lỗi model cố ý gửi JSON thiếu.

## 26. Quan sát lỗi mà không lộ dữ liệu

Khi production gặp lỗi arguments, log tối thiểu:

~~~text
toolName=get_order_status
toolCallId=<opaque-id>
schemaVersion=v3
failureStage=BINDING
failureCode=ARGUMENT_TYPE_MISMATCH
field=orderNumber
expectedType=string
actualType=number
model=provider/model-family
traceId=<opaque-trace-id>
~~~

Tránh ghi:

~~~text
rawPrompt=<nội dung người dùng>
rawToolArguments=<PII, token, địa chỉ>
rawToolResult=<dữ liệu nghiệp vụ>
stackTrace=<nội bộ không kiểm soát>
~~~

Trong Spring AI, observation cho tool có tên `spring.ai.tool`; khả năng xuất arguments/results dưới dạng span attributes thường tắt mặc định vì nhạy cảm. Không bật raw tracing để sửa một issue mà không có redaction, access control và retention.

Định nghĩa failure codes có cardinality thấp: `JSON_PARSE_ERROR`, `MISSING_REQUIRED`, `NULL_REQUIRED`, `TYPE_MISMATCH`, `ENUM_INVALID`, `VALIDATION_FAILED` và `AUTHORIZATION_DENIED`. Không dùng nguyên value người dùng làm metric tag.

## 27. Checklist khắc phục sự cố

- [ ] Đã xác nhận Spring AI version, model/provider và phương thức `call()`/`stream()`.
- [ ] Biết chính xác tool name, `inputSchema()` và Java signature đang chạy.
- [ ] Đã kiểm tra JSON syntax độc lập với model.
- [ ] Đã phân biệt missing key, explicit `null`, empty và blank string.
- [ ] Required/optional được sinh đúng từ annotation và không mâu thuẫn.
- [ ] Không dùng optional primitive `int`/`boolean` dễ nhận `null` khi bỏ trống.
- [ ] Đã kiểm tra enum, number, date, array và nested DTO shapes.
- [ ] Đã kiểm tra Java parameter names và compiler `-parameters` khi dùng method tool.
- [ ] Đã xác minh `ToolContext` đến từ server, không phải model arguments.
- [ ] Đã kiểm tra Bean Validation/authorization được chạy ở application service.
- [ ] Đã phân biệt lỗi callback binding với REST/SDK/domain failures.
- [ ] Không gửi stack trace, secrets hoặc raw PII vào tool error/result.
- [ ] Có test `ToolCallback.call(...)` trực tiếp cho valid, missing, null, wrong type.
- [ ] Có contract test parse `inputSchema()` thay vì so toàn chuỗi.
- [ ] Streaming không thực thi partial tool-call arguments.
- [ ] Có giới hạn retry, timeout và số tool calls để tránh vòng tự sửa vô hạn.
- [ ] Nếu tool ghi dữ liệu, có authorization, confirmation và idempotency phù hợp.
- [ ] Sau khi sửa, có regression fixture và kiểm tra trên đúng version hiện hành.

## Tài liệu tham khảo

- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): `@Tool`, `@ToolParam`, JSON Schema, `ToolCallback`, `ToolContext`, `MethodToolCallback`, `FunctionToolCallback`, các giới hạn và xử lý exception.
- [Spring AI — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html): tool loop, kết quả, error và đường đồng bộ/streaming.
- [Spring AI 2.1 — Tool Specification Reference](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/tools/reference.html): sinh schema, required/optional, annotations và hợp đồng tool theo phiên bản.
- [JSON Schema — Understanding JSON Schema](https://json-schema.org/understanding-json-schema/): object `required`, nullable type, array, enum và validation.
- [Jackson — Databind](https://github.com/FasterXML/jackson-databind): cách map JSON object sang Java types, lỗi mismatch/invalid format.
- [Java Reflection — Parameter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html): thông tin tham số, tên trong bytecode và reflection.
- [Spring AI issue #6723](https://github.com/spring-projects/spring-ai/issues/6723): báo cáo tình huống thiếu primitive tool parameter trong Spring AI 2.0.0 và lỗi `IllegalArgumentException`; xác minh tình trạng fix theo version của dự án.

**Điểm cần nhớ:** cần phân biệt **schema hướng dẫn model**, **JSON model thực tế tạo**, **kiểu Java callback nhận** và **validation của ứng dụng**. `required` không có nghĩa khác `null`, `optional` không có nghĩa primitive nhận được `null`, và map được JSON sang Java không có nghĩa đã có quyền thực thi. Cách gỡ lỗi tin cậy nhất là đọc generated schema, tái hiện JSON bằng `ToolCallback.call(...)` và kiểm tra bất biến ở service trước khi sửa prompt hoặc nâng phiên bản.

