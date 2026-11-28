# Kiểm thử schema, required field và chuyển đổi kiểu dữ liệu

Trong Spring AI Tool Calling, mô hình ngôn ngữ không gọi một method Java bằng kiểu dữ liệu đã được compiler kiểm tra. Model nhận tên tool và **JSON Schema của tham số**, sau đó sinh một chuỗi JSON làm input. `ToolCallback` của ứng dụng nhận chuỗi đó, chuyển các giá trị sang kiểu Java rồi thực thi nghiệp vụ.

Khoảng cách giữa schema mà model nhìn thấy và dữ liệu thật callback nhận được là nơi dễ phát sinh lỗi: model quên trường bắt buộc, truyền chuỗi thay vì số, dùng enum không hợp lệ, gửi `null` cho primitive hoặc tạo cấu trúc lồng nhau sai. Nếu chỉ test method Java bằng cách gọi trực tiếp, các lỗi này không được phát hiện.

Bài học trình bày chiến lược kiểm thử **ba lớp** cho Spring AI Tool Calling: kiểm tra JSON Schema đã quảng bá; kiểm tra việc chuyển JSON thành đối số Java; và kiểm tra validation ở ranh giới nghiệp vụ trước khi tạo side effect. Các ví dụ chính nhắm Spring AI **2.1.0**, Java 21, JUnit 5, AssertJ và **Jackson 3** (`tools.jackson.*`) trên Spring Boot 4. Với Spring AI 1.x/2.0.x hoặc dự án còn dùng Jackson 2 (`com.fasterxml.jackson.*`), phải điều chỉnh import/API và đối chiếu hành vi exception thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Lấy `ToolDefinition.inputSchema()` từ callback thật và kiểm tra nó như một JSON document.
- Kiểm thử danh sách `required`, tham số tùy chọn và mô tả của `@ToolParam`.
- Phân biệt field vắng mặt, field có giá trị `null`, chuỗi rỗng và giá trị mặc định.
- Kiểm tra chuyển kiểu `String`, `Integer`, `BigDecimal`, enum, record và danh sách lồng nhau.
- Kiểm tra khác biệt giữa `MethodToolCallback` và `FunctionToolCallback` khi tạo input schema.
- Xây dựng negative test độc lập với model provider và không phụ thuộc exception message dễ thay đổi.
- Bổ sung validation ở backend để chặn dữ liệu không hợp lệ trước khi thực thi nghiệp vụ.
- Kiểm tra `ToolContext` không bị đưa vào schema hoặc thay bằng dữ liệu do model tạo.
- Xác minh kết quả tool được serialize đúng và exception được xử lý an toàn.
- Lập bộ regression test khi thay đổi DTO, annotation, Jackson hoặc phiên bản Spring AI.

## Ba lớp hợp đồng cần kiểm thử

~~~mermaid
flowchart TD
    A[Java method / Function input DTO] --> B[JsonSchemaGenerator]
    B --> C[ToolDefinition.inputSchema]
    C --> M[Model sinh JSON arguments]
    M --> V[Kiểm tra JSON shape / schema]
    V --> D[Chuyển JSON sang kiểu Java]
    D --> E[Validation nghiệp vụ và quyền]
    E --> F[Callback thực thi service]
    F --> R[Tool result serialize thành String]
    R --> G[Model diễn giải kết quả]

    C -. Test 1 .-> T1[Schema contract tests]
    D -. Test 2 .-> T2[Conversion tests]
    E -. Test 3 .-> T3[Validation và security tests]
    R -. Test 4 .-> T4[Output serialization tests]
~~~

Ba lớp này **không thay thế nhau**:

| Lớp | Cần đảm bảo | Không tự đảm bảo |
|---|---|---|
| JSON Schema | Model được hướng dẫn về property, type, required, description | Model luôn tuân thủ; backend tự động từ chối mọi vi phạm |
| Chuyển kiểu | JSON hợp lệ được map thành đối số Java theo adapter | Mọi phép ép kiểu đều đúng nghiệp vụ hoặc đủ nghiêm ngặt |
| Business validation | Dữ liệu và quyền hợp lệ trước side effect | Model sẽ chọn tool đúng hay cung cấp đầy đủ thông tin |

`required` trong JSON Schema cho biết **property phải xuất hiện** theo hợp đồng. Nó **khác** việc giá trị chắc chắn khác `null`, khác chuỗi rỗng và khác kiểm tra quyền truy cập. Đây là điểm bắt buộc phải test riêng.

## Công cụ thử nghiệm: giữ dữ liệu nhỏ nhưng đủ kiểu

Sử dụng một tool chỉ **xem trước báo giá**, không ghi dữ liệu, để có thể gọi lặp lại trong unit test.

~~~java
import java.math.BigDecimal;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

enum CurrencyCode {
    VND, USD
}

record QuotePreview(
        String orderId,
        int quantity,
        CurrencyCode currency,
        BigDecimal total
) {}

final class QuoteTools {

    final AtomicInteger invocations = new AtomicInteger();

    @Tool(
        name = "previewQuote",
        description = "Xem trước báo giá cho đơn hàng, không tạo giao dịch"
    )
    public QuotePreview previewQuote(
            @ToolParam(description = "Mã đơn hàng") String orderId,
            @ToolParam(description = "Số lượng nguyên dương") Integer quantity,
            @ToolParam(description = "Đơn vị tiền tệ") CurrencyCode currency,
            @ToolParam(
                description = "Mã giảm giá nếu có",
                required = false
            )
            String coupon,
            ToolContext toolContext) {

        // Validation không phụ thuộc vào việc model có tuân schema.
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (quantity == null || quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (currency == null) {
            throw new IllegalArgumentException("currency is required");
        }

        String tenantId =
                (String) toolContext.getContext().get("tenantId");
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Trusted tenant is required");
        }

        invocations.incrementAndGet();

        return new QuotePreview(
                orderId,
                quantity,
                currency,
                new BigDecimal("150000")
                        .multiply(BigDecimal.valueOf(quantity))
        );
    }
}
~~~

