# Document lỗi validation của form bằng Spring REST Docs

## 1. Vì sao cần tài liệu hóa lỗi form?

Một REST API nhận dữ liệu biểu mẫu không chỉ có response thành công. Client cũng cần biết server phản hồi thế nào khi thiếu trường bắt buộc, email sai định dạng, giá trị nằm ngoài tập cho phép hoặc dữ liệu không chuyển được sang kiểu Java. Nếu tài liệu chỉ có request hợp lệ và response `201 Created`, người tích hợp vẫn phải tự dò cách xử lý khi form bị từ chối.

Trong module **SPRING_REST_DOCS**, tài liệu REST API được sinh từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Với form `application/x-www-form-urlencoded`, Spring REST Docs có thể tạo snippet mô tả tham số bằng `formParameters(...)`, đồng thời tài liệu hóa response lỗi bằng `responseFields(...)`, `responseHeaders(...)` và các snippet HTTP tương ứng. Các bài kiểm thử là bằng chứng để tài liệu phản ánh hành vi thực tế của endpoint.

Bài này xây dựng một endpoint đăng ký nhận form, chuẩn hóa lỗi validation thành JSON ổn định và viết test để sinh tài liệu cho cả request hợp lệ lẫn request sai.

Sau bài học, bạn có thể:

1. Phân biệt lỗi binding, lỗi validation và lỗi nghiệp vụ.
2. Dùng Jakarta Bean Validation để kiểm tra dữ liệu form đã bind vào DTO.
3. Chuẩn hóa lỗi qua `@RestControllerAdvice` mà không làm lộ dữ liệu nhạy cảm.
4. Dùng MockMvc xác nhận status, cấu trúc error response và sinh snippet Spring REST Docs.
5. Nhúng snippet lỗi vào Asciidoctor/Markdown và đưa bước kiểm chứng vào CI.

## 2. Các loại lỗi khi nhận form

Giả sử endpoint `POST /registrations` nhận body:

```http
POST /registrations HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Accept: application/json

email=mai%40example.com&plan=pro&seats=2
```

| Loại lỗi | Ví dụ | Nơi thường phát hiện |
| --- | --- | --- |
| Thiếu trường bắt buộc | Không gửi `email` | Binding hoặc Bean Validation, tùy cách khai báo |
| Giá trị trống | `email=` | `@NotBlank` |
| Sai định dạng | `email=mai-at-example` | `@Email` |
| Ngoài tập giá trị | `plan=enterprise` khi chỉ nhận `basic`/`pro` | `@Pattern` hoặc validation nghiệp vụ |
| Ngoài miền số | `seats=0` khi yêu cầu từ 1 đến 5 | `@Min` / `@Max` |
| Sai kiểu dữ liệu | `seats=two` với thuộc tính số nguyên | Type conversion/binding |
| Vi phạm quy tắc liên trường | Ngày kết thúc trước ngày bắt đầu | Validator nghiệp vụ hoặc lớp service |

Nên phân biệt:

- **Binding/conversion:** chuyển các chuỗi form thành thuộc tính Java. Ví dụ `seats=two` không chuyển được sang `Integer`.
- **Validation:** kiểm tra giá trị đã bind, ví dụ `seats` nhỏ hơn 1 hoặc email sai định dạng.
- **Business rule:** điều kiện phụ thuộc trạng thái hệ thống, chẳng hạn mã khuyến mại đã hết hạn hoặc tài khoản đã tồn tại.

Các loại lỗi có thể xuất hiện ở các thời điểm khác nhau, do đó không nên giả định tất cả đều được xử lý bởi cùng một exception. Bài thực hành tập trung vào lỗi Bean Validation để giữ ví dụ dễ theo dõi; phần cuối nêu cách mở rộng cho lỗi binding và nghiệp vụ.

## 3. Thiết kế hợp đồng error response

