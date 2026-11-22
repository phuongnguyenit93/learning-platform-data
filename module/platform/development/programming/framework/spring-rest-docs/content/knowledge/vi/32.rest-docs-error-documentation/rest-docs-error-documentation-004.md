# Validation errors theo field và theo object

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, ta tạo tài liệu REST API có thể kiểm chứng bằng các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào quy trình build và CI.

Khi API xác thực dữ liệu đầu vào, lỗi có thể gắn với một field cụ thể hoặc với nhiều field cùng lúc. Ví dụ email sai định dạng là lỗi theo field; startDate lớn hơn endDate là lỗi theo object vì quy tắc cần so sánh hai giá trị. Với request lồng nhau và danh sách phần tử, API còn cần chỉ rõ đường dẫn tới vị trí không hợp lệ.

Bài học này hướng dẫn thiết kế và document validation errors theo field và theo object. Sau bài, bạn có thể:

- Phân biệt lỗi field-level, object-level và lỗi tổng quát của request.
- Thiết kế error payload chứa field path, code, message và rejected value theo chính sách an toàn.
- Ánh xạ Bean Validation errors thành response ổn định.
- Document nested fields, list elements và object-level errors bằng Spring REST Docs.
- Viết MockMvc test xác nhận cả status, error code lẫn vị trí validation.
- Tổ chức nhiều ví dụ validation trong tài liệu API và CI.

## 2. Field-level và object-level validation

### 2.1. Lỗi theo field

Field-level validation xảy ra khi một giá trị riêng lẻ không đáp ứng constraint:

~~~json
{
  "email": "not-an-email",
  "quantity": 0
}
~~~

Ví dụ:

- email không đúng định dạng.
- quantity nhỏ hơn giá trị tối thiểu.
- shippingAddress.postalCode để trống.

API có thể trả:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "One or more fields are invalid.",
  "errors": [
    {
      "field": "email",
      "code": "EMAIL_INVALID",
      "message": "Email must be a valid address."
    },
    {
      "field": "quantity",
      "code": "QUANTITY_MIN",
      "message": "Quantity must be at least 1."
    }
  ]
}
~~~

Mỗi phần tử chỉ ra một field cùng mã lỗi và thông điệp tương ứng.

### 2.2. Lỗi theo object

Object-level validation áp dụng cho quy tắc cần nhìn nhiều field hoặc trạng thái tổng thể:

~~~json
{
  "startDate": "2026-12-20",
  "endDate": "2026-12-10"
}
~~~

Quy tắc startDate phải trước hoặc bằng endDate không thể đánh giá chỉ từ một field. API có thể trả:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "The request contains an invalid combination of values.",
  "errors": [
    {
      "object": "bookingRequest",
      "code": "DATE_RANGE_INVALID",
      "message": "Start date must be on or before end date."
    }
  ]
}
~~~

Lỗi này gắn với object bookingRequest, không nhất thiết có một field đơn lẻ làm nguyên nhân. Nếu API muốn giúp người dùng sửa dữ liệu, có thể bổ sung relatedFields: ["startDate", "endDate"].

### 2.3. Lỗi tổng quát của request

Một số lỗi không gắn với field hay object cụ thể, chẳng hạn request body không parse được hoặc payload không phù hợp với loại thao tác:

~~~json
{
  "code": "REQUEST_BODY_INVALID",
  "message": "The request body could not be read."
}
~~~

Không gán một field giả chỉ để tất cả lỗi có cùng hình thức. Hãy phân biệt field path, object name và lỗi tổng quát.

## 3. Thiết kế error payload cho validation

Một schema có thể biểu diễn cả ba dạng:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "One or more values are invalid.",
  "errors": [
    {
      "scope": "FIELD",
      "path": "items[0].quantity",
      "code": "QUANTITY_MIN",
      "message": "Quantity must be at least 1."
    },
    {
      "scope": "OBJECT",
      "path": "bookingRequest",
      "relatedFields": [
        "startDate",
        "endDate"
      ],
      "code": "DATE_RANGE_INVALID",
      "message": "Start date must be on or before end date."
    },
    {
      "scope": "REQUEST",
      "code": "REQUEST_BODY_INVALID",
      "message": "The request body could not be read."
    }
  ],
  "traceId": "req-validation-001"
}
~~~