`QuoteTools` là một fixture dùng để minh họa. Trong ứng dụng thực tế, service vẫn phải kiểm tra user có quyền đọc đơn hàng trong tenant hiện tại. `coupon` được đánh dấu optional; các tham số khác mặc định required. `ToolContext` do backend cung cấp, không phải một property do model điền.

**Vì sao dùng `Integer` thay cho `int`?** Nếu model bỏ quên field, wrapper `Integer` có thể mang giá trị `null` để ứng dụng kiểm tra trước khi tính toán. Primitive `int` không biểu diễn được `null` và có thể khiến reflection fail trước khi chạy body của tool. Đây là một failure mode quan trọng khi kiểm thử thiếu tham số.

## Tạo callback thật thay vì chỉ gọi method Java

`ToolCallbacks.from(...)` tạo các `ToolCallback` từ object chứa `@Tool`. Đây là cùng lớp abstraction được dùng khi ứng dụng đưa local tools cho model.

~~~java
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.support.ToolCallbacks;

QuoteTools tools = new QuoteTools();

ToolCallback[] callbacks = ToolCallbacks.from(tools);

assertThat(callbacks).hasSize(1);

ToolCallback callback = callbacks[0];

assertThat(callback.getToolDefinition().name())
        .isEqualTo("previewQuote");
~~~

Test `callback.call(...)` kiểm tra đường chuyển JSON thành đối số và chuyển kết quả về chuỗi. Test `tools.previewQuote(...)` trực tiếp **không** đi qua JSON schema, parsing hay conversion, nên không thể thay thế test callback.

`ToolDefinition` có ba trường cần kiểm tra:

- `name()`: tên model dùng để gọi công cụ.
- `description()`: hướng dẫn model chọn tool.
- `inputSchema()`: JSON Schema của arguments.

Không cần gọi model thật để kiểm tra các phần này; model chỉ là bên sử dụng hợp đồng.

## Kiểm thử JSON Schema đã sinh

### Đọc JSON Schema thành cây thay vì so sánh chuỗi

~~~java
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

JsonNode schema = mapper.readTree(
        callback.getToolDefinition().inputSchema()
);

assertThat(schema.path("type").asString()).isEqualTo("object");
assertThat(schema.path("properties").has("orderId")).isTrue();
assertThat(schema.path("properties").has("quantity")).isTrue();
assertThat(schema.path("properties").has("currency")).isTrue();
assertThat(schema.path("properties").has("coupon")).isTrue();
assertThat(schema.path("properties").has("toolContext")).isFalse();
~~~

Kiểm tra cấu trúc JSON thay vì snapshot cả chuỗi giúp tránh lỗi giả khi JSON Schema generator thay đổi thứ tự property, cách xuống dòng hoặc một số metadata không ảnh hưởng hợp đồng.

Lưu ý, schema của enum hoặc các record phức tạp có thể được biểu diễn qua `$defs`/`$ref` tùy phiên bản và cấu hình. Không luôn giả định `properties.currency.enum` nằm trực tiếp tại property. Hãy kiểm tra nghĩa của schema hoặc dùng schema validator có hỗ trợ `$ref`.

### Kiểm tra required/optional

Mảng `required` là một JSON array chứa tên các thuộc tính bắt buộc. Có thể chuyển nó thành danh sách để assertion:

~~~java
List<String> required =
        StreamSupport.stream(
                schema.path("required").spliterator(),
                false
        )
        .map(JsonNode::asString)
        .toList();

assertThat(required)
        .contains("orderId", "quantity", "currency")
        .doesNotContain("coupon", "toolContext");
~~~

Đừng so sánh thứ tự mảng nếu thứ tự không phải một phần hợp đồng API. Ở đây `coupon` optional không xuất hiện trong `required`; `toolContext` không xuất hiện trong `properties` hay `required`.

Kiểm tra thêm mô tả:

~~~java
assertThat(
        schema.path("properties")
              .path("quantity")
              .path("description")
              .asString()
).contains("Số lượng");
~~~

Mô tả giúp model chọn tham số chính xác, nhưng không phải một validator của dữ liệu thật. Ví dụ mô tả “số lượng nguyên dương” **không** tự thiết lập `minimum: 1`; cần biểu diễn ràng buộc bằng schema/validation phù hợp hoặc kiểm tra trong service.

## Quy tắc required của Spring AI

Spring AI 2.1.0 tạo JSON Schema bằng `JsonSchemaGenerator`. Mặc định, một tham số method được coi là required; có thể thay đổi bằng các annotation dưới đây theo thứ tự ưu tiên được tài liệu hóa:

| Annotation | Tác dụng đối với schema | Điểm cần kiểm thử |
|---|---|---|
| `@ToolParam(required = false)` | Đánh dấu optional | Không có tên tham số trong `required` |
| `@JsonProperty(required = false)` | Tùy chọn theo Jackson | Cần kiểm tra tương tác với annotation ưu tiên cao hơn |
| `@Schema(required = false)` | Tùy chọn theo Swagger/OpenAPI | Chỉ áp dụng khi annotation đó được generator nhận biết |
| `@Nullable` | Cho phép tham số optional | Không có tên tham số trong `required` nếu không có override |
| Không có annotation | Mặc định required | Tên tham số có trong `required` |

