# Tùy chỉnh thông báo lỗi và bản địa hóa khi kiểm tra dữ liệu trong Spring Boot

## 1. Vấn đề: validation đúng nhưng thông điệp lỗi chưa hữu ích

Trong API Spring Boot, hai request có thể đều bị từ chối với HTTP 400 nhưng người dùng cần **hai điều khác nhau**: một *mã lỗi ổn định* để client xử lý bằng chương trình và một *thông điệp dễ hiểu theo ngôn ngữ* để hiển thị. Ví dụ cùng một ràng buộc `@NotBlank` cho tên, client đặt `Accept-Language: vi` có thể nhận “Tên không được để trống”, còn client đặt `Accept-Language: en` nhận “Name must not be blank”.

Bài này hướng dẫn một cách làm có thể kiểm thử cho **Spring Boot 3.5.x + Spring MVC + Jakarta Bean Validation + Java 17+**:

- Định nghĩa constraint bằng `@NotBlank`, `@Email`, `@Min` với **message keys** thay cho hard-code thông báo tại controller.
- Tạo resource bundles `messages.properties`, `messages_vi.properties`; giải thích `MessageSource` và locale fallback.
- Nhận locale từ `Accept-Language` thông qua MVC `LocaleResolver`, không cố parse header theo cách thủ công.
- Xử lý `MethodArgumentNotValidException` bằng `@RestControllerAdvice`, tạo JSON error contract có `code`, `message`, `errors[]`.
- Phân biệt validation object với sai JSON, sai kiểu path/query, thiếu request parameter, business rule và method validation.
- Kiểm tra tự động bằng `MockMvc` với ít nhất hai ngôn ngữ và tình huống lỗi riêng.
- Giữ chi tiết kỹ thuật, rejected values, token và thông tin riêng tư khỏi response công khai.

**Tư duy chính:** bản địa hóa thay đổi *thông điệp hiển thị*, không thay đổi bản chất của ràng buộc, HTTP status, trường lỗi, mã lỗi ổn định hoặc quyền truy cập API.

## 2. Phân biệt i18n, l10n, validation và error response

- **Internationalization (i18n)**: thiết kế hệ thống để thông điệp có thể thay đổi theo locale mà không phải sửa business logic.
- **Localization (l10n)**: cung cấp bản dịch và quy tắc riêng cho ngôn ngữ/khu vực, ví dụ tiếng Việt, tiếng Anh, dấu thập phân, ngày tháng.
- **Validation**: xác định dữ liệu có thỏa ràng buộc không, như tên bắt buộc, tuổi tối thiểu, email có định dạng thích hợp.
- **Error response contract**: JSON gửi cho client; API quyết định mã lỗi và danh sách field issues, đồng thời chọn thông điệp theo locale.

Thông điệp từ `@NotBlank(message="...")` có thể được nội suy bởi Bean Validation. Một `FieldError` từ `BindingResult` cũng là `MessageSourceResolvable`, có các error codes và một default message. Hai cách bản địa hóa này có liên quan nhưng không hoàn toàn giống nhau.

Một response nên có cấu trúc ví dụ:

~~~json
{
  "code": "VALIDATION_ERROR",
  "message": "Dữ liệu yêu cầu không hợp lệ",
  "errors": [
    {
      "field": "name",
      "message": "Tên không được để trống"
    }
  ]
}
~~~

Giữ `code=VALIDATION_ERROR` như nhau cho cả hai ngôn ngữ. Tầng giao diện nên dựa vào `code` và `field` khi thực hiện logic, không so sánh text thông điệp tiếng Việt/Anh.

## 3. Chuỗi xử lý từ HTTP request tới thông điệp bản địa hóa

~~~text
POST /api/registrations
Accept-Language: vi
Content-Type: application/json
                |
                v
DispatcherServlet và LocaleResolver
  -> Locale của request (vi)
                |
                v
@RequestBody + HttpMessageConverter
  -> JSON được giải mã thành RegistrationRequest
                |
                v
@Valid -> Validator (Hibernate Validator)
  -> kiểm tra @NotBlank, @Email, @Min
  -> resolve constraint message templates từ MessageSource
                |
                +-- hợp lệ -> gọi controller
                |
                +-- sai -> BindingResult/FieldError
                              |
                              v
                 MethodArgumentNotValidException
                              |
                              v
                 @RestControllerAdvice
                   MessageSource + Locale
                              |
                              v
                 ResponseEntity<ApiError>
                 HTTP 400 + JSON localized
~~~

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Làm gì? | Không làm gì? |
|---|---|---|
| `@Valid` | Yêu cầu validation đối số được hỗ trợ | Không tự viết JSON response |
| `jakarta.validation.Validator` | Đánh giá constraint và tạo violations | Không chọn HTTP status theo business rule |
| `LocalValidatorFactoryBean` | Tích hợp Bean Validation với Spring | Không phải nơi quyết định JSON schema public |
| `MessageSource` | Tìm thông điệp theo code + locale và arguments | Không tự quyết định người gọi có quyền xem đối tượng |
| `LocaleResolver` | Chọn locale của HTTP request | Không tự dịch văn bản hard-coded |
| `BindingResult` | Giữ lỗi bind/validate dưới dạng field/global errors | Không tự bảo đảm mọi dữ liệu trong đó được công khai an toàn |
| `@RestControllerAdvice` | Chuyển exception thành response hợp đồng API | Không thay thế việc kiểm tra constraint |
| `HttpMessageConverter` | Giải mã/serialize HTTP body | Không tự suy ra bản dịch của mọi lỗi nghiệp vụ |

**Thứ tự quan trọng:** nếu JSON body chưa đọc được, validation trên DTO chưa chạy. Nếu query parameter không convert được, có thể phát sinh lỗi chuyển kiểu trước khi business controller được gọi. Không nên bắt mọi exception thành `VALIDATION_ERROR`.

