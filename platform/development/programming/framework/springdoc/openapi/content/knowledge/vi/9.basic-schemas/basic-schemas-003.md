# Tên schema, mô tả, kiểu và format

Schema là phần của OpenAPI mô tả hình dạng dữ liệu mà API nhận hoặc trả về. Một schema cho biết dữ liệu là object, string, number hay array; mỗi thuộc tính có kiểu gì; và một số định dạng quen thuộc như UUID, ngày hoặc thời điểm. Schema cũng có tên và mô tả để người đọc hiểu thành phần đó đại diện cho dữ liệu nào.

Với springdoc-openapi, phần lớn schema được suy ra từ kiểu Java, generic, annotation Jackson và Bean Validation. Annotation của swagger-core như @Schema cho phép bổ sung hoặc điều chỉnh metadata để tài liệu sinh ra rõ ràng hơn. Cần phân biệt metadata OpenAPI với hành vi runtime: tên, mô tả, type và format giúp công bố hợp đồng; chúng không tự thay đổi cách Java serialize, deserialize hoặc kiểm tra dữ liệu.

## 1. Schema Object và vị trí của nó trong OpenAPI

Schema Object mô tả một giá trị dữ liệu. Nó có thể nằm trực tiếp trong request body hoặc response, hoặc được đặt tên trong components để nhiều operation cùng tham chiếu.

Ví dụ schema inline:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        properties:
          name:
            type: string
          quantity:
            type: integer
~~~

Khi một kiểu dữ liệu được dùng ở nhiều nơi, nên đặt schema trong components.schemas rồi tham chiếu bằng $ref:

~~~yaml
components:
  schemas:
    ProductInput:
      type: object
      properties:
        name:
          type: string
        quantity:
          type: integer
~~~

Một response có thể sử dụng lại schema:

~~~yaml
responses:
  '200':
    description: Thông tin sản phẩm
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ProductInput'
~~~

Tên schema là định danh của thành phần trong tài liệu. Mô tả giải thích ý nghĩa của thành phần. Type và format cho biết dữ liệu có cấu trúc và biểu diễn như thế nào.

## 2. Phân biệt name, title và description

Ba khái niệm này có mục đích khác nhau:

| Thuộc tính | Mục đích | Ví dụ |
| --- | --- | --- |
| name | Tên schema hoặc tên thành phần được sinh trong OpenAPI khi đặt trên model | ProductView |
| title | Tiêu đề dễ đọc của Schema Object | Product response |
| description | Giải thích ý nghĩa, quy ước và cách sử dụng | Dữ liệu công khai của một sản phẩm trong catalog |

Trong Java, có thể khai báo tên và mô tả cho DTO:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.UUID;

@Schema(
    name = "ProductView",
    title = "Product response",
    description = "Thông tin sản phẩm được công bố bởi Catalog API."
)
public record ProductView(
    UUID id,
    String name,
    BigDecimal price,
    LocalDateTime createdAt
) {}
~~~

Trong ví dụ này, name đặt tên schema là ProductView; title là nhãn dễ đọc; description giải thích nội dung của object. Springdoc có thể tham chiếu thành phần đó từ request hoặc response bằng $ref.

Nếu không khai báo name, springdoc thường suy ra tên schema từ kiểu Java. Việc đặt tên tường minh hữu ích khi tên class nội bộ khó hiểu, khi muốn tên hợp đồng ổn định hoặc khi có nhiều class cùng tên ở các package khác nhau. Hãy chọn tên duy nhất và có ý nghĩa theo miền API.

Không nhầm tên schema với tên property JSON. Ví dụ, nếu muốn đổi property Java code thành product_code trong JSON, dùng annotation Jackson như @JsonProperty:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

public record ProductIdentifier(
    @JsonProperty("product_code")
    @Schema(description = "Mã sản phẩm công khai", example = "KB-01")
    String code
) {}
~~~

Tên property trong hợp đồng phải khớp với JSON thực tế được Jackson serialize. @Schema(name = "...") trên class dùng cho tên schema; @JsonProperty trên field hoặc record component điều khiển tên thuộc tính JSON.

## 3. Viết description hữu ích

Description giải thích điều mà tên và kiểu dữ liệu không thể hiện được. Một mô tả tốt cho biết dữ liệu đại diện cho điều gì, quy ước nào cần tuân thủ và giới hạn quan trọng nào người tích hợp phải biết.

