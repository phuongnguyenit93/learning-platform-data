# Schema của tham số số, Boolean, chuỗi, enum và ngày giờ

Khi springdoc-openapi đọc controller Spring, thư viện suy ra phần lớn kiểu dữ liệu của tham số từ kiểu Java và metadata của Spring MVC. Một tham số `Integer` thường trở thành schema `integer`, `Boolean` trở thành `boolean`, `String` trở thành `string`, còn một kiểu enum được biểu diễn bằng danh sách giá trị cho phép. Các kiểu ngày giờ có thể được biểu diễn thành chuỗi với `format` phù hợp.

Schema giúp client hiểu dữ liệu cần gửi và công cụ như Swagger UI trình bày tham số đúng kiểu. Tuy nhiên, schema là mô tả trong hợp đồng OpenAPI. Spring MVC vẫn chịu trách nhiệm chuyển chuỗi HTTP thành kiểu Java; Bean Validation kiểm tra ràng buộc runtime; Jackson xử lý dữ liệu JSON trong request body và response. Muốn tài liệu chính xác, cần đồng bộ cả ba phần này.

## 1. Schema được suy ra từ kiểu Java

OpenAPI dùng một số kiểu dữ liệu cơ bản để mô tả tham số và thuộc tính:

| Kiểu Java thường gặp | Kiểu OpenAPI thường được sinh | Ý nghĩa |
| --- | --- | --- |
| `byte`, `short`, `int`, `Integer` | `integer`, thường là `int32` | Số nguyên 32 bit. |
| `long`, `Long` | `integer`, thường là `int64` | Số nguyên 64 bit. |
| `BigInteger` | `integer`, format có thể không được gắn | Số nguyên độ chính xác tùy ý; không nên mặc định giới hạn nó trong phạm vi `int64`. |
| `float`, `Float` | `number`, `float` | Số thực độ chính xác đơn. |
| `double`, `Double` | `number`, `double` | Số thực độ chính xác kép. |
| `BigDecimal` | `number` | Số thập phân có độ chính xác cao, phù hợp với tiền và phép tính tài chính. |
| `boolean`, `Boolean` | `boolean` | Giá trị đúng hoặc sai. |
| `String`, `char`, `Character` | `string` | Văn bản hoặc ký tự. |
| `UUID` | `string`, `uuid` | Mã định danh UUID. |
| Java `enum` | `string` cùng danh sách giá trị | Một giá trị được chọn từ tập hằng số. |
| `LocalDate` | `string`, `date` | Ngày không kèm giờ hoặc múi giờ. |
| `OffsetDateTime`, `Instant`, `Date` | `string`, thường là `date-time` | Thời điểm có thể biểu diễn theo chuẩn ngày giờ có offset hoặc UTC. |

Đây là cách ánh xạ phổ biến, không phải quy tắc bất biến cho mọi kiểu tùy chỉnh. Jackson module, custom converter, annotation và phiên bản springdoc có thể ảnh hưởng cách dữ liệu được mô tả. Hãy kiểm tra đặc tả JSON thực tế khi kiểu dữ liệu quan trọng với hợp đồng.

## 2. Tham số số: integer và number

OpenAPI phân biệt `integer` với `number`. `format` giúp mô tả độ rộng hoặc độ chính xác thường dùng:

- `integer` với `int32`: số nguyên 32 bit, thường tương ứng Java `int` hoặc `Integer`.
- `integer` với `int64`: số nguyên 64 bit, thường tương ứng Java `long` hoặc `Long`.
- `number` với `float` hoặc `double`: số dấu phẩy động.
- `number` không có format cụ thể: có thể dùng cho `BigDecimal` hoặc số thập phân không gắn với độ chính xác nhị phân.

Ví dụ controller tìm sản phẩm theo khoảng giá:

```java
@RestController
@RequestMapping("/api/products")
@Validated
class ProductController {

    @GetMapping
    List<ProductResponse> search(
        @Parameter(description = "Giá tối thiểu", example = "100000")
        @RequestParam(required = false)
        @DecimalMin("0.00")
        BigDecimal minPrice,

        @Parameter(description = "Giá tối đa", example = "5000000")
        @RequestParam(required = false)
        @DecimalMin("0.00")
        BigDecimal maxPrice,

        @Parameter(description = "Số kết quả tối đa", example = "50")
        @RequestParam(defaultValue = "20")
        @Min(1) @Max(100)
        Integer limit
    ) {
        return productService.search(minPrice, maxPrice, limit);
    }
}
```

