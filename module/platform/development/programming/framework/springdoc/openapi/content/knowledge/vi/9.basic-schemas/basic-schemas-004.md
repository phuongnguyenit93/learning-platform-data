# Số nguyên, số thực, Boolean, chuỗi và kiểu bất kỳ

Schema mô tả kiểu dữ liệu và các giá trị hợp lệ của request hoặc response trong hợp đồng OpenAPI. Khi dùng springdoc-openapi, schema thường được suy ra từ kiểu Java trong controller và DTO, sau đó có thể bổ sung bằng annotation Swagger như <code>@Schema</code>, ràng buộc Bean Validation hoặc cấu hình OpenAPI.

Những kiểu cơ bản xuất hiện thường xuyên nhất là số nguyên, số thực, Boolean và chuỗi. Ngoài ra, một số API nhận dữ liệu JSON linh hoạt mà chưa thể cố định cấu trúc; trường hợp đó cần mô tả rõ schema có kiểu bất kỳ hay là một object có các thuộc tính động.

## 1. Kiểu dữ liệu trong OpenAPI

Schema Object dùng thuộc tính <code>type</code> để mô tả kiểu dữ liệu. Với các kiểu cơ bản, những giá trị thường gặp là:

| type | Ý nghĩa | Ví dụ JSON |
|---|---|---|
| <code>integer</code> | Số nguyên, không có phần thập phân | <code>42</code> |
| <code>number</code> | Số có thể có phần thập phân | <code>19.95</code> |
| <code>boolean</code> | Giá trị logic | <code>true</code>, <code>false</code> |
| <code>string</code> | Chuỗi ký tự | <code>"Spring Boot"</code> |
| Không khai báo <code>type</code> | Không giới hạn vào một kiểu JSON cụ thể | Bất kỳ giá trị JSON hợp lệ |

<code>format</code> có thể bổ sung thông tin cụ thể cho một kiểu, ví dụ <code>int64</code> cho số nguyên 64 bit hoặc <code>date-time</code> cho chuỗi ngày giờ. <code>format</code> không thay thế <code>type</code>: một schema ngày giờ vẫn có <code>type: string</code>.

Các ví dụ JSON thể hiện kiểu dữ liệu trực tiếp. Số và Boolean không đặt trong dấu nháy kép; chuỗi phải đặt trong dấu nháy kép. Ví dụ <code>25</code> là số, còn <code>"25"</code> là chuỗi.

## 2. Số nguyên: integer

Dùng <code>type: integer</code> khi giá trị không có phần thập phân, chẳng hạn số lượng, số trang, tuổi hoặc số lần thử:

~~~yaml
type: integer
format: int32
minimum: 0
maximum: 1000
example: 25
~~~

Các thuộc tính thường dùng:

- <code>format: int32</code>: gợi ý số nguyên có dấu 32 bit.
- <code>format: int64</code>: gợi ý số nguyên có dấu 64 bit.
- <code>minimum</code> và <code>maximum</code>: giới hạn dưới và trên, mặc định là bao gồm biên.
- <code>exclusiveMinimum</code> và <code>exclusiveMaximum</code>: quy định giới hạn loại trừ biên theo phiên bản OAS tương ứng.
- <code>multipleOf</code>: yêu cầu giá trị là bội số của một số đã cho.

### 2.1. int32 và int64

OpenAPI thường dùng hai format sau để mô tả kích thước số nguyên:

| Schema | Miền giá trị số nguyên có dấu |
|---|---:|
| <code>integer / int32</code> | -2.147.483.648 đến 2.147.483.647 |
| <code>integer / int64</code> | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |

Trong Java, <code>int</code> và <code>Integer</code> thường tương ứng với số nguyên 32 bit; <code>long</code> và <code>Long</code> thường tương ứng với số nguyên 64 bit. <code>BigInteger</code> có thể biểu diễn số nguyên lớn hơn miền của <code>int64</code>; không nên gắn format <code>int64</code> nếu API thực sự cho phép giá trị vượt giới hạn đó.

