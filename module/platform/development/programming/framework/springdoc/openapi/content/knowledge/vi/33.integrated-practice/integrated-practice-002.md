# Mô tả DTO có validation, enum, ngày giờ và thuộc tính chỉ đọc

Một OpenAPI schema tốt phải mô tả đúng dữ liệu mà API thực sự nhận và trả về: trường nào bắt buộc, chuỗi dài bao nhiêu, số nằm trong giới hạn nào, giá trị enum nào được chấp nhận, ngày giờ dùng định dạng gì và thuộc tính nào chỉ do server tạo. Với Spring Boot, có thể kết hợp Jakarta Bean Validation, kiểu dữ liệu Java, Jackson và Swagger annotations để Springdoc sinh schema cho các DTO.

Bài thực hành này xây dựng một API tạo đơn hàng. Request có email, số lượng, mức ưu tiên, ngày giao dự kiến, thời điểm yêu cầu và địa chỉ giao hàng. Response bổ sung mã đơn hàng, trạng thái và thời điểm tạo do server quản lý. Sau khi khai báo DTO, ta kiểm tra cả validation runtime lẫn OpenAPI document để bảo đảm hai phía mô tả cùng một hợp đồng.

## 1. Chuẩn bị dependency

Ví dụ dùng Spring Boot 3, Java 17 trở lên, Spring MVC và Springdoc v2. Cần có starter validation để Jakarta Bean Validation thực sự chạy, cùng Springdoc starter phù hợp với ứng dụng.

Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

Nếu chỉ cần endpoint OpenAPI JSON/YAML và không cần giao diện Swagger UI, có thể thay starter `webmvc-ui` bằng `springdoc-openapi-starter-webmvc-api`. Với ứng dụng WebFlux, dùng starter WebFlux tương ứng.

## 2. Chọn DTO request và response riêng

Trong API thực tế, nên tách DTO nhận dữ liệu và DTO trả dữ liệu. Request chỉ chứa các trường client được phép gửi; response có thể chứa mã định danh, trạng thái xử lý, thời điểm tạo hoặc dữ liệu được server tính toán.

Ví dụ:

| DTO | Vai trò | Trường điển hình |
|---|---|---|
| `CreateOrderRequest` | Dữ liệu client gửi để tạo đơn | Email, số lượng, ưu tiên, ngày giao, địa chỉ |
| `OrderResponse` | Dữ liệu server trả về | ID, dữ liệu đơn hàng, trạng thái, thời điểm tạo |

Không đưa `id`, `createdAt` hoặc `updatedAt` vào request chỉ để dùng chung một class. Việc tách DTO giúp schema request không vô tình cho client gửi dữ liệu do server quản lý. Nếu hệ thống buộc phải dùng chung DTO, cần mô tả và thực thi quyền đọc/ghi riêng cho thuộc tính như phần read-only bên dưới.

## 3. Định nghĩa enum cho giá trị có tập lựa chọn cố định

Enum giúp giới hạn giá trị hợp lệ trong Java và cho Springdoc biết schema chỉ chấp nhận một tập giá trị.

```java
package com.example.orders.api.dto;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "OrderPriority",
    description = "Mức ưu tiên xử lý đơn hàng"
)
public enum OrderPriority {
    STANDARD,
    EXPRESS,
    ECONOMY
}
```

Khi dùng enum Java thông thường, Springdoc thường sinh schema kiểu `string` với danh sách `enum` tương ứng:

```yaml
OrderPriority:
  type: string
  description: Mức ưu tiên xử lý đơn hàng
  enum:
    - STANDARD
    - EXPRESS
    - ECONOMY
```

Nếu muốn enum được tái sử dụng thành component schema có tên riêng, Springdoc FAQ hướng dẫn dùng `@Schema(enumAsRef = true)` trên enum:

```java
@Schema(name = "OrderPriority", enumAsRef = true)
public enum OrderPriority {
    STANDARD,
    EXPRESS,
    ECONOMY
}
```

