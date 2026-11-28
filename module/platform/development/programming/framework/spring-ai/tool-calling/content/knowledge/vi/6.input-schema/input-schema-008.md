# Tùy chỉnh schema bằng annotation Spring AI, Jackson hoặc Swagger

Khi Spring AI công bố một method thành tool, framework tạo JSON Schema từ các tham số của method. Schema này được gửi cùng định nghĩa tool để mô hình biết tên trường, kiểu dữ liệu, ý nghĩa và trường nào bắt buộc phải có. Một chữ ký Java đúng cú pháp vẫn có thể tạo ra schema khó hiểu nếu tên tham số mơ hồ, mô tả thiếu định dạng hoặc đánh dấu sai trạng thái bắt buộc.

Spring AI hỗ trợ ba nhóm annotation để bổ sung thông tin cho schema: annotation riêng của Spring AI, annotation Jackson và annotation Swagger. Có thể dùng chúng trực tiếp trên tham số method hoặc trên các thuộc tính của kiểu dữ liệu lồng nhau. Bài học này tập trung vào hai thông tin được hỗ trợ rõ ràng trong quá trình sinh schema: mô tả và trạng thái required/optional.

## Sau bài học, bạn có thể

- Giải thích cách Spring AI sinh JSON Schema từ tham số của method hoặc function.
- Dùng `@ToolParam` để mô tả tham số và xác định tham số bắt buộc.
- Dùng `@JsonClassDescription`, `@JsonPropertyDescription` và `@JsonProperty` của Jackson.
- Dùng `@Schema` của Swagger để bổ sung mô tả và trạng thái optional.
- Hiểu thứ tự ưu tiên khi nhiều annotation cùng khai báo required/optional.
- Tùy chỉnh schema cho DTO hoặc record lồng nhau.
- Kiểm tra schema thực tế và xác thực dữ liệu ở phía ứng dụng trước khi thực thi nghiệp vụ.

## Schema đầu vào là hợp đồng giữa model và ứng dụng

Một tool có ba thông tin mô tả chính:

- **Tên tool:** định danh mà model dùng khi yêu cầu gọi công cụ.
- **Mô tả tool:** giải thích tool làm gì và khi nào nên dùng.
- **Input schema:** mô tả cấu trúc JSON mà model phải tạo để gọi tool.

Ví dụ người dùng yêu cầu: “Tìm laptop màu đen, giá tối đa 25 triệu, chỉ lấy 5 sản phẩm”. Ứng dụng có thể cung cấp tool `searchProducts` với các tham số `keyword`, `color`, `maxPrice` và `limit`. Schema giúp model hiểu rằng `keyword` là chuỗi, `maxPrice` là số, `limit` là số nguyên và một số tham số có thể được bỏ qua.

Luồng xử lý có thể hình dung như sau:

~~~mermaid
flowchart TD
    A[Method Java và annotation] --> B[Spring AI JsonSchemaGenerator]
    B --> C[ToolDefinition: name, description, inputSchema]
    C --> D[Đưa định nghĩa tool vào request]
    D --> E[Model tạo tên tool và đối số JSON]
    E --> F[Ứng dụng ánh xạ và kiểm tra đầu vào]
    F --> G[ToolCallback gọi dịch vụ nghiệp vụ]
    G --> H[Kết quả được trả về theo luồng tool calling]
~~~

Schema không phải mã thực thi và cũng không phải lớp bảo mật. Nó hướng dẫn model tạo đầu vào theo một cấu trúc mà ứng dụng mong đợi. Ứng dụng vẫn phải kiểm tra dữ liệu, xác thực người dùng và phân quyền trước khi gọi dịch vụ.

Spring AI dùng `JsonSchemaGenerator` để sinh schema cho method-based tool và function-based tool. Với cách khai báo `@Tool`, thông thường không cần tự viết JSON Schema. Framework suy ra schema từ chữ ký method, sau đó đọc các annotation được hỗ trợ để bổ sung mô tả và trạng thái required.

## Tùy chỉnh bằng @ToolParam của Spring AI