Chú ý giữa các phiên bản: một số tài liệu 1.0/2.0 nhắc `@Nullable` từ Spring Framework, còn tài liệu mới có hỗ trợ JSpecify. Nên dùng đúng annotation và import của phiên bản module, không dựa vào một annotation trùng tên từ library khác.

### Khi annotation mâu thuẫn

Ví dụ:

~~~java
@Tool(description = "Kiểm tra giá bán")
public String check(
        @ToolParam(required = true)
        @Nullable
        String productId) {
    // ...
}
~~~

`@ToolParam` có độ ưu tiên cao hơn `@Nullable` theo tài liệu. Test phải đọc schema sinh ra và xác nhận `productId` vẫn nằm trong `required`. Nếu đổi annotation nhưng test vẫn PASS theo giả định cũ, đó là dấu hiệu hợp đồng model đã thay đổi ngoài ý muốn.

Với `@JsonProperty`/`@Schema`, hãy kiểm tra chính xác phiên bản: thuộc tính `required` hoặc `requiredMode` của thư viện có thể thay đổi theo đời Jackson/Swagger. Không dùng annotation “trông giống optional” rồi bỏ qua test schema thực tế.

### Required khác non-null và non-empty

Xét ba lời gọi:

~~~json
{}
~~~

~~~json
{"orderId": null}
~~~

~~~json
{"orderId": ""}
~~~

Cả ba đều khác nhau:

- **Vắng field:** không có property tên `orderId`.
- **Có `null`:** property hiện diện nhưng giá trị rỗng theo JSON.
- **Chuỗi rỗng:** giá trị là một `String` có độ dài 0.

Schema `required: ["orderId"]` chỉ yêu cầu **sự hiện diện**. Muốn cấm `null` cần schema type không cho null và/hoặc validation; muốn cấm chuỗi rỗng cần `minLength` hoặc kiểm tra nghiệp vụ. Không coi một assertion trên `required` là đã kiểm tra được cả ba tình huống.

## Bảng trường hợp cần test

| JSON đầu vào | Kết quả hợp đồng mong muốn | Đường kiểm thử |
|---|---|---|
| Có đủ required, đúng kiểu | Chấp nhận và chuyển đúng Java type | `callback.call(...)` |
| Thiếu `coupon` optional | Chấp nhận, Java nhận `null`/giá trị mặc định được quy định | Callback và fixture |
| Thiếu `orderId` required | Từ chối trước side effect | Schema validator hoặc input guard |
| `orderId: null` | Từ chối nếu không cho phép null | Input guard và service |
| `orderId: ""` | Từ chối chuỗi rỗng | Business validation |
| `quantity: 2` | Map thành `Integer(2)` | Callback |
| `quantity: "2"` | Từ chối nếu hợp đồng yêu cầu integer nghiêm ngặt | JSON type validator |
| `quantity: 2.7` | Từ chối số lẻ cho số lượng | JSON type validator |
| `quantity: -1` | Từ chối vì vi phạm nghiệp vụ | Service validation |
| `currency: "VND"` | Map thành enum `CurrencyCode.VND` | Callback |
| `currency: "GBP"` | Từ chối enum ngoài tập | Parser/validator |
| JSON sai cú pháp | Trả lỗi đầu vào, không gọi service | Parser hoặc guard |
| Thừa property lạ | Chấp nhận/từ chối theo chính sách đã định | Schema validator hoặc guard |
| Không có `ToolContext` hợp lệ | Từ chối/không truy vấn tenant | Backend security |

**Không khẳng định mọi đầu vào sai schema đều tự động bị Spring AI từ chối.** Bộ tạo schema dùng để mô hình hiểu cách tạo lời gọi; đường deserialization của callback có thể ép kiểu một số giá trị hoặc ném exception theo cách khác nhau giữa các phiên bản.

## Kiểm thử chuyển kiểu từ JSON qua MethodToolCallback

### Trường hợp hợp lệ

Dùng callback thật và truyền `ToolContext`:

~~~java
ToolCallback callback = ToolCallbacks.from(tools)[0];

String output = callback.call("""
    {
      "orderId": "DH-1024",
      "quantity": 2,
      "currency": "VND"
    }
    """, new ToolContext(Map.of("tenantId", "acme")));

QuotePreview quote = mapper.readValue(output, QuotePreview.class);

assertThat(quote.orderId()).isEqualTo("DH-1024");
assertThat(quote.quantity()).isEqualTo(2);
assertThat(quote.currency()).isEqualTo(CurrencyCode.VND);
assertThat(quote.total())
        .isEqualByComparingTo(new BigDecimal("300000"));
assertThat(tools.invocations.get()).isEqualTo(1);
~~~

Ví dụ xác minh:

1. Chuỗi JSON được parse.
2. `quantity` được chuyển thành `Integer`.
3. `currency` được chuyển thành enum.
4. `coupon` được bỏ qua vẫn không cản trở lời gọi.
5. `ToolContext` đến được method.
6. DTO kết quả được serialize thành chuỗi và parse lại được.
7. Tool được gọi đúng một lần.

Nếu hệ thống dùng Jackson phiên bản/cấu hình riêng, hãy chạy test này trên đúng classpath của ứng dụng. Không giả định mọi kiểu Java hoặc module Jackson đều được callback mặc định hỗ trợ.

### Test giá trị tùy chọn có mặt và vắng mặt

~~~java
final class CouponTools {

@Tool(description = "Xác nhận mã giảm giá tùy chọn")
public String formatCoupon(
        @ToolParam(required = false) String coupon) {
    return coupon == null ? "<none>" : coupon;
}

}
~~~

Test hai input:

~~~java
ToolCallback couponTool = ToolCallbacks.from(new CouponTools())[0];