Ý nghĩa:

| Field | Ý nghĩa |
| --- | --- |
| code | Mã tổng quát hoặc mã lỗi cụ thể, ổn định cho client. |
| message | Thông điệp ở cấp response hoặc từng lỗi. |
| errors | Danh sách lỗi được phát hiện. |
| errors[].scope | Phạm vi lỗi: FIELD, OBJECT hoặc REQUEST. |
| errors[].path | Đường dẫn tới field/object nếu có. |
| errors[].relatedFields | Các field liên quan tới một quy tắc liên trường. |
| errors[].code | Mã lỗi cụ thể cho phần tử lỗi. |
| errors[].message | Giải thích lỗi cụ thể. |
| traceId | Mã tương quan để tra cứu log, nếu được cấp. |

Đây là schema minh họa, không phải cấu trúc bắt buộc của Spring. Dự án có thể dùng field, object, rejectedValue hoặc cấu trúc khác; điều quan trọng là tài liệu mô tả chính xác payload mà API trả.

Không trả rejected value mặc định cho mọi lỗi. Giá trị người dùng gửi có thể chứa mật khẩu, token, dữ liệu cá nhân hoặc nội dung không an toàn để ghi log. Nếu cần phản hồi giá trị sai, chỉ làm vậy với loại dữ liệu được phép và có quy tắc che dữ liệu.

## 4. Khai báo field-level constraints bằng Bean Validation

Ví dụ request DTO:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public record CreateOrderRequest(
    @NotBlank
    String customerName,

    @NotBlank
    @Email
    String email,

    @NotNull
    @Valid
    AddressRequest shippingAddress,

    @NotEmpty
    List<@Valid OrderItemRequest> items
) {
}

public record AddressRequest(
    @NotBlank String street,
    @NotBlank String postalCode
) {
}

public record OrderItemRequest(
    @NotBlank String productId,
    @Min(1) int quantity
) {
}
~~~

Spring MVC kích hoạt Bean Validation cho request body khi controller dùng @Valid hoặc @Validated phù hợp:

~~~java
@PostMapping("/api/orders")
ResponseEntity<?> createOrder(
        @Valid @RequestBody CreateOrderRequest request) {
    // Create order
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
~~~

@Valid trên nested DTO và collection element giúp validation đi sâu vào object con. Nếu thiếu cascade validation, constraint trong shippingAddress hoặc từng items có thể không được đánh giá.

Với ví dụ trên, field path có thể là:

- email
- shippingAddress.postalCode
- items[0].quantity

Path thực tế phụ thuộc tên thuộc tính, cấu trúc DTO và cách framework tạo binding error. Test cần xác nhận đường dẫn mà API công bố.

## 5. Object-level constraint với class-level validation

Để kiểm tra quan hệ giữa hai field, tạo annotation constraint ở cấp class:

~~~java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface ValidDateRange {
    String message() default "Start date must be on or before end date.";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, BookingRequest> {

    @Override
    public boolean isValid(
            BookingRequest value,
            ConstraintValidatorContext context) {
        if (value == null
                || value.startDate() == null
                || value.endDate() == null) {
            return true;
        }

        return !value.startDate().isAfter(value.endDate());
    }
}
~~~

Request DTO:

~~~java
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

@ValidDateRange
public record BookingRequest(
    @NotNull LocalDate startDate,
    @NotNull LocalDate endDate
) {
}
~~~

Class-level constraint thường tạo object error không có property path cụ thể. Có thể tùy chỉnh ConstraintValidatorContext để gắn violation vào một field:

~~~java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        "Start date must be on or before end date.")
    .addPropertyNode("startDate")
    .addConstraintViolation();
~~~

Khi gắn vào startDate, violation được xem như field-level để giao diện người dùng đánh dấu input cụ thể. Nếu quy tắc thực sự liên quan cả hai field, giữ object-level error và cung cấp relatedFields rõ ràng thường trung thực hơn.

## 6. Ánh xạ BindingResult thành error response

Trong Spring MVC, validation của @Valid @RequestBody có thể ném MethodArgumentNotValidException. Một @RestControllerAdvice có thể chuyển các field errors và global errors thành schema API:

~~~java
@RestControllerAdvice
class ValidationExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ValidationErrorResponse> handleValidation(
            MethodArgumentNotValidException exception) {

        List<ValidationErrorItem> errors = new ArrayList<>();

        exception.getBindingResult().getFieldErrors().forEach(error ->
            errors.add(new ValidationErrorItem(
                "FIELD",
                error.getField(),
                error.getCode(),
                error.getDefaultMessage()
            ))
        );

        exception.getBindingResult().getGlobalErrors().forEach(error ->
            errors.add(new ValidationErrorItem(
                "OBJECT",
                null,
                error.getCode(),
                error.getDefaultMessage()
            ))
        );

        return ResponseEntity.badRequest().body(
            new ValidationErrorResponse(
                "VALIDATION_FAILED",
                "One or more values are invalid.",
                errors
            )
        );
    }
}
~~~

