# @Min, @Max, @Pattern và các ràng buộc miền giá trị

API thường cần giới hạn dữ liệu đầu vào theo quy tắc nghiệp vụ: số lượng phải nằm trong một khoảng, giá tiền phải lớn hơn một ngưỡng, mã sản phẩm phải theo một mẫu nhất định hoặc danh sách nhãn không được vượt quá số phần tử cho phép. Trong Spring Boot, các annotation **Jakarta Bean Validation** giúp khai báo những ràng buộc này ngay trên DTO và tham số controller. **springdoc-openapi** có thể đọc nhiều ràng buộc để đưa giới hạn tương ứng vào schema OpenAPI.

Để hợp đồng API chính xác, cần bảo đảm ba phần thống nhất:

1. **Ràng buộc lúc chạy:** Bean Validation thực sự từ chối dữ liệu không hợp lệ.
2. **Schema OpenAPI:** tài liệu mô tả đúng khoảng giá trị, độ dài, mẫu chuỗi và các trường bắt buộc.
3. **Response lỗi:** client nhận được mã trạng thái và cấu trúc lỗi có thể hiểu khi vi phạm ràng buộc.

Chỉ thêm annotation vào DTO chưa đủ nếu ứng dụng không kích hoạt validation. Tương tự, chỉ mô tả giới hạn trong OpenAPI không làm server tự kiểm tra dữ liệu.

## 1. Các nhóm ràng buộc miền giá trị

Bean Validation cung cấp các constraint chuẩn để kiểm tra số, chuỗi và collection. Một số constraint thường dùng:

| Annotation | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **@Min(value)** | Giá trị phải lớn hơn hoặc bằng ngưỡng | Số lượng tối thiểu là 1 |
| **@Max(value)** | Giá trị phải nhỏ hơn hoặc bằng ngưỡng | Số trang tối đa là 100 |
| **@DecimalMin(value)** | Giá trị số thập phân phải lớn hơn hoặc bằng ngưỡng; có thể đặt inclusive = false | Giá phải lớn hơn 0 |
| **@DecimalMax(value)** | Giá trị số thập phân phải nhỏ hơn hoặc bằng ngưỡng; có thể đặt inclusive = false | Tỷ lệ không vượt quá 100 |
| **@Positive** | Giá trị phải lớn hơn 0 | Số lượng đặt mua |
| **@PositiveOrZero** | Giá trị phải lớn hơn hoặc bằng 0 | Số dư không âm |
| **@Negative**, **@NegativeOrZero** | Giá trị phải âm hoặc không dương | Khoản điều chỉnh giảm |
| **@Digits(integer, fraction)** | Giới hạn số chữ số phần nguyên và phần thập phân | Giá có tối đa 8 chữ số nguyên, 2 chữ số thập phân |
| **@Size(min, max)** | Giới hạn độ dài chuỗi hoặc số phần tử của collection, map, array | Tên dài 3–80 ký tự |
| **@Pattern(regexp)** | Chuỗi phải khớp biểu thức chính quy | Mã có định dạng ABC-123456 |
| **@NotNull**, **@NotBlank**, **@NotEmpty** | Kiểm tra sự hiện diện hoặc nội dung rỗng | Trường bắt buộc |

**@Min** và **@Max** hỗ trợ các kiểu số nguyên cùng **BigInteger** và **BigDecimal**; chúng không hỗ trợ **float** và **double**. Với ngưỡng thập phân, dùng **@DecimalMin** và **@DecimalMax** để biểu diễn chính xác. Tránh dùng float hoặc double cho tiền tệ; thường nên dùng **BigDecimal**.