Nếu Jackson serialize enum thành chuỗi khác tên hằng số, ví dụ `"standard"` thay cho `"STANDARD"`, OpenAPI schema phải phản ánh đúng giá trị JSON thực tế. Khi dùng `@JsonValue`, `@JsonCreator` hoặc custom serializer, hãy kiểm tra document được Springdoc sinh ra và thử serialize/deserialise DTO bằng ObjectMapper của ứng dụng.

## 4. Định nghĩa DTO địa chỉ với Bean Validation

Địa chỉ là object lồng trong request. Dùng `@Valid` để kích hoạt validation đệ quy trên các trường con.

```java
package com.example.orders.api.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

@Schema(name = "ShippingAddressRequest", description = "Địa chỉ nhận hàng")
public record ShippingAddressRequest(

    @Schema(description = "Tên người nhận", example = "Nguyen Van An")
    @NotBlank
    @Size(max = 120)
    String recipient,

    @Schema(description = "Địa chỉ dòng 1", example = "12 Nguyen Hue")
    @NotBlank
    @Size(max = 200)
    String addressLine1,

    @Schema(description = "Mã bưu chính", example = "700000")
    @NotBlank
    @Pattern(regexp = "^[0-9]{5,10}$")
    String postalCode,

    @Schema(description = "Mã quốc gia ISO 3166-1 alpha-2", example = "VN")
    @NotBlank
    @Pattern(regexp = "^[A-Z]{2}$")
    String countryCode
) {
}
```

Các constraint thường dùng:

| Constraint | Ý nghĩa | Schema có thể được mô tả |
|---|---|---|
| `@NotNull` | Giá trị không được null | Property nằm trong `required` |
| `@NotBlank` | Chuỗi không null, không rỗng và có ký tự không phải whitespace | `required`, thường kèm giới hạn tối thiểu phù hợp |
| `@NotEmpty` | Chuỗi/collection/map không được rỗng | `minLength: 1`, `minItems: 1` hoặc `minProperties: 1` tùy kiểu |
| `@Size(min, max)` | Giới hạn kích thước chuỗi, collection hoặc map | `minLength`/`maxLength`, `minItems`/`maxItems` hoặc `minProperties`/`maxProperties` |
| `@Pattern` | Giá trị phải khớp regular expression | `pattern` |
| `@Email` | Giá trị phải có dạng email theo validator | Có thể thể hiện `format: email` |
| `@Min`, `@Max` | Giới hạn số nguyên | `minimum`, `maximum` |
| `@Positive`, `@PositiveOrZero` | Số dương hoặc không âm | Ràng buộc minimum tương ứng |
| `@DecimalMin`, `@DecimalMax` | Giới hạn số thập phân, có thể exclusive | `minimum`/`maximum` hoặc `exclusiveMinimum`/`exclusiveMaximum` |
| `@Past`, `@Future` | Thời điểm phải ở quá khứ hoặc tương lai | Constraint runtime; cần mô tả ý nghĩa thời gian trong schema nếu consumer cần biết |

Khả năng chuyển constraint thành OpenAPI keyword phụ thuộc Springdoc, Swagger Core và phiên bản Bean Validation. Bean Validation là quy tắc thực thi ở server; OpenAPI schema là mô tả hợp đồng. Không giả định mọi constraint runtime đều được chuyển thành một keyword OpenAPI tương đương hoàn hảo.

## 5. Định nghĩa request DTO có validation, enum và ngày giờ