assertThat(couponTool.call("{}")).isEqualTo("<none>");
assertThat(couponTool.call("""
    {"coupon":"KM-2026"}
    """)).isEqualTo("KM-2026");
~~~

`CouponTools` ở đây là class chứa method `formatCoupon` nêu trên; test nên giữ fixture này thật nhỏ và không phụ thuộc service bên ngoài.

Nếu ứng dụng muốn phân biệt **field vắng mặt** với **field có giá trị null**, đừng dùng riêng một tham số `String` rồi kỳ vọng Java tự phân biệt được hai trường hợp. Hãy kiểm tra raw JSON trước khi deserialize, hoặc thiết kế DTO/trạng thái ba giá trị rõ ràng.

## Kiểm thử kiểu dữ liệu với FunctionToolCallback

Với function-based tool, JSON Schema thường được tạo từ **kiểu đầu vào** do `inputType(...)` cung cấp, thay vì danh sách tham số của method.

~~~java
import java.math.BigDecimal;
import java.util.function.Function;

import org.springframework.ai.tool.function.FunctionToolCallback;

record QuoteRequest(
        String orderId,
        Integer quantity,
        CurrencyCode currency,
        @ToolParam(required = false) String coupon
) {}

Function<QuoteRequest, QuotePreview> function = request ->
        new QuotePreview(
                request.orderId(),
                request.quantity(),
                request.currency(),
                BigDecimal.valueOf(request.quantity())
                          .multiply(new BigDecimal("150000"))
        );

FunctionToolCallback<QuoteRequest, QuotePreview> functionTool =
        FunctionToolCallback
                .builder("quoteWithFunction", function)
                .description("Tính thử báo giá từ JSON input DTO")
                .inputType(QuoteRequest.class)
                .build();
~~~

Test schema:

~~~java
JsonNode functionSchema = mapper.readTree(
        functionTool.getToolDefinition().inputSchema()
);

assertThat(functionSchema.path("properties").has("orderId")).isTrue();
assertThat(functionSchema.path("properties").has("quantity")).isTrue();
assertThat(functionSchema.path("properties").has("currency")).isTrue();
~~~

Test conversion:

~~~java
String output = functionTool.call("""
    {
      "orderId": "DH-2048",
      "quantity": 3,
      "currency": "USD"
    }
    """);

QuotePreview actual = mapper.readValue(output, QuotePreview.class);

assertThat(actual.orderId()).isEqualTo("DH-2048");
assertThat(actual.quantity()).isEqualTo(3);
assertThat(actual.currency()).isEqualTo(CurrencyCode.USD);
~~~

Chú ý: trong `FunctionToolCallback`, record là **root object** của JSON input. Trong `MethodToolCallback` có method nhận một DTO `QuoteRequest request`, input schema có thể bọc DTO bên dưới property `request`. Đây là khác biệt quan trọng khi chuyển một method tool sang function tool: cần test schema thật và payload thật, không giả định hai kiểu callback có chung cấu trúc đầu vào.

Các kiểu reactive/async như `Mono`, `Flux`, `Future` và `CompletableFuture` không phải kiểu input/output trực tiếp được method tool hỗ trợ; hãy dùng DTO có thể serialize thay vì kỳ vọng converter tự await publisher.

## Kiểm thử record, danh sách và cấu trúc lồng nhau

Nhiều tool có đầu vào phức tạp, ví dụ tạo báo giá cho nhiều mặt hàng:

~~~java
record LineItem(
        String sku,
        Integer quantity,
        BigDecimal unitPrice
) {}

record BatchQuoteRequest(
        String customerId,
        List<LineItem> items,
        @ToolParam(required = false) String note
) {}
~~~

Với `FunctionToolCallback<BatchQuoteRequest, BatchQuoteResult>`, JSON có dạng:

~~~json
{
  "customerId": "C-42",
  "items": [
    {"sku": "SP-A", "quantity": 2, "unitPrice": 125000.50},
    {"sku": "SP-B", "quantity": 1, "unitPrice": 99000}
  ]
}
~~~

Bộ test cần kiểm tra:

- `items` thực sự có JSON type `array` và element có các property cần thiết.
- `sku` là string, `quantity` là integer, `unitPrice` là number theo schema đã sinh.
- Giá trị `BigDecimal` được chuyển với độ chính xác mong đợi; không trung gian qua `double` nếu nghiệp vụ là tiền.
- Bỏ `items`, dùng mảng rỗng, phần tử `null` và một phần tử thiếu `sku` được xử lý theo chính sách.
- Một `quantity` âm, bằng 0 hoặc vượt giới hạn được service từ chối, kể cả khi JSON parser chấp nhận.

JSON Schema có thể dùng `$defs` hoặc `$ref` cho record lồng nhau. Đừng assertion ở một path cứng chỉ hoạt động với một version generator. Nếu cần kiểm tra toàn bộ tính hợp lệ, sử dụng JSON Schema validator hỗ trợ draft và `$ref` mà hệ thống đã chọn, rồi test dữ liệu hợp lệ/không hợp lệ qua validator đó.

**Chuyển kiểu thành công không có nghĩa dữ liệu hợp lệ.** `quantity = -5` có thể deserialize hoàn toàn đúng thành `Integer(-5)` nhưng vẫn vi phạm nghiệp vụ.

## Test enum và các phép ép kiểu không mong muốn

### Enum không nằm trong tập cho phép

Model có thể trả:

~~~json
{
  "orderId": "DH-1024",
  "quantity": 2,
  "currency": "GBP"
}
~~~

Nhưng enum chỉ có `VND` và `USD`. Bộ test không nên khẳng định một exception message duy nhất trên tất cả bản Spring AI: hành vi parse và cách bọc exception đã thay đổi trong quá trình phát triển.