**@Size** áp dụng cho **CharSequence**, collection, map và array; nó không giới hạn giá trị số. Muốn giới hạn số lượng sản phẩm, dùng **@Min**/**@Max**; muốn giới hạn số ký tự của mã sản phẩm, dùng **@Size** hoặc **@Pattern**.

Ba constraint về sự hiện diện có phạm vi khác nhau: **@NotNull** chỉ từ chối null; **@NotBlank** dành cho chuỗi và từ chối null, chuỗi rỗng hoặc chỉ có khoảng trắng; **@NotEmpty** từ chối null và giá trị rỗng trên chuỗi, collection, map hoặc array. Chọn constraint theo kiểu dữ liệu và ý nghĩa nghiệp vụ.

Một số provider như Hibernate Validator có constraint mở rộng, ví dụ **@Range**. Constraint này không thuộc bộ Jakarta Bean Validation chuẩn. Nếu dùng extension, kiểm tra provider đang cài và xác minh springdoc có phản ánh nó vào schema hay không; với hợp đồng dùng chung nhiều provider, ưu tiên constraint chuẩn.

## 2. @Min và @Max cho giới hạn số

**@Min** và **@Max** xác định biên bao gồm cả giá trị tại ngưỡng. Ví dụ:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record InventoryRequest(
    @NotNull
    @Min(1)
    @Max(5000)
    Integer quantity
) {}
~~~

Giá trị hợp lệ gồm 1 và 5000. Giá trị 0, số âm hoặc 5001 bị từ chối. **@Min** và **@Max** tự thân chấp nhận null; kết hợp **@NotNull** nếu trường bắt buộc.

Khi cần giới hạn một tham số query:

~~~java
import java.util.List;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/products")
List<ProductView> findProducts(
    @RequestParam(defaultValue = "1")
    @Min(1) @Max(100)
    int page,

    @RequestParam(defaultValue = "20")
    @Min(1) @Max(100)
    int size
) {
    return productService.find(page, size);
}
~~~

Ví dụ này cho phép page từ 1 đến 100 và size từ 1 đến 100. Giá trị mặc định do **@RequestParam(defaultValue = ...)** cung cấp khi client bỏ qua parameter. Bean Validation kiểm tra giá trị sau khi Spring đã chuyển đổi chuỗi query thành kiểu Java.

## 3. @DecimalMin, @DecimalMax và @Digits cho số thập phân

Đối với tiền, tỷ lệ hoặc đại lượng có phần thập phân, dùng **BigDecimal** và constraint thập phân:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;

public record PriceRequest(
    @NotNull
    @DecimalMin(value = "0.01")
    @DecimalMax(value = "999999.99")
    @Digits(integer = 6, fraction = 2)
    BigDecimal price
) {}
~~~

Trong ví dụ:

- Giá nhỏ nhất là 0.01 và lớn nhất là 999999.99.
- **@DecimalMin** và **@DecimalMax** mặc định bao gồm ngưỡng.
- **@Digits(integer = 6, fraction = 2)** giới hạn tối đa 6 chữ số phần nguyên và 2 chữ số phần thập phân.
- **@NotNull** yêu cầu client phải cung cấp giá trị.

Nếu muốn loại trừ chính ngưỡng, dùng thuộc tính **inclusive = false**:

~~~java
@DecimalMin(value = "0", inclusive = false)
BigDecimal balance
~~~

Điều này yêu cầu balance lớn hơn 0. **@DecimalMin** và **@DecimalMax** cho phép mô tả ngưỡng thập phân mà **@Min** và **@Max** không thể biểu đạt rõ ràng.

## 4. @Positive và các ràng buộc dấu

Khi nghiệp vụ chỉ yêu cầu giá trị dương hoặc không âm, constraint theo dấu làm ý định rõ hơn:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

public record ShippingRequest(
    @NotNull
    @Positive
    BigDecimal weightKg,

    @NotNull
    @PositiveOrZero
    BigDecimal insuranceFee
) {}
~~~

**weightKg** phải lớn hơn 0; **insuranceFee** có thể bằng 0 nhưng không được âm. Tương tự, **@Negative** yêu cầu giá trị nhỏ hơn 0 và **@NegativeOrZero** cho phép cả 0.

Các constraint này không thay thế **@NotNull**: hầu hết constraint kiểm tra giá trị miền đều coi null là hợp lệ để có thể kết hợp với constraint hiện diện riêng. Với trường bắt buộc, hãy dùng thêm **@NotNull**.

## 5. @Pattern cho mã và chuỗi có định dạng

**@Pattern** dùng biểu thức chính quy để kiểm tra nội dung chuỗi. Ví dụ, mã SKU gồm ba chữ cái in hoa, dấu gạch ngang và sáu chữ số:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record ProductCodeRequest(
    @NotBlank
    @Pattern(
        regexp = "^[A-Z]{3}-[0-9]{6}$",
        message = "Mã sản phẩm phải có dạng ABC-123456"
    )
    String sku
) {}
~~~

Một số ví dụ:

| Dữ liệu | Kết quả |
| --- | --- |
| ABC-123456 | Hợp lệ |
| XYZ-000001 | Hợp lệ |
| abc-123456 | Không hợp lệ vì chữ thường |
| AB-123456 | Không hợp lệ vì thiếu chữ cái |
| ABC-12345 | Không hợp lệ vì thiếu chữ số |
| ABC-123456-extra | Không hợp lệ vì có phần dư |

Bean Validation dùng cơ chế matching của Java regex để kiểm tra toàn bộ chuỗi. Trong khi đó, pattern của JSON Schema/OpenAPI có ngữ nghĩa tìm khớp trong chuỗi; vì vậy nên dùng **^** và **$** khi muốn biểu diễn điều kiện khớp toàn bộ giá trị như ví dụ trên. Dùng tập cú pháp regex tương thích với các công cụ OpenAPI và client generator; một số tính năng riêng của Java regex có thể không được công cụ khác hỗ trợ.

**@Pattern** chỉ áp dụng cho **CharSequence** và chấp nhận null. Nếu trường bắt buộc, kết hợp với **@NotBlank** hoặc **@NotNull**. **@NotBlank** còn loại chuỗi rỗng và chuỗi chỉ chứa khoảng trắng.

Không nên tạo regex quá phức tạp cho dữ liệu như số điện thoại, địa chỉ hoặc tên người nếu định dạng thực tế có nhiều biến thể. Hãy chọn quy tắc nghiệp vụ vừa đủ, mô tả rõ và kiểm thử bằng các giá trị biên.

## 6. Kết hợp nhiều constraint trên một DTO

Một trường thường cần nhiều điều kiện cùng lúc. Ví dụ DTO tạo sản phẩm:

~~~java
import java.math.BigDecimal;
import java.util.List;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
    @NotBlank
    @Size(min = 3, max = 80)
    String name,

    @NotBlank
    @Pattern(regexp = "^[A-Z]{3}-[0-9]{6}$")
    String sku,

    @NotNull
    @DecimalMin("0.01")
    @DecimalMax("999999.99")
    @Digits(integer = 6, fraction = 2)
    BigDecimal price,

    @NotNull
    @Min(0)
    @Max(100000)
    Integer stock,

    @Size(max = 10)
    List<
        @NotBlank
        @Pattern(regexp = "^[A-Z0-9_-]{2,20}$")
        String
    > tags
) {}
~~~

DTO này quy định:

- Tên không rỗng, dài từ 3 đến 80 ký tự.
- SKU theo đúng mẫu.
- Giá là số thập phân từ 0.01 đến 999999.99, tối đa 6 chữ số nguyên và 2 chữ số thập phân.
- Tồn kho nằm trong khoảng 0 đến 100000.
- Danh sách tag có tối đa 10 phần tử; mỗi phần tử không rỗng và có định dạng riêng.

Constraint đặt trên phần tử generic như **List<@Pattern(...) String>** là container element constraint. Nó kiểm tra từng phần tử trong danh sách, còn **@Size(max = 10)** kiểm tra số lượng phần tử.

Nếu tags được phép bỏ qua, **@Size** vẫn chấp nhận null. Nếu API yêu cầu danh sách phải có ít nhất một phần tử, thêm **@NotNull** và **@Size(min = 1, max = 10)**. Nếu muốn danh sách rỗng là hợp lệ nhưng không cho phép phần tử rỗng, giữ **@Size(max = 10)** và constraint trên phần tử.

## 7. Kích hoạt validation trong Spring Boot

### Kiểm tra request body bằng @Valid

Với DTO nhận từ JSON, đặt **@Valid** trên **@RequestBody** để Spring kích hoạt Bean Validation:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @PostMapping("/api/products")
    ResponseEntity<ProductView> create(
        @Valid @RequestBody CreateProductRequest request
    ) {
        ProductView result = productService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }
}
~~~

Ứng dụng cần có implementation Bean Validation. Với Spring Boot, dependency thường dùng là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Khi dùng Spring Boot 3 trở lên, import constraint từ namespace **jakarta.validation**. Các ứng dụng Spring Boot 2 cũ dùng namespace **javax.validation**; không trộn hai namespace trong cùng một cấu hình.

### Kiểm tra tham số method

Constraint đặt trực tiếp trên **@RequestParam**, **@PathVariable** hoặc tham số controller cần method validation:

~~~java
@GetMapping("/api/products")
List<ProductView> find(
    @RequestParam(defaultValue = "1") @Min(1) @Max(100) int page,
    @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size
) {
    return productService.find(page, size);
}
~~~

Với Spring Framework 6.1 trở lên, Spring MVC có hỗ trợ method validation tích hợp. Khi sử dụng cơ chế này, tránh đặt **@Validated** ở cấp controller vì nó có thể kích hoạt method validation qua AOP thay cho cơ chế tích hợp của MVC. Với các phiên bản Spring Framework cũ hơn, thường cần **@Validated** ở controller hoặc bean và cấu hình method validation phù hợp. Hãy làm theo hướng dẫn tương ứng với phiên bản Spring Boot/Spring Framework của dự án.

### Validation lồng nhau

**@Valid** kích hoạt validation cho object lồng nhau:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record AddressRequest(
    @NotBlank
    @Size(max = 120)
    String street,

    @NotBlank
    @Pattern(regexp = "^[0-9]{5,10}$")
    String postalCode
) {}

public record CreateCustomerRequest(
    @NotBlank
    String name,

    @NotNull
    @Valid
    AddressRequest address
) {}
~~~

Nếu thiếu **@Valid** ở thuộc tính address, các constraint bên trong **AddressRequest** có thể không được chạy khi kiểm tra object cha. Với collection object, dùng **List<@Valid AddressRequest>** để cascade đến từng phần tử.

## 8. Ràng buộc liên trường và quy tắc miền nghiệp vụ

Không phải mọi quy tắc đều kiểm tra được bằng một annotation trên một field. Ví dụ ngày kết thúc phải sau ngày bắt đầu, hoặc tổng phần trăm phân bổ phải bằng 100. Đây là ràng buộc liên trường hoặc ràng buộc cấp đối tượng.

Ví dụ annotation cấp lớp:

~~~java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.Target;

import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Target(TYPE)
@Retention(RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
@Documented
public @interface ValidDateRange {
    String message() default "Ngày kết thúc phải sau hoặc bằng ngày bắt đầu";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, DateRangeRequest> {

    @Override
    public boolean isValid(
            DateRangeRequest value,
            ConstraintValidatorContext context
    ) {
        if (value == null
                || value.startDate() == null
                || value.endDate() == null) {
            return true;
        }

        return !value.endDate().isBefore(value.startDate());
    }
}
~~~

DTO:

~~~java
import java.time.LocalDate;

import jakarta.validation.constraints.NotNull;

@ValidDateRange
public record DateRangeRequest(
    @NotNull LocalDate startDate,
    @NotNull LocalDate endDate
) {}
~~~

Validator trả true khi một trong hai ngày là null vì trách nhiệm kiểm tra sự hiện diện thuộc về **@NotNull**. Cách tách này giúp constraint cấp lớp chỉ tập trung vào quan hệ giữa hai giá trị.

Các quy tắc liên trường thường không được biểu diễn đầy đủ bằng một thuộc tính schema đơn giản. Hãy bổ sung mô tả ở DTO hoặc operation bằng **@Schema(description = ...)**, mô tả response lỗi phù hợp và kiểm tra runtime. Schema OpenAPI có thể mô tả một số điều kiện phức tạp bằng JSON Schema/OpenAPI 3.1, nhưng việc springdoc suy luận tự động từ custom validator không nên được giả định.

## 9. Validation groups cho các ngữ cảnh khác nhau

Một DTO có thể được dùng cho nhiều thao tác, nhưng quy tắc bắt buộc ở thao tác tạo mới có thể khác thao tác cập nhật. Bean Validation hỗ trợ groups để chọn tập constraint cần chạy.

~~~java
public interface OnCreate {}
public interface OnUpdate {}

public record ProductInput(
    @NotBlank(groups = OnCreate.class)
    String name,

    @NotNull(groups = OnCreate.class)
    @Min(value = 0, groups = {OnCreate.class, OnUpdate.class})
    Integer stock
) {}
~~~

Có thể chọn group khi kích hoạt validation bằng **@Validated(OnCreate.class)** hoặc **@Validated(OnUpdate.class)** ở điểm phù hợp với cơ chế method validation của phiên bản Spring đang dùng. Nếu dùng **@Valid** mặc định, group mặc định là **Default**; các constraint chỉ gắn vào group tùy chỉnh sẽ không tự chạy.

Khi cùng một DTO được dùng trong nhiều operation, OpenAPI thường chỉ có một schema cho kiểu đó. Schema chung có thể không diễn đạt đầy đủ sự khác nhau giữa các group. Nếu hợp đồng request của create và update khác nhau đáng kể, nên cân nhắc tách DTO để springdoc tạo schema riêng và client hiểu đúng yêu cầu của từng operation.

## 10. Bean Validation được phản ánh vào OpenAPI như thế nào?

Springdoc có thể đọc metadata từ các constraint chuẩn và đưa giới hạn vào schema. Một số ánh xạ thường gặp:

| Bean Validation | Thuộc tính OpenAPI/JSON Schema thường tương ứng |
| --- | --- |
| **@Min(1)** | **minimum: 1** |
| **@Max(100)** | **maximum: 100** |
| **@DecimalMin("0.01")** | **minimum** hoặc **exclusiveMinimum** theo tính inclusive và phiên bản OpenAPI |
| **@DecimalMax("99.99")** | **maximum** hoặc **exclusiveMaximum** theo tính inclusive và phiên bản OpenAPI |
| **@Size(min = 3, max = 80)** trên chuỗi | **minLength**, **maxLength** |
| **@Size(max = 10)** trên array | **maxItems** |
| **@Pattern(regexp = "...")** | **pattern** |
| **@Digits(integer = 6, fraction = 2)** | Giới hạn số chữ số/độ chính xác nếu phiên bản và converter hỗ trợ |

Ví dụ schema cho SKU:

~~~yaml
sku:
  type: string
  pattern: '^[A-Z]{3}-[0-9]{6}$'
  minLength: 10
  maxLength: 10
  example: ABC-123456
~~~

Ví dụ schema cho số lượng:

~~~yaml
quantity:
  type: integer
  format: int32
  minimum: 1
  maximum: 5000
~~~

Ví dụ schema cho giá:

~~~yaml
price:
  type: number
  minimum: 0.01
  maximum: 999999.99
~~~

Đây là các đoạn minh họa ý nghĩa schema. Schema sinh ra thực tế có thể dùng **number** không kèm format hoặc tham chiếu component tùy kiểu Java và cấu hình. Với ngưỡng loại trừ, cách biểu diễn **exclusiveMinimum**/**exclusiveMaximum** khác nhau giữa OpenAPI 3.0 và 3.1; hãy kiểm tra trường **openapi** trong tài liệu và ý nghĩa của schema thay vì so khớp máy móc một dạng YAML.