```java
package com.example.orders.api.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.FutureOrPresent;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

import java.time.LocalDate;
import java.time.OffsetDateTime;

@Schema(name = "CreateOrderRequest", description = "Dữ liệu tạo đơn hàng")
public record CreateOrderRequest(

    @Schema(
        description = "Email nhận thông báo về đơn hàng",
        example = "buyer@example.com",
        format = "email"
    )
    @NotBlank
    @Email
    @Size(max = 254)
    String customerEmail,

    @Schema(description = "Số lượng sản phẩm", example = "2", minimum = "1", maximum = "1000")
    @NotNull
    @Positive
    @Max(1000)
    Integer quantity,

    @Schema(description = "Mức ưu tiên xử lý")
    @NotNull
    OrderPriority priority,

    @Schema(
        description = "Ngày giao dự kiến theo lịch địa phương, không chứa múi giờ",
        type = "string",
        format = "date",
        example = "2099-12-05"
    )
    @NotNull
    @FutureOrPresent
    LocalDate expectedDeliveryDate,

    @Schema(
        description = "Thời điểm client gửi yêu cầu, có offset múi giờ",
        type = "string",
        format = "date-time",
        example = "2099-12-01T09:30:00+07:00"
    )
    @NotNull
    OffsetDateTime requestedAt,

    @Schema(description = "Địa chỉ nhận hàng")
    @NotNull
    @Valid
    ShippingAddressRequest shippingAddress
) {
}
```

Trong ví dụ:

- `customerEmail` là chuỗi bắt buộc, có định dạng email và giới hạn độ dài.
- `quantity` là số nguyên bắt buộc, lớn hơn 0 và không vượt quá 1000.
- `priority` chỉ nhận một trong các giá trị của `OrderPriority`.
- `expectedDeliveryDate` là ngày lịch, không mang giờ hoặc múi giờ.
- `requestedAt` là thời điểm có offset, ví dụ `+07:00`.
- `shippingAddress` là object bắt buộc; `@Valid` kích hoạt kiểm tra các trường địa chỉ.

`@NotNull` và `@NotBlank` giúp validation runtime từ chối giá trị không hợp lệ khi controller dùng `@Valid`. `@Schema` bổ sung mô tả, example và format cho OpenAPI; nó không thay thế Bean Validation.

## 6. Phân biệt `LocalDate`, `LocalDateTime`, `OffsetDateTime` và `Instant`

Chọn kiểu thời gian theo ý nghĩa dữ liệu, không chỉ theo định dạng chuỗi.

| Java type | Ý nghĩa | OpenAPI format thường dùng | Ví dụ JSON |
|---|---|---|---|
| `LocalDate` | Ngày lịch, không có giờ/múi giờ | `date` | `"2026-12-05"` |
| `LocalTime` | Giờ trong ngày, không có ngày/múi giờ | `string`; `time` có thể dùng như format mở rộng nếu tool hỗ trợ | `"09:30:00"` |
| `LocalDateTime` | Ngày và giờ địa phương, không có offset | Thường được mô tả là `date-time`, cần chú thích rõ semantics | `"2026-12-05T09:30:00"` |
| `OffsetDateTime` | Ngày giờ kèm UTC offset | `date-time` | `"2026-12-05T09:30:00+07:00"` |
| `Instant` | Một thời điểm tuyệt đối trên UTC timeline | `date-time` | `"2026-12-05T02:30:00Z"` |

`LocalDateTime` không chứa timezone hoặc offset. Dù công cụ có thể sinh `format: date-time`, giá trị đó không tự trở thành timestamp RFC 3339 có offset. Nếu API trao đổi thời điểm tuyệt đối giữa nhiều múi giờ, ưu tiên `OffsetDateTime` hoặc `Instant`.

Với ngày giao dự kiến, ngày sinh hoặc ngày hiệu lực chỉ có ý nghĩa theo lịch, `LocalDate` thường phù hợp hơn `Date` hoặc `OffsetDateTime`. Không thêm timezone vào dữ liệu vốn không có ý nghĩa thời điểm.

## 7. Phân biệt `@JsonFormat` và `@DateTimeFormat`

Hai annotation phục vụ hai luồng binding khác nhau:

| Annotation | Dùng cho | Ví dụ |
|---|---|---|
| `@JsonFormat` | Jackson serialize/deserialise JSON body | `@JsonFormat(pattern = "yyyy-MM-dd")` |
| `@DateTimeFormat` | Spring bind query parameter, path variable hoặc form value | `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` |
| `@Schema` | Mô tả kiểu, format và example trong OpenAPI | `@Schema(type = "string", format = "date")` |

