# Tùy chỉnh BindingErrorProcessor khi có hợp đồng lỗi riêng

## 1. Bài toán và mục tiêu

Trong một API Spring MVC, request có thể gửi form như `age=abc` dù thuộc tính Java là `Integer age`. Spring cố chuyển `"abc"` thành số và ghi lỗi binding vào `BindingResult`. Một request khác có thể không gửi trường bắt buộc `email`. Mặc định Spring dùng các mã như `required` và `typeMismatch`, phù hợp với cơ chế hiển thị lỗi chung.

Tuy nhiên, một hệ thống có **hợp đồng lỗi (error contract)** riêng có thể quy định mã dành cho client:

| Tình huống | Mã lỗi API mong muốn |
| --- | --- |
| Thiếu field bắt buộc trong property binding | `INPUT_REQUIRED` |
| Không chuyển được giá trị sang kiểu đích | `INPUT_TYPE` |
| Không thể gán property vì lỗi khác | `INPUT_PROPERTY` |
| Dữ liệu đã bind nhưng không đạt quy tắc nghiệp vụ | `VALIDATION_FAILED` |

Mã lỗi cần ổn định qua các bản phát hành và không phụ thuộc vào ngôn ngữ hiển thị. Khi đó có thể cần tùy chỉnh **`org.springframework.validation.BindingErrorProcessor`**: chiến lược cho phép quyết định **lỗi được ghi vào `BindingResult` như thế nào** khi thiếu required field hoặc có `PropertyAccessException`.

Bài học này hướng dẫn lựa chọn đúng điểm mở rộng, triển khai processor, gắn vào `DataBinder`/`WebDataBinder`, giữ metadata lỗi, kiểm thử hợp đồng và phân biệt với validation/JSON parsing. Ví dụ dùng **Java 17+ và Spring Framework 6.2.x**. Phần Spring MVC phù hợp với dự án Spring Boot 3.x có Spring Web tương ứng.

## 2. BindingErrorProcessor nằm ở đâu trong vòng đời binding?

Với JavaBean mutable và `DataBinder.bind(PropertyValues)`, luồng tổng quát:

~~~text
Form/query parameters hoặc PropertyValues
                 |
                 v
             DataBinder
                 |
       allowedFields / requiredFields
                 |
          +------+-------+
          |              |
    Thiếu field?    Gán giá trị property
          |              |
          |        Chuyển kiểu / gọi setter
          |              |
          |        PropertyAccessException?
          |              |
          v              v
processMissing...   processPropertyAccessException(...)
          |              |
          +------+-------+
                 |
                 v
            BindingResult
       FieldError / ObjectError
                 |
                 v
      Controller / API response
~~~

Theo `DefaultBindingErrorProcessor`, Spring thường dùng mã cơ sở:

- `required`: required field thiếu.
- `typeMismatch`: giá trị không thể chuyển sang kiểu property.
- `methodInvocation`: thao tác gọi setter/phương thức không thực hiện được.

Mã cơ sở có thể được mở rộng thành nhiều ứng viên như `typeMismatch.registration.age`, `typeMismatch.age` và `typeMismatch` nhờ `MessageCodesResolver`. Điều này giúp ứng dụng tra thông điệp chi tiết theo object và field.

**Phạm vi giới hạn:** BindingErrorProcessor không xử lý mọi lỗi HTTP 400. Nó không trực tiếp xử lý JSON sai cú pháp ở `@RequestBody`, exception xác thực, lỗi phân quyền, hay constraint do Jakarta Bean Validation tạo ra. Những lỗi này có cơ chế riêng.

## 3. Interface và dữ liệu cần giữ lại

`BindingErrorProcessor` có hai callback chính:

~~~java
void processMissingFieldError(
        String missingField,
        BindingResult bindingResult);

void processPropertyAccessException(
        PropertyAccessException exception,
        BindingResult bindingResult);
~~~

Đoạn trên minh họa chữ ký API, **không phải một tệp Java độc lập**.

