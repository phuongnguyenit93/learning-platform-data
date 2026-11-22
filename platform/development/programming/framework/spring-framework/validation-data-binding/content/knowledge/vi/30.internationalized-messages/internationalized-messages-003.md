# DefaultMessageCodesResolver và thứ tự mã lỗi dự phòng

Trong Spring MVC, một lỗi binding hoặc Bean Validation không nhất thiết chỉ có một mã thông báo. Ví dụ khi form gửi `age=abc` nhưng JavaBean khai báo `Integer age`, Spring có thể tạo một `FieldError` chứa **bốn khóa thông báo theo thứ tự**:

~~~text
typeMismatch.registration.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
~~~

Các khóa đó do **`DefaultMessageCodesResolver`** sinh ra. **`MessageSource`** mới tra tài nguyên ngôn ngữ tương ứng để chọn câu thông báo cho người dùng, chẳng hạn “Tuổi phải là số nguyên.” (tiếng Việt) hoặc “Age must be a whole number.” (tiếng Anh). Khi không có khóa cụ thể, Spring thử khóa ít cụ thể hơn: đây chính là **thứ tự mã lỗi dự phòng** (*message code fallback order*).

Bài này thuộc nhóm **Thông báo đa ngữ** của Spring Framework, bao gồm thuật toán tạo mã cho field/object/nested collection, tương tác với `BindingResult` và `MessageSource`, resource bundles, tùy chỉnh prefix/formatter, ví dụ Spring Boot 3.5 / Spring Framework 6.2 / Java 17+ và integration test MockMvc. Không trộn cơ chế Servlet MVC với Spring WebFlux khi lựa chọn exception/resolver.

## 1. Phân biệt mã lỗi và văn bản đã dịch

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| `DataBinder` / `WebDataBinder` | Bind, type conversion, ghi nhận lỗi | `"abc"` không chuyển được sang `Integer` |
| `Errors` / `BindingResult` | Lưu những lỗi trên object/field | `errors.getFieldErrors()` |
| `ObjectError` / `FieldError` | Một lỗi với `codes`, `arguments`, `defaultMessage` | Field `age` có bốn codes |
| `MessageCodesResolver` | Chiến lược tạo các mã có thứ tự từ error metadata | `resolveMessageCodes(...)` |
| `DefaultMessageCodesResolver` | Implementation mặc định của chiến lược | `typeMismatch.registration.age` rồi các fallback |
| `MessageSource` | Tra keys theo locale và nội suy message | `getMessage(fieldError, locale)` |
| `messages_vi.properties` | Bản dịch tiếng Việt | `typeMismatch.age=Tuổi phải là số.` |

Hai bước không được nhập làm một:

~~~text
Form request: age=abc
     |
     v
WebDataBinder -> conversion fail
     |
     v
BindingResult có FieldError(code="typeMismatch")
     |
     v
DefaultMessageCodesResolver
     |  tạo candidates có thứ tự
     v
["typeMismatch.registration.age",
 "typeMismatch.age",
 "typeMismatch.java.lang.Integer",
 "typeMismatch"]
     |
     v
MessageSource + Locale(vi/en)
     |  tìm key đầu tiên phù hợp
     v
Thông báo ngôn ngữ đã chọn
~~~

`DefaultMessageCodesResolver` **không** tự mở file `messages.properties` và **không** dịch câu văn. Nó tạo **các key**. `MessageSource` mới làm tra cứu ngôn ngữ. Muốn hiểu vì sao user thấy một câu cụ thể, phải kiểm tra **cả mã trong `FieldError.getCodes()` lẫn những key có trong bundles**.

## 2. API chính xác

Interface:

~~~java
org.springframework.validation.MessageCodesResolver
~~~

Implementation mặc định:

~~~java
org.springframework.validation.DefaultMessageCodesResolver
~~~

Có hai overload:

~~~java
String[] resolveMessageCodes(
    String errorCode,
    String objectName);

String[] resolveMessageCodes(
    String errorCode,
    String objectName,
    String field,
    Class<?> fieldType);
~~~

Đây là chữ ký API rút gọn cho học tập, không cần tự định nghĩa lại. Overload thứ nhất phục vụ lỗi cấp **object**; overload thứ hai phục vụ lỗi cấp **field**. `fieldType` có thể là `null` nếu framework không xác định được kiểu Java.

Mã gốc `errorCode` có thể là:

- `typeMismatch` khi binding/chuyển kiểu thất bại.
- `required` khi cơ chế binding đánh dấu một field bắt buộc nhưng thiếu.
- `NotBlank`, `Min`, `Size`... khi Jakarta Bean Validation constraint được Spring chuyển thành error.
- `account.invalid` hoặc `tooYoung` do lập trình viên chủ động gọi `errors.reject(...)`/`rejectValue(...)`.