## 4. MessageSource và resource bundles

### 4.1. File mặc định phải có thật

Trong Spring Boot 3.5, mặc định tìm bundle tên `messages` ở classpath root. Một cấu trúc chuẩn:

~~~text
src/main/resources/
  application.properties
  messages.properties
  messages_vi.properties
~~~

`messages.properties` là **bundle mặc định** và cần tồn tại để Spring Boot tự cấu hình `MessageSource` theo tài liệu. Chỉ tạo `messages_vi.properties` mà bỏ bundle mặc định có thể khiến auto-configuration không xảy ra như dự kiến.

`messages.properties` là fallback dùng cho ngôn ngữ không được hỗ trợ; ví dụ chọn English làm fallback. `messages_vi.properties` chứa bản dịch tương ứng. Có thể bổ sung `messages_en.properties`, `messages_en_US.properties`, `messages_vi_VN.properties` khi cần biến thể riêng.

Các file phải được đóng gói vào classpath của ứng dụng (thường bên trong JAR). Chọn encoding UTF-8 rõ ràng, đặc biệt với dấu tiếng Việt.

### 4.2. Cấu hình application.properties

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false

spring.web.locale=en
spring.web.locale-resolver=accept-header
~~~

Ý nghĩa:

1. `spring.messages.basename`: nơi tìm bộ thông điệp; có thể là danh sách basename phân cách bằng dấu phẩy khi có nhiều module.
2. `spring.messages.encoding=UTF-8`: giúp đọc thông điệp Unicode có dấu chính xác.
3. `spring.messages.fallback-to-system-locale=false`: tránh phụ thuộc locale của JVM/máy chủ khi không có bản dịch. Fallback về `messages.properties` thay vì vô tình dùng một bundle của hệ điều hành.
4. `spring.web.locale=en`: giá trị locale mặc định khi request không đưa lựa chọn phù hợp.
5. `spring.web.locale-resolver=accept-header`: dùng HTTP `Accept-Language` để chọn locale khi request cung cấp.

**Chú ý:** `Accept-Language` là sở thích ngôn ngữ, không phải bằng chứng địa lý, quốc tịch hay quyền người dùng. Header có thể bị client chủ động thay đổi.

Nếu sản phẩm chỉ hỗ trợ hai locale, hãy định nghĩa chính sách fallback có chủ đích và kiểm thử các header như `vi`, `vi-VN`, `en-US`, `fr`, hoặc header vắng mặt. `AcceptHeaderLocaleResolver` không có chức năng “dịch tất cả” — nó chỉ xác định locale; `MessageSource` vẫn phải có thông điệp.

### 4.3. Lấy thông điệp trong Java

`MessageSource` hỗ trợ:

~~~java
String text = messages.getMessage(
        "registration.name.required",
        null,
        locale);
~~~

Đây là đoạn method minh họa: `messages` là một `org.springframework.context.MessageSource`, còn `locale` là `java.util.Locale` của request. Nếu code không tồn tại và gọi overload **không có fallback**, Spring có thể ném `NoSuchMessageException`.

Khi một key có thể thiếu, có thể chủ động cung cấp fallback:

~~~java
String safeText = messages.getMessage(
        "registration.name.required",
        null,
        "Invalid name",
        locale);
~~~

Không nên bật `spring.messages.use-code-as-default-message=true` như một giải pháp production lâu dài: nó có thể khiến người dùng thấy nguyên mã nội bộ kiểu `registration.name.required` thay vì văn bản phù hợp.

### 4.4. Tham số thông điệp: MessageFormat

Đối với text có biến, dùng message arguments:

~~~properties
errors.minimum-age=Age must be at least {0}
~~~

~~~java
String text = messages.getMessage(
        "errors.minimum-age",
        new Object[]{18},
        locale);
~~~

Kết quả English là `Age must be at least 18`. Các placeholder `{0}`, `{1}` tuân theo `java.text.MessageFormat`. Dấu nháy đơn trong message format có semantics escape đặc biệt; kiểm thử bản dịch có apostrophe và các placeholder được sắp thứ tự khác nhau.

**Đừng nhầm** `{0}` của `MessageSource` với `{min}` của Jakarta Bean Validation constraint template; đó là hai kiểu placeholder được nội suy trong những bước khác nhau.

## 5. Bean Validation message templates và MessageSource

### 5.1. Viết annotation theo key, không hard-code ngôn ngữ

Thay vì:

~~~java
@NotBlank(message = "Tên không được để trống")
String name
~~~

hãy viết:

~~~java
@NotBlank(message = "{registration.name.required}")
String name
~~~

Khi Bean Validation chạy, key `registration.name.required` được tìm trong nguồn thông điệp đã cấu hình. Spring Boot tích hợp `MessageSource` của ứng dụng để giải quyết các placeholder `{...}` trong constraint messages, rồi hoàn thiện interpolation bằng Bean Validation provider.

**Lưu ý:** khi dùng nguyên Jakarta Bean Validation ngoài Spring Boot hoặc tự dựng `ValidatorFactory`, chuẩn Bean Validation có convention `ValidationMessages.properties`. Spring Boot có bridge đến application `MessageSource`; trong kiến trúc không dùng Boot, cần cấu hình `LocalValidatorFactoryBean` hoặc message interpolator thích hợp thay vì mặc định rằng mọi `messages.properties` tự có hiệu lực.

### 5.2. Phân biệt interpolation và binding error codes

Với `@NotBlank` trên field `name` của `RegistrationRequest`, một `FieldError` có thể mang các codes theo mức cụ thể giảm dần:

~~~text
NotBlank.registrationRequest.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
~~~

Đây là các code do `DefaultMessageCodesResolver` tạo theo quy ước; tên object thực tế và kiểu field cần xác minh theo binding context. Framework thử code cụ thể trước và fallback đến code chung.