Với tham số số, springdoc có thể suy ra kiểu từ `BigDecimal` hoặc `Integer`; `@Parameter` bổ sung mô tả và ví dụ; constraint như `@DecimalMin`, `@Min`, `@Max` có thể được phản ánh thành giới hạn trong schema khi Bean Validation được nhận diện. `defaultValue` của `@RequestParam` là giá trị Spring MVC sử dụng khi client không gửi tham số; nó cũng ảnh hưởng việc tham số có bắt buộc hay không.

Nếu cần bổ sung giới hạn hoặc metadata chỉ dành cho tài liệu, có thể dùng `@Schema` lồng trong `@Parameter`:

```java
@Parameter(
    description = "Số lượng bản ghi mỗi trang",
    example = "25",
    schema = @Schema(minimum = "1", maximum = "100", defaultValue = "25")
)
@RequestParam(defaultValue = "25")
Integer size
```

`@Schema(minimum = "1")` mô tả giới hạn trong OpenAPI. Để server thực sự từ chối giá trị nhỏ hơn 1, cần constraint runtime như `@Min(1)` và kích hoạt method validation phù hợp. Không nên chỉ dựa vào tài liệu để bảo vệ dữ liệu đầu vào.

Với tiền tệ, ưu tiên `BigDecimal` thay vì `float` hoặc `double` để tránh sai số biểu diễn nhị phân. Nên ghi rõ đơn vị trong mô tả, ví dụ VND, USD hoặc đơn vị nhỏ nhất của tiền tệ. `minimum` và `maximum` cần cùng đơn vị với giá trị API nhận.

## 3. Boolean: true, false và giá trị mặc định

Kiểu `boolean` hoặc `Boolean` được biểu diễn thành schema `boolean`. Với query parameter, client thường truyền `true` hoặc `false` trong URL:

```java
@GetMapping("/api/products")
List<ProductResponse> search(
    @Parameter(description = "Chỉ lấy sản phẩm đang kinh doanh", example = "true")
    @RequestParam(defaultValue = "false")
    boolean active
) {
    return productService.findByActive(active);
}
```

Ví dụ request:

```http
GET /api/products?active=true
```

Với `boolean` nguyên thủy, Java luôn có một giá trị `true` hoặc `false`; nó không thể biểu diễn `null`. Với `Boolean`, ứng dụng có thể phân biệt ba trạng thái: `true`, `false` và `null` khi tham số được khai báo không bắt buộc và không có giá trị mặc định. Sự khác biệt này hữu ích nếu `null` mang nghĩa “không lọc theo trạng thái”.

Không nên dùng chuỗi như `yes/no`, `1/0` hoặc `on/off` nếu endpoint không có converter riêng. Hãy công bố định dạng client cần gửi và kiểm tra cách Spring chuyển đổi giá trị thực tế.

## 4. String: độ dài, pattern và định dạng

`String` thường được biểu diễn thành schema `string`. Các ràng buộc thường dùng gồm:

- `minLength` và `maxLength`: giới hạn độ dài.
- `pattern`: biểu thức chính quy mà giá trị cần khớp.
- `format`: định dạng có ý nghĩa như `email`, `uuid`, `uri`, `date` hoặc `date-time`.
- `example`: giá trị minh họa để người đọc hiểu định dạng.

Ví dụ tham số mã khách hàng:

```java
@GetMapping("/api/customers")
List<CustomerResponse> find(
    @Parameter(
        description = "Địa chỉ email cần tìm",
        example = "support@example.com",
        schema = @Schema(format = "email", maxLength = 254)
    )
    @RequestParam(required = false)
    @Email @Size(max = 254)
    String email,

    @Parameter(
        description = "Mã tham chiếu gồm 6 đến 12 ký tự chữ và số",
        example = "CUS8A21",
        schema = @Schema(minLength = 6, maxLength = 12, pattern = "^[A-Za-z0-9]+$")
    )
    @RequestParam(required = false)
    @Size(min = 6, max = 12) @Pattern(regexp = "^[A-Za-z0-9]+$")
    String reference
) {
    return customerService.find(email, reference);
}
```