Các record minh họa:

~~~java
public record ValidationErrorResponse(
    String code,
    String message,
    List<ValidationErrorItem> errors
) {
}

public record ValidationErrorItem(
    String scope,
    String path,
    String code,
    String message
) {
}
~~~

Đoạn code minh họa cách phân biệt getFieldErrors() và getGlobalErrors(). Trong dự án thật, cần xử lý null/empty path, message localization, mã lỗi ổn định và các lỗi binding không phải Bean Validation theo hợp đồng đã chọn.

Không dùng error.getCode() như mã API ổn định mà không kiểm soát. Bean Validation code có thể là tên constraint như NotBlank hoặc Email; API nên ánh xạ sang mã công khai có versioning và ý nghĩa rõ ràng.

## 7. Document field path lồng nhau

Spring REST Docs mô tả response JSON bằng responseFields(...) và fieldWithPath(...). Ví dụ payload:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "One or more fields are invalid.",
  "errors": [
    {
      "scope": "FIELD",
      "path": "shippingAddress.postalCode",
      "code": "POSTAL_CODE_REQUIRED",
      "message": "Postal code is required."
    }
  ]
}
~~~

Descriptors:

~~~java
responseFields(
    fieldWithPath("code")
        .description("Mã lỗi tổng quát của response validation."),
    fieldWithPath("message")
        .description("Thông điệp tổng quát."),
    fieldWithPath("errors")
        .description("Danh sách lỗi validation."),
    fieldWithPath("errors[].scope")
        .description("Phạm vi lỗi: FIELD hoặc OBJECT."),
    fieldWithPath("errors[].path")
        .description("Đường dẫn field hoặc object gây lỗi."),
    fieldWithPath("errors[].code")
        .description("Mã lỗi ổn định cho trường hợp cụ thể."),
    fieldWithPath("errors[].message")
        .description("Thông điệp giải thích lỗi.")
)
~~~

Đường dẫn errors[] chỉ phần tử trong mảng. Các field con được mô tả một lần và áp dụng cho từng phần tử. Nếu field path có thể null với object-level error, descriptor phải phản ánh đúng khả năng vắng mặt/null theo payload thực tế.

### 7.1. Field tùy chọn hoặc nullable

Nếu object-level error không có path:

~~~java
fieldWithPath("errors[].path")
    .description("Đường dẫn field/object; null với lỗi không gắn một path cụ thể.")
    .optional()
~~~

Trong REST Docs, optional() cho biết field có thể vắng mặt. Nếu JSON luôn chứa key path với giá trị null, field vẫn hiện diện; mô tả nên nói rõ có thể null. Không nhầm field vắng mặt với field hiện diện có giá trị null.