Một negative test ở lớp chuyển đổi có thể:

~~~java
assertThatThrownBy(() ->
        callback.call("""
            {
              "orderId": "DH-1024",
              "quantity": 2,
              "currency": "GBP"
            }
            """, new ToolContext(Map.of("tenantId", "acme")))
).isInstanceOf(RuntimeException.class);

assertThat(tools.invocations.get()).isZero();
~~~

Assertion này xác nhận callback không thể xử lý enum không hợp lệ thành một lần thực thi nghiệp vụ thành công. Khi dự án khóa Spring AI BOM cụ thể, có thể thêm assertion chính xác cho `ToolExecutionException` hoặc loại exception đã được xác nhận bằng test.

### Chuỗi số và số thập phân

Tùy converter/Jackson configuration, JSON `"2"` có thể bị từ chối hoặc được ép thành `Integer(2)`. Tương tự `2.7` có thể bị từ chối hoặc qua một phép chuyển kiểu ngoài mong đợi. Vì vậy, nếu nghiệp vụ cần integer nghiêm ngặt, **đừng để chính sách phụ thuộc vào default Jackson coercion**.

Test “chính sách nghiêm ngặt” ở lớp input validator:

~~~java
JsonNode args = mapper.readTree("""
    {"quantity": "2"}
    """);

assertThat(args.path("quantity").isIntegralNumber()).isFalse();
~~~

Assertion chỉ kiểm tra loại dữ liệu JSON gốc. Nó không chứng minh `MethodToolCallback` mặc định sẽ từ chối; việc **từ chối trước side effect** phải do validator/wrapper của ứng dụng đảm nhận.

## Đặt validation trước khi gọi service

Một cách bảo vệ là dùng wrapper `ToolCallback` để kiểm tra raw JSON **trước khi ủy quyền** cho callback thật. Wrapper này kiểm soát yêu cầu tối thiểu của nghiệp vụ: object JSON, required field, kiểu dữ liệu và enum.

~~~java
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.ToolDefinition;
import org.springframework.ai.tool.ToolMetadata;

public final class StrictQuoteToolCallback implements ToolCallback {

    private final ToolCallback delegate;
    private final ObjectMapper mapper;

    public StrictQuoteToolCallback(
            ToolCallback delegate,
            ObjectMapper mapper) {
        this.delegate = delegate;
        this.mapper = mapper;
    }

    @Override
    public ToolDefinition getToolDefinition() {
        return delegate.getToolDefinition();
    }

    @Override
    public ToolMetadata getToolMetadata() {
        return delegate.getToolMetadata();
    }

    @Override
    public String call(String input) {
        return call(input, null);
    }

    @Override
    public String call(String input, ToolContext context) {
        JsonNode data;

        try {
            data = mapper.readTree(input);
        }
        catch (JacksonException ex) {
            throw new IllegalArgumentException(
                    "Tool arguments must be valid JSON", ex
            );
        }

        if (data == null || !data.isObject()) {
            throw new IllegalArgumentException(
                    "Tool arguments must be a JSON object"
            );
        }

        if (!data.path("orderId").isString()
                || data.path("orderId").asString().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        if (!data.path("quantity").isIntegralNumber()
                || !data.path("quantity").canConvertToInt()
                || data.path("quantity").intValue() <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be a positive integer"
            );
        }

        if (!data.path("currency").isString()
                || !Set.of("VND", "USD")
                       .contains(data.path("currency").asString())) {
            throw new IllegalArgumentException(
                    "Unsupported currency"
            );
        }

        if (data.has("coupon")
                && !data.get("coupon").isNull()
                && !data.get("coupon").isString()) {
            throw new IllegalArgumentException(
                    "coupon must be a string or null"
            );
        }

        return delegate.call(input, context);
    }
}
~~~

Ví dụ này là một **validator thủ công cho một tool**, không phải bộ triển khai đầy đủ JSON Schema Draft. Nó chỉ xử lý các trường được liệt kê; nếu cần chặn unknown properties, giới hạn độ dài chuỗi, kích thước danh sách hay schema lồng nhau, hãy thêm các quy tắc đó hoặc dùng JSON Schema validator.

Wrapper cần chuyển tiếp `getToolDefinition()`, `getToolMetadata()` và `ToolContext` để không mất `returnDirect`, confirmation hoặc metadata của tool gốc. Với Spring AI, thứ tự xử lý và loại exception trả về model/caller cần được cấu hình ở tầng exception processor.

### Kiểm thử wrapper không tạo side effect khi input sai

~~~java
QuoteTools tools = new QuoteTools();
ToolCallback delegate = ToolCallbacks.from(tools)[0];

ToolCallback validated =
        new StrictQuoteToolCallback(delegate, new ObjectMapper());

assertThatThrownBy(() -> validated.call("""
    {
      "orderId": "DH-1024",
      "quantity": "2",
      "currency": "VND"
    }
    """, new ToolContext(Map.of("tenantId", "acme"))))
        .isInstanceOf(IllegalArgumentException.class);

assertThat(tools.invocations.get()).isZero();
~~~

Nếu muốn kiểm tra toàn bộ `required`/`type` của một JSON Schema, thay phần kiểm tra thủ công bằng validator phù hợp và bổ sung test khớp schema cho các phiên bản. Giữ validation nghiệp vụ và kiểm tra quyền ở service ngay cả khi có schema validator trước callback.

## Thiếu trường required: regression cho primitive