- `processMissingFieldError` nhận tên field mà `DataBinder` xác định bị thiếu dựa trên cấu hình `setRequiredFields(...)`.
- `processPropertyAccessException` nhận lỗi xảy ra khi truy cập/gán property.
- Cả hai được trao `BindingResult` để tạo `FieldError` hoặc `ObjectError`. Implementation có thể quyết định mã, rejected value, thông điệp và loại lỗi.

Một `FieldError` có các đặc tính quan trọng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `objectName` | Tên model attribute, ví dụ `registration` |
| `field` | Property gặp lỗi, ví dụ `age` |
| `rejectedValue` | Giá trị đầu vào bị từ chối, nếu được giữ |
| `bindingFailure` | `true` nếu lỗi phát sinh trong quá trình binding |
| `codes` | Danh sách mã ứng viên để `MessageSource` tra thông điệp |
| `defaultMessage` | Nội dung dự phòng |

Đổi mã lỗi mà vẫn giữ các metadata liên quan giúp Spring MVC, template rendering và các thành phần kiểm tra lỗi tiếp tục làm việc. Ví dụ một controller có thể gọi `result.hasFieldErrors("age")` dù code đã được đổi thành `INPUT_TYPE`.

**Tránh lặng lẽ bỏ qua callback**: nếu processor không ghi lỗi, controller có thể nhận `hasErrors() == false` rồi xử lý một đối tượng chưa phù hợp.

## 4. Thiết kế hợp đồng trước khi code

Giả sử một endpoint nhận form có `email` và `age`:

- Không có `email`: code `INPUT_REQUIRED`.
- `age=abc`: code `INPUT_TYPE`.
- Exception gán property khác lỗi chuyển kiểu: `INPUT_PROPERTY`.
- Body HTTP 400 chỉ đưa ra `field`, `code`, `message`; không lộ rejected value hoặc stack trace.
- Code ổn định, message có thể dịch sang các locale.
- Validation nghiệp vụ (chẳng hạn `age >= 18`) do validator xử lý riêng.

Ví dụ JSON hợp đồng:

~~~json
{
  "errors": [
    {
      "field": "email",
      "code": "INPUT_REQUIRED",
      "message": "Dữ liệu đầu vào không hợp lệ"
    },
    {
      "field": "age",
      "code": "INPUT_TYPE",
      "message": "Dữ liệu đầu vào không hợp lệ"
    }
  ]
}
~~~

Đây là **một API contract do ứng dụng lựa chọn**, không phải body mặc định do Spring cung cấp. Không nên yêu cầu client phụ thuộc thứ tự hai lỗi; nếu thứ tự là một phần hợp đồng thì phải quy định và kiểm thử rõ.

## 5. Viết ApiBindingErrorProcessor

Tệp `src/main/java/demo/ApiBindingErrorProcessor.java`:

~~~java
package demo;

import org.springframework.beans.PropertyAccessException;
import org.springframework.validation.BindingErrorProcessor;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

public final class ApiBindingErrorProcessor
        implements BindingErrorProcessor {

    public static final String INPUT_REQUIRED = "INPUT_REQUIRED";
    public static final String INPUT_TYPE = "INPUT_TYPE";
    public static final String INPUT_PROPERTY = "INPUT_PROPERTY";

    @Override
    public void processMissingFieldError(
            String field, BindingResult result) {

        String[] codes = result.resolveMessageCodes(
                INPUT_REQUIRED, field);

        result.addError(new FieldError(
                result.getObjectName(),
                field,
                null,
                true,
                codes,
                null,
                "Thiếu trường bắt buộc"
        ));
    }

    @Override
    public void processPropertyAccessException(
            PropertyAccessException exception,
            BindingResult result) {

        String field = exception.getPropertyName();

        if (field == null || field.isBlank()) {
            result.addError(new ObjectError(
                    result.getObjectName(),
                    new String[]{INPUT_PROPERTY},
                    null,
                    "Không thể gán thuộc tính đối tượng"
            ));
            return;
        }

        String code = "typeMismatch".equals(
                exception.getErrorCode())
                ? INPUT_TYPE : INPUT_PROPERTY;

        result.addError(new FieldError(
                result.getObjectName(),
                field,
                exception.getValue(),
                true,
                result.resolveMessageCodes(code, field),
                null,
                "Giá trị đầu vào không phù hợp"
        ));
    }
}
~~~