`@ToolParam` là lựa chọn trực tiếp và rõ ràng nhất khi đang viết tool bằng Spring AI. Annotation có hai thuộc tính quan trọng:

- `description`: giải thích tham số, định dạng, đơn vị, miền giá trị hoặc cách diễn giải.
- `required`: xác định tham số bắt buộc hay tùy chọn. Mặc định là `true`.

Ví dụ:

~~~java
@Component
public class ProductTools {

    private final ProductSearchService productSearchService;

    public ProductTools(ProductSearchService productSearchService) {
        this.productSearchService = productSearchService;
    }

    @Tool(description = "Tìm sản phẩm theo từ khóa và bộ lọc. Dùng khi người dùng muốn tra cứu danh sách sản phẩm.")
    public List<ProductSummary> searchProducts(
            @ToolParam(description = "Từ khóa tên hoặc mã sản phẩm cần tìm") String keyword,
            @ToolParam(description = "Màu sản phẩm, ví dụ black, white hoặc silver", required = false)
            String color,
            @ToolParam(description = "Giá tối đa, tính bằng VND", required = false)
            BigDecimal maxPrice,
            @ToolParam(description = "Số kết quả cần trả về, từ 1 đến 20", required = false)
            Integer limit) {

        return productSearchService.search(keyword, color, maxPrice, limit);
    }
}
~~~

Trong ví dụ này:

- `keyword` mặc định bắt buộc; annotation làm rõ ý nghĩa trường.
- `color`, `maxPrice` và `limit` là tùy chọn.
- Mô tả `maxPrice` ghi rõ đơn vị VND để model không nhầm giữa đồng, nghìn đồng hoặc USD.
- Mô tả `limit` ghi miền giá trị mong muốn. Ứng dụng vẫn phải kiểm tra giới hạn đó khi thực thi.

Schema được sinh có hình dạng tương tự:

~~~json
{
  "type": "object",
  "properties": {
    "keyword": {
      "type": "string",
      "description": "Từ khóa tên hoặc mã sản phẩm cần tìm"
    },
    "color": {
      "type": "string",
      "description": "Màu sản phẩm, ví dụ black, white hoặc silver"
    },
    "maxPrice": {
      "type": "number",
      "description": "Giá tối đa, tính bằng VND"
    },
    "limit": {
      "type": "integer",
      "description": "Số kết quả cần trả về, từ 1 đến 20"
    }
  },
  "required": ["keyword"]
}
~~~

Đây là minh họa cấu trúc schema, không phải bản dump được lấy từ một lần chạy cụ thể. Tên property và kiểu JSON thực tế phụ thuộc vào chữ ký Java, cấu hình sinh schema và phiên bản Spring AI.

### Khi nào dùng @ToolParam?

Dùng `@ToolParam` khi muốn annotation gần với method tool và muốn thể hiện rõ ý định dành cho tool calling. Nó đặc biệt hữu ích khi tham số cần mô tả chuyên biệt cho model, khác với cách mô tả trường đó trong API hoặc tài liệu dữ liệu thông thường.

Một mô tả tốt nên trả lời được các câu hỏi:

- Model cần truyền giá trị gì?
- Giá trị dùng định dạng nào?
- Đơn vị là gì?
- Có những giá trị hợp lệ nào?
- Nếu không biết giá trị thì có thể bỏ qua không?

Ví dụ, “Ngày bắt đầu” quá chung chung. “Ngày bắt đầu theo ISO-8601, dạng yyyy-MM-dd, tính theo múi giờ của tài khoản” giúp model tạo đầu vào rõ hơn.

## Tùy chỉnh bằng annotation Jackson

Spring AI hỗ trợ các annotation mô tả của Jackson khi sinh schema:

- `@JsonClassDescription`: mô tả một kiểu dữ liệu, thường dùng cho DTO hoặc nested object.
- `@JsonPropertyDescription`: mô tả một thuộc tính hoặc tham số.
- `@JsonProperty(required = false)`: đánh dấu thuộc tính là không bắt buộc trong schema được sinh.

Ví dụ DTO dùng làm điều kiện tìm kiếm:

~~~java
import com.fasterxml.jackson.annotation.JsonClassDescription;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonPropertyDescription;