Một error response tốt có cấu trúc ổn định để client có thể xử lý tự động. Ví dụ:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "code": "VALIDATION_FAILED",
  "message": "Dữ liệu biểu mẫu không hợp lệ",
  "errors": [
    {
      "field": "email",
      "code": "INVALID_FORMAT",
      "message": "Email không đúng định dạng"
    },
    {
      "field": "seats",
      "code": "OUT_OF_RANGE",
      "message": "Số lượng phải từ 1 đến 5"
    }
  ]
}
```

| Thuộc tính | Mục đích |
| --- | --- |
| `code` | Mã lỗi cấp request, ổn định để client rẽ nhánh |
| `message` | Thông điệp chung cho người đọc |
| `errors` | Danh sách lỗi theo từng trường |
| `errors[].field` | Tên field trong biểu mẫu |
| `errors[].code` | Mã lỗi máy đọc được cho field |
| `errors[].message` | Thông điệp giải thích lỗi field |

Chọn `400 Bad Request` hay `422 Unprocessable Content` là quyết định hợp đồng API; điều quan trọng là sử dụng nhất quán và mô tả rõ. Ví dụ dưới đây chọn `400` cho lỗi validation. Nếu hệ thống đang dùng `422`, hãy đổi test và tài liệu theo status đã chọn thay vì trộn cả hai.

Không nên đưa giá trị người dùng đã nhập vào response lỗi một cách mặc định. Dữ liệu có thể chứa mật khẩu, token, số định danh hoặc thông tin cá nhân. Tên field, mã lỗi và thông điệp đủ rõ thường đã đáp ứng nhu cầu client.

## 4. Tạo DTO form với Jakarta Bean Validation

Để form URL-encoded được bind theo nhóm trường, Spring MVC có thể dùng `@ModelAttribute` với một DTO. DTO có getter/setter để binder gán giá trị và các annotation validation để kiểm tra sau khi bind.

```java
package example.docs;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public class RegistrationForm {
    @NotBlank(message = "Email không được để trống")
    @Email(message = "Email không đúng định dạng")
    private String email;

    @NotBlank(message = "Gói đăng ký không được để trống")
    @Pattern(regexp = "basic|pro",
        message = "Gói đăng ký chỉ nhận basic hoặc pro")
    private String plan;

    @NotNull(message = "Số lượng là bắt buộc")
    @Min(value = 1, message = "Số lượng phải từ 1 đến 5")
    @Max(value = 5, message = "Số lượng phải từ 1 đến 5")
    private Integer seats;

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getPlan() { return plan; }
    public void setPlan(String plan) { this.plan = plan; }
    public Integer getSeats() { return seats; }
    public void setSeats(Integer seats) { this.seats = seats; }
}
```

Một vài điểm cần lưu ý:

- `@NotBlank` từ chối `null`, chuỗi rỗng và chuỗi chỉ chứa khoảng trắng.
- `@Email` kiểm tra hình dạng địa chỉ email theo validator đang sử dụng; nó không xác minh hộp thư tồn tại. Kết hợp `@NotBlank` vì `@Email` thường xem giá trị rỗng là hợp lệ.
- `@Pattern` giới hạn `plan` ở hai giá trị; biểu thức chính quy phân biệt chữ hoa/thường.
- `@Min` và `@Max` kiểm tra miền giá trị của `seats`. `@NotNull` bảo đảm trường có mặt; kiểu `Integer` có thể biểu diễn trạng thái thiếu bằng `null`.

## 5. Chuẩn hóa lỗi bằng `@RestControllerAdvice`

### 5.1. Kiểu dữ liệu response lỗi

Mỗi public top-level Java type nên nằm trong tệp riêng:

```java
// FieldViolation.java
package example.docs;

public record FieldViolation(String field, String code, String message) {
}
```

```java
// ValidationErrorResponse.java
package example.docs;

import java.util.List;

