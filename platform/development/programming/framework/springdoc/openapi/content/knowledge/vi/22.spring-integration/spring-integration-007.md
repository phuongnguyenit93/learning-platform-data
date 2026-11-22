# Kotlin: khả năng nhận null, data class và tham số mặc định

Khi dùng Springdoc trong ứng dụng Spring Boot viết bằng Kotlin, kiểu dữ liệu Kotlin mang thêm thông tin quan trọng cho hợp đồng API: `String` không nhận `null`, `String?` có thể nhận `null`, còn tham số constructor có giá trị mặc định có thể được bỏ qua khi tạo object. Những khác biệt này ảnh hưởng đến cách Jackson đọc JSON request và cách Springdoc mô tả schema trong OpenAPI.

Ba khái niệm cần được hiểu riêng:

1. **Nullability** cho biết giá trị của một thuộc tính có thể là `null` hay không.
2. **Requiredness** trong OpenAPI cho biết client có bắt buộc phải gửi property đó hay không.
3. **Default value** cho biết server dùng giá trị nào khi property không được gửi, nếu constructor/deserializer hỗ trợ giá trị mặc định đó.

Một property có thể không nullable nhưng vẫn không bắt buộc vì Kotlin constructor có default value. Ngược lại, một property có thể bắt buộc phải xuất hiện nhưng cho phép giá trị `null` nếu hợp đồng API yêu cầu như vậy. Không nên dùng ba khái niệm này thay thế cho nhau.

## 1. Chuẩn bị dependency cho Kotlin và Springdoc

Spring Boot hỗ trợ Kotlin thông qua Kotlin standard library và Kotlin reflection. Jackson cần `jackson-module-kotlin` để đọc/ghi Kotlin constructor và data class theo metadata của Kotlin. Springdoc sử dụng thông tin model cùng Jackson/Spring để tạo OpenAPI schema.

Ví dụ Gradle Kotlin DSL cho Spring MVC:

```kotlin
plugins {
    id("org.springframework.boot") version "<spring-boot-version>"
    id("io.spring.dependency-management") version "<dependency-management-version>"
    kotlin("jvm") version "<kotlin-version>"
    kotlin("plugin.spring") version "<kotlin-version>"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:<springdoc-version>")
    implementation(kotlin("reflect"))
    implementation("com.fasterxml.jackson.module:jackson-module-kotlin")
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
```

Với WebFlux, dùng `spring-boot-starter-webflux` và starter Springdoc WebFlux tương ứng, chẳng hạn `springdoc-openapi-starter-webflux-ui`. Nếu chỉ cần endpoint OpenAPI mà không cần Swagger UI, chọn starter `*-api` phù hợp với stack web.

Spring Boot thường quản lý phiên bản Jackson tương thích qua dependency management. Hãy tránh tự nâng `jackson-module-kotlin` lên một phiên bản khác major/minor với Jackson Databind do Spring Boot quản lý. Các placeholder phiên bản trong ví dụ cần được thay bằng phiên bản tương thích của dự án.

`kotlin("reflect")` cung cấp metadata reflection mà nhiều framework cần để đọc kiểu và constructor Kotlin. `jackson-module-kotlin` bổ sung hỗ trợ serialize/deserialize Kotlin class, bao gồm data class và constructor có tham số mặc định. Springdoc v2 cũng yêu cầu thêm Jackson Kotlin module để hỗ trợ đầy đủ Kotlin types.

`kotlin("plugin.spring")` mở các class Spring được đánh dấu phù hợp để proxy. Plugin này hữu ích cho component/configuration/service Kotlin vì class Kotlin mặc định là `final`; nó không thay thế Jackson Kotlin module và cũng không quyết định schema OpenAPI.

## 2. Data class là DTO phù hợp cho request và response

Kotlin `data class` thường được dùng làm DTO vì primary constructor khai báo trực tiếp các property, còn compiler sinh `equals`, `hashCode`, `toString`, `copy` và component functions.

Ví dụ:

```kotlin
data class CreateCustomerRequest(
    val name: String,
    val email: String,
    val nickname: String? = null,
    val marketingOptIn: Boolean = true
)
```

Jackson Kotlin module có thể tạo object từ primary constructor mà không cần bắt buộc phải có no-argument constructor như cách tiếp cận Java bean cũ. Tên property thường được suy ra từ constructor parameter và Kotlin metadata.