Có hai cách dùng thông điệp:

- **Bean Validation message template**: `@NotBlank(message="{registration.name.required}")`; provider tạo default message đã nội suy cho constraint.
- **FieldError resolution**: `messageSource.getMessage(fieldError, locale)`; Spring thử các field-specific codes, rồi dùng `FieldError.defaultMessage` khi không có mã riêng trong bundle.

Trong cùng một dự án, cả hai có thể cùng tồn tại. Nếu bundle thêm `NotBlank.registrationRequest.name`, nó có thể ưu tiên hơn default message từ annotation khi bạn gọi `getMessage(fieldError, locale)`. **Không tự ý vừa định nghĩa hai thông điệp xung đột cho cùng trường vừa kỳ vọng kết quả luôn theo annotation.**

`FieldError.getDefaultMessage()` thường chứa nội dung đã được Bean Validation nội suy trong request locale, nhưng việc gọi `MessageSource.getMessage(fieldError,locale)` cho phép framework giải quyết theo error codes. Với manual `BindingResult.rejectValue`, dùng cơ chế này đặc biệt hữu ích vì default message có thể không đủ.

### 5.3. Các annotation thường dùng

| Constraint | Ý nghĩa | Tình huống |
|---|---|---|
| `@NotBlank` | Chuỗi không null và có ít nhất một ký tự không phải whitespace | Tên hiển thị |
| `@NotNull` | Giá trị không null | Giá trị không phải chuỗi hoặc trường bắt buộc |
| `@Size(min,max)` | Kích thước chuỗi/collection/map/array | Tên dài 3–40 ký tự |
| `@Email` | Kiểm tra cú pháp email theo validator | Email; **không** xác minh địa chỉ thực sự tồn tại |
| `@Min(18)` | Giá trị số không nhỏ hơn 18 | Tuổi tối thiểu |
| `@Pattern(regexp=...)` | Chuỗi khớp regular expression | Mã sản phẩm, định dạng có quy ước |
| `@Valid` | Kích hoạt cascaded validation cho object phù hợp | Body DTO chứa nested DTO |

Một số constraint như `@Email` cho phép `null` hoặc chuỗi rỗng theo Jakarta Bean Validation; nếu email **bắt buộc**, thêm `@NotBlank` với message key riêng. Không cho rằng `@Email` thay luôn requiredness.

## 6. Những nhánh lỗi cần phân biệt trong Spring MVC

| Nguồn / giai đoạn | Exception thường gặp | HTTP mặc định điển hình | Hướng bản địa hóa |
|---|---|---|---|
| `@Valid @RequestBody DTO` không thỏa constraint | `MethodArgumentNotValidException` | 400 | FieldError/ObjectError qua MessageSource |
| `@Valid @ModelAttribute` lỗi binding/validation, không có BindingResult kế tiếp | `MethodArgumentNotValidException` trong nhiều trường hợp | 400 | Error codes từ binding/validator |
| Constraint trực tiếp trên `@RequestParam`, `@PathVariable`, method arguments | `HandlerMethodValidationException` trong MVC mới | 400 với input validation | ParameterValidationResult + MessageSource |
| Query/path không chuyển thành kiểu đích (`abc` -> `int`) | `MethodArgumentTypeMismatchException` | 400 | Mã lỗi và message chung an toàn |
| Tham số bắt buộc không được gửi | `MissingServletRequestParameterException` | 400 | Key missing-parameter |
| JSON sai cấu trúc/cú pháp hoặc không deserialize được | `HttpMessageNotReadableException` | 400 | Key unreadable-body |
| `Content-Type` không được hỗ trợ | `HttpMediaTypeNotSupportedException` | 415 | Key unsupported-media-type |
| `Accept` không khớp response có thể tạo | `HttpMediaTypeNotAcceptableException` | 406 | Key not-acceptable |
| Rule nghiệp vụ như user đã có email | Exception nghiệp vụ do ứng dụng định nghĩa | Theo contract, có thể 409 | Key business error riêng |

**Không bắt `Exception.class` rồi trả mọi lỗi là 400.** Nó che cả lỗi server, database, programming bug và authentication/authorization failure. Cũng không dùng mỗi `MethodArgumentNotValidException` để giả định mọi validation của Spring MVC đều được xử lý, vì **method validation** có nhánh riêng.

### 6.1. Vị trí BindingResult

Với method:

~~~java
@PostMapping("/forms")
String submit(@Valid @ModelAttribute FormData form,
              BindingResult result) {
    if (result.hasErrors()) {
        return "form";
    }
    return "success";
}
~~~

Đây chỉ là method minh họa, cần `FormData` và các import. `BindingResult` phải đặt **ngay sau** đối số nó liên quan để Spring có thể đưa lỗi cho method tự xử lý. Nếu có `BindingResult`, một số lỗi sẽ không ném exception mặc định mà được trả dưới dạng `result.getFieldErrors()`.

Trong REST API, thường chọn centralized `@RestControllerAdvice` thay vì lặp xử lý trong mọi controller. Nhưng chọn một cách nhất quán: nếu đã nhận `BindingResult` và muốn tự trả response, đừng kỳ vọng một global exception handler tự nhiên được gọi cho những lỗi bạn đã giữ lại.

### 6.2. Method validation khác validation của một DTO

Trong Spring Framework 6.1+, khi constraint đặt trực tiếp trên tham số hoặc kiểu trả về, MVC có cơ chế method validation và có thể ném `HandlerMethodValidationException`. Kết quả gồm các `ParameterValidationResult` theo từng method parameter, không chỉ `BindingResult` của một DTO.

Nếu có class-level `@Validated` trên controller, validation bằng AOP proxy có thể thay đổi đường xử lý. Tài liệu Spring Framework khuyến nghị bỏ class-level `@Validated` trên controller khi muốn tận dụng built-in MVC method validation.