public record ValidationErrorResponse(
        String code,
        String message,
        List<FieldViolation> errors) {
}
```

### 5.2. Exception handler

```java
package example.docs;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiValidationExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ValidationErrorResponse> handleValidation(
            MethodArgumentNotValidException exception) {
        List<FieldViolation> violations =
                exception.getBindingResult().getFieldErrors()
                    .stream()
                    .map(this::toViolation)
                    .toList();

        ValidationErrorResponse body = new ValidationErrorResponse(
                "VALIDATION_FAILED",
                "Dữ liệu biểu mẫu không hợp lệ",
                violations);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(body);
    }

    private FieldViolation toViolation(FieldError error) {
        String code = switch (error.getCode() == null ? "" : error.getCode()) {
            case "NotBlank", "NotNull" -> "REQUIRED";
            case "Email" -> "INVALID_FORMAT";
            case "Min", "Max" -> "OUT_OF_RANGE";
            case "Pattern" -> "INVALID_VALUE";
            default -> "INVALID_VALUE";
        };
        return new FieldViolation(
                error.getField(),
                code,
                error.getDefaultMessage() == null
                        ? "Giá trị không hợp lệ"
                        : error.getDefaultMessage());
    }
}
```

Handler ánh xạ lỗi Bean Validation sang mã ổn định của API. Không nên để client phụ thuộc trực tiếp vào tên class exception hoặc mã validator nội bộ như `NotBlank`, vì các chi tiết đó có thể thay đổi theo thư viện/cấu hình. Có thể mở rộng mapping cho constraint mới và quy tắc nghiệp vụ.

Thông điệp trong ví dụ được viết tiếng Việt để minh họa. Ứng dụng đa ngôn ngữ nên dùng message source/locale và vẫn giữ `code` ổn định. Không đưa `FieldError.getRejectedValue()` vào response nếu không có lý do rõ ràng.

### 5.3. Controller nhận form

Thêm dependency validation nếu dự án Spring Boot chưa có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

Controller và response DTO:

```java
// RegistrationResponse.java
package example.docs;