@JsonClassDescription("Bộ lọc dùng để tìm sản phẩm trong danh mục")
public record ProductFilter(

        @JsonPropertyDescription("Từ khóa tên, mã SKU hoặc một phần mô tả sản phẩm")
        String keyword,

        @JsonPropertyDescription("Thương hiệu cần lọc, ví dụ Acme hoặc Contoso")
        @JsonProperty(required = false)
        String brand,

        @JsonPropertyDescription("Mã danh mục sản phẩm")
        @JsonProperty(required = false)
        String categoryId
) {
}
~~~

Có thể dùng kiểu dữ liệu này làm tham số của tool:

~~~java
@Tool(description = "Tìm sản phẩm theo bộ lọc được cung cấp")
public List<ProductSummary> searchProducts(ProductFilter filter) {
    return productSearchService.search(filter);
}
~~~

Spring AI có thể áp dụng việc đọc mô tả cho các kiểu lồng nhau theo cách đệ quy. Vì vậy, mô tả ở cấp lớp và cấp thuộc tính giúp model hiểu đối tượng phức hợp mà không phải dồn toàn bộ hướng dẫn vào mô tả của method.

`@JsonProperty(required = false)` có ý nghĩa đối với schema đầu vào được Spring AI tạo ra. Không nên suy luận rằng mọi cấu hình Jackson hoặc mọi annotation của Jackson đều được chuyển thành ràng buộc JSON Schema. Chỉ sử dụng những annotation mà Spring AI tài liệu hóa cho mục đích sinh schema.

### Phân biệt các annotation Jackson

| Annotation | Vị trí thường dùng | Mục đích trong schema |
|---|---|---|
| `@JsonClassDescription` | Class hoặc record | Mô tả ý nghĩa của object |
| `@JsonPropertyDescription` | Field, getter hoặc tham số | Mô tả một property |
| `@JsonProperty(required = false)` | Property hoặc tham số phù hợp | Đánh dấu property không bắt buộc |

Jackson được dùng rộng rãi trong Spring Boot nên các annotation này thường đã có trong dependency của ứng dụng. Nếu dự án tối giản không có `jackson-annotations`, cần bổ sung dependency tương ứng theo dependency management của dự án.

## Tùy chỉnh bằng annotation Swagger @Schema

Nếu dự án đã sử dụng Swagger/OpenAPI, có thể tận dụng `@Schema` từ package `io.swagger.v3.oas.annotations.media` để mô tả tham số và xác định trạng thái required.

Ví dụ:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Tool(description = "Tìm đơn hàng theo trạng thái và khoảng thời gian")
public List<OrderSummary> searchOrders(
        @Schema(
                description = "Trạng thái đơn hàng: PENDING, PROCESSING, SHIPPED hoặc DELIVERED",
                required = true
        )
        OrderStatus status,

        @Schema(
                description = "Ngày bắt đầu theo ISO-8601, dạng yyyy-MM-dd",
                required = false
        )
        LocalDate startDate,

        @Schema(
                description = "Ngày kết thúc theo ISO-8601, dạng yyyy-MM-dd",
                required = false
        )
        LocalDate endDate) {

    return orderQueryService.search(status, startDate, endDate);
}
~~~

Ở đây, `status` là bắt buộc, còn hai mốc thời gian có thể được bỏ qua. Mô tả cũng cho biết các giá trị trạng thái hợp lệ và định dạng ngày mong đợi.

Để biên dịch mã có `@Schema`, dự án cần có artifact `swagger-annotations` tương thích với bộ dependency đang sử dụng. Nếu ứng dụng đã dùng springdoc hoặc OpenAPI starter, annotation này có thể đã được kéo vào gián tiếp; hãy kiểm tra dependency tree thay vì thêm một phiên bản trùng lặp.

### Không phải mọi thuộc tính OpenAPI đều trở thành ràng buộc tool schema