Khi cần xử lý nhánh này, có thể dùng visitor của `HandlerMethodValidationException` hoặc iterating `getAllValidationResults()`; các error result hỗ trợ `MessageSourceResolvable`. Không copy một handler `MethodArgumentNotValidException` rồi ép cast sang method-validation exception.

## 7. Ví dụ chạy được: Spring Boot 3.5.16 + Java 17+ + Maven

Ví dụ gồm API đăng ký đơn giản với ràng buộc:

- `name` không để trống.
- `email` phải có cú pháp email hợp lệ.
- `age` phải từ 18 trở lên.

Mỗi constraint có key bản dịch. Advice tạo error response cố định schema nhưng nội dung tùy `Accept-Language`. Project không có database và không triển khai xác thực; mục đích là minh họa validation error pipeline.

### 7.1. Cấu trúc project

~~~text
validation-i18n-demo/
  pom.xml
  src/
    main/
      java/com/example/validationi18n/
        ValidationI18nApplication.java
        RegistrationRequest.java
        RegistrationController.java
        ValidationErrorAdvice.java
      resources/
        application.properties
        messages.properties
        messages_vi.properties
    test/
      java/com/example/validationi18n/
        RegistrationMvcTest.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>validation-i18n-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-validation` cần có mặt để Hibernate Validator thực thi các Jakarta Bean Validation constraint. Đừng giả định chỉ có `spring-boot-starter-web` là luôn có validation provider trong mọi Boot version.

### 7.3. Cấu hình message source và locale

File `src/main/resources/application.properties`:

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false

spring.web.locale=en
spring.web.locale-resolver=accept-header
~~~

Không cần tự khai báo `MessageSource` hay `LocalValidatorFactoryBean` trong project này vì Boot có auto-configuration tương ứng khi resource bundle và validation provider được phát hiện. Tự tạo lại hai bean mà không hiểu điều kiện auto-configuration có thể làm mất tích hợp message interpolation.

### 7.4. messages.properties — English default

File `src/main/resources/messages.properties`:

~~~properties
validation.failed=Request data is invalid
registration.name.required=Name must not be blank
registration.email.invalid=Email address is invalid
registration.age.min=Age must be at least 18
error.body.unreadable=Request body cannot be read
error.parameter.invalid=Request parameter has an invalid format
~~~

File mặc định đóng vai trò fallback; không cần bản dịch English riêng nếu toàn bộ English messages nằm ở đây. Nếu sản phẩm yêu cầu English US và UK khác nhau, thêm `messages_en_US.properties`/`messages_en_GB.properties` theo quy ước.

### 7.5. messages_vi.properties — tiếng Việt

File `src/main/resources/messages_vi.properties`, lưu bằng UTF-8:

~~~properties
validation.failed=Dữ liệu yêu cầu không hợp lệ
registration.name.required=Tên không được để trống
registration.email.invalid=Địa chỉ email không hợp lệ
registration.age.min=Tuổi phải từ 18 trở lên
error.body.unreadable=Không đọc được nội dung yêu cầu
error.parameter.invalid=Tham số yêu cầu có định dạng không hợp lệ
~~~

**Quy tắc:** giữ cùng key ở hai bundle, chỉ thay giá trị. Có thể dùng một công cụ CI để kiểm tra không bỏ sót keys, duplicate keys, placeholder `{0}` hoặc encoding hỏng.

### 7.6. Spring Boot entry point

File `src/main/java/com/example/validationi18n/ValidationI18nApplication.java`:

~~~java
package com.example.validationi18n;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationI18nApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationI18nApplication.class, args);
    }
}
~~~

### 7.7. Request DTO với Bean Validation

File `src/main/java/com/example/validationi18n/RegistrationRequest.java`:

~~~java
package com.example.validationi18n;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record RegistrationRequest(
        @NotBlank(message = "{registration.name.required}")
        String name,

        @Email(message = "{registration.email.invalid}")
        String email,

        @Min(value = 18, message = "{registration.age.min}")
        int age) {
}
~~~

Record là lựa chọn đơn giản trong Java 17 và dùng tốt với Jackson của Spring Boot 3.5. Các constraint là annotations trên record components; Bean Validation nhận các thông tin này trong quá trình kiểm tra.

Trong ví dụ, `email` **không bắt buộc**: `@Email` chủ yếu kiểm tra định dạng cho giá trị thích hợp, không tự bắt null/empty. Trong API thực tế muốn email bắt buộc, thêm `@NotBlank(message="{registration.email.required}")` và key tương ứng ở tất cả bundles.

Dùng `int age` có nghĩa nếu JSON bỏ field `age`, quá trình mapping có thể đưa giá trị mặc định 0 và `@Min(18)` phát hiện lỗi; nếu cần phân biệt “bị thiếu” với “nhỏ hơn 18”, dùng `Integer age` cùng `@NotNull` và `@Min`.

### 7.8. Controller

File `src/main/java/com/example/validationi18n/RegistrationController.java`:

~~~java
package com.example.validationi18n;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RegistrationController {

    public record RegistrationResponse(String name, String email, int age) {
    }

    @PostMapping(
            value = "/api/registrations",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public RegistrationResponse create(
            @Valid @RequestBody RegistrationRequest request) {
        return new RegistrationResponse(
                request.name(), request.email(), request.age());
    }

    @GetMapping("/api/registrations/{id}")
    public String getById(@PathVariable("id") long id) {
        return "id=" + id;
    }
}
~~~

Trong `create`, JSON được decode trước và validator kiểm tra DTO sau. Khi có lỗi và không có `BindingResult` kế tiếp, Spring MVC thông thường phát `MethodArgumentNotValidException`. `getById` dùng để minh họa lỗi chuyển đổi path `"abc"` thành `long`, là nhánh khác với DTO validation.

Project không lưu user thật, không mã hóa password và không xác nhận email ngoài đời. Response thành công chỉ giúp chứng minh controller được gọi sau khi validation pass.

### 7.9. @RestControllerAdvice: một schema lỗi, nhiều bản dịch

File `src/main/java/com/example/validationi18n/ValidationErrorAdvice.java`:

~~~java
package com.example.validationi18n;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;

import org.springframework.context.MessageSource;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class ValidationErrorAdvice {
    private final MessageSource messages;

    public ValidationErrorAdvice(MessageSource messages) {
        this.messages = messages;
    }

    public record FieldIssue(String field, String message) {
    }

    public record ApiError(
            String code,
            String message,
            List<FieldIssue> errors) {
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> validation(
            MethodArgumentNotValidException ex,
            Locale locale) {

        List<FieldIssue> fields = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        messages.getMessage(error, locale)))
                .sorted(Comparator.comparing(FieldIssue::field))
                .toList();

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "VALIDATION_ERROR",
                        text("validation.failed", locale),
                        fields));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException ex,
            Locale locale) {
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_BODY",
                        text("error.body.unreadable", locale),
                        List.of()));
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiError> typeMismatch(
            MethodArgumentTypeMismatchException ex,
            Locale locale) {
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_PARAMETER",
                        text("error.parameter.invalid", locale),
                        List.of(new FieldIssue(
                                ex.getName(),
                                text("error.parameter.invalid", locale)))));
    }

    private String text(String key, Locale locale) {
        return messages.getMessage(key, null, locale);
    }
}
~~~

**Giải thích cẩn thận:**

1. `MessageSource` được inject, không `new ResourceBundleMessageSource` trong mỗi request.
2. `Locale locale` là đối số hợp lệ của `@ExceptionHandler` trong Spring MVC, được giải quyết từ locale resolver của request.
3. `messages.getMessage(error, locale)` nhận `FieldError` như một `MessageSourceResolvable`; có thể dùng các field-specific error codes rồi fallback về default message đã được Bean Validation nội suy.
4. Sắp xếp theo tên field để test response nhất quán hơn. Nếu một field có nhiều constraint cùng lỗi, thứ tự giữa các lỗi cùng field vẫn phụ thuộc cách validation tạo errors; hợp đồng nên tránh phụ thuộc thứ tự đó.
5. `List<FieldIssue>` chỉ gửi tên field và bản dịch an toàn. Không gửi `getRejectedValue()`, nguyên JSON body, Java exception cause hay stack trace.
6. Với body không đọc được, trả `INVALID_BODY` và thông điệp chung; không giả vờ đó là lỗi `@NotBlank`.
7. Với path/query sai kiểu, trả `INVALID_PARAMETER`, không dùng constraint code và không hiện giá trị đầu vào nếu có nguy cơ nhạy cảm.
8. Handler này **chưa xử lý đầy đủ mọi exception MVC**: `MissingServletRequestParameterException`, `HandlerMethodValidationException`, 415, business errors và các ObjectError không có field cần policy riêng trong ứng dụng production.
9. Khi muốn trả cả global validation errors (class-level constraints), phải xét `ex.getBindingResult().getGlobalErrors()`; code trên tập trung vào field errors của DTO minh họa.

`@RestControllerAdvice` phù hợp để trả JSON thống nhất trên nhiều controller. Không nên vừa `extends ResponseEntityExceptionHandler` vừa khai báo `@ExceptionHandler` cho cùng các exception được lớp cha định tuyến sẵn: có thể tạo ambiguous exception mapping. Khi đã extend lớp cha, hãy **override protected handler method** tương ứng thay vì khai báo hai handler trùng trách nhiệm.

### 7.10. Chạy thử bằng Maven

Cần JDK 17+ và Maven. Tại thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Nếu dự án có Maven Wrapper, có thể dùng `./mvnw spring-boot:run`; trên Windows dùng `mvnw.cmd spring-boot:run`.

Server mặc định lắng nghe cổng 8080 khi không có cấu hình khác và cổng còn trống.

**Request hợp lệ:**

~~~bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"name":"Mai","email":"mai@example.test","age":21}'
~~~

Kỳ vọng HTTP 200, body JSON tương đương:

~~~json
{"name":"Mai","email":"mai@example.test","age":21}
~~~

**Tên rỗng, chọn tiếng Việt:**

~~~bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"name":"","email":"mai@example.test","age":21}'
~~~

Kỳ vọng HTTP 400; body JSON về mặt logic:

~~~json
{
  "code": "VALIDATION_ERROR",
  "message": "Dữ liệu yêu cầu không hợp lệ",
  "errors": [
    {
      "field": "name",
      "message": "Tên không được để trống"
    }
  ]
}
~~~

**Cùng lỗi, chọn English:**

~~~bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H "Content-Type: application/json" \
  -H "Accept-Language: en" \
  -d '{"name":"","email":"mai@example.test","age":21}'
~~~

Kỳ vọng HTTP 400; phần thông điệp trở thành:

~~~json
{
  "code": "VALIDATION_ERROR",
  "message": "Request data is invalid",
  "errors": [
    {
      "field": "name",
      "message": "Name must not be blank"
    }
  ]
}
~~~

Whitespace/thứ tự các JSON properties là chi tiết serializer, không phải hợp đồng. `code` và `field` **không đổi** giữa hai ngôn ngữ.

**Địa chỉ email sai cú pháp:**

~~~bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"name":"Mai","email":"not-an-email","age":21}'
~~~

Kỳ vọng `VALIDATION_ERROR`, field `email`, message “Địa chỉ email không hợp lệ”.

**Tuổi không đủ:**

~~~bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"name":"Mai","email":"mai@example.test","age":16}'
~~~

Kỳ vọng `VALIDATION_ERROR`, field `age`, message “Tuổi phải từ 18 trở lên”.

**JSON không đọc được:**

~~~bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"name":"Mai","age":'
~~~

Kỳ vọng `INVALID_BODY` với message “Không đọc được nội dung yêu cầu”, không phải `VALIDATION_ERROR`: không có DTO hợp lệ để validate.

**Path variable không convert được:**

~~~bash
curl -i -H "Accept-Language: vi" \
  http://localhost:8080/api/registrations/abc
~~~

Kỳ vọng `INVALID_PARAMETER` và message “Tham số yêu cầu có định dạng không hợp lệ”.

Với `curl -i`, output thực tế gồm HTTP status line, headers và body. Các JSON blocks trên chỉ mô tả **body logic**, không phải toàn bộ stdout. Khi cần so sánh response JSON, dùng JSONPath thay vì so sánh bytes có thể thay đổi thứ tự property.

## 8. MockMvc: kiểm thử bản địa hóa và hợp đồng lỗi

Sử dụng `@SpringBootTest` + `@AutoConfigureMockMvc` (Boot 3.5) để chạy pipeline MVC, validator, messages và advice. File `src/test/java/com/example/validationi18n/RegistrationMvcTest.java`:

~~~java
package com.example.validationi18n;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationMvcTest {
    @Autowired
    MockMvc mvc;

    @Test
    void nameErrorIsVietnameseWithViLanguageHeader() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                        .content("""
                                {"name":"","email":"mai@example.test","age":21}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.message")
                        .value("Dữ liệu yêu cầu không hợp lệ"))
                .andExpect(jsonPath("$.errors[0].field").value("name"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Tên không được để trống"));
    }

    @Test
    void sameErrorIsEnglishWithEnHeader() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "en")
                        .content("""
                                {"name":"","email":"mai@example.test","age":21}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.message")
                        .value("Request data is invalid"))
                .andExpect(jsonPath("$.errors[0].field").value("name"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Name must not be blank"));
    }

    @Test
    void invalidEmailIsLocalizedInVietnamese() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                        .content("""
                                {"name":"Mai","email":"not-an-email","age":21}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field").value("email"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Địa chỉ email không hợp lệ"));
    }

    @Test
    void minimumAgeUsesLocalizedMessage() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                        .content("""
                                {"name":"Mai","email":"mai@example.test","age":16}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field").value("age"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Tuổi phải từ 18 trở lên"));
    }

    @Test
    void malformedJsonHasSeparateCodeAndLocalizedMessage() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                        .content("{\"name\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_BODY"))
                .andExpect(jsonPath("$.message")
                        .value("Không đọc được nội dung yêu cầu"));
    }

    @Test
    void invalidPathVariableHasSeparateErrorCode() throws Exception {
        mvc.perform(get("/api/registrations/abc")
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"))
                .andExpect(jsonPath("$.errors[0].field").value("id"))
                .andExpect(jsonPath("$.message")
                        .value("Tham số yêu cầu có định dạng không hợp lệ"));
    }

    @Test
    void validRequestPassesValidation() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"name":"Mai","email":"mai@example.test","age":21}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Mai"))
                .andExpect(jsonPath("$.age").value(21));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Trong ví dụ mỗi test validation chỉ làm **một constraint** sai nên `errors[0]` dễ dự đoán. Khi một request có nhiều lỗi, nên so sánh theo field/code thay vì phụ thuộc thứ tự. Các test kiểm tra key schema, HTTP status, bản dịch Việt/Anh và sự phân biệt JSON/parsing với validation.

`MockMvc` không mở TCP port. Với test tích hợp qua mạng, dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` và HTTP client phù hợp, nhất là khi cần kiểm tra reverse proxy, TLS, caching và HTTP headers trong deploy thực tế.