Springdoc có thể cần dependency hoặc cấu hình tương ứng để đọc Jakarta Bean Validation. Nếu constraint không xuất hiện trong tài liệu, kiểm tra phiên bản springdoc, phiên bản Jakarta Validation, dependency validation và cách annotation được đặt trên field/getter/record component.

## 11. Phân biệt ràng buộc runtime với metadata @Schema

**@Schema** bổ sung mô tả cho tài liệu OpenAPI; nó không thay thế validator runtime. Ví dụ:

~~~java
@Schema(
    description = "Số lượng đặt hàng",
    minimum = "1",
    maximum = "5000",
    example = "12"
)
@Min(1)
@Max(5000)
Integer quantity
~~~

Trong ví dụ, **@Min** và **@Max** là ràng buộc runtime được Bean Validation thực thi khi validation được kích hoạt. **@Schema** cung cấp thông tin tài liệu. Nếu hai bên mâu thuẫn, client có thể gửi dữ liệu mà tài liệu cho là hợp lệ nhưng server từ chối, hoặc ngược lại.

Để giảm sai lệch:

- Ưu tiên constraint Bean Validation chuẩn cho các giới hạn runtime.
- Để springdoc suy luận schema từ constraint khi được hỗ trợ.
- Dùng **@Schema** cho mô tả, ví dụ hoặc chi tiết chưa suy luận được.
- Nếu phải khai báo giới hạn ở cả hai nơi, kiểm thử để bảo đảm các giá trị giống nhau.
- Không gắn constraint vào response DTO với kỳ vọng Spring tự động validate response; annotation trên DTO không tự động xác thực mọi object được serialize ra ngoài.