`@Schema` là annotation có nhiều thuộc tính phục vụ tài liệu OpenAPI. Tuy nhiên, Spring AI chỉ đọc các metadata mà bộ sinh JSON Schema hỗ trợ. Tài liệu Spring AI nêu rõ việc lấy mô tả và required/optional từ `@Schema`; không nên giả định rằng các thuộc tính như `example`, `implementation`, `accessMode`, `deprecated` hoặc toàn bộ validation metadata của OpenAPI sẽ tự động xuất hiện trong schema gửi tới model.

Nếu model cần biết miền giá trị, hãy ghi miền đó trong description hoặc dùng kiểu dữ liệu có tập giá trị hữu hạn như enum khi phù hợp. Nếu cần cấu trúc JSON Schema phức tạp hơn những metadata annotation hỗ trợ, hãy xem xét tạo `ToolDefinition` tùy chỉnh với `inputSchema` tường minh.

## Thứ tự ưu tiên khi xác định required và optional

Mặc định, các tham số đầu vào được coi là bắt buộc. Spring AI hỗ trợ đánh dấu tham số tùy chọn qua các annotation sau, theo thứ tự ưu tiên từ cao xuống thấp:

1. `@ToolParam(required = false)` — annotation của Spring AI.
2. `@JsonProperty(required = false)` — annotation của Jackson.
3. `@Schema(required = false)` — annotation của Swagger.
4. `@Nullable` — annotation nullability của Spring Framework.

Nếu nhiều annotation xung đột, khai báo có mức ưu tiên cao hơn quyết định trạng thái required/optional theo cơ chế sinh schema. Ví dụ, `@ToolParam(required = true)` thể hiện rõ rằng tham số vẫn bắt buộc dù có annotation nullability ở vị trí khác.

Ví dụ:

~~~java
@Tool(description = "Tra cứu thông tin khách hàng")
public CustomerSummary getCustomer(
        @ToolParam(description = "Mã khách hàng", required = true)
        String customerId,

        @JsonProperty(required = false)
        @JsonPropertyDescription("Địa chỉ email nếu người gọi biết")
        String email,

        @Schema(description = "Mã phân khúc bổ sung", required = false)
        String segment) {

    return customerService.find(customerId, email, segment);
}
~~~

Không nên gắn nhiều annotation cùng khai báo một metadata nếu không cần thiết. Nếu một tham số vừa mang `@ToolParam`, vừa mang `@JsonProperty`, vừa mang `@Schema`, người bảo trì sẽ khó biết annotation nào đang quyết định schema. Hãy chọn một nguồn mô tả chính và chỉ phối hợp annotation khi có lý do rõ ràng.

### Required không đồng nghĩa với dữ liệu hợp lệ

Nếu tham số được đánh dấu required, model phải cung cấp giá trị cho trường đó khi gọi tool. Nếu đánh dấu optional, model được phép bỏ trường đó. Trạng thái này không chứng minh giá trị có hợp lệ về nghiệp vụ hay không.

Ví dụ:

- `limit` có thể optional nhưng nếu được truyền thì chỉ được nằm trong khoảng 1 đến 20.
- `startDate` và `endDate` có thể optional nhưng nếu cùng có mặt thì ngày bắt đầu phải trước hoặc bằng ngày kết thúc.
- `email` có thể optional nhưng nếu được truyền thì phải đúng định dạng mà ứng dụng chấp nhận.
- `status` có thể required nhưng vẫn phải nằm trong tập trạng thái mà nghiệp vụ cho phép.

Model có thể tạo một chuỗi đúng kiểu JSON nhưng sai định dạng, sai phạm vi hoặc không có quyền sử dụng. Callback hoặc dịch vụ nghiệp vụ phải kiểm tra các điều kiện này trước khi thực hiện truy vấn hay thay đổi dữ liệu.

## Optional, null và trường bị bỏ qua

Ba trạng thái thường bị nhầm lẫn:

- **Required:** model phải gửi trường.
- **Optional:** model có thể bỏ trường.
- **Nullable:** trường có thể nhận giá trị null theo hợp đồng dữ liệu.

Đánh dấu optional không nhất thiết có nghĩa là model phải gửi `null` khi không biết giá trị. Thông thường, nó có thể bỏ hẳn property khỏi JSON. Code ứng dụng cần xử lý trường hợp tham số không có giá trị.

