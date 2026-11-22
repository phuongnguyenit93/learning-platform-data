# @Valid và cấu trúc dữ liệu lồng nhau

## 1. Vì sao dữ liệu lồng nhau cần validation theo tầng?

Request JSON trong ứng dụng Spring Boot hiếm khi chỉ chứa những trường đơn giản. Một request tạo đơn hàng có thể gồm thông tin giao hàng, danh sách dòng hàng và địa chỉ nhận hàng. Mỗi object con lại có các quy tắc riêng: tên người nhận không được để trống, mã sản phẩm phải hợp lệ, số lượng phải lớn hơn 0 và danh sách dòng hàng phải có ít nhất một phần tử.

Nếu chỉ kiểm tra object ngoài cùng, các object con có thể chứa dữ liệu sai nhưng vẫn đi vào logic nghiệp vụ. Bean Validation giải quyết vấn đề này bằng cơ chế **cascaded validation**: khi một thuộc tính được đánh dấu bằng **@Valid**, bộ kiểm tra tiếp tục xác thực object hoặc phần tử bên trong thuộc tính đó.

Trong tài liệu API, Springdoc OpenAPI cần mô tả cấu trúc JSON lồng nhau và các ràng buộc tương ứng. Jackson quyết định cách JSON được ánh xạ vào Java object; Bean Validation kiểm tra object sau khi binding; Springdoc đọc kiểu Java, Jackson metadata và validation annotations để xây dựng schema. Ba phần này liên quan chặt chẽ nhưng có trách nhiệm riêng.

Bài học này tập trung vào cách dùng **@Valid** để kiểm tra object con, collection, array và cấu trúc lồng nhiều cấp; cách Jackson ảnh hưởng đến tên và khả năng xuất hiện của thuộc tính; và cách xác minh schema OpenAPI khớp với hành vi runtime.

## 2. Luồng xử lý request trong Spring MVC

Với endpoint nhận JSON, luồng xử lý thường diễn ra theo thứ tự:

1. Client gửi HTTP request với Content-Type phù hợp, thường là application/json.
2. Spring chọn HttpMessageConverter và Jackson đọc JSON.
3. Jackson deserialize dữ liệu thành DTO Java.
4. Spring kích hoạt Bean Validation nếu tham số được đánh dấu bằng @Valid hoặc @Validated theo cấu hình.
5. Validator kiểm tra các constraint ở object ngoài cùng và các object con được cascade qua @Valid.
6. Nếu dữ liệu hợp lệ, controller tiếp tục xử lý nghiệp vụ.
7. Nếu dữ liệu không hợp lệ, Spring tạo lỗi validation để exception handler chuyển thành HTTP response phù hợp.

Ví dụ:

~~~java
@PostMapping("/api/orders")
public OrderResponse create(
    @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

**@RequestBody** yêu cầu Spring đọc request body và bind vào CreateOrderRequest. **@Valid** yêu cầu kiểm tra các constraint trên đối tượng sau khi deserialize. Nếu DTO có thuộc tính object con hoặc collection, cần đánh dấu cascade ở những thuộc tính tương ứng để validator đi sâu vào cấu trúc.

Jackson và Bean Validation xử lý hai loại lỗi khác nhau:

- JSON sai cú pháp, sai kiểu không thể deserialize hoặc thiếu dữ liệu cần cho constructor có thể gây lỗi đọc message, thường được ánh xạ thành 400 Bad Request.
- JSON deserialize thành công nhưng vi phạm @NotBlank, @Min hoặc constraint khác sẽ gây lỗi validation, thường đi qua MethodArgumentNotValidException trong Spring MVC.

OpenAPI mô tả schema và response lỗi mà client cần biết. Springdoc không tự chạy Jackson deserialize hay thực thi Bean Validation khi tạo tài liệu.

## 3. @Valid thực hiện cascade validation

Annotation **jakarta.validation.Valid** đánh dấu một vị trí cần xác thực đệ quy. Nó không phải constraint kiểm tra giá trị. @Valid chỉ yêu cầu validator đi vào object được tham chiếu và kiểm tra các constraint được khai báo trên object đó.

Ví dụ:

~~~java
public record AddressRequest(
    @NotBlank
    String street,

    @NotBlank
    String city,

    @Pattern(regexp = "^[0-9]{5,10}$")
    String postalCode
) {}

public record CreateCustomerRequest(
    @NotBlank
    String fullName,

    @Email
    String email,

    @Valid
    AddressRequest address
) {}
~~~

Khi validator kiểm tra CreateCustomerRequest, các constraint trên fullName và email được kiểm tra. Vì address có @Valid, validator tiếp tục kiểm tra street, city và postalCode trong AddressRequest nếu address không null.

Một điểm quan trọng: **@Valid không tự yêu cầu object con phải tồn tại**. Nếu address là null, validator không thể đi vào object đó và thường bỏ qua cascade. Nếu nghiệp vụ yêu cầu address bắt buộc, cần kết hợp @NotNull:

~~~java
public record CreateCustomerRequest(
    @NotBlank
    String fullName,

    @NotNull
    @Valid
    AddressRequest address
) {}
~~~

Trong ví dụ này:

- @NotNull yêu cầu address có giá trị.
- @Valid yêu cầu kiểm tra tiếp các trường bên trong AddressRequest.
- @NotBlank trên street và city kiểm tra nội dung của các trường con.

Kết hợp constraint và cascade giúp phân biệt rõ sự hiện diện của object với tính hợp lệ của các thuộc tính bên trong.

## 4. @Valid với collection và phần tử lồng nhau

Một thuộc tính List hoặc Set có thể chứa nhiều object con. Để kiểm tra từng phần tử, cần cấu hình cascade validation trên thuộc tính collection hoặc trên type argument theo mô hình container element constraints.

Ví dụ dùng type-use annotation:

~~~java
public record CreateOrderRequest(
    @NotEmpty
    @Size(max = 50)
    List<@NotNull @Valid OrderLineRequest> items
) {}

public record OrderLineRequest(
    @NotNull
    @Positive
    Long productId,

    @NotNull
    @Min(1)
    @Max(1000)
    Integer quantity
) {}
~~~

Khi kiểm tra CreateOrderRequest:

- @NotEmpty yêu cầu danh sách items không null và có ít nhất một phần tử.
- @Size(max = 50) giới hạn tối đa 50 dòng hàng.
- @NotNull trên phần tử cấm phần tử null trong danh sách.
- @Valid trên phần tử yêu cầu kiểm tra từng OrderLineRequest.
- @Positive và @Min/@Max kiểm tra giá trị của từng dòng hàng.

Có thể đặt @Valid trên thuộc tính collection:

~~~java
public record CreateOrderRequest(
    @NotEmpty
    @Valid
    List<OrderLineRequest> items
) {}
~~~

Cách này cũng kích hoạt cascade tới các phần tử collection. Type-use annotation giúp chỉ rõ constraint nào áp dụng lên phần tử, chẳng hạn @NotNull, còn @Valid kích hoạt kiểm tra object con.

Với array hoặc Set, nguyên tắc tương tự:

~~~java
public record BatchRequest(
    @NotEmpty
    List<@NotNull @Valid CustomerRequest> customers,

    @NotNull
    @Valid
    AddressRequest[] deliveryAddresses
) {}
~~~

Cần kiểm tra khả năng hỗ trợ của provider Bean Validation và phiên bản Java/Jakarta Validation đang dùng, đặc biệt với container element constraints và collection lồng nhiều cấp.

## 5. Cascade qua nhiều cấp object

Dữ liệu có thể lồng nhiều tầng. Ví dụ một đơn hàng có khách hàng, địa chỉ, danh sách dòng hàng và thông tin giao nhận.

~~~java
public record CreateOrderRequest(
    @NotNull
    @Valid
    CustomerRequest customer,

    @NotEmpty
    List<@NotNull @Valid OrderLineRequest> items,

    @NotNull
    @Valid
    DeliveryRequest delivery
) {}

public record CustomerRequest(
    @NotBlank
    String name,

    @NotNull
    @Valid
    AddressRequest address
) {}

public record DeliveryRequest(
    @NotBlank
    String recipient,

    @NotNull
    @Valid
    AddressRequest address,

    @Future
    LocalDate deliveryDate
) {}
~~~

Khi controller gọi validation trên CreateOrderRequest, validator sẽ đi qua customer, customer.address, từng items element, delivery và delivery.address nhờ các vị trí có @Valid.

Mỗi cấp có thể có constraint riêng:

- Object cha kiểm tra object con có được cung cấp không.
- Object con kiểm tra trường dữ liệu của chính nó.
- Collection kiểm tra số lượng phần tử.
- Phần tử collection kiểm tra giá trị và object lồng bên trong.

Nếu quên @Valid tại một mắt xích, cascade dừng ở đó. Ví dụ customer có @Valid nhưng customer.address không có @Valid, validator sẽ kiểm tra constraint trên CustomerRequest nhưng không đi sâu vào AddressRequest.

## 6. @Valid, @NotNull, @NotEmpty và @NotBlank khác nhau thế nào?

Các annotation này thường xuất hiện cùng nhau nhưng kiểm tra những điều kiện khác nhau:

| Annotation | Kiểu thường áp dụng | Điều kiện |
|---|---|---|
| @Valid | Object, collection, phần tử container | Cascade validation vào object hoặc phần tử con |
| @NotNull | Bất kỳ reference type | Giá trị không được null |
| @NotEmpty | CharSequence, Collection, Map, array | Không null và không rỗng |
| @NotBlank | CharSequence | Không null và có ít nhất một ký tự không phải whitespace |
| @Size | CharSequence, Collection, Map, array | Kích thước nằm trong khoảng cho phép |
| @NotEmpty + @Valid | Collection chứa object | Collection phải có phần tử và từng object được cascade validation |
| @NotNull + @Valid | Object con | Object phải tồn tại và các trường con được kiểm tra |

Ví dụ:

~~~java
public record RegistrationRequest(
    @NotNull
    @Valid
    ProfileRequest profile,

    @NotEmpty
    List<@NotNull @Valid ContactRequest> contacts
) {}
~~~

Profile không được null và được kiểm tra sâu. Contacts phải có ít nhất một phần tử, từng phần tử không được null và được kiểm tra các constraint bên trong.

@Valid một mình không thay thế @NotNull, @NotEmpty hoặc @NotBlank. Ngược lại, @NotNull chỉ kiểm tra reference có khác null, không đi vào object con.

## 7. @Valid trên Map và container lồng nhau

Bean Validation hỗ trợ cascade validation cho nhiều kiểu container, không chỉ List. Với Map, có thể xác thực value hoặc key bằng type-use annotation.

Ví dụ xác thực value của Map:

~~~java
public record ContactDirectoryRequest(
    @NotEmpty
    Map<
        @NotBlank String,
        @NotNull @Valid ContactRequest
    > contacts
) {}

public record ContactRequest(
    @NotBlank
    String phone,

    @Email
    String email
) {}
~~~

Ở đây:

- Key phải là chuỗi không rỗng hoặc whitespace.
- Value không được null.
- Mỗi ContactRequest được kiểm tra phone và email.

Nếu cần kiểm tra key và value, đặt constraint lên đúng type argument. Với container lồng nhau như Map<String, List<AddressRequest>>, cần cascade ở từng tầng có object cần xác thực:

~~~java
Map<String, List<@NotNull @Valid AddressRequest>> addressesByType
~~~

Cấu trúc JSON của Map thường là object có tên property động, còn List bên trong là array. OpenAPI schema phải phản ánh đúng cấu trúc đó. Springdoc có thể suy luận generic type và schema lồng nhau, nhưng cần kiểm tra tài liệu sinh ra khi dùng kiểu container phức tạp.

## 8. Jackson quyết định tên thuộc tính JSON

Jackson chịu trách nhiệm chuyển đổi giữa JSON và Java object. Tên thuộc tính trong JSON không nhất thiết giống tên field hoặc component trong Java record.

Ví dụ:

~~~java
public record CustomerRequest(
    @JsonProperty("full_name")
    @NotBlank
    String fullName,

    @JsonProperty("email_address")
    @Email
    String email
) {}
~~~

Client gửi JSON:

~~~json
{
  "full_name": "Nguyen Van An",
  "email_address": "an@example.com"
}
~~~

Jackson ánh xạ full_name vào component fullName và email_address vào email. Springdoc thường sử dụng Jackson metadata để tạo tên property trong schema OpenAPI, vì vậy tài liệu nên hiển thị full_name và email_address nếu đó là tên JSON thực tế.

Có thể dùng naming strategy ở cấp class:

~~~java
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record CustomerRequest(
    @NotBlank String fullName,
    @Email String emailAddress
) {}
~~~

Với cấu hình này, Jackson chuyển tên thuộc tính sang snake_case theo naming strategy. Cần kiểm tra OpenAPI document để chắc chắn tên property được tạo khớp với ObjectMapper đang chạy.

## 9. Jackson alias, ignore và read/write access

Một số Jackson annotation ảnh hưởng đến việc property được nhận khi deserialize hoặc xuất hiện khi serialize.

| Annotation/cấu hình | Hành vi Jackson | Điều cần kiểm tra trong OpenAPI |
|---|---|---|
| @JsonProperty | Đặt tên property hoặc cấu hình access | Schema dùng đúng tên JSON |
| @JsonAlias | Chấp nhận các tên thay thế khi deserialize | Alias đầu vào không nhất thiết là tên property chuẩn được công bố |
| @JsonIgnore | Bỏ qua property theo cấu hình annotation | Property có thể không xuất hiện trong schema |
| @JsonIgnoreProperties(ignoreUnknown = true) | Bỏ qua property không biết khi deserialize | Không làm các property tùy ý trở thành schema đã công bố |
| @JsonProperty(access = READ_ONLY) | Chỉ đọc/serialize, không nhận input thông thường | Có thể thể hiện readOnly |
| @JsonProperty(access = WRITE_ONLY) | Chỉ nhận input, không serialize output thông thường | Có thể thể hiện writeOnly |
| @JsonInclude | Điều khiển điều kiện đưa property vào JSON output | Không thay thế required hoặc validation |

Ví dụ một DTO có trường chỉ đọc:

~~~java
public record ProductResponse(
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    Long id,

    @NotBlank
    String name
) {}
~~~

Nếu cùng DTO được dùng cho request và response, thuộc tính id có thể bị Jackson xử lý theo hướng chỉ đọc. Tuy nhiên, trong dự án thực tế nên cân nhắc tách CreateProductRequest và ProductResponse để hợp đồng đầu vào và đầu ra rõ ràng hơn.

Ví dụ alias:

~~~java
public record SearchRequest(
    @JsonProperty("keyword")
    @JsonAlias({"q", "searchTerm"})
    String keyword
) {}
~~~

Jackson có thể chấp nhận các tên q hoặc searchTerm khi đọc JSON, nhưng tên property chuẩn được công bố nên là keyword. Alias là khả năng tương thích đầu vào; không nên coi mọi alias là property riêng biệt trong schema nếu API không muốn client mới tiếp tục dùng các tên cũ.

## 10. Jackson và phân biệt property bị thiếu với null

JSON có thể biểu diễn một property theo ba trạng thái:

1. Property không xuất hiện.
2. Property xuất hiện với giá trị null.
3. Property xuất hiện với giá trị cụ thể.

Ba trường hợp này có thể mang ý nghĩa khác nhau, đặc biệt với API cập nhật một phần như PATCH.

Ví dụ:

~~~json
{
  "displayName": null
}
~~~

khác với:

~~~json
{}
~~~

Trong DTO Java thông thường, cả hai trường hợp có thể cùng tạo ra giá trị null nếu không có cơ chế giữ trạng thái presence riêng. Jackson configuration, constructor binding, primitive type và custom deserializer có thể làm thay đổi cách phân biệt.

Một số lưu ý:

- Reference type như String hoặc Integer có thể nhận null nếu không có constraint hoặc deserializer từ chối.
- Primitive như int không thể giữ null; nếu property bị thiếu, giá trị mặc định của Java có thể là 0.
- @NotNull kiểm tra giá trị sau binding, không tự phân biệt property bị thiếu với property gửi null.
- @JsonInclude(NON_NULL) điều khiển serialize response, không làm request property trở thành optional.
- OpenAPI required mô tả property phải xuất hiện; nullable mô tả giá trị null có được chấp nhận hay không.

Với PATCH, nếu cần phân biệt “không thay đổi” và “xóa giá trị”, hãy thiết kế DTO hoặc cơ chế presence rõ ràng, chẳng hạn wrapper chuyên biệt hoặc JsonNode. Không nên dựa vào một field nullable duy nhất nếu hai trạng thái có ý nghĩa nghiệp vụ khác nhau.

## 11. Validation constraints được phản ánh vào OpenAPI Schema

Springdoc có thể đọc các constraint Bean Validation để bổ sung metadata vào schema. Các ánh xạ phổ biến gồm:

| Bean Validation | Metadata schema thường tương ứng |
|---|---|
| @NotNull | Không chấp nhận giá trị null; công cụ có thể đồng thời đưa property vào required tùy schema/version và cấu hình |
| @NotBlank | Chuỗi không rỗng sau khi bỏ khoảng trắng |
| @Size(min, max) | minLength/maxLength hoặc minItems/maxItems tùy kiểu |
| @Min / @DecimalMin | minimum |
| @Max / @DecimalMax | maximum |
| @Positive | exclusiveMinimum hoặc giới hạn tương ứng |
| @Pattern | pattern |
| @Email | Format email hoặc metadata tương ứng |
| @NotEmpty | Tối thiểu một ký tự/phần tử theo kiểu |
| @Digits | Giới hạn số chữ số và phần thập phân nếu được hỗ trợ |

Việc ánh xạ cụ thể phụ thuộc phiên bản Springdoc, swagger-core, Bean Validation provider và phiên bản OpenAPI được xuất. Không phải constraint tùy chỉnh nào cũng được chuyển tự động thành schema keyword.

Lưu ý rằng OpenAPI có hai khái niệm riêng: required quyết định property có phải xuất hiện trong object hay không, còn nullable/type quyết định property có được nhận giá trị null hay không. @NotNull là constraint runtime cấm null; cách nó được biểu diễn thành required, nullable hoặc cả hai cần được kiểm tra trong document sinh ra. Tương tự, minLength: 1 không thể diễn tả đầy đủ @NotBlank vì chuỗi chỉ gồm dấu cách vẫn có độ dài lớn hơn 0.

Ví dụ:

~~~java
public record AddressRequest(
    @NotBlank
    @Size(max = 120)
    String street,

    @NotBlank
    @Pattern(regexp = "^[A-Z]{2,3}$")
    String countryCode,

    @NotNull
    @Positive
    BigDecimal latitude
) {}
~~~

OpenAPI có thể mô tả độ dài tối đa của street, pattern của countryCode và giới hạn số của latitude. Dù vậy, cần kiểm tra JSON sinh ra thay vì giả định mọi annotation được ánh xạ giống nhau giữa các phiên bản.

## 12. @Valid không tự làm schema lồng nhau trở thành required

Một DTO có thể khai báo:

~~~java
public record OrderRequest(
    @Valid
    AddressRequest address
) {}
~~~

Kiểu AddressRequest giúp Springdoc biết cấu trúc object con và có thể tạo schema lồng nhau. @Valid kích hoạt cascade validation ở runtime. Tuy nhiên, chỉ @Valid không có nghĩa address bắt buộc xuất hiện.

Nếu address bắt buộc, khai báo:

~~~java
public record OrderRequest(
    @NotNull
    @Valid
    AddressRequest address
) {}
~~~

Springdoc có thể phản ánh constraint @NotNull vào schema theo phiên bản và cấu hình. Hãy xác minh cả danh sách required của object lẫn schema nullable để chắc rằng client hiểu đúng.

Tương tự, với collection:

~~~java
public record OrderRequest(
    @NotEmpty
    List<@Valid OrderLineRequest> items
) {}
~~~

@Valid kiểm tra từng phần tử, @NotEmpty yêu cầu collection có ít nhất một phần tử. Nếu item không được null, có thể thêm @NotNull trên type argument.

## 13. Validation groups và nested validation

Một DTO có thể được dùng trong nhiều luồng, chẳng hạn tạo mới và cập nhật. Validation groups cho phép chọn tập constraint theo từng thao tác.

Ví dụ định nghĩa nhóm:

~~~java
public interface OnCreate {}
public interface OnUpdate {}
~~~

DTO:

~~~java
public record ProductRequest(
    @NotBlank(groups = {OnCreate.class, OnUpdate.class})
    String name,

    @NotNull(groups = OnCreate.class)
    @Positive(groups = {OnCreate.class, OnUpdate.class})
    BigDecimal price
) {}
~~~

Controller có thể chọn group khi kích hoạt validation:

~~~java
@PostMapping("/api/products")
public ProductResponse create(
    @Validated(OnCreate.class)
    @RequestBody ProductRequest request
) {
    return productService.create(request);
}

@PutMapping("/api/products/{id}")
public ProductResponse update(
    @PathVariable Long id,
    @Validated(OnUpdate.class)
    @RequestBody ProductRequest request
) {
    return productService.update(id, request);
}
~~~

Trong thực tế, cần bảo đảm Default group và các group tùy chỉnh được cấu hình đúng; constraint không gắn group cụ thể thuộc Default. Khi cascade sang object con với một group khác, có thể dùng **@ConvertGroup** trên vị trí @Valid để ánh xạ group hiện tại sang group của object con.

Ví dụ:

~~~java
public record CreateOrderRequest(
    @Valid
    @ConvertGroup(from = Default.class, to = OnCreate.class)
    AddressRequest address
) {}
~~~

Validation group là hành vi runtime. Springdoc không thể tự tạo một schema duy nhất thể hiện đầy đủ mọi tập constraint khác nhau cho mọi group trong mọi operation. Nếu request create và update có hợp đồng khác nhau, dùng DTO riêng hoặc mô tả request schema riêng để client không phải đoán constraint nào đang áp dụng.

## 14. Validation ở cấp class và quy tắc liên trường

Một số quy tắc cần xem nhiều thuộc tính cùng lúc. Ví dụ ngày bắt đầu phải trước ngày kết thúc, hoặc ít nhất một trong email và phone phải được cung cấp.

Có thể tạo class-level constraint:

~~~java
@ValidDateRange
@Schema(description = "Ngày kết thúc phải sau ngày bắt đầu.")
public record BookingRequest(
    @NotNull LocalDate startDate,
    @NotNull LocalDate endDate
) {}
~~~

Validator tùy chỉnh sẽ kiểm tra quan hệ giữa startDate và endDate. OpenAPI Schema thường có thể thể hiện kiểu, required và constraint đơn lẻ của từng property, nhưng không phải lúc nào cũng diễn tả đầy đủ logic liên trường bằng JSON Schema.

Nếu không thể đặt metadata ở class như ví dụ, hãy bổ sung quy tắc trong description của schema hoặc operation. Validator tùy chỉnh vẫn cần được thực thi ở runtime; @Schema.description chỉ giải thích quy tắc cho người đọc tài liệu. Đồng thời khai báo response lỗi validation nếu client cần biết cấu trúc lỗi. Không nên cho rằng chỉ vì có custom validator thì Springdoc tự sinh ra một schema keyword tương đương.

## 15. Định nghĩa response lỗi validation

Khi validation thất bại, Spring MVC thường chuyển lỗi thành exception. Ứng dụng có thể dùng @RestControllerAdvice để chuẩn hóa response.

Ví dụ DTO lỗi:

~~~java
public record ValidationErrorResponse(
    String code,
    String message,
    List<FieldViolation> violations
) {}

public record FieldViolation(
    String field,
    String message
) {}
~~~

Exception handler:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ValidationErrorResponse> handleValidation(
        MethodArgumentNotValidException exception
    ) {
        List<FieldViolation> violations =
            exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldViolation(
                    error.getField(),
                    error.getDefaultMessage()
                ))
                .toList();

        ValidationErrorResponse body = new ValidationErrorResponse(
            "VALIDATION_FAILED",
            "Request chứa dữ liệu không hợp lệ",
            violations
        );

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Có thể công bố response 400 bằng OpenAPI:

~~~java
@ApiResponse(
    responseCode = "400",
    description = "Dữ liệu request không hợp lệ",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ValidationErrorResponse.class)
    )
)
~~~