## 9. Bản địa hóa với MessageFormat, FieldError và trường hợp phức tạp

### 9.1. Phân biệt field và object-level errors

`FieldError` có tên field như `name`, `age`; `ObjectError` có thể mô tả constraint ở cấp object, ví dụ “ngày kết thúc phải sau ngày bắt đầu”. Nếu chỉ dùng `getFieldErrors()` như demo, các global errors sẽ không được đưa vào response.

Với production, có thể chuẩn hóa:

~~~json
{
  "code": "VALIDATION_ERROR",
  "message": "Dữ liệu yêu cầu không hợp lệ",
  "errors": [
    {
      "field": "startDate",
      "message": "Ngày bắt đầu không hợp lệ"
    },
    {
      "field": null,
      "message": "Ngày kết thúc phải sau ngày bắt đầu"
    }
  ]
}
~~~

Đây là **ví dụ contract**, không phải output của project ở mục 7 (vì project đó không có startDate/endDate). Khi thêm class-level custom validator, hãy đọc `getGlobalErrors()` và resolve qua `MessageSource.getMessage(ObjectError,locale)`; giới hạn giá trị được xuất ra.

### 9.2. DefaultMessageCodesResolver và thông điệp riêng theo field

Các key như `Size.registrationRequest.name`, `Size.name`, `Size.java.lang.String`, `Size` là những mức ưu tiên thông điệp có thể được Spring tạo. Để tránh dịch một constraint chung thành message sai ở mọi field, dùng key cụ thể khi cần:

~~~properties
NotBlank.registrationRequest.name=Please enter a name
NotBlank.name=This name is required
NotBlank=This field is required
~~~

Khi `MessageSource.getMessage(FieldError,locale)` được gọi, key cụ thể có thể ưu tiên. Tuy nhiên, project demo dùng `@NotBlank(message="{registration.name.required}")` và không khai báo `NotBlank...` để tránh hai nguồn định nghĩa khác nhau.

### 9.3. MessageFormat placeholder và escaping

Ví dụ key có arguments:

~~~properties
validation.size=Please enter between {0} and {1} characters
~~~

Code:

~~~java
messages.getMessage(
        "validation.size", new Object[]{3, 40}, locale);
~~~

sẽ điền các tham số theo thứ tự, và bản dịch tiếng Việt có thể đảo vị trí tham số nếu câu tự nhiên yêu cầu. Với thông điệp chứa apostrophe, Java `MessageFormat` xử lý dấu nháy đơn như ký tự điều khiển quoting; test chính xác các message có apostrophe, brace hoặc format date/number.

Trong constraint `@Size(min=3,max=40)`, các thành phần `{min}`/`{max}` là attribute interpolation của Bean Validation. Không thay chúng bằng `{0}` một cách tùy tiện nếu đang dựa vào Bean Validation message interpolator, hoặc trộn chuỗi có placeholder không cùng cơ chế.