Format giúp công cụ hiểu ý định của schema, nhưng mức kiểm tra cụ thể phụ thuộc validator và code generator. Nếu miền giá trị là một phần của hợp đồng, hãy khai báo giới hạn bằng <code>minimum</code>/<code>maximum</code> và kiểm tra cả validation runtime.

### 2.2. Khai báo số nguyên trong DTO

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

public record InventoryRequest(
    @Schema(
        description = "Số lượng sản phẩm trong kho",
        type = "integer",
        format = "int32",
        example = "25",
        minimum = "0",
        maximum = "1000"
    )
    @Min(0)
    @Max(1000)
    Integer quantity
) {}
~~~

springdoc đọc kiểu Java và annotation để tạo schema. Trong ví dụ, <code>Integer</code> biểu thị kiểu số nguyên; <code>@Schema</code> mô tả định dạng và ví dụ trong tài liệu; <code>@Min</code> và <code>@Max</code> thực thi giới hạn khi Bean Validation được kích hoạt.

<code>@Schema</code> không thay thế validation runtime. Nếu chỉ khai báo <code>minimum</code> trong tài liệu mà controller không kiểm tra dữ liệu, client vẫn có thể gửi giá trị ngoài giới hạn.

## 3. Số thực: number

Dùng <code>type: number</code> cho dữ liệu có thể chứa phần thập phân như nhiệt độ, tỷ lệ hoặc giá trị đo:

~~~yaml
type: number
format: double
minimum: 0
maximum: 100
multipleOf: 0.01
example: 19.95
~~~

Các format phổ biến:

| Format | Ý nghĩa thường dùng |
|---|---|
| <code>float</code> | Số dấu phẩy động độ chính xác đơn |
| <code>double</code> | Số dấu phẩy động độ chính xác kép |

Trong Java, <code>float</code>/<code>Float</code> thường tương ứng với <code>number / float</code>; <code>double</code>/<code>Double</code> thường tương ứng với <code>number / double</code>. <code>BigDecimal</code> biểu diễn số thập phân với độ chính xác tùy kích thước và scale; thường nên mô tả là <code>number</code> mà không gắn format dấu phẩy động nếu muốn giữ ý nghĩa thập phân chính xác.

Với tiền tệ hoặc phép tính tài chính, nên dùng <code>BigDecimal</code> trong Java và quy định rõ số chữ số thập phân, quy tắc làm tròn cùng giới hạn giá trị. Kiểu <code>double</code> dùng biểu diễn nhị phân dấu phẩy động nên một số số thập phân quen thuộc không thể biểu diễn chính xác.

### 3.1. Ví dụ BigDecimal

~~~java
import java.math.BigDecimal;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMin;

public record PriceRequest(
    @Schema(
        description = "Giá sản phẩm theo đơn vị tiền tệ của API",
        type = "number",
        example = "199.90",
        minimum = "0"
    )
    @DecimalMin("0.00")
    BigDecimal price
) {}
~~~

Schema thể hiện giá là một số, không phải chuỗi chứa ký tự số. Giá trị JSON đúng có dạng <code>{"price": 199.90}</code>; dạng <code>{"price": "199.90"}</code> là chuỗi và không khớp schema số.

## 4. Boolean

Boolean chỉ có hai giá trị <code>true</code> và <code>false</code>. Trong OpenAPI, dùng:

~~~yaml
type: boolean
example: true
~~~

Trong Java, kiểu <code>boolean</code> và wrapper <code>Boolean</code> đều ánh xạ thành schema Boolean. Khác biệt quan trọng nằm ở khả năng biểu diễn null trong Java: primitive <code>boolean</code> không thể chứa null, còn <code>Boolean</code> có thể.

Ví dụ DTO:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

public record NotificationRequest(
    @Schema(
        description = "Có bật thông báo qua email hay không",
        example = "true"
    )
    Boolean emailEnabled
) {}
~~~

Boolean không có format riêng. Không mô tả giá trị Boolean bằng chuỗi như <code>"true"</code> hoặc <code>"false"</code> trừ khi hợp đồng thực sự yêu cầu kiểu string.

Nếu thuộc tính là tùy chọn, cần quy định hành vi khi client bỏ qua nó. Ví dụ server có thể dùng mặc định <code>false</code>. Việc một thuộc tính bắt buộc xuất hiện và việc nó có thể nhận null là các quyết định riêng của schema; hãy mô tả đúng với quy tắc API.

