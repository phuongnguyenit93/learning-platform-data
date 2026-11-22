# Schema Object và ánh xạ kiểu Java sang kiểu OpenAPI

Schema là phần mô tả hình dạng và quy tắc dữ liệu trong hợp đồng OpenAPI. Nó cho biết một giá trị là chuỗi, số, boolean, object hay array; object có những thuộc tính nào; thuộc tính nào bắt buộc; giá trị có định dạng hoặc giới hạn gì. Khi dùng springdoc-openapi, schema thường được suy ra từ kiểu Java của tham số, DTO và kiểu trả về trong controller Spring Boot, sau đó có thể được bổ sung bằng annotation và cấu hình.

Hiểu cách ánh xạ kiểu Java sang OpenAPI giúp kiểm tra tài liệu được sinh có phản ánh đúng JSON mà ứng dụng nhận và trả hay không. Một kiểu Java không phải lúc nào cũng chuyển thành một schema duy nhất: Jackson có thể đổi tên hoặc loại bỏ thuộc tính, Bean Validation có thể bổ sung ràng buộc, còn annotation `@Schema` có thể làm rõ hoặc điều chỉnh mô tả công khai.

## 1. Schema Object dùng để mô tả điều gì?

Trong OpenAPI, Schema Object mô tả cấu trúc dữ liệu dựa trên một tập quy tắc của JSON Schema. Nó được dùng trong request body, response, parameter và các thành phần có thể tái sử dụng.

Một schema đơn giản:

```yaml
type: object
required:
  - name
  - age
properties:
  name:
    type: string
    description: Tên người dùng
  age:
    type: integer
    format: int32
    minimum: 0
```

Schema trên mô tả một object có hai thuộc tính `name` và `age`. Cả hai thuộc tính được liệt kê trong `required`; `name` là chuỗi, `age` là số nguyên 32-bit và không nhỏ hơn 0.

Các trường thường gặp:

| Trường | Ý nghĩa |
|---|---|
| `type` | Kiểu dữ liệu như `string`, `integer`, `number`, `boolean`, `object` hoặc `array` |
| `format` | Định dạng bổ sung, ví dụ `date`, `date-time`, `uuid`, `int32`, `int64` |
| `properties` | Các thuộc tính của object |
| `required` | Danh sách tên thuộc tính bắt buộc trong object |
| `items` | Schema của từng phần tử trong array |
| `enum` | Tập giá trị được phép |
| `minimum`, `maximum` | Giới hạn cho giá trị số |
| `minLength`, `maxLength`, `pattern` | Ràng buộc cho chuỗi |
| `minItems`, `maxItems`, `uniqueItems` | Ràng buộc cho array |
| `description` | Mô tả ý nghĩa của dữ liệu |
| `example` | Một ví dụ minh họa |
| `$ref` | Tham chiếu đến schema hoặc thành phần được tái sử dụng |
| `readOnly`, `writeOnly`, `deprecated` | Đặc tính sử dụng của thuộc tính hoặc schema |

Schema mô tả hợp đồng dữ liệu, không thực thi validation trong ứng dụng. Ví dụ, `minimum: 0` giúp công cụ hiểu giới hạn hợp đồng; để từ chối giá trị âm khi request chạy, ứng dụng vẫn cần validation hoặc logic nghiệp vụ tương ứng.

## 2. Schema được tạo từ kiểu Java như thế nào?

Springdoc phân tích endpoint Spring, chữ ký phương thức, kiểu dữ liệu, annotation và các metadata liên quan. Thư viện dùng thông tin từ hệ sinh thái Swagger Core, Jackson và Bean Validation để xây dựng mô hình OpenAPI.

Ví dụ:

```java
@RestController
@RequestMapping("/api/users")
class UserController {

    @GetMapping("/{id}")
    UserResponse getById(@PathVariable UUID id) {
        return userService.findById(id);
    }

    @PostMapping
    UserResponse create(@Valid @RequestBody CreateUserRequest request) {
        return userService.create(request);
    }
}
```