### 9.4. Bản địa hóa lỗi nghiệp vụ

Lỗi nghiệp vụ không nhất thiết đến từ `BindingResult`. Ví dụ một service phát hiện email đã đăng ký, có thể ném exception nghiệp vụ có **stable code** `EMAIL_ALREADY_REGISTERED`; advice dịch message bằng key `business.email.duplicate`.

Không nên đưa nguyên `Exception.getMessage()` ra API: nó có thể không dịch được, chứa email/SQL/class name hoặc thông tin nhạy cảm. Chỉ đưa mã lỗi và thông điệp thuộc public catalog, đồng thời log nội bộ có request correlation ID.

## 10. Problem Details và ResponseEntityExceptionHandler

Spring Framework hỗ trợ RFC 9457 `ProblemDetail` với các trường `type`, `title`, `status`, `detail`, `instance` và custom properties. Nếu ứng dụng muốn response chuẩn thay vì record `ApiError`, có thể cấu hình trong Spring Boot 3.5:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

Khi bật, Spring Boot có thể cung cấp `ResponseEntityExceptionHandler` để xử lý nhiều lỗi MVC tích hợp và tra `MessageSource` cho title/detail. Nhưng một custom `@RestControllerAdvice` vẫn có thể quyết định response khác tùy phạm vi/độ ưu tiên; cần chọn **một chiến lược lỗi rõ ràng**.

Ví dụ đoạn method minh họa:

~~~java
ProblemDetail detail = ProblemDetail.forStatus(
        HttpStatus.BAD_REQUEST);
detail.setTitle(messages.getMessage(
        "validation.failed", null, locale));
detail.setProperty("code", "VALIDATION_ERROR");
return detail;
~~~

Đoạn này cần imports/biến messages, locale và không phải class độc lập. Spring có thể serialize `ProblemDetail` dạng `application/problem+json` khi converter phù hợp. Nếu extend `ResponseEntityExceptionHandler`, nên override `handleMethodArgumentNotValid(...)` hoặc hooks liên quan, không tạo handler `@ExceptionHandler` trùng mapping với lớp cha.

Tài liệu Spring MVC mô tả message codes có dạng `problemDetail.[fully-qualified-exception-class]`; `MethodArgumentNotValidException` và `HandlerMethodValidationException` cũng có tham số message dùng `MessageSourceResolvable`. Do đó nhiều thông báo có thể bản địa hóa mà không viết một exception handler tùy chỉnh cho từng loại.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Response chỉ hiện `{registration.name.required}` | Missing key/bundle/validator integration | Kiểm tra messages.properties, tên key, classpath, Spring validator |
| Có `messages_vi.properties` nhưng luôn English | Chưa có default messages.properties; locale chưa chọn vi | Kiểm tra Spring Boot i18n auto-config và `Accept-Language` |
| Tiếng Việt bị lỗi dấu | Encoding không phải UTF-8, build đổi encoding | `spring.messages.encoding`, file encoding, response charset |
| Message đổi theo máy dev/prod | Fallback theo JVM/system locale | Dùng `fallback-to-system-locale=false`, kiểm tra default bundle |
| Đã gửi `Accept-Language: vi` nhưng không đổi | Custom `LocaleResolver` hoặc `spring.web.locale-resolver=fixed` | Kiểm tra resolver đang được dùng, request headers |
| Constraint không được chạy | Thiếu validation provider, `@Valid`, binding chưa chạy | Starter validation, `@Valid`, type annotation và log |
| `@Email` chấp nhận chuỗi rỗng | Email syntax constraint không đồng nghĩa requiredness | Thêm `@NotBlank` với key riêng |
| `@Valid` lỗi nhưng handler không chạy | Controller có `BindingResult` ngay sau đối số hoặc nhánh method validation khác | Phân biệt `MethodArgumentNotValidException` và `HandlerMethodValidationException` |
| Lỗi JSON cú pháp thành validation message | Advice quá rộng hoặc mapping exception sai | Bắt riêng `HttpMessageNotReadableException` |
| Path `abc` thành `long` báo key DTO validation | Bắt quá rộng `Exception`/code mismatch | Bắt `MethodArgumentTypeMismatchException` riêng |
| JSON gửi sai Content-Type nhưng trả 400 | Error handler che mất 415 | Giữ `HttpMediaTypeNotSupportedException` và status đúng |
| Default message chứa `{0}`/apostrophe bất thường | Sai cơ chế MessageFormat/Bean Validation interpolation | Phân biệt placeholders và escape theo cơ chế |
| Một field có nhiều error và test chập chờn | Phụ thuộc thứ tự errors không được contract đảm bảo | Assert theo field/code, sort công khai có chủ đích |
| Global validation error không xuất hiện | Chỉ đọc `getFieldErrors()` | Kết hợp `getGlobalErrors()` khi có class-level constraint |
| Bản dịch đúng nhưng response lộ password/token | In rejectedValue/cause/raw body ra response | Giới hạn fields và dùng message catalog an toàn |
| Có hai exception handlers cho cùng class | Advice kế thừa `ResponseEntityExceptionHandler` nhưng còn khai báo handler trùng | Override protected methods hoặc chọn một chiến lược |
| Exception từ Spring Security chưa được dịch | Filter chain chạy trước DispatcherServlet | Thiết lập security localization/handlers và LocaleContextHolder phù hợp |
| Locale thay đổi nhưng cache trả sai ngôn ngữ | Shared cache không phân biệt Accept-Language | Dùng chính sách `Vary: Accept-Language` hoặc cache key theo locale |