## 5. Chuỗi: string

Chuỗi được dùng cho tên, mã, email, địa chỉ, ngày giờ đã tuần tự hóa và nhiều giá trị văn bản khác:

~~~yaml
type: string
minLength: 1
maxLength: 120
example: Spring Boot
~~~

Các ràng buộc phổ biến:

| Thuộc tính | Ý nghĩa |
|---|---|
| <code>minLength</code> | Số ký tự tối thiểu |
| <code>maxLength</code> | Số ký tự tối đa |
| <code>pattern</code> | Biểu thức chính quy mà chuỗi phải thỏa |
| <code>enum</code> | Danh sách giá trị được phép |
| <code>format</code> | Gợi ý định dạng chuỗi đã biết |

Ví dụ mã trạng thái chỉ nhận một số giá trị:

~~~yaml
type: string
enum:
  - PENDING
  - APPROVED
  - REJECTED
example: PENDING
~~~

### 5.1. Các format chuỗi thường gặp

| Format | Ý nghĩa | Ví dụ |
|---|---|---|
| <code>date</code> | Ngày theo dạng full-date | <code>2026-11-20</code> |
| <code>date-time</code> | Thời điểm theo định dạng RFC 3339 | <code>2026-11-20T10:30:00Z</code> |
| <code>email</code> | Địa chỉ email | <code>dev@example.com</code> |
| <code>uuid</code> | Định danh UUID | <code>550e8400-e29b-41d4-a716-446655440000</code> |
| <code>uri</code> | URI | <code>https://example.com/items/1</code> |
| <code>hostname</code> | Tên máy chủ | <code>api.example.com</code> |
| <code>ipv4</code> / <code>ipv6</code> | Địa chỉ IP | <code>192.0.2.10</code> |
| <code>byte</code> | Dữ liệu nhị phân mã hóa Base64 | <code>SGVsbG8=</code> |
| <code>binary</code> | Dữ liệu nhị phân | Thường dùng khi mô tả nội dung file |
| <code>password</code> | Gợi ý giao diện nhập mật khẩu | Không hiển thị giá trị thực trong tài liệu |

Các format này là thông tin ngữ nghĩa cho công cụ. Mức độ kiểm tra định dạng có thể khác nhau giữa validator, Swagger UI và code generator. Nếu cần xác thực email, UUID hoặc định dạng riêng, hãy kiểm tra ở tầng ứng dụng bằng Bean Validation hay logic nghiệp vụ.

### 5.2. Ngày và thời điểm

Các kiểu Java thường gặp:

| Kiểu Java | Schema thường dùng |
|---|---|
| <code>LocalDate</code> | <code>string / date</code> |
| <code>LocalDateTime</code> | <code>string / date-time</code> |
| <code>OffsetDateTime</code> | <code>string / date-time</code> |
| <code>Instant</code> | <code>string / date-time</code> |

Ví dụ:

~~~java
import java.time.LocalDate;
import java.time.OffsetDateTime;

public record BookingRequest(
    LocalDate startDate,
    OffsetDateTime createdAt
) {}
~~~

Ngày là một ngày lịch, không nhất thiết gắn múi giờ. <code>LocalDateTime</code> không chứa offset, nên chuỗi serialize của nó có thể không biểu diễn một thời điểm toàn cục. Thời điểm nên có quy ước múi giờ rõ ràng; dùng <code>OffsetDateTime</code> hoặc <code>Instant</code> khi API cần biểu diễn một thời điểm trên dòng thời gian. Kiểm tra JSON sinh ra để xác nhận <code>type</code> và <code>format</code> phù hợp.

## 6. Ánh xạ kiểu Java sang schema cơ bản

springdoc-openapi sử dụng metadata từ Spring và swagger-core để suy ra schema từ kiểu Java. Bảng dưới đây mô tả ánh xạ thường gặp:

| Kiểu Java | OpenAPI type | Format thường gặp |
|---|---|---|
| <code>byte</code>, <code>short</code>, <code>int</code>, <code>Integer</code> | <code>integer</code> | <code>int32</code> |
| <code>long</code>, <code>Long</code> | <code>integer</code> | <code>int64</code> |
| <code>BigInteger</code> | <code>integer</code> | Không nhất thiết có format cố định |
| <code>float</code>, <code>Float</code> | <code>number</code> | <code>float</code> |
| <code>double</code>, <code>Double</code> | <code>number</code> | <code>double</code> |
| <code>BigDecimal</code> | <code>number</code> | Nên kiểm tra và tránh ép thành float/double nếu cần độ chính xác |
| <code>boolean</code>, <code>Boolean</code> | <code>boolean</code> | Không có |
| <code>String</code>, <code>char</code>, <code>Character</code> | <code>string</code> | Không có mặc định |
| <code>UUID</code> | <code>string</code> | <code>uuid</code> |
| <code>LocalDate</code> | <code>string</code> | <code>date</code> |
| <code>OffsetDateTime</code>, <code>Instant</code> | <code>string</code> | <code>date-time</code> |

Đây là ánh xạ phổ biến; phiên bản thư viện, cấu hình ObjectMapper và custom converter có thể làm thay đổi đầu ra. Đặc biệt với <code>BigInteger</code>, <code>BigDecimal</code>, kiểu thời gian và kiểu tùy chỉnh, hãy đọc schema thực tế ở <code>/v3/api-docs</code>.

## 7. Kiểu bất kỳ: schema không giới hạn type

Đôi khi API cần nhận một giá trị JSON mà kiểu của nó thay đổi theo loại sự kiện, cấu hình hoặc dữ liệu mở rộng. Trong trường hợp đó, có thể dùng schema không khai báo <code>type</code>:

~~~yaml
components:
  schemas:
    JsonValue: {}
~~~

Schema rỗng này không giới hạn giá trị vào một kiểu JSON duy nhất. Nó có thể đại diện cho string, number, integer, boolean, object, array hoặc null theo ngữ nghĩa schema của phiên bản OpenAPI/JSON Schema đang dùng.

Không nhầm schema bất kỳ với:

~~~yaml
type: object
~~~

Schema trên chỉ nhận object JSON, không phải mọi giá trị JSON. Tương tự, <code>type: object</code> với <code>additionalProperties</code> mô tả một object có các thuộc tính động, không mô tả một giá trị bất kỳ.

### 7.1. Object có thuộc tính động

Nếu payload luôn là object nhưng tên thuộc tính thay đổi, dùng <code>type: object</code> cùng <code>additionalProperties</code>:

~~~yaml
type: object
additionalProperties: {}
example:
  source: mobile
  retryCount: 2
  verified: true
~~~

Ví dụ này cho phép object có các thuộc tính tùy ý, mỗi thuộc tính có thể chứa giá trị JSON bất kỳ. Nếu tất cả giá trị phải là chuỗi, mô tả chặt hơn:

~~~yaml
type: object
additionalProperties:
  type: string
example:
  region: south
  language: vi
~~~

### 7.2. Dùng JsonNode cho dữ liệu JSON linh hoạt

Trong Java, <code>JsonNode</code> của Jackson là kiểu phù hợp khi cần thao tác trên cây JSON mà không biết trước cấu trúc. Một thuộc tính <code>JsonNode</code> có thể chứa object, array hoặc scalar.

Có thể khai báo component schema bất kỳ bằng OpenAPI bean:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.media.Schema;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class FlexibleJsonSchemaConfiguration {

    @Bean
    OpenAPI flexibleJsonOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Event API")
                .version("1.0.0"))
            .components(new Components()
                .addSchemas("JsonValue",
                    new Schema<>().description("Bất kỳ giá trị JSON hợp lệ")));
    }
}
~~~

Sau đó tham chiếu schema trong DTO:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.media.Schema;

public record EventRequest(
    @Schema(ref = "#/components/schemas/JsonValue")
    JsonNode payload
) {}
~~~

Component <code>JsonValue</code> không khai báo <code>type</code>, nên schema không giới hạn payload vào object hay một kiểu cụ thể. Nếu ứng dụng đã có OpenAPI bean, hãy bổ sung component vào cấu hình hiện tại thay vì tạo một bean thứ hai độc lập.