Từ chữ ký phương thức, springdoc có thể suy ra:

- `UUID id` là path parameter có schema chuỗi với định dạng UUID.
- `CreateUserRequest` là schema của request body.
- `UserResponse` là schema của nội dung response.
- Các thuộc tính trong DTO được phân tích để tạo object schema, cùng những constraint được nhận diện.

Đây là quá trình suy luận dựa trên metadata. Kiểu Java là nguồn thông tin quan trọng nhưng không phải lúc nào cũng phản ánh toàn bộ JSON thực tế. Serializer tùy chỉnh, mixin Jackson, getter đặc biệt, view hoặc cấu hình loại bỏ thuộc tính có thể làm payload khác với cấu trúc lớp Java.

## 3. Ánh xạ các kiểu scalar phổ biến

Các kiểu scalar là những giá trị đơn như chuỗi, số và boolean. Bảng sau mô tả ánh xạ thường gặp; định dạng cụ thể có thể thay đổi theo phiên bản springdoc, Swagger Core, OpenAPI và cấu hình converter.

| Kiểu Java | Kiểu OpenAPI thường gặp | Ghi chú |
|---|---|---|
| `String` | `string` | Không tự suy ra ngữ nghĩa như email hoặc mã bưu chính nếu thiếu metadata |
| `char`, `Character` | `string` | Có thể cần giới hạn độ dài nếu hợp đồng yêu cầu đúng một ký tự |
| `boolean`, `Boolean` | `boolean` | Primitive không thể nhận `null`; wrapper có thể vắng mặt hoặc null tùy hợp đồng |
| `byte`, `short`, `int`, `Integer` | `integer`, thường `int32` | Số nguyên 32-bit trong mô tả thông thường |
| `long`, `Long` | `integer`, thường `int64` | Số nguyên 64-bit |
| `float`, `Float` | `number`, thường `float` | Số dấu phẩy động độ chính xác đơn |
| `double`, `Double` | `number`, thường `double` | Số dấu phẩy động độ chính xác kép |
| `BigDecimal`, `BigInteger` | `number` hoặc `integer` | Định dạng và độ chính xác cần được xác nhận theo serializer, thư viện và hợp đồng |
| `UUID` | `string`, `format: uuid` | Chuỗi định danh UUID |
| `LocalDate` | `string`, `format: date` | Ngày không kèm thời gian |
| `LocalDateTime`, `OffsetDateTime`, `Instant` | Thường `string`, `format: date-time` | Cần thống nhất múi giờ và cách serialize |
| `LocalTime` | Thường `string` | Có thể bổ sung format và mô tả theo quy ước API |
| `byte[]` | Thường là chuỗi theo cách biểu diễn nhị phân/base64 | Cần xác định media type và cách truyền file hoặc nội dung nhị phân |

`format` bổ sung ý nghĩa cho `type`; nó không thay thế `type`. Ví dụ, UUID vẫn có `type: string`, còn `format: uuid` mô tả định dạng cụ thể. Tương tự, `date-time` là một định dạng của chuỗi chứ không phải kiểu dữ liệu độc lập.

Một số format được OpenAPI và công cụ phổ biến nhận biết, nhưng `format` thường là metadata định hướng và không phải validator runtime tự động. Nếu API có quy tắc riêng, hãy mô tả rõ bằng `description`, `pattern`, giới hạn hoặc constraint tương ứng.

## 4. Ánh xạ object, array, collection và Map

### Object từ DTO hoặc POJO

Một lớp Java có các thuộc tính thường được mô tả thành `type: object`, mỗi thuộc tính nằm trong `properties`.

```java
public class Address {
    private String street;
    private String city;
    private String postalCode;

    // getters và setters
}

public class UserResponse {
    private UUID id;
    private String name;
    private Address address;

    // getters và setters
}
```