Ví dụ query parameter ngày:

```java
@GetMapping("/api/orders")
List<OrderResponse> search(
    @RequestParam
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    LocalDate fromDate
) {
    return orderService.searchFrom(fromDate);
}
```

Ví dụ JSON property:

```java
public record DeliveryWindow(
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
    LocalDate deliveryDate
) {
}
```

Nếu dùng pattern tùy chỉnh, schema OpenAPI phải phản ánh đúng wire format thực tế. Một `format: date-time` không mô tả đầy đủ mọi pattern tùy chỉnh; hãy thêm `description` và `example`, đồng thời kiểm tra request/response JSON thực tế.

## 8. Định nghĩa enum trạng thái và response DTO

Trạng thái đơn hàng do server quản lý:

```java
package com.example.orders.api.dto;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "OrderStatus", description = "Trạng thái xử lý đơn hàng")
public enum OrderStatus {
    NEW,
    CONFIRMED,
    PROCESSING,
    SHIPPED,
    CANCELLED
}
```

Response DTO có các thuộc tính do server tạo:

```java
package com.example.orders.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.UUID;

@Schema(name = "OrderResponse", description = "Thông tin đơn hàng trả về từ server")
public record OrderResponse(

    @Schema(
        description = "Mã định danh đơn hàng do server cấp",
        accessMode = Schema.AccessMode.READ_ONLY,
        example = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    )
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    UUID id,

    @Schema(description = "Email khách hàng", format = "email")
    String customerEmail,

    @Schema(description = "Số lượng sản phẩm", example = "2")
    Integer quantity,

    OrderPriority priority,

    OrderStatus status,

    @Schema(type = "string", format = "date", example = "2026-12-05")
    LocalDate expectedDeliveryDate,

    @Schema(
        type = "string",
        format = "date-time",
        example = "2026-12-01T09:30:00+07:00"
    )
    OffsetDateTime requestedAt,

    @Schema(
        description = "Thời điểm server tạo đơn hàng theo UTC",
        accessMode = Schema.AccessMode.READ_ONLY,
        type = "string",
        format = "date-time",
        example = "2026-12-01T02:30:01Z"
    )
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    Instant createdAt
) {
}
```

`OrderResponse` dùng enum `OrderPriority` và `OrderStatus`, ngày lịch `LocalDate`, thời điểm có offset `OffsetDateTime` và thời điểm UTC `Instant`. Các trường `id` và `createdAt` được đánh dấu read-only.

## 9. Phân biệt OpenAPI `readOnly` và Jackson `READ_ONLY`

Hai annotation có mục đích khác nhau và không nên nhầm lẫn:

| Annotation | Tác động |
|---|---|
| `@Schema(accessMode = Schema.AccessMode.READ_ONLY)` | Đánh dấu property là chỉ đọc trong OpenAPI schema để consumer biết property thuộc response direction |
| `@JsonProperty(access = JsonProperty.Access.READ_ONLY)` | Cho Jackson serialize property ra JSON nhưng không nhận giá trị property đó khi deserialize JSON đầu vào |

OpenAPI `readOnly` là metadata mô tả hướng sử dụng của schema. Nó không tự ngăn controller nhận một giá trị do client gửi. Jackson `READ_ONLY` điều khiển quá trình deserialize/serialize ở runtime, nhưng cũng không thay thế authorization hoặc kiểm tra quyền trong service.

Với API thực tế, cách an toàn và dễ hiểu nhất vẫn là dùng request DTO riêng không có `id` hoặc `createdAt`, và response DTO có các trường này. Nếu vì lý do tương thích phải dùng chung một DTO, kết hợp `@Schema(accessMode = READ_ONLY)` để mô tả hợp đồng và `@JsonProperty(access = READ_ONLY)` để Jackson không bind giá trị từ request. Sau đó viết test chứng minh client không thể ghi đè thuộc tính server quản lý.