Springdoc không nên được kỳ vọng tự suy ra mọi response lỗi từ toàn bộ @RestControllerAdvice trong mọi cấu hình. Hãy khai báo rõ response quan trọng ở operation hoặc dùng cấu hình response dùng chung, rồi kiểm tra tài liệu sinh ra.

Cũng cần phân biệt lỗi Jackson parse với lỗi Bean Validation. JSON sai định dạng có thể đi qua HttpMessageNotReadableException; constraint thất bại sau binding thường đi qua MethodArgumentNotValidException. Nếu API trả hai dạng lỗi khác nhau, tài liệu nên mô tả chúng riêng hoặc chuẩn hóa về một error response thống nhất.

## 16. Từ Jackson DTO đến OpenAPI Schema: ví dụ tổng hợp

Ví dụ request tạo đơn hàng:

~~~java
public record CreateOrderRequest(
    @JsonProperty("customer")
    @NotNull
    @Valid
    CustomerRequest customer,

    @JsonProperty("line_items")
    @NotEmpty
    @Size(max = 50)
    List<@NotNull @Valid OrderLineRequest> lineItems,

    @JsonProperty("delivery_note")
    @Size(max = 500)
    String deliveryNote
) {}

public record CustomerRequest(
    @JsonProperty("full_name")
    @NotBlank
    @Size(max = 120)
    String fullName,

    @Email
    String email,

    @NotNull
    @Valid
    AddressRequest address
) {}