Với tham số optional, nên dùng kiểu boxed như `Integer`, `Long`, `Boolean` thay cho primitive `int`, `long`, `boolean` nếu cần phân biệt giá trị bị thiếu với giá trị mặc định. Ví dụ `Integer limit` có thể là `null` khi không được cung cấp; `int limit` không thể biểu diễn trạng thái null.

Ví dụ xử lý optional:

~~~java
private int normalizeLimit(Integer requestedLimit) {
    if (requestedLimit == null) {
        return 10;
    }

    if (requestedLimit < 1 || requestedLimit > 20) {
        throw new IllegalArgumentException("limit phải nằm trong khoảng 1 đến 20");
    }

    return requestedLimit;
}
~~~

Giá trị mặc định trong ứng dụng là quy tắc nghiệp vụ do nhà phát triển quyết định. Không nên đánh dấu một trường optional rồi ngầm cho model quyền lựa chọn một mặc định không an toàn.

## Kết hợp annotation trên tham số và DTO lồng nhau

Khi tool có nhiều bộ lọc, thay vì tạo method với hàng loạt tham số rời rạc, có thể gom chúng vào một record hoặc POJO. Spring AI hỗ trợ sinh schema cho các kiểu dữ liệu thông dụng và đọc annotation mô tả đệ quy cho nested type.

Ví dụ:

~~~java
@JsonClassDescription("Điều kiện lọc sản phẩm")
public record ProductSearchCriteria(

        @ToolParam(description = "Từ khóa tên hoặc mã sản phẩm")
        String keyword,

        @JsonPropertyDescription("Mã thương hiệu cần lọc")
        @JsonProperty(required = false)
        String brandId,

        @Schema(
                description = "Giá tối đa tính bằng VND",
                required = false
        )
        BigDecimal maxPrice,

        @Schema(
                description = "Số kết quả tối đa, từ 1 đến 20",
                required = false
        )
        Integer limit
) {
}
~~~

Method tool nhận object:

~~~java
@Tool(description = "Tìm sản phẩm theo điều kiện lọc")
public List<ProductSummary> search(
        @ToolParam(description = "Các điều kiện tìm kiếm sản phẩm")
        ProductSearchCriteria criteria) {

    return productSearchService.search(criteria);
}
~~~

Mô hình cần tạo object JSON có các trường tương ứng. Mô tả ở cấp class giải thích ý nghĩa tổng thể của bộ lọc; mô tả từng property giải thích cách cung cấp giá trị. Trạng thái required của các thuộc tính được xác định theo annotation trên từng property.

Không gom object chỉ để giảm số tham số nếu nó làm schema khó hiểu. Cấu trúc nested nên phản ánh nhóm dữ liệu có ý nghĩa với nghiệp vụ. Tên property nên ổn định và mô tả đúng dữ liệu mà service cần.

## Chọn annotation nào?

| Tình huống | Annotation nên ưu tiên | Lý do |
|---|---|---|
| Chỉ cần metadata cho tool calling | `@ToolParam` | Rõ ràng, thuộc Spring AI và có ưu tiên cao |
| DTO đã dùng Jackson | `@JsonClassDescription`, `@JsonPropertyDescription`, `@JsonProperty` | Tái sử dụng mô tả trên kiểu và property |
| Dự án đã chuẩn hóa OpenAPI | `@Schema` | Dùng cùng metadata mô tả API và tool ở phạm vi được Spring AI hỗ trợ |
| Cần schema vượt quá mô tả/required | `ToolDefinition.inputSchema` | Kiểm soát JSON Schema trực tiếp |

Một quy tắc thực tế là chọn annotation theo nguồn sở hữu metadata. Nếu schema chỉ phục vụ tool, dùng `@ToolParam`. Nếu kiểu dữ liệu dùng chung trong nhiều lớp và đã được mô tả bằng Jackson, có thể đặt metadata trên DTO. Nếu dự án quản lý API bằng OpenAPI, có thể dùng `@Schema` cho những trường cần chia sẻ mô tả.

Không cần lặp lại cùng một mô tả ở ba annotation. Khi nhiều hệ thống cùng đọc một DTO, hãy xác định metadata nào là mô tả chung của dữ liệu và metadata nào là hướng dẫn riêng cho model.