Ở đây, `@Schema` giúp công bố định dạng và giới hạn; `@Email`, `@Size`, `@Pattern` là constraint validation. Constraint chỉ được thực thi nếu validation provider và method validation đã được cấu hình. Ngoài ra, `@Email` có thể chấp nhận nhiều dạng địa chỉ theo validator; nếu hợp đồng yêu cầu quy tắc cụ thể hơn, hãy dùng pattern có chủ đích và kiểm thử nó.

Không tự đặt `format` tùy tiện. OpenAPI cho phép format mở rộng, nhưng client generator chỉ hiểu chắc chắn một số format phổ biến. Nếu format không phải chuẩn được công cụ nhận diện, hãy mô tả rõ bằng `description`, `pattern` và ví dụ.

## 5. Enum: công bố tập giá trị hợp lệ

Khi tham số Java dùng enum, springdoc thường sinh schema chuỗi có danh sách các giá trị tương ứng. Ví dụ:

```java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}
```

```java
@GetMapping("/api/orders")
List<OrderResponse> findByStatus(
    @Parameter(description = "Trạng thái đơn hàng", example = "PENDING")
    @RequestParam(required = false)
    OrderStatus status
) {
    return orderService.findByStatus(status);
}
```

Schema thường có dạng:

```yaml
type: string
enum:
  - PENDING
  - CONFIRMED
  - SHIPPED
  - CANCELLED
```

Enum giúp giảm lỗi chính tả và tạo danh sách lựa chọn trong Swagger UI. Tuy nhiên, giá trị thực tế được chấp nhận phụ thuộc cách Spring chuyển đổi tham số và cấu hình Jackson cho body. Nếu ứng dụng dùng converter tùy chỉnh, `@JsonValue` hoặc cách serialize enum khác, cần bảo đảm schema liệt kê đúng giá trị wire format mà API thật sự nhận hoặc trả về.

Với một tham số `String` chỉ nhận một tập giá trị cố định, có thể khai báo `allowableValues` hoặc `@Schema(allowableValues = {...})`. Tuy nhiên, nếu các giá trị là một khái niệm ổn định trong domain, Java enum thường giúp tránh lặp lại danh sách ở nhiều nơi.

## 6. Ngày và giờ: chọn đúng kiểu dữ liệu và format

Ngày giờ dễ gây hiểu nhầm vì kiểu Java có thể có hoặc không có múi giờ. OpenAPI thường dùng chuỗi với format:

| Kiểu Java | Biểu diễn API thường dùng | Ghi chú |
| --- | --- | --- |
| `LocalDate` | `type: string`, `format: date` | Ngày lịch, ví dụ `2026-11-20`; không có giờ hoặc múi giờ. |
| `LocalTime` | `type: string`, thường mô tả giờ địa phương | Không chứa ngày hoặc múi giờ; quy ước format cần được thống nhất trong API. |
| `LocalDateTime` | Chuỗi ngày giờ địa phương; có thể được suy ra thành `date-time` tùy tích hợp | Không có offset; không tự xác định được một thời điểm duy nhất trên toàn cầu. Nếu schema sinh ra dùng `date-time`, mô tả phải nói rõ đây là giờ địa phương. |
| `OffsetDateTime` | `type: string`, `format: date-time` | Có offset, ví dụ `2026-11-20T09:30:00+07:00`. |
| `Instant` | `type: string`, `format: date-time` | Thời điểm UTC, thường có hậu tố `Z`. |
| `Date` | Thường là `type: string`, `format: date-time` | Cách serialize phụ thuộc cấu hình Jackson và ứng dụng. |

Ví dụ filter theo ngày tạo:

```java
@GetMapping("/api/orders")
List<OrderResponse> findCreatedAfter(
    @Parameter(
        description = "Ngày bắt đầu, định dạng yyyy-MM-dd",
        example = "2026-11-01",
        schema = @Schema(type = "string", format = "date")
    )
    @RequestParam
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    LocalDate from
) {
    return orderService.findCreatedAfter(from);
}
```