## 8. Document lỗi trong collection và nested object

Request lồng nhau có thể tạo path sâu:

~~~json
{
  "customer": {
    "email": "bad-address"
  },
  "items": [
    {
      "productId": "BOOK-01",
      "quantity": 0
    }
  ]
}
~~~

Một response validation có thể chỉ ra:

~~~json
{
  "errors": [
    {
      "scope": "FIELD",
      "path": "customer.email",
      "code": "EMAIL_INVALID",
      "message": "Email must be a valid address."
    },
    {
      "scope": "FIELD",
      "path": "items[0].quantity",
      "code": "QUANTITY_MIN",
      "message": "Quantity must be at least 1."
    }
  ]
}
~~~

Quy ước path nên ổn định và dễ đọc. Có thể dùng dot notation cho object và bracket index cho collection. Nếu API chọn JSON Pointer, ví dụ /items/0/quantity, hãy dùng nhất quán ở mọi endpoint và document format đó.

Không nhầm path trong error response với descriptor path của REST Docs. errors[].path là giá trị dữ liệu mà API trả; fieldWithPath("errors[].path") là đường dẫn tới field trong JSON response được REST Docs mô tả.

## 9. Document object-level error và related fields

Ví dụ response:

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "scope": "OBJECT",
      "path": "bookingRequest",
      "relatedFields": [
        "startDate",
        "endDate"
      ],
      "code": "DATE_RANGE_INVALID",
      "message": "Start date must be on or before end date."
    }
  ]
}
~~~

Descriptors:

~~~java
responseFields(
    fieldWithPath("code").description("Mã lỗi tổng quát."),
    fieldWithPath("errors").description("Danh sách validation errors."),
    fieldWithPath("errors[].scope").description("Phạm vi lỗi; OBJECT với quy tắc liên trường."),
    fieldWithPath("errors[].path").description("Tên object hoặc path chứa quy tắc."),
    fieldWithPath("errors[].relatedFields").description("Các field tham gia quy tắc."),
    fieldWithPath("errors[].relatedFields[]").description("Tên một field liên quan."),
    fieldWithPath("errors[].code").description("Mã lỗi quy tắc liên trường."),
    fieldWithPath("errors[].message").description("Giải thích điều kiện không được đáp ứng.")
)
~~~

Khi cùng một schema có field relatedFields chỉ xuất hiện ở object-level errors, có thể đánh dấu optional nếu response field thực sự có thể vắng mặt ở các lỗi field-level. Nếu muốn tránh một schema nhiều field tùy chọn, API có thể tách fieldErrors và objectErrors thành hai collection có cấu trúc riêng.

## 10. Ví dụ MockMvc test cho field-level validation

Ví dụ test giả định endpoint tạo đơn hàng trả 400 khi email không hợp lệ. REST Docs ghi body error và mô tả từng field:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@Import(ValidationExceptionHandler.class)
class OrderValidationDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentsInvalidEmail() throws Exception {
        this.mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerName": "An",
                      "email": "bad-address",
                      "shippingAddress": {
                        "street": "1 Main Street",
                        "postalCode": "10000"
                      },
                      "items": [
                        {"productId": "BOOK-01", "quantity": 1}
                      ]
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.errors[0].path").value("email"))
            .andDo(document("orders/validation-invalid-email",
                responseFields(
                    fieldWithPath("code").description("Mã lỗi tổng quát."),
                    fieldWithPath("message").description("Thông điệp tổng quát."),
                    fieldWithPath("errors").description("Danh sách validation errors."),
                    fieldWithPath("errors[].scope").description("Phạm vi lỗi."),
                    fieldWithPath("errors[].path").description("Đường dẫn field hoặc object."),
                    fieldWithPath("errors[].code").description("Mã lỗi cụ thể."),
                    fieldWithPath("errors[].message").description("Thông điệp lỗi.")
                )
            ));
    }
}
~~~