Với request DTO, các property trong primary constructor thường chính là những field client gửi trong JSON. Với response DTO, các property là những field server trả về. Nên tách request và response DTO khi hai chiều có yêu cầu khác nhau, ví dụ request không cho client gửi `id`, trong khi response luôn trả `id`.

```kotlin
data class CustomerResponse(
    val id: Long,
    val name: String,
    val email: String,
    val nickname: String?
)
```

Không nên dùng trực tiếp JPA entity làm request/response model chỉ vì entity cũng là class Kotlin. Entity có thể chứa quan hệ lazy, field nội bộ, proxy hoặc thuộc tính không nên công bố. DTO giúp kiểm soát schema và hợp đồng API rõ hơn.

## 3. Kotlin nullability và OpenAPI nullable

Kotlin biểu diễn nullability ngay trong kiểu:

```kotlin
val displayName: String       // Không nhận null
val nickname: String?        // Có thể nhận null
val age: Int                  // Không nhận null
val secondaryPhone: String?  // Có thể nhận null
```

Springdoc có hỗ trợ Kotlin types. Khi thông tin Kotlin được đọc đúng, thuộc tính nullable có thể được mô tả là nullable trong OpenAPI. Cách biểu diễn cụ thể phụ thuộc phiên bản OpenAPI được xuất:

**OpenAPI 3.0** thường biểu diễn như sau:

```yaml
type: string
nullable: true
```

**OpenAPI 3.1** dùng JSON Schema type union:

```yaml
type:
  - string
  - 'null'
```

`nullable` hoặc union có `null` chỉ nói rằng giá trị `null` được chấp nhận. Nó không tự nói property có thể bị bỏ khỏi JSON hay không. Việc property có bắt buộc xuất hiện hay không được thể hiện bằng danh sách `required` của object schema.

Ví dụ schema có thể vừa yêu cầu `name`, vừa cho phép `nickname` null:

```yaml
type: object
properties:
  name:
    type: string
  nickname:
    type: string
    nullable: true
required:
  - name
```

Trong ví dụ này, `name` phải xuất hiện và không được null; `nickname` có thể bị bỏ qua hoặc được gửi với giá trị null. Nếu muốn `nickname` bắt buộc xuất hiện nhưng giá trị vẫn có thể là null, đưa `nickname` vào `required` và giữ schema nullable. Đây là hai quy tắc độc lập.

## 4. Required property và nullable property không phải một

Bảng sau giúp phân biệt các trường hợp phổ biến:

| Kotlin property | Có thể null? | Có thể bỏ khỏi JSON request? | Ý nghĩa thường dùng |
|---|---:|---:|---|
| `val name: String` | Không | Không | Bắt buộc, giá trị phải khác null |
| `val nickname: String? = null` | Có | Có | Tùy chọn, mặc định null |
| `val pageSize: Int = 20` | Không | Có | Tùy chọn, mặc định 20 |
| `val middleName: String?` | Có | Cần xác định rõ theo deserializer/hợp đồng | Nullable nhưng không có default Kotlin tường minh |

Hai trường hợp đầu tiên thường gặp nhất trong request DTO. `String? = null` cho phép client bỏ field hoặc gửi null; `Int = 20` cho phép client bỏ field nhưng không cho phép gửi null theo null-safety của Kotlin.

Trường hợp `String?` không có default cần được kiểm tra với Jackson module và phiên bản đang dùng. Kotlin yêu cầu argument khi gọi constructor trực tiếp, nhưng Jackson Kotlin module có quy tắc xử lý tham số nullable khi property vắng mặt. Không suy luận requiredness của JSON chỉ từ việc constructor Kotlin không khai báo `= null`; hãy kiểm tra request runtime và OpenAPI được sinh ra.

## 5. Tham số mặc định trong data class

Kotlin cho phép đặt default value ngay trong primary constructor:

```kotlin
data class CreateOrderRequest(
    val productId: Long,
    val quantity: Int = 1,
    val note: String? = null
)
```

Với Jackson Kotlin module, khi property không có trong JSON, constructor có thể sử dụng default value của Kotlin:

| JSON request | Giá trị trong object |
|---|---|
| `{"productId": 501}` | `productId = 501`, `quantity = 1`, `note = null` |
| `{"productId": 501, "quantity": 3}` | `quantity = 3`, `note = null` |
| `{"productId": 501, "note": "Giao buổi sáng"}` | `quantity = 1`, `note = "Giao buổi sáng"` |
| `{"productId": 501, "quantity": null}` | Không hợp lệ với `Int` non-null theo cấu hình null handling mặc định thông thường |
| `{"quantity": 2}` | Thiếu `productId` bắt buộc; không có default để thay thế |

Default value xử lý trường hợp property bị bỏ khỏi JSON. Nó không tự làm property nullable. Ví dụ `quantity: Int = 1` có thể bị bỏ qua, nhưng `quantity: null` vẫn không hợp lệ với kiểu `Int` không nullable.

Jackson Kotlin module có tùy chọn cấu hình liên quan đến cách xử lý explicit `null` đối với tham số có default, chẳng hạn `NullIsSameAsDefault`. Hành vi có thể thay đổi nếu ứng dụng bật tùy chọn này hoặc dùng custom deserializer. Vì vậy, hãy ghi rõ hợp đồng dựa trên cấu hình ObjectMapper thực tế.

## 6. Phân biệt property bị bỏ qua và property được gửi null

Đối với DTO:

```kotlin
data class UpdateProfileRequest(
    val displayName: String,
    val nickname: String? = null,
    val locale: String = "vi-VN"
)
```

Hai request sau có thể tạo cùng giá trị `nickname = null`:

```json
{
  "displayName": "Minh"
}
```

```json
{
  "displayName": "Minh",
  "nickname": null
}
```

Với DTO trên, code sau khi deserialize không thể biết chắc client đã bỏ `nickname` hay đã gửi explicit null, vì cả hai đều trở thành `null`.

Điều này rất quan trọng với PATCH. Nhiều API cần phân biệt:

- Không gửi field: giữ nguyên giá trị hiện tại.
- Gửi field với null: xóa giá trị hiện tại.
- Gửi field với giá trị: cập nhật sang giá trị mới.

Một nullable property mặc định null không biểu diễn được ba trạng thái đó. Có thể dùng wrapper biểu diễn presence, `JsonNode`, custom deserializer hoặc một DTO patch chuyên biệt có trạng thái `Absent`, `Null`, `Value`. Hãy mô tả rõ semantics trong OpenAPI và kiểm thử cả ba trường hợp.

Ví dụ hợp đồng PATCH:

| JSON | Ý nghĩa nghiệp vụ |
|---|---|
| `{}` | Không thay đổi nickname |
| `{"nickname": null}` | Xóa nickname |
| `{"nickname": "Mimi"}` | Đặt nickname thành Mimi |

Không dùng `String? = null` nếu service cần phân biệt trường hợp thứ nhất và thứ hai mà không có thêm cơ chế theo dõi presence.

## 7. Cấu hình Kotlin support trong Springdoc

Springdoc v2 hỗ trợ Kotlin types và có cấu hình bật hỗ trợ Kotlin. Trong các phiên bản hiện hành, `springdoc.enable-kotlin` mặc định được bật. Nếu ứng dụng cần vô hiệu hóa xử lý Kotlin đặc thù vì một lý do tương thích, có thể cấu hình property này; thông thường không cần tắt.

```yaml
springdoc:
  enable-kotlin: true
  nullable-request-parameter-enabled: true
```

`springdoc.nullable-request-parameter-enabled` điều khiển hỗ trợ nullable request parameter trong Kotlin. Giá trị mặc định trong cấu hình Springdoc v2 là `true`. Thuộc tính này liên quan đến request parameter, ví dụ query/path/header parameter, không thay thế việc thiết kế nullability của DTO request body.

Springdoc v2 có property `springdoc.model-converters.kotlin-nullable-property-customizer.enabled` để điều khiển việc đánh dấu Kotlin nullable model property là nullable trong schema. Mặc định là bật trong cấu hình được tài liệu hóa. Nếu phải tắt do tương thích với schema cũ, hãy cân nhắc tác động đến tất cả Kotlin DTO và kiểm tra output sau khi thay đổi.

```yaml
springdoc:
  model-converters:
    kotlin-nullable-property-customizer:
      enabled: true
```

Không sao chép property chỉ có ở phiên bản mới vào ứng dụng Springdoc cũ mà chưa kiểm tra tài liệu phiên bản. Nếu property không được hỗ trợ, Spring Boot có thể bỏ qua cấu hình hoặc báo binding tùy cách thiết lập.