Schema tương ứng có thể được tổ chức bằng `$ref` để tái sử dụng `Address`:

```yaml
components:
  schemas:
    UserResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        name:
          type: string
        address:
          $ref: '#/components/schemas/Address'
    Address:
      type: object
      properties:
        street:
          type: string
        city:
          type: string
        postalCode:
          type: string
```

Springdoc có thể tạo các schema trong `components.schemas` và tham chiếu chúng từ operation. Tên schema phụ thuộc tên lớp, cấu hình tên schema, generic type và các quy tắc xử lý model của thư viện.

### Array và collection

Mảng Java, `List<T>`, `Set<T>` và các collection tương tự thường được mô tả bằng `type: array`. Trường `items` mô tả kiểu của từng phần tử.

```java
public class TeamResponse {
    private List<UserResponse> members;
    private Set<String> labels;

    // getters và setters
}
```

Schema minh họa:

```yaml
TeamResponse:
  type: object
  properties:
    members:
      type: array
      items:
        $ref: '#/components/schemas/UserResponse'
    labels:
      type: array
      items:
        type: string
```

Với `Set`, hợp đồng có thể thể hiện `uniqueItems: true` nếu metadata và công cụ hỗ trợ suy ra đặc tính đó. Không nên dựa vào tên kiểu Java để khẳng định mọi công cụ client sẽ giữ nguyên ngữ nghĩa tập hợp; hãy kiểm tra schema thực tế và yêu cầu nghiệp vụ.

### Map và object có key động

Map có key dạng chuỗi thường được mô tả bằng object với `additionalProperties` chỉ ra schema của giá trị:

```java
Map<String, String> labels;
Map<String, BigDecimal> prices;
```

```yaml
labels:
  type: object
  additionalProperties:
    type: string
prices:
  type: object
  additionalProperties:
    type: number
```

Nếu key của Map không cố định, `properties` không thể liệt kê trước tất cả key. `additionalProperties` mô tả kiểu của các giá trị động. Nếu API chỉ cho phép một tập key xác định, có thể cân nhắc DTO có thuộc tính rõ ràng hoặc constraint bổ sung để hợp đồng dễ hiểu hơn.

## 5. Enum và tập giá trị hợp lệ

Java enum thường được serialize thành chuỗi và có thể được mô tả bằng `type: string` cùng `enum`.

```java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}
```

Schema minh họa:

```yaml
OrderStatus:
  type: string
  enum:
    - PENDING
    - PAID
    - SHIPPED
    - CANCELLED
```

Nếu Jackson dùng `@JsonValue`, custom serializer hoặc cấu hình chuyển enum thành số/chuỗi khác, giá trị JSON công khai có thể không giống tên hằng enum. Khi đó, cần kiểm tra output thực tế và bổ sung metadata để schema phản ánh đúng biểu diễn đã serialize.

Ví dụ enum có mã công khai riêng:

```java
public enum OrderStatus {
    PENDING("P"),
    PAID("Y"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    @JsonValue
    public String getCode() {
        return code;
    }
}
```

Trong trường hợp này, hãy kiểm tra cách Swagger Core và cấu hình Jackson được tích hợp để xác nhận enum trong OpenAPI là `P`, `Y`, `X` hay tên hằng. Không giả định schema tự động luôn theo một cách serialize tùy chỉnh.

## 6. `required`, nullable và giá trị mặc định

Ba khái niệm này có liên quan nhưng không đồng nghĩa:

- **Required:** thuộc tính phải xuất hiện trong object JSON.
- **Nullable:** thuộc tính có thể xuất hiện với giá trị `null`.
- **Default:** giá trị mặc định được mô tả hoặc áp dụng theo quy ước của API khi dữ liệu không được cung cấp.

Ví dụ, một thuộc tính có thể bắt buộc xuất hiện nhưng vẫn cho phép `null`; một thuộc tính khác có thể không bắt buộc xuất hiện nhưng nếu xuất hiện thì phải có giá trị khác null. Cách biểu diễn nullable phụ thuộc phiên bản OpenAPI.