OpenAPI 3.0 quy định property `readOnly: true` có thể xuất hiện trong response và không nên được gửi trong request; nếu property read-only nằm trong `required`, yêu cầu đó áp dụng cho response. Trong OpenAPI 3.1, `readOnly` được xử lý như annotation của JSON Schema; việc validator có từ chối property trong request hay không phụ thuộc cách validator áp dụng hướng đọc/ghi. Vì vậy, không dùng `readOnly` làm cơ chế bảo mật.

## 10. Kết hợp `@Valid` ở controller

Controller phải yêu cầu Spring thực thi Bean Validation trên request body:

```java
package com.example.orders.api;

import com.example.orders.api.dto.CreateOrderRequest;
import com.example.orders.api.dto.OrderResponse;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    OrderResponse create(@Valid @RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
```

`@Valid` yêu cầu Bean Validation kiểm tra request DTO sau khi Jackson deserialize JSON. `@Valid` trên `shippingAddress` trong record kích hoạt validation lồng nhau. Nếu thiếu `spring-boot-starter-validation`, các annotation có thể vẫn biên dịch nhưng không có provider để thực thi validation.

Với constraint đặt trên method parameter như `@RequestParam @Min(1) int page`, có thể cần method validation qua `@Validated` và cấu hình phù hợp với phiên bản Spring Boot/Spring Framework. Đừng nhầm validation của query/path parameter với validation của `@RequestBody`.

## 11. Kiểm tra OpenAPI schema được Springdoc sinh ra

Khởi động ứng dụng rồi tải document:

```bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output openapi.json
```

Kiểm tra request schema:

```bash
jq '.components.schemas.CreateOrderRequest' openapi.json
```

Kiểm tra enum:

```bash
jq '.components.schemas.OrderPriority' openapi.json
jq '.components.schemas.OrderStatus' openapi.json
```

Kiểm tra response read-only properties:

```bash
jq '.components.schemas.OrderResponse.properties.id' openapi.json
jq '.components.schemas.OrderResponse.properties.createdAt' openapi.json
```

Kết quả mong đợi về mặt semantics:

- `customerEmail` có kiểu string, định dạng email và giới hạn độ dài.
- `quantity` là integer có giới hạn dưới/trên.
- `priority` và `status` có danh sách enum.
- `expectedDeliveryDate` là string format `date`.
- `requestedAt` và `createdAt` là string format `date-time`.
- `id` và `createdAt` được đánh dấu `readOnly` trong response schema.
- Các property bắt buộc xuất hiện trong `required` theo validation và cấu hình schema.

Tên component có thể khác nếu Springdoc đặt tên theo generic type hoặc model converter. Dùng `@Schema(name = "...")` khi cần tên schema ổn định. Không chỉ kiểm tra Swagger UI; hãy xem JSON/YAML raw để xác minh `required`, `enum`, `format`, `pattern`, `minimum`, `maximum` và `readOnly`.

## 12. Kiểm thử validation runtime