Ví dụ:

~~~java
@Schema(
    description = "Giá bán theo đơn vị tiền tệ của cửa hàng. Giá trị không bao gồm phí vận chuyển.",
    example = "199000.00"
)
BigDecimal price
~~~

So sánh:

| Mô tả yếu | Mô tả rõ hơn |
| --- | --- |
| Giá sản phẩm | Giá bán theo đơn vị tiền tệ của cửa hàng, chưa gồm phí vận chuyển |
| Ngày tạo | Thời điểm sản phẩm được tạo lần đầu, biểu diễn theo ISO 8601 |
| Trạng thái | Trạng thái công khai của sản phẩm; giá trị có thể là ACTIVE, INACTIVE hoặc OUT_OF_STOCK |

Description trong OpenAPI có thể chứa CommonMark/Markdown. Có thể dùng danh sách hoặc liên kết ngắn nếu chúng giúp người đọc hiểu hợp đồng. Tránh đưa toàn bộ hướng dẫn nghiệp vụ dài vào một field; dùng externalDocs để liên kết tới tài liệu bổ sung khi cần.

Không đưa thông tin nhạy cảm, dữ liệu nội bộ hoặc ví dụ chứa thông tin khách hàng thật vào mô tả. Các tài liệu OpenAPI thường được chia sẻ cho nhiều nhóm client và môi trường.

## 4. Type mô tả kiểu dữ liệu cơ bản

Trường type cho biết loại giá trị mà schema chấp nhận. Các kiểu thường gặp:

| OpenAPI type | Ý nghĩa | Ví dụ JSON |
| --- | --- | --- |
| string | Chuỗi ký tự | "keyboard" |
| integer | Số nguyên | 42 |
| number | Số có thể có phần thập phân | 199000.50 |
| boolean | Giá trị đúng hoặc sai | true |
| object | Đối tượng có các thuộc tính | {"name":"Keyboard"} |
| array | Danh sách các giá trị | ["red","blue"] |

Springdoc thường suy ra type từ kiểu Java:

| Kiểu Java | Schema thường được suy ra |
| --- | --- |
| String, Character | string |
| Integer, int, Short | integer |
| Long, long | integer, thường kèm format int64 |
| Float, float | number, thường kèm format float |
| Double, double | number, thường kèm format double |
| BigDecimal | number |
| Boolean, boolean | boolean |
| DTO hoặc record | object |
| List<T>, Set<T>, T[] | array với items theo kiểu T |
| Map<String, T> | object với additionalProperties theo kiểu T |

Đây là quy tắc suy luận phổ biến; kiểu cụ thể được công bố có thể phụ thuộc phiên bản thư viện, cấu hình và annotation. Hãy kiểm tra tài liệu JSON/YAML thực tế khi hợp đồng cần chính xác.

Ví dụ DTO:

~~~java
public record InventoryView(
    String sku,
    int quantity,
    boolean available,
    List<String> labels
) {}
~~~

Schema có thể được sinh tương ứng:

~~~yaml
type: object
properties:
  sku:
    type: string
  quantity:
    type: integer
  available:
    type: boolean
  labels:
    type: array
    items:
      type: string
~~~

Thông thường không cần ghi type thủ công nếu kiểu Java đã thể hiện chính xác cấu trúc. Chỉ ghi đè khi cần công bố hợp đồng đặc biệt và đã xác minh serialization thực tế tương thích.

## 5. Format bổ sung ý nghĩa cho type

Format tinh chỉnh cách diễn giải một giá trị, thường được dùng cùng type. Ví dụ, UUID vẫn là string nhưng có định dạng UUID; ngày vẫn là string nhưng có quy ước ngày ISO.

| type | format phổ biến | Ý nghĩa |
| --- | --- | --- |
| string | uuid | Chuỗi định danh UUID |
| string | date | Ngày theo định dạng full-date, ví dụ 2026-11-20 |
| string | date-time | Thời điểm theo định dạng date-time |
| string | byte | Dữ liệu nhị phân được biểu diễn bằng base64 trong một số ngữ cảnh |
| string | binary | Nội dung nhị phân, thường dùng cho file |
| string | password | Chuỗi mật khẩu; công cụ có thể hiển thị dưới dạng che ký tự |
| integer | int32 | Số nguyên 32 bit |
| integer | int64 | Số nguyên 64 bit |
| number | float | Số thực độ chính xác đơn |
| number | double | Số thực độ chính xác kép |