Class này cài đặt đầy đủ hai method của Spring `BindingErrorProcessor` và không lưu dữ liệu theo request vào field.

Giải thích các quyết định:

1. `resolveMessageCodes(code, field)` cho Spring tạo danh sách code theo object/field/type để `MessageSource` có thể phân giải thông điệp chuyên biệt.
2. `FieldError(..., true, ...)` đánh dấu đây là **binding failure**. `FieldError#isBindingFailure()` vẫn hữu ích ngay cả khi application code đổi mã từ `typeMismatch` sang `INPUT_TYPE`.
3. `exception.getErrorCode()` được dùng để tách lỗi `typeMismatch` khỏi lỗi property access khác. Không phải mọi `PropertyAccessException` đều là sai kiểu.
4. `exception.getValue()` giúp giữ rejected value **nội bộ** khi cần render form. Controller mẫu sẽ không gửi giá trị này ra HTTP.
5. Trường hợp không xác định được tên property được chuyển thành `ObjectError`; API response chuyên biệt cần quyết định cách serialize global errors.
6. Processor stateless cho phép dùng chung với nhiều request, trong khi `BindingResult` luôn là tham số của lần gọi hiện tại.

### Dùng interface hay kế thừa implementation mặc định?

Nếu cần thay đổi rất ít so với hành vi mặc định, có thể `extends DefaultBindingErrorProcessor` và override một phương thức. Cách đó giúp giữ những hành vi khác của Spring, như thông tin exception đã bọc và message arguments. Khi tự `implements BindingErrorProcessor` như trên, bạn chịu trách nhiệm giữ những metadata cần thiết.

Đoạn ví dụ chủ ý tập trung vào hợp đồng mã lỗi. Nếu ứng dụng yêu cầu giữ exception gốc để giải thích lỗi cho đội vận hành, cần nghiên cứu thêm `FieldError.wrap(...)` và cách `DefaultBindingErrorProcessor` quản lý diagnostic, thay vì đưa message kỹ thuật ra client.

## 6. Chương trình Java 17+ chạy không cần HTTP server

Để kiểm tra processor, có thể dùng `DataBinder` trực tiếp.

### 6.1. Cấu hình Gradle

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'binding-error-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.BindingErrorDemo'
}
~~~

Trong dự án Spring Boot, nên dùng BOM/plugin của Boot để quản lý phiên bản Spring thay vì cố định phiên bản `spring-context` độc lập.

### 6.2. Model JavaBean

Tệp `src/main/java/demo/RegistrationForm.java`:

~~~java
package demo;

public class RegistrationForm {
    private String email;
    private Integer age;