## 8. Dùng annotation với Kotlin use-site target

Kotlin property có thể sinh ra field, getter, setter và constructor parameter trên JVM. Annotation Java có thể được đặt lên một trong các phần tử đó. Vì vậy, khi gắn Swagger annotation hoặc Bean Validation annotation lên property, hãy dùng use-site target tường minh để annotation đến đúng phần tử mà thư viện đọc.

Ví dụ:

```kotlin
import io.swagger.v3.oas.annotations.media.Schema
import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.Size

data class CreateCustomerRequest(
    @field:NotBlank
    @field:Size(max = 80)
    @field:Schema(
        description = "Tên khách hàng",
        example = "Nguyen An"
    )
    val name: String,

    @field:Schema(
        description = "Tên hiển thị tùy chọn; có thể là null",
        example = "An"
    )
    val nickname: String? = null,

    @field:Schema(
        description = "Có nhận thông tin khuyến mại hay không",
        defaultValue = "true",
        requiredMode = Schema.RequiredMode.NOT_REQUIRED
    )
    val marketingOptIn: Boolean = true
)
```

`@field:Schema` gắn annotation lên backing field; `@get:Schema` gắn lên getter. Chọn target phù hợp với thư viện và cách Springdoc/Jackson đọc model. Với DTO data class, dùng `@field:` tường minh là một cách rõ ràng, dễ kiểm tra.

Kotlin 2.2 có thay đổi quy tắc mặc định truyền annotation đến parameter/property/field và cung cấp compiler flag `-Xannotation-default-target=param-property`. Dùng use-site target tường minh giúp tránh phụ thuộc vào quy tắc mặc định của compiler.

Nếu một annotation không xuất hiện trong OpenAPI hoặc validation không chạy, kiểm tra use-site target trước khi thêm customizer. Annotation có thể đã được compiler đặt lên constructor parameter trong khi thư viện đang đọc field/getter, hoặc ngược lại.

## 9. Điều khiển requiredness của schema bằng `@Schema`

Springdoc có thể suy luận schema từ Kotlin metadata, nhưng đôi khi hợp đồng cần được diễn đạt rõ hơn. `@Schema` hỗ trợ `requiredMode` để chỉ định property có bắt buộc hay không.

Ví dụ một property không nullable nhưng có default value:

```kotlin
data class SearchRequest(
    val keyword: String,

    @field:Schema(requiredMode = Schema.RequiredMode.NOT_REQUIRED)
    val pageSize: Int = 20
)
```

Nếu phiên bản Springdoc đang dùng không suy luận default parameter như mong muốn, annotation có thể giúp thể hiện ý định của hợp đồng. Ngược lại, nếu property cần bắt buộc, có thể dùng `requiredMode = Schema.RequiredMode.REQUIRED`.

Tuy nhiên, nullability Kotlin và annotation requiredness có thể được xử lý bởi các model converter khác nhau giữa phiên bản Springdoc/Swagger Core. Một số phiên bản hoặc trường hợp kế thừa có thể có khác biệt khi annotation nằm trên field, getter hay constructor parameter. Không chỉ dựa vào annotation trong source; hãy xác minh schema JSON được sinh ra.

`requiredMode` điều khiển việc property có nằm trong danh sách `required`; nó không thay đổi kiểu Kotlin và không tự làm runtime chấp nhận hoặc từ chối null. Bean Validation, Jackson và logic ứng dụng vẫn quyết định request nào hợp lệ.

## 10. Bean Validation trên data class

Null-safety của Kotlin kiểm soát giá trị null, nhưng không thay thế các ràng buộc nghiệp vụ như chuỗi không rỗng, độ dài, số lượng tối thiểu hoặc định dạng email.

```kotlin
import jakarta.validation.constraints.Email
import jakarta.validation.constraints.Min
import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.Size

data class RegisterAccountRequest(
    @field:NotBlank
    @field:Size(max = 100)
    val fullName: String,

    @field:Email
    val email: String,

    @field:Min(18)
    val age: Int,

    val referralCode: String? = null
)
```

Controller:

```kotlin
import jakarta.validation.Valid
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RestController

@RestController
class AccountController(
    private val accountService: AccountService
) {

    @PostMapping("/api/accounts")
    fun register(
        @Valid @RequestBody request: RegisterAccountRequest
    ): ResponseEntity<AccountResponse> {
        return ResponseEntity.ok(accountService.register(request))
    }
}
```