Với thời điểm cần xác định rõ múi giờ, ưu tiên `OffsetDateTime` hoặc `Instant`:

```java
@GetMapping("/api/events")
List<EventResponse> findEvents(
    @Parameter(
        description = "Thời điểm bắt đầu theo ISO 8601, có offset múi giờ",
        example = "2026-11-20T09:30:00+07:00",
        schema = @Schema(type = "string", format = "date-time")
    )
    @RequestParam
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
    OffsetDateTime from
) {
    return eventService.findFrom(from);
}
```

`@DateTimeFormat` hướng dẫn Spring chuyển đổi tham số query, path hoặc form thành kiểu ngày giờ Java. Với JSON request/response body, Jackson thực hiện serialize và deserialize; cấu hình `ObjectMapper`, Java Time module và `@JsonFormat` có thể ảnh hưởng định dạng JSON. `@Schema(format = "date-time")` chỉ công bố định dạng trong tài liệu, không tự cấu hình parser hoặc serializer.

Không nên gắn `format: date-time` cho `LocalDateTime` rồi mặc định rằng client sẽ hiểu múi giờ. Kiểu này không mang offset. Nếu API biểu diễn một thời điểm toàn cầu, hãy chọn kiểu có offset/UTC và ghi rõ quy tắc múi giờ. Nếu nghiệp vụ thực sự dùng giờ địa phương, cần mô tả vùng thời gian áp dụng, ví dụ múi giờ của cửa hàng hoặc địa điểm.

## 7. Kết hợp schema, required và default value

Kiểu dữ liệu và tính bắt buộc là hai khái niệm riêng. Ví dụ `Integer` có thể là tham số bắt buộc hoặc tùy chọn tùy cách khai báo trong Spring MVC:

```java
@GetMapping("/api/products/{id}")
ProductResponse get(
    @PathVariable UUID id,
    @RequestParam(required = false) Boolean includeInactive,
    @RequestParam(defaultValue = "0") @Min(0) Integer page
) {
    return productService.get(id, includeInactive, page);
}
```

- `id` là path parameter nên bắt buộc theo cấu trúc URL.
- `includeInactive` là query parameter tùy chọn; khi không gửi, Spring có thể bind thành `null`.
- `page` có default value `0`; Spring dùng giá trị này khi client không gửi tham số.

Trong OpenAPI, `required` mô tả client có phải gửi parameter hay không; `schema` mô tả kiểu và ràng buộc của giá trị. `default` là giá trị mặc định được công bố hoặc sử dụng theo ngữ cảnh, nhưng không phải cơ chế validation. Không nhầm `nullable` của schema với `required` của parameter: một parameter có thể tùy chọn, trong khi một parameter bắt buộc vẫn có schema không cho phép giá trị null.

## 8. Tùy chỉnh schema khi suy luận tự động chưa đủ

Thông thường nên để springdoc suy ra kiểu từ Java. Chỉ ghi đè `@Schema` khi cần diễn đạt một chi tiết mà kiểu Java hoặc annotation Spring chưa cung cấp đủ:

```java
@Parameter(
    name = "trackingCode",
    description = "Mã theo dõi gồm đúng 10 chữ số",
    required = true,
    example = "0123456789",
    schema = @Schema(
        type = "string",
        minLength = 10,
        maxLength = 10,
        pattern = "^[0-9]{10}$"
    )
)
@RequestParam String trackingCode
```

Ở ví dụ này, mã theo dõi được giữ dưới kiểu `string` dù chỉ gồm chữ số. Nếu mô tả nó là `integer`, client có thể loại bỏ số 0 ở đầu hoặc chuyển sang kiểu số, làm thay đổi giá trị định danh. Chọn schema theo ý nghĩa dữ liệu, không chỉ theo hình dạng ký tự.

Khi tùy chỉnh, hãy giữ nhất quán giữa:

- Kiểu Java mà controller nhận.
- Quy tắc chuyển đổi của Spring MVC hoặc Jackson.
- Constraint runtime mà server thực thi.
- `type`, `format`, `enum`, `pattern`, `minimum`, `maximum`, `minLength` và `maxLength` trong OpenAPI.