### 11.1. Debug an toàn

Ở môi trường test, log tên exception và field codes, không cần log raw body hay token. Kiểm tra lần lượt: `Accept-Language` đầu vào → locale được resolver chọn → `MessageSource` có key → Bean Validation có chạy → `BindingResult` chứa code/defaultMessage gì → advice tạo response ra sao.

Có thể inject `MessageSource` trong test và gọi:

~~~java
String msg = messages.getMessage(
        "registration.name.required", null, Locale.forLanguageTag("vi"));
~~~

Kỳ vọng là “Tên không được để trống”. Nếu lookup này đúng mà HTTP response sai, nguyên nhân nhiều khả năng nằm ở locale resolver, validator/interpolator, hoặc exception handling, không phải thiếu key.

Đối với HTTP response được cache chung, nội dung thay đổi theo `Accept-Language` phải có cache policy an toàn, ví dụ `Vary: Accept-Language` khi phù hợp; những response chứa thông tin cá nhân thường nên tránh shared caching.

## 12. Các giới hạn bảo mật và sản phẩm

1. **Không đưa rejectedValue vào JSON lỗi**. Email, password, API key, token và giá trị query có thể nhạy cảm.
2. **Không trả stack trace, binding target, SQL, class names hoặc root exception cause** cho client. Log nội bộ phải có phân quyền và redaction.
3. **Không dựa vào text để phân quyền hay xử lý tự động**; dùng `code`, `field`, HTTP status và chuẩn hóa schema.
4. **Không coi `Accept-Language` là danh tính/địa lý**. Đây là tín hiệu preference không đáng tin cho quyết định bảo mật.
5. **Không bắt mọi exception rồi trả 400**; giữ 401/403/404/409/415/422/500 theo semantics và hợp đồng API phù hợp.
6. **Bản địa hóa cả ngữ nghĩa, không chỉ dịch chữ**: thông điệp cho người dùng cần chỉ rõ cách khắc phục, tránh đổ lỗi hoặc lộ nội bộ.
7. **Giữ bản dịch đồng bộ**: CI check keys, placeholders, encoding, ngôn ngữ fallback và version của mobile/web frontend.
8. **Không áp dụng hard-code message tiếng Việt vào validation annotation** nếu API phục vụ nhiều ngôn ngữ; dùng keys và bundles.
9. **Tránh quá tin default exception message**: nội dung từ Hibernate Validator/Jackson thay đổi giữa phiên bản và không nhất thiết là public API contract.
10. **Rà soát khi nâng Boot 4.x**: API/packages, starter webmvc/validation/test, Jackson 3, Problem Details/error auto-configuration và cách khai báo locale resolver có thể thay đổi; test locale và response contract trở thành regression tests.

## 13. Checklist để đưa vào production

- [ ] Có `messages.properties` mặc định và mọi bundle locale hỗ trợ trong JAR.
- [ ] Cấu hình `spring.messages.encoding=UTF-8` và fallback độc lập hệ điều hành.
- [ ] Sử dụng `Accept-Language` hoặc chiến lược locale được sản phẩm chủ động lựa chọn.
- [ ] Validation annotations chứa message keys, không hard-code ngôn ngữ.
- [ ] Có `spring-boot-starter-validation` và kiểm thử provider khởi tạo đúng.
- [ ] Có response contract ổn định (`code`, `message`, `errors[]`) hoặc ProblemDetail chuẩn.
- [ ] Phân biệt `MethodArgumentNotValidException`, `HandlerMethodValidationException`, lỗi bind/convert, lỗi đọc body và 415.
- [ ] FieldError và ObjectError được hiển thị theo policy; không lộ raw rejected values.
- [ ] Test ít nhất English và tiếng Việt cho cùng một lỗi, plus header thiếu và locale không hỗ trợ.
- [ ] Test các ràng buộc khác nhau, JSON sai, path/query sai kiểu, và trường hợp hợp lệ.
- [ ] Test các keys có `MessageFormat` arguments, apostrophes và Unicode.
- [ ] Đã xác minh security/authorization errors được xử lý riêng, không bị biến thành validation 400.
- [ ] Có chính sách cache đúng khi response khác nhau theo locale.
- [ ] Kiểm tra message catalog và error schema khi nâng Spring Boot/Framework.

**Kết luận:** để bản địa hóa validation error đúng trong Spring Boot, hãy tách **ràng buộc** (`@Valid`/Jakarta Bean Validation), **nguồn bản dịch** (`MessageSource`), **locale của request** (`LocaleResolver`) và **response contract** (`@RestControllerAdvice` hoặc Problem Details). Key ổn định, thông điệp được tra theo locale, và các bài test Việt/Anh giúp API vừa dễ dùng vừa nhất quán.

## Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Internationalization, bundles và cấu hình `spring.messages.*`: https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html
- Spring Boot 3.5 — Validation và MessageSource interpolation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Boot 3.5 — Common Application Properties (`spring.web.locale`, `spring.messages.*`): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Framework — MVC Validation, MethodArgumentNotValidException và HandlerMethodValidationException: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — Controller Method Exception Handling: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework — MVC Error Responses / Problem Details: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework — MVC LocaleResolver: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html
- Spring Framework — Validation Error Code Resolution: https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html
- Spring Framework — Bean Validation và tùy chỉnh validation errors: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — MessageSource API/concepts: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