**Mã gốc do nguồn lỗi quyết định**; resolver không tự thực thi `@Min`, không kiểm tra giá trị và không quyết định HTTP status.

## 3. ObjectError: đúng hai mã dự phòng

Ví dụ:

~~~java
var resolver = new DefaultMessageCodesResolver();
String[] codes = resolver.resolveMessageCodes(
    "account.invalid", "registration");
~~~

Kết quả:

~~~text
account.invalid.registration
account.invalid
~~~

Với formatter mặc định, thứ tự là:

1. `errorCode.objectName` — thông báo đặc thù cho lỗi trên model có tên đó.
2. `errorCode` — thông báo tổng quát.

Ví dụ:

~~~properties
account.invalid.registration=Thông tin đăng ký chưa hợp lệ.
account.invalid=Dữ liệu không hợp lệ.
~~~

Nếu cả hai keys tồn tại, `account.invalid.registration` được ưu tiên. Nếu không có key thứ nhất, key `account.invalid` là fallback.

Object error có thể xuất hiện khi một Spring `Validator` gọi:

~~~java
errors.reject("account.invalid", "Đăng ký chưa hợp lệ");
~~~

Đây là snippet trong method có biến `errors`, không phải Java program độc lập. `reject` tạo lỗi **cấp object**; `rejectValue` tạo lỗi **theo field**.

Tên `objectName` quan trọng: nếu controller dùng `@ModelAttribute("registration")` thì tên của `BindingResult` là `registration`. Đổi model name thành `signupForm` làm code ưu tiên thành `account.invalid.signupForm`. Khi đổi tên form/model, hãy kiểm tra cả message resources.

## 4. FieldError: bốn mã, từ cụ thể đến tổng quát

Ví dụ trực tiếp:

~~~java
var resolver = new DefaultMessageCodesResolver();
String[] codes = resolver.resolveMessageCodes(
    "typeMismatch",
    "registration",
    "age",
    Integer.class);
~~~

Kết quả chính xác:

~~~text
typeMismatch.registration.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
~~~

| Ưu tiên | Công thức | Phạm vi |
|---|---|---|
| 1 | `code.objectName.field` | Một field trong một model cụ thể |
| 2 | `code.field` | Cùng tên field ở mọi model |
| 3 | `code.fieldType` | Cùng kiểu Java, khi kiểu được xác định |
| 4 | `code` | Mọi lỗi cùng mã gốc |

Nếu định nghĩa:

~~~properties
typeMismatch.registration.age=Tuổi đăng ký phải là số nguyên.
typeMismatch.age=Tuổi phải là số.
typeMismatch.java.lang.Integer=Vui lòng nhập số nguyên.
typeMismatch=Định dạng không hợp lệ.
~~~

thì lỗi của `registration.age` chọn dòng đầu. Nếu không có dòng đó, Spring có thể dùng `typeMismatch.age`. Nếu một form khác có `Integer quantity` mà chưa có khóa đặc thù, Spring có thể chọn `typeMismatch.java.lang.Integer`.

### Primitive và wrapper là hai tên kiểu khác nhau

Với `int.class`, mã type-specific là `typeMismatch.int`. Với `Integer.class`, là `typeMismatch.java.lang.Integer`. Đừng định nghĩa duy nhất `typeMismatch.int` rồi cho rằng nó bao phủ mọi property khai báo `Integer`.

Nếu `fieldType` không xác định được (`null`), khóa theo kiểu Java không có ý nghĩa để thêm; khi đó danh sách không nhất thiết có đủ bốn entries.

### Mã dự phòng không phụ thuộc vào bản dịch hiện có

`DefaultMessageCodesResolver` vẫn sinh cùng danh sách dù resource bundle chưa có **bất kỳ** key nào. Chỉ `MessageSource` quan sát các bản dịch hiện có và chọn message tương ứng. Vì thế test “danh sách mã” và test “thông báo theo locale” phải là **hai loại kiểm tra riêng**.

## 5. Nested property, indexed List và Map: nhiều hơn bốn mã

Trong form có `groups[0].name`, Spring tạo mã cho **phần tử cụ thể** lẫn **property path bỏ index** để tái sử dụng thông báo cho cả collection.

Theo Javadoc Spring 6.2:

~~~java
resolver.resolveMessageCodes(
    "typeMismatch",
    "user",
    "groups[0].name",
    String.class);
~~~

Kết quả **bảy khóa có thứ tự**:

~~~text
typeMismatch.user.groups[0].name
typeMismatch.user.groups.name
typeMismatch.groups[0].name
typeMismatch.groups.name
typeMismatch.name
typeMismatch.java.lang.String
typeMismatch
~~~

Ý nghĩa:

- Key chứa `user.groups[0].name` cho phép tạo thông báo đặc biệt cho một phần tử.
- Key `user.groups.name` áp cho các phần tử của collection đó trong object `user`.
- Key `groups[0].name` áp indexed field path ở nhiều model.
- Key `groups.name` áp cho field tương tự bất kể index/object.
- Key `name` áp cho field cuối cùng tên `name`.
- Key theo Java type và key gốc là hai fallback rộng hơn.

Ví dụ:

~~~properties
typeMismatch.user.groups[0].name=Tên nhóm đầu tiên bị lỗi.
typeMismatch.user.groups.name=Tên nhóm không đúng.
typeMismatch.name=Tên không hợp lệ.
typeMismatch=Giá trị không hợp lệ.
~~~

Nếu muốn một thông báo chung cho mọi phần tử, chỉ cần key bỏ index. **Không giả định mọi nested field đều có đúng bảy mã**: số lượng còn phụ thuộc cấu trúc field path, số index/keys và formatter đang dùng. Hãy xem `FieldError.getCodes()` thực tế.

## 6. `MessageSource` tra mã và locale như thế nào?

`ObjectError`/`FieldError` triển khai `MessageSourceResolvable` với:

- `String[] getCodes()` — danh sách mã ứng viên **có thứ tự**.
- `Object[] getArguments()` — arguments của thông báo.
- `String getDefaultMessage()` — câu mặc định nếu có.

`MessageSource` có overload:

~~~java
String getMessage(
    MessageSourceResolvable resolvable,
    Locale locale);
~~~

Dùng trong controller:

~~~java
for (FieldError error : result.getFieldErrors()) {
    String[] candidates = error.getCodes();
    String translated = messageSource.getMessage(
        error, locale);
    // Gửi translated tới client, hoặc đưa vào model view.
}
~~~

Đây là snippet trong method đã có `result`, `messageSource` và `locale`. `MessageSource` thử các ứng viên theo thứ tự. Nếu tất cả không tồn tại, một `defaultMessage` hợp lệ có thể được sử dụng. Nếu không có mã nào được resolve và không có default message, overload này có thể ném `NoSuchMessageException`.

### Ba tầng fallback dễ bị trộn

1. **Fallback giữa các mã lỗi:** từ `typeMismatch.registration.age` đến `typeMismatch`.
2. **Fallback giữa các locale/resource bundles:** từ bản dịch cho locale yêu cầu sang bundle mặc định theo cấu hình.
3. **Fallback sang defaultMessage:** khi không tìm được key nhưng error có default message phù hợp.

Đây là **ba cơ chế khác nhau**. Một key rất cụ thể nằm trong bundle mặc định có thể thắng một key ít cụ thể hơn chỉ có ở bản dịch locale khác, tùy cách MessageSource tổ chức và resolve resources. Để tránh câu trả lời trộn tiếng Việt và tiếng Anh, dịch đủ các mã quan trọng cho mỗi locale hỗ trợ.

## 7. Đến từ DataBinder, @Valid hay Spring Validator?

### Conversion failure

Request:

~~~text
age=abc
~~~

trong khi DTO có `Integer age`. Binder không tạo được số, ghi `FieldError` với mã gốc `typeMismatch`. Đây là lỗi **kiểu dữ liệu**, không phải `@Min(18)` báo lỗi trên một `Integer` đã convert thành công.

### Bean Validation failure

Nếu request gửi `age=17`, conversion thành công. Nếu DTO có:

~~~java
@Min(18)
private Integer age;
~~~

và handler đặt `@Valid` đúng cách, Jakarta Validation phát hiện vi phạm. Spring adapter thường tạo `FieldError` với mã gốc `Min`, ví dụ:

~~~text
Min.registration.age
Min.age
Min.java.lang.Integer
Min
~~~

Nếu field `name` vi phạm `@NotBlank`, mã tương ứng có thể là:

~~~text
NotBlank.registration.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
~~~

### Spring Validator chủ động reject

Một `org.springframework.validation.Validator` tùy chỉnh có thể gọi:

~~~java
errors.rejectValue(
    "age", "tooYoung", "Người dùng chưa đủ tuổi");
~~~

Với object name `registration` và field `Integer age`, resolver có thể sinh:

~~~text
tooYoung.registration.age
tooYoung.age
tooYoung.java.lang.Integer
tooYoung
~~~

Đây là snippet minh họa trong một `validate(Object,Errors)` method, không phải class độc lập. Việc phát hiện lỗi vẫn do validator làm; resolver chỉ thêm các mã dự phòng cho **mã gốc `tooYoung`**.

Một lỗi class-level như constraint kiểm tra `startDate <= endDate` có thể được chuyển thành `ObjectError` thay vì `FieldError`, nên dùng hai mã thay vì bốn. Không coi tất cả Jakarta violations là field errors.

## 8. Resource bundles tiếng Việt và tiếng Anh