Trong OpenAPI 3.0, `nullable: true` thường được dùng để thể hiện một giá trị có thể là null:

```yaml
type: object
required:
  - nickname
properties:
  nickname:
    type: string
    nullable: true
  description:
    type: string
```

Trong ví dụ, `nickname` phải có mặt nhưng có thể mang giá trị null. `description` không nằm trong danh sách required nên có thể không xuất hiện. Nếu `description` có mặt, schema ở ví dụ này yêu cầu nó là chuỗi.

OpenAPI 3.1 dựa sát hơn vào JSON Schema và hỗ trợ cách biểu diễn union type có `null`, ví dụ `type: [string, 'null']`. Cú pháp cụ thể cần phù hợp phiên bản OpenAPI mà tài liệu springdoc đang xuất; không trộn cú pháp 3.0 và 3.1 trong cùng schema.

### Java primitive và wrapper

Java primitive như `int` hoặc `boolean` không thể nhận `null`; wrapper như `Integer` hoặc `Boolean` có thể nhận `null`. Tuy vậy, wrapper không tự động đồng nghĩa thuộc tính là optional hay nullable trong mọi schema. Sự hiện diện của thuộc tính và khả năng nhận null còn phụ thuộc Bean Validation, annotation, Jackson, phiên bản OpenAPI và cách thư viện suy luận.

Ví dụ DTO:

```java
public class CreateUserRequest {
    @NotBlank
    private String name;

    @NotNull
    @Positive
    private Integer age;

    private String nickname;

    // getters và setters
}
```

`@NotBlank` và `@NotNull` có thể giúp springdoc mô tả các thuộc tính tương ứng là bắt buộc theo tích hợp Bean Validation. `@Positive` có thể được ánh xạ thành giới hạn số nếu constraint được hỗ trợ. Tuy nhiên, hãy kiểm tra schema thực tế thay vì giả định mọi validation tùy chỉnh đều được chuyển thành OpenAPI.

### Giá trị mặc định

`default` mô tả giá trị mặc định theo hợp đồng. Nó không nhất thiết làm cho Spring tự gán giá trị khi request thiếu field. Nếu ứng dụng muốn áp dụng mặc định khi nhận request, logic đó cần tồn tại trong constructor, setter, binder hoặc tầng xử lý phù hợp.

```yaml
page:
  type: integer
  format: int32
  default: 0
  minimum: 0
```

Đừng nhầm `default` với `example`: default là giá trị mặc định được mô tả; example chỉ minh họa một giá trị có thể dùng.

## 7. Ràng buộc dữ liệu từ Bean Validation

Bean Validation có thể bổ sung giới hạn cho schema. Những constraint phổ biến:

| Annotation | Ràng buộc OpenAPI thường gặp |
|---|---|
| `@NotNull` | Thuộc tính bắt buộc hoặc không nullable tùy vị trí và phiên bản tích hợp |
| `@NotBlank` | Chuỗi không được null, rỗng hoặc chỉ chứa khoảng trắng; có thể ảnh hưởng required và minLength |
| `@NotEmpty` | Chuỗi, collection hoặc map không được rỗng; có thể ánh xạ thành minLength/minItems hoặc required |
| `@Size(min, max)` | `minLength`/`maxLength` hoặc `minItems`/`maxItems` tùy kiểu |
| `@Min`, `@Max` | `minimum`, `maximum` |
| `@DecimalMin`, `@DecimalMax` | Giới hạn số tương ứng |
| `@Positive`, `@PositiveOrZero` | Giới hạn dưới của giá trị số |
| `@Pattern` | `pattern` |
| `@Email` | Thường mô tả chuỗi với định dạng email hoặc constraint tương ứng |

Ví dụ:

```java
public class CreateProductRequest {
    @NotBlank
    @Size(max = 120)
    private String name;

    @NotNull
    @DecimalMin("0.01")
    @DecimalMax("999999999.99")
    private BigDecimal price;

    @Pattern(regexp = "^[A-Z0-9-]+$")
    private String sku;

    // getters và setters
}
```

Các constraint có thể được biểu diễn trong schema để client hiểu dữ liệu hợp lệ. Nhưng validator mới là thành phần thực thi khi request chạy. Một schema có `minLength: 1` không bảo đảm ứng dụng thực sự từ chối chuỗi chỉ có dấu cách nếu validator hoặc logic runtime không áp dụng đúng quy tắc.

## 8. Tùy chỉnh Schema bằng `@Schema`

Springdoc suy luận schema từ kiểu Java, nhưng annotation `@Schema` cho phép bổ sung metadata hoặc điều chỉnh cách mô tả.

```java
@Schema(name = "CreateUserRequest", description = "Dữ liệu tạo người dùng mới")
public class CreateUserRequest {

    @Schema(
        description = "Tên hiển thị của người dùng",
        example = "Nguyen Van A",
        maxLength = 100
    )
    @NotBlank
    private String name;

    @Schema(
        description = "Email dùng để liên hệ",
        example = "user@example.com",
        format = "email"
    )
    @Email
    private String email;

    // getters và setters
}
```

Một số thuộc tính `@Schema` thường dùng:

| Thuộc tính | Mục đích |
|---|---|
| `name` | Tên schema hoặc tên thuộc tính được công bố |
| `description` | Mô tả ý nghĩa dữ liệu |
| `type`, `format` | Chỉ định kiểu và định dạng |
| `example` | Giá trị ví dụ |
| `allowableValues` | Tập giá trị cho phép trong một số cách dùng |
| `minimum`, `maximum` | Giới hạn số |
| `minLength`, `maxLength` | Giới hạn độ dài chuỗi |
| `pattern` | Biểu thức chính quy |
| `accessMode` | Đánh dấu thuộc tính chỉ đọc, chỉ ghi hoặc đọc/ghi |
| `hidden` | Ẩn schema hoặc thuộc tính khỏi tài liệu trong phạm vi hỗ trợ |
| `implementation` | Chỉ định kiểu triển khai dùng làm schema |

Không nên dùng annotation để mô tả một kiểu dữ liệu khác với payload thực tế. Nếu `@Schema(type = "string")` được đặt lên một thuộc tính đang serialize thành object, client sẽ nhận một hợp đồng sai. Khi thay đổi schema bằng annotation, cần kiểm tra JSON runtime.

## 9. `readOnly`, `writeOnly` và DTO request/response

Một số thuộc tính chỉ xuất hiện trong response hoặc chỉ được gửi trong request. OpenAPI hỗ trợ `readOnly` và `writeOnly` để thể hiện điều này.

Ví dụ:

```yaml
User:
  type: object
  properties:
    id:
      type: string
      format: uuid
      readOnly: true
    password:
      type: string
      writeOnly: true
    name:
      type: string
```

Trong Java, có thể mô tả bằng `@Schema(accessMode = Schema.AccessMode.READ_ONLY)` hoặc `WRITE_ONLY` tùy thuộc tính và phiên bản annotation.

Tuy nhiên, nếu request và response có cấu trúc hoặc quy tắc khác nhau đáng kể, dùng hai DTO riêng thường rõ ràng hơn:

```java
public class CreateUserRequest {
    @NotBlank
    private String name;

    @Email
    private String email;

    // getters và setters
}

public class UserResponse {
    private UUID id;
    private String name;
    private String email;
    private Instant createdAt;

    // getters và setters
}
```

Tách DTO giúp tránh vô tình công bố trường nội bộ, giảm nhầm lẫn về required và nullable, và phản ánh đúng dữ liệu được phép ghi so với dữ liệu được trả về.