## 12. Response lỗi khi dữ liệu vi phạm constraint

Khi **@Valid @RequestBody** phát hiện dữ liệu không hợp lệ, Spring MVC thường phát sinh **MethodArgumentNotValidException**. Với method validation tích hợp của Spring Framework 6.1, lỗi tham số method có thể được biểu diễn bằng **HandlerMethodValidationException**. Cấu hình method validation qua AOP ở các phiên bản hoặc cách cấu hình khác có thể dùng **ConstraintViolationException**.

Ứng dụng nên chuẩn hóa response lỗi qua **@RestControllerAdvice**, ví dụ trả mã **400 Bad Request** cùng danh sách field và thông báo:

~~~json
{
  "type": "VALIDATION_ERROR",
  "message": "Dữ liệu đầu vào không hợp lệ",
  "violations": [
    {
      "field": "price",
      "message": "phải lớn hơn hoặc bằng 0.01"
    },
    {
      "field": "sku",
      "message": "Mã sản phẩm không đúng định dạng"
    }
  ]
}
~~~

Mô tả response lỗi trong OpenAPI:

~~~java
@ApiResponse(
    responseCode = "400",
    description = "Dữ liệu đầu vào vi phạm ràng buộc",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ValidationErrorView.class)
    )
)
~~~

Tên exception và cách Spring chuyển chúng thành response phụ thuộc phiên bản và cấu hình. Dù dùng exception nào, client nên nhận cấu trúc lỗi ổn định để xác định field, quy tắc vi phạm và cách sửa dữ liệu.