Không mặc định rằng mọi kiểu Java <code>Object</code> hoặc <code>JsonNode</code> đều được springdoc xuất thành schema rỗng. Bộ chuyển đổi model có thể tạo schema khác tùy phiên bản và cấu hình. Sau khi dùng <code>@Schema(ref = ...)</code> hoặc customizer, hãy kiểm tra tham chiếu thực tế trong tài liệu sinh ra.

### 7.3. Khi nào nên dùng oneOf hoặc anyOf?

Schema bất kỳ rất linh hoạt nhưng ít thông tin cho người tiêu thụ API. Nếu payload chỉ có một số cấu trúc đã biết, hãy mô tả rõ các lựa chọn bằng <code>oneOf</code> hoặc <code>anyOf</code>.

~~~yaml
oneOf:
  - $ref: "#/components/schemas/CardPayment"
  - $ref: "#/components/schemas/BankTransfer"
discriminator:
  propertyName: paymentType
~~~

Ví dụ trên nói payload phải khớp một trong các schema thanh toán được liệt kê. Nó giúp Swagger UI, validator và code generator hiểu cấu trúc tốt hơn so với một schema hoàn toàn tự do. Chỉ dùng <code>discriminator</code> khi payload thực sự có thuộc tính phân biệt và các schema được thiết kế tương ứng.

## 8. Kết hợp @Schema và Bean Validation

Annotation <code>@Schema</code> bổ sung metadata OpenAPI như type, format, example, description, minimum, maximum, minLength, maxLength và pattern. Bean Validation quy định những điều kiện mà ứng dụng kiểm tra lúc chạy.