Với Kotlin, annotation validation thường nên dùng `@field:NotBlank`, `@field:Email`, `@field:Min` để gắn vào field mà Bean Validation đọc. `@Valid` trên tham số controller yêu cầu Spring kích hoạt validation cho request body. Cần dependency `spring-boot-starter-validation`.

Springdoc có thể dùng một số validation annotation để bổ sung schema constraints như `minLength`, `maxLength`, `minimum` hoặc `format`. Nhưng schema validation không thay thế validation runtime; hãy giữ cả annotation và kiểm thử request thực tế.

## 11. Jackson property naming và annotation trên Kotlin data class

Tên JSON có thể khác tên Kotlin property do `@JsonProperty`, naming strategy hoặc `@JsonIgnore`. OpenAPI phải mô tả tên JSON thực tế mà Jackson đọc/ghi.

```kotlin
import com.fasterxml.jackson.annotation.JsonProperty
import io.swagger.v3.oas.annotations.media.Schema

data class CustomerProfile(
    @field:JsonProperty("display_name")
    @field:Schema(description = "Tên hiển thị của khách hàng")
    val displayName: String,

    @field:JsonProperty("phone_number")
    val phoneNumber: String?
)
```

JSON request/response dùng `display_name` và `phone_number`. Khi kiểm tra `/v3/api-docs`, schema properties cũng phải phản ánh các tên JSON đã cấu hình. Nếu tài liệu vẫn hiện `displayName`, hãy kiểm tra Jackson annotation target, naming strategy và phiên bản Springdoc.

Không đưa field nội bộ vào schema nếu Jackson bỏ qua nó:

```kotlin
data class CustomerResponse(
    val id: Long,
    val name: String,
    @field:com.fasterxml.jackson.annotation.JsonIgnore
    val internalNote: String
)
```

Nếu dùng `@JsonIgnore`, `@JsonProperty(access = READ_ONLY/WRITE_ONLY)` hoặc `@JsonInclude`, cần kiểm tra riêng schema request và response. Một model được dùng ở cả hai chiều có thể có semantics khác nhau; DTO riêng thường dễ mô tả hơn.

## 12. Data class request và response có default khác nhau

Default value thường quan trọng nhất ở request body: server dùng default khi client không gửi field. Với response, server thường chủ động tạo object và serialize tất cả field theo cấu hình Jackson; default constructor không nhất thiết là default mà client được phép bỏ qua.

Ví dụ:

```kotlin
data class CreateProductRequest(
    val name: String,
    val active: Boolean = true
)

data class ProductResponse(
    val id: Long,
    val name: String,
    val active: Boolean
)
```

Trong request, `active` có thể bị bỏ qua và server dùng `true`. Trong response, server phải trả `active` theo object đã tạo; client không gửi field này. Dùng DTO riêng giúp OpenAPI mô tả đúng requiredness theo từng hướng.

Nếu response có property nullable:

```kotlin
data class ProductResponse(
    val id: Long,
    val description: String?
)
```

`description` có thể được serialize thành JSON `null` hoặc bị bỏ khỏi JSON nếu Jackson được cấu hình `NON_NULL`. Hai hành vi này khác nhau với client. Hãy kiểm tra cấu hình `ObjectMapper`/`@JsonInclude` và bảo đảm response schema thể hiện đúng cách server phát JSON.

## 13. Request parameter Kotlin nullable và default

Nullability của request parameter như query parameter là một phần khác với nullability của DTO property.

Ví dụ:

```kotlin
import io.swagger.v3.oas.annotations.Parameter
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController

@RestController
class CustomerSearchController(
    private val customerService: CustomerService
) {

    @GetMapping("/api/customers")
    fun search(
        @Parameter(description = "Từ khóa tìm kiếm", required = false)
        @RequestParam(required = false)
        keyword: String?
    ): List<CustomerResponse> {
        return customerService.search(keyword)
    }
}
```

`String?` cho phép biến Kotlin nhận null; `@RequestParam(required = false)` cho Spring MVC biết query parameter có thể vắng mặt. Springdoc có property `springdoc.nullable-request-parameter-enabled` để hỗ trợ nullable request parameter trong Kotlin.

Khi dùng default value ở HTTP parameter, khai báo rõ ở Spring annotation:

```kotlin
@GetMapping("/api/orders")
fun list(
    @RequestParam(defaultValue = "20") size: Int
): List<OrderResponse> = orderService.list(size)
```

`@RequestParam(defaultValue = "20")` là quy tắc bind HTTP parameter của Spring. Nó khác với default argument trong Kotlin function signature. Không giả định một Kotlin default argument tự động tạo query parameter default trong Spring MVC và OpenAPI.

Springdoc FAQ ghi nhận query parameter có `defaultValue` có thể được đánh dấu required trong một số trường hợp suy luận. Nếu hợp đồng cần query parameter optional, kiểm tra document và bổ sung `@Parameter(required = false)` khi phù hợp. Luôn xác minh cả binding runtime và schema.

## 14. Ví dụ hoàn chỉnh: Kotlin data class và OpenAPI schema

DTO:

```kotlin
import io.swagger.v3.oas.annotations.media.Schema
import jakarta.validation.constraints.Min
import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.Size

@Schema(name = "CreateOrderRequest", description = "Thông tin tạo đơn hàng")
data class CreateOrderRequest(
    @field:NotBlank
    @field:Schema(description = "Mã sản phẩm", example = "501")
    val productCode: String,

    @field:Min(1)
    @field:Schema(
        description = "Số lượng; mặc định là 1 nếu không gửi",
        defaultValue = "1",
        requiredMode = Schema.RequiredMode.NOT_REQUIRED
    )
    val quantity: Int = 1,

    @field:Size(max = 200)
    @field:Schema(description = "Ghi chú có thể để trống hoặc null")
    val note: String? = null
)
```

Controller:

```kotlin
import jakarta.validation.Valid
import io.swagger.v3.oas.annotations.Operation
import io.swagger.v3.oas.annotations.media.Content
import io.swagger.v3.oas.annotations.media.Schema
import io.swagger.v3.oas.annotations.responses.ApiResponse
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.ResponseStatus
import org.springframework.web.bind.annotation.RestController

@RestController
class OrderController(
    private val orderService: OrderService
) {

    @PostMapping("/api/orders")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(
        summary = "Tạo đơn hàng",
        responses = [
            ApiResponse(responseCode = "201", description = "Đã tạo đơn hàng"),
            ApiResponse(
                responseCode = "400",
                description = "Request không hợp lệ",
                content = [Content(schema = Schema(implementation = ApiError::class))]
            )
        ]
    )
    fun create(
        @Valid @RequestBody request: CreateOrderRequest
    ): OrderResponse {
        return orderService.create(request)
    }
}
```

Request tối thiểu:

```json
{
  "productCode": "SKU-501"
}
```

Sau khi Jackson tạo object, `quantity` là `1` và `note` là `null`. Request có thể gửi thêm:

```json
{
  "productCode": "SKU-501",
  "quantity": 3,
  "note": "Giao trong giờ hành chính"
}
```

Hợp đồng OpenAPI dự kiến phải thể hiện `productCode` là property bắt buộc, `quantity` không bắt buộc với default `1`, còn `note` nullable và không bắt buộc. Cách serialize nullability có thể là `nullable: true` trong OpenAPI 3.0 hoặc type union chứa `null` trong OpenAPI 3.1.

Nếu output thực tế đánh dấu `quantity` required hoặc không đánh dấu `note` nullable, hãy kiểm tra Springdoc version, Kotlin support, Jackson Kotlin module và annotation use-site target. Không sửa runtime chỉ để khớp schema suy luận sai; trước hết xác định hợp đồng JSON mà endpoint thực sự chấp nhận.

## 15. Kiểm tra JSON runtime và OpenAPI schema

Sau khi ứng dụng chạy, mở `/v3/api-docs` và kiểm tra component schema:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.components.schemas.CreateOrderRequest'
```

Kiểm tra danh sách property bắt buộc:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.components.schemas.CreateOrderRequest.required'
```

Kiểm tra schema của `note`:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.components.schemas.CreateOrderRequest.properties.note'
```

Với OpenAPI 3.0, tìm `nullable: true`. Với OpenAPI 3.1, kiểm tra `type` có chứa `null`. Cũng kiểm tra `required` riêng; không kết luận property optional chỉ vì nó nullable.

Kiểm tra request runtime bằng cURL:

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"productCode":"SKU-501"}'
```