    public RegistrationForm() {}

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

DTO này có setter cho property binding và dùng `Integer` thay vì `int` để có thể biểu diễn trường chưa được nhập.

### 6.3. Tạo binder, gắn processor và đọc lỗi

Tệp `src/main/java/demo/BindingErrorDemo.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public class BindingErrorDemo {

    public static void main(String[] args) {
        RegistrationForm form = new RegistrationForm();
        DataBinder binder = new DataBinder(
                form, "registration");

        binder.setAllowedFields("email", "age");
        binder.setRequiredFields("email");
        binder.setBindingErrorProcessor(
                new ApiBindingErrorProcessor());

        binder.bind(new MutablePropertyValues(
                Map.of("age", "abc")));

        BindingResult result = binder.getBindingResult();

        for (String field : List.of("email", "age")) {
            FieldError error = result.getFieldError(field);
            if (error != null) {
                System.out.println(
                        error.getField() + ":"
                        + error.getCode() + ":"
                        + error.isBindingFailure());
            }
        }

        System.out.println("hasErrors=" + result.hasErrors());
    }
}
~~~

Các tệp trên ở cùng package `demo`. Chạy bằng Gradle Wrapper có sẵn:

~~~bash
./gradlew run
~~~

Trên Windows:

~~~powershell
.\gradlew.bat run
~~~

Stdout của **class Java**, bỏ qua dòng log tác vụ Gradle:

~~~text
email:INPUT_REQUIRED:true
age:INPUT_TYPE:true
hasErrors=true
~~~

Diễn giải:

- `email` bị thiếu, trong khi `setRequiredFields("email")` yêu cầu có field. Binder gọi `processMissingFieldError`.
- `age=abc` không thể chuyển thành `Integer`. Binder chuyển lỗi property access qua `processPropertyAccessException`; processor trả mã `INPUT_TYPE`.
- Cả hai lỗi được thêm vào `BindingResult` và mang `bindingFailure=true`.
- Với `DefaultMessageCodesResolver` mặc định, `getCode()` là mã cơ sở cuối cùng trong danh sách code được phân giải, nên xuất ra `INPUT_REQUIRED`/`INPUT_TYPE`.

Chương trình chủ động đọc hai field theo `List.of(...)` nên thứ tự stdout xác định và không phụ thuộc cách binder sắp xếp danh sách lỗi.

## 7. Required field, conversion error và suppressed field là ba chuyện khác nhau

| Dữ liệu | Kết quả |
| --- | --- |
| Không có `email`, đã cấu hình `setRequiredFields("email")` | Missing field → `INPUT_REQUIRED` |
| Có `email=mai@example.com` | Không có missing-field error |
| Có `age=abc`, đích là `Integer` | Type mismatch → `INPUT_TYPE` |
| Có `age=20` | Chuyển kiểu thành công |
| Gửi field `role`, chỉ cho phép `email`/`age` | Bị loại khỏi binding; không nhất thiết gọi processor |
| Có `email=not-an-email` | Chuyển kiểu String thành công; cần validator kiểm tra định dạng |

`setRequiredFields(...)` kiểm tra **trường phải có mặt trong quá trình `bind(PropertyValues)`**, còn Bean Validation như `@NotBlank` và `@Email` kiểm tra **giá trị hoặc trạng thái đối tượng sau binding**. Nếu dùng hai cơ chế cho cùng một trường, cần quy định có cho phép trả hai lỗi trùng ý nghĩa hay không.

### Không áp dụng requiredFields cho constructor binding

`DataBinder#setRequiredFields(...)` là cơ chế của **property binding qua `bind(PropertyValues)`**, **không áp dụng cho `construct(ValueResolver)`**. Nếu model là record và request dùng constructor binding, các tham số thiếu phải được xử lý theo chính sách constructor/validation riêng. Đừng kỳ vọng processor bắt buộc được gọi cho mỗi tham số constructor bị thiếu.

### Suppressed field không phải FieldError của processor

Khi cấu hình `binder.setAllowedFields("email", "age")`, một field đầu vào như `role=ADMIN` có thể bị loại khỏi binding. Danh sách được ghi nhận qua:

~~~java
String[] suppressed =
        binder.getBindingResult().getSuppressedFields();
~~~

Đây là **fragment** chạy sau `bind(...)`, không phải class Java độc lập. Nó cho biết các field bị binder từ chối do chính sách allowed fields. Spring **không mặc định chuyển mọi suppressed field thành `FieldError` thông qua `BindingErrorProcessor`**.

Nếu hợp đồng API muốn **từ chối request có field không được phép**, controller/service phải kiểm tra `getSuppressedFields()` và quyết định mã lỗi riêng như `INPUT_FIELD_NOT_ALLOWED`. Không tự cho rằng `hasErrors()` sẽ là `true` khi chỉ có suppressed fields.

### Unknown field cũng có đường xử lý riêng

Theo cấu hình thông thường, `DataBinder` có thể bỏ qua unknown property. Nếu thay đổi `ignoreUnknownFields`, một property path không tồn tại có thể dẫn tới exception khác với type mismatch thông thường. Hãy kiểm thử cấu hình binder thực tế; **`BindingErrorProcessor` không phải một cơ chế bắt tất cả exception**.

## 8. Dùng processor trong Spring MVC

Với Spring MVC, `WebDataBinder` kế thừa `DataBinder`, nên có thể cấu hình processor ở `@InitBinder` cho đúng model attribute.

Giả sử đưa hai file `RegistrationForm.java` và `ApiBindingErrorProcessor.java` sang dự án Spring Boot 3.x có `spring-boot-starter-web`, thêm file `src/main/java/demo/RegistrationController.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RegistrationController {

    private final ApiBindingErrorProcessor processor =
            new ApiBindingErrorProcessor();

    @InitBinder("registration")
    void initBinder(WebDataBinder binder) {
        binder.setAllowedFields("email", "age");
        binder.setRequiredFields("email");
        binder.setBindingErrorProcessor(processor);
    }

    @PostMapping(
            path = "/registrations",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> create(
            @ModelAttribute("registration") RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            var problems = errors.getFieldErrors().stream()
                    .map(error -> Map.of(
                            "field", error.getField(),
                            "code", Objects.toString(
                                    error.getCode(), "INPUT_PROPERTY"),
                            "message", "Dữ liệu đầu vào không hợp lệ"
                    ))
                    .toList();

            return ResponseEntity.badRequest()
                    .body(Map.of("errors", problems));
        }

        return ResponseEntity.ok(
                Map.of("status", "accepted"));
    }
}
~~~

Đây là class controller đầy đủ; ứng dụng còn cần bootstrap `@SpringBootApplication`. Processor không có field mutable theo request, nên instance do controller giữ có thể được dùng lại. Spring quản lý binder của từng request/object, không dùng chung `BindingResult` cho nhiều request.

**`BindingResult` phải đứng ngay sau `@ModelAttribute`** để controller nhận lỗi binding của đúng object. `@InitBinder("registration")` giới hạn cấu hình cho model attribute mang tên `registration`. Controller còn dùng `setAllowedFields` để tránh bind các property không thuộc API.

Thử gọi endpoint:

~~~bash
curl -i -X POST http://localhost:8080/registrations -H "Content-Type: application/x-www-form-urlencoded" --data "age=abc"
~~~

Kỳ vọng HTTP 400, hai mã `INPUT_REQUIRED` và `INPUT_TYPE` (thứ tự có thể khác). Request hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/registrations -H "Content-Type: application/x-www-form-urlencoded" --data "email=mai%40example.com&age=22"
~~~

Kỳ vọng HTTP 200 và body:

~~~json
{"status":"accepted"}
~~~

Ví dụ này chỉ nhằm kiểm chứng **binding error contract**. Nó chưa dùng `@Valid`; để bắt email sai định dạng hoặc tuổi không đạt giới hạn nghiệp vụ, thêm Bean Validation và quy tắc ánh xạ mã validation riêng.

## 9. Kiểm thử mã lỗi ổn định

### 9.1. Unit test qua DataBinder

Trong project có JUnit Jupiter, tạo `src/test/java/demo/ApiBindingErrorProcessorTest.java`:

~~~java
package demo;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

import static org.junit.jupiter.api.Assertions.*;

class ApiBindingErrorProcessorTest {

    private BindingResult bind(Map<String, ?> input) {
        DataBinder binder = new DataBinder(
                new RegistrationForm(), "registration");
        binder.setAllowedFields("email", "age");
        binder.setRequiredFields("email");
        binder.setBindingErrorProcessor(
                new ApiBindingErrorProcessor());
        binder.bind(new MutablePropertyValues(input));

        return binder.getBindingResult();
    }

    @Test
    void usesStableCodesForMissingAndTypeMismatch() {
        BindingResult errors = bind(Map.of("age", "abc"));

        FieldError missing = errors.getFieldError("email");
        FieldError wrongType = errors.getFieldError("age");

        assertNotNull(missing);
        assertNotNull(wrongType);
        assertEquals("INPUT_REQUIRED", missing.getCode());
        assertEquals("INPUT_TYPE", wrongType.getCode());
        assertTrue(missing.isBindingFailure());
        assertTrue(wrongType.isBindingFailure());
    }

    @Test
    void validValuesProduceNoBindingErrors() {
        BindingResult errors = bind(Map.of(
                "email", "mai@example.com",
                "age", "22"));

        assertFalse(errors.hasErrors());
    }

    @Test
    void disallowedFieldIsSuppressed() {
        BindingResult errors = bind(Map.of(
                "email", "mai@example.com",
                "age", "22",
                "role", "ADMIN"));

        assertFalse(errors.hasErrors());
        assertArrayEquals(
                new String[]{"role"},
                errors.getSuppressedFields());
    }
}
~~~

Với Gradle `application` tại mục 6, thêm các dependency dành cho test:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Test thứ ba cố ý chứng minh **suppressed field không tự được coi là FieldError**. Nếu API cần báo lỗi cho field bị từ chối, tầng trả response phải có xử lý riêng cho `getSuppressedFields()`.

### 9.2. MockMvc kiểm thử HTTP

Với Spring Boot 3.x và `spring-boot-starter-test`, có thể dùng test MVC slice:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RegistrationController.class)
class RegistrationControllerTest {

    @Autowired MockMvc mvc;

    @Test
    void missingEmailGetsContractCode() throws Exception {
        mvc.perform(post("/registrations")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("age", "22"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("email"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("INPUT_REQUIRED"));
    }

    @Test
    void validInputIsAccepted() throws Exception {
        mvc.perform(post("/registrations")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("email", "mai@example.com")
                    .param("age", "22"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status")
                        .value("accepted"));
    }
}
~~~

Test đầu tiên chỉ phát sinh một lỗi binding nên việc kiểm tra `errors[0]` không gây vấn đề thứ tự. Nếu có nhiều lỗi, nên kiểm tra theo `field`/`code` mà không phụ thuộc vị trí. Test này không chứng minh mọi loại exception đều đi qua processor; cần thêm ca cho setter lỗi và JSON nếu API dùng chúng.

Nếu ứng dụng có Spring Security, cần thiết lập auth và CSRF trong MockMvc theo chính sách hiện hành. Ví dụ tối thiểu chỉ giả định các starter Spring Web và Test.

## 10. Chọn đúng điểm mở rộng: code, thông điệp hay JSON

Không phải hợp đồng lỗi riêng nào cũng cần viết `BindingErrorProcessor`. Hãy phân biệt:

| Nhu cầu | Điểm mở rộng phù hợp |
| --- | --- |
| Thay cách tạo binding `FieldError`/`ObjectError` | `BindingErrorProcessor` |
| Điều chỉnh danh sách mã ứng viên theo object/field/type | `MessageCodesResolver` |
| Dịch thông điệp theo locale | `MessageSource` và message bundles |
| Chuyển Spring errors thành response JSON/ProblemDetail | Controller/`@RestControllerAdvice` |
| Áp quy tắc nghiệp vụ lên object đã bind | Spring `Validator` hoặc Jakarta Bean Validation |

Nếu chỉ cần đổi mã **khi serialize HTTP**, có thể giữ nguyên `typeMismatch` bên trong Spring rồi map ở tầng response:

~~~java
String apiCode = "typeMismatch".equals(error.getCode())
        ? "INPUT_TYPE" : "INPUT_PROPERTY";
~~~

Đây là fragment, `error` cần là một `FieldError`. Nếu API không yêu cầu đổi lỗi nội bộ, cách này giảm phạm vi ảnh hưởng.

### Khác biệt giữa base code và candidate codes

`BindingErrorProcessor` quyết định lỗi cơ sở, ví dụ `INPUT_TYPE`. `MessageCodesResolver` phát triển nó thành danh sách như:

~~~text
INPUT_TYPE.registration.age
INPUT_TYPE.age
INPUT_TYPE.java.lang.Integer
INPUT_TYPE
~~~

Đây là ví dụ cấu trúc mã **khi dùng DefaultMessageCodesResolver** với field type tương ứng; thứ tự và các biến thể nên được kiểm thử trong cấu hình thực tế.

Ví dụ nội dung `messages_vi.properties`:

~~~properties
INPUT_REQUIRED.registration.email=Vui lòng nhập email
INPUT_TYPE.registration.age=Tuổi phải là số hợp lệ
INPUT_REQUIRED=Trường bắt buộc
INPUT_TYPE=Kiểu dữ liệu không hợp lệ
~~~

`MessageSource` có thể dùng `FieldError` như một `MessageSourceResolvable` để chọn thông điệp chi tiết rồi fallback. Client chỉ nên dựa vào `code`, còn `message` là văn bản hiển thị có thể thay đổi theo locale.

## 11. Những giới hạn phải biết

### 11.1. Constructor binding

`setRequiredFields` phục vụ `bind(PropertyValues)`, không áp dụng như một cơ chế bắt thiếu tham số trong `construct(ValueResolver)`. Khi nhận record/immutable DTO, cần kết hợp ràng buộc thích hợp và đường xử lý lỗi của constructor binding.

### 11.2. JSON request body

Với `@RequestBody`, Jackson/`HttpMessageConverter` xử lý JSON trước Bean Validation. Nếu JSON không đọc/deserialize được, có thể phát sinh `HttpMessageNotReadableException`. `BindingErrorProcessor` cấu hình trên binder **không tự đổi mọi exception đó** thành `INPUT_TYPE`. Cần mapper exception/response phù hợp.

### 11.3. Validation nghiệp vụ

`@Email`, `@NotNull`, `@Min` hay custom `Validator` kiểm tra dữ liệu sau khi binder xử lý conversion. Các lỗi này có thể đi vào `BindingResult` nhưng không phải do hai callback BindingErrorProcessor tạo ra. Với một field vừa thiếu trong requiredFields vừa có constraint, ứng dụng nên cân nhắc chính sách tránh lỗi trùng.

### 11.4. Field và global errors

Nếu processor tạo `ObjectError` (global error), code controller chỉ đọc `getFieldErrors()` sẽ không đưa lỗi đó vào response. Hợp đồng HTTP hoàn chỉnh cần quyết định cách serialize cả `getGlobalErrors()` hoặc `getAllErrors()`, ví dụ dùng `field=null`/`field=""` một cách nhất quán. Ở ví dụ `RegistrationController`, branch global error không phát sinh từ hai request curl minh họa.

### 11.5. Lỗi phần mềm và lỗi input

Một setter ném exception có thể là bug ở server chứ không phải input sai. Không nên vô điều kiện biến mọi `methodInvocation` thành HTTP 400 mà không đánh giá nguyên nhân. Nếu đó là lỗi lập trình/hạ tầng, nên log an toàn và sử dụng mã 5xx thích hợp ở tầng exception handling.

## 12. Bảo mật và sử dụng đồng thời

Processor có thể là singleton nếu **không lưu trạng thái theo request**. Ví dụ trong class ở mục 5, toàn bộ biến là tham số hoặc biến cục bộ; không có field `lastError`, `currentRequest` hay `currentBindingResult`. Điều này tránh trộn lỗi giữa các request song song.

Bảo mật hợp đồng lỗi:

1. Định nghĩa mã thuộc một danh mục hữu hạn và version hóa khi thay đổi ngữ nghĩa.
2. Không ghép nguyên dữ liệu client vào code.
3. Không trả `exception.getMessage()` hoặc `rejectedValue` trong HTTP body theo mặc định.
4. Giữ `allowedFields`/DTO chỉ có những thuộc tính client được phép điều khiển.
5. Phân quyền ở tầng service/domain; mã lỗi binding không thay thế authorization.
6. Giới hạn request size và nested collection inputs.
7. Metric/log nên nhóm theo code và endpoint, hạn chế dữ liệu nhạy cảm.
8. Kiểm thử code và flag `bindingFailure` thay vì so sánh thông điệp tiếng Việt.

Nếu dữ liệu nhạy cảm không được lưu cả trong `BindingResult`, implementation có thể dùng `null` thay cho `exception.getValue()` và điều chỉnh UX render form phù hợp. Đó là quyết định chính sách, không nên áp đặt cho mọi form.

## 13. Các lỗi triển khai thường gặp

**Quên `setBindingErrorProcessor`:** định nghĩa class tùy chỉnh nhưng không đăng ký trên binder thì Spring vẫn dùng `DefaultBindingErrorProcessor`.

**Quên required fields:** callback `processMissingFieldError` không tự quét tất cả property. Cần cấu hình `setRequiredFields(...)` ở property binding nếu muốn thông báo field phải có trong request.

**Dùng `rejectValue(...)` rồi nghĩ `bindingFailure=true`:** phương thức này dành cho việc ghi lỗi tiện lợi nhưng không biểu diễn đầy đủ metadata binding failure như constructor đầy đủ của `FieldError`. Khi contract cần flag chính xác, tạo `FieldError` trực tiếp.

**Mọi property exception đều thành INPUT_TYPE:** nhiều lỗi thuộc nhóm `methodInvocation` hoặc dạng khác. Chỉ ánh xạ `typeMismatch` vào `INPUT_TYPE` khi đó thực sự là lỗi chuyển kiểu.

**Tự nối tên field vào một code duy nhất:** bỏ qua `resolveMessageCodes` có thể làm mất thông điệp chuyên biệt theo object/field/type. Nếu không cần candidates thì đó phải là quyết định có chủ đích.

**Xem suppressed fields như binding errors:** field bị loại bởi `allowedFields` thường cần kiểm tra bằng `getSuppressedFields()`; callback của processor không tự báo lỗi cho tất cả field bị chặn.

**Không xử lý global errors:** processor có thể tạo `ObjectError`; response mapper cần đọc chúng khi thiết kế contract có loại lỗi này.

**Dùng processor để xử lý toàn bộ HTTP errors:** lỗi JSON body, method validation, authentication, authorization và business exception có đường xử lý khác.

**Trả raw rejected value:** dữ liệu như mật khẩu, token và thông tin cá nhân không nên bị lộ qua response/log.

**Custom toàn hệ thống khi chỉ một form có contract riêng:** áp dụng `@InitBinder("registration")` cục bộ nếu phù hợp; chỉ cài global khi tất cả controller cùng cần chính sách ấy.

## 14. Checklist áp dụng

- [ ] Có danh mục mã lỗi hợp đồng, phạm vi và ý nghĩa rõ ràng.
- [ ] Processor cài đủ hai callback của `BindingErrorProcessor`.
- [ ] `FieldError` giữ đúng object, field, bindingFailure và candidate codes.
- [ ] Cấu hình `setRequiredFields(...)` cho missing field thuộc property binding.
- [ ] Cấu hình `setAllowedFields(...)`/DTO đầu vào theo quyền thực tế.
- [ ] Kiểm tra `BindingResult#getSuppressedFields()` nếu contract cần từ chối field không được phép.
- [ ] Controller đặt `BindingResult` liền sau `@ModelAttribute`.
- [ ] Response không lộ exception message, rejected value hoặc stack trace.
- [ ] Unit test mã lỗi binding và test HTTP status/JSON bằng MockMvc.
- [ ] Mapping lỗi JSON/validation/business được thiết kế ở các tầng phù hợp.

## 15. Ghi nhớ

`BindingErrorProcessor` quyết định **cách biểu diễn lỗi trong quá trình data binding**. Khi có hợp đồng lỗi riêng, có thể chuyển `required`, `typeMismatch`, `methodInvocation` thành những mã ổn định như `INPUT_REQUIRED`, `INPUT_TYPE`, `INPUT_PROPERTY` mà vẫn dùng `BindingResult` làm kết quả chuẩn của Spring.

Nếu yêu cầu chỉ là đổi **message** hoặc **JSON response**, `MessageSource` và tầng response mapping thường thích hợp hơn. Nếu cần thay **FieldError/ObjectError ngay tại nguồn**, cài custom processor trên `DataBinder` hoặc `WebDataBinder`, kiểm thử cả missing field lẫn conversion, và không quên những đường lỗi nằm ngoài phạm vi của processor.

### Tài liệu chính thức để đọc thêm

- [BindingErrorProcessor API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/BindingErrorProcessor.html)
- [DefaultBindingErrorProcessor API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/DefaultBindingErrorProcessor.html)
- [DataBinder API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/DataBinder.html)
- [FieldError API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring MVC @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