## Khi annotation không đủ: khai báo inputSchema tường minh

Annotation phù hợp với phần lớn method-based tool. Nếu cần một JSON Schema cụ thể mà các annotation hiện có không biểu đạt được, có thể tạo `ToolDefinition` và cung cấp `inputSchema` trực tiếp.

~~~java
ToolDefinition definition = ToolDefinition.builder()
        .name("searchProducts")
        .description("Tìm sản phẩm theo điều kiện đã cung cấp")
        .inputSchema("""
                {
                  "type": "object",
                  "properties": {
                    "keyword": {
                      "type": "string",
                      "description": "Từ khóa tên hoặc mã sản phẩm"
                    },
                    "limit": {
                      "type": "integer",
                      "minimum": 1,
                      "maximum": 20
                    }
                  },
                  "required": ["keyword"],
                  "additionalProperties": false
                }
                """)
        .build();
~~~

Đây là định nghĩa schema minh họa. Khi dùng callback tùy chỉnh, cần bảo đảm schema và logic thực thi khớp nhau: tên trường, kiểu dữ liệu, required status và các ràng buộc đều phải được kiểm tra ở ứng dụng. Việc khai báo `minimum`, `maximum` hoặc `additionalProperties` trong schema không thay thế validation ở phía server.

Dùng schema tường minh khi thật sự cần kiểm soát cấu trúc JSON. Với tool method thông thường, annotation giúp schema gắn liền với chữ ký Java và giảm nguy cơ khai báo lệch giữa method và JSON.

## Kiểm tra schema thực tế

Đừng chỉ đọc annotation rồi giả định schema được sinh đúng. Hãy kiểm tra `ToolDefinition.inputSchema()` của callback mà ứng dụng thực sự đăng ký.

Một quy trình kiểm tra:

1. Tạo callback từ tool object bằng cơ chế Spring AI đang dùng.
2. Lấy `ToolDefinition` từ callback.
3. Đọc `inputSchema()` và parse JSON.
4. Kiểm tra `properties`, `description`, kiểu dữ liệu và mảng `required`.
5. So sánh schema với hợp đồng mà service mong đợi.

Ví dụ khung kiểm tra:

~~~java
ToolCallback[] callbacks = ToolCallbacks.from(productTools);

ToolDefinition definition = callbacks[0].getToolDefinition();
String schemaJson = definition.inputSchema();

// Parse schemaJson bằng Jackson JsonNode trong test.
// Kiểm tra properties.keyword, properties.limit và required.
~~~

Tên và thứ tự callback trong mảng không nên được dùng như một định danh cố định nếu tool set có thể thay đổi. Trong test thực tế, hãy tìm callback theo `ToolDefinition.name()`, sau đó kiểm tra schema của tool đó.

Nếu có thay đổi annotation, hãy so sánh schema trước và sau thay đổi như một thay đổi hợp đồng. Một trường chuyển từ required sang optional có thể làm thay đổi hành vi model và cách callback xử lý đầu vào.

## Validation vẫn thuộc về ứng dụng

JSON Schema giúp model tạo đầu vào theo cấu trúc mong muốn. Nó không bảo đảm:

- chuỗi ngày tháng tồn tại trong lịch;
- mã khách hàng thuộc về người dùng hiện tại;
- giá trị nằm trong giới hạn nghiệp vụ;
- người dùng có quyền truy cập dữ liệu;
- trạng thái đơn hàng cho phép thao tác;
- dữ liệu không chứa nội dung độc hại hoặc vượt giới hạn hệ thống.

Ví dụ, dù mô tả `limit` ghi “từ 1 đến 20”, service vẫn phải kiểm tra:

~~~java
public List<ProductSummary> search(
        String keyword,
        Integer limit) {

    if (keyword == null || keyword.isBlank()) {
        throw new IllegalArgumentException("keyword không được để trống");
    }

    int safeLimit = limit == null ? 10 : limit;

    if (safeLimit < 1 || safeLimit > 20) {
        throw new IllegalArgumentException("limit phải từ 1 đến 20");
    }

    return productRepository.search(keyword, safeLimit);
}
~~~