Một test gửi request hợp lệ:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerValidationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void acceptsValidOrderRequest() throws Exception {
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerEmail": "buyer@example.com",
                      "quantity": 2,
                      "priority": "EXPRESS",
                      "expectedDeliveryDate": "2099-12-05",
                      "requestedAt": "2099-12-01T09:30:00+07:00",
                      "shippingAddress": {
                        "recipient": "Nguyen Van An",
                        "addressLine1": "12 Nguyen Hue",
                        "postalCode": "700000",
                        "countryCode": "VN"
                      }
                    }
                    """))
            .andExpect(status().isCreated());
    }
}
```

Test request không hợp lệ:

```java
@Test
void rejectsInvalidOrderRequest() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "customerEmail": "not-an-email",
                  "quantity": 0,
                  "priority": "EXPRESS",
                  "expectedDeliveryDate": "2020-01-01",
                  "requestedAt": "2026-12-01T09:30:00+07:00",
                  "shippingAddress": {
                    "recipient": "",
                    "addressLine1": "12 Nguyen Hue",
                    "postalCode": "ABC",
                    "countryCode": "Viet Nam"
                  }
                }
                """))
        .andExpect(status().isBadRequest());
}
```

Ví dụ trên giả định ứng dụng dùng xử lý lỗi mặc định của Spring MVC cho `MethodArgumentNotValidException`. Nếu có `@ControllerAdvice` tùy chỉnh, status và error body có thể khác; hãy viết assertion theo error contract thực tế của ứng dụng.

## 13. Kiểm thử thuộc tính read-only

Nếu DTO response có thể được dùng lại làm request, kiểm tra Jackson không nhận giá trị `id` từ JSON:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import org.junit.jupiter.api.Test;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class ReadOnlyDtoTest {

    public record SharedOrderDto(
        @Schema(accessMode = Schema.AccessMode.READ_ONLY)
        @JsonProperty(access = JsonProperty.Access.READ_ONLY)
        UUID id,
        String customerEmail
    ) {
    }

    @Test
    void ignoresClientSuppliedReadOnlyId() throws Exception {
        ObjectMapper objectMapper = new ObjectMapper()
            .findAndRegisterModules();

        SharedOrderDto dto = objectMapper.readValue("""
            {
              "id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
              "customerEmail": "buyer@example.com"
            }
            """, SharedOrderDto.class);

        assertThat(dto.id()).isNull();

        UUID serverId = UUID.fromString("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11");
        String responseJson = objectMapper.writeValueAsString(
            new SharedOrderDto(serverId, "buyer@example.com")
        );
        assertThat(responseJson).contains(serverId.toString());
    }
}
```

Đây là test cho Jackson `@JsonProperty(access = READ_ONLY)`, không phải test cho `@Schema(accessMode = READ_ONLY)`. Với DTO request/response tách riêng, test nên xác nhận request DTO không có property server-managed ngay từ thiết kế, và response DTO trả đúng giá trị được service tạo.

Không coi việc Jackson bỏ qua property là kiểm tra quyền truy cập đầy đủ. Service vẫn phải tự sinh ID, thời gian tạo và trạng thái; không tin dữ liệu do client cung cấp cho những trường này.

## 14. Các lỗi thường gặp khi mô tả DTO

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Swagger UI không đánh dấu trường bắt buộc | Thiếu `@NotNull`/`@NotBlank`, hoặc schema customizer ghi đè | Kiểm tra `required` trong raw OpenAPI; dùng `requiredMode` nếu cần mô tả tường minh |
| Validation không chạy dù có annotation | Thiếu `spring-boot-starter-validation` hoặc controller thiếu `@Valid` | Kiểm tra provider và annotation tại tham số request body |
| DTO lồng nhau không được validate | Thiếu `@Valid` trên property lồng | Thêm `@Valid` cùng `@NotNull`/`@NotEmpty` phù hợp |
| Enum trong Swagger khác JSON thực tế | Jackson dùng `@JsonValue` hoặc custom serializer | Kiểm tra wire value và OpenAPI enum cùng nhau |
| Ngày giờ bị lệch múi giờ | Dùng `LocalDateTime` cho một thời điểm tuyệt đối | Dùng `OffsetDateTime` hoặc `Instant` |
| `format: date-time` nhưng giá trị không có offset | `LocalDateTime` được mô tả như date-time | Nêu rõ semantics hoặc đổi kiểu có offset |
| `@DateTimeFormat` không đổi JSON body | Annotation dành cho Spring conversion, không phải Jackson body | Dùng `@JsonFormat` hoặc cấu hình ObjectMapper |
| Property read-only vẫn nhận dữ liệu client | Chỉ có `@Schema(accessMode=READ_ONLY)` | Tách request DTO hoặc dùng Jackson `@JsonProperty(READ_ONLY)` và test |
| Property bị ẩn khỏi schema | Dùng nhầm `@Schema(hidden = true)` | Dùng `accessMode` cho read-only; chỉ dùng `hidden` khi muốn loại khỏi docs |
| `@Schema` có example nhưng runtime reject | Example không thỏa constraint hoặc format thật | Đồng bộ example với Bean Validation và Jackson |
| Schema component có tên không ổn định | Tên model tự sinh hoặc generic DTO | Đặt `@Schema(name = "...")` cho contract cần ổn định |