Sau đó thử explicit null cho property non-null:

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"productCode":"SKU-501","quantity":null}'
```

Request thứ hai thường bị từ chối khi Jackson Kotlin module giữ null-safety mặc định. Status cụ thể phụ thuộc exception handler và cấu hình Spring MVC. Hãy ghi nhận response thực tế để tài liệu lỗi 400 phản ánh đúng.

## 16. Kiểm thử default parameter với Jackson Kotlin module

Có thể kiểm thử trực tiếp ObjectMapper mà Spring Boot cấu hình:

```kotlin
import com.fasterxml.jackson.module.kotlin.readValue
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import com.fasterxml.jackson.databind.ObjectMapper

@SpringBootTest
class KotlinRequestDeserializationTest {

    @Autowired
    lateinit var objectMapper: ObjectMapper

    @Test
    fun `missing fields use Kotlin constructor defaults`() {
        val request = objectMapper.readValue<CreateOrderRequest>(
            """{"productCode":"SKU-501"}"""
        )

        assertThat(request.quantity).isEqualTo(1)
        assertThat(request.note).isNull()
    }

    @Test
    fun `explicit null is accepted for nullable property`() {
        val request = objectMapper.readValue<CreateOrderRequest>(
            """{"productCode":"SKU-501","note":null}"""
        )

        assertThat(request.note).isNull()
    }
}
```

Test trên kiểm tra hành vi Jackson thực tế thay vì chỉ kiểm tra Kotlin constructor. Có thể bổ sung test xác nhận `quantity: null` bị từ chối và `productCode` bị thiếu không tạo được request. Nếu ứng dụng tùy biến `ObjectMapper`, các test phải dùng đúng bean runtime đó.

## 17. Kiểm thử hợp đồng OpenAPI cho Kotlin DTO

Nên có contract test để phát hiện khi nâng Springdoc, Kotlin hoặc Jackson khiến requiredness/nullability thay đổi. Ví dụ với MockMvc:

```kotlin
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status

@SpringBootTest
@AutoConfigureMockMvc
class KotlinOpenApiSchemaTest {

    @Autowired
    lateinit var mockMvc: MockMvc