## 10. Jackson và kiểu JSON thực tế

Schema cần mô tả JSON mà ứng dụng thực sự serialize hoặc deserialize. Jackson có thể ảnh hưởng đến tên và sự hiện diện của thuộc tính thông qua annotation và cấu hình.

Ví dụ:

```java
public class UserResponse {
    @JsonProperty("display_name")
    private String name;

    @JsonIgnore
    private String internalNote;

    // getters và setters
}
```

Payload JSON công khai có thể chứa `display_name` thay vì `name` và không chứa `internalNote`. Springdoc tích hợp với Jackson để mô tả nhiều quy tắc này, nhưng với serializer tùy chỉnh, mixin, view hoặc logic serialize đặc biệt, vẫn cần kiểm tra tài liệu được sinh và JSON thực tế.

Các tình huống cần chú ý:

- `@JsonProperty` có thể đổi tên thuộc tính JSON.
- `@JsonIgnore` có thể loại bỏ thuộc tính khỏi quá trình serialize/deserialize theo cấu hình.
- `@JsonProperty(access = ...)` có thể điều chỉnh hướng đọc/ghi.
- `@JsonFormat` có thể ảnh hưởng định dạng ngày giờ hoặc enum.
- Custom serializer/deserializer có thể làm giá trị JSON khác kiểu Java ban đầu.
- Polymorphism, inheritance và Jackson subtype metadata có thể ảnh hưởng `oneOf`, `allOf`, discriminator hoặc schema được sinh.

Không nên chỉ nhìn field khai báo trong lớp Java để kết luận schema. Hãy kiểm tra getter/setter, annotation Jackson, cấu hình ObjectMapper và output runtime.

## 11. Generic type và schema tái sử dụng

Kiểu generic thường được dùng cho response có cấu trúc bao ngoài, ví dụ `PageResponse<UserResponse>` hoặc `ApiResponse<OrderResponse>`. Springdoc có thể phân tích generic type để tạo schema phù hợp, nhưng tên schema sinh tự động có thể dài hoặc khác nhau giữa phiên bản thư viện.

```java
public class ApiResponse<T> {
    private T data;
    private String message;

    // getters và setters
}
```

Controller:

```java
@GetMapping("/{id}")
ApiResponse<UserResponse> getById(@PathVariable UUID id) {
    return userService.getById(id);
}
```

Schema về mặt ý nghĩa là một object có `data` theo kiểu `UserResponse` và `message` là chuỗi. Tên thành phần thực tế do springdoc tạo phụ thuộc cách giải quyết generic và cấu hình model converter.

Nếu cần một tên schema ổn định cho hợp đồng công khai, có thể tạo DTO cụ thể hoặc cấu hình tên schema bằng annotation phù hợp. Tránh đổi tên schema đã được client tham chiếu nếu thay đổi đó gây ảnh hưởng đến quá trình sinh mã hoặc quản lý phiên bản.

## 12. Kiểm tra schema được springdoc sinh ra

Sau khi khai báo controller, DTO và annotation, cần kiểm tra tài liệu thực tế:

1. Khởi động ứng dụng Spring Boot.
2. Mở `/v3/api-docs` hoặc `/v3/api-docs.yaml`.
3. Tìm operation tương ứng trong `paths`.
4. Theo `$ref` đến `components.schemas` để xem định nghĩa đầy đủ.
5. Đối chiếu `type`, `format`, `properties`, `items`, `required`, nullable và constraint.
6. Gửi request hợp lệ và không hợp lệ để kiểm tra binding, serialization và validation.
7. So sánh response JSON thực tế với schema công bố.
8. Chạy OpenAPI validator để phát hiện cấu trúc sai hoặc tham chiếu không hợp lệ.

Ví dụ, nếu DTO có `LocalDate`, schema nên thể hiện chuỗi ngày theo định dạng phù hợp; nếu response thực tế lại serialize thành timestamp số, cần xem lại ObjectMapper hoặc điều chỉnh schema theo đúng hợp đồng thực tế.