Trong test thực tế, cần bảo đảm các field khác hợp lệ để chỉ tạo lỗi email. Nếu request có nhiều lỗi, assertion nên tìm đúng phần tử theo path/code thay vì giả định lỗi luôn nằm ở index 0.

## 11. Ví dụ object-level validation test

Giả sử booking request có startDate sau endDate và validator tạo global error:

~~~java
mockMvc.perform(post("/api/bookings")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "startDate": "2026-12-20",
              "endDate": "2026-12-10"
            }
            """))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.errors[0].scope").value("OBJECT"))
    .andExpect(jsonPath("$.errors[0].code").value("DATE_RANGE_INVALID"))
    .andDo(document("bookings/validation-date-range",
        responseFields(
            fieldWithPath("code").description("Mã lỗi tổng quát."),
            fieldWithPath("errors").description("Danh sách validation errors."),
            fieldWithPath("errors[].scope").description("Phạm vi lỗi."),
            fieldWithPath("errors[].path").description("Object chứa quy tắc."),
            fieldWithPath("errors[].code").description("Mã lỗi liên trường."),
            fieldWithPath("errors[].message").description("Giải thích quy tắc.")
        )
    ));
~~~

Đây là object-level error vì điều kiện phụ thuộc hai ngày. Nếu handler ánh xạ global error thành scope=OBJECT, tài liệu và client có thể phân biệt nó với field-level error.

## 12. Phân biệt lỗi validation với lỗi binding và parse

Không phải mọi lỗi trước khi controller chạy đều là Bean Validation:

| Nhóm | Ví dụ | Cách phân biệt |
| --- | --- | --- |
| Bean Validation | @NotBlank, @Email, @Min không đạt | Dữ liệu đã bind nhưng vi phạm constraint. |
| Type conversion/binding | Chuỗi không chuyển được sang số hoặc ngày | Request không bind được vào kiểu Java mong đợi. |
| JSON parse | JSON sai cú pháp hoặc kiểu dữ liệu không đọc được | Message converter không tạo được object request. |
| Object-level rule | startDate > endDate | Quy tắc cần đánh giá toàn bộ object/nhiều field. |

Spring MVC có thể ném các exception khác nhau cho các nhóm này, ví dụ MethodArgumentNotValidException cho validation của request body và HttpMessageNotReadableException cho lỗi đọc body. Nếu API dùng chung error envelope, vẫn nên có code khác nhau để client biết lỗi cần sửa ở đâu.

Đừng gán EMAIL_INVALID cho một request JSON sai cú pháp. Mã lỗi phải phản ánh giai đoạn và nguyên nhân thực tế.

## 13. Quy tắc ổn định cho field path và error code

Để client có thể xử lý validation errors lâu dài:

- Dùng tên field trong hợp đồng JSON, không dùng tên biến Java nội bộ nếu chúng khác nhau.
- Giữ format path nhất quán: dot notation, bracket index hoặc JSON Pointer.
- Dùng error code ổn định; message có thể được bản địa hóa hoặc chỉnh câu chữ.
- Xác định cách biểu diễn object-level error và related fields.
- Quy định thứ tự lỗi nếu client/test cần output ổn định; nếu không, test nên tìm lỗi theo path/code thay vì index.
- Không trả rejected value nhạy cảm.

Nếu đổi tên field JSON, hãy xem các error path tương ứng là phần hợp đồng cần cập nhật và version/announce theo chính sách tương thích của API.

## 14. Tích hợp Asciidoctor

Tài liệu có thể tách ví dụ validation theo field và object:

~~~asciidoc
== Validation errors

=== Email không hợp lệ

include::{snippets}/orders/validation-invalid-email/http-response.adoc[]
include::{snippets}/orders/validation-invalid-email/response-fields.adoc[]

=== Khoảng ngày không hợp lệ

include::{snippets}/bookings/validation-date-range/http-response.adoc[]
include::{snippets}/bookings/validation-date-range/response-fields.adoc[]
~~~

Snippet cho thấy response thực tế đã được test; phần văn bản xung quanh giải thích cách người dùng API sửa field hoặc điều chỉnh tổ hợp giá trị.

## 15. Tích hợp Gradle và CI

Giả sử plugin Asciidoctor đã được cấu hình, nối task tài liệu với test:

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

Chạy:

~~~bash
./gradlew clean test asciidoctor
~~~

CI xác nhận validation handler trả đúng status, field path, object scope và error code trước khi ghép snippets. Nếu constraint hoặc schema thay đổi mà tài liệu không được cập nhật, assertion hoặc REST Docs descriptors sẽ làm build thất bại.

Với Markdown thuần, cú pháp include:: của Asciidoctor không tự được xử lý; cần bước build riêng để nhúng snippet hoặc liên kết tới tệp được sinh.

## 16. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân và cách xử lý |
| --- | --- |
| Nested field không có lỗi | Thiếu @Valid ở DTO con hoặc collection element. |
| Object-level rule không chạy | Constraint chưa gắn ở cấp class hoặc validator chưa được đăng ký. |
| Object error bị document như field error | Handler chỉ đọc getFieldErrors() mà bỏ getGlobalErrors(). |
| Path trong response là tên Java property không đúng | Ánh xạ theo tên field JSON công khai và kiểm thử khi dùng @JsonProperty. |
| Lỗi collection có index không ổn định | Dữ liệu test hoặc thứ tự collection thay đổi; assertion theo path/code thay vì vị trí cố định. |
| REST Docs báo undocumented field | Response có field chưa được mô tả; bổ sung descriptor hoặc xử lý field theo hợp đồng. |
| Optional field bị hiểu nhầm là nullable | Mô tả rõ key có thể vắng mặt hay hiện diện với giá trị null. |
| Error code thay đổi theo tên constraint | Ánh xạ constraint nội bộ sang mã API ổn định. |
| Snippet chứa rejected value nhạy cảm | Bỏ field đó khỏi payload hoặc che bằng chính sách phù hợp; dùng fixture giả trong test. |

## 17. Bài thực hành

1. Tạo DTO có email, nested shipping address và list items với các constraint.
2. Gửi request có email sai và quantity bằng 0; xác định các field paths.
3. Tạo class-level constraint so sánh startDate và endDate.
4. Ánh xạ FieldError và ObjectError thành hai scope khác nhau.
5. Viết MockMvc test riêng cho field-level và object-level validation.
6. Document errors[] bằng responseFields, bao gồm nested paths và relatedFields.
7. Kiểm tra trường hợp path có thể null/vắng mặt và mô tả đúng optional semantics.
8. Tạo test JSON parse error để phân biệt với Bean Validation.
9. Include snippets vào Asciidoctor và chạy Gradle/CI.

## 18. Ghi nhớ

- Field-level error gắn với một thuộc tính; object-level error gắn với quy tắc cần nhiều field hoặc toàn bộ object.
- Nested validation cần cascade bằng @Valid; collection element cũng phải được validate.
- Bean Validation errors, binding errors và JSON parse errors là các nhóm khác nhau.
- Dùng FieldError và ObjectError để ánh xạ scope/path phù hợp; không coi constraint code nội bộ là API error code nếu chưa chuẩn hóa.
- Document field path theo tên JSON công khai và giữ format path ổn định.
- Dùng responseFields(...) và fieldWithPath(...) để mô tả mảng lỗi và các field lồng nhau; đánh dấu optional đúng với hợp đồng.
- Test status, error code và field/object path trước khi REST Docs sinh snippet.

## 19. Tài liệu tham khảo

- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Bean Validation, nested validation và tích hợp Spring.
- [Spring REST Docs — Payload Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/payloads.html): field descriptors, nested paths, optional fields và subsection documentation.
- [Jakarta Bean Validation](https://beanvalidation.org/): constraint annotations và custom class-level validators.