Nếu schema nói tham số là số nhưng controller nhận chuỗi theo một định dạng riêng, Swagger UI và client generator có thể tạo request sai. Nếu schema công bố giới hạn nhưng server không kiểm tra, client sẽ tin vào một hợp đồng không được thực thi.

## 9. Kiểm tra schema được sinh ra

Sau khi thêm hoặc thay đổi tham số, nên xác minh đặc tả và hành vi HTTP:

1. Khởi động ứng dụng và mở `/v3/api-docs` hoặc URL đã cấu hình.
2. Tìm operation trong `paths`, mở `parameters` và kiểm tra `name`, `in`, `required`, `schema.type`, `schema.format`, `enum`, `minimum`, `maximum`, `pattern` và `example`.
3. Mở Swagger UI, xác nhận kiểu điều khiển nhập liệu và danh sách enum được hiển thị hợp lý.
4. Gửi giá trị hợp lệ để kiểm tra Spring chuyển đổi đúng kiểu Java.
5. Gửi giá trị sai kiểu, vượt giới hạn, sai enum hoặc sai định dạng ngày giờ; xác minh server trả lỗi phù hợp.
6. Với ngày giờ, kiểm tra offset hoặc UTC trong request và response để tránh lệch thời điểm khi triển khai ở môi trường có múi giờ khác nhau.

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Tham số số không có giới hạn trong schema | Constraint chưa được nhận diện hoặc thiếu metadata | Kiểm tra Bean Validation và bổ sung `@Schema` nếu cần. |
| Swagger UI cho nhập chuỗi nhưng API mong enum | Tham số khai báo bằng `String` mà không công bố allowable values | Dùng Java enum hoặc khai báo `allowableValues`. |
| Ngày giờ bị lỗi parse | Format gửi lên không khớp converter của Spring hoặc cấu hình Jackson | Phân biệt query parameter với JSON body; kiểm tra `@DateTimeFormat` và `@JsonFormat`. |
| Thời điểm lệch giờ | Dùng kiểu không có offset hoặc serialize theo timezone môi trường | Dùng `Instant`/`OffsetDateTime` và thống nhất quy tắc UTC/offset. |
| Số định danh mất số 0 đầu | Mô tả mã định danh bằng schema số | Dùng `string` cùng pattern/độ dài phù hợp. |
| Tài liệu nói optional nhưng server báo thiếu parameter | `required` trong mapping không khớp metadata hoặc default value | Kiểm tra `@RequestParam`, `@PathVariable` và schema trong `/v3/api-docs`. |

## 10. Nguyên tắc áp dụng

- Để springdoc suy luận schema từ kiểu Java trước; chỉ tùy chỉnh khi hợp đồng cần thêm định dạng hoặc ràng buộc.
- Dùng kiểu số phù hợp với miền giá trị; ưu tiên `BigDecimal` cho tiền và `String` cho mã định danh có thể có số 0 đầu.
- Dùng Java enum cho tập giá trị cố định và bảo đảm schema khớp cách Spring/Jackson chuyển đổi giá trị.
- Dùng `LocalDate` cho ngày lịch; dùng `OffsetDateTime` hoặc `Instant` khi cần một thời điểm có múi giờ xác định.
- Tách bạch metadata `@Schema` với chuyển đổi dữ liệu và validation runtime.
- Kiểm tra `/v3/api-docs`, Swagger UI và request thực tế mỗi khi thay đổi kiểu tham số.

Schema tốt mô tả đúng giá trị mà API nhận và trả về. Springdoc giúp tự động hóa phần mô tả từ kiểu Java, nhưng người phát triển vẫn phải xác định rõ định dạng, đơn vị, miền giá trị và quy tắc múi giờ để client có thể tích hợp chính xác.

## Tài liệu tham khảo

- [OpenAPI Specification – Data Types and Formats](https://spec.openapis.org/oas/latest.html)
- [Springdoc OpenAPI – tài liệu chính thức](https://springdoc.org/)
- [Swagger Annotations – Schema and Parameter annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
- [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