Spring AI có một tình huống dễ bỏ sót: optional primitive như `boolean` hoặc `int` không thể nhận `null` khi tham số bị model bỏ qua. Một issue công khai của Spring AI (#6723, tháng 8/2026) ghi nhận trên **Spring AI 2.0.0** rằng thiếu optional primitive có thể gây `IllegalArgumentException` trực tiếp từ Java reflection, không đi qua `ToolExecutionExceptionProcessor` như một số lỗi chuyển đổi khác.

Ví dụ cần tránh:

~~~java
@Tool(description = "Tra cứu tùy chọn")
public String search(
        String keyword,
        @ToolParam(required = false) boolean includeArchived) {
    return "...";
}
~~~

Nên dùng wrapper object:

~~~java
@Tool(description = "Tra cứu tùy chọn")
public String search(
        String keyword,
        @ToolParam(required = false) Boolean includeArchived) {

    boolean include = Boolean.TRUE.equals(includeArchived);
    return searchService.search(keyword, include);
}
~~~

Bộ regression nên có ít nhất:

- Không gửi `includeArchived`.
- Gửi `includeArchived: null` nếu hợp đồng cho phép.
- Gửi `includeArchived: true` và `false`.
- Gửi chuỗi `"true"` và xác minh chính sách strict/coercion mong muốn.
- Xác minh không có side effect nếu dữ liệu không hợp lệ.

Issue trên nêu hiện tượng ở một bản cụ thể, **không đủ căn cứ kết luận mọi bản 2.x đều giữ lỗi y hệt**. Khóa đúng Spring AI BOM rồi chạy lại regression test trước khi nâng cấp.

## Required ở schema không thay thế Bean Validation

Annotation như `@NotBlank`, `@Min` hoặc `@Valid` có thể phù hợp để diễn đạt ràng buộc nghiệp vụ, nhưng không nên mặc định rằng chỉ cần đặt annotation trên mọi method tool là Spring AI sẽ tự kích hoạt Spring MVC/Bean Validation giống một REST controller.

Một method `@Tool` có thể được gọi bằng reflection qua callback, ngoài pipeline validation của controller. Tùy adapter, method có thể không chạy validation interceptor. Nếu bắt buộc kiểm tra, hãy:

1. Gọi `Validator` trong service/wrapper, hoặc dùng service được Spring proxy có validation cấu hình đúng.
2. Viết test gọi **`ToolCallback.call(...)`**, không chỉ test controller.
3. Bảo đảm mọi đường gọi (REST, message consumer, scheduler, AI tool) đều đi qua cùng service validation.
4. Ánh xạ validation error thành lỗi an toàn, không để lộ stack trace hoặc thông tin nội bộ.

Ví dụ các ràng buộc nghiệp vụ cần test: mã đơn được phép truy cập, số lượng nằm trong giới hạn, tổng tiền tối đa, số phần tử danh sách, chuỗi không rỗng, ngày không ở quá khứ và idempotency key hợp lệ.

## Kiểm thử ngày giờ và tiền tệ

Một số kiểu chuyển đổi phụ thuộc nhiều vào cấu hình parser:

| Kiểu Java | JSON đầu vào khuyến nghị | Lưu ý |
|---|---|---|
| `String` | `"DH-1024"` | Kiểm tra blank, length và pattern ở service |
| `Integer` | `2` | Không nhận string/decimal nếu hợp đồng strict |
| `Long` | `9007199254740993` | Kiểm tra biên, precision ở model/provider |
| `BigDecimal` | `125000.50` | Không đổi sang `double` để tính tiền |
| Enum | `"VND"` | Enum values cần khớp tên/cách mapping đã định |
| `LocalDate` | `"2026-11-27"` | Định dạng ISO-8601; phụ thuộc mapper/module |
| `Instant` | `"2026-11-27T13:00:00Z"` | Dùng UTC và cấu hình Jackson Java Time phù hợp |
| `List<LineItem>` | `[{"sku":"A","quantity":2}]` | Test phần tử rỗng/null và cấu trúc lồng nhau |

Nếu callback dùng Jackson parser với cấu hình nội bộ, một `ObjectMapper` tự tạo trong unit test có thể hoạt động khác với mapper Spring AI thực dùng. Hãy luôn có test chạy qua **callback thật** cho các kiểu quan trọng như `Instant` và enum. Không kết luận rằng cấu hình `ObjectMapper` của Spring Boot chắc chắn được mọi tool adapter Spring AI/MCP tái sử dụng.

### Lưu ý Jackson 2 và Jackson 3 theo phiên bản

Spring Boot 4 ưu tiên **Jackson 3**: import `tools.jackson.databind.ObjectMapper`, `tools.jackson.databind.JsonNode` và `tools.jackson.core.JacksonException`; ví dụ trong bài dùng `JsonNode.asString()`/`isString()`. Jackson 3 vẫn có `asText()` và `isTextual()` nhưng đã deprecated. Với dự án Spring Boot 3 hoặc còn khóa Jackson 2, các package tương ứng là `com.fasterxml.jackson.databind.*` và `com.fasterxml.jackson.core.JsonProcessingException`; `asText()`/`isTextual()` là các method quen thuộc.

Đừng trộn `JsonNode` của Jackson 2 với `ObjectMapper` của Jackson 3 trong cùng một snippet. Trên Spring AI 2.1.0, hãy dùng cùng bộ thư viện mà ứng dụng đang chạy và kiểm tra sự tương thích khi nâng cấp.

Với tiền tệ, test `BigDecimal` bằng `isEqualByComparingTo` hoặc quy tắc scale đã thống nhất, không so sánh qua `double`. Với ngày giờ, chuẩn hóa UTC và xác minh timezone tại ranh giới API.

## Kiểm thử kết quả tool và dữ liệu nhạy cảm

Đầu vào đúng chưa đủ: giá trị method trả về phải được `ToolCallResultConverter` chuyển thành chuỗi mà model/ứng dụng có thể sử dụng.

Spring AI cung cấp `DefaultToolCallResultConverter` dựa trên Jackson để serialize kết quả tool. Với DTO, nên kiểm tra JSON theo cấu trúc:

~~~java
String output = callback.call("""
    {"orderId":"DH-1024","quantity":2,"currency":"VND"}
    """, new ToolContext(Map.of("tenantId", "acme")));

JsonNode result = mapper.readTree(output);

assertThat(result.path("orderId").asString())
        .isEqualTo("DH-1024");
assertThat(result.path("total").decimalValue())
        .isEqualByComparingTo(new BigDecimal("300000"));
assertThat(result.has("internalToken")).isFalse();
~~~

`internalToken` chỉ là một trường cấm ví dụ; một hệ thống thực tế cần test không xuất hiện API token, secret, password hash, stack trace hay trường dữ liệu khách hàng không được phép đưa cho model.

Nếu dùng custom `ToolCallResultConverter`, cần test cả content-type và cấu trúc chuỗi sau conversion, kể cả kết quả `null`/`void`. Không nhầm schema **input** của tool với JSON **output** sau khi callback chạy.

## Lỗi và ToolExecutionExceptionProcessor

Khi callback hoặc service thất bại, Spring AI có cơ chế xử lý `ToolExecutionException` và `ToolExecutionExceptionProcessor`. Tài liệu 2.1.0 mô tả processor có thể biến lỗi thành text gửi model hoặc ném lỗi lên caller; property liên quan là:

~~~yaml
spring:
  ai:
    tools:
      throw-exception-on-error: true
~~~

Chính sách cụ thể phụ thuộc ứng dụng. Với công cụ ghi, lỗi input không hợp lệ thường cần chặn trước side effect và trả mã lỗi ổn định cho caller. Với lỗi có thể giải thích cho model, chỉ gửi thông điệp đã lọc, không đưa exception stack hoặc dữ liệu nhạy cảm.

Cần test riêng:

- Exception ở deserialization/typing trước khi method được gọi.
- Exception do validation trong method/service.
- Exception từ network/database sau khi method đã bắt đầu.
- Hành vi khi `throw-exception-on-error` bật/tắt.
- Không retry hoặc gọi lại tool ghi một cách mù sau lỗi/timeout không rõ kết quả.

Không giả định mọi exception được bọc cùng một kiểu qua tất cả phiên bản. Negative tests nên xác nhận **hành vi quan trọng**: callback không tạo side effect, error được phân loại an toàn và vòng chat không bỏ qua quy tắc bảo mật.

## Bộ kiểm thử tích hợp không phụ thuộc model thật

Một quy trình test hợp lý gồm:

1. Tạo `QuoteTools` thật hoặc mock service phía sau.
2. Lấy callback bằng `ToolCallbacks.from(...)`.
3. Đọc JSON Schema, test required/optional/type/description.
4. Gọi callback bằng một ma trận JSON input hợp lệ và không hợp lệ.
5. Xác minh kiểu đối số mà service nhận, số lần gọi và output converter.
6. Thử nhiều `ToolContext` cho hai tenant khác nhau; đảm bảo không trộn dữ liệu.
7. Với `ChatClient`, dùng model stub/fake trả tool call để xác minh callback được gọi và kết quả được đưa lại model.
8. Với provider thực tế, chỉ thêm smoke/integration test nhỏ cho việc provider có tuân schema mong muốn hay không.

Model thật không cần thiết để kiểm tra schema generator và JSON-to-Java conversion; dùng model thật ở giai đoạn cuối để đo **tỷ lệ model tự sinh input hợp lệ** cho schema và mô tả đã thiết kế.

### Bảng test nên tự động hóa

| Test | Điều kiện PASS |
|---|---|
| `requiredFieldsAreCorrect` | Required gồm ba field đúng; coupon optional |
| `toolContextNeverAppearsInSchema` | Không có tenantId/userId/toolContext |
| `validJsonMapsToExpectedJavaTypes` | Quantity là Integer, enum đúng, return DTO đúng |
| `missingOptionalFieldIsAccepted` | Không có coupon vẫn gọi được |
| `missingRequiredFieldIsRejectedByGuard` | Không gọi service khi thiếu orderId |
| `nullAndBlankAreDistinct` | Policy xử lý rõ null/blank |
| `stringNumberIsRejectedInStrictMode` | Không ép `"2"` thành `2` nếu policy strict |
| `unknownEnumIsRejected` | `GBP` không thành enum hợp lệ |
| `malformedJsonDoesNotExecuteTool` | Lỗi parsing không chạy business method |
| `nestedListItemsAreValidated` | Danh sách có cấu trúc và giới hạn |
| `resultSerializationExcludesSecrets` | Output không chứa trường nhạy cảm |
| `twoTenantsStayIsolated` | ToolContext được truyền và service kiểm tra quyền |
| `primitiveOptionalMissingRegression` | Không bỏ qua lỗi missing primitive khi nâng cấp |
| `errorProcessorDoesNotLeakDetails` | Lỗi được làm sạch theo policy |

Đối với tool có side effect, mọi negative test quan trọng phải xác minh số lần gọi service ghi bằng **0**. Với test concurrency, dùng idempotency key ổn định và xác minh hai request trùng không tạo hai giao dịch.

## Golden schema snapshots và nâng cấp phiên bản

Khi thay đổi Java record, annotation, version Jackson hoặc Spring AI BOM, JSON Schema sinh ra có thể đổi. Snapshot có thể phát hiện thay đổi bất ngờ, nhưng nên dùng có chọn lọc:

- Normalize JSON để bỏ qua thứ tự property không có ý nghĩa.
- So sánh tên, type, enum và required fields theo semantic contract.
- Kiểm tra `additionalProperties`, `$defs` và `$ref` khi provider phụ thuộc strict schema.
- Tránh snapshot toàn bộ description nếu thay câu chữ thường xuyên; chỉ khóa những mô tả quan trọng.
- Test callback thực thi với input hợp lệ/không hợp lệ để tránh “schema đúng nhưng conversion sai”.
- Chạy regression trên Spring AI BOM mục tiêu trước khi deploy.

Các khác biệt đáng chú ý khi chuyển từ Spring AI 1.x sang 2.x: vòng tool calling chuyển sang `ToolCallingAdvisor`; cách đăng ký tool trên `ChatClient` dùng `.tools(...)`/`.defaultTools(...)` theo API 2.x. Tuy nhiên, trọng tâm bộ test schema là `ToolDefinition.inputSchema()` và `ToolCallback.call(...)`, không phụ thuộc việc model gọi tool qua advisor hay `ChatModel`.

Nếu schema được cung cấp thủ công qua `ToolDefinition.builder().inputSchema(...)`, kiểm thử càng cần thiết: việc model thấy schema viết tay **không tự bảo đảm** Java function phía sau có đúng kiểu đầu vào mà schema mô tả.

## Lỗi thường gặp

- **Chỉ unit test method Java:** bỏ qua JSON parsing, schema và callback converter.
- **Đồng nhất required với non-null/non-empty:** mảng `required` chỉ yêu cầu property xuất hiện.
- **Kỳ vọng `@ToolParam(required = true)` là backend validator:** nó chủ yếu điều khiển schema cho model.
- **Dùng `int`/`boolean` cho optional field:** không có giá trị để biểu diễn “không gửi”; dễ lỗi reflection.
- **Không test sai enum:** model có thể tạo giá trị ngoài enum; hành vi exception thay đổi theo version.
- **Cho rằng chuỗi số luôn bị từ chối:** Jackson có thể có coercion; dùng validator strict khi cần.
- **So sánh chuỗi schema nguyên văn:** dễ fail do khác thứ tự field dù hợp đồng không đổi.
- **Giả định mọi DTO lồng nhau có path schema giống nhau:** generator có thể dùng `$defs`/`$ref`.
- **Không kiểm thử `ToolContext`:** dễ đưa nhầm tenant/user vào input model tự sinh.
- **Giả định Jackson ObjectMapper của app được mọi adapter dùng:** cần test callback thực tế.
- **Chỉ kiểm tra exception type mà quên side effect:** tool vẫn có thể đã thực thi một phần trước lỗi.
- **Để exception text nội bộ gửi thẳng model:** có thể lộ URL, token hoặc chi tiết hệ thống.
- **Không test khi nâng cấp BOM:** schema, type coercion và exception wrapping có thể thay đổi.

## Checklist trước khi hoàn thành

- [ ] Test lấy callback thật và parse `ToolDefinition.inputSchema()` thành JSON.
- [ ] Test tên, description, property types và required/optional.
- [ ] Test annotation precedence theo phiên bản đang dùng.
- [ ] Test missing, explicit null, blank và sai kiểu.
- [ ] Test integer/decimal, enum, BigDecimal, ngày giờ và nested DTO quan trọng.
- [ ] Test `MethodToolCallback` và `FunctionToolCallback` nếu ứng dụng dùng cả hai.
- [ ] Test business validation chặn side effect cho input sai.
- [ ] Test ToolContext không xuất hiện trong schema và quyền tenant được enforce.
- [ ] Test kết quả được serialize thành text đúng và không lộ secret.
- [ ] Test hành vi exception processor và lỗi parsing.
- [ ] Có regression test cho optional primitive nếu module đang dùng kiểu này.
- [ ] Test schema khi thay đổi Spring AI BOM, Jackson hoặc DTO.
- [ ] Không cần gọi model thật cho phần lớn test; chỉ dùng provider test khi đánh giá chất lượng sinh argument.

## Ghi nhớ

Kiểm thử Tool Calling cần đi qua **callback thật**, không chỉ gọi method Java. Hãy đọc `ToolDefinition.inputSchema()` để xác minh model nhìn thấy đúng tên, kiểu và danh sách required/optional; sau đó dùng `ToolCallback.call(...)` với JSON hợp lệ và không hợp lệ để kiểm tra chuyển đổi sang Java type.

`required` là một phần của JSON Schema, không phải bảo đảm dữ liệu đầu vào đã được backend kiểm tra. Trường thiếu, `null`, chuỗi rỗng, enum sai và numeric coercion cần được xử lý rõ ở validator/service. Với thao tác ghi, chỉ cho phép side effect sau khi validation và authorization thành công; test bắt buộc phải xác minh không có side effect khi input sai.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling, JSON Schema, ToolCallback và Exception Handling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html)
- [Spring AI — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI API — JsonSchemaGenerator](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/util/json/schema/JsonSchemaGenerator.html)
- [Spring AI API — MethodToolCallback](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/method/MethodToolCallback.html)
- [Spring AI issue #6723 — Missing optional primitive argument](https://github.com/spring-projects/spring-ai/issues/6723)
- [Spring Boot 4 — JSON và Jackson 3](https://docs.spring.io/spring-boot/reference/features/json.html)
- [Jackson 3 — JsonNode API](https://javadoc.io/static/tools.jackson.core/jackson-databind/3.0.0/tools.jackson.databind/tools/jackson/databind/JsonNode.html)
- [Jackson — Deserialization Features](https://github.com/FasterXML/jackson-databind/wiki/Deserialization-Features)