Swagger UI hữu ích để xem schema và thử request, nhưng giao diện không thay thế việc kiểm tra JSON/YAML và payload runtime. Một schema hiển thị đẹp vẫn có thể mô tả sai dữ liệu.

## 13. Lỗi thường gặp khi ánh xạ kiểu

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Long` hiển thị thành string | Annotation hoặc converter tùy chỉnh đã đổi kiểu | Kiểm tra kiểu JSON thực tế và metadata schema |
| Ngày giờ thiếu format | Kiểu tùy chỉnh, Jackson format hoặc converter không được suy ra đầy đủ | Bổ sung `@Schema(format = ...)` và kiểm tra serializer |
| Enum có giá trị khác tên hằng | `@JsonValue` hoặc custom serializer | Đối chiếu schema với giá trị JSON được serialize |
| Thuộc tính bị thiếu | `@JsonIgnore`, visibility hoặc mixin | Kiểm tra cấu hình Jackson và DTO công khai |
| Field không được đánh dấu required | Constraint không được nhận diện hoặc annotation đặt sai vị trí | Kiểm tra Bean Validation và `required` trong schema |
| Wrapper bị hiểu nhầm nullable/optional | Nhầm giữa kiểu Java, sự hiện diện thuộc tính và null | Xác định riêng required, nullable và default |
| Collection thiếu schema phần tử | Generic type bị mất hoặc kiểu raw collection | Khai báo generic cụ thể, ví dụ `List<UserResponse>` |
| Schema Map không mô tả giá trị động | Kiểu value generic không được xác định | Dùng `Map<String, T>` rõ ràng hoặc DTO cụ thể |
| Generic schema có tên khó đọc | Tên model tự sinh từ nhiều tham số kiểu | Tạo DTO cụ thể hoặc tùy chỉnh tên schema |
| Tài liệu khác payload runtime | Serializer, view hoặc cấu hình Jackson thay đổi JSON | Kiểm thử serialization và cập nhật metadata |

## 14. Nguyên tắc thiết kế schema

- Thiết kế DTO công khai theo JSON contract, không để entity persistence quyết định schema API.
- Dùng kiểu Java cụ thể và generic đầy đủ để springdoc suy ra schema ổn định.
- Phân biệt `type` với `format`; format bổ sung ý nghĩa cho kiểu cơ sở.
- Xác định riêng thuộc tính bắt buộc, nullable và default.
- Dùng Bean Validation cho ràng buộc thực thi và kiểm tra cách chúng được ánh xạ vào OpenAPI.
- Dùng `@Schema` để bổ sung mô tả, ví dụ và giới hạn mà kiểu Java không thể diễn đạt.
- Kiểm tra Jackson annotation và custom serializer vì chúng ảnh hưởng JSON công khai.
- Dùng schema tái sử dụng khi nhiều endpoint chia sẻ cùng cấu trúc dữ liệu.
- Tách request DTO và response DTO khi quyền đọc/ghi hoặc cấu trúc khác nhau.
- Kiểm tra tài liệu OpenAPI cùng payload runtime sau mỗi thay đổi có ảnh hưởng đến schema.

## Kết luận

Schema Object mô tả kiểu, cấu trúc, định dạng và ràng buộc của dữ liệu trong hợp đồng OpenAPI. Springdoc-openapi suy ra schema từ kiểu Java, DTO, generic, Jackson và Bean Validation, sau đó cho phép bổ sung metadata bằng `@Schema`. Việc ánh xạ không chỉ là đổi tên kiểu Java sang `string`, `integer` hay `object`; còn phải thể hiện đúng required, nullable, format, collection, enum và JSON thực tế. Hãy kiểm tra schema được sinh cùng payload runtime để bảo đảm hợp đồng mà client nhìn thấy phản ánh chính xác ứng dụng Spring Boot.