## 13. Kiểm thử validation và schema sinh ra

### Kiểm thử request hợp lệ và không hợp lệ

Ví dụ với MockMvc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductValidationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    ProductService productService;

    @Test
    void rejectsInvalidSku() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Laptop",
                      "sku": "bad-code",
                      "price": 120.00,
                      "stock": 5,
                      "tags": []
                    }
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsPriceBelowMinimum() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Laptop",
                      "sku": "ABC-123456",
                      "price": 0.00,
                      "stock": 5,
                      "tags": []
                    }
                    """))
            .andExpect(status().isBadRequest());
    }
}
~~~

Test slice cần có cấu hình validation và mock các dependency của controller. Tùy cấu hình Spring Security, test có thể cần cung cấp authentication hoặc disable filter phù hợp. Kiểm thử không chỉ xác nhận status mà nên kiểm tra tên field và cấu trúc lỗi nếu đó là một phần của hợp đồng.

### Kiểm tra schema OpenAPI

Lấy đặc tả sau khi ứng dụng khởi động:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Kiểm tra component:

~~~bash
jq '.components.schemas.CreateProductRequest' openapi.json
~~~

Đối chiếu:

1. **price** có kiểu số và khoảng giá đúng không.
2. **stock** có minimum và maximum đúng không.
3. **sku** có pattern, độ dài và ví dụ đúng không.
4. **tags** có giới hạn số phần tử và schema cho từng phần tử không.
5. Field bắt buộc có được mô tả đúng theo hợp đồng không.
6. Response **400** có schema lỗi mà server thực sự trả về không.

Mở Swagger UI để xem các giới hạn và thử nhập dữ liệu ngoài khoảng. Swagger UI có thể hỗ trợ hiển thị giới hạn hoặc kiểm tra một số giá trị, nhưng server vẫn là nơi thực thi validation cuối cùng.

## 14. Lỗi thường gặp

**Dữ liệu sai vẫn được chấp nhận.** Kiểm tra dependency **spring-boot-starter-validation**, annotation **@Valid** trên request body và cơ chế method validation cho tham số trực tiếp. Kiểm tra controller có thực sự đi qua validation provider không.

**Trường null không bị từ chối dù có @Min hoặc @Pattern.** Đây là hành vi đúng của nhiều constraint: null được xem là hợp lệ. Thêm **@NotNull** hoặc **@NotBlank** nếu trường bắt buộc.

**Giá trị đúng ngưỡng bị từ chối.** Kiểm tra **inclusive** của **@DecimalMin**/**@DecimalMax**, cũng như ràng buộc **@Digits**. **@Min** và **@Max** bao gồm ngưỡng.

**OpenAPI có minimum nhưng không có maximum.** Kiểm tra annotation ở field/getter/record component, dependency và phiên bản springdoc. Đọc schema JSON được sinh ra để xác định constraint nào bị bỏ qua.

**Regex hiển thị trong OpenAPI nhưng client gửi giá trị vẫn khác kết quả server.** Kiểm tra anchor **^** và **$**, khác biệt giữa Java regex và regex mà công cụ OpenAPI/client hỗ trợ, cùng flags đang dùng.

**@Valid không kiểm tra object lồng nhau.** Thêm **@Valid** ở thuộc tính lồng hoặc phần tử collection cần cascade.

**Schema nói trường bắt buộc nhưng runtime chấp nhận null.** Kết hợp đúng **@NotNull**/**@NotBlank**, kiểm tra **requiredMode** hoặc cấu hình schema và xác minh request thực tế.

**Response DTO có constraint nhưng response sai vẫn được gửi.** Bean Validation không tự động xác thực object response chỉ vì annotation có trên DTO. Thêm kiểm tra rõ ràng ở service/controller hoặc test serialization và response nếu nghiệp vụ yêu cầu.

## 15. Checklist áp dụng ràng buộc miền giá trị

- [ ] Chọn constraint đúng kiểu dữ liệu: số nguyên, số thập phân, chuỗi hay collection.
- [ ] Dùng **@Min**/**@Max** cho biên số bao gồm và **@DecimalMin**/**@DecimalMax** cho ngưỡng thập phân.
- [ ] Dùng **@Positive**, **@PositiveOrZero** khi diễn đạt quy tắc dấu rõ hơn.
- [ ] Dùng **@Pattern** cho chuỗi có định dạng và neo regex nếu cần khớp toàn chuỗi.
- [ ] Kết hợp **@NotNull**, **@NotBlank** hoặc **@NotEmpty** khi trường phải có giá trị.
- [ ] Dùng **@Size** cho độ dài chuỗi hoặc số phần tử, không dùng để giới hạn giá trị số.
- [ ] Kích hoạt validation bằng **@Valid** hoặc method validation phù hợp với phiên bản Spring.
- [ ] Cascade validation cho object và collection lồng nhau.
- [ ] Dùng custom class-level constraint cho quy tắc liên trường.
- [ ] Đồng bộ ràng buộc runtime với schema OpenAPI và response lỗi.
- [ ] Kiểm thử cả request hợp lệ, request không hợp lệ và tài liệu **/v3/api-docs**.

## 16. Kết luận

**@Min**, **@Max**, **@DecimalMin**, **@DecimalMax**, **@Pattern** và các constraint liên quan giúp chuyển quy tắc miền giá trị thành kiểm tra có thể thực thi trong Spring Boot. springdoc có thể phản ánh nhiều giới hạn này vào schema OpenAPI để client biết trước dữ liệu hợp lệ. Hãy kích hoạt validation đúng cách, xử lý riêng tính bắt buộc và null, mô tả các quy tắc liên trường, rồi kiểm tra response lỗi cùng schema sinh ra. Khi runtime và tài liệu cùng thể hiện một hợp đồng, client có thể chuẩn bị dữ liệu chính xác hơn và giảm lỗi khi tích hợp.

## 17. Nguồn tham khảo

- [Jakarta Bean Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): ý nghĩa constraint chuẩn, groups, cascading và custom validator.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): tích hợp Bean Validation trong Spring.
- [Spring Framework — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): validation request body và method parameters trong Spring MVC.
- [Springdoc OpenAPI](https://springdoc.org/): cách tạo schema OpenAPI từ controller, DTO và annotation của Spring.