Ví dụ dùng annotation @Schema:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.UUID;

public record SubscriptionView(
    @Schema(
        description = "Mã định danh subscription",
        type = "string",
        format = "uuid",
        example = "7d9c2d0e-8f9d-4a2a-a2c3-0f65b7d2c111"
    )
    UUID id,

    @Schema(
        description = "Ngày bắt đầu hiệu lực",
        type = "string",
        format = "date",
        example = "2026-11-20"
    )
    LocalDate startsOn,

    @Schema(
        description = "Thời điểm cập nhật gần nhất",
        type = "string",
        format = "date-time",
        example = "2026-11-20T10:30:00+07:00"
    )
    OffsetDateTime updatedAt
) {}
~~~

Springdoc thường tự suy ra format phù hợp từ kiểu Java như UUID, LocalDate hoặc OffsetDateTime. Khai báo tường minh có ích khi muốn tài liệu dễ đọc hoặc khi kiểu Java không đủ thể hiện quy ước công khai.

## 6. Format không thay thế type hoặc validation

Type xác định nhóm dữ liệu; format bổ sung quy ước biểu diễn. Format không tự thay đổi kiểu Java, converter hoặc logic kiểm tra ở runtime.

Ví dụ:

- type: string, format: date-time mô tả chuỗi thời điểm.
- type: integer, format: int64 mô tả số nguyên 64 bit.
- type: string, format: uuid mô tả chuỗi có hình dạng UUID.

Nếu controller nhận một String, đặt format: date-time chỉ làm tài liệu nói rằng chuỗi đó phải tuân theo quy ước thời điểm. Spring không tự chuyển String thành thời gian chỉ vì schema có format. Muốn parse thành kiểu thời gian, hãy dùng kiểu Java phù hợp hoặc converter/formatter.

Tương tự, format: email không thay thế kiểm tra địa chỉ email; format: uuid không thay thế validation tại server nếu dữ liệu được nhận dưới dạng String. Các công cụ OpenAPI cũng có thể hỗ trợ format khác nhau: một số validator kiểm tra định dạng, một số chỉ coi format là gợi ý.

Khi cần ràng buộc dữ liệu cụ thể, dùng keyword hoặc Bean Validation phù hợp:

| Yêu cầu | Ràng buộc thường dùng |
| --- | --- |
| Chuỗi không rỗng | @NotBlank |
| Chuỗi có độ dài giới hạn | @Size |
| Chuỗi khớp mẫu | @Pattern |
| Số lớn hơn hoặc bằng một giá trị | @Min, @DecimalMin |
| Giá trị phải có mặt | @NotNull |
| Tập giá trị hữu hạn | enum hoặc allowableValues |

Ví dụ:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Size(max = 80)
    @Schema(description = "Tên sản phẩm", example = "Mechanical Keyboard")
    String name,

    @NotNull
    @DecimalMin("0.01")
    @Schema(description = "Giá bán phải lớn hơn 0", example = "199000.00")
    BigDecimal price
) {}
~~~

Với Spring Boot 3 trở lên, các annotation validation thuộc package jakarta.validation. Dự án cần có validation provider và kích hoạt validation tại điểm nhận request, chẳng hạn dùng @Valid trên tham số @RequestBody. Metadata validation có thể được springdoc phản ánh vào schema; việc thực thi vẫn do Bean Validation runtime đảm nhiệm.

## 7. Dùng @Schema trên class và property

Annotation @Schema có thể đặt trên class, record hoặc property để bổ sung metadata.

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

@Schema(
    name = "ProductDetail",
    title = "Product detail",
    description = "Thông tin chi tiết sản phẩm trong catalog."
)
public record ProductDetail(
    @Schema(
        description = "Định danh sản phẩm",
        example = "7d9c2d0e-8f9d-4a2a-a2c3-0f65b7d2c111"
    )
    UUID id,

    @JsonProperty("product_name")
    @Schema(
        description = "Tên hiển thị của sản phẩm",
        example = "Mechanical Keyboard"
    )
    String name,

    @Schema(
        description = "Giá bán theo đơn vị tiền tệ của cửa hàng",
        type = "number",
        example = "199000.00"
    )
    BigDecimal price,

    @Schema(
        description = "Thời điểm tạo sản phẩm",
        format = "date-time",
        example = "2026-11-20T10:30:00+07:00"
    )
    OffsetDateTime createdAt,

    @Schema(description = "Các nhãn dùng để tìm kiếm và phân loại")
    List<String> tags
) {}
~~~