    @Test
    fun `openapi describes Kotlin request model`() {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk)
            .andExpect(
                jsonPath("$.components.schemas.CreateOrderRequest.required")
                    .value(org.hamcrest.Matchers.hasItem("productCode"))
            )
            .andExpect(
                jsonPath("$.components.schemas.CreateOrderRequest.properties.quantity")
                    .exists()
            )
            .andExpect(
                jsonPath("$.components.schemas.CreateOrderRequest.properties.note")
                    .exists()
            )
    }
}
```

Test này kiểm tra các property có mặt và `productCode` nằm trong required list. Có thể bổ sung assertion riêng cho `quantity` không required và `note` nullable; assertion nullability cần hỗ trợ cả OpenAPI 3.0 (`nullable`) lẫn 3.1 (`type` chứa `null`) nếu dự án có thể đổi phiên bản document.

Ngoài schema test, hãy kiểm tra request body thực tế bằng MockMvc/WebTestClient. Schema chỉ mô tả hợp đồng; Jackson và Bean Validation mới quyết định request có deserialize và validate thành công hay không.

## 18. Các điểm dễ nhầm khi nâng cấp Kotlin hoặc Springdoc

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Kotlin data class không deserialize được | Thiếu `jackson-module-kotlin` hoặc Jackson/Kotlin không tương thích | Thêm module và dùng phiên bản do Spring Boot quản lý |
| Nullability không xuất hiện trong schema | Thiếu Kotlin metadata/reflection, converter bị tắt hoặc phiên bản có khác biệt | Kiểm tra `kotlin-reflect`, `springdoc.enable-kotlin` và nullable property customizer |
| Property có default vẫn bị đánh dấu required | Springdoc không suy luận default constructor parameter như kỳ vọng hoặc annotation target sai | Kiểm tra output, dùng `@field:Schema(requiredMode = NOT_REQUIRED)` khi phù hợp |
| Non-null property không bị đánh dấu required | Khác biệt model converter hoặc regression theo phiên bản | Kiểm tra version, test contract và khai báo `requiredMode = REQUIRED` nếu cần |
| `@Schema` không có tác dụng trên Kotlin property | Annotation được gắn vào constructor parameter thay vì field/getter mà thư viện đọc | Dùng `@field:Schema` hoặc `@get:Schema` phù hợp |
| Gửi thiếu field có default bị lỗi | Jackson Kotlin module không được đăng ký hoặc custom ObjectMapper bỏ module | Kiểm tra ObjectMapper thực tế và Jackson module registration |
| Gửi null vào non-null field nhưng được chấp nhận | Jackson được cấu hình null handling/coercion khác mặc định | Xem lại KotlinModule options và contract test |
| PATCH không phân biệt absent với null | DTO dùng nullable property default null | Dùng presence wrapper hoặc custom deserializer |
| OpenAPI property name khác JSON thực tế | `@JsonProperty`, naming strategy hoặc annotation target không được nhận diện | Đồng bộ Jackson metadata và kiểm tra `/v3/api-docs` |
| Response null bị bỏ khỏi JSON | `JsonInclude.NON_NULL` hoặc global inclusion policy | Đồng bộ response schema với JSON serialization thực tế |
| Query parameter nullable bị required | Spring request binding và Springdoc suy luận khác nhau | Khai báo `required = false`, kiểm tra `nullable-request-parameter-enabled` |

## 19. Checklist thiết kế Kotlin DTO cho OpenAPI

- [ ] Đã có `kotlin-reflect` và `jackson-module-kotlin` phù hợp với Spring Boot/Jackson.
- [ ] Dùng data class DTO thay vì phơi trực tiếp entity nếu hợp đồng cần kiểm soát riêng.
- [ ] Dùng `Type` và `Type?` đúng với khả năng nhận null của JSON runtime.
- [ ] Đã phân biệt property nullable với property có thể bị bỏ qua.
- [ ] Default constructor parameter chỉ được xem là optional sau khi kiểm tra Jackson deserialization và OpenAPI output.
- [ ] Đã xác định explicit `null` khác gì với property bị thiếu.
- [ ] Với PATCH, có cơ chế phân biệt absent, null và value nếu nghiệp vụ yêu cầu.
- [ ] Dùng `@field:` hoặc `@get:` cho Swagger/Validation annotations khi cần target rõ ràng.
- [ ] Bean Validation constraints phản ánh đúng quy tắc nghiệp vụ.
- [ ] `@JsonProperty`, `@JsonIgnore`, `@JsonInclude` khớp schema OpenAPI.
- [ ] Request và response DTO tách riêng khi semantics khác nhau.
- [ ] Đã kiểm tra OpenAPI 3.0 `nullable` hoặc OpenAPI 3.1 `type` union chứa null.
- [ ] Đã kiểm tra `required` list độc lập với nullability.
- [ ] Đã test ObjectMapper với property bị thiếu, explicit null và giá trị cụ thể.
- [ ] Đã thêm contract test cho `/v3/api-docs` sau khi nâng Kotlin/Jackson/Springdoc.

Kotlin giúp biểu diễn nullability và default value ngay trong data class, còn Springdoc chuyển thông tin model thành OpenAPI schema. `String?` mô tả khả năng nhận null; constructor default mô tả cách tạo object khi property bị bỏ qua; danh sách `required` mô tả property client bắt buộc phải gửi. Jackson Kotlin module và `kotlin-reflect` giúp runtime hiểu constructor Kotlin, trong khi Springdoc cần được kiểm tra qua `/v3/api-docs` để bảo đảm schema khớp JSON thực tế. Khi thiết kế DTO, annotation target, validation và contract test đều rõ ràng, tài liệu API sẽ mô tả chính xác hơn hành vi của ứng dụng Kotlin.

## Tài liệu tham khảo

- [Springdoc OpenAPI v2 – Kotlin support](https://springdoc.org/v2/#kotlin-support)
- [Springdoc OpenAPI v2 – Configuration properties](https://springdoc.org/v2/properties.html)
- [Spring Boot – Kotlin support](https://docs.spring.io/spring-boot/reference/features/kotlin.html)
- [Jackson Kotlin Module – README](https://github.com/FasterXML/jackson-module-kotlin)
- [Kotlin – Null safety](https://kotlinlang.org/docs/null-safety.html)
- [Kotlin – Classes and constructors](https://kotlinlang.org/docs/classes.html)
- [OpenAPI Specification 3.1 – Schema Object](https://spec.openapis.org/oas/v3.1.1.html#schema-object)