public record RegistrationResponse(
        String id, String email, String plan, Integer seats) {
}
```

```java
// RegistrationController.java
package example.docs;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RegistrationController {

    @PostMapping(
        path = "/registrations",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<RegistrationResponse> create(
            @Valid @ModelAttribute RegistrationForm form) {
        RegistrationResponse response = new RegistrationResponse(
                "reg-demo",
                form.getEmail(),
                form.getPlan(),
                form.getSeats());
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
```

`@Valid` yêu cầu Spring chạy Bean Validation sau khi bind form vào DTO. Với `@ModelAttribute`, lỗi validation được báo qua `MethodArgumentNotValidException` khi không có `BindingResult` kế tiếp để controller tự xử lý. Nếu có `BindingResult`, controller phải chủ động xử lý lỗi; khi đó không nên mong exception handler ở trên tự nhận các lỗi đã được giữ lại trong `BindingResult`.

## 6. Kiểm thử MockMvc và sinh snippet lỗi

### 6.1. Dependency kiểm thử

Ví dụ dùng Spring Boot 3.x, Spring REST Docs và Gradle Groovy DSL:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Dependency management của dự án cần cung cấp phiên bản tương thích. Nếu dự án không dùng Spring Boot, cấu hình MockMvc và `RestDocumentationExtension` theo cách tích hợp Spring REST Docs đang sử dụng.

### 6.2. Test request hợp lệ

```java
package example.docs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RegistrationController.class)
@Import(ApiValidationExceptionHandler.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class RegistrationFormDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void validFormCreatesRegistration() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .accept(MediaType.APPLICATION_JSON)
                .param("email", "mai@example.com")
                .param("plan", "pro")
                .param("seats", "2"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("reg-demo"))
            .andDo(document("registrations/create",
                formParameters(
                    parameterWithName("email")
                        .description("Email hợp lệ; bắt buộc"),
                    parameterWithName("plan")
                        .description("Gói đăng ký: basic hoặc pro"),
                    parameterWithName("seats")
                        .description("Số lượng; số nguyên từ 1 đến 5")
                )
            ));
    }
}
```

Test thành công tạo snippet request và response mặc định, cùng `form-parameters.adoc`. `formParameters(...)` mô tả **các tên trường hợp lệ**; nó không mô tả error body và cũng không tự kiểm tra miền giá trị.

### 6.3. Test lỗi validation và document response

Thêm test sau vào class `RegistrationFormDocumentationTest`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

@Test
void invalidFormDocumentsValidationErrors() throws Exception {
    mockMvc.perform(post("/registrations")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .accept(MediaType.APPLICATION_JSON)
            .param("email", "not-an-email")
            .param("plan", "enterprise")
            .param("seats", "0"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.errors").isArray())
        .andDo(document("registrations/validation-error",
            formParameters(
                parameterWithName("email")
                    .description("Email hợp lệ; bắt buộc"),
                parameterWithName("plan")
                    .description("Gói đăng ký: basic hoặc pro"),
                parameterWithName("seats")
                    .description("Số lượng; số nguyên từ 1 đến 5")
            ),
            responseFields(
                fieldWithPath("code").description("Mã lỗi tổng quát"),
                fieldWithPath("message").description("Thông điệp tổng quát"),
                fieldWithPath("errors").description("Danh sách lỗi theo trường"),
                fieldWithPath("errors[].field").description("Tên trường bị lỗi"),
                fieldWithPath("errors[].code").description("Mã lỗi ổn định"),
                fieldWithPath("errors[].message").description("Thông điệp lỗi")
            )
        ));
}
```

Phần import static có thể gom lên đầu class cùng các import đang có. Trong response fields, path `errors[]...` mô tả từng phần tử của mảng. Spring REST Docs kiểm tra cấu trúc response theo descriptor và cảnh báo khi response có field chưa được tài liệu hóa hoặc field bắt buộc bị thiếu.

**Không phụ thuộc thứ tự lỗi trong mảng.** Validator có thể trả field errors theo thứ tự khác nhau tùy provider/cấu hình. Test chỉ khẳng định status, mã lỗi tổng và cấu trúc; nếu cần assertion cho từng lỗi, hãy tìm theo field/code thay vì gắn cứng chỉ số `errors[0]`.

### 6.4. Test thiếu trường và ngoài miền hợp lệ

```java
@Test
void missingEmailAndSeatsDocumentsRequiredErrors() throws Exception {
    mockMvc.perform(post("/registrations")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .accept(MediaType.APPLICATION_JSON)
            .param("plan", "basic"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.errors").isArray());
}

@Test
void unsupportedPlanIsRejected() throws Exception {
    mockMvc.perform(post("/registrations")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("email", "mai@example.com")
            .param("plan", "enterprise")
            .param("seats", "2"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
}
```

Hai test trên xác nhận hành vi server. Khi cần document nhiều biến thể lỗi, mỗi test có thể dùng identifier riêng (`registrations/missing-fields`, `registrations/invalid-plan`) và cùng một bộ `responseFields(...)`. Đừng dùng chung identifier cho các test tạo snippet khác nhau vì file output có nguy cơ bị ghi đè.

### 6.5. Kiểm tra lỗi chuyển kiểu (binding)

Nếu `seats=two`, Spring không thể chuyển chuỗi `"two"` thành `Integer`. Đây là lỗi binding/conversion, không phải lỗi `@Min`/`@Max`. Hành vi exception cụ thể phụ thuộc cách binding và cấu hình. Muốn tài liệu hóa loại lỗi này, bổ sung handler phù hợp cho `BindException`/`MethodArgumentNotValidException` hoặc exception tương ứng đã quan sát trong ứng dụng, sau đó viết test chứng minh status và error shape. Không gán nhãn `OUT_OF_RANGE` cho lỗi không chuyển được kiểu.

Tốt nhất là tạo một **error contract chung** cho binding và validation, ví dụ cùng `code`, `message`, `errors[]`, nhưng dùng mã field-level khác nhau:

| Tình huống | Mã lỗi field gợi ý |
| --- | --- |
| Không gửi trường bắt buộc | `REQUIRED` |
| Sai định dạng email | `INVALID_FORMAT` |
| Số ngoài giới hạn | `OUT_OF_RANGE` |
| Không chuyển chuỗi sang số | `INVALID_TYPE` |
| Giá trị không nằm trong enum/tập cho phép | `INVALID_VALUE` |

Nếu mở rộng exception handler cho lỗi binding, tránh trả nội dung exception kỹ thuật trực tiếp cho client; thông tin đó có thể chứa class name, raw input hoặc chi tiết nội bộ.

## 7. Đọc snippet được sinh

Với các test ở trên, thư mục output có dạng:

```text
build/generated-snippets/
└── registrations/
    ├── create/
    │   ├── form-parameters.adoc
    │   ├── http-request.adoc
    │   └── http-response.adoc
    └── validation-error/
        ├── form-parameters.adoc
        ├── response-fields.adoc
        ├── http-request.adoc
        └── http-response.adoc
```

Các snippet thể hiện hai mặt của cùng một hợp đồng:

- `form-parameters.adoc` nói rõ client gửi những trường nào và ý nghĩa của chúng.
- `http-request.adoc` thể hiện request cụ thể (trong test lỗi, các giá trị sai định dạng là dữ liệu minh họa).
- `response-fields.adoc` mô tả cấu trúc JSON lỗi mà client có thể đọc.
- `http-response.adoc` chứa status, header và body lỗi được ghi nhận từ test.

Ví dụ bảng response fields:

| Field path | Mô tả |
| --- | --- |
| `code` | Mã lỗi tổng quát |
| `message` | Thông điệp tổng quát |
| `errors` | Danh sách lỗi theo trường |
| `errors[].field` | Tên trường bị lỗi |
| `errors[].code` | Mã lỗi ổn định của trường |
| `errors[].message` | Thông điệp giải thích lỗi |

Snippet là kết quả từ request/response của test tại thời điểm chạy. Nếu error contract thay đổi, test và descriptor cần thay đổi cùng nhau; không chỉnh trực tiếp snippet sinh ra để làm tài liệu trông khớp.

## 8. Biên soạn tài liệu Asciidoctor và Markdown

Ví dụ trang `src/docs/asciidoc/index.adoc`:

```adoc
= Registration API

== Tạo đăng ký bằng form

=== Request parameters
include::{snippets}/registrations/create/form-parameters.adoc[]

=== Request ví dụ
include::{snippets}/registrations/create/http-request.adoc[]

=== Validation error
Khi dữ liệu form không hợp lệ, server trả HTTP 400.

==== Request gây lỗi
include::{snippets}/registrations/validation-error/http-request.adoc[]

==== Error response fields
include::{snippets}/registrations/validation-error/response-fields.adoc[]

==== HTTP response
include::{snippets}/registrations/validation-error/http-response.adoc[]
```

Biến `{snippets}` phải trỏ tới thư mục gốc chứa snippet (ví dụ `build/generated-snippets`). Lệnh `include::...[]` là cú pháp Asciidoctor. Nếu trang chính dùng Markdown, có thể liên kết tới HTML được Asciidoctor tạo ra hoặc có bước chuyển đổi được kiểm soát; không giả định Markdown renderer mặc định hiểu cú pháp include của AsciiDoc.

### 8.1. Nối test với bước build tài liệu

Với Gradle Groovy DSL và plugin Asciidoctor đã được cấu hình:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.absolutePath
}
```

CI có thể chạy:

```bash
./gradlew test asciidoctor
```

Quy trình cần đảm bảo:

1. Test HTTP tạo cả request hợp lệ và lỗi validation.
2. Spring REST Docs kiểm tra descriptor và sinh snippet tương ứng.
3. Asciidoctor đọc snippet từ đúng thư mục và render tài liệu.
4. CI thất bại nếu test hoặc bước render tài liệu thất bại.

Không dùng snippet cũ còn sót lại từ lần build trước làm bằng chứng tài liệu đã được kiểm chứng. Với pipeline nghiêm ngặt, dùng workspace build sạch hoặc cơ chế clean output phù hợp trước khi chạy.

## 9. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng giải quyết |
| --- | --- | --- |
| Thiếu trường mà không có error response tùy chỉnh | Controller chưa bật `@Valid`, thiếu dependency validation hoặc exception handler không xử lý exception thực tế | Kiểm tra `spring-boot-starter-validation`, annotation và loại exception |
| `@Email` không từ chối chuỗi rỗng | `@Email` thường cho phép giá trị rỗng | Kết hợp `@NotBlank` |
| `seats=two` không sinh lỗi `OUT_OF_RANGE` | Lỗi xảy ra trong chuyển đổi chuỗi sang số, trước Bean Validation | Xử lý lỗi binding riêng và kiểm thử |
| Error response có field mới nhưng snippet không mô tả | `responseFields(...)` chưa cập nhật descriptor | Thêm `fieldWithPath(...)` hoặc đánh dấu field nội bộ `.ignored()` có chủ ý |
| Test phụ thuộc thứ tự `errors[]` | Validator không cam kết thứ tự field errors | Tìm lỗi theo tên field và mã lỗi, không cố định index |
| Response bị lộ giá trị người dùng nhập | Handler trả `rejectedValue` hoặc exception message trực tiếp | Chỉ trả field, error code và thông điệp đã kiểm soát |
| Test invalid form không tạo snippet | Assertion status sai hoặc exception không được map như dự kiến | Xem exception thực tế, chuẩn hóa handler rồi chạy lại test |
| Asciidoctor không thấy snippet | Identifier hoặc `{snippets}` không khớp | Đối chiếu tên `document(...)`, thư mục output và dependency task |
| API trả `415` | `Content-Type` không khớp `consumes` | Gửi đúng `application/x-www-form-urlencoded` |

## 10. Bài tập thực hành

Tạo API `POST /feedback` nhận form URL-encoded với các trường:

- `email`: bắt buộc, đúng định dạng email.
- `rating`: bắt buộc, số nguyên từ 1 đến 5.
- `comment`: tùy chọn, tối đa 300 ký tự.
- `category`: bắt buộc, một trong `bug`, `feature`, `docs`.

Thực hiện:

1. Tạo DTO và khai báo các constraint phù hợp (`@NotBlank`, `@Email`, `@NotNull`, `@Min`, `@Max`, `@Size`, `@Pattern`).
2. Tạo error response thống nhất có `code`, `message` và `errors[]`.
3. Viết test thành công để sinh `form-parameters.adoc`.
4. Viết test email sai, rating ngoài giới hạn, category không hợp lệ và thiếu trường bắt buộc. Dùng `responseFields(...)` để sinh `response-fields.adoc`.
5. Bổ sung test lỗi binding với một giá trị số không chuyển đổi được và thiết kế mã lỗi riêng `INVALID_TYPE`.
6. Nhúng request, response và bảng lỗi vào Asciidoctor; chạy test và render tài liệu trong CI.

**Tiêu chí hoàn thành:** client biết trường nào sai, lỗi thuộc loại nào và cách sửa; response lỗi có schema ổn định; snippet được sinh từ test HTTP; khi hợp đồng lỗi thay đổi, CI yêu cầu cập nhật tài liệu tương ứng.

## Tài liệu tham khảo

- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Documenting Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Documenting HTTP Responses](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-responses.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — Model Attribute Methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Jakarta Bean Validation](https://beanvalidation.org/)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