Trong ví dụ:

- Metadata trên record mô tả schema ProductDetail.
- Metadata trên từng component mô tả property tương ứng.
- @JsonProperty đổi tên field JSON thành product_name.
- UUID, BigDecimal, OffsetDateTime và List<String> giúp springdoc suy ra type phù hợp; annotation bổ sung description và example.

Không nên đặt type tùy ý nếu nó mâu thuẫn với kiểu Java hoặc dữ liệu Jackson thực sự phát ra. Ví dụ, khai báo type: integer cho một property được serialize thành chuỗi sẽ khiến client sinh mã và validator hiểu sai hợp đồng.

## 8. Tham chiếu schema trong request và response

Khi model đã có tên, springdoc có thể tái sử dụng nó trong các operation. Ví dụ controller trả về ProductDetail:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping("/{id}")
    ProductDetail getProduct(@PathVariable UUID id) {
        return productService.getDetail(id);
    }
}
~~~

Đặc tả OpenAPI có thể tham chiếu schema:

~~~yaml
paths:
  /api/products/{id}:
    get:
      responses:
        '200':
          description: Chi tiết sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductDetail'
components:
  schemas:
    ProductDetail:
      title: Product detail
      description: Thông tin chi tiết sản phẩm trong catalog.
      type: object
      properties:
        id:
          type: string
          format: uuid
        product_name:
          type: string
        price:
          type: number
        createdAt:
          type: string
          format: date-time
        tags:
          type: array
          items:
            type: string
~~~

Đoạn YAML là hình minh họa cấu trúc. Đặc tả thực tế có thể thêm required, example, constraint hoặc tên property khác tùy annotation, Jackson và cấu hình dự án.

Nếu muốn kiểm soát schema response tường minh, có thể dùng @ApiResponse và @Content:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Chi tiết sản phẩm",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ProductDetail.class)
    )
)
~~~

Annotation này mô tả response trong OpenAPI. Nó không thay đổi object mà controller trả về.

## 9. Khi nào nên dùng type và format tường minh?

Hãy để springdoc suy luận từ Java khi kiểu Java đã phản ánh đúng hợp đồng. Chỉ ghi đè type hoặc format khi có lý do rõ ràng:

| Tình huống | Cách làm |
| --- | --- |
| DTO thông thường | Để springdoc suy luận object và properties |
| UUID, LocalDate, OffsetDateTime | Dùng kiểu Java chuẩn; kiểm tra format sinh ra |
| Kiểu tùy chỉnh được serialize thành chuỗi | Dùng @Schema(type = "string") và format phù hợp với biểu diễn JSON |
| File upload hoặc dữ liệu binary | Mô tả string/binary và media type tương ứng |
| Số nguyên cần công bố độ rộng | Dùng kiểu Java phù hợp hoặc format int32/int64 |
| Model có tên nội bộ khó hiểu | Đặt @Schema(name = "...") và description rõ ràng |

Nếu cần một định dạng riêng không nằm trong danh sách phổ biến, OpenAPI cho phép format mở rộng. Tuy nhiên, client generator và validator có thể không hiểu format tùy chỉnh. Hãy mô tả ý nghĩa trong description, thống nhất cách biểu diễn và kiểm thử công cụ tiêu thụ tài liệu.

## 10. Khác biệt hỗ trợ giữa OpenAPI 3.0 và 3.1

OpenAPI 3.0 dùng tập type và format theo mô hình Schema Object của OAS 3.0. OpenAPI 3.1 đồng bộ Schema Object gần hơn với JSON Schema 2020-12 và có cách biểu diễn một số cấu trúc phong phú hơn.

Một số điểm cần nhớ:

- Các format phổ biến như date, date-time, uuid, int32 và int64 được nhiều công cụ nhận biết, nhưng mức độ kiểm tra có thể khác nhau.
- Format là thông tin bổ sung cho type; không dùng format để biến một string thành number hoặc object.
- Với OpenAPI 3.1, format có thể được xem là annotation tùy theo vocabulary và validator; đừng giả định mọi công cụ đều thực thi kiểm tra định dạng.
- Cách mô tả giá trị null giữa OpenAPI 3.0 và 3.1 có khác biệt. Không dùng format để mô tả nullable; chọn cấu trúc schema phù hợp với phiên bản OpenAPI đang xuất.