## 15. Quy trình thiết kế và kiểm tra DTO

Thực hiện theo thứ tự:

1. Xác định dữ liệu client được phép gửi và dữ liệu server tạo.
2. Tách request DTO khỏi response DTO nếu hai hướng có trường khác nhau.
3. Chọn kiểu Java phù hợp với semantics: số, enum, ngày lịch, thời điểm UTC hoặc thời điểm có offset.
4. Đặt Bean Validation constraints để bảo vệ runtime.
5. Dùng `@Valid` cho object lồng và collection phần tử cần validate.
6. Dùng `@Schema` để bổ sung tên, mô tả, example, format, enum và access mode.
7. Dùng Jackson annotations khi cần kiểm soát JSON wire format hoặc quyền serialize/deserialize.
8. Tải `/v3/api-docs` và kiểm tra `required`, `enum`, `format`, constraints và `readOnly`.
9. Viết test cho request hợp lệ, request không hợp lệ và thuộc tính server-managed.
10. Chạy OpenAPI parser/linter để phát hiện document không hợp lệ trước khi phát hành.

## 16. Checklist hoàn thiện DTO OpenAPI

- [ ] Request DTO chỉ có các property client được phép gửi.
- [ ] Response DTO có thể chứa ID, status và timestamp do server quản lý.
- [ ] `@NotNull`, `@NotBlank`, `@Size`, `@Pattern`, numeric constraints được chọn đúng semantics.
- [ ] Controller dùng `@Valid` cho request body.
- [ ] Nested DTO có `@Valid` để validation chạy đệ quy.
- [ ] Enum schema phản ánh đúng giá trị JSON được serialize.
- [ ] `LocalDate` được dùng cho ngày lịch.
- [ ] `OffsetDateTime` hoặc `Instant` được dùng cho thời điểm tuyệt đối.
- [ ] `LocalDateTime` không bị mô tả nhầm là timestamp có timezone.
- [ ] `@JsonFormat`, `@DateTimeFormat` và `@Schema` được dùng đúng mục đích.
- [ ] Property server-managed được đánh dấu `readOnly` trong OpenAPI.
- [ ] Jackson được cấu hình để không nhận giá trị read-only nếu DTO có thể dùng cho input.
- [ ] Raw OpenAPI document được kiểm tra `required`, `enum`, `format`, bounds và `readOnly`.
- [ ] Có test request hợp lệ, không hợp lệ và test bảo vệ ID/timestamp do server tạo.

Một DTO tốt phải đồng thời đúng ở ba lớp: kiểu Java thể hiện đúng semantics dữ liệu, Bean Validation bảo vệ request runtime, và OpenAPI schema mô tả chính xác hợp đồng cho consumer. Dùng enum cho tập giá trị hữu hạn, `LocalDate` cho ngày lịch, `OffsetDateTime`/`Instant` cho thời điểm, `@Valid` cho object lồng và `@Schema` để mô tả example/format/read-only. Tách request và response DTO khi có thể; nếu dùng chung, phối hợp OpenAPI `readOnly` với Jackson access control và kiểm thử hành vi deserialize thực tế.

## Tài liệu tham khảo

- [Springdoc OpenAPI v2 – FAQ](https://springdoc.org/v2/faq.html)
- [Swagger Core – `@Schema` annotation](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/io/swagger/v3/oas/annotations/media/Schema.html)
- [Jakarta Bean Validation – Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jackson – `JsonProperty.Access`](https://fasterxml.github.io/jackson-annotations/javadoc/2.17/com/fasterxml/jackson/annotation/JsonProperty.Access.html)
- [OpenAPI Specification 3.0 – Schema Object](https://spec.openapis.org/oas/v3.0.3.html#schema-object)
- [OpenAPI Specification 3.1 – Schema Object](https://spec.openapis.org/oas/v3.1.1.html#schema-object)