Ví dụ DTO tổng hợp:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ProductRequest(
    @Schema(
        description = "Tên sản phẩm",
        example = "Wireless Mouse",
        minLength = 1,
        maxLength = 120,
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    @NotBlank
    @Size(max = 120)
    String name,

    @Schema(
        description = "Số lượng trong kho",
        type = "integer",
        format = "int64",
        example = "250",
        minimum = "0",
        maximum = "1000000"
    )
    @Min(0)
    @Max(1000000)
    Long stock,

    @Schema(
        description = "Giá sản phẩm",
        type = "number",
        example = "1299.95",
        minimum = "0"
    )
    @DecimalMin("0.00")
    BigDecimal price,

    @Schema(
        description = "Có đang được kinh doanh hay không",
        type = "boolean",
        example = "true"
    )
    Boolean active,

    @Schema(
        description = "Mã danh mục",
        type = "string",
        format = "uuid",
        example = "550e8400-e29b-41d4-a716-446655440000"
    )
    UUID categoryId
) {}
~~~

Controller kích hoạt validation bằng <code>@Valid</code>:

~~~java
@PostMapping("/products")
ResponseEntity<Void> createProduct(
        @Valid @RequestBody ProductRequest request) {
    // Lưu sản phẩm sau khi dữ liệu hợp lệ
    return ResponseEntity.accepted().build();
}
~~~

Các ràng buộc trong schema và Bean Validation cần thống nhất. Ví dụ <code>@Schema(maxLength = 120)</code> và <code>@Size(max = 120)</code> mô tả cùng giới hạn. Nếu chỉ khai báo giới hạn trong một lớp mà quên lớp còn lại, tài liệu và hành vi runtime có thể khác nhau.

<code>requiredMode</code> điều khiển sự hiện diện của thuộc tính trong schema OpenAPI. <code>@NotBlank</code>, <code>@Min</code> hoặc <code>@DecimalMin</code> kiểm tra giá trị ở runtime khi validation được kích hoạt. Không xem hai cơ chế này là một.

## 9. Kiểm tra schema được springdoc sinh ra

Sau khi khởi động ứng dụng, tải đặc tả:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Kiểm tra các mục sau:

1. Số nguyên được xuất thành <code>type: integer</code>, số thập phân thành <code>type: number</code>.
2. Boolean được xuất thành <code>type: boolean</code>, không phải string.
3. Chuỗi có <code>format</code> phù hợp như <code>date</code>, <code>date-time</code> hoặc <code>uuid</code>.
4. Các giới hạn số, độ dài, pattern và enum phản ánh đúng validation.
5. Schema bất kỳ không bị sinh nhầm thành <code>type: object</code> nếu API cho phép scalar hoặc array.
6. Các tham chiếu component không bị thiếu hoặc trỏ sai.

Có thể thử payload đại diện cho từng kiểu:

~~~json
{
  "quantity": 25,
  "price": 199.95,
  "active": true,
  "name": "Wireless Mouse"
}
~~~

Với schema bất kỳ, hãy kiểm tra các payload như số, chuỗi, Boolean, mảng, object và null nếu API cho phép. Điều này giúp xác nhận schema mô tả đúng phạm vi dữ liệu mà endpoint chấp nhận.

## 10. Lỗi thường gặp

**Khai báo số nhưng ví dụ lại là chuỗi.** <code>example: "25"</code> có thể khiến người đọc hiểu nhầm kiểu. Với số, dùng ví dụ số không có dấu nháy như <code>example: 25</code> trong YAML.

**Dùng integer cho dữ liệu có phần thập phân.** Giá tiền hoặc tỷ lệ có phần thập phân nên dùng <code>number</code>. Chọn kiểu Java và ràng buộc phù hợp với độ chính xác cần thiết.

**Gắn format không phù hợp với miền giá trị.** <code>int64</code> không mô tả chính xác một <code>BigInteger</code> vượt giới hạn 64 bit. <code>double</code> không thể hiện ý định số thập phân chính xác của <code>BigDecimal</code>.

**Cho rằng format tự xác thực dữ liệu.** <code>format: email</code> hoặc <code>format: uuid</code> là metadata cho công cụ. Hãy bổ sung validation runtime nếu API cần từ chối dữ liệu không hợp lệ.

**Nhầm Boolean với chuỗi.** JSON Boolean là <code>true</code>/<code>false</code> không có dấu nháy. Chuỗi <code>"true"</code> là kiểu dữ liệu khác.

**Dùng type object cho mọi JSON.** <code>type: object</code> không cho phép scalar hoặc array. Nếu API nhận mọi giá trị JSON, dùng schema không giới hạn type; nếu chỉ nhận object có khóa động, dùng <code>additionalProperties</code>.

**Cho rằng Object hoặc JsonNode luôn sinh schema mong muốn.** Kiểm tra đầu ra của springdoc và dùng component schema hoặc customizer để thể hiện rõ ý định nếu cần.

## 11. Danh sách rà soát trước khi công bố

- [ ] Số nguyên dùng <code>integer</code> và format đúng với miền giá trị.
- [ ] Số thập phân dùng <code>number</code>; kiểu tiền tệ cân nhắc <code>BigDecimal</code>.
- [ ] Boolean dùng <code>boolean</code>, không dùng chuỗi.
- [ ] Chuỗi có độ dài, pattern, enum hoặc format phù hợp khi cần.
- [ ] Format được xem là metadata và có validation runtime tương ứng nếu cần.
- [ ] Schema bất kỳ được phân biệt rõ với object có thuộc tính động.
- [ ] Dữ liệu linh hoạt dùng <code>JsonNode</code> hoặc kiểu phù hợp và có schema được xác minh.
- [ ] Các annotation <code>@Schema</code> thống nhất với Bean Validation.
- [ ] Đã kiểm tra tài liệu thực tế tại <code>/v3/api-docs</code>.

## Tài liệu tham khảo

- [OpenAPI Specification – Data Types](https://spec.openapis.org/oas/latest.html#data-types): các kiểu dữ liệu, format và schema trong OpenAPI.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): cấu trúc Schema Object và các ràng buộc.
- [JSON Schema – Numeric Types](https://json-schema.org/understanding-json-schema/reference/numeric): integer, number và các giới hạn số.
- [JSON Schema – String](https://json-schema.org/understanding-json-schema/reference/string): độ dài, pattern và format chuỗi.
- [Swagger Core – Schema annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/Schema.html): thuộc tính của annotation <code>@Schema</code>.
- [springdoc-openapi](https://springdoc.org/): tích hợp Spring Boot và sinh đặc tả OpenAPI.