public record AddressRequest(
    @NotBlank
    String street,

    @NotBlank
    String city,

    @Pattern(regexp = "^[A-Z]{2,3}$")
    String countryCode
) {}

public record OrderLineRequest(
    @NotNull
    @Positive
    Long productId,

    @NotNull
    @Min(1)
    Integer quantity
) {}
~~~

Controller:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public OrderResponse create(
    @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

Tài liệu OpenAPI cần phản ánh:

- Property JSON là customer, line_items và delivery_note theo Jackson mapping.
- customer là object bắt buộc, các trường con tuân theo CustomerRequest.
- line_items là array có tối đa 50 phần tử và không được rỗng.
- Mỗi phần tử line_items là OrderLineRequest và được kiểm tra cascade.
- delivery_note có giới hạn độ dài tối đa.
- full_name là chuỗi không rỗng, có giới hạn độ dài.
- address là object bắt buộc và được cascade validation.
- countryCode có pattern được công bố nếu constraint được hỗ trợ.
- Request body dùng application/json.

OpenAPI có thể biểu diễn phần lớn cấu trúc và constraint đơn lẻ. Quy tắc nghiệp vụ phức tạp hoặc phụ thuộc validation group vẫn cần mô tả thêm hoặc dùng schema/request DTO riêng.

## 17. Các lỗi thường gặp khi dùng @Valid với dữ liệu lồng nhau

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Object con không được kiểm tra | Thiếu @Valid tại thuộc tính hoặc một tầng lồng nhau |
| Object con null nhưng không báo lỗi | Có @Valid nhưng thiếu @NotNull |
| Collection rỗng vẫn hợp lệ | Có @Valid nhưng thiếu @NotEmpty hoặc @Size(min = 1) |
| Một phần tử collection null không bị từ chối | Thiếu @NotNull trên phần tử |
| Constraint trong từng phần tử không chạy | Cascade validation chưa được đặt đúng trên container/type argument |
| Tên property Swagger khác JSON | Jackson @JsonProperty hoặc naming strategy chưa được phản ánh như mong đợi |
| Property read-only vẫn xuất hiện ở request | Dùng chung DTO hoặc Jackson access mode/schema access chưa khớp |
| Schema báo required sai | Nhầm @Valid với @NotNull hoặc suy luận constraint khác phiên bản |
| Validation group không được áp dụng | Controller chưa kích hoạt đúng group hoặc thiếu group conversion khi cascade |
| Custom validator không xuất hiện trong schema | Springdoc không tự suy luận được quy tắc nghiệp vụ tùy chỉnh |
| JSON sai kiểu trả lỗi khác validation | Deserialize thất bại trước khi Bean Validation chạy |
| Schema có giới hạn nhưng backend không kiểm tra | Constraint không được kích hoạt hoặc chưa có provider validation |

Khi điều tra, hãy kiểm tra theo thứ tự: JSON thực tế, Jackson mapping, DTO sau deserialize, vị trí @Valid, constraint Bean Validation, exception handler và OpenAPI document. Cách này giúp xác định lỗi nằm ở binding, validation hay tài liệu.

## 18. Kiểm tra đồng bộ runtime và tài liệu OpenAPI

Sau khi cập nhật DTO hoặc annotation, tải OpenAPI JSON tại endpoint Springdoc, thường là:

~~~http
GET /v3/api-docs
~~~

Kiểm tra các mục:

1. Tên property có khớp Jackson serialization/deserialization không.
2. Object lồng nhau có schema đúng và tham chiếu component phù hợp không.
3. Collection có type array và items đúng không.
4. required phản ánh thuộc tính bắt buộc; nullable phản ánh khả năng nhận null.
5. minLength, maxLength, minimum, maximum, pattern, minItems và maxItems có đúng không.
6. readOnly/writeOnly có khớp Jackson access và hướng request/response không.
7. Validation group có làm các endpoint dùng cùng DTO cần schema khác nhau không.
8. Response 400 mô tả đúng lỗi validation và lỗi parse JSON không.

Nên viết integration test cho các trường hợp:

- Thiếu object con bắt buộc.
- Object con có trường rỗng hoặc sai format.
- Collection rỗng, vượt giới hạn hoặc chứa phần tử null.
- Một phần tử collection vi phạm constraint lồng sâu.
- JSON dùng tên property chuẩn, alias và tên sai.
- Property bị thiếu, null hoặc có giá trị.
- Ngày tháng, enum hoặc kiểu số sai định dạng.
- JSON không hợp lệ về cú pháp.

Test runtime xác nhận hành vi thật; kiểm tra OpenAPI xác nhận hợp đồng công bố. Hai việc này bổ sung cho nhau và giúp tránh tình trạng tài liệu mô tả một quy tắc mà server không thực thi.

## 19. Nguyên tắc thiết kế DTO lồng nhau

Để Jackson, Bean Validation và Springdoc phối hợp nhất quán:

1. Dùng DTO riêng cho request và response khi quyền đọc/ghi hoặc constraint khác nhau.
2. Dùng @Valid tại mỗi ranh giới object cần cascade validation.
3. Kết hợp @NotNull khi object con bắt buộc phải tồn tại.
4. Dùng @NotEmpty hoặc @Size khi collection cần giới hạn số phần tử.
5. Dùng type-use constraints để kiểm tra từng phần tử collection.
6. Khai báo @JsonProperty hoặc naming strategy rõ ràng nếu tên JSON khác tên Java.
7. Không xem @JsonInclude là cơ chế required hoặc validation.
8. Dùng validation groups có chủ đích; cân nhắc DTO riêng khi hợp đồng create/update khác nhau.
9. Mô tả class-level business rule trong description nếu schema không biểu diễn đầy đủ.
10. Kiểm tra OpenAPI JSON/YAML cùng integration test sau thay đổi DTO, Jackson hoặc validation.

@Valid giúp kiểm tra sâu qua cấu trúc object; Jackson quyết định dữ liệu JSON được ánh xạ thành cấu trúc Java nào; Bean Validation thực thi các constraint; Springdoc dùng metadata đó để mô tả hợp đồng. Khi các lớp này được cấu hình nhất quán, client có thể hiểu đúng cấu trúc request lồng nhau và server có thể từ chối dữ liệu không hợp lệ theo cùng quy tắc được công bố.