Với dữ liệu nhạy cảm, không đưa user ID, tenant ID hoặc quyền truy cập thành tham số mà model tự tạo. Lấy danh tính từ principal đã xác thực hoặc `ToolContext` do ứng dụng thiết lập, rồi kiểm tra quyền trong dịch vụ nghiệp vụ.

## Những lỗi thường gặp khi tùy chỉnh schema

- **Mô tả quá chung chung:** model không biết định dạng, đơn vị hoặc miền giá trị. Viết mô tả cụ thể và có ví dụ hợp lệ.
- **Đánh dấu mọi trường là required:** model có thể tự tạo dữ liệu cho trường mà người dùng chưa cung cấp. Chỉ đánh dấu required khi thật sự cần.
- **Đánh dấu trường bắt buộc thành optional:** callback có thể nhận null hoặc thiếu dữ liệu rồi thất bại. Kiểm tra lại hợp đồng service.
- **Dùng annotation OpenAPI với kỳ vọng mọi thuộc tính đều vào tool schema:** Spring AI chỉ đọc metadata được hỗ trợ. Kiểm tra JSON Schema thực tế.
- **Khai báo nhiều annotation xung đột:** người bảo trì khó biết giá trị nào có hiệu lực. Chọn một annotation chính và kiểm tra thứ tự ưu tiên.
- **Nhầm optional với null:** model có thể bỏ property thay vì gửi null. Xử lý cả trường hợp vắng mặt.
- **Tin schema thay cho validation:** schema không cấp quyền và không thực thi quy tắc nghiệp vụ. Validate ở backend.
- **Không kiểm tra schema sau khi đổi DTO:** thay đổi field hoặc annotation có thể làm thay đổi hợp đồng tool mà không có lỗi biên dịch.

## Checklist thiết kế schema đầu vào

- [ ] Tên tool và mô tả tool nói rõ hành động, phạm vi và điều kiện sử dụng.
- [ ] Mỗi tham số có tên rõ nghĩa và mô tả đủ định dạng, đơn vị hoặc miền giá trị.
- [ ] Chỉ trường thật sự cần thiết mới được đánh dấu required.
- [ ] Trường optional dùng kiểu Java có thể biểu diễn việc không có giá trị.
- [ ] Annotation được chọn theo metadata sở hữu: Spring AI, Jackson hoặc Swagger.
- [ ] Không có annotation xung đột hoặc lặp mô tả không cần thiết.
- [ ] DTO lồng nhau có mô tả cấp object và cấp property.
- [ ] Schema được sinh thực tế đã được kiểm tra trong test.
- [ ] Backend vẫn validate đầu vào và phân quyền trước khi gọi service.
- [ ] Không đưa bí mật hoặc dữ liệu quyền truy cập vào tham số do model tạo.

## Ghi nhớ khi thiết kế

Spring AI tự sinh JSON Schema từ chữ ký method hoặc function. `@ToolParam` là cách trực tiếp để mô tả tham số và đặt trạng thái required/optional; Jackson cung cấp annotation mô tả class/property và required; Swagger cung cấp `@Schema` cho mô tả và trạng thái optional trong phạm vi Spring AI hỗ trợ.

Mặc định tham số là bắt buộc. Khi cần đánh dấu optional, thứ tự ưu tiên là `@ToolParam(required = false)`, `@JsonProperty(required = false)`, `@Schema(required = false)`, rồi đến `@Nullable`. Hãy kiểm tra schema thực tế, xử lý giá trị bị thiếu và luôn xác thực đầu vào ở phía ứng dụng trước khi thực thi nghiệp vụ.

## Tài liệu tham khảo

- [Spring AI 1.0 Reference — Tool Calling và JSON Schema](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html)
- [Spring AI Reference — Tool Calling và JSON Schema](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Jackson Annotations](https://github.com/FasterXML/jackson-annotations)
- [Swagger Core — @Schema](https://docs.swagger.io/swagger-core/v2.2.30/apidocs/io/swagger/v3/oas/annotations/media/Schema.html)