Trong Spring Boot 3.5, có thể dùng:

~~~text
src/main/resources/
  messages.properties
  messages_vi.properties
  application.properties
~~~

Để auto-configure `MessageSource` theo mặc định, cần `messages.properties` tại classpath root (hoặc basename phù hợp). Chỉ có `messages_vi.properties` mà thiếu base bundle có thể khiến Boot không auto-configure MessageSource như mong đợi.

`messages.properties` — default English:

~~~properties
typeMismatch.registration.age=Age must be a whole number.
typeMismatch.age=Age must be numeric.
typeMismatch.java.lang.Integer=Enter a valid integer.
typeMismatch=Invalid format.
Min.registration.age=Age must be at least 18.
Min.age=Age is below the minimum.
Min=Value is too small.
NotBlank.registration.name=Name is required.
NotBlank.name=This field must not be blank.
NotBlank=Cannot be blank.
NotNull.registration.age=Age is required.
NotNull=Required value is missing.
~~~

`messages_vi.properties` — tiếng Việt:

~~~properties
typeMismatch.registration.age=Tuổi phải là số nguyên.
typeMismatch.age=Tuổi phải là số.
typeMismatch.java.lang.Integer=Vui lòng nhập số nguyên.
typeMismatch=Định dạng không hợp lệ.
Min.registration.age=Tuổi phải từ 18 trở lên.
Min.age=Tuổi chưa đạt mức tối thiểu.
Min=Giá trị nhỏ hơn giới hạn.
NotBlank.registration.name=Vui lòng nhập họ tên.
NotBlank.name=Trường này không được để trống.
NotBlank=Không được để trống.
NotNull.registration.age=Vui lòng nhập tuổi.
NotNull=Thiếu giá trị bắt buộc.
~~~

Trong `application.properties`:

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

Những properties này minh họa cách cố định encoding/basename và giảm ảnh hưởng từ system locale. Spring Boot có default cho basename và encoding, nên không nhất thiết phải lặp các dòng khi dùng cấu hình chuẩn. Lưu resource files ở UTF-8.

**Phân biệt key với object path:** `typeMismatch.registration.age` là một **string key**, không có nghĩa MessageSource phản chiếu object Java rồi truy cập `registration.age`.

## 9. Ứng dụng chạy được: Spring Boot 3.5 / Java 17+

Mục tiêu: form gửi `name`/`age`, Spring MVC bind vào `RegistrationForm`, `@Valid` kiểm tra constraints, `BindingResult` nhận lỗi, `DefaultMessageCodesResolver` tạo codes và `MessageSource` dịch theo `Accept-Language`.

### 9.1. Dependency

Trong project Spring Boot hợp lệ đã có Gradle plugin/version management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Không thể dùng `javac` thuần chỉ với JDK để compile các lớp import Spring/Jakarta. Dùng Gradle wrapper đã có hoặc tạo project từ Spring Initializr.

### 9.2. `MessageCodesApplication.java`

`src/main/java/com/example/codes/MessageCodesApplication.java`:

~~~java
package com.example.codes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessageCodesApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessageCodesApplication.class, args);
    }
}
~~~

### 9.3. `RegistrationForm.java`

`src/main/java/com/example/codes/RegistrationForm.java`:

~~~java
package com.example.codes;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class RegistrationForm {
    @NotBlank
    private String name;

    @NotNull
    @Min(18)
    private Integer age;

    public RegistrationForm() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Với `age=abc`, conversion thất bại. Với `age=17`, conversion đúng nhưng `@Min(18)` không đạt. Với `age` thiếu, `@NotNull` không đạt. Với `name=""`, `@NotBlank` không đạt. Đó là những case tạo mã gốc **khác nhau**, mặc dù tất cả đều có thể được gửi qua `MessageSource`.

### 9.4. `MessageCodesPrinter.java` — xem trực tiếp các mã

`src/main/java/com/example/codes/MessageCodesPrinter.java`:

~~~java
package com.example.codes;

import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;
import org.springframework.validation.DefaultMessageCodesResolver;

@Component
public class MessageCodesPrinter implements CommandLineRunner {
    @Override
    public void run(String... args) {
        var resolver = new DefaultMessageCodesResolver();

        System.out.println("FIELD: " + String.join(" | ",
            resolver.resolveMessageCodes(
                "typeMismatch",
                "registration",
                "age",
                Integer.class)));

        System.out.println("OBJECT: " + String.join(" | ",
            resolver.resolveMessageCodes(
                "registration.invalid", "registration")));

        System.out.println("NESTED: " + String.join(" | ",
            resolver.resolveMessageCodes(
                "typeMismatch",
                "user",
                "groups[0].name",
                String.class)));
    }
}
~~~

Ngoài log khởi động Boot, ba dòng được in **theo đúng thứ tự**:

~~~text
FIELD: typeMismatch.registration.age | typeMismatch.age | typeMismatch.java.lang.Integer | typeMismatch
OBJECT: registration.invalid.registration | registration.invalid
NESTED: typeMismatch.user.groups[0].name | typeMismatch.user.groups.name | typeMismatch.groups[0].name | typeMismatch.groups.name | typeMismatch.name | typeMismatch.java.lang.String | typeMismatch
~~~

Điểm cần nhớ: đây là **unit demo thuật toán**; nó không cần người dùng gửi HTTP để in các arrays, và không chứng minh MessageSource đã nạp đúng bundle. Controller phía dưới mới nối cả pipeline với MVC.

### 9.5. `RegistrationController.java`

`src/main/java/com/example/codes/RegistrationController.java`:

~~~java
package com.example.codes;

import java.util.Arrays;
import java.util.List;
import java.util.Locale;

import jakarta.validation.Valid;
import org.springframework.context.MessageSource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RegistrationController {
    private final MessageSource messages;

    public RegistrationController(MessageSource messages) {
        this.messages = messages;
    }

    @PostMapping(
        path = "/registration",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<FormReply> register(
            @Valid @ModelAttribute("registration")
            RegistrationForm form,
            BindingResult errors,
            Locale locale) {

        if (!errors.hasErrors()) {
            return ResponseEntity.ok(
                new FormReply(true, List.of()));
        }

        List<FieldIssue> details =
            errors.getFieldErrors()
                .stream()
                .map(error -> toIssue(error, locale))
                .toList();

        return ResponseEntity.badRequest().body(
            new FormReply(false, details));
    }

    private FieldIssue toIssue(
            FieldError error, Locale locale) {

        String[] candidates = error.getCodes();

        return new FieldIssue(
            error.getField(),
            candidates == null
                ? List.of()
                : Arrays.asList(candidates),
            messages.getMessage(error, locale)
        );
    }

    public record FormReply(
        boolean valid, List<FieldIssue> errors) {
    }

    public record FieldIssue(
        String field, List<String> codes, String message) {
    }
}
~~~

`@ModelAttribute("registration")` cố định object name; `BindingResult` đặt **ngay sau** object. `@Valid` kích hoạt Jakarta Validation. Khi có lỗi, `FieldError.getCodes()` cho phép quan sát thứ tự từ cụ thể đến chung, còn `messages.getMessage(error,locale)` hiển thị message theo locale. Endpoint minh họa chỉ trả field errors, không trả object-level errors hay rejected values.

Không tự gọi `new DefaultMessageCodesResolver()` để xử lý HTTP trong controller này: Spring binder đã tạo các codes. Component printer độc lập chỉ giúp học và kiểm chứng quy tắc.

### 9.6. Chạy và gọi thử bằng curl

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Với resources ở phần 8 và cổng mặc định 8080, request:

~~~bash
curl -i -X POST "http://localhost:8080/registration" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept-Language: vi" \
  --data-urlencode "name=Lan" \
  --data-urlencode "age=abc"
~~~

kỳ vọng **HTTP 400** cùng JSON tương đương:

~~~json
{
  "valid": false,
  "errors": [
    {
      "field": "age",
      "codes": [
        "typeMismatch.registration.age",
        "typeMismatch.age",
        "typeMismatch.java.lang.Integer",
        "typeMismatch"
      ],
      "message": "Tuổi phải là số nguyên."
    }
  ]
}
~~~

Thay header thành `Accept-Language: en` thì codes **giữ nguyên**, message trở thành:

~~~text
Age must be a whole number.
~~~

Nếu gửi `age=17` và `name=Lan`, Bean Validation tạo `Min` violation, message tiếng Việt là `"Tuổi phải từ 18 trở lên."`. Nếu gửi `age=20`, `name=""`, sẽ nhận `NotBlank.registration.name` và message `"Vui lòng nhập họ tên."`. Nếu gửi `age=20` và `name=Lan` thì HTTP **200**:

~~~json
{"valid":true,"errors":[]}
~~~

Một controller có thể gặp cùng lúc nhiều errors. Không viết test phụ thuộc thứ tự giữa **các FieldError của những field khác nhau** nếu framework/validator không cam kết thứ tự; nhưng **thứ tự trong `getCodes()` của từng lỗi** là hợp đồng của `DefaultMessageCodesResolver` mặc định.

## 10. Kiểm thử JUnit và MockMvc

Một unit test cho resolver xác nhận thứ tự keys. Một integration test HTTP xác nhận dữ liệu thật được bind/validate và `MessageSource` tra đúng bản dịch.

`src/test/java/com/example/codes/MessageCodesResolverTest.java`:

~~~java
package com.example.codes;

import org.junit.jupiter.api.Test;
import org.springframework.validation.DefaultMessageCodesResolver;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;

class MessageCodesResolverTest {
    private final DefaultMessageCodesResolver resolver =
        new DefaultMessageCodesResolver();

    @Test
    void fieldCodesHaveExpectedPriority() {
        assertArrayEquals(
            new String[] {
                "typeMismatch.registration.age",
                "typeMismatch.age",
                "typeMismatch.java.lang.Integer",
                "typeMismatch"
            },
            resolver.resolveMessageCodes(
                "typeMismatch", "registration",
                "age", Integer.class));
    }

    @Test
    void objectCodesHaveTwoEntries() {
        assertArrayEquals(
            new String[] {
                "registration.invalid.registration",
                "registration.invalid"
            },
            resolver.resolveMessageCodes(
                "registration.invalid", "registration"));
    }

    @Test
    void indexedPathCreatesSevenCodes() {
        assertArrayEquals(
            new String[] {
                "typeMismatch.user.groups[0].name",
                "typeMismatch.user.groups.name",
                "typeMismatch.groups[0].name",
                "typeMismatch.groups.name",
                "typeMismatch.name",
                "typeMismatch.java.lang.String",
                "typeMismatch"
            },
            resolver.resolveMessageCodes(
                "typeMismatch", "user",
                "groups[0].name", String.class));
    }

    @Test
    void optionalPrefixIsAppliedToAllCodes() {
        var other = new DefaultMessageCodesResolver();
        other.setPrefix("validation.");

        assertArrayEquals(
            new String[] {
                "validation.typeMismatch.registration.age",
                "validation.typeMismatch.age",
                "validation.typeMismatch.java.lang.Integer",
                "validation.typeMismatch"
            },
            other.resolveMessageCodes(
                "typeMismatch", "registration",
                "age", Integer.class));
    }
}
~~~

`src/test/java/com/example/codes/RegistrationControllerTest.java`:

~~~java
package com.example.codes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void vietnameseTranslationUsesSpecificCode()
            throws Exception {
        mvc.perform(post("/registration")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                .param("name", "Lan")
                .param("age", "abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].field")
                .value("age"))
            .andExpect(jsonPath("$.errors[0].codes[0]")
                .value("typeMismatch.registration.age"))
            .andExpect(jsonPath("$.errors[0].codes[3]")
                .value("typeMismatch"))
            .andExpect(jsonPath("$.errors[0].message")
                .value("Tuổi phải là số nguyên."));
    }

    @Test
    void englishTranslationUsesSameCode()
            throws Exception {
        mvc.perform(post("/registration")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .header(HttpHeaders.ACCEPT_LANGUAGE, "en")
                .param("name", "Lan")
                .param("age", "abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].codes[0]")
                .value("typeMismatch.registration.age"))
            .andExpect(jsonPath("$.errors[0].message")
                .value("Age must be a whole number."));
    }

    @Test
    void minViolationHasMinCodeNotTypeMismatch()
            throws Exception {
        mvc.perform(post("/registration")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                .param("name", "Lan")
                .param("age", "17"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].codes[0]")
                .value("Min.registration.age"))
            .andExpect(jsonPath("$.errors[0].message")
                .value("Tuổi phải từ 18 trở lên."));
    }

    @Test
    void blankNameUsesNotBlankKey()
            throws Exception {
        mvc.perform(post("/registration")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                .param("name", "")
                .param("age", "20"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].codes[0]")
                .value("NotBlank.registration.name"))
            .andExpect(jsonPath("$.errors[0].message")
                .value("Vui lòng nhập họ tên."));
    }

    @Test
    void validFormHasNoErrors() throws Exception {
        mvc.perform(post("/registration")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("name", "Lan")
                .param("age", "20"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.valid").value(true))
            .andExpect(jsonPath("$.errors").isEmpty());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

hoặc Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Với Spring Boot 3.5/Spring 6.2 và hai bundles nói trên, **chín tests kỳ vọng PASS** (bốn test thuật toán và năm test HTTP). Đây là kỳ vọng của ví dụ, không phải khẳng định đã chạy Gradle. Nếu ứng dụng thật có security/CSRF, cần cấu hình MockMvc tương ứng.

## 11. Cách thử fallback một cách có kiểm soát

Đừng xóa keys trong ứng dụng production để “xem Spring chọn gì”. Trong unit test, dùng `StaticMessageSource` và chỉ thêm các keys muốn kiểm tra:

~~~java
var resolver = new DefaultMessageCodesResolver();

var source =
    new org.springframework.context.support.StaticMessageSource();

source.addMessage(
    "typeMismatch.age",
    Locale.forLanguageTag("vi"),
    "Tuổi phải là số.");
source.addMessage(
    "typeMismatch",
    Locale.forLanguageTag("vi"),
    "Định dạng không hợp lệ.");

var error = new org.springframework.validation.FieldError(
    "registration",
    "age",
    "abc",
    true,
    resolver.resolveMessageCodes(
        "typeMismatch", "registration",
        "age", Integer.class),
    null,
    "Giá trị không hợp lệ");

String chosen = source.getMessage(
    error, Locale.forLanguageTag("vi"));
System.out.println(chosen);
~~~

Đây là **snippet trong một method** có import `DefaultMessageCodesResolver` và `java.util.Locale`; không phải class độc lập. Output:

~~~text
Tuổi phải là số.
~~~

Vì `typeMismatch.registration.age` **không tồn tại** trong source này, message source thử tiếp và thấy `typeMismatch.age`. Nếu thêm key đầu tiên, message mới sẽ được ưu tiên. `StaticMessageSource` hữu ích cho test độc lập không cần sửa resource bundles của ứng dụng.

## 12. Tùy chỉnh prefix và formatter

`DefaultMessageCodesResolver` có:

~~~java
resolver.setPrefix("validation.");
~~~

Sau đó, ví dụ bốn mã trở thành:

~~~text
validation.typeMismatch.registration.age
validation.typeMismatch.age
validation.typeMismatch.java.lang.Integer
validation.typeMismatch
~~~

Nếu thêm prefix nhưng không thêm prefix vào keys trong file properties, thông báo có thể không tìm được. Một cách tổ chức khác là đổi formatter:

~~~java
resolver.setMessageCodeFormatter(
    DefaultMessageCodesResolver.Format.POSTFIX_ERROR_CODE);
~~~

Formatter mặc định là `PREFIX_ERROR_CODE`, tạo `typeMismatch.registration.age`. `POSTFIX_ERROR_CODE` đưa error code ra sau, ví dụ `registration.age.typeMismatch`. Chỉ đổi khi đã chọn một naming convention đồng nhất cho toàn bộ bundles.

Cần gắn resolver với **đúng DataBinder** nếu muốn áp dụng:

~~~java
binder.setMessageCodesResolver(resolver);
~~~

Đoạn trên là snippet có biến `binder` và `resolver` trong scope. Với MVC, có thể tùy chỉnh theo form:

~~~java
@InitBinder("registration")
public void configureCodes(WebDataBinder binder) {
    var resolver = new DefaultMessageCodesResolver();
    resolver.setPrefix("validation.");
    binder.setMessageCodesResolver(resolver);
}
~~~

Đây là **ví dụ thay thế**, không thêm vào project phần 9 nếu chưa chuyển các resource keys sang `validation.*`. Cần imports `@InitBinder`, `WebDataBinder` và `DefaultMessageCodesResolver` khi dùng.

Muốn áp dụng quy tắc cho mọi binder, có thể cấu hình `ConfigurableWebBindingInitializer` và `setMessageCodesResolver(...)` trong MVC infrastructure, nhưng cần giữ conversion service/validator mặc định. Đừng thay cả bộ config global chỉ vì một form có cách đặt keys khác.

## 13. Sai lầm thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chỉ thấy thông báo chung `typeMismatch` | Chưa có bản dịch đặc thù | Thêm `typeMismatch.object.field`, `typeMismatch.field` |
| Định nghĩa `typeMismatch.int` nhưng không match | Property là `Integer`, không phải `int` | Kiểm tra `getCodes()`, thêm key `typeMismatch.java.lang.Integer` |
| Key theo tên form không khớp | `@ModelAttribute` dùng objectName khác | Xem `BindingResult.getObjectName()` |
| Form key có nhưng bản dịch không được chọn | Có key cụ thể hơn đứng trước | In toàn bộ `FieldError.getCodes()` |
| Locale vi hiện tiếng Anh | Thiếu bản dịch, fallback sang bundle mặc định | Bổ sung translations và test theo locale |
| Boot không load message bundle | Thiếu `messages.properties`, basename sai | Xác minh resource path và `spring.messages.*` |
| Dấu tiếng Việt bị lỗi | File/MessageSource encoding khác nhau | Lưu UTF-8 và kiểm tra `spring.messages.encoding` |
| `getDefaultMessage()` chưa được dịch theo keys Spring | Code bỏ qua `MessageSource` | Gọi `getMessage(fieldError, locale)` |
| `NoSuchMessageException` | Không có keys và default message phù hợp | Cung cấp bản dịch chung và safe fallback |
| Cả bốn keys không giống dự đoán | fieldType null, nested path, custom prefix/formatter | Dùng getCodes() thực tế, unit test |
| Lỗi `age=abc` không có key `Min` | Chuyển kiểu thất bại trước `@Min` | Xử lý `typeMismatch` riêng |
| Lỗi `age=17` lại được báo `Min` | Conversion đúng, constraint sai | Đây là hành vi mong muốn |
| Đổi `@ModelAttribute("registration")` sang tên khác | Key cụ thể đổi theo object name | Cập nhật bundles hoặc dùng keys chung |
| API trả cả rejected password | Serialize `FieldError` thẳng ra JSON | Chỉ trả field, code và message đã kiểm soát |
| Unit test resolver PASS nhưng HTTP vẫn sai | Locale/MessageSource/binder khác | Kiểm tra integration bằng MockMvc |

### Kiểm tra theo thứ tự

1. Lỗi phát sinh từ **type conversion**, Bean Validation hay custom validator?
2. Object name từ `BindingResult.getObjectName()` là gì?
3. `FieldError.getCodes()` hoặc `ObjectError.getCodes()` trả keys theo thứ tự nào?
4. Files `messages.properties`/`messages_vi.properties` có key nào?
5. Locale được chọn từ `Accept-Language` có đúng không?
6. `MessageSource.getMessage(error,locale)` chọn thông báo nào?
7. Có custom resolver, prefix, formatter hoặc initializer không?
8. Một integration test với MockMvc có xác nhận đúng contract HTTP không?

## 14. Tự kiểm tra

**Câu 1.** Mã nào đầu tiên cho `typeMismatch` của `registration.age` kiểu `Integer`? — `typeMismatch.registration.age`.

**Câu 2.** Key thứ ba là gì? — `typeMismatch.java.lang.Integer`, không phải `typeMismatch.int`.

**Câu 3.** Object error `account.invalid` trên object `registration` có mấy keys? — Hai: `account.invalid.registration`, `account.invalid`.

**Câu 4.** Tại sao `groups[0].name` có thể tạo nhiều hơn bốn codes? — Spring sinh cả indexed và non-indexed property paths.

**Câu 5.** `DefaultMessageCodesResolver` có đọc file tiếng Việt không? — Không; `MessageSource` mới tra bundles.

**Câu 6.** Khi không tìm thấy key đầu tiên, Spring có dùng key tiếp theo không? — Có, theo thứ tự `getCodes()`.

**Câu 7.** `@Min(18)` và `typeMismatch` có giống nhau không? — Không. Một bên là constraint trên số đã convert, một bên là lỗi chuyển kiểu.

**Câu 8.** Khi đổi model name, có thể ảnh hưởng i18n không? — Có, vì `code.objectName.field` thay đổi.

**Câu 9.** Thêm `setPrefix("validation.")` cần làm gì? — Đồng bộ các keys trong resource bundles.

**Câu 10.** Làm thế nào xác minh cả fallback và bản dịch? — Unit test resolver với thứ tự mã và test `MessageSource`/MockMvc theo locale.

## 15. Checklist

- [ ] Xác định mã gốc và loại lỗi trước khi thiết kế translation.
- [ ] Ghi nhớ **hai keys object-level**, **bốn keys field-level** thông thường.
- [ ] Kiểm tra collection/nested field với nhiều indexed/non-indexed keys.
- [ ] Hiểu sự khác biệt giữa `int` và `Integer` khi tạo key theo type.
- [ ] Dùng `BindingResult`/`FieldError.getCodes()` để xác nhận keys thực tế.
- [ ] Dùng `MessageSource.getMessage(error,locale)` cho thông báo đã dịch.
- [ ] Có base `messages.properties` và các files ngôn ngữ cần thiết, UTF-8.
- [ ] Test vi/en và các tình huống fallback bị thiếu key cụ thể.
- [ ] Không nhầm `getDefaultMessage()` với Spring code-based i18n.
- [ ] Khi đổi object name, cập nhật hoặc kiểm tra fallback message keys.
- [ ] Nếu tùy chỉnh prefix/formatter, di chuyển tất cả keys có liên quan.
- [ ] Không lộ rejected values/stack traces trong response.
- [ ] Xác minh bằng unit test thuật toán và HTTP integration test.

**Ghi nhớ:** `DefaultMessageCodesResolver` sinh danh sách mã **từ cụ thể đến tổng quát**: object error thường có **2 mã**, field error đơn giản thường có **4 mã**, nested collection có thể nhiều hơn. `MessageSource` mới dùng các khóa đó và locale để chọn thông báo. Mã lỗi giúp ứng dụng tái sử dụng quy tắc, còn bản dịch giúp người dùng hiểu đúng lỗi bằng ngôn ngữ phù hợp.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — DefaultMessageCodesResolver API](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html)
- [Spring Framework — Resolving Error Codes to Error Messages](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html)
- [Spring Framework 6.2 — MessageCodesResolver API](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/MessageCodesResolver.html)
- [Spring Framework 6.2 — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — FieldError API](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework 6.2 — DefaultMessageCodesResolver.Format API](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.Format.html)
- [Spring Framework 6.2 — MessageSource API](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/MessageSource.html)
- [Spring Boot 3.5 — Internationalization](https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html)