Phiên bản tài liệu thực tế phụ thuộc cấu hình springdoc. Hãy xác nhận trường openapi ở đầu /v3/api-docs trước khi áp dụng các keyword JSON Schema cụ thể.

## 11. Kiểm tra schema được sinh

Sau khi thêm annotation, lấy đặc tả OpenAPI JSON hoặc YAML từ ứng dụng:

~~~bash
curl -sS http://localhost:8080/v3/api-docs
curl -sS http://localhost:8080/v3/api-docs.yaml
~~~

Kiểm tra:

1. Tên component dưới components.schemas có đúng như mong muốn không?
2. title và description có xuất hiện đúng ở cấp schema không?
3. Mỗi property có đúng tên JSON, type và format không?
4. Array có items đúng kiểu không?
5. Schema có được tái sử dụng qua $ref hay bị tạo bản inline không mong muốn?
6. Ví dụ và constraint có khớp dữ liệu runtime không?
7. Swagger UI có hiển thị mô tả và định dạng đủ rõ cho người tích hợp không?

Nếu tên schema không như mong muốn, kiểm tra @Schema(name = "...") trên model và các class có tên trùng. Nếu property sai tên, kiểm tra Jackson annotation và cấu hình naming strategy. Nếu format không xuất hiện, kiểm tra kiểu Java, annotation, phiên bản swagger-core và đặc tả OpenAPI đang dùng.

Đừng chỉ nhìn Swagger UI. JSON/YAML là hợp đồng được công bố; hãy xác minh trực tiếp dữ liệu sinh ra và kiểm tra response/request thực tế để chắc chắn schema khớp serialization.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Schema có tên class Java không mong muốn | Chưa đặt tên công khai hoặc trùng tên model | Dùng @Schema(name = "...") với tên duy nhất |
| Swagger UI chỉ hiển thị tên schema mà thiếu giải thích | Thiếu title hoặc description | Bổ sung metadata ở cấp class |
| UUID được mô tả như string chung | Kiểu hoặc format không được suy luận theo mong đợi | Dùng UUID hoặc @Schema(format = "uuid") |
| Ngày tháng có format không đúng | Dùng kiểu Java hoặc converter không tương ứng | Chọn LocalDate/OffsetDateTime và xác minh serialization |
| Schema nói number nhưng JSON phát ra string | type bị ghi đè không khớp Jackson serializer | Đồng bộ kiểu Java, serializer và annotation |
| Client generator bỏ qua format | Công cụ không hỗ trợ format đó | Dùng format phổ biến, mô tả thêm và kiểm thử generator |
| Property có tên khác tài liệu | Jackson đổi tên qua @JsonProperty hoặc naming strategy | Kiểm tra JSON thực tế và OpenAPI cùng lúc |

## 13. Quy trình thiết kế schema

Khi công bố một DTO thành schema API, thực hiện theo thứ tự:

1. Chọn tên schema ổn định, có ý nghĩa với client; dùng @Schema(name = "...") khi tên mặc định chưa phù hợp.
2. Viết title và description giải thích vai trò của dữ liệu.
3. Dùng kiểu Java phản ánh chính xác JSON được serialize.
4. Chọn type và format phù hợp; không dùng format để thay thế validation hoặc conversion.
5. Mô tả property bằng description, example và constraint cần thiết.
6. Dùng $ref để tái sử dụng model trong request/response khi thích hợp.
7. Kiểm tra JSON/YAML được springdoc sinh ra và đối chiếu với payload runtime.

Một schema tốt giúp người tích hợp hiểu tên thành phần, ý nghĩa dữ liệu và cách biểu diễn từng giá trị. Khi name, description, type và format nhất quán với DTO và JSON thực tế, OpenAPI trở thành hợp đồng đáng tin cậy để đọc tài liệu, kiểm thử và sinh client.

## Tài liệu tham khảo

- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [OpenAPI Specification – Data Types](https://spec.openapis.org/oas/latest.html#data-types)
- [Swagger Core – @Schema Annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/Schema.html)
- [Jackson Annotations – @JsonProperty](https://github.com/FasterXML/jackson-annotations)
- [springdoc-openapi – Documentation](https://springdoc.org/)
